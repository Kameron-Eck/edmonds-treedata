# Overnight literature hunt — consolidated digest (two-reader audit, 2026-09-06)

Sources: `LIT_HUNT_FINAL_2026-09-06.md` (v3 synthesis) + `LIT_HUNT_MASTER_2026-09-06.md`
(v3 + appendices A–G: full hunt log, panel returns). Both preserved from the hunter
session's scratchpad. Contract: `TRUTH_DOCUMENT_TEMPORAL_INCONSISTENCY_HUNT.md`.
Audited by two context-carrying readers; verdict: **no material overclaim; if anything
systematic under-claiming** (Condition B refused despite a checklist pass, because its
own pilot numbers failed the purpose).

## Verdicts
- **Condition A: met by exactly one study, under a stated generous scoring** —
  Roman et al. 2021 (*Land* 10(4):403; Philadelphia 1970–2010, five epochs, two
  uncalibrated aerial programs, 10,000 paired points, one interpreter, 3.2 pp/40 yr
  detectable-change threshold). It is the peer-reviewed precedent for **Panel A's
  exact method**, not for a map series. Present as "closest study, 4/5 under rule (i)".
  Siblings: Nix 2021/2023, Healy 2022 — a 3-study USFS lineage.
- **No segmentation twin exists**: 1,359 queries, ~585 triaged, 132 full-text reads,
  42 UNREADABLE recorded. The paper's gap claim is now HUNTED: *no published map-series
  study maps wall-to-wall from a heterogeneous sub-meter archive over ≥5 epochs,
  measures its own inconsistency, and validates change against blind human truth.*
- **Condition B: honestly refused.** PACC ("panel is the estimator, map is the
  auxiliary/locator") passed the adversarial checklist but its read-only pilot on our
  stack showed the map shrinks the panel CI only ~4% (±1.89→±1.81) and forcing the map
  to carry the difference is worse than ignoring it (±3.68). Independent convergence
  with our change-detector session's architecture.
- **Angle 10 (replacement-aware detection) NEVER FINISHED** — sweeps triaged, no
  full reads/synthesis (engines 429'd; OpenAlex dead all day; the armed 17:07 sweep
  never fired). Cleanly re-launchable after midnight UTC; spec + seeds in the master.

## New measurements from the hunt's pilot (port as instruments before citing)
- Edge-band anisotropy on lidar-certified-unchanged ground: 0–2 m band swings
  **13.2 pp** across epochs; >16 m core reads 1.0000 in 7 of 8 — inter-date
  inconsistency IS an edge phenomenon.
- Cross-date bias on 1,045 stable points: −2.32 ± 3.62 pp (undetermined).
- Smoothing trap reproduced independently — still needs a repo instrument + gated CSV.

## Corrections the hunt made to OUR record (action before publishing)
- Truth document F-numbers superseded by our own recalibration (F1 sign fixed at
  matched cuts; F3 3.55 pp not 1.07; F5 47.8% not 50.7%; F6 1.53 ha recut; F7
  overstated given the 0.15 pp matched floor). Truth doc to be annotated, not edited
  silently.
- Gold counts pinned: 1,169 no-change / 42 loss / 2 gain; "41/42" always with the
  10 m-halo qualifier (pixel-exact 36/42).
- **Interpreter error (3.6% from 28 duplicates) is comparable to the effect and
  unpropagated** — judges bound the bias at 0.5–2 pp; fix ≈ 2,550 duplicates with a
  second reader; ε-corrected statistic B_true = (B_obs − ε·d̄)/(1−ε).
- Citation-rot catches inside candidate designs (Bautin, Ruetschi, Cai) and two
  Literature_Tracker ledger errors (Healy journal; Kropp attribution).

## Keeps (queued on the master board)
1. Citation spine: Roman/Nix/Healy lineage; Pawlak 2026 as the automated analogue
   reproducing our disease at state scale (its 6.6 pp drop / 3.3 pp rebound survives
   Olofsson adjustment; authors warn against pixel-to-pixel change use).
2. The one experiment closing three gaps: pre-registered date-blinded order-randomized
   re-interpretation of a stable stratum (N≈2,070 → ±1.5 pp; ~1–2.5 h at Kam's
   measured 1.94 s/label): certifies PACC, de-circularizes the kill test, measures
   the arbiter error.
3. Cheap grafts: σ_chain (1.3 pp same-flight) published as the MDC floor;
   found-overlap cohort pair bank; BCTS class-specific calibration as the F3 remedy;
   the shadow-settling anisotropy probe (free).
4. Open leads, one cheap pass each: unfired OpenAlex sweep queries; Scholar cited-by
   for 12 seeds; Stehman 2022 + Xing & Stehman 2024; the 42-item UNREADABLE list via
   library access; IR-MAD/COLD never swept as primaries; angle-10 relaunch.
5. Killed family recorded as citable negative: label-shift/operating-point transfer
   without per-date labels has no remote-sensing instance (Alexandari/Taff read-full).
6. Panel protocol upgrades for all future panels: date-blinded, order-randomized,
   both chips resampled to the coarser GSD.

Housekeeping done: the pilot's four stray 13.3 MB npy caches at D:\edmonds-pipeline\
root deleted (flagged by the hunter itself).
