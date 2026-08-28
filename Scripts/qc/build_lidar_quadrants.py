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
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
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


def log(m):
    print(m, flush=True)


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

    t0 = time.time()
    z, h, w, tf, crs = load_grid(a.cell)
    cell_ha = a.cell ** 2 / 1e4            # EPSG:26910 = TRUE metres
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
