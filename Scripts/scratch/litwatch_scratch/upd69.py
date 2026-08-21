import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - SHADOW REFUTED AS THE OVERHANG MECHANISM (Q122) *** - 2026-08-19
Liu et al. 2023 (Remote Sensing 15:519, tracker ID 196) reports that **U-Net specifically** suffers
high omission from canopy shadow. That is our architecture and our symptom, so it is a live rival to
the dark-foliage-on-dark-roof contrast story. The two hypotheses make **opposite geometric
predictions**, which makes them separable with data already in hand: building shadow in the northern
hemisphere falls to the NORTH, so shadow predicts a north-side recall deficit, while contrast is
isotropic with respect to the sun.

Bearing from the nearest building pixel for every C-CAP canopy pixel near a building, 2016 baseline:

| | within 10 m (n=135,941) | within 20 m (n=235,295) |
|---|---|---|
| north side (NW,N,NE) | 0.5725 | 0.6326 |
| south side (SE,S,SW) | 0.5371 | 0.6105 |
| **north minus south** | **+0.0354** | **+0.0221** |

**The north side is slightly BETTER, not worse, at both radii. Shadow is refuted in the predicted
direction** - this is not a null result, it is a sign error against the hypothesis.

**THE CONFOUND, AND WHY THE ANSWER SURVIVES IT.** The dominant pattern in the table is not
north-south at all: the four DIAGONAL sectors all score 0.58-0.61 and the four CARDINAL sectors all
score 0.44-0.51, a spread of 0.123 - **five times the north-south effect.** That is almost certainly
a footprint-geometry artefact, not physics: buildings here are axis-aligned rectangles, so a pixel
due north sits off a long wall face while a pixel to the north-east sits in an open corner wedge with
more sky around it. **I am flagging this rather than reading anything into it.**

It does not damage the shadow test, because that test compares **sectors of matched geometric type**:

| matched comparison | north | south | difference |
|---|---|---|---|
| faces (N vs S) | 0.5071 | 0.4401 | **+0.0670** |
| corners (NE,NW vs SE,SW) | 0.6053 | 0.5857 | **+0.0196** |
| control (E vs W) | 0.4678 | 0.4755 | -0.0077 |

North beats south within both geometric types, and the east-west control is flat as it should be.

**WHAT THIS SETTLES.** The over-impervious deficit is **isotropic with respect to the sun**, so it is
structural, not illumination. **That rules out the cheap radiometric remedies** - shadow
compensation, histogram matching, illumination normalisation - and leaves the structural ones the
overhang finding already pointed at: a height channel or a NIR band. Combined with iteration 68
(corrected LABELS do nothing at matched operating point), the remaining candidate list is short and
specific, which is the useful thing about a refutation.

**Caveat.** Aerial survey flights are deliberately flown near solar noon to minimise shadow, so the
shadow effect being tested may simply be small in this imagery rather than absent in principle. The
test rules out shadow *as an explanation for our gap*; it does not rule out shadow mattering for
imagery flown at lower sun. Acquisition times are not in `imagery_stats/imagery_catalog.csv`, which
is why this had to be answered geometrically rather than from metadata.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q122. ANSWERED: SHADOW REFUTED.** North-side recall is +0.035/+0.022 HIGHER than south, at both
  radii and within both matched geometry types. The deficit is isotropic w.r.t. the sun, so it is
  structural, not illumination - **radiometric fixes are ruled out**.
- **Q123. [REAL GAP - ZERO COVERAGE IN 197 PAPERS]** Does RELIEF DISPLACEMENT explain part of both
  central findings? A standard orthophoto displaces elevated objects radially from nadir, **and the
  displacement scales with object height** - which is exactly the axis our staircase runs along.
  A tall crown is drawn leaning off its true ground position, by metres at our GSDs, and buildings
  lean too. C-CAP is built from a stereo DSM and may be closer to true-ortho, so **our masks and our
  reference may be systematically misregistered as a function of height**, concentrating exactly
  where the overhang deficit lives. A tracker search for `off-nadir`, `view angle`, `BRDF` and
  `orthorectif` returns **nothing across all 197 papers** - this is a genuine blind spot, not a
  question we considered and parked. Testable by cross-correlating mask against reference within
  height bands and looking for a height-dependent offset.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Test relief displacement / height-dependent misregistration (Q123)** - a genuine blind spot
   with zero coverage in 197 papers, and it bears on BOTH central findings at once. Measurable as a
   per-height-band offset between mask and reference.
2. **Re-score the cross-year recall series at matched CALL RATE (Q121)** - running; Q119 proved a
   fixed threshold can manufacture a +0.225 gain out of nothing.
3. **Human-check the 2-5 m over-impervious cell (Q120)** - reference-independent, which is what
   Q119's caveat needs.
4. **Test the v045/v046 aux-height INPUT variants on the impervious split** - now the leading
   structural candidate, with labels (it.68) and shadow (it.69) both ruled out.
5. **Characterise the tall-but-not-green pixels (Q114).**
6. **Write down the canopy definition (Q1).**
7. **Test whether scrub reconciles the references (Q112).**
8. **Trace what else used the NDVI reference (Q107).**
9. **Specificity on the UNCHANGED class (Q66).**
10. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 69 | 2026-08-19 | *** EMPIRICAL - SHADOW REFUTED as the overhang mechanism (Q122) *** | "
       "Liu 2023 RS 15:519 (ID 196) says U-Net specifically suffers shadow omission - our arch, our "
       "symptom | Shadow and contrast make OPPOSITE geometric predictions, so bearing-from-nearest-"
       "building separates them. North-side recall is HIGHER, not lower: +0.0354 within 10 m, +0.0221 "
       "within 20 m. Holds within MATCHED geometry: faces N .5071 vs S .4401 (+.067), corners "
       "+.020, E-W control flat (-.008). SIGN ERROR against the hypothesis, not a null. Flagged but "
       "NOT read into: cardinal .44-.51 vs diagonal .58-.61, spread .123 = 5x the N-S effect, almost "
       "certainly an axis-aligned-footprint artefact (wall faces vs corner wedges). CONSEQUENCE: the "
       "deficit is isotropic wrt the sun -> structural, not illumination -> RADIOMETRIC FIXES RULED "
       "OUT (shadow compensation, histogram matching). With it.68 ruling out corrected labels, the "
       "candidate list is now height channel or NIR. NEW BLIND SPOT Q123: relief displacement scales "
       "with HEIGHT and 0 of 197 tracker papers cover off-nadir/view-angle/orthorectification |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
