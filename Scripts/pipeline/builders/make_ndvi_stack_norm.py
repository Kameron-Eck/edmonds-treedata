#!/usr/bin/env python3
r"""
  NORMALIZED NDVI MEGA-STACK — the radiometry-corrected companion to
  nir_stack_ndvi_1m.tif
  ---------------------------------------------------------------------------

WHY THIS EXISTS AS A SEPARATE FILE
    pipeline/make_nir_stack.py builds nir_stack_ndvi_1m.tif from NATIVE DNs.
    That product is correct and stays the default: it is what the sensors
    actually recorded, and every pipeline input, reference and headline metric
    is entitled to see native values.

    But native DNs are NOT cross-year comparable (IMAGERY_FACTS §3: over
    identical ground a naive greenness test swings 2.5x across the King series,
    and 2019 King vs 2019 NAIP differ by 0.78 on the same day). So flickering
    the native NDVI stack between years shows a mixture of vegetation change and
    camera change, and there is no way to tell which from the pixel alone.

    This script writes the OTHER product: the same grid, the same formula, with
    each acquisition's red and NIR first mapped through the R2 linear
    normalization (qc/radiometry_norm.py) onto one reference era. What changes
    between bands here is much closer to vegetation alone.

    BOTH ARE KEPT. Neither replaces the other. The native stack is the record;
    this one is the comparison tool, and it says so in its filename, in every
    band description, and in its own README.

    THIS SCRIPT DOES NOT MODIFY pipeline/make_nir_stack.py — it IMPORTS it, so
    the grid, the warp, the nodata convention, the NDVI formula and the
    band-4-is-alpha guard are literally the same code, not a copy that can drift.

WHAT IT WRITES
    nir_stack_ndvi_norm_1m.tif        int16, N bands — NORMALIZED NDVI x 1000.
    nir_stack_ndvi_norm_README.txt    band order, coefficients, warnings.

    Same grid as the native stack (EPSG:3857, 1.0-unit pixels, CHM lattice), so
    the two overlay pixel-for-pixel and can be differenced band by band.

    A SEPARATE README on purpose: make_nir_stack.py regenerates
    nir_stack_README.txt on every run and would silently clobber a note added
    there.

THE HYBRID REFERENCE — say this out loud, do not let a reader infer it
    Red is mapped onto 2020s (anchor-era EagleView 3-in); NIR is mapped onto
    2019s (2020s is RGB-only and cannot serve as a NIR reference; 2019s is the
    nearest 4-band acquisition with a healthy §12 floor). So these NDVI values
    equal NO SINGLE ACQUISITION'S native NDVI. That is fine for the purpose —
    every year is mapped onto the SAME target, which is exactly what cross-year
    comparability requires — but it means an absolute value here is not "the
    2019s NDVI of that pixel" and must not be quoted as one.

THE TWO LIFTED-FLOOR YEARS ARE CARRIED RAW, NOT CORRECTED
    2015n and 2021s have lifted NIR black points (IMAGERY_FACTS §12), traced to
    the deliveries themselves. R2 REFUSES to emit coefficients for them, and
    this script does NOT invent a workaround:

      * their NDVI is computed from BOTH bands RAW — byte-identical to the
        native stack's band for that year.
      * NOT "normalized red over raw NIR". That hybrid would be the worst of
        both: a number on neither the native scale nor the normalized one, and
        it would look corrected.
      * the band is tagged  normalized=no  and  warning='floor-lifted: relative
        use only', and the band description carries [RAW - FLOOR-LIFTED].

    Read those two bands for WHERE vegetation is, never for HOW MUCH against
    another band.

WHAT THE CORRECTION CANNOT FIX (also in qc/radiometry_norm.py's header)
    Phenology (an April frame and an August frame stay different over plants —
    normalization makes the CAMERAS comparable, never the SEASONS); per-scene
    vignetting, BRDF/hotspot and mosaic-seam gradients (one gain + one offset
    for a whole acquisition cannot touch them); saturation; the non-linearity of
    real tone curves; and the lifted floors above, which are refused.

USAGE
    py -3.12 qc/make_ndvi_stack_norm.py --step inventory
    py -3.12 qc/make_ndvi_stack_norm.py
    py -3.12 qc/make_ndvi_stack_norm.py --only 2019n,2021s --out-dir <scratch>
      --resampling / --threads / --warp-mem   as make_nir_stack.py
      --norm-table PATH   override phase4/qc/radiometry_norm.csv

Local-only (rasterio + geopandas install locally); no Colab, no GPU.
"""

from __future__ import annotations
from phase4seg.names import clean_argv  # noqa: E402

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio

_HERE = Path(__file__).resolve().parent            # …/Scripts/qc
_SCRIPTS = _HERE.parent.parent                     # …/Scripts (builders/ is one deeper)
sys.path.insert(0, str(_SCRIPTS / "qc"))           # radiometry_norm (4c home)

import make_nir_stack as mns                       # noqa: E402  IMPORTED, never edited
import radiometry_norm as rn                       # noqa: E402

try:
    from pipeline_log import write_step_log        # noqa: E402
except Exception:
    write_step_log = None

NDVI_TIF = "nir_stack_ndvi_norm_1m.tif"
README_TXT = "nir_stack_ndvi_norm_README.txt"

# The band this stack normalizes for the RED half of the ratio, and the NIR
# half. Repo-wide 4-band convention is R,G,B,NIR (band 1 = RED, band 4 = NIR) —
# reused from make_nir_stack.RED_BAND / NIR_BAND, not restated.
RED_NAME, NIR_NAME = "R", "N"


# ══════════════════════════════════════════════════════════════════════════════
#  per-acquisition normalization decision
# ══════════════════════════════════════════════════════════════════════════════

def plan_band(label, table):
    """What will happen to one acquisition: normalize both halves, or carry raw.

    Returns a dict. `mode` is "norm" or "raw"; "raw" ALWAYS means BOTH bands
    raw — there is no half-normalized path, because a normalized red over a raw
    NIR is on no scale at all.
    """
    coeffs, why = {}, []
    for band in (RED_NAME, NIR_NAME):
        try:
            g, o, row = rn.coefficients(label, band, table=table)
            coeffs[band] = (g, o, row.get("reference", "?"))
        except (KeyError, ValueError) as exc:
            why.append(f"{band}: {exc}")
    if len(coeffs) == 2:
        return dict(mode="norm", coeffs=coeffs, reason="")
    return dict(mode="raw", coeffs={}, reason=" | ".join(why))


def _norm_note(plan):
    if plan["mode"] != "norm":
        return "RAW (uncorrected)"
    r, n = plan["coeffs"][RED_NAME], plan["coeffs"][NIR_NAME]
    return (f"R x{r[0]:.4f}{r[1]:+.2f} -> {r[2]} ; "
            f"N x{n[0]:.4f}{n[1]:+.2f} -> {n[2]}")


# ══════════════════════════════════════════════════════════════════════════════
#  build
# ══════════════════════════════════════════════════════════════════════════════

def build(args):
    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    inv, problems = mns.build_inventory(only)
    if not inv:
        print("[ndvi-norm] nothing to stack — inventory is empty")
        return 1

    table = rn.load_table(Path(args.norm_table), force=True)
    for rec in inv:
        rec["plan"] = plan_band(rec["label"], table)

    transform, width, height, bounds, snapped_to, city = mns.target_grid()
    resamp = mns.RESAMPLING[args.resampling]
    n = len(inv)

    print(f"[ndvi-norm] grid   : {mns.DST_CRS} @ {mns.DST_RES} unit px  "
          f"{width} x {height}  ({width * height / 1e6:.1f} Mpx/band)")
    print(f"[ndvi-norm] bounds : {bounds[0]:.1f} {bounds[1]:.1f} {bounds[2]:.1f} "
          f"{bounds[3]:.1f}   snapped to {snapped_to}")
    print(f"[ndvi-norm] table  : {args.norm_table}")
    print(f"[ndvi-norm] bands  : {n}   resampling={args.resampling}")
    for i, rec in enumerate(inv, 1):
        tag = "NORM" if rec["plan"]["mode"] == "norm" else "RAW "
        print(f"    {i:2d}  [{tag}] {rec['label']:6s} {rec['date']:12s} "
              f"{rec['file']:26s} {_norm_note(rec['plan'])}")
        if rec["plan"]["mode"] == "raw":
            print(f"        REFUSED -> carried raw: {rec['plan']['reason'][:150]}")
    for lab, f, why in problems:
        print(f"    !!  {lab:6s} {f:26s} {why}")

    out_dir = Path(args.out_dir) if args.out_dir else mns.OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ndvi_path = out_dir / NDVI_TIF

    # interleave="BAND" is LOAD-BEARING — see the comment in make_nir_stack.build().
    common = dict(driver="GTiff", width=width, height=height, count=n,
                  crs=mns.DST_CRS, transform=transform, tiled=True,
                  blockxsize=512, blockysize=512, compress="LZW", predictor=2,
                  interleave="BAND", photometric="MINISBLACK",
                  BIGTIFF="IF_SAFER", num_threads="ALL_CPUS")

    stats, notes, t0 = [], [], time.time()
    dst = rasterio.open(ndvi_path, "w", dtype="int16",
                        nodata=mns.NDVI_NODATA, **common)
    try:
        for i, rec in enumerate(inv, 1):
            t1 = time.time()
            plan = rec["plan"]
            print(f"[ndvi-norm] ({i}/{n}) {rec['label']:6s} "
                  f"[{'NORM' if plan['mode'] == 'norm' else 'RAW'}] warping "
                  f"{rec['file']} ({rec['bytes'] / 2**30:.1f} GB) …", flush=True)

            rgbi, _src_dtype = mns.warp_rgbi(rec["path"], transform, width, height,
                                             resamp, args.threads, args.warp_mem)

            # NODATA IS DECIDED ON RAW PIXELS, BEFORE ANY OFFSET IS APPLIED.
            # The convention (phase4seg COVERAGE_NODATA) is all-bands-exactly-0;
            # a positive offset would turn those 0s into a plausible DN and
            # fabricate imagery out of the fill value.
            valid = (rgbi != 0).any(axis=0)
            red_raw = rgbi[mns.RED_BAND - 1]
            nir_raw = rgbi[mns.NIR_BAND - 1]

            # band-4-is-alpha guard — same test as make_nir_stack.build()
            nv = nir_raw[valid] if valid.any() else nir_raw.ravel()[:1]
            const_nir = bool(nv.size and nv.min() == nv.max())
            if const_nir:
                notes.append(f"{rec['label']}: band 4 is CONSTANT (= {int(nv.min())}) "
                             f"over the city grid — an alpha channel, not NIR. "
                             f"NDVI SKIPPED.")
                print(f"    !! band 4 constant ({int(nv.min())}) — NDVI skipped")
                nd = np.full((height, width), mns.NDVI_NODATA, np.int16)
                st = dict(valid_px=0, pct=0.0, min=None, max=None, mean=None,
                          std=None, p1=None, p50=None, p99=None, frac_below=None)
            else:
                if plan["mode"] == "norm":
                    # float32 THROUGHOUT — the uint8 round-and-clip is lossy and
                    # doing it before the ratio throws away the precision the
                    # correction just added. valid= keeps nodata pixels raw.
                    red = rn.normalize_array(red_raw, rec["label"], RED_NAME,
                                             table=table, valid=valid,
                                             out_dtype="float32")
                    nir = rn.normalize_array(nir_raw, rec["label"], NIR_NAME,
                                             table=table, valid=valid,
                                             out_dtype="float32")
                else:
                    red, nir = red_raw, nir_raw       # BOTH raw, never one of each
                nd = mns.ndvi_int16(red, nir, valid)
                st = mns.band_stats(nd, mns.NDVI_NODATA, -mns.NDVI_SCALE,
                                    mns.NDVI_SCALE, frac_below=mns.WATER_NDVI)
                del red, nir

            stats.append(st)
            dst.write(nd, i)
            dst.set_band_description(i, _describe(rec))
            dst.update_tags(
                i, **mns._stat_tags(st), source_file=rec["file"],
                acquired=rec["date"], native_gsd_cm=f"{rec['gsd_cm']}",
                formula="(b4-b1)/(b4+b1+1e-6) x1000, int16",
                normalized="yes" if plan["mode"] == "norm" else "no",
                normalization=_norm_note(plan),
                norm_table=str(args.norm_table),
                warning=("" if plan["mode"] == "norm" else
                         "floor-lifted: relative use only — absolute NDVI is "
                         "biased upward (IMAGERY_FACTS §12); read this band for "
                         "WHERE vegetation is, never HOW MUCH vs another band"),
                skipped="constant band 4" if const_nir else "")
            del nd, rgbi, red_raw, nir_raw

            summary = ("NO VALID PIXELS" if not st["valid_px"] else
                       f"p1/p50/p99 = {st['p1'] / mns.NDVI_SCALE:+.3f}/"
                       f"{st['p50'] / mns.NDVI_SCALE:+.3f}/"
                       f"{st['p99'] / mns.NDVI_SCALE:+.3f}  "
                       f"water-tail {100 * (st['frac_below'] or 0):.1f}%")
            print(f"    valid={st['pct']:.1f}%  {summary}   "
                  f"{time.time() - t1:.0f}s", flush=True)
    finally:
        dst.close()

    if not args.no_overviews:
        print("[ndvi-norm] building overviews …", flush=True)
        with rasterio.open(ndvi_path, "r+") as ds:
            ds.build_overviews([2, 4, 8, 16, 32], mns.Resampling.average)

    readme = out_dir / README_TXT
    write_readme(readme, inv, problems, stats, bounds, snapped_to,
                 width, height, args, time.time() - t0)
    print(f"[ndvi-norm] wrote {ndvi_path}  "
          f"({ndvi_path.stat().st_size / 2**30:.2f} GB)")
    print(f"[ndvi-norm] wrote {readme}")
    print(f"[ndvi-norm] done in {(time.time() - t0) / 60:.1f} min")

    if write_step_log:
        try:
            write_step_log(script="make_ndvi_stack_norm", step="build",
                           logs_dir=mns.LOGS_DIR,
                           info={"out": str(ndvi_path), "bands": n,
                                 "normalized": sum(1 for r in inv
                                                   if r["plan"]["mode"] == "norm"),
                                 "raw_carried": sum(1 for r in inv
                                                    if r["plan"]["mode"] == "raw")})
        except Exception as exc:
            print(f"    (step log skipped: {exc})")
    return 0


def _describe(rec):
    """ArcGIS band name. The NORM / RAW state is IN THE NAME, not only a tag —
    a reader stepping bands in Symbology sees the tag list rarely and the band
    name always."""
    base = (f"{rec['label']} {rec['date']} NDVIx1000 {rec['gsd_cm']:.0f}cm "
            f"{rec['src_short']}")
    return base + (" [NORM]" if rec["plan"]["mode"] == "norm"
                   else " [RAW - FLOOR-LIFTED]")


# ══════════════════════════════════════════════════════════════════════════════
#  README
# ══════════════════════════════════════════════════════════════════════════════

def write_readme(path, inv, problems, stats, bounds, snapped_to, width, height,
                 args, elapsed):
    A = []
    a = A.append
    a("=" * 78)
    a("  nir_stack_ndvi_norm_1m.tif — RADIOMETRY-NORMALIZED NDVI MEGA-STACK")
    a("=" * 78)
    a(f"  built  : {datetime.now():%Y-%m-%d %H:%M}  in {elapsed / 60:.1f} min")
    a(f"  by     : Scripts/qc/make_ndvi_stack_norm.py")
    a(f"  table  : {args.norm_table}   (fitted by Scripts/qc/radiometry_norm.py)")
    a(f"  grid   : {mns.DST_CRS} @ {mns.DST_RES} unit px, {width} x {height}, "
      f"snapped to {snapped_to}")
    a(f"  bounds : {bounds[0]:.1f} {bounds[1]:.1f} {bounds[2]:.1f} {bounds[3]:.1f}")
    a(f"  dtype  : int16, NDVI x {mns.NDVI_SCALE}, nodata {mns.NDVI_NODATA}")
    a(f"  warp   : {args.resampling}")
    a("")
    a("  WHAT THIS IS")
    a("  ------------------------------------------------------------------")
    a("  The radiometry-corrected COMPANION to nir_stack_ndvi_1m.tif, on the")
    a("  identical grid. Before the NDVI ratio is taken, each acquisition's RED")
    a("  and NIR bands are mapped through a per-acquisition per-band linear")
    a("  correction (gain, offset) fitted over PSEUDO-INVARIANT HARDSCAPE — an")
    a("  asphalt retail lot and the Edmonds Heights K-12 campus, PIF-masked to")
    a("  non-vegetated pixels from the fixed 2020 anchor.")
    a("")
    a("  The native stack stays the record. This one is the COMPARISON tool:")
    a("  what changes between bands here is much closer to vegetation alone.")
    a("")
    a("  THE REFERENCE IS HYBRID — read this before quoting an absolute value")
    a("  ------------------------------------------------------------------")
    a("  RED is mapped onto 2020s (anchor-era EagleView 3-in). NIR is mapped")
    a("  onto 2019s — 2020s is RGB-ONLY and cannot serve as a NIR reference, and")
    a("  2019s is the nearest 4-band acquisition with a healthy dark-target")
    a("  floor. So these values equal NO SINGLE ACQUISITION'S native NDVI.")
    a("  Every year is mapped onto the SAME target, which is what cross-year")
    a("  comparison needs — but an absolute number here is not 'the 2019s NDVI")
    a("  of that pixel' and must not be reported as one.")
    a("")
    a("  BANDS")
    a("  ------------------------------------------------------------------")
    a(f"  {'#':>2s}  {'year':6s} {'date':12s} {'state':6s} "
      f"{'p1':>7s} {'p50':>7s} {'p99':>7s}  correction")
    for i, (rec, st) in enumerate(zip(inv, stats), 1):
        state = "NORM" if rec["plan"]["mode"] == "norm" else "RAW"
        q = (f"{st['p1'] / mns.NDVI_SCALE:+7.3f} {st['p50'] / mns.NDVI_SCALE:+7.3f} "
             f"{st['p99'] / mns.NDVI_SCALE:+7.3f}" if st["valid_px"] else
             f"{'—':>7s} {'—':>7s} {'—':>7s}")
        a(f"  {i:2d}  {rec['label']:6s} {rec['date']:12s} {state:6s} {q}  "
          f"{_norm_note(rec['plan'])}")
    a("")
    a("  BANDS CARRIED RAW — 'floor-lifted: relative use only'")
    a("  ------------------------------------------------------------------")
    raw = [r for r in inv if r["plan"]["mode"] == "raw"]
    if not raw:
        a("  (none)")
    for rec in raw:
        a(f"  * {rec['label']}: {rec['plan']['reason']}")
    a("")
    a("  These bands are computed from BOTH bands RAW and are byte-identical to")
    a("  the corresponding band of nir_stack_ndvi_1m.tif. They are NOT half-")
    a("  corrected: a normalized red over a raw NIR would be on no scale at all")
    a("  and would look corrected. Read them for WHERE vegetation is, never for")
    a("  HOW MUCH against another band.")
    a("")
    a("  WHAT THIS CORRECTION CANNOT FIX")
    a("  ------------------------------------------------------------------")
    a("  * PHENOLOGY. The fit is blind to vegetation by construction. An April")
    a("    frame and an August frame, both perfectly normalized, still disagree")
    a("    over grass and deciduous canopy because the plants really differ.")
    a("    Normalization makes the CAMERAS comparable, never the SEASONS — and")
    a("    this record mixes February, April/May, June, July, August and October")
    a("    acquisitions. A band-to-band difference is still season + change.")
    a("  * WITHIN-SCENE STRUCTURE. One gain and one offset for a whole")
    a("    acquisition cannot touch vignetting, BRDF/hotspot gradients, mosaic")
    a("    seams, or a flight line balanced differently from its neighbour. The")
    a("    spine is two small footprints; what they measure is asserted citywide.")
    a("  * LIFTED FLOORS — refused, not fixed (above).")
    a("  * SATURATION. Where a source clipped at 255 the information is gone.")
    a("  * NON-LINEARITY. Gamma and tone curves are not affine; this is a")
    a("    first-order correction to whatever the real transfer function was.")
    a("  * RESOLUTION. Sources span 30.5 cm to 1 m native and are resampled onto")
    a("    one grid; a 1 m pixel over a tree edge is a mixture, corrected or not.")
    a("")
    a("  THE DARK END IS EXTRAPOLATED — THE ONE THING THAT COULD MISLEAD YOU")
    a("  ------------------------------------------------------------------")
    a("  The correction is fitted on HARDSCAPE, roughly 30-240 DN. Every fitted")
    a("  row publishes its exact domain (fit_x_min / fit_x_max in the table).")
    a("  Anything darker than that domain is EXTRAPOLATION, and here is what it")
    a("  does, measured:")
    a("")
    a("  The reference for red is 2020s at 7.6 cm. At that resolution a masked")
    a("  hardscape pixel is PURE hardscape (its red p5 is 89-135 DN), while at")
    a("  60 cm the same nominal pixel mixes in shaded canopy edge (p5 17-79 DN).")
    a("  So the fitted red OFFSET for the coarse years — around +70 DN — is part")
    a("  radiometry and part the reference's sharpness. Applied to a dark pixel")
    a("  it lifts RED by tens of DN while NIR barely moves, and NDVI is a ratio:")
    a("")
    a("      NORMALIZED NDVI RUNS HARD NEGATIVE IN SHADOW AND OVER WATER.")
    a("")
    a("  Over open water, five of the eight healthy 4-band years CLAMP at exactly")
    a("  -1.000 (raw they span -0.04 to -0.87). Their apparent agreement there is")
    a("  DEGENERATE — everything pinned to the same rail — not a convergence win.")
    a("")
    a("  Two consequences, both operational:")
    a("  * The §12 LIFTED-FLOOR TEST CANNOT BE RUN ON THIS FILE. Water clamps to")
    a("    -1.000 by construction, so the negative-tail diagnostic is destroyed.")
    a("    Run that test on nir_stack_ndvi_1m.tif — the native stack — always.")
    a("  * VEGETATION-PRESENCE READS IN DEEP SHADOW ARE LESS RELIABLE HERE than")
    a("    in the native stack. Shadowed conifer is exactly what this project")
    a("    cares about, so for a shadow question prefer the native product; use")
    a("    this one for cross-year comparison of sunlit canopy.")
    a("  Reproduce the numbers: py -3.12 qc/radiometry_norm.py --step validate [4]")
    a("")
    a("  HOW THE CORRECTION WAS VALIDATED")
    a("  ------------------------------------------------------------------")
    a("  Same-flight cross-sensor pairs — same ground, same day, different")
    a("  sensor and processing chain — must agree over invariant hardscape after")
    a("  correction. Reproduce with:  py -3.12 qc/radiometry_norm.py --step validate")
    a("  Measured (mean |spine p50 difference| over R/G/B[/N]):")
    a("      2015n vs 2015s   16.0 DN raw  ->   1.6 DN normalized")
    a("      2017n vs 2017s   11.4 DN raw  ->   4.6 DN normalized")
    a("      2019n vs 2019s   11.9 DN raw  ->   4.3 DN normalized")
    a("      2019n vs 2019k   11.2 DN raw  ->   2.0 DN normalized  (date-mismatched)")
    a("  And the 2000 King colour cast (IMAGERY_FACTS §3): G/R on invariant")
    a("  ground 1.1785 raw (+22.9% vs the reference's own 0.9591) -> 0.9650")
    a("  corrected (+0.6%).")
    a("")
    if problems:
        a("  NOT INCLUDED")
        a("  ------------------------------------------------------------------")
        for lab, f, why in problems:
            a(f"  * {lab:6s} {f:26s} {why}")
        a("")
    a("  IN ARCGIS")
    a("  ------------------------------------------------------------------")
    a("  * Add nir_stack_ndvi_norm_1m.tif; Symbology -> Stretched, then step the")
    a("    Band dropdown to flicker years. Band names carry [NORM] or")
    a("    [RAW - FLOOR-LIFTED].")
    a("  * Use a FIXED stretch (e.g. -0.2 to 0.8) — a per-band auto-stretch")
    a("    re-normalizes each year and undoes the whole point of this file.")
    a("  * Difference two bands with Raster Calculator for a change candidate")
    a("    layer; do NOT difference a [NORM] band against a [RAW] one.")
    a("")
    a("=" * 78)
    path.write_text("\n".join(A) + "\n", encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def inventory_only(args):
    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    inv, problems = mns.build_inventory(only)
    table = rn.load_table(Path(args.norm_table), force=True)
    print(f"[ndvi-norm] table: {args.norm_table}")
    print(f"[ndvi-norm] {len(inv)} four-band acquisitions")
    for i, rec in enumerate(inv, 1):
        plan = plan_band(rec["label"], table)
        tag = "NORM" if plan["mode"] == "norm" else "RAW "
        print(f"  {i:2d}  [{tag}] {rec['label']:6s} {rec['date']:12s} "
              f"{rec['file']:26s} {_norm_note(plan)}")
        if plan["mode"] == "raw":
            print(f"      REFUSED -> carried raw: {plan['reason'][:160]}")
    for lab, f, why in problems:
        print(f"  !!  {lab:6s} {f:26s} {why}")
    return 0


def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(
        description="Radiometry-normalized NDVI companion to nir_stack_ndvi_1m.tif.")
    ap.add_argument("--step", default="build", choices=["build", "inventory"])
    ap.add_argument("--only", default="")
    ap.add_argument("--resampling", default="bilinear", choices=sorted(mns.RESAMPLING))
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--warp-mem", type=int, default=1024)
    ap.add_argument("--out-dir", default="",
                    help=f"Output directory (default {mns.OUT_DIR}).")
    ap.add_argument("--norm-table", default=str(rn.OUT_CSV))
    ap.add_argument("--no-overviews", action="store_true")
    args = ap.parse_args(filtered)
    return inventory_only(args) if args.step == "inventory" else build(args)


if __name__ == "__main__":
    sys.exit(main())
