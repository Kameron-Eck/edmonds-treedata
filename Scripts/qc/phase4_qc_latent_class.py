"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — LATENT-CLASS ACCURACY WITH NO GOLD STANDARD
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (assessment 2026-08-18, unknown U2)
  ------------------------------------------------------------------
  "Which reference is closer to truth?"  blocks the 2016c deploy decision
  and rides as a caveat on every number we quote.  The two references
  disagree on 15-17% of pixels and we have no gold standard, so the
  dispute has been un-arbitrable:

      C-CAP    says 2016 canopy fraction ~29.5%
      NDVI+CHM says 2016 canopy fraction ~37.7%

  Foody 2022 (Literature_Tracker ID 80) is the escape.  Treat C-CAP, the
  NDVI+CHM reference and the model as THREE IMPERFECT TESTS of one latent
  binary variable (canopy / not).  Their 2x2x2 agreement table has 7
  degrees of freedom, and a 2-class latent model has exactly 7 free
  parameters:

      pi                    prevalence of latent canopy
      se_j, sp_j  (j=1..3)  sensitivity + specificity of each source

  Solving it turns DISAGREEMENT from noise into the estimator's input.

  ** THE ASSUMPTION THAT DECIDES WHETHER THIS IS WORTH ANYTHING **
  ------------------------------------------------------------------
  Latent-class modelling assumes the three sources' errors are
  CONDITIONALLY INDEPENDENT given the latent class.  Ours are almost
  certainly not (Foody 2010, ID 79):

    * all three ultimately interpret the same imagery;
    * the model was trained on labels descended from the NDVI reference's
      definition, and phase4_qc_height_by_agreement showed the model
      siding with the NDVI ref in 90.8% of contested pixels.

  Naive 3-source LCA on dependent sources degenerates into a 2-versus-1
  VOTE against C-CAP wearing a statistician's coat.  Two defences, both
  implemented here:

    1. FIT WITHIN CHM HEIGHT BANDS.  Height is the dominant driver of
       every source's error rate (P1c, U3).  Conditioning on it absorbs
       much of the shared dependence, and per-band se/sp is what U2
       actually needs.  The global fit is reported too, and where the two
       disagree the BAND-CONDITIONED fit is the defensible one.
    2. REPORT AS A SENSITIVITY ANALYSIS, not a verdict.  The output
       states which conclusion flips if model<->NDVI dependence is real.

  TWO MORE THINGS THIS OUTPUT WILL NOT DO
    * No goodness-of-fit test.  7 parameters on 7 d.f. is JUST-IDENTIFIED:
      the model reproduces the observed table exactly, by construction.
      A perfect fit is arithmetic, not evidence.
    * No naive pixel-count CIs.  n is in the millions and spatially
      autocorrelated, so binomial intervals would be fiction.  Intervals
      come from a SPATIAL BLOCK BOOTSTRAP over ~256 m blocks.

  USAGE
    py -3.12 phase4_qc_latent_class.py \\
        --prob  phase4/masks/edmonds_canopy_prob_2016.tif \\
        --ccap  D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc.tif \\
        --ndvi  phase4/qc/ndvi_ref_2016.tif \\
        --thresh 0.509 --label 2016_baseline

  OUTPUT
    phase4/qc/latent_class_{label}.txt / .csv
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import io
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from phase4seg.names import clean_argv  # noqa: E402
from rasterio.transform import Affine

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
CHM_NAME = "lidar_snoh_chm.tif"
CHM_DN_PER_M = 1.0 / 0.2

# Same banding as phase4_qc_height_by_agreement.py, deliberately — U3's
# partition curves and these per-band se/sp must be readable side by side.
HEIGHT_BINS = [0, 2, 5, 10, 15, 20, 25, 30, 100]
CCAP_CANOPY = [9, 10, 11, 13, 16]          # forest + forested wetland, as qc_indep
NDVI_CANOPY = 2                            # ndvi_ref codes: 0 non-veg, 1 grass, 2 canopy

SOURCES = ["ccap", "ndvi_ref", "model"]
# pattern index = ccap*4 + ndvi*2 + model  (bit 2 = C, bit 1 = N, bit 0 = M)
PATTERN = np.array([[(i >> 2) & 1, (i >> 1) & 1, i & 1] for i in range(8)], dtype=np.float64)


def resolve_chm():
    for d in (_LOCAL_IMG, _DRIVE_IMG):
        p = d / CHM_NAME
        if p.exists():
            return p
    raise FileNotFoundError(CHM_NAME)


def _band_labels():
    out = []
    for i in range(len(HEIGHT_BINS) - 1):
        lo, hi = HEIGHT_BINS[i], HEIGHT_BINS[i + 1]
        out.append(f"{lo:>2}-{hi:<3}m" if hi < 100 else f"{lo:>2}+   m")
    return out


# ───────────────────────────── the estimator ─────────────────────────────

def _loglik(counts, pi, se, fp):
    l1 = pi * np.prod(se ** PATTERN * (1 - se) ** (1 - PATTERN), axis=1)
    l0 = (1 - pi) * np.prod(fp ** PATTERN * (1 - fp) ** (1 - PATTERN), axis=1)
    return float((counts * np.log(np.maximum(l1 + l0, 1e-300))).sum()), l1, l0


def fit_lca(counts, n_starts=16, seed=0, max_iter=4000, tol=1e-11, init=None):
    """2-class, 3-indicator latent class model by EM.

    counts : length-8 vector of pattern frequencies (see PATTERN).
    Returns dict with pi, se[3], sp[3], loglik, n, plus diagnostic flags,
    or None when the cell is empty.

    LABEL SWITCHING: the likelihood is invariant to swapping the two latent
    classes (pi -> 1-pi, se <-> 1-sp), which mirrors every solution.  We
    resolve it by the standard identifying constraint se_j + sp_j > 1 — each
    source must be a better-than-chance test of canopy.  Without it the
    reported "sensitivity" could be the sensitivity of NOT-canopy.
    """
    counts = np.asarray(counts, dtype=np.float64)
    N = counts.sum()
    if N <= 0:
        return None

    rng = np.random.default_rng(seed)
    starts = []
    if init is not None:
        starts.append((float(init["pi"]), np.asarray(init["se"], float),
                       1.0 - np.asarray(init["sp"], float)))
    for _ in range(n_starts):
        starts.append((rng.uniform(0.15, 0.85),
                       rng.uniform(0.55, 0.98, 3),
                       rng.uniform(0.02, 0.45, 3)))

    best = None
    for pi, se, fp in starts:
        se = np.clip(np.array(se, dtype=np.float64), 1e-6, 1 - 1e-6)
        fp = np.clip(np.array(fp, dtype=np.float64), 1e-6, 1 - 1e-6)
        for _ in range(max_iter):
            _, l1, l0 = _loglik(counts, pi, se, fp)
            tot = np.maximum(l1 + l0, 1e-300)
            w = l1 / tot
            n1 = counts * w
            n0 = counts * (1.0 - w)
            s1, s0 = n1.sum(), n0.sum()
            pi_new = s1 / N
            se_new = (n1 @ PATTERN) / max(s1, 1e-12)
            fp_new = (n0 @ PATTERN) / max(s0, 1e-12)
            se_new = np.clip(se_new, 1e-6, 1 - 1e-6)
            fp_new = np.clip(fp_new, 1e-6, 1 - 1e-6)
            delta = max(abs(pi_new - pi),
                        float(np.abs(se_new - se).max()),
                        float(np.abs(fp_new - fp).max()))
            pi, se, fp = float(np.clip(pi_new, 1e-9, 1 - 1e-9)), se_new, fp_new
            if delta < tol:
                break
        ll, _, _ = _loglik(counts, pi, se, fp)
        if best is None or ll > best[0] + 1e-9:
            best = (ll, pi, se, fp)

    ll, pi, se, fp = best
    sp = 1.0 - fp
    # identifying constraint: each source better than chance for canopy
    if float(np.mean(se + sp)) < 1.0:
        pi, se, sp = 1.0 - pi, 1.0 - se, 1.0 - sp

    boundary = bool(np.any(se > 1 - 1e-4) or np.any(se < 1e-4)
                    or np.any(sp > 1 - 1e-4) or np.any(sp < 1e-4)
                    or pi < 1e-4 or pi > 1 - 1e-4)
    weak = bool(np.any(se + sp < 1.02))     # a source carrying ~no information
    return {"pi": float(pi), "se": se, "sp": sp, "loglik": ll, "n": float(N),
            "boundary": boundary, "weak": weak,
            "observed": (counts @ PATTERN) / N}


# ───────────────────────────── data assembly ─────────────────────────────

def assemble(prob_path, ccap_path, ndvi_path, thresh, decim, block):
    """Return per-(block, band) pattern counts + the observables U2 needs."""
    chm_path = resolve_chm()
    print(f"[latent-class] prob = {prob_path}")
    print(f"[latent-class] ccap = {ccap_path}")
    print(f"[latent-class] ndvi = {ndvi_path}")
    print(f"[latent-class] chm  = {chm_path}")
    print(f"[latent-class] decimation 1/{decim} · bootstrap block {block} cells")

    thr_u8 = thresh * 254.0
    with rasterio.open(prob_path) as p:
        H = p.height // decim
        W = p.width // decim
        dt = p.transform * Affine.scale(decim)
        crs = p.crs
        nodata = 255 if p.nodata is None else p.nodata
        pr = p.read(1, out_shape=(H, W), resampling=Resampling.nearest)

    with rasterio.open(ccap_path) as r:
        with WarpedVRT(r, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest) as rv:
            rc = rv.read(1)
            ccap_nodata = r.nodata
    with rasterio.open(ndvi_path) as n:
        with WarpedVRT(n, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest) as nv:
            nd = nv.read(1)
            ndvi_nodata = n.nodata
    with rasterio.open(chm_path) as c:
        with WarpedVRT(c, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest, src_nodata=0, nodata=0) as cv:
            dn = cv.read(1)

    valid = pr != nodata
    if ccap_nodata is not None:
        valid &= rc != ccap_nodata
    valid &= rc != 0
    if ndvi_nodata is not None:
        valid &= nd != ndvi_nodata

    C = np.isin(rc, CCAP_CANOPY)
    N_ = nd == NDVI_CANOPY
    M = pr >= thr_u8
    pat = (C.astype(np.uint8) << 2) | (N_.astype(np.uint8) << 1) | M.astype(np.uint8)

    hgt = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    hgt[dn == 0] = np.nan
    n_bins = len(HEIGHT_BINS) - 1
    band = np.full((H, W), -1, dtype=np.int16)
    fin = np.isfinite(hgt)
    band[fin] = np.clip(np.digitize(hgt[fin], HEIGHT_BINS) - 1, 0, n_bins - 1).astype(np.int16)

    rows = np.arange(H, dtype=np.int64)[:, None] // block
    cols = np.arange(W, dtype=np.int64)[None, :] // block
    n_bcols = int(W // block) + 1
    blk = np.broadcast_to(rows * n_bcols + cols, (H, W))

    v = valid
    n_blk = int(blk.max()) + 1
    # global table (all valid cells, CHM or not) and the band tables (CHM only)
    cube_all = np.bincount(blk[v] * 8 + pat[v],
                           minlength=n_blk * 8).reshape(-1, 8)
    vb = v & (band >= 0)
    idx = (blk[vb] * n_bins + band[vb]) * 8 + pat[vb]
    cube_band = np.bincount(idx, minlength=n_blk * n_bins * 8).reshape(-1, n_bins, 8)

    keep = cube_all.sum(axis=1) > 0
    print(f"[latent-class] {int(v.sum()):,} valid cells · "
          f"{int(vb.sum()):,} with CHM · {int(keep.sum()):,} non-empty blocks")
    return {"cube_all": cube_all[keep], "cube_band": cube_band[keep],
            "n_valid": int(v.sum()), "n_chm": int(vb.sum()),
            "thresh": thresh, "decim": decim, "block": block,
            "prob": Path(prob_path).name, "ccap": Path(ccap_path).name,
            "ndvi": Path(ndvi_path).name}


# ───────────────────────────── bootstrap ─────────────────────────────

def block_bootstrap(D, point, reps, seed):
    """Resample whole spatial blocks with replacement; refit each rep.

    Blocks are ~(block x decim) native pixels on a side, so a resample unit is
    far larger than the autocorrelation range of a canopy patch.  This is the
    only interval reported; a binomial CI on 20M correlated pixels is fiction.
    """
    if reps <= 0:
        return None
    ca, cb = D["cube_all"], D["cube_band"]
    nblk = ca.shape[0]
    n_bins = cb.shape[1]
    rng = np.random.default_rng(seed)
    acc = {"global": [], "band": [[] for _ in range(n_bins)]}

    for r in range(reps):
        pick = rng.integers(0, nblk, nblk)
        f = fit_lca(ca[pick].sum(axis=0), n_starts=2, seed=seed + r,
                    init=point["global"], max_iter=1500)
        if f is not None and not f["boundary"]:
            acc["global"].append(np.concatenate(([f["pi"]], f["se"], f["sp"])))
        cbs = cb[pick].sum(axis=0)
        for b in range(n_bins):
            pb = point["band"][b]
            if pb is None:
                continue
            fb = fit_lca(cbs[b], n_starts=2, seed=seed + r, init=pb, max_iter=1500)
            if fb is not None and not fb["boundary"]:
                acc["band"][b].append(np.concatenate(([fb["pi"]], fb["se"], fb["sp"])))
        if (r + 1) % 25 == 0:
            print(f"[latent-class]   bootstrap {r + 1}/{reps}")

    def ci(rowlist):
        if len(rowlist) < 10:
            return None
        A = np.vstack(rowlist)
        return {"lo": np.percentile(A, 2.5, axis=0), "hi": np.percentile(A, 97.5, axis=0),
                "reps": len(rowlist)}

    return {"global": ci(acc["global"]), "band": [ci(x) for x in acc["band"]]}


# ───────────────────────────── reporting ─────────────────────────────

def _fmt_ci(ci, k):
    if ci is None:
        return ""
    return f" [{ci['lo'][k]:.3f},{ci['hi'][k]:.3f}]"


def report(D, point, boot, label):
    bands = _band_labels()
    n_bins = len(bands)
    G = point["global"]

    L = [f"LATENT-CLASS ACCURACY WITHOUT A GOLD STANDARD (Foody 2022, ID 80) — {label}",
         f"  prob : {D['prob']}   @ thresh {D['thresh']}",
         f"  ccap : {D['ccap']}",
         f"  ndvi : {D['ndvi']}",
         f"  sample : 1/{D['decim']} decimation · {D['n_valid']:,} valid cells · "
         f"{D['n_chm']:,} with CHM",
         f"  intervals : 95% spatial block bootstrap, {D['block']}-cell blocks"
         + (f", {boot['global']['reps'] if boot and boot['global'] else 0} usable reps"
            if boot else " (not run)"),
         ""]

    if G is None:
        L.append("  NO DATA.")
    else:
        obs = G["observed"]
        L += ["  -- OBSERVED (what each source simply says) " + "-" * 20]
        for j, s in enumerate(SOURCES):
            L.append(f"     {s:<10} calls canopy on {obs[j]:.4f} of valid cells")
        L += ["",
              "  -- GLOBAL LATENT FIT (pooled; see the caveat below) " + "-" * 11,
              f"     latent canopy prevalence pi = {G['pi']:.4f}"
              f"{_fmt_ci(boot['global'] if boot else None, 0)}",
              "",
              f"     {'source':<10} {'sensitivity':<22} {'specificity':<22}"]
        for j, s in enumerate(SOURCES):
            se = f"{G['se'][j]:.4f}{_fmt_ci(boot['global'] if boot else None, 1 + j)}"
            sp = f"{G['sp'][j]:.4f}{_fmt_ci(boot['global'] if boot else None, 4 + j)}"
            L.append(f"     {s:<10} {se:<22} {sp:<22}")
        if G["boundary"]:
            L.append("     ** BOUNDARY SOLUTION — a parameter hit 0 or 1; do not quote it. **")
        if G["weak"]:
            L.append("     ** a source has se+sp ~ 1 (no information); the fit is unstable. **")

    L += ["",
          "  -- BAND-CONDITIONED FIT (the defensible one) " + "-" * 18,
          "     Fitted separately inside each CHM height band, because height is",
          "     the dominant driver of every source's error rate and conditioning",
          "     on it absorbs much of the shared dependence between sources.",
          ""]
    hdr = f"     {'band':<11} {'n':>12} {'pi':>7}"
    for s in SOURCES:
        hdr += f" | {s + ' se':>9} {s + ' sp':>9}"
    L.append(hdr)
    for b in range(n_bins):
        P = point["band"][b]
        if P is None:
            continue
        cib = boot["band"][b] if boot else None
        row = f"     {bands[b]:<11} {P['n']:>12,.0f} {P['pi']:>7.4f}"
        for j in range(3):
            row += f" | {P['se'][j]:>9.4f} {P['sp'][j]:>9.4f}"
        if P["boundary"]:
            row += "  (boundary)"
        elif P["weak"]:
            row += "  (weak)"
        L.append(row)
        if cib is not None:
            row2 = f"     {'':<11} {'':>12} {'':>7}"
            for j in range(3):
                row2 += (f" | {cib['lo'][1+j]:.2f}-{cib['hi'][1+j]:.2f}"
                         f" {cib['lo'][4+j]:.2f}-{cib['hi'][4+j]:.2f}")
            L.append(row2)

    # ---- the U2 discriminator ----
    L += ["", "  -- WHAT THIS SAYS ABOUT U2 " + "-" * 35]
    if G is not None:
        obs = G["observed"]
        L += [f"     C-CAP calls canopy on            {obs[0]:.4f}",
              f"     NDVI+CHM calls canopy on         {obs[1]:.4f}",
              f"     latent prevalence estimate is    {G['pi']:.4f}",
              ""]
        d_c, d_n = abs(G["pi"] - obs[0]), abs(G["pi"] - obs[1])
        closer = "C-CAP" if d_c < d_n else "the NDVI+CHM reference"
        L += [f"     -> the latent prevalence sits closer to {closer}"
              f" (|d| {min(d_c, d_n):.4f} vs {max(d_c, d_n):.4f}).",
              "        Prevalence agreement is NOT accuracy — read it with the",
              "        se/sp table, where a source can hit the right total by",
              "        trading false positives against false negatives.",
              ""]
        j_hi = int(np.argmax(G["se"] + G["sp"]))
        L.append(f"     -> highest Youden J (se+sp-1): {SOURCES[j_hi]} "
                 f"at {G['se'][j_hi] + G['sp'][j_hi] - 1:.4f}.")

    L += ["",
          "  -- HOW THIS CAN BE WRONG (read before quoting) " + "-" * 16,
          "     1. CONDITIONAL INDEPENDENCE IS THE WHOLE MODEL, and ours is",
          "        doubtful.  The model was trained on labels descended from the",
          "        NDVI reference and sides with it on 90.8% of contested pixels",
          "        (phase4_qc_height_by_agreement).  Two correlated sources out-vote",
          "        the third, so LCA will flatter the model/NDVI pair and understate",
          "        C-CAP's specificity.  IF THAT DEPENDENCE IS REAL, the conclusion",
          "        'C-CAP over-calls canopy' is the first thing to fall — it is",
          "        exactly what a 2-vs-1 vote manufactures.  Treat the band table as",
          "        a sensitivity analysis bracketing P2, not as an arbitration.",
          "     2. NO FIT STATISTIC IS REPORTED because none exists here: 7 free",
          "        parameters on a 7-d.f. table is just-identified and reproduces the",
          "        observed counts exactly.  Perfect fit is arithmetic, not evidence.",
          "     3. Every band is conditioned on CHM presence (~60% of the city) and",
          "        the CHM is ~2016 vintage with a realistic MAE ~3 m (Moudry 2024,",
          "        ID 82), which blurs adjacent 5 m bands.",
          "     4. The NDVI reference requires height >= 2 m BY CONSTRUCTION, so its",
          "        se in the 0-2 m band is not an error rate — it is the definition.",
          "        Do not quote the 0-2 m row.",
          "     5. Decimated sample; the shape across bands is the robust part.",
          "",
          "     RESOLVES NOTHING BY ITSELF.  U2 is settled by human photo-interpretation",
          "     (P3) against a written canopy definition (U1), which does not exist yet.",
          "     This narrows what that sample has to decide."]

    txt = "\n".join(L)
    print("\n" + txt)

    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"latent_class_{label}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"latent_class_{label}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "band_lo_m", "band_hi_m", "n", "pi", "source",
                    "sensitivity", "specificity", "youden_j", "flag"])

        def _rows(scope, lo, hi, P):
            if P is None:
                return
            flag = "boundary" if P["boundary"] else ("weak" if P["weak"] else "")
            for j, s in enumerate(SOURCES):
                w.writerow([scope, lo, hi, int(P["n"]), round(P["pi"], 4), s,
                            round(float(P["se"][j]), 4), round(float(P["sp"][j]), 4),
                            round(float(P["se"][j] + P["sp"][j] - 1), 4), flag])

        _rows("global", "", "", point["global"])
        for b in range(n_bins):
            _rows("band", HEIGHT_BINS[b], HEIGHT_BINS[b + 1], point["band"][b])
    print(f"\n[latent-class] wrote {QC_DIR / f'latent_class_{label}.txt'}")


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(
        description="Latent-class sensitivity/specificity for C-CAP, the NDVI reference "
                    "and the model, with no gold standard (Foody 2022).")
    ap.add_argument("--prob", required=True)
    ap.add_argument("--ccap", required=True)
    ap.add_argument("--ndvi", required=True)
    ap.add_argument("--thresh", type=float, required=True)
    ap.add_argument("--label", required=True, help="Name for the output files.")
    ap.add_argument("--decim", type=int, default=8, help="Decimation factor (default 8).")
    ap.add_argument("--block", type=int, default=64,
                    help="Bootstrap block side in decimated cells (default 64).")
    ap.add_argument("--boot", type=int, default=200,
                    help="Block-bootstrap replicates (default 200; 0 disables).")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    D = assemble(Path(args.prob), Path(args.ccap), Path(args.ndvi),
                 args.thresh, args.decim, args.block)

    n_bins = len(HEIGHT_BINS) - 1
    band_totals = D["cube_band"].sum(axis=0)
    point = {"global": fit_lca(D["cube_all"].sum(axis=0), seed=args.seed),
             "band": [fit_lca(band_totals[b], seed=args.seed) for b in range(n_bins)]}
    boot = block_bootstrap(D, point, args.boot, args.seed + 1)
    report(D, point, boot, args.label)

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        G = point["global"]
        (LOGS_DIR / f"phase4_qc_latent_class_{args.label}_{ts}.log").write_text(
            f"phase4_qc_latent_class.py label={args.label} decim={args.decim} "
            f"block={args.block} boot={args.boot} valid={D['n_valid']} chm={D['n_chm']} "
            + ("" if G is None else
               f"pi={G['pi']:.4f} se={np.round(G['se'], 4).tolist()} "
               f"sp={np.round(G['sp'], 4).tolist()}") + "\n",
            encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
