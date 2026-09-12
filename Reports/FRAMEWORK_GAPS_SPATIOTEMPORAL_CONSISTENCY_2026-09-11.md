# Spatio-temporal consistency — framework and the mathematics still open

**Status: DESIGN-STAGE. UNVALIDATED. Nothing here is a measurement on our data.** This
document assembles the halves the literature supplies into one framework and names, as
precisely as it can, what is still ours to derive or measure. Written 2026-09-11. Owner:
Kam. It sits under the brief (`TEMPORAL_SPATIAL_CONSISTENCY_BRAINSTORM_2026-09-10.md`, the
home of every measured number about our stack — cited as *brief §x*) and the review
(`LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md`, the home of every citation — cited
as *review §x*). **An unprefixed § is a section of this document.** This file carries no
bibliography and restates no measured number as its own; where a number appears it is
cited to its home.

**Every equation below is in one of three bins, and the bin is marked:**

| Bin | Means |
|---|---|
| **[Q]** | Quoted from a paper the review fetched and graded PRIMARY; the review section is cited |
| **[S]** | A paper's result under *this document's* substitution of our objects (r, f, the 0/1/255 mask, the probability raster). The paper did not do this. |
| **[D]** | This document's own derivation. |

Every [S] and every [D] is unvalidated under CLAUDE.md 3.4c and names, in §11, the
independent check that would validate it. This document does not perform any of those
checks, and per 3.4c its author does not score its own proposal.

---

## 1. Objects and notation

- Cells `i = 1..N` on the 2 m analysis grid; `N ≈ 13.3 M` (brief §2.3). Epochs
  `t = 1..T`, `T = 12`, 2009–2024 (brief §1).
- Latent state `z_{i,t} ∈ {0, 1}` (not canopy / canopy).
- Hard observation `x_{i,t} ∈ {0, 1, ⊘}`, `⊘` = IGNORE, from the mask
  (`phase4seg/postproc.py::threshold_and_clean`). Soft observation
  `p_{i,t} ∈ [0, 1] ∪ {⊘}` from the probability raster written by
  `phase4seg/core.py::step_inference`: uint8, `k ∈ 0..254 → p = k/254`, `255 = ⊘`. The
  raster is kept per epoch alongside the mask; the float logits are not (session code
  check, 2026-09-11).
- **Per-epoch eyesight, in the brief's convention:** `r_t = P(x = 1 | z = 1)` is
  **recall**, `f_t = P(x = 1 | z = 0)` is the false-positive rate (brief §2.3: "r ≈ 0.61,
  f ≈ 0.05"; the emission gate "f 0.011–0.082 < r"). The miss rate is `1 − r_t`. *The
  round-3 agents wrote r for the miss rate; every formula below has been re-expressed in
  the brief's convention. That translation is [S] and is the first thing to check (§11
  row 12).*
- Transitions `q_loss = P(z_{t+1} = 0 | z_t = 1)`, `q_gain = P(z_{t+1} = 1 | z_t = 0)`.
  Pre-registered `q_loss = 0.02` (brief §2.3); the review's recommendation (review §6
  item 2) is to estimate both from the certified populations instead.
- Certified populations (brief §2.2): `𝒢` = lidar-certified GAIN 2005→2016 (46,805
  cells), `ℱ` = lidar-certified FLAT (40,609 cells), on the sample blocks. Gold (brief
  §2.4): 1,214 points = 1,170 no-change / 42 loss / 2 gain, ruling on 2016→2024, no
  false-positive class.
- Rates in hand (brief §2.3): C-CAP-2021- and C-CAP-2016-referenced `(r_t, f_t)` for all
  twelve tags at the delivered cut. **Lidar-referenced rates do not exist yet.** Everything
  below runs on the C-CAP rates until they do, and C-CAP overestimates canopy (brief §4.3
  item 2).
- **Revised 2026-09-12 (§12):** the rates are indexed by epoch *and* distance band,
  `(r_{t,b}, f_{t,b})`; a certified-canopy population `𝒞` (PACC's `A_can`, MASTER §3a) is
  added; transitions are per calendar year and per population, estimated by §12.2, not
  pre-registered. Read every `(r_t, f_t)` in §2–§8 as `(r_{t,b}, f_{t,b})`.

---

## 2. The per-cell temporal chain (brief §4.1, axis 1)

### 2.1 What one observation is worth — the evidence increment

With hard observations and known `(r_t, f_t)`, the log-likelihood-ratio increment for
canopy at epoch `t` is **[S]** (form: Itkin eq. 2 and Cor. 1(ii), review §4.12.2; the
paper carries no `(r, f)` symbols):

```
ℓ_t(x) =  log( r_t / f_t )                 if x = 1
       =  log( (1 − r_t) / (1 − f_t) )     if x = 0
       =  0                                if x = ⊘        [D — see §7.3]
```

This is the brief's own arithmetic written down: at `r = 0.61, f = 0.05`, one observed
absence is evidence *for* absence of `log((1 − f)/(1 − r)) = log(0.95/0.39) ≈ 0.89` nats,
i.e. the "likelihood ratio ≈ 2.5" of brief §2.3; four are `≈ 3.56` nats `≈ 35:1` (the
brief's "≈ 39:1" rounds 2.5 first); the persistence prior's cost is `log(0.98/0.02) ≈ 3.89`
nats `= 49:1`. Nothing new; the point is that the chain, the CUSUM (§2.2) and the gate (§4)
all consume the same `ℓ_t`.

**Sensitivity [D].** `∂ℓ_t/∂f_t = −1/f_t` on an observed 1; at `f = 0.05` a `0.01`
absolute error in `f` moves the increment by `0.2` nats (≈ 22 % in the likelihood
ratio). On an observed 0, `∂ℓ_t/∂r_t = −1/(1 − r_t) ≈ −2.6` at `r = 0.61`, so a `0.05`
error in recall moves the absence evidence by `0.13` nats; `∂/∂f = −1/(1 − f) ≈ −1.05`,
small. **The gain-side evidence is hypersensitive to `f`, which is exactly the rate the
review says is biased under correlated reference error (review §4.7, Foody 2010).** This
is one line of calculus with a large consequence: any bias in `f_t` propagates into the
detector at `1/f_t`.

### 2.2 The change detector — two published halves, joined here

**Half one, the Bernoulli CUSUM [Q]** (Ross, Tasoulis & Adams 2012 §5.1, review
§4.12.2), for a gain (pre-change `P(x = 1) = θ0`, post-change `θ1`):

```
C_0 = 0;   C_t = max(0, C_{t−1} + x_t − k),   k = r1 / r2,
r1 = −log((1 − θ1)/(1 − θ0)),   r2 = log(θ1(1 − θ0) / (θ0(1 − θ1)));
flag when C_t > h(θ0, θ1).
```

Optimal under known `θ0, θ1` (Lorden 1971, as cited by Ross). **Substitution [S]:**
`θ0 = f_t`, `θ1 = r_t` for a gain chart; for a loss chart relabel `x → 1 − x` and swap
`r_t ↔ 1 − f_t`, `f_t ↔ 1 − r_t`. Worked instance **[D, illustrative, C-CAP rates]:** at
`r = 0.61, f = 0.05`, `r1 = log(0.95/0.39) = 0.890`, `r2 = log(0.61·0.95/(0.05·0.39)) =
log(29.7) = 3.39`, so `k = 0.262`: every observed 1 adds `0.738`, every 0 subtracts
`0.262`. Under no gain `E[x] = f = 0.05 < k` and the chart drifts down; under gain
`E[x] = r = 0.61 > k` and it climbs. That is the right sign, which is all a worked
instance can show.

**Half two, the misclassification correction [Q]** (Chen & Yang 2022 eq. 7 and Thm 3.1(b),
review §4.12.2), with `π_kl = P(observed k | true l)`:

```
p** = (p* − π₁₀) / (1 − π₁₀ − π₀₁),
var{·} ∝ 1 / (1 − π₁₀ − π₀₁)².
```

**Substitution [S]:** `π₁₀ = f_t`, `π₀₁ = 1 − r_t`, so the denominator is `r_t − f_t` and
**the variance inflation from imperfect eyesight is `1 / (r_t − f_t)²`** — at the brief's
rates `1/0.56² ≈ 3.2`. This is the noise-floor factor CLAUDE.md 3.5 asks every effect to be
read against, in closed form, and the brief's emission gate `f < r` (brief §2.3) is
exactly the condition that keeps it finite.

**The join [D] — what is not in either paper:**

1. *Per-year rates.* Ross assumes `θ0, θ1` constant in `t`. With `(r_t, f_t)` varying by
   epoch the constant-`k` form is wrong; the raw-LLR form (Itkin eq. 2, review §4.12.2)
   `S_t = max(0, S_{t−1} + ℓ_t(x_t))` is the one that admits per-year rates, with `ℓ_t` from
   §2.1. The CUSUM and the chain then share every input.
2. *Two-sided.* Loss and gain are two one-sided charts run in parallel; their joint
   false-alarm rate at `T = 12` is not the sum of the marginals and has no published form.
3. *Threshold at n = 12.* No asymptotic run-length formula applies at twelve steps
   (Ross's `h` is for long sequences). `h_loss` and `h_gain` must be calibrated by Monte
   Carlo on **null** sequences drawn with the per-year rates — for the loss chart,
   `z ≡ 1` and `x_t ~ Bernoulli(r_t)` — at the `(1 − α)` quantile of `max_t S_t`. The
   brief's placebo (brief §5: shuffle the survey-to-rate assignment, 20 draws; agreement
   must fall) is the kill that must fire on this calibration before it counts.

### 2.3 The soft emission — the decision that settles the logits question

Everything above uses hard `x`. Brief §4.5 and review §4.9 argue for sitting *upstream of
the threshold*, on `p_{i,t}`. That changes the emission from two numbers per epoch to a
distribution `e_t(p | z)`, and there are two ways to get it:

**Option A — binned emission [D].** Bin `p` into `K` levels `b(p) ∈ {1..K}` and estimate
the multinomial `e_t(b | z)` per epoch on cells whose `z` is certified: `ℱ` (`z` fixed),
`𝒢` after 2016 (`z = 1`), the lidar epochs directly. Then `ℓ_t = log e_t(b | 1) / e_t(b | 0)`
— the same shape as §2.1 with `K` outcomes instead of two. `K` is chosen by held-out
log-likelihood on the certified cells, not by hand; a rule of thumb (every `(bin, z, t)`
cell holding enough certified samples to estimate a proportion) is a placeholder until
that criterion is run. **uint8 suffices: 254 levels ≫ K.**

**Option B — calibrated log-odds [D].** Use `ℓ_t = logit(p_{i,t}) + c_t` directly. This
requires `p` to be *calibrated* per epoch, i.e. `P(z = 1 | p) = p`. Review §4.12.3 (Kumar,
Liang & Ma 2019) says a continuous corrector's "true calibration error is unmeasurable
with a finite number of bins" — so calibration would have to be *assumed*. And at the
uint8 ceiling `p = 254/254 = 1` the log-odds are infinite: this option needs the float
logits.

**Verdict [D]:** Option A, unless a per-epoch calibration audit on the certified cells
passes at a stated tolerance — which is itself a binned test, so it collapses into A.
**The raw-logits patch is only needed for Option B. Hold it until §11 row 1 is resolved;
the choice is analytic, not a preference.**

### 2.4 Missing epochs and how long the chain remembers

On `x = ⊘` the emission contributes nothing (`ℓ_t = 0`, equivalently `P(x | z) = 1` for
both `z`) and the transition still applies. This is the two-state-chain form of Sinopoli et
al.'s `γ_t = 0` update (review §4.12.4): the state carries forward, the uncertainty does not
shrink **[S]**.

Their second result — a critical observation rate below which the error is unbounded — has
a chain analogue that is bounded but decisive **[D]**. The transition matrix

```
T = [ 1 − q_gain    q_gain  ]
    [ q_loss       1 − q_loss ]
```

has eigenvalues `1` and `λ₂ = 1 − q_loss − q_gain`. After `k` unobserved epochs the
posterior's distance from the stationary distribution `π = (q_loss, q_gain)/(q_loss + q_gain)`
has decayed by `λ₂^k`. The **information half-life** is

```
k_½ = ln 2 / (−ln λ₂)  ≈  ln 2 / (q_loss + q_gain)   for small rates.
```

At the pre-registered `q_loss = 0.02` with `q_gain ≪ q_loss`, `k_½ ≈ 35` epochs — three
times the archive. **Under the brief's rates an IGNORE gap never forgets:** the chain
carries a single confident observation across every intervening nodata epoch essentially
undiminished. On the raw stack (where the layer sits, brief §4.5) IGNORE is nodata — the
coverage gaps of the older, partial surveys — and any cell that is nodata for several
consecutive epochs is governed by this number, not by any smoothing weight. Whatever
`q_loss, q_gain` the certified populations yield (§11 row 11), `k_½` should be reported
next to them.

---

## 3. The spatial coupling (brief §4.1, axes 2 and 3)

### 3.1 The joint field, as an energy

The brief's "formal object: a random field in space and time" (brief §4.1) written down
**[D; shape from Krähenbühl & Koltun 2011, review §4.12.1]**:

```
E(z) = Σ_{i,t} ψ_u(z_{i,t})
     + β · Σ_t Σ_{(i,j) ∈ N_s} ψ_s(z_{i,t}, z_{j,t})        (space, same epoch — axis 2)
     + γ · Σ_i Σ_t ψ_τ(z_{i,t}, z_{i,t+1})                (time, per cell — axis 1)
```

with `ψ_u(1) − ψ_u(0) = −ℓ_t` (the §2.1 evidence as the unary), `ψ_τ = −log T(z_t, z_{t+1})`
(the chain), and `ψ_s` a Potts or contrast-sensitive pairwise term. Axis 3 (the
twelve-year consensus) is not a separate term: it is what `γ` and the chain already
propagate. Two limits are the baselines: `β = 0` is exactly the per-cell chain the brief
already has (brief §2.3 engine); `γ = 0` is a per-epoch CRF.

### 3.2 Estimating `(β, γ)` — the protocol, and the two warnings

The brief says the local/global weight is "a parameter to be MEASURED, not set" (brief
§4.1). The literature has no measured value and one protocol (Gräler et al. 2016, review
§4.12.1): **fit the weight, then test the fitted model against the `β = 0` and `γ = 0`
baselines on held-out data.** Here **[D]**: choose `(β, γ)` to minimise the
Efron-penalised counting error of §5.1 summed over `𝒢 ∪ ℱ`, and report `(0, γ̂)`,
`(β̂, 0)` and `(0, 0)` beside it. Two published outcomes are legitimate results, not
failures: Gräler's (a threefold spread in fit bought no held-out skill) and Krähenbühl's
("the smoothness kernel parameters … do not significantly affect classification
accuracy"). If either recurs here, the weight is inert on our data and the chain alone is
the layer.

### 3.3 The size below which smoothing erases a real removal

For total-variation smoothing the answer is closed-form **[Q]** (Strong & Chan 2003 §3.1,
review §4.12.1): `δ = α / scale`, `scale = |Ω|/|∂Ω|`. **[S]:** a feature of contrast `h`
is fully erased when `δ ≥ h`, i.e. a disk of radius `R ≤ 2α/h`. In a probability raster
`h = p_before − p_after < 1`, so **at fixed `α` the erased radius grows as the model's
confidence falls** — a 60 %-confident removal is erased at a larger physical size than a
95 %-confident one.

For the smoother in §3.1 (mean-field on a CRF) there is no closed form. Two routes
**[D]**:

- For any *linear* smoother with kernel `K`, the attenuation at the centre of a disk
  `D_R` of contrast `h` is `h · (1 − (1_{D_R} ∗ K)(0))`, computable exactly; the erased
  radius is where that reaches `h`. This is a property of the operator.
- For the non-linear case, inject disks of known `(R, h)` into *real* probability rasters
  and read the survival curve. **Per 3.4c this characterises the operator; it does not
  validate the claim** that real removals survive. The claim is tested only on the 42
  losses and `𝒢`.

### 3.4 Inference, and what it costs

**[D]** Alternate a mean-field spatial pass per epoch (Krähenbühl & Koltun 2011:
permutohedral-lattice filtering, "billions of edges" in 0.2 s — review §4.12.1) with an
exact forward–backward temporal pass per cell. The temporal pass is `N` independent
12-step chains — CPU-parallel, free tier (CLAUDE.md §3.4), memory ≈ 15 GB as written so
float32 with row-block chunking (brief §2.3). **The spatial pass is the only expensive
part.** Mean-field has no convergence guarantee (nor does Krähenbühl's); stop at a fixed
iteration count and report the objective's change. Liu et al. 2021's ordering (review
§4.2, spatial *then* temporal, once) is the thing not to do: alternate, so neither pass
hardens the other's error in.

---

## 4. Confidence gating — where it lives, and where it does not

The brief wants each survey's vote "weighted by its measured eyesight" (brief §3 rule 4)
and a per-cell weight "derived from the survey's own measured r and f" (review §4.2).
Martinis & Twele 2010, read in full (review §4.2, §4.12), gates *whether* a node enters the
contextual update by a threshold on its posterior entropy; the weights for admitted nodes
are fixed at 1 and never swept.

**[D] In the chain the gate is subsumed.** With per-epoch emissions, an epoch with poor
eyesight has small `|ℓ_t|` automatically: both `|log(r_t/f_t)|` and
`|log((1 − r_t)/(1 − f_t))|` shrink as `r_t → f_t`. A confident survey resists the
consensus and an unreliable one yields to it without any additional mechanism — that *is*
the per-cell weight the review asked for, and it is measured, not set.

Where a gate still has work to do is the **spatial** term: whether cell `i`'s own
`p_{i,t}` is confident enough to resist its neighbours. Candidate **[D]**:
`w_{i,t} = 1 − H(p_{i,t}) / ln 2` (normalised binary entropy — Martinis's `E_s` is this
quantity, thresholded), multiplying the unary. It is a free choice, must be swept, and
must be reported against `β = 0`; nothing in the literature has done the graded version.

---

## 5. Validation the layer cannot game

### 5.1 Efron's per-cell optimism, on the certified strata

**[Q]** (Efron 2004 Thm 1 and Remark F, review §4.12.3): for counting error at an
asymmetric cut, `E{Err_i} = E{err_i + Ω_i}` with `Ω_i = 2 cov(λ̂_i, y_i)` — the true error
is the apparent error plus a per-cell covariance penalty that measures how much the
corrector bent toward the data it was scored on. **[S]:** `y_i` = the certified state
(`𝒢`, `ℱ`, gold), `λ̂_i` = the layer's output. Estimate `Ω` by Efron's parametric bootstrap
(his 3.17): resample `y` from the fitted Bernoulli, rerun the layer, take the covariance —
`B` reruns on the strata only, feasible if the layer is local.

**Sum `Ω` per stratum, never citywide [Q→D]:** `Ω_𝒢`, `Ω_ℱ`, `Ω_loss` (42),
`Ω_nochange` (1,170). The review's caveat (b) is the reason: an average-risk estimate
blesses a launderer when change is rare. And the sign structure (Ramani, Blu & Unser 2008,
review §4.12.3) is what makes this a laundering test: a rigid persistence prior has near-zero
covariance with the data, so `Ω` charges it nothing — it is caught in `err_i` on `𝒢` and
the 42, where erased real change is misfit.

### 5.2 J-invariance as a *scoring* device, not an architecture

Noise2Self's condition (review §4.12.3) — the output at `t` may not read the input at `t` —
contradicts the chain's purpose, where `x_{i,t}` is the unary at `t`. The resolution
**[D]** is to keep the architecture and change what is scored: define the
**leave-one-epoch-out posterior**

```
P(z_{i,t} | x_{i,1..t−1}, x_{i,t+1..T})
```

— forward from `1..t−1`, backward from `t+1..T`, emission at `t` omitted — and score its
prediction of `x_{i,t}` against the observed `x_{i,t}`. By construction it cannot have read
what it predicts. It is one forward–backward pass per cell per held-out epoch, cheap.

**What is *not* derived here:** Noise2Self's Proposition 1 assumes additive independent
noise; under Bernoulli misclassification with known `(r_t, f_t)` the decomposition of the
self-supervised counting error into true error plus a known noise term has a different form,
and Efron's Bernoulli penalty (§5.1) is the bridge, not Noise2Self. Deriving that
decomposition is §11 row 5.

### 5.3 What the 42 losses can and cannot resolve

**[D]** The terminal-absence kill is recall on 42 verified losses (brief §5). At a true
recall of `0.80`, the 95 % interval on 42 trials is `±1.96·√(0.8·0.2/42) ≈ ±0.12`. **Two
layers whose true recall differs by less than ≈ 0.12 are indistinguishable on the gold
alone.** The 42-loss kill has power for large effects only; small effects are testable on
`𝒢` (46,805) and `ℱ` (40,609), which is why §5.1 sums `Ω` there. The 2 gains resolve
nothing.

### 5.4 Correlated error — the open gap

Every tool in §5 assumes the observation is *unbiased* for truth. Ours is not: leaf-off
flights and an 80.7 cm effective 2005 give species- and season-correlated error (CLAUDE.md
§4), and the reference itself may share the model's edge errors (review §4.7). Round 3 found
nothing for the covariance penalty under spatially and class-correlated error. **Mitigation,
not a fix [D]:** stratify `Ω` additionally by flight month (from the acquisition-date home,
`qc/imagery_pixelsize_and_date.csv`) and by the coregistration bound, and report per stratum.
This is §11 row 6 and the hardest item on the ledger.

---

## 6. The two constructs with no prior art

### 6.1 Development as a dated, directional prior (brief §4.2)

**[D; framing S]** The brief's "raise `q_loss(x, t′)` locally" is a proportional-hazards
modifier with a time-varying covariate:

```
q_loss(i, t) = q_loss · exp( A · K_R(d_i) · D_k(t − t_permit,i) ),   A ≥ 0,
```

`K_R` a spatial kernel of radius `R` around the dated footprint, `D_k` a decay over the
`k` years before the permit, and `A ≥ 0` the one-directionality the brief requires (only
`q_loss` moves; nothing manufactures a loss). `R, k, A` come from the enrichment count the
brief already orders first (brief §4.2, §7 step 1). Two bounds from the review, both
Christchurch/Seattle and not ours: Pedley & Morgenroth 2025's Table 2 puts 12.78 % of
citywide loss on 2.33 % of parcels — a per-parcel enrichment of ≈ 5.5× **[D from review
§4.4 figures]** — and Seattle's ratios are net-over-net, not gross (review §4.4). Rosa et al.
2013 (review §4.4): score the *year* of loss, not only the place. **The statistical home
of this form — survival analysis with time-varying covariates — was not searched (review
§5 item 2).**

### 6.2 Buildings as a soft prior, measurable from data we already hold (brief §6.2)

The review answers brief §6.2 "soft, not hard" (review §4.10, §6 item 5). The soft form
**[D]** is a unary offset

```
u_i = log( P(z = 1 | on footprint) / P(z = 1 | off footprint) ),
```

added to `ψ_u` for cells on a dated footprint. **Both quantities are estimable from the
lidar epochs** — the fraction of footprint cells that lidar sees as canopy in 2005 and
2016 — a measurement no paper in the review had. Positional error enters as CG-Net's soft
conditioning (review §4.10) rather than a mask edge: blur the footprint by the measured
inter-epoch registration error. The home is `phase4/qc/coregistration.csv`; its reader
rules (`docs/SCHEMAS.md`) say `median_dx_m / median_dy_m` is registration proper and
`p95_mag_m` is a conservative bound that *includes* building lean and parallax — for a
roof-versus-canopy question that inclusion is arguably what one wants, so start with the
conservative bound and report both. King & Locke 2013 (review §4.10) is the reason the
hard form is off the table: one closely related product assigns canopy over a roof to
canopy.

---

## 7. IGNORE through every stage (review §4.12.4)

### 7.1 Morphology — adoptable without a free parameter

**[S]** Map `0 / 1 / 255 → [0,0] / [1,1] / [0,1]` in the interval lattice (Sussner et al.,
review §4.12.4). Component-wise infimum and supremum then give Kleene three-valued
propagation — `inf([0,1],[0,0]) = [0,0]`, `sup([0,1],[1,1]) = [1,1]`, and IGNORE survives
`inf([0,1],[1,1]) = sup([0,1],[0,0]) = [0,1]` — and adjunction makes opening and closing
idempotent inside the lattice. This replaces the 3×3 opening/closing in
`threshold_and_clean` (brief §2.4) with an operator that cannot turn 255 into a class. No
parameter.

### 7.2 Probability-domain smoothing — adoptable with one free parameter

**[Q]** Partial-convolution renormalisation (Liu et al. 2018 eq. 1, review §4.12.4):
`x′ = Wᵀ(X ⊙ M) · sum(1)/sum(M) + b` where `sum(M) > 0`. **[S→D]** Their mask update
(eq. 2: one valid neighbour dissolves the mask) fills holes; ours must keep them. The
conservative rule is `m′ = 1 iff sum(M)/sum(1) ≥ φ`, and **`φ` is a free parameter.**
Proposed principle **[D]:** `φ` is the smallest valid fraction under which the kernel can
still resolve the smallest feature §3.3 protects, i.e. tie `φ` to `R_min`. Until that is
derived, `φ` is hand-set and must be reported as such — the review criticises every other
author for exactly this.

### 7.3 The chain

`ℓ_t = 0` on `⊘`; transition applied; memory governed by `k_½` of §2.4 **[S/D]**.

---

## 8. The metric (review §5 item 13)

**[D]** A triple, never a scalar, each element at its stated cut and population
(`docs/STATS_CHECKLIST.md`), each with its Efron optimism from §5.1:

1. recall on certified / gold **loss** (42; `𝒢`'s pre-gain absences),
2. recall on certified **gain** (`𝒢`),
3. false-change rate on certified **FLAT** (`ℱ`) and on the 1,170 no-change points.

The impossible-triple count (brief §2.1) is reported as a secondary and never optimised:
the brief records that it has no power at this cadence. Li et al. 2025's change/no-change
matrix (review §4.11) is the reporting shape; the certified strata are a stronger
denominator than theirs.

---

## 9. What this changes in the brief's order (brief §7)

- **Step 2 (per-cell port)** — unchanged, but scored with §8 and §5.1, and with the
  §2.2 detector run on the same chain (same `ℓ_t`; the marginal cost is the Monte-Carlo
  threshold).
- **Step 3 (consensus features)** — becomes the `(β, γ)` fit of §3.2 with its three
  baselines; "swept and READ against the gold" becomes "fit on `𝒢 ∪ ℱ`, read on the gold
  and per stratum."
- **The raw-logits patch** — hold until §11 row 1 resolves (§2.3).
- **New, before step 3, both CPU, both on files that exist:** the `K`-bin emission audit
  (row 1) and the Monte-Carlo threshold (row 2).

---

## 10. Where the compute goes

Per-cell chain and CUSUM: `N` independent 12-step recursions — CPU, parallel, free tier;
memory as noted in §3.4 (from brief §2.3). Leave-one-epoch-out scoring (§5.2): `T` such
passes. Efron bootstrap (§5.1): `B` reruns, strata-local. Spatial mean-field (§3.4): the
one GPU-shaped cost, or permutohedral on CPU. Nothing here needs training.

---

## 11. Gap ledger — what is still ours to derive or measure

| # | Gap | Blocks | Cheapest closing step | Kill that must FIRE on a known-bad input | State |
|---|---|---|---|---|---|
| 1 | Emission model: `K`-bin (§2.3 A) vs calibrated log-odds (B) | the logits patch; everything upstream of the threshold | held-out log-likelihood of `e_t(b\|z)` on certified cells across `K` | placebo rate shuffle (brief §5): likelihood must fall | **[D] open — decides the patch** |
| 2 | ~~Two-sided CUSUM thresholds at `T = 12`~~ → one-sided chart per certified population, threshold per `(population, band, α)` | the detector (§2.2, §12.3) | Monte Carlo on null sequences, `(r_{t,b}, f_{t,b})` | null sequences must not alarm above `α`; placebo must fall | **[D] resolved in form (§12.3); threshold still to run** |
| 3 | `(β, γ)` estimation | the spatial layer (§3) | Gräler protocol on `𝒢 ∪ ℱ` with `(0,γ̂)`, `(β̂,0)`, `(0,0)` | `(0,0)` reported; an inert weight is a result | **model + MPLE + bootstrap SEs published for equal intervals [Q] (§17.3); interval-dependent temporal term [D]** |
| 4 | Erasure radius for the smoother actually chosen | §3.3; the "never redraw" question (brief §6.1) | TV-L1 / area opening: exact, `R_erase = 2/λ` (§13.2); mean-field: injected disks on real rasters only | 42 losses and `𝒢` (claim) | **closed-form for TV-L1 [Q→S]; TV-flow extinction `t = R/2` [Q] (§16.2); open only if mean-field is chosen (§13.2)** |
| 5 | Leave-one-epoch-out scoring identity under Bernoulli noise | §5.2 | derived: §12.4 (Brier form; needs stratum prevalence `π_t`) | a deliberately leaking (median-type) layer must score *below* the noise floor | **[D] derived (§12.4); check not run** |
| 6 | Covariance penalty under spatially / class-correlated error | §5 as a whole | no closed form exists (PRIMARY negative, §13.1); Efron identity + *correlated* bootstrap, leave-out widened to the correlation group `G(t)`; two residual correlograms on the strata | independent-Bernoulli bootstrap must under-estimate `Ω` on an injected correlated field; correlated one must not | **per-cell closed form [S] (§15.1); `G(t)` mask rule [Q] (§16.1); published goodness-of-fit kill [Q] (§17.5); the two correlograms remain [D — measurement]** |
| 7 | Power: 42 losses resolve `Δ ≳ 0.12` only | which kills can decide small effects | use `𝒢`, `ℱ` for small effects | — | **[D] derived, stated** |
| 8 | Conservative mask fraction `φ` | §7.2 | tie to `R_min` (row 4) or report hand-set | — | **[D] open** |
| 9 | Development prior `A, R, k` | §6.1 | fit: `A` canonical by pseudolikelihood, `R, k` irregular by profile likelihood, or NHMM-EM (§13.3); population = LOSS build (11b) near dated footprints | no-change gold near new buildings stays no-change (brief §5) | **fitting protocol found [S]; forms still ours (§13.3)** |
| 10 | Building prior `u`; blur radius | §6.2 | footprint canopy fraction at the lidar epochs; radius = coregistration bound (row 14); no published blur-prior form (§13.3) | canopy painted on `ℱ` (brief §5) | **[D] open; data on hand; negative on prior art** |
| 11a | Estimator for lidar-anchored `(r_{t,b}, f_{t,b})` at every epoch, and `(q_g, q_l)` per population | every `ℓ_t`; §2.4 | derived: §12.2 (decaying anchor; closed-form `(q_g, q_l)` from `Q_g, Q_l`) | 2005-footprint propagation must reproduce the direct 2016 rates and must FAIL under `q × 10` | **[D] derived (§12.2); kill not run** |
| 11b | The populations the estimator needs: `𝒞` (certified canopy, PACC's `A_can`) and `LOSS` (GAIN's mirror), per band | 11a; §12.3 | two rules in `certified_flat_scoring.py`'s family — data builds, not math | — | **not built** |
| 12 | The `r`-convention translation of every [S] above | everything | one reader re-derives §2.1–§2.2 from the papers with `r` = recall | — | **[S] unchecked** |
| 13 | Band-stratified emissions `(r_{t,b}, f_{t,b})` — is a scalar per epoch misspecified? | every rate above; the order of rows 1–2 | re-run the PACC band profile (MASTER §3a, "re-run before any number is cited") on the twelve tags | a scalar-rate chain scored on the 0–2 m band must show the bias; if it does not, banding is dropped | **[D] motivated by a pilot; unmeasured** |
| 14 | Erosion radius tied to the coregistration bound; does it admit the 0–2 m band? | §12.1; `f_{t,0–2}` | read p95 from `coregistration.csv` per SCHEMAS; compare with 2 m | — | **measurement; data on hand** |

**Bins and checks, the 3.4c ledger.** Every [S] in this document (§1 convention, §2.1
increments, §2.2 substitutions and worked instance, §2.4 the `γ = 0` analogue, §3.3 the
contrast translation, §5.1 the strata, §7.1 the lattice map, §7.2 the conservative rule)
and every [D] (§2.1 sensitivity, §2.2 the join, §2.3 the verdict, §2.4 `k_½`, §3.1–3.4,
§4, §5.2–5.4, §6, §7.2 `φ`, §8, §11, and all of §12–§17 — added 2026-09-12, after this
ledger, which is why they sit below it) is unvalidated. The independent check for each is the
row above that names it, run by someone other than this document's author, on real data,
with the kill shown to fire first. A design accepted on numbers it produced about itself is
the failure 3.4c exists to prevent; this document produced none, and should be held to
that.

---

## 12. Where the rates come from — the mathematics closed on 2026-09-12

**Status of this section: [D] throughout, UNVALIDATED (3.4c). Written 2026-09-12 after
§1–§11.** Everything in §2–§5 consumes `(r_t, f_t)` as known. They are not known: brief
§2.3 holds only C-CAP-referenced rates, C-CAP overestimates canopy, and §2.1 shows the
detector's sensitivity to `f` is `1/f`. This section derives where lidar-anchored rates can
come from, corrects one misspecification in §1 that the derivation exposed, and closes
ledger rows 2 and 5 along the way. Four results; each names its kill.

### 12.1 The rates are not per-epoch scalars — band-stratified emissions

**The finding that reorders the rest.** `LIT_HUNT_MASTER_2026-09-06.md` §3a (PACC pilot,
single run, 2026-09-06, "re-run before any number is cited") measured `P(map = canopy)` on
lidar-certified-unchanged cells by distance to the lidar canopy boundary: in the 0–2 m band
it "swings 13.2 pp across epochs" while the >16 m core "reads 1.0000 in seven of eight
epochs", and permanent non-canopy within 2 m of canopy "is called canopy 16–26 % of the
time." Read in §1's notation: `f_t ≈ 0.16–0.26` at the edge against near zero in the
interior. A single `f_t` per epoch is misspecified in exactly the band where `1/f` makes
the detector most sensitive — and `ℱ` is eroded 6 m, so any rate estimated on it is the
*interior* rate, the one closest to zero. Those numbers are cited here as motivation only;
they carry the pilot's own caveat and are not restated as facts.

**Correction to §1 [D].** Emissions are indexed by epoch *and* band:

```
b(i) ∈ {0–2, 2–4, 4–8, 8–16, >16 m}   distance from cell i to the lidar canopy boundary
                                       (PACC's five bands, MASTER §3a item 2; lidar-anchored,
                                       so b(i) is fixed in t)
r_{t,b} = P(x = 1 | z = 1, b),   f_{t,b} = P(x = 1 | z = 0, b)
ℓ_{t,b}(x) as §2.1 with (r_{t,b}, f_{t,b})
```

Everything downstream — the chain (§2), the detector (§2.2), the emission audit (§2.3),
the gate (§4), the Efron strata (§5.1) — goes through unchanged with `ℓ_{t,b}` in place of
`ℓ_t`; the spatial energy (§3) is unaffected because the unary already varies by cell. The
cost is five rate estimates per epoch instead of one, and a sample-size floor per `(t, b)`
cell that §12.2 makes explicit.

**Where the edge bands are anchored.** `ℱ`'s 6 m erosion means it contains no cell in
bands 0–2 or 2–4 and only the outer part of 4–8: the bands that matter most have no
certified non-canopy population at all. The erosion radius is the right knob, and it has a
principled setting: a cell can be certified relative to the boundary only if it is farther
from the boundary than the inter-epoch registration error, so the minimum erosion is the
coregistration bound (`phase4/qc/coregistration.csv`, p95 per `docs/SCHEMAS.md`), not a
round number. Whether that bound admits the 0–2 m band at all is a measurement, not a
derivation; if it does not, `f_{t,0–2}` is unanchored and the chain must treat those cells
with the conservative rule of §7.2 rather than a guessed rate.

### 12.2 The decaying-anchor estimator for `(r_{t,b}, f_{t,b})`

**The problem.** A certified population is certified at the lidar dates (2005, 2016) and
nowhere else. Between and after them its cells transition at the population's own rates,
so at any other epoch the population is a *mixture* of its certified state and the other
state, and the naive rate `m = mean(x)` on it is biased. This is Chen & Yang's
misclassification correction (§2.2, [Q]) with the anchor's own decay playing the role of
the misclassification matrix; the algebra is the same and so is the variance penalty.

**Objects.** For one band `b` (suppressed below) and one certified population, let the
two-state chain have per-calendar-year rates `q_g = q_gain`, `q_l = q_loss`, transition
matrix `T = [[1 − q_g, q_g], [q_l, 1 − q_l]]`, stationary law `π₁ = q_g/(q_g + q_l)`,
`π₀ = 1 − π₁`, and second eigenvalue `λ = 1 − q_g − q_l`. Then for a cell certified at
year `t₀`, `k` calendar years later:

```
a_k = P(z_{t₀+k} = 0 | z_{t₀} = 0) = π₀ + π₁ λ^k        (persistence of certified 0)
c_k = P(z_{t₀+k} = 1 | z_{t₀} = 1) = π₁ + π₀ λ^k        (persistence of certified 1)
```

(Check: `a₀ = 1`; `a₁ = 1 − q_g`; `a_k → π₀`.) `k` is in **calendar years between the
lidar date and the epoch's flight date** (`qc/imagery_pixelsize_and_date.csv`), not in
chain steps; the epochs are unevenly spaced, so the chain's own transition between
consecutive epochs `t, t+1` is `T^{Δt}` with `Δt` their year gap. §2.4's half-life should
be read in the same unit.

**Two populations, two equations.** `ℱ` (certified 0) and `𝒞` (certified 1; PACC's
`A_can` — lidar canopy in both 2005 and 2016 — is the existing instance, MASTER §3a item 1,
though `certified_flat_scoring.py` does not yet write it). Their observed rates at the
epoch `k` years from the anchor date are

```
m^ℱ_k = a_k · f + (1 − a_k) · r
m^𝒞_k = (1 − c_k) · f + c_k · r
```

a 2×2 linear system in `(f, r)` with determinant `a_k + c_k − 1 = (π₀ + π₁)λ^k = λ^k`.
Hence the **estimator [D; the `λ^k` decay weights and the yearly-rate closed form below
re-binned [S] on 2026-09-12 per §14.1 — they are Bell & Hinojosa 1977 eqs. 1–2 in the
2×2 case; the 2×2 solve and its kill remain [D]]**:

```
f̂ = ( c_k · m^ℱ_k − (1 − a_k) · m^𝒞_k ) / λ^k
r̂ = ( a_k · m^𝒞_k − (1 − c_k) · m^ℱ_k ) / λ^k
```

At `k = 0` this is the direct lidar-referenced rate; as `k` grows the anchor forgets and
the correction blows up at `1/λ^k`.

**Variance [D].** With `m^ℱ, m^𝒞` independent binomial means on `n_ℱ, n_𝒞` cells,

```
Var(f̂) ≈ [ c_k² · m^ℱ(1 − m^ℱ)/n_ℱ + (1 − a_k)² · m^𝒞(1 − m^𝒞)/n_𝒞 ] / λ^{2k}
```

and symmetrically for `r̂`. The inflation factor is `1/λ^{2k}`: **4× at the anchor's
half-life** (`λ^k = ½`), the same `1/(denominator)²` law as §2.2. Because cells within a
sample block are not independent, the `n` in these formulas overstates the information;
the honest interval is a block bootstrap over the sample blocks, not the binomial one.

**Bridge weight for the interior epochs [D].** Epochs 2009–2015 lie between two lidar
dates, `K = 11` years apart. A cell certified 0 at both ends is more likely still 0 at
year `k` than one-sided decay says, by the Markov identity

```
P(z_k = 0 | z_0 = 0, z_K = 0) = a_k · a_{K−k} / a_K   ≥ a_k
```

(and `c_k c_{K−k}/c_K` for certified 1). Use the bridge weights in the system above for
the in-bracket epochs, the one-sided weights `a_k, c_k` from the 2016 anchor for
2017–2024. This is the formal reason PACC's in-bracket fit (MASTER §3a item 8) is the only
defensible pre-2016 statement: it is where the mixture weights are tightest.

**Bias if the decay is ignored [D].** Treating `ℱ` as pure at year `k` gives
`f̂_naive = m^ℱ_k = f + (1 − a_k)(r − f)`, i.e. a bias of `(1 − a_k)(r − f) ≈ k·q_g·(r − f)`
for small `k q_g` — *upward*, and through §2.1 it enters the gain evidence at `1/f`. At
the brief's rates `r − f = 0.56`: every `0.01` of cumulative gain probability on the anchor
adds `0.0056` to `f̂`, which at `f = 0.05` is an 11 % error in the increment.

**The rates must be the population's own, not the city's.** `ℱ` is eroded-interior
non-canopy — roads, roofs, water — whose gain rate is far below the citywide rate, which is
dominated by growth at canopy edges. Using a citywide `q_g` in `a_k` over-corrects by
construction. The population's own rates come from the same instrument that certifies it,
over the 11-year lidar interval:

```
Q_g = |GAIN ∩ S| / |2005-non-canopy ∩ S|        S = the population's own stratum (band,
Q_l = |LOSS ∩ S| / |2005-canopy ∩ S|                erosion applied to the 2005 mask
                                                    before intersecting)
```

with `GAIN` as defined in `qc/instruments/harm_change_laundering.py` (`both & (h05 < 2.0)
& (h16 >= 5.0)`) and `LOSS` its mirror (`both & (h05 >= 5.0) & (h16 < 2.0)`) — the
thresholds are GAIN's, not new ones. `GAIN` alone leaves `(q_g, q_l)` under-determined;
the pair identifies both exactly, because `Q_g = 1 − a_K = π₁(1 − λ^K)` and
`Q_l = 1 − c_K = π₀(1 − λ^K)`:

```
λ   = (1 − Q_g − Q_l)^{1/K}
q_g = (1 − λ) · Q_g / (Q_g + Q_l),     q_l = (1 − λ) · Q_l / (Q_g + Q_l)
```

(for small `Q`, `q_g ≈ Q_g/K`). These are per band, per population.

**Assumptions, stated.** (i) *Stationarity* of `(q_g, q_l)` from the 2005–2016 interval
to 2016–2024 — an assumption, and §6.1's prior asserts it fails near dated development
footprints, so anchor cells are drawn away from them. *Testable [Q→S, added 2026-09-12,
review §4.14.1]:* Anderson & Goodman 1957's likelihood-ratio / χ² test of constant
transition probabilities, in Bell & Hinojosa 1977's land-use form — raise the 2005–2016
matrix to the power that matches the later interval (`Pᵗ = HΛᵗH⁻¹`, non-integer `t`),
predict the state counts on the certified strata at the next lidar-coincident date, and
test against the observed counts. On our data this needs a third certified date; until
one exists the test can only be run *within* 2005–2016 on the interior epochs via the
bridge weights, which is a consistency check, not a test of the post-2016 assumption.
The `λ^k` diagonalisation and the yearly-rate closed form above are Bell & Hinojosa's
eqs. 1–2 applied to the 2×2 case, so they are [S], not [D]. (ii) *Homogeneity within a stratum*:
the mixture algebra assumes every cell in `S` shares `(q_g, q_l)`; banding is the first
covariate, land-use class (PACC's "impervious") is the next if the kill below fails.
(iii) *Conditional independence* `x ⊥ (anchor membership) | z, b` — the model's error on a
certified cell is the same as on an uncertified cell of the same state and band. This is
what erosion buys and what the registration bound (§12.1) is for.

**Kill — non-circular, and it must fire [D].** Propagating `ℱ` from 2005 to 2016 proves
nothing: `ℱ` is certified 0 at 2016 by definition. The valid form: take the full 2005 lidar
footprint (uneroded, or eroded identically on both sides), split by 2005 state, propagate
`K = 11` years with the population's own `(q_g, q_l)`, solve the system at the 2016 imagery
epoch (present in the stack: `YEAR_CATALOG` label `2016`, checked 2026-09-12; the exact
`k` is the flight-date gap), and compare `(f̂, r̂)` to the direct rates scored against the
2016 CHM, which the estimator never saw. Eleven years is longer than the eight the
post-2016 estimates need, so the test is conservative. It must *fail* under the placebo
`(q_g, q_l) × 10`: if the corrected and naive estimates cannot be told apart at the true
rates, the correction is below the noise floor and is reported UNDETERMINED, not adopted.

### 12.3 The CUSUM needs a certified start — ledger row 2 dissolves

§2.2 left two open problems: the joint false-alarm rate of two parallel one-sided charts,
and thresholds at `T = 12`. Both were posed for a chart run *blind* on every cell. That
chart is misspecified, and the calculation is one line **[D]**: a gain chart accumulates
`ℓ_t(x_t)` from §2.1; on a cell that was canopy all along, `x_t ~ Bernoulli(r_t)` and

```
E[ℓ_t | z = 1] = r log(r/f) + (1 − r) log((1 − r)/(1 − f)) = KL( Bern(r) ‖ Bern(f) ) > 0
```

— at the brief's rates `0.61·log(12.2) + 0.39·log(0.411) ≈ 1.53 − 0.35 = 1.18` nats per
epoch. The chart drifts *up* on a cell with no change and fires within a few epochs. Ross's
optimality (§2.2, [Q]) assumes the pre-change law `θ₀` holds at the start; on an
uncertified cell it does not, and no threshold fixes that.

**Resolution [D].** The CUSUM is well-posed exactly where the initial state is certified:
the gain chart on `ℱ` (start `z = 0`), the loss chart on `𝒞` (start `z = 1`), direction
fixed by the certification, rates `(r_{t,b}, f_{t,b})` from §12.2. There is no two-sided
problem — each population runs one chart — and row 2 reduces to **one Monte Carlo per
`(population, band, α)`**: null sequences with the certified state persisting and
`x_t ~ Bernoulli(rate_{t,b})`, threshold at the `(1 − α)` quantile of `max_t S_t`, the
brief's placebo (§2.2 item 3) still the kill. Everywhere else — the 13.3 M uncertified
cells — the change point is the chain's posterior (`argmax_t P(z_t ≠ z_{t−1} | x_{1..T})`
from forward–backward), which carries its own uncertainty and needs no chart.

### 12.4 The leave-one-epoch-out identity under Bernoulli noise — ledger row 5

§5.2 defined the leave-one-epoch-out posterior `p̂_t = P(z_t = 1 | x_{−t})` and deferred
the scoring identity. It is short **[D]**. Define the *debiased pseudo-label*

```
y_t = (x_t − f_t) / (r_t − f_t)
```

(band-indexed rates understood). Since `E[x_t | z_t] = f_t + z_t (r_t − f_t)`,
`E[y_t | z_t] = z_t`: the pseudo-label is unbiased for the latent state, at the price of
lying outside `[0, 1]` (at the brief's rates `y = 1.70` on an observed 1, `−0.089` on a 0).
Now expand `E[(p̂_t − y_t)²] = E[(p̂_t − z_t)²] + E[(z_t − y_t)²] + 2E[(p̂_t − z_t)(z_t − y_t)]`.
The cross term vanishes: `p̂_t` is a function of `x_{−t}` alone, and in the chain the
emission `x_t` is a leaf with single parent `z_t`, so `x_t ⊥ x_{−t} | z_t` and
`E[z_t − y_t | z_t, x_{−t}] = z_t − E[y_t | z_t] = 0`. Hence

```
E[(p̂_t − z_t)²]  =  E[(p̂_t − y_t)²]  −  [ π_t · r_t(1 − r_t) + (1 − π_t) · f_t(1 − f_t) ] / (r_t − f_t)²
   true Brier        observable              noise floor, π_t = P(z_t = 1) in the stratum
```

— the Bernoulli analogue of Noise2Self's Proposition 1 (review §4.12.3), with the same
structure: an observable self-supervised loss minus a known noise term. Three things to
say. (a) The noise term needs a prevalence `π_t` per stratum, not citywide; on the
certified strata it is the persistence weight `a_k` or `c_k` of §12.2, which is why this
score and the estimator share inputs. At the brief's rates the floor is `0.76` on a canopy
cell and `0.15` on a non-canopy cell — large, so the identity is useful on stratum means,
never per cell. (b) This scores *squared error on the probability* (a Brier score),
whereas §5.1's Efron penalty scores *counting error at a cut*; they are two metrics and §8
should carry both. (c) It inherits §12.1: with a single `f_t` on an edge cell `y_t` is
biased and the identity fails silently. Epochs with `x_t = ⊘` are not scored. **Kill:** a
layer that copies `x_t` through (a median-type filter reading its own input) must show
`E[(p̂_t − y_t)²]` *below* the noise floor on a certified stratum — an impossible value that
flags the leak; if the check cannot produce that on a deliberately leaking layer, it is not
a check.

### 12.5 What this section changes upstream

- §1 notation: `(r_t, f_t)` → `(r_{t,b}, f_{t,b})`; `𝒞` added; `k` in calendar years.
- §2.2 item 2 (two-sided) and item 3 (thresholds): replaced by §12.3.
- §2.4 half-life: in calendar years; `(q_g, q_l)` per population from §12.2, not
  pre-registered.
- §5.2: the identity is §12.4; §8's metric triple gains the Brier form.
- §9 order: **before rows 1 and 2, the populations.** `𝒞` and `LOSS` are one rule each
  in `certified_flat_scoring.py`'s family and are data builds, not mathematics — but
  §12.2 has no `r̂` without `𝒞`, and row 1's emission audit has no lidar-anchored rates
  without §12.2. The estimator kill (§12.2) runs on files that exist plus those two rules.

---

## 13. Round 4 — what the adjacent literatures give rows 4, 6, 9 and 10 (2026-09-12)

**[S] and [D] only; sources and grades in review §4.13. Nothing here is validated.** Round
4 searched the mathematics behind the three hardest ledger rows. Each row below states
what was found, the substitution that makes it ours, and what remains.

### 13.1 Row 6 — covariance penalty under correlated error: two measurements, not a theorem

**Found [Q, review §4.13.1].** No unbiased-risk identity exists for correlated binary
observations: the discrete Stein identity is stated for independent variables in both of
its sources (Hudson 1978 §3; Hwang 1982 eq. 2.1), and the correlated identity
(Chaux et al. 2008 Prop. 1: `E[f(r)s] = E[f(r)r] − E[∂f/∂r]ᵀΓ`; Eldar 2009 Thm 1) is
Gaussian and continuous. This is a PRIMARY negative.

**Substitution [S].** Two things survive.

1. *Efron's identity with a correlated bootstrap.* §5.1's `Ω_i = 2cov(λ̂_i, y_i)` is a
   marginal covariance; its derivation (review §4.12.3) compares the fit to an independent
   replicate of the whole data vector and does not need independence across `i`. What
   dies is only the Stein closed form. Efron's parametric bootstrap (his 3.17) therefore
   stands, **provided the resampled `y` is drawn from a correlated generative model** —
   on the certified strata, a Bernoulli field with the *measured* error correlogram, not
   independent Bernoullis. *Checked (review §4.13.1, Efron 2021 PRIMARY): the Q-class
   theorem is stated for an arbitrary joint model `f`; only the Stein special case needs
   `N(μ, σ²I)`.* **The bootstrap model is [Q], not ours:** the autologistic field
   `P(x | z) ∝ exp(Σ α_i x_i + Σ β_ij x_i x_j)`, `β_ij` a function of inter-cell distance,
   fitted by Monte Carlo maximum likelihood (Hughes, Guttorp & Charles 1999, review
   §4.13.3). **[S]:** fit it per stratum and band to the residual field on `ℱ` and `𝒞`;
   `α` reproduces `f_{t,b}` / `r_{t,b}`, `β(d)` is the correlogram; draw the bootstrap
   `y` from it by Gibbs sampling.
2. *Widen the blind spot to the correlation footprint.* §12.4 holds out the whole epoch
   `t`, so same-epoch spatial correlation never leaks into `p̂_t`. Cross-epoch error
   correlation does — it breaks `x_t ⊥ x_{−t} | z_t`. The blind-spot principle (review
   §4.13.1, ABSTRACT-grade sources) applied to time: hold out epoch `t` *and every epoch
   whose error correlates with it*; the identity of §12.4 then holds with `x_{−G(t)}` in
   place of `x_{−t}`, `G(t)` the correlation group. The noise floor is unchanged.

**What remains [D — measurement].** Row 6 reduces to two correlograms on the certified
strata, per band: (a) the spatial correlogram of `x_{i,t} − f_{t,b}` on `ℱ` and of
`x_{i,t} − r_{t,b}` on `𝒞` at each epoch, which sets the bootstrap model in item 1 and
the block size in §12.2 (Valavi et al. 2018: blocks from the measured autocorrelation
range); (b) the cross-epoch correlogram of the same residuals, which defines `G(t)` in
item 2 — expected to follow flight month (`qc/imagery_pixelsize_and_date.csv`). Neither
is a derivation. **Kill:** on a synthetic correlated field the independent-Bernoulli
bootstrap must *under*-estimate `Ω` and the correlated one must not — and then the same
on `ℱ` with the measured correlogram; a bootstrap that cannot be made to fail on an
injected correlation is not a check.

### 13.2 Row 4 — erasure radius: exact if the smoother is TV-L1 or an opening; unobtainable if it is mean-field

**Found [Q, review §4.13.2].** For TV-L1 with fidelity weight `λ`, a disc of radius `R` is
removed *whole* iff `λ < 2/R` and kept whole iff `λ > 2/R` (Chan & Esedoglu 2005 §3;
Duval et al. 2009 §5.1; Vixie 2007: empty solution inside a ball of radius `n/λ`). In the
convex case the exact TV-L1 solution is an *opening* followed by a perimeter/area test
(Duval et al. abstract, Thm 3.6). For mean-field CRF inference there is no erasure result
(Krähenbühl & Koltun 2011 guarantee KL descent only; nothing found elsewhere).

**Substitution [S].** A removed tree is a hole — a disc of 0 in a 1-field. TV-L1 on binary
data is symmetric under `u → 1 − u`, so the rule applies to holes: **`R_erase = 2/λ`**, and
§3.3's "size below which smoothing erases a real removal" is closed-form, with no
approximation, for this smoother. By Duval's equivalence the same holds for an area
opening of the matching radius, which is the morphology stage §7.1 already admits.
Row 8 follows: the conservative-mask fraction `φ` can be tied to the opening radius rather
than hand-set.

**[D] — the Potts one-liner, attributed to nobody.** For a Potts/CRF MAP with pairwise
weight `β` per unit boundary and a unary margin `m` per unit area on an isolated disc, the
disc flips when `β·2πR > m·πR²`, i.e. **`R < 2β/m`**. Kolmogorov & Boykov 2005 discuss
the shrinking bias qualitatively and do not state this; it is an energy comparison, not a
theorem, and says nothing about mean-field.

**What remains.** A decision, not mathematics: choose TV-L1/opening (closed-form erasure;
row 4 closes; row 8 closes) or mean-field (row 4 stays a measurement by injected discs on
real rasters, framework §3.3). §9's order should put this choice before the `(β, γ)` fit.

### 13.3 Rows 9–10 — the priors: a fitting protocol, no forms

**Found [Q, review §4.13.3].** Baddeley & Turner 2005: a log-linear intensity is fitted by
maximum pseudolikelihood via the Berman–Turner device; *canonical* parameters (those the
log-likelihood is linear in) are fitted directly, *irregular* ones (a radius inside the
covariate) by profile pseudolikelihood. Hilbert et al. 2019: permitting data "show
promise" for tree mortality and are "rarely applied" — the field names our covariate and
has not built the model. Hughes, Guttorp & Charles 1999 (ABSTRACT): covariate-dependent
transition probabilities inside an HMM, fitted by EM. No paper fits a joint distance ×
time hazard; no paper gives a registration-blurred footprint prior.

**Substitution [S].** In `q_loss(i,t) = q_loss·exp(A·K_R(d_i)·D_k(t − t_permit))`, `A`
is canonical — a GLM coefficient on the covariate `K_R(d)·D_k(τ)` — and `R, k` are
irregular: fit `A` by pseudolikelihood at each `(R, k)` on a grid and take the profile
maximum. The population is the LOSS build of §12.2 (row 11b) within reach of dated
footprints, which makes rows 9 and 11b the *same* data build. The NHMM form is the
cleaner home for the same thing: put the covariate in the transition matrix and fit by EM,
so that `A, R, k` are estimated jointly with the chain rather than bolted on. Row 10 is
unchanged: the only principled blur radius is the coregistration bound (row 14).

**Revised after the Sci-Hub pass (same day).** Two of the "not found" forms are found.
(i) The *multiplicative* structure `q_loss · exp(covariate term)` inside an HMM is
Hughes, Guttorp & Charles 1999's non-homogeneous transition — "a base-line transition
matrix and a multiplicative function of the covariates", EM-fitted (review §4.13.3,
PRIMARY). §6.1's form is theirs; only the covariate `K_R(d)·D_k(τ)` is ours. (ii) The
radius `R` has an empirical protocol: Verburg et al. 2004's enrichment factor `F` (share of
a class in a radius-`d` neighbourhood over its study-area share; `F = 1` is no enrichment)
computed for later canopy loss around dated footprints at increasing `d`; the `d` at which
`F` returns to 1 is `R`, read off the data before any fit. (iii) For a 1-D median, the
erasure length is exact (Gallagher & Wise 1981 Thm I: runs of `≤ N` erased under a
`2N + 1` window) — relevant to §7.1 if a median stage is used, not to row 4's 2-D question.

**What remains.** `D_k(τ)`'s form (a decay after the permit date) is still ours; the
fit needs the LOSS population and the permit dates; the kill is unchanged (row 9).

### 13.4 Ledger deltas from round 4

| # | Was | Now |
|---|---|---|
| 4 | [S→D] open; injected discs | **closed-form if TV-L1/opening** (`R_erase = 2/λ` [Q→S]); measurement only if mean-field; a smoother choice is now a §9 decision |
| 6 | OPEN, hardest; none found | **narrowed to two measurements** (spatial + cross-epoch residual correlograms on the strata) under Efron-with-correlated-bootstrap [S] and the widened leave-out `G(t)` [S]; PRIMARY negative on any closed form |
| 8 | hand-set `φ` | tie to the opening radius `1/λ` (row 4) |
| 9 | framing unsearched | **form and fitting protocol found**: multiplicative NHMM transition is Hughes–Guttorp–Charles 1999 [Q]; `R` from Verburg's enrichment factor vs `d` [S]; `A` canonical / `k` irregular (Baddeley & Turner) [S]; only `D_k` still ours; same data build as 11b |
| 10 | data on hand | no published blur-prior form (negative); radius from row 14 |

---

## 14. Round 5 — what moved from "need information" to "known" (2026-09-12)

**[Q] → [S] only; sources and grades in review §4.14. Unvalidated as before.**

### 14.1 The `λ^k` machinery and the stationarity test are 1977 results

Bell & Hinojosa 1977 state `P = HΛH⁻¹`, `Pᵗ = HΛᵗH⁻¹` for non-integer `t` and use it to
put two land-use transition matrices on an equal footing before a χ² test — a two-state
developed/undeveloped chain in Washington State. §12.2's decay weights `a_k, c_k`, its
determinant `λ^k`, and its yearly-rate closed form are the 2×2 case of their eqs. 1–2:
**re-binned [D] → [S].** Assumption (i) (stationarity across lidar intervals) has its
test: Anderson & Goodman 1957's likelihood-ratio / χ² test of constant transition
probabilities, applied as Bell & Hinojosa apply it. The existence condition for the yearly
root, `λ > 0`, is their eigenvalue remark; Hasegawa & Takada 2019 (ABSTRACT) report it
holds with high probability for matrices with large diagonals — ours.

### 14.2 Row 6 — the correlated bootstrap is fully sourced

Generative model: autologistic (Hughes, Guttorp & Charles 1999 use it for a binary field
with distance-dependent interaction; Besag 1974 is the origin, METADATA). Estimator:
Monte Carlo maximum likelihood (Geyer & Thompson 1992, PRIMARY), which Hughes–Guttorp
use; pseudolikelihood is the cheap alternative. Identity: Efron's Optimism Theorem holds
for an arbitrary joint `f` (Efron 2021, PRIMARY). Mechanism the widened leave-out
guards against: Burnicki et al. 2007 — correlated error across dates "improved the overall
accuracy of the resulting change map" without improving the user's accuracy of change.
**Row 6 is now: two correlograms to measure, one autologistic fit per stratum, one
bootstrap.** Every piece has a home.

### 14.3 Rows 9–10 — radii from the field, a window for `k`, a generative offset for the blur

- `K_R(d)`: the field reports two scales — 0.7–1.4 m from the building itself and ~20 m
  for associated works (Morgenroth et al. 2017 via Hilbert's table; Guo et al. 2018,
  ABSTRACT). **[S]:** `K_R` as two kernels, or `R` read from Verburg's enrichment curve
  (§13.3); the single-radius form of §6.1 is under-specified.
- `D_k(τ)`: no curve exists. Windows of elevated loss are 4–8 years (Hauer 1994), 4–5
  (Guo 2018/2019), 6–7 (Steenberg, Robinson & Millward, JEPM, print vol. 2018: 806 trees
  re-measured 2007/08 → 2014; the Environment & Planning B 2018 paper is a different
  study); replanting at 2–3 years (Conway
  2022). **`k ≈ 5 y` is the only literature-supported prior for the fit's starting value;
  it is a window, not a shape — `D_k` stays [D].**
- Row 10 blur: **[S]** — the footprint prior's blur is the expectation of the footprint
  indicator under a per-coordinate Gaussian-random-field displacement (Girard et al.
  2019a's noise model) with amplitude set to the epoch's coregistration p95 and
  correlation length from the coregistration field; the "bound as input radius"
  precedent is Vargas-Muñoz et al. 2019. No published label prior does this (negative
  stands); the offset model and the precedent are [Q].

### 14.4 Ledger deltas from round 5

| # | Was | Now |
|---|---|---|
| 6 | narrowed to measurements | **fully sourced**: identity (Efron 2021), model (autologistic), estimator (MCML), mechanism (Burnicki 2007); remaining = the two correlograms + one fit per stratum |
| 9 | form + protocol found; `D_k` ours | radii two-scale from the field [S]; `k ≈ 5 y` starting value (window) [S]; `D_k` shape still [D] |
| 10 | negative on prior art | blur = footprint ⊗ GRF-offset(p95) [S]; precedent for bound-as-radius [Q]; negative on a published prior stands |
| 11a | estimator [D] | `λ^k` decay and yearly-rate closed form → [S] (Bell & Hinojosa 1977 eqs. 1–2) |
| **15 (new)** | — | **Stationarity of `(q_g, q_l)` across lidar intervals** — test: Anderson & Goodman 1957 / Bell & Hinojosa 1977; needs a third certified date; interior-epoch bridge check is a consistency check only. Kill: the test must reject on a stratum where §6.1's development prior says rates changed (dated footprints). **[Q→S]; not runnable until a third lidar date exists** |

### 14.5 Row 14 — the edge-band false-positive rate from registration error, in closed form [D]

**Anchor [Q, review §4.14.3].** Dai & Khorram 1998: false change from misregistration is
"mainly distributed spatially along the edges"; the semivariance a shift adds equals the
autocorrelation drop at that lag (their eq. 5); on 30 m TM, one-fifth of a pixel of
registration error keeps change error under 10 %. Empirical curves, no formula.

**Derivation [D].** Let `A` be the canopy set of a binary mask and `s` a registration
offset vector. A cell is falsely flagged as change between two epochs of the *same*
scene shifted by `s` iff it lies in the symmetric difference `A △ (A + s)`. For a set with
finite perimeter `Per(A)` and `|s|` small relative to the feature size, the area of that
symmetric difference averaged over the direction of `s` is

```
E_θ |A △ (A + s)|  ≈  (2/π) · Per(A) · |s|          (Crofton / Cauchy mean-width form; [D])
```

so the false-change *fraction* of the scene is `≈ (2/π) · ρ_P · |s|` with `ρ_P` the
perimeter density (perimeter per unit area) of the canopy mask. With `|s|` drawn from the
epoch's registration-error distribution (`coregistration.csv`; p95 as the bound), the
expected edge-band false-positive rate is `(2/π) · ρ_P · E|s|`, and its worst case
`(2/π) · ρ_P · s_95`. Two consequences: (i) it is proportional to perimeter density, which
is why fragmented residential canopy is worse than a closed stand — Dai & Khorram's
"finer spatial frequency" in geometric terms; (ii) it is the size of the band in which
`f_{t,b}` (§12.1) must be allowed to rise, and the width `s_95` is the erosion radius of
§12.1 by construction. `ρ_P` is measurable from any mask in one pass.

**Kill.** On the 2016 lidar-coincident epoch, shift the mask against itself by the
measured `s_95` in eight directions and count the flagged fraction; the formula must
reproduce the mean within its small-`|s|` error, and must *fail* (over-predict, since
the symmetric difference is bounded by twice the area) once `|s|` approaches the typical
crown radius, where the linear term stops holding. If it cannot be made to fail, the
test is not testing the approximation. *Arithmetic self-check 2026-09-12, not
validation:* on a synthetic disc (`R = 50`, `|s| = 2`) the formula gives 400 against a
measured 393.5; on a square (`L = 100`) 509 against 502.5; at `|s| = 60 > R` it gives
12,000 against 11,173 — the over-prediction the kill expects.

### 14.6 Row 9 — the shape family for `D_k(τ)`, sourced [Q→S]

**Found [Q, review §4.15.1].** No fitted post-disturbance hazard exists (Hood et al.
2018: models are "binary—either the tree survives or dies"). But the *shape* is stated
with its mechanism by the fragment-ecology literature: one component that starts high
and declines over "the first few years" (immediate death of sensitive individuals,
acclimation, edge sealing — D'Angelo et al. 2004; Laurance et al. 2011) and one that
*rises* as the edge ages (wind exposure of a closing edge — Laurance et al. 2011). The
distance half is a separate regression (Mesquita et al. 1999: strongest within 0–20 m,
penetrating 40–100 m depending on the matrix).

**Substitution [S].** Replace §6.1's single decay with the two-term family

```
D_k(τ) = e^{−τ/k₁}  +  w · (1 − e^{−τ/k₂}) · 1[τ ≤ T_max]          k = (k₁, k₂, w, T_max)
```

— an immediate-clearing term that decays with `k₁` (the 2–3-year replanting horizon of
Conway 2022 and the 4–8-year windows of §14.3 bound it) and a delayed-removal term that
rises with `k₂` and is truncated at the window `T_max`. The first term's weight is fixed
at 1 because §6.1's amplitude `A` already multiplies `D_k`: with two free weights `A·w₁`
and `A·w₂` would be the only identifiable products and `A` alone would not be. Under
Baddeley & Turner's split (§13.3) `A` and `A·w` are canonical and `k₁, k₂, T_max`
irregular. **The family is quoted; every coefficient is fit on the LOSS build near dated
footprints; nothing here is a number.** Kill unchanged (row 9): no-change gold near new buildings must stay
no-change; and the two-term fit must beat the one-term fit on held-out permits by more
than the noise floor or the second term is dropped.

### 14.7 Row 10 — the blurred footprint indicator, in closed form [D] on a [Q] radial law

**Found [Q, review §4.15.2].** Leung & Yan 1997: a boundary with circular-normal
positional error of scale `σ` lies within the `r`-band of its nominal position with
probability `1 − exp(−r²/2σ²)` (their eq. 21); the exact point-in-random-polygon
probability is bounded, not closed (their eqs. 24–25).

**Derivation [D].** For a cell at signed distance `d` from the nominal footprint edge
(positive inside), and a locally straight edge displaced by a circular-normal offset of
scale `σ`, the probability the cell is truly inside the footprint is

```
π_in(d) = Φ(d / σ)          (Φ the standard normal CDF)
```

— the Gaussian-blurred indicator. It is exact for a straight edge, an approximation
within a curvature radius of corners, and it is the closed-form of the Girard et al.
2019a Gaussian-random-field offset (§14.3) for a single independent offset. §6.2's prior
becomes `u_i = log( P(z=1 | in) π_in(d_i) + P(z=1 | out) (1 − π_in(d_i)) ) − log P(z=1 | out)`.

**Which `σ` — stated precisely, because the obvious choice is wrong twice.** (a) The
offset between a footprint and an epoch's imagery is the *composition* of two errors:
the footprint layer's own positional error against the ground, and the image's
registration error against the ground. `phase4/qc/coregistration.csv` holds only the
second, and only relative to the 2020s anchor; the footprint half is not in any table
yet and must be measured once, against a lidar building reference at 2005/2016 where
both are absolute. (b) The table's columns are not `σ`: `median_dx_m / median_dy_m` are
per-axis *systematic* offsets — correctable at comparison time, so they are removed, not
blurred over — and `p95_mag_m` is a magnitude bound that per `docs/SCHEMAS.md` "includes
building lean, parallax and real change inside the chip, not pure georeferencing", so it
over-states registration. Under Leung & Yan's own circular-normal model the offset
*magnitude* is Rayleigh(σ), whose median is `σ√(2 ln 2) ≈ 1.18σ` and whose 95th
percentile is `σ√(2 ln 20) ≈ 2.45σ`; a quantile used as `σ` inflates the blur by that
factor. So: `σ_reg` is the residual scatter after the median offset is removed
(`σ ≈ p95_mag / 2.45` is an *upper* bound, given what p95 contains), `σ_fp` is the
footprint layer's own scale measured against the lidar reference, and
`σ² = σ_reg² + σ_fp²`. **No free parameter — but two measured ones, one of which does not
exist yet.** The same `σ_reg` sets the edge band of §14.5 and the erosion radius of §12.1.

**Kill — against a building reference, not the canopy.** The first draft of this kill
compared footprints to `CHM ≥ 5 m`; that measures canopy *overhanging* roofs (a real
signal with a transition width of a crown radius), not footprint position, and could
never recover a sub-metre `σ`. The valid form: on the 2016 lidar-coincident epoch, take
the lidar's building return class if the deliverable carries one (to be confirmed
against the lidar facts home, `IMAGERY_FACTS.md`), else roof height from DSM − DTM;
the empirical `P(building | d)` at signed distance `d` from the footprint edge must
follow `Φ(d/σ)` with the *measured* `σ`, and must visibly fail at `10σ`. If it needs a
fitted width to match, the registration table, the footprints, or the composition above
is wrong — and that is the finding.

### 14.8 Ledger deltas from round 6

| # | Was | Now |
|---|---|---|
| 9 | `D_k` shape [D]; `k ≈ 5 y` window | **two-term family [Q→S]** (decaying immediate + rising delayed, truncated at the window); coefficients fit; one-vs-two-term test added to the kill |
| 10 | blur = footprint ⊗ GRF-offset [S] | **closed form `π_in(d) = Φ(d/σ)` [D] on Leung & Yan's radial law [Q]**; `σ² = σ_reg² + σ_fp²` — `σ_reg` from the coregistration residual (quantiles converted, p95 an upper bound), `σ_fp` the footprint layer's own error, **not yet measured**; kill against a lidar building reference on the 2016 epoch |
| 14 | `(2/π)·ρ_P·|s|` [D] | Salas et al. 2003 publish the perimeter/area ratio as the empirical index of misregistration bias (METADATA, not obtained) — the same quantity; obtain it to re-bin toward [S] |

### 14.9 Row 14, addendum — Salas et al. 2003 read: a second tool, not the same formula

**[Q, review §4.15.2].** Salas et al. compute the perimeter/area ratio of each *change
clump* and compare it with the theoretical P/A of a one-pixel misregistration strip:
`4/x` for a diagonal strip (upper limit) and `(2/x)(1 + 1/n)` for a row/column strip of
`n` pixels (lower limit), `x` the pixel size. Clumps above the lower limit are candidate
linear false change; on their scene the area-weighted upper bound on such change was
9.55 % / 4.13 % of two change classes.

**Relation to §14.5 [D].** Different object. §14.5 predicts the *expected* false-change
area of a scene *a priori* from the mask's perimeter density and the registration
offset; Salas screens *observed* change clumps *post hoc* by shape. They share the
premise — false change is a strip along a class boundary — which Salas state and test,
so §14.5's premise is now [Q] while its formula stays [D]. **Substitution [S] of the
Salas screen to our grid:** on the 2 m grid with a registration offset of `s` cells, a
sliver's P/A is bounded below by `(2/(s·x))(1 + s/n)` for a straight boundary; any
flagged change clump above that bound and within `s_95` of a class boundary in the
earlier epoch is a candidate sliver and goes to the CUSUM/chain as `⊘`, not as
evidence — a rule for §7.3 that costs one connected-components pass. **Kill:** the
screen must flag the self-shift slivers of §14.5's kill at ≥ 95 % and must *not* flag
the 42 verified losses; a screen that removes verified change is laundering by another
name.

Ledger row 14 → premise [Q] (Salas 2003), rate formula [D] (§14.5), sliver screen [S]
(§14.9); Leung–Ma–Goodchild Parts 2–4 still unobtained (the editorial introduction is
filed and carries no formulas).

---

## 15. Round 7 — the closed papers, obtained: three results change (2026-09-12)

### 15.1 Row 6 — the per-cell penalty in closed form under dependence: no bootstrap [Q→S]

**[Q, review §4.16.1–4.16.2].** Efron 2004 eq. 3.19 defines the *conditional*
covariance `cov₍ᵢ₎ = E{λ̂_i (y_i − μ_i) | y₍ᵢ₎}` and states the conditional optimism
theorem `E₍ᵢ₎{Err_i} = E₍ᵢ₎{err_i} + 2 cov₍ᵢ₎`; eqs. 3.21–3.22, the "Steinian", give it
in closed form for Bernoulli `y_i`:

```
cov₍ᵢ₎ = μ_i (1 − μ_i) · [ λ̂_i(y₍ᵢ₎, y_i = 1) − λ̂_i(y₍ᵢ₎, y_i = 0) ]
```

— one recomputation of the layer per cell with that cell's label flipped. Besag 1974
eq. 4.8 gives, for an autologistic field, `P(x_i = 1 | x₍ᵢ₎) = expit(α_i + Σ_j β_ij x_j)`
with coding-method (pseudolikelihood) estimation.

**Substitution [S].** Conditioning on `y₍ᵢ₎` is what makes dependence harmless: given the
other cells, `y_i` is Bernoulli whatever the joint law, with parameter
`μ_i|₍ᵢ₎ = P(y_i = 1 | y₍ᵢ₎)`. Under the autologistic error model of §13.1 that is
Besag's (4.8). Hence, per certified cell and band,

```
Ω_i = 2 · p_i (1 − p_i) · [ λ̂_i(flip_i = 1) − λ̂_i(flip_i = 0) ],
p_i = expit( α_b + Σ_{j ~ i} β_b(d_ij) y_j )
```

with `(α_b, β_b(·))` fitted once per stratum and band by pseudolikelihood (Besag) or
MCML (Geyer & Thompson). **The correlated bootstrap of §13.1 is no longer needed for
`Ω`**: the penalty is exact given the fitted local conditional, costs one layer
evaluation per certified cell (the same count as cross-validation, as Efron notes), and
is *local*, so it runs on the strata only. The bootstrap remains useful for intervals.
The independent-Bernoulli version of the same formula (marginal `μ_i` in place of
`p_i`) is what §5.1 implicitly assumed; the two differ exactly where the correlogram is
non-zero.

**Kill.** On a synthetic autologistic field with a known layer, `Ω` from the
flip-with-local-conditional estimator must match the Monte-Carlo truth within its
standard error, and the marginal-`μ` version must be biased by an amount that grows
with `β`; then the same comparison on `ℱ` with the fitted `(α, β)`. A version that
cannot be made to disagree with the marginal one on an injected correlation is not
testing the correction.

### 15.2 Row 11a — the yearly root, re-binned [S→Q] with its failure modes [Q]

Takada et al. 2010 state the `c`-th power root of a `c`-year transition matrix via
eigendecomposition, "conditional as follows: 'if an n-by-n matrix has n distinct
eigenvalues and all of them are not equal to zero'", and its two practical failures:
multiple roots (the scalar root is multi-valued) and roots "partially consisting of
negative numbers". For the 2×2 chain the eigenvalues are `1` and `λ = 1 − Q_g − Q_l`;
the root is unique, real and a proper stochastic matrix iff `0 < λ < 1`, which §12.2's
closed form assumed and can now cite. **Guard [D]:** if a stratum's `Q_g + Q_l ≥ 1` over
the 11-year interval the yearly rate is undefined (the chain has mixed), and that
stratum's anchor carries no information about `(r, f)` at any `k > 0` — report it as
such rather than extrapolate.

### 15.3 Row 10 — what Part 2 and Shi add, and do not

Leung, Ma & Goodchild Part 2 confirm the gap in their own words (§4.16.4) and give
bounds under *independent, normal* vertex errors — a condition a digitised footprint
layer violates (its vertices share one georeferencing error). §14.7's `Φ(d/σ)` treats the
whole edge as displaced together, which is the correlated limit, so it is the right
model for a layer offset rather than for jittered vertices; Part 2 is the right model
for the *other* case and is cited for it, not adopted. Shi 1998's point — the epsilon
band "does not define the relationship of the band width with confidence level" — is
the formal statement of why §12.1's erosion radius must be a quantile of `σ`, not a
round number.

### 15.4 Ledger deltas from round 7

| # | Was | Now |
|---|---|---|
| 6 | fully sourced; correlated bootstrap | **closed-form per-cell `Ω` via Efron's Steinian with Besag's local conditional [S]; bootstrap only for intervals**; kill: must disagree with the marginal version on an injected correlation |
| 11a | `λ^k` and yearly rate [S] | yearly root **[Q]** (Takada 2010) with the `0 < λ < 1` existence condition and a mixed-stratum guard [D] |
| 10 | `Φ(d/σ)` [D] on Leung & Yan | unchanged; Part 2's independent-vertex bounds cited as the other regime; Shi 1998 anchors "quantile of σ, not a fixed radius" |
| 9 | two-term family; radii 0.7–1.4 / ~20 m | radii now PRIMARY-quoted (Guo 2018: 1.4 m, 44 % vs 13.5 %, >3×); Steenberg 2017 vs 2018 are two papers |

## 16. Round 8 — the remainder read: one rule sourced, one law added, one correction (2026-09-12)

Review §4.17. Nothing here changes an estimator; it changes what the estimators rest on.

### 16.1 Row 6 — the `G(t)` leave-out rule, quoted [ABSTRACT→Q]; the block rule second-sourced [Q]

§13.1 item 2 held out epoch `t` *and every epoch whose error correlates with it* on an
abstract-grade reading of the blind-spot literature. The rule at its source (Broaddus et
al. 2020, review §4.17.1): hide, in addition to the active pixel, the neighbouring pixels
"that contain information about the noise of the active pixel", and keep the loss "active
for individual pixels" only. Translated to the chain: `G(t) = {t' : ρ_res(t, t') > noise
floor}`, the cross-epoch residual correlation of §13.1 measurement (b); the identity of
§12.4 holds with `x_{−G(t)}` in place of `x_{−t}`; the score stays per held-out cell.
What `ρ_res` is remains [D — measurement]; the rule that consumes it is now [Q].

The §12.2 block size (Valavi et al. 2018) is second-sourced by Roberts et al. 2017: blocks
"at least as many units as the range of autocorrelation" as read from the correlogram.
Two independent statements of the same rule; measurement (a) of §13.1 feeds both.

Lineage, for the record: Efron 1986 states the model with "the yi independently equal 1 or
0"; Efron 2004 §3 conditions on the observed data and drops independence; §15.1's per-cell
Steinian with Besag's local conditional is that 2004 form on the autologistic field. Row 6
is closed by a chain of three read papers, none of them ours.

### 16.2 Row 4 — three smoothers, three erasure laws; the choice is the only open input

Bellettini, Caselles & Novaga 2002 (review §4.17.1) give the total-variation *flow*
`u_t = div(Du/|Du|)` on an indicator: for a bounded convex set with `C^{1,1}` boundary
whose curvature never exceeds `λ_Ω = P(Ω)/|Ω|`, `χ_Ω` evolves as `(1 − λ_Ω t)⁺ χ_Ω` — a
uniform linear fade with no boundary motion, extinct at `t = 1/λ_Ω`. A disc of radius `R`
has `λ = 2/R` and curvature `1/R ≤ 2/R`, so its indicator is gone at **`t = R/2`**; run the
flow for time `t` and every convex feature with `|Ω|/P(Ω) ≤ t` is erased. **[Q]** for the
law; **[D]** for the reading "run time `t` ⇒ `R_erase = 2t`" on a probability raster,
where the input is not an indicator.

| smoother | erasure of a disc of radius `R` | contrast-dependent? | source | bin |
|---|---|---|---|---|
| ROF (TV-L2 minimisation), weight `α` | erased when `R ≤ 2α/h`, `h` the feature contrast | yes | Strong & Chan 2003 §3.1 | [Q]+[S], §3.3 |
| TV-L1 minimisation, weight `λ` | removed whole iff `λ < 2/R` ⇒ `R_erase = 2/λ` | no | Chan & Esedoglu 2005 §3; Duval et al. 2009 | [Q], §13.2 |
| TV flow, time `t` | indicator extinct at `t = R/2` ⇒ `R_erase = 2t` | no (indicator input) | Bellettini, Caselles & Novaga 2002 | [Q], this section |
| mean-field CRF | no result (PRIMARY negative) | — | §13.2 | measurement only |

The two contrast-independent laws are the argument, already made in §3.3's last
paragraph, for a TV-L1-type smoother over ROF on a probability raster: with ROF a 60 %-
confident removal is erased at a larger physical size than a 95 %-confident one; with
TV-L1 or the flow the erased size is a property of the smoother alone. The smoother is a
§9 decision (Kam's); whichever is chosen, its row above states `R_erase` before any
`(β, γ)` fit, and the injected-disc kill of §13.2 applies to all four.

### 16.3 Rows 9, 10, 14 — grades, one correction, one option

- **Row 9.** Morgenroth et al. 2017's radii (0.7 m to a demolished building; 20 m to a
  driveway) are now quoted from the paper (review §4.17.2), not from Hilbert's table; the
  §14.6 two-scale reading stands. The paper also splits on crown area (7.9 m²) — a size
  covariate the per-cell chain cannot carry (crown polygons exist only for 2020; CLAUDE.md
  §1), so it is noted and not added. **Correction, at the text:** the 6–7 y window in
  §14.6 belongs to Steenberg, Robinson & Millward (JEPM; 806 trees re-measured between
  2007/08 and 2014), which Hilbert cites under its 2018 print volume. The Environment &
  Planning B 2018 paper, read this round, is a census-tract regression on 2003 and 2014
  imagery and carries neither figure. The window and `k ≈ 5 y` as the fit's starting
  value are unchanged (Hauer 4–8, Guo 4–5, Steenberg 6–7).
- **Row 10.** Leung & Yan 1998 confirms the circular-normal point model and the Rayleigh
  radial law at the text (second source for §14.7's `Φ(d/σ)`); STAPLE's negative is
  confirmed at the text (rater sensitivity/specificity, nothing positional). §14.7
  unchanged; its inputs (σ_fp; a building reference) are still measurements.
- **Row 14.** Stow 1999 is a third tool: gradient-weighted *compensation* of the
  difference magnitude from sparse misregistration estimates. It corrects a continuous
  difference image; our object is a binary mask difference, so it is recorded as an
  option **[S]**, not adopted — reconsider only if row 14's measurement (p95 of
  `coregistration.csv` against 2 m) admits the 0–2 m band and the §14.9 screen proves
  insufficient.
- **Row 6, mechanism.** Burnicki 2010 (abstract): raising temporal dependence between
  classification errors "did not improve the accuracy of resulting maps of change" once
  the class count rose. Ours is one class; the 2007 binary mechanism (§14.2) applies
  unchanged.

### 16.4 Ledger deltas from round 8

| # | Was | Now |
|---|---|---|
| 4 | TV-L1 closed form; Potts [D]; mean-field none | + TV-flow extinction `t = R/2` [Q]; three laws tabulated (§16.2); the smoother choice is the only open input |
| 6 | per-cell `Ω` [S]; `G(t)` on an ABSTRACT source | `G(t)` rule [Q] (StructN2V quoted); block size second-sourced (Roberts 2017) [Q]; the two correlograms unchanged [D — measurement] |
| 9 | radii via Guo 2018 and Hilbert | Morgenroth 0.7 m / 20 m PRIMARY-quoted; 6–7 y / `n = 806` confirmed at the text as the JEPM Steenberg paper (2007/08 → 2014) |
| 10 | `Φ(d/σ)` on Leung & Yan 1997 | second-sourced (Leung & Yan 1998); STAPLE negative confirmed at the text |
| 14 | rate [D] + screen [S] | + compensation option (Stow 1999) [S], not adopted |

### 16.5 What is not obtained, and why it does not matter

Conley 1999 (indexed on the second mirror, whose storage host went behind a JavaScript
bot challenge that afternoon — round 8 had misread the 403 as a missing file) would supply a heteroskedasticity-and-autocorrelation-consistent variance
for the correlogram estimates; §15.1's per-cell Steinian and the correlated bootstrap for
intervals cover that need. The four MDPI papers and Laurance 1998 *Ecology* are cited by
nothing in this document. **Nothing load-bearing is unread.** Every row still open in §11
closes by a measurement named in its "cheapest closing step" column, and the first three
of those (row 12's convention check, §15.1's synthetic-autologistic kill, the `𝒞` and
LOSS rules) need no lake write and no GPU.

## 17. Round 9 — seven fields named from the [D] list, searched: what became theorem, estimator, or kill (2026-09-12)

Review §4.18. Rule for this section: a [D] line moves only if the theorem or estimator
was read at the passage; searcher-verified files move nothing.

### 17.1 §14.5 — the edge-band rate is the covariogram slope [D→Q]

Galerne 2011, Eq. 2 (review §4.18.1): for any measurable planar set the perimeter equals
`−(1/2)∫_{S¹}(g^u)′(0⁺)du`, so the direction-averaged slope of the covariogram at zero is
`−Per/π` and `|Ω Δ (Ω+s)| ≈ (2/π)·Per(Ω)·|s|`. §14.5's false-change fraction
`(2/π)·ρ_P·|s|` (with `ρ_P = Per/area`) is therefore Matheron's result, attributed by
Galerne to Haas et al. 1967, Matheron 1975 and Serra 1982. Two consequences: (i) the
numeric self-check in §14.5 now checks a theorem, not a derivation; (ii) Eq. 1 supplies
the **directional** version — slope in direction `u` equals `−V_u(Ω)`, the directional
variation (for a smooth boundary, the total projected width in that direction). The
per-axis systematic medians in `coregistration.csv` are a directional shift, so the
correctable component uses Eq. 1 with `u` along the measured axis and the isotropic
residual uses Eq. 2. The kill in §14.5 (linear term over-predicts at large `s`) stands;
the small-`s` regime is the one the theorem covers.

### 17.2 §14.7 — the σ composition is the Law of Propagation of Errors [D→Q]; `Φ(d/σ)` stays [D]

Chrisman 1982 (review §4.18.2): independent error sources introduced at successive
stages compose by "adding the variances of the distributions". `σ² = σ_reg² + σ_fp²` is
that law with its assumption stated — registration residual and footprint digitising
error must be independent, which they are by construction (different instruments,
different epochs). No source states the blurred indicator `Φ(d/σ)`; the medical-imaging
literature builds soft labels by fixed-radius dilation (a step, not a Gaussian ramp) —
recorded as a negative. `Φ(d/σ)` remains a one-line derivation of ours, and the §14.7
inputs (σ_fp; a building reference) remain measurements.

### 17.3 Row 3 — the layer's model is the spatio-temporal autologistic regression [D→Q for equal intervals]

Zhu, Huang & Wu 2005 (review §4.18.3) is the framework's §2 chain plus §3 coupling in one
published conditional: covariates (development, building, water priors as regressors),
a spatial autoregression `θ_{p+1}` (our `β`), a temporal autoregression `θ_{p+2}` (our
`γ`). Published with it: maximum pseudo-likelihood for the parameters, Gibbs sampling for
prediction, parametric bootstrap for standard errors. Hughes, Haran & Caragea 2011 add
the practical recommendation — the *centered* parameterisation and PL — because in the
traditional model the autocovariate absorbs large-scale structure that the regressors
should carry; here that is exactly the competition between the development prior and
the spatial term. **What stays [D]:** their field is undirected in time (`Y_{i,t}`
conditions on `Y_{i,t−1}` *and* `Y_{i,t+1}`) on equally spaced `t ∈ Z`, with time-invariant
coefficients. Our epochs are irregular and the §2 chain is forward. Two routes, both ours:
(a) fit their model on the yearly grid of §15.2 with missing epochs marginalised by the
Gibbs step (their prediction machinery already handles unobserved `Y_t`); (b) keep the
forward chain and set `γ(Δt)` from the yearly root, `γ(Δt) = logit`-scale image of
`λ^{Δt}`. Route (a) uses only published pieces; route (b) uses §15.2 [Q] plus a [D] map.
Kill unchanged (§3.4 injected disc; §11 row 3: `(0,0)` reported). Software: `ngspatial`
(areal, centered, PL) exists; the temporal term does not, in it.

### 17.4 Row 9 — `D_k(τ)·R(d)` has a nonparametric estimator: the ETAS kernel by EM [Q for the estimator; D for the mapping]

Ogata 1988's epidemic form (review §4.18.4): intensity = background + Σ over past events
of a kernel `g(t − t_i)`; the space-time version has `g(τ, d)`. Marsan & Lengliné's
model-independent declustering (Reinhart 2018 §3.2.3) estimates `g` as **piecewise
constant in `(τ, d)`** by EM — a histogram kernel, no shape assumed — and Zhuang 2002's
branching probabilities attribute each event to background or to a specific parent. The
mapping to us is not in those papers and is [D]: the "parents" are dated developments
(known, exogenous — no branching to estimate), the "events" are certified losses on
`𝒞`, and the kernel is the excess loss hazard at lag `τ` and distance `d`. Under that
mapping the EM reduces to a weighted histogram: for each certified loss, distribute its
weight over the developments within `(T_max, R_max)` in proportion to the current `g`,
re-estimate `g` on the `(τ, d)` bins, iterate. The two-term family of §14.6 becomes the
*parametric* alternative, tested against the histogram by the same held-out
log-likelihood as the one-vs-two-term test. Bacry 2015's caveat applies: EM is slow for
slowly decaying kernels and cannot produce negative bins (a protective effect after
replanting would be invisible; §14.6's `1[τ ≤ T_max]` truncation handles it). The
multiplicative local-transition form of §6.1 is second-sourced in remote sensing by Liu
et al. 2008 (review §4.18.9).

### 17.5 Row 6 — the §15.1 kill has a published form; two block-size rules that answer different questions

Kaiser, Lahiri & Nordman 2012 (review §4.18.8): generalized spatial residuals of a fitted
MRF, computed within concliques, are i.i.d. uniform under the model. That is a
goodness-of-fit test for the autologistic fit §15.1 relies on, and it is the test the
synthetic-autologistic kill should run: on a field simulated from the fitted model the
conclique residuals must pass; on the real strata they either pass (model adequate,
per-cell `Ω` trusted) or fail (and the correlogram measurement says how). Block size:
Nordman & Lahiri 2004 give `m ∝ n^{1/3}` as MSE-optimal for *variance estimation* by
subsampling; Roberts 2017 / Valavi 2018 give "at least the autocorrelation range" for
*leakage-free validation*. §12.2 keeps the range rule (its purpose is leakage);
§15.1's interval bootstrap uses the `n^{1/3}` rule.

### 17.6 Row 11a — the guard is the theorem; and what to do when it fails [Q]

Kingman 1962 Proposition 2 (review §4.18.5): a 2 × 2 stochastic matrix has a
continuous-time generator iff `det P > 0` and `tr P > 1`. With `λ = tr P − 1` for two
states, that is `0 < λ < 1` — §15.2's existence guard is the necessary-and-sufficient
condition, not a heuristic. Israel, Rosenthal & Wei 2001 Theorem 2: `p_ii > 1/2` for all
`i` guarantees the log-series converges and (Cuthbert) the generator is unique — for a
persistence chain both diagonals exceed one half by construction, so the yearly root is
unique when it exists. When a multi-state matrix (the `K`-bin emission chain of §2.3 A, or
a mixed stratum) fails: Israel's §3 fix (zero small negative off-diagonals, redistribute
along the row) or Charitos 2008's minimum-distance row regularisation, both [Q]; the
choice is a §9 decision, recorded when it arises.

### 17.7 Row 2 — the CUSUM threshold is an exact computation, not a Monte Carlo [Q]

Reynolds & Stoumbos 2000 Appendix C (review §4.18.6): the in-control run length of the
Bernoulli CUSUM is exact from a Markov chain on the chart's `t = mh` transient states
(the Brook–Evans construction), when the log-likelihood-ratio increments are in integer
ratio `m`. Row 2's threshold per `(population, band, α)` is therefore solved by
inverting that run-length formula for `h`; the Monte Carlo on null sequences becomes the
check that the implementation matches the formula. The transition matrix itself is in
the 1999 *JQT* paper (indexed, behind the challenge); until it is read, the construction
is [Q] by description and the matrix is rebuilt from the chart definition [D] — a
one-page derivation, checkable against Lucas & Crosier's Table 1 values.

### 17.8 Ledger deltas from round 9

| # | Was | Now |
|---|---|---|
| 2 | Monte Carlo threshold [D] | **exact Markov-chain run length [Q]** (Reynolds & Stoumbos 2000 App. C; Brook–Evans); Monte Carlo is the check |
| 3 | `(β, γ)` open [D] | **model, MPLE, bootstrap SEs published [Q] for equal intervals** (Zhu 2005; Hughes 2011 centered + PL); irregular-interval temporal term [D] via §15.2 |
| 4 | TV-L1 / TV-flow [Q]; Potts one-liner [D] | unchanged — nine graph-cut papers filed, unread |
| 6 | per-cell `Ω` [S]; `G(t)` [Q] | + **published goodness-of-fit kill [Q]** (Kaiser–Lahiri–Nordman conclique residuals); block rules separated by purpose |
| 9 | two-term `D_k` family [S]; coefficients fit | + **nonparametric `(τ, d)` histogram kernel by EM [Q]** (ETAS/MISD); mapping to dated developments [D]; §6.1 form second-sourced (Liu 2008) |
| 10 | `Φ(d/σ)` [D]; σ composition [D] | **composition [Q]** (Chrisman 1982, Law of Propagation of Errors); `Φ(d/σ)` still [D]; dilation-based soft labels a negative |
| 11a | yearly root [Q]; `0<λ<1` guard [D] | **guard is Kingman's iff condition [Q]**; uniqueness for `p_ii > ½` [Q]; regularisation when invalid [Q] |
| 14 | rate [D]; screen [S]; compensation option [S] | **rate [Q]** (Galerne Eq. 2 = Matheron); directional form (Eq. 1) for the per-axis medians |

### 17.9 What round 9 did not obtain, and whether it matters

Twelve indexed papers sit behind one JavaScript challenge on the second index's storage
host (review §4.18, closing list). Three of them would move a grade: Reynolds & Stoumbos
1999 (the CUSUM transition matrix, [D→Q]), Zhu et al. 2008 (MCML for the spatio-temporal
autologistic model, the fit §17.3 would use at scale), and Marsan & Lengliné 2008 (the
MISD estimator at its source rather than via Reinhart). The other nine attribute or
confirm. A browser can pass the challenge where `curl` cannot; that is Kam's call.
