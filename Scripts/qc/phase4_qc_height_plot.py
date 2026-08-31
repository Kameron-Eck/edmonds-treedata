"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — HEIGHT-CURVE COMPARISON PLOT   (honest-measurement-overhaul, P4)
  Edmonds Temporal Active Learning Pipeline

  The single clearest picture of the 2026-08-18 investigation: canopy
  detection is a FUNCTION OF HEIGHT, the deficit is inherited from the label
  source, and corrected labels lift the low bands hardest.

  Draws one line per height_curve_*.csv in phase4/qc/ — so it grows as more
  curves are produced. Computes nothing itself; the CSVs are the source of
  truth, as with the accuracy dashboard.

  The three curves it was built for:
    2020_labelsource  the Phase-3 mask that SUPPLIES coarse-year labels
    2016_baseline     a model trained on that mask
    2016_corrected    the same year retrained with the NIR+CHM overlay

  DESIGN (dataviz skill)
    * A line chart, because the question is shape across an ordered band —
      does detection rise with height, and does a treatment change that rise.
    * One axis. All three series are recall on 0-1, same unit.
    * Categorical hues in fixed order, never cycled; validated for CVD
      separation on the light surface. Endpoints carry direct value labels
      (the relief rule), so identity never depends on colour alone.

  USAGE
    py -3.12 phase4_qc_height_plot.py
    py -3.12 phase4_qc_height_plot.py --only 2016_baseline,2016_corrected

  OUTPUT
    phase4/qc/height_curves.png
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import io
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                # noqa: E402
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
import sys as _sys_lake
from pathlib import Path as _P_lake
_sys_lake.path.insert(0, str(_P_lake(__file__).resolve().parents[1] / "pipeline"))
from lake import BASE  # noqa: E402
QC_DIR = BASE / "phase4" / "qc"

SURFACE, INK, INK_2, INK_3, GRID = "#fcfcfb", "#1a1a19", "#42403c", "#6b6b68", "#e3e3e0"
# fixed categorical order, never cycled
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]

# Curves we know how to caption. Anything else still plots, unlabelled.
KNOWN = {
    "2020_labelsource": "2020 mask — the LABEL SOURCE for coarse years",
    "2016_baseline":    "2016 model — trained on that mask",
    "2016_corrected":   "2016 + corrected labels (--add-canopy-mask)",
}
ORDER = ["2020_labelsource", "2016_baseline", "2016_corrected"]


def load(only=None):
    out = {}
    for p in sorted(QC_DIR.glob("height_curve_*.csv")):
        name = p.stem.replace("height_curve_", "")
        if only and name not in only:
            continue
        rows = list(csv.DictReader(io.open(p, encoding="utf-8", newline="")))
        pts = []
        for r in rows:
            try:
                lo, hi = float(r["band_lo_m"]), float(r["band_hi_m"])
                pts.append((lo, hi, float(r["recall"])))
            except (KeyError, TypeError, ValueError):
                continue
        if pts:
            out[name] = pts
    return out


def build(curves, out):
    if not curves:
        print("[height-plot] no height_curve_*.csv found — nothing drawn.")
        return False

    names = [n for n in ORDER if n in curves] + [n for n in curves if n not in ORDER]
    fig, ax = plt.subplots(figsize=(10.5, 6.0), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    # x positions = band index; label with the band range
    ref = curves[names[0]]
    xs = list(range(len(ref)))
    labels = [f"{int(lo)}-{int(hi)}" if hi < 100 else f"{int(lo)}+" for lo, hi, _ in ref]

    for i, n in enumerate(names):
        col = SLOTS[i % len(SLOTS)]
        pts = curves[n]
        y = [r for _, _, r in pts]
        x = list(range(len(y)))
        ax.plot(x, y, color=col, lw=2.0, marker="o", markersize=6.5,
                markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3,
                label=KNOWN.get(n, n))
        # direct value labels on the endpoints (relief rule)
        ax.annotate(f"{y[0]:.2f}", (x[0], y[0]), textcoords="offset points",
                    xytext=(-10, -4), ha="right", fontsize=9, color=INK, zorder=4)
        ax.annotate(f"{y[-1]:.2f}", (x[-1], y[-1]), textcoords="offset points",
                    xytext=(10, -4), ha="left", fontsize=9, color=INK, zorder=4)

    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=10, color=INK_2)
    ax.set_ylim(0, 1.02)
    ax.set_yticks([0, .25, .5, .75, 1.0])
    ax.tick_params(colors=INK_3, length=0)
    ax.set_xlabel("canopy height band (m, from the lidar CHM)", fontsize=10.5, color=INK_2)
    ax.set_ylabel("recall vs C-CAP canopy", fontsize=10.5, color=INK_2)
    ax.set_title("Detection is a function of canopy height",
                 fontsize=15, color=INK, loc="left", pad=14)
    ax.grid(axis="y", color=GRID, lw=.9, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    ax.legend(frameon=False, fontsize=10, loc="upper left", bbox_to_anchor=(0, -0.13),
              ncol=1, labelcolor=INK_2)

    fig.text(0.008, -0.10,
             "The label source carries the same staircase as the model it teaches, and sits below it at "
             "every band — the deficit is\ninherited, not developed during fine-tuning. Corrected labels "
             "lift the low bands hardest (+.34 at 2-5 m vs +.06 at 30 m+),\nbut adopt the NDVI "
             "reference's canopy definition, so the gain cannot be adjudicated without human labels.",
             fontsize=9, color=INK_3, va="top", linespacing=1.6)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"[height-plot] wrote {out}")
    return True


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(description="Plot recall-by-height curves.")
    ap.add_argument("--only", default=None, help="Comma-separated curve names.")
    ap.add_argument("--out", default=str(QC_DIR / "height_curves.png"))
    args = ap.parse_args(argv)
    only = {x.strip() for x in args.only.split(",")} if args.only else None
    curves = load(only)
    for n, pts in curves.items():
        print(f"[height-plot] {n:<20} {len(pts)} bands  "
              f"{pts[0][2]:.3f} -> {pts[-1][2]:.3f}")
    build(curves, Path(args.out))


if __name__ == "__main__":
    main()
