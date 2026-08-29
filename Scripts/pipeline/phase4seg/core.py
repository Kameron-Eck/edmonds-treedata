from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (
    _ensure_deps, _tag_sfx, entry_for, resolve_native_path,
    _stage_imagery_local, _unstage_imagery_local, read_rgb_window,
    read_hillshade_chip, close_thread_hillshade, tick, tock,
    _copy_to_drive, _local_artifact_path, _StagingLock, STAGE_LOCK_MIN_BYTES,
    tile_dir_for,
)
from phase4seg.tiling import _origins_from_manifest

import contextlib
import gc
import os
import shutil
import subprocess
import threading
import time
import numpy as np
import pandas as pd
import rasterio
import rasterio.windows
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sklearn.model_selection import train_test_split
from tqdm import tqdm


# ── Lazy torch imports (same as phase3) ───────────────────────────────────────

_torch_loaded = False


def _ensure_torch():
    global _torch_loaded
    if _torch_loaded:
        return
    _ensure_deps([
        ("segmentation_models_pytorch", "segmentation-models-pytorch"),
        ("albumentations",              "albumentations>=2.0,<3"),
    ])
    global torch, nn, Dataset, DataLoader, WeightedRandomSampler
    global smp, A, ToTensorV2
    import torch as _torch
    import torch.nn as _nn
    from torch.utils.data import (
        Dataset as _Dataset,
        DataLoader as _DataLoader,
        WeightedRandomSampler as _WeightedRandomSampler,
    )
    import segmentation_models_pytorch as _smp
    import albumentations as _A
    from albumentations.pytorch import ToTensorV2 as _ToTensorV2

    torch = _torch
    nn = _nn
    Dataset = _Dataset
    DataLoader = _DataLoader
    WeightedRandomSampler = _WeightedRandomSampler
    smp = _smp
    A = _A
    ToTensorV2 = _ToTensorV2
    _torch_loaded = True

# ══════════════════════════════════════════════════════════════════════════════
#  Augmentation / dataset / model (ported from Phase 3)
# ══════════════════════════════════════════════════════════════════════════════

def _make_spatial_transform():
    _ensure_torch()
    # v039: geometric transforms fill out-of-frame borders with a CONSTANT. The
    # image border stays 0 (black), but the MASK border must be IGNORE_LABEL (255),
    # not 0 — otherwise rotated/warped corners become fake BACKGROUND pixels that
    # the loss learns from (and feed the empty-tile problem). fill_mask pins them to
    # ignore so they're excluded from loss and metrics (albumentations 2.x API).
    return A.Compose([
        A.HorizontalFlip(p=0.5), A.VerticalFlip(p=0.5), A.Transpose(p=0.5),
        A.RandomRotate90(p=0.5),
        A.Rotate(limit=45, border_mode=0, fill_mask=IGNORE_LABEL, p=0.5),
        A.Affine(translate_percent=0.1, scale=(0.9, 1.1), rotate=0,
                 border_mode=0, fill_mask=IGNORE_LABEL, p=0.5),
        A.GridDistortion(num_steps=5, distort_limit=0.3, border_mode=0,
                         fill_mask=IGNORE_LABEL, p=0.4),
        A.ElasticTransform(alpha=50, sigma=5, border_mode=0,
                           fill_mask=IGNORE_LABEL, p=0.3),
    ], additional_targets={"mask": "mask"})


def _make_pixel_transform():
    _ensure_torch()
    return A.Compose([
        A.OneOf([A.GaussianBlur(blur_limit=(3, 7), p=1.0),
                 A.MedianBlur(blur_limit=5, p=1.0)], p=0.5),
        A.RandomBrightnessContrast(0.3, 0.3, p=0.6),
        A.HueSaturationValue(15, 30, 15, p=0.5),
        A.RandomGamma(gamma_limit=(70, 130), p=0.4),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1), num_shadows_limit=(1, 3),
                       shadow_dimension=5, p=0.4),
        A.RandomFog(fog_coef_range=(0.05, 0.2), p=0.3),
        A.Downscale(scale_range=(0.5, 0.75),
                    interpolation_pair={"downscale": 0, "upscale": 2}, p=0.3),
        A.CoarseDropout(num_holes_range=(2, 8), hole_height_range=(32, 96),
                        hole_width_range=(32, 96), fill=0, p=0.4),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ])


def _make_test_transform():
    _ensure_torch()
    return A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ], additional_targets={"mask": "mask"})


def compute_vis(rgb01, eps=1e-6):
    R, G, B = rgb01[..., 0], rgb01[..., 1], rgb01[..., 2]
    s = R + G + B + eps
    return np.stack([G / s, (G - R) / (G + R + eps), 2.0 * G - R - B],
                    axis=-1).astype(np.float32)


def _input_norm(has_hs=False):
    # Channel order: [R, G, B, (VI..), (structure)] — VI derived from RGB, the
    # structure raster is the stored 4th band. Stats follow HS_SOURCE.
    hs_mean, hs_std = HS_STATS[config.HS_SOURCE]
    mean = list(IMAGENET_MEAN) + (VI_MEAN if config.USE_VI else []) + (hs_mean if has_hs else [])
    std  = list(IMAGENET_STD)  + (VI_STD  if config.USE_VI else []) + (hs_std  if has_hs else [])
    return np.asarray(mean, np.float32), np.asarray(std, np.float32)


def _sync_hs_source_from_tile(img_path):
    """Adopt the HS_SOURCE baked into a tile set (tile tag → global) so the
    normalization stats and any hillshade re-reads match the data on disk,
    regardless of the --hs-source flag at train/eval time. Pre-v027 4-band
    tiles carry no tag → 'fr' (they were tiled from the first-return raster)."""
    with rasterio.open(img_path) as s0:
        if s0.count < 4:
            return
        tag = s0.tags().get("HS_SOURCE", "fr")
    if tag not in HS_STATS:
        print(f"  WARNING: tile tag HS_SOURCE={tag!r} unknown — keeping "
              f"{config.HS_SOURCE!r}")
        return
    if tag != config.HS_SOURCE:
        print(f"  Tiles were baked with --hs-source {tag} — adopting it "
              f"(flag said {config.HS_SOURCE}).")
        config.HS_SOURCE = tag


# Reader threads for full-city inference (P11.6). rasterio window reads and the
# per-tile hillshade warp release the GIL, so threads — not processes — overlap the
# read path with GPU compute. 8 measured best on a Colab A100 VM (16.5 -> 3.1 ms/tile;
# 12 threads was no better). Override with EDMONDS_INFER_WORKERS; 1 restores the old
# fully serial path for a bisect.
INFER_READ_WORKERS = max(1, int(os.environ.get("EDMONDS_INFER_WORKERS", "8")))


def rgb_to_model_input(img_uint8):
    """uint8 HWC tile → normalised CHW model input. A 4th band is the LIDAR
    hillshade; VI (if --vi) is derived from RGB and inserted before it. Detects
    the hillshade channel from band count, so 3- and 4-band tiles both work."""
    has_hs = img_uint8.shape[-1] >= 4
    img01 = img_uint8.astype(np.float32) / 255.0
    rgb01 = img01[..., :3]
    chans = [rgb01]
    if config.USE_VI:
        chans.append(compute_vis(rgb01))
    if has_hs:
        chans.append(img01[..., 3:4])
    arr = np.concatenate(chans, -1) if len(chans) > 1 else rgb01
    mean, std = _input_norm(has_hs)
    arr = (arr - mean) / std
    if has_hs:
        # M06 caveat for --hs-source nir: band 4 is then the year's NIR, where a
        # raw 0 is *usually* out-of-coverage but can also be a genuinely black
        # NIR pixel (deep water/deep shadow). Those get neutralised too. Measured
        # 2026-08-26 on the two A/B orthos: 0.000% of the grid is NIR==0 while RGB
        # is non-zero, so the conflation is nil there. Left as-is deliberately.
        # No-coverage LIDAR is stored as raw 0 (nodata sentinel). Left alone it
        # normalises to (0-mean)/std ≈ -1.78 — a distinctive EXTREME the net was
        # never taught to read as "no info". Blank it to 0 (= the channel mean),
        # matching HS_DROPOUT, so missing coverage reads as neutral, not signal.
        nod = (img_uint8[..., 3] == 0)
        arr[..., -1][nod] = 0.0
    return np.ascontiguousarray(arr.transpose(2, 0, 1))


def _make_pixel_transform_nonorm():
    _ensure_torch()
    return A.Compose([
        A.OneOf([A.GaussianBlur(blur_limit=(3, 7), p=1.0),
                 A.MedianBlur(blur_limit=5, p=1.0)], p=0.5),
        A.RandomBrightnessContrast(0.3, 0.3, p=0.6),
        A.HueSaturationValue(15, 30, 15, p=0.5),
        A.RandomGamma(gamma_limit=(70, 130), p=0.4),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1), num_shadows_limit=(1, 3),
                       shadow_dimension=5, p=0.4),
        A.RandomFog(fog_coef_range=(0.05, 0.2), p=0.3),
        A.Downscale(scale_range=(0.5, 0.75),
                    interpolation_pair={"downscale": 0, "upscale": 2}, p=0.3),
        A.CoarseDropout(num_holes_range=(2, 8), hole_height_range=(32, 96),
                        hole_width_range=(32, 96), fill=0, p=0.4),
    ])


def _height_to_target(height_dn):
    """CHM DN grid (0 = nodata) → a 1×H×W normalized-height target for the aux head:
    metres = (DN-1)*0.2, normalized by HEIGHT_SCALE_M, with -1 as an invalid sentinel
    (masked out of the L1 loss). Used only under --aux-height."""
    dn = np.asarray(height_dn, dtype=np.float32)
    h_norm = np.clip((dn - 1.0) * 0.2 / HEIGHT_SCALE_M, 0.0, 2.0)
    tgt = np.where(dn > 0.5, h_norm, -1.0).astype(np.float32)
    return torch.from_numpy(tgt).unsqueeze(0)


class SemanticDataset:
    """Paired RGB + binary canopy mask tiles (identical contract to Phase 3)."""

    def __init__(self, df, training=True):
        self.df = df.reset_index(drop=True)
        self.training = training
        # Detect a stored 4th (hillshade) band straight off the tiles so the model
        # always matches the data, regardless of the --hillshade flag at train time.
        self.has_extra = False
        if len(self.df):
            with rasterio.open(self.df.iloc[0]["img_path"]) as s0:
                self.has_extra = (s0.count >= 4)
        # >3 channels (hillshade and/or VI) → normalise via numpy (rgb_to_model_input);
        # albumentations A.Normalize / HueSaturationValue assume exactly 3 channels.
        self._numpy_norm = bool(config.USE_VI or self.has_extra)
        if training:
            self.spatial_tf = _make_spatial_transform()
            self.pixel_tf = (_make_pixel_transform_nonorm() if self._numpy_norm
                             else _make_pixel_transform())
        else:
            self.test_tf = _make_test_transform()

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        _ensure_torch()
        row = self.df.iloc[idx]
        with rasterio.open(row["img_path"]) as src:
            img = src.read().transpose(1, 2, 0)
        with rasterio.open(row["mask_path"]) as src:
            mask = src.read(1).astype(np.float32)

        if config.AUX_HEIGHT:
            # RGB-only input + a co-registered CHM-DN height TARGET. Sidecar may be
            # absent for non-credible years → all-invalid target (loss auto-zeros).
            hp = row.get("height_path")
            if isinstance(hp, str) and hp and Path(hp).exists():
                with rasterio.open(hp) as hsrc:
                    height_dn = hsrc.read(1).astype(np.float32)     # CHM DN, 0 = nodata
            else:
                height_dn = np.zeros(mask.shape, dtype=np.float32)  # no sidecar → invalid
            rgb = img[..., :3]
            if self.training:
                # Height rides as a 4th channel so geometry is applied jointly, then is
                # split back out before the RGB-only colour aug.
                stacked = np.concatenate([rgb, height_dn[..., None]], axis=-1)
                out = self.spatial_tf(image=stacked, mask=mask)
                stacked, mask = out["image"], out["mask"]
                height_dn = stacked[..., 3]
                # np.concatenate upcast RGB→float32; the colour augs assume uint8, so
                # cast the RGB slice back (else HSV/brightness corrupt it → divergence).
                img = self.pixel_tf(image=stacked[..., :3].astype(np.uint8))["image"]
                mask = torch.from_numpy(mask).unsqueeze(0).float()
            else:
                out = self.test_tf(image=rgb, mask=mask)
                img, mask = out["image"], out["mask"]
                mask = mask.unsqueeze(0).float() if mask.dim() == 2 else mask.float()
            return (img, mask, _height_to_target(height_dn),
                    {"tile_name": row["tile_name"], "site": row["site"]})

        if self.training:
            # Spatial aug applies jointly to all bands + mask (geometry only).
            out = self.spatial_tf(image=img, mask=mask)
            img, mask = out["image"], out["mask"]
            if self._numpy_norm:
                # Colour/appearance aug on RGB only; the hillshade band is passed
                # through (HSV/shadow/fog assume RGB). VI is recomputed from the
                # augmented RGB inside rgb_to_model_input.
                rgb = self.pixel_tf(image=img[..., :3])["image"]
                if self.has_extra:
                    img = np.concatenate([rgb, img[..., 3:4]], axis=-1)
                else:
                    img = rgb
                img = torch.from_numpy(rgb_to_model_input(img))
                # Structure-channel dropout (training only): blank the last
                # channel to 0 in normalized space (= its mean) with prob
                # HS_DROPOUT. Forces a strong pure-RGB pathway so the model
                # never over-trusts the ~2016 snapshot where it is stale.
                # torch RNG is per-worker seeded, unlike np.random under fork.
                if self.has_extra and config.HS_DROPOUT > 0 \
                        and torch.rand(()).item() < config.HS_DROPOUT:
                    img[-1] = 0.0
            else:
                img = self.pixel_tf(image=img)["image"]
            mask = torch.from_numpy(mask).unsqueeze(0).float()
        else:
            if self._numpy_norm:
                img = torch.from_numpy(rgb_to_model_input(img))
                mask = torch.from_numpy(mask).unsqueeze(0).float()
            else:
                out = self.test_tf(image=img, mask=mask)
                img, mask = out["image"], out["mask"]
                mask = mask.unsqueeze(0).float() if mask.dim() == 2 else mask.float()

        meta = {"tile_name": row["tile_name"], "site": row["site"]}
        return img, mask, meta


def _inject_dropout(module, p):
    for _, child in module.named_children():
        if isinstance(child, nn.Sequential):
            child.add_module("dropout", nn.Dropout2d(p=p))
        else:
            _inject_dropout(child, p)


def _build_unet_with_height():
    """A subclass of smp.Unet with a parallel height-regression head off the shared
    64-ch decoder features. Subclass (not wrapper) so the state_dict keys stay
    encoder.*/decoder.*/segmentation_head.* — P3/P0 checkpoints load via strict=False
    and the new height_head.* keys init random. forward returns (seg_logits, height).
    Defined lazily because smp/nn are only importable after _ensure_torch()."""
    class UnetWithHeight(smp.Unet):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.height_head = nn.Conv2d(DECODER_CHANNELS[-1], 1, kernel_size=1)

        def forward(self, x):
            feats = self.encoder(x)
            dec = self.decoder(feats)            # smp>=0.4: decoder takes the feature list
            return self.segmentation_head(dec), self.height_head(dec)

    return UnetWithHeight(encoder_name=ENCODER, encoder_weights=None,
                          decoder_channels=DECODER_CHANNELS, in_channels=config.IN_CHANNELS,
                          classes=1, activation=None)


def build_model(device, compile_model=True):
    """U-Net with a canopy logits head. With AUX_HEIGHT, adds a parallel height head
    so the model returns a (seg_logits, height) tuple (the --aux-height reframe)."""
    _ensure_torch()
    model = _build_unet_with_height() if config.AUX_HEIGHT else smp.Unet(
        encoder_name=ENCODER, encoder_weights=None,
        decoder_channels=DECODER_CHANNELS, in_channels=config.IN_CHANNELS,
        classes=1, activation=None)
    _inject_dropout(model.decoder, DECODER_DROPOUT)
    model = model.to(device)
    if compile_model:
        try:
            model = torch.compile(model)
        except Exception as e:
            print(f"  (torch.compile disabled: {e})")
    return model


def _inflate_first_conv(state, own):
    """Adapt a 3-channel-input checkpoint to a 4-channel model (RGB → RGB+hillshade).

    Only the encoder's first conv has input-channel-dependent shape
    ([C_out,3,k,k] → [C_out,4,k,k]). Copy the RGB weights and ZERO-init the extra
    channel, so the pretrained RGB behaviour is exactly preserved at fine-tune
    start and the hillshade weights are learned from scratch (vs strict=False
    silently dropping the whole conv → random stem). No-op when channel counts
    already match (loading a saved 4ch ckpt back for eval/inference). Returns a
    patched copy of `state`."""
    patched = dict(state)
    for k, w in state.items():
        if k not in own or own[k].dim() != 4:
            continue
        tw = own[k]
        if tw.shape[1] == w.shape[1] or tw.shape[0] != w.shape[0]:
            continue
        if tw.shape[1] > w.shape[1]:
            new = tw.clone(); new.zero_()
            new[:, :w.shape[1]] = w
            patched[k] = new
            print(f"    • inflated input conv {k}: {tuple(w.shape)} → "
                  f"{tuple(tw.shape)} (zero-init {tw.shape[1]-w.shape[1]} extra ch)")
        else:
            patched.pop(k, None)
            print(f"    • dropped wider input conv {k}: ckpt {tuple(w.shape)} "
                  f"> model {tuple(tw.shape)} (left random)")
    return patched


def load_state_into(model, ckpt_path, device):
    """Load a checkpoint's model_state into model (handles torch.compile wrap and
    RGB→RGB+hillshade first-conv inflation)."""
    ckpt = torch.load(ckpt_path, map_location=device)
    state = ckpt["model_state"]
    tgt = model._orig_mod if hasattr(model, "_orig_mod") else model
    state = _inflate_first_conv(state, tgt.state_dict())
    tgt.load_state_dict(state, strict=False)
    return ckpt


def resolve_p3_ckpt(override=None):
    if override:
        p = Path(override)
        if p.exists():
            return p
        print(f"  WARNING: --ckpt {p} not found; falling back to default Phase 3 ckpt")
    for c in P3_CKPT_CANDIDATES:
        if c.exists():
            return c
    return None


# ── spatial buffer split (ported from Phase 3) ────────────────────────────────

def make_spatial_buffer_splits(df, n_folds=5, buffer_px=512, seed=42):
    from scipy.spatial.distance import cdist
    rng = np.random.RandomState(seed)
    sites = sorted(df["site"].unique())
    fold_assign = np.full(len(df), -1, dtype=int)
    for site in sites:
        idx = np.where(df["site"] == site)[0]
        for i, j in enumerate(rng.permutation(idx)):
            fold_assign[j] = i % n_folds
    folds = []
    for fold in range(n_folds):
        val_idx, tr_idx = [], []
        for site in sites:
            g = np.where(df["site"] == site)[0]
            v = g[fold_assign[g] == fold]
            o = g[fold_assign[g] != fold]
            if len(v) == 0:
                tr_idx.extend(o.tolist()); continue
            val_idx.extend(v.tolist())
            if len(o) == 0:
                continue
            d = cdist(df.iloc[o][["row_off", "col_off"]].values,
                      df.iloc[v][["row_off", "col_off"]].values, metric="chebyshev")
            md = d.min(axis=1)
            for i, j in enumerate(o):
                if md[i] >= buffer_px:
                    tr_idx.append(j)
        folds.append((np.array(tr_idx), np.array(val_idx)))
    return folds


def _masked_l1(pred, target):
    """Mean L1 over VALID height pixels only (target >= 0; -1 = nodata/invalid
    sentinel). pred/target are B×1×H×W. Returns 0 when no valid pixels in the batch
    (so non-credible years, whose tiles have no height sidecar, contribute nothing)."""
    valid = (target >= 0).float()
    diff = (pred.float() - target.float()).abs() * valid
    return diff.sum() / valid.sum().clamp(min=1.0)


def _masked_bce(criterion_none, logits, masks):
    """Mean BCE over labeled pixels only (mask value 255 = IGNORE is excluded).

    `criterion_none` is a BCEWithLogitsLoss with reduction='none'. For legacy
    masks (values only {0,1}) every pixel is valid, so this equals the plain
    mean BCE — bit-for-bit identical to the previous behaviour.
    """
    valid  = (masks != IGNORE_LABEL).float()
    target = torch.where(masks == IGNORE_LABEL, torch.zeros_like(masks), masks)
    loss_map = criterion_none(logits, target)
    return (loss_map * valid).sum() / valid.sum().clamp(min=1.0)


def _masked_dice(logits, masks, smooth=DICE_SMOOTH):
    """Soft-Dice loss over labeled pixels only (255 = IGNORE excluded).

    IGNORE-aware exactly like `_masked_bce`: both the prediction probabilities
    and the target are zeroed at IGNORE pixels, so those pixels contribute
    nothing to the intersection or the denominator. Computed per-sample over the
    batch then averaged. For legacy {0,1} masks the IGNORE mask is empty, so this
    is a plain soft-Dice. All-background tiles → near-zero loss unless the model
    predicts false canopy (penalised via the denominator).
    """
    valid  = (masks != IGNORE_LABEL).float()
    target = torch.where(masks == IGNORE_LABEL, torch.zeros_like(masks), masks) * valid
    probs  = torch.sigmoid(logits) * valid
    dims   = tuple(range(1, probs.dim()))
    inter  = (probs * target).sum(dims)
    denom  = probs.sum(dims) + target.sum(dims)
    dice   = (2.0 * inter + smooth) / (denom + smooth)
    return (1.0 - dice).mean()


def _masked_focal(criterion_none, logits, masks):
    """Masked, IGNORE-aware binary focal loss (Edit F). IGNORE handling is
    IDENTICAL to `_masked_bce` (255 zeroed in the target, excluded from the
    average). Reuses the per-pixel BCE map from `criterion_none`
    (BCEWithLogitsLoss, reduction='none'); for focal_dice that criterion is built
    with pos_weight=None so focal+alpha is the sole class-balance channel.

        p   = sigmoid(logits);  p_t = p*t + (1-p)*(1-t)
        focal = alpha_t * (1 - p_t)**gamma * bce_map
    """
    valid   = (masks != IGNORE_LABEL).float()
    target  = torch.where(masks == IGNORE_LABEL, torch.zeros_like(masks), masks)
    bce_map = criterion_none(logits, target)
    p       = torch.sigmoid(logits)
    p_t     = p * target + (1.0 - p) * (1.0 - target)
    focal_map = ((1.0 - p_t) ** FOCAL_GAMMA) * bce_map
    if FOCAL_ALPHA is not None:
        alpha_t = FOCAL_ALPHA * target + (1.0 - FOCAL_ALPHA) * (1.0 - target)
        focal_map = alpha_t * focal_map
    return (focal_map * valid).sum() / valid.sum().clamp(min=1.0)


def _seg_loss(criterion_none, logits, masks, loss_mode="bce_dice"):
    """Combined masked segmentation loss (all terms IGNORE-aware).

    loss_mode "focal_dice" → FOCAL_WEIGHT*focal + DICE_WEIGHT*dice (Edit F);
    otherwise → BCE_WEIGHT*bce + DICE_WEIGHT*dice (default, run-5 baseline).
    Returns (combined, primary_component, dice_component).
    """
    dice = _masked_dice(logits, masks)
    if loss_mode == "focal_dice":
        focal = _masked_focal(criterion_none, logits, masks)
        return FOCAL_WEIGHT * focal + config.DICE_WEIGHT * dice, focal, dice
    bce = _masked_bce(criterion_none, logits, masks)
    return config.BCE_WEIGHT * bce + config.DICE_WEIGHT * dice, bce, dice


def _compute_pos_weight(df):
    """RAW BCE ``pos_weight`` = (#background labeled px) / (#canopy labeled px)
    over the given tiles' label rasters, excluding IGNORE (255). Unclamped — the
    caller applies a tier-specific clamp (Tune Fix 1) and logs both values.
    Returns 1.0 (no-op weighting) when the split holds no canopy pixels.
    """
    pos = neg = 0
    for mp in df["mask_path"]:
        with rasterio.open(mp) as src:
            m = src.read(1)
        pos += int((m == 1).sum())
        neg += int((m == 0).sum())
    if pos == 0:
        return 1.0
    return float(neg / pos)


def _train_one_epoch(model, loader, optimizer, scaler, criterion, device,
                     loss_mode="bce_dice", freeze_bn=False):
    model.train()
    if freeze_bn:
        _set_encoder_bn_eval(model)   # re-pin frozen-encoder BN after train()
    loss_sum = seg_sum = 0.0       # seg_sum tracks the combined seg loss (no L1)
    n = 0
    for batch in loader:
        if config.AUX_HEIGHT:
            imgs, masks, heights, _ = batch
            heights = heights.to(device, non_blocking=True)
        else:
            imgs, masks, _ = batch
            heights = None
        imgs = imgs.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)
        optimizer.zero_grad()
        with torch.amp.autocast("cuda"):
            out = model(imgs)
            logits, height_pred = (out if isinstance(out, (tuple, list)) else (out, None))
            seg, _p, _dice = _seg_loss(criterion, logits, masks, loss_mode)
            aux_h = (_masked_l1(height_pred, heights)
                     if (heights is not None and height_pred is not None) else None)
        loss = seg if aux_h is None else seg + config.HEIGHT_LAMBDA * aux_h
        if L1_LAMBDA > 0:
            l1 = sum(p.abs().sum() for p in model.parameters() if p.requires_grad)
            loss = loss + L1_LAMBDA * l1
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()
        loss_sum += loss.item(); seg_sum += seg.item(); n += 1
    return loss_sum / max(n, 1), seg_sum / max(n, 1)


# Threshold grid for the best-threshold IoU: swept so a probability-scale/
# calibration shift (IoU@0.5 drops while the model still ranks fine) is
# distinguishable from real degradation, and so checkpoint selection is robust to
# where the operating point sits. 0.5 must stay in the grid (reported separately).
_VAL_THRESH_GRID = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
_VAL_THRESH_I05  = _VAL_THRESH_GRID.index(0.5)


def _validate(model, loader, criterion, device, loss_mode="bce_dice"):
    model.eval()
    seg_sum = 0.0        # seg_sum = combined seg loss (matches train objective)
    n = 0
    # v039: pool inter/pred/tgt over the WHOLE val set, then compute one IoU per
    # threshold. Global (dataset-level) IoU is the honest metric; the old per-batch
    # mean scored target-empty batches as 0 and biased selection on a bg-heavy pool.
    ntg = len(_VAL_THRESH_GRID)
    inter_g = torch.zeros(ntg, device=device)
    pred_g  = torch.zeros(ntg, device=device)
    tgt_total = torch.zeros((), device=device)
    with torch.no_grad():
        for batch in loader:
            if config.AUX_HEIGHT:
                imgs, masks, _heights, _ = batch
            else:
                imgs, masks, _ = batch
            imgs = imgs.to(device, non_blocking=True)
            masks = masks.to(device, non_blocking=True)
            with torch.amp.autocast("cuda"):
                out = model(imgs)
                logits, height_pred = (out if isinstance(out, (tuple, list)) else (out, None))
                seg, _p, _dice = _seg_loss(criterion, logits, masks, loss_mode)
            seg_sum += seg.item(); n += 1
            valid = (masks != IGNORE_LABEL).float()
            prob  = torch.sigmoid(logits.float())
            tgt   = (masks == 1).float() * valid
            tgt_total += tgt.sum()
            for i, t in enumerate(_VAL_THRESH_GRID):
                p = (prob > t).float() * valid
                inter_g[i] += (p * tgt).sum()
                pred_g[i]  += p.sum()
    union_g  = pred_g + tgt_total - inter_g
    iou_grid = (inter_g / union_g.clamp(min=1e-8)).tolist()
    bt_i = max(range(ntg), key=lambda i: iou_grid[i])
    return (seg_sum / max(n, 1), iou_grid[_VAL_THRESH_I05],
            iou_grid[bt_i], _VAL_THRESH_GRID[bt_i])


def _seed_everything(seed):
    """P6.2: make a training run repeatable-in-principle and RECORD the seed.

    Python/numpy/torch(+cuda) are seeded; DataLoader workers get a derived seed
    via _worker_init/_loader_generator. cudnn.benchmark stays ON and AMP stays
    nondeterministic — accepted and documented (the manifest records the seed;
    bitwise reproducibility is not the goal, bounded variation is).
    """
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    print(f"  Seeds: python/numpy/torch(+cuda) = {seed}  "
          f"(cudnn.benchmark + AMP nondeterminism accepted)")


def _worker_init(worker_id):
    import random
    random.seed(RANDOM_SEED + worker_id)
    np.random.seed(RANDOM_SEED + worker_id)


def _loader_generator():
    g = torch.Generator()
    g.manual_seed(RANDOM_SEED)
    return g


_STAGE_RCLONE_REMOTE = "treedata-user"     # gen_vm_bootstrap.py's WRITER remote
_STAGE_MOUNT_PREFIX  = "/content/drive/MyDrive/treedata/"
_stage_rclone_probe = None


def _bulk_stage_ok(src_root):
    """True iff a bulk `rclone copy` can replace the per-file staging read.

    Deliberately narrow — same activation discipline as tiling.py's bulk WRITE:
    posix, the path really is under the Drive mount, rclone is on PATH, and the
    writer remote exists. Anywhere else (Windows QC, a dry run, a VM without
    rclone) this answers False and the historical per-file loop runs unchanged.
    """
    global _stage_rclone_probe
    if os.name != "posix" or not str(src_root).startswith(_STAGE_MOUNT_PREFIX):
        return False
    if _stage_rclone_probe is None:
        _stage_rclone_probe = False
        try:
            if shutil.which("rclone"):
                r = subprocess.run(["rclone", "listremotes"], capture_output=True,
                                   text=True, timeout=60)
                _stage_rclone_probe = (r.returncode == 0 and
                                       f"{_STAGE_RCLONE_REMOTE}:" in (r.stdout or "").split())
        except Exception:                              # noqa: BLE001 — any failure = no
            _stage_rclone_probe = False
    return _stage_rclone_probe


def _bulk_stage_tiles(src_root, dst_root, n_expected):
    """One server-side-listed bulk copy of a tile dir. Returns files copied, or 0.

    0 means "did not work, use the per-file loop" — never a silent partial. The
    caller re-copies everything on 0, which is safe because --checksum makes the
    bulk pass idempotent and the per-file pass skips size-matched files.
    """
    rel = str(src_root)[len(_STAGE_MOUNT_PREFIX):].strip("/")
    try:
        dst_root.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["rclone", "copy", f"{_STAGE_RCLONE_REMOTE}:{rel}", str(dst_root),
             "--transfers", "16", "--checkers", "16", "--checksum"],
            capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            print(f"  (bulk stage rc={r.returncode}, falling back to per-file: "
                  f"{(r.stderr or '')[-160:]})")
            return 0
        got = sum(1 for _ in dst_root.rglob("*.tif"))
        if got < n_expected:
            print(f"  (bulk stage short: {got} < {n_expected} expected — per-file fallback)")
            return 0
        print(f"  ✓ bulk-staged {got} tiles via rclone (was N FUSE opens)")
        return got
    except Exception as e:                             # noqa: BLE001
        print(f"  (bulk stage raised {type(e).__name__}: {e} — per-file fallback)")
        return 0


def _stage_tiles_local(idx_df, label):
    """P4.2: stage the year's tile set to local NVMe at train start.

    Training used to re-read every tile over the Drive FUSE mount EVERY EPOCH.
    Copy the set once (0.2-0.7 GB measured per year — same pattern as
    _stage_imagery_local), rewrite the index's baked-absolute paths (see
    tiling.py: they are written as /content/drive/... strings), and let the
    epochs read NVMe. Any failure falls back to the original Drive paths, unchanged.
    P11.4: the exists/size pass runs OUTSIDE the staging lock (thousands of FUSE
    stats, nothing copied on a resume); only a >= STAGE_LOCK_MIN_BYTES (1 GiB)
    copy set takes the lock — no existing tile set reaches that, so today this
    copy runs unlocked by design of the floor; tick/tock wrap the copy alone.
    """
    first = str(idx_df.iloc[0]["img_path"]) if len(idx_df) else ""
    if not first.startswith("/content/drive"):
        return idx_df                       # already local (or not on Colab)
    kinds = {"img_path": "images", "mask_path": "masks", "height_path": "heights"}
    cols = [c for c in kinds if c in idx_df.columns]
    dst_root = LOCAL_SCRATCH / "tiles" / str(label)
    try:
        new_cols = {c: [] for c in cols}
        todo, todo_bytes = [], 0
        for _, row in idx_df.iterrows():
            for c in cols:
                p = row[c]
                if not (isinstance(p, str) and p):
                    new_cols[c].append(p)
                    continue
                src = Path(p)
                dst = dst_root / str(row["split"]) / kinds[c] / str(row["tile_name"])
                src_size = src.stat().st_size
                if not dst.exists() or dst.stat().st_size != src_size:
                    todo.append((src, dst))
                    todo_bytes += src_size
                new_cols[c].append(str(dst))
        n_copied = 0
        if todo:
            lock = (_StagingLock(f"tiles {label}") if todo_bytes >= STAGE_LOCK_MIN_BYTES
                    else contextlib.nullcontext())
            with lock:                      # P11.4: one bulk Drive copy at a time
                tick(f"stage tiles {label}")
                # BULK READ (2026-08-29). The per-file loop below reads each tile
                # individually over the FUSE mount. Measured on this night's run:
                # 613 tiles took 55+ min with the GPU at 0% and 6 MB allocated —
                # an A100 sitting idle moving files. A tile set is ~0.65 GB, under
                # STAGE_LOCK_MIN_BYTES, so nothing even serialises two arms doing
                # it at once. tiling.py already solved the WRITE direction this way
                # (78-138 s for the same volume); the READ direction never got it.
                # ONE `rclone copy` of the arm's tile dir replaces N FUSE opens.
                # Falls through to the per-file loop on ANY failure, so the slow
                # path stays the safety net rather than being deleted.
                src_root = Path(str(idx_df.iloc[0]["img_path"])).parents[2]
                if _bulk_stage_ok(src_root):
                    n_copied = _bulk_stage_tiles(src_root, dst_root, len(todo))
                if not n_copied:
                    for src, dst in todo:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        n_copied += 1
                tock(f"stage tiles {label}")
        out = idx_df.copy()
        for c in cols:
            out[c] = new_cols[c]
        print(f"  Tiles staged local: {n_copied} files copied ({todo_bytes / 1e9:.2f} GB) → {dst_root}")
        return out
    except Exception as e:
        print(f"  WARNING: tile staging failed ({e}); training reads from Drive")
        return idx_df


def _model_state_of(model):
    """The state_dict of the REAL module — unwrapping torch.compile.

    Split out of _save_ckpt so the selection-smoothing ring captures exactly the
    same keys the checkpoint writer does. Capturing the COMPILED wrapper instead
    would prefix every key with `_orig_mod.`, and load_state_into's
    strict=False load would then silently match NOTHING — a random-init model
    deployed with no error raised anywhere. That is the one silent-failure mode
    in this whole path, so both writers go through this function.
    """
    return (model._orig_mod.state_dict() if hasattr(model, "_orig_mod")
            else model.state_dict())


def _save_ckpt_state(phase, epoch, state, optim_state, sched_state,
                     history, best_val, path, extra=None):
    """Write a checkpoint from an ALREADY-CAPTURED state dict.

    Body lifted verbatim out of _save_ckpt (2026-08-29) so a checkpoint can also
    be written from a snapshot taken at an earlier epoch (centred selection
    smoothing needs the weights of epoch i once epoch i+K//2 has been seen).
    _save_ckpt keeps its exact previous behaviour by capturing live state and
    calling straight through — the default path is unchanged except that the
    dict is now assembled here.
    """
    # verified write (P4.1): torch.save to local NVMe, then size-verified copy to
    # Drive. Size-only (no sha) because this runs many times per training and the
    # observed failure class is truncation, which size catches; the once-per-run
    # rasters get the full sha256 treatment instead.
    path = Path(path)
    local = _local_artifact_path(path)
    payload = {"phase": phase, "epoch": epoch, "model_state": state,
               "optim_state": optim_state, "sched_state": sched_state,
               "history": history, "best_val": best_val,
               "in_channels": config.IN_CHANNELS,          # 3=RGB, 4=RGB+structure
               "aux_height_head": bool(config.AUX_HEIGHT), # height-prediction head present
               "hs_source": config.HS_SOURCE}              # which raster band 4 was
    if extra:
        payload.update(extra)
    torch.save(payload, local)
    if local != path:
        _copy_to_drive(local, path, checksum=False)
        try:
            local.unlink()
        except OSError:
            pass


def _save_ckpt(phase, epoch, model, optim, sched, history, best_val, path):
    _save_ckpt_state(phase, epoch, _model_state_of(model), optim.state_dict(),
                     sched.state_dict(), history, best_val, path)


# ══════════════════════════════════════════════════════════════════════════════
#  Checkpoint selection: raw per-epoch peak (default) vs K-epoch smoothed peak
# ══════════════════════════════════════════════════════════════════════════════

def _centred_moving_average(values, k):
    """K-epoch CENTRED moving average, EDGE-TRUNCATED (never zero-padded).

    values[i] averages over indices [i-k//2, i+k//2] clipped to the series, so the
    first and last k//2 entries average over the shorter window that actually
    exists rather than being dropped or diluted with zeros. k=1 returns the input
    values unchanged — that identity is what makes --select-smooth 1 exactly
    today's raw-peak selection.

    ONE implementation, used by both the online selector (which needs the value
    for epoch i as soon as epoch i+k//2 has run) and the post-hoc loss-history
    column, so the CSV can never disagree with what was actually selected.
    """
    n = len(values)
    if k <= 1 or n == 0:
        return [float(v) for v in values]
    half = k // 2
    out = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        w = values[lo:hi]
        out.append(float(sum(w)) / len(w))
    return out


class _SmoothCkptSelector:
    """Picks the DEPLOYED epoch by the smoothed metric, holding its real weights.

    Constructed only when SELECT_SMOOTH_K > 1 — at K=1 the caller leaves this
    None and the untouched raw best-checkpoint logic is the whole story.

    Save policy (the centred-smoothing trap): the smoothed value of epoch i is
    only final once epoch i+half has run, so the decision LAGS the training loop.
    A naive implementation that picked the smoothed argmax out of the finished
    loss-history CSV would then have no weights left for that epoch and would
    deploy the wrong (or the last-saved) checkpoint. This class instead keeps a
    ring of the last `half+1` epochs' CPU weight snapshots, so the moment epoch
    i's smoothed value finalises its real weights are still in hand; the winner
    is copied out and the ring rolls on. Peak cost is (half+2) CPU copies of the
    model state (~371 MB each for the resnet101 U-Net) — reported at construction.

    Smoothing runs WITHIN a phase, not across the A→B boundary: Phase B restarts
    from the best Phase-A checkpoint, so the two series are separate trajectories
    and averaging across the seam would blend unrelated weights' scores. The
    winners are then compared ACROSS phases with the same strict >/< and the same
    A-then-B order as the raw logic, so the global pick reproduces exactly at K=1.
    """

    def __init__(self, k, maximize, model_mb=None):
        self.k = int(k)
        self.half = self.k // 2
        self.maximize = bool(maximize)
        self.ring = deque()          # [(phase, epoch, state), ...] pending finalisation
        self.raw = []                # raw metric of the CURRENT phase
        self.best = None             # (smoothed, phase, epoch, raw, state)
        est = ((self.half + 2) * model_mb / 1024.0) if model_mb else None
        print(f"  Ckpt selection: {self.k}-epoch CENTRED moving average of the "
              f"early-stop metric (edge-truncated)"
              + (f"; holds ≤{self.half + 2} CPU weight snapshots "
                 f"(~{est:.1f} GB)" if est else ""))

    # ── internals ────────────────────────────────────────────────────────────
    def _better(self, a, b):
        return a > b if self.maximize else a < b

    def _finalise(self, upto):
        """Score every ring entry whose centred window is complete (index < upto)."""
        sm = _centred_moving_average(self.raw, self.k)
        while self.ring and self.ring[0][1] - 1 < upto:
            phase, ep, state = self.ring.popleft()
            i = ep - 1
            if self.best is None or self._better(sm[i], self.best[0]):
                self.best = (sm[i], phase, ep, self.raw[i], state)

    # ── public ───────────────────────────────────────────────────────────────
    def observe(self, phase, ep, es_val, model):
        """Record epoch `ep` (1-based) of `phase` and snapshot its weights."""
        self.raw.append(float(es_val))
        state = {kk: v.detach().to("cpu", copy=True)      # copy=True: a CPU-run
                 for kk, v in _model_state_of(model).items()}   # .cpu() would alias
        self.ring.append((phase, ep, state))
        self._finalise(len(self.raw) - self.half)         # all windows now closed

    def end_phase(self):
        """Close the phase: the trailing `half` epochs get their truncated windows."""
        self._finalise(len(self.raw))
        self.raw = []
        self.ring.clear()

    @property
    def selection(self):
        """(smoothed_val, phase, epoch, raw_val) of the winner, or None."""
        return None if self.best is None else self.best[:4]

    def write(self, path, history, extra=None):
        """Save the winning epoch's REAL weights to `path`."""
        if self.best is None:
            return False
        sm, phase, ep, raw, state = self.best
        # optim/sched are deliberately None: they would have to be the SELECTED
        # epoch's, and holding AdamW's two moment buffers per ring slot would
        # triple the snapshot cost for state nothing in this repo ever reads back
        # (grep: phase4seg writes optim_state, only phase0/phase3 read theirs).
        _save_ckpt_state(phase, ep, state, None, None, history, raw, path,
                         extra=extra)
        return True

    def release(self):
        self.ring.clear()
        self.best = None
        self.raw = []


def _state_mb(model):
    try:
        return sum(v.numel() * v.element_size()
                   for v in _model_state_of(model).values()) / 1e6
    except Exception:
        return None


def _stop_reason(es, ran, budget):
    """PATIENCE or EPOCH_CAP — the fact no run used to record.

    `es` is the epochs-since-improvement counter as the loop left it, `ran` the
    epochs actually executed, `budget` the configured cap.
    """
    if budget == 0:
        return "skipped"
    if es >= EARLY_STOP_PAT:
        return "patience"
    if ran >= budget:
        return "epoch_cap"
    return "incomplete"          # loop exited some other way (should not happen)


def _phase_smoothed(history, k):
    """Post-hoc smoothed series over the FINISHED history, smoothed within phase.

    Same _centred_moving_average the online selector used, applied per phase, so
    the CSV column is provably the series that drove the pick — not a re-derived
    approximation.
    """
    out = [None] * len(history["es_val"])
    for ph in ("A", "B"):
        idx = [i for i, p in enumerate(history["phase"]) if p == ph]
        sm = _centred_moving_average([history["es_val"][i] for i in idx], k)
        for j, i in enumerate(idx):
            out[i] = sm[j]
    return out


def _record_manifest_training(label, payload):
    """Add this year's training-stop + checkpoint-selection block to the run
    manifest. Best-effort, exactly like the manifest writer itself — provenance
    must never be able to kill a run."""
    try:
        run_id = getattr(config, "RUN_ID", None)
        if not run_id or run_id == "unrecorded":
            return
        import json as _json
        mp = OUT_DIR / "runs" / run_id / "manifest.json"
        if not mp.exists():
            return
        man = _json.loads(mp.read_text(encoding="utf-8"))
        man.setdefault("training", {})[label] = payload
        mp.write_text(_json.dumps(man, indent=2), encoding="utf-8")
    except Exception as e:                                       # noqa: BLE001
        print(f"  WARNING: training block not added to manifest ({e})")


def _finish_selection(label, history, es_metric, es_maximize, best_val, raw_best,
                      smooth_k, sel, best_ckpt, stop_a, stop_b, ran_b):
    """Deploy the chosen epoch, write the loss history, and record WHY it stopped.

    At K=1 `sel` is None: best_ckpt already holds the raw-peak epoch, written
    during training exactly as it always was, and nothing here rewrites it.
    """
    sm = _phase_smoothed(history, smooth_k)
    n = len(history["es_val"])
    # raw argmax/argmin in the SAME order and with the SAME strict comparison the
    # training loops used, so the first epoch to reach the peak wins ties.
    ri = mi = None                        # raw argbest, smoothed argbest
    for i in range(n):
        if ri is None or (history["es_val"][i] > history["es_val"][ri] if es_maximize
                          else history["es_val"][i] < history["es_val"][ri]):
            ri = i
        if mi is None or (sm[i] > sm[mi] if es_maximize else sm[i] < sm[mi]):
            mi = i

    def _row_of(phase, epoch, fallback):
        return next((i for i in range(n) if history["phase"][i] == phase
                     and history["epoch"][i] == epoch), fallback)

    # Default (K=1, or any failure below): the raw peak is what best_ckpt holds.
    deployed = "raw"
    sel_phase, sel_epoch = raw_best[0], raw_best[1]
    sel_row = _row_of(sel_phase, sel_epoch, ri)

    if sel is not None:
        pick = sel.selection                 # (smoothed, phase, epoch, raw)
        post = (history["phase"][mi], history["epoch"][mi]) if mi is not None else None
        if pick is None:
            print("  WARNING: --select-smooth held no epoch (no validation epochs "
                  "ran?) — leaving the raw-peak checkpoint in place.")
        else:
            # Online (lagged) pick and post-hoc pick are the SAME arithmetic on the
            # SAME numbers; a disagreement means a bug in the ring, so say so loudly
            # and deploy the online pick — its weights are the ones actually held.
            if post is not None and (pick[1], pick[2]) != post:
                print(f"  WARNING: smoothed-selection disagreement — online picked "
                      f"{pick[1]}E{pick[2]}, post-hoc {post[0]}E{post[1]}; "
                      f"deploying the online pick (it owns the weights).")
            if (pick[1], pick[2]) == (raw_best[0], raw_best[1]):
                # Same epoch: best_ckpt on disk already IS those weights, and it
                # still carries its optimiser/scheduler state. Rewriting would cost
                # a ~371 MB Drive round-trip to produce a strictly poorer file.
                deployed = "smoothed(==raw)"
                print(f"  Smoothed selection agrees with the raw peak "
                      f"({pick[1]}E{pick[2]}) — best_ckpt left exactly as written.")
            elif sel.write(best_ckpt, history, extra={
                    "select_smooth_k": smooth_k, "selected_by": "smoothed",
                    "es_metric": es_metric,
                    "raw_best_phase": raw_best[0], "raw_best_epoch": raw_best[1],
                    "raw_best_val": (float(history["es_val"][ri])
                                     if ri is not None else None),
                    "sel_smooth_val": float(pick[0])}):
                deployed = "smoothed"
                sel_phase, sel_epoch = pick[1], pick[2]
                sel_row = _row_of(sel_phase, sel_epoch, sel_row)
                print(f"  ★ DEPLOYED {sel_phase}E{sel_epoch} — smoothed {es_metric}"
                      f"={pick[0]:.4f} (raw {pick[3]:.4f}); REPLACES the raw peak "
                      f"{raw_best[0]}E{raw_best[1]} "
                      f"(raw {history['es_val'][ri]:.4f}) in {best_ckpt.name}")
        sel.release()

    df = pd.DataFrame(history)
    df["es_smooth"] = sm
    df["is_raw_best"] = [1 if i == ri else 0 for i in range(n)]
    df["is_smooth_best"] = [1 if i == mi else 0 for i in range(n)]
    df["is_deployed"] = [1 if i == sel_row else 0 for i in range(n)]
    df["select_smooth_k"] = smooth_k
    df["es_metric"] = es_metric
    df["stop_reason_a"] = stop_a
    df["stop_reason_b"] = stop_b
    df.to_csv(MODELS_DIR / f"sem_loss_history_{label}{_tag_sfx()}.csv", index=False)

    def _at(i, series):
        return float(series[i]) if i is not None else None

    summary = {
        "es_metric": es_metric,
        "select_smooth_k": smooth_k,
        "deployed_by": deployed,
        "stop_reason_a": stop_a, "stop_reason_b": stop_b,
        "epochs_a": sum(1 for p in history["phase"] if p == "A"),
        "epochs_b": ran_b,
        "epoch_cap_a": config.EPOCHS_PHASE_A, "epoch_cap_b": config.EPOCHS_PHASE_B,
        "early_stop_patience": EARLY_STOP_PAT,
        "raw_best_phase": raw_best[0], "raw_best_epoch": raw_best[1],
        "raw_best_val": _at(ri, history["es_val"]),
        "smooth_best_phase": history["phase"][mi] if mi is not None else None,
        "smooth_best_epoch": history["epoch"][mi] if mi is not None else None,
        "smooth_best_val": _at(mi, sm),
        "deployed_phase": sel_phase, "deployed_epoch": sel_epoch,
        "deployed_raw_val": _at(sel_row, history["es_val"]),
        "deployed_smooth_val": _at(sel_row, sm),
        "best_val": (float(best_val) if best_val is not None
                     and np.isfinite(best_val) else None),
    }
    if ri is None:
        print("  Selection: no epoch produced a finite metric — nothing deployed.")
    else:
        print(f"  Selection [{deployed}]: raw peak {raw_best[0]}E{raw_best[1]}"
              f"={summary['raw_best_val']:.4f}  |  smoothed(K={smooth_k}) peak "
              f"{summary['smooth_best_phase']}E{summary['smooth_best_epoch']}"
              f"={summary['smooth_best_val']:.4f}  |  DEPLOYED "
              f"{sel_phase}E{sel_epoch} (raw={summary['deployed_raw_val']:.4f})")
    _record_manifest_training(label, summary)
    return summary


def _freeze_encoder(model):
    enc = model._orig_mod.encoder if hasattr(model, "_orig_mod") else model.encoder
    for p in enc.parameters():
        p.requires_grad = False
    # Inflated (4ch) stem must stay trainable in Phase A: its structure channel
    # is ZERO-INIT, and frozen-at-zero means the 4th channel contributes nothing
    # for all of Phase A, then must learn from exact zero at LR_PHASE_B=5e-6 —
    # it never gets off the ground (2016 ablation: struct≈fr≈rgb, channel dead).
    # RGB behaviour is still preserved at start (the extra channel IS zero);
    # Phase A's LR gives the new channel a real chance to learn its mixing.
    if config.IN_CHANNELS > 3 and hasattr(enc, "conv1"):
        for p in enc.conv1.parameters():
            p.requires_grad = True
        print(f"    (inflated {config.IN_CHANNELS}ch input conv kept trainable in Phase A)")


def _unfreeze_encoder(model):
    enc = model._orig_mod.encoder if hasattr(model, "_orig_mod") else model.encoder
    for p in enc.parameters():
        p.requires_grad = True


def _set_encoder_bn_eval(model):
    """Put the encoder's BatchNorm layers in eval mode so they USE the frozen
    2020-pretrained running stats and STOP updating them from each batch.

    `requires_grad=False` alone does NOT freeze BN: `model.train()` (called every
    epoch) flips all BN back to train mode, where they track running stats off
    the current batches. With a trainable input-conv shifting the input and a
    canopy-scarce / negative-heavy pool (batch stats far from 2020), those
    running stats drift until the FROZEN deeper weights receive out-of-distribution
    normalised features → eval-time collapse at a fixed epoch (the E6 cliff). This
    must be re-applied AFTER every model.train(). The trainable decoder BN is left
    in train mode — only the frozen encoder is pinned to its pretrained stats.
    """
    enc = model._orig_mod.encoder if hasattr(model, "_orig_mod") else model.encoder
    n = 0
    for m in enc.modules():
        if isinstance(m, torch.nn.modules.batchnorm._BatchNorm):
            m.eval(); n += 1
    return n


# ══════════════════════════════════════════════════════════════════════════════
#  Step 3 — Per-year fine-tune (Phase A frozen + Phase B full, from P3 ckpt)
# ══════════════════════════════════════════════════════════════════════════════

def step_train(label, batch_size=BATCH_SIZE, p3_ckpt=None, dry_run=False, compile_model=True):
    _ensure_torch()
    entry = entry_for(label)
    tier  = tier_for(entry)
    print(f"\n── [{label}] Step 3: Fine-tune ({tier}) ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}"
          + (f"  GPU: {torch.cuda.get_device_name(0)}" if device.type == "cuda" else ""))

    index_path = tile_dir_for(label) / f"tile_index_{label}.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first")
        return
    idx_df = pd.read_csv(index_path)
    idx_df = _stage_tiles_local(idx_df, label)     # P4.2: epochs read NVMe, not FUSE
    train_df = idx_df[idx_df["split"] == "train"].reset_index(drop=True)
    test_df  = idx_df[idx_df["split"] == "test"].reset_index(drop=True)
    print(f"  Train tiles: {len(train_df)}  |  held-out test: {len(test_df)}")
    if len(train_df) == 0:
        print("  ERROR: no training tiles — skipping.")
        return
    if dry_run:
        print("  Dry run — not training")
        return

    # Train/val split for early stopping.
    #  • fine tier: tiles are non-overlapping (stride == TILE_SIZE), so the
    #    fixed-pixel spatial-buffer split gives clean separation (matches Phase 3).
    #  • medium/coarse: tiles OVERLAP (stride < TILE_SIZE) and sites are small,
    #    so a fixed 512px Chebyshev buffer prunes the entire training set (it did
    #    for 2000: train=0). Honest spatial CV isn't achievable at these GSDs —
    #    use a random split for early stopping only; the reported coarse metric
    #    is the in-sample IoU in step_evaluate, and Phase 6 cross-checks against
    #    2020 detections.
    tier_stride = TIER_TILE_PARAMS[tier]["stride"]
    ftr = fva = None

    # Fix 4: if a geographically-blocked val split was carved at tiling time
    # (coarse city-wide), use it directly — it is already >520 m from train, so
    # no random/neighbour val tiles are needed. Replaces the leaked random-15%
    # fallback for that path.
    val_df = idx_df[idx_df["split"] == "val"].reset_index(drop=True)
    use_blocked_val = len(val_df) > 0     # citywide-coarse path (bin-balanced pool)
    if use_blocked_val:
        ftr = train_df.reset_index(drop=True)
        fva = val_df.reset_index(drop=True)
        print(f"  Val split: BLOCKED hold-out from tile index ({len(fva)} tiles)")

    if ftr is None and tier_stride >= TILE_SIZE and train_df["site"].nunique() > 1 and len(train_df) >= 25:
        folds = make_spatial_buffer_splits(
            train_df, n_folds=5, buffer_px=SPATIAL_BUFFER_PX, seed=42)
        tr_idx, val_idx = folds[0]
        if len(tr_idx) > 0 and len(val_idx) > 0:
            ftr = train_df.iloc[tr_idx].reset_index(drop=True)
            fva = train_df.iloc[val_idx].reset_index(drop=True)
        else:
            print("  (spatial-buffer split left an empty side — random split)")

    if ftr is None:
        if len(train_df) >= 7:
            # Stratify by site only when every site has ≥2 tiles (else sklearn errors).
            strat = (train_df["site"]
                     if train_df["site"].nunique() > 1
                     and train_df["site"].value_counts().min() >= 2 else None)
            ftr, fva = train_test_split(train_df, test_size=0.15,
                                        random_state=RANDOM_SEED, stratify=strat)
            ftr = ftr.reset_index(drop=True); fva = fva.reset_index(drop=True)
        else:
            # Too few tiles to hold any out — validate on the training set.
            ftr = train_df.copy(); fva = train_df.copy()

    print(f"  Train split: {len(ftr)}  |  Val split: {len(fva)}")
    if len(fva) == 0:           # degenerate — validate on train
        fva = ftr.copy()
    if len(ftr) == 0:
        print("  ERROR: no training tiles after split — skipping.")
        return

    # Match the model to the tiles on disk (3=RGB, 4=RGB+structure) so a structure
    # tile set trains a 4ch model and a plain RGB set trains 3ch — no flag/tile
    # mismatch. Phase-3 (3ch) is inflated to this in load_state_into below.
    # Likewise adopt the tiles' HS_SOURCE tag (stats must match the baked band).
    with rasterio.open(ftr.iloc[0]["img_path"]) as _s0:
        config.IN_CHANNELS = _s0.count
    _sync_hs_source_from_tile(ftr.iloc[0]["img_path"])
    print(f"  Input channels: {config.IN_CHANNELS}  "
          f"({'RGB+structure[' + config.HS_SOURCE + ']' if config.IN_CHANNELS >= 4 else 'RGB'})"
          + (f"  hs-dropout={config.HS_DROPOUT}" if config.IN_CHANNELS >= 4 else ""))

    pin = device.type == "cuda"
    # Sampler (v039 fix): the citywide-coarse pool is already balanced by
    # canopy-fraction bin in _select_citywide_tiles, so use NATURAL (instance-
    # balanced) sampling — plain shuffle — which preserves the true canopy prior
    # (~40% of tiles). The previous inverse-SITE weighting gave the single "city"
    # site (which holds ALL canopy) and each tiny curated pure-negative site EQUAL
    # total sampling mass, so batches ran ~83% pure background → recall crash +
    # train/test prior shift + probability scale dragged below 0.5. Non-citywide
    # (legacy 6-site) pools are NOT pre-balanced, so keep per-site balancing there.
    if use_blocked_val:
        sampler = None
        train_shuffle = True
        print("  Sampler: natural/shuffle (bin-balanced citywide pool; prior preserved)")
    else:
        counts = ftr["site"].value_counts().to_dict()
        weights = ftr["site"].map(lambda s: 1.0 / counts[s]).values.astype(np.float32)
        sampler = WeightedRandomSampler(torch.from_numpy(weights),
                                        num_samples=len(ftr), replacement=True)
        train_shuffle = False
        print("  Sampler: per-site inverse-frequency (6-site pool)")
    _seed_everything(RANDOM_SEED)                              # P6.2
    nw = min(NUM_WORKERS, max(2, len(ftr)))
    train_loader = DataLoader(SemanticDataset(ftr, True), batch_size=batch_size,
                              sampler=sampler, shuffle=train_shuffle,
                              num_workers=nw, pin_memory=pin,
                              drop_last=len(ftr) >= batch_size,
                              persistent_workers=True, prefetch_factor=4,
                              worker_init_fn=_worker_init,
                              generator=_loader_generator())
    val_loader = DataLoader(SemanticDataset(fva, False), batch_size=batch_size,
                            shuffle=False, num_workers=nw, pin_memory=pin,
                            drop_last=False, persistent_workers=True, prefetch_factor=4,
                            worker_init_fn=_worker_init)

    # Fine-tune START = Phase 3 2020 semantic checkpoint (every year, independently).
    p3 = resolve_p3_ckpt(p3_ckpt)
    if p3 is None:
        print("  ERROR: Phase 3 checkpoint (sem_best_2020.pt) not found — "
              "run Phase 3 first or pass --ckpt.")
        return
    model = build_model(device, compile_model=compile_model)
    ck = load_state_into(model, p3, device)
    print(f"  ✓ Fine-tune start: {Path(p3).name}  "
          f"(P3 val_bce={ck.get('best_val', '?')})")

    # pos_weight for class imbalance. Principled Edit 1: coarse retires
    # pos_weight (sampler owns class balance) unless COARSE_USE_POS_WEIGHT is
    # flipped on. Medium keeps the ratio-derived, clamped pos_weight (it does not
    # use the city-wide stratified sampler, so it is not double-rebalanced). Fine
    # stays neutral. Computed from the actual training split (ftr) so held-out val
    # tiles don't leak into the statistic.
    loss_mode = TIER_LOSS_MODE.get(tier, "bce_dice")
    pos_weight_t = None
    if loss_mode == "focal_dice":
        # Focal + alpha is the class-balance channel; do NOT also apply pos_weight
        # (Edit F: one rebalancing channel, not two).
        print(f"  pos_weight ({tier}): N/A — focal+alpha owns class balance")
    elif use_blocked_val:
        # Citywide bin-balanced pool (coarse by default, or ANY tier under
        # --force-citywide): the natural sampler owns class balance, so pos_weight
        # is off unless COARSE_USE_POS_WEIGHT flips it on. Keyed on the POOL, not
        # the GSD tier, so --force-citywide gives a fine year the identical recipe.
        if COARSE_USE_POS_WEIGHT:
            raw = _compute_pos_weight(ftr)
            pw  = float(min(max(raw, POS_WEIGHT_MIN), config.COARSE_POS_WEIGHT_MAX))
            print(f"  pos_weight (citywide): raw={raw:.3f} → {pw:.3f}  "
                  f"(clamped to [{POS_WEIGHT_MIN}, {config.COARSE_POS_WEIGHT_MAX}])")
            pos_weight_t = torch.tensor([pw], device=device)
        else:
            print("  pos_weight (citywide): DISABLED — sampler owns class balance (1.0)")
    elif tier == "medium":
        raw = _compute_pos_weight(ftr)
        pw  = float(min(max(raw, POS_WEIGHT_MIN), POS_WEIGHT_MAX))
        print(f"  pos_weight (medium): raw={raw:.3f} → {pw:.3f}  "
              f"(clamped to [{POS_WEIGHT_MIN}, {POS_WEIGHT_MAX}])")
        pos_weight_t = torch.tensor([pw], device=device)
    else:
        print(f"  pos_weight (fine): 1.0 (disabled)")
    criterion = nn.BCEWithLogitsLoss(reduction="none", pos_weight=pos_weight_t)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    best_ckpt   = MODELS_DIR / f"sem_best_{label}{_tag_sfx()}.pt"
    latest_ckpt = MODELS_DIR / f"sem_latest_{label}{_tag_sfx()}.pt"
    # Early-stop / best-checkpoint criterion follows the POOL, not the GSD tier:
    # any citywide bin-balanced pool (coarse, or a --force-citywide fine year) uses
    # val_iou_bt (its BCE scale drifts below 0.5); 6-site pools use val_bce. Keying
    # on use_blocked_val makes --force-citywide fully unify the recipe.
    es_metric   = "val_iou_bt" if use_blocked_val else TIER_EARLYSTOP.get(tier, "val_bce")
    es_maximize = es_metric in ("val_iou", "val_iou_bt")
    sched_mode  = "max" if es_maximize else "min"
    best_val    = float("-inf") if es_maximize else float("inf")
    print(f"  Early-stop / best-ckpt metric: {es_metric} "
          f"({'maximize' if es_maximize else 'minimize'}), scheduler mode={sched_mode}")
    if loss_mode == "focal_dice":
        print(f"  Loss mode: focal_dice (FOCAL_WEIGHT={FOCAL_WEIGHT} γ={FOCAL_GAMMA} "
              f"α={FOCAL_ALPHA} + DICE_WEIGHT={config.DICE_WEIGHT})")
    else:
        print(f"  Loss mode: bce_dice (BCE_WEIGHT={config.BCE_WEIGHT} + DICE_WEIGHT={config.DICE_WEIGHT})")
    history = {"phase": [], "epoch": [], "train_bce": [], "val_bce": [],
               "val_iou": [], "val_iou_bt": [], "val_thr_bt": [], "es_val": []}
    # Which epoch's weights the RAW rule deploys (what best_ckpt holds during
    # training). Tracked only so the run can SAY it afterwards — the rule itself
    # is untouched.
    raw_best = [None, None]                       # [phase, epoch]
    # --select-smooth: deferred, smoothed selection of the DEPLOYED epoch. None at
    # K=1, and every new code path below is gated on that, so the default run
    # takes the historical path exactly.
    smooth_k = max(1, int(getattr(config, "SELECT_SMOOTH_K", 1)))
    sel = (_SmoothCkptSelector(smooth_k, es_maximize,
                               model_mb=_state_mb(model)) if smooth_k > 1 else None)

    # ── Phase A: frozen encoder ──
    print(f"\n  PHASE A — frozen encoder | {config.EPOCHS_PHASE_A} ep | LR={config.LR_PHASE_A}")
    _freeze_encoder(model)
    if config.FREEZE_ENCODER_BN:
        nbn = _set_encoder_bn_eval(model)
        print(f"    (encoder BN pinned to pretrained running stats: {nbn} layers)")
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=config.LR_PHASE_A, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, mode=sched_mode, factor=0.5, patience=5, threshold=1e-4,
        cooldown=2, min_lr=1e-7)
    scaler = torch.amp.GradScaler("cuda")
    es = 0
    for ep in range(config.EPOCHS_PHASE_A):
        t0 = time.time()
        _, tr_bce = _train_one_epoch(model, train_loader, opt, scaler, criterion,
                                     device, loss_mode, freeze_bn=config.FREEZE_ENCODER_BN)
        v_bce, v_iou, v_iou_bt, v_thr = _validate(model, val_loader, criterion,
                                                  device, loss_mode)
        es_val = (v_iou_bt if es_metric == "val_iou_bt"      # tier-selected metric
                  else v_iou if es_metric == "val_iou" else v_bce)
        sched.step(es_val)
        history["phase"].append("A"); history["epoch"].append(ep + 1)
        history["train_bce"].append(tr_bce); history["val_bce"].append(v_bce)
        history["val_iou"].append(v_iou)
        history["val_iou_bt"].append(v_iou_bt); history["val_thr_bt"].append(v_thr)
        history["es_val"].append(float(es_val))
        best = es_val > best_val if es_maximize else es_val < best_val
        if best:
            best_val = es_val; es = 0
            raw_best[:] = ["A", ep + 1]
            _save_ckpt("A", ep, model, opt, sched, history, best_val, best_ckpt)
        else:
            es += 1
        if sel is not None:
            sel.observe("A", ep + 1, es_val, model)
        if (ep + 1) % SAVE_EVERY == 0 or ep == config.EPOCHS_PHASE_A - 1:
            _save_ckpt("A", ep, model, opt, sched, history, best_val, latest_ckpt)
        print(f"  A E{ep+1:>3}/{config.EPOCHS_PHASE_A} tr_bce={tr_bce:.4f} "
              f"val_bce={v_bce:.4f} val_iou={v_iou:.4f} "
              f"iou_bt={v_iou_bt:.4f}@{v_thr:.1f} "
              f"lr={opt.param_groups[0]['lr']:.2e} {time.time()-t0:.0f}s"
              f"{' ★' if best else f'  [{es}/{EARLY_STOP_PAT}]'}")
        if es >= EARLY_STOP_PAT:
            print("  Early stop — Phase A"); break
    # WHY training stopped, not just that it did. Four of five 2009 arms hit the
    # EPOCH CAP rather than converging (one with its best epoch LAST), and nothing
    # recorded that, so the truncation hid for a week. One line per phase.
    stop_a = _stop_reason(es, len(history["epoch"]), config.EPOCHS_PHASE_A)
    if sel is not None:
        sel.end_phase()             # trailing epochs get their truncated windows
    print(f"  ✓ Phase A best {es_metric}: {best_val:.4f}")
    print(f"  ⏹ Phase A stopped by {stop_a.upper()} after "
          f"{len(history['epoch'])}/{config.EPOCHS_PHASE_A} epochs "
          f"(best epoch {raw_best[1]}, patience {EARLY_STOP_PAT})")

    # ── Phase B: full model ── (skipped entirely when EPOCHS_PHASE_B == 0,
    # e.g. fast diagnostic runs — Phase B never recovers a Phase-A collapse).
    if config.EPOCHS_PHASE_B == 0:
        print("\n  PHASE B — skipped (--epochs-phase-b 0)")
        stop_b, ran_b = "skipped", 0
    else:
        best_val, stop_b, ran_b = _run_phase_b(
            model, train_loader, val_loader, criterion, device, loss_mode,
            es_metric, es_maximize, sched_mode, best_val, best_ckpt,
            latest_ckpt, history, raw_best, sel)

    # ── deploy: raw peak (default) or the smoothed peak's REAL weights ────────
    summary = _finish_selection(label, history, es_metric, es_maximize, best_val,
                                raw_best, smooth_k, sel, best_ckpt,
                                stop_a, stop_b, ran_b)
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()
    return summary


def _run_phase_b(model, train_loader, val_loader, criterion, device, loss_mode,
                 es_metric, es_maximize, sched_mode, best_val, best_ckpt,
                 latest_ckpt, history, raw_best=None, sel=None):
    if raw_best is None:
        raw_best = [None, None]
    n_before = len(history["epoch"])
    print(f"\n  PHASE B — full model | {config.EPOCHS_PHASE_B} ep | LR={LR_PHASE_B}")
    # v039 fix: resume from the BEST Phase-A checkpoint, not the last-epoch weights.
    # Previously Phase B continued from whatever weights Phase A ended on (which
    # early-stopping had already rejected), so it started behind its own best_val
    # and could never improve on it → Phase B wasted. Reload best before unfreezing.
    if best_ckpt.exists():
        load_state_into(model, best_ckpt, device)
        print(f"    (resumed from best Phase-A checkpoint: {es_metric}={best_val:.4f})")
    _unfreeze_encoder(model)
    opt = torch.optim.AdamW(model.parameters(), lr=LR_PHASE_B, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, mode=sched_mode, factor=0.5, patience=5, threshold=1e-4,
        cooldown=2, min_lr=1e-7)
    scaler = torch.amp.GradScaler("cuda")
    es = 0
    for ep in range(config.EPOCHS_PHASE_B):
        t0 = time.time()
        _, tr_bce = _train_one_epoch(model, train_loader, opt, scaler, criterion,
                                     device, loss_mode)
        v_bce, v_iou, v_iou_bt, v_thr = _validate(model, val_loader, criterion,
                                                  device, loss_mode)
        es_val = (v_iou_bt if es_metric == "val_iou_bt"      # tier-selected metric
                  else v_iou if es_metric == "val_iou" else v_bce)
        sched.step(es_val)
        history["phase"].append("B"); history["epoch"].append(ep + 1)
        history["train_bce"].append(tr_bce); history["val_bce"].append(v_bce)
        history["val_iou"].append(v_iou)
        history["val_iou_bt"].append(v_iou_bt); history["val_thr_bt"].append(v_thr)
        history["es_val"].append(float(es_val))
        best = es_val > best_val if es_maximize else es_val < best_val
        if best:
            best_val = es_val; es = 0
            raw_best[:] = ["B", ep + 1]
            _save_ckpt("B", ep, model, opt, sched, history, best_val, best_ckpt)
        else:
            es += 1
        if sel is not None:
            sel.observe("B", ep + 1, es_val, model)
        if (ep + 1) % SAVE_EVERY == 0 or ep == config.EPOCHS_PHASE_B - 1:
            _save_ckpt("B", ep, model, opt, sched, history, best_val, latest_ckpt)
        print(f"  B E{ep+1:>3}/{config.EPOCHS_PHASE_B} tr_bce={tr_bce:.4f} "
              f"val_bce={v_bce:.4f} val_iou={v_iou:.4f} "
              f"iou_bt={v_iou_bt:.4f}@{v_thr:.1f} "
              f"lr={opt.param_groups[0]['lr']:.2e} {time.time()-t0:.0f}s"
              f"{' ★' if best else f'  [{es}/{EARLY_STOP_PAT}]'}")
        if es >= EARLY_STOP_PAT:
            print("  Early stop — Phase B"); break

    ran_b = len(history["epoch"]) - n_before
    stop_b = _stop_reason(es, ran_b, config.EPOCHS_PHASE_B)
    if sel is not None:
        sel.end_phase()
    print(f"  ✓ Phase B best {es_metric}: {best_val:.4f}  → {best_ckpt.name}")
    print(f"  ⏹ Phase B stopped by {stop_b.upper()} after "
          f"{ran_b}/{config.EPOCHS_PHASE_B} epochs (best epoch "
          f"{raw_best[1] if raw_best[0] == 'B' else f'in phase A ({raw_best[1]})'}"
          f", patience {EARLY_STOP_PAT})")
    del opt, scaler
    return best_val, stop_b, ran_b


# ══════════════════════════════════════════════════════════════════════════════
#  Step 4 — Per-year evaluation (pixel accuracy, IoU, Dice vs projected labels)
# ══════════════════════════════════════════════════════════════════════════════

def _metrics(tp, fp, fn, tn):
    total = tp + fp + fn + tn
    acc  = (tp + tn) / total if total else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec  = tp / (tp + fn) if (tp + fn) else 0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    iou  = tp / (tp + fp + fn) if (tp + fp + fn) else 0
    dice = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0
    return dict(accuracy=round(acc, 4), precision=round(prec, 4),
                recall=round(rec, 4), f1=round(f1, 4), iou=round(iou, 4),
                dice=round(dice, 4), tp=tp, fp=fp, fn=fn, tn=tn)


# Cap on pooled pixels for the threshold-independent metrics (memory guard for
# fine years with many tiles). 40M float32+int8 ≈ 200 MB — comfortable.
TI_MAX_PIXELS = 40_000_000


def _threshold_independent_metrics(all_prob, all_gt, f1_at_default):
    """
    Pooled AUROC / average precision / log-loss / best-F1 threshold over all eval
    pixels. Judges the probability RANKING independent of the 0.5 cutoff — the key
    diagnostic for coarse years whose probabilities pile up near 0.5. Returns {} if
    sklearn is missing, a class is absent, or the pixel pool is degenerate.
    """
    if not all_prob:
        return {}
    try:
        import sklearn.metrics as skm
        y_prob = np.concatenate(all_prob)
        y_true = np.concatenate(all_gt).astype(np.int8)
        # Memory guard: subsample if the pool is very large.
        n = y_true.shape[0]
        if n > TI_MAX_PIXELS:
            rng = np.random.default_rng(42)
            sel = rng.choice(n, size=TI_MAX_PIXELS, replace=False)
            y_prob = y_prob[sel]
            y_true = y_true[sel]
        # AUROC / AP need both classes present.
        if y_true.min() == y_true.max():
            return {}
        ti = {
            "auroc":    float(skm.roc_auc_score(y_true, y_prob)),
            "ap":       float(skm.average_precision_score(y_true, y_prob)),
            "log_loss": float(skm.log_loss(y_true, y_prob, labels=[0, 1])),
        }
        prec_c, rec_c, thr_c = skm.precision_recall_curve(y_true, y_prob)
        f1_c = 2 * prec_c * rec_c / (prec_c + rec_c + 1e-12)
        bi = int(np.argmax(f1_c[:-1])) if len(thr_c) else 0
        ti["best_f1"]        = float(f1_c[bi])
        ti["best_f1_thresh"] = float(thr_c[bi]) if len(thr_c) else CANOPY_PROB_THRESHOLD
        # Precision-floor operating point (Fix D): the lowest threshold whose
        # precision ≥ PRECISION_FLOOR — i.e. the highest-recall point that still
        # meets the precision target. prec_c[:-1] aligns with thr_c. Persisted to
        # the eval CSV so step_postproc can use it under --thresh-mode.
        meet = np.where(prec_c[:-1] >= PRECISION_FLOOR)[0] if len(thr_c) else []
        if len(meet):
            fi = int(meet[0])
            ti["prec_floor_thresh"] = float(thr_c[fi])
            ti["prec_at_floor"]     = float(prec_c[fi])
            ti["rec_at_floor"]      = float(rec_c[fi])
        else:                                   # floor unreachable at any threshold
            ti["prec_floor_thresh"] = ""
            ti["prec_at_floor"]     = ""
            ti["rec_at_floor"]      = ""
        return ti
    except Exception as e:
        print(f"  WARNING: threshold-independent metrics failed ({e})")
        return {}


def step_evaluate(label, dry_run=False):
    _ensure_torch()
    entry = entry_for(label)
    tier  = tier_for(entry)
    has_test = TIER_TILE_PARAMS[tier]["has_test"]
    print(f"\n── [{label}] Step 4: Evaluation ({tier}) ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    index_path = tile_dir_for(label) / f"tile_index_{label}.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first"); return
    idx_df = pd.read_csv(index_path)
    eval_df = idx_df[idx_df["split"] == "test"].reset_index(drop=True)
    eval_scope = "held-out test"
    # v039: honesty caveat. Only the coarse-citywide path carves a spatially
    # BLOCKED split (val rows present in the index, >520 m from train). Medium/fine
    # with stride < TILE_SIZE use a RANDOM tile-level test split on 50%-overlapping
    # tiles, so train and "test" tiles overlap → optimistic, leaked metrics. Flag
    # it so these numbers aren't trusted as true held-out until spatial blocking is
    # applied to those tiers.
    has_blocked_split = bool((idx_df["split"] == "val").any())
    tier_stride = TIER_TILE_PARAMS[tier]["stride"]
    if len(eval_df) > 0 and not has_blocked_split and tier_stride < TILE_SIZE:
        eval_scope = "held-out test (TILE-LEVEL split — LEAKS across overlapping tiles)"
    if len(eval_df) == 0:
        # Coarse years have no held-out test → evaluate in-sample (DG4 number).
        eval_df = idx_df.reset_index(drop=True)
        eval_scope = "IN-SAMPLE (no held-out test at this GSD)"
    print(f"  Eval tiles: {len(eval_df)}  [{eval_scope}]")
    if dry_run or len(eval_df) == 0:
        if len(eval_df) == 0:
            print("  No tiles to evaluate."); 
        return

    ckpt = MODELS_DIR / f"sem_best_{label}{_tag_sfx()}.pt"
    if not ckpt.exists():
        print(f"  ERROR: {ckpt} not found — run step train first"); return
    with rasterio.open(eval_df.iloc[0]["img_path"]) as _s0:
        config.IN_CHANNELS = _s0.count           # match the model to the eval tiles
    _sync_hs_source_from_tile(eval_df.iloc[0]["img_path"])
    model = build_model(device, compile_model=False)
    ck = load_state_into(model, ckpt, device)
    model.eval()
    print(f"  Model: {ckpt.name}  (phase={ck.get('phase','?')} "
          f"val_bce={ck.get('best_val','?')})")

    eval_tf = A.Compose([A.Normalize(IMAGENET_MEAN, IMAGENET_STD, max_pixel_value=255.0),
                         ToTensorV2()])
    tp = fp = fn = tn = 0
    site_cm = {}
    all_prob, all_gt = [], []   # pooled pixels for threshold-independent metrics
    with torch.no_grad():
        for _, row in tqdm(eval_df.iterrows(), total=len(eval_df), desc="  Eval"):
            with rasterio.open(row["img_path"]) as src:
                img = src.read().transpose(1, 2, 0)
            with rasterio.open(row["mask_path"]) as src:
                gt = src.read(1).astype(np.float32)
            if config.USE_VI or img.shape[-1] >= 4:      # VI and/or hillshade → numpy norm
                inp = torch.from_numpy(rgb_to_model_input(img)).unsqueeze(0).to(device)
            else:
                inp = eval_tf(image=img)["image"].unsqueeze(0).to(device)
            _out = model(inp)
            _seg = _out[0] if isinstance(_out, (tuple, list)) else _out   # aux-height → tuple
            prob = 1.0 / (1.0 + np.exp(-_seg.squeeze().cpu().numpy()))
            pred = (prob > CANOPY_PROB_THRESHOLD).astype(np.uint8)
            valid = gt != IGNORE_LABEL    # drop unreviewed/nodata pixels
            all_prob.append(prob[valid].ravel().astype(np.float32))
            all_gt.append(gt[valid].ravel().astype(np.int8))
            a = int(((pred == 1) & (gt == 1)).sum()); tp += a
            b = int(((pred == 1) & (gt == 0)).sum()); fp += b
            c = int(((pred == 0) & (gt == 1)).sum()); fn += c
            d = int(((pred == 0) & (gt == 0)).sum()); tn += d
            s = row["site"]
            sm = site_cm.setdefault(s, [0, 0, 0, 0])
            sm[0] += a; sm[1] += b; sm[2] += c; sm[3] += d

    overall = _metrics(tp, fp, fn, tn)   # at the fixed 0.5 cutoff

    # ── Threshold-independent metrics (pooled over all eval pixels) ───────────
    # These judge the model's probability RANKING, independent of the 0.5 cutoff —
    # critical for coarse years where the distribution piles up near 0.5 and the
    # fixed threshold is brutally sensitive. best_f1_thresh is the per-year
    # operating point to use instead of 0.5.
    ti = _threshold_independent_metrics(all_prob, all_gt, overall["f1"])

    # v039: also compute confusion metrics at the DEPLOYED operating threshold
    # (best_f1), not just 0.5. For coarse years the probability scale drifts below
    # 0.5, so IoU/recall@0.5 grossly understate the model and mislead the DG4 gate;
    # inference deploys best_f1_thresh, so THIS is the honest headline number.
    op_thr = (float(ti["best_f1_thresh"])
              if ti.get("best_f1_thresh", "") not in ("", None)
              else CANOPY_PROB_THRESHOLD)
    overall_op = overall
    if all_prob:
        yp = np.concatenate(all_prob); yt = np.concatenate(all_gt)
        pop = yp > op_thr
        tp_o = int((pop & (yt == 1)).sum()); fp_o = int((pop & (yt == 0)).sum())
        fn_o = int((~pop & (yt == 1)).sum()); tn_o = int((~pop & (yt == 0)).sum())
        overall_op = _metrics(tp_o, fp_o, fn_o, tn_o)
    del all_prob, all_gt

    print(f"  {'-'*52}")
    print(f"  IoU={overall['iou']:.4f}  Dice={overall['dice']:.4f}  "
          f"Acc={overall['accuracy']:.4f}  Prec={overall['precision']:.4f}  "
          f"Rec={overall['recall']:.4f}")
    if ti:
        print(f"  AUROC={ti['auroc']:.4f}  AP={ti['ap']:.4f}  "
              f"LogLoss={ti['log_loss']:.4f}   [AP is the honest headline]")
        print(f"  Best-F1 @ thresh {ti['best_f1_thresh']:.3f}  "
              f"(F1={ti['best_f1']:.4f}  vs  {overall['f1']:.4f} @ {CANOPY_PROB_THRESHOLD:.2f})")
        print(f"  @ operating thresh {op_thr:.3f}: IoU={overall_op['iou']:.4f}  "
              f"Dice={overall_op['dice']:.4f}  Prec={overall_op['precision']:.4f}  "
              f"Rec={overall_op['recall']:.4f}   (vs IoU={overall['iou']:.4f} @ 0.50)")
        pf = ti.get("prec_floor_thresh", "")
        if pf not in ("", None):
            print(f"  Precision-floor @ thresh {pf:.3f}  "
                  f"(P={ti.get('prec_at_floor', 0):.3f}  R={ti.get('rec_at_floor', 0):.3f}, "
                  f"floor={PRECISION_FLOOR})")
        else:
            print(f"  Precision-floor {PRECISION_FLOOR} unreachable at any threshold "
                  f"(stick with best-F1)")

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    # Input-arm label so ablation rows (rgb / rgb+fr / rgb+struct) coexist in the
    # report instead of silently overwriting each other. (VI unused in phase 4.)
    chan_desc = f"rgb+{config.HS_SOURCE}" if config.IN_CHANNELS >= 4 else "rgb"
    rows = []
    for s in sorted(site_cm):
        m = _metrics(*site_cm[s])
        rows.append(dict(year=label, gsd_cm=entry["gsd_cm"], tier=tier,
                         channels=chan_desc,
                         eval_scope=eval_scope, scope="site", site=s, **m))
    overall_row = dict(year=label, gsd_cm=entry["gsd_cm"], tier=tier,
                       channels=chan_desc,
                       eval_scope=eval_scope, scope="OVERALL", site="ALL", **overall)
    overall_row.update(ti)   # auroc, ap, log_loss, best_f1, best_f1_thresh (if available)
    # v039: confusion metrics at the deployed operating threshold (best_f1), as
    # *_op columns alongside the legacy 0.5 columns. Use these for DG decisions.
    overall_row["op_thresh"] = round(op_thr, 4)
    overall_row.update({f"{k}_op": overall_op[k]
                        for k in ("iou", "dice", "precision", "recall",
                                  "f1", "accuracy")})
    rows.append(overall_row)
    new = pd.DataFrame(rows)

    # Append/replace this (year, channels) arm's rows in the cumulative report.
    # Pre-channels rows were RGB-only — treat missing as "rgb" so a re-run still
    # replaces them rather than duplicating.
    if EVAL_CSV.exists():
        old = pd.read_csv(EVAL_CSV)
        if "channels" not in old.columns:
            old["channels"] = "rgb"
        old["channels"] = old["channels"].fillna("rgb")
        old = old[~((old["year"].astype(str) == label) &
                    (old["channels"] == chan_desc))]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(EVAL_CSV, index=False)
    print(f"  ✓ Eval rows written → {EVAL_CSV.name}  (channels={chan_desc})")

    if tier == "coarse":
        bf = f", best-F1 thresh={ti['best_f1_thresh']:.3f}" if ti else ""
        au = f", AUROC={ti['auroc']:.3f}" if ti else ""
        # Fix 4: coarse city-wide years now carry a blocked held-out test block,
        # so this is out-of-sample; legacy 6-site / degraded years stay in-sample.
        scope_txt = ("out-of-sample" if eval_scope == "held-out test"
                     else "in-sample")
        print(f"  ◆ DG2 note: {label} coarse-year IoU={overall['iou']:.3f} "
              f"({scope_txt}){au}{bf}.")
        if ti:
            print(f"    AUROC measures ranking independent of the 0.5 cutoff — use it "
                  f"(not in-sample IoU) to judge whether the year is usable; apply "
                  f"best-F1 thresh as the per-year operating point. Confirm with "
                  f"random-point photo-interpretation before DG2 include/exclude.")
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ══════════════════════════════════════════════════════════════════════════════
#  Step 5 — Full-city native inference → probability raster
# ══════════════════════════════════════════════════════════════════════════════

def _aoi_pixel_rects(aoi_path, img_crs, img_tf, img_h, img_w):
    """Sector AOI file → pixel rects [(r0, r1, c0, c1)] on this ortho, clamped to the
    grid; empty/degenerate rects dropped. Accepts the sectors JSON written by
    pipeline/make_sectors.py ({"crs": ..., "sectors": [{"bounds_3857": [minx,miny,maxx,maxy]}]})
    or any vector file geopandas can read (bounds per feature). Relative paths resolve
    against the repo pipeline/ dir so the same flag value works locally and on a VM clone."""
    import json
    p = Path(aoi_path)
    if not p.is_absolute():
        # The shim/queue run with cwd = Scripts/pipeline, so CWD is the primary anchor.
        # __file__ is NOT reliable on the VM: the engine stages the package to
        # /content/_phase4seg_pkg/, which has no aoi/ dir (found 2026-08-25).
        for cand in (Path.cwd() / p,
                     Path(__file__).resolve().parents[1] / p,
                     Path("/content/repo/Scripts/pipeline") / p):
            if cand.exists():
                p = cand
                break
        else:
            raise FileNotFoundError(f"--infer-aoi {aoi_path}: not found from cwd, "
                                    f"the package dir, or the VM repo")
    rects_bounds, src_crs = [], None
    if p.suffix.lower() == ".json":
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        src_crs = d.get("crs", "EPSG:3857")
        rects_bounds = [s["bounds_3857"] for s in d["sectors"]]
    else:
        import geopandas as gpd
        g = gpd.read_file(p)
        src_crs = str(g.crs)
        rects_bounds = [list(geom.bounds) for geom in g.geometry]
    out = []
    for minx, miny, maxx, maxy in rects_bounds:
        bx = rasterio.warp.transform_bounds(src_crs, img_crs, minx, miny, maxx, maxy)
        win = rasterio.windows.from_bounds(*bx, transform=img_tf)
        r0 = max(0, int(np.floor(win.row_off)))
        c0 = max(0, int(np.floor(win.col_off)))
        r1 = min(img_h, int(np.ceil(win.row_off + win.height)))
        c1 = min(img_w, int(np.ceil(win.col_off + win.width)))
        if r1 > r0 and c1 > c0:
            out.append((r0, r1, c0, c1))
    return out


def step_inference(label, batch_size=INFER_BATCH_SIZE, dry_run=False, citywide=False):
    _ensure_torch()
    entry = entry_for(label)
    print(f"\n── [{label}] Step 5: Full-city native inference ──")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    native = resolve_native_path(entry)
    if not native.exists():
        print(f"  ERROR: native ortho not found: {native}"); return
    # M06: catalog-level NIR gate BEFORE any staging/GPU spend. The authoritative
    # check is against the raster itself (below, once the ckpt's hs_source is
    # adopted); this one just fails in seconds instead of after a multi-GB copy.
    if config.nir_mode() and int(entry.get("bands", 3)) < 4:
        raise RuntimeError(
            f"--hs-source nir: year {label} is catalogued with "
            f"{entry.get('bands')} bands — no NIR to feed channel 4.")
    ckpt = MODELS_DIR / f"sem_best_{label}{_tag_sfx()}.pt"
    if not ckpt.exists():
        if dry_run:
            print(f"  (dry run: ckpt {ckpt.name} missing — geometry checks continue)")
        else:
            print(f"  ERROR: {ckpt} not found — run step train first"); return

    MASKS_DIR.mkdir(parents=True, exist_ok=True)
    prob_final = MASKS_DIR / f"edmonds_canopy_prob_{label}{_tag_sfx()}.tif"
    # verified write path (P4.1): write the multi-GB raster to local NVMe, then
    # size+sha256-verified copy to Drive — the 2017/2022/2024 failure class dies here
    prob_out = _local_artifact_path(prob_final)

    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()

    local = native if dry_run else _stage_imagery_local(native)
    with rasterio.open(local) as src:
        img_h, img_w = src.height, src.width
        img_crs, img_tf = src.crs, src.transform
        src_nodata = src.nodata
        img_bands = src.count                      # M06 NIR gate (checked below)
        px = src.transform.a; py = abs(src.transform.e)
    print(f"  Ortho: {img_w}×{img_h}px  ({img_w*px/1000:.1f}×{img_h*py/1000:.1f} km)"
          f"  GSD≈{px*100:.1f}cm  nodata={src_nodata}")
    # AOI resolution happens BEFORE the dry-run return so a dry run is a free,
    # machine-checkable smoke of the sector geometry (no GPU, no staging).
    aoi_rects = None
    if config.INFER_AOI:
        aoi_rects = _aoi_pixel_rects(config.INFER_AOI, img_crs, img_tf, img_h, img_w)
        px_aoi = sum((r1 - r0) * (c1 - c0) for r0, r1, c0, c1 in aoi_rects)
        print(f"  AOI: {len(aoi_rects)} rect(s) from {Path(config.INFER_AOI).name} "
              f"(~{100 * px_aoi / (img_h * img_w):.1f}% of the grid; rest → nodata)")
        if not aoi_rects:
            print("  ERROR: --infer-aoi has no overlap with this ortho"); return
    if dry_run:
        print("  Dry run — not running inference")
        _unstage_imagery_local(local) if local != native else None
        return

    # in_channels is recorded in the ckpt (3=RGB, 4=RGB+structure); set IN_CHANNELS
    # before build_model so the U-Net stem matches, then load (inflation is a no-op
    # when shapes already match). Pre-hillshade ckpts lack the field → default 3.
    # hs_source is likewise adopted from the ckpt (pre-v027 4ch ckpts → 'fr') so
    # the raster read per window and the stats match what the model trained on.
    ck = torch.load(ckpt, map_location=device)
    config.IN_CHANNELS = int(ck.get("in_channels", 3))
    has_hs = config.IN_CHANNELS >= 4
    if has_hs:
        _ck_src = str(ck.get("hs_source", "fr"))
        if _ck_src in HS_STATS and _ck_src != config.HS_SOURCE:
            print(f"  ckpt was trained with --hs-source {_ck_src} — adopting it.")
            config.HS_SOURCE = _ck_src
    # M06: the ckpt (not the flag) decides whether band 4 is NIR. An NIR model
    # can only be run on an ortho that HAS band 4 — refuse rather than fall back.
    nir_mode = has_hs and config.nir_mode()
    if nir_mode and img_bands < 4:
        raise RuntimeError(
            f"--hs-source nir ({ckpt.name} was trained on NIR band 4): ortho "
            f"{native.name} has {img_bands} band(s). Refusing to infer with a "
            f"substituted 4th channel.")
    model = build_model(device, compile_model=False)
    _tgt = model._orig_mod if hasattr(model, "_orig_mod") else model
    _tgt.load_state_dict(_inflate_first_conv(ck["model_state"], _tgt.state_dict()),
                         strict=False)
    model.eval()
    if device.type == "cuda":
        # every inference forward has the same shape, so cuDNN's autotuner pays for
        # itself on the first batch and is free for the remaining hundreds of thousands
        torch.backends.cudnn.benchmark = True
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()   # release memory held from train/eval in the same process
    print(f"  Model: {ckpt.name}  (val_bce={ck.get('best_val','?')})  "
          f"in_channels={config.IN_CHANNELS}"
          f"{'  +structure[' + config.HS_SOURCE + ']' if has_hs else ''}")

    tf = A.Compose([A.Normalize(IMAGENET_MEAN, IMAGENET_STD, max_pixel_value=255.0),
                    ToTensorV2()])
    stride, pad, cc = INFER_STRIDE, INFER_PAD, INFER_STRIDE

    # Only sample-restrict when the year was actually tiled from the manifest, i.e. the
    # citywide path ran. Without this, a fine year without --force-citywide would train
    # on full crops but emit a mostly-nodata prob raster (tiling ignores the manifest).
    sample_mode = bool(config.SAMPLE_MANIFEST) and citywide
    aoi_mode = bool(aoi_rects) and not sample_mode   # sample-manifest wins (cli warns)
    if sample_mode:
        # Sample-only inference: predict ONLY the manifest tiles (same fixed locations
        # the model tiled/trained on), everything else stays nodata. Turns a full-city
        # sweep into ~200 forwards so the forest-miss autopsy can run on the fast sample.
        # half=INFER_STRIDE//2 centres the written crop on the point, not a half-tile off.
        origins = _origins_from_manifest(img_crs, img_tf, img_h, img_w,
                                         half=INFER_STRIDE // 2, extent=INFER_STRIDE)
        print(f"  SAMPLE inference: {len(origins):,} manifest tiles (rest → nodata)  "
              f"|  batch={batch_size}")
    else:
        origins = [(r, c) for r in range(0, img_h, stride) for c in range(0, img_w, stride)]
        if origins[-1][0] + stride < img_h:
            origins += [(img_h - TILE_SIZE, c) for c in range(0, img_w, stride)]
        if origins[-1][1] + stride < img_w:
            origins += [(r, img_w - TILE_SIZE) for r in range(0, img_h, stride)]
        origins.append((img_h - TILE_SIZE, img_w - TILE_SIZE))
        origins = sorted(set(origins))
        if aoi_rects:
            # keep a tile iff its INFER_STRIDE write-crop intersects any sector rect —
            # the crop is what lands in the raster, so this is the exact coverage test
            origins = [(r, c) for (r, c) in origins
                       if any(r < r1 and r + cc > r0 and c < c1 and c + cc > c0
                              for (r0, r1, c0, c1) in aoi_rects)]
            print(f"  AOI-restricted tile positions: {len(origins):,}  |  batch={batch_size}")
        else:
            print(f"  Tile positions: {len(origins):,}  |  batch={batch_size}")

    # uint8 prob raster; 255 reserved as a nodata sentinel (blanks un-imaged areas
    # of partial-coverage years). Real probabilities clipped to 0–254.
    prob_profile = {"driver": "GTiff", "dtype": "uint8", "width": img_w,
                    "height": img_h, "count": 1, "crs": img_crs, "transform": img_tf,
                    "compress": "lzw", "BIGTIFF": "YES", "nodata": PROB_NODATA}

    batch_imgs, batch_meta = [], []

    def _forward(imgs):
        # OOM-resilient forward: on CUDA OOM, halve the batch and retry (freeing the
        # failed alloc first). Guards the full-city pass when an oversized inference
        # batch or leftover train/eval memory tips the GPU over.
        #
        # P11.6 throughput: sigmoid, the centre crop and the uint8 quantisation all run
        # ON THE GPU. The old path pulled (B,512,512) fp32 logits to the host and ran
        # numpy exp() over 8.4M values per 32-tile batch (~60-100 ms of single-threaded
        # CPU inside the serial loop), then cropped. Doing it on device leaves only the
        # (B,cc,cc) uint8 crop to transfer — ~5x less traffic — and frees the CPU for
        # the tile readers. Numerically identical to within 1 LSB: the same fp32
        # sigmoid, the same *254/round/clip.
        try:
            inp = torch.stack(imgs).to(device, non_blocking=True)
            with torch.no_grad(), torch.amp.autocast("cuda"):
                raw = model(inp)
                seg = raw[0] if isinstance(raw, (tuple, list)) else raw
            p = torch.sigmoid(seg.float().squeeze(1))[:, pad:pad + cc, pad:pad + cc]
            out = (p * 254.0).round().clamp_(0, 254).to(torch.uint8).cpu().numpy()
            del inp, raw, seg, p
            return out
        except RuntimeError as e:
            if "out of memory" not in str(e).lower() or len(imgs) == 1:
                raise
            torch.cuda.empty_cache()
            mid = len(imgs) // 2
            return np.concatenate([_forward(imgs[:mid]), _forward(imgs[mid:])], axis=0)

    def flush(dst):
        if not batch_imgs:
            return
        crops = _forward(batch_imgs)          # (B, cc, cc) uint8, already sigmoid+quantised
        for k, (ro, co, valid) in enumerate(batch_meta):
            cr_end = min(ro + cc, img_h); cc_end = min(co + cc, img_w)
            ch, cw = cr_end - ro, cc_end - co
            crop = np.ascontiguousarray(crops[k, :ch, :cw])   # view -> own buffer
            if valid is not None:                       # blank no-data pixels
                crop[~valid[:ch, :cw]] = PROB_NODATA
            win = rasterio.windows.Window(co, ro, cw, ch)
            dst.write(crop[np.newaxis], window=win)

    tick("inference")
    with rasterio.open(prob_out, "w", **prob_profile) as dst:
        if sample_mode or aoi_mode:
            # Pixels outside the sampled/AOI tiles must read as nodata (255), not the GTiff
            # default 0 — else the autopsy scores un-inferred forest as a miss. Fill 255
            # in row strips (memory-safe), then the sample windows overwrite it.
            _fill = np.full((TILE_SIZE, img_w), PROB_NODATA, dtype=np.uint8)
            for _r0 in range(0, img_h, TILE_SIZE):
                _rh = min(TILE_SIZE, img_h - _r0)
                dst.write(_fill[np.newaxis, :_rh],
                          window=rasterio.windows.Window(0, _r0, img_w, _rh))
        with rasterio.open(local) as src:
            # One ortho handle PER READER THREAD. A GDAL DatasetReader is not
            # thread-safe: sharing `src` across the pool raced in the block cache and
            # died with "IReadBlock failed at X offset 0, Y offset 0:
            # TIFFReadEncodedTile() failed" on the very first batch (2026-08-22). The
            # main thread keeps `src` for the geometry it already read.
            _tls = threading.local()

            def _src():
                ds = getattr(_tls, "ds", None)
                if ds is None:
                    ds = _tls.ds = rasterio.open(local)
                return ds

            def _prep(rc):
                """Read + preprocess ONE tile. Runs in reader threads: rasterio reads and
                the hillshade warp release the GIL, so this overlaps with GPU work.
                Byte-for-byte the same tile the serial loop produced."""
                ro, co = rc
                r0, c0 = ro - pad, co - pad
                r1, c1 = r0 + TILE_SIZE, c0 + TILE_SIZE
                rr0, cc0 = max(0, r0), max(0, c0)
                rr1, cc1 = min(img_h, r1), min(img_w, c1)
                win = rasterio.windows.Window(cc0, rr0, cc1 - cc0, rr1 - rr0)
                _s = _src()
                tile = read_rgb_window(_s, win).transpose(1, 2, 0)
                if has_hs and nir_mode:
                    # M06: band 4 = the SAME window of the SAME ortho the RGB came
                    # from — co-registered by construction, no warp, no second
                    # dataset. Concatenated BEFORE the reflect-pad, exactly where
                    # the hillshade chip goes, so the padded tile is identical in
                    # shape and the model sees the same channel order as training.
                    nir = _s.read([4], window=win).transpose(1, 2, 0)
                    tile = np.concatenate([tile, nir], axis=-1)
                elif has_hs:                                # co-registered hillshade band
                    win_tf = rasterio.windows.transform(win, _s.transform)
                    hs = read_hillshade_chip(_s.crs, win_tf,
                                             int(win.height), int(win.width))
                    tile = np.concatenate([tile, hs.transpose(1, 2, 0)], axis=-1)
                pt, pb = rr0 - r0, r1 - rr1
                pl, pr = cc0 - c0, c1 - cc1
                if any([pt, pb, pl, pr]):
                    tile = np.pad(tile, ((pt, pb), (pl, pr), (0, 0)), mode="reflect")

                # Validity for the center crop (skip-write for un-imaged pixels).
                # Judge coverage on RGB only — hillshade carries its own nodata.
                center_rgb = tile[pad:pad+cc, pad:pad+cc, :3]
                if src_nodata is not None:
                    valid = ~np.all(center_rgb == src_nodata, axis=-1)
                else:
                    valid = ~np.all(center_rgb == 0, axis=-1)
                if valid.all():
                    valid = None  # full-coverage tile, skip the masking work

                img = (torch.from_numpy(rgb_to_model_input(tile))
                       if (config.USE_VI or has_hs) else tf(image=tile)["image"])
                return img, (ro, co, valid)

            def _close_thread_datasets(pool):
                """Close each worker's private handles (ortho + hillshade) in its own
                thread, so no dataset outlives the pool."""
                def _shut():
                    ds = getattr(_tls, "ds", None)
                    if ds is not None:
                        ds.close(); _tls.ds = None
                    close_thread_hillshade()
                futs = [pool.submit(_shut) for _ in range(INFER_READ_WORKERS)]
                for f in futs:
                    try:
                        f.result(timeout=30)
                    except Exception:                      # noqa: BLE001
                        pass

            pbar = tqdm(total=len(origins), desc="  Inference", unit="tile",
                        miniters=2000, mininterval=2.0)
            # Bounded look-ahead: keep ~3 batches of tiles in flight so the GPU never
            # waits on a read, without materialising the whole city in RAM. Results are
            # consumed in submission order, so the write order is unchanged. Measured
            # 2026-08-22 on the 2019 ortho: 16.5 ms/tile serial (12 ms of it the per-tile
            # CHM warp) vs 3.1 ms/tile at 8 threads — the serial read path, not the GPU,
            # was the ceiling (~40 tile/s at ~20% GPU).
            inflight = deque()
            max_inflight = max(batch_size * 3, 64)
            it = iter(origins)
            with ThreadPoolExecutor(max_workers=INFER_READ_WORKERS) as pool:
                def _pump():
                    while len(inflight) < max_inflight:
                        try:
                            inflight.append(pool.submit(_prep, next(it)))
                        except StopIteration:
                            break
                _pump()
                while inflight:
                    img, meta = inflight.popleft().result()
                    _pump()
                    batch_imgs.append(img)
                    batch_meta.append(meta)
                    if len(batch_imgs) == batch_size:
                        flush(dst); batch_imgs.clear(); batch_meta.clear()
                    pbar.update(1)
                _close_thread_datasets(pool)
            pbar.close()
            flush(dst)
    tock("inference")
    if prob_out != prob_final:
        _copy_to_drive(prob_out, prob_final)      # raises loudly on size/sha mismatch
        try:
            prob_out.unlink()
        except OSError:
            pass
    print(f"  ✓ Probability raster: {prob_final.name} "
          f"({prob_final.stat().st_size/1e6:.0f} MB)")

    if local != native:
        _unstage_imagery_local(local)
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()

