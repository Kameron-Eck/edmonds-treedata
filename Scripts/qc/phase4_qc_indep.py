"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: score the model against an INDEPENDENT canopy reference
  Edmonds Temporal Active Learning Pipeline

  WHY
    Every recall number to date is CIRCULAR — scored against the 2020 model
    mask reprojected onto another year, or against the NDVI+CHM proxy that
    shares its CHM axis with two of the models being ranked. This scorer takes
    a reference that never saw the model or the 2020 labels and produces the
    first NON-circular numbers.

    NOAA C-CAP 2016 1 m land cover is the Edmonds reference — a free stand-in
    for hand-drawn validation polygons. But this scorer is REFERENCE-AGNOSTIC:
    it works equally on hand-drawn canopy polygons or photo-interp points
    rasterized elsewhere. C-CAP is EVALUATION ONLY — it is NEVER a training or
    label source, so the pipeline stays reproducible where no C-CAP exists.

  WHAT IT DOES
    - maps a categorical reference's classes → land-cover GROUPS (C-CAP default
      below; overridable via --ref-map; or --ref-scheme binary for a 0/1 mask),
    - reprojects the reference onto the year's model-prob grid (nearest —
      categorical-safe) window-by-window,
    - scores canopy recall/precision under THREE nested canopy definitions
      (forest_only ⊆ forest_wetland ⊆ forest_wetland_scrub), and
    - delineates EVERY surface group: the model's canopy-call rate is RECALL for
      canopy groups and the FALSE-POSITIVE rate for non-canopy groups (grass,
      developed, bare, water …) — so both misses and false alarms are attributed
      by surface type, not lumped into one precision number.

  DEFINITIONS
    recall(def)      = TP / ref_canopy(def)              <-- headline, non-circular
    precision(def)   = TP / (TP + FP)   FP = model-canopy on any non-canopy group
    grass_reject     = 1 - (model-canopy on ref-grass / ref-grass)   (want ~0.99)
    canopy-call rate = model-canopy px / group px        (per surface group)

  PRODUCES (phase4/qc/):
    qc_indep_report.csv        one row per (year, ref, canopy_def, thresh)
    qc_indep_surfaces_{year}.csv   one row per surface group (the breakout)
    qc_indep_{year}.txt        human-readable: class map + 3 defs + per-surface
                               table + threshold sweep
    Never overwrites qc_report.csv (NDVI), semantic_eval_report.csv (circular),
    or flicker_report.csv.

  USAGE (local Windows or Colab; rasterio auto-installs; torch-free):
    py -3.12 phase4_qc_indep.py --year 2016 --ref <ccap.tif>
    py -3.12 phase4_qc_indep.py --year 2016 --ref <ccap.tif> --prob <variant.tif> --thresh 0.38
    py -3.12 phase4_qc_indep.py --year 2016 --ref <polys.tif> --ref-scheme binary
    py -3.12 phase4_qc_indep.py --year 2016 --ref <ccap.tif> --ref-map my_codes.json
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import re as _re
import json
import sys
from pathlib import Path



# Dep bootstrap: mechanism in phase4seg/deps.py (refactor 2.3); the LIST stays
# per-file — nine distinct sets exist and one shared list would over-install.
# KERNEL-EXEC KEEP (Canary 1, 2026-08-31): this file is exec'd BY PATH inside the
# Colab kernel, where the editable install is INVISIBLE - pip -e works via a .pth
# file and site.py reads .pth only at interpreter STARTUP, so a kernel that was
# already running when the bootstrap installed never sees it. Subprocesses re-run
# site startup and do see it - measured on canary3b: the engine steps imported
# phase4seg fine while this file's kernel-level import raised ModuleNotFoundError.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.deps import ensure_deps as _ensure_deps  # noqa: E402
_ensure_deps([("rasterio", "rasterio"), ("numpy", "numpy")])

import warnings
warnings.filterwarnings("ignore", message="Setting the shape on a NumPy array",
                        category=DeprecationWarning)  # rasterio read + numpy 2.5

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.windows import Window
from pipeline_log import write_step_log


# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402

QC_DIR   = BASE / "phase4" / "qc"
MASKS    = BASE / "phase4" / "masks"
EVAL_CSV = BASE / "phase4" / "eval" / "semantic_eval_report.csv"
LOGS_DIR = BASE / "phase4" / "logs"

SWEEP_THRESHOLDS = [0.20, 0.25, 0.30, 0.3767, 0.45, 0.50]

# ── DEFAULT reference map: NOAA C-CAP 25-class standard legend ─────────────────
# VERIFY these codes against the legend shipped with the actual C-CAP raster —
# printed on every run so a mismatch is caught immediately. Fully overridable via
# --ref-map (same JSON shape). Groups drive both the canopy definitions and the
# per-surface breakout.
CCAP_DEFAULT = {
    "groups": {
        # canopy (woody, tall) — the recall reference
        "forest":            [9, 10, 11],       # Deciduous / Evergreen / Mixed Forest
        "wetland":           [13, 16],          # Palustrine / Estuarine Forested Wetland
        "scrub":             [12, 14, 17],      # Scrub/Shrub (+ scrub-shrub wetland)
        # non-canopy surfaces — each scored & reported separately
        "grass":             [5, 7, 8],         # Developed Open Space / Pasture-Hay / Grassland
        "cropland":          [6],               # Cultivated
        "developed":         [2, 3, 4],         # High / Medium / Low Intensity Developed
        "barren":            [19, 20],          # Unconsolidated Shore / Bare Land
        "emergent_wetland":  [15, 18],          # Palustrine / Estuarine Emergent Wetland
        "water":             [21, 22, 23],      # Open Water / Aquatic Bed
        # excluded from scoring entirely
        "ignore":            [0, 1, 24, 25],    # Background / Unclassified / Tundra / Snow-Ice
    },
    "canopy_order": ["forest", "wetland", "scrub"],   # cumulative nesting order
    "grass_group": "grass",
}


# ── helpers copied from phase4_qc_score.py (scripts are standalone) ────────────
def _safe(n, d):
    return n / d if d else float("nan")


def resolve_prob(year, override=None):
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"--prob raster not found: {p}")
        return p
    for c in (MASKS / f"edmonds_canopy_prob_{year}.tif",
              BASE / "phase5" / "masks" / f"edmonds_canopy_prob_{year}.tif"):
        if c.exists():
            return c
    raise FileNotFoundError(f"prob raster for {year} not found under {MASKS} "
                            f"(pass --prob to score an archived variant)")


def deployed_threshold(year, channels_pref=("rgb+chm", "rgb+struct", "rgb")):
    """Read the deployed op-threshold from the (circular) eval CSV — torch-free."""
    if not EVAL_CSV.exists():
        return None
    rows = [r for r in csv.DictReader(open(EVAL_CSV, encoding="utf-8"))
            if r.get("year") == str(year) and r.get("scope", "").upper() == "OVERALL"]
    for ch in channels_pref:
        for r in rows:
            if r.get("channels") == ch:
                for key in ("op_thresh", "best_f1_thresh"):
                    v = r.get(key, "").strip()
                    if v:
                        return float(v), ch
    return None


# ── reference-map plumbing ────────────────────────────────────────────────────
def load_ref_map(ref_scheme, ref_map_path):
    """Return (group_names, canopy_order, grass_group, code_to_group_dict).
    For 'binary' the returned dict is None (values, not codes, decide group)."""
    if ref_scheme == "binary":
        return (["canopy", "other", "ignore"], ["canopy"], None, None)

    spec = CCAP_DEFAULT
    if ref_map_path:
        spec = json.loads(Path(ref_map_path).read_text(encoding="utf-8"))
    groups = spec["groups"]
    canopy_order = spec.get("canopy_order",
                            [g for g in ("forest", "wetland", "scrub") if g in groups])
    grass_group = spec.get("grass_group", "grass" if "grass" in groups else None)

    names = list(groups.keys())
    for g in ("other", "ignore"):
        if g not in names:
            names.append(g)
    code_to_group = {}
    for g, codes in groups.items():
        for c in codes:
            code_to_group[int(c)] = g
    return names, canopy_order, grass_group, code_to_group


def build_lut(names, code_to_group):
    """256-entry code→group-index LUT; unmapped codes → 'other'."""
    other_id = names.index("other")
    lut = np.full(256, other_id, dtype=np.int16)
    for code, g in code_to_group.items():
        if 0 <= code < 256:
            lut[code] = names.index(g)
    return lut


def canopy_definitions(canopy_order):
    """Cumulative nested definitions: [(name, set(groups)), …]."""
    defs, acc = [], []
    for g in canopy_order:
        acc = acc + [g]
        name = f"{acc[0]}_only" if len(acc) == 1 else "_".join(acc)
        defs.append((name, set(acc)))
    return defs


# ── core scoring ──────────────────────────────────────────────────────────────
class QCUnscorableError(RuntimeError):
    """The inputs cannot yield an honest score. NEVER downgrade this to a nan row."""


def _preflight_prob(year, prob_path, min_valid_frac, sample=2000):
    """Cheap decimated check that the prob raster holds real predictions.

    Catches the 2017 failure mode (96.5% nodata + probabilities collapsed near 0)
    in seconds instead of after a full block scan.
    """
    with rasterio.open(prob_path) as p:
        if p.count < 1 or p.width == 0 or p.height == 0:
            raise QCUnscorableError(f"year {year}: {prob_path} is empty/unreadable.")
        h = min(sample, p.height)
        w = max(1, int(p.width * h / p.height))
        a = p.read(1, out_shape=(h, w), resampling=Resampling.nearest)
    valid = a != 255
    frac = float(valid.mean())
    if frac < min_valid_frac:
        raise QCUnscorableError(
            f"year {year}: prob raster is {100*(1-frac):.1f}% NODATA "
            f"(only {frac:.2%} valid, below --min-valid-frac {min_valid_frac:.2%}).\n"
            f"    prob = {prob_path}\n"
            f"  This is a FAILED INFERENCE RUN, not a scoring problem. Re-run inference.\n"
            f"  (Detected on a decimated preflight — no full scan was wasted.)")
    if valid.any():
        mx = float(a[valid].max()) / 254.0
        if mx < 0.5:
            print(f"[qc-indep] WARNING: max probability anywhere is {mx:.3f} — the model "
                  f"never confidently predicts canopy in {year}. Suspect a broken run.",
                  file=sys.stderr)
    print(f"[qc-indep] preflight: prob {frac:.1%} valid — OK")


def score(year, ref_path, prob_path, thresh, ref_scheme, ref_map_path, block_rows,
          min_valid_frac=0.05):
    names, canopy_order, grass_group, code_to_group = load_ref_map(ref_scheme, ref_map_path)
    ignore_id = names.index("ignore")
    lut = build_lut(names, code_to_group) if ref_scheme != "binary" else None
    defs = canopy_definitions(canopy_order)

    print(f"[qc-indep] year={year}  scheme={ref_scheme}")
    print(f"    ref  = {ref_path}")
    print(f"    prob = {prob_path}")
    print(f"    canopy definitions: {[d[0] for d in defs]}")

    thr_u8 = thresh * 254.0

    # PREFLIGHT — estimate the prob raster's valid fraction from a decimated read
    # BEFORE spending an hour block-scanning a raster that is mostly nodata.
    _preflight_prob(year, prob_path, min_valid_frac)

    with rasterio.open(ref_path) as _r:
        ref_nodata = _r.nodata
    ref_src = rasterio.open(ref_path)

    with rasterio.open(prob_path) as prob:
        H, W = prob.height, prob.width
        rx, ry = prob.res
        # pixel area in TRUE m² — prob CRS units may be feet (EPSG:2285 = US survey ft),
        # so convert via the CRS unit factor before estimating independent 1 m² cells.
        m_per_unit = 1.0
        try:
            from pyproj import CRS as _pyCRS
            _c = _pyCRS.from_user_input(prob.crs)
            if _c.is_projected:
                m_per_unit = float(_c.axis_info[0].unit_conversion_factor)
        except Exception:
            pass
        px_area = abs(rx * ry) * (m_per_unit ** 2)   # prob-grid pixel area in m²

        # per-group accumulators (valid px only)
        gpx = {g: 0 for g in names}                  # group px
        gmc = {g: 0 for g in names}                  # group px the model calls canopy
        valid_total = 0
        # sweep on the PRIMARY definition (forest_wetland if present else last)
        primary_idx = 1 if len(defs) >= 2 else 0
        primary_groups = defs[primary_idx][1]
        sweep = {round(t, 4): dict(tp=0, fn=0, fp=0) for t in SWEEP_THRESHOLDS}

        with WarpedVRT(ref_src, crs=prob.crs, transform=prob.transform,
                       width=W, height=H, resampling=Resampling.nearest) as ref_vrt:
            n_blocks = (H + block_rows - 1) // block_rows
            for bi, row0 in enumerate(range(0, H, block_rows)):
                rows = min(block_rows, H - row0)
                win = Window(0, row0, W, rows)
                pr = prob.read(1, window=win)
                rc = ref_vrt.read(1, window=win)

                # group id per pixel
                if ref_scheme == "binary":
                    gid = np.full(pr.shape, names.index("other"), dtype=np.int16)
                    gid[rc > 0] = names.index("canopy")
                    if ref_nodata is not None:
                        gid[rc == ref_nodata] = ignore_id
                    gid[rc == 0] = names.index("other")
                    if ref_nodata == 0:
                        gid[rc == 0] = ignore_id     # 0 was nodata, not 'other'
                else:
                    codes = np.clip(rc.astype(np.int64), 0, 255)
                    gid = lut[codes]
                    if ref_nodata is not None and 0 <= int(ref_nodata) < 256:
                        gid[rc == ref_nodata] = ignore_id

                valid = (gid != ignore_id) & (pr != 255)
                if not valid.any():
                    if bi % 5 == 0 or bi == n_blocks - 1:
                        print(f"    block {bi+1}/{n_blocks}", flush=True)
                    continue
                mc = valid & (pr >= thr_u8)          # model canopy @ deployed thr
                valid_total += int(valid.sum())

                for gi, g in enumerate(names):
                    gmask = valid & (gid == gi)
                    n = int(gmask.sum())
                    if n:
                        gpx[g] += n
                        gmc[g] += int((gmask & mc).sum())

                # sweep on primary canopy def
                prim = valid & np.isin(gid, [names.index(g) for g in primary_groups])
                for t in sweep:
                    mct = valid & (pr >= t * 254.0)
                    sweep[t]["tp"] += int((prim & mct).sum())
                    sweep[t]["fn"] += int((prim & ~mct).sum())
                    sweep[t]["fp"] += int((~prim & mct & valid).sum())

                if bi % 5 == 0 or bi == n_blocks - 1:
                    print(f"    block {bi+1}/{n_blocks}", flush=True)

    ref_src.close()

    # ── FAIL LOUD ────────────────────────────────────────────────────────────
    # A scorer that writes `nan` on empty overlap manufactures the illusion of a
    # measurement. 2017 did exactly that: a 96.5%-nodata prob raster (a failed
    # inference run) was reported as a nan row instead of an error, and sat in
    # qc_indep_report.csv looking like a scored year. Refuse instead.
    total_px = H * W
    frac = valid_total / total_px if total_px else 0.0
    if valid_total == 0:
        raise QCUnscorableError(
            f"year {year}: ZERO valid px — nothing overlaps between\n"
            f"    prob = {prob_path}\n    ref  = {ref_path}\n"
            f"  Check (a) the prob raster is not all-nodata (a failed inference run),\n"
            f"        (b) the two rasters actually overlap on the ground.\n"
            f"  No row written — an unscorable year must not look like a scored one.")
    if frac < min_valid_frac:
        raise QCUnscorableError(
            f"year {year}: only {frac:.2%} of the prob raster is valid "
            f"({valid_total:,} / {total_px:,} px), below --min-valid-frac "
            f"{min_valid_frac:.2%}.\n    prob = {prob_path}\n"
            f"  This usually means the inference run failed or covered only a strip.\n"
            f"  Re-run inference, or pass --min-valid-frac to score it deliberately.")
    print(f"[qc-indep] valid {valid_total:,} / {total_px:,} px ({frac:.1%}) — OK")

    indep_cells = valid_total * px_area / 1.0        # ≈ independent 1 m² C-CAP cells
    result = dict(names=names, defs=defs, primary_idx=primary_idx,
                  grass_group=grass_group, gpx=gpx, gmc=gmc,
                  valid=valid_total, indep_cells=indep_cells, thr=thr_u8)
    _report(year, ref_path, prob_path, thresh, ref_scheme, result, sweep)
    return result


def _report(year, ref_path, prob_path, thresh, ref_scheme, R, sweep):
    names, defs = R["names"], R["defs"]
    gpx, gmc = R["gpx"], R["gmc"]
    valid = R["valid"]
    grass_group = R["grass_group"]
    model_canopy_total = sum(gmc.values())
    canopy_groups_all = set().union(*[d[1] for d in defs]) if defs else set()

    # per-definition recall / precision
    def_rows = []
    for i, (dname, dgroups) in enumerate(defs):
        ref_can = sum(gpx[g] for g in dgroups)
        tp = sum(gmc[g] for g in dgroups)
        fn = ref_can - tp
        fp = model_canopy_total - tp                 # model canopy on any non-def group
        recall = _safe(tp, ref_can)
        precision = _safe(tp, tp + fp)
        gr = (_safe(gpx[grass_group] - gmc[grass_group], gpx[grass_group])
              if grass_group and grass_group in gpx else float("nan"))
        def_rows.append(dict(name=dname, ref_canopy=ref_can, tp=tp, fn=fn, fp=fp,
                             recall=recall, precision=precision, grass_reject=gr,
                             primary=(i == R["primary_idx"])))

    # per-surface breakout: canopy-call rate = recall (canopy) or FP-rate (else)
    surf_rows = []
    for g in names:
        if g == "ignore":
            continue
        rate = _safe(gmc[g], gpx[g])
        kind = "canopy" if g in canopy_groups_all else "non-canopy"
        surf_rows.append(dict(group=g, kind=kind, px=gpx[g],
                              area_pct=100 * _safe(gpx[g], valid), call_rate=rate))

    # ── text report ──
    L = []
    L.append(f"QC score vs INDEPENDENT reference — year {year}")
    L.append(f"  ref  : {ref_path}   (scheme={ref_scheme})")
    L.append(f"  prob : {prob_path}")
    L.append(f"  deployed threshold : {thresh}")
    L.append(f"  valid px           : {valid:,}   (≈ {R['indep_cells']:,.0f} independent 1 m² cells)")
    L.append(f"  model canopy frac  : {100*_safe(model_canopy_total, valid):.2f}%")
    L.append("")
    L.append("  CANOPY DEFINITIONS (nested):")
    L.append("    definition             recall   precision   grass_rej   ref_canopy%   TP / FN(missed)")
    for r in def_rows:
        tag = "  <-- PRIMARY" if r["primary"] else ""
        L.append(f"    {r['name']:<21}  {r['recall']:>6.4f}   {r['precision']:>7.4f}   "
                 f"{r['grass_reject']:>7.4f}   {100*_safe(r['ref_canopy'], valid):>9.2f}%   "
                 f"{r['tp']:,} / {r['fn']:,}{tag}")
    L.append("")
    L.append("  PER-SURFACE DELINEATION (canopy-call rate = recall for canopy, FP-rate otherwise):")
    L.append("    group                kind         px          area%    canopy-call")
    for s in surf_rows:
        note = "recall" if s["kind"] == "canopy" else "FP-rate"
        L.append(f"    {s['group']:<19}  {s['kind']:<11}  {s['px']:>12,}  {s['area_pct']:>6.2f}%   "
                 f"{s['call_rate']:>7.4f} ({note})")
    L.append("")
    L.append("  THRESHOLD SWEEP (primary def = " + defs[R["primary_idx"]][0] + "):")
    L.append("    thresh    recall   precision   TP / missed")
    for t in sorted(sweep):
        s = sweep[t]
        rec = _safe(s["tp"], s["tp"] + s["fn"])
        prc = _safe(s["tp"], s["tp"] + s["fp"])
        L.append(f"    {t:<7.4f}  {rec:>6.4f}   {prc:>7.4f}     {s['tp']:,} / {s['fn']:,}")
    L.append("")
    L.append("  CLASS MAP USED (audit — VERIFY vs the reference's own legend):")
    L.append(f"    canopy order : {[d[0] for d in defs]}")
    L.append(f"    grass group  : {grass_group}")
    txt = "\n".join(L)
    print("\n" + txt)

    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"qc_indep_{year}.txt").write_text(txt, encoding="utf-8")
    # run_tag column mirrors the arm parsed from the prob filename — before
    # 2026-08-26 it silently defaulted to '' for --prob overrides, mislabeling
    # tagged arms as the untagged lineage in the human-readable column (the
    # supersede logic was unaffected: it parses the prob filename itself).
    _write_csvs(year, ref_path, prob_path, thresh, def_rows, surf_rows, R,
                run_tag=_prob_arm(prob_path.name))
    print(f"\n[qc-indep] wrote {QC_DIR / f'qc_indep_{year}.txt'}")


def _prob_arm(name):
    m = _re.search(r"prob_[0-9a-z]+_(.+)\.tif", name or "")
    return m.group(1) if m else ""


def _write_csvs(year, ref_path, prob_path, thresh, def_rows, surf_rows, R, run_tag=""):
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Main per-definition CSV.
    #
    # HISTORY IS KEPT, but exactly one row per (year, ref, canopy_def) is LIVE.
    # The old de-dupe keyed on (year, ref, prob, thresh), so a re-run against a
    # different prob raster or threshold ADDED a row instead of replacing one —
    # which is how 2015 ended up showing recall .257 beside .62, and 2016 four
    # rows (two of them nan), with nothing saying which to quote. Superseding is
    # now explicit: live=1 on the newest, live=0 on everything it replaces.
    main = QC_DIR / "qc_indep_report.csv"
    fields = ["year", "ref", "prob", "canopy_def", "thresh", "recall", "precision",
              "grass_reject", "tp", "fn", "fp", "ref_canopy", "valid",
              "indep_1m_cells", "primary", "live", "run_tag", "ts"]
    new = []
    for r in def_rows:
        new.append(dict(year=year, ref=ref_path.name, prob=prob_path.name,
                        canopy_def=r["name"], thresh=thresh,
                        recall=round(r["recall"], 4), precision=round(r["precision"], 4),
                        grass_reject=round(r["grass_reject"], 4),
                        tp=r["tp"], fn=r["fn"], fp=r["fp"], ref_canopy=r["ref_canopy"],
                        valid=R["valid"], indep_1m_cells=round(R["indep_cells"]),
                        primary=int(r["primary"]), live=1, run_tag=run_tag, ts=ts))
    keep, n_sup = [], 0
    if main.exists():
        for row in csv.DictReader(open(main, encoding="utf-8")):
            # identical run (same prob AND thresh) → replace outright, don't stack
            if (row.get("year") == str(year) and row.get("ref") == ref_path.name
                    and row.get("prob") == prob_path.name
                    and row.get("thresh") == str(thresh)):
                continue
            # same year+ref+ARM, different run → keep as history, mark dead.
            # Arm = the run tag parsed from the prob filename (the same parse
            # live_thresholds() uses): a sectors_v1 re-score must never kill the
            # citywide live row for the same year — each tag is its own lineage.
            if (row.get("year") == str(year) and row.get("ref") == ref_path.name
                    and _prob_arm(row.get("prob", "")) == _prob_arm(prob_path.name)
                    and row.get("live", "1") != "0"):
                row["live"] = "0"
                n_sup += 1
            keep.append(row)
    with open(main, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in keep:
            row.setdefault("live", "1")          # pre-existing rows for OTHER years
            w.writerow({k: row.get(k, "") for k in fields})
        for row in new:
            w.writerow(row)
    if n_sup:
        print(f"[qc-indep] superseded {n_sup} earlier row(s) for {year}/{ref_path.name} "
              f"(live=0; history kept)")
    print(f"[qc-indep] wrote {main}  — quote live=1 rows ONLY")

    # per-surface breakout CSV (one file per year, overwritten)
    surf = QC_DIR / f"qc_indep_surfaces_{year}.csv"
    sfields = ["group", "kind", "px", "area_pct", "canopy_call_rate", "ref", "prob", "thresh", "ts"]
    with open(surf, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sfields)
        w.writeheader()
        for s in surf_rows:
            w.writerow(dict(group=s["group"], kind=s["kind"], px=s["px"],
                            area_pct=round(s["area_pct"], 3),
                            canopy_call_rate=round(s["call_rate"], 4),
                            ref=ref_path.name, prob=prob_path.name, thresh=thresh, ts=ts))
    print(f"[qc-indep] wrote {main}")
    print(f"[qc-indep] wrote {surf}")



def main():
    # Colab injects `-f <kernel.json>`; strip only that pair. (The generic
    # "drop any *.json arg" filter used elsewhere would eat --ref-map values.)
    keep, skip_next = [], False
    for i, a in enumerate(sys.argv[1:]):
        if skip_next:
            skip_next = False
            continue
        if a == "-f":
            skip_next = True
            continue
        keep.append(a)
    # re-attach values that follow known value-flags even if they end in .json
    ap = argparse.ArgumentParser(description="Score the model vs an independent canopy reference.")
    ap.add_argument("--year", default="2016")
    ap.add_argument("--ref", required=True, help="Independent reference raster (any CRS/res).")
    ap.add_argument("--ref-scheme", choices=["ccap", "binary"], default="ccap")
    ap.add_argument("--ref-map", default=None, help="JSON overriding the class→group map.")
    ap.add_argument("--prob", default=None, help="Prob raster override (score an archived variant).")
    ap.add_argument("--thresh", type=float, default=None,
                    help="Operating threshold; default = deployed value from eval CSV.")
    ap.add_argument("--block-rows", type=int, default=2048)
    ap.add_argument("--min-valid-frac", type=float, default=0.05,
                    help="Abort if less than this fraction of the prob raster is valid "
                         "(default 0.05). Guards against scoring a failed inference run.")
    args = ap.parse_args(keep)

    ref_path = Path(args.ref)
    if not ref_path.exists():
        raise FileNotFoundError(f"--ref not found: {ref_path}")
    prob_path = resolve_prob(args.year, args.prob)

    if args.thresh is not None:
        thresh = args.thresh
    else:
        got = deployed_threshold(args.year)
        if got is None:
            print("  ! no eval-CSV threshold found; defaulting to 0.5")
            thresh = 0.5
        else:
            thresh, ch = got
            print(f"  deployed threshold {thresh} (channels={ch}) from eval CSV")

    try:
        R = score(args.year, ref_path, prob_path, thresh,
                  args.ref_scheme, args.ref_map, args.block_rows,
                  min_valid_frac=args.min_valid_frac)
    except QCUnscorableError as e:
        print(f"\n[qc-indep] UNSCORABLE — no row written\n{e}\n", file=sys.stderr)
        raise SystemExit(2)
    _prim = R["defs"][R["primary_idx"]]
    write_step_log("phase4_qc_indep", step=str(args.year), logs_dir=LOGS_DIR,
                   primary_def=_prim[0],
                   recall=round(_safe(sum(R["gmc"][g] for g in _prim[1]),
                                      sum(R["gpx"][g] for g in _prim[1])), 4),
                   valid=R["valid"], indep_1m_cells=int(R["indep_cells"]))


if __name__ == "__main__":
    main()
