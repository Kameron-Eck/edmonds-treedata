"""Gates for the pre-registered crown state model (experiments/crown_state_model.yaml).

Everything here runs on SYNTHETIC observation matrices of non-default shape — no stack, no
crown gpkg, no lake (qc/conftest.py blocks lake writes anyway). What is pinned:

  1. forward-backward is a correct posterior — sums to 1 and matches brute-force
     enumeration over every state path on a 3-epoch toy;
  2. THE PERSISTENCE RULE, mutation-tested: a lone 1 between 0s cannot carry the posterior
     over 0.5, and the SAME input flips to ~0.98 when `persistence=False` removes the rule,
     while 1,1 passes with it on;
  3. a low-recall epoch WIDENS the first-seen interval versus a high-recall one;
  4. --placebo-seed changes the assignment and stamps the provenance;
  5. an unscored arm FAILS LOUDLY unless --allow-missing;
  6. a MISSING observation leaves the posterior identical to having no emission at all;
  7. THE EMISSION GATE (crown_state_model_v2.yaml decision_rule 2), mutation-tested: on a
     synthetic stack whose crown-pooled prevalence far exceeds its pixel prevalence, the
     v1 derivation (--emission-plugin crown) makes f >= r and the gate FIRES; the pixel
     derivation on the SAME stack passes with f < r in every epoch, and the clip that used
     to be silent announces itself on stderr.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_crown_state_model.py -q
"""
from __future__ import annotations

import importlib.util
import itertools
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
np = pytest.importorskip("numpy")


def _load():
    """By path, not by sys.path insert (ledger: test_status_discovery)."""
    p = SCRIPTS / "qc" / "instruments" / "crown_state_model.py"
    spec = importlib.util.spec_from_file_location("_csm_under_test", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load()
PRIOR = np.array([0.9, 0.0, 0.1])


def _fb(obs, rates, **kw):
    kw.setdefault("prior", PRIOR)
    return M.forward_backward(np.asarray(obs, dtype=np.int8), rates, **kw)


# ---------------------------------------------------------------- 1. correctness

def test_forward_backward_matches_brute_force():
    """Five crowns, three epochs — a shape the instrument never runs at, so nothing here
    can pass by accident on the twelve-epoch default."""
    obs = np.array([[1, 0, 1, -1, 0],
                    [0, 0, 1, 1, -1],
                    [1, 1, 0, 1, 0]], dtype=np.int8)
    rates = [(0.8, 0.1), (0.6, 0.2), (0.9, 0.05)]
    q_gain, q_loss = 0.15, 0.25
    post = _fb(obs, rates, q_gain=q_gain, q_loss=q_loss)

    assert np.allclose(post.sum(axis=2), 1.0)

    T = M.transition_matrix(q_gain, q_loss, True)
    B = [M.emission_matrix(obs[e], *rates[e]) for e in range(3)]
    for j in range(obs.shape[1]):
        marg = np.zeros((3, 3))
        for path in itertools.product(range(3), repeat=3):
            wgt = PRIOR[path[0]] * B[0][j, path[0]]
            for e in range(1, 3):
                wgt *= T[path[e - 1], path[e]] * B[e][j, path[e]]
            for e in range(3):
                marg[e, path[e]] += wgt
        marg /= marg.sum(axis=1, keepdims=True)
        assert np.allclose(post[:, j, :], marg, atol=1e-9), j


def test_viterbi_is_the_argmax_path():
    obs = np.array([[0, 1], [1, 1], [1, 0]], dtype=np.int8)
    rates = [(0.9, 0.05)] * 3
    path = M.viterbi(obs, rates, q_gain=0.2, q_loss=0.2, prior=PRIOR)
    T = M.transition_matrix(0.2, 0.2, True)
    B = [M.emission_matrix(obs[e], *rates[e]) for e in range(3)]
    for j in range(obs.shape[1]):
        best, arg = -1.0, None
        for cand in itertools.product(range(3), repeat=3):
            wgt = PRIOR[cand[0]] * B[0][j, cand[0]]
            for e in range(1, 3):
                wgt *= T[cand[e - 1], cand[e]] * B[e][j, cand[e]]
            if wgt > best:
                best, arg = wgt, cand
        assert tuple(int(s) for s in path[:, j]) == arg


# ---------------------------------------------------------------- 2. persistence

# High recall, low false-positive, a generous gain rate and a very high loss rate: the
# regime where a two-state chain would happily accept a one-epoch tree. Verified 2026-09-10
# before the assertions were written — 0.386 with the rule, 0.982 without.
BLIP_KW = dict(q_gain=0.3, q_loss=0.9)
BLIP_RATES = [(0.99, 0.01)] * 3


def test_lone_gain_is_refused_but_two_in_a_row_is_not():
    lone = _fb([[0], [1], [0]], BLIP_RATES, **BLIP_KW)
    assert M.canopy_posterior(lone)[1, 0] < 0.5

    pair = _fb([[0], [1], [1]], BLIP_RATES, **BLIP_KW)
    assert M.canopy_posterior(pair)[1, 0] >= 0.5


def test_removing_the_persistence_rule_flips_the_lone_gain():
    """MUTATION TEST (CLAUDE.md 3.4c): the gate is shown to FIRE. The identical input that
    the rule refuses is accepted with confidence once the rule is switched off, so the
    assertion above is testing the rule and not the emissions."""
    obs = [[0], [1], [0]]
    with_rule = M.canopy_posterior(_fb(obs, BLIP_RATES, persistence=True, **BLIP_KW))[1, 0]
    without = M.canopy_posterior(_fb(obs, BLIP_RATES, persistence=False, **BLIP_KW))[1, 0]
    assert with_rule < 0.5 <= without
    assert without - with_rule > 0.5


# ---------------------------------------------------------------- 3. recall widens

def test_low_recall_epoch_widens_the_first_seen_interval():
    """Five epochs, one crown. The crown is absent early and present at the end; the
    epoch just before the first sighting is scored once at recall .95 and once at .05.
    A survey that cannot see trees may not be read as evidence of absence, so the
    first-seen interval must widen rather than the planting date move."""
    obs = np.array([[0], [0], [0], [1], [1]], dtype=np.int8)
    hi = [(0.95, 0.02)] * 5
    lo = list(hi)
    lo[2] = (0.05, 0.02)
    w = {}
    for name, rr in (("hi", hi), ("lo", lo)):
        pcan = M.canopy_posterior(_fb(obs, rr))
        iv = M.intervals(pcan)
        assert int(iv["first_seen"][0]) == 3
        w[name] = int(iv["first_width"][0])
    assert w["lo"] > w["hi"], w


# ---------------------------------------------------------------- 4. placebo

def test_placebo_seed_permutes_and_is_stamped():
    pairs = [(0.9, 0.01), (0.5, 0.05), (0.2, 0.2), (0.7, 0.02)]
    same, perm0 = M.assign_rates(pairs, None)
    assert same == pairs and perm0 == [0, 1, 2, 3]

    shuffled, perm = M.assign_rates(pairs, 7)
    assert sorted(perm) == [0, 1, 2, 3]
    assert perm != perm0
    assert shuffled == [pairs[i] for i in perm]

    obs = np.array([[0], [1], [1]], dtype=np.int8)
    true_post = M.canopy_posterior(_fb(obs, pairs[:3]))
    fake_post = M.canopy_posterior(_fb(obs, M.assign_rates(pairs[:3], 3)[0]))
    assert not np.allclose(true_post, fake_post)


def test_placebo_provenance_reaches_the_csv():
    res = _tiny_result(placebo_seed=7, permutation=[2, 0, 1])
    text = M.intervals_csv(res)
    assert "# placebo_seed,7" in text
    assert "# permutation,\"[2, 0, 1]\"" in text
    assert "# persistence,1" in text
    clean = M.intervals_csv(_tiny_result())
    assert "# placebo_seed,-1" in clean


def _tiny_result(placebo_seed=-1, permutation=(0, 1, 2)):
    obs = np.array([[0], [1], [1]], dtype=np.int8)
    rates = [(0.9, 0.02)] * 3
    post = M.forward_backward(obs, rates, prior=PRIOR)
    pcan = M.canopy_posterior(post)
    return {
        "years": ["2009", "2013", "2016"], "tags": ["a", "b", "c"], "obs": obs,
        "post_canopy": pcan, "viterbi": M.viterbi(obs, rates, prior=PRIOR),
        "intervals": M.intervals(pcan), "crown_id": np.array(["EDM_0000000"]),
        "placebo_seed": placebo_seed, "permutation": list(permutation),
        "policy": "scored_live", "ref": "ccap_2021_hires_lc.tif",
        "canopy_def": "forest_wetland", "q_gain": 0.02, "q_loss": 0.02,
        "persistence": True, "dropped_tags": [], "stack_path": "synthetic",
        "emission_plugin": "pixel", "pixel_scope": M.PIXEL_SCOPE,
        "pi_grid": np.array([0.2, 0.3, 0.25]),
        "pi_crownpx": np.array([0.4, 0.5, 0.45]),
        "pi_pooled": np.array([0.8, 0.9, 0.85]),
        "f_grid": np.array([0.02, 0.03, 0.04]),
        "f_crownpx": np.array([0.2, 0.3, 0.4]),
        "f_pixel": np.array([0.02, 0.03, 0.04]),
        "f_crown": np.array([0.9, 0.95, 0.99]),
    }


# ---------------------------------------------------------------- 5. missing rates

_HDR = ("curve_id,year,run_tag,ref,canopy_def,eval_scope,policy,recall,precision\n")
_ROW = "c1,2009,trend8_2009,ccap_2021_hires_lc.tif,forest_wetland,,scored_live,0.69,0.78\n"


def _rates_file(tmp_path, extra=""):
    p = tmp_path / "arm_metrics.csv"
    p.write_text(_HDR + _ROW + extra, encoding="utf-8")
    return p


def test_missing_rates_fail_loudly(tmp_path):
    p = _rates_file(tmp_path)
    with pytest.raises(SystemExit) as e:
        M.load_rates(p, ["trend8_2009", "heal_2020", "heal_2022"])
    msg = str(e.value)
    assert "heal_2020" in msg and "heal_2022" in msg
    assert "--allow-missing" in msg


def test_allow_missing_drops_the_epoch(tmp_path):
    p = _rates_file(tmp_path)
    rates, missing = M.load_rates(p, ["trend8_2009", "heal_2020"], allow_missing=True)
    assert missing == ["heal_2020"]
    assert rates["trend8_2009"]["recall"] == pytest.approx(0.69)


def test_ambiguous_rate_rows_are_refused_even_with_allow_missing(tmp_path):
    dup = "c2,2009,trend8_2009,ccap_2021_hires_lc.tif,forest_wetland,,scored_live,0.60,0.90\n"
    p = _rates_file(tmp_path, extra=dup)
    with pytest.raises(SystemExit) as e:
        M.load_rates(p, ["trend8_2009"], allow_missing=True)
    assert "ambiguous" in str(e.value)


def test_rates_ref_switch_selects_a_different_row(tmp_path):
    other = "c3,2009,trend8_2009,ccap_2016_hires_lc.tif,forest_wetland,,scored_live,0.42,0.91\n"
    p = _rates_file(tmp_path, extra=other)
    a, _ = M.load_rates(p, ["trend8_2009"], ref="ccap_2021_hires_lc.tif")
    b, _ = M.load_rates(p, ["trend8_2009"], ref="ccap_2016_hires_lc.tif")
    assert a["trend8_2009"]["recall"] != b["trend8_2009"]["recall"]


# ---------------------------------------------------------------- 6. MISSING is silent

def test_missing_observation_equals_no_emission():
    """A MISSING observation must contribute nothing. Two routes to 'no evidence' —
    obs = MISSING at a rated epoch, and an epoch with no rates at all — must give the
    identical posterior, and both must differ from the same crown observed 0."""
    rates = [(0.85, 0.07)] * 4
    with_missing = _fb([[1, 1], [-1, -1], [1, 1], [0, 0]], rates)
    no_rates = _fb([[1, 1], [0, 1], [1, 1], [0, 0]],
                   [rates[0], None, rates[2], rates[3]])
    assert np.allclose(M.canopy_posterior(with_missing),
                       M.canopy_posterior(no_rates))
    observed_zero = _fb([[1, 1], [0, 0], [1, 1], [0, 0]], rates)
    assert not np.allclose(M.canopy_posterior(with_missing),
                           M.canopy_posterior(observed_zero))


# ---------------------------------------------------------------- emission algebra

def test_emission_fp_inverts_precision():
    r, p_prec, pi = 0.7, 0.8, 0.35
    f = M.emission_fp(r, p_prec, pi)
    back = pi * r / (pi * r + (1 - pi) * f)
    assert back == pytest.approx(p_prec, abs=1e-9)


def test_observations_follow_the_project_ladder():
    """cover >= .50 PRESENT, <= .15 ABSENT, between UNSURE, and a crown with fewer than
    half its cells valid is UNOBSERVED — never 0."""
    ids = np.array([[1, 1, 2, 2], [1, 1, 2, 2], [3, 3, 4, 4], [3, 3, 4, 4]],
                   dtype=np.int32)
    #      crown 1 all canopy   crown 2 all background
    #      crown 3 half canopy/half background (cover .5 -> PRESENT)
    #      crown 4 three of four cells IGNORE (valid frac .25 -> UNOBSERVED)
    epoch = np.array([[1, 1, 0, 0], [1, 1, 0, 0], [1, 1, 255, 255], [0, 0, 255, 1]],
                     dtype=np.uint8)
    obs = M.observations(np.stack([epoch]), ids, 4)
    assert list(obs[0, 1:]) == [1, 0, 1, M.MISSING]


def test_positive_fraction_ignores_missing():
    row = np.array([1, 1, 0, -1, -1, -1], dtype=np.int8)
    assert M.positive_fraction(row) == pytest.approx(2 / 3)


# ---------------------------------------------------------------- 7. the emission gate

# A SYNTHETIC stack of non-default shape: 3 epochs (never 12), a 10x8 lattice, ten crowns
# rasterised as 2x2 blocks. Nine crowns are exactly half canopy — cover 0.50, the PRESENT
# rung — and one is bare, so the crown-POOLED prevalence is 0.9 while only 18 of the 40
# crown-covered cells and 18 of the 80 inside cells are canopy. That gap between the crown
# unit and the pixel unit IS the v1 defect, reproduced in miniature.
GATE_R, GATE_P = 0.7, 0.8
GATE_TAGS = ["synth_a", "synth_b", "synth_c"]


def _gate_stack():
    ids = np.zeros((10, 8), dtype=np.int32)
    k = 0
    for r0 in range(0, 10, 2):
        for c0 in range(0, 8, 2):
            k += 1
            if k <= 10:
                ids[r0:r0 + 2, c0:c0 + 2] = k
    epoch = np.zeros((10, 8), dtype=np.uint8)
    for cid in range(1, 10):                       # crowns 1-9 half canopy, crown 10 bare
        rr, cc = np.nonzero(ids == cid)
        epoch[rr[:2], cc[:2]] = 1
    stack = np.stack([epoch, epoch, epoch])
    inside = np.ones((10, 8), dtype=bool)
    return stack, inside, ids


def _gate_rows(plugin):
    stack, inside, ids = _gate_stack()
    obs = M.observations(stack, ids, 10)[:, 1:]
    pi_grid, pi_crownpx, pi_pooled = M.epoch_prevalences(stack, inside, ids, obs)
    rate_rows = {t: {"recall": GATE_R, "precision": GATE_P} for t in GATE_TAGS}
    return M.derive_emissions(GATE_TAGS, rate_rows, pi_grid, pi_crownpx, pi_pooled,
                              plugin), (pi_grid, pi_crownpx, pi_pooled)


def test_pixel_and_crown_prevalences_are_different_numbers():
    """The plug-ins must actually disagree, or the mutation test below proves nothing."""
    _, (pi_grid, pi_crownpx, pi_pooled) = _gate_rows("pixel")
    assert pi_pooled == pytest.approx([0.9] * 3)          # crowns judged PRESENT
    assert pi_crownpx == pytest.approx([0.45] * 3)        # 18 of 40 crown-covered cells
    assert pi_grid == pytest.approx([0.225] * 3)          # 18 of 80 inside cells


def test_emission_gate_fires_on_the_v1_crown_plugin():
    """MUTATION TEST (CLAUDE.md 3.4c): the gate is SHOWN firing on a known-bad input —
    the v1 derivation this fix replaces. pooled 0.9 with r=.7, p=.8 gives f = 1.575."""
    rows, _ = _gate_rows("crown")
    for row in rows:
        assert row["f_crown"] >= row["r"]
    with pytest.raises(SystemExit) as e:
        M.emission_gate(rows, "crown")
    msg = str(e.value)
    assert "EMISSION GATE: f >= r for epochs" in msg
    for t in GATE_TAGS:
        assert t in msg


def test_emission_gate_passes_on_the_pixel_plugin():
    """The SAME stack, the same rates, only the plug-in unit changed."""
    rows, _ = _gate_rows("pixel")
    for row in rows:
        assert row["f_applied"] < row["r"], row
    assert M.emission_gate(rows, "pixel") is rows


def test_both_plugins_are_reported_side_by_side():
    rows, _ = _gate_rows("pixel")
    for row in rows:
        assert row["f_grid"] == pytest.approx(0.225 * 0.7 * 0.2 / (0.775 * 0.8))
        assert row["f_crownpx"] == pytest.approx(0.45 * 0.7 * 0.2 / (0.55 * 0.8))
        assert row["f_crown"] == pytest.approx(1.0 - M.EPS)      # 1.575, clipped
        assert row["f_pixel"] == pytest.approx(
            row["f_grid"] if M.PIXEL_SCOPE == "grid" else row["f_crownpx"])
    table = M.emission_table(rows, "pixel", ["2009", "2013", "2016"])
    for head in ("pi_grid", "pi_crwnpx", "pi_pooled", "f_grid", "f_crwnpx", "f_crown"):
        assert head in table


def test_the_clip_is_loud(capsys):
    f = M.emission_fp(GATE_R, GATE_P, 0.9, "synth_a")
    assert f == pytest.approx(1.0 - M.EPS)
    err = capsys.readouterr().err
    assert "EMISSION CLIP" in err and "synth_a" in err
    assert "1.575" in err                     # the unclipped value is named, not hidden


def test_the_trailer_carries_every_plugin():
    text = M.intervals_csv(_tiny_result())
    for key in ("# emission_plugin,", "# pixel_scope,", "# pi_grid,", "# pi_crownpx,",
                "# pi_pooled,", "# f_grid,", "# f_crownpx,", "# f_crown,"):
        assert key in text, key


def test_an_unknown_plugin_is_refused():
    with pytest.raises(SystemExit):
        M.derive_emissions(["a"], {}, [0.2], [0.4], [0.8], plugin="whatever")
