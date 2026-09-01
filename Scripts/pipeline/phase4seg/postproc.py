from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (_tag_sfx, entry_for, tick, tock,
                              _copy_to_drive, _local_artifact_path, _crs_unit_m)

import gc
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.windows
from shapely.geometry import mapping, shape
from tqdm import tqdm


# ══════════════════════════════════════════════════════════════════════════════
#  Step 6 — Post-processing (threshold → morphology → polygonize)
# ══════════════════════════════════════════════════════════════════════════════

def _operating_threshold(label):
    """Per-year canopy probability operating threshold for post-processing.

    Selects the column by THRESH_MODE (Fix D):
      "best_f1"         → ``best_f1_thresh`` (max-F1 point; default)
      "precision_floor" → ``prec_floor_thresh`` (lowest threshold with
                          precision ≥ PRECISION_FLOOR)
    Read from this year's OVERALL row of ``semantic_eval_report.csv``; falls back
    to CANOPY_PROB_THRESHOLD (0.5) if the report, row, or column is missing /
    NaN / out of (0,1) — e.g. when the precision floor was unreachable.

    Returns (threshold_float, source_str).

    An explicit --infer-thresh (INFER_THRESH_OVERRIDE) wins over everything: it
    returns verbatim, bypassing the eval-CSV lookup (used to lower off-year
    thresholds that suppress real canopy).

    NOTE: for coarse years tiled city-wide the threshold is now read from the
    held-out test block (Fix 3/4) and is out-of-sample; legacy 6-site / degraded
    years remain in-sample and optimistic.
    """
    if config.INFER_THRESH_OVERRIDE is not None and 0.0 < float(config.INFER_THRESH_OVERRIDE) < 1.0:
        return float(config.INFER_THRESH_OVERRIDE), f"--infer-thresh override ({float(config.INFER_THRESH_OVERRIDE):.3f})"
    col = ("prec_floor_thresh" if config.THRESH_MODE == "precision_floor"
           else "best_f1_thresh")
    # The channels arm being deployed — must match how step_evaluate keys its rows
    # (core.py::step_evaluate) so a year with MULTIPLE arms (rgb and rgb+chm) picks THIS
    # arm's threshold, not whichever row happened to be appended last.
    chan_desc = f"rgb+{config.HS_SOURCE}" if config.IN_CHANNELS >= 4 else "rgb"
    if EVAL_CSV.exists():
        try:
            df = pd.read_csv(EVAL_CSV)
            sub = df[(df["year"].astype(str) == str(label)) &
                     (df["scope"] == "OVERALL")]
            if len(sub) and "channels" in sub.columns:
                arm = sub[sub["channels"].astype(str) == chan_desc]
                if len(arm):
                    sub = arm          # exact (year, channels) arm; else fall back below
            if len(sub) and col in sub.columns:
                # Within the matched arm, the last row is the most recent eval.
                val = pd.to_numeric(sub.iloc[-1][col], errors="coerce")
                if pd.notna(val) and 0.0 < float(val) < 1.0:
                    return float(val), f"{col} ({config.THRESH_MODE}, {chan_desc}, semantic_eval_report.csv)"
        except Exception as e:
            print(f"  (could not read {col}: {e}; "
                  f"using default {CANOPY_PROB_THRESHOLD})")
    return CANOPY_PROB_THRESHOLD, f"default 0.5 ({config.THRESH_MODE} unavailable)"


def sieve_min_px(pixel_area_crs_units):
    """THE sieve arithmetic, one home (2026-09-01): minimum patch size in PIXELS from
    MIN_CANOPY_PATCH divided by pixel area in CRS UNITS. That denominator is the
    documented Class-B defect (docs/CRS_CENSUS.md): on survey-foot years "3.0 m²"
    is effectively 3.0 ft² -> 0.279 m² true; on NAIP years 3.24 m². Kam has declared
    a RE-BASELINE that will change this function; step_postproc and the geometry
    instrument (mmu_effective_m2) both call it, so the change lands everywhere or
    nowhere."""
    return int(np.ceil(MIN_CANOPY_PATCH / pixel_area_crs_units))


def threshold_and_clean(prob, thr_u8, kernel):
    """The postproc NUMERIC kernel, pure: uint8 prob chunk -> {0,1,255} mask chunk.
    Threshold at the operating cut, open+close with the morph kernel, carry nodata
    through as 255. Extracted 2026-09-01 so qc/bench.py regresses the REAL code —
    a replica in the bench would regress nothing. step_postproc is the only other
    caller; behavior identical by construction."""
    from scipy.ndimage import binary_opening, binary_closing
    nod = prob == PROB_NODATA
    m = ((~nod) & (prob >= thr_u8)).astype(np.uint8)
    m = binary_opening(m, structure=kernel).astype(np.uint8)
    m = binary_closing(m, structure=kernel).astype(np.uint8)
    m[nod] = 255                       # carry no-data through to the mask
    return m


def step_postproc(label, dry_run=False):
    print(f"\n── [{label}] Step 6: Post-processing ──")

    prob_out = MASKS_DIR / f"edmonds_canopy_prob_{label}{_tag_sfx()}.tif"
    mask_final = MASKS_DIR / f"edmonds_canopy_mask_{label}{_tag_sfx()}.tif"
    gpkg_final = MASKS_DIR / f"edmonds_canopy_mask_{label}{_tag_sfx()}.gpkg"
    # verified write path (P4.1): heavy outputs land on local NVMe first, then a
    # size+sha256-verified copy moves each to Drive (also makes the polygonize
    # read-back local instead of a multi-GB FUSE read).
    mask_out = _local_artifact_path(mask_final)
    gpkg_out = _local_artifact_path(gpkg_final)
    if not prob_out.exists():
        print(f"  ERROR: {prob_out} not found — run inference first"); return

    with rasterio.open(prob_out) as src:
        img_h, img_w = src.height, src.width
        img_crs, img_tf = src.crs, src.transform
        px, py = src.transform.a, abs(src.transform.e)
    pixel_area = px * py
    # CRS-UNIT TRAP (2026-08-27). `pixel_area` is in the raster's OWN CRS units,
    # which are NOT true m²: EPSG:2285 is US survey FEET (1 unit² = 0.0929 m², so
    # a "1 m" pixel is 10.76x too small) and EPSG:3857 is Web Mercator (inflated
    # 1/cos²(47.81°) = 2.215x at this latitude). Same family as the gsd_cm defect
    # (WORKPLAN §1.5). `pixel_area_true` below is for REPORTED AREAS only.
    #
    # DELIBERATELY NOT APPLIED to min_px: MIN_CANOPY_PATCH lives in config.py
    # (pure-move protected) and was tuned against these CRS-unit areas, so
    # converting here would silently change every postproc mask. The sieve is
    # therefore ~10.8x more permissive than "3.0 m²" reads on 2285 years and
    # ~2.2x stricter on 3857 years. Retuning that constant is a science decision.
    pixel_area_true = pixel_area * _crs_unit_m(img_crs) ** 2
    min_px = sieve_min_px(pixel_area)
    # Per-year operating threshold from step_evaluate (best-F1), not the fixed 0.5.
    thr, thr_src = _operating_threshold(label)
    thr_u8 = int(round(thr * 254))
    print(f"  threshold={thr:.3f} [{thr_src}] (u8≥{thr_u8})  "
          f"min_patch={MIN_CANOPY_PATCH}m²({min_px}px)  "
          f"morph={MORPH_KERNEL_SIZE}×{MORPH_KERNEL_SIZE}")
    if dry_run:
        print("  Dry run — not processing"); return

    tick("postproc")
    CHUNK = 4096
    kernel = np.ones((MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), dtype=bool)
    mask_profile = {"driver": "GTiff", "dtype": "uint8", "width": img_w,
                    "height": img_h, "count": 1, "crs": img_crs, "transform": img_tf,
                    "compress": "lzw", "nodata": 255, "BIGTIFF": "YES"}
    canopy_px = valid_px = 0
    with rasterio.open(prob_out) as src, rasterio.open(mask_out, "w", **mask_profile) as dst:
        for r0 in tqdm(range(0, img_h, CHUNK), desc="  Threshold"):
            r1 = min(r0 + CHUNK, img_h)
            win = rasterio.windows.Window(0, r0, img_w, r1 - r0)
            prob = src.read(1, window=win)
            m = threshold_and_clean(prob, thr_u8, kernel)
            canopy_px += int((m == 1).sum())
            valid_px  += int((~nod).sum())
            dst.write(m[np.newaxis], window=win)

    canopy_area = canopy_px * pixel_area_true       # TRUE m² (see _crs_unit_m note)
    pct = 100 * canopy_px / valid_px if valid_px else 0
    print(f"  ✓ Mask (local): {mask_out.name} ({mask_out.stat().st_size/1e6:.0f} MB)")
    print(f"  Canopy: {canopy_px:,}px = {canopy_area/1e4:.1f} ha true "
          f"({pct:.1f}% of imaged area)")

    # ── Polygonize in ROW-STRIPS (memory-safe) ──
    # A fine year's mask is multi-GB (2013 = 74496×105984 ≈ 7.9 GB) — a single
    # src.read(1) OOMs the host (silent kernel kill). Read ~400M-px strips, sieve +
    # polygonize each, and collect the geometries (lightweight vs the raster). A canopy
    # region spanning a strip edge becomes two adjacent polygons — negligible for a
    # semantic-canopy area layer. Coarse years fit in one/two strips (unchanged).
    print("  Polygonizing…"); tick("polygonize")
    import fiona
    schema = {"geometry": "Polygon",
              "properties": {"canopy_id": "str", "area_m2": "float"}}
    strip_rows = max(TILE_SIZE, min(img_h, int(400_000_000 / max(img_w, 1))))
    geom_list = []
    with rasterio.open(mask_out) as src:
        for _r0 in range(0, img_h, strip_rows):
            _win = rasterio.windows.Window(0, _r0, img_w, min(strip_rows, img_h - _r0))
            _clean = rasterio.features.sieve(
                (src.read(1, window=_win) == 1).astype(np.uint8),
                size=min_px, connectivity=POLYGON_CONNECTIVITY)
            _wtf = rasterio.windows.transform(_win, img_tf)
            geom_list.extend(shape(g) for g, _ in rasterio.features.shapes(
                _clean, mask=(_clean == 1), transform=_wtf,
                connectivity=POLYGON_CONNECTIVITY))
            del _clean
        gc.collect()
    n = 0
    # v039 speedup: the per-polygon Python loop (simplify preserve_topology=True +
    # is_valid + buffer(0), one fiona write each) dominates postproc on a full-city
    # mask (100k+ crowns). shapely 2.x runs simplify/validity/area as C ufuncs over
    # the whole array at once, and fiona.writerecords batches the write. Fallback to
    # the per-feature loop if shapely 2.x isn't available.
    try:
        import shapely as _shp
        _vec = all(hasattr(_shp, a) for a in
                   ("simplify", "make_valid", "is_valid", "get_parts",
                    "get_type_id", "area"))
    except Exception:
        _vec = False
    # layer= is EXPLICIT since 2026-08-29 (D18). The GPKG driver defaults the layer
    # name to the file's basename, and this file is written under a LOCAL STAGING
    # name before being copied to gpkg_final — so the published artifact's internal
    # layer name was silently inherited from a scratch filename. Pinning it to the
    # final stem reproduces exactly the name every existing GPKG already carries,
    # and stops the staging path from being able to change it.
    with fiona.open(gpkg_out, "w", driver="GPKG", layer=gpkg_final.stem,
                    crs=img_crs.to_wkt(), schema=schema) as dst:
        if _vec:
            print("  (vectorized shapely 2.x polygonize)")
            geoms = np.array(geom_list, dtype=object)
            if len(geoms):
                if SIMPLIFY_TOLERANCE_M > 0:
                    # preserve_topology=False = fast Douglas-Peucker; the make_valid
                    # pass below repairs the rare self-intersection it can create.
                    geoms = _shp.simplify(geoms, SIMPLIFY_TOLERANCE_M,
                                          preserve_topology=False)
                bad = ~_shp.is_valid(geoms)
                if bad.any():
                    geoms[bad] = _shp.make_valid(geoms[bad])
                parts = _shp.get_parts(geoms)                     # explode multi/coll
                parts = parts[_shp.get_type_id(parts) == 3]       # keep Polygons only
                areas = _shp.area(parts)
                keep = areas >= MIN_CANOPY_PATCH
                parts = parts[keep]; areas = areas[keep]
                dst.writerecords(
                    {"geometry": mapping(p),
                     "properties": {"canopy_id": f"CAN_{label}_{i:07d}",
                                    "area_m2": round(float(a), 2)}}
                    for i, (p, a) in enumerate(zip(parts, areas)))
                n = len(parts)
        else:
            for poly in tqdm(geom_list, desc="  Polygonize", mininterval=5.0):
                if SIMPLIFY_TOLERANCE_M > 0:
                    poly = poly.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty:
                    continue
                parts = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
                for part in parts:
                    if part.area < MIN_CANOPY_PATCH:
                        continue
                    dst.write({"geometry": mapping(part),
                               "properties": {"canopy_id": f"CAN_{label}_{n:07d}",
                                              "area_m2": round(part.area, 2)}})
                    n += 1
    tock("polygonize")
    print(f"  ✓ Canopy GeoPackage: {gpkg_out.name}  ({n:,} polygons)")

    for _local, _final in ((mask_out, mask_final), (gpkg_out, gpkg_final)):
        if _local != _final:
            _copy_to_drive(_local, _final)     # raises loudly on size/sha mismatch
            try:
                _local.unlink()
            except OSError:
                pass

    # Record a one-line area summary for the cross-year consistency step.
    _append_area_summary(label, entry_for(label), canopy_area, pct, valid_px,
                         pixel_area_true)
    tock("postproc")


def _append_area_summary(label, entry, canopy_area_m2, canopy_pct, valid_px,
                         pixel_area):
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    # P6.4: rows are keyed (year, run_tag) — two tagged runs of one year used to
    # silently overwrite each other's area row.
    row = dict(year=label, run_tag=config.RUN_TAG or "", gsd_cm=entry["gsd_cm"],
               tier=tier_for(entry), coverage=entry["coverage"],
               canopy_ha=round(canopy_area_m2 / 1e4, 2),
               canopy_pct_of_imaged=round(canopy_pct, 2),
               imaged_ha=round(valid_px * pixel_area / 1e4, 2))
    path = EVAL_DIR / "_per_year_canopy_area.csv"
    if path.exists():
        df = pd.read_csv(path)
        if "run_tag" not in df.columns:
            df["run_tag"] = ""                 # legacy rows = untagged
        df["run_tag"] = df["run_tag"].fillna("")
        df = df[~((df["year"].astype(str) == label)
                  & (df["run_tag"].astype(str) == row["run_tag"]))]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(path, index=False)


# ══════════════════════════════════════════════════════════════════════════════
#  Cross-year consistency (run once after all years)
# ══════════════════════════════════════════════════════════════════════════════

def _year_sort_key(label):
    """Sort chronologically; suffixed keys (2019n, 2021s) sit beside their year."""
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    base = int(digits) if digits else 0
    suffix = "".join(ch for ch in str(label) if ch.isalpha())
    return (base, suffix)


def step_consistency(dry_run=False):
    print("\n── Cross-year consistency check ──")
    area_path = EVAL_DIR / "_per_year_canopy_area.csv"
    if not area_path.exists():
        print(f"  No per-year area summaries yet ({area_path.name}). "
              f"Run inference+postproc first."); return
    df = pd.read_csv(area_path)
    if df.empty:
        print("  No rows."); return
    if "run_tag" in df.columns:
        # One row per year for the trend: prefer the recipe-matched citywide_rgb
        # row when a year has been postproc'd under more than one tag (P6.4).
        df["_pref"] = (df["run_tag"].astype(str) == "citywide_rgb").astype(int)
        df = (df.sort_values("_pref", ascending=False)
                .drop_duplicates(subset="year", keep="first")
                .drop(columns="_pref").reset_index(drop=True))

    # Full-coverage years only for the trend (partial-coverage 67% years aren't
    # directly comparable in absolute hectares).
    df["_full"] = df["coverage"].astype(str).str.lower().eq("full")
    df = df.sort_values(by="year", key=lambda s: s.map(_year_sort_key)).reset_index(drop=True)

    full = df[df["_full"]].reset_index(drop=True)
    # Median canopy across full-coverage years; flag years deviating > ±40%.
    flags = []
    if len(full) >= 3:
        med = float(np.median(full["canopy_ha"]))
        for _, r in full.iterrows():
            dev = (r["canopy_ha"] - med) / med if med else 0
            flag = ""
            if abs(dev) > 0.40:
                flag = "HIGH" if dev > 0 else "LOW"
            flags.append((r["year"], r["canopy_ha"], round(dev * 100, 1), flag))
        print(f"  Median full-coverage canopy: {med:.1f} ha")
        print(f"  {'Year':<8}{'Canopy ha':>11}{'Δ vs median':>13}  flag")
        print(f"  {'-'*8}{'-'*11}{'-'*13}  ----")
        for y, ha, dev, flag in flags:
            print(f"  {str(y):<8}{ha:>11.1f}{dev:>12.1f}%  {flag}")
    else:
        print("  <3 full-coverage years processed — trend check deferred.")

    if dry_run:
        return
    out = df.drop(columns=["_full"]).copy()
    if flags:
        fmap = {str(y): f for y, _, _, f in flags}
        dmap = {str(y): d for y, _, d, _ in flags}
        out["pct_dev_from_median"] = out["year"].astype(str).map(dmap)
        out["anomaly_flag"] = out["year"].astype(str).map(fmap).fillna("")
    out.to_csv(CONSISTENCY_CSV, index=False)
    print(f"  ✓ {CONSISTENCY_CSV.name}")
    print("  Note: large deviations may reflect real canopy change, seasonal/"
          "phenology differences, or model issues — confirm visually before "
          "trusting the trend (Method Pipeline 'Temporal Validity Check').")
