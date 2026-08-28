# What counts as a tree? — one page, for Kam's sign-off

**What this decides.** The written rule that says which pixels of Edmonds are "canopy."
**Why no amount of computing can decide it.** Our two reference datasets disagree on
**15–17% of pixels, every year**, and that disagreement is not scatter — it is one specific
population: **suburban ornamentals, hedgerows and young trees, median height 6.0 m, 88.7% of
them above 3 m** (CHATLOG result 5). Both references are internally consistent. They are
answering *different questions*, and only a human can say which question we are asking.
**What it is worth:** about **6 percentage points of citywide canopy** — more than twice the
2.6-point difference the policy conversation is actually arguing about (WORKPLAN §3).

---

## What you already settled (2026-08-20) — and the consequence

**D2 — do short woody plants count?** You said **yes**: woody vegetation from ~2 m up counts
as canopy, recorded as its own interpreter class so it stays reversible.

That single choice does most of the work. It puts the headline on the **NDVI-reference side**
(true canopy ≈ **.35**) rather than the C-CAP side (≈ **.29**), and it means the 5–15 m trees
the model keeps missing — half of all its misses — **count fully against us** rather than
being defined away (CHATLOG result 5). Nothing below reopens that.

---

## The one real decision left

### A. Where to put the two cutoffs (was "D1")

Our working rule needs a greenness cutoff and a height cutoff. The proposal's own measured
table (canopy as % of the imaged 2016 band):

| | height ≥2 m | ≥3 m | ≥5 m |
|---|---|---|---|
| greenness ≥0.20 | **37.7** | 36.1 | 31.6 |
| greenness ≥0.30 | 33.2 | **32.0** | 28.5 |

Two things that surprised the authors and are worth your attention:

1. **The greenness cutoff matters more than the height cutoff.** Moving greenness from .10
   to .30 costs 10.0 points; moving height from 1 m to 5 m costs 7.4. Every document in this
   project quotes a height and almost none quote a greenness cut — so the more powerful knob
   has been the invisible one.
2. **No cutoff pair reproduces C-CAP's total.** C-CAP counts *stands*, not individual crowns,
   so it excludes isolated trees as a matter of kind. Do not expect a threshold choice to
   reconcile the two references — that assumption is now known to be wrong.

**Recommended: greenness ≥0.30 and height ≥3 m counts as canopy; green things 2–3 m tall are
marked "unsure" rather than judged.** Lands at **32.0%** of the imaged band.

**Why I recommend it despite your D2 decision pointing higher (~.35):** "unsure" is *not* the
same as "not a tree." It is honest abstention on exactly the contested band, and the pipeline
already has that third state. It is also **already what the code does**, so adopting it makes
the existing corrected labels consistent instead of requiring a rebuild.

**But here is the catch nobody has written down, and it is yours to settle:** whether those
"unsure" pixels are **excluded from the total** or **counted as not-canopy** changes the
published number by roughly the size of the whole policy debate. Excluding them (my
recommendation) means we report canopy among pixels we are willing to judge, and say so.

### B. Four smaller rules (I recommend accepting all four as proposed)

- **Partial pixels at crown edges:** a pixel counts as canopy if the crown covers ≥50% of it;
  interpreters judge the pixel centre. *Not a technicality* — the outer 2 m of crowns is 16%
  of canopy area but carries **42% of all our misses**.
- **What is under the crown:** irrelevant — lawn, driveway or roof beneath an overhanging
  limb all count. Standard practice.
- **Binary or fractional:** binary per pixel; city totals published as an **area with a
  confidence interval**, never a bare percentage.
- **What a human records per point:** primary label, plus an *alternate* label where genuinely
  ambiguous, plus a short-tree/shrub flag, plus a duplicate-judged subset. The alternate
  matters — published work shows primary-vs-alternate scoring swings accuracy by 10 points,
  and our current tool throws "unsure" away, which discards precisely the contested pixels.

---

## Two traps, both measured

**The definition must be written BEFORE any human starts interpreting points.** Sloppy
interpretation does not merely add noise — it **biases toward the tree-friendly answer**, and
it collapses our ability to tell the two definitions apart (power falls from .89 to .44 at 10%
interpreter error, CHATLOG result 6). Deciding the rule mid-campaign would quietly favour one
side.

**Two different questions need two different sample sizes, and they must never be conflated**
(WORKPLAN §5): settling *which definition is right* needs about **250 points**; producing a
*publishable canopy percentage* needs about **1,221 points per year**. Same sampling machinery,
five-fold difference in cost.

---

## Does signing this off change the recipe? — NO, if you accept the defaults

Kam's objection, and it is the right one: this project's hardest-won rule is **don't change
the recipe** — recipe changes swing recall 5.6–12.7 points with the sign varying by year
(WORKPLAN "Do not do"). So: what does each choice actually cost operationally?

| choice | if you accept the default | if you pick the alternative |
|---|---|---|
| **A. cutoffs** ≥0.30 / ≥3 m | **NO-OP.** Verified 2026-08-27: `phase4_build_corrected_labels.py:145,193-195` already builds canopy at `NDVI>=0.3 AND height>=3.0 m` and IGNORE at 2–3 m. Signing off *documents* the running system | dropping to ≥2 m rebuilds every corrected-label overlay and **retrains every year that uses one** — a genuine recipe change |
| **A2. unsure excluded** | **NO-OP on the model.** Changes a denominator and a caption in published totals; no label, tile or weight moves | counting unsure as not-canopy is also model-free, but lowers the headline by ~the policy gap |
| **B1. edge ≥50%** | **NO-OP on the model.** Governs how a *human* judges a sample point | — |
| **B2. under-crown** | **NO-OP on the model.** Interpretation only | — |
| **B3. binary + interval** | **NO-OP.** The pipeline is binary end-to-end already (rule 6) | fractional cover would be a full rewrite of the mask convention |
| **B4. interpreter records** | changes `phase4_accuracy_sample.py --step serve` — the **human review tool**, not the model. No retraining | — |

**So the defaults are deliberately the no-op path.** The proposal chose the rule the code
already runs *precisely so that* adopting a definition would not force a rebuild. What you
would be signing is: "write down, and commit to, what the pipeline already does."

The one place the tension is real: your D2 decision (woody ≥2 m counts) taken to its literal
end would drop the height cut to 2 m — which *is* a recipe change. The recommended rule
honours D2's intent differently, by **abstaining** on 2–3 m rather than denying it. That is
the compromise, and it is worth knowing you are making it.

## Checkboxes — "accept all defaults" is a complete answer

- [ ] **A. Cutoffs:** greenness ≥0.30, height ≥3 m; 2–3 m green = unsure *(recommended)*
- [ ] **A2. Unsure pixels are EXCLUDED from the published total**, and we say so in the caption
      *(recommended)* — the alternative is counting them as not-canopy, which lowers the
      headline by roughly the size of the policy gap
- [ ] **B1.** Edge pixels: ≥50% crown coverage, judged at pixel centre *(recommended)*
- [ ] **B2.** Under-crown surface is irrelevant *(recommended)*
- [ ] **B3.** Binary per pixel; totals published as area ± interval *(recommended)*
- [ ] **B4.** Interpreters record primary + alternate + shrub flag + duplicate subset
      *(recommended)*

---

## Stale in the original proposal — corrected here

- Its percentages are over the **2016 imaged band (41.9% of the study area)**, not the city.
  Relative comparisons between cutoff pairs are unaffected (shared denominator), so the
  decision is sound — but **none of these numbers is a citywide canopy figure**.
- Written before this week's work, so it does not know: that **run-to-run luck is ±1 point of
  recall**, that **C-CAP over-paints residential canopy** (Kam's own observation, which means
  our recall is understated and precision flattered in exactly the neighbourhoods this
  definition is about), or that a lidar-dependent rule now has **2005 height data** available
  at 7× the assumed density — which weakens its "cannot be applied before 2016" caveat.
