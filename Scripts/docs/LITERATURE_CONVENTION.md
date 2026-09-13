# LITERATURE_CONVENTION — file names and manifest for the literature store

**Why this file exists.** On 2026-09-12, 149 PDFs were lost in one day to an
unidentified delete issued from a shell against the literature folders; the `.txt`
extracts survived and every lost PDF was re-acquired by DOI. That is the reason for
every rule below, not a style preference. This doc describes the CONVENTION — naming,
manifest schema, acquisition rules. It never restates which papers exist or what they
found; that lives in `Reports/LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md` and
the topic's own `manifest.csv` (one fact, one home).

## Location

`D:\edmonds-pipeline\Literture\<Topic>\` — flat per topic, currently `Validation`,
`ASPP`, `Labeling`, `other`. This tree is **outside git** and **not backed up**. The
`.txt` extract is the durable copy and is written the moment a PDF lands — never defer
the extract to a later pass.

## File name: `Surname_Year_slug.ext`

- **Surname** — first author only, ASCII, multi-part names joined without spaces or
  punctuation (`ONeilDunne`, `VanDenHout`).
- **Year** — 4 digits. An `a`/`b` suffix is used ONLY to break a same-surname,
  same-year collision (`Smith_2019a_…`, `Smith_2019b_…`) — never as a versioning
  convention.
- **slug** — 2 to 5 lowercase title words, hyphen-joined, stopwords dropped, no venue
  name, no DOI fragment.
- **ext** — one stem, three possible extensions, all present when the paper is fully
  processed:
  - `.pdf` — the source
  - `.txt` — `pdftotext -layout` extract
  - `.raw.txt` — `pdftotext -raw` extract, for two-column papers where `-layout`
    scrambles column order
- Whole name: no spaces, no unicode, under 60 characters.

Examples: `Galerne_2011_perimeter-covariogram`, `Zhu_2008_spatiotemporal-autologistic-mcml`,
`ONeilDunne_2014_production-canopy-mapping`.

## `manifest.csv` — the machine-readable authority

One file per topic folder, one row per stem. The manifest is authoritative; the
filename is a label for humans, not a parser target.

| column | meaning |
|---|---|
| `stem` | the filename stem (no extension) — join key to the files on disk |
| `title` | full paper title |
| `authors` | all authors, as printed |
| `year` | publication year |
| `venue` | journal / conference |
| `doi` | DOI if known |
| `arxiv` | arXiv id if known |
| `source_route` | how it was obtained — see acquisition order below |
| `obtained_date` | date the file landed in the folder |
| `sha256` | checksum of the `.pdf` at acquisition time |
| `verified_against_extract` | `yes` / `no` / `loose` — see verification rule below |
| `cited_by` | report filenames that cite this stem |

## Rules (learned 2026-09-12)

1. **No delete permission.** Acquisition agents never get delete permission in these
   folders. This is the direct fix for the loss above — a re-acquisition can replace a
   missing file, but nothing should be able to remove one in the first place.
2. **Verify by content, never by filename.** Every file is verified against its own
   `.txt` extract or the Crossref-returned title — a filename matching what was
   requested is not evidence the content matches. Record the outcome in
   `verified_against_extract`.
3. **Acquisition route order:** open access first; then Sci-Hub, first mirror index,
   by `curl`; then Sci-Hub, second mirror index, by `curl`; a browser session is the
   LAST resort, and browser-capable agents run **one at a time** — never two browser
   sessions against these folders concurrently.

## Legacy stems

Stems written between 2026-08 and 2026-09-12 predate this convention. The rename
mapping from legacy stem to convention stem lives in
`Reports/lit_stem_rename_map.csv` once the rename pass runs; that file does not exist
yet.
