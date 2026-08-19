import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 50 - ACCURACY ASSESSMENT *OF CHANGE* - IDs 187-188
Search 49 showed our accuracy figures describe the canopy class when a change product is governed
by the change class. This search finds that the community has already written the document.

**THE PROTOCOL EXISTS, IT IS CURRENT, AND IT COVERS CHANGE (ID 187).**
*Land Cover and Change Map Accuracy Assessment and Area Estimation Good Practices Protocol,
Version 1.1 (2025)* - CEOS Working Group on Calibration and Validation, Land Product Validation
Subgroup. 187 pages, DOI-registered, edited by Tyukavina, Stehman, Foody, Bontemps, Komarova,
Tsendbazar and Nickeson.

**It is written by the authors whose individual papers Phase 4 assembled one at a time.** Stehman,
Foody, Olofsson, Radoux and Woodcock are already in our tracker as IDs 69-76, 78-80 and 87. This
consolidates that machinery into one standard - and unlike Olofsson 2014 (ID 69), it addresses
**CHANGE maps specifically**, which is exactly the gap Search 49 exposed.

**Practical consequence:** our accuracy reporting should be written against this document rather
than assembled from papers. Adopting a published community standard also makes our figures
comparable to other work, which a bespoke protocol never will be - the same argument that favoured
TimeSync over a custom interpretation tool (Q58). Two standards, both already written, both
currently being reinvented in our plan.

**AND A DESIGN CHOICE WE HAVE BEEN CONFLATING (ID 188, Stehman 2012).**
Because change is rare, the change stratum is normally over-sampled - but *which* over-sampling
rule you choose determines which question the sample can answer:

| objective | allocation |
|---|---|
| estimate the AREA of change | Neyman optimal |
| estimate USER'S ACCURACY of change | equal allocation |

**These compete.** An allocation tuned for one degrades the other. So P3 must decide whether it
exists to say *how accurate our change map is* or *how much canopy actually changed*. Those are
different studies, and this loop - across Searches 40, 41, 47 and 49 - has been treating them as
one. Adding it to the pile of design decisions that must precede `--step design`:

1. strata: model-output / agreement / CHM band (Q33, Search 9)
2. paired vs independent, and the blind subset (Searches 41-42)
3. **area-optimal vs accuracy-optimal allocation (this search)**
4. which epoch pairs (Q59, blocked on acquisition dates)
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q69.** Is P3 an ACCURACY study or an AREA study? The allocations compete (ID 188): Neyman
  optimal for area of change, equal allocation for user's accuracy of change. The loop has assumed
  one sample answers both. It cannot, and the choice determines the design.
- **Q70.** Should our accuracy reporting simply follow the CEOS protocol (ID 187) rather than be
  assembled from individual papers? It is current, DOI-registered, covers change maps specifically,
  and is written by the authors already in our tracker. This is the second community standard the
  loop has found us reinventing - the first was TimeSync (Q58).

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

**NOTE ON CADENCE (2026-08-18):** ten loop fires queued while iteration 38 was running - the
10-minute cron interval is shorter than an iteration takes. Fires are backing up rather than
pacing work. Recommend a longer interval, or dynamic pacing.

1. **Read the CEOS protocol (ID 187) properly** - 187 pages that likely answer several open queue
   items at once. Higher value than another single-paper search.
2. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
4. **Canopy AREA turnover vs tree-COUNT mortality** - the Q50 counterweight.
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **Instance-norm / whitening for style removal.**
7. **Shadow masking as IGNORE vs removal.**
8. **Ladder-side-tuning and cheap foundation-model adaptation.**
9. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.
10. **How the Landsat/MODIS harmonization community validates a multi-decade series.**

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 38 | 2026-08-18 | Search 50 - accuracy assessment OF CHANGE | 187-188 | "
       "THE PROTOCOL ALREADY EXISTS: CEOS WGCV LPV *Land Cover and CHANGE Map Accuracy Assessment "
       "and Area Estimation Good Practices Protocol* v1.1 (2025), 187pp, by the same authors Phase 4 "
       "cited one at a time - and it covers CHANGE maps, the gap Search 49 exposed. Second community "
       "standard we are reinventing (first was TimeSync). Stehman 2012: area-optimal and "
       "accuracy-optimal allocations COMPETE - P3 must choose which question it answers (Q69) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
