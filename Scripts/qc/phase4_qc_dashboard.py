"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — HONEST-ACCURACY DASHBOARD   (honest-measurement-overhaul, P4)
  Edmonds Temporal Active Learning Pipeline

  One page that answers "how is the model doing, really" without anyone
  having to remember which CSV row is live or which caveat applies.

  Reads ONLY committed QC artefacts — it computes no metrics of its own:
    phase4/qc/qc_indep_report.csv     live=1, primary=1, C-CAP-referenced rows
    phase4/qc/ref_agreement_report.csv P2 partition (raw vs both-agree)

  PANELS
    1. Per-year recall & precision vs C-CAP, chronological, with the value
       printed on every bar (the reference is a proxy, so a reader must be
       able to see the number, not estimate it off an axis).
    2. The P2 correction, where it exists: raw -> both-agree, for recall and
       precision. This is the 2026-08-18 finding — ~1/3 of the apparent miss
       is reference disagreement, and precision was understated as much as
       recall.
    3. Provenance strip: sensor, C-CAP vintage distance, NIR availability.
       Every number above is scored against a PROXY, and the panel says which.

  DESIGN NOTES (dataviz skill)
    * No dual axis anywhere. Recall and precision share one 0-1 axis because
      they are the same unit; canopy fraction would be a different unit and
      therefore is NOT overlaid — it gets its own artefact if wanted.
    * Categorical hues assigned in fixed order and never cycled:
      slot1 blue = recall, slot2 orange = precision, slot3 aqua = corrected.
      Validated with the skill's validator (light surface): lightness band,
      chroma floor, CVD separation and normal-vision floor all PASS; the aqua
      sits below 3:1 contrast, so the relief rule applies and every mark
      carries a visible value label.
    * Legend present (>=2 series) AND direct labels, so identity is never
      colour-alone.

  USAGE
    py -3.12 phase4_qc_dashboard.py
    py -3.12 phase4_qc_dashboard.py --out phase4/qc/accuracy_dashboard.png

  OUTPUT
    phase4/qc/accuracy_dashboard.png
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

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
QC_DIR = BASE / "phase4" / "qc"

# Validated categorical slots, fixed order, never cycled (see module docstring).
SURFACE   = "#fcfcfb"
C_RECALL  = "#2a78d6"   # slot 1
C_PREC    = "#eb6834"   # slot 2
C_CORR    = "#1baf7a"   # slot 3
INK       = "#1a1a19"
INK_MUTED = "#6b6b68"
GRID      = "#e3e3e0"

# Per-year provenance. Every headline number is scored against a PROXY and the
# reader needs to know which one and how far off in time it is.
PROVENANCE = {
    "2000":  dict(sensor="King Co. 59.7cm", nir=False, ccap="2016 (+16y)"),
    "2002":  dict(sensor="King Co. 59.7cm", nir=False, ccap="2016 (+14y)"),
    "2013":  dict(sensor="King Co. 14.9cm", nir=False, ccap="2016 (+3y)"),
    "2015":  dict(sensor="King Co. 14.9cm", nir=False, ccap="2016 (+1y)"),
    "2016":  dict(sensor="Snohomish 50cm",  nir=True,  ccap="2016 (same)"),
    "2017":  dict(sensor="CoE 7.5cm",       nir=False, ccap="2016 (-1y)"),
    "2019n": dict(sensor="NAIP 60cm",       nir=True,  ccap="2021 (+2y)"),
    "2021s": dict(sensor="Snohomish 50cm",  nir=True,  ccap="2021 (same)"),
    "2023n": dict(sensor="NAIP 60cm",       nir=True,  ccap="2021 (-1y)"),
}
YEAR_ORDER = ["2000", "2002", "2013", "2015", "2016", "2017", "2019n", "2021s", "2023n"]


def _rows(path):
    if not path.exists():
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))


def load():
    """Live, primary, C-CAP-referenced rows + whatever P2 has produced."""
    # E05: filter to the CHAMPION arm per year — year-keyed last-wins silently
    # plotted whichever arm was last in file order (2013 has two live arms).
    # A year with live rows but no champion designation is SKIPPED AND LISTED,
    # never guessed.
    from champion import load_champions, prob_arm
    champ = load_champions()
    undesignated = set()
    live = {}
    for r in _rows(QC_DIR / "qc_indep_report.csv"):
        if r.get("live") != "1" or r.get("primary") != "1":
            continue
        if "ccap" not in (r.get("ref") or "").lower():
            continue        # NDVI-referenced rows are a different question
        y = r["year"]
        if y not in champ:
            undesignated.add(y)
            continue
        if prob_arm(r.get("prob", "")) != champ[y]:
            continue        # a non-champion arm — real, but not the deliverable
        try:
            live[y] = dict(recall=float(r["recall"]),
                           precision=float(r["precision"]),
                           prob=r.get("prob", ""))
        except (TypeError, ValueError):
            continue        # a nan row should never exist now, but never plot one
    if undesignated:
        print("  ! UNDESIGNATED years skipped (live rows exist, no champion_arms.csv "
              f"row): {sorted(undesignated)}")

    agree = {}
    for r in _rows(QC_DIR / "ref_agreement_report.csv"):
        try:
            agree[r["year"]] = dict(recall=float(r["recall_agree"]),
                                    precision=float(r["precision_agree"]),
                                    disagree=float(r["disagree_pct"]))
        except (TypeError, ValueError, KeyError):
            continue
    return live, agree


def build(live, agree, out):
    years = [y for y in YEAR_ORDER if y in live]
    if not years:
        print("[dashboard] no live C-CAP rows to plot — nothing written.")
        return False

    n = len(years)
    fig = plt.figure(figsize=(12.5, 4.2 + 0.42 * n), facecolor=SURFACE)
    gs = fig.add_gridspec(3, 1, height_ratios=[0.52 * n + 1.0, 2.4, 1.25],
                          hspace=0.90, left=0.13, right=0.97,
                          top=0.93, bottom=0.05)

    # ── Panel 1 — per-year recall & precision ────────────────────────────
    ax = fig.add_subplot(gs[0], facecolor=SURFACE)
    ypos = range(n)
    h = 0.34
    for i, y in enumerate(years):
        d = live[y]
        ax.barh(i + h/2, d["recall"], height=h, color=C_RECALL, zorder=3)
        ax.barh(i - h/2, d["precision"], height=h, color=C_PREC, zorder=3)
        ax.text(d["recall"] + .012, i + h/2, f"{d['recall']:.3f}", va="center",
                fontsize=8.5, color=INK, zorder=4)
        ax.text(d["precision"] + .012, i - h/2, f"{d['precision']:.3f}", va="center",
                fontsize=8.5, color=INK, zorder=4)
    ax.set_yticks(list(ypos)); ax.set_yticklabels(years, fontsize=9.5, color=INK)
    ax.set_xlim(0, 1.13); ax.set_xticks([0, .25, .5, .75, 1.0])
    ax.invert_yaxis()
    ax.set_xlabel("score vs C-CAP (forest_wetland, deployed threshold)",
                  fontsize=9, color=INK_MUTED)
    ax.set_title("Per-year accuracy against C-CAP — every number here is scored "
                 "against a PROXY, not ground truth",
                 fontsize=11.5, color=INK, loc="left", pad=10)
    ax.grid(axis="x", color=GRID, lw=.8, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, length=0)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=C_RECALL),
                       plt.Rectangle((0, 0), 1, 1, color=C_PREC)],
              labels=["recall", "precision"], frameon=False, fontsize=9,
              loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)

    # ── Panel 2 — the P2 correction ──────────────────────────────────────
    ax2 = fig.add_subplot(gs[1], facecolor=SURFACE)
    ay = [y for y in years if y in agree]
    if ay:
        for i, y in enumerate(ay):
            raw, cor = live[y], agree[y]
            for off, key, col in ((0.18, "recall", C_RECALL),
                                  (-0.18, "precision", C_PREC)):
                ax2.plot([raw[key], cor[key]], [i + off, i + off], color=GRID,
                         lw=2.4, zorder=2, solid_capstyle="round")
                ax2.scatter([raw[key]], [i + off], s=70, color=col, zorder=3)
                ax2.scatter([cor[key]], [i + off], s=70, color=C_CORR, zorder=3)
                ax2.text(raw[key] - .012, i + off, f"{raw[key]:.3f}", va="center",
                         ha="right", fontsize=8.5, color=INK_MUTED, zorder=4)
                ax2.text(cor[key] + .012, i + off, f"{cor[key]:.3f}", va="center",
                         fontsize=8.5, color=INK, zorder=4)
            ax2.text(0.462, i + 0.42, f"refs disagree on "
                     f"{agree[y]['disagree']:.1f}% of pixels",
                     va="center", fontsize=8.5, color=INK_MUTED, zorder=4)
        ax2.set_yticks(range(len(ay)))
        ax2.set_yticklabels(ay, fontsize=9.5, color=INK)
        ax2.set_xlim(0.45, 1.02)
        ax2.invert_yaxis()
        # room below the last row for its "refs disagree" note, which otherwise
        # lands on the axis line and collides with the tick labels
        ax2.set_ylim(len(ay) - 0.5 + 0.75, -0.75)
        ax2.set_title("Removing reference disagreement (P2): raw \u2192 scored only "
                      "where BOTH references agree",
                      fontsize=11.5, color=INK, loc="left", pad=10)
        ax2.set_xlabel("grey line spans the correction \u00b7 green = both-agree subset",
                       fontsize=9, color=INK_MUTED)
        ax2.grid(axis="x", color=GRID, lw=.8, zorder=0)
        ax2.set_axisbelow(True)
        for sp in ("top", "right", "left"):
            ax2.spines[sp].set_visible(False)
        ax2.spines["bottom"].set_color(GRID)
        ax2.tick_params(colors=INK_MUTED, length=0)
        ax2.legend(handles=[plt.Line2D([], [], marker="o", ls="", color=C_RECALL),
                            plt.Line2D([], [], marker="o", ls="", color=C_PREC),
                            plt.Line2D([], [], marker="o", ls="", color=C_CORR)],
                   labels=["raw recall", "raw precision", "both-agree"],
                   frameon=False, fontsize=9, loc="upper center",
                   bbox_to_anchor=(0.5, -0.30), ncol=3)
    else:
        ax2.axis("off")
        ax2.text(0, .5, "No P2 partition yet — run phase4_ref_agreement.py "
                        "(NIR years only).", fontsize=10, color=INK_MUTED)

    # ── Panel 3 — provenance / caveats ───────────────────────────────────
    ax3 = fig.add_subplot(gs[2], facecolor=SURFACE)
    ax3.axis("off")
    lines = ["PROVENANCE — what each year is actually scored against:"]
    for y in years:
        p = PROVENANCE.get(y)
        if p:
            lines.append(f"   {y:<6} {p['sensor']:<18} C-CAP {p['ccap']:<14}"
                         f"{'has NIR' if p['nir'] else 'no NIR'}")
    lines += [
        "",
        "CAVEATS that ride with every number above:",
        "   \u2022 C-CAP is a 1 m generalized product; a distant vintage means real land-cover",
        "     change is charged to the model as error.",
        "   \u2022 The both-agree subset is EASIER BY CONSTRUCTION — it is the canopy both",
        "     proxies can see. It is a favourable subset, NOT ground truth.",
        "   \u2022 Only a human-labelled sample (P3) can adjudicate the disagreement zone.",
    ]
    ax3.text(0, 1, "\n".join(lines), va="top", fontsize=8.4, color=INK_MUTED,
             family="monospace", linespacing=1.5)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"[dashboard] wrote {out}")
    return True


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(description="One-page honest-accuracy dashboard.")
    ap.add_argument("--out", default=str(QC_DIR / "accuracy_dashboard.png"))
    args = ap.parse_args(argv)

    live, agree = load()
    print(f"[dashboard] live C-CAP rows: {len(live)}  |  P2 partitions: {len(agree)}")
    for y in sorted(live):
        a = agree.get(y)
        extra = (f"  ->  both-agree {a['recall']:.4f}/{a['precision']:.4f}"
                 f" (disagree {a['disagree']:.1f}%)") if a else ""
        print(f"    {y:<6} recall {live[y]['recall']:.4f}  "
              f"precision {live[y]['precision']:.4f}{extra}")
    build(live, agree, Path(args.out))


if __name__ == "__main__":
    main()
