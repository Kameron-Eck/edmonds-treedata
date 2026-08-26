"""Roof-presence probe — can a DETERMINISTIC per-footprint colour rule decide
whether a roof existed in a given year's imagery?

WHY (Kam, 2026-08-26): roofs are a major NIR contaminant, building footprints
are available, and building shapes barely change. If a fixed rule can say
"a roof was standing here in 2005" from the imagery alone, we can (a) mask roofs
per-year rather than with one current-state footprint layer, and (b) get an
independent confidence signal for backward projection of crown validity.

WHAT THIS IS: a SIZING PROBE, not a product. It measures a handful of
within-footprint statistics on a small sample and applies transparent, relative
thresholds. It is not calibrated against ground truth and reports no accuracy.
See the "HONEST LIMITS" block at the bottom of this docstring.

METHOD
  For each footprint x year:
    CORE  = footprint eroded by CORE_ERODE_M          (the roof itself)
    RING  = annulus RING_INNER_M..RING_OUTER_M outside the footprint,
            MINUS every other footprint buffered by NEIGHBOUR_BUF_M
            (so an adjacent garage cannot contaminate the "surroundings")
  Both are built ONCE in EPSG:26910 (UTM 10N, TRUE METRES) and only then
  reprojected to each raster's own CRS. This matters: the King orthos are
  EPSG:3857, whose "metres" at 47.8 N are ~1.487x ground metres, and the
  Snohomish orthos are EPSG:2285, whose units are US survey FEET. Buffering in
  either would silently change the erosion distance.

  Features (all windowed reads; nothing is loaded whole):
    core/ring RGB means and std
    d_bright_rel  (core - ring) / ring          brightness contrast, relative
    d_grvi        core GRVI - ring GRVI         greenness contrast
    d_ndvi        core NDVI - ring NDVI         (4-band years only)
    core_grad_rel mean |grad(brightness)| / mean brightness   texture
    core_res_cv   std of a PLANE-FIT residual / mean          non-planarity
    core_slope_rel fitted plane gradient magnitude, %/m       Kam's "gradient
                  of colour unique to a roof" - a pitched roof shades smoothly
                  across its slope, so it fits a plane WELL (low res_cv) while
                  still carrying a real gradient (non-zero slope_rel).

  GRVI = (G-R)/(G+R) is used as the greenness proxy on 3-band years. On 4-band
  years NDVI is preferred. NOTE (IMAGERY_FACTS 12): 2015n and 2021s have LIFTED
  BLACK POINTS - absolute NDVI cuts do not apply there. This probe only ever
  uses NDVI as a core-MINUS-ring DIFFERENCE, which is immune to an additive
  offset, and the default year set avoids both anyway.

VERDICT RULE (transparent; every constant is named and commented below)
  1. too few pixels                       -> uncertain / too_small
  2. core NOT green vs ring AND core smooth -> present
  3. core green like its ring AND core rough -> absent
  4. anything else                        -> uncertain

HONEST LIMITS (do not oversell this)
  - "roof present" and "bare cleared ground" are NOT separable here. Both are
    non-green and smooth. A razed lot mid-construction reads as a roof.
  - Morning-sun imagery (Kam, IMAGERY_FACTS 11 addendum: "shadows go west")
    puts a hard shadow on one side of the annulus. No shadow model here.
  - The footprint layer is a 2025 CURRENT-STATE snapshot: a building demolished
    before 2025 has NO footprint, so this probe can never see it in any year.
  - Thresholds are provisional and were set from the observed distributions on
    this sample, not from labelled truth.
  - What would make it production-grade is in README_PROVENANCE.md next to the
    footprint data: the county assessor YrBuilt join is a deterministic answer
    to most of this question and needs no imagery model at all.

USAGE
  py -3.12 qc/roof_presence_probe.py                    # default sample
  py -3.12 qc/roof_presence_probe.py --years 2005 2013 --sector-n 50
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window
from shapely.geometry import shape
from shapely.strtree import STRtree

# ── Paths (code resolves via __file__; data via the mirror / data plane) ──────
HERE = Path(__file__).resolve().parent
REPO = HERE.parent

FOOTPRINTS = Path(r"G:\My Drive\treedata\building_footprints\data.json")
SITES_SHP = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid"
                 r"\sites_drawn_clean.shp")
SECTORS = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\sectors"
               r"\sectors_v1.gpkg")
IMAGERY_MIRROR = Path(r"D:\edmonds-pipeline\Imagery")
OUT_DIR = Path(r"G:\My Drive\treedata\phase4\qc\roof_presence")

# ── Geometry constants — ALL IN TRUE METRES (applied in EPSG:26910) ──────────
WORK_CRS = "EPSG:26910"     # UTM 10N. Real metres; 3857/2285 are not.
CORE_ERODE_M = 1.5          # inward buffer: drop the roof edge + eaves +
                            # georeferencing slop between acquisitions
RING_INNER_M = 2.0          # start the annulus clear of the wall/eave shadow
RING_OUTER_M = 5.0          # ...and stay close enough to be the same yard
NEIGHBOUR_BUF_M = 1.0       # every OTHER footprint is cut out of the ring at
                            # this buffer, so a neighbouring roof never becomes
                            # part of "the surroundings"

# ── Sample-size gates ────────────────────────────────────────────────────────
MIN_CORE_PX = 30            # below this a core statistic is noise. At 60 cm
                            # (2023n) 30 px ~ 11 m2 of eroded roof.
MIN_RING_PX = 50

# ── Verdict thresholds (relative, never absolute DN cuts) ────────────────────
# CALIBRATION (2026-08-26): set by measuring the feature distributions on the
# Development parcel, where the county assessor gives a CLEAN construction year
# per house (the Greystone subdivision: 71 houses, YrBuilt 2001-2005, built on
# graded raw land, so "absent" really means no structure). 640 labelled
# footprint-years. Per-feature separation measured there, as AUC(present>absent):
#     d_bright_rel   0.881   <- the strongest single cue
#     core_res_cv    0.844
#     core_grad_rel  0.819
#     core_slope_rel 0.778   <- Kam's "gradient unique to a roof", and it works
#     d_grvi         0.235 (i.e. 0.765 the other way: roofs are LESS green)
#     core_sat       0.403   <- no useful signal, reported only
# Thresholds are ROUND NUMBERS placed near the observed class gaps, not a
# fitted optimum. They are IN-SAMPLE for the Development parcel and have never
# been tested on an independent site. See the honest-limits block above.
ROOF_D_BRIGHT = 0.10        # core >=10% brighter than its ring => roof-like.
                            # (absent p75 = 0.075, present p50 = 0.293)
FLAT_D_BRIGHT = 0.05        # |contrast| <= 5% => core matches its surroundings
ROOF_SLOPE_REL = 0.010      # fitted plane gradient, fraction of mean per metre.
                            # A pitched roof shades smoothly along its slope.
                            # (absent p50 = 0.004, present p50 = 0.020)
ROOF_RES_CV = 0.10          # plane-fit residual CV. A gable is TWO planes plus
                            # a ridge, so one plane leaves a real residual;
                            # graded bare earth leaves almost none.
                            # (absent p50 = 0.057, present p50 = 0.200)
GRVI_D_ROOF = -0.015        # 3-band years: core markedly less green than ring
GRVI_D_VEG = -0.005         # ...or as green as its ring => vegetated
NDVI_D_ROOF = -0.15         # 4-band years, same idea on NDVI. Used ONLY as a
NDVI_D_VEG = -0.08          # core-minus-ring DIFFERENCE, so a lifted black
                            # point (2015n / 2021s, IMAGERY_FACTS 12) cancels.
N_SIGNALS_PRESENT = 2       # how many of the four roof cues must agree

FEATURE_COLS = [
    "core_px", "ring_px", "core_bright", "ring_bright", "d_bright_rel",
    "core_grvi", "ring_grvi", "d_grvi", "core_ndvi", "ring_ndvi", "d_ndvi",
    "core_grad_rel", "core_res_cv", "core_slope_rel", "core_sat",
    "core_r", "core_g", "core_b", "ring_r", "ring_g", "ring_b",
]


# ── Imagery catalog ──────────────────────────────────────────────────────────
def load_catalog():
    """YEAR_CATALOG is the one home for imagery paths (CLAUDE.md)."""
    sys.path.insert(0, str(REPO / "pipeline"))
    from phase4seg import config as C          # noqa: E402
    return {str(e["key"]): e for e in C.YEAR_CATALOG}


def resolve_year(cat, key):
    e = cat.get(str(key))
    if e is None:
        raise SystemExit(f"year key {key!r} not in YEAR_CATALOG")
    p = IMAGERY_MIRROR / e["native_file"]
    if not p.exists():
        raise SystemExit(f"{key}: {p} not on the local mirror")
    return p, e


# ── Footprints ───────────────────────────────────────────────────────────────
def load_footprints():
    """Read the ONEGEO GeoJSON preserving its per-feature `id`.

    geopandas/pyogrio drops the GeoJSON top-level "id", and that id is the only
    stable handle back into Kam's file — so parse the JSON directly.
    """
    d = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    recs, geoms = [], []
    for f in d["features"]:
        p = f.get("properties", {})
        recs.append({
            "footprint_id": f.get("id"),
            "fp_area_m2": p.get("area"),
            "fp_height_m": p.get("height"),
            "fp_type": p.get("type"),
            "fp_date": p.get("date"),
        })
        geoms.append(shape(f["geometry"]))
    return gpd.GeoDataFrame(recs, geometry=geoms, crs="EPSG:4326")


def build_core_ring(sel, allfp_work):
    """Core / ring polygons in WORK_CRS, with neighbours removed from the ring."""
    tree = STRtree(allfp_work.geometry.values)
    cores, rings = [], []
    for geom in sel.geometry.values:
        core = geom.buffer(-CORE_ERODE_M)
        ring = geom.buffer(RING_OUTER_M).difference(geom.buffer(RING_INNER_M))
        # subtract EVERY other footprint (buffered) that touches the annulus
        hits = tree.query(ring)
        for j in hits:
            other = allfp_work.geometry.values[j]
            if other.equals(geom):
                continue
            ring = ring.difference(other.buffer(NEIGHBOUR_BUF_M))
        cores.append(core)
        rings.append(ring)
    return cores, rings


# ── Feature extraction ───────────────────────────────────────────────────────
def _plane_fit(vals, rr, cc):
    """Least-squares plane through the core brightness.

    Returns (residual_std, |gradient| in DN per pixel). A pitched roof is
    strongly PLANAR — a real gradient with a small residual. Canopy is neither.
    """
    A = np.column_stack([np.ones_like(rr, dtype=np.float64),
                         rr.astype(np.float64), cc.astype(np.float64)])
    try:
        coef, *_ = np.linalg.lstsq(A, vals.astype(np.float64), rcond=None)
    except np.linalg.LinAlgError:
        return np.nan, np.nan
    resid = vals - A @ coef
    return float(resid.std()), float(np.hypot(coef[1], coef[2]))


def measure(src, core_geom, ring_geom, has_nir):
    """Windowed read + per-footprint statistics. None if the window is unusable."""
    minx, miny, maxx, maxy = ring_geom.bounds
    try:
        win = rasterio.windows.from_bounds(minx, miny, maxx, maxy,
                                           transform=src.transform)
    except Exception:
        return None
    # snap out to whole pixels, then pad one pixel so the gradient stencil has
    # a neighbour at the window edge (rasterio dropped Window.round_offsets(op))
    c0 = int(np.floor(win.col_off)) - 1
    r0 = int(np.floor(win.row_off)) - 1
    c1 = int(np.ceil(win.col_off + win.width)) + 1
    r1 = int(np.ceil(win.row_off + win.height)) + 1
    win = Window(c0, r0, c1 - c0, r1 - r0)
    win = win.intersection(Window(0, 0, src.width, src.height))
    if win.width < 4 or win.height < 4:
        return None

    arr = src.read(window=win).astype(np.float32)
    tr = src.window_transform(win)
    shp = arr.shape[1:]

    core_m = ~geometry_mask([core_geom], out_shape=shp, transform=tr,
                            invert=False) if not core_geom.is_empty else \
        np.zeros(shp, bool)
    ring_m = ~geometry_mask([ring_geom], out_shape=shp, transform=tr,
                            invert=False) if not ring_geom.is_empty else \
        np.zeros(shp, bool)

    r, g, b = arr[0], arr[1], arr[2]
    valid = np.isfinite(r)
    if src.nodata is not None:
        valid &= ~np.all(arr == src.nodata, axis=0)
    valid &= ~((r == 0) & (g == 0) & (b == 0))     # black fill in the orthos
    core_m &= valid
    ring_m &= valid

    out = {c: np.nan for c in FEATURE_COLS}
    out["core_px"] = int(core_m.sum())
    out["ring_px"] = int(ring_m.sum())
    if out["core_px"] < 3 or out["ring_px"] < 3:
        return out

    bright = (r + g + b) / 3.0
    eps = 1e-6
    grvi = (g - r) / (g + r + eps)
    ndvi = ((arr[3] - r) / (arr[3] + r + eps)) if has_nir else None

    for tag, m in (("core", core_m), ("ring", ring_m)):
        out[f"{tag}_bright"] = float(bright[m].mean())
        out[f"{tag}_grvi"] = float(grvi[m].mean())
        out[f"{tag}_r"] = float(r[m].mean())
        out[f"{tag}_g"] = float(g[m].mean())
        out[f"{tag}_b"] = float(b[m].mean())
        if ndvi is not None:
            out[f"{tag}_ndvi"] = float(ndvi[m].mean())

    rb = out["ring_bright"]
    out["d_bright_rel"] = ((out["core_bright"] - rb) / rb) if rb > eps else np.nan
    out["d_grvi"] = out["core_grvi"] - out["ring_grvi"]
    if ndvi is not None:
        out["d_ndvi"] = out["core_ndvi"] - out["ring_ndvi"]

    cb = out["core_bright"]
    mx = max(out["core_r"], out["core_g"], out["core_b"])
    mn = min(out["core_r"], out["core_g"], out["core_b"])
    out["core_sat"] = float((mx - mn) / mx) if mx > eps else np.nan

    # texture + planarity, on the core only
    gy, gx = np.gradient(bright)
    gmag = np.hypot(gy, gx)
    out["core_grad_rel"] = float(gmag[core_m].mean() / cb) if cb > eps else np.nan

    rr, cc = np.nonzero(core_m)
    res_std, slope_dn_px = _plane_fit(bright[core_m], rr, cc)
    if cb > eps and np.isfinite(res_std):
        out["core_res_cv"] = float(res_std / cb)
        px_m = abs(tr.a) / (1.487 if src.crs.to_epsg() == 3857 else
                            (0.3048 if src.crs.to_epsg() in (2285, 2926) else 1.0))
        out["core_slope_rel"] = float(slope_dn_px / px_m / cb) if px_m > 0 \
            else np.nan
    return out


# ── Verdict ──────────────────────────────────────────────────────────────────
def verdict(row):
    """Transparent rule. Returns (verdict, reason, n_signals).

    Four independent ROOF cues, each a named constant above:
        B  the core is distinctly brighter than its ring
        G  the core is distinctly less green than its ring
        S  the core carries a real plane gradient (a pitched, shaded surface)
        R  the core is not a single flat plane (ridge / facets / roof clutter)
    present  = at least N_SIGNALS_PRESENT of them fire
    absent   = NONE fires AND the core both matches its ring in brightness and
               is as green as its ring
    uncertain= everything in between, which is where the honest answer is
    """
    if not np.isfinite(row["core_px"]) or row["core_px"] < MIN_CORE_PX:
        return "uncertain", "too_small_core", 0
    if row["ring_px"] < MIN_RING_PX:
        return "uncertain", "too_small_ring", 0

    # prefer NDVI where the year carries NIR; both are used as a DIFFERENCE
    use_ndvi = np.isfinite(row.get("d_ndvi", np.nan))
    dg = row["d_ndvi"] if use_ndvi else row["d_grvi"]
    d_roof = NDVI_D_ROOF if use_ndvi else GRVI_D_ROOF
    d_veg = NDVI_D_VEG if use_ndvi else GRVI_D_VEG

    db, sl, res = row["d_bright_rel"], row["core_slope_rel"], row["core_res_cv"]
    if not np.isfinite(db):
        return "uncertain", "no_features", 0

    sig = {
        "B": bool(db >= ROOF_D_BRIGHT),
        "G": bool(np.isfinite(dg) and dg <= d_roof),
        "S": bool(np.isfinite(sl) and sl >= ROOF_SLOPE_REL),
        "R": bool(np.isfinite(res) and res >= ROOF_RES_CV),
    }
    n = sum(sig.values())
    fired = "".join(k for k, v in sig.items() if v) or "-"

    if n >= N_SIGNALS_PRESENT:
        return "present", f"roof_cues:{fired}", n
    if n == 0 and abs(db) <= FLAT_D_BRIGHT and (not np.isfinite(dg)
                                                or dg >= d_veg):
        return "absent", "matches_surroundings", n
    return "uncertain", f"weak_cues:{fired}", n


# ── Sample construction ──────────────────────────────────────────────────────
def join_assessor(sample, gpkg):
    """Attach the county construction year to each footprint.

    A footprint's representative point is placed in the parcel polygon that
    contains it; that parcel's EARLIEST improvement year is used, because the
    question is "was anything standing here", not "how old is the main house".

    THIS IS A PROXY TRUTH, NOT TRUTH. YrBuilt carries the CURRENT improvement:
    a teardown-and-rebuild reports the new year and erases the old structure,
    so on an established street a pre-rebuild "absent" label can be flat wrong.
    It is only trustworthy on greenfield land — which is exactly what the
    Development parcel is, and why the calibration used only that site.
    """
    if not Path(gpkg).exists():
        print(f"  (no assessor layer at {gpkg} — skipping the year-built join;"
              f" run qc/fetch_snoco_improvements.py to build it)")
        for c in ("assessor_parcel_id", "assessor_yrbuilt", "assessor_roof_mat"):
            sample[c] = None
        return sample
    par = gpd.read_file(gpkg, layer="parcels_yrbuilt").to_crs(sample.crs)
    par = par[["parcel_id", "yrbuilt_min", "roof_mat", "geometry"]]
    pts = gpd.GeoDataFrame(sample[["footprint_id"]],
                           geometry=sample.representative_point(),
                           crs=sample.crs)
    j = gpd.sjoin(pts, par, how="left", predicate="within")
    # a parcel polygon can be stacked (condos); keep the earliest year
    j = (j.groupby("footprint_id")
           .agg(assessor_parcel_id=("parcel_id", "first"),
                assessor_yrbuilt=("yrbuilt_min", "min"),
                assessor_roof_mat=("roof_mat", "first"))
           .reset_index())
    out = sample.merge(j, on="footprint_id", how="left")
    n = out.assessor_yrbuilt.notna().sum()
    print(f"  assessor year-built joined to {n} / {len(out)} footprints")
    return out


def build_sample(fp, sector_id, sector_n, seed):
    dev = gpd.read_file(SITES_SHP)
    dev = dev[(dev.site == "Development") & (dev.role == "region")]
    dev_geom = dev.to_crs(fp.crs).geometry.union_all()

    sec = gpd.read_file(SECTORS, layer="sectors")
    sec = sec[sec.id == sector_id]
    if sec.empty:
        raise SystemExit(f"sector {sector_id!r} not in {SECTORS}")
    sec_geom = sec.to_crs(fp.crs).geometry.union_all()

    rp = fp.representative_point()
    in_dev = fp[rp.within(dev_geom)].copy()
    in_dev["aoi"] = "Development"
    in_sec = fp[rp.within(sec_geom)].copy()
    in_sec = in_sec[~in_sec.footprint_id.isin(in_dev.footprint_id)]
    if len(in_sec) > sector_n:
        in_sec = in_sec.sample(n=sector_n, random_state=seed)
    in_sec = in_sec.copy()
    in_sec["aoi"] = f"sector_{sector_id}"
    return pd.concat([in_dev, in_sec]), dev_geom, sec_geom


# ── Main ─────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+",
                    default=["2000", "2002", "2003s", "2005", "2007", "2013",
                             "2019s", "2023n"],
                    help="YEAR_CATALOG keys. The default spans the record AND "
                         "brackets the Development parcel's 2001-2005 build-out "
                         "so the mini-timeline can show the transition, not "
                         "just its endpoints.")
    ap.add_argument("--sector", default="S3")
    ap.add_argument("--sector-n", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--assessor",
                    default=str(OUT_DIR / "snoco_parcels_yrbuilt.gpkg"),
                    help="parcel year-built layer from "
                         "qc/fetch_snoco_improvements.py (optional)")
    args = ap.parse_args(argv)

    cat = load_catalog()
    print("loading footprints ...", flush=True)
    fp = load_footprints()
    print(f"  {len(fp):,} footprints  crs={fp.crs}")

    sample, dev_geom, sec_geom = build_sample(fp, args.sector, args.sector_n,
                                              args.seed)
    print(f"sample: {len(sample):,} footprints  "
          f"({(sample.aoi == 'Development').sum()} Development, "
          f"{(sample.aoi != 'Development').sum()} {args.sector} "
          f"seed={args.seed})")
    sample = join_assessor(sample, Path(args.assessor))

    # Buffering happens ONCE, in true metres.
    sample_w = sample.to_crs(WORK_CRS)
    # neighbours: every footprint near the sample, so adjacent structures are
    # cut out of the rings even when they were not themselves sampled
    aoi_w = gpd.GeoSeries([dev_geom, sec_geom],
                          crs=fp.crs).to_crs(WORK_CRS).union_all()
    near = fp.to_crs(WORK_CRS)
    near = near[near.intersects(aoi_w.buffer(RING_OUTER_M + 5))]
    print(f"  neighbour footprints considered for ring cut-out: {len(near):,}")

    cores, rings = build_core_ring(sample_w, near)
    sample_w = sample_w.assign(_core=cores, _ring=rings)
    keep = [i for i, (c, r) in enumerate(zip(cores, rings))
            if (not c.is_empty) and (not r.is_empty)]
    dropped = len(sample_w) - len(keep)
    sample_w = sample_w.iloc[keep]
    if dropped:
        print(f"  dropped {dropped} footprints with an empty core or ring "
              f"(smaller than the {CORE_ERODE_M} m erosion)")

    rows = []
    for ykey in args.years:
        path, meta = resolve_year(cat, ykey)
        t0 = time.time()
        with rasterio.open(path) as src:
            has_nir = src.count >= 4
            core_r = gpd.GeoSeries(sample_w._core.values,
                                   crs=WORK_CRS).to_crs(src.crs).values
            ring_r = gpd.GeoSeries(sample_w._ring.values,
                                   crs=WORK_CRS).to_crs(src.crs).values
            n_ok = 0
            for k in range(len(sample_w)):
                rec = sample_w.iloc[k]
                m = measure(src, core_r[k], ring_r[k], has_nir)
                if m is None:
                    m = {c: np.nan for c in FEATURE_COLS}
                    m["core_px"] = m["ring_px"] = 0
                v, why, nsig = verdict(m)
                n_ok += (v != "uncertain")
                rows.append({
                    "footprint_id": rec.footprint_id,
                    "aoi": rec.aoi,
                    "year": ykey,
                    "year_num": int(str(ykey)[:4]),
                    "gsd_cm": meta["gsd_cm"],
                    "bands": meta["bands"],
                    "fp_area_m2": rec.fp_area_m2,
                    "fp_height_m": rec.fp_height_m,
                    "fp_type": rec.fp_type,
                    "fp_date": rec.fp_date,
                    "assessor_parcel_id": rec.get("assessor_parcel_id"),
                    "assessor_yrbuilt": rec.get("assessor_yrbuilt"),
                    "assessor_roof_mat": rec.get("assessor_roof_mat"),
                    **m,
                    "verdict": v,
                    "reason": why,
                    "n_signals": nsig,
                })
        print(f"  {ykey:<6} {meta['gsd_cm']:>5.1f} cm  {meta['bands']}-band  "
              f"{len(sample_w)} footprints  decided={n_ok}  "
              f"{time.time()-t0:.1f}s", flush=True)

    df = pd.DataFrame(rows)
    # proxy truth, where the assessor gave a year (see join_assessor caveats)
    yb = pd.to_numeric(df.assessor_yrbuilt, errors="coerce")
    df["assessor_truth"] = np.where(
        yb.isna(), "unknown",
        np.where(df.year_num >= yb, "present", "absent"))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "roof_presence_sample.csv"
    df.to_csv(out, index=False, float_format="%.5f")
    print(f"\nwrote {out}  ({len(df):,} rows)")

    # ── reporting ────────────────────────────────────────────────────────────
    print("\nVERDICTS by AOI x year")
    print((df.groupby(["aoi", "year", "verdict"]).size()
             .unstack(fill_value=0)
             .reindex(columns=["present", "absent", "uncertain"],
                      fill_value=0)).to_string())

    print("\nWHY (reason codes; roof cues B=brighter G=less-green "
          "S=plane-gradient R=non-planar)")
    print(df.reason.value_counts().to_string())

    print("\n" + "=" * 78)
    print("DEVELOPMENT PARCEL MINI-TIMELINE")
    print("Kam's clear-and-rebuild site = the Greystone subdivision. The county")
    print("assessor dates every house here (built 2001-2005 on graded raw land),")
    print("so this is the one place in the sample where 'absent' is trustworthy.")
    print("=" * 78)
    d = df[df.aoi == "Development"]
    lines = []
    for y in args.years:
        s = d[d.year == y]
        if s.empty:
            continue
        tp = (s.assessor_truth == "present").sum()
        known = (s.assessor_truth != "unknown").sum()
        lines.append({
            "year": y, "gsd_cm": s.gsd_cm.iloc[0], "n": len(s),
            "assessor_built": f"{tp}/{known}" if known else "-",
            "PRESENT": int((s.verdict == "present").sum()),
            "ABSENT": int((s.verdict == "absent").sum()),
            "uncert": int((s.verdict == "uncertain").sum()),
            "pct_called_present": round(100 * (s.verdict == "present").mean(), 1),
            "pct_truth_present": (round(100 * tp / known, 1) if known else None),
            "med_d_bright": round(float(np.nanmedian(s.d_bright_rel)), 4),
            "med_slope": round(float(np.nanmedian(s.core_slope_rel)), 4),
            "med_res_cv": round(float(np.nanmedian(s.core_res_cv)), 4),
        })
    print(pd.DataFrame(lines).to_string(index=False))

    print("\nAGREEMENT WITH THE ASSESSOR, Development only (in-sample: the")
    print("thresholds were calibrated here, so this is NOT a held-out score)")
    dd = d[(d.assessor_truth != "unknown") & (d.verdict != "uncertain")]
    dall = d[d.assessor_truth != "unknown"]
    if len(dd):
        print(f"  decided {len(dd)}/{len(dall)} "
              f"({100*len(dd)/max(len(dall),1):.1f}% coverage)   "
              f"agreement {100*(dd.verdict == dd.assessor_truth).mean():.1f}%")
        print(pd.crosstab(dd.assessor_truth, dd.verdict).to_string())

    other = df[df.aoi != "Development"]
    if len(other):
        print(f"\n{other.aoi.iloc[0]} — APPLICATION ONLY, no accuracy claim.")
        print("This is an established neighbourhood (most houses predate the")
        print("record), so a correct probe should say PRESENT in every year, and")
        print("the assessor's 'absent' rows here are mostly teardown/rebuild")
        print("artefacts rather than genuinely empty ground.")
        print((other.groupby(["year", "verdict"]).size()
                    .unstack(fill_value=0)).to_string())

    print("\nFEATURE MEDIANS by AOI x year — for threshold audit")
    fcols = ["d_bright_rel", "core_slope_rel", "core_res_cv", "core_grad_rel",
             "d_grvi", "d_ndvi"]
    print(df.groupby(["aoi", "year"])[fcols].median().round(4).to_string())

    print("\nEXAMPLE ROWS")
    cols = ["footprint_id", "aoi", "year", "core_px", "d_bright_rel",
            "core_slope_rel", "core_res_cv", "d_grvi", "d_ndvi",
            "assessor_yrbuilt", "verdict", "reason"]
    print(df.sample(n=min(10, len(df)), random_state=args.seed)[cols]
            .to_string(index=False))
    return 0


if __name__ == "__main__":
    # Colab injects `-f <json>`; strip it (CLAUDE.md rule 4).
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    sys.exit(main(filtered))
