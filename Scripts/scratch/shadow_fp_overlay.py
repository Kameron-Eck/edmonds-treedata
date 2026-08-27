r"""Shadow-side FP overlay: do false positives concentrate on the down-sun side
of trees, and can NDVI screen them?

Kam's hypothesis (2026-08-26): the shadow side of trees fuels false positives
(dark shadow texture adjacent to canopy misread as canopy). He also observed the
normalized NDVI stack separates trees (bright) from shadows (dark) cleanly.

Design (template: scratch/roof_fp_overlay.py — FP definition, ccap scheme,
deployed threshold, TP control all copied):

  1. SUN AZIMUTH, EMPIRICAL: on the CHM grid, take the band of ground pixels a
     fixed step DOWN-direction-D from canopy (CHM>=2 m), for D = 0..345 step 15.
     The true shadow direction is the D whose band is DARKEST in the 2016 ortho.
     Prior from the catalog: 2016-08-12 ~09:05-09:50 PDT morning sun (ESE) ->
     shadows toward ~280-310. If no direction clearly wins, stop.
  2. BANDS on the prob raster's own grid: shadow-side band = ground pixels
     within ~5 m (16 px @ 1 ft) of a canopy edge in direction D*; control =
     same construction up-sun (D*+180). Overlap pixels excluded from both.
     Canopy EDGES come from the CHM (>=2 m), not C-CAP: C-CAP over-generalizes
     residential canopy (measured 2026-08-26) and its blob edges are not the
     physical shadow casters; the CHM is the actual height field. C-CAP stays
     the TRUTH for FP/TP (matching every live qc_indep row). Band statistics
     are restricted to CHM-valid, CHM-non-canopy ("off-tree ground") pixels so
     the three regions are comparable.
  3. FP density per region (shadow band / up-sun band / other ground), TP as
     the misregistration control.
  4. NDVI (normalized stack band 2 = 2016, x1000): means/percentiles for
     shadow-band FPs vs shadow-band TPs vs all TPs -> can a screen separate?

Scratch one-shot; writes a markdown summary; changes nothing else.
"""
import sys
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window

PROB = r"G:\My Drive\treedata\phase4\masks\edmonds_canopy_prob_2016_fullext_sectors_v1.tif"
THRESH = 0.5223
CCAP = r"D:\edmonds-pipeline\Imagery\ccap_2016_hires_lc_snohfull.tif"
CHM = r"D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif"
ORTHO = r"D:\edmonds-pipeline\Imagery\2016_snoh_1ft_rgbi.tif"
NDVI = r"D:\edmonds-pipeline\ARCGIS\MachineLearning\nir_stack\nir_stack_ndvi_norm_1m.tif"
NDVI_BAND = 2                                   # 2016 (normalized) per README
OUT_MD = (r"C:\Users\Kameron\AppData\Local\Temp\claude"
          r"\D--edmonds-pipeline-treedata-Scripts"
          r"\38ce7527-5e87-4d98-b55b-f039524783e8\scratchpad\shadow_fp_results.md")

CANOPY_CODES = {9, 10, 11, 13, 16}              # forest_wetland (primary def)
IGNORE_CODES = {0, 1, 24, 25}
CHM_CANOPY_DN = 10                              # 2 m at 0.2 m/DN
BAND_PX = 16                                    # ~5 m at 1 ft/px on the prob grid
AZ_STEP_PX = 4                                  # ~4 m probe step on the CHM 1 m grid
BLOCK = 2048


def shift_bool(a, drow, dcol):
    """Shift a bool array, zero-filling (no wrap)."""
    out = np.zeros_like(a)
    src_r = slice(max(0, -drow), a.shape[0] - max(0, drow))
    src_c = slice(max(0, -dcol), a.shape[1] - max(0, dcol))
    dst_r = slice(max(0, drow), a.shape[0] - max(0, -drow))
    dst_c = slice(max(0, dcol), a.shape[1] - max(0, -dcol))
    out[dst_r, dst_c] = a[src_r, src_c]
    return out


def dir_offsets(deg, dist):
    """(drow, dcol) moving `dist` px toward compass bearing `deg` (north-up grid)."""
    return (int(round(-dist * np.cos(np.radians(deg)))),
            int(round(dist * np.sin(np.radians(deg)))))


def estimate_azimuth():
    with rasterio.open(CHM) as c:
        chm = c.read(1)
        vrt_kw = dict(crs=c.crs, transform=c.transform, width=c.width,
                      height=c.height, resampling=Resampling.average)
    canopy = chm >= CHM_CANOPY_DN
    valid = chm > 0
    bright = np.zeros(chm.shape, np.float32)
    with rasterio.open(ORTHO) as o, WarpedVRT(o, **vrt_kw) as v:
        for r0 in range(0, chm.shape[0], BLOCK):
            h = min(BLOCK, chm.shape[0] - r0)
            win = Window(0, r0, chm.shape[1], h)
            rgb = v.read([1, 2, 3], window=win).astype(np.float32)
            bright[r0:r0 + h] = rgb.mean(axis=0)
    ortho_valid = bright > 0                     # ortho nodata collar reads 0
    rows = []
    for d in range(0, 360, 15):
        dr, dc = dir_offsets(d, AZ_STEP_PX)
        band = shift_bool(canopy, dr, dc) & ~canopy & valid & ortho_valid
        n = int(band.sum())
        rows.append((d, float(bright[band].mean()) if n else np.nan, n))
    ok = [r for r in rows if r[2] > 10000]
    win_d, win_b, _ = min(ok, key=lambda r: r[1])
    means = [b for _, b, _ in ok]
    spread = max(means) - min(means)
    second = sorted(means)[1]
    return win_d, win_b, second - win_b, spread, rows


def main():
    d_star, b_win, margin, spread, table = estimate_azimuth()
    lines = ["# Shadow-side FP overlay — 2016 fullext, sample footprint",
             "",
             f"Empirical shadow direction: **{d_star}°** (band brightness "
             f"{b_win:.1f}; margin to 2nd-darkest {margin:.2f}; full spread "
             f"{spread:.2f}). Sun azimuth ≈ {(d_star + 180) % 360}° "
             f"(prior: morning ESE sun, shadows ~280–310°).",
             "", "| dir° | band mean brightness | px |", "|---|---|---|"]
    for d, b, n in table:
        mark = " ← darkest" if d == d_star else ""
        lines.append(f"| {d} | {b:.2f}{mark} | {n:,} |")
    print("\n".join(lines[:6]))

    thr_dn = int(np.ceil(THRESH * 254.0 - 1e-9))
    down = [dir_offsets(d_star, t) for t in range(1, BAND_PX + 1)]
    up = [dir_offsets((d_star + 180) % 360, t) for t in range(1, BAND_PX + 1)]
    PAD = BAND_PX + 1
    reg = {k: dict(scor=0, fp=0, tp=0) for k in ("shadow", "upsun", "other")}
    nd = {k: dict(n=0, s=0.0, ss=0.0, hist=np.zeros(60, np.int64))
          for k in ("fp_shadow", "tp_shadow", "tp_all")}

    def nd_acc(key, vals):
        v = vals[vals > -32768] / 1000.0
        if v.size:
            nd[key]["n"] += v.size
            nd[key]["s"] += float(v.sum())
            nd[key]["ss"] += float((v * v).sum())
            h, _ = np.histogram(v, bins=60, range=(-1.0, 2.0))
            nd[key]["hist"] += h

    with rasterio.open(PROB) as p:
        vrt_kw = dict(crs=p.crs, transform=p.transform, width=p.width,
                      height=p.height)
        with rasterio.open(CCAP) as cds, rasterio.open(CHM) as hds, \
             rasterio.open(NDVI) as nds, \
             WarpedVRT(cds, **vrt_kw, resampling=Resampling.nearest) as cv, \
             WarpedVRT(hds, **vrt_kw, resampling=Resampling.nearest) as hv, \
             WarpedVRT(nds, **vrt_kw, resampling=Resampling.bilinear) as nv:
            for r0 in range(0, p.height, BLOCK):
                h = min(BLOCK, p.height - r0)
                pr0 = max(0, r0 - PAD)
                ph = min(p.height, r0 + h + PAD) - pr0
                top = r0 - pr0
                pwin = Window(0, pr0, p.width, ph)
                dn = p.read(1, window=pwin)
                valid = dn != 255
                if not valid[top:top + h].any():
                    continue
                chm = hv.read(1, window=pwin)
                chm_valid = chm > 0
                canopy = chm >= CHM_CANOPY_DN
                sb = np.zeros_like(canopy)
                ub = np.zeros_like(canopy)
                for dr, dc in down:
                    sb |= shift_bool(canopy, dr, dc)
                for dr, dc in up:
                    ub |= shift_bool(canopy, dr, dc)
                both = sb & ub
                ground = ~canopy & chm_valid
                sb = sb & ground & ~both
                ub = ub & ground & ~both
                ref = cv.read(1, window=pwin)
                scor = valid & ~np.isin(ref, list(IGNORE_CODES))
                called = (dn >= thr_dn) & scor
                ref_can = np.isin(ref, list(CANOPY_CODES))
                fp = called & ~ref_can
                tp = called & ref_can
                core = np.zeros(dn.shape, bool)
                core[top:top + h] = True          # count each pixel once
                for key, m in (("shadow", sb), ("upsun", ub),
                               ("other", ground & ~sb & ~ub)):
                    mm = m & core
                    reg[key]["scor"] += int((scor & mm).sum())
                    reg[key]["fp"] += int((fp & mm).sum())
                    reg[key]["tp"] += int((tp & mm).sum())
                ndvi = nv.read(NDVI_BAND, window=pwin).astype(np.int32)
                nd_acc("fp_shadow", ndvi[fp & sb & core])
                nd_acc("tp_shadow", ndvi[tp & sb & core])
                nd_acc("tp_all", ndvi[tp & core])

    lines += ["", "## FP/TP density by region (off-tree ground, CHM-valid only)",
              "", "| region | scorable px | FP px | FP density | TP px | TP density |",
              "|---|---|---|---|---|---|"]
    for k, label in (("shadow", f"shadow-side band (≤5 m, {d_star}°)"),
                     ("upsun", "up-sun band (control)"),
                     ("other", "other ground")):
        r = reg[k]
        fd = r["fp"] / r["scor"] if r["scor"] else float("nan")
        td = r["tp"] / r["scor"] if r["scor"] else float("nan")
        lines.append(f"| {label} | {r['scor']:,} | {r['fp']:,} | {fd:.4f} "
                     f"| {r['tp']:,} | {td:.4f} |")
    ratio = ((reg["shadow"]["fp"] / reg["shadow"]["scor"]) /
             (reg["upsun"]["fp"] / reg["upsun"]["scor"]))
    tratio = ((reg["shadow"]["tp"] / reg["shadow"]["scor"]) /
              (reg["upsun"]["tp"] / reg["upsun"]["scor"]))
    lines += ["", f"**Shadow/up-sun FP density ratio: {ratio:.2f}**  "
                  f"(TP control ratio: {tratio:.2f} — near 1.0 means bands are "
                  f"geometrically fair and any FP excess is real)"]

    lines += ["", "## NDVI (normalized 2016 band, ×1 shown as NDVI units)", "",
              "| population | n px | mean | sd | p10 | p50 |", "|---|---|---|---|---|---|"]
    stats = {}
    for k, label in (("fp_shadow", "shadow-band FPs"),
                     ("tp_shadow", "shadow-band TPs"),
                     ("tp_all", "all TPs")):
        d = nd[k]
        if d["n"]:
            mean = d["s"] / d["n"]
            sd = max(0.0, d["ss"] / d["n"] - mean * mean) ** 0.5
            cum = np.cumsum(d["hist"]) / d["n"]
            edges = np.linspace(-1.0, 2.0, 61)
            p10 = float(edges[np.searchsorted(cum, 0.10) + 1])
            p50 = float(edges[np.searchsorted(cum, 0.50) + 1])
            stats[k] = (mean, sd, p10, p50, d)
            lines.append(f"| {label} | {d['n']:,} | {mean:.3f} | {sd:.3f} "
                         f"| {p10:.2f} | {p50:.2f} |")
    if "fp_shadow" in stats and "tp_all" in stats:
        tp_p10 = stats["tp_all"][2]
        d = stats["fp_shadow"][4]
        edges = np.linspace(-1.0, 2.0, 61)
        below = int(d["hist"][: max(0, np.searchsorted(edges, tp_p10) - 1)].sum())
        lines += ["", f"Fraction of shadow-band FPs with NDVI below the all-TP "
                      f"10th percentile ({tp_p10:.2f}): "
                      f"**{100.0 * below / d['n']:.1f}%** — the share an NDVI "
                      f"screen could remove at ≤10% recall cost."]

    md = "\n".join(lines) + "\n"
    open(OUT_MD, "w", encoding="utf-8").write(md)
    print(md[md.index("## FP/TP"):])
    print("wrote", OUT_MD)


if __name__ == "__main__":
    sys.exit(main())
