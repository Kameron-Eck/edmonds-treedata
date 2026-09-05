"""Item 6 — cached 2 m trend8 stack + invalid-transition census.

One pass: warp all 8 trend8 masks onto the common 2 m city grid (majority
rule, the trend8_harmonized_fractions convention), cache as a compressed
npz (the I/O amortizer every later trajectory pass reuses), and census the
label trajectories: a pixel's 8-year sequence is classified STABLE /
MONOTONE (one transition) / FLICKER (>=2 transitions, incl. the impossible
canopy->gone->canopy triple). The FLICKER share is the trajectory family's
error-isolation headline; crown-level aggregation comes next and reuses
the same cache.

Outputs: D:\edmonds-pipeline\trend8_stack_2m.npz (local cache, NOT the lake)
         phase4/qc/trend8_transition_census.csv
"""
import csv
import io
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features as rfeat
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from affine import Affine

from lake import BASE

MASKS = BASE / "phase4" / "masks"
CITY = BASE / "City Boundry" / "Edmonds Boundry.shp"
CACHE = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")
OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "trend8_transition_census.csv"
YEARS = ("2009", "2011s", "2013", "2015", "2016", "2019", "2021", "2024")
CELL, EPSG = 2.0, 26910


def main():
    import geopandas as gpd
    city = gpd.read_file(CITY).to_crs(EPSG)
    minx, miny, maxx, maxy = city.total_bounds
    tf = Affine(CELL, 0, float(np.floor(minx)), 0, -CELL, float(np.ceil(maxy)))
    w = int(np.ceil((maxx - minx) / CELL)) + 1
    h = int(np.ceil((maxy - miny) / CELL)) + 1
    inside = rfeat.rasterize(((g, 1) for g in city.geometry), out_shape=(h, w),
                             transform=tf, fill=0, dtype="uint8").astype(bool)
    layers = []
    for y in YEARS:
        p = MASKS / f"edmonds_canopy_mask_{y}_trend8_{y}.tif"
        with rasterio.open(p) as src:
            with WarpedVRT(src, crs=f"EPSG:{EPSG}", transform=tf, width=w,
                           height=h, resampling=Resampling.average,
                           src_nodata=255, nodata=float("nan"),
                           dtype="float32") as v:
                a = v.read(1)
        lay = np.full((h, w), 255, np.uint8)
        fin = np.isfinite(a)
        lay[fin & (a >= 0.5)] = 1
        lay[fin & (a < 0.5)] = 0
        layers.append(lay)
        print(f"  {y} cached", flush=True)
    stack = np.stack(layers)              # (8, h, w) uint8 0/1/255
    np.savez_compressed(CACHE, stack=stack, inside=inside,
                        years=np.array(YEARS), transform=np.array(tf)[:6])
    print(f"cache -> {CACHE} ({CACHE.stat().st_size/1e6:.0f} MB)")

    ok = inside & (stack != 255).all(axis=0)
    s = stack[:, ok].astype(np.int8)      # (8, N) of 0/1
    trans = (np.abs(np.diff(s, axis=0)) > 0).sum(axis=0)
    ever = s.any(axis=0)
    n = s.shape[1]
    stable = int((trans == 0).sum())
    mono = int((trans == 1).sum())
    flick = int((trans >= 2).sum())
    pap = int(((np.diff(s, axis=0) != 0).sum(axis=0) >= 2) .sum())  # same as flick
    # canopy->gone->canopy specifically
    has_101 = np.zeros(n, bool)
    for i in range(6):
        has_101 |= (s[i] == 1) & (s[i + 1] == 0) & (s[i + 2:] == 1).any(axis=0)
    rows = [
        ("all_city_px", n, 1.0, ""),
        ("stable_0_transitions", stable, stable / n, ""),
        ("monotone_1_transition", mono, mono / n, "real single change OR one bad year"),
        ("flicker_2plus", flick, flick / n, "trajectory family's target"),
        ("canopy_gone_canopy", int(has_101.sum()), float(has_101.mean()),
         "impossible triple (trees do not resurrect)"),
        ("ever_canopy_px", int(ever.sum()), float(ever.mean()), ""),
        ("flicker_share_of_ever_canopy",
         int((trans[ever] >= 2).sum()),
         float((trans[ever] >= 2).mean()), "the paper ratio"),
    ]
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(["quantity", "px", "frac", "note"])
        wcsv.writerows(rows)
    for r in rows:
        print(f"  {r[0]:32s} {r[1]:>12,}  {100*r[2]:6.2f}%  {r[3]}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
