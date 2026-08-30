"""Which `config.py` constants force a re-tile? Derived from the source, not remembered.

WHY THIS EXISTS. `pipeline/phase4seg/config.py` is documented as "pure-move protected":
changing a constant can invalidate every cached tile set and cost ~20 min of GPU per
year to rebuild. That rule is stated repeatedly and is treated as covering the whole
file — 128 module-level constants.

It does not. Only the constants that feed `tiling._tile_signature` can invalidate a
cache; the rest are free to change. The asymmetry is roughly 17 against 111, and
NOTHING IN THE FILE SAYS WHICH IS WHICH — the constants are interleaved, and only
tiling.py knows. So the rule is obeyed by treating every constant as untouchable, which
is both more cautious than necessary and, worse, uninformative: a blanket prohibition
gives no signal when someone edits one of the 17 that genuinely matters.

WHY A TEST RATHER THAN A COMMENT. A comment listing the 17 is exactly the kind of
hand-maintained restatement this repo has been correcting all day — it would drift the
first time someone added a key to the signature. This derives the set from
`_tile_signature`'s own source with the AST, so the documented list cannot be wrong for
longer than one test run.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_tile_signature_scope.py -q
"""
import ast
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))

TILING = SCRIPTS / "pipeline" / "phase4seg" / "tiling.py"
CONFIG = SCRIPTS / "pipeline" / "phase4seg" / "config.py"

# The re-tile triggers, as of 2026-08-30. Editing any of these invalidates cached tile
# sets; editing any OTHER config constant does not. Kept here rather than in config.py
# because the test below proves it against the source — a list in a comment could not.
RETILE_TRIGGERS = {
    # unconditional
    "TILE_SIZE", "RANDOM_SEED", "USE_HILLSHADE", "HS_SOURCE", "USE_VI",
    "COARSE_CITYWIDE_TILES", "HARD_NEG_FRACTION", "BACKGROUND_BUDGET_FRACTION",
    "GREEN_GRVI_THRESHOLD", "COARSE_VAL_FRAC", "COARSE_TEST_FRAC",
    "SPATIAL_BLOCK_SIZE_M", "CANOPY_AUTOCORR_M",
    # keyed only when the feature is ON, so turning it off does not invalidate caches
    "ADD_CANOPY_MASK", "SAMPLE_MANIFEST", "AUX_HEIGHT", "CHM_CREDIBLE_YEARS",
}


def _signature_reads():
    """Every UPPERCASE name `_tile_signature` reads, bare or via `config.`."""
    tree = ast.parse(TILING.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_tile_signature")
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "config" and node.attr.isupper():
                names.add(node.attr)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id.isupper() and len(node.id) > 2:
                names.add(node.id)
    return names


def test_the_documented_trigger_set_matches_the_source():
    """If someone adds a key to _tile_signature, this fails and the list above must be
    updated — which is the moment to notice that a new constant now costs a re-tile."""
    actual = _signature_reads()
    missing = actual - RETILE_TRIGGERS
    extra = RETILE_TRIGGERS - actual
    assert not missing, (
        f"_tile_signature now reads {sorted(missing)}, which are NOT documented as "
        f"re-tile triggers. Changing one would silently invalidate every cached tile "
        f"set. Add them to RETILE_TRIGGERS.")
    assert not extra, (
        f"{sorted(extra)} are documented as re-tile triggers but _tile_signature no "
        f"longer reads them — they are now free to change. Remove them.")


def test_the_asymmetry_is_real_and_worth_stating():
    """The point of the exercise: most of config.py is NOT a re-tile trigger, and the
    blanket 'never touch config.py' reading is both over-cautious and uninformative."""
    src = CONFIG.read_text(encoding="utf-8")
    tree = ast.parse(src)
    consts = {t.id for n in tree.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name) and t.id.isupper()}
    assert len(consts) > 100, f"expected ~128 constants, found {len(consts)}"
    triggers = consts & RETILE_TRIGGERS
    assert len(triggers) < len(consts) / 4, (
        f"{len(triggers)} of {len(consts)} constants force a re-tile — the asymmetry "
        f"this test documents. If that ratio ever approaches 1, the blanket rule is "
        f"the right one after all and this test should be deleted.")


def test_every_documented_trigger_actually_exists_in_config():
    """A trigger name that is not a real constant would make the list useless."""
    from phase4seg import config as C
    absent = [n for n in RETILE_TRIGGERS if not hasattr(C, n)]
    assert not absent, f"documented triggers missing from config.py: {sorted(absent)}"


def test_epoch_and_boundary_constants_are_NOT_triggers():
    """Two constants appended on 2026-08-30, both deliberately outside the signature.

    EPOCH marks whether RESULTS are comparable; tiles are inputs, and bumping it must
    not cost a re-tile. BOUNDARY_WEIGHT changes the loss, not the tiles. Getting either
    wrong would attach a ~20 min/year rebuild to a change that does not need one."""
    assert "EPOCH" not in RETILE_TRIGGERS
    assert "BOUNDARY_WEIGHT" not in RETILE_TRIGGERS
    assert "BOUNDARY_IGNORE_BUFFER" not in RETILE_TRIGGERS
    reads = _signature_reads()
    for n in ("EPOCH", "BOUNDARY_WEIGHT", "BOUNDARY_IGNORE_BUFFER"):
        assert n not in reads, f"{n} leaked into _tile_signature — it would force re-tiles"
