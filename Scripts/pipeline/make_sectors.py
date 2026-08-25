r"""Training sectors — fixed west-east inference/testing strips (sector program, 2026-08-24).

WHY. Full-city inference per iteration is unjustified (Kam). A west-east band crosses the full
shore->upland gradient in one pass (Edmonds' terrain flows west to the Sound); several bands at
different latitudes stratify the north-south axis; holding the geometry FIXED across years makes
every year-over-year comparison happen on identical ground. Sectors are the unit of the
sector-restricted inference (`--infer-aoi`), the design-based city canopy totals, and the A/B
machinery-testing harness.

GEOMETRY. Anchored to the 2020 anchor tile lattice (the same one the site snap-grid uses):
origin (-13625893.973200373, 6084272.795957603) EPSG:3857, px 0.07464553543473991, tile 512 px
= 38.2185 m, block 4x4 tiles = 152.874 m. Each sector = `--rows-per-sector` whole block-rows
tall (default 3 = 458.62 m), spanning every block-col that intersects the city polygon in that
band, plus a westward water extension: `ceil(--water-ext-m / block)` block-cols where >=50% of
the cell is waterbody (bathology layer) — Kam: "we need some water in the training data".

PLACEMENT. Even N-S stratification into `--n-sectors` bands, then an exhaustive shift search
(each sector may move +/-1 block-row) with a lexicographic objective: (1) most training sites
fully contained, (2) most partially covered, (3) smallest total shift. Deterministic.

GRADIENT ATTRIBUTES. There is NO terrain DEM anywhere in the data plane (the crowns' dtm_* are
distance transforms, not elevation — see the 2026-08-24 exploration). The gradient is recorded
as distance-to-shore stats + C-CAP class composition per sector instead.

OUTPUTS
  repo:  pipeline/aoi/{version}.json          (committed — the engine + VMs read this)
  data:  phase4/qc/sectors/{version}.gpkg     (layers: sectors, sector_bounds) + overview PNG
         + README.txt
  copy:  D:\edmonds-pipeline\ARCGIS\MachineLearning\sectors\   (Kam's review set)

One-shot writer; idempotent (overwrites its own outputs only).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[0].parent
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_measure as im  # noqa: E402   (CITY_SHP local-first)

# the anchor lattice (identical to scratch/make_site_grid.py)
ORIGIN_X = -13625893.973200373
ORIGIN_Y = 6084272.795957603
PX = 0.07464553543473991
TILE = 512
BLOCK = 4
BLOCK_M = BLOCK * TILE * PX          # 152.8740565…
CRS = "EPSG:3857"
COS_LAT = float(np.cos(np.radians(47.81)))   # 3857 -> ground scale at Edmonds

DATA = Path(r"G:\My Drive\treedata")
WATER_SHP = DATA / "bathology" / "GDBA_HYDROGRAPHY__waterbody_snoco.shp"
PHOTOS = DATA / "photos"
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
CROWNS_FALLBACK = DATA / "inference" / "edmonds_crowns_2020.gpkg"
ARCGIS_OUT = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\sectors")

# C-CAP groups — same grouping the honest scorer uses (qc/phase4_qc_indep.py CCAP_DEFAULT)
CCAP_GROUPS = {"forest": [9, 10, 11], "wetland": [13, 16], "emergent_wetland": [15, 18],
               "grass": [8], "developed": [2, 3, 4, 5], "bare": [7, 19, 20],
               "water": [21, 22, 23], "ignore": [0, 1, 24, 25]}


def _ccap_path(name):
    for root in (Path(r"D:\edmonds-pipeline\Imagery"), DATA / "Full_Image" / "Pipeline Imagery"):
        p = root / name
        if p.exists():
            return p
    return None


def site_footprints():
    """label -> bounds(3857) for every photos/*_rgb.tif (header-only reads)."""
    import rasterio
    from rasterio.warp import transform_bounds
    out = {}
    for p in sorted(PHOTOS.glob("*_rgb.tif")):
        with rasterio.open(p) as ds:
            b = ds.bounds
            if ds.crs and ds.crs.to_epsg() != 3857:
                b = transform_bounds(ds.crs, CRS, *b)
        out[p.stem[:-4]] = tuple(b)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sectors", type=int, default=5)
    ap.add_argument("--rows-per-sector", type=int, default=3)
    ap.add_argument("--water-ext-m", type=float, default=150.0)
    ap.add_argument("--version", default="sectors_v1")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    import geopandas as gpd
    import rasterio
    from rasterio.warp import transform_bounds
    from shapely.geometry import box
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    city = gpd.read_file(im.CITY_SHP).to_crs(CRS)
    city_poly = city.union_all() if hasattr(city, "union_all") else city.unary_union
    water = gpd.read_file(WATER_SHP)
    water = water[water.geometry.notna() & water.is_valid]
    # clip to the city neighbourhood before the union — the layer is county-wide
    minx, miny, maxx, maxy = city_poly.buffer(2000).bounds
    water = water.cx[minx:maxx, miny:maxy]
    water_u = unary_union(list(water.geometry))
    print(f"city {city_poly.area/1e6:.1f} km2(3857); water features near city: {len(water)}")

    sites = site_footprints()
    print(f"{len(sites)} site footprints: {sorted(sites)}")

    # block-row range intersecting the city
    r_lo = int(np.floor((ORIGIN_Y - city_poly.bounds[3]) / BLOCK_M))
    r_hi = int(np.ceil((ORIGIN_Y - city_poly.bounds[1]) / BLOCK_M))
    n_rows = r_hi - r_lo
    assert 80 <= n_rows <= 100, f"unexpected city block-row count {n_rows}"
    print(f"city block-rows: [{r_lo}, {r_hi}) = {n_rows}")

    L, rows = a.n_sectors, a.rows_per_sector

    def band_rows(h):
        return r_lo + int(round((h + 0.5) * n_rows / L - rows / 2))

    def sector_y(s):
        y1 = ORIGIN_Y - s * BLOCK_M
        return y1 - rows * BLOCK_M, y1          # (y0, y1)

    def sites_in(s):
        y0, y1 = sector_y(s)
        full = [n for n, b in sites.items() if b[1] >= y0 and b[3] <= y1]
        part = [n for n, b in sites.items() if n not in full and b[3] > y0 and b[1] < y1]
        return full, part

    # exhaustive shift search (L small: 3^L combos)
    from itertools import product
    best = None
    for deltas in product((-1, 0, 1), repeat=L):
        starts = [band_rows(h) + d for h, d in zip(range(L), deltas)]
        if any(starts[i + 1] <= starts[i] + rows for i in range(L - 1)):
            continue                             # keep sectors disjoint and ordered
        nf = sum(len(sites_in(s)[0]) for s in starts)
        np_ = sum(len(sites_in(s)[1]) for s in starts)
        score = (nf, np_, -sum(abs(d) for d in deltas))
        if best is None or score > best[0]:
            best = (score, starts, deltas)
    (nf, np_, negshift), starts, deltas = best
    print(f"placement: starts {starts} (shifts {list(deltas)}) — "
          f"{nf} sites fully contained, {np_} partial")

    # per-sector geometry + attributes
    ccap = {}
    for tag, name in (("ccap_2021", "ccap_2021_hires_lc.tif"), ("ccap_2016", "ccap_2016_hires_lc.tif")):
        p = _ccap_path(name)
        if p:
            ccap[tag] = p
    crowns_path = CROWNS if CROWNS.exists() else CROWNS_FALLBACK
    crowns = gpd.read_file(crowns_path, columns=["crown_id"], engine="pyogrio")
    crown_tree = STRtree(crowns.geometry.values)
    shore = water_u.boundary

    ext_cols = int(np.ceil(a.water_ext_m / BLOCK_M))
    sectors, bounds_rows = [], []
    for i, s in enumerate(starts):
        y0, y1 = sector_y(s)
        band = box(city_poly.bounds[0] - 1, y0, city_poly.bounds[2] + 1, y1)
        strip_city = band.intersection(city_poly)
        c_lo = int(np.floor((strip_city.bounds[0] - ORIGIN_X) / BLOCK_M))
        c_hi = int(np.ceil((strip_city.bounds[2] - ORIGIN_X) / BLOCK_M))
        base = box(ORIGIN_X + c_lo * BLOCK_M, y0, ORIGIN_X + c_hi * BLOCK_M, y1)
        # westward water extension: keep candidate cells that are >=50% waterbody
        kept_water = []
        for cc_ in range(c_lo - ext_cols, c_lo):
            cell = box(ORIGIN_X + cc_ * BLOCK_M, y0, ORIGIN_X + (cc_ + 1) * BLOCK_M, y1)
            frac = cell.intersection(water_u).area / cell.area
            if frac >= 0.5:
                kept_water.append(cell)
        poly = unary_union([base] + kept_water)
        b = poly.bounds
        land = poly.intersection(city_poly).difference(water_u)
        wfrac = poly.intersection(water_u).area / poly.area
        full, part = sites_in(s)
        n_crowns = len(crown_tree.query(poly, predicate="intersects"))
        # distance-to-shore stats from land block centroids
        dists = []
        for cc_ in range(c_lo, c_hi):
            cx = ORIGIN_X + (cc_ + 0.5) * BLOCK_M
            cy = (y0 + y1) / 2
            from shapely.geometry import Point
            pnt = Point(cx, cy)
            if land.buffer(0).contains(pnt) or land.distance(pnt) < BLOCK_M:
                dists.append(pnt.distance(shore) * COS_LAT)
        dshore = {"min": round(min(dists), 1), "p50": round(float(np.median(dists)), 1),
                  "max": round(max(dists), 1)} if dists else {}
        # C-CAP composition (window-read in the ref CRS)
        comp = {}
        for tag, p in ccap.items():
            with rasterio.open(p) as ds:
                bb = transform_bounds(CRS, ds.crs, *b)
                win = rasterio.windows.from_bounds(*bb, transform=ds.transform)
                win = win.round_offsets().round_lengths()
                # a northern sector can fall (partly) outside the C-CAP raster; clamp by
                # hand — Window.intersection RAISES on empty overlap rather than returning it
                r0 = max(0, int(win.row_off)); c0 = max(0, int(win.col_off))
                r1 = min(ds.height, int(win.row_off + win.height))
                c1 = min(ds.width, int(win.col_off + win.width))
                if r1 <= r0 or c1 <= c0:
                    continue
                arr = ds.read(1, window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0))
            counts = np.bincount(arr.ravel(), minlength=26)
            tot = counts.sum() - counts[0]
            if tot > 0:
                comp[tag] = {g: round(float(sum(counts[v] for v in vals) / tot), 4)
                             for g, vals in CCAP_GROUPS.items() if g != "ignore"}
        sectors.append({
            "id": f"S{i+1}", "band": i, "block_row0": int(s), "block_rows": rows,
            "bounds_3857": [round(v, 3) for v in b],
            "west_col": c_lo, "east_col": c_hi, "water_cells": len(kept_water),
            "area_m2_true": round(poly.area * COS_LAT ** 2, 1),
            "land_area_m2_true": round(land.area * COS_LAT ** 2, 1),
            "water_frac": round(wfrac, 4),
            "sites": full, "sites_partial": part, "n_crowns": int(n_crowns),
            "dist_shore_m": dshore, **{k: v for k, v in comp.items()},
            "_poly": poly,
        })
        print(f"  {sectors[-1]['id']}: rows [{s},{s+rows}) cols [{c_lo},{c_hi}) "
              f"+{len(kept_water)} water cells; land {land.area*COS_LAT**2/1e4:,.0f} ha true; "
              f"water {wfrac:.1%}; sites {full or '-'}; crowns {n_crowns:,}")

    # alignment proof
    for sec in sectors:
        x0 = ORIGIN_X + sec["west_col"] * BLOCK_M
        k = (x0 - ORIGIN_X) / BLOCK_M
        assert abs(k - round(k)) < 1e-9
    print("alignment proof: sector corners on the anchor lattice (exact)")

    git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                         text=True, cwd=SCRIPTS).stdout.strip()
    doc = {"version": a.version, "crs": CRS,
           "lattice": {"origin_x": ORIGIN_X, "origin_y": ORIGIN_Y, "px": PX,
                       "tile_px": TILE, "block_tiles": BLOCK},
           "params": {"n_sectors": L, "rows_per_sector": rows, "water_ext_m": a.water_ext_m},
           "generated": {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                         "git": git, "script": "pipeline/make_sectors.py"},
           "sectors": [{k: v for k, v in s.items() if k != "_poly"} for s in sectors]}
    aoi_dir = SCRIPTS / "pipeline" / "aoi"
    aoi_dir.mkdir(exist_ok=True)
    (aoi_dir / f"{a.version}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"-> {aoi_dir / (a.version + '.json')}")

    out_dir = DATA / "phase4" / "qc" / "sectors"
    out_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(
        {"id": [s["id"] for s in sectors],
         "block_row0": [s["block_row0"] for s in sectors],
         "water_frac": [s["water_frac"] for s in sectors],
         "n_crowns": [s["n_crowns"] for s in sectors],
         "sites": [";".join(s["sites"]) for s in sectors]},
        geometry=[s["_poly"] for s in sectors], crs=CRS)
    gpkg = out_dir / f"{a.version}.gpkg"
    gdf.to_file(gpkg, layer="sectors", driver="GPKG")
    gpd.GeoDataFrame({"id": [s["id"] for s in sectors]},
                     geometry=[box(*s["bounds_3857"]) for s in sectors], crs=CRS
                     ).to_file(gpkg, layer="sector_bounds", driver="GPKG")

    # overview PNG
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 11))
        gpd.GeoSeries([city_poly], crs=CRS).plot(ax=ax, facecolor="#eee", edgecolor="k", lw=0.7)
        gpd.GeoSeries([water_u.intersection(box(minx, miny, maxx, maxy))], crs=CRS).plot(
            ax=ax, facecolor="#bcd9f5", edgecolor="none")
        gdf.plot(ax=ax, facecolor="#2a9d3a55", edgecolor="#1a6b26", lw=1.5)
        for n, bnd in sites.items():
            ax.add_patch(plt.Rectangle((bnd[0], bnd[1]), bnd[2]-bnd[0], bnd[3]-bnd[1],
                                       fill=False, edgecolor="crimson", lw=1))
        for s in sectors:
            b = s["bounds_3857"]
            ax.annotate(s["id"], ((b[0]+b[2])/2, (b[1]+b[3])/2), ha="center",
                        fontsize=14, weight="bold")
        ax.set_title(f"{a.version}: {L} sectors x {rows} block-rows (~{rows*BLOCK_M:.0f} m), "
                     f"sites red")
        ax.set_axis_off()
        fig.savefig(out_dir / f"{a.version}_overview.png", dpi=140, bbox_inches="tight")
        plt.close(fig)
        print(f"-> {out_dir / (a.version + '_overview.png')}")
    except Exception as ex:
        print(f"overview PNG skipped: {ex}")

    (out_dir / "README.txt").write_text(
        f"{a.version} — fixed west-east training/inference sectors ({dt.date.today()})\n"
        f"{L} sectors x {rows} block-rows tall, anchored to the 2020 anchor tile lattice.\n"
        "Engine use: --infer-aoi aoi/" + a.version + ".json (inference restricted to sector\n"
        "rects; rest of the prob raster = nodata 255). QC clips by the sector POLYGON layer.\n"
        "Attributes incl. water_frac (bathology waterbodies), C-CAP composition, sites,\n"
        "crown counts, distance-to-shore (there is NO terrain DEM in the data plane).\n",
        encoding="utf-8")

    ARCGIS_OUT.mkdir(parents=True, exist_ok=True)
    import shutil
    for f in (gpkg, out_dir / f"{a.version}_overview.png", out_dir / "README.txt"):
        if f.exists():
            shutil.copy2(f, ARCGIS_OUT / f.name)
    print(f"-> copies in {ARCGIS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
