#!/usr/bin/env python3
"""
  CANONICAL BUILDINGS LAYER — one per-structure footprint table, dated
  ---------------------------------------------------------------------------

WHY
    Two things in this project need to know where buildings are AND when they
    existed:

      1. Roofs are the largest non-vegetation NIR contaminant in the city. A
         static current-state footprint layer masks them in the wrong years —
         it over-masks structures that had not been built yet and never masks
         structures since demolished (README_PROVENANCE.md §4).
      2. Backward projection of crown validity needs a date for the ground a
         crown sits next to. "This roof appeared in 2004" is a hard constraint
         on "this tree was planted after 2004".

    The county publishes the two halves of the answer separately: roofprint
    POLYGONS (per structure, with LiDAR heights) and Assessor IMPROVEMENT
    RECORDS (per structure, with YrBuilt), joined through the parcel number.
    This script welds them into one layer and records exactly how.

WHAT IT WRITES
    {BUILDINGS}/buildings_canonical.gpkg   layer "buildings"
    {BUILDINGS}/README_BUILDINGS.md        provenance, join stats, licences
    {BUILDINGS}/cache/snoco_roofprints.geojson    raw county fetch (idempotent)

    BUILDINGS = G:\\My Drive\\treedata\\buildings   (data plane)

GEOMETRY BACKBONE — why the county roofprints and not the ONEGEO file
    `building_footprints/data.json` (ONEGEO GmbH, 23,666 polygons) is a
    commercial blend whose licence forbids resale and whose heights are
    modelled (`heightScore` = 0.55 on 96.4% of features). The county
    `BUILDINGS__roofprints` layer covers the same ground (23,262 polygons in
    the study bbox), carries **LiDAR-derived** `ht_mean` / `ht_max` / `ht_95`,
    and is public-agency data. So the county layer is the backbone; ONEGEO is
    used ONLY to gap-fill structures the county layer lacks, and every feature
    records which source it came from.

THE JOIN RULE (this is the part to read before trusting `yr_built`)
    Improvement records are PARCEL-keyed (`PIN`), roofprints are structure-
    keyed (`uniq_id`). The chain is:

        roofprint --representative point within--> parcel polygon (parcel_id)
        parcel_id == PIN --> N improvement rows

    Three cases, recorded per feature in `yr_built_rule`:

    `single`        the parcel has exactly ONE improvement row. 95.9% of PINs
                    in the study bbox. yr_built = that row's YrBuilt.
    `rank_finsize`  the parcel has SEVERAL improvements and SEVERAL roofprints.
                    Both are sorted by size (improvements by `FinSize`,
                    roofprints by polygon area) and paired in rank order: the
                    largest improvement is assumed to be the largest structure.
                    CAVEAT: FinSize is *finished area summed over stories*, so a
                    two-storey house can out-rank a larger single-storey one and
                    invert the pairing. This touches ~350 of ~22k parcels; the
                    parcel-wide `yr_built_min` / `yr_built_max` are carried on
                    every feature so a consumer can ignore the ranking entirely.
    `parcel_min`    more roofprints than improvements (the usual surplus is an
                    unassessed shed / detached garage) — the surplus structures
                    take the parcel's EARLIEST year, on the reading that an
                    outbuilding is contemporaneous with or older than the house.
                    This biases toward "present earlier", i.e. toward masking.
    `none`          no parcel matched, or the parcel has no usable YrBuilt.
                    ~1 footprint in 12. Downstream must treat these as undated.

    CONDO / STACKED PARCELS: many condo parcels share one polygon, so a single
    roofprint can fall inside several parcel polygons. Those are collapsed by
    `uniq_id` — min over the matched years for `yr_built_min`, max for
    `yr_built_max` — so the output has exactly one row per structure.

WHAT `yr_built` CANNOT TELL YOU  (repeated because it governs every downstream use)
    - It is the improvement AS IT STANDS. A teardown-and-rebuild carries the
      NEW year and erases the old structure, so a pre-rebuild year reads
      "nothing here" when a different house stood there.
    - DEMOLISHED structures are absent from both the roll and the roofprints.
      A current-state layer cannot count what it deleted.
    - Therefore: assessor-PRESENT is strong evidence; assessor-ABSENT is weak.
      That asymmetry is the whole design of qc/roof_presence_matrix.py.

USAGE
    py -3.12 pipeline/build_buildings_layer.py              # build everything
    py -3.12 pipeline/build_buildings_layer.py --step fetch # cache only
    py -3.12 pipeline/build_buildings_layer.py --refetch    # ignore the cache

    Requires qc/fetch_snoco_improvements.py to have run first (it produces the
    parcel + improvement inputs; one fact, one home — this script never
    re-downloads the 99 MB Assessor workbook).

Local-only (rasterio/geopandas install locally); no Colab, no GPU.
v001
"""

from __future__ import annotations

from phase4seg.names import clean_argv
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon, shape

_HERE = Path(__file__).resolve().parent           # …/Scripts/pipeline
_SCRIPTS = _HERE.parent                           # …/Scripts

try:
    from pipeline_log import write_step_log       # noqa: E402
except Exception:                                 # logging is a nicety, not a gate
    write_step_log = None


# ── Paths: code via __file__, data via the data plane ────────────────────────
DATA = Path(r"G:\My Drive\treedata")
BUILDINGS = DATA / "buildings"
CACHE = BUILDINGS / "cache"
LOGS_DIR = DATA / "phase4" / "logs"

ROOF_PRESENCE = DATA / "phase4" / "qc" / "roof_presence"
PARCELS_GPKG = ROOF_PRESENCE / "snoco_parcels_yrbuilt.gpkg"     # fetch_snoco_improvements.py
IMPROVE_CSV = ROOF_PRESENCE / "snoco_improvements_studybbox.csv"  # ditto
ONEGEO_JSON = DATA / "building_footprints" / "data.json"

OUT_GPKG = BUILDINGS / "buildings_canonical.gpkg"
OUT_LAYER = "buildings"
OUT_README = BUILDINGS / "README_BUILDINGS.md"

# ── County roofprint service (verified 2026-08-26; URL from README_PROVENANCE) ─
ROOFPRINT_URL = ("https://gis.snoco.org/host/rest/services/Hosted/"
                 "BUILDINGS__roofprints/FeatureServer/0/query")
PAGE = 2000                       # == the service's maxRecordCount

# Study extent — the bbox of Kam's ONEGEO order (building_footprints/index.json),
# so the county layer and the gap-filler cover exactly the same ground.
BBOX = (-122.39697, 47.77759, -122.31936, 47.85954)

WORK_CRS = "EPSG:26910"           # UTM 10N — TRUE metres. Areas are computed here.
OUT_CRS = "EPSG:4326"             # the layer is stored in lon/lat like its inputs

# ONEGEO gap-fill test: an ONEGEO polygon is a GAP only if its representative
# point falls outside every county roofprint dilated by this much. The dilation
# absorbs registration slop between two independently-digitised layers.
GAPFILL_SLOP_M = 2.0
# ...and only if it is big enough to be a building rather than a mapping artefact.
GAPFILL_MIN_AREA_M2 = 20.0

YEAR_LO, YEAR_HI = 1850, 2030     # plausibility gate on YrBuilt

# The county roofprint ht_* fields are US SURVEY FEET (measured, not assumed —
# see the UNITS comment where ht_95_m is computed).
FT_TO_M = 0.3048


# ── County fetch ─────────────────────────────────────────────────────────────
def _get(url, params, timeout=240):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params),
                                timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _rings_to_geom(rings):
    """Esri rings -> shapely. First ring outer; holes are ignored (they are rare
    on roofprints and a hole would only shrink a mask)."""
    polys = [Polygon(r) for r in rings if len(r) >= 4]
    polys = [p if p.is_valid else p.buffer(0) for p in polys]
    polys = [p for p in polys if not p.is_empty]
    if not polys:
        return None
    if len(polys) == 1:
        return polys[0]
    return MultiPolygon([g for p in polys
                         for g in (p.geoms if p.geom_type == "MultiPolygon"
                                   else [p])])


def fetch_roofprints(cache: Path, refetch: bool) -> gpd.GeoDataFrame:
    """Page every county roofprint intersecting the study bbox.

    IDEMPOTENT: a cache file that parses and holds >= MIN features is reused.
    The service reports its own count first, so "size-matched" here means
    feature-count-matched against the live service — stronger than a byte size.
    """
    live_n = None
    try:
        d = _get(ROOFPRINT_URL, {
            "where": "1=1",
            "geometry": ",".join(str(v) for v in BBOX),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "returnCountOnly": "true",
            "f": "json",
        }, timeout=120)
        live_n = int(d.get("count", 0)) or None
    except Exception as exc:
        print(f"  (could not read the live feature count: {exc})")

    if cache.exists() and not refetch:
        try:
            raw = json.loads(cache.read_text(encoding="utf-8"))
            n = len(raw.get("features", []))
            if live_n is None or n == live_n:
                print(f"  cache hit: {cache.name}  {n:,} features"
                      f"{'' if live_n is None else f' (== live {live_n:,})'}"
                      f"  {cache.stat().st_size/1e6:.1f} MB — skipping the fetch")
                return _roofprints_from_raw(raw)
            print(f"  cache STALE: {n:,} cached vs {live_n:,} live — refetching")
        except Exception as exc:
            print(f"  cache unreadable ({exc}) — refetching")

    feats, offset = [], 0
    while True:
        d = _get(ROOFPRINT_URL, {
            "where": "1=1",
            "geometry": ",".join(str(v) for v in BBOX),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": ("uniq_id,name,height,ht_mean,ht_max,ht_95,source,"
                          "created_date,last_edited_date"),
            "returnGeometry": "true",
            "outSR": "4326",
            "resultOffset": str(offset),
            "resultRecordCount": str(PAGE),
            "f": "json",
        })
        page = d.get("features", [])
        feats.extend(page)
        print(f"  roofprints offset={offset} -> {len(page)} "
              f"(total {len(feats):,})", flush=True)
        if not d.get("exceededTransferLimit") or not page:
            break
        offset += len(page)
        time.sleep(0.25)

    raw = {"features": feats,
           "_fetched": datetime.now().isoformat(timespec="seconds"),
           "_service": ROOFPRINT_URL, "_bbox": list(BBOX)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(raw), encoding="utf-8")
    print(f"  cached -> {cache}  ({cache.stat().st_size/1e6:.1f} MB)")
    return _roofprints_from_raw(raw)


def _roofprints_from_raw(raw) -> gpd.GeoDataFrame:
    recs, geoms = [], []
    for f in raw["features"]:
        g = _rings_to_geom((f.get("geometry") or {}).get("rings") or [])
        if g is None:
            continue
        a = f["attributes"]
        recs.append({
            "uniq_id": a.get("uniq_id"),
            "co_name": a.get("name"),
            "co_height": a.get("height"),
            "ht_mean": a.get("ht_mean"),
            "ht_max": a.get("ht_max"),
            "ht_95": a.get("ht_95"),
            "co_source": a.get("source"),
        })
        geoms.append(g)
    gdf = gpd.GeoDataFrame(recs, geometry=geoms, crs="EPSG:4326")
    # uniq_id is the key space; guarantee it is one
    dup = gdf.uniq_id.duplicated(keep="first")
    if dup.any():
        print(f"  NOTE {int(dup.sum())} duplicate uniq_id values dropped")
        gdf = gdf[~dup]
    return gdf.reset_index(drop=True)


# ── ONEGEO gap-filler ────────────────────────────────────────────────────────
def load_onegeo() -> gpd.GeoDataFrame:
    """Read the ONEGEO GeoJSON preserving its per-feature top-level `id`.

    geopandas/pyogrio drops the GeoJSON `id`, and that id is the only stable
    handle back into Kam's file (and into the earlier probe output), so the
    JSON is parsed directly — same reason as qc/roof_presence_probe.py.
    """
    d = json.loads(ONEGEO_JSON.read_text(encoding="utf-8"))
    recs, geoms = [], []
    for f in d["features"]:
        p = f.get("properties", {})
        recs.append({
            "og_id": f.get("id"),
            "og_area_m2": p.get("area"),
            "og_height_m": p.get("height"),
            "og_type": p.get("type"),
        })
        geoms.append(shape(f["geometry"]))
    return gpd.GeoDataFrame(recs, geometry=geoms, crs="EPSG:4326")


# ── Assessor join ────────────────────────────────────────────────────────────
def load_assessor():
    if not PARCELS_GPKG.exists() or not IMPROVE_CSV.exists():
        raise SystemExit(
            f"missing assessor inputs:\n"
            f"  {PARCELS_GPKG}  exists={PARCELS_GPKG.exists()}\n"
            f"  {IMPROVE_CSV}   exists={IMPROVE_CSV.exists()}\n"
            f"Run:  py -3.12 qc/fetch_snoco_improvements.py")
    par = gpd.read_file(PARCELS_GPKG, layer="parcels_yrbuilt")
    imp = pd.read_csv(IMPROVE_CSV, dtype={"PIN": str})
    imp["YrBuilt"] = pd.to_numeric(imp["YrBuilt"], errors="coerce")
    imp.loc[~imp.YrBuilt.between(YEAR_LO, YEAR_HI), "YrBuilt"] = np.nan
    imp["FinSize"] = pd.to_numeric(imp["FinSize"], errors="coerce")
    return par, imp


def attach_parcel(fp_work: gpd.GeoDataFrame, par_work: gpd.GeoDataFrame,
                  key: str, stats: dict | None = None) -> pd.DataFrame:
    """Structure -> parcel(s) by representative point, collapsed to one row.

    A representative point is used rather than a centroid because an L-shaped
    or annular roofprint can put its centroid outside itself. Condo parcels are
    stacked on one polygon, so `within` can return several parcels for one
    structure; those are collapsed here — min/max over the matched years — so
    the canonical layer has exactly one row per structure.
    """
    pts = gpd.GeoDataFrame(fp_work[[key]],
                           geometry=fp_work.representative_point(),
                           crs=fp_work.crs)
    j = gpd.sjoin(pts, par_work[["parcel_id", "yrbuilt_min", "yrbuilt_max",
                                 "n_improvements", "roof_mat", "roof_type",
                                 "use_desc", "geometry"]],
                  how="left", predicate="within")
    n_multi = int(j.groupby(key).size().gt(1).sum())
    if stats is not None:
        stats["n_multi_parcel"] = n_multi
    if n_multi:
        print(f"  {n_multi:,} structures fell inside >1 parcel polygon "
              f"(stacked condo/mobile-home parcels) — collapsed by {key}")
    agg = (j.groupby(key)
             .agg(parcel_id=("parcel_id", "first"),
                  n_parcels_matched=("parcel_id", lambda s: int(s.notna().sum())),
                  yr_built_min=("yrbuilt_min", "min"),
                  yr_built_max=("yrbuilt_max", "max"),
                  n_improvements=("n_improvements", "max"),
                  roof_mat=("roof_mat", "first"),
                  roof_type=("roof_type", "first"),
                  use_desc=("use_desc", "first"))
             .reset_index())
    return agg


def rank_match_years(fp: pd.DataFrame, imp: pd.DataFrame, key: str) -> pd.DataFrame:
    """Per-structure yr_built + the rule that produced it. See the module
    docstring's THE JOIN RULE block — this function IS that rule."""
    imp_ok = imp[imp.YrBuilt.notna()].copy()
    by_pin = {pin: g.sort_values("FinSize", ascending=False,
                                 na_position="last")
              for pin, g in imp_ok.groupby("PIN")}

    yb, rule = {}, {}
    for pid, grp in fp.groupby("parcel_id", dropna=True):
        rows = by_pin.get(pid)
        if rows is None or rows.empty:
            continue
        # structures on this parcel, largest first
        order = grp.sort_values("area_m2", ascending=False).index
        years = rows.YrBuilt.astype(int).tolist()
        if len(years) == 1:
            for i in order:
                yb[i], rule[i] = years[0], "single"
            continue
        ymin = min(years)
        for k, i in enumerate(order):
            if k < len(years):
                yb[i], rule[i] = years[k], "rank_finsize"
            else:
                yb[i], rule[i] = ymin, "parcel_min"

    fp = fp.copy()
    fp["yr_built"] = pd.Series(yb, dtype="Float64").reindex(fp.index)
    fp["yr_built_rule"] = pd.Series(rule, dtype="object").reindex(fp.index)
    fp["yr_built_rule"] = fp.yr_built_rule.fillna("none")
    return fp


# ── Build ────────────────────────────────────────────────────────────────────
def build(args) -> dict:
    stats = {}
    BUILDINGS.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    print("fetching county roofprints ...", flush=True)
    roof = fetch_roofprints(CACHE / "snoco_roofprints.geojson", args.refetch)
    print(f"county roofprints: {len(roof):,}")
    stats["n_roofprints"] = len(roof)
    if args.step == "fetch":
        return stats

    print("\nloading the ONEGEO blend (gap-filler) ...", flush=True)
    og = load_onegeo()
    print(f"ONEGEO footprints: {len(og):,}")
    stats["n_onegeo"] = len(og)

    # areas are measured in TRUE metres, never in 3857 or 2285 units
    roof_w = roof.to_crs(WORK_CRS)
    og_w = og.to_crs(WORK_CRS)
    roof["area_m2"] = roof_w.area.values
    og["area_m2"] = og_w.area.values

    # ── gap-fill: which ONEGEO polygons have no county counterpart? ──────────
    print("\nfinding structures the county layer lacks ...", flush=True)
    covered = gpd.GeoDataFrame(geometry=roof_w.geometry.buffer(GAPFILL_SLOP_M),
                               crs=WORK_CRS)
    og_pts = gpd.GeoDataFrame(og[["og_id"]],
                              geometry=og_w.representative_point(),
                              crs=WORK_CRS)
    hit = gpd.sjoin(og_pts, covered, how="left", predicate="within")
    matched = set(hit.loc[hit.index_right.notna(), "og_id"])
    gap = og[(~og.og_id.isin(matched)) & (og.area_m2 >= GAPFILL_MIN_AREA_M2)].copy()
    n_small = int(((~og.og_id.isin(matched))
                   & (og.area_m2 < GAPFILL_MIN_AREA_M2)).sum())
    print(f"  ONEGEO polygons matching a county roofprint: {len(matched):,}")
    print(f"  ONEGEO gap-fill candidates (>= {GAPFILL_MIN_AREA_M2:.0f} m2): "
          f"{len(gap):,}   (+{n_small:,} rejected as too small)")
    stats["n_onegeo_matched"] = len(matched)
    stats["n_gapfill"] = len(gap)
    stats["n_gapfill_rejected_small"] = n_small

    # ── assemble ─────────────────────────────────────────────────────────────
    a = roof[["uniq_id", "area_m2", "ht_mean", "ht_max", "ht_95", "co_height",
              "co_source", "co_name", "geometry"]].copy()
    a["building_id"] = a.uniq_id.astype(str)
    a["source"] = "snoco_roofprint"

    b = gap[["og_id", "area_m2", "og_height_m", "og_type", "geometry"]].copy()
    # prefix so the key spaces can never collide
    b["building_id"] = "OG_" + b.og_id.astype(str)
    b["source"] = "onegeo_gapfill"
    b["ht_mean"] = np.nan
    b["ht_max"] = np.nan
    b["ht_95"] = np.nan
    b["co_height"] = np.nan          # county field; NOT the ONEGEO metre height
    b["co_source"] = None
    b["co_name"] = None
    a["og_height_m"] = np.nan

    cols = ["building_id", "source", "area_m2", "ht_mean", "ht_max", "ht_95",
            "co_height", "og_height_m", "co_source", "co_name", "geometry"]
    can = gpd.GeoDataFrame(pd.concat([a[cols], b[cols]], ignore_index=True),
                           geometry="geometry", crs="EPSG:4326")
    can["og_type"] = pd.concat([pd.Series([None] * len(a)),
                                b.og_type.reset_index(drop=True)],
                               ignore_index=True)
    print(f"\ncanonical structures: {len(can):,} "
          f"({len(a):,} county + {len(b):,} ONEGEO gap-fill)")
    stats["n_canonical"] = len(can)

    # ── assessor join ────────────────────────────────────────────────────────
    print("\njoining the assessor record ...", flush=True)
    par, imp = load_assessor()
    print(f"  parcels {len(par):,}   improvement rows {len(imp):,}")
    par_w = par.to_crs(WORK_CRS)
    can_w = can.to_crs(WORK_CRS)
    agg = attach_parcel(can_w, par_w, "building_id", stats)
    can = can.merge(agg, on="building_id", how="left")
    n_par = int(can.parcel_id.notna().sum())
    print(f"  structures landing in a parcel polygon: {n_par:,} / {len(can):,} "
          f"({100*n_par/len(can):.1f}%)")
    stats["n_in_parcel"] = n_par

    can = rank_match_years(can, imp, "building_id")
    n_yb = int(can.yr_built.notna().sum())
    print(f"  structures with a yr_built:  {n_yb:,} / {len(can):,} "
          f"({100*n_yb/len(can):.1f}%)")
    stats["n_yr_built"] = n_yb
    stats["pct_yr_built"] = round(100 * n_yb / len(can), 2)
    print("  yr_built_rule:")
    for k, v in can.yr_built_rule.value_counts().items():
        print(f"    {k:<14} {v:7,}")
        stats[f"rule_{k}"] = int(v)

    # ── final schema ─────────────────────────────────────────────────────────
    can["yr_built"] = can.yr_built.astype("Float64")
    can["yr_built_min"] = pd.to_numeric(can.yr_built_min, errors="coerce")
    can["yr_built_max"] = pd.to_numeric(can.yr_built_max, errors="coerce")
    can["built_in_record"] = (can.yr_built >= 2000) & (can.yr_built <= 2024)

    # UNITS: the county roofprint heights are in US SURVEY FEET, not metres.
    # The service publishes no unit; it was MEASURED here (2026-08-26) by
    # matching 22,378 county structures to their ONEGEO counterpart, whose
    # `height` IS metres: median(ht_mean / onegeo_height) = 3.40, against
    # 1/0.3048 = 3.281 ft per metre — and ht_95 median 21.97 ft = 6.70 m, a
    # normal ridge height for an Edmonds house (metres would make it 22 m).
    # The verbatim county fields are kept as-is so they can be traced back to
    # the service; `ht_95_m` is the converted copy downstream should use.
    can["ht_95_m"] = pd.to_numeric(can.ht_95, errors="coerce") * FT_TO_M
    can["ht_mean_m"] = pd.to_numeric(can.ht_mean, errors="coerce") * FT_TO_M
    # one height in metres for every feature that has one, either source
    can["height_m"] = can.ht_95_m.fillna(pd.to_numeric(can.og_height_m,
                                                       errors="coerce"))

    keep = ["building_id", "source", "area_m2", "yr_built", "yr_built_min",
            "yr_built_max", "yr_built_rule", "built_in_record",
            "n_improvements", "n_parcels_matched", "parcel_id",
            "roof_mat", "roof_type", "use_desc",
            "height_m", "ht_95_m", "ht_mean_m",
            "ht_mean", "ht_max", "ht_95", "co_height", "og_height_m",
            "co_source", "co_name", "og_type", "geometry"]
    can = can[keep].to_crs(OUT_CRS)

    # ── write (local-then-copy is unnecessary here: ~15 MB, but validate) ────
    tmp = Path(args.tmp_dir) / OUT_GPKG.name
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        tmp.unlink()
    can.to_file(tmp, layer=OUT_LAYER, driver="GPKG")
    chk = gpd.read_file(tmp, layer=OUT_LAYER)
    if len(chk) != len(can):
        raise SystemExit(f"validation failed: wrote {len(chk)} of {len(can)}")
    import shutil
    OUT_GPKG.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp, OUT_GPKG)
    print(f"\nwrote {OUT_GPKG}  ({OUT_GPKG.stat().st_size/1e6:.1f} MB, "
          f"{len(can):,} features)")

    # ── reporting ────────────────────────────────────────────────────────────
    yrs = can.yr_built.dropna().astype(int)
    dec = yrs.floordiv(10).mul(10).value_counts().sort_index()
    print("\nyr_built by decade")
    for d, c in dec.items():
        print(f"  {int(d)}s  {c:6,}")
    inrec = yrs.between(2000, 2024)
    stats["n_built_in_record"] = int(inrec.sum())
    stats["pct_built_in_record"] = round(100 * inrec.mean(), 2)
    print(f"BUILT INSIDE THE 2000-2024 IMAGERY RECORD: {int(inrec.sum()):,} "
          f"({100*inrec.mean():.1f}%) — the population a static footprint layer "
          f"gets wrong in the early years")

    print("\nheights — county ht_* are US SURVEY FEET (measured; see the "
          "UNITS comment in the source)")
    h = pd.to_numeric(can.ht_95_m, errors="coerce").dropna()
    stats["n_ht95"] = int(len(h))
    if len(h):
        print(f"  ht_95_m on {len(h):,} features; median {h.median():.2f} m  "
              f"p90 {h.quantile(0.9):.2f} m  max {h.max():.2f} m")
    hm = pd.to_numeric(can.height_m, errors="coerce").dropna()
    stats["n_height_m"] = int(len(hm))
    print(f"  height_m (either source) on {len(hm):,} / {len(can):,} features")

    write_readme(can, stats)
    return stats


# ── Sidecar README ───────────────────────────────────────────────────────────
def write_readme(can: gpd.GeoDataFrame, stats: dict) -> None:
    yrs = can.yr_built.dropna().astype(int)
    dec = yrs.floordiv(10).mul(10).value_counts().sort_index()
    dec_tbl = "\n".join(f"| {int(d)}s | {c:,} |" for d, c in dec.items())
    rule_tbl = "\n".join(
        f"| `{k}` | {v:,} | {100*v/len(can):.1f}% |"
        for k, v in can.yr_built_rule.value_counts().items())
    src_tbl = "\n".join(
        f"| `{k}` | {v:,} | {100*v/len(can):.1f}% |"
        for k, v in can.source.value_counts().items())
    h = pd.to_numeric(can.ht_95_m, errors="coerce").dropna()

    txt = f"""# buildings/ — the canonical Edmonds buildings layer

Generated {datetime.now().isoformat(timespec="seconds")} by
`Scripts/pipeline/build_buildings_layer.py`. Re-running the script rewrites
this file; edit the script, not this.

`buildings_canonical.gpkg`, layer **`buildings`**, **{len(can):,} structures**,
EPSG:4326.

---

## What this layer is for

Two consumers:

1. **`qc/roof_presence_matrix.py`** — the per-structure x per-year presence
   matrix. `yr_built` is its deterministic backbone; the imagery probe only has
   to resolve the {stats.get('n_built_in_record', 0):,} structures built inside
   the 2000-2024 imagery record
   ({stats.get('pct_built_in_record', 0):.1f}% of the dated stock,
   {100*stats.get('n_built_in_record', 0)/max(stats.get('n_canonical', 1), 1):.1f}%
   of the whole layer), plus the disagreements.
2. **`pipeline/make_building_masks.py`** — the per-year 1 m building-presence
   rasters that filter roofs out of the NIR / NDVI products.

## Composition

| `source` | features | share |
|---|---:|---:|
{src_tbl}

**Geometry backbone = Snohomish County `BUILDINGS__roofprints`.** It is
per-structure, carries LiDAR-derived heights, and is public-agency data. The
ONEGEO blend is used only where the county layer has no structure at all
(representative point outside every county roofprint dilated by
{GAPFILL_SLOP_M:.0f} m, and area >= {GAPFILL_MIN_AREA_M2:.0f} m2); those
features get a `OG_`-prefixed `building_id` so the key spaces cannot collide.

## Fields

| field | meaning |
|---|---|
| `building_id` | county `uniq_id`, or `OG_<onegeo id>` for gap-fill features |
| `source` | `snoco_roofprint` / `onegeo_gapfill` |
| `area_m2` | polygon area in **true metres** (computed in EPSG:26910) |
| `yr_built` | best per-structure construction year — see the join rule below |
| `yr_built_min` / `yr_built_max` | range over ALL improvements on the parcel |
| `yr_built_rule` | which branch of the join rule produced `yr_built` |
| `built_in_record` | `yr_built` falls in 2000-2024, i.e. the layer is wrong for this structure in early years unless gated |
| `n_improvements` | improvement rows on the matched parcel |
| `n_parcels_matched` | >1 means stacked condo/mobile-home parcels |
| `parcel_id` | county `parcel_id` == Assessor `PIN` |
| `roof_mat` / `roof_type` / `use_desc` | Assessor `RoofMatDesc` / `RoofTypeDesc` / `UseDesc` |
| `height_m` | **use this one.** Best height in METRES: `ht_95_m` where the county has it, else the ONEGEO modelled height |
| `ht_95_m` / `ht_mean_m` | county LiDAR heights converted to metres |
| `ht_mean` / `ht_max` / `ht_95` | the verbatim county fields — **US SURVEY FEET**, see below |
| `co_height` | the verbatim county `height` field (county rows only; presumed feet, not separately verified) |
| `og_height_m` | ONEGEO modelled height in metres (gap-fill rows only) |
| `co_source` | county provenance tag: `Microsoft` / `OMF` / `OSM` / `OSM2` / `SWM` |
| `og_type` | ONEGEO use tag, gap-fill rows only |

### Height units — MEASURED, because the service does not say

The county service publishes `ht_mean` / `ht_max` / `ht_95` with **no unit**.
They are **US survey feet**. Evidence taken 2026-08-26: 22,378 county structures
were matched to their ONEGEO counterpart, whose `height` *is* metres, giving
`median(ht_mean / onegeo_height) = 3.40` against `1 / 0.3048 = 3.281` feet per
metre. Corroborating: `ht_95` has a median of 21.97, which is 6.70 m — a normal
ridge height for an Edmonds house. Read as metres it would be 22 m, i.e. a
seven-storey house on every residential lot.

Downstream code should use **`height_m`**; the raw fields are kept only so a
value can be traced back to the service.

## The join rule (parcel-keyed record -> structure-keyed geometry)

```
roofprint --representative point within--> parcel polygon (parcel_id)
parcel_id == PIN --> N improvement rows (Assessor Improvement Records)
```

| `yr_built_rule` | features | share |
|---|---:|---:|
{rule_tbl}

- **`single`** — the parcel has exactly one improvement row (95.9% of PINs in
  the study bbox). `yr_built` is that row's `YrBuilt`.
- **`rank_finsize`** — several improvements *and* several structures on one
  parcel. Improvements are sorted by `FinSize` and structures by polygon area,
  then paired in rank order. **Caveat:** `FinSize` is finished area summed over
  stories, so a two-storey house can out-rank a physically larger single-storey
  one and invert a pairing. `yr_built_min` / `yr_built_max` are carried on every
  feature so a consumer can ignore the ranking entirely.
- **`parcel_min`** — more structures than improvements (surplus is usually an
  unassessed shed or detached garage). The surplus takes the parcel's
  **earliest** year, on the reading that an outbuilding is contemporaneous with
  or older than the house. This biases toward "present earlier", i.e. toward
  masking.
- **`none`** — no parcel matched, or no usable `YrBuilt`. Downstream must treat
  these as **undated**, not as absent.

**Condo / stacked parcels:** many condo and mobile-home parcels share one
polygon, so a structure can fall inside several parcel polygons —
{stats.get('n_multi_parcel', 0):,} did this run. Those matches are collapsed by
`building_id` (min year -> `yr_built_min`, max -> `yr_built_max`), so the layer
has exactly one row per structure.

## Join statistics (measured this run)

| | |
|---|---:|
| county roofprints fetched (study bbox) | {stats.get('n_roofprints', 0):,} |
| ONEGEO footprints read | {stats.get('n_onegeo', 0):,} |
| ONEGEO matching a county roofprint | {stats.get('n_onegeo_matched', 0):,} |
| ONEGEO added as gap-fill | {stats.get('n_gapfill', 0):,} |
| ONEGEO gaps rejected as too small | {stats.get('n_gapfill_rejected_small', 0):,} |
| **canonical structures** | **{stats.get('n_canonical', 0):,}** |
| landing inside a parcel polygon | {stats.get('n_in_parcel', 0):,} |
| falling inside >1 parcel (stacked condos, collapsed) | {stats.get('n_multi_parcel', 0):,} |
| **with a `yr_built`** | **{stats.get('n_yr_built', 0):,} ({stats.get('pct_yr_built', 0):.1f}%)** |
| with a LiDAR `ht_95` | {stats.get('n_ht95', 0):,} |
| with a `height_m` (either source) | {stats.get('n_height_m', 0):,} |
| built inside the 2000-2024 record | {stats.get('n_built_in_record', 0):,} ({stats.get('pct_built_in_record', 0):.1f}%) |

### `yr_built` by decade

| decade | structures |
|---|---:|
{dec_tbl}

### LiDAR heights (metres, converted from the county's feet)

{'`ht_95_m` present on %s features; median %.2f m, p90 %.2f m, max %.2f m'
 % (f"{len(h):,}", h.median(), h.quantile(0.9), h.max()) if len(h) else
 'no ht_95 values present'}

---

## What this layer CANNOT tell you

Read this before any temporal use.

- **`yr_built` is the improvement AS IT STANDS.** A teardown-and-rebuild carries
  the NEW year and erases the older structure, so a pre-rebuild year reads
  "nothing here" when a different house stood there.
- **Demolished structures are absent from both inputs.** Neither a current-state
  roll nor a current-state footprint layer can count what it deleted. This layer
  will never mask a building torn down before 2025.
- **Therefore assessor-PRESENT is strong evidence and assessor-ABSENT is weak.**
  That asymmetry is the design of `qc/roof_presence_matrix.py`: the record
  promotes a structure to PRESENT, but only the imagery can demote it.
- Structures finished after the input vintages (county roofprints ~2025,
  ONEGEO 2025-06) are missing from the most recent years.

## Provenance and licences

| source | what it contributed | licence |
|---|---|---|
| Snohomish County `BUILDINGS__roofprints` | geometry backbone, LiDAR `ht_mean`/`ht_max`/`ht_95`, `co_source` | county open data; portal disclaimer: "for illustrative purposes only", not an official citation to the County Code |
| Snohomish County `CADASTRAL__parcels` | the `parcel_id` bridge | same |
| Snohomish County Assessor Improvement Records | `yr_built`, `roof_mat`, `roof_type`, `use_desc` | same |
| ONEGEO GmbH blended footprints | gap-fill geometry only ({stats.get('n_gapfill', 0):,} features) | **non-transferable, resale prohibited**; ODbL upstreams (OSM, Microsoft US Building Data). See `building_footprints/README_PROVENANCE.md` |

**Publication note.** The ONEGEO gap-fill rows carry the restrictive licence
into any derivative that reconstitutes them. For anything published, filter to
`source == 'snoco_roofprint'` (or re-derive the gaps from Microsoft Global ML
Building Footprints, CDLA-Permissive-2.0). Internal analysis and masks are fine
as-is.

### Service URLs (all responded 2026-08-26)

```
roofprints   {ROOFPRINT_URL.rsplit('/query', 1)[0]}
             EPSG:2285 native; fetched in EPSG:4326
             bbox {BBOX}
parcels      https://gis.snoco.org/host/rest/services/Hosted/
             CADASTRAL__parcels/FeatureServer/0
improvements https://www.arcgis.com/sharing/rest/content/items/
             3c5edc985cec4fba8b3938d16ed1d3c3/data   (xlsx, ~99 MB)
```

## Reproducing

```
py -3.12 Scripts/qc/fetch_snoco_improvements.py     # parcels + improvements (first)
py -3.12 Scripts/pipeline/build_buildings_layer.py  # this layer
```

The raw county fetch is cached at `buildings/cache/snoco_roofprints.geojson`
and reused when its feature count matches the live service; `--refetch` forces
a new download.
"""
    OUT_README.write_text(txt, encoding="utf-8")
    print(f"wrote {OUT_README}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="build", choices=["build", "fetch"])
    ap.add_argument("--refetch", action="store_true",
                    help="ignore the roofprint cache and re-download")
    ap.add_argument("--tmp-dir", default=r"D:\edmonds-pipeline\_tmp",
                    help="local NVMe scratch — large writes land here first")
    args = ap.parse_args(argv)

    t0 = time.time()
    stats = build(args)
    print(f"\nelapsed {time.time()-t0:.1f}s")

    if write_step_log is not None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            write_step_log(script="build_buildings_layer", step=args.step,
                           logs_dir=LOGS_DIR, errors=0,
                           out_gpkg=str(OUT_GPKG),
                           **{k: v for k, v in stats.items()})
        except Exception as exc:
            print(f"[buildings] WARN could not write step log: {exc}")
    return 0


if __name__ == "__main__":
    # Colab injects `-f <json>`; strip it (CLAUDE.md rule 4).
    filtered = clean_argv()
    sys.exit(main(filtered))
