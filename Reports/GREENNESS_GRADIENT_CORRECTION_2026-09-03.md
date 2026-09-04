# The "leaf-off" recall gradient is a GREENNESS gradient — cause unresolved

**Status: correction to the 2026-09-03 adversarial-review synthesis (its S6 finding).
Documented, pending Kam's K4 confirmation. Supersedes the phenology framing.**

## What was claimed

The review's S6: within the King sensor at fixed 10.03 cm grid, recall tracks the
year's measured low-greenness fraction (GRVI < 0.02 per `qc/instruments/
phase4_qc_leafoff.py`): 2013 (22%) recall .740 · 2015 (31%) .740 vs 2019 (91%)
.635 · 2021 (64%) .606 · 2023 (66%) .651 — delta ≈ −.109, and it was framed as
LEAF-OFF PHENOLOGY, promoting a seasonal-IGNORE training experiment.

## What the flight dates say (qc/imagery_pixelsize_and_date.csv, read 2026-09-03)

| year | flight window | low-GRVI fraction |
|---|---|---|
| 2013 | Jun 2–6 | 22% |
| 2015 | **Feb 15 – Mar 8** | 31% |
| 2019 | Apr 25 – May 8 | **91%** |
| 2021 | Apr 14–17 | 64% |
| 2023 | Apr 19 – May 7 | 66% |

If the gradient were phenology, the February flight (2015) would carry the highest
low-greenness fraction by far. It carries nearly the lowest, and scores as well as
June 2013. Three late-April flights measure 2–3× "less green" than deep winter.
Kam's independent observation (2026-09-03): no visible leaf-off variation by eye.

## Corrected statement

The measured association is RECALL vs IMAGE GREENNESS (−.109 across these five
same-sensor years), and the greenness fraction does not track the calendar — so the
mechanism is plausibly the RADIOMETRIC PROCESSING CHAIN of each delivery (color
rendering, exposure), not canopy phenology. The 2016 delivery is dark-valued overall
(mean band-1 DN ≈ 25 in sampled forest; 118/250 sample points flag dark at mean
DN < 60 — `sample_2016_covariates.csv`), consistent with delivery-level radiometry
dominating the index.

## Consequences

- The queued "leaf-off quantity-preserving IGNORE" experiment's PREMISE is flagged:
  an IGNORE keyed on low-GRVI would mask by radiometry, not season. Do not launch
  until the covariate is decomposed (per-delivery histogram normalization vs GRVI,
  or the E2 covariate split of Kam's photo-interp labels).
- "Leaf-off years carry systematic label error" (CLAUDE.md durable gotcha) remains
  TRUE as stated — label projection from an April–July 2020 flight onto a February
  acquisition is still a seasonal mismatch. This correction is about the RECALL
  GRADIENT's cause, not about label-projection season risk.
- Radiometric normalization (per-delivery) enters the candidate list for the 36-run
  recipe — it was previously judged unnecessary; this gradient is the first evidence
  with a mechanism pointing at it.
