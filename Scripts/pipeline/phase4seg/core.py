from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (
    _ensure_deps, _tag_sfx, entry_for, resolve_native_path,
    _stage_imagery_local, _unstage_imagery_local, read_rgb_window,
    read_hillshade_chip, close_thread_hillshade, tick, tock,
    _copy_to_drive, _local_artifact_path, tile_dir_for,
)
from phase4seg.tiling import _origins_from_manifest

import datetime as _dt
import gc
import os
import threading
import time
import numpy as np
import pandas as pd
import rasterio
import rasterio.windows
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tqdm import tqdm


# ── Lazy torch imports (same as phase3) ───────────────────────────────────────

_torch_loaded = False


def _ensure_torch():
    global _torch_loaded
    if _torch_loaded:
        return
    _ensure_deps([
        ("segmentation_models_pytorch", "segmentation-models-pytorch>=0.4,<0.6"),
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
            meta = {"tile_name": row["tile_name"], "site": row["site"]}
            if self.training and config.BOUNDARY_WEIGHT:
                sdm, w = sdm_for_mask(mask.squeeze(0).numpy(),
                                      config.BOUNDARY_IGNORE_BUFFER)
                meta["sdm"] = torch.from_numpy(sdm).unsqueeze(0)
                meta["sdm_w"] = torch.from_numpy(w).unsqueeze(0)
            return img, mask, _height_to_target(height_dn), meta

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
        # The boundary term's distance field, computed HERE — in the DataLoader worker,
        # on the AUGMENTED mask, which is the only mask the loss ever sees.
        #
        # IT CANNOT BE PRECOMPUTED PER TILE, and the plan said it could. The spatial
        # augmentation is Rotate(45) + Affine(scale) + GridDistortion + ElasticTransform
        # at p = .5/.5/.4/.3, so 89.5% of training tiles get a NON-ISOMETRIC warp. A
        # distance field computed before that describes a different shape than the mask
        # the logits are scored against — a silent correctness bug wearing an
        # optimisation's clothes. Caching would have been wrong 9 tiles in 10.
        #
        # What this DOES buy: the ~23 ms/tile moves off the training step's critical
        # path into workers that run in parallel and overlap with GPU compute, and the
        # GPU->CPU->GPU round trip per batch disappears. Total CPU work is unchanged.
        # That is the honest claim; "pure waste, recomputed every epoch" was not.
        #
        # Carried in `meta` rather than as new tuple elements on purpose. The batch is
        # already unpacked two ways (AUX_HEIGHT on/off) at two sites; a third and fourth
        # shape is how a positional mix-up gets in, and a dict lookup cannot mix up.
        if self.training and config.BOUNDARY_WEIGHT:
            sdm, w = sdm_for_mask(mask.squeeze(0).numpy(),
                                  config.BOUNDARY_IGNORE_BUFFER)
            meta["sdm"] = torch.from_numpy(sdm).unsqueeze(0)
            meta["sdm_w"] = torch.from_numpy(w).unsqueeze(0)
        return img, mask, meta






# ── losses live in phase4seg/losses.py since 2026-08-31 (plan item 3.5) ──────
# Re-exported here because ~9 call sites and several tests reach them as core.X, and a
# facade keeps the move invisible to every one of them. See losses.py for why torch is
# imported inside those functions rather than bound into module globals.
from phase4seg.losses import (             # noqa: E402,F401
    _compute_pos_weight, _masked_bce, _masked_boundary, _masked_dice, _masked_focal,
    _masked_l1, _seg_loss, _signed_distance_map, sdm_for_mask,
)
# ── splits + staging live in phase4seg/splits.py / staging.py since 2026-09-01 ──
# Same facade contract as losses above: tests and call sites reach them as core.X.
from phase4seg.splits import (             # noqa: E402,F401
    _choose_val_split, _index_split_mode, _split_mode_label,
    make_blocked_val_split, make_spatial_buffer_splits,
)
from phase4seg.staging import (            # noqa: E402,F401
    _bulk_stage_ok, _bulk_stage_tiles, _stage_tiles_local,
)
from sklearn.model_selection import train_test_split  # noqa: E402,F401 — facade: test_val_split's reference split reaches it as core.train_test_split
# ── model/ckpt IO and checkpoint selection live in phase4seg/ckpt.py / select.py
# since 2026-09-01. Same facade contract as losses above.
from phase4seg.ckpt import (               # noqa: E402,F401
    ARCHS, _assert_state_fits, _build_unet_with_height, _inflate_first_conv, _inject_dropout,
    _model_state_of, _save_ckpt, _save_ckpt_state, build_model, load_state_into,
    resolve_p3_ckpt,
)
from phase4seg.select import (             # noqa: E402,F401
    _SmoothCkptSelector, _centred_moving_average, _deploy_smoothed_keeping_raw,
    _finish_selection, _phase_smoothed, _record_manifest_training, _state_mb,
    _stop_reason,
)



def _train_one_epoch(model, loader, optimizer, scaler, criterion, device,
                     loss_mode="bce_dice", freeze_bn=False, boundary_w=0.0):
    model.train()
    if freeze_bn:
        _set_encoder_bn_eval(model)   # re-pin frozen-encoder BN after train()
    loss_sum = seg_sum = 0.0       # seg_sum tracks the combined seg loss (no L1)
    n = 0
    for batch in loader:
        if config.AUX_HEIGHT:
            imgs, masks, heights, meta = batch
            heights = heights.to(device, non_blocking=True)
        else:
            imgs, masks, meta = batch
            heights = None
        imgs = imgs.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)
        # Present only when the boundary term is on (see SemanticDataset.__getitem__).
        sdm = None
        if boundary_w and isinstance(meta, dict) and "sdm" in meta:
            sdm = (meta["sdm"].to(device, non_blocking=True),
                   meta["sdm_w"].to(device, non_blocking=True))
        optimizer.zero_grad()
        with torch.amp.autocast("cuda"):
            out = model(imgs)
            logits, height_pred = (out if isinstance(out, (tuple, list)) else (out, None))
            seg, _p, _dice = _seg_loss(criterion, logits, masks, loss_mode,
                                       boundary_w, sdm=sdm)
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

    # Train/val split for early stopping. The selection chain itself moved to
    # _choose_val_split (2026-08-29) so a test can run it against a verbatim copy
    # of the historical code and prove the default path is unchanged, row order
    # included; see that function for what each branch does and why it leaked.
    ftr = fva = None

    # Fix 4: if a geographically-blocked val split was carved at tiling time
    # (coarse city-wide), use it directly — it is already >520 m from train, so
    # no random/neighbour val tiles are needed. Replaces the leaked random-15%
    # fallback for that path.
    val_df = idx_df[idx_df["split"] == "val"].reset_index(drop=True)
    use_blocked_val = len(val_df) > 0     # citywide-coarse path (bin-balanced pool)
    # T3: `use_blocked_val` is the RECIPE boolean — it selects the sampler,
    # the pos_weight decision and the early-stop metric further down, and is
    # deliberately left keyed on "does the index carry a val split", unchanged.
    # It is NOT evidence that the split was blocked: the degraded random
    # fallback in tiling._block_partition also writes val rows (and writes the
    # `block` column before it bails), so the two indexes were
    # byte-indistinguishable and this line printed "BLOCKED" for both. What the
    # split actually was is now READ from the index instead of inferred.
    split_mode = _index_split_mode(idx_df)
    if use_blocked_val:
        ftr = train_df.reset_index(drop=True)
        fva = val_df.reset_index(drop=True)
        print(f"  Val split: {_split_mode_label(split_mode)} hold-out from tile "
              f"index ({len(fva)} tiles)")
    else:
        ftr, fva, split_mode, _notes = _choose_val_split(
            train_df, tier, gsd_m=entry["gsd_cm"] / 100.0)
        for _n in _notes:
            print(_n)

    print(f"  Train split: {len(ftr)}  |  Val split: {len(fva)}  "
          f"[{split_mode or 'unrecorded'}]")
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
    # The ONE legitimate gap in the pipeline: the Phase-3 2020 base predates the
    # aux height head, so a --aux-height model has keys it cannot supply. Named
    # here rather than waved through globally, so any OTHER gap still stops the run.
    ck = load_state_into(model, p3, device,
                         allow_missing=("height_head.",),
                         what="Phase-3 2020 base -> this fine-tune model")
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
    if config.LATEST_CKPT_LOCAL and str(MODELS_DIR).startswith("/content/drive"):
        # sem_latest re-uploaded ~1.1 GB per epoch through the verified-write
        # path; it has ZERO production readers (checked 2026-09-02: only frozen
        # phase3 and one test fixture name the pattern), and the queue's resume
        # policy re-trains on any unverified checkpoint anyway. Keep it LOCAL:
        # crash-resume within the VM still works, Drive stops paying per epoch.
        # sem_best uploads unchanged (verified) — that one is the deliverable.
        _lc = Path("/content/_ckpt_local")
        _lc.mkdir(parents=True, exist_ok=True)
        latest_ckpt = _lc / latest_ckpt.name
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
                                     device, loss_mode,
                                     freeze_bn=config.FREEZE_ENCODER_BN,
                                     # Phase A maps 2020-learned features onto a new
                                     # resolution with the encoder frozen. Edges are
                                     # Phase B's job (Kam, 2026-08-30), so the boundary
                                     # term is explicitly OFF here, not merely unset.
                                     boundary_w=0.0)
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
            _save_ckpt("A", ep + 1, model, opt, sched, history, best_val, best_ckpt)
        else:
            es += 1
        if sel is not None:
            sel.observe("A", ep + 1, es_val, model)
        if (ep + 1) % SAVE_EVERY == 0 or ep == config.EPOCHS_PHASE_A - 1:
            _save_ckpt("A", ep + 1, model, opt, sched, history, best_val, latest_ckpt)
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
                                stop_a, stop_b, ran_b, val_split=split_mode)
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
        load_state_into(model, best_ckpt, device, what="own Phase-A best -> Phase B")
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
                                     device, loss_mode,
                                     boundary_w=config.BOUNDARY_WEIGHT)
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
            _save_ckpt("B", ep + 1, model, opt, sched, history, best_val, best_ckpt)
        else:
            es += 1
        if sel is not None:
            sel.observe("B", ep + 1, es_val, model)
        if (ep + 1) % SAVE_EVERY == 0 or ep == config.EPOCHS_PHASE_B - 1:
            _save_ckpt("B", ep + 1, model, opt, sched, history, best_val, latest_ckpt)
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
    # P4.2 parity (2026-09-02): step_train has staged tiles to NVMe since P4.2;
    # evaluate kept reading FUSE — measured on t1gpuA as 3->18 s/batch jitter
    # (Drive latency), the eval pass dominating small-arm wall time. Same bytes,
    # same numerics; only the read path changes.
    idx_df = _stage_tiles_local(idx_df, label)
    eval_df = idx_df[idx_df["split"] == "test"].reset_index(drop=True)
    eval_scope = "held-out test"
    # v039: honesty caveat. Only the coarse-citywide path carves a spatially
    # BLOCKED split (val rows present in the index, >520 m from train). Medium/fine
    # with stride < TILE_SIZE use a RANDOM tile-level test split on 50%-overlapping
    # tiles, so train and "test" tiles overlap → optimistic, leaked metrics. Flag
    # it so these numbers aren't trusted as true held-out until spatial blocking is
    # applied to those tiers.
    # T3: prefer the RECORDED mode. `(split == "val").any()` is also true of the
    # degraded random fallback, so it could certify a leaked split as blocked.
    # An index written before the column existed keeps the historical inference
    # exactly, so no existing eval row changes value.
    _mode = _index_split_mode(idx_df)
    has_blocked_split = (_mode in HONEST_SPLIT_MODES if _mode
                         else bool((idx_df["split"] == "val").any()))
    if _mode:
        print(f"  Tile-index split mode: {_split_mode_label(_mode)}")
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
    ck = load_state_into(model, ckpt, device, what="deployed checkpoint -> evaluate/inference")
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

    # ── Run identity on every row (D6, 2026-08-29) ────────────────────────────
    # semantic_eval_report.csv is CUMULATIVE and SHARED: every year, every arm,
    # every campaign appends into one file, and until now a row could not say
    # which run produced it. That is why the queue's VERIFY:evaluate matched on
    # `year` alone and passed on any historical row from any arm — a job could
    # "verify" its evaluate step against a number measured weeks earlier by a
    # different model. These three columns are what make that check possible.
    #
    # DELIBERATELY ADDITIVE. The replace key below stays (year, channels) and is
    # NOT extended with run_tag. Letting tags coexist would put several OVERALL
    # rows in one arm, and postproc._operating_threshold takes the LAST row of the
    # matched arm as the deployed mask's threshold — so that change would silently
    # move which threshold real masks are cut at. That is a science decision for
    # the lane that owns thresholds, not a side effect of a provenance fix.
    new["run_tag"] = config.RUN_TAG
    new["run_id"] = config.RUN_ID
    new["written_utc"] = (_dt.datetime.now(_dt.timezone.utc)
                          .strftime("%Y-%m-%dT%H:%M:%SZ"))

    # Append/replace this (year, channels) arm's rows in the cumulative report.
    # Pre-channels rows were RGB-only — treat missing as "rgb" so a re-run still
    # replaces them rather than duplicating.
    if EVAL_CSV.exists():
        old = pd.read_csv(EVAL_CSV)
        if "channels" not in old.columns:
            old["channels"] = "rgb"
        old["channels"] = old["channels"].fillna("rgb")
        _drop = ((old["year"].astype(str) == label) &
                 (old["channels"] == chan_desc))
        # KEEPING THE KEY AT (year, channels) IS DELIBERATE (see above) — but
        # "not the deployed row" is not the same as "delete it". Two arms on one
        # year and channel set is the normal shape of a paired experiment, and the
        # second arm was silently erasing the first arm's measured rows from the
        # only cumulative record of them. Worse now that VERIFY:evaluate is
        # tag-keyed: the erased arm would re-verify as MISSING having once passed.
        # Supersede instead of destroy — the deployed-threshold lookup is unchanged
        # because the archive is a different file that nothing reads for thresholds.
        if _drop.any():
            _sup = EVAL_CSV.with_name("semantic_eval_report_superseded.csv")
            _arch = old[_drop].copy()
            _arch["superseded_utc"] = new["written_utc"].iloc[0]
            _arch["superseded_by_tag"] = config.RUN_TAG or "(untagged)"
            _sup_local = _local_artifact_path(_sup)
            if _sup.exists():
                _arch = pd.concat([pd.read_csv(_sup), _arch], ignore_index=True)
            _arch.to_csv(_sup_local, index=False)
            if _sup_local != _sup:
                _copy_to_drive(_sup_local, _sup)
                try:
                    _sup_local.unlink()
                except OSError:
                    pass
            print(f"  ({len(old[_drop])} superseded row(s) for {label}/{chan_desc} "
                  f"archived to {_sup.name} before replacement)")
        old = old[~_drop]
        new = pd.concat([old, new], ignore_index=True)
    # Local-then-verified-copy, not a bare to_csv onto the FUSE mount. This one
    # file carries EVERY year's metrics history, and it is rewritten whole on every
    # evaluate step — a torn write here loses the lot. Same publish path as every
    # other artifact (absent-destination replace + whatever verification the host
    # can actually do).
    _eval_local = _local_artifact_path(EVAL_CSV)
    new.to_csv(_eval_local, index=False)
    if _eval_local != EVAL_CSV:
        _copy_to_drive(_eval_local, EVAL_CSV)
        try:
            _eval_local.unlink()
        except OSError:
            pass
    print(f"  ✓ Eval rows written → {EVAL_CSV.name}  (channels={chan_desc}, "
          f"run_tag={config.RUN_TAG or '(none)'})")

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
    pipeline/builders/make_sectors.py ({"crs": ..., "sectors": [{"bounds_3857": [minx,miny,maxx,maxy]}]})
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
    # THE DELIVERABLE-PRODUCING STEP, and it was the one load path still doing its
    # own strict=False and discarding the result — so a checkpoint that did not fit
    # this model produced a full citywide canopy raster with no error raised. Same
    # guard as every other path now.
    _res = _tgt.load_state_dict(
        _inflate_first_conv(ck["model_state"], _tgt.state_dict()), strict=False)
    _assert_state_fits(_res, ckpt, allow_missing=("height_head.",),
                       what="deployed checkpoint -> citywide inference")
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
    model = None  # free the ref (GPU mem) WITHOUT unbinding: _forward closes over
                  # this name, and `del` of a cell var makes any later call a NameError
    if device.type == "cuda":
        torch.cuda.empty_cache()

