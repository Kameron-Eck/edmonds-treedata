# The mathematics of the spatiotemporal consistency layer — inputs to outputs, in order

**Status:** compiled 2026-09-12 from `FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md`
(§1–§18) and `LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md` (§4.12–§4.18). This is a
*narrative*, not a new source: every formula below is carried from those two documents with
its grade, and nothing here is validated (CLAUDE.md 3.4c). Where a section number is given
without a file, it is the framework's.

**How to read the grades.** `[Q]` quoted from a read paper; `[S]` a substitution of our
symbols into a quoted result; `[D]` derived here, unvalidated. A step's grade is the weakest
grade in it. The illustrative numbers (`r = 0.61, f = 0.05, q_loss = 0.02`) are the brief's
C-CAP-referenced placeholders, repeated only where the framework repeats them; none is a
measured lidar-referenced rate.

---

## 0. The picture in one paragraph

Each 2 m cell has a hidden canopy state that persists through time and is correlated with
its neighbours. Each aerial epoch gives a noisy look at that state through a year-specific,
band-specific "eyesight" `(r, f)`. The lidar epochs certify the state on some cells, and
those cells anchor the eyesight and the persistence rates for everyone else. Dated
buildings and developments shift the persistence locally; registration error blurs every
boundary by a known amount. A space-time autologistic model ties the states together, a
smoother with a known erasure radius cleans the field, a change detector runs where the
start state is certified, and the whole thing is scored by an optimism penalty that is
exact under dependence. Every one of those sentences is now a formula with a source.

---

## 1. Inputs — the objects the mathematics consumes

| Symbol | What it is | Home (one fact, one home) |
|---|---|---|
| `i = 1..N` | cells on the 2 m analysis grid, `N ≈ 13.3 M` | `config.ANALYSIS_GRID_EPSG`; brief §2.3 |
| `t = 1..T` | aerial epochs, `T = 12`, 2009–2024; flight dates and effective pixel size per epoch | `qc/imagery_pixelsize_and_date.csv` |
| `Δt` | calendar-year gap between consecutive epochs (uneven) | same table |
| `z_{i,t} ∈ {0,1}` | latent state: not canopy / canopy | — (the unknown) |
| `x_{i,t} ∈ {0,1,⊘}` | hard observation from the mask; `⊘` = IGNORE/nodata | `phase4seg/postproc.py::threshold_and_clean` |
| `p_{i,t} ∈ [0,1] ∪ {⊘}` | soft observation, uint8 `k/254`, `255 = ⊘` | `phase4seg/core.py::step_inference` |
| `b(i) ∈ {0–2, 2–4, 4–8, 8–16, >16 m}` | distance band from cell to the lidar canopy boundary; fixed in `t` | PACC §3a bands (§12.1) |
| lidar 2005, 2016 | canopy height models; the two certified dates | `IMAGERY_FACTS.md` |
| `ℱ, 𝒢, 𝒞, LOSS` | certified populations: FLAT (0 at both lidar dates, eroded), GAIN (0→1), certified canopy (1 at both), LOSS (1→0); thresholds are GAIN's (`h05 < 2 m`, `h16 ≥ 5 m`) | `qc/instruments/harm_change_laundering.py`; §12.2 |
| gold | 1,214 photo-interpreted points ruling on 2016→2024 (1,170 no-change / 42 loss / 2 gain) | brief §2.4 |
| `(median_dx_m, median_dy_m, p95_mag_m)` | inter-epoch registration: per-axis systematic offset (correctable) and a conservative magnitude bound | `phase4/qc/coregistration.csv`; `docs/SCHEMAS.md` |
| building footprints, permits | dated polygons; `d` = distance from a cell to the nearest footprint, `τ` = years since its date | brief §4.2, §6.2 |
| 2020 crown polygons | 222,435 crowns, frozen; the size distribution of real objects | CLAUDE.md §1 |
| `s_t` | the registration shift of epoch `t` relative to the reference | derived from the coregistration table |

Two things about the inputs decide everything downstream. **Only 2020 has hand labels**, so
eyesight in every other year is anchored by lidar, not by labels. **The epochs are unevenly
spaced**, so every rate is per calendar year and every chain step is a power `T^{Δt}`.

---

## 2. Step 1 — what one look is worth: the emission

**Eyesight per epoch and band [convention, §1; band-stratification §12.1 D].**

```
r_{t,b} = P(x = 1 | z = 1, b)    recall
f_{t,b} = P(x = 1 | z = 0, b)    false-positive rate
```

Band-stratified because the pilot measured the edge band swinging by tens of points while
the interior read near-perfect (§12.1); a scalar `f_t` is misspecified exactly where the
detector is most sensitive.

**The evidence increment [S, Itkin eq. 2 and Cor. 1(ii)]:**

```
ℓ_{t,b}(x) =  log( r_{t,b} / f_{t,b} )                  if x = 1
           =  log( (1 − r_{t,b}) / (1 − f_{t,b}) )      if x = 0
           =  0                                          if x = ⊘     [D, §7.3]
```

One number per look, consumed unchanged by the chain (§3), the detector (§7) and the gate
(§4). Its sensitivity is the first hard fact: `∂ℓ/∂f = −1/f` on an observed 1 (§2.1 D), so
any bias in `f` enters the gain evidence at `1/f`.

**Soft observations [D, §2.3].** Bin `p` into `K` levels and estimate the multinomial
`e_t(b_p | z)` on certified cells; `ℓ = log e_t(b_p|1)/e_t(b_p|0)`. `K` by held-out
likelihood. The calibrated-log-odds alternative needs an unmeasurable calibration
(Kumar, Liang & Ma 2019 [Q]) and float logits; it is held.

**The variance cost of imperfect eyesight [S on Chen & Yang 2022 eq. 7]:** any rate
estimated through this emission carries inflation `1/(r − f)²`. The emission gate `f < r`
is what keeps it finite.

---

## 3. Step 2 — where the rates come from: lidar anchors and the yearly root

The rates are not given; they are estimated from cells certified at the lidar dates, with
the anchor's own decay corrected for. All of §12.2 is [D] except the parts re-binned.

**Persistence of a certified state after `k` calendar years [S, Bell & Hinojosa 1977
eqs. 1–2, the 2×2 case].** With per-year rates `(q_g, q_l)`, `λ = 1 − q_g − q_l`,
stationary `π₁ = q_g/(q_g+q_l)`, `π₀ = 1 − π₁`:

```
a_k = P(z_k = 0 | z_0 = 0) = π₀ + π₁ λ^k
c_k = P(z_k = 1 | z_0 = 1) = π₁ + π₀ λ^k
```

**Two populations, two equations, one solve [D].** At an epoch `k` years from the anchor,
the observed mean of `x` on `ℱ` (certified 0) and on `𝒞` (certified 1) is a mixture:

```
m^ℱ_k = a_k f + (1 − a_k) r          m^𝒞_k = (1 − c_k) f + c_k r
f̂ = ( c_k m^ℱ_k − (1 − a_k) m^𝒞_k ) / λ^k
r̂ = ( a_k m^𝒞_k − (1 − c_k) m^ℱ_k ) / λ^k
```

Determinant `λ^k`; variance inflation `1/λ^{2k}` (4× at the anchor's half-life). Between
the two lidar dates use the **bridge weight** `a_k a_{K−k}/a_K ≥ a_k` [D, Markov identity];
after 2016 the one-sided weight. Intervals by block bootstrap over sample blocks, never the
binomial (cells within a block are dependent; §17.5, block size `∝ n^{1/3}` for variance
estimation, Nordman & Lahiri 2004 [Q]).

**The population's own yearly rates from the eleven-year lidar interval [S/Q].** Count
`Q_g = |GAIN ∩ S| / |2005-non-canopy ∩ S|` and `Q_l` likewise on the stratum `S`; then

```
λ = (1 − Q_g − Q_l)^{1/K},   q_g = (1 − λ) Q_g/(Q_g + Q_l),   q_l = (1 − λ) Q_l/(Q_g + Q_l)
```

This is the *yearly root* of the interval transition matrix. It exists and is unique for a
two-state chain **iff `|P| > 0`, equivalently `tr P > 1`, equivalently `p₁₂ + p₂₁ < 1`**
(Kingman 1962 Prop. 2 [Q]) — which is `0 < λ < 1`. For more states: root by
eigendecomposition, unique iff `n` distinct nonzero eigenvalues (Takada 2010 [Q]);
uniqueness of the generator when all `p_ii > ½` (Israel, Rosenthal & Wei 2001 Thm 2 [Q]);
regularisation when the root comes out invalid (Israel §3; Charitos 2008 [Q]).

**Stationarity is an assumption with a test [Q→S].** Anderson & Goodman 1957's
likelihood-ratio test of constant transition probabilities, in Bell & Hinojosa's
non-integer-power form `P^t = HΛ^tH^{−1}`; it needs a third certified date (§14.1). Near
dated developments the framework *asserts* non-stationarity (Step 4) and draws anchors away
from them.

**Bias if the decay is ignored [D]:** `f̂_naive − f = (1 − a_k)(r − f) ≈ k q_g (r − f)`,
upward, entering the detector at `1/f`.

**The kill [D, must fire]:** propagate the full 2005 lidar split by state for eleven years,
solve at the 2016 imagery epoch, compare to the direct rates scored against the 2016 CHM,
which the estimator never saw; it must fail under the placebo `(q_g, q_l) × 10`.

**What Step 2 does not yet handle (row 18, [D]):** the rates are estimated from
misclassified observations, which attenuates persistence; the correction lives in the
multi-state framework of row 17 (round 10).

---

## 4. Step 3 — the chain, then the field: the model that ties looks together

**The per-cell forward chain [S/D, §2].** Transition per calendar year

```
T = [ 1 − q_g   q_g ]
    [ q_l   1 − q_l ],    between epochs: T^{Δt}
```

Missing epochs contribute `ℓ = 0` and the transition still applies (Sinopoli's `γ_t = 0`
update, [S]); memory decays as `λ₂^k` with half-life `k_½ = ln2 / (−ln λ₂)` — at the brief's
placeholder rates about three archives long, so an IGNORE gap "never forgets" (§2.4 D).

**The joint space-time field [Q, Zhu, Huang & Wu 2005 for the undirected form; Zhu, Zheng,
Carroll & Aukema 2008 for the forward form].** The framework's energy (§3.1)

```
E(z) = Σ_{i,t} ψ_u(z_{i,t}) + β Σ_t Σ_{(i,j)∈N_s} ψ_s(z_{i,t}, z_{j,t}) + γ Σ_i Σ_t ψ_τ(z_{i,t}, z_{i,t+1})
```

with `ψ_u(1) − ψ_u(0) = −ℓ`, `ψ_τ = −log T`, is — once the state is observed on an annual
grid — the spatio-temporal autologistic regression model. Its published full conditional
(2005, eq. 2.3; 2008 modifies it "so that the conditional distributions depend only on the
past"):

```
P(Y_{i,t} = 1 | rest) = expit( Σ_k θ_k X_{k,i,t} + θ_{p+1} Σ_{j∼i} (2Y_{j,t} − 1) + θ_{p+2}·(temporal term on Y_{i,t−1}, …, Y_{i,t−S}) )
```

Read `θ_{p+1} = β`, `θ_{p+2} = γ`, and `X_k` = the priors of Step 4 as regressors. Fit by
Monte Carlo maximum likelihood with Fisher-information standard errors, lag order `S` and
neighbourhood order by AIC (2008 [Q]); pseudo-likelihood is "statistically quite
inefficient when spatial and/or temporal dependence is strong" (2008 [Q]) but is the fast
first pass with parametric-bootstrap errors (2005 [Q]). Use the **centered**
parameterisation so the autocovariate fits only residual structure and the regressors keep
the large-scale structure (Caragea & Kaiser 2009; Hughes, Haran & Caragea 2011 [Q]) — here
that is the development prior versus the spatial term competing for the same signal.

**Two baselines are results, not failures [Q, Gräler 2016; Krähenbühl & Koltun 2011]:**
`(0, γ̂)`, `(β̂, 0)` and `(0, 0)` reported beside the fit; if the weight buys no held-out
skill, the chain alone is the layer.

**What is still ours [D].** (i) The state is *hidden* behind Step 1's emission; the
published fit assumes it observed. Rows 1 and 3 are one estimator: EM on the yearly grid,
E-step by Gibbs over `z` given `x`, M-step = the 2008 MCML plus the emission fit on the
certified cells (§18.1). Identifiability comes from the certified populations only.
(ii) Irregular spacing: run on the yearly grid with unobserved years marginalised, or
adopt the continuous-time multi-state form with a generator `Q` and `exp(QΔt)` (rows 17–18,
round 10). (iii) One `β` per resolution stratum (row 21).

---

## 5. Step 4 — the priors, as regressors

**Development (dated, local, directional) [Q for the form].** The multiplicative
transition `q(t) = q · exp(covariate)` is the non-homogeneous hidden Markov model of
Hughes, Guttorp & Charles 1999, with EM; in remote sensing, Liu et al. 2008's "locally
adjusted global transition model … multiplying a pixel-wise probability of change with the
global transition model" [Q]. Our covariate, [D], is a kernel in lag `τ` and distance `d`
from a dated development:

```
q_loss(i, t) = q_l · exp( A · R(d_i) · D_k(τ_{i,t}) )
```

- **The distance profile `R(d)`** by Verburg 2004's enrichment factor `F(d)` = neighbourhood
  share / study-area share, with `R` = the `d` at which `F → 1` [S]; radii in the field:
  0.7 m to a demolished building and 20 m to a driveway (Morgenroth 2017 [Q]), 1.4 m to a
  redeveloped building with removal odds above three times baseline (Guo 2018 [Q]).
- **The lag profile `D_k(τ)`.** No published curve. The two-term family
  `D(τ) = e^{−τ/k₁} + w(1 − e^{−τ/k₂})·1[τ ≤ T_max]` [S] carries the two mechanisms
  fragment ecology describes (immediate mortality decaying; delayed mortality rising —
  D'Angelo 2004, Laurance 2011 [Q]); windows 4–8 y (Hauer), 4–5 y (Guo), 6–7 y (Steenberg
  2017, 806 trees re-measured 2007/08→2014 [Q]); replanting at 2–3 y (Conway 2022). The
  shape-free alternative is the **histogram kernel by EM** of seismology (Ogata 1988's
  epidemic form; Marsan & Lengliné 2008's two-step iteration; Zhuang 2002's attribution
  probabilities [Q]) — with our mapping [D]: parents are dated developments (known), events
  are certified losses, so the EM is a weighted histogram over `(τ, d)` bins. Row 19
  recasts both as a distributed-lag regression under a complementary-log-log link (round 10).
- **Fitting protocol [S, Baddeley & Turner]:** `A` canonical by pseudolikelihood; `R`, `k`
  irregular by profile likelihood; or NHMM-EM. Kill: no-change gold near new buildings
  stays no-change; a null surface on shuffled dates must be flat.

**Buildings and water as hard negative context, blurred by positional error.** A footprint
is not a hard mask; a cell at signed distance `d` from its boundary is inside with
probability

```
π_in(d) = Φ(d / σ),      σ² = σ_reg² + σ_fp²
```

`Φ(d/σ)` is ours [D] (a one-line convolution; the medical-imaging soft labels are
dilation steps, not Gaussian ramps — negative). The composition is the Law of Propagation
of Errors for independent stages (Chrisman 1982 [Q]); the radial law behind it is the
Rayleigh distribution of an isotropic normal displacement (Leung & Yan 1997 eq. 21; 1998
[Q]), so the boundary band at confidence `c` has radius `σ·√(−2 ln(1−c))`, and a fixed
erosion radius is the wrong object — a quantile of `σ` is the right one (Shi 1998's
G-band argument [Q]). `σ_reg` from the coregistration table (median = 1.177σ for a
Rayleigh); `σ_fp` unmeasured; kill against a lidar building reference, not the CHM.

**Registration as a source of false change [Q, Galerne 2011 = Matheron].** For a shift `s`
of a set `Ω` with perimeter `Per(Ω)`:

```
|Ω Δ (Ω + s)| ≈ (2/π) · Per(Ω) · |s|          (direction-averaged; Eq. 2)
|Ω Δ (Ω + s)| ≈ |s| · V_u(Ω)                   (shift along u; Eq. 1, V_u = directional variation)
```

so the false-change fraction on a mask with perimeter density `ρ_P` is `(2/π)·ρ_P·|s|`,
concentrated in the boundary band (Dai & Khorram 1998: false change "mainly distributed
spatially along the edges" [Q]; one-fifth pixel for under 10 % error). The directional form
applies to the per-axis medians (correctable), the averaged form to the residual. A
post-hoc **sliver screen** flags change clumps whose perimeter/area ratio sits at the
one-pixel-strip limit (Salas 2003 [Q]: `4/x` diagonal, `(2/x)(1+1/n)` row/column; our grid
`(2/(s·x))(1+s/n)` [S]). Gradient-weighted compensation of the difference image is a third
tool, recorded not adopted (Stow 1999 [Q]). Folding a registration term into the chain's
emission is row 23 [D].

---

## 6. Step 5 — the smoother, and what it erases

The spatial pass of §3.4 alternates with the temporal pass; whatever smoother is chosen,
its erasure radius must be stated before the `(β, γ)` fit. Three closed forms and one
negative (§16.2):

| smoother | a disc of radius `R` is erased when | contrast-dependent? | source |
|---|---|---|---|
| ROF (TV-L2), weight `α` | `R ≤ 2α/h`, `h` the contrast | yes | Strong & Chan 2003 §3.1 [Q]+[S] |
| TV-L1, weight `λ` | `λ < 2/R` ⇒ `R_erase = 2/λ` | no | Chan & Esedoglu 2005 §3; Duval 2009 Thm 3.6 [Q] |
| TV flow, time `t` | indicator fades as `(1 − λ_Ω t)⁺`, `λ_Ω = Per/|Ω|`; disc extinct at `t = R/2` | no | Bellettini, Caselles & Novaga 2002 [Q] |
| mean-field CRF | no result | — | PRIMARY negative |

Contrast-independence is the argument for TV-L1 or the flow on a probability raster: with
ROF a 60 %-confident removal is erased at a larger physical size than a 95 %-confident one
(§3.3). Related closed forms: Gallagher & Wise 1981 (a median of window `2N+1` erases runs
`≤ N` [Q]); the Potts flip `R < 2β/m` [D, unattributed — nine graph-cut papers filed unread].
**What is missing is the target (row 22):** the smallest real removal to preserve is a
quantile of the 2020 crown sizes; the largest noise blob a quantile of the residual blobs
on `ℱ`; `R_erase` must sit between them or no weight works. Kill: injected discs at the
chosen radius — real-size survive, blob-size erased — on real rasters (§13.2).

---

## 7. Step 6 — detecting change

**Where a chart is well-posed [D, §12.3].** A CUSUM run blind on every cell drifts up on
unchanged canopy at `KL(Bern(r) ‖ Bern(f))` per epoch and fires anyway. It is well-posed
only where the start state is certified: the gain chart on `ℱ`, the loss chart on `𝒞`,
one direction each. Everywhere else the change point is the chain's posterior
`argmax_t P(z_t ≠ z_{t−1} | x_{1..T})` from forward–backward.

**The Bernoulli CUSUM [Q, Ross et al. 2012 §5.1; Reynolds & Stoumbos 1999, 2000].**

```
C_t = max(0, C_{t−1} + x_t − k),   k = r₁/r₂,
r₁ = −log((1−θ₁)/(1−θ₀)),   r₂ = log(θ₁(1−θ₀)/(θ₀(1−θ₁))),   flag when C_t > h
```

with `θ₀ = f_{t,b}`, `θ₁ = r_{t,b}` for gain [S]; per-year rates use the raw-LLR form
`S_t = max(0, S_{t−1} + ℓ_{t,b}(x_t))` [D]. **The threshold `h` is exact, not simulated:**
choose `θ₁` so that `r₂/r₁ = m` is an integer; the statistic lives on multiples of `1/m`;
the chart is a Markov chain on `t = m·h` transient states, moving down one state or up
`m − 1` per observation; the run length follows from the transient matrix (Brook & Evans
1972; Reynolds & Stoumbos 1999 App. A [Q]), with the closed-form first guess
`ANOS(θ₀) ≈ (e^{h r₂} − h r₂ − 1)/|r₂θ₀ − r₁|` (their Eq. 7 [Q]) inverted for `h`. The
Monte Carlo on null sequences is the check that the implementation matches. The variance
inflation `1/(r − f)²` and the placebo shuffle remain the kill.

**Two assumptions the published run length makes that we violate (row 20, [D]):**
independent increments — chart the chain's *residuals* `x_t − p̂(x_t | past)`, not raw
states; and one chart — millions of charts need a false-discovery rule over cells. Round 10.

---

## 8. Step 7 — scoring without fooling ourselves

**The optimism penalty, exact under dependence [Q].** For any fitted rule, true error =
apparent error + `Ω`, `Ω = (2/N) Σ_i cov(μ̂_i, y_i)` (Efron 1986; 2004 Theorem for an
arbitrary joint model — the Gaussian form is the only special case). For binary `y` the
covariance is a *Steinian* per cell (Efron 2004 eqs. 3.19–3.22):

```
cov_(i) = μ_i (1 − μ_i) · [ λ̂_i(y_(i), 1) − λ̂_i(y_(i), 0) ]
```

— refit with cell `i` flipped, difference the prediction, weight by the cell's own
variance. With `μ_i` the **autologistic local conditional** `expit(α_i + Σ β_ij x_j)`
(Besag 1974 eq. 4.8; fitted by coding/pseudolikelihood or MCML, Geyer & Thompson 1992
[Q]) the penalty is exact under spatial dependence with one refit per cell; the correlated
bootstrap (Gibbs draws from the fitted field) is only for intervals (§15.1). There is no
closed-form unbiased-risk identity for correlated binary data (Hudson 1978, Hwang 1982
independence-only; Eldar 2009, Chaux 2008 Gaussian-only — PRIMARY negative), which is
why the per-cell Steinian is the route.

**Leave-out that respects correlation [Q].** Hold out epoch `t` *and every epoch whose
error is correlated with it*, `G(t)`: the extended blind mask ("additionally hide
(neighboring) pixels that contain information about the noise of the active pixel",
Broaddus 2020 [Q]); cross-epoch correlation of errors improves overall change accuracy but
not user's accuracy of change (Burnicki 2007 [Q]). Spatial blocks "at least as many units
as the range of autocorrelation" (Roberts 2017; Valavi 2018 [Q]) — a leakage rule, distinct
from the `n^{1/3}` variance rule.

**The leave-one-epoch-out Brier identity [D, §12.4].** With the debiased pseudo-label
`y_t = (x_t − f_t)/(r_t − f_t)`,

```
E[(p̂_t − z_t)²] = E[(p̂_t − y_t)²] − [ π_t r_t(1−r_t) + (1−π_t) f_t(1−f_t) ] / (r_t − f_t)²
```

— observable loss minus a known noise floor (the Bernoulli analogue of Noise2Self's
Proposition 1 [Q]); `π_t` per stratum is Step 2's persistence weight. Usable on stratum
means, never per cell. Kill: a layer that copies its input must score *below* the floor.

**Model adequacy [Q].** Generalized spatial residuals within concliques are i.i.d. uniform
under the fitted autologistic model (Kaiser, Lahiri & Nordman 2012 Thm 2.1) — the
published form of the synthetic-autologistic kill.

**Two things every reported number needs:** the noise-floor factor `1/(r−f)²` (report
UNDETERMINED below it, CLAUDE.md 3.5), and the honest split (LOSO; ~5 forest sites, not
tile counts).

---

## 9. The order of operations, and the kill at each step

1. **Row 12** — one reader re-derives §2.1–§2.2 with `r` = recall. Everything sits on it.
2. **The populations** — `𝒞` and LOSS rules (11b), one rule each, on the lidar; then
   Step 2 on them with the 2016-reproduction kill.
3. **The emission** (Step 1) — `K` by held-out likelihood on certified cells; placebo
   shuffle must fall.
4. **Correlograms per stratum and band** — spatial and cross-epoch residuals; they set the
   bootstrap model, the block size, and `G(t)`.
5. **The synthetic-autologistic kill / conclique test** (Step 7) — CPU, no lake write.
6. **Row 22 measurement, then the smoother choice** (Step 5) — injected discs.
7. **The joint fit** (Step 3) — `(β, γ)` with the three baselines; hidden-state EM per
   §18.1; per-resolution `β`.
8. **The priors** (Step 4) — kernel by histogram or distributed lag; `σ_fp` and the
   building-reference kill; the self-shift test for the edge band.
9. **The detector** (Step 6) — on the certified populations only; exact `h`; residual
   charts and multiplicity per row 20.

---

## 10. Where the mathematics is still ours

After nine rounds of reading, the derivations that no paper supplies: `Φ(d/σ)` (one
line); the hidden-state EM joining rows 1 and 3; the irregular-interval spacing of the
chain (pending row 17); the earthquake-to-development mapping of the kernel; the
registration covariate in the emission; the Potts erasure constant (nine papers filed,
unread). Everything else above is quoted or substituted. The measurements that close the
rest are in §9; the first three need neither the lake nor a GPU.

---

## 11. Symbol table

| Symbol | Meaning | Defined |
|---|---|---|
| `r_{t,b}, f_{t,b}` | recall, false-positive rate per epoch and band | §1, §12.1 |
| `ℓ_{t,b}(x)` | evidence increment of one observation | §2.1 |
| `q_g, q_l` | per-calendar-year gain and loss rates per population and band | §12.2 |
| `λ = 1 − q_g − q_l` | second eigenvalue; yearly root | §12.2, §15.2 |
| `a_k, c_k` | persistence of a certified 0 / 1 after `k` years | §12.2 |
| `π₀, π₁` | stationary law of the chain | §12.2 |
| `k_½` | information half-life of the chain | §2.4 |
| `(β, γ)` | spatial and temporal coupling; `θ_{p+1}, θ_{p+2}` in Zhu's notation | §3.1, §17.3 |
| `A, R(d), D_k(τ)` | development prior amplitude, distance profile, lag profile | §6.1, §14.6 |
| `π_in(d), σ` | blurred footprint membership; positional error | §14.7 |
| `ρ_P, s, V_u` | perimeter density; registration shift; directional variation | §14.5, §17.1 |
| `R_erase` | disc radius the smoother removes | §16.2 |
| `C_t, S_t, h, m` | CUSUM statistic (Bernoulli / raw-LLR), threshold, integer increment ratio | §2.2, §17.10 |
| `Ω, cov_(i)` | optimism penalty; per-cell Steinian covariance | §5.1, §15.1 |
| `G(t)` | correlation group held out with epoch `t` | §13.1, §16.1 |
| `y_t` | debiased pseudo-label | §12.4 |
| `𝒞, ℱ, 𝒢, LOSS` | certified populations | §1, §12.2 |
