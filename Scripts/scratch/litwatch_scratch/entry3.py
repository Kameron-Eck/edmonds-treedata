import io

entry = """## 2026-08-18  AGENCY IS NOT SENSOR - domain screen refutes the per-(sensor x era) grouping
goal:    Kam: "Edmonds and King County use EagleView in the later years, and King County
         switched contractors many times. There may be more than a few different sensors."
         Test it. Free - imagery_stats/imagery_summary.txt already holds per-band mean/std.
did:     NEW Scripts/phase4_qc_domain_cluster.py - clusters the 17 acquisitions on their RGB
         radiometric signature (mean+std per band, standardised). No imagery opened, no GPU.
         -> phase4/qc/domain_cluster.txt / .csv
RESULT - KAM IS RIGHT, AND IT BREAKS THE ANCHOR DESIGN:
  * NEAREST NEIGHBOUR SHARES AGENCY ONLY 8/17 = 47%. That is chance. Our per-(sensor x era)
    anchors are keyed on AGENCY, which is not the domain axis.
  * EAGLEVIEW SIGNATURE VISIBLE: 2017 (City of Edmonds, 7.5cm) and 2019 (King County, 14.9cm)
    are each other's NEAREST NEIGHBOURS at dist 0.34 - closest cross-agency pair in the set,
    closer than most same-agency pairs. Different agency, different GSD, near-identical
    radiometry = shared contractor.
  * KING COUNTY IS NOT ONE DOMAIN. Its 9 images split >=3 ways: {2005,2007} 29.9cm pair;
    2009 sits with {2021,2023}; {2000,2013,2015,2019} elsewhere.
  * 2024 IS A SEVERE OUTLIER - nearest-neighbour dist 4.96 vs next-largest 1.09, singleton
    cluster at every k. Band means 144/154/146 vs typical 80-110. CHECK BEFORE USING 2024.
    Different product? different processing? unknown.
  * CATALOG ALSO SHOWS FOUR AGENCIES not three - City of Edmonds (2017/2020/2022/2024) was
    missing from our standing project description. 2020, the ONLY labelled year, is CoE.
decided: stop ASSERTING domain groups from agency labels; DISCOVER them. Everything keyed on
         "sensor era" needs its grouping re-derived - anchors, radiometric normalization,
         reweighting, and the held-out-era experiment (hold out a radiometric CLUSTER, not an
         agency).
caveat:  BAND STATS ARE A WEAK, CONFOUNDED PROXY. Footprint/season/sun-angle all move them;
         2016+2021s cover 66.7% of city, NAIP frames 53.8km2 vs 176km2 -> not the same ground.
         The 2000 grouping (59.7cm with 7.5cm CoE years) is probably an exposure coincidence.
         This is a SCREEN not a verdict. Proper instrument = low-frequency AMPLITUDE signature
         (FDA, Yang & Soatto CVPR 2020, lit ID 136 - amplitude=style, phase=content).
         REAL ground truth = acquisition METADATA (camera/contractor/flight date/sun angle).
files:   Scripts/phase4_qc_domain_cluster.py (new) - phase4/qc/domain_cluster.txt/.csv (new)
         Scripts/litwatch_robustness.md (lit-watch ledger, iterations 1-11)
next:    (1) DOES ACQUISITION METADATA EXIST for the 17 images? It beats every pixel proxy.
         (2) 2024 outlier - diagnose before use. (3) amplitude-signature version of this screen.
         (4) re-derive the anchor grouping from whatever (1)/(3) says.

"""

p = r'G:/My Drive/treedata/Scripts/CHATLOG.md'
s = io.open(p, encoding='utf-8').read()
anchor = "## 2026-08-18  U3 ANSWERED"
i = s.index(anchor)
io.open(p, 'w', encoding='utf-8').write(s[:i] + entry + s[i:])
print("CHATLOG entry inserted at char", i)
