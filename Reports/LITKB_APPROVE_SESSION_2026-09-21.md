# litkb approve session — S3 second session

- Date: 2026-09-21
- Session label: `s3-approve-1` (agent `claude`)
- Workstream opened for this review: `01a0c380-0a7f-7827-9d62-fb49479cca0d` (slug `approve-1`,
  purpose "S3 second-session review of edges-1 proposals", branch `work/20260921-litkb-s3-approve`)
- Worktree: `D:\edmonds-pipeline\wt-s3-approve`, merged HEAD `568988b`
- Scope: the two real URL-source manual proposals the web-source gate
  (`decisions.yaml` → `litkb-web-source-gate`) has held since 2026-09-15/16. The S3 edge run in
  workstream `edges-1` (`01a0c289-fda3-77c3-aa94-b71103e7874b`) created no proposals of its own —
  every URL row it ran was refused as a duplicate of a work the base already holds.

---

## 01a0a7c4-9f49-7c81-a1b8-f482f479858c

- Work key: `Riva_2017_ifla-library-reference-model` (work_id `01a0a7c4-9f1b-7834-acf5-3e6cac1f390a`)
- Route: `manual` (URL-PDF). Admitted 2026-09-15 by `claude-opus-5` /
  `session_015MUcyGTfX2koRdYAjW5kED` in workstream `linkage-review`
  (`01a0a7be-4440-7a1c-879b-9a691d2c52d7`).
- **Decision: APPROVED**

Evidence read

- Admission `checks`: check1 `pass`, check2 `pass`, check3 `bound` at ratio 1.0; `manual_source` =
  `https://www.ifla.org/wp-content/uploads/2019/05/assets/cataloguing/frbr-lrm/ifla-lrm-august-2017_rev201712.pdf`
  retrieved 2026-09-15, "IFLA standard, no DOI".
- File version: `_litkb_staging/incoming/IFLA_2017_library-reference-model.pdf`, md5
  `c013813f9a391724fde785b9d5aee68b`, 101 pages, text layer present. The checks carry an md5, not a
  sha256; I recomputed both from the file on disk — md5 matches the recorded value; sha256 is
  `ac0e699d923b33dcc47884678d08ee1e51923363eb40fdbdaeb30feaca310948` (recorded here for the first
  time; there is nothing in the row to compare it against).
- Document itself (`pdftotext` pages 1–3, read-only): title page reads "IFLA Library Reference
  Model / A Conceptual Model for Bibliographic Information"; byline "Pat Riva, Patrick Le Boeuf,
  and Maja Zumer, Consolidation Editorial Group of the IFLA FRBR Review Group"; "August 2017 /
  Revised after world-wide review / Endorsed by the IFLA Professional Committee / As amended and
  corrected through December 2017"; CC BY 4.0, IFLA, Den Haag.
- What matched: the title in the work version is the title page verbatim; the three author families
  in the record (Riva, Boeuf, Zumer) are the three people on the byline; year 2017 is printed on the
  title page. The file is the full 101-page standard — table of contents, entity / attribute /
  relationship definitions, model overview — not a landing or abstract page.
- Host: `www.ifla.org`, the standards body that issued the LRM. The work's own publisher, not an
  aggregator and not a search page.
- Duplicate check at review time: `litkb.main_works` held no work with this key and no title
  matching "library reference model"; `litkb.main_identifiers` held no IFLA value.

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a7c4-9f1b-7834-acf5-3e6cac1f390a", "entity": "work", "version": "01a0a7c4-9f1c-7d8b-bbc2-f8acce8bfde5"},
  {"id": "01a0a7c4-9f2f-7f7f-ad81-7255d86e709f", "entity": "file", "version": "01a0a7c4-9f3e-72cd-89be-39ec1f436fea"}
]
```

---

## 01a0ad55-ebc2-79c1-892b-6485eb34c776

- Work key: `Abdulkader_2020_cnn-fpga-implementation-hardware` (work_id
  `01a0ad55-eb8d-7037-b37c-5a431107074a`)
- Route: `manual`, `source_route` = `web`. Admitted 2026-09-16 by `claude-opus-5` /
  `hunt-one-shot-20260916` in workstream `hunt-test-1` (`01a0ad54-4a7a-7291-bb8c-02afc132f0c8`).
- **Decision: APPROVED**

Evidence read

- Admission `checks`: check1 `pass`, check2 `pass`, check3 `bound` at ratio 0.8916; `web.url` =
  `https://raw.githubusercontent.com/omarelhedaby/CNN-FPGA/master/Hardware%20Documentation.pdf`,
  retrieved 2026-09-17, `snapshot_binding` `bound`; `manual_source` "hunted from the CNN-FPGA
  repository (github.com/omarelhedaby/CNN-FPGA), raw blob at master; no DOI, no publisher".
- File version: `_litkb_staging/filed/Abdulkader_2020_cnn-fpga-implementation-hardware.pdf`, md5
  `4bb523d01a07959ea9dadcc03c606692`, 62 pages, `has_text_layer` false, text extract at
  `_litkb_staging/filed/Abdulkader_2020_cnn-fpga-implementation-hardware.txt`. Recomputed from
  disk: md5 matches; sha256 is
  `7bdd142ad01fddd031d48af615dada6d01e1edfea6d8c792aaaf8e5449fb23e4` (no sha256 in the row to
  compare against).
- Snapshot named by the checks,
  `_litkb_staging/web/Abdulkader_2020_cnn-fpga-implementation-hardware.txt` (216 bytes), read: it
  is the title-page text used for binding, not an HTML page capture. This admission predates the S3
  HTML-snapshot mechanism, so there is no `.snapshot.json` sidecar beside it; the bytes retrieved
  were the PDF itself, not HTML.
- Document itself (the bound text extract, 10,095 lines, read-only): title page "CNN / FPGA /
  Implementation / Hardware Documentation — A Logic Design Project By: Ahmed Abdulkader, Daniel
  Eskandar, Omar Essam, Omar Tarek, Ahmed Ezzat" with five student numbers; then the project
  abstract ("implement a convolutional neural network on an FPGA using Verilog"), contents, the
  overview section and the five individual member reports (Convolution, Tanh, SoftMax, Average
  Pooling, Integration).
- What matched: the work title is the title page verbatim; the five author families in the record
  are the five names on the title page. The file is the complete 62-page documentation, not a
  landing page or a repository index.
- Year: **not printed anywhere in the document** — `grep` for "2020" over the full extract returns
  0 hits, and there is no semester, date or institution line. The recorded year 2020 rests solely
  on the PDF's own embedded `CreationDate` (Mon Jun 8 21:27:09 2020, in the file version's
  `pdf_metadata`). That is the document's own metadata and nothing contradicts it, but it is a
  weaker basis than a printed date and is recorded here as such.
- Host: `raw.githubusercontent.com` serving the blob committed to
  `github.com/omarelhedaby/CNN-FPGA` — the repository of the project the document documents. Grey
  literature with no publisher and no DOI; the project's own repository is its only distribution
  point. Not an aggregator (no third-party index or re-host), not a search page, and the URL
  resolves to the PDF's bytes directly. The owner handle `omarelhedaby` matches no recorded author
  family, but the title-page names are two-token Arabic name chains whose second token is likely a
  patronymic rather than a family name, so the handle is uninformative rather than contradictory.
  No evidence of a third-party re-host was found.
- Duplicate check at review time: `litkb.main_works` held no work with this key and no title
  matching "FPGA"; `litkb.main_identifiers` held no CNN-FPGA value.

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0ad55-eb8d-7037-b37c-5a431107074a", "entity": "work", "version": "01a0ad55-eb93-759d-b29a-281812978890"},
  {"id": "01a0ad55-eba6-7895-80ef-4b182bc889b4", "entity": "identifier", "version": "01a0ad55-ebac-751c-a13f-c83dd08c3bb1"},
  {"id": "01a0ad55-ebb2-7cf4-8b7d-7f4122466864", "entity": "file", "version": "01a0ad55-ebba-79a9-9f05-e25f327ed7ea"}
]
```

---

## What approval did to the rows

Both approvals moved their versions straight to `promoted`, and both works now read out of
`litkb.main_works`. That is what `litkb.approve_admission` does for a manual admission — approval
is the promotion for this path, not a step before one.

## Noted, not blocking

Two metadata-quality defects in the approved records. Neither is an identity error — each names the
person on the title page — so neither blocks the gate, which asks whether the record is the
document and whether the document is the work.

- `Riva_2017_…`: the second author's family is stored as `Boeuf`; the title page reads
  "Patrick Le Boeuf". The surname particle was dropped.
- Both records: every author's `given` is the empty string, so the title-page given names (Pat,
  Patrick, Maja; Ahmed, Daniel, Omar, Omar, Ahmed) are not in the database. For
  `Abdulkader_2020_…` the stored families (Essam, Tarek, Ezzat, Eskandar) are more likely
  patronymics than family names.

## What I did NOT do

- Did not touch the 13 remaining `proposed` admissions (tracker-era manual proposals in workstreams
  `p3-migration` / `edge-pre1990`). They wait on Kam. The count was 13 before this session's two
  approvals and 13 after.
- Did not refuse anything; there is no REFUSED and no DB-REFUSED row. The database accepted both
  approvals — my session label `s3-approve-1` differs from both admitter sessions
  (`session_015MUcyGTfX2koRdYAjW5kED`, `hunt-one-shot-20260916`).
- Did not hunt, admit, acquire, extract, ingest or record any use.
- Did not edit code, run migrations, or run `check.py`.
- Did not write, move, rename or delete anything under `D:\edmonds-pipeline\Literture\` — every
  file there was opened read-only.
- Did not fetch either source URL over the network. Host and provenance were judged from the
  recorded URL and the bound document, not from a live retrieval.
- Did not open, read or print `.litkb-workstream`.
- Did not commit, merge, push, vault or delete anything.
- Did not touch any other workstream's rows beyond reading them; the only writes were the two
  `approve` calls.
