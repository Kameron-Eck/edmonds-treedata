r"""Build the SPARSE VERIFIED additions overlay for the stable-groves experiment.

WHAT THIS REPLACES. A per-year fine-tune normally learns from the Phase-3 2020
citywide mask projected onto that year's imagery. On an old year every canopy
claim in that key is wrong wherever a tree was planted after the year in
question, and every background claim is wrong wherever a tree was later removed.
This overlay withholds the unverified claims and asserts only what independent
evidence supports:

    code 1  force canopy   -- stable groves (crowns whose cover held across every
                              observed year) + Kam's hand-drawn Forest site
    code 0  no change      -- ONLY on verified-background ground where the 2020
                              key already reads background: the negative we can
                              stand behind (lawn/grass/pavement from the dual-
                              epoch lidar test, plus structures standing that year)
    code 3  force IGNORE   -- everything else, INCLUDING verified-background
                              ground where the 2020 key reads canopy (a later
                              planting, or a mask error -- withdraw the claim)

RULE 6 HOLDS. Nothing here asserts background that the 2020 key did not already
assert; code 3 only ever withdraws a claim to IGNORE. See
`phase4seg/labels.py::apply_additions`.

--hybrid MODE (2026-08-28) -- the successor design, and the one to use.
The sparse mode above LOST decisively: on 2009, at MATCHED PRECISION, recall fell
.699 (projected key) -> .442 (groves+buildings) / .489 (+lidar), ~26 sigma, and
both sparse arms' calibration collapsed (31% of valid px within +-0.01 of 0.5 vs
10.9% baseline; maxprob 1.000). Diagnosis: the experiment changed TWO things at
once -- it made labels more CORRECT and far FEWER -- and a model graded on only
15-21% of pixels never learns uncertainty. --hybrid isolates the two:

    code 1  force canopy   -- same verified positives as above
    code 3  force IGNORE   -- ONLY where verified background and the 2020 key
                              CONTRADICT each other (key says canopy on ground
                              proven flat/built). Withdraws just the contradicted
                              claims.
    code 0  no change      -- EVERYWHERE ELSE. The projected key survives intact,
                              so label QUANTITY is held constant against the
                              baseline and only CORRECTNESS varies.

GRID. Matches `canopy_additions_2016.tif` -- EPSG:2285 at 0.5 m -- which is the
PRODUCTION overlay convention, *not* MASK_2020's grid (EPSG:3857 at 7.5 cm; an
overlay on that grid would be a ~31 GB file). `additions_from_mask` reprojects
the overlay onto each tile, so CRS/resolution need not match the 2020 mask; what
matters is that the overlay COVERS the tiled extent, because uncovered ground
returns code 0 (no change) and would silently keep the full projected key.

WATER comes from the county hydrography layer, NOT from C-CAP -- C-CAP is
eval-only and must never enter a training label (CLAUDE.md Key Data Facts).

Usage:
    py -3.12 qc/build_groves_overlay.py --year 2009 [--hybrid] [--with-lidar]
                                        [--no-water] [--limit-blocks N]
"""
import argparse
import hashlib
import shutil
import time
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
from rasterio.enums import Resampling
from rasterio.features import rasterize
from phase4seg.names import clean_argv  # noqa: E402

BASE = Path(r"G:\My Drive\treedata")
LOCAL_OUT = Path(r"D:\edmonds-pipeline\_tmp")
TEMPLATE = BASE / "phase4" / "labels_corrected" / "canopy_additions_2016.tif"
MASK_2020 = BASE / "phase3" / "edmonds_canopy_mask_2020.tif"
GROVES = BASE / "phase4" / "qc" / "stable_crowns_v0.gpkg"
FOREST = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid\negative_sites_draw.shp")
LIDAR_BG = BASE / "Full_Image" / "Pipeline Imagery" / "verified_background_lidar_2005_2016.tif"
BUILDINGS = BASE / "buildings" / "buildings_canonical.gpkg"
WATER = BASE / "bathology" / "GDBA_HYDROGRAPHY__waterbody_snoco.shp"
AOI = Path(__file__).resolve().parent.parent / "pipeline" / "aoi" / "sectors_v1.json"

CODE_CANOPY, CODE_NOCHANGE, CODE_IGNORE = 1, 0, 3
BLOCK = 2048
LAKE_OUT = BASE / "phase4" / "labels_corrected"


def _sha256(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _copy_verified(local_path, dest_dir):
    """Copy to the lake and PROVE it landed (size + sha256 both sides).

    This step did not exist before 2026-08-28: the builder wrote only to local
    scratch, so two A100s once sat idle waiting for overlays that were never on
    the lake — the launcher's own visibility guard was what caught it. Nothing
    here is conditional on the output name.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / local_path.name
    want = local_path.stat().st_size
    for attempt in range(2):
        shutil.copyfile(local_path, dest)
        # SETTLE FIRST. The Drive mount reports size LAZILY: measured 2026-08-28,
        # the first stat straight after copyfile returned exactly 14 MiB for a
        # 15,001,242-byte file and the full size appeared ~5 s later. Judging on
        # that first read reports a truncation that never happened. Poll to
        # convergence, THEN hash — a real short write never converges.
        got = -1
        for _ in range(24):
            got = dest.stat().st_size
            if got == want:
                break
            time.sleep(5)
        if got != want:
            if attempt == 0:
                print(f"  (size still {got} != {want} after 2 min — recopying)")
                continue
            sys.exit(f"COPY FAIL (size {want} != {got}): {dest}")
        lh, dh = _sha256(local_path), _sha256(dest)
        if lh == dh:
            print(f"[lake] VERIFIED {dest}  ({got/1e6:.1f} MB, sha256 {lh[:16]})")
            return dest
        if attempt == 0:
            print(f"  (sha256 {lh[:16]} != {dh[:16]} — recopying)")
    sys.exit(f"COPY FAIL (sha256 mismatch after retry): {dest}")

# EPSG:2285 is Washington State Plane North in US SURVEY FEET, so GeoPandas
# `.area` and pixel areas come out in ft^2. Every hectare figure here converts
# explicitly. This is the same units trap that produced the gsd_cm defect
# (WORKPLAN 1.5) and, checked against it, the "22.9 ha groves / 959 ha strip"
# figures in circulation are Web-Mercator-inflated (~2.2x at this latitude) --
# see the report.
FT2_TO_M2 = 0.3048006096 ** 2          # US survey foot
def _ha_ft2(v):  return v * FT2_TO_M2 / 1e4


def _load_vec(path, target_crs, where=None, layer=None):
    import geopandas as gpd
    g = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if where is not None:
        g = g[where(g)]
    if len(g) and g.crs is not None and target_crs is not None:
        g = g.to_crs(target_crs)
    return g


def _shapes(gdf):
    return [(geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty]


def _warp_block(src, block_tf, h, w, dst_crs, nearest_fill):
    """Warp a window of `src` onto the block grid; returns array filled with
    `nearest_fill` where the source does not cover."""
    b = rasterio.transform.array_bounds(h, w, block_tf)          # l,b,r,t
    try:
        sb = rasterio.warp.transform_bounds(dst_crs, src.crs, *b)
        win = rasterio.windows.from_bounds(*sb, transform=src.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
    except (rasterio.windows.WindowError, ValueError):
        return np.full((h, w), nearest_fill, dtype=np.uint8)
    if win.width <= 0 or win.height <= 0:
        return np.full((h, w), nearest_fill, dtype=np.uint8)
    oh, ow = int(min(win.height, h * 4)), int(min(win.width, w * 4))
    oh, ow = max(1, oh), max(1, ow)
    raw = src.read(1, window=win, out_shape=(oh, ow), resampling=Resampling.nearest)
    wtf = src.window_transform(win)
    stf = wtf * wtf.scale(win.width / ow, win.height / oh)
    dst = np.full((h, w), nearest_fill, dtype=np.uint8)
    rasterio.warp.reproject(
        source=raw.astype(np.uint8), destination=dst,
        src_transform=stf, src_crs=src.crs,
        dst_transform=block_tf, dst_crs=dst_crs,
        src_nodata=nearest_fill, dst_nodata=nearest_fill,
        resampling=Resampling.nearest)
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", default="2009")
    ap.add_argument("--hybrid", action="store_true",
                    help="KEEP the projected 2020 key everywhere; assert code 1 only on "
                         "verified canopy and code 3 only where verified background and the "
                         "key CONTRADICT. Isolates label correctness from label quantity — "
                         "the sparse default lost ~26 sigma at matched precision (2026-08-28)")
    ap.add_argument("--with-lidar", action="store_true",
                    help="include the dual-epoch lidar flat mask as verified background")
    ap.add_argument("--limit-blocks", type=int, default=0, help="debug: stop after N blocks")
    ap.add_argument("--no-water", action="store_true",
                    help="drop open water from the negatives — it is verified but trivial, "
                         "and it outnumbers the HARD negatives ~200:1, diluting the signal")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(clean_argv())

    yr = int("".join(c for c in a.year if c.isdigit())[:4])
    if a.hybrid:
        arm = "lidar" if a.with_lidar else "nolidar"
        name = a.out or f"add_hybrid_{arm}_{a.year}.tif"
    else:
        arm = "lidar" if a.with_lidar else "noLidar"
        name = a.out or f"add_groves_{arm}_{a.year}.tif"
    print(f"[mode] {'HYBRID — projected key kept, only contradictions withdrawn' if a.hybrid else 'SPARSE — everything unverified ignored'}")
    LOCAL_OUT.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_OUT / name

    for p in (TEMPLATE, MASK_2020, GROVES, FOREST, BUILDINGS):
        if not p.exists():
            sys.exit(f"missing required input: {p}")
    if a.with_lidar and not LIDAR_BG.exists():
        sys.exit(f"--with-lidar but missing: {LIDAR_BG}")

    # Grid: production overlay CONVENTION (EPSG:2285 @ 0.5 m, from
    # canopy_additions_2016.tif) but sized to THIS YEAR'S ORTHO, because the
    # citywide tiling walks the whole ortho and any ground the overlay does not
    # cover comes back as code 0 = no change, silently keeping the projected key.
    # The 2016 template's own extent stops ~10 km short of the northern sectors.
    with rasterio.open(TEMPLATE) as t:
        crs, res = t.crs, abs(t.transform.a)
        prof = t.profile.copy()
    from phase4seg.common import entry_for, resolve_native_path
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
    tf = rasterio.transform.from_origin(left, top, res, res)
    prof.update(width=W, height=H, transform=tf, crs=crs)
    print(f"[grid] {W}x{H} @ {crs} res={res:g} m  sized to {ortho.name} "
          f"({W*H/1e9:.2f} Gpx)")

    # ---- coverage assertion: the overlay MUST span the tiled extent ----------
    import json
    aoi = json.loads(AOI.read_text(encoding="utf-8"))
    sb = [s["bounds_3857"] for s in aoi["sectors"]]
    ux = rasterio.warp.transform_bounds(
        "EPSG:3857", crs,
        min(b[0] for b in sb), min(b[1] for b in sb),
        max(b[2] for b in sb), max(b[3] for b in sb))
    ob = rasterio.transform.array_bounds(H, W, tf)
    inside = (ob[0] <= ux[0] and ob[1] <= ux[1] and ob[2] >= ux[2] and ob[3] >= ux[3])
    print(f"[grid] sector union (2285): {[round(v) for v in ux]}")
    print(f"[grid] overlay bounds      : {[round(v) for v in ob]}  contains_sectors={inside}")
    if not inside:
        sys.exit("FAIL: overlay grid does not cover the sector strips — uncovered ground "
                 "returns code 0 (no change) and would keep the full projected key.")

    # ---- vector inputs ------------------------------------------------------
    groves = _load_vec(GROVES, crs)
    forest_all = _load_vec(FOREST, crs)
    fcol = "site" if "site" in forest_all.columns else None
    rcol = "role" if "role" in forest_all.columns else None
    forest = forest_all[(forest_all[fcol] == "Forest")] if fcol else forest_all.iloc[0:0]
    if rcol is not None and len(forest):
        # the layer carries BOTH a Region row and a Tree row of equal area — take the Tree row
        tree = forest[forest[rcol].astype(str).str.strip().str.lower().isin(("tree", "positive"))]
        forest = tree if len(tree) else forest.iloc[[0]]
    print(f"[pos ] groves {len(groves)} ({_ha_ft2(groves.geometry.area.sum()):.1f} ha true)  "
          f"forest {len(forest)} ({_ha_ft2(forest.geometry.area.sum()):.1f} ha true)")

    bld = _load_vec(BUILDINGS, crs,
                    where=lambda g: g["yr_built_max"].notna() & (g["yr_built_max"] <= yr))
    print(f"[neg ] buildings standing by {yr}: {len(bld)} "
          f"({_ha_ft2(bld.geometry.area.sum()):.1f} ha true) "
          f"[yr_built_max <= {yr}; unknown-date rows excluded]")

    # clip water to the grid: the county layer spans all of Snohomish incl. Puget
    # Sound, so an unclipped rasterize is both meaningless to report and slow
    from shapely.geometry import box as _box
    grid_box = _box(left, bottom, right, top)
    if WATER.exists() and not a.no_water:
        wat = _load_vec(WATER, crs)
        wat = wat[wat.geometry.notna()]
        wat = wat[wat.geometry.intersects(grid_box)]
        print(f"[neg ] water polygons in grid: {len(wat)} "
              f"({_ha_ft2(wat.geometry.clip(grid_box).area.sum()):.1f} ha true) "
              f"[county hydrography — NOT C-CAP, which is eval-only]")
    else:
        wat = None
        print("[neg ] water: %s" % ("EXCLUDED by --no-water"
              if a.no_water else "NO clean source found — OMITTED (not invented)"))

    pos_shapes = _shapes(groves) + _shapes(forest)
    bld_shapes = _shapes(bld)
    wat_shapes = _shapes(wat) if wat is not None and len(wat) else []

    prof.update(dtype="uint8", count=1, nodata=255, compress="lzw",
                tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")

    # sector strips as a boolean, for the "inside the strips" half of the report
    strip_boxes = []
    for s in aoi["sectors"]:
        bb = rasterio.warp.transform_bounds("EPSG:3857", crs, *s["bounds_3857"])
        strip_boxes.append((_box(*bb), 1))

    stats = dict(code1=0, code0=0, code3=0, conflict_grove_flat=0,
                 conflict_under_pos=0,
                 bg_mask_canopy=0, bg_total=0, blocks_with_bg=0,
                 bg_water=0, bg_bld=0, bg_lidar=0,
                 s_code1=0, s_code0=0, s_code3=0, s_land=0)

    mask_src = rasterio.open(MASK_2020)
    lid_src = rasterio.open(LIDAR_BG) if a.with_lidar else None
    try:
        with rasterio.open(local_path, "w", **prof) as dst:
            nblocks = (H + BLOCK - 1) // BLOCK
            for bi, r0 in enumerate(range(0, H, BLOCK)):
                if a.limit_blocks and bi >= a.limit_blocks:
                    print(f"  (stopping early after {bi} blocks — debug)")
                    break
                h = min(BLOCK, H - r0)
                btf = rasterio.windows.transform(
                    rasterio.windows.Window(0, r0, W, h), tf)
                # HYBRID: default is "leave the projected key alone" (code 0).
                # SPARSE: default is "withhold everything" (code 3).
                out = np.full((h, W), CODE_NOCHANGE if a.hybrid else CODE_IGNORE,
                              dtype=np.uint8)

                verified_bg = np.zeros((h, W), dtype=bool)
                for shp, key in ((bld_shapes, "bg_bld"), (wat_shapes, "bg_water")):
                    if shp:
                        m = rasterize(shp, out_shape=(h, W), transform=btf, fill=0,
                                      dtype="uint8", all_touched=False).astype(bool)
                        stats[key] += int(m.sum())
                        verified_bg |= m
                if lid_src is not None:
                    m = (_warp_block(lid_src, btf, h, W, crs, 255) == 1)
                    stats["bg_lidar"] += int(m.sum())
                    verified_bg |= m

                pos = np.zeros((h, W), dtype=bool)
                if pos_shapes:
                    pos = rasterize(pos_shapes, out_shape=(h, W), transform=btf,
                                    fill=0, dtype="uint8", all_touched=False).astype(bool)

                if verified_bg.any():
                    stats["blocks_with_bg"] += 1
                    m2020 = _warp_block(mask_src, btf, h, W, crs, 255)
                    conflict = verified_bg & (m2020 == 1)   # key claims canopy on proven bg
                    stats["bg_total"] += int(verified_bg.sum())
                    stats["bg_mask_canopy"] += int(conflict.sum())
                    if a.hybrid:
                        # withdraw ONLY the contradicted claims; every other pixel
                        # keeps whatever the projected key said.
                        out[conflict] = CODE_IGNORE
                    else:
                        bg_and_bg = verified_bg & (m2020 == 0)  # key agrees: background
                        out[bg_and_bg] = CODE_NOCHANGE          # the negative we teach

                # positives win over negatives (a grove inside a "flat" cell means
                # the flat test was wrong there) — count the conflict as a quality signal
                stats["conflict_grove_flat"] += int((pos & verified_bg).sum())
                # how many withdrawn-claim pixels a positive then reclaims (hybrid
                # invariant: code3_final == bg_mask_canopy - conflict_under_pos)
                stats["conflict_under_pos"] += int((pos & (out == CODE_IGNORE)).sum())
                out[pos] = CODE_CANOPY

                dst.write(out, 1, window=rasterio.windows.Window(0, r0, W, h))
                stats["code1"] += int((out == CODE_CANOPY).sum())
                stats["code0"] += int((out == CODE_NOCHANGE).sum())
                stats["code3"] += int((out == CODE_IGNORE).sum())
                strip = rasterize(strip_boxes, out_shape=(h, W), transform=btf,
                                  fill=0, dtype="uint8").astype(bool)
                if strip.any():
                    stats["s_land"] += int(strip.sum())
                    stats["s_code1"] += int((strip & (out == CODE_CANOPY)).sum())
                    stats["s_code0"] += int((strip & (out == CODE_NOCHANGE)).sum())
                    stats["s_code3"] += int((strip & (out == CODE_IGNORE)).sum())
                if bi % 2 == 0 or bi == nblocks - 1:
                    print(f"  block {bi+1}/{nblocks}  rows {r0}-{r0+h}", flush=True)
    finally:
        mask_src.close()
        if lid_src is not None:
            lid_src.close()

    px_ha = _ha_ft2(tf.a * abs(tf.e))          # true ha per pixel (2285 = feet)
    print(f"\n[out ] {local_path}  ({local_path.stat().st_size/1e6:.1f} MB)")
    lab0 = "code 0 KEEPkey" if a.hybrid else "code 0 keep-bg"
    print(f"  CITYWIDE (whole {a.year} ortho extent — what actually gets tiled)")
    for k, lab in (("code1", "code 1 canopy "), ("code0", lab0),
                   ("code3", "code 3 IGNORE ")):
        print(f"    {lab}: {stats[k]:>13,} px  {stats[k]*px_ha:>9.1f} ha")
    graded = stats["code1"] + stats["code0"]
    tot = graded + stats["code3"]
    print(f"    graded {100*graded/max(tot,1):.2f}%  /  ignored {100*stats['code3']/max(tot,1):.2f}%"
          + ("   (hybrid: 'graded' means the projected key survives there, so this is "
             "~100% BY DESIGN — quantity held constant)" if a.hybrid else ""))
    print(f"  INSIDE SECTOR STRIPS")
    sg = stats["s_code1"] + stats["s_code0"]
    st = sg + stats["s_code3"]
    for k, lab in (("s_code1", "code 1 canopy "), ("s_code0", lab0.replace("code 0", "code 0")),
                   ("s_code3", "code 3 IGNORE ")):
        print(f"    {lab}: {stats[k]:>13,} px  {stats[k]*px_ha:>9.1f} ha")
    print(f"    graded {100*sg/max(st,1):.2f}%  /  ignored {100*stats['s_code3']/max(st,1):.2f}%"
          f"   (strip extent {st*px_ha:.0f} ha incl. water)")
    print(f"  NEGATIVE SOURCES (px, may overlap): water {stats['bg_water']:,}"
          f" · buildings {stats['bg_bld']:,} · lidar-flat {stats['bg_lidar']:,}")
    if stats["bg_total"]:
        print(f"  verified-bg px  : {stats['bg_total']:,}  of which the 2020 key calls canopy "
              f"{stats['bg_mask_canopy']:,} ({100*stats['bg_mask_canopy']/stats['bg_total']:.2f}%) "
              f"-> withdrawn to IGNORE, never asserted as background")
    print(f"  grove-vs-flat conflicts: {stats['conflict_grove_flat']:,} px "
          f"({stats['conflict_grove_flat']*px_ha:.2f} ha) — positives won")
    if a.hybrid:
        # INVARIANT: in hybrid the ONLY pixels changed from the projected key are
        # code 1 (verified canopy) and code 3 (contradicted claims). Everything
        # else must be untouched, and code 3 must be exactly the conflicts that a
        # positive did not reclaim.
        expect3 = stats["bg_mask_canopy"] - stats["conflict_under_pos"]
        ok3 = (stats["code3"] == expect3)
        changed = stats["code1"] + stats["code3"]
        print(f"  HYBRID INVARIANT: code3 {stats['code3']:,} == conflicts "
              f"{stats['bg_mask_canopy']:,} - reclaimed-by-positive "
              f"{stats['conflict_under_pos']:,} = {expect3:,}  -> {'OK' if ok3 else 'MISMATCH'}")
        if not ok3:
            sys.exit("HYBRID INVARIANT FAILED — code 3 is not exactly the contradicted set")
        print(f"  pixels CHANGED from the projected key: {changed:,} "
              f"({100*changed/max(tot,1):.3f}% of the grid) — the rest is byte-untouched, "
              f"which is the point: quantity constant, only correctness varies")
    else:
        if stats["code0"]:
            print(f"  class balance citywide canopy:background = "
                  f"1 : {stats['code0']/max(stats['code1'],1):.1f}")
        if stats["s_code0"]:
            print(f"  class balance strips   canopy:background = "
                  f"1 : {stats['s_code0']/max(stats['s_code1'],1):.1f}")

    if not a.limit_blocks:
        _copy_verified(local_path, LAKE_OUT)
    else:
        print("  (--limit-blocks set: partial raster, NOT copied to the lake)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
