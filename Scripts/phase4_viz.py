"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — Qualitative diagnostics / error-map visualiser
  Edmonds Temporal Active Learning Pipeline
╚══════════════════════════════════════════════════════════════════╝

WHY THIS EXISTS
───────────────
Aggregate IoU / AUROC are dominated by the bulk canopy-vs-background split.
Grass / lawn / park pixels are a SMALL fraction of the frame, so grass
false-positives — the exact failure the green-hard-negative mining and the
negative sites exist to fight — barely move the headline metrics. This script
makes them visible two ways:

  1. PER-TILE ERROR MAPS where grass false-alarms are drawn in MAGENTA, so a
     model that lights up on lawns is obvious at a glance.
  2. A GRASS-RESTRICTED METRIC: over background pixels that are green
     (per-pixel GRVI ≥ GREEN_GRVI_THRESHOLD), what fraction does the model
     call canopy? That number is invisible in the pooled IoU.

It reuses the LIVE module (phase4_semantic_finetune.py, v029+) for the model
factory, checkpoint loader and input normalisation, and operates on the
already-written test tiles (which already carry the struct 4th band) — so it
never re-derives the version-specific hillshade path logic and is guaranteed
to score the same pixels step_evaluate did.

USAGE (Colab, after mounting Drive)
───────────────────────────────────
  %cd /content/drive/MyDrive/treedata/Scripts
  !python phase4_viz.py --year 2000
  # optional: overlay the RGB-only model's errors on the SAME tiles to see
  # whether the struct channel actually removes grass FPs:
  !python phase4_viz.py --year 2000 --rgb-ckpt phase3/sem_best_2020.pt
  # knobs: --thresh 0.516 (default: year's best-F1 from the eval report),
  #        --n-grass 12 --n-canopy 6 --n-mixed 6 --module ./phase4_semantic_finetune.py

OUTPUT
──────
  phase4/eval/viz_{year}/grass_gallery.png   worst grass false-alarm tiles
  phase4/eval/viz_{year}/panels_{bucket}.png RGB | struct | prob | error map
  phase4/eval/viz_{year}/grass_metrics.txt   grass-restricted numbers
  (all PNGs also printed to stdout paths for quick download)
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EPS = 1e-6


# ── Load the live pipeline module by path (robust to cwd / module name) ────────
def load_pipeline_module(module_path: Path):
    module_path = Path(module_path).resolve()
    if not module_path.exists():
        sys.exit(f"ERROR: pipeline module not found at {module_path}\n"
                 f"       pass --module /path/to/phase4_semantic_finetune.py")
    spec = importlib.util.spec_from_file_location("p4_live", module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["p4_live"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Per-pixel GRVI green mask (matches the tiler's hard-negative definition) ────
def grvi_green_mask(img_hwc, threshold):
    r = img_hwc[..., 0].astype(np.float32)
    g = img_hwc[..., 1].astype(np.float32)
    grvi = (g - r) / (g + r + EPS)
    return grvi >= threshold, grvi


# ── Run one model over one tile → probability map ──────────────────────────────
def infer_prob(m, model, device, img_hwc, in_channels):
    import torch
    if in_channels >= 4 or getattr(m, "USE_VI", False):
        # numpy normalisation path — handles VI insertion + the struct band
        inp = torch.from_numpy(m.rgb_to_model_input(img_hwc[..., :in_channels]))
    else:
        # plain RGB → ImageNet normalise (mirrors step_evaluate's eval_tf)
        rgb = img_hwc[..., :3].astype(np.float32) / 255.0
        rgb = (rgb - np.array(m.IMAGENET_MEAN)) / np.array(m.IMAGENET_STD)
        inp = torch.from_numpy(rgb.transpose(2, 0, 1).astype(np.float32))
    with torch.no_grad():
        logits = model(inp.unsqueeze(0).to(device)).squeeze().cpu().numpy()
    return 1.0 / (1.0 + np.exp(-logits))


def build_and_load(m, device, ckpt_path, in_channels):
    m.IN_CHANNELS = in_channels           # build_model reads this global
    model = m.build_model(device, compile_model=False)
    ck = m.load_state_into(model, ckpt_path, device)
    model.eval()
    return model, ck


# ── Error-map RGB image: grass false-alarms in magenta ─────────────────────────
def error_map(pred, gt, valid, green, ignore_rgb=(0.15, 0.15, 0.15)):
    """TN grey · TP green · FN blue · FP-nongreen orange · FP-on-grass magenta."""
    h, w = pred.shape
    out = np.zeros((h, w, 3), np.float32)
    out[~valid] = ignore_rgb
    tp = valid & (pred == 1) & (gt == 1)
    fn = valid & (pred == 0) & (gt == 1)
    fp = valid & (pred == 1) & (gt == 0)
    tn = valid & (pred == 0) & (gt == 0)
    out[tn] = (0.05, 0.10, 0.05)
    out[tp] = (0.20, 0.80, 0.25)
    out[fn] = (0.20, 0.45, 1.00)
    out[fp & ~green] = (1.00, 0.55, 0.10)      # generic false alarm
    out[fp & green] = (1.00, 0.10, 0.85)       # GRASS false alarm ← the concern
    return out


def read_tile(rasterio, img_path, mask_path, ignore_label):
    with rasterio.open(img_path) as src:
        img = src.read().transpose(1, 2, 0)           # HWC uint8, 3 or 4 band
    with rasterio.open(mask_path) as src:
        gt = src.read(1).astype(np.float32)
    valid = gt != ignore_label
    return img, gt, valid


# ── Confusion counts restricted to a boolean region ────────────────────────────
def region_counts(pred, gt, region):
    tp = int(((pred == 1) & (gt == 1) & region).sum())
    fp = int(((pred == 1) & (gt == 0) & region).sum())
    fn = int(((pred == 0) & (gt == 1) & region).sum())
    tn = int(((pred == 0) & (gt == 0) & region).sum())
    return tp, fp, fn, tn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", required=True)
    ap.add_argument("--module", default=None,
                    help="path to live phase4_semantic_finetune.py "
                         "(default: sibling of this script)")
    ap.add_argument("--thresh", type=float, default=None,
                    help="operating threshold (default: year's best-F1 from "
                         "semantic_eval_report.csv, else 0.5)")
    ap.add_argument("--rgb-ckpt", default=None,
                    help="optional RGB-only checkpoint to run on the SAME tiles "
                         "(bands 1-3) for a struct-vs-RGB grass comparison")
    ap.add_argument("--n-grass", type=int, default=12)
    ap.add_argument("--n-canopy", type=int, default=6)
    ap.add_argument("--n-mixed", type=int, default=6)
    ap.add_argument("--max-metric-tiles", type=int, default=0,
                    help="0 = all test tiles for the grass metric")
    args = ap.parse_args()
    year = str(args.year)

    module_path = Path(args.module) if args.module else \
        Path(__file__).resolve().parent / "phase4_semantic_finetune.py"
    m = load_pipeline_module(module_path)
    m._ensure_torch()
    import torch
    import rasterio
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    green_thr = float(getattr(m, "GREEN_GRVI_THRESHOLD", 0.10))
    ignore_label = getattr(m, "IGNORE_LABEL", 255)

    # ── locate this year's test tiles ─────────────────────────────────────────
    index_path = m.TILE_DIR / year / f"tile_index_{year}.csv"
    if not index_path.exists():
        sys.exit(f"ERROR: {index_path} not found — run `step tile` for {year} first")
    idx = pd.read_csv(index_path)
    test = idx[idx["split"] == "test"].reset_index(drop=True)
    if len(test) == 0:
        test = idx.reset_index(drop=True)
        print("  NOTE: no held-out test split — visualising in-sample tiles")
    print(f"  {len(test)} tiles for {year}")

    # ── model(s) ──────────────────────────────────────────────────────────────
    # Input-channel count = band count of the tiles the model actually consumes
    # (v029 dropped the NIR-era year_in_channels()/entry_for(); the written tiles
    # are the source of truth — 3 = RGB, 4 = RGB+struct).
    with rasterio.open(test.iloc[0]["img_path"]) as _s0:
        in_ch = _s0.count
        src_label = _s0.tags().get("HS_SOURCE", getattr(m, "HS_SOURCE", "hs"))
    ckpt = m.MODELS_DIR / f"sem_best_{year}.pt"
    if not ckpt.exists():
        sys.exit(f"ERROR: {ckpt} not found — run `step train` for {year} first")
    model, ck = build_and_load(m, device, ckpt, in_ch)
    print(f"  model: {ckpt.name}  in_channels={in_ch}  band4={src_label}")

    rgb_model = None
    if args.rgb_ckpt:
        rgb_ckpt = Path(args.rgb_ckpt)
        if not rgb_ckpt.is_absolute():
            rgb_ckpt = m.BASE / args.rgb_ckpt
        rgb_model, _ = build_and_load(m, device, rgb_ckpt, 3)
        print(f"  rgb model:    {rgb_ckpt.name}  in_channels=3")
        # restore the struct model's global so nothing downstream breaks
        m.IN_CHANNELS = in_ch

    # ── threshold ─────────────────────────────────────────────────────────────
    thresh = args.thresh
    if thresh is None:
        thresh = 0.5
        rep = getattr(m, "EVAL_CSV", None)
        try:
            if rep and Path(rep).exists():
                r = pd.read_csv(rep)
                row = r[(r["year"].astype(str) == year) & (r["scope"] == "OVERALL")]
                if len(row) and pd.notna(row.iloc[-1].get("best_f1_thresh")):
                    thresh = float(row.iloc[-1]["best_f1_thresh"])
        except Exception as e:
            print(f"  (could not read best-F1 thresh from report: {e})")
    print(f"  operating threshold = {thresh:.3f}  (grass GRVI ≥ {green_thr})")

    out_dir = m.EVAL_DIR / f"viz_{year}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── pass 1: score every tile, bucket it, accumulate grass metric ──────────
    metric_rows = test if args.max_metric_tiles <= 0 else test.head(args.max_metric_tiles)
    g_tp = g_fp = g_fn = g_tn = 0       # grass-background restricted confusion
    fp_total = fp_green = 0            # composition of ALL false positives
    per_tile = []                      # (grass_fp_count, mean_grvi, canopy_frac, idx)
    for i, row in metric_rows.iterrows():
        img, gt, valid = read_tile(rasterio, row["img_path"], row["mask_path"], ignore_label)
        green, grvi = grvi_green_mask(img, green_thr)
        prob = infer_prob(m, model, device, img, in_ch)
        pred = (prob > thresh).astype(np.uint8)

        grass_bg = valid & green & (gt == 0)          # green, truly background
        tp, fp, fn, tn = region_counts(pred, gt, grass_bg)
        g_tp += tp; g_fp += fp; g_fn += fn; g_tn += tn
        fp_pix = valid & (pred == 1) & (gt == 0)
        fp_total += int(fp_pix.sum())
        fp_green += int((fp_pix & green).sum())

        cf = float(row.get("canopy_frac", np.nan))
        mean_grvi = float(grvi[valid].mean()) if valid.any() else 0.0
        grass_fp_count = int((fp_pix & green).sum())
        per_tile.append((grass_fp_count, mean_grvi, cf, i))

    # grass metric = fraction of green-background pixels the model calls canopy
    grass_bg_px = g_fp + g_tn
    grass_fp_rate = g_fp / grass_bg_px if grass_bg_px else float("nan")
    fp_green_share = fp_green / fp_total if fp_total else float("nan")
    lines = [
        f"PHASE 4 — grass-restricted diagnostics, year {year}",
        f"threshold = {thresh:.3f}   green GRVI ≥ {green_thr}",
        f"tiles scored = {len(metric_rows)}",
        "",
        f"green-background pixels           : {grass_bg_px:,}",
        f"  → predicted canopy (grass FP)   : {g_fp:,}",
        f"  GRASS FALSE-POSITIVE RATE       : {grass_fp_rate:.4f}",
        "",
        f"all false-positive pixels         : {fp_total:,}",
        f"  of which green (grass)          : {fp_green:,}",
        f"  GRASS SHARE OF ALL FALSE ALARMS : {fp_green_share:.4f}",
    ]
    (out_dir / "grass_metrics.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join("  " + ln for ln in lines))

    # ── bucket tiles for the panels ───────────────────────────────────────────
    df = pd.DataFrame(per_tile, columns=["grass_fp", "mean_grvi", "canopy_frac", "idx"])
    grass = df.sort_values(["grass_fp", "mean_grvi"], ascending=False).head(args.n_grass)
    canopy = df.sort_values("canopy_frac", ascending=False).head(args.n_canopy)
    mixed = df[(df["canopy_frac"] > 0.2) & (df["canopy_frac"] < 0.6)].head(args.n_mixed)
    buckets = {"grass_gallery": grass, "panels_canopy": canopy, "panels_mixed": mixed}

    # ── render ────────────────────────────────────────────────────────────────
    for name, sel in buckets.items():
        if len(sel) == 0:
            continue
        ncol = 5 if rgb_model is not None else 4
        fig, axes = plt.subplots(len(sel), ncol, figsize=(3.0 * ncol, 3.0 * len(sel)))
        axes = np.atleast_2d(axes)
        for r, (_, prow) in enumerate(sel.iterrows()):
            trow = test.iloc[int(prow["idx"])]
            img, gt, valid = read_tile(rasterio, trow["img_path"], trow["mask_path"], ignore_label)
            green, _ = grvi_green_mask(img, green_thr)
            prob = infer_prob(m, model, device, img, in_ch)
            pred = (prob > thresh).astype(np.uint8)

            axes[r, 0].imshow(img[..., :3]); axes[r, 0].set_ylabel(trow.get("site", ""), fontsize=7)
            axes[r, 0].set_title("RGB" if r == 0 else "", fontsize=9)
            if img.shape[-1] >= 4:
                axes[r, 1].imshow(img[..., 3], cmap="gray")
            axes[r, 1].set_title(f"{src_label} ch4" if r == 0 else "", fontsize=9)
            axes[r, 2].imshow(prob, cmap="viridis", vmin=0, vmax=1)
            axes[r, 2].set_title("prob" if r == 0 else "", fontsize=9)
            axes[r, 3].imshow(error_map(pred, gt, valid, green))
            axes[r, 3].set_title(f"{src_label} errors\n(magenta=grass FP)" if r == 0 else "", fontsize=8)
            if rgb_model is not None:
                pr = infer_prob(m, rgb_model, device, img, 3)
                pd_ = (pr > thresh).astype(np.uint8)
                axes[r, 4].imshow(error_map(pd_, gt, valid, green))
                axes[r, 4].set_title("RGB errors\n(magenta=grass FP)" if r == 0 else "", fontsize=8)
            for c in range(ncol):
                axes[r, c].set_xticks([]); axes[r, c].set_yticks([])
        fig.suptitle(f"{year} — {name}  (thresh {thresh:.3f})", fontsize=11)
        fig.tight_layout()
        p = out_dir / f"{name}.png"
        fig.savefig(p, dpi=110, bbox_inches="tight")
        plt.close(fig)
        print(f"  ✓ {p}")

    print(f"\n  All diagnostics → {out_dir}")


if __name__ == "__main__":
    main()
