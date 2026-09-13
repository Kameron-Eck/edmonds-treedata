# Literature knowledge base — design, architecture and plan

**Status:** DRAFT revision 2 for Kam's approval, 2026-09-13 (revision 1 was refereed; the response
is §19). Nothing here is built. Every design claim is UNVALIDATED until the phase that tests it has
run on real data with its kill shown to fire (CLAUDE.md 3.4c).

**Evidence marks.** **[F]** = stated, with a URL, in the tool facts report
`Reports/LITKB_TOOL_FACTS_2026-09-13.md` (§17), and only as strongly as that report states it.
**[M]** = measured on this machine or disk on 2026-09-13, with the command named. **[UNCONFIRMED]**
= must be checked before it is relied on. A number with none of these marks is a design choice,
not a fact.

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

**Non-goals:** storing PDF bytes in Postgres; a backup system (R12 — but see §15.12 on a small
database dump); a public or multi-user service; replacing the research reports (briefs and findings
stay as reviewed documents in git).

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
      │  process:   workstreams · ws_heads · candidates · │                           │
      │             attempts · admissions · promotions ·  │                           │
      │             extraction_runs · file_checks         │                           │
      └───────▲───────────────────────▲───────────────────┘                           │
              │ ingest (local only)   │ admission / acquisition                        │
   ┌──────────┴─────────────┐  ┌──────┴─────────────────────────────┐     ┌────────────▼──────────┐
   │ extraction artifacts   │  │ paper-search (discover, OA)        │     │ exports: tracker.xlsx │
   │ _derived/<sha256>/…    │  │ resolver (Crossref/S2/arXiv)       │     │ tracker.csv, manifest │
   │ from Colab or local    │  │ aa_fetch (Anna's Archive), Sci-Hub │     │ promotion reports     │
   └──────────▲─────────────┘  └──────┬─────────────────────────────┘     └───────────────────────┘
              │                        │ PDFs (+ .txt extract written at landing)
   ┌──────────┴────────────────────────▼────────────────────────────────────────────────────────┐
   │ D:\edmonds-pipeline\Literture\<Topic>\<Surname_Year_slug>.pdf   (readable names, R9)       │
   └────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Four decisions carry the design:**

1. **One database, many related tables** — foreign keys only hold inside one database (R5, R7).
2. **Verified facts are visible at once; interpretations are promoted.** A study's identity, its
   files and its extracted text are facts checked against registries and hashes at admission: every
   worktree sees them immediately, so no two hunts acquire the same paper. What a study *means for the
   project* — uses, gaps, metadata judgements — is written into a workstream and promoted only after
   Kam has merged the branch (R3, §5).
3. **Version rows are never updated in place.** Every interpreted or corrected entity is an identity
   row plus append-only versions (R6). The one in-place change is the identity row's
   `current_version_id` pointer, and it moves only by compare-and-set inside a database function
   (§4.1). The roles agents use cannot UPDATE or DELETE version rows. Not every table is versioned —
   the list is in §4.1.
4. **The database runs only on this machine.** Colab is stateless compute: it reads PDFs from the
   Drive lake and writes packed extraction artifacts back; a local ingest step loads them (R11). The
   same pipeline code runs locally later, versioned.

---

## 3. Identifiers (R4)

- **Every row ID is a UUIDv7** — time-ordered, generated by the database or by a client offline
  (Colab). The installed PostgreSQL 18.6 catalog carries `uuidv7` (found in `share/postgres.bki`,
  2026-09-13, earlier session); P1 confirms it with a query **[UNCONFIRMED until P1]**.
- **Readable keys alongside, never instead:** `works.key` = the file stem (`Surname_Year_slug`,
  unique). **`works.key` is the one home for the stem** (§4.2): the manifest's `stem` column and the
  tracker's `File stem` column become exports of it, and files carry no stem column of their own.
  `workstreams.slug` is unique among open workstreams.
- **External identifiers are rows, not columns** — a study can carry several DOIs (Page 1954 has
  OUP and JSTOR DOIs), an arXiv id, an ISBN, a JSTOR stable id, PMID, OpenAlex id.
- **Project identifiers are rows too:** scheme `tracker` holds the tracker's `ID` (the convention
  defines it as "stable row identifier, contiguous 1..N, never reused or renumbered"), so every
  `[ID n]` cross-reference in reports and tracker cells keeps resolving after migration; scheme
  `legacy_stem` holds pre-convention stems from `Reports/lit_stem_rename_map.csv`.

---

## 4. Data model

### 4.1 The versioning pattern (used by every versioned entity)

```
<entity>            id (uuidv7) · created_at · created_in_ws → workstreams ·
                    current_version_id → <entity>_versions   (main's view; moved only by CAS)
<entity>_versions   version_id · <entity>_id · version_no (unique per entity) · …fields… ·
                    change_reason (required from v2) · based_on_version_id (required from v2) ·
                    workstream_id · agent · session_id · created_at ·
                    state: proposed | prepared | promoted | rejected | withdrawn ·
                    promoted_at · promotion_id
ws_heads            workstream_id · <entity> · <entity>_id · version_id   (a workstream's view; CAS)
```

- **Main's view** of an entity = the version its `current_version_id` points to. Not the highest
  version number: two writers can each create a higher-numbered version, and "highest wins" would let
  the later insert silently discard the earlier one's change.
- **A workstream's view** = its `ws_heads` row for the entity if one exists, else main's pointer.
- **Every write is compare-and-set, facts included.** A new version names its `based_on_version_id`;
  the write function inserts the version and, in the same transaction, moves the pointer with
  `UPDATE … SET current_version_id = :new WHERE id = :entity AND current_version_id = :based_on`
  (or the `ws_heads` equivalent for a proposal). Zero rows updated means someone else moved the
  pointer first: the transaction rolls back and the writer re-reads and redoes the change. Nobody's
  version is overwritten, and a stale base is refused at write time, not discovered at promotion.
- **Fact tables** (works, identifiers, files) use the same function against main's pointer directly,
  after their admission checks pass (§4.6): the history is kept, the promotion step is not.
- **Tables that are NOT versioned** (append-only logs, derived data or process state):
  `workstreams` (state moves open → merged/abandoned, recorded with timestamps, no history rows),
  `ws_heads` (pointers), `candidates`, `admissions`, `acquisition_attempts`, `promotions`,
  `extraction_runs`, `file_checks`, every §4.4 text table (`pages`, `blocks`, `tables`, `figures`,
  `equations`, `references`, `citation_mentions`, `chunks`, `embeddings` — immutable per extraction
  run; a rerun writes a new run), `use_evidence` and `use_embeddings` (immutable, attached to one use
  version).

### 4.2 Identity (facts)

| Table | Key columns | Notes |
|---|---|---|
| `works` / `work_versions` | key (the stem, §3); type (article, book, chapter, proceedings, report, thesis, preprint, dataset); title, subtitle; authors (ordered JSON: family, given, ORCID); year; venue; volume, issue, pages; publisher; language; abstract | Versioned: a corrected title or year is a new version with a reason |
| `identifiers` / `identifier_versions` | work_id; scheme (doi, arxiv, jstor, isbn, pmid, pmcid, openalex, s2, handle, url, tracker, legacy_stem); value (as found); **value_norm** (normalised, §4.6); verified_by (crossref, datacite, arxiv, s2, manual); evidence (JSON: registry title, first author, year, ratio) | Partial unique index on (scheme, value_norm) where the current version is active. A DOI proven wrong (the Averkov 2009 case) gets a `retracted` version with its reason |
| `files` / `file_versions` | work_id; rel_path; **sha256** (unique); md5 (Anna's Archive identity); bytes; pages; has_text_layer; pdf metadata (JSON: info dict, XMP, producer, creator); copy_kind (publisher, author manuscript, preprint, scan); source_route; source_url; obtained_at; txt_extract_path; binding (JSON: matched title line, ratio, first author, page); status (active, quarantined, superseded) + reason; **current_run_id** → extraction_runs | R9: the hash and everything about the file live here; the name on disk stays readable. A check asserts the file name stem equals its work's `key`; how a second copy of the same work is named (Brook 1972) is settled in P3 against the files on disk **[UNCONFIRMED]** |
| `file_checks` | file_id; check (hash, content vs registry, archive record); verdict; detail; run_at | Re-audits over time (the `--audit-fast` logic). The binding check itself is an admission gate (§4.6), not an audit |

### 4.3 Process

| Table | Purpose |
|---|---|
| `workstreams` | id; slug; git_branch; worktree_path; purpose; brief_path; state (open, merged, abandoned); opened_at; closed_at; merge_commit |
| `candidates` | Leads not yet admitted: source (paper-search source, citation, manual); query or citing reference; raw record (JSON); title/authors/year/ids as found; state (new, admitted, duplicate, rejected) + reason; admitted_work_id |
| `admissions` | id; candidate_id; route (registry, manual); admitter agent + session; state (admitted, proposed, approved, refused); approver agent + session; approved_at; checks (JSON: every §4.6 check with its inputs and verdict) |
| `acquisition_attempts` | work or candidate; route (open access, annas, scihub, browser); identifier used; status (ok, not-in-archive, bad-file, binding-failed, partner-404, …); detail; http codes; at; workstream |
| `promotions` | id; workstream_id; state (prepared, committed, abandoned); prepared_at; branch_head_commit; version_set_hash; report_path; merge_commit; committed_at; counts; conflicts (JSON) |
| `extraction_runs` | file_id; stage; tool; tool_version; params hash; pipeline_version; host (colab, local); status; artifact_path; metrics (JSON: seconds, pages/s, coverage) |

`parent_workstream` (revision 1) is dropped: nothing in R1–R12 asks for nested workstreams, and it
had no defined effect on either view.

### 4.4 Text and structure (derived, R10)

| Table | Key columns |
|---|---|
| `pages` | file_id; run_id; page_no (1-indexed); width, height (PDF points); rotation; text_layer_chars; needs_ocr; image_path (rendered only when needed) |
| `blocks` | id; file_id; run_id; page_no; bbox (canonical frame, §7.1); reading_order; **type** (title, author, affiliation, abstract, heading, paragraph, list_item, footnote, caption, table, figure, equation, reference, page_header, page_footer, page_number, sidebar, other); section_path (text[]); text; latex; parent_block_id (caption → its figure or table); extractor; confidence; canonical (bool, set by reconciliation) |
| `tables` | block_id; n_rows; n_cols; cells (JSON: row, col, rowspan, colspan, text, is_header); caption_block_id |
| `figures` | block_id; crop_path; caption_block_id; description; description_model |
| `equations` | block_id; latex; display or inline; label (e.g. "3.19") |
| `references` | id; file_id; run_id; block_id; raw text; parsed (JSON: authors, title, year, venue, volume, pages, DOI); resolved_work_id; resolution (resolved, candidate, unresolved); confidence |
| `citation_mentions` | block_id; reference_id; char span — links an in-text citation to its reference |
| `chunks` | id; file_id; work_id; run_id; block_ids; kind (abstract, prose, table, caption, equation, reference); section_path; page_start, page_end; text (with section heading prepended as context); tokens |
| `embeddings` | chunk_id; model; dim; vector (`halfvec`); created — separate table so models can be swapped or compared |

Extraction rows are keyed by (file sha256, stage, tool version, params hash). Rerunning with the same
key is a no-op; a new pipeline version writes new runs and the old ones stay queryable.
**Each file has one current run** (`files.current_run_id`, moved by compare-and-set like any
pointer). Search, exports and new evidence read only the current run's blocks; older runs are kept
for comparison, never mixed into results.

### 4.5 Knowledge (interpretation, R5, R6)

| Table | Key columns |
|---|---|
| `gaps` / `gap_versions` | slug; question; framework pointer (e.g. "gap row 6"); brief_path; state (open, closed, abandoned) |
| `uses` | id; work_id; gap_id (nullable); created_in_ws; current_version_id |
| `use_versions` | statement (what the work supplies or was thought to supply); kind (method, theorem, parameter, empirical evidence, negative result, context, contradiction); **status** (proposed, supported, refuted, superseded, withdrawn); confidence; feeds (tokens: `framework §N`, `gap row N`, `decision <slug>` …); rationale; change_reason; based_on_version_id; workstream; agent; state + promotion fields |
| `use_evidence` | use_version_id; block_id; run_id; page; **quote; char_start; char_end** (offsets into the block's text); stance (supports, refutes, context); **quote_verified** |
| `use_embeddings` | use_version_id; model; vector — so Claude can ask "what have we already used literature for on X?" |

**`quote_verified` is computed by the database, never written by a client.** A `BEFORE INSERT`
trigger sets it to whether `substring(block.text from char_start + 1 for char_end - char_start)`
equals `quote` exactly; the writer role has no column privilege on it, so a client-supplied value
cannot survive. Evidence rows are immutable and remember the run they were anchored in; the view
`use_evidence_status` also reports whether that run is still its file's current run, and promotion
(§5) refuses evidence that is unverified or anchored in a superseded run until it is re-anchored.

**Worked example.** Efron 2004 enters once as a work. Round 4 records a use: "supplies the optimism
identity under an arbitrary joint model", status `supported`, evidence on p. 624, eq. 3.19, feeds
`gap row 6`. A later hunt finds the per-cell form fails for spatially coupled cells: it writes
version 2, status `refuted`, based on version 1, with its reason and evidence. Main's pointer moves
to v2 when the promotion commits; v1 stays readable. A different worktree records a *second* use of
Efron 2004 (the bootstrap variance), a separate `uses` row with its own history.

### 4.6 The checks (R7)

**Admission is one transaction.** Candidate → checks → `works`, `identifiers`, `files` and the
`admissions` row either all commit or none do. Two sessions admitting the same identifier at once
collide on the unique index; the loser's transaction rolls back and it reads the winner's work.

**Check 1 — the study exists.** Before any `works` row:
- a DOI confirmed on Crossref or DataCite with normalised title ratio ≥ 0.85, first-author surname
  match and year match — the rule in `Scripts/docs/LITERATURE_CONVENTION.md` ("DOI-first rule").
  The convention requires the year to *match*; revision 1 wrongly said ±1 for online-first. Whether
  to allow that tolerance is Kam's rule to change (§15.15);
- or an arXiv id confirmed on the arXiv API; or an ISBN confirmed against a registry record;
- the registry evidence JSON is stored on the identifier version, so the check is auditable later.

**Check 2 — no duplicate study.**
- Identifiers are normalised before comparison and the database enforces uniqueness on the
  normalised form: DOIs lowercased with any `https://doi.org/` or `doi:` prefix stripped; arXiv ids
  with the version suffix stripped. The real case: the manifest carried `10.4171/JEMS/183` before
  the 2026-09-13 audit fix and `10.4171/jems/179` after — case differences must never create two
  rows.
- A work with **no identifier** is compared by trigram similarity of normalised title plus year
  against every existing work. The threshold is not set here: P2 calibrates it on the tracker's
  existing `Duplicate of` pairs (real known duplicates) before it is used **[UNCONFIRMED]**. A hit
  sends the candidate to `duplicate` review instead of admitting it.

**Check 3 — the file is that study (binding), at admission.** A file is admitted only if its title
is found in the PDF header metadata or in the first page's text with normalised ratio ≥ 0.85 against
the *registry* title, and the registry first-author surname appears there too. The matched line,
ratio and page go into `files.binding`. Search every first-page line, not the first line: the Higham
2011 file is an author manuscript whose first line is MIMS EPrint boilerplate, while its title and
authors follow further down (`audit_fast.csv`, 2026-09-13 **[M]**). A file with no text layer on its
first page cannot pass and is quarantined as `binding-pending` until OCR (P4 onward) or a manual
admission binds it. Rationale: in revision 1 binding was a later audit, and the manifest shows what
that costs — two files sat under wrong DOIs with `verified_against_extract = yes` until an audit
caught them.

**Check 4 — manual admissions are proposals.** A work with no confirmable identifier (older
proceedings, reports) is admitted with `verified_by = manual` and its `admissions.state = proposed`:
evidence rows name the source and a held file whose text contains the title. It becomes visible as
a fact only when approved by an agent *and* session different from the admitter's (a check
constraint on `admissions`); until then it appears only in its workstream's view and is flagged in
exports. Limits: agent and session names are recorded by the client, so the constraint stops an
honest mistake, not a forged identity. Whether sign-off must come from Kam is §15.13.

**Check 5 — every reference points at something real.** Enforced by the database: foreign keys,
the unique normalised identifiers, unique sha256, enum checks on every status column, a regex check
on `works.key`, `change_reason` and `based_on_version_id` required for version ≥ 2, `version_no`
unique per entity. The agent roles can INSERT but not UPDATE/DELETE version tables; only the write
and promotion functions move pointers or change `state`.

### 4.7 Roles

| Role | Can | Used by |
|---|---|---|
| `litkb_reader` | SELECT | the MCP query tools; exports |
| `litkb_writer` | INSERT into proposals, candidates, admissions, attempts, extraction tables; EXECUTE the write functions; no column privilege on `quote_verified` or any `state` | agents, acquisition, ingest |
| `litkb_promoter` | EXECUTE `promote_prepare()` and `promote_commit()` | §5; who holds it is §15.7 |
| `litkb_test` | CONNECT on database `litkb_test` only (CONNECT on `litkb` revoked from PUBLIC) | the test suite (§9) |
| `litkb_owner` | DDL, migrations | migration runner only |

Credentials live in `D:\edmonds-pipeline\secrets\` (a `pgpass` file), never in the repo.

---

## 5. Workstreams and promotion (R3)

`main` belongs to Kam. Nothing in this section merges, pushes or commits to `main`; promotion reads
git to confirm that Kam has merged.

1. **Open.** `litkb ws open --slug <slug> --branch <git branch> --purpose "…" [--brief <path>]`
   writes the workstream and a git-ignored `.litkb-workstream` file in the worktree root. Every
   write from that worktree carries its ID.
2. **Work.** Agents admit works and files (facts, visible to all once admitted, §4.6), and record
   gaps, uses and evidence as `proposed` versions (visible through their workstream's `ws_heads`).
3. **Prepare, on the branch.** `litkb promote prepare --ws <slug>`:
   - groups proposed versions into **chains**: all of one entity's versions in the workstream after
     main's current version, plus everything the chain depends on — its work and identifiers
     admitted and approved, the gap version it points to (promoted, or in this promotion), its
     evidence rows, and its `based_on_version_id` (main's current, or earlier in the same chain);
   - re-runs the checks: evidence `quote_verified` and anchored in the file's current run, feeds
     tokens valid, no positional references;
   - flags conflicts (a chain whose base is no longer main's pointer) and near-duplicate uses of the
     same work and gap;
   - marks clean chains `prepared`, records a `promotions` row with the branch head commit and a hash
     of the exact version set, and writes the report to
     `Reports/litkb_promotions/<date>_<slug>.md` — committed **on the work branch**, so it goes to
     Kam inside the merge he reviews.
4. **Commit, only after Kam merges.** `litkb promote commit --ws <slug> --merge-commit <sha>`:
   - refuses unless `git merge-base --is-ancestor <sha> main` succeeds against a freshly fetched
     `main`, and the prepared commit is an ancestor of `<sha>`;
   - refuses if the version set no longer hashes to what was prepared (something changed after the
     report Kam saw);
   - in one transaction, for each chain **all or nothing**: compare-and-set main's pointers from
     each chain's base to its head. If any pointer in a chain has moved, that chain stays `prepared`
     with a conflict note, and every chain that depends on it stays too;
   - marks the workstream `merged` with the merge commit.
5. **Abandon.** `litkb ws abandon` marks the workstream; its versions stay, invisible to main.

---

## 6. File store and metadata (R9, R12)

- **PDFs:** `D:\edmonds-pipeline\Literture\<Topic>\<Surname_Year_slug>.pdf`, as today.
- **The convention's two loss rules stay in force** (`LITERATURE_CONVENTION.md`, written after the
  2026-09-12 loss of 149 PDFs): the `.txt` extract is written the moment a PDF lands and is the
  durable copy — the database and `_derived/` do not replace it; and acquisition agents and litkb
  never hold delete permission in these folders. Quarantine is a move to `_quarantine\`, never a
  delete.
- **Derived artifacts** (raw tool outputs, figure crops, rendered pages for scans):
  `D:\edmonds-pipeline\Literture\_derived\<sha256>\<stage>\…` — keyed by hash, so renames never
  orphan them.
- **Metadata captured per file** at inventory: sha256, md5, bytes, page count, PDF version, info
  dictionary, XMP, producer/creator, encryption flags, per-page text-layer size, fonts summary,
  scan detection; plus registry metadata on the work and GROBID's header parse — all three kept so
  disagreements (a wrong DOI, a missing year) are visible.
- **Disk [M]:** D: had 139 GB free on 2026-09-13 (`df -h /d`). PDFs under `Literture\`: 219 active
  files in `ASPP`, `Labeling`, `Validation`, `other` = 756.5 MB (721.5 MiB); with the 17 in
  `_quarantine\`, 236 files = 807.7 MB (770.3 MiB) (`find -printf %s`, summed). Revision 1's
  "771 MB" was the quarantine-inclusive MiB figure presented as the active corpus. Page images are
  the only large derived item; they are rendered for scans and disputed pages only. Figure crops are
  small.
- **Backup:** tabled (R12). `files.sha256` lets any future copy be verified. The database itself
  holds things no file can regenerate (use histories, approvals, promotions); whether a small
  `pg_dump` is in scope is §15.12.

---

## 7. Extraction pipeline (R10)

Each stage is an idempotent step keyed by (sha256, stage, tool version, params). Stages write raw
artifacts first, then an ingest loads them.

| Stage | What | Candidate tool(s) | Output |
|---|---|---|---|
| 0 Inventory | hash, page count, text-layer probe per page, PDF metadata, scan routing | **pypdfium2** (Apache-2.0/BSD-3 **[F]**; PyMuPDF is AGPL or commercial **[F]**) | `files`, `pages` |
| 1 Native layer | words with positions, font sizes and weights, links | same (per-character box API name **[UNCONFIRMED]**) | raw JSON |
| 2 Scholarly structure | header metadata, section tree, paragraphs, footnotes, figure and table captions with coordinates, parsed references, in-text citations linked to references | **GROBID 0.9.1**, CRF image first (the deep-learning image adds 2–4 F1 on reference parsing at 2–3× the time **[F]**). JDK 21 or higher **[F]**; its maintainers "cannot ensure currently support for Windows", Docker is the documented alternative **[F]** — so here it runs on Colab (Linux), or locally only under WSL2/Docker (§15.9). A Colab recipe is **[UNCONFIRMED]**: P4 tests it | TEI XML with `teiCoordinates` |
| 3 Layout, tables, OCR | reading order across 2–3 columns, table cells, figure crops, OCR for image-only scans | **Docling** (MIT, Windows supported **[F]**); OCR engine chosen in P4 (engine list **[UNCONFIRMED]**) | DoclingDocument JSON |
| 4 Equations | LaTeX per equation region | **Docling formula enrichment** (CodeFormula, LaTeX **[F]**) first; **MinerU 3.4** (LaTeX plus a 0–1000 box and page index per equation **[F]**) as the comparison in P4. Nougat excluded: weights CC-BY-NC **[F]**, and its last commits are 2025-02-21 and 2023-10-04 **[F]** (that it is unmaintained is our inference from those dates). Marker/Surya only if both fail (weights free only for research, personal use and startups under $5M **[F]**; served through vLLM or llama.cpp **[F]**) | JSON |
| 5 Reconciliation | map every tool's boxes to the canonical frame (§7.1); align regions by page and box overlap; choose canonical text per region; record disagreements | project code | `blocks` (canonical flag), `tables`, `figures`, `equations` |
| 6 References | parse → Crossref match → link to `works`, else create `candidates` (found via citation) | project code + resolver | `references`, `citation_mentions`, `candidates` |
| 7 Chunks + embeddings | structure-aware chunks; embed | **bge-m3** lead candidate (MIT, 1024-d, 8192 tokens, dense + sparse **[F]**) vs nomic-embed-text-v1.5 (Apache-2.0, 768-d, 8192 tokens **[F]**) in P7; SPECTER2 optional for whole-paper similarity (512 tokens, title + abstract **[F]**) | `chunks`, `embeddings` |
| 8 Vision on demand | figure descriptions; adjudicating disputed pages | Claude | `figures.description`, notes |

### 7.1 One coordinate frame, one adapter per tool

Boxes from different tools cannot be overlapped until they share a frame, and the tools disagree on
every axis of it. **Canonical frame:** PDF points, page numbers 1-indexed, origin at the top-left
of the page as displayed (rotation applied), box = (x0, y0, x1, y1). Each tool gets an adapter:

| Tool | What it emits | Adapter |
|---|---|---|
| GROBID | `"page,x,y,w,h"`, page 1-indexed, PDF units, origin upper-left **[F]** | x1 = x + w, y1 = y + h |
| MinerU | `bbox` normalised 0–1000, `page_idx` 0-based **[F]** | scale by page width/height ÷ 1000; page + 1 |
| pypdfium2 | bounded text takes (left, bottom, right, top) **[F]**, implying a bottom-left origin (our inference **[UNCONFIRMED]**) | y flipped against page height; rotation applied |
| Docling | "bounding boxes for all items, if available" **[F]**; field names and origin **[UNCONFIRMED]** | written in P4 after reading its output on a real page |

**Test (P4, before reconciliation is written):** on one born-digital page, take a word whose box
pypdfium2 reports, and require every adapter's box for the region containing that word to contain
it. A tool whose adapter fails the test contributes no boxes. The test must also fail when one
adapter's page offset or y-flip is deliberately removed.

**Reconciliation rules (stage 5), initial, to be tuned in P4 on measured accuracy:**
- born-digital text: the native layer's characters win; the layout model supplies order and type;
- reading order and table structure: the layout model wins;
- sections, footnotes, captions, references, citation links: GROBID wins;
- inside equation regions: the math model's LaTeX, with the native text kept beside it;
- scans: OCR text, with confidence stored; any region where tools disagree beyond a threshold is
  marked `disputed` for stage 8;
- **coverage metric per file:** share of native-layer characters assigned to some canonical block
  (target frozen before P4 runs, §14).

---

## 8. Retrieval (R2)

- **Hybrid search:** Postgres full-text (`tsvector`) and trigram similarity (`pg_trgm`; its
  `pg_trgm.control` file is present in `C:\Program Files\PostgreSQL\18\share\extension` **[M]**,
  loading it is P1) plus pgvector similarity, fused by reciprocal rank.
- **Filters:** block or chunk kind, work, year, gap, use status, workstream view (main or own).
- **Every hit returns** work key, page, bounding box and section path, from the file's current
  extraction run, so an answer can be cited and checked against the page.
- **Evaluation set:** the literature review's quote-gated quotes are known passages with known pages.
  Verbatim quotes would be found by the lexical legs alone, so they cannot test the vectors: a
  referee (not the author of the retrieval code) writes a **paraphrased** query for each, frozen in
  git before P7 runs; recall@k thresholds are frozen with it, and the vector leg and the hybrid are
  scored separately (§14 P7).

---

## 9. Access: package, CLI and MCP server (R2, R8)

- **Package** `litkb` under `Scripts/pipeline/litkb/` (added to `pyproject.toml` `packages`,
  respecting its documented shape): `db/` (connection, migrations as plain SQL files with a small
  runner), `admit/`, `acquire/` (open access, annas, scihub adapters), `extract/` (stages), `index/`
  (chunks, embeddings, search), `promote/`, `export/`, `mcp/`.
- **Dependencies stay out of the engine's environment.** `Scripts/requirements-litkb.txt` (database,
  CLI, MCP, resolver) and `Scripts/requirements-litkb-extract.txt` (Docling, MinerU, embedding
  models) are separate from `requirements-colab.txt` / `requirements-local.txt`. Heavy libraries are
  imported inside the functions that use them, never at module top; a test asserts that
  `import litkb` loads none of them, so `qc/check.py`'s compile and test sweep never pulls torch or
  Docling.
- **CLI:** `py -3.12 -m litkb <command>` — ws open/abandon, discover, admit, approve, acquire,
  extract, ingest, audit, search, promote prepare/commit, export.
- **MCP server** (`litkb.mcp`), read-only by default:
  - query: `search`, `get_work`, `get_file_blocks`, `get_use_history`, `list_gaps`, `citations_of`,
    `cited_by`, `missing_citations(gap)`;
  - write (writer role, workstream required): `open_workstream`, `add_candidate`, `admit`,
    `request_acquisition`, `record_use_version`, `verify_quote`;
  - `approve`, `promote prepare` and `promote commit` are not exposed to agents.
- **Ad-hoc SQL for Claude:** the crystaldba `postgres-mcp` server in `--access-mode=restricted`
  (read-only transactions, rejects COMMIT/ROLLBACK **[F]**) connected as `litkb_reader`, beside the
  domain tools above — two locks, since a parser guard alone is defence in depth.
- **Tests:** a throwaway database `litkb_test`, connected through the `litkb_test` role, which can
  CONNECT to `litkb_test` and nothing else — so a test that is pointed at `litkb` fails in the
  server, not only in a client-side conftest guard (the lake-guard lesson in `qc/conftest.py`). Tests
  that need the server carry a `requires_litkb_pg` marker and skip when the server or role is absent,
  so the ladder still runs on a machine without Postgres; the skip count is printed, never silent.

---

## 10. Tool integration (R8)

| Existing tool | Becomes | Change |
|---|---|---|
| paper-search (21 sources, OA download) | `litkb.acquire.discover` and the open-access route | Called as a library from its installed package; results → `candidates`; free CORE/DOAJ keys and an Unpaywall email to be set by Kam |
| aa_fetch resolver | admission checks 1–3 | Moves into `litkb.admit`; evidence stored on identifier versions |
| aa_fetch archive route and gates | `litkb.acquire.annas` | Writes `files` and `acquisition_attempts` instead of `manifest.csv`; the three gates, JSTOR evidence rule, retry ladder and quarantine behaviour kept; its test file moves with it (`D:\tools\annas-mcp\test_aa_fetch.py`: 80 `def test_` definitions, 2026-09-13 **[M]**, `grep -c`; the collected count may differ) |
| aa_fetch `--audit-fast` | `litkb audit` | Writes `file_checks` |
| Sci-Hub method (memory `scihub-fetch-method`) | `litkb.acquire.scihub` | Same route order: first index by curl, second by curl, browser last |
| `manifest.csv`, `Literature_Tracker.xlsx`, `literature_tracker.csv` | exports | Generated by `litkb export`; never edited by hand |
| `Scripts/docs/LITERATURE_CONVENTION.md` | the operating manual | Its tracker section says the xlsx is "human-edited" and "authoritative"; that becomes false the moment exports exist, so it is rewritten **in P3**, in the same commit that makes the tracker an export. The hunt protocol is added in P8 |

Secrets stay outside the repo; a check in the ladder fails if a key file, `.env` or `pgpass` is staged.

---

## 11. Colab bulk pass (R11)

- **Why Colab:** the active corpus is 219 PDFs, 4,655 pages (`pdfinfo` over every active PDF,
  2026-09-13 **[M]**; the largest is the 688-page Schneider 2008 book). Kam expects ~7,400 pages with
  the backlog (his estimate). CPU runtimes cost 0 compute units (`Scripts/pipeline/colab_rates.csv`,
  PUBLISHED tier) and run 3–4 in parallel (memory `cpu-runtimes-parallel-free`).
- **Account:** the project account is on **Colab Pro**, not the free tier (`colab_rates.csv`,
  screen-read 2026-09-01). The CPU runtime size a Pro account gets is **[UNCONFIRMED]**; the canary
  measures it.
- **Shape:** stateless shards. The PDFs would be uploaded to the Drive lake once
  (`treedata/literature_store/`, ~0.8 GB) — but part of the corpus came from shadow libraries, so
  putting it on Drive is Kam's decision (§15.11). How much is not known: `Validation\manifest.csv`
  records `unknown (pre-manifest)` for 196 of 207 rows; of the 11 with a route, 6 are Anna's Archive,
  2 a Sci-Hub mirror, 2 arXiv, 1 Copernicus **[M]**. Files are packed into shards balanced by page count. Each
  shard runs on one CPU runtime through `pipeline/vm_ops.py` (the front door: one CLI call at a time,
  bootstrap verification, self-stop watchdog). Each VM installs the pinned toolchain, processes its
  shard, and writes **one packed archive per shard** (per-file artifact folders inside it, keyed by
  sha256) plus a done marker holding each artifact's hash. Packed, because Drive throughput depends on
  size class and stalls in bursts (memory `drive-throughput-and-claims-drift`): thousands of small
  per-file writes are the slow case.
- **Writing results:** through the project's existing verified writer path to the lake, with
  server-side verification using independent credentials (memory `verify-drive-path-never-idle`:
  a read-back through the writing mount proves nothing). The exact writer path is taken from
  `gen_vm_bootstrap.py` as it stands at P5, not assumed here.
- **Ingest:** local. `litkb ingest --from <lake path>` checks each done marker's hashes, unpacks,
  loads artifacts into Postgres, records `extraction_runs` with host `colab`, and moves each file's
  `current_run_id`.
- **Canary first:** one shard of the P4 hard papers, measuring seconds per page per stage and the
  runtime's CPU and RAM; the full-run wall-clock is projected from that measurement, not from
  published numbers.
- **GPU is optional and gated:** if the canary shows the layout or math stage is too slow on CPU, a
  GPU runtime is proposed to Kam with tier, count, expected wall-clock and cost (CLAUDE.md 3.4).
- **Reference speeds, not projections:** Docling reports 1.2–1.5 pages/s CPU-only and 3.1–7.9 on GPU,
  on its vendor's hosts **[F]**; GROBID reports 10.6 PDFs/s on one 16-CPU, 32 GB machine **[F]**.
- **MinerU needs at least 16 GB RAM [F].** Whether a Colab CPU runtime on this account has that is
  **[UNCONFIRMED]** (secondary sources put the free tier at ~13 GB; the account is Pro). If P4 picks
  MinerU and the canary shows too little RAM, it runs on the laptop (63.8 GB **[M]**) or a GPU runtime.
- **Colab terms:** the Colab FAQ says the free tier disallows "bypassing the notebook UI" and
  "distributed computing workers" **[F]**. What the Pro terms say about headless multi-VM work is
  **[UNCONFIRMED]**. This is not a question about this pass: the project already drives Colab
  headless through `vm_ops.py` and fans CPU runtimes out, so the question is project-wide (§15.10).

---

## 12. Local incremental runs (R11)

- The same package, `--host local`. New files from acquisition enter an `extraction_queue`; a worker
  processes them stage by stage.
- **Parity rule:** a file processed on Colab and locally with the same pipeline version must give the
  same canonical blocks; P9 tests this on a sample.
- **This laptop [M] (2026-09-13, earlier session):** Intel i7-9850H, 12 logical cores; 63.8 GB RAM;
  Quadro T2000 4 GB; Java 23; no Docker; WSL version 2 set as default but the WSL feature not enabled;
  PostgreSQL 17 and 18 installed.
- **What the sources say runs on Windows:** pypdfium2 (Windows wheels **[F]**), Docling (Windows
  supported **[F]**; 4 GB VRAM sufficiency **[UNCONFIRMED]**), MinerU's pipeline backend (Windows,
  CPU or ≥4 GB VRAM **[F]**). The embedding models on this laptop are **[UNCONFIRMED]** (the facts
  report does not cover it); P7 measures it.
- **What does not:** GROBID ("We cannot ensure currently support for Windows"; JDK 21 or higher
  **[F]**; Java 23 specifically **[UNCONFIRMED]**) — locally it needs WSL2 enabled or Docker Desktop
  (§15.9). Until then stage 2 runs on Colab.

---

## 13. Migration of what exists

All loaders go through the P2 admission code (§4.6) — migration is admission in bulk, not a bypass.

| Asset | Loads into | Check |
|---|---|---|
| `Validation\manifest.csv` (207 data rows **[M]**, `wc -l` 208 with header; hashes) | works (by DOI/arXiv), identifiers, files | every row maps or is refused with a reason; sha256 on disk matches; binding check passes |
| `_quarantine\` (17 PDFs **[M]**) | files, status quarantined, reason from the recovery logs | counts match |
| `Literature_Tracker.xlsx` (460 rows **[M]**, from `Reports/literature_tracker.csv`, 461 lines with header) | works (deduplicated by identifier), `tracker` identifiers from `ID`, gaps (from Feeds), uses version 1 (from Relevance, Evidence grade, Status) | export regenerates an equivalent tracker; row-level diff reviewed; every `[ID n]` resolves |
| `Reports/lit_stem_rename_map.csv` | `legacy_stem` identifiers | every legacy stem resolves to one work |
| Framework gap ledger rows | gaps | every `gap row N` resolves |
| Review §4.12–§4.19 findings, including refutations | use versions with evidence pointers | an agent drafts, a referee checks each against the review text |
| `audit_fast.csv`, acquisition logs | file_checks, acquisition_attempts | counts match |

---

## 14. Plan

Each phase ends with a commit on this branch, a gate that must pass, and a kill that must fire.
Designs and results in each phase are refereed by an agent other than the author (3.4c). **Gold data
and thresholds for any measured gate are written by a referee and committed (their git hash recorded
in the phase's report) before the tool or code being measured first runs on them.**

Order (revision 2): admission is built before migration, because migration is admission in bulk and
P3's kill needs the gate.

| Phase | Deliverable | Gate (pass) | Kill (must fire first) |
|---|---|---|---|
| **P0 Decisions** | Kam answers §15 | answers recorded in `decisions.yaml` | — |
| **P1 Foundation** | pgvector installed on PG18; database, roles, migrations; versioning with pointers and compare-and-set write functions; views; `promote_prepare()` / `promote_commit()`; test role and skip marker | migration runner applies cleanly to an empty DB; `uuidv7()` answers; test suite green | writer role UPDATE on a version table is refused; two writers based on the same version — the second is refused, **for a fact table and for a proposal**; a client-supplied `quote_verified = true` on a non-matching quote is stored false; the `litkb_test` role connecting to `litkb` is refused by the server; `promote commit` with a merge commit that is not reachable from `main` is refused; a chain whose gap dependency conflicts is not promoted, and neither is its dependent |
| **P2 Admission + acquisition** | admission checks 1–5 in one transaction; approve flow; annas, scihub, paper-search adapters writing the DB; attempts log | 5 real DOIs admitted and acquired end to end; the no-identifier title threshold calibrated on the tracker's `Duplicate of` pairs | **replays the real pre-fix manifest rows** (fixture: the backup `manifest.pre-auditfix.csv`, copied into the test data): Averkov 2009 with `10.4171/JEMS/183` (Crossref title "Heegard Floer invariants of Legendrian knots in contact three-manifolds", ratio 0.36) and Higham 2011 with `10.1016/j.laa.2010.09.001` (ratio 0.25), each with its real file — both refused at binding (`audit_fast.csv` **[M]**); the corrected DOIs (`10.4171/jems/179`, `10.1016/j.laa.2010.04.007`) admit the same files; `10.4171/JEMS/179` after `10.4171/jems/179` collides; two concurrent admissions of one DOI leave one work; a known `Duplicate of` pair re-entered without identifiers is sent to duplicate review; an admitter approving its own manual admission is refused |
| **P3 Migration + exports** | §13 loaders through P2 admission; `litkb export`; convention rewritten (§10) | regenerated tracker and manifest match today's content (reviewed diff) | a planted duplicate DOI and the planted Averkov wrong DOI are rejected at load |
| **P4 Extraction bake-off** | stages 0–5 run on ~10 hard papers (two-column article, three-column article, JSTOR scan, image-only scan, equation-heavy theory paper, table-heavy paper, the 688-page book), locally and on one Colab CPU runtime; bbox adapters (§7.1) | GROBID 0.9.1 CRF boots on a Colab CPU runtime and returns TEI with coordinates for one paper; adapters pass the §7.1 test; tools chosen against **referee-authored, pre-committed gold**: reading-order sequences, table cells, header metadata, equation LaTeX for the hard papers, plus reference lists checked against Crossref-deposited lists; thresholds committed with the gold | the GROBID boot check fails when run under a JDK older than 21; the §7.1 test fails with an adapter's y-flip removed; a deliberately interleaved column extraction fails the reading-order metric; shuffled table cells fail the table metric |
| **P5 Colab bulk pass** | canary shard → projection → Kam's go (and GPU approval if proposed) → all shards → ingest | every active file has a current run with pages, blocks, chunks; coverage at or above the P4 threshold; disagreements logged | a shard with a corrupted artifact fails ingest verification |
| **P6 Citations** | references resolved, citation graph, citation candidates | reference resolution rate measured and reported | a **near-miss** reference — a real reference from the corpus with one field altered (year, a title word, or a DOI digit) — does not resolve to the real work |
| **P7 Retrieval** | embeddings, hybrid search, evaluation on the referee's paraphrased query set (§8) | vector leg and hybrid each at or above their pre-committed recall@k thresholds | with the vectors replaced by random vectors, **the vector leg alone**, on the paraphrased queries, falls below its threshold (the lexical legs would otherwise rescue a scrambled index) |
| **P8 Access** | MCP server and CLI; hunt protocol written into the convention | an agent in a scratch worktree runs a full mini-hunt: open workstream → admit → acquire → extract → record use with verified quote → promote prepare; commit is exercised against a scratch git repo whose `main` it merges itself (never the real one) | a use with an unverifiable quote is refused at prepare |
| **P9 Local + retire old paths** | local worker, parity test, hand-edited tracker retired | parity on a sample; old paths removed from the convention | a parity break introduced on purpose is caught |

**Order of value:** P1–P3 already fix today's pain (mergeable, versioned, concurrent records with
checks). P4–P7 add the knowledge layer. P8 makes it Claude's daily tool.

---

## 15. Decisions for Kam (P0)

1. **Server:** PostgreSQL 18 on port 5433 (proposed) or 17 on 5432.
2. **pgvector on Windows:** pgvector's README gives only a build from source with Visual Studio C++
   and `nmake /F Makefile.win` **[F]**; prebuilt third-party binaries are **[UNCONFIRMED]** — accept
   the Build Tools install.
3. **Embeddings stay local** (no text sent to a third-party embedding API) — proposed yes.
4. **Colab bulk pass on CPU runtimes first** (0 CU per `colab_rates.csv`), GPU only by separate
   approval after the canary — proposed yes.
5. **paper-search keys:** set free CORE and DOAJ keys and an Unpaywall email (your email, your call).
6. **Derived artifacts location:** `D:\edmonds-pipeline\Literture\_derived\` — proposed yes.
7. **Promotion authority:** `promote prepare` runs on the branch and its report reaches you inside
   the merge; `promote commit` runs only after you merge (§5). Who runs commit — the orchestrator,
   after seeing your merge, or you?
8. **Figure descriptions by Claude vision:** on demand only (proposed), or a bulk pass later.
9. **GROBID locally:** enable WSL2 (admin, one reboot) or install Docker Desktop, or keep stage 2 on
   Colab only.
10. **Colab terms, project-wide:** the FAQ wording against headless and distributed use is stated
    for the free tier; the account is Pro, whose terms on this are unread. The question covers the
    existing `vm_ops.py` headless practice and CPU fan-out, not only this pass: read the Pro terms,
    accept the current practice, or change it.
11. **Shadow-library PDFs on Drive:** upload the corpus to the Drive lake for the Colab pass, upload
    only the open-access subset (the rest extracted locally), or extract everything locally.
12. **A small database dump:** R12 tabled backup, but the database will hold use histories,
    approvals and promotions that no file regenerates. Is a periodic `pg_dump` (no PDFs, no derived
    artifacts) in scope?
13. **Manual-admission sign-off:** a second agent session (the database enforces admitter ≠
    approver), or you only?
14. **Who may approve admissions refused at binding** (scans with no first-page text layer, papers
    whose first page is a cover sheet): wait for OCR in P4, or a manual admission under item 13?
15. **Year tolerance:** the DOI-first rule requires the registry year to match exactly; allow ±1
    for online-first publications, or keep exact?

---

## 16. Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| GROBID's maintainers do not support Windows; JDK 21 or higher **[F]**; a Colab recipe is unproven **[UNCONFIRMED]** | stage 2 cannot run natively on Windows, and may not boot on Colab | P4 gate and kill test the Colab boot first; WSL2 or Docker locally (§15.9) |
| Layout or math models too slow on CPU | bulk pass takes days | canary measures first; GPU proposal gated by Kam |
| pgvector's README offers only a source build on Windows **[F]** | P1 needs a C++ toolchain | Build Tools install (§15.2) |
| Colab terms on headless and parallel use **[UNCONFIRMED for Pro]** | the project's existing practice, not only this pass, may conflict | Kam's call (§15.10) |
| MinerU needs at least 16 GB RAM **[F]**; Colab CPU runtime RAM on this account **[UNCONFIRMED]** | may not fit a CPU runtime | canary measures; laptop or GPU runtime |
| Scan OCR quality on 1950s–70s JSTOR papers | wrong text in theory papers | per-block confidence; disputed regions to vision; evidence quotes must verify |
| Scans and cover-sheet first pages cannot pass the binding gate | papers wait in quarantine | `binding-pending` state; §15.14 |
| Colab writer path to Drive | artifacts silently lost | existing verified path + independent server-side check (memory); packed shards with hashed done markers |
| Library licences **[F]**: PyMuPDF AGPL or commercial; Marker/Surya weights free only for research, personal use and startups under $5M; Nougat weights CC-BY-NC | constraints on use | pypdfium2 instead of PyMuPDF; Docling (MIT), GROBID (Apache-2.0), MinerU (custom licence based on Apache 2.0) preferred |
| Concurrency on one local server | Colab cannot write the DB | by design: Colab writes artifacts, ingest is local |
| Recorded agent/session identities are client-supplied | the admitter ≠ approver constraint can be defeated by a forged name | stops mistakes, not adversaries; §15.13 |
| The database holds history no file regenerates, and has no backup | a disk loss erases use histories and promotions | §15.12 |
| Disk | derived artifacts grow | page images only for scans and disputed pages; sizes reported per phase |

---

## 17. Tool facts (verified 2026-09-13)

The full report — every claim with the URL fetched and its own UNCONFIRMED list — is
**`Reports/LITKB_TOOL_FACTS_2026-09-13.md`**. It is the home for these facts; the rows below restate
only what shapes the design, at the strength the report gives them.

| Tool | Facts used in this design | Still unconfirmed |
|---|---|---|
| GROBID 0.9.1 (2026-08-04) | "OpenJDK 21 or higher"; maintainers "cannot ensure currently support for Windows", Docker the documented alternative; CRF image ~500 MB vs full image ~8 GB, full adds 2–4 F1 on reference parsing and 2–5 on citation context at 2–3× the time; 10.6 PDFs/s on one 16-CPU, 32 GB machine; `teiCoordinates` ("page,x,y,w,h", page 1-indexed, PDF units, origin upper-left) for ref, biblStruct, persName, figure, formula, head, s, p, note, title, affiliation; Apache-2.0 | whether Java 23 works; exact in-text citation target syntax; whether formula content is LaTeX; a Colab recipe (Docker not available on Colab, also unconfirmed) |
| Docling | MIT; Windows supported; formula enrichment (CodeFormula) emits LaTeX; 1.2–1.5 pages/s CPU-only and 3.1–7.9 GPU on vendor hosts; DoclingDocument with body and furniture trees, reading order by body child order, "bounding boxes for all items, if available" | version; VRAM needed; OCR engine list; provenance field names and box origin; table cell schema |
| MinerU 3.4 (2026-06-18) | `content_list.json` equation blocks with LaTeX, `bbox` normalised 0–1000, `page_idx` 0-based; "MinerU Open Source License, a custom license based on Apache 2.0" (was AGPLv3); pipeline backend CPU-capable or ≥4 GB VRAM; Windows; RAM minimum 16 GB | formula model name; fit on a Colab CPU runtime |
| Marker / Surya 2 | Apache-2.0 code; weights free for research, personal use and startups under $5M; served through vLLM (NVIDIA GPU) or llama.cpp (CPU) | VRAM; Surya per-equation box |
| Nougat | code MIT, weights CC-BY-NC; last commits 2025-02-21 and 2023-10-04 | scan hallucination from a primary source |
| pypdfium2 / PyMuPDF | pypdfium2 Apache-2.0/BSD-3, bounded text extraction (left, bottom, right, top), page rendering, Windows wheels; PyMuPDF 1.28.2 AGPL or commercial | pypdfium2 version and per-character box API; legal reading of AGPL (moot if pypdfium2 is used) |
| Embeddings | bge-m3: MIT, 1024-d, 8192 tokens, dense + sparse + multi-vector; nomic-embed-text-v1.5: Apache-2.0, 768-d (Matryoshka), 8192 tokens, 0.1B params; SPECTER2: Apache-2.0, 512 tokens, title + abstract per paper; pgvector index limits: 2,000-d `vector`, 4,000-d `halfvec` | bge-m3 params; SPECTER2 dimension; scientific-retrieval benchmarks per model; bge-large, e5-large-v2, gte |
| pgvector 0.8.6 (2026-07-29) | 0.8.1 "Added support for Postgres 18 rc1"; 0.8.2 improved the Windows install target and fixed EXPLAIN for PG18; Windows install by building with Visual Studio C++ and `nmake /F Makefile.win`; the README names no prebuilt Windows binary | third-party prebuilt binaries; exact PGROOT lines |
| PostgreSQL 18.6 (this machine) **[M]** | `pg_trgm.control` and `fuzzystrmatch.control` present in `share\extension` (file listing, 2026-09-13; the facts report left `pg_trgm` unconfirmed); `uuidv7` present in the catalog file | both confirmed by query in P1 |
| postgres-mcp (crystaldba) | MIT; `uvx postgres-mcp`; `--access-mode=restricted` runs read-only transactions and rejects COMMIT/ROLLBACK | version and date; status of the older reference server |
| Colab | FAQ: VMs have a maximum lifetime; idle timeout; usage limits fluctuate; the free tier disallows remote control, bypassing the notebook UI and distributed computing workers. Account plan Colab Pro (`Scripts/pipeline/colab_rates.csv`, screen-read 2026-09-01) | Pro terms on headless use; runtime vCPU/RAM (free tier ~2 vCPU / ~13 GB from secondary sources only); disk; apt and Java installs; tool speeds on Colab |

---

## 18. Change log

**Revision 2 (2026-09-13)** — answers the independent referee's review of revision 1.

- **The referee's report file was empty.** The task output file named as the report was 0 bytes when
  this revision was written. The response works from the orchestrator's summary of each defect
  (H1–H10, M1–M9, L1–L3). Each summarised claim was checked against revision 1 and against disk
  before it was acted on; the evidence is cited where the fix lands.
- **M2 had no stated reason in the summary.** The reading applied is the dependency inside revision 1
  itself: P2 "Migration" had a kill ("a planted wrong DOI (the Averkov case) rejected at load") that
  needs the admission check, but admission was built in P3. Admission now comes first (P2), migration
  second (P3). If the referee meant a different ordering problem, it is not addressed here.
- **L2, "add a P4 kill that GROBID boots on Colab":** applied with a change of form. A boot that
  succeeds is a pass condition, so it is a P4 **gate**; the matching **kill** is that the same check
  fails under a JDK older than 21, so the gate is shown to be able to fail.
- **Found while verifying, not raised in the summary:** revision 1 §4.6 said the convention allows
  a ±1 year for online-first; the convention's DOI-first rule says the year must match. Corrected,
  and the tolerance question added as §15.15.
- **Numbers corrected against disk:** aa_fetch tests 77 → 80 `def test_`; corpus 771 MB → 756.5 MB
  active (219 PDFs) / 807.7 MB (770.3 MiB) with quarantine (236 PDFs). Confirmed unchanged: 219 PDFs,
  4,655 pages, 688-page book, 207 manifest rows, 460 tracker rows, 139 GB free.
- **[F] marks re-graded** to the strength of the facts report: GROBID "Linux only" → maintainers do
  not support Windows; "pgvector has no Windows binary" → the README names none; "MinerU does not fit
  a free CPU runtime" → 16 GB minimum is [F], the fit is unconfirmed; embeddings and Postgres on
  Windows lost their [F] (not in the report; Postgres is [M]); pgvector "PG18 supported since 0.8.1"
  → "0.8.1 added support for Postgres 18 rc1"; Nougat "unmaintained" marked as inference; `pg_trgm`
  presence re-marked [M] (local file listing) since the report left it unconfirmed.
- **No referee claim was rejected.**

---

## 19. Referee response

| ID | Defect (summary) | Response | Where |
|---|---|---|---|
| H1 | File-to-work binding was a later audit, not an admission gate | **Fixed.** Binding (registry title ≥ 0.85 in header or first-page text, plus first author) is admission check 3; P2 kill replays the real pre-fix Averkov 2009 and Higham 2011 rows and files, with their measured Crossref ratios (0.36, 0.25) | §4.6, §4.2 `files.binding`, §14 P2; binding-pending policy §15.14 |
| H2 | Main's view was "highest promoted version" | **Fixed.** `current_version_id` pointer on each identity row; main's view is the pointer | §4.1 |
| H3 | Writes did not compare against their base; facts bypassed it | **Fixed.** Every write, facts included, is compare-and-set in a database function; P1 kill for a fact table and a proposal | §4.1, §14 P1 |
| H4 | Admission not atomic; no identifier uniqueness on normal form; no-identifier dedupe | **Fixed.** One transaction; partial unique index on `value_norm`; trigram title + year check with a threshold calibrated on real `Duplicate of` pairs | §4.6 checks 2, §4.2, §14 P2 |
| H5 | Manual admissions entered as facts on the admitter's word | **Fixed**, authority **deferred to Kam.** Manual admissions start `proposed`; admitter ≠ approver enforced; limit stated (client-supplied identities) | §4.6 check 4, §4.3 `admissions`, §15.13 |
| H6 | Evidence not tied to an extraction run; `quote_verified` client-writable | **Fixed.** `files.current_run_id`; evidence stores quote, page, run, offsets; trigger computes `quote_verified`, no column privilege for writers | §4.4, §4.5, §4.7 |
| H7 | Promotion wrote to main's knowledge before Kam's merge | **Fixed**, who runs commit **deferred to Kam.** `prepare` on the branch (report committed there); `commit` only when the merge commit is reachable from `main` and the version set is unchanged | §5, §14 P1/P8, §15.7 |
| H8 | Promotion could split dependent versions; `parent_workstream` undefined | **Fixed.** Chains with dependencies, all or nothing, dependents held back with a failing chain; `parent_workstream` dropped | §5, §4.3, §14 P1 |
| H9 | P7 kill (random vectors) rescued by the lexical legs; verbatim queries | **Fixed.** Kill on the vector leg alone, with referee-paraphrased queries | §8, §14 P7 |
| H10 | P4 gold and thresholds not independent or frozen | **Fixed.** Referee authors gold and thresholds, committed before tools run | §14 preamble and P4 |
| M1 | Boxes from different tools in different frames | **Fixed.** Canonical frame, per-tool adapters, a containment test and its kill | §7.1, §14 P4 |
| M2 | Phase order | **Fixed** (reading stated in §18): admission (P2) now precedes migration (P3) | §14, §13 |
| M3 | P6 kill used a fabricated reference (trivially unresolvable) | **Fixed.** Near-miss reference with one altered field | §14 P6 |
| M4 | Colab section assumed the free tier | **Fixed**, terms **deferred to Kam.** Account is Pro (`colab_rates.csv`); terms restated as a project-wide question | §11, §15.4, §15.10, §16, §17 |
| M5 | Shadow-library PDFs to Drive undecided; per-file artifact writes | **Fixed** (packed shard archives), Drive upload **deferred to Kam** | §11, §15.11 |
| M6 | `.txt` durable copy and no-delete rules missing; database has no dump | **Fixed** (rules restated), dump scope **deferred to Kam** | §6, §15.12 |
| M7 | Convention update too late; tracker IDs lost; stem in two homes | **Fixed.** Convention rewritten in P3; `tracker` and `legacy_stem` identifier schemes; `works.key` sole home of the stem, `files.stem` dropped | §3, §4.2, §10, §13, §14 P3 |
| M8 | Test guard only client-side; ladder breaks without Postgres | **Fixed.** `litkb_test` role can only CONNECT to `litkb_test`; `requires_litkb_pg` skip marker with printed count | §4.7, §9, §14 P1 |
| M9 | Heavy dependencies would enter the engine environment | **Fixed.** Separate `requirements-litkb*.txt`; lazy imports with a test | §9 |
| L1 | Tool facts report not in the repo | **Fixed.** Copied to `Reports/LITKB_TOOL_FACTS_2026-09-13.md`; §17 links it as the home | §17 |
| L2 | Over-claimed [F] marks; no Colab boot test for GROBID | **Fixed** (boot as a P4 gate with a JDK kill; form change explained in §18) | §7, §11, §12, §15.2, §16, §17, §14 P4 |
| L3 | Numbers not checked against disk; unversioned tables not listed | **Fixed.** 80 tests; 756.5 MB active / 807.7 MB with quarantine; others confirmed [M]; unversioned tables listed | §4.1, §6, §10, §11, §13 |

**Totals:** 22 fixed (5 of them with a remaining decision for Kam: H5, H7, M4, M5, M6), 0 rejected.
