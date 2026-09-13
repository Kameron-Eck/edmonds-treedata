# Gated plan with branches — what happens when each kill fires

**Written 2026-09-12 at the close of the literature branch.** Companion to
`HANDOFF_SPATIOTEMPORAL_DATA_SESSION_2026-09-12.md` §4 (the order of measurements) and
`MATH_NARRATIVE_SPATIOTEMPORAL_CONSISTENCY_2026-09-12.md` (the formulas). Every gate below
already has a kill in the framework; this file adds the *branch* taken when the kill
fires, with the fallback's source so the data session does not have to re-derive it.
Nothing here is validated (CLAUDE.md 3.4c); each branch is a design with its own kill.

Convention: **PASS** = what the gate must show; **FAIL(x)** = a named failure mode; **→** =
the branch, with its source and grade; **cost** = what the branch gives up.

---

## Gate 0 — the convention check (ledger row 12)

**PASS.** One reader re-derives framework §2.1–§2.2 with `r` = recall, `f` = false-positive
rate, and every sign in the increment `ℓ_{t,b}` agrees with the brief's arithmetic.
**FAIL.** A sign or a swapped rate. **→** Not a branch: correct every formula that consumed
it (the narrative lists them: increment, CUSUM substitution, pseudo-label, noise floor)
and re-run nothing, since nothing has run. *Cost:* half a day.

## Gate 1 — the certified populations (11b)

**PASS.** `𝒞` reproduces PACC's `A_can` where both exist; `LOSS` mirrors `GAIN` under the
same height thresholds; both have cells in every distance band ≥ 4 m.
**FAIL(a): too few cells in a band.** **→** Merge adjacent bands for that population only,
keeping the 0–2 m band separate whatever its count (it is the sensitive one; §12.1).
*Cost:* coarser rates at the edge.
**FAIL(b): the two lidar surveys disagree on height thresholds** (point-density or
vegetation-season effects between 2005 and 2016). **→** Certify on the *intersection* of
both surveys' calls with a margin (canopy ≥ 5 m in both; non-canopy < 2 m in both, as
already written) and report the margin's cost in cell count; if the intersection empties
a band, that band is unanchored and takes the conservative rule of §7.2. *Cost:* fewer
anchors; honest.

## Gate 2 — the 2016 reproduction kill (ledger row 11a; framework §12.2)

**PASS.** Rates solved at the 2016 imagery epoch from the 2005 anchor, propagated eleven
years with the population's own `(q_g, q_l)`, match the direct rates scored against the
2016 CHM within the block-bootstrap interval; and the placebo `(q_g, q_l) × 10` fails.
**FAIL(a): mismatch on some strata only.** The population-own rates are wrong for those
strata (heterogeneity within the stratum, assumption (ii) of §12.2). **→** Add the next
covariate — land-use class (PACC's "impervious") after band — and re-solve; the mixture
algebra is unchanged. *Cost:* more rate cells, larger intervals.
**FAIL(b): mismatch everywhere.** The anchor-decay algebra itself is the problem (the
"certified 0 stays 0 at rate `a_k`" model). **→** Drop the two-population solve and fit
the **hidden multi-state model** directly: generator `Q` with `exp(QΔt)`, a
misclassification matrix `e_{rs}` with epoch and band as covariates, maximum likelihood
(Kalbfleisch & Lawless 1985; Jackson 2011 `msm`; framework §19.1, [Q]). It estimates
emission and transitions jointly on all epochs and needs no anchor decay, only the
certified cells as fixed-state observations. *Cost:* one fit instead of a closed form;
identifiability rests on the certified fraction (Gate 5b).
**FAIL(c): the placebo does not fire** (corrected and naive rates indistinguishable at
the true rates). **→** Report UNDETERMINED. Run the layer on the *direct* 2016-referenced
rates only, and flag every epoch after 2016 as unanchored in the output metadata. Do not
adopt the correction. *Cost:* the post-2016 half of the archive carries a stated,
uncorrected bias; the deliverable is smaller and honest.

## Gate 3 — the edge band (ledger row 14; framework §12.1)

**PASS.** The coregistration p95 admits the 0–2 m band: cells there are farther from the
boundary than the registration error, so `f_{t,0–2}` can be anchored.
**FAIL.** p95 exceeds 2 m for some epochs. **→** Two branches, both already designed:
(i) those epochs' 0–2 m cells take the conservative rule (§7.2: no evidence, chain
carries), and (ii) the **sliver screen** (Salas 2003; framework §14.9) removes change
clumps at the one-pixel-strip perimeter/area limit before any rate is read. If the
per-axis medians are large, correct them first (they are systematic; framework §17.1's
directional form gives the expected false change per axis) and re-measure p95. *Cost:*
the most sensitive band contributes no evidence in bad-registration years.

## Gate 4 — the emission bins (ledger row 1)

**PASS.** A `K` exists at which held-out log-likelihood on certified cells stops
improving, and the placebo shuffle lowers it.
**FAIL(a): likelihood keeps improving with `K`** (the emission is not a clean function of
`p`). **→** The soft observation carries covariate information; add band and crown-size
stratum to the bin index before adding `K`. *Cost:* more cells to estimate.
**FAIL(b): the shuffle does not lower it.** The certified labels carry no information the
bins can see — the anchors are wrong or the emission is degenerate. **→** Stop; this is a
Gate 1 problem. Do not proceed to the chain on a degenerate emission.

## Gate 5 — dependence, and the model of it (ledger row 6; framework §13.1, §15.1, §17.5)

**PASS.** The correlograms are measured per stratum and band; on a field simulated from
the fitted autologistic model the conclique residuals are uniform (Kaiser, Lahiri &
Nordman 2012); on the real strata they pass.
**FAIL(a): conclique test fails on the real strata.** The autologistic form is the wrong
dependence model (long-range or anisotropic error). **→** Keep Efron's identity (it holds
for any joint model, §13.1) and fall back to the **correlated block bootstrap** for `Ω`
with the block size from the measured range (Roberts 2017; Nordman & Lahiri 2004), giving
up the per-cell closed form. *Cost:* bootstrap refits instead of one flip per cell;
intervals only.
**FAIL(b): the fit passes with `𝒞` removed** (the leak test of §18.1). The emission is
fitting itself. **→** Not a branch; a defect. Find the leak (a covariate that encodes
the certified state, an epoch used on both sides) before anything else runs.
**FAIL(c): cross-epoch correlation is strong** (`G(t)` is most of the archive). **→** The
leave-out identity of §12.4 loses power; score on stratum means with the noise floor
reported, and lean on the conclique test rather than leave-out for adequacy. *Cost:*
weaker validation, stated.

## Gate 6 — the coupling and its baselines (ledger row 3; framework §3.2, §17.3, §17.10)

**PASS.** The joint fit `(β̂, γ̂)` beats `(0, γ̂)`, `(β̂, 0)` and `(0, 0)` on held-out
likelihood, block-honest, with the centered parameterisation.
**FAIL(a): `(0, γ̂)` ties the joint fit.** The coupling is inert on our data — a published
outcome twice over (Gräler 2016; Krähenbühl & Koltun 2011). **→** The chain alone is the
layer; the smoother question (Gate 7) is moot; report the tie as a result. *Cost:* none;
simpler layer.
**FAIL(b): `(β̂, 0)` ties the joint fit.** Time adds nothing beyond space — implausible
for a persistence process, so treat as a defect in the temporal term (interval handling)
before accepting. **→** Check the yearly-grid marginalisation; if the continuous-time
`exp(QΔt)` form (Gate 2b) was not used, use it.
**FAIL(c): `β` differs by resolution stratum** (row 21). **→** Expected; fit per stratum
and report the trend against `effective_cm`. *Cost:* none.

## Gate 7 — the smoother and the erasure radius (ledger rows 4, 22; framework §16.2, §20)

**PASS.** A radius exists between the smallest crown at or above the floor (2020 polygons
× lidar height) and the largest residual blob on `ℱ`; injected discs at that radius
behave (floor-size survive, blob-size erased) on real rasters.
**FAIL(a): the two size distributions overlap.** No radius separates real from noise.
**→** Drop the spatial smoother; use the chain's temporal evidence to reject blobs (a
blob present in one epoch and absent before and after is noise by the chain, not by
size). If Gate 6a already retired the coupling, this is automatic. *Cost:* no spatial
cleaning; temporal only.
**FAIL(b): the smoother chosen has no closed form** (mean-field). **→** Switch to TV-L1
or the TV flow, whose erasure is contrast-independent and closed-form (Chan & Esedoglu
2005; Bellettini et al. 2002), or characterise mean-field by injected discs and accept
that this characterises the operator, not the claim (§3.3). *Cost:* a different smoother
than the CRF literature's default.

## Gate 8 — the development prior (ledger row 9; framework §14.6, §17.4, §19.2)

**PASS.** The lag × distance surface fitted as a distributed-lag cross-basis on certified
losses is non-flat, and a null surface on shuffled dates is flat.
**FAIL(a): the null is not flat.** Leakage through the date shuffle (developments cluster
in space; shuffling dates alone leaves the spatial signal). **→** Shuffle dates *within*
spatial blocks, or permute development locations. If the null still is not flat, the
prior cannot be validated on this archive and is switched off. *Cost:* no development
prior; the chain treats developed and undeveloped cells alike.
**FAIL(b): too few certified losses for a surface** (42 gold losses; `LOSS` may be
larger). **→** Collapse to the two-term family (§14.6) with `k ≈ 5 y` as the starting
value and one amplitude; report the nested comparison as UNDETERMINED. *Cost:* a
parametric shape assumed, stated.

## Gate 9 — the building prior (ledger row 10; framework §14.7)

**PASS.** `σ_fp` measured against a lidar building reference; `Φ(d/σ)` with
`σ² = σ_reg² + σ_fp²` predicts the canopy fraction inside footprints at the lidar epochs.
**FAIL.** Under-prediction near footprints (the blur is wider than positional error —
overhang, not misregistration). **→** Two components: positional `Φ(d/σ)` plus an
overhang term measured from the CHM-over-footprint fraction at the lidar dates; if they
cannot be separated, use the empirical footprint canopy fraction per band as the prior
and drop the closed form. *Cost:* an empirical prior in place of a derived one.

## Gate 10 — the detector (ledger rows 2, 20; framework §12.3, §17.10, §19.6)

**PASS.** On null sequences simulated from the fitted chain, the Markov binary CUSUM
alarms at the stated global rate; the Bernoulli chart on the same sequences alarms above
it (the kill that shows dependence matters).
**FAIL(a): the Bernoulli chart does not alarm above the stated rate.** Dependence is weak
at the chart's scale — use the simpler Bernoulli chart with its exact run length
(Reynolds & Stoumbos 1999) and record the measured autocorrelation that justified it.
**FAIL(b): the global false-alarm constraint cannot be met at any threshold with twelve
steps.** **→** The chart is not the tool at `T = 12`; the chain's posterior change point
is (already the rule off the certified populations, §12.3). Report the run-length
limitation. *Cost:* no sequential chart at all; posterior dating only.

## Gate 11 — identifiability of the emission without lidar (ledger row 16; §19.4)

**PASS.** Three arms with conditionally independent errors exist for an epoch (agreement
rates satisfy the rank-one structure of Parisi et al. 2014).
**FAIL.** Arm errors are shared (the fusion finding says two are). **→** Hui & Walter's
two-population route (two arms, two strata of different prevalence), and otherwise
lidar-only anchoring as now. *Cost:* none relative to the current design; this gate only
adds anchors.

---

## The two failures with no branch

1. **Stationarity after 2016** cannot be tested without a third certified date. If a
   later lidar or a certified photo-interpretation date appears, run Anderson & Goodman's
   test (§14.1) first. Until then every post-2016 rate carries the assumption, stated.
2. **"Certified" carries the lidar's own error.** No kill in this document sees it,
   because every kill uses the same lidar. The only check is external: the gold points
   on 2016→2024, which are photo-interpreted and independent of the CHMs.

## Order of the branches

Gates 0–2 decide the estimator (closed form vs multi-state fit) before anything else is
built; Gate 5 decides the penalty (per-cell vs bootstrap) before any score is reported;
Gate 6 decides whether Gates 7 and 9 matter at all. Gates 8, 10 and 11 are independent
of each other and can run in any order once 2 and 5 have settled.
