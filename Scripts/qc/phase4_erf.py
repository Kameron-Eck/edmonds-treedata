r"""Measure the EFFECTIVE receptive field of the deployed model. The gate before any
global-context decision (ASPP, DeepLabV3+, image-pooling branch).

WHY THIS EXISTS. An argument was made in-session (2026-08-29, by me) that a resnet101
U-Net "already sees the whole 512 px tile" because its THEORETICAL receptive field is
1027 px. The premise is right and the conclusion does not follow. Every primary source
says the effective RF is far smaller than the theoretical one:

  * Luo et al. 2016 (NeurIPS) - ERF grows O(sqrt(n)) while TRF grows O(n). Their own
    case is literally the claim under test: "the theoretical receptive field of our
    network is actually 74 x 74, bigger than the image size, but the ERF is still not
    able to fully fill the image."
  * Ding et al. 2022 (RepLKNet) measured ResNet-101 itself: on a 1024 px input, 50% of
    the input-gradient contribution to a centre output sits inside ~3.2% of the area,
    and "adding more layers to ResNet-101 does not effectively enlarge the ERF."
  * Luo section 2.5, specific to us: "skip-connections ... make ERFs smaller." A U-Net
    decoder's skip fusion makes an encoder-only estimate optimistic.

WHAT THE ANSWER DECIDES. ParseNet gives the discriminator, in both directions: where the
tile EXCEEDS the ERF, adding a global branch is worth +2.57 mIoU on VOC2012; where the
tile already sits INSIDE the ERF (their 256 px SiftFlow case) the same branch is
"essentially a noop". So:

    ERF covers the tile      -> a context module is a noop here. Do not build it.
    ERF well short of tile   -> context is genuinely missing; ParseNet's gain is on the
                                table, and the cheap form is an image-level global
                                average pool branch, not large-rate atrous taps.

METHOD (RepLKNet's). Take the CENTRE pixel of the output map, backpropagate to the
input, accumulate |gradient| over many real tiles, and ask how much of the tile area
carries what fraction of the total contribution. Gradient magnitude at an input pixel is
how much that pixel can influence that one prediction - which is the operational meaning
of "does the model see it".

MEASURE THE TRAINED MODEL, NOT AN INITIALISED ONE. Luo measured the ERF growing from
~100 px at init to ~150 px after training on CamVid; an init-only number understates it.
Pass --ckpt.

WHAT THIS DOES NOT ESTABLISH. It measures REACH, not whether reach is the binding
constraint. Loos et al. 2024 (varying TRF at constant parameter count) found the required
receptive field tracks OBJECT SIZE IN PIXELS, not metric context - by which a 6 px crown
at 100 cm needs very little. A short ERF is necessary evidence for a context module, not
sufficient. Read this alongside the object-size framing, not instead of it.

Run:
  py -3.12 qc/phase4_erf.py --ckpt "G:/My Drive/treedata/phase3/sem_best_2020.pt"
  py -3.12 qc/phase4_erf.py --ckpt <path> --tiles <tile_dir> --n 32
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))


# config.BASE is HARDCODED to the Colab path because the engine only ever
# RUNS on Colab. This is a local QC tool, so it resolves the lake the way the other qc
# scripts do (phase4_accuracy_sample.py, nir_change_probe.py): Colab path if present,
# else the Drive letter.
_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
_LAKE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE


def _log(m):
    print(m, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", default=None,
                    help="checkpoint to measure. STRONGLY recommended — an untrained "
                         "model understates the ERF (Luo: ~100 px at init vs ~150 after).")
    ap.add_argument("--tiles", default=None,
                    help="a tile dir to draw real imagery from. Falls back to noise, "
                         "which is a WEAKER measurement — report it as such.")
    ap.add_argument("--n", type=int, default=24, help="samples to accumulate")
    ap.add_argument("--tile-size", type=int, default=None, help="default: config.TILE_SIZE")
    ap.add_argument("--device", default="cpu", help="cpu is fine; this is a few passes")
    ap.add_argument("--out-name", default="erf_report.md")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(clean_argv())

    out = Path(r"D:\edmonds-pipeline\treedata\phase4\qc") / a.out_name
    if out.exists() and not a.overwrite:
        raise SystemExit(f"refusing to overwrite {out}  (--overwrite, or --out-name)")

    from phase4seg import core, config
    core._ensure_torch()
    import torch

    S = a.tile_size or config.TILE_SIZE
    device = torch.device(a.device)

    # ── the model, as deployed ────────────────────────────────────────────────
    model = core.build_model(device, compile_model=False)
    if a.ckpt:
        core.load_state_into(model, Path(a.ckpt), device,
                             allow_missing=("height_head.",),
                             what="ERF measurement")
        trained = True
    else:
        trained = False
        _log("  ! no --ckpt: measuring an INITIALISED model. Luo et al. measured the ERF "
             "growing ~100 -> ~150 px through training, so this UNDERSTATES reach.")
    model.eval()

    # ── inputs: real tiles beat noise ─────────────────────────────────────────
    imgs, src_desc = [], ""
    if a.tiles:
        import rasterio
        tdir = Path(a.tiles)
        # Read paths from the tile INDEX, not by walking the tree: rglob over the
        # Drive mount takes minutes and times out. The index already lists them.
        idx = next(iter(sorted(tdir.glob("tile_index_*.csv"))), None)
        if idx is not None:
            import pandas as pd
            df = pd.read_csv(idx)
            # Tile indices bake COLAB-ABSOLUTE paths (/content/drive/MyDrive/...),
            # so on Windows they must be remapped onto BASE. This is the two-planes
            # rule in miniature: data resolves via BASE, never via a stored string.
            _COLAB = "/content/drive/MyDrive/treedata"
            def _local(q):
                q = str(q).replace("\\", "/")
                if q.startswith(_COLAB):
                    return _LAKE / q[len(_COLAB):].lstrip("/")
                return Path(q)
            cand = [_local(q) for q in df["img_path"].astype(str).tolist()]
        else:
            cand = sorted(tdir.rglob("*.tif"))
            cand = [q for q in cand if "images" in str(q).replace(chr(92), "/")] or cand
        for p in cand[:a.n]:
            with rasterio.open(p) as s:
                arr = s.read()[:config.IN_CHANNELS].astype(np.float32) / 255.0
            if arr.shape[-2:] != (S, S) or arr.shape[0] < config.IN_CHANNELS:
                continue
            imgs.append(arr)
        src_desc = f"{len(imgs)} real tiles from {tdir.name}"
    if not imgs:
        g = np.random.default_rng(42)
        imgs = [g.normal(0.5, 0.25, (config.IN_CHANNELS, S, S)).astype(np.float32)
                for _ in range(a.n)]
        src_desc = f"{len(imgs)} GAUSSIAN NOISE tiles (weaker than real imagery)"
    _log(f"  input: {src_desc}")

    # ── accumulate |d(centre output) / d(input)| ──────────────────────────────
    acc = np.zeros((S, S), np.float64)
    c = S // 2
    for i, arr in enumerate(imgs):
        x = torch.from_numpy(arr).unsqueeze(0).to(device).requires_grad_(True)
        out_t = model(x)
        if isinstance(out_t, (tuple, list)):
            out_t = out_t[0]
        # the centre pixel of the OUTPUT map; the decoder restores input resolution
        oc = out_t.shape[-1] // 2
        model.zero_grad(set_to_none=True)
        out_t[0, 0, oc, oc].backward()
        acc += x.grad.detach().abs().sum(0).sum(0).cpu().numpy().astype(np.float64)
        if (i + 1) % 8 == 0 or i == len(imgs) - 1:
            _log(f"    {i+1}/{len(imgs)}")

    if acc.sum() <= 0:
        raise SystemExit("all gradients are zero — the model is not differentiable "
                         "w.r.t. its input here; nothing was measured.")
    acc /= acc.sum()

    # ── how much AREA carries what fraction of the contribution ───────────────
    flat = np.sort(acc.ravel())[::-1]
    cum = np.cumsum(flat)
    rows = []
    for t in (0.20, 0.50, 0.90, 0.99):
        npix = int(np.searchsorted(cum, t) + 1)
        frac = 100.0 * npix / (S * S)
        side = float(np.sqrt(npix))                 # equivalent square side, px
        rows.append((t, npix, frac, side))

    # centred-box view: the smallest square centred on the pixel holding t of the mass
    box = []
    for t in (0.50, 0.90, 0.99):
        for half in range(1, c + 1):
            if acc[c - half:c + half + 1, c - half:c + half + 1].sum() >= t:
                box.append((t, 2 * half + 1))
                break
        else:
            box.append((t, None))                   # never reaches t inside the tile

    L = ["# Effective receptive field — the deployed model", "",
         f"Model: `{config.ENCODER}` U-Net, decoder{tuple(config.DECODER_CHANNELS)}, "
         f"in_channels={config.IN_CHANNELS}, tile {S}x{S}.",
         f"Checkpoint: `{Path(a.ckpt).name if a.ckpt else 'NONE — initialised weights'}`"
         f"{'' if trained else '  ← understates reach'}",
         f"Input: {src_desc}", "",
         "Method: |d(centre output pixel) / d(input)| accumulated and normalised "
         "(RepLKNet's measurement).", "",
         "## How much of the tile actually influences one prediction", "",
         "| share of influence | pixels | % of tile area | equivalent square side |",
         "|---|---|---|---|"]
    for t, npix, frac, side in rows:
        L.append(f"| {t*100:.0f}% | {npix:,} | **{frac:.2f}%** | {side:.0f} px |")
    L += ["", "## Centred-box view", "",
          "| share | smallest centred square holding it |", "|---|---|"]
    for t, s in box:
        L.append(f"| {t*100:.0f}% | {(str(s) + ' px') if s else '**does not fit in the tile**'} |")

    # ── the verdict, in ParseNet's terms ──────────────────────────────────────
    half_side = rows[1][3]
    covers = half_side >= 0.75 * S
    L += ["", "## Verdict", ""]
    if covers:
        L += [f"- 50% of the influence spans ~{half_side:.0f} px of a {S} px tile. The tile is "
              "effectively INSIDE the receptive field.",
              "- This is ParseNet's SiftFlow regime, where they measured a global branch as "
              "**\"essentially a noop\"**. A context module is not indicated."]
    else:
        L += [f"- 50% of the influence sits in ~{rows[1][2]:.1f}% of the tile area "
              f"(~{half_side:.0f} px square of {S}). Reach is **well short** of the tile.",
              "- This is ParseNet's VOC regime, where adding an image-level global branch "
              "was worth **+2.57 mIoU**. Global context is genuinely missing.",
              "- The cheap form is a global-average-pool branch, NOT large-rate atrous taps: "
              f"at output stride 32 the bottleneck is {S//32}x{S//32}, and DeepLabv3 states "
              "rates approaching feature-map size \"degenerate to a simple 1x1 filter\"."]

    # metric reading — the same pixel reach means very different ground distances
    L += ["", "## What that reach means on the ground", "",
          "The same ERF in pixels is a different context window in metres at each tier.", "",
          "| GSD | 50% influence within |", "|---|---|"]
    for gsd in (5.0, 10.0, 30.5, 60.0, 100.0):
        L.append(f"| {gsd:.1f} cm | {half_side * gsd / 100.0:.1f} m |")
    L += ["",
          "**Do not read this table as settling the question.** Loos et al. 2024 varied "
          "theoretical RF at constant parameter count and found the required receptive "
          "field tracks OBJECT SIZE IN PIXELS, not metric context — under which a 6 px "
          "crown at 100 cm is already well covered and the deficit would sit at the FINE "
          "end instead. This measures reach; it does not prove reach is the binding "
          "constraint.", ""]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    _log(f"\n[erf] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
