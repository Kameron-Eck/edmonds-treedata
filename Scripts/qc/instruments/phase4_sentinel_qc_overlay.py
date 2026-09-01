r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — SENTINEL TP/FN/FP OVERLAYS, COLOUR-CODED BY P2 PARTITION
  Edmonds Temporal Active Learning Pipeline

  WHY  (the P4 remaining item, CHATLOG STATE "P4 REMAINING")
    phase4_sentinel_snap.py shows WHERE the model calls canopy. It does not
    show where the model is WRONG — and on this project "wrong" is not a
    well-defined word everywhere in the frame:

      * where the two references AGREE, a disagreement with them is a real
        error and TP / FN / FP mean what they say;
      * where the references DISAGREE (~15-17% of pixels, every year) there
        is NO TRUTH to be wrong about. Scoring those pixels as errors is the
        single most common way this project has misled itself.

    So this renders both facts at once: the P2 agreement partition, and the
    model's outcome INSIDE the partition where outcomes are meaningful.
    Contested ground is drawn in its own colours and is never scored.

  READS THE SAME FIXED WINDOWS as phase4_sentinel_snap.py
  (Scripts/sentinel_sites.json) and reuses its window/bounds helpers, so a
  site here and a site there are the same rectangle.

  PANELS (per site)
    1  RGB
    2  P2 AGREEMENT PARTITION   both-canopy / C-CAP only / NDVI only / both-non
    3  MODEL OUTCOME            TP / FN / FP on agreed ground; contested greyed

  PRODUCES
    phase4/qc/sentinel_overlays/{site}_{year}.png
    phase4/qc/sentinel_overlays_{year}.csv     per-site TP/FN/FP + contested %

  USAGE (local; no torch)
    py -3.12 phase4_sentinel_qc_overlay.py --year 2016
    py -3.12 phase4_sentinel_qc_overlay.py --year 2016 --site marsh_deciduous
    py -3.12 phase4_sentinel_qc_overlay.py --year 2016 \
        --mask ..\phase4\masks\edmonds_canopy_prob_2016_corrected.tif --thresh 0.509
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import io
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import phase4_sentinel_snap as SNAP
from phase4seg.names import clean_argv  # noqa: E402

BASE = SNAP.BASE
QC_DIR = BASE / "phase4" / "qc"
OUT_DIR = QC_DIR / "sentinel_overlays"
LOGS_DIR = BASE / "phase4" / "logs"

CCAP_CANOPY = [9, 10, 11, 13, 16]     # forest + forested wetland, as qc_indep
NDVI_CANOPY = 2                       # ndvi_ref: 0 non-veg, 1 grass, 2 canopy

# year -> the C-CAP epoch used to score it (same pairing as qc_indep)
CCAP_FOR_YEAR = {
    "2000": "ccap_2016_hires_lc.tif", "2002": "ccap_2016_hires_lc.tif",
    "2013": "ccap_2016_hires_lc.tif", "2015": "ccap_2016_hires_lc.tif",
    "2016": "ccap_2016_hires_lc.tif", "2017": "ccap_2016_hires_lc.tif",
    "2019n": "ccap_2021_hires_lc.tif", "2021s": "ccap_2021_hires_lc.tif",
    "2023n": "ccap_2021_hires_lc.tif",
}

PART_COLOURS = {
    "both_canopy":    (0.13, 0.62, 0.20),   # green   — both refs say canopy
    "ccap_only":      (0.95, 0.72, 0.10),   # amber   — C-CAP only (contested)
    "ndvi_only":      (0.25, 0.50, 0.90),   # blue    — NDVI only (contested)
    "both_noncanopy": (0.85, 0.85, 0.85),   # grey    — both say not canopy
}
OUTCOME_COLOURS = {
    "TP":        (0.13, 0.62, 0.20),   # green
    "FN":        (0.85, 0.13, 0.13),   # red     — agreed canopy the model missed
    "FP":        (0.80, 0.20, 0.75),   # magenta — agreed non-canopy the model called
    "TN":        (0.93, 0.93, 0.93),   # near-white
    "contested": (0.72, 0.72, 0.55),   # olive-grey — NO TRUTH HERE, never scored
}


def _blend(rgb, mask, colour, alpha=0.55):
    out = rgb.astype(np.float32).copy()
    c = np.array(colour, dtype=np.float32) * 255.0
    out[mask] = (1 - alpha) * out[mask] + alpha * c
    return out.astype(np.uint8)


def _layer(path, bounds, shape, pick):
    """Read a categorical raster window and resize to shape; pick -> bool."""
    a = SNAP.read_window(path, bounds, bands=[1])
    if a is None:
        return None
    return pick(SNAP._resize_to(a[0], shape))


def site_panels(site, bounds, img_path, mask_path, ccap_path, ndvi_path, thresh):
    rgbi = SNAP.read_window(img_path, bounds, bands=[1, 2, 3])
    if rgbi is None:
        return None
    rgb = np.transpose(rgbi, (1, 2, 0)).astype(np.uint8)
    shape = rgb.shape[:2]

    model = SNAP.canopy_from_mask(mask_path, bounds, shape, thresh)
    ccap = _layer(ccap_path, bounds, shape, lambda a: np.isin(a, CCAP_CANOPY))
    ndvi = _layer(ndvi_path, bounds, shape, lambda a: a == NDVI_CANOPY) if ndvi_path else None
    if model is None or ccap is None:
        return None
    model = np.nan_to_num(model).astype(bool)

    if ndvi is None:
        # Single-reference year: there IS no agreement partition. Say so rather
        # than silently drawing C-CAP as if it were truth.
        return dict(rgb=rgb, single_ref=True, ccap=ccap, model=model)

    parts = {
        "both_canopy": ccap & ndvi,
        "ccap_only": ccap & ~ndvi,
        "ndvi_only": ndvi & ~ccap,
        "both_noncanopy": ~ccap & ~ndvi,
    }
    agreed = parts["both_canopy"] | parts["both_noncanopy"]
    outcome = {
        "TP": parts["both_canopy"] & model,
        "FN": parts["both_canopy"] & ~model,
        "FP": parts["both_noncanopy"] & model,
        "TN": parts["both_noncanopy"] & ~model,
        "contested": ~agreed,
    }
    return dict(rgb=rgb, single_ref=False, parts=parts, outcome=outcome, model=model)


def render(name, year, P, run_note, out_png):
    rgb = P["rgb"]
    if P["single_ref"]:
        fig, axes = plt.subplots(1, 2, figsize=(10, 5))
        axes[0].imshow(rgb); axes[0].set_title("RGB", fontsize=10)
        ov = _blend(rgb, P["ccap"] & P["model"], OUTCOME_COLOURS["TP"])
        ov = _blend(ov, P["ccap"] & ~P["model"], OUTCOME_COLOURS["FN"])
        axes[1].imshow(ov)
        axes[1].set_title("vs C-CAP ONLY — one reference, NOT arbitrated", fontsize=9)
        for ax in axes:
            ax.axis("off")
        fig.suptitle(f"{name} — {year} — single-reference year", fontsize=11)
        fig.tight_layout(); fig.savefig(out_png, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return

    part_img = np.zeros(rgb.shape, dtype=np.uint8)
    for k, m in P["parts"].items():
        part_img = _blend(part_img, m, PART_COLOURS[k], alpha=1.0)
    out_img = np.zeros(rgb.shape, dtype=np.uint8)
    for k, m in P["outcome"].items():
        out_img = _blend(out_img, m, OUTCOME_COLOURS[k], alpha=1.0)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.4))
    axes[0].imshow(rgb); axes[0].set_title("RGB", fontsize=10)
    axes[1].imshow(part_img)
    axes[1].set_title("P2 reference agreement", fontsize=10)
    axes[1].legend(handles=[Patch(facecolor=c, label=k) for k, c in PART_COLOURS.items()],
                   loc="lower center", bbox_to_anchor=(0.5, -0.19), ncol=2, fontsize=7,
                   frameon=False)
    axes[2].imshow(out_img)
    o = P["outcome"]
    agreed_n = int(o["TP"].sum() + o["FN"].sum())
    rec = o["TP"].sum() / agreed_n if agreed_n else float("nan")
    axes[2].set_title(f"model outcome — recall on agreed canopy {rec:.2f}", fontsize=10)
    axes[2].legend(handles=[Patch(facecolor=c, label=k) for k, c in OUTCOME_COLOURS.items()],
                   loc="lower center", bbox_to_anchor=(0.5, -0.19), ncol=3, fontsize=7,
                   frameon=False)
    for ax in axes:
        ax.axis("off")
    fig.suptitle(f"{name} — {year}{run_note}   "
                 f"(contested {100*o['contested'].mean():.1f}% of window — never scored)",
                 fontsize=11)
    fig.tight_layout(); fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(
        description="Sentinel TP/FN/FP overlays colour-coded by the P2 agreement partition.")
    ap.add_argument("--year", default="2016", choices=sorted(SNAP.IMG_CATALOG))
    ap.add_argument("--mask", default=None, help="prob raster (default masks/edmonds_canopy_prob_{year}.tif)")
    ap.add_argument("--thresh", type=float, default=0.509)
    ap.add_argument("--site", action="append", default=None, help="repeatable; default all")
    ap.add_argument("--ndvi", default=None, help="override ndvi_ref_{year}.tif")
    ap.add_argument("--tag", default="", help="suffix for the output filenames")
    args = ap.parse_args(argv)

    year = args.year
    img_path = SNAP.resolve(SNAP.IMG_CATALOG[year])
    mask_path = Path(args.mask) if args.mask else SNAP.MASKS / f"edmonds_canopy_prob_{year}.tif"
    if not mask_path.exists():
        raise SystemExit(f"missing prob raster {mask_path} — pass --mask")
    ccap_path = SNAP.resolve(CCAP_FOR_YEAR[year])
    ndvi_path = Path(args.ndvi) if args.ndvi else QC_DIR / f"ndvi_ref_{year}.tif"
    if not ndvi_path.exists():
        print(f"  ! no NDVI reference for {year} — single-reference mode "
              f"(agreement partition is UNDEFINED, nothing is arbitrated)")
        ndvi_path = None

    sites = json.loads(SNAP.SITES_JSON.read_text(encoding="utf-8"))["sites"]
    if args.site:
        sites = [s for s in sites if s["name"] in set(args.site)]
        if not sites:
            raise SystemExit(f"no sentinel site matched {args.site}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_note = f" — {mask_path.stem}"
    print(f"[sentinel-qc] year={year} thresh={args.thresh}\n  mask={mask_path}\n"
          f"  ccap={ccap_path}\n  ndvi={ndvi_path}")

    rows, n_ok = [], 0
    for site in sites:
        name = site["name"]
        bounds = SNAP.site_bounds(site)
        P = site_panels(site, bounds, img_path, mask_path, ccap_path, ndvi_path, args.thresh)
        if P is None:
            print(f"  ! {name}: outside {year} imagery extent — skipped")
            continue
        png = OUT_DIR / f"{name}_{year}{args.tag}.png"
        render(name, year, P, run_note, png)
        n_ok += 1
        if P["single_ref"]:
            print(f"  ~ {name}: single-reference render → {png.name}")
            continue
        o = P["outcome"]
        tp, fn, fp = int(o["TP"].sum()), int(o["FN"].sum()), int(o["FP"].sum())
        cont = float(o["contested"].mean())
        rec = tp / (tp + fn) if tp + fn else float("nan")
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rows.append(dict(site=name, year=year, mask=mask_path.name, thresh=args.thresh,
                         tp=tp, fn=fn, fp=fp, recall_agreed=round(rec, 4),
                         precision_agreed=round(prec, 4),
                         contested_frac=round(cont, 4)))
        print(f"  ✓ {name}: recall(agreed) {rec:.3f}  prec(agreed) {prec:.3f}  "
              f"contested {100*cont:.1f}%  → {png.name}")

    if rows:
        csv_p = QC_DIR / f"sentinel_overlays_{year}{args.tag}.csv"
        with io.open(csv_p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n[sentinel-qc] {n_ok} sites → {OUT_DIR}\n[sentinel-qc] wrote {csv_p}")
        print("  NOTE: recall/precision here are ON AGREED GROUND ONLY. They are not")
        print("  comparable to the citywide qc_indep numbers, which score against a")
        print("  single reference including contested pixels.")

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_sentinel_qc_overlay_{year}_{ts}.log").write_text(
            f"phase4_sentinel_qc_overlay.py year={year} mask={mask_path.name} "
            f"thresh={args.thresh} sites={n_ok}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
