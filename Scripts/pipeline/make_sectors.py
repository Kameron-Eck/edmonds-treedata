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
as distance-to-water stats + C-CAP class composition per sector instead.

COVARIATE FIXES (2026-08-26, attributes only — geometry is frozen, see GEOMETRY LOCK):
  * C-CAP 2016 composition now reads `ccap_2016_hires_lc_snohfull.tif`, which extends north to
    y=6,162,379 (EPSG:3857). The two clipped rasters (`ccap_{2016,2021}_hires_lc.tif`) both END
    at y=6,079,042, so S1 (6,081,980–6,082,591) and S2 (6,079,228–6,079,839) previously got NO
    ccap_* attributes at all — 23.4% of the sampled land weight was uncharacterized. The 2021
    clip is kept where it has coverage (S3–S5); every epoch's source file + coverage fraction is
    recorded per sector under `ccap_meta`, so an attribute always NAMES the epoch it came from.
  * `dist_sound_m` (NEW) measures to the PUGET SOUND polygon only. `dist_shore_m` (kept for
    back-compat) measures to the boundary of the union of ALL waterbodies, so eastern blocks
    measure to inland ponds / Lake Ballinger rather than the Sound — S4 shipped p50 739 m where
    the true Sound-only p50 is ~1,950 m, and the west→east ordering was broken. Use
    `dist_sound_m` for any shore→upland gradient; `dist_shore_m` is "distance to ANY water".

GEOMETRY LOCK. `pipeline/aoi/{version}.json` is read by the inference engine (`--infer-aoi`) and
its bounds define the 1-m cover-sidecar grid in phase4/qc/sector_campaign/cover1m. If a json for
this version already exists, the script (a) inherits its `params` for any flag not given on the
CLI, (b) PINS `block_row0` per sector from it and skips the shift search entirely, and (c) refuses
to write anything unless every sector's bounds_3857 / west_col / east_col / water_cells /
block_row* are identical to the shipped values. Re-running is therefore an attributes-only update.

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

# C-CAP groups for the SECTOR-DESCRIPTION attributes. This grouping DELIBERATELY DIVERGES from
# the honest scorer's (qc/phase4_qc_indep.py CCAP_DEFAULT): here 5 (Developed Open Space) and 7
# (Pasture/Hay) are folded into developed/bare rather than into grass, and scrub (12/14/17) and
# cropland (6) have no bucket of their own (they land in nothing and simply do not sum to 1).
# It is a coarse land-context descriptor, NOT the scoring taxonomy — qc/phase4_sector_poststrat.py
# strata use CCAP_DEFAULT, so its per-group fractions will not match these to the decimal.
CCAP_GROUPS = {"forest": [9, 10, 11], "wetland": [13, 16], "emergent_wetland": [15, 18],
               "grass": [8], "developed": [2, 3, 4, 5], "bare": [7, 19, 20],
               "water": [21, 22, 23], "ignore": [0, 1, 24, 25]}

# epoch -> candidate rasters, best coverage first. The 2016 "snohfull" variant is the only one
# that reaches S1/S2 (see COVARIATE FIXES in the module docstring); the clipped pair stops at
# y=6,079,042 in EPSG:3857.
CCAP_SOURCES = (("ccap_2016", ("ccap_2016_hires_lc_snohfull.tif", "ccap_2016_hires_lc.tif")),
                ("ccap_2021", ("ccap_2021_hires_lc.tif",)))

# geometry-defining params: CLI > existing json for this version > these
PARAM_DEFAULTS = {"n_sectors": 5, "rows_per_sector": 3, "water_ext_m": 150.0}
# fields that must be byte-identical to the shipped json (the engine reads them)
FROZEN_KEYS = ("bounds_3857", "block_row0", "block_rows", "west_col", "east_col", "water_cells")
COVARIATES_UPDATED = "2026-08-26"


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
    # defaults are None on purpose — an existing json for this version wins over the hardcoded
    # PARAM_DEFAULTS, so a bare re-run can never silently re-cut the geometry (the shipped
    # sectors_v1 used rows_per_sector=4 while the hardcoded default is 3).
    ap.add_argument("--n-sectors", type=int, default=None)
    ap.add_argument("--rows-per-sector", type=int, default=None)
    ap.add_argument("--water-ext-m", type=float, default=None)
    ap.add_argument("--version", default="sectors_v1")
    ap.add_argument("--replace-geometry", action="store_true",
                    help="allow the geometry to move (re-cuts sectors; INVALIDATES every cover1m "
                         "sidecar and any AOI-restricted inference). Never use on sectors_v1.")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    aoi_dir = SCRIPTS / "pipeline" / "aoi"
    prev_p = aoi_dir / f"{a.version}.json"
    prev = json.loads(prev_p.read_text(encoding="utf-8")) if prev_p.exists() else None
    prev_params = (prev or {}).get("params", {})
    for k, d in PARAM_DEFAULTS.items():
        if getattr(a, k) is None:
            src = "json" if k in prev_params else "default"
            setattr(a, k, type(d)(prev_params.get(k, d)))
            print(f"param {k} = {getattr(a, k)} (from {src})")
        else:
            print(f"param {k} = {getattr(a, k)} (from CLI)")
    if prev and a.replace_geometry:
        print("!! --replace-geometry: the geometry lock is DISABLED for this run")

    import geopandas as gpd
    import rasterio
    from rasterio.warp import transform_bounds
    from shapely.geometry import box
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    city = gpd.read_file(im.CITY_SHP).to_crs(CRS)
    city_poly = city.union_all() if hasattr(city, "union_all") else city.unary_union
    water = gpd.read_file(WATER_SHP)
    if water.crs is not None and water.crs.to_epsg() != 3857:
        water = water.to_crs(CRS)
    water = water[water.geometry.notna() & water.is_valid]
    # clip to the city neighbourhood before the union — the layer is county-wide
    minx, miny, maxx, maxy = city_poly.buffer(2000).bounds
    water = water.cx[minx:maxx, miny:maxy]
    water_u = unary_union(list(water.geometry))
    print(f"city {city_poly.area/1e6:.1f} km2(3857); water features near city: {len(water)}")

    # PUGET SOUND ONLY — robust pick: the single largest waterbody polygon touching the city
    # neighbourhood. Everything else near Edmonds (Lake Ballinger, Hall Lake, tidal-flat slivers,
    # ponds) is orders of magnitude smaller, so "largest" is unambiguous; the ratio is asserted
    # and printed rather than trusted.
    w_area = water.geometry.area.sort_values(ascending=False)
    sound_row = water.loc[w_area.index[0]]
    a1, a2 = float(w_area.iloc[0]), float(w_area.iloc[1])
    print(f"Puget Sound pick: NAME={sound_row.get('NAME')!r} FEATURE={sound_row.get('FEATURE_re')!r}"
          f" area {a1/1e6:,.1f} km2(3857) vs runner-up "
          f"({water.loc[w_area.index[1]].get('NAME')!r}) {a2/1e6:,.3f} km2 -> {a1/a2:,.0f}x")
    assert a1 > 25 * a2, f"Puget Sound selection is NOT unambiguous: {a1:.0f} vs {a2:.0f}"
    sound_shore = sound_row.geometry.boundary

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

    if prev and prev.get("sectors") and not a.replace_geometry:
        # GEOMETRY LOCK: the shift search is the one input-sensitive step (its objective counts
        # photos/*_rgb.tif site footprints, and that set grows). Pin the shipped placement so an
        # attributes-only refresh can never move a sector.
        starts = [int(s["block_row0"]) for s in prev["sectors"]]
        assert len(starts) == L, (f"existing {a.version}.json has {len(starts)} sectors but "
                                  f"--n-sectors={L}")
        nf = sum(len(sites_in(s)[0]) for s in starts)
        np_ = sum(len(sites_in(s)[1]) for s in starts)
        print(f"placement: starts {starts} PINNED from {prev_p.name} (shift search skipped) — "
              f"{nf} sites fully contained, {np_} partial")
    else:
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
    for tag, cands in CCAP_SOURCES:
        for name in cands:
            p = _ccap_path(name)
            if p:
                ccap[tag] = p
                break
        print(f"C-CAP {tag}: {ccap.get(tag) or 'NOT FOUND'}")
    # the small clipped 2016 raster, kept only as a cross-check against the snohfull product
    ccap_2016_clip = _ccap_path("ccap_2016_hires_lc.tif")
    if ccap.get("ccap_2016") == ccap_2016_clip:
        ccap_2016_clip = None

    def ccap_comp(path, bnds):
        """(group_fracs, coverage_frac_of_bbox, classified_px) for a sector bbox, or None.

        coverage_frac = read pixels / pixels the bbox window asks for — a sector that falls
        (partly) outside the raster reports it instead of silently shrinking its denominator.
        """
        with rasterio.open(path) as ds:
            bb = transform_bounds(CRS, ds.crs, *bnds)
            win = rasterio.windows.from_bounds(*bb, transform=ds.transform)
            win = win.round_offsets().round_lengths()
            want = max(1, int(win.height) * int(win.width))
            # a northern sector can fall (partly) outside the C-CAP raster; clamp by hand —
            # Window.intersection RAISES on empty overlap rather than returning it
            r0 = max(0, int(win.row_off)); c0 = max(0, int(win.col_off))
            r1 = min(ds.height, int(win.row_off + win.height))
            c1 = min(ds.width, int(win.col_off + win.width))
            if r1 <= r0 or c1 <= c0:
                return None
            arr = ds.read(1, window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0))
        counts = np.bincount(arr.ravel(), minlength=26)
        tot = int(counts.sum() - counts[0])
        if tot <= 0:
            return None
        return ({g: round(float(sum(counts[v] for v in vals) / tot), 4)
                 for g, vals in CCAP_GROUPS.items() if g != "ignore"},
                round(arr.size / want, 4), tot)

    crowns_path = CROWNS if CROWNS.exists() else CROWNS_FALLBACK
    crowns = gpd.read_file(crowns_path, columns=["crown_id"], engine="pyogrio")
    crown_tree = STRtree(crowns.geometry.values)
    shore = water_u.boundary        # ALL waterbodies — feeds dist_shore_m (back-compat only)

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
        # distance-to-water stats from land block centroids.
        #   dist_shore_m — distance to the boundary of the union of ALL waterbodies. KEPT ONLY
        #     FOR BACK-COMPAT: east of the city the nearest "shore" is an inland pond or Lake
        #     Ballinger, so this is "distance to ANY water" and is NOT a shore->upland gradient.
        #   dist_sound_m — distance to the PUGET SOUND polygon boundary. This is the gradient
        #     covariate; use it, not dist_shore_m.
        dists, d_sound = [], []
        for cc_ in range(c_lo, c_hi):
            cx = ORIGIN_X + (cc_ + 0.5) * BLOCK_M
            cy = (y0 + y1) / 2
            from shapely.geometry import Point
            pnt = Point(cx, cy)
            if land.buffer(0).contains(pnt) or land.distance(pnt) < BLOCK_M:
                dists.append(pnt.distance(shore) * COS_LAT)
                d_sound.append(pnt.distance(sound_shore) * COS_LAT)

        def _stats(v):
            return {"min": round(min(v), 1), "p50": round(float(np.median(v)), 1),
                    "max": round(max(v), 1)} if v else {}
        dshore, dsound = _stats(dists), _stats(d_sound)
        # C-CAP composition (window-read in the ref CRS), per epoch, source NAMED
        comp, cmeta = {}, {}
        for tag, p in ccap.items():
            got = ccap_comp(p, b)
            if got is None:
                cmeta[tag] = {"file": p.name, "coverage_frac": 0.0, "classified_px": 0,
                              "note": "sector falls outside this raster"}
                continue
            comp[tag], cov_frac, npx = got
            cmeta[tag] = {"file": p.name, "coverage_frac": cov_frac, "classified_px": int(npx)}
        sectors.append({
            "id": f"S{i+1}", "band": i, "block_row0": int(s), "block_rows": rows,
            "bounds_3857": [round(v, 3) for v in b],
            "west_col": c_lo, "east_col": c_hi, "water_cells": len(kept_water),
            "area_m2_true": round(poly.area * COS_LAT ** 2, 1),
            "land_area_m2_true": round(land.area * COS_LAT ** 2, 1),
            "water_frac": round(wfrac, 4),
            "sites": full, "sites_partial": part, "n_crowns": int(n_crowns),
            "dist_shore_m": dshore, "dist_sound_m": dsound,
            **{k: v for k, v in comp.items()}, "ccap_meta": cmeta,
            "_poly": poly,
        })
        print(f"  {sectors[-1]['id']}: rows [{s},{s+rows}) cols [{c_lo},{c_hi}) "
              f"+{len(kept_water)} water cells; land {land.area*COS_LAT**2/1e4:,.0f} ha true; "
              f"water {wfrac:.1%}; sites {full or '-'}; crowns {n_crowns:,}")
        print(f"      dist_sound_m {dsound or '-'} | dist_shore_m(any water) {dshore or '-'}")
        for tag in ("ccap_2016", "ccap_2021"):
            m = cmeta.get(tag)
            if not m:
                continue
            c = comp.get(tag)
            print(f"      {tag} <- {m['file']} cov {m['coverage_frac']:.0%}: "
                  + (f"forest {c['forest']:.3f} developed {c['developed']:.3f} "
                     f"water {c['water']:.3f}" if c else "NO COVERAGE"))
        if ccap_2016_clip is not None:                    # product cross-check, not stored
            chk = ccap_comp(ccap_2016_clip, b)
            if chk and comp.get("ccap_2016"):
                d = max(abs(chk[0][g] - comp["ccap_2016"][g]) for g in chk[0])
                print(f"      ccap_2016 snohfull-vs-clip max group delta {d:.4f} "
                      f"(clip cov {chk[1]:.0%})")

    # alignment proof
    for sec in sectors:
        x0 = ORIGIN_X + sec["west_col"] * BLOCK_M
        k = (x0 - ORIGIN_X) / BLOCK_M
        assert abs(k - round(k)) < 1e-9
    print("alignment proof: sector corners on the anchor lattice (exact)")

    # ── GEOMETRY LOCK ─────────────────────────────────────────────────────────────────────
    # pipeline/aoi/{version}.json is read by the inference engine (--infer-aoi) and its bounds
    # define the 1-m cover-sidecar grid. Verify BEFORE any write; abort on the first mismatch.
    if prev and prev.get("sectors") and not a.replace_geometry:
        prev_by_id = {s["id"]: s for s in prev["sectors"]}
        bad = []
        if len(prev["sectors"]) != len(sectors):
            bad.append(f"sector COUNT {len(prev['sectors'])} -> {len(sectors)}")
        for s in sectors:
            p = prev_by_id.get(s["id"])
            if p is None:
                bad.append(f"{s['id']}: not present in the shipped json")
                continue
            for k in FROZEN_KEYS:
                if k not in p:
                    continue
                new, old = s[k], p[k]
                if isinstance(old, list):
                    if len(new) != len(old) or any(float(x) != float(y)
                                                   for x, y in zip(new, old)):
                        bad.append(f"{s['id']}.{k}: {old} -> {new}")
                elif float(new) != float(old):
                    bad.append(f"{s['id']}.{k}: {old} -> {new}")
        if bad:
            print("GEOMETRY LOCK FAILED — nothing written. Moved:")
            for m in bad:
                print("   " + m)
            return 2
        print(f"geometry lock: OK — {len(sectors)} sectors, every {'/'.join(FROZEN_KEYS)} "
              f"identical to {prev_p.name} (attributes-only update)")

    git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                         text=True, cwd=SCRIPTS).stdout.strip()
    doc = {"version": a.version, "crs": CRS,
           "lattice": {"origin_x": ORIGIN_X, "origin_y": ORIGIN_Y, "px": PX,
                       "tile_px": TILE, "block_tiles": BLOCK},
           "params": {"n_sectors": L, "rows_per_sector": rows, "water_ext_m": a.water_ext_m},
           "generated": {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                         "git": git, "script": "pipeline/make_sectors.py"},
           "covariates_updated": COVARIATES_UPDATED,
           "covariate_notes": {
               "dist_sound_m": "distance (true m) from land block centroids to the PUGET SOUND "
                               "polygon boundary — the shore->upland gradient covariate",
               "dist_shore_m": "BACK-COMPAT ONLY: distance to the boundary of the union of ALL "
                               "waterbodies, so eastern blocks measure to inland ponds / Lake "
                               "Ballinger. Not a shore gradient.",
               "ccap_*": "group fractions of the classified (non-background) pixels in the "
                         "sector bbox; ccap_meta names the source raster + coverage per epoch. "
                         "Grouping is make_sectors.CCAP_GROUPS, which deliberately diverges "
                         "from qc/phase4_qc_indep.CCAP_DEFAULT (see the constant's comment)."},
           "ccap_sources": {t: (ccap[t].name if t in ccap else None) for t, _ in CCAP_SOURCES},
           "sectors": [{k: v for k, v in s.items() if k != "_poly"} for s in sectors]}
    aoi_dir.mkdir(exist_ok=True)
    (aoi_dir / f"{a.version}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"-> {aoi_dir / (a.version + '.json')}")

    out_dir = DATA / "phase4" / "qc" / "sectors"
    out_dir.mkdir(parents=True, exist_ok=True)
    gpkg = out_dir / f"{a.version}.gpkg"

    def _d(s, key, stat):
        return s.get(key, {}).get(stat)

    def _c(s, tag, grp):
        return s.get(tag, {}).get(grp)

    attrs = {
        "id": [s["id"] for s in sectors],
        "block_row0": [s["block_row0"] for s in sectors],
        "water_frac": [s["water_frac"] for s in sectors],
        "n_crowns": [s["n_crowns"] for s in sectors],
        "sites": [";".join(s["sites"]) for s in sectors],
        # ── covariates refreshed 2026-08-26 ────────────────────────────────────────────
        "land_ha_true": [round(s["land_area_m2_true"] / 1e4, 2) for s in sectors],
        "d_sound_min": [_d(s, "dist_sound_m", "min") for s in sectors],
        "d_sound_p50": [_d(s, "dist_sound_m", "p50") for s in sectors],
        "d_sound_max": [_d(s, "dist_sound_m", "max") for s in sectors],
        "d_anywater_p50": [_d(s, "dist_shore_m", "p50") for s in sectors],
        "ccap16_src": [s["ccap_meta"].get("ccap_2016", {}).get("file") for s in sectors],
        "ccap16_cov": [s["ccap_meta"].get("ccap_2016", {}).get("coverage_frac")
                       for s in sectors],
        "ccap21_src": [s["ccap_meta"].get("ccap_2021", {}).get("file") for s in sectors],
        "ccap21_cov": [s["ccap_meta"].get("ccap_2021", {}).get("coverage_frac")
                       for s in sectors],
    }
    for tag, short in (("ccap_2016", "ccap16"), ("ccap_2021", "ccap21")):
        for grp in ("forest", "developed", "water", "grass", "bare", "wetland"):
            attrs[f"{short}_{grp}"] = [_c(s, tag, grp) for s in sectors]
    gdf = gpd.GeoDataFrame(attrs, geometry=[s["_poly"] for s in sectors], crs=CRS)

    # gpkg geometry lock — the 1-m cover sidecars in sector_campaign/cover1m were gridded from
    # this layer's total_bounds, so a moved corner silently misregisters every one of them.
    if gpkg.exists() and not a.replace_geometry:
        old = gpd.read_file(gpkg, layer="sectors").set_index("id")
        new = gdf.set_index("id")
        assert list(old.index) == list(new.index), f"gpkg sector ids moved: {list(old.index)}"
        assert np.array_equal(np.asarray(old.total_bounds), np.asarray(new.total_bounds)), (
            f"gpkg total_bounds moved {old.total_bounds} -> {new.total_bounds} — this "
            f"invalidates every cover1m sidecar")
        for sid in new.index:
            og, ng = old.geometry[sid], new.geometry[sid]
            assert og.equals(ng) and np.array_equal(np.asarray(og.bounds),
                                                    np.asarray(ng.bounds)), \
                f"gpkg geometry moved for {sid}"
        print(f"gpkg geometry lock: OK — {len(new)} polygons identical, total_bounds "
              f"{[round(v, 3) for v in new.total_bounds]} unchanged")
    if gpkg.exists():
        # rewrite from scratch (the attribute table gains columns); keep one rollback copy
        bak = gpkg.with_suffix(".gpkg.prev")
        bak.unlink(missing_ok=True)
        gpkg.replace(bak)
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
        "crown counts, distance-to-water (there is NO terrain DEM in the data plane).\n"
        f"\nCovariates refreshed {COVARIATES_UPDATED} (geometry FROZEN — see the script's\n"
        "GEOMETRY LOCK; a re-run refuses to write if any sector bound moves):\n"
        "  d_sound_* / dist_sound_m — distance to the PUGET SOUND polygon. THE gradient\n"
        "    covariate. d_anywater_p50 / dist_shore_m is the old any-waterbody distance,\n"
        "    kept only for back-compat (east of the city it measures to inland ponds).\n"
        "  ccap16_* now come from " + (ccap.get("ccap_2016").name if ccap.get("ccap_2016")
                                       else "NO 2016 RASTER") + ", which covers S1/S2;\n"
        "    the clipped ccap_{2016,2021}_hires_lc.tif end at y=6,079,042 (EPSG:3857), so\n"
        "    ccap21_* is null for S1/S2. ccap16_src/ccap21_src name the file per sector.\n"
        "  Grouping = make_sectors.CCAP_GROUPS, which is NOT the scorer's CCAP_DEFAULT.\n",
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
