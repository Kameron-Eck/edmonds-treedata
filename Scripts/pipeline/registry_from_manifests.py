r"""registry_from_manifests.py — generate run_registry.csv rows from run manifests (overhaul P6).

Rule 9c says every Colab run gets a `run_registry.csv` row. Writing them by hand is
where the contract leaks: the interesting runs are the ones that failed at 03:00 and
never got typed up. Every run already stamps a manifest
(`phase4/runs/<run_id>/manifest.json`: engine version, git sha + branch, GPU, argv,
seed, years), so this builds the rows from that, joining in what was measured:

  * held-out metrics  <- phase4/eval/semantic_eval_report.csv   (scope=OVERALL row for
                         the year; carries `channels`, which is the rgb+chm gate)
  * honest metrics    <- phase4/qc/qc_indep_report.csv          (live=1 rows only —
                         CLAUDE.md rule 5: never headline a circular number)
  * outcome + timing  <- phase4/qc/train_queue_status*.csv      (merged across launches:
                         state, minutes, and the VERIFY detail for the step)
  * artifacts         <- phase4/models, phase4/masks            (path recorded only if
                         the file actually exists on the data plane)

APPEND-ONLY and idempotent: a run_id already in the registry is never rewritten, so the
hand-written history (and any note a human added) is safe. Runs that FAILED get a row
too — a registry that only records successes cannot explain a GPU bill.

Usage (local Windows, from the repo):
    py -3.12 pipeline/registry_from_manifests.py --dry-run     # show what would be added
    py -3.12 pipeline/registry_from_manifests.py               # append the new rows
    py -3.12 pipeline/registry_from_manifests.py --since 20260822
"""
import argparse
import csv
import datetime as _dt
import json
import sys
from pathlib import Path

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE          # data plane
REPO = Path(__file__).resolve().parents[2]                           # code plane
REGISTRY = REPO / "Scripts" / "run_registry.csv"

RUNS = BASE / "phase4" / "runs"
EVAL_REPORT = BASE / "phase4" / "eval" / "semantic_eval_report.csv"
INDEP_REPORT = BASE / "phase4" / "qc" / "qc_indep_report.csv"
STATUS_GLOB = "train_queue_status*.csv"
QC_DIR = BASE / "phase4" / "qc"
MODELS, MASKS = BASE / "phase4" / "models", BASE / "phase4" / "masks"

COLUMNS = ["run_id", "date", "year", "step", "script_version", "args",
           "headline_metrics", "model_path", "mask_path", "notes"]


def _rows(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _fmt(x, nd=4):
    try:
        return f"{float(x):.{nd}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(x)


def held_out_metrics(year, tag):
    """The OVERALL held-out row for this year — the model's own test number."""
    best = None
    for r in _rows(EVAL_REPORT):
        if r.get("year") == year and r.get("scope") == "OVERALL":
            best = r                                  # last wins: the newest re-run
    if not best:
        return ""
    bits = [f"held-out IoU {_fmt(best.get('iou'))}"]
    for label, key in (("AUROC", "auroc"), ("AP", "ap"),
                       ("prec", "precision"), ("rec", "recall")):
        if best.get(key):
            bits.append(f"{label} {_fmt(best[key])}")
    ch = best.get("channels")
    return f"{', '.join(bits)} [{ch}]" if ch else ", ".join(bits)


def honest_metrics(year, tag="", run_ts=None):
    """Independent (live=1) recall/precision — CLAUDE.md rule 5's primary number.

    MATCHED ON THE RASTER, not on time. qc_indep_report keeps every past scoring of a
    year, so the newest row is not necessarily this run's: tonight's 2017 citywide run
    would otherwise have inherited August's off-recipe `_xsensor_train` number. Timestamps
    cannot arbitrate it either — the queue writes UTC on the VM while qc_indep runs
    locally and writes LOCAL time (measured 2026-08-22: manifest 22:02:31Z vs report
    17:29:20 local for the same run, a 7 h skew that made the scoring look older than the
    run it came from). The `prob` column names the raster that was scored, and that IS the
    artefact this run produced — an exact, timezone-immune join.

    A run whose raster has not been scored yet gets no honest number; the row is then
    skipped until it has one (append-only cannot correct it later).
    """
    want = f"edmonds_canopy_prob_{year}{('_' + tag) if tag else ''}.tif"
    live = [r for r in _rows(INDEP_REPORT)
            if r.get("year") == year and str(r.get("live", "")).strip() == "1"]
    exact = [r for r in live
             if str(r.get("prob", "")).replace("\\", "/").split("/")[-1] == want]
    if exact:
        live = exact
    elif run_ts is not None and any(r.get("prob") for r in live):
        return ""                       # this run's raster has no live scoring yet
    if not live:
        return ""
    # the report marks ONE canopy definition primary (forest_wetland); quoting the last
    # row instead would headline forest_wetland_scrub, a different definition
    primary = [r for r in live if str(r.get("primary", "")).strip() == "1"]
    r = (primary or live)[-1]
    return (f"honest rec {_fmt(r.get('recall'))} prec {_fmt(r.get('precision'))} "
            f"vs {r.get('ref', '?')} @{_fmt(r.get('thresh'))} ({r.get('canopy_def', '?')}"
            f"{'' if primary else ', NON-PRIMARY def'})")


def _parse_status_ts(v):
    try:
        return _dt.datetime.strptime(str(v).strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_manifest_ts(ts):
    try:
        return _dt.datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def status_for(year, tag, step, run_ts, window_min=10):
    """Outcome + timing for THIS attempt.

    A year/step can appear in many per-launch status files (2024 inference has five
    attempts tonight). Taking the last match would staple the newest launch's outcome
    onto an old manifest, so pair by time: the status row is written when the step
    starts and the manifest is stamped at the same moment, so the correct row is the
    nearest one within a few minutes. Later rows for the same attempt (the terminal
    state, or an audit row closing a stale RUNNING) are then folded in.
    """
    cands, verifies = [], []
    for f in sorted(QC_DIR.glob(STATUS_GLOB)):
        for r in _rows(f):
            # Join on the status CSV's `year` column, NOT `job`: queue job ids may
            # carry suffixes (queue_sectors_base2020 uses id "2006s_b20" for year
            # "2006s"), and a job-keyed join returned zero rows for the whole sector
            # campaign. Seeded placeholder rows (write_seed / VM-side seeds) must
            # never supply an attempt's state or minutes.
            if r.get("year") != year or r.get("tag") not in (tag, "", None):
                continue
            if (r.get("detail") or "").startswith("SEEDED"):
                continue
            if r.get("step") == step:
                cands.append(r)
            elif r.get("step") == f"VERIFY:{step}":
                verifies.append(r)
    if run_ts is None or not cands:
        return (cands[-1] if cands else None), (verifies[-1] if verifies else None)

    def _near(rows):
        best, best_d = None, None
        for r in rows:
            t = _parse_status_ts(r.get("ts"))
            if t is None:
                continue
            d = abs((t - run_ts).total_seconds())
            if best_d is None or d < best_d:
                best, best_d = r, d
        return (best, best_d)

    start, d = _near(cands)
    if start is None or d > window_min * 60:
        return None, None
    # The attempt's final word, BOUNDED to this attempt: rows from t0 until the next
    # attempt of the same step begins. Without that bound, the 01:03 tile run inherited
    # the 16:18 re-run's "OK" — five 2024 inference attempts share one (job, step) key.
    t0 = _parse_status_ts(start.get("ts"))
    ordered = sorted((r for r in cands if _parse_status_ts(r.get("ts"))),
                     key=lambda r: _parse_status_ts(r["ts"]))
    t_end = None
    for r in ordered:
        t = _parse_status_ts(r["ts"])
        if t > t0 and r.get("state") == "RUNNING":
            t_end = t                                   # the next attempt starts here
            break
    final = start
    for r in ordered:
        t = _parse_status_ts(r["ts"])
        if t < t0 or (t_end is not None and t >= t_end):
            continue
        if r.get("state") != "RUNNING":
            final = r                                   # ordered: the last one wins
    vmatch = None
    for r in sorted((r for r in verifies if _parse_status_ts(r.get("ts"))),
                    key=lambda r: _parse_status_ts(r["ts"])):
        t = _parse_status_ts(r["ts"])
        if t >= t0 and (t_end is None or t < t_end):
            vmatch = r
    return final, vmatch


def build_row(mf):
    m = json.loads(mf.read_text(encoding="utf-8"))
    years = list((m.get("years") or {}).keys())
    year = years[0] if len(years) == 1 else "+".join(years) or "?"
    tag, step = m.get("run_tag", ""), m.get("step", "?")
    ts = m.get("ts_utc", "")
    date = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else ""

    ver = m.get("engine_version", "?")
    sha, branch = (m.get("git_sha") or "")[:8], m.get("git_branch") or "?"
    script_version = f"{ver} ({sha} on {branch}{'; DIRTY' if m.get('git_dirty') else ''})"

    metrics = [x for x in (held_out_metrics(year, tag) if step in ("train", "evaluate") else "",
                           honest_metrics(year, tag, _parse_manifest_ts(ts))
                           if step == "inference" else "") if x]
    run_ts = _parse_manifest_ts(ts)
    row_status, row_verify = status_for(year, tag, step, run_ts)

    note_bits = []
    if row_status:
        st = row_status.get("state", "?")
        note_bits.append(f"queue {st}" + (f" in {row_status['minutes']} min"
                                          if row_status.get("minutes") else ""))
        if st != "OK" and row_status.get("detail"):
            note_bits.append(str(row_status["detail"])[:180])
    if row_verify:
        note_bits.append(f"VERIFY:{step} {row_verify.get('state', '?')}"
                         + (f" ({row_verify['detail']})" if row_verify.get("detail") else ""))
    gpu = m.get("gpu")
    if gpu:
        note_bits.append(f"{gpu}" + (f" {m['gpu_mem_gb']:g} GB" if m.get("gpu_mem_gb") else ""))
    if m.get("seed") is not None:
        note_bits.append(f"seed {m['seed']}")

    sfx = f"_{tag}" if tag else ""
    model = MODELS / f"sem_best_{year}{sfx}.pt"
    mask = MASKS / f"edmonds_canopy_prob_{year}{sfx}.tif"
    return {
        "_state": (row_status or {}).get("state", ""),
        "_unscored": step == "inference" and not metrics
        and (row_status or {}).get("state") == "OK",
        "run_id": m.get("run_id", mf.parent.name),
        "date": date,
        "year": year,
        "step": step,
        "script_version": script_version,
        "args": " ".join(m.get("argv") or []),
        "headline_metrics": "; ".join(metrics),
        "model_path": f"phase4/models/{model.name}" if model.exists() else "",
        "mask_path": f"phase4/masks/{mask.name}" if mask.exists() else "",
        "notes": "; ".join(note_bits),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    ap.add_argument("--since", default=None, help="only manifests from this YYYYMMDD onwards")
    ap.add_argument("--registry", default=str(REGISTRY))
    ap.add_argument("--include-running", action="store_true",
                    help="also write rows for attempts still marked RUNNING (default: skip "
                         "them — append-only means a RUNNING row could never be corrected)")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    if not RUNS.exists():
        sys.exit(f"no run manifests on the data plane: {RUNS}")
    reg_path = Path(a.registry)
    existing = _rows(reg_path)
    have = {r.get("run_id") for r in existing}
    if existing and list(existing[0].keys()) != COLUMNS:
        sys.exit(f"registry columns changed: {list(existing[0].keys())} != {COLUMNS}")

    manifests = sorted(RUNS.glob("*/manifest.json"), key=lambda p: p.parent.name)
    if a.since:
        manifests = [p for p in manifests if p.parent.name[:8] >= a.since]

    new, running, unscored = [], [], []
    for mf in manifests:
        try:
            row = build_row(mf)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"  SKIP {mf.parent.name}: unreadable manifest ({e})")
            continue
        if row["run_id"] in have:
            continue
        if row.pop("_state", "") == "RUNNING" and not a.include_running:
            running.append(row["run_id"])
            continue
        if row.pop("_unscored", False) and not a.include_running:
            unscored.append(row["run_id"])       # append-only: wait for the honest number
            continue
        row.pop("_state", None); row.pop("_unscored", None)
        new.append(row)
        have.add(row["run_id"])

    print(f"{len(manifests)} manifest(s) considered, {len(existing)} registry row(s) already "
          f"present, {len(new)} new"
          + (f", {len(running)} still RUNNING (skipped; re-run when they finish)" if running else "")
          + (f", {len(unscored)} finished but not yet scored (skipped; re-run after "
             f"qc_indep)" if unscored else "")
          + ".")
    for r in new:
        print(f"  + {r['run_id']:52s} {r['step']:10s} {r['headline_metrics'] or r['notes'][:70]}")
    if not new or a.dry_run:
        print("(dry run — nothing written)" if a.dry_run else "registry already current.")
        return 0

    write_header = not reg_path.exists() or not existing
    with open(reg_path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()
        for r in new:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    print(f"appended {len(new)} row(s) to {reg_path}")
    print("stage it explicitly (CLAUDE.md rule 1b):  git add -- Scripts/run_registry.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
