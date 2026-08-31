"""DeepLabV3+ as an ARM — the plumbing, and the silent cross-load it has to prevent.

Kam, 2026-08-31: "can deeplab v3+ be an arm? We are to test the plumbing out on a pilot set
of fine and course data. not the full pipeline."

So this is an ARM and a PLUMBING test. It does NOT overturn the decision recorded in
WORKPLAN.md — "keep the U-Net and resnet101; change the loss, not the backbone" — and
nothing here argues DeepLabV3+ should ship.

THE HAZARD THAT HAD TO BE CLOSED FIRST, measured on the installed smp 0.5.0: U-Net and
DeepLabV3+ share **626 of 685 state_dict keys**, because both hang off the same
`encoder.*` prefix. Loading one's checkpoint into the other therefore matches 91% of keys
and randomly initialises only the decoder. Before 2026-08-31 nothing recorded which
architecture produced a checkpoint — not the payload, not the run manifest, not the eval
rows — so that cross-load would have been invisible to every reader, and an "arm
comparison" could have been a U-Net encoder wearing an untrained DeepLabV3+ decoder.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_arch_arm.py -q
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent

torch = pytest.importorskip("torch")
core = pytest.importorskip("phase4seg.core")
from phase4seg import config  # noqa: E402

core._ensure_torch()


def _build(arch, in_ch=3, aux=False):
    sa, sc, sx = config.ARCH, config.IN_CHANNELS, config.AUX_HEIGHT
    try:
        config.ARCH, config.IN_CHANNELS, config.AUX_HEIGHT = arch, in_ch, aux
        return core.build_model(torch.device("cpu"), compile_model=False)
    finally:
        config.ARCH, config.IN_CHANNELS, config.AUX_HEIGHT = sa, sc, sx


def test_both_arms_build_and_agree_on_output_shape():
    """Same output contract, so nothing downstream needs to know which arm ran."""
    x = torch.randn(2, 3, 256, 256)
    for arch in ("unet", "deeplabv3plus"):
        m = _build(arch).eval()
        with torch.no_grad():
            out = m(x)
        assert tuple(out.shape) == (2, 1, 256, 256), f"{arch} -> {tuple(out.shape)}"


def test_the_two_arms_share_most_keys_which_is_exactly_the_danger():
    """Documents the hazard as a measurement rather than a warning. If this ratio ever
    drops to near zero the cross-load stops being silent and the stamp matters less —
    but on smp 0.5.0 it is 91%."""
    u, d = _build("unet"), _build("deeplabv3plus")
    uk, dk = set(u.state_dict()), set(d.state_dict())
    shared = len(uk & dk)
    assert shared > 0.8 * min(len(uk), len(dk)), (
        f"only {shared} shared keys — re-read whether the cross-load is still silent")


def test_a_cross_architecture_load_is_refused():
    """THE POINT. Without _assert_state_fits this is a 91%-successful partial load with no
    error: encoder weights land, the decoder stays at initialisation, training proceeds,
    and a number comes out."""
    u, d = _build("unet"), _build("deeplabv3plus")
    res = d.load_state_dict(u.state_dict(), strict=False)
    assert res.missing_keys and res.unexpected_keys, (
        "the two architectures now have identical key sets — this test is meaningless")
    with pytest.raises(SystemExit):
        core._assert_state_fits(res, "unet.pt", what="u-net weights into deeplab")


def test_arch_is_stamped_where_a_reader_can_find_it():
    """A checkpoint or a run whose architecture cannot be recovered is not comparable to
    anything. Both the payload and the manifest carry it."""
    from phase4seg.names import symbol_body
    pkg = SCRIPTS / "pipeline" / "phase4seg"
    # By SYMBOL, not by filename — the 3.5 split moves this code, and a path-anchored
    # read would then pass vacuously. test_status_discovery bans the hardcoded shape and
    # caught this test doing it on the first attempt.
    ckpt = symbol_body(pkg, "_save_ckpt_state", "function") or ""
    manifest = symbol_body(pkg, "_write_run_manifest", "function") or ""
    assert ckpt and manifest, "could not locate the checkpoint writer or manifest writer"
    assert '"arch"' in ckpt, "the checkpoint payload does not record the architecture"
    assert '"arch"' in manifest, "the run manifest does not record the architecture"


def test_aux_height_with_a_non_unet_arch_is_refused_not_resolved():
    """_build_unet_with_height subclasses smp.Unet specifically to preserve the
    encoder.*/decoder.*/segmentation_head.* layout that P3/P0 warm starts need. Combining
    it with another architecture has no meaning, so it raises rather than silently
    picking one."""
    with pytest.raises(SystemExit):
        _build("deeplabv3plus", aux=True)


def test_arch_does_not_invalidate_the_tile_cache():
    """An arm comparison is only affordable if switching arms reuses the tiles. Gated
    against _tile_signature's real source, not a remembered list."""
    from phase4seg.names import engine_files
    import ast
    pkg = SCRIPTS / "pipeline" / "phase4seg"
    src = (pkg / "tiling.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_tile_signature")
    body = ast.get_source_segment(src, fn) or ""
    for name in ("ARCH", "DEEPLAB_OUTPUT_STRIDE", "DEEPLAB_DECODER_CH"):
        assert name not in body, (
            f"{name} leaked into _tile_signature — switching arms would force a "
            f"~20 min/year re-tile and make arm comparison unaffordable")
    assert engine_files(pkg)
