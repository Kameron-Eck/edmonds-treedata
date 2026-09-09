"""--encoder is a RUN flag, and the warm start it implies is stamped, not silent.

WHAT HAD TO BE TRUE before a resnet18/50 arm could run (2026-09-08, the backbone
sweep): the builders must read config.ENCODER at CALL time (ckpt.py used to import
the constant, so a per-run override would have built the default while the manifest
recorded the flag); the fine-tune must not die on the resnet101-only Phase-3 base
(it starts from ImageNet encoder weights instead, through the engine's own
first-conv inflation); and every writer a reader consults — manifest, checkpoint
payload, eval row — must carry `encoder` AND `warm_start`, because a 2020-warm-started
resnet101 arm and an ImageNet-started resnet18 arm differ in TWO things.

No download happens here: the ImageNet path is exercised with the smp encoder
factory monkeypatched to a random-init encoder of the same architecture, which has
the identical key set — what the load asserts is the KEY FIT, and that is what the
test checks.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_encoder_flag.py -q
"""
import ast
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent

torch = pytest.importorskip("torch")
core = pytest.importorskip("phase4seg.core")
from phase4seg import config, ckpt  # noqa: E402

core._ensure_torch()


def _build(encoder, in_ch=3):
    se, sc, sx = config.ENCODER, config.IN_CHANNELS, config.AUX_HEIGHT
    try:
        config.ENCODER, config.IN_CHANNELS, config.AUX_HEIGHT = encoder, in_ch, False
        return core.build_model(torch.device("cpu"), compile_model=False)
    finally:
        config.ENCODER, config.IN_CHANNELS, config.AUX_HEIGHT = se, sc, sx


def _n_params(m):
    return sum(p.numel() for p in m.parameters())


def test_choices_are_a_closed_set_containing_the_default():
    assert config.ENCODER in config.ENCODER_CHOICES
    assert config.P3_CKPT_ENCODER in config.ENCODER_CHOICES
    assert config.ENCODER == config.P3_CKPT_ENCODER, (
        "the default encoder no longer matches the P3 base — every default run "
        "would silently start from ImageNet; that is a recipe change, not a flag")


def test_builders_read_config_encoder_at_call_time():
    """The whole point: setting config.ENCODER changes what build_model returns."""
    r18, r50 = _build("resnet18"), _build("resnet50")
    assert _n_params(r18) < _n_params(r50), "resnet18 U-Net should be smaller than resnet50"
    assert set(r18.state_dict()) != set(r50.state_dict()), (
        "different encoders built identical key sets — config.ENCODER is not reaching "
        "the builder")


@pytest.mark.parametrize("encoder", ["resnet18", "resnet50"])
def test_small_encoder_keeps_the_step_contract(encoder):
    m = _build(encoder).eval()
    with torch.no_grad():
        out = m(torch.randn(1, 3, 128, 128))
    assert tuple(out.shape) == (1, 1, 128, 128)


def test_p3_base_cannot_load_into_a_small_encoder():
    """The refusal IS the guard: without it a resnet101 checkpoint would partially
    load into a resnet50 (380/380 target keys match — ckpt._assert_state_fits
    docstring) and train on. Simulated with fresh builds, no lake checkpoint."""
    r101, r50 = _build("resnet101"), _build("resnet50")
    res = r50.load_state_dict(r101.state_dict(), strict=False)
    assert res.unexpected_keys or res.missing_keys
    with pytest.raises(SystemExit):
        core._assert_state_fits(res, "sem_best_2020.pt", allow_missing=("height_head.",),
                                what="P3 base into resnet50")


def test_warm_start_kind_follows_encoder_and_ckpt():
    se = config.ENCODER
    try:
        config.ENCODER = config.P3_CKPT_ENCODER
        assert ckpt.warm_start_kind(None) == "p3_ckpt"
        config.ENCODER = "resnet18"
        assert ckpt.warm_start_kind(None) == "imagenet"
        # an explicit --ckpt is intent: it takes the checkpoint path, where a
        # mismatch STOPS the run rather than quietly switching to ImageNet
        assert ckpt.warm_start_kind("some/ckpt.pt") == "p3_ckpt"
    finally:
        config.ENCODER = se


@pytest.mark.parametrize("in_ch", [3, 4])
def test_imagenet_encoder_load_fits_without_download(monkeypatch, in_ch):
    """Key fit of the ImageNet path, with the download replaced by a same-architecture
    random encoder. 4-channel: the extra band goes through _inflate_first_conv
    (zero-init), the engine's convention, not smp's repeat-and-rescale."""
    import segmentation_models_pytorch as smp
    se = config.ENCODER
    try:
        config.ENCODER = "resnet18"
        calls = {}
        real = smp.encoders.get_encoder          # bound BEFORE the patch, or it recurses

        def fake_get_encoder(name, in_channels=3, depth=5, weights=None, **kw):
            calls["args"] = (name, in_channels, depth, weights)
            return real(name, in_channels=in_channels, depth=depth, weights=None)
        monkeypatch.setattr(smp.encoders, "get_encoder", fake_get_encoder)
        m = _build("resnet18", in_ch=in_ch)
        before = m.decoder.state_dict()
        before = {k: v.clone() for k, v in before.items()}
        info = ckpt.load_imagenet_encoder(m)
        assert calls["args"] == ("resnet18", 3, 5, config.ENCODER_FALLBACK_WEIGHTS)
        assert info["encoder"] == "resnet18" and info["encoder_params"] > 0
        # decoder untouched (random start preserved)
        after = m.decoder.state_dict()
        assert all(torch.equal(before[k], after[k]) for k in before)
        if in_ch == 4:
            w = m.encoder.conv1.weight
            assert tuple(w.shape)[1] == 4
            assert torch.count_nonzero(w[:, 3]) == 0, "extra channel must be zero-init"
    finally:
        config.ENCODER = se


def test_imagenet_load_refuses_a_wrong_encoder(monkeypatch):
    """If the factory hands back the wrong architecture the keys do not fit and the
    load must STOP — unexpected keys are never allowed."""
    import segmentation_models_pytorch as smp
    se = config.ENCODER
    try:
        config.ENCODER = "resnet18"
        real = smp.encoders.get_encoder
        monkeypatch.setattr(
            smp.encoders, "get_encoder",
            lambda name, in_channels=3, depth=5, weights=None, **kw:
                real("resnet34", in_channels=3, depth=5, weights=None))
        m = _build("resnet18")
        with pytest.raises(SystemExit):
            ckpt.load_imagenet_encoder(m)
    finally:
        config.ENCODER = se


def test_encoder_and_warm_start_are_stamped_where_a_reader_can_find_them():
    from phase4seg.names import symbol_body
    pkg = SCRIPTS / "pipeline" / "phase4seg"
    ck = symbol_body(pkg, "_save_ckpt_state", "function") or ""
    man = symbol_body(pkg, "_write_run_manifest", "function") or ""
    ev = symbol_body(pkg, "step_evaluate", "function") or ""
    assert ck and man and ev
    for body, where in ((ck, "checkpoint payload"), (man, "run manifest"),
                        (ev, "eval row")):
        assert '"encoder"' in body, f"the {where} does not record the encoder"
        assert '"warm_start"' in body, f"the {where} does not record the warm start"
    # and the manifest reads the LIVE value, never the star-imported constant
    assert "config.ENCODER" in man and '"encoder": ENCODER' not in man


def test_encoder_does_not_invalidate_the_tile_cache():
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_tile_signature")
    body = ast.get_source_segment(src, fn) or ""
    for name in ("ENCODER", "WARM_START", "P3_CKPT_ENCODER"):
        assert name not in body, f"{name} leaked into _tile_signature"


def test_no_builder_still_reads_a_frozen_encoder_constant():
    """ckpt.py must not import ENCODER as a name — that is the bug this flag fixes."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "ckpt.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "phase4seg.config":
            assert "ENCODER" not in {a.name for a in node.names}, (
                "ckpt.py imports ENCODER as a constant — builders would ignore --encoder")


def test_cli_accepts_the_flag_and_rejects_an_unknown_encoder(monkeypatch, capsys):
    """Parse-only, in-process, the way phase4seg_preflight.py drives `--check` (the
    shim itself is Colab-only: it forces the fork start method)."""
    import sys
    from phase4seg import cli
    base = ["phase4_semantic_finetune.py", "--year", "2011s", "--step", "train",
            "--force-citywide", "--no-hillshade", "--run-tag", "t_enc", "--check"]
    monkeypatch.setattr(sys, "argv", base + ["--encoder", "resnet18"])
    cli.main()
    assert "arguments parsed OK" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", base + ["--encoder", "vgg16"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
