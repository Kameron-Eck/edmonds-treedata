import io
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
IF 2020 CoE FOLLOWED REGIONAL PRACTICE (not yet confirmed), then our ONE hand-labelled year
was labelled on imagery where DECIDUOUS CROWNS ARE BARE. That is a PHYSICAL explanation for
findings we have treated as modelling defects:
  * "conifer-only-label blind spot" -> deciduous crowns not in the labelling imagery at all
  * scrub recall .25 vs forest .68  -> deciduous scrub bare, conifer forest visible
  * recall .16 (0-5m) -> .93 (30m+)  -> short crowns skew deciduous yard/ornamental
  * 8/8 missed stands suburban, "purple-leaf LOW-NDVI" -> purple-leaf = deciduous = bare in spring
  * FINDING 3 IS THE TELL: 9 years span IoU .49-.76 yet recall stays pinned .51-.78. That is
    exactly what you see when the limit is WHAT THE IMAGERY CONTAINS, not the model.
INDEPENDENT SUPPORT - iteration-18 GRVI screen re-read:
  both NAIP years (spec LEAF-ON) rank top-5 of 17 by green-excess; the bottom SIX are all
  King County or City of Edmonds (consortium, spec LEAF-OFF); 2020 is 4th LOWEST of 17.
NOT PROVEN:  confirmed = the consortium SPEC and that KC 2012/2015 were spring flights.
         NOT confirmed = that 2020 CoE followed it, nor the season of Snoh 2016/2021s.
         GRVI remains confounded with colour balance (iteration 18 caveat stands).
         RECOVERABLE: King County's photo-centre index layer carries per-exposure ACQ_DATE
         and UTC_TIME. One data pull converts hypothesis to fact.
IF IT HOLDS, IT REORDERS THE PROJECT:
  * the blind spot is a DATA problem, not a model problem - no architecture, augmentation,
    domain generalization or foundation model recovers deciduous crowns from leaf-off pixels.
    Retrospectively explains why 30 iterations of modelling literature kept concluding model
    quality was not the constraint.
  * right fix = LABELS ON LEAF-ON IMAGERY (NAIP years, or Snoh if leaf-on), NOT better
    training on 2020.
  * any cross-era comparison mixing leaf-off with leaf-on measures PHENOLOGY, not canopy.
    Very likely the source of the 2026-08-19 sign disagreement (NDVI +2.45pp vs C-CAP -1.72pp).
  * the height curve may be substantially a DECIDUOUS-FRACTION curve.
files:   Scripts/litwatch_robustness.md (iteration 45) - Literature_Tracker.xlsx ID 194
         Scripts/phase4_qc_turnover.py (new, iterations 43-44) -
         phase4/qc/turnover_ccap_2016_2021.txt, turnover_ndvi_2016_2021s.txt
next:    (1) CONFIRM THE 2020 SEASON. King County photo-centre index (ACQ_DATE/UTC_TIME), the
         ortho metadata, or ask the City. Everything else is downstream. (2) season-label all
         18 acquisitions. (3) recall-by-height on a LEAF-ON year (2019n/2022n, rasters already
         scored) vs a leaf-off year - tests whether the height curve is a deciduous curve.
gotcha:  leaf-off flights are also LOW SUN ANGLE, so the shadow axis and the phenology axis are
         CORRELATED, not independent. Do not treat them as separate confounds.

"""
p = r'G:/My Drive/treedata/Scripts/CHATLOG.md'
s = io.open(p, encoding='utf-8').read()
a = "## 2026-08-18  AGENCY IS NOT SENSOR"
i = s.index(a)
io.open(p,'w',encoding='utf-8').write(s[:i] + entry + s[i:])
print("CHATLOG entry inserted")
