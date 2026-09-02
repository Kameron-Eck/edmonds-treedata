r"""Build CONTROLLED-DAMAGE overlays for the 2009 training key — a dose-response
instrument, not a correction.

╔══════════════════════════════════════════════════════════════════════════════╗
  WHY THIS EXISTS
    Three label-correction experiments on 2009 came back uninterpretable because
    the DOSE was never under our control:
      · sparse verified labels  — lost 21-26 pp recall at matched precision, but
        changed TWO things at once (labels more correct AND far fewer;
        15-21% graded).  CHATLOG 2026-08-28.
      · hybrid (correctness only) — a ~0.7% dose; clean null.
      · lidar quadrants          — dose-capped ~0.85%, because the key and the
        lidar already agree nearly everywhere.
    Every one of those tried to FIX errors we cannot enumerate. This tool goes
    the other way: it INJECTS errors we fully specify, at a dose we choose, so
    the damage curve can be measured. If a heavy dose barely moves the metric,
    then no correction at the doses available was ever going to matter and the
    whole label-correction thread closes cheaply.

  THE MECHANISM BEING SIMULATED
    2009 trains on the Phase-3 2020 citywide mask projected back onto 2009
    imagery. Its DOMINANT error is FALSE CANOPY: every tree planted between 2009
    and 2020 stands in the key as canopy that was not there yet. So the injected
    corruption is PHANTOM CROWNS — canopy claims on ground where no tree stood.

  WHY WHOLE CROWNS, NOT RANDOM PIXELS
    Structured / spatially-clustered label noise is roughly an order of magnitude
    more damaging than i.i.d. pixel noise, and back-projection error is
    crown-shaped and clustered by construction. Random pixel flips would measure
    a different (and far more benign) failure mode. Each phantom is therefore a
    REAL crown polygon from the canonical layer, translated onto nearby
    background — which also preserves the true size and shape distribution that
    synthetic blobs would not.

  RULE 6 (CLAUDE.md) AND THE DIRECTION WE CANNOT TEST
    Emitted codes: **1 (force canopy) ONLY**; every other pixel is 0 = no change.
    That is ADD-ONLY and rule-6 legal, and it rides the existing
    `--add-canopy-mask` path (phase4seg/labels.py::additions_from_mask ->
    apply_additions), so NO ENGINE CHANGE IS NEEDED.
    ** LIMITATION, stated up front: the opposite error direction — ERASING real
    canopy, i.e. the trees that were REMOVED between 2009 and 2020 and that the
    key therefore misses — cannot be injected this way. It would need
    force-background, which rule 6 forbids in an overlay. So this instrument
    measures the damage curve for FALSE-CANOPY (commission) label error only;
    FALSE-BACKGROUND (omission) label error is UNTESTED. **

  "SCORED FOOTPRINT" — the interpretation used here (flag it if you disagree)
    Placement is CITYWIDE, over the whole tiled 2009 ortho extent, because
    training is full-extent: sector strips are ~9% of tiled ground, so
    strips-only phantoms would turn a nominal 0.50 dose into ~4% of the training
    signal and we would measure dilution rather than damage. Both prior arms
    (sparse, hybrid) altered labels citywide too. A landing is REJECTED when it
    falls outside MASK_2020's coverage — off-key ground carries no projected
    label at all, so a phantom there would ADD labels where none existed, which
    is a different intervention. Dose is REPORTED both citywide and inside the
    sector strips.

  GRID
    Follows qc/build_groves_overlay.py exactly: production overlay CONVENTION
    (EPSG:2285 @ 0.5 CRS-unit = 0.1524 m, from canopy_additions_2016.tif) but
    SIZED TO THIS YEAR'S OWN ORTHO — the 2016 template's extent stops short of
    the northern sectors and sizing from it would silently leave part of the
    study area uncorrupted (uncovered ground returns code 0 = no change).

  CRS-UNIT TRAP — every area here is TRUE area
    EPSG:2285 is US survey FEET (raw areas 10.76x too large read as m2);
    EPSG:3857 is Web Mercator, inflated 2.2215x at 47.81N. The crown layer's
    stored `area_m2` and the `size_class` derived from it are Web-Mercator
    values and are NEVER used. True areas are recomputed in EPSG:26910 (UTM 10N)
    and pixel areas via phase4seg.common::_crs_unit_m.

  NESTED DOSES
    One seeded shuffle of the crown layer; the accepted phantoms of level 0.10
    are a strict PREFIX of 0.25, which is a strict prefix of 0.50. Dose is
    monotone by construction, so the three overlays differ only in dose and
    nothing else. All three are written in a single grid pass.

  USAGE
    py -3.12 qc/build_corruption_overlay.py --year 2009 --dry-run     # placement only
    py -3.12 qc/build_corruption_overlay.py --year 2009               # writes 3 overlays
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
from rasterio.enums import Resampling
from rasterio.features import rasterize
from phase4seg.names import clean_argv  # noqa: E402

BASE = Path(r"G:\My Drive\treedata")
LOCAL_OUT = Path(r"D:\edmonds-pipeline\_tmp")
LAKE_OUT = BASE / "phase4" / "labels_corrected"
TEMPLATE = BASE / "phase4" / "labels_corrected" / "canopy_additions_2016.tif"

# D: mirror FIRST, lake second — the resolution order qc/instruments/phase4_crown_touch.py::CROWNS
# and qc/instruments/mine_stable_crowns.py::CROWNS already use. The D: copies are the P1 backup and
# are sha256-manifested (MANIFEST.sha256 beside each). The chosen path is printed.
MASK_2020 = Path(r"D:\edmonds-pipeline\backup\phase3\edmonds_canopy_mask_2020.tif")
MASK_2020_FALLBACK = BASE / "phase3" / "edmonds_canopy_mask_2020.tif"
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
CROWNS_FALLBACK = BASE / "inference" / "edmonds_crowns_2020.gpkg"

# County hydrography — the SAME layer build_groves_overlay.py uses. NOT C-CAP,
# which is eval-only and must never touch a training label.
WATER = BASE / "bathology" / "GDBA_HYDROGRAPHY__waterbody_snoco.shp"
AOI = Path(__file__).resolve().parent.parent / "aoi" / "sectors_v1.json"  # parent.parent = pipeline/

CODE_CANOPY, CODE_NOCHANGE = 1, 0
BLOCK = 2048


# ── lake copy, lifted verbatim from qc/build_groves_overlay.py ────────────────

def _sha256(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _copy_verified(local_path, dest_dir):
    """Copy to the lake and PROVE it landed (size + sha256 both sides).

    The Drive mount reports size LAZILY: measured 2026-08-28, the first stat
    straight after copyfile returned exactly 14 MiB for a 15,001,242-byte file
    and the full size appeared ~5 s later. Judging on that first read reports a
    truncation that never happened. Poll to convergence, THEN hash — a real
    short write never converges.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / local_path.name
    want = local_path.stat().st_size
    for attempt in range(2):
        shutil.copyfile(local_path, dest)
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
            return dest, lh
        if attempt == 0:
            print(f"  (sha256 {lh[:16]} != {dh[:16]} — recopying)")
    sys.exit(f"COPY FAIL (sha256 mismatch after retry): {dest}")


def _warp_block(src, block_tf, h, w, dst_crs, nearest_fill):
    """Warp a window of `src` onto the block grid; returns an array filled with
    `nearest_fill` where the source does not cover. (build_groves_overlay.py)"""
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


def _pick(primary, fallback, what):
    if primary.exists():
        print(f"[src ] {what}: {primary}  (D: mirror)")
        return primary
    if fallback.exists():
        print(f"[src ] {what}: {fallback}  (lake — D: mirror absent)")
        return fallback
    sys.exit(f"missing required input ({what}): {primary} / {fallback}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", default="2009")
    ap.add_argument("--levels", default="0.10,0.25,0.50",
                    help="fractions of the crown layer duplicated as phantoms; "
                         "ascending, nested (default 0.10,0.25,0.50)")
    ap.add_argument("--seed", type=int, default=20260828,
                    help="RNG seed — shuffle order AND per-crown offsets. Printed.")
    ap.add_argument("--min-offset-m", type=float, default=10.0,
                    help="floor on displacement, TRUE metres (default 10). Justification: "
                         "10 m clears the crown itself (median true bbox extent 7.0 m, p90 "
                         "11.7 m) so a phantom lands on genuinely different ground, and it "
                         "is a typical suburban setback — the scale at which a post-2009 "
                         "planting sits relative to an existing tree.")
    ap.add_argument("--max-offset-m", type=float, default=40.0,
                    help="ceiling on displacement, TRUE metres (default 40). Justification: "
                         "40 m is about one residential lot depth, so the phantom stays in "
                         "the same parcel/streetscape context as its source crown — the "
                         "same ground a real later planting would occupy. Larger offsets "
                         "would decouple phantoms from plantable land.")
    ap.add_argument("--bg-frac", type=float, default=0.90,
                    help="a landing is accepted only if >= this fraction of its footprint "
                         "reads BACKGROUND in the 2020 key (default 0.90). We are simulating "
                         "canopy claimed on empty ground; painting over existing key canopy "
                         "is a no-op in apply_additions and is not the error under study.")
    ap.add_argument("--max-tries", type=int, default=6,
                    help="independent offset draws per crown before it is abandoned "
                         "(default 6). Needed to reach a 0.50 dose: acceptance per DRAW is "
                         "well under 1 because canopy is dense near canopy. Both per-draw "
                         "and per-crown statistics are reported.")
    ap.add_argument("--test-decim", type=int, default=8,
                    help="decimation of MASK_2020 for the landing test (default 8 -> "
                         "0.40 true m/px). The screen is a bounding-box test; the EXACT "
                         "overlap is measured at full resolution in the write pass.")
    ap.add_argument("--dry-run", action="store_true",
                    help="placement + approximate dose from the test grid only; writes "
                         "nothing. Run this first — it costs ~1 min.")
    ap.add_argument("--limit-blocks", type=int, default=0,
                    help="debug: stop after N grid blocks (partial raster, NOT copied)")
    ap.add_argument("--no-copy", action="store_true", help="skip the lake copy")
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting an existing overlay of the same name on the lake")
    a = ap.parse_args(clean_argv())

    t_start = time.time()
    levels = [float(x) for x in a.levels.split(",") if x.strip()]
    if not levels or sorted(levels) != levels or levels[0] <= 0 or levels[-1] >= 1:
        sys.exit(f"--levels must be ascending fractions in (0,1): {a.levels}")
    names = [f"add_corrupt{int(round(L*100))}_{a.year}.tif" for L in levels]

    print("=" * 78)
    print("CONTROLLED LABEL CORRUPTION — phantom crowns (FALSE-CANOPY direction only)")
    print(f"  year={a.year}  SEED={a.seed}  levels={levels}")
    print(f"  offset {a.min_offset_m:g}-{a.max_offset_m:g} true m · bg-frac >= {a.bg_frac} "
          f"· max-tries {a.max_tries} · test grid /{a.test_decim}")
    print("  emits code 1 ONLY (ADD-ONLY, rule 6). Canopy-ERASURE direction untested.")
    print("=" * 78)

    mask_path = _pick(MASK_2020, MASK_2020_FALLBACK, "2020 key mask")
    crown_path = _pick(CROWNS, CROWNS_FALLBACK, "canonical crowns")
    for p in (TEMPLATE, AOI):
        if not p.exists():
            sys.exit(f"missing required input: {p}")
    if not a.dry_run and not a.force:
        clash = [n for n in names if (LAKE_OUT / n).exists()]
        if clash:
            sys.exit(f"refusing to overwrite existing lake overlays: {clash}  (--force to allow)")

    LOCAL_OUT.mkdir(parents=True, exist_ok=True)

    # ── output grid: production CONVENTION, sized to THIS YEAR'S ortho ────────
    from phase4seg.common import entry_for, resolve_native_path, _crs_unit_m

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
    tf = rasterio.transform.from_origin(left, top, res, res)
    prof.update(width=W, height=H, transform=tf, crs=crs)
    u_out = _crs_unit_m(crs)
    px_ha = (res * u_out) ** 2 / 1e4                 # TRUE ha per output pixel
    print(f"[grid] {W}x{H} @ {crs} res={res:g} CRS-units = {res*u_out:.4f} true m "
          f"({W*H/1e9:.2f} Gpx, {W*H*px_ha:.0f} ha) sized to {ortho.name}")

    aoi = json.loads(AOI.read_text(encoding="utf-8"))
    sb = [s["bounds_3857"] for s in aoi["sectors"]]
    ux = rasterio.warp.transform_bounds(
        "EPSG:3857", crs,
        min(b[0] for b in sb), min(b[1] for b in sb),
        max(b[2] for b in sb), max(b[3] for b in sb))
    ob = rasterio.transform.array_bounds(H, W, tf)
    if not (ob[0] <= ux[0] and ob[1] <= ux[1] and ob[2] >= ux[2] and ob[3] >= ux[3]):
        sys.exit("FAIL: overlay grid does not cover the sector strips — uncovered ground "
                 "returns code 0 (no change) and would leave the key uncorrupted there.")
    print(f"[grid] contains_sectors=True  overlay {[round(v) for v in ob]}")
    aoi_land_ha = sum(s["land_area_m2_true"] for s in aoi["sectors"]) / 1e4
    aoi_all_ha = sum(s["area_m2_true"] for s in aoi["sectors"]) / 1e4
    print(f"[grid] sector strips (sectors_v1, authoritative): land {aoi_land_ha:.1f} ha "
          f"true · incl. water {aoi_all_ha:.1f} ha")

    # ── crowns: TRUE geometry facts only ─────────────────────────────────────
    import geopandas as gpd
    import shapely
    from shapely.geometry import box as _box

    t0 = time.time()
    g = gpd.read_file(crown_path, engine="pyogrio", columns=["crown_id"])
    N = len(g)
    if g.crs is None:
        sys.exit("crown layer has no CRS")
    u_cr = _crs_unit_m(g.crs)
    area_true = g.geometry.to_crs("EPSG:26910").area.to_numpy()      # TRUE m2
    bnds = g.geometry.bounds.to_numpy()                             # crown-CRS units
    ext_true = np.maximum(bnds[:, 2] - bnds[:, 0], bnds[:, 3] - bnds[:, 1]) * u_cr
    print(f"[crown] {N:,} polygons from {crown_path.name} ({g.crs}) in {time.time()-t0:.1f}s")
    print(f"[crown] TRUE area (EPSG:26910): total {area_true.sum()/1e4:.1f} ha · "
          f"median {np.median(area_true):.1f} m2 · mean {area_true.mean():.1f} · "
          f"p90 {np.quantile(area_true,0.9):.1f} m2")
    print(f"[crown] stored area_m2/size_class IGNORED — Web-Mercator, inflated "
          f"{(g.geometry.area.to_numpy()/np.maximum(area_true,1e-9)).mean():.4f}x")

    # ── landing-test grid: MASK_2020 decimated, on its OWN grid/CRS ───────────
    D = int(a.test_decim)
    t0 = time.time()
    with rasterio.open(mask_path) as ms:
        if ms.crs != g.crs:
            sys.exit(f"crown CRS {g.crs} != mask CRS {ms.crs}; the landing test assumes "
                     "they share a CRS (they do today: both EPSG:3857)")
        TH, TW = ms.height // D, ms.width // D
        key = ms.read(1, out_shape=(TH, TW), resampling=Resampling.nearest)
        ttf = ms.transform * ms.transform.scale(ms.width / TW, ms.height / TH)
        mnod = 255 if ms.nodata is None else int(ms.nodata)
        kb_out = rasterio.warp.transform_bounds(ms.crs, crs, *ms.bounds)
    tpx_m = abs(ttf.a) * u_cr
    print(f"[test ] key grid {TW}x{TH} @ {tpx_m:.3f} true m/px  ({time.time()-t0:.1f}s)")
    # The off-key rejection doubles as the off-grid rejection ONLY if the output
    # grid contains the key's footprint. When it does, behavior is UNCHANGED
    # (2009's overlays stay byte-reproducible). When it does not (2011s: the
    # ortho is 4-40 ft smaller than the key on each edge, found 2026-09-02),
    # the fix is not to refuse but to SHRINK THE LANDING ZONE: eligibility is
    # ANDed with the output-grid bounds inset by 1.2x the largest crown bbox
    # (the builder's own min-offset factor), so no accepted landing can reach
    # the grid edge — the clipping the old sys.exit guarded against is
    # impossible by construction.
    grid_inset_mask = None
    if (ob[0] <= kb_out[0] and ob[1] <= kb_out[1]
            and ob[2] >= kb_out[2] and ob[3] >= kb_out[3]):
        print(f"[test ] output grid contains the key footprint: OK")
    else:
        g26 = g.to_crs(epsg=26910)
        bx = g26.bounds
        max_ext_m = float(max((bx.maxx - bx.minx).max(), (bx.maxy - bx.miny).max()))
        inset_m = 1.2 * max_ext_m
        gb_key = rasterio.warp.transform_bounds(crs, ms.crs, *ob)
        inset_u = inset_m / u_cr                     # metres -> key CRS units
        inner = _box(gb_key[0] + inset_u, gb_key[1] + inset_u,
                     gb_key[2] - inset_u, gb_key[3] - inset_u)
        grid_inset_mask = rasterize([(inner, 1)], out_shape=(TH, TW),
                                    transform=ttf, fill=0,
                                    dtype="uint8").astype(bool)
        print(f"[test ] output grid does NOT contain the key footprint "
              f"(grid {[round(v) for v in ob]} vs key {[round(v) for v in kb_out]}) "
              f"— landing zone inset {inset_m:.1f} m true (1.2 x max crown bbox "
              f"{max_ext_m:.1f} m); off-grid landings impossible by construction")

    wat = None
    if WATER.exists():
        wg = gpd.read_file(WATER)
        if wg.crs is not None:
            wg = wg.to_crs(g.crs)
        gb = _box(*rasterio.transform.array_bounds(TH, TW, ttf))
        wg = wg[wg.geometry.notna() & wg.geometry.intersects(gb)]
        if len(wg):
            wat = rasterize([(x, 1) for x in wg.geometry], out_shape=(TH, TW),
                            transform=ttf, fill=0, dtype="uint8").astype(bool)
        print(f"[test ] water polygons in grid: {len(wg)} "
              f"({0 if wat is None else wat.sum()*(tpx_m**2)/1e4:.0f} ha true)")
    else:
        print("[test ] water: layer ABSENT — water landings NOT excluded (report it)")

    good = (key == 0)
    if wat is not None:
        good &= ~wat
    if grid_inset_mask is not None:
        good &= grid_inset_mask
    n_key_c = int((key == 1).sum())
    n_key_b = int((key == 0).sum())
    n_key_n = int((key == mnod).sum())
    print(f"[test ] key on this grid: canopy {n_key_c*(tpx_m**2)/1e4:.0f} ha · "
          f"background {n_key_b*(tpx_m**2)/1e4:.0f} ha · nodata {n_key_n:,} px")

    t0 = time.time()
    tmp = good.astype(np.int32)
    del good
    np.cumsum(tmp, axis=0, out=tmp)
    np.cumsum(tmp, axis=1, out=tmp)
    I = np.zeros((TH + 1, TW + 1), dtype=np.int32)
    I[1:, 1:] = tmp
    del tmp
    print(f"[test ] integral image {I.nbytes/1e9:.2f} GB in {time.time()-t0:.1f}s")

    # ── seeded placement ─────────────────────────────────────────────────────
    rng = np.random.default_rng(a.seed)
    order = rng.permutation(N)
    lo = np.maximum(a.min_offset_m, 1.2 * ext_true)          # clear the crown itself
    hi = np.full(N, float(a.max_offset_m))
    if np.any(lo >= hi):
        nbig = int((lo >= hi).sum())
        print(f"  ! {nbig} crowns wider than the offset window — their floor is clamped "
              f"to {a.max_offset_m:g} m (they can only be placed adjacent)")
        lo = np.minimum(lo, hi - 1e-6)
    dist = lo[:, None] + (hi - lo)[:, None] * rng.random((N, a.max_tries))
    ang = rng.random((N, a.max_tries)) * 2 * np.pi
    dx = (dist * np.cos(ang)) / u_cr                          # crown-CRS units
    dy = (dist * np.sin(ang)) / u_cr

    tx0, ty0, tpx = ttf.c, ttf.f, abs(ttf.a)                  # test-grid origin/size
    acc_try = np.full(N, -1, dtype=np.int8)                   # which try was accepted
    rej = dict(offkey=0, water=0, bg=0)
    rej_frac_sum, rej_frac_n = 0.0, 0
    tried = 0
    live = np.arange(N)
    for k in range(a.max_tries):
        if live.size == 0:
            break
        bb = bnds[live] + np.stack([dx[live, k], dy[live, k],
                                    dx[live, k], dy[live, k]], axis=1)
        tried += live.size
        c0 = np.floor((bb[:, 0] - tx0) / tpx).astype(np.int64)
        c1 = np.ceil((bb[:, 2] - tx0) / tpx).astype(np.int64)
        r0 = np.floor((ty0 - bb[:, 3]) / tpx).astype(np.int64)
        r1 = np.ceil((ty0 - bb[:, 1]) / tpx).astype(np.int64)
        c1 = np.maximum(c1, c0 + 1)
        r1 = np.maximum(r1, r0 + 1)
        on = (c0 >= 0) & (r0 >= 0) & (c1 <= TW) & (r1 <= TH)
        rej["offkey"] += int((~on).sum())
        idx = np.where(on)[0]
        # NOTE the output grid is sized to the ortho, whose extent CONTAINS the
        # 2020 key's extent (asserted at startup), so "inside the key" already
        # implies "inside the output grid" — no separate off-grid cause exists.
        cc = ((bb[idx, 0] + bb[idx, 2]) * 0.5 - tx0) / tpx
        cr = (ty0 - (bb[idx, 1] + bb[idx, 3]) * 0.5) / tpx
        cc = np.clip(cc.astype(np.int64), 0, TW - 1)
        cr = np.clip(cr.astype(np.int64), 0, TH - 1)
        if wat is not None:
            inw = wat[cr, cc]
            rej["water"] += int(inw.sum())
            idx, cr, cc = idx[~inw], cr[~inw], cc[~inw]
        gsum = (I[r1[idx], c1[idx]] - I[r0[idx], c1[idx]]
                - I[r1[idx], c0[idx]] + I[r0[idx], c0[idx]]).astype(np.float64)
        npx = ((r1[idx] - r0[idx]) * (c1[idx] - c0[idx])).astype(np.float64)
        frac = gsum / np.maximum(npx, 1)
        ok = frac >= a.bg_frac
        rej["bg"] += int((~ok).sum())
        rej_frac_sum += float(frac[~ok].sum())
        rej_frac_n += int((~ok).sum())
        acc_try[live[idx[ok]]] = k
        drop = np.zeros(live.size, dtype=bool)
        drop[idx[ok]] = True
        live = live[~drop]
        print(f"  try {k+1}/{a.max_tries}: accepted {int(ok.sum()):,}  "
              f"remaining {live.size:,}")

    placed = acc_try >= 0
    print(f"[place] draws {tried:,} · crowns placed {int(placed.sum()):,}/{N:,} "
          f"({100*placed.mean():.1f}%) · per-draw acceptance "
          f"{100*int(placed.sum())/max(tried,1):.1f}%")
    tot_rej = sum(rej.values())
    for k_, lab in (("offkey", "outside 2020-key coverage (off scored footprint)"),
                    ("water", "landed in open water (county hydrography)"),
                    ("bg", f"landing not >= {a.bg_frac:.0%} key-BACKGROUND "
                           f"(would paint over existing canopy)")):
        print(f"        reject {rej[k_]:>9,} ({100*rej[k_]/max(tried,1):5.1f}% of draws, "
              f"{100*rej[k_]/max(tot_rej,1):5.1f}% of rejections)  {lab}")
    if rej_frac_n:
        print(f"        rejected-for-background landings averaged "
              f"{rej_frac_sum/rej_frac_n:.3f} background fraction (threshold {a.bg_frac})")

    # accepted rank in shuffle order -> nested tiers
    rank = np.full(N, -1, dtype=np.int64)
    ordered_ok = order[placed[order]]
    rank[ordered_ok] = np.arange(ordered_ok.size)
    tier = np.zeros(N, dtype=np.uint8)
    targets = [int(round(L * N)) for L in levels]
    short = False
    for ti, (L, tgt) in enumerate(zip(levels, targets), start=1):
        prev = 0 if ti == 1 else targets[ti - 2]
        sel = (rank >= prev) & (rank < tgt)
        tier[sel] = ti
        got = int(((rank >= 0) & (rank < tgt)).sum())
        if got < tgt:
            short = True
        print(f"[level] {L:.2f} -> target {tgt:,} phantoms, HAVE {got:,} "
              f"({'SHORT — level not reached' if got < tgt else 'ok'})")
    if short:
        print("  ! ** LEVEL NOT REACHED ** — the shuffled layer was exhausted before the "
              "target. Raise --max-tries, relax --bg-frac, or report the achieved dose.")
    keep = tier > 0
    print(f"[level] phantoms used {int(keep.sum()):,} "
          f"(rest of the placed set is beyond the top level and is DISCARDED)")
    print(f"[size ] TRUE area m2 — source layer median {np.median(area_true):.1f}; "
          f"phantoms median {np.median(area_true[keep]):.1f}, mean {area_true[keep].mean():.1f}, "
          f"total {area_true[keep].sum()/1e4:.1f} ha (vector, before overlap merge)")

    # ── translate the accepted geometries (vectorised, once) ─────────────────
    ki = np.where(keep)[0]
    kt = acc_try[ki]
    sub = np.asarray(g.geometry.values)[ki].copy()
    nco = shapely.get_num_coordinates(sub)
    repi = np.repeat(np.arange(sub.size), nco)
    xy = shapely.get_coordinates(sub)
    xy[:, 0] += dx[ki, kt][repi]
    xy[:, 1] += dy[ki, kt][repi]
    moved = gpd.GeoSeries(shapely.set_coordinates(sub, xy), crs=g.crs)
    tiers = tier[ki]

    if a.dry_run:
        print("\n[dry-run] approximate dose from the TEST grid "
              f"({tpx_m:.2f} true m/px) — exact figures need the full write pass")
        gv, tv = moved.values, tiers
        srt = np.argsort(-tv.astype(np.int16), kind="stable")   # high tier burns first
        ph = rasterize([(gv[j], int(tv[j])) for j in srt],
                       out_shape=(TH, TW), transform=ttf, fill=0, dtype="uint8")
        strips = rasterize([(_box(*rasterio.warp.transform_bounds(
                                "EPSG:3857", g.crs, *s["bounds_3857"])), 1)
                            for s in aoi["sectors"]],
                           out_shape=(TH, TW), transform=ttf, fill=0, dtype="uint8").astype(bool)
        ha = tpx_m ** 2 / 1e4
        s_land = int((strips & ~wat).sum()) if wat is not None else int(strips.sum())
        print(f"  strip land on test grid {s_land*ha:.1f} ha "
              f"(sectors_v1 authoritative {aoi_land_ha:.1f} ha)")
        for ti, L in enumerate(levels, start=1):
            sel = (ph >= 1) & (ph <= ti)
            eff = sel & (key == 0)
            se = eff & strips
            print(f"  level {L:.2f}: painted {sel.sum()*ha:8.1f} ha · effective "
                  f"{eff.sum()*ha:8.1f} ha · in strips {se.sum()*ha:7.1f} ha = "
                  f"{100*se.sum()*ha/max(aoi_land_ha,1e-9):5.2f}% of strip LAND · "
                  f"class inflation {100*eff.sum()/max(n_key_c,1):5.1f}% of key canopy")
        print(f"\n[dry-run] nothing written. {time.time()-t_start:.0f}s")
        return 0

    # ── bin shapes by output block ───────────────────────────────────────────
    t0 = time.time()
    m2285 = moved.to_crs(crs)
    ob2 = m2285.bounds.to_numpy()
    b_top = np.floor((top - ob2[:, 3]) / res).astype(np.int64)
    b_bot = np.maximum(np.ceil((top - ob2[:, 1]) / res).astype(np.int64), b_top + 1)
    blk0 = np.clip(b_top // BLOCK, 0, (H - 1) // BLOCK)
    blk1 = np.clip((b_bot - 1) // BLOCK, 0, (H - 1) // BLOCK)
    per_block = defaultdict(list)
    geoms2285 = m2285.values
    # burn HIGH tier first so the LOWEST tier wins on overlap (level 0.10 is a
    # strict subset of 0.25 is a strict subset of 0.50 — see NESTED DOSES above)
    srt = np.argsort(-tiers.astype(np.int16), kind="stable")
    for j in srt:
        pair = (geoms2285[j], int(tiers[j]))
        for b in range(blk0[j], blk1[j] + 1):
            per_block[b].append(pair)
    print(f"[bin  ] {len(m2285):,} phantoms -> {len(per_block)} blocks "
          f"({time.time()-t0:.1f}s)")

    strip_boxes = [(_box(*rasterio.warp.transform_bounds("EPSG:3857", crs, *s["bounds_3857"])), 1)
                   for s in aoi["sectors"]]
    wat_boxes = []
    if WATER.exists():
        wg2 = gpd.read_file(WATER)
        if wg2.crs is not None:
            wg2 = wg2.to_crs(crs)
        gbox = _box(left, bottom, right, top)
        wg2 = wg2[wg2.geometry.notna() & wg2.geometry.intersects(gbox)]
        wat_boxes = [(x, 1) for x in wg2.geometry]

    prof.update(dtype="uint8", count=1, nodata=255, compress="lzw",
                tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")

    nlev = len(levels)
    st = dict(key_canopy=0, key_bg=0, s_land=0, s_land_nw=0, s_key_canopy=0,
              painted=[0] * nlev, eff=[0] * nlev, on_canopy=[0] * nlev,
              off_key=[0] * nlev, s_painted=[0] * nlev, s_eff=[0] * nlev,
              sl_eff=[0] * nlev)
    paths = [LOCAL_OUT / n for n in names]
    mask_src = rasterio.open(mask_path)
    dsts = [rasterio.open(p, "w", **prof) for p in paths]
    try:
        nblocks = (H + BLOCK - 1) // BLOCK
        for bi, r0 in enumerate(range(0, H, BLOCK)):
            if a.limit_blocks and bi >= a.limit_blocks:
                print(f"  (stopping early after {bi} blocks — debug)")
                break
            h = min(BLOCK, H - r0)
            win = rasterio.windows.Window(0, r0, W, h)
            btf = rasterio.windows.transform(win, tf)
            shp = per_block.get(bi, [])
            ph = (rasterize(shp, out_shape=(h, W), transform=btf, fill=0,
                            dtype="uint8", all_touched=False) if shp
                  else np.zeros((h, W), dtype=np.uint8))
            m2020 = _warp_block(mask_src, btf, h, W, crs, 255)
            strip = rasterize(strip_boxes, out_shape=(h, W), transform=btf,
                              fill=0, dtype="uint8").astype(bool)
            watr = (rasterize(wat_boxes, out_shape=(h, W), transform=btf, fill=0,
                              dtype="uint8").astype(bool) if wat_boxes
                    else np.zeros((h, W), dtype=bool))
            kb = (m2020 == 0)
            kc = (m2020 == 1)
            st["key_canopy"] += int(kc.sum())
            st["key_bg"] += int(kb.sum())
            st["s_land"] += int(strip.sum())
            st["s_land_nw"] += int((strip & ~watr).sum())
            st["s_key_canopy"] += int((strip & kc).sum())
            for ti in range(nlev):
                sel = (ph >= 1) & (ph <= ti + 1)
                st["painted"][ti] += int(sel.sum())
                st["eff"][ti] += int((sel & kb).sum())
                st["on_canopy"][ti] += int((sel & kc).sum())
                st["off_key"][ti] += int((sel & ~kb & ~kc).sum())
                ss = sel & strip
                st["s_painted"][ti] += int(ss.sum())
                st["s_eff"][ti] += int((ss & kb).sum())
                st["sl_eff"][ti] += int((ss & kb & ~watr).sum())
                dsts[ti].write(np.where(sel, CODE_CANOPY, CODE_NOCHANGE).astype(np.uint8),
                               1, window=win)
            if bi % 2 == 0 or bi == nblocks - 1:
                print(f"  block {bi+1}/{nblocks}  rows {r0}-{r0+h}  "
                      f"[{time.time()-t_start:.0f}s]", flush=True)
    finally:
        mask_src.close()
        for d in dsts:
            d.close()

    # ── report ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print(f"DOSE TABLE — {a.year}, seed {a.seed}.  'effective' = code-1 pixels landing on "
          f"ground the\n2020 key calls BACKGROUND; code 1 on ground already canopy is a "
          f"NO-OP in apply_additions.")
    print(f"Strip-LAND denominator {aoi_land_ha:.1f} ha (sectors_v1 land_area_m2_true; "
          f"rasterised cross-check {st['s_land_nw']*px_ha:.1f} ha).")
    print(f"Key canopy: citywide {st['key_canopy']*px_ha:.0f} ha · in strips "
          f"{st['s_key_canopy']*px_ha:.1f} ha.")
    print("-" * 78)
    hdr = ("level  phantoms   painted_ha  effect_ha  strip_eff_ha  %STRIP_LAND  "
           "%key_canopy  medsize")
    print(hdr)
    for ti, L in enumerate(levels):
        inlev = (tiers >= 1) & (tiers <= ti + 1)
        ncum = int(inlev.sum())
        med = float(np.median(area_true[ki][inlev]))
        print(f"{L:5.2f}  {ncum:9,}  {st['painted'][ti]*px_ha:10.1f}  "
              f"{st['eff'][ti]*px_ha:9.1f}  {st['sl_eff'][ti]*px_ha:12.1f}  "
              f"{100*st['sl_eff'][ti]*px_ha/max(aoi_land_ha,1e-9):10.2f}%  "
              f"{100*st['eff'][ti]/max(st['key_canopy'],1):10.1f}%  {med:6.1f}")
    print("-" * 78)
    print("COMPARATORS — the doses we already have outcomes for:")
    print("  0.70%  hybrid correction ....... measured CLEAN NULL   [figure NOT verified")
    print("  0.85%  lidar-quadrant cap ...... key/lidar agree almost  in-repo by this")
    print("                                   everywhere              script; carried from")
    print("                                                           the caller's brief]")
    print("  15-21% sparse arm ............. CHATLOG 2026-08-28. CAUTION: that is pixels")
    print("         GRADED, not an error dose. It sits on a different axis and the")
    print("         comparison is loose — the sparse arm removed labels, this adds")
    print("         wrong ones. Use it as a scale marker, never as an equal dose.")
    print("-" * 78)
    for ti, L in enumerate(levels):
        p = st["painted"][ti]
        print(f"  level {L:.2f} placement quality: painted {p:,} px · on key-canopy "
              f"{100*st['on_canopy'][ti]/max(p,1):.2f}% (wasted, no-op) · off-key "
              f"{100*st['off_key'][ti]/max(p,1):.2f}% · in strips "
              f"{100*st['s_painted'][ti]/max(p,1):.1f}%")
        print(f"       secondary denominators: {st['s_eff'][ti]*px_ha:.1f} ha effective in "
              f"the strip EXTENT = {100*st['s_eff'][ti]*px_ha/max(aoi_all_ha,1e-9):.2f}% of "
              f"{aoi_all_ha:.0f} ha incl. water (NOT the headline — WORKPLAN 1.5 flags this "
              f"denominator class); citywide {100*st['eff'][ti]/max(st['key_bg'],1):.2f}% of "
              f"key BACKGROUND land")
    print("=" * 78)

    if a.limit_blocks:
        print("  (--limit-blocks set: partial rasters, NOT copied to the lake)")
        return 0

    for ti, (L, p) in enumerate(zip(levels, paths)):
        print(f"[out ] {p}  ({p.stat().st_size/1e6:.1f} MB)")
        sha = None
        if not a.no_copy:
            _, sha = _copy_verified(p, LAKE_OUT)
        lin = {
            "source_year": a.year,
            "purpose": "CONTROLLED CORRUPTION — injected false canopy for a label-noise "
                       "dose-response test. NOT a correction. Never use as a deliverable label.",
            "codes": {"1": "force canopy (phantom crown)", "0": "no change"},
            "rule6": "ADD-ONLY; canopy-erasure direction not representable and NOT tested",
            "level": L, "seed": a.seed,
            "phantoms": int(((tiers >= 1) & (tiers <= ti + 1)).sum()),
            "offset_m": [a.min_offset_m, a.max_offset_m],
            "min_offset_rule": "max(--min-offset-m, 1.2 x true bbox extent)",
            "bg_frac": a.bg_frac, "max_tries": a.max_tries, "test_decim": D,
            "crowns": str(crown_path), "key_mask": str(mask_path),
            "water": str(WATER) if WATER.exists() else None,
            "grid": {"crs": str(crs), "res_crs_units": res, "width": W, "height": H,
                     "sized_to": str(ortho)},
            "draws": int(tried), "rejections": rej,
            "painted_ha_true": round(st["painted"][ti] * px_ha, 3),
            "effective_ha_true": round(st["eff"][ti] * px_ha, 3),
            "strip_effective_ha_true": round(st["sl_eff"][ti] * px_ha, 3),
            "pct_of_strip_land": round(100 * st["sl_eff"][ti] * px_ha / max(aoi_land_ha, 1e-9), 4),
            "strip_land_ha_true": round(aoi_land_ha, 2),
            "pct_of_key_canopy": round(100 * st["eff"][ti] / max(st["key_canopy"], 1), 4),
            "size": p.stat().st_size, "sha256": sha or _sha256(p),
            "build_date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "builder_script": "qc/build_corruption_overlay.py",
        }
        lj = p.with_suffix(".lineage.json")
        lj.write_text(json.dumps(lin, indent=2), encoding="utf-8")
        if not a.no_copy:
            shutil.copyfile(lj, LAKE_OUT / lj.name)
        print(f"[out ] lineage {lj.name}")
    print(f"\ndone in {time.time()-t_start:.0f}s   SEED {a.seed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
