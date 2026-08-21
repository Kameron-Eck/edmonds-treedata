import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - THE TWO REFERENCES DISAGREE ON THE **SIGN** OF CHANGE (Q81) - 2026-08-19
Ran the turnover test on the NDVI references - 2016 Snohomish vs 2021s Snohomish, **same source,
same sensor, same 50 cm GSD, same 5-year window** as the C-CAP pair. Side by side:

| | C-CAP 2016 -> 2021 | NDVI ref 2016 -> 2021s |
|---|---|---|
| loss | 6.44% | 4.34% |
| gain | 4.72% | 6.80% |
| **discordance** | **11.16%** | **11.14%** |
| **NET CHANGE** | **-1.72 pp (LOSS)** | **+2.45 pp (GAIN)** |

**The two references disagree on whether Edmonds gained or lost canopy between 2016 and 2021.**
A 4.17 pp spread, on the sign. The policy question is whether canopy is heading toward 35% by 2036;
neither available reference can say which direction it is currently moving.

**And both land on ~11.1% discordance from completely different failure modes** - which is strong
evidence that each is dominated by its own noise floor rather than by trees:
* **C-CAP** compares two product VINTAGES, so method revision enters as apparent change. Its implied
  5.33%/yr whole-canopy loss exceeds published street-tree mortality (ID 182) and is not credible.
* **The NDVI reference** applies a STATIC ~2016 CHM at both dates, so its height test is identical
  across the pair and the entire change signal comes from greenness - which is phenology-sensitive
  (Search 30). Two Snohomish flights at different times of year would manufacture exactly this.

**So: C-CAP change is dominated by product revision, NDVI change by phenology. Neither measures
trees.** This is Search 40's Seattle finding (ID 167 - conflicting canopy values for identical
dates) reproduced on our own data, and it settles several threads at once:
* the "two references bracket truth" framing (STATE) is too generous for CHANGE - they do not
  bracket, they contradict;
* Q66 (specificity on the unchanged class) is confirmed as a precondition, not a refinement;
* **the P3 human sample is not merely useful, it is the only instrument that could establish the
  sign of change** - which is a much stronger argument for running it than "we should be rigorous".

**A BUG FOUND AND FIXED, REPORTED BECAUSE IT NEARLY PRODUCED A FALSE FINDING.** The first NDVI run
returned 0.97% discordance and 90.56% "stable canopy", which would have looked like a wonderfully
clean reference. It was wrong: `phase4_qc_turnover.py` treated 0 as nodata, which is correct for
C-CAP but **not** for the NDVI references, where 0 means NON-VEGETATED - a real class. Every
non-vegetated pixel was silently dropped, leaving only grass and canopy and inflating the canopy
share from ~33% to ~91%. Fixed with an explicit `--zero-is-data` flag and a comment at the mask,
so the next person meets the trap with a warning rather than a plausible number.

**Design consequence.** Both measured discordances are ~11%, so the paired-precision figure from
iteration 43 (n=750 -> +/-2.39 pp) is unchanged. But its interpretation is now firmer: **that 11% is
mostly instrument noise, not trees**, so a self-consistent human interpreter revisiting the same
point should see far less - and the 750-point budget has more real margin than the arithmetic
suggests. The measurement that would confirm it is the P3 blind-subset (Search 42).
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q81.** Does the same test on the NDVI references (2016 Snoh vs 2021s Snoh - same source, same
  sensor, 5-year gap) give a lower discordance than C-CAP-vs-C-CAP? If yes, it isolates how much of
  the 11.16% is C-CAP product revision specifically. Cheap: the rasters exist and the script now
  takes `--a/--b`.""",
"""- **Q81.** Does the NDVI-reference pair give lower discordance than C-CAP-vs-C-CAP?
  **ANSWERED: no - 11.14% vs 11.16%, nearly identical - but with OPPOSITE SIGN (+2.45 pp vs
  -1.72 pp).** Two references, same city, same window, disagreeing on whether canopy grew or shrank.
  Each is dominated by its own artefact: C-CAP by vintage revision, NDVI by phenology (static CHM
  means the whole signal is greenness).
- **Q82.** Would a phenology-controlled NDVI reference change the sign? The NDVI reference's change
  signal is pure greenness because the CHM is static across both dates. If the 2016 and 2021s
  Snohomish flights differ in season, that alone could produce +2.45 pp. **Acquisition dates would
  settle it** - the same missing fact that gates Q19, Q24, Q29 and Q59. This is now the fifth open
  question blocked on it.
- **Q83.** Can ANY existing reference establish the SIGN of canopy change in Edmonds? Both available
  ones fail. If not, every change claim in the project rests on the human sample, and P3 stops being
  a validation step and becomes the primary measurement.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **RECOVER THE ACQUISITION DATES.** Promoted from a standing note to the top item. It now gates
   Q19, Q24, Q29, Q59 and Q82 - including whether the NDVI reference's +2.45 pp is phenology. King
   County GIS, WA state imagery programs and USDA NAIP all publish flight dates. Not a search.
2. **Specificity on the UNCHANGED class (Q66)** - confirmed as a precondition by two measurements.
3. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
4. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Ladder-side-tuning and cheap foundation-model adaptation.**
10. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 44 | 2026-08-19 | EMPIRICAL - references disagree on the SIGN of change (Q81) | - | "
       "NDVI ref 2016 vs 2021s: discordance 11.14% (vs C-CAP 11.16%) but NET +2.45pp GAIN against "
       "C-CAP's -1.72pp LOSS. TWO REFERENCES DISAGREE ON WHETHER EDMONDS GAINED OR LOST CANOPY. Each "
       "dominated by its own artefact: C-CAP by vintage revision, NDVI by phenology (static CHM = "
       "signal is pure greenness). Neither measures trees. P3 becomes the ONLY instrument that could "
       "establish the sign (Q83). BUG FOUND+FIXED: 0 is nodata in C-CAP but NON-VEG in the NDVI refs "
       "- first run gave a false 0.97%/90.6%-stable result |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
