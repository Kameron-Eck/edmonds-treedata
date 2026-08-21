import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE REFERENCE GAP IS REAL, AND BIGGER ON COMMON GROUND (Q103) *** - 2026-08-19
Compared C-CAP and the NDVI+CHM reference on **identical cells** for the first time: city boundary
AND C-CAP valid AND NDVI-ref valid.

**COVERAGE WITHIN THE CITY**

| | area | share of city |
|---|---|---|
| city | 24.65 km2 | 100.0% |
| C-CAP (city-clipped) | 24.63 km2 | **99.9%** |
| NDVI reference | 16.44 km2 | **66.7%** |
| **common** | **16.44 km2** | **66.7%** |

**THE RESULT**

| footprint | C-CAP | NDVI ref | gap |
|---|---|---|---|
| each on its own | 36.07% | 42.28% | +6.21 pp |
| **COMMON CELLS** | **31.31%** | **42.29%** | **+10.98 pp** |

**The gap is LARGER on common ground, not smaller.** 10.98 pp, against the 8.2 pp that has been
quoted from mismatched footprints.

**WHICH REFUTES MY ITERATION-57 READING, AND BY THE EXACT ERROR I HAD JUST DIAGNOSED.** Three
iterations ago I concluded that citywide C-CAP (36.05%) sits "within 1.7 pp of the NDVI reference's
37.7%", and wrote that "a large part of what we have been calling a definitional dispute may simply
be a footprint mismatch." **That comparison was itself a footprint mismatch** - C-CAP measured
citywide against an NDVI figure measured over two thirds of the city. One iteration after
identifying this failure mode, I committed it.

**Why it fooled me:** C-CAP reads 36.07% citywide but only **31.31%** on the NDVI's footprint. The
Snohomish imagery covers the *less forested* two thirds of Edmonds, so restricting to it drops
C-CAP by ~4.8 pp while leaving the NDVI figure unchanged. The two errors happened to cancel into a
plausible-looking 1.7 pp.

**PER-PIXEL AGREEMENT ON COMMON GROUND**

| | share |
|---|---|
| both canopy | 27.40% |
| both non-canopy | 53.80% |
| C-CAP only | 3.91% |
| **NDVI only** | **14.89%** |
| **disagree** | **18.80%** |

**18.80% disagreement, higher than the 15-17% on record**, and **NDVI-only exceeds C-CAP-only
roughly four to one** - which confirms the "systematically more liberal" finding on properly
matched ground rather than dissolving it.

**WHAT THIS SETTLES.**
* The reference disagreement is **real, not a footprint artefact.** Twenty iterations of reasoning
  about it were not wasted.
* It is **larger than believed**: ~11 pp on canopy fraction, 18.8% per pixel.
* The asymmetry is stark and unexplained: the NDVI reference calls canopy on **3.8x** as much
  disputed ground as C-CAP does.
* And **iteration 49's phenology explanation for that asymmetry survives** - the NDVI reference is
  built from leaf-on Snohomish imagery, C-CAP's season is unknown (Q90, still open). That remains
  the best available account of why one reference sees so much more canopy than the other.

**Method note for anyone reading later:** any two area figures in this project must be checked for
common footprint before they are differenced. This is now the third distinct instance
(iterations 55, 57, 60) where a footprint mismatch produced a wrong conclusion.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q103.** How much of the 15-17% inter-reference disagreement is FOOTPRINT rather than
  definition?""",
"""- **Q103. ANSWERED: none of it - the gap is BIGGER on common ground.** On identical cells C-CAP
  reads 31.31% and the NDVI reference 42.29%, a **+10.98 pp** gap against the 8.2 pp quoted from
  mismatched footprints; per-pixel disagreement is **18.80%**, above the 15-17% on record, with
  NDVI-only exceeding C-CAP-only ~4:1. **My iteration-57 suggestion that footprint explained the
  dispute is withdrawn.** Original question below.
  How much of the 15-17% inter-reference disagreement is FOOTPRINT rather than definition?""")

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q106.** Why does the NDVI reference call canopy on 3.8x as much disputed ground as C-CAP?
  14.89% NDVI-only against 3.91% C-CAP-only on matched cells. Iteration 49's account - the NDVI
  reference is built from leaf-on imagery, C-CAP's season unknown - is the best available and is
  testable the moment Q90 is answered.
- **Q107.** The NDVI reference covers only 66.7% of the city, and the third it misses is the more
  forested part (C-CAP reads 36.07% citywide vs 31.31% on the NDVI footprint). **Any figure derived
  from the NDVI reference is a statement about the less-forested two thirds of Edmonds.** That
  includes the corrected-label workstream, which used it as the label source.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Establish C-CAP's season (Q90)** - now the pivotal open question. It is the only remaining
   test of iteration 49's account for the 3.8:1 asymmetry, which is the largest unexplained effect
   in the reference comparison.
2. **Trace what else used the NDVI reference (Q107)** - it covers the less-forested two thirds of
   the city, and it was the label source for the corrected-label workstream. Anything built on it
   inherits that footprint.
3. **Write down the canopy definition (Q1)** - an 11 pp gap between two references is a definition
   problem before it is a measurement problem.
4. **Acquire county-wide C-CAP 2021 (Q104)** - unblocks citywide change.
5. **What DOES the model key on (Q98)?**
6. **Specificity on the UNCHANGED class (Q66).**
7. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
8. **Geometric vs thematic accuracy for per-object products (Q41).**
9. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
10. **Get the flight dates.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 60 | 2026-08-19 | *** EMPIRICAL - the reference gap is REAL and BIGGER on common ground "
       "(Q103) *** | - | First like-for-like comparison. On identical cells: C-CAP 31.31% vs NDVI "
       "42.29% = +10.98 pp, ABOVE the 8.2 pp quoted from mismatched footprints. Per-pixel "
       "disagreement 18.80% (vs 15-17% on record), NDVI-only 14.89% vs C-CAP-only 3.91% = 3.8:1. "
       "WITHDRAWING iteration 57's suggestion that footprint explained the dispute - and I made "
       "exactly the footprint error I had diagnosed two iterations earlier (C-CAP citywide vs NDVI "
       "on 66.7%). C-CAP reads 36.07% citywide but 31.31% on the NDVI footprint, so the errors "
       "cancelled into a plausible 1.7pp. New Q106/Q107 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
