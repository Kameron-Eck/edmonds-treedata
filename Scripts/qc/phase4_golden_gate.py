r"""
==================================================================
  PHASE 4 -- GOLDEN REGRESSION GATE v1  (E07)
  Edmonds Temporal Active Learning Pipeline

WHAT THIS IS
  A LOCAL, torch-free, REPORT-ONLY regression gate. It re-scores the frozen
  sentinel windows (Scripts/sentinel_sites.json -- the same 12 rectangles
  phase4_sentinel_snap.py / phase4_sentinel_qc_overlay.py use) against the
  two-reference AGREEMENT partition, pools the counts, and appends one row per
  run to a history file on the data lake. Comparing today's pooled numbers to
  the last row for the same (year, tag) tells you whether a code or model
  change MOVED the model on ground that has not changed.

WHAT THIS IS NOT
  It is NOT an accuracy measurement. The numbers here are computed on a
  hand-picked dozen windows, only where C-CAP and NDVI agree -- a deliberately
  easy, deliberately unrepresentative slice. Absolute accuracy lives in
  phase4/qc/qc_indep_report.csv (live=1 rows). Never quote a golden-gate
  number as an accuracy figure.

HONESTY RAILS (all enforced in code, not by convention)
  * Thresholds come ONLY from qc_indep_report.csv live=1 primary=1 rows, keyed
    (year, tag) parsed from the prob filename, latest ts wins. A (year, tag)
    with no live row is REFUSED and listed. There is no 0.5 fallback, ever.
  * qc_indep_report.csv is opened READ-ONLY and never rewritten.
  * PROB_NODATA (255) pixels are EXCLUDED from scoring entirely. This is the
    one place the gate deliberately departs from phase4_sentinel_snap's
    canopy_from_mask(), whose `p[a==255]=nan; nan>=thresh -> False` quietly
    folds nodata into canopy-ABSENT and so manufactures false negatives on any
    sector-restricted or partially written raster.
  * Reference nodata is excluded too: ndvi_ref 255 and C-CAP 0 are NOT
    evidence of "no canopy". (Verified a no-op on all 12 windows for the four
    NDVI years as of 2026-08-25 -- baked in before any history accumulated so
    the definition never has to be amended later.)
  * A window whose prob-valid pixel count is under 80% of the FULL requested
    window (denominator = the un-intersected window, so an edge-clipped read
    cannot masquerade as fully valid) is reported SKIPPED with a reason and is
    never scored. Skips are PRINTED, never silently omitted -- on a
    sector-restricted raster the negatives drop out and the pooled precision
    stops meaning what it meant on a citywide raster.
  * Per-window rows are DIAGNOSTICS. The gate metric is the POOLED sum.
  * REPORT-ONLY in v1: exit code is 0 unless the script itself fails. There is
    no armed tolerance because no noise arm has been run -- nobody knows yet
    how much a pooled number moves between two identical runs. Arming a
    threshold before measuring that would be inventing a number.

SCORING DEFINITION (frozen -- changing any of this breaks the history)
  grid          the prob raster's own native window, so nodata is exact
  refs          C-CAP epoch-matched (<=2018 -> ccap_2016_hires_lc.tif,
                >=2019 -> ccap_2021_hires_lc.tif, per the overlay's
                CCAP_FOR_YEAR) and ndvi_ref_{year}.tif, nearest-resampled onto
                the prob window's footprint
  agreed        (ccap_canopy & ndvi_canopy) | (~ccap_canopy & ~ndvi_canopy),
                intersected with prob-valid and both refs' valid data
  canopy call   prob_DN >= ceil(thresh * 254)  -- exactly equivalent to the
                overlay's float `DN/254.0 >= thresh`, without the upcast
  tp/fn/fp      tp = agreed-canopy & called; fn = agreed-canopy & not called;
                fp = agreed-non-canopy & called

PRODUCES  (everything it writes on the data plane, and nothing else)
  phase4/qc/golden_gate_history.csv           APPEND-ONLY, one row per scored run
  phase4/logs/phase4_golden_gate_{step}_{ts}.log   step log, per repo rule 2

USAGE (local; no torch)
  py -3.12 qc\phase4_golden_gate.py --year 2016
  py -3.12 qc\phase4_golden_gate.py --year 2016 --tag corrected
  py -3.12 qc\phase4_golden_gate.py --year 2021s --tag p2nir --note "post-E05"
  py -3.12 qc\phase4_golden_gate.py --all-scorable
==================================================================
"""

import argparse
import csv
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path
from phase4seg.names import clean_argv  # noqa: E402

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase4_sentinel_snap as SNAP                # window/bounds/read helpers
import phase4_sentinel_qc_overlay as OVL           # the agreement-partition instrument

BASE = SNAP.BASE
QC_DIR = BASE / "phase4" / "qc"
MASKS = SNAP.MASKS
LOGS_DIR = BASE / "phase4" / "logs"
HISTORY = QC_DIR / "golden_gate_history.csv"
INDEP = QC_DIR / "qc_indep_report.csv"             # READ ONLY. never written here.
REPO = Path(__file__).resolve().parents[1]

CCAP_CANOPY = OVL.CCAP_CANOPY                      # forest + forested wetland classes
NDVI_CANOPY = OVL.NDVI_CANOPY                      # ndvi_ref: 0 non-veg, 1 grass, 2 canopy
CCAP_NODATA = 0
NDVI_NODATA = 255
PROB_NODATA = 255
MIN_VALID_FRAC = 0.80                              # below this a window is SKIPPED

PROB_RE = re.compile(r"edmonds_canopy_prob_([0-9a-z]+?)(?:_(.+))?\.tif$")

HIST_COLS = ["ts", "year", "tag", "prob_name", "thresh", "n_windows_scored",
             "n_windows_skipped", "pooled_tp", "pooled_fn", "pooled_fp",
             "pooled_recall", "pooled_precision", "pooled_iou", "git_sha", "note"]

BANNER = ("RELATIVE regression signal only -- NEVER an absolute accuracy claim; "
          "absolute accuracy lives in qc_indep_report.csv live=1.")


# ------------------------------------------------------------------ provenance

def git_sha():
    """Short HEAD sha of the code plane, with -dirty when the tree is not clean."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO),
                             capture_output=True, text=True, timeout=30)
        if sha.returncode != 0:
            return "unknown"
        out = sha.stdout.strip()
        st = subprocess.run(["git", "status", "--porcelain"], cwd=str(REPO),
                            capture_output=True, text=True, timeout=60)
        if st.returncode == 0 and st.stdout.strip():
            out += "-dirty"
        return out
    except Exception:
        return "unknown"


def parse_year_tag(prob_name):
    """('edmonds_canopy_prob_2021s_p2nir.tif') -> ('2021s', 'p2nir'). Same key the
    sector program uses, so a threshold looked up here is the same threshold."""
    m = PROB_RE.search(str(prob_name))
    if not m:
        return None
    return (m.group(1), m.group(2) or "")


def live_thresholds():
    """(year, tag) -> deployed row from qc_indep_report.csv, live=1 primary=1,
    latest ts wins. Read-only. A key absent here has NO deployed threshold and
    must never be scored."""
    out = {}
    if not INDEP.exists():
        raise SystemExit(f"missing {INDEP} -- no deployed thresholds to read; refusing to score")
    with open(INDEP, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if str(r.get("live", "")).strip() != "1" or str(r.get("primary", "")).strip() != "1":
                continue
            key = parse_year_tag(r.get("prob", ""))
            if key is None:
                continue
            ts = r.get("ts", "")
            if key in out and ts < out[key]["ts"]:
                continue
            out[key] = {"thresh": float(r["thresh"]), "ts": ts, "prob": r.get("prob", ""),
                        "recall": r.get("recall", ""), "precision": r.get("precision", "")}
    return out


def ccap_for(year):
    """Epoch pairing, copied from the overlay: <=2018 scores against the 2016
    C-CAP, >=2019 against the 2021 C-CAP."""
    fname = OVL.CCAP_FOR_YEAR.get(year)
    if fname is None:
        m = re.match(r"(\d{4})", year)
        if not m:
            raise SystemExit(f"cannot infer a C-CAP epoch for year key {year!r}")
        fname = ("ccap_2016_hires_lc.tif" if int(m.group(1)) <= 2018
                 else "ccap_2021_hires_lc.tif")
    return SNAP.resolve(fname)


def ndvi_for(year):
    p = QC_DIR / f"ndvi_ref_{year}.tif"
    return p if p.exists() else None


# ------------------------------------------------------------------- windowing

def read_prob_window(path, bounds_wgs84):
    """Windowed read of the prob raster.

    Returns (arr2d, full_px, eff_bounds_wgs84). `full_px` is the pixel count of
    the window BEFORE intersection with the raster, so a read clipped at the
    raster edge is measured against the geometry that was asked for, not the
    geometry that came back. `eff_bounds_wgs84` is the footprint actually read
    -- the references are read over THAT, so the nearest-resize lines up.
    """
    with rasterio.open(path) as src:
        b = rasterio.warp.transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)
        win = rasterio.windows.from_bounds(*b, transform=src.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        full_px = int(max(win.width, 0)) * int(max(win.height, 0))
        try:
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        except rasterio.errors.WindowError:
            return None, full_px, None
        if win.width <= 0 or win.height <= 0:
            return None, full_px, None
        arr = src.read(1, window=win)
        wb = rasterio.windows.bounds(win, src.transform)
        eff = rasterio.warp.transform_bounds(src.crs, "EPSG:4326", *wb)
        return arr, full_px, eff


def ref_layer(path, bounds, shape, pick_canopy, nodata):
    """Read a categorical reference over `bounds`, nearest-resize to `shape`.
    Returns (canopy_bool, valid_bool) or (None, None) if outside the ref."""
    a = SNAP.read_window(path, bounds, bands=[1])
    if a is None:
        return None, None
    a = SNAP._resize_to(a[0], shape)
    return pick_canopy(a), (a != nodata)


def score_window(site, prob_path, ccap_path, ndvi_path, thr_dn):
    """One frozen window -> a diagnostic row. Never raises on a missing overlap."""
    name = site["name"]
    bounds = SNAP.site_bounds(site)
    row = {"site": name, "status": "SKIPPED", "reason": "", "valid_frac": float("nan"),
           "tp": 0, "fn": 0, "fp": 0, "contested_frac": float("nan")}

    arr, full_px, eff = read_prob_window(prob_path, bounds)
    if arr is None or full_px <= 0:
        row["reason"] = "outside prob raster extent"
        row["valid_frac"] = 0.0
        return row

    valid = arr != PROB_NODATA
    row["valid_frac"] = float(valid.sum()) / float(full_px)
    if row["valid_frac"] < MIN_VALID_FRAC:
        row["reason"] = (f"prob-valid {100*row['valid_frac']:.1f}% of window "
                         f"< {100*MIN_VALID_FRAC:.0f}%")
        return row

    shape = arr.shape
    ccap_can, ccap_ok = ref_layer(ccap_path, eff, shape,
                                  lambda a: np.isin(a, CCAP_CANOPY), CCAP_NODATA)
    if ccap_can is None:
        row["reason"] = "outside C-CAP reference extent"
        return row
    ndvi_can, ndvi_ok = ref_layer(ndvi_path, eff, shape,
                                  lambda a: a == NDVI_CANOPY, NDVI_NODATA)
    if ndvi_can is None:
        row["reason"] = "outside NDVI reference extent"
        return row

    scorable = valid & ccap_ok & ndvi_ok
    both_can = scorable & ccap_can & ndvi_can
    both_non = scorable & ~ccap_can & ~ndvi_can
    agreed = both_can | both_non
    called = arr >= thr_dn                      # integer form of DN/254 >= thresh

    row["tp"] = int((both_can & called).sum())
    row["fn"] = int((both_can & ~called).sum())
    row["fp"] = int((both_non & called).sum())
    n_score = int(scorable.sum())
    row["contested_frac"] = (1.0 - int(agreed.sum()) / n_score) if n_score else float("nan")
    row["status"] = "scored"
    return row


# --------------------------------------------------------------------- history

def history_rows():
    if not HISTORY.exists():
        return []
    with open(HISTORY, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def append_history(row):
    """APPEND ONLY. Header written only when the file is absent or empty."""
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    need_header = (not HISTORY.exists()) or HISTORY.stat().st_size == 0
    with open(HISTORY, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HIST_COLS)
        if need_header:
            w.writeheader()
        w.writerow(row)


def prior_row(rows, year, tag):
    """Most recent PRIOR row for the SAME (year, tag) lineage. Deliberately no
    cross-tag fallback: 2016 bare and 2016-corrected are different model
    outputs, and a delta between them would be noise dressed as a signal."""
    same = [r for r in rows if r.get("year") == year and (r.get("tag") or "") == tag]
    return same[-1] if same else None


# ---------------------------------------------------------------------- report

def _f(x, nd=4):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return round(v, nd)


def run_one(year, tag, prob_path, thresh, sites, note, sha):
    ccap_path = ccap_for(year)
    ndvi_path = ndvi_for(year)
    if ndvi_path is None:
        raise SystemExit(f"no NDVI reference for {year} (expected {QC_DIR / f'ndvi_ref_{year}.tif'}) "
                         "-- a single reference cannot arbitrate; refusing to score")
    thr_dn = int(np.ceil(thresh * 254.0 - 1e-9))

    print("=" * 72)
    print(f"[golden-gate] {year}{('/' + tag) if tag else ''}   thresh={thresh}  (DN >= {thr_dn})")
    print(f"  prob = {prob_path}")
    print(f"  ccap = {ccap_path.name}")
    print(f"  ndvi = {ndvi_path.name}")
    print(f"  code = {sha}")

    rows = [score_window(s, prob_path, ccap_path, ndvi_path, thr_dn) for s in sites]
    scored = [r for r in rows if r["status"] == "scored"]
    skipped = [r for r in rows if r["status"] != "scored"]

    print("\n  per-window diagnostics (NOT the gate metric):")
    print(f"    {'window':20s} {'status':8s} {'valid%':>7s} {'tp':>10s} {'fn':>10s} "
          f"{'fp':>10s} {'recall':>7s} {'prec':>7s} {'contst%':>8s}")
    for r in rows:
        if r["status"] != "scored":
            print(f"    {r['site']:20s} {'SKIPPED':8s} {100*r['valid_frac']:7.1f} "
                  f"{'-':>10s} {'-':>10s} {'-':>10s} {'-':>7s} {'-':>7s} {'-':>8s}")
            continue
        tp, fn, fp = r["tp"], r["fn"], r["fp"]
        rec = tp / (tp + fn) if tp + fn else float("nan")
        pre = tp / (tp + fp) if tp + fp else float("nan")
        print(f"    {r['site']:20s} {'scored':8s} {100*r['valid_frac']:7.1f} "
              f"{tp:10d} {fn:10d} {fp:10d} {rec:7.3f} {pre:7.3f} "
              f"{100*r['contested_frac']:8.1f}")

    if skipped:
        negs = [r for r in rows if r["site"].startswith("neg_")]
        neg_skipped = [r for r in negs if r["status"] != "scored"]
        print(f"\n  SKIPPED {len(skipped)}/{len(rows)} windows -- these contributed NOTHING "
              f"to the pooled numbers:")
        for r in skipped:
            print(f"    - {r['site']}: {r['reason']}")
        if neg_skipped:
            print(f"  NOTE: {len(neg_skipped)} of {len(negs)} NEGATIVE windows skipped. "
                  "Pooled precision on this run is measured on a different window set "
                  "than a run where the negatives scored -- the two are NOT comparable.")

    tp = sum(r["tp"] for r in scored)
    fn = sum(r["fn"] for r in scored)
    fp = sum(r["fp"] for r in scored)
    rec = tp / (tp + fn) if tp + fn else float("nan")
    pre = tp / (tp + fp) if tp + fp else float("nan")
    iou = tp / (tp + fn + fp) if tp + fn + fp else float("nan")

    print(f"\n  POOLED over {len(scored)} scored windows (THE gate metric):")
    print(f"    tp={tp}  fn={fn}  fp={fp}")
    print(f"    recall={rec:.4f}  precision={pre:.4f}  IoU={iou:.4f}")

    # read the prior row BEFORE appending, or the gate compares against itself
    prior = prior_row(history_rows(), year, tag)

    hist = {"ts": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "year": year, "tag": tag, "prob_name": Path(prob_path).name,
            "thresh": thresh, "n_windows_scored": len(scored),
            "n_windows_skipped": len(skipped), "pooled_tp": tp, "pooled_fn": fn,
            "pooled_fp": fp, "pooled_recall": _f(rec), "pooled_precision": _f(pre),
            "pooled_iou": _f(iou), "git_sha": sha,
            "note": "; ".join(x for x in [
                note, f"ccap={ccap_path.name}", f"ndvi={ndvi_path.name}",
                f"thr_dn={thr_dn}", "report_only_v1"] if x)}
    append_history(hist)

    print(f"\n  DELTA vs prior row for {year}{('/' + tag) if tag else ''}:")
    if prior is None:
        print("    first entry for this lineage -- nothing to compare against yet.")
    else:
        p_tp, p_fn, p_fp = (int(prior["pooled_tp"]), int(prior["pooled_fn"]),
                            int(prior["pooled_fp"]))
        print(f"    prior  {prior['ts']}  {prior['prob_name']}  thresh={prior['thresh']}  "
              f"sha={prior['git_sha']}")
        print(f"    recall     {_f(prior['pooled_recall'])} -> {_f(rec)}  "
              f"({rec - float(prior['pooled_recall']):+.4f})")
        print(f"    precision  {_f(prior['pooled_precision'])} -> {_f(pre)}  "
              f"({pre - float(prior['pooled_precision']):+.4f})")
        print(f"    IoU        {_f(prior['pooled_iou'])} -> {_f(iou)}  "
              f"({iou - float(prior['pooled_iou']):+.4f})")
        print(f"    counts     tp {p_tp} -> {tp} ({tp-p_tp:+d})   "
              f"fn {p_fn} -> {fn} ({fn-p_fn:+d})   fp {p_fp} -> {fp} ({fp-p_fp:+d})")
        if str(prior["prob_name"]) != Path(prob_path).name:
            print(f"    ! prior row scored a DIFFERENT raster ({prior['prob_name']}) -- "
                  "the delta mixes a raster change with any model change.")
        if abs(float(prior["thresh"]) - float(thresh)) > 1e-12:
            print(f"    ! THRESHOLD MOVED {prior['thresh']} -> {thresh}. Movement below is "
                  "explained by the threshold, not necessarily by the model.")
        if int(prior["n_windows_scored"]) != len(scored):
            print(f"    ! window set changed ({prior['n_windows_scored']} -> {len(scored)} "
                  "scored) -- pooled numbers are over different ground; not comparable.")
        if (p_tp, p_fn, p_fp) == (tp, fn, fp):
            if str(prior["git_sha"]) != str(sha):
                print(f"    WARNING STALE_SUSPECT: pooled counts are bitwise identical to the "
                      f"prior row but the code moved ({prior['git_sha']} -> {sha}). Either the "
                      "change genuinely does not touch these windows, or the raster being "
                      "scored was never regenerated. Verify the prob raster mtime.")
            else:
                print("    identical counts at the same sha -- reproducible, as expected.")

    print(f"\n  -> appended to {HISTORY}")
    print(f"  {BANNER}")
    return 0


def _log(step):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_golden_gate_{step}_{ts}.log").write_text(
            f"phase4_golden_gate.py {step} report_only history={HISTORY}\n", encoding="utf-8")
    except Exception:
        pass


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(
        description="Golden regression gate v1 -- pooled sentinel-window drift, REPORT ONLY.")
    ap.add_argument("--year", default=None, help="year key, e.g. 2016 / 2021s")
    ap.add_argument("--tag", default=None, help="run tag, e.g. p2nir / corrected")
    ap.add_argument("--prob", default=None, help="prob raster path override")
    ap.add_argument("--all-scorable", action="store_true",
                    help="sweep every (year, tag) with a live threshold AND an NDVI reference")
    ap.add_argument("--note", default="", help="free-text note recorded in the history row")
    ap.add_argument("--threshold-from", default=None, metavar="YEAR[/TAG]",
                    help="borrow the deployed threshold of ANOTHER live arm (same year "
                         "only) instead of requiring one for this raster's own tag. For "
                         "golden re-runs: a checkpoint re-inferred under a new tag has no "
                         "deployed threshold of its own; its SOURCE arm's is the honest "
                         "one. Provenance is appended to the history note.")
    args = ap.parse_args(argv)

    print(BANNER)
    sites = json.loads(SNAP.SITES_JSON.read_text(encoding="utf-8"))["sites"]
    print(f"[golden-gate] {len(sites)} frozen windows from {SNAP.SITES_JSON}")
    live = live_thresholds()
    sha = git_sha()

    if args.all_scorable:
        if args.prob or args.year or args.tag:
            raise SystemExit("--all-scorable takes no --year/--tag/--prob")
        scorable, unscorable = [], []
        for (year, tag), row in sorted(live.items()):
            prob = MASKS / Path(row["prob"]).name
            if ndvi_for(year) is None:
                unscorable.append((year, tag, f"no ndvi_ref_{year}.tif on the data plane"))
            elif not prob.exists():
                unscorable.append((year, tag, f"prob raster missing: {prob.name}"))
            else:
                scorable.append((year, tag, prob, row["thresh"]))
        print(f"\n[golden-gate] {len(scorable)} scorable of {len(live)} live (year, tag) pairs")
        if unscorable:
            print(f"[golden-gate] NOT SCORED ({len(unscorable)}) -- listed, never scored at an "
                  "invented threshold:")
            for year, tag, why in unscorable:
                print(f"    - {year}{('/' + tag) if tag else ''}: {why}")
        for year, tag, prob, thresh in scorable:
            run_one(year, tag, prob, thresh, sites, args.note, sha)
        _log("all_scorable")
        return 0

    if not args.year and not args.prob:
        raise SystemExit("need --year (optionally --tag / --prob) or --all-scorable")

    year, tag = args.year, (args.tag or "")
    if args.prob:
        parsed = parse_year_tag(Path(args.prob).name)
        if parsed is None:
            raise SystemExit(f"cannot parse a (year, tag) key from {Path(args.prob).name} -- "
                             "no deployed threshold can be looked up; refusing")
        p_year, p_tag = parsed
        if year and year != p_year:
            raise SystemExit(f"--year {year} contradicts --prob filename (year {p_year}) -- "
                             "refusing to score a raster against another year's references")
        if args.tag is not None and args.tag != p_tag:
            raise SystemExit(f"--tag {args.tag!r} contradicts --prob filename (tag {p_tag!r})")
        year, tag = p_year, p_tag
        prob = Path(args.prob)
    else:
        prob = MASKS / f"edmonds_canopy_prob_{year}{('_' + tag) if tag else ''}.tif"

    if not prob.exists():
        raise SystemExit(f"prob raster not found: {prob}")
    if args.threshold_from:
        parts = args.threshold_from.split("/", 1)
        src_key = (parts[0], parts[1] if len(parts) > 1 else "")
        if src_key[0] != year:
            raise SystemExit(f"--threshold-from year {src_key[0]} != raster year {year} -- "
                             "refusing to score against another year's threshold and references")
        if src_key not in live:
            raise SystemExit(f"--threshold-from {args.threshold_from}: no live=1 primary=1 row "
                             "-- the source arm has no deployed threshold either")
        thresh = live[src_key]["thresh"]
        note = (args.note + f" [thresh {thresh} borrowed from "
                f"{src_key[0]}{('/' + src_key[1]) if src_key[1] else ''}]").strip()
        rc = run_one(year, tag, prob, thresh, sites, note, sha)
        _log(f"{year}{('_' + tag) if tag else ''}")
        return rc
    key = (year, tag)
    if key not in live:
        avail = sorted(f"{y}{('/' + t) if t else ''}" for y, t in live)
        raise SystemExit(
            f"no live=1 primary=1 row in qc_indep_report.csv for {year}"
            f"{('/' + tag) if tag else ''} -- there is NO deployed threshold for it and this "
            f"gate will not invent one.\n  live (year, tag) keys available: {', '.join(avail)}")

    rc = run_one(year, tag, prob, live[key]["thresh"], sites, args.note, sha)
    _log(f"{year}{('_' + tag) if tag else ''}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
