import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - TWO INDEPENDENT DEFICITS, AND THEY COMPOUND (Q118) *** - 2026-08-19
Recomputed recall-by-height separately over pervious and impervious ground. The question was
whether the height staircase is the overhang deficit in disguise. **It is not.**

| CHM band | PERVIOUS | n | IMPERVIOUS | n | gap |
|---|---|---|---|---|---|
| 0-2 m | 0.1206 | 1,584 | **0.0262** | 420 | -0.094 |
| 2-5 m | 0.1721 | 18,927 | **0.0282** | 6,878 | -0.144 |
| 5-10 m | 0.3930 | 45,325 | 0.1111 | 16,704 | -0.282 |
| 10-15 m | 0.5753 | 35,584 | 0.3013 | 9,907 | -0.274 |
| 15-20 m | 0.7324 | 34,988 | 0.4375 | 7,058 | -0.295 |
| 20-25 m | 0.8358 | 34,994 | 0.5805 | 5,421 | -0.255 |
| 25-30 m | 0.8902 | 32,680 | 0.6607 | 3,979 | -0.230 |
| 30+ m | **0.9421** | 62,293 | 0.7509 | 4,909 | -0.191 |

**The staircase survives on pervious ground with a spread of +0.82** (0.12 to 0.94), and appears
again on impervious ground with a spread of +0.72. **These are two independent deficits, and they
compound.**

**AND THE OVERHANG PENALTY IS NOT A SHORT-TREE ARTEFACT.** It persists at every height, including
**-0.19 at 30 m and above**. A 30-metre tree over pavement is detected at 0.75 against 0.94 over
grass. Overhang costs the model roughly a fifth to a third of its recall regardless of tree size -
so it cannot be explained away as "short suburban crowns are also over pavement".

**THE MAP OF THE DEFICIT, WHICH IS THE USEFUL OUTPUT.** The model's blind spot is now two-
dimensional and specific:
* short -> bad (0.17 at 2-5 m even over grass)
* over impervious -> bad (a 0.19-0.30 penalty at every height)
* **short AND over impervious -> effectively blind: 0.028**

**That worst cell is the one to act on.** At 2-5 m over impervious the model finds under 3% of what
C-CAP calls canopy - street trees and yard trees beside driveways and houses, the most policy-
relevant canopy in a residential city, and the class a tree ordinance is written about.

**WHAT IT MEANS FOR THE FIXES ON THE TABLE.**
* **Height input (Q119) addresses the overhang axis directly** - the CHM is what separates a crown
  over a roof from the roof - but the pervious-only staircase shows it will not, on its own, fix the
  short-crown axis, because that deficit exists where there is no roof to confuse.
* **Annotation should target the intersection**, not suburban stands generally. STATE's plan calls
  for "3-5 suburban/ornamental sites"; this says the highest-value labels are **short crowns over
  impervious surfaces**, which is a much narrower and more findable target.
* **The two axes have different mechanisms** - resolution and spectral mixing for short crowns,
  contrast and context for overhang - so they plausibly need different remedies, and progress on one
  should not be expected to move the other.

**Caveat.** Both axes are measured against C-CAP, which has its own error and its own
impervious-under-canopy construction; the overhang penalty is partly a statement about where C-CAP
and the model disagree most. The stability across three sensors (iteration 66) argues it is real,
but a human check on the 2-5 m over-impervious cell would settle it - and that cell is small enough
to inspect exhaustively.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q118. [HIGH VALUE, ONE RUN]** Is the recall-by-height staircase just the overhang deficit in
  disguise?""",
"""- **Q118. ANSWERED: NO - two independent deficits that COMPOUND.** The staircase survives on
  pervious ground alone (spread +0.82, 0.12 to 0.94), and the overhang penalty persists at every
  height including **-0.19 above 30 m**. Worst cell: **2-5 m over impervious = 0.028**. Original
  question below.
  Is the recall-by-height staircase just the overhang deficit in disguise?
- **Q120.** Is the 2-5 m over-impervious cell real, or a C-CAP artefact? The model finds under 3% of
  it. That is extreme enough to warrant exhaustive human inspection - and the cell is small
  (6,878 sampled cells) so it can be checked completely rather than sampled. **If it is real it is
  the single highest-value annotation target in the project; if it is C-CAP error it removes a large
  slice of the apparent shortfall.** Either answer is worth having.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Human-check the 2-5 m over-impervious cell (Q120)** - recall under 3%, small enough to inspect
   exhaustively, and either answer is decisive: the top annotation target, or a large slice of the
   shortfall that is C-CAP error.
2. **Does the CHM-input model close the overhang gap (Q119)?** `prob_2016_corrected` and the
   aux-height variants exist; measure their over-impervious recall against the baseline's 0.3183.
3. **Characterise the tall-but-not-green pixels (Q114).**
4. **Write down the canopy definition (Q1).**
5. **Test whether scrub reconciles the references (Q112).**
6. **Trace what else used the NDVI reference (Q107).**
7. **What DOES the model key on (Q98)?** - the overhang finding suggests contrast and context
   rather than colour, which is testable.
8. **Specificity on the UNCHANGED class (Q66).**
9. **Recover C-CAP's source imagery date (Q109).**
10. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 67 | 2026-08-19 | *** EMPIRICAL - two INDEPENDENT deficits that compound (Q118) *** | - "
       "| The height staircase SURVIVES on pervious ground alone: 0.1206 at 0-2 m to 0.9421 at 30+ m, "
       "spread +0.82. And the overhang penalty persists at EVERY height, including -0.19 above 30 m "
       "(0.7509 vs 0.9421) - so it is NOT a short-tree artefact. TWO-DIMENSIONAL BLIND SPOT: short "
       "-> bad, over-impervious -> bad, and SHORT AND OVER IMPERVIOUS -> 0.028, effectively blind. "
       "That worst cell is street/yard trees beside driveways - the most policy-relevant canopy in a "
       "residential city. Implication: height input addresses overhang but NOT the short-crown axis; "
       "annotation should target the INTERSECTION, not suburban stands generally (Q120) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
