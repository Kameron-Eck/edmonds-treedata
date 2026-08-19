import io, re
p = r'G:/My Drive/treedata/Scripts/CHATLOG.md'
s = io.open(p, encoding='utf-8').read()

entry = """## 2026-08-19  TWO REFUTATIONS AND A DEPLOY WARNING - what is NOT causing the overhang gap
scope:   loop iterations 67-69, all measurement, nothing deployed, no plan file edited.
did:     (1) Q118 HEIGHT AND OVERHANG ARE INDEPENDENT, NOT THE SAME THING.
           Recall by CHM band split by surface beneath, 2016 vs C-CAP city.
           staircase SURVIVES on pervious alone: 0-2m .1206 -> 30+m .9421, spread +.8215
           staircase on impervious:              2-5m .0282 -> 30+m .7509, spread +.7227
           impervious penalty is roughly CONSTANT above 5 m (-.19 to -.29), so the two
           deficits are ~ADDITIVE. Both need fixing separately.
           WORST CELL: 2-5 m OVER IMPERVIOUS = .0282. Model finds under 3% of it. That is
           street/yard trees beside driveways - the canopy a tree ordinance is about.
           And the impervious penalty is NOT a short-tree artefact: -.19 even above 30 m.
         (2) Q119 THE CORRECTED MODEL'S OVERHANG GAIN IS AN OPERATING-POINT ARTEFACT.
           prob_2016 vs prob_2016_corrected, COMMON footprint, 321,651 C-CAP canopy cells.
           at thr .509      recall .6279 -> .8533   over-imp .3183 -> .5612   LOOKS GREAT
             but call rate on C-CAP non-canopy .0493 -> .1725  (TRIPLES)
           at MATCHED overall recall (thr .835)
                            recall .6279 -> .6296   over-imp .3183 -> .3070   GAIN REVERSES
             gap -.3739 -> -.3895 (WIDER); worst cell .0282 -> .0366 (nothing)
             matched gap WORSE where it matters: -.076 at 2-5m, -.050 at 5-10m
           IT MOVED ITS OPERATING POINT, IT DID NOT LEARN OVERHANG.
           CAVEAT STATED, not buried: corrected from NIR+CHM but scored against C-CAP, so
           this is an AGREEMENT statement not a TRUTH statement. Q120 settles it.
         (3) Q122 SHADOW REFUTED AS THE MECHANISM.
           Liu 2023 RS 15:519 says U-Net specifically suffers shadow omission - our arch,
           our symptom. Shadow falls NORTH, contrast is isotropic -> separable by geometry.
           bearing from nearest building, 2016:  N-S = +.0354 (10m) / +.0221 (20m)
           north is BETTER. Holds within matched geometry: faces N .5071 vs S .4401,
           corners +.020, E-W control flat. SIGN ERROR against the hypothesis.
           FLAGGED NOT READ INTO: cardinal .44-.51 vs diagonal .58-.61, spread .123 = 5x
           the N-S effect. Axis-aligned footprints, wall faces vs corner wedges. Artefact.
decided: nothing deployed. RADIOMETRIC FIXES RULED OUT (shadow compensation, histogram
         matching, illumination normalisation). With corrected labels also ruled out, the
         candidate list is down to HEIGHT CHANNEL or NIR BAND - v045/v046 aux-height on the
         impervious split is now the leading untested experiment.
lit:     +3 papers, IDs 195-197, Phase 6 Search 56, all DOI-verified via Crossref:
           195 Techapinyawat 2024 CACAIE 10.1111/mice.13277 - retrieves CANOPY-COVERED
               IMPERVIOUS SURFACES by post-classification. Exact inverse of our failure mode.
           196 Liu 2023 RS 15(2):519 10.3390/rs15020519 - the U-Net shadow claim above.
           197 Yoo 2026 RS 18(12):1899 10.3390/rs18121899 - transferable NAIP canopy
               framework. NAIP is our 2019n/2022n. External benchmark we currently lack.
files:   Scripts/litwatch_robustness.md (it.67-69 + Q120-Q123)
         Literature_Tracker.xlsx (197 papers, 56 searches)
         scratchpad only: height_by_surface.py, q119.py, q122.py - all READ-ONLY, none
         write to phase4/qc
next:    Q123 RELIEF DISPLACEMENT - a genuine blind spot. Ortho displaces elevated objects
         radially from nadir AND THE DISPLACEMENT SCALES WITH HEIGHT, which is the exact
         axis our staircase runs along. C-CAP is stereo-DSM derived and may be nearer
         true-ortho, so mask and reference may be misregistered AS A FUNCTION OF HEIGHT.
         Tracker search for off-nadir / view angle / BRDF / orthorectif returns 0 of 197.
         Then Q121 (running): re-score the cross-year series at MATCHED CALL RATE. Finding
         3's .50-.78 wander has never been checked against the it.68 artefact.
gotcha:  Q121 EVERY per-year threshold is calibrated separately, so ANY cross-year recall
         comparison in this pipeline is confounded until re-scored at matched operating
         point. it.68 shows the size of the effect: +0.225 of pure nothing.
         `python` is not on PATH here, only `py -3` - a heredoc starting `python -` fails
         silently mid-chain and the NEXT command still runs, so check for the alias error.
         Crossref titles carry U+2010; console is cp1252; sanitize to ASCII before print.

"""
m = re.search(r'^##\s*(?=\d{4}-\d{2}-\d{2})', s, re.M)
assert m, 'no dated entry header found'
s = s[:m.start()] + entry + s[m.start():]
io.open(p, 'w', encoding='utf-8').write(s)
print('CHATLOG updated, inserted at offset', m.start())
