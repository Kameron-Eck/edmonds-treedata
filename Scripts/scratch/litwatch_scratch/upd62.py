import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE SUBURBAN OVER-COUNT HYPOTHESIS IS REFUTED (Q108) *** - 2026-08-19
Tested STATE's load-bearing claim that C-CAP inflates canopy by counting lawns and roofs between
yard trees. C-CAP's own height came from a photogrammetric stereo DSM; our CHM is 3DEP lidar -
**independent height sources**, so this is a fair test. 95% of the city has CHM coverage.

**HEIGHT DISTRIBUTION OF PIXELS EACH REFERENCE CALLS CANOPY**

| CHM height | C-CAP | NDVI ref |
|---|---|---|
| 0-1 m | 0.16% | 0.01% |
| 1-2 m | 0.40% | 0.07% |
| 2-3 m | 1.23% | **5.07%** |
| 3-5 m | 6.01% | **14.01%** |
| 5-10 m | 17.10% | 22.94% |
| 10-20 m | 25.19% | 23.47% |
| **20+ m** | **49.91%** | 34.43% |

**C-CAP canopy below 2 m: 0.56%.** If C-CAP were counting lawn and roof between yard trees, a large
share of its canopy would sit at low lidar height. **It does not - 99.44% of C-CAP canopy is above
2 m by an independent height source.** The hypothesis is refuted.

**AND THE TRUTH IS THE OPPOSITE SHAPE.** C-CAP is **conservative and skewed tall**: 75% of its
canopy is above 10 m, half above 20 m. The NDVI reference is the **liberal** one, with 19.08% of its
canopy in the 2-5 m band against C-CAP's 7.24%.

**SO THE REFERENCE DISPUTE IS ABOUT SHORT VEGETATION, NOT SUBURBAN LAWNS.** That is a specific,
checkable claim replacing a vague one, and it follows from how each reference is built:
* the **NDVI reference** counts anything with NDVI >= 0.2 AND height >= 2 m - which sweeps in tall
  shrubs, hedges and blackberry thickets;
* **C-CAP** separates **Scrub/Shrub** as its own class (3.47% of the city) and reserves canopy for
  "Upland Tree (Forest)".

Adding C-CAP's scrub to its canopy closes roughly a third of the 10.98 pp gap (31.31% + 3.47% =
34.8% against 42.29%), so short vegetation is a large part of the disagreement but not all of it.

**THIS REFRAMES A CENTRAL PROJECT FINDING.** STATE records that 8/8 inspected missed stands were
suburban, and attributes the gap to C-CAP "definitionally over-counting leafy suburbs (NOT a model
error)". **The visual grounding was right; the attribution was wrong.** Those stands are suburban,
and C-CAP is calling canopy there on ground that independent lidar says is genuinely over 2 m tall.
**They are real misses, not reference error.** The comfortable half of the "the gap splits into
reference error plus real under-detection" reading loses its support.

**What still stands from iteration 61.** C-CAP being tall-skewed is equally consistent with (a) its
definition excluding short vegetation, and (b) its stereo DSM under-recovering height on short or
bare-deciduous crowns. This test cannot separate those - both produce the same signature - so Q109
survives intact.

**Two claims down in two iterations.** Iteration 61 showed C-CAP deliberately includes
impervious-under-canopy overhang; this shows its canopy is essentially all genuinely tall. The
"C-CAP over-counts suburbs" story was wrong in both of its mechanisms.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q108.** Does STATE's suburban over-count hypothesis survive?""",
"""- **Q108. ANSWERED: NO, REFUTED.** Only **0.56%** of C-CAP canopy sits below 2 m by independent
  lidar - it is not counting lawns or roofs. C-CAP is the CONSERVATIVE reference, skewed tall (50%
  above 20 m); the NDVI reference is the liberal one, with 19.08% of its canopy at 2-5 m against
  C-CAP's 7.24%. **The dispute is about SHORT VEGETATION, not suburban lawns.** Consequence: STATE's
  8/8 suburban missed stands are **real misses, not reference error**. Original question below.
  Does STATE's suburban over-count hypothesis survive?""")

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q111.** If the missed suburban stands are REAL misses rather than reference error, the
  "unmeasurable band" framing of Phase 2 needs revisiting. STATE splits the ~30% gap into real miss
  plus unmeasurable disagreement, with 64.6% landing in the disagreement band. If C-CAP is
  conservative and tall-skewed rather than over-counting, more of that band is real miss than
  assumed - and the honest recall figure is worse, not better.
- **Q112.** Does adding C-CAP Scrub/Shrub to the canopy definition reconcile the two references?
  It closes about a third of the 10.98 pp gap. Worth computing properly: the `forest_wetland_scrub`
  rows already exist in the QC CSV, so the comparison can be made without new processing.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Revisit the "unmeasurable band" split (Q111)** - Phase 2 assigns 64.6% of the miss to
   reference disagreement on the assumption C-CAP over-counts. That assumption is now refuted, and
   the correction moves the honest recall figure DOWN. Load-bearing and uncomfortable.
2. **Test whether scrub reconciles the references (Q112)** - the `forest_wetland_scrub` rows
   already exist; no new processing needed.
3. **Write down the canopy definition (Q1)** - now sharply posed: does 2-5 m green vegetation count
   as canopy? The two references answer differently and that is most of the dispute.
4. **Recover C-CAP's source imagery date (Q109)** - still the route to separating definition from
   stereo-DSM failure.
5. **Trace what else used the NDVI reference (Q107).**
6. **What DOES the model key on (Q98)?**
7. **Specificity on the UNCHANGED class (Q66).**
8. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
9. **Simplify the canopy_def reporting (Q110).**
10. **Geometric vs thematic accuracy for per-object products (Q41).**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 62 | 2026-08-19 | *** EMPIRICAL - the suburban over-count hypothesis is REFUTED (Q108) "
       "*** | - | Tested against INDEPENDENT lidar height (C-CAP uses a stereo DSM, ours is 3DEP). "
       "Only 0.56% of C-CAP canopy is below 2 m - it is NOT counting lawns or roofs. C-CAP is the "
       "CONSERVATIVE reference, 50% of its canopy above 20 m; the NDVI ref is LIBERAL, 19.08% at "
       "2-5 m vs C-CAP's 7.24%. THE DISPUTE IS ABOUT SHORT VEGETATION, not suburban lawns. "
       "REFRAMES A CENTRAL FINDING: STATE's 8/8 suburban missed stands are REAL MISSES, not "
       "reference error - so more of Phase 2's 'unmeasurable band' is real miss than assumed, and "
       "honest recall is WORSE not better (Q111) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
