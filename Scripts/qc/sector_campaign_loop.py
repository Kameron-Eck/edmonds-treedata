r"""Sector-campaign autonomous loop — executes pipeline/sector_campaign_checklist.yaml.

THE CONTRACT (sector program, 2026-08-24). The checklist is the AUTHORED source of truth
(what must happen, how each item is verified, who runs it). This loop is the executor:
each tick it merges the measured state (data-plane JSONL, append-only, one file per launch,
latest-ts-wins per item — the train_queue_status pattern), picks runnable items (deps done
or skipped, owner available), executes, verifies, appends state, and exits when everything
is terminal (0), a blocking item failed with nothing else runnable (1), or the deadline
passed (2). Restart is resume: state is re-merged from disk, and verify-first idempotency
means an item whose verify already passes is marked done without re-executing.

Owners: local (subprocess, serial) · qc-vm / gpu-vm (colab exec, fire-and-poll) ·
kam (never executed — polled until verify passes or wait_min expires -> skipped).

Claude's role is reduced to: kickoff, failure triage on exit 1/2, final report narrative.

USAGE
  py -3.12 qc/sector_campaign_loop.py --check            # validate the checklist
  py -3.12 qc/sector_campaign_loop.py --status           # merged state table
  py -3.12 qc/sector_campaign_loop.py --emit-vm-scripts  # write VM exec scripts to scratch
  py -3.12 qc/sector_campaign_loop.py --write-seed       # the 24-row inference-only seed CSV
  py -3.12 qc/sector_campaign_loop.py --score-all        # qc_indep over the new sector arms
  py -3.12 qc/sector_campaign_loop.py --postproc-all     # VM postproc at live thresholds
  py -3.12 qc/sector_campaign_loop.py --postproc-audit   # exit 0 iff every scored arm has masks
  py -3.12 qc/sector_campaign_loop.py --report           # machine report skeleton
  py -3.12 qc/sector_campaign_loop.py --run --deadline-min 720   # the loop
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
DATA = Path(r"G:\My Drive\treedata")
CHECKLIST = SCRIPTS / "pipeline" / "sector_campaign_checklist.yaml"
CAMP = DATA / "phase4" / "qc" / "sector_campaign"
COLAB = r"/c/Users/Kameron/.local/bin/colab.exe"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import BAD_STATES, is_status_file   # stdlib-only; see names.py

BASH = shutil.which("bash") or r"C:\Program Files\Git\bin\bash.exe"
SCRATCH_DEFAULT = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "sector_campaign_vm"

BASE_JOBS = ["2006s_b20", "2011s_b20", "2003s_b20", "2012s_b20", "2018s_b20", "2020s_b20"]
BASE_YEARS = ["2006s", "2011s", "2003s", "2012s", "2018s", "2020s"]
NEW_ARMS = [(y, "sectors_v1") for y in BASE_YEARS] + [("2016", "fullext_sectors_v1"),
                                                     ("2021s", "fullext_sectors_v1")]
SEED_STEPS = ["labels", "tile", "train", "evaluate"]
# Was a hand-copy of SIX states against the queue's ten — it could not see
# BAD_CKPT, NO_TILES, BAD_INDEX, UNREADABLE, STALE_EVAL or SIZE_CHANGED, so a
# campaign job that failed any of those read as fine and the loop continued.
HARD_FAIL = set(BAD_STATES)
NOW = lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")  # noqa: E731


def _yaml():
    import yaml
    return yaml.safe_load(CHECKLIST.read_text(encoding="utf-8"))


def _resolve(path: str) -> Path:
    if path.startswith("data:"):
        return DATA / path[5:]
    if path.startswith("repo:"):
        return SCRIPTS / path[5:]
    return Path(path)


def _sub(cmd: str, scratch: Path) -> str:
    return cmd.replace("{colab}", COLAB).replace("{scratch}", scratch.as_posix())


def merged_state():
    state = {}
    for p in sorted(CAMP.glob("state_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            cur = state.get(r["item_id"])
            if cur is None or r["ts"] >= cur["ts"]:
                state[r["item_id"]] = r
    return state


class Ledger:
    def __init__(self, launch):
        CAMP.mkdir(parents=True, exist_ok=True)
        self.path = CAMP / f"state_{launch}.jsonl"
        self.launch = launch

    def append(self, item_id, state, evidence="", retries=0):
        rec = {"item_id": item_id, "state": state, "ts": NOW(),
               "evidence": str(evidence)[:800], "retries": retries, "launch": self.launch}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"  [{state.upper():8s}] {item_id}  {str(evidence)[:110]}", flush=True)


def run_cmd(cmd: str, timeout=900):
    """Run a checklist cmd through bash (handles quoting, the colab posix path, git)."""
    try:
        r = subprocess.run([BASH, "-lc", f"cd '{SCRIPTS.as_posix()}' && {cmd}"],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s"


def check_verify(clause, scratch) -> tuple[bool, str]:
    if "file" in clause:
        c = clause["file"] if isinstance(clause["file"], dict) else clause
        p = _resolve(c["path"] if "path" in c else clause["file"])
        need = c.get("min_bytes", 1)
        ok = p.exists() and p.stat().st_size >= need
        return ok, f"{p.name} {'%d B' % p.stat().st_size if p.exists() else 'MISSING'}"
    if "csv_rows" in clause:
        c = clause["csv_rows"]
        p = _resolve(c["path"])
        if not p.exists():
            return False, f"{p.name} MISSING"
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        for k, v in (c.get("where") or {}).items():
            rows = [r for r in rows if str(r.get(k, "")).strip() == str(v)]
        tags = c.get("contains_tag_any")
        if tags:
            rows = [r for r in rows if any(t in (r.get("prob", "") + r.get("run_tag", ""))
                                           for t in tags)]
        ok = len(rows) >= c.get("min_rows", 1)
        return ok, f"{p.name}: {len(rows)} matching rows"
    if "cmd" in clause:
        code, out = run_cmd(_sub(clause["cmd"], scratch), timeout=1200)
        ok = code == clause.get("expect_exit", 0)
        pat = clause.get("stdout_re")
        if ok and pat and not re.search(pat, out, re.M):
            ok = False
        return ok, f"exit {code} " + out.strip().splitlines()[-1][:100] if out.strip() else f"exit {code}"
    if "queue_verify" in clause:
        c = clause["queue_verify"]
        rows = []
        root = _resolve(c["glob"].split("*")[0]).parent
        pat = Path(c["glob"].replace("data:", "")).name
        # the checklist's glob is deliberately narrow (one campaign), but it is still
        # filtered through the one discovery rule — a file renamed aside is not data.
        for p in sorted(q for q in (DATA / "phase4" / "qc").glob(pat)
                        if is_status_file(q)):
            rows += list(csv.DictReader(open(p, encoding="utf-8")))
        verdicts = {}
        for r in rows:
            if r.get("step") == "VERIFY":
                # `job` only. This file's OWN column contract, ~35 lines below, records
                # that a first version wrote `job_id` and the seed went silently
                # invisible, so the queue began full fine-tunes for the base years
                # (caught 4 min in, 2026-08-25). A fallback to the column that caused
                # that invites the same row back.
                verdicts[r.get("job")] = \
                    (r.get("state") or "").upper()
        missing = [j for j in c["jobs"] if j not in verdicts]
        bad = {j: v for j, v in verdicts.items()
               if j in c["jobs"] and any(h in v for h in HARD_FAIL)}
        if missing:
            return False, f"awaiting VERIFY for {missing}"
        if bad:
            return False, f"HARD FAIL {bad}"
        return True, f"all VERIFY non-hard-fail: { {j: verdicts[j] for j in c['jobs']} }"
    return False, f"unknown verify clause {list(clause)}"


def verify_item(item, scratch):
    evs = []
    for clause in item.get("verify", []):
        ok, ev = check_verify(clause, scratch)
        evs.append(ev)
        if not ok:
            return False, "; ".join(evs)
    return True, "; ".join(evs)


# ----------------------------------------------------------------------------- operations
def _seed_ts():
    """LATER than any real queue row so the seed wins the ts-sorted merge — a killed
    launch leaves RUNNING rows that revoke earlier OKs
    (phase4_train_queue.py::_completed_steps)."""
    import datetime as _dt
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")   # queue rows are UTC


def write_seed():
    out = DATA / "phase4" / "qc" / "train_queue_status_queue_sectors_base2020_seed.csv"
    # COLUMN CONTRACT: _completed_steps reads r.get("job") — the header must be the
    # queue's own (job,year,tag,step,state,exit,minutes,detail,ts). A first version
    # wrote "job_id" and the seed was silently invisible: the queue started running
    # FULL fine-tunes for the base years (caught 4 min in, 2026-08-25). Keys must
    # match the reader, and the reader is phase4_train_queue.py::_completed_steps.
    cols = ["job", "year", "tag", "step", "state", "exit", "minutes", "detail", "ts"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for j, y in zip(BASE_JOBS, BASE_YEARS):
            for s in SEED_STEPS:
                w.writerow({"job": j, "year": y, "tag": "sectors_v1", "step": s,
                            "state": "OK", "exit": 0, "minutes": 0,
                            "detail": "SEEDED: base-model inference only "
                                      "(sem_best_2020 copy; no fine-tune)",
                            "ts": _seed_ts()})
    print(f"seed CSV: {out} (24 rows)")
    return 0


def live_thresholds():
    """(year, tag) -> (thresh, precision, recall) from qc_indep live rows, latest ts."""
    p = DATA / "phase4" / "qc" / "qc_indep_report.csv"
    out = {}
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if str(r.get("live", "")).strip() != "1" or str(r.get("primary", "")).strip() != "1":
            continue
        tag = ""
        m = re.search(r"prob_[0-9a-z]+_(.+)\.tif", r.get("prob", ""))
        if m:
            tag = m.group(1)
        key = (str(r["year"]), tag)
        if key not in out or r.get("ts", "") >= out[key][3]:
            out[key] = (float(r["thresh"]), float(r["recall"]), float(r["precision"]),
                        r.get("ts", ""))
    return out


def _ccap_ref(year: str) -> str:
    """Epoch-matched C-CAP reference (local-first). <=2018 -> the 2016 snohfull product,
    >=2019 -> 2021 — the same convention the campaign's existing live rows use."""
    yi = int(re.match(r"(\d{4})", year).group(1))
    name = ("ccap_2016_hires_lc_snohfull.tif" if yi <= 2018 else "ccap_2021_hires_lc.tif")
    for root in (Path(r"D:/edmonds-pipeline/Imagery"),
                 DATA / "Full_Image" / "Pipeline Imagery"):
        if (root / name).exists():
            return (root / name).as_posix()
    return name


def score_all():
    rc = 0
    for year, tag in NEW_ARMS:
        prob = DATA / "phase4" / "masks" / f"edmonds_canopy_prob_{year}_{tag}.tif"
        if not prob.exists():
            print(f"  {year}/{tag}: prob missing — skipped (queue incomplete or job failed)")
            continue
        code, out = run_cmd(
            f"py -3.12 qc/phase4_qc_indep.py --year {year} --ref '{_ccap_ref(year)}' "
            f"--prob '{prob.as_posix()}'",
            timeout=5400)
        print(f"  {year}/{tag}: qc_indep exit {code}")
        rc |= (0 if code == 0 else 1)
    return rc


def postproc_all(scratch):
    th = live_thresholds()
    scratch.mkdir(parents=True, exist_ok=True)
    rc = 0
    for year, tag in NEW_ARMS:
        prob = DATA / "phase4" / "masks" / f"edmonds_canopy_prob_{year}_{tag}.tif"
        mask = DATA / "phase4" / "masks" / f"edmonds_canopy_mask_{year}_{tag}.tif"
        if not prob.exists() or mask.exists():
            continue
        key = (year, tag)
        if key not in th:
            print(f"  {year}/{tag}: NO LIVE THRESHOLD ROW — refusing postproc "
                  f"(the 0.5 fallback is forbidden)")
            rc = 1
            continue
        t = th[key][0]
        vs = scratch / f"vm_postproc_{year}_{tag}.py"
        vs.write_text(
            "import subprocess, sys\n"
            "r = subprocess.run([sys.executable, 'phase4_semantic_finetune.py',\n"
            f"    '--year', '{year}', '--step', 'postproc', '--run-tag', '{tag}',\n"
            f"    '--infer-thresh', '{t}'],\n"
            "    cwd='/content/repo/Scripts/pipeline', capture_output=True, text=True)\n"
            "print(r.stdout[-1500:]); print(r.stderr[-500:])\n"
            "print('POSTPROC_RC', r.returncode)\n", encoding="utf-8")
        code, out = run_cmd(f"{COLAB} exec -s qc -f {vs.as_posix()} --timeout 3600",
                            timeout=3900)
        ok = code == 0 and "POSTPROC_RC 0" in out
        print(f"  {year}/{tag}: postproc @{t} -> {'OK' if ok else 'FAIL'}")
        rc |= (0 if ok else 1)
    return rc


def postproc_audit():
    th = live_thresholds()
    bad = []
    for year, tag in NEW_ARMS:
        prob = DATA / "phase4" / "masks" / f"edmonds_canopy_prob_{year}_{tag}.tif"
        mask = DATA / "phase4" / "masks" / f"edmonds_canopy_mask_{year}_{tag}.tif"
        if not prob.exists():
            print(f"  {year}/{tag}: no prob (job did not run) — excused")
            continue
        if (year, tag) in th and not mask.exists():
            bad.append(f"{year}/{tag}")
    if bad:
        print("MISSING masks for scored arms:", bad)
        return 1
    print("postproc audit clean")
    return 0


def report():
    state = merged_state()
    th = live_thresholds()
    lines = [f"# Sector campaign v1 — machine report skeleton ({NOW()})", "",
             "## Checklist outcomes", "| item | state | evidence |", "|---|---|---|"]
    for iid, r in sorted(state.items()):
        lines.append(f"| {iid} | {r['state']} | {r['evidence'][:120]} |")
    lines += ["", "## New arms (year, tag) -> live threshold (recall, precision)"]
    for (y, t), (thr, rec, prec, _) in sorted(th.items()):
        if t in ("sectors_v1", "fullext_sectors_v1"):
            lines.append(f"- {y}/{t}: thr {thr} (r {rec}, p {prec})")
    for name in ("sector_canopy_series.csv", "city_canopy_totals_design.csv"):
        p = CAMP / name
        lines.append(f"\n## {name}: "
                     f"{'%d rows' % (len(open(p, encoding='utf-8').readlines()) - 1) if p.exists() else 'MISSING'}")
    out = CAMP / "sector_campaign_v1_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"-> {out} ({out.stat().st_size} B)")
    return 0


def emit_vm_scripts(scratch):
    scratch.mkdir(parents=True, exist_ok=True)
    tok = subprocess.run([r"C:/Program Files/GitHub CLI/gh.exe", "auth", "token"],
                         capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True, cwd=SCRIPTS).stdout.strip()
    (scratch / "vm_probe.py").write_text(
        "import os, platform\nprint('VM OK', platform.node())\n"
        "print('DRIVE_MOUNTED', os.path.isdir('/content/drive/MyDrive/treedata'))\n",
        encoding="utf-8")
    (scratch / "vm_aoi_dryrun.py").write_text(
        "import subprocess, sys\n"
        f"BR = {branch!r}\n"
        "for c in (['git','-C','/content/repo','fetch','origin',BR],\n"
        "          ['git','-C','/content/repo','checkout','-B',BR,'FETCH_HEAD']):\n"
        "    subprocess.run(c, capture_output=True)\n"
        "r = subprocess.run([sys.executable, 'phase4_semantic_finetune.py', '--year', '2006s',\n"
        "    '--step', 'inference', '--dry-run', '--run-tag', 'aoi_smoke',\n"
        "    '--infer-aoi', 'aoi/sectors_v1.json'],\n"
        "    cwd='/content/repo/Scripts/pipeline', capture_output=True, text=True)\n"
        "print(r.stdout[-2000:]); print(r.stderr[-800:])\n", encoding="utf-8")
    (scratch / "vm_copy_ckpts.py").write_text(
        "import shutil, os\n"
        "D = '/content/drive/MyDrive/treedata'\n"
        "src = D + '/phase3/sem_best_2020.pt'\n"
        f"for y in {BASE_YEARS!r}:\n"
        "    dst = D + f'/phase4/models/sem_best_{y}_sectors_v1.pt'\n"
        "    if not (os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src)):\n"
        "        shutil.copy2(src, dst)\n"
        "    print(y, os.path.getsize(dst))\n"
        "print('CKPTS_DONE')\n", encoding="utf-8")
    for name, queue in (("vm_launch_base2020.py", "queue_sectors_base2020.yaml"),
                        ("vm_launch_fullext.py", "queue_sectors_fullext.yaml")):
        (scratch / name).write_text(
            "import os, subprocess, datetime\n"
            f"BR = {branch!r}\n"
            "REPO = '/content/repo'\n"
            f"AUTH = 'https://x-access-token:{tok}@github.com/Kameron-Eck/edmonds-treedata.git'\n"
            "if os.path.exists(REPO):\n"
            "    subprocess.run(['git','-C',REPO,'remote','set-url','origin',AUTH], check=True)\n"
            "    subprocess.run(['git','-C',REPO,'fetch','--depth','1','origin',BR], check=True)\n"
            "    subprocess.run(['git','-C',REPO,'checkout','-B',BR,'FETCH_HEAD'], check=True)\n"
            "else:\n"
            "    subprocess.run(['git','clone','--depth','1','--branch',BR,AUTH,REPO], check=True)\n"
            "subprocess.run(['git','-C',REPO,'remote','set-url','origin',\n"
            "    'https://github.com/Kameron-Eck/edmonds-treedata.git'], check=True)\n"
            "subprocess.run(['python','-m','pip','install','-q','-r',\n"
            "    REPO + '/Scripts/requirements-colab.txt'], check=True)\n"
            "ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')\n"
            f"log = '/content/drive/MyDrive/treedata/phase4/logs/train_queue_nohup_{queue[:-5]}_' + ts + '.log'\n"
            "p = subprocess.Popen('cd ' + REPO + '/Scripts/pipeline && nohup python -u "
            f"phase4_train_queue.py --queue {queue} > ' + log + ' 2>&1 & echo $!',\n"
            "    shell=True, stdout=subprocess.PIPE, text=True)\n"
            "out, _ = p.communicate(timeout=30)\n"
            "print('LAUNCHED pid', out.strip()); print('LOG', log)\n", encoding="utf-8")
    print(f"VM scripts -> {scratch}  (launch scripts embed a token: delete after use)")
    return 0


# ----------------------------------------------------------------------------- the loop
def run_loop(deadline_min, scratch, tick_s=60):
    doc = _yaml()
    items = {i["id"]: i for i in doc["items"]}
    order = [i["id"] for i in doc["items"]]
    launch = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    led = Ledger(launch)
    t0 = time.monotonic()
    started, retries, gpu_session_created = {}, {}, False
    print(f"LOOP {launch}: {len(order)} items, deadline {deadline_min} min")

    def st(iid):
        return merged_state().get(iid, {}).get("state", "pending")

    def deps_ok(item):
        return all(st(d) in ("done", "skipped") for d in item.get("depends_on", []))

    while True:
        if (time.monotonic() - t0) / 60 > deadline_min:
            led.append("_loop", "failed", f"deadline {deadline_min} min reached")
            return 2
        state = merged_state()
        terminal = {i for i in order
                    if state.get(i, {}).get("state") in ("done", "skipped")
                    or (state.get(i, {}).get("state") == "failed"
                        and retries.get(i, 0) >= items[i].get("retries", 1))}
        if all(i in terminal for i in order):
            print("LOOP complete — all items terminal")
            return 0
        progressed = False
        for iid in order:
            item = items[iid]
            s = state.get(iid, {}).get("state", "pending")
            if iid in terminal or not deps_ok(item):
                continue
            # kam-owned: poll; create the gpu session once; skip after wait_min
            if item["owner"] == "kam":
                if iid == "S10_gpu_vm_up" and not gpu_session_created:
                    code, out = run_cmd(f"{COLAB} new -s gpu --gpu A100", timeout=600)
                    gpu_session_created = True
                    led.append(iid, "running",
                               f"A100 session created (exit {code}) — waiting for Kam's "
                               f"drivemount, max {item.get('wait_min', 120)} min")
                    started[iid] = time.monotonic()
                ok, ev = verify_item(item, scratch)
                if ok:
                    led.append(iid, "done", ev)
                    progressed = True
                elif iid in started and (time.monotonic() - started[iid]) / 60 > item.get("wait_min", 120):
                    led.append(iid, "skipped", "SKIPPED_NO_GPU: wait_min expired")
                    run_cmd(f"{COLAB} stop -s gpu", timeout=300)   # cap idle spend
                    progressed = True
                elif iid not in started:
                    started[iid] = time.monotonic()
                    led.append(iid, "running", "polling for Kam")
                continue
            if s == "running":
                ok, ev = verify_item(item, scratch)
                if ok:
                    led.append(iid, "done", ev)
                    progressed = True
                elif (time.monotonic() - started.get(iid, t0)) / 60 > item.get("timeout_min", 480):
                    led.append(iid, "failed", f"timeout_min exceeded; last: {ev}")
                    progressed = True
                continue
            # runnable
            ok, ev = verify_item(item, scratch)
            if ok:
                led.append(iid, "done", f"verify-first: {ev}")
                progressed = True
                continue
            if "run" not in item:
                continue
            if iid == "S11_base2020_queue" and st("S01_kam_review") != "done":
                led.append("_warn", "done", "S11 launching with sectors UNREVIEWED by Kam")
            cmd = _sub(item["run"], scratch)
            led.append(iid, "running", cmd[:110])
            started[iid] = time.monotonic()
            if item["owner"] in ("gpu-vm", "qc-vm"):
                code, out = run_cmd(cmd, timeout=3900)
                if code != 0:
                    retries[iid] = retries.get(iid, 0) + 1
                    led.append(iid, "failed", f"launch exit {code}: {out.strip()[:200]}",
                               retries[iid])
                # else stay running; polled next tick
            else:
                code, out = run_cmd(cmd, timeout=60 * item.get("timeout_min", 480))
                ok2, ev2 = verify_item(item, scratch)
                if code == 0 and ok2:
                    led.append(iid, "done", ev2)
                else:
                    retries[iid] = retries.get(iid, 0) + 1
                    led.append(iid, "failed",
                               f"exit {code}; verify: {ev2}; out: {out.strip()[-160:]}",
                               retries[iid])
            progressed = True
        # blocked-failure exit: a blocking failed item with no runnable work left
        state = merged_state()
        blocked = [i for i in order
                   if state.get(i, {}).get("state") == "failed"
                   and items[i].get("blocking", True)
                   and retries.get(i, 0) >= items[i].get("retries", 1)]
        runnable = [i for i in order if i not in terminal and deps_ok(items[i])
                    and state.get(i, {}).get("state") != "running"]
        if blocked and not runnable and not any(
                state.get(i, {}).get("state") == "running" for i in order):
            led.append("_loop", "failed", f"blocked on {blocked}")
            return 1
        if not progressed:
            time.sleep(tick_s)


def main():
    ap = argparse.ArgumentParser()
    for f in ("check", "status", "emit-vm-scripts", "write-seed", "score-all",
              "postproc-all", "postproc-audit", "report", "run"):
        ap.add_argument(f"--{f}", action="store_true")
    ap.add_argument("--deadline-min", type=int, default=720)
    ap.add_argument("--scratch", type=Path, default=SCRATCH_DEFAULT)
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])
    if a.check:
        doc = _yaml()
        ids = [i["id"] for i in doc["items"]]
        assert len(ids) == len(set(ids)), "duplicate ids"
        for i in doc["items"]:
            for d in i.get("depends_on", []):
                assert d in ids, f"{i['id']}: unknown dep {d}"
            assert i.get("verify"), f"{i['id']}: no verify"
        print(f"checklist OK: {len(ids)} items")
        return 0
    if a.status:
        state = merged_state()
        for i in _yaml()["items"]:
            r = state.get(i["id"], {})
            print(f"  {r.get('state', 'pending'):8s} {i['id']:26s} {r.get('evidence', '')[:90]}")
        return 0
    if a.emit_vm_scripts:
        return emit_vm_scripts(a.scratch)
    if a.write_seed:
        return write_seed()
    if a.score_all:
        return score_all()
    if a.postproc_all:
        return postproc_all(a.scratch)
    if a.postproc_audit:
        return postproc_audit()
    if a.report:
        return report()
    if a.run:
        return run_loop(a.deadline_min, a.scratch)
    print("nothing to do — see --help")
    return 0


if __name__ == "__main__":
    sys.exit(main())
