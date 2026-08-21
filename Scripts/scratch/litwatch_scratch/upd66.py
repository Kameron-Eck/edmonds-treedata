import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - RECALL HALVES ON CANOPY OVER IMPERVIOUS (Q116) *** - 2026-08-19
Split C-CAP canopy by what lies beneath - buildings and the impervious layer versus pervious
ground - and measured the model's recall on each.

| year | recall OVER IMPERVIOUS | recall over pervious | gap |
|---|---|---|---|
| 2016 | **0.3183** | 0.6922 | **-0.374** |
| 2013 | **0.3383** | 0.7683 | **-0.430** |
| 2017 | **0.4570** | 0.8279 | **-0.371** |

**The model's recall roughly halves on canopy overhanging buildings and pavement**, and the effect
is consistent across three years spanning three different sensors and eras - a gap of 0.37 to 0.43
every time. **Canopy over impervious is 17.2% of all C-CAP canopy**, so this is not a corner case.

**THIS IS THE CLEANEST FAILURE MODE THE LOOP HAS FOUND, AND IT IS MORE STABLE THAN THE HEADLINE
METRIC.** Overall honest recall wanders between .50 and .78 across years with no clear driver
(finding 3). The impervious gap sits at 0.37-0.43 in every year tested. **A quantity that stable
across sensor, era and resolution is describing something real about the model rather than about
the imagery.**

**WHAT IT WOULD BE WORTH FIXING.** If the model achieved its pervious-ground recall on
over-impervious canopy too, overall recall on 2016 would rise by
`0.172 x (0.6922 - 0.3183) = 0.064` - **about 6.4 points, roughly a fifth of the entire
shortfall**, from a single named weakness.

**AND IT MAY UNIFY TWO FINDINGS.** Canopy over impervious is street trees and yard trees beside
houses - which are also disproportionately the SHORT, suburban crowns that the recall-by-height
staircase is built on, and the ones in STATE's 8/8 missed suburban stands. **The height staircase
and the overhang deficit may be the same phenomenon seen two ways.** That is directly testable:
recompute recall-by-height WITHIN the pervious-only subset. If the staircase flattens there, height
was a proxy for overhang all along; if it survives, they are independent deficits and both need
fixing.

**WHY THE MODEL WOULD FAIL HERE, MECHANISTICALLY.** Dark foliage over a dark roof or asphalt gives
little contrast at the crown edge, no surrounding ground texture to anchor the segmentation, and -
critically - the training labels come from a 2020 mask that inherits the same weakness. C-CAP finds
these pixels because it has a stereo DSM and an explicit impervious-under-canopy class; our model
has RGB and, for most years, no height channel at all.

**Which suggests the fix is structural rather than more data:** the CHM is exactly the signal that
separates a crown over a roof from the roof itself, and it is already built. The aux-height
experiments (v045/v046) were aimed at grass rejection; **this is a second and arguably better
reason to give the model height.**
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q116.** Is canopy OVERHANGING BUILDINGS AND ROADS the model's dominant failure mode?""",
"""- **Q116. ANSWERED: YES, AND IT IS STABLE.** Recall over impervious is 0.32-0.46 against 0.69-0.83
  over pervious ground - a gap of **0.37 to 0.43 in every year tested**, across three sensors and
  eras. Canopy over impervious is 17.2% of all C-CAP canopy, and closing the gap would lift overall
  recall by ~6.4 points, about a fifth of the shortfall. Original question below.
  Is canopy OVERHANGING BUILDINGS AND ROADS the model's dominant failure mode?
- **Q118. [HIGH VALUE, ONE RUN]** Is the recall-by-height staircase just the overhang deficit in
  disguise? Canopy over impervious is disproportionately short suburban crowns. Recompute
  recall-by-height **within the pervious-only subset**: if the staircase flattens, height was a
  proxy for overhang; if it survives, they are independent deficits. This would either unify or
  separate the project's two central findings.
- **Q119.** Would a height channel fix the overhang deficit? The CHM is precisely the signal that
  distinguishes a crown over a roof from the roof itself, and it exists. The v045/v046 aux-height
  work targeted grass rejection; **overhang is a second and possibly stronger motivation** - and it
  predicts the benefit should concentrate on the over-impervious subset, which is directly
  measurable.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Recall-by-height within the pervious-only subset (Q118)** - unifies or separates the project's
   two central findings. One run on data already loaded, and it changes what the fix should be.
2. **Does the CHM-input model close the overhang gap (Q119)?** `prob_2016_corrected` and the
   aux-height variants exist; measuring their over-impervious recall against the baseline's 0.3183
   tests the structural fix directly.
3. **Characterise the tall-but-not-green pixels (Q114)** - shadow, bare deciduous, or dark foliage?
4. **Write down the canopy definition (Q1).**
5. **Test whether scrub reconciles the references (Q112).**
6. **Trace what else used the NDVI reference (Q107).**
7. **What DOES the model key on (Q98)?**
8. **Specificity on the UNCHANGED class (Q66).**
9. **Recover C-CAP's source imagery date (Q109).**
10. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 66 | 2026-08-19 | *** EMPIRICAL - recall HALVES on canopy over impervious (Q116) *** | - "
       "| 2016: 0.3183 over impervious vs 0.6922 over pervious. 2013: 0.3383 vs 0.7683. 2017: 0.4570 "
       "vs 0.8279. GAP OF 0.37-0.43 IN EVERY YEAR, across three sensors and eras - far more STABLE "
       "than overall recall, which wanders .50-.78. Canopy over impervious is 17.2% of all C-CAP "
       "canopy; closing the gap would lift overall recall ~6.4 points = a fifth of the shortfall. "
       "Mechanism: dark foliage over dark roof, no ground texture, and the 2020 labels share the "
       "weakness. MAY UNIFY WITH THE HEIGHT STAIRCASE (Q118) - overhang canopy is disproportionately "
       "short suburban crowns. Suggests a STRUCTURAL fix: give the model the CHM (Q119) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
