# litkb ruled hunts — Kam's 2026-09-21 rulings on register rows E23 / E24

**Date:** 2026-09-21 (hunts ran 2026-09-22 03:05–04:00 UTC) · **Workstream:** `ruled-hunts-1`
(`01a0c713-8348-7620-82bc-0f38676bdf0c`, branch `work/20260921-litkb-ruled-hunts`) ·
**Agent/session:** `claude` / `s3-wrap-hunts-2` · **Row table:**
`LITKB_RULED_HUNTS_2026-09-21.csv` (35 rows: the 34 input rows + a second row for 187's URL leg).

Every number here came from a command in this job: the `litkb hunt` / `hunt-request add` /
`acquire` / `admit` CLI, three read-only `psql -U litkb_reader` queries against
`litkb.admissions` / `litkb.hunt_requests`, `litkb.admit.registry.confirm_doi` for the DataCite
record, `pypdf` for two first pages, and `litkb.netutil.Client` / `curl` probes of the arXiv API.
Nothing is restated from `LITKB_TITLE_HUNTS_2026-09-21.md`.

---

## 1. Kam's ruling works — but NOT the way step 2 of the brief describes it

The ruling is implemented in the code already: `litkb.admit.front.admit_registry` has a
`registry_only` mode (migration 0020, check 1) that takes the **registry record as the identity**
when an admission claims nothing and binds no file. That is exactly "the registry record is
authoritative over the tracker's claimed author/year", and it is what let 24 of these rows admit.

What does **not** work is passing `--hunt-request <id>` to the hunt that admits. A drop-off's
`claimed_title` / `claimed_authors` / `claimed_year` are **filled into the hunt**
(`litkb.hunt.fill_from_request`, call site at `hunt.py:1080`), so the tracker's wrong claim is
handed straight back to admission check 1 — the same gate the title run died on. Measured, row 48:

| call | result |
|---|---|
| `hunt 10.1109/tpami.2024.3498346 --ref-scheme doi --hunt-request 01a0c713-ba71… --no-extract` | `refused` / `admission-refused`, `refused_at: check1_study_exists`, 0.95 s (`from_hunt_request.filled: [title, author, year]`, `first_author: Yang`) |
| `hunt 10.1109/tpami.2024.3498346 --ref-scheme doi --no-extract` (no drop-off) | **admitted** — `Wang_2025_comprehensive-survey-forgetting-deep`, `verified_by: crossref` |

That refusal's own `check1_study_exists.reasons`, read back from `litkb.admissions`
(`01a0c713-d237-75ca-bf69-95f0ad486c00`), names the ruling's two fields and nothing else:

> `["doi 10.1109/tpami.2024.3498346: claimed first author does not match the registry's", "doi
> 10.1109/tpami.2024.3498346: claimed year 2024 against registry year 2025", "registry admission: no
> doi, arxiv or isbn identifier was confirmed by a registry"]`

The same thing happened to 187's **first** linking attempt
(`01a0c722-676e-7df4-b10e-7667e0c1e095`, claimed first author `Tyukavina`): its bare hunt had just
crashed, so no work existed to answer from, the call fell through to admission and check 1 refused it
on the claim. Once the work was admitted (§6), the same linking call linked in 0.62 s **without
reaching admission at all** — which is the whole reason step 3 is safe.

So the brief's own sentence ("every hunt here goes by IDENTIFIER … and carries **no claimed
metadata**") and its step 2(b) (`hunt … --hunt-request <id>`) contradict each other. Each row was
therefore run as **three** calls, which satisfies both halves of the ruling:

1. `hunt-request add` with the tracker's claim **verbatim** — the wrong claim stays on record;
2. `hunt <ref> --ref-scheme <scheme> --no-extract` with **no** drop-off and no claim — registry-only
   admission, spend allowed;
3. `hunt <ref> --ref-scheme <scheme> --hunt-request <id> --no-extract --no-spend` — this one answers
   from the database (`look_up` finds the work) and links the drop-off **before** any claim can reach
   admission, in ~0.5 s and without a second spend.

All 34 drop-offs exist; **25 are linked to a work** (`litkb.hunt_requests.work_id` non-null), 9 are
not because their hunt never reached a work (8 arXiv rows + 235).

A second piece of evidence that the claim was the only obstacle: the five rows the title run scored
`unresolved` because the tracker's title is a truncation or paraphrase (20, 131, 186, 239, 274) all
admitted here without trouble — nothing about them was ever ambiguous except the claim.

---

## 2. Hunt states over the 34 input rows (35 result rows)

| state / reason | count | rows |
|---|---|---|
| `bound-unextracted` / `fresh-bound` | **10** | 20, 22, 24, 25, 52, 177, 178, 186, 239, 194 |
| `blocked` / `403` | **15** | 2, 10, 33, 39, 46, 48, 55, 57, 66, 67, 131, 154, 187 (DOI leg), 274, 293 |
| `api-error` / `registry-transient` | **8** | 28, 49, 117, 122, 132, 174, 193, 242 (all E23-arxiv) |
| `refused` / `admission-refused` | **2** | 187 (URL leg — `duplicate-review`), 235 (`check4_manual`) |
| `held`, `crashed`, `extracted` | 0 | — (187's first attempt crashed; the re-run with `--key` stands) |

By group:

| group | rows | bound-unextracted | blocked | api-error | refused |
|---|---|---|---|---|---|
| E24-registry | 19 | 6 | 13 | 0 | 0 |
| E24-swap | 2 | 2 | 0 | 0 | 0 |
| E24-datacite | 1 (2 legs) | 0 | 1 | 0 | 1 |
| E23-arxiv | 8 | 0 | 0 | 8 | 0 |
| E23-doi | 2 | 1 | 1 | 0 | 0 |
| E23-url | 2 | 1 | 0 | 0 | 1 |

**Works admitted: 24 fresh + 1 pre-existing.** `litkb.admissions` for this workstream holds
`registry/admitted 23`, `manual/proposed 1` (row 194), `registry/refused 3` (row 48's claim-carrying
test, 187's claim-carrying link hunt, and the §8 dual-identifier probe) and `manual/refused 3`
(187's URL leg + 235's two attempts). Row 39's DOI `10.3390/rs15030765` was already in main: its
hunt has **no admission row**, answered from the database and spent on the held work —
`work_id 01a0c101-b227-…`, an older entity than anything this job created. A duplicate is an answer,
and this is the only one that came back.

**Files acquired: 9 PDFs + 1 HTML snapshot.**

| row | work key | pages | landed by |
|---|---|---|---|
| 20 | `Storey_2018_normalizing-shadows-multi-temporal` | 22 | annas (OA `blocked`) |
| 22 | `Liu_2019_misregistration-tolerant-change-detection` | 4 | annas (OA `no-oa-copy`) |
| 24 | `Liu_2021_change-detection-deep-learning` | 16 | annas (OA `bad-file`) |
| 25 | `Coulter_2008_assessment-spatial-co-registration` | 13 | annas (OA `blocked`) |
| 52 | `Yin_2022_broadband-green-red-vegetation` | 10 | **open access** |
| 177 | `Kennedy_2010_detecting-trends-forest-disturbance` | 14 | annas |
| 178 | `Cohen_2010_detecting-trends-forest-disturbance` | 14 | annas |
| 186 | `Burnicki_2012_impact-error-landscape-pattern` | 17 | annas |
| 239 | `Capliez_2023_multisensor-temporal-unsupervised-domain` | 16 | **open access** |
| 194 | `Center_2015_ortho-image15c-point-gis` | — | web snapshot (`_litkb_staging/web/hunt-20260922T033750.txt`) |

**Proposals created (invisible to `litkb_search` outside this workstream until a SECOND session
approves):** exactly one — admission **`01a0c730-fa16-7d45-baf8-0fce8c8ad084`**, state `proposed`,
work `Center_2015_ortho-image15c-point-gis` (row 194). 235's proposal was refused, so none exists
for it.

---

## 3. Every refusal, verbatim

**8 × E23-arxiv** (`state: api-error`, `reason: registry-transient`), e.g. row 28:

> "the registry answered arxiv 406 for 2507.00170 — a transient answer, not a verdict on the record.
> Nothing was admitted and nothing was written; hunt the reference again."

**15 × `blocked` / `403`**, one and the same refusal (code `not-acquired`):

> "hunt spent by default (open access, then the archive, then Sci-Hub) and none of them landed a
> file; see `acquisition.attempts`. `litkb acquire --key <key> --from-file <PDF>` is the manual
> route."

**187, URL leg** (`refused` / `admission-refused`, admission `01a0c72d-f064-731a-8494-cf4060bef12d`,
`outcome: duplicate-review`):

> "the web source was not admitted; the checks say why."

and the follow-up `acquire --key LPVSubgroup_2025_… --from-file <filed pdf>`:

> `{"outcome": "duplicate-held", "attempts": [["browser", "duplicate-held"]], "archive_downloads_used": 0}`

**235** (`refused` / `admission-refused`, `refused_at: check4_manual`, twice):

> "the web source was not admitted; the checks say why."

and, read from `litkb.admissions.checks->'check3_binding'` for both attempts
(`01a0c72e-dae5-748f-bb14-9817eb90752e`, `01a0c730-2e90-745d-bad0-a54ef1c3c195`):

> `{"ratio": 0.8, "verdict": "binding-failed", "reasons": ["title ratio 0.8 < 0.85: the registry
> title is not in the title region of the first page or in the PDF title"]}`

**187, DOI leg, first attempt** (`crashed` / `admit:CheckViolation`):

> "CheckViolation: new row for relation \"works\" violates check constraint \"works_key_check\""

---

## 4. Tracker claim vs registry record — the whole point of the ruling

`registry_first_author` is the surname segment litkb itself derived into the work key from the
registry record; `registry_year` is the admitted work's year. Of the **24 rows that reached a
registry record**, the tracker's **first author is wrong in 17**, its **year is wrong in 8**, and
**both are wrong in 5**. Exactly **3 rows agree with the registry on both fields**: 186, 239, 274.

| row | group | tracker (1st author / year) | registry (1st author / year) | state | file |
|---|---|---|---|---|---|
| 2 | E24-registry | Li / 2025 | **Schindler / 2024** | blocked/403 | n |
| 10 | E24-registry | Qin / 2023 | **Hao** / 2023 | blocked/403 | n |
| 20 | E24-registry | Storey / 2019 | Storey / **2018** | bound | y |
| 22 | E24-registry | Chen / 2019 | **Liu** / 2019 | bound | y |
| 24 | E24-registry | Wang / 2021 | **Liu** / 2021 | bound | y |
| 25 | E23-doi | Stow / 2013 | **Coulter / 2008** | bound | y |
| 33 | E24-registry | Wagner / 2025 | **Zhu / 2026** | blocked/403 | n |
| 39 | E24-registry | Zhou / 2023 | **Chen** / 2023 | blocked/403 | n (already in main) |
| 46 | E24-registry | Li / 2025 | **He** / 2025 | blocked/403 | n |
| 48 | E24-registry | Yang / 2024 | **Wang / 2025** | blocked/403 | n |
| 52 | E24-registry | Nagai / 2022 | **Yin** / 2022 | bound | y |
| 55 | E24-registry | Li / 2025 | **Wang** / 2025 | blocked/403 | n |
| 57 | E23-doi | Zhang / 2023 | **Guo / 2024** | blocked/403 | n |
| 66 | E24-registry | Berland / 2024 | **Kropp** / 2024 | blocked/403 | n |
| 67 | E24-registry | Smith / 2024 | **Morgan** / 2024 | blocked/403 | n |
| 131 | E24-registry | Sosa / 2024 | Sosa / **2025** | blocked/403 | n |
| 154 | E24-registry | Wang / 2024 | **Lu** / 2024 | blocked/403 | n |
| 177 | E24-swap | Cohen / 2010 | **Kennedy** / 2010 | bound | y |
| 178 | E24-swap | Kennedy / 2010 | **Cohen** / 2010 | bound | y |
| 186 | E24-registry | Burnicki / 2012 | Burnicki / 2012 | bound | y |
| 187 | E24-datacite | Tyukavina / 2025 | **"Land Product Validation Subgroup (Working Group on Calibration and Validation"** (corporate, DataCite) / 2025 | blocked/403 | n |
| 239 | E24-registry | Capliez / 2023 | Capliez / 2023 | bound | y |
| 274 | E24-registry | Li / 2022 | Li / 2022 | blocked/403 | n |
| 293 | E24-registry | Appel / 2022 | Appel / **2024** | blocked/403 | n |

**177 / 178, the swap, closed from this side too.** Each row was hunted on the DOI its *title*
resolved to in the previous run, and each admitted with the **other** row's claimed first author:
`10.1016/j.rse.2010.07.008` → `Kennedy_2010_…` (tracker row 177 claims Cohen) and
`…07.010` → `Cohen_2010_…` (row 178 claims Kennedy). Both PDFs are bound. The tracker's own
`DOI/URL` column holds the other paper's DOI in both rows — that is a tracker edit, not a hunt, and
it is still outstanding.

---

## 5. Spend

| measure | value | source |
|---|---|---|
| CLI seconds, the 81 calls captured in the row files | **897.8** | sum of `seconds.total` |
| plus the six timed hand-run 187 / 194 / 235 hunts | **79.4** | 52.77 + 0.62 + 20.53 + 1.08 + 2.30 + 2.06 (the `acquire` and `admit` probes report no seconds) |
| wall clock, first call to last | 03:05:59 → ~03:53 UTC (~47 min of calls) | CLI `at` fields |
| my measured wall time over the driver's calls | 928.8 s | subprocess timing in the driver |
| open-access route: `ok` / `no-oa-copy` / `blocked` / `bad-file` | 2 / 10 / 9 / 3 (24 spends) | `route_detail` |
| **Anna's Archive downloads used** | **7** (`annas: ok`; 15 more answered `not-in-archive`, 22 calls) | `route_detail` |
| **Sci-Hub attempts** | **15**, every one `blocked` (codes 200, 200, 403, 200 each time) | `route_detail` |
| `browser` route | 15 × `manual-step` (an attempt record, no fetch) | `attempts` |
| files acquired | **10** (9 PDFs, 1 HTML snapshot) | `files[]` |
| archive downloads reported by the acquire call | 0 | `archive_downloads_used` |

No GPU, no Colab, no extraction: `--no-extract` on every hunt (S4 owns extraction), so all ten
bound files sit at `bound-unextracted` with `current_run_id: null`.

---

## 6. 187 — both outcomes, as asked

**DOI leg.** Crossref answers **404** and DataCite answers **200**, so the registry ladder does
reach this DOI (measured with `litkb.admit.registry.confirm_doi`). The first hunt **crashed**:
`admit:CheckViolation` on `works_key_check`, because DataCite's creator is corporate — the record's
`first_author` is the 76-character string *"Land Product Validation Subgroup (Working Group on
Calibration and Validation"* and the derived key has no `[A-Za-z]+` surname segment to put in front
of the year. Re-run with an explicit `--key LPVSubgroup_2025_land-cover-change-accuracy-protocol`,
it admitted (`verified_by: datacite`, type `report`, year 2025) and then spent: OA `no-oa-copy`,
Anna's `not-in-archive`, Sci-Hub `blocked` 403 → `blocked` / `403`, no file, 52.77 s.

**URL leg** (run because the DOI leg landed no file). `lpvs.gsfc.nasa.gov/documents.html` links
exactly one PDF for this protocol and cites it as *"Tyukavina et al., 2025"* with this DOI — so the
tracker's author claim agrees with the **publisher's** page while DataCite records a corporate
creator. The PDF fetched clean (HTTP 200, 7,623,037 bytes, sha256 `94d8fbed…3888f`, filed as
`_litkb_staging/filed/Tyukavina_2025_land-cover-change-map.pdf`), and the admission was refused
`duplicate-review`: check 2 recognised it as the work already admitted by DOI, which is correct
behaviour. The obvious follow-up, `acquire --key … --from-file <the filed PDF>`, returned
`duplicate-held` — the known self-dedupe hazard for a `*.pdf` under the literature root, whose
documented workaround is to pass the `.download` path, and that path had already been moved into
`filed/` by the hunt itself. **The 7.6 MB protocol PDF is on disk and unbound.**

---

## 7. The two URL rows

**194 — the brief's premise is false, measured.** The task said to read the King County metadata page
and hunt the specification document it points to. That page points to **no document at all** (its
only outward links are ArcGIS Open Data, EPSG:2926, terms of use and a contact address) and carries
**no acquisition-specification text**: no leaf-off wording, no flight window, nothing about snow or
smoke, "Supplemental Information: None". Its whole substantive content is the photo-centre index's
abstract, purpose and attribute list. A targeted web search for a Puget Sound consortium acquisition
specification PDF returned none either. So the **page itself** was hunted as a web source — HTML is
a first-class web source in the URL branch since S3 — and it landed `bound-unextracted` /
`fresh-bound` as a manual **PROPOSAL** (`in_main: false`).
**A doubt recorded, not resolved:** the tracker's relevance sentence quotes 2012 leaf-off wording
that is not on this 2015 page, so row 194's evidence and its `ref` describe different documents.

**235 — found, fetched, and refused at the binding gate.** The official PDF is
`https://seattle.gov/documents/Departments/OSE/Urban%20Forestry/2021%20Tree%20Canopy%20Assessment%20Report_FINAL_230227.pdf`
(53 pages, 9,769,141 bytes, sha256 `1e31150a…aa6d`). Both hunts downloaded and filed it, and both
were refused at `check4_manual` — "a manual admission needs a held file whose first page carries the
title" — because check 3 measured the title ratio at **0.80 < 0.85**. The cause is the cover: page 1
holds only 225 characters, printing the title down five short lines ("2 0 2 1 / CITY OF SEATTLE /
TREE CANOPY / ASSESSMENT / FINAL REPORT / Findings prepared by …"), and the PDF's own `/Title` is
**empty** (`/Author` is "Julie Stein"). Two title strings were tried — the plain one and the cover's
own, year-first form — and **both measured exactly 0.80**. No check was weakened and no third
variant was hunted for.

---

## 8. The eight arXiv rows: arXiv is refusing this host

Three attempts per row — 03:22 UTC, then ~03:26 (45 s spacing), then ~03:52 (60 s spacing) — and all
24 calls came back `arxiv 406`. Probes, all read-only:

| probe | result |
|---|---|
| `litkb.netutil.Client` → `http://export.arxiv.org/api/query?id_list=2507.00170`, Accept `application/atom+xml` | **406** |
| same, `https://` | **406** |
| same, Accept `*/*` | **406** |
| same, with a non-browser UA (`litkb/0.1 (…)`) instead of litkb's `Mozilla/5.0 … Chrome/128.0` | **406** |
| `curl` → `https://export.arxiv.org/api/query?id_list=2507.00170` | **429** |
| `curl` → `http://…` | 301 (redirect to https) |

So arXiv serves `curl` and rate-limits it (429) while answering litkb's urllib client 406 whatever
Accept header or UA it sends. The discriminator is **UNDETERMINED** — it is not the UA and not the
scheme. `registry-transient` may therefore be under-describing a persistent, client-shaped refusal;
against that, memory `litkb-*` records the same 406 pattern recovering after 4m17s on 2026-09-20.
Either way **nothing was admitted and nothing was written** for these eight, and the correct next
move is the CLI's own: hunt them again later.

One alternative route was measured and **refused**, so it is not a workaround:
`litkb admit --arxiv 2507.00170 --doi 10.48550/arXiv.2507.00170` → `refused_at:
check1_study_exists`, "arxiv 2507.00170 is not confirmed by a registry", `confirmed: 1` — the DOI
form confirms (DataCite) but check 1 requires **every** passed identifier to confirm. Admitting by
the `10.48550/…` DOI **alone** would work, but it would store no arXiv identifier, so the drop-off
could not be linked and a later arXiv-id hunt would collide with it as a duplicate. Not done on
purpose.

---

## 9. Rows that still need Kam

| rows | what is established | what is needed |
|---|---|---|
| 28, 49, 117, 122, 132, 174, 193, 242 | arXiv answered 406 to 24 consecutive calls over 30 min; nothing written; drop-offs unlinked | retry when arXiv answers (S4), or decide whether litkb's arXiv client needs fixing |
| 15 rows at `blocked`/`403` | admitted, registry-confirmed, no file: OA has no copy or blocks, Anna's does not hold them, Sci-Hub 403s | `acquire --from-file` from copies Kam can get, or accept them as METADATA-grade |
| 187 (URL leg) | the protocol PDF is fetched and filed; binding blocked by the `*.pdf`-under-the-literature-root self-dedupe hazard | bind it (the `.download`-path workaround, or the fix in flight) |
| 235 | the report is fetched and filed; check 3 measures 0.80 on a cover whose title is split over five lines and whose `/Title` is empty | a manual CLI admission with a SECOND session's sign-off, or a title-region fix. **Do not lower 0.85.** |
| 194 | admitted as a proposal; needs a second session's approval to be searchable outside this workstream | approve `01a0c730-fa16-7d45-baf8-0fce8c8ad084`, and decide what row 194's `ref` should be, since its relevance quotes a different page |
| 177, 178 | the two DOIs are crossed in the tracker's own `DOI/URL` column; both works now admitted and bound under the registry's authors | a tracker edit (swap the DOIs, align the author lists) |
| 17 author / 8 year disagreements | the tracker's claim is wrong in 17 of 24 rows that reached a registry record; the registry record is what was admitted, per the ruling | whether the tracker rows get corrected to the registry's values (§4 is the list) |
| 187 (key derivation) | a corporate-creator registry record crashes `litkb hunt` at `admit` with `CheckViolation` on `works_key_check`; only an explicit `--key` gets past it | a defect to fix: derive a key from a corporate creator, or refuse with a message instead of crashing |

---

## 10. What this job did not do

- **No extraction.** `--no-extract` on **every** hunt call in this job (86 of them: 48 bare hunts
  including the arXiv retries, 32 linking hunts, 1 refused claim-carrying test, and 5 hand-run for
  187/194/235); the ten bound files are `bound-unextracted` with `current_run_id: null`.
- **No uses, no promotion, nothing approved.** No `litkb use add`, no `promote prepare`, no
  `approve` — 194's proposal is left for a second session, as the tool says.
- **No tracker edits.** The tracker's wrong author/year strings were written onto the drop-offs
  verbatim (that was the point) and nothing in `Reports/literature_tracker.csv` was touched.
- **No `abstract_passage` on any drop-off.** The tracker's Relevance sentence is a project-authored
  summary, not a verbatim abstract quote, so `expected_claim` carries it and the abstract field was
  left empty rather than filled with something that is not from an abstract.
- **No fourth arXiv attempt**, and no hunt of the `10.48550/arXiv.<id>` DOI form for the eight rows
  beyond the single measured probe in §8.
- **No third title variant for 235**, and no attempt to move or copy anything under
  `D:\edmonds-pipeline\Literture\` to get 187's or 235's PDF bound — that is outside this job's
  write grant.
- **`check.py` was not run**: this job added no code to the repo, only these two report files.
- **litkb imported from the main tree**, not from this worktree — the editable install's finder wins
  over `PYTHONPATH` (`import litkb` → `D:\edmonds-pipeline\treedata\Scripts\pipeline\litkb`). Both
  trees are at 9239729; the workstream token and the outputs are the worktree's.
