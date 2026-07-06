"""
Phase 3 — Segmentation proof-of-concept figure
================================================
Loads a Phase 3 semantic checkpoint, runs inference on a handful of tiles,
and saves a PNG grid:  RGB | Ground truth | Predicted probability | Overlay.

Run this in the SAME environment where the data lives (Colab + Drive), e.g.

    %run phase3_make_segmentation_png.py
    %run phase3_make_segmentation_png.py --per-site --n 5
    %run phase3_make_segmentation_png.py --site Forest_6 --n 4
    %run phase3_make_segmentation_png.py --ckpt /content/drive/MyDrive/treedata/phase3/checkpoints/sem_ft_fold_Forest_6.pt

The script mirrors phase3_semantic_dev exactly:
  • model      smp.Unet(resnet101, decoder (1024,512,256,128,64), classes=1)
  • channels   auto-detected from the checkpoint's conv1 (3 = RGB, 6 = RGB+VI)
  • VI         GCC, GRVI, ExG computed from RGB in [0,1]
  • normalise  ImageNet mean/std (+ VI mean/std when 6-channel)
  • predict    sigmoid(logit) > 0.5
"""

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import geopandas as gpd
from shapely.geometry import box

import torch
import segmentation_models_pytorch as smp

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

# Instance segmentation (watershed on the probability map). scikit-image ships
# with Colab; install on the rare miss so the script still runs end-to-end.
try:
    from scipy import ndimage as ndi
    from skimage.feature import peak_local_max
    from skimage.segmentation import watershed, mark_boundaries
    from skimage.color import label2rgb
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "scikit-image", "scipy"], check=True)
    from scipy import ndimage as ndi
    from skimage.feature import peak_local_max
    from skimage.segmentation import watershed, mark_boundaries
    from skimage.color import label2rgb

# ── Constants copied verbatim from phase3_semantic_dev ────────────────────────
ENCODER          = "resnet101"
DECODER_CHANNELS = (1024, 512, 256, 128, 64)
IMAGENET_MEAN    = [0.485, 0.456, 0.406]
IMAGENET_STD     = [0.229, 0.224, 0.225]
VI_MEAN          = [0.33, 0.00, 0.10]
VI_STD           = [0.10, 0.30, 0.25]
CANOPY_PROB_THRESHOLD = 0.5

BASE       = Path("/content/drive/MyDrive/treedata")
PHASE3_DIR = BASE / "phase3"
DEFAULT_CKPT  = PHASE3_DIR / "checkpoints" / "sem_best_2020.pt"
DEFAULT_INDEX = PHASE3_DIR / "tiles" / "tile_index_semantic.csv"
DEFAULT_OUT   = PHASE3_DIR / "proof_of_concept_tiles.png"
# Phase 0 instance detector crowns over the full 2020 ortho (vector polygons).
DEFAULT_CROWNS = BASE / "inference" / "edmonds_crowns_2020.gpkg"

# LOSO fold structure (from the Phase 3 handoff). Keyed by the held-out (test =
# UNSEEN) site → the forest sites the model actually trained on (SEEN). The val
# site is held out too (used for early stopping, not gradient updates), so it is
# excluded from "seen". sem_best_2020.pt is the fold that held out Forest_1.
LOSO_FOLDS = {
    "forest_1": {"val": "forest_2", "train": ["forest_3", "forest_4", "forest_6"]},
    "forest_2": {"val": "forest_3", "train": ["forest_1", "forest_4", "forest_6"]},
    "forest_3": {"val": "forest_4", "train": ["forest_1", "forest_2", "forest_6"]},
    "forest_4": {"val": "forest_6", "train": ["forest_1", "forest_2", "forest_3"]},
    "forest_6": {"val": "forest_1", "train": ["forest_2", "forest_3", "forest_4"]},
}


def _match_site(name, sites):
    """Map a (case-insensitive) site name to the exact value used in the index."""
    if name is None:
        return None
    low = {s.lower(): s for s in sites}
    return low.get(str(name).lower())


def resolve_holdout(ckpt_path, sites):
    """Infer the UNSEEN (held-out) site for a checkpoint from its filename."""
    name = Path(ckpt_path).name.lower()
    m = re.search(r"fold_(.+?)\.pt$", name)          # sem_ft_fold_Forest_6.pt
    cand = m.group(1) if m else ("forest_1" if "sem_best_2020" in name else None)
    return _match_site(cand, sites)


# ── VI + normalisation (identical math to the training pipeline) ──────────────
def compute_vis(rgb01, eps=1e-6):
    """rgb01: H×W×3 float in [0,1] → H×W×3 float (GCC, GRVI, ExG)."""
    R, G, B = rgb01[..., 0], rgb01[..., 1], rgb01[..., 2]
    s    = R + G + B + eps
    gcc  = G / s
    grvi = (G - R) / (G + R + eps)
    exg  = 2.0 * G - R - B
    return np.stack([gcc, grvi, exg], axis=-1).astype(np.float32)


def rgb_to_model_input(rgb_uint8, use_vi):
    """H×W×3 uint8 → C×H×W float32, normalised, with VI channels if use_vi."""
    rgb01 = rgb_uint8.astype(np.float32) / 255.0
    arr   = np.concatenate([rgb01, compute_vis(rgb01)], -1) if use_vi else rgb01
    mean  = np.asarray(IMAGENET_MEAN + (VI_MEAN if use_vi else []), np.float32)
    std   = np.asarray(IMAGENET_STD  + (VI_STD  if use_vi else []), np.float32)
    arr   = (arr - mean) / std
    return np.ascontiguousarray(arr.transpose(2, 0, 1))


# ── Model loading with auto channel detection ─────────────────────────────────
def load_model(ckpt_path, device):
    ckpt  = torch.load(ckpt_path, map_location=device)
    state = ckpt["model_state"] if "model_state" in ckpt else ckpt
    # torch.compile sometimes prefixes keys with "_orig_mod." — strip it.
    state = {k.replace("_orig_mod.", "", 1): v for k, v in state.items()}

    conv1 = state.get("encoder.conv1.weight")
    in_channels = int(conv1.shape[1]) if conv1 is not None else 3
    use_vi = in_channels == 6
    print(f"  checkpoint: {Path(ckpt_path).name}")
    print(f"  detected in_channels = {in_channels}  "
          f"({'RGB + VI' if use_vi else 'RGB only'})")
    if "epoch" in ckpt:
        print(f"  phase={ckpt.get('phase','?')}  epoch={ckpt.get('epoch','?')}  "
              f"best_val={ckpt.get('best_val','?')}")

    model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                     decoder_channels=DECODER_CHANNELS,
                     in_channels=in_channels, classes=1, activation=None)
    model.load_state_dict(state)
    model = model.to(device).eval()
    return model, use_vi


@torch.no_grad()
def predict(model, img_uint8, use_vi, device):
    inp   = torch.from_numpy(rgb_to_model_input(img_uint8, use_vi))
    inp   = inp.unsqueeze(0).to(device)
    logit = model(inp).squeeze().cpu().numpy()
    return 1.0 / (1.0 + np.exp(-logit))   # sigmoid → probability [0,1]


def watershed_instances(prob, threshold=CANOPY_PROB_THRESHOLD, min_distance=25,
                        smooth_sigma=1.0):
    """Split the binary canopy mask into individual crowns.

    Distance transform of the thresholded probability → local maxima as crown
    seeds → watershed flooded over the inverted distance, confined to the mask.
    Returns an int label image (0 = background, 1..N = crowns) and the count.
    This is the 'watershed instance segmentation' demo from the Phase 3 handoff;
    it derives instances from the semantic prediction (not the Phase 0 detector).
    """
    mask = prob >= threshold
    if not mask.any():
        return np.zeros_like(mask, dtype=np.int32), 0
    distance = ndi.distance_transform_edt(mask)
    if smooth_sigma:
        distance = ndi.gaussian_filter(distance, smooth_sigma)
    coords = peak_local_max(distance, min_distance=min_distance,
                            labels=mask, exclude_border=False)
    markers = np.zeros(distance.shape, dtype=np.int32)
    if len(coords):
        markers[tuple(coords.T)] = np.arange(1, len(coords) + 1)
    else:                                   # one big blob, no clear peaks
        markers[tuple(np.argwhere(mask)[len(np.argwhere(mask)) // 2])] = 1
    labels = watershed(-distance, markers, mask=mask)
    return labels.astype(np.int32), int(labels.max())


# ── Tile selection: one SEEN row + one UNSEEN row ─────────────────────────────
def _best_canopy_tile(df, site, min_canopy):
    g = df[df["site"].astype(str).str.lower() == site.lower()]
    if "canopy_frac" in g.columns:
        g = g[g["canopy_frac"] >= min_canopy].sort_values(
            "canopy_frac", ascending=False)
    return None if g.empty else g.iloc[[0]]


def select_seen_unseen(index_df, holdout_site, seen_site, min_canopy):
    """Return a 2-row frame: row 0 = SEEN (training site), row 1 = UNSEEN
    (the checkpoint's held-out site). Adds a '_kind' label column."""
    sites = sorted(index_df["site"].astype(str).unique())
    if holdout_site is None:
        raise SystemExit(
            "Could not infer the held-out site from the checkpoint name. "
            "Pass --unseen-site explicitly (e.g. --unseen-site Forest_1).")

    # Pick the SEEN site: user override, else a trained-on forest for this fold.
    if seen_site is None:
        fold = LOSO_FOLDS.get(holdout_site.lower())
        train_candidates = (fold["train"] if fold
                            else [s for s in sites
                                  if s.lower() != holdout_site.lower()
                                  and s.lower().startswith("forest")])
        seen_row = None
        for cand in train_candidates:
            cand_exact = _match_site(cand, sites)
            if cand_exact:
                seen_row = _best_canopy_tile(index_df, cand_exact, min_canopy)
                if seen_row is not None:
                    break
    else:
        seen_exact = _match_site(seen_site, sites)
        if seen_exact is None:
            raise SystemExit(f"--seen-site '{seen_site}' not in index. "
                             f"Sites: {sites}")
        if seen_exact.lower() == holdout_site.lower():
            raise SystemExit("--seen-site must differ from the held-out site.")
        seen_row = _best_canopy_tile(index_df, seen_exact, min_canopy)

    unseen_row = _best_canopy_tile(index_df, holdout_site, min_canopy)
    if seen_row is None or unseen_row is None:
        missing = "seen" if seen_row is None else f"unseen ({holdout_site})"
        raise SystemExit(f"No qualifying tile found for the {missing} row "
                         f"(try lowering --min-canopy).")

    seen_row   = seen_row.copy();   seen_row["_kind"]   = "seen"
    unseen_row = unseen_row.copy(); unseen_row["_kind"] = "unseen"
    return pd.concat([seen_row, unseen_row]).reset_index(drop=True)


def read_tile(row):
    with rasterio.open(row["img_path"]) as src:
        img = src.read().transpose(1, 2, 0)            # H×W×3 uint8
        geo = {"transform": src.transform, "crs": src.crs,
               "shape": (src.height, src.width),
               "bounds": tuple(src.bounds)}            # (minx,miny,maxx,maxy)
    with rasterio.open(row["mask_path"]) as src:
        gt = src.read(1).astype(np.float32)            # H×W 0/1
    return img[..., :3], gt, geo


class CrownSource:
    """Rasterise Phase 0 instance-crown polygons onto a tile's pixel grid.

    Loads the crowns gpkg once, reprojects lazily to each tile's CRS, clips to
    the tile bounds, and burns one unique integer label per crown so the figure
    colours each detected crown distinctly (same rendering as the watershed mode).
    """

    def __init__(self, gpkg_path):
        self.gdf = gpd.read_file(gpkg_path)
        self.gdf = self.gdf[self.gdf.geometry.notna()
                            & ~self.gdf.geometry.is_empty]
        print(f"  loaded {len(self.gdf):,} crowns from {Path(gpkg_path).name}  "
              f"(crs={self.gdf.crs})")
        self._cache = {}

    def _reprojected(self, crs):
        key = str(crs)
        if key not in self._cache:
            g = self.gdf
            if self.gdf.crs is not None and crs is not None \
                    and str(self.gdf.crs) != key:
                g = self.gdf.to_crs(crs)
            self._cache[key] = g
        return self._cache[key]

    def labels_for(self, geo):
        g = self._reprojected(geo["crs"])
        minx, miny, maxx, maxy = geo["bounds"]
        sub = g.cx[minx:maxx, miny:maxy]               # bbox spatial slice
        out_shape = geo["shape"]
        if sub.empty:
            return np.zeros(out_shape, dtype=np.int32), 0
        shapes = ((geom, i) for i, geom in enumerate(sub.geometry, start=1))
        lab = rasterio.features.rasterize(
            shapes, out_shape=out_shape, transform=geo["transform"],
            fill=0, dtype="int32", all_touched=False)
        return lab, int(np.unique(lab[lab > 0]).size)


# ── Figure ────────────────────────────────────────────────────────────────────
def make_figure(rows, model, use_vi, device, out_path, dpi, min_distance,
                instances, crown_source):
    n = len(rows)
    fig, axes = plt.subplots(n, 5, figsize=(16, 3.2 * n))
    if n == 1:
        axes = axes[None, :]
    inst_title = ("Instance segmentation" if instances == "phase0"
                  else "Instance (watershed)")
    col_titles = ["RGB", "Ground truth", "Predicted probability",
                  "Semantic segmentation", inst_title]

    gt_cmap = ListedColormap([(0, 0, 0, 0), (0.11, 0.62, 0.46, 1.0)])  # teal

    for r, (_, row) in enumerate(rows.iterrows()):
        img, gt, geo = read_tile(row)
        prob    = predict(model, img, use_vi, device)
        pred    = prob >= CANOPY_PROB_THRESHOLD
        if instances == "phase0":
            inst, n_crowns = crown_source.labels_for(geo)
        else:
            inst, n_crowns = watershed_instances(prob, min_distance=min_distance)

        iou = ((pred & (gt > 0.5)).sum() /
               max(1, (pred | (gt > 0.5)).sum()))

        axes[r, 0].imshow(img)
        axes[r, 1].imshow(img); axes[r, 1].imshow(gt, cmap=gt_cmap, vmin=0, vmax=1)
        im = axes[r, 2].imshow(prob, cmap="viridis", vmin=0, vmax=1)
        axes[r, 3].imshow(img)
        axes[r, 3].imshow(np.ma.masked_where(~pred, pred),
                          cmap=ListedColormap([(1.0, 0.35, 0.19)]), alpha=0.45)
        axes[r, 3].contour(pred, levels=[0.5], colors="#D85A30", linewidths=0.8)

        # Instance column: distinct random color per crown, over a dimmed RGB,
        # with white watershed boundaries so individual crowns read clearly.
        inst_rgb = label2rgb(inst, image=img, bg_label=0, alpha=0.55,
                             image_alpha=0.55, kind="overlay")
        inst_rgb = mark_boundaries(inst_rgb, inst, color=(1, 1, 1), mode="thick")
        axes[r, 4].imshow(inst_rgb)
        axes[r, 4].text(0.02, 0.97, f"{n_crowns} crowns", transform=axes[r, 4].transAxes,
                        fontsize=9, va="top", ha="left", color="white",
                        bbox=dict(boxstyle="round,pad=0.2", fc="#26215C", ec="none", alpha=0.7))

        site = str(row.get("site", ""))
        kind = str(row.get("_kind", "")).upper()
        axes[r, 0].set_ylabel(f"{kind}\n{site}\nIoU {iou:.2f}",
                              fontsize=11, rotation=0, ha="right", va="center",
                              labelpad=40)
        for c in range(5):
            axes[r, c].set_xticks([]); axes[r, c].set_yticks([])
        if r == 0:
            for c, t in enumerate(col_titles):
                axes[r, c].set_title(t, fontsize=12)

    # Dedicated colorbar in the empty margin beneath the probability column, so
    # it sits under the map it describes and never intrudes on a neighbouring
    # tile. Reserve bottom space first, then anchor the bar to that column.
    fig.subplots_adjust(bottom=0.15)
    fig.suptitle("Proof of Concept (2020)", fontsize=14, y=0.995)
    pos = axes[-1, 2].get_position()
    cax = fig.add_axes([pos.x0, pos.y0 - 0.085, pos.width, 0.022])
    cbar = fig.colorbar(im, cax=cax, orientation="horizontal")
    cbar.set_label("canopy probability", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"  ✓ saved {out_path}  ({n} tiles)")


def main():
    p = argparse.ArgumentParser(description="Phase 3 segmentation PNG "
                                            "(seen vs unseen rows)")
    p.add_argument("--ckpt",  default=str(DEFAULT_CKPT))
    p.add_argument("--index", default=str(DEFAULT_INDEX))
    p.add_argument("--out",   default=str(DEFAULT_OUT))
    p.add_argument("--unseen-site", default=None,
                   help="held-out site for row 2 (auto-detected from --ckpt name "
                        "if omitted; sem_best_2020.pt → Forest_1)")
    p.add_argument("--seen-site", default=None,
                   help="training site for row 1 (default: a trained-on forest "
                        "for this fold)")
    p.add_argument("--min-canopy", type=float, default=0.05,
                   help="min canopy fraction (skip near-empty tiles)")
    p.add_argument("--min-distance", type=int, default=25,
                   help="watershed: min pixels between crown seeds (~crown radius "
                        "in px; 7.5cm/px → 25px ≈ 1.9m). Lower = more, smaller crowns")
    p.add_argument("--instances", choices=["phase0", "watershed"], default="phase0",
                   help="instance column source: 'phase0' = detected crowns from "
                        "the 2020 gpkg (default); 'watershed' = split the semantic "
                        "prediction")
    p.add_argument("--crowns", default=str(DEFAULT_CROWNS),
                   help="path to the Phase 0 crowns gpkg (for --instances phase0)")
    p.add_argument("--dpi",   type=int, default=200)
    args, _ = p.parse_known_args()   # tolerate Jupyter's -f kernel.json

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  device: {device}")

    index_df = pd.read_csv(args.index)
    sites = sorted(index_df["site"].astype(str).unique())
    print(f"  tiles in index: {len(index_df)}  sites: {sites}")

    model, use_vi = load_model(args.ckpt, device)

    holdout = (_match_site(args.unseen_site, sites) if args.unseen_site
               else resolve_holdout(args.ckpt, sites))
    print(f"  UNSEEN (held-out) site: {holdout}")

    # Instance column source. Fall back to watershed if the gpkg is absent.
    instances, crown_source = args.instances, None
    if instances == "phase0":
        if Path(args.crowns).exists():
            crown_source = CrownSource(args.crowns)
        else:
            print(f"  WARNING: crowns gpkg not found at {args.crowns} — "
                  f"falling back to watershed instances")
            instances = "watershed"

    rows = select_seen_unseen(index_df, holdout, args.seen_site, args.min_canopy)
    for _, rr in rows.iterrows():
        print(f"    {rr['_kind']:>6}: {rr.get('tile_name', '?')}  "
              f"site={rr['site']}  canopy_frac={rr.get('canopy_frac', '?')}")
    make_figure(rows, model, use_vi, device, args.out, args.dpi,
                args.min_distance, instances, crown_source)


if __name__ == "__main__":
    main()