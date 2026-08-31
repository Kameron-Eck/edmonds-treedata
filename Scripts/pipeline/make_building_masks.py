#!/usr/bin/env python3
"""
  PER-YEAR BUILDING-PRESENCE MASKS — the NIR/vegetation roof filter
  ---------------------------------------------------------------------------

WHY
    Roofs are the largest non-vegetation contaminant in every spectral product
    this project builds. ~15% of the city's land sits under a building before
    you count the shadow and the driveway, and a bright composition-shingle
    roof can carry an NDVI that a fixed 0.2 cut will not reject.

    Masking them out with ONE current-state footprint layer is wrong in the
    early years: it removes ground where a house had not been built yet
    (Greystone, 2001-2005: bare graded earth in 2000, masked anyway) and never
    removes anything that has since been demolished. These masks are the
    time-aware version — one raster per acquisition year, containing only the
    structures that presence evidence says were standing.

WHAT IT WRITES
    {BUILDINGS}/masks/building_mask_{year}_1m.tif
        uint8, 1 = building, 0 = not. No nodata (every pixel is a real answer).
        LZW, tiled 512, one band.
    {BUILDINGS}/masks/building_mask_manifest.csv
        per-year counts and the measured building-pixel fraction.

THE GRID — read from the raster, never re-derived
    EPSG:3857, 1.0-unit pixels, the exact lattice of
    `nir_stack_1m.tif` (which is itself snapped to `lidar_snoh_chm.tif`).
    So these masks overlay the NIR stack, the NDVI stack, the CHM and every
    other 1 m 3857 product in the project pixel-for-pixel, with no resampling
    and no half-pixel drift.

    CAUTION ON "1 m": EPSG:3857 is not metric on the ground. At Edmonds
    (lat ~47.81) Web Mercator inflates distance by 1/cos(lat) = 1.487, so a 1.0
    *unit* pixel is ~0.67 m of ground. This is the same caveat the NIR stack
    and the YEAR_CATALOG carry. It is also why the +1 m buffer below is applied
    in EPSG:26910 (TRUE metres) and only then reprojected — buffering by 1.0 in
    3857 would be a 0.67 m buffer on the ground.

WHICH STRUCTURES GO IN
    Presence comes from `qc/roof_presence_matrix.py`, whose fusion rule is
    imported here rather than reimplemented, so the mask and the matrix can
    never drift apart:

      1. If the structure has a row in the matrix for this year, use its
         `verdict_final`.
      2. Otherwise (the matrix may be sector-only, or the year may not have
         been run) fall back to the ASSESSOR BACKBONE alone —
         `assessor_verdict(yr_built, year)` fused with an absent probe.
      3. Structures with no `yr_built` at all (2.5% of the layer) resolve to
         `uncertain`.

    A structure is burned when `verdict_final` is PRESENT **or** UNCERTAIN.
    That bias is deliberate: the mask's job is to REMOVE roof pixels from
    vegetation products, so a false positive costs a little real ground while a
    false negative leaves a roof masquerading as canopy. Every year's manifest
    row reports how many pixels came from each branch, so the cost is visible.

    NOTE the standing asymmetry: a building demolished before ~2025 has no
    footprint in any available source, so no mask can contain it, in any year.
    These masks under-mask the early years by an unmeasured amount.

BUFFER
    +1.0 TRUE metre, applied in EPSG:26910. A roof's thermal/spectral influence
    does not stop at the digitised wall line: eaves overhang, the polygon is a
    generalised trace, and the ortho carries building lean and registration slop
    between acquisitions. One metre is the smallest buffer that covers those
    without swallowing the yard. It costs area — a median 185 m2 footprint
    grows ~25-30% — and the manifest reports buffered and unbuffered fractions
    separately so the cost is never hidden inside one number.

USAGE
    py -3.12 pipeline/make_building_masks.py                 # default year set
    py -3.12 pipeline/make_building_masks.py --years 2016 2005
    py -3.12 pipeline/make_building_masks.py --all-years     # every catalog year
    py -3.12 pipeline/make_building_masks.py --overwrite

    Idempotent: an existing mask of the right shape is skipped unless
    --overwrite is given.

Local-only. CPU + rasterio. No Colab, no GPU.
v001
"""

from __future__ import annotations

from phase4seg.names import clean_argv
import argparse
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

_HERE = Path(__file__).resolve().parent           # …/Scripts/pipeline
_SCRIPTS = _HERE.parent                           # …/Scripts
sys.path.insert(0, str(_SCRIPTS / "qc"))   # roof_presence_matrix — the ONE blessed qc-path import

# the fusion rule and the mask policy live in the matrix script — import them
from roof_presence_matrix import (                # noqa: E402
    assessor_verdict, fuse, mask_present, MASK_PRESENT_FINAL,
)

try:
    from pipeline_log import write_step_log       # noqa: E402
except Exception:
    write_step_log = None


# ── Paths ────────────────────────────────────────────────────────────────────
DATA = Path(r"G:\My Drive\treedata")
BUILDINGS = DATA / "buildings"
BUILDINGS_GPKG = BUILDINGS / "buildings_canonical.gpkg"
MASK_DIR = BUILDINGS / "masks"
MANIFEST = MASK_DIR / "building_mask_manifest.csv"
LOGS_DIR = DATA / "phase4" / "logs"

MATRIX_DIR = DATA / "phase4" / "qc" / "roof_presence"
GRID_RASTER = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\nir_stack"
                   r"\nir_stack_1m.tif")
CITY_SHP = Path(r"D:\edmonds-pipeline\Imagery\City Boundry\Edmonds Boundry.shp")

WORK_CRS = "EPSG:26910"     # UTM 10N — TRUE metres. The buffer is applied here.
BUFFER_M = 1.0

# The 4 NIR-stack anchor years Kam named, plus two RGB-only years that bracket
# the record (2005 early, 2013 mid) — these are the years the roof filter is
# needed for first.
DEFAULT_YEARS = ["2005", "2013", "2016", "2019n", "2021s", "2023n"]


# ── Grid ─────────────────────────────────────────────────────────────────────
def read_grid(path: Path) -> dict:
    """The lattice is READ, never recomputed — see the module docstring."""
    if not path.exists():
        raise SystemExit(f"grid raster not found: {path}\n"
                         f"Run:  py -3.12 pipeline/make_nir_stack.py")
    with rasterio.open(path) as s:
        g = {"crs": s.crs, "transform": s.transform,
             "width": s.width, "height": s.height, "bounds": s.bounds}
    print(f"grid  {g['crs']}  {g['width']}x{g['height']}  "
          f"res {g['transform'].a}  from {path.name}")
    return g


# ── Presence resolution ──────────────────────────────────────────────────────
def presence_for_year(can: gpd.GeoDataFrame, matrix: pd.DataFrame | None,
                      ykey: str) -> pd.DataFrame:
    """One row per structure: verdict_final + which branch produced it.

    Structures covered by the matrix take its fused verdict; the rest fall back
    to the assessor backbone with no probe evidence. See the module docstring.
    """
    year_num = int(str(ykey)[:4])
    yb = pd.to_numeric(can.yr_built, errors="coerce")
    va = [assessor_verdict(y, year_num) for y in yb]
    fallback = [fuse(a, "unavailable") for a in va]

    out = pd.DataFrame({
        "building_id": can.building_id.values,
        "verdict_assessor": va,
        "verdict_final": [f[0] for f in fallback],
        "verdict_rule": [f[1] for f in fallback],
        "evidence": "assessor_only",
    })

    if matrix is not None:
        m = matrix[matrix.year == ykey]
        if len(m):
            m = m[["building_id", "verdict_final", "verdict_rule",
                   "disagreement"]].drop_duplicates("building_id")
            idx = out.building_id.isin(set(m.building_id))
            merged = (out[["building_id"]].merge(m, on="building_id", how="left"))
            out.loc[idx, "verdict_final"] = merged.loc[idx.values,
                                                       "verdict_final"].values
            out.loc[idx, "verdict_rule"] = merged.loc[idx.values,
                                                      "verdict_rule"].values
            out.loc[idx, "evidence"] = "matrix"
            print(f"  matrix covers {int(idx.sum()):,} / {len(out):,} structures "
                  f"for {ykey}")
        else:
            print(f"  matrix has no rows for {ykey} — assessor backbone only")
    out["burn"] = out.verdict_final.map(mask_present)
    return out


# ── Rasterize ────────────────────────────────────────────────────────────────
def burn_year(can_w: gpd.GeoDataFrame, pres: pd.DataFrame, grid: dict,
              ykey: str, tmp_dir: Path, overwrite: bool,
              city_mask: np.ndarray, n_city: int) -> dict:
    dst = MASK_DIR / f"building_mask_{ykey}_1m.tif"
    burn_ids = set(pres.loc[pres.burn, "building_id"])
    sel = can_w[can_w.building_id.isin(burn_ids)]
    row = {
        "year": ykey,
        "n_structures_total": len(can_w),
        "n_burned": len(sel),
        "n_present": int((pres.verdict_final == "present").sum()),
        "n_absent": int((pres.verdict_final == "absent").sum()),
        "n_uncertain": int((pres.verdict_final == "uncertain").sum()),
        "n_from_matrix": int((pres.evidence == "matrix").sum()),
        "n_from_assessor": int((pres.evidence == "assessor_only").sum()),
    }

    if dst.exists() and not overwrite:
        with rasterio.open(dst) as s:
            if (s.width, s.height) == (grid["width"], grid["height"]):
                a = s.read(1) != 0
                row["mask_px"] = int(a.sum())
                row["mask_px_in_city"] = int((a & city_mask).sum())
                row["pct_of_city_land"] = round(
                    100 * row["mask_px_in_city"] / n_city, 2)
                row["status"] = "skipped_exists"
                print(f"  {ykey}: exists with the right shape — skipping "
                      f"(--overwrite to rebuild)")
                return row

    # Buffer in TRUE metres, then reproject onto the 3857 grid.
    t0 = time.time()
    buf = sel.geometry.buffer(BUFFER_M)
    unbuf_m2 = float(sel.geometry.area.sum())
    buf_m2 = float(buf.area.sum())
    shp = gpd.GeoSeries(buf, crs=WORK_CRS).to_crs(grid["crs"])

    arr = rasterize(((g, 1) for g in shp.values),
                    out_shape=(grid["height"], grid["width"]),
                    transform=grid["transform"], fill=0,
                    all_touched=False, dtype="uint8")
    n_px = int(arr.sum())

    # The SAME structures without the buffer — so the reported city-land
    # fraction can be decomposed into "footprints" + "buffer", and neither
    # half can hide inside the other. This is the sanity check, not a product.
    raw = rasterize(((g, 1) for g in
                     gpd.GeoSeries(sel.geometry, crs=WORK_CRS)
                     .to_crs(grid["crs"]).values),
                    out_shape=(grid["height"], grid["width"]),
                    transform=grid["transform"], fill=0,
                    all_touched=False, dtype="uint8")
    ab = arr != 0
    row["mask_px"] = n_px
    row["mask_px_in_city"] = int((ab & city_mask).sum())
    row["pct_of_city_land"] = round(100 * row["mask_px_in_city"] / n_city, 2)
    row["mask_px_unbuffered"] = int(raw.sum())
    row["unbuf_px_in_city"] = int(((raw != 0) & city_mask).sum())
    row["pct_of_city_land_unbuffered"] = round(
        100 * row["unbuf_px_in_city"] / n_city, 2)
    del raw, ab

    prof = {"driver": "GTiff", "dtype": "uint8", "count": 1,
            "width": grid["width"], "height": grid["height"],
            "crs": grid["crs"], "transform": grid["transform"],
            "compress": "LZW", "tiled": True, "blockxsize": 512,
            "blockysize": 512, "BIGTIFF": "IF_SAFER"}
    tmp = tmp_dir / dst.name
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(arr, 1)
        d.set_band_description(1, f"building presence {ykey} (1=building)")
        d.update_tags(year=ykey, source="make_building_masks.py",
                      buffer_m=str(BUFFER_M),
                      policy="+".join(MASK_PRESENT_FINAL),
                      built=datetime.now().isoformat(timespec="seconds"))
    # validate before it goes to the FUSE mount (CLAUDE.md rule 3)
    with rasterio.open(tmp) as s:
        if (s.width, s.height) != (grid["width"], grid["height"]):
            raise SystemExit(f"{ykey}: written shape {s.width}x{s.height} != grid")
    MASK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp, dst)
    tmp.unlink(missing_ok=True)

    row.update({
        "mask_px": n_px,
        "footprint_area_m2": round(unbuf_m2, 1),
        "buffered_area_m2": round(buf_m2, 1),
        "buffer_area_gain_pct": round(100 * (buf_m2 / unbuf_m2 - 1), 1)
        if unbuf_m2 else None,
        "file_mb": round(dst.stat().st_size / 1e6, 2),
        "status": "written",
    })
    print(f"  {ykey}: burned {len(sel):,} structures -> {n_px:,} px "
          f"({dst.stat().st_size/1e6:.1f} MB, {time.time()-t0:.1f}s)")
    return row


# ── City-land denominator (for the sanity check) ─────────────────────────────
def city_land_px(grid: dict) -> tuple[int, np.ndarray]:
    """Pixels of the Edmonds city polygon on this grid.

    The city polygon is LAND: it is the municipal boundary, so Puget Sound is
    outside it. That makes it the right denominator for "what fraction of city
    land is roof".
    """
    city = gpd.read_file(CITY_SHP).to_crs(grid["crs"])
    arr = rasterize(((g, 1) for g in city.geometry.values),
                    out_shape=(grid["height"], grid["width"]),
                    transform=grid["transform"], fill=0, dtype="uint8")
    return int(arr.sum()), arr.astype(bool)


# ── Main ─────────────────────────────────────────────────────────────────────
def load_matrix(scope_files):
    frames = []
    for p in scope_files:
        if p.exists():
            frames.append(pd.read_parquet(
                p, columns=["building_id", "year", "verdict_final",
                            "verdict_rule", "disagreement"]))
            print(f"  matrix part: {p.name}  {len(frames[-1]):,} rows")
    if not frames:
        print("  NO presence matrix found — every year falls back to the "
              "assessor backbone alone (run qc/roof_presence_matrix.py)")
        return None
    m = pd.concat(frames, ignore_index=True)
    # citywide rows win over sector rows for the same (building_id, year)
    return m.drop_duplicates(["building_id", "year"], keep="first")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", default=None)
    ap.add_argument("--all-years", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--tmp-dir", default=r"D:\edmonds-pipeline\_tmp")
    args = ap.parse_args(argv)

    if args.all_years:
        from phase4seg import config as C
        years = [str(e["key"]) for e in C.YEAR_CATALOG]
    else:
        years = args.years or DEFAULT_YEARS

    grid = read_grid(GRID_RASTER)

    if not BUILDINGS_GPKG.exists():
        raise SystemExit(f"missing {BUILDINGS_GPKG}\n"
                         f"Run:  py -3.12 pipeline/build_buildings_layer.py")
    can = gpd.read_file(BUILDINGS_GPKG, layer="buildings")
    print(f"canonical buildings: {len(can):,}")
    can_w = can.to_crs(WORK_CRS)

    print("\nloading the presence matrix ...")
    # citywide first so it wins the drop_duplicates
    matrix = load_matrix([MATRIX_DIR / "roof_presence_matrix.parquet",
                          MATRIX_DIR / "roof_presence_matrix_sectors.parquet"])

    # the sanity denominator, built once
    print("\ncomputing the city-land denominator ...", flush=True)
    n_city, city_mask = city_land_px(grid)
    px_ground_m = grid["transform"].a / 1.487      # 3857 unit -> ground metre
    print(f"  city polygon: {n_city:,} px on this grid "
          f"({n_city*px_ground_m**2/1e4:.0f} ha of ground at "
          f"{px_ground_m:.2f} m/px)")

    print(f"\nbuilding {len(years)} masks -> {MASK_DIR}")
    rows = []
    for ykey in years:
        pres = presence_for_year(can, matrix, ykey)
        rows.append(burn_year(can_w, pres, grid, ykey, Path(args.tmp_dir),
                              args.overwrite, city_mask, n_city))

    man = pd.DataFrame(rows)
    MASK_DIR.mkdir(parents=True, exist_ok=True)
    # MERGE, never clobber: a run of `--years 2005` must not shrink a manifest
    # that already describes six masks sitting on disk beside it.
    if MANIFEST.exists():
        try:
            old = pd.read_csv(MANIFEST)
            keep = old[~old.year.astype(str).isin(set(man.year.astype(str)))]
            man_out = pd.concat([keep, man], ignore_index=True)
        except Exception as exc:
            print(f"  (existing manifest unreadable, replacing: {exc})")
            man_out = man
    else:
        man_out = man
    man_out["_k"] = man_out.year.astype(str).str[:4].astype(int)
    man_out = (man_out.sort_values(["_k", "year"])
                      .drop(columns="_k").reset_index(drop=True))
    man_out.to_csv(MANIFEST, index=False)
    print(f"\nwrote {MANIFEST}  ({len(man_out)} years described, "
          f"{len(man)} touched this run)")

    print("\n" + "=" * 78)
    print("MASK MANIFEST")
    print("=" * 78)
    cols = ["year", "n_burned", "n_present", "n_absent", "n_uncertain",
            "n_from_matrix", "mask_px_in_city", "pct_of_city_land",
            "pct_of_city_land_unbuffered", "buffer_area_gain_pct", "status"]
    print(man[[c for c in cols if c in man.columns]].to_string(index=False))

    print("\nSANITY — building-pixel fraction of city land, DECOMPOSED")
    print("  Reference: the ONEGEO footprints UNBUFFERED cover 14.83% of the")
    print("  city polygon (building_footprints/README_PROVENANCE.md, measured")
    print("  independently, on a different grid).")
    if "pct_of_city_land_unbuffered" in man.columns:
        u = man.pct_of_city_land_unbuffered.dropna()
        b = man.pct_of_city_land.dropna()
        if len(u) and len(b):
            print(f"  these masks, UNBUFFERED : "
                  f"{u.min():.2f}% - {u.max():.2f}%   <- compare to 14.83%")
            print(f"  these masks, +{BUFFER_M:.0f} m BUFFER: "
                  f"{b.min():.2f}% - {b.max():.2f}%")
            print(f"  the buffer alone accounts for "
                  f"+{b.max()-u.max():.2f} points; a median 185 m2 footprint")
            print("  grows ~25-30% in area at +1 m, so this is arithmetic, not error.")
    print("  The remaining spread across years is real: the masks drop")
    print("  structures the record says were not yet built, which pulls the")
    print("  early years down. Nothing here is tuned to hit a target band.")
    return 0, man


if __name__ == "__main__":
    filtered = clean_argv()
    rc, man = main(filtered)
    if write_step_log is not None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            write_step_log(script="make_building_masks", step="build",
                           logs_dir=LOGS_DIR, errors=0,
                           years=len(man),
                           mask_dir=str(MASK_DIR),
                           pct_city_land=", ".join(
                               f"{r.year}={r.pct_of_city_land}"
                               for r in man.itertuples()
                               if hasattr(r, "pct_of_city_land")))
        except Exception as exc:
            print(f"[masks] WARN could not write step log: {exc}")
    sys.exit(rc)
