import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 48 - INTERVAL CENSORING + MISCLASSIFICATION - IDs 183-184
**THE TWO WORKSTREAMS TURN OUT TO BE ONE.**

Search 47 established that our data is interval-censored. This search finds the version that also
accounts for the observation being made by an IMPERFECT detector - and in doing so it connects the
honest-measurement effort to the change product in a way nobody has articulated.

**The model (IDs 183, 184).** An event known only to fall within an interval, detected by a test
with imperfect **sensitivity** and **specificity**, where those accuracy parameters enter the
LIKELIHOOD as explicit corrections. Deng et al. 2026 (ID 184, *Annals of Applied Statistics*) adds
a **terminal** event - crown removal is terminal in exactly that sense, a felled tree does not
return - fits a Cox-type semiparametric model, and handles censoring and misclassification together
by NPMLE with EM.

**Why this reframes the project.** The measurement workstream has been treated as quality control -
producing caveats to attach to numbers. It is not. It produces **the parameters the change
estimator consumes**:

| what P1-P4 measure | where it enters the change product |
|---|---|
| per-year recall (sensitivity) | likelihood correction for missed losses |
| per-year precision -> specificity | likelihood correction for false losses |
| per-band recall (the height curve) | covariate-conditional sensitivity |
| reference disagreement bounds | uncertainty on those parameters |

**Without those numbers the per-crown change product cannot be de-biased. With them, it can.**
That is a much stronger justification for the honest-measurement work than "we should be rigorous",
and it means the accuracy figures are not a caveat section - they are inputs.

**And covariates enter properly.** ID 184 accepts covariates, so height band, land-use context and
radiometric cluster become RISK FACTORS in the model rather than post-hoc stratifications bolted on
afterwards. Our height curve (recall .16 to .93) would enter as covariate-conditional sensitivity,
which is exactly the shape it has.

**The obvious objection, stated honestly.** These are biostatistics methods on cohorts of hundreds
to thousands of subjects with a handful of visits. We have ~222,000 crowns and up to 18 observation
epochs, which is a different computational regime - NPMLE with EM over 222k subjects is not
obviously tractable, and nothing found addresses that scale. It may need aggregation to strata or a
sampled cohort. Also, our sensitivity is not merely imperfect but STRUCTURED (height-dependent,
context-dependent, era-dependent), which is more than the two-parameter sensitivity/specificity
these methods assume - though the covariate machinery of ID 184 is the natural place to put it.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q63.** Does interval-censored-with-misclassification estimation scale to ~222,000 crowns?
  The methods are biostatistical, developed for cohorts of hundreds to thousands with a few visits;
  NPMLE with EM at our scale is untested and nothing found addresses it. Fallbacks: aggregate to
  strata, or fit on a sampled cohort and apply the estimated survival curves population-wide.
- **Q64.** Our sensitivity is STRUCTURED, not scalar - it varies with height band, land-use context
  and era. The misclassification models assume a sensitivity/specificity pair. Does covariate-
  conditional sensitivity (ID 184's covariate machinery) express our height curve correctly, or does
  it need a more general measurement-error model? This is where the height curve stops being a
  diagnostic finding and becomes a model term.
- **Q65.** Which per-year accuracy figures would actually be USED? If sensitivity/specificity are
  inputs to the change estimator, then their uncertainty propagates into every crown's interval -
  which makes the reference-disagreement problem (15-17%) a direct source of uncertainty in the
  deliverable rather than a separate caveat. That coupling has never been traced.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Measurement-error models with STRUCTURED (covariate-dependent) misclassification (Q64)** -
   our sensitivity varies by height, context and era, which is more than a sensitivity/specificity
   pair. This is where the height curve becomes a model term instead of a finding.
2. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred
   seven times.
4. **Canopy AREA turnover vs tree-COUNT mortality** - the Q50 counterweight.
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Ladder-side-tuning and cheap foundation-model adaptation.**
10. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 36 | 2026-08-18 | Search 48 - interval censoring + misclassification | 183-184 | "
       "THE TWO WORKSTREAMS ARE ONE. Interval-censored survival with imperfect sensitivity/"
       "specificity puts our MEASURED accuracy directly into the change likelihood as corrections - "
       "so P1-P4 do not produce caveats, they produce INPUTS the change product needs to be "
       "de-biased. Deng 2026 (AoAS) adds a TERMINAL event (crown removal is terminal) and accepts "
       "COVARIATES, so the height curve becomes covariate-conditional sensitivity. Scale to 222k "
       "crowns is untested (Q63); structured sensitivity may exceed the model (Q64) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
