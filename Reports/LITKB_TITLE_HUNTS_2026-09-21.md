# litkb title-resolution hunts — register rows E20, E21, E22, E23, E24

**Date:** 2026-09-21 (hunts ran 2026-09-22 01:24–01:36 UTC) · **Workstream:** `title-hunts-1`
(`01a0c6b6-33ae-720b-b896-6c3c8534c5ab`, branch `work/20260921-litkb-title-hunts`) ·
**Agent/session:** `claude` / `s3-wrap-hunts-1` · **Row table:** `LITKB_TITLE_HUNTS_2026-09-21.csv`
(40 rows: 37 tracker rows + E20 + E21 + E22).

Every number here came from a command in this job: the `litkb hunt` / `hunt-request add` CLI
(37 title hunts, 3 identifier/title hunts), `api.crossref.org/works/<doi>` for 66 DOIs, and
`doi.org/api/handles/<doi>` for the six DOIs Crossref answered 404 on. Nothing is restated from
`LITKB_HELD_QUEUE_2026-09-15.md`.

---

## 1. The headline: 0 of 37 resolved, and the reason is structural

| outcome | count |
|---|---|
| E23 `skipped-low` rows hunted | 15 |
| E24 `refused-check1` rows hunted | 22 |
| resolved (a work admitted by title) | **0** |
| `refused` / `ambiguous-title` | **37 of 37** |
| `unresolved-title` (no registry candidate at all) | 0 |

**Mechanism.** A `title` hunt does not bypass the check that refused these rows — it *is* that
check. `litkb.hunt.resolve_title` delegates the whole decision to
`litkb.admit.resolver.resolve_doi`, whose `judge_candidate`
(`Scripts/pipeline/litkb/admit/resolver.py:112-128`) accepts a candidate only if **all three** hold:
title ratio ≥ `RESOLVE_TITLE_RATIO` (= 0.85, line 27), the first-author family name matches, and the
year is within ±1. Those are the same three comparisons admission check 1 makes. So a row whose
claimed first author or claimed year contradicts Crossref cannot resolve by title either: the claim
is the resolver's *input*, not something the title route routes around.

That makes the E24 half of Kam's ruling unachievable as stated, and the measurement is the answer:
**the 16 E24 rows whose title matched at ≥0.85 all landed on the DOI already stored for them** — the
stored DOIs are right and the tracker's author/year claims are what is wrong. `resolver_detail`
reports only the highest-*ratio* candidate, so a refusal at ratio 1.00 means the title matched
exactly and the author or the year did not.

**Reading the CSV's `resolved_doi` column.** For a refused hunt it holds the *best candidate gate 0
named and rejected* — never an admitted DOI. `title_ratio` is that candidate's ratio; anything below
0.85 is the resolver saying "this is not the work you asked for", and those rows are scored
`unresolved`, not `tracker-doi-wrong`.

### Hunt states, all 40 rows

| state / reason | count | rows |
|---|---|---|
| `refused` / `ambiguous-title` | 38 | the 37 tracker rows + E22 |
| `blocked` / `403` | 1 | E20 (the book) |
| `bound-unextracted` / `fresh-bound` | 1 | E21 (the bioRxiv preprint) |
| `held`, `api-error`, `crashed`, `extracted` | 0 | — |

### Verdicts

| class | verdict | count |
|---|---|---|
| E23 | `unresolved` | 15 |
| E23 | `resolved` | 0 |
| E24 | `registry-quirk` (title matched ≥0.85, same DOI as stored) | 16 |
| E24 | `unresolved` (best candidate below 0.85) | 6 |
| E24 | `tracker-doi-wrong` | 0 |
| E24 | `dead-doi` | 0 |

`tracker-doi-wrong` is 0 **against `stored_doi`**, which is what the ruling named. Against the
tracker's own `DOI/URL` column it is 7 — see §4.

### The refusal, verbatim

All 38 refused hunts returned one and the same `message` (and `reason` `ambiguous-title`):

> "a registry candidate was found for this title and gate 0 refused it: the title ratio, the
> first-author family name or the year did not agree. litkb does not admit a work it is not sure is
> the one asked for."

Each row's `refusals[0]` also carries `resolver_detail` (`best=<registry>:<ratio>:<doi>`), `surname`
and `year`. Every `best=` in this job named **crossref**; no row reached the Semantic Scholar or
arXiv stages with a better candidate, and no row came back `best=none`.

---

## 2. E20 — the book (10.1201/9781315374321, van den Hout 2016)

**Pair: `blocked` / `403`.** This is the register's expected state for E20, dated 2026-09-22
01:34 UTC. Work `VanDenHout_2016_multi-state-survival-models`
(`01a0a4db-0697-7b50-b00f-e00ce008a385`), `in_main: true`, **files: [] — still zero**. Acquisition
`outcome: not-acquired`, 52.73 s of the 53.36 s total.

Routes, verbatim from `acquisition.route_detail` / `attempts`:

| route | status | http codes |
|---|---|---|
| `open_access` | `no-oa-copy` | — |
| `annas` | `not-in-archive` | — |
| `scihub` | `blocked` | 200, 200, 403, 200 |
| `browser` | `manual-step` | (attempt only, no route_detail entry) |

Refusal, verbatim:

> `not-acquired` — "hunt spent by default (open access, then the archive, then Sci-Hub) and none of
> them landed a file; see `acquisition.attempts`. `litkb acquire --key <key> --from-file <PDF>` is
> the manual route."

So books "MAY be acquired on every route" is now exercised and measured: all three public routes
were tried and none holds this book. The precedence rule in `docs/SCHEMAS.md` turns the Sci-Hub 403
into the state, which is why the pair is `blocked`/`403` rather than `held`/`not-acquired`.

**ISBNs — measured, not added.** `api.crossref.org/works/10.1201/9781315374321` carries
`ISBN: ["9781466568419"]` with `isbn-type: [{"value":"9781466568419","type":"electronic"}]`. One
ISBN, electronic only; no print ISBN in the record. Crossref's `first_author` for it is
`van den Hout`, year 2016, type `book`. **No identifier was written to litkb** — this job only
measured that the registry has one.

---

## 3. E21 and E22 (coordinator additions)

**E21 — bioRxiv preprint 10.1101/357798.** Pair: **`bound-unextracted` / `fresh-bound`**, `ok: true`,
3.0 s total (resolve 0.26, acquire 2.47). Route: `open_access` = `ok` (http 200) — one route, one
file. Work `Valavi_2018_blockcv-r-package-generating`
(`01a0a4c5-1378-7d19-9320-cb8bdc1e0eac`), type `preprint`, now holding
`_litkb_staging/filed/Valavi_2018_blockcv-r-package-generating.pdf`,
sha256 `b0e8f0caf1a3157905a3796c40a4de2605e0166ebbd0dbad8c7ff6eb96d9a079`, 19 pages,
`current_run_id: null` (extraction is S4's, `--no-extract` held).
**There was no duplicate refusal against the published article** `Valavi_2018_block-cv-r-package`:
the hunt resolved the preprint DOI to its own work and acquired it without mentioning the article.
Kam's two-works ruling is what the tool already does.

**E22 — Chrisman 1982, by title, `--no-spend`.** Pair: **`refused` / `ambiguous-title`**, 12.75 s —
**not** `unresolved-title`. `resolver_detail: best=crossref:0.52:10.1179/caj.1976.13.1.22`, which
Crossref gives as *"Quantisation Error in Area Measurement"*, Lloyd, 1976, The Cartographic Journal.
So Crossref *does* return something for that title string; gate 0 rejects it at ratio 0.52 with the
wrong author and a six-year gap. Nothing about the promoted, identifier-less work
`Chrisman_1982_theory-cartographic-error-measurement` appears in the result, and no duplicate
refusal fired — gate 0 refuses at resolution, before admission (and therefore before check 2) is
ever reached. **The register's expected pair for E22 is `refused`/`ambiguous-title` with that
`best=` string.**

---

## 4. E24 verdict table, in full (22 rows)

`claim` is the tracker's; `registry` is Crossref's record for the candidate DOI. Ratio ≥0.85 means
the title matched and the refusal is about the claim.

| row | ratio | candidate DOI | same as `stored_doi`? | claim (1st author / year) | Crossref (1st author / year) | verdict |
|---|---|---|---|---|---|---|
| 2 | 1.00 | 10.2139/ssrn.4979539 | yes | Li / 2025 | Schindler / 2024 | registry-quirk |
| 10 | 1.00 | 10.1080/17538947.2023.2257636 | yes | Qin / 2023 | Hao / 2023 | registry-quirk |
| 20 | 0.82 | 10.1080/15481603.2018.1489446 | yes | Storey / 2019 | — (below 0.85) | unresolved |
| 22 | 1.00 | 10.1145/3347146.3359068 | yes | Chen / 2019 | Liu / 2019 | registry-quirk |
| 24 | 1.00 | 10.1016/j.rse.2021.112308 | yes | Wang / 2021 | Liu / 2021 | registry-quirk |
| 33 | 0.88 | 10.1016/j.rse.2025.115091 | yes | Wagner / 2025 | Zhu / 2026 | registry-quirk |
| 39 | 0.90 | 10.3390/rs15030765 | yes | Zhou / 2023 | Chen / 2023 | registry-quirk |
| 46 | 1.00 | 10.1080/22797254.2025.2609404 | yes | Li / 2025 | He / 2025 | registry-quirk |
| 48 | 1.00 | 10.1109/tpami.2024.3498346 | yes | Yang / 2024 | Wang / 2025 | registry-quirk |
| 52 | 1.00 | 10.34133/2022/9764982 | yes | Nagai / 2022 | Yin / 2022 | registry-quirk |
| 55 | 0.97 | 10.3390/plants14111677 | yes | Li / 2025 | Wang / 2025 | registry-quirk |
| 66 | 1.00 | 10.1007/s00267-023-01934-6 | yes | Berland / 2024 | Kropp / 2024 | registry-quirk |
| 67 | 1.00 | 10.3390/geomatics4040022 | yes | Smith / 2024 | Morgan / 2024 | registry-quirk |
| 131 | 0.67 | 10.1109/icip55913.2025.11084679 | yes | Sosa / 2024 | — (below 0.85) | unresolved |
| 154 | 1.00 | 10.1137/1.9781611978032.28 | yes | Wang / 2024 | Lu / 2024 | registry-quirk |
| 177 | 1.00 | 10.1016/j.rse.2010.07.008 | yes | Cohen / 2010 | Kennedy / 2010 | registry-quirk |
| 178 | 1.00 | 10.1016/j.rse.2010.07.010 | yes | Kennedy / 2010 | Cohen / 2010 | registry-quirk |
| 186 | 0.69 | 10.1007/s10980-012-9719-2 | yes | Burnicki / 2012 | — (below 0.85) | unresolved |
| 187 | 0.34 | 10.7717/peerj.13435/fig-3 | **no** | Tyukavina / 2025 | — (a *figure* DOI, 0.34) | unresolved |
| 239 | 0.73 | 10.1109/tgrs.2023.3297077 | yes | Capliez / 2023 | — (below 0.85) | unresolved |
| 274 | 0.78 | 10.1016/j.jag.2022.102909 | yes | Li / 2022 | — (below 0.85) | unresolved |
| 293 | 1.00 | 10.1175/aies-d-22-0055.1 | yes | Appel / 2022 | Appel / 2024 | registry-quirk |

Three things this table says that the ruling did not anticipate:

1. **`registry-quirk` is not a formatting difference in any of the 16.** In **13** of them the
   registry's first author is a surname that does not appear anywhere in the tracker's author string
   (2, 10, 22, 24, 33, 39, 46, 48, 52, 55, 66, 67, 154 — row 10 is the name-order case: tracker
   "Qin, H." vs Crossref family "Hao"); in **2** (177, 178) the registry's surname *is* in the
   tracker's list but not first — the crossed pair; and in **1** (293) the author agrees and the
   **year** is two apart (2022 claimed vs 2024 in Crossref — the AMS early-release/print gap), which
   the ±1 rule cannot absorb. The ruling's parenthetical ("check 1 failed on a formatting difference
   — quote the two strings") does not describe any of them. The two strings are quoted per row above
   and in the CSV's `note` column.
2. **Rows 177 and 178 are now proven crossed, from the other direction.** Title 177 (LandTrendr
   part 1) resolves at ratio 1.00 to `…07.008`, whose registry first author is **Kennedy**, while the
   tracker's row 177 claims Cohen and its `DOI/URL` column holds `…07.010`. Row 178 is the exact
   mirror. The title route therefore pins each title to the right DOI independently: the fix is to
   swap the two DOIs and align each author list, and then both admit.
3. **Row 187 is the one row where the candidate differs from `stored_doi`, and the candidate is
   junk** — a figure DOI from an unrelated PeerJ paper at ratio 0.34. Its stored DOI
   `10.5067/doc/ceoswgcv/lpv/lc.001` is 404 at Crossref but **registered and live in the global
   handle system** (`doi.org/api/handles/…` → `responseCode 1`, target
   `http://lpvs.gsfc.nasa.gov/documents.html`), i.e. a non-Crossref registration agency. Calling it
   dead would be wrong, so it is scored `unresolved`, not `dead-doi`.

### E23 (15 rows): the low-confidence classification was right

Not one candidate reached 0.85, so nothing here was resolvable by title. Twelve of the fifteen
landed on the *same* weak candidate the 2026-09-15 search had recorded (25, 28, 49, 50, 57, 122,
132, 174, 193, 194, 242, 369); three found a different, also-weak one (53, 117, 235).

| row | ratio | candidate DOI | Crossref title (truncated) | 1st author / year |
|---|---|---|---|---|
| 25 | 0.82 | 10.3390/s8042161 | Assessment of the Spatial Co-registration of Multitemporal … | Coulter / 2008 |
| 28 | 0.49 | 10.5194/egusphere-egu25-16271 | Global 500m Resolution Tree Crown Structure Dataset | Xiang / 2025 |
| 49 | 0.48 | 10.5220/0014640400004061 | Enhancing Continual Learning for Software Vulnerability … | Dou / 2026 |
| 50 | 0.55 | 10.4135/9781452219011.n14 | Fine-Tuning Your Presentation | — / 2009 |
| 53 | 0.59 | 10.3390/drones4020027 | Vegetation Extraction Using Visible-Bands from Openly … | Agapiou / 2020 |
| 57 | 0.78 | 10.1016/j.agrformet.2023.109809 | Tracking photosynthetic phenology using spectral indices … | Guo / 2024 |
| 117 | 0.44 | 10.2139/ssrn.2351870 | You Can Have Your Trust and Calculativeness, Too … | James / 2013 |
| 122 | 0.56 | 10.52202/085713-2355 | Conformal Risk Training: End-to-End Optimization … | Yeh / 2025 |
| 132 | 0.63 | 10.1109/igarss52108.2023.10282926 | Self Supervised Learning in Remote Sensing: Quantifying … | Grau / 2023 |
| 174 | 0.64 | 10.1111/2041-210x.70116/v1/review1 | Review for "Zero-shot shark tracking and biometrics …" | — / 2025 |
| 193 | 0.69 | 10.1109/tgrs.2022.3199502 | Remote Sensing Change Detection via Temporal Feature … | Li / 2022 |
| 194 | 0.41 | 10.3403/30376491u | Stationary source emissions. Data acquisition and handling … | — / — |
| 235 | 0.49 | 10.2172/1922672 | Solar Canopy Expansion Project (Final Technical Report) | Ahmann / 2023 |
| 242 | 0.69 | 10.14214/sf.1405 | Tropical forest canopy cover estimation using satellite … | Korhonen / 2015 |
| 369 | 0.45 | 10.70675/26a20172zaa7bz4dafz8ae3z927831678d49 | Approximation géométrique d'ensembles aléatoires convexes … | Rahmani / — |

Rows 50, 117, 174, 193, 194 and 235 illustrate the class: the stored "candidate" points at a
completely different work (a presentation-skills book chapter, a trust-and-calculativeness SSRN
paper, a shark-tracking peer review, an emissions standard, a solar-canopy DOE report). Those are
weak candidates from the 09-15 keyword search, not the papers the tracker rows describe.

### Independently corroborated tracker-DOI corrections (7)

Where the tracker's own `DOI/URL` column differs from the credible (≥0.85) candidate, the title
route confirms the 09-15 correction without using it:

| row | tracker `DOI/URL` | title resolved to |
|---|---|---|
| 2 | 10.1016/j.tfp.2025.100146 (unregistered: Crossref 404 **and** no handle) | 10.2139/ssrn.4979539 |
| 33 | 10.1016/j.rse.2025.114632 (unregistered) | 10.1016/j.rse.2025.115091 |
| 48 | 10.1109/tpami.2024.3367329 (live — a *different* paper: "A Comprehensive Survey of Continual Learning") | 10.1109/tpami.2024.3498346 |
| 55 | 10.3390/rs17112050 (unregistered) | 10.3390/plants14111677 |
| 67 | 10.3390/geohazards4040022 (live — "Evaluating Post-Fire Erosion and Flood Protection Techniques") | 10.3390/geomatics4040022 |
| 177 | 10.1016/j.rse.2010.07.010 | 10.1016/j.rse.2010.07.008 |
| 178 | 10.1016/j.rse.2010.07.008 | 10.1016/j.rse.2010.07.010 |

"Unregistered" here is measured twice: `api.crossref.org` 404 **and** `doi.org/api/handles` 404
(`10.1016/j.rse.2025.114632`, `10.1016/j.tfp.2025.100146`, `10.3390/rs17112050`,
`10.3390/rs5041397`). The two Crossref-404 DOIs that *are* registered are
`10.5067/doc/ceoswgcv/lpv/lc.001` and `10.48550/arxiv.2501.01946` — non-Crossref agencies, live.

---

## 5. Rows that need Kam, with the question

| rows | what is established | the question |
|---|---|---|
| 177, 178 | the two DOIs are swapped in the tracker; each title resolves at 1.00 to the *other* row's DOI | swap the DOIs (and the author lists) and re-admit both? This is a tracker edit, not a hunt. |
| 2, 10, 22, 24, 33, 39, 46, 48, 52, 55, 66, 67, 154, 293 (14) | the stored DOI is the right record and the tracker's **claimed first author / year** is what disagrees | is the registry's first author authoritative for these rows — i.e. may the tracker's claim be corrected to Crossref's and the works admitted? No hunt of any kind can settle it: the claim is the gate's input. |
| 187 | stored `10.5067/doc/ceoswgcv/lpv/lc.001` is live outside Crossref; the tracker names Tyukavina, the record names the CEOS LPV subgroup | admit as a manual proposal (corporate author), since no Crossref-backed route will ever confirm a DataCite/other-agency DOI here? |
| 20, 131, 186, 239, 274 | the tracker title is a truncation or a paraphrase, so the ratio misses 0.85 while the stored DOI looks right | supply the registry's full title to the tracker row (then check 1's ratio passes), or admit from a bound PDF? |
| 15 E23 rows | no registry holds a record within 0.85 of these titles; six of the stored candidates are demonstrably other works | drop the bogus candidate DOIs from the tracker rows, and decide per row whether the work is wanted at all (five are grey literature: 194 King County ortho spec, 235 Seattle canopy assessment, 369 Matheron 1986 internal note, 50 DeepForest fine-tuning note, 174 a preprint review). |
| E20 (book) | no public route holds it; ISBN 9781466568419 (electronic) exists in Crossref | `--from-file` from a copy Kam has, or leave E20 at `blocked`/`403` as the register's expected state? |

## 6. Cost

| measure | value | source |
|---|---|---|
| total wall seconds, all hunts | **556.3** | sum of CLI-reported `seconds.total` (469.4 for the 37 + 53.36 book + 3.00 preprint + 12.75 Chrisman) + 17.8 s of drop-off calls |
| slowest single hunt | 13.53 s | max over the 37 |
| hunts over 10 min | 0 | — |
| hunting wall clock | ~12 min (first hunt 01:24:15, last 01:36:16 UTC) | CLI `at` fields |
| open-access fetches | 2 attempted, **1 landed** (E21); E20 `no-oa-copy` | route_detail |
| Anna's Archive **downloads used** | **0** | E20's only archive call answered `not-in-archive`, so no download was issued; the 37 title hunts never reached acquisition |
| Sci-Hub attempts | **1** (E20) — `blocked`, codes 200, 200, 403, 200 | route_detail |
| files acquired | **1** (E21, 19-page PDF) | `files[]` |
| Crossref record lookups | 66 DOIs, 1.1 s pacing, anonymous pool | `meta.py` |
| handle-system lookups | 6 | `handle.py` inline |

Spend on the 37 rows was **zero on every route**: a `refused` at resolution never reaches
acquisition, so the E23/E24 sweep cost 8 minutes of Crossref queries and nothing else.

## 7. What this job did not do

- **No extraction.** `--no-extract` on every call; E21's file is `bound-unextracted` by design and
  S4 owns it.
- **No identifier written.** The book's ISBN was measured in Crossref and not added to litkb.
- **No admission, no use, no promotion.** 40 hunts, 37 drop-offs, zero works admitted, zero uses
  recorded, no `promote prepare`. Nothing merged, pushed, vaulted or deleted.
  `litkb hunt-request list` confirms all 37 drop-offs stand at `resolution_state: open` with
  `work_id: null` — a refused hunt links no work, so not one expectation is even testable yet. Their
  ids are in the CSV's `hunt_request_id` column.
- **Nothing re-hunted by DOI.** The ruling asked for title resolution; where a title hunt refused,
  no DOI hunt was run as a fallback, so this report says nothing about whether those 22 stored DOIs
  would bind a PDF today.
- **`check.py` was not run** — this job added no code to the repo, only two report files.
- **The 37 drop-offs carry no `abstract_passage`.** The tracker's Relevance sentence is a
  project-authored summary, not an abstract quote, so that field was left empty rather than filled
  with something that is not verbatim from an abstract.
- **litkb imported from the main tree**, not from this worktree: the editable install's finder wins
  over `PYTHONPATH` (`import litkb` → `D:\edmonds-pipeline\treedata\Scripts\pipeline\litkb`). Both
  trees are at 1640f82 with a clean status, so the code is the same bytes; the workstream token and
  the outputs are the worktree's.
