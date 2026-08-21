import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** SEARCH 55 - LEAF-OFF. THE ACQUISITION SPEC MAY EXPLAIN THE CENTRAL FINDING *** - ID 194
Went after the acquisition dates - the standing top action - and found something better than dates:
**the acquisition SPECIFICATIONS**, which are published.

**THE TWO SPECS ARE OPPOSITE.**
* **Puget Sound regional orthophoto consortium** (88 participants, King County as lead manager -
  the source of our King County imagery): *"acquisition was to occur during **leaf-off** season
  while ground conditions were free of snow and smoke"*. The 2012 flight was March-May
  *"with the intent of representing leaf-off conditions"*; 2015 was acquired *"in the spring"*.
* **NAIP**: flown *"during the agricultural growing season, or **leaf-on** conditions"*, targeted at
  peak crop growth.

**So our archive mixes leaf-off and leaf-on imagery, and nothing in the pipeline accounts for it.**

**AND IF THE 2020 CITY OF EDMONDS ACQUISITION FOLLOWS REGIONAL PRACTICE, THE CONSEQUENCE IS LARGE:**
our ONE hand-labelled year would have been labelled on imagery **in which deciduous crowns are
bare**. Conifers hold their needles in March-May; deciduous trees do not. That is a *physical*
explanation for a finding the project has treated as a modelling defect:

| observation (STATE) | leaf-off explanation |
|---|---|
| "conifer-only-label blind spot" | deciduous crowns are literally not in the labelling imagery |
| scrub recall .25 vs forest .68 | deciduous scrub bare; conifer forest visible |
| recall .16 at 0-5 m rising to .93 at 30 m+ | short crowns are disproportionately deciduous yard/ornamental |
| 8/8 missed stands suburban, "purple-leaf LOW-NDVI" | purple-leaf ornamentals are deciduous - bare in spring |
| model strength does not move recall (finding 3) | no architecture recovers signal that is not in the pixels |

**Finding 3 is the tell.** Nine years spanning IoU .49-.76 with honest recall pinned at .51-.78 is
exactly what you expect when the limiting factor is not the model but **what the imagery physically
contains**.

**INDEPENDENT SUPPORT FROM THE GREENNESS SCREEN (iteration 18, recomputed against the spec):**

| rank | year | source | GRVI | spec |
|---|---|---|---|---|
| 1 | 2019n | NAIP | 0.1521 | **LEAF-ON** |
| 5 | 2022n | NAIP | 0.0808 | **LEAF-ON** |
| ... | | | | |
| 14 | **2020** | **CoE** | **0.0250** | **labelled year** |
| 15 | 2017 | CoE | 0.0242 | consortium |
| 16 | 2019 | King | 0.0224 | consortium |
| 17 | 2023 | King | 0.0143 | consortium |

**Both NAIP years (spec: leaf-on) sit in the top five of seventeen. The bottom six are all King
County or City of Edmonds - the consortium whose spec is leaf-off. Our labelled year is fourth
lowest of seventeen.** Two independent lines - published specification and measured scene greenness -
point the same way.

**WHAT THIS IS NOT.** It is not proof. Confirmed: the consortium SPEC is leaf-off, and King County
2012 and 2015 were spring flights. NOT confirmed: that the 2020 City of Edmonds acquisition
followed it, or the season of the Snohomish 2016/2021s flights. Colour balance remains confounded
with phenology in the GRVI screen (iteration 18's caution stands). **The per-exposure ACQ_DATE and
UTC_TIME fields exist in King County's photo-centre index layer**, so the dates are recoverable,
not lost - which converts this from hypothesis to fact with one data pull.

**IF IT HOLDS, IT REORDERS THE PROJECT.**
* The blind spot is a DATA problem, not a model problem. No amount of architecture, augmentation,
  domain generalization or foundation-model work recovers deciduous crowns from leaf-off pixels -
  which retrospectively explains why thirty iterations of modelling literature kept concluding that
  model quality was not the constraint.
* The right fix is **labels on leaf-on imagery** - the NAIP years, or Snohomish if leaf-on - not
  better training on 2020.
* Cross-era comparison acquires a new confound: comparing a leaf-off year to a leaf-on year measures
  phenology, not canopy change. **This is very likely the source of the sign disagreement in
  iteration 44** (+2.45 pp NDVI vs -1.72 pp C-CAP).
* The height curve may be substantially a DECIDUOUS-FRACTION curve, since short urban trees skew
  deciduous - which is a second confound layered on iteration 11's suburban/height entanglement.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Answerable only by our own experiment""",
"""- **Q84. [LIKELY THE MOST IMPORTANT OPEN QUESTION IN THE PROJECT]** Was the 2020 City of Edmonds
  acquisition flown LEAF-OFF? The regional consortium spec is leaf-off spring; NAIP is leaf-on. If
  2020 is leaf-off, our only hand labels omit deciduous canopy by construction, and the conifer-only
  blind spot, the height curve and finding 3 all have a physical rather than algorithmic explanation.
  **Recoverable from King County's photo-centre index (ACQ_DATE, UTC_TIME) or by asking the City.**
- **Q85.** Which of the 18 acquisitions are leaf-on and which leaf-off? Any cross-era comparison
  that mixes the two measures phenology, not canopy. This likely explains the iteration-44 sign
  disagreement and it invalidates specific year-pairs for both the change product and the
  weak-supervision training set (Search 54).
- **Q86.** Is the height curve partly a DECIDUOUS-FRACTION curve? Short urban trees skew deciduous
  and ornamental; if labels are leaf-off, low-height recall is depressed by species composition
  rather than by size. Testable once leaf-on labels exist, or by comparing recall-by-height on a
  leaf-on year (2019n/2022n) against a leaf-off year.

### Answerable only by our own experiment""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **CONFIRM THE 2020 SEASON (Q84).** Everything else is downstream of it. Sources: King County
   photo-centre index (ACQ_DATE/UTC_TIME fields, published), the City of Edmonds GIS contact, or
   the ortho metadata shipped with the tif. Not a search - a data pull or an email.
2. **Season-label all 18 acquisitions (Q85)** - decides which year-pairs are valid for change and
   for weak-supervision training.
3. **Recall-by-height on a LEAF-ON year vs a leaf-off year (Q86)** - tests whether the height curve
   is partly a deciduous-fraction curve. 2019n and 2022n are NAIP, spec leaf-on; both have prob
   rasters already scored.
4. **Specificity on the UNCHANGED class (Q66).**
5. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
6. **Geometric vs thematic accuracy for per-object products (Q41).**
7. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
8. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
9. **Shadow masking as IGNORE vs removal** - and note leaf-off flights have LOW SUN ANGLE, so the
   shadow axis (Search 31) and the phenology axis are correlated, not independent.
10. **Broadleaf / deciduous-specific crown segmentation** - now urgent rather than merely unread.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 45 | 2026-08-19 | *** Search 55 - LEAF-OFF: the acquisition spec may explain the central "
       "finding *** | 194 | PUGET SOUND CONSORTIUM SPEC (King County lead, our King imagery) = "
       "acquire during LEAF-OFF season, March-May spring. NAIP SPEC = LEAF-ON peak growing season. "
       "Our archive MIXES them and nothing accounts for it. IF 2020 CoE followed regional practice, "
       "our ONE labelled year was labelled on imagery where DECIDUOUS CROWNS ARE BARE - a PHYSICAL "
       "explanation for the conifer-only blind spot, the height curve, scrub recall .25, the 8/8 "
       "purple-leaf missed stands, and finding 3 (no architecture recovers signal absent from "
       "pixels). GRVI screen agrees: both NAIP years top-5, bottom-6 all consortium, 2020 is 4th "
       "LOWEST of 17. NOT PROVEN - 2020's actual date is recoverable from King County's photo-centre "
       "index. New Q84/Q85/Q86 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
