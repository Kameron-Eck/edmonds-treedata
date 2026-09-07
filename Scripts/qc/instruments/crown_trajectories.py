"""crown_trajectories.py — the product: per-location canopy history, with its confidence.

WHAT HEALING IS FOR. Healed masks may never feed the annual canopy fraction — endpoints
cannot be healed, so the bias would not cancel and 2016->2024 would gain a manufactured
decline. What they CAN feed is per-location history: was a tree here, when did it go,
does the record support saying so. That is a different product from a citywide percentage
and it is the one a city acts on — siting, enforcement, canopy-ordinance cases.

THE UNIT is the frozen 2020 crown delineation (222,435 features). Per crown, per epoch,
cover is the healed canopy fraction inside the polygon, and the state ladder is the
project's own (CLAUDE.md 3.8, as `build_validity_intervals` uses it):

    PRESENT     cover >= 0.50
    ABSENT      cover <= 0.15
    UNSURE      between — never assigned to a class
    UNOBSERVED  no valid data in the polygon that epoch

THE CLAMP, and it is the reason this file exists rather than a one-liner. Healing is a
PIXEL predicate; `valid_to` is a CROWN-COVER predicate at 0.5. A healed cell can push a
crown from 0.45 to 0.55 and move a recorded removal date one epoch LATER than the raw
evidence supports. An adversarial review flagged exactly this as needing a clamp in the
consumer rather than an assertion in a test. So:

    valid_to  is computed from the RAW cover — the last epoch the unhealed data calls
              PRESENT. Healing may never extend the life of a tree.
    valid_from may use healed cover — filling a detection gap earlier in the series can
              only make the record of when a tree EXISTED more complete, and it cannot
              invent a removal.

Asymmetric on purpose, and in the safe direction: healing adds confidence about presence,
never about survival.

SCALES WITH THE ARCHIVE. Nothing here is tied to eight epochs. The trend8 subset leaves
50% of interior brackets BLIND (a bracket >= 3 years wide, which bigleaf maple coppice can
cross); at one epoch per calendar year the full catalog's 20 imagery years leave ZERO
brackets blind, because no consecutive-year gap reaches three. Production density does not
merely add rows — it converts the healer's weakest tier into its strongest.

Output: phase4/qc/crown_trajectories.csv (per-crown) + a summary the caller prints.

Run:  py -3.12 qc/instruments/crown_trajectories.py [--dry-run]
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

PRESENT_AT = 0.50
ABSENT_AT = 0.15
MIN_VALID_FRAC = 0.5          # a crown needs half its cells observed to be judged


def _state(cover, valid_frac):
    if valid_frac is None or valid_frac < MIN_VALID_FRAC:
        return "U"            # UNOBSERVED
    if cover >= PRESENT_AT:
        return "P"
    if cover <= ABSENT_AT:
        return "A"
    return "?"                # UNSURE — never assigned to a class


def classify(raw_states, healed_states):
    """One label per crown, from the HEALED series with the raw series as the check."""
    seen = [i for i, s in enumerate(healed_states) if s == "P"]
    if not seen:
        return "NEVER_SEEN"
    first, last = seen[0], seen[-1]
    after = healed_states[last + 1:]
    # A crown absent at every observed epoch after its last sighting is a candidate loss.
    if after and all(s in ("A",) for s in after if s != "U") and \
            any(s == "A" for s in after):
        return "LOST"
    if first > 0 and all(s in ("A", "U") for s in healed_states[:first]) and \
            any(s == "A" for s in healed_states[:first]):
        return "GAINED"
    gaps = sum(1 for i in range(first, last) if healed_states[i] == "A")
    if gaps:
        return "FLICKERING"
    return "PERSISTENT"


def build():
    import numpy as np
    sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))  # ledger: test_status_discovery
    from detectability_curve import STACK, load, per_crown_cover
    from temporal_heal import apply_heal, build as heal_build

    if not STACK.exists():
        return None, None, f"{STACK} not found (local mirror)"
    heal_rows, overlays, err = heal_build()
    if err:
        return None, None, err
    tiers = {r["epoch"]: r["tier"] for r in heal_rows}

    stack, inside, years, g, ids = load()
    n = len(g)
    healed_stack = []
    for i, yr in enumerate(years):
        ov = overlays.get(yr)
        healed_stack.append(stack[i] if ov is None
                            else apply_heal(stack[i], ov["heal"], ov["ignore"]))

    raw_cov = np.vstack([per_crown_cover(stack[i], ids, n, False)
                         for i in range(len(years))])
    heal_cov = np.vstack([per_crown_cover(healed_stack[i], ids, n, False)
                          for i in range(len(years))])
    # validity share per crown per epoch, to separate UNOBSERVED from ABSENT
    flat = ids.ravel()
    m = flat > 0
    idm = flat[m]
    tot = np.bincount(idm, minlength=n + 1).astype(float)
    vfrac = np.vstack([
        np.divide(np.bincount(idm, weights=(stack[i].ravel()[m] != 255).astype(float),
                              minlength=n + 1), np.maximum(tot, 1))
        for i in range(len(years))])

    diam = np.full(n + 1, np.nan)
    diam[g["idx"].to_numpy()] = g["diameter_m"].to_numpy()

    rows = []
    for cid in g["idx"].to_numpy():
        rs = [_state(raw_cov[i][cid], vfrac[i][cid]) for i in range(len(years))]
        hs = [_state(heal_cov[i][cid], vfrac[i][cid]) for i in range(len(years))]
        if all(s == "U" for s in hs):
            continue
        # THE CLAMP: valid_to from RAW presence only. Healing never extends a life.
        raw_p = [i for i, s in enumerate(rs) if s == "P"]
        heal_p = [i for i, s in enumerate(hs) if s == "P"]
        if not raw_p and not heal_p:
            continue
        valid_from = years[min(heal_p)] if heal_p else ""
        valid_to = years[max(raw_p)] if raw_p else ""
        label = classify(rs, hs)
        # confidence follows the weakest tier the crown's evidence leans on
        touched = [years[i] for i in range(len(years)) if rs[i] != hs[i]]
        conf = ("RAW" if not touched else
                "BLIND" if any(tiers.get(e) == "BLIND" for e in touched) else
                "REVIEW" if any(tiers.get(e) == "REVIEW" for e in touched) else
                "HEALED")
        # TERMINAL dominates every other confidence class, because it is not about how
        # the record was built — it is about whether the record can be corroborated AT
        # ALL. A loss whose only evidence is the final epoch has no later observation to
        # confirm it, and the final epoch is the series' worst-recall year (2024, 0.6955
        # against 2021's 0.826). Left unflagged this class swamps the product: 64% of
        # LOST crowns were last seen in the penultimate epoch, which is a detection
        # deficit wearing a removal's label. Reported with honest low confidence, never
        # deleted — deleting it is what the shipped persist filter did, and it discarded
        # every verified terminal loss.
        if label == "LOST" and raw_p:
            after = [s for s in hs[max(raw_p) + 1:] if s != "U"]
            if len(after) < 2:
                conf = "TERMINAL"
        rows.append({
            "crown_id": int(cid), "diameter_m": round(float(diam[cid]), 2),
            "raw_states": "".join(rs), "healed_states": "".join(hs),
            "valid_from": valid_from, "valid_to": valid_to,
            "class": label, "confidence": conf,
            "epochs_healed": ",".join(touched),
        })
    return rows, {"years": years, "tiers": tiers}, None


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, meta, err = build()
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = list(rows[0].keys())
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    cls = collections.Counter(r["class"] for r in rows)
    conf = collections.Counter(r["confidence"] for r in rows)
    for k, v in sorted(cls.items()):
        buf.write(f"# class_{k},{v}\n")
    for k, v in sorted(conf.items()):
        buf.write(f"# conf_{k},{v}\n")
    buf.write(f"# n_crowns,{len(rows)}\n")
    buf.write(f"# epochs,{'|'.join(meta['years'])}\n")
    if not a.dry_run:
        (QC / "crown_trajectories.csv").write_text(buf.getvalue(), encoding="utf-8",
                                                   newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/crown_trajectories.csv — "
          f"{len(rows):,} crowns over {len(meta['years'])} epochs")
    print(f"\n{'class':14}{'crowns':>10}{'share':>8}")
    for k, v in cls.most_common():
        print(f"{k:14}{v:>10,}{100 * v / len(rows):>7.1f}%")
    print(f"\n{'confidence':14}{'crowns':>10}{'share':>8}")
    for k, v in conf.most_common():
        print(f"{k:14}{v:>10,}{100 * v / len(rows):>7.1f}%")
    lost = [r for r in rows if r["class"] == "LOST"]
    print(f"\n  LOST crowns carry valid_to from RAW cover only — healing never extends a "
          f"life.\n  {len(lost):,} lost; last-seen years: "
          f"{dict(sorted(collections.Counter(r['valid_to'] for r in lost).items()))}")
    term = [r for r in lost if r["confidence"] == "TERMINAL"]
    print(f"\n  Of those, {len(term):,} ({100 * len(term) / max(len(lost), 1):.0f}%) are "
          f"TERMINAL — their only evidence is the final epoch, which has no")
    print("  later observation to corroborate it and is the series' worst-recall year "
          "(2024, 0.6955\n  against 2021's 0.826). Reported at low confidence, NEVER "
          "deleted: the shipped persist\n  filter deleted this class and discarded every "
          "verified terminal event.")
    print(f"  CORROBORATED losses (>= 2 later observations agree): "
          f"{len(lost) - len(term):,}")
    print("\n  This is per-location HISTORY, not a canopy percentage. Healed masks must "
          "never\n  feed the annual fraction series — see temporal_heal.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
