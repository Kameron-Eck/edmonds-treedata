"""heal_fill_audit_sample.py — draw the FILL-SIDE laundering audit, stratified, with a control.

WHY THE EXISTING SCORE CANNOT ANSWER THIS. `heal_vs_gold.py` scores the healer against the
frozen human panel and reports 0 of 42 verified losses laundered. That number is drawn from
the ENDPOINT PANEL: it can only ever see laundering at the losses the panel happened to
contain, so it bounds the rate at 1 - 0.05^(1/42) = 6.9% and no draw on the panel can do
better — the 42 are spent. The literature review reached the same place from ten other
fields and named the remedy (`Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` §7 test 1, and
mechanism G1 in `Reports/lit_healing_analogues_2026-09-08.csv`): sample from the
CORRECTION'S OWN OUTPUT — the fills — and have a human read the paired interval.

WHAT THIS INSTRUMENT DOES. It draws the manifest and states the design; it does not read
imagery and it does not judge anything. Output is a worksheet a human fills in:

    phase4/qc/heal_fill_audit_sample.csv   one row per audit unit, two empty label columns
    phase4/qc/heal_fill_audit_design.txt   strata populations, weights, detectable effect

THE UNIT IS A FILL COMPONENT, NOT A CELL. §7 says "~300 cells"; a 2 m cell is not
independently readable and 300 cells could all come from one patch. The unit here is a
connected component of the healer's own output — every one at least `temporal_heal.py`'s
MIN_AREA_M2 (28 m2, one mature crown), which is what a reader can actually judge. Component
count, not cell count, is what the bound below is computed on.

STRATA: tier x gap bucket x crown-size class.
  * tier            HEAL / REVIEW / BLIND, from `temporal_heal.py::tier_for` — the
                    operator's own decision rule, so the audit is stratified on the thing
                    it audits.
  * gap bucket      max(gap_left, gap_right) in years, bucketed 1-2 / 3 / 4+ — again the
                    tier rule's own quantity (BLIND fires at >= 3).
  * size class      equivalent-area diameter of the component, binned on
                    `detectability_curve.py::BINS`. The bins were defined on the crowns'
                    `diameter_m`, which `pipeline/frozen/phase0_instance_seg.py` computes as
                    2*sqrt(area/pi) — the same equivalent-area diameter used here, so the
                    mapping is exact in form (MEASURED, not assumed); ours is quantised to
                    the 2 m lattice.

OVERSAMPLING. REVIEW and BLIND are drawn at 2x their population share. Those are the tiers
where laundering is possible: post-2016 no lidar epoch can veto a real clearing, and a
bracket >= 3 years is wide enough for bigleaf maple coppice to cross. Note what a "fill" MEANS
in those tiers — the healer writes IGNORE there, not canopy — so a "no" on a REVIEW/BLIND unit
does not score written output; it measures what the both-sides rule WOULD have laundered had
the tier been promoted, which is the evidence the tier policy currently rests on by argument
alone.

THE CONTROL, and what it is honestly worth. The literal population the brief names —
untouched BRACKETED absences, i.e. absent with both aligned flanks present and >= the size
floor — is EMPTY BY CONSTRUCTION: filling exactly those is the operator's definition. This
instrument measures that count (`untouched_two_sided` in the design note; expect 0) rather
than asserting it, then substitutes the nearest untouched population at the same scale:
absences with EXACTLY ONE aligned flank present, matched stratum-for-stratum and drawn at the
same per-stratum counts. Fill and control candidates are disjoint by construction
(`both` vs `xor` on the same two aligned flanks), which `qc/test_heal_fill_audit_sample.py`
proves rather than assumes.

  That control is a DISCRIMINATION control, not a blinded error-rate control: its flanks look
  different, so a reader can tell a control from a fill. It answers "does the both-sides rule
  buy anything in the reader's eyes" and bounds context bias. It does NOT establish truth.
  The only independent modality here is lidar, which is why a sub-sample carries `adjudicate`.

ADJUDICABLE. `adjudicable=1` where an independent modality exists within one year of the
filled epoch and covers the point — on this archive that is the 2016 lidar CHM (chm2), so it
reaches the 2015 and 2016 epochs only. No CHM VALUE is written to the manifest: putting the
answer in the worksheet would destroy the check it exists to make.

Run:  py -3.12 qc/instruments/heal_fill_audit_sample.py [--n 300] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import itertools
import math
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

N_TARGET = 300            # G1: ~300 fills is what buys a sub-1% bound at k=0
SEED = 20260908
CELL_M = 2.0

TIERS = ("HEAL", "REVIEW", "BLIND")
# (label, lo, hi) on max(gap_left, gap_right) — the quantity tier_for() itself keys on.
GAP_BUCKETS = (("1-2", 1, 2), ("3", 3, 3), ("4+", 4, 10 ** 6))
OVERSAMPLE = {"HEAL": 1.0, "REVIEW": 2.0, "BLIND": 2.0}

# Independent modalities: (name, epoch year, raster). Lidar only — a human re-reading the
# same ortho the model read is not independent of the model (the defect G1 step iv-b names).
LIDAR = (("lidar_chm2_2016_50cm", 2016,
          Path(r"D:\edmonds-pipeline\Imagery\lidar_chm2_2016_50cm.tif")),)
ADJ_MAX_DYEAR = 1
ADJUDICATE_SHARE = 0.20   # of the drawn units, among those a modality can reach

Z95 = 1.959963985          # same convention as phase4_qc_design_power.py::estimate
ALPHA = 0.05
# The endpoint bound this audit exists to beat is READ, never restated. It lives in
# heal_vs_gold.py::main's trailer (`# loss_n`, `# loss_laundered`), and
# experiments/heal_infill_2017_2023.yaml is queued to rebuild that file on 12 epochs — a
# constant typed here would keep quoting 0/42 after the number it names had moved.
ENDPOINT_SRC = QC / "heal_vs_gold.csv"

COLS = ["unit_id", "blind_order", "is_control", "stratum_id", "stratum_name", "tier",
        "gap_left_yr", "gap_right_yr", "gap_years", "gap_bucket", "size_class",
        "bracket_years", "epoch_prev", "epoch_filled", "epoch_next",
        "x", "y", "epsg", "row", "col", "n_cells", "area_m2", "equiv_diam_m",
        "control_flank", "adjudicable", "adjudicator", "adjudicator_dyear", "adjudicate",
        "present_in_filled_epoch", "notes"]


def trailer(path):
    """`# key,value` summary lines from a measured CSV -> {key: value}. Absent file -> {}."""
    p = Path(path)
    if not p.exists():
        return {}
    out = {}
    for ln in p.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s.startswith("#") and "," in s:
            k, _, v = s.lstrip("# ").partition(",")
            out[k.strip()] = v.strip()
    return out


def endpoint_bound(src=None):
    """(laundered, n, bound) from the panel-side score, or (None, None, None) if unread."""
    t = trailer(ENDPOINT_SRC if src is None else src)
    try:
        k, n = int(t["loss_laundered"]), int(t["loss_n"])
    except (KeyError, ValueError):
        return None, None, None
    return k, n, cp_upper(k, n)


def _sibling(name):
    """Load a sibling instrument BY PATH, with no mutation of the import path.

    The older instruments here reach siblings by pushing the instruments dir onto sys.path
    and are on the ledger for it (test_status_discovery.py::test_path_insert_ledger, whose
    caps only ever fall). A spec loaded from `__file__`'s own directory needs no such push,
    so this adds nothing to that ledger.
    """
    spec = importlib.util.spec_from_file_location(
        f"_hfas_{name}", Path(__file__).with_name(name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def size_classes(bins):
    """detectability_curve.BINS -> ordered (label, lo, hi)."""
    return [(f"{lo}-{hi}" if hi < 999 else f"{lo}+", lo, hi) for lo, hi in bins]


def size_class_of(diam_m, classes):
    for lab, lo, hi in classes:
        if lo <= diam_m < hi:
            return lab
    return classes[-1][0]


def gap_bucket_of(gap_years):
    for lab, lo, hi in GAP_BUCKETS:
        if lo <= gap_years <= hi:
            return lab
    return GAP_BUCKETS[-1][0]


def equiv_diam_m(n_cells, cell_m=CELL_M):
    """Equivalent-area diameter, the SAME estimator phase0 used for crown diameter_m
    (`pipeline/frozen/phase0_instance_seg.py` — 2*sqrt(area/pi))."""
    return 2.0 * math.sqrt(n_cells * cell_m * cell_m / math.pi)


def components(mask, min_cells):
    """Connected components (8-neighbour) >= min_cells, each with an INTERIOR anchor cell.

    The anchor is the member nearest the centroid, never the centroid itself: a concave
    component's centroid can sit outside it, and the reader must be pointed at a cell the
    operator actually wrote.
    """
    import numpy as np
    from scipy import ndimage
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    if n == 0:
        return []
    sizes = np.bincount(lab.ravel())
    keep = np.where(sizes >= min_cells)[0]
    keep = keep[keep > 0]
    if keep.size == 0:
        return []
    cents = ndimage.center_of_mass(mask, lab, list(keep))
    flat = lab.ravel()
    order = np.argsort(flat, kind="stable")
    sl = flat[order]
    s = np.searchsorted(sl, keep, "left")
    e = np.searchsorted(sl, keep, "right")
    w = mask.shape[1]
    out = []
    for k, a, b, cent in zip(keep, s, e, cents):
        idx = order[a:b]
        rr, cc = idx // w, idx % w
        j = int(np.argmin((rr - cent[0]) ** 2 + (cc - cent[1]) ** 2))
        out.append({"n_cells": int(sizes[k]), "row": int(rr[j]), "col": int(cc[j])})
    return out


def collect_units(stack, inside, years, heal_rows, overlays, min_cells, classes,
                  shift_mask):
    """Every audit unit on the stack: the healer's fills, and the matched control pool.

    Returns (units, diag). `units` carry every design column except the draw-time ones.
    `diag["untouched_two_sided"]` is the MEASURED size of the population the brief's literal
    control definition names — it should be 0, because filling those is what the operator is.
    """
    units, diag = [], {"untouched_two_sided": 0, "per_epoch": []}
    for r in heal_rows:
        y = r["epoch"]
        t = years.index(y)
        ov = overlays[y]
        keep = ov["heal"] | ov["ignore"]
        valid = ((stack[t] != 255) & (stack[t - 1] != 255) & (stack[t + 1] != 255)
                 & inside)
        prev_a = shift_mask(stack[t - 1] == 1,
                            float(r["shift_prev_dx_m"]), float(r["shift_prev_dy_m"]))
        next_a = shift_mask(stack[t + 1] == 1,
                            float(r["shift_next_dx_m"]), float(r["shift_next_dy_m"]))
        absent = (stack[t] == 0) & valid
        two_sided = absent & prev_a & next_a
        one_sided = absent & (prev_a ^ next_a)

        fills = components(keep, min_cells)
        controls = components(one_sided & ~keep, min_cells)
        untouched2 = components(two_sided & ~keep, min_cells)
        diag["untouched_two_sided"] += len(untouched2)

        gl, gr = int(r["gap_left_yr"]), int(r["gap_right_yr"])
        gmax = max(gl, gr)
        common = dict(tier=r["tier"], gap_left_yr=gl, gap_right_yr=gr, gap_years=gmax,
                      gap_bucket=gap_bucket_of(gmax), bracket_years=gl + gr,
                      epoch_prev=r["prev"], epoch_filled=y, epoch_next=r["next"])
        for kind, comps in (("fill", fills), ("control", controls)):
            for c in comps:
                d = equiv_diam_m(c["n_cells"])
                u = dict(common)
                u.update(is_control=int(kind == "control"),
                         row=c["row"], col=c["col"], n_cells=c["n_cells"],
                         area_m2=round(c["n_cells"] * CELL_M * CELL_M, 1),
                         equiv_diam_m=round(d, 2),
                         size_class=size_class_of(d, classes),
                         control_flank=("" if kind == "fill" else
                                        ("prev" if prev_a[c["row"], c["col"]] else "next")))
                u["unit_id"] = (f"{'C' if u['is_control'] else 'F'}{y}"
                                f"_{c['row']:05d}_{c['col']:05d}")
                units.append(u)
        diag["per_epoch"].append({
            "epoch": y, "tier": r["tier"], "prev": r["prev"], "next": r["next"],
            "gap_years": gmax, "n_fill": len(fills), "n_control": len(controls),
            "n_untouched_two_sided": len(untouched2),
            "fill_cells": int(keep.sum()), "control_cells": int((one_sided & ~keep).sum()),
        })
    return units, diag


def universe(classes):
    """Every declared stratum, populated or not — an empty one must be VISIBLE."""
    return [(t, g[0], s[0]) for t, g, s in
            itertools.product(TIERS, GAP_BUCKETS, classes)]


def allocate(pop, n_target, keys):
    """Proportional-to-population x tier oversample, then CAP at population.

    Two deliberate deviations from `phase4_accuracy_sample.py::step_design`, which tops up
    and trims until the draw hits n exactly:

      * an EMPTY stratum is refused and reported, never reweighted away. Weight-0
        arithmetic would hide it, so the refusal is carried in the returned `refused`
        list and printed.
      * an UNDER-POPULATED stratum (0 < N_h < nominal) is capped at N_h and the shortfall
        is reported, NOT redistributed. Topping up would move the draw into strata the
        design did not ask for and would silently change the weights the estimator uses.

    Over-budget rounding IS trimmed (budget discipline); under-budget is not filled.
    Returns (alloc, nominal, refused, shortfall).
    """
    live = [k for k in keys if pop.get(k, 0) > 0]
    refused = [k for k in keys if pop.get(k, 0) <= 0]
    if not live:
        return {}, {}, refused, n_target
    w = {k: pop[k] * OVERSAMPLE[k[0]] for k in live}
    tot = sum(w.values())
    # nominal = what the design ASKS FOR, computed before any population cap — a nominal
    # that already knew the cap could not produce a shortfall, and the shortfall is the
    # whole point of refusing to reweight. Floor of 2: below it the within-stratum
    # variance is undefined (phase4_qc_design_power.py::estimate divides by n_h - 1).
    nominal = {k: max(2, int(round(n_target * w[k] / tot))) for k in live}
    while sum(nominal.values()) > n_target:
        k = max(nominal, key=lambda q: (nominal[q], q))
        if nominal[k] <= 2:
            break
        nominal[k] -= 1
    alloc = {k: min(nominal[k], pop[k]) for k in live}
    shortfall = sum(nominal.values()) - sum(alloc.values())
    return alloc, nominal, refused, shortfall


def draw(units, alloc, seed, is_control):
    """Deterministic within-stratum SRS. Strata are visited in sorted key order."""
    import numpy as np
    rng = np.random.default_rng(seed)
    bucket = {}
    for u in units:
        if u["is_control"] != int(is_control):
            continue
        bucket.setdefault((u["tier"], u["gap_bucket"], u["size_class"]), []).append(u)
    out = []
    for k in sorted(bucket):
        n = alloc.get(k, 0)
        if n <= 0:
            continue
        pool = sorted(bucket[k], key=lambda u: u["unit_id"])
        pick = sorted(rng.choice(len(pool), size=min(n, len(pool)), replace=False).tolist())
        out.extend(pool[i] for i in pick)
    return out


def cp_upper(k, n, alpha=ALPHA):
    """Exact one-sided Clopper-Pearson upper bound. k=0 is G1's 1 - alpha^(1/n)."""
    if n <= 0:
        return float("nan")
    if k <= 0:
        return 1.0 - alpha ** (1.0 / n)
    if k >= n:
        return 1.0
    def cdf(p):
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def stratified_halfwidth(alloc, weights, p):
    """95% half-width of the weighted rate at an assumed common p.

    Same variance convention as `phase4_qc_design_power.py::estimate` — within-stratum
    Var(p_h) = p(1-p)/(n_h - 1), summed as sum_h W_h^2 Var(p_h). A single binary outcome is
    the two-cell case of that estimator's multinomial covariance.
    """
    v = 0.0
    for k, n in alloc.items():
        if n > 1:
            v += weights[k] ** 2 * p * (1 - p) / (n - 1)
    return Z95 * math.sqrt(max(v, 0.0))


def sample_adjudicable(rows, epsg):
    """Flag rows an independent modality can reach. Reads coverage only — never a value."""
    hits = {}
    try:
        import rasterio
        from rasterio.warp import transform as warp_transform
    except Exception:                                              # noqa: BLE001
        return hits, "rasterio unavailable — adjudicable left blank"
    for name, lyear, path in LIDAR:
        if not path.exists():
            continue
        sel = [r for r in rows
               if abs(int(str(r["epoch_filled"])[:4]) - lyear) <= ADJ_MAX_DYEAR]
        if not sel:
            continue
        with rasterio.open(path) as src:
            xs = [r["x"] for r in sel]
            ys = [r["y"] for r in sel]
            if src.crs and str(src.crs) != f"EPSG:{epsg}":
                xs, ys = warp_transform(f"EPSG:{epsg}", src.crs, xs, ys)
            vals = [v[0] for v in src.sample(zip(xs, ys), 1)]
        for r, v in zip(sel, vals):
            if float(v) > 0:      # chm2 DN 0 = nodata (phase4_accuracy_sample.py::build_strata)
                hits[r["unit_id"]] = (name,
                                      int(str(r["epoch_filled"])[:4]) - lyear)
    return hits, ""


def pick_adjudicate(rows, share, seed):
    """A stated-size sub-draw among adjudicable rows, stratified by tier AND is_control —
    the control needs the independent check as much as the fill does, because that is where
    the reader's own error rate stops being an assumption."""
    import numpy as np
    rng = np.random.default_rng(seed)
    elig = [r for r in rows if r["adjudicable"] == 1]
    target = int(round(share * len(rows)))
    if not elig or target <= 0:
        return set()
    groups = {}
    for r in elig:
        groups.setdefault((r["tier"], r["is_control"]), []).append(r)
    out = set()
    for k in sorted(groups):
        pool = sorted(groups[k], key=lambda r: r["unit_id"])
        n = min(len(pool), max(1, int(round(target * len(pool) / len(elig)))))
        for i in rng.choice(len(pool), size=n, replace=False).tolist():
            out.add(pool[i]["unit_id"])
    return out


def build(n_target=N_TARGET, seed=SEED, stack_path=None):
    """The whole draw. Returns (rows, design) or (None, None) with an error string."""
    import numpy as np
    heal = _sibling("temporal_heal")
    dc = _sibling("detectability_curve")
    if stack_path is not None:
        heal.STACK = Path(stack_path)
    if not heal.STACK.exists():
        return None, None, f"{heal.STACK} not found (local mirror)"

    classes = size_classes(dc.BINS)
    heal_rows, overlays, err = heal.build()
    if err:
        return None, None, err

    d = np.load(heal.STACK)
    stack, inside, tf = d["stack"], d["inside"], d["transform"]
    years = [str(y) for y in d["years"]]
    min_cells = int(round(heal.MIN_AREA_M2 / (heal.CELL_M ** 2)))

    units, diag = collect_units(stack, inside, years, heal_rows, overlays, min_cells,
                                classes, heal.shift_mask)

    keys = universe(classes)
    kid = {k: i + 1 for i, k in enumerate(keys)}
    pop_f, pop_c = {k: 0 for k in keys}, {k: 0 for k in keys}
    for u in units:
        k = (u["tier"], u["gap_bucket"], u["size_class"])
        (pop_c if u["is_control"] else pop_f)[k] += 1

    alloc_f, nominal_f, refused, shortfall_f = allocate(pop_f, n_target, keys)
    # MATCHED: the control takes the fill's per-stratum count, capped at its own population.
    alloc_c = {k: min(alloc_f[k], pop_c.get(k, 0)) for k in alloc_f}
    shortfall_c = sum(alloc_f.values()) - sum(alloc_c.values())

    n_f = sum(pop_f.values())
    weights = {k: (pop_f[k] / n_f if n_f else 0.0) for k in alloc_f}

    picked = draw(units, alloc_f, seed, False) + draw(units, alloc_c, seed + 1, True)

    epsg = _epsg()
    rows = []
    for u in picked:
        r = dict(u)
        r["x"] = round(float(tf[2] + tf[0] * (u["col"] + 0.5)), 2)
        r["y"] = round(float(tf[5] + tf[4] * (u["row"] + 0.5)), 2)
        r["epsg"] = epsg
        k = (u["tier"], u["gap_bucket"], u["size_class"])
        r["stratum_id"] = kid[k]
        r["stratum_name"] = "|".join(k)
        r["adjudicable"] = 0
        r["adjudicator"] = ""
        r["adjudicator_dyear"] = ""
        r["adjudicate"] = 0
        r["present_in_filled_epoch"] = ""
        r["notes"] = ""
        rows.append(r)

    hits, adj_note = sample_adjudicable(rows, epsg)
    for r in rows:
        if r["unit_id"] in hits:
            r["adjudicable"] = 1
            r["adjudicator"], r["adjudicator_dyear"] = hits[r["unit_id"]]
    for uid in pick_adjudicate(rows, ADJUDICATE_SHARE, seed + 2):
        for r in rows:
            if r["unit_id"] == uid:
                r["adjudicate"] = 1

    rng = np.random.default_rng(seed + 3)
    order = rng.permutation(len(rows)).tolist()
    for r, o in zip(sorted(rows, key=lambda q: q["unit_id"]), order):
        r["blind_order"] = int(o) + 1
    rows.sort(key=lambda r: r["blind_order"])

    design = dict(classes=classes, keys=keys, kid=kid, pop_f=pop_f, pop_c=pop_c,
                  alloc_f=alloc_f, alloc_c=alloc_c, nominal_f=nominal_f,
                  refused=refused, shortfall_f=shortfall_f, shortfall_c=shortfall_c,
                  weights=weights, diag=diag, n_target=n_target, seed=seed,
                  years=years, heal_rows=heal_rows, adj_note=adj_note,
                  endpoint=endpoint_bound(),
                  min_area_m2=heal.MIN_AREA_M2, stack=str(heal.STACK), epsg=epsg)
    return rows, design, None


def _epsg():
    try:
        from phase4seg import config as cfg
        return int(cfg.ANALYSIS_GRID_EPSG)
    except Exception:                                              # noqa: BLE001
        return ""


def design_note(rows, D):
    """The design, written from COMPUTED values only — nothing here is typed by hand."""
    L = []
    A = L.append
    n_fill = sum(1 for r in rows if not r["is_control"])
    n_ctrl = sum(1 for r in rows if r["is_control"])
    n_adj = sum(1 for r in rows if r["adjudicable"] == 1)
    n_sub = sum(1 for r in rows if r["adjudicate"] == 1)
    # eps is only knowable where an INDEPENDENT modality rules, so the adjudicated
    # controls — not the whole control draw — set the floor under a resolvable lambda.
    n_ctrl_adj = sum(1 for r in rows if r["is_control"] and r["adjudicate"] == 1)

    A("HEAL FILL-SIDE LAUNDERING AUDIT — SAMPLE DESIGN")
    A(f"  instrument : qc/instruments/heal_fill_audit_sample.py  (seed {D['seed']})")
    A("  manifest   : phase4/qc/heal_fill_audit_sample.csv")
    A(f"  stack      : {D['stack']}  ({len(D['years'])} epochs: {', '.join(D['years'])})")
    A(f"  operator   : qc/instruments/temporal_heal.py  (min component "
      f"{D['min_area_m2']:.0f} m2 = one mature crown)")
    A("  unit       : one FILL COMPONENT (a crown-scale patch), not a 2 m cell.")
    A(f"  drawn      : {n_fill} fills + {n_ctrl} matched controls = {len(rows)}"
      f"   (target {D['n_target']} fills)")
    A("")
    A("-- CADENCE: what the operator did, per interior epoch " + "-" * 12)
    A(f"  {'epoch':8}{'bracket':14}{'tier':8}{'gap':>5}{'fills':>9}{'controls':>10}"
      f"{'untouched2':>12}")
    for e in D["diag"]["per_epoch"]:
        A(f"  {e['epoch']:8}{e['prev'] + '-' + e['next']:14}{e['tier']:8}"
          f"{e['gap_years']:>5}{e['n_fill']:>9,}{e['n_control']:>10,}"
          f"{e['n_untouched_two_sided']:>12,}")
    A("")
    A("  untouched2 = absences with BOTH aligned flanks present, >= the size floor, that the")
    A(f"  healer did not fill — the brief's literal control population. MEASURED total: "
      f"{D['diag']['untouched_two_sided']}.")
    A("  Filling exactly those is the operator's definition, which is why the control below")
    A("  is drawn from ONE-SIDED absences instead: the substitution is forced by the")
    A("  operator, not chosen for convenience, and the count above is how we know.")
    A("")
    # Whether the two stratification axes are independent is a property of the CADENCE,
    # not of this design — and on a stack where each tier occurs at one gap length they
    # are collinear, which no amount of allocation arithmetic can fix.
    by_tier = {}
    for e in D["diag"]["per_epoch"]:
        by_tier.setdefault(e["tier"], set()).add(gap_bucket_of(e["gap_years"]))
    if all(len(v) == 1 for v in by_tier.values()) and len(by_tier) > 1:
        pairs = "; ".join(f"{t} only at gap {sorted(v)[0]}"
                          for t, v in sorted(by_tier.items()))
        A("  COLLINEAR AXES on this stack — a property of the flight cadence, not of this")
        A(f"  design: {pairs}. Tier and gap length are therefore")
        A("  NOT separable here: a tier effect and a gap-length effect would be the same")
        A("  column. The two are still declared as separate axes because the density")
        A("  experiment breaks the collinearity; until it lands, read them as one.")
        A("")
    A("-- STRATA " + "-" * 56)
    A(f"  {'id':>4} {'stratum (tier|gap|size)':<28}{'N_fill':>9}{'W_h':>9}"
      f"{'nominal':>9}{'drawn':>7}{'N_ctrl':>9}{'ctrl':>6}")
    for k in D["keys"]:
        if D["pop_f"][k] == 0 and D["pop_c"][k] == 0:
            continue
        A(f"  {D['kid'][k]:>4} {'|'.join(k):<28}{D['pop_f'][k]:>9,}"
          f"{D['weights'].get(k, 0.0):>9.4f}{D['nominal_f'].get(k, 0):>9}"
          f"{D['alloc_f'].get(k, 0):>7}{D['pop_c'][k]:>9,}{D['alloc_c'].get(k, 0):>6}")
    A(f"  {'':>4} {'TOTAL':<28}{sum(D['pop_f'].values()):>9,}"
      f"{sum(D['weights'].values()):>9.4f}{sum(D['nominal_f'].values()):>9}"
      f"{sum(D['alloc_f'].values()):>7}{sum(D['pop_c'].values()):>9,}"
      f"{sum(D['alloc_c'].values()):>6}")
    A("")
    A(f"  Allocation: proportional to N_fill x tier oversample "
      f"({', '.join(f'{t} {OVERSAMPLE[t]:g}x' for t in TIERS)}), floor 2 per live stratum")
    A("  (below 2 the within-stratum variance is undefined), then CAPPED at population.")
    A("  Controls take the fill's per-stratum count, capped at their own population.")
    A("")
    A("-- REFUSED: strata with zero population " + "-" * 27)
    A("  These are NOT reweighted into their neighbours. A design that silently spreads an")
    A("  empty stratum's points reports a draw it did not make.")
    # Compressed per (tier, gap) SLAB — a union over gap buckets would read as though a
    # size class were missing everywhere when it is only missing from an absent slab.
    refused = set(D["refused"])
    live_tiers = {k[0] for k in D["keys"] if D["pop_f"][k] > 0}
    for t, (gl, _, _) in itertools.product(TIERS, GAP_BUCKETS):
        slab = [k for k in D["keys"] if k[0] == t and k[1] == gl]
        empty = [k for k in slab if k in refused]
        if not empty:
            continue
        if len(empty) == len(slab):
            why = ("no epoch has this (tier, gap) in the cadence"
                   if t in live_tiers else
                   f"no {t} epoch exists in this cadence")
            A(f"  {t + '|' + gl:<16} ALL {len(empty)} strata empty — {why}.")
        else:
            A(f"  {t + '|' + gl:<16} {len(empty)} of {len(slab)} empty: "
              f"{', '.join(k[2] for k in empty)}")
    if "REVIEW" not in live_tiers:
        A("  REVIEW is empty on the whole stack: every post-2016 bracket in this cadence")
        A("  also spans >= 3 years, so BLIND dominates it (temporal_heal.py::tier_for).")
        A("  The declared 2x REVIEW oversample therefore CANNOT be exercised until the")
        A("  density experiment lands — experiments/heal_infill_2017_2023.yaml.")
    A("")
    A(f"  Size classes below the sieve are empty BY CONSTRUCTION: a component of "
      f"{D['min_area_m2']:.0f} m2")
    A(f"  has equivalent diameter {equiv_diam_m(int(round(D['min_area_m2'] / (CELL_M ** 2)))):.2f} m, "
      f"so no unit can land under it.")
    A(f"  Shortfall from population caps: {D['shortfall_f']} fills, {D['shortfall_c']} "
      f"controls — reported, not redistributed.")
    A("")
    A("-- OLOFSSON WEIGHTS AND THE ESTIMATOR " + "-" * 29)
    A("  Population = the healer's own fill components. W_h = N_h / N over fills.")
    A("  Weighted laundering rate:      lambda_hat = sum_h W_h * (k_h / n_h)")
    A("  Variance (the convention of phase4_qc_design_power.py::estimate — within-stratum")
    A("  Var(p_h) = p_h(1-p_h)/(n_h - 1), a single binary outcome being the two-cell case")
    A("  of its multinomial covariance):")
    A("        Var(lambda_hat) = sum_h W_h^2 * p_h(1-p_h)/(n_h - 1)")
    A(f"        95% half-width  = {Z95} * sqrt(Var)")
    A("")
    A(f"  {'assumed p':>11}{'half-width':>13}{'  (weighted, at the realised allocation)'}")
    for p in (0.005, 0.01, 0.02, 0.05, 0.10):
        A(f"  {p:>11.3f}{stratified_halfwidth(D['alloc_f'], D['weights'], p):>13.4f}")
    A("")
    A("-- DETECTABLE EFFECT " + "-" * 46)
    n = n_fill
    ep_k, ep_n, endpoint = D["endpoint"]
    if endpoint is None:
        A(f"  ENDPOINT BOUND NOT READ — {ENDPOINT_SRC.name} is absent or carries no")
        A("  loss_laundered/loss_n trailer, so there is nothing to compare against. Run")
        A("  qc/instruments/heal_vs_gold.py and regenerate. No constant is substituted.")
    else:
        A(f"  The endpoint bound this replaces, READ from {ENDPOINT_SRC.name}: "
          f"{ep_k} of {ep_n}")
        A("  verified losses laundered -> exact one-sided 95% upper bound")
        A(f"  1 - 0.05^(1/{ep_n}) = {endpoint:.4f} ({100 * endpoint:.2f}%). Those {ep_n} are "
          f"spent: no draw")
        A("  on the panel can tighten it, which is why this audit samples the fills instead.")
    A("")
    A(f"  At n = {n} fills, k laundered, exact one-sided 95% upper bound "
      f"(Clopper-Pearson;")
    A("  k = 0 is G1's closed form 1 - 0.05^(1/n)):")
    A(f"  {'k':>4}{'k/n':>9}{'upper bound':>14}   verdict vs the "
      + (f"{100 * endpoint:.1f}% endpoint bound" if endpoint else "endpoint (UNREAD)"))
    kmax = None
    for k in range(0, 41):
        ub = cp_upper(k, n) if n else float("nan")
        if endpoint is not None and ub < endpoint:
            kmax = k
        if k in (0, 1, 2, 3, 5, 10, 20):
            verdict = ("—" if endpoint is None else
                       "tighter" if ub < endpoint else "NO IMPROVEMENT")
            A(f"  {k:>4}{(k / n if n else float('nan')):>9.4f}{ub:>14.4f}   {verdict}")
    A("")
    if endpoint is not None:
        A(f"  So the audit beats the endpoint bound for any k <= {kmax} of {n}, and at k = 0 it")
        A(f"  reports < {100 * cp_upper(0, n):.2f}% — a "
          f"{endpoint / cp_upper(0, n):.1f}x tightening.")
    A("  G1's teeth, quoted from Reports/LIT_HEALING_ANALOGUES_2026-09-08.md §7: the base")
    A("  loss rate is 3.47%, so a fill-side rate below 1% requires the heal to fill")
    A("  real-loss cells at under 29% of the rate it fills random cells.")
    A("")
    A("  THE SRS CAVEAT, stated because it is easy to miss: 1 - 0.05^(1/n) is a BINOMIAL")
    A("  bound and this draw is stratified with deliberate 2x oversampling. It applies")
    A("  exactly to the UNWEIGHTED sample rate. The city-level weighted rate carries the")
    A("  stratified variance above instead, and the two answer different questions.")
    A("")
    A("-- THE READER'S OWN ERROR RATE " + "-" * 36)
    A(f"  Control draw: {n_ctrl} units, matched stratum-for-stratum, from absences with")
    A("  EXACTLY ONE aligned flank present — the nearest untouched population at the same")
    A("  scale (see CADENCE above for why the literal both-flanks control is empty).")
    A("  Let eps = the rate at which the reader calls canopy ABSENT where it was present.")
    A("  Rogan-Gladen: lambda_hat = (p_obs - eps) / (1 - beta - eps), beta the miss rate;")
    A("  SE(eps) = sqrt(eps(1-eps)/m), and a lambda under Z*SE(eps) is UNDETERMINED, not")
    A("  zero (CLAUDE.md 3.5).")
    A("")
    A("  WHICH m, and this is the binding fact of the whole design: eps is only knowable")
    A("  where truth is known INDEPENDENTLY of the reader, i.e. on the ADJUDICATED rows —")
    A(f"  not on the {n_ctrl}-unit control draw as a whole. m is bracketed, not fixed:")
    A(f"    lower  m = {n_ctrl_adj}   adjudicated CONTROLS alone")
    A(f"    upper  m = {n_sub}   every adjudicated row, fills included — an adjudicated fill")
    A("                whose lidar reads PRESENT is as valid an eps observation as a")
    A("                control is, under the double-sampling reading")
    A("  Which of the two applies is settled only once the lidar is read, because only")
    A("  then is it known how many adjudicated rows carry a PRESENT truth at all.")
    A(f"  {'assumed eps':>12}{'SE at m=' + str(n_ctrl_adj):>14}{'floor':>9}"
      f"{'SE at m=' + str(n_sub):>14}{'floor':>9}   (floor = Z*SE)")
    for eps in (0.02, 0.05, 0.10):
        se_a = math.sqrt(eps * (1 - eps) / n_ctrl_adj) if n_ctrl_adj else float("nan")
        se_b = math.sqrt(eps * (1 - eps) / n_sub) if n_sub else float("nan")
        A(f"  {eps:>12.2f}{se_a:>14.4f}{Z95 * se_a:>9.4f}{se_b:>14.4f}"
          f"{Z95 * se_b:>9.4f}")
    A("")
    A("  THE ASYMMETRY THIS EXPOSES, and it is the most decision-relevant line in the note:")
    A(f"  n = {n_fill} fills buys a k/n bound near {100 * cp_upper(0, n_fill):.1f}%, while the "
      f"floor under a")
    A("  resolvable lambda sits several times higher. The bound and the floor are bought by")
    A(f"  DIFFERENT numbers — the {n_fill} fills and the adjudicated rows — and enlarging one")
    A("  without the other moves nothing. ADJUDICATE_SHARE is a chosen constant, not a")
    A("  sourced one: G1 says 'a sub-sample' and names no size. Raising it is Kam's call.")
    A("")
    A("  ASSUMED, and not testable inside this design: that the reader errs at the same")
    A("  rate on fills and on controls. The control's flanks differ, so a reader can tell")
    A("  the two apart — it is a DISCRIMINATION control (does the both-sides rule buy")
    A("  anything in the reader's eyes), not a blinded error-rate control. blind_order")
    A("  randomises presentation order only; it cannot blind the flanks.")
    A("")
    A("-- ADJUDICATOR SUB-SAMPLE " + "-" * 41)
    A(f"  adjudicable rows: {n_adj} of {len(rows)}; flagged for adjudication: {n_sub}"
      f"  ({ADJUDICATE_SHARE:.0%} target, stratified by tier and is_control)")
    A(f"  modality: {', '.join(f'{n} ({y})' for n, y, _ in LIDAR)}, "
      f"|epoch - modality| <= {ADJ_MAX_DYEAR} yr, coverage only.")
    if D["adj_note"]:
        A(f"  NOTE: {D['adj_note']}")
    A("  Without this step k/n bounds HUMAN-MODEL AGREEMENT, not laundering: a human")
    A("  re-reading the same ortho the model read is not independent of the model")
    A("  (G1 step iv-b). No CHM value is written to the manifest — that would hand the")
    A("  reader the answer.")
    A("")
    A("-- WHAT IS MEASURED, DERIVED, ASSUMED " + "-" * 29)
    A("  MEASURED: every population and cell count above, from the healer's own output on")
    A(f"            the {len(D['years'])}-epoch stack; the untouched-two-sided count; lidar coverage.")
    A("  DERIVED : the allocation, the weights, the bounds and half-widths — arithmetic on")
    A("            those counts under the stated formulas.")
    A("  ASSUMED : that reader error is equal on fills and controls; that a component's")
    A("            equivalent-area diameter is comparable to the crown polygons' diameter_m")
    A("            (same estimator, quantised to the 2 m lattice); that units are")
    A("            independent — they are not strictly, since one crown can be a fill in")
    A("            two epochs, which makes the binomial bound mildly optimistic.")
    A("  NOT MEASURED HERE: whether any fill is laundering. This instrument draws the")
    A("            sample and states the design; the human reads it.")
    return "\n".join(L)


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=N_TARGET, help="target FILL units to draw")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--heal", default=None,
                    help="epoch stack the healer reads (overrides temporal_heal.STACK)")
    ap.add_argument("--out", default=None, help="manifest CSV path")
    ap.add_argument("--design-out", default=None, help="design note path")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, D, err = build(a.n, a.seed, a.heal)
    if err:
        print(f"FATAL: {err}")
        return 2

    out = Path(a.out) if a.out else (QC / "heal_fill_audit_sample.csv")
    dout = Path(a.design_out) if a.design_out else (QC / "heal_fill_audit_design.txt")

    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    note = design_note(rows, D)
    if not a.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(buf.getvalue(), encoding="utf-8", newline="")
        dout.write_text(note + "\n", encoding="utf-8", newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}{out} — {len(rows)} rows")
    print(note)
    if not a.dry_run:
        print(f"\n  wrote {out}\n  wrote {dout}")
    print("\n  The manifest is a WORKSHEET: the reader fills present_in_filled_epoch "
          "(yes/no/unsure)\n  and notes. Everything else is design and must not be edited.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
