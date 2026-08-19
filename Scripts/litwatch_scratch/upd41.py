import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 53 - DIRECT CHANGE MAPPING FROM ONE LABELLED YEAR - IDs 191-192
Search 52 left Q74 looking like a dead end: the protocol says map change DIRECTLY, but direct
change detection needs labelled bitemporal CHANGE pairs, and we have none and cannot afford them.
**That objection is removed.**

**STAR / ChangeStar (ID 191, Zheng et al. 2024, IJCV - peer-reviewed).** Trains a change detector
from **single-temporal labels alone**, by constructing pseudo-bitemporal pairs from unpaired
labelled images so that change supervision is generated from ordinary semantic labels. Its stated
motivation is precisely our constraint - labelling change regions in bitemporal high-resolution
pairs is prohibitively expensive.

| what STAR needs | what we have |
|---|---|
| single-date semantic labels | the 2020 hand-labelled year |
| unpaired labelled images | 2020 crops across the city |
| NO labelled change pairs | correct - we have none |

**So the architecture the protocol recommends is reachable from the assets we already hold.** That
closes a loop opened two iterations ago: Search 44 (He 2024) and Search 52 (CEOS) both said
post-classification comparison of 20-30%-error maps manufactures change; this says the alternative
is trainable without new labels.

**Do not treat it as settled.** Three cautions:
1. STAR is built for **object** change (buildings) on satellite imagery. Canopy is fragmented,
   fuzzy-edged and seasonally variable - the pseudo-pair construction assumes objects appear and
   disappear cleanly, which crowns do not.
2. Pseudo-bitemporal pairs are drawn from the SAME acquisition, so the model never sees the
   radiometric shift between eras that Searches 15-31 spent thirty iterations establishing as our
   real problem. It solves the label shortage, not the domain shift - the two would have to be
   composed (e.g. STAR pairs plus FOSMix-style frequency augmentation, ID 145).
3. It would need our 2020 labels to be good, and Search 39 (ID 165) says hand-drawn crowns inflate
   measured performance - so the training signal carries the correlated-error problem in with it.

**And the taxonomy to check ourselves against (ID 192, Peng et al. 2025, The Photogrammetric
Record).** Six label-efficient change-detection schemes - semi-supervised, weakly supervised,
self-supervised, active learning, few-shot, unsupervised - with systematic comparisons. Worth
reading before adopting STAR, because our constraint is not simply "few labels" but an unusual
shape: **one labelled DATE, zero labelled CHANGE, seventeen unlabelled acquisitions**. Something
cheaper may fit better, and this is the map for finding out.

**Where the modelling side now stands.** Two architectures are on the table and they are not
exclusive:
* **A. Fix the per-year masks** (style/frequency augmentation, DSBN, WiSE-FT, tuned ERM) and keep
  differencing them - incremental, uses existing code, but the protocol says the differencing step
  itself manufactures change.
* **B. Train a direct change detector from 2020 labels** (STAR family) - matches protocol guidance,
  needs no new labels, but is unproven for canopy and does not by itself address era shift.
The honest read is that B addresses the architectural criticism and A addresses the domain
criticism, and the project probably needs both.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q74.** Should change be mapped DIRECTLY rather than derived by comparing per-year masks? The
  CEOS protocol and He et al. 2024 (ID 176) now both say post-classification comparison of maps with
  20-30% error produces erroneous change. Our architecture is post-classification comparison. This
  is an architectural question, not a tuning one, and it may be the most consequential open item on
  the modelling side.""",
"""- **Q74.** Should change be mapped DIRECTLY rather than derived by comparing per-year masks?
  **The blocker is gone (Search 53):** STAR (ID 191) trains a change detector from SINGLE-TEMPORAL
  labels, which is exactly what we hold. Still an open decision, but no longer blocked on
  unaffordable change labels. Remaining doubts are canopy-specific, not label-specific.
- **Q76.** Does single-temporal change supervision work for FRAGMENTED, FUZZY-EDGED, seasonally
  variable objects? STAR is demonstrated on buildings, which appear and disappear cleanly. Crowns
  grow, thin, overlap and change with phenology. Nothing found tests it on canopy, and the
  pseudo-pair construction is where it would break.
- **Q77.** Can single-temporal change supervision be COMPOSED with era-shift handling? STAR's
  pseudo-pairs come from one acquisition, so the model never sees cross-era radiometry - it solves
  the label shortage, not the domain shift. Combining it with frequency-domain style augmentation
  (FOSMix, ID 145) is the obvious move and is untested by anyone.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Read Peng 2025 (ID 192) label-efficient taxonomy properly** - place our exact constraint (one
   labelled date, zero labelled change, 17 unlabelled acquisitions) and check whether something
   cheaper than STAR fits. Cheaper than adopting the first matching method.
2. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
3. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
4. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
5. **Canopy AREA turnover vs tree-COUNT mortality** - the Q50 counterweight.
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
s2 += ("\n| 41 | 2026-08-19 | Search 53 - direct change mapping from one labelled year | 191-192 | "
       "Q74 UNBLOCKED: STAR/ChangeStar (IJCV 2024) trains a change detector from SINGLE-TEMPORAL "
       "labels via pseudo-bitemporal pairs - exactly our asset (2020 labels, zero change labels). "
       "The architecture CEOS recommends is reachable without new labels. CAUTIONS: built for clean "
       "OBJECT change (buildings) not fuzzy crowns (Q76); pseudo-pairs come from one acquisition so "
       "it does NOT address era shift (Q77) - would need composing with FOSMix-style augmentation. "
       "Peng 2025 gives the label-efficient taxonomy to check cheaper options first |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
