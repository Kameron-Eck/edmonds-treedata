#!/usr/bin/env python3
"""
C-CAP-stratified tile sampler — draw a small, land-cover-representative set of
FIXED geographic tile locations to reuse across every sensor-year, so a
cross-sensor experiment runs on a fraction of the imagery without a spatial-crop
bias. C-CAP LOCATES only (never a label); the engine still labels from the 2020
mask. Torch-free, runs locally off the D: imagery mirror.

Design:
  • grid candidate points over the city (EPSG:26910, C-CAP's CRS);
  • stratum = C-CAP class; FOREST (code 11) is sub-stratified by 2016 NDVI (an
    NxN-pixel window mean) so the OOD-deciduous tail (low NDVI ~.35) is its own
    stratum, not lumped with conifer;
  • allocation GUARANTEES >=1 tile per nonzero stratum (so the area-adjustment is
    unbiased), then water-fills the remainder to exactly --n by weight with forest
    OVERSAMPLED (esp. low-NDVI), re-spreading any capped overflow;
  • each sampled tile carries an AREA WEIGHT (= candidates/sampled in its stratum)
    so city-wide estimates stay unbiased (Olofsson area-adjustment).

    py -3.12 phase4_ccap_sample.py --n 200 --out sample_xsensor.gpkg
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
import geopandas as gpd
from shapely.geometry import Point
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

MIRROR = Path(r"D:/edmonds-pipeline/Imagery")
CCAP = MIRROR / "ccap_2016_hires_lc.tif"
NIR_IMG = MIRROR / "2016_snoh_rgbi.tif"          # R,G,B,NIR — NDVI reference
FOREST_CODE = 11                                  # C-CAP hi-res Upland Forest
NIR_BAND = 4

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=200, help="total tiles to sample")
ap.add_argument("--grid-step-m", type=float, default=250.0, help="candidate grid spacing (m)")
ap.add_argument("--forest-oversample", type=float, default=3.0,
                help="multiply forest strata target vs proportional (excludes forest_nocover)")
ap.add_argument("--forest-lo-boost", type=float, default=2.0,
                help="extra multiplier on the low-NDVI (deciduous) forest stratum")
ap.add_argument("--ndvi-bins", default="0.40,0.55",
                help="forest NDVI cut points: lo<c0<=mid<c1<=hi")
ap.add_argument("--ndvi-window", type=int, default=3,
                help="odd NxN pixel window to average NDVI (stabilises the forest bin)")
ap.add_argument("--out", default="sample_ccap.gpkg", help="manifest path (.gpkg; .csv also written)")
ap.add_argument("--seed", type=int, default=42)
# Colab %run injects `-f <json>` — filter it (Rule 4) in case this is ever run there.
filtered = clean_argv()
args = ap.parse_args(filtered)

for p in (CCAP, NIR_IMG):
    if not p.exists():
        sys.exit(f"[FAILED] missing input: {p}")
rng = np.random.RandomState(args.seed)
lo_cut, hi_cut = (float(x) for x in args.ndvi_bins.split(","))
win = max(1, args.ndvi_window | 1)               # force odd

# ── 1. candidate grid + C-CAP class (open C-CAP once) ─────────────────────────
with rasterio.open(CCAP) as cc:
    b, cc_crs = cc.bounds, cc.crs
    step = args.grid_step_m
    xs = np.arange(b.left + step / 2, b.right, step)
    ys = np.arange(b.bottom + step / 2, b.top, step)
    pts = [(float(x), float(y)) for y in ys for x in xs]
    classes = np.array([v[0] for v in cc.sample(pts)], dtype=np.int32)
keep = classes > 0                                # 0 = C-CAP nodata / background
pts = [p for p, ok in zip(pts, keep) if ok]
classes = classes[keep]
print(f"[1/4] {len(pts):,} candidate points @ {step:.0f} m "
      f"({int((classes == FOREST_CODE).sum()):,} forest)")

# ── 2. NDVI (NxN window mean) at FOREST points → sub-stratum ───────────────────
strata = [None] * len(pts)
ndvi_arr = np.full(len(pts), np.nan)
f_idx = np.where(classes == FOREST_CODE)[0]
with rasterio.open(NIR_IMG) as nir:
    nd = nir.nodata
    resx, resy = nir.res
    if len(f_idx):
        rx, ry = rasterio.warp.transform(cc_crs, nir.crs,
                                         [pts[i][0] for i in f_idx],
                                         [pts[i][1] for i in f_idx])
        off = range(-(win // 2), win // 2 + 1)
        coords = [(x + dx * resx, y - dy * resy)
                  for x, y in zip(rx, ry) for dy in off for dx in off]
        samp = np.array([s for s in nir.sample(coords, indexes=[1, NIR_BAND])],
                        dtype=np.float32).reshape(len(f_idx), win * win, 2)
        red, nirv = samp[..., 0], samp[..., 1]
        cover = (red + nirv) > 0 if nd is None else ~((red == nd) & (nirv == nd))
        ndvi = (nirv - red) / (nirv + red + 1e-6)
        for k, i in enumerate(f_idx):
            m = cover[k]
            if not m.any():
                strata[i] = "forest_nocover"      # forest w/o NIR coverage
                continue
            v = float(ndvi[k][m].mean())
            ndvi_arr[i] = v
            strata[i] = ("forest_lo" if v < lo_cut
                         else "forest_hi" if v >= hi_cut else "forest_mid")
for i in np.where(classes != FOREST_CODE)[0]:
    strata[i] = f"ccap_{classes[i]}"
print(f"[2/4] strata set; forest NDVI split {lo_cut}/{hi_cut} on {win}x{win} windows "
      f"(lo=deciduous tail)")

stratum_idx = defaultdict(list)
for i, s in enumerate(strata):
    stratum_idx[s].append(i)
cand = {s: len(ix) for s, ix in stratum_idx.items()}

# ── 3. allocation: guarantee >=1 per stratum, then water-fill to exactly --n ───
def weight(s):
    w = float(cand[s])                            # proportional base
    if s.startswith("forest") and s != "forest_nocover":
        w *= args.forest_oversample               # oversample real forest sub-strata
    if s == "forest_lo":
        w *= args.forest_lo_boost                 # extra for the deciduous tail
    return w

weights = {s: weight(s) for s in cand}
alloc = {s: 0 for s in cand}
b_left = args.n
for s in sorted(cand, key=lambda s: -weights[s]):   # guarantee >=1, weight-priority
    if b_left <= 0:
        break
    if cand[s] > 0:
        alloc[s] = 1
        b_left -= 1
while b_left > 0:                                   # water-fill remainder by weight
    room = [s for s in cand if alloc[s] < cand[s]]
    if not room:
        break
    wsum = sum(weights[s] for s in room)
    given, rema = 0, []
    for s in room:
        want = b_left * weights[s] / wsum
        add = min(int(want), cand[s] - alloc[s])
        alloc[s] += add
        given += add
        rema.append((want - int(want), s))
    b_left -= given
    if given == 0:                                 # all fractional — largest-remainder
        for _, s in sorted(rema, reverse=True):
            if b_left <= 0:
                break
            if alloc[s] < cand[s]:
                alloc[s] += 1
                b_left -= 1
        if b_left > 0 and all(alloc[s] >= cand[s] for s in cand):
            break

# ── 4. draw + area weights + manifest (batch the final reprojection) ──────────
chosen = []                                        # (idx, stratum, area_weight)
for s in sorted(cand):
    take = alloc[s]
    aw = cand[s] / take if take else 0.0
    pick = rng.choice(stratum_idx[s], size=take, replace=False) if take else []
    chosen += [(int(i), s, aw) for i in pick]

lons, lats = rasterio.warp.transform(
    cc_crs, "EPSG:4326", [pts[i][0] for i, _, _ in chosen],
    [pts[i][1] for i, _, _ in chosen])
rows = [{"tile_id": f"{s}_{i}", "stratum": s, "ccap_class": int(classes[i]),
         "ndvi_2016": float(ndvi_arr[i]) if np.isfinite(ndvi_arr[i]) else None,
         "x_26910": pts[i][0], "y_26910": pts[i][1], "lon": lon, "lat": lat,
         "area_weight": round(aw, 3), "geometry": Point(lon, lat)}
        for (i, s, aw), lon, lat in zip(chosen, lons, lats)]
gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
out = Path(args.out)
gdf.to_file(out, driver="GPKG")
gdf.drop(columns="geometry").to_csv(out.with_suffix(".csv"), index=False)

# ── report + integrity checks ─────────────────────────────────────────────────
print(f"[4/4] sampled {len(gdf)} tiles (target {args.n}) -> {out.name} (+ .csv)")
print("\n  stratum         candidates  sampled  area_wt   (share of city)")
print("  " + "-" * 62)
tot = sum(cand.values())
for s in sorted(cand):
    n_s = alloc[s]
    aw = cand[s] / n_s if n_s else 0
    print(f"  {s:<15} {cand[s]:>10,} {n_s:>8}  {aw:>6.1f}   ({100 * cand[s] / tot:5.1f}%)")
f_city = 100 * sum(cand[s] for s in cand if s.startswith("forest")) / tot
f_samp = 100 * sum(alloc[s] for s in cand if s.startswith("forest")) / max(len(gdf), 1)
dropped = [s for s in cand if cand[s] > 0 and alloc[s] == 0]
print(f"\n  forest: {f_city:.1f}% of the city -> {f_samp:.1f}% of the sample "
      f"(oversampled {f_samp / max(f_city, 1e-6):.1f}x); area_weight restores the city proportion.")
if dropped:
    print(f"  WARNING: {len(dropped)} nonzero strata got 0 tiles (raise --n above the "
          f"stratum count to keep the estimate unbiased): {dropped}")
else:
    print("  every nonzero stratum has >=1 tile -> area-adjusted city estimate is unbiased.")
