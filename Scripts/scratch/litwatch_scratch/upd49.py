import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE SEASON MAP, AND WHY THE NDVI REFERENCE IS "MORE LIBERAL" *** - 2026-08-19
Season-scored the Snohomish acquisitions, whose spec was unknown and which build our NDVI
reference. **Both are clearly LEAF-ON.** The archive now splits cleanly:

| year | source | median GRVI over canopy | low-greenness | read |
|---|---|---|---|---|
| 2019n | NAIP | +0.2745 | 0.00% | **LEAF-ON** |
| 2016 | Snohomish | +0.2079 | 1.95% | **LEAF-ON** |
| 2021s | Snohomish | +0.1623 | 0.58% | **LEAF-ON** |
| 2022n | NAIP | +0.1226 | 5.23% | **LEAF-ON** |
| 2022 | City of Edmonds | +0.0485 | 16.42% | leaf-off |
| 2020 | City of Edmonds | +0.0330 | **33.02%** | **LEAF-OFF** |

**Bimodal and unambiguous:** four acquisitions at 0-5% non-green canopy, two at 16-33%. Nothing in
between.

**AND THIS EXPLAINS A STANDING FINDING.** STATE records that the two references disagree on 15-17%
of pixels and that **the NDVI reference is systematically MORE LIBERAL** than C-CAP
(`ndvi_only` 10-14% vs `ccap_only` 1.9-5.7%). That has been treated as an unexplained property of
the products. It now has a physical cause:

* the **NDVI+CHM reference is built from LEAF-ON imagery** (2016 and 2021s Snohomish);
* the **model is trained on LEAF-OFF labels** (2020 City of Edmonds);
* so the reference sees deciduous canopy the model was never taught to see.

**The reference is not "more liberal". It is looking at trees that have leaves on them while the
model was taught on trees that did not.** That reframes finding 3 from a products dispute into a
phenology mismatch, and it is testable: the disagreement should concentrate on deciduous crowns and
vanish on conifers.

**IT ALSO CORRECTS ME.** In iteration 44 I attributed the NDVI reference's +2.45 pp apparent GAIN
(2016 -> 2021s) to phenology. **Both dates are leaf-on**, so a leaf-off/leaf-on seasonal swing is
not available as the explanation. What survives from that argument is narrower and still true: the
NDVI reference applies a STATIC ~2016 CHM at both dates, so its entire change signal is greenness -
and the two acquisitions do differ in greenness (median +0.208 vs +0.162, a 22% relative gap), so
within-season phenology can still contribute. **But "dominated by phenology" was too strong.**

**A systematic mismatch runs through the whole measurement workstream.** Every honest-recall number
we hold scores a leaf-off-trained model against a leaf-on reference, or against C-CAP, whose season
we have not established. The mismatch is not an occasional confound; it is the default condition of
the evaluation.

**Practical consequences, in order:**
1. **Do not pair 2020 or 2022 (leaf-off) with 2016, 2021s, 2019n or 2022n (leaf-on) for CHANGE.**
   Those comparisons measure phenology. That rules out several of the year-pairs the change product
   would naturally reach for.
2. **Weak-supervision training pairs (Search 54) must be season-matched.** A same-location pair
   labelled "no change" is only a lesson in sensor invariance if both dates are the same season;
   otherwise it teaches the model to ignore real phenological difference.
3. **2016 and 2021s are both leaf-on, same source, same sensor** - which makes them the best
   matched pair in the archive for change, and the iteration-44 result on them (11.14% discordance,
   +2.45 pp) is the most trustworthy change figure we have, thin as it is.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Answerable only by our own experiment""",
"""- **Q89.** Does the reference disagreement concentrate on DECIDUOUS crowns? The leaf-on NDVI
  reference vs leaf-off-trained model predicts it should, and that conifers should show little
  disagreement. If confirmed, the 15-17% inter-reference disagreement is largely a phenology
  artefact rather than a definitional dispute - which changes what the P3 human sample needs to
  adjudicate. Testable with the existing agreement partitions plus any conifer/deciduous proxy.
- **Q90.** What season is C-CAP? Its hi-res product is built from commercial imagery of unstated
  season, and every headline recall number we quote is scored against it. If C-CAP is leaf-on, our
  model is being judged on crowns absent from its training imagery in EVERY per-year figure.
- **Q91.** Which year-pairs are season-matched? Only matched pairs can support a change claim or a
  weak-supervision training pair. Currently known matched: {2016, 2021s} leaf-on, same sensor;
  {2019n, 2022n} leaf-on, same program; {2020, 2022} leaf-off, same program. **Everything else in
  the archive is unscored**, and the remaining 12 acquisitions are one command each.

### Answerable only by our own experiment""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Season-score the remaining 12 acquisitions (Q91)** - 2000, 2002, 2005, 2007, 2009, 2013, 2015,
   2017, 2019, 2021, 2023, 2024. One command each. Produces the season map that decides every valid
   year-pair for both the change product and weak-supervision training. **Highest value remaining
   and entirely mechanical.**
2. **Establish C-CAP's season (Q90)** - every headline recall number is scored against it.
3. **Test whether reference disagreement concentrates on deciduous crowns (Q89)** - would recast
   the 15-17% disagreement as phenology rather than definition.
4. **Separate season from resolution (Q86)** - needs one Colab re-inference of a degraded fine year.
5. **Specificity on the UNCHANGED class (Q66).**
6. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
7. **Geometric vs thematic accuracy for per-object products (Q41).**
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
10. **Get the flight dates** - still the cleanest proof.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 49 | 2026-08-19 | *** EMPIRICAL - season map, and why the NDVI ref is 'more liberal' *** "
       "| - | BOTH SNOHOMISH YEARS ARE LEAF-ON (2016: 1.95% non-green, 2021s: 0.58%). Archive splits "
       "BIMODALLY: four acquisitions 0-5%, two 16-33%, nothing between. EXPLAINS A STANDING FINDING: "
       "the NDVI reference is built from LEAF-ON imagery while the model is trained on LEAF-OFF "
       "labels - so it is not 'more liberal', it is looking at trees with leaves on them. Recasts "
       "the 15-17% reference disagreement as a possible PHENOLOGY artefact (Q89). CORRECTS my "
       "iteration-44 claim that NDVI change is 'dominated by phenology' - both its dates are "
       "leaf-on, so that was too strong. New Q89/Q90/Q91 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
