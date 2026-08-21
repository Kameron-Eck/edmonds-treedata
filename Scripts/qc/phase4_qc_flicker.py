"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: temporal-stability ("flicker") test on stable parcels
  Edmonds Temporal Active Learning Pipeline

  WHY
    For a 24-year canopy CHANGE series, a model's single-year accuracy
    matters far less than whether it makes the SAME mistakes every year.
    A false "tree" on a lawn that appears EVERY year cancels in
    year-to-year differencing; one that FLICKERS (present some years,
    absent others) manufactures spurious canopy gain/loss — the worst
    error mode for a change product.

    This is the cheap decision-gate (per the multi-agent review): before
    investing in the phase3 height base-mirror to shave grass FPs, measure
    whether grass FPs are STATIC or FLICKER across years, on ground we KNOW
    did not change.

  METHOD
    On known-unchanged non-tree parcels (parks / playing fields / stadium /
    parking / water — the curated Negative_* training-site footprints, or a
    --parcels GeoPackage), score each year's canopy mask and report the
    FALSE-CANOPY fraction (any canopy on these parcels is a false positive).
    Then:
      • per-parcel FLICKER = std-dev of false-canopy % across years
      • RESOLUTION STEP   = mean false-canopy on fine (≤15 cm) vs coarse
                            (≥50 cm) years — a jump masquerades as change
                            at the acquisition boundary.

  GATE (read the numbers, not a magic cutoff):
    mean flicker LOW  (≲3 pp) → FPs are static → they cancel in differencing
                                → ship the RGB-only model, SKIP the phase3 mirror.
    mean flicker HIGH (≳5 pp) → FPs flicker → per-year grass rejection matters
                                → the 2020 ceiling probe / phase3 jumps the queue.

  PRODUCES (phase4/qc/):
    flicker_report.csv   parcel × year false-canopy %, + flicker/step summary
    flicker_report.txt   human-readable summary + verdict
    flicker_report.png   grouped bars (parcel × year)

  USAGE (local Windows or Colab; rasterio auto-installs; torch-free):
    py -3.12 phase4_qc_flicker.py                       # all masks on disk
    py -3.12 phase4_qc_flicker.py --years 2000,2013,2015,2017,2022
    py -3.12 phase4_qc_flicker.py --parcels my_stable_parcels.gpkg
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import datetime as _dt
import glob
import importlib
import subprocess
import sys
from pathlib import Path


def _pip(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("rasterio", "rasterio"), ("numpy", "numpy"),
                    ("geopandas", "geopandas"), ("matplotlib", "matplotlib")]:
    try:
        importlib.import_module(_imp)
    except ImportError:
        _pip(_spec)

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

MASKS_DIR = BASE / "phase4" / "masks"
PHOTOS    = BASE / "photos"
QC_DIR    = BASE / "phase4" / "qc"
LOGS_DIR  = BASE / "phase4" / "logs"
CANOPY_VALUE = 1
MASK_NODATA  = 255

# year → GSD (cm), for the fine/coarse resolution-step split (Method_Pipeline).
GSD_CM = {"2000": 59.7, "2002": 59.7, "2005": 29.9, "2007": 29.9, "2009": 29.9,
          "2013": 14.9, "2015": 14.9, "2016": 50.0, "2017": 7.5, "2019": 14.9,
          "2019n": 60.0, "2020": 7.5, "2021": 14.9, "2021s": 50.0, "2022": 7.5,
          "2022n": 60.0, "2023": 14.9, "2024": 7.5}
FINE_MAX_CM = 15.0            # ≤ this = fine tier; ≥ COARSE_MIN = coarse tier
COARSE_MIN_CM = 45.0


# ── Stable parcels ────────────────────────────────────────────────────────────
def load_parcels(parcels_path=None):
    """Return a GeoDataFrame of known-unchanged non-tree parcels (EPSG:3857).
    Default: the curated Negative_* footprints (each _rgb.tif's bounds → a box)."""
    from shapely.geometry import box
    if parcels_path:
        gdf = gpd.read_file(parcels_path).to_crs("EPSG:3857")
        if "name" not in gdf.columns:
            gdf["name"] = [f"parcel_{i}" for i in range(len(gdf))]
        return gdf[["name", "geometry"]]

    rows = []
    for tif in sorted(glob.glob(str(PHOTOS / "Negative_*_rgb.tif"))):
        with rasterio.open(tif) as s:
            b = rasterio.warp.transform_bounds(s.crs, "EPSG:3857", *s.bounds)
        name = Path(tif).stem.replace("Negative_", "").replace("_rgb", "")
        rows.append({"name": name, "geometry": box(*b)})
    if not rows:
        raise FileNotFoundError(f"no Negative_*_rgb.tif parcels in {PHOTOS} "
                                f"(and no --parcels given)")
    return gpd.GeoDataFrame(rows, crs="EPSG:3857")


def discover_years(years_arg):
    if years_arg:
        return [y.strip() for y in years_arg.split(",") if y.strip()]
    ys = []
    for p in sorted(glob.glob(str(MASKS_DIR / "edmonds_canopy_mask_*.tif"))):
        y = Path(p).stem.replace("edmonds_canopy_mask_", "")
        ys.append(y)
    return ys


def false_canopy_fraction(mask_path, parcel_geom_3857):
    """Fraction of a parcel's IMAGED pixels that the mask calls canopy (= false
    positive, since the parcel is known non-tree). None if the parcel is outside
    this year's coverage."""
    with rasterio.open(mask_path) as m:
        b = rasterio.warp.transform_bounds("EPSG:3857", m.crs, *parcel_geom_3857.bounds)
        win = rasterio.windows.from_bounds(*b, transform=m.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(rasterio.windows.Window(0, 0, m.width, m.height))
        if win.width <= 0 or win.height <= 0:
            return None
        a = m.read(1, window=win)
    imaged = a != MASK_NODATA
    n = int(imaged.sum())
    if n == 0:
        return None
    return 100.0 * int(((a == CANOPY_VALUE) & imaged).sum()) / n


# ── Report ────────────────────────────────────────────────────────────────────
def run(years, parcels_path):
    parcels = load_parcels(parcels_path)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[flicker] parcels: {list(parcels['name'])}")
    print(f"[flicker] years  : {years}")

    # parcel × year matrix of false-canopy %
    table = {}                                     # name -> {year -> pct or None}
    for _, p in parcels.iterrows():
        row = {}
        for y in years:
            mp = MASKS_DIR / f"edmonds_canopy_mask_{y}.tif"
            row[y] = false_canopy_fraction(mp, p.geometry) if mp.exists() else None
        table[p["name"]] = row

    # summaries
    def _vals(name):
        return [v for v in table[name].values() if v is not None]

    per_parcel_std = {n: (float(np.std(_vals(n))) if len(_vals(n)) >= 2 else float("nan"))
                      for n in table}
    valid_std = [s for s in per_parcel_std.values() if not np.isnan(s)]
    mean_flicker = float(np.mean(valid_std)) if valid_std else float("nan")

    fine_ys   = [y for y in years if GSD_CM.get(y, 99) <= FINE_MAX_CM]
    coarse_ys = [y for y in years if GSD_CM.get(y, 0) >= COARSE_MIN_CM]

    def _tier_mean(tier_years):
        vals = [table[n][y] for n in table for y in tier_years
                if table[n].get(y) is not None]
        return float(np.mean(vals)) if vals else float("nan")

    fine_mean, coarse_mean = _tier_mean(fine_ys), _tier_mean(coarse_ys)
    res_step = (coarse_mean - fine_mean
                if not (np.isnan(fine_mean) or np.isnan(coarse_mean)) else float("nan"))

    _write_outputs(years, table, per_parcel_std, mean_flicker,
                   fine_ys, coarse_ys, fine_mean, coarse_mean, res_step)
    return mean_flicker, res_step


def _verdict(mean_flicker):
    if np.isnan(mean_flicker):
        return "INCONCLUSIVE — need ≥2 years of masks per parcel."
    if mean_flicker < 3.0:
        return ("STATIC (flicker <3 pp) → false canopy on stable ground is steady; it "
                "cancels in year-to-year differencing → SHIP the RGB-only model, SKIP phase3.")
    if mean_flicker > 5.0:
        return ("FLICKER (>5 pp) → false canopy jumps year to year → spurious change; per-year "
                "grass rejection matters → run the 2020 ceiling probe / reopen phase3.")
    return ("BORDERLINE (3–5 pp) → judge against the smallest real canopy change the study must "
            "detect; lean ship if the target effect is larger than this flicker.")


def _write_outputs(years, table, per_parcel_std, mean_flicker,
                   fine_ys, coarse_ys, fine_mean, coarse_mean, res_step):
    import csv
    # CSV
    csv_path = QC_DIR / "flicker_report.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["parcel"] + years + ["flicker_std_pp"])
        for n in table:
            w.writerow([n] + [("" if table[n][y] is None else round(table[n][y], 2))
                              for y in years] + [round(per_parcel_std[n], 2)])
    # TXT
    L = ["Temporal-stability (flicker) test — false canopy on known-unchanged parcels",
         f"  years  : {', '.join(years)}",
         f"  parcels: {', '.join(table)}",
         "",
         "  false-canopy % (any canopy on these non-tree parcels = false positive):",
         "    parcel                " + "  ".join(f"{y:>7}" for y in years) + "   flicker(std)"]
    for n in table:
        cells = "  ".join(("    n/a" if table[n][y] is None else f"{table[n][y]:>7.2f}")
                          for y in years)
        L.append(f"    {n:<20}  {cells}   {per_parcel_std[n]:>6.2f} pp")
    L += ["",
          f"  MEAN FLICKER (avg per-parcel std across years): {mean_flicker:.2f} pp",
          f"  resolution step: fine(≤{FINE_MAX_CM:.0f}cm) {fine_mean:.2f}% vs "
          f"coarse(≥{COARSE_MIN_CM:.0f}cm) {coarse_mean:.2f}%  → step {res_step:+.2f} pp",
          f"    fine years={fine_ys}  coarse years={coarse_ys}",
          "",
          "  VERDICT: " + _verdict(mean_flicker)]
    txt = "\n".join(L)
    (QC_DIR / "flicker_report.txt").write_text(txt, encoding="utf-8")
    print("\n" + txt)

    # PNG grouped bars
    try:
        names = list(table)
        x = np.arange(len(names))
        wbar = 0.8 / max(len(years), 1)
        fig, ax = plt.subplots(figsize=(max(7, 1.4 * len(names)), 4.6))
        for i, y in enumerate(years):
            vals = [(table[n][y] if table[n][y] is not None else 0) for n in names]
            ax.bar(x + i * wbar, vals, wbar, label=y)
        ax.set_xticks(x + 0.4 - wbar / 2)
        ax.set_xticklabels(names, rotation=20, ha="right", fontsize=9)
        ax.set_ylabel("false-canopy % on stable parcel")
        ax.set_title(f"Flicker test — mean flicker {mean_flicker:.2f} pp")
        ax.legend(fontsize=8, ncol=min(len(years), 6))
        fig.tight_layout()
        fig.savefig(QC_DIR / "flicker_report.png", dpi=115, bbox_inches="tight")
        plt.close(fig)
        print(f"[flicker] wrote {QC_DIR / 'flicker_report.png'}")
    except Exception as e:
        print(f"[flicker] WARN plot: {e}")
    print(f"[flicker] wrote {csv_path}\n[flicker] wrote {QC_DIR / 'flicker_report.txt'}")


def write_step_log(mean_flicker, res_step):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_flicker_{ts}.log").write_text(
            f"phase4_qc_flicker.py  mean_flicker={mean_flicker:.2f}pp "
            f"res_step={res_step:.2f}pp\n", encoding="utf-8")
    except Exception:
        pass


def main():
    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="Temporal-stability flicker test on stable parcels.")
    ap.add_argument("--years", default=None,
                    help="Comma-separated years (default: all masks on disk).")
    ap.add_argument("--parcels", default=None,
                    help="GeoPackage of known-unchanged non-tree polygons "
                         "(default: the curated Negative_* footprints).")
    args = ap.parse_args(filtered)

    years = discover_years(args.years)
    if len(years) < 2:
        print(f"  ! only {len(years)} year mask(s) found ({years}); flicker needs ≥2. "
              f"Run more years first, or pass --years.")
    mean_flicker, res_step = run(years, args.parcels)
    write_step_log(mean_flicker, res_step)


if __name__ == "__main__":
    main()
