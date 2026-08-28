r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: PER-CROWN TOUCH / COVER, a label-independent arm metric

  WHY IT IS (ALMOST) FREE
    Coarse-tier and --force-citywide runs learn from the Phase-3 citywide 2020
    SEMANTIC MASK (phase3/edmonds_canopy_mask_2020.tif). Verified in the engine,
    not assumed:
      · phase4seg/cli.py:576-578   citywide = (coarse or --force-citywide) and
                                   not --coarse-site-tiling and not --anchor-labels
      · phase4seg/labels.py:315-321  citywide => Step 1 (crown burn) is SKIPPED
                                   ("citywide: labels step is skipped by design")
      · phase4seg/tiling.py:341-344,419-420  every citywide tile is labelled by
                                   canopy_label_from_2020_mask() off MASK_2020
      · phase4seg/core.py:785,795-800  step_train reads tile_index_*.csv only;
                                   `grep -n crown core.py` returns nothing
    So the 222,435 per-crown INSTANCE polygons never enter such a run. No holdout
    has to be reserved — they are already fully held out.

  THE ESCAPE HATCH THIS SCRIPT POLICES
    tiling.py:349-357,421-424 apply an ADD-ONLY overlay from --add-canopy-mask
    into citywide label tiles. On 2009 the `hybrid_v1`, `groves_lidar` and
    `groves_nolidar` arms use overlays whose force-canopy code is RASTERISED
    CROWN POLYGONS — qc/build_groves_overlay.py:72 (GROVES = stable_crowns_v0
    .gpkg), :293 (pos_shapes = groves + forest), :343 (rasterize -> CODE_CANOPY),
    and stable_crowns_v0.gpkg is a 2,307-row subset of the canonical crown layer
    with crown_id intact (qc/mine_stable_crowns.py:40,101-105). Those crowns were
    TRAINED AS FORCED CANOPY: unexcluded they score ~1.0 by construction and the
    metric FLATTERS the contaminated arm.
    This script therefore reads each arm's own run manifest (phase4/runs/*_tile/
    manifest.json, written by cli.py:414) and decides from the recorded facts —
    never from a hardcoded tag list — whether exclusion is required. A
    contaminated arm scored without exclusion is REFUSED.

  WHAT IT MEASURES, per arm (one prob raster), on the arms' COMMON footprint
    touch       any predicted-canopy pixel intersects the crown
    cover_frac  fraction of the crown's valid pixels predicted canopy
    reported as: crowns considered, touch rate, cover_frac median/quartiles and
    the fraction at >= 0.25 / 0.50 / 0.75 — stratified by RECOMPUTED size class
    and by sector, plus a PAIRED (discordance) table, which is the part an
    aggregate rate would hide.

  ONE READ, EVERY THRESHOLD
    Per crown we accumulate a 256-bin histogram of the predicted DN. Because the
    prob rasters are uint8, that histogram determines touch and cover_frac
    EXACTLY at all 255 possible thresholds, so --match-precision-to costs no
    extra pass. Same trick, same reason, as qc/phase4_arm_pr_curves.py, whose
    curve machinery (_curve_from_hists / _at_precision) and C-CAP conventions
    (via phase4_qc_indep) are IMPORTED here, never reimplemented.

  NOT TRUTH. Read the header the script prints before quoting any number.

  USAGE
    py -3.12 qc/phase4_crown_touch.py --year 2009 \
        --tags fullext_sectors_v1,rgb3_nodeb --thresh 0.5
    py -3.12 qc/phase4_crown_touch.py --year 2009 \
        --tags fullext_sectors_v1,hybrid_v1 \
        --match-precision-to 2009/fullext_sectors_v1 \
        --ref D:\edmonds-pipeline\Imagery\ccap_2016_hires_lc_snohfull.tif
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
DATA = Path(r"G:\My Drive\treedata")
RUNS = DATA / "phase4" / "runs"

# The canonical per-crown instance layer (phase 0). D: mirror first, lake second
# — the same resolution order qc/mine_stable_crowns.py:40-41 uses.
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
CROWNS_FALLBACK = DATA / "inference" / "edmonds_crowns_2020.gpkg"

# Known crown-derived training-overlay ingredients (qc/build_groves_overlay.py:72,263).
STABLE_CROWNS = DATA / "phase4" / "qc" / "stable_crowns_v0.gpkg"
FOREST_SITE = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid"
                   r"\negative_sites_draw.shp")

SECTORS_DIR = DATA / "phase4" / "qc" / "sectors"

# TRUE areas only. The shipped crown layer's area_m2/size_class are EPSG:3857
# (Web Mercator) values, inflated 2.2215x at this latitude — phase0_instance_seg
# .py:425-440 documents the trap and deliberately does NOT fix it in place
# (size_class cut-points were calibrated against the inflated numbers).
AREA_CRS = "EPSG:26910"                      # UTM 10N, true metres

# Recomputed size bins, in TRUE m². Printed in the header so nobody collides
# them with the layer's stored small/medium/large.
SIZE_BINS = [0.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, float("inf")]
COVER_STEPS = (0.25, 0.50, 0.75)


def _load_arm_pr():
    """Import phase4_arm_pr_curves as a module so the curve math and the C-CAP
    conventions are the SAME OBJECTS the arm comparison of record uses."""
    spec = importlib.util.spec_from_file_location(
        "_arm_pr", HERE / "phase4_arm_pr_curves.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # safe: the script is __main__-guarded
    return mod


AP = _load_arm_pr()
QI = AP.QI
MASKS = AP.MASKS


# ── provenance ────────────────────────────────────────────────────────────────

def _manifest_for(year, tag, step="tile"):
    """Newest phase4/runs manifest for this (year, tag, step). Run dirs are
    named {ts}_{year}_{tag}_{step} with an ISO-ish ts, so lexicographic sort is
    chronological. Untagged runs use the literal 'untagged'."""
    tagpart = tag if tag else "untagged"
    dirs = sorted(RUNS.glob(f"*_{year}_{tagpart}_{step}"))
    for d in reversed(dirs):
        mp = d / "manifest.json"
        if mp.exists():
            try:
                return mp, json.loads(mp.read_text(encoding="utf-8"))
            except Exception as e:                        # noqa: BLE001
                print(f"  ! unreadable manifest {mp}: {type(e).__name__}: {e}")
    return None, None


def _provenance(year, tag):
    """Decide, from the run's OWN recorded facts, whether crowns could have
    entered this arm's training labels.

    status:
      clean        citywide recipe, no add-overlay        -> score as-is
      add_overlay  --add-canopy-mask present              -> MITIGABLE by exclusion
      site_crowns  not the citywide path (anchor/site)    -> NOT mitigable
      unknown      no manifest found                      -> refuse w/o an override
    """
    mp, m = _manifest_for(year, tag)
    if m is None:
        return dict(status="unknown", manifest=None, add=None, argv=None,
                    detail="no phase4/runs/*_tile/manifest.json found")
    lab = m.get("labels") or {}
    argv = m.get("argv") or []
    add = lab.get("add_canopy_mask")
    forced = bool(lab.get("force_citywide"))
    anchor = "--anchor-labels" in argv
    site_tiling = "--coarse-site-tiling" in argv
    base = dict(manifest=mp, add=add, argv=argv,
                source_mask=lab.get("source_mask"), force_citywide=forced)
    if anchor or site_tiling:
        return dict(base, status="site_crowns",
                    detail=("--anchor-labels" if anchor else "--coarse-site-tiling")
                           + " defeats the citywide path; labels come from site "
                             "crown polygons (phase4seg/labels.py:217-243)")
    if not forced:
        return dict(base, status="site_crowns",
                    detail="manifest labels.force_citywide is not true — this run "
                           "did not use the citywide 2020-mask recipe")
    if add:
        return dict(base, status="add_overlay",
                    detail=f"--add-canopy-mask {Path(str(add)).name} "
                           f"({lab.get('add_canopy_mask_size')} B) is applied to "
                           f"citywide label tiles at phase4seg/tiling.py:421-424")
    return dict(base, status="clean",
                detail="citywide 2020-mask labels, no add-overlay")


# ── crowns ────────────────────────────────────────────────────────────────────

def _read_crowns(path, bounds):
    import geopandas as gpd
    g = gpd.read_file(path, bbox=tuple(bounds), engine="pyogrio")
    g = g[g.geometry.notna() & ~g.geometry.is_empty].reset_index(drop=True)
    return g


def _load_exclusion(src, crowns):
    """Return (crown_id set | None, geometry list | None) for one source.

    A source carrying crown_id excludes BY ID (exact — it is a subset of the
    canonical layer). Anything else excludes by geometry (crowns intersecting).
    """
    import geopandas as gpd
    p = Path(src)
    if not p.exists():
        return None, None, f"MISSING: {p}"
    g = gpd.read_file(p, engine="pyogrio")
    if p == FOREST_SITE:
        # Mirror qc/build_groves_overlay.py:259-263 exactly: the 'Forest' site,
        # and of its two equal-area rows take the Tree/positive one.
        if "site" in g.columns:
            g = g[g["site"] == "Forest"]
        if "role" in g.columns and len(g):
            tree = g[g["role"].astype(str).str.strip().str.lower()
                     .isin(("tree", "positive"))]
            g = tree if len(tree) else g.iloc[[0]]
    if not len(g):
        return None, None, f"{p.name}: no features selected"
    if "crown_id" in g.columns:
        return set(g["crown_id"].astype(str)), None, \
            f"{p.name}: {len(g):,} features, excluded BY crown_id"
    if g.crs is not None and crowns.crs is not None:
        g = g.to_crs(crowns.crs)
    return None, list(g.geometry.values), \
        f"{p.name}: {len(g):,} features, excluded BY GEOMETRY (crowns intersecting)"


# ── the single pass ───────────────────────────────────────────────────────────

def _accumulate(paths, tags, crowns, block_rows, all_touched, ref_path,
                ref_scheme, ref_map):
    """One read of every arm. Returns (per-crown DN histograms, n_rast,
    footprint px, and — when a reference is given — pos/neg DN histograms for
    the curve machinery)."""
    n = len(crowns)
    srcs = [rasterio.open(p) for p in paths]
    W, H = srcs[0].width, srcs[0].height
    tf0, crs0 = srcs[0].transform, srcs[0].crs

    hist = {t: np.zeros((n, 256), dtype=np.uint32) for t in tags}
    n_rast = np.zeros(n, dtype=np.int64)
    valid_px = 0

    pos = {t: np.zeros(256, dtype=np.int64) for t in tags}
    neg = {t: np.zeros(256, dtype=np.int64) for t in tags}
    scorable_px = 0

    sindex = crowns.sindex
    geoms = crowns.geometry.values

    ref_src = ref_vrt = None
    lut = ignore_id = prim_ids = canopy_id = None
    if ref_path:
        names, canopy_order, _grass, code_to_group = QI.load_ref_map(ref_scheme, ref_map)
        canopy_id = names.index("canopy") if "canopy" in names else 1
        other_id = names.index("other") if "other" in names else 0
        lut = QI.build_lut(names, code_to_group) if ref_scheme != "binary" else None
        defs = QI.canopy_definitions(canopy_order)
        primary_idx = 1 if len(defs) >= 2 else 0
        primary_name, primary_groups = defs[primary_idx]
        ignore_id = names.index("ignore")
        prim_ids = [names.index(g) for g in primary_groups]
        print(f"[crown-touch] reference canopy definition: {primary_name}")
        ref_src = rasterio.open(ref_path)
        ref_vrt = WarpedVRT(ref_src, crs=crs0, transform=tf0, width=W, height=H,
                            resampling=Resampling.nearest)

    try:
        n_blocks = (H + block_rows - 1) // block_rows
        for bi, row0 in enumerate(range(0, H, block_rows)):
            h = min(block_rows, H - row0)
            win = Window(0, row0, W, h)
            btf = rasterio.windows.transform(win, tf0)

            # crowns whose bbox meets this block — rasterised EVERY block (even
            # fully-nodata ones) so n_rast is the crown's true in-grid pixel
            # count and the valid-fraction gate below cannot be flattered.
            b = rasterio.windows.bounds(win, tf0)
            cand = np.asarray(sorted(sindex.query(_box(*b))), dtype=np.int64)
            ids = None
            if cand.size:
                ids = rasterize(
                    [(geoms[g], i + 1) for i, g in enumerate(cand)],
                    out_shape=(h, W), transform=btf, fill=0, dtype="int32",
                    all_touched=all_touched)
                nz = ids > 0
                if nz.any():
                    cnt = np.bincount(ids[nz].astype(np.int64),
                                      minlength=cand.size + 1)[1:]
                    n_rast[cand] += cnt
                else:
                    ids = None

            prs = [s.read(1, window=win) for s in srcs]
            valid = prs[0] != 255
            for pr in prs[1:]:
                valid &= (pr != 255)          # INTERSECTION — identical ground
            if not valid.any():
                if bi % 10 == 0 or bi == n_blocks - 1:
                    print(f"    block {bi+1}/{n_blocks}", flush=True)
                continue
            valid_px += int(valid.sum())

            if ref_vrt is not None:
                rc = ref_vrt.read(1, window=win)
                if ref_scheme == "binary":
                    # mirrors phase4_arm_pr_curves.py:202-206 exactly
                    gid = np.full(rc.shape, other_id, dtype=np.int16)
                    gid[rc > 0] = canopy_id
                else:
                    gid = lut[np.clip(rc.astype(np.int64), 0, 255)]
                rnd = ref_src.nodata
                if rnd is not None and 0 <= int(rnd) < 256:
                    gid[rc == rnd] = ignore_id
                sv = valid & (gid != ignore_id)
                if sv.any():
                    scorable_px += int(sv.sum())
                    prim = sv & np.isin(gid, prim_ids)
                    other = sv & ~prim
                    for t, pr in zip(tags, prs):
                        pos[t] += np.bincount(pr[prim], minlength=256)
                        neg[t] += np.bincount(pr[other], minlength=256)

            if ids is not None:
                m = (ids > 0) & valid
                if m.any():
                    li = ids[m].astype(np.int64) - 1
                    nloc = cand.size
                    for t, pr in zip(tags, prs):
                        key = li * 256 + pr[m].astype(np.int64)
                        hb = np.bincount(key, minlength=nloc * 256
                                         ).reshape(nloc, 256)
                        hist[t][cand] += hb.astype(np.uint32)

            if bi % 10 == 0 or bi == n_blocks - 1:
                print(f"    block {bi+1}/{n_blocks}", flush=True)
    finally:
        if ref_vrt is not None:
            ref_vrt.close()
        if ref_src is not None:
            ref_src.close()
        for s in srcs:
            s.close()

    return hist, n_rast, valid_px, pos, neg, scorable_px


def _box(*b):
    from shapely.geometry import box
    return box(*b)


# ── reporting helpers ─────────────────────────────────────────────────────────

def _pred_counts(h, cut):
    """Predicted-canopy pixels per crown at DN >= cut (suffix sum of the
    per-crown histogram). cut is derived as round(t*254) to match
    phase4_arm_pr_curves' i50 = round(0.5*254) and its thr = i/254."""
    return h[:, cut:].sum(axis=1).astype(np.int64)


def _stats(cover, touch):
    if cover.size == 0:
        return None
    q = np.nanpercentile(cover, [25, 50, 75])
    d = dict(n=int(cover.size), touch=float(touch.mean()),
             q25=float(q[0]), med=float(q[1]), q75=float(q[2]),
             mean=float(cover.mean()))
    for s in COVER_STEPS:
        d[f"ge{int(s*100)}"] = float((cover >= s).mean())
    return d


def _row(name, s):
    if s is None:
        return f"| {name} | 0 | — | — | — | — | — | — | — |"
    return (f"| {name} | {s['n']:,} | {s['touch']:.4f} | {s['med']:.4f} | "
            f"{s['q25']:.4f} | {s['q75']:.4f} | "
            + " | ".join(f"{s[f'ge{int(x*100)}']:.4f}" for x in COVER_STEPS) + " |")


HDR = ("| group | crowns | touch | cover med | q25 | q75 | "
       + " | ".join(f">={s:.2f}" for s in COVER_STEPS) + " |")
SEP = "|---" * (6 + len(COVER_STEPS)) + "|"


def main():
    ap = argparse.ArgumentParser(
        description="Per-crown touch/cover — a training-label-independent arm metric.")
    ap.add_argument("--year", default="2009")
    ap.add_argument("--tags", required=True,
                    help="comma-separated run tags; '' means the untagged raster")
    ap.add_argument("--thresh", type=float, default=None,
                    help="explicit probability threshold for EVERY arm")
    ap.add_argument("--match-precision-to", default=None, metavar="YEAR/TAG",
                    help="pick each arm's threshold so its PIXEL precision equals "
                         "this reference arm's at --ref-thresh (needs --ref)")
    ap.add_argument("--ref-thresh", type=float, default=0.5,
                    help="the reference arm's own operating point (default 0.5)")
    ap.add_argument("--ref", default=None,
                    help="reference land-cover raster (C-CAP) — required for "
                         "--match-precision-to and for the curve self-check")
    ap.add_argument("--ref-scheme", default="ccap", choices=["ccap", "binary"])
    ap.add_argument("--ref-map", default=None)
    ap.add_argument("--crowns", default=None)
    ap.add_argument("--exclude-crowns", action="append", default=[],
                    help="extra crown-derived training source(s) to exclude; "
                         "repeatable. Defaults are added automatically for any "
                         "arm whose manifest shows an add-canopy overlay.")
    ap.add_argument("--no-exclude", action="store_true",
                    help="skip exclusion — REFUSED for a contaminated arm")
    ap.add_argument("--allow-unverified-provenance", action="store_true",
                    help="score an arm whose run manifest cannot be found")
    ap.add_argument("--sectors", default=None,
                    help="sector gpkg (default phase4/qc/sectors/sectors_v1.gpkg)")
    ap.add_argument("--min-valid-frac", type=float, default=0.90,
                    help="a crown counts only if this fraction of its in-grid "
                         "pixels are valid in EVERY arm (default 0.90)")
    ap.add_argument("--min-rast-px", type=int, default=1)
    ap.add_argument("--all-touched", action="store_true",
                    help="rasterise crowns with all_touched=True")
    ap.add_argument("--block-rows", type=int, default=1024)
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args([a for a in sys.argv[1:]
                          if not (a == "-f" or a.endswith(".json"))])

    if (args.thresh is None) == (args.match_precision_to is None):
        raise SystemExit(
            "Pick exactly ONE of --thresh or --match-precision-to.\n"
            "There is no default: Method_Pipeline.md 'Operating-point protocol' — a "
            "fixed 0.5 compares differently-calibrated models by an accident of where "
            "their probability mass landed, which produced three wrong conclusions "
            "this week.")
    if args.match_precision_to and not args.ref:
        raise SystemExit("--match-precision-to needs --ref (precision is defined "
                         "against a reference land cover).")

    tags = [t.strip() for t in args.tags.split(",")]
    paths = []
    for t in tags:
        p = MASKS / (f"edmonds_canopy_prob_{args.year}" + (f"_{t}" if t else "") + ".tif")
        if not p.exists():
            raise SystemExit(f"missing prob raster: {p}")
        paths.append(p)

    # ── provenance gate ───────────────────────────────────────────────────────
    print(f"[crown-touch] year={args.year}  arms={tags}")
    prov = {t: _provenance(args.year, t) for t in tags}
    need_exclusion = False
    for t in tags:
        pv = prov[t]
        mp = pv.get("manifest")
        print(f"  provenance {t or '(untagged)'}: {pv['status'].upper()} — {pv['detail']}")
        print(f"    manifest: {mp if mp else 'NONE'}")
        if pv["status"] == "site_crowns":
            raise SystemExit(
                f"REFUSING to score arm '{t}': {pv['detail']}. Crown polygons are "
                f"this arm's LABEL SOURCE, so a per-crown metric is circular and no "
                f"id-exclusion can repair it.")
        if pv["status"] == "unknown" and not args.allow_unverified_provenance:
            raise SystemExit(
                f"REFUSING to score arm '{t}': {pv['detail']}. Its training labels "
                f"cannot be verified crown-free. Re-run with "
                f"--allow-unverified-provenance only if you can vouch for it another way.")
        if pv["status"] == "add_overlay":
            need_exclusion = True
    if need_exclusion and args.no_exclude:
        raise SystemExit(
            "REFUSING: an arm trained with an add-canopy overlay and --no-exclude was "
            "passed. Those crowns were labelled FORCED CANOPY, so the metric would "
            "flatter that arm by construction.")

    import geopandas as gpd
    import pandas as pd

    with rasterio.open(paths[0]) as s0:
        bounds, crs0 = s0.bounds, s0.crs
        px_area_crs_units = abs(s0.transform.a * s0.transform.e)
    metas = []
    for p in paths:
        with rasterio.open(p) as s:
            metas.append((s.width, s.height, s.crs.to_string(),
                          tuple(round(v, 6) for v in s.transform[:6])))
    if len(set(metas)) != 1:
        raise SystemExit("arms are NOT on a common grid; refusing to compare:\n  "
                         + "\n  ".join(map(str, metas)))

    cpath = Path(args.crowns) if args.crowns else (
        CROWNS if CROWNS.exists() else CROWNS_FALLBACK)
    if not cpath.exists():
        raise SystemExit(f"crown layer not found: {cpath}")
    crowns = _read_crowns(cpath, bounds)
    if crowns.crs is not None and crs0 is not None and crowns.crs != crs0:
        crowns = crowns.to_crs(crs0)
    print(f"[crown-touch] crowns: {len(crowns):,} from {cpath}")

    # TRUE area — never the stored area_m2 (EPSG:3857, 2.2215x inflated;
    # phase0_instance_seg.py:425-440).
    true_area = crowns.geometry.to_crs(AREA_CRS).area.to_numpy()
    stored = crowns["area_m2"].to_numpy() if "area_m2" in crowns.columns else None
    if stored is not None and len(stored):
        with np.errstate(divide="ignore", invalid="ignore"):
            infl = float(np.nanmedian(stored / np.where(true_area > 0, true_area, np.nan)))
        print(f"[crown-touch] stored area_m2 / TRUE {AREA_CRS} area: median {infl:.4f}x "
              f"(expected ~2.2215 — confirms the CRS-unit trap)")
    diam = 2.0 * np.sqrt(np.maximum(true_area, 0) / np.pi)
    size_lbl = np.array([f"{SIZE_BINS[i]:g}-{SIZE_BINS[i+1]:g}"
                         for i in range(len(SIZE_BINS) - 1)], dtype=object)
    size_lbl[-1] = f">={SIZE_BINS[-2]:g}"
    size_idx = np.clip(np.digitize(true_area, SIZE_BINS[1:-1], right=True),
                       0, len(size_lbl) - 1)

    # ── exclusion ─────────────────────────────────────────────────────────────
    sources = list(args.exclude_crowns)
    if need_exclusion and not args.no_exclude:
        for d in (STABLE_CROWNS, FOREST_SITE):
            if str(d) not in [str(Path(s)) for s in sources]:
                sources.append(str(d))
    excl = np.zeros(len(crowns), dtype=bool)
    excl_notes = []
    cid = crowns["crown_id"].astype(str).to_numpy() if "crown_id" in crowns.columns \
        else np.array([str(i) for i in range(len(crowns))])
    for src in sources:
        ids, geoms, note = _load_exclusion(src, crowns)
        hit = np.zeros(len(crowns), dtype=bool)
        if ids is not None:
            hit = pd.Series(cid).isin(ids).to_numpy()
        elif geoms is not None:
            from shapely import STRtree
            tree = STRtree(crowns.geometry.values)
            for g in geoms:
                hit[tree.query(g, predicate="intersects")] = True
        excl |= hit
        excl_notes.append(f"{note} -> {int(hit.sum()):,} crowns matched")
        print(f"  exclude {excl_notes[-1]}")
    if need_exclusion and not excl.any():
        raise SystemExit(
            "REFUSING: an arm is contaminated (add-canopy overlay) but the exclusion "
            "sources matched ZERO crowns — the correction did not apply. Check "
            f"{STABLE_CROWNS} and {FOREST_SITE}.")

    # ── sectors (optional) ────────────────────────────────────────────────────
    sector = np.array(["(none)"] * len(crowns), dtype=object)
    spath = Path(args.sectors) if args.sectors else (SECTORS_DIR / "sectors_v1.gpkg")
    if spath.exists():
        try:
            sec = gpd.read_file(spath, layer="sectors", engine="pyogrio")
            if sec.crs is not None and sec.crs != crowns.crs:
                sec = sec.to_crs(crowns.crs)
            from shapely import STRtree
            tree = STRtree(crowns.geometry.values)
            key = "id" if "id" in sec.columns else sec.columns[0]
            for _, r in sec.iterrows():
                idx = tree.query(r.geometry, predicate="intersects")
                fresh = idx[sector[idx] == "(none)"]
                sector[fresh] = str(r[key])
            print(f"[crown-touch] sectors: {spath.name} "
                  f"({int((sector != '(none)').sum()):,} crowns inside a sector)")
        except Exception as e:                            # noqa: BLE001
            print(f"[crown-touch] sector join skipped: {type(e).__name__}: {e}")
    else:
        print(f"[crown-touch] no sector layer at {spath} — sector table omitted")

    # ── the pass ──────────────────────────────────────────────────────────────
    hist, n_rast, valid_px, pos, neg, scorable_px = _accumulate(
        paths, tags, crowns, args.block_rows, args.all_touched,
        args.ref, args.ref_scheme, args.ref_map)

    # Identical for every arm by construction — `valid` is the intersection — but
    # assert it rather than trust it: the whole comparison rests on one crown set.
    n_valid = hist[tags[0]].sum(axis=1).astype(np.int64)
    for t in tags[1:]:
        assert np.array_equal(hist[t].sum(axis=1).astype(np.int64), n_valid), \
            "arms disagree on per-crown valid pixel counts — footprint is not shared"

    with np.errstate(divide="ignore", invalid="ignore"):
        vfrac = np.where(n_rast > 0, n_valid / np.maximum(n_rast, 1), 0.0)
    keep = (n_rast >= args.min_rast_px) & (vfrac >= args.min_valid_frac) & ~excl
    dropped_zero_rast = int((n_rast < args.min_rast_px).sum())
    dropped_footprint = int(((n_rast >= args.min_rast_px) & (vfrac < args.min_valid_frac)).sum())
    dropped_excl = int((excl & (n_rast >= args.min_rast_px)
                        & (vfrac >= args.min_valid_frac)).sum())

    # ── thresholds ────────────────────────────────────────────────────────────
    curves = None
    if args.ref:
        curves = {t: AP._curve_from_hists(pos[t][:255], neg[t][:255]) for t in tags}
    cuts, reasons = {}, {}
    if args.thresh is not None:
        for t in tags:
            cuts[t] = int(round(args.thresh * 254))
            reasons[t] = f"explicit --thresh {args.thresh:.4f}"
    else:
        ry, _, rt = args.match_precision_to.partition("/")
        if ry != args.year:
            raise SystemExit(f"--match-precision-to year {ry} != --year {args.year}; "
                             "arms of different years are not on one grid.")
        if rt not in tags:
            raise SystemExit(f"--match-precision-to tag '{rt}' is not among --tags")
        i_ref = int(round(args.ref_thresh * 254))
        tgt = float(curves[rt]["precision"][i_ref])
        print(f"[crown-touch] matching precision to {rt}@{args.ref_thresh}: {tgt:.4f}")
        for t in tags:
            hit = AP._at_precision(curves[t], tgt)
            if hit is None:
                raise SystemExit(f"arm '{t}' cannot reach precision {tgt:.4f}")
            cuts[t] = int(round(hit[2] * 254))
            reasons[t] = (f"matched to `{rt}`@{args.ref_thresh:.2f} "
                          f"(precision {tgt:.4f}); thr {hit[2]:.4f}, "
                          f"pixel recall {hit[0]:.4f}")

    # ── per-crown results ─────────────────────────────────────────────────────
    res = {}
    for t in tags:
        npred = _pred_counts(hist[t], cuts[t])
        with np.errstate(divide="ignore", invalid="ignore"):
            cov = np.where(n_valid > 0, npred / np.maximum(n_valid, 1), np.nan)
        res[t] = dict(npred=npred, cover=cov, touch=npred > 0)

    K = np.flatnonzero(keep)
    px_true_m2 = px_area_crs_units * float(np.cos(np.radians(47.81))) ** 2 \
        if str(crs0).endswith("3857") else px_area_crs_units

    L, A = [], None
    A = L.append
    A(f"# Per-crown TOUCH / COVER — {args.year}, arms {', '.join('`'+t+'`' for t in tags)}\n")
    A("## Read this before quoting a number\n")
    A("**This is not ground truth.** The crown layer is itself model output — phase 0 "
      "instance segmentation anchored to the 2020 hand annotations — not hand-drawn "
      "truth.\n")
    A("**Shared ancestry.** The crown layer (phase 0) and `MASK_2020` "
      "(`phase3/edmonds_canopy_mask_2020.tif`, the training key here) BOTH descend from "
      "the same 2020 hand annotations. Independence is at the LABEL-PATHWAY level — "
      "these crowns never entered these models' training labels — not total independence.\n")
    A(f"**Temporal confound.** 2020 crowns scored against {args.year} predictions makes "
      f"real {args.year}->2020 planting count as model error, and real removal count as "
      f"model credit. Same family as CLAUDE.md rule 5's circularity ban. Therefore "
      f"**absolute touch rates and cover fractions are NOT quotable**; only the "
      f"ARM-vs-ARM delta on the identical crown set below is interpretable.\n")
    A("## Provenance gate (read from each arm's own run manifest, not a tag list)\n")
    A("| arm | status | evidence |")
    A("|---|---|---|")
    for t in tags:
        pv = prov[t]
        A(f"| `{t}` | **{pv['status']}** | {pv['detail']} |")
    A("")
    for t in tags:
        A(f"- `{t}` manifest: `{prov[t]['manifest']}`")
    A("")
    if excl_notes:
        A("**Exclusion applied** (an arm's manifest showed an add-canopy overlay whose "
          "force-canopy code is rasterised crown polygons — "
          "`qc/build_groves_overlay.py:72,293,343`):\n")
        for nte in excl_notes:
            A(f"- {nte}")
        A(f"\nTotal crowns excluded as CONTAMINATED: **{int(excl.sum()):,}** "
          f"({dropped_excl:,} of them would otherwise have passed the footprint gate). "
          f"They were trained as FORCED CANOPY, so unexcluded they score ~1.0 by "
          f"construction and flatter that arm.\n")
    else:
        A("**No exclusion needed** — every arm's manifest shows the plain citywide "
          "2020-mask recipe with no add-canopy overlay, so the crown layer is fully "
          "held out for all of them.\n")
    A("## Footprint\n")
    A(f"- Common valid footprint (INTERSECTION of `!= 255` across all arms): "
      f"**{valid_px:,} px** = {valid_px * px_true_m2 / 1e4:,.1f} ha true")
    if args.ref:
        A(f"- Of which scorable against the reference (curve/threshold work only): "
          f"{scorable_px:,} px")
    A(f"- Crown gate: in-grid pixels >= {args.min_rast_px} AND valid fraction "
      f"(`n_valid / n_rast`) >= {args.min_valid_frac:.2f}, so only crowns genuinely "
      f"inside the scored footprint count. Rasterisation `all_touched="
      f"{bool(args.all_touched)}`.")
    A(f"- Crowns loaded {len(crowns):,} -> dropped {dropped_zero_rast:,} with no "
      f"in-grid pixels, {dropped_footprint:,} outside/partly outside the footprint, "
      f"{dropped_excl:,} contaminated -> **{int(keep.sum()):,} scored**.")
    A("- AOI-restricted inference writes at BLOCK granularity (WORKPLAN 1.5, "
      "'AOI block-leak'), so valid pixels extend beyond the sector rects; the sector "
      "table below separates in-sector crowns from leaked-block crowns.\n")
    A("## Thresholds — one per arm, and why\n")
    A("| arm | threshold | DN cut | reason |")
    A("|---|---|---|---|")
    for t in tags:
        A(f"| `{t}` | {cuts[t]/254:.4f} | {cuts[t]} | {reasons[t]} |")
    A("")
    if curves is not None:
        i50 = int(round(0.5 * 254))
        A("### Pixel-curve self-check (imported machinery — compare to "
          "`arm_pr_curves_{year}.md`)\n".replace("{year}", str(args.year)))
        A("| arm | AUROC | PR-AUC (AP) | pixel recall@0.5 | pixel precision@0.5 |")
        A("|---|---|---|---|---|")
        for t in tags:
            c = curves[t]
            A(f"| `{t}` | {c['auroc']:.4f} | {c['ap']:.4f} | "
              f"{c['recall'][i50]:.4f} | {c['precision'][i50]:.4f} |")
        A("")
    A("## Overall (identical crown set for every arm)\n")
    A(HDR)
    A(SEP)
    for t in tags:
        A(_row(f"`{t}`", _stats(res[t]["cover"][K], res[t]["touch"][K])))
    A("")
    A(f"## By RECOMPUTED size class (TRUE {AREA_CRS} area — the stored `area_m2` and "
      f"`size_class` are Web-Mercator-inflated 2.2215x and are NOT used)\n")
    A("Bins are true m², with the equivalent circular diameter in brackets.\n")
    for t in tags:
        A(f"**`{t}`**\n")
        A(HDR)
        A(SEP)
        for i, lb in enumerate(size_lbl):
            sel = K[size_idx[K] == i]
            d0 = 2.0 * np.sqrt(SIZE_BINS[i] / np.pi)
            d1 = (2.0 * np.sqrt(SIZE_BINS[i+1] / np.pi)
                  if np.isfinite(SIZE_BINS[i+1]) else float("inf"))
            nm = (f"{lb} m² [{d0:.1f}-{d1:.1f} m]" if np.isfinite(d1)
                  else f"{lb} m² [>={d0:.1f} m]")
            A(_row(nm, _stats(res[t]["cover"][sel], res[t]["touch"][sel])))
        A("")
    secs = sorted(set(sector[K].tolist()))
    if len(secs) > 1:
        A("## By sector ( `(none)` = AOI block-leak ground, outside the sector rects )\n")
        for t in tags:
            A(f"**`{t}`**\n")
            A(HDR)
            A(SEP)
            for s in secs:
                sel = K[sector[K] == s]
                A(_row(s, _stats(res[t]["cover"][sel], res[t]["touch"][sel])))
            A("")
    if len(tags) == 2:
        a, b = tags
        ta, tb = res[a]["touch"][K], res[b]["touch"][K]
        ca, cb = res[a]["cover"][K], res[b]["cover"][K]
        A("## PAIRED comparison — the same crowns, both arms\n")
        A("Aggregate rates can agree while the two arms disagree crown by crown. "
          "These are the discordant counts (McNemar-style).\n")
        A(f"| stratum | crowns | touch: `{a}` only | touch: `{b}` only | McNemar z "
          f"(touch) | cover>=0.5: `{a}` only | cover>=0.5: `{b}` only | mean cover "
          f"delta (`{b}`-`{a}`) |")
        A("|---|---|---|---|---|---|---|---|")

        def prow(nm, sel_local):
            if sel_local.size == 0:
                return f"| {nm} | 0 | — | — | — | — | — | — |"
            A_ = ta[sel_local]; B_ = tb[sel_local]
            ca_ = ca[sel_local] >= 0.5; cb_ = cb[sel_local] >= 0.5
            n01, n10 = int((A_ & ~B_).sum()), int((B_ & ~A_).sum())
            z = (n01 - n10) / np.sqrt(max(n01 + n10, 1))
            dl = float(np.nanmean(cb[sel_local] - ca[sel_local]))
            return (f"| {nm} | {sel_local.size:,} | {n01:,} | {n10:,} | {z:+.2f} | "
                    f"{int((ca_ & ~cb_).sum()):,} | {int((cb_ & ~ca_).sum()):,} | "
                    f"{dl:+.4f} |")

        A(prow("ALL", np.arange(K.size)))
        for i, lb in enumerate(size_lbl):
            A(prow(f"{lb} m²", np.flatnonzero(size_idx[K] == i)))
        A("")
        A("The McNemar z is **NOMINAL and overstated**: it assumes crowns are "
          "independent samples, and they are not — crowns are spatially clustered "
          "and CLAUDE.md rule 5 puts the effective independent sample size at ~5 "
          "sites, not tens of thousands. Use it to read the SIGN and the "
          "concentration across strata, never as a p-value. The cluster-level test "
          "below is the honest one.\n")
        if len(secs) > 1:
            import math
            A("### Cluster-level check — one paired delta per sector\n")
            A(f"| sector | crowns | touch `{a}` | touch `{b}` | delta | "
              f"mean cover `{a}` | mean cover `{b}` | delta |")
            A("|---|---|---|---|---|---|---|---|")
            dts = []
            for s in secs:
                # LOCAL positions: ta/tb/ca/cb are already the K subset.
                loc = np.flatnonzero(sector[K] == s)
                if loc.size == 0:
                    continue
                t1, t2 = float(ta[loc].mean()), float(tb[loc].mean())
                m1, m2 = float(np.nanmean(ca[loc])), float(np.nanmean(cb[loc]))
                dts.append(t2 - t1)
                A(f"| {s} | {loc.size:,} | {t1:.4f} | {t2:.4f} | {t2-t1:+.4f} | "
                  f"{m1:.4f} | {m2:.4f} | {m2-m1:+.4f} |")
            def _sign_p(v):
                v = np.asarray(v)
                nn, NN = int((v < 0).sum()), int(v.size)
                if NN == 0:
                    return 0, 0, 1.0
                pp = min(1.0, 2 * sum(math.comb(NN, i)
                                      for i in range(max(nn, NN - nn), NN + 1)) / 2 ** NN)
                return nn, NN, pp

            real = [d for s, d in zip([s for s in secs
                                       if np.flatnonzero(sector[K] == s).size], dts)
                    if s != "(none)"]
            neg, N, p = _sign_p(dts)
            rneg, rN, rp = _sign_p(real)
            A("")
            A(f"**Sign test over sector-level paired deltas — the honest test.** It "
              f"respects the spatial clustering the McNemar z ignores.\n")
            A(f"- Over the **{rN} designed sectors**: `{b}` has the lower touch rate in "
              f"**{rneg} of {rN}**, two-sided p = **{rp:.4f}**. *This is the number to "
              f"quote.*")
            A(f"- Including the `(none)` AOI-leak bucket ({neg} of {N}, p = {p:.4f}) — "
              f"reported for completeness only; leaked blocks are ground adjacent to "
              f"the same sectors, not an independent cluster, so this p is optimistic.\n")
            A("**What this sign test CANNOT tell you.** It clusters on SPACE, not on "
              "TRAINING RUNS — and there is exactly ONE run per arm here. A single "
              "training run that landed slightly low by seed is worse in *every* "
              "sector, so spatial consistency cannot separate 'this recipe is worse' "
              "from 'this run is worse'. The rerun noise floor (recall sd .0100, n=5, "
              "same seed — itself a LOWER bound) is the scale the recipe-level question "
              "lives on, and it is not measured by anything on this page. Treat the "
              "sign test as evidence about THESE TWO RASTERS, and leave the recipe "
              "verdict where the pre-registered read put it.\n")
    A("---\n")
    A(f"Generated by `qc/phase4_crown_touch.py`. Crown layer: `{cpath}`. "
      f"Analysis only — writes no row to `qc_indep_report.csv`.")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md = "\n".join(L)
    (out / f"crown_touch_{args.year}.md").write_text(md, encoding="utf-8")
    print("\n" + md)

    df = pd.DataFrame({
        "crown_id": cid[K], "sector": sector[K],
        "area_true_m2": np.round(true_area[K], 3),
        "diam_true_m": np.round(diam[K], 3),
        "size_bin": size_lbl[size_idx[K]],
        "area_m2_stored_INFLATED": (stored[K] if stored is not None else np.nan),
        "n_rast_px": n_rast[K], "n_valid_px": n_valid[K],
    })
    for t in tags:
        sfx = t if t else "untagged"
        df[f"npred_{sfx}"] = res[t]["npred"][K]
        df[f"cover_{sfx}"] = np.round(res[t]["cover"][K], 6)
        df[f"touch_{sfx}"] = res[t]["touch"][K].astype(int)
    dest = out / f"crown_touch_{args.year}_percrown.csv"
    df.to_csv(dest, index=False)
    print(f"\n[crown-touch] per-crown -> {dest} ({len(df):,} rows)")
    print(f"[crown-touch] report    -> {out / f'crown_touch_{args.year}.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
