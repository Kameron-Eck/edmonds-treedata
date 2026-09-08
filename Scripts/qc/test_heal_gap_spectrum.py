"""Gates for the gap-length spectrum — chiefly, that its kill criterion can FIRE.

WHY THE MUTATION TESTS ARE THE POINT. On the eight-epoch stack `laundered(L)` is zero in
every bucket, and it is zero for a structural reason rather than a virtuous one: a
verified loss's terminal absence runs to the END of the series, so the epoch after any
interior epoch inside it also reads absent and a both-sides fill predicate cannot fire
there. A criterion that reports zero on every input it will ever see is not a gate.
CLAUDE.md 3.4c says so in those words — "a kill criterion must be shown to FIRE on a
known-bad input before it counts as a gate" — so two known-bad inputs are seeded here:

    MUTATION A   a fill landed on a verified loss's terminal absence, inside one chosen
                 L bucket. `laundered(L)` must move 0 -> 1 in THAT bucket and stay 0 in
                 the others. A counter that moved everywhere would be counting fills, not
                 attributing them.
    MUTATION B   a fill landed where the bracket predicate is false. It must be REFUSED
                 from `n_eligible` — the denominator may not grow to accommodate a write
                 nothing licensed — and must be reported in `fills_outside_eligible`,
                 which is 0 on the real run and is the containment check between the
                 healer's own candidate set and what it actually wrote.

Everything runs on synthetic 6x6 stacks in tmp_path. Nothing here touches the lake, and
the two tests that read the real measured CSV skip when it has not been generated.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_heal_gap_spectrum.py -q
"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
REAL_CSV = QC / "heal_gap_spectrum.csv"

np = pytest.importorskip("numpy")


def _load(name, where="instruments"):
    """Load an instrument by file location, leaving `sys.path` alone — see the module's
    own `heal_gap_spectrum.py::_sibling` for why."""
    p = SCRIPTS / "qc" / where / f"{name}.py" if where else SCRIPTS / "qc" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_t_{name}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


HGS = _load("heal_gap_spectrum")

# ---- the synthetic archive -------------------------------------------------------
# Five epochs, three interior brackets, three DISTINCT gap lengths so an attribution
# error cannot hide in a single bucket.
YEARS = ["2009", "2011", "2013", "2016", "2020"]
PREV = ["", "2009", "2011", "2013", ""]
NEXT = ["", "2013", "2016", "2020", ""]
TIERS = ["", "HEAL", "HEAL", "BLIND", ""]
L_OF = [None, 4, 5, 7, None]                 # int(next) - int(prev)
TF = np.array([2.0, 0.0, 0.0, 0.0, -2.0, 100.0])
SHAPE = (6, 6)

LOSS_RC = (1, 1)          # raw 1 1 0 0 0  -> terminal run starts at epoch 2
NC_RC = (2, 2)            # raw 1 0 1 0 1  -> impossible triples at epochs 1 and 3
NC2_RC = (3, 3)           # raw 1 1 1 1 1  -> nothing to fix, a stable control point
FREE_RC = (4, 4)          # absent everywhere, never bracketed: mutation B's target


def _xy(rc):
    """Cell -> a map coordinate safely inside it, inverting
    `heal_gap_spectrum.py::cell_of`."""
    r, c = rc
    return TF[2] + TF[0] * c + 1.0, TF[5] + TF[4] * r - 1.0


def _bundle():
    """Raw stack, its unmodified healed twin, and the bracket predicate that licenses
    fills. `candidate` is derived from the stack exactly as the healer derives it (absent
    at t, canopy on both flanks) so the fixture cannot drift from the thing it models."""
    stack = np.zeros((len(YEARS),) + SHAPE, dtype=np.uint8)
    for i, v in enumerate([1, 1, 0, 0, 0]):
        stack[i][LOSS_RC] = v
    for i, v in enumerate([1, 0, 1, 0, 1]):
        stack[i][NC_RC] = v
    for i in range(len(YEARS)):
        stack[i][NC2_RC] = 1
    cand = np.zeros(stack.shape, dtype=bool)
    for i in range(1, len(YEARS) - 1):
        cand[i] = (stack[i] == 0) & (stack[i - 1] == 1) & (stack[i + 1] == 1)
    return {"years": list(YEARS), "stack": stack, "healed": stack.copy(),
            "candidate": cand, "inside": np.ones(SHAPE, dtype=bool),
            "transform": TF, "tiers": list(TIERS), "prev": list(PREV),
            "next": list(NEXT), "year_int": lambda s: int(str(s)[:4]),
            "crown_raw": None, "crown_healed": None}


def _gold():
    (lx, ly), (nx, ny), (n2x, n2y) = _xy(LOSS_RC), _xy(NC_RC), _xy(NC2_RC)
    return [{"point_id": "L1", "label": "loss", "x": lx, "y": ly},
            {"point_id": "N1", "label": "nochange", "x": nx, "y": ny},
            {"point_id": "N2", "label": "nochange", "x": n2x, "y": n2y}]


def _by_L(rows, kind="spectrum"):
    return {r["L_years"]: r for r in rows if r["row_kind"] == kind}


# ---- baseline --------------------------------------------------------------------

def test_baseline_reports_zero_laundered_with_its_denominators():
    """No fills at all: the harm side is zero, and the two denominators say WHY.

    `laundered_eligible` is positional — a bracket of that L overlaps the terminal
    absence. `laundered_at_risk` is the one with teeth: the bracket predicate actually
    fires at that cell. On a terminal run the second is always zero, which is the finding
    the whole instrument exists to publish.
    """
    rows, meta = HGS.spectrum(_bundle(), _gold(), no_crowns=True)
    by = _by_L(rows)
    assert sorted(by) == [4, 5, 7], "the three synthetic brackets did not bucket apart"
    assert all(r["laundered"] == 0 for r in by.values())
    # the loss's terminal run covers epochs 2 (L=5), 3 (L=7) and the 4 endpoint
    assert by[5]["laundered_eligible"] == 1 and by[7]["laundered_eligible"] == 1
    assert by[4]["laundered_eligible"] == 0
    assert all(r["laundered_at_risk"] == 0 for r in by.values()), (
        "a terminal absence became at-risk — the next epoch inside the run should read "
        "absent and the both-sides predicate should not fire")
    assert meta["off_grid"] == 0


def test_triples_attribute_to_the_bracket_that_could_fix_them():
    """The win side, per bucket. The no-change point flickers at epochs 1 and 3, which
    are two different gap lengths — one number for both would hide that."""
    rows, _ = HGS.spectrum(_bundle(), _gold(), no_crowns=True)
    by = _by_L(rows)
    assert by[4]["triples_present"] == 1 and by[7]["triples_present"] == 1
    assert by[5]["triples_present"] == 0
    assert sum(r["triples_removed"] for r in by.values()) == 0, "nothing was healed"

    b = _bundle()
    b["healed"] = b["stack"].copy()
    b["healed"][1][NC_RC] = 1                      # heal the epoch-1 dropout
    rows2, _ = HGS.spectrum(b, _gold(), no_crowns=True)
    by2 = _by_L(rows2)
    assert by2[4]["triples_removed"] == 1, "the fix was not credited to L=4"
    assert by2[7]["triples_removed"] == 0, "the fix leaked into another bucket"


# ---- MUTATION A: the kill criterion must fire ------------------------------------

def test_mutation_a_seeded_laundering_fires_in_exactly_one_bucket():
    """CLAUDE.md 3.4c: a gate that has never fired is not known to work.

    Land one fill on the verified loss's terminal absence at epoch 2 (L=5) and license it
    in the candidate set, so it reads as a legitimate heal rather than a stray write. The
    count must move 0 -> 1 at L=5 and nowhere else.
    """
    base = _by_L(HGS.spectrum(_bundle(), _gold(), no_crowns=True)[0])
    assert base[5]["laundered"] == 0, "the fixture already launders — nothing to prove"

    b = _bundle()
    b["healed"] = b["stack"].copy()
    b["healed"][2][LOSS_RC] = HGS.HEALED
    b["candidate"][2][LOSS_RC] = True
    by = _by_L(HGS.spectrum(b, _gold(), no_crowns=True)[0])

    assert by[5]["laundered"] == 1, "the seeded laundering was not detected"
    assert by[5]["laundered_points"] == 1
    assert by[5]["laundered_at_risk"] == 1, "at-risk did not follow the licensed fill"
    assert by[4]["laundered"] == 0 and by[7]["laundered"] == 0, (
        "the seeded fill was charged to a bracket that did not make it — the attribution "
        "is counting fills rather than attributing them")
    # and the reported ceiling reacts: 1 of 1 at risk is not a clean bill
    assert by[5]["laundered_rate_ci95_upper"] == 1.0
    assert by[7]["laundered_rate_ci95_upper"] == "", (
        "a bucket with nothing at risk must publish no bound at all, not a small one")


def test_mutation_a_ignore_writes_land_in_censored_not_laundered():
    """Marking a real removal's terminal absence UNKNOWABLE is a different harm from
    filling it, and the two must not be summed. REVIEW and BLIND write 255."""
    b = _bundle()
    b["healed"] = b["stack"].copy()
    b["healed"][3][LOSS_RC] = HGS.HEALED_IGNORE
    b["candidate"][3][LOSS_RC] = True
    by = _by_L(HGS.spectrum(b, _gold(), no_crowns=True)[0])
    assert by[7]["censored"] == 1 and by[7]["laundered"] == 0
    assert by[5]["censored"] == 0


# ---- MUTATION B: an unlicensed fill must be refused, not absorbed ----------------

def test_mutation_b_a_fill_outside_any_bracket_is_refused_from_n_eligible():
    """The denominator may not stretch to cover a write nothing licensed.

    FREE_RC is absent in every epoch, so no bracket contains it and `candidate` is false
    there. Writing canopy anyway must leave `n_eligible` untouched and must surface in
    `fills_outside_eligible` — the positional containment check that reads 0 on the real
    run because the healer only ever writes inside its own candidate set.
    """
    base = _by_L(HGS.spectrum(_bundle(), _gold(), no_crowns=True)[0])
    assert base[4]["fills_outside_eligible"] == 0

    b = _bundle()
    b["healed"] = b["stack"].copy()
    b["healed"][1][FREE_RC] = HGS.HEALED           # candidate[1][FREE_RC] stays False
    by = _by_L(HGS.spectrum(b, _gold(), no_crowns=True)[0])

    assert by[4]["n_eligible"] == base[4]["n_eligible"], (
        "an unbracketed fill was admitted to n_eligible — the fill_rate denominator "
        "now absorbs writes the bracket predicate never licensed")
    assert by[4]["fills_outside_eligible"] == 1, "the unlicensed fill was not flagged"
    assert by[4]["n_fills"] == base[4]["n_fills"] + 1, "the fill itself went uncounted"
    assert by[5]["fills_outside_eligible"] == 0 and by[7]["fills_outside_eligible"] == 0


# ---- the negative control --------------------------------------------------------

def test_negative_control_row_exists_and_shuffles_only_the_labels():
    """Same trajectories, permuted verdicts, fixed seed. The control must be a real row
    computed by the same function — not a constant — and must be reproducible."""
    rows, meta = HGS.spectrum(_bundle(), _gold(), no_crowns=True, seed=7)
    ctrl = [r for r in rows if r["row_kind"] == "negative_control"]
    assert len(ctrl) == 1 and ctrl[0]["L_years"] == meta["median_L"]
    # cell-level columns describe the operator, not the labels: they must be identical
    spec = _by_L(rows)[meta["median_L"]]
    for k in ("n_eligible", "n_fills", "n_fills_canopy", "fills_outside_eligible"):
        assert ctrl[0][k] == spec[k], f"{k} moved when only the gold labels changed"
    again, _ = HGS.spectrum(_bundle(), _gold(), no_crowns=True, seed=7)
    assert again == rows, "the fixed seed did not reproduce"


# ---- shared definitions kept in one home ------------------------------------------

def test_terminal_start_matches_the_definition_heal_vs_gold_uses():
    """Laundering is filling the TERMINAL absence; an earlier dropout at a point cut
    later is the operator working. Conflating them once reported 5 of 42."""
    assert HGS.terminal_start([1, 1, 0, 0, 0]) == 2
    assert HGS.terminal_start([1, 0, 1, 0, 1]) == 5          # ends present: no run
    assert HGS.terminal_start([0, 0, 0]) == 0
    # a no-data epoch stops the walk — a terminal run is asserted absence, never 255
    assert HGS.terminal_start([1, 0, 255, 0, 0]) == 3


def test_states_matrix_agrees_with_the_scalar_ladder():
    """The vectorised ladder must be the SAME ladder as
    `crown_trajectories.py::_state`, including its NaN behaviour: an unobserved crown
    reads UNSURE there because `nan < MIN_VALID_FRAC` is False, and a silent divergence
    would move every crowns_deleted count."""
    ct = _load("crown_trajectories")
    rng = np.random.default_rng(4)
    cov = rng.random((200, 8))
    vf = rng.random((200, 8))
    cov[rng.random(cov.shape) < 0.1] = np.nan
    vf[rng.random(vf.shape) < 0.1] = np.nan
    got = HGS.states_matrix(cov, vf, ct.PRESENT_AT, ct.ABSENT_AT, ct.MIN_VALID_FRAC)
    for i in range(cov.shape[0]):
        for j in range(cov.shape[1]):
            assert got[i, j] == ct._state(cov[i, j], vf[i, j]), (i, j)


def test_crown_boundary_removal_counts_only_what_it_can_attribute():
    """A P A P record carries a validity-interval boundary pair; healing the single
    ABSENT deletes it. A two-epoch run sits in two brackets at once and is counted
    separately rather than charged to a bracket by an arbitrary rule."""
    elig, rem, multi = HGS.crown_boundary_removals(
        ["PAPPP", "PAPPP", "PPAAP", "PPPPP"],
        ["PPPPP", "PAPPP", "PPPPP", "PPPPP"], L_OF)
    assert elig[4] == 2 and rem[4] == 1, "the closed boundary was not attributed to L=4"
    assert multi == 1, "the two-epoch run was not held out of the per-L attribution"
    assert sum(rem.values()) == 1


def test_exact_upper_bound_is_the_zero_event_closed_form():
    """0 of 42 is a 6.9% ceiling, not a zero — and 0 of nothing is not a ceiling."""
    assert HGS.exact_upper_bound(0, 42) == pytest.approx(1 - 0.05 ** (1 / 42), abs=1e-12)
    assert round(HGS.exact_upper_bound(0, 42), 3) == 0.069
    assert HGS.exact_upper_bound(0, 0) is None


# ---- end to end, through the CLI the tests are meant to drive ---------------------

def _write_bundle(path, b):
    np.savez(path, years=np.array(b["years"]), stack=b["stack"], healed=b["healed"],
             candidate=b["candidate"], inside=b["inside"], transform=b["transform"],
             tiers=np.array(b["tiers"]), prev=np.array(b["prev"]),
             next=np.array(b["next"]))


def _write_gold(path, gold):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["point_id", "label", "x", "y"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(gold)


def test_cli_overrides_write_only_where_told(tmp_path):
    """--heal / --gold / --out keep the whole instrument runnable off a synthetic
    archive, which is what makes the mutation tests possible at all. The lake and the
    tracked measured CSV must be untouched by a test run."""
    bpath, gpath, opath = (tmp_path / "b.npz", tmp_path / "g.csv", tmp_path / "o.csv")
    _write_bundle(bpath, _bundle())
    _write_gold(gpath, _gold())
    before = REAL_CSV.read_bytes() if REAL_CSV.exists() else None

    rc = HGS.main(["--heal", str(bpath), "--gold", str(gpath), "--out", str(opath),
                   "--no-crowns"])
    assert rc == 0
    body = [ln for ln in opath.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    rows = list(csv.DictReader(body))
    assert {r["row_kind"] for r in rows} == {"spectrum", "negative_control"}
    assert [r["L_years"] for r in rows if r["row_kind"] == "spectrum"] == ["4", "5", "7"]
    after = REAL_CSV.read_bytes() if REAL_CSV.exists() else None
    assert after == before, "a test run rewrote the tracked measured CSV"


def test_cli_is_deterministic(tmp_path):
    """Two runs, byte-identical. A measured CSV that churns cannot be diffed, and the
    negative control would be unreadable if its draw moved between runs."""
    bpath, gpath = tmp_path / "b.npz", tmp_path / "g.csv"
    _write_bundle(bpath, _bundle())
    _write_gold(gpath, _gold())
    outs = []
    for n in ("a.csv", "b.csv"):
        p = tmp_path / n
        assert HGS.main(["--heal", str(bpath), "--gold", str(gpath), "--out", str(p),
                         "--no-crowns"]) == 0
        outs.append(p.read_bytes())
    assert outs[0] == outs[1]


# ---- the real measured CSV --------------------------------------------------------

def _real_rows():
    if not REAL_CSV.exists():
        pytest.skip("heal_gap_spectrum.csv absent — run "
                    "qc/instruments/heal_gap_spectrum.py")
    body = [ln for ln in REAL_CSV.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    return list(csv.DictReader(body))


def test_real_csv_columns_match_schemas():
    """SCHEMAS.md is the one home for what a column means. A column that exists in the
    file and not in the doc is a fact with no home; one in the doc and not in the file is
    a pointer to nothing."""
    rows = _real_rows()
    doc = (SCRIPTS / "docs" / "SCHEMAS.md").read_text(encoding="utf-8")
    assert "heal_gap_spectrum.csv" in doc, "the writer has no SCHEMAS entry"
    block = doc.split("heal_gap_spectrum.csv", 1)[1].split("\n## ", 1)[0]
    documented = {m.strip("` ") for line in block.splitlines()
                  if line.startswith("| `") for m in [line.split("|")[1]]}
    missing = set(rows[0]) - documented
    extra = documented - set(rows[0])
    assert not missing and not extra, f"missing from SCHEMAS={missing} stale={extra}"


def test_real_csv_agrees_with_heal_vs_gold_on_the_totals_it_shares():
    """Per-L attribution must sum to the aggregate the scorer that owns it published.
    If it does not, the fills are being charged to the wrong brackets and every row in
    this file is wrong in a way no single row would reveal."""
    p = QC / "heal_vs_gold.csv"
    if not p.exists():
        pytest.skip("heal_vs_gold.csv absent")
    tr = HGS._trailer(p)
    rows = [r for r in _real_rows() if r["row_kind"] == "spectrum"]
    assert sum(int(r["triples_present"]) for r in rows) == int(tr["nochange_triples_raw"])
    assert sum(int(r["triples_removed"]) for r in rows) == \
        int(tr["nochange_triples_fixed"])
    assert sum(int(r["laundered"]) for r in rows) == int(tr["loss_laundered"])


def test_real_csv_reports_no_fill_outside_the_healers_own_candidate_set():
    """Containment, positionally. `temporal_heal.py::build` sieves its candidate set and
    writes the survivors, so every write must sit inside it; a non-zero here means the
    reconstruction of that set has drifted and the denominators are not the healer's."""
    rows = [r for r in _real_rows() if r["row_kind"] == "spectrum"]
    assert rows, "no spectrum rows"
    assert all(int(r["fills_outside_eligible"]) == 0 for r in rows)
    for r in rows:
        assert int(r["n_fills"]) <= int(r["n_eligible"])
        assert int(r["crowns_deleted"]) <= int(r["crowns_eligible"])


def test_real_csv_publishes_the_denominator_beside_every_zero():
    """The finding, pinned. Reporting `laundered = 0` without `laundered_at_risk` is the
    defect this instrument exists to fix — and at_risk is itself 0 here, so the file must
    also carry the positional `laundered_eligible` that shows the population was looked
    at rather than missed."""
    rows = [r for r in _real_rows() if r["row_kind"] == "spectrum"]
    assert all("laundered_at_risk" in r for r in rows)
    assert sum(int(r["laundered_eligible"]) for r in rows) > 0, (
        "no verified loss's terminal absence overlaps any bracket — then even the "
        "positional denominator is empty and the file should say so")


# ---- --stack: the healer runs on another stack; the defaults do not move --------------

def test_parser_defaults_are_the_module_constants():
    a = HGS._parser().parse_args([])
    assert a.out == str(HGS.OUT_CSV) and a.gold == str(HGS.GOLD_CSV)
    assert a.stack is None and a.heal is None
    assert HGS.OUT_CSV == REAL_CSV == QC / "heal_gap_spectrum.csv"
    assert a.seed == HGS.SHUFFLE_SEED and not a.dry_run and not a.no_crowns


def _synthetic_stack(path):
    """The temporal_heal fixture: 2013/2015/2016, a 10x10 block dropped at 2015."""
    n = 30
    stack = np.zeros((3, n, n), np.uint8)
    stack[0, 5:15, 5:15] = 1
    stack[2, 5:15, 5:15] = 1
    np.savez(path, stack=stack, inside=np.ones((n, n), bool),
             years=np.array(["2013", "2015", "2016"]),
             transform=np.array([2.0, 0.0, 0.0, 0.0, -2.0, 2.0 * n]))
    return path


def test_stack_override_runs_the_healer_on_that_stack(tmp_path):
    """Through the real path — temporal_heal.build on the override, candidate
    reconstruction and containment both passing — writing only to --out."""
    pytest.importorskip("scipy")
    s = _synthetic_stack(tmp_path / "s.npz")
    # one no-change point inside the dropped block (row 7, col 7 -> a P A P cell) and one
    # verified loss on bare ground; both on-grid
    gold = [{"point_id": "N1", "label": "nochange", "x": 2.0 * 7 + 1.0, "y": 60.0 - 2.0 * 7 - 1.0},
            {"point_id": "L1", "label": "loss", "x": 2.0 * 20 + 1.0, "y": 60.0 - 2.0 * 20 - 1.0}]
    g = tmp_path / "g.csv"
    _write_gold(g, gold)
    o = tmp_path / "o.csv"
    before = REAL_CSV.read_bytes() if REAL_CSV.exists() else None

    bundle, err = HGS.load_bundle(None, stack=s)
    assert err is None and bundle["years"] == ["2013", "2015", "2016"]
    assert bundle["tiers"] == ["", "HEAL", ""] and int(bundle["candidate"][1].sum()) == 100
    assert int((bundle["healed"][1] == HGS.HEALED).sum()) == 100

    rc = HGS.main(["--stack", str(s), "--gold", str(g), "--out", str(o), "--no-crowns"])
    assert rc == 0
    body = [ln for ln in o.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    rows = list(csv.DictReader(body))
    spec = [r for r in rows if r["row_kind"] == "spectrum"]
    assert [r["L_years"] for r in spec] == ["3"] and spec[0]["epochs"] == "2015"
    assert spec[0]["n_fills_canopy"] == "100" and spec[0]["triples_removed"] == "1"
    assert spec[0]["fills_outside_eligible"] == "0"
    assert "# epochs,2013|2015|2016" in o.read_text(encoding="utf-8")
    after = REAL_CSV.read_bytes() if REAL_CSV.exists() else None
    assert after == before, "a --stack run rewrote the tracked measured CSV"


def test_stack_override_lands_on_the_module_instance_the_healer_runs_from(tmp_path):
    """_sibling loads a fresh temporal_heal each call, so setting STACK anywhere but on
    that instance is a no-op — an absent override must surface as ITS error."""
    bundle, err = HGS.load_bundle(None, stack=tmp_path / "absent.npz")
    assert bundle is None and "absent.npz" in err
