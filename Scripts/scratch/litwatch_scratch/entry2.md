## 2026-08-18  ASSESSMENT — P3 AS SCOPED CANNOT ANSWER THE BLOCKING QUESTIONS (250 pts too few)
goal:    Kam asked: assess what we know / what we need to know. Synthesis over STATE +
         honest-measurement-overhaul.md + the 105-paper tracker. No new measurement.
did:     Reports/Measurement_Validity_Assessment_2026-08-18.md. Unknowns ordered BY THE
         DECISION EACH BLOCKS (U1-U8), not by topic. Power math COMPUTED, not gestured at.
THE FINDING — P3 at 250 pts/yr answers the question that is NOT in doubt and cannot
         answer either question that IS:
  * arbitrate C-CAP 29.5% vs NDVI-ref 37.7% (gap 8.2pp, midpoint 33.6%):
      n=250 -> +/-5.9pp, CI [27.7,39.5] = COVERS BOTH REFS. n=400 -> still covers both.
      n=510 needed to separate at the midpoint. And the midpoint is exactly what
      "the refs BRACKET truth" predicts. -> 250 leaves the question open.
  * per-band recall: 3 strata -> 83/stratum -> +/-10.7pp. 4 strata -> +/-12.3pp.
      8 strata (4 CHM band x 2 agreement — the design that would split the U3 confound)
      -> 31/stratum -> +/-17.6pp. 5-15m band cannot be pinned better than ~+/-12pp.
  * confirm the height effect (.36 @5-10m vs .83 @20-25m): significant at n_h=20.
      BUT WE ALREADY KNOW THIS, replicated. Spending the human budget to re-confirm the
      one thing not in doubt is the failure mode to avoid.
NEW/UNDER-USED KNOWN surfaced from STATE (absent from the 5 headline findings):
  8/8 missed stands = SUBURBAN (yard/ornamental, many purple-leaf low-NDVI), ZERO
  deciduous forest. -> HEIGHT AND LAND-USE CONTEXT ARE CONFOUNDED. Short trees live in
  yards, tall trees in stands. Unknown share of the height staircase is a suburban-vs-
  forest staircase in a height costume. CHEAP TEST (local, no GPU, inputs all exist):
  recall by height band WITHIN each P2 agreement partition. Staircase survives inside
  both-agree = real height effect. Flattens = C-CAP suburban over-count.
decided: 7 proposed AMENDMENTS to honest-measurement-overhaul.md, NOT applied — Kam signs off.
         (1) write the canopy definition FIRST (min height / crown area / shrub-vs-short-
         tree / continuous-vs-binary). No definition = the 250-pt run is a THIRD OPINION,
         not an arbiter (Gutierrez-Velez ID 81: cross-product disagreement is manufactured
         by different cut points on one continuous variable).
         (2) run the FREE instruments before spending human hours: recall-by-band within
         P2 partitions (U3) · miss-depth per yr one recipe (U4) · Foody-2022 LATENT CLASS
         on ccap x ndvi-ref x model (U2, no gold standard needed) · Clark-2023 stratified
         patch re-sample (U5). Any may change what the human sample must be.
         (3) re-derive n FROM THE QUESTION: ~500+ in 2016 alone beats 250x3 spread thin.
         (4) response design: primary + ALTERNATE/fuzzy label + explicit SHORT-TREE-vs-
         SHRUB call. Plan currently EXCLUDES Unsure — that discards exactly the pixels the
         refs disagree about. Wickham ID 78: NLCD OA 77.5% primary-only -> 87.1% with
         alternate = 10pp from a SCORING CONVENTION, bigger than our whole model range.
         (5) duplicate-interpreted subset designed IN (Stehman ID 100 / Xing ID 101) —
         cannot be added later. (6) 20-30 pt 2000 FEASIBILITY block, interpreted twice,
         before production (Reis ID 103: 3 interpreters fully agreed on <40% of historical
         px; at 60cm no-NIR the short-tree/shrub call may be beyond one interpreter).
         (7) strata decision resolves BEFORE --step design. model-output / agreement /
         CHM-band strata are THREE DIFFERENT STUDIES; Stehman ID 72 permits any, not all
         three on this budget.
killed:  "your recall is probably optimistic" (my own claim, prev turn) — WRONG as a blanket.
         Direction is PER REFERENCE: vs C-CAP the suburb over-count inflates the recall
         denominator -> measured recall is PESSIMISTIC; vs the NDVI ref (shared lineage,
         and post-overlay it also supplied labels) errors correlate -> OPTIMISTIC. That is
         the quantitative form of "the refs bracket truth".
files:   Reports/Measurement_Validity_Assessment_2026-08-18.md (new)
         honest-measurement-overhaul.md NOT edited — amendments are proposals only.
next:    Kam signs off on the amendments. Then U1 (definition) -> the three free local
         instruments -> re-derive P3 n. Mechanical chain unchanged: P1 Colab stage 1 ->
         2022 citywide raster -> P3 --step design.
caveat:  power table uses SRS variance = conservative. Recompute with Olofsson/Wagner-
         Stehman stratified variance once stratum weights known. p=.5 worst case.

