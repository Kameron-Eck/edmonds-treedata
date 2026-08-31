"""load_state_into must refuse a checkpoint that does not fit the model (T10).

WHY THIS IS A TEST AND NOT A COMMENT. The old line was

    tgt.load_state_dict(state, strict=False)      # result discarded

and `strict=False` does not raise on a key mismatch — it RETURNS one. So a
checkpoint sharing only its encoder with the target model loaded that encoder,
left the decoder at initialisation, and then trained and scored with no error
anywhere. The output of that is not a crash; it is a number, and a plausible one.

This was recorded as deferred (T10) while every model in the project was the same
`smp.Unet` and a key mismatch could not really happen. The proposed ASPP-UNet
overhaul ends that: inserting a bottleneck adds keys between encoder and decoder,
so the very first load of the existing 2020 base into the new architecture IS this
failure. The guard has to exist before that load is attempted, not after someone
notices the numbers look odd.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_ckpt_load.py -q
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent

torch = pytest.importorskip("torch")
core = pytest.importorskip("phase4seg.core")

# core.py binds `torch` lazily inside _ensure_torch(); every step function calls it
# before touching the model. A direct unit call has to do the same or the loader
# raises NameError on `torch.load` before it can refuse anything.
core._ensure_torch()


class _Tiny(torch.nn.Module):
    """Stand-in for the real model: two named blocks, so we can drop one and get
    exactly the encoder-matches / decoder-missing shape the overhaul will produce."""

    def __init__(self, with_head=False):
        super().__init__()
        self.encoder = torch.nn.Conv2d(3, 4, 1)
        self.decoder = torch.nn.Conv2d(4, 1, 1)
        if with_head:
            # NAMED TO MATCH THE REAL MODEL. core.py::_build_unet_with_height calls this
            # attribute `height_head`, so the state_dict keys are height_head.weight /
            # .bias. This stand-in used to call it `aux_height_head`, and because the
            # three production call sites passed that same wrong prefix to allow_missing,
            # all four assertions below passed against a prefix the real model never
            # emits. The tests agreed with the bug instead of catching it.
            self.height_head = torch.nn.Conv2d(4, 1, 1)


def _save(tmp_path, state, name="ck.pt"):
    p = tmp_path / name
    torch.save({"model_state": state}, p)
    return p


def test_an_exactly_matching_checkpoint_loads(tmp_path):
    m = _Tiny()
    ck = _save(tmp_path, m.state_dict())
    assert core.load_state_into(_Tiny(), ck, torch.device("cpu")) is not None


def test_a_checkpoint_missing_the_decoder_is_refused(tmp_path):
    """The overhaul's exact shape: encoder keys line up, the rest do not."""
    full = _Tiny().state_dict()
    encoder_only = {k: v for k, v in full.items() if k.startswith("encoder.")}
    ck = _save(tmp_path, encoder_only)
    with pytest.raises(SystemExit) as e:
        core.load_state_into(_Tiny(), ck, torch.device("cpu"))
    msg = str(e.value)
    assert "CHECKPOINT DOES NOT FIT THIS MODEL" in msg
    assert "decoder.weight" in msg, msg
    assert "INITIALISATION" in msg, "the message must say what loading anyway would do"


def test_unexpected_keys_are_refused_even_with_allow_missing(tmp_path):
    """A ckpt carrying weights the model has no place for is the wrong-architecture
    signal itself, so allow_missing must not launder it."""
    state = _Tiny(with_head=True).state_dict()
    ck = _save(tmp_path, state)
    with pytest.raises(SystemExit) as e:
        core.load_state_into(_Tiny(), ck, torch.device("cpu"),
                             allow_missing=("height_head.",))
    assert "unexpected" in str(e.value)


def test_the_declared_aux_head_gap_is_permitted(tmp_path):
    """The one real allowance: the Phase-3 2020 base predates the aux height head,
    so a --aux-height model legitimately has keys it cannot supply."""
    ck = _save(tmp_path, _Tiny().state_dict())            # no head, like Phase 3
    got = core.load_state_into(_Tiny(with_head=True), ck, torch.device("cpu"),
                               allow_missing=("height_head.",))
    assert got is not None


def test_the_allowance_is_prefix_scoped_not_a_blanket(tmp_path):
    """Naming one absent block must not excuse an unrelated one."""
    full = _Tiny(with_head=True).state_dict()
    ck = _save(tmp_path, {k: v for k, v in full.items() if k.startswith("encoder.")})
    with pytest.raises(SystemExit) as e:
        core.load_state_into(_Tiny(with_head=True), ck, torch.device("cpu"),
                             allow_missing=("height_head.",))
    assert "decoder" in str(e.value), "the undeclared decoder gap must still stop it"


# ── --loss-mode must not be accepted-and-inert ───────────────────────────────
def test_loss_mode_is_refused_where_it_would_do_nothing():
    """--loss-mode only mutates TIER_LOSS_MODE["coarse"]. The help text is honest
    about that, but nothing said so at RUN time: passing it on a fine or medium year
    was accepted, changed nothing, and landed in the manifest's argv looking as though
    it applied. A later reader comparing that arm to a baseline would credit the null
    to the loss rather than to a flag that never took effect."""
    from phase4seg.cli import loss_mode_scope_error

    msg = loss_mode_scope_error("focal_dice", {"fine"})
    assert msg and "only affects the COARSE tier" in msg
    assert "change nothing" in msg, "the message must say WHY it is refused"

    assert loss_mode_scope_error("focal_dice", {"coarse"}) is None
    assert loss_mode_scope_error("focal_dice", {"fine", "coarse"}) is None, \
        "a mixed run that INCLUDES coarse is legitimate — the flag does something"
    assert loss_mode_scope_error(None, {"fine"}) is None, "no flag, no complaint"
    assert loss_mode_scope_error("focal_dice", set()) is None, \
        "unknown tier set must not hard-fail a run"


# ── --ckpt must not silently substitute a different model ────────────────────
def test_a_bad_ckpt_path_refuses_rather_than_falling_back(tmp_path):
    """A mistyped --ckpt used to WARN and then train from the DEFAULT Phase-3
    checkpoint. One wrong character and the run starts from a different model than the
    operator named — the warning scrolls past in a Colab log nobody reads live, and the
    manifest records the --ckpt they intended. The arm is then compared against others
    as though it used it."""
    with pytest.raises(SystemExit) as e:
        core.resolve_p3_ckpt(str(tmp_path / "typo_does_not_exist.pt"))
    msg = str(e.value)
    assert "does not exist" in msg
    assert "Refusing to fall back" in msg, "the message must say what it refused to do"


def test_a_good_ckpt_path_is_returned(tmp_path):
    p = tmp_path / "real.pt"
    p.write_bytes(b"x")
    assert core.resolve_p3_ckpt(str(p)) == p


def test_no_override_still_searches_the_defaults():
    """The default search is for when the caller expressed NO preference — the refusal
    above must not break it."""
    got = core.resolve_p3_ckpt(None)
    assert got is None or got.exists(), "default search returned a nonexistent path"


# ── the prefix must come FROM the model, not from a stand-in ──────────────────

def test_allow_missing_prefix_matches_the_real_aux_head():
    """THE REGRESSION THIS FILE MISSED, 2026-08-31.

    core.py::_build_unet_with_height names the head `self.height_head`, so its state_dict
    keys are `height_head.weight` / `height_head.bias`. Three production call sites passed
    `allow_missing=("aux_height_head.",)` — a prefix that matches NEITHER — so
    _assert_state_fits would raise SystemExit on any --aux-height run loading a non-aux
    checkpoint, which is every warm start from the 2020 base.

    It shipped in 50006ce (2026-08-29, the commit that made a non-fitting checkpoint
    fatal) and was invisible for two reasons that reinforced each other: this file's
    stand-in was ALSO called `aux_height_head`, so four assertions agreed with the bug;
    and phase4seg_smoke.py hard-sets AUX_HEIGHT = False, so the runtime gate never
    reached the branch. Nobody had run the flag since — the last aux run in
    run_registry.csv is 20260707_2016_v046_aux-height.

    A stand-in can be named anything. This derives the prefix from the REAL model, so the
    two cannot drift apart again.
    """
    from phase4seg import config, core

    core._ensure_torch()
    saved_aux, saved_ch = config.AUX_HEIGHT, config.IN_CHANNELS
    try:
        config.AUX_HEIGHT, config.IN_CHANNELS = True, 3
        model = core._build_unet_with_height()
        head_keys = [k for k in model.state_dict() if "height" in k]
    finally:
        config.AUX_HEIGHT, config.IN_CHANNELS = saved_aux, saved_ch

    assert head_keys, "the aux model exposes no height keys at all"

    # Scan the whole ENGINE PACKAGE, not core.py by path: the split boarded as 3.5 would
    # move this code, and a path-anchored read would then pass vacuously. Same reason
    # test_status_discovery bans the hardcoded shape.
    import re
    from phase4seg.names import engine_files

    prefixes = set()
    for f in engine_files(Path(__file__).resolve().parent.parent / "pipeline" / "phase4seg"):
        prefixes |= set(re.findall(r'allow_missing=\("([A-Za-z0-9_.]+)",\)',
                                   f.read_text(encoding="utf-8")))
    assert prefixes, "no allow_missing prefixes found anywhere in the engine package"

    for pref in prefixes:
        assert any(k.startswith(pref) for k in head_keys), (
            f"the engine passes allow_missing=({pref!r},) but the real model's head keys "
            f"are "
            f"{head_keys} — nothing starts with it, so _assert_state_fits will reject "
            f"every warm start on an --aux-height run")


def test_the_aux_head_actually_loads_from_a_non_aux_checkpoint():
    """End-to-end on the real model: a checkpoint WITHOUT the head (every 2020 base
    warm start) must load into the aux model with the head left at initialisation, and
    must NOT raise. This is the exact path --aux-height takes on epoch 1."""
    from phase4seg import config, core

    core._ensure_torch()
    saved_aux, saved_ch = config.AUX_HEIGHT, config.IN_CHANNELS
    try:
        config.AUX_HEIGHT, config.IN_CHANNELS = True, 3
        model = core._build_unet_with_height()
        full = model.state_dict()
        non_aux = {k: v for k, v in full.items() if not k.startswith("height_head.")}
        res = model.load_state_dict(non_aux, strict=False)
        core._assert_state_fits(res, "synthetic.pt",
                                allow_missing=("height_head.",), what="aux warm start")
    finally:
        config.AUX_HEIGHT, config.IN_CHANNELS = saved_aux, saved_ch
