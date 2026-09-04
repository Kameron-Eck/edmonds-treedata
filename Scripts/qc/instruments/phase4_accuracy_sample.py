r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — HUMAN ACCURACY SAMPLE  (honest-measurement-overhaul, P3)
  Edmonds Temporal Active Learning Pipeline

  The ONLY measurement in this project with no model and no proxy product
  standing between Kam and the answer. Everything else — C-CAP, the NDVI+CHM
  reference, the 2020 mask — is a stand-in that carries its own bias.

  WHY IT IS NOW THE BLOCKER (2026-08-18)
  --------------------------------------
    * The two references DISAGREE ON 15-17% OF PIXELS, replicated across four
      years and three sensors. On 2021s they differ by 12 points on the SAME
      year and ground, so it is not vintage drift.
    * The corrected-label experiment (2016c) lifted recall .684 -> .872 but
      adopted the NDVI reference's canopy DEFINITION. Whether that made the
      model more CORRECT or merely more LIBERAL lives entirely inside the
      contested zone. No proxy can adjudicate it.
    * Detection is a function of canopy height: recall .16 below 5 m rising to
      .93 above 30 m, with 5-15 m holding 53% of all missed pixels.

  STRATIFICATION — CHANGED FROM THE ORIGINAL PLAN, DELIBERATELY
  ------------------------------------------------------------
  The plan first proposed stratifying by MODEL OUTPUT (canopy / non-canopy /
  near-threshold). The findings superseded that: uniform strata would spend
  most of the sample on ground both references already agree about, which
  needs no adjudication. Instead the strata cross REFERENCE AGREEMENT with
  CANOPY HEIGHT, so points land where the information is:

      1  DISAGREE      x  5-15 m      <- contested AND the worst-recall band
      2  DISAGREE      x  other       <- contested
      3  BOTH_CANOPY   x  5-15 m      <- the band the model actually misses
      4  BOTH_CANOPY   x  other
      5  BOTH_NONCANOPY               <- needed for precision + area estimates
      6  NO CHM                       <- CHM covers only ~60% of the city;
                                         excluding it would bias the estimate

  Every stratum keeps its true area, so the Olofsson estimators correct the
  over-sampling back to unbiased city-wide numbers. Over-sampling the
  interesting strata costs precision NOWHERE — it buys precision where the
  question is.

  STEPS
    --step design    draw the sample            -> qc/sample_{year}.gpkg + .csv
    --step serve     browser photo-interpreter  -> qc/sample_{year}_labels.csv
    --step estimate  Olofsson estimators        -> qc/accuracy_{year}.txt + .csv

  Unsure is a first-class answer and is EXCLUDED from estimation, never
  coerced — the same three-state discipline as the mask labels (rule 6).

  USAGE
    py -3.12 phase4_accuracy_sample.py --step design --year 2016 --n 250
    py -3.12 phase4_accuracy_sample.py --step serve  --year 2016
    py -3.12 phase4_accuracy_sample.py --step estimate --year 2016
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime
import http.server
import io
import json
import math
import socketserver
import threading
from pathlib import Path

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine, xy
from rasterio.warp import transform as warp_transform
from phase4seg.names import clean_argv  # noqa: E402

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402
QC_DIR = BASE / "phase4" / "qc"
MASKS = BASE / "phase4" / "masks"

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
# chm2 REPLACED lidar_snoh_chm.tif 2026-09-03: the old raster reads +4.1-5.4 m
# high in every bin and calls 8.82% of certified-flat ground >2 m (config.py
# chm2 block); strata drawn from it put the "5-15 m" band at ~0-11 m true.
# Same DN encoding (1 + round(h/0.2), 0 = nodata) — decode below unchanged.
CHM_NAME = "lidar_chm2_2016_50cm.tif"
CHM_DN_PER_M = 1.0 / 0.2

CCAP_CANOPY = [9, 10, 11, 13, 16]
NDVI_CANOPY = 2

# stratum id -> (name, default share of the sample)
#
# TWO SCHEMES. Years with NIR have a second reference (NDVI+CHM) and therefore a
# measurable DISAGREEMENT zone — that is where the sample earns most, so it gets
# most of the points. Years without NIR (2000, 2002, 2013, 2015, 2017) have only
# C-CAP; there is no disagreement to adjudicate, so the sample falls back to
# stratifying by C-CAP class crossed with canopy height. Height stays in both
# schemes because detection is a function of height and the 5-15 m band holds
# 53% of all misses.
STRATA_DUAL = {
    1: ("disagree_5_15m",      0.24),
    2: ("disagree_other",      0.18),
    3: ("both_canopy_5_15m",   0.16),
    4: ("both_canopy_other",   0.10),
    5: ("both_noncanopy",      0.20),
    6: ("no_chm",              0.12),
}
STRATA_SINGLE = {
    1: ("ccap_canopy_5_15m",   0.30),
    2: ("ccap_canopy_other",   0.22),
    3: ("ccap_noncanopy",      0.28),
    4: ("no_chm",              0.20),
}
STRATA = STRATA_DUAL          # rebound per-run by build_strata()


def resolve(name, *dirs):
    for d in dirs:
        p = Path(d) / name
        if p.exists():
            return p
    raise FileNotFoundError(name)


def build_strata(prob_path, ccap_path, ndvi_path, thresh, decim):
    """Strata map on a decimated lattice + true area weight per cell."""
    chm_path = resolve(CHM_NAME, _LOCAL_IMG, _DRIVE_IMG)
    with rasterio.open(prob_path) as p:
        H, W = p.height // decim, p.width // decim
        dt = p.transform * Affine.scale(decim)
        crs = p.crs
        nod = 255 if p.nodata is None else p.nodata
        pr = p.read(1, out_shape=(H, W), resampling=Resampling.nearest)

    def warp(path, **kw):
        with rasterio.open(path) as src:
            with WarpedVRT(src, crs=crs, transform=dt, width=W, height=H,
                           resampling=Resampling.nearest, **kw) as v:
                return v.read(1), src.nodata

    cc, cc_nod = warp(ccap_path)
    dn, _ = warp(chm_path, src_nodata=0, nodata=0)
    dual = ndvi_path is not None and Path(ndvi_path).exists()
    nd = warp(ndvi_path)[0] if dual else None

    hgt = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    hgt[dn == 0] = np.nan

    valid = pr != nod
    if cc_nod is not None:
        valid &= cc != cc_nod
    valid &= cc != 0

    global STRATA
    cc_can = np.isin(cc, CCAP_CANOPY)
    has_chm = np.isfinite(hgt)
    mid = has_chm & (hgt >= 5) & (hgt < 15)
    strata = np.zeros((H, W), dtype=np.uint8)

    if dual:
        STRATA = STRATA_DUAL
        nd_can = nd == NDVI_CANOPY
        disagree = cc_can ^ nd_can
        both_can = cc_can & nd_can
        strata[valid & ~has_chm] = 6
        strata[valid & has_chm & ~disagree & ~both_can] = 5
        strata[valid & has_chm & both_can & ~mid] = 4
        strata[valid & has_chm & both_can & mid] = 3
        strata[valid & has_chm & disagree & ~mid] = 2
        strata[valid & has_chm & disagree & mid] = 1
    else:
        # No NIR for this year, so no second reference and no adjudicable
        # disagreement. Stratify by C-CAP class x height instead, and SAY SO in
        # the metadata — a single-reference estimate answers a narrower question
        # and must not be reported as if it settled a contested zone.
        STRATA = STRATA_SINGLE
        print("  ! no NDVI reference for this year (no NIR band) — falling back to")
        print("    SINGLE-REFERENCE strata (C-CAP class x height). This sample can")
        print("    estimate accuracy, but it CANNOT adjudicate reference disagreement.")
        strata[valid & ~has_chm] = 4
        strata[valid & has_chm & ~cc_can] = 3
        strata[valid & has_chm & cc_can & ~mid] = 2
        strata[valid & has_chm & cc_can & mid] = 1

    scheme = "dual_reference" if dual else "single_reference"

    model = (pr >= thresh * 254.0)
    return dict(strata=strata, model=model, transform=dt, crs=crs,
                decim=decim, shape=(H, W), scheme=scheme)


def step_design(year, prob_path, ccap_path, ndvi_path, thresh, n, decim, seed):
    S = build_strata(prob_path, ccap_path, ndvi_path, thresh, decim)
    strata, model = S["strata"], S["model"]
    rng = np.random.default_rng(seed)

    counts = {sid: int((strata == sid).sum()) for sid in STRATA}
    total = sum(counts.values())
    if total == 0:
        raise SystemExit("no valid cells — check the inputs overlap")

    # allocation: the configured share, but never more points than cells
    alloc = {}
    for sid, (name, share) in STRATA.items():
        alloc[sid] = min(counts[sid], int(round(n * share)))
    # top up / trim to exactly n using the largest strata
    while sum(alloc.values()) < n:
        sid = max(STRATA, key=lambda k: counts[k] - alloc[k])
        if counts[sid] - alloc[sid] <= 0:
            break
        alloc[sid] += 1
    while sum(alloc.values()) > n:
        sid = max(alloc, key=lambda k: alloc[k])
        alloc[sid] -= 1

    rows = []
    pid = 0
    for sid, (name, _) in STRATA.items():
        k = alloc[sid]
        if k <= 0:
            continue
        idx = np.flatnonzero(strata.ravel() == sid)
        pick = rng.choice(idx, size=k, replace=False)
        rr, cc_ = np.unravel_index(pick, S["shape"])
        xs, ys = xy(S["transform"], rr, cc_, offset="center")
        lon, lat = warp_transform(S["crs"], "EPSG:4326", list(np.atleast_1d(xs)),
                                  list(np.atleast_1d(ys)))
        for i in range(k):
            pid += 1
            rows.append(dict(
                point_id=pid, stratum=sid, stratum_name=name,
                row=int(rr[i]), col=int(cc_[i]),
                x=float(np.atleast_1d(xs)[i]), y=float(np.atleast_1d(ys)[i]),
                lon=round(float(lon[i]), 7), lat=round(float(lat[i]), 7),
                model_canopy=int(model[rr[i], cc_[i]]),
            ))

    QC_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = QC_DIR / f"sample_{year}.csv"
    with io.open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    meta = dict(year=year, seed=seed, decim=decim, thresh=thresh,
                scheme=S["scheme"],
                prob=Path(prob_path).name, ccap=Path(ccap_path).name,
                ndvi=(Path(ndvi_path).name if ndvi_path else None), crs=str(S["crs"]),
                n_requested=n, n_drawn=len(rows),
                strata={str(sid): dict(name=STRATA[sid][0],
                                       cells=counts[sid],
                                       sampled=alloc[sid],
                                       area_share=counts[sid] / total)
                        for sid in STRATA})
    (QC_DIR / f"sample_{year}_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\n  STRATIFIED SAMPLE — {year}   (seed {seed}, lattice 1/{decim})")
    print(f"  {'stratum':<22}{'cells':>14}{'area %':>9}{'points':>8}")
    for sid, (name, _) in STRATA.items():
        print(f"  {name:<22}{counts[sid]:>14,}{100*counts[sid]/total:>8.2f}%{alloc[sid]:>8}")
    print(f"  {'TOTAL':<22}{total:>14,}{100:>8.2f}%{sum(alloc.values()):>8}")
    print(f"\n  wrote {out_csv}")
    print(f"  wrote {QC_DIR / f'sample_{year}_meta.json'}")
    print(f"\n  Next: --step serve --year {year}   (photo-interpret each point)")


def step_estimate(year):
    meta_p = QC_DIR / f"sample_{year}_meta.json"
    lab_p = QC_DIR / f"sample_{year}_labels.csv"
    samp_p = QC_DIR / f"sample_{year}.csv"
    for p in (meta_p, samp_p):
        if not p.exists():
            raise SystemExit(f"missing {p} — run --step design first")
    if not lab_p.exists():
        raise SystemExit(f"missing {lab_p} — run --step serve and label the points first")

    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    samp = {int(r["point_id"]): r for r in
            csv.DictReader(io.open(samp_p, encoding="utf-8", newline=""))}
    labels = {}
    for r in csv.DictReader(io.open(lab_p, encoding="utf-8", newline="")):
        lab = r["label"].strip().lower()
        # The labels CSV is an append-only event log; "undo" retracts the point's
        # standing decision (same fold as step_serve._final). Without this, a
        # trailing undo was scored as a fabricated non-canopy truth.
        if lab == "undo":
            labels.pop(int(r["point_id"]), None)
        else:
            labels[int(r["point_id"])] = lab

    # Olofsson stratified estimation. Population units are lattice cells; each
    # stratum h has known weight W_h = N_h / N. Within-stratum sample means of
    # the indicator variables give the confusion cells, and the estimator
    # re-weights them back to the population.
    strata_meta = {int(k): v for k, v in meta["strata"].items()}
    N = sum(v["cells"] for v in strata_meta.values())

    acc = {h: dict(n=0, tp=0, fp=0, fn=0, tn=0, unsure=0) for h in strata_meta}
    for pid, row in samp.items():
        lab = labels.get(pid)
        if lab is None:
            continue
        h = int(row["stratum"])
        a = acc[h]
        if lab in ("unsure", "u", ""):
            a["unsure"] += 1
            continue
        truth = lab in ("canopy", "c", "yes", "1")
        pred = row["model_canopy"] == "1"
        a["n"] += 1
        if truth and pred:   a["tp"] += 1
        elif not truth and pred: a["fp"] += 1
        elif truth and not pred: a["fn"] += 1
        else: a["tn"] += 1

    # ── Stratified estimation with the FULL multinomial covariance ──────────
    # Within a stratum the four confusion cells are one multinomial draw, so
    # they are NEGATIVELY correlated:
    #     Var(p_i)    =  p_i(1-p_i) / (n_h - 1)
    #     Cov(p_i,p_j) = -p_i p_j    / (n_h - 1)
    # An earlier version summed Var(tp)+Var(fn) for the canopy-area interval,
    # which drops that covariance and OVERSTATES the CI. Carrying the whole
    # covariance matrix is barely more code and gets area, recall and precision
    # right from one place.
    CELLS = ("tp", "fp", "fn", "tn")
    P_ = {c: 0.0 for c in CELLS}
    V = {(a, b): 0.0 for a in CELLS for b in CELLS}
    labelled = 0
    used_strata = 0

    for h, m in strata_meta.items():
        a = acc[h]
        n = a["n"]
        if n == 0:
            continue
        labelled += n
        used_strata += 1
        W = m["cells"] / N
        p = {c: a[c] / n for c in CELLS}
        for c in CELLS:
            P_[c] += W * p[c]
        if n > 1:
            for i in CELLS:
                for j in CELLS:
                    term = (p[i] * (1 - p[i]) if i == j else -p[i] * p[j]) / (n - 1)
                    V[(i, j)] += W * W * term

    def var_of(weights):
        """Variance of a linear combination sum(w_c * P_c)."""
        return sum(weights.get(i, 0) * weights.get(j, 0) * V[(i, j)]
                   for i in CELLS for j in CELLS)

    def ratio_ci(num_w, den_w):
        """Delta-method 95% half-width for (sum num) / (sum den).

        Var(X/Y) ~= (1/Y^2)[Var(X) + R^2 Var(Y) - 2 R Cov(X,Y)]
        APPROXIMATE: the strata here are defined by reference agreement and
        height, NOT by the map classes the textbook estimators assume, so treat
        these intervals as indicative. Resolving the exact estimator for
        non-map strata is Search 9 of the Phase-4 literature review.
        """
        X = sum(w * P_[c] for c, w in num_w.items())
        Y = sum(w * P_[c] for c, w in den_w.items())
        if Y <= 0:
            return float("nan"), float("nan")
        R = X / Y
        vX, vY = var_of(num_w), var_of(den_w)
        cXY = sum(num_w.get(i, 0) * den_w.get(j, 0) * V[(i, j)]
                  for i in CELLS for j in CELLS)
        var = (vX + R * R * vY - 2 * R * cXY) / (Y * Y)
        return R, 1.96 * math.sqrt(max(var, 0.0))

    p_tp, p_fp, p_fn, p_tn = (P_["tp"], P_["fp"], P_["fn"], P_["tn"])

    # true canopy area = tp + fn, WITH the covariance term
    area_true = p_tp + p_fn
    ci_area = 1.96 * math.sqrt(max(var_of({"tp": 1, "fn": 1}), 0.0))

    recall, ci_recall = ratio_ci({"tp": 1}, {"tp": 1, "fn": 1})
    prec, ci_prec = ratio_ci({"tp": 1}, {"tp": 1, "fp": 1})

    L = [f"HUMAN ACCURACY ESTIMATE — {year}   (Olofsson stratified)",
         f"  sample : {meta['n_drawn']} points, {labelled} labelled, "
         f"{sum(a['unsure'] for a in acc.values())} unsure (EXCLUDED, never coerced)",
         f"  model  : {meta['prob']} @ thresh {meta['thresh']}",
         "",
         f"  recall     {recall:.4f}  ± {ci_recall:.4f}   (95% CI, approx)",
         f"  precision  {prec:.4f}  ± {ci_prec:.4f}   (95% CI, approx)",
         f"  true canopy area  {100*area_true:.2f}%  ± {100*ci_area:.2f}  (95% CI)",
         f"  model canopy area {100*(p_tp+p_fp):.2f}%",
         f"  strata contributing: {used_strata} of {len(strata_meta)}",
         "",
         "  PER-STRATUM (unweighted counts — the estimator re-weights these):",
         f"  {'stratum':<22}{'n':>5}{'tp':>6}{'fp':>6}{'fn':>6}{'tn':>6}{'unsure':>8}"]
    for h, m in strata_meta.items():
        a = acc[h]
        L.append(f"  {m['name']:<22}{a['n']:>5}{a['tp']:>6}{a['fp']:>6}"
                 f"{a['fn']:>6}{a['tn']:>6}{a['unsure']:>8}")
    L += ["",
          "  These are the only numbers in this project with no model and no proxy",
          "  product between the estimate and the ground.",
          "",
          "  CI NOTE: the area interval is exact for stratified sampling (it carries",
          "  the full multinomial covariance). The recall/precision intervals are",
          "  DELTA-METHOD APPROXIMATIONS, and these strata are defined by reference",
          "  agreement and height rather than by map class, which the textbook",
          "  estimators assume. Treat them as indicative until Search 9 of the",
          "  Phase-4 literature review settles the exact form."]
    txt = "\n".join(L)
    print("\n" + txt)
    (QC_DIR / f"accuracy_{year}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"accuracy_{year}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in (("recall", recall), ("ci95_recall", ci_recall),
                     ("precision", prec), ("ci95_precision", ci_prec),
                     ("true_canopy_frac", area_true), ("ci95_canopy_frac", ci_area),
                     ("model_canopy_frac", p_tp + p_fp), ("n_labelled", labelled)):
            w.writerow([k, round(v, 6) if isinstance(v, float) else v])
    print(f"\n  wrote {QC_DIR / f'accuracy_{year}.txt'}")



def _chip(src, x, y, span_m, px=430):
    """One square chip centred on (x, y) in the raster CRS, with a crosshair.

    The crosshair is four ticks pointing AT the centre rather than a cross
    drawn over it — the interpreter has to judge the pixel under the mark, so
    the mark must not cover it.
    """
    from PIL import Image, ImageDraw
    res = abs(src.transform.a)
    half = (span_m / 2.0) / res
    r, c = ~src.transform * (x, y)
    win = rasterio.windows.Window(int(c - half), int(r - half),
                                  max(int(2 * half), 2), max(int(2 * half), 2))
    bands = [1, 2, 3] if src.count >= 3 else [1, 1, 1]
    # NEVER upscale in the chip. At 50-60 cm GSD a 40 m window is only ~70-80
    # native pixels; bilinear-stretching that to 430 px invents detail the
    # imagery does not contain, which is exactly the wrong failure for an
    # instrument built to make honest judgements possible. Render at native
    # resolution (capped) and let the browser scale it with pixelated
    # rendering, so the interpreter sees real pixels and knows it.
    native = max(int(2 * half), 2)
    out = min(px, native)
    a = src.read(bands, window=win, boundless=True, fill_value=0,
                 out_shape=(3, out, out), resampling=Resampling.nearest)
    px = out
    img = Image.fromarray(np.transpose(a, (1, 2, 0)).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    m = px // 2
    gap, ln = px // 26, px // 11
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        d.line([(m + dx * gap, m + dy * gap),
                (m + dx * (gap + ln), m + dy * (gap + ln))],
               fill=(255, 232, 66), width=3)
    return img


def step_serve(year, ortho_path, port, ctx_m, det_m):
    samp_p = QC_DIR / f"sample_{year}.csv"
    if not samp_p.exists():
        raise SystemExit(f"missing {samp_p} - run --step design first")
    rows = list(csv.DictReader(io.open(samp_p, encoding="utf-8", newline="")))

    root = QC_DIR / f"review_{year}"
    chips = root / "chips"
    chips.mkdir(parents=True, exist_ok=True)

    todo = [r for r in rows if not (chips / f"{r['point_id']}_det.jpg").exists()]
    if todo:
        print(f"  cutting chips for {len(todo)} points from {Path(ortho_path).name} ...")
        with rasterio.open(ortho_path) as src:
            for k, r in enumerate(todo, 1):
                x, y = float(r["x"]), float(r["y"])
                _chip(src, x, y, det_m).save(chips / f"{r['point_id']}_det.jpg", quality=88)
                _chip(src, x, y, ctx_m).save(chips / f"{r['point_id']}_ctx.jpg", quality=85)
                if k % 25 == 0 or k == len(todo):
                    print(f"    {k}/{len(todo)}", flush=True)
    else:
        print("  chips already present - reusing them.")

    manifest = dict(year=year, ctx_m=ctx_m, det_m=det_m, points=[
        dict(id=int(r["point_id"]), stratum=r["stratum_name"],
             lat=r["lat"], lon=r["lon"], ctx_m=ctx_m, det_m=det_m) for r in rows])
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # The UI is a sibling asset, refreshed every serve so edits land without
    # re-cutting chips.
    app_src = Path(__file__).with_name("phase4_accuracy_review.html")
    if not app_src.exists():
        raise SystemExit(f"missing UI asset {app_src}")
    (root / "review_app.html").write_text(
        app_src.read_text(encoding="utf-8"), encoding="utf-8")

    labels_csv = QC_DIR / f"sample_{year}_labels.csv"

    def _final():
        """Latest decision per point, honouring undo."""
        out = {}
        if labels_csv.exists():
            for r in csv.DictReader(io.open(labels_csv, encoding="utf-8", newline="")):
                if r["label"] == "undo":
                    out.pop(int(r["point_id"]), None)
                else:
                    out[int(r["point_id"])] = r["label"]
        return out

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass

        def _json(self, obj):
            b = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path.rstrip("/") == "/progress":
                self._json({"done": {str(k): v for k, v in _final().items()}})
                return
            super().do_GET()

        def do_POST(self):
            if self.path.rstrip("/") != "/label":
                self.send_response(404)
                self.end_headers()
                return
            n = int(self.headers.get("Content-Length", 0))
            pl = json.loads(self.rfile.read(n))
            new = not labels_csv.exists()
            with io.open(labels_csv, "a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["ts", "point_id", "label"])
                w.writerow([datetime.datetime.now().isoformat(timespec="seconds"),
                            pl.get("point_id"), pl.get("label")])
            self._json({"ok": True})

    srv = socketserver.ThreadingTCPServer(("", port), H)
    srv.allow_reuse_address = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    done = len(_final())
    print("\n  -- Point reviewer running --")
    print(f"  OPEN:  http://localhost:{port}/review_app.html")
    print(f"  {done} of {len(rows)} already labelled; it resumes where you left off.")
    print("  Keys: 1 canopy - 2 not canopy - 3 unsure - z undo")
    print(f"  Decisions append to {labels_csv}")
    print("  Leave this running while you review; Ctrl-C when done.")
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        print("\n  stopped - progress is saved.")
    return srv


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(description="Human accuracy sample (Olofsson).")
    ap.add_argument("--step", required=True, choices=["design", "serve", "estimate"])
    ap.add_argument("--year", required=True)
    ap.add_argument("--prob", default=None)
    ap.add_argument("--ref", default=None, help="C-CAP raster.")
    ap.add_argument("--ndvi-ref", default=None)
    ap.add_argument("--thresh", type=float, default=None)
    ap.add_argument("--n", type=int, default=250)
    ap.add_argument("--decim", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260818)
    ap.add_argument("--ortho", default=None, help="Native ortho, for --step serve.")
    ap.add_argument("--port", type=int, default=8731)
    ap.add_argument("--ctx-m", type=float, default=160.0, help="Context chip width (m).")
    ap.add_argument("--det-m", type=float, default=40.0, help="Detail chip width (m).")
    args = ap.parse_args(argv)

    if args.step == "design":
        for req in ("prob", "ref", "thresh"):
            if getattr(args, req) is None:
                raise SystemExit(f"--{req} is required for --step design")
        ndvi = Path(args.ndvi_ref) if args.ndvi_ref else (QC_DIR / f"ndvi_ref_{args.year}.tif")
        if not Path(ndvi).exists():
            ndvi = None      # single-reference fallback; build_strata reports it
        step_design(args.year, Path(args.prob), Path(args.ref), ndvi,
                    args.thresh, args.n, args.decim, args.seed)
    elif args.step == "estimate":
        step_estimate(args.year)
    else:
        if args.ortho is None:
            raise SystemExit("--ortho is required for --step serve (the year's native "
                             "ortho, e.g. D:/edmonds-pipeline/Imagery/2016_snoh_rgbi.tif)")
        step_serve(args.year, Path(args.ortho), args.port, args.ctx_m, args.det_m)


if __name__ == "__main__":
    main()
