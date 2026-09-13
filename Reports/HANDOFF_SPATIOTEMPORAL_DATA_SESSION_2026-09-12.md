# Handoff — from the spatiotemporal-consistency literature branch to the data session

**Written 2026-09-12 at the close of branch `docs/lit-review-spatiotemporal-consistency`.**
Kam works one workflow at a time; this file is what the next session loads so it does not
need this conversation. (CLAUDE.md §3.12 retires `HANDOFF_*.md` for pipeline milestones;
this is a one-off branch close-out, named so a reader knows it is not a plan.)

## 1. Read these, in this order

1. `Reports/MATH_NARRATIVE_SPATIOTEMPORAL_CONSISTENCY_2026-09-12.md` — the whole layer,
   inputs to outputs, every formula with its source and grade (≈ 400 lines).
2. `Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md` §11 (ledger) and
   §18–§20 (second-order gaps, round-10 results, the canopy-floor decision). The rest is
   derivation history; consult by section number when the narrative cites one.
3. `Reports/LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md` §5 (what the literature
   does not have) and §8 (bibliography). §4.12–§4.19 are the reading logs by round.
4. `Reports/lit_spatiotemporal_bibliography.csv` — machine-readable index of §8: one row
   per bibliography line, with DOI, grade, round, filed stem, read status,
   `superseded_by_id` (later rounds re-graded earlier lines). Same content as the
   "Spatiotemporal Review 2026-09" sheet of `Literature_Tracker.xlsx`.

## 2. Where the papers are

- PDFs and text extracts: `D:\edmonds-pipeline\Literture\Validation\<stem>.pdf/.txt`
  (outside git; not backed up). The `.txt` is the reviewer's read copy; `_raw.txt` is a
  reading-order extract for two-column papers. Every quote in the reports was gated
  against those files.
- **2026-09-12 incident:** 149 PDFs were deleted from that folder during the acquisition
  pass (cause not identified; the four agents' transcripts show no delete command). The
  `.txt` extracts survived, so no report content was lost. A re-acquisition by DOI was
  run the same day; the residue is listed in the CHATLOG entry "RE-ACQUISITION".
  **Back the folder up before the next session, or track the `.txt` extracts in git.**
- Fetch method, mirrors, and the browser-last rule: memory
  `scihub-fetch-method.md` (Kam's standing authorisation is recorded there).

## 3. Decisions already made (do not re-open)

- Canopy has a floor: small ~2 m trees are not canopy (framework §20). The mask adopts
  the lidar certification floor, `h ≥ 5 m`, unless Kam sets another value.
- Rates are per calendar year, per certified population, per distance band — never
  pre-registered (framework §12).
- The CUSUM runs only where the start state is certified (framework §12.3); elsewhere
  the change point is the chain's posterior.
- Sonnet acquires PDFs; Fable reads; Opus does code and referee work (memory
  `use-opus-for-subagents.md`). Browser-capable agents run one at a time.

## 4. The first measurements, in order (narrative §9)

| # | Measurement | Instrument to write | Kill that must fire | Needs |
|---|---|---|---|---|
| 0 | Row 12: re-derive framework §2.1–§2.2 with `r` = recall | one reader, one hour | — | nothing |
| 1 | Certified populations `𝒞` and LOSS (11b), one rule each on the two lidar dates | `qc/instruments/` builder mirroring `harm_change_laundering.py` GAIN | counts must reproduce PACC's `A_can` where it exists | lidar CHMs (local mirror) |
| 2 | Lidar-anchored rates `(r_{t,b}, f_{t,b})` by the decaying-anchor estimator (§12.2) | instrument → `phase4/qc/` CSV | 2016 reproduction: solve at the 2016 imagery epoch, compare to direct rates vs the 2016 CHM; placebo `(q_g, q_l)×10` must fail | masks per epoch; coregistration table |
| 3 | Emission bins `K` by held-out likelihood on certified cells (§2.3 A) | same | placebo shuffle must lower the likelihood | 2 |
| 4 | Spatial and cross-epoch residual correlograms per stratum and band (§13.1) | instrument | — (sets the bootstrap model, block size, `G(t)`) | 2 |
| 5 | Conclique goodness-of-fit of the autologistic fit (§17.5, §15.1 kill) | CPU, no lake write | must pass on a field simulated from the fit; a fit that passes with `𝒞` removed is a leak | 4 |
| 6 | Row 22: crown-size floor from 2020 polygons × lidar height vs residual blob sizes (§20) | instrument | injected discs: floor-size survive, blob-size erased | 1 |
| 7 | Row 21: `β` per resolution stratum | part of the joint fit | pooled fit must lose held-out likelihood on coarse strata | 4 |

Rows 1–7 need no GPU; 1–6 need no lake write (CLAUDE.md §3.4b: instrument → measured
CSV → gated finding).

## 5. What the theory does not yet have (assessment of 2026-09-12)

Nothing measured; stationarity untestable after 2016 (two lidar dates); edge bands
unanchored until the registration bound is checked; conditional independence assumed
six times and known false once (shared arm errors); early-epoch error is permanent in
the chain; borrowed results come from long-sequence, large-event regimes; the per-cell
penalty must run on strata samples; "certified" carries the lidar's own error. The
growth question is closed by the floor (§20). Measurements 0–4 expose the first four.

## 6. Branch mechanics

Worktree `D:\edmonds-pipeline\treedata-litreview`, branch
`docs/lit-review-spatiotemporal-consistency`, 30+ commits ahead of `main`, tree clean at
close. Kam pushes and merges (`main` is his). After the merge, the data session opens in
`D:\edmonds-pipeline\treedata\Scripts` on a `work/…` branch; the three reports, the CSV
index, this file and the tracker sheet come with the merge; the PDFs do not (see §2).
