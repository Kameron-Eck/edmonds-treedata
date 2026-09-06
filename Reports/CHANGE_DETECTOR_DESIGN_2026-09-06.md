# REAL-LOSS CHANGE DETECTOR — SYNTHESIS

**Corrections to the brief first** (each changed something downstream):

- **There is no 2022 layer.** The stack's epochs are 2009, 2011s, 2013, 2015, 2016, 2019, 2021, 2024 — gaps of 1–3 years. Your 2021/2022/2023 example is illustrative only; any design must handle irregular gaps.
- **Gold counts:** 1169 verified no-change (not 1155), 42 losses, 2 gains (not 7) — arbitrated by re-deduplicating the label+verify logs. No script pins this dedup; that's why three analysts got three counts.
- **"41/42 corroborated" is a 10 m-halo convention.** I verified the file myself this session: 36 `in_loss` + 5 `within_10m` + 1 miss. Pixel-exact is 36/42. Both numbers are true; never print one without the convention.
- **"2.2 m registration" is 2013s, not a trend8 year.** The operative per-year quantity is p68 scatter: 0.86 m (2021) to 3.94 m (2013) — scatter is uncorrectable and becomes evidence width, not a shift to fix.
- **The smoothing trap has no fact home in the repo.** Both referees reproduced it fresh from the cached stack (it's real — numbers below). Per the measurement contract it needs an instrument + gated CSV before anything cites it again.
- I verified directly: the shipped rule is `persist = loss & ~c21` (`Scripts/qc/instruments/trend8_hotspots.py:56`).

---

## 1. Your shape-borrowing question, answered

**Neighbors may certify and weight a middle year. They must never overwrite it. And shape-consensus is a flicker detector, not a loss detector — those are opposite instruments.**

Measured (Design 2, injection tests on the real stack): a neighbor-consensus deviation statistic fires on flicker at 0.624 and on real sustained events at 0.025. A sustained 50% cut of a stand is caught **81% of the time by a level-step statistic and 2.9% of the time by consensus**. Mechanism: consensus deviation is a *curvature* measure, and a real loss is a *step* — flat before, flat after, zero curvature except at the drop. The more sustained (i.e. the more real) the loss, the less shape-consensus can see it. Your worry about half-cut stands was exactly right: neighbors vote the cut half back.

Why overwriting specifically is poison — the mechanism behind the measured smoothing trap:

1. **A neighbor "vouching" mostly votes its own threshold placement into the middle year.** Each year's mask sits at a per-delivery operating point (2016 detects stable canopy at r=0.988; 2024 at 0.913; 2015/2019, 2016's temporal neighbors, are the two *worst* years). Median-3's per-year correction correlates **−0.999** with deviation-from-neighbor-mean — it is literally a machine for regressing the best-calibrated year toward its worst-calibrated neighbors. Corrections run up to 3.4 pp/year against a total 8-year signal of ~2 pp.
2. **Endpoints can't be smoothed, so the bias never cancels.** Every headline estimate differences a smoothed interior year against an unsmoothed endpoint. That's how median-3 turned −3.49 raw into −0.59 against human truth −2.21 ± 1.10 — past truth from the other side.
3. **Any persistence rule censors the last epoch.** 13 of the 42 human-verified losses are 2021→2024 events. No later year exists to corroborate them. The shipped `~c21` rule deletes **all 13** by construction. A "wait for confirmation" rule discards the most recent — most policy-relevant — third of the inventory.

When neighbors **can** vouch: interior years, and only as *evidence weighting*. The one head-to-head case that is exactly your scenario — pid 923, code `1,1,1,1,1,0,1,0` (a 2019 dropout inside a real 2021→2024 loss) — is won outright by the model that lets a weak year be weak without letting it veto (HMM emission weighting: certified, p=1.000) and missed by 0.002 by the plain slope. **Your instinct is right in its principled form: neighbors inform how much a year's testimony counts, never what it says.**

One caveat neither of us anticipated: **the trap is spatial too.** pid 815 — a human-verified single-crown removal at the edge of a surviving stand — is missed by *both* designs, because both average over a window and the surviving spatial neighbors vote the removed crown back. Signal and noise share an address in space as well as time.

## 2. Recommended design (hybrid), calibration, gates, cost

The referees converged on something neither design proposed alone, and it's cheaper than either.

**The decisive measurement (Referee 2, Olofsson-weighted precision — the axis the atlas actually consumes; truth gross loss 2.29 pp = 56 ha):**

| rule | weighted precision | recall |
|---|---|---|
| shipped persist filter | 0.236 | 55% |
| raw two-epoch rule | 0.249 | 86% |
| **raw rule + guarded step-shape certifier** | **0.431** | 69% |
| HMM + certifier (best tier) | 0.598 | 67% |
| D2 slope + certifier | 0.535 | 64% |

60% of the total gain comes from bolting a **step-shape certifier** onto the existing rule — ~5 lines on the already-cached 2 m stack, no model, no fitted parameter, seconds of compute. Once the certifier is attached, HMM vs slope is statistically empty (difference +0.063, P=0.755). So:

**Build, in dependency order:**

1. **Freeze the gold set** — a 20-line writer producing `panel_a_gold.csv` from the label/verify logs with pinned dedup semantics. Blocker for everything; ends the 1155/1169/1170 drift.
2. **Port the certifier as a repo instrument** (both prototypes currently live only in session scratch — every number here is unreproducible from repo+lake until this lands). Per unit: 8-point cover trajectory → one-break-vs-flat test → certified if break-shape AND amplitude drop >0.2. Three mandatory fixes found in audit: an `RSS1==0` guard (**50.6% of the city has zero residual variance → degenerate p=0**; the certifier is a *shape+amplitude* test, not a significance test — a port that drops the amplitude gate fires on 47% of the map); an **empirical null** from the same-flight twin + the four hard-negative parcels, replacing the nominal F-distribution; unit = frozen 2020 crowns where possible, 12 m cells otherwise (connected-component "stands" percolate — one component is 221.7 ha — and are dead).
3. **Tiered output**, per unit: **CERTIFIED** (fires, weighted precision ~0.43–0.60) / **PROBABLE** (raw rule fires, uncertified — the human review queue) / **REVIEW-TERMINAL** (2021→2024 events, structurally uncorroborable, 31% of real loss — reported with honest low confidence, never deleted) / **BLIND** (canopy never or always visible — pids 8, 356; the ceiling is 40/42 for any mask-based detector) / **EVENT-NOT-LOSS** (clear-then-regrow trajectories — 77.6 ha citywide have this shape; a real event, not a persistent loss, flagged rather than silenced).
4. **Only then decide the model question.** The HMM's marginal +0.169 over the fit-free certifier was measured with emissions fitted on the same gold it's scored on — a handicapped comparison. Before crediting it: refit emissions per fold (~1 hour), and **declare the emission reference** (Panel A stable-canopy gives r≈0.99; C-CAP gives 0.70–0.83 — same symbol, 3× different emission width, currently unstated).

**Calibration plan — which gold measures what:** emission/noise rates → hard-negative parcels + same-flight twin + duplicate pairs (never the loss gold); transition rates → Panel A human flows (never EM'd on the stack); detection thresholds → the frozen no-change null; certifier null → twin + parcels, empirically. The 42+1169 are **spent** — development set forever.

**Confirmatory protocol (pre-register before any labeling):** the ~60-cell UA spot check already queued in WORKPLAN, drawn from the certified tier — a direct same-interval precision estimate, Kam-minutes. Plus a fresh Panel-A-protocol draw enriched on detector fires, sized ~150 positives — because with 42 positives, held-out recall has **sd 7.3 pp**, so no recall difference under ~10 pp is resolvable, ever, on the current set. Both designs' proposed confirmatory sets fail: Panel B and `certified_change_cells` are 2005→2016 (outside the validated interval), K1 labels state, not change.

**Pre-registered gates:** weighted precision beats **0.431** (the fit-free certifier, not the 0.249 raw rule), paired bootstrap P≥0.95 · gross loss and gross gain scored **separately** against 2.29/0.071 pp — never a net, because every estimator on this stack gets its net right by cancellation · FP reported in the 25–75%-cover stratum (where it runs 5–15%, 2–6× the diluted city rate; 420 of 1169 no-change points can't produce a false loss at all) · 0 fires on hard-negative parcels · bait fires ≤ raw's 3/9 · terminal-class recall ≥10/13 (shipped rule: 0/13) · certified area within 1.5× of 2.29 pp, kill at 2× · every recall number printed with ±7.3 pp.

**Cost:** steps 1–2 are hours. One-time 2 m prob-raster stack: 19.4 min, 106 MB — for triage and per-year calibration only (discrimination value measured at +0.006 AUC, CI spans zero — the matched cut already extracted the information). **Crown-level output is blocked**: it needs citywide 1 m trend8 cover sidecars that don't exist (~half-day build); the existing crown matrix is the wrong arm and covers 17% of the city.

## 3. What it beats — exactly

The incumbent is worse than we thought. Measured: the persist filter changes weighted precision by **−0.010 (P=0.426) — statistical zero — while deleting 100% of the terminal third of verified losses.** It is a pure recall tax. And the atlas's flagship 1.53 ha hot-spot (cluster 2512) is **0% certified**: its trajectory (canopy 0.75 in 2013, 0.07 in 2015, 1.00 in 2016, 0.11 in 2019) contains a physically impossible resurrection — at least one epoch's mask is provably wrong there.

The new detector adds: precision 0.24→0.43 with no model (0.53–0.60 with one); terminal-loss recall 0→77%; **0/9** fires on the bait set (losses humans demoted on review) vs raw's 3/9; certified fired area landing near truth's 56 ha instead of 224 (raw) or 113 (persist); break-year distribution reproducing the post-2016 acceleration unforced; and honest tiers instead of silent deletion. One caveat on every area claim: the sample quantum is **5.47 ha per stable_other point** and 6 of 42 losses carry 73.5% of the area weight — "2.24 vs 2.29 pp" is one-fifth of one sample point, never evidence of level calibration.

## 4. Failure modes that survive, and their bounds

- **Terminal 2021→2024 events (31% of real loss):** nothing on this stack can corroborate them. Bounded by the REVIEW tier; fixed only by a 9th epoch. The two designs fail it oppositely — the HMM's asymmetric prior is itself a soft persistence rule (discounts terminal events 4.1×), the slope gives the worst-calibrated year 72% of the leverage.
- **Single-crown loss inside a surviving stand (pid 815):** both designs miss it via spatial borrowing. Bound: edge-adjacent recall runs 67–76% vs 81–90% deep. Crown-unit scoring is the mitigation, currently blocked on the sidecars.
- **Sparse canopy (cover <50%):** recall 14–43% across configurations. Report as low-confidence, don't pretend.
- **Clear-and-regrow:** invisible to both designs (77.6 ha of that shape citywide); worse, the HMM asserts P(canopy)=0.97 across years of verified absence. Bounded by the EVENT-NOT-LOSS flag.
- **Gap blindness:** an event fully inside the 2016→2019 or 2021→2024 gap never enters any mask. Stack limit, no fix.
- **Pre-2016 rail:** no validated null exists before 2016, and the HMM run backward *fabricates* a 15-year trend (raw −2.13 pp → HMM −4.86, prior-driven at the endpoints). **Atlas scope is 2016→2024, hard.** Panel A stays the pace authority; this detector owns WHERE only.

## 5. Referee disagreements

- **"The HMM never rewrites a year" — Design 1 loses.** Referee 1 measured it: the HMM's per-year corrections correlate 0.858 with median-3's and it flips *more* cell-years than median-3. Its genuine distinctness is being two-sided (cuts false loss AND false gain) and reaching endpoints — it escapes the trap's consequence, not its mechanism. Its net also sweeps −1.5 to −3.6 and flips sign purely under the prior, which was fit from the truth it reproduces.
- **Design 2's 115 ha anchor — Referee 1 wins.** That number is the persist rule's own output (112.9 ha), not independent map loss (224.3) and not truth (56). Its "precision ≥1.00" rows and kill criterion #6 are invalid; measured precision at its chosen operating point is 0.32.
- **Chow as significance test — Referee 2 wins.** Degenerate p=0 on half the city; keep it as a shape+amplitude certifier with an empirical null.
- **Genuinely unresolved:** D1's rule-fill −9.97 vs R1's reproduction −5.26 (unreproduced number — don't cite); the emission reference (C-CAP vs Panel A); the HMM's +0.169 pending per-fold refit; and D1's "256-code ceiling" claim, contradicted by pid 815 — spatial aggregation does break code ties, sometimes into misses. The two referees' precision tables agree within noise; I cite R2's (it carries CIs).

**Your three action items:** (a) one chip-pair look at cluster 2512 before the atlas ships — minutes, and it decides whether the current flagship hot-spot is real; (b) approve the gold-freeze writer + certifier port (hours, the shippable win); (c) pre-register the gates above before any new labeling spends fresh gold.