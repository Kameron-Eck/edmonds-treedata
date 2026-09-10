r"""crown_state_model.py — per-crown canopy state from measured per-survey detection rates.

PRE-REGISTERED 2026-09-10 in `Scripts/experiments/crown_state_model.yaml`. This file is the
IMPLEMENTATION only; it produces no score against the Panel A gold and writes no verdict.
An independent referee re-runs it and writes `crown_state_vs_gold.csv`.

THE MODEL. The unit is one frozen 2020 crown polygon. Per epoch the crown's canopy cover on
the 2 m stack lattice is reduced to ONE observation by the project's own ladder
(CLAUDE.md 3.8, `build_validity_intervals.py`, `crown_trajectories.py`):

    cover >= 0.50   PRESENT     obs = 1
    cover <= 0.15   ABSENT      obs = 0
    between         UNSURE      MISSING — never assigned to a class
    < 50% of the crown's cells valid that epoch   UNOBSERVED   MISSING

MISSING contributes no emission term, so a crown the survey could not judge neither
supports nor contradicts canopy.

EMISSIONS COME FROM MEASURED RATES, not hand-set tiers. For every epoch the stack's `tags`
array names the arm (trend8_2009, heal_2017, …); the row for that arm in
`phase4/qc/arm_metrics.csv` at the DELIVERED cut (policy scored_live, reference
ccap_2021_hires_lc.tif, canopy_def forest_wetland — the pre-registered primary) gives
recall r_e = P(obs=1 | canopy) and precision p_e. The false-positive rate is DERIVED, not
read:

    p = pi*r / (pi*r + (1-pi)*f)   =>   f = pi*r*(1-p) / ((1-pi)*p)

with pi a plug-in for the true prevalence. THE UNIT OF THAT PLUG-IN IS THE FIX registered
in `crown_state_model_v2.yaml`: v1 inverted a PIXEL-measured precision with a CROWN-POOLED
prevalence (the share of crowns judged PRESENT, 0.80-0.95), which put f >= r in 11 of 12
epochs and collapsed every crown to a constant path. The plug-in is now measured in the
same unit the precision was — PIXELS on that epoch's mask:

    pi_grid      positive fraction over the whole valid inside grid
    pi_crownpx   positive fraction over the valid CROWN-COVERED cells
    pi_pooled    v1's crown-pooled share of PRESENT crowns  (reproducible, never default)

Both pixel figures are reported in the epoch table and the trailer every run;
`--emission-plugin pixel` (the default) uses the population named by `PIXEL_SCOPE` —
measured to be `pi_grid`, the citywide unit the precision itself was scored in; the
constant carries the measurement that rejected `pi_crownpx`.
`--emission-plugin crown` reproduces the v1 derivation and exists ONLY so the gate below
can be shown FIRING on it (CLAUDE.md 3.4c mutation-test rule) — never for a scored run.

THE EMISSION GATE. Before any inference the derived rates are checked: if f_e >= r_e for
ANY rated epoch the model prints the epoch table and REFUSES to run. An observation of
canopy that does not raise P(canopy) is not evidence, and v1 ran twelve such epochs
silently. The clip to 1-EPS that hid it is now a loud warning naming the epoch.

TRANSITIONS. A loss may happen at any step; a gain must PERSIST (the coppice rule). That is
a three-state expanded chain {absent, canopy_new, canopy}:

    absent      -> canopy_new  q_gain      (-> absent 1-q_gain; -> canopy 0)
    canopy_new  -> canopy      1           (canopy_new -> absent is NOT allowed)
    canopy      -> absent      q_loss      (-> canopy 1-q_loss)

canopy_new and canopy emit identically. `--no-persistence` collapses the chain to the
two-state model (absent -> canopy directly) and exists ONLY so the persistence rule can be
mutation-tested: `qc/test_crown_state_model.py` shows the lone-blip assertion flipping when
it is set. It must never be used for a scored run.

Inference is scaled forward-backward (posterior marginals) plus the Viterbi path, both
vectorised over crowns with numpy.

Outputs (repo-side, never the lake):
    phase4/qc/crown_state_posterior.npz   posterior P(canopy) per crown per epoch, the
                                          observations, the Viterbi path, every rate and
                                          parameter, and the provenance stamp
    phase4/qc/crown_state_intervals.csv   per-crown first_seen / last_seen with the
                                          posterior interval width

Run:  py -3.12 qc/instruments/crown_state_model.py --dry-run
      py -3.12 qc/instruments/crown_state_model.py
      py -3.12 qc/instruments/crown_state_model.py --placebo-seed 7
      py -3.12 qc/instruments/crown_state_model.py --dry-run --emission-plugin crown
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

STACK = Path(r"D:\edmonds-pipeline\heal_stack_2m.npz")
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
RATES_CSV = QC / "arm_metrics.csv"
OUT_NPZ = QC / "crown_state_posterior.npz"
OUT_CSV = QC / "crown_state_intervals.csv"

PRESENT_AT = 0.50          # CLAUDE.md 3.8 / build_validity_intervals.py
ABSENT_AT = 0.15
MIN_VALID_FRAC = 0.5       # crown_trajectories.py: half the cells must be valid
ANALYSIS_CRS = "EPSG:26910"

DEFAULT_POLICY = "scored_live"
DEFAULT_REF = "ccap_2021_hires_lc.tif"
DEFAULT_CANOPY_DEF = "forest_wetland"
DEFAULT_Q_LOSS = 0.02
DEFAULT_Q_GAIN = 0.02
PLUGINS = ("pixel", "crown")
DEFAULT_PLUGIN = "pixel"
# WHICH pixel population the `pixel` plug-in measures. decision_rule item (1) permits
# either the crown-covered area or the whole valid grid — "state which, and report both".
# MEASURED 2026-09-10 on the real twelve-epoch stack: pi_crownpx (0.82-0.96) reproduces
# pi_pooled (0.80-0.95) to within 0.02 in every epoch — a crown judged PRESENT is >= 50%
# canopy pixels and ~85% of crowns are PRESENT, so the crown-covered fraction is the
# crown-pooled fraction restated, and it trips the gate below on the same 11 of 12 epochs
# as the v1 defect. GRID is the unit-consistent choice: AMENDMENT (1) of
# crown_state_model.yaml records the precision rows as CITYWIDE scores, and the inversion
# p = pi*r/(pi*r+(1-pi)*f) only holds with p, r, pi and f over ONE population. pi_grid
# (0.245-0.376) reproduces the referee's f = 0.02-0.11 exactly. Flip this to "crownpx"
# for the narrower reading; BOTH columns are reported either way, always.
PIXEL_SCOPE = "grid"
IGNORE = 255               # heal_stack_build.py / detectability_curve.py: 0/1/255

EPS = 1e-6
MISSING = -1

# state indices of the expanded chain
S_ABSENT, S_NEW, S_CANOPY = 0, 1, 2


# --------------------------------------------------------------------------- rates

def _rows(p):
    p = Path(p)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def load_rates(csv_path, tags, policy=DEFAULT_POLICY, ref=DEFAULT_REF,
               canopy_def=DEFAULT_CANOPY_DEF, allow_missing=False):
    """-> (rates, missing). `rates` maps tag -> dict(recall, precision, curve_id, ...).

    FAILS LOUDLY: a tag with no matching row raises unless `allow_missing`; a tag with
    MORE than one matching row always raises, because silently taking the first would let
    an unrelated evaluation scope decide the emission."""
    rows = _rows(csv_path)
    if not rows:
        raise SystemExit(f"FATAL: no rate rows in {csv_path}")
    rates, missing = {}, []
    for tag in tags:
        hit = [r for r in rows
               if r.get("run_tag") == tag and r.get("policy") == policy
               and r.get("ref") == ref and r.get("canopy_def") == canopy_def]
        if len(hit) > 1:
            raise SystemExit(
                f"FATAL: {len(hit)} rows for run_tag={tag} policy={policy} ref={ref} "
                f"canopy_def={canopy_def} — the cut is ambiguous, refusing to pick one")
        if not hit:
            missing.append(tag)
            continue
        r = hit[0]
        try:
            rec, prec = float(r["recall"]), float(r["precision"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"FATAL: unreadable recall/precision for run_tag={tag}")
        rates[tag] = {"recall": rec, "precision": prec,
                      "curve_id": r.get("curve_id", ""), "thresh": r.get("thresh", ""),
                      "population": r.get("population", "")}
    if missing and not allow_missing:
        raise SystemExit(
            "FATAL: no rate row at policy=%s ref=%s canopy_def=%s for: %s\n"
            "       These arms are not scored yet. Score them, or pass --allow-missing "
            "to DROP them from the emission (they become MISSING observations)."
            % (policy, ref, canopy_def, ", ".join(missing)))
    return rates, missing


def emission_fp(recall, precision, pi, label=None):
    """False-positive rate f = P(obs=1 | not canopy), derived from precision and the
    prevalence plug-in pi. The formula is unchanged from v1; what changed is the UNIT of
    pi (see the module docstring) and that a clip is now LOUD, not silent."""
    who = f"epoch {label}: " if label is not None else ""
    if precision <= 0 or pi <= 0:
        return EPS
    if pi >= 1:
        print(f"  ⚠ EMISSION CLIP — {who}prevalence plug-in pi={pi:.6f} >= 1; "
              f"f forced to 1-EPS ({1.0 - EPS:.6f}). The inversion is undefined here.",
              file=sys.stderr)
        return 1.0 - EPS
    f = pi * recall * (1.0 - precision) / ((1.0 - pi) * precision)
    if f >= 1.0 - EPS:
        print(f"  ⚠ EMISSION CLIP — {who}derived f={f:.6f} clipped to "
              f"{1.0 - EPS:.6f} (r={recall:.4f}, p={precision:.4f}, pi={pi:.6f}). "
              f"A false-positive rate at the ceiling is not a rate.", file=sys.stderr)
    elif f <= EPS:
        print(f"  ⚠ EMISSION CLIP — {who}derived f={f:.6g} raised to {EPS:.6g} "
              f"(r={recall:.4f}, p={precision:.4f}, pi={pi:.6f}).", file=sys.stderr)
    return float(min(max(f, EPS), 1.0 - EPS))


def derive_emissions(tags, rate_rows, pi_grid, pi_crownpx, pi_pooled,
                     plugin=DEFAULT_PLUGIN):
    """Pure: -> one row per epoch with both derivations side by side.

    `f_grid` / `f_crownpx` invert the precision with each PIXEL prevalence, `f_crown` with
    the crown-pooled share (the v1 defect, kept reproducible). `f_pixel` is whichever pixel
    population `PIXEL_SCOPE` names — see that constant for the measurement behind it.
    `f_applied` is whichever `plugin` names. Unrated epochs carry None for every rate."""
    if plugin not in PLUGINS:
        raise SystemExit(f"FATAL: --emission-plugin must be one of {sorted(PLUGINS)}")
    rows = []
    for e, t in enumerate(tags):
        rr = rate_rows.get(t)
        row = {"epoch": e, "tag": t,
               "pi_grid": float(pi_grid[e]), "pi_crownpx": float(pi_crownpx[e]),
               "pi_pooled": float(pi_pooled[e]),
               "r": None, "p": None, "f_grid": None, "f_crownpx": None,
               "f_pixel": None, "f_crown": None,
               "f_applied": None, "rated": False}
        if rr is not None:
            r, p = rr["recall"], rr["precision"]
            row["r"], row["p"], row["rated"] = r, p, True
            row["f_grid"] = emission_fp(r, p, float(pi_grid[e]), f"{t}[grid]")
            row["f_crownpx"] = emission_fp(r, p, float(pi_crownpx[e]), f"{t}[crownpx]")
            row["f_pixel"] = (row["f_grid"] if PIXEL_SCOPE == "grid"
                              else row["f_crownpx"])
            row["f_crown"] = emission_fp(r, p, float(pi_pooled[e]), f"{t}[crown]")
            row["f_applied"] = row["f_pixel"] if plugin == "pixel" else row["f_crown"]
        rows.append(row)
    return rows


def emission_table(rows, plugin, years=None):
    """-> the printable epoch table (also the gate's failure message body)."""
    out = [f"  {'epoch':>8}{'tag':>16}{'recall':>9}{'prec':>8}{'pi_grid':>9}"
           f"{'pi_crwnpx':>11}{'pi_pooled':>11}{'f_grid':>9}{'f_crwnpx':>10}"
           f"{'f_crown':>9}{'applied':>10}  gate"]
    for row in rows:
        y = years[row["epoch"]] if years else str(row["epoch"])
        if not row["rated"]:
            out.append(f"  {y:>8}{row['tag']:>16}{'—':>9}{'—':>8}"
                       f"{row['pi_grid']:>9.4f}{row['pi_crownpx']:>11.4f}"
                       f"{row['pi_pooled']:>11.4f}{'—':>9}{'—':>10}{'—':>9}"
                       f"{'—':>10}  NO ROW")
            continue
        ok = row["f_applied"] < row["r"]
        out.append(f"  {y:>8}{row['tag']:>16}{row['r']:>9.4f}{row['p']:>8.4f}"
                   f"{row['pi_grid']:>9.4f}{row['pi_crownpx']:>11.4f}"
                   f"{row['pi_pooled']:>11.4f}{row['f_grid']:>9.4f}"
                   f"{row['f_crownpx']:>10.4f}{row['f_crown']:>9.4f}"
                   f"{row['f_applied']:>10.4f}"
                   f"  {'ok' if ok else 'FIRE  f>=r'}")
    out.append(f"  plug-in in force: {plugin}  (pixel = pi_{PIXEL_SCOPE}, "
               f"crown = v1 pooled)")
    return "\n".join(out)


def emission_gate(rows, plugin, years=None):
    """HARD GATE (decision_rule item 2). Raises SystemExit if f >= r for any rated epoch.

    An observation of canopy under f >= r LOWERS P(canopy); a model with such an emission
    is not measuring anything, so it refuses to run rather than producing a number."""
    bad = [row for row in rows if row["rated"] and row["f_applied"] >= row["r"]]
    if not bad:
        return rows
    names = ", ".join(f"{row['tag']}(f={row['f_applied']:.4f} >= r={row['r']:.4f})"
                      for row in bad)
    raise SystemExit(
        emission_table(rows, plugin, years)
        + f"\n\nEMISSION GATE: f >= r for epochs {names}\n"
          "  The derived false-positive rate is at or above the recall, so an observed\n"
          "  canopy is evidence AGAINST canopy. Refusing to run. This is the v1 defect\n"
          "  (crown_state_model.yaml verdict); --emission-plugin crown reproduces it on\n"
          "  purpose and is never valid for a scored run.")


def assign_rates(pairs, seed=None):
    """`pairs` is the list of (r, f) in epoch order for the RATED epochs. With a seed the
    epoch-to-rate assignment is permuted — kill K3's mechanism. Returns (pairs, perm)."""
    import numpy as np
    n = len(pairs)
    if seed is None:
        return list(pairs), list(range(n))
    perm = np.random.default_rng(int(seed)).permutation(n).tolist()
    return [pairs[i] for i in perm], perm


# --------------------------------------------------------------------------- crowns

def _load_per_crown_cover():
    """Borrow the measured cover reducer from detectability_curve.py by path (no new
    path insert — the ledger in test_status_discovery is a ratchet)."""
    p = SCRIPTS / "qc" / "instruments" / "detectability_curve.py"
    spec = importlib.util.spec_from_file_location("_detect_curve_for_state_model", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.per_crown_cover


def load_crowns(stack_path, crowns_path):
    """Rasterise the frozen 2020 crowns onto THIS stack's lattice.

    Deliberately not `detectability_curve.load()`: that function hard-codes the published
    eight-epoch cache, and this model runs on the twelve-epoch stack."""
    import geopandas as gpd
    import numpy as np
    import rasterio.features
    from affine import Affine

    d = np.load(stack_path)
    stack, inside = d["stack"], d["inside"]
    years = [str(y) for y in d["years"]]
    tags = [str(t) for t in d["tags"]] if "tags" in d.files else list(years)
    tf = Affine(*d["transform"])

    g = gpd.read_file(crowns_path).to_crs(ANALYSIS_CRS)
    g = g[g.geometry.notna() & (g["diameter_m"] > 0)].reset_index(drop=True)
    g["idx"] = range(1, len(g) + 1)
    ids = rasterio.features.rasterize(
        ((geom, i) for geom, i in zip(g.geometry, g["idx"])),
        out_shape=inside.shape, transform=tf, fill=0, dtype="int32")
    return stack, inside, years, tags, g, ids


def observations(stack, ids, n_crowns, per_crown_cover=None):
    """-> int8 (n_epochs, n_crowns+1) of 1 / 0 / MISSING, index 0 unused."""
    import numpy as np
    if per_crown_cover is None:
        per_crown_cover = _load_per_crown_cover()
    cov = np.vstack([per_crown_cover(stack[i], ids, n_crowns, True)
                     for i in range(len(stack))])
    obs = np.full(cov.shape, MISSING, dtype=np.int8)
    fin = np.isfinite(cov)
    obs[fin & (cov >= PRESENT_AT)] = 1
    obs[fin & (cov <= ABSENT_AT)] = 0
    return obs


def pixel_positive_fraction(epoch, where):
    """PIXEL-level positive fraction of one epoch's mask: share of `epoch == 1` among the
    VALID (`!= 255`) cells of `where`. This is the unit the precision was measured in."""
    import numpy as np
    m = np.asarray(where) & (np.asarray(epoch) != IGNORE)
    n = int(m.sum())
    if n == 0:
        return 0.0
    return float(np.count_nonzero(np.asarray(epoch)[m] == 1) / n)


def epoch_prevalences(stack, inside, ids, obs):
    """-> (pi_grid, pi_crownpx, pi_pooled), one value per epoch.

    pi_grid    pixels: whole valid inside grid
    pi_crownpx pixels: valid cells covered by a 2020 crown (the crown rasterisation the
               model already builds is reused — no second pass over the polygons)
    pi_pooled  crowns: the v1 plug-in, share of crowns this epoch judged PRESENT"""
    import numpy as np
    inside = np.asarray(inside).astype(bool)
    crown_px = inside & (np.asarray(ids) > 0)
    pi_grid = np.array([pixel_positive_fraction(stack[e], inside)
                        for e in range(len(stack))])
    pi_crownpx = np.array([pixel_positive_fraction(stack[e], crown_px)
                           for e in range(len(stack))])
    pi_pooled = np.array([positive_fraction(obs[e]) for e in range(obs.shape[0])])
    return pi_grid, pi_crownpx, pi_pooled


def positive_fraction(obs_row):
    """pi_e — share of crowns this epoch OBSERVED as 1, among those it judged at all."""
    import numpy as np
    judged = obs_row != MISSING
    n = int(judged.sum())
    if n == 0:
        return 0.0
    return float(np.count_nonzero(obs_row[judged] == 1) / n)


# --------------------------------------------------------------------------- the chain

def transition_matrix(q_gain, q_loss, persistence=True):
    """Rows are from-states, columns to-states, order (absent, canopy_new, canopy)."""
    import numpy as np
    T = np.zeros((3, 3), dtype=float)
    if persistence:
        T[S_ABSENT] = [1.0 - q_gain, q_gain, 0.0]
        T[S_NEW] = [0.0, 0.0, 1.0]                 # forced: the gain must persist
    else:
        # MUTATION SWITCH ONLY. Two-state collapse: a gain may vanish the next step.
        T[S_ABSENT] = [1.0 - q_gain, 0.0, q_gain]
        T[S_NEW] = [q_loss, 0.0, 1.0 - q_loss]
    T[S_CANOPY] = [q_loss, 0.0, 1.0 - q_loss]
    return T


def emission_matrix(obs, r_e, f_e):
    """P(obs_e | state) per crown, shape (n_crowns, 3). MISSING emits 1 everywhere."""
    import numpy as np
    n = obs.shape[0]
    B = np.ones((n, 3), dtype=float)
    one = obs == 1
    zero = obs == 0
    B[one, S_ABSENT] = f_e
    B[one, S_NEW] = r_e
    B[one, S_CANOPY] = r_e
    B[zero, S_ABSENT] = 1.0 - f_e
    B[zero, S_NEW] = 1.0 - r_e
    B[zero, S_CANOPY] = 1.0 - r_e
    return B


def forward_backward(obs, rates, q_gain=DEFAULT_Q_GAIN, q_loss=DEFAULT_Q_LOSS,
                     prior=None, persistence=True):
    """obs (E, N) of 1/0/MISSING; `rates` a list of E (r_e, f_e) pairs, or None for an
    epoch with no rates (that epoch contributes no emission at all).

    -> posterior (E, N, 3), scaled, each crown-epoch summing to 1."""
    import numpy as np
    obs = np.asarray(obs)
    E, N = obs.shape
    T = transition_matrix(q_gain, q_loss, persistence)
    if prior is None:
        pi0 = positive_fraction(obs[0])
        prior = np.array([1.0 - pi0, 0.0, pi0], dtype=float)
    prior = np.asarray(prior, dtype=float)

    B = []
    for e in range(E):
        if rates[e] is None:
            B.append(np.ones((N, 3), dtype=float))
        else:
            B.append(emission_matrix(obs[e], rates[e][0], rates[e][1]))

    alpha = np.empty((E, N, 3))
    a = prior[None, :] * B[0]
    a /= np.maximum(a.sum(1, keepdims=True), EPS)
    alpha[0] = a
    for e in range(1, E):
        a = (a @ T) * B[e]
        a /= np.maximum(a.sum(1, keepdims=True), EPS)
        alpha[e] = a

    beta = np.empty((E, N, 3))
    beta[E - 1] = 1.0
    for e in range(E - 2, -1, -1):
        b = (beta[e + 1] * B[e + 1]) @ T.T
        b /= np.maximum(b.sum(1, keepdims=True), EPS)
        beta[e] = b

    post = alpha * beta
    post /= np.maximum(post.sum(2, keepdims=True), EPS)
    return post


def viterbi(obs, rates, q_gain=DEFAULT_Q_GAIN, q_loss=DEFAULT_Q_LOSS,
            prior=None, persistence=True):
    """-> int8 (E, N) of state indices."""
    import numpy as np
    obs = np.asarray(obs)
    E, N = obs.shape
    T = transition_matrix(q_gain, q_loss, persistence)
    if prior is None:
        pi0 = positive_fraction(obs[0])
        prior = np.array([1.0 - pi0, 0.0, pi0], dtype=float)
    lT = np.log(np.maximum(np.asarray(T, dtype=float), EPS))

    def lB(e):
        if rates[e] is None:
            return np.zeros((N, 3))
        return np.log(np.maximum(emission_matrix(obs[e], rates[e][0], rates[e][1]), EPS))

    d = np.log(np.maximum(np.asarray(prior, dtype=float), EPS))[None, :] + lB(0)
    back = np.zeros((E, N, 3), dtype=np.int8)
    for e in range(1, E):
        cand = d[:, :, None] + lT[None, :, :]        # (N, from, to)
        back[e] = np.argmax(cand, axis=1)
        d = np.max(cand, axis=1) + lB(e)
    path = np.zeros((E, N), dtype=np.int8)
    path[E - 1] = np.argmax(d, axis=1)
    for e in range(E - 1, 0, -1):
        path[e - 1] = back[e][np.arange(N), path[e]]
    return path


def canopy_posterior(post):
    """P(canopy) = P(canopy_new) + P(canopy)."""
    return post[:, :, S_NEW] + post[:, :, S_CANOPY]


def intervals(pcan):
    """first_seen / last_seen with the posterior interval, on the project's own ladder.

    The literal 'last epoch below 0.5 before first_seen' is first_seen-1 by construction
    and has no width, so the bound uses the 0.15 rung: the interval runs from the last
    epoch the posterior CONFIDENTLY calls absent to first_seen. Symmetric at the tail.

    -> dict of arrays over crowns."""
    import numpy as np
    E, N = pcan.shape
    seen = pcan >= PRESENT_AT
    absent = pcan <= ABSENT_AT
    any_seen = seen.any(axis=0)
    idx = np.arange(E)[:, None]

    first = np.where(any_seen, np.argmax(seen, axis=0), -1)
    last = np.where(any_seen, E - 1 - np.argmax(seen[::-1], axis=0), -1)

    before = absent & (idx < first[None, :])
    lo = np.where(before.any(axis=0), E - 1 - np.argmax(before[::-1], axis=0), -1)
    after = absent & (idx > last[None, :])
    hi = np.where(after.any(axis=0), np.argmax(after, axis=0), E)

    fw = np.where(any_seen, first - lo, -1)
    lw = np.where(any_seen, hi - last, -1)
    return {"first_seen": first, "last_seen": last,
            "first_lo": np.where(any_seen, lo, -1),
            "last_hi": np.where(any_seen, hi, -1),
            "first_width": fw, "last_width": lw}


# --------------------------------------------------------------------------- driver

def build(stack=None, crowns=None, rates_csv=None, policy=DEFAULT_POLICY,
          ref=DEFAULT_REF, canopy_def=DEFAULT_CANOPY_DEF, q_gain=DEFAULT_Q_GAIN,
          q_loss=DEFAULT_Q_LOSS, placebo_seed=None, allow_missing=False,
          persistence=True, plugin=DEFAULT_PLUGIN, quiet=False):
    """-> (result dict, error string). Rates are resolved BEFORE the crowns are
    rasterised, so a missing arm fails in a second rather than after a two-minute burn."""
    import numpy as np
    stack_path = Path(stack) if stack is not None else STACK
    crowns_path = Path(crowns) if crowns is not None else CROWNS
    if not stack_path.exists():
        return None, f"{stack_path} not found (local cache)"
    if not crowns_path.exists():
        return None, f"{crowns_path} not found (local mirror)"

    d = np.load(stack_path)
    tags = [str(t) for t in d["tags"]]
    rates_path = Path(rates_csv) if rates_csv is not None else RATES_CSV
    rate_rows, missing = load_rates(rates_path, tags, policy, ref, canopy_def,
                                    allow_missing)

    stack_arr, inside, years, tags, g, ids = load_crowns(stack_path, crowns_path)
    n = len(g)
    obs = observations(stack_arr, ids, n)[:, 1:]          # drop the unused id-0 column

    pi_grid, pi_crownpx, pi_pooled = epoch_prevalences(stack_arr, inside, ids, obs)
    erows = derive_emissions(tags, rate_rows, pi_grid, pi_crownpx, pi_pooled, plugin)

    # THE GATE runs on the TRUE per-tag pairs, BEFORE any placebo permutation, so
    # --placebo-seed can never route around it.
    emission_gate(erows, plugin, years)
    if not quiet:
        print(emission_table(erows, plugin, years))

    _pi_key = (("pi_grid" if PIXEL_SCOPE == "grid" else "pi_crownpx")
               if plugin == "pixel" else "pi_pooled")
    pi = np.array([erows[e][_pi_key] for e in range(len(tags))])
    rated_ix = [e for e, t in enumerate(tags) if t in rate_rows]
    pairs = [(erows[e]["r"], erows[e]["f_applied"]) for e in rated_ix]
    pairs, perm = assign_rates(pairs, placebo_seed)

    rates = [None] * len(tags)
    for slot, e in enumerate(rated_ix):
        rates[e] = pairs[slot]

    # The prior is a CROWN-state prior and stays on the crown-pooled fraction, exactly as
    # in v1 — only the emission plug-in changed.
    p0 = float(pi_pooled[0])
    prior = np.array([1.0 - p0, 0.0, p0])
    post = forward_backward(obs, rates, q_gain, q_loss, prior, persistence)
    path = viterbi(obs, rates, q_gain, q_loss, prior, persistence)
    pcan = canopy_posterior(post)
    iv = intervals(pcan)

    # r/f are the APPLIED rates (permuted under placebo); r_true/f_true stay with their
    # own tag, so a referee can join the two through `permutation`.
    def _col(key):
        return np.array([np.nan if row[key] is None else row[key] for row in erows])

    r_true = _col("r")
    f_true = _col("f_applied")
    r_arr = np.array([rates[e][0] if rates[e] else np.nan for e in range(len(tags))])
    f_arr = np.array([rates[e][1] if rates[e] else np.nan for e in range(len(tags))])
    p_arr = np.array([rate_rows[t]["precision"] if t in rate_rows else np.nan
                      for t in tags])
    return {
        "years": years, "tags": tags, "obs": obs, "post_canopy": pcan,
        "post": post, "viterbi": path, "intervals": iv,
        "crown_id": g["crown_id"].to_numpy().astype(str),
        "r": r_arr, "f": f_arr, "r_true": r_true, "f_true": f_true, "p": p_arr, "pi": pi,
        "pi_grid": pi_grid, "pi_crownpx": pi_crownpx, "pi_pooled": pi_pooled,
        "f_pixel": _col("f_pixel"), "f_crown": _col("f_crown"),
        "f_grid": _col("f_grid"), "f_crownpx": _col("f_crownpx"),
        "pixel_scope": PIXEL_SCOPE,
        "emission_plugin": plugin, "emission_rows": erows,
        "curve_ids": np.array([rate_rows.get(t, {}).get("curve_id", "") for t in tags]),
        "rated_tags": [tags[e] for e in rated_ix], "dropped_tags": missing,
        "permutation": perm, "placebo_seed": -1 if placebo_seed is None else int(placebo_seed),
        "q_gain": q_gain, "q_loss": q_loss, "prior": prior,
        "policy": policy, "ref": ref, "canopy_def": canopy_def,
        "persistence": persistence, "n_crowns": n,
        "stack_path": str(stack_path), "crowns_path": str(crowns_path),
        "rates_csv": str(rates_path),
    }, None


def intervals_csv(res):
    import numpy as np
    yrs = res["years"]
    iv = res["intervals"]

    def yr(i):
        return yrs[i] if 0 <= i < len(yrs) else ""

    cols = ["crown_id", "crown_idx", "n_observed", "first_seen_idx", "first_seen_year",
            "first_lo_idx", "first_lo_year", "first_seen_width", "last_seen_idx",
            "last_seen_year", "last_hi_idx", "last_hi_year", "last_seen_width",
            "obs_pattern", "posterior_pattern", "viterbi_pattern"]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    obs, pcan, vit = res["obs"], res["post_canopy"], res["viterbi"]
    nobs = (obs != MISSING).sum(axis=0)
    for j, cid in enumerate(res["crown_id"]):
        w.writerow({
            "crown_id": cid, "crown_idx": j + 1, "n_observed": int(nobs[j]),
            "first_seen_idx": int(iv["first_seen"][j]),
            "first_seen_year": yr(int(iv["first_seen"][j])),
            "first_lo_idx": int(iv["first_lo"][j]),
            "first_lo_year": yr(int(iv["first_lo"][j])),
            "first_seen_width": int(iv["first_width"][j]),
            "last_seen_idx": int(iv["last_seen"][j]),
            "last_seen_year": yr(int(iv["last_seen"][j])),
            "last_hi_idx": int(iv["last_hi"][j]),
            "last_hi_year": yr(int(iv["last_hi"][j])),
            "last_seen_width": int(iv["last_width"][j]),
            "obs_pattern": "".join("C" if v == 1 else ("." if v == 0 else "x")
                                   for v in obs[:, j]),
            "posterior_pattern": "".join(
                "C" if v >= PRESENT_AT else ("." if v <= ABSENT_AT else "?")
                for v in pcan[:, j]),
            "viterbi_pattern": "".join("ANC"[s] for s in vit[:, j]),
        })
    buf.write(f"# placebo_seed,{res['placebo_seed']}\n")
    buf.write(f"# permutation,\"{res['permutation']}\"\n")
    buf.write(f"# policy,{res['policy']}\n# ref,{res['ref']}\n")
    buf.write(f"# canopy_def,{res['canopy_def']}\n")
    buf.write(f"# q_gain,{res['q_gain']}\n# q_loss,{res['q_loss']}\n")
    buf.write(f"# persistence,{int(res['persistence'])}\n")
    buf.write(f"# dropped_tags,\"{','.join(res['dropped_tags'])}\"\n")

    def _vec(key):
        return ",".join("" if v is None or (isinstance(v, float) and np.isnan(v))
                        else f"{float(v):.6f}" for v in res.get(key, []))

    buf.write(f"# emission_plugin,{res.get('emission_plugin', DEFAULT_PLUGIN)}\n")
    buf.write(f"# pi_grid,\"{_vec('pi_grid')}\"\n")
    buf.write(f"# pi_crownpx,\"{_vec('pi_crownpx')}\"\n")
    buf.write(f"# pi_pooled,\"{_vec('pi_pooled')}\"\n")
    buf.write(f"# pixel_scope,{res.get('pixel_scope', PIXEL_SCOPE)}\n")
    buf.write(f"# f_grid,\"{_vec('f_grid')}\"\n")
    buf.write(f"# f_crownpx,\"{_vec('f_crownpx')}\"\n")
    buf.write(f"# f_pixel,\"{_vec('f_pixel')}\"\n")
    buf.write(f"# f_crown,\"{_vec('f_crown')}\"\n")
    buf.write(f"# stack,{res['stack_path']}\n")
    _ = np
    return buf.getvalue()


def _parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=str(STACK),
                    help="epoch stack (default: the twelve-epoch local cache)")
    ap.add_argument("--crowns", default=str(CROWNS),
                    help="frozen 2020 crown polygons")
    ap.add_argument("--rates-csv", default=str(RATES_CSV),
                    help="measured precision/recall table (default: phase4/qc/arm_metrics.csv)")
    ap.add_argument("--rates-ref", default=DEFAULT_REF,
                    help="reference filter for the rate rows (K4 uses ccap_2016_hires_lc.tif)")
    ap.add_argument("--policy", default=DEFAULT_POLICY,
                    help="cut policy of the rate rows; the stack holds DELIVERED masks, so "
                         "the default is scored_live — override explicitly, never silently")
    ap.add_argument("--canopy-def", default=DEFAULT_CANOPY_DEF)
    ap.add_argument("--q-loss", type=float, default=DEFAULT_Q_LOSS)
    ap.add_argument("--q-gain", type=float, default=DEFAULT_Q_GAIN)
    ap.add_argument("--emission-plugin", choices=list(PLUGINS), default=DEFAULT_PLUGIN,
                    help="prevalence plug-in for the false-positive inversion. "
                         "pixel (default) = the PIXEL fraction over the whole valid grid "
                         "(PIXEL_SCOPE), the unit the precision was measured in; the "
                         "crown-covered pixel fraction is reported beside it but measured "
                         "equivalent to the defect (v2 AMENDMENT); crown = the v1 "
                         "crown-pooled fraction, "
                         "a MUTATION SWITCH that exists only to show the emission gate "
                         "firing. Never for a scored run")
    ap.add_argument("--placebo-seed", type=int, default=None,
                    help="shuffle the epoch-to-rate assignment (kill K3). Stamped in every "
                         "output and in the trailer — never silent")
    ap.add_argument("--allow-missing", action="store_true",
                    help="drop unscored arms from the emission instead of failing")
    ap.add_argument("--no-persistence", action="store_true",
                    help="MUTATION SWITCH: collapse to two states, removing the "
                         "two-epoch gain-persistence rule. Never for a scored run")
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--out-npz", default=str(OUT_NPZ))
    ap.add_argument("--dry-run", action="store_true")
    return ap


def _plan(a):
    """Dry-run: resolve rates, MEASURE both prevalences off the stack, print the epoch
    table with r, f_grid, f_crownpx, f_crown and the gate verdict. Writes nothing.

    It reads the stack and rasterises the crowns (v1's dry-run did neither) because the
    gate verdict cannot be shown without the prevalence — which was exactly how the v1
    defect survived a dry-run."""
    import numpy as np
    sp = Path(a.stack)
    if not sp.exists():
        print(f"FATAL: {sp} not found")
        return 2
    d = np.load(sp)
    years = [str(y) for y in d["years"]]
    tags = [str(t) for t in d["tags"]]
    try:
        rates, missing = load_rates(a.rates_csv, tags, a.policy, a.rates_ref,
                                    a.canopy_def, allow_missing=True)
    except SystemExit as e:
        print(str(e))
        return 2
    print(f"DRY RUN: {sp}  ({len(tags)} epochs)  crowns={a.crowns}")
    print(f"  rates: {a.rates_csv}  policy={a.policy} ref={a.rates_ref} "
          f"canopy_def={a.canopy_def}")
    print(f"  q_gain={a.q_gain} q_loss={a.q_loss} persistence="
          f"{not a.no_persistence} placebo_seed={a.placebo_seed}")
    print(f"  emission plug-in: {a.emission_plugin}")
    cp = Path(a.crowns)
    if not cp.exists():
        print(f"FATAL: {cp} not found (local mirror)")
        return 2
    stack_arr, inside, years, tags, g, ids = load_crowns(sp, cp)
    obs = observations(stack_arr, ids, len(g))[:, 1:]
    pi_grid, pi_crownpx, pi_pooled = epoch_prevalences(stack_arr, inside, ids, obs)
    erows = derive_emissions(tags, rates, pi_grid, pi_crownpx, pi_pooled,
                             a.emission_plugin)
    print()
    try:
        emission_gate(erows, a.emission_plugin, years)
    except SystemExit as e:
        print(str(e))
        return 2
    print(emission_table(erows, a.emission_plugin, years))
    print("\n  EMISSION GATE: PASS — f < r for every rated epoch.")
    print(f"\n  would write: {a.out_npz}\n               {a.out}")
    if missing and not a.allow_missing:
        print(f"\n  BLOCKED — no rate row for: {', '.join(missing)}")
        print("  Score those arms, or re-run with --allow-missing to drop them "
              "(they become MISSING observations).")
        return 2
    if missing:
        print(f"\n  WARNING: dropping unscored arms from the emission: "
              f"{', '.join(missing)}")
    return 0


def main(argv=None):
    from phase4seg.names import clean_argv
    a = _parser().parse_args(clean_argv() if argv is None else argv)

    if a.dry_run:
        return _plan(a)

    import numpy as np
    try:
        res, err = build(stack=a.stack, crowns=a.crowns, rates_csv=a.rates_csv,
                         policy=a.policy, ref=a.rates_ref, canopy_def=a.canopy_def,
                         q_gain=a.q_gain, q_loss=a.q_loss,
                         placebo_seed=a.placebo_seed, allow_missing=a.allow_missing,
                         persistence=not a.no_persistence, plugin=a.emission_plugin)
    except SystemExit as e:
        print(str(e))
        return 2
    if err:
        print(f"FATAL: {err}")
        return 2

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(intervals_csv(res), encoding="utf-8", newline="")
    iv = res["intervals"]
    np.savez_compressed(
        a.out_npz, obs=res["obs"], post_canopy=res["post_canopy"],
        viterbi=res["viterbi"], crown_id=res["crown_id"],
        years=np.array(res["years"]), tags=np.array(res["tags"]),
        r=res["r"], f=res["f"], r_true=res["r_true"], f_true=res["f_true"],
        p=res["p"], pi=res["pi"], pi_grid=res["pi_grid"],
        pi_crownpx=res["pi_crownpx"], pi_pooled=res["pi_pooled"],
        f_pixel=res["f_pixel"], f_crown=res["f_crown"],
        f_grid=res["f_grid"], f_crownpx=res["f_crownpx"],
        pixel_scope=res["pixel_scope"],
        emission_plugin=res["emission_plugin"],
        curve_ids=res["curve_ids"], prior=res["prior"],
        first_seen=iv["first_seen"], last_seen=iv["last_seen"],
        first_lo=iv["first_lo"], last_hi=iv["last_hi"],
        first_width=iv["first_width"], last_width=iv["last_width"],
        q_gain=res["q_gain"], q_loss=res["q_loss"],
        placebo_seed=res["placebo_seed"], permutation=np.array(res["permutation"]),
        dropped_tags=np.array(res["dropped_tags"], dtype=object).astype(str),
        policy=res["policy"], ref=res["ref"], canopy_def=res["canopy_def"],
        persistence=int(res["persistence"]), stack_path=res["stack_path"])

    out = io.StringIO()

    def A(s=""):
        print(s)
        out.write(s + "\n")

    seen = iv["first_seen"] >= 0
    A(f"{a.out_npz}\n{a.out}  — {res['n_crowns']} crowns x {len(res['tags'])} epochs")
    A(f"  crowns ever P(canopy)>=0.5: {int(seen.sum())} of {res['n_crowns']}")
    A(f"  median first-seen interval width: "
      f"{float(np.median(iv['first_width'][seen])) if seen.any() else float('nan'):.2f} epochs")
    A(f"  median last-seen interval width:  "
      f"{float(np.median(iv['last_width'][seen])) if seen.any() else float('nan'):.2f} epochs")
    A("")
    A(emission_table(res["emission_rows"], res["emission_plugin"], res["years"]))
    A("  (rates above are the TRUE per-tag pairs; under --placebo-seed the APPLIED "
      "assignment is permuted — see `permutation`.)")

    A("\n-- WHAT IS MEASURED, DERIVED, ASSUMED " + "-" * 29)
    A(f"  MEASURED: recall and precision per epoch, read from {Path(a.rates_csv).name} at "
      f"policy={a.policy},\n            ref={a.rates_ref}, canopy_def={a.canopy_def}; the "
      "per-crown cover on the 2 m lattice;\n            the observed positive fraction "
      "pi_e per epoch.")
    A("  DERIVED : the false-positive rate f_e, from precision and pi_e by inverting "
      "p = pi*r/(pi*r+(1-pi)*f);\n            the posterior marginals and the Viterbi "
      "path; the first/last-seen intervals.")
    A("  ASSUMED : (1) pi_e OBSERVED is a plug-in for the TRUE prevalence — the "
      "inversion is only as\n            good as that substitution; (2) rates measured "
      "on PIXELS are inverted with a PIXEL\n            prevalence (v2 fix) but applied to "
      "a CROWN's pooled vote; (3) detection quality is "
      "uniform across the city (yaml: 'only approximately');\n            (4) q_gain / "
      "q_loss are per STEP, though the epochs are unevenly spaced;\n            (5) the "
      "initial prior puts pi_2009 on `canopy`, none on `canopy_new`.")
    A(f"  PROVENANCE: placebo_seed={res['placebo_seed']} "
      f"permutation={res['permutation']} persistence={res['persistence']} "
      f"emission_plugin={res['emission_plugin']}")
    A("  PREVALENCE PLUG-INS, all three reported (the applied one is "
      f"{('pi_' + PIXEL_SCOPE) if res['emission_plugin'] == 'pixel' else 'pi_pooled'}):")
    A(f"    pi_grid    (pixels, whole valid inside grid): {np.round(res['pi_grid'], 4)}")
    A(f"    pi_crownpx (pixels, crown-covered cells)    : "
      f"{np.round(res['pi_crownpx'], 4)}")
    A(f"    pi_pooled  (crowns judged PRESENT, v1)      : "
      f"{np.round(res['pi_pooled'], 4)}")
    if res["dropped_tags"]:
        A(f"  DROPPED (no rate row, treated as MISSING): {', '.join(res['dropped_tags'])}")
    A("  NOT SCORED HERE: this instrument produces no comparison against the Panel A "
      "gold and no\n            verdict. An independent referee writes "
      "crown_state_vs_gold.csv (yaml design contract).")

    try:
        from lake import BASE
        from pipeline_log import write_step_log
        write_step_log(script="crown_state_model", step="posterior",
                       logs_dir=BASE / "phase4" / "logs", stdout_text=out.getvalue(),
                       errors=0, crowns=res["n_crowns"], epochs=len(res["tags"]),
                       placebo_seed=res["placebo_seed"], policy=res["policy"],
                       ref=res["ref"], dropped_tags=res["dropped_tags"],
                       emission_plugin=res["emission_plugin"])
    except Exception as e:                                        # noqa: BLE001
        print(f"  ⚠ step log not written — {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
