import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - NORMALISATION CANNOT RESCUE GRVI, AND BRIGHTNESS BEATS GREENNESS (Q130/Q134) *** - 2026-08-19
**The test is chosen so it needs no normalisation implemented.** AUC is **invariant under any
monotone transform** - affine gain/offset (IR-MAD), gamma, histogram matching, quantile mapping are
all monotone. So AUC settles whether a year's problem is *calibration* (fixable) or *lost
information* (not), before spending any effort on IR-MAD.

Discriminating C-CAP canopy from C-CAP non-canopy at 162,829 points:

| acquisition | **AUC GRVI** | AUC brightness | canopy-vs-other separation (SD) |
|---|---|---|---|
| 2000 King | 0.5927 | 0.6333 | 0.057 |
| 2005 King | 0.6941 | 0.7170 | 0.471 |
| 2009 King | 0.7061 | 0.6847 | 0.561 |
| 2013 King | **0.7273** | 0.6881 | 0.429 |
| **2019 King** | **0.5835** | 0.6838 | **-0.045** |
| **2021 King** | **0.5453** | 0.6662 | **-0.007** |
| 2019 NAIP | 0.6893 | 0.6887 | 0.656 |
| 2016 Snoh | 0.6911 | 0.6631 | 0.648 |

**1. I HAD THE WRONG YEARS. 2019 AND 2021 KING ARE WORSE THAN 2000.** I have been treating 2000 as
the damaged acquisition. By information content the two most recent King County years are worse -
AUC 0.5835 and **0.5453**, with canopy-vs-other separation of **-0.045 and -0.007**, i.e. GRVI does
not distinguish canopy from anything else there at all. The monotone drift found in it.72 is not a
harmless shift; **it corresponds to real loss of discriminative signal in the newest RGB years.**

**AND THE VINTAGE CONFOUND ARGUES THE SAME WAY.** C-CAP is 2016, so distance in time should hurt
2000 most and help 2019/2021. **It goes the other way**, which makes the result stronger rather than
weaker.

**THE CONTROLLED PAIR AGAIN: 2019 King 0.5835 versus 2019 NAIP 0.6893.** Same year, same ground.
The difference is the sensor and its processing, not the season or the vegetation.

**2. Q130 AND Q134 ANSWERED, BOTH NEGATIVE.** Because AUC is monotone-invariant, **IR-MAD,
histogram matching and per-year standardisation cannot recover 2000, 2019 or 2021 King GRVI** - the
information is not mis-scaled, it is absent. Normalisation remains worth doing for **cross-year
threshold comparability** (it.72, it.73), but **not as a way to make greenness work in those years**.
That distinction saves implementing IR-MAD for the wrong reason.

**3. THE ACTIONABLE FINDING: BRIGHTNESS IS A BETTER AND FAR MORE STABLE CANOPY CUE THAN GREENNESS.**
Darkness-as-canopy scores **0.663 to 0.717 in every single acquisition** - a range of 0.054 -
against GRVI's 0.545 to 0.727, a range of 0.182. **In the three worst GRVI years brightness beats it
outright**, by 0.041 (2000), 0.100 (2019 King) and 0.121 (2021 King).

**This reframes what a cross-sensor RGB model should lean on.** Greenness is the intuitive canopy
cue and it is the least transferable one here; luminance is unglamorous and it is the one thing
every sensor in this archive agrees on. It also offers a partial explanation for why an RGB U-Net
transfers across these sensors as well as it.73 shows it does - **it is unlikely to be keying mainly
on colour**, which is directly testable and is exactly open question Q98.

**Caveats.** GRVI was never strong here - its best year is 0.7273, which is a weak discriminator by
any standard - so this is a comparison between two mediocre features, not a demotion of a good one.
Both are single-pixel, context-free features, while the model has texture and neighbourhood; these
numbers bound what colour alone can do, not what the model does. And all of it is measured against
C-CAP, with C-CAP's own definition and errors.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)
s = s.replace("""- **Q132. [DELIVERABLE-LEVEL, HIGH PRIORITY]**""",
"""- **Q130/Q134. ANSWERED, BOTH NEGATIVE.** AUC is monotone-invariant, so no normalisation can
  rescue GRVI where AUC is near 0.5 - and that is 2000 (0.5927), **2019 King (0.5835) and 2021 King
  (0.5453)**, not just the old years. Normalisation is still worth doing for cross-year threshold
  comparability, but **not** to make greenness work.
- **Q135. [DIRECTLY TESTABLE, ties to Q98]** If brightness is the more transferable cue (0.663-0.717
  in every year vs GRVI's 0.545-0.727), is that what the model actually keys on? A channel-ablation
  or occlusion test on the trained U-Net would answer it, and the answer decides whether the
  pre-2005 and post-2017 RGB years are usable at all.
- **Q132. [DELIVERABLE-LEVEL, HIGH PRIORITY]**""")
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 75 | 2026-08-19 | *** EMPIRICAL - normalisation CANNOT rescue GRVI, and BRIGHTNESS beats "
       "greenness (Q130/Q134) *** | - | Test chosen to need no normalisation built: AUC is INVARIANT "
       "under any monotone transform (affine/IR-MAD, gamma, histogram matching), so it separates "
       "CALIBRATION problems from LOST INFORMATION. AUC GRVI: 2013 .7273 best; 2000 .5927; **2019 "
       "King .5835 and 2021 King .5453 with separation -0.045 and -0.007**. I HAD THE WRONG YEARS - "
       "the two NEWEST King years are worse than 2000, and the C-CAP 2016 vintage confound argues "
       "the same way since it should have HELPED them. Controlled pair again: 2019 King .5835 vs "
       "2019 NAIP .6893, same year same ground. => Q130/Q134 BOTH NEGATIVE: IR-MAD cannot recover "
       "those years, information is absent not mis-scaled; normalisation still worth doing for "
       "cross-year THRESHOLD comparability but not for greenness. ACTIONABLE: BRIGHTNESS "
       "(darker=canopy) scores .663-.717 in EVERY acquisition (range .054) vs GRVI .545-.727 (range "
       ".182), and beats GRVI outright in its 3 worst years by .041/.100/.121. Luminance is the one "
       "cue every sensor here agrees on - plausible partial reason the RGB U-Net transfers as well "
       "as it.73 shows (Q135, ties to Q98). CAVEAT: both are weak single-pixel features; this bounds "
       "what COLOUR ALONE can do, not what the model does |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
