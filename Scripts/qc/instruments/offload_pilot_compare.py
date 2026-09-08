"""offload_pilot_compare.py — the offload pilot's verdict, read from a file.

WHAT THIS IS FOR. `experiments/offload_pilot_2017k.yaml` pre-registers a decision rule
(2026-09-07, before any launch) that re-runs ONE already-run acquisition — 2017k, tag
`of_2017k`, the whole pipeline on one A100 — as `spd_2017k` split across three Colab
runtimes: CPU-1 does labels+tile, an A100 does train+evaluate+inference, CPU-2 does
postproc. Every READ in that rule (R1 A100-bearing span, R2 checkpoint size, R3 postproc
elapsed, R4 per-step hardware attribution, R5 evaluate AP/AUROC) and both KILL criteria
(K1 a step fails on a CPU runtime, K2 the tile set changes) are numbers that live in five
different homes. This instrument joins them into ONE tracked CSV so the verdict is
written FROM A FILE and not from chat (CLAUDE.md 3.4b).

LONG FORMAT, BASELINE AND PILOT SIDE BY SIDE: one row per (metric, step), the two arms in
two columns, each with its own source column naming the file the number came from.

A BLANK PILOT CELL MEANS NOT-YET-MEASURED, NEVER ZERO. Every row is emitted whether or
not the pilot has run; that is the point of running this before the launch as well as
after. The one case a blank would be dishonest is a step that RAN AND FAILED — K1 — so
when a (tag, step) has queue rows but no OK row, the value stays blank and `note` carries
the latest state (`latest state FAIL`). Otherwise K1 would read exactly like "not run".

WHERE EACH NUMBER COMES FROM, and why that home and not another:

  step_minutes      the queue ledger's own `minutes` (state OK), merged across every
                    admissible train_queue_status*.csv via names.status_files. This is
                    WALL CLOCK as the orchestrator saw it — it includes the engine
                    process's start-up and the queue's own overhead.
  step_elapsed_log  the engine's `elapsed:` line from
                    phase4/logs/phase4_semantic_finetune_<step>_<year>_*.log, matched by
                    the `--run-tag` on its `command:` line and normalised to minutes
                    ("46.4min", "59.2s" and "1.02h" are all written by
                    pipeline_log.StepLogger._write). This is ENGINE time and is the
                    number the yaml's decision rule quotes. The two differ by ~1-3 min
                    per step and neither is wrong; they measure different brackets.
  machine           WHICH RUNTIME RAN THE STEP — the whole point of the pilot, and the
                    queue does NOT record it. `phase4_train_queue._gpu_line()` prints the
                    tier into the launch HEADER on stdout; the status CSV's columns are
                    job,year,tag,step,state,exit,minutes,detail,ts,host,session — `host`
                    is a container hostname and says nothing about a GPU. So the most
                    reliable field is the RUN MANIFEST's `gpu`, which cli.py fills from
                    nvidia-smi ON THE MACHINE THAT RAN THE STEP and leaves null on a CPU
                    runtime; its tracked view is phase4/qc/run_passport.csv. Two
                    fallbacks, because that view is harvested and will lag the pilot:
                    the per-session heartbeat JSON in the logs dir (`gpu.name`), then the
                    train log's own `Device: cuda  GPU: ...` line. Every row says in
                    `note` which of the three answered.
  a100_span_min     the money lever (R1): first queue ts to last VERIFY* ts over the rows
                    of the GPU-bearing session(s). The queue rewrites a step's row in
                    place RUNNING -> OK keeping the START timestamp
                    (registry_from_manifests.py), so a row's `ts` IS the step's start and
                    no RUNNING row survives a completed run.
  artifact sizes    stat on the lake. MB is decimal (bytes / 1e6), which is what the
                    yaml's 1113.2 / 2368.4 figures and the queue's VERIFY details are.
  tileset_id        phase4/qc/tileset_registry.csv. K2: a CPU-tiled set that does not
                    reproduce a36d6772e88b is a different experiment, not a cheaper one.
  eval_ap/auroc     the arm's OVERALL row of phase4/eval/semantic_eval_report.csv — AND
                    of semantic_eval_report_superseded.csv, which is not optional here:
                    step_evaluate's replace key is (year, channels) and NOT run_tag
                    (core.py, deliberately), so the moment spd_2017k evaluates 2017k/rgb
                    it DISPLACES the of_2017k rows into the superseded file. Reading only
                    the live report would blank the baseline at exactly the moment the
                    comparison became possible.
  hw_* fracs        phase4/qc/hw_step_attribution.csv (harvest_hw_attribution.py). That
                    file keys on (session, step, basis) and carries no run_tag, so the
                    sessions are taken from the queue rows of each tag. Absent file is
                    reported as absent, not as zero.

Run:  py -3.12 qc/instruments/offload_pilot_compare.py [--dry-run]
      py -3.12 qc/instruments/offload_pilot_compare.py --pilot-tag spd_2017k --out FILE
Output: phase4/qc/offload_pilot_2017k.csv   (schema: docs/SCHEMAS.md)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

COLS = ["metric", "step", "baseline", "pilot", "unit",
        "baseline_source", "pilot_source", "note"]

# The engine's steps, in pipeline order. The order rows are emitted in, too.
STEPS = ["labels", "tile", "train", "evaluate", "inference", "postproc"]

_ELAPSED = re.compile(r"^elapsed:\s+([0-9.]+)\s*(min|s|h)\s*$", re.M)
_STARTED = re.compile(r"^started:\s+(\S+)", re.M)
_COMMAND = re.compile(r"^command:\s+(.*)$", re.M)
_RUN_TAG = re.compile(r"--run-tag[=\s]+(\S+)")
# `Device: cuda  GPU: NVIDIA A100-SXM4-40GB` — only step_train prints it.
_DEVICE = re.compile(r"^\s*Device:\s*(\S+)", re.M)

_TS = "%Y-%m-%d %H:%M:%S"


# ── formatting ────────────────────────────────────────────────────────────────

def _f(v, nd):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return ""


def _mb(path):
    """Decimal MB, one decimal — the unit the queue's VERIFY details and the yaml use."""
    try:
        return f"{path.stat().st_size / 1e6:.1f}"
    except OSError:
        return ""


def _elapsed_min(text):
    """`elapsed:` as minutes. StepLogger writes s / min / h and all three appear."""
    m = _ELAPSED.search(text or "")
    if not m:
        return ""
    v, unit = float(m.group(1)), m.group(2)
    if unit == "s":
        v = v / 60.0
    elif unit == "h":
        v = v * 60.0
    return f"{v:.2f}"


# ── the homes ─────────────────────────────────────────────────────────────────

def _lake(explicit, attr):
    """A lake directory: the override, else lake.py — THE one home for lake paths."""
    if explicit:
        return Path(explicit)
    import lake

    return getattr(lake, attr)


def queue_rows(status_dir, year, tag):
    """Every ledger row for this (year, tag), from every admissible status file.

    Discovery goes through names.status_files, never a raw glob: a renamed-aside file
    escapes the underscore pattern but not the naive one (names.py records the 2026-08-29
    case where a "quarantined" fixture kept being ingested by five readers).
    """
    from phase4seg.names import status_files

    out = []
    for p in status_files(status_dir):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, r in enumerate(csv.DictReader(text.splitlines())):
            if str(r.get("year") or "") != str(year):
                continue
            if str(r.get("tag") or "") != str(tag):
                continue
            r["_file"], r["_idx"] = p.name, i
            out.append(r)
    out.sort(key=lambda r: (str(r.get("ts") or ""), r["_file"], r["_idx"]))
    return out


def _src(row):
    sess = str(row.get("session") or "").strip()
    return f"{row['_file']} session={sess}" if sess else str(row["_file"])


def _base_step(row):
    """`VERIFY:train` -> `train`; a bare `VERIFY` closes the JOB, not a step."""
    s = str(row.get("step") or "")
    if s.startswith("VERIFY:"):
        return s.split(":", 1)[1]
    return "" if s == "VERIFY" else s


def step_minutes(rows, step):
    """(value, source, note) — the LATEST OK row's `minutes`, or K1's blank-with-state."""
    hits = [r for r in rows if str(r.get("step") or "") == step]
    ok = [r for r in hits if str(r.get("state") or "") == "OK"
          and str(r.get("minutes") or "").strip()]
    if ok:
        return _f(ok[-1].get("minutes"), 1), _src(ok[-1]), ""
    if hits:
        return "", _src(hits[-1]), f"latest state {hits[-1].get('state') or '?'}"
    return "", "", ""


def step_logs(logs_dir, year, tag):
    """{step: (name, text)} — the LATEST log per step whose `--run-tag` equals `tag`.

    Equality, not `in`: `of_2017k` must not match a hypothetical `of_2017k_b`.
    """
    out = {}
    for step in STEPS:
        cands = []
        for p in sorted(Path(logs_dir).glob(
                f"phase4_semantic_finetune_{step}_{year}_*.log")):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            cmd = _COMMAND.search(text)
            m = _RUN_TAG.search(cmd.group(1)) if cmd else None
            if not m or m.group(1) != str(tag):
                continue
            st = _STARTED.search(text)
            cands.append((st.group(1) if st else "", p.name, text))
        if cands:
            cands.sort(key=lambda c: (c[0], c[1]))
            out[step] = (cands[-1][1], cands[-1][2])
    return out


def passport_gpu(passport_csv, tag):
    """{step: (gpu, run_id)} from the tracked run_passport view of the run manifests."""
    p = Path(passport_csv)
    if not p.exists():
        return {}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    best = {}
    for r in csv.DictReader(text.splitlines()):
        if str(r.get("run_tag") or "") != str(tag):
            continue
        step = str(r.get("step") or "")
        key = (str(r.get("ts_utc") or ""), str(r.get("run_id") or ""))
        if step not in best or key > best[step][0]:
            best[step] = (key, str(r.get("gpu") or "").strip(),
                          str(r.get("run_id") or ""))
    return {s: (v[1], v[2]) for s, v in best.items()}


def heartbeat_gpu(logs_dir):
    """{session: gpu_name} from phase4/logs/heartbeat_<session>.json.

    Per VM by construction, which is what makes it the fallback that populates BEFORE
    the tracked run_passport view has been re-harvested.
    """
    out = {}
    for p in sorted(Path(logs_dir).glob("heartbeat_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        sess = str(d.get("session") or p.stem[len("heartbeat_"):])
        gpu = d.get("gpu")
        name = (gpu or {}).get("name") if isinstance(gpu, dict) else gpu
        out[sess] = str(name or "").strip()
    return out


def _is_gpu(name):
    """A CUDA device by name. Blank / `none (CPU runtime...)` is a CPU runtime."""
    n = str(name or "").strip().lower()
    return bool(n) and not n.startswith("none") and not n.startswith("unknown")


def step_session(rows, step):
    hits = [r for r in rows
            if _base_step(r) == step and str(r.get("session") or "").strip()]
    return str(hits[-1].get("session")).strip() if hits else ""


def machine(step, rows, passport, hearts, logs):
    """(value, source, note) — GPU or CPU, and which field answered."""
    if step in passport:
        gpu, run_id = passport[step]
        return ("GPU" if _is_gpu(gpu) else "CPU",
                f"run_passport.csv {run_id}",
                f"basis run_passport.gpu={gpu or '(null)'}")
    sess = step_session(rows, step)
    if sess and sess in hearts:
        return ("GPU" if _is_gpu(hearts[sess]) else "CPU",
                f"heartbeat_{sess}.json",
                f"basis heartbeat gpu.name={hearts[sess] or '(blank)'}")
    if step in logs:
        m = _DEVICE.search(logs[step][1])
        if m:
            dev = m.group(1)
            return ("GPU" if dev.lower().startswith("cuda") else "CPU",
                    logs[step][0], f"basis step log Device: {dev}")
    return "", "", ""


def _dtparse(s):
    try:
        return dt.datetime.strptime(str(s).strip()[:19], _TS)
    except (TypeError, ValueError):
        return None


def spans(rows, machines):
    """(a100_span, a100_source, a100_note, total_span, total_source).

    The GPU slice is chosen at SESSION level when the rows name a session — that is what
    the pilot's split IS, one runtime per slice — and falls back to the per-step machine
    for legacy rows that carry no session.
    """
    stamped = [(r, _dtparse(r.get("ts"))) for r in rows]
    stamped = [(r, t) for r, t in stamped if t]
    if not stamped:
        return "", "", "", "", ""
    total = (max(t for _, t in stamped)
             - min(t for _, t in stamped)).total_seconds() / 60.0
    total_src = f"{len(stamped)} rows, {stamped[0][0]['_file']}"

    gpu_steps = {s for s in STEPS if machines.get(s) == "GPU"}
    if not gpu_steps:
        return "", "", "no step resolved to a GPU runtime", _f(total, 1), total_src
    sessions = sorted({str(r.get("session") or "").strip() for r, _ in stamped
                       if _base_step(r) in gpu_steps
                       and str(r.get("session") or "").strip()})
    if sessions:
        slice_ = [(r, t) for r, t in stamped
                  if str(r.get("session") or "").strip() in sessions]
        who = "session " + ",".join(sessions)
    else:
        slice_ = [(r, t) for r, t in stamped if _base_step(r) in gpu_steps]
        who = "steps " + ",".join(sorted(gpu_steps)) + " (rows carry no session)"
    if not slice_:
        return "", "", "no rows in the GPU slice", _f(total, 1), total_src
    start = min(t for _, t in slice_)
    verify = [t for r, t in slice_ if str(r.get("step") or "").startswith("VERIFY")]
    end = max(verify) if verify else max(t for _, t in slice_)
    note = (f"{who}; " + ("first ts to last VERIFY* ts" if verify
                          else "no VERIFY row — last ts used"))
    if any(str(r.get("state") or "") == "RUNNING" for r, _ in slice_):
        note += "; a row is still RUNNING — in progress"
    return (_f((end - start).total_seconds() / 60.0, 1),
            f"{len(slice_)} rows, {slice_[0][0]['_file']}", note,
            _f(total, 1), total_src)


def tileset(registry_csv, year, tag):
    """(tileset_id, n_tiles, source) from the tracked tile-set registry."""
    p = Path(registry_csv)
    if not p.exists():
        return "", "", ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", "", ""
    hits = [r for r in csv.DictReader(text.splitlines())
            if str(r.get("label") or "") == str(year)
            and str(r.get("run_tag") or "") == str(tag)]
    if not hits:
        return "", "", ""
    return (str(hits[-1].get("tileset_id") or ""),
            str(hits[-1].get("n_tiles") or ""), p.name)


def eval_row(eval_csv, year, tag):
    """(row, source) — the arm's OVERALL eval row, live report OR superseded archive.

    Both, because step_evaluate's replace key is (year, channels): the pilot evaluating
    2017k/rgb moves the baseline's rows into the archive.
    """
    live = Path(eval_csv)
    cands = []
    for p in (live, live.with_name("semantic_eval_report_superseded.csv")):
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for r in csv.DictReader(text.splitlines()):
            if (str(r.get("year") or "") == str(year)
                    and str(r.get("scope") or "") == "OVERALL"
                    and str(r.get("run_tag") or "").strip() == str(tag)):
                cands.append((str(r.get("written_utc") or ""), p.name, r))
    if not cands:
        return None, ""
    cands.sort(key=lambda c: (c[0], c[1]))
    return cands[-1][2], cands[-1][1]


def hw_rows(hw_csv, sessions):
    """{step: row} for the sessions this tag ran on. Marker basis wins over interval.

    None (not {}) when the file is absent, so the caller can say "absent" rather than
    publishing a blank that reads like a measured zero.

    NO SESSIONS MEANS NO ROWS, never every row. The first cut wrote
    `if sessions and session not in sessions`, so an arm that had not run — empty session
    set — matched EVERY session in the archive and the pilot column came back full of
    another campaign's numbers while the pilot had zero queue rows. A blank pilot cell is
    the whole contract of this file.

    ONLY ENGINE-STEP ROWS. Since the marker gained a `phase`, that file is one row per
    (session, step, basis, phase) — one step legitimately owns several rows, and
    harvest_hw_attribution.py::build_rows sorts them launching < open < verifying. This
    dict keys on the step alone and keeps the LAST row at equal basis rank, so without
    the filter below a one-sample VERIFY window would be published as the step's
    hardware profile. A row with no `phase` column at all reads as "" and is kept, so
    the pre-phase files still parse.
    """
    p = Path(hw_csv)
    if not p.exists():
        return None
    if not sessions:
        return {}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rank = {"marker": 2, "interval": 1}
    out = {}
    for r in csv.DictReader(text.splitlines()):
        if str(r.get("session") or "") not in sessions:
            continue
        if str(r.get("phase") or "") not in ("open", ""):
            continue
        key = str(r.get("step") or "")
        prev = out.get(key)
        if prev is None or (rank.get(str(r.get("basis")), 0)
                            >= rank.get(str(prev.get("basis")), 0)):
            out[key] = r
    return out


# ── the table ─────────────────────────────────────────────────────────────────

class Arm:
    """Everything one tag's side of the comparison needs, read once."""

    def __init__(self, year, tag, status_dir, logs_dir, models_dir, masks_dir,
                 registry_csv, eval_csv, passport_csv, hw_csv):
        self.tag = tag
        self.rows = queue_rows(status_dir, year, tag)
        self.logs = step_logs(logs_dir, year, tag)
        self.passport = passport_gpu(passport_csv, tag)
        self.hearts = heartbeat_gpu(logs_dir)
        self.machines, self.machine_src, self.machine_note = {}, {}, {}
        for s in STEPS:
            v, src, note = machine(s, self.rows, self.passport, self.hearts, self.logs)
            self.machines[s], self.machine_src[s], self.machine_note[s] = v, src, note
        (self.a100_span, self.a100_src, self.a100_note,
         self.total_span, self.total_src) = spans(self.rows, self.machines)
        self.sizes = {
            "sem_best_mb": Path(models_dir) / f"sem_best_{year}_{tag}.pt",
            "prob_raster_mb": Path(masks_dir) / f"edmonds_canopy_prob_{year}_{tag}.tif",
            "mask_mb": Path(masks_dir) / f"edmonds_canopy_mask_{year}_{tag}.tif",
            "gpkg_mb": Path(masks_dir) / f"edmonds_canopy_mask_{year}_{tag}.gpkg",
        }
        self.tileset_id, self.n_tiles, self.tileset_src = tileset(
            registry_csv, year, tag)
        self.eval, self.eval_src = eval_row(eval_csv, year, tag)
        self.sessions = sorted({str(r.get("session") or "").strip() for r in self.rows
                                if str(r.get("session") or "").strip()})
        self.hw = hw_rows(hw_csv, set(self.sessions))


def _both(base_note, pilot_note):
    return "; ".join(x for x in (f"baseline {base_note}" if base_note else "",
                                 f"pilot {pilot_note}" if pilot_note else "") if x)


def build_rows(base, pilot):
    """The long table. Every row is emitted for both arms, blank where unmeasured."""
    out = []

    def add(metric, step, b, p, unit, bsrc="", psrc="", note=""):
        out.append({"metric": metric, "step": step, "baseline": b, "pilot": p,
                    "unit": unit, "baseline_source": bsrc, "pilot_source": psrc,
                    "note": note})

    # 1 — the orchestrator's wall clock per step
    for s in STEPS:
        bv, bsrc, bnote = step_minutes(base.rows, s)
        pv, psrc, pnote = step_minutes(pilot.rows, s)
        add("step_minutes", s, bv, pv, "min", bsrc, psrc, _both(bnote, pnote))

    # 2 — the engine's own elapsed, which is what the decision rule quotes
    for s in STEPS:
        add("step_elapsed_log", s,
            _elapsed_min(base.logs[s][1]) if s in base.logs else "",
            _elapsed_min(pilot.logs[s][1]) if s in pilot.logs else "",
            "min",
            base.logs[s][0] if s in base.logs else "",
            pilot.logs[s][0] if s in pilot.logs else "",
            "engine time, `elapsed:` normalised to minutes")

    # 3 — which runtime ran it
    for s in STEPS:
        add("machine", s, base.machines[s], pilot.machines[s], "GPU|CPU",
            base.machine_src[s], pilot.machine_src[s],
            _both(base.machine_note[s], pilot.machine_note[s]))

    # 4 — R1, the money lever, and the wall clock the yaml says will get worse
    add("a100_span_min", "", base.a100_span, pilot.a100_span, "min",
        base.a100_src, pilot.a100_src, _both(base.a100_note, pilot.a100_note))
    add("total_span_min", "", base.total_span, pilot.total_span, "min",
        base.total_src, pilot.total_src,
        "all rows of the tag; the pilot's is EXPECTED to exceed the baseline's "
        "(three bootstraps in sequence) — see the yaml")

    # 5 — R2 and R3's artifacts
    for metric, step in (("sem_best_mb", "train"), ("prob_raster_mb", "inference"),
                         ("mask_mb", "postproc"), ("gpkg_mb", "postproc")):
        bp, pp = base.sizes[metric], pilot.sizes[metric]
        add(metric, step, _mb(bp), _mb(pp), "MB (bytes/1e6)", bp.name, pp.name,
            "stat on the lake; blank = the file is not there")

    # 6 — K2
    add("tileset_id", "tile", base.tileset_id, pilot.tileset_id, "id",
        base.tileset_src, pilot.tileset_src, "")
    add("n_tiles", "tile", base.n_tiles, pilot.n_tiles, "tiles",
        base.tileset_src, pilot.tileset_src, "")
    if base.tileset_id and pilot.tileset_id:
        note = ("MATCH — K2 satisfied: CPU tiling reproduced the GPU-tiled set"
                if base.tileset_id == pilot.tileset_id else
                "DIFF — K2 FIRES: the pilot tiled a different set, which is a different "
                "experiment and not a cheaper one")
    else:
        note = ("pilot not tiled yet — or tileset_registry.csv has not been "
                "re-harvested (qc/instruments/harvest_tilesets.py)")
    add("tileset_id_match", "tile", base.tileset_id, pilot.tileset_id, "id",
        base.tileset_src, pilot.tileset_src, note)

    # 7 — R5, reported and NOT gated
    for metric, col in (("eval_ap", "ap"), ("eval_auroc", "auroc")):
        add(metric, "evaluate",
            _f((base.eval or {}).get(col), 4) if base.eval else "",
            _f((pilot.eval or {}).get(col), 4) if pilot.eval else "",
            "fraction (4dp)", base.eval_src, pilot.eval_src,
            "OVERALL row, held-out test; R5 is REPORTED, not gated")

    # 8 — R4, the first marker-basis attribution
    absent = base.hw is None and pilot.hw is None
    for metric, col in (("hw_nothing_frac", "nothing_frac"),
                        ("hw_gpu_busy_frac", "gpu_busy_frac")):
        for s in STEPS:
            br = (base.hw or {}).get(s)
            pr = (pilot.hw or {}).get(s)
            add(metric, s,
                str(br.get(col) or "") if br else "",
                str(pr.get(col) or "") if pr else "",
                "fraction",
                f"{br.get('source_file')} basis={br.get('basis')}" if br else "",
                f"{pr.get('source_file')} basis={pr.get('basis')}" if pr else "",
                "hw_step_attribution.csv absent" if absent
                else "sessions taken from the queue rows (the file carries no run_tag)")
    return out


def _table(rows, base_tag, pilot_tag):
    wm = max(len(r["metric"]) for r in rows)
    ws = max(len(r["step"]) for r in rows)
    wb = max(len(base_tag), max(len(r["baseline"]) for r in rows))
    wp = max(len(pilot_tag), max(len(r["pilot"]) for r in rows))
    head = (f"  {'metric':<{wm}}  {'step':<{ws}}  {base_tag:>{wb}}  "
            f"{pilot_tag:>{wp}}  unit")
    lines = [head, "  " + "-" * (len(head) - 2)]
    for r in rows:
        lines.append(f"  {r['metric']:<{wm}}  {r['step']:<{ws}}  "
                     f"{r['baseline']:>{wb}}  {r['pilot']:>{wp}}  {r['unit']}")
    return "\n".join(lines)


def main(argv=None):
    from phase4seg.names import clean_argv

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", default="2017k")
    ap.add_argument("--baseline-tag", default="of_2017k")
    ap.add_argument("--pilot-tag", default="spd_2017k")
    ap.add_argument("--out", default=None)
    ap.add_argument("--status-dir", default=None, help="lake phase4/qc (the ledger)")
    ap.add_argument("--logs-dir", default=None, help="lake phase4/logs")
    ap.add_argument("--models-dir", default=None, help="lake phase4/models")
    ap.add_argument("--masks-dir", default=None, help="lake phase4/masks")
    ap.add_argument("--tileset-registry", default=None,
                    help="default phase4/qc/tileset_registry.csv (tracked)")
    ap.add_argument("--eval-report", default=None,
                    help="default lake phase4/eval/semantic_eval_report.csv")
    ap.add_argument("--run-passport", default=None,
                    help="default phase4/qc/run_passport.csv (tracked)")
    ap.add_argument("--hw-attribution", default=None,
                    help="default phase4/qc/hw_step_attribution.csv (tracked)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    status_dir = _lake(a.status_dir, "QC_DIR")
    logs_dir = _lake(a.logs_dir, "LOGS_DIR")
    models_dir = _lake(a.models_dir, "MODELS_DIR")
    masks_dir = _lake(a.masks_dir, "MASKS_DIR")
    eval_csv = (Path(a.eval_report) if a.eval_report
                else _lake(None, "EVAL_DIR") / "semantic_eval_report.csv")
    registry = Path(a.tileset_registry or (QC / "tileset_registry.csv"))
    passport = Path(a.run_passport or (QC / "run_passport.csv"))
    hw = Path(a.hw_attribution or (QC / "hw_step_attribution.csv"))
    out = Path(a.out) if a.out else (QC / f"offload_pilot_{a.year}.csv")

    if not Path(status_dir).exists():
        print(f"FATAL: status dir not found: {status_dir}\n"
              f"       this instrument reads the lake — mount it, or pass --status-dir")
        return 2

    def arm(tag):
        return Arm(a.year, tag, status_dir, logs_dir, models_dir, masks_dir,
                   registry, eval_csv, passport, hw)

    base, pilot = arm(a.baseline_tag), arm(a.pilot_tag)
    rows = build_rows(base, pilot)

    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not a.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(buf.getvalue(), encoding="utf-8", newline="")

    shown = out.relative_to(REPO) if out.is_relative_to(REPO) else out
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} rows → {shown}")
    print(f"  {a.year}: baseline {a.baseline_tag} ({len(base.rows)} queue rows, "
          f"sessions {','.join(base.sessions) or '-'}) vs pilot {a.pilot_tag} "
          f"({len(pilot.rows)} queue rows, sessions {','.join(pilot.sessions) or '-'})")
    if not pilot.rows:
        print("  the pilot has not run: every pilot cell is blank = NOT MEASURED, not 0")
    if not hw.exists():
        print("  hw_step_attribution.csv absent — R4 rows are blank by design")
    print(_table(rows, a.baseline_tag, a.pilot_tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
