import io, re

entry = """## 2026-08-19  ** LEAF-OFF ** - the acquisition SPEC may explain the conifer-only blind spot
goal:    lit-watch loop, iteration 45. Standing top action was "recover acquisition dates".
         Found something better: the published acquisition SPECIFICATIONS.
did:     Searched King County / Puget Sound consortium and NAIP acquisition specs.
         -> Literature_Tracker ID 194. Re-read the iteration-18 GRVI screen against them.
THE TWO SPECS ARE OPPOSITE:
  * PUGET SOUND REGIONAL ORTHOPHOTO CONSORTIUM (88 participants, King County lead manager -
    the source of our King imagery): "acquisition was to occur during LEAF-OFF season while
    ground conditions were free of snow and smoke". 2012 flown March-May "with the intent of
    representing leaf-off conditions". 2015 acquired "in the spring".
  * NAIP: flown "during the agricultural growing season, or LEAF-ON conditions".
  -> OUR ARCHIVE MIXES LEAF-OFF AND LEAF-ON AND NOTHING IN THE PIPELINE ACCOUNTS FOR IT.
IF 2020 CoE FOLLOWED REGIONAL PRACTICE (not yet confirmed), our ONE hand-labelled year was
labelled on imagery where DECIDUOUS CROWNS ARE BARE. Physical explanation for findings we have
treated as modelling defects:
  * "conifer-only-label blind spot" -> deciduous crowns not in the labelling imagery at all
  * scrub recall .25 vs forest .68  -> deciduous scrub bare, conifer forest visible
  * recall .16 (0-5m) -> .93 (30m+) -> short crowns skew deciduous yard/ornamental
  * 8/8 missed stands suburban, "purple-leaf LOW-NDVI" -> purple-leaf = deciduous = bare in spring
  * FINDING 3 IS THE TELL: 9 years span IoU .49-.76 yet recall stays pinned .51-.78. That is
    what you see when the limit is WHAT THE IMAGERY CONTAINS, not the model.
INDEPENDENT SUPPORT - iteration-18 GRVI screen re-read: both NAIP years (spec LEAF-ON) rank
  top-5 of 17 by green-excess; the bottom SIX are all King County or City of Edmonds
  (consortium, spec LEAF-OFF); 2020 is 4th LOWEST of 17.
NOT PROVEN: confirmed = the consortium SPEC, and that KC 2012/2015 were spring flights.
         NOT confirmed = that 2020 CoE followed it, nor the season of Snoh 2016/2021s.
         GRVI stays confounded with colour balance (iteration-18 caveat stands).
         RECOVERABLE: King County photo-centre index carries per-exposure ACQ_DATE + UTC_TIME.
IF IT HOLDS, IT REORDERS THE PROJECT:
  * blind spot is a DATA problem not a model problem - no architecture, augmentation, domain
    generalization or foundation model recovers deciduous crowns from leaf-off pixels.
  * right fix = LABELS ON LEAF-ON IMAGERY (NAIP years, or Snoh if leaf-on), NOT better training
    on 2020.
  * any cross-era comparison mixing leaf-off with leaf-on measures PHENOLOGY, not canopy.
  * the height curve may be substantially a DECIDUOUS-FRACTION curve.
also this session (lit-watch iterations 43-44), NEW Scripts/phase4_qc_turnover.py:
  * C-CAP 2016 vs 2021: discordance 11.16%, net -1.72pp LOSS, implied 5.33%/yr canopy loss -
    which EXCEEDS published street-tree mortality, so most of it is product revision not trees.
  * NDVI ref 2016 vs 2021s (same source, same sensor): discordance 11.14%, net +2.45pp GAIN.
  * -> THE TWO REFERENCES DISAGREE ON THE SIGN OF CHANGE. Neither can say whether Edmonds
    gained or lost canopy 2016-2021. C-CAP dominated by vintage revision, NDVI by phenology
    (its CHM is static across both dates, so the whole signal is greenness).
  * BUG FOUND+FIXED in that script: 0 = nodata in C-CAP but NON-VEGETATED in the NDVI refs.
    First run gave a false 0.97% discordance / 90.6% stable-canopy. --zero-is-data flag added.
files:   Scripts/litwatch_robustness.md (iterations 43-45) - Literature_Tracker.xlsx ID 194
         Scripts/phase4_qc_turnover.py - phase4/qc/turnover_{ccap_2016_2021,ndvi_2016_2021s}.txt
next:    (1) CONFIRM THE 2020 SEASON - photo-centre index, ortho metadata, or ask the City.
         Everything else is downstream. (2) season-label all 18 acquisitions. (3) recall-by-height
         on a LEAF-ON year (2019n/2022n, rasters already scored) vs a leaf-off year.
gotcha:  leaf-off flights are also LOW SUN ANGLE, so the shadow axis and the phenology axis are
         CORRELATED, not independent. Do not treat them as separate confounds.

"""

p = r'G:/My Drive/treedata/Scripts/CHATLOG.md'
s = io.open(p, encoding='utf-8').read()

m = re.search(r'^.*LOG\s+\(newest first\).*$', s, re.M)
assert m, "LOG header not found"
i = s.index('\n', m.end()) + 1
while s[i] == '\n':
    i += 1

io.open(p, 'w', encoding='utf-8').write(s[:i] + entry + s[i:])
print("inserted at char", i)
nxt = re.search(r'^## .*$', s[i:i+3000], re.M)
print("entry now precedes:", nxt.group(0)[:70] if nxt else "?")
