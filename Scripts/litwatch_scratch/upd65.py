import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE RANGE CLOSES: REAL MISS IS ~88-93%, NOT 35% (Q115) *** - 2026-08-19
Rasterised the per-building `height` attribute and compared it against the lidar CHM on the
on-building pixels. **Canopy overhanging a roof sits above the building height; a miscalled roof
sits at it.**

**CHM height MINUS building height, on-building tall-band pixels (n = 12,271):**

| delta | share |
|---|---|
| below roof by >2 m | 1.80% |
| **AT roof (-2 to +1 m)** | **29.77%** |
| +1 to +3 m | 27.59% |
| +3 to +6 m | 15.37% |
| +6 to +12 m | 13.52% |
| +12 m or more | 11.96% |
| **median delta** | **+2.10 m** |

**Two thirds of it sits above the roof.** On a strict reading (>1 m above = overhang), 68.4% is
genuine overhanging canopy the model missed and 29.8% is a probable C-CAP miscall.

**BUT THE BUILDING HEIGHTS LOOK LOW, AND THAT MATTERS.** Median building height is **4.5 m** with
p90 of only **6.0 m**, and `heightScore` medians 0.55. A two-storey house measures roughly 6-8 m to
the ridge, so these read as eaves-height or underestimates. **If heights are ~2 m low, the +1 to
+3 m band is roof rather than overhang** - so the answer must be given under both readings:

| | real miss | C-CAP error | ambiguous |
|---|---|---|---|
| liberal (>1 m above = overhang) | **93.0%** | 5.6% | 1.5% |
| conservative (>3 m above = overhang) | **88.1%** | 10.4% | 1.5% |

**Phase 2 implied real miss of ~35.4%. Both readings put it at 88-93%.** The conclusion is robust to
the building-height caveat, which is the useful thing about computing it twice.

**WHERE THIS LEAVES THE PROJECT'S CENTRAL NUMBER.** Four iterations ago the shortfall was understood
as roughly one third genuine model failure and two thirds unmeasurable reference disagreement. It is
now roughly **nine tenths genuine model failure**. The chain that got there, each step against an
independent measurement:
1. C-CAP does not over-count suburbs - 0.56% of its canopy is below 2 m by lidar (iteration 62);
2. the "unmeasurable" band is 95% tall (iteration 63);
3. buildings explain 58% of that tall band - a real confound, not a footnote (iteration 64);
4. but two thirds of the on-building pixels sit **above** the roofline, so they are overhanging
   canopy the model missed, not roofs C-CAP miscalled (this iteration).

**THE HONEST IMPLICATION IS UNCOMFORTABLE AND SHOULD BE STATED PLAINLY.** The model misses far more
real canopy than the project has been assuming, and a framing that existed to bound the
unmeasurable portion was instead absorbing genuine under-detection. Honest recall does not change -
the shortfall was always there - but **almost none of it is excusable**.

**And it sharpens what the model is actually bad at:** canopy overhanging buildings and roads. That
is the hard case for an RGB model - dark foliage over dark roof, no ground context - and it is
exactly where C-CAP's impervious-under-canopy class is designed to look. It is also a large share of
urban canopy in a city of single-family lots with street trees.

**Caveats carried forward:** building heights are modelled estimates from a 2025-vintage vector
product compared against a ~2016 lidar CHM, so vintage change and modelling error both blur the
split. The direction is robust; the exact percentages are not.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q115.** Is a tall C-CAP-canopy pixel over a roof an overhanging crown (real miss) or a miscalled
  roof (C-CAP error)?""",
"""- **Q115. ANSWERED: mostly overhang.** Median CHM-minus-building height is **+2.10 m**; 68.4% sits
  above the roofline on a strict reading, 41% on a conservative one that allows for the building
  heights being ~2 m low. Either way the shortfall resolves to **88-93% real miss** against
  Phase 2's implied 35.4%. Original question below.
  Is a tall C-CAP-canopy pixel over a roof an overhanging crown (real miss) or a miscalled roof?""")

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q116.** Is canopy OVERHANGING BUILDINGS AND ROADS the model's dominant failure mode? The
  evidence now points there: the misses concentrate on tall vegetation over impervious surfaces,
  which is the hard RGB case (dark foliage over dark roof, no ground context). If so it is
  addressable - it is a specific, nameable weakness rather than a diffuse deficit - and it would
  reframe the annotation plan around overhang cases rather than suburban stands generally.
- **Q117.** Are the building heights usable at all? Median 4.5 m and p90 6.0 m look like eaves
  rather than ridge heights, with a modelled `heightScore` of 0.55. If a better height source exists
  (or the CHM itself over building footprints), the 88-93% range would tighten. Low priority - the
  conclusion is already robust to it.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Test whether overhang-over-impervious is the dominant failure mode (Q116)** - the misses now
   look concentrated there. Naming a specific weakness is worth more than another diffuse metric,
   and it would redirect the annotation plan.
2. **Characterise the tall-but-not-green pixels (Q114)** - shadow, bare deciduous, or dark foliage?
3. **Write down the canopy definition (Q1)** - does 2-5 m green vegetation count?
4. **Test whether scrub reconciles the references (Q112).**
5. **Trace what else used the NDVI reference (Q107).**
6. **What DOES the model key on (Q98)?**
7. **Specificity on the UNCHANGED class (Q66).**
8. **Recover C-CAP's source imagery date (Q109).**
9. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
10. **Simplify the canopy_def reporting (Q110).**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 65 | 2026-08-19 | *** EMPIRICAL - the range CLOSES: real miss is 88-93%, not 35% (Q115) "
       "*** | - | Rasterised per-building heights vs the CHM. Median delta +2.10 m; 68.4% of "
       "on-building tall-band pixels sit ABOVE the roofline = overhanging canopy the model missed, "
       "not roofs C-CAP miscalled. Building heights look ~2 m low (median 4.5 m, p90 6.0 m, "
       "heightScore 0.55), so computed both readings: real miss 93.0% liberal / 88.1% conservative. "
       "PHASE 2 IMPLIED 35.4%. Conclusion robust to the height caveat. FOUR-STEP CHAIN complete "
       "(it.62-65), each against an independent measurement. Sharpens the failure mode: canopy "
       "OVERHANGING BUILDINGS AND ROADS - the hard RGB case (Q116) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
