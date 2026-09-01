#!/usr/bin/env python3
"""
  ROOF PRESENCE MATRIX — every canonical structure x every catalog year
  ---------------------------------------------------------------------------

WHAT THIS IS
    The production run of `qc/instruments/roof_presence_probe.py`. The probe was a sizing
    experiment on 316 footprints x 8 years; this is the same rule applied to the
    whole canonical buildings layer across the whole imagery record, fused with
    the county Assessor's construction year.

    Output: {roof_presence}/roof_presence_matrix.parquet
            one row per (building_id, year), with

              verdict_assessor  what the RECORD says      (deterministic)
              verdict_probe     what the IMAGERY says     (the 4-cue rule)
              verdict_final     the fused answer
              verdict_rule      which branch decided it
              disagreement      the interesting rows (see below)

    The probe's thresholds, features and verdict rule are IMPORTED from
    `roof_presence_probe`, never copied — that module stays the one home for
    the calibration (CLAUDE.md: one fact, one home). This file adds the
    assessor backbone, the fusion rule, scale, and resumability.

THE FUSION RULE — and why it is asymmetric
    The Assessor roll is CURRENT-STATE. A teardown-and-rebuild carries the NEW
    year and erases the older structure; a demolition leaves no row at all. So:

        assessor says PRESENT  ->  strong.  Something was standing here.
        assessor says ABSENT   ->  weak.    Maybe nothing was here; maybe a
                                            different building was, and the
                                            record no longer remembers it.

    That asymmetry is the whole design:

      1. BACKBONE (no imagery needed).  yr_built <= year - 1  =>  PRESENT.
         About 90% of the canonical layer predates the imagery record, so this
         one line answers most of the matrix deterministically. The `- 1` is
         deliberate: a house finished in year Y may not exist at the moment
         year Y was flown, so credit starts the following year.
      2. THE PROBE FILLS THE WINDOW.  Structures with yr_built inside 2000-2024
         (10.0% of the canonical layer, measured) are exactly the population a
         static footprint layer gets wrong in early years. There the imagery
         decides.
      3. THE PROBE CAN DEMOTE, NEVER SILENTLY.  Where the record says PRESENT
         but the imagery says ABSENT, the row is NOT called present — it is
         flagged `disagree_probe_absent`. Those are the demolition-and-rebuild
         candidates, and they are the rows worth a human's time.

DISAGREEMENT CODES
    disagree_probe_absent   record present, imagery absent.
                            -> the standing structure post-dates the imagery:
                               teardown/rebuild, or an addition that replaced a
                               different building. Also fires on heavy canopy
                               overhang and deep shadow, so it is a CANDIDATE
                               list, not a finding.
    disagree_probe_present  record says not-yet-built, imagery says a roof is
                            there. -> a predecessor building stood on the lot
                            (the record forgot it), or `yr_built` is late.

HONEST LIMITS (inherited from the probe — read its docstring too)
    - "roof present" and "bare cleared ground" are NOT separable by the probe.
      A razed lot mid-construction reads as a roof.
    - The probe's thresholds are IN-SAMPLE for the Greystone subdivision
      (93.5% agreement there) and have never been scored on an independent
      site. Treat `verdict_probe` as a strong hint, not a measurement.
    - A structure demolished before ~2025 has no footprint in ANY source, so it
      is absent from this matrix in every year. The matrix cannot find what the
      geometry layer never had.
    - Four CoE years (2017, 2020, 2022, 2024) are not on the local imagery
      mirror. Their rows carry `probe_status = imagery_unavailable` and are
      decided by the backbone alone.

RESUMABILITY
    Work is chunked by (year, chunk). Each finished chunk is written as a
    parquet part on LOCAL NVMe (never the FUSE mount — CLAUDE.md rule 3), so a
    kill -9 costs at most one chunk. Re-running the identical command skips
    every part already on disk and continues. The exact resume command is
    printed at every checkpoint.

USAGE
    # the sector deliverable (S1..S5), all catalog years
    py -3.12 qc/instruments/roof_presence_matrix.py --scope sectors

    # citywide — hours; resumable, safe to kill
    py -3.12 qc/instruments/roof_presence_matrix.py --scope city

    # timing pilot
    py -3.12 qc/instruments/roof_presence_matrix.py --scope sectors --years 2013 2023n --limit 200

    --merge-only rebuilds the parquet from whatever parts exist, without
    measuring anything. Use it to harvest a partial background run.

Local-only. CPU, windowed reads. No Colab, no GPU.
v001
"""

from __future__ import annotations
from phase4seg.names import clean_argv  # noqa: E402

import argparse
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

_HERE = Path(__file__).resolve().parent           # …/Scripts/qc
_SCRIPTS = _HERE.parent                           # …/Scripts
sys.path.insert(0, str(_HERE))

# The probe is the one home for the calibrated rule. Import, never copy.
from roof_presence_probe import (                 # noqa: E402
    FEATURE_COLS, WORK_CRS, RING_OUTER_M, CORE_ERODE_M,
    build_core_ring, measure, verdict, load_catalog,
)

try:
    from pipeline_log import write_step_log       # noqa: E402
except Exception:
    write_step_log = None


# ── Paths ────────────────────────────────────────────────────────────────────
DATA = Path(r"G:\My Drive\treedata")
BUILDINGS_GPKG = DATA / "buildings" / "buildings_canonical.gpkg"
OUT_DIR = DATA / "phase4" / "qc" / "roof_presence"
OUT_PARQUET = OUT_DIR / "roof_presence_matrix.parquet"
LOGS_DIR = DATA / "phase4" / "logs"

IMAGERY_MIRROR = Path(r"D:\edmonds-pipeline\Imagery")
SECTORS = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\sectors\sectors_v1.gpkg")
SITES_SHP = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid"
                 r"\sites_drawn_clean.shp")
PARTS_ROOT = Path(r"D:\edmonds-pipeline\_tmp\roof_matrix_parts")

CHUNK = 500          # footprints per checkpoint part
GDAL_CACHE_MB = 512  # bigger block cache => fewer re-reads of the same 512px tile


# ── The fusion rule ──────────────────────────────────────────────────────────
# These two functions ARE the policy. pipeline/make_building_masks.py imports
# them so the mask and the matrix can never drift apart.

def assessor_verdict(yr_built, year_num) -> str:
    """What the county record alone says about (structure, year).

    present    yr_built <= year - 1   the backbone. Strong evidence.
    build_year yr_built == year       the ambiguous window; the flight may
                                      predate the certificate of occupancy.
    pre_build  yr_built >  year       the record knows of nothing here yet.
                                      WEAK — a predecessor building would look
                                      exactly like this.
    unknown    no yr_built            ~2.5% of the layer.
    """
    if yr_built is None or (isinstance(yr_built, float) and np.isnan(yr_built)):
        return "unknown"
    yb = int(yr_built)
    if yb <= year_num - 1:
        return "present"
    if yb == year_num:
        return "build_year"
    return "pre_build"


def fuse(va: str, vp: str) -> tuple[str, str, str]:
    """(verdict_assessor, verdict_probe) -> (final, rule, disagreement).

    `vp` is one of present / absent / uncertain / unavailable.
    Returns disagreement = "" when the two sources do not conflict.
    """
    # 1. BACKBONE: the record says something stood here.
    if va == "present":
        if vp == "absent":
            # do NOT quietly call it present; this is the interesting case
            return "uncertain", "disagree", "disagree_probe_absent"
        return "present", "assessor_backbone", ""

    # 2. THE WINDOW: the record puts construction at or after this flight.
    if va in ("build_year", "pre_build"):
        if vp == "present":
            dis = "disagree_probe_present" if va == "pre_build" else ""
            return "present", "probe", dis
        if vp == "absent":
            return "absent", "probe_confirms_record", ""
        # probe could not decide (or no imagery): fall back to the record,
        # which is WEAK in this direction — see the module docstring.
        if va == "pre_build":
            return "absent", "assessor_prebuild_weak", ""
        return "uncertain", "build_year_undecided", ""

    # 3. UNDATED structures: only the imagery has anything to say.
    if vp in ("present", "absent"):
        return vp, "probe_only", ""
    return "uncertain", "no_evidence", ""


# MASK POLICY — used by pipeline/make_building_masks.py.
# A structure is burned into year Y's mask when it is PRESENT, and also when
# nothing could decide. Rationale: the mask's job is to REMOVE roof pixels from
# vegetation products, so a false positive costs a little real ground while a
# false negative leaves a roof masquerading as canopy. The bias is deliberate
# and is reported per year by the mask builder.
MASK_PRESENT_FINAL = ("present", "uncertain")


def mask_present(verdict_final: str) -> bool:
    return verdict_final in MASK_PRESENT_FINAL


# ── Scope selection ──────────────────────────────────────────────────────────
def load_buildings(scope: str, limit: int | None):
    if not BUILDINGS_GPKG.exists():
        raise SystemExit(f"missing {BUILDINGS_GPKG}\n"
                         f"Run:  py -3.12 pipeline/build_buildings_layer.py")
    can = gpd.read_file(BUILDINGS_GPKG, layer="buildings")
    print(f"canonical buildings: {len(can):,}")
    all_w = can.to_crs(WORK_CRS)

    if scope == "city":
        sel = all_w
    elif scope == "sectors":
        sec = gpd.read_file(SECTORS, layer="sectors").to_crs(WORK_CRS)
        geom = sec.geometry.union_all()
        sel = all_w[all_w.representative_point().within(geom)]
        print(f"  sector scope (sectors_v1, S1..S5): {len(sel):,}")
    elif scope == "development":
        dev = gpd.read_file(SITES_SHP)
        dev = dev[(dev.site == "Development") & (dev.role == "region")]
        geom = dev.to_crs(WORK_CRS).geometry.union_all()
        sel = all_w[all_w.representative_point().within(geom)]
        print(f"  Development (Greystone) scope: {len(sel):,}")
    else:
        raise SystemExit(f"unknown scope {scope!r}")

    # SPATIAL SORT: the imagery is 512-px tiled, so reading footprints in
    # spatial order keeps the GDAL block cache warm. Hilbert order beats a
    # row-major sort because it is local in BOTH axes.
    try:
        sel = sel.iloc[np.argsort(sel.geometry.hilbert_distance().values)]
    except Exception:
        c = sel.geometry.centroid
        sel = sel.iloc[np.lexsort((c.x.values, np.round(c.y.values / 200.0)))]
    sel = sel.reset_index(drop=True)
    if limit:
        sel = sel.iloc[:limit].copy()
        print(f"  --limit {limit}: {len(sel):,} footprints")
    return sel, all_w


def prepare_geometry(sel, all_w):
    """Core / ring polygons, built ONCE in true metres (EPSG:26910).

    Neighbour cut-out uses the FULL canonical layer, not just the selection, so
    a neighbouring garage is removed from a ring even when it was not selected.
    """
    t0 = time.time()
    if len(sel) == len(all_w):
        near = all_w
    else:
        hit = all_w.sindex.query(sel.geometry.buffer(RING_OUTER_M + 5),
                                 predicate="intersects")
        near = all_w.iloc[np.unique(hit[1])]
    print(f"  neighbours considered for ring cut-out: {len(near):,}")
    cores, rings = build_core_ring(sel, near.reset_index(drop=True))
    sel = sel.assign(_core=cores, _ring=rings)
    probeable = np.array([(not c.is_empty) and (not r.is_empty)
                          for c, r in zip(cores, rings)])
    dropped = int((~probeable).sum())
    if dropped:
        print(f"  {dropped} footprints have an empty core or ring "
              f"(smaller than the {CORE_ERODE_M} m erosion) — probe skipped, "
              f"assessor backbone still applies")
    sel["_probeable"] = probeable
    print(f"  core/ring built in {time.time()-t0:.1f}s")
    return sel


# ── Measurement ──────────────────────────────────────────────────────────────
ATTR_COLS = ["building_id", "source", "area_m2", "yr_built", "yr_built_min",
             "yr_built_max", "yr_built_rule", "n_improvements", "parcel_id",
             "roof_mat", "roof_type", "use_desc", "height_m"]


def year_rows(sel, ykey, meta, path, chunk_idx, lo, hi):
    """Measure one chunk of footprints for one year. Returns a DataFrame."""
    sub = sel.iloc[lo:hi]
    n = len(sub)
    base = {c: np.nan for c in FEATURE_COLS}
    out = []

    probeable = sub["_probeable"].values
    if path is None:
        core_r = ring_r = [None] * n
        src = None
    else:
        src = rasterio.open(path)
        core_r = gpd.GeoSeries(sub["_core"].values,
                               crs=WORK_CRS).to_crs(src.crs).values
        ring_r = gpd.GeoSeries(sub["_ring"].values,
                               crs=WORK_CRS).to_crs(src.crs).values
    try:
        has_nir = bool(src is not None and src.count >= 4)
        for k in range(n):
            rec = sub.iloc[k]
            if src is None:
                m = dict(base)
                m["core_px"] = m["ring_px"] = 0
                vp, why, nsig, status = "unavailable", "no_imagery", 0, \
                    "imagery_unavailable"
            elif not probeable[k]:
                m = dict(base)
                m["core_px"] = m["ring_px"] = 0
                vp, why, nsig, status = "unavailable", "empty_core_or_ring", 0, \
                    "geometry_too_small"
            else:
                m = measure(src, core_r[k], ring_r[k], has_nir)
                if m is None:
                    m = dict(base)
                    m["core_px"] = m["ring_px"] = 0
                vp, why, nsig = verdict(m)
                status = "ok"
            row = {c: rec[c] for c in ATTR_COLS}
            row.update({
                "year": ykey,
                "year_num": int(str(ykey)[:4]),
                "gsd_cm": meta["gsd_cm"],
                "bands": meta["bands"],
                **m,
                "verdict_probe": vp,
                "probe_reason": why,
                "probe_status": status,
                "n_signals": nsig,
            })
            out.append(row)
    finally:
        if src is not None:
            src.close()
    df = pd.DataFrame(out)
    df["chunk"] = chunk_idx
    return df


def resolve_verdicts(df: pd.DataFrame) -> pd.DataFrame:
    """Attach verdict_assessor / verdict_final / verdict_rule / disagreement."""
    yb = pd.to_numeric(df.yr_built, errors="coerce")
    df["verdict_assessor"] = [assessor_verdict(y, n)
                              for y, n in zip(yb, df.year_num)]
    fused = [fuse(a, p) for a, p in zip(df.verdict_assessor, df.verdict_probe)]
    df["verdict_final"] = [f[0] for f in fused]
    df["verdict_rule"] = [f[1] for f in fused]
    df["disagreement"] = [f[2] for f in fused]
    df["mask_present"] = df.verdict_final.map(mask_present)
    return df


# ── Driver ───────────────────────────────────────────────────────────────────
def resolve_year(cat, key):
    """Path to a year's imagery on the local mirror, or None if not held."""
    e = cat.get(str(key))
    if e is None:
        raise SystemExit(f"year key {key!r} not in YEAR_CATALOG")
    p = IMAGERY_MIRROR / e["native_file"]
    return (p if p.exists() else None), e


def run(args):
    os.environ.setdefault("GDAL_CACHEMAX", str(GDAL_CACHE_MB))
    cat = load_catalog()
    years = args.years or [str(e["key"]) for e in
                           sorted(cat.values(), key=lambda e: str(e["key"]))]
    parts_dir = PARTS_ROOT / args.scope
    parts_dir.mkdir(parents=True, exist_ok=True)
    resume_cmd = (f"py -3.12 qc/instruments/roof_presence_matrix.py --scope {args.scope}"
                  + (f" --years {' '.join(args.years)}" if args.years else "")
                  + (f" --limit {args.limit}" if args.limit else ""))

    if not args.merge_only:
        sel, all_w = load_buildings(args.scope, args.limit)
        sel = prepare_geometry(sel, all_w)
        n = len(sel)
        chunks = [(i, i * CHUNK, min((i + 1) * CHUNK, n))
                  for i in range((n + CHUNK - 1) // CHUNK)]
        total = len(years) * len(chunks)
        print(f"\n{n:,} footprints x {len(years)} years "
              f"= {n*len(years):,} rows, in {total} chunks of <= {CHUNK}")
        print(f"parts -> {parts_dir}   (local NVMe; resumable)\n")

        done = t_start = 0
        t_start = time.time()
        for ykey in years:
            path, meta = resolve_year(cat, ykey)
            ty = time.time()
            n_new = 0
            for ci, lo, hi in chunks:
                part = parts_dir / f"{ykey}_{ci:04d}.parquet"
                done += 1
                if part.exists():
                    continue
                df = year_rows(sel, ykey, meta, path, ci, lo, hi)
                tmp = part.with_suffix(".parquet.tmp")
                df.to_parquet(tmp, index=False)
                tmp.replace(part)          # atomic: a part is whole or absent
                n_new += 1
                if n_new % 5 == 0:
                    el = time.time() - t_start
                    print(f"    [{done}/{total}] {ykey} chunk {ci} "
                          f"elapsed {el/60:.1f} min  "
                          f"eta {el/max(done,1)*(total-done)/60:.0f} min",
                          flush=True)
            tag = "SKIPPED (no local imagery)" if path is None else \
                  f"{n_new} new chunks"
            print(f"  {ykey:<6} {meta['gsd_cm']:>5.1f} cm {meta['bands']}b  "
                  f"{tag}  {time.time()-ty:.1f}s", flush=True)
        print(f"\ncheckpoint complete. Resume/extend with:\n  {resume_cmd}")

    # ── merge ────────────────────────────────────────────────────────────────
    parts = sorted(parts_dir.glob("*.parquet"))
    if not parts:
        raise SystemExit(f"no parts under {parts_dir}")
    print(f"\nmerging {len(parts):,} parts ...", flush=True)
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    df = resolve_verdicts(df)
    df = df.sort_values(["building_id", "year_num", "year"]).reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / (OUT_PARQUET.name if args.scope == "city"
                     else f"roof_presence_matrix_{args.scope}.parquet")
    tmp_local = Path(args.tmp_dir) / out.name
    tmp_local.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(tmp_local, index=False)
    import shutil
    shutil.copy2(tmp_local, out)
    print(f"wrote {out}  ({len(df):,} rows, {out.stat().st_size/1e6:.1f} MB)")
    report(df, out)
    return df, out, resume_cmd


# ── Reporting ────────────────────────────────────────────────────────────────
def report(df, out):
    print(f"\n{'='*78}\nMATRIX  {df.building_id.nunique():,} structures x "
          f"{df.year.nunique()} years = {len(df):,} rows\n{'='*78}")

    print("\nverdict_final x verdict_rule")
    print(pd.crosstab(df.verdict_rule, df.verdict_final).to_string())

    print("\nHOW MUCH DID THE RECORD ANSWER WITHOUT IMAGERY?")
    bb = (df.verdict_rule == "assessor_backbone").mean()
    print(f"  assessor_backbone decided {100*bb:.1f}% of all rows")
    probe_rows = df.verdict_rule.isin(["probe", "probe_confirms_record",
                                       "probe_only", "disagree"])
    print(f"  the imagery probe decided or contradicted {100*probe_rows.mean():.1f}%")

    print("\nDISAGREEMENTS (the interesting rows)")
    d = df[df.disagreement != ""]
    if len(d):
        print(d.disagreement.value_counts().to_string())
        print(f"  structures involved: "
              f"{d.building_id.nunique():,} / {df.building_id.nunique():,}")
        print("\n  by year")
        print(d.groupby(["year", "disagreement"]).size()
               .unstack(fill_value=0).to_string())
    else:
        print("  none")

    print("\nPRESENT COUNT BY YEAR (mask_present)")
    g = (df.groupby("year")
           .agg(n=("building_id", "size"),
                present=("verdict_final", lambda s: int((s == "present").sum())),
                absent=("verdict_final", lambda s: int((s == "absent").sum())),
                uncertain=("verdict_final",
                           lambda s: int((s == "uncertain").sum())),
                masked=("mask_present", "sum"))
           .sort_index())
    g["pct_masked"] = (100 * g.masked / g.n).round(1)
    print(g.to_string())

    print("\nPROBE STATUS")
    print(df.probe_status.value_counts().to_string())


def greystone_check(df):
    """The one place in Edmonds where 'absent' is trustworthy: 71 houses built
    2001-2005 on graded raw land. A correct matrix flips them present across
    that window and holds them present afterwards."""
    yb = pd.to_numeric(df.yr_built, errors="coerce")
    dev = df[yb.between(2001, 2005).fillna(False)]
    if dev.empty:
        return
    print(f"\n{'='*78}\nGREYSTONE-STYLE CHECK — structures with yr_built 2001-2005")
    print(f"{dev.building_id.nunique():,} structures\n{'='*78}")
    t = (dev.groupby("year")
            .agg(n=("building_id", "size"),
                 present=("verdict_final", lambda s: int((s == "present").sum())),
                 absent=("verdict_final", lambda s: int((s == "absent").sum())),
                 uncertain=("verdict_final",
                            lambda s: int((s == "uncertain").sum())))
            .reset_index())
    t["year_num"] = t.year.str[:4].astype(int)
    t = t.sort_values(["year_num", "year"])
    t["pct_present"] = (100 * t.present / t.n).round(1)
    print(t.to_string(index=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", default="sectors",
                    choices=["sectors", "city", "development"])
    ap.add_argument("--years", nargs="+", default=None,
                    help="YEAR_CATALOG keys; default = every catalog year")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N footprints (timing pilot)")
    ap.add_argument("--merge-only", action="store_true",
                    help="rebuild the parquet from existing parts; measure nothing")
    ap.add_argument("--tmp-dir", default=r"D:\edmonds-pipeline\_tmp")
    args = ap.parse_args(argv)

    t0 = time.time()
    df, out, resume_cmd = run(args)
    greystone_check(df)
    el = time.time() - t0
    print(f"\nelapsed {el/60:.1f} min")
    print(f"resume/extend:  {resume_cmd}")

    if write_step_log is not None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            d = df[df.disagreement != ""]
            write_step_log(script="roof_presence_matrix", step=args.scope,
                           logs_dir=LOGS_DIR, errors=0,
                           out_parquet=str(out), rows=len(df),
                           structures=int(df.building_id.nunique()),
                           years=int(df.year.nunique()),
                           disagreements=int(len(d)),
                           backbone_pct=round(
                               100 * (df.verdict_rule == "assessor_backbone").mean(), 2),
                           notes=f"resume: {resume_cmd}")
        except Exception as exc:
            print(f"[matrix] WARN could not write step log: {exc}")
    return 0


if __name__ == "__main__":
    # Colab injects `-f <json>`; strip it (CLAUDE.md rule 4).
    filtered = clean_argv()
    sys.exit(main(filtered))
