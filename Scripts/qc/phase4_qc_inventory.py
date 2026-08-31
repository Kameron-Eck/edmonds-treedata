"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — MASK / PROB RASTER INVENTORY
  Edmonds Temporal Active Learning Pipeline

  Sweeps phase4/masks/ and reports, for EVERY raster, whether it is
  actually usable: file size, valid (non-nodata) fraction, probability
  range, CRS, shape, bounds. Flags the failure modes that have silently
  poisoned QC in this project:

    EMPTY        zero-byte file                     (prob_2022_xsensor_train)
    MOSTLY_NODATA valid fraction below --min-valid-frac
                 → a failed / partial inference run (prob_2017_xsensor_rgb,
                   96.5% nodata with probabilities collapsed near 0)
    NO_CONFIDENCE max probability anywhere < 0.5
                 → the model never confidently predicts canopy; broken run
    OK           usable

  WHY THIS EXISTS
  ---------------
  Before this, a failed inference run reached the scorer, which wrote a
  `nan` row into qc_indep_report.csv, which then looked like a scored
  year. The scorers now fail loudly (--min-valid-frac); this script is
  the standing inventory so a bad raster is caught before anyone scores
  it at all.

  Reads only — never writes into masks/. Local-safe (rasterio only, no
  torch): runs on the Windows mount off D:/G: without a Colab round-trip.

  USAGE
    py -3.12 phase4_qc_inventory.py
    py -3.12 phase4_qc_inventory.py --min-valid-frac 0.10 --sample 4000
    py -3.12 phase4_qc_inventory.py --glob "edmonds_canopy_prob_*.tif"

  OUTPUT
    phase4/qc/mask_inventory.csv   one row per raster
    stdout                          human-readable table, problems first
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import importlib
import re
import subprocess
import sys
from pathlib import Path


def _pip(spec):
    try:
        importlib.import_module(spec.split("==")[0].replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=False)


_pip("rasterio")

import numpy as np                                            # noqa: E402
import rasterio                                               # noqa: E402
from rasterio.enums import Resampling                          # noqa: E402
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402
from pipeline_log import write_step_log

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

QC_DIR   = BASE / "phase4" / "qc"
MASKS    = BASE / "phase4" / "masks"
LOGS_DIR = BASE / "phase4" / "logs"

# verdicts, worst first — drives both sort order and the exit code
VERDICT_ORDER = ["EMPTY", "UNREADABLE", "MOSTLY_NODATA", "NO_CONFIDENCE",
                 "SUSPECT_PARTIAL", "SPARSE_BY_DESIGN", "OK"]
BAD = {"EMPTY", "UNREADABLE", "MOSTLY_NODATA", "NO_CONFIDENCE", "SUSPECT_PARTIAL"}

# Some rasters are SUPPOSED to be mostly nodata: the *_train / *_sample runs
# infer over a fixed set of C-CAP-stratified sample tiles (phase4_ccap_sample.py,
# locate-only), not the whole city, so ~0.3-5% valid is CORRECT for them. Calling
# those "failed runs" is a false alarm that trains you to ignore the tool.
SPARSE_BY_DESIGN = ("_train", "_sample")


def inspect(path, min_valid_frac, sample):
    """One raster → a dict row. Never raises; unreadable is a verdict, not a crash."""
    row = dict(file=path.name, verdict="OK", size_mb=0.0, valid_frac=float("nan"),
               max_prob=float("nan"), mean_prob=float("nan"), nodata="",
               crs="", width=0, height=0, note="")
    try:
        row["size_mb"] = round(path.stat().st_size / 1e6, 2)
    except OSError:
        pass

    if row["size_mb"] == 0.0:
        row["verdict"] = "EMPTY"
        row["note"] = "zero-byte file — the write failed silently"
        return row

    try:
        with rasterio.open(path) as s:
            row["crs"] = str(s.crs)
            row["width"], row["height"] = s.width, s.height
            row["nodata"] = "" if s.nodata is None else str(s.nodata)
            if s.count < 1 or s.width == 0 or s.height == 0:
                row["verdict"] = "UNREADABLE"
                row["note"] = "no bands or zero extent"
                return row
            h = min(sample, s.height)
            w = max(1, int(s.width * h / s.height))
            a = s.read(1, out_shape=(h, w), resampling=Resampling.nearest)
            nd = 255 if s.nodata is None else s.nodata
    except Exception as e:                                     # noqa: BLE001
        row["verdict"] = "UNREADABLE"
        row["note"] = f"{type(e).__name__}: {e}"[:160]
        return row

    valid = a != nd
    row["valid_frac"] = round(float(valid.mean()), 4)
    if valid.any():
        v = a[valid].astype(np.float32) / 254.0
        row["max_prob"] = round(float(v.max()), 4)
        row["mean_prob"] = round(float(v.mean()), 4)

    sparse_ok = any(k in path.stem for k in SPARSE_BY_DESIGN)
    if row["valid_frac"] <= 0.0:
        # "Sparse by design" never means ZERO valid pixels. A train/sample raster
        # with no data at all is broken, not sparse — do not let the exemption
        # hide it (edmonds_canopy_prob_2022_xsensor_train.tif, 0.0% valid).
        row["verdict"] = "EMPTY"
        row["note"] = ("no valid pixels at all — broken regardless of tiling; "
                       "if this file is on Drive, also confirm it is not still syncing")
    elif row["valid_frac"] < min_valid_frac and sparse_ok:
        row["verdict"] = "SPARSE_BY_DESIGN"
        row["note"] = ("sample/train tile subset — sparse is CORRECT here; "
                       "not citywide, do not score as a year")
    elif row["valid_frac"] < min_valid_frac:
        row["verdict"] = "MOSTLY_NODATA"
        row["note"] = (f"{100*(1-row['valid_frac']):.1f}% nodata — failed or partial "
                       f"inference run; do NOT score")
    elif row["max_prob"] == row["max_prob"] and row["max_prob"] < 0.5:
        row["verdict"] = "NO_CONFIDENCE"
        row["note"] = (f"max prob {row['max_prob']:.3f} — model never confidently "
                       f"predicts canopy; suspect a broken run")
    return row


def _flag_outliers(rows, ratio=0.5):
    """Catch a partial run that clears the absolute floor but not its own siblings.

    A flat --min-valid-frac cannot see this: edmonds_canopy_prob_2015_citywide_rgb
    is 7.4% valid and passed as OK, while every other citywide 2015 raster is
    ~90.8%. Same year, same ground — one of them did not finish. Comparing each
    citywide raster against the best coverage achieved for that same year finds
    it without hard-coding any per-year expectation.
    """
    best = {}
    for r in rows:
        if r["verdict"] in ("EMPTY", "UNREADABLE", "SPARSE_BY_DESIGN"):
            continue
        m = re.search(r"prob_(\d{4})", r["file"])
        if not m or r["valid_frac"] != r["valid_frac"]:
            continue
        y = m.group(1)
        best[y] = max(best.get(y, 0.0), r["valid_frac"])
    for r in rows:
        if r["verdict"] != "OK":
            continue
        m = re.search(r"prob_(\d{4})", r["file"])
        if not m:
            continue
        top = best.get(m.group(1), 0.0)
        if top > 0 and r["valid_frac"] < ratio * top:
            r["verdict"] = "SUSPECT_PARTIAL"
            r["note"] = (f"valid {100*r['valid_frac']:.1f}% vs {100*top:.1f}% for another "
                         f"{m.group(1)} raster — likely an unfinished run")
    return rows


def _print_table(rows):
    order = {v: i for i, v in enumerate(VERDICT_ORDER)}
    rows = sorted(rows, key=lambda r: (order.get(r["verdict"], 9), r["file"]))
    print(f"\n{'verdict':<14} {'file':<52} {'MB':>9} {'valid':>7} {'maxp':>6}  note")
    print("-" * 132)
    for r in rows:
        vf = "  n/a" if r["valid_frac"] != r["valid_frac"] else f"{100*r['valid_frac']:5.1f}%"
        mp = "   n/a" if r["max_prob"] != r["max_prob"] else f"{r['max_prob']:6.3f}"
        print(f"{r['verdict']:<14} {r['file']:<52} {r['size_mb']:>9.2f} {vf:>7} {mp:>6}  {r['note'][:44]}")
    bad = [r for r in rows if r["verdict"] in BAD]
    print("-" * 132)
    print(f"{len(rows)} raster(s); {len(bad)} PROBLEM(S).")
    if bad:
        print("\nDo not score these until they are re-run:")
        for r in bad:
            print(f"  ! {r['file']:<52} {r['verdict']}")
    return rows


def _write_csv(rows):
    QC_DIR.mkdir(parents=True, exist_ok=True)
    out = QC_DIR / "mask_inventory.csv"
    cols = ["file", "verdict", "size_mb", "valid_frac", "max_prob", "mean_prob",
            "nodata", "crs", "width", "height", "note", "ts"]
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "ts": ts})
    print(f"\n[inventory] wrote {out}")
    return out



def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(
        description="Inventory phase4/masks/ — flag empty / mostly-nodata / no-confidence rasters.")
    ap.add_argument("--dir", default=str(MASKS), help=f"Directory to sweep (default {MASKS}).")
    ap.add_argument("--glob", default="*.tif", help="Filename glob (default *.tif).")
    ap.add_argument("--min-valid-frac", type=float, default=0.05,
                    help="Below this valid fraction a raster is MOSTLY_NODATA (default 0.05).")
    ap.add_argument("--sample", type=int, default=2000,
                    help="Decimated read height in px (default 2000) — keeps the sweep fast.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 2 if any problem raster is found (for CI / gating).")
    args = ap.parse_args(filtered)

    d = Path(args.dir)
    if not d.exists():
        raise FileNotFoundError(f"--dir not found: {d}")
    paths = sorted(d.glob(args.glob))
    if not paths:
        print(f"[inventory] no files matching {args.glob} in {d}")
        return
    print(f"[inventory] sweeping {len(paths)} raster(s) in {d}")

    rows = []
    for i, p in enumerate(paths, 1):
        print(f"    [{i}/{len(paths)}] {p.name}", flush=True)
        rows.append(inspect(p, args.min_valid_frac, args.sample))

    rows = _flag_outliers(rows)
    rows = _print_table(rows)
    _write_csv(rows)
    _bad = [r for r in rows if r["verdict"] in BAD]
    write_step_log("phase4_qc_inventory", step="sweep", logs_dir=LOGS_DIR,
                   rasters=len(rows), problems=len(_bad),
                   bad=" ".join(f"{r['file']}={r['verdict']}" for r in _bad))

    if args.strict and any(r["verdict"] in BAD for r in rows):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
