r"""cost_report.py — what the GPU work actually cost, and what each arm bought (E04).

TWO SUBCOMMANDS
    --launches                     harvest one row per queue LAUNCH -> Reports/gpu_launches.csv
    --per-arm --baseline <tag>     GPU-minutes and honest metrics per (year, run_tag)
                                   -> Reports/cost_per_arm.md + .csv

THE ONE FACT THAT SHAPES THIS WHOLE SCRIPT
Colab bills **VM uptime**, not engine-subprocess seconds. The queue only measures the
subprocess: it never sees VM setup, the repo clone, the pip bootstrap, ortho staging,
VERIFY reads, or idle time between jobs and after the last step. Measured over the real
status files, summed step-minutes cover between 0% and 100% of even the *observed* launch
span (mean ~60%) — a launch can have a 79-minute span and ZERO recorded step minutes when
the VM died before any step returned. So:

  * there is NO per-run `est_usd` / `compute_units` column anywhere in this pipeline, and
    there never will be — a per-run dollar figure would be a fiction with a decimal point;
  * rates apply to a LAUNCH SPAN, and even that is a LOWER BOUND (it starts at the first
    step, i.e. after VM setup, and ends at the last row written);
  * `measured_cu_delta` is the only column that could ever settle a bill, and it is
    hand-filled by Kam from the compute-unit balance before/after a launch. This script
    always leaves it blank rather than guessing.

An unknown or unmatched GPU yields BLANK cost, never 0. Silent-cheap — an arm that looks
free because nothing was recorded — is the exact failure this script exists to prevent.

NO MTIMES. Drive mtimes are meaningless here (FUSE rewrites them on sync, and the local
listing shows files "modified" hours off their content). Every time in this report comes
from a filename stamp (UTC, written by the launcher/queue) or a status row's `ts` column
(written by the VM, which runs UTC on Colab). The two are never subtracted from each
other: a launch's span is computed purely from row ts within one file.

Usage (local Windows, from the repo):
    py -3.12 pipeline/cost_report.py --launches
    py -3.12 pipeline/cost_report.py --per-arm --baseline sectors_v1
"""
import argparse
import csv
import datetime as _dt
import io
import re
import sys
from pathlib import Path

# names.py is STDLIB-ONLY (see its docstring) — the one status-file discovery rule,
# the one launch filter, and the one ledger row key, without the engine's deps.
from phase4seg.names import clean_argv, job_key, parse_status_name, status_files

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402
REPO = Path(__file__).resolve().parents[2]                           # code plane

QC_DIR = BASE / "phase4" / "qc"
LOG_DIR = BASE / "phase4" / "logs"
REPORTS = REPO / "Reports"
REGISTRY = REPO / "Scripts" / "run_registry.csv"
RATES = Path(__file__).resolve().parent / "colab_rates.csv"

LAUNCHES_CSV = REPORTS / "gpu_launches.csv"
PER_ARM_CSV = REPORTS / "cost_per_arm.csv"
PER_ARM_MD = REPORTS / "cost_per_arm.md"

# The launch stamp is what makes a status file a LAUNCH: the hand-written `_seed`
# files and the legacy shared train_queue_status.csv carry none, and a seed row
# records a step declared already-done, so it burned no GPU. That filter is right
# and is kept — it now comes from phase4seg.names.parse_status_name, which is also
# what DISCOVERY goes through. It used to be a glob for
#     train_queue_status_queue_*_2*.csv
# which additionally demanded the `_queue_` infix. Every queue file to date happens
# to be named queue_*.yaml, so that looked like a rule; it is a coincidence. The
# overhaul's pilot queue (pilot_2019.yaml) writes train_queue_status_pilot_2019_{ts}
# .csv and was globbed out — its A100 hours would have appeared in no cost report,
# silently. See names.py::parse_status_name.
NOHUP_RE = re.compile(r"^train_queue_nohup_(?P<stem>.+)_(?P<ts>\d{8}T\d{6}Z)\.log$")
# the queue header prints:  "  GPU    : NVIDIA A100-SXM4-40GB, 40960 MiB   (ceilings ...)"
GPU_LINE_RE = re.compile(r"^\s*GPU\s*:\s*(?P<val>.+?)\s*$")
GPU_MIB_RE = re.compile(r"^(?P<name>.+?),\s*\d+\s*MiB\b")

EST_LABEL = ("ESTIMATE (lower bound: span starts at first step; excludes VM setup/"
             "staging/teardown/idle)")

LAUNCH_COLUMNS = ["launch_id", "queue_file", "gpu_name", "first_step_ts", "last_row_ts",
                  "span_min", "sum_step_min", "coverage_pct", "n_steps", "n_ok",
                  "n_failed", "measured_cu_delta", "est_cu", "est_usd", "est_basis",
                  "est_label"]

LAUNCHES_HEADER_COMMENT = f"""\
# gpu_launches.csv — one row per queue LAUNCH. DERIVED AND REGENERABLE: every run of
# `py -3.12 pipeline/cost_report.py --launches` overwrites this file wholesale. Do not
# hand-edit it (the one exception is `measured_cu_delta`, see below, and a hand-filled
# value there WILL be lost on the next run until it is carried into a rate row).
#
# NOT the authoritative launch record. That is the CHATLOG launch line each launch must
# carry — OVERHAUL_PLAN_2026-08-20.md P11.5 rule 2: "every launch writes a run manifest
# (now with `git_branch`, `gpu`, `gpu_mem_gb`) and a CHATLOG line with tier, start time,
# expected hours". This table is a HARVEST of the artefacts those launches left behind
# (per-launch status CSVs + the queue's nohup log header); the prose log wins on conflict.
#
# TIMES: filename stamps (UTC) and status-row `ts` only. Drive mtimes are never read.
#
# COLUMN DEFINITIONS
#   launch_id      UTC stamp parsed from the status filename (the moment the queue started).
#   queue_file     the queue YAML, reconstructed from the same filename.
#   gpu_name       from the matching nohup log's "GPU : <name>, <MiB>" header line; BLANK
#                  if no log or no such line. BLANK means UNKNOWN, never "free".
#   first_step_ts  ts of the earliest non-VERIFY row (a step START).
#   last_row_ts    ts of the latest row of any kind in the file.
#   span_min       last_row_ts - first_step_ts. A LOWER BOUND on billable VM uptime: it
#                  begins after VM setup/clone/pip and ends at the last row written, so a
#                  step still RUNNING when the VM died contributes none of its own time.
#   sum_step_min   sum of the `minutes` column over ALL non-VERIFY, non-SEEDED rows,
#                  retries included (a retried step burns the GPU twice and is billed twice).
#   coverage_pct   100 * sum_step_min / span_min. THE HONESTY DIAL: it says how much of the
#                  observed window the engine can account for. May read slightly over 100%
#                  from the queue's 0.1-min rounding (measured: 18.3 vs an 18.27-min span);
#                  it is NOT clamped, because clamping would hide the rounding.
#   n_steps        distinct (job, step) pairs among non-VERIFY, non-SEEDED rows.
#   n_ok / n_failed  by each pair's LAST row: n_ok = final state OK; n_failed = final state
#                  neither OK nor RUNNING. A pair still RUNNING counts in n_steps but in
#                  NEITHER of the others — the VM died and nothing ever closed the row.
#   measured_cu_delta  ALWAYS BLANK here. The compute-unit balance before/after a launch is
#                  the only thing that can settle a bill, and only Kam can read it. Fill it
#                  by hand, then promote it into pipeline/colab_rates.csv as a MEASURED row.
#   est_cu/est_usd BLANK unless pipeline/colab_rates.csv has a row matching gpu_name. It
#                  ships with ZERO GPU rate rows on purpose (no sourced rate exists in this
#                  repo), so today every GPU launch here is blank — correctly.
#   est_basis      why the cost columns say what they say (which rate matched, or why none did).
#   est_label      the standing caveat: {EST_LABEL}
"""


# ── shared helpers ────────────────────────────────────────────────────────────
def _rows(path):
    """CSV rows, tolerating (and skipping) a leading '#' comment block."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def _f(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _fmt(v, nd=1):
    return "" if v is None else f"{v:.{nd}f}"


def _parse_row_ts(v):
    """A status row's `ts`: '%Y-%m-%d %H:%M:%S', written by the VM (UTC on Colab)."""
    try:
        return _dt.datetime.strptime(str(v).strip(), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _parse_stamp(v):
    try:
        return _dt.datetime.strptime(str(v), "%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError):
        return None


def load_rates(path=RATES):
    """The rate table, '#' comment block skipped. Missing file is not fatal — it just
    means every cost is blank, which is the safe direction."""
    rows = _rows(path)
    if not rows:
        print(f"  ! no rate rows in {path} — every cost column will be BLANK (safe).")
    return rows


def rate_for(gpu_name, rates):
    """(rate_row_or_None, reason). THE BLANK-NAME GUARD FIRES FIRST.

    An empty gpu_name means the probe failed or no log was found — "we do not know what
    this ran on". It must never fall through to a CPU/zero rate and make an unknown run
    look free, so it is short-circuited here, ahead of every pattern.
    """
    name = (gpu_name or "").strip()
    if not name:
        return None, "gpu_name UNKNOWN (no nohup header line) — cost BLANK by design"
    for r in rates:
        pat = (r.get("gpu_name_pattern") or "").strip()
        if not pat:
            continue
        try:
            if re.search(pat, name, re.IGNORECASE):
                return r, ""
        except re.error as e:
            print(f"  ! bad regex in colab_rates.csv ({pat!r}): {e} — row skipped.")
    return None, f"no rate row in colab_rates.csv matches {name!r} (no sourced rate exists)"


def cost_for_span(gpu_name, span_min, rates):
    """(est_cu, est_usd, est_basis) for a LAUNCH SPAN. Blank stays blank; 0 is only ever
    produced by a rate row that explicitly says 0 (the sourced CPU row)."""
    row, why = rate_for(gpu_name, rates)
    if row is None:
        return "", "", why
    tier = row.get("tier_label") or row.get("gpu_name_pattern") or "?"
    cph, upc = _f(row.get("cu_per_hour")), _f(row.get("usd_per_cu"))
    if span_min is None or cph is None:
        return "", "", (f"matched {tier} [{row.get('evidence_tier', '?')}] but "
                        f"{'span unknown' if span_min is None else 'cu_per_hour blank'} "
                        f"— cost BLANK")
    cu = cph * span_min / 60.0
    basis = (f"{cph:g} CU/hr x {span_min:.1f} min span = {cu:.2f} CU "
             f"[{tier}, {row.get('evidence_tier', '?')}, as_of {row.get('as_of', '?')}]")
    if upc is None:
        return f"{cu:.2f}", "", basis + "; usd_per_cu blank -> est_usd BLANK"
    return f"{cu:.2f}", f"{cu * upc:.2f}", basis + f" x ${upc:g}/CU"


def _is_verify(step):
    return str(step or "").upper().startswith("VERIFY")


def _is_seeded(row):
    return str(row.get("detail") or "").startswith("SEEDED")


# ── Layer B: --launches ───────────────────────────────────────────────────────
def gpu_from_nohup(stem, launch_id):
    """The GPU the queue printed in its own header, for THIS launch.

    Matching is not a plain filename equality: the launcher stamps the nohup log just
    before starting the queue, and the queue stamps its own status file a moment later,
    so the two stamps differ by a second or two on 4 of the 12 launches on disk
    (054716/054717, 172057/172058, 175540/175541, 061927/061928). An exact-name-only
    match would silently blank a third of the table — exactly the silent-cheap failure
    this script exists to prevent. So: exact name first, else the same queue stem with
    the NEAREST log stamp at or before the status stamp, within 120 s.
    """
    exact = LOG_DIR / f"train_queue_nohup_{stem}_{launch_id}.log"
    pick, how = (exact, "exact") if exact.exists() else (None, "")
    if pick is None:
        want = _parse_stamp(launch_id)
        best = None
        for p in sorted(LOG_DIR.glob(f"train_queue_nohup_{stem}_*.log")):
            m = NOHUP_RE.match(p.name)
            t = _parse_stamp(m.group("ts")) if m and m.group("stem") == stem else None
            if t is None or want is None:
                continue
            d = (want - t).total_seconds()
            if 0 <= d <= 120 and (best is None or d < best[0]):
                best = (d, p)
        if best:
            pick, how = best[1], f"log stamped {best[0]:.0f}s before the status file"
    if pick is None:
        return "", "no nohup log found for this launch"
    try:
        with open(pick, encoding="utf-8", errors="replace") as f:
            head = [next(f, "") for _ in range(40)]
    except OSError as e:
        return "", f"nohup log unreadable ({e})"
    for ln in head:
        m = GPU_LINE_RE.match(ln)
        if not m:
            continue
        val = m.group("val")
        mm = GPU_MIB_RE.match(val)
        if mm:                                   # "NVIDIA A100-SXM4-40GB, 40960 MiB  (…)"
            return mm.group("name").strip(), how
        # CPU runtimes print no MiB: "none (CPU runtime or no driver)   (ceilings …)"
        return re.split(r"\s{3,}\(", val)[0].strip(), how
    return "", f"no 'GPU :' header line in {pick.name}"


def harvest_launch(path, rates):
    parsed = parse_status_name(path.name)
    if parsed is None or parsed[1] is None:
        return None                      # not a status file, or not a LAUNCH
    stem, launch_id = parsed
    rows = _rows(path)

    steps = [r for r in rows if not _is_verify(r.get("step")) and not _is_seeded(r)]
    all_ts = [t for t in (_parse_row_ts(r.get("ts")) for r in rows) if t]
    step_ts = [t for t in (_parse_row_ts(r.get("ts")) for r in steps) if t]
    first = min(step_ts) if step_ts else (min(all_ts) if all_ts else None)
    last = max(all_ts) if all_ts else None
    span = (last - first).total_seconds() / 60.0 if (first and last) else None

    # retries append a NEW row for the same (job, step) and burn the GPU again, so the
    # minutes are summed over every row; the OUTCOME, though, is the last row's word.
    total = sum(v for v in (_f(r.get("minutes")) for r in steps) if v is not None)
    final = {}
    for r in steps:
        # D8's key, not (job, step): a job id is a nickname and nothing makes it mean
        # the same year and tag twice. See names.py::job_key.
        final[job_key(r.get("job"), r.get("year"), r.get("tag"),
                      r.get("step"))] = r                 # file order = chronological
    states = [str(r.get("state") or "").upper() for r in final.values()]
    n_ok = sum(1 for s in states if s == "OK")
    n_failed = sum(1 for s in states if s not in ("OK", "RUNNING"))

    gpu, _how = gpu_from_nohup(stem, launch_id)
    est_cu, est_usd, basis = cost_for_span(gpu, span, rates)
    cov = (100.0 * total / span) if (span and span > 0) else None
    return {
        "launch_id": launch_id,
        "queue_file": f"{stem}.yaml",
        "gpu_name": gpu,
        "first_step_ts": first.strftime("%Y-%m-%d %H:%M:%S") if first else "",
        "last_row_ts": last.strftime("%Y-%m-%d %H:%M:%S") if last else "",
        "span_min": _fmt(span),
        "sum_step_min": f"{total:.1f}",
        "coverage_pct": _fmt(cov),
        "n_steps": str(len(final)),
        "n_ok": str(n_ok),
        "n_failed": str(n_failed),
        "measured_cu_delta": "",          # hand-filled by Kam; never inferred here
        "est_cu": est_cu,
        "est_usd": est_usd,
        "est_basis": basis,
        "est_label": EST_LABEL,
    }


def cmd_launches():
    rates = load_rates()
    files = status_files(QC_DIR)          # harvest_launch drops seeds and the legacy file
    out = []
    for p in files:
        row = harvest_launch(p, rates)
        if row is None:                   # no launch stamp: the _seed file, hand-written
            print(f"  skip {p.name} (no launch stamp in the filename — not a launch)")
            continue
        out.append(row)
    out.sort(key=lambda r: r["launch_id"])

    REPORTS.mkdir(parents=True, exist_ok=True)
    with open(LAUNCHES_CSV, "w", encoding="utf-8", newline="") as f:
        f.write(LAUNCHES_HEADER_COMMENT)
        w = csv.DictWriter(f, fieldnames=LAUNCH_COLUMNS)
        w.writeheader()
        for r in out:
            w.writerow(r)

    print(f"\n{len(out)} launch(es) -> {LAUNCHES_CSV}\n")
    hdr = (f"{'launch_id':17s} {'queue_file':30s} {'gpu_name':22s} "
           f"{'span':>7s} {'steps':>7s} {'cov%':>6s} {'n':>3s} {'ok':>3s} {'fail':>4s}")
    print(hdr)
    print("-" * len(hdr))
    for r in out:
        print(f"{r['launch_id']:17s} {r['queue_file']:30s} "
              f"{(r['gpu_name'] or '(unknown)'):22s} {r['span_min']:>7s} "
              f"{r['sum_step_min']:>7s} {(r['coverage_pct'] or '-'):>6s} "
              f"{r['n_steps']:>3s} {r['n_ok']:>3s} {r['n_failed']:>4s}")
    covs = [_f(r["coverage_pct"]) for r in out]
    covs = [c for c in covs if c is not None]
    if covs:
        print(f"\ncoverage of step-minutes vs launch span: min {min(covs):.0f}%  "
              f"median {sorted(covs)[len(covs)//2]:.0f}%  mean {sum(covs)/len(covs):.0f}%  "
              f"max {max(covs):.0f}%   ({sum(1 for c in covs if c < 50)} of {len(covs)} "
              f"launches under 50%)")
    print("Colab bills VM UPTIME. Every span above is a LOWER BOUND and every cost column "
          "is blank\nunless colab_rates.csv sourced a rate. " + EST_LABEL)
    return 0


# ── Layer D: --per-arm ────────────────────────────────────────────────────────
TAG_RE = re.compile(r"--run-tag[= ]+(\S+)")
HONEST_RE = re.compile(r"honest rec ([0-9.]+) prec ([0-9.]+)")


def _tag_of(row):
    m = TAG_RE.search(row.get("args") or "")
    return m.group(1) if m else "(untagged)"


def _arm_launch_usd(rates):
    """Per-(year, tag) dollars, apportioned from LAUNCH-level costs by GPU step-minute
    share. Deliberately plumbing-only today: colab_rates.csv ships with no GPU rate row,
    so every launch's est_usd is blank and every arm's dollars come back blank with a
    reason. When a MEASURED rate lands, this starts producing numbers — clearly labelled
    INFERRED, because apportioning a VM's uptime across the arms it served is a model,
    not a measurement.
    """
    usd, blocked = {}, {}
    for p in status_files(QC_DIR):
        if (parse_status_name(p.name) or (None, None))[1] is None:
            continue                         # seed or legacy file: no GPU was burned
        rows = [r for r in _rows(p) if not _is_verify(r.get("step")) and not _is_seeded(r)]
        share, tot = {}, 0.0
        for r in rows:
            v = _f(r.get("minutes")) or 0.0
            key = (str(r.get("year") or ""), str(r.get("tag") or "(untagged)"))
            share[key] = share.get(key, 0.0) + v
            tot += v
        launch = harvest_launch(p, rates)
        amount = _f((launch or {}).get("est_usd"))
        for key in share:
            if amount is None:
                why = (launch or {}).get("est_basis") or "no cost computed for this launch"
            elif tot <= 0:
                why = ("launch carries a cost but recorded zero step-minutes — "
                       "unattributable to any arm")
            else:
                usd[key] = usd.get(key, 0.0) + amount * share[key] / tot
                continue
            blocked.setdefault(key, []).append((m.group("ts"), why))
    return usd, blocked


def _blocked_summary(entries):
    """One line per arm: the distinct REASON(s), with the launches that hit each. Reasons
    repeat verbatim across a dozen launches, so the launch ids are grouped under the
    reason rather than the reason repeated under each launch."""
    if not entries:
        return "no launch attributable to this arm"
    by_why = {}
    for lid, why in entries:
        by_why.setdefault(why, []).append(lid)
    return " | ".join(f"{why} [{len(ids)} launch(es): {', '.join(ids)}]"
                      for why, ids in by_why.items())


def cmd_per_arm(baseline):
    reg = _rows(REGISTRY)
    if not reg:
        sys.exit(f"no registry rows at {REGISTRY}")
    if "step_minutes" not in reg[0]:
        sys.exit("run_registry.csv has no `step_minutes` column — run\n"
                 "  py -3.12 pipeline/registry_from_manifests.py --migrate-columns")

    arms = {}
    for r in reg:
        key = (str(r.get("year") or "?"), _tag_of(r))
        a = arms.setdefault(key, {"rows": [], "min": 0.0, "timed": 0, "gpus": set()})
        a["rows"].append(r)
        v = _f(r.get("step_minutes"))
        if v is not None:
            a["min"] += v
            a["timed"] += 1
        if (r.get("gpu_name") or "").strip():
            a["gpus"].add(r["gpu_name"].strip())
        # The honest number is gated on the TEXT, not on the step name: hand-written rows
        # from July record a whole pipeline in one row ("tile+train+eval+inference+
        # postproc"), and an exact step=="inference" test threw their honest numbers away.
        # A row whose step mentions inference still wins over one that does not.
        m = HONEST_RE.search(r.get("headline_metrics") or "")
        if m:
            inf = "inference" in str(r.get("step") or "").lower()
            if inf or "rec" not in a or not a.get("rec_from_inference"):
                a["rec"], a["prec"] = float(m.group(1)), float(m.group(2))
                a["rec_from_inference"] = inf

    usd, blocked = _arm_launch_usd(load_rates())

    # the baseline is matched PER YEAR: an arm is only comparable to the same year's
    # baseline run, never to another year's (different imagery, different everything).
    base = {y: a for (y, t), a in arms.items() if t == baseline}
    if not base:
        print(f"  ! baseline tag {baseline!r}: no registry rows yet — every arm below is "
              f"reported in ABSOLUTE terms, with no delta column filled.")

    out = []
    for (year, tag), a in sorted(arms.items(),
                                 key=lambda kv: (-kv[1]["min"], kv[0][0], kv[0][1])):
        b = base.get(year)
        d_rec = d_prec = ""
        if b is not None and tag != baseline and "rec" in a and "rec" in b:
            d_rec, d_prec = f"{a['rec'] - b['rec']:+.4f}", f"{a['prec'] - b['prec']:+.4f}"
        n, timed = len(a["rows"]), a["timed"]
        if timed == 0:
            cav = ("NO TIMING COVERAGE — this arm's GPU-minutes are UNKNOWN, not zero "
                   "(pre-2026-08-25 rows carry their minutes as prose in `notes`)")
        elif timed < n:
            cav = (f"PARTIAL TIMING — {timed}/{n} rows timed; the total below is a LOWER "
                   f"BOUND and arms are NOT comparable on it")
        else:
            cav = ("all rows timed; still SUBPROCESS-only — excludes VM setup, staging, "
                   "VERIFY and idle, which Colab bills")
        u = usd.get((year, tag))
        out.append({
            "year": year, "run_tag": tag,
            "gpu_step_min": f"{a['min']:.1f}" if timed else "",
            "n_rows": str(n), "n_rows_timed": str(timed),
            "gpu_names": "; ".join(sorted(a["gpus"])),
            "honest_recall": f"{a['rec']:.4f}" if "rec" in a else "",
            "honest_precision": f"{a['prec']:.4f}" if "prec" in a else "",
            f"d_recall_vs_{baseline}": d_rec,
            f"d_precision_vs_{baseline}": d_prec,
            "est_usd": f"{u:.2f}" if u is not None else "",
            "est_usd_blocked_because": "" if u is not None
                else _blocked_summary(blocked.get((year, tag))),
            "caveat": cav,
        })

    REPORTS.mkdir(parents=True, exist_ok=True)
    cols = list(out[0].keys())
    with open(PER_ARM_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)

    n_timed = sum(1 for r in out if r["gpu_step_min"])
    md = [f"# Cost per arm — GPU-minutes and what they bought",
          "",
          f"*Generated by `pipeline/cost_report.py --per-arm --baseline {baseline}` on "
          f"{_dt.datetime.now().strftime('%Y-%m-%d')} from `Scripts/run_registry.csv`. "
          f"DERIVED AND REGENERABLE — regenerate it, never hand-edit it.*",
          "",
          "## Read this before reading a number",
          "",
          "* **`gpu_step_min` is engine-subprocess wall-clock only.** It excludes VM setup, "
          "the repo clone and pip bootstrap, ortho staging, VERIFY reads and idle time "
          "between jobs. Colab bills **VM uptime**, so this is a LOWER BOUND on billable "
          "time — across the real launches, summed step-minutes cover 0%–100% of even the "
          "observed launch span (see `Reports/gpu_launches.csv`).",
          "* **A blank `gpu_step_min` means UNKNOWN, not cheap.** "
          f"{len(out) - n_timed} of {len(out)} arms below have no timing coverage at all: "
          "their runs predate the 2026-08-25 registry cutover and carry their minutes as "
          "prose inside `notes`. Do not read those arms as free, and do not rank arms "
          "against each other on this column unless both say all rows timed.",
          "* **Dollars are blank on purpose.** `pipeline/colab_rates.csv` ships with zero "
          "GPU rate rows because no Colab GPU rate has a source anywhere in this repo. A "
          "figure would be hearsay with a decimal point. The way to fill it is a MEASURED "
          "compute-unit delta across a launch, not a remembered number.",
          "* **Honest metrics only** (CLAUDE.md rule 5): recall/precision below are the "
          "`live=1` independent numbers carried in the registry's inference rows — never "
          "held-out, never circular.",
          ""]
    if not base:
        md += [f"> **Baseline `{baseline}` has no registry rows yet**, so no delta column "
               f"is filled. Every figure below is absolute. Re-run this report once the "
               f"baseline's runs are appended to the registry.", ""]
    md += ["## Arms, GPU-minutes first", "",
           f"| year | run_tag | gpu_step_min | rows timed | honest rec | honest prec | "
           f"Δrec vs {baseline} | Δprec vs {baseline} | est_usd | caveat |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in out:
        md.append(f"| {r['year']} | {r['run_tag']} | {r['gpu_step_min'] or '—'} | "
                  f"{r['n_rows_timed']}/{r['n_rows']} | {r['honest_recall'] or '—'} | "
                  f"{r['honest_precision'] or '—'} | {r[f'd_recall_vs_{baseline}'] or '—'} | "
                  f"{r[f'd_precision_vs_{baseline}'] or '—'} | {r['est_usd'] or '—'} | "
                  f"{r['caveat']} |")
    n_blank = sum(1 for r in out if not r["est_usd"])
    md += ["", f"## Why {'every' if n_blank == len(out) else str(n_blank) + ' of '
                        + str(len(out))} `est_usd` cell"
           f"{'' if n_blank == len(out) or n_blank == 1 else 's'} is blank", "",
           "Dollars, when they exist, are apportioned to an arm from the LAUNCH that ran it "
           "(`--launches` → `Reports/gpu_launches.csv`), pro-rata by that arm's share of the "
           "launch's step-minutes. That apportionment would be INFERRED, never measured: a "
           "VM's uptime is not divisible by inspection. Today none of it runs, for these "
           "reasons:", ""]
    reasons = {}
    for r in out:
        for lid, why in blocked.get((r["year"], r["run_tag"]), []):
            reasons.setdefault(why, set()).add(lid)
        if not blocked.get((r["year"], r["run_tag"])) and not r["est_usd"]:
            reasons.setdefault("no launch status file mentions this (year, run_tag) — the "
                               "runs predate per-launch status files, or ran outside the "
                               "queue", set())
    for why, ids in reasons.items():
        md.append(f"* {why}" + (f" — {len(ids)} launch(es): {', '.join(sorted(ids))}"
                                if ids else ""))
    md += ["", "*Per-run dollar figures do not exist in this pipeline and never will — see "
           "the module docstring of `pipeline/cost_report.py`.*", ""]
    PER_ARM_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"{len(out)} arm(s) -> {PER_ARM_MD}\n                 -> {PER_ARM_CSV}\n")
    yw = max(4, *(len(r["year"]) for r in out))   # multi-year rows ("2022/2017/2015")
    hdr = (f"{'year':{yw}s} {'run_tag':22s} {'gpu_min':>8s} {'timed':>7s} {'rec':>7s} "
           f"{'prec':>7s} {'d_rec':>8s}")
    print(hdr)
    print("-" * len(hdr))
    for r in out:
        print(f"{r['year']:{yw}s} {r['run_tag']:22s} {(r['gpu_step_min'] or '-'):>8s} "
              f"{r['n_rows_timed'] + '/' + r['n_rows']:>7s} "
              f"{(r['honest_recall'] or '-'):>7s} {(r['honest_precision'] or '-'):>7s} "
              f"{(r[f'd_recall_vs_{baseline}'] or '-'):>8s}")
    print(f"\n{len(out) - n_timed} of {len(out)} arms have NO timing coverage — they are "
          f"UNKNOWN, not cheap.\nDollars blank: colab_rates.csv has no sourced GPU rate row.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--launches", action="store_true",
                    help="harvest per-launch rows -> Reports/gpu_launches.csv")
    ap.add_argument("--per-arm", action="store_true",
                    help="GPU-minutes + honest metrics per (year, run_tag)")
    ap.add_argument("--baseline", default=None,
                    help="run_tag to difference the other arms against (--per-arm)")
    a = ap.parse_args(clean_argv())

    if a.launches:
        return cmd_launches()
    if a.per_arm:
        if not a.baseline:
            sys.exit("--per-arm needs --baseline <run_tag>")
        return cmd_per_arm(a.baseline)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
