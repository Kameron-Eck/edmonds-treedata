# Spatio-temporal consistency — framework and the mathematics still open

**Status: DESIGN-STAGE. UNVALIDATED. Nothing here is a measurement on our data.** This
document assembles the halves the literature supplies into one framework and names, as
precisely as it can, what is still ours to derive or measure. Written 2026-09-11. Owner:
Kam. It sits under the brief (`TEMPORAL_SPATIAL_CONSISTENCY_BRAINSTORM_2026-09-10.md`, the
home of every measured number about our stack — §-references without a prefix are to it)
and the review (`LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md`, the home of every
citation — referenced as *review §x*). This file carries no bibliography and restates no
measured number as its own; where a number appears it is cited to its home.

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

- Cells `i = 1..N` on the 2 m analysis grid; `N ≈ 13.3 M` (§2.3). Epochs `t = 1..T`,
  `T = 12`, 2009–2024 (§1).
- Latent state `z_{i,t} ∈ {0, 1}` (not canopy / canopy).
- Hard observation `x_{i,t} ∈ {0, 1, ⊘}`, `⊘` = IGNORE, from the mask
  (`phase4seg/postproc.py::threshold_and_clean`). Soft observation
  `p_{i,t} ∈ [0, 1] ∪ {⊘}` from the probability raster written by
  `phase4seg/core.py::step_inference`: uint8, `k ∈ 0..254 → p = k/254`, `255 = ⊘`. The
  raster is kept per epoch alongside the mask; the float logits are not (session code
  check, 2026-09-11).
- **Per-epoch eyesight, in the brief's convention:** `r_t = P(x = 1 | z = 1)` is
  **recall**, `f_t = P(x = 1 | z = 0)` is the false-positive rate (§2.3: "r ≈ 0.61,
  f ≈ 0.05"; the emission gate "f 0.011–0.082 < r"). The miss rate is `1 − r_t`. *The
  round-2 agents wrote r for the miss rate; every formula below has been re-expressed in
  the brief's convention. That translation is [S] and is the first thing to check.*
- Transitions `q_loss = P(z_{t+1} = 0 | z_t = 1)`, `q_gain = P(z_{t+1} = 1 | z_t = 0)`.
  Pre-registered `q_loss = 0.02` (§2.3); the review's recommendation (review §6 item 2) is
  to estimate both from the certified populations instead.
- Certified populations (§2.2): `𝒢` = lidar-certified GAIN 2005→2016 (46,805 cells),
  `ℱ` = lidar-certified FLAT (40,609 cells), on the sample blocks. Gold (§2.4): 1,214
  points = 1,170 no-change / 42 loss / 2 gain, ruling on 2016→2024, no false-positive
  class.
- Rates in hand (§2.3): C-CAP-2021- and C-CAP-2016-referenced `(r_t, f_t)` for all twelve
  tags at the delivered cut. **Lidar-referenced rates do not exist yet.** Everything below
  runs on the C-CAP rates until they do, and C-CAP overestimates canopy (§4.3 item 2).

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
i.e. the "likelihood ratio ≈ 2.5" of §2.3; four are `≈ 3.56` nats `≈ 35:1` (the brief's
"≈ 39:1" rounds 2.5 first); the persistence prior's cost is `log(0.98/0.02) ≈ 3.89` nats
`= 49:1`. Nothing new; the point is that the chain, the CUSUM (§2.2) and the gate (§4)
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
read against, in closed form, and the brief's emission gate `f < r` (§2.3) is exactly the
condition that keeps it finite.

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
   brief's placebo (§5: shuffle the survey-to-rate assignment, 20 draws; agreement must
   fall) is the kill that must fire on this calibration before it counts.

### 2.3 The soft emission — the decision that settles the logits question

Everything above uses hard `x`. The brief's §4.5 and the review's §4.9 argue for sitting
*upstream of the threshold*, on `p_{i,t}`. That changes the emission from two numbers per
epoch to a distribution `e_t(p | z)`, and there are two ways to get it:

**Option A — binned emission [D].** Bin `p` into `K` levels `b(p) ∈ {1..K}` and estimate
the multinomial `e_t(b | z)` per epoch on cells whose `z` is certified: `ℱ` (`z` fixed),
`𝒢` after 2016 (`z = 1`), the lidar epochs directly. Then `ℓ_t = log e_t(b | 1) / e_t(b | 0)`
— the same shape as §2.1 with `K` outcomes instead of two. `K` is chosen by held-out
log-likelihood on the certified cells, not by hand; a rule of thumb (every `(bin, z, t)`
cell holding enough certified samples to estimate a proportion) is a placeholder until
that criterion is run. **uint8 suffices: 254 levels ≫ K.**

**Option B — calibrated log-odds [D].** Use `ℓ_t = logit(p_{i,t}) + c_t` directly. This
requires `p` to be *calibrated* per epoch, i.e. `P(z = 1 | p) = p`. The review's §4.12.3
(Kumar, Liang & Ma 2019) says a continuous corrector's "true calibration error is
unmeasurable with a finite number of bins" — so calibration would have to be *assumed*.
And at the uint8 ceiling `p = 254/254 = 1` the log-odds are infinite: this option needs
the float logits.

**Verdict [D]:** Option A, unless a per-epoch calibration audit on the certified cells
passes at a stated tolerance — which is itself a binned test, so it collapses into A.
**The raw-logits patch is only needed for Option B. Hold it until §11 gap 1 is
resolved; the choice is analytic, not a preference.**

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
carries a 2016 observation across every interior IGNORE epoch essentially undiminished.
Seven of ten interior epochs carry only IGNORE in places (§4.5), so this number, not the
smoothing weight, governs how far a single confident year reaches. Whatever `q_loss, q_gain`
the certified populations yield (§11 gap 11), `k_½` should be reported next to them.

---

## 3. The spatial coupling (brief §4.1, axes 2 and 3)

### 3.1 The joint field, as an energy

The brief's "formal object: a random field in space and time" (§4.1) written down **[D;
shape from Krähenbühl & Koltun 2011, review §4.12.1]**:

```
E(z) = Σ_{i,t} ψ_u(z_{i,t})
     + β · Σ_t Σ_{(i,j) ∈ N_s} ψ_s(z_{i,t}, z_{j,t})        (space, same epoch — axis 2)
     + γ · Σ_i Σ_t ψ_τ(z_{i,t}, z_{i,t+1})                (time, per cell — axis 1)
```

with `ψ_u(1) − ψ_u(0) = −ℓ_t` (the §2.1 evidence as the unary), `ψ_τ = −log T(z_t, z_{t+1})`
(the chain), and `ψ_s` a Potts or contrast-sensitive pairwise term. Axis 3 (the
twelve-year consensus) is not a separate term: it is what `γ` and the chain already
propagate. Two limits are the baselines: `β = 0` is exactly the per-cell chain the brief
already has (§2.3 engine); `γ = 0` is a per-epoch CRF.

### 3.2 Estimating `(β, γ)` — the protocol, and the two warnings

The brief says the local/global weight is "a parameter to be MEASURED, not set" (§4.1). The
literature has no measured value and one protocol (Gräler et al. 2016, review §4.12.1):
**fit the weight, then test the fitted model against the `β = 0` and `γ = 0` baselines on
held-out data.** Here **[D]**: choose `(β, γ)` to minimise the Efron-penalised counting
error of §5.1 summed over `𝒢 ∪ ℱ`, and report `(0, γ̂)`, `(β̂, 0)` and `(0, 0)` beside
it. Two published outcomes are legitimate results, not failures: Gräler's (a threefold
spread in fit bought no held-out skill) and Krähenbühl's ("the smoothness kernel
parameters … do not significantly affect classification accuracy"). If either recurs here,
the weight is inert on our data and the chain alone is the layer.

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
float32 with row-block chunking (§2.3). **The spatial pass is the only expensive part.**
Mean-field has no convergence guarantee (nor does Krähenbühl's); stop at a fixed iteration
count and report the objective's change. Liu et al. 2021's ordering (review §4.2, spatial
*then* temporal, once) is the thing not to do: alternate, so neither pass hardens the other's
error in.

---

## 4. Confidence gating — where it lives, and where it does not

The brief wants each survey's vote "weighted by its measured eyesight" (§3 rule 4) and a
per-cell weight "derived from the survey's own measured r and f" (review §4.2). Martinis &
Twele 2010, read in full (review §4.2, §4.12), gates *whether* a node enters the contextual
update by a threshold on its posterior entropy; the weights for admitted nodes are fixed at
1 and never swept.

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
decomposition is §11 gap 5.

### 5.3 What the 42 losses can and cannot resolve

**[D]** The terminal-absence kill is recall on 42 verified losses (§5). At a true recall of
`0.80`, the 95 % interval on 42 trials is `±1.96·√(0.8·0.2/42) ≈ ±0.12`. **Two layers whose
true recall differs by less than ≈ 0.12 are indistinguishable on the gold alone.** The
42-loss kill has power for large effects only; small effects are testable on `𝒢`
(46,805) and `ℱ` (40,609), which is why §5.1 sums `Ω` there. The 2 gains resolve nothing.

### 5.4 Correlated error — the open gap

Every tool in §5 assumes the observation is *unbiased* for truth. Ours is not: leaf-off
flights and an 80.7 cm effective 2005 give species- and season-correlated error (CLAUDE.md
§4), and the reference itself may share the model's edge errors (review §4.7). Round 2 found
nothing for the covariance penalty under spatially and class-correlated error. **Mitigation,
not a fix [D]:** stratify `Ω` additionally by flight month (from the acquisition-date home,
`qc/imagery_pixelsize_and_date.csv`) and by the coregistration bound, and report per stratum.
This is §11 gap 6 and the hardest item on the ledger.

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
brief already orders first (§4.2, §7 step 1). Two bounds from the review, both
Christchurch/Seattle and not ours: Pedley & Morgenroth 2025's Table 2 puts 12.78 % of
citywide loss on 2.33 % of parcels — a per-parcel enrichment of ≈ 5.5× **[D from review
§4.4 figures]** — and Seattle's ratios are net-over-net, not gross (review §4.4). Rosa et al.
2013 (review §4.4): score the *year* of loss, not only the place. **The statistical home
of this form — survival analysis with time-varying covariates — was not searched (review
§5 item 2).**

### 6.2 Buildings as a soft prior, measurable from data we already hold (brief §6.2)

The review answers §6.2 "soft, not hard" (review §4.10, §6 item 5). The soft form
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
`threshold_and_clean` (§2.4) with an operator that cannot turn 255 into a class. No
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

The impossible-triple count (§2.1) is reported as a secondary and never optimised: the brief
records that it has no power at this cadence. Li et al. 2025's change/no-change matrix
(review §4.11) is the reporting shape; the certified strata are a stronger denominator than
theirs.

---

## 9. What this changes in the brief's order (§7)

- **Step 2 (per-cell port)** — unchanged, but scored with §8 and §5.1, and with the
  §2.2 detector run on the same chain (same `ℓ_t`; the marginal cost is the Monte-Carlo
  threshold).
- **Step 3 (consensus features)** — becomes the `(β, γ)` fit of §3.2 with its three
  baselines; "swept and READ against the gold" becomes "fit on `𝒢 ∪ ℱ`, read on the gold
  and per stratum."
- **The raw-logits patch** — hold until §11 gap 1 resolves (§2.3).
- **New, before step 3, both CPU, both on files that exist:** the `K`-bin emission audit
  (gap 1) and the Monte-Carlo threshold (gap 2).

---

## 10. Where the compute goes

Per-cell chain and CUSUM: `N` independent 12-step recursions — CPU, parallel, free tier;
memory as noted in §2.3. Leave-one-epoch-out scoring (§5.2): `T` such passes. Efron
bootstrap (§5.1): `B` reruns, strata-local. Spatial mean-field (§3.4): the one GPU-shaped
cost, or permutohedral on CPU. Nothing here needs training.

---

## 11. Gap ledger — what is still ours to derive or measure

| # | Gap | Blocks | Cheapest closing step | Kill that must FIRE on a known-bad input | State |
|---|---|---|---|---|---|
| 1 | Emission model: `K`-bin (§2.3 A) vs calibrated log-odds (B) | the logits patch; everything upstream of the threshold | held-out log-likelihood of `e_t(b\|z)` on certified cells across `K` | placebo rate shuffle (§5): likelihood must fall | **[D] open — decides the patch** |
| 2 | Two-sided CUSUM thresholds at `T = 12` with per-year rates | the detector (§2.2) | Monte Carlo on null sequences, per-year `(r_t, f_t)` | null sequences must not alarm above `α`; placebo must fall | **[D] open** |
| 3 | `(β, γ)` estimation | the spatial layer (§3) | Gräler protocol on `𝒢 ∪ ℱ` with `(0,γ̂)`, `(β̂,0)`, `(0,0)` | `(0,0)` reported; an inert weight is a result | **[D] open** |
| 4 | Erasure radius for the smoother actually chosen | §3.3; the "never redraw" question (§6.1 of the brief) | linear: closed form; non-linear: injected disks on real rasters (operator only) | 42 losses and `𝒢` (claim) | **[S→D] open** |
| 5 | Leave-one-epoch-out scoring identity under Bernoulli noise | §5.2 | derive the counting-error decomposition with known `(r_t, f_t)` | a non-invariant (median-type) layer must show the Noise2Self failure when checked | **[D] not derived** |
| 6 | Covariance penalty under spatially / class-correlated error | §5 as a whole | none found; stratify by flight month and registration bound | — | **OPEN, hardest** |
| 7 | Power: 42 losses resolve `Δ ≳ 0.12` only | which kills can decide small effects | use `𝒢`, `ℱ` for small effects | — | **[D] derived, stated** |
| 8 | Conservative mask fraction `φ` | §7.2 | tie to `R_min` (gap 4) or report hand-set | — | **[D] open** |
| 9 | Development prior `A, R, k` | §6.1 | the enrichment count (§4.2 step 1); search survival analysis | no-change gold near new buildings stays no-change (§5) | **[D] open; framing unsearched** |
| 10 | Building prior `u`; blur radius | §6.2 | footprint canopy fraction at the lidar epochs; `coregistration.csv` per SCHEMAS | canopy painted on `ℱ` (§5) | **[D] open; data on hand** |
| 11 | Lidar-referenced `(r_t, f_t)`, `q_loss`, `q_gain`, and `k_½` | every `ℓ_t`; §2.4 | score the twelve tags against the lidar binaries; estimate transitions on `𝒢 ∪ ℱ` | placebo | **not built (§2.3)** |
| 12 | The `r`-convention translation of every [S] above | everything | one reader re-derives §2.1–§2.2 from the papers with `r` = recall | — | **[S] unchecked** |

**Bins and checks, the 3.4c ledger.** Every [S] in this document (§1 convention, §2.1
increments, §2.2 substitutions and worked instance, §2.4 the `γ = 0` analogue, §3.3 the
contrast translation, §5.1 the strata, §7.1 the lattice map, §7.2 the conservative rule)
and every [D] (§2.1 sensitivity, §2.2 the join, §2.3 the verdict, §2.4 `k_½`, §3.1–3.4,
§4, §5.2–5.4, §6, §7.2 `φ`, §8, §11) is unvalidated. The independent check for each is the
row above that names it, run by someone other than this document's author, on real data,
with the kill shown to fire first. A design accepted on numbers it produced about itself is
the failure 3.4c exists to prevent; this document produced none, and should be held to
that.
