"""IGNORE-aware segmentation losses. Extracted from core.py 2026-08-31 (plan item 3.5).

WHY THIS MODULE AND NOT THE OTHERS. core.py is 2,833 lines; this is the one cluster that
splits cheaply. It has one lazy handle (torch), zero monkeypatch surface, no symbol
citations pointing into it, one-way dependencies, and a 15-test local suite that runs
against real torch. The steps and checkpoint-selection clusters have none of that — a test
monkeypatches core._train_one_epoch, and another hardcodes step_evaluate living in core.py
— so a green result here does NOT board them.

TORCH IS IMPORTED INSIDE THE FUNCTIONS THAT NEED IT, exactly as sdm_for_mask already does
for scipy. That is deliberate and it is the whole reason this split is cheap. core.py binds
torch into ITS OWN module globals via `global torch, ...` in _ensure_torch, so a moved-out
module would otherwise have no torch at all. The board's proposed remedy was to rework the
loader to bind into a caller-supplied globals dict; that was rejected — it would impose a
per-module call-ordering obligation whose failure mode is a NameError at call time, in
training. A function-local import cannot fail that way: by the time any loss runs,
build_model has already called _ensure_torch and the module is in sys.modules.

The package-level lazy-torch property is preserved: importing phase4seg.losses pulls no
torch, which qc/test_ci_gates.py::test_torch_stays_lazy enforces for the package as a whole.

Every term here is IGNORE-aware (255 = unlabelled). A loss that is not silently trains on
the sentinel, which is why they all carry an explicit weight and normalise by its sum.
"""
from phase4seg.config import *          # noqa: F401,F403  (DICE_SMOOTH, FOCAL_*, IGNORE_LABEL)
from phase4seg import config            # noqa: F401

import numpy as np
import rasterio

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
    import torch

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
    import torch

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
    import torch

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


def sdm_for_mask(s, ignore_buffer=0):
    """Signed distance map + weight for ONE 2-D mask. numpy in, numpy out.

    The per-sample core, so the Dataset (which has a single numpy mask) and the batch
    path (which has a torch tensor) share one implementation rather than two that agree
    until someone edits one. See phase4seg/names.py for what that costs.

    scipy is imported lazily and stays lazy: this module is heavy, and the import
    hygiene the orchestrator depends on is worth more than a microsecond here.
    """
    from scipy.ndimage import binary_dilation, distance_transform_edt

    ign = (s == IGNORE_LABEL)
    canopy = (s == 1)
    valid = ~ign
    if ignore_buffer > 0 and ign.any():
        valid &= ~binary_dilation(ign, iterations=int(ignore_buffer))
    w = valid.astype(np.float32)
    # A tile that is all canopy or all background has NO boundary; a distance field
    # there is meaningless, so contribute nothing rather than a large constant.
    if not canopy.any() or canopy.all():
        return np.zeros(s.shape, np.float32), w
    d = (distance_transform_edt(~canopy)
         - distance_transform_edt(canopy)).astype(np.float32)
    peak = float(np.abs(d).max())
    if peak > 0:
        d /= peak
    return d, w


def _signed_distance_map(masks, ignore_buffer=0):
    """Kervadec-style signed distance map of the canopy boundary, plus its weight.

    Sign convention (Kervadec et al. 2019): NEGATIVE inside canopy, POSITIVE outside.
    The boundary loss is then sum(sdm * prob), so predicting canopy far outside the
    true region is penalised in proportion to how far outside it is, and predicting it
    inside is rewarded. That distance weighting is the whole point: an ordinary region
    loss treats a pixel 1 px over the edge exactly like one 50 px over it.

    THE HAZARD THIS FUNCTION EXISTS TO HANDLE, and it does not arise for BCE or Dice.
    A distance transform needs a BINARY field, so the 255 IGNORE pixels have to be
    assigned to one side. Assigning them to background manufactures a boundary at every
    canopy/IGNORE edge - and those edges are everywhere in this project, because IGNORE
    is exactly where the label is unsure. Training a boundary term to snap to a
    manufactured edge would teach the model the shape of our uncertainty.

    Two defences, both necessary:
      1. the returned weight is zero at IGNORE (matching _masked_bce/_masked_dice), and
      2. `ignore_buffer` dilates that zero outward, so the manufactured boundary's
         NEIGHBOURHOOD is excluded too - the loss is only applied where the distance
         field was computed from real labels on both sides.

    Returns (sdm, weight), float32, on masks.device. Per-sample normalisation by the
    max absolute distance makes the term scale-free, so its weight means the same thing
    at any tile size or canopy fraction.
    """
    import torch

    m = masks.detach().cpu().numpy()
    sdm = np.zeros(m.shape, np.float32)
    w = np.zeros(m.shape, np.float32)
    flat = m.reshape(-1, *m.shape[-2:])
    fs, fw = sdm.reshape(-1, *m.shape[-2:]), w.reshape(-1, *m.shape[-2:])
    for j in range(flat.shape[0]):
        fs[j], fw[j] = sdm_for_mask(flat[j], ignore_buffer)
    dev = masks.device
    return (torch.from_numpy(sdm).to(dev), torch.from_numpy(w).to(dev))


def _masked_boundary(logits, masks, sdm=None, ignore_buffer=0):
    """Boundary loss over labeled pixels only (255 = IGNORE excluded, plus a buffer).

    IGNORE handling matches _masked_bce and _masked_dice: the weight is zero at IGNORE
    and the sum is normalised by the weight, so an all-IGNORE tile contributes nothing
    rather than dividing by zero.

    COST, AND A PREMISE THAT DID NOT SURVIVE THE CODE (2026-08-30). The two distance
    transforms are ~23 ms per 512 px tile, so a batch of 10 adds ~230 ms plus a
    GPU->CPU->GPU round trip. The plan called that "pure waste, since the SDM depends
    only on the fixed mask" and said to precompute one per tile. IT DOES NOT DEPEND ONLY
    ON THE TILE: the training augmentation is Rotate(45) + Affine(scale) + GridDistortion
    + ElasticTransform at p = .5/.5/.4/.3, so 89.5% of training tiles are warped
    NON-ISOMETRICALLY. A field computed before that describes a different shape than the
    mask the logits are scored against, and the mismatch is silent.

    So the work is not removable, only movable. SemanticDataset now computes it AFTER
    augmentation, in the DataLoader workers, and passes it in as `sdm` — parallel,
    overlapped with GPU compute, and no round trip. Total CPU work is unchanged; the
    training step's critical path is what gets shorter.

    Passing `sdm=None` still computes it here. That is the path the boundary tests
    drive, and the one any caller without Dataset support gets.
    """
    import torch

    if sdm is None:
        sdm, w = _signed_distance_map(masks, ignore_buffer)
    else:
        sdm, w = sdm
    probs = torch.sigmoid(logits)
    return (sdm * probs * w).sum() / w.sum().clamp(min=1.0)



def _seg_loss(criterion_none, logits, masks, loss_mode="bce_dice", boundary_w=0.0,
              sdm=None):
    """Combined masked segmentation loss (all terms IGNORE-aware).

    loss_mode "focal_dice" -> FOCAL_WEIGHT*focal + DICE_WEIGHT*dice (Edit F);
    otherwise -> BCE_WEIGHT*bce + DICE_WEIGHT*dice (default, run-5 baseline).

    `boundary_w` > 0 ADDS the signed-distance boundary term. It is a WEIGHT rather than
    a loss_mode on purpose: Kam's design applies it in Phase B only, so the caller passes
    0.0 while the encoder is frozen and the configured value once it is not. A weight
    also makes the Kervadec alpha schedule expressible without a second mode string.

    Default 0.0 -> byte-for-byte the previous loss. Every existing arm is unaffected.

    Returns (combined, primary_component, dice_component) as before.
    """
    dice = _masked_dice(logits, masks)
    if loss_mode == "focal_dice":
        focal = _masked_focal(criterion_none, logits, masks)
        total = FOCAL_WEIGHT * focal + config.DICE_WEIGHT * dice
        primary = focal
    else:
        bce = _masked_bce(criterion_none, logits, masks)
        total = config.BCE_WEIGHT * bce + config.DICE_WEIGHT * dice
        primary = bce
    if boundary_w:
        # `sdm` is the (field, weight) pair the Dataset already computed for THIS
        # augmented mask. None falls back to computing it here — the path the boundary
        # tests exercise directly, and the one any caller without Dataset support gets.
        total = total + boundary_w * _masked_boundary(
            logits, masks, sdm=sdm, ignore_buffer=config.BOUNDARY_IGNORE_BUFFER)
    return total, primary, dice


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
