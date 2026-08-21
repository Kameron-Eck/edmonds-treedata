import io, re
p = r'G:/My Drive/treedata/Scripts/CHATLOG.md'
s = io.open(p, encoding='utf-8').read()
entry = """## 2026-08-19  ** THE MODEL IS BETTER THAN ITS NUMBERS ** - calibration, not capability, is binding
scope:   loop iterations 73-77. Measurement + code reading. Nothing deployed, no plan edit.
** FINDING 1 - MOST OF THE CROSS-YEAR RECALL WANDER IS THE OPERATING POINT (Q121). **
         One recipe (_citywide_rgb), one reference (C-CAP), one footprint (161,052 pts, 98.9%),
         8 years. Only the operating point is varied.
           recall spread @ FIXED thr 0.5      0.1827
           recall spread @ MATCHED call .30   0.0721      = 61% REDUCTION
         Mechanism: thr 0.5 calls 22.0%-30.5% of the city depending on year. A fixed threshold
         is NOT a fixed operating point.
         RESIDUAL IS INTERPRETABLE where finding 3's 0.28 wander was not:
           2000 .6454 · 2002 .6541          <- the two coarsest (~40 cm true GSD)
           2005-2021 .6974 .7052 .7069 .7174 .7155 .7086   <- ALL WITHIN 0.020
         across 16 years, 3 providers and a 4x resolution change.
         CREDIT: the 2026-08-18 recipe-controlled run is column two here. This adds the SECOND
         control, not the first. The two together account for most of finding 3.
         ANOMALY: 2007 gives IDENTICAL recall at cr .20 and .25 (.6189) -> degenerate/saturated
         raster. DO NOT quote the cr=.20 row until understood (Q133).
** FINDING 2 - THE MODEL DOES NOT RELY ON COLOUR, AND IS MORE STABLE THAN ITS INPUTS (Q135). **
           year  AUCmodel  AUCbright  AUCgrvi  gain   corr(m,grvi)
           2000    .8760     .6333     .5927  +.2427     +.1882
           2005    .9134     .7170     .6941  +.1964     +.4737
           2009    .9195     .6847     .7061  +.2348     +.4745
           2013    .9125     .6881     .7273  +.2243     +.5428
           2021    .9150     .6662     .5453  +.2488     +.0755
           RANGE   0.044     0.084     0.182
         MODEL AUC VARIES 4x LESS THAN THE COLOUR STATISTICS OF ITS OWN INPUTS. Threshold-free,
         so no calibration choice is doing the work.
         2021 IS DECISIVE: worst GRVI of any year AND lowest model-GRVI correlation (+.0755,
         ~zero), yet model AUC .9150 - its second best. With 2000 (colour saturated, model still
         .8760) that is TWO independent extreme cases, not an inference from correlations.
         ONLY DIP IS 2000 = THE COARSEST YEAR. 2021's colour is worse and does not dip.
         => RESOLUTION separates the years, COLOUR DOES NOT. Same asymmetry finding 1 found.
** FINDING 3 - THE REFRAMING NUMBER: AUC .876-.920 vs MATCHED RECALL .645-.717. **
         The model's RANKING is strong and stable; only WHERE THE LINE IS DRAWN is weak.
         Q132 PREMISE CONFIRMED IN CODE: phase3_semantic_dev.py:1722
           canopy_area = total_canopy_px * pixel_area
         The AREA SERIES - the deliverable - is MAP-COUNT off a thresholded mask, with
         binary_closing applied first, which inflates it further by a threshold-dependent amount.
         phase4_qc_score.py:83 already calls its threshold source "the (circular) eval CSV".
         THREE INDEPENDENT LINES CONVERGE (GRVI drift it.72, operating point it.73, AUC gap
         it.76/77): THIS PROJECT'S MODEL IS BETTER THAN ITS NUMBERS, AND THE NUMBERS ARE
         DOMINATED BY CALIBRATION AND A MAP-COUNT ESTIMATOR.
decided: nothing deployed. Highest-value fix identified (Q136): estimate area from a REFERENCE
         SAMPLE, not by counting thresholded pixels. NOT new research - the Olofsson/CEOS
         machinery is already in the tracker and P3's sample design already exists.
         Colour-comparability problems (it.72/74/75) are REAL BUT NOT BINDING - the model
         already largely ignores the channel they damage.
lit:     +6 papers, IDs 204-209, searches 59-60, DOI/arXiv verified.
           204 Canty & Nielsen 2008 RSE - IR-MAD, invariant to gain/offset
           205 Ryadi 2023 Sensors - cross-sensor relaxation-based normalisation
           206 Chen 2023 Appl.Sci - pseudo-invariant POLYGONS (we have roofs + impervious)
           207 Geirhos 2019 ICLR - CNNs texture-biased. Unifies transfer-vs-resolution asymmetry.
           208 arXiv 2509.20234 (2025) - DIRECTLY CONTRADICTS 207. Read BEFORE leaning on it.
           209 arXiv 2509.11355 (2025) - frequency regularisation for shape bias (conditional)
         NOTE Q130/Q134 ANSWERED NEGATIVE BY MEASUREMENT: AUC is invariant under ANY monotone
         transform, so IR-MAD/histogram matching CANNOT rescue GRVI where AUC ~ 0.5 - and that
         is 2000 (.5927), 2019 King (.5835) and 2021 King (.5453). Normalisation is still worth
         doing for cross-year THRESHOLD comparability, but NOT to make greenness work.
files:   Scripts/litwatch_robustness.md (it.73-77 + Q131-Q136)
         Literature_Tracker.xlsx (210 papers, 60 searches)
         scratchpad, all READ-ONLY: sampler.py (162,829-pt grid), q121c.py, q131b.py, q134.py,
         q135.py, cast2.py, chk1936.py
next:    Q136 area-from-reference-sample. Then channel ablation (needs GPU) for Q98.
gotcha:  NO RASTER IN THIS PROJECT HAS OVERVIEWS (ovr=[] everywhere) and the prob rasters are
         ROW-STRIPED (block=(1,18944)), so every out_shape/decimated read silently reads the
         WHOLE file. Two runs stalled ~40 min at 3.5 GB before this was found. Use
         scratchpad/sampler.py point sampling instead - seconds, not tens of minutes.
         Building overviews would speed every future QC run but writes GB of sidecars on G:,
         so that is Kam's call.

"""
m = re.search(r'^##\s*(?=\d{4}-\d{2}-\d{2})', s, re.M)
assert m
s = s[:m.start()] + entry + s[m.start():]
io.open(p, 'w', encoding='utf-8').write(s)
print('CHATLOG updated')
