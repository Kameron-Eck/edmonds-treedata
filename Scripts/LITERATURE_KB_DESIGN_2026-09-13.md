# Literature knowledge base — design, architecture and plan

**Status:** DRAFT revision 3, 2026-09-13 (revision 1 was refereed; the response is §19; revision 3
applies Kam's decision that all literature work runs locally, §18). **Built so far:** P1 Foundation
(migrations 0001–0012, three referee rounds; `Reports/LITKB_P1_REPORT_2026-09-13.md`), the nightly
`pg_dump` and the staged-secrets ladder rung (`Reports/LITKB_OPS_2026-09-13.md`). Everything else is
unbuilt, and every design claim beyond P1 is UNVALIDATED until the phase that tests it has run on real
data with its kill shown to fire (CLAUDE.md 3.4c).

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
| R11 | ~~Bulk pass on Colab now; local runs later~~ **Superseded the same day:** all processing runs locally on this laptop, CPU first, optimised as needed; no Colab pass (decisions.yaml `litkb-p0-foundation`, "After P1 acceptance") | earlier: "we can use colab. I want this to run locally in the future"; now: "I think we should be doing all of this work locally. I think there will be a back log that will take some time to work through on this CPU, but I think we can make it work with some optimization." |
| R12 | No backup for now (disk) — a nightly dump of the database records was later approved and built (§6) | "We can table a back up for now" |
| R13 | Every use of literature by the project goes through this knowledge base | "Anytime literature is called upon to aid this project, it must flow through this workstream." |

**Non-goals:** storing PDF bytes in Postgres; a backup system for PDFs or derived artifacts (R12; the
database records alone are dumped nightly, §6); a public or multi-user service; replacing the research
reports (briefs and findings stay as reviewed documents in git); any cloud compute or upload of the
corpus (R11).

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
   │ local worker pool §12  │  │ aa_fetch (Anna's Archive), Sci-Hub │     │ promotion reports     │
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
4. **Everything runs on this machine.** The database, the PDFs, the extraction workers and the ingest
   all live on the laptop; no PDF leaves it and no cloud runtime is used (R11, revision 3). Extraction
   is a resumable, database-backed job queue worked by a local process pool, sized and scheduled so
   the backlog drains over nights without losing more than one unit of work to a crash (§12).

---

## 3. Identifiers (R4)

- **Every row ID is a UUIDv7** — time-ordered, generated by the database or by a client offline
  (an extraction worker writing artifacts before ingest). `select uuidv7()` answered on the P1 server
  (`Reports/LITKB_P1_REPORT_2026-09-13.md`, gate table).
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
| `extraction_runs` | file_id; stage; tool; tool_version; params hash; pipeline_version; host; status (ok, failed); artifact_path; metrics (JSON: seconds, pages/s, peak RSS, coverage). **Built** (`0001_core.sql`): UNIQUE on (file, stage, tool, tool_version, params_hash, pipeline_version); the `host` check still admits `'colab'` as well as `'local'` — harmless, unused after revision 3, and applied migrations are checksum-locked, so narrowing it would be a new migration, not an edit |
| `extraction_jobs` | **Not built (P4/P5 migration).** The queue of §12: file_id; stage; page_start, page_end (null = whole file); tool; tool_version; params_hash; pipeline_version; state (queued, leased, done, dead); attempts; lease_owner (worker id); lease_expires_at; last_error; artifact_path; artifact_sha256; run_id → extraction_runs; enqueued_at; finished_at. UNIQUE on the run key plus page range. No `workstream_id`: it hangs below `files`, a main-owned identity table, so it sits outside the workstream guard by the rule in §4.7. Written only through SECURITY DEFINER functions (`enqueue_extraction`, `claim_jobs`, `renew_lease`, `finish_job`, `fail_job`) that only `litkb_ingest` may EXECUTE, added to the role-privilege matrix test |

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
  The convention requires the year to *match*; revision 1 wrongly said ±1 for online-first. **Kam
  decided (§15.15):** ±1 year is allowed only when the title and first author both match the registry
  record; otherwise the year must match exactly. P2 implements it;
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
ratio and page go into `files.binding`. Search every first-page line, not the first line: the Averkov
2009 file's extract begins with the journal running header, a copyright line and the author names,
and its title is the fourth line (`audit_fast.csv` column `extract_head`, 2026-09-13 **[M]**). A file with no text layer on its
first page cannot pass and is quarantined as `binding-pending` until OCR (P4 onward) binds it; Kam
decided there is no manual admission for these files (§15.14). Rationale: in revision 1 binding was a later audit, and the manifest shows what
that costs — two files sat under wrong DOIs with `verified_against_extract = yes` until an audit
caught them.

**Check 4 — manual admissions are proposals.** A work with no confirmable identifier (older
proceedings, reports) is admitted with `verified_by = manual` and its `admissions.state = proposed`:
evidence rows name the source and a held file whose text contains the title. It becomes visible as
a fact only when approved in a session different from the admitter's (a check constraint on
`admissions` compares session identifiers only: agent names are client-supplied labels, so the same
agent name in another session may approve, and another name in the same session may not —
decisions.yaml `litkb-p0-foundation`, D-4); until then it appears only in its workstream's view and
is flagged in exports. Limits: session names are recorded by the client, so the constraint stops an
honest mistake, not a forged identity (§15.13).

**Check 5 — every reference points at something real.** Enforced by the database: foreign keys,
the unique normalised identifiers, unique sha256, enum checks on every status column, a regex check
on `works.key`, `change_reason` and `based_on_version_id` required for version ≥ 2, `version_no`
unique per entity. No agent role holds INSERT, UPDATE or DELETE on a version table: versions are
written only by the write, rebase and admission functions, and only the write and promotion
functions move pointers or change `state`.

### 4.7 Roles

| Role | Can | Used by |
|---|---|---|
| `litkb_reader` | SELECT | the MCP query tools; exports |
| `litkb_writer` | SELECT; EXECUTE the write functions — `write_proposal`, `write_fact`, `add_evidence`, `add_candidate`, `record_acquisition_attempt`, `add_use_embedding`, `abandon_workstream` — each of which takes the named workstream's token (§5), and `open_workstream`. **No** direct INSERT, UPDATE or DELETE on any table whose rows belong to a workstream (version tables, candidates, admissions, attempts, evidence, use embeddings; a catalog test fails if any agent role gains one); no INSERT on extraction tables and no EXECUTE on `set_current_run` (tested) | agents, acquisition |
| `litkb_ingest` | INSERT on the extraction tables (`extraction_runs`, `file_checks`, `pages`, `blocks`, `tables`, `figures`, `equations`, `references`, `citation_mentions`, `chunks`, `embeddings`); EXECUTE `set_current_run()`; SELECT. No gaps, uses, evidence or workstreams (tested). From P4/P5 also EXECUTE on the `extraction_jobs` functions (§4.3), and nothing else new | the ingest tool and the local extraction workers (§7, §12) |
| `litkb_promoter` | EXECUTE `promote_prepare()`, `promote_commit()`, `promote_abandon()`, `promote_rebase()`; reader and writer hold none of these (tested) | the promote tool only (§5, §15.7) |
| `litkb_test` | CONNECT on `litkb_test`; the server refuses it on `litkb` (CONNECT revoked from PUBLIC there). It can also open Postgres's empty system databases, which grant CONNECT to PUBLIC; the property that counts is that `litkb` refuses it | the test suite (§9) |
| `litkb_owner` | DDL, migrations; owns the SECURITY DEFINER functions | the migration runner (`migrate.runner_connect`, through `connect.connect_admin()`, which opens only `postgres` and `litkb_owner` and which the shared `connect()` refuses, F-9) and the nightly `pg_dump` (`litkb.ops.nightly_dump`; its weekly restore check creates and drops its scratch database as the superuser, because the owner has NOCREATEDB; `Reports/LITKB_OPS_2026-09-13.md` §1) |

Credentials are never in the repo. The owner, reader, writer and test logins are lines in the
libpq pgpass file `%APPDATA%\postgresql\pgpass.conf`, written by `litkb.db.provision` (this section
used to say `D:\edmonds-pipeline\secrets\`; P1 never put them there). The promoter's line lives in
a passfile of its own, `D:\edmonds-pipeline\secrets\litkb_promoter.pgpass`
(`litkb.db.connect.promoter_passfile()`), which only `litkb.promote.connect()` names; the shared
`litkb.db.connect.connect()` refuses the promoter login, so an agent's reader or writer connection
never carries it (decisions.yaml `litkb-p0-foundation`, D-3). The server cannot tell the promote
tool from any other process that reads that file: the credential is protected by where it is kept.

The ingest login follows the same pattern (decisions.yaml `litkb-p0-foundation`, after the second P1
referee): its line lives in its own passfile, `D:\edmonds-pipeline\secrets\litkb_ingest.pgpass`
(`litkb.db.connect.ingest_passfile()`), which only `litkb.ingest.connect()` names, and the shared
`connect()` refuses that login too. The writer lost INSERT on the extraction tables and EXECUTE on
`set_current_run()` because with them it could install an `ok` run and make it current (which
un-promotes that file's evidence), or insert a block whose text matches any quote. The secrets
folder's inherited ACL is left as it is: an accepted risk on a one-user laptop (same decision).

A **workstream token** is not a login. `open_workstream()` returns it once; the database stores only
its sha256, in `workstream_tokens`, which no agent role can read. It stops a session writing into
another session's workstream by mistake; it does not stop a process that reads another worktree's
token file. The token is only a lock if nothing goes round it, so no agent role holds a direct write
on a guarded relation (migration 0011; the rule was widened after the third P1 referee, F-1).
`qc/test_litkb_p1.py` (`_GUARDED_RELATIONS`, `_direct_write_offenders`) builds both the relation
list and the role list from the catalog; that code is the rule's one home. In outline, it covers
every relation of every kind that is `workstreams`, has a `workstream_id` column or a foreign key to
`workstreams`, or is a view, plus everything below those through foreign keys at any depth. It does
not descend through the main-owned identity tables. The roles are every role an agent login can use
or `SET ROLE` to, plus PUBLIC and every ACL grantee. Token hashes are not readable through any
relation, and each role's table, column and function privileges match the table above
(`test_role_privilege_matrix`). `abandon_workstream` refuses while a promotion is prepared, and
`add_use_embedding` takes only a proposed version in an open workstream (migration 0012).
Clients send the token only as a bound query parameter, never inlined in the SQL text, because
another login of the same role can read `pg_stat_activity.query`. Admission rows have no writer
path until P2's token-checked `admit`.

---

## 5. Workstreams and promotion (R3)

`main` belongs to Kam. Nothing in this section merges, pushes or commits to `main`; promotion reads
git to confirm that Kam has merged.

1. **Open.** `litkb ws open --slug <slug> --branch <git branch> --purpose "…" [--brief <path>]`
   writes the workstream and a git-ignored `.litkb-workstream` file in the worktree root
   (`litkb.workstream.open_workstream`). `open_workstream()` returns a secret **token** once; the
   file holds the ID and the token, and the database keeps only the token's sha256. Every writer
   function that names a workstream (`write_fact`, `write_proposal`, `add_evidence`,
   `abandon_workstream`) takes the token and refuses (42501, inside the SECURITY DEFINER function)
   one that does not hash to that workstream's, so a session cannot write into another session's
   workstream by mistake. The same holds for `add_candidate`, `record_acquisition_attempt` and
   `add_use_embedding`. The promotion functions take no token: the promoter acts on every
   workstream. There is no way round the token: the writer holds no direct INSERT on any table whose
   rows belong to a workstream (§4.7).
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
   - **the promote tool** refuses unless `git merge-base --is-ancestor <sha> main` succeeds against a
     freshly fetched `main`, and the prepared commit is an ancestor of `<sha>`. The database cannot
     run git, so this check lives in the tool, and the tool holds the only promoter credential (§4.7);
   - the database refuses if the version set no longer hashes to what was prepared (something changed
     after the report Kam saw);
   - in one transaction, for each chain **all or nothing**: compare-and-set main's pointers from
     each chain's base to its head. If any pointer in a chain has moved, that chain stays `prepared`
     with a conflict note, and every chain that depends on it stays too;
   - marks the workstream `merged` with the merge commit.
   - **Rebase what the commit held back** (decisions.yaml `litkb-p0-foundation`, D-2). A held chain is
     never left stuck: `promote_rebase()` (promoter or owner only) copies each chain the merged
     workstream still holds into a fresh open workstream, one new version per chain carrying the
     head's content, based on main's current version as the promoter names it. A name main has since
     left is refused (compare-and-set), so the rebase is reviewed against the main it lands on. The
     new version records `rebased_from_version_id`; the old versions are kept and marked `rebased`;
     **only the head version's evidence rows are copied**, exactly what promotion would carry (main's
     current version carries only its own rows; a row on an earlier chain version never reaches
     main), every copied column equal to its source and `quote_verified` recomputed by the trigger
     (decisions.yaml `litkb-p0-foundation`, E-5); `rebases` records source and target workstreams, the
     promotion that held the chain, and the versions. The fresh workstream then goes through
     prepare, Kam's merge and commit like any other.
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
  scan detection; plus registry metadata on the work and a header parse from stage 2 (GROBID under
  §15.9 path A; under path B whatever header output the chosen route gives, or none, leaving two
  sources) — all kept so disagreements (a wrong DOI, a missing year) are visible.
- **Disk [M]:** D: had 139 GB free on 2026-09-13 (`df -h /d`). PDFs under `Literture\`: 219 active
  files in `ASPP`, `Labeling`, `Validation`, `other` = 756.5 MB (721.5 MiB); with the 17 in
  `_quarantine\`, 236 files = 807.7 MB (770.3 MiB) (`find -printf %s`, summed). Revision 1's
  "771 MB" was the quarantine-inclusive MiB figure presented as the active corpus. Page images are
  the only large derived item; they are rendered for scans and disputed pages only. Figure crops are
  small.
- **Backup of PDFs and derived artifacts:** tabled (R12). `files.sha256` lets any future copy be
  verified. **All of it stays on this laptop:** no PDF goes to Drive (§15.11 answered).
- **Database dump — built** (§15.12 decided; `Reports/LITKB_OPS_2026-09-13.md` §1 is the home for
  the detail). `litkb.ops.nightly_dump` runs `pg_dump -Fc` of `litkb` as `litkb_owner` into
  `D:\edmonds-pipeline\pgdump\litkb\`, writes `.partial`, verifies it (`pg_restore --list`, then a
  full read), records its sha256 in `manifest.json`, keeps the newest 14, and weekly restores into a
  scratch database and compares exact row counts per table. Scheduled task `litkb-nightly-dump`,
  02:30 daily, "run only when logged on" (S4U registration was refused without elevation). **Its
  working directory is this worktree:** after the merge the task is re-registered from the merged
  tree (`--install-task --logon Interactive`). Records only: no PDFs, no derived artifacts.

---

## 7. Extraction pipeline (R10)

Each stage is an idempotent step keyed by (sha256, stage, tool version, params). Stages run in the
local worker pool (§12), write raw artifacts first, then an ingest loads them. Loading is owned by the `litkb_ingest` login (§4.7): it
inserts the extraction runs and derived text tables and, for the reconciliation stage only (§12.4),
moves the file's `current_run_id` with `set_current_run()`; agents' writer connections can do neither.

| Stage | What | Candidate tool(s) | Output |
|---|---|---|---|
| 0 Inventory | hash, page count, text-layer probe per page, PDF metadata, scan routing | **pypdfium2** (Apache-2.0/BSD-3 **[F]**; PyMuPDF is AGPL or commercial **[F]**) | `files`, `pages` |
| 1 Native layer | words with positions, font sizes and weights, links | same (per-character box API name **[UNCONFIRMED]**) | raw JSON |
| 2 Scholarly structure | header metadata, section tree, paragraphs, footnotes, figure and table captions with coordinates, parsed references, in-text citations linked to references | **Two paths, Kam's choice (§15.9).** **Path A — GROBID 0.9.1**, CRF image (the deep-learning image adds 2–4 F1 on reference parsing at 2–3× the time; GPU through a container on Windows is not supported **[F]**, so the CPU-only CRF image is the one that fits). JDK 21 or higher **[F]**; its maintainers "cannot ensure currently support for Windows", Docker is the documented alternative **[F]**. On this laptop that means WSL2 or Docker, neither of which is set up **[M]**. The firmware flag reads disabled but a hypervisor is running **[M]**, so a BIOS change is probably unneeded (inferred, §12.1). **Path B — no GROBID.** Docling's stated features cover layout, reading order, tables and formulas **[F]**, not reference parsing or citation linking. References would come from a reference-string parser not yet in the tool facts report — a candidate is named and fact-checked into that report before P4 **[UNCONFIRMED]** — and in-text citation → reference links from project code. Path B loses GROBID's header parse and its citation-context linking unless those are rebuilt | A: TEI XML with `teiCoordinates`; B: parser JSON plus Docling items |
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
| GROBID (path A only) | `"page,x,y,w,h"`, page 1-indexed, PDF units, origin upper-left **of the CROPBOX** **[M]** | x1 = x + w, y1 = y + h, then shift into the mediabox frame: x += crop.x0 − media.x0, y += media.y1 − crop.y1 |
| Path B reference parser | not known until it is chosen **[UNCONFIRMED]**; it may emit no boxes, in which case references are anchored through the Docling block they were read from | written in P4 |
| MinerU | `bbox` normalised 0–1000, `page_idx` 0-based **[F]** | scale by page width/height ÷ 1000; page + 1 |
| pypdfium2 | bounded text takes (left, bottom, right, top) **[F]**, implying a bottom-left origin (our inference **[UNCONFIRMED]**) | y flipped against page height; rotation applied |
| Docling | `bbox` with an explicit `coord_origin` per box: `"BOTTOMLEFT"` on items, `"TOPLEFT"` on table cells **in the same JSON file** **[M]**; the page box it reports is the CROPBOX, as GROBID's is **[M]** | branch on `coord_origin` (never on the container), flip BOTTOMLEFT against the page height, then the same mediabox shift as GROBID — `litkb.extract.docling.to_mediabox()` |

**The canonical frame is the MEDIABOX** (added 2026-09-15, measured). "Origin at the top-left of the
page" is ambiguous whenever a PDF's cropbox differs from its mediabox, and **223 pages of the
216-PDF corpus** do. GROBID measures from the CROPBOX: its `<facsimile><surface>` carries the
cropbox's size, and its coords are relative to the cropbox's upper-left corner. Measured on
`Alwan_1988` p2/p3 (mediabox `(0,0,612,792)`, cropbox `(10.345,10.777,603.441,782.948)`): a whole
`<ref>` element's box agrees with pypdfium2 to **0.39–0.91 pt** after the shift and is off by
**10.5–10.9 pt** without it. `litkb.extract.grobid.page_frames()` reads the two boxes from the PDF
and `to_mediabox()` applies the shift; every `Block` states its `frame`. Rotation *is* applied by
GROBID (`/Rotate 90` yields a landscape `<surface>`) — `to_mediabox()` refuses those 7 corpus pages
rather than convert them silently.

**Rotation: the refusal is necessary, not cautious [M] (2026-09-15).** Rotation only costs anything
on a page that ALSO has cropbox ≠ mediabox, and that intersection is **exactly one page in 4,712**
(referee's corpus: 224 PDFs under `Literture\` excluding `_quarantine`, 7 rotated pages and 271
cropped — quote those counts only with that corpus definition; they differ from the 216/223 set
above). The page is `Hall_1985_resampling-coverage-pattern.pdf` p12, rotation 180. Measured there:
GROBID's 551 body blocks match pypdfium2 to **2.04 pt** read in the rot-180 *displayed* frame, vs
10.99 pt read unrotated — so GROBID does report the displayed frame. **And the correct map for 180°
is a reflection, not the translation `to_mediabox` applies**: `x_m = crop.x1 − X`,
`y_m = media.y1 − crop.y0 − Y`. The two agree nowhere on that page — a block at displayed `x = 49.8`
belongs at `x_m = 413.2` and the translation would place it at `51.8`, a **361.4 pt** error (roughly
the page width); in y, **557.6 pt**. For 90°/270° the axes swap as well. Implementing the
per-rotation maps is **future work**; refusing is the only correct behaviour available, and it is
pinned by `test_to_mediabox_refuses_a_rotated_page_with_a_cropbox`.

**`teiCoordinates` is a REPEATED form field [M].** One field per element name. Comma-joining the
list is accepted with HTTP 200 and yields almost no coordinates (8 boxes, all on `graphic`, vs
3,760 for the same paper sent correctly) — a silent degradation, not an error.

**Zero-block rule [M]: HTTP 200 is not success.** A PDF with a text layer on *some* pages — a JSTOR
scan whose cover page carries the access boilerplate — returns 200 with a parsed header and an
EMPTY `<text><body>` (`Anderson_1957`: 3,659 B, 4 blocks, all of them header boilerplate). A file
with *no* text layer anywhere is refused by GROBID itself with a 500 `[NO_BLOCKS]`; the partial case
is the dangerous one. A TEI with **fewer than `MIN_BODY_BLOCKS` = 4** coordinate-bearing blocks
inside `<text><body>` is REFUSED (`NoTextBlocks`), is never recorded as a successful extraction, and
its `extraction_runs` row is `failed`. **The threshold is 4, not 1 [M] (2026-09-15):** injecting one
junk `<p>` box into the Anderson scan's empty body flipped it from refused to admitted with nothing
flagging it (referee 2, D3). With `segmentSentences=1` one real three-sentence paragraph already
yields four boxes (`<p>` + 3 `<s>`), while a scan page's furniture — page number, running head,
footer — is at most three; 4 is the lowest value that separates them by mechanism and is below the 8
body blocks of the smallest real-paper fixture. **Provisional** pending a per-PDF body-block census.

**Docling measures from the cropbox too [M] (2026-09-15).** Independently of the GROBID finding:
on `Alwan_1988` the same block agrees with the pypdfium2 character-box union to **3.45 pt** after
the shift and is **11.02 pt** out without it, and the shift that fixes it is `dx = crop.x0 − media.x0`
= 10.345 — the cropbox origin, not a tolerance
(`Reports/LITKB_DOCLING_LOCAL_REFEREE_2026-09-15.md` §4, "The canonical frame — referee's own pypdfium2 census"). Docling also mixes origins
*within one file*: items carry `coord_origin = "BOTTOMLEFT"` while table cells in the same JSON carry
`"TOPLEFT"` (`Reports/LITKB_DOCLING_LOCAL_2026-09-15.md` §2). The adapter reads the field per box;
a mutation that ignores `coord_origin` and treats everything as TOPLEFT fails 3 tests (M2,
`Reports/LITKB_DOCLING_LOCAL_REFEREE_2026-09-15.md` §5, "Kills — five source mutations").

**CLOSED 2026-09-15**, before stage 5 was written, as this section required
(`Reports/LITKB_STAGE5_INGEST_2026-09-15.md` §1). The three copies are one body —
`litkb.extract.inventory.page_frames(pdf_path, error=…)` — and the GROBID and Docling functions
call it, differing only in the exception class they raise on a page with no mediabox. The referee
numbers are unchanged (Alwan p2 `dx` 10.3449, `dy` 9.052; Hall p12 still refused by both adapters)
and the three now return equal dicts. The inherited-`/MediaBox` case is **real corpus data, not a
fixture**: sweeping the raw pdfium getter over the 224 PDFs under `Literture\` finds **16 such
pages in two files** — all 10 of `Platanios_2014` and 6 of `Vincent_1993` — every one of which
Docling's copy would have died on. The record of the defect follows, as written.

**Three modules now read the frame, and that is one home too many [M] (2026-09-15, now RESOLVED).**
`litkb.extract.inventory.page_frames`, `litkb.extract.grobid.page_frames` and
`litkb.extract.docling.page_frames` all return `{page: {mediabox, cropbox, rotation, dx, dy}}` with
the same `dx`/`dy` arithmetic. They are **not** interchangeable: inventory's and GROBID's resolve a
page that INHERITS its `/MediaBox` from the page tree (the raw pdfium getter returns 0 there, and
they fall back to pypdfium2's high-level accessor), and GROBID's raises rather than return a `None`
mediabox; Docling's copy has neither guard and would raise a `TypeError` on such a page.
Inventory's docstring already claims the role ("This is the ONE frame reader … grobid should import
this one rather than keep a second copy"). **Not collapsed at the P4 merge**: each copy is the one
the branch's referee measured against, and refactoring all three with no referee would retire
refereed numbers on an unrefereed change (3.4c). It is carried as an open item in
`Reports/LITKB_P4_MERGE_2026-09-15.md`, to be closed before stage 5 reconciliation is written —
stage 5 is where a disagreement between the copies would actually produce wrong boxes.

**Test (P4, before reconciliation is written):** on one born-digital page, take a word whose box
pypdfium2 reports, and require every adapter's box for the region containing that word to contain
it. A tool whose adapter fails the test contributes no boxes. The test must also fail when one
adapter's page offset or y-flip is deliberately removed.

**Reconciliation rules (stage 5), initial, to be tuned in P4 on measured accuracy:**
- born-digital text: the native layer's characters win; the layout model supplies order and type;
- reading order and table structure: the layout model wins;
- sections, footnotes, captions, references, citation links: GROBID wins (path A); under path B the
  layout model wins for sections, footnotes and captions, the chosen parser for references, and
  project code links citations;
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
  extract, ingest, audit, search, promote prepare/commit, export; and, for the local worker pool (§12),
  queue status, worker start/pause. Built so far: the library calls `litkb.workstream.open_workstream`,
  `litkb.promote`, `litkb.ingest.connect`, the `litkb.db.migrate` / `litkb.db.provision` modules and
  `litkb.ops.nightly_dump`; no `litkb` CLI entry point exists yet (P1 report).
- **MCP server** (`litkb.mcp`), read-only by default:
  - query: `search`, `get_work`, `get_file_blocks`, `get_use_history`, `list_gaps`, `citations_of`,
    `cited_by`, `missing_citations(gap)`;
  - write (writer role, workstream and its token required, §5): `open_workstream`, `add_candidate`, `admit`,
    `request_acquisition`, `record_use_version`, `verify_quote`. Each wraps a token-checked database
    function; the writer role has no direct INSERT on any table a workstream owns (§4.7), so a tool
    cannot write round the token;
  - `approve`, `promote prepare` and `promote commit` are not exposed to agents, and neither is
    `ingest`: the MCP server never holds the promoter or ingest credential (§4.7).
- **Credentials:** owner, reader, writer and test logins in the shared pgpass file; the promoter and
  ingest logins each in their own passfile under `D:\edmonds-pipeline\secrets\`, opened only by
  `litkb.promote.connect()` and `litkb.ingest.connect()`; the shared `litkb.db.connect.connect()`
  refuses both (§4.7). A session's workstream token lives in its worktree's git-ignored
  `.litkb-workstream` file (§5).
- **Ad-hoc SQL for Claude:** the crystaldba `postgres-mcp` server in `--access-mode=restricted`
  (read-only transactions, rejects COMMIT/ROLLBACK **[F]**) connected as `litkb_reader`, beside the
  domain tools above — two locks, since a parser guard alone is defence in depth.
- **Tests:** a throwaway database `litkb_test`, connected through the `litkb_test` role. The server
  refuses that role on `litkb` — so a test that is pointed at `litkb` fails in the server, not only
  in a client-side conftest guard (the lake-guard lesson in `qc/conftest.py`). The test login can
  also open Postgres's empty system databases (`postgres`, `template1`, `postgis_36_sample` grant
  CONNECT to PUBLIC); the property that counts is that `litkb` refuses it, and a test asserts exactly
  that (decisions.yaml `litkb-p0-foundation`, D-9). Tests
  that need the server carry a `requires_litkb_pg` marker and skip when the server or role is absent,
  so the ladder still runs on a machine without Postgres; the skip count is printed, never silent.

### 9.1 Access layer: how literature flows through the knowledge base (R13)

Kam's rule is that any literature the project calls on flows through this workstream. A rule by itself
does not make that happen. An agent that has read the rule still reaches for a web search or the
paper-search tool out of habit, and the database never hears of the paper. So R13 is carried by five
pieces, each with one job. Each piece lands only once the thing it points at exists: a rule or a hook
that names a tool not yet built blocks work and offers no path.

| Piece | Job | Home | Phase |
|---|---|---|---|
| **CLAUDE.md rule** | Policy only, stated as a pointer: literature used by the project is found, admitted, read and cited through litkb, and the procedure is the litkb skill. It adds one roadmap row to CLAUDE.md §2.1. It restates no procedure, because CLAUDE.md is "a ROADMAP and a RULEBOOK … deliberately NOT a facts store" and each fact has one home (§3.3) | `Scripts/CLAUDE.md` | **Interim form at P3**, because P3 makes the tracker and manifest exports, and from then on hand-editing them is wrong. The interim rule says: never hand-edit them, admit through the litkb CLI. It is cheap and needed at that moment. **Final form at P8**, naming the skill and the MCP tools |
| **Skill** | The procedure. Search the KB first (`search`, `get_use_history`), open a workstream, then discover → admit → acquire → extract → record a use with a verified quote → promote prepare. It says which tool serves each step and what is never done (cite a work that is not admitted, fetch a PDF outside a workstream). It points at the hunt protocol in `LITERATURE_CONVENTION.md` and does not copy it | a project skill folder; the exact location is settled in P8 (no `.claude/` directory exists in the repository today: `ls -a`, 2026-09-13 **[M]**) | P8 |
| **litkb MCP tools** | The agents' only path to query and write (§9 above); they wrap the token-checked database functions | `litkb.mcp` | P8 |
| **Hooks** | Guardrails, not enforcement: the database checks (§4.6, §4.7) remain the enforcement. A pre-tool hook on the routes that reach literature outside litkb (the paper-search tools, the Anna's Archive tools, Sci-Hub fetches) flags or refuses a call made in a worktree with no `.litkb-workstream`, and points at the skill. The exact tool matchers are read from the installed tool names in P8 **[UNCONFIRMED]** | project settings file, location settled in P8 | **After P8's gate passes.** Before the MCP tools exist, a blocking hook would leave agents no route to literature at all |
| **Librarian subagent** | Answers "what does the literature say about X" from the KB only. It returns work key, page, box, quote, and whether a use already exists. When a caller's workstream is open, it records candidates and uses in that workstream with its token. It holds no promoter or ingest credential. Its model follows the project's subagent routing rule, which is not restated here | a project agent definition, location settled in P8 | P8 |

**None of this reaches other sessions until Kam merges.** The CLAUDE.md rule, the skill, the agent
definition and the hook settings are files in this repository. They reach `main`, and with it every
other session, only through Kam's merge of this branch (CLAUDE.md §3.1: `main` is Kam's). Until then
they bind only sessions working in this worktree. Hook settings change every session's tool calls once
merged, so the P8 promotion report lists them for Kam's review.

---

## 10. Tool integration (R8)

| Existing tool | Becomes | Change |
|---|---|---|
| paper-search (21 sources, OA download) | `litkb.acquire.discover` and the open-access route | Called as a library from its installed package; results → `candidates`. Unpaywall uses Kam's email, held only in the untracked `D:\edmonds-pipeline\secrets\paper_search.env`; optional source keys stay blank until Kam asks (§15.5, decided) |
| aa_fetch resolver | admission checks 1–3 | Moves into `litkb.admit`; evidence stored on identifier versions |
| aa_fetch archive route and gates | `litkb.acquire.annas` | Writes `files` and `acquisition_attempts` instead of `manifest.csv`; the three gates, JSTOR evidence rule, retry ladder and quarantine behaviour kept; its test file moves with it (`D:\tools\annas-mcp\test_aa_fetch.py`: 80 `def test_` definitions, 2026-09-13 **[M]**, `grep -c`; the collected count may differ) |
| aa_fetch `--audit-fast` | `litkb audit` | Writes `file_checks` |
| Sci-Hub method (memory `scihub-fetch-method`) | `litkb.acquire.scihub` | Same route order: first index by curl, second by curl, browser last |
| `manifest.csv`, `Literature_Tracker.xlsx`, `literature_tracker.csv` | exports | Generated by `litkb export`; never edited by hand |
| `Scripts/docs/LITERATURE_CONVENTION.md` | the operating manual | Its tracker section says the xlsx is "human-edited" and "authoritative"; that becomes false the moment exports exist, so it is rewritten **in P3**, in the same commit that makes the tracker an export. The hunt protocol is added in P8 |

Secrets stay outside the repo. **The staged-secrets check is built** (`Reports/LITKB_OPS_2026-09-13.md`
§2 is the home for its rules and kills): `Scripts/qc/secrets_check.py` reads git's index, so one pass
covers tracked and staged files, and refuses secrets file names (`*.pgpass`, `pgpass.conf`, `.env`,
`*.env`, `.litkb-workstream`, anything under `secrets/`), pgpass-shaped lines and named 64-hex tokens.
It is rung 0 of `qc/check.py` and a step in `.github/workflows/ci.yml`. A pre-commit hook is **not**
installed: `.git/hooks` is shared by every worktree of the repository, so installing it would change
other sessions' commits.

---

## 11. Colab (retired for this workstream)

Revision 2 planned a Colab CPU bulk pass here, with the corpus uploaded to the Drive lake, packed shard
archives and a local ingest. **Kam rejected it on 2026-09-13, after P1 acceptance:** all literature
work runs locally on this laptop, CPU first, optimised as needed (decisions.yaml `litkb-p0-foundation`;
R11). No PDF goes to Drive and no runtime is launched for literature. §15.4 and §15.10 are moot for
this workstream and §15.11 is answered. The revision-2 text is in git history. The processing plan is
§12.

---

## 12. Local processing plan (R11)

Everything in this section is design. None of it is built, and no rate, pool size or duration here is
measured. P4 measures, P5 runs (§14).

### 12.1 The machine and what it already carries

- **Hardware [M]:** Intel i7-9850H, 6 physical and 12 logical cores (`Win32_Processor`
  `NumberOfCores` 6, `NumberOfLogicalProcessors` 12); 63.8 GB RAM (`Win32_ComputerSystem`); Quadro
  T2000 4 GB (earlier session, 2026-09-13); Java 23; PostgreSQL 17 and 18, with `litkb` on 18, port
  5433.
- **Virtualization [M], 2026-09-13.** The readings conflict:
  - `Win32_Processor.VirtualizationFirmwareEnabled = False`;
  - but `Win32_ComputerSystem.HypervisorPresent = True`, and `systeminfo` prints "A hypervisor has been
    detected. Features required for Hyper-V will not be displayed.";
  - `wsl.exe -l -v` prints "Windows Subsystem for Linux has no installed distributions";
  - `Get-Command docker` finds nothing.

  A hypervisor cannot run with VT-x off in firmware, and a running hypervisor hides the firmware flag
  from Windows. So the False reading is most likely that masking, and VT-x is most likely already on
  (**inferred, not measured**). If so, path A of §15.9 needs no BIOS change, only a WSL2 distribution
  or Docker Desktop. That stays **[UNCONFIRMED]** until the install is attempted. The revision-3 brief,
  which read the flag alone, said a BIOS change was needed.
- **What runs natively on Windows [F]:** pypdfium2 (Windows wheels), Docling ("Works on macOS, Linux
  and Windows"), MinerU's pipeline backend (Windows, Python 3.10–3.12). GROBID does not: its
  maintainers "cannot ensure currently support for Windows". Embedding models on this laptop are not
  covered by the facts report **[UNCONFIRMED]**; P7 measures them.
- **Shared machine.** The same laptop runs Claude Code sessions, the project's local QC, raster
  diagnostics and the ladder, and the T2000 is the project's local device for that work (CLAUDE.md
  §5). The worker pool is a guest on it: §12.7 reserves for that work, §12.9 schedules around it.

### 12.2 The backlog

- **Active corpus [M]:** 219 PDFs, 4,655 pages (`pdfinfo` over every active PDF); the largest is the
  688-page Schneider 2008 book. Kam expects about 7,400 pages with the backlog (his estimate, not
  measured).
- **Scans.** The revision-3 brief gives 7 image-only scans; its criterion and command are not
  recorded. This revision's probe (`pdftotext` over the 219 active PDFs, 2026-09-13) does not
  reproduce 7 under either criterion it tried:
  - 1 file has no extractable text at all (Ogata 1998);
  - 4 more hold 130–142 characters across 11–22 pages (Anderson 1957, Hudson 1978, Hwang 1982,
    Politis 1994). That is a text layer on at most a cover sheet (inferred);
  - the book has no text on its first page.

  The count is **[UNCONFIRMED]** until stage 0's per-page text-layer probe sets it. OCR cost depends
  on it.

**Stage 0 has now set both, and the home is `phase4/qc/litkb_inventory.csv`, not this section
[M] (2026-09-15).** Over `D:\edmonds-pipeline\Literture`: **241 files / 5,038 pages** including
`_quarantine`, **224 files / 4,712 pages** excluding it; 7 rotated pages, 271 cropped pages in 19
files (296 in 20 including `_quarantine`), exactly 1 page both rotated and cropped, 3 encrypted
files, 0 unreadable, 114 pages needing OCR (111 active). Routing: native 213, mixed 14,
cover-sheet 8, scan 6 (active: 198 / 14 / 7 / 5). The census reproduces byte-identical except its
`seconds` column on a `--force` re-run — verified again at the P4 merge.
(`Reports/LITKB_INVENTORY_2026-09-15.md` §3 "The corpus, measured" and §5 "The scan question"; referee `…_REFEREE_2026-09-15.md`.)

**The "219 PDFs / 4,655 pages" above is a THIRD corpus definition and is superseded**: it came from
`pdfinfo` over 219 active PDFs. **And the scan count is 5 active (+1 in `_quarantine`), not 7** —
reaching 7 requires counting the quarantined copy as a document and the 688-page book as a scan.
Quote a page count only with its corpus definition; §7.1's 216/223 and 224/4,712 sets are likewise
different populations.

### 12.3 A resumable job queue in the database

The queue is the `extraction_jobs` table (§4.3), written only through ingest-role functions.

- **Enqueue by sweep.** A sweep running as `litkb_ingest` finds every active file that lacks a done job
  for each stage of the current pipeline version, and enqueues the missing ones. The unique key makes a
  repeated sweep a no-op. New acquisitions need no enqueue call from agents, so the writer role gains
  no extraction right (§4.7). Migration (P3) is picked up by the same sweep.
- **Dependencies.** A stage's job becomes claimable only when the jobs it reads from are done (stage 5
  needs 0–4, stage 7 needs 5).
- **Claim with a lease.** `claim_jobs(worker, n, lease)` takes queued jobs, or leased jobs whose lease
  has expired, with `FOR UPDATE SKIP LOCKED`. Two workers can never lease the same job, and a dead
  worker's jobs return to the pool when the lease runs out. While a tool runs, a heartbeat renews the
  lease. The lease length is set from P4's longest measured job **[UNCONFIRMED until P4]**. The
  `extraction_runs` unique key is the second lock if two workers ever do the same work.
- **Order.** Short files first, so the number of fully usable files rises fastest; the book last. This
  is a design choice.
- **Failure.** `fail_job` records the error and returns the job to the queue. After a set number of
  attempts (set in P4) the job is `dead`, and only then is an `extraction_runs` row with status
  `failed` inserted. Runs are unique on their key, so a retry after a recorded failure needs a new
  params hash or pipeline version. That is intended: a deterministic failure repeated unchanged fails
  again.
- **Visibility.** `py -3.12 -m litkb queue status` gives counts by stage and state, and pages
  remaining.

### 12.4 Idempotent per-file stages

- **Skip what is done.** A claimed job whose run key already has an `ok` run is marked done without
  running the tool. An artifact already on disk whose sha256 equals the one recorded on the job is not
  produced again.
- **Artifacts.** Output goes to `_derived\<sha256>\<stage>\<tool>@<version>_<params>\` (§6). It is
  written as `.partial`, fsynced, then renamed, which is the pattern `litkb.ops.nightly_dump` already
  uses. Its sha256 is recorded on the job.
- **Ingest is one transaction per (file, stage):** the run row, its text rows and `finish_job` commit
  together or not at all. A killed worker therefore leaves either a finished unit or no rows, and a
  re-run writes the same rows once.
- **Only the reconciliation run moves the pointer.** A file has one current run (§4.4), evidence is
  anchored in it, and `set_current_run` is compare-and-set on the whole file. So only the stage-5
  transaction, whose run owns the canonical `blocks`, calls `set_current_run`. Every other stage
  records its run and leaves `current_run_id` alone. If stage 7 or a re-run of any other stage moved
  the pointer, it would leave the canonical blocks and un-anchor every verified quote on that file.
- **No deletes.** litkb holds no delete permission in `Literture\` (§6). A leftover `.partial` is
  overwritten by the retry at the same path; strays are reported, never deleted.

### 12.5 Checkpointing: a crash or reboot loses at most one file's work

- **The unit of loss is one job.** For almost every file a job is one file at one stage, so a crash, a
  Windows update reboot or a killed process loses at most the file in flight at that stage.
- **Long documents break that bound, so they are split.** The 688-page book, and any file above a page
  threshold set in P4, becomes page-range jobs, each checkpointed as its own artifact. The (file, stage)
  run and its text rows are inserted only when every range is done, in the one transaction that
  assembles the parts (and, for stage 5 only, moves the pointer, §12.4). Page numbers are offset back to the whole document before the §7.1 adapters
  run. For those files the loss bound is one page range. Whether each tool takes a page range directly,
  or needs a split PDF, and whether splitting changes coordinates, is **[UNCONFIRMED until P4]**.
- **On restart** nothing is replayed by hand. Expired leases return, done jobs are skipped (§12.4), and
  the worker continues.

### 12.6 Page-level batching

- **Batches, not one call per page,** where the tool supports it. Docling documents layout and OCR batch
  sizes, recommending 64 over a default of 4 **[F]**. Each stage's batch size is chosen in P4 against
  measured peak memory, not taken from the vendor.
- **Stages 0–1** (pypdfium2) are per page and light. Page images are rendered only for scans and
  disputed pages (§6).

### 12.7 Process pool sizing (12 logical cores against 63.8 GB)

- **Sizing rule, per stage:** workers = min(⌊core budget ÷ threads per worker⌋, ⌊RAM budget ÷ measured
  peak RSS per worker⌋).
  - The core budget is 12 logical cores minus a reserve for Postgres, Claude Code sessions and Kam's
    own use.
  - The RAM budget is 63.8 GB minus a reserve.
  - Both reserves depend on when the pool runs (§15.16). No number is fixed here.
- **Separate pools by weight.** Light stages (0, 1, 5, 6) fan out wide; heavy layout, OCR and math
  models run narrow. Each pool is sized by its own measured peak.
- **No oversubscription.** Each worker's own thread pools (torch, ONNX, BLAS) are capped so that
  workers × threads stays within the core budget. Which settings each tool honours is **[UNCONFIRMED
  until P4]**.
- **Measure at more than one pool size.** 12 logical cores are 6 physical **[M]**, and the gain from
  the second thread on each core is unknown, so P4 records the knee rather than assuming linear
  scaling.
- **GROBID (stage 2), MEASURED 2026-09-14/15, replaces the sourced estimate below for this tool.**
  Pool size **4** is the setting, and the reason is the CPU half of §15.16, not RAM:

  | pool | pages/s (2,361 pages) | peak service RSS | peak whole-system CPU |
  |--:|--:|--:|--:|
  | 1 | 7.73 | 8,243 MiB | 58.6 % |
  | **4** | **20.2** | 11,655 MiB | **76.5 %** |
  | 9 | 21.1 | 13,758 MiB | 100.0 % |

  Pool 9 leaves Kam nothing and buys 4 % of the rate; `grobid.sh` now defaults to 4 and REFUSES
  anything higher unless `GROBID_BREAK_HEADROOM=1` says so out loud. **There is no per-worker
  process** — one JVM serves the whole pool — so "peak RSS per worker" can only be derived:
  **≈ 689 MiB per added worker** over the 1→9 span, on top of a base that is itself ~5.7 GiB of
  non-heap above `-Xmx8g`. `pdfalto` is the only per-request process and peaks at **20.5 MiB**
  (the earlier 1.5 GiB-per-worker budget term was wrong by ~75×; the 1,536 MB config value is a
  ceiling, not a budget). The 688-page book, re-measured warm on an idle machine by
  `qc/instruments/litkb_grobid_throughput.py` (`--runs 3 --warm-up <a 16-page paper>`):
  **12.11 pages/s median, 7.0 % spread** (61.1 / 56.8 / 56.8 s), replicating an
  earlier-that-session 12.20 / 7.6 %. This is ONE request served by one worker of a pool-4
  service — it is not the 20.2 pages/s pool figure above, which is a 15-request mixed set —
  and it supersedes the builder's unreplicated 10.91 and the referee's contended 8.04.
  Rows land in `phase4/qc/litkb_extraction_metrics.jsonl`; the spread rule is the
  instrument's own (>20 % ⇒ UNDETERMINED, not "slower").
- **The only sourced per-process memory figures [F]:** MinerU needs at least 16 GB RAM, 32 GB
  recommended; GROBID needs 4 GB for full structuring and 6–8 GB for batch (path A, counted against
  the budget inside WSL2 or Docker). By arithmetic on those figures alone, at most three MinerU workers
  fit in 63.8 GB before any reserve. Docling's memory, and every other figure, is **[UNCONFIRMED]**
  until P4 measures peak RSS.

### 12.8 The T2000 4 GB GPU: where it may help (all UNCONFIRMED until measured)

A stage uses the GPU only if the tool supports it, P4 measures it running within 4 GB on the hard
papers, and it is faster than that stage's CPU pool. Only one GPU worker runs at a time. The card is the
project's local QC device too, so GPU stages run only in the window of §15.16.

| Stage | Tool support | Fit on 4 GB |
|---|---|---|
| 3 Layout, tables, OCR (Docling) | GPU speeds published **[F]** | VRAM need "not stated" **[F]** → **[UNCONFIRMED]** |
| 4 Equations (MinerU pipeline backend) | "min 4 GB VRAM" **[F]** | exactly the card's size, no headroom → **[UNCONFIRMED]**; hybrid and VLM backends need 8 GB **[F]**, excluded |
| 4 Equations (Docling formula enrichment) | not stated in the facts report | **[UNCONFIRMED]** |
| 7 Embeddings | not in the facts report | **[UNCONFIRMED]**; P7 measures |
| 2 GROBID (path A) | GPU through a container on Windows not supported **[F]**; GPU under WSL2 not in the facts report | none planned; the CRF image needs no GPU **[F]** |
| Marker / Surya | vLLM on an NVIDIA GPU, README says Docker + NVIDIA Container Toolkit **[F]** | excluded (§7 stage 4) |

### 12.9 Overnight and low-priority running

- **Always below-normal priority,** so interactive work wins the CPU. The Windows mechanism the worker
  uses is chosen in P4 **[UNCONFIRMED]**.
- **Full pool overnight; reduced pool or none by day.** The window and both reserves are Kam's call
  (§15.16).
- **Launch by scheduled task,** like the nightly dump, with the dump's measured limit
  (`Reports/LITKB_OPS_2026-09-13.md` §1). Registering the task to run "whether logged on or not" (S4U)
  was refused without elevation. An unelevated task therefore runs only while Kam is logged on, and the
  pool stops at logoff unless Kam registers the task elevated (§15.16).
- **Pause drains.** `litkb worker pause` finishes the jobs in flight and claims no more. A reboot or
  kill is covered by §12.5.
- **Nightly dump.** The dump runs at 02:30 and took 1.6 s at 12 rows (ops report). No coordination is
  needed now; revisit once the database holds the corpus's text.
- **On battery,** whether the pool pauses is a design choice for P5; how it detects mains power is
  **[UNCONFIRMED]**.

### 12.10 Backlog projection: measured by P4, never stated here

**This document projects no hours.** P4 measures on this laptop, per stage and chosen tool, on the
hard-paper set, and at more than one pool size (§12.7):
- pages per second;
- peak RSS per worker;
- GPU memory, where a stage uses the GPU.

P5's canary measures the same on ordinary papers.

**Projection** = Σ over stages of (pages that stage must process ÷ measured pages/s at its chosen pool
size), converted to nights at the window Kam sets (§15.16). The page count comes from stage 0's
inventory: 4,655 active **[M]**, about 7,400 with the backlog (Kam's estimate).

**What P4 has measured so far — PROVISIONAL, and the throughput gate is NOT MET [M] (2026-09-15).**
This section stays unfilled as a projection; what follows is the measured basis, with its load
stated, so that the gap to the gate is visible rather than implied.

| Stage / tool | measured | basis, and why it is not yet the gate |
|---|---|---|
| 2 GROBID, 688-page book | **10.91 p/s** warm / 5.70 cold (builder, 3 rows 11.26/12.11/12.11); referee 1 median **8.04 p/s**; referee 2 determined **9.41 p/s** on a quiet host, 22.3 % below the builder's 12.11 | Every timing is **concurrency 1**. A projection built on 12.11 p/s is optimistic by ~25 %; carry the **range with the load stated**, not a point. `GROBID_LOCAL_REFEREE2` defect D6 |
| 3 Docling, layout, 5 gate papers | **0.711 p/s** aggregate over 199 pages, peak RSS 2,641 MB; the 688-page book alone **0.691 p/s**, peak **4,120 MB** | 5 papers + one book, **not the corpus**. `DOCLING_LOCAL` §3, "Timing, memory and CPU — CPU only" |
| 3 Docling, OCR (Anderson 1957) | **0.094 p/s**, 22 pages | one file |
| 4 Docling, formula enrichment | **0.0042–0.0062 p/s** (Bellettini pp. 3–4) | two pages; the corpus figure is an equation-density census plus an explicit projection, labelled "Not a measurement" |
| 3–4 on the T2000 GPU | layout **6.0×** (4.272 p/s), OCR **6.6×** (0.622 p/s), at +1,482–1,662 MiB | measured, same 5-paper set |
| 4 formula over the corpus | **≈17 h GPU / ≈150 h CPU** | a **projection**, not a measurement: decode time plus per-run cold start, from the density census. `DOCLING_A_REFEREE` §5, "Projection — «per region» is right; the region count is 18% too high" |

**Why the gate is not met**, clause by clause: metrics are parked as JSONL
(`phase4/qc/litkb_extraction_metrics.jsonl`) rather than written to `extraction_runs.metrics`;
GROBID's per-worker RSS is **derived** from one shared JVM's slope (~689 MiB/worker), not measured;
GROBID has no two-pool-size measurement; Docling has not run on the corpus. The two throughput
**kills** do fire — a one-core pin reports a lower rate than the pool (GROBID 12.65 s vs 8.14 s,
1.55×; Docling 0.396 vs 0.601 p/s, 1.52×), and the Docling instrument refuses a run recording no RSS (the GROBID instrument records the RSS but has no refusal path: a gap, named here).

**Vendor speeds are not inputs.** Docling reports 1.2–1.5 pages/s CPU-only **[F]**, and GROBID 10.6
PDFs/s on one 16-CPU machine **[F]**, both on other hardware.

**If the measured projection is too long for Kam,** the levers, in order:
1. GPU stages that P4 showed fit (§12.8);
2. a first pass without stages 4 (equations) and 6 (references), which run as a second pass;
3. batch sizes (§12.6);
4. a longer window.

### 12.11 Reproducibility

The Colab-versus-local parity rule of revision 2 has no subject now. It is replaced by a
reproducibility rule: the same file, extracted again at the same pipeline version, gives the same
canonical blocks. P9 tests it on a sample. A tool found to be nondeterministic is recorded as such, not
averaged away.

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
| **P4 Extraction bake-off (local)** | Stages 0–5 run **on this laptop** on ~10 hard papers: a two-column article, a three-column article, a JSTOR scan, an image-only scan, an equation-heavy theory paper, a table-heavy paper, and the 688-page book. Also: the bbox adapters (§7.1); stage 2 on the path Kam chose (§15.9); the `extraction_jobs` migration, the leased worker and the sweep (§12.3–§12.5); and a throughput and memory instrument | Tools are chosen against **referee-authored, pre-committed gold**: reading-order sequences, table cells, header metadata and equation LaTeX for the hard papers, plus reference lists checked against Crossref-deposited lists. Thresholds are committed with the gold. The adapters pass the §7.1 test. **Path A:** GROBID 0.9.1 CRF boots under WSL2 or Docker on this laptop and returns TEI with coordinates for one paper. **Path B:** the chosen reference parser meets the pre-committed reference threshold. **Throughput gate:** for every stage × chosen tool, pages/s and peak RSS per worker (plus GPU memory where used, §12.8) are measured on the hard-paper set at two or more pool sizes. They are written to `extraction_runs.metrics` and the phase report, and the §12.10 projection is filled in from them. A referee re-runs one stage and reproduces its rate (3.4c). No wall-clock is accepted from any other source | **Path A:** the GROBID boot check fails when run under a JDK older than 21. **Path B:** reference fields shuffled between entries fail the reference metric. **Both paths:** the §7.1 test fails with an adapter's y-flip removed; a deliberately interleaved column extraction fails the reading-order metric; shuffled table cells fail the table metric. **Throughput:** the instrument refuses a stage run that records no rate or no peak RSS, and it reports a lower rate for a stage pinned to one logical core than for the same stage on the pool, which shows it can see a slowdown |
| **P5 Local bulk pass** | Canary → projection → Kam's go → backlog. The **canary** is a batch not in the hard set, spanning born-digital, scanned and long documents. The **projection** comes from P4's measured rates, checked against the canary's. **Kam's go** is asked with the projection, its measured basis and the run window (§15.16). The **backlog** is then drained by the worker pool with ingest, overnight at low priority (§12.9) | Every active file has a current run with pages and blocks; chunks and embeddings come in P7. Coverage is at or above the P4 threshold, and disagreements are logged. The canary's rate falls within a tolerance of P4's, frozen before the canary runs; otherwise the projection is redone before Kam is asked. There are zero duplicate runs and zero text rows outside an `ok` run | **(a)** A worker killed mid-file, once during a tool run and once during ingest, resumes after restart. The file completes with exactly one `ok` run per key and the same block count as an uninterrupted control run, with no duplicate blocks. The kill fires when ingest is mutated to commit text rows outside the run's transaction. **(b)** An artifact whose bytes no longer match the job's recorded sha256 fails ingest verification. **(c)** Two workers claiming at once never lease the same job; this fires with `SKIP LOCKED` or the lease check removed. **(d)** A job whose worker died is reclaimed only after its lease expires, not while the lease is live |
| **P6 Citations** | references resolved, citation graph, citation candidates | reference resolution rate measured and reported | a **near-miss** reference — a real reference from the corpus with one field altered (year, a title word, or a DOI digit) — does not resolve to the real work |
| **P7 Retrieval** | embeddings, hybrid search, evaluation on the referee's paraphrased query set (§8) | vector leg and hybrid each at or above their pre-committed recall@k thresholds | with the vectors replaced by random vectors, **the vector leg alone**, on the paraphrased queries, falls below its threshold (the lexical legs would otherwise rescue a scrambled index) |
| **P8 Access** | MCP server and CLI; the hunt protocol written into the convention; the access layer of §9.1: skill, librarian subagent, and the final CLAUDE.md rule on this branch (it reaches `main` only by Kam's merge). The hooks come last, after the gate | The librarian subagent, following the skill in a scratch worktree, runs a full mini-hunt: open workstream → admit → acquire → extract → record use with verified quote → promote prepare. Commit is exercised against a scratch git repository whose `main` it merges itself, never the real one | A use with an unverifiable quote is refused at prepare (fires before the mini-hunt gate is accepted). The hook's own kill fires after that gate and before the hook is relied on: with the hook installed, a paper-search call made in a worktree with no `.litkb-workstream` is flagged; with the hook entry removed, it is not |
| **P9 Incremental mode + retire old paths** | The sweep (§12.3) picks up newly admitted files with no manual step; the reproducibility test (§12.11); the hand-edited tracker retired | A sample re-extracted at the same pipeline version gives identical canonical blocks; a file admitted after P5 reaches a current run with no manual step; old paths are removed from the convention | A nondeterminism introduced on purpose (reading order permuted in one re-run) is caught |

### P4 status at the adapter merge (2026-09-15)

Three refereed branches landed on `work/20260913-literature-kb` —
stage 0 inventory (`work/20260915-inventory-stage0`), stage 2 GROBID
(`work/20260914-grobid-local`), stage 3 Docling (`work/20260915-docling-local`).
The row's gate text above is unchanged; this is what of it is now MET.

| P4 gate clause | Status | Evidence |
|---|---|---|
| Path A: GROBID 0.9.1 CRF boots under WSL2 and returns TEI with coordinates | **MET** | `Reports/LITKB_GROBID_LOCAL_REFEREE_2026-09-14.md`; re-run at the merge, 54/54 tests pass with the service live |
| Kill: the boot check fails under a JDK older than 21 | **FIRES** | same referee (`class file version 65.0`, rc 1) |
| Kill: the §7.1 test fails with an adapter's arithmetic removed | **FIRES** for GROBID and for Docling | `…GROBID_LOCAL_REFEREE_2026-09-14.md`; `…DOCLING_LOCAL_REFEREE_2026-09-15.md` (M2: ignoring `coord_origin` fails 3 tests) |
| The adapters pass the §7.1 test | **MET for stages 0, 2, 3**; MinerU and any path-B parser unwritten | the three referee reports |
| Stage 0 inventory, with the frame and text-layer census | **MET, with three named limitations**; its threshold band is pinned and the pins fire | `Reports/LITKB_INVENTORY_REFEREE_2026-09-15.md` |
| Docling fail-closed formula enrichment | **MET, and no longer synthetic** — the OOM kill fired on a real CUDA OOM | `Reports/LITKB_DOCLING_A_REFEREE_2026-09-15.md` |
| Kill: the throughput instrument refuses a run with no rate or no peak RSS | **FIRES for Docling; NOT SHOWN for GROBID** | `Reports/LITKB_DOCLING_LOCAL_2026-09-15.md` §5. `qc/instruments/litkb_grobid_throughput.py` records `peak_rss_bytes` but carries no refusal path, and no referee exercised one |
| Kill: a one-core pin reports a lower rate than the pool | **FIRES** (GROBID 1.55×, Docling 1.52×) | §12.10 |
| **Throughput gate** (pages/s and peak RSS per worker, every stage × chosen tool, **two or more pool sizes**, written to `extraction_runs.metrics`, §12.10 filled in) | **NOT MET** | §12.10: GROBID is concurrency-1 only and its per-worker RSS is derived, not measured; Docling has run on 5 gate papers and the book, **not the corpus**; metrics are parked as JSONL, not in `extraction_runs.metrics` |
| **Stage 5 reconciliation** | **BUILT 2026-09-15**, with the P5 ingest schema (migration 0017) and `litkb.extract.{reconcile,ingest}`. Run on the 5 gate papers + `Ogata_1998` (scan/OCR) + `Almon_1965` (cover sheet); 18 mutation rows `R51`–`R518` all fire. **Its four thresholds are author-chosen and UNVALIDATED against gold**, and 0017 is NOT applied to `litkb` | `Reports/LITKB_STAGE5_INGEST_2026-09-15.md` |
| Stages 1 (native layer) and 4 via MinerU; path-B reference parser; the `extraction_jobs` migration, leased worker and sweep (§12.3–§12.5) | **NOT BUILT** | — |
| "Referee-authored, pre-committed gold … thresholds committed before the tool first runs on them" | **NOT VERIFIED.** Nothing in the three reports records gold authored by a referee and committed ahead of the measurement; the referees re-ran the builders' measurements instead | — |

**Two honesty notes (3.4c).** (1) Each branch's head is an **author** commit made *after* its last
referee pass — `cc36b82`, `8f985e5`, `5b26768`. In particular `GROBID_LOCAL_REFEREE2` returned
**STAGE 2 NOT READY** on defect D1 (`enable` did not check the concurrency headroom) and `8f985e5`
closes it; the fix is real and readable — `enable` now goes through `write_unit()`, which calls
`require_concurrency_headroom` before it writes the unit (`grobid.sh`, `write_unit()`) — but **it has
not been re-refereed**. The referee reports named above are the authority for everything up to the
defects they list; the author commits that close those defects are not covered by any referee.
(2) The GROBID book rate is a **range under stated load** (8.04–12.11 p/s), not a point; the
builder's 12.11 did not reproduce.

**Order of value:** P1–P3 already fix today's pain (mergeable, versioned, concurrent records with
checks). P4–P7 add the knowledge layer. P8 makes it Claude's daily tool.

---

## 15. Decisions for Kam (P0)

Numbers are stable: `decisions.yaml` cites these items by number, so answered items are marked, never
removed or renumbered. Authority for every "Decided" is `decisions.yaml` `litkb-p0-foundation`.

1. **Server.** **Decided:** PostgreSQL 18 on port 5433.
2. **pgvector on Windows.** **Decided:** P1 waited for the C++ Build Tools and pgvector. Built:
   `vector 0.8.6` in both databases (P1 report).
3. **Embeddings stay local** (no text sent to a third-party embedding API). Proposed yes. The all-local
   decision points the same way, but this item is not recorded as answered.
4. ~~Colab bulk pass on CPU runtimes first~~ **Moot:** no Colab pass (§11).
5. **paper-search keys.** **Decided:** Unpaywall uses Kam's email, held only in the untracked
   `D:\edmonds-pipeline\secrets\paper_search.env`; optional source keys stay blank until Kam asks.
6. **Derived artifacts location:** `D:\edmonds-pipeline\Literture\_derived\`. Proposed yes. Open.
7. **Promotion authority.** `promote prepare` runs on the branch, and its report reaches you inside the
   merge; `promote commit` runs only after you merge (§5). **Decided:** the orchestrator runs commit
   after it sees the merge commit on main. The promote tool refuses a commit that is not reachable
   from main (the database cannot run git), and only the promote tool holds the promoter credential
   (§4.7).
8. **Figure descriptions by Claude vision:** on demand only (proposed), or a bulk pass later. Open.
9. **GROBID — confirm the path.** The recorded decision is that GROBID runs locally under WSL2 or
   Docker, with setup pending. On 2026-09-13 the laptop read `VirtualizationFirmwareEnabled = False`,
   yet a hypervisor is running (`HypervisorPresent = True`); WSL has no distribution; Docker is not
   installed **[M]** (§12.1). GROBID's maintainers do not support native Windows **[F]**, so running
   it natively is not offered. **Two paths — choose one before P4:**
   - **(a) Keep GROBID under WSL2 or Docker.** A WSL2 distribution or Docker Desktop is installed,
     which needs admin. If that install reports virtualization unavailable, you enable VT-x in the
     BIOS, which needs a reboot and your hands. The running hypervisor suggests it is already on
     (inferred, §12.1). P4 then boots the GROBID 0.9.1 CRF image, which needs no GPU. *Gains:* header metadata, section
     tree, footnotes and captions with coordinates, parsed references and in-text citations linked to
     them, all in one TEI output **[F]**. P6 (citations) is designed on these. *Costs:* an admin
     install (plus a firmware change only if the install demands it), and GROBID's 4–8 GB of RAM
     **[F]** taken from the worker pool's budget.
   - **(b) Drop GROBID.** Docling supplies layout, reading order, tables and formulas **[F]**.
     Reference-string parsing comes from another parser: none is in the tool facts report yet, so a
     candidate is researched into that report before P4 **[UNCONFIRMED]**. Citation → reference
     linking and any header parse come from project code. *Gains:* no installs outside Python.
     *Costs:* the citation layer that P6 builds on is new project code, validated from scratch, and
     stage 0's metadata loses one of its three sources (§6).
   - *Proposed:* (a), because P6 is built on GROBID's reference parsing and citation linking. Your
     call.
10. ~~Colab terms, project-wide~~ **Moot for this workstream.** The project-wide question about
    `vm_ops.py` headless practice is not this design's to raise.
11. ~~Shadow-library PDFs on Drive~~ **Answered:** no PDFs go to Drive; everything is extracted
    locally.
12. **A small database dump.** **Decided and built:** a nightly `pg_dump` of the records, with no PDFs
    and no derived artifacts (§6; ops report §1). Residual: the dumps sit on D:, the same disk as the
    database's tablespace (inferred from the two paths), so a disk loss takes both; off-disk copies
    remain tabled under R12.
13. **Manual-admission sign-off.** **Decided:** a second session. The database refuses an approver
    session equal to the admitter's; agent names are labels and are not compared (D-4).
14. **Admissions refused at binding** (scans with no first-page text layer, cover-sheet first pages).
    **Decided:** they wait for OCR in P4, with no manual admission.
15. **Year tolerance.** **Decided:** ±1 year only when the title and first author both match the
    registry record; otherwise the year must match exactly.
16. **New — worker run window (§12.7, §12.9).** Choose when the extraction pool runs and what it leaves
    free:
    - (a) overnight only, with the full pool;
    - (b) overnight full, plus daytime at below-normal priority with a reduced pool;
    - (c) continuously at below-normal priority.

    Also choose the CPU and RAM reserve kept for your own use and for Claude Code. And choose how the
    scheduled task is registered. Unelevated, it runs only while you are logged on: S4U registration
    was refused without elevation **[M]**, ops report §1. Registered by you from an elevated shell, it
    can run logged off. Needed before P5's go.
17. **New — what "flows through this workstream" covers (R13, §9.1).** Choose the reach of the
    CLAUDE.md rule:
    - (a) every literature claim in a gated document cites an admitted work, with a use whose quote
      verifies;
    - (b) (a), plus every literature search and PDF fetch goes through litkb tools, with hooks as
      guardrails;
    - (c) (b), plus a paper Claude recalls from memory is admitted before anything relies on it.

    Also choose whether literature already cited in gated documents (SCIENCE.md, the reports) is
    back-filled, or the rule applies going forward. Needed for the interim rule at P3.

---

## 16. Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| GROBID's maintainers do not support Windows **[F]**; neither WSL2 nor Docker is set up **[M]**; the firmware virtualization flag reads disabled while a hypervisor runs **[M]** (VT-x probably on, inferred) | stage 2 on path A cannot start until an install succeeds, and a BIOS change may yet be needed; path B loses GROBID's header parse and citation linking unless rebuilt | §15.9 before P4; path A's boot gate with its JDK kill, or path B's reference-metric gate with its shuffle kill (§14 P4) |
| Layout, OCR or math models slow on this CPU | the backlog takes many nights (no figure is projected; P4 measures) | P4 throughput gate; P5 projection and Kam's go before the backlog; GPU stages only where they fit; stages 4 and 6 deferred to a second pass (§12.10) |
| ~~pgvector's README offers only a source build on Windows~~ | — | **Resolved in P1:** Build Tools installed, `vector 0.8.6` loaded |
| ~~Colab terms on headless and parallel use~~ | — | **Moot for this workstream** (§11, §15.10) |
| MinerU needs at least 16 GB RAM **[F]** | at most three MinerU workers in 63.8 GB before any reserve (arithmetic) | pools sized by measured peak RSS per stage (§12.7) |
| The laptop is shared with Claude Code sessions, local QC, the ladder and GPU raster work (CLAUDE.md §5) | extraction slows interactive work, or is slowed by it; the 4 GB card cannot hold two model loads (inferred) | below-normal priority; core and RAM reserve; run window; one GPU worker, only in the window (§12.8, §12.9, §15.16) |
| A worker killed, a crash, or a Windows update reboot mid-run | lost or duplicated extraction work | leases with expiry; one transaction per (file, stage) ingest; `.partial` + fsync + rename; page-range jobs for long documents; P5 kills (a)–(d) |
| The scheduled task runs only while Kam is logged on (S4U refused unelevated **[M]**) | the pool stops at logoff | §15.16 |
| Scan OCR quality on 1950s–70s JSTOR papers | wrong text in theory papers | per-block confidence; disputed regions to vision; evidence quotes must verify |
| Scans and cover-sheet first pages cannot pass the binding gate | papers wait in quarantine | `binding-pending` state; they wait for P4 OCR (§15.14, decided) |
| ~~Colab writer path to Drive~~ | — | **Moot:** no Drive writes (§11) |
| Library licences **[F]**: PyMuPDF AGPL or commercial; Marker/Surya weights free only for research, personal use and startups under $5M; Nougat weights CC-BY-NC | constraints on use | pypdfium2 instead of PyMuPDF; Docling (MIT), GROBID (Apache-2.0), MinerU (custom licence based on Apache 2.0) preferred |
| A stage other than reconciliation moves `files.current_run_id` (a stage-7 ingest, or a P9 re-run) | verified evidence on that file is un-anchored and promotion refuses it; the P9 reproducibility test would not notice, since blocks are unchanged | only the stage-5 transaction calls `set_current_run` (§12.4); a P5 test asserts that a stage-7 ingest leaves the pointer and `use_evidence_status` unchanged |
| Extraction workers and agents share one database server | ingest load slows agent queries; lock waits | short per-(file, stage) transactions; workers at low priority; the ingest role cannot touch knowledge tables (§4.7) |
| Recorded agent/session identities are client-supplied | the approver-session ≠ admitter-session constraint can be defeated by a forged session label | stops mistakes, not adversaries; §15.13 |
| Dumps sit on the same disk as the database | a disk loss erases use histories and promotions together with their dumps | nightly dump built (§6); off-disk copy tabled under R12 (§15.12) |
| An access rule or hook that points at tools not yet built | agents blocked with no route, or the rule ignored | interim rule at P3 points at the working CLI; hooks only after P8's gate (§9.1) |
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
| Colab — **moot for this workstream (revision 3)**; kept as the record of what was checked | FAQ: VMs have a maximum lifetime; idle timeout; usage limits fluctuate; the free tier disallows remote control, bypassing the notebook UI and distributed computing workers. Account plan Colab Pro (`Scripts/pipeline/colab_rates.csv`, screen-read 2026-09-01) | Pro terms on headless use; runtime vCPU/RAM (free tier ~2 vCPU / ~13 GB from secondary sources only); disk; apt and Java installs; tool speeds on Colab |

---

## 18. Change log

**Revision 3 (2026-09-13).** Applies Kam's decision after P1 acceptance: all literature work runs
locally, with no Colab pass, and any literature the project uses flows through the knowledge base
(decisions.yaml `litkb-p0-foundation`). The doc is also brought into line with what is built.

- **§1:** R11 marked superseded, with Kam's words; R13 added; non-goals now exclude cloud compute.
- **§2:** decision 4 and the diagram describe local workers.
- **§3:** `uuidv7` is confirmed by the P1 gate.
- **§11:** the Colab plan is retired to a short note.
- **§12:** rewritten as the local processing plan: the queue, idempotent stages, the checkpoint loss
  bound with page-range jobs for long documents, batching, the pool sizing rule, GPU candidates (all
  UNCONFIRMED), overnight and low-priority running, a projection formula with no hours stated, and a
  reproducibility rule replacing Colab/local parity.
- **§4.3:** the `extraction_jobs` table is added (design, not built). The built `extraction_runs` unique
  key and its leftover `host = 'colab'` value are recorded.
- **§4.7:** the ingest row points at §12 and adds the queue functions. The owner row now names
  `connect_admin()` (F-9) and the nightly dump.
- **§6:** the dump is recorded as built (location, verification, retention, task mode, and the need to
  re-register the task after the merge). The header parse depends on §15.9. No PDFs go to Drive.
- **§7 / §7.1:** stage 2 presents path A (GROBID under WSL2 or Docker) and path B (no GROBID), with what B
  loses.
- **§9:** CLI entries for the worker pool added, and the missing CLI stated.
- **§9.1 (new):** the access layer — the CLAUDE.md rule, skill, MCP tools, hooks and librarian
  subagent, with a phase for each, and the rule that they reach `main` only by Kam's merge.
- **§10:** the staged-secrets check is recorded as built (rung 0 of `check.py`, a CI step, no pre-commit
  hook); the paper-search keys row is updated to §15.5.
- **§14:**
  - P4 runs locally, with a measured throughput gate and kill, and gates and kills for each GROBID
    path.
  - P5 becomes the local bulk pass. Its kills are local: a killed worker resumes without duplicate
    blocks, an artifact hash mismatch is caught, concurrent claims never collide, and a job is
    reclaimed only after its lease expires.
  - P5's gate no longer asks for chunks. Chunks are stage 7, built in P7; the earlier text was
    inconsistent.
  - P8 adds the access layer and a hook kill.
  - P9 replaces parity with reproducibility.
- **§15:**
  - Items 1, 2, 5, 12, 14 and 15 are marked decided (7 and 13 already were), 4 and 10 moot, and 11
    answered. Numbering is kept, because `decisions.yaml` cites these items by number.
  - 9 is reopened as a two-path choice by the virtualization measurement.
  - 16 (worker run window) and 17 (reach of R13) are new.
- **§16:** Colab rows marked moot, pgvector resolved, local risks added. §17's Colab row is marked moot.
  §19's M4/M5 rows are historical and left as written.
- **§4.6:** check 1 records the decided year rule (§15.15). Check 3 drops manual admission for files
  refused at binding (§15.14).
- **§12.4 (fixed before the report):** the first rev-3 text had every stage's ingest call
  `set_current_run`. That would move a file's single pointer off the reconciliation run and un-anchor
  its evidence. Now only stage 5 moves the pointer; §16 carries the risk and its test.
- **Brief corrected by measurement:** the brief said VT-x must be enabled in the BIOS, reading
  `VirtualizationFirmwareEnabled = False` alone. `HypervisorPresent = True` and `systeminfo`'s "A
  hypervisor has been detected" show a hypervisor running. So the flag is most likely masked and VT-x
  already on (inferred). §7, §12.1, §15.9 and §16 say so.
- **Measured this revision:**
  - `Win32_Processor`: 6 cores, 12 logical, `VirtualizationFirmwareEnabled` False.
    `Win32_ComputerSystem.HypervisorPresent`: True.
  - `wsl.exe -l -v`: no installed distributions. `Get-Command docker`: not found.
  - `Win32_ComputerSystem`: 63.8 GB RAM.
  - `ls -a`: no `.claude/` directory in the repository.
- **Not reproduced:** the brief's "7 image-only scans". A `pdftotext` probe over the 219 active PDFs
  found 1 file with no text, 4 with 130–142 characters in total, and 1 (the book) with no first-page
  text (§12.2). The count stays UNCONFIRMED until stage 0.

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
- **Corrected after the first revision-2 commit:** §4.6 check 3 cited Higham 2011 as a file whose
  title is not on the first line. That misread `audit_fast.csv`: the quoted boilerplate was the
  `best_extract_line` matched against the wrong registry title, and Higham's extract begins with its
  title. The example is now Averkov 2009, whose title is the fourth line of its extract.
- **No referee claim was rejected.**

### 2026-09-15 — P4 GROBID referee defects closed (`Reports/LITKB_GROBID_LOCAL_REFEREE_2026-09-14.md`)

- **§7.1** gains three measured facts the design did not state: the canonical origin sits on the
  **mediabox** while GROBID measures from the **cropbox** (10.5–10.9 pt on 223 corpus pages, with
  the adapter and the 0.39–0.91 pt residual after correction); `teiCoordinates` is a **repeated**
  form field that degrades silently when comma-joined; and the **zero-block rule** — a 200 whose
  `<text><body>` carries no block is refused, never recorded as an extraction.
- **§12.7** gains the measured GROBID pool table. **Pool 4, not 9**: pool 9 reaches 100 % system CPU,
  breaking the CPU half of §15.16, for 4 % more throughput. Per-worker RSS is derived (~689 MiB per
  added worker of one shared JVM), and the old 1.5 GiB-per-worker pdfalto term is replaced by the
  measured 20.5 MiB. The 688-page book is re-measured at **12.20 pages/s median (7.6 % spread)**,
  superseding both the builder's unreplicated 10.91 and the referee's contended 8.04 — and
  measured by a committed instrument, `qc/instruments/litkb_grobid_throughput.py`, not by a
  scratch script. A cold service is not comparable to a warm one even in its OUTPUT, not just
  its rate: cold Benedek returns 274,185 B / 3,762 boxes, warm 274,093 B / 3,760.
- `extraction_runs.metrics` is produced by `litkb.extract.grobid.extract()` as the dict P5's ingest
  persists (§4.3's JSON contract), parked meanwhile as JSONL — the table needs a `files` row and the
  `litkb_ingest` login, both P3/P5.

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
