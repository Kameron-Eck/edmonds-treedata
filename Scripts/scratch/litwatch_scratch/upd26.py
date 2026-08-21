import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 38 - CORRELATED REFERENCE ERRORS: the structural problem named - IDs 163-164
Search 37 observed that three of this loop's recommendations failed for the same reason -
correlated errors between sources we treat as independent. This iteration searched that directly,
and the problem has a name, a DIRECTION, and a partial fix in the remote-sensing literature.

**THE DIRECTION (ID 163, Radoux & Bogaert 2020, Remote Sensing).**
* reference errors **CORRELATED** with a classifier's errors -> accuracy **OVERESTIMATED**, and
  that classifier is **systematically favoured** over competitors;
* reference errors **conditionally independent** -> accuracy **underestimated**.

Read finding 5 against that. The corrected 2016 model landed beside the NDVI reference
(35.28% vs 37.7%) rather than C-CAP's (29.5%), and after the v042 overlay that reference had
supplied its training labels. **Scoring it against the NDVI reference flatters it by construction** -
not as a suspicion, as a stated property of the estimator. Conversely C-CAP, whose errors are more
nearly independent of ours, should be UNDERSTATING our accuracy. That is the quantitative form of
"the two references bracket truth", and it now has a mechanism rather than an intuition.

**Same paper, a direct steer for P3:** a few HIGH-QUALITY trusted labels beat a larger volume of
questionable reference data. Combined with Search 21 (250 points suffices for calibration, not for
arbitration), the design implication is consistent - spend the human budget on fewer, better,
harder points rather than more easy ones.

**THE MACHINERY (ID 164, Persson et al. 2022, RSE).** Forest-specific estimators that MEASURE
reference error and propagate it into the final figures. STATE's standing caveat - "both refs are
PROXIES; an unknown share of the gap is ref error" - is currently a sentence. This is how it
becomes a term in an equation with a number attached, which the per-crown intervals need if they
are to mean anything.

**A CHEAP INSTRUMENT THIS SUGGESTS, AND WE ALREADY HAVE THE INPUTS.** The epidemiology literature
uses NEGATIVE CONTROLS - places where the answer is known a priori to be null - to detect shared
bias. Failing the test is always cause for concern; passing does not prove absence of bias, but
the asymmetry is still useful. For us the known-negative surfaces are free:
* **open water** (Puget Sound) - no canopy, ever;
* **building footprints** - we already hold `building_footprints/data.json`;
* **paved/impervious** - the `impervious/` layer already exists.

If the model AND the NDVI reference both call canopy on the same known-negative pixels, that is
direct evidence of shared bias, measured with no human labelling at all. The project already has
the instinct - "grass-rejection" is exactly this idea applied to one surface - but it has never
been framed as a negative-control test across several surfaces, nor used to compare SOURCES rather
than models.

**Why this matters more than another method.** Three retractions (Searches 20, 36, 37) traced to
one cause. This search says the cause is recognized, directional, partially correctable, and
detectable with data already on disk. That is a better return than a fourth method would have been.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q43.** Is there a method for estimating accuracy when ALL available references share a common
  cause? This loop has now deflated three of its own recommendations (DG methods, RCA, latent
  class) and the reason was the same each time: correlated errors between sources we treat as
  independent. That recurring failure deserves a search of its own.""",
"""- **Q43.** Is there a method for estimating accuracy when ALL available references share a common
  cause? **ANSWERED (Search 38).** The problem is recognized in remote sensing, has a known
  DIRECTION (correlated -> overestimate and favour that classifier; independent -> underestimate),
  a maximum-entropy correction (ID 163), and propagation machinery (ID 164). It is not solved, but
  it is no longer an unknown unknown.
- **Q44.** What do NEGATIVE CONTROLS say about shared bias between our model and the NDVI
  reference? Known-negative surfaces are free and already on disk - open water, building
  footprints, the impervious layer. If model and NDVI reference both call canopy on the same
  known-negative pixels, that is measured evidence of shared bias with zero human labelling.
  Cheapest remaining diagnostic; the grass-rejection metric is this idea applied to one surface
  only, and never used to compare SOURCES against each other.
- **Q45.** Can Radoux & Bogaert's maximum-entropy correction be applied to our confusion matrices
  retrospectively? If so, every per-year number in `qc_indep_report.csv` could be restated with the
  reference-error bias partly removed, without new data.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art** - fine-res half
   of the two-stream plan, untouched since Phase 1A and now the oldest gap by far.
2. **Geometric vs thematic accuracy for per-object products (Q41).**
3. **Urban forestry / arboriculture reporting standards for canopy change** - defines what "good
   enough" means for the deliverable; never searched in 26 iterations.
4. **Temporal consistency as a training objective.**
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
8. **Instance-norm / whitening for style removal.**
9. **Shadow masking as IGNORE vs removal.**
10. **Maximum-entropy / bias-corrected confusion matrices (Q45)** - follow ID 163's method into
    its implementation.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 26 | 2026-08-18 | Search 38 - correlated reference errors | 163-164 | "
       "Q43 ANSWERED - the structural problem behind 3 retractions is recognized and DIRECTIONAL: "
       "correlated ref errors OVERESTIMATE accuracy and systematically favour that classifier; "
       "independent ones UNDERESTIMATE. So the NDVI ref flatters our model BY CONSTRUCTION and "
       "C-CAP understates it - the bracket now has a mechanism. Max-entropy correction exists "
       "(ID 163). NEGATIVE CONTROLS (water/buildings/impervious - all on disk) would measure "
       "shared bias with zero labelling. New Q44/Q45 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
