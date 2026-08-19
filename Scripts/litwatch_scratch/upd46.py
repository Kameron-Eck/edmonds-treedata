import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - 2020 SHOWS THE LEAF-OFF SIGNATURE (Q84) *** - 2026-08-19 - `phase4_qc_leafoff.py`
Iteration 45 found the published spec and inferred leaf-off. This tests it in the pixels, with no
species map and no acquisition metadata.

**THE TEST.** Take pixels the 2020 canopy mask calls CANOPY and look at the greenness distribution
inside them. Leaf-on canopy is green: unimodal, positive. Leaf-off canopy is mixed - conifers stay
green, deciduous crowns are bare - so a substantial LOW/NEGATIVE mode appears. The low-greenness
fraction is the signature; NAIP (leaf-on **by specification**) calibrates it.

**RESULT - same canopy mask, same city:**

| | 2020 CoE | 2022n NAIP (**leaf-on by spec**) |
|---|---|---|
| median GRVI over canopy | **+0.0330** | **+0.1226** |
| p25 | +0.0127 | +0.0946 |
| **low-greenness fraction (<0.02)** | **33.02%** | **5.23%** |
| negative fraction | 13.06% | 4.11% |

**A third of everything the model calls canopy in 2020 is not green.** In NAIP it is 5%.

**AND THE OBVIOUS CONFOUND IS ELIMINATED.** The two differ in GSD (7.5 cm vs 60 cm), and coarse
pixels average bare branches with green neighbours, which would inflate the difference. So we
degraded 2020 to 60 cm and recomputed on the same windows:

| 2020 CoE | n | median | low<0.02 | negative |
|---|---|---|---|---|
| native 7.5 cm | 1,046,712 | +0.0330 | 33.02% | 13.06% |
| **degraded to 60 cm** | 16,358 | **+0.0331** | **33.02%** | 13.29% |

**Identical.** Resolution explains none of it. At matched 60 cm, 2020 canopy is a quarter as green
as NAIP canopy and has six times the low-greenness fraction.

**WHAT REMAINS AS AN ALTERNATIVE.** Sensor colour balance - NAIP has different radiometry from a
consortium ortho, and nothing here rules that out. But a **4x difference in median canopy greenness**
is large for colour balance alone, and three independent lines now agree:
1. the published consortium specification (leaf-off, March-May, snow- and smoke-free);
2. the scene-wide greenness ranking (both NAIP years top-5 of 17; the bottom six all consortium);
3. this canopy-conditional test, with resolution controlled.

**Strong evidence, still not proof.** Only the flight date is proof, and it remains recoverable.

**AND THE TEST IS BIASED AGAINST ITSELF.** The canopy mask used to select pixels is a model output
carrying the very blind spot under investigation - if it already omits bare deciduous crowns, the
33% is an UNDER-estimate. A positive result under that bias is stronger than it looks.

**Honest limits:** few windows met the 15% canopy threshold (2 of 16 for 2020, 1 of 16 for NAIP),
so this is indicative rather than a probability sample; thin shadow is not excluded, and leaf-off
flights have low sun angle, so shadow and phenology are correlated (Search 31) and the low mode is
not purely deciduous.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q84. [LIKELY THE MOST IMPORTANT OPEN QUESTION IN THE PROJECT]** Was the 2020 City of Edmonds
  acquisition flown LEAF-OFF?""",
"""- **Q84. [STRONG EVIDENCE YES - iteration 46]** 2020 canopy has a **33.0% low-greenness fraction**
  against NAIP's 5.2%, and a median GRVI a quarter of NAIP's, **with resolution controlled**
  (degrading 2020 to 60 cm changes the numbers not at all). Remaining alternative is sensor colour
  balance; remaining proof is the flight date. Original question below.
  Was the 2020 City of Edmonds acquisition flown LEAF-OFF?""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Rule out sensor colour balance (the last alternative to leaf-off).** Run `phase4_qc_leafoff.py`
   on 2017/2022/2024 CoE (same sensor family as 2020) and on 2019n NAIP. If all consortium years
   show ~30% low-greenness and both NAIP years ~5%, colour balance cannot explain it - the split
   follows the SPEC, not the vendor. One command each, rasters on disk.
2. **Get the flight date (Q84 proof).** Photo-centre index, ortho metadata, or ask the City.
3. **Recall-by-height on a LEAF-ON year vs a leaf-off year (Q86)** - tests whether the height curve
   is partly a deciduous-fraction curve. 2019n/2022n already have scored prob rasters.
4. **Season-label all 18 acquisitions (Q85).**
5. **Specificity on the UNCHANGED class (Q66).**
6. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
7. **Geometric vs thematic accuracy for per-object products (Q41).**
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
10. **Broadleaf / deciduous-specific crown segmentation** - urgent if leaf-off confirms.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 46 | 2026-08-19 | *** EMPIRICAL - 2020 shows the LEAF-OFF signature (Q84) *** | - | "
       "Same canopy mask: 2020 CoE median GRVI +0.0330 with 33.02% of canopy pixels LOW-GREENNESS; "
       "NAIP 2022n (leaf-on BY SPEC) median +0.1226 with 5.23%. A THIRD of what the model calls "
       "canopy in 2020 is not green. GSD CONFOUND ELIMINATED: degrading 2020 from 7.5cm to 60cm "
       "changes nothing (+0.0331, 33.02%). Three independent lines now agree - published spec, "
       "scene-wide greenness ranking, canopy-conditional test. Remaining alternative: sensor colour "
       "balance (testable, queue #1). Remaining proof: the flight date. NOTE the test is BIASED "
       "AGAINST itself - the mask omits bare crowns, so 33% is an under-estimate |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
