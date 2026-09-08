"""harvest_timing_events.py — every timed I/O operation the engine ever printed, joined
to the size of the file it moved.

THE ENGINE HAS BEEN TIMING ITSELF SINCE PHASE 1 AND NOBODY COULD READ IT.
`common.py::tock` prints one line per timed operation — `  ⏱ stage 2017_king_rgb.tif:
309.4s` — and 2,823 of them sit in 362 step logs. As text they answer "how long did that
take" and nothing else, because the number that turns a duration into a RATE — the size
of the file being moved — is not printed beside the duration. For `copy` events the log
DOES carry it one line down (`common.py::_copy_to_drive` prints
`✓ verified|staged write: X (N MB…)`; measured 2026-09-07, 2,228 of 2,233 copy events
have it, to the nearest whole MB). For `stage` events nothing in the log carries it, and `stage` is the half the
storage argument rests on — which is why the size join reads the lake. So the project's
storage arguments have been made on an unmeasured constant: `Reports/
PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md` §1 states "Drive gives 40 MB/s on one big
sequential file", and §2's 3.6 h checkpoint saving, its 2.32 h re-staging saving and the
16.6% ceiling §3 puts on any storage purchase are all priced against it. This script
makes that constant a measured column instead of a quoted one (CLAUDE.md 3.4b).

WHAT A ROW IS. One `⏱ <label>: <N>s` line. `run_id`, `year`, `run_tag` and `step` come
from the log's own header block, so every event carries the arm that produced it.

THE SIZE JOIN, and its three failure modes, all published as a BLANK `bytes` cell:

    hit         the label is `stage <name>` or `copy <name>` and exactly one distinct
                size answers to `<name>` anywhere in the five lake roots below.
    ambiguous   two or more DIFFERENT sizes answer to that basename — `phase4/masks/`
                versus `phase4/masks/_prerefactor_backup/`, or `eval/viz_2000/` versus
                `eval/viz_2016/`. Which one this row moved is not recoverable from the
                log, so the cell stays blank rather than picking a side. Same size in
                several directories is NOT ambiguous: the answer is the same either way.
    miss        no such basename. The bulk of these are `stage tiles 2009` — a label
                whose tail is a directory description, not a filename — plus the
                corrected-label overlays (`add_chm2016.tif`, `add_nodec_2009.tif`),
                which live in `phase4/labels_corrected/`. That directory is DELIBERATELY
                outside the scan: the contract names five roots and widening it here
                would change what every historical row means. Measured 2026-09-07:
                281/375 `stage` and 2,178/2,233 `copy` labels resolve.

THE SCAN IS ONE WALK, CACHED. `build_size_index` walks the five roots exactly once per
process and returns a basename→size map; the per-row lookup is a dict hit. A per-row walk
of `Full_Image/Pipeline Imagery` over the FUSE/Drive mount would cost more than the runs
it is measuring. An unmounted lake is not an error: every root that does not exist is
skipped, `bytes` is blank for every row, and the timings — which come from the LOGS —
are published anyway. A root that exists but walks to zero files is retried through
`lake.py::read_retry`, because the G: mirror returns empty listings for directories that
are plainly populated seconds later. `read_retry_logs` gives the LOG listing the same
guard, and `main` refuses to write zero rows over a populated output — between them, a
blink cannot publish a header-only file over the archive and exit 0.

WHAT `bytes` MEANS, and it is not "the size at the time of the event". The scan reads the
lake NOW.

THE `stage` HALF IS EXACT, and it is the half every published throughput number uses.
The orthos under `Full_Image/Pipeline Imagery` and `phase3/edmonds_canopy_mask_2020.tif`
are written once and read forever; all 28 distinct sized `stage` basenames resolve in
those two write-once roots, and 24 cross-check exactly against the independent `size_mb`
column of `phase4/qc/imagery_geometry.csv` (0 disagreements).

THE `copy` HALF IS NOT, and the error is systematic, not churn. Measured 2026-09-07 by
pairing every `⏱ copy X: Ns` with the `✓ … write: X (N MB` line the same call prints and
comparing `round(bytes/1e6)` to that integer MB (the rounding is not optional — the
engine formats `{want_size/1e6:.0f}`, so a byte-exact comparison disagrees on all 2,173
rows and tells you nothing): **1,025 of 2,173 comparable rows disagree — 47%, median
44%, max 67%, the lake file LARGER in 984 of them.** `sem_best_*.pt` is overwritten every
improving epoch and the architecture grew. So `copy` `mb_per_s` is NOT usable at the row
level; only its median means anything, and even that shifts: the all-copy median is
463.9 MB/s on this file's `bytes` and 429.4 MB/s on the logged sizes (`sem_best` alone:
484.0 vs 429.4). Quote 429.4. `bytes` would be
outright WRONG for append-mode artifacts — `semantic_eval_report.csv` grows with every
run — though those rows are ambiguity-blanked anyway. The rule is the rule: `bytes` is a
property of the lake, joined by name, not a property of the event.

`stage` AND `copy` MEASURE OPPOSITE DIRECTIONS AND DIFFERENT MEDIA.

    stage       `common.py::_stage_imagery_local` (`stage <ortho>`) and
                `staging.py::_stage_tiles_local` (`stage tiles <year>`) copy Drive → local
                NVMe. This is a Drive READ, and it is the number the 40 MB/s claim is
                about — but only on a COLD read. `common.py::_unstage_imagery_local`
                deletes the scratch copy after each step, so a later step re-staging the
                same file reads it back out of the warm rclone VFS / OS page cache: 3 of
                281 sized rows exceed 500 MB/s for that reason (the same ortho twice and
                the 2020 mask once, max `stage 2006_snoh_1m_rgb.tif` at 1092.72 MB/s, the same basename
                that read 156.10 MB/s three minutes earlier in the same session). Drop
                the >300 MB/s tail before quoting `stage` as Drive throughput; doing so
                moves the median 38.96 → 38.25 and p90 87.22 → 84.11, so the published
                39.0 / 39.7 (≥1 GB) figures stand either way.
    copy        `common.py::_copy_to_drive` copies local NVMe → a `.part` file on the
                rclone FUSE mount. That write lands in the VFS cache and returns before
                anything reaches Google, so `copy` mb_per_s is a CACHE-WRITE rate, not
                upload bandwidth — the speedup report already caught itself pricing a
                write at the read rate (§2, "a correction to my own framing"). Never
                quote a `copy` row as Drive throughput.

    Two further caveats on `copy`: `_copy_to_drive` also calls `tock` inside its
    `except OSError` retry branch, so a row CAN time a FAILED partial transfer — measured
    2026-09-07, 0 of 2,233 copy rows do (no `⏱ copy` line in the 507 archived step logs
    is followed by `! copy raised`), so do not discard a fast or slow copy row as a
    failure without re-counting; and the label is the DESTINATION basename, which is what
    the scan finds.

`mb_per_s` is blank unless `bytes` resolved AND `seconds` > 0. `copy semantic_eval_report
.csv: 0.0s` occurs 43 times in the archive — sub-cadence operations are real, and a
division by zero is not a rate.

Run:  py -3.12 qc/instruments/harvest_timing_events.py [--dry-run]
      py -3.12 qc/instruments/harvest_timing_events.py --logs-dir DIR --lake-root DIR
      A run that finds ZERO events REFUSES to overwrite a populated output and exits 2;
      `--allow-empty` is the deliberate override.
Output: phase4/qc/timing_events.csv  (schema: docs/SCHEMAS.md)
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import statistics
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

COLS = ["run_id", "year", "run_tag", "step", "label", "seconds", "bytes",
        "mb_per_s", "log_file"]

# The five roots the size join may look in, relative to the lake root. Named here rather
# than taken from lake.py's constants because the SET is the contract — adding a sixth
# changes what a blank `bytes` means in every historical row.
SIZE_ROOTS = ("Full_Image/Pipeline Imagery", "phase4/models", "phase4/masks",
              "phase4/eval", "phase3")

# Only these two label shapes name a file. Everything else (`inference`, `postproc`,
# `polygonize`) is a phase, not a transfer, and gets a blank `bytes` by construction.
SIZED_PREFIXES = ("stage ", "copy ")

# `  ⏱ stage 2017_king_rgb.tif: 309.4s`. Two guards, and it is worth being precise about
# which does what: the DIGIT RUN `(\d+(?:\.\d+)?)s` is what excludes the one archived log
# that echoed the writer's own source line, `print(f"  ⏱ {label}: {elapsed:.1f}s")` —
# `{elapsed:.1f}s` has no digits. The end anchor excludes trailing text after the seconds
# (`… : 12.3s (retry 2/3)`), a shape the archive does not currently contain; measured
# 2026-09-07, anchored and unanchored both match the same 2,823 of 2,824 glyph lines.
_EVENT = re.compile(r"⏱\s+(.+?):\s+(\d+(?:\.\d+)?)s\s*$")

# The header block `pipeline_log.py::StepLogger` writes. `run id` and `year` are
# space-aligned with NO colon; `command:` has one.
_RUN_ID = re.compile(r"^run id\s+(\S+)\s*$", re.M)
_YEAR = re.compile(r"^year\s+(\S+)\s*$", re.M)
_COMMAND = re.compile(r"^command:\s+(.*)$", re.M)


def _flag(command, flag):
    m = re.search(rf"{re.escape(flag)}[ =](\S+)", command or "")
    return m.group(1) if m else ""


def parse_header(text):
    """-> (run_id, year, run_tag, step). Anything absent is blank, never guessed.

    `step` comes from the COMMAND LINE's `--step`, which is the bare step name
    (`evaluate`), not from the `=== ... --step evaluate_2006s ===` banner, whose value
    carries the year label. Early logs (the 2026-08-22/26 `labels`/`tile` runs) predate
    `--run-tag` entirely and legitimately have none.
    """
    m = _COMMAND.search(text)
    cmd = m.group(1) if m else ""
    rid = _RUN_ID.search(text)
    yr = _YEAR.search(text)
    return (rid.group(1) if rid else "",
            yr.group(1) if yr else _flag(cmd, "--year"),
            _flag(cmd, "--run-tag"),
            _flag(cmd, "--step"))


def build_size_index(lake_root, roots=SIZE_ROOTS):
    """basename -> size in bytes, or None where two DIFFERENT sizes share the name.

    One walk per root, in this process, ever. Roots that do not exist are skipped (an
    unmounted lake yields an empty index and blank `bytes`, not a crash). A root that
    exists but lists empty is retried through `lake.py::read_retry` — the Drive mirror
    returns empty listings for populated directories, and treating that as "no files"
    would silently blank the whole join.
    """
    sizes = {}
    lake_root = Path(lake_root)
    for rel in roots:
        root = lake_root / rel
        try:
            if not root.is_dir():
                continue
        except OSError:
            continue
        found = read_retry_listing(root)
        for name, size in found:
            if name in sizes and sizes[name] != size:
                sizes[name] = None          # ambiguous, and stays that way
            elif name not in sizes:
                sizes[name] = size
    return sizes


def read_retry_listing(root, tries=3, pause=1.0):
    """[(basename, size)] under `root`, recursively, retried while empty."""
    def _walk():
        out = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for f in filenames:
                try:
                    out.append((f, os.path.getsize(os.path.join(dirpath, f))))
                except OSError:
                    continue
        return out
    try:
        from lake import read_retry
    except ImportError:                                          # pragma: no cover
        return _walk()
    return read_retry(_walk, tries=tries, pause=pause) or []


def size_for(label, sizes):
    """The bytes this label moved, or None (miss, ambiguous, or not a transfer)."""
    for pre in SIZED_PREFIXES:
        if label.startswith(pre):
            return sizes.get(label[len(pre):].strip())
    return None


def read_retry_logs(logs_dir, tries=3, pause=1.0):
    """The step logs under `logs_dir`, retried while the listing comes back empty.

    The PRIMARY input gets the same guard as the size scan, and for the same measured
    reason (`lake.py::read_retry`): the Drive mirror hands back an empty listing for a
    directory that is plainly populated a second later. Without it a blink publishes a
    header-only `timing_events.csv` over 2,823 measured rows and exits 0. `tries=3`
    deliberately, not `read_retry`'s default 10 — a genuinely empty directory must not
    cost ten seconds of sleep.
    """
    def _glob():
        return sorted(Path(logs_dir).glob("phase4_semantic_finetune_*.log"))
    try:
        from lake import read_retry
    except ImportError:                                          # pragma: no cover
        return _glob()
    return read_retry(_glob, tries=tries, pause=pause) or []


def harvest(logs_dir, sizes):
    """One row per timing line, in (run_id, log line) order."""
    rows = []
    for p in read_retry_logs(logs_dir):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        run_id, year, tag, step = parse_header(text)
        for line in text.splitlines():
            m = _EVENT.search(line)
            if not m:
                continue
            label, secs_s = m.group(1).strip(), m.group(2)
            nbytes = size_for(label, sizes)
            try:
                secs = float(secs_s)
            except ValueError:                                   # pragma: no cover
                continue
            rate = ""
            if nbytes is not None and secs > 0:
                rate = f"{nbytes / 1e6 / secs:.2f}"
            rows.append({
                "run_id": run_id, "year": year, "run_tag": tag, "step": step,
                "label": label,
                # Verbatim from the log — a float round-trip would churn `309.4` to
                # `309.40000000000003` on some rows and the tracked CSV would diff.
                "seconds": secs_s,
                "bytes": "" if nbytes is None else nbytes,
                "mb_per_s": rate,
                "log_file": p.name,
            })
    # Stable sort on run_id alone: rows already arrive in (file, line) order, so this is
    # exactly "run_id, then log line order". log_file breaks ties between the early logs
    # that carry no `run id` line at all.
    rows.sort(key=lambda r: (r["run_id"], r["log_file"]))
    return rows


def _has_rows(out):
    """True if `out` exists and holds more than a header line."""
    try:
        return len([ln for ln in out.read_text(encoding="utf-8").splitlines()
                    if ln.strip()]) > 1
    except OSError:
        return False


def _logs_dir(explicit=None):
    if explicit:
        return Path(explicit)
    from lake import LOGS_DIR
    return LOGS_DIR


def _lake_root(explicit=None):
    if explicit:
        return Path(explicit)
    from lake import BASE
    return BASE


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--logs-dir", default=None)
    ap.add_argument("--lake-root", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-empty", action="store_true",
                    help="permit replacing a populated timing_events.csv with a "
                         "header-only one (default: refuse and exit 2)")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    logs_dir = _logs_dir(a.logs_dir)
    if not logs_dir.exists():
        print(f"FATAL: logs not found: {logs_dir}\n"
              f"       this instrument reads the lake — mount it, or pass --logs-dir")
        return 2

    sizes = build_size_index(_lake_root(a.lake_root))
    if not sizes:
        print("  ! no lake roots readable — every `bytes` cell will be blank")
    rows = harvest(logs_dir, sizes)

    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    out = Path(a.out) if a.out else (QC / "timing_events.csv")
    # A harvest that found NOTHING must never be the thing that erases the archive.
    # The retry above covers a blinking listing; this covers everything else that can
    # end in zero rows (wrong --logs-dir, a mount that vanished mid-walk).
    if not a.dry_run and not rows and not a.allow_empty and _has_rows(out):
        print(f"REFUSING: 0 timing events, but {out.name} already holds measured rows.\n"
              f"          check --logs-dir, or pass --allow-empty to overwrite anyway")
        return 2
    if not a.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(buf.getvalue(), encoding="utf-8", newline="")

    sized = [r for r in rows if r["bytes"] != ""]
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} timing events "
          f"({len(sized)} with a size) → {out.name}")
    print(f"  {'label prefix':16} {'n':>5} {'sized':>6} {'median MB/s':>12} "
          f"{'p10':>8} {'p90':>8}")
    for pre in ("stage ", "copy "):
        grp = [r for r in rows if r["label"].startswith(pre)]
        rates = sorted(float(r["mb_per_s"]) for r in grp if r["mb_per_s"])
        if rates:
            p10 = rates[max(0, int(0.10 * (len(rates) - 1)))]
            p90 = rates[min(len(rates) - 1, int(0.90 * (len(rates) - 1)))]
            print(f"  {pre.strip():16} {len(grp):>5} {len(rates):>6} "
                  f"{statistics.median(rates):>12.1f} {p10:>8.1f} {p90:>8.1f}")
        else:
            print(f"  {pre.strip():16} {len(grp):>5} {0:>6} {'':>12} {'':>8} {'':>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
