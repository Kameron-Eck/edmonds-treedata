"""The signed-distance boundary loss: does it do what Dice cannot, and is it safe?

WHY THIS TERM EXISTS. The measured failure here is crown PERIMETERS and small crowns —
41.8% of misses in 16.3% of the area. BCE and Dice are region losses: they score a pixel
one step over the edge exactly like one fifty steps over it, so neither can express "the
edge is in the wrong place". And canopy AREA — the deliverable — is an integral over the
mask edge, so a blobby border inflates the number the project reports.

The discriminating test is `test_it_penalises_distance_where_dice_cannot`: two predictions
wrong in the SAME NUMBER of pixels, one hugging the boundary and one far away. Dice scores
them identically. If the boundary term does too, it is not worth its cost.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_boundary_loss.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))

torch = pytest.importorskip("torch")
pytest.importorskip("scipy")
core = pytest.importorskip("phase4seg.core")
from phase4seg import config  # noqa: E402

core._ensure_torch()

S = 64
IGN = core.IGNORE_LABEL


def _mask(canopy_box=(20, 44), ignore_box=None):
    """(1,1,S,S) mask: a centred canopy square, optionally an IGNORE stripe."""
    m = np.zeros((S, S), np.float32)
    a, b = canopy_box
    m[a:b, a:b] = 1.0
    if ignore_box:
        r0, r1, c0, c1 = ignore_box
        m[r0:r1, c0:c1] = IGN
    return torch.from_numpy(m)[None, None]


def _logits_for(pred_bool, conf=6.0):
    """Near-saturated logits: +conf where predicted canopy, -conf elsewhere."""
    x = np.where(pred_bool, conf, -conf).astype(np.float32)
    return torch.from_numpy(x)[None, None]


def _box(a, b):
    p = np.zeros((S, S), bool)
    p[a:b, a:b] = True
    return p


# ── the discriminating test ───────────────────────────────────────────────────

def test_it_penalises_distance_where_dice_cannot():
    """Same pixel count wrong, different distance from the true edge.

    Truth is the square [20,44). Both predictions add exactly the same NUMBER of false
    canopy pixels — one as a ring hugging the boundary, one as a detached blob far away.
    Dice sees an identical intersection and union, so it cannot separate them. The
    boundary term must.
    """
    masks = _mask()
    truth = _box(20, 44)

    near = truth.copy()
    near[18:20, 20:44] = True          # 48 px, one step outside the top edge
    far = truth.copy()
    far[0:2, 20:44] = True             # 48 px, twenty steps away

    assert near.sum() == far.sum(), "the two errors must be the same SIZE"

    d_near = core._masked_dice(_logits_for(near), masks).item()
    d_far = core._masked_dice(_logits_for(far), masks).item()
    assert abs(d_near - d_far) < 1e-5, (
        f"Dice separated them ({d_near:.6f} vs {d_far:.6f}) — the premise of this test "
        "is that it cannot, so the test itself is wrong")

    b_near = core._masked_boundary(_logits_for(near), masks).item()
    b_far = core._masked_boundary(_logits_for(far), masks).item()
    assert b_far > b_near, (
        f"the boundary term did not punish distance: near={b_near:.6f} far={b_far:.6f}. "
        "That is the one thing it exists to do.")


def test_a_correct_prediction_beats_a_dilated_one():
    masks = _mask()
    exact = core._masked_boundary(_logits_for(_box(20, 44)), masks).item()
    blobby = core._masked_boundary(_logits_for(_box(16, 48)), masks).item()
    assert blobby > exact, "a blobby border must cost more than a tight one"


def test_sign_convention_inside_is_rewarded():
    """Kervadec: the map is NEGATIVE inside, POSITIVE outside, so predicting canopy
    inside the true region lowers the loss and predicting it outside raises it."""
    masks = _mask()
    sdm, w = core._signed_distance_map(masks)
    s = sdm[0, 0].numpy()
    assert s[32, 32] < 0, "centre of the canopy square should be NEGATIVE (inside)"
    assert s[2, 2] > 0, "far corner should be POSITIVE (outside)"


# ── IGNORE safety — the contract every loss term here shares ──────────────────

def test_ignore_pixels_contribute_nothing():
    """Changing the prediction ONLY under IGNORE must not move the loss."""
    masks = _mask(ignore_box=(0, 8, 0, S))
    base = _box(20, 44)
    with_junk = base.copy()
    with_junk[0:8, :] = True                     # all inside the IGNORE stripe
    a = core._masked_boundary(_logits_for(base), masks, ignore_buffer=0).item()
    b = core._masked_boundary(_logits_for(with_junk), masks, ignore_buffer=0).item()
    assert abs(a - b) < 1e-6, f"IGNORE pixels leaked into the loss: {a} vs {b}"


def test_the_buffer_excludes_the_manufactured_boundary():
    """A distance transform needs a binary field, so IGNORE is assigned to background
    and a FALSE boundary appears wherever canopy meets IGNORE. The buffer must widen
    the exclusion so the loss is not applied in that neighbourhood."""
    masks = _mask(canopy_box=(20, 44), ignore_box=(20, 44, 44, 52))   # touches canopy
    _s0, w0 = core._signed_distance_map(masks, ignore_buffer=0)
    _s3, w3 = core._signed_distance_map(masks, ignore_buffer=3)
    assert w3.sum() < w0.sum(), "the buffer excluded nothing"
    # the excluded band must sit adjacent to the IGNORE region, not somewhere random
    assert w3[0, 0, 32, 45] == 0.0 and w3[0, 0, 32, 41] == 0.0, \
        "the buffer should zero the pixels flanking the canopy/IGNORE seam"


def test_an_all_ignore_tile_is_finite_and_zero():
    m = torch.full((1, 1, S, S), float(IGN))
    v = core._masked_boundary(_logits_for(_box(20, 44)), m).item()
    assert np.isfinite(v) and abs(v) < 1e-6, f"all-IGNORE tile gave {v}"


def test_degenerate_tiles_contribute_nothing():
    """All-canopy and all-background tiles have NO boundary; a distance field there is
    meaningless and must not become a large constant push."""
    for fill in (0.0, 1.0):
        m = torch.full((1, 1, S, S), fill)
        sdm, _w = core._signed_distance_map(m)
        assert float(sdm.abs().max()) == 0.0, f"fill={fill} produced a distance field"
        v = core._masked_boundary(_logits_for(_box(20, 44)), m).item()
        assert np.isfinite(v), f"fill={fill} gave {v}"


# ── it must be inert until switched on ────────────────────────────────────────

def test_default_is_byte_for_byte_the_previous_loss():
    """Every existing arm must be unaffected. boundary_w defaults to 0.0 and the term
    is additive, so the default path cannot differ."""
    masks = _mask()
    logits = _logits_for(_box(18, 46))
    crit = torch.nn.BCEWithLogitsLoss(reduction="none")
    off = core._seg_loss(crit, logits, masks)[0].item()
    expected = (config.BCE_WEIGHT * core._masked_bce(crit, logits, masks)
                + config.DICE_WEIGHT * core._masked_dice(logits, masks)).item()
    assert abs(off - expected) < 1e-9, "the default loss changed"


def test_the_weight_actually_switches_it_on():
    masks = _mask()
    logits = _logits_for(_box(10, 54))            # deliberately blobby
    crit = torch.nn.BCEWithLogitsLoss(reduction="none")
    off = core._seg_loss(crit, logits, masks, boundary_w=0.0)[0].item()
    on = core._seg_loss(crit, logits, masks, boundary_w=1.0)[0].item()
    assert on != off, "boundary_w had no effect"
    assert on > off, "an over-dilated prediction should cost MORE with the term on"


def test_it_is_differentiable():
    """It has to train, not just score."""
    masks = _mask()
    logits = _logits_for(_box(18, 46)).clone().requires_grad_(True)
    core._masked_boundary(logits, masks).backward()
    assert logits.grad is not None and torch.isfinite(logits.grad).all()
    assert float(logits.grad.abs().sum()) > 0, "no gradient reaches the logits"
