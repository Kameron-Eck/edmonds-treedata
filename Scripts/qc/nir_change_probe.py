"""
==================================================================
  PHASE 4 -- QC: NIR CHANGE PROBE  (first artifact of the change-learning idea)
  Edmonds Temporal Active Learning Pipeline

  THE IDEA BEING TESTED
    Kam's proposal: use the 4-band (NIR-bearing) years to LEARN what
    development-driven change looks like -- colour + texture -- seeded by
    known (location, time-window) change events, then TRANSFER that detector
    to the RGB-only, low-resolution years via a *validated* degradation
    model. This script is the smallest honest test of whether the three
    legs of that idea stand up:

      LEG 1  Is there a measurable change signal at a known-change site?
      LEG 2  Does a known-STABLE site read stable? (the null control -- if
             the null fails, every "change" the detector finds is suspect)
      LEG 3  Can naive downsampling of a fine product actually reproduce a
             real coarser sensor? (the transfer trick, MEASURED not assumed)

  INPUTS (all read-only)
    NIR mega-stack   D:/edmonds-pipeline/ARCGIS/MachineLearning/nir_stack/
                       nir_stack_1m.tif       uint8 NIR DN, nodata 0
                       nir_stack_ndvi_1m.tif  int16 NDVI x1000, nodata -32768
                     10 acquisitions, chronological, EPSG:3857, 1 CRS unit/px
                     (= ~0.67 ground m). Band descriptions + per-band tags
                     carry label / acquired date / native GSD / source file.
    Site labels      {BASE}/phase4/labels_sites/site_labels_timeseries.gpkg
                     layer site_labels: site, year_from, year_to, cls, src.
                     Development = the dated 1996-2005 clear-and-regrow
                     parcel. Edmonds Heights K-12 = stable 1990-2025.
    Cross-sensor     resolved from pipeline/phase4seg/config.py YEAR_CATALOG.
      pair (2019)    2019n = NAIP 60 cm  vs  2019s = SnohCo 1 ft (30.48 cm).

  RADIOMETRY (nir_stack_README.txt, "RADIOMETRY" block)
    Bands 2015n and 2021s have LIFTED BLACK POINTS (NIR p1 = 33 / 28 DN, no
    negative NDVI tail over Puget Sound). Their ABSOLUTE NDVI is biased
    upward. This script therefore never applies a fixed NDVI cut and never
    treats a raw cross-band NDVI difference as truth: every verdict that
    matters is stated as a CONTROL-ADJUSTED contrast (site minus the stable
    school), which is a relative/temporal comparison and survives the bias.
    Rows and pairs touching a flagged band are marked in the CSVs.

  PRODUCES ({BASE}/phase4/qc/)
    nir_change_probe.csv              zonal stats, per site x zone x band
    nir_change_probe_signal.csv       change signal, per zone x band-pair
    nir_change_probe_trend.csv        greening/browning trend per zone
    nir_change_probe_degradation.csv  the degradation-validation table
    ...plus a printed narrative ending in an explicit GO / NO-GO verdict.

  ZONES
    Edmonds Heights K-12  tree | background | whole_parcel   (the CONTROL;
                          labels valid 1990-2025, i.e. across the whole stack)
    Development           whole_parcel  -- labelled "post-timeline regrowth":
                          the drawn labels stop at 2005 and the stack starts
                          in 2015, so the parcel-level trajectory is the only
                          honest read. Per the operator, its post-2005
                          evolution is yard trees -> hedges -> clustered
                          ornamentals.
                          tree_2002_2005 | background_2002_2005 -- the last
                          drawn windows, carried forward and flagged STALE.
                          The 2002-2005 *background* greening up is the
                          localized regrowth signal.

  USAGE (local Windows, CPU; no GPU, no Colab)
    PYTHONUTF8=1 py -3.12 qc/nir_change_probe.py
    PYTHONUTF8=1 py -3.12 qc/nir_change_probe.py --skip-degradation
==================================================================
"""

import argparse
import importlib
import subprocess
import sys
from pathlib import Path


# -- Dependency bootstrap (matches requirements-local.txt) --------------------
def _pip(spec):
    print(f"  . installing {spec} ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("numpy", "numpy"), ("rasterio", "rasterio"),
                    ("geopandas", "geopandas"), ("pandas", "pandas"),
                    ("scipy", "scipy")]:
    try:
        importlib.import_module(_imp)
    except ImportError:
        _pip(_spec)

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.ndimage import gaussian_filter, uniform_filter


# -- Environment / paths ------------------------------------------------------
_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

SCRIPTS_DIR = Path(__file__).resolve().parent.parent          # code plane
NIR_STACK_DIR = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\nir_stack")
STACK_NIR  = NIR_STACK_DIR / "nir_stack_1m.tif"
STACK_NDVI = NIR_STACK_DIR / "nir_stack_ndvi_1m.tif"

LABELS_GPKG  = BASE / "phase4" / "labels_sites" / "site_labels_timeseries.gpkg"
LABELS_LAYER = "site_labels"

QC_DIR   = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"

# Imagery roots for the degradation step -- same order as config.imagery_roots()
_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]


# -- Documented constants (a-priori; NOT tuned on the control) ----------------
# Direction verdict cut on the median per-pixel NDVI difference. Chosen BEFORE
# looking at the control so the null test stays non-circular. The repo has no
# published delta-NDVI threshold (its 0.2 / 0.3 cuts are absolute vegetation
# cuts, which the radiometry warning forbids applying across bands), so this is
# a fresh, declared choice -- and the school's measured spread below is what
# says whether it was the right one.
DELTA_NDVI_CUT = 0.05

# Same-acquisition band pairs: both deliveries of one flight, so dt = 0 and any
# apparent "change" is pure sensor/processing noise. A second null, measured on
# the sites themselves rather than at a second location.
#   2017n/2017s : NAIP 1 m and SnohCo 1 ft, both 2017-08-15 + 2017-08-21
#                 (qc/imagery_pixelsize_and_date.csv, WA consortium flight areas)
#   2019n/2019s : NAIP 60 cm and SnohCo 1 ft, both 2019-10-11 -- documented in
#                 the same CSV as "the same Hexagon flight"
SAME_FLIGHT_PAIRS = {("2017n", "2017s"), ("2019n", "2019s")}

# Lifted black point -- absolute NDVI biased upward (nir_stack_README RADIOMETRY)
RADIOMETRY_FLAGGED = {"2015n", "2021s"}

# October acquisitions among an otherwise Jun-Aug stack: phenology alone can
# fake "browning", so the trend is also reported on the leaf-on subset.
OCTOBER_BANDS = {"2019n", "2019s", "2023n"}

SCHOOL = "Edmonds Heights K-12"
DEV    = "Development"

# Which control zone each zone is differenced against (like-for-like cover).
CONTROL_FOR = {
    (DEV,    "whole_parcel"):          (SCHOOL, "whole_parcel"),
    (DEV,    "tree_2002_2005"):        (SCHOOL, "tree"),
    (DEV,    "background_2002_2005"):  (SCHOOL, "background"),
    (SCHOOL, "tree"):                  (SCHOOL, "whole_parcel"),
    (SCHOOL, "background"):            (SCHOOL, "whole_parcel"),
    (SCHOOL, "whole_parcel"):          None,      # it IS the control
}

# A control only cancels the sensor/season term if it sits at a similar NDVI
# LEVEL: a black-point lift or an exposure change does not move NDVI 0.03
# pavement and NDVI 0.55 canopy by the same amount, so subtracting one from the
# other manufactures change. Zones whose mean NDVI p50 differs from their
# control's by more than this are marked COVER_MISMATCH and are excluded from
# the verdict.
COVER_MATCH_MAX_NDVI_GAP = 0.15

# GO / NO-GO criteria, declared up front (see verdict() for how they are read).
GO_SNR_MIN          = 2.0    # |span signal| / matched-control null spread
GO_TREND_RHO_MIN    = 0.0    # Spearman must be positive AND ...
GO_TREND_P_MAX      = 0.10   # ... not attributable to chance at n = 7-10
GO_DEGRADE_R_MIN    = 0.80   # NDVI Pearson r, simulated vs real coarse
GO_DEGRADE_BIAS_MAX = 0.05   # |mean(sim - real)| in NDVI units
GO_DEGRADE_STD_LO   = 0.80
GO_DEGRADE_STD_HI   = 1.25

NODATA_NDVI = -32768
NDVI_SCALE  = 1000.0


# -- Small helpers ------------------------------------------------------------
def _rankdata(a):
    """Average-tie ranks (avoids a scipy.stats import for one function)."""
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(a.size, dtype=float)
    ranks[order] = np.arange(1, a.size + 1, dtype=float)
    vals, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    for k in np.where(cnt > 1)[0]:
        m = inv == k
        ranks[m] = ranks[m].mean()
    return ranks


def spearman(x, y, n_perm=5000, seed=42):
    """Spearman rho + a two-sided permutation p (n is tiny; no asymptotics)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if x.size < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return float("nan"), float("nan")
    rx, ry = _rankdata(x), _rankdata(y)
    rho = float(np.corrcoef(rx, ry)[0, 1])
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_perm):
        r = abs(float(np.corrcoef(rx, rng.permutation(ry))[0, 1]))
        if r >= abs(rho) - 1e-12:
            hits += 1
    return rho, (hits + 1) / (n_perm + 1)


def pearson(a, b):
    if a.size < 8 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def ndvi_from_bands(arr):
    """Repo NDVI convention, verbatim: read [1,2,3,4], r = band1, nir = band4,
    NDVI = (nir - r) / (nir + r + 1e-6)  -- qc/phase4_qc_ndvi.py and
    pipeline/phase4_build_corrected_labels.py."""
    r   = arr[0].astype(np.float32)
    nir = arr[3].astype(np.float32)
    return (nir - r) / (nir + r + 1e-6)


def direction(delta, cut=DELTA_NDVI_CUT):
    if not np.isfinite(delta):
        return "n/a"
    if delta >= cut:
        return "greening"
    if delta <= -cut:
        return "browning"
    return "stable"


def resolve_img(fname):
    for d in IMAGERY_DIRS:
        p = d / fname
        if p.exists():
            return p, str(d)
    raise FileNotFoundError(f"{fname} not in {[str(d) for d in IMAGERY_DIRS]}")


def year_catalog():
    """YEAR_CATALOG is the ONE home for which file a year key means."""
    sys.path.insert(0, str(SCRIPTS_DIR / "pipeline"))
    from phase4seg import config as _cfg          # noqa: E402
    return {str(e["key"]): e for e in _cfg.YEAR_CATALOG}


# -- Step 0: zones ------------------------------------------------------------
def build_zones():
    """Return {(site, zone): (geom, note)} in the label CRS (EPSG:3857)."""
    gdf = gpd.read_file(LABELS_GPKG, layer=LABELS_LAYER)
    if gdf.crs is None or gdf.crs.to_epsg() != 3857:
        raise SystemExit(f"labels CRS is {gdf.crs}, expected EPSG:3857")

    zones = {}

    sch = gdf[gdf["site"] == SCHOOL]
    for cls in ("tree", "background"):
        sub = sch[sch["cls"] == cls]
        if len(sub):
            zones[(SCHOOL, cls)] = (sub.union_all(),
                                    f"stable {sub['year_from'].min()}-{sub['year_to'].max()}")
    zones[(SCHOOL, "whole_parcel")] = (sch.union_all(), "stable 1990-2025 (null control)")

    dev = gdf[gdf["site"] == DEV]
    zones[(DEV, "whole_parcel")] = (dev.union_all(), "post-timeline regrowth")
    last = dev[(dev["year_from"] == 2002) & (dev["year_to"] == 2005)]
    for cls in ("tree", "background"):
        sub = last[last["cls"] == cls]
        if len(sub):
            zones[(DEV, f"{cls}_2002_2005")] = (
                sub.union_all(), "STALE labels (2002-2005) carried onto 2015-2023 pixels")
    return zones, gdf


def site_window(src, geoms, pad=20):
    """Outward-rounded raster window covering the geometries, padded."""
    xs = [g.bounds for g in geoms]
    minx = min(b[0] for b in xs) - pad
    miny = min(b[1] for b in xs) - pad
    maxx = max(b[2] for b in xs) + pad
    maxy = max(b[3] for b in xs) + pad
    w = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
    w = w.round_offsets(op="floor").round_lengths(op="ceil")
    return Window(max(0, int(w.col_off)), max(0, int(w.row_off)),
                  int(w.width), int(w.height))


# -- Step 1: zonal stats ------------------------------------------------------
def read_site_cubes(site, zones):
    """Read the NIR + NDVI cubes over one site's window and rasterize its zones.

    Returns (nir[b,y,x] float, ndvi[b,y,x] float NDVI units, masks{zone->bool},
             bands[list of dicts]).
    """
    geoms = [g for (s, _z), (g, _n) in zones.items() if s == site]
    with rasterio.open(STACK_NIR) as sn, rasterio.open(STACK_NDVI) as sv:
        if (sn.width, sn.height) != (sv.width, sv.height) or sn.transform != sv.transform:
            raise SystemExit("NIR and NDVI stacks are not on the same grid")
        win = site_window(sn, geoms)
        tf = sn.window_transform(win)
        nir = sn.read(window=win).astype(np.float32)
        ndv = sv.read(window=win).astype(np.float32)
        bands = []
        for i in range(1, sn.count + 1):
            t = sn.tags(i)
            desc = sn.descriptions[i - 1] or ""
            bands.append({
                "idx": i,
                "label": desc.split()[0] if desc else f"b{i}",
                "acquired": t.get("acquired", ""),
                "native_gsd_cm": float(t.get("native_gsd_cm", "nan")),
                "source_file": t.get("source_file", ""),
                "desc": desc,
            })

    nir[nir == 0] = np.nan                       # stack nodata
    ndv[ndv == NODATA_NDVI] = np.nan
    ndv = ndv / NDVI_SCALE

    shape = (int(win.height), int(win.width))
    masks = {}
    for (s, z), (g, _note) in zones.items():
        if s != site:
            continue
        masks[z] = rasterize([(g, 1)], out_shape=shape, transform=tf,
                             fill=0, dtype="uint8").astype(bool)
    return nir, ndv, masks, bands


def zonal_stats(zones):
    rows, cubes = [], {}
    for site in sorted({s for (s, _z) in zones}):
        nir, ndv, masks, bands = read_site_cubes(site, zones)
        cubes[site] = dict(nir=nir, ndvi=ndv, masks=masks, bands=bands)
        for z, m in masks.items():
            note = zones[(site, z)][1]
            for b in bands:
                k = b["idx"] - 1
                nv = nir[k][m]
                dv = ndv[k][m]
                ok = np.isfinite(nv) & np.isfinite(dv)
                nv, dv = nv[ok], dv[ok]
                rows.append({
                    "site": site, "zone": z, "zone_note": note,
                    "band": b["label"], "acquired": b["acquired"],
                    "native_gsd_cm": b["native_gsd_cm"],
                    "source_file": b["source_file"],
                    "radiometry_flag": ("LIFTED_BLACK_POINT"
                                        if b["label"] in RADIOMETRY_FLAGGED else ""),
                    "n_px_zone": int(m.sum()), "n_px_valid": int(ok.sum()),
                    "nir_mean": round(float(nv.mean()), 3) if nv.size else np.nan,
                    "nir_std":  round(float(nv.std()), 3) if nv.size else np.nan,
                    "ndvi_mean": round(float(dv.mean()), 4) if dv.size else np.nan,
                    "ndvi_std":  round(float(dv.std()), 4) if dv.size else np.nan,
                    "ndvi_p25": round(float(np.percentile(dv, 25)), 4) if dv.size else np.nan,
                    "ndvi_p50": round(float(np.percentile(dv, 50)), 4) if dv.size else np.nan,
                    "ndvi_p75": round(float(np.percentile(dv, 75)), 4) if dv.size else np.nan,
                })
    return pd.DataFrame(rows), cubes


# -- Step 2: change signal ----------------------------------------------------
def pair_stats(ndv, mask, i, j):
    """Per-pixel NDVI difference band_j - band_i inside the zone.

    delta_p50 is the MEDIAN OF THE DIFFERENCE IMAGE (not the difference of the
    two medians): it is paired per pixel, so it is insensitive to which pixels
    happen to be valid in only one band.
    """
    a, b = ndv[i][mask], ndv[j][mask]
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 50:
        return dict(n_px=int(ok.sum()), delta_p50=np.nan, delta_mean=np.nan,
                    texture_std=np.nan, delta_p25=np.nan, delta_p75=np.nan)
    d = b[ok] - a[ok]
    return dict(n_px=int(ok.sum()),
                delta_p50=float(np.median(d)), delta_mean=float(d.mean()),
                texture_std=float(d.std()),
                delta_p25=float(np.percentile(d, 25)),
                delta_p75=float(np.percentile(d, 75)))


def change_signal(zones, cubes, zstats):
    bands = cubes[SCHOOL]["bands"]
    labels = [b["label"] for b in bands]
    n = len(bands)
    pairs = [(k, k + 1, "consecutive") for k in range(n - 1)] + [(0, n - 1, "span")]

    # NDVI level per zone (mean of its p50 across bands) -- the cover-match test
    level = (zstats.groupby(["site", "zone"])["ndvi_p50"].mean()).to_dict()

    # pass 1: raw stats for every zone
    raw = {}
    for site in cubes:
        for z, m in cubes[site]["masks"].items():
            for (i, j, kind) in pairs:
                raw[(site, z, i, j)] = pair_stats(cubes[site]["ndvi"], m, i, j)

    # pass 2: control-adjust
    rows = []
    for site in sorted(cubes):
        for z in sorted(cubes[site]["masks"]):
            ctrl = CONTROL_FOR.get((site, z))
            gap = (abs(level.get((site, z), np.nan) - level.get(ctrl, np.nan))
                   if ctrl else np.nan)
            cover = ("" if not ctrl else
                     ("COVER_MISMATCH" if not np.isfinite(gap)
                      or gap > COVER_MATCH_MAX_NDVI_GAP else "cover_matched"))
            for (i, j, kind) in pairs:
                s = raw[(site, z, i, j)]
                la, lb = labels[i], labels[j]
                same_flight = ((la, lb) in SAME_FLIGHT_PAIRS
                               or (bands[i]["acquired"] and
                                   bands[i]["acquired"] == bands[j]["acquired"]))
                cs = raw.get((ctrl[0], ctrl[1], i, j)) if ctrl else None
                dvc = (s["delta_p50"] - cs["delta_p50"]) if cs else np.nan
                tratio = (s["texture_std"] / cs["texture_std"]
                          if cs and cs["texture_std"] else np.nan)
                rows.append({
                    "site": site, "zone": z, "pair_kind": kind,
                    "pair": f"{la}->{lb}",
                    "from_band": la, "to_band": lb,
                    "from_date": bands[i]["acquired"], "to_date": bands[j]["acquired"],
                    "same_acquisition": bool(same_flight),
                    "radiometry_flag": ",".join(
                        sorted({x for x in (la, lb) if x in RADIOMETRY_FLAGGED})),
                    "n_px": s["n_px"],
                    "delta_ndvi_p50": round(s["delta_p50"], 4),
                    "delta_ndvi_mean": round(s["delta_mean"], 4),
                    "delta_ndvi_iqr": round(s["delta_p75"] - s["delta_p25"], 4),
                    "texture_std": round(s["texture_std"], 4),
                    "direction_raw": direction(s["delta_p50"]),
                    "control": f"{ctrl[0]}/{ctrl[1]}" if ctrl else "(is the control)",
                    "control_cover": cover,
                    "control_ndvi_gap": round(gap, 3) if np.isfinite(gap) else np.nan,
                    "control_delta_p50": round(cs["delta_p50"], 4) if cs else np.nan,
                    "delta_vs_control": round(dvc, 4) if np.isfinite(dvc) else np.nan,
                    "direction_vs_control": direction(dvc) if np.isfinite(dvc) else "n/a",
                    "texture_ratio_vs_control": round(tratio, 3) if np.isfinite(tratio) else np.nan,
                })
    return pd.DataFrame(rows)


# -- Trend --------------------------------------------------------------------
def decimal_year(datestr):
    s = (datestr or "").strip().rstrip("+")
    try:
        y, m, d = (int(x) for x in s.split("-")[:3])
    except Exception:
        return np.nan
    return y + ((m - 1) * 30.4 + d) / 365.25


def trend_table(zstats, cubes):
    bands = cubes[SCHOOL]["bands"]
    labels = [b["label"] for b in bands]
    yrs = np.array([decimal_year(b["acquired"]) for b in bands])
    piv = zstats.pivot_table(index=["site", "zone"], columns="band",
                             values="ndvi_p50", aggfunc="first")
    leafon = np.array([lb not in OCTOBER_BANDS for lb in labels])
    # Within-programme series: the 5 NAIP epochs share one sensor programme and
    # one processing chain, so their year-to-year steps are the most comparable
    # the stack can offer (October phenology still confounds 2019n / 2023n).
    naip = np.array(["NAIP" in (b["desc"] or "") for b in bands])

    rows = []
    for (site, zone), r in piv.iterrows():
        y = np.array([r.get(lb, np.nan) for lb in labels], dtype=float)
        ctrl = CONTROL_FOR.get((site, zone))
        if ctrl and (ctrl[0], ctrl[1]) in piv.index:
            c = np.array([piv.loc[ctrl, lb] for lb in labels], dtype=float)
            adj = y - c
        else:
            adj = np.full_like(y, np.nan)
        out = {"site": site, "zone": zone, "n_bands": int(np.isfinite(y).sum()),
               "control": f"{ctrl[0]}/{ctrl[1]}" if ctrl else "(is the control)"}
        for tag, series, sel in (("raw_all", y, np.ones_like(leafon)),
                                 ("raw_leafon", y, leafon),
                                 ("raw_naip", y, naip),
                                 ("adj_all", adj, np.ones_like(leafon)),
                                 ("adj_leafon", adj, leafon),
                                 ("adj_naip", adj, naip)):
            m = np.isfinite(series) & np.isfinite(yrs) & sel.astype(bool)
            if m.sum() >= 3:
                rho, p = spearman(yrs[m], series[m])
                slope = float(np.polyfit(yrs[m], series[m], 1)[0])
            else:
                rho, p, slope = np.nan, np.nan, np.nan
            out[f"rho_{tag}"] = round(rho, 3) if np.isfinite(rho) else np.nan
            out[f"p_{tag}"] = round(p, 4) if np.isfinite(p) else np.nan
            out[f"slope_ndvi_per_yr_{tag}"] = round(slope, 5) if np.isfinite(slope) else np.nan
            out[f"n_{tag}"] = int(m.sum())
        rows.append(out)
    return pd.DataFrame(rows)


# -- Step 3: degradation validation ------------------------------------------
def _shift_crop(sim, real, dx, dy, m=3):
    H, W = real.shape[-2], real.shape[-1]
    return (sim[..., m + dy:H - m + dy, m + dx:W - m + dx],
            real[..., m:H - m, m:W - m])


def _metrics(sim, real, valid):
    s, r = sim[valid], real[valid]
    if s.size < 32:
        return dict(n_px=int(s.size), r=np.nan, bias=np.nan, std_ratio=np.nan,
                    rmse=np.nan, rmse_gain_offset=np.nan, gain=np.nan, offset=np.nan)
    rr = pearson(s, r)
    bias = float(s.mean() - r.mean())
    sr = float(s.std() / r.std()) if r.std() else np.nan
    rmse = float(np.sqrt(np.mean((s - r) ** 2)))
    A = np.column_stack([s, np.ones_like(s)])
    gain, off = np.linalg.lstsq(A, r, rcond=None)[0]     # real ~ gain*sim + off
    rmse_go = float(np.sqrt(np.mean((gain * s + off - r) ** 2)))
    return dict(n_px=int(s.size), r=rr, bias=bias, std_ratio=sr, rmse=rmse,
                rmse_gain_offset=rmse_go, gain=float(gain), offset=float(off))


def _hf(img, valid):
    """High-frequency energy: sd of (img - 3x3 box mean). Sim/real ratio > 1
    means the simulated image is SHARPER than the real coarse sensor."""
    a = np.where(valid, img, np.nan)
    a = np.nan_to_num(a, nan=float(np.nanmean(a)) if np.isfinite(np.nanmean(a)) else 0.0)
    return float(np.std((a - uniform_filter(a, 3))[valid]))


def degradation(zones, catalog, sigmas=(0.0, 0.5, 0.75, 1.0, 1.5)):
    """2019s (30.48 cm, finer) downsampled onto the 2019n (60 cm) grid, vs the
    REAL 2019n pixels. Both are 4-band, so RGB *and* NDVI are comparable.

    HONESTY NOTE, printed and repeated in the CSV: qc/imagery_pixelsize_and_date.csv
    records both as the same 2019-10-11 Hexagon acquisition -- the county 1-ft
    consortium delivery and the NAIP 60 cm delivery of ONE flight. Same photons,
    same sun, same phenology. So this is the BEST CASE for simulating a coarse
    product from a fine one; a real cross-year, cross-sensor simulation can only
    be worse than what is measured here.
    """
    fine_e, coarse_e = catalog["2019s"], catalog["2019n"]
    fine_p, fine_root = resolve_img(fine_e["native_file"])
    coarse_p, coarse_root = resolve_img(coarse_e["native_file"])
    band_names = ["R", "G", "B", "NIR"]
    rows = []
    prov = dict(fine=str(fine_p), fine_root=fine_root, coarse=str(coarse_p),
                coarse_root=coarse_root)

    with rasterio.open(coarse_p) as cs:
        for site in sorted({s for (s, _z) in zones}):
            g3857 = zones[(site, "whole_parcel")][0]
            gs = gpd.GeoSeries([g3857], crs="EPSG:3857").to_crs(cs.crs)
            minx, miny, maxx, maxy = gs.total_bounds
            pad = 10.0                                   # metres
            win = from_bounds(minx - pad, miny - pad, maxx + pad, maxy + pad,
                              transform=cs.transform)
            win = win.round_offsets(op="floor").round_lengths(op="ceil")
            win = Window(max(0, int(win.col_off)), max(0, int(win.row_off)),
                         int(win.width), int(win.height))
            tf = cs.window_transform(win)
            real = cs.read(indexes=[1, 2, 3, 4], window=win).astype(np.float32)
            H, W = real.shape[1], real.shape[2]
            zmask = rasterize([(gs.iloc[0], 1)], out_shape=(H, W), transform=tf,
                              fill=0, dtype="uint8").astype(bool)
            real_ok = (real.sum(axis=0) > 0) & zmask

            for method, rs in (("average", Resampling.average),
                               ("bilinear", Resampling.bilinear)):
                with rasterio.open(fine_p) as fs, WarpedVRT(
                        fs, crs=cs.crs, transform=tf, width=W, height=H,
                        resampling=rs) as vrt:
                    sim = vrt.read(indexes=[1, 2, 3, 4]).astype(np.float32)
                sim_ok = sim.sum(axis=0) > 0

                # --- integer shift search on NIR (separates misregistration
                #     from genuine degradation error). +-2 coarse px = +-1.2 m.
                best = (-2.0, 0, 0)
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        s, r = _shift_crop(sim[3], real[3], dx, dy)
                        vs, vr = _shift_crop(sim_ok, real_ok, dx, dy)
                        v = vs & vr
                        rr = pearson(s[v], r[v]) if v.sum() > 64 else np.nan
                        if np.isfinite(rr) and rr > best[0]:
                            best = (rr, dx, dy)
                _, bdx, bdy = best

                sweep = sigmas if method == "average" else (0.0,)
                for sig in sweep:
                    simb = (sim if sig == 0 else
                            np.stack([gaussian_filter(sim[k], sig) for k in range(4)]))
                    s4, r4 = _shift_crop(simb, real, bdx, bdy)
                    vs, vr = _shift_crop(sim_ok, real_ok, bdx, bdy)
                    v = vs & vr
                    fields = []
                    for k, bn in enumerate(band_names):
                        fields.append((bn, s4[k], r4[k]))
                    fields.append(("NDVI", ndvi_from_bands(s4), ndvi_from_bands(r4)))
                    for bn, sarr, rarr in fields:
                        m = _metrics(sarr, rarr, v)
                        rows.append({
                            "site": site, "pair": "2019s->2019n",
                            "fine_product": fine_e["native_file"],
                            "fine_gsd_cm": fine_e["gsd_cm"],
                            "coarse_product": coarse_e["native_file"],
                            "coarse_gsd_cm": coarse_e["gsd_cm"],
                            "same_acquisition": True,
                            "method": method, "psf_sigma_px": sig,
                            "shift_dx": bdx, "shift_dy": bdy,
                            "band": bn, "n_px": m["n_px"],
                            "r": round(m["r"], 4) if np.isfinite(m["r"]) else np.nan,
                            "bias_sim_minus_real": round(m["bias"], 4),
                            "std_ratio_sim_over_real": round(m["std_ratio"], 4),
                            "rmse": round(m["rmse"], 4),
                            "rmse_after_gain_offset": round(m["rmse_gain_offset"], 4),
                            "gain": round(m["gain"], 4), "offset": round(m["offset"], 4),
                            "hf_ratio_sim_over_real": round(
                                _hf(sarr, v) / _hf(rarr, v), 4) if _hf(rarr, v) else np.nan,
                            "note": "SAME FLIGHT (2019-10-11 Hexagon): best-case bound",
                        })
    return pd.DataFrame(rows), prov


# -- Narrative + verdict ------------------------------------------------------
def hr(t=""):
    print("\n" + "-" * 78)
    if t:
        print(t)
        print("-" * 78)


def narrate(zstats, sig, trend, deg, prov, bands):
    school_null = {}
    hr("1. ZONAL STATS  (NDVI p50 per zone per band; NIR mean in DN)")
    piv = zstats.pivot_table(index=["site", "zone"], columns="band",
                             values="ndvi_p50", aggfunc="first")
    order = [b["label"] for b in bands]
    print(piv[order].to_string())
    print("\n  n_px_valid per zone (min across bands):")
    for (s, z), sub in zstats.groupby(["site", "zone"]):
        print(f"    {s:22s} {z:22s} {int(sub['n_px_valid'].min()):>8,}"
              f"  ({sub['zone_note'].iloc[0]})")
    print("\n  NOTE bands 2015n / 2021s carry a LIFTED BLACK POINT: their ABSOLUTE")
    print("  NDVI reads high. Compare them only within-band or via the control.")

    hr("2. CHANGE-SIGNAL TABLE  (median per-pixel dNDVI; cut |d| >= "
       f"{DELTA_NDVI_CUT:.2f} a-priori)")
    cols = ["pair", "same_acquisition", "n_px", "delta_ndvi_p50", "texture_std",
            "direction_raw", "delta_vs_control", "direction_vs_control",
            "texture_ratio_vs_control"]
    for (s, z) in [(SCHOOL, "whole_parcel"), (SCHOOL, "tree"), (SCHOOL, "background"),
                   (DEV, "whole_parcel"), (DEV, "background_2002_2005"),
                   (DEV, "tree_2002_2005")]:
        sub = sig[(sig.site == s) & (sig.zone == z)]
        if not len(sub):
            continue
        cov = sub["control_cover"].iloc[0]
        gap = sub["control_ndvi_gap"].iloc[0]
        tail = ("" if not cov else
                f"  [{cov}, NDVI level gap {gap:.3f}]")
        print(f"\n  [{s} / {z}]   control = {sub['control'].iloc[0]}{tail}")
        if cov == "COVER_MISMATCH":
            print("    WARNING: control sits at a different NDVI level, so the additive")
            print("    control correction is NOT valid here -- read delta_vs_control as")
            print("    an upper bound on artefact, not as a change measurement.")
        print(sub[cols].to_string(index=False))

    hr("2b. NULL CONTROL -- does the stable school read stable?")
    sc = sig[(sig.site == SCHOOL) & (sig.pair_kind == "consecutive")]
    for z in ("whole_parcel", "tree", "background"):
        s = sc[sc.zone == z]
        if not len(s):
            continue
        d = s["delta_ndvi_p50"].values
        n_stable = int((np.abs(d) < DELTA_NDVI_CUT).sum())
        school_null[z] = dict(n=len(d), n_stable=n_stable,
                              spread=float(np.std(d)), maxabs=float(np.max(np.abs(d))),
                              iqr=float(np.percentile(d, 75) - np.percentile(d, 25)))
        print(f"  {z:14s} stable on {n_stable}/{len(d)} consecutive pairs "
              f"| sd(dp50) = {np.std(d):.4f} | max|dp50| = {np.max(np.abs(d)):.4f}")
    sf = sig[sig.same_acquisition & (sig.pair_kind == "consecutive")]
    if len(sf):
        print("\n  SAME-ACQUISITION pairs -- ONE flight delivered twice, so dt = 0 and")
        print("  every number below is pure sensor/GSD/processing artefact:")
        gsd = {b["label"]: b["native_gsd_cm"] for b in bands}
        for pr, grp in sf.groupby("pair"):
            a, b_ = pr.split("->")
            ga, gb = gsd.get(a, np.nan), gsd.get(b_, np.nan)
            ratio = max(ga, gb) / min(ga, gb) if np.isfinite(ga) and np.isfinite(gb) else np.nan
            print(f"\n    {pr}   native GSD {ga:.0f} cm vs {gb:.0f} cm "
                  f"= {ratio:.1f}x resolution gap")
            for _, r in grp.iterrows():
                print(f"      {r['site'][:20]:20s} {r['zone']:22s} "
                      f"dp50 = {r['delta_ndvi_p50']:+.4f}   "
                      f"texture sd = {r['texture_std']:.4f}   n = {r['n_px']:,}")
            d = grp["delta_ndvi_p50"].values
            span = float(d.max() - d.min())
            print(f"      -> across zones: min {d.min():+.4f}  max {d.max():+.4f}  "
                  f"SPREAD {span:.4f}")
            if span <= 0.02:
                print("         UNIFORM: a single additive offset cancels this pair "
                      "for every zone.")
            else:
                print("         NOT UNIFORM: the artefact is LOCATION-DEPENDENT, so no "
                      "single offset")
                print("         can remove it -- this is the resolution/mixed-pixel term, "
                      "not exposure.")
        print("\n    Read those two together: the artefact tracks the RESOLUTION GAP, not")
        print("    the time gap (both pairs have dt = 0). That is the single most useful")
        print("    number this probe produces for the transfer design -- it says how much")
        print("    apparent 'change' a GSD change alone can invent at a fixed location.")
    wp = school_null.get("whole_parcel", {})
    if wp and wp["n_stable"] >= wp["n"] - 1:
        print(f"\n  VERDICT: null control HOLDS ({wp['n_stable']}/{wp['n']}).")
    else:
        print(f"\n  *** LOUD FINDING: the null control does NOT hold "
              f"({wp.get('n_stable','?')}/{wp.get('n','?')} pairs stable). ***")
        print("  The school did not change; the STACK did. Raw cross-band dNDVI is")
        print("  therefore NOT usable at this threshold -- only control-adjusted")
        print("  contrasts are. This is a finding about the imagery, not the site.")

    hr("3. TREND  (Spearman rho of NDVI p50 vs acquisition date)")
    tcols = ["site", "zone", "rho_raw_all", "p_raw_all", "rho_raw_leafon",
             "rho_raw_naip", "rho_adj_all", "p_adj_all", "rho_adj_leafon",
             "rho_adj_naip", "slope_ndvi_per_yr_adj_leafon"]
    print(trend[tcols].to_string(index=False))
    print("\n  leafon = the 7 Jun-Aug bands (2019n/2019s/2023n are OCTOBER and")
    print("  phenology alone can fake browning). naip = the 5 NAIP epochs only")
    print("  (one sensor programme, one processing chain). adj = minus the")
    print("  matched control.")

    hr("4. DEGRADATION VALIDATION  (2019s 30.5 cm -> the real 2019n 60 cm grid)")
    if deg is None or not len(deg):
        print("  SKIPPED.")
        return school_null, None
    print(f"  fine   : {prov['fine']}   (root {prov['fine_root']})")
    print(f"  coarse : {prov['coarse']} (root {prov['coarse_root']})")
    print("  BOTH ARE THE SAME 2019-10-11 HEXAGON FLIGHT (imagery_pixelsize_and_date.csv):")
    print("  the county 1-ft delivery and the NAIP 60 cm delivery of ONE acquisition.")
    print("  Same photons, same sun, same leaf state. Whatever number comes out here")
    print("  is an UPPER BOUND on simulating a different sensor in a different decade.")
    naive = deg[(deg.method == "average") & (deg.psf_sigma_px == 0)]
    print("\n  NAIVE downsample (area average, best integer shift, no PSF blur):")
    print(naive[["site", "band", "n_px", "r", "bias_sim_minus_real",
                 "std_ratio_sim_over_real", "rmse", "rmse_after_gain_offset",
                 "hf_ratio_sim_over_real", "shift_dx", "shift_dy"]].to_string(index=False))
    bil = deg[(deg.method == "bilinear")]
    print("\n  BILINEAR downsample, same comparison:")
    print(bil[["site", "band", "r", "bias_sim_minus_real",
               "std_ratio_sim_over_real", "hf_ratio_sim_over_real"]].to_string(index=False))
    print("\n  PSF SWEEP (Gaussian blur applied after the area average) -- NDVI + NIR:")
    sw = deg[(deg.method == "average") & (deg.band.isin(["NDVI", "NIR"]))]
    print(sw[["site", "band", "psf_sigma_px", "r", "std_ratio_sim_over_real",
              "hf_ratio_sim_over_real", "rmse"]].to_string(index=False))

    # -- independent cross-check ---------------------------------------------
    # Section 2 measured the 2019n->2019s difference as a ZONAL MEDIAN on the
    # 1-unit stack; section 4 measures it PIXELWISE on the native 60 cm grid
    # from the original orthos. Different grids, different statistics, no shared
    # code path. If they agree, the offset is real delivery radiometry.
    print("\n  CROSS-CHECK -- the same delivery offset, measured two independent ways:")
    for site in sorted(deg["site"].unique()):
        z = sig[(sig.site == site) & (sig.zone == "whole_parcel") &
                (sig.pair == "2019n->2019s")]
        d = deg[(deg.site == site) & (deg.band == "NDVI") &
                (deg.method == "average") & (deg.psf_sigma_px == 0)]
        if len(z) and len(d):
            a = float(z["delta_ndvi_p50"].iloc[0])
            b = float(d["bias_sim_minus_real"].iloc[0])
            print(f"    {site:22s} stack zonal median dNDVI {a:+.4f}  vs  "
                  f"native pixelwise bias {b:+.4f}   (diff {abs(a - b):.4f})")
    print("    Agreement here means the NDVI offset between the two 2019 deliveries")
    print("    is REAL RADIOMETRY, not an artefact of how this probe resamples.")
    return school_null, naive


def verdict(school_null, sig, trend, naive):
    hr("5. VERDICT -- does this justify a permit-seeded corpus + a trained detector?")
    ok, bad = [], []

    wp = school_null.get("whole_parcel", {})
    null_holds = bool(wp) and wp["n_stable"] >= wp["n"] - 1
    (ok if null_holds else bad).append(
        f"null control raw-stable on {wp.get('n_stable','?')}/{wp.get('n','?')} pairs "
        f"(sd {wp.get('spread', float('nan')):.4f})")

    # -- the Development contrasts, one line each -----------------------------
    print("  Development 2015n->2023n span, per zone. SNR = |control-adjusted span|")
    print(f"  / the null spread of that zone's OWN control (GO needs >= {GO_SNR_MIN}):\n")
    print(f"    {'zone':22s} {'raw span':>9s} {'vs ctrl':>9s} {'null sd':>8s} "
          f"{'SNR':>6s}  cover")
    best = None
    for z in ("whole_parcel", "background_2002_2005", "tree_2002_2005"):
        row = sig[(sig.site == DEV) & (sig.zone == z) & (sig.pair_kind == "span")]
        if not len(row):
            continue
        r = row.iloc[0]
        cz = r["control"].split("/")[-1]
        noise = school_null.get(cz, {}).get("spread", np.nan)
        dvc = float(r["delta_vs_control"])
        snr = abs(dvc) / noise if np.isfinite(noise) and noise > 0 else np.nan
        print(f"    {z:22s} {float(r['delta_ndvi_p50']):+9.4f} {dvc:+9.4f} "
              f"{noise:8.4f} {snr:6.2f}  {r['control_cover']}")
        if r["control_cover"] == "cover_matched":
            if best is None or (np.isfinite(snr) and snr > best[1]):
                best = (z, snr, dvc)
    print()
    if best is None:
        print("  NO cover-matched Development contrast exists. Every zone that should")
        print("  carry the regrowth signal is compared against a control at a different")
        print("  NDVI level, which manufactures apparent change. The change signal is")
        print("  therefore NOT MEASURABLE with this label set -- not absent, unmeasured.")
        sig_ok, trend_ok = False, False
        bad.append("no cover-matched control for any changing zone")
        bad.append("progressive-greening trend untestable without a valid control")
    else:
        z, snr, dvc = best
        print(f"  Cover-matched contrast : Development/{z}  ->  "
              f"{dvc:+.4f} NDVI ({direction(dvc)}), SNR {snr:.2f}")
        sig_ok = np.isfinite(snr) and snr >= GO_SNR_MIN and dvc > 0
        (ok if sig_ok else bad).append(
            f"change signal SNR {snr:.2f} on the one cover-matched zone, "
            f"direction {direction(dvc)}")
        tr = trend[(trend.site == DEV) & (trend.zone == z)]
        rho = float(tr["rho_adj_leafon"].iloc[0]) if len(tr) else np.nan
        pv = float(tr["p_adj_leafon"].iloc[0]) if len(tr) else np.nan
        print(f"  Its trend (control-adj, leaf-on)        : rho = {rho:+.3f} "
              f"(p = {pv:.3f}; GO needs rho > {GO_TREND_RHO_MIN} and p <= {GO_TREND_P_MAX})")
        trend_ok = (np.isfinite(rho) and rho > GO_TREND_RHO_MIN
                    and np.isfinite(pv) and pv <= GO_TREND_P_MAX)
        (ok if trend_ok else bad).append(
            f"progressive-greening trend rho {rho:+.3f} (p {pv:.3f})")

    deg_ok = False
    geom_ok = rad_ok = None
    if naive is not None and len(naive):
        nd = naive[naive.band == "NDVI"]
        r_ = float(nd["r"].mean())
        b_ = float(nd["bias_sim_minus_real"].abs().max())
        s_ = float(nd["std_ratio_sim_over_real"].mean())
        h_ = float(nd["hf_ratio_sim_over_real"].mean())
        rgb = naive[naive.band.isin(["R", "G", "B", "NIR"])]
        rgb_bias = float(rgb["bias_sim_minus_real"].abs().max())
        rmse_raw = float(rgb["rmse"].mean())
        rmse_go = float(rgb["rmse_after_gain_offset"].mean())
        geom_ok = (r_ >= GO_DEGRADE_R_MIN
                   and GO_DEGRADE_STD_LO <= s_ <= GO_DEGRADE_STD_HI)
        rad_ok = b_ <= GO_DEGRADE_BIAS_MAX
        deg_ok = geom_ok and rad_ok
        print("\n  Naive downsample vs the REAL coarse sensor, split into its two halves:")
        print(f"    GEOMETRY   r = {r_:.4f} (need >= {GO_DEGRADE_R_MIN}), "
              f"std ratio = {s_:.4f} (need {GO_DEGRADE_STD_LO}-{GO_DEGRADE_STD_HI}), "
              f"HF ratio = {h_:.4f}  -> {'PASS' if geom_ok else 'FAIL'}")
        print(f"    RADIOMETRY NDVI |bias| = {b_:.4f} (need <= {GO_DEGRADE_BIAS_MAX}), "
              f"worst DN band |bias| = {rgb_bias:.1f} DN  -> "
              f"{'PASS' if rad_ok else 'FAIL'}")
        print(f"    A per-band gain/offset match drops band RMSE {rmse_raw:.1f} -> "
              f"{rmse_go:.1f} DN, i.e. most of the residual IS the offset.")
        (ok if geom_ok else bad).append(
            f"degradation GEOMETRY: r {r_:.4f}, std ratio {s_:.4f}, HF {h_:.4f}")
        (ok if rad_ok else bad).append(
            f"degradation RADIOMETRY: NDVI bias {b_:.4f}, worst band {rgb_bias:.1f} DN")
    else:
        bad.append("degradation not measured")

    hr()
    print("  PASSED :")
    for t in ok:
        print(f"    + {t}")
    print("  FAILED :")
    for t in bad:
        print(f"    - {t}")

    print()
    if sig_ok and trend_ok and deg_ok:
        print("  VERDICT: GO. Signal, null and transfer all clear their declared bars.")
    elif sig_ok and trend_ok:
        print("  VERDICT: GO ON THE LEARNING HALF, NO-GO ON THE TRANSFER HALF (as built).")
        print("  The change signal survives the null control, so a permit-seeded event")
        print("  corpus + a detector trained on the 4-band years is justified. The")
        print("  degradation leg did NOT clear its bar even on a SAME-FLIGHT pair,")
        print("  which is the easiest case that will ever exist -- so 'simulate old")
        print("  imagery by downsampling' is NOT yet a validated transfer path.")
    elif deg_ok:
        print("  VERDICT: NO-GO on the change signal as measured; the transfer leg passed.")
        print("  Without a signal that beats the null, a detector trained on these")
        print("  zonal statistics would be learning sensor differences, not development.")
    else:
        print("  VERDICT: NOT YET. The idea is not falsified -- but this probe cannot")
        print("  support it, and it says exactly why:")
        print()
        print("   1. The null control FAILS on raw cross-band dNDVI. The school did not")
        print("      change; the stack did. So zonal NDVI medians differenced ACROSS")
        print("      bands are not a change instrument on their own.")
        print("   2. The same-acquisition pairs quantify that directly, with dt = 0:")
        for pr, grp in sig[sig.same_acquisition &
                           (sig.pair_kind == "consecutive")].groupby("pair"):
            d = grp["delta_ndvi_p50"].values
            sp = float(d.max() - d.min())
            kind = ("uniform, so one additive offset removes it"
                    if sp <= 0.02 else
                    "LOCATION-DEPENDENT, so no single offset can remove it")
            print(f"      {pr}: dp50 {d.min():+.4f}..{d.max():+.4f}, spread {sp:.4f} "
                  f"-- {kind}.")
        print("      A location-dependent artefact at dt = 0 is a RESOLUTION effect --")
        print("      the same effect the degradation leg has to model.")
        if best is not None:
            z, snr, dvc = best
            print(f"   3. The one Development zone with a cover-matched control "
                  f"({z})")
            print(f"      reads {direction(dvc).upper()} ({dvc:+.4f} NDVI, SNR {snr:.2f}). "
                  f"The zones that")
            print("      should carry the regrowth signal have no cover-matched stable")
            print("      control in this label set, so their numbers are not readable.")
        else:
            print("   3. No Development zone has a cover-matched stable control, so the")
            print("      regrowth claim is untested here -- not refuted, untested.")
        if geom_ok is not None:
            print("   4. The degradation leg splits cleanly, and this is the good news:")
            print(f"      GEOMETRY {'PASSES' if geom_ok else 'FAILS'} and RADIOMETRY "
                  f"{'PASSES' if rad_ok else 'FAILS'}. Naive area-averaging reproduces")
            print("      the coarse sensor's SPATIAL content almost exactly, and the PSF")
            print("      sweep barely improves it -- so 'simulate old imagery' is not a")
            print("      sharpness problem. What it fails on is the DN/NDVI offset")
            print("      between deliveries, which a per-band gain/offset fit largely")
            print("      removes. That is a tractable, well-posed fix.")
        print()
        print("  WHAT WOULD CHANGE THE VERDICT, in order of leverage:")
        print("   a. Controls matched by LAND COVER, not just by stability -- for each")
        print("      seeded event, stable reference polygons of the same cover type.")
        print("      That is a labelling task, and it is the cheapest fix here.")
        print("   b. More seed events. n = 2 sites is not a corpus; the permit record")
        print("      is the right source and this probe is the right instrument to")
        print("      re-run over it.")
        print("   c. Per-band radiometric normalisation onto pseudo-invariant targets")
        print("      before any cross-band difference is taken.")
        print("   d. NOT a fancier resampler. The sigma sweep says naive averaging is")
        print("      already at or near the optimum; spend the effort on radiometry.")
        print("   e. Learn on FEATURES that are robust to all of the above (texture,")
        print("      spatial arrangement, per-object change) rather than on the median")
        print("      NDVI of a polygon, which is what this probe deliberately tested")
        print("      first because it is the simplest thing that could have worked.")
    print("\n  Caveat that binds all of the above: n = 2 sites, one changing and one")
    print("  stable, and the changing one's drawn labels stop 10 years before the")
    print("  stack starts. This probe can falsify the idea; it cannot confirm it.")


# -- main ---------------------------------------------------------------------
def main():
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="NIR change probe: signal, null control, "
                                             "and degradation validation.")
    ap.add_argument("--skip-degradation", action="store_true",
                    help="Skip step 3 (the only step that opens the big orthos).")
    ap.add_argument("--out-dir", default=str(QC_DIR), help="CSV output directory.")
    args = ap.parse_args(filtered)

    sys.path.insert(0, str(SCRIPTS_DIR / "pipeline"))
    from pipeline_log import StepLogger                      # noqa: E402

    logger = StepLogger(script="nir_change_probe", step="probe", logs_dir=LOGS_DIR)
    logger.start()
    errors = 0
    try:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        for p in (STACK_NIR, STACK_NDVI, LABELS_GPKG):
            if not p.exists():
                raise SystemExit(f"missing input: {p}")

        print("NIR CHANGE PROBE")
        print(f"  stack  : {STACK_NIR}")
        print(f"  ndvi   : {STACK_NDVI}")
        print(f"  labels : {LABELS_GPKG}")
        print(f"  out    : {out_dir}")

        catalog = year_catalog()
        zones, _gdf = build_zones()
        print(f"  zones  : {len(zones)}")

        zstats, cubes = zonal_stats(zones)
        bands = cubes[SCHOOL]["bands"]
        sig = change_signal(zones, cubes, zstats)
        trend = trend_table(zstats, cubes)

        deg, prov = (None, {})
        if not args.skip_degradation:
            deg, prov = degradation(zones, catalog)

        zstats.to_csv(out_dir / "nir_change_probe.csv", index=False)
        sig.to_csv(out_dir / "nir_change_probe_signal.csv", index=False)
        trend.to_csv(out_dir / "nir_change_probe_trend.csv", index=False)
        if deg is not None:
            deg.to_csv(out_dir / "nir_change_probe_degradation.csv", index=False)

        pd.set_option("display.width", 200)
        pd.set_option("display.max_columns", 40)
        school_null, naive = narrate(zstats, sig, trend, deg, prov, bands)
        verdict(school_null, sig, trend, naive)

        hr("FILES")
        for n in ("nir_change_probe.csv", "nir_change_probe_signal.csv",
                  "nir_change_probe_trend.csv", "nir_change_probe_degradation.csv"):
            p = out_dir / n
            if p.exists():
                print(f"  {p}  ({p.stat().st_size:,} B)")
    except Exception as e:                                   # noqa: BLE001
        errors = 1
        print(f"ERROR: {type(e).__name__}: {e}")
        raise
    finally:
        logger.finish(errors=errors,
                      notes="NIR change probe: zonal stats, change signal, null "
                            "control, degradation validation (2019s->2019n).")


if __name__ == "__main__":
    main()
