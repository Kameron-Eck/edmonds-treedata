# Literature knowledge base — design, architecture and plan

**Status:** DRAFT for Kam's approval, 2026-09-13. Nothing here is built. Every design claim is
UNVALIDATED until the phase that tests it has run on real data with its kill shown to fire
(CLAUDE.md 3.4c). Tool facts marked **[F]** come from the verification report
(§17); anything marked **[UNCONFIRMED]** must be checked before it is relied on.

**Branch:** `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`, based on
`docs/lit-review-spatiotemporal-consistency` (merge that branch first; this one rebases cleanly).

---

## 1. What Kam asked for (the requirements, in his terms)

| # | Requirement | Source (2026-09-13) |
|---|---|---|
| R1 | Many agents and sessions write at once | "We usually have many agents and work sessions writing at once" |
| R2 | Literature becomes actionable knowledge Claude can pull from, with vectors | "turn the literature into actionable knowledge for claude to pull from … vectors claude can query" |
| R3 | Work branches get their own side of the data and merge into main | "a side database that belongs to the work tree, and then gets placed into the main" |
| R4 | A unique ID per literature piece and per work branch | "a unique ID for each literature piece … a unique ID for each work branch" |
| R5 | Multiple use rows for the same study (different worktrees, different uses), linked to the study | "multiple rows for the same study … dedicated to that use … linked by the parent ID" |
| R6 | Use cases recorded; every row versioned; changing understanding tracked | "recording use case(s) … versioning each row … track this change" |
| R7 | Checks so only studies and books that exist enter | "checks and balances about what can get placed into the database" |
| R8 | aa_fetch and paper-search integrated; tooling in the project | "work my anna archive tool and paper search tool into this"; "bring the tooling into the project" |
| R9 | PDFs keep readable names; the hash lives in metadata; metadata is central | "use readable names and put the hash in the meta data. Metadata will be super important" |
| R10 | Extraction keeps figures, tables, multi-column order, sources, footnotes, headers, captions | "This is all great information. We should be baking this into the overhaul" |
| R11 | Bulk pass on Colab now; local runs later when the backlog is small | "we can use colab. I want this to run locally in the future" |
| R12 | No backup for now (disk) | "We can table a back up for now" |

**Non-goals:** storing PDF bytes in Postgres; a backup system (R12); a public or multi-user
service; replacing the research reports (briefs and findings stay as reviewed documents in git).

---

## 2. Architecture at a glance

```
                ┌──────────────────────────── worktrees / agents / sessions (R1) ─────────────────────┐
                │  hunt: discover → admit → acquire → extract → read → record uses → promote on merge │
                └───────────────┬─────────────────────────────────────────────────────┬──────────────┘
                                │ MCP server + CLI (litkb)                            │ git (reports, exports)
      ┌─────────────────────────▼─────────────────────────┐                           │
      │  PostgreSQL 18 on this machine  —  database litkb │                           │
      │  identity:  works · identifiers · files           │  verified facts, visible  │
      │  knowledge: gaps · uses · use_versions · evidence │  promoted per workstream  │
      │  text:      pages · blocks · tables · figures ·   │  derived, keyed by file   │
      │             equations · references · chunks ·     │  hash + pipeline version  │
      │             embeddings (pgvector)                 │                           │
      │  process:   workstreams · candidates · attempts · │                           │
      │             extraction_runs · file_checks         │                           │
      └───────▲───────────────────────▲───────────────────┘                           │
              │ ingest (local only)   │ admission / acquisition                        │
   ┌──────────┴─────────────┐  ┌──────┴─────────────────────────────┐     ┌────────────▼──────────┐
   │ extraction artifacts   │  │ paper-search (discover, OA)        │     │ exports: tracker.xlsx │
   │ _derived/<sha256>/…    │  │ resolver (Crossref/S2/arXiv)       │     │ tracker.csv, manifest │
   │ from Colab or local    │  │ aa_fetch (Anna's Archive), Sci-Hub │     │ promotion reports     │
   └──────────▲─────────────┘  └──────┬─────────────────────────────┘     └───────────────────────┘
              │                        │ PDFs
   ┌──────────┴────────────────────────▼────────────────────────────────────────────────────────┐
   │ D:\edmonds-pipeline\Literture\<Topic>\<Surname_Year_slug>.pdf   (readable names, R9)       │
   └────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Four decisions carry the design:**

1. **One database, many related tables** — foreign keys only hold inside one database (R5, R7).
2. **Verified facts are visible at once; interpretations are promoted.** A study's identity, its
   files and its extracted text are facts checked against registries and hashes: every worktree sees
   them immediately, so no two hunts acquire the same paper. What a study *means for the project* —
   uses, gaps, metadata judgements — is written into a workstream and promoted on merge (R3).
3. **Nothing is updated in place.** Every mutable thing is an identity row plus append-only versions
   (R6). The database role agents use cannot UPDATE or DELETE version rows.
4. **The database runs only on this machine.** Colab is stateless compute: it reads PDFs from the
   Drive lake and writes extraction artifacts back; a local ingest step loads them (R11). The same
   pipeline code runs locally later, byte-for-byte versioned.

---

## 3. Identifiers (R4)

- **Every row ID is a UUIDv7** — time-ordered, generated by the database or by a client offline
  (Colab). The installed PostgreSQL 18.6 catalog carries `uuidv7` (found in `share/postgres.bki`,
  2026-09-13); P1 confirms it with a query. Clients generate the same form when offline.
- **Readable keys alongside, never instead:** `works.key` = the file stem convention
  (`Surname_Year_slug`, unique); `workstreams.slug` (unique per open workstream).
- **External identifiers are rows, not columns** — a study can carry several DOIs (Page 1954 has
  OUP and JSTOR DOIs), an arXiv id, an ISBN, a JSTOR stable id, PMID, OpenAlex id.

---

## 4. Data model

### 4.1 The versioning pattern (used by every mutable entity)

```
<entity>            id (uuidv7) · created_at · created_in_ws → workstreams
<entity>_versions   version_id · <entity>_id · version_no · …fields… ·
                    change_reason (required from v2) · based_on_version_id ·
                    workstream_id · agent · session_id · created_at ·
                    state: proposed | promoted | rejected | withdrawn · promoted_at · promotion_id
```

- **Main's view** of an entity = its highest-numbered `promoted` version.
- **A workstream's view** = its own latest version if one exists, else main's.
- **Conflict** = a version whose `based_on_version_id` is no longer main's current version at
  promotion time. The promote step flags it; nobody's version is overwritten.
- For **fact tables** (identity, files, extraction) the same pattern applies but versions are
  written `promoted` directly after their checks pass — the history is kept, the review step is not.

### 4.2 Identity (facts)

| Table | Key columns | Notes |
|---|---|---|
| `works` / `work_versions` | key; type (article, book, chapter, proceedings, report, thesis, preprint, dataset); title, subtitle; authors (ordered JSON: family, given, ORCID); year; venue; volume, issue, pages; publisher; language; abstract | Versioned: a corrected title or year is a new version with a reason |
| `identifiers` / `identifier_versions` | work_id; scheme (doi, arxiv, jstor, isbn, pmid, pmcid, openalex, s2, handle, url); value (normalised); verified_by (crossref, datacite, arxiv, s2, manual); evidence (JSON: registry title, first author, year, ratio) | Active (scheme, value) unique across works. A DOI proven wrong (the Averkov 2009 case) gets a `retracted` version with its reason |
| `files` / `file_versions` | work_id; stem; rel_path; **sha256** (unique); md5 (Anna's Archive identity); bytes; pages; has_text_layer; pdf metadata (JSON: info dict, XMP, producer, creator); copy_kind (publisher, author manuscript, preprint, scan); source_route; source_url; obtained_at; status (active, quarantined, superseded) + reason | R9: the hash and everything about the file live here; the name on disk stays readable. A study may have several files (Brook 1972: a different copy) |
| `file_checks` | file_id; check (hash, content vs registry, archive record); verdict; detail; run_at | Filled by the audit (the `--audit-fast` logic) |

### 4.3 Process

| Table | Purpose |
|---|---|
| `workstreams` | id; slug; git_branch; worktree_path; purpose; brief_path; parent_workstream; state (open, merged, abandoned); opened_at; closed_at; merge_commit |
| `candidates` | Leads not yet admitted: source (paper-search source, citation, manual); query or citing reference; raw record (JSON); title/authors/year/ids as found; state (new, admitted, duplicate, rejected) + reason; admitted_work_id |
| `acquisition_attempts` | work or candidate; route (open access, annas, scihub, browser); identifier used; status (ok, not-in-archive, bad-file, partner-404, …); detail; http codes; at; workstream |
| `promotions` | id; workstream_id; started/finished; merge_commit; counts; conflicts (JSON); report_path |
| `extraction_runs` | file_id; stage; tool; tool_version; params hash; pipeline_version; host (colab, local); status; artifact_path; metrics (JSON: seconds, pages/s, coverage) |

### 4.4 Text and structure (derived, R10)

| Table | Key columns |
|---|---|
| `pages` | file_id; page_no; width, height (PDF points); rotation; text_layer_chars; needs_ocr; image_path (rendered only when needed) |
| `blocks` | id; file_id; run_id; page_no; bbox (x0, y0, x1, y1 in PDF points); reading_order; **type** (title, author, affiliation, abstract, heading, paragraph, list_item, footnote, caption, table, figure, equation, reference, page_header, page_footer, page_number, sidebar, other); section_path (text[]); text; latex; parent_block_id (caption → its figure or table); extractor; confidence; canonical (bool, set by reconciliation) |
| `tables` | block_id; n_rows; n_cols; cells (JSON: row, col, rowspan, colspan, text, is_header); caption_block_id |
| `figures` | block_id; crop_path; caption_block_id; description; description_model |
| `equations` | block_id; latex; display or inline; label (e.g. "3.19") |
| `references` | id; file_id; block_id; raw text; parsed (JSON: authors, title, year, venue, volume, pages, DOI); resolved_work_id; resolution (resolved, candidate, unresolved); confidence |
| `citation_mentions` | block_id; reference_id; char span — links an in-text citation to its reference |
| `chunks` | id; file_id; work_id; run_id; block_ids; kind (abstract, prose, table, caption, equation, reference); section_path; page_start, page_end; text (with section heading prepended as context); tokens |
| `embeddings` | chunk_id; model; dim; vector (`halfvec`); created — separate table so models can be swapped or compared |

Extraction rows are keyed by (file sha256, stage, tool version, params hash). Rerunning with the same
key is a no-op; a new pipeline version writes new runs and the old ones stay queryable.

### 4.5 Knowledge (interpretation, R5, R6)

| Table | Key columns |
|---|---|
| `gaps` / `gap_versions` | slug; question; framework pointer (e.g. "gap row 6"); brief_path; state (open, closed, abandoned) |
| `uses` | id; work_id; gap_id (nullable); created_in_ws |
| `use_versions` | statement (what the work supplies or was thought to supply); kind (method, theorem, parameter, empirical evidence, negative result, context, contradiction); **status** (proposed, supported, refuted, superseded, withdrawn); confidence; feeds (tokens: `framework §N`, `gap row N`, `decision <slug>` …); rationale; change_reason; based_on_version_id; workstream; agent; state + promotion fields |
| `use_evidence` | use_version_id; block_id; page; quote; stance (supports, refutes, context); quote_verified (bool: the quote exists verbatim in the block text) |
| `use_embeddings` | use_version_id; model; vector — so Claude can ask "what have we already used literature for on X?" |

**Worked example.** Efron 2004 enters once as a work. Round 4 records a use: "supplies the optimism
identity under an arbitrary joint model", status `supported`, evidence on p. 624, eq. 3.19, feeds
`gap row 6`. A later hunt finds the per-cell form fails for spatially coupled cells: it writes
version 2, status `refuted`, based on version 1, with its reason and evidence. Main shows v2 after
promotion; v1 stays readable. A different worktree records a *second* use of Efron 2004 (the
bootstrap variance), a separate `uses` row with its own history.

### 4.6 The two kinds of checks (R7)

**Check 1 — the study exists.** Enforced in the admission code before any `works` row:
- a DOI confirmed on Crossref or DataCite with normalised title ratio ≥ 0.85, first-author family
  name and year (±1 for online-first) — the rule already in `Scripts/docs/LITERATURE_CONVENTION.md`;
- or an arXiv id confirmed on the arXiv API; or an ISBN confirmed against a registry record;
- or, with no identifier (older proceedings, reports), evidence rows naming the source and a
  held file whose text contains the title — marked `verified_by = manual` and flagged in exports;
- the evidence JSON is stored on the identifier version, so the check is auditable later.

**Check 2 — every reference points at something real.** Enforced by the database itself: foreign
keys, unique active identifiers, unique sha256, enum checks on every status column, a regex check on
`works.key`, `change_reason` required for version ≥ 2. The agent role can INSERT but not
UPDATE/DELETE version tables; only the promotion function changes `state`.

### 4.7 Roles

| Role | Can | Used by |
|---|---|---|
| `litkb_reader` | SELECT | the MCP query tools; exports |
| `litkb_writer` | INSERT into proposals, candidates, attempts, extraction tables | agents, acquisition, ingest |
| `litkb_promoter` | run `promote()` | the merge step (orchestrator or Kam) |
| `litkb_owner` | DDL, migrations | migration runner only |

Credentials live in `D:\edmonds-pipeline\secrets\` (a `pgpass` file), never in the repo.

---

## 5. Workstreams and promotion (R3)

1. **Open.** `litkb ws open --slug <slug> --branch <git branch> --purpose "…" [--brief <path>]`
   writes the workstream and a git-ignored `.litkb-workstream` file in the worktree root. Every
   write from that worktree carries its ID.
2. **Work.** Agents admit works and files (visible to all at once), and record gaps, uses and
   evidence as `proposed` versions (visible to their workstream).
3. **Promote at merge.** `litkb promote --ws <slug>`:
   - produces a report — every proposed version, grouped by work and gap;
   - re-runs the checks: quotes verified against blocks, feeds tokens valid, no positional references;
   - flags conflicts (stale `based_on_version_id`) and near-duplicate uses of the same work and gap;
   - in one transaction marks clean versions `promoted`, leaves flagged ones `proposed` with a note;
   - writes the report to `Reports/litkb_promotions/<date>_<slug>.md`, committed with the merge,
     so git records what entered main's knowledge.
4. **Abandon.** `litkb ws abandon` marks the workstream; its versions stay, invisible to main.

---

## 6. File store and metadata (R9, R12)

- **PDFs:** `D:\edmonds-pipeline\Literture\<Topic>\<Surname_Year_slug>.pdf`, as today.
- **Derived artifacts** (raw tool outputs, figure crops, rendered pages for scans):
  `D:\edmonds-pipeline\Literture\_derived\<sha256>\<stage>\…` — keyed by hash, so renames never
  orphan them.
- **Metadata captured per file** at inventory: sha256, md5, bytes, page count, PDF version, info
  dictionary, XMP, producer/creator, encryption flags, per-page text-layer size, fonts summary,
  scan detection; plus registry metadata on the work and GROBID's header parse — all three kept so
  disagreements (a wrong DOI, a missing year) are visible.
- **Disk:** D: had 139 GB free on 2026-09-13; the current corpus is 771 MB of PDFs. Page images are
  the only large derived item; they are rendered for scans and disputed pages only, not stored for
  every page. Figure crops are small.
- **Backup:** tabled (R12). `files.sha256` lets any future copy be verified.

---

## 7. Extraction pipeline (R10)

Each stage is an idempotent step keyed by (sha256, stage, tool version, params). Stages write raw
artifacts first, then an ingest loads them.

| Stage | What | Candidate tool(s) | Output |
|---|---|---|---|
| 0 Inventory | hash, page count, text-layer probe per page, PDF metadata, scan routing | **pypdfium2** (Apache-2.0/BSD-3; PyMuPDF is AGPL) **[F]** | `files`, `pages` |
| 1 Native layer | words with positions, font sizes and weights, links | same | raw JSON |
| 2 Scholarly structure | header metadata, section tree, paragraphs, footnotes, figure and table captions with coordinates, parsed references, in-text citations linked to references | **GROBID 0.9.1**, CRF build first (the deep-learning build adds 2–4 F1 on references at 2–3× the time) **[F]**; Linux only (Colab, or WSL2/Docker locally) | TEI XML with `teiCoordinates` |
| 3 Layout, tables, OCR | reading order across 2–3 columns, table cells, figure crops, OCR for image-only scans | **Docling** (MIT, native Windows) **[F]**; OCR engine chosen in P4 | DoclingDocument JSON |
| 4 Equations | LaTeX per equation region | **Docling formula enrichment** (LaTeX) first; **MinerU 3.4** (LaTeX plus box per equation) as the comparison in P4 **[F]**. Nougat excluded (unmaintained, non-commercial weights); Marker/Surya only if both fail (weights licence, vLLM or llama.cpp server) | JSON |
| 5 Reconciliation | align stage 1–4 regions by page and box overlap; choose canonical text per region; record disagreements | project code | `blocks` (canonical flag), `tables`, `figures`, `equations` |
| 6 References | parse → Crossref match → link to `works`, else create `candidates` (found via citation) | project code + resolver | `references`, `citation_mentions`, `candidates` |
| 7 Chunks + embeddings | structure-aware chunks; embed | **bge-m3** lead candidate (MIT, 1024-d, 8192 tokens, dense + sparse) vs nomic-embed-text-v1.5 (Apache, 768-d) in P7; SPECTER2 optional for whole-paper similarity **[F]** | `chunks`, `embeddings` |
| 8 Vision on demand | figure descriptions; adjudicating disputed pages | Claude | `figures.description`, notes |

**Reconciliation rules (stage 5), initial, to be tuned in P4 on measured accuracy:**
- born-digital text: the native layer's characters win; the layout model supplies order and type;
- reading order and table structure: the layout model wins;
- sections, footnotes, captions, references, citation links: GROBID wins;
- inside equation regions: the math model's LaTeX, with the native text kept beside it;
- scans: OCR text, with confidence stored; any region where tools disagree beyond a threshold is
  marked `disputed` for stage 8;
- **coverage metric per file:** share of native-layer characters assigned to some canonical block
  (target set before P4 runs, not after).

---

## 8. Retrieval (R2)

- **Hybrid search:** Postgres full-text (`tsvector`) and trigram similarity (`pg_trgm`, bundled with
  PG18 — present on this machine) plus pgvector similarity, fused by reciprocal rank.
- **Filters:** block or chunk kind, work, year, gap, use status, workstream view (main or own).
- **Every hit returns** work key, file stem, page, bounding box and section path, so an answer can be
  cited and checked against the page.
- **A ready-made gold set:** the literature review's quote-gated quotes are known passages with
  known pages. P7 builds its evaluation queries from them, sets recall@k thresholds before running,
  and reports against them.

---

## 9. Access: package, CLI and MCP server (R2, R8)

- **Package** `litkb` under `Scripts/pipeline/litkb/` (added to `pyproject.toml` `packages`,
  respecting its documented shape): `db/` (connection, migrations as plain SQL files with a small
  runner), `admit/`, `acquire/` (open access, annas, scihub adapters), `extract/` (stages), `index/`
  (chunks, embeddings, search), `promote/`, `export/`, `mcp/`.
- **CLI:** `py -3.12 -m litkb <command>` — ws open/abandon, discover, admit, acquire, extract, ingest,
  audit, search, promote, export.
- **MCP server** (`litkb.mcp`), read-only by default:
  - query: `search`, `get_work`, `get_file_blocks`, `get_use_history`, `list_gaps`, `citations_of`,
    `cited_by`, `missing_citations(gap)`;
  - write (writer role, workstream required): `open_workstream`, `add_candidate`, `admit`,
    `request_acquisition`, `record_use_version`, `verify_quote`;
  - `promote` is not exposed to agents.
- **Ad-hoc SQL for Claude:** the crystaldba `postgres-mcp` server in `--access-mode=restricted`
  (read-only transactions) connected as `litkb_reader`, beside the domain tools above **[F]**.
- **Tests:** a throwaway database `litkb_test` created per run; a conftest guard refuses to connect
  to `litkb` itself (the same principle as the lake guard in `qc/conftest.py`).

---

## 10. Tool integration (R8)

| Existing tool | Becomes | Change |
|---|---|---|
| paper-search (21 sources, OA download) | `litkb.acquire.discover` and the open-access route | Called as a library from its installed package; results → `candidates`; free CORE/DOAJ keys and an Unpaywall email to be set by Kam |
| aa_fetch resolver | admission check 1 | Moves into `litkb.admit`; evidence stored on identifier versions |
| aa_fetch archive route and gates | `litkb.acquire.annas` | Writes `files` and `acquisition_attempts` instead of `manifest.csv`; the three gates, JSTOR evidence rule, retry ladder and quarantine behaviour kept; its 77 tests move with it |
| aa_fetch `--audit-fast` | `litkb audit` | Writes `file_checks` |
| Sci-Hub method (memory `scihub-fetch-method`) | `litkb.acquire.scihub` | Same route order: first index by curl, second by curl, browser last |
| `manifest.csv`, `Literature_Tracker.xlsx`, `literature_tracker.csv` | exports | Generated by `litkb export`; never edited by hand |
| `Scripts/docs/LITERATURE_CONVENTION.md` | the operating manual | Rewritten in P9 around the hunt protocol |

Secrets stay outside the repo; a check in the ladder fails if a key file, `.env` or `pgpass` is staged.

---

## 11. Colab bulk pass (R11)

- **Why Colab:** measured corpus 219 PDFs, 4,655 pages (Kam expects ~7,400 with the backlog);
  CPU runtimes cost nothing and run 3–4 in parallel (memory `cpu-runtimes-parallel-free`).
- **Shape:** stateless shards. Upload the PDFs to the Drive lake once (`treedata/literature_store/`,
  ~0.8 GB). Pack files into shards balanced by page count. Each shard runs on one CPU runtime through
  `pipeline/vm_ops.py` (the front door: one CLI call at a time, bootstrap verification, self-stop
  watchdog). Each VM installs the pinned toolchain, processes its shard, writes one artifact folder per
  file keyed by sha256 plus a done marker containing the artifact hashes.
- **Writing results:** through the project's existing verified writer path to the lake, with
  server-side verification using independent credentials (memory `verify-drive-path-never-idle`:
  a read-back through the writing mount proves nothing; service accounts have no Drive quota). The
  exact writer path is taken from `gen_vm_bootstrap.py` as it stands at P5, not assumed here.
- **Ingest:** local. `litkb ingest --from <lake path>` checks each done marker's hashes, loads
  artifacts into Postgres, and records `extraction_runs` with host `colab`.
- **Canary first:** one shard of the P4 hard papers, measuring seconds per page per stage on Colab
  CPU; the full-run wall-clock is projected from that measurement, not from published numbers.
- **GPU is optional and gated:** if the canary shows the layout or math stage is too slow on CPU, a
  GPU runtime is proposed to Kam with tier, count, expected wall-clock and cost (CLAUDE.md 3.4).
- **Reference speeds, not projections:** Docling reports 1.2–1.5 pages/s on its vendor's CPU and
  3.1–7.9 on GPU; GROBID reports 10.6 PDFs/s on 16 CPUs **[F]**. Colab's free CPU runtime is smaller
  (about 2 vCPU and 13 GB RAM, secondary sources only **[UNCONFIRMED]**), so the canary decides.
- **MinerU does not fit a free CPU runtime** (needs at least 16 GB RAM **[F]**): if P4 picks it, it
  runs on the laptop (63.8 GB RAM) or a GPU runtime.
- **Colab terms:** the free tier's terms prohibit "bypassing the notebook UI" and "distributed
  computing workers" **[F]**. The project already drives Colab headless through `vm_ops.py`; a
  parallel CPU fan-out is closer to that wording, so Kam decides whether to run shards in parallel,
  serially, or on a paid tier (§15).

---

## 12. Local incremental runs (R11)

- The same package, `--host local`. New files from acquisition enter an `extraction_queue`; a worker
  processes them stage by stage.
- **Parity rule:** a file processed on Colab and locally with the same pipeline version must give the
  same canonical blocks; P9 tests this on a sample.
- **This laptop (measured 2026-09-13):** Intel i7-9850H, 12 logical cores; 63.8 GB RAM; Quadro
  T2000 4 GB; Java 23; no Docker; WSL version 2 set as default but the WSL feature not enabled.
- **What runs natively:** pypdfium2, Docling (official Windows support), MinerU's pipeline backend
  (Windows, CPU or 4 GB GPU, RAM ample), embeddings, Postgres **[F]**.
- **What does not:** GROBID ("we cannot ensure currently support for Windows"; JDK 21+) **[F]** —
  locally it needs WSL2 enabled or Docker Desktop (§15). Until then stage 2 runs on Colab.

---

## 13. Migration of what exists

| Asset | Loads into | Check |
|---|---|---|
| `Validation\manifest.csv` (207 rows, hashes) | works (by DOI/arXiv), identifiers, files | every row maps; sha256 on disk matches |
| `_quarantine\` | files, status quarantined, reason from the recovery logs | counts match |
| `Literature_Tracker.xlsx` (460 rows) | works (deduplicated by identifier), gaps (from Feeds), uses version 1 (from Relevance, Evidence grade, Status) | export regenerates an equivalent tracker; row-level diff reviewed |
| Framework gap ledger rows | gaps | every `gap row N` resolves |
| Review §4.12–§4.19 findings, including refutations | use versions with evidence pointers | an agent drafts, a referee checks each against the review text |
| `audit_fast.csv`, acquisition logs | file_checks, acquisition_attempts | counts match |

---

## 14. Plan

Each phase ends with a commit on this branch, a gate that must pass, and a kill that must fire.
Designs and results in each phase are refereed by an agent other than the author (3.4c).

| Phase | Deliverable | Gate (pass) | Kill (must fire first) |
|---|---|---|---|
| **P0 Decisions** | Kam answers §15 | answers recorded in `decisions.yaml` | — |
| **P1 Foundation** | pgvector installed on PG18; database, roles, migrations; versioning, views, `promote()`; test DB guard | migration runner applies cleanly to an empty DB; test suite green | writer role UPDATE on a version table is refused; promotion flags a stale-base version; test run pointed at `litkb` aborts |
| **P2 Migration + exports** | §13 loaders; `litkb export` | regenerated tracker and manifest match today's content (reviewed diff) | a planted duplicate DOI and a planted wrong DOI (the Averkov case) are rejected at load |
| **P3 Acquisition** | admission, annas, scihub, paper-search adapters writing the DB; attempts log | 5 real DOIs admitted and acquired end to end | a DOI whose registry title does not match is refused; a wrong-paper file is quarantined |
| **P4 Extraction bake-off** | stages 0–5 run on ~10 hard papers (two-column article, three-column article, JSTOR scan, image-only scan, equation-heavy theory paper, table-heavy paper, the 688-page book), locally and on one Colab CPU runtime | tools chosen on measured reading order, table cell accuracy, reference parsing (checked against Crossref-deposited reference lists), header metadata (checked against registries), equation spot checks; thresholds written before measuring | a deliberately interleaved column extraction fails the reading-order metric; shuffled table cells fail the table metric |
| **P5 Colab bulk pass** | canary shard → projection → Kam's go (and GPU approval if proposed) → all shards → ingest | every active file has pages, blocks, chunks; coverage at or above the P4 threshold; disagreements logged | a shard with a corrupted artifact fails ingest verification |
| **P6 Citations** | references resolved, citation graph, citation candidates | reference resolution rate measured and reported | a fabricated reference does not resolve to a work |
| **P7 Retrieval** | embeddings, hybrid search, evaluation on the review-quote gold set | recall@k at or above the pre-registered threshold | a scrambled index (random vectors) fails the threshold |
| **P8 Access** | MCP server and CLI; hunt protocol written | an agent in a scratch worktree runs a full mini-hunt: open workstream → admit → acquire → extract → record use with verified quote → promote | a use with an unverifiable quote is refused at promotion |
| **P9 Local + retire old paths** | local worker, parity test, convention rewritten, hand-edited tracker retired | parity on a sample; old paths removed from the convention | a parity break introduced on purpose is caught |

**Order of value:** P1–P3 already fix today's pain (mergeable, versioned, concurrent records with
checks). P4–P7 add the knowledge layer. P8 makes it Claude's daily tool.

---

## 15. Decisions for Kam (P0)

1. **Server:** PostgreSQL 18 on port 5433 (proposed) or 17 on 5432.
2. **pgvector on Windows:** no prebuilt binary; building 0.8.6 needs Visual Studio C++ Build Tools
   and `nmake` **[F]** — accept the install.
3. **Embeddings stay local** (no text sent to a third-party embedding API) — proposed yes.
4. **Colab bulk pass on free CPU first**, GPU only by separate approval after the canary — proposed yes.
5. **paper-search keys:** set free CORE and DOAJ keys and an Unpaywall email (your email, your call).
6. **Derived artifacts location:** `D:\edmonds-pipeline\Literture\_derived\` — proposed yes.
7. **Promotion authority:** the orchestrator runs `promote` at merge and you review the committed
   report, or you run it yourself.
8. **Figure descriptions by Claude vision:** on demand only (proposed), or a bulk pass later.
9. **GROBID locally:** enable WSL2 (admin, one reboot) or install Docker Desktop, or keep stage 2 on
   Colab only.
10. **Colab terms:** run the bulk shards in parallel on free CPU runtimes as the project already
    does, serially, or on a paid tier (§11).

---

## 16. Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| GROBID is Linux-only in practice and needs JDK 21+ **[F]** | stage 2 cannot run natively on Windows | WSL2 or Docker locally (§15.9); Colab meanwhile |
| Layout or math models too slow on CPU | bulk pass takes days | canary measures first; GPU proposal gated by Kam |
| pgvector has no Windows binary **[F]** | P1 needs a C++ toolchain | Build Tools install (§15.2) |
| Colab free-tier terms **[F]** | parallel headless shards may breach them | Kam's call (§15.10) |
| MinerU needs at least 16 GB RAM **[F]** | does not fit free Colab CPU | laptop or GPU runtime |
| Scan OCR quality on 1950s–70s JSTOR papers | wrong text in theory papers | per-block confidence; disputed regions to vision; evidence quotes must verify |
| Colab writer path to Drive | artifacts silently lost | existing verified path + independent server-side check (memory) |
| Library licences **[F]**: PyMuPDF AGPL; Marker/Surya weights free only for research, personal use and startups under $5M; Nougat CC-BY-NC | constraints on use | pypdfium2 instead of PyMuPDF; Docling (MIT), GROBID (Apache-2.0), MinerU (Apache-based) preferred |
| Concurrency on one local server | Colab cannot write the DB | by design: Colab writes artifacts, ingest is local |
| Disk | derived artifacts grow | page images only for scans and disputed pages; sizes reported per phase |

---

## 17. Tool facts (verified 2026-09-13)

Collected by a research agent with a URL for every claim; the facts that shape the design are
restated here so this document stands alone.

| Tool | Facts used in this design | Still unconfirmed |
|---|---|---|
| GROBID 0.9.1 (2026-08-04) | JDK 21+ since 0.9.0; Windows not supported (Docker is the documented route); CRF image ~500 MB vs full image ~8 GB, full adds 2–4 F1 on reference parsing and 2–5 on citation context at 2–3× the time; 10.6 PDFs/s on 16 CPUs; `teiCoordinates` ("page,x,y,w,h") for references, bibliographic entries, figures, formulas, headings, sentences, paragraphs, notes, titles, affiliations; Apache-2.0 | whether Java 23 works; exact in-text citation target syntax; a Colab recipe |
| Docling | MIT; official Windows support; formula enrichment (CodeFormula) emits LaTeX; 1.2–1.5 pages/s CPU and 3.1–7.9 GPU (vendor hardware); DoclingDocument with body and furniture trees, reading order by child order, boxes where available | VRAM needed; OCR engine list; exact table and provenance schema |
| MinerU 3.4 (2026-06-18) | LaTeX plus box per equation (`content_list.json`, box scaled 0–1000, page index); licence now Apache-based (no longer AGPL); pipeline backend on CPU or 4 GB GPU, Windows; needs at least 16 GB RAM | Colab free RAM (secondary source ~13 GB) |
| Marker / Surya 2 | Apache-2.0 code; model weights free only for research, personal use and startups under $5M; now served through vLLM (Docker, GPU) or llama.cpp (CPU) | — |
| Nougat | last commits 2025-02-21 and 2023-10-04; weights CC-BY-NC | — |
| pypdfium2 / PyMuPDF | pypdfium2 Apache-2.0/BSD-3, text within boxes, page rendering, Windows wheels; PyMuPDF 1.28.2 AGPL or commercial | legal reading of AGPL (moot if pypdfium2 is used) |
| Embeddings | bge-m3: MIT, 1024-d, 8192 tokens, dense + sparse + multi-vector; nomic-embed-text-v1.5: Apache, 768-d (truncatable), 8192 tokens, 0.1B params; SPECTER2: Apache, 512 tokens, title + abstract per paper; pgvector indexes: 2,000-d `vector`, 4,000-d `halfvec` | scientific-retrieval benchmarks per model; bge-large, e5-large-v2, gte |
| pgvector 0.8.6 (2026-07-29) | PG18 supported since 0.8.1; Windows install by building with Visual Studio C++ and `nmake /F Makefile.win`; no prebuilt binary in the README | — |
| PostgreSQL 18.6 (this machine) | `pg_trgm` and `fuzzystrmatch` present in `share/extension`; `uuidv7` present in the catalog file (checked locally) | `uuidv7()` confirmed by query in P1 |
| postgres-mcp (crystaldba) | MIT; `uvx postgres-mcp`; `--access-mode=restricted` runs read-only transactions and rejects COMMIT/ROLLBACK | version; status of the older reference server |
| Colab free tier | limits fluctuate; VMs have a maximum lifetime; idle timeout; terms prohibit bypassing the notebook UI and distributed computing workers | 2 vCPU / ~13 GB RAM / 12 h / ~90 min idle (secondary sources); disk; apt and Java installs; Docling or GROBID speed on Colab |
