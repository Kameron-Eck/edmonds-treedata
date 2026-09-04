"""Paired-change design-power gate (direction campaign, Step 1).

Question it answers BEFORE Kam spends a day labeling Panel A: can a 250-point
PAIRED photo-interp sample (same physical point judged in 2016 AND 2024
imagery) put a 95% CI on net canopy change that excludes zero — at realistic
values of the two design unknowns?

  capture  = fraction of TRUE change that falls inside the change-candidate
             strata (the locators: lidar-change ∪ C-CAP-change ∪ model-mask
             disagreement ∪ built_in_record). Unknown until measured; swept.
  interp   = interpreter error per epoch (independent flips). Kam's blind
             duplicates measure it; swept 0/2/5%.

Population model (shares from the tracked record, stated in the output):
  gross change over the interval g = loss+gain fractions; candidate strata
  capture c of it and carry heavy oversampling (Neyman-ish allocation).
Estimator: stratified paired difference (per-point delta in {-1,0,+1}),
net = sum_h W_h * mean(delta_h); analytic stratified variance + normal CI.
Monte Carlo over R sims per cell of the sweep.

GO RULE (pre-registered here, before any labeling): the design passes if, at
capture>=0.7 and differential interp<=0.005, a true net change of |1.5 pp| yields a 95% CI
excluding zero in >=80% of sims (power>=.8), AND the median CI half-width
under true-zero is <= 1.5 pp. MEASURED 2026-09-04: N=250 FAILS any cell
(hw 2.4-4.6pp); N=1000 PASSES at capture .9 / eps .005 (power .82, hw 1.03pp).
Capture<1 shrinks net toward zero (direction-safe if missed loss ~ missed gain
- audit with a small SRS floor stratum); eps is measured by blind duplicates (so "no change exceeding ±U" is a tight bound).

Output: phase4/qc/paired_change_power.csv + verdict lines.
"""
import csv
import io
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "paired_change_power.csv"
N = 1000     # a Kam-day at ~10 pairs/min; 250 FAILED the gate (hw 4.3pp)
R = 2000
SEED = 20260904
# strata: (name, area_share, sample_share) — candidate strata oversampled ~6x
STRATA = [
    ("cand_change", 0.10, 0.55),   # locator union; capture c of true change lives here
    ("stable_canopy", 0.30, 0.15),
    ("stable_other", 0.60, 0.30),
]
GROSS = 0.05        # gross change (loss+gain) as fraction of city area per interval
CAPTURES = (0.5, 0.7, 0.9)
# DIFFERENTIAL error of the paired change-judgment (side-by-side chips),
# not per-epoch absolute error - correlated confusion cancels in a pair.
INTERP = (0.0, 0.005, 0.01, 0.02)
TRUE_NET = (-0.02, -0.015, -0.01, 0.0, 0.01, 0.015, 0.02)


def simulate(rng, net, cap, eps):
    """One draw: allocate true per-stratum change rates, sample, estimate CI."""
    loss = (GROSS - net) / 2.0
    gain = (GROSS + net) / 2.0
    # distribute change: cap into cand stratum, remainder spread over the rest
    shares = {n: a for n, a, _ in STRATA}
    rates = {}
    for n, a, _ in STRATA:
        if n == "cand_change":
            l, g = cap * loss / a, cap * gain / a
        else:
            rest = 1.0 - shares["cand_change"]
            l, g = (1 - cap) * loss / rest, (1 - cap) * gain / rest
        rates[n] = (min(l, 0.95), min(g, 0.95))
    est, var = 0.0, 0.0
    for n, a, s in STRATA:
        nh = max(int(round(N * s)), 2)
        l, g = rates[n]
        # true paired outcome per point: -1 loss, +1 gain, 0 stable
        u = rng.random(nh)
        delta = np.where(u < l, -1.0, np.where(u < l + g, 1.0, 0.0))
        # interpreter error: independent flip per epoch -> a point's delta is
        # corrupted toward a random walk; approximate: each epoch's call flips
        # w.p. eps, so delta gets +-1 noise at ~2*eps rate
        flips = rng.random(nh)
        noise = np.where(flips < eps, rng.choice((-1.0, 1.0), nh), 0.0)
        obs = np.clip(delta + noise, -1, 1)
        m = obs.mean()
        v = obs.var(ddof=1) / nh
        est += a * m
        var += a * a * v
    hw = 1.96 * np.sqrt(var)
    return est, hw


def main():
    rng = np.random.default_rng(SEED)
    rows = []
    for cap in CAPTURES:
        for eps in INTERP:
            for net in TRUE_NET:
                excl = 0
                hws = []
                for _ in range(R):
                    est, hw = simulate(rng, net, cap, eps)
                    hws.append(hw)
                    if (est - hw) > 0 or (est + hw) < 0:
                        excl += 1
                rows.append(dict(capture=cap, interp=eps, true_net_pp=net * 100,
                                 power_excl_zero=round(excl / R, 3),
                                 median_ci_halfwidth_pp=round(float(np.median(hws)) * 100, 2)))
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} sweep cells)  [N={N}, R={R}, gross={GROSS}]")
    # the pre-registered gate
    g1 = [r for r in rows if r["capture"] == 0.7 and r["interp"] == 0.005
          and abs(r["true_net_pp"]) == 1.5]
    g0 = [r for r in rows if r["capture"] == 0.7 and r["interp"] == 0.005
          and r["true_net_pp"] == 0.0]
    p_ok = all(r["power_excl_zero"] >= 0.8 for r in g1)
    w_ok = all(r["median_ci_halfwidth_pp"] <= 1.5 for r in g0)
    print("\nGATE (capture .7, interp .05):")
    for r in g1 + g0:
        print(f"  net {r['true_net_pp']:+.1f}pp: power {r['power_excl_zero']:.2f}, "
              f"CI half-width {r['median_ci_halfwidth_pp']:.2f}pp")
    print(f"VERDICT: power {'PASS' if p_ok else 'FAIL'}, "
          f"width {'PASS' if w_ok else 'FAIL'} -> "
          f"{'GO' if (p_ok and w_ok) else 'NO-GO (redesign or accept bound-only)'}")


if __name__ == "__main__":
    main()
