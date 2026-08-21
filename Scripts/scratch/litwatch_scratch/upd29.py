import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 41 - PAIRED SAMPLING: the fix for Q48 - IDs 169-170
Search 40 ended on the project's central feasibility question: every uncertainty we have exceeds
the ~2.6 pp effect a decadal canopy goal implies. **This iteration finds the design that closes
the gap, and it costs no extra points.**

**The principle is settled and old (ID 170, Frayer & Furnival 1967, Forest Science).** Forest
inventory resolved this in the 1960s: **permanent plots give the highest precision for CHANGE**
(shared bias cancels between dates), temporary plots give unbiased LEVELS, and **sampling with
partial replacement** keeps some of each to get both. Our Phase 3 design uses neither - it samples
each year independently.

**The arithmetic, for a net +2.6 pp change** (paired variance is McNemar-form: only points that
CHANGED contribute, so the ~2/3 of points that are canopy at both dates drop out entirely):

| n | paired ± (low turnover) | paired ± (high turnover) | independent ± | detects 2.6 pp? |
|---|---|---|---|---|
| 250 | 2.86 pp | 3.79 pp | 8.30 pp | no |
| **500** | **2.02 pp** | 2.68 pp | 5.87 pp | **yes (low turnover)** |
| **750** | **1.65 pp** | **2.19 pp** | 4.79 pp | **YES, both** |
| 1000 | 1.43 pp | 1.89 pp | 4.15 pp | yes |

**Pairing buys roughly a 2.9x precision gain, and it is the difference between "cannot answer" and
"can answer".** Independent sampling never reaches 2.6 pp at any affordable n - not even 1000
points.

**THE PUNCHLINE FOR THE EXISTING PLAN.** Phase 3 is scoped at **250 points x 3 years = 750 points**.
That is *already* the budget that works - it is simply being **spent the wrong way**. Interpreted
independently per year it answers nothing at the policy-relevant scale; interpreted as **the same
points revisited across dates** it resolves a 2.6 pp change in both turnover scenarios. Same human
hours, same 750 interpretations, opposite conclusion about feasibility.

**And the omission problem has its own estimator (ID 169, Olofsson et al. 2020, RSE).** Our model
is a documented high-precision under-predictor missing 30-35% of reference forest, so every area
figure is omission-dominated and the change series compounds it. This paper treats omission
specifically as it propagates into area AND area-change estimates, and gives estimators that
mitigate rather than merely report it. It is the missing link between the Search 9 machinery
(ID 69) and a defensible change number.

**Caveats, honestly.** The turnover assumptions (4.0%/1.4% and 6.0%/3.4% gain/loss) are guesses -
the true discordant rate drives everything and we do not know it, though the P2 partition could
bound it. Pairing also introduces its own risks: the interpreter sees both dates together and may
anchor on the first, which is a known bias in repeated interpretation, so blind or randomized date
order matters. And permanent points can drift out of representativeness over 24 years, which is
exactly what partial replacement exists to fix.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q49.** Should the deliverable lead with PAIRED CHANGE between matched-instrument year pairs
  rather than an 18-year series of absolute percentages? The former is defensible at achievable
  precision; the latter inherits every source-driven offset. That is a scope decision for Kam, not
  a technical one, and it depends on Q19 (which years share an instrument).""",
"""- **Q49.** Should the deliverable lead with PAIRED CHANGE between matched-instrument year pairs
  rather than an 18-year series of absolute percentages? **Search 41 makes this concrete and
  affordable:** the existing 750-point budget resolves a 2.6 pp change IF interpreted as the same
  points revisited across dates, and resolves nothing at that scale if interpreted independently
  per year. Same hours, opposite feasibility. Scope decision for Kam.
- **Q50.** What is the true discordant (change) rate between our year-pairs? Paired precision
  depends entirely on it, and our estimates (4%/1.4%, 6%/3.4%) are guesses. The P2 agreement
  partition could bound it from raster data before any human interpretation, which would let us
  size the sample properly instead of assuming.
- **Q51.** Does interpreting both dates at the same point introduce ANCHORING bias? Repeated
  interpretation of the same location risks the interpreter carrying their first call forward,
  which would suppress apparent change - biasing us toward "no change" precisely where the policy
  question lives. Blind or randomized date order is the obvious mitigation; whether it suffices is
  unread.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Anchoring / order effects in repeated photo-interpretation (Q51)** - paired designs depend on
   it and it would bias us toward "no change", the worst direction for this project.
2. **Training-free / annotation-free crown segmentation** - annotation is the binding constraint.
3. **Geometric vs thematic accuracy for per-object products (Q41).**
4. **Temporal consistency as a training objective.**
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
8. **Instance-norm / whitening for style removal.**
9. **Shadow masking as IGNORE vs removal.**
10. **Ladder-side-tuning and cheap foundation-model adaptation.**

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 29 | 2026-08-18 | Search 41 - paired / partial-replacement sampling | 169-170 | "
       "ANSWERS Q48. Paired interpretation (same points, both dates) gives ~2.9x precision because "
       "only CHANGED points contribute variance: 750 pts -> +/-1.65-2.19pp, resolving a 2.6pp "
       "effect; independent sampling never gets there at any affordable n. THE EXISTING 250x3=750 "
       "BUDGET ALREADY WORKS - it is just being spent the wrong way. Frayer & Furnival 1967 is the "
       "canonical design; Olofsson 2020 handles omission in CHANGE estimates. New Q50/Q51 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
