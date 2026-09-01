"""bench.py — the deterministic micro-benchmark: does my change move the numbers?

The smoke proves the code RUNS; the canary proved (once, expensively) that a change
left the numbers alone. This is the desk-sized middle rung: synthetic-but-structured
tiles generated fresh each run from a pinned seed, pushed through the REAL engine
path — SemanticDataset (aug, masked losses' IGNORE handling), _train_one_epoch,
_validate — and compared against a stored reference. Any edit that shifts engine
numerics fails here in ~a minute, before an A100 sees it.

HERMETIC by design: no lake, no mirror, no fixture files — the tile GENERATOR is the
fixture (same seed → same tiles, byte-for-byte). Model is smp.Unet resnet18 (random
init, no download): the bench regresses ENGINE math, not the shipping architecture —
build_model has its own registry contract in test_arch_arm.

    py -3.12 qc/bench.py             compare against qc/bench_reference.json
    py -3.12 qc/bench.py --update    re-baseline (ONLY after verifying the shift is
                                     intended or environmental — the file records the
                                     torch/numpy versions it was made with)

Tolerance: rtol 1e-4. Same machine + same env is bit-stable; a torch/numpy upgrade
may shift the numbers legitimately — the failure message says how to tell.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
REF = Path(__file__).resolve().parent / "bench_reference.json"
SEED = 1337
N_TILES, TILE = 8, 512


def make_tiles(root):
    """Structured synthetic tiles in the production format: smooth blob canopy, RGB
    correlated with the mask, a 16 px IGNORE ring so the masked losses' 255-handling
    is actually exercised (a bench that never feeds IGNORE would pass a loss that
    silently trains on it)."""
    import pandas as pd
    import rasterio
    from rasterio.transform import from_origin
    rng = np.random.default_rng(SEED)
    (root / "images").mkdir(parents=True)
    (root / "masks").mkdir(parents=True)
    rows = []
    for i in range(N_TILES):
        field = rng.normal(size=(TILE // 8, TILE // 8)).repeat(8, 0).repeat(8, 1)
        for _ in range(3):  # cheap smoothing -> blobs at crown-ish scale
            field = (field + np.roll(field, 1, 0) + np.roll(field, -1, 0)
                     + np.roll(field, 1, 1) + np.roll(field, -1, 1)) / 5.0
        mask = (field > 0.25).astype(np.uint8)
        canopy = mask.astype(bool)
        rgb = np.empty((3, TILE, TILE), dtype=np.uint8)
        base = rng.integers(90, 150, size=3)
        for b in range(3):
            layer = np.full((TILE, TILE), base[b], dtype=np.float32)
            layer[canopy] *= (0.55 if b != 1 else 0.85)   # canopy darker, green-ish
            layer += rng.normal(0, 12, size=(TILE, TILE))
            rgb[b] = np.clip(layer, 0, 255).astype(np.uint8)
        m = mask.copy()
        m[:16, :] = m[-16:, :] = m[:, :16] = m[:, -16:] = 255   # IGNORE ring
        tf = from_origin(500000 + i * TILE, 5290000, 0.6, 0.6)
        prof = dict(driver="GTiff", width=TILE, height=TILE, crs="EPSG:26910",
                    transform=tf, compress="lzw")
        ip, mp = root / "images" / f"bench_{i:02d}.tif", root / "masks" / f"bench_{i:02d}.tif"
        with rasterio.open(ip, "w", count=3, dtype="uint8", **prof) as d:
            d.write(rgb)
        with rasterio.open(mp, "w", count=1, dtype="uint8", **prof) as d:
            d.write(m, 1)
        rows.append(dict(tile_name=ip.name, site="bench", split="train" if i < 6 else "val",
                         img_path=str(ip), mask_path=str(mp),
                         canopy_frac=float(mask[mask != 255].mean())))
    return pd.DataFrame(rows)


def run():
    from phase4seg import config, core
    core._ensure_torch()
    import torch
    import segmentation_models_pytorch as smp
    from torch.utils.data import DataLoader

    # _seed_everything covers python/numpy/torch RNGs but deliberately accepts
    # thread-level nondeterminism (its docstring: "bounded variation"). A REGRESSION
    # bench needs bitwise stability, so pin the two engine-external sources: CPU
    # intra-op thread count (parallel reduction order) and algorithm choice.
    torch.set_num_threads(1)
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass
    sa, sx, sv = config.AUX_HEIGHT, config.IN_CHANNELS, config.USE_VI
    config.AUX_HEIGHT, config.IN_CHANNELS, config.USE_VI = False, 3, False
    try:
        with tempfile.TemporaryDirectory() as td:
            df = make_tiles(Path(td))
            core._seed_everything(SEED)
            device = torch.device("cpu")
            model = smp.Unet("resnet18", encoder_weights=None, in_channels=3,
                             classes=1, activation=None).to(device)
            criterion = torch.nn.BCEWithLogitsLoss(reduction="none")
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
            try:
                scaler = torch.cuda.amp.GradScaler(enabled=False)
            except Exception:
                scaler = torch.amp.GradScaler("cuda", enabled=False)
            ds_tr = core.SemanticDataset(df[df["split"] == "train"], True)
            # albumentations 2.x seeds each Compose from OS entropy and IGNORES the
            # global python/numpy seeds (measured: two applications after identical
            # reseeding differ). Training accepts that ("bounded variation",
            # _seed_everything docstring); a regression bench cannot. Pin the
            # dataset's own transforms — engine untouched, aug path still exercised.
            for _tf in (getattr(ds_tr, "spatial_tf", None), getattr(ds_tr, "pixel_tf", None)):
                if _tf is not None and hasattr(_tf, "set_random_seed"):
                    _tf.set_random_seed(SEED)
            tr = DataLoader(ds_tr,
                            batch_size=2, num_workers=0, shuffle=True,
                            generator=core._loader_generator(),
                            worker_init_fn=core._worker_init, drop_last=True)
            va = DataLoader(core.SemanticDataset(df[df["split"] == "val"], False),
                            batch_size=2, num_workers=0, shuffle=False)
            out = {}
            for ep in (1, 2):
                loss, seg = core._train_one_epoch(model, tr, optimizer, scaler,
                                                  criterion, device, loss_mode="bce_dice")
                out[f"e{ep}_loss"], out[f"e{ep}_seg"] = round(loss, 6), round(seg, 6)
            bloss, bseg = core._train_one_epoch(model, tr, optimizer, scaler,
                                               criterion, device, loss_mode="bce_dice",
                                               boundary_w=0.1)
            out["boundary_loss"] = round(bloss, 6)
            v = core._validate(model, va, criterion, device)
            out["val_loss"] = round(float(v[0] if isinstance(v, (tuple, list)) else v), 6)

            # evaluate/postproc NUMERIC kernels (2026-09-01): the last unguarded
            # numeric path was canary-only. Same pinned rng; REAL functions, not
            # replicas (threshold_and_clean was extracted from step_postproc for
            # exactly this).
            rng2 = np.random.default_rng(SEED + 1)
            gt = (rng2.random((4, 256, 256)) < 0.3)
            probf = np.clip(gt * 0.55 + rng2.random(gt.shape) * 0.45, 0, 1)
            pred = probf >= 0.5
            m = core._metrics(int((pred & gt).sum()), int((pred & ~gt).sum()),
                              int((~pred & gt).sum()), int((~pred & ~gt).sum()))
            out["eval_f1"], out["eval_iou"] = m["f1"], m["iou"]
            ti = core._threshold_independent_metrics(
                [probf.ravel().astype(np.float32)], [gt.ravel()], m["f1"])
            for k in ("auroc", "ap", "best_f1"):
                if k in ti:
                    out[f"eval_{k}"] = round(float(ti[k]), 6)
            from phase4seg import postproc as PP
            prob_u8 = np.clip(probf[0] * 254, 0, 254).astype(np.uint8)
            prob_u8[:8, :] = 255                      # a nodata band
            kernel = np.ones((config.MORPH_KERNEL_SIZE,) * 2, dtype=bool)
            pm = PP.threshold_and_clean(prob_u8, int(round(0.5 * 254)), kernel)
            out["postproc_canopy_px"] = int((pm == 1).sum())
            out["postproc_nodata_px"] = int((pm == 255).sum())
            return out
    finally:
        config.AUX_HEIGHT, config.IN_CHANNELS, config.USE_VI = sa, sx, sv


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true",
                    help="write qc/bench_reference.json from this run")
    a = ap.parse_args()
    import platform
    got = run()
    print("bench metrics:", json.dumps(got, indent=1))
    if a.update or not REF.exists():
        import numpy, torch
        REF.write_text(json.dumps({
            "metrics": got, "seed": SEED, "n_tiles": N_TILES,
            "torch": torch.__version__, "numpy": numpy.__version__,
            "python": platform.python_version()}, indent=1) + "\n", encoding="utf-8")
        print(f"reference {'updated' if a.update else 'CREATED'}: {REF}")
        return
    ref = json.loads(REF.read_text(encoding="utf-8"))
    bad = []
    for k, want in ref["metrics"].items():
        have = got.get(k)
        if have is None or not np.isclose(have, want, rtol=1e-4, atol=1e-6):
            bad.append(f"  {k}: reference {want} vs now {have}")
    if bad:
        import torch
        env = f"(ref torch {ref.get('torch')} / now {torch.__version__})"
        sys.exit("BENCH DIVERGED — engine numerics moved:\n" + "\n".join(bad) +
                 f"\nIf the change is INTENDED or the environment changed {env}, "
                 f"re-baseline with: py -3.12 qc/bench.py --update")
    print("BENCH MATCH — engine numerics unchanged vs reference "
          f"(torch {ref.get('torch')}).")


if __name__ == "__main__":
    main()
