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

INVARIANT: rows are append-only; the HEADER was migrated once, on 2026-08-25, by
`--migrate-columns` (E04 cost accounting), which added `gpu_name` and `step_minutes`
after `step` and padded the 50 pre-existing rows with empty cells. That mode refuses to
run a second time, and normal runs still hard-exit on any other column drift.

E04 cutover, 2026-08-25 — two facts moved out of free-text `notes` into typed columns:

  * `gpu_name`    <- manifest.json["gpu"], VERBATIM (e.g. "NVIDIA A100-SXM4-40GB").
                     EMPTY when the manifest recorded None, and an empty cell is
                     AMBIGUOUS: it means either the step ran on a CPU runtime or the
                     nvidia-smi/torch probe failed. It never means "free" — see
                     pipeline/colab_rates.csv, which blanks (never zeroes) the cost of
                     an unknown GPU.
  * `step_minutes` <- the joined status row's `minutes`: WALL-CLOCK OF THE ENGINE
                     SUBPROCESS ONLY. It EXCLUDES VM setup, the repo clone/pip
                     bootstrap, ortho staging, VERIFY reads, and idle time between
                     jobs — Colab bills VM uptime, not subprocess seconds, so this
                     column is a LOWER BOUND on billable time and must never be
                     multiplied by a rate to produce a per-run dollar figure. Empty
                     when the VM died mid-step (no terminal row was ever written).

Rows written BEFORE the cutover carry those two facts as prose inside `notes`
("… ; queue OK in 73.9 min; NVIDIA A100-SXM4-40GB 40 GB"). That is history, not a
contradiction: read the typed columns for new rows, the prose for old ones. Rows
written AFTER it keep the outcome word in `notes` (`queue OK` / `queue FAIL …`) —
state has no typed column — but no longer the minutes or the GPU name.

Usage (local Windows, from the repo):
    py -3.12 pipeline/registry_from_manifests.py --dry-run     # show what would be added
    py -3.12 pipeline/registry_from_manifests.py               # append the new rows
    py -3.12 pipeline/registry_from_manifests.py --since 20260822
    py -3.12 pipeline/registry_from_manifests.py --migrate-columns   # ONCE, 2026-08-25
"""
import argparse
import csv
import datetime as _dt
import json
import sys
from pathlib import Path

from phase4seg.names import status_files

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE          # data plane
REPO = Path(__file__).resolve().parents[2]                           # code plane
REGISTRY = REPO / "Scripts" / "run_registry.csv"

RUNS = BASE / "phase4" / "runs"
EVAL_REPORT = BASE / "phase4" / "eval" / "semantic_eval_report.csv"
INDEP_REPORT = BASE / "phase4" / "qc" / "qc_indep_report.csv"
# discovery moved to phase4seg/names.status_files (2026-08-30)
STATUS_GLOB = "train_queue_status*.csv"   # kept: some callers log it
QC_DIR = BASE / "phase4" / "qc"
MODELS, MASKS = BASE / "phase4" / "models", BASE / "phase4" / "masks"

# gpu_name    : manifest.json["gpu"] verbatim; EMPTY = ambiguous (CPU runtime OR a
#               failed probe), never "free" — cost lookups blank it, never zero it.
# step_minutes: wall-clock of the ENGINE SUBPROCESS only. Excludes VM setup, ortho
#               staging, VERIFY reads and idle between jobs; empty when the VM died
#               mid-step. A lower bound on billable time — Colab bills VM uptime.
COLUMNS = ["run_id", "date", "year", "step", "gpu_name", "step_minutes",
           "script_version", "args", "headline_metrics", "model_path", "mask_path",
           "notes"]

# The pre-2026-08-25 header. Kept ONLY so a normal run can tell "needs the one-time
# migration" apart from "someone changed the schema again" (which stays a hard exit).
LEGACY_COLUMNS = ["run_id", "date", "year", "step", "script_version", "args",
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


# step_evaluate stamps run_tag / run_id / written_utc on every row it writes (D6,
# 2026-08-29). That landed AFTER the last evaluate step ran, so the live report still
# carries none of them — the columns appear on the first evaluate that runs from here.
# held_out_metrics handles both eras, so nothing has to be changed when they arrive.
_EVAL_RUN_ID_COLS = ("run_tag", "run_id")
EVAL_SUPERSEDED = EVAL_REPORT.with_name("semantic_eval_report_superseded.csv")


def _eval_bits(r):
    bits = [f"IoU {_fmt(r.get('iou'))}"]
    for label, key in (("AUROC", "auroc"), ("AP", "ap"),
                       ("prec", "precision"), ("rec", "recall")):
        if r.get(key):
            bits.append(f"{label} {_fmt(r[key])}")
    ch = r.get("channels")
    return f"{', '.join(bits)} [{ch}]" if ch else ", ".join(bits)


def held_out_metrics(year, tag=""):
    """This arm's OVERALL eval row when the report can name it; the year's otherwise.

    THE DEFECT THIS REPLACES. It took `tag` and IGNORED it — filtered on year and
    scope==OVERALL and took the last match. Regenerating the registry on 2026-08-30
    printed the consequence: three different 2009 arms (nodecW, rgb3_ep60_s1234,
    rgb3_nodeb_twin), different seeds and GPUs, all carrying "IoU 0.6959, AUROC 0.9082",
    and two of them named `rgb3` while the bracket read `[rgb+chm]`.

    It is worse than a labelling slip. step_train does NOT write eval rows, and the
    registry holds 46 train steps against 9 evaluate steps — so most of those train rows
    were showing an evaluation that had never been run for that arm at all, borrowed
    from whichever arm last evaluated the year.

    TWO ERAS, AND THE FUNCTION SPANS BOTH so nothing needs changing when the second
    arrives. Pre-D6 rows carry no run identity and cannot be attributed; the number is
    kept (most years have one arm, and for those it IS that run's) but stamped as a
    year-level fact. Post-D6 rows carry run_tag, so the join is exact — and an arm with
    no eval row of its own then gets NOTHING rather than a borrowed number, which is the
    whole point.

    Superseded rows count as the arm's own. Two arms on one year and channel set is the
    normal shape of a paired experiment, and step_evaluate archives the displaced rows
    to semantic_eval_report_superseded.csv precisely so they are not lost. An arm whose
    row was replaced still measured what it measured.

    honest_metrics below is the pattern this now follows: join on something that names
    the run, and decline to report when the join finds nothing.
    """
    rows = [r for r in (_rows(EVAL_REPORT) + _rows(EVAL_SUPERSEDED))
            if r.get("year") == year and r.get("scope") == "OVERALL"]
    if not rows:
        return ""

    identified = [r for r in rows if str(r.get("run_tag") or "").strip()]
    if identified:
        want = str(tag or "").strip()
        mine = [r for r in identified if str(r["run_tag"]).strip() == want]
        if not mine:
            return ""            # no eval row belongs to this arm — do not borrow one
        return "held-out " + _eval_bits(mine[-1])

    # Pre-D6: the report cannot say who wrote a row, so neither can this.
    return ("year-eval " + _eval_bits(rows[-1])
            + " (newest OVERALL row for the YEAR; these rows predate run_tag stamping, "
              "so none can be attributed to a run)")


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
    for f in status_files(QC_DIR):
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
    #
    # THE BOUND USED TO REQUIRE state == "RUNNING" ON THE NEXT ROW, and that hole let the
    # bug back in (2026-08-31). A launch REWRITES its own status file and updates a step's
    # row IN PLACE, RUNNING -> OK, keeping the step's START timestamp — so once the next
    # attempt finishes, its RUNNING marker no longer exists anywhere and the bound never
    # closes. Measured: pilotcoarse died mid-evaluate leaving only a RUNNING row; the
    # pilotcoarse3 rerun completed in 26.2 min on an A100; and the DEAD L4 attempt's
    # manifest absorbed it, so the registry claimed an L4 had finished a step it never
    # started. A false outcome in an append-only ledger.
    #
    # Any next row of the same step opens the next attempt, whatever its state — safe
    # because a terminal row carries its attempt's START ts, not its end ts (medium's
    # `train OK` sits at 01:12:54 and evaluate begins 26.8 min later at 01:39:51), so an
    # attempt's own terminal row can never be mistaken for the next attempt's start.
    t0 = _parse_status_ts(start.get("ts"))
    ordered = sorted((r for r in cands if _parse_status_ts(r.get("ts"))),
                     key=lambda r: _parse_status_ts(r["ts"]))
    t_end = None
    for r in ordered:
        t = _parse_status_ts(r["ts"])
        if t > t0:
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

    # E04 cutover 2026-08-25: the minutes and the GPU name are TYPED COLUMNS now and are
    # no longer restated here. The outcome WORD stays — `state` has no typed column, and
    # a registry row that cannot say whether the run succeeded is worthless. Older rows
    # still carry "queue OK in N min; <gpu> N GB" as prose; that is history.
    note_bits = []
    if row_status:
        st = row_status.get("state", "?")
        note_bits.append(f"queue {st}")
        if st != "OK" and row_status.get("detail"):
            note_bits.append(str(row_status["detail"])[:180])
    if row_verify:
        note_bits.append(f"VERIFY:{step} {row_verify.get('state', '?')}"
                         + (f" ({row_verify['detail']})" if row_verify.get("detail") else ""))
    if m.get("seed") is not None:
        note_bits.append(f"seed {m['seed']}")

    # Verbatim, and empty when the manifest recorded None. A None is AMBIGUOUS — a CPU
    # runtime and a failed nvidia-smi/torch probe are indistinguishable here — so it is
    # left blank rather than guessed at, and every cost path treats blank as UNKNOWN
    # (blank cost), never as zero.
    gpu_name = m.get("gpu") or ""
    # Wall-clock of the engine subprocess only (see the module docstring). Empty-tolerant:
    # a step whose VM died before a terminal row was written has no minutes at all.
    step_minutes = str((row_status or {}).get("minutes", "") or "")

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
        "gpu_name": gpu_name,
        "step_minutes": step_minutes,
        "script_version": script_version,
        "args": " ".join(m.get("argv") or []),
        "headline_metrics": "; ".join(metrics),
        "model_path": f"phase4/models/{model.name}" if model.exists() else "",
        "mask_path": f"phase4/masks/{mask.name}" if mask.exists() else "",
        "notes": "; ".join(note_bits),
    }


def migrate_columns(reg_path):
    """The ONE-TIME header migration of 2026-08-25 (E04): rewrite run_registry.csv with
    `gpu_name` and `step_minutes` inserted after `step`, every pre-existing row padded
    with empty cells.

    This is the ONLY code path that rewrites an existing registry row, and it refuses to
    run twice: if the header already carries the new columns it reports that and exits 0.
    Rows themselves are never edited — a padded cell stays empty forever, because those
    runs' GPU and minutes live in their `notes` prose and re-deriving them would be a
    guess. Written to a temp file and os.replace()d so a crash cannot leave a half file.
    """
    if not reg_path.exists():
        print(f"no registry at {reg_path} — nothing to migrate (a fresh run writes the "
              f"new header itself).")
        return 0
    with open(reg_path, encoding="utf-8", newline="") as f:
        rdr = csv.reader(f)
        try:
            header = next(rdr)
        except StopIteration:
            print(f"{reg_path} is empty — nothing to migrate.")
            return 0
        body = [r for r in rdr]

    if header == COLUMNS:
        print(f"already migrated: {reg_path.name} carries the 2026-08-25 header "
              f"({len(body)} row(s)). Nothing to do.")
        return 0
    if header != LEGACY_COLUMNS:
        sys.exit(f"refusing to migrate: header is neither the pre-2026-08-25 layout nor "
                 f"the current one.\n  found : {header}\n  legacy: {LEGACY_COLUMNS}")

    ins = COLUMNS.index("gpu_name")                 # 4 — right after `step`
    n_pad = len(COLUMNS) - len(LEGACY_COLUMNS)      # 2
    out = []
    for r in body:
        r = list(r) + [""] * (len(LEGACY_COLUMNS) - len(r))     # tolerate short rows
        out.append(r[:ins] + [""] * n_pad + r[ins:])

    tmp = reg_path.with_suffix(".csv.migrating")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(out)
    tmp.replace(reg_path)

    check = _rows(reg_path)
    if not check or list(check[0].keys()) != COLUMNS or len(check) != len(body):
        sys.exit(f"MIGRATION VERIFY FAILED for {reg_path} — restore it with "
                 f"`git checkout -- Scripts/run_registry.csv` and investigate.")
    ids_before = [r[0] for r in body]
    ids_after = [r.get("run_id", "") for r in check]
    if ids_before != ids_after:
        sys.exit(f"MIGRATION VERIFY FAILED: run_id order/content changed. Restore with "
                 f"`git checkout -- Scripts/run_registry.csv`.")
    print(f"migrated {reg_path} to the 2026-08-25 header "
          f"(+gpu_name, +step_minutes after `step`); {len(out)} existing row(s) padded "
          f"with empty cells, run_ids unchanged.")
    print("stage it explicitly (CLAUDE.md rule 1b):  git add -- Scripts/run_registry.csv")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    ap.add_argument("--since", default=None, help="only manifests from this YYYYMMDD onwards")
    ap.add_argument("--registry", default=str(REGISTRY))
    ap.add_argument("--include-running", action="store_true",
                    help="also write rows for attempts still marked RUNNING (default: skip "
                         "them — append-only means a RUNNING row could never be corrected)")
    ap.add_argument("--migrate-columns", action="store_true",
                    help="ONE-TIME (2026-08-25): rewrite the registry with gpu_name and "
                         "step_minutes added after `step`, padding existing rows. Refuses "
                         "to run twice. The only path that rewrites existing rows.")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    if a.migrate_columns:
        return migrate_columns(Path(a.registry))

    if not RUNS.exists():
        sys.exit(f"no run manifests on the data plane: {RUNS}")
    reg_path = Path(a.registry)
    existing = _rows(reg_path)
    have = {r.get("run_id") for r in existing}
    if existing and list(existing[0].keys()) != COLUMNS:
        found = list(existing[0].keys())
        if found == LEGACY_COLUMNS:
            sys.exit("registry still has the pre-2026-08-25 header. Run the one-time "
                     "migration first:\n"
                     "  py -3.12 pipeline/registry_from_manifests.py --migrate-columns")
        sys.exit(f"registry columns changed: {found} != {COLUMNS}")

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
        # gpu_name/step_minutes are printed explicitly: they are the whole point of the
        # E04 columns, and a dry run that hid them could not be used to check them.
        gpu = r["gpu_name"] or "(none/unknown)"
        mins = f"{r['step_minutes']} min" if r["step_minutes"] else "(no timing)"
        print(f"  + {r['run_id']:52s} {r['step']:10s} {gpu:24s} {mins:>12s}  "
              f"{r['headline_metrics'] or r['notes'][:60]}")
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
