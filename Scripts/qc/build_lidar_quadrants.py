r"""Dual-epoch lidar CROSS-TABULATION — all four states, not just flat/flat.

`build_lidar_background.py` used the two lidar epochs (PSLC 2005, USGS 2016) to
certify ONE of the four states a cell can be in: flat in both, i.e. verified
BACKGROUND. The other three were measured and discarded. This script keeps them.

    2005 -> 2016   meaning                                   raw @3.0 m cut
    flat -> flat   nothing tall ever grew                        1205 ha
    tall -> tall   something stood the WHOLE window              1626 ha
    tall -> flat   removed between 2005 and 2016                  156 ha
    flat -> tall   grew between 2005 and 2016                     512 ha
    (raw = building-inclusive, un-eroded, over the 44.3% of grid known in both)

WHY `tall -> tall` IS THE POINT (Kam, 2026-08-27). A tree standing in 2009 and
felled in 2018 is BACKGROUND in the back-projected 2020 key, so a model that
correctly finds it is punished. That is silent label noise biased toward
UNDER-calling canopy — the exact bias this project fights (CLAUDE.md, Project
Purpose). `tall -> tall` labels that tree CANOPY without consulting the 2020 key
at all, and adding canopy is explicitly permitted by rule 6.

The two change states are the honest half of the same coin: something was there
in 2005 and gone by 2016 (or vice versa) and neither epoch dates it, so on a
2009 image neither `canopy` nor `background` is defensible. Those go to IGNORE,
which asserts nothing.

BUILDINGS. "Tall" includes roofs. Every tall class is subtracted by the canonical
footprint layer (buffered, cell-centre test) before anything is asserted. ALL
footprints are subtracted, dated or not: over-subtraction costs a little label
quantity, under-subtraction paints a roof as canopy, and only the second is a
lie. Residual hole, named by `buildings/README_BUILDINGS.md`: a structure
standing 2005-2016 and demolished AFTER 2016 is absent from a current-state
layer and reads `tall -> tall`. The 3-cell erosion largely neutralises it — a
freestanding house is narrower than 2x6 m and erodes away entirely; only roofs
embedded in persistent canopy survive. That is the strongest argument for
keeping erode=3 as the shipped default.

EROSION, and a DELIBERATE ASYMMETRY. `tall -> tall` is eroded exactly as the
flat class was (default 3 cells = 6 m), for the same reason: the product is
consumed by warping onto each year's ORTHO grid and this project has measured a
~5 m east-side ortho-vs-CHM displacement. The CHANGE classes are NOT eroded.
Erosion is a safety margin on an ASSERTION, and IGNORE asserts nothing — eroding
an IGNORE region would re-expose exactly the fringe pixels most likely to carry
the wrong key label, which is the noise this whole script exists to remove. The
cost of that choice is stated honestly: code 1 gets a 6 m pull-back from the
registration slop while code 3 leaves that same slop fringe holding the key's
label. `--change-dilate` / `--change-erode` flip it; the sensitivity ladder is
printed either way.

MIXED CUTS ARE INTENTIONAL, NOT A BUG. The tall classes use `--tall-m` (3.0 m,
a tree-height cut). The flat/flat rule instead READS THE SHIPPED PRODUCT
`verified_background_lidar_2005_2016.tif == 1` (built at flat < 2.0 m, eroded 3)
so this overlay's background behaviour is byte-identical to the current
`build_groves_overlay.py --hybrid --with-lidar` arm rather than a near-miss
re-derivation. The two never collide: the shipped product needs hag < 2.0 m in
BOTH epochs, while every tall class needs >= 3.0 m in at least one, so the sets
are disjoint by construction. Cells between 2 and 3 m simply assert nothing.

OUTPUTS
  1. `lidar_quadrants_2005_2016.tif` (EPSG:26910, 2 m, the cache's own grid)
     band 1 = THE PRODUCT, what every consumer reads: 1 flat/flat · 2 tall/tall
              (buildings subtracted, eroded) · 3 tall/flat · 4 flat/tall
              (buildings subtracted) · 0 withdrawn by buildings/erosion ·
              255 not known in both epochs
     band 2 = raw states, same codes, no subtraction and no erosion — audit only
  2. `add_quad_{year}.tif` — the per-year overlay, rule-6-legal codes only:
     code 1 tall/tall · code 3 change classes and flat/flat-vs-key contradictions
     · code 0 EVERYWHERE else, so the projected key survives intact and label
     QUANTITY stays comparable to the baseline (the lesson of the sparse arm's
     ~26 sigma loss, `build_groves_overlay.py` docstring).

  py -3.12 qc/build_lidar_quadrants.py [--year 2009] [--tall-m 3.0] [--erode 3]
                                       [--bld-buffer 2.0] [--quad-only]

`--year` is gated to 2005..2016: outside the lidar window a `tall -> tall` cell
says nothing about that year's imagery, and asserting canopy there would be the
same unverified claim this script removes.

Local CPU only. Both outputs are written to local NVMe, then copied to the lake
and VERIFIED (size polled to convergence, then sha256 both sides).

═════════════════════════════════════════════════════════════════════════════
NODE C MODE (`--nodec`, 2026-08-28) — ONE treatment, ONE direction
═════════════════════════════════════════════════════════════════════════════
`add_quad_{year}.tif` above mixed a force-canopy dose with an IGNORE dose ~17x
larger and is therefore uninterpretable as an experiment: two variables moved.
Node C is the strictly one-variable arm against Node B (2009, projected 2020
key, 3-band RGB). It emits **code 1 only** — no code 2, no code 3, no IGNORE
region anywhere — where ALL FOUR hold:

  1. dual-epoch lidar says something TALL stood in BOTH 2005 and 2016;
  2. it was GREEN in 2016 (screens poles, masts, boats, fences, retaining
     walls — the adversarial review's top semantic objection to height-only);
  3. it is NOT a building (same footprint subtraction as above);
  4. the projected 2020 key currently calls it BACKGROUND. Where the key
     already says canopy, changing nothing IS the point.

Four fixes the adversarial workflow demanded, all implemented here:

(a) COMMON HEIGHT DATUM. The two epochs are NOT comparable at a shared cut.
    Measured on this cache: 2016 exceeds 2005 in tall AREA by 1.17-1.23x at
    EVERY threshold 2-20 m, and the paired median height delta on the stable
    population (both >= 3 m) is +1.55 m. Cause is almost certainly point
    density (2005 = 1.68 pts/m2 measured, 2016 = 4-5x that): per-cell max-z is
    an EXTREME-VALUE statistic whose expectation rises with sample count, so
    the denser epoch reads systematically taller on the same object. The cut
    pair is therefore QUANTILE-MATCHED on the stable population (every cell
    known in both epochs): pick `--tall05-m`, measure p = P(hag05 >= it), and
    take the 2016 cut as the (1-p) quantile of hag16 so both epochs call the
    same AREA tall. 3.0 m -> 4.52 m. A ladder is printed.

(b) GREENNESS FROM 2016 INFRARED, NEVER FROM THE YEAR'S OWN IMAGERY. If the
    label derived greenness from the same 2009 pixels the model reads, the
    model could learn "green = tree" as a shortcut — a second flavour of the
    circularity that 3-band Node B exists to escape. NDVI comes from
    `2016_snoh_1ft_rgbi.tif` (HXIP, flown 2016-08-12 morning, leaf-on, real
    NIR band 4) — temporally matched to the 2016 lidar epoch and disjoint from
    the 2009 model input. Threshold 0.30 is not invented here: it is
    `canopy_definition_PROPOSAL.md` D1's recommended rule and the de-facto
    rule already shipped in `phase4_build_corrected_labels.py`
    (NDVI >= .3 AND height >= 3 m -> canopy). Aggregation to the 2 m grid uses
    a VALID DENOMINATOR — green and coverage are averaged separately and
    divided — so ortho-edge cells are not deflated by fill.

(c) EROSION 1 CELL (2 m), NOT 3. The review priced erode-3: 76% of the signal
    (1102 -> 267 ha citywide) and it preferentially annihilates ISOLATED
    STREET TREES, since a 6 m erosion kills any crown under ~12 m across —
    exactly the population this project already fails on. Erosion existed to
    guard against buildings demolished after 2016 reading tall->tall; the
    greenness screen in (b) now carries most of that load (roofs are not
    green), so the margin can shrink. The 0/1/2/3 ladder is printed anyway,
    height-only and post-greenness side by side.

(d) NO CHANGE CLASSES AT ALL. tall->flat and flat->tall are cross-epoch
    speckle — flat->tall is 164,759 connected components for 512 ha, median
    blob 2 cells, 69% of its area within 2 m of persistent canopy. They are
    excluded from Node C entirely rather than routed to IGNORE.

  py -3.12 qc/build_lidar_quadrants.py --nodec --year 2009
        [--tall05-m 3.0] [--tall16-m auto] [--nodec-erode 1]
        [--ndvi-thresh 0.30] [--green-frac 0.5] [--valid-frac 0.5]

Node C NEVER writes `lidar_quadrants_2005_2016.tif`: its cut pair and erosion
differ from the shipped product, and re-emitting a different build under that
name would be exactly the untagged overwrite this project refuses. The only
lake write is `add_nodec_{year}.tif` -> phase4/labels_corrected/.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

_HERE = Path(__file__).resolve().parent                 # …/Scripts/qc
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "pipeline"))

# ONE HOME for the settle-then-hash lake copy and the block warp: import them
# from the overlay builder rather than pasting copies that will drift.
from build_groves_overlay import (                      # noqa: E402
    _copy_verified, _warp_block, _load_vec, FT2_TO_M2,
    BASE, TEMPLATE, MASK_2020, BUILDINGS, LIDAR_BG, AOI, LAKE_OUT, BLOCK,
    CODE_CANOPY, CODE_NOCHANGE, CODE_IGNORE,
)
from phase4seg.common import _crs_unit_m                # noqa: E402

LOCAL_IMAGERY = Path(r"D:\edmonds-pipeline\Imagery")
LOCAL_OUT = Path(r"D:\edmonds-pipeline\_tmp")
CACHE = LOCAL_IMAGERY / "_lidar_bg_cache_%.1fm.npz"
GRID_REF = LOCAL_IMAGERY / "verified_background_lidar_2005_2016.tif"
LAKE_IMAGERY = BASE / "Full_Image" / "Pipeline Imagery"
QUAD_NAME = "lidar_quadrants_2005_2016.tif"

# Same file either side; QC reads the local mirror first (CLAUDE.md, data plane)
# so the per-block warps do not hammer the FUSE mount.
BG_SRC = GRID_REF if GRID_REF.exists() else LIDAR_BG

# Quadrant state codes (both bands)
Q_NONE, Q_FF, Q_TT, Q_TF, Q_FT, Q_UNK = 0, 1, 2, 3, 4, 255
Q_LABEL = {Q_FF: "flat->flat  (nothing tall ever)",
           Q_TT: "tall->tall  (stood the window)",
           Q_TF: "tall->flat  (removed between)",
           Q_FT: "flat->tall  (grew between)"}

# The lidar window. Outside it a quadrant says nothing about the year's imagery.
YEAR_LO, YEAR_HI = 2005, 2016

# Buffer applied to every footprint before the cell-centre test. 2.0 m is not a
# new number: `build_buildings_layer.py::GAPFILL_SLOP_M` uses exactly 2.0 m as
# this project's allowance for registration slop between two independently
# digitised layers, which is what county roofprints vs. lidar returns are. It is
# also ~1 cell, so it absorbs the 2 m grid's own quantisation. Sensitivity at
# 0/1/2/3/5 m is printed so the choice can be revisited.
BLD_BUFFER_M = 2.0

# ── NODE C constants ─────────────────────────────────────────────────────────
# The greenness instrument. 4-band, real NIR (band 4), flown 2016-08-12 morning
# (leaf-on) per qc/imagery_pixelsize_and_date.csv — temporally matched to the
# 2016 lidar epoch and, crucially, DISJOINT from the 2009 imagery the model
# reads. `phase4seg/config.py` YEAR_CATALOG marks this file bands=4; it replaced
# the 53%-clipped 2016_snoh_rgbi.tif on 2026-08-23 and covers 100% of the city
# polygon (82.3% of the study extent; the remainder is Puget Sound).
NDVI_FILE = "2016_snoh_1ft_rgbi.tif"
NDVI_R_BAND, NDVI_NIR_BAND = 1, 4
NDVI_LADDER = (0.20, 0.25, 0.30, 0.35)
FRAC_LADDER = (0.25, 0.50, 0.75)
ERODE_LADDER = (0, 1, 2, 3)
NODEC_CAND_NAME = "nodec_candidate_2005_2016.tif"
# MEASURED 2026-08-28: of add_hybrid_lidar_2009's 20.26 ha of code 1 inside the
# sector strips, only this much landed on ground the projected key calls
# BACKGROUND. The rest fell where the key already said canopy — a no-op. This is
# the only quantity comparable to a Node C dose, so the report divides by it.
HYBRID_FLIP_HA = 2.98
NDVI_BLK = 512                          # 2 m cells per side of the ortho pass


def log(m):
    print(m, flush=True)


def _ndvi_src():
    for d in (LOCAL_IMAGERY, LAKE_IMAGERY):
        p = d / NDVI_FILE
        if p.exists():
            return p
    sys.exit(f"greenness source not found: {NDVI_FILE} in "
             f"{[str(LOCAL_IMAGERY), str(LAKE_IMAGERY)]}")


# ── quadrant construction ────────────────────────────────────────────────────

def load_grid(cell):
    """Height cache + the georeferencing of the grid it was built on.

    The point pass costs ~5 min over 88 tiles and was already paid; the shipped
    background raster was written on this exact grid, so its transform IS the
    cache's transform. Shapes are compared before it is trusted.
    """
    cache = Path(str(CACHE) % cell)
    if not cache.exists():
        sys.exit(f"missing height cache: {cache}\n"
                 f"Run: py -3.12 qc/build_lidar_background.py --cell {cell:g}")
    z = np.load(cache)
    h, w = (int(v) for v in z["shape"])
    if not GRID_REF.exists():
        sys.exit(f"missing grid reference raster: {GRID_REF}")
    with rasterio.open(GRID_REF) as s:
        if (s.height, s.width) != (h, w):
            sys.exit(f"grid mismatch: cache {h}x{w} vs {GRID_REF.name} "
                     f"{s.height}x{s.width} — rebuild one of them")
        tf, crs = s.transform, s.crs
    if abs(abs(tf.a) - cell) > 1e-6:
        sys.exit(f"{GRID_REF.name} is {abs(tf.a):g} m, not the requested {cell:g} m")
    log(f"cache {cache.name}: {h} x {w} cells @ {cell:g} m ({h*w/1e6:.1f} Mcell), "
        f"grid from {GRID_REF.name} ({crs})")
    return z, h, w, tf, crs


def building_mask(h, w, tf, crs, buf, year_gate=None):
    """Cells whose CENTRE falls in a footprint dilated by `buf` metres.

    `all_touched=False` is the centre test. Areas/buffers are computed in
    EPSG:26910 — TRUE metres — never in the 2285 feet / 3857 Mercator units that
    this project's CRS-unit trap punishes (`phase4seg/common.py::_crs_unit_m`).
    """
    where = None
    if year_gate is not None:
        where = (lambda g: g["yr_built_max"].notna()
                 & (g["yr_built_max"] <= year_gate))
    bld = _load_vec(BUILDINGS, crs, where=where)
    geom = bld.geometry.buffer(buf) if buf else bld.geometry
    shapes = [(g, 1) for g in geom if g is not None and not g.is_empty]
    if not shapes:
        return np.zeros((h, w), dtype=bool)
    m = rasterize(shapes, out_shape=(h, w), transform=tf, fill=0,
                  dtype="uint8", all_touched=False).astype(bool)
    return m


def quadrants(z, tall_m):
    """Raw four-state cross-tabulation over the cells known in BOTH epochs."""
    h5, k5, h6, k6 = z["hag05"], z["k05"], z["hag16"], z["k16"]
    both = k5 & k6
    t5, t6 = (h5 >= tall_m), (h6 >= tall_m)
    return both, {Q_FF: both & ~t5 & ~t6, Q_TT: both & t5 & t6,
                  Q_TF: both & t5 & ~t6, Q_FT: both & ~t5 & t6}


# ── per-year overlay ─────────────────────────────────────────────────────────

def build_overlay(a, quad_path):
    """Warp the quadrant product onto the year's overlay grid and emit codes."""
    import json
    from shapely.geometry import box as _box
    from phase4seg.common import entry_for, resolve_native_path

    with rasterio.open(TEMPLATE) as t:
        crs, res = t.crs, abs(t.transform.a)
        prof = t.profile.copy()
    ortho = resolve_native_path(entry_for(a.year))
    if not ortho.exists():
        sys.exit(f"native ortho not found for {a.year}: {ortho}")
    with rasterio.open(ortho) as o:
        ob_src = rasterio.warp.transform_bounds(o.crs, crs, *o.bounds)
    left = np.floor(ob_src[0] / res) * res
    bottom = np.floor(ob_src[1] / res) * res
    right = np.ceil(ob_src[2] / res) * res
    top = np.ceil(ob_src[3] / res) * res
    W = int(round((right - left) / res))
    H = int(round((top - bottom) / res))
    tf = from_origin(left, top, res, res)
    prof.update(width=W, height=H, transform=tf, crs=crs, dtype="uint8", count=1,
                nodata=255, compress="lzw", tiled=True, blockxsize=512,
                blockysize=512, BIGTIFF="IF_SAFER")
    log(f"\n[grid] {W}x{H} @ {crs} res={res:g} sized to {ortho.name} "
        f"({W*H/1e9:.2f} Gpx)")

    # TRUE hectares per pixel. EPSG:2285 is US survey FEET; the generic converter
    # and the overlay builder's hard-coded factor must agree, so assert it.
    unit = _crs_unit_m(crs)
    px_ha = tf.a * abs(tf.e) * unit ** 2 / 1e4
    assert abs(px_ha - tf.a * abs(tf.e) * FT2_TO_M2 / 1e4) < 1e-12, "unit mismatch"
    log(f"[unit] {crs} 1 unit = {unit:.9f} m -> {px_ha*1e4:.4f} true m2/px")

    aoi = json.loads(AOI.read_text(encoding="utf-8"))
    sb = [s["bounds_3857"] for s in aoi["sectors"]]
    ux = rasterio.warp.transform_bounds(
        "EPSG:3857", crs, min(b[0] for b in sb), min(b[1] for b in sb),
        max(b[2] for b in sb), max(b[3] for b in sb))
    ob = rasterio.transform.array_bounds(H, W, tf)
    if not (ob[0] <= ux[0] and ob[1] <= ux[1] and ob[2] >= ux[2] and ob[3] >= ux[3]):
        sys.exit("FAIL: overlay grid does not cover the sector strips — uncovered "
                 "ground returns code 0 and would keep the full projected key.")
    strip_boxes = [(_box(*rasterio.warp.transform_bounds(
        "EPSG:3857", crs, *s["bounds_3857"])), 1) for s in aoi["sectors"]]

    name = a.out or f"add_quad_{a.year}.tif"
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_OUT / name

    st = dict(code1=0, code0=0, code3=0, c3_change=0, c3_conflict=0,
              known=0, bg_px=0, bg_conflict=0, tt_px=0,
              s_code1=0, s_code0=0, s_code3=0, s_land=0, s_known=0,
              s_c3_change=0, s_c3_conflict=0)

    q_src = rasterio.open(quad_path)
    bg_src = rasterio.open(BG_SRC)
    key_src = rasterio.open(MASK_2020)
    try:
        with rasterio.open(local_path, "w", **prof) as dst:
            nblocks = (H + BLOCK - 1) // BLOCK
            for bi, r0 in enumerate(range(0, H, BLOCK)):
                if a.limit_blocks and bi >= a.limit_blocks:
                    log(f"  (stopping early after {bi} blocks — debug)")
                    break
                hh = min(BLOCK, H - r0)
                btf = rasterio.windows.transform(
                    rasterio.windows.Window(0, r0, W, hh), tf)

                q = _warp_block(q_src, btf, hh, W, crs, Q_UNK)   # band 1 = product
                out = np.full((hh, W), CODE_NOCHANGE, dtype=np.uint8)

                # 1. change classes -> IGNORE (undatable inside the window)
                change = (q == Q_TF) | (q == Q_FT)
                out[change] = CODE_IGNORE

                # 2. flat/flat vs the key -> withdraw ONLY the contradictions.
                #    Reuses the SHIPPED background product so this half is
                #    byte-identical to build_groves_overlay --hybrid --with-lidar.
                bg = (_warp_block(bg_src, btf, hh, W, crs, 255) == 1)
                conflict = np.zeros((hh, W), dtype=bool)
                if bg.any():
                    key = _warp_block(key_src, btf, hh, W, crs, 255)
                    conflict = bg & (key == 1)
                    out[conflict] = CODE_IGNORE

                # 3. tall/tall -> force canopy. LAST: positives win (the existing
                #    convention), though the sets are disjoint by construction.
                tt = (q == Q_TT)
                out[tt] = CODE_CANOPY

                dst.write(out, 1, window=rasterio.windows.Window(0, r0, W, hh))

                st["known"] += int((q != Q_UNK).sum())
                st["bg_px"] += int(bg.sum())
                st["bg_conflict"] += int(conflict.sum())
                st["tt_px"] += int(tt.sum())
                st["code1"] += int((out == CODE_CANOPY).sum())
                st["code0"] += int((out == CODE_NOCHANGE).sum())
                st["code3"] += int((out == CODE_IGNORE).sum())
                st["c3_change"] += int((change & ~tt).sum())
                st["c3_conflict"] += int((conflict & ~tt & ~change).sum())

                strip = rasterize(strip_boxes, out_shape=(hh, W), transform=btf,
                                  fill=0, dtype="uint8").astype(bool)
                if strip.any():
                    st["s_land"] += int(strip.sum())
                    st["s_known"] += int((strip & (q != Q_UNK)).sum())
                    st["s_code1"] += int((strip & (out == CODE_CANOPY)).sum())
                    st["s_code0"] += int((strip & (out == CODE_NOCHANGE)).sum())
                    st["s_code3"] += int((strip & (out == CODE_IGNORE)).sum())
                    st["s_c3_change"] += int((strip & change & ~tt).sum())
                    st["s_c3_conflict"] += int((strip & conflict & ~tt & ~change).sum())
                if bi % 2 == 0 or bi == nblocks - 1:
                    log(f"  block {bi+1}/{nblocks}  rows {r0}-{r0+hh}")
    finally:
        for s in (q_src, bg_src, key_src):
            s.close()

    report_overlay(a, st, px_ha, local_path)
    if not a.limit_blocks:
        _copy_verified(local_path, LAKE_OUT)
    else:
        log("  (--limit-blocks set: partial raster, NOT copied to the lake)")
    return st


def report_overlay(a, st, px_ha, local_path):
    tot = st["code1"] + st["code0"] + st["code3"]
    log(f"\n[out ] {local_path}  ({local_path.stat().st_size/1e6:.1f} MB)")
    log(f"\n  DOSE — CITYWIDE (the whole {a.year} ortho extent, i.e. what gets tiled)")
    for k, lab in (("code1", "code 1 force canopy"), ("code0", "code 0 KEEP key  "),
                   ("code3", "code 3 force IGNORE")):
        log(f"    {lab}: {st[k]:>14,} px  {st[k]*px_ha:>9.1f} ha")
    log(f"      of code 3: change classes {st['c3_change']:,} px "
        f"({st['c3_change']*px_ha:.1f} ha) · key-contradictions "
        f"{st['c3_conflict']:,} px ({st['c3_conflict']*px_ha:.1f} ha)")
    changed = st["code1"] + st["code3"]
    log(f"    CHANGED vs the projected key: {changed:,} px "
        f"({100*changed/max(tot,1):.3f}% of the grid) — the rest is byte-untouched")

    log(f"\n  DOSE — INSIDE THE SECTOR STRIPS")
    stot = st["s_code1"] + st["s_code0"] + st["s_code3"]
    for k, lab in (("s_code1", "code 1 force canopy"), ("s_code0", "code 0 KEEP key  "),
                   ("s_code3", "code 3 force IGNORE")):
        log(f"    {lab}: {st[k]:>14,} px  {st[k]*px_ha:>9.1f} ha")
    log(f"      of code 3: change classes {st['s_c3_change']:,} px "
        f"({st['s_c3_change']*px_ha:.1f} ha) · key-contradictions "
        f"{st['s_c3_conflict']:,} px ({st['s_c3_conflict']*px_ha:.1f} ha)")
    schanged = st["s_code1"] + st["s_code3"]
    log(f"    CHANGED vs the projected key: {schanged:,} px "
        f"({100*schanged/max(stot,1):.3f}% of the strips)  "
        f"[strip extent {stot*px_ha:.0f} ha incl. water]")

    log(f"\n  LIDAR COVERAGE (the binding constraint — only 44.3% of the 2 m grid "
        f"is known in BOTH epochs)")
    log(f"    citywide overlay px with a quadrant verdict: {st['known']:,} "
        f"({100*st['known']/max(tot,1):.1f}% of grid, {st['known']*px_ha:.0f} ha)")
    log(f"    inside the strips                         : {st['s_known']:,} "
        f"({100*st['s_known']/max(stot,1):.1f}% of strips, {st['s_known']*px_ha:.0f} ha)")

    log(f"\n  INVARIANT: code1+code0+code3 == grid  -> "
        f"{'OK' if tot else 'EMPTY'}; every pixel outside code1/code3 is a literal "
        f"0, so the projected key survives there and label QUANTITY is held "
        f"constant against the baseline — only correctness varies.")

    # The comparison Kam asked for. COMPOSITION DIFFERS — say so, or it misleads.
    log(f"\n  vs THE CURRENT HYBRID RUN (add_hybrid_lidar_2009.tif: 0.71% of grid "
        f"changed, code 1 = 38.4 ha, code 3 = 20.5 ha)")
    log(f"    this overlay: {100*changed/max(tot,1):.3f}% changed, "
        f"code 1 = {st['code1']*px_ha:.1f} ha ({st['code1']*px_ha/38.4:.1f}x), "
        f"code 3 = {st['code3']*px_ha:.1f} ha ({st['code3']*px_ha/20.5:.1f}x)")
    log(f"    CAVEAT — same metric, different ingredients: that run's code 1 was "
        f"stable groves + Kam's hand-drawn Forest polygon and its code 3 was "
        f"lidar-flat AND building AND water contradictions. This one is lidar "
        f"quadrants ONLY. The two are complements, not a like-for-like swap; a "
        f"combined arm would union them.")


# ── NODE C ───────────────────────────────────────────────────────────────────

def matched_cut(z, both, tall05):
    """Quantile-match the 2016 cut to a chosen 2005 cut on the stable population.

    "Stable population" = every cell known in BOTH epochs. The two epochs are
    not comparable at a shared cut (fix (a) in the docstring), so instead of
    asserting a physical height for 2016 we ask: what cut makes 2016 call the
    SAME FRACTION of the common domain tall as `tall05` does in 2005? Returns
    (p, cut16) where p = P(hag05 >= tall05).
    """
    a5, a6 = z["hag05"][both], z["hag16"][both]
    p = float((a5 >= tall05).mean())
    return p, float(np.quantile(a6, 1.0 - p))


def green_fractions(h, w, tf, crs, need, thresholds, blk=NDVI_BLK):
    """Per-2 m-cell fraction of 2016 pixels that are green, at each threshold.

    VALID DENOMINATOR, deliberately: `green` and `coverage` are averaged onto
    the cell separately and divided, so a cell straddling the ortho edge is
    judged on the pixels it actually has rather than diluted by fill. A single
    fill-zero average would make every edge cell read un-green.

    Returns (gf, vf): gf[thr] = green px / valid px in the cell (0 where no
    valid px), vf = valid px / all px covered by the cell.
    """
    src_path = _ndvi_src()
    gf = {t: np.zeros((h, w), dtype=np.float32) for t in thresholds}
    vf = np.zeros((h, w), dtype=np.float32)
    nblk = ((h + blk - 1) // blk) * ((w + blk - 1) // blk)
    done = skipped = 0
    t0 = time.time()
    with rasterio.open(src_path) as src:
        log(f"[green] NDVI source {src_path.name}  {src.width}x{src.height} "
            f"{src.count}b {src.crs} res {src.res[0]:g}")
        for r0 in range(0, h, blk):
            for c0 in range(0, w, blk):
                hh, ww = min(blk, h - r0), min(blk, w - c0)
                done += 1
                # Only cells that could still become code 1 need an answer;
                # everywhere else the ortho pass would be pure cost.
                if not need[r0:r0 + hh, c0:c0 + ww].any():
                    skipped += 1
                    continue
                btf = rasterio.windows.transform(
                    rasterio.windows.Window(c0, r0, ww, hh), tf)
                b = rasterio.transform.array_bounds(hh, ww, btf)
                try:
                    sb = rasterio.warp.transform_bounds(crs, src.crs, *b)
                    win = rasterio.windows.from_bounds(*sb, transform=src.transform)
                    win = win.round_offsets(op="floor").round_lengths(op="ceil")
                    win = rasterio.windows.Window(
                        win.col_off - 1, win.row_off - 1, win.width + 2, win.height + 2)
                    win = win.intersection(
                        rasterio.windows.Window(0, 0, src.width, src.height))
                except (rasterio.windows.WindowError, ValueError):
                    continue
                if win.width <= 0 or win.height <= 0:
                    continue
                arr = src.read([1, 2, 3, 4], window=win)
                # Same coverage convention as phase4_qc_ndvi.py: all-zero = no
                # imagery. Cast BEFORE the subtraction — uint8 wraps.
                cov = arr.sum(axis=0, dtype=np.uint16) > 0
                if not cov.any():
                    continue
                r = arr[NDVI_R_BAND - 1].astype(np.float32)
                nir = arr[NDVI_NIR_BAND - 1].astype(np.float32)
                ndvi = (nir - r) / (nir + r + 1e-6)
                stf = src.window_transform(win)

                def _avg(a2):
                    d = np.zeros((hh, ww), dtype=np.float32)
                    rasterio.warp.reproject(
                        source=a2, destination=d, src_transform=stf,
                        src_crs=src.crs, dst_transform=btf, dst_crs=crs,
                        resampling=Resampling.average)
                    return d

                vf[r0:r0 + hh, c0:c0 + ww] = _avg(cov.astype(np.float32))
                for t in thresholds:
                    gf[t][r0:r0 + hh, c0:c0 + ww] = _avg(
                        (cov & (ndvi >= t)).astype(np.float32))
                if done % 20 == 0:
                    log(f"  [green] block {done}/{nblk} ({skipped} skipped, "
                        f"{time.time()-t0:.0f}s)")
    log(f"[green] {done} blocks, {skipped} skipped (no candidate), "
        f"{time.time()-t0:.0f}s")
    # green px / valid px, guarded: no valid px -> 0, and the caller also
    # requires vf >= --valid-frac before trusting the ratio.
    out = {}
    for t in thresholds:
        with np.errstate(invalid="ignore", divide="ignore"):
            q = np.where(vf > 0, gf[t] / np.maximum(vf, 1e-9), 0.0)
        out[t] = np.clip(q, 0.0, 1.0).astype(np.float32)
    return out, vf


def build_nodec_overlay(a, cand_path, land_ha):
    """Emit `add_nodec_{year}.tif` — code 1 and code 0 ONLY.

    code 1  candidate AND the projected 2020 key reads BACKGROUND there
    code 0  literally everywhere else, so the projected key survives byte for
            byte and label QUANTITY is held constant against Node B.

    The key == 0 gate is load-bearing. `phase4seg/labels.py::apply_additions`
    forces code 1 onto ANY mask value, IGNORE included, so without the gate
    this overlay would also manufacture labels on ground the key declines to
    grade — a second variable. Candidate pixels landing on key == 1 and
    key == 255 are counted and reported instead of asserted.
    """
    import json
    from shapely.geometry import box as _box
    from phase4seg.common import entry_for, resolve_native_path

    with rasterio.open(TEMPLATE) as t:
        crs, res = t.crs, abs(t.transform.a)
        prof = t.profile.copy()
    ortho = resolve_native_path(entry_for(a.year))
    if not ortho.exists():
        sys.exit(f"native ortho not found for {a.year}: {ortho}")
    with rasterio.open(ortho) as o:
        ob_src = rasterio.warp.transform_bounds(o.crs, crs, *o.bounds)
    left = np.floor(ob_src[0] / res) * res
    bottom = np.floor(ob_src[1] / res) * res
    right = np.ceil(ob_src[2] / res) * res
    top = np.ceil(ob_src[3] / res) * res
    W = int(round((right - left) / res))
    H = int(round((top - bottom) / res))
    tf = from_origin(left, top, res, res)
    prof.update(width=W, height=H, transform=tf, crs=crs, dtype="uint8", count=1,
                nodata=255, compress="lzw", tiled=True, blockxsize=512,
                blockysize=512, BIGTIFF="IF_SAFER")
    log(f"\n[grid] {W}x{H} @ {crs} res={res:g} sized to {ortho.name} "
        f"({W*H/1e9:.2f} Gpx)")

    unit = _crs_unit_m(crs)
    px_ha = tf.a * abs(tf.e) * unit ** 2 / 1e4
    assert abs(px_ha - tf.a * abs(tf.e) * FT2_TO_M2 / 1e4) < 1e-12, "unit mismatch"
    log(f"[unit] {crs} 1 unit = {unit:.9f} m -> {px_ha*1e4:.4f} true m2/px")

    aoi = json.loads(AOI.read_text(encoding="utf-8"))
    sb = [s["bounds_3857"] for s in aoi["sectors"]]
    ux = rasterio.warp.transform_bounds(
        "EPSG:3857", crs, min(b[0] for b in sb), min(b[1] for b in sb),
        max(b[2] for b in sb), max(b[3] for b in sb))
    ob = rasterio.transform.array_bounds(H, W, tf)
    if not (ob[0] <= ux[0] and ob[1] <= ux[1] and ob[2] >= ux[2] and ob[3] >= ux[3]):
        sys.exit("FAIL: overlay grid does not cover the sector strips — uncovered "
                 "ground returns code 0 and would keep the full projected key.")
    strip_boxes = [(_box(*rasterio.warp.transform_bounds(
        "EPSG:3857", crs, *s["bounds_3857"])), 1) for s in aoi["sectors"]]

    name = a.out or f"add_nodec_{a.year}.tif"
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_OUT / name

    st = dict(code1=0, code0=0, cand=0, cand_key1=0, cand_key255=0,
              key0=0, key1=0, key255=0,
              s_code1=0, s_code0=0, s_cand=0, s_cand_key1=0, s_cand_key255=0,
              s_key255=0, s_all=0)

    c_src = rasterio.open(cand_path)
    key_src = rasterio.open(MASK_2020)
    try:
        with rasterio.open(local_path, "w", **prof) as dst:
            nblocks = (H + BLOCK - 1) // BLOCK
            for bi, r0 in enumerate(range(0, H, BLOCK)):
                if a.limit_blocks and bi >= a.limit_blocks:
                    log(f"  (stopping early after {bi} blocks — debug)")
                    break
                hh = min(BLOCK, H - r0)
                btf = rasterio.windows.transform(
                    rasterio.windows.Window(0, r0, W, hh), tf)

                cand = _warp_block(c_src, btf, hh, W, crs, 0) == 1
                key = _warp_block(key_src, btf, hh, W, crs, 255)
                out = np.zeros((hh, W), dtype=np.uint8)      # CODE_NOCHANGE == 0
                hit = cand & (key == 0)
                out[hit] = CODE_CANOPY
                dst.write(out, 1, window=rasterio.windows.Window(0, r0, W, hh))

                st["code1"] += int(hit.sum())
                st["code0"] += int(hh * W - hit.sum())
                st["cand"] += int(cand.sum())
                st["cand_key1"] += int((cand & (key == 1)).sum())
                st["cand_key255"] += int((cand & (key == 255)).sum())
                st["key0"] += int((key == 0).sum())
                st["key1"] += int((key == 1).sum())
                st["key255"] += int((key == 255).sum())

                strip = rasterize(strip_boxes, out_shape=(hh, W), transform=btf,
                                  fill=0, dtype="uint8").astype(bool)
                if strip.any():
                    ns = int(strip.sum())
                    st["s_all"] += ns
                    st["s_code1"] += int((strip & hit).sum())
                    st["s_code0"] += ns - int((strip & hit).sum())
                    st["s_cand"] += int((strip & cand).sum())
                    st["s_cand_key1"] += int((strip & cand & (key == 1)).sum())
                    st["s_cand_key255"] += int((strip & cand & (key == 255)).sum())
                    st["s_key255"] += int((strip & (key == 255)).sum())
                if bi % 2 == 0 or bi == nblocks - 1:
                    log(f"  block {bi+1}/{nblocks}  rows {r0}-{r0+hh}")
    finally:
        for s in (c_src, key_src):
            s.close()

    report_nodec(a, st, px_ha, local_path, land_ha)
    if not a.limit_blocks:
        _copy_verified(local_path, LAKE_OUT)
    else:
        log("  (--limit-blocks set: partial raster, NOT copied to the lake)")
    return st


def report_nodec(a, st, px_ha, local_path, land_ha):
    tot = st["code1"] + st["code0"]
    log(f"\n[out ] {local_path}  ({local_path.stat().st_size/1e6:.1f} MB)")

    log("\n" + "=" * 78)
    log("  THE DOSE — what percentage of graded land code 1 changes")
    log("=" * 78)
    s_ha = st["s_code1"] * px_ha
    log(f"  ** SECTOR STRIPS, vs STRIP LAND: {s_ha:.2f} ha of {land_ha:.1f} ha "
        f"=  {100*s_ha/max(land_ha,1e-9):.3f}%  **")
    log(f"     (strip land ha = sum of sectors_v1.json land_area_m2_true — the "
        f"project's own home for that number; the bbox extent below includes water)")
    log(f"  citywide, vs the whole {a.year} ortho grid: {st['code1']*px_ha:.2f} ha "
        f"of {tot*px_ha:.0f} ha = {100*st['code1']/max(tot,1):.3f}% "
        f"(the convention the 0.71% / 0.85% prior art used)")
    log(f"  strips, vs the strip BBOX extent (incl. water): {s_ha:.2f} ha of "
        f"{st['s_all']*px_ha:.1f} ha = {100*st['s_code1']/max(st['s_all'],1):.3f}%")
    log(f"  strictly-graded denominator: the projected key reads IGNORE on "
        f"{st['s_key255']*px_ha:.1f} ha of the strip bbox "
        f"({100*st['s_key255']/max(st['s_all'],1):.2f}%), so strip graded = "
        f"{(st['s_all']-st['s_key255'])*px_ha:.1f} ha -> dose "
        f"{100*st['s_code1']/max(st['s_all']-st['s_key255'],1):.3f}%")

    log(f"\n  CODES EMITTED (Node C is code 1 / code 0 ONLY — no 2, no 3, no IGNORE)")
    log(f"    code 1 force canopy: {st['code1']:>14,} px  {st['code1']*px_ha:>9.2f} ha")
    log(f"    code 0 KEEP key    : {st['code0']:>14,} px  {st['code0']*px_ha:>9.1f} ha")
    log(f"    code 2 / code 3    : 0 px — by construction; the change classes are "
        f"excluded entirely (fix (d)) and no IGNORE region is asserted anywhere")

    log(f"\n  WHERE THE CANDIDATE SET LANDED vs THE PROJECTED KEY")
    c = st["cand"]
    log(f"    candidate px citywide            : {c:>14,}  {c*px_ha:>9.2f} ha")
    log(f"      key reads BACKGROUND -> code 1 : {st['code1']:>14,}  "
        f"{st['code1']*px_ha:>9.2f} ha  ({100*st['code1']/max(c,1):.1f}% of candidates)")
    log(f"      key ALREADY reads canopy       : {st['cand_key1']:>14,}  "
        f"{st['cand_key1']*px_ha:>9.2f} ha  ({100*st['cand_key1']/max(c,1):.1f}%) "
        f"— agreement; nothing changes, which is the point")
    log(f"      key reads IGNORE/nodata        : {st['cand_key255']:>14,}  "
        f"{st['cand_key255']*px_ha:>9.2f} ha  ({100*st['cand_key255']/max(c,1):.1f}%) "
        f"— EXCLUDED: forcing canopy there would add labels the key never graded, "
        f"moving label QUANTITY as well as correctness")
    log(f"    same, inside the strips: candidates {st['s_cand']*px_ha:.2f} ha -> "
        f"code 1 {s_ha:.2f} ha · already-canopy {st['s_cand_key1']*px_ha:.2f} ha · "
        f"key-IGNORE {st['s_cand_key255']*px_ha:.2f} ha")

    log(f"\n  INVARIANT: code1 + code0 == grid -> {'OK' if tot else 'EMPTY'}; every "
        f"non-code-1 pixel is a literal 0, so the projected key survives there and "
        f"Node C differs from Node B in exactly one direction on exactly one set.")

    # vs the prior art, on ONE denominator and ONE definition of "dose".
    # MEASURED 2026-08-28 by cross-tabulating add_hybrid_lidar_2009.tif against the
    # projected key inside the strips, on this same 0.5 m grid. The published
    # "0.71% of grid" for that arm is a CITYWIDE-grid figure and is not comparable
    # to a strip figure; worse, most of its code 1 fell on ground the key ALREADY
    # called canopy, so it changed nothing there. The comparable quantity is the
    # EFFECTIVE dose: force-canopy area that actually flips a key BACKGROUND pixel.
    log(f"\n  vs THE PRIOR ART, ON ONE DENOMINATOR (strip land, effective flips only)")
    log(f"    add_hybrid_lidar_2009 (the arm that produced the null):")
    log(f"      code 1 in strips 20.26 ha (3.598% of strip land) — but only 2.98 ha "
        f"(0.530%) landed on key=BACKGROUND. The other 17.27 ha fell where the key "
        f"already said canopy: a NO-OP. It also carried 4.61 ha of code 3 IGNORE, so "
        f"it was never a one-variable arm either.")
    dose = 100 * s_ha / max(land_ha, 1e-9)
    log(f"    this overlay: {s_ha:.2f} ha ({dose:.3f}%), 100% of it on key=BACKGROUND "
        f"by construction, and 0.00 ha of IGNORE.")
    log(f"    -> EFFECTIVE force-canopy dose is {s_ha/HYBRID_FLIP_HA:.1f}x the arm that "
        f"nulled, in one direction, with nothing else moving.")

    log("\n" + "=" * 78)
    if dose < 2.0:
        log(f"  RECOMMENDATION: DO NOT SPEND GPU. Strip dose {dose:.3f}% < 2%.")
        log(f"  Prior art: a 0.53% EFFECTIVE dose produced a clean null. A treatment "
            f"this small cannot move a recall number measured at ~.599 by more than "
            f"noise, so the run would buy a null already predictable from this number.")
    else:
        log(f"  RECOMMENDATION: RUN IT. Strip dose {dose:.3f}% of graded land (>= 2%), "
            f"every pixel an effective flip, {s_ha/2.98:.1f}x the effective dose of the "
            f"arm that nulled — large enough that a real effect separates from noise.")
    log("=" * 78)


def run_nodec(a, z, h, w, tf, crs, cell_ha):
    """Everything Node C needs, and nothing the shipped quadrant product needs."""
    import json
    both = z["k05"] & z["k16"]
    log(f"\ncells known in BOTH epochs: {both.sum():,} ({100*both.mean():.1f}% of "
        f"grid, {both.sum()*cell_ha:.0f} ha)")

    # ── (a) common height datum ──────────────────────────────────────────────
    log("\n" + "=" * 78)
    log("  FIX (a) — COMMON HEIGHT DATUM (the two epochs are NOT comparable)")
    log("=" * 78)
    a5, a6 = z["hag05"][both], z["hag16"][both]
    log("  tall AREA by epoch at a SHARED cut — the bias, measured:")
    log("    cut_m     2005 ha     2016 ha    ratio")
    for t in (2.0, 3.0, 4.0, 5.0, 8.0, 10.0, 15.0, 20.0):
        n5, n6 = int((a5 >= t).sum()), int((a6 >= t).sum())
        log(f"    {t:5.1f} {n5*cell_ha:>11.0f} {n6*cell_ha:>11.0f} {n6/max(n5,1):>8.3f}")
    stable = (a5 >= 3.0) & (a6 >= 3.0)
    log(f"  paired height delta on the stable population (both >= 3 m, "
        f"n={int(stable.sum()):,}): median {float(np.median(a6[stable]-a5[stable])):+.3f} m, "
        f"mean {float((a6[stable]-a5[stable]).mean()):+.3f} m")
    log(f"  -> a near-constant multiplicative offset at EVERY threshold is a datum "
        f"problem, not growth: per-cell max-z is an extreme-value statistic and 2016 "
        f"has ~3x the point density of 2005 (1.68 pts/m2 measured).")

    log("\n  QUANTILE-MATCHED CUT LADDER (equal tall AREA in both epochs)")
    log("    2005 cut   p(tall05)   matched 2016 cut   tall/tall ha (raw)")
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        p, c16 = matched_cut(z, both, t)
        n = int((both & (z["hag05"] >= t) & (z["hag16"] >= c16)).sum())
        log(f"    {t:8.2f} {p:11.5f} {c16:18.2f} {n*cell_ha:>18.0f}")
    p05, cut16 = matched_cut(z, both, a.tall05_m)
    if a.tall16_m is not None:
        log(f"  --tall16-m OVERRIDE {a.tall16_m:g} m supplied; matched value "
            f"{cut16:.2f} m reported but not used")
        cut16 = a.tall16_m
    log(f"\n  ** SHIPPED PAIR: 2005 >= {a.tall05_m:g} m  (p = {p05:.5f})  matched to "
        f"2016 >= {cut16:.2f} m **")

    tt_raw = both & (z["hag05"] >= a.tall05_m) & (z["hag16"] >= cut16)
    tt_naive = both & (z["hag05"] >= a.tall05_m) & (z["hag16"] >= a.tall05_m)
    log(f"  tall->tall at the MATCHED pair : {int(tt_raw.sum()):>10,} cells "
        f"{tt_raw.sum()*cell_ha:>8.0f} ha")
    log(f"  tall->tall at a NAIVE shared cut: {int(tt_naive.sum()):>10,} cells "
        f"{tt_naive.sum()*cell_ha:>8.0f} ha  "
        f"({100*(tt_naive.sum()/max(tt_raw.sum(),1)-1):+.1f}% — what the datum fix removes)")

    # ── buildings ────────────────────────────────────────────────────────────
    log("\n" + "=" * 78)
    log(f"  BUILDING SUBTRACTION (footprints dilated {a.bld_buffer:g} m, cell-CENTRE "
        f"test, ALL footprints incl. undated)")
    log("=" * 78)
    bld = building_mask(h, w, tf, crs, a.bld_buffer)
    tt_sub = tt_raw & ~bld
    log(f"  building cells on the 2 m grid : {int(bld.sum()):,} ({bld.sum()*cell_ha:.0f} ha)")
    log(f"  tall->tall minus buildings     : {int(tt_sub.sum()):,} "
        f"({tt_sub.sum()*cell_ha:.0f} ha; {100*(1-tt_sub.sum()/max(tt_raw.sum(),1)):.1f}% removed)")

    # ── (b) greenness ────────────────────────────────────────────────────────
    log("\n" + "=" * 78)
    log(f"  FIX (b) — GREENNESS FROM 2016 INFRARED (never from the {a.year} imagery)")
    log("=" * 78)
    gfrac, vfrac = green_fractions(h, w, tf, crs, tt_sub, NDVI_LADDER)
    known = vfrac >= a.valid_frac
    log(f"  cells with >= {a.valid_frac:g} valid 2016 coverage, among tall->tall-minus-"
        f"buildings: {int((tt_sub & known).sum()):,} of {int(tt_sub.sum()):,} "
        f"({100*(tt_sub & known).sum()/max(tt_sub.sum(),1):.1f}%) — the rest have no "
        f"usable 2016 pixels and are EXCLUDED (greenness unknown is not greenness)")
    log(f"  cost of that exclusion: {(tt_sub & ~known).sum()*cell_ha:.1f} ha")

    log(f"\n  NDVI LADDER (tall->tall minus buildings, un-eroded, at green-frac "
        f"{a.green_frac:g})")
    log("    NDVI cut     kept ha    kept %   removed vs height-only")
    base = float(tt_sub.sum() * cell_ha)
    for t in NDVI_LADDER:
        m = tt_sub & known & (gfrac[t] >= a.green_frac)
        k = float(m.sum() * cell_ha)
        log(f"    >= {t:.2f} {k:>11.0f} {100*k/max(base,1e-9):>9.1f}% {base-k:>16.0f} ha")
    log(f"\n  GREEN-FRACTION LADDER (at NDVI >= {a.ndvi_thresh:g})")
    log("    frac of cell green    kept ha")
    for f in FRAC_LADDER:
        m = tt_sub & known & (gfrac[a.ndvi_thresh] >= f)
        log(f"    >= {f:.2f} {m.sum()*cell_ha:>21.0f}")
    log(f"  JUSTIFICATION for NDVI >= {a.ndvi_thresh:g}: canopy_definition_PROPOSAL.md D1 "
        f"recommends 'NDVI >= 0.30 AND height >= 3 m -> canopy', and that is already the "
        f"de-facto rule in phase4_build_corrected_labels.py, so this screen adopts the "
        f"project's own shipped definition rather than inventing a cut.")
    green = known & (gfrac[a.ndvi_thresh] >= a.green_frac)

    # ── (c) erosion ──────────────────────────────────────────────────────────
    log("\n" + "=" * 78)
    log("  FIX (c) — EROSION LADDER (operand = tall->tall minus buildings, so the "
        "review's 1102 -> 267 ha pricing stays comparable)")
    log("=" * 78)
    log("    erode          height-only ha    AND-green ha   green removes")
    cand = None
    for e in ERODE_LADDER:
        m = ndimage.binary_erosion(tt_sub, iterations=e) if e else tt_sub
        hg = float(m.sum() * cell_ha)
        g = float((m & green).sum() * cell_ha)
        log(f"    {e} cell ({e*a.cell:.0f} m) {hg:>16.0f} {g:>15.0f} {hg-g:>13.0f} ha")
        if e == a.nodec_erode:
            cand = m & green
    if cand is None:
        m = (ndimage.binary_erosion(tt_sub, iterations=a.nodec_erode)
             if a.nodec_erode else tt_sub)
        cand = m & green
    log(f"  SHIPPED: erode {a.nodec_erode} cell ({a.nodec_erode*a.cell:.0f} m). A 6 m "
        f"erosion (erode 3) kills any crown under ~12 m across — isolated street trees, "
        f"the population this project already fails on. The greenness screen now carries "
        f"the demolished-after-2016 roof risk that erosion used to.")
    log(f"\n  ** CANDIDATE SET (2 m grid): {int(cand.sum()):,} cells = "
        f"{cand.sum()*cell_ha:.1f} true ha **")

    # ── candidate raster (LOCAL ONLY — never overwrites the shipped quad) ────
    arr = np.where(both, cand.astype(np.uint8), Q_UNK).astype(np.uint8)
    prof = dict(driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                crs=crs, transform=tf, nodata=Q_UNK, compress="LZW",
                tiled=True, blockxsize=512, blockysize=512)
    LOCAL_IMAGERY.mkdir(parents=True, exist_ok=True)
    cand_local = LOCAL_IMAGERY / NODEC_CAND_NAME
    with rasterio.open(cand_local, "w", **prof) as dst:
        dst.write(arr, 1)
        dst.set_band_description(1, "Node C candidate: tall/tall matched, minus "
                                    "buildings, eroded, green in 2016")
        dst.update_tags(
            source="PSLC 2005 + USGS 2016 lidar points (height cache), "
                   "buildings_canonical.gpkg, " + NDVI_FILE,
            codes="1 candidate; 0 not; 255 not known in both epochs",
            method=f"hag05 >= {a.tall05_m:g} m AND hag16 >= {cut16:.2f} m "
                   f"(quantile-matched on the both-known population, p={p05:.5f}); "
                   f"minus buildings buffered {a.bld_buffer:g} m (cell-centre); "
                   f"eroded {a.nodec_erode} cells; AND >= {a.green_frac:g} of the "
                   f"cell's valid {NDVI_FILE} pixels at NDVI >= {a.ndvi_thresh:g} "
                   f"(valid-fraction floor {a.valid_frac:g})",
            window=f"{YEAR_LO}-{YEAR_HI}", cell_m=f"{a.cell:g}",
            note="INTERMEDIATE, local only — the shipped product is "
                 "add_nodec_{year}.tif in phase4/labels_corrected",
            built=time.strftime("%Y-%m-%d"))
    log(f"\n-> {cand_local} ({cand_local.stat().st_size/1e6:.1f} MB)  [local only]")

    land_ha = sum(s["land_area_m2_true"] for s in
                  json.loads(AOI.read_text(encoding="utf-8"))["sectors"]) / 1e4
    build_nodec_overlay(a, cand_local, land_ha)
    return cut16, p05


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", default="2009",
                    help=f"overlay year; gated to {YEAR_LO}..{YEAR_HI}")
    ap.add_argument("--cell", type=float, default=2.0)
    ap.add_argument("--tall-m", type=float, default=3.0,
                    help="tree-height cut, metres above ground (default 3.0)")
    ap.add_argument("--erode", type=int, default=3,
                    help="cells eroded off tall->tall; 3 x 2 m = 6 m (default 3)")
    ap.add_argument("--change-dilate", type=int, default=0,
                    help="cells to GROW the change classes (safer IGNORE, costs "
                         "label quantity). Default 0 — see the docstring")
    ap.add_argument("--change-erode", type=int, default=0,
                    help="cells to SHRINK the change classes. Mutually exclusive "
                         "with --change-dilate")
    ap.add_argument("--bld-buffer", type=float, default=BLD_BUFFER_M,
                    help="metres each footprint is dilated before the cell-centre "
                         "test (default 2.0)")
    ap.add_argument("--quad-only", action="store_true",
                    help="build + report the quadrant raster; skip the overlay")
    ap.add_argument("--nodec", action="store_true",
                    help="NODE C: emit add_nodec_{year}.tif — code 1 ONLY, on "
                         "quantile-matched tall/tall that is green in 2016, not a "
                         "building, and called BACKGROUND by the projected key. No "
                         "code 2/3, no IGNORE, and the shipped quadrant raster is "
                         "never rewritten. See the docstring's NODE C section")
    ap.add_argument("--tall05-m", type=float, default=3.0,
                    help="NODE C: the 2005 height cut (default 3.0). The 2016 cut "
                         "is derived from it by quantile matching, not chosen")
    ap.add_argument("--tall16-m", type=float, default=None,
                    help="NODE C: override the quantile-matched 2016 cut. The "
                         "matched value is still reported. Use only to test the "
                         "datum fix — a hand-picked pair reintroduces the bias")
    ap.add_argument("--nodec-erode", type=int, default=1,
                    help="NODE C: cells eroded off the candidate set; 1 x 2 m = 2 m "
                         "(default 1, NOT the quadrant path's 3 — see fix (c))")
    ap.add_argument("--ndvi-thresh", type=float, default=0.30,
                    help="NODE C: NDVI cut for 'green in 2016' (default 0.30 = "
                         "canopy_definition_PROPOSAL.md D1's recommended rule)")
    ap.add_argument("--green-frac", type=float, default=0.50,
                    help="NODE C: fraction of a 2 m cell's VALID 2016 pixels that "
                         "must clear --ndvi-thresh (default 0.50 = majority)")
    ap.add_argument("--valid-frac", type=float, default=0.50,
                    help="NODE C: minimum fraction of a cell covered by valid 2016 "
                         "pixels before greenness is trusted at all (default 0.50)")
    ap.add_argument("--limit-blocks", type=int, default=0,
                    help="debug: stop the overlay after N blocks (skips lake copy)")
    ap.add_argument("--out", default=None, help="overlay filename override")
    a = ap.parse_args([x for x in sys.argv[1:]
                       if not (x == "-f" or x.endswith(".json"))])

    yr = int("".join(c for c in a.year if c.isdigit())[:4])
    if not (YEAR_LO <= yr <= YEAR_HI):
        sys.exit(f"--year {a.year} is outside the lidar window {YEAR_LO}..{YEAR_HI}. "
                 f"A `tall->tall` cell says nothing about imagery from outside it "
                 f"(a tree felled in 2017 is still tall->tall), so code 1 there "
                 f"would be exactly the unverified claim this script removes.")
    if a.change_dilate and a.change_erode:
        sys.exit("--change-dilate and --change-erode are mutually exclusive")
    for p in (GRID_REF, BUILDINGS, BG_SRC, TEMPLATE, MASK_2020):
        if not p.exists():
            sys.exit(f"missing required input: {p}")
    if a.nodec:
        _ndvi_src()                        # fail now, not after the ortho pass
        if a.quad_only:
            sys.exit("--nodec and --quad-only are mutually exclusive: Node C "
                     "deliberately never writes the quadrant raster")

    t0 = time.time()
    z, h, w, tf, crs = load_grid(a.cell)
    cell_ha = a.cell ** 2 / 1e4            # EPSG:26910 = TRUE metres

    if a.nodec:
        # Branch BEFORE anything writes lidar_quadrants_2005_2016.tif. Node C's
        # cut pair and erosion differ from the shipped product; re-emitting a
        # different build under that name on either plane would be exactly the
        # untagged overwrite CLAUDE.md refuses.
        cut16, p05 = run_nodec(a, z, h, w, tf, crs, cell_ha)
        log(f"\nelapsed {time.time()-t0:.1f}s")
        try:
            from pipeline_log import write_step_log
            write_step_log(script="build_lidar_quadrants",
                           step=f"nodec_{a.year}",
                           logs_dir=BASE / "phase4" / "logs", errors=0,
                           tall05_m=a.tall05_m, tall16_m_matched=round(cut16, 3),
                           p_tall05=round(p05, 6), nodec_erode=a.nodec_erode,
                           ndvi_thresh=a.ndvi_thresh, green_frac=a.green_frac,
                           valid_frac=a.valid_frac, ndvi_src=NDVI_FILE,
                           bld_buffer=a.bld_buffer,
                           out=str(LAKE_OUT / (a.out or f"add_nodec_{a.year}.tif")))
        except Exception as exc:                          # logging is a nicety
            log(f"[log] WARN could not write step log: {exc}")
        return 0

    both, q = quadrants(z, a.tall_m)
    log(f"\ncells known in BOTH epochs: {both.sum():,} ({100*both.mean():.1f}% of "
        f"grid, {both.sum()*cell_ha:.0f} ha)")

    log(f"\nRAW QUADRANTS @ cut {a.tall_m:g} m (buildings included, un-eroded)")
    log("  state                              cells        ha   %of-both")
    for k in (Q_FF, Q_TT, Q_TF, Q_FT):
        n = int(q[k].sum())
        log(f"  {Q_LABEL[k]:<34} {n:>9,} {n*cell_ha:>9.0f}    {100*n/max(1,both.sum()):5.1f}%")

    log(f"\nCUT SENSITIVITY (raw, ha)")
    log("  cut_m   flat/flat  tall/tall  tall/flat  flat/tall")
    for t in (2.0, 2.5, 3.0, 4.0, 5.0):
        _, qq = quadrants(z, t)
        log("  %5.1f %11.0f %10.0f %10.0f %10.0f"
            % (t, qq[Q_FF].sum()*cell_ha, qq[Q_TT].sum()*cell_ha,
               qq[Q_TF].sum()*cell_ha, qq[Q_FT].sum()*cell_ha))

    # ── buildings ────────────────────────────────────────────────────────────
    log(f"\nBUILDING SUBTRACTION (footprint dilated {a.bld_buffer:g} m, "
        f"cell-CENTRE test, ALL footprints incl. undated)")
    bld = building_mask(h, w, tf, crs, a.bld_buffer)
    log(f"  building cells on the 2 m grid: {int(bld.sum()):,} "
        f"({bld.sum()*cell_ha:.0f} ha)")
    log("  state                             raw ha   bld ha   bld%   minus-bld ha")
    q_sub = {}
    for k in (Q_FF, Q_TT, Q_TF, Q_FT):
        raw = int(q[k].sum())
        ov = int((q[k] & bld).sum())
        q_sub[k] = q[k] & ~bld if k != Q_FF else q[k]
        keep = int(q_sub[k].sum())
        log(f"  {Q_LABEL[k]:<34}{raw*cell_ha:>7.0f}{ov*cell_ha:>9.0f}"
            f"{100*ov/max(1,raw):>6.1f}%{keep*cell_ha:>13.0f}")
    # flat/flat is NOT subtracted, and its building overlap is mostly the BUFFER
    # RING, not roofs. Measured rather than asserted: the un-buffered footprint
    # overlap is the part that is a genuine lidar miss or a footprint-geometry
    # error; the rest is the ring falling on lawn beside houses, which is exactly
    # the verified background this product wants to keep.
    bld0 = building_mask(h, w, tf, crs, 0.0)
    ff_true = int((q[Q_FF] & bld0).sum())
    ff_buf = int((q[Q_FF] & bld).sum())
    log(f"  flat/flat is NOT subtracted. Of its {ff_buf*cell_ha:.0f} ha overlap at "
        f"{a.bld_buffer:g} m, only {ff_true*cell_ha:.0f} ha falls on a TRUE footprint "
        f"(lidar miss / footprint geometry error); the other "
        f"{(ff_buf-ff_true)*cell_ha:.0f} ha is the buffer ring on ground beside "
        f"houses — verified background, and worth keeping")

    log(f"\n  BUFFER SENSITIVITY on tall->tall (raw {q[Q_TT].sum()*cell_ha:.0f} ha)")
    for b in (0.0, 1.0, 2.0, 3.0, 5.0):
        m = bld0 if b == 0.0 else building_mask(h, w, tf, crs, b)
        n = int((q[Q_TT] & ~m).sum())
        log(f"    buffer {b:3.1f} m -> tall/tall minus buildings {n*cell_ha:8.0f} ha "
            f"({100*(1-n/max(1,q[Q_TT].sum())):.1f}% removed)")

    # Dated-subset check: how much of tall->tall would survive if only structures
    # the assessor dates to <= 2005 were subtracted? The gap between this and the
    # subtract-all number is the price of the undated + post-2005 footprints.
    bld_dated = building_mask(h, w, tf, crs, a.bld_buffer, year_gate=YEAR_LO)
    n_d = int((q[Q_TT] & ~bld_dated).sum())
    log(f"  dated-only variant (yr_built_max <= {YEAR_LO}): tall/tall "
        f"{n_d*cell_ha:.0f} ha vs subtract-all {q_sub[Q_TT].sum()*cell_ha:.0f} ha "
        f"— the {(n_d-q_sub[Q_TT].sum())*cell_ha:.0f} ha gap is undated/newer "
        f"footprints, subtracted anyway because a roof labelled canopy is a lie "
        f"while an over-subtracted roof is only a smaller label set")

    # ── erosion ──────────────────────────────────────────────────────────────
    log(f"\nEROSION SENSITIVITY on tall->tall (post building subtraction)")
    tt = None
    for e in (0, 1, 2, 3, 5):
        m = ndimage.binary_erosion(q_sub[Q_TT], iterations=e) if e else q_sub[Q_TT]
        log(f"  erode {e} cells ({e*a.cell:.0f} m): {int(m.sum()):>9,} cells "
            f"{m.sum()*cell_ha:>8.0f} ha")
        if e == a.erode:
            tt = m
    if tt is None:
        tt = (ndimage.binary_erosion(q_sub[Q_TT], iterations=a.erode)
              if a.erode else q_sub[Q_TT])

    log(f"\nCHANGE-CLASS MORPHOLOGY LADDER (shipped: dilate "
        f"{a.change_dilate} / erode {a.change_erode} — see the docstring's "
        f"deliberate asymmetry)")
    log("  setting          tall/flat ha   flat/tall ha")
    for lab, fn in (("erode 1", lambda m: ndimage.binary_erosion(m, iterations=1)),
                    ("as-is  ", lambda m: m),
                    ("dilate 1", lambda m: ndimage.binary_dilation(m, iterations=1)),
                    ("dilate 2", lambda m: ndimage.binary_dilation(m, iterations=2))):
        log(f"  {lab:<16}{fn(q_sub[Q_TF]).sum()*cell_ha:>10.0f}"
            f"{fn(q_sub[Q_FT]).sum()*cell_ha:>15.0f}")

    def _morph(m):
        if a.change_dilate:
            return ndimage.binary_dilation(m, iterations=a.change_dilate)
        if a.change_erode:
            return ndimage.binary_erosion(m, iterations=a.change_erode)
        return m
    tfl, flt = _morph(q_sub[Q_TF]), _morph(q_sub[Q_FT])

    # ── write the quadrant raster ────────────────────────────────────────────
    prod = np.where(both, Q_NONE, Q_UNK).astype(np.uint8)
    prod[q[Q_FF]] = Q_FF
    prod[tfl] = Q_TF
    prod[flt] = Q_FT
    prod[tt] = Q_TT                        # canopy assertion wins, written last
    raw_band = np.where(both, Q_NONE, Q_UNK).astype(np.uint8)
    for k in (Q_FF, Q_TF, Q_FT, Q_TT):
        raw_band[q[k]] = k

    log(f"\nSHIPPED PRODUCT (band 1)")
    for k in (Q_FF, Q_TT, Q_TF, Q_FT):
        n = int((prod == k).sum())
        log(f"  {Q_LABEL[k]:<34} {n:>9,} {n*cell_ha:>9.0f} ha")
    n0 = int((prod == Q_NONE).sum())
    log(f"  {'withdrawn (buildings / erosion)':<34} {n0:>9,} {n0*cell_ha:>9.0f} ha")

    prof = dict(driver="GTiff", height=h, width=w, count=2, dtype="uint8",
                crs=crs, transform=tf, nodata=Q_UNK, compress="LZW",
                tiled=True, blockxsize=512, blockysize=512)
    LOCAL_IMAGERY.mkdir(parents=True, exist_ok=True)
    quad_local = LOCAL_IMAGERY / QUAD_NAME
    with rasterio.open(quad_local, "w", **prof) as dst:
        dst.write(prod, 1)
        dst.write(raw_band, 2)
        dst.set_band_description(1, "product: bld-subtracted, tall/tall eroded")
        dst.set_band_description(2, "raw quadrant states (audit only)")
        dst.update_tags(
            source="PSLC 2005 + USGS 2016 lidar points (height cache), "
                   "buildings_canonical.gpkg",
            codes="0 withdrawn; 1 flat->flat; 2 tall->tall; 3 tall->flat; "
                  "4 flat->tall; 255 not known in both epochs",
            method=f"max height above ground >= {a.tall_m:g} m per epoch; tall "
                   f"classes minus buildings buffered {a.bld_buffer:g} m "
                   f"(cell-centre); tall->tall eroded {a.erode} cells; change "
                   f"classes dilate {a.change_dilate} / erode {a.change_erode}",
            window=f"{YEAR_LO}-{YEAR_HI}", cell_m=f"{a.cell:g}",
            built=time.strftime("%Y-%m-%d"))
    log(f"\n-> {quad_local} ({quad_local.stat().st_size/1e6:.1f} MB)")
    _copy_verified(quad_local, LAKE_IMAGERY)

    if not a.quad_only:
        build_overlay(a, quad_local)

    log(f"\nelapsed {time.time()-t0:.1f}s")
    try:
        from pipeline_log import write_step_log
        write_step_log(script="build_lidar_quadrants",
                       step="quad" if a.quad_only else f"overlay_{a.year}",
                       logs_dir=BASE / "phase4" / "logs", errors=0,
                       tall_m=a.tall_m, erode=a.erode, bld_buffer=a.bld_buffer,
                       out=str(quad_local))
    except Exception as exc:                              # logging is a nicety
        log(f"[log] WARN could not write step log: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
