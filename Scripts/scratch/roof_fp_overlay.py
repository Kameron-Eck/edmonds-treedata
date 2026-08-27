r"""Roof-FP overlay: what fraction of false-positive canopy calls sit on buildings?

Kam's hypothesis (2026-08-26): roofs are a major false-positive source, worse in
NIR. This one-shot instrument overlays each arm's FP pixels (model-canopy where
C-CAP says non-canopy, at the arm's DEPLOYED threshold) on the per-year building
mask built today by pipeline/make_building_masks.py.

Definitions (copied from qc/phase4_qc_indep.py CCAP_DEFAULT, primary canopy_def
= forest_wetland, matching the live=1 primary=1 rows):
  canopy ref  = C-CAP codes {9,10,11} forest  |  {13,16} forested wetland
  non-canopy  = grass{5,7,8} cropland{6} developed{2,3,4} barren{19,20}
                emergent_wetland{15,18} water{21,22,23}  (+ scrub {12,14,17},
                non-canopy under the forest_wetland definition)
  ignored     = {0,1,24,25} and prob-nodata pixels
  canopy call = prob_DN >= ceil(thresh*254 - 1e-9)   (golden-gate DN form)

Building layers (1 m nir_stack grid, uint8 1/0):
  mask  = building_mask_2016_1m.tif — footprints of record-present structures
          ALREADY +1 m buffered in true metres (see make_building_masks.py)
  halo  = mask dilated 2 px (~+2 m city-block metric) — roof-edge shadow band

Grid standardized on: each PROB raster's own grid (the scoring grid); C-CAP and
building layers warped onto it per block, nearest neighbor.

Output: pixel counts + fractions per arm, TP rows as the misregistration
control. Scratch one-shot: writes a markdown summary, changes nothing else.
"""
import sys
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.vrt import WarpedVRT
from scipy.ndimage import binary_dilation

MASKS = r"G:\My Drive\treedata\phase4\masks"
CCAP = r"G:\My Drive\treedata\Full_Image\Pipeline Imagery\ccap_2016_hires_lc.tif"
BMASK = r"G:\My Drive\treedata\buildings\masks\building_mask_2016_1m.tif"
OUT_MD = (r"C:\Users\Kameron\AppData\Local\Temp\claude"
          r"\D--edmonds-pipeline-treedata-Scripts"
          r"\38ce7527-5e87-4d98-b55b-f039524783e8\scratchpad\roof_fp_overlay_results.md")

ARMS = [
    ("nir_m06 (rgb+nir)", MASKS + r"\edmonds_canopy_prob_2016_nir_m06.tif", 0.5939),
    ("fullext (rgb+chm)", MASKS + r"\edmonds_canopy_prob_2016_fullext_sectors_v1.tif", 0.5223),
]
CANOPY = {9, 10, 11, 13, 16}                      # forest_wetland definition
IGNORE = {0, 1, 24, 25}
BLOCK = 2048


def build_bld_layers():
    """Return two in-memory rasters on the building mask's own 1 m grid:
    the shipped mask and its 2 px (~2 m) dilation."""
    with rasterio.open(BMASK) as b:
        arr = b.read(1)
        prof = b.profile.copy()
    halo = binary_dilation(arr.astype(bool), iterations=2).astype(np.uint8)
    mems = []
    for a in (arr, halo):
        m = MemoryFile()
        with m.open(**prof) as d:
            d.write(a, 1)
        mems.append(m)
    return mems


def run_arm(name, prob_path, thresh, bld_mems):
    thr_dn = int(np.ceil(thresh * 254.0 - 1e-9))
    tot = dict(fp=0, fp_b=0, fp_h=0, tp=0, tp_b=0, tp_h=0, valid=0)
    with rasterio.open(prob_path) as p:
        nod = p.nodata
        vrt_kw = dict(crs=p.crs, transform=p.transform, width=p.width,
                      height=p.height, resampling=Resampling.nearest)
        with rasterio.open(CCAP) as cds, \
             bld_mems[0].open() as bm, bld_mems[1].open() as hm, \
             WarpedVRT(cds, **vrt_kw) as cv, \
             WarpedVRT(bm, **vrt_kw, nodata=0) as bv, \
             WarpedVRT(hm, **vrt_kw, nodata=0) as hv:
            for row in range(0, p.height, BLOCK):
                h = min(BLOCK, p.height - row)
                win = rasterio.windows.Window(0, row, p.width, h)
                dn = p.read(1, window=win)
                valid = dn != nod if nod is not None else np.ones(dn.shape, bool)
                if not valid.any():
                    continue
                ref = cv.read(1, window=win)
                scorable = valid & ~np.isin(ref, list(IGNORE))
                if not scorable.any():
                    continue
                called = (dn >= thr_dn) & scorable
                ref_can = np.isin(ref, list(CANOPY))
                fp = called & ~ref_can
                tp = called & ref_can
                b = bv.read(1, window=win).astype(bool)
                hl = hv.read(1, window=win).astype(bool)
                tot["valid"] += int(scorable.sum())
                tot["fp"] += int(fp.sum());  tot["tp"] += int(tp.sum())
                tot["fp_b"] += int((fp & b).sum());  tot["tp_b"] += int((tp & b).sum())
                tot["fp_h"] += int((fp & hl).sum()); tot["tp_h"] += int((tp & hl).sum())
    return dict(name=name, thresh=thresh, thr_dn=thr_dn, **tot)


def pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def main():
    bld_mems = build_bld_layers()
    rows = [run_arm(*a, bld_mems) for a in ARMS]
    lines = [
        "# Roof-FP overlay — 2016, sample footprint (~11% of city, sector strips)",
        "",
        "FP = canopy call at the arm's DEPLOYED threshold where C-CAP (forest_wetland",
        "definition, matching live primary rows) says non-canopy. Building mask =",
        "record-present footprints +1 m (as shipped); halo = +2 px (~2 m) beyond that.",
        "Warp target: each prob raster's own grid, nearest neighbor.",
        "",
        "| arm | thresh | scorable px | FP px | FP in bld | FP in bld+halo | TP px | TP in bld | TP in bld+halo |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['thresh']} | {r['valid']:,} | {r['fp']:,} "
            f"| {r['fp_b']:,} ({pct(r['fp_b'], r['fp'])}) "
            f"| {r['fp_h']:,} ({pct(r['fp_h'], r['fp'])}) "
            f"| {r['tp']:,} | {r['tp_b']:,} ({pct(r['tp_b'], r['tp'])}) "
            f"| {r['tp_h']:,} ({pct(r['tp_h'], r['tp'])}) |")
    md = "\n".join(lines) + "\n"
    print(md)
    open(OUT_MD, "w", encoding="utf-8").write(md)
    print("wrote", OUT_MD)


if __name__ == "__main__":
    sys.exit(main())
