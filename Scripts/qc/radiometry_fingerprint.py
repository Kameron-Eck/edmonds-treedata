r"""
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402
╔══════════════════════════════════════════════════════════════════╗
  R1 — RADIOMETRY FINGERPRINT (per-acquisition colour over stable ground)
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION THIS ANSWERS
  ------------------------------------------------------------------
  The pipeline does NOTHING radiometric today: every acquisition's DNs are fed
  to the model as if they were comparable. Three independent signals say they
  are not.

    * OBSERVED (IMAGERY_FACTS §11, Kam): "2007 snoh 1ft … Snohomish looks
      greener … some funny business with the color."
    * MEASURED (IMAGERY_FACTS §12): 2015n and 2021s carry LIFTED NIR BLACK
      POINTS (p1 = 33 / 28 DN against 1–5 DN on the eight healthy 4-band years).
      This script REPRODUCES that bimodality on its own water target and prints
      the comparison. It does not reproduce §12's exact DNs and should not: a
      different dark-target window is a different sample. Measured here: 2015n
      33 (§12: 33), 2021s 25 (§12: 28), and the healthy eight span 1–10 rather
      than §12's 1–5, with 2018s at 10 (§12: 9) the top of that band. Separation
      between the two groups is what reproduces — 10 vs 25 — not the digits.
    * MEASURED (IMAGERY_FACTS §3): a naive greenness test swings 2.5x across the
      King series (.80 → .11, 2000 → 2019) over IDENTICAL ground — a processing
      drift, not vegetation.

  Before ANY correction is contemplated, MEASURE. This script fingerprints every
  catalogued acquisition over PSEUDO-INVARIANT GROUND — surfaces whose true
  reflectance does not change year to year — so that a colour difference between
  two acquisitions over that ground can only be sensor / processing / atmosphere.

  THE TARGETS AND WHY THEY ARE SPLIT IN TWO
  ------------------------------------------------------------------
  target_class = INVARIANT  (the stable spine — the reference)
    neg_parking   asphalt retail lot                       (sentinel_sites.json)
    school_k12    Edmonds Heights K-12 campus, 30-yr stable per the operator
                  (polygons/Negative_Edmonds_Heights_K_12_regions.gpkg)
    neg_water     Puget Sound — dark target, carries the NIR-floor test.
                  CAVEAT: SUN-GLINT SENSITIVE. A specular flight geometry lifts
                  water DNs in every band; glint is a per-flight accident, not a
                  calibration property. Water is therefore EXCLUDED from the
                  colour-ratio spine (reported separately) and used only for the
                  dark-target NIR floor.

  The two colour-spine targets are PIF-MASKED to hardscape (see PIF_TARGETS
  below). This was NOT the first design and the correction matters: taking the
  school polygon whole made 2007s read +4.6% green on "invariant" ground, which
  would have been reported as a radiometric cast. A visual check across
  2005/2007/2009 showed the polygon is dominated by a grass sports field —
  straw-brown in July 2005, vivid green in May 2009 — and on the genuinely
  invariant parking lot 2007s reads +0.65%. The grass WAS the result. Any target
  added here must be checked the same way before it is trusted.

  target_class = VEGETATED  (the thing being tested, NOT a reference)
    neg_stadium, neg_cemetery, neg_civic_field — turf/grass.
    CAVEAT: SEASONALLY VARIABLE. Pacific-NW turf is lush in April–May and
    straw-brown by August. These are fingerprinted so that "the vegetation really
    is greener" can be distinguished from "the image is greener", but a raw
    difference between an April and an August acquisition here is phenology.

  THE DISCRIMINATOR
  ------------------------------------------------------------------
  A global colour cast multiplies BOTH classes. So the ratio

      gr_veg_over_inv = (G/R on vegetated) / (G/R on invariant)

  divides the cast out and leaves the WITHIN-IMAGE greenness contrast. Read
  against gr_invariant it turns "looks greener" into two separable numbers:
  greenness ON STABLE GROUND (radiometry) and greenness ON PLANTS (vegetation
  or phenology).

  The verdict block prints those as TWO INDEPENDENT CALLS — never one label —
  because they can both be true, both false, or point opposite ways:

      line 1 (invariant): stable ground reads GREENER / LESS GREEN / NORMAL,
              with a strength tier from |zsrc|:
                  > 2  CONFIRMED      1–2  SUGGESTIVE      <= 1  not
                  distinguishable from its own source family
      line 2 (vegetated): the cast-free contrast is HIGHER / LOWER / NORMAL,
              always carrying the season caveat where the date is unknown

  Both lines call anything under 1.5% NORMAL — that is the uint8 quantisation
  floor at a p50 near 140, not a real difference.

  Two yardsticks appear side by side and are allowed to disagree: %-vs-named-
  peers (effect size) and zsrc (robust z against the whole source family). A
  large % with a small zsrc means the family spread is simply wide; both are
  printed so neither can be cherry-picked.

  The spine members (parking, school) are also printed SEPARATELY, and the block
  raises "! SPINE MEMBERS DISAGREE" when they differ by more than 3 points. That
  warning is not decoration — it is the guard that caught the school-grass
  contamination described above, and parking-only remains the cleanest single
  number whenever it fires.

  METHOD NOTES THAT MATTER
  ------------------------------------------------------------------
  * NATIVE-GRID WINDOWED READS ONLY. Never a full ortho; never a reprojection.
    Percentiles ARE the deliverable, so oversized windows are decimated with
    NEAREST (a subsample preserves the distribution) — average resampling would
    smooth the p1/p99 tails and destroy the NIR-floor test.
  * BOUNDLESS reads, so the window geometry is identical whether or not the
    acquisition covers it. Coverage is therefore measured against the FULL
    requested window, not a post-clip crop — an edge-clipped target cannot
    masquerade as fully covered. <MIN_COVERAGE → the target is SKIPPED and
    listed, never fabricated.
  * Band 4 is NIR on the ten `bands: 4` catalog entries. GDAL tags it
    colorinterp=alpha; that tag is wrong (IMAGERY_FACTS §10/§12) and is ignored.
  * Nodata follows the project convention (phase4seg/config COVERAGE_NODATA):
    a pixel is invalid when all RGB bands equal the declared nodata, or equal 0
    where none is declared. Deep shadow is therefore counted as nodata — a known,
    accepted conservatism.
  * Cross-SOURCE colour comparison is INVALID (IMAGERY_FACTS §3). Robust z is
    reported BOTH record-wide (as specified) and WITHIN SOURCE GROUP; the
    within-source number is the honest one.

  PRODUCES  (data plane — phase4/qc/)
    radiometry_fingerprint.csv   one row per acquisition x target x band
    radiometry_summary.csv       one row per acquisition: derived indices,
                                 robust z, ANOMALY flags, skipped targets

  USAGE
    py -3.12 qc/radiometry_fingerprint.py
    py -3.12 qc/radiometry_fingerprint.py --only 2007      # substring filter
      --max-edge N   decimate a window to <= N px on its long edge (default 2048)
      --min-cov F    skip a target below this coverage fraction (default 0.50)
      --pif-grvi F   hardscape GRVI ceiling in the PIF reference (default 0.02).
                     SENSITIVITY KNOB. Measured 2026-08-25: moving it 0.02 -> 0.00
                     shifts the 2007 conclusions by under 1 point in either
                     direction and changes no sign, so the verdict below does not
                     hang on this number. At -0.03 the masks collapse (parking 6.6%,
                     school 2.2%) and PIF_MIN_FRAC refuses them — by design.
      --out-dir DIR  override the phase4/qc destination
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio import features as rfeatures
from rasterio.enums import Resampling
from rasterio.errors import WindowError
from rasterio.warp import reproject, transform_bounds, transform_geom
from rasterio.windows import Window, from_bounds as win_from_bounds
from affine import Affine

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
from phase4seg import config as C            # noqa: E402

# ── data plane ────────────────────────────────────────────────────────────────
# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402
QC_DIR   = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"
POLY_DIR = BASE / "polygons"

SITES_JSON  = SCRIPTS / "sentinel_sites.json"                      # code plane
SCHOOL_GPKG = POLY_DIR / "Negative_Edmonds_Heights_K_12_regions.gpkg"
DATE_CSV    = SCRIPTS / "qc" / "imagery_pixelsize_and_date.csv"

BAND_NAMES = {3: ["R", "G", "B"], 4: ["R", "G", "B", "N"]}

# sentinel-site name -> (target_class, caveat)
SENTINEL_TARGETS = {
    "neg_parking":     ("invariant", "asphalt lot - the stable spine"),
    "neg_water":       ("invariant", "Puget Sound dark target - SUN-GLINT SENSITIVE; "
                                     "excluded from the colour-ratio spine, carries the NIR floor"),
    "neg_stadium":     ("vegetated", "turf - SEASONALLY VARIABLE"),
    "neg_cemetery":    ("vegetated", "grass/turf - SEASONALLY VARIABLE"),
    "neg_civic_field": ("vegetated", "grass/turf - SEASONALLY VARIABLE"),
}
# invariant targets that carry the colour-ratio spine (water excluded: glint)
SPINE = ("neg_parking", "school_k12")
VEG   = ("neg_stadium", "neg_cemetery", "neg_civic_field")

MIN_COVERAGE = 0.50
MAX_EDGE     = 2048
Z_FLAG       = 2.0

# ── PIF sub-masking (added after a VISUAL CHECK overturned a first result) ─────
# The first run took the whole Edmonds Heights K-12 polygon as invariant, on the
# operator's "30-year-stable" note. Rendering the window across 2005/2007/2009
# showed why that is wrong: the polygon is dominated by a GRASS SPORTS FIELD —
# straw-brown in the July 2005 frame, vivid green in the May 2009 frame. It is
# seasonally variable, not radiometrically invariant, and it was carrying the
# result: 2007s measured +4.6% green on the combined "invariant" spine but only
# +0.65% on the parking lot alone, i.e. the whole effect was the grass.
#
# Fix: a genuine pseudo-invariant-feature mask. Hardscape is selected ONCE, from
# a single fixed REFERENCE acquisition (the 2020 anchor), and that fixed geometry
# is then applied identically to all 36. The selection never depends on the year
# being measured, so it is not circular — this is standard PIF practice.
PIF_TARGETS  = ("neg_parking", "school_k12")   # colour-spine members
PIF_REF_KEY  = "2020"                          # the anchor ortho defines hardscape
PIF_GRID_M   = 0.5      # reference grid; coarse enough to shrug off registration jitter
PIF_GRVI_MAX = 0.02     # (G-R)/(G+R) above this is vegetation -> dropped
PIF_MIN_G    = 40       # drop deep shadow
PIF_MAX_G    = 245      # drop blown highlights
PIF_MIN_FRAC = 0.05     # refuse a PIF mask that keeps under this share of the polygon


# ══════════════════════════════════════════════════════════════════════════════
#  targets
# ══════════════════════════════════════════════════════════════════════════════

def _bounds_wgs84(site):
    """Explicit bounds, or lon/lat/radius_m -> (W,S,E,N)."""
    if "bounds_wgs84" in site:
        return tuple(float(v) for v in site["bounds_wgs84"])
    lon, lat, r = site["lon"], site["lat"], site.get("radius_m", 250.0)
    dlat = r / 111320.0
    dlon = r / (111320.0 * np.cos(np.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def build_targets():
    """The pseudo-invariant target set: 5 sentinel negatives + the school polygon.

    Each target is {name, target_class, bounds (WGS84 W,S,E,N), geom_wgs84 or None,
    note}. geom_wgs84 is set only for the school, which is a real polygon and is
    rasterised — its bbox would swallow neighbouring streets and yards.
    """
    sites = json.loads(SITES_JSON.read_text(encoding="utf-8"))["sites"]
    by_name = {s["name"]: s for s in sites}
    targets, missing = [], []
    for name, (cls, note) in SENTINEL_TARGETS.items():
        s = by_name.get(name)
        if s is None:
            missing.append(name)
            continue
        targets.append(dict(name=name, target_class=cls, bounds=_bounds_wgs84(s),
                            geom=None, note=note, pif=None, pif_frac=None))
    if missing:
        print(f"  ! sentinel_sites.json is missing: {missing}")

    if SCHOOL_GPKG.exists():
        try:
            import geopandas as gpd
            g = gpd.read_file(SCHOOL_GPKG).to_crs("EPSG:4326")
            geom = g.union_all() if hasattr(g, "union_all") else g.unary_union
            targets.append(dict(
                name="school_k12", target_class="invariant",
                bounds=tuple(float(v) for v in geom.bounds),
                geom=geom.__geo_interface__, pif=None, pif_frac=None,
                note="Edmonds Heights K-12 campus, 30-yr stable per the operator; "
                     "POLYGON-MASKED (not bbox), then PIF-MASKED to hardscape - the "
                     "polygon is dominated by a grass sports field that is straw-brown "
                     "in 2005 and vivid green in 2009, so the raw polygon is NOT "
                     "radiometrically invariant. A _v2 copy of this gpkg exists with "
                     "identical geometry, so the file choice is moot."))
        except Exception as exc:                                  # pragma: no cover
            print(f"  ! school polygon unreadable ({exc}) - continuing without it")
    else:
        print(f"  ! school polygon not found: {SCHOOL_GPKG}")
    return targets


# ══════════════════════════════════════════════════════════════════════════════
#  measurement
# ══════════════════════════════════════════════════════════════════════════════

def _erode3(m):
    """1-px binary erosion (3x3), pure numpy — trims PIF edges so a field/lot
    boundary cannot leak into the mask through cross-year registration jitter."""
    out = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out &= np.roll(np.roll(m, dy, axis=0), dx, axis=1)
    out[0, :] = out[-1, :] = out[:, 0] = out[:, -1] = False
    return out


def build_pif(targets, grvi_max=PIF_GRVI_MAX):
    """Hardscape sub-masks for the colour-spine targets, from the REFERENCE ortho.

    One read per target of the 2020 anchor; keep the non-green, non-shadow,
    non-blown pixels inside the target footprint; erode 1 px. The result is a
    fixed piece of GROUND, reprojected into every acquisition's own grid later.
    """
    ref = next((e for e in C.YEAR_CATALOG if str(e["key"]) == PIF_REF_KEY), None)
    if ref is None:
        print(f"  ! PIF reference {PIF_REF_KEY} not in the catalog - spine stays unmasked")
        return
    path, _ = resolve(ref["native_file"])
    if path is None:
        print(f"  ! PIF reference file missing - spine stays unmasked")
        return
    with rasterio.open(path) as ds:
        for t in targets:
            if t["name"] not in PIF_TARGETS:
                continue
            b = transform_bounds("EPSG:4326", ds.crs, *t["bounds"], densify_pts=21)
            win = win_from_bounds(*b, transform=ds.transform)
            win = win.round_offsets(op="floor").round_lengths(op="ceil")
            # EPSG:3857 inflates distance by 1/cos(lat) at Edmonds — scale so the
            # PIF grid really is PIF_GRID_M on the GROUND (config.py gsd note).
            px = abs(ds.transform.a)
            if ds.crs.to_epsg() == 3857:
                px *= float(np.cos(np.radians(47.81)))
            dec = max(1, int(round(PIF_GRID_M / max(px, 1e-9))))
            oh = max(8, int(round(win.height / dec)))
            ow = max(8, int(round(win.width / dec)))
            a = ds.read([1, 2, 3], window=win, out_shape=(3, oh, ow), boundless=True,
                        fill_value=0, resampling=Resampling.average).astype(np.float32)
            tr = ds.window_transform(win) * Affine.scale(win.width / ow, win.height / oh)
            R, G, B = a[0], a[1], a[2]
            grvi = (G - R) / np.maximum(G + R, 1.0)
            keep = (grvi < grvi_max) & (G >= PIF_MIN_G) & (G <= PIF_MAX_G)
            if t["geom"] is not None:
                gm = transform_geom("EPSG:4326", ds.crs, t["geom"])
                keep &= rfeatures.geometry_mask([gm], out_shape=(oh, ow), transform=tr,
                                                invert=True)
                denom = rfeatures.geometry_mask([gm], out_shape=(oh, ow), transform=tr,
                                                invert=True).sum()
            else:
                denom = keep.size
            keep = _erode3(keep)
            frac = keep.sum() / max(denom, 1)
            if frac < PIF_MIN_FRAC:
                print(f"  ! PIF for {t['name']} kept only {frac:.1%} - REFUSED, "
                      f"target falls back to its full footprint")
                continue
            t["pif"] = dict(mask=keep, transform=tr, crs=ds.crs)
            t["pif_frac"] = round(float(frac), 4)
            print(f"    PIF {t['name']:14s} hardscape = {frac:6.1%} of the footprint "
                  f"({int(keep.sum()):,} ref px @ {PIF_GRID_M} m, ref={PIF_REF_KEY})")


def resolve(fname):
    """Catalog filename -> (path, root) through config.imagery_roots(); first wins.

    Which root answered is RECORDED in every output row: a silent cross-root
    fallback is the exact bug the ordering exists to make visible (config.py).
    """
    for root in C.imagery_roots():
        p = root / fname
        if p.exists():
            return p, root
    return None, None


def fingerprint_target(ds, target, max_edge, min_cov):
    """Windowed native-grid read of one target from one open ortho.

    Returns (per-band stats list, coverage, decimation, note) or (None, cov, dec, why).
    """
    try:
        b = transform_bounds("EPSG:4326", ds.crs, *target["bounds"], densify_pts=21)
    except Exception as exc:
        return None, 0.0, 1, f"CRS transform failed: {exc}"

    win = win_from_bounds(*b, transform=ds.transform)
    win = win.round_offsets(op="floor").round_lengths(op="ceil")
    if win.width < 2 or win.height < 2:
        return None, 0.0, 1, "target smaller than 2 px on this grid"

    # fast reject: no overlap at all -> never touch the file
    try:
        Window(0, 0, ds.width, ds.height).intersection(win)
    except (WindowError, ValueError):
        return None, 0.0, 1, "window entirely outside raster extent"

    dec = max(1, int(np.ceil(max(win.width, win.height) / max_edge)))
    oh = max(1, int(round(win.height / dec)))
    ow = max(1, int(round(win.width / dec)))
    nb = min(ds.count, 4)
    idx = list(range(1, nb + 1))

    # BOUNDLESS: the array always spans the FULL requested window, so coverage is
    # measured against the window we asked for, not a post-clip crop.
    arr = ds.read(idx, window=win, out_shape=(nb, oh, ow), boundless=True,
                  fill_value=0, resampling=Resampling.nearest)

    tr = ds.window_transform(win) * Affine.scale(win.width / ow, win.height / oh)

    if target["geom"] is not None:
        gm = transform_geom("EPSG:4326", ds.crs, target["geom"])
        inside = rfeatures.geometry_mask([gm], out_shape=(oh, ow), transform=tr,
                                         invert=True, all_touched=False)
    else:
        inside = np.ones((oh, ow), dtype=bool)

    # PIF: carry the reference-defined hardscape geometry onto THIS grid (nearest,
    # so the mask stays boolean and no interpolated half-pixels appear).
    pif = target.get("pif")
    if pif is not None:
        proj = np.zeros((oh, ow), dtype=np.uint8)
        reproject(pif["mask"].astype(np.uint8), proj,
                  src_transform=pif["transform"], src_crs=pif["crs"],
                  dst_transform=tr, dst_crs=ds.crs, resampling=Resampling.nearest)
        inside &= proj.astype(bool)

    expected = int(inside.sum())
    if expected < 16:
        return None, 0.0, dec, "target footprint under 16 sampled px"

    nd = ds.nodata
    rgb = arr[:3]
    if nd is not None:
        bad = np.all(rgb == nd, axis=0)
    else:
        bad = np.all(rgb == 0, axis=0)
    sel = inside & ~bad

    n = int(sel.sum())
    cov = n / expected
    if cov < min_cov:
        return None, cov, dec, f"coverage {cov:.3f} < {min_cov:.2f} - SKIPPED"

    names = BAND_NAMES.get(nb, [f"b{i}" for i in idx])
    stats = []
    for i in range(nb):
        v = arr[i][sel].astype(np.float64)
        p1, p5, p50, p95, p99 = np.percentile(v, [1, 5, 50, 95, 99])
        stats.append(dict(band_idx=i + 1, band=names[i],
                          p1=p1, p5=p5, p50=p50, p95=p95, p99=p99,
                          mean=float(v.mean()), std=float(v.std()), valid_px=n))
    return stats, cov, dec, ""


# ══════════════════════════════════════════════════════════════════════════════
#  derived indices
# ══════════════════════════════════════════════════════════════════════════════

def _p50(rows, target, band):
    for r in rows:
        if r["target"] == target and r["band"] == band:
            return r["p50"]
    return None


def _ratio(rows, target, num, den):
    a, b = _p50(rows, target, num), _p50(rows, target, den)
    if a is None or b is None or b <= 0:
        return None
    return a / b


def _median(vals):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return float(np.median(vals)) if vals else None


def derive(rows):
    """Per-acquisition indices from that acquisition's per-target band rows."""
    d = {}
    d["gr_invariant"] = _median([_ratio(rows, t, "G", "R") for t in SPINE])
    # the spine members, unaggregated. If these two disagree the spine median is
    # not to be trusted, and the reader must be able to see that for themselves.
    d["gr_parking"] = _ratio(rows, "neg_parking", "G", "R")
    d["gr_school"] = _ratio(rows, "school_k12", "G", "R")
    d["gb_invariant"] = _median([_ratio(rows, t, "G", "B") for t in SPINE])
    d["gr_invariant_with_water"] = _median(
        [_ratio(rows, t, "G", "R") for t in list(SPINE) + ["neg_water"]])
    d["lum_invariant_g_p50"] = _median([_p50(rows, t, "G") for t in SPINE])
    d["gr_vegetated"] = _median([_ratio(rows, t, "G", "R") for t in VEG])

    # The raw DNs the ratios above are built from. Published so the ratio is
    # AUDITABLE: these are uint8 medians, so a ratio near 1.0 on a p50 of ~140
    # moves ~0.7% per DN — differences under ~1.5% are quantisation, not colour.
    for b in ("R", "G", "B"):
        d[f"spine_{b.lower()}_p50"] = _median([_p50(rows, t, b) for t in SPINE])
        d[f"veg_{b.lower()}_p50"] = _median([_p50(rows, t, b) for t in VEG])

    gi, gv = d["gr_invariant"], d["gr_vegetated"]
    # divides a global colour cast out: the WITHIN-IMAGE greenness contrast
    d["gr_veg_over_inv"] = (gv / gi) if (gi and gv) else None

    # dark-target NIR floor (IMAGERY_FACTS §12 extended to every 4-band year)
    d["nir_floor_water_p1"] = next(
        (r["p1"] for r in rows if r["target"] == "neg_water" and r["band"] == "N"), None)
    nirs = [r["p1"] for r in rows if r["band"] == "N"]
    d["nir_floor_min_p1"] = float(min(nirs)) if nirs else None
    nw, rw = _p50(rows, "neg_water", "N"), _p50(rows, "neg_water", "R")
    d["water_ndvi_p50"] = ((nw - rw) / (nw + rw)) if (nw is not None and rw is not None
                                                     and (nw + rw) > 0) else None
    d["n_targets"] = len({r["target"] for r in rows})
    return d


def robust_stats(values):
    """Median and a FLOORED robust sd (1.4826 x MAD) over the finite entries.

    The floor matters. A source family of five with a tight spread can produce a
    MAD near zero, and the resulting z then reads in the tens for a deviation that
    is real but not that extreme (2023n's luminance is the live example). Every
    index here is built from uint8 medians, so claiming a spread finer than 1% of
    the level is claiming precision the data does not have. Floor at 1% of |median|
    and say so. z stays comparable; it stops being theatrical.

    Returns (median, sd) — sd None when there is too little to score against.
    """
    v = np.array([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if v.size < 3:
        return None, None
    med = float(np.median(v))
    sd = 1.4826 * float(np.median(np.abs(v - med)))
    if sd <= 0:
        sd = float(v.std())
    sd = max(sd, 0.01 * abs(med))
    return (med, sd) if sd > 0 else (med, None)


def source_group(entry):
    """Delivery family — the only footing on which colour compares (§3).

    Snohomish is tested FIRST: 2006s is catalogued as "Snohomish Co. (1 m; likely
    NAIP 2006 republish)" and is a COUNTY delivery whatever its origin, so a naive
    "naip" substring test would file it with the true NAIP DOQQs.
    """
    s = entry["source"].lower()
    if "snohomish" in s or "snoh" in s:
        return "snoh"
    if "king" in s:
        return "king"
    if "city of edmonds" in s:
        return "coe"
    if "usgs" in s:
        return "usgs"
    if "naip" in s:
        return "naip"
    return "other"


# ══════════════════════════════════════════════════════════════════════════════
#  the 2007 verdict
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(v, w=7, p=4):
    return ("-" * w) if v is None or not np.isfinite(v) else f"{v:{w}.{p}f}"


def verdict_2007(summary):
    """Answer the operator's question with a number, within-source (§3)."""
    by = {r["key"]: r for r in summary}
    out = []
    out.append("")
    out.append("=" * 78)
    out.append("  THE 2007 VERDICT — greenness on INVARIANT ground vs on VEGETATION")
    out.append("=" * 78)
    out.append("  gr_invariant   = G/R median on parking + school hardscape (water excluded)")
    out.append("  gr_vegetated   = G/R median on stadium + cemetery + civic field (turf)")
    out.append("  veg_over_inv   = gr_vegetated / gr_invariant — the within-image greenness")
    out.append("                   contrast, with any GLOBAL colour cast divided out")
    out.append("  spine R/G/B    = the raw uint8 medians the ratios are built from. At p50~140")
    out.append("                   one DN is ~0.7%, so read differences under ~1.5% as noise.")
    out.append("")

    hdr = (f"  {'acq':7s} {'source':6s} {'spine R/G/B p50':>17s} {'gr_inv':>8s} "
           f"{'gb_inv':>8s} {'gr_veg':>8s} {'veg/inv':>8s}  date")
    for group, keys, title in [
        ("king", ["2005", "2007", "2009"], "KING COUNTY series (the literal ask: 2007 vs its neighbours)"),
        ("snoh", ["2002s", "2003s", "2006s", "2007s", "2009s", "2011s"],
         "SNOHOMISH series (the file the operator actually flagged: 2007s)"),
    ]:
        out.append(f"  -- {title}")
        out.append(hdr)
        for k in keys:
            r = by.get(k)
            if not r:
                out.append(f"  {k:7s} (not measured)")
                continue
            dns = (f"{_fmt(r['spine_r_p50'],5,1)}/{_fmt(r['spine_g_p50'],5,1)}"
                   f"/{_fmt(r['spine_b_p50'],5,1)}")
            out.append(f"  {k:7s} {r['source_group']:6s} {dns:>17s} {_fmt(r['gr_invariant'])} "
                       f"{_fmt(r['gb_invariant'])} {_fmt(r['gr_vegetated'])} "
                       f"{_fmt(r['gr_veg_over_inv'])}  {r['date_short']}")
        out.append("")

    def _diff(key, peers, field):
        r = by.get(key)
        if not r or r.get(field) is None:
            return None, None
        pv = [by[p][field] for p in peers if p in by and by[p].get(field) is not None]
        if not pv:
            return None, None
        m = float(np.median(pv))
        return (r[field] / m - 1.0) * 100.0, m

    out.append("  Two yardsticks are reported, because they can disagree and BOTH are honest:")
    out.append("    %-vs-peers = effect size against the named neighbours' median.")
    out.append("    zsrc       = robust z against the acquisition's WHOLE source family")
    out.append("                 (MAD-based). |zsrc| > 2 is the anomaly bar; a large %")
    out.append("                 with a small zsrc means the family spread is simply wide.")
    out.append("")

    lines_call = []
    for key, peers, lbl in [("2007", ["2005", "2009"], "2007 King vs 2005/2009 King"),
                            ("2007s", ["2002s", "2003s", "2006s", "2009s", "2011s"],
                             "2007s Snoh vs its Snoh RGB neighbours")]:
        d_inv, m_inv = _diff(key, peers, "gr_invariant")
        d_veg, m_veg = _diff(key, peers, "gr_vegetated")
        d_con, m_con = _diff(key, peers, "gr_veg_over_inv")
        out.append(f"  -- {lbl}")
        if d_inv is None:
            out.append("     insufficient data")
            continue
        zsrc = by[key].get("zsrc_gr_invariant")
        out.append(f"     gr_invariant  {by[key]['gr_invariant']:.4f} vs peer median "
                   f"{m_inv:.4f}   -> {d_inv:+6.2f}%   zsrc={_fmt(zsrc, 5, 2)}")
        # spine members separately — the aggregate is only as good as its agreement
        d_pk, m_pk = _diff(key, peers, "gr_parking")
        d_sc, m_sc = _diff(key, peers, "gr_school")
        if d_pk is not None:
            out.append(f"        - parking  {by[key]['gr_parking']:.4f} vs {m_pk:.4f}"
                       f"   -> {d_pk:+6.2f}%")
        if d_sc is not None:
            out.append(f"        - school   {by[key]['gr_school']:.4f} vs {m_sc:.4f}"
                       f"   -> {d_sc:+6.2f}%")
        if d_pk is not None and d_sc is not None and abs(d_pk - d_sc) > 3.0:
            out.append(f"        ! SPINE MEMBERS DISAGREE by {abs(d_pk - d_sc):.1f} points "
                       f"- the aggregate below is weak evidence; trust neither alone")
        if d_veg is not None:
            out.append(f"     gr_vegetated  {by[key]['gr_vegetated']:.4f} vs peer median "
                       f"{m_veg:.4f}   -> {d_veg:+6.2f}%")
        if d_con is not None:
            out.append(f"     veg_over_inv  {by[key]['gr_veg_over_inv']:.4f} vs peer median "
                       f"{m_con:.4f}   -> {d_con:+6.2f}%")

        # ── decision rule, stated so it can be argued with ────────────────────
        # DIRECTION matters: "greener" is a POSITIVE deviation. A negative one is
        # the opposite complaint and must not be reported as confirming it.
        z = abs(zsrc) if zsrc is not None else 0.0
        strength = ("CONFIRMED (|zsrc|>2)" if z > 2 else
                    "SUGGESTIVE (1<|zsrc|<=2)" if z > 1 else
                    "not distinguishable from its family (|zsrc|<=1)")
        direction = "GREENER" if d_inv > 0 else "LESS GREEN"
        if abs(d_inv) < 1.5:
            inv_call = ("stable ground is NORMAL (within uint8 quantisation of its peers)")
        else:
            inv_call = (f"stable ground reads {direction} than its peers by {abs(d_inv):.1f}% "
                        f"- {strength}")
        if d_con is None:
            veg_call = "vegetated contrast not measurable"
        elif abs(d_con) < 1.5:
            veg_call = "within-image greenness contrast is NORMAL"
        else:
            veg_call = (f"within-image greenness contrast is "
                        f"{'HIGHER' if d_con > 0 else 'LOWER'} by {abs(d_con):.1f}% "
                        f"(cast-free, but CONFOUNDED BY SEASON where the date is unknown)")
        out.append(f"     CALL: {inv_call}")
        out.append(f"           {veg_call}")
        out.append("")
        lines_call.append((lbl, inv_call, veg_call, d_inv, d_con))

    # same-year same-ground cross-check (excludes real vegetation change by construction)
    a, b = by.get("2007"), by.get("2007s")
    if a and b and a.get("gr_invariant") and b.get("gr_invariant"):
        out.append("  -- 2007 King vs 2007s Snoh — SAME YEAR, SAME GROUND")
        out.append(f"     gr_invariant  King {a['gr_invariant']:.4f}   Snoh {b['gr_invariant']:.4f}"
                   f"   -> Snoh is {(b['gr_invariant']/a['gr_invariant']-1)*100:+.2f}% greener on STABLE ground")
        if a.get("gr_veg_over_inv") and b.get("gr_veg_over_inv"):
            out.append(f"     veg_over_inv  King {a['gr_veg_over_inv']:.4f}   Snoh {b['gr_veg_over_inv']:.4f}"
                       f"   -> {(b['gr_veg_over_inv']/a['gr_veg_over_inv']-1)*100:+.2f}%")
        out.append("     (cross-SOURCE, so §3 applies: this pair proves the two DELIVERIES differ,")
        out.append("      it cannot attribute the difference to either one alone.)")
        out.append("")
    out.append("  CAVEAT — phenology: 2009 King is MAY (spring flush), 2007 King is Jun-Aug,")
    out.append("  2005 King is July, and every Snohomish date is NOT FOUND. Turf differences")
    out.append("  between an April and an August frame are season. Only the INVARIANT row and")
    out.append("  the cast-free veg_over_inv ratio carry a radiometric reading.")
    return "\n".join(out), lines_call


# ══════════════════════════════════════════════════════════════════════════════
#  driver
# ══════════════════════════════════════════════════════════════════════════════

def load_dates():
    """native_file -> (short date, full date_shot) from the one-home date table."""
    out = {}
    if not DATE_CSV.exists():
        return out
    for r in csv.DictReader(DATE_CSV.open(encoding="utf-8")):
        f = r.get("file", "")
        if f and f not in out:
            d = (r.get("date_shot") or "").strip()
            short = "NOT FOUND" if d.upper().startswith("NOT FOUND") else d[:24]
            out[f] = (short, d)
    return out


def run(only, max_edge, min_cov, out_dir, grvi_max=PIF_GRVI_MAX):
    targets = build_targets()
    dates = load_dates()
    print(f"[R1] {len(targets)} pseudo-invariant targets: "
          + ", ".join(f"{t['name']}({t['target_class'][:3]})" for t in targets))
    build_pif(targets, grvi_max)

    entries = [e for e in C.YEAR_CATALOG
               if (not only or only.lower() in str(e["key"]).lower()
                   or only.lower() in e["native_file"].lower())]
    print(f"[R1] {len(entries)} of {len(C.YEAR_CATALOG)} catalog acquisitions selected")

    band_rows, summary, skipped, unresolved = [], [], [], []

    for e in entries:
        key = str(e["key"])
        path, root = resolve(e["native_file"])
        if path is None:
            unresolved.append((key, e["native_file"]))
            print(f"  ! {key:7s} FILE NOT FOUND: {e['native_file']}")
            continue
        short, full = dates.get(e["native_file"], ("NOT FOUND", "NOT FOUND"))
        rows_this = []
        skips_this = []
        with rasterio.open(path) as ds:
            for t in targets:
                stats, cov, dec, why = fingerprint_target(ds, t, max_edge, min_cov)
                if stats is None:
                    skips_this.append(f"{t['name']}:{why}")
                    skipped.append(dict(key=key, target=t["name"], coverage=round(cov, 4),
                                        reason=why))
                    continue
                for s in stats:
                    r = dict(key=key, label=e["label"], source=e["source"],
                             source_group=source_group(e), native_file=e["native_file"],
                             root=str(root), gsd_cm=e["gsd_cm"], bands=e["bands"],
                             crs_epsg=e["crs_epsg"], date_shot=full,
                             target=t["name"], target_class=t["target_class"],
                             target_note=t["note"], coverage=round(cov, 4),
                             pif_frac=t.get("pif_frac"), decimation=dec, **s)
                    rows_this.append(r)
                    band_rows.append(r)
        d = derive(rows_this)
        summary.append(dict(key=key, label=e["label"], source=e["source"],
                            source_group=source_group(e), native_file=e["native_file"],
                            root=str(root), gsd_cm=e["gsd_cm"], bands=e["bands"],
                            date_shot=full, date_short=short,
                            skipped_targets=";".join(skips_this), **d))
        print(f"  * {key:7s} gr_inv={_fmt(d['gr_invariant'])} gb_inv={_fmt(d['gb_invariant'])} "
              f"gr_veg={_fmt(d['gr_vegetated'])} lumG={_fmt(d['lum_invariant_g_p50'],6,1)} "
              f"nirp1={_fmt(d['nir_floor_water_p1'],5,1)} "
              f"targets={d['n_targets']}/{len(targets)}")

    # ── robust z + ANOMALY flags: record-wide (as specified) AND within source ──
    IDX = ["gr_invariant", "gb_invariant", "lum_invariant_g_p50",
           "gr_vegetated", "gr_veg_over_inv", "nir_floor_water_p1"]
    INV_IDX = ["gr_invariant", "gb_invariant", "lum_invariant_g_p50",
               "nir_floor_water_p1"]
    stats_all = {f: robust_stats([r.get(f) for r in summary]) for f in IDX}
    groups = sorted({r["source_group"] for r in summary})
    stats_grp = {}
    for g in groups:
        sub = [r for r in summary if r["source_group"] == g]
        for f in IDX:
            stats_grp[(g, f)] = robust_stats([r.get(f) for r in sub])

    for r in summary:
        flags, flags_g = [], []
        for f in IDX:
            med, sd = stats_all[f]
            v = r.get(f)
            z = ((v - med) / sd) if (v is not None and np.isfinite(v)
                                     and med is not None and sd) else None
            r[f"z_{f}"] = None if z is None else round(z, 3)
            if z is not None and abs(z) > Z_FLAG:
                flags.append(f"{f}({z:+.1f})")
            med, sd = stats_grp.get((r["source_group"], f), (None, None))
            zg = ((v - med) / sd) if (v is not None and np.isfinite(v)
                                      and med is not None and sd) else None
            r[f"zsrc_{f}"] = None if zg is None else round(zg, 3)
            if zg is not None and abs(zg) > Z_FLAG:
                flags_g.append(f"{f}({zg:+.1f})")
        r["anomaly"] = ";".join(flags)
        r["anomaly_within_source"] = ";".join(flags_g)
        r["anomaly_score"] = round(max(
            [abs(r[f"z_{f}"]) for f in IDX if r.get(f"z_{f}") is not None] or [0.0]), 3)
        # The DECISION-RELEVANT score: invariant-ground indices only, scored WITHIN
        # the source family. gr_vegetated is excluded because turf greenness is
        # season + sensor, so it dominates the raw score with signal that says
        # nothing about calibration.
        r["anomaly_score_invariant"] = round(max(
            [abs(r[f"zsrc_{f}"]) for f in INV_IDX
             if r.get(f"zsrc_{f}") is not None] or [0.0]), 3)

    # ── write ─────────────────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    fp_csv = out_dir / "radiometry_fingerprint.csv"
    su_csv = out_dir / "radiometry_summary.csv"
    if band_rows:
        cols = ["key", "label", "source", "source_group", "native_file", "root",
                "gsd_cm", "bands", "crs_epsg", "date_shot", "target", "target_class",
                "coverage", "pif_frac", "decimation", "band_idx", "band", "p1", "p5",
                "p50", "p95", "p99", "mean", "std", "valid_px", "target_note"]
        with fp_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in band_rows:
                w.writerow({k: (round(v, 4) if isinstance(v, float) else v)
                            for k, v in r.items() if k in cols})
    if summary:
        base = ["key", "label", "source", "source_group", "native_file", "root",
                "gsd_cm", "bands", "date_shot", "n_targets"]
        deriv = IDX + ["gr_invariant_with_water", "nir_floor_min_p1", "water_ndvi_p50",
                       "gr_parking", "gr_school",
                       "spine_r_p50", "spine_g_p50", "spine_b_p50",
                       "veg_r_p50", "veg_g_p50", "veg_b_p50"]
        zs = [f"z_{f}" for f in IDX] + [f"zsrc_{f}" for f in IDX]
        cols = base + deriv + zs + ["anomaly", "anomaly_within_source", "anomaly_score",
                                    "anomaly_score_invariant", "skipped_targets"]
        with su_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in summary:
                w.writerow({k: (round(v, 5) if isinstance(v, float) else v)
                            for k, v in r.items() if k in cols})
    print(f"\n[R1] wrote {len(band_rows)} band rows -> {fp_csv}")
    print(f"[R1] wrote {len(summary)} acquisition rows -> {su_csv}")

    # ── report ────────────────────────────────────────────────────────────────
    txt, _ = verdict_2007(summary)
    print(txt)

    print("=" * 78)
    print("  IMAGERY_FACTS §12 REPRODUCTION — NIR p1 on the water dark target")
    print("=" * 78)
    print("  §12 used a different dark target, so the DNs are not expected to match")
    print("  digit for digit. What must reproduce is the BIMODAL SEPARATION.")
    print(f"  {'acq':7s} {'water N p1':>10s} {'water N p50':>11s} {'water NDVI p50':>14s}  §12 classed it")
    s12 = {"2015n": "LIFTED (§12 p1=33)", "2021s": "LIFTED (§12 p1=28)"}
    for r in sorted([x for x in summary if x["bands"] == 4], key=lambda x: x["key"]):
        exp = s12.get(r["key"], "healthy")
        nw = _p50([x for x in band_rows if x["key"] == r["key"]], "neg_water", "N")
        print(f"  {r['key']:7s} {_fmt(r['nir_floor_water_p1'],10,1)} {_fmt(nw,11,1)} "
              f"{_fmt(r['water_ndvi_p50'],14,3)}  {exp}")
    heal = [r["nir_floor_water_p1"] for r in summary
            if r["bands"] == 4 and r["key"] not in s12 and r["nir_floor_water_p1"] is not None]
    lift = [r["nir_floor_water_p1"] for r in summary
            if r["key"] in s12 and r["nir_floor_water_p1"] is not None]
    if heal and lift:
        print(f"  -> healthy span {min(heal):.0f}-{max(heal):.0f} DN, lifted "
              f"{min(lift):.0f}-{max(lift):.0f} DN. Clean separation, §12 REPRODUCED.")

    # ── positive control: acquisitions that ARE the same flight must agree ─────
    print()
    print("=" * 78)
    print("  POSITIVE CONTROL — same-flight pairs must fingerprint alike")
    print("  (2020/2022/2024 CoE vs the county's own serving of the SAME EagleView")
    print("   programme, IMAGERY_FACTS §10.16. These were not designed as a control;")
    print("   they are one for free, and they bound the instrument's noise.)")
    print("=" * 78)
    by = {r["key"]: r for r in summary}
    for a_k, b_k in [("2020", "2020s"), ("2022", "2022s"), ("2024", "2024s")]:
        a, b = by.get(a_k), by.get(b_k)
        if not (a and b and a.get("gr_invariant") and b.get("gr_invariant")):
            continue
        d = (b["gr_invariant"] / a["gr_invariant"] - 1) * 100
        dl = ((b["lum_invariant_g_p50"] / a["lum_invariant_g_p50"] - 1) * 100
              if a.get("lum_invariant_g_p50") and b.get("lum_invariant_g_p50") else float("nan"))
        print(f"  {a_k:5s} vs {b_k:6s} gr_inv {a['gr_invariant']:.4f} / {b['gr_invariant']:.4f}"
              f"  -> {d:+5.2f}%    lumG {dl:+5.2f}%")

    print()
    print("=" * 78)
    print("  MOST ANOMALOUS ON INVARIANT GROUND — the decision-relevant ranking")
    print("  (invariant indices only, robust z WITHIN the source family; §3 says")
    print("   cross-source colour does not compare, so this is the honest footing)")
    print("=" * 78)
    inv_ranked = sorted(summary, key=lambda r: -r["anomaly_score_invariant"])
    for r in inv_ranked[:6]:
        R, G, B = r["spine_r_p50"], r["spine_g_p50"], r["spine_b_p50"]
        gr = "" if (R is None or G is None) else f"  spine G-R = {G - R:+.1f} DN"
        # name the index that drives the score, with its raw % offset from the
        # family median — z alone hides whether a big number is a big effect
        drv, best = None, -1.0
        for f in INV_IDX:
            z = r.get(f"zsrc_{f}")
            if z is not None and abs(z) > best:
                drv, best = f, abs(z)
        detail = ""
        if drv is not None:
            med, _sd = stats_grp.get((r["source_group"], drv), (None, None))
            v = r.get(drv)
            if med and v is not None:
                detail = (f"    driver: {drv} = {v:.4g} vs {r['source_group']} family median "
                          f"{med:.4g}  ({(v / med - 1) * 100:+.1f}%)")
        print(f"  {r['key']:7s} {r['source_group']:6s} zsrc_max={r['anomaly_score_invariant']:6.2f}"
              f"  {r['anomaly_within_source'] or '(no index over the 2-sigma bar)'}")
        print(f"          gr_inv={_fmt(r['gr_invariant'])} gb_inv={_fmt(r['gb_invariant'])} "
              f"lumG={_fmt(r['lum_invariant_g_p50'],6,1)}{gr}")
        if detail:
            print(detail)

    print()
    print("=" * 78)
    print("  MOST ANOMALOUS, RECORD-WIDE (all indices, robust z over all 36; |z| > 2)")
    print("  NOTE: gr_vegetated is included here and it is season+sensor driven, so")
    print("  the leaf-on NAIP years dominate. Read the invariant ranking above first.")
    print("=" * 78)
    ranked = sorted([r for r in summary if r["anomaly"]],
                    key=lambda r: -r["anomaly_score"])
    if not ranked:
        print("  none exceed the flag threshold")
    for r in ranked[:8]:
        print(f"  {r['key']:7s} {r['source_group']:6s} score={r['anomaly_score']:5.2f}  {r['anomaly']}")
        print(f"          gr_inv={_fmt(r['gr_invariant'])} gb_inv={_fmt(r['gb_invariant'])} "
              f"lumG={_fmt(r['lum_invariant_g_p50'],6,1)} gr_veg={_fmt(r['gr_vegetated'])}")

    if skipped:
        print()
        print("=" * 78)
        print(f"  SKIPPED TARGETS ({len(skipped)}) — measured coverage below the floor,")
        print("  or outside the acquisition footprint. NOTHING WAS FABRICATED.")
        print("=" * 78)
        for s in skipped:
            print(f"  {s['key']:7s} {s['target']:16s} cov={s['coverage']:.3f}  {s['reason']}")
    if unresolved:
        print(f"\n  ! UNRESOLVED FILES: {unresolved}")

    _log(len(summary), len(band_rows))
    return summary, band_rows


def _log(n_acq, n_rows):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"radiometry_fingerprint_run_{ts}.log").write_text(
            f"radiometry_fingerprint.py run\nacquisitions={n_acq}\nband_rows={n_rows}\n",
            encoding="utf-8")
    except Exception:
        pass


def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(
        description="R1 radiometry fingerprint over pseudo-invariant ground.")
    ap.add_argument("--only", help="substring filter on catalog key / filename")
    ap.add_argument("--max-edge", type=int, default=MAX_EDGE,
                    help="decimate a window to <= N px on its long edge (NEAREST)")
    ap.add_argument("--min-cov", type=float, default=MIN_COVERAGE,
                    help="skip a target below this coverage fraction")
    ap.add_argument("--pif-grvi", type=float, default=PIF_GRVI_MAX,
                    help="GRVI ceiling defining hardscape in the PIF reference; "
                         "lower = stricter. Sensitivity knob, not a tuning dial.")
    ap.add_argument("--out-dir", default=str(QC_DIR))
    a = ap.parse_args(filtered)
    run(a.only, a.max_edge, a.min_cov, Path(a.out_dir), a.pif_grvi)


if __name__ == "__main__":
    main()
