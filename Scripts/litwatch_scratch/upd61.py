import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** WHAT C-CAP HI-RES ACTUALLY IS (Q90) *** - 2026-08-19
Attacked C-CAP's season two ways: its class histogram on our own city footprint, and its official
InPort documentation. Neither gives a season - but together they characterise the reference far
better than we had it, and one detail reframes several earlier results.

**1. IT IS NOT A LAND-COVER CLASSIFICATION. IT IS A CANOPY PRODUCT WEARING THE C-CAP LEGEND.**
Class histogram over the city-clipped 2016 raster:

| code | class | share |
|---|---|---|
| 11 | Mixed Forest | 35.76% |
| 2 | High Intensity Developed | 34.06% |
| 5 | Developed Open Space | 18.22% |
| 21 | Open Water | 5.43% |
| 12 | Scrub/Shrub | 3.47% |
| ... | 8 minor classes | <1.1% each |

**Deciduous Forest (9): zero pixels. Evergreen Forest (10): zero pixels.** All tree cover is
class 11. There is also **no Low or Medium Intensity Developed** in a city that is overwhelmingly
single-family residential - "High Intensity Developed" at 34% is doing duty as *impervious*.

The documentation confirms it: the final product attributes are **"Upland Tree (Forest),
Scrub/Shrub, and Background"** at 1 m. Thirteen legend codes appear, but the product is really
canopy / impervious / open space / water.

**Consequence for our QC:** the three `canopy_def` variants are nearly meaningless here.
`forest_only` and `forest_wetland` differ by Palustrine Forested Wetland at **0.30%** of the city -
which is exactly why 2013 scores .7072 vs .7094 across them. Only `forest_wetland_scrub` differs
materially, because it adds Scrub/Shrub at 3.47%. We have been reporting three definitions where
the data supports about one and a half.

**2. C-CAP CANOPY INCLUDES OVERHANG, AND IS HEIGHT-INFORMED.** Per InPort, canopy was formed by
*"combining the upland forest class with the **impervious under canopy** class"*, and *"a digital
surface model (DSM) derived from the stereo imagery was used to determine vegetation heights"*.

Two things follow that we had wrong:
* **C-CAP counts canopy overhanging roads and roofs.** It is a canopy-COVER product, not a
  land-cover product - so the long-standing worry that C-CAP "counts the lawn and roof between yard
  trees as forest" (STATE's suburban over-count hypothesis) is at least partly backwards: the
  impervious-under-canopy class exists precisely to attribute overhang to canopy.
* **Both references are height-informed.** Ours uses NDVI + a lidar CHM; C-CAP uses spectral +
  a photogrammetric stereo DSM. So the 10.98 pp gap (iteration 60) is **not** "spectral versus
  structural" - both use height. That removes the easiest explanation for it.

**3. A CONCRETE MECHANISM FOR C-CAP BEING CONSERVATIVE ON DECIDUOUS.** If C-CAP's height comes from
stereo matching on regional aerial imagery, and that imagery is leaf-off spring (the Puget Sound
consortium spec, ID 194), then **bare deciduous crowns are poor stereo targets** - little texture,
see-through structure - so their DSM height is under-recovered and canopy under-called. That is a
physical mechanism for the 3.8:1 asymmetry of iteration 60, and it does not require C-CAP to have a
different *definition* at all.

**4. AND THE SEASON IS NOT CONTROLLED - WHICH IS ITSELF THE ANSWER TO Q90.** InPort states
acquisition dates vary by location "**based on the latest date of available imagery**". C-CAP
hi-res is built opportunistically from whatever recent imagery exists; **season is not a design
parameter**. So:
* C-CAP cannot be assumed leaf-on or leaf-off - it is uncontrolled;
* **the 2016 and 2021 vintages may differ in season**, which is a direct mechanism for
  iteration 43's implausible result (11.16% discordance implying 5.33%/yr canopy loss, far above
  published street-tree mortality). Uncontrolled season between vintages would manufacture exactly
  that.

**Net:** Q90 has no clean answer because the product has no clean season. That is worse than either
answer would have been for change detection, and it strengthens the iteration-43/44 conclusion that
**C-CAP-vs-C-CAP change is not a usable change signal.**
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q90.** What season is C-CAP?""",
"""- **Q90. ANSWERED, AWKWARDLY: it has no controlled season.** InPort says acquisition varies by
  location "based on the latest date of available imagery". Season is not a design parameter, so
  C-CAP cannot be assumed either way and **the 2016 and 2021 vintages may differ** - a direct
  mechanism for iteration 43's implausible 5.33%/yr apparent loss. Also established: C-CAP hi-res is
  a canopy product (Upland Tree / Scrub-Shrub / Background), includes **impervious-under-canopy**
  overhang, and derives height from a **stereo DSM**. Original question below.
  What season is C-CAP?""")

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q108.** Does STATE's suburban over-count hypothesis survive? It holds that C-CAP inflates
  canopy by counting lawns and roofs between yard trees as forest. But C-CAP explicitly includes an
  **impervious-under-canopy** class folded into canopy - it is attributing overhang, which is
  correct behaviour for a canopy-cover product. And on matched ground C-CAP calls **less** canopy
  than our reference, not more. The hypothesis may be backwards and should be re-examined.
- **Q109.** Is C-CAP's stereo-DSM height failing on bare deciduous crowns? Poor stereo texture on
  leaf-off broadleaf would under-recover height and under-call canopy - a physical mechanism for
  the 3.8:1 asymmetry (iteration 60) that requires no definitional difference. Testable if C-CAP's
  source imagery date for this tile can be recovered.
- **Q110.** Should we keep reporting three `canopy_def` variants? Deciduous and evergreen classes
  are absent, and forest_only vs forest_wetland differ by 0.30% of the city. The reporting implies
  a granularity the product does not have.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Re-examine the suburban over-count hypothesis (Q108)** - it is load-bearing in STATE and the
   evidence now points the other way. C-CAP includes overhang deliberately and calls LESS canopy
   than our reference on matched ground.
2. **Recover C-CAP's source imagery date for this tile (Q109)** - would test the stereo-DSM
   mechanism and is the last route to a season.
3. **Write down the canopy definition (Q1)** - an 11 pp gap between two height-informed references
   is a definition problem.
4. **Trace what else used the NDVI reference (Q107)** - it covers the less-forested two thirds.
5. **Acquire county-wide C-CAP 2021 (Q104)** - though its value drops now that C-CAP change is
   suspect.
6. **What DOES the model key on (Q98)?**
7. **Specificity on the UNCHANGED class (Q66).**
8. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
9. **Simplify the canopy_def reporting (Q110).**
10. **Geometric vs thematic accuracy for per-object products (Q41).**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 61 | 2026-08-19 | *** what C-CAP hi-res ACTUALLY is (Q90) *** | - | "
       "HISTOGRAM: zero Deciduous, zero Evergreen - ALL tree cover is class 11; no Low/Med "
       "Developed either. It is a canopy/impervious/open-space/water product wearing the C-CAP "
       "legend (InPort: 'Upland Tree, Scrub/Shrub, Background'). So our three canopy_def variants "
       "differ by 0.30% of the city (Q110). CANOPY INCLUDES IMPERVIOUS-UNDER-CANOPY OVERHANG - "
       "STATE's suburban over-count hypothesis may be BACKWARDS (Q108). BOTH references are "
       "height-informed (C-CAP uses a stereo DSM), so the 10.98pp gap is NOT spectral-vs-structural. "
       "Q90 ANSWERED AWKWARDLY: season is NOT a design parameter - 'latest available imagery' - so "
       "2016 and 2021 vintages may differ, a direct mechanism for iteration 43's implausible loss |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
