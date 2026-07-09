#!/usr/bin/env python3
"""
C-CAP-stratified tile sampler — draw a small, land-cover-representative set of
FIXED geographic tile locations to reuse across every sensor-year, so a
cross-sensor experiment runs on a fraction of the imagery without a spatial-crop
bias. C-CAP LOCATES only (never a label); the engine still labels from the 2020
mask. Torch-free, runs locally off the D: imagery mirror.

Design (per the plan):
  • grid candidate points over the city (EPSG:26910, C-CAP's CRS);
  • stratum = C-CAP class; FOREST (code 11) is sub-stratified by 2016 NDVI so the
    OOD-deciduous tail (low NDVI ~.35) is its own stratum, not lumped with conifer;
  • BALANCED allocation with forest OVERSAMPLED (esp. low-NDVI forest) — spend the
    budget where the signal is, not where the area is;
  • each sampled tile carries an AREA WEIGHT (= candidates/sampled in its stratum)
    so city-wide estimates stay unbiased (Olofsson area-adjustment).

Output: a manifest (CSV + GPKG) of tile-center points the engine will tile per year.

    py -3.12 phase4_ccap_sample.py --n 200 --out sample_xsensor.gpkg
"""
import argparse
import sys
from pathlib import Path

import numpy as np

# geo deps pip-install locally on import (same bootstrap as the QC scripts)
import rasterio
import rasterio.warp
import geopandas as gpd
from shapely.geometry import Point

MIRROR = Path(r"D:/edmonds-pipeline/Imagery")
CCAP = MIRROR / "ccap_2016_hires_lc.tif"
NIR_IMG = MIRROR / "2016_snoh_rgbi.tif"          # R,G,B,NIR — NDVI reference
FOREST_CODE = 11                                  # C-CAP hi-res Upland Forest
NIR_BAND = 4

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=200, help="total tiles to sample")
ap.add_argument("--grid-step-m", type=float, default=250.0, help="candidate grid spacing (m)")
ap.add_argument("--forest-oversample", type=float, default=3.0,
                help="multiply forest strata target vs proportional")
ap.add_argument("--forest-lo-boost", type=float, default=2.0,
                help="extra multiplier on the low-NDVI (deciduous) forest stratum")
ap.add_argument("--ndvi-bins", default="0.40,0.55",
                help="forest NDVI cut points: lo<c0<=mid<c1<=hi")
ap.add_argument("--out", default="sample_ccap.gpkg", help="manifest path (.gpkg; .csv also written)")
ap.add_argument("--seed", type=int, default=42)
args = ap.parse_args()

for p in (CCAP, NIR_IMG):
    if not p.exists():
        sys.exit(f"[FAILED] missing input: {p}")

rng = np.random.RandomState(args.seed)
lo_cut, hi_cut = (float(x) for x in args.ndvi_bins.split(","))

# ── 1. candidate grid over the C-CAP extent (26910) ───────────────────────────
with rasterio.open(CCAP) as cc:
    b = cc.bounds
    cc_crs = cc.crs
step = args.grid_step_m
xs = np.arange(b.left + step / 2, b.right, step)
ys = np.arange(b.bottom + step / 2, b.top, step)
pts = [(float(x), float(y)) for y in ys for x in xs]
print(f"[1/4] candidate grid: {len(pts):,} points @ {step:.0f} m over the C-CAP extent")

# ── 2. C-CAP class at each point (batch sample) ───────────────────────────────
with rasterio.open(CCAP) as cc:
    classes = np.array([v[0] for v in cc.sample(pts)], dtype=np.int32)
valid = classes > 0                                   # 0 = C-CAP nodata / background
pts = [p for p, ok in zip(pts, valid) if ok]
classes = classes[valid]
print(f"[2/4] {len(pts):,} points inside C-CAP coverage "
      f"({int((classes == FOREST_CODE).sum()):,} forest)")

# ── 3. NDVI at FOREST points only → sub-stratum ───────────────────────────────
strata = np.empty(len(pts), dtype=object)
ndvi_arr = np.full(len(pts), np.nan)
is_forest = classes == FOREST_CODE
with rasterio.open(NIR_IMG) as nir:
    nir_crs = nir.crs
    f_idx = np.where(is_forest)[0]
    if len(f_idx):
        fx = [pts[i][0] for i in f_idx]
        fy = [pts[i][1] for i in f_idx]
        rx, ry = rasterio.warp.transform(cc_crs, nir_crs, fx, fy)
        samp = np.array([s for s in nir.sample(list(zip(rx, ry)),
                                               indexes=[1, NIR_BAND])], dtype=np.float32)
        red, nirv = samp[:, 0], samp[:, 1]
        ndvi = (nirv - red) / (nirv + red + 1e-6)
        cover = (red + nirv) > 0                       # 0,0 = outside NIR ortho
        for k, i in enumerate(f_idx):
            if not cover[k]:
                strata[i] = "forest_nocover"           # forest w/o NIR coverage
                continue
            ndvi_arr[i] = ndvi[k]
            strata[i] = ("forest_lo" if ndvi[k] < lo_cut
                         else "forest_hi" if ndvi[k] >= hi_cut else "forest_mid")
for i in np.where(~is_forest)[0]:
    strata[i] = f"ccap_{classes[i]}"
print(f"[3/4] strata assigned; forest split at NDVI {lo_cut}/{hi_cut} "
      f"(lo=deciduous-tail)")

# ── 4. balanced-with-forest-oversampled allocation + area weights ─────────────
uniq, counts = np.unique(strata, return_counts=True)
cand = dict(zip(uniq.tolist(), counts.tolist()))

def weight(s):
    w = cand[s]                                        # proportional base
    if s.startswith("forest"):
        w *= args.forest_oversample
    if s == "forest_lo":
        w *= args.forest_lo_boost                      # extra for the deciduous tail
    return w

wsum = sum(weight(s) for s in cand)
alloc = {s: min(cand[s], int(round(args.n * weight(s) / wsum))) for s in cand}

rows = []
for s in sorted(cand):
    idx = np.where(strata == s)[0]
    take = min(alloc[s], len(idx))
    chosen = rng.choice(idx, size=take, replace=False) if take else []
    aw = cand[s] / take if take else 0.0               # each tile stands for this many candidates
    for i in chosen:
        x, y = pts[i]
        lon, lat = rasterio.warp.transform(cc_crs, "EPSG:4326", [x], [y])
        rows.append({"tile_id": f"{s}_{i}", "stratum": s, "ccap_class": int(classes[i]),
                     "ndvi_2016": float(ndvi_arr[i]) if np.isfinite(ndvi_arr[i]) else None,
                     "x_26910": x, "y_26910": y, "lon": lon[0], "lat": lat[0],
                     "area_weight": round(aw, 3),
                     "geometry": Point(lon[0], lat[0])})

gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
out = Path(args.out)
gdf.to_file(out, driver="GPKG")
gdf.drop(columns="geometry").to_csv(out.with_suffix(".csv"), index=False)

print(f"[4/4] sampled {len(gdf)} tiles -> {out.name} (+ .csv)")
print("\n  stratum        candidates  sampled  area_wt   (share of city)")
print("  " + "-" * 62)
tot = sum(cand.values())
for s in sorted(cand):
    n_s = int((gdf["stratum"] == s).sum())
    aw = cand[s] / n_s if n_s else 0
    print(f"  {s:<14} {cand[s]:>10,} {n_s:>8}  {aw:>6.1f}   ({100*cand[s]/tot:5.1f}%)")
f_share_city = 100 * sum(cand[s] for s in cand if s.startswith("forest")) / tot
f_share_samp = 100 * int(gdf["stratum"].str.startswith("forest").sum()) / max(len(gdf), 1)
print(f"\n  forest: {f_share_city:.1f}% of the city -> {f_share_samp:.1f}% of the sample "
      f"(oversampled {f_share_samp / max(f_share_city, 1e-6):.1f}x). "
      f"area_weight restores the city proportion for unbiased estimates.")
