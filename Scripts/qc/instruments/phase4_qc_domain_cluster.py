"""
+==================================================================+
  PHASE 4 - DO OUR ACQUISITIONS SEPARATE INTO DOMAINS? (open question Q5)
  Edmonds Temporal Active Learning Pipeline

  WHY
  ---
  We have always grouped acquisitions by AGENCY - King County / Snohomish /
  NAIP / City of Edmonds - and built per-(sensor x era) anchors on that basis.
  Kam, 2026-08-18: "Edmonds and King County use EagleView in the later years,
  and King County switched contractors many times. There may be more than a
  few different sensors."

  If that is right, AGENCY IS NOT SENSOR, and the anchor grouping is wrong.
  The fix is not to guess a better grouping - it is to let the imagery say.

  WHAT THIS DOES
  --------------
  Reads the per-band statistics already in imagery_stats/imagery_summary.txt
  (no imagery is opened - this is free) and clusters the acquisitions on their
  RGB radiometric signature: mean and std of R, G, B, standardised.

  Then reports:
    * the pairwise distance matrix, nearest neighbour per year
    * agglomerative clusters at a few cut levels
    * whether the resulting groups agree with the AGENCY labels

  READ THE CAVEATS AT THE BOTTOM OF THE OUTPUT BEFORE BELIEVING ANY OF IT.
  Band statistics are a weak, confounded proxy for "sensor": footprint,
  season, and sun angle all move them. This is a SCREEN, not a verdict - it
  says where to look, and a negative result is more informative than a
  positive one. The proper instrument is the low-frequency amplitude
  signature (Literature_Tracker ID 136, Yang & Soatto FDA), which needs the
  imagery.

  USAGE
    py -3.12 phase4_qc_domain_cluster.py [--k 4]

  OUTPUT
    phase4/qc/domain_cluster.txt / .csv
+==================================================================+
"""

import argparse
import csv
import datetime as _dt
import io
import re
import sys
from pathlib import Path

import numpy as np
from phase4seg.names import clean_argv  # noqa: E402

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"
SUMMARY = BASE / "imagery_stats" / "imagery_summary.txt"

BANDS = ("Red", "Green", "Blue")


def parse_summary(path):
    """Pull per-image GSD/source from the detail table and mean/std from the
    band-statistics block. Returns {label: dict}."""
    txt = io.open(path, encoding="utf-8").read()
    rec = {}

    # detail table rows: label source GSD bands dims area epsg mb
    for m in re.finditer(
        r"^\s{2}(\S+)\s+(King County|Snohomish Co\.|City of Edmonds|NAIP)\s+"
        r"([\d.]+)cm\s+(\d)\s", txt, re.M):
        rec[m.group(1)] = {"source": m.group(2), "gsd": float(m.group(3)),
                           "nbands": int(m.group(4))}

    # band-statistics blocks
    for blk in re.finditer(r"^  (\S+) \((RGBI? \(\d-band\))\):\n((?:    \S+.*\n)+)",
                           txt, re.M):
        label, body = blk.group(1), blk.group(3)
        if label not in rec:
            continue
        for bm in re.finditer(r"^    (\w+)\s+min=(-?[\d.]+)\s+mean=([\d.]+)\s+"
                              r"max=(-?[\d.]+)\s+std=([\d.]+)", body, re.M):
            b = bm.group(1)
            rec[label][f"{b}_mean"] = float(bm.group(3))
            rec[label][f"{b}_std"] = float(bm.group(5))
    return rec


def build_matrix(rec):
    labels, rows = [], []
    for lab, d in rec.items():
        feats = []
        ok = True
        for b in BANDS:
            if f"{b}_mean" not in d:
                ok = False
                break
            feats += [d[f"{b}_mean"], d[f"{b}_std"]]
        if ok:
            labels.append(lab)
            rows.append(feats)
    X = np.array(rows, dtype=float)
    Z = (X - X.mean(0)) / X.std(0)          # standardise each feature
    return labels, X, Z


def agglomerative(Z, labels, k):
    """Minimal complete-linkage agglomerative clustering (no scipy needed)."""
    clusters = [[i] for i in range(len(labels))]
    D = np.linalg.norm(Z[:, None, :] - Z[None, :, :], axis=-1)
    while len(clusters) > k:
        best, bi, bj = None, None, None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = max(D[i, j] for i in clusters[a] for j in clusters[b])
                if best is None or d < best:
                    best, bi, bj = d, a, b
        clusters[bi] = clusters[bi] + clusters[bj]
        del clusters[bj]
    return clusters


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(description="Cluster acquisitions on radiometric signature.")
    ap.add_argument("--k", type=int, nargs="*", default=[3, 4, 5],
                    help="Cluster counts to report (default 3 4 5).")
    args = ap.parse_args(argv)

    if not SUMMARY.exists():
        raise SystemExit(f"[domain-cluster] ABORT: {SUMMARY} not found. "
                         "Regenerate it before running this.")

    rec = parse_summary(SUMMARY)
    labels, X, Z = build_matrix(rec)
    if len(labels) < 4:
        raise SystemExit(f"[domain-cluster] ABORT: parsed only {len(labels)} "
                         "acquisitions with full RGB statistics — parser or file changed.")

    D = np.linalg.norm(Z[:, None, :] - Z[None, :, :], axis=-1)
    np.fill_diagonal(D, np.inf)

    L = ["DO OUR ACQUISITIONS SEPARATE INTO DOMAINS? (Q5 screen)",
         f"  source   : {SUMMARY}",
         f"  features : mean+std of R,G,B (standardised) - {len(labels)} acquisitions",
         "",
         "  NEAREST NEIGHBOUR BY RADIOMETRIC SIGNATURE",
         "  (does the nearest year share the same AGENCY?)",
         "",
         f"  {'year':<8}{'agency':<18}{'GSD':>7}   {'nearest':<8}{'nearest agency':<18}{'dist':>6}  same?"]

    agree = 0
    for i, lab in enumerate(labels):
        j = int(np.argmin(D[i]))
        same = rec[lab]["source"] == rec[labels[j]]["source"]
        agree += same
        L.append(f"  {lab:<8}{rec[lab]['source']:<18}{rec[lab]['gsd']:>6.1f}   "
                 f"{labels[j]:<8}{rec[labels[j]]['source']:<18}{D[i, j]:>6.2f}  "
                 f"{'YES' if same else 'no'}")
    L += ["",
          f"  nearest neighbour shares agency: {agree}/{len(labels)} "
          f"({100*agree/len(labels):.0f}%)",
          "  If this is near chance, AGENCY IS NOT THE DOMAIN AXIS.",
          ""]

    for k in args.k:
        cl = agglomerative(Z, labels, k)
        L.append(f"  --- {k} CLUSTERS " + "-" * 40)
        for c in sorted(cl, key=lambda c: min(c)):
            members = [labels[i] for i in sorted(c)]
            srcs = sorted({rec[labels[i]]['source'] for i in c})
            gsds = sorted({rec[labels[i]]['gsd'] for i in c})
            L.append(f"    {', '.join(members)}")
            L.append(f"        agencies: {', '.join(srcs)}")
            L.append(f"        GSDs    : {', '.join(f'{g:g}cm' for g in gsds)}")
        L.append("")

    L += ["  CAVEATS - READ BEFORE BELIEVING ANY OF THIS",
          "    * Band statistics are a WEAK, CONFOUNDED proxy for 'sensor'.",
          "      Footprint, season, sun angle and scene content all move them.",
          "      2016/2021s cover 66.7% of the city and the NAIP frames cover",
          "      53.8 km2 vs 176 km2 - so those means are not measured over the",
          "      same ground as the rest and are NOT strictly comparable.",
          "    * This is a SCREEN, not a verdict. A negative result (no clean",
          "      separation) is more informative than a positive one.",
          "    * The proper instrument is the low-frequency AMPLITUDE signature",
          "      (Literature_Tracker ID 136, Yang & Soatto, FDA, CVPR 2020):",
          "      amplitude carries style, phase carries content. That needs the",
          "      imagery but is still label-free and GPU-free.",
          "    * Ground truth for sensor/contractor is acquisition METADATA, not",
          "      pixels. If that metadata exists, it beats this entirely."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / "domain_cluster.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / "domain_cluster.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "agency", "gsd_cm", "nbands"]
                   + [f"{b}_{s}" for b in BANDS for s in ("mean", "std")]
                   + ["nearest", "nearest_agency", "dist", "same_agency"])
        for i, lab in enumerate(labels):
            j = int(np.argmin(D[i]))
            w.writerow([lab, rec[lab]["source"], rec[lab]["gsd"], rec[lab]["nbands"]]
                       + [rec[lab][f"{b}_{s}"] for b in BANDS for s in ("mean", "std")]
                       + [labels[j], rec[labels[j]]["source"], round(float(D[i, j]), 3),
                          rec[lab]["source"] == rec[labels[j]]["source"]])
    print(f"\n[domain-cluster] wrote {QC_DIR / 'domain_cluster.txt'}")

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_domain_cluster_{ts}.log").write_text(
            f"phase4_qc_domain_cluster.py n={len(labels)} agency_agree={agree}\n",
            encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
