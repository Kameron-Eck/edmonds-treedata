"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: score the model against the independent NDVI reference
  Edmonds Temporal Active Learning Pipeline

  WHY
    phase4_qc_ndvi.py built ndvi_ref_{year}.tif — a canopy reference that
    never saw the model or the 2020 labels (canopy = NDVI-vegetated AND
    tall via CHM). This scores the model's probability raster against it to
    get the HONEST recall — i.e. how much real tree canopy the model MISSES
    (the under-prediction we are chasing) — instead of the circular recall
    measured against the 2020-derived labels.

  DEFINITIONS (positives = independently-confirmed tree canopy, ref==2)
    TP        model canopy  &  ref canopy      (correct detection)
    FN        model non-can  & ref canopy      <-- UNDER-PREDICTION (missed)
    FP_grass  model canopy  &  ref grass       (precision risk — false alarm)
    FP_nonveg model canopy  &  ref non-veg     (precision risk)
    recall    = TP / (TP + FN)                 <-- the headline
    precision = TP / (TP + FP_grass + FP_nonveg)
    grass_reject = frac of ref-grass the model calls non-canopy (want ~99%)

  The prob raster and ndvi_ref are on the SAME grid for the NIR years, so
  this is a direct pixel confusion (no reprojection).

  PRODUCES (phase4/qc/):
    qc_report.csv     one row per (year, thresh) — never overwrites the
                      circular semantic_eval_report.csv
    printed confusion + a THRESHOLD SWEEP (recall vs precision vs the NDVI
    reference) so an honest operating threshold can be chosen.

  USAGE (local or Colab):
    py -3.12 phase4_qc_score.py --year 2016
    py -3.12 phase4_qc_score.py --year 2016 --thresh 0.30
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import sys



# Dep bootstrap: mechanism in phase4seg/deps.py (refactor 2.3); the LIST stays
# per-file — nine distinct sets exist and one shared list would over-install.
from phase4seg.deps import ensure_deps as _ensure_deps  # noqa: E402
_ensure_deps([("rasterio", "rasterio"), ("numpy", "numpy")])

import rasterio
from rasterio.windows import Window
from phase4seg.names import clean_argv  # noqa: E402
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


def resolve_prob(year):
    for c in (MASKS / f"edmonds_canopy_prob_{year}.tif",
              BASE / "phase5" / "masks" / f"edmonds_canopy_prob_{year}.tif"):
        if c.exists():
            return c
    raise FileNotFoundError(f"prob raster for {year} not found under {MASKS}")


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


class QCUnscorableError(RuntimeError):
    """The inputs cannot yield an honest score. NEVER downgrade this to a nan row."""


def score(year, thresh, block_rows, min_valid_frac=0.05):
    ref_path  = QC_DIR / f"ndvi_ref_{year}.tif"
    prob_path = resolve_prob(year)
    if not ref_path.exists():
        raise FileNotFoundError(f"{ref_path} missing — run phase4_qc_ndvi.py --year {year} first")

    print(f"[qc-score] year={year}  thresh={thresh}")
    print(f"    ref  = {ref_path}")
    print(f"    prob = {prob_path}")

    with rasterio.open(ref_path) as ref, rasterio.open(prob_path) as prob:
        if (ref.width, ref.height) != (prob.width, prob.height) or str(ref.crs) != str(prob.crs):
            raise ValueError(f"grid mismatch: ref {ref.width}x{ref.height}/{ref.crs} "
                             f"vs prob {prob.width}x{prob.height}/{prob.crs}")
        H, W = ref.height, ref.width
        # confusion @ the deployed threshold, plus a recall/precision sweep
        C = dict(tp=0, fn=0, fp_grass=0, fp_nonveg=0, tn=0,
                 ref_canopy=0, ref_grass=0, model_canopy=0, valid=0,
                 grass_rejected=0)
        sweep = {round(t, 4): dict(tp=0, fn=0, fp=0) for t in SWEEP_THRESHOLDS}
        thr_u8 = thresh * 254.0

        n_blocks = (H + block_rows - 1) // block_rows
        for bi, row0 in enumerate(range(0, H, block_rows)):
            rows = min(block_rows, H - row0)
            win = Window(0, row0, W, rows)
            rr = ref.read(1, window=win)
            pr = prob.read(1, window=win)
            valid = (rr != 255) & (pr != 255)
            if not valid.any():
                continue
            rc = valid & (rr == 2)          # ref canopy
            rg = valid & (rr == 1)          # ref grass
            rn = valid & (rr == 0)          # ref non-veg
            mc = valid & (pr >= thr_u8)     # model canopy @ deployed thr

            C["valid"]        += int(valid.sum())
            C["ref_canopy"]   += int(rc.sum())
            C["ref_grass"]    += int(rg.sum())
            C["model_canopy"] += int(mc.sum())
            C["tp"]           += int((rc & mc).sum())
            C["fn"]           += int((rc & ~mc).sum())
            C["fp_grass"]     += int((rg & mc).sum())
            C["fp_nonveg"]    += int((rn & mc).sum())
            C["tn"]           += int((~rc & ~mc & valid).sum())
            C["grass_rejected"] += int((rg & ~mc).sum())

            for t in sweep:
                mct = valid & (pr >= t * 254.0)
                sweep[t]["tp"] += int((rc & mct).sum())
                sweep[t]["fn"] += int((rc & ~mct).sum())
                sweep[t]["fp"] += int((~rc & mct & valid).sum())

            if bi % 5 == 0 or bi == n_blocks - 1:
                print(f"    block {bi+1}/{n_blocks}", flush=True)

    # ── FAIL LOUD (see phase4_qc_indep.py for the rationale) ─────────────────
    # qc_report.csv currently holds 2016 rows with valid=0 and every metric nan.
    # Those are failures wearing the costume of measurements. Refuse instead.
    total_px = H * W
    frac = C["valid"] / total_px if total_px else 0.0
    if C["valid"] == 0:
        raise QCUnscorableError(
            f"year {year}: ZERO valid px — ref and prob never both valid.\n"
            f"    ref  = {ref_path}\n    prob = {prob_path}\n"
            f"  Usually a failed inference run (all-nodata prob raster).\n"
            f"  No row written — an unscorable year must not look like a scored one.")
    if frac < min_valid_frac:
        raise QCUnscorableError(
            f"year {year}: only {frac:.2%} valid ({C['valid']:,} / {total_px:,} px), "
            f"below --min-valid-frac {min_valid_frac:.2%}.\n"
            f"    prob = {prob_path}\n"
            f"  Re-run inference, or pass --min-valid-frac to score it deliberately.")
    print(f"[qc-score] valid {C['valid']:,} / {total_px:,} px ({frac:.1%}) — OK")

    _report(year, thresh, C, sweep, ref_path, prob_path)
    return year, thresh, C


def _safe(n, d):
    return n / d if d else float("nan")


def _report(year, thresh, C, sweep, ref_path, prob_path):
    recall    = _safe(C["tp"], C["tp"] + C["fn"])
    fp_tot    = C["fp_grass"] + C["fp_nonveg"]
    precision = _safe(C["tp"], C["tp"] + fp_tot)
    grass_rej = _safe(C["grass_rejected"], C["ref_grass"])
    ref_can_p = 100 * _safe(C["ref_canopy"], C["valid"])
    mod_can_p = 100 * _safe(C["model_canopy"], C["valid"])

    L = []
    L.append(f"QC score vs independent NDVI reference — year {year}")
    L.append(f"  ref  : {ref_path}")
    L.append(f"  prob : {prob_path}")
    L.append(f"  deployed threshold : {thresh}")
    L.append("")
    L.append(f"  valid px            : {C['valid']:,}")
    L.append(f"  ref canopy fraction : {ref_can_p:.2f}%   (independent — NDVI+CHM)")
    L.append(f"  model canopy frac   : {mod_can_p:.2f}%   (@thr {thresh})")
    L.append(f"  gap (ref - model)   : {ref_can_p - mod_can_p:+.2f} pp"
             f"   {'<-- UNDER-prediction' if mod_can_p < ref_can_p else ''}")
    L.append("")
    L.append(f"  RECALL (of NDVI canopy) : {recall:.4f}   <-- honest, non-circular")
    L.append(f"  precision (vs NDVI)     : {precision:.4f}")
    L.append(f"  grass rejection rate    : {grass_rej:.4f}   (want ~0.99)")
    L.append(f"  TP={C['tp']:,}  FN(missed)={C['fn']:,}  "
             f"FP_grass={C['fp_grass']:,}  FP_nonveg={C['fp_nonveg']:,}")
    L.append("")
    L.append("  THRESHOLD SWEEP (vs NDVI canopy):")
    L.append("    thresh    recall   precision   canopy_recovered")
    base_fn = None
    for t in sorted(sweep):
        s = sweep[t]
        rec = _safe(s["tp"], s["tp"] + s["fn"])
        prc = _safe(s["tp"], s["tp"] + s["fp"])
        if base_fn is None:
            base_fn = s["fn"]
        L.append(f"    {t:<7.4f}  {rec:>6.4f}   {prc:>7.4f}     "
                 f"{s['tp']:,} TP / {s['fn']:,} missed")
    txt = "\n".join(L)
    print("\n" + txt)

    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"qc_score_{year}.txt").write_text(txt, encoding="utf-8")

    # append a row to qc_report.csv (never touches semantic_eval_report.csv)
    csv_path = QC_DIR / "qc_report.csv"
    fields = ["year", "thresh", "ref_canopy_pct", "model_canopy_pct", "gap_pp",
              "recall", "precision", "grass_reject", "tp", "fn",
              "fp_grass", "fp_nonveg", "valid", "ref", "prob", "ts"]
    row = dict(year=year, thresh=thresh,
               ref_canopy_pct=round(ref_can_p, 3), model_canopy_pct=round(mod_can_p, 3),
               gap_pp=round(ref_can_p - mod_can_p, 3),
               recall=round(recall, 4), precision=round(precision, 4),
               grass_reject=round(grass_rej, 4),
               tp=C["tp"], fn=C["fn"], fp_grass=C["fp_grass"], fp_nonveg=C["fp_nonveg"],
               valid=C["valid"], ref=ref_path.name, prob=prob_path.name,
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    existing = []
    if csv_path.exists():
        existing = [r for r in csv.DictReader(open(csv_path, encoding="utf-8"))
                    if not (r.get("year") == str(year) and r.get("thresh") == str(thresh))]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in existing:
            w.writerow({k: r.get(k, "") for k in fields})
        w.writerow(row)
    print(f"\n[qc-score] wrote {csv_path}")
    print(f"[qc-score] wrote {QC_DIR / f'qc_score_{year}.txt'}")



def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(description="Score the model vs the NDVI canopy reference.")
    ap.add_argument("--year", default="2016")
    ap.add_argument("--thresh", type=float, default=None,
                    help="Operating threshold; default = deployed value from eval CSV.")
    ap.add_argument("--block-rows", type=int, default=2048)
    ap.add_argument("--min-valid-frac", type=float, default=0.05,
                    help="Abort if less than this fraction of the grid is valid "
                         "(default 0.05). Guards against scoring a failed inference run.")
    args = ap.parse_args(filtered)

    thresh, ch = (args.thresh, None), None
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
        _, _, C = score(args.year, thresh, args.block_rows,
                        min_valid_frac=args.min_valid_frac)
    except QCUnscorableError as e:
        print(f"\n[qc-score] UNSCORABLE — no row written\n{e}\n", file=sys.stderr)
        raise SystemExit(2)
    write_step_log("phase4_qc_score", step=str(args.year), logs_dir=LOGS_DIR,
                   thresh=thresh, recall_vs_ndvi=round(_safe(C["tp"], C["tp"] + C["fn"]), 4),
                   tp=C["tp"], fn=C["fn"])


if __name__ == "__main__":
    main()
