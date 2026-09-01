"""ckpt.py — model construction, checkpoint fit/load/save.

Split out of core.py 2026-09-01 (plan item 1 / 3.5 continuation — the losses.py
precedent). core.py re-exports every name here with a facade import, so call sites
and test monkeypatches that reach them as core.X keep working unchanged.

Torch/smp are imported FUNCTION-LOCALLY in the five functions that need them
(the losses.py pattern, approved in 3.5): each such function first calls
core._ensure_torch() via a lazy import, so the deps bootstrap still fires and
no caller inherits an ordering obligation. sys.modules makes the per-call
import cost a dict hit.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path


from phase4seg import config
from phase4seg.config import (
    DECODER_CHANNELS, DECODER_DROPOUT, ENCODER, P3_CKPT_CANDIDATES,
)
from phase4seg.common import _copy_to_drive, _local_artifact_path

def _inject_dropout(module, p):
    from phase4seg.core import _ensure_torch  # lazy: no module-level cycle
    _ensure_torch()                            # deps bootstrap still fires here
    import torch.nn as nn
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
    from phase4seg.core import _ensure_torch  # lazy: no module-level cycle
    _ensure_torch()                            # deps bootstrap still fires here
    import torch.nn as nn
    import segmentation_models_pytorch as smp
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


def _build_unet():
    """Registry builder: the shipping arm. AUX_HEIGHT resolves here because only the
    U-Net subclass preserves the encoder.*/decoder.*/segmentation_head.* key layout
    that P3/P0 warm starts depend on."""
    import segmentation_models_pytorch as smp
    return _build_unet_with_height() if config.AUX_HEIGHT else smp.Unet(
        encoder_name=ENCODER, encoder_weights=None,
        decoder_channels=DECODER_CHANNELS, in_channels=config.IN_CHANNELS,
        classes=1, activation=None)


def _build_deeplabv3plus():
    """Registry builder: the TABLED alternative arm (Kam, 2026-08-31) — inert unless a
    run sets ARCH. Kept registered because it proves the seam works and its measured
    trade-off (2.44x faster, stride-4 decoder vs a crown-perimeter failure mode) is
    recorded in config.py's ARCH block."""
    import segmentation_models_pytorch as smp
    return smp.DeepLabV3Plus(
        encoder_name=ENCODER, encoder_weights=None,
        encoder_output_stride=config.DEEPLAB_OUTPUT_STRIDE,
        decoder_channels=config.DEEPLAB_DECODER_CH,
        in_channels=config.IN_CHANNELS, classes=1, activation=None)


# ══════════════════════════════════════════════════════════════════════════════
#  THE ARCHITECTURE REGISTRY — the seam for trying a different architecture.
#
#  To add one:
#    1. Write a builder above: no args; reads config at CALL time (IN_CHANNELS etc.);
#       returns an UN-compiled, UN-moved torch.nn.Module whose forward maps
#       (B, IN_CHANNELS, H, W) -> (B, 1, H, W) at input resolution — that is the
#       step contract; inference/postproc/eval need to know nothing else about it.
#       Import torch/smp INSIDE the builder (lazy-torch rule; see module docstring).
#    2. Register it here with its capability flags.
#    3. Run `py -3.12 qc/check.py` — qc/test_arch_arm.py parametrizes over THIS dict,
#       so the new arm is automatically built, forwarded, key-diffed against every
#       other arm, cross-load-refused, and checked for tile-cache invariance.
#    4. Any new config constants are APPENDED to config.py (its rule) and must NOT
#       enter _tile_signature — architecture must never invalidate the tile cache
#       (test_arch_does_not_invalidate_the_tile_cache pins this).
#
#  aux_height: whether the arm supports the training-only height head. Refused, not
#  silently dropped, when unsupported (build_model).
# ══════════════════════════════════════════════════════════════════════════════
ARCHS = {
    "unet":          {"build": _build_unet,          "aux_height": True},
    "deeplabv3plus": {"build": _build_deeplabv3plus, "aux_height": False},
}


def build_model(device, compile_model=True):
    """The segmentation model for this arm. U-Net by default; DeepLabV3+ as an ARM.

    ARCHITECTURE IS AN ARM, NOT A MIGRATION (Kam, 2026-08-31). The recorded decision
    "keep the U-Net and resnet101; change the loss, not the backbone" stands; this exists
    so the alternative can be PLUMBED and tested on a pilot pair, which is a different
    question from which one ships.

    THE DANGER THIS FUNCTION CREATES, and why config.ARCH is stamped everywhere: smp 0.5.0
    gives U-Net and DeepLabV3+ the SAME `encoder.*` prefix. Loading one's checkpoint into
    the other therefore matches every encoder key and misses only the decoder — a partial
    load, not an error. Without the stamp, an arm comparison could silently be a U-Net
    encoder wearing a DeepLabV3+ decoder at initialisation. _assert_state_fits catches the
    key mismatch, but only because the caller has to declare what it expects; the stamp is
    what lets a READER catch it afterwards.

    AUX_HEIGHT stays U-Net-only: _build_unet_with_height subclasses smp.Unet to keep the
    encoder.*/decoder.*/segmentation_head.* key layout that P3/P0 warm starts depend on.
    Asking for both is refused rather than silently resolved.
    """
    from phase4seg.core import _ensure_torch  # lazy: no module-level cycle
    _ensure_torch()                            # deps bootstrap still fires here
    import torch
    arch = str(getattr(config, "ARCH", "unet")).lower()
    spec = ARCHS.get(arch)
    if spec is None:
        raise SystemExit(f"unknown ARCH {arch!r} — registered: {sorted(ARCHS)} "
                         f"(add one via the ARCHS registry above; the contract test in "
                         f"qc/test_arch_arm.py picks it up automatically)")
    if config.AUX_HEIGHT and not spec["aux_height"]:
        raise SystemExit(
            f"--aux-height is U-Net only, but ARCH={arch}. The height head subclasses "
            f"smp.Unet to preserve the checkpoint key layout that warm starts need. "
            f"Pick one.")
    model = spec["build"]()
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


def _assert_state_fits(res, ckpt_path, allow_missing=(), what=""):
    """Refuse a load_state_dict result that does not fit. Shared, because
    step_inference does its own raw load_state_dict and bypassed the guarded
    loader entirely — and that is the step that writes the deliverable rasters,
    so it was the WORST one to leave silent. Measured on smp 0.5.0: a resnet101
    checkpoint loaded into a resnet50 U-Net matches 380/380 target keys, so a
    franken-load reports ZERO missing keys and is caught only by the 306
    unexpected ones. Missing-key checks alone would not see it.
    """
    missing = [n for n in res.missing_keys
               if not any(n.startswith(a) for a in allow_missing)]
    unexpected = list(res.unexpected_keys)
    if missing or unexpected:
        def _show(keys):
            head = ", ".join(keys[:6])
            return head + (" ... (+%d more)" % (len(keys) - 6) if len(keys) > 6 else "")
        msg = ["CHECKPOINT DOES NOT FIT THIS MODEL" + (" - " + what if what else ""),
               "  checkpoint : %s" % Path(ckpt_path).name]
        if missing:
            msg += ["  missing    : %d key(s) the model needs and the ckpt lacks" % len(missing),
                    "               " + _show(missing)]
        if unexpected:
            msg += ["  unexpected : %d key(s) the ckpt has and the model lacks" % len(unexpected),
                    "               " + _show(unexpected)]
        msg += ["",
                "  Loading anyway leaves those weights at INITIALISATION and then trains",
                "  and scores without raising - a plausible number off a partly random",
                "  model. If this gap is expected, the CALLER declares it via",
                "  allow_missing=(...); the loader does not guess."]
        raise SystemExit(chr(10).join(msg))


def load_state_into(model, ckpt_path, device, allow_missing=(), what=""):
    """Load a checkpoint's model_state into model (handles torch.compile wrap and
    RGB->RGB+hillshade first-conv inflation).

    T10 (2026-08-29). This called load_state_dict(strict=False) and THREW THE RESULT
    AWAY. strict=False does not fail on a key mismatch - it reports one and carries
    on - so a checkpoint sharing only its encoder with this model loads that, leaves
    everything else at initialisation, and trains and scores with no error raised
    anywhere. core.py already documents that hazard in prose at the writer side.

    Deferred while every model was the same smp.Unet and a mismatch was hypothetical.
    An architecture change ends that: inserting an ASPP bottleneck adds keys between
    encoder and decoder, so the FIRST load of the old 2020 base into the new model is
    precisely this failure - and its symptom is a plausible number, not a crash.

    `allow_missing` is the only way to permit a gap, it is per-call and prefix-matched,
    so a caller must NAME what it expects to be absent. Unexpected keys are never
    allowed: they mean the checkpoint carries weights this model has no place for,
    which is the wrong-architecture signal itself.
    """
    from phase4seg.core import _ensure_torch  # lazy: no module-level cycle
    _ensure_torch()                            # deps bootstrap still fires here
    import torch
    ckpt = torch.load(ckpt_path, map_location=device)
    state = ckpt["model_state"]
    tgt = model._orig_mod if hasattr(model, "_orig_mod") else model
    state = _inflate_first_conv(state, tgt.state_dict())
    res = tgt.load_state_dict(state, strict=False)
    _assert_state_fits(res, ckpt_path, allow_missing, what)
    return ckpt


def resolve_p3_ckpt(override=None):
    """Which checkpoint does this fine-tune start from?

    T12 (2026-08-30). A bad `--ckpt` used to WARN and then fall back to the default
    Phase-3 checkpoint, and training continued normally. One mistyped character and the
    run silently starts from a different model than the operator asked for — the
    warning scrolls past in a Colab log nobody reads live, the manifest records the
    --ckpt they intended, and the arm is then compared against others as though it used
    it. Under the re-baseline that is worse, not better: an epoch-2 run claiming a
    specific warm start is exactly the kind of provenance the EPOCH marker exists to
    make trustworthy.

    An explicit path is a statement of intent. If it is wrong, say so and stop; do not
    substitute a different model and carry on. The default search is for when the
    caller expressed no preference.
    """
    if override:
        p = Path(override)
        if p.exists():
            return p
        raise SystemExit(
            f"--ckpt {p} does not exist.\n"
            f"  Refusing to fall back to the default Phase-3 checkpoint: you named a "
            f"specific starting model, and silently training from a different one "
            f"would misattribute every number this run produces.\n"
            f"  Fix the path, or drop --ckpt to use the default.")
    for c in P3_CKPT_CANDIDATES:
        if c.exists():
            return c
    return None

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
    from phase4seg.core import _ensure_torch  # lazy: no module-level cycle
    _ensure_torch()                            # deps bootstrap still fires here
    import torch
    # verified write (P4.1): torch.save to local NVMe, then a verified copy to
    # Drive.
    # WAS size-only, on the reasoning that this runs many times per training and
    # truncation is what size catches. That reasoning did not survive 2026-08-29:
    # the checkpoint that passed every gate was not truncated, it was the WRONG
    # EPOCH — a well-formed, correctly-sized epoch-7 file sitting where the log
    # said epoch 24 was. Size cannot see that and neither can sha256; what sees it
    # is the identity block below plus a check against the SERVER, which is what
    # `checksum=True` now unlocks (it computes the md5 verify_on_drive compares).
    # Cost is one hash pass over a local-NVMe file per improving epoch — tenths of
    # a second, against an artifact this run exists to produce.
    path = Path(path)
    local = _local_artifact_path(path)
    payload = {"phase": phase, "epoch": epoch, "model_state": state,
               "optim_state": optim_state, "sched_state": sched_state,
               "history": history, "best_val": best_val,
               "in_channels": config.IN_CHANNELS,          # 3=RGB, 4=RGB+structure
               "aux_height_head": bool(config.AUX_HEIGHT), # height-prediction head present
               # Re-baseline marker: lets a reader tell whether two checkpoints
               # are comparable without reconstructing it from dates. Absent on
               # pre-2026-08-30 checkpoints, which means epoch 1.
               "epoch_marker": config.EPOCH,
               # Which architecture produced these weights. Without it a DeepLabV3+
               # checkpoint and a U-Net one are indistinguishable, and smp gives them the
               # same encoder.* prefix so a cross-load is a PARTIAL load, not an error.
               "arch": str(getattr(config, "ARCH", "unet")).lower(),
               "hs_source": config.HS_SOURCE,             # which raster band 4 was
               # ── identity (2026-08-29, D2/D17) ──────────────────────────────
               # Without these a checkpoint cannot say which run produced it, so
               # a stale-but-well-formed file is indistinguishable from the right
               # one — exactly how an epoch-7 corpse passed VERIFY:train while the
               # log reported epoch 24. `epoch` is now ALWAYS 1-based and matches
               # the log line; `epoch_base` records that so a file written before
               # this change is still readable.
               "run_id": config.RUN_ID,
               "run_tag": config.RUN_TAG,
               "run_years": config.RUN_YEARS,
               "epoch_base": 1,
               "saved_utc": _dt.datetime.now(_dt.timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%SZ")}
    if extra:
        payload.update(extra)
    torch.save(payload, local)
    if local != path:
        _copy_to_drive(local, path)
        try:
            local.unlink()
        except OSError:
            pass


def _save_ckpt(phase, epoch, model, optim, sched, history, best_val, path):
    _save_ckpt_state(phase, epoch, _model_state_of(model), optim.state_dict(),
                     sched.state_dict(), history, best_val, path)
