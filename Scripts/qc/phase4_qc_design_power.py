"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — WHAT CI WILL THE ACTUAL STRATIFIED DESIGN DELIVER?
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (assessment 2026-08-18, §3.1 and §5)
  ------------------------------------------------------------------
  The assessment says n=250 gives +/-5.9pp, which COVERS BOTH references
  (C-CAP .295 vs NDVI+CHM .377), so the human sample "cannot arbitrate".
  But it flags its own arithmetic as SIMPLE RANDOM SAMPLING, and says:

      "Recomputing them with the Olofsson/Wagner-Stehman stratified
       variance once stratum weights are known is a small local job and
       should be done before committing."

  The weights ARE now known — phase4_accuracy_sample.py --step design has
  been run for 2016 / 2022n / 2000 and wrote sample_{year}_meta.json.  Our
  design deliberately over-samples the contested zone, which should beat
  SRS.  This script measures by how much, instead of assuming.

  HOW
  ---
  1. Take the REAL stratum weights W_h and the REAL allocation n_h from
     sample_{year}_meta.json.
  2. Rebuild the design's own strata raster (same decim, same threshold,
     via phase4_accuracy_sample.build_strata) and measure, INSIDE each
     stratum, the joint distribution of (C-CAP call, NDVI call, model call).
     That is the population the interpreter will actually be drawing from.
  3. Monte-Carlo the study: draw n_h points per stratum, assign each a TRUE
     label under a stated hypothesis, and run the SAME Olofsson estimation
     the real script runs — full multinomial covariance, as fixed in 8283232.
  4. Report the spread of the estimate and, the point of the exercise,
     THE POWER to exclude the rival hypothesis.

  THE TWO HYPOTHESES ARE TWO DEFINITIONS, NOT A RIGHT AND A WRONG ONE
  (see CHATLOG STATE result 5).  H_CCAP = the interpreter applies C-CAP's
  tree-form definition; H_NDVI = the interpreter counts woody veg >=2 m.
  Power here means "can 250 points TELL THE TWO APART", which is exactly
  what U1 needs to know before anyone spends interpreter hours.

  WHAT THIS DOES NOT MODEL
    * spatial autocorrelation between sample points (250 points scattered
      over millions of cells are effectively independent — this is the one
      place the SRS-style assumption is actually safe);
    * interpreter DISAGREEMENT, except via --interp-error, which flips a
      true label with the given probability.  Real interpreter error is
      biased, not symmetric — read that row as a floor, not an estimate;
    * the "unsure" response, which the current sampler EXCLUDES (assessment
      amendment 4 wants primary+alternate instead — unbuilt).

  USAGE
    py -3.12 phase4_qc_design_power.py --year 2016
    py -3.12 phase4_qc_design_power.py --year 2016 --interp-error 0.05

  OUTPUT
    phase4/qc/design_power_{year}.txt / .csv
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import io
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase4_accuracy_sample as PAS

BASE = PAS.BASE
QC_DIR = PAS.QC_DIR
LOGS_DIR = BASE / "phase4" / "logs"

CELLS = ("tp", "fp", "fn", "tn")
Z = 1.959963985


def population_by_stratum(meta, year):
    """Joint (ccap, ndvi, model) distribution inside each design stratum.

    build_strata() returns the strata map but not the two reference masks, so
    they are re-warped here onto the grid it hands back — same CRS, transform
    and shape, so the alignment is the design's own, not a re-derivation.
    """
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling

    prob = PAS.resolve(meta["prob"], BASE / "phase4" / "masks")
    ccap = PAS.resolve(meta["ccap"], PAS._LOCAL_IMG, PAS._DRIVE_IMG)
    ndvi = PAS.resolve(meta["ndvi"], QC_DIR) if meta["ndvi"] else None

    S = PAS.build_strata(prob, ccap, ndvi, meta["thresh"], meta["decim"])
    strata, model = S["strata"], S["model"]
    H, W = S["shape"]

    def warp(path):
        with rasterio.open(path) as src:
            with WarpedVRT(src, crs=S["crs"], transform=S["transform"],
                           width=W, height=H, resampling=Resampling.nearest) as v:
                return v.read(1)

    ccap_can = np.isin(warp(ccap), PAS.CCAP_CANOPY)
    ndvi_can = (warp(ndvi) == PAS.NDVI_CANOPY) if ndvi else None

    out = {}
    for sid in sorted(int(k) for k in meta["strata"]):
        m = strata == sid
        n = int(m.sum())
        if n == 0:
            out[sid] = None
            continue
        c = ccap_can[m].astype(np.uint8)
        d = (ndvi_can[m].astype(np.uint8) if ndvi_can is not None
             else np.zeros(n, dtype=np.uint8))
        p = model[m].astype(np.uint8)
        pat = (c << 2) | (d << 1) | p
        out[sid] = np.bincount(pat, minlength=8).astype(np.float64) / n
    return out


def estimate(acc, weights):
    """Olofsson stratified estimation — mirrors phase4_accuracy_sample.step_estimate.

    Within a stratum the four confusion cells are ONE multinomial draw, so they
    are negatively correlated; carrying the full covariance is what keeps the
    canopy-area interval honest (the bug fixed in 8283232 dropped it).
    """
    P_ = {c: 0.0 for c in CELLS}
    V = {(a, b): 0.0 for a in CELLS for b in CELLS}
    for h, a in acc.items():
        n = sum(a[c] for c in CELLS)
        if n == 0:
            continue
        W = weights[h]
        p = {c: a[c] / n for c in CELLS}
        for c in CELLS:
            P_[c] += W * p[c]
        if n > 1:
            for i in CELLS:
                for j in CELLS:
                    term = (p[i] * (1 - p[i]) if i == j else -p[i] * p[j]) / (n - 1)
                    V[(i, j)] += W * W * term

    def var_of(w):
        return sum(w.get(i, 0) * w.get(j, 0) * V[(i, j)] for i in CELLS for j in CELLS)

    area = P_["tp"] + P_["fn"]                      # estimated TRUE canopy share
    area_hw = Z * np.sqrt(max(var_of({"tp": 1, "fn": 1}), 0.0))

    num, den = {"tp": 1}, {"tp": 1, "fn": 1}
    X = P_["tp"]
    Y = P_["tp"] + P_["fn"]
    if Y > 0:
        R = X / Y
        vX, vY = var_of(num), var_of(den)
        cXY = sum(num.get(i, 0) * den.get(j, 0) * V[(i, j)] for i in CELLS for j in CELLS)
        vR = max((vX + R * R * vY - 2 * R * cXY) / (Y * Y), 0.0)
        recall, recall_hw = R, Z * np.sqrt(vR)
    else:
        recall, recall_hw = float("nan"), float("nan")
    return area, area_hw, recall, recall_hw


def simulate(pop, meta, truth_bit, reps, interp_err, seed):
    """truth_bit: 2 = C-CAP defines truth, 1 = NDVI defines truth."""
    rng = np.random.default_rng(seed)
    sm = {int(k): v for k, v in meta["strata"].items()}
    N = sum(v["cells"] for v in sm.values())
    weights = {h: sm[h]["cells"] / N for h in sm}

    # true population canopy share under this hypothesis
    truth_of = np.array([(i >> truth_bit) & 1 for i in range(8)], dtype=np.uint8)
    model_of = np.array([i & 1 for i in range(8)], dtype=np.uint8)
    true_share = sum(weights[h] * float(pop[h] @ truth_of)
                     for h in sm if pop[h] is not None)

    areas, hws, covered, recalls, rec_hws = [], [], [], [], []
    for _ in range(reps):
        acc = {}
        for h in sm:
            if pop[h] is None:
                acc[h] = {c: 0 for c in CELLS}
                continue
            draw = rng.choice(8, size=sm[h]["sampled"], p=pop[h])
            t = truth_of[draw].astype(bool)
            if interp_err > 0:
                flip = rng.random(t.size) < interp_err
                t = np.where(flip, ~t, t)
            m = model_of[draw].astype(bool)
            acc[h] = {"tp": int(np.sum(t & m)), "fp": int(np.sum(~t & m)),
                      "fn": int(np.sum(t & ~m)), "tn": int(np.sum(~t & ~m))}
        a, hw, r, rhw = estimate(acc, weights)
        areas.append(a); hws.append(hw); recalls.append(r); rec_hws.append(rhw)
        covered.append(abs(a - true_share) <= hw)
    return {"true_share": true_share, "area": np.array(areas), "hw": np.array(hws),
            "cover": float(np.mean(covered)), "recall": np.array(recalls),
            "recall_hw": np.array(rec_hws)}


def report(year, meta, sweep, reps):
    """sweep = list of (interp_err, {"H_CCAP": res, "H_NDVI": res})."""
    sm = {int(k): v for k, v in meta["strata"].items()}
    n_tot = sum(v["sampled"] for v in sm.values())
    interp_err, res = sweep[0]
    A, B = res["H_CCAP"], res["H_NDVI"]

    L = [f"EXPECTED CI OF THE ACTUAL STRATIFIED DESIGN — {year}",
         f"  scheme  : {meta['scheme']} · n = {n_tot} · {reps:,} simulated studies",
         f"  weights : the REAL area shares from sample_{year}_meta.json",
         f"  estimator: Olofsson stratified, full multinomial covariance "
         f"(as fixed in 8283232)",
         f"  interpreter error swept: "
         + ", ".join(f"{e:.0%}" for e, _ in sweep)
         + f"  (blocks below are the {interp_err:.0%} case)",
         "",
         "  -- ALLOCATION (what --step design actually drew) " + "-" * 14,
         f"     {'stratum':<22} {'area share':>11} {'points':>7} {'pts/share':>10}"]
    for h in sorted(sm):
        v = sm[h]
        ratio = (v["sampled"] / n_tot) / v["area_share"] if v["area_share"] else float("nan")
        L.append(f"     {v['name']:<22} {v['area_share']:>11.4f} {v['sampled']:>7} "
                 f"{ratio:>10.2f}")
    L += ["     (pts/share > 1 = over-sampled relative to area — that is the",
          "      contested zone being bought precision on purpose)", ""]

    for tag, R in (("H_CCAP  (truth = C-CAP's tree-form definition)", A),
                   ("H_NDVI  (truth = woody veg >=2 m)", B)):
        L += [f"  -- {tag} " + "-" * max(4, 44 - len(tag)),
              f"     true canopy share under this definition : {R['true_share']:.4f}",
              f"     mean estimate                           : {R['area'].mean():.4f}",
              f"     empirical SD of the estimate            : {R['area'].std():.4f}",
              f"     mean 95% half-width (the CI we report)  : +/-{R['hw'].mean():.4f}"
              f"  ({100*R['hw'].mean():.2f} pp)",
              f"     empirical coverage of that CI           : {R['cover']:.3f}",
              f"     mean recall estimate                    : {R['recall'].mean():.4f}"
              f" +/-{R['recall_hw'].mean():.4f}",
              ""]

    # ---- the discriminating number ----
    gap = abs(A["true_share"] - B["true_share"])
    powA = float(np.mean(np.abs(A["area"] - B["true_share"]) > A["hw"]))
    powB = float(np.mean(np.abs(B["area"] - A["true_share"]) > B["hw"]))
    srs_hw = Z * np.sqrt(0.25 / n_tot)

    L += ["  -- CAN n=%d TELL THE TWO DEFINITIONS APART? " % n_tot + "-" * 12,
          f"     separation between the hypotheses      : {gap:.4f} "
          f"({100*gap:.2f} pp)",
          f"     half-width the assessment assumed (SRS)  : "
          f"+/-{srs_hw:.4f} ({100*srs_hw:.2f} pp)",
          "",
          "     ** THE ANSWER TURNS ENTIRELY ON INTERPRETER FIDELITY. **",
          "     At 0% interpreter error the question is rigged: truth is DEFINED as",
          "     one of the two references, so inside strata built from those same",
          "     references every point has the same truth and the within-stratum",
          "     variance collapses to almost nothing.  That is an artefact of the",
          "     idealisation, not a property of the design.  The rows below let the",
          "     interpreter disagree with the reference and show what survives.",
          "",
          f"     {'interp err':>10} {'half-width':>12} {'power(C)':>9} {'power(N)':>9}"
          f"  {'verdict':<12}"]
    for e, R in sweep:
        a, b = R["H_CCAP"], R["H_NDVI"]
        pa = float(np.mean(np.abs(a["area"] - b["true_share"]) > a["hw"]))
        pb = float(np.mean(np.abs(b["area"] - a["true_share"]) > b["hw"]))
        v = ("arbitrates" if min(pa, pb) >= 0.80 else
             "cannot" if max(pa, pb) < 0.50 else "marginal")
        L.append(f"     {e:>10.0%} {a['hw'].mean():>11.4f} {pa:>9.3f} {pb:>9.3f}"
                 f"  {v:<12}")
    L.append("")

    worst = sweep[-1]
    wa, wb = worst[1]["H_CCAP"], worst[1]["H_NDVI"]
    pwa = float(np.mean(np.abs(wa["area"] - wb["true_share"]) > wa["hw"]))
    pwb = float(np.mean(np.abs(wb["area"] - wa["true_share"]) > wb["hw"]))
    if min(pwa, pwb) >= 0.80:
        L += [f"     -> ROBUST. Even at {worst[0]:.0%} interpreter error the design still",
              "        separates the two definitions. The assessment's 'cannot arbitrate'",
              "        (§3.1) was an artefact of assuming SIMPLE RANDOM SAMPLING: the real",
              "        allocation over-samples the contested zone and buys the precision",
              "        back. §3.1 should be corrected — n=250 is not the binding limit.",
              "        WHAT REMAINS BINDING IS U1: the sample can only reproduce a",
              "        definition it has been given, and no definition is written yet."]
    elif max(pwa, pwb) < 0.50:
        L += [f"     -> FRAGILE. At {worst[0]:.0%} interpreter error the separation is gone,",
              "        so the study's answer would be manufactured by interpreter",
              "        fidelity rather than measured. Duplicate-interpret a subset and",
              "        measure the real error rate BEFORE trusting any of this",
              "        (assessment amendment 5, Stehman 2022 ID 100)."]
    else:
        L += [f"     -> CONDITIONAL. The design arbitrates only while interpreter error",
              f"        stays low; by {worst[0]:.0%} it is marginal or gone. The",
              "        duplicate-interpreted subset (amendment 5) stops being optional —",
              "        it is what decides whether the headline number means anything."]

    L += ["",
          "  -- CAVEATS " + "-" * 47,
          "     * The hypotheses are DEFINITIONS, not a right and a wrong answer",
          "       (CHATLOG STATE result 5). Power here = can the sample TELL THEM",
          "       APART; it does not say which one U1 should adopt.",
          "     * Points are treated as independent within a stratum. For 250 points",
          "       scattered over millions of cells that is safe — unlike the pixel",
          "       counts elsewhere in this pipeline, where it would not be.",
          "     * Interpreter error is simulated as a symmetric flip. Real error is",
          "       biased and correlated with difficulty, so the --interp-error rows",
          "       are a FLOOR on the damage, not an estimate of it.",
          "     * 'unsure' is not modelled because the current sampler excludes it.",
          "       Assessment amendment 4 (primary + alternate) would change this.",
          "     * The ratio estimator's CI is delta-method and the strata are not map",
          "       classes, so the recall interval stays indicative (assessment (d))."]

    txt = "\n".join(x for x in L if x != "")
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"design_power_{year}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"design_power_{year}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "n", "interp_error", "hypothesis", "true_share",
                    "mean_estimate", "sd", "mean_half_width", "coverage",
                    "power_vs_rival", "srs_half_width"])
        for e, R in sweep:
            a, b = R["H_CCAP"], R["H_NDVI"]
            pa = float(np.mean(np.abs(a["area"] - b["true_share"]) > a["hw"]))
            pb = float(np.mean(np.abs(b["area"] - a["true_share"]) > b["hw"]))
            for tag, Rr, pw in (("H_CCAP", a, pa), ("H_NDVI", b, pb)):
                w.writerow([year, n_tot, e, tag, round(Rr["true_share"], 4),
                            round(float(Rr["area"].mean()), 4),
                            round(float(Rr["area"].std()), 4),
                            round(float(Rr["hw"].mean()), 4), round(Rr["cover"], 3),
                            round(pw, 3), round(srs_hw, 4)])
    print(f"\n[design-power] wrote {QC_DIR / f'design_power_{year}.txt'}")
    return powA, powB


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(
        description="Simulate the real stratified design to get its expected CI and "
                    "its power to tell the two canopy definitions apart.")
    ap.add_argument("--year", required=True)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--interp-error", type=float, nargs="+", default=[0.0, 0.05, 0.10],
                    help="Interpreter flip probabilities to sweep (default 0 .05 .10).")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    meta_p = QC_DIR / f"sample_{args.year}_meta.json"
    if not meta_p.exists():
        raise SystemExit(f"missing {meta_p} — run phase4_accuracy_sample.py --step design first")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    if meta["scheme"] != "dual_reference":
        raise SystemExit(
            f"{args.year} is a {meta['scheme']} design — it has only ONE reference, so "
            "there are no two definitions to tell apart. Run a NIR year (2016/2022n).")

    print(f"[design-power] rebuilding the design's own strata for {args.year} "
          f"(decim {meta['decim']}, thresh {meta['thresh']})")
    pop = population_by_stratum(meta, args.year)

    sweep = []
    for k, e in enumerate(sorted(args.interp_error)):
        print(f"[design-power] simulating {args.reps} studies at interpreter error {e:.0%}")
        sweep.append((e, {
            "H_CCAP": simulate(pop, meta, 2, args.reps, e, args.seed + 100 * k),
            "H_NDVI": simulate(pop, meta, 1, args.reps, e, args.seed + 100 * k + 1)}))
    report(args.year, meta, sweep, args.reps)

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_design_power_{args.year}_{ts}.log").write_text(
            f"phase4_qc_design_power.py year={args.year} reps={args.reps} "
            f"interp_error={args.interp_error}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
