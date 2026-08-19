import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 29 - SDG sweep with the right vocabulary - 2026-08-18 - IDs 145-146
First iteration searched under **domain generalization / SDG** rather than domain adaptation.
Immediately more productive, which is itself the lesson: sixteen iterations were sampling the
wrong shelf.

**FOSMix (ID 145, Iizuka, Xia & Yokoya 2024, TGRS) refines what we were about to do wrong.**
Everything from Search 24, 26 and 28 converged on "mix style in the frequency domain". FOSMix is
the remote-sensing realization - and it adds the constraint we were missing: **keep the
frequencies that carry segmentation signal, randomize only the rest**, plus a consistency
regularizer. That matters concretely for us. A blunt low-frequency amplitude swap (FDA, ID 136)
risks destroying the fine texture that separates a crown from a lawn at 7.5 cm; FOSMix explicitly
preserves the essential frequencies. It names **location, time and sensor** as its target shifts -
our exact triple - and the code is public.

**The map we lacked (ID 146, Rafi et al. 2024, Artificial Intelligence Review, peer-reviewed).**
A survey organizing DG for segmentation into families: augmentation/randomization, feature
normalization and disentanglement, and meta-learning. Use it to audit the loop's coverage for
whole families we have never touched, instead of continuing to sample one method at a time.

**A fifth convergence, now at the ARCHITECTURE level.** The sweep surfaced that **instance
normalization removes style while batch normalization preserves discriminability**, and that
combining them (global-to-local normalization) is a standard SDG move. This connects to
iteration 15: the BN question is not only freeze-vs-adapt, it is which NORMALIZATION to use.
IN+BN hybrids are a third option that neither v039 nor AdaBN considered, and they attack style
without touching the data pipeline.

**The literature independently names our two unsearched axes.** Domain randomization in remote
sensing is described as targeting texture divergence from **phenological periods** and style
divergence from **illumination** - i.e. leaf-on/leaf-off and sun angle, the two queue items
flagged in iteration 14 as never examined. They are recognized primary causes of RS domain shift,
not afterthoughts. That raises their priority and makes Q24 (were the two 2017 flights at similar
dates?) more load-bearing than it looked.

**Consolidated view of the style-vs-content thread, now five lines deep:**
| line | where style is handled | cost |
|---|---|---|
| RHM (ID 143) | intensity histogram | none - augmentation only |
| FDA (ID 136) | low-freq amplitude swap | none - FFT only |
| FOSMix (ID 145) | frequency, selectively | none - augmentation only |
| style mapper (ID 144) | statistical style prototypes | light module |
| IN+BN hybrids | inside the network | architecture change |
Every one of them is cheaper than the generative route we demoted in Search 28.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Phenology / leaf-on vs leaf-off across acquisitions.** Promoted: the SDG literature names
   phenological period as a PRIMARY cause of RS domain shift, and deciduous crowns are our known
   blind spot. Never examined.
2. **Shadow / illumination / sun-angle as a distinct domain axis.** Same promotion, same reason;
   also decides whether the 2017 matched pair is controlled (Q24).
3. **Instance-norm / whitening families for style removal** - the architecture-level branch of
   the style thread, surfaced this iteration and never followed.
4. **Audit coverage against the Rafi 2024 survey taxonomy** - which DG families has this loop
   never touched at all? Cheaper than sampling one more method.
5. **Deep ensembles vs cheaper uncertainty under shift.**
6. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art.**
7. **Temporal consistency as a training objective** rather than a post-hoc fix.
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Spatially-aware pseudo-labelling specifically** - the good half of SpADANN.
10. **How the Landsat/MODIS harmonization community validates a multi-decade series.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""- **Q26.** Does BN-affine-only fine-tuning suffice per year?""",
"""- **Q27.** Would a blunt FDA amplitude swap destroy the fine texture that separates crown from
  lawn at 7.5 cm? FOSMix (ID 145) exists precisely because unrestricted frequency mixing can
  remove segmentation-relevant detail. Our GSD range is far finer than the satellite data these
  methods are tuned on, so the "essential frequency" band is probably different for us and would
  need to be found empirically - on the 2017 matched pair, where the answer is checkable.
- **Q28.** Which DG families has this loop never touched? Rafi 2024 (ID 146) gives the taxonomy;
  we have covered augmentation/randomization and normalization, barely touched disentanglement,
  and not touched meta-learning at all. An audit is cheaper than another single-method search.
- **Q26.** Does BN-affine-only fine-tuning suffice per year?""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 17 | 2026-08-18 | Search 29 - SDG sweep with correct vocabulary | 145-146 | "
       "FOSMix (TGRS) refines the frequency-mixing plan: keep segmentation-essential frequencies, "
       "randomize the rest - a blunt FDA swap could destroy crown texture at 7.5cm. Rafi 2024 "
       "survey gives the family map we lacked. FIFTH convergence on style/content, now at "
       "architecture level (IN removes style, BN preserves discriminability). SDG literature "
       "independently names PHENOLOGY and ILLUMINATION as primary RS shift causes - both unsearched |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
