"""Who pays for the training-site footprint discovery, and when it happens at all.

WHY THIS EXISTS (measured, not hypothetical).

`cli.py::main` used to call `common.py::discover_site_footprints` for ANY
invocation containing `labels` or `tile`, before the per-year loop and therefore
before any StepLogger existed. That call globs PHOTOS_DIR on the lake and loads
every training site's crown layer (`load_site_crowns` -> `preprocess_crowns`).

  · 2026-09-07 pilot: the labels step logged `elapsed: 0.0s` INSIDE StepLogger
    and still cost 6.8 queue-minutes; the tile step ran ~9 min before its marker
    opened.
  · 2026-09-08 validation (CPU runtime spdvc1): the labels engine process was
    walking "Forest_1 4118 crowns [REVIEW: 4118 approved, interval-tagged]" with
    the queue's marker still in phase "launching".

Under the citywide 2020-mask recipe — which is what every queue job runs, via
`--force-citywide` — none of that work is used by the labels step at all:
`labels.py::step_labels` returns at its "Label projection — SKIPPED" print before
it ever iterates `sites`. `tiling.py::step_tile` DOES use them
(`_gather_citywide_coarse` -> `_negative_site_records` builds the curated
guaranteed-background `force_keep` tiles), so it discovers them itself, inside its
own StepLogger, where the cost is attributed to the step paying it.

WHAT IS GATED HERE.

  a  `_citywide_for` is the ONE home for the recipe decision — the pre-loop guard
     and the per-year loop must ask it, not two copies of the expression.
  b  A citywide-only invocation calls `discover_site_footprints` ZERO times
     (monkeypatched to raise: a single call fails the test loudly).
  c  A site-recipe invocation still calls it EXACTLY ONCE, shared across years —
     the "discover once" property the original comment promised.
  d  `--dry-run` outcomes are unchanged on both recipes.
  e  Source pins on the late discovery inside `step_tile`: it sits after the
     `_existing_tiles_valid` reuse return and is excluded on `dry_run`, so
     neither of those two paths pays for it. Both are real skips —
     `_gather_citywide_coarse` returns before `_negative_site_records` on a dry
     run — and a top-of-function call would have lost them.

The SAVING is UNMEASURED. These tests prove the call is not made; they say nothing
about how many seconds that is worth. That number only exists once a citywide
labels/tile launch reads its own start-up gap.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_cli_site_discovery.py -q
"""
import subprocess
import sys
import types
from pathlib import Path

import pytest

cli = pytest.importorskip("phase4seg.cli")
config = pytest.importorskip("phase4seg.config")
tiling = pytest.importorskip("phase4seg.tiling")

SCRIPTS = Path(__file__).resolve().parent.parent

# Years are DERIVED from the catalog, never typed: CLAUDE.md §2.2 — a restated
# label rots, and the coarse/fine boundary is a config decision.
COARSE_YEAR = next(e["label"] for e in config.YEAR_CATALOG
                   if config.tier_for(e) == "coarse")
FINE_YEAR = next(e["label"] for e in config.YEAR_CATALOG
                 if config.tier_for(e) == "fine")


# ══ harness: run the real cli.main() with every lake path redirected ══════════

class _Calls:
    """What main() actually invoked, and with what `sites`."""

    def __init__(self):
        self.discover = 0
        self.labels = []
        self.tile = []


def _fake_proc(*a, **kw):
    """Stand-in for subprocess.run: `_write_run_manifest` shells out to git,
    nvidia-smi and `pip freeze` (120 s timeout) purely for provenance, and
    swallows every failure. Keeps these tests hermetic and fast."""
    return types.SimpleNamespace(stdout="", stderr="", returncode=1)


def run_cli(monkeypatch, tmp_path, argv, discover_raises=True):
    """Drive `cli.main()` on `argv`, with nothing reaching the data lake.

    Every path main() writes through is a module global on `cli` (star-imported
    from config), so redirecting them here is enough — the conftest lake guard
    exists because patching `BASE` alone is NOT.
    """
    calls = _Calls()

    for name in ("OUT_DIR", "SITE_DIR", "TILE_DIR", "MODELS_DIR", "MASKS_DIR",
                 "EVAL_DIR", "BASE"):
        monkeypatch.setattr(cli, name, tmp_path / name.lower(), raising=False)
    monkeypatch.setattr(cli, "EVAL_CSV", tmp_path / "eval_absent.csv",
                        raising=False)
    monkeypatch.setattr(cli, "MASK_2020", tmp_path / "mask_absent.tif",
                        raising=False)
    monkeypatch.setattr(subprocess, "run", _fake_proc)
    # _record_tilesets re-imports this by attribute at call time; the real one
    # stats the lake's tile dirs.
    monkeypatch.setattr(tiling, "tileset_id", lambda label: None)
    monkeypatch.setattr(cli, "resolve_p3_ckpt", lambda ckpt: None)

    def _discover(site_buffer=0.0):
        calls.discover += 1
        if discover_raises:
            raise AssertionError(
                "discover_site_footprints was called — this invocation runs the "
                "citywide recipe end to end and must not pay for the site "
                "footprint glob + crown load before any StepLogger exists.")
        return [("Negative_Parking", None, None)]

    monkeypatch.setattr(cli, "discover_site_footprints", _discover)
    monkeypatch.setattr(cli, "step_labels",
                        lambda lab, sites, **kw: calls.labels.append(sites))
    monkeypatch.setattr(cli, "step_tile",
                        lambda lab, sites, **kw: calls.tile.append(sites))

    monkeypatch.setattr(sys, "argv", ["phase4_semantic_finetune.py"] + argv)
    cli.main()
    return calls


@pytest.fixture(autouse=True)
def _config_restored():
    """main() assigns ~25 `config.*` attributes directly (cli.py, the block from
    `config.USE_VI = ...` to `config.HONEST_VAL_SPLIT = ...`, plus RUN_ID /
    RUN_YEARS / POSTPROC_FOLLOWS). Without this they leak into every later test
    in the same process."""
    before = dict(vars(config))
    yield
    after = vars(config)
    for k, v in before.items():
        if after.get(k, object()) is not v:
            setattr(config, k, v)
    for k in [k for k in list(after) if k not in before]:
        delattr(config, k)


# ══ a — one home for the recipe decision ═════════════════════════════════════

def _args(**kw):
    base = dict(force_citywide=False, coarse_site_tiling=False,
                anchor_labels=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


@pytest.mark.parametrize("year,kw,expect", [
    (COARSE_YEAR, {}, True),                             # coarse default (Fix 3)
    (FINE_YEAR, {}, False),                              # fine keeps the 6 sites
    (FINE_YEAR, {"force_citywide": True}, True),         # what every queue job uses
    (COARSE_YEAR, {"coarse_site_tiling": True}, False),  # legacy opt-out
    (COARSE_YEAR, {"anchor_labels": True}, False),       # anchor path wins
    (FINE_YEAR, {"force_citywide": True, "anchor_labels": True}, False),
])
def test_citywide_for_is_the_recipe_decision(year, kw, expect):
    assert cli._citywide_for(cli.entry_for(year), _args(**kw)) is expect


def test_the_loop_asks_the_helper_rather_than_recomputing_the_expression():
    """Source pin. Two copies of this predicate is how the pre-loop guard and the
    per-year recipe silently disagree — the guard would skip discovery for a year
    that then took the site path with `sites=None`."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "cli.py").read_text(encoding="utf-8")
    body = src[src.index("def main("):]
    assert body.count("_citywide_for(") == 2, \
        "main() should ask _citywide_for exactly twice: the pre-loop sites guard " \
        "and the per-year recipe"
    assert 'tier_for(e) == "coarse" or args.force_citywide' not in body, \
        "the recipe expression is back inline in main() — it has one home now"


# ══ b — a citywide-only invocation never discovers ═══════════════════════════

def test_citywide_labels_never_discovers_site_footprints(monkeypatch, tmp_path,
                                                         capsys):
    """The measured case: `--step labels` on a coarse year. step_labels returns
    before it reads `sites` at all, so the glob bought nothing."""
    calls = run_cli(monkeypatch, tmp_path, ["--year", COARSE_YEAR, "--step", "labels"])
    assert calls.discover == 0
    assert calls.labels == [None]
    out = capsys.readouterr().out
    assert "NOT discovered up front" in out, \
        "a skipped discovery must SAY it was skipped, and why"


def test_force_citywide_on_a_fine_year_never_discovers(monkeypatch, tmp_path):
    """`--force-citywide` is what every queue job passes, and it moves fine years
    onto the recipe that needs no up-front footprints either."""
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", FINE_YEAR, "--step", "tile", "--force-citywide"])
    assert calls.discover == 0
    assert calls.tile == [None], \
        "step_tile must receive sites=None and discover them itself, inside its " \
        "own StepLogger"


def test_a_citywide_full_pipeline_still_skips_the_up_front_discovery(monkeypatch,
                                                                     tmp_path):
    """labels AND tile in one invocation — still zero, because tile owns its own."""
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", COARSE_YEAR, "--skip-training", "--skip-inference"])
    assert calls.discover == 0
    assert calls.labels == [None] and calls.tile == [None]


def test_a_step_that_reads_no_footprints_never_discovered_them_anyway(monkeypatch,
                                                                      tmp_path,
                                                                      capsys):
    """Guard regression: `--step evaluate` requests neither labels nor tile, so it
    must neither discover NOR print the skip line — the line would be noise on a
    step the decision does not concern."""
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", FINE_YEAR, "--step", "evaluate"])
    assert calls.discover == 0
    assert "NOT discovered up front" not in capsys.readouterr().out


# ══ c — the site recipe still discovers, exactly once ════════════════════════

def test_a_site_recipe_still_discovers_exactly_once(monkeypatch, tmp_path):
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", FINE_YEAR, "--step", "labels"],
                    discover_raises=False)
    assert calls.discover == 1
    assert calls.labels and calls.labels[0] is not None


def test_discovery_is_still_shared_across_years(monkeypatch, tmp_path):
    """"Site footprints are shared across years — discover once." Two fine years,
    labels + tile: still one call, and both steps see the same object."""
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", f"{FINE_YEAR},{COARSE_YEAR}", "--step", "labels",
                     "--coarse-site-tiling"],
                    discover_raises=False)
    assert calls.discover == 1
    assert len(calls.labels) == 2
    assert calls.labels[0] is calls.labels[1]


def test_one_non_citywide_year_in_a_mixed_set_still_discovers(monkeypatch, tmp_path):
    """The guard is `any(not _citywide_for(...))`, deliberately conservative: a
    mixed invocation pays once rather than half-discovering."""
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", f"{COARSE_YEAR},{FINE_YEAR}", "--step", "tile"],
                    discover_raises=False)
    assert calls.discover == 1
    assert all(s is not None for s in calls.tile)


def test_coarse_site_tiling_flips_the_same_year_back_to_discovery(monkeypatch,
                                                                  tmp_path):
    """Isolation: same year, same step — only the recipe flag differs."""
    assert run_cli(monkeypatch, tmp_path,
                   ["--year", COARSE_YEAR, "--step", "tile"]).discover == 0
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", COARSE_YEAR, "--step", "tile",
                     "--coarse-site-tiling"], discover_raises=False)
    assert calls.discover == 1


def test_anchor_labels_still_discovers(monkeypatch, tmp_path):
    """--anchor-labels builds masks from the 2020 prob raster over the SITE crops,
    so it is a site recipe however coarse the year is."""
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", COARSE_YEAR, "--step", "labels", "--anchor-labels"],
                    discover_raises=False)
    assert calls.discover == 1


# ══ d — dry run unaffected ═══════════════════════════════════════════════════

def test_dry_run_citywide_plans_without_discovering(monkeypatch, tmp_path):
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", COARSE_YEAR, "--step", "tile", "--dry-run"])
    assert calls.discover == 0
    assert calls.tile == [None]


def test_dry_run_site_recipe_discovers_exactly_as_before(monkeypatch, tmp_path):
    calls = run_cli(monkeypatch, tmp_path,
                    ["--year", FINE_YEAR, "--step", "tile", "--dry-run"],
                    discover_raises=False)
    assert calls.discover == 1


# ══ e — where the late discovery sits inside step_tile ═══════════════════════

def _step_tile_body():
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    return src[src.index("def step_tile("):]


def test_step_tile_discovers_after_the_reuse_return_and_never_on_a_dry_run():
    """Source pin, because driving the real `step_tile` needs an ortho and would
    mkdir into the lake.

    Two paths must keep paying NOTHING: the `_existing_tiles_valid` reuse hit
    (which returns above) and `--dry-run` (`_gather_citywide_coarse` returns
    before it reaches `_negative_site_records`). A top-of-function call would lose
    both. Order is the whole property, so it is pinned, not described.
    """
    body = _step_tile_body()
    call = body.index("discover_site_footprints(site_buffer=site_buffer)")
    reuse = body.index("REUSED")
    gather = body.index("_gather_citywide_coarse(")
    assert reuse < call < gather, \
        "the late discovery must sit after the tile-reuse return and before the " \
        "citywide gather that consumes it"
    guard = body[body.index("if citywide:", reuse):call]
    assert "sites is None" in guard and "not dry_run" in guard, \
        "the late discovery must be guarded on sites is None AND not dry_run"


def test_the_site_branch_of_step_tile_is_left_alone():
    """The cli guard guarantees `sites` is populated for a site recipe, so the
    non-citywide branch must NOT grow a lazy path of its own — a second discovery
    site is a second thing to keep in step with `_citywide_for`."""
    body = _step_tile_body()
    assert body.count("discover_site_footprints(") == 1
    else_branch = body[body.index("        year_site_dir  = SITE_DIR / label"):]
    assert "discover_site_footprints" not in else_branch


def test_cli_hands_step_tile_the_buffer_the_shared_discovery_would_have_used():
    """Without this, a `--site-buffer N --force-citywide` run would silently tile
    UNBUFFERED negative-site footprints — fewer guaranteed-background tiles than
    the same command produced before."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "cli.py").read_text(encoding="utf-8")
    body = src[src.index("def main("):]
    tile_call = body[body.index("r = step_tile("):]
    assert "site_buffer=args.site_buffer" in tile_call[:tile_call.index(")\n")]
