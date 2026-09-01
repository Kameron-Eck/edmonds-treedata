"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — Threshold Diagnostic (Reason A vs Reason B)
  Edmonds Temporal Active Learning Pipeline

  Answers ONE question before committing to supervision work:
  is the year-2000 over-prediction a THRESHOLD effect (false positives
  sitting just above 0.5 — cheap to fix) or a DATA problem (the model
  is CONFIDENTLY calling non-canopy "canopy" — needs more labels)?

  HOW IT DECIDES
    The cleanest negative we have is the Negative_Parking footprint
    (asphalt/cars/roofs — should be ~0% canopy). It looks at where the
    predicted-canopy probability mass sits there:
      • mostly 0.50–0.60  → Reason A: a threshold bump removes it ~free
      • mostly > 0.80     → Reason B: confident error, supervision needed
    It also sweeps thresholds and reports how city-wide canopy % and the
    negative-footprint false-positive % respond.

  PRODUCES (phase4/qa/2000/):
    2000_threshold_diagnostic.png   city + per-site probability histograms
    printed threshold sweep table + a plain-English verdict

  USAGE (Colab):
    %run phase4_threshold_diagnostic.py
    %run phase4_threshold_diagnostic.py --year 2000
    %run phase4_threshold_diagnostic.py --prob /path/to/prob.tif
    %run phase4_threshold_diagnostic.py --no-show     # save only
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import importlib
import subprocess
import sys
from pathlib import Path


# ── Dependency bootstrap ──────────────────────────────────────────────────────

# Dep bootstrap: mechanism in phase4seg/deps.py (refactor 2.3); the LIST stays
# per-file — nine distinct sets exist and one shared list would over-install.
from phase4seg.deps import ensure_deps as _ensure_deps  # noqa: E402
_ensure_deps([("rasterio", "rasterio"), ("matplotlib", "matplotlib"),
                    ("numpy", "numpy")])

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling
import matplotlib
import matplotlib.pyplot as plt
from phase4seg.names import clean_argv  # noqa: E402


# ── Paths ─────────────────────────────────────────────────────────────────────
BASE       = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR = BASE / "photos"
QA_DIR     = BASE / "phase4" / "qa"
CROWN_CRS  = "EPSG:3857"

# Threshold sweep points
THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
# Bands for the borderline-vs-confident split (among predicted-canopy pixels)
BORDERLINE = (0.50, 0.60)
CONFIDENT  = 0.80


# ── File resolution (handles the phase5→phase4 rename) ────────────────────────
def resolve_prob(year, override=None):
    if override:
        p = Path(override)
        if p.exists():
            return p
        raise FileNotFoundError(f"--prob path not found: {p}")
    cands = [
        BASE / "phase4" / "masks" / f"edmonds_canopy_prob_{year}.tif",
        BASE / "phase5" / "masks" / f"edmonds_canopy_prob_{year}.tif",  # pre-rename
    ]
    for c in cands:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Probability raster for {year} not found in phase4/masks or phase5/masks.\n"
        f"  Pass --prob <path> if it's elsewhere.")


# ── Probability helpers (uint8: 0–254 = prob, 255 = nodata) ───────────────────
def to_prob(arr):
    """Convert uint8 raster values to probability in [0,1], NaN where nodata."""
    p = arr.astype(np.float32)
    p[arr == 255] = np.nan
    return p / 254.0


def read_prob_decimated(path, max_dim=1600):
    with rasterio.open(path) as src:
        scale = max(src.width, src.height) / float(max_dim)
        scale = max(scale, 1.0)
        ow = max(1, int(src.width / scale))
        oh = max(1, int(src.height / scale))
        a = src.read(1, out_shape=(oh, ow), resampling=Resampling.nearest)
        return to_prob(a)


def read_prob_window(path, bounds, prob_crs):
    """Read native-resolution probabilities within a site footprint (CRS=bounds)."""
    with rasterio.open(path) as src:
        b = bounds
        if str(src.crs) != str(prob_crs):
            b = rasterio.warp.transform_bounds(prob_crs, src.crs, *bounds)
        win = rasterio.windows.from_bounds(*b, transform=src.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        full = rasterio.windows.Window(0, 0, src.width, src.height)
        win = win.intersection(full)
        if win.width <= 0 or win.height <= 0:
            return None
        a = src.read(1, window=win)
        return to_prob(a)


# ── Site footprints ───────────────────────────────────────────────────────────
def discover_sites():
    sites = []
    if not PHOTOS_DIR.exists():
        return sites
    for photo in sorted(PHOTOS_DIR.glob("*_rgb.tif")):
        name = photo.stem.replace("_rgb", "")
        with rasterio.open(photo) as src:
            b, crs = src.bounds, src.crs
        if crs is not None and str(crs) != CROWN_CRS:
            b = rasterio.coords.BoundingBox(
                *rasterio.warp.transform_bounds(crs, CROWN_CRS, *b))
        sites.append(dict(name=name, bounds=tuple(b),
                          is_negative="Negative" in name))
    return sites


# ── Stats ─────────────────────────────────────────────────────────────────────
def canopy_frac(prob, t):
    """Fraction of valid pixels with prob > t."""
    valid = prob[np.isfinite(prob)]
    if valid.size == 0:
        return float("nan")
    return float((valid > t).mean())


def predicted_canopy_split(prob):
    """Among pixels predicted canopy at 0.5, what fraction is borderline vs confident?"""
    valid = prob[np.isfinite(prob)]
    pc = valid[valid > 0.50]
    if pc.size == 0:
        return dict(n=0, borderline=float("nan"), confident=float("nan"),
                    median=float("nan"))
    borderline = float(((pc > BORDERLINE[0]) & (pc <= BORDERLINE[1])).mean())
    confident = float((pc > CONFIDENT).mean())
    return dict(n=int(pc.size), borderline=borderline, confident=confident,
                median=float(np.median(pc)))


# ── Figure ────────────────────────────────────────────────────────────────────
def make_figure(year, city_prob, site_probs, out_path, show):
    n_sites = len(site_probs)
    ncols = 3
    nrows = 1 + int(np.ceil(n_sites / ncols))
    fig = plt.figure(figsize=(15, 3.2 * nrows))

    # City-wide histogram across the top
    ax0 = plt.subplot2grid((nrows, ncols), (0, 0), colspan=ncols, fig=fig)
    cv = city_prob[np.isfinite(city_prob)]
    ax0.hist(cv, bins=60, color="#4a7", edgecolor="white", linewidth=0.3)
    ax0.axvspan(*BORDERLINE, color="orange", alpha=0.18, label="borderline 0.50–0.60")
    ax0.axvline(0.50, color="k", ls="--", lw=1, label="threshold 0.5")
    ax0.axvline(CONFIDENT, color="firebrick", ls=":", lw=1, label="confident >0.80")
    for t in (0.50, 0.60, 0.70):
        ax0.annotate(f"{canopy_frac(city_prob, t)*100:.0f}% @ {t:.2f}",
                     xy=(t, 0), xycoords=("data", "axes fraction"),
                     xytext=(0, 8), textcoords="offset points",
                     fontsize=8, rotation=90, va="bottom", color="#333")
    ax0.set_title(f"{year} — city-wide canopy probability distribution", fontsize=12)
    ax0.set_xlabel("predicted canopy probability")
    ax0.set_ylabel("pixel count")
    ax0.legend(fontsize=8, loc="upper center")

    # Per-site small multiples
    for i, (name, prob, is_neg) in enumerate(site_probs):
        r, c = 1 + i // ncols, i % ncols
        ax = plt.subplot2grid((nrows, ncols), (r, c), fig=fig)
        v = prob[np.isfinite(prob)] if prob is not None else np.array([])
        color = "#d9534f" if is_neg else "#5a8"
        if v.size:
            ax.hist(v, bins=40, color=color, edgecolor="white", linewidth=0.3)
        ax.axvspan(*BORDERLINE, color="orange", alpha=0.18)
        ax.axvline(0.50, color="k", ls="--", lw=0.8)
        frac = canopy_frac(prob, 0.50) if prob is not None else float("nan")
        tag = " [NEG]" if is_neg else ""
        ax.set_title(f"{name}{tag} — {frac*100:.0f}% canopy@0.5", fontsize=9)
        ax.set_xlim(0, 1)
        ax.tick_params(labelsize=7)

    fig.suptitle(f"{year} — threshold diagnostic", fontsize=13, y=0.998)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"  ✓ {out_path}")
    if show:
        plt.show()
    plt.close(fig)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    filtered = clean_argv()
    p = argparse.ArgumentParser(description="Phase 4 — threshold diagnostic")
    p.add_argument("--year", default="2000")
    p.add_argument("--prob", default=None, help="override probability raster path")
    p.add_argument("--max-dim", type=int, default=1600,
                   help="decimation cap for the city-wide histogram")
    p.add_argument("--no-show", action="store_true")
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(filtered)

    year = args.year
    show = not args.no_show
    if args.no_show:
        matplotlib.use("Agg")

    prob_path = resolve_prob(year, args.prob)
    with rasterio.open(prob_path) as src:
        prob_crs = src.crs
    out_dir = Path(args.out_dir) if args.out_dir else (QA_DIR / year)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n── Phase 4 threshold diagnostic — {year} ──")
    print(f"  Prob raster: {prob_path}")

    # City-wide
    city_prob = read_prob_decimated(prob_path, args.max_dim)

    # Per-site
    sites = discover_sites()
    site_probs = []
    for s in sites:
        pr = read_prob_window(prob_path, s["bounds"], prob_crs)
        site_probs.append((s["name"], pr, s["is_negative"]))

    # ── Threshold sweep table ─────────────────────────────────────────────────
    # Pick the cleanest negative footprint as the false-positive proxy
    neg = next((sp for sp in site_probs
                if sp[2] and sp[1] is not None and np.isfinite(sp[1]).any()), None)
    # Pick a clean forest footprint as a true-positive reference
    pos = next((sp for sp in site_probs
                if (not sp[2]) and sp[1] is not None and np.isfinite(sp[1]).any()
                and canopy_frac(sp[1], 0.5) > 0.5), None)

    print(f"\n  Threshold sweep")
    hdr = f"    {'thresh':>7}  {'city canopy%':>12}"
    if neg: hdr += f"  {neg[0]+' (NEG)':>22}"
    if pos: hdr += f"  {pos[0]:>16}"
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    for t in THRESHOLDS:
        row = f"    {t:>7.2f}  {canopy_frac(city_prob, t)*100:>11.1f}%"
        if neg: row += f"  {canopy_frac(neg[1], t)*100:>21.1f}%"
        if pos: row += f"  {canopy_frac(pos[1], t)*100:>15.1f}%"
        print(row)

    # ── Verdict heuristic (from the cleanest negative) ────────────────────────
    print(f"\n  Verdict")
    if neg is None:
        print("    ⚠ No usable negative footprint found — read the histograms by eye.")
        print("    (Negative_Water is nodata in 2000; without a clean negative the")
        print("     parking footprint is the key panel to inspect.)")
    else:
        split = predicted_canopy_split(neg[1])
        fp50 = canopy_frac(neg[1], 0.50) * 100
        fp65 = canopy_frac(neg[1], 0.65) * 100
        fp80 = canopy_frac(neg[1], 0.80) * 100
        print(f"    Cleanest negative: {neg[0]}")
        print(f"    False-positive canopy% there: {fp50:.1f}% @0.50 → "
              f"{fp65:.1f}% @0.65 → {fp80:.1f}% @0.80")
        if split["n"] > 0:
            print(f"    Of pixels it calls canopy here: "
                  f"{split['borderline']*100:.0f}% are borderline (0.50–0.60), "
                  f"{split['confident']*100:.0f}% are confident (>0.80); "
                  f"median prob {split['median']:.2f}")
        # decision
        if fp50 < 5:
            print("    → The clean negative is already mostly correct; the city-wide")
            print("      over-call is coming from MIXED scenes (residential), not flat")
            print("      negatives. Inspect Forest_3's panel: a smeared mid-range there")
            print("      = Reason B (supervision). Threshold helps only the edges.")
        elif fp65 < 5 and split.get("borderline", 0) > 0.5:
            print("    → REASON A dominant: most false positives are borderline and a")
            print(f"      threshold bump (~0.65) removes them nearly for free. Try that")
            print("      first; supervision can be lighter.")
        elif fp80 > 15 or split.get("confident", 0) > 0.5:
            print("    → REASON B dominant: false positives are CONFIDENT (high prob).")
            print("      A threshold bump won't fix them — the model genuinely confuses")
            print("      these surfaces for canopy. Supervision is the real fix.")
        else:
            print("    → MIXED: a threshold bump helps somewhat but doesn't fully clear")
            print("      the false positives. Do both — bump threshold AND supervise.")

    print("\n    Also check the city histogram shape:")
    print("      bimodal (piles near 0 and 1, valley in middle) = decisive model")
    print("      smeared across the middle / shifted high = confused, over-predicting")

    make_figure(year, city_prob, site_probs, out_dir / f"{year}_threshold_diagnostic.png", show)
    print("  ✓ done\n")


if __name__ == "__main__":
    main()
