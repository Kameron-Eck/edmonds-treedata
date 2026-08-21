import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - 1936 AND 1998 ARE SINGLE-BAND, AND THE FILENAME SAYS OTHERWISE (Q124) *** - 2026-08-19
Opened the two uncatalogued frames. **Both are literally one band**, despite being named
`1936_king_rgb.tif` and `1998_king_rgb.tif`.

| file | bands | grid | mean | p1 | p99 |
|---|---|---|---|---|---|
| 1936_king_rgb.tif | **1** | 18944 x 26880, EPSG:3857 | 230.5 | 69 | **255** |
| 1998_king_rgb.tif | **1** | 18944 x 26880, EPSG:3857 | 125.6 | 76 | 219 |
| 2000_king_rgb.tif | 3 | 18944 x 26880, EPSG:3857 | 89.9 / 106.6 / 105.3 | | |

**THE NAME IS A TRAP, AND THAT IS THE OPERATIONALLY IMPORTANT PART.** Every other `*_king_rgb.tif`
in the pipeline is three-band, and `phase1_preprocess.py` is built around that convention (its
year table lists `2000_king_rgb.tif`, `2002_king_rgb.tif` and so on as `native_file`). Anything that
globs `_king_rgb.tif` and assumes three bands will either crash or silently read band 1 three times
on these two. Confirmed by grep: **`1936` and `1998` appear nowhere in `phase2_data_prep.py`,
`phase4seg/config.py` or `pipeline_config.py`** - they are referenced by no config at all, which is
why the trap has never been sprung.

**THEY SHARE THE 2000 PIXEL GRID EXACTLY** - 18944 x 26880 in EPSG:3857, identical to 2000, while
2013 is 74496 x 105984. Two consequences:
* someone has already **co-registered and resampled them onto the 2000 mosaic grid**, so the hard
  georeferencing work on scanned film may already be done - this is better news than expected;
* but their nominal GSD is therefore **inherited from that grid, not measured from the film**. A
  1936 frame resampled to ~40 cm cells does not carry 40 cm of optical detail. **Do not quote the
  grid spacing as the resolution** - that is the it.70 `gsd_cm` lesson in a new place.

**RADIOMETRY IS POOR IN TWO DIFFERENT WAYS, WHICH MATTERS FOR ANY TRANSFER PLAN.**
* **1936 is clipped at the bright end**: p99 = 255, so at least 1% of the frame is blown to pure
  white with mean 230.5. Detail in bright areas is **destroyed, not merely compressed** - no
  normalisation recovers it.
* **1998 is low-contrast**: p1 = 76 and p99 = 219, using about 143 of 256 levels. That IS
  recoverable by rescaling, so the two years need **different** preprocessing, not one historical
  recipe.

**WHAT THIS DOES TO THE Q124 DECISION.** Combined with Tian 2025 (ID 202), the honest position is
that 1936 is not an extension of the current problem: single band, blown highlights, and an unknown
true resolution. **1998 is the much better candidate** - single band too, but well-behaved
radiometry, and only two years off 2000, which gives a **near-contemporaneous RGB frame on the
identical grid to validate a panchromatic method against.** That is an unusually clean experiment
and it is sitting unused: train or adapt on 1998 single-band, score against the 2000 model's output
where the two overlap in time. **If a panchromatic route cannot reproduce 2000 from a 1998 frame, it
will not survive 1936.**
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q125.**""",
"""- **Q126. [CHEAP, HIGH LEVERAGE]** Use 1998 as the panchromatic PILOT before touching 1936. Same
  grid as 2000, well-behaved radiometry, two years apart - so the 2000 RGB result is a near-
  contemporaneous control for a single-band method. This converts "can we do panchromatic at all"
  from an open research question into a measurable one, at the cost of one inference run.
- **Q127.** Does anything in the codebase glob `*_king_rgb.tif` and assume three bands? The two
  single-band files are currently invisible to every config, so the trap is dormant - but adding
  them to a catalog without checking would spring it.
- **Q125.**""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **1998 as the panchromatic pilot (Q126)** - cheapest way to answer whether the series can go
   back at all, with a built-in near-contemporaneous control in 2000 on the identical grid.
2. **Test relief displacement / height-dependent misregistration (Q123)**, then its
   deliverable-level version, spurious CHANGE from differing frame layouts (Q125).
3. **Q121 at matched call rate** - running.
4. **Human-check the 2-5 m over-impervious cell (Q120).**
5. **Test the v045/v046 aux-height INPUT variants on the impervious split** - labels (it.68) and
   shadow (it.69) are both ruled out; Wagner 2024 (ID 199) is the published precedent.
6. **Characterise the tall-but-not-green pixels (Q114).**
7. **Write down the canopy definition (Q1).**
8. **Test whether scrub reconciles the references (Q112).**
9. **Trace what else used the NDVI reference (Q107).**
10. **Specificity on the UNCHANGED class (Q66).**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 71 | 2026-08-19 | *** EMPIRICAL - 1936 and 1998 are SINGLE-BAND and the filename lies "
       "(Q124) *** | - | Both `*_king_rgb.tif` files are literally 1 band. Every other _king_rgb is "
       "3-band and phase1_preprocess.py is built on that convention, so any glob assuming 3 bands "
       "breaks or silently reads band 1 thrice. Dormant only because grep finds 1936/1998 in NO "
       "config (phase2_data_prep, phase4seg/config, pipeline_config). THEY SHARE THE 2000 GRID "
       "EXACTLY (18944x26880 EPSG:3857) -> already co-registered/resampled, so georeferencing may be "
       "DONE; but nominal GSD is inherited from that grid, NOT measured from film - do not quote it "
       "as resolution (the it.70 gsd_cm lesson again). RADIOMETRY BAD TWO DIFFERENT WAYS: 1936 "
       "CLIPPED (p99=255, mean 230.5, bright detail destroyed not compressed); 1998 LOW-CONTRAST "
       "(p1 76 p99 219, ~143 of 256 levels, recoverable by rescaling). So they need different "
       "preprocessing, not one historical recipe. CONSEQUENCE: 1998 is the pilot, not 1936 - same "
       "grid as 2000, two years apart, giving a near-contemporaneous RGB control for a panchromatic "
       "method (Q126) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
