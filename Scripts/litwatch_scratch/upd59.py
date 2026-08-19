import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - THE FOOTPRINT ERROR BARELY MOVES RECALL (Q101/Q105) - 2026-08-19
Re-score complete. **My iteration-58 prediction was directionally right and badly wrong on
magnitude**, and the reason is instructive.

| year | old rec | CITY rec | delta | old pre | CITY pre | delta |
|---|---|---|---|---|---|---|
| 2000 | .6293 | .6453 | **+0.0160** | .7759 | .7788 | +0.0029 |
| 2002 | .5050 | .5236 | **+0.0186** | .8399 | .8387 | -0.0012 |
| 2013 | .7085 | .7072 | -0.0013 | .8549 | .8435 | -0.0113 |
| 2015 | .6221 | .6296 | +0.0075 | .8833 | .8857 | +0.0024 |
| 2017 | .7781 | .7775 | -0.0005 | .8082 | .8189 | +0.0107 |

**HARNESS VALIDATED.** On the old reference the script reproduces all five published figures:
2013 .7085 vs .7094, 2000 .6293 vs .6303, 2002 .5050 vs .5069, 2015 .6221 vs .6222,
2017 .7781 vs .7784 - every one within a thousandth or two, the expected decimation difference.

**I predicted citywide recall "should come out HIGHER... by a few points". It moves by -0.001 to
+0.019, mean +0.008.** Three of five years rise, two fall trivially. **The per-year accuracy figures
are essentially robust to the footprint error.**

**AND THAT RESOLVES Q101 CLEANLY.** The .6303 -> .6749 gap on 2000 between the old clip and
`snohfull` is now decomposed:
* **+0.016** from the genuinely missing city area
* **+0.029** from non-Edmonds rural county forest

**About two thirds of that gap was land outside Edmonds.** Scoring against `snohfull` would have
inflated recall with ground the deliverable does not cover. **The old clip was the better of the two
available references, not the worse one** - which reverses the implication I drew in iteration 55.

**THE PRECISE LESSON, AND IT IS WORTH GENERALISING.** Iteration 56 raised the alarm that headline
numbers were computed on 80% of the city. That was true. But the consequence splits sharply by
statistic type:

| statistic | effect of the footprint error |
|---|---|
| **canopy FRACTION / area** | **large - 29.5% -> 36.05%, a 6.5 pp shift** |
| recall, precision | **negligible - under 2 pp, mostly under 1** |

**Because recall is CONDITIONED on reference canopy**, adding more canopy of similar detectability
barely moves it. **The canopy fraction is a RATIO OVER THE AREA**, so the omitted area changes it
directly - and the omitted fifth was 52.6% canopy against the south's 32.3%.

So: **footprint errors are devastating for area statistics and nearly harmless for accuracy
statistics.** Iteration 56 was right to raise it and wrong to imply it contaminated everything. The
accuracy work of the whole measurement programme stands; only the area figures needed rescoping -
which is exactly the number that feeds the policy comparison.

**Scoring my own prediction.** I wrote it down before the run specifically so it could be checked,
and it failed on magnitude. The failure was informative: I reasoned "the added area is forest, the
model is good at forest, so recall rises" and neglected that recall's denominator grows with its
numerator. A conditional statistic does not respond to adding more of what it is conditioned on.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q101.** How much of the .6303 -> .6749 gain is the missing city strip versus non-Edmonds rural
  forest?""",
"""- **Q101. ANSWERED.** Of the +0.045, only **+0.016 is the missing city area**; **+0.029 is
  non-Edmonds rural forest**. Two thirds of the gap was land outside the deliverable. The old clip
  was the better of the two available references. Original question below.
  How much of the .6303 -> .6749 gain is the missing city strip versus non-Edmonds rural forest?""")

s = s.replace("""- **Q105.** Do the per-year RECALL figures change when scored against the city-clipped reference?""",
"""- **Q105. ANSWERED: barely.** -0.001 to +0.019, mean +0.008 across five years. Accuracy statistics
  are robust to the footprint error; AREA statistics are not (29.5% -> 36.05%). The distinction is
  structural: recall is conditioned on reference canopy, canopy fraction is a ratio over area.
  Original question below.
  Do the per-year RECALL figures change when scored against the city-clipped reference?""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Re-score the NDVI reference on the city footprint (Q103)** - now the ONLY unresolved half of
   the reference-disagreement question. C-CAP citywide is 36.05%; the NDVI figure of 37.7% is still
   computed over 66.7% of the city. Same-footprint comparison has never been made.
2. **Acquire county-wide C-CAP 2021 (Q104)** - a download; unblocks citywide change.
3. **Write down the canopy definition (Q1)** - open since the Phase 4 assessment, now load-bearing
   for a 36.05% figure that could be quoted to a city.
4. **What DOES the model key on (Q98)?**
5. **Specificity on the UNCHANGED class (Q66).**
6. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
7. **Geometric vs thematic accuracy for per-object products (Q41).**
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Finish the rendering index** (2017 especially).
10. **Get the flight dates.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 59 | 2026-08-19 | EMPIRICAL - the footprint error barely moves RECALL (Q101/Q105) | - | "
       "Re-score done, harness reproduces all five published figures within .002. Citywide recall "
       "moves -0.001 to +0.019, MEAN +0.008 - my iteration-58 prediction of 'a few points' FAILED on "
       "magnitude. Q101 DECOMPOSED: of the .6303->.6749 snohfull gap, only +0.016 is missing city "
       "area, +0.029 is NON-EDMONDS rural forest - so the old clip was the BETTER reference, "
       "reversing iteration 55's implication. THE LESSON: footprint errors are devastating for AREA "
       "statistics (29.5->36.05%) and nearly harmless for ACCURACY statistics, because recall is "
       "conditioned on reference canopy while fraction is a ratio over area |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
