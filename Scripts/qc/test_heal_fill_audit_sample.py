"""Gates for the fill-side laundering audit's sampler.

THREE THINGS A SAMPLER CAN DO WRONG that no output inspection would reveal, so each is
mutation-tested against a fixture built to make it fire (CLAUDE.md 3.4c — a gate that has
never fired is not known to work):

  1. SILENTLY REWEIGHT an empty or under-populated stratum into its neighbours. The draw
     then looks complete while the design it reports was never executed.
  2. LOSE THE TIER STRATIFICATION, so REVIEW and BLIND — the only tiers where laundering is
     possible — collapse back to their population share and the audit spends its budget
     where the question is not.
  3. DRAW A CONTROL THAT OVERLAPS THE FILLS, which would make the reader's error rate a
     function of the thing it is supposed to control for.

The fixtures are synthetic and live in tmp_path; the lake is never touched (qc/conftest.py).
The one test that reads a real file only reads the repo's tracked manifest header.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_heal_fill_audit_sample.py -q
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")


def _load():
    """By path, not by sys.path insert (ledger: test_status_discovery)."""
    p = SCRIPTS / "qc" / "instruments" / "heal_fill_audit_sample.py"
    spec = importlib.util.spec_from_file_location("_hfas_under_test", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load()


# ── fixtures ──────────────────────────────────────────────────────────────────────

def _blank(h=60, w=60, n=3):
    return np.zeros((n, h, w), dtype=np.uint8)


def _heal_row(**kw):
    r = dict(epoch="2011s", prev="2009", next="2013", tier="HEAL",
             gap_left_yr=2, gap_right_yr=2,
             shift_prev_dx_m=0.0, shift_prev_dy_m=0.0,
             shift_next_dx_m=0.0, shift_next_dy_m=0.0)
    r.update(kw)
    return r


def _identity_shift(mask, dx, dy):
    return mask


def _scene():
    """One fill (absent, both flanks present), one control (absent, ONE flank present),
    and one two-sided absence the overlay does NOT contain — the last exists so the
    `untouched_two_sided` diagnostic has a known-bad input to fire on."""
    stack = _blank()
    inside = np.ones((60, 60), dtype=bool)
    # fill: rows 5-10, cols 5-10  (36 cells = 144 m2 -> d = 13.54 m -> size class 10-14)
    stack[0, 5:11, 5:11] = 1
    stack[2, 5:11, 5:11] = 1
    # control: one flank only
    stack[0, 20:26, 20:26] = 1
    # an unfilled two-sided absence
    stack[0, 40:46, 40:46] = 1
    stack[2, 40:46, 40:46] = 1

    keep = np.zeros((60, 60), dtype=bool)
    keep[5:11, 5:11] = True
    overlays = {"2011s": {"heal": keep, "ignore": np.zeros_like(keep), "tier": "HEAL"}}
    return stack, inside, ["2009", "2011s", "2013"], [_heal_row()], overlays


def _units():
    stack, inside, years, rows, ov = _scene()
    classes = M.size_classes([(0, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 8), (8, 10),
                              (10, 14), (14, 999)])
    return M.collect_units(stack, inside, years, rows, ov, 7, classes, _identity_shift)


def _npz(tmp_path):
    """A stack temporal_heal.build() can actually run on, for the CLI end-to-end."""
    stack, inside, years, _, _ = _scene()
    p = tmp_path / "stack.npz"
    np.savez(p, stack=stack, inside=inside, years=np.array(years),
             transform=np.array([2.0, 0.0, 500000.0, 0.0, -2.0, 5300000.0]))
    return p


# ── 1. the refusal ────────────────────────────────────────────────────────────────

def test_zero_population_stratum_is_refused_not_reweighted():
    """An empty stratum must appear in `refused` and take no points, and the strata
    around it must not grow to absorb its share."""
    keys = [("HEAL", "1-2", "6-8"), ("HEAL", "1-2", "8-10"),
            ("BLIND", "3", "6-8"), ("BLIND", "3", "8-10")]
    pop = {keys[0]: 1000, keys[1]: 1000, keys[2]: 1000, keys[3]: 0}
    alloc, nominal, refused, shortfall = M.allocate(pop, 300, keys)
    assert keys[3] in refused and keys[3] not in alloc
    assert shortfall == 0                      # empty != under-populated
    # the empty stratum's absence must not inflate anyone: shares are population x tier
    w = {k: pop[k] * M.OVERSAMPLE[k[0]] for k in keys[:3]}
    tot = sum(w.values())
    for k in keys[:3]:
        assert alloc[k] == pytest.approx(round(300 * w[k] / tot), abs=1)


def test_under_populated_stratum_is_capped_and_the_shortfall_is_reported():
    """THE MUTATION. A stratum with one unit cannot yield the points the design asks for.
    The honest response is a short draw with a named shortfall; the dishonest one is a
    full-looking draw whose weights no longer match the design."""
    keys = [("HEAL", "1-2", "6-8"), ("HEAL", "1-2", "8-10"), ("BLIND", "3", "6-8")]
    pop = {keys[0]: 1000, keys[1]: 1, keys[2]: 1000}
    alloc, nominal, refused, shortfall = M.allocate(pop, 300, keys)
    assert alloc[keys[1]] == 1
    assert nominal[keys[1]] > 1
    assert shortfall == nominal[keys[1]] - 1
    assert sum(alloc.values()) == 300 - shortfall < 300
    # and the other two are untouched — no top-up
    for k in (keys[0], keys[2]):
        assert alloc[k] == nominal[k]


def test_every_live_stratum_gets_at_least_two_or_its_whole_population():
    """n_h = 1 leaves the within-stratum variance undefined
    (phase4_qc_design_power.py::estimate divides by n_h - 1)."""
    keys = [("HEAL", "1-2", "6-8"), ("HEAL", "1-2", "14+"), ("BLIND", "3", "6-8")]
    pop = {keys[0]: 100000, keys[1]: 3, keys[2]: 100000}
    alloc, _, _, _ = M.allocate(pop, 300, keys)
    for k, n in alloc.items():
        assert n >= min(2, pop[k]), (k, n)


# ── 2. the tier stratification ────────────────────────────────────────────────────

def test_removing_the_tier_oversample_collapses_blind_to_its_base_share(monkeypatch):
    """MUTATION: with the oversample removed, BLIND's allocation must fall to its
    population share. If the two agree, the stratification was never doing anything."""
    keys = [("HEAL", "1-2", "6-8"), ("BLIND", "3", "6-8")]
    pop = {keys[0]: 9000, keys[1]: 1000}

    alloc_on, _, _, _ = M.allocate(pop, 300, keys)
    for t in M.TIERS:
        monkeypatch.setitem(M.OVERSAMPLE, t, 1.0)
    alloc_off, _, _, _ = M.allocate(pop, 300, keys)

    base = 300 * pop[keys[1]] / sum(pop.values())          # 30
    assert alloc_off[keys[1]] == pytest.approx(base, abs=1)
    assert alloc_on[keys[1]] == pytest.approx(300 * 2000 / 11000, abs=1)
    assert alloc_on[keys[1]] > 1.5 * alloc_off[keys[1]]


# ── 3. the control ────────────────────────────────────────────────────────────────

def test_control_units_never_overlap_fill_units():
    """Fills come from `both flanks present`, controls from `exactly one` — disjoint by
    construction. Asserted on the units, because 'by construction' is a claim about code."""
    units, _ = _units()
    fills = {(u["epoch_filled"], u["row"], u["col"]) for u in units if not u["is_control"]}
    ctrls = {(u["epoch_filled"], u["row"], u["col"]) for u in units if u["is_control"]}
    assert fills and ctrls
    assert not (fills & ctrls)
    assert len({u["unit_id"] for u in units}) == len(units)


def test_the_drawn_control_and_fill_samples_are_disjoint():
    units, _ = _units()
    f = M.draw(units, {("HEAL", "1-2", "10-14"): 1}, 1, False)
    c = M.draw(units, {("HEAL", "1-2", "10-14"): 1}, 1, True)
    assert f and c
    assert not ({u["unit_id"] for u in f} & {u["unit_id"] for u in c})


def test_untouched_two_sided_diagnostic_fires_on_a_known_bad_input():
    """The design note's justification for substituting a one-sided control is that the
    literal population is empty. That claim is only worth anything if the counter can be
    non-zero — here it is, because the scene hides a two-sided absence from the overlay."""
    _, diag = _units()
    assert diag["untouched_two_sided"] == 1
    assert diag["per_epoch"][0]["n_untouched_two_sided"] == 1


def test_a_control_carries_the_flank_it_was_drawn_from():
    units, _ = _units()
    ctrl = [u for u in units if u["is_control"]]
    assert ctrl and all(u["control_flank"] in ("prev", "next") for u in ctrl)
    assert all(u["control_flank"] == "" for u in units if not u["is_control"])


# ── geometry and arithmetic ───────────────────────────────────────────────────────

def test_equivalent_diameter_matches_the_crown_polygons_estimator():
    """phase0_instance_seg.py writes diameter_m = 2*sqrt(area/pi); the size bins were
    defined on that column, so the mapping must be the same formula."""
    for cells in (7, 9, 36, 100):
        area = cells * M.CELL_M ** 2
        assert M.equiv_diam_m(cells) == pytest.approx(2 * (area / math.pi) ** 0.5)


def test_the_size_floor_forbids_the_small_bins():
    """28 m2 -> 5.97 m, so no unit can land below the 5-6 bin. The design note states this
    as the reason those strata are empty; if the floor moved, the statement would be false."""
    min_cells = 7
    assert M.equiv_diam_m(min_cells) == pytest.approx(5.9708, abs=1e-3)
    classes = M.size_classes([(0, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 8), (14, 999)])
    assert M.size_class_of(M.equiv_diam_m(min_cells), classes) == "5-6"


def test_gap_bucket_follows_the_tier_rule():
    assert M.gap_bucket_of(1) == "1-2" and M.gap_bucket_of(2) == "1-2"
    assert M.gap_bucket_of(3) == "3"          # temporal_heal.BLIND_GAP_YEARS
    assert M.gap_bucket_of(9) == "4+"


def test_exact_bound_is_the_closed_form_at_k_zero_and_monotone_after():
    assert M.cp_upper(0, 300) == pytest.approx(1 - 0.05 ** (1 / 300))
    assert M.cp_upper(0, 42) == pytest.approx(1 - 0.05 ** (1 / 42))
    prev = 0.0
    for k in range(0, 12):
        ub = M.cp_upper(k, 300)
        assert ub > prev
        prev = ub
    # the k>0 branch must actually solve the binomial CDF, not interpolate
    p = M.cp_upper(3, 300)
    cdf = sum(math.comb(300, i) * p ** i * (1 - p) ** (300 - i) for i in range(4))
    assert cdf == pytest.approx(0.05, abs=1e-4)


def test_stratified_halfwidth_uses_the_n_minus_one_convention():
    alloc = {("HEAL", "1-2", "6-8"): 50, ("BLIND", "3", "6-8"): 50}
    wts = {("HEAL", "1-2", "6-8"): 0.5, ("BLIND", "3", "6-8"): 0.5}
    p = 0.1
    want = M.Z95 * math.sqrt(2 * 0.5 ** 2 * p * (1 - p) / 49)
    assert M.stratified_halfwidth(alloc, wts, p) == pytest.approx(want)
    # a stratum of one contributes no variance rather than dividing by zero
    assert M.stratified_halfwidth({("HEAL", "1-2", "6-8"): 1}, wts, p) == 0.0


# ── end to end ────────────────────────────────────────────────────────────────────

def test_cli_writes_a_manifest_and_a_design_note_to_the_given_paths(tmp_path):
    out = tmp_path / "m.csv"
    note = tmp_path / "d.txt"
    rc = M.main(["--heal", str(_npz(tmp_path)), "--out", str(out),
                 "--design-out", str(note), "--n", "4", "--seed", "1"])
    assert rc == 0
    import csv
    rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
    assert rows and list(rows[0].keys()) == M.COLS
    assert all(r["present_in_filled_epoch"] == "" and r["notes"] == "" for r in rows)
    assert {r["epoch_filled"] for r in rows} == {"2011s"}
    assert {int(r["blind_order"]) for r in rows} == set(range(1, len(rows) + 1))
    body = note.read_text(encoding="utf-8")
    assert "REFUSED" in body and "DETECTABLE EFFECT" in body
    assert "UNDETERMINED" in body


def test_dry_run_writes_nothing(tmp_path):
    out = tmp_path / "m.csv"
    assert M.main(["--heal", str(_npz(tmp_path)), "--out", str(out),
                   "--design-out", str(tmp_path / "d.txt"), "--dry-run"]) == 0
    assert not out.exists()


def test_the_draw_is_deterministic(tmp_path):
    p = _npz(tmp_path)
    a, _, _ = M.build(4, 7, p)
    b, _, _ = M.build(4, 7, p)
    assert [r["unit_id"] for r in a] == [r["unit_id"] for r in b]


# ── the contract ──────────────────────────────────────────────────────────────────

def test_the_real_manifest_columns_match_schemas():
    """SCHEMAS.md is the data contract. If the writer's header and the doc disagree, one
    of them is lying to the next reader."""
    csv_p = REPO / "phase4" / "qc" / "heal_fill_audit_sample.csv"
    doc = (SCRIPTS / "docs" / "SCHEMAS.md").read_text(encoding="utf-8")
    assert "heal_fill_audit_sample.csv" in doc, "the manifest has no SCHEMAS entry"
    block = doc.split("heal_fill_audit_sample.csv", 1)[1].split("\n## ", 1)[0]
    documented = [ln.split("|")[1].strip().strip("`")
                  for ln in block.splitlines()
                  if ln.startswith("| `")]
    assert documented, "the SCHEMAS entry has no column table"
    assert documented == M.COLS, (
        f"SCHEMAS and heal_fill_audit_sample.py::COLS disagree: "
        f"{set(documented) ^ set(M.COLS)}")
    if csv_p.exists():
        header = csv_p.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert header == M.COLS


def test_the_endpoint_bound_is_read_from_the_trailer_not_restated(tmp_path):
    """The 0-of-42 this audit exists to beat lives in heal_vs_gold.py::main's trailer, and
    experiments/heal_infill_2017_2023.yaml is queued to rebuild it on 12 epochs. A constant
    would keep quoting the old pair after the file had moved on."""
    p = tmp_path / "heal_vs_gold.csv"
    p.write_text("point_id,label\n1,loss\n# loss_n,42\n# loss_laundered,0\n",
                 encoding="utf-8")
    assert M.endpoint_bound(p) == (0, 42, pytest.approx(1 - 0.05 ** (1 / 42)))
    # the SAME reader must track a changed file rather than a remembered number
    p.write_text("point_id,label\n# loss_n,90\n# loss_laundered,2\n", encoding="utf-8")
    k, n, b = M.endpoint_bound(p)
    assert (k, n) == (2, 90) and b == pytest.approx(M.cp_upper(2, 90))


def test_a_missing_endpoint_source_reports_rather_than_falling_back(tmp_path):
    """No constant is substituted for an unreadable file — the note says NOT READ."""
    assert M.endpoint_bound(tmp_path / "absent.csv") == (None, None, None)
    p = tmp_path / "no_trailer.csv"
    p.write_text("point_id,label\n1,loss\n", encoding="utf-8")
    assert M.endpoint_bound(p) == (None, None, None)


def test_the_live_endpoint_source_still_carries_the_keys_this_reads():
    """A rename of loss_n / loss_laundered in heal_vs_gold.py must break here, loudly,
    rather than silently degrade the design note to NOT READ."""
    if not M.ENDPOINT_SRC.exists():
        pytest.skip("heal_vs_gold.csv not generated")
    t = M.trailer(M.ENDPOINT_SRC)
    assert "loss_n" in t and "loss_laundered" in t
