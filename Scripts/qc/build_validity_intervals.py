r"""Per-crown temporal validity intervals — the PoC deliverable (2026-08-27).

THE product of the project (CLAUDE.md: "Per-crown temporal validity intervals
for 222,435 individual tree crowns"), scoped here to the crowns intersecting
the sector strips. Everything below is SAMPLE-SCOPED and threshold-fixed; read
the caveats block the script prints before quoting any number.

ARM RAIL (rule 1). Intervals are built from ONE arm family — default
`fullext_sectors_v1`, the PoC recipe. Legacy/base2020/p2nir/noise arms are a
DIFFERENT recipe (different training labels, different operating points) and
are listed in the header as available-but-excluded. Mixing recipes inside one
crown's time series would attribute recipe differences to the tree. `--arm`
makes the choice explicit and re-runnable.

THREE-STATE PRESENCE (rule 2), never binary — the same discipline as the
0/1/255 masks (CLAUDE.md rule 6):
    cover >= --present-hi (0.5)   PRESENT     P
    cover <= --absent-lo  (0.15)  ABSENT      A
    between                       UNSURE      U   (never assigned to a class)
    NaN                           UNOBSERVED  -   (crown outside that year's
                                                  scored footprint, or <30
                                                  valid 1-m cells; NEVER 0)

INTERVAL (rule 3, CLAUDE.md rule 8 generalised to a ladder of years):
    valid_to   = latest PRESENT year
    valid_from = earliest PRESENT year with no ABSENT between it and valid_to
                 (i.e. the start of the final uninterrupted presence run)
`pattern` carries the per-year state codes in chronological order so any
crown's evidence is inspectable without re-reading the matrix.

UNCERTAINTY (rule 5) — MEASURED, not assumed. The five same-recipe 2021s
repeats (`cover_2021s_noise_r*`) are five independent draws of the same crown's
cover, so the run-to-run cover sigma is measured directly per crown instead of
being derived from the global recall sigma (recall sd .0100 is a mean over
millions of pixels and would badly understate per-crown spread). Measured
2026-08-27 over 27,508 crowns observed in all five repeats:

    cover band      median per-crown sd
    [0.00, 0.15)    0.0000     settled absent  — deterministic
    [0.15, 0.50)    0.0830     AMBIGUOUS       — ~90x noisier
    [0.50, 1.00]    0.0009     settled present — deterministic

So the noise lives almost entirely in the crowns the three-state rule already
refuses to classify. `--sigma-mode band` (default) applies that empirical
cover-conditioned sd to every cell of every year; `--sigma-mode crown` uses each
crown's own measured sd where it exists (falling back to the band model).
`sigma_fragile` = the crown's class changes when every cell is shifted by
+sd or by -sd.

THREE HONEST LIMITS ON THAT SIGMA:
  1. Measured on 2021s only (one modern 15.2 cm year) and assumed to transfer
     to every other year. Early/coarse years are almost certainly noisier, so
     the fragile fraction below is a FLOOR.
  2. Same seed (the engine has no --seed flag), so it captures hardware
     nondeterminism + threshold selection only — a LOWER BOUND on true
     retrain sigma. Every derived number inherits that label.
  3. A systematic +/-sd shift is not an adversarial test. `n_near_boundary`
     (per-crown count of observed years sitting within one sd of a cutoff) is
     reported alongside for the per-year view.

INPUT   data:phase4/qc/sector_campaign/crown_cover_matrix.parquet
        + crown_cover_matrix.columns.json   (from qc/phase4_crown_cover_matrix.py)
OUTPUT  data:phase4/qc/sector_campaign/crown_validity_intervals.csv
        data:phase4/qc/sector_campaign/crown_validity_intervals.gpkg
        (2020 crownV5 polygons joined, D: mirror first — same source as the
        matrix builder and the stable-crown miner)

New arm columns are picked up automatically: the arm's year list is discovered
from the column map, so re-running after a matrix rebuild (e.g. once
2024_fullext_sectors_v1 lands) needs no code change.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from phase4seg.names import clean_argv  # noqa: E402

DATA = Path(r"G:\My Drive\treedata")
CAMP = DATA / "phase4" / "qc" / "sector_campaign"
MATRIX = CAMP / "crown_cover_matrix.parquet"
COLMAP = CAMP / "crown_cover_matrix.columns.json"
OUT_CSV = CAMP / "crown_validity_intervals.csv"
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
CROWNS_FALLBACK = DATA / "inference" / "edmonds_crowns_2020.gpkg"

MIN_YEARS = 3                      # below this: INSUFFICIENT, never classified
# Empirical per-crown cover sd by cover band, measured from the five same-recipe
# 2021s repeats (see module docstring). Edges are (lo, hi_exclusive, sd).
SIGMA_BANDS = [(0.00, 0.15, 0.0000),
               (0.15, 0.50, 0.0830),
               (0.50, 1.01, 0.0009)]
# Classes. The five named in the PoC brief plus three the data forces: a crown
# can be present-with-unsure-gaps, never present at all, or all-unsure, and
# none of those honestly fit STABLE_PRESENT / ESTABLISHED / LOST / FLICKERING.
CLASS_ORDER = ["STABLE_PRESENT", "PRESENT_WITH_GAPS", "ESTABLISHED", "LOST",
               "FLICKERING", "ABSENT_ALL", "ALL_UNSURE", "INSUFFICIENT"]


def year_sort_key(y):
    """Chronological order for keys like 2000 / 2018s / 2019n / 2021s."""
    m = re.match(r"(\d{4})", str(y))
    if not m:
        raise SystemExit(f"cannot order year key {y!r}")
    return (int(m.group(1)), str(y))


def states_for(cov, present_hi, absent_lo):
    """cover row -> state codes; NaN stays UNOBSERVED. Cutoffs are inclusive
    on both ends per the docstring (>= hi PRESENT, <= lo ABSENT)."""
    st = np.full(cov.shape, "-", dtype="<U1")
    obs = np.isfinite(cov)
    st[obs & (cov >= present_hi)] = "P"
    st[obs & (cov <= absent_lo)] = "A"
    st[obs & (cov > absent_lo) & (cov < present_hi)] = "U"
    return st


def classify_row(states, years):
    """-> (cls, valid_from, valid_to, first_present, last_present)."""
    obs = [(y, s) for y, s in zip(years, states) if s != "-"]
    n_obs = len(obs)
    pres = [y for y, s in obs if s == "P"]
    if n_obs < MIN_YEARS:
        return "INSUFFICIENT", None, None, (pres[0] if pres else None), (pres[-1] if pres else None)
    hard = [(y, s) for y, s in obs if s in ("P", "A")]
    if not hard:
        return "ALL_UNSURE", None, None, None, None
    if not pres:
        return "ABSENT_ALL", None, None, None, None

    # interval: walk back from the last PRESENT, stop at the first ABSENT
    idx = {y: i for i, y in enumerate(years)}
    last_p = max(idx[y] for y in pres)
    first_of_run = last_p
    for i in range(last_p - 1, -1, -1):
        if states[i] == "A":
            break
        if states[i] == "P":
            first_of_run = i
    valid_from, valid_to = years[first_of_run], years[last_p]

    # runs of the hard (P/A) states decide the class; UNSURE never votes
    runs = [s for i, (_, s) in enumerate(hard) if i == 0 or s != hard[i - 1][1]]
    if runs == ["P"]:
        cls = "STABLE_PRESENT" if all(s == "P" for _, s in obs) else "PRESENT_WITH_GAPS"
    elif runs == ["A", "P"]:
        cls = "ESTABLISHED"
    elif runs == ["P", "A"]:
        cls = "LOST"
    else:
        cls = "FLICKERING"
    return cls, valid_from, valid_to, pres[0], pres[-1]


def classify_all(cov, years, present_hi, absent_lo):
    st = states_for(cov, present_hi, absent_lo)
    out = [classify_row(list(st[i]), years) for i in range(st.shape[0])]
    return st, out


def band_sigma(cov):
    """Cover-conditioned sd per cell (NaN cells -> NaN)."""
    sd = np.full(cov.shape, np.nan)
    for lo, hi, s in SIGMA_BANDS:
        sd[np.isfinite(cov) & (cov >= lo) & (cov < hi)] = s
    return sd


def main():
    ap = argparse.ArgumentParser(
        description="Per-crown temporal validity intervals from the crown cover matrix.")
    ap.add_argument("--matrix", default=str(MATRIX))
    ap.add_argument("--colmap", default=str(COLMAP))
    ap.add_argument("--arm", default="fullext_sectors_v1",
                    help="arm/tag family to build intervals from (default fullext_sectors_v1); "
                         "recipes are never mixed inside one crown series")
    ap.add_argument("--present-hi", type=float, default=0.50,
                    help="cover >= this is PRESENT (default 0.50)")
    ap.add_argument("--absent-lo", type=float, default=0.15,
                    help="cover <= this is ABSENT (default 0.15)")
    ap.add_argument("--sigma-mode", choices=["band", "crown", "off"], default="band",
                    help="band: empirical cover-conditioned sd (default); "
                         "crown: each crown's own measured sd where available; off: skip")
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--gpkg", action="store_true",
                    help="also write crown_validity_intervals.gpkg beside --out")
    a = ap.parse_args(clean_argv())

    import pandas as pd

    df = pd.read_parquet(a.matrix)
    colmap = json.loads(Path(a.colmap).read_text(encoding="utf-8"))
    arm_cols = {c: v["year"] for c, v in colmap.items()
                if v["tag"] == a.arm and c in df.columns}
    if not arm_cols:
        sys.exit(f"no columns for arm {a.arm!r} in {a.colmap}")
    years = sorted(arm_cols.values(), key=year_sort_key)
    if len(years) != len(set(years)):
        sys.exit(f"arm {a.arm!r} has duplicate years — a year must map to one column")
    cols = [c for _, c in sorted(((arm_cols[c], c) for c in arm_cols),
                                 key=lambda t: year_sort_key(t[0]))]
    other = sorted({v["tag"] or "(untagged)" for v in colmap.values() if v["tag"] != a.arm})

    print("=" * 72)
    print("  PER-CROWN VALIDITY INTERVALS  (PoC deliverable, SAMPLE-SCOPED)")
    print("=" * 72)
    print(f"  arm            : {a.arm}   ({len(years)} years: {', '.join(years)})")
    print(f"  EXCLUDED arms  : {', '.join(other)}")
    print(f"                   (different recipes — never mixed into one series)")
    print(f"  cutoffs        : PRESENT >= {a.present_hi}   ABSENT <= {a.absent_lo}"
          f"   (between = UNSURE, NaN = UNOBSERVED)")
    print(f"  crowns in matrix: {len(df):,}")

    cov = df[cols].to_numpy(dtype="float64")
    st, res = classify_all(cov, years, a.present_hi, a.absent_lo)

    cls = np.array([r[0] for r in res])
    n_present = (st == "P").sum(axis=1)
    n_absent = (st == "A").sum(axis=1)
    n_unsure = (st == "U").sum(axis=1)
    n_unobs = (st == "-").sum(axis=1)

    # ---- sigma fragility -------------------------------------------------
    frag = np.zeros(len(df), dtype=bool)
    near = np.zeros(len(df), dtype=int)
    crown_sd = np.full(len(df), np.nan)
    noise_cols = [c for c in df.columns if "_noise_r" in c]
    if len(noise_cols) >= 3:
        nv = df[noise_cols].to_numpy(dtype="float64")
        ok = np.isfinite(nv).sum(axis=1) >= 3
        with np.errstate(invalid="ignore"):
            crown_sd[ok] = np.nanstd(nv[ok], axis=1, ddof=1)
    if a.sigma_mode != "off":
        sd = band_sigma(cov)
        if a.sigma_mode == "crown":
            own = np.repeat(crown_sd[:, None], cov.shape[1], axis=1)
            sd = np.where(np.isfinite(own) & np.isfinite(cov), own, sd)
        hi = np.where(np.isfinite(cov), np.clip(cov + sd, 0, 1), np.nan)
        lo = np.where(np.isfinite(cov), np.clip(cov - sd, 0, 1), np.nan)
        _, res_hi = classify_all(hi, years, a.present_hi, a.absent_lo)
        _, res_lo = classify_all(lo, years, a.present_hi, a.absent_lo)
        frag = np.array([r[0] for r in res_hi]) != cls
        frag |= np.array([r[0] for r in res_lo]) != cls
        d_hi = np.abs(cov - a.present_hi)
        d_lo = np.abs(cov - a.absent_lo)
        with np.errstate(invalid="ignore"):
            near = (np.isfinite(cov) & ((d_hi <= sd) | (d_lo <= sd))).sum(axis=1)

    rows = pd.DataFrame({
        "crown_id": df["crown_id"],
        "sector": df["sector"],
        "area_m2": df["area_m2"],
        "arm": a.arm,
        "class": cls,
        "valid_from": [r[1] for r in res],
        "valid_to": [r[2] for r in res],
        "first_present_year": [r[3] for r in res],
        "last_present_year": [r[4] for r in res],
        "n_years_observed": (st != "-").sum(axis=1),
        "n_present": n_present, "n_absent": n_absent,
        "n_unsure": n_unsure, "n_unobserved": n_unobs,
        "pattern": ["".join(r) for r in st],
        "sigma_fragile": frag,
        "n_near_boundary": near,
        "noise_sd_2021s": np.round(crown_sd, 4),
    })

    print(f"\n  CLASS COUNTS  (of {len(rows):,} crowns)")
    for c in CLASS_ORDER:
        n = int((cls == c).sum())
        if n:
            f = int(frag[cls == c].sum())
            print(f"    {c:18s} {n:7,}  ({n/len(rows):5.1%})   sigma_fragile {f:6,}")
    # from `res`, not the DataFrame: a None valid_from becomes NaN there, and
    # NaN is truthy in Python — an `if f and t` guard would let it through.
    span = [year_sort_key(r[2])[0] - year_sort_key(r[1])[0]
            for r in res if r[1] is not None and r[2] is not None]
    if span:
        print(f"\n  median interval span : {int(np.median(span))} yr  "
              f"(mean {np.mean(span):.1f}, n={len(span):,} with an interval)")
    print(f"  sigma_fragile        : {frag.sum():,} ({frag.mean():.1%}) "
          f"[mode={a.sigma_mode}; LOWER BOUND — same-seed sigma, 2021s-measured]")
    print(f"  crowns with >=1 year within 1 sd of a cutoff: "
          f"{(near > 0).sum():,} ({(near > 0).mean():.1%})")

    # ---- cutoff sensitivity (rule 2) -------------------------------------
    print(f"\n  CUTOFF SENSITIVITY  (default {a.present_hi}/{a.absent_lo} vs alternatives)")
    print(f"    {'cutoffs':>14s}  " + "".join(f"{c[:11]:>12s}" for c in CLASS_ORDER[:6])
          + f"{'changed':>10s}")
    for ph, al in [(a.present_hi, a.absent_lo), (0.40, 0.10), (0.60, 0.20), (0.50, 0.25)]:
        _, r2 = classify_all(cov, years, ph, al)
        c2 = np.array([r[0] for r in r2])
        line = f"    {ph:.2f}/{al:.2f}".ljust(18)
        line += "".join(f"{int((c2 == c).sum()):12,}" for c in CLASS_ORDER[:6])
        line += f"{int((c2 != cls).sum()):10,}"
        print(line)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(out, index=False)
    print(f"\n-> {out}")

    if a.gpkg:
        import geopandas as gpd
        src = CROWNS if CROWNS.exists() else CROWNS_FALLBACK
        g = gpd.read_file(src, engine="pyogrio")
        g = g[g["crown_id"].isin(set(rows["crown_id"]))].merge(rows, on="crown_id")
        gp = out.with_suffix(".gpkg")
        g.to_file(gp, layer="crown_validity_intervals", driver="GPKG")
        print(f"-> {gp} ({len(g):,} polygons, from {src})")

    print("""
  CAVEATS — read before quoting any number above
    * SAMPLE SCOPE. Sector strips only: ~11% of city pixels, 38,642 crowns =
      17.4% of the 222,435 citywide. These are not city totals.
    * FIXED THRESHOLD 0.5. The PoC years were scored at a fixed 0.5 because
      their evaluate step was seeded-skipped, so no per-year deployed operating
      point exists (Method_Pipeline "Operating-point protocol").
    * SIGMA IS A FLOOR. Same-seed repeats, measured on 2021s only; true
      retrain sigma needs a --seed flag that does not exist yet.
    * EARLY-YEAR ABSENT CALLS ARE THE WEAKEST LINK. C-CAP over-paints
      residential canopy and the models under-call scattered backyard trees,
      so an ABSENT in a residential block circa 2000-2009 is the least
      trustworthy state in this table. FLICKERING + sigma_fragile crowns are
      the human-review queue, not a result.""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
