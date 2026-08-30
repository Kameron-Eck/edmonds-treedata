#!/usr/bin/env python3
"""
Local RUNTIME smoke test for the phase4seg engine. Complements phase4seg_preflight.py
(which catches static errors): this actually EXERCISES the real training code paths on
CPU with a tiny model and a handful of your real tiles, catching runtime crashes that
only surface when tensors flow — dataset __getitem__ casts, masked-loss shapes, the
train/eval loop, and the checkpoint save/load round-trip.

It validates PLUMBING, not science: a tiny random-init model on 4 tiles gives garbage
IoU — expected. Real accuracy still comes from Colab. Needs torch+smp+albumentations
installed locally (CPU is fine). Reuses tiles already on disk (default year 2000).

    py -3.12 phase4seg_smoke.py            # year 2000
    py -3.12 phase4seg_smoke.py --year 2016
Exit 0 = the pipeline runs end-to-end; safe to push a training run to Colab.
"""
import argparse
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

HERE = Path(__file__).resolve().parent          # repo Scripts/pipeline (CODE plane)
# DATA plane: code left Drive for the D: git repo 2026-08-20, so BASE can no
# longer be derived from __file__ — probe the mounts like every other script.
_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
sys.path.insert(0, str(HERE))

ap = argparse.ArgumentParser()
ap.add_argument("--year", default="2000")
ap.add_argument("--tiles", type=int, default=4, help="how many train tiles to smoke on")
args = ap.parse_args()

def step(name):
    print(f"\n>>> {name}")

def die(name, exc):
    print(f"\n[FAILED] during: {name}")
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    sys.exit(1)

# ── load the engine (torch stays lazy until _ensure_torch) ────────────────────
import phase4seg.config as config          # noqa: E402
import phase4seg.core as core              # noqa: E402

step("import torch / smp / albumentations (via the engine's own _ensure_torch)")
try:
    core._ensure_torch()
    import torch
    import torch.nn as nn
    import segmentation_models_pytorch as smp
    from torch.utils.data import DataLoader
    print(f"    torch {torch.__version__}  cuda={torch.cuda.is_available()}  (using CPU)")
except Exception as e:
    die("torch/smp/albumentations import", e)

device = torch.device("cpu")

# ── assemble a mini tile index from REAL local tiles ──────────────────────────
step(f"locate real tiles for year {args.year}")
tdir = BASE / "phase4" / "tiles" / args.year
csv = tdir / f"tile_index_{args.year}.csv"
if not csv.exists():
    print(f"[FAILED] no local tile index: {csv}\n"
          f"         (run --step tile for that year, or pick a year whose tiles synced down.)")
    sys.exit(1)
df = pd.read_csv(csv)

def local_path(row, kind):                       # rebuild path from tile layout, ignore Colab prefix
    return str(tdir / row["split"] / kind / row["tile_name"])

df["img_path"] = df.apply(lambda r: local_path(r, "images"), axis=1)
df["mask_path"] = df.apply(lambda r: local_path(r, "masks"), axis=1)
df = df[df["img_path"].map(lambda p: Path(p).exists())
        & df["mask_path"].map(lambda p: Path(p).exists())].reset_index(drop=True)
if len(df) < 3:
    print(f"[FAILED] only {len(df)} tiles present locally — need >=3.")
    sys.exit(1)
train_df = df[df["split"] == "train"].head(args.tiles).reset_index(drop=True)
val_df = df[df["split"] == "val"].head(2)
if len(val_df) == 0:
    val_df = train_df.head(2)
val_df = val_df.reset_index(drop=True)
print(f"    {len(train_df)} train + {len(val_df)} val tiles from {tdir}")

# ── match config to the tiles on disk, exactly like step_train does ───────────
step("configure IN_CHANNELS / HS_SOURCE from the tiles (mirrors step_train)")
try:
    with rasterio.open(train_df.iloc[0]["img_path"]) as s0:
        config.IN_CHANNELS = s0.count
    core._sync_hs_source_from_tile(train_df.iloc[0]["img_path"])
    config.USE_VI = False
    config.AUX_HEIGHT = False
    print(f"    IN_CHANNELS={config.IN_CHANNELS}  HS_SOURCE={config.HS_SOURCE}")
except Exception as e:
    die("config from tiles", e)

# ── the REAL architecture (build_model, not a stand-in) ──────────────────────
# The tiny-model step below deliberately builds smp.Unet("resnet18") directly,
# for speed. That makes it a good wiring test and a USELESS architecture gate:
# it never calls build_model(), so a change to the encoder, the decoder channels,
# or an inserted ASPP bottleneck is not exercised, and the smoke would PASS on a
# model that cannot be constructed at all. CLAUDE.md rule 1 mandates this script
# before a Colab round-trip precisely so an architecture error costs seconds
# rather than a queue launch, so the real constructor has to run here.
# Measured 1.2 s on CPU (build 1.1 + forward 0.1) with encoder_weights=None, so
# nothing downloads and nothing is slow.
step("build the REAL model via build_model() + one forward pass")
try:
    _real = core.build_model(device, compile_model=False)
    with torch.no_grad():
        _out = _real(torch.zeros(1, config.IN_CHANNELS, 64, 64, device=device))
    _shape = _out[0].shape if isinstance(_out, (tuple, list)) else _out.shape
    if tuple(_shape)[-2:] != (64, 64):
        raise AssertionError(f"forward returned {tuple(_shape)}, expected ...x64x64 "
                             f"- the decoder is not restoring input resolution")
    print(f"    {config.ENCODER} + decoder{tuple(config.DECODER_CHANNELS)} "
          f"in_ch={config.IN_CHANNELS} -> {tuple(_shape)}")
    del _real, _out
except Exception as e:
    die("build the REAL model", e)


# ── tiny model (real smp.Unet, tiny encoder, random init → no download) ───────
step("build a tiny model + the real loss/optimizer/scaler wiring")
try:
    def tiny():
        return smp.Unet("resnet18", encoder_weights=None,
                        in_channels=config.IN_CHANNELS, classes=1, activation=None).to(device)
    model = tiny()
    criterion = nn.BCEWithLogitsLoss(reduction="none")   # what _masked_bce expects
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    sched = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.5)
    try:
        scaler = torch.cuda.amp.GradScaler(enabled=False)      # CPU-safe no-op
    except Exception:
        scaler = torch.amp.GradScaler("cuda", enabled=False)
    print("    tiny resnet18 U-Net, BCEWithLogitsLoss(reduction=none), AdamW, disabled scaler")
except Exception as e:
    die("model/loss/opt wiring", e)

# ── the real dataset + a CPU-safe loader (num_workers=0) ──────────────────────
step("real SemanticDataset -> DataLoader (train + val)")
try:
    train_loader = DataLoader(core.SemanticDataset(train_df, True),
                              batch_size=2, num_workers=0, shuffle=True,
                              drop_last=len(train_df) >= 2)
    val_loader = DataLoader(core.SemanticDataset(val_df, False),
                            batch_size=2, num_workers=0, shuffle=False)
except Exception as e:
    die("dataset/loader", e)

# ── 1) real training epoch (dataset __getitem__ + aug + masked loss + step) ───
step("_train_one_epoch (the real training loop, 1 epoch)")
try:
    tr_loss, seg = core._train_one_epoch(model, train_loader, optimizer, scaler,
                                          criterion, device, loss_mode="bce_dice")
    print(f"    train loss={tr_loss:.4f}  seg={seg:.4f}")
    if not np.isfinite(tr_loss):
        raise ValueError("non-finite training loss")
except Exception as e:
    die("_train_one_epoch", e)

# ── 2) real validation (pooled IoU sweep) ─────────────────────────────────────
step("_validate (pooled global IoU over the threshold grid)")
try:
    v_loss, iou05, iou_bt, bt = core._validate(model, val_loader, criterion, device)
    print(f"    val loss={v_loss:.4f}  IoU@0.5={iou05:.3f}  best IoU={iou_bt:.3f}@{bt} "
          f"(garbage is EXPECTED — tiny model, plumbing test only)")
except Exception as e:
    die("_validate", e)

# ── 3) real checkpoint save + load round-trip ─────────────────────────────────
step("_save_ckpt -> load_state_into (checkpoint round-trip)")
try:
    ckpt = Path(tempfile.gettempdir()) / "phase4seg_smoke_ckpt.pt"
    core._save_ckpt("A", 1, model, optimizer, sched, {"train_loss": [tr_loss]}, 0.5, str(ckpt))
    reloaded = tiny()
    ck = core.load_state_into(reloaded, str(ckpt), device)
    print(f"    saved+reloaded ok  (ckpt keys: {sorted(ck.keys())})")
    ckpt.unlink(missing_ok=True)
except Exception as e:
    die("_save_ckpt/load_state_into", e)

print("\n[PASSED] runtime smoke clean — dataset, loss, train, validate, and checkpoint")
print("         all run end-to-end. Safe to push a real training run to Colab.")
print("         (Reminder: this proves the CODE runs, NOT that it predicts canopy.)")
