import io, re
p = r'G:/My Drive/treedata/Scripts/CHATLOG.md'
s = io.open(p, encoding='utf-8').read()
entry = """## 2026-08-19  ** GRVI IS NOT COMPARABLE ACROSS SENSORS ** + 1936 is an empty file
scope:   loop iterations 70-72. Measurement + inventory. Nothing deployed, no plan edit.
** THE FINDING **  GRVI over the SAME GROUND in every acquisition, 2400 px window:
           frac>.02 = share of pixels a naive GRVI vegetation test calls green
           2000 King .8027 | 2002 .5029 | 2005 .4782 | 2007 .4016 | 2009 .6237
           2012 .6268 | 2013 .3463 | 2015 .2745 | 2017 .1877 | 2019 .1146
           2021 .1344 | 2023 .1541 | 2016 Snoh .6928 | 2019 NAIP .8919 | 2022 NAIP .7822
         DECISIVE PAIR: 2019 King .1146 vs 2019 NAIP .8919. SAME YEAR, SAME GROUND, SAME
         SEASON, differing by 0.78. Cannot be vegetation, phenology, growth or loss. It is
         sensor + processing colour balance and nothing else.
         AND THE KING SERIES DRIFTS MONOTONICALLY: .80 (2000) -> .35 (2013) -> .11 (2019),
         GRVI mean crossing positive-to-negative around 2017. ANY cross-year GRVI diagnostic
         on this series reports a large steady CANOPY DECLINE THAT IS PURE ARTEFACT.
         DAMAGES OUR OWN WORK: the leaf-off / canopy-rendering signature compared low-
         greenness fractions BETWEEN years. Those comparisons are NOT SAFE. The WITHIN-year
         use (canopy-masked pixels vs the rest of the same image) survives, because the cast
         is global. That distinction is the whole of what is left standing.
killed:  cross-year GRVI comparisons. Do not re-quote them (Q129 = trace what used them).
** CORRECTION **  1936_king_rgb.tif CONTAINS NO IMAGE DATA OVER EDMONDS.
         I reported it in it.71 as "clipped at the bright end, bright detail destroyed".
         WRONG. Nine probe windows across the city are ALL CONSTANT: mean 253.0 std 0.00
         min=max=253 in the south/centre, 0.0 in the north. A georeferenced EMPTY SHELL.
         The "p99=255 clipping" was fill value in a whole-raster downsample.
         WHY: these are KING COUNTY mosaics and EDMONDS IS IN SNOHOMISH COUNTY. A 1936 King
         survey does not reach this far north. INDEPENDENT BONUS: 2000's northern probes are
         also all-zero, so the known north-coverage gap is A COUNTY LINE, not a footprint quirk.
         1998 IS REAL (std 29-44 at all nine probes, whole city) and single-band, on the
         IDENTICAL grid to 2000 -> still the clean panchromatic pilot with a near-
         contemporaneous RGB control. Prize is 2 extra years, not 60.
did:     also (it.71) 1936/1998 are SINGLE-BAND despite _king_rgb names; every other
         _king_rgb is 3-band and phase1_preprocess.py assumes it. Dormant only because grep
         finds 1936/1998 in NO config. They share the 2000 grid exactly (18944x26880) so
         co-registration looks already done - but their GSD is INHERITED FROM THAT GRID, not
         measured from film. Do not quote grid spacing as resolution.
         (it.70) RELIEF DISPLACEMENT, 0 of 197 papers covered it. A conventional ortho is
         rectified on a BARE-EARTH DTM, so only the BASE of a tree lands correctly; everything
         above ground is displaced radially PROPORTIONAL TO HEIGHT. d=(h/H)*r -> a 20 m crown
         500 m off nadir at 3 km = 3.3 m = 33 px at King's true 10 cm GSD. Runs along the SAME
         axis as our staircase but CUTS AGAINST it (tall-band recall is our highest, .9421), so
         it cannot be manufacturing the staircase. BIGGER RISK IS THE DELIVERABLE: 17
         acquisitions = 17 frame layouts = 17 displacement fields -> SPURIOUS CHANGE on tall
         crowns near buildings (Q125).
** INFRASTRUCTURE **  NO RASTER IN THIS PROJECT HAS OVERVIEWS (ovr=[] on every file checked),
         so every out_shape / decimated read silently reads the ENTIRE file. The prob rasters
         are also ROW-STRIPED, block=(1,18944), not tiled. Two QC runs stalled at 3.5-3.7 GB
         for ~40 min before I found this. FIX ADOPTED: scratchpad/sampler.py builds a 162,829-
         point systematic grid inside the city and samples rasters at points - seconds, not
         tens of minutes. Building overviews would help every future QC run but creates GB of
         sidecar files on G:, so that is Kam's call, not mine.
lit:     +9 papers, IDs 195-203, Phase 6 searches 56-58, all DOI-verified via Crossref.
           195 Techapinyawat 2024 CACAIE - retrieves CANOPY-COVERED IMPERVIOUS SURFACES
           196 Liu 2023 RS 15:519 - U-Net specifically suffers SHADOW omission (tested, refuted)
           197 Yoo 2026 RS 18:1899 - transferable NAIP canopy framework (NAIP = our 2019n/2022n)
           198 Gharibi 2018 RS 10:581 - true ortho from frames + LiDAR; names the DTM defect
           199 Wagner 2024 RSE 302:114099 - U-Net regression, 60 cm NAIP -> LiDAR CHM, statewide.
               This is our v045/v046 aux-height experiment ALREADY DONE at scale.
           200 Chen 2014 ISPRS XL-3:67 - double-mapping; spurious multitemporal change
           201 Mboga 2020 ISPRS J 167:385 - FCN land cover from PANCHROMATIC historical frames
           202 Tian 2025 ISPRS Ann X-G:885 - NO method works on panchromatic alone; uses DL
               COLORIZATION as the bridge. Absent from all 200 prior rows.
           203 Kostrzewa 2025 PE&RS - CNN LULC from historical aerial (provisional, abstract unread)
files:   Scripts/litwatch_robustness.md (it.70, 70c, 71, 72 + Q123-Q130)
         Literature_Tracker.xlsx (204 papers, 58 searches)
         scratchpad only, all READ-ONLY: sampler.py, cast2.py, chk1936.py, q119.py, q122.py,
         height_by_surface.py, q121c.py, q128.py
next:    Q121 running (cross-year recall at MATCHED CALL RATE, point-sampled). Then Q128 -
         model DISAGREEMENT as a label-free reliability proxy: 2000/2002/2013/2015 each carry
         4-5 independently trained variants, and Baek 2022 (ID 153) says mutual agreement
         estimates OOD accuracy. Validate against measured recall before trusting it.
gotcha:  a substring match on a filename is NOT evidence - EDM_0001936.jpg is crown 0001936,
         not the year 1936, and I briefly claimed 1936 crops existed on that basis.
         piping a background job through grep BUFFERS all output until exit; use `py -3 -u
         script.py > out.txt 2>&1` instead so partial progress is readable.
         `python` is not on PATH, only `py -3`.

"""
m = re.search(r'^##\s*(?=\d{4}-\d{2}-\d{2})', s, re.M)
assert m
s = s[:m.start()] + entry + s[m.start():]
io.open(p, 'w', encoding='utf-8').write(s)
print('CHATLOG updated')
