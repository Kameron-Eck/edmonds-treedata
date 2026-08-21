import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - TURNOVER MEASURED (Q50 / Q78) - 2026-08-19 - `phase4_qc_turnover.py`
The top queue item was not a search. Two designs were sized on a guessed turnover rate; this
measures it. Instrument: **C-CAP hi-res 2016 vs 2021** - same product, same producer, 5-year gap,
and independent of our model (using our own masks would confound turnover with model instability,
which is the very distinction we want).

**RESULT** (690,432 valid cells, 1/8 decimation):

| partition | share |
|---|---|
| stable canopy | 20.47% |
| stable non-canopy | 68.38% |
| **LOSS** (canopy -> non) | **6.44%** |
| **GAIN** (non -> canopy) | **4.72%** |
| **DISCORDANCE** | **11.16%** |
| net change | **-1.72 pp** |

**1. PAIRED SAMPLE SIZING - the answer survives, barely.** Recomputing Search 41's table at the
measured rates rather than assumed ones:

| n (paired) | ± at measured discordance | resolves 2.6 pp? |
|---|---|---|
| 250 | 4.14 pp | no |
| 500 | 2.92 pp | no |
| **750** | **2.39 pp** | **yes** |
| 1000 | 2.07 pp | yes |

Against Search 41's assumptions at n=750: low (4.0/1.4) gave ±1.65 pp, high (6.0/3.4) gave
±2.19 pp, **measured gives ±2.39 pp**. So reality is slightly worse than our pessimistic case, and
**the existing 750-point budget still works - but with no margin.** Search 41's headline stands and
its comfort does not.

**2. AND THE NUMBER FAILS ITS OWN SANITY CHECK - WHICH IS THE MORE IMPORTANT FINDING.**
C-CAP implies **23.94% of 2016 canopy was gone by 2021**, an annualised loss of **5.33%/yr**.
Compare lit ID 182: 3.5-5.1%/yr is typical **street-tree** mortality, and street trees turn over far
faster than whole canopy. Whole-canopy loss of a quarter in five years would be catastrophic and
locally obvious in a city that has been arguing about its tree code.

**So a large share of the 11.16% discordance is product error and vintage revision, not trees.**
That is Search 49's rare-class trap demonstrated on our own data, and Search 40's Seattle warning
(ID 167 - conflicting canopy values for identical dates) reproduced in miniature: **reference-vs-
reference change is dominated by method, not by trees.**

**Consequences, all of which sharpen earlier conclusions:**
* **Do not use C-CAP 2016 vs 2021 as a change reference.** It cannot support a -1.72 pp claim; the
  noise floor is far above the signal. Q66 (specificity on the UNCHANGED class) is not a refinement,
  it is a precondition.
* **The paired-precision figure above is pessimistic, and that is good news.** A human interpreter
  revisiting the same point is far more self-consistent than two C-CAP vintages, so true discordance
  in a P3 paired sample should be well below 11.16% - meaning the 750-point budget likely has more
  margin than the table shows. But we now know the direction of the correction rather than guessing.
* **Weak temporal supervision (ID 193) is better supported than feared.** At 5 years, 88.8% of
  locations are unchanged even by a noisy reference; the true figure is higher. "Predominantly
  unchanged" holds comfortably at our short-gap pairs, which is exactly the training material
  Search 54 identified.
* **A measured upper bound on turnover is now on record**, so the next person does not have to guess.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q78.** At what temporal gap does "same location, predominantly unchanged" break for Edmonds
  canopy? Our estimate says safe to ~3 years, violated by ~13. That threshold determines which of
  our 18 acquisitions can serve as weak-supervision training pairs - and it depends on the real
  turnover rate, which is Q50, still unmeasured. **The two questions should be answered together.**""",
"""- **Q78.** At what temporal gap does "same location, predominantly unchanged" break?
  **MEASURED: 11.16% discordance at a 5-year gap, and that is an upper bound.** So ~89% unchanged at
  5 years by a noisy reference, higher in truth - the assumption holds comfortably for our short-gap
  pairs. Long-gap pairs (2000-2020) remain unsafe by extrapolation but are now bounded rather than
  guessed.
- **Q80.** How much of the measured 11.16% is real canopy change and how much is C-CAP vintage
  revision? The implied 5.33%/yr whole-canopy loss exceeds published STREET-TREE mortality, so most
  of it cannot be trees. Separating the two requires a reference that is stable by construction -
  which is what the P3 paired human sample would be, and is another reason to run it.
- **Q81.** Does the same test on the NDVI references (2016 Snoh vs 2021s Snoh - same source, same
  sensor, 5-year gap) give a lower discordance than C-CAP-vs-C-CAP? If yes, it isolates how much of
  the 11.16% is C-CAP product revision specifically. Cheap: the rasters exist and the script now
  takes `--a/--b`.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Run the same turnover test on the NDVI references (Q81)** - 2016 Snoh vs 2021s Snoh, same
   source and sensor, 5-year gap. Isolates C-CAP product revision from real change. One command.
2. **Specificity on the UNCHANGED class (Q66)** - now a precondition, not a refinement; the
   turnover result shows the noise floor may exceed the signal.
3. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
4. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Ladder-side-tuning and cheap foundation-model adaptation.**
10. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 43 | 2026-08-19 | EMPIRICAL - turnover measured (not a search) | - | "
       "MEASURED C-CAP 2016 vs 2021: discordance 11.16% (loss 6.44, gain 4.72), net -1.72pp. "
       "Paired precision at MEASURED rates: n=750 -> +/-2.39pp, still resolves 2.6pp but with NO "
       "margin (Search 41 assumed +/-1.65-2.19). BUT THE NUMBER FAILS ITS SANITY CHECK: implied "
       "5.33%/yr whole-canopy loss EXCEEDS published street-tree mortality, so most of the 11% is "
       "PRODUCT REVISION not trees - Search 49's rare-class trap on our own data. C-CAP cannot serve "
       "as a change reference. Weak temporal supervision better supported than feared. New Q80/Q81 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
