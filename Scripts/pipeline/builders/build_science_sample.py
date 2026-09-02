r"""build_science_sample.py — THE permanent Tier-1 science sample (plan of record:
TIER1_SCIENCE_SAMPLE_PLAN_2026-09-02.md; matrix: experiments/tier1_science_sample.yaml).

Produces the fixed ground geometry every Tier-1 arm trains/validates/tests on:

  TRAIN regions     contiguous rectangles (~10-12% of the city together) — training
                    needs TILE MASS, and a 512-px tile spans 512 m on 2006s (100 cm),
                    so scattered small blocks would yield ZERO complete coarse tiles
                    (the measured object-ratio spread, 33-745 m per tile).
  SELECTION region  one contiguous region — early-stop validation tiles AND the
                    policy-C threshold sweep live here, never on test ground.
  TEST blocks       scattered 250 m blocks, stratified — the paired scoring units.
                    Scoring is per-pixel on the prob raster, so block size is
                    GSD-free; many independent blocks is what the statistics need.

  BUFFER RULE: every eval geometry sits >= BUFFER_M from any train region edge —
  wider than the coarsest tile footprint + inference pad, so no training tile's
  ground ever overlaps evaluation ground (the spatial-leakage ban, CLAUDE.md 3.5).

SCREENS (why each exists):
  - both-epochs lidar: chm2005 AND chm2_2016 valid. Both-epochs coverage is only
    ~44.3% of the grid (build_lidar_quadrants.py header) — without this screen the
    lidar arms of tier1 train blind on missing channel/labels.
  - land: C-CAP non-water/non-ignore fraction >= LAND_MIN per cell.
  - strata: C-CAP forest fraction bins cells into forest / mixed / low so the
    sample spans the canopy gradient instead of oversampling forest.
  NOT screened here (recorded in the plan doc): per-block radiometry (checked as a
  sample-level representativeness REPORT, not a filter) and coregistration (the
  measured table is per-acquisition, not spatial — applies globally as a caveat).

OUTPUTS (lake phase4/qc/):
  science_sample_blocks.gpkg     layers: one geometry per feature; columns
                                 block_id, role {train,selection,test}, stratum
  science_sample_manifest.csv    same rows flat + per-cell screen metrics
  stdout                          tiles-per-year-per-split table — the Phase-0 gate
                                 that decides whether 2020 (5 cm) stays feasible.

Deterministic: seeded selection, fixed grid origin. Local rasters first, lake
fallback. Zero GPU. Idempotent: re-running overwrites the two outputs.
"""
import argparse
from pathlib import Path

import numpy as np

from phase4seg.deps import ensure_deps as _ensure_deps
_ensure_deps([("rasterio", "rasterio"), ("geopandas", "geopandas"),
              ("shapely", "shapely"), ("pandas", "pandas")])

import geopandas as gpd
import pandas as pd
import rasterio
import rasterio.warp
from rasterio.enums import Resampling
from shapely.geometry import box

from lake import BASE
from phase4seg import config as _cfg

GRID_EPSG = int(getattr(_cfg, "ANALYSIS_GRID_EPSG", 26910))
CELL_M = 250                      # test-block edge; also the screening grid cell
# THE CONTAINMENT RULE (this is what makes the geometry fit a 19 km2 city):
# Phase A keeps only tiles whose FULL FOOTPRINT lies inside their train/selection
# region — so train ground can never leak past a region edge, and the required
# train-to-eval separation collapses from a 512 m tile-footprint buffer (which a
# first run measured blanketing the whole city: 0 train regions survived) to a
# small safety margin. Cost, stated honestly: coarse years lose edge positions,
# so regions must be >= ~1.25 km for 2006s (512 m tiles) to fit a usable grid.
BUFFER_M = 100
LAND_MIN = 0.90
FOREST_HI, FOREST_LO = 0.50, 0.15
# Proportional-with-floors test allocation. The city's eligible cells are ~76%
# "mixed" (measured by this builder's own first dry-run: forest 30 / mixed 187 /
# low 29 of 246) — equal strata are unreachable AND unrepresentative. Scarce
# strata get RESERVED FIRST, before train regions claim ground.
TEST_WANT = {"forest": 8, "mixed": 14, "low": 8}
SEED = 42

# C-CAP groups (mirror of phase4_qc_indep.CCAP_DEFAULT — forest+wetland = canopy ref)
CANOPY_CODES = {9, 10, 11, 13, 16}
IGNORE_CODES = {0, 1, 24, 25}
WATER_CODES = {21, 22, 23}


def _first_existing(*cands):
    for c in cands:
        p = Path(c)
        if p.exists():
            return p
    raise FileNotFoundError(f"none of {[str(c) for c in cands]} exist")


LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
CCAP = _first_existing(LOCAL_IMG / "ccap_2021_hires_lc.tif",
                       BASE / "Full_Image" / "Pipeline Imagery" / "ccap_2021_hires_lc.tif")
CHM05 = _first_existing(LOCAL_IMG / "lidar_chm2005_2m.tif",
                        BASE / "Full_Image" / "Pipeline Imagery" / "lidar_chm2005_2m.tif")
CHM16 = _first_existing(LOCAL_IMG / "lidar_chm2_2016_50cm.tif",
                        BASE / "Full_Image" / "Pipeline Imagery" / "lidar_chm2_2016_50cm.tif")
CITY = _first_existing(BASE / "City Boundry" / "Edmonds Boundry.shp")

OUT_GPKG = BASE / "phase4" / "qc" / "science_sample_blocks.gpkg"
OUT_CSV = BASE / "phase4" / "qc" / "science_sample_manifest.csv"

# tiles-per-split arithmetic inputs: (year, gsd_cm, tier stride px) — strides from
# config.TIER_TILE_PARAMS at import time so the printout can never drift from code.
SAMPLE_YEARS = ["2006s", "2011s", "2016", "2020", "2019n"]


def cell_fraction(src_path, cells_gdf, classify, dec_to=2500):
    """Per-cell fraction via one decimated warp of the raster onto the 26910 grid.
    `classify(arr) -> bool array`. Decimated (~10 m px) is plenty for 250 m cells."""
    with rasterio.open(src_path) as src:
        minx, miny, maxx, maxy = cells_gdf.total_bounds
        res = max((maxx - minx), (maxy - miny)) / dec_to
        w = int(np.ceil((maxx - minx) / res))
        h = int(np.ceil((maxy - miny) / res))
        tf = rasterio.transform.from_origin(minx, maxy, res, res)
        dst = np.full((h, w), 255, dtype=np.uint8)
        rasterio.warp.reproject(
            rasterio.band(src, 1), dst, dst_transform=tf,
            dst_crs=f"EPSG:{GRID_EPSG}", dst_nodata=255,
            resampling=Resampling.nearest)
    good = classify(dst)
    valid = dst != 255
    fr = []
    for geom in cells_gdf.geometry:
        gx0, gy0, gx1, gy1 = geom.bounds
        c0, c1 = int((gx0 - minx) / res), int(np.ceil((gx1 - minx) / res))
        r0, r1 = int((maxy - gy1) / res), int(np.ceil((maxy - gy0) / res))
        v = valid[r0:r1, c0:c1]
        g = good[r0:r1, c0:c1]
        fr.append(float(g.sum()) / max(int(v.sum()), 1) if v.any() else 0.0)
    return np.array(fr), [float(valid[int((maxy - g.bounds[3]) / res):int(np.ceil((maxy - g.bounds[1]) / res)),
                                       int((g.bounds[0] - minx) / res):int(np.ceil((g.bounds[2] - minx) / res))].mean())
                          for g in cells_gdf.geometry]


def spread_pick(cands, n, rng):
    """Greedy max-min-distance pick of n rows from a candidate GeoDataFrame."""
    if len(cands) <= n:
        return list(cands.index)
    idx = [rng.choice(cands.index)]
    cx = cands.geometry.centroid
    while len(idx) < n:
        d = np.min([cx.distance(cx.loc[i]) for i in idx], axis=0)
        d = pd.Series(d, index=cands.index)
        d[idx] = -1
        idx.append(d.idxmax())
    return idx


def main():
    ap = argparse.ArgumentParser(description="Build the Tier-1 science sample geometry.")
    ap.add_argument("--train-frac", type=float, default=0.11,
                    help="target train-region fraction of the city (default 0.11)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)

    city = gpd.read_file(CITY).to_crs(epsg=GRID_EPSG)
    city_geom = city.union_all()
    minx, miny, maxx, maxy = city_geom.bounds
    x0, y0 = np.floor(minx / CELL_M) * CELL_M, np.floor(miny / CELL_M) * CELL_M

    cells = []
    for gx in np.arange(x0, maxx, CELL_M):
        for gy in np.arange(y0, maxy, CELL_M):
            g = box(gx, gy, gx + CELL_M, gy + CELL_M)
            if g.intersection(city_geom).area / g.area >= 0.99:
                cells.append(g)
    cells = gpd.GeoDataFrame(geometry=cells, crs=f"EPSG:{GRID_EPSG}")
    print(f"grid: {len(cells)} full {CELL_M} m cells inside the city "
          f"({len(cells) * CELL_M**2 / 1e6:.1f} km2)")

    canopy_fr, _ = cell_fraction(CCAP, cells, lambda a: np.isin(a, list(CANOPY_CODES)))
    land_fr, _ = cell_fraction(
        CCAP, cells, lambda a: ~np.isin(a, list(WATER_CODES | IGNORE_CODES)) & (a != 255))
    chm05_fr, _ = cell_fraction(CHM05, cells, lambda a: a != 255)
    chm16_fr, _ = cell_fraction(CHM16, cells, lambda a: a != 255)
    cells["canopy_fr"] = canopy_fr
    cells["land_fr"] = land_fr
    cells["chm_both_fr"] = np.minimum(chm05_fr, chm16_fr)
    cells["stratum"] = np.where(canopy_fr >= FOREST_HI, "forest",
                                np.where(canopy_fr >= FOREST_LO, "mixed", "low"))
    cells["eligible"] = (cells.land_fr >= LAND_MIN) & (cells.chm_both_fr >= 0.95)
    el = cells[cells.eligible]
    print(f"eligible (land>={LAND_MIN}, BOTH-epoch lidar): {len(el)}/{len(cells)} cells")
    for s in ("forest", "mixed", "low"):
        print(f"  {s:<7} {int((el.stratum == s).sum())}")
    if len(el) < sum(TEST_WANT.values()) + 20:
        raise SystemExit("NOT ENOUGH ELIGIBLE CELLS — screens too tight; inspect "
                         "the per-stratum counts above before relaxing anything.")

    # STARVATION GUARD (successor to the first two designs, both measured
    # failing: greedy-train-first left 1 forest + 1 low test candidate;
    # scatter-reserve-first fragmented the city so no selection region fit).
    # Regions are placed first for contiguity, but any region that would drop a
    # scarce stratum's surviving candidates below its test quota is REJECTED.
    def survivors(stratum, boxes):
        away = [b.buffer(BUFFER_M) for b in boxes]
        sub = el[el.stratum == stratum]
        return int(sum(all(not g.intersects(a) for a in away) for g in sub.geometry))

    def starves(boxes):
        return any(survivors(s, boxes) < TEST_WANT[s] + 2 for s in ("forest", "low"))

    # TRAIN regions: n x n cell anchors (5x5 = 1.25 km first, then 4x4), scored
    # by eligible content + strata diversity, packed until the target fraction —
    # never inside a reserved-test buffer. Regions must hold full coarse tiles
    # (containment rule above), hence the >= 1 km sizes.
    target_cells = int(args.train_frac * len(cells))
    el_set = set(map(tuple, np.round(np.array(
        [g.bounds[:2] for g in el.geometry])).astype(int)))

    def anchors_of(n):
        out = []
        need = int(np.ceil(0.85 * n * n))
        for gx in np.arange(x0, maxx, CELL_M):
            for gy in np.arange(y0, maxy, CELL_M):
                blk = [(int(gx + i * CELL_M), int(gy + j * CELL_M))
                       for i in range(n) for j in range(n)]
                n_el = sum(b in el_set for b in blk)
                if n_el >= need:
                    sub = el[[tuple(np.round(g.bounds[:2]).astype(int)) in set(blk)
                              for g in el.geometry]]
                    out.append((n_el + 2 * sub.stratum.nunique(), gx, gy, n))
        out.sort(reverse=True)
        return out

    train_boxes, got = [], 0
    for size in (5, 4, 4, 3):
        if got >= target_cells:
            break
        for sc, gx, gy, n in anchors_of(size):
            b = box(gx, gy, gx + n * CELL_M, gy + n * CELL_M)
            if any(b.buffer(BUFFER_M).intersects(t) for t in train_boxes):
                continue
            if starves(train_boxes + [b]):
                continue                         # would eat a scarce stratum's quota
            train_boxes.append(b)
            got += n * n
            break                                # one box per size step, re-rank
    print(f"train regions: {len(train_boxes)} "
          f"({got * CELL_M**2 / 1e6:.1f} km2, {100 * got / len(cells):.1f}% of city)")

    # SELECTION region: 4x4 (1 km) so coarse val tiles fit under containment.
    sel_box = None
    for sc, gx, gy, n in anchors_of(4):
        b = box(gx, gy, gx + n * CELL_M, gy + n * CELL_M)
        if any(b.buffer(BUFFER_M).intersects(t) for t in train_boxes):
            continue
        if starves(train_boxes + [b]):
            continue
        sel_box = b
        break
    if sel_box is None:
        raise SystemExit("no selection region clears the buffer — inspect anchors")

    # TEST blocks last, from everything the regions left standing.
    keep_away = [b.buffer(BUFFER_M) for b in train_boxes + [sel_box]]
    free = el[[all(not g.intersects(k) for k in keep_away) for g in el.geometry]]
    test_idx = []
    for s in ("forest", "low", "mixed"):
        cand = free[free.stratum == s]
        take = min(TEST_WANT[s], len(cand))
        if take < TEST_WANT[s]:
            print(f"  WARNING stratum {s}: only {take} candidates clear the screens")
        test_idx += spread_pick(cand, take, rng)
    test = cells.loc[test_idx]
    print(f"test blocks: {len(test)} across strata "
          f"{dict(test.stratum.value_counts())}")

    # tiles-per-year-per-split — THE PHASE-0 GATE printout, under CONTAINMENT:
    # positions per region axis = floor((L - tile_footprint)/stride) + 1, zero
    # when the region cannot hold one full tile.
    def contained_positions(boxes, stride_m, tile_m):
        n = 0
        for b in boxes:
            lx = b.bounds[2] - b.bounds[0]
            ly = b.bounds[3] - b.bounds[1]
            if lx < tile_m or ly < tile_m:
                continue
            n += (int((lx - tile_m) / stride_m) + 1) * (int((ly - tile_m) / stride_m) + 1)
        return n

    print("\ntiles per split (full-containment positions; the feasibility gate):")
    print(f"{'year':<8}{'gsd':>6}{'tier':>8}{'tile_m':>8}{'stride_m':>10}{'train':>8}{'sel':>6}")
    for y in SAMPLE_YEARS:
        e = _cfg.entry_for(y) if hasattr(_cfg, "entry_for") else \
            next(x for x in _cfg.YEAR_CATALOG if x["label"] == y)
        tier = _cfg.tier_for(e)
        stride_px = _cfg.TIER_TILE_PARAMS[tier].get("stride", _cfg.TILE_SIZE)
        stride_m = stride_px * e["gsd_cm"] / 100.0
        tile_m = _cfg.TILE_SIZE * e["gsd_cm"] / 100.0
        n_tr = contained_positions(train_boxes, stride_m, tile_m)
        n_se = contained_positions([sel_box], stride_m, tile_m)
        flag = "  <-- ZERO" if (n_tr == 0 or n_se == 0) else ""
        print(f"{y:<8}{e['gsd_cm']:>6.0f}{tier:>8}{tile_m:>8.0f}{stride_m:>10.1f}"
              f"{n_tr:>8}{n_se:>6}{flag}")

    if args.dry_run:
        print("\ndry run — nothing written")
        return

    rows = []
    feats = []
    for i, b in enumerate(train_boxes):
        feats.append(dict(block_id=f"TR{i:02d}", role="train", stratum="", geometry=b))
    feats.append(dict(block_id="SE00", role="selection", stratum="", geometry=sel_box))
    for j, (i, r) in enumerate(test.iterrows()):
        feats.append(dict(block_id=f"TE{j:02d}", role="test", stratum=r.stratum,
                          geometry=r.geometry))
    out = gpd.GeoDataFrame(feats, crs=f"EPSG:{GRID_EPSG}")
    OUT_GPKG.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(OUT_GPKG, driver="GPKG", layer="science_sample")
    for f in feats:
        g = f["geometry"]
        rows.append(dict(block_id=f["block_id"], role=f["role"], stratum=f["stratum"],
                         minx=round(g.bounds[0], 1), miny=round(g.bounds[1], 1),
                         maxx=round(g.bounds[2], 1), maxy=round(g.bounds[3], 1),
                         area_ha=round(g.area / 1e4, 2), epsg=GRID_EPSG))
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_GPKG.name} + {OUT_CSV.name} ({len(rows)} features)")


if __name__ == "__main__":
    main()
