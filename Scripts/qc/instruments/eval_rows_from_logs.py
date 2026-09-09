"""eval_rows_from_logs.py — the evaluate metrics that survive when the eval report is clobbered.

THE FAILURE. `phase4/eval/semantic_eval_report.csv` is ONE shared lake file that every
evaluate step rewrites: read the whole CSV, drop the superseded rows for this year/arm,
append this run's rows, write it back through an async upload cache. Two Colab runtimes
running evaluate steps minutes apart each read a copy that lacks the other's rows, and
whichever upload lands LAST wins. Observed 2026-09-09 05:44Z: bb18_2006s_base and
bb50_2006s_base evaluated on two VMs; the report kept bb50 and lost bb18.

WHAT SURVIVES. Every evaluate step also writes its own per-step log,
`phase4/logs/phase4_semantic_finetune_evaluate_<year>_<stamp>.log`, ONE FILE PER RUN, so
nothing overwrites it. The stdout it captures carries the same headline metrics the
report row does. This instrument parses every such log into one row each
(`phase4/qc/eval_from_logs.csv`) and, with `--compare`, names the run_ids that exist in
the logs but not in the live report (`phase4/qc/eval_report_gaps.csv`).

A GAP IS NOT A CLOBBER. Each gap row carries a `verdict`:
    superseded        the run_id sits in semantic_eval_report_superseded.csv — a later
                      evaluate's write archived it (the log says so: "N superseded
                      row(s) for 2006s/rgb archived ... before replacement"; the key is
                      year/channels, not the arm). On record, not lost.
    pre_run_id_era    the run_id sorts before the EARLIEST run_id either report file
                      carries — the report did not record run_id/run_tag yet, so its rows
                      from then are unjoinable; absence is a schema gap, not a loss
    clobber_candidate absent from both files and from the recorded era — nothing on the
                      lake but the log holds these metrics
Read that column before calling anything lost.

Line shapes, pinned from real logs (2026-09-08, 63 evaluate logs on the lake):
    command:   --year 2006s --step evaluate ... --run-tag bb18_2006s_base ... --encoder resnet18 ...
    run id     20260909T054202Z_2006s_bb18_2006s_base_evaluate       (4 logs say `unrecorded`)
    completed: 2026-09-02T11:20:57.926803                            (Colab clock is UTC)
      Eval tiles: 49  [IN-SAMPLE (no held-out test at this GSD)]    (10 logs)
      Eval tiles: 147  [held-out test]                              (53 logs)
      Model: sem_best_2006s_t1_2006s_base.pt  (phase=B val_bce=0.47970083355903625)
      IoU=0.4441  Dice=0.6150  Acc=0.7960  Prec=0.5877  Rec=0.6451
      AUROC=0.8438  AP=0.6368  LogLoss=0.4688   [AP is the honest headline]
      Best-F1 @ thresh 0.417  (F1=0.6271  vs  0.6150 @ 0.50)
      @ operating thresh 0.417: IoU=0.4568  Dice=0.6271  Prec=0.5522  Rec=0.7256   (vs IoU=0.4441 @ 0.50)
`IoU=` also appears on the operating-thresh line and the `◆ DG2 note` line, so every
metric regex is anchored to its own line. One log (2011s hy_e3, 2026-09-01) died before
the metrics line: it yields a row with blank metrics and `note = no metrics line`.
No log prints a warm start; `warm_start` is parsed from a `--warm-start` flag if one is
ever present and is empty by observation otherwise.

Read-only on the lake. Writes only the two repo CSVs. Output is byte-identical across
runs (sorted by run_id then log_file; nothing clock-derived).

Run:  py -3.12 qc/instruments/eval_rows_from_logs.py [--logs-dir D] [--compare [--eval-report F]]
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
OUT_DIR = REPO / "phase4" / "qc"
OUT_ROWS = OUT_DIR / "eval_from_logs.csv"
OUT_GAPS = OUT_DIR / "eval_report_gaps.csv"

COLS = ["run_id", "year", "run_tag", "encoder", "warm_start", "eval_scope",
        "n_eval_tiles", "model_file", "phase", "val_bce",
        "iou", "dice", "acc", "prec", "rec",
        "op_thresh", "iou_op", "dice_op", "prec_op", "rec_op",
        "auroc", "best_f1_thresh", "log_file", "written_utc", "note"]
GAP_COLS = ["run_id", "year", "run_tag", "encoder", "iou", "log_file", "verdict"]

LOG_GLOB = "phase4_semantic_finetune_evaluate_*.log"
DEFAULT_ENCODER = "resnet101"
NUM = r"([0-9]*\.?[0-9]+)"

_RX = {
    "command": re.compile(r"^command:\s+(.*)$", re.M),
    "run_id": re.compile(r"^run id\s+(\S+)", re.M),
    "completed": re.compile(r"^completed:\s+(\S+)", re.M),
    "started": re.compile(r"^started:\s+(\S+)", re.M),
    "tiles": re.compile(r"^\s*Eval tiles:\s+(\d+)\s+\[([^\]]*)\]", re.M),
    "model": re.compile(r"^\s*Model:\s+(\S+)\s+\(phase=(\S+)\s+val_bce=" + NUM + r"\)", re.M),
    "headline": re.compile(r"^\s*IoU=" + NUM + r"\s+Dice=" + NUM + r"\s+Acc=" + NUM
                           + r"\s+Prec=" + NUM + r"\s+Rec=" + NUM, re.M),
    "op": re.compile(r"^\s*@ operating thresh " + NUM + r":\s+IoU=" + NUM + r"\s+Dice="
                     + NUM + r"\s+Prec=" + NUM + r"\s+Rec=" + NUM, re.M),
    "auroc": re.compile(r"^\s*AUROC=" + NUM, re.M),
    "bestf1": re.compile(r"^\s*Best-F1 @ thresh " + NUM, re.M),
}
_FNAME = re.compile(r"_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2})\.log$")


def _flag(cmd, name):
    m = re.search(r"(?:^|\s)" + re.escape(name) + r"(?:=|\s+)(\S+)", cmd)
    return m.group(1) if m else ""


def _utc(stamp):
    """`2026-09-02T11:20:57.926803` → `2026-09-02T11:20:57Z` (report's own format)."""
    return stamp[:19] + "Z" if len(stamp) >= 19 else ""


def parse_log(text, log_name):
    """One row (dict over COLS) from one evaluate step log's text."""
    g = lambda k: _RX[k].search(text)  # noqa: E731
    cmd = g("command").group(1) if g("command") else ""
    row = {c: "" for c in COLS}
    row.update({
        "run_id": g("run_id").group(1) if g("run_id") else "",
        "year": _flag(cmd, "--year"),
        "run_tag": _flag(cmd, "--run-tag"),
        "encoder": _flag(cmd, "--encoder") or DEFAULT_ENCODER,
        "warm_start": _flag(cmd, "--warm-start"),
        "log_file": log_name,
    })
    if (m := g("tiles")):
        row["n_eval_tiles"], row["eval_scope"] = m.group(1), m.group(2)
    if (m := g("model")):
        row["model_file"], row["phase"], row["val_bce"] = m.groups()
    if (m := g("headline")):
        row["iou"], row["dice"], row["acc"], row["prec"], row["rec"] = m.groups()
    else:
        row["note"] = "no metrics line"
    if (m := g("op")):
        (row["op_thresh"], row["iou_op"], row["dice_op"],
         row["prec_op"], row["rec_op"]) = m.groups()
    if (m := g("auroc")):
        row["auroc"] = m.group(1)
    if (m := g("bestf1")):
        row["best_f1_thresh"] = m.group(1)
    ts = g("completed") or g("started")
    if ts:
        row["written_utc"] = _utc(ts.group(1))
    elif (m := _FNAME.search(log_name)):
        d, hm = m.group(1).split("T")
        row["written_utc"] = f"{d}T{hm.replace('-', ':')}:00Z"
    return row


def harvest(logs_dir):
    rows = []
    for p in sorted(Path(logs_dir).glob(LOG_GLOB)):
        rows.append(parse_log(p.read_text(encoding="utf-8", errors="replace"), p.name))
    rows.sort(key=lambda r: (r["run_id"], r["log_file"]))
    return rows


def _csv_text(rows, cols):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _report_run_ids(path):
    """run_ids carried by a semantic_eval_report-shaped CSV (OVERALL rows; all rows if
    the file predates the `scope` column). Missing file → empty set."""
    path = Path(path)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        return {r.get("run_id", "") for r in rd
                if r.get("scope", "OVERALL") == "OVERALL"} - {"", "unrecorded"}


def compare(rows, eval_report, superseded=None):
    """Rows whose run_id the live report lacks. Unjoinable run_ids (blank / unrecorded)
    are skipped and counted, not listed."""
    live = _report_run_ids(eval_report)
    sup = _report_run_ids(superseded) if superseded else set()
    # run_ids are `YYYYMMDDTHHMMSSZ_...`, so string order is time order.
    first_recorded = min(live | sup) if (live | sup) else ""
    gaps, skipped = [], 0
    for r in rows:
        if r["run_id"] in ("", "unrecorded"):
            skipped += 1
            continue
        if r["run_id"] in live:
            continue
        if r["run_id"] in sup:
            verdict = "superseded"
        elif first_recorded and r["run_id"] < first_recorded:
            verdict = "pre_run_id_era"
        else:
            verdict = "clobber_candidate"
        gaps.append({**{c: r[c] for c in GAP_COLS if c != "verdict"}, "verdict": verdict})
    return gaps, skipped


def _lake_default(attr):
    import lake
    return getattr(lake, attr)


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--logs-dir", default=None, help="default: the lake's phase4/logs")
    ap.add_argument("--compare", action="store_true",
                    help="also write eval_report_gaps.csv against the live eval report")
    ap.add_argument("--eval-report", default=None,
                    help="default: the lake's phase4/eval/semantic_eval_report.csv")
    ap.add_argument("--out-dir", default=None, help="default: <repo>/phase4/qc")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    logs_dir = Path(a.logs_dir) if a.logs_dir else _lake_default("LOGS_DIR")
    if not logs_dir.exists():
        print(f"FATAL: logs dir not found: {logs_dir} — this reads the lake")
        return 2
    out_dir = Path(a.out_dir) if a.out_dir else OUT_DIR

    rows = harvest(logs_dir)
    n_blank = sum(1 for r in rows if r["note"])
    if not a.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / OUT_ROWS.name).write_text(_csv_text(rows, COLS), encoding="utf-8",
                                             newline="")
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} evaluate logs parsed "
          f"({n_blank} without a metrics line) → {out_dir / OUT_ROWS.name}")

    if a.compare:
        report = Path(a.eval_report) if a.eval_report else \
            _lake_default("EVAL_DIR") / "semantic_eval_report.csv"
        superseded = report.with_name(report.stem + "_superseded" + report.suffix)
        gaps, skipped = compare(rows, report, superseded)
        if not a.dry_run:
            (out_dir / OUT_GAPS.name).write_text(_csv_text(gaps, GAP_COLS),
                                                 encoding="utf-8", newline="")
        from collections import Counter
        n = Counter(x["verdict"] for x in gaps)
        lost = [x for x in gaps if x["verdict"] == "clobber_candidate"]
        print(f"  live report {report.name}: {len(gaps)} log run_ids absent "
              f"({skipped} unjoinable skipped) → {out_dir / OUT_GAPS.name}")
        print(f"  superseded {n['superseded']} (in {superseded.name}, replaced on purpose) · "
              f"pre_run_id_era {n['pre_run_id_era']} (report had no run_id column yet) · "
              f"clobber_candidate {len(lost)}:")
        for x in lost:
            print(f"    ! {x['run_id']:55} {x['encoder']:10} IoU={x['iou'] or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
