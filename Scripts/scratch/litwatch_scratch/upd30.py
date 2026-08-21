import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 42 - ANCHORING vs FALSE CHANGE: a real trade-off, not a solved problem - IDs 171-172
Search 41 recommended paired interpretation and flagged anchoring as a risk. Searching it turns up
a genuine two-sided trade-off, with both failure modes measured, and no free option.

**SIDE ONE - ANCHORING IS LARGE AND BIASES TOWARD "NO CHANGE" (ID 171, Branch et al. 2022).**
Radiologists shown prior diagnostic information anchor at **38.3% (low experience)** and **28.3%
(most experienced)**, and can ignore task-relevant image evidence entirely once anchoring
information is present. Expertise reduces it; it does not remove it, so a single expert interpreter
is not a mitigation. **The direction is the dangerous one for us**: anchoring suppresses apparent
change, biasing a canopy trend toward zero, precisely where the policy question lives.

**SIDE TWO - INDEPENDENT READING MANUFACTURES FALSE CHANGE (ID 172, Mas et al. 2017, EJRS).**
From our own field: classifying each date independently generates spurious transitions, and a
cascading protocol (classify date 1, carry labels forward, edit only where change is seen) yields
consistent maps without them.

**AND FALSE CHANGE IS NOT MERELY NOISE - IT DESTROYS THE PRECISION GAIN.** Paired variance is
driven ONLY by discordant pairs, so every false change directly inflates it. Net change held at
+2.6 pp:

| scenario | gain% | loss% | n=250 | n=750 |
|---|---|---|---|---|
| true change only (clean pairing) | 4.0 | 1.4 | 2.86 pp | **1.65 pp** |
| + mild false change | 8.0 | 5.4 | 4.53 pp | 2.61 pp |
| + heavy false change | 15.0 | 12.4 | 6.48 pp | 3.74 pp |
| + severe false change | 25.0 | 22.4 | 8.53 pp | 4.92 pp |

**At severe false-change rates even 750 points cannot resolve 2.6 pp.** So Search 41's headline -
"the existing 750-point budget already works" - holds ONLY if the response design keeps false
change low. Independent reading is not a neutral alternative; it can spend the entire precision
advantage.

**THE RESOLUTION, AND IT REUSES SOMETHING ALREADY IN THE TRACKER.** Neither option is free, so
measure the bias rather than assuming it away: interpret the MAIN sample with the cascading/paired
protocol (low false change, high precision), and interpret a **blind independent subset** - dates
shown separately, order randomized - to **estimate the anchoring effect** and correct the main
estimate for it. That is exactly the interpenetrating-subsample design of Xing & Stehman 2024
(**ID 101**, Search 14), repurposed: there it separated interpreter variance, here it separates
protocol-induced bias. Same machinery, new use, already cited.

**What we still do not know:** the size of anchoring for CANOPY specifically. The 28-38% figures
are mammography, where the prior is a diagnosis rather than an image. Canopy-at-a-point is a
simpler judgement and the anchoring may be much smaller - or larger, since change is genuinely
subtle at 60 cm. Nothing found measures it for land cover, which makes the blind subset not merely
prudent but the only way to know.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q51.** Does interpreting both dates at the same point introduce ANCHORING bias? Repeated
  interpretation of the same location risks the interpreter carrying their first call forward,
  which would suppress apparent change - biasing us toward "no change" precisely where the policy
  question lives. Blind or randomized date order is the obvious mitigation; whether it suffices is
  unread.""",
"""- **Q51.** Does paired interpretation introduce ANCHORING bias? **ANSWERED: yes, and it is large
  in the one field that has measured it** - 28-38% in radiology (ID 171), biasing toward "no
  change". But the alternative is worse in a different way: independent reading manufactures FALSE
  CHANGE (ID 172), which directly destroys the paired estimator's precision (at severe rates even
  750 points cannot resolve 2.6 pp). **Resolution: cascading protocol for the main sample + a
  BLIND INDEPENDENT SUBSET to measure the anchoring and correct for it** - the interpenetrating
  design of ID 101, repurposed.
- **Q52.** How large is anchoring for CANOPY-AT-A-POINT specifically? The 28-38% figures are
  mammography, where the prior is a diagnosis rather than an image, and canopy presence is a
  simpler judgement. Nothing found measures it for land cover. Unknown, and the blind subset is
  the only way to find out - which means it must be designed in from the start, not added later.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Training-free / annotation-free crown segmentation** - annotation is the binding constraint
   and this came within ~2% of supervised models without instance labels.
2. **Geometric vs thematic accuracy for per-object products (Q41).**
3. **Temporal consistency as a training objective** - the model-side counterpart to the false-change
   problem this search surfaced on the human side.
4. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Ladder-side-tuning and cheap foundation-model adaptation.**
10. **False change in MODEL time series** - we have measured flicker but never asked what the
    literature says about suppressing spurious model-side transitions without suppressing real ones.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 30 | 2026-08-18 | Search 42 - anchoring vs false change | 171-172 | "
       "TWO-SIDED TRADE-OFF, both measured. Anchoring in paired reading is 28-38% (radiology) and "
       "biases toward NO CHANGE - the dangerous direction. But independent reading manufactures "
       "FALSE CHANGE, which directly destroys the paired precision gain: at severe rates even 750 "
       "pts cannot resolve 2.6pp. RESOLUTION: cascading main sample + BLIND INDEPENDENT SUBSET to "
       "measure anchoring - reuses Xing & Stehman ID 101. Anchoring size for canopy is UNKNOWN |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
