"""--overrides: the R&D overlay and its re-tile guard. Repo-only, no torch."""

import pytest

from phase4seg import config
from phase4seg.overrides import apply_overrides, prescan_argv, signature_constants


def _yaml(tmp_path, text):
    p = tmp_path / "ov.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_signature_constants_are_derived_not_restated():
    """The guard set comes from tiling._tile_signature's AST at call time, so a
    constant added to the signature is guarded the same day, with no list to rot."""
    sig = signature_constants()
    assert {"TILE_SIZE", "RANDOM_SEED", "USE_HILLSHADE", "HS_SOURCE"} <= sig
    assert len(sig) >= 10, f"suspiciously small signature set: {sorted(sig)}"


def test_unknown_key_is_a_typo_not_a_new_constant(tmp_path):
    with pytest.raises(SystemExit, match="typo"):
        apply_overrides(_yaml(tmp_path, "BCE_WIEGHT: 2.0"))


def test_signature_member_is_refused_without_force(tmp_path):
    with pytest.raises(SystemExit, match="_tile_signature"):
        apply_overrides(_yaml(tmp_path, "USE_HILLSHADE: true"))


def test_signature_member_is_allowed_with_force(tmp_path):
    old = config.USE_HILLSHADE
    try:
        got = apply_overrides(_yaml(tmp_path, f"USE_HILLSHADE: {str(not old).lower()}"),
                              force_retile=True)
        assert got == {"USE_HILLSHADE": (not old)}
        assert config.USE_HILLSHADE is (not old)
    finally:
        config.USE_HILLSHADE = old
        config.OVERRIDES_APPLIED = None


def test_type_mismatch_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="float"):
        apply_overrides(_yaml(tmp_path, 'BCE_WEIGHT: "high"'))


def test_bool_is_not_a_number(tmp_path):
    """YAML true would happily land in a float constant via isinstance(int) — refuse."""
    with pytest.raises(SystemExit):
        apply_overrides(_yaml(tmp_path, "BCE_WEIGHT: true"))


def test_valid_override_applies_and_is_recorded(tmp_path):
    old = config.BCE_WEIGHT
    try:
        got = apply_overrides(_yaml(tmp_path, f"BCE_WEIGHT: {float(old) * 2}"))
        assert config.BCE_WEIGHT == float(old) * 2
        assert config.OVERRIDES_APPLIED == got, "the manifest source must match"
    finally:
        config.BCE_WEIGHT = old
        config.OVERRIDES_APPLIED = None


def test_prescan_pops_its_flags_and_keeps_the_rest(tmp_path):
    old = config.BCE_WEIGHT
    p = _yaml(tmp_path, f"BCE_WEIGHT: {float(old) * 3}")
    try:
        rest = prescan_argv(["--year", "2019n", "--overrides", p, "--step", "train"])
        assert rest == ["--year", "2019n", "--step", "train"]
        assert config.BCE_WEIGHT == float(old) * 3
        rest2 = prescan_argv([f"--overrides={p}", "--dry-run"])
        assert rest2 == ["--dry-run"]
    finally:
        config.BCE_WEIGHT = old
        config.OVERRIDES_APPLIED = None


def test_force_without_overrides_is_refused():
    with pytest.raises(SystemExit, match="does nothing"):
        prescan_argv(["--force-retile-overrides", "--year", "2019n"])
