"""
watch_queue.py — dumb poller of train_queue_status.csv (overhaul P7).

Prints each NEW status row as it lands (the queue flushes the CSV after every
step), flags anomalies loudly, and exits when the watched jobs finish — so a
human (or an agent invoked ONCE at exit) judges only when signaled. This is a
read-only poller, never a decision-maker, and never a billed daemon: run it in
a spare terminal during a Colab window.

Usage:
    py -3.12 watch_queue.py                    # poll every 60s until Ctrl-C
    py -3.12 watch_queue.py --interval 120
    py -3.12 watch_queue.py --until-jobs 2024  # exit 0 when job 2024 VERIFYs OK,
                                               # exit 1 on its hard failure
"""
import argparse
import csv
import sys
import time
from pathlib import Path

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
STATUS = BASE / "phase4" / "qc" / "train_queue_status.csv"

BAD = {"FAIL", "ERROR", "TIMEOUT", "ABORTED", "EMPTY", "MOSTLY_NODATA",
       "NO_CONFIDENCE", "BAD_CKPT", "NO_TILES", "BAD_INDEX", "MISSING"}


def _rows():
    if not STATUS.exists():
        return []
    with open(STATUS, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--until-jobs", default=None,
                    help="comma-separated job ids; exit when each has a job-end "
                         "VERIFY row (0 if all OK-ish, 1 if any hard-failed)")
    args = ap.parse_args([a for a in sys.argv[1:]
                          if not (a == "-f" or a.endswith(".json"))])
    watch = ({s.strip() for s in args.until_jobs.split(",") if s.strip()}
             if args.until_jobs else None)

    seen = len(_rows())
    print(f"watching {STATUS}  ({seen} existing rows; every {args.interval}s)")
    while True:
        try:
            rows = _rows()
            for r in rows[seen:]:
                mark = " <-- !!" if r.get("state") in BAD else ""
                print(f"  {r.get('ts','')}  {r.get('job',''):<7} "
                      f"{r.get('step',''):<16} {r.get('state',''):<16} "
                      f"{r.get('detail','')}{mark}")
            seen = len(rows)
            if watch:
                ended = {r["job"]: r["state"] for r in rows
                         if r.get("step") == "VERIFY" and r.get("job") in watch}
                failed = {r["job"] for r in rows
                          if r.get("job") in watch and r.get("state") in BAD}
                if watch <= (set(ended) | failed):
                    hard = failed | {j for j, s in ended.items() if s in BAD}
                    print(f"\ndone: {sorted(watch)}  "
                          f"({'ALL OK' if not hard else 'FAILED: ' + ', '.join(sorted(hard))})")
                    sys.exit(1 if hard else 0)
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nstopped.")
            return


if __name__ == "__main__":
    main()
