"""heal_gap_spectrum.py — laundering risk as a FUNCTION OF GAP LENGTH, not a single 0/42.

WHY THIS EXISTS. The healer's safety number is currently one scalar: zero of 42 verified
losses laundered (`heal_vs_gold.py::build`). That scalar hides two things a reader needs.

  1. **It has no denominator.** Four fields converge on the same fill-odds expression and
     its change-path denominator carries `(1-gamma)^(k-1)` — the odds of a fill being
     wrong is a function of how long the bracket is, so the risk must be reported as a
     curve over gap length, not as one number over a series whose brackets run 3 to 5
     years (`Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` sections 3, 6-G2, 6-G3, 7).
  2. **A count of zero can mean two different things** — the operator refused, or the
     population could not contain the event. Only `n_eligible` separates them, and the
     0/42 never had one.

So this instrument buckets every fill the healer makes by the span of the bracket that
licensed it, and reports the win, the harm, and BOTH denominators per bucket.

WHAT L IS, AND WHAT IT IS NOT. The bucket key is the bracket span in whole calendar
years — `int(next) - int(prev)` via `temporal_heal.py::_year_int`, the healer's own
arithmetic, which is also what `temporal_heal.py::tier_for` thresholds on. A secondary
column carries the span in DAYS measured from `qc/imagery_pixelsize_and_date.csv`, and it
is blank for most brackets on purpose: that table has no date for 2011s ("NOT FOUND"),
and 2021 carries two held acquisitions (King, Snohomish) whose dates are four months
apart, so a date-derived span would be invented for those two epochs rather than
measured. Whole-year arithmetic is what the healer used; days are reported where they
resolve and named where they do not.

THE STRUCTURAL FACT THIS INSTRUMENT WAS BUILT TO EXPOSE, and it is the headline rather
than a caveat. A verified loss's TERMINAL absence is the run of absent epochs that runs
to the END of the series (`heal_vs_gold.py::build` defines it by walking back from the
last epoch). The healer fills a cell at epoch t only when both flanks read canopy at that
cell after alignment — and on this stack every alignment shift rounds to zero cells
(`temporal_heal.py::shift_mask` quantises to whole 2 m cells; the largest published shift
is 1.0 m). So for any interior epoch inside a terminal run, the NEXT epoch is also inside
the run and reads absent, the candidate predicate is false, and the fill cannot happen.
`laundered_at_risk` is therefore zero in every bucket, and `laundered` is pinned at zero
by the shape of the trajectory rather than by the operator's judgement. Report it that
way: the panel cannot see laundering by ANY both-sides rule at this cadence, and the
"0 of 42" is not a 6.9% bound on the loss side — it is a criterion with no power. The
only demonstration that the gate CAN fire is the mutation test in
`qc/test_heal_gap_spectrum.py`, which seeds a fill onto a verified loss's terminal
absence and shows the count move 0 -> 1 in that bucket alone.

THE COLUMNS, in the order a reader should meet them:
  n_eligible / n_fills / fill_rate    what the operator did at this L, in 2 m cells
  laundered_eligible / _at_risk       the two denominators the 0/42 never had
  laundered / censored                the harm side, attributed to the bracket that did it
  triples_present / triples_removed   the win side, at the 1,170 verified no-change points
  crowns_eligible / crowns_deleted    validity-interval boundaries the fills erased

CROWNS_DELETED, precisely. A crown whose RAW ladder reads P A P carries a boundary pair —
the record says the tree left and came back. Healing that single ABSENT to anything other
than ABSENT deletes both boundaries and merges two presence episodes into one. That is a
deletion from the product `crown_trajectories.py::build` ships, and it is counted here.
Note the second mechanism, which is easy to miss: at REVIEW/BLIND epochs the healer writes
255, and `detectability_curve.py::per_crown_cover` divides by the VALID cell count, so an
IGNORE write shrinks the denominator and can lift a crown out of ABSENT with no canopy
asserted anywhere. A non-zero crowns_deleted in an all-BLIND bucket is that, not a fill.

WHAT THIS CANNOT SEE, stated because it bounds every row.
  * **Bracket length resolves to whole calendar years, not to flight dates.** The
    secondary day column covers 4 of the 6 brackets: 2011s has no date in the table at
    all and 2021 holds two held acquisitions four months apart, so the two brackets that
    touch them carry no measured span. A February-flown epoch and an August-flown one
    both count as one year here, and the archive spans February to October.
  * **28% of the crown boundary pairs are not attributed to any L.** 10,103 of the
    36,248 P-A-P records carry an absent run longer than one epoch, which sits inside
    more than one bracket at once; they are counted in the trailer and excluded from
    `crowns_deleted` rather than charged to a bracket by a rule nobody could defend.
  * **Nothing here scores whether a fill was RIGHT.** The spectrum measures where fills
    landed and which verified events they touched. Whether an individual fill restored a
    tree or invented one is an adjudication, and it needs the output-sampled audit
    (`Reports/LIT_HEALING_ANALOGUES_2026-09-08.md`, G1), not this instrument.

NEGATIVE CONTROL. The median-L bucket is recomputed with the gold's labels permuted at a
fixed seed — which points are losses and which are no-change is shuffled, the trajectories
are not. If the real bucket and the shuffled bucket report the same thing, the instrument
is measuring trajectory shape rather than the human verdict, which is a fact about the
population and must be published, not hidden. The analytic null (the base rate scaled to
42 points) is written to the trailer beside the single fixed-seed draw, because one draw
of 42 from 1,214 is noisy and the expectation is exact.

Output: phase4/qc/heal_gap_spectrum.csv

Run:  py -3.12 qc/instruments/heal_gap_spectrum.py [--dry-run] [--no-crowns]
      py -3.12 qc/instruments/heal_gap_spectrum.py --heal bundle.npz --gold g.csv --out o.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import statistics
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

GOLD_CSV = QC / "panel_a_gold.csv"
OUT_CSV = QC / "heal_gap_spectrum.csv"
HEAL_VS_GOLD_CSV = QC / "heal_vs_gold.csv"
DATE_TABLE = SCRIPTS / "qc" / "imagery_pixelsize_and_date.csv"

SHUFFLE_SEED = 20260908          # fixed: the control must be reproducible byte-for-byte
CONF = 0.95                      # one-sided upper bound on the laundering rate

HEALED = 1                       # mirrors temporal_heal.py::HEALED
HEALED_IGNORE = 255              # mirrors temporal_heal.py::HEALED_IGNORE


def _sibling(name):
    """Import a sibling instrument BY FILE LOCATION.

    Not a `sys.path` insert: the editable install does not cover `qc/instruments/`, and
    the insert ledger in `test_status_discovery.py::test_path_insert_ledger` is a
    ratchet whose counts are ceilings — that gate greps for the literal call, so even
    naming it in prose adds a ledger row. A spec loader needs neither the path nor the
    ledger line.
    """
    import importlib.util
    p = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_hgs_{name}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _rows(p):
    """CSV body only — every file in phase4/qc/ carries a `#` trailer."""
    p = Path(p)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _trailer(p):
    """The `# key,value` trailer as a dict — the summary half of a measured CSV."""
    out = {}
    p = Path(p)
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s.startswith("#") and "," in s:
            k, _, v = s[1:].strip().partition(",")
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------- shared definitions

def terminal_start(raw):
    """First index of the TERMINAL absent run, copied from `heal_vs_gold.py::build`.

    Walk back from the end while the epoch reads 0. A 255 stops the walk, so a terminal
    run is a run of asserted absence and never of no-data. Filling anything at or after
    this index is what "laundering a verified loss" means; filling an earlier absence at
    a point cut later is the operator working, and conflating the two is the error that
    once reported 5 of 42.
    """
    t = len(raw)
    while t > 0 and raw[t - 1] == 0:
        t -= 1
    return t


def cell_of(transform, x, y, shape):
    """Map coordinate -> stack cell, copied from `heal_vs_gold.py::build` so the gold
    lands on the same lattice both scorers use. Returns None when off-grid."""
    h, w = shape
    col = int((float(x) - transform[2]) / transform[0])
    row = int((float(y) - transform[5]) / transform[4])
    return (row, col) if (0 <= row < h and 0 <= col < w) else None


def bucket_of_epoch(years, prev, nxt, year_int):
    """L per epoch index in whole years; None where the epoch has no bracket."""
    out = []
    for i in range(len(years)):
        if not prev[i] or not nxt[i]:
            out.append(None)
        else:
            out.append(year_int(nxt[i]) - year_int(prev[i]))
    return out


def exact_upper_bound(k, n, conf=CONF):
    """One-sided upper bound on a binomial rate.

    k = 0 has a closed form, 1 - (1-conf)^(1/n) — the "rule of three" done exactly, and
    the one that matters here because k is always 0. Anything else needs the
    Clopper-Pearson beta quantile; if scipy is unavailable the cell stays blank rather
    than carrying an approximation nobody asked for.
    """
    if n <= 0:
        return None
    if k <= 0:
        return 1.0 - (1.0 - conf) ** (1.0 / n)
    if k >= n:
        return 1.0
    try:
        from scipy import stats
    except Exception:
        return None
    return float(stats.beta.ppf(conf, k + 1, n - k))


# ---------------------------------------------------------------- the gold half

def gold_counters(bundle, labels, l_of):
    """Per-L gold statistics for ONE label vector — real labels or a shuffle.

    Same function both times on purpose: the negative control differs from the real row
    only in which points are called losses, so any difference in the output is
    attributable to the labels and to nothing else.
    """
    import numpy as np
    stack, healed, cand = bundle["stack"], bundle["healed"], bundle["candidate"]
    pts = bundle["points"]                     # [(row, col, point_id), ...] on-grid only
    n_ep = len(bundle["years"])

    z = collections.Counter
    acc = {"laundered": z(), "censored": z(), "triples_present": z(),
           "triples_removed": z(), "loss_n": 0, "nochange_n": 0}
    lp, le, lr = collections.defaultdict(set), collections.defaultdict(set), \
        collections.defaultdict(set)
    filled_any = set()                         # any label: the analytic null's numerator

    rows = np.array([p[0] for p in pts], dtype=np.intp)
    cols = np.array([p[1] for p in pts], dtype=np.intp)
    raw_m = np.stack([stack[i][rows, cols] for i in range(n_ep)], axis=1).astype(int)
    new_m = np.stack([healed[i][rows, cols] for i in range(n_ep)], axis=1).astype(int)
    cand_m = np.stack([cand[i][rows, cols] for i in range(n_ep)], axis=1).astype(bool)

    for j, (_, _, pid) in enumerate(pts):
        raw, new, cnd = raw_m[j], new_m[j], cand_m[j]
        lab = labels[j]
        term = terminal_start(list(raw))
        for i in range(term, n_ep):
            if l_of[i] is None:                # an endpoint: no bracket, never healed
                continue
            if raw[i] == 0 and new[i] == HEALED:
                filled_any.add(pid)
        if lab == "loss":
            acc["loss_n"] += 1
            for i in range(term, n_ep):
                L = l_of[i]
                if L is None:
                    continue
                le[L].add(pid)                 # POSITIONAL denominator: a bracket of
                if cnd[i]:                     # this L overlaps the terminal absence
                    lr[L].add(pid)             # AT-RISK: the fill predicate actually fires
                if raw[i] == 0 and new[i] == HEALED:
                    acc["laundered"][L] += 1
                    lp[L].add(pid)
                elif raw[i] == 0 and new[i] == HEALED_IGNORE:
                    acc["censored"][L] += 1
        elif lab == "nochange":
            acc["nochange_n"] += 1
            for i in range(1, n_ep - 1):
                L = l_of[i]
                if L is None:
                    continue
                if raw[i - 1] == 1 and raw[i] == 0 and raw[i + 1] == 1:
                    acc["triples_present"][L] += 1
                    if new[i] != 0:
                        acc["triples_removed"][L] += 1
    acc["laundered_points"] = {L: len(v) for L, v in lp.items()}
    acc["laundered_eligible"] = {L: len(v) for L, v in le.items()}
    acc["laundered_at_risk"] = {L: len(v) for L, v in lr.items()}
    acc["filled_any_points"] = filled_any
    return acc


# ---------------------------------------------------------------- the crown half

def states_matrix(cov, vfrac, present_at, absent_at, min_valid):
    """Vectorised twin of `crown_trajectories.py::_state`, checked against it in the test.

    Order matters and mirrors the scalar version: UNOBSERVED is tested FIRST there, so it
    is written LAST here. NaN is deliberate — `nan < min_valid` is False, so a crown with
    no cells at all reads UNSURE, exactly as the scalar ladder does.
    """
    import numpy as np
    out = np.full(cov.shape, "?", dtype="<U1")
    with np.errstate(invalid="ignore"):
        out[cov >= present_at] = "P"
        out[cov <= absent_at] = "A"
        out[vfrac < min_valid] = "U"
    return out


def crown_boundary_removals(raw_states, healed_states, l_of):
    """Per-L count of validity-interval boundaries healing removed.

    Only SINGLE-epoch absent runs are attributed. A longer run sits inside more than one
    bracket and would have to be charged to two different L at once; those are counted
    and reported separately rather than allocated by a rule nobody could defend.
    """
    elig, rem = collections.Counter(), collections.Counter()
    multi = 0
    for rs, hs in zip(raw_states, healed_states):
        i = 1
        n = len(rs)
        while i < n - 1:
            if rs[i] != "A":
                i += 1
                continue
            j = i
            while j + 1 < n and rs[j + 1] == "A":
                j += 1
            if rs[i - 1] == "P" and j + 1 < n and rs[j + 1] == "P":
                if j == i and l_of[i] is not None:
                    elig[l_of[i]] += 1
                    if hs[i] != "A":
                        rem[l_of[i]] += 1
                elif j > i:
                    multi += 1
            i = j + 1
    return elig, rem, multi


def crown_states(bundle):
    """RAW and HEALED crown ladders on the frozen 2020 delineation.

    Reuses `detectability_curve.py::load` for the crown raster and
    `detectability_curve.py::per_crown_cover` for cover, and takes the ladder constants
    from `crown_trajectories.py` rather than restating them — one fact, one home. The
    validity share comes from the RAW stack, as `crown_trajectories.py::build` computes
    it, so healing changes cover but never changes which epochs count as observed.
    """
    import numpy as np
    dc = _sibling("detectability_curve")
    ct = _sibling("crown_trajectories")
    if not dc.CROWNS.exists():
        return None, None, f"{dc.CROWNS.name} not found (local mirror)"

    stack, inside, years, g, ids = dc.load()
    if [str(y) for y in years] != list(bundle["years"]):
        return None, None, "crown raster epochs disagree with the heal bundle"
    n = len(g)
    healed = bundle["healed"]
    raw_cov = np.vstack([dc.per_crown_cover(stack[i], ids, n, False)
                         for i in range(len(years))])
    heal_cov = np.vstack([dc.per_crown_cover(healed[i], ids, n, False)
                          for i in range(len(years))])

    flat = ids.ravel()
    m = flat > 0
    idm = flat[m]
    tot = np.bincount(idm, minlength=n + 1).astype(float)
    vfrac = np.vstack([
        np.divide(np.bincount(idm, weights=(stack[i].ravel()[m] != 255).astype(float),
                              minlength=n + 1), np.maximum(tot, 1))
        for i in range(len(years))])

    idx = g["idx"].to_numpy()
    rs = states_matrix(raw_cov[:, idx].T, vfrac[:, idx].T,
                       ct.PRESENT_AT, ct.ABSENT_AT, ct.MIN_VALID_FRAC)
    hs = states_matrix(heal_cov[:, idx].T, vfrac[:, idx].T,
                       ct.PRESENT_AT, ct.ABSENT_AT, ct.MIN_VALID_FRAC)
    return ["".join(r) for r in rs], ["".join(r) for r in hs], None


# ---------------------------------------------------------------- measured date span

def measured_spans(years):
    """Bracket span in DAYS from `qc/imagery_pixelsize_and_date.csv`, where it resolves.

    A stack label matches a table row when the row is held imagery and its `year_label`
    is the label itself or the label followed by " (". Several rows may match; what
    decides is whether they AGREE on the first date. 2016 has two rows (the county
    product and the campaign replacement) carrying the same flight, so it resolves; 2021
    holds a King April flight and a Snohomish June-to-November one, and picking either
    would be an invention, so it stays AMBIGUOUS and contributes nothing. No ISO date in
    `date_shot` is UNDATED — 2011s reads "NOT FOUND (year from the county service name
    Aerial_2011 only)", which is why the two brackets that touch it carry no measured
    span.
    """
    import datetime
    import re
    out = {}
    rows = _rows(DATE_TABLE)
    for y in years:
        seen = set()
        n_rows = 0
        for r in rows:
            if not r.get("row_type", "").startswith("held imagery"):
                continue
            yl = r.get("year_label", "")
            if yl != y and not yl.startswith(y + " ("):
                continue
            n_rows += 1
            m = re.search(r"\d{4}-\d{2}-\d{2}", r.get("date_shot", ""))
            if m:
                seen.add(m.group(0))
        if len(seen) == 1:
            out[y] = (datetime.date.fromisoformat(seen.pop()), "measured")
        elif seen:
            out[y] = (None, "ambiguous")
        else:
            out[y] = (None, "undated" if n_rows else "no-row")
    return out


# ---------------------------------------------------------------- the spectrum

def spectrum(bundle, gold, no_crowns=False, seed=SHUFFLE_SEED):
    """Bucket every fill by bracket span and score both sides against the gold.

    `bundle` is arrays-in / rows-out so the whole instrument is exercisable on a
    synthetic stack in tmp_path — the mutation test needs to seed a fill onto a verified
    loss and watch the count move, which is the only evidence that the gate fires at all.
    """
    import numpy as np
    year_int = bundle["year_int"]
    years = list(bundle["years"])
    n_ep = len(years)
    stack, healed, cand = bundle["stack"], bundle["healed"], bundle["candidate"]
    l_of = bucket_of_epoch(years, bundle["prev"], bundle["next"], year_int)

    # ---- on-grid gold points, off-grid counted rather than dropped silently
    inside = bundle["inside"]
    pts, labels, off = [], [], 0
    for g in gold:
        rc = cell_of(bundle["transform"], g["x"], g["y"], inside.shape)
        if rc is None or not inside[rc]:
            off += 1
            continue
        pts.append((rc[0], rc[1], g["point_id"]))
        labels.append(g["label"])
    bundle = dict(bundle, points=pts)

    real = gold_counters(bundle, labels, l_of)

    # ---- crown ladders (optional: needs the 2020 crown gpkg on the local mirror)
    crown_elig, crown_rem, crown_multi, crown_note = \
        collections.Counter(), collections.Counter(), 0, ""
    if not no_crowns:
        if bundle.get("crown_raw") is not None:
            rs, hs = list(bundle["crown_raw"]), list(bundle["crown_healed"])
        else:
            rs, hs, err = crown_states(bundle)
            if err:
                rs = hs = None
                crown_note = err
        if rs is not None:
            crown_elig, crown_rem, crown_multi = crown_boundary_removals(rs, hs, l_of)
    else:
        crown_note = "skipped (--no-crowns)"

    # ---- cell-level aggregates, read off the healed array rather than the overlay, so
    # a fill the eligibility predicate never licensed still shows up (mutation B).
    per_L = collections.defaultdict(lambda: collections.Counter())
    epochs_in = collections.defaultdict(list)
    for i in range(n_ep):
        L = l_of[i]
        if L is None:
            continue
        writable = stack[i] == 0
        to_can = writable & (healed[i] == HEALED)
        to_ign = writable & (healed[i] == HEALED_IGNORE)
        b = per_L[L]
        b["n_epochs"] += 1
        b["n_eligible"] += int(cand[i].sum())
        b["n_fills_canopy"] += int(to_can.sum())
        b["n_fills_ignore"] += int(to_ign.sum())
        b["fills_outside_eligible"] += int(((to_can | to_ign) & ~cand[i]).sum())
        b[f"tier_{bundle['tiers'][i] or 'NONE'}"] += 1
        epochs_in[L].append(years[i])

    span = measured_spans(years)
    days_of = {}
    for L in sorted(per_L):
        days_of[L] = []
        for e in epochs_in[L]:
            i = years.index(e)
            d0, d1 = span.get(bundle["prev"][i], (None, ""))[0], \
                span.get(bundle["next"][i], (None, ""))[0]
            if d0 and d1:
                days_of[L].append((d1 - d0).days)
    rows = []
    for L in sorted(per_L):
        rows.append(_row("spectrum", L, per_L[L], epochs_in[L], real, crown_elig,
                         crown_rem, days_of[L], ""))

    # ---- NEGATIVE CONTROL on the median-L bucket, labels permuted at a fixed seed
    interior_L = [L for L in l_of if L is not None]
    med = statistics.median_low(sorted(interior_L)) if interior_L else None
    null_note = ""
    if med is not None and pts:
        rng = np.random.default_rng(seed)
        shuf = [labels[k] for k in rng.permutation(len(labels))]
        ctrl = gold_counters(bundle, shuf, l_of)
        # crowns are label-independent: repeating the spectrum row's counts here would
        # imply the shuffle produced them, so the control leaves those two cells BLANK.
        rows.append(_row("negative_control", med, per_L[med], epochs_in[med], ctrl,
                         None, None, days_of.get(med, []),
                         f"gold labels permuted, seed {seed}"))
        # analytic null: the base rate of "terminal absence filled at any L" over ALL
        # gold points, scaled to the 42 losses. Exact, where one draw of 42 is not.
        k_all = len(real["filled_any_points"])
        null_note = (f"{k_all}/{len(pts)} of all gold points have a terminal absence "
                     f"filled anywhere; expected laundered points among "
                     f"{real['loss_n']} losses under the null = "
                     f"{real['loss_n'] * k_all / max(len(pts), 1):.3f}")

    meta = {"off_grid": off, "years": years, "l_of": l_of, "median_L": med,
            "crown_multi_epoch_runs": crown_multi, "crown_note": crown_note,
            "null_note": null_note, "n_points": len(pts),
            "date_basis": {y: span[y][1] for y in years},
            "triples_present_total": sum(real["triples_present"].values()),
            "triples_removed_total": sum(real["triples_removed"].values())}
    return rows, meta


def _row(kind, L, cells, epochs, acc, crown_elig, crown_rem, days, note):
    """One CSV row. Cell counts come from the bundle, gold counts from `acc` — which is
    the real labels for a spectrum row and the shuffled labels for the control."""
    n_el = cells["n_eligible"]
    n_fill = cells["n_fills_canopy"] + cells["n_fills_ignore"]
    at_risk = acc["laundered_at_risk"].get(L, 0)
    k = acc["laundered_points"].get(L, 0)
    ub = exact_upper_bound(k, at_risk)
    return {
        "row_kind": kind,
        "L_years": L,
        "n_epochs": cells["n_epochs"],
        "epochs": "|".join(epochs),
        "L_days_measured": int(statistics.median_low(sorted(days))) if days else "",
        "n_epochs_dated": len(days),
        "tier_HEAL": cells["tier_HEAL"],
        "tier_REVIEW": cells["tier_REVIEW"],
        "tier_BLIND": cells["tier_BLIND"],
        "n_eligible": n_el,
        "n_fills": n_fill,
        "n_fills_canopy": cells["n_fills_canopy"],
        "n_fills_ignore": cells["n_fills_ignore"],
        "fill_rate": round(n_fill / n_el, 4) if n_el else "",
        "fills_outside_eligible": cells["fills_outside_eligible"],
        "gold_loss_n": acc["loss_n"],
        "laundered": acc["laundered"].get(L, 0),
        "laundered_points": k,
        "laundered_eligible": acc["laundered_eligible"].get(L, 0),
        "laundered_at_risk": at_risk,
        "laundered_rate_ci95_upper": round(ub, 4) if ub is not None else "",
        "censored": acc["censored"].get(L, 0),
        "triples_present": acc["triples_present"].get(L, 0),
        "triples_removed": acc["triples_removed"].get(L, 0),
        "crowns_eligible": "" if crown_elig is None else crown_elig.get(L, 0),
        "crowns_deleted": "" if crown_rem is None else crown_rem.get(L, 0),
        "notes": note,
    }


# ---------------------------------------------------------------- the real bundle

def load_bundle(path=None):
    """Either replay a saved bundle (`--heal`, what the tests use) or build the real one.

    The real path runs `temporal_heal.py::build` and RECONSTRUCTS its candidate set from
    the shifts that same call published, using the healer's own
    `temporal_heal.py::shift_mask`. Two reconciliations gate the reconstruction, because
    a count that agrees is not the same as a set that agrees:

        cand.sum() == candidate_cells_raw     the healer's own published count
        filled <= cand, cell by cell          positional containment, not just totals

    Either one failing means the predicate here has drifted from the predicate there,
    and the whole spectrum would be attributing fills to the wrong denominator.
    """
    import numpy as np
    th = _sibling("temporal_heal")
    if path:
        d = np.load(path, allow_pickle=False)
        b = {"years": [str(y) for y in d["years"]],
             "stack": d["stack"], "healed": d["healed"],
             "candidate": d["candidate"].astype(bool), "inside": d["inside"].astype(bool),
             "transform": d["transform"], "tiers": [str(t) for t in d["tiers"]],
             "prev": [str(t) for t in d["prev"]], "next": [str(t) for t in d["next"]],
             "year_int": th._year_int,
             "crown_raw": [str(s) for s in d["crown_raw"]] if "crown_raw" in d else None,
             "crown_healed": ([str(s) for s in d["crown_healed"]]
                              if "crown_healed" in d else None)}
        return b, None

    rows, overlays, err = th.build()
    if err:
        return None, err
    d = np.load(th.STACK)
    stack, inside = d["stack"], d["inside"]
    years = [str(y) for y in d["years"]]
    by_epoch = {r["epoch"]: r for r in rows}

    healed = np.stack([stack[i].copy() for i in range(len(years))])
    cand = np.zeros(stack.shape, dtype=bool)
    tiers, prev, nxt = [""] * len(years), [""] * len(years), [""] * len(years)
    for i, y in enumerate(years):
        r = by_epoch.get(y)
        if r is None:
            continue
        tiers[i], prev[i], nxt[i] = r["tier"], r["prev"], r["next"]
        ov = overlays[y]
        healed[i] = th.apply_heal(stack[i], ov["heal"], ov["ignore"])
        ip, inx = years.index(r["prev"]), years.index(r["next"])
        valid = ((stack[i] != 255) & (stack[ip] != 255) & (stack[inx] != 255) & inside)
        prev_a = th.shift_mask(stack[ip] == 1,
                               r["shift_prev_dx_m"], r["shift_prev_dy_m"])
        next_a = th.shift_mask(stack[inx] == 1,
                               r["shift_next_dx_m"], r["shift_next_dy_m"])
        cand[i] = (stack[i] == 0) & prev_a & next_a & valid
        got, want = int(cand[i].sum()), int(r["candidate_cells_raw"])
        if got != want:
            return None, (f"candidate reconstruction disagrees at {y}: {got} != {want} "
                          f"— the bracket predicate here has drifted from temporal_heal")
        filled = ov["heal"] | ov["ignore"]
        if bool(np.any(filled & ~cand[i])):
            return None, (f"healer wrote outside its own candidate set at {y} — the "
                          f"reconstruction matches on count but not on position")
    return {"years": years, "stack": stack, "healed": healed, "candidate": cand,
            "inside": inside, "transform": d["transform"], "tiers": tiers,
            "prev": prev, "next": nxt, "year_int": th._year_int,
            "crown_raw": None, "crown_healed": None}, None


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--heal", default=None,
                    help="replay a saved heal bundle (.npz) instead of running the healer")
    ap.add_argument("--gold", default=str(GOLD_CSV))
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--no-crowns", action="store_true",
                    help="skip the validity-interval boundary count (needs the 2020 gpkg)")
    ap.add_argument("--seed", type=int, default=SHUFFLE_SEED)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    gold = _rows(a.gold)
    if not gold:
        print(f"FATAL: {a.gold} absent or empty — run freeze_panel_a_gold.py")
        return 2
    bundle, err = load_bundle(a.heal)
    if err:
        print(f"FATAL: {err}")
        return 2

    rows, meta = spectrum(bundle, gold, no_crowns=a.no_crowns, seed=a.seed)
    if not rows:
        print("FATAL: no interior brackets — nothing to bucket")
        return 2

    cols = list(rows[0].keys())
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    spec = [r for r in rows if r["row_kind"] == "spectrum"]
    tp = meta["triples_present_total"]
    tr = meta["triples_removed_total"]
    buf.write(f"# epochs,{'|'.join(meta['years'])}\n")
    buf.write(f"# n_gold_points_on_grid,{meta['n_points']}\n")
    buf.write(f"# off_grid,{meta['off_grid']}\n")
    buf.write(f"# median_L_years,{meta['median_L']}\n")
    buf.write(f"# shuffle_seed,{a.seed}\n")
    buf.write(f"# laundered_total,{sum(r['laundered'] for r in spec)}\n")
    buf.write(f"# laundered_at_risk_total,{sum(r['laundered_at_risk'] for r in spec)}\n")
    buf.write(f"# fills_outside_eligible_total,"
              f"{sum(r['fills_outside_eligible'] for r in spec)}\n")
    buf.write(f"# triples_present_total,{tp}\n")
    buf.write(f"# triples_removed_total,{tr}\n")
    buf.write(f"# crown_multi_epoch_runs,{meta['crown_multi_epoch_runs']}\n")
    if meta["crown_note"]:
        buf.write(f"# crowns_note,{meta['crown_note']}\n")
    if meta["null_note"]:
        buf.write(f"# analytic_null,{meta['null_note']}\n")
    for y, basis in meta["date_basis"].items():
        buf.write(f"# date_basis_{y},{basis}\n")
    # cross-check against the scorer that owns the aggregate. Reported, not asserted:
    # a stale heal_vs_gold.csv is a reason to re-run it, not a reason to fail here.
    hv = _trailer(HEAL_VS_GOLD_CSV)
    xc = ""
    if hv.get("nochange_triples_raw"):
        ok = (str(tp) == hv["nochange_triples_raw"]
              and str(tr) == hv.get("nochange_triples_fixed"))
        xc = (f"triples {tp}/{tr} vs heal_vs_gold "
              f"{hv['nochange_triples_raw']}/{hv.get('nochange_triples_fixed')} "
              f"{'MATCH' if ok else 'MISMATCH'}")
        buf.write(f"# crosscheck_heal_vs_gold,{xc}\n")
    if not a.dry_run:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(buf.getvalue(), encoding="utf-8", newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}{a.out} — {len(spec)} gap-length buckets, "
          f"{meta['n_points']} gold points on grid ({meta['off_grid']} off)")
    print(f"\n{'L yr':>5}{'epochs':>26}{'tiers':>16}{'eligible':>10}{'fills':>9}"
          f"{'rate':>7}{'laund':>7}{'at-risk':>8}{'elig':>6}{'trip+':>7}{'trip-':>7}"
          f"{'crown+':>9}{'crown-':>9}")
    def _rate(r):
        return f"{r['fill_rate']:.2f}" if r["fill_rate"] != "" else "—"
    for r in spec:
        t = f"{r['tier_HEAL']}H/{r['tier_REVIEW']}R/{r['tier_BLIND']}B"
        print(f"{r['L_years']:>5}{r['epochs']:>26}{t:>16}{r['n_eligible']:>10,}"
              f"{r['n_fills']:>9,}{_rate(r):>7}{r['laundered']:>7}"
              f"{r['laundered_at_risk']:>8}{r['laundered_eligible']:>6}"
              f"{r['triples_present']:>7}{r['triples_removed']:>7}"
              f"{r['crowns_eligible']:>9,}{r['crowns_deleted']:>9,}")
    ctrl = [r for r in rows if r["row_kind"] == "negative_control"]
    for r in ctrl:
        print(f"{r['L_years']:>5}{'SHUFFLED GOLD (control)':>26}{'-':>16}"
              f"{r['n_eligible']:>10,}{r['n_fills']:>9,}{_rate(r):>7}"
              f"{r['laundered']:>7}{r['laundered_at_risk']:>8}"
              f"{r['laundered_eligible']:>6}{r['triples_present']:>7}"
              f"{r['triples_removed']:>7}{'-':>9}{'-':>9}")

    at_risk = sum(r["laundered_at_risk"] for r in spec)
    print(f"\n  AT-RISK is the denominator the 0/{spec[0]['gold_loss_n']} never had: "
          f"{at_risk} verified losses across all buckets sit at a position where the "
          f"healer's\n  bracket predicate actually fires.")
    if at_risk == 0:
        print("  It is ZERO, and that is the finding. A terminal absence runs to the "
              "END of the series, so the\n  epoch after any interior epoch inside it "
              "also reads absent and the both-sides predicate cannot\n  fire. "
              "'Zero laundered' here is pinned by trajectory shape, not earned by the "
              "operator — it is a\n  criterion with no power, not a 6.9% bound. The "
              "mutation test in qc/test_heal_gap_spectrum.py\n  is the only "
              "demonstration that the count can move at all.")
    print(f"\n  {meta['null_note']}")
    if xc:
        print(f"  CROSSCHECK: {xc}")
    if meta["crown_note"]:
        print(f"  crowns: {meta['crown_note']}")
    else:
        print(f"  crowns: {meta['crown_multi_epoch_runs']:,} multi-epoch absent runs are "
              f"counted but NOT attributed to an L —\n  they span more than one bracket. "
              f"An all-BLIND bucket with crowns_deleted > 0 is the IGNORE\n  mechanism: "
              f"255 leaves the valid denominator, so cover rises with no canopy asserted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
