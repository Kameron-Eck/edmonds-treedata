r"""build_sample_manifests.py — per-year tile manifests for the Tier-1 sample.

Converts the science sample's TRAIN + SELECTION regions into the fixed tile
locations each year trains on, emitted in the engine's --sample-manifest CSV
contract (lon/lat, EPSG:4326; tiling centres a TILE_SIZE tile on each point,
origin = point - TILE_SIZE/2 — tiling._origins_from_manifest).

THE CONTAINMENT RULE MADE CONCRETE: candidate origins are stride-grid positions
whose FULL tile footprint's four corners all fall inside the region polygon in
the year's own pixel space — so no training tile's ground can leak past a
region edge (the leakage ban the sample geometry was designed around;
build_science_sample.py header). Strides come from config.TIER_TILE_PARAMS at
import time — the same arithmetic as the sample builder's feasibility printout.

THE CAP (pre-registered): fine years explode (2020 @ 5 cm: 3,825 contained
positions); every year is capped at --cap (default 1200) by a SEEDED uniform
draw stratified proportionally across regions — recorded per-year in the
manifest header comment and the printout.

Output: {lake}/phase4/qc/sample_tiles_{year}.csv (lon,lat + provenance columns
the engine ignores). The manifest path is part of the tile signature
(path+size+mtime), so regenerating one re-tiles exactly the affected arms.
"""
import argparse

import numpy as np

from phase4seg.deps import ensure_deps as _ensure_deps
_ensure_deps([("rasterio", "rasterio"), ("pandas", "pandas"), ("shapely", "shapely")])

import pandas as pd
import rasterio
import rasterio.warp
from shapely.geometry import Polygon, Point, box as _box

from lake import BASE
from phase4seg import config as _cfg
from phase4seg.common import entry_for, resolve_native_path

SAMPLE_CSV = BASE / "phase4" / "qc" / "science_sample_manifest.csv"
OUT_DIR = BASE / "phase4" / "qc"
SAMPLE_YEARS = ["2006s", "2011s", "2016", "2020", "2019n"]
SEED = 42


def contained_origins(src, region_poly_native, stride_px):
    """Stride-grid origins whose full TILE_SIZE footprint sits inside the region
    polygon (in this ortho's pixel space). Exact corner-in-polygon test — the
    transformed region need not be axis-aligned in every CRS."""
    T = _cfg.TILE_SIZE
    inv = ~src.transform
    minx, miny, maxx, maxy = region_poly_native.bounds
    cs = [inv * (x, y) for x, y in ((minx, miny), (minx, maxy),
                                    (maxx, miny), (maxx, maxy))]
    c0 = max(0, int(min(c for c, r in cs)))
    c1 = min(src.width - T, int(max(c for c, r in cs)))
    r0 = max(0, int(min(r for c, r in cs)))
    r1 = min(src.height - T, int(max(r for c, r in cs)))
    out = []
    for ro in range(r0, r1 + 1, stride_px):
        for co in range(c0, c1 + 1, stride_px):
            ok = True
            for pr, pc in ((ro, co), (ro, co + T), (ro + T, co), (ro + T, co + T)):
                x, y = src.transform * (pc, pr)
                if not region_poly_native.contains(Point(x, y)):
                    ok = False
                    break
            if ok:
                out.append((ro, co))
    return out


def main():
    ap = argparse.ArgumentParser(description="Per-year Tier-1 tile manifests.")
    ap.add_argument("--cap", type=int, default=1200,
                    help="max tiles per year (seeded, region-proportional draw)")
    ap.add_argument("--years", nargs="+", default=SAMPLE_YEARS)
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)

    sm = pd.read_csv(SAMPLE_CSV)
    sm = sm[sm.role.isin(["train", "selection"])]
    epsg = int(sm.epsg.iloc[0])
    regions = [(r.block_id, _box(r.minx, r.miny, r.maxx, r.maxy))
               for r in sm.itertuples()]
    print(f"{len(regions)} regions (train+selection) from {SAMPLE_CSV.name}")

    for y in args.years:
        e = entry_for(y)
        tier = _cfg.tier_for(e)
        stride_px = _cfg.TIER_TILE_PARAMS[tier].get("stride", _cfg.TILE_SIZE)
        ortho = resolve_native_path(e)
        with rasterio.open(ortho) as src:
            per_region = []
            for bid, poly in regions:
                gj = rasterio.warp.transform_geom(
                    f"EPSG:{epsg}", src.crs, poly.__geo_interface__)
                native = Polygon(gj["coordinates"][0])
                origins = contained_origins(src, native, stride_px)
                per_region.append((bid, origins))
            total = sum(len(o) for _, o in per_region)
            keep = []
            for bid, origins in per_region:
                if total > args.cap:
                    n = max(1, int(round(args.cap * len(origins) / total)))
                    idx = rng.choice(len(origins), size=min(n, len(origins)),
                                     replace=False)
                    origins = [origins[i] for i in sorted(idx)]
                keep += [(bid, ro, co) for ro, co in origins]
            half = _cfg.TILE_SIZE // 2
            xs, ys = zip(*[(src.transform * (co + half, ro + half))
                           for _, ro, co in keep])
            lons, lats = rasterio.warp.transform(src.crs, "EPSG:4326",
                                                 list(xs), list(ys))
        out = OUT_DIR / f"sample_tiles_{y}.csv"
        pd.DataFrame(dict(
            lon=[round(v, 7) for v in lons], lat=[round(v, 7) for v in lats],
            block_id=[b for b, _, _ in keep],
            row_off=[r for _, r, _ in keep], col_off=[c for _, _, c in keep],
        )).to_csv(out, index=False)
        print(f"{y:<7} tier={tier:<7} stride={stride_px}px contained={total:>5} "
              f"kept={len(keep):>5} -> {out.name}")


if __name__ == "__main__":
    main()
