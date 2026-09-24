# litkb S4.5 referee — STAGE-B (plan item 4: Stage B, the metadata fan-out and its kill criterion)

Referee `referee-stage-b`, 2026-09-24. I did not build, propose, integrate or audit Stage B; I score it on the REAL rows
of the ladder-1 run with oracles I wrote myself (CLAUDE.md §3.4c; brief-CONTRACTS X9: no builder detector is my oracle).

**Verdict: REJECT** — one Stage B rung is wrong on real rows: **B9 `openaire`** asks, and in MEASURE mode credits, PDF
URLs of OTHER works that OpenAIRE lists under `<rels>`; 7 run rows (L074 L090 L150 L080 L102 L168 L170). A fix needs a
re-freeze and a re-run of those rows, never these rows re-graded under new code. Two gated counters also read non-zero
on the real run and need the orchestrator's ruling (neither is a rung defect): `crosswalk_rows_without_identifier=17`
(the ladder's first-landing stop cuts Stage B's Wave 2 short of the plan's closure stop rule — 17 named crosswalk rows)
and `free_ceiling_measured_unconverted=1` after the IIASA exception (Kats_2019 L005: the right arXiv bytes, refused as
`duplicate-held` by the disk dedupe against an unowned copy). Everything else scored CORRECT: all 58 Stage B binds are
the work by my own reader; the arXiv B1 rung converted E13 and 13 more works, every one through an arXiv id S2 wrote in
this run; the harvest's recall is 100 % wherever its service was asked; the fan-out kill criterion scores **KEEP**.

## What I read, and how (every number below is MEASURED by a script in my scratch unless marked)

- Checkout `D:\edmonds-pipeline\wt-s45-ref-stage-b` (detached **2ef3d68**, `git status --short` empty apart from this
  report). Worker DB `litkb_test_w6` (pg_locks: 0 advisory locks, 0 sessions before every DB run and at the end). Live
  `litkb` read ONLY as `litkb_reader`. No network (the cassette and the body store are read from disk). Corpus read-only.
- Inputs, read-only from the main tree (sha256 prefix): manifest `hardening-1-manifest.json` 5873d3fc… (frozen_at
  2026-09-24T08:22:40.799Z, 198 rows); run CSV 8ddad087… (195 rows); recording report 7caa3330… (`record_errors []`,
  index sha 4566ea28…); cassette index 4566ea28… (3,632 recorded interactions); bodies
  `D:\edmonds-pipeline\litkb_derived\cassette_bodies`; the driver's printed lines `live\run-full-3.out` 3da1c9a7…;
  the probe CSVs `phase4/qc/litkb_acq_probe_head.csv` and `litkb_acq_probe_crosswalk.csv` (content sha with CRLF folded
  = the manifest's pinned `probe_csvs_sha256`: 6eca28d3…, ce7778c4…).
- Live census (reader, after frozen_at, workstream ladder-1): 3,842 attempts over 187 works, 0 attempts in any other
  workstream; 76 file versions (open_access 34, landing 14, arxiv 14, openaire 6, wayback 4, crossref-link 3, s2 1) —
  the dispatch's numbers, reproduced. Stage B binds = 58 of them (open_access, arxiv, openaire, crossref-link, s2).
- **My oracles** (scratch `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-stage-b\`):
  `landed.py` — every PDF a Stage B rung reached (102 attempts, 81 distinct PDFs), read with **PyMuPDF** (litkb uses
  it nowhere: the binder reads pdftotext, the acceptance test pypdfium2): page count, and the title as a HEADING (best
  SequenceMatcher ratio against 1–4 consecutive lines of pages 1–2) and the first author's surname, against the work's
  **Crossref record as recorded in this run's cassette** (main_works only where Crossref had none); CORRECT needs
  ratio ≥ 0.85 and the surname; five borderline PDFs I read by hand (`manual_verdicts.json`, quoted in the table).
  `crosswalk.py` — the crosswalk CSV's values vs the identifiers/edges each work holds now, with `asserted_by`, and
  whether S2 / Crossref was ever ASKED. `kill.py`, `kill2.py` — the kill criterion from the plan text. `yields.py` —
  every Stage B yield from the attempt rows, verified and net-new. `openaire_rels.py` / `openaire_mech.py` — my own
  XML walk of every recorded OpenAIRE answer. `f1.py` — auditor-fix5 F1. `noa.py` — the 35 `no-oa-copy` rows beside
  the 09-22 head probe (HEAD answers taken before and independent of the ladder).

## Findings

**N1 — REJECT: B9 `openaire` asks and credits other works' PDFs.** `litkb.acquire.stage_b_repos.openaire_urls` walks
EVERY `url` / `webresource` element of the OpenAIRE XML answer (its docstring: the walk of paper-search-mcp 0.1.4
`OpenAIRESearcher._extract_rel_data` — a relayed design), including the `<rels>` subtree, which holds OTHER results
(`IsAmongTopNSimilarDocuments`, `hasAuthorInstitution`). `<rels>` precedes `<children>` in the document, so those URLs
are asked FIRST. My walk of the run's 187 recorded answers: 8 answers put another work's PDF among the rung's
candidates, always first; 7 attempts ended on another work's URL:

| row | work | mode | the rung's answer | the URL it ended on belongs to |
|---|---|---|---|---|
| L074 | Coulter_2008 | measure | `measured` — credited as a conversion | Narendran et al. 2014, ISPRS Archives XL-8 (my read of page 1) |
| L090 | Zhang_2021_feature-matching | hunt | `measured` — credited as a conversion | Zhang et al., ISPRS Annals V-2-2020 "Guided feature matching …" (another paper, 8 pp vs the article's 14) |
| L150 | Kokubu_2020 | hunt | `binding-failed`, another work's PDF quarantined | MacGregor et al. 2020, J. Glaciology (the binder refused it: correct) |
| L080 | Majasalmi_2021 | hunt | `blocked/challenge_or_bot_check` | a bioRxiv preprint of another work |
| L102 | Rodman_2021 | hunt | `blocked/challenge_or_bot_check` | another MDPI article (rs 13/6/1089) |
| L168 | Vixie_2007 | measure | `blocked/challenge_or_bot_check` | a Hindawi AAA 2007 article |
| L170 | Kumar_2019 | measure | `blocked/challenge_or_bot_check` | a Kiel technical report |

Consequences: openaire's printed `yield: openaire=11/187` is **9/187** by my reader; 4 works carry a `blocked` row on
openaire caused by another work's host (`blocked` is dead-in-run and enters the route's back-off ladder for that
work); one unrelated PDF sits in
quarantine. No wrong BIND occurred (the binder is the backstop in acquire mode; MEASURE mode has no binder). Smallest
fix (the orchestrator's): take URLs from the asked result only (skip the `<rels>` subtree), plus a mutation row; then
re-freeze and re-run the 7 rows.

**N2 — gated, needs a ruling: the Stage B stop rule.** The plan's item 4 takes round 3's closure rule — "STOP when a full
pass adds nothing" (LINKAGE §2.3). `run.acquire` instead stops the whole ladder at the first landing: once a concurrent
Wave-1 rung lands, the stage's non-concurrent rungs (Wave 2: datacite, zenodo, figshare, ncbi-idconv, s2, europepmc,
arxiv, venue) are never called and write no row. MEASURED: every one of the **17 crosswalk rows** still without its
arXiv sibling (L082 L090 L109 L128 L129 L130 L132 L135 L175 L176 L178 L181 L184 L186 L187 L188 L194) is a hunt that
landed at Wave 1 (open_access 14, crossref-link 2, openaire 1) — 0 s2 attempts and 0 recorded S2 requests for any of
them. The builder's counter, read as litkb_reader, reads `crosswalk_rows_without_identifier=17` and names the same 17
works. No file was lost (all 17 bound one). Every S2 call that WAS made harvested: arxiv 21/21, dblp 44/44. Options:
continue Stage B's metadata-only calls after a landing (a code change: re-freeze, re-run the 17), or rule the gate's
population excludes hunts that landed before Wave 2 and carry the 17 by name. Codex's review SUPPORTED the closure rule
itself; nobody examined its interplay with the first-landing stop — only the real rows showed it.

**N3 — gated, not a Stage B defect: Kats_2019 L005 did not convert.** The arxiv rung reached the work's free copy (my
reader: 9 pp, the title as the heading, "Kats" on page 1; served sha d54e42ec…), and `run.land_and_attach`'s disk
dedupe answered `duplicate-held`: the same bytes are `Literture\Validation\Kats_2019b_soft-staple-algorithm-combined.pdf`
(sha256 d54e42ec…, measured), a file the database does not own. The work holds no file, so
`free_ceiling_measured_unconverted` reads 2 today (Kats, IIASA) and 1 once LADDER1 carries the IIASA exception line.
The D11/D23 exception grammar excuses only BINDING refusals (`binding-failed`/`binding-pending`), so Kats cannot be
excused by it. The register-editor's E03 re-grade (held/duplicate-held) already records the pair; the gate still counts it.

**N4 — auditor-fix5 F1, measured on the run.** The literal case (an Unpaywall location equal to an EarthArXiv URL,
credited twice) occurred **0** times — vacuously: the EarthArXiv rung answered `no-oa-copy` ("no EarthArXiv preprint in
the harvested map") on all 191 of its rows / 187 works, so no EarthArXiv URL was ever asked. The CLASS F1 names
(`open_access` neither consults nor books the run's asked URLs) occurred **17** times: one URL credited to both
`open_access` and `openalex` for one work — 16 hunts (open_access `ok` + openalex `measured`) and 1 measure row — each
URL GET twice in one take (34 recorded GETs for 17 URLs). So `yield: openalex=17/187` is entirely this double credit:
**net-new over Unpaywall = 0/187**, which MEASURES on this corpus the plan's "B3 — DISPUTED … zero net-new over
Unpaywall". Also 4 measure rows (L168 Vixie, L169 Jaffe, L170 Kumar, L171 Gulrajani) where Stage C's landing rung re-asked the arXiv PDF
open_access had already asked (outside Stage B, same class).

**N5 — yield-line semantics.** `yield: arxiv=19/26` counts 5 rows (Thakur, Vixie, Jaffe, Kumar, Gulrajani) where the
rung made no request because open_access had already asked the same arXiv PDF (the C2A34 dedupe) — booked
`no-oa-copy`, a miss statement about a URL that was a hit. By requests actually made: 19/21. My recount agrees with the
printed line for the other 17 routes (table below).

**N6 — a negative re-graded: Europe PMC.** The plan keeps B12 as "MEASURED ZERO on the survey's controls"; the run
measured **1/12**: Coulter_2008 L074 via `europepmc.org/articles/PMC3673411?pdf=render` — 13 pp = Crossref's 1–13
range, the title and "Coulter" on page 1 (CORRECT), net-new over Unpaywall. The rung found a real copy; the survey's
zero does not hold on this corpus (1 row — a measurement, not a trend).

**N7 — the binder refused the work's own bytes three times (outside Stage B; reported).** LPVSubgroup_2025 L007 via
`openalex` (pure.iiasa.ac.at, 188 pp, title as heading — D23's named exception; note the exception line names route
`openalex`, not `wayback`: the openalex rung reached the IIASA copy live), Likowski_2022 L191 via `arxiv` (the registry's
first author "Likowski" is not a whole token on the page), Chen_2014_true-orthophoto L165 via `open_access` (author on
page 1 but "not near the title").

**N8 — a test gap on a kill-criterion scheme.** No test pins S2's DBLP harvest: my mutation M1 (below) left all 103
builder tests green; only my real-data test went red (44 of 44). dblp is the scheme with the most real gains (44).

**N9 — open_access on the no-oa-copy bucket.** The plan asks every rung for every `no-oa-copy` row; `open_access` asked 18 of the 35. The
other 17 are HUNT rows whose Unpaywall answer before the run was already `no-oa-copy` (that history is what put them in
the bucket), skipped `dead_route` by C1a's pre-existing rule. No MEASURE row skipped it (D9 holds: 18 dead_route skips in
the run, all hunts). Its bucket yield is therefore measured on 18 rows, not 35 — stated, not a defect of Stage B's rungs.

## Scored rows

Distinct run rows scored: **116** — **92 CORRECT, 24 WRONG, 0 UNDETERMINED** (WRONG = L005; the 7 N1 rows; the 17 N2
rows; L090 is in both). Attempt-level: 102 Stage B PDF reaches — **99 CORRECT, 3 WRONG** (L074, L090 openaire
`measured`; L150 openaire `binding-failed`); binds 58/58 CORRECT; measured 37/39 CORRECT.

### FREE-PDF rows and E13 (head probe CSV `verdict=FREE-PDF`, plan: "Kats must convert; Girard/Subramanian/Bacry measured")

| row | work | expected | the run did | my oracle | verdict |
|---|---|---|---|---|---|
| L005 | Kats_2019 (hunt) | convert (arXiv via S2) | arxiv `duplicate-held` → `held/duplicate-held`, no file | the PDF is the work (9 pp; heading ratio 1.00; author) — held on disk unowned | **WRONG** (row; N3) — rung CORRECT |
| L019 | Girard_2019 (measure) | arxiv `measured` | arxiv `measured` (1903.06529) | 4 pp = Crossref 4; heading 1.00; author | CORRECT |
| L020 | Subramanian_2021 (measure) | arxiv `measured` | arxiv `measured` (2103.07534) | 10 pp = 10; 1.00; author | CORRECT |
| L021 | Bacry_2015 (measure) | arxiv `measured` | arxiv `measured` (1502.04592); ia measured the same sha via archive.org | 48 pp (article-number range); 1.00; author | CORRECT |
| L002 | Pfitzmann_2022, E13 (hunt) | land via arXiv (D10) | arxiv `ok` → `bound-unextracted/fresh-bound`, 2206.01062 from an S2 edge written in the run | 9 pp = 3743–3751; 0.89; author | CORRECT |

### The 53 crosswalk works (36 arXiv, 8 ISBN, 11 relation — the plan's split, reproduced): 36 CORRECT, 17 WRONG (N2)

Every identifier or edge found carries `asserted_by` (s2 16 arXiv edges, deterministic 3, crossref 8 ISBN + 16 relation
edges), all written in the run; ISBN 8/8 and relation 11/11 rows complete; arXiv 19/36.

| row | work | mode | run pair | the crosswalk says it gains | what it holds now (asserted_by, written in the run) | S2 asked | verdict |
|---|---|---|---|---|---|---|---|
| L002 | Pfitzmann_2022_doclaynet-large-human-annotated | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2206.01062 (s2) | yes | CORRECT |
| L003 | VanDenHout_2016_multi-state-survival-models | hunt | blocked/challenge | isbn | isbn 9781466568419 (crossref) | yes | CORRECT |
| L005 | Kats_2019_soft-staple-algorithm-combined | hunt | held/duplicate-held | arxiv,isbn | arxiv 1910.12077 (s2); isbn 9783030322472,9783030322489 (crossref) | yes | CORRECT |
| L027 | Herzog_2007_string-comparator-metrics-typographical | hunt | blocked/challenge | isbn | isbn 9780387695020 (crossref) | yes | CORRECT |
| L043 | Wang_2025_comprehensive-survey-forgetting-deep | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2307.09218 (s2) | yes | CORRECT |
| L046 | Lu_2024_optimization-model-selection-domain | hunt | blocked/403 | isbn | isbn 9781611978032 (crossref) | yes | CORRECT |
| L052 | Ventura_2024_individual-tree-detection-large | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2208.10607 (s2) | yes | CORRECT |
| L061 | Tkaczyk_2024_how-good-your-matching | hunt | blocked/challenge | relation,relation | relation is-part-of (crossref); relation is-version-of (crossref) | yes | CORRECT |
| L063 | Tkaczyk_2018_reference-matching-real-this | hunt | bound-unextracted/fresh-bound | relation,relation | relation is-part-of (crossref); relation is-version-of (crossref) | no | CORRECT |
| L064 | Tkaczyk_2025_metadata-matching-beyond-correctness | hunt | blocked/challenge | relation,relation | relation has-version (crossref); relation is-part-of (crossref) | yes | CORRECT |
| L076 | Lahiri_2003_resampling-methods-spatial-data | hunt | blocked/challenge | isbn | isbn 9781441918482,9781475738032 (crossref) | yes | CORRECT |
| L077 | Liu_2018_image-inpainting-irregular-holes | hunt | bound-unextracted/fresh-bound | arxiv,isbn | arxiv 1804.07723 (s2); isbn 9783030012519,9783030012526 (crossref) | yes | CORRECT |
| L081 | Vovk_2013_conditional-validity-inductive-conformal | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 1209.2673 (s2) | yes | CORRECT |
| L082 | Polunchenko_2011_state-art-sequential-change | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 1109.2938 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L090 | Zhang_2021_feature-matching-multi-epoch | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2112.04255 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L109 | Hamraz_2017_forest-understory-trees-can | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 1702.06188 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L126 | Chang_2019_domain-specific-batch-normalization | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 1906.03950 (s2) | yes | CORRECT |
| L127 | Yang_2020_fda-fourier-domain-adaptation | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2004.05498 (s2) | yes | CORRECT |
| L128 | Ding_2021_local-temperature-scaling-probability | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2008.05105 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L129 | Brigato_2021_tune-it-don-t | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2108.13122 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L130 | Arazo_2020_pseudo-labeling-confirmation-bias | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 1908.02983 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L132 | Tuia_2011_survey-active-learning-algorithms | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2104.07784 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L135 | Valindria_2017_reverse-classification-accuracy-predicting | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 1702.03407 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L136 | Weinstein_2020_deepforest-python-package-rgb | hunt | bound-unextracted/fresh-bound | relation,relation | relation has-preprint (crossref); relation has-review (crossref) | yes | CORRECT |
| L149 | Weinstein_2019_individual-tree-crown-detection | hunt | bound-unextracted/fresh-bound | relation | relation has-preprint (crossref) | yes | CORRECT |
| L166 | Tkaczyk_2018_matchmaker-matchmaker-make-me | hunt | blocked/challenge | relation,relation | relation has-version (crossref); relation is-part-of (crossref) | yes | CORRECT |
| L172 | Ball_2023_accurate-delineation-individual-tree | hunt | bound-unextracted/already-bound | relation | relation has-preprint (crossref) | no | CORRECT |
| L173 | Mossina_2025_conformal-prediction-image-segmentation | hunt | blocked/challenge | isbn | isbn 9783032049643,9783032049650 (crossref) | yes | CORRECT |
| L174 | Ranabhat_2026_promoting-shape-bias-cnns | hunt | bound-unextracted/fresh-bound | isbn | isbn 9783032215819,9783032215826 (crossref) | no | CORRECT |
| L175 | MaiaPolo_2022_effective-sample-size-dimensionality | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2010.01184 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L176 | Khoee_2024_domain-generalization-through-meta | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2404.02785 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L177 | Liu_2026_geoai-machine-learning-tools | hunt | blocked/403 | relation | relation has-preprint (crossref) | yes | CORRECT |
| L178 | Zheng_2024_single-temporal-supervised-learning | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2406.15694 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L179 | Bo_2026_saru-shadow-aware-removal | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2604.25432 (s2) | yes | CORRECT |
| L180 | Tolan_2024_very-high-resolution-canopy | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2304.07213 (s2) | yes | CORRECT |
| L181 | Lang_2023_high-resolution-canopy-height | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2204.08322 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L182 | Allred_2025_canopy-height-model-naip | hunt | blocked/403 | relation | relation has-preprint (crossref) | yes | CORRECT |
| L183 | Singh_2024_uncertainty-quantification-probabilistic-machine | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2401.06421 (s2) | yes | CORRECT |
| L184 | Wang_2022_continual-test-time-domain | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2203.13591 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L185 | Wortsman_2022_robust-fine-tuning-zero | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2109.01903 (s2) | yes | CORRECT |
| L186 | Perantoni_2024_bayesian-modelling-multi-year | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2510.07008 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L187 | Yaras_2024_randomized-histogram-matching-simple | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2104.14032 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L188 | Peng_2025_human-annotated-label-noise | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2305.12106 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L189 | Cosarinsky_2026_confic-rca-statistically-grounded | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2503.04522 (s2) | yes | CORRECT |
| L190 | Gong_2026_crossearth-geospatial-vision-foundation | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2410.22629 (s2) | yes | CORRECT |
| L191 | Likowski_2022_misconv-convolutional-neural-networks | hunt | blocked/challenge | arxiv | arxiv 2110.14010 (s2) | yes | CORRECT |
| L192 | Okkaoglu_2024_detecting-departures-conditional-independence | hunt | blocked/403 | relation | relation has-preprint (crossref) | yes | CORRECT |
| L193 | Barber_2023_conformal-prediction-beyond-exchangeability | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2202.13415 (s2) | yes | CORRECT |
| L194 | Deng_2026_semiparametric-analysis-interval-censored | hunt | bound-unextracted/fresh-bound | arxiv | - MISSING arxiv 2601.07044 | no | WRONG (S2 never asked: the hunt stopped at its Wave-1 landing — N2) |
| L195 | Moghimi_2022_automatic-relative-radiometric-normalization | hunt | bound-unextracted/fresh-bound | relation | relation correction (crossref) | yes | CORRECT |
| L196 | Wortsman_2022_model-soups-averaging-weights | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2203.05482 (deterministic) | no | CORRECT |
| L197 | Lala_2023_paperqa-retrieval-augmented-generative | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2312.07559 (deterministic) | no | CORRECT |
| L198 | Lu_2026_conformal-prediction-sets-instance | hunt | bound-unextracted/fresh-bound | arxiv | arxiv 2602.10045 (deterministic) | no | CORRECT |

### The 35 `no-oa-copy` rows — every Wave-1 rung asked all 35; Stage B's only hits are the work; no Stage B bind on the paywalled remainder

Per-work (the plan's negative, C2a F8's "per-attempt vs per-work"): per WORK, 0 wrong binds anywhere in the run; per
ATTEMPT, 2 wrong `measured` credits and 5 rows booked from another work's URL (N1) — so the rule holds per work and
fails per attempt.

| row | work | mode | head probe 09-22 | run pair | Stage B hits (route:status:my verdict) | Stage B bound | verdict |
|---|---|---|---|---|---|---|---|
| L003 | VanDenHout_2016_multi-state-survival-models | hunt | PREVIEW-PDF | blocked/challenge | - | - | CORRECT |
| L005 | Kats_2019_soft-staple-algorithm-combined | hunt | FREE-PDF | held/duplicate-held | arxiv:duplicate-held:CORRECT | - | CORRECT for the rung (the work's arXiv PDF reached); the ROW is WRONG — see the FREE-PDF table |
| L006 | AllenMatthew_2026_manual-labelling-artificia | hunt | - | blocked/challenge | - | - | CORRECT |
| L007 | LPVSubgroup_2025_land-cover-change-accuracy- | hunt | HTML | blocked/challenge | openalex:binding-failed:CORRECT | - | CORRECT |
| L019 | Girard_2019_noisy-supervision-correcting-mis | measure | FREE-PDF | measured/measured | arxiv:measured:CORRECT | - | CORRECT |
| L020 | Subramanian_2021_s2and-benchmark-evaluation- | measure | FREE-PDF | measured/measured | arxiv:measured:CORRECT | - | CORRECT |
| L021 | Bacry_2015_hawkes-processes-finance | measure | FREE-PDF | measured/measured | arxiv:measured:CORRECT | - | CORRECT |
| L022 | Winkler_2014_matching-record-linkage | measure | HTML,status-400 | measured/measured | - | - | CORRECT |
| L023 | McRoberts_2018_effects-imperfect-reference-d | measure | HTML | measured/measured | - | - | CORRECT |
| L024 | Pengra_2020_quality-control-assessment-inter | measure | HTML | measured/measured | - | - | CORRECT |
| L025 | Stehman_2022_incorporating-interpreter-varia | hunt | HTML | blocked/403 | - | - | CORRECT |
| L026 | Nowak_2018_declining-urban-community-tree | measure | HTML | measured/measured | - | - | CORRECT |
| L027 | Herzog_2007_string-comparator-metrics-typogr | hunt | HTML | blocked/challenge | - | - | CORRECT |
| L028 | Bloch_2023_preprintresolver-improving-citati | measure | - | measured/measured | arxiv:measured:CORRECT | - | CORRECT |
| L029 | Kingman_1962_imbedding-problem-finite-markov | hunt | HTML | held/duplicate-held | - | - | CORRECT |
| L030 | Kropp_2024_historical-changes-tree-imperviou | hunt | HTML | blocked/challenge | - | - | CORRECT |
| L031 | Burnicki_2012_impact-error-landscape-pattern | measure | HTML | measured/measured | - | - | CORRECT |
| L032 | Guo_2024_tracking-photosynthetic-phenology-s | hunt | - | blocked/403 | - | - | CORRECT |
| L033 | Chen_2014_assessment-image-misregistration-e | measure | - | measured/measured | - | - | CORRECT |
| L034 | Kennedy_2010_detecting-trends-forest-disturb | measure | - | measured/measured | - | - | CORRECT |
| L035 | Cohen_2010_detecting-trends-forest-disturban | measure | - | measured/measured | - | - | CORRECT |
| L036 | Stehman_1998_design-analysis-thematic-map | hunt | - | blocked/403 | - | - | CORRECT |
| L037 | Enamorado_2019_probabilistic-model-assist-me | hunt | HTML | blocked/challenge | - | - | CORRECT |
| L038 | Ogata_1998_space-time-point-process | measure | HTML | measured/measured | - | - | CORRECT |
| L039 | Fellegi_1969_theory-record-linkage | measure | - | measured/measured | - | - | CORRECT |
| L040 | Strong_2003_edge-preserving-scale-dependent | hunt | HTML | blocked/challenge | - | - | CORRECT |
| L041 | Mei_2010_efficient-scalable-schemes-monitori | measure | HTML | measured/measured | - | - | CORRECT |
| L042 | Sosa_2025_multimae-meets-earth-observation | hunt | - | bound-unextracted/fresh-bound | - | - | CORRECT |
| L043 | Wang_2025_comprehensive-survey-forgetting-de | hunt | - | bound-unextracted/fresh-bound | arxiv:ok:CORRECT | arxiv | CORRECT (a bind the 09-22 head probe never probed; my reader: the work) |
| L044 | Chernozhukov_2018_double-debiased-machine-le | measure | status-400 | measured/measured | - | - | CORRECT |
| L045 | Marsan_2008_extending-earthquakes-reach-thro | measure | - | measured/measured | - | - | CORRECT |
| L046 | Lu_2024_optimization-model-selection-domain | hunt | - | blocked/403 | - | - | CORRECT |
| L047 | Liu_2019_misregistration-tolerant-change-det | measure | - | measured/measured | - | - | CORRECT |
| L048 | Kopcke_2010_evaluation-entity-resolution-app | hunt | - | blocked/403 | - | - | CORRECT |
| L049 | Konda_2016_magellan-work | hunt | - | blocked/403 | - | - | CORRECT |

### Every PDF a Stage B rung reached (102 attempts, 81 distinct PDFs), my reader vs the recorded Crossref record

| attempt | work (row) | route | status | sha256[:12] | pages (mine) | Crossref range | title-window ratio / author | verdict (mine) |
|---|---|---|---|---|---|---|---|---|
| 01a0d2ed-b08b | Bacry_2015_hawkes-processes-finance (L021) | arxiv | measured | a4dd4a8e65c4 | 48 | - | 1.00/A | CORRECT |
| 01a0d4a3-91ca | Barber_2023_conformal-prediction-beyond-exchangeability (L193) | arxiv | ok | 7d09be24289d | 63 | - | 1.00/A | CORRECT |
| 01a0d283-2159 | Bloch_2023_preprintresolver-improving-citation-quality (L028) | arxiv | measured | 63821e321da6 | 15 | 15 | 1.00/A | CORRECT |
| 01a0d2f5-bb51 | Bloch_2023_preprintresolver-improving-citation-quality (L028) | arxiv | measured | 63821e321da6 | 15 | 15 | 1.00/A | CORRECT |
| 01a0d49f-43f7 | Bo_2026_saru-shadow-aware-removal (L179) | arxiv | ok | d81a5e815737 | 18 | 15 | 1.00/A | CORRECT |
| 01a0d489-09e3 | Chang_2019_domain-specific-batch-normalization (L126) | arxiv | ok | 0dbc2d358a97 | 9 | 9 | 1.00/A | CORRECT |
| 01a0d4a1-5ce2 | Cosarinsky_2026_confic-rca-statistically-grounded (L189) | arxiv | ok | cb0d97c1dcbb | 13 | 13 | 1.00/A | CORRECT |
| 01a0d448-d4b6 | Culbert_2025_reference-coverage-analysis-openalex (L051) | arxiv | measured | f99099e8ca11 | 20 | 18 | 1.00/A | CORRECT |
| 01a0d2a1-6985 | Girard_2019_noisy-supervision-correcting-misaligned (L019) | arxiv | measured | 9c9d67862c0b | 4 | 4 | 1.00/A | CORRECT |
| 01a0d2eb-462a | Girard_2019_noisy-supervision-correcting-misaligned (L019) | arxiv | measured | 9c9d67862c0b | 4 | 4 | 1.00/A | CORRECT |
| 01a0d4a1-a323 | Gong_2026_crossearth-geospatial-vision-foundation (L190) | arxiv | ok | b44e9d5cf529 | 34 | 18 | 1.00/A | CORRECT |
| 01a0d28f-6533 | Kats_2019_soft-staple-algorithm-combined (L005) | arxiv | duplicate-held | d54e42ec8dee | 9 | 8 | 1.00/A | CORRECT |
| 01a0d4a1-f80e | Likowski_2022_misconv-convolutional-neural-networks (L191) | arxiv | binding-failed | fe03e97dcf39 | 14 | 10 | 1.00/A | CORRECT |
| 01a0d463-2e6c | Liu_2018_image-inpainting-irregular-holes (L077) | arxiv | ok | d0753c271d14 | 23 | 17 | 1.00/A | CORRECT |
| 01a0d28d-a1c4 | Pfitzmann_2022_doclaynet-large-human-annotated (L002) | arxiv | ok | 5dfbd8c115a1 | 9 | 9 | 0.89/A | CORRECT |
| 01a0d4a0-8634 | Singh_2024_uncertainty-quantification-probabilistic-machine (L183) | arxiv | ok | ab0f16bada0e | 46 | - | 1.00/A | CORRECT |
| 01a0d2eb-c6e3 | Subramanian_2021_s2and-benchmark-evaluation-system (L020) | arxiv | measured | fb8528da8901 | 10 | 10 | 1.00/A | CORRECT |
| 01a0d49f-765c | Tolan_2024_very-high-resolution-canopy (L180) | arxiv | ok | 2a85ea6ba64a | 37 | - | 1.00/A | CORRECT |
| 01a0d449-7cb8 | Ventura_2024_individual-tree-detection-large (L052) | arxiv | ok | 91597a877f87 | 14 | - | 1.00/A | CORRECT |
| 01a0d464-7346 | Vovk_2013_conditional-validity-inductive-conformal (L081) | arxiv | ok | 759684870def | 23 | 28 | 1.00/A | CORRECT |
| 01a0d30c-f8de | Wang_2025_comprehensive-survey-forgetting-deep (L043) | arxiv | ok | b8bb1dcb2167 | 25 | 20 | 1.00/A | CORRECT |
| 01a0d4a0-b15b | Wortsman_2022_robust-fine-tuning-zero (L185) | arxiv | ok | 2c94c2d7741e | 51 | 13 | 1.00/A | CORRECT |
| 01a0d489-1bd2 | Yang_2020_fda-fourier-domain-adaptation (L127) | arxiv | ok | 7b7016a24729 | 11 | 11 | 1.00/A | CORRECT |
| 01a0d499-4ab0 | Hessel_2020_relative-radiometric-normalization-several (L163) | crossref-link | measured | 663ebfa92d13 | 8 | 8 | 1.00/A | CORRECT |
| 01a0d499-6286 | Hoberg_2012_context-models-crf-based (L164) | crossref-link | measured | 850966f21fa3 | 6 | 6 | 1.00/A | CORRECT |
| 01a0d4a1-2c75 | Peng_2025_human-annotated-label-noise (L188) | crossref-link | ok | 74931bd91517 | 15 | 15 | 1.00/A | CORRECT |
| 01a0d458-7ac9 | Tkaczyk_2018_reference-matching-real-this (L063) | crossref-link | ok | 254b3765fe98 | 10 | - | 1.00/A | CORRECT |
| 01a0d48d-cb77 | Valindria_2017_reverse-classification-accuracy-predicting (L135) | crossref-link | ok | 7f4b0ed4dc75 | 10 | 10 | 1.00/A | CORRECT |
| 01a0d4a1-01ef | Yaras_2024_randomized-histogram-matching-simple (L187) | crossref-link | measured | 997569c3b85b | 11 | 11 | 1.00/A | CORRECT |
| 01a0d48e-efcc | Rosa_2013_predictive-modelling-contagious-deforestation (L140) | doaj | measured | b6cd3f0146ae | 14 | - | 1.00/A | CORRECT |
| 01a0d45f-0192 | Coulter_2008_assessment-spatial-co-registration (L074) | europepmc | measured | 958ff7472a1c | 13 | 13 | 1.00/A | CORRECT |
| 01a0d489-5287 | Arazo_2020_pseudo-labeling-confirmation-bias (L130) | open_access | ok | a6990593eaba | 8 | 8 | 1.00/A | CORRECT |
| 01a0d289-0bb3 | Ball_2023_accurate-delineation-individual-tree (L172) | open_access | ok | 9965da2f3765 | 14 | 15 | 0.93/A | CORRECT |
| 01a0d489-3c86 | Brigato_2021_tune-it-don-t (L129) | open_access | ok | dbabfcef3e39 | 10 | 10 | 1.00/A | CORRECT |
| 01a0d499-a268 | Chen_2014_true-orthophoto-generation-multi (L165) | open_access | binding-failed | da40796b79ce | 5 | 5 | 1.00/A | CORRECT |
| 01a0d498-a7ad | Chen_2020_deep-siamese-domain-adaptation (L162) | open_access | ok | d8759a53912c | 4 | - | 1.00/A | CORRECT |
| 01a0d4a3-9ea1 | Deng_2026_semiparametric-analysis-interval-censored (L194) | open_access | ok | 9ecc32021743 | 32 | - | 1.00/A | CORRECT |
| 01a0d489-2a30 | Ding_2021_local-temperature-scaling-probability (L128) | open_access | ok | b14814b6ba2d | 42 | 11 | 1.00/A | CORRECT |
| 01a0d492-2540 | Graler_2016_spatio-temporal-interpolation-gstat (L145) | open_access | ok | b9f439c51870 | 15 | - | 1.00/A | CORRECT |
| 01a0d49d-658b | Gulrajani_2020_search-lost-domain-generalization (L171) | open_access | measured | 92ea5bb1b5be | 27 | - | 1.00/A | CORRECT |
| 01a0d479-e102 | Hamraz_2017_forest-understory-trees-can (L109) | open_access | ok | 3d6151104116 | 9 | - | 1.00/A | CORRECT |
| 01a0d499-4813 | Hessel_2020_relative-radiometric-normalization-several (L163) | open_access | ok | 663ebfa92d13 | 8 | 8 | 1.00/A | CORRECT |
| 01a0d499-61a1 | Hoberg_2012_context-models-crf-based (L164) | open_access | ok | 850966f21fa3 | 6 | 6 | 1.00/A | CORRECT |
| 01a0d492-1276 | Howard_2018_universal-language-model-fine (L144) | open_access | ok | 357805f5bbe6 | 12 | 12 | 1.00/A | CORRECT |
| 01a0d498-7b96 | Hwang_2020_geospatial-methods-tree-canopy (L160) | open_access | ok | 5faa4536ef03 | 15 | 15 | 1.00/A | CORRECT |
| 01a0d49c-7601 | Jaffe_2014_estimating-accuracies-multiple-classifiers (L169) | open_access | measured | 8d523cc20724 | 27 | - | 1.00/A | CORRECT |
| 01a0d49e-7b88 | Khoee_2024_domain-generalization-through-meta (L176) | open_access | ok | fc621bdf0954 | 40 | - | 1.00/A | CORRECT |
| 01a0d498-5bb4 | King_2013_comparison-three-methods-measuring (L159) | open_access | ok | 774de9a1cd14 | 6 | - | 1.00/A | CORRECT |
| 01a0d49c-f982 | Kumar_2019_verified-uncertainty-calibration (L170) | open_access | measured | cc4e4bde39f5 | 38 | - | 1.00/A | CORRECT |
| 01a0d4a4-370b | Lala_2023_paperqa-retrieval-augmented-generative (L197) | open_access | ok | 6b3178322242 | 20 | - | 1.00/a | CORRECT — by my reading: my read of page 1: 'PaperQA: Retrieval-Augmented Generative Agent for Scientific Research', Jakub Lála et al. - the work (the accent is extracted as a separate glyph, so my surname fold missed it) |
| 01a0d4a4-4997 | Lu_2026_conformal-prediction-sets-instance (L198) | open_access | ok | 02ad0159bbd4 | 28 | - | 1.00/A | CORRECT |
| 01a0d492-4582 | Ma_2021_multi-task-deep-supervision (L146) | open_access | ok | 2e10315a0cc2 | 14 | - | 1.00/A | CORRECT |
| 01a0d49e-4b65 | MaiaPolo_2022_effective-sample-size-dimensionality (L175) | open_access | ok | ccf0ce4d1a1a | 15 | 13 | 1.00/A | CORRECT |
| 01a0d48e-d8d2 | Miller_2013_determining-occurrence-dynamics-when (L139) | open_access | ok | aef5677805be | 9 | - | 1.00/A | CORRECT |
| 01a0d4a0-bb78 | Perantoni_2024_bayesian-modelling-multi-year (L186) | open_access | ok | aecd0484f69c | 5 | 5 | 1.00/A | CORRECT |
| 01a0d464-82d8 | Polunchenko_2011_state-art-sequential-change (L082) | open_access | ok | fa4c1c9f756a | 34 | 36 | 1.00/A | CORRECT |
| 01a0d49e-40c8 | Ranabhat_2026_promoting-shape-bias-cnns (L174) | open_access | ok | 55f8563877c2 | 12 | 11 | 1.00/A | CORRECT |
| 01a0d498-9802 | Ro_2020_autolr-layer-wise-pruning (L161) | open_access | ok | 7401a4a2bb85 | 10 | - | 1.00/A | CORRECT |
| 01a0d48e-ec4e | Rosa_2013_predictive-modelling-contagious-deforestation (L140) | open_access | ok | b6cd3f0146ae | 14 | - | 1.00/A | CORRECT |
| 01a0d285-06dc | Ross_2012_sequential-monitoring-bernoulli-sequence (L078) | open_access | ok | 21c31deebbca | 19 | 17 | 1.00/A | CORRECT |
| 01a0d486-b887 | Tarko_2020_producing-consistent-visually-interpreted (L121) | open_access | ok | 65c9f625437a | 20 | 19 | 1.00/A | CORRECT |
| 01a0d48a-9e86 | Tuia_2011_survey-active-learning-algorithms (L132) | open_access | ok | 1f73eae52341 | 29 | 12 | 1.00/A | CORRECT |
| 01a0d28a-0713 | Valavi_2018_blockcv-r-package-generating (L001) | open_access | measured | c993c66fe8ab | 19 | - | 0.99/A | CORRECT |
| 01a0d458-64ee | VelasquezCamacho_2025_monitoring-temporal-changes-large (L062) | open_access | ok | 8c37309e0280 | 20 | - | 1.00/A | CORRECT |
| 01a0d49b-fb3c | Vixie_2007_some-properties-minimizers-chan (L168) | open_access | measured | 647f940ff541 | 14 | - | 0.99/A | CORRECT |
| 01a0d4a0-96b6 | Wang_2022_continual-test-time-domain (L184) | open_access | ok | 051e84bee98a | 11 | 11 | 1.00/A | CORRECT |
| 01a0d48e-c821 | Wasser_2013_influence-vegetation-structure-lidar (L138) | open_access | ok | 5de13a732792 | 13 | - | 1.00/A | CORRECT |
| 01a0d4a4-2bdb | Wortsman_2022_model-soups-averaging-weights (L196) | open_access | ok | 226ac91243bd | 34 | - | 1.00/A | CORRECT |
| 01a0d4a0-fd40 | Yaras_2024_randomized-histogram-matching-simple (L187) | open_access | ok | d9188fe4d965 | 12 | 11 | 1.00/A | CORRECT |
| 01a0d46a-3249 | Zhang_2021_feature-matching-multi-epoch (L090) | open_access | ok | 69303bfdc3f2 | 34 | 14 | 1.00/A | CORRECT |
| 01a0d49f-1eaf | Zheng_2024_single-temporal-supervised-learning (L178) | open_access | ok | b55b146a5d4d | 21 | 21 | 1.00/A | CORRECT |
| 01a0d489-5428 | Arazo_2020_pseudo-labeling-confirmation-bias (L130) | openaire | measured | a903862fed01 | 8 | 8 | 1.00/A | CORRECT |
| 01a0d46a-feec | Canty_2008_automatic-radiometric-normalization (L092) | openaire | ok | fdbb7f1cb1f9 | 12 | 12 | 1.00/A | CORRECT |
| 01a0d45e-f77b | Coulter_2008_assessment-spatial-co-registration (L074) | openaire | measured | 9281883cbca1 | 5 | 13 | 0.52/a | WRONG — by my reading: my read of page 1: 'Quality Metrics of Semi Automatic DTM from Large Format Digital Camera' (Narendran et al., ISPRS Archives XL-8, 2014, 5 pp) - another work; its URL sits under the OpenAIRE answer's <rels> (IsAmongTopNSimilarDocuments) |
| 01a0d498-7f5a | Hwang_2020_geospatial-methods-tree-canopy (L160) | openaire | measured | 5faa4536ef03 | 15 | 15 | 1.00/A | CORRECT |
| 01a0d493-caf0 | Kokubu_2020_mapping-seasonal-tree-canopy (L150) | openaire | binding-failed | 31325d05ea5f | 18 | - | 0.47/a | WRONG — by my reading: my read of page 1: MacGregor et al. 2020, 'The age of surface-exposed ice along the northern margin of the Greenland Ice Sheet', J. Glaciology - another work (the binder refused it: correct); URL under <rels> |
| 01a0d49f-e133 | Lang_2023_high-resolution-canopy-height (L181) | openaire | ok | a2659363590c | 29 | 12 | 1.00/A | CORRECT |
| 01a0d284-faf5 | Li_2022_identification-undocumented-buildings-cadastral (L065) | openaire | ok | 22891d074f62 | 11 | - | 1.00/A | CORRECT |
| 01a0d469-803f | Mboga_2020_fully-convolutional-networks-land (L089) | openaire | ok | 00d4faffc439 | 22 | 11 | 1.00/A | CORRECT |
| 01a0d459-c88d | Ploton_2020_spatial-validation-reveals-poor (L066) | openaire | measured | 897445ab6aef | 11 | - | 1.00/A | CORRECT |
| 01a0d486-7cf1 | Pontius_2017_methods-summarize-change-among (L120) | openaire | ok | f1d74a300708 | 30 | 13 | 0.64/A | CORRECT — by my reading: my read of page 1: White Rose Research Online accepted-manuscript cover naming Pontius et al. 2017 'Methods to summarize change among land categories across time intervals', doi 10.1080/1747423x.2017.1338768 - the work (AAM, 30 pp) |
| 01a0d48d-98f0 | Ramani_2008_monte-carlo-sure-black (L134) | openaire | ok | 1613843c9fdf | 15 | 15 | 1.00/A | CORRECT |
| 01a0d46a-34ca | Zhang_2021_feature-matching-multi-epoch (L090) | openaire | measured | 9f32e13452cd | 8 | 14 | 0.83/A | WRONG — by my reading: my read of page 1: 'Guided feature matching for multi-epoch historical image blocks pose estimation' (ISPRS Annals V-2-2020, 8 pp) - another paper by the same authors, not the 14-page ISPRS J. article; URL under <rels> |
| 01a0d289-0d34 | Ball_2023_accurate-delineation-individual-tree (L172) | openalex | measured | 9965da2f3765 | 14 | 15 | 0.93/A | CORRECT |
| 01a0d492-25f6 | Graler_2016_spatio-temporal-interpolation-gstat (L145) | openalex | measured | b9f439c51870 | 15 | - | 1.00/A | CORRECT |
| 01a0d499-4d39 | Hessel_2020_relative-radiometric-normalization-several (L163) | openalex | measured | 663ebfa92d13 | 8 | 8 | 1.00/A | CORRECT |
| 01a0d499-634d | Hoberg_2012_context-models-crf-based (L164) | openalex | measured | 850966f21fa3 | 6 | 6 | 1.00/A | CORRECT |
| 01a0d492-1344 | Howard_2018_universal-language-model-fine (L144) | openalex | measured | 357805f5bbe6 | 12 | 12 | 1.00/A | CORRECT |
| 01a0d498-7d75 | Hwang_2020_geospatial-methods-tree-canopy (L160) | openalex | measured | 5faa4536ef03 | 15 | 15 | 1.00/A | CORRECT |
| 01a0d49e-7f5d | Khoee_2024_domain-generalization-through-meta (L176) | openalex | measured | 3b711711bbf4 | 40 | - | 1.00/A | CORRECT |
| 01a0d498-5c45 | King_2013_comparison-three-methods-measuring (L159) | openalex | measured | 774de9a1cd14 | 6 | - | 1.00/A | CORRECT |
| 01a0d293-478a | LPVSubgroup_2025_land-cover-change-accuracy-protocol (L007) | openalex | binding-failed | 41c07271c178 | 188 | - | 1.00/A | CORRECT |
| 01a0d492-4767 | Ma_2021_multi-task-deep-supervision (L146) | openalex | measured | 2e10315a0cc2 | 14 | - | 1.00/A | CORRECT |
| 01a0d48e-da96 | Miller_2013_determining-occurrence-dynamics-when (L139) | openalex | measured | aef5677805be | 9 | - | 1.00/A | CORRECT |
| 01a0d48e-ee18 | Rosa_2013_predictive-modelling-contagious-deforestation (L140) | openalex | measured | b6cd3f0146ae | 14 | - | 1.00/A | CORRECT |
| 01a0d486-b9d8 | Tarko_2020_producing-consistent-visually-interpreted (L121) | openalex | measured | 65c9f625437a | 20 | 19 | 1.00/A | CORRECT |
| 01a0d28a-084a | Valavi_2018_blockcv-r-package-generating (L001) | openalex | measured | 706cc664018f | 19 | - | 0.99/A | CORRECT |
| 01a0d458-686d | VelasquezCamacho_2025_monitoring-temporal-changes-large (L062) | openalex | measured | 8c37309e0280 | 20 | - | 1.00/A | CORRECT |
| 01a0d4a0-980a | Wang_2022_continual-test-time-domain (L184) | openalex | measured | 051e84bee98a | 11 | 11 | 1.00/A | CORRECT |
| 01a0d48e-c92f | Wasser_2013_influence-vegetation-structure-lidar (L138) | openalex | measured | 5de13a732792 | 13 | - | 1.00/A | CORRECT |
| 01a0d4a1-0526 | Yaras_2024_randomized-histogram-matching-simple (L187) | openalex | measured | d9188fe4d965 | 12 | 11 | 1.00/A | CORRECT |
| 01a0d48e-b7d5 | Berra_2020_individual-tree-crown-detection (L137) | s2 | ok | 1f0a3ee406aa | 32 | - | 0.97/A | CORRECT |

### Per-rung yields (every Stage B rung; the 35 no-oa-copy rows at the right)

| route | printed `yield:` | mine (conv/asked) | verified by my reader | net-new over Unpaywall | no-oa-copy rows: asked / conv / verified |
|---|---|---|---|---|---|
| eartharxiv | 0/187 | 0/187 | 0 | 0 | 35 / 0 / 0 |
| publisher-url | 0/18 | 0/18 | 0 | 0 | 2 / 0 / 0 |
| opencitations | 0/187 | 0/187 | 0 | 0 | 35 / 0 / 0 |
| crossref-link | 6/187 | 6/187 | 6 | 6 | 35 / 0 / 0 |
| openalex | 17/187 | 17/187 | 17 | 0 | 35 / 0 / 0 |
| doaj | 1/187 | 1/187 | 1 | 1 | 35 / 0 / 0 |
| openaire | 11/187 | 11/187 | 9 | 9 | 35 / 0 / 0 |
| hal | 0/187 | 0/187 | 0 | 0 | 35 / 0 / 0 |
| osf | 0/1 | 0/1 | 0 | 0 | 0 / 0 / 0 |
| datacite | 0/7 | 0/7 | 0 | 0 | 2 / 0 / 0 |
| zenodo | 0/1 | 0/1 | 0 | 0 | 1 / 0 / 0 |
| figshare | 0/0 | 0/0 | 0 | 0 | 0 / 0 / 0 |
| ncbi-idconv | 0/144 | 0/144 | 0 | 0 | 35 / 0 / 0 |
| s2 | 1/144 | 1/144 | 1 | 1 | 35 / 0 / 0 |
| europepmc | 1/12 | 1/12 | 1 | 1 | 0 / 0 / 0 |
| arxiv | 19/26 | 19/21 | 19 | 19 | 6 / 5 / 5 |
| venue | 0/128 | 0/128 | 0 | 0 | 33 / 0 / 0 |
| open_access | 39/170 | 39/170 | 39 | 39 | 18 / 0 / 0 |

## The fan-out kill criterion — scored by a non-proposer, `eligible` recomputed over the rows RUN

The survey's bar (LINKAGE §5.3, S6: "does not fill … for a majority of the 406 DOI tracker rows") re-stated against
`arxiv pii dblp isbn md5`; the proposer printed `kill-criterion: KEEP` by its per-scheme bar gained > eligible/2.
**Rows run = 195 of 198 → 187 works; the 3 dropped rows (L004 L008 L009) add no crosswalk key, so `eligible` over the
rows RUN equals the manifest's** — the printed eligible numbers stand.

| scheme | eligible (rows RUN) | held at frozen_at | gained in the run (any writer) | the holding service ASKED / gained among them | value = crosswalk value | files this session through the scheme | proposer's bar | my verdict |
|---|---|---|---|---|---|---|---|---|
| arxiv | 41 | 0 | 24 (21 S2 edges + 3 deterministic 10.48550) | S2 21 / 21 | 24/24 | **14 bound** (every arxiv-route bind fetched an id from an S2 edge written in the run) + 5 measured | 21/41 — passes by half a work | **KEEP** |
| pii | 43 | 0 | 43 (crossref) | Crossref 43 / 43 | 43/43 | 0 (Stage C asked Elsevier pdfft on 36 rows: all `blocked/challenge_or_bot_check`) | 43/43 | **KEEP** on recall; file value UNDETERMINED until entitlement |
| dblp | 66 | 0 | 44 (s2) | S2 44 / 44 | 44/44 | 0 (no file rung reads dblp; venue 0/128) | 44/66 | **KEEP** on recall (rides the S2 call already made: no extra request); file value 0 |
| isbn | 9 | 0 | 9 (crossref, 15 versions) | Crossref 9 / 9 | 9/9 | 0 (books are S4.6) | 9/9 | **KEEP** on recall; file value deferred |
| md5 | n/a | — | 0 | no source wired | — | — | n/a | **UNDETERMINED** — structurally 0, cannot be scored |

**Overall: KEEP.** My ruling on the bar: (1) the survey's literal denominator (a majority of ALL DOI rows) cannot answer
KEEP for a sparse scheme — arXiv's ceiling here is 41/187 = 22 % — so it is not a test; (2) the proposer's per-scheme
`gained > eligible/2` is a sound RECALL test only if `eligible` counts works the holding service was ASKED: as printed it
also counts the 20 arXiv / 22 dblp works the first-landing stop kept from S2 (N2), which is why arxiv passes by half a
work while its recall where asked is 21/21; (3) recall alone does not show worth — only arxiv turned identifiers into
files this session (14 new binds, none of which a Wave-1 rung had landed in those hunts). **The statement can FIRE:**
control KEEP; CONSTRUCTED known-bad (the fan-out's writes counted as none: `STAGE_B_SERVICES` emptied in-process,
restored) → every `kill:` line 0/187 and `kill-criterion: KILL`; my own oracle's known-bad (every run-written
identifier/edge removed) → 0/41, 0/43, 0/66, 0/9 → KILL (`kill_fire.out`).

Rests on a survey no different-model-family read covered: the kill criterion itself (Codex reviewed Stage B's order and
closure, not §5.3's bar); B9's URL walk (relayed from paper-search-mcp, the source of N1); B3's net-new dispute (now
measured 0); B12's zero (now measured 1/12). Codex SUPPORTED the closure rule; its interplay with the first-landing stop
(N2) was seen by nobody before the real rows.

## (c) re-fires — every Stage B known-bad, pasted verbatim (`PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w6 py -3.12 qc/instruments/litkb_acceptance.py hardening --fire <name> --db litkb_test_w6`, each exit 0)

```
fire=b1_disabled_kats (litkb_hardening_c2a) arm=control free_ceiling_measured_unconverted=0 (bound =0)
fire=b1_disabled_kats (litkb_hardening_c2a) arm=known_bad free_ceiling_measured_unconverted=1 (bound =0)
fire=b1_disabled_kats FIRED
fire=harvest_disabled_crosswalk (litkb_hardening_b1) arm=control crosswalk_rows_without_identifier=0 (bound =0)
fire=harvest_disabled_crosswalk (litkb_hardening_b1) arm=known_bad crosswalk_rows_without_identifier=3 (bound =0)
fire=harvest_disabled_crosswalk FIRED
fire=harvest_disabled_crosswalk_isbn (litkb_hardening_b1) arm=control crosswalk_rows_without_identifier=0 (bound =0)
fire=harvest_disabled_crosswalk_isbn (litkb_hardening_b1) arm=known_bad crosswalk_rows_without_identifier=1 (bound =0)
fire=harvest_disabled_crosswalk_isbn FIRED
fire=harvest_disabled_crosswalk_relation (litkb_hardening_b1) arm=control crosswalk_rows_without_identifier=0 (bound =0)
fire=harvest_disabled_crosswalk_relation (litkb_hardening_b1) arm=known_bad crosswalk_rows_without_identifier=1 (bound =0)
fire=harvest_disabled_crosswalk_relation FIRED
fire=harvest_disabled_crosswalk_c2a (litkb_hardening_c2a) arm=control crosswalk_rows_without_identifier=0 (bound =0)
fire=harvest_disabled_crosswalk_c2a (litkb_hardening_c2a) arm=known_bad crosswalk_rows_without_identifier=1 (bound =0)
fire=harvest_disabled_crosswalk_c2a FIRED
fire=yield_line_deleted (litkb_hardening_a) arm=control stage_b_rungs_unmeasured=0 (bound =0)
fire=yield_line_deleted (litkb_hardening_a) arm=known_bad stage_b_rungs_unmeasured=1 (bound =0)
fire=yield_line_deleted FIRED
```

**6/6 FIRED.**

fired: free_ceiling_measured_unconverted=1 on Kats_2019 with the B1 rung disabled (b1_disabled_kats, litkb_test_w6)
fired: crosswalk_rows_without_identifier=3 on the crosswalk's arXiv-id works re-hunted with the harvest disabled (harvest_disabled_crosswalk, litkb_test_w6)
fired: crosswalk_rows_without_identifier=1 on an ISBN carrier with the ISBN harvest disabled (harvest_disabled_crosswalk_isbn, litkb_test_w6)
fired: crosswalk_rows_without_identifier=1 on a relation carrier with the relation harvest disabled (harvest_disabled_crosswalk_relation, litkb_test_w6)
fired: crosswalk_rows_without_identifier=1 on a crosswalk row through the ladder with the harvest write disabled (harvest_disabled_crosswalk_c2a, litkb_test_w6)
fired: stage_b_rungs_unmeasured=1 on the report with a Stage B yield line deleted (yield_line_deleted, litkb_test_w6)

## My own mutations (not in any builder's mutation row; one exact occurrence each; one pytest process on litkb_test_w6; restored, sha256 re-checked)

Control first (unmutated): my real-data test + `qc/test_litkb_s45_identity.py` + `qc/test_litkb_stage_ab.py` →
`104 passed in 56.84s`, exit 0. `pipeline/litkb/admit/harvest.py` sha256 b388e9a7…dc90e before and after both.

- **M1** — `litkb.admit.harvest.from_s2`: `("DBLP", "dblp"), ("CorpusId", "s2")` → `("CorpusId", "s2")` (S2's DBLP key no
  longer harvested — the kill criterion's dblp scheme). My test `test_referee_s2_dblp_real.py` (scratch; the oracle is
  the recorded S2 JSON field itself, over every DBLP-bearing S2 answer this run recorded) → **RED by AssertionError**:
  `AssertionError: 44 of 44 recorded DBLP keys not harvested, e.g. [('10.1007/978-3-030-01252-6_6', 'conf/eccv/LiuRSWTC18', []), …]`;
  summary `1 failed, 103 passed in 55.37s`, exit 1. **The builders' 103 tests stayed green: SURVIVED there (N8).**
  Restore sha match: True.
- **M2** — the same file: `if elsevier and I.valid("pii", alt):` → `if I.valid("pii", alt):` (any publisher's
  alternative-id taken as a PII). → **RED by AssertionError** in
  `qc/test_litkb_s45_identity.py::test_crossref_harvest_reads_the_fields_it_used_to_discard`; `1 failed, 102 passed in
  50.58s`, exit 1. Restore sha match: True.

fired: dblp_keys_unharvested=44 on the run's 44 recorded DBLP-bearing S2 answers with the DBLP harvest dropped (own mutation M1, my real-data test, litkb_test_w6)

## Not done, and why

No fix written (a referee scores; N1/N2 fixes are the orchestrator's, and need a re-freeze + re-run). No live write, no
network, no commit. The LADDER1 report does not exist yet, so `stage_b_rungs_unmeasured` was not read against it; my
yield table agrees with the printed lines for 17/18 routes (arxiv differs by definition, N5). The replay, vocabulary
(the `blocked` rows N1 created) and stage-e (the Wayback leg of IIASA) questions are those referees'. Observation for
the replay referee, not scored: the cassette index holds 3,632 interactions where the recording report says
`entries: 3509`.

Working notes: every script named above and its output (`*.out`, `*.json`) in `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-stage-b\` — the harness refused this subagent a separate notes .md, so the scratch folder is the notes.
