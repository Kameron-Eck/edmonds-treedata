# Adversarial review of the QC findings — 2026-08-24

Review of `IMAGERY_QC_FINDINGS_2026-08-24.md` by an 11-agent workflow: six verifiers re-checking
every quantitative claim against the CSVs/JSONs on disk (recomputing statistics, not re-reading
prose), five attackers assigned to refute the headline claims and re-audit the tool code.
**147 findings: 0 critical, 6 major, 35 minor, 106 notes.** Verdict up front:

> **Every finding of fact survives. Several claims of interpretation were overstated and are
> corrected in the report** (marked "amended in review"). The 2024 displacement, the mirror bug,
> the byte-verification zero-mismatch result, the NIR effect, and all six method corrections
> reproduce exactly from the data. What fell was scope and certainty: the resolution claim is
> valid only at the 50 cm analysis grid; the "no relationship" Spearman cannot exclude moderate
> effects; two "negligible/invariant" framings needed uncertainty attached.

## The six major findings

### M1 — The resolution claim is partially circular (the attack that landed)
Every separability number was computed **after resampling all rasters to a common 50 cm grid**
(confirmed in `grab_common()` and arithmetically: 576,000 px = 40 windows × (60 m / 0.5 m)²).
Averaging to 50 cm erases all sub-50 cm information from the 5–10 cm files while the 60–100 cm
files lose nothing — the design is structurally incapable of detecting a native-resolution
advantage below the analysis scale (e.g. purer edge pixels at 7.6 cm can never show up).
**Correct claim: "at a 50 cm analysis grid, native resolution does not affect per-pixel colour
separability."** Materially weaker than the original headline.

### M2 — Resolution is confounded with product and season in this catalog
The ≥60 cm group is dominated by leaf-on summer NAIP 4-band products; the ≤10 cm group by King
web-Mercator caches and CoE orthos. No resolution effect is *detectable* against co-varying
product/season effects. Only the NIR gain (+0.099) is isolated by a paired same-pixel design.
"The NIR band is the entire advantage" → "the only advantage this design can isolate."

### M3 — "Spearman −0.036, no relationship" stated a null without its uncertainty
95% CI at n=36 is roughly **(−0.35, +0.31)**: the data exclude only moderate-to-strong monotone
effects. n is also mildly inflated (two same-pixel pairs, one same-flight pair → ~32–33
independent acquisitions). And the exact −0.036 is not cleanly reproducible: recomputation gives
−0.025…−0.036 depending on which GSD source is joined (config.py lists the CoE orthos at 5.0 cm
while the report itself uses 7.62 cm — a GSD-source inconsistency worth resolving in the catalog).
The *conclusion* (|ρ| < 0.04, p ≈ 0.9) is robust across every variant.

### M4 — "+0.013, negligible" is not affirmable
Median reproduces (+0.013) but the mean is +0.045, Mann-Whitney p = 0.12, and a file-level
bootstrap CI on the median difference is (−0.015, +0.107) — the data cannot distinguish zero from
half the NDVI gain. Same for "coarser scores slightly higher" (permutation p = 0.13 →
"statistically indistinguishable").

### M5 — Pseudo-replication: per-file AUROCs carry implied precision the pipeline never measured
Each AUROC pools ~576k spatially autocorrelated pixels from ~40 windows; the CSVs record no
per-window values, so **no uncertainty is computable from the published outputs** and the
effective sample is ~40 clusters. Paired same-window contrasts (the NDVI gain, the 2015 seasonal
pair — and the 2022 duplicate pair reproducing to 0.0001) are the defensible subset; unpaired
cross-file differences below ~0.03–0.05 are unresolved. **Tool fix queued: emit per-window AUROCs
so a cluster-level SE can back every comparison.**

### M6 — The byte-verification headline double-counts
"336 files / 78.4 GB" sums two **overlapping** runs (220 + 116 rows; 77 files / 15.0 GB were
verified in both). Distinct coverage is **259 files / 63.4 GB** — files inflated ~30%, bytes ~24%.
The zero-mismatch conclusion is unaffected (0 mismatches in 336 row-checks over 259 files), and
the USGS re-verification (45/45 OK) stands — though "2.93 GB" was the 39 tiles alone; the 45
entries total 4.94 GB.

## Minor findings worth acting on (selected from 35)

- **"3.5× more variable" is ~30% ceiling compression.** NDVI's mean AUROC sits nearer 1.0, which
  mechanically compresses variance; on a logit scale the ratio is ~2.5×. The difference is still
  real (paired Pitman–Morgan p = 0.019), so the invariance claim survives at reduced magnitude.
- **The seasonality corollary cherry-picked its October file.** 2019n (0.850) was cited; 2023n
  (0.835 — the *minimum* of all ten) was not, and three of the four lowest NDVI AUROCs are October
  acquisitions. Direction holds; "barely" was built on the more favourable of two available points.
  Also unreported: in the same NAIP line, ExG scores *higher* in October than July (0.734/0.759 vs
  0.709) — RGB separability is too product/atmosphere-noisy to carry a seasonal story at all.
- **A fifth campaign pair contradicts two §3 sentences.** 2015n↔2015s (both campaign files, same
  2015-08-07 flight day) grades NOISY — site spread 0.302 m vs the 0.30 gate, a 2 mm exceedance —
  so "every campaign pair … tight agreement" and "the ten NOISY pairs all involve King or
  cross-season" are each false by this one pair (9 of 10 fit).
- **"All larger than the 2.76 m question" is false for 2.117 m** (three of four are larger; the
  full 8-reference set also had four spreads *below* 2.76 that failed the per-pair gate honestly).
- **1936's "0.466, below chance" is not a meaningful number.** The valid-pixel mask passes white
  padding, and the CSV shows median canopy = median background = −253: the AUROC measured which
  class drew more padding. "No signal" is right; citing 0.466 as a floor is not.
- **Two code-comment falsehoods** (both now fixed): `phase_shift`'s docstring claimed it is "the
  same estimator as `band_registration_px`" — it is a separate re-implementation *with* a Hanning
  window the other lacks; and a crossreg comment labelled 0.03 m as "MAD" when the measured MAD is
  0.005–0.007 m (0.03 is the range).
- **A silent-regression hazard in the coverage fix** (now warned): `_city_mask` returns None on a
  missing shapefile or import failure, and coverage silently reverts to the full-frame analysis
  §7.5 was written to kill. This run demonstrably had the mask applied; a future run could regress
  without notice. A warning + CSV column now record whether confinement applied.
- **A latent edge in the mirror fix**: the tree-wide basename skip would silently *not* mirror a
  subdirectory file sharing the final raster's basename (none exists today), and the rglob loop
  lacks the post-copy size check the raster copy has.
- **"The 12 acquisition tests still pass" carries no weight for the mirror path** — no test
  exercises `do_mirror`. The actual proof is the cloud re-verification, which the report also
  gives.
- **3-inch verification is stickier than "unverified pending upload" implies**: the Drive-side
  SnoCo manifest must itself have been regenerated *and* uploaded before a re-run can see them.
- Assorted wording: "11 files … plus the CoE orthos" self-contradicts its own count (the CoE
  orthos are additional, unmeasured Drive-resident files); "valid 1.000" is 0.9995–0.9999 for
  several rows; the 2024 "0.03 m" is a range while the table's "0.01" is the vector spread — two
  different statistics presented as one; 1936's "38%/15%" padding split exists in no preserved
  measurement (ad-hoc terminal output); "best like-for-like 0.855" is a max over 37 files with
  runners-up within noise.

## What was attacked and held

- **The 2024 displacement.** Every number reproduces; the "five scattered sites" description is
  accurate (the sites span 3.2 × 4.4 km — the attacker's "all in the city core" premise failed);
  the pure-translation reading is consistent (per-site dx agrees to 0.033 m, leaving < 1 arcsec
  for any rotation); and the recommendation (use `2024s` positionally) survives every angle,
  including the "what if 2024_coe is right and everything else shares a bias" inversion — which
  would require the King, NAIP, county and CoE product lines to share one 1.28 m error that 2024's
  city copy alone escaped. Two honest residues: whether the mechanism is a datum slip or a
  re-rendered lattice is *undeterminable from held data* (and operationally irrelevant); and the
  shift-corrected r of 0.985 vs the controls' 0.995 is consistent with the sub-pixel remainder of
  an integer-pixel correction.
- **NDVI invariance** — survives at ~2.5× (scale-free) with p = 0.019; not sampling luck, though
  n=10 keeps it a strong observation rather than a law.
- **The six §7 method corrections** — all six verified present in the code, doing what the report
  says, including the negation with its synthetic test.
- **The seasonal +0.145** — reproduces exactly, and the report's own "upper bound" caveat was
  judged correct (no same-product comparison reaches the Feb–Mar leaf-off regime).
- **The within-year contrast CSV** contains known-confounded rows (NDVI-vs-ExG contrasts; a
  "year −" row pairing 1936 with 1998) — but the report never cites those rows.

## Process note

Every reviewer worked from the CSVs/JSONs and code only (no raster reads), and recomputed rather
than trusted. The review found the report's *facts* reliable and its *confidence* the thing needing
correction — which is the same failure mode the report itself documented six times in §7. The
corrections below are applied in the findings report, marked "amended in review".
