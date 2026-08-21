import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 40 - WHAT PRECISION DOES A CANOPY NUMBER ACTUALLY NEED? - IDs 167-168
Twenty-eight iterations optimizing a canopy-change product without once asking what the number is
for. This should have been iteration 1.

**THE CAUTIONARY TALE IS 15 MILES AWAY (ID 167, Richardson & Moskal 2014, UF&UG).** Assessed
SEATTLE canopy cover varies substantially across studies **for identical dates** - multiple
conflicting published values for 1972, 2002 and 2009. Methodological difference, not real canopy
change, produced apparent trends that a city then acted on. Same region, same imagery ecosystem,
same institutional pressures. This is the failure mode our honest-measurement workstream exists to
avoid, and it is citable directly in any Edmonds-facing write-up.

**AND THE SOURCE ALONE MOVES THE ANSWER (ID 168, Ucar et al. 2016).** Tallahassee canopy cover
estimated at 44.5-45.1% from NAIP versus 48.6-49.1% from Google Earth - about **four percentage
points from imagery choice, with nothing changing on the ground.** Same order as our own
inter-reference disagreement, which reframes that disagreement as normal rather than pathological.

**THE COMPARISON THAT MATTERS.** Edmonds policy context: a 32.4% baseline and a 35%-by-2036 goal -
a **2.6 percentage point** effect over a decade. Set that against every uncertainty we have measured
or read:

| source of uncertainty | magnitude | vs the 2.6 pp effect |
|---|---|---|
| our 250-point sample (95% half-width) | 5.9 pp | **larger** |
| i-Tree at >500 points (SE 1.7% -> 95%) | 3.3 pp | **larger** |
| imagery source alone (NAIP vs Google Earth) | 4.0 pp | **larger** |
| our two references disagree | 8.2 pp | **larger** |

**Every single source of measurement uncertainty is larger than the effect the policy is about.**
That is the "good enough" answer the loop has been missing, and it is uncomfortable.

**THE IMPORTANT CAVEAT, WHICH SHARPENS RATHER THAN SOFTENS THE POINT.** A CHANGE between two years
can be estimated far more precisely than either absolute level, because systematic bias shared by
both measurements partly cancels - paired estimation on the same ground with the same instrument.
So the table above is not fatal in principle. **But cancellation requires the instrument to be
constant across years, and ours is the opposite**: four agencies, multiple contractors, 7.5-60 cm
GSD, unknown flight dates, and radiometric clusters that do not follow agency (iteration 11).
The one design that would rescue the precision is the one our archive most conspicuously violates.

**What this implies for the project, stated plainly:**
1. Absolute per-year canopy percentages are the WEAKEST product we could ship - they inherit every
   source-driven offset in the table.
2. **Paired change on stable ground with a matched instrument** is the strongest - which is an
   argument for prioritizing year-pairs from the same radiometric cluster over the full 18-year
   series, and for the 2017 matched pair (iteration 13) as the calibration anchor.
3. Any number we publish needs its method and interval attached, or it becomes another row in
   Seattle's table of conflicting values for the same date.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q48.** Can we deliver a change number precise enough to matter? Every measured uncertainty
  (5.9 / 3.3 / 4.0 / 8.2 pp) exceeds the ~2.6 pp effect a decadal canopy goal implies. Paired
  estimation cancels shared bias and could rescue this - but only where the instrument is constant,
  which our four-agency, multi-contractor, 7.5-60 cm archive violates. **This is the project's
  central feasibility question and it has never been posed.**
- **Q49.** Should the deliverable lead with PAIRED CHANGE between matched-instrument year pairs
  rather than an 18-year series of absolute percentages? The former is defensible at achievable
  precision; the latter inherits every source-driven offset. That is a scope decision for Kam, not
  a technical one, and it depends on Q19 (which years share an instrument).

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Paired / difference estimation for canopy change** - forced to the top by Search 40. How is
   change estimated when absolute levels are unreliable but the pair shares bias? Includes
   before-after designs, matched-pair sampling, and change-specific accuracy assessment.
2. **Training-free / annotation-free crown segmentation** - annotation is our binding constraint.
3. **Geometric vs thematic accuracy for per-object products (Q41).**
4. **Temporal consistency as a training objective.**
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
8. **Instance-norm / whitening for style removal.**
9. **Shadow masking as IGNORE vs removal.**
10. **Ladder-side-tuning and cheap foundation-model adaptation.**

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 28 | 2026-08-18 | Search 40 - what precision does a canopy number need? | 167-168 | "
       "SHOULD HAVE BEEN ITERATION 1. Seattle (15 mi away) has MULTIPLE CONFLICTING published canopy "
       "values for IDENTICAL dates - method, not trees. Imagery source alone moves the answer 4 pp. "
       "AND: every uncertainty we have (5.9/3.3/4.0/8.2 pp) EXCEEDS the ~2.6 pp effect a decadal "
       "canopy goal implies. Paired change could rescue it, but only with a CONSTANT instrument - "
       "which our archive violates. New Q48/Q49: the project's central feasibility question |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
