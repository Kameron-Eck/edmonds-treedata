import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - Q5/Q18 SCREENED - 2026-08-18 - `phase4_qc_domain_cluster.py`
**Kam, 2026-08-18: "Edmonds and King County use EagleView in the later years, and King County
switched contractors many times. There may be more than a few different sensors."**
Screened against the per-band statistics already in `imagery_stats/imagery_summary.txt` -
free, no imagery opened. Result: **the correction is supported.**

**1. AGENCY IS NOT THE DOMAIN AXIS.** Nearest neighbour by radiometric signature shares agency
for only **8 of 17 acquisitions (47%)** - near chance. Our per-(sensor x era) anchors are keyed
on the wrong variable.

**2. The EagleView signature is visible.** **2017 (City of Edmonds) and 2019 (King County) are
each other's nearest neighbours at distance 0.34** - the closest cross-agency pair in the set,
and closer than most same-agency pairs, despite 7.5 cm vs 14.9 cm GSD. Two different agencies,
near-identical radiometry. That is what a shared contractor looks like.

**3. King County is not one domain.** Its 9 acquisitions split across at least three groups:
2005+2007 (29.9 cm) pair off; 2009 sits with 2021/2023; 2000/2013/2015/2019 land elsewhere.
Consistent with repeated contractor changes.

**4. 2024 IS A SEVERE OUTLIER - flag for Kam.** Nearest-neighbour distance **4.96** (next
largest is 1.09) and a singleton cluster at every cut level. Band means 144/154/146 against a
typical 80-110. Either a genuinely different product or a processing/normalisation difference.
Worth checking before 2024 is used for anything.

**Honest limits.** Band statistics are a weak, confounded proxy for sensor - footprint, season
and sun angle all move them, and 2016/2021s cover 66.7% of the city while the NAIP frames cover
53.8 km2 against 176 km2, so those means are not over the same ground. The 2000 grouping (59.7 cm
sitting with 7.5 cm CoE years) is probably an exposure coincidence, not a sensor match. This is a
SCREEN. The proper instrument is the low-frequency amplitude signature (ID 136); the actual
ground truth is acquisition metadata, which would beat both.

**What it changes.** Stop asserting domain groups from agency labels; discover them. Every
downstream design that keys on "sensor era" - anchors, radiometric normalisation, the reweighting
of Search 20, the held-out-era experiment of Q16 - needs its grouping re-derived. And the
held-out-era test now has a much better design: hold out a radiometric CLUSTER, not an agency.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q18 = """- **Q18.** Is City of Edmonds a fourth distinct source, or does it share a contractor with King
  County? The catalog lists it separately and **2020 — our only labelled year — belongs to it**,
  while the 9-image King County block does not. If genuinely distinct, the anchor design is
  missing a level and every King County year is a cross-source transfer from the outset.
  Verifiable from acquisition metadata; **Kam should confirm.**"""

new_q18 = """- **Q18.** Is City of Edmonds a fourth distinct source, or does it share a contractor with King
  County? **ANSWERED by Kam + screened empirically:** they share EagleView in the later years,
  and King County switched contractors repeatedly. The radiometric screen agrees - 2017 (CoE) and
  2019 (KC) are nearest neighbours at 0.34, and agency predicts the nearest neighbour only 47% of
  the time. **Agency is not sensor.** Superseded by Q19.
- **Q19.** What ARE the true domain groups? The screen suggests at least: {2005, 2007},
  {2009, 2021, 2023}, {2017, 2019, 2020, 2022 ...}, {2019n, 2021s}, {2024 alone}. But the screen
  is confounded and the real answer is acquisition metadata (camera, contractor, flight date, sun
  angle). **Does that metadata exist for these 17 images?** If yes it beats every pixel-based
  proxy and should be recovered first. If no, the amplitude signature (ID 136) is the fallback.
- **Q20.** Why is 2024 a radiometric outlier by a factor of ~5 in nearest-neighbour distance?
  Different product, different processing, or a genuine scene change. Unknown, and it affects
  whether 2024 can join the series at all."""

assert old_q18 in s, "Q18 anchor not found"
s = s.replace(old_q18, new_q18, 1)

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 11 | 2026-08-18 | EMPIRICAL - domain clustering screen (Kam's contractor correction)"
       " | - | AGENCY IS NOT THE DOMAIN AXIS: nearest neighbour shares agency 8/17 (47%, chance)."
       " 2017-CoE and 2019-KC are nearest neighbours at 0.34 = the EagleView signature."
       " King County splits into >=3 groups. 2024 is a severe outlier (dist 4.96). New Q19/Q20 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
