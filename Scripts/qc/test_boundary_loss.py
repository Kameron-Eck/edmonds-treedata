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


# ── the SDM moved into the DataLoader worker (4.1, 2026-08-30) ───────────────

def _getitem_source():
    """SemanticDataset.__getitem__'s text, found by SYMBOL rather than by filename.

    It lived in core.py when these were written, and core.py is 2,833 lines with a split
    scheduled. A path-anchored read would pass vacuously the moment the class moved —
    the gate would stop checking and say nothing, which is the failure this repo keeps
    finding in other people's code and had just written into its own."""
    from phase4seg.names import symbol_body
    body = symbol_body(SCRIPTS / "pipeline" / "phase4seg", "__getitem__",
                       "function", within="SemanticDataset")
    assert body, "SemanticDataset.__getitem__ not found in the engine package"
    return body

def test_the_precomputed_field_equals_the_one_computed_in_the_loss():
    """The move is only safe if both paths agree exactly. They share sdm_for_mask now,
    so this is really asserting that the batch wrapper still routes through the
    per-sample core rather than having regrown its own copy of the EDT logic."""
    masks = _mask(ignore_box=(50, 60, 0, S))          # canopy square + IGNORE stripe
    m = masks[0, 0].numpy()

    sdm_b, w_b = core._signed_distance_map(masks, config.BOUNDARY_IGNORE_BUFFER)
    sdm_s, w_s = core.sdm_for_mask(m, config.BOUNDARY_IGNORE_BUFFER)

    assert np.allclose(sdm_b.numpy()[0, 0], sdm_s), "batch and per-sample fields differ"
    assert np.allclose(w_b.numpy()[0, 0], w_s), "batch and per-sample weights differ"


def test_passing_a_precomputed_field_gives_the_same_loss():
    """What the training step now does. If the two disagree, every boundary-trained run
    would be optimising a slightly different objective than the tests measured."""
    masks = _mask()
    logits = torch.randn(1, 1, S, S) * 2.0

    crit = torch.nn.BCEWithLogitsLoss(reduction="none")
    pre = core._signed_distance_map(masks, config.BOUNDARY_IGNORE_BUFFER)
    a = core._seg_loss(crit, logits, masks, "bce_dice", boundary_w=1.0, sdm=pre)[0]
    b = core._seg_loss(crit, logits, masks, "bce_dice", boundary_w=1.0, sdm=None)[0]
    assert torch.allclose(a, b, atol=1e-6), (a.item(), b.item())


def test_the_field_follows_the_augmented_mask_not_the_stored_one():
    """THE REASON THIS IS NOT A CACHE. The plan said the SDM depends only on the fixed
    tile, so precompute one per tile. The training augmentation warps 89.5% of tiles
    non-isometrically (Rotate 45, Affine scale, GridDistortion, ElasticTransform), and a
    field computed before that describes a shape the logits are never scored against.

    A shifted square stands in for the warp: the field must move with the mask. If a
    cached, pre-augmentation field were used, this is the assertion that would fail —
    silently, in training, with no error anywhere."""
    stored = _mask(canopy_box=(20, 44))[0, 0].numpy()
    warped = _mask(canopy_box=(28, 52))[0, 0].numpy()   # what augmentation handed the loss

    sdm_stored, _ = core.sdm_for_mask(stored, 0)
    sdm_warped, _ = core.sdm_for_mask(warped, 0)

    assert not np.allclose(sdm_stored, sdm_warped), (
        "the distance field did not move with the mask — a per-tile cache would have "
        "been indistinguishable from correctness here, which is exactly the risk")
    # and the sign flips where the canopy moved: inside the new square, outside the old
    assert sdm_warped[48, 48] < 0 < sdm_stored[48, 48]


def test_the_dataset_carries_the_field_in_meta_not_as_a_new_tuple_element():
    """The batch is already unpacked two ways (AUX_HEIGHT on/off) at two sites. Adding
    positional elements would make four shapes, and a positional mix-up is the failure
    mode that just cost a dashboard every one of its step chips. A dict key cannot be
    mixed up."""
    import ast
    body = _getitem_source()
    assert 'meta["sdm"]' in body and "sdm_for_mask(" in body
    for ret in [n for n in ast.walk(ast.parse(body)) if isinstance(n, ast.Return)]:
        seg = ast.get_source_segment(body, ret)
        assert "sdm" not in seg, f"the SDM leaked into a return tuple: {seg}"


def test_nothing_is_computed_when_the_term_is_off():
    """BOUNDARY_WEIGHT is 0.0 today. The Dataset must not pay ~23 ms/tile for a term
    nothing is using — this is what keeps the change free for every current arm."""
    body = _getitem_source()
    assert body.count("if self.training and config.BOUNDARY_WEIGHT:") == 2, (
        "both Dataset return paths (AUX_HEIGHT on and off) must gate the SDM on the "
        "weight being non-zero")
