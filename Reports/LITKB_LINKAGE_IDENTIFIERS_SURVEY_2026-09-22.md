# litkb — shadow-library record linkage and identifier coverage, survey round 3 (2026-09-22)

**What this is.** Kam's ask of 2026-09-22 ("review all the GitHub pages that use libraries like Anna's Archive,
LibGen, Sci-Hub and other alternative libraries … how these repos handle these libraries and link records
between them … how we can maximize identifier coverage so we can jump through different PDF providers … update
the plan"). It extends `Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md` (rounds 1 and 2) and is the record the
plan's S4.5 item 1 (registry identity), Stage A, Stage B and S4.6 Stages F and G cite. Every mechanism below is a
DESIGN read in someone else's code (CLAUDE.md §3.4c); nothing has run on litkb's rows except the probes named
in this header, and no rung counts until an agent that did not propose it re-runs it on the named rows.

**How it was made.** Workflow `wf_a95fe3dd-5d3` (40 min): six Opus crawlers — S1 clients of Anna's Archive plus
the local fetch script under D:\tools\annas-mcp read without its key · S2 LibGen clients and data model · S3 Sci-Hub
clients, successors and the coverage datasets · S4 the other alternative libraries and the Open Library, Internet
Archive, HathiTrust and Google Books hubs · S5 the identifier crosswalk services and the native-key table · S6 the
codebases that accumulate and canonicalise identifiers — each holding the round-2 blacklist, plus one Codex
attempt that DIED on quota for the third consecutive round (its file is a failure record; the Codex GitHub pass
stays owed). The synthesizer merged the six into the body below; `blacklist-round3.txt` (2,961 lines) is the
union of every URL visited. Worker reports: `D:\tools\claude-config\jobs\litkb-acquisition-survey\`.

## M. Measured on litkb's rows, this round

| measurement | result | who |
|---|---|---|
| identifier crosswalk yield, every DOI-bearing work in main asked at OpenAlex, Semantic Scholar and Crossref (`qc/instruments/litkb_acq_probe_crosswalk.py` → `phase4/qc/litkb_acq_probe_crosswalk.csv`) | OpenAlex id for every work; a Semantic Scholar corpus id for most; an arXiv id for 71 works (the table holds six); a PMID for 67; a PMCID for 36, ALL from Semantic Scholar and none from OpenAlex; an ISBN for 12; Crossref `relation` on 22 works (ten `has-preprint`); Crossref answers 404 for 32 DOIs | orchestrator |
| the same joined to the file table: works with NO active file today (222 of 466) | an arXiv id for 36, a PMID for 38, a PMCID for 24, an ISBN for 8, a `relation` edge for 11, a Crossref `link[]` for 200; eight unknown to Crossref | orchestrator |
| Crossref `alternative-id` for the corpus's Elsevier (10.1016) DOIs | 92 Elsevier DOIs; an Elsevier PII carried for 90 of them — the native key of the corpus's largest closed publisher, fetched on every hunt and discarded | crawler S5, from the probe CSV and live Crossref |
| litkb's own identifier table | the schemes doi, arxiv, jstor, isbn, pmid, pmcid, openalex, s2, handle, url, tracker, legacy_stem are admitted; doi, arxiv, url and tracker are populated; pmid, pmcid, openalex, s2, isbn, handle and jstor are EMPTY (`SELECT scheme, count(*) FROM litkb.main_identifiers GROUP BY 1`) | orchestrator |
| litkb's own Anna's fetch script (D:\tools\annas-mcp\aa_fetch.py, read without its key) | fetches the record's `identifiers_unified` dictionary (about 120 schemes) at its second gate and parses ONE key out of it, `doi` | crawler S1 |

**The bottom line the orchestrator carries into the plan.** This round adds no new PDF source; its value is
that it makes the sources already on the ladder ADDRESSABLE and turns three miss labels into measurable
distinctions. The largest free items need no ruling: harvest the Anna's identifier dictionary wholesale, read the
`alternative-id`, `ids` and `externalIds` fields from three calls litkb already makes, derive the `10.48550` DOI
for every arXiv id as a candidate until DataCite confirms it, and import the public, hash-pinned Sci-Hub DOI list
and LibGen article table from GitHub so a blocked row can be told from an out-of-corpus one before any mirror is
spent. The external coverage decomposition (body §5.1, a 2018 study of 290,120 articles) says 95 percent needs
at least two of the open-access ladder, the shadow tier and institutional access; no identifier changes that
arithmetic. Disagreements the synthesis records (body §6) are carried, not resolved, here.

---

# Shadow-library record linkage and identifier coverage — survey round 3 (2026-09-22)

**What this is.** The round-3 synthesis for the two questions Kam asked on 2026-09-22: (1) how the
GitHub codebases that use Anna's Archive, LibGen, Sci-Hub, Z-Library, Nexus/STC and the other
alternative libraries **key their lookups and link records between those libraries**, and (2) how to
**maximise identifier coverage** for a work so every PDF provider can be asked by the key *it* takes.
It merges six Opus crawler reports (S1–S6, 492 URLs) and records the one Codex agent that did not run.
It is a companion to `Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md` (rounds 1+2, 125 rungs) and
changes specific rungs of that ladder rather than replacing it.

**Every rung and every model below is a DESIGN read in someone else's code** (CLAUDE.md §3.4c).
Nothing here has run on litkb's rows except the orchestrator's own read-only probes, which are named
where they are used and which are the only MEASURED numbers about this corpus in this file.

**Reports read.**

| report | URLs | state |
|---|---:|---|
| `S1-annas-clients.md` | 90 | complete |
| `S2-libgen-clients.md` | 97 | complete |
| `S3-scihub-clients.md` | 66 | complete |
| `S4-other-alt-libraries.md` | 72 | complete |
| `S5-crosswalk-services.md` | 68 | complete |
| `S6-crosswalk-codebases.md` | 99 | complete |
| `C3-codex-shadow-linkage.md` | 0 | **FAILURE RECORD, not findings** — Codex quota exhausted (`ERROR: You've hit your usage limit… try again at 9:13 AM`), codex-cli 0.155.1, model gpt-6-astra, session `01a0c964-2ebe-7a22-bfcc-8c169817d660`. No survey run. This is the **third consecutive round** in which the Codex GitHub pass has died on quota (R2C-github-acquisition, R2C-github-ocr, C3). The owed pass is still owed. |

Two invocation facts C3 adds for the next dispatcher, worth keeping because they are cheap and were
paid for: `codex exec` 0.155.1 has **no `--search` flag** — web search is the config key
`-c tools.web_search=true`; and `-C /mnt/d/tools/claude-config/jobs/…` died with
`Error: No such file or directory (os error 2)` *before reaching the model* while `-C /tmp` reached it,
so the D: mount as a workdir is an unresolved blocker distinct from the `-C` bug round 2 already found.

Blacklist for round 4: `blacklist-round3.txt` — the union of `blacklist-round2.txt` (2,505 lines) and
the 492 round-3 URLs, deduplicated and sorted: **2,961 lines**.

---

## 0. The two questions and the one-query gap (litkb's empty identifier schemes)

### 0.1 The answer to question 1, in one sentence

**These codebases do not link *library to library*; they link *identifier to identifier*, and the file
hash is the pivot.** Anna's Archive's own application code states it structurally: every upstream
library gets one ingest module under `allthethings/page/sources/`, each module calls
`add_identifier_unified(record, scheme, value)` into a per-record
`identifiers_unified: dict[str, list[str]]`, and records then merge **by shared `(scheme, value)` code**
through per-source `aarecords_codes_<source>_for_lookup` tables — never by a pairwise
Z-Library↔LibGen mapping (S4 §2.3, `henrylzl/annas-archive@7a261075`). Every independent client read
this round converges on the same pivot in different words: biblio-mcp says it verbatim in `types.ts`
(*"`md5` is the universal join key across sources"*); libgen-mcp routes one `Item{MD5, DOI, ISBN}`
through a chain where **each source declares the key it supports**; doi-fetch uses Anna's purely as an
md5 oracle and then logs `MD5=… (use LibGen to download)`.

**DOI is the universal WORK key, md5 is the universal FILE key, and ISBN-13 is the book-side entry
key.** That is S3's formulation and it is the load-bearing sentence of this round.

### 0.2 The answer to question 2, in one sentence

**The crosswalk litkb needs mostly already arrives in calls litkb already makes and discards.** Two of
the three richest keyless calls (Crossref, OpenAlex) are already in litkb's hunt; the Anna's
`aarecord` litkb fetches at gate 2 carries up to ~120 identifier schemes and litkb parses exactly one
key out of it. Verified on disk: `D:\tools\annas-mcp\aa_fetch.py:611` reads
`identifiers_unified.doi` and `:615` reads `extension_best`, and nothing else from that dict.

### 0.3 The gap itself, verified in litkb's own schema

`Scripts/pipeline/litkb/db/migrations/0001_core.sql:118`:

```sql
scheme text NOT NULL CHECK (scheme IN ('doi','arxiv','jstor','isbn','pmid','pmcid',
                                       'openalex','s2','handle','url','tracker','legacy_stem')),
```

`0001_core.sql:128` — the partial unique index `identifiers_active_scheme_value ON identifiers
(scheme, value_norm) WHERE active`. `0001_core.sql:137` — `verified_by text CHECK (verified_by IN
('crossref','datacite','arxiv','s2','manual'))`. `0003_write_functions.sql:11-20` —
`norm_identifier` normalises **only** `doi` (lowercase, prefix-strip) and `arxiv` (lowercase,
`arxiv:` strip, `v\d+$` strip); every other scheme falls through to `btrim`.
`0013_admission.sql:328` and `0014_referee_p2_fixes.sql:253` both gate identity on
`scheme IN ('doi','arxiv','isbn','pmid','pmcid','jstor','handle')`.

So: **the identity plumbing for `pmid`, `pmcid`, `isbn`, `handle` and `jstor` is BUILT AND UNFED.**
Populating them is a data problem. Four other schemes do not exist at all and each has a named
consumer on litkb's own ladder (§3.1).

### 0.4 What the orchestrator's probe already measured on litkb's rows

`Scripts/qc/instruments/litkb_acq_probe_crosswalk.py` → `phase4/qc/litkb_acq_probe_crosswalk.csv`,
**466 rows** (every DOI-bearing work in main), one OpenAlex + one Semantic Scholar + one Crossref call
each. Recomputed from the CSV for this synthesis:

| field | works filled | note |
|---|---:|---|
| `doi` | 466 | the input |
| `openalex` | **466 (100 %)** | OpenAlex answered 200 for every work |
| `mag` | 302 | derived from the W-id's numeric tail, not independent (S5 §1.1) |
| `issn_l` | 423 | |
| `s2_corpus` | 416 | S2 404 for 48, 504 for 1, 400 for 1 |
| `pmid` (OpenAlex ∪ S2) | **68** | OpenAlex 67, S2 66 |
| `pmcid` (OpenAlex ∪ S2) | **36** | OpenAlex returned **0**; all 36 came from Semantic Scholar |
| `s2_arxiv` | **71** | |
| `s2_dblp` | 158 | |
| `cr_isbn` | **12** | the entire book/chapter namespace in this corpus |
| `cr_alt_id` | 289 | of which the first token is **PII-shaped (`S\d{4}…`) for 96** |
| `cr_relation_types` | 22 | `has-preprint` 10, `has-review` 5, `is-part-of` 5, `is-referenced-by` 3, `correction` 2, `has-version` 2, `is-version-of` 2, `references` 1, `is-preprint-of` 1 |
| `cr_has_link` | 407 | |
| Crossref status | 200 for 434, **404 for 32** | DataCite or another agency |
| Crossref type | journal-article 382, proceedings-article 32, **book-chapter 11**, posted-content 8, **book 1**, unknown 32 | |

**And the single sharpest number of this round, computed here for the first time: the corpus holds
92 Elsevier (`10.1016`) DOIs, and Crossref carries an Elsevier PII in `alternative-id` for 90 of
them (97.8 %).** litkb fetches that field on every hunt and throws it away.

Section M's joined figures stand: of the 222 works with **no active file**, the fan-out adds an arXiv
id for 36, a PMID for 38, a PMCID for 24, an ISBN for 8, a `relation` edge for 11 and a Crossref
`link[]` for 200.

**S6 flagged two untracked files under the project as "not mine" — `Scripts/qc/instruments/litkb_acq_probe_crosswalk.py`
and `phase4/qc/litkb_acq_probe_crosswalk.csv`. They are the orchestrator's round-3 probe, cited in the
survey's §M. Resolved; no agent wrote outside its grant.**

---

## 1. The shadow-library LINKAGE MAP

**21 libraries / layers.** "Native key" is what the library is addressed *by*. "Join keys out" is what
a record from it hands you that addresses a *different* library. VERIFIED = read as source at a pinned
sha or observed in a committed fixture; ASSERTED = repo metadata, README or prose only. **No request
was sent to any shadow-library host in any of the six crawls.**

### 1.1 The map

| # | Library / layer | Native key(s) | Record fields | Join keys OUT | Block vs miss | Offline coverage check | Grade | Crawler |
|---:|---|---|---|---|---|---|---|---|
| 1 | **Anna's Archive** (`aarecord`) | md5 (primary); DOI via `/scidb/`; **any of ~120 schemes via `/search?q=<scheme>:<value>`**; `/codes?prefix_b64=` | `file_unified_data.{identifiers_unified, classifications_unified, extension_best, filesize_best, title_best, author_best, content_type_best, ipfs_infos, has_scidb, has_torrent_paths}`; `additional.{download_urls, ipfs_urls, torrent_paths, partner_url_paths, scidb_info}`; `source_records[]` grouped by `source_type` | **this IS the crosswalk**: md5, header_md5, sha1, sha256, crc32, doi, isbn10, isbn13, issn, ean13, csbn, oclc, oclc_library, ol, openlib_source_record, lccn, gbooks, gbooks_other, asin, goodreads, **pmid, pmcid, jstorstableid**, pii, isni, hathi, nexusstc, zlib, lgrsnf, lgrsfic, lgli (+8 repo ids), edsebk, magzdb, motw, duxiu_ssid/dxid, cadal_ssno, ipfs_cid, aacid, filepath, server_path | **`<title>`/header/`check=1` test, three detectors ranked in §1.4.** A `/scidb` 302 is **five conditions, only one of which is absence** (§1.3) | **`aa_derived_mirror_metadata_<date>.torrent`** — three independent local-DB implementations (§1.6) | VERIFIED (as this mirror states) | S1, S4 |
| 2 | **LibGen.li** (`json.php` generation) | `object=e&doi=`, `object=f&md5=`, `object=e\|f&ids=`; HTML `index.php?req=&columns[]=d\|i\|t\|a\|s\|p\|y` | edition `{title, author, publisher, year, pages, doi, type, libgen_topic, issue_*, files{f_id, md5}}`; file `{md5, extension, filesize, locator, ocr, libgen_id, fiction_id, comics_id, scimag_id, standarts_id, magz_id, scimag_archive_path, add{}, editions{e_id}}` | **`add{}` bag**: IPFS CID, BTIH, SHA1, SHA256, CRC32, eDonkey, AICH, TTH, and **`Library="zlib"` + `value_add1` = the Z-Library id**; the `*_id` fields are intra-LibGen collection joins | **miss = body `[]`** (not a status). `ads.php` miss = body `"File not found in DB"`. Search miss = `"no records found"` / `"0 files found"`. Transport: 5xx/429/timeout transient, other 4xx permanent | LibGen SQL dumps (§1.6) | VERIFIED (`jmrplens/libgen-mcp@12d8a56e` + its committed server-response fixtures) | S2 |
| 3 | **LibGen.rs / .is / .st** (classic + dumps) | `search.php?req=&column=identifier\|def\|title\|author`; `json.php?fields=…&timenewer=&idnewer=&mode=newer`; the three SQL dumps | `updated` (non-fiction): Identifier (ISBN list), IdentifierWODash, ISSN, ASIN, UDC, LBC, DDC, LCC, Doi, **Googlebookid, OpenLibraryID**, MD5, Locator, Coverurl, Tags. `scimag`: DOI, DOI2, ISBN, ISSNP, ISSNE, MD5, JOURNALID, AbstractURL, **PubmedID, PMC, PII**, Attribute1-6. `fiction`: MD5, Identifier, GooglebookID, ASIN. `hashes`: MD5 → ipfs_cid | Open Library id, Google Books id, ASIN, DDC/LCC/UDC/LBC, **PMID, PMCID, PII**, ISSN print + electronic, IPFS CID | no miss discrimination in the sync client; the dump is offline so there is no miss | **Yes — this is the strongest offline table in the class.** Column census over **64,195,945 scimag rows**: DOI 100 %, MD5 100 %, ISSNP 81.4 %, ISSNE 45.9 %, PubmedID 12.87 % (8.26 M), PII 7.60 % (4.88 M), ISBN 6.35 %, PMC 2.36 % (1.52 M); Journal name only 55.4 % | VERIFIED (`libgenapps/LibgenDesktop@f74e224a`, 2020; census from `greenelab/scihub@b49f7b0`, 2017-04-07 dump) | S2, S3 |
| 4 | **Sci-Hub** | **lowercased DOI** | HTML page; `citation_pdf_url` meta, then `embed\|iframe src`; `citation_title/author/journal_title` — free bibliographic metadata for works Crossref has no record of | **none — a Sci-Hub hit has NO md5.** This is the whole reason the class needs LibGen or Anna's as a second hop | **Positive miss marker**: literal body string `Unfortunately, Sci-Hub doesn't have the requested document`. A challenge is Altcha, intermittent by *time* not rate. **A concurrent probe manufactures false "unavailable"** (§1.5) | **Yes — Sci-Hub's own published DOI list**, `dois.2020.07.29.sorted.clean.txt.xz`, git-LFS **on GitHub**, 71,698,648 B, `sha256 ae1c76aa…cedfa04`, **82,470,219 DOIs**. Earlier list 2017-03-19, 62,835,101 DOIs | VERIFIED (list = pointer + README; blob not fetched) | S3 |
| 5 | **sci.bban.top** | `pdf/<doi>.pdf` | bytes only | none | 404 | — | VERIFIED as a route; **case handling CONTESTED** (§6) | S2, S3 |
| 6 | **Nexus / STC** (`nexus_science`) | `id.dois` term query (DOI lowercased); aliases `doi: isbn: issn: pmid: cid: extension: rd:` | `id{dois[], libgen_ids[], zlibrary_ids[], pubmed_id, ark_ids, internal_iso, internal_bs, nexus_id}`; `metadata{isbns, parent_isbns, issns, container_title, publisher, series}`; **`links[]{cid, md5, extension, filesize, type}`**; `content` (GROBID/EPUB HTML); `references[].doi`; Crossref `type` | **the richest single join in the class — DOI ↔ LibGen id ↔ Z-Library id ↔ PMID ↔ ISBN ↔ ISSN ↔ md5 ↔ IPFS CID in ONE document** | three outcomes: absent; present with `links[]`; **present with NO `links[]` (metadata-only)**. `exists: content` separates indexed from has-bytes | via Anna's `aac_nexusstc` ingest (which is live even when STC's transport is not) | VERIFIED (schema `nexus-stc/stc@f65119df:search/nexus-science.yaml` + committed notebook outputs); **transport disputed** | S3, S4 |
| 7 | **Z-Library** (eAPI) | **`(bookid, hash)` pair.** Search takes **free text only** — no ISBN, DOI or hash parameter exists | `/eapi/book/search` (POST `{message, yearFrom, yearTo, languages, extensions[], order, page, limit}`); `/eapi/book/{id}/{hash}[/formats\|/file]`; `file{downloadLink, description, author, extension}`; `/eapi/user/profile{downloads_limit, downloads_today}` | **none natively.** zlib ids arrive only from Anna's (`zlib` scheme) or Nexus/STC (`id.zlibrary_ids`) or LibGen (`add{}` `Library="zlib"`) | **DiamWall: a walled host answers `/eapi/` with a non-JSON body at HTTP 513** — health decided on `content-type` + `success`, **never on status** | via Anna's zlib ingest: `zlibrary_id, md5, md5_reported, isbns[], ipfs_cid, ipfs_cid_blake2b, storage, **in_libgen**, pilimi_torrent` | VERIFIED (`hoanganhduc/getscipapers@f0337174`, 419-line client) | S4 |
| 8 | **Internet Archive** | `ocaid` | `metadata{isbn[], lccn, oclc-id, openlibrary_edition, openlibrary_work, external-identifier[], access-restricted-item, collection[]}`; `files[]{name, format, size, private}` incl. `{ocaid}.pdf`, **`{ocaid}_djvu.txt`**, `{ocaid}_encrypted.pdf` | `urn:libgen:…/<md5>` → **a LibGen md5 inside a fully legitimate keyless API**; `urn:oclc:record:<n>`, `urn:oclc:<n>`, `urn:isbn:`, `urn:acs6:`, `urn:lcp:`; `openlibrary_edition` → OLID | not a shadow host; the open/CDL boundary is `access-restricted-item` + `collection` containing `printdisabled`/`inlibrary` + `urn:lcp:` | OL and IA bulk dumps (§1.6) | VERIFIED | S1, S4, S5 |
| 9 | **Open Library** | **ISBN, OCLC, LCCN, OLID — four native keys at one endpoint** (`/api/books?bibkeys=<TYPE>:<num>`); `/isbn/{isbn}.json`; `/search.json?fields=…` | `edition_key[]`, `ia[]`, `isbn[]` (all 10- and 13-forms across every edition), `lccn[]`, `oclc[]`, `id_goodreads[]`, `identifiers{}`, `classifications{}`, `source_records[]` (`"amazon:0849370809"` = ASIN), `availability{identifier,status,is_restricted}`, `ebook_access`, `public_scan_b` | isbn ↔ olid ↔ ocaid ↔ lccn ↔ oclc in ONE keyless call; **`OPENLIB_TO_UNIFIED_IDENTIFIERS_MAPPING["annas_archive"] = "md5"` — an OL edition can name an Anna's md5 directly** | not a shadow host | `ol_dump_editions_latest.txt.gz` + `archive.org/download/ia-abc-historical-data/<YYYYMMDD>_inlibrary_direct.tsv` | VERIFIED (live responses, S5 §2.8) | S1, S4, S5 |
| 10 | **HathiTrust** | `catalog/api/volumes/brief/<TYPE>/<num>.json` with **the same four TYPEs** {ISBN, OCLC, LCCN, OLID}; `htid` | `items[]{usRightsString, itemURL, fromRecord}`; hathifiles columns `access, rights, ht_bib_key, source, source_bib_num, rights_reason_code, **us_gov_doc_flag**, pub_place, bib_fmt, collection_code, content_provider_code, responsible_entity_code, digitization_agent_code, access_profile_code` | htid ↔ ISBN ↔ ISSN ↔ LCCN ↔ OCLC; `fromRecord` = `ht_bib_key` | not a shadow host; `access_profile_code ∈ {open, google, page}` is the download gate; only `usRightsString == "Full view"` counts | hathifiles | VERIFIED | S4, S5 |
| 11 | **Google Books** | volume id; queried by ISBN | `industryIdentifiers[]` typed `ISBN_10 / ISBN_13 / ISSN / OTHER`, where `OTHER` is `<PREFIX>:<value>` | **`OCLC:` → oclc (42,399,475 in Anna's in-code census), `LCCN:` → lccn (1,528,733), `LOC:` 44,158** — a free ISBN→OCLC→LCCN bridge dominated by OCLC | not a shadow host; an unknown `type` **raises** in Anna's ingest | via Anna's `aac_gbooks` | VERIFIED as a **crosswalk**; still no PDF logic anywhere (round 2's F5 negative stands) | S4 |
| 12 | **WorldCat / OCLC** | `oclc_id`; old Search API `/oclc/<num>` + key → MARCXML | Anna's OCLC record carries OpenURL `rft.isbn, rft.issn, rft.eissn, rft.pub, rft.date, rft.edition, rft.place, rft_dat{stdrt1,stdrt2}`, **a `doi` field**, holdings counts | **OCLC is the one BOOK identifier that carries a DOI** — it bridges the book path back to the paper path | keyed, institution-gated | via Anna's `oclc` dataset | MIXED. **OCLC Classify is DEAD** (zero GitHub code hits for `classify.oclc.org` / `classify2.oclc.org`, consistent with its 2024 retirement); WorldCat Search v2 keyed | S4, S5, S6 |
| 13 | **Memory of the World** | `motw_id`, **only through Anna's** — MotW itself has no query URL in any codebase found | Calibre-shaped `{title, authors[], publisher, pubdate, series, description, languages[], librarian, formats[].url, identifiers[{scheme, code}]}` | in-code scheme census: isbn 138,771; oclc-owi 83,393; amazon 82,362; lccn 78,251; google 77,875; isni 68,839; oclc 11,843; goodreads 3,298. **Anna's maps only isbn/asin/oclc/gbooks/lccn and SILENTLY DROPS isni, viaf_author_id, oclc-owi, lc_authority_name** | — | a direct MotW Calibre dump would carry *more* than Anna's exposes; `marcellmars/letssharebooks` located, not read | MIXED | S4 |
| 14 | **fatcat (IA Scholar)** | 14 per-scheme lookup columns | `ext_ids{doi, wikidata_qid, isbn13, pmid, pmcid, core, arxiv (vN required), jstor, ark, mag (empty since 2021), doaj, dblp, oai, hdl}`; `work_id`; `container_id` (ISSN-L); file entities `{md5, sha1, sha256, mimetype, content_scope, release_ids[], urls[]{url, rel}}` with `rel ∈ web\|webarchive\|repository\|academicsocial\|publisher\|aggregator\|**dweb** (ipfs://)` | **the richest ext_ids set in the open**, plus a **doi → file-hash → IPFS** edge structurally identical to the shadow tier's | **API is DEAD — `curl` exit 28 / HTTP `000`, measured this session.** Dump-only | identifier-snapshot TSVs in the IA collection `fatcat_snapshots_and_exports` | schema VERIFIED @`8f3f4c6`; API death VERIFIED. **CAVEAT: fatcat's md5 is the hash of the file IA crawled, not the file the shadow libraries hold — a CANDIDATE key, never a guaranteed one** | S5, S6 |
| 15 | **IPFS gateway layer** | IPFS CID | bytes | CIDs tagged by origin (`zlib_ipfs_cid`, `zlib_ipfs_cid_blake2b`, `lgrsnf`, `lgrsfic`) | 20 gateways to walk, not one host: `w3s.link, cf-ipfs.com, ipfs.eth.aragon.network, zerolend.myfilebase.com, ccgateway.infura-ipfs.io, knownorigin.mypinata.cloud, storry.tv, ipfs-stg.fleek.co, cloudflare-ipfs.com, ipfs.io, snapshot.4everland.link, gateway.pinata.cloud, dweb.link, gw3.io, public.w3ipfs.aioz.network, ipfsgw.com, magic.decentralized-content.com, ipfs.raribleuserdata.com, www.gstop-content.com, atomichub-ipfs.com` — all `https://<host>/ipfs/{cid}?filename={name}` | — | VERIFIED | S4 |
| 16 | **Torrent / dump layer** | BTIH (infohash), `server_path`, `path_in_torrent`, `scimag_archive_path` | `TorrentFileData{name, link, infohash, ipfs_cid, size_bytes, type ∈ fiction\|books\|scimag, path, seeders, leechers}` | **`infohash` == the `add{}` BTIH; `ipfs_cid` == the `add{}` IPFS CID** — the torrent layer and the catalog layer join on exactly the identifiers §1's row 2 exposes | — | LibGen.rs publishes its daily dbdumps over `https://ipfs.io/<hash>?filename=` | VERIFIED (`subdavis/libgen-seedtools@628cc4cf`, `rcelha/libgen-dump-rs@dc590a23`, `lgdbdumps@bc190f01`) | S2, S4 |
| 17 | **Sci-Net** | DOI | remote page states `pending \| working \| pdf \| not-found \| logged-out`; local queue states `queued \| requested \| working \| fetched \| approved`; visible token balance | **reports open-access AND Sci-Hub availability and "resolved provider URLs" for a DOI — one query, several providers** | `not-found` is defined as *the page did not match the DOI* — a redirect is not a miss of the work | — | MIXED (`magicalpowerranking894/scinet-queue@e6c71bd`, pushed 2026-09-21; its own doc disclaims being an API contract) | S3 |
| 18 | **Monoskop** | **none** — free-text `?cat=17&s=<query>` on a WordPress log; an ISBN is passed *as the query string* | scraped `title, landing, img_href, desc, href[], isbn[]` (regex-mined from the post body) | ISBN only, and only when the post happens to print one | empty hits on any exception; **bails out entirely if a post has no cover image** | — | VERIFIED **and weak — not worth a rung** | S4 |
| 19 | **Aaaaarg** | `aaaaarg.fail/search?query=` | — | — | — | — | **VERIFIED DEAD — `'selected': 0, 'enabled': 0`, `books: 0, articles: 0` in the only codebase that names it**; every other GitHub hit is prose | S4 |
| 20 | **UbuWeb** | site paths | — | — | — | — | ASSERTED (`lazzarello/ubuweb-mirror` located, not read); no identifier surface expected | S4 |
| 21 | **PDFDrive / OceanofPDF and the file-mill class** | **none** | — | — | — | — | **VERIFIED AS NON-PROVIDERS.** They appear in code only as (a) a `-5.0` domain prior to demote and (b) filename-pollution regexes to strip (`_OceanofPDF.com_Title_-_Author`, `( PDFDrive )`). The same `-5.0` bucket holds `z-lib.org, annas-archive.org, libgen.is, libgen.rs, dokumen.pub, epdf.pub, ebin.pub, pdfcoffee.com, vdoc.pub, idoc.pub, docslib.org` | S4 |

### 1.2 How a client walks a miss in one library into a hit in another — four shipped implementations

1. **`yakeworld/doi-fetch@3ef74ed`** — the canonical walk, four phases on one DOI:
   `sci.bban.top/pdf/<lowercased doi>.pdf` → Sci-Hub frontend (sci-hub.vg iframe) → LibGen
   `index.php?req=<doi>&columns[]=d` → `edition.php?id=` → any `md5=` href → `libgen.li/main/<md5>` →
   `library.lol/main/<md5>` → **Anna's `/scidb/<doi>/` used for md5 DISCOVERY ONLY**. Its
   `phases/annas.py` is four lines of logic and ends `return False  # MD5 found but can't download from AA`,
   logging `MD5=… (use LibGen to download)`. `content[:5] == b"%PDF-"` decides success at every hop.
   **Anna's is the address book; LibGen is the courier.** This is A5's Tier-0/Tier-1 split already in
   production.
2. **`JeremiahM37/librarr@d7f4db91`** — Anna's `fast_download.json?md5=&key=` → on failure, public
   LibGen mirrors (`li, la, bz, gl, vg`) by the same md5 → on `errLibgenNoMatch`, **re-search Anna's by
   TITLE for *alternative* md5s of the same work**, filter with `titlesMatch`, and try each against
   LibGen again. Terminal message: *"Anna's Archive could not find a matching LibGen MD5 for this book."*
   — i.e. **one work legitimately has many files, and a miss on one md5 is not a miss on the work.**
3. **`jmrplens/libgen-mcp@12d8a56e`** — a *declarative* chain over `Item{MD5, DOI, ISBN}` where each
   source declares `Supports()`: `unpaywall, openalex, europepmc, biorxiv, rfc, nist, dagstuhl, acl, …,
   scihub, scidb, libgen, randombook, annas`. `scidb`/`scihub` take DOI, `libgen`/`annas` take md5,
   OAPEN/OpenLibrary take ISBN. This is the shape litkb's ladder should adopt: **a rung declares its
   key, and the router only offers it works that hold that key.**
4. **`francy2222/annas-archive-download-mcp@af149fc`** — DOI → SciDB page → regex `/md5/([0-9a-f]{32})`
   → if absent, `search_fallback` → `libgen.li/ads.php?md5=` → `get.php?md5=&key=`. Its **two-value miss
   vocabulary** is the one litkb must keep distinct: `"DOI not found in Anna's Archive"` vs
   `"LibGen has no copy of MD5 <md5>"` — **only the second is worth a mirror retry.**

**S3's ordering consequence, which reverses the survey's:** an STC record returns md5 **and** CID
**and** libgen_id in one call; LibGen `object=e&doi=` returns only the md5 and then G2a costs a second
call. So the cheapest correct walk is **STC → LibGen scimag → Anna's SciDB**, i.e. **G0b before G0a**
(§4).

### 1.3 A SciDB 302 is not "not in the archive" — the mechanism

`henrylzl/annas-archive@7a261075:allthethings/utils.py:580 scidb_info` returns `None` — sending the
caller to `/search?index=journals&q="doi:…"` — if **any** of five things is true:

```python
if aarecord["indexes"] != ["aarecords_journals"]: return None          # (1) not in the journals index
valid_dois = [d for d in identifiers_unified.get("doi") or [] if not doi_is_isbn(d)]
if len(valid_dois) == 0: return None                                   # (2) the only DOI is an ISBN-A
if file_unified_data["extension_best"] != "pdf": return None           # (3) not a PDF
if (content_type_best != "journal_article") and (scihub_link is None): return None   # (4) book record
if path_info: priority = 1
elif scihub_link: priority = 2
elif ipfs_url:   priority = 3
else: return None                                                      # (5) no partner path / scihub row / IPFS
```

**Only condition (5), and only partly, is absence.** litkb's `aa_fetch.py` gate 1 books a `Location`
starting `/search` as `not-in-archive` — a status name that overstates what was measured. **The 33 rows
counted under it in the survey's §M must be re-read.** A better name: `scidb-no-servable-journal-record`.

### 1.4 Challenge detection — three detectors, ranked, and litkb has the weakest

| rank | detector | source | why |
|---:|---|---|---|
| 1 | **`status === 403 && /ddos-guard/i.test(headers.get("server"))`, OR a 3xx whose `Location` contains `check=1`** | `bitesized/annas-archive-api@2485c61` `lib/annas.js::isChallenge` | cheapest and most specific; its own comment: *"A challenge shows up two ways: a 403 straight from DDoS-Guard, or a redirect to the same path with `check=1`. The latter is what an expired session gets, and following it loops until fetch dies with 'redirect count exceeded' — so we drive redirects manually and name the condition instead."* |
| 2 | `<title> == "DDoS-Guard"` | round 2's G0d rule | correct, but costs the body |
| 3 | body regex | litkb `aa_fetch.py:107` `CHALLENGE_RE = rb"Just a moment\|DDoS-Guard\|Checking your browser"`, applied at `:172-173` **only on 403/503** | guarded, so it will not misfire on a solved record page — but **litkb's `resolve()` runs with redirects DISABLED, so a challenge arriving as a `check=1` redirect currently reads as a benign hop** |

**And the wall is path-dependent by design.** `dyn/views.py` serves `/dyn/md5/summary/` and
`/dyn/md5/inline_info/` as `Content-Type: text/css` with the source comment
`# "text/css" for DDOS-GUARD caching.` `/search` and `/md5/` are challenged; `/dyn/*` is not.

**"Health on body, never on status" now has four independent instances** and should be one guard with a
per-host marker table, not four rung footnotes: LibGen's nginx-default-page-at-200; Anna's DDoS-Guard;
Z-Library's DiamWall non-JSON at HTTP 513; `codegod100/eve@59fcb32` treating any body beginning `<` as
blocked on a JSON endpoint.

### 1.5 A shadow-tier "miss" is not a measurement — two distinct false-negative mechanisms

- **Concurrency (NEW this round).** `materialcritic/doi-extension@e4007a8` `background.js` carries its
  own observed rationale: *"Running several at once … makes the mirrors flaky and causes false
  'unavailable' results, so we run checks one at a time"* and *"observed live: a check for a DOI
  reported 'unavailable' 20s after that exact DOI had just downloaded successfully via Sci-Hub."*
  Implemented as a serialised `checkQueue` (one in flight) plus `RECENT_DOWNLOAD_GUARD_MS = 5 * 60 * 1000`
  — a five-minute window in which a contradicting "unavailable" is **discarded**.
  **Rule for litkb: never record a shadow-tier miss from a concurrent probe.**
- **Challenge intermittency** (round 1's Altcha finding) — unchanged.

### 1.6 The zero-network tier — coverage answered offline, at zero shadow requests

| artefact | what it answers | host | grade |
|---|---|---|---|
| `dois.2020.07.29.sorted.clean.txt.xz` (71,698,648 B, `sha256 ae1c76aa…cedfa04`, 82,470,219 DOIs) | **is this DOI in Sci-Hub** | **GitHub** (`greenelab/scihub@b49f7b0`, git-LFS) | VERIFIED (pointer + README) |
| `libgen-scimag-date-added-2017-04-07.tsv.xz` (187,959,588 B) | **is this DOI in LibGen scimag** | **GitHub**, same repo | VERIFIED |
| the scimag SQL dump extract | DOI→MD5 (100 %), DOI→PMID/PMCID/PII/ISSN | **figshare `10.6084/m9.figshare.5231245`** — a non-shadow route litkb could admit through its own normal ladder | VERIFIED |
| `aa_derived_mirror_metadata_<date>.torrent` | DOI→md5, ISBN→md5, OCLC→md5, md5→torrent path, md5→CID | torrent | VERIFIED, **three independent implementations**: `iziplay/anna-api@fe3be82` (Postgres `RecordIdentifier{Record,Type,Value}`, indexed `(type,value)`), `jasperweiss/alexandria@53dded3` (SQLite `record_isbns(isbn13 PK)`, `record_oclc(oclc PK)`, `record_files(record_id, torrent_display_name, path_in_torrent, btih, magnet)`), `max-mal/aa_local_db@1b09ac5` (`md5 = source.id[4:]`, `server_path`, `classifications_unified.torrent`, `ipfs_cid`) |
| fatcat identifier-snapshot TSVs | doi ↔ core/jstor/dblp/doaj/oai/ark/hdl/wikidata_qid ↔ md5/sha1/sha256 ↔ ipfs | **Internet Archive collection `fatcat_snapshots_and_exports`** | schema VERIFIED, contents ASSERTED |
| `ol_dump_editions_latest.txt.gz` + `<YYYYMMDD>_inlibrary_direct.tsv` | isbn13 ↔ ocaid ↔ OLID | openlibrary.org / archive.org | VERIFIED (`scottbarnes/reconcile@bb2631a7`) |
| LibGen.rs daily dbdumps over `ipfs.io/<hash>?filename=` | md5 ↔ libgen id ↔ ISBN ↔ DOI | IPFS | VERIFIED (`lgdbdumps@bc190f01`) |

**I searched for a packaged offline Sci-Hub coverage checker and there is none** — two GitHub
repository searches (`"sci-hub doi list bloom filter"`, `"scihub dois sqlite offline"`) both returned
`total_count: 0`. Every client in the class asks a live mirror instead. **litkb would be first.**

### 1.7 Two quota facts that change the cost model

- **`/dyn/md5/summary/<md5>` and `/dyn/md5/inline_info/<md5>` are NOT member-gated**, are
  `public_cache`d, and `summary` returns `downloads_left` and `is_member` **without spending a
  download** (`dyn/views.py:482,513`). A free quota probe and a free "does AA know this md5" probe.
  **Neither is in the 125-rung ladder.** (Reachability without a cookie is inferred from the absence of
  `protect_db_page`/`check_is_member` in the handler plus bitesized using it unauthenticated — **not
  measured**.)
- **Anna's `fast_download.json` returns `recently_downloaded_md5s`, and a re-download of an md5 in that
  list does NOT decrement `downloads_left`.** A retry after a bad file is free. Rounds 1 and 2 treat
  every call as metered. The miss vocabulary is **six** statuses (400 invalid md5 / 401 invalid key /
  403 not a member / 404 record not found / 429 no downloads left / 500 fetch error), not one `blocked`.

### 1.8 Anna's Sci-Hub layer is a DOI LIST, not files — and it is dated

`allthethings/page/sources/isbndb_scihub.py::get_scihub_doi_dicts` reads a **one-column table
`scihub_dois`** and synthesises `identifiers_unified.filepath = "scihub/<doi>.pdf"` with
`content_type_best = "journal_article"`. The in-code provenance comment:
*"This is a file from Sci-Hub's dois-2022-02-12.7z dataset."*

Two consequences. **An AA `scihub_doi` hit proves membership of that dump, not that bytes exist**
anywhere — which is why `scidb_info` demotes it to priority 2 and hands out a *link*. And the corpus
boundary is **2022-02-12**, a firmer date than the survey §6.2's "froze around 2021".

**This also makes a new rung possible: a SciDB lookup tells litkb whether Sci-Hub has a DOI WITHOUT
asking Sci-Hub** — the fix for the 21 `blocked` rows being retried blindly.

### 1.9 Mirror choice can cost zero shadow requests

`ShayNeeo/annas-mcp@c29e1a9` `src/mirror/resolver.rs` builds candidates from
`en.wikipedia.org/wiki/Anna%27s_Archive` and `open-slum.org` (an Uptime-Kuma status page), enriches
each with heartbeat history, and ranks by `success_rate` then `average_ping` — it **never probes the
shadow host to decide which mirror is alive**, and on total probe failure returns the top Wikipedia
candidate rather than concluding failure. `libgen-mcp` reads `shadowlibraries.github.io/DirectDownloads/libgen/`
(a GitHub Pages host) the same way; `calibre-lib` reads `open-slum.org/libgen.html`.
**Wikipedia, GitHub Pages and open-slum are not shadow hosts, so this rung is inside litkb's read rules today.**

And **cache the session, not the solve**: bitesized trades the member key for a cookie and caches only
the cookie (`sha256(key+mirror) → {cookie, at}`, 6 h TTL, in-memory, *"the key itself is never
retained"*, cookie name `aa_account_id2`), noting that **a bad key still returns 200 with the login
form, just no session cookie** — a login-failure detector litkb can adopt.
`RemiKalbe@d7dcb55` re-authenticates once on 403, then rotates domains.

### 1.10 The validity gate the shadow tier gives you free

Because **the address IS the digest**, `VerifyMD5` — hashing the streamed bytes against the md5 that
addressed them — is a stronger and cheaper acceptance test than any title match (libgen-mcp sets
`VerifyMD5: true` on md5-keyed items). An expired LibGen link answers **200 with a page**, so accept
bytes only on `%PDF` magic + content-type, and prefer the digest check when the key was a digest.
Symmetrically: Anna's `identifiers_unified.sha1/sha256` let litkb **verify a file it obtained anywhere
against the shadow tier's record of it without ever fetching from the shadow tier.**

### 1.11 One identity trap, with a committed regression fixture

`jmrplens/libgen-mcp` ships `internal/tools/testdata/libgen_edition_mismatched_doi.json`, whose own
header reads: *"LibGen edition 137198203 as served on 2026-08-08. The catalog carries Nassim Taleb's
Antifragile under John Ioannidis' PLoS Medicine DOI, so the record's `doi` field names a different work than every other field does."* The client answers it with a Crossref
title-containment check returning **`DOIConfirmed / DOIMismatch / DOIUnverified`** with a deliberate
unverified band. **A LibGen record's DOI is a claim, not an identifier.** If litkb ever admits a work
on a LibGen-supplied DOI it needs the same three-state corroboration.

---

## 2. The IDENTIFIER CROSSWALK GRAPH

### 2.1 The edge table

**103 edges.** Auth column: `none` = keyless; `email` = politeness parameter expected; `token` = a key
is required. VERIFIED here means a live response was observed this session by the named crawler, or the
mechanism was read as source at a pinned sha.

| # | from | to | service | endpoint | auth / rate | grade |
|---:|---|---|---|---|---|---|
| 1 | doi | openalex | OpenCitations META | `api.opencitations.net/meta/v1/metadata/doi:{doi}` | none | VERIFIED (live) |
| 2 | doi | pmid | OpenCitations META | same | none | VERIFIED (live) |
| 3 | doi | issn | OpenCitations META (`venue`) | same | none | VERIFIED (live) |
| 4 | doi | omid | OpenCitations META | same | none | VERIFIED |
| 5 | pmid | the whole id bag | OpenCitations META | `…/metadata/pmid:{pmid}` | none | VERIFIED (live, bidirectional) |
| 6 | openalex | the whole id bag | OpenCitations META | `…/metadata/openalex:{W…}` | none | VERIFIED (live) |
| 7 | doi | pmid | NCBI ID Converter | `pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/?ids={ids}&format=json` | none (`tool`+`email` warned if absent); **batches a comma list** | VERIFIED (live) |
| 8 | doi | pmcid | NCBI ID Converter | same | same | VERIFIED (live) |
| 9 | pmid | doi, pmcid | NCBI ID Converter (`idtype` auto-detected) | same | same | VERIFIED |
| 10 | pmcid | doi, pmid | NCBI ID Converter | same | same | VERIFIED |
| 11 | doi | pmid | NCBI E-utilities (the converter's fallback — it *under-reports* PMIDs for PubMed-not-PMC works) | `eutils…/esearch.fcgi?db=pubmed&term={doi}[DOI]` | none; 2/s | VERIFIED (source, manubot@859dd15) |
| 12 | pmid | doi, pmcid | NCBI efetch | `efetch.fcgi?db=pubmed&id={pmid}&retmode=xml` → `ArticleIdList` | none; 2/s | VERIFIED |
| 13 | pmid\|pmcid | CSL with DOI | NCBI Literature Citation Exporter | `api.ncbi.nlm.nih.gov/lit/ctxp/v1/{pubmed\|pmc}/?format=csl&id=` | none | VERIFIED |
| 14 | doi | pmid | Europe PMC core | `ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:"{doi}"&format=json&resultType=core` | none | VERIFIED |
| 15 | doi | pmcid | Europe PMC core | same | none | VERIFIED |
| 16 | pmcid | per-URL openness pre-check | Europe PMC `fullTextUrlList[]` `{availabilityCode, documentStyle, site}` | same | none | VERIFIED |
| 17 | doi | **pii** | Crossref `alternative-id[]` | `api.crossref.org/works/{doi}` | none (polite pool: send the UA string as `User-Agent` **and** `X-USER-AGENT`) | **VERIFIED (live: `10.1016/j.rse.2019.111496` → `S0034425719305152`)** |
| 18 | doi | isbn | Crossref `ISBN[]` + `isbn-type` | same | none | VERIFIED |
| 19 | doi | issn / **issn-l** | Crossref `ISSN[]` + `issn-type` (`pissn`/`eissn`/**`lissn`**) | same | none | VERIFIED (schema); `lissn` unobserved live |
| 20 | doi | related doi | Crossref `relation{name → {id-type, id, asserted-by}}` | same | none | VERIFIED (schema); **22/466 populated on this corpus** |
| 21 | doi | TDM URL | Crossref `link[]` `{URL, content-type, content-version, intended-application}` | none | VERIFIED — **Crossref hands over the built `api.elsevier.com/content/article/PII:{pii}` URL itself** |
| 22 | doi (`10.48550`) | arxiv id | DataCite | `api.datacite.org/dois/{doi}` → `identifiers[]` / `alternateIdentifiers[]` | none | VERIFIED (live) |
| 23 | version doi | concept doi | DataCite `relatedIdentifiers` `IsVersionOf` | same | none | VERIFIED (live) |
| 24 | concept doi | version doi | DataCite `HasVersion` | same | none | VERIFIED — **a Zenodo CONCEPT DOI has no file; without this edge the Zenodo rung 404s for reasons that look like a missing record** |
| 25 | doi | 13 relation types (`IsPartOf, Reviews, Continues, IsVariantFormOf, IsSupplementTo, HasVersion, IsMetadataFor, IsNewVersionOf, IsIdenticalTo, IsVersionOf, IsDerivedFrom, IsSourceOf`) | DataCite | same | none | VERIFIED (fatcat stores them verbatim under `extra.datacite.relations` and **never uses them** — `# TODO: could use many of these relations to do release/work grouping`) |
| 26 | doi | openalex | OpenAlex | `api.openalex.org/works/doi:{doi}` → `ids{}` | none; **batches `filter=doi:A\|B\|C`, 50/call** | VERIFIED — **466/466 on litkb's rows** |
| 27 | doi | mag | OpenAlex `ids.mag` | same | none | VERIFIED — but MEASURED to be the numeric tail of the W-id, i.e. **derived, not independent** |
| 28 | doi | pmid, pmcid | OpenAlex `ids.pmid/pmcid` | same | none | VERIFIED; **on this corpus `pmcid` came back EMPTY for all 466 — OpenAlex is not the pmcid source** |
| 29 | doi | handle | OpenAlex `locations[].pmh_id` → an OAI record in a named repository | same | none | VERIFIED |
| 30 | doi | s2 CorpusId | Semantic Scholar Graph | `api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=externalIds` | none, **429s within seconds unauthenticated — put it LAST** | VERIFIED (incl. the 429) |
| 31 | doi | dblp key | S2 `externalIds.DBLP` | same | same | VERIFIED — **the only free service that returned a DBLP key for a non-CS journal article**; 158/466 here |
| 32 | doi | arxiv, mag, acl, pmid, pmcid | S2 `externalIds` | same | same | VERIFIED — **all 36 PMCIDs on this corpus came from S2, none from OpenAlex** |
| 33 | doi | bibcode | NASA ADS | bootstrap → `api.adsabs.harvard.edu/v1/search/query?q=doi:{doi}&fl=bibcode,doi,identifier,eid,esources,property` | **keyless `/v1/accounts/bootstrap` yields a 40-char Bearer token** | VERIFIED (live) |
| 34 | arxiv | bibcode + `10.48550` doi | NASA ADS `identifier[]` | same | same | VERIFIED (live: `arxiv:1505.04597` → all three) |
| 35 | doi | **route pre-check** (`esources[] ∈ PUB_HTML, PUB_PDF, EPRINT_PDF, EPRINT_HTML, ADS_PDF, ADS_SCAN`; `property[] ∋ OPENACCESS`) | NASA ADS | same | same | **VERIFIED (live: closed IEEE TGRS `10.1109/TGRS.2016.2612821` → `["PUB_HTML"]`, no `OPENACCESS` — every free rung will miss, known before a byte moves)** |
| 36 | doi\|pmid\|arxiv\|P&lt;n&gt; | wikidata QID | Wikidata hub | `hub.toolforge.org/{prefix\|Pnnn}:{value}?format=json` | none | VERIFIED (live) |
| 37 | QID | doi (P356, **stored UPPERCASE**) | Wikidata EntityData | `wikidata.org/wiki/Special:EntityData/{QID}.json` | none | VERIFIED (live) |
| 38 | QID | pmid (P698) | same | same | none | VERIFIED |
| 39 | QID | pmcid (P932, **stored WITHOUT the `PMC` prefix**) | same | same | none | VERIFIED |
| 40 | QID | bibcode (P819) | same | same | none | VERIFIED |
| 41 | QID | opencitations (P3181), researchgate (P5875) | same | same | none | VERIFIED |
| 42 | doi\|pmid\|pmcid\|issn | QID | Wikidata SPARQL (P356 **uppercased** / P698 / P932 / P236) | `query.wikidata.org/sparql` | none | VERIFIED (source, oc_graphenricher@08cd064) |
| 43 | doi | landing URL **without contacting the publisher** | handle.net REST | `hdl.handle.net/api/handles/{doi}` → `values[]` type `URL` | none | **VERIFIED (live: `10.3390/rs14205081` → `mdpi.com/2072-4292/14/20/5081`)** |
| 44 | handle | repository item URL | handle.net REST | same shape | none | VERIFIED |
| 45 | shortdoi (`10/abcde`) | full doi | Handle system | `doi.org/api/handles/{sd}?type=HS_ALIAS` | none | VERIFIED (manubot `expand_short_doi`) |
| 46 | doi | registration agency (`crossref\|datacite\|jalc\|medra\|airiti\|cnki\|istic\|kisti\|op`) | doi.org | `doi.org/ra/{doi}`; existence via `doi.org/api/handles/{doi}` (`responseCode == 1`) | none | VERIFIED — **this, not a metadata API, is the correct fan-out ROOT** |
| 47 | doi | core id | fatcat | `api.fatcat.wiki/v0/release/lookup?doi=` | none | schema VERIFIED; **API DEAD (curl exit 28 / HTTP 000)** → dumps only |
| 48 | doi | jstor | fatcat | same | — | same — **the only open source of a `jstor` edge** |
| 49 | doi | dblp, doaj, oai, ark, hdl, mag, wikidata_qid, isbn13 | fatcat (one call returns them together) | same | — | same |
| 50 | doi | file md5 / sha1 / sha256 | fatcat file entity | same | — | same. **CAVEAT: this is the hash of IA's crawled file, a CANDIDATE Anna's key, never guaranteed** |
| 51 | doi | ipfs url (`rel = dweb`) | fatcat file `urls[]` | same | — | same |
| 52 | isbn | olid | Open Library | `openlibrary.org/search.json?fields=key,ia,isbn,lccn,oclc,edition_key,id_goodreads`; `/isbn/{isbn}.json`; `/api/books?bibkeys=ISBN:` | none | VERIFIED (live) |
| 53 | isbn | **ocaid** | Open Library `ia[]` | same | none | VERIFIED (live) — **this is the edge round 2 thought was closed; it is closed in *Zotero*, not in Open Library** |
| 54 | isbn | oclc | Open Library `oclc[]` | same | none | VERIFIED (live) |
| 55 | isbn | lccn | Open Library `lccn[]` | same | none | VERIFIED (live) |
| 56 | isbn | goodreads, asin (`source_records: ["amazon:…"]`) | Open Library | `/isbn/{isbn}.json` | none | VERIFIED |
| 57 | oclc \| lccn \| olid | the same bag | Open Library `/api/books?bibkeys=<TYPE>:` — **four native key types at one endpoint** | same | none | VERIFIED |
| 58 | OL edition | **anna's md5** | Open Library `identifiers.annas_archive` (Anna's ingests it as `md5`) | `/books/{OLID}.json` | none | **VERIFIED — a keyless, legitimate API that names a shadow-tier file key** |
| 59 | ocaid | isbn, lccn, oclc, olid | IA metadata | `archive.org/metadata/{ocaid}` | none | VERIFIED (live) |
| 60 | ocaid | **a LibGen md5** (`urn:libgen:…/<md5>`) | IA `external-identifier[]` | same | none | VERIFIED |
| 61 | ocaid | files + **DRM state** (`access-restricted-item`, `collection`, `urn:lcp:`, `urn:acs6:`) | IA metadata | same | none | VERIFIED — **the only place the DRM state is visible BEFORE a fetch** |
| 62 | ocaid | `{ocaid}_djvu.txt` — free, legal, searchable, quotable OCR of the same scan whose `.pdf` is lending-gated | IA files | same | none | VERIFIED (live) |
| 63 | isbn \| oclc \| lccn \| olid | htid | HathiTrust Bib API | `catalog.hathitrust.org/api/volumes/brief/<TYPE>/<num>.json` | none | VERIFIED |
| 64 | htid | isbn, issn, lccn, oclc | hathifiles / Anna's `aac_hathi` | — | none | VERIFIED |
| 65 | htid | **`us_gov_doc_flag`** — the unrestricted US federal slice | hathifiles | — | none | VERIFIED — the one HathiTrust population that overlaps a forestry/agency corpus |
| 66 | isbn | gbooks volume id | Google Books | `googleapis.com/books/v1/volumes?q=isbn:` | none | VERIFIED |
| 67 | gbooks | oclc (`OTHER` prefix `OCLC:`) | Google Books `industryIdentifiers[]` | same | none | VERIFIED — 42,399,475 in Anna's in-code census |
| 68 | gbooks | lccn (`OTHER` prefix `LCCN:`) | same | same | none | VERIFIED — 1,528,733 |
| 69 | oclc | isbn, issn, **doi** | WorldCat / Anna's `oclc` record (OpenURL `rft.*`) | `/oclc/<num>` + key | **token** | MIXED |
| 70 | isbn10 | isbn13 | `isbnlib.to_isbn13` | — | **none, zero network** | VERIFIED |
| 71 | isbn13 | ISBN-A doi | `isbnlib.doi(isbn)` | — | **none, zero network** | VERIFIED |
| 72 | isbn | the edition ISBN set | `isbnlib.editions(isbn, 'merge')` — unions Open Library **and** LibraryThing | — | none | VERIFIED (source) |
| 73 | isbn | oclc + **OWI** (OCLC Work Identifier) | `isbnlib._oclc` → `classify.oclc.org/classify2/Classify?isbn=` | none | **LIVENESS UNVERIFIED — Classify retired 2024; zero GitHub code hits** |
| 74 | arxiv id | doi | **`10.48550/arXiv.{id}`, "replacing the colon with a period"** — arXiv's own help page; **a new version does NOT mint a new DOI** | — | **none, zero network** | ASSERTED-BY-PUBLISHER — **the cheapest coverage change in this report** |
| 75 | doi (`10.48550`) | arxiv id | the inverse of #74 | — | none, zero network | ASSERTED-BY-PUBLISHER |
| 76 | isbn / doi / pmid / pmcid / QID / any URL | Zotero-shaped CSL incl. normalised ISBN-13 | Citoid | `en.wikipedia.org/api/rest_v1/data/citation/mediawiki/{id}` | none | VERIFIED (live; `source[]` names the backend that answered) |
| 77 | free text | `{DOI, ISBN, PMID, arXiv, adsBibcode, contextObject, identifiers:{oclc}}` | Zotero `extractIdentifiers` / translation-server `/search` | POST text/plain | none | VERIFIED |
| 78 | isbn \| oclc | MARC-derived item | Zotero `Open WorldCat.js` — **the only translator that takes an OCLC number natively** | — | none | VERIFIED |
| 79 | doi | md5 | **Anna's `/scidb/<doi>`** → `a[href^='/md5/']` | shadow host | member cookie for the record route | VERIFIED (source) |
| 80 | md5 | `identifiers_unified` — **up to ~120 schemes incl. pmid, pmcid, isbn10/13, jstorstableid, issn, oclc, ol, lccn, gbooks, hathi, nexusstc, zlib, lgrsnf, lgli, pii, isni, sha1, sha256, ipfs_cid, server_path, asin, goodreads** | Anna's `/db/aarecord_elasticsearch/md5:<md5>.json` | shadow host; **member cookie**; litkb ALREADY makes this call | VERIFIED — **the single largest identifier windfall available, at ZERO new requests** |
| 81 | any `<scheme>:<value>` | aarecord | **Anna's `/search?q=pmid:… \| oclc:… \| ol:OL…M \| hathi:… \| jstorstableid:… \| lgrsnf:… \| zlib:… \| md5:…`** — `search_text` is indexed as `"<scheme>:<value>"` for EVERY key in `identifiers_unified`; only `isbn13` and `doi` get dedicated ES fields | shadow host | VERIFIED — **a universal identifier lookup nobody named in rounds 1–2** |
| 82 | a code byte-prefix | up to 100 `aarecord_id`s | Anna's `/codes?prefix_b64=` over `aarecords_codes(code, aarecord_id)` | shadow host | VERIFIED (cost unknown) |
| 83 | md5 | ipfs_cid (+ `from` = the source collection) | Anna's `ipfs_infos[]` | shadow host | VERIFIED |
| 84 | md5 | torrent path / `server_path` | Anna's `classifications_unified.torrent`, `identifiers_unified.server_path` | shadow host / offline dump | VERIFIED |
| 85 | md5 | `downloads_left`, `is_member` **without spending a download** | Anna's `/dyn/md5/summary/<md5>` | **unauthenticated, `public_cache`d, served as `text/css`** | VERIFIED (source); reachability unmeasured |
| 86 | doi | **Sci-Hub membership** (the `scihub_doi` source record) | Anna's SciDB waterfall `{priority, doi, path_info, scihub_link, ipfs_url, nexusstc_id}` | shadow host | VERIFIED — **answers "does Sci-Hub have this DOI" without asking Sci-Hub** |
| 87 | doi | md5 | **LibGen `json.php?object=e&doi=<doi>&addkeys=*`** → `files{}.md5` | shadow host; **an honest bot UA works on this path** | VERIFIED (independent Go client + committed fixtures) |
| 88 | md5 | sha1, sha256, crc32, eDonkey, AICH, TTH, **BTIH**, **IPFS CID**, **Z-Library id** (`Library="zlib"`, `value_add1`) | **LibGen `json.php?object=f&md5=<md5>&addkeys=*`** — the `add{}` bag | shadow host | VERIFIED — **a rung whose product is IDENTIFIERS, not bytes; it should run even after a successful download** |
| 89 | md5 | libgen_id, fiction_id, comics_id, scimag_id, standarts_id, magz_id, `scimag_archive_path` | LibGen `object=f` | shadow host | VERIFIED |
| 90 | isbn | md5 | LibGen `index.php?req=&columns[]=i&topics[]=l\|f`; classic `search.php?req=&column=identifier` | shadow host | VERIFIED |
| 91 | doi | pmid | **LibGen `scimag.PubmedID`** — 12.87 % of 64.2 M rows (8.26 M) | dump or record | **offline** | VERIFIED (2017 census) |
| 92 | doi | pmcid | **LibGen `scimag.PMC`** — 2.36 % (1.52 M) | same | offline | VERIFIED |
| 93 | doi | **pii** | **LibGen `scimag.PII`** — 7.60 % (4.88 M), **Elsevier's own native key** | same | offline | VERIFIED |
| 94 | doi | issn print / electronic | LibGen `scimag.ISSNP` 81.4 %, `ISSNE` 45.9 % (vs `Journal` name only 55.4 %) | same | offline | VERIFIED — **resolve serials by ISSN, never by name** |
| 95 | doi | md5 | **LibGen `scimag.MD5` — 100 % complete over 64,195,945 rows, no exceptions** | same | offline | VERIFIED |
| 96 | md5 | openlibraryid, googlebookid, asin, ISBN list, DDC/LCC/UDC/LBC | LibGen `updated` dump table | same | offline | VERIFIED (2020 schema) |
| 97 | md5 | ipfs_cid | LibGen `hashes` table joined on MD5 | same | offline | VERIFIED |
| 98 | doi | libgen_ids[], zlibrary_ids[], pubmed_id, isbns, **parent_isbns**, issns, ark_ids, md5, **IPFS CID** — **all in ONE document** | **Nexus/STC `nexus_science`** term query on `id.dois` | shadow host / IPFS | VERIFIED (schema + committed notebook records) |
| 99 | nexusstc_id \| md5 | doi, zlib, lgrsnf, manualslib, iso, british_standard, **pmid**, isbns, **parent_isbns**, issns, orcid | Anna's `aac_misc.py::get_aac_nexusstc_book_dicts` | shadow host | VERIFIED — **the densest single crosswalk call in the class**; `parent_isbns` is the chapter→container-ISBN routing the survey's §4.1 needs |
| 100 | doi | `in_scihub_dois`, `in_scihub_logs`, `in_libgen` | **greenelab offline membership test** (`doi_df.doi.isin(scihub_dois)`) | **GitHub, zero shadow requests** | VERIFIED |
| 101 | doi | `citation_title`, `citation_author`, `citation_journal_title`, `citation_pdf_url` | Sci-Hub page parse (**meta FIRST, then `embed\|iframe src`**, `//` and `/` resolved against the mirror host) | shadow host | VERIFIED — free bibliographic metadata for works Crossref has no record of |
| 102 | doi | open-access **and** Sci-Hub availability + "resolved provider URLs" | Sci-Net search | account | MIXED (its own doc disclaims being an API contract) |
| 103 | title + author + year | doi | Crossref `query.bibliographic`, `similarStrings(...) > 0.75`, newest `deposited` wins, DOI lowercased | `api.crossref.org` | none | VERIFIED (`ferru97/PyPaperBot@a65bf70`) |

### 2.2 The NATIVE-KEY table — which key each provider actually accepts

**The operative column is the last: the crosswalk edge a hunt must already have resolved before that
rung can fire at all.** Rows marked **UNFIREABLE** cannot run today because litkb's column for that key
is empty.

| provider (survey rung) | accepts | does NOT accept | prerequisite edge | state today |
|---|---|---|---|---|
| Unpaywall (B2) | **doi only** | title, pmid, isbn | — | fireable |
| OpenAlex (B3) | doi, pmid, pmcid, openalex, mag, title | isbn | — | fireable |
| Semantic Scholar (B5, B18) | DOI, ArXiv, MAG, ACL, PMID, PMCID, DBLP, CorpusId, paperId, title | isbn | — | fireable |
| CORE v3 search (B7) | doi, oai id, arxiv, pmid, mag, title | isbn | — | fireable |
| **CORE download (B17)** | **coreId only** — `core.ac.uk/download/{id}.pdf` | doi | doi → core id (fatcat dump, or B7) | **UNFIREABLE for retry** — litkb cannot store a core id, so a successful B7 resolution can never be re-used |
| Europe PMC (B12, B20, B25) | doi, **pmid**, **pmcid**, title | isbn | doi → pmid/pmcid | partly fireable (doi) |
| **PMC OA service (B22), `?pdf=render` (B21)** | **pmcid only** | doi | **doi → pmcid** | **UNFIREABLE — the survey's instruction to budget no yield from this family was decided with the key missing** |
| arXiv (B10) | **arxiv id** (`vN`-sensitive), title | doi | `10.48550` doi → arxiv id, or #74's inverse | partly fireable (6 rows carry `arxiv` today; the probe finds 71) |
| bioRxiv / medRxiv (B23) | doi + a resolved version | — | doi → version | fireable |
| Zenodo (B14) | **version doi** or record id | concept doi alone | concept → version via DataCite `HasVersion` | fireable with #24 |
| **NASA ADS (B15)** | doi, arxiv, **bibcode**, title | isbn | doi → bibcode | partly fireable; **no `bibcode` scheme exists** |
| HAL / SSRN / RePEc / DBLP | native site id | — | doi → dblp via S2; **no free doi→SSRN or doi→RePEc edge found** | MIXED |
| DSpace 7 / OAI (B16, D6, D13) | item **uuid**, **oai id**, handle | doi | doi → handle (OpenAlex `pmh_id`, fatcat `hdl`/`oai`) | **UNFIREABLE for retry — no `oai` scheme, and `handle` is empty** |
| USFS Treesearch (D1/A8), USGS (D2), OSTI, NTRS | **title** and a site id | doi mostly absent | none available | fireable by title |
| Internet Archive (books) | **ocaid** | isbn, doi | isbn → ocaid (Open Library) | **UNFIREABLE — no `ocaid` scheme, and `isbn` is empty** |
| Open Library / DOAB / OAPEN | **isbn** (DOAB also doi) | — | doi → isbn (Crossref `ISBN[]`; **12 works on this corpus**) | **UNFIREABLE — `isbn` empty** |
| HathiTrust (F5) | isbn, oclc, lccn, **htid** | — | isbn → oclc/lccn | **UNFIREABLE** |
| Google Books (F6) | isbn, oclc, lccn, volume id | doi | isbn → volume id | **UNFIREABLE** |
| **Elsevier TDM (H2)** | doi **or PII** — `api.elsevier.com/content/article/PII:{pii}` | — | doi → PII (Crossref `alternative-id`) | **UNFIREABLE by PII — no `pii` scheme.** 90 of the corpus's 92 Elsevier DOIs have one waiting |
| Springer (H1), Wiley (H3), IEEE (H4) | doi | — | — | fireable |
| **Anna's Archive** (G0d, G2a) | **md5** (record), **doi** (`?content=journal`), **isbn** (`content=book_any`), **and — NEW — any scheme via `/search?q=<scheme>:<value>`** | — | doi → md5, or isbn-13 for books | partly fireable; **book half UNFIREABLE** |
| **LibGen** (G0a, G1d, F-stage) | **doi** (scimag), **isbn** (book table), **md5** (delivery) | — | book path needs ISBN-13 | **book half UNFIREABLE by construction** |
| **Sci-Hub** (G0c, G1a, G1b) | **lowercased doi**; then a portable `/storage/…pdf` path | isbn | doi, casefolded | fireable |
| **Nexus / STC** (G0b, G1c) | **doi** (lowercased), and aliases `isbn: issn: pmid: cid:` | — | doi | fireable |
| **Z-Library** (F10) | **`(bookid, hash)`**; search is **free text only** | isbn, doi, hash-as-parameter | the zlib id must come from Anna's, STC or LibGen's `add{}` | **RE-GRADED: reachable but NOT addressable** |
| IPFS gateways | **CID** | — | md5 → CID (Anna's `ipfs_infos`, LibGen `add{}`, STC `links[]`) | **no `ipfs_cid` home** |

### 2.3 The fan-out ORDER for this corpus, with the closure rule

The corpus is remote sensing, ecology, statistics, ML and agency reports: **mostly Crossref DOIs
(382 journal articles + 32 proceedings), a minority of arXiv preprints (71 by the probe), almost no
biomedical, 11 chapters and 1 book, and 32 DOIs Crossref does not know.** Order accordingly.

**Wave 0 — DETERMINISTIC, zero requests, provenance `deterministic`:**

```
arxiv id            → doi = "10.48550/arXiv.{id}"          (versionless; CANDIDATE until DataCite confirms)
doi prefix 10.48550 → arxiv id                             (the inverse)
isbn10              → isbn13   isbnlib.to_isbn13
isbn13              → ISBN-A doi  isbnlib.doi(isbn)
pmcid "PMC7391"     ↔ "7391"                               (idutils pmcid_regexp)
shortdoi "10/abcde" → full doi                             (Handle HS_ALIAS — 1 request, not 0)
```

**Wave 1 — three CONCURRENT keyless calls. Two of them litkb already makes.**

| # | call | fills | note |
|---|---|---|---|
| 1 | `api.opencitations.net/meta/v1/metadata/doi:{doi}` | `openalex`, `pmid`, issn, crossref-member, orcid — **4–6 schemes in one GET** | NEW rung |
| 2 | `api.crossref.org/works/{doi}` | **`pii`**, `isbn`, issn/`lissn`, `relation` targets, `link[]` | **already made; the fields are discarded** |
| 3 | `api.openalex.org/works/doi:{doi}` | `openalex`, `mag`, `pmh_id` → `handle` | **already made; the fields are discarded** |

**Wave 2 — one conditional call each, fired only where Wave 1 left a gap:**

| condition | call | fills |
|---|---|---|
| no `pmid`/`pmcid` | **NCBI idconv, BATCHED over the whole hunt queue** (comma list) | `pmid`, `pmcid` |
| idconv silent but the work looks indexed | eutils `esearch?term={doi}[DOI]` | `pmid` — the converter under-reports PubMed-not-PMC works |
| `pmcid` found | Europe PMC `resultType=core` | confirms pmcid **and pre-checks every PMC delivery rung** |
| prefix `10.48550`, `10.5281`, `10.6084`, or Crossref 404 (**32 rows here**) | `api.datacite.org/dois/{doi}` | `arxiv`, Zenodo concept↔version, relation edges |
| still no free PDF candidate | ADS bootstrap + `fl=identifier,esources,property` | `bibcode` **and the answer to "will any free rung fire"** |
| everything else exhausted | S2 `?fields=externalIds` | `s2`, `dblp`, and **the pmcid OpenAlex does not have** — **LAST, it 429s in seconds** |

**Wave 3 — book/report class only** (the work-class router says `book`, `chapter`, `report`, `thesis`):
Open Library `search.json?fields=key,ia,isbn,lccn,oclc,edition_key` → `archive.org/metadata/{ocaid}`
(files **and** DRM state) → Citoid as the normalising fallback.

**Wave 4 — late, cheap, low-yield:** `hub.toolforge.org/doi:{doi}` → QID → `Special:EntityData`.
MEASURED coverage on this corpus is poor (a 2022 MDPI *Remote Sensing* DOI has **no Wikidata item at
all**), so it belongs last, and **the `isbn:` alias must be replaced by `P212:`** (§6).

**Offline, once:** the fatcat identifier-snapshot TSVs (`jstor`, `ark`, `doaj`, `core`, `oai`), the
greenelab Sci-Hub DOI list and LibGen scimag TSV, and — under Kam's ruling — the AA derived-mirror
metadata and the LibGen SQL dumps.

**The closure rule, from `oc_graphenricher@08cd064`:**

1. A target scheme is pursued **only if it is absent** (`if has_openalex is None`) — per-scheme, not global.
2. The **input** key is whichever held identifier the target service accepts (`BR_API_SCHEMAS` is a table), tried in turn, **`break` on the first hit**.
3. The accumulation step runs **after whichever resolver won, unconditionally** (Manubot's `augment_get_doi_csl_item` always adds PMID/PMCID after any DOI retriever).
4. Repeat only for the schemes still absent, and only with identifiers **discovered since the last pass**. **STOP when a full pass adds no new identifier** — in practice ≤3 passes; the QID hop is the only one that ever fires a third.

Cost: roughly **6–9 keyless requests per work**, all cacheable, with idconv and OpenAlex batching
across the corpus. For litkb's 466 DOI-bearing works that is **one evening, not a campaign.**

**The explicit anti-recommendation, from S5:** do **NOT** add more OA indexes hoping for identifiers.
Round 2's 24-tool union already concluded Stage B is complete. This round's yield is **reading fields
existing calls already return, and adding four schemes so the answers have somewhere to go.**

---

## 3. The identifier DATA MODEL recommended for litkb

### 3.1 The schemes to add, each with a named consumer

litkb's table **shape is right** — a one-row-per-`(scheme, value)` edge table is exactly what the best
crosswalks use, and three independent offline Anna's mirrors converged on it
(`RecordIdentifier{Record, Type, Value}`, indexed `(type,value)`). What is missing is vocabulary and
content.

**Tier 1 — a rung on litkb's own ladder cannot fire without it:**

| add | consumer | evidence |
|---|---|---|
| **`md5`** | G0a, G1d, G2a, G2b, and the survey's own Stage-G rule *"keep a `doi → {md5, cid, storage_path}` cache — it is the ladder's real state"* **has nowhere to live today**. litkb learns an md5 **before** it has bytes, so `files.sha256` is the wrong hash and the wrong direction | S1, S2, S3, S5 |
| **`pii`** | H2 — `api.elsevier.com/content/article/PII:{pii}`, the native key of this corpus's largest closed publisher. **90 of 92 Elsevier DOIs here already have one in a field litkb fetches and discards** | §0.4, S5 §2.3 |
| **`core`** | **B17 is `core.ac.uk/download/{id}.pdf` — a BYTE rung keyed on a CORE id litkb cannot store**, so a successful CORE resolution can never be retried | S6 |
| **`bibcode`** | B15 (NASA ADS), whose gateway is `link_gateway/{bibcode}/ARTICLE`, and whose `esources` route pre-check is the cheapest "will any free rung fire" test found | S5, S6 |
| **`ocaid`** | the Internet Archive book PDF **and** the `_djvu.txt` quotable-text fallback | S5 |
| **`oai`** | B16 / D6 / D13 / A7 — a DSpace item uuid or OAI id has nowhere to live, so a successful repository resolution is re-derived every run | S6 |

**Tier 2 — cheap to carry, arrive unasked, and unlock the book path:**
`issn` (container-level), `oclc`, `lccn`, `olid`, `htid`, `gbooks`, `asin`, `sha1`, `sha256`,
`ipfs_cid`, `btih`, `zlib`, `lgrsnf`/`lgrsfic`/`lgli`, `nexusstc`, `wikidata`, `mag`, `dblp`, `doaj`,
`ark`, `urn`, `hal`.

**Tier 3 — Anna's four state-bearing schemes, worth copying verbatim** because they are *evidence*, not
dropped values: **`isbn_invalid`**, **`isbn_cancelled`**, `md5` vs `md5_reported`, `ipfs_cid` vs
`ipfs_cid_blake2b`.

**Do NOT put `ipfs_cid`, `btih`, `server_path` or `torrent_path` in the identifier table if you accept
S6's line**: they are storage locations for a *file*, not identifiers of a *work*, and A5's structural
rule (separate address resolution from delivery) draws the same boundary. **This synthesis disagrees
with S6 on `md5`** and agrees on the rest: `md5` is simultaneously the shadow tier's *work address* and
a file digest, and it is the join key every other library takes, so it belongs in the identifier table.
`ipfs_cid`/`btih`/`server_path` belong beside it **in the acquisition ledger**. (Recorded as a
disagreement in §6.)

**Keep `scheme` open, or at least easy to extend.** Anna's has ~120 and adds more; a closed CHECK
constraint is a migration every time a library is added.

### 3.2 Provenance per identifier

litkb already has `verified_by` and `evidence jsonb` on `identifier_versions`. Three changes:

1. **Widen `verified_by`** from five values to the service list: `crossref, datacite, arxiv, s2,
   openalex, opencitations, pubmed, pmc_idconv, europepmc, unpaywall, core, doaj, openaire, ads,
   wikidata, handle, isbnlib, openlibrary, internetarchive, hathitrust, gbooks, worldcat, fatcat,
   annas, libgen, nexusstc, **deterministic**, manual`.
2. **Add `asserted_by` distinct from `verified_by`** — Invenio-RDM's split between `provider` (who
   minted it) and `client` (who asserted it here). Its `PIDSchema` is six lines and is the only
   implementation in the class that *persists* per-identifier provenance:
   ```python
   class PIDSchema(Schema):
       identifier = SanitizedUnicode(required=True)
       provider   = SanitizedUnicode(required=True)
       client     = SanitizedUnicode()
   ```
3. **Record the INPUT identifier the edge was derived from.** `oc_graphenricher` computes exactly this
   string — `by_means_of = f"its {schema.upper()} {literal}"` — **and passes it only to
   `LOGGER.debug`.** Even the best crosswalk in the class throws its provenance away. Keeping it is
   what makes a bad crosswalk **retractable** later, and litkb's version-and-retract machinery already
   exists to hold it.

Anna's does the same thing at scale: `merge_unified_fields_with_provenance` keeps, for every
`(scheme, value)` pair, the list of source records that asserted it. **Memory of the World alone
contributes ISBNs from 138,771 records of uneven quality** — without provenance litkb cannot later
decide which ISBN to trust, and the survey's §4.5 admission gate is exactly where a wrong ISBN silently
binds the wrong book.

### 3.3 Uniqueness must be per-scheme DATA, not one blanket index

`identifiers_active_scheme_value` asserts that **every** scheme is distinct-valued. That is:

- **true** for `doi`, `arxiv`, `pmid`, `pmcid`, `openalex`, `s2`, `mag`, `bibcode`;
- **false for `isbn`** — fatcat's own spec says *"ISBN-13, for books. Usually not set for chapters"*
  and its Crossref importer sets it on chapters anyway (`importers/crossref.py:325-331`), getting away
  with it only because `ext_ids` are plain columns with **no uniqueness constraint**;
- **false for `issn`** — a container key shared by every article in the journal; citation-js reads it
  as `P1433.P236`, i.e. **through the container entity**, not from the work;
- **false for `oai` and `handle`** across repositories that mirror;
- **false for `md5`** — one work legitimately has many files (librarr re-searches for *alternative*
  md5s of the same work; an STC record carries four links with four md5s; Anna's tracks
  `ipfs_infos[].from` per collection **precisely because** the same work exists as several distinct files).

Follow `WikidataIntegrator@505d58d`, which reads its uniqueness set from Wikidata's own
**distinct-values constraint** (P2302 / Q21502410) rather than hardcoding it, and carries
`core_prop_match_thresh = 0.66`. **Add a `scheme_registry` table with `distinct_values boolean`**
(plus label, url template, regex, normaliser name) and enforce the partial unique index only over the
schemes that carry it. A non-distinct scheme's collisions then become *data* rather than a constraint
violation — which is what makes the book/chapter case representable at all.

### 3.4 The two-works-one-identifier rule — books/chapters, and preprints/versions

**Adopt fatcat's two conflict rules verbatim. They are the only tested answers in the class.**

*Merge, strictly monotone* (`importers/pubmed.py`): `existing.x = existing.x or incoming.x` — **a later
source fills a null and can never overwrite a value.**

*Collision*: when two identifiers in one incoming record resolve to two different existing works, do
**not** overwrite and do **not** refuse — **drop the weaker identifier from the incoming record and
assert a work-level GROUPING instead**, and count it:

```python
if existing and existing.ext_ids.pmid and existing.ext_ids.pmid != re.ext_ids.pmid:
    warnings.warn("PMID/DOI mismatch: ..."); self.counts["warn-pmid-doi-mismatch"] += 1
    re.ext_ids.doi = None        # don't clobber DOI,
    re.work_id = existing.work_id  # but do group together
```

The arXiv importer does the same for arXiv/DOI. **litkb's equivalent: write no identifier row, write an
`is_version_of` / `is_identical_to` edge with `asserted_by='conflict-resolution'`, and increment a
QC-visible counter.** A collision silently dropped is exactly the class of defect CLAUDE.md §3.4c was
written about. (WikidataIntegrator's alternative is a hard stop — `ManualInterventionReqException`
recording `conflict_source`, i.e. *which property* collided; litkb's partial unique index already
raises, so what it lacks is the `conflict_source` and the threshold.)

**Edge vocabulary — take DataCite's, which fatcat captures and never uses:** `is_part_of` (chapter →
book, article → proceedings volume — the survey's C17 whole-volume case), `is_version_of`,
`is_new_version_of` (preprint → VOR, arXiv v1 → v3, Zenodo version → concept), `is_identical_to`,
`is_supplement_to`. **MEASURED on this corpus: Crossref already carries `has-preprint` on 10 works,
`is-part-of` on 5, `has-version`/`is-version-of` on 2 each, `correction` on 2.**

**Three of the four codebases that need this express it as a PARENT ENTITY, not an edge table** —
fatcat `work_id`, Invenio `RDMParentSchema.pids`, Wikidata `P361`. A parent column is cheaper, and
**Zenodo's concept-vs-version DOI is not two identifier types; it is one type held at two levels of the
same entity hierarchy.** So `works.part_of_work_id` and `works.version_of_work_id` are enough for the
common cases, with an edge table only for the rest.

**The ISBN routing rule, concretely:** a chapter DOI carries the **book's** ISBN. The ISBN attaches to
the **BOOK** work; the chapter links by a `part_of` edge. Nexus/STC's ingest names both sides of this
explicitly — `metadata.isbns` **and `metadata.parent_isbns`**.

**The preprint/VOR rule:** OpenAlex states its policy verbatim — *"this field always has just one DOI,
the DOI for the published work"*. arXiv states that **the `10.48550` DOI is versionless** and a new
version does not mint a new one. That **vindicates litkb's `norm_identifier` arXiv rule** (strip
`v\d+$`) and Zotero's (*"arXiv OAI API doesn't allow to access individual versions"*), and explains
fatcat's opposite rule — fatcat makes each version a first-class release, so it *needs* the version in
the key.

### 3.5 Validators to port, in priority order

1. **`Zotero.Utilities.cleanDOI`** (`zotero/utilities@4051881`, `utilities.js:481-523`) — the
   bracket-balance rule: it strips a trailing `)`, `]` or `}` **only when the preceding text holds an
   unclosed opener of the same kind**. litkb's DOIs come from reference lists where `(doi:10.1234/x)`
   is ordinary, and **nothing else in the class handles it.**
2. **`isbnlib.canonical` + `check_digit13` + `to_isbn13`** (`xlcnd/isbnlib@ddc62f2`) — it **rejects
   rather than coerces**, screens the all-zero sentinels (`0000000000`, `000000000X`), and re-derives
   the check digit instead of trusting the input's.
3. **idutils' regex table** (`inveniosoftware/idutils@2623d78`) for `pmid, pmcid, handle, urn, ark,
   ads, wikidata, openalex, hal, issn` — and especially `arxiv_post_2007_with_class_regexp`, whose own
   docstring is the reason: *"technically malformed, however appears in real data."*
4. **`detect_identifier_schemes` returning a SET + the declarative `IDUTILS_SCHEME_FILTER` table** —
   detection must return every match and disambiguate from data, because **a bare number is
   simultaneously a plausible `pmid`, `oclc`, `mag` and `core` id**, and litkb's `tracker` and
   `legacy_stem` schemes already guarantee ambiguous strings. Keep Zotero's ordering discipline on top:
   **PMID last, and only when it is the whole string.**
5. **`oc_idmanager.DOIManager.normalise`** — the `id_string[id_string.index("10."):]` slice, which
   survives any wrapper (a URL, `doi:`, a BibTeX field, a PDF line), as a **second pass** when
   `cleanDOI` returns null.
6. **`isbnlib.editions(isbn, 'merge')` and `isbnlib.doi(isbn)`** — the two book-side crosswalks, one
   function call each.
7. **libgen-mcp's `NormalizeISBN`** — validates **shape, not the check digit**, deliberately: *"a
   mistyped check digit is indistinguishable from a catalog that recorded one wrong"*; requires a
   `978`/`979` Bookland prefix for 13 digits; `isbn13Of` converts so **the two spellings of one book
   compare equal.** Pair it with isbnlib's stricter canonical and decide which layer rejects.

**DO NOT PORT: `oc_idmanager`'s ISBN-13 check digit.** `val = 3 if val == 1 else val == 1` assigns a
**boolean**, so after the second digit `val` is `False` (0) and the weights degenerate to `1,3,0,0,…`;
the test becomes `(d0 + 3·d1) % 10 == 0` and **roughly one in ten arbitrary 13-digit strings passes.**
(The ISBN-10 branch immediately below it is correct.) VERIFIED by reading; not executed.

**Also do not port**: CSL as an identifier schema (Manubot's `CSL_Item` has first-class slots only for
DOI/PMID/PMCID/ISBN/ISSN and stuffs everything else into a free-text `note` parsed back by regex), and
`papis`' `papis_id` (an md5 of the document's own string representation, non-deterministic unless a
separator is supplied — a local handle, not a crosswalk).

### 3.6 Three normalisation traps that silently cause misses

| trap | consequence | fix |
|---|---|---|
| **Wikidata stores P356 (DOI) UPPERCASE and P932 (PMCID) WITHOUT the `PMC` prefix** | a `value_norm` lookup misses by construction; oc_graphenricher literally does `literal = entity.upper() if schema == "doi"` | keep `value` (as received) **alongside** `value_norm`, and shape the request per provider — **the same DOI must be lowercased to key litkb's table and uppercased to ask Wikidata** |
| **DataCite lowercases the DOI it returns** — `10.48550/arXiv.N` comes back `10.48550/arxiv.N` | an equality check against the registered form fails | litkb's A1 already casefolds; this confirms it is right |
| **`hub.toolforge.org`'s `isbn:` alias searches P957 (ISBN-10), P3035 and P3097 — NOT P212 (ISBN-13)** | an ISBN-13 hunt misses by construction | ask by bare property (`P212:`), never by the alias. The hub echoes the properties it searched in `context.properties`, so this is checkable |

Plus one **shortDOI** trap: `10/abcde` is a real, resolvable DOI form that litkb's `norm_identifier`
passes through **unchanged**, so one work would hold two rows. Expand it via
`doi.org/api/handles/{sd}?type=HS_ALIAS` (`responseCode` 100 = not found, 200 = no alias, 1 = ok) at
Wave 0 and store only the expanded form.

---

## 4. What this changes in the survey's ladder and in the plan

### 4.1 Stage A — canonicalisation and routing (survey A1 / A2 / A3)

| rung | change |
|---|---|
| **A1** | add the three normalisations of §3.6; add `to_isbn13` **while keeping the ISBN-10** (Wikidata P957 and Open Library both index the 10-form); add shortDOI expansion; add Zotero's `cleanDOI` bracket rule |
| **A3 (DOI-prefix router)** | pair with `doi.org/ra/{doi}` — **the registration agency, not a guess**, then call THAT agency's API. **32 of this corpus's 466 DOIs are Crossref 404s** and the router is what sends them to DataCite instead of booking a miss |
| **A-NEW — zero-network identifier derivation** | `arxiv id → 10.48550/arXiv.{id}`, `isbn10 → isbn13`, `isbn13 → ISBN-A`, `pmcid ↔ bare number`. **Zero requests. The tracker's 42 arXiv-only rows gain a DOI, which unlocks DataCite (B6), `sci.bban.top` (G1a), Anna's scidb-by-DOI (G0d) and Nexus (G1c)** |
| **A-NEW — offline shadow-coverage membership** | import `dois.2020.07.29.sorted.clean.txt.xz` (**from GitHub**, sha256-pinned) and the LibGen scimag DOI TSV into SQLite. Answers `in_scihub_dois` / `in_libgen` **before the ladder spends anything**, prunes G0a/G0b/G0c/G1a/G1b, and **re-classifies litkb's 21 `blocked` + 33 `not-in-archive` rows as OUT-OF-CORPUS vs genuinely blocked.** Under CLAUDE.md §3.5 that is the difference between a measured miss and an undetermined one |

### 4.2 Stage B — the fan-out (survey B2–B5, B12, B15, B16, B20–B22)

| rung | change |
|---|---|
| **B-NEW: OpenCitations META** | one keyless GET returning 4–6 schemes; the densest crosswalk call found |
| **B-NEW: NCBI idconv (batched)** | the doi→pmid→pmcid edge, comma-batched over the whole hunt queue |
| **B4 (Crossref `link[]`)** | extend to *"read `link[]` **and** `alternative-id[]` **and** `issn-type` **and** `relation`"*. **The PII in `alternative-id` is a strictly better Elsevier key than the DOI, and it is already in the response** |
| **B3 (OpenAlex)** | read `ids{}` and `locations[].pmh_id` instead of discarding them. **Note the measured limit: `ids.pmcid` was empty for all 466 works here — do not expect pmcid from OpenAlex** |
| **B5 (Semantic Scholar)** | read `externalIds` on the call B5 already makes. **It is the only source of the 36 PMCIDs and 158 DBLP keys on this corpus** |
| **B12 / B20 / B21 / B22 (the PMC family)** | **currently UNFIREABLE — every one keys on a PMCID litkb has never held.** The survey's instruction to budget no yield here was decided **with the key missing**; that measures the missing crosswalk as much as the missing content. **Worth exactly one honest re-measure after idconv fills pmcid, then keep or drop on evidence** |
| **B15 (NASA ADS)** | **promote from "one more index" to a ROUTE PRE-CHECK.** `esources` + `property` answer "will any free rung fire" in one call. Requires a `bibcode` scheme |
| **B16 / D6 / D13 (DSpace, OAI)** | `hdl.handle.net/api/handles/{h}` resolves a handle — **and a DOI** — to its target URL **without contacting the publisher or the repository**. A free, wall-free replacement for the `doi.org → publisher` redirect at the *resolution* step |
| **B7 → B17 (CORE)** | B17 is a **byte** rung keyed on a CORE id. Add the `core` scheme or B17 can only ever run in the same breath as B7 |

### 4.3 Stage F — the ISBN namespace (survey F2, F5, F6, F9, F10, §4.1, §4.2)

- **F2 (Open Library → ocaid) — WIDEN.** The endpoint accepts **ISBN, OCLC, LCCN and OLID**, and
  HathiTrust's Bib API accepts **the same four**. One key-type table serves both. Add the availability
  gate as a *guard*: `ebook_access ∈ {open, public}` **and** `public_scan_b` **and not**
  `availability.is_restricted`, then `archive.org/metadata/{ocaid}` and refuse on
  `access-restricted-item`.
- **Round 2's §4.2 item 4 is NARROWED, not overturned.** *"Zotero's Open Library translator does not
  even hand off the `ocaid`"* is true **of Zotero**, and false of Open Library: its own `search.json`
  hands you `ia[]` directly, and `goldhac/academic-book-downloader@04f84fb` implements the whole route
  in eight lines with a `difflib` title gate at 0.4.
- **F5 (Google Books) — RE-GRADE** from "no PDF logic to crib" (still true) to **"VERIFIED as a
  crosswalk"**: a free ISBN→OCLC→LCCN bridge dominated by OCLC 42.4 M to 1.5 M.
- **F6 (HathiTrust) — ADD the `us_gov_doc_flag` slice**, the one unrestricted HathiTrust population
  that overlaps agency/forestry literature.
- **F9 — ADD the IPFS dump route** as a *metadata* rung: LibGen.rs publishes its daily non-fiction dump
  over `ipfs.io/<hash>?filename=`, and that dump **is** the md5 ↔ libgen id ↔ ISBN ↔ DOI table,
  obtainable without touching a LibGen web host.
- **F10 (Z-Library) — RE-GRADE to "reachable but NOT addressable."** Search takes free text only; there
  is no ISBN, DOI or hash parameter; delivery needs the `(bookid, hash)` pair. **Z-Library is useful to
  litkb only downstream of Anna's, STC or LibGen's `add{}` bag, which supply the id.** Add the DiamWall
  body-not-status health check to the same guard family as G0a and G0d.
- **Stage F NEGATIVE — rung removal.** **Delete any prospective PDFDrive / OceanofPDF / dokumen.pub /
  epdf.pub rung before it is written.** Keep their filename patterns as *provenance markers*.
- **A NEW free non-PDF terminal state for the book class:** `{ocaid}_djvu.txt` — the OCR text of the
  same IA scan whose `.pdf` is lending-DRM'd. Free, legal, searchable, quotable, `kind != pdf`.
  **This is a concrete instance for the §6.2-item-4 / §4.5 "what counts as having the study" ruling.**

### 4.4 Stage G — the shadow tier (survey G0a–G5, G2a/G2b)

| rung | change |
|---|---|
| **G0a (LibGen DOI→md5)** | **fully specified**, not just "highest-value". Add `&addkeys=*`. **Miss = body `[]`, not a status.** The **UA claim is NARROWED**: libgen-mcp reaches `json.php` with an honest bot UA (`libgen-mcp/<version>`) and has no nginx check anywhere; the UA/Referer wall is real for the **HTML** paths (calibre-lib injects a per-mirror `Referer` *"to bypass anti-scraper mechanisms (e.g. on libgen.li)"*). The surviving cost-free guard is **"assert the body is JSON / `Welcome to nginx` absent, and never judge mirror health on status code"** |
| **G0a-prime — NEW** | `json.php?object=f&md5=<md5>&addkeys=*` — **a rung whose product is IDENTIFIERS, not bytes** (sha1/sha256/crc32/BTIH/IPFS CID/Z-Library id). **It should run even after the download already succeeded by another route** |
| **G0b (Nexus/STC) — PROMOTE ABOVE G0a, and SPLIT IN TWO** | (i) **STC-as-crosswalk** — worth running even when no file comes back, because one DOI query returns libgen ids, zlibrary ids, PMID, ISBNs, parent ISBNs, ISSNs, md5s and CIDs; (ii) **STC-as-delivery** — the disputed half. Anna's own builder has the `nexusstc_id` branch **commented out** with `# TODO: re-enable when Nexus/STC is more reliable` — first-party in-code corroboration that (ii) is unreliable and (i) is unaffected |
| **G0c (Sci-Hub) — three corrections** | (a) **positive miss marker**: the literal body string `Unfortunately, Sci-Hub doesn't have the requested document`; (b) **parse order**: `citation_pdf_url` meta **FIRST**, then `embed\|iframe src`, resolving `//` and `/` against the mirror host — the survey describes only the embed; (c) **NEVER run availability checks concurrently**, and discard an "unavailable" within 5 minutes of a success on the same DOI |
| **G0d (Anna's) — REGRADE, and it is THREE rungs** | (a) `/scidb/<doi>` is *address discovery* and a 302 is **five conditions**; rename `not-in-archive` to `scidb-no-servable-journal-record` and re-read §M's 33; (b) **`/search?q=<scheme>:<value>` is a UNIVERSAL IDENTIFIER LOOKUP** — a new rung reaching Anna's by ISBN, OCLC, PMID, OL id, HathiTrust id or md5, not only by DOI; (c) `/codes?prefix_b64=` is the enumerable form |
| **G1a (`sci.bban.top`)** | **case handling CONTESTED** — scimon does *not* lowercase; the survey says uppercase 404s spuriously. One comparison settles it. And **its HEAD-200 validity test is a DEFECT litkb must not copy** (no content-type, no magic bytes) |
| **G1d (LibGen delivery)** | `ads.php?md5=` → the anchor whose text is exactly `GET` → **require `key=` on the `get.php` URL** → else `library.lol/main/<md5>`, `libgen.me/item/detail/<md5>`, `<mirror>/main/<md5>`, the thousand-bucket direct tree, the IPFS gateway label. Miss marker `"File not found in DB"`. **Prefer `VerifyMD5` over a title match — the address IS the digest** |
| **G2a (Anna's record)** | **UPGRADE from "get the `ipfs_urls`" to "harvest the whole crosswalk."** Same request litkb already makes and already pays for; keep `identifiers_unified` wholesale instead of one key. **ZERO new requests — the cheapest change in this report** |
| **G2b (fast download)** | **ADD THE QUOTA RULE**: `recently_downloaded_md5s` means **a retry after a bad file is FREE**. Replace the single `blocked` with the six statuses (400/401/403/404/429/500) |
| **G-NEW — free quota + presence probe** | `/dyn/md5/summary/<md5>` and `/dyn/md5/inline_info/<md5>`: unauthenticated, `public_cache`d, served as `text/css` for DDoS-Guard. **`summary` returns `downloads_left` without spending one.** Not in the 125-rung ladder |
| **G-NEW — Anna's SciDB as a Sci-Hub oracle** | a SciDB lookup tells litkb whether Sci-Hub holds a DOI **without asking Sci-Hub** — the fix for the 21 `blocked` rows being retried blindly. Preconditions: `aarecords_journals` index, `extension_best == 'pdf'`, a non-ISBN DOI |
| **G-NEW — zero-network Stage A tier** | the offline dumps of §1.6: DOI→md5, ISBN→md5, OCLC→md5 at **zero requests and zero challenge risk**, surviving Anna's being down. **Kam's ruling on whether a torrent fetch counts as "a request to a shadow-library host"** |
| **G-NEW — mirror ranking without probing** | rank from `en.wikipedia.org` + `open-slum.org` heartbeat history + `shadowlibraries.github.io`. **All three are non-shadow hosts, so this is inside litkb's current read rules** |
| **G-guard — session, not solve** | cache the **session cookie** (`sha256(key+mirror) → {cookie, at}`, 6 h, in-memory, key never retained, cookie `aa_account_id2`); *"a bad key still returns 200 with the login form, just no session cookie"* is a free login-failure detector |
| **G-guard — challenge detection REGRADE** | put the **header / `check=1`** test ahead of `<title>` and body. **litkb's `resolve()` disables redirects and will never see a `check=1` `Location`, so a challenge that arrives as a redirect currently reads as a benign hop** |
| **G-date correction** | the Sci-Hub corpus boundary is the file **`dois-2022-02-12.7z`**, so §6.2's "froze around 2021" should read **pre-2022-02**; and an AA `scihub_doi` hit is evidence of membership in that list, **not** that a file exists |
| **G-ledger vocabulary** | adopt libgen-mcp's two sentinels verbatim: **`ErrNotIndexed`** (*"a NORMAL, final answer about one item … it must never put a source in cooldown: a provider that legitimately does not carry an item would otherwise be punished for being honest"*) vs **`ErrSourceUnavailable`** (5xx/429/timeout, cools the mirror 45 s). **litkb's `not-in-archive` and `blocked` map onto exactly these two and today are decided on evidence that conflates them** |
| **G4 (Sci-Net)** | now implementable **and queryable before a token is spent**: Sci-Net reports OA + Sci-Hub availability and resolved provider URLs; its `--budget-check` refuses locally when `balance < reward × DOI count`; `not-found` means *the page did not match the DOI*, so a redirect is not a miss; `fetch` marks `fetched` only after validating the file header |

### 4.5 What it changes in the plan (`Scripts/LITKB_WORKPLAN.md`)

**S4.5 item 1 — "registry identity".** Today it names the Crossref `relation` probe, edges with a third
state, identifier-first duplicates, type-scoped ISBN-13 and a key-LENGTH rule. Round 3 adds five
things, all inside the same item:

1. **The scheme vocabulary is the blocker, not the identity logic.** Add the six Tier-1 schemes
   (`md5`, `pii`, `core`, `bibcode`, `ocaid`, `oai`) plus Tier 2, or S4.6's Stages F and G are
   unreachable by construction and B17/B21/B22/B15/B16 can never be *retried*.
2. **Uniqueness becomes per-scheme data** (`scheme_registry.distinct_values`), because the plan's own
   *"type-scoped ISBN-13"* phrase is already an admission that one blanket index is wrong. Adopt
   WikidataIntegrator's shape rather than special-casing ISBN.
3. **The conflict rule is fatcat's**, verbatim: drop the weaker identifier, assert a work-level
   grouping, **count it**. The plan's *"edges with a third state"* is the right half; the counter and
   the `conflict_source` are the missing half.
4. **Provenance gains `asserted_by` and the input identifier**, and `verified_by`'s five-value CHECK
   widens. `deterministic` becomes a first-class provenance value for Wave-0 edges.
5. **The normaliser table.** `norm_identifier` handles two schemes; adding ten more without normalisers
   means an ISBN-10 and its ISBN-13, or `PMC7391` and `7391`, are **stored as different identifiers**.
   Port the §3.5 list.

**S4.5 item 3 (Stage A) and item 4 (Stage B).** Add the Wave-0 deterministic derivations and the
offline Sci-Hub/LibGen membership table to Stage A; add OpenCitations META and batched NCBI idconv to
Stage B; change B4 from *"Crossref `link[]` with the correct filter"* to *"`link[]` **and**
`alternative-id` **and** `issn-type` **and** `relation`"*. **The plan already schedules B5 and B3 —
this is reading their responses, not adding calls.**

**S4.6 item 2 (Stage F).** The plan says *"the harvest S4.5 schedules cannot produce E20's ISBN, because
Crossref holds none for it"*. That is right for E20 and **the probe now bounds the general case:
Crossref carries an ISBN for exactly 12 of the corpus's 466 DOI-bearing works.** Round 3 adds three
free ISBN sources the plan does not name — Open Library `search.json` (`isbn[]` across every edition),
IA `urn:isbn:`, and Nexus/STC `metadata.isbns` + **`parent_isbns`** — and the last is precisely the
chapter→container routing the plan's `part_of` edge needs. Add `isbnlib.editions(isbn,'merge')` as the
edition-clustering step the plan already wants. **F5/F6 stay PROBED not built (the plan is right about
the Cloudflare 403 and the missing partner access), but they are re-graded VERIFIED as crosswalks.**

**S4.6 item 3 (Stage G).** Eight concrete amendments, all above in §4.4. The three that change what
gets *built*: (a) the **zero-network membership table** is a Stage-A rung that needs no new host and
therefore **no `litkb-shadow-hosts` ruling** — it reads GitHub; (b) **G2a's upgrade to harvest
`identifiers_unified` wholesale costs zero new requests and is inside the existing grant**; (c) the
**`/dyn/md5/summary/` quota probe** and the **mirror ranking from Wikipedia/open-slum** are both new
and both cheap, but (a) and (b) are the ones that need no ruling at all. The plan's statement that a
post-2021 paywalled work ends `held/not-acquired` with `retriable=false` should cite **2022-02-12**.

**S4.6 item 5 (the coverage instrument).** It must now distinguish **out-of-corpus** (the DOI is not in
the Sci-Hub list and not in LibGen scimag) from **blocked** and from **not-in-archive**. Without that
split the instrument's `paywalled_residue` column silently absorbs works no shadow rung could ever have
reached.

**A new decision for Kam, or an extension of `litkb-shadow-hosts`:** *does fetching an offline metadata
dump (an AA derived-mirror torrent, a LibGen SQL dump) count as contacting a shadow-library host?* The
greenelab DOI list and the figshare scimag extract do **not** — they are on GitHub and figshare — so
the Sci-Hub/LibGen membership rung can be built under today's rules either way.

---

## 5. Expected effect on coverage, per miss bucket

**Grades: MEASURED = someone ran it and the measuring party is named. ESTIMATED = reasoning from a
verified mechanism plus a known corpus property. UNDETERMINED = the input does not exist yet.**

### 5.1 The external ceiling, now with a per-route decomposition

`greenelab/scihub@b49f7b0` `data/state-of-oa-coverage.tsv`, **290,120 articles**:

| route(s) | available | coverage |
|---|---:|---|
| oaDOI (Unpaywall) alone | 107,315 | **37.0 %** [36.8–37.2] |
| institutional (PennText) alone | 244,867 | 84.4 % |
| Sci-Hub alone | 246,050 | **84.8 %** |
| oaDOI + institutional | 258,249 | 89.0 % |
| **oaDOI + Sci-Hub** | 272,655 | **94.0 % — BELOW Kam's 95 %** |
| institutional + Sci-Hub | 277,316 | **95.6 %** |
| all three | 282,593 | 97.4 % |

Published study: Himmelstein et al. 2018, eLife, `10.7554/eLife.32822`. **MEASURED (external).**

**So 95 % needs at least TWO of {OA ladder, shadow tier, institutional} and lands only just above the
line when it has them.** Three caveats, all narrowing: the population is 2017-era Crossref/Scopus;
"available" means present-in-repository, **not successfully fetched through a challenge**; and the
year table decays monotonically from 2011 (0.703) to 2016 (0.560), so **a modern IEEE TGRS / Elsevier
remote-sensing corpus sits BELOW the 84.8 % headline.**

**And the record-class boundary is now MEASURED, not asserted** (`data/type-coverage.tsv`):
journal-article **77.8 %**, proceedings-article **79.7 %**, book-chapter **14.2 %**, reference-entry
11.5 %, standard 1.5 %, book-section 0.077 %, **report 0.046 % (167 of 361,079)**. The survey's claim
that *"no shadow rung will ever deliver the USFS / USGS / NOAA / King County reports"* is confirmed by
a number.

### 5.2 Per litkb bucket

| bucket | n | what round 3 changes | grade |
|---|---:|---|---|
| **`no-oa-copy`** | 35 | **Free ceiling stays 9 of 35 — MEASURED, unchanged.** The Elsevier PII does **not** move it: the survey's H2-RG already measured that an *unentitled* key returns a first-page stub at HTTP 200. What PII buys is (a) a *better-shaped* H2 request the moment `litkb-tdm-keys` is decided, and (b) a native key for the 90 Elsevier works if entitlement ever arrives. The ~26 paywalled residue is unchanged by any identifier | **MEASURED (ceiling) / ESTIMATED zero (PII effect without entitlement)** |
| **`not-in-archive`** | 33 | **The label overstates the evidence** (§1.3) — the 33 must be re-read against five conditions, not one. §M's typing already shows **5 preprints (a routing error Stage A's router fixes with zero shadow requests), 3 chapters + 1 book (unreachable until `isbn` is populated — and Crossref holds an ISBN for only 12 works corpus-wide), 7 with no Crossref record at all** (→ `refused/unresolved`, never `not-in-archive`). The offline membership table re-types the remainder as out-of-corpus vs genuinely blocked at **zero requests** | **MEASURED (typing) / UNDETERMINED (how many recover)** |
| **`blocked`** | 39 (25 Sci-Hub + 14 OA) | The offline `in_scihub_dois` test answers, at zero cost, which of the 25 could **never** have been served. §M types them: 12 articles, 2 chapters, 1 book, 2 proceedings, 1 preprint, 3 with no record. **Plus a NEW false-negative mechanism: a concurrent availability probe manufactures "unavailable"** — litkb must serialise | **UNDETERMINED, but now cheaply decidable** |
| **`bad-file`** | 26 | Round 3 adds one thing: **`VerifyMD5` on the streamed bytes** wherever the address was a digest, which is free and stronger than a title match, plus Anna's `sha1`/`sha256` as an *external* check on a file obtained anywhere. The survey's ten causes are unchanged and still unread | **UNDETERMINED (nobody has read the 26)** |
| **`manual-step`** | 45 | **Unchanged.** Binary on `litkb-institutional-access`, which is still unasked after three rounds | **UNDETERMINED** |
| **the 222 works with no active file** | 222 | §M's join, MEASURED: the fan-out gives **36 an arXiv id** (a free preprint route the base could not see), **38 a PMID**, **24 a PMCID**, **8 an ISBN**, **11 a `relation` edge** (6 `has-preprint`), **200 a Crossref `link[]`**, and 8 are unknown to Crossref. **The arXiv-id 36 is the largest single free conversion candidate this round surfaces**, and it costs nothing | **MEASURED (identifiers gained) / UNDETERMINED (files gained)** |
| **the 42 arXiv-only tracker rows** | 42 | **Gain a DOI at ZERO requests** via `10.48550/arXiv.{id}`, unlocking DataCite (B6 — the rung that exists *because* `10.48550` is 404 in Unpaywall/OpenAlex/Crossref and 200 in DataCite), `sci.bban.top` (G1a), Anna's scidb-by-DOI (G0d) and Nexus (G1c). **Caveat: treat the constructed DOI as a CANDIDATE until DataCite confirms** — nobody verified that every historical arXiv id has a registered 10.48550 DOI | **ESTIMATED (mechanism ASSERTED-BY-PUBLISHER)** |
| **the 32 Crossref-404 DOIs** | 32 | `doi.org/ra/{doi}` routes them to their real agency instead of booking a miss | **MEASURED (that they 404) / ESTIMATED (recovery)** |

### 5.3 The honest summary of what this round is worth

**This round adds no new PDF source.** Its entire value is that it makes the sources **already on the
ladder addressable**, and that it turns three "miss" labels into measurable distinctions:

- **Zero-cost, zero-ruling, largest first:** harvest `identifiers_unified` wholesale at G2a (263 works'
  records were fetched and discarded); read `alternative-id`, `ids{}` and `externalIds` from three calls
  litkb already makes; derive the `10.48550` DOIs.
- **One evening of keyless calls:** the Wave-1/Wave-2 fan-out, ~6–9 requests per work, batched.
- **One import, then free forever:** the offline Sci-Hub and LibGen membership tables, from GitHub.
- **The ladder's arithmetic is unchanged.** 95 % still needs two of {OA, shadow, institutional}, or a
  ruling on what "has the study" means. **No identifier changes that.**

**S6's stated kill criterion, which this synthesis adopts: if Wave 0 plus one batched OpenAlex call
does not fill `pmid`/`pmcid`/`openalex` for a majority of the 406 DOI tracker rows, the fan-out is not
worth its complexity.** Note that the orchestrator's probe has **already half-fired it in both
directions**: `openalex` filled 466/466 (pass), `pmid` 68/466 and `pmcid` 36/466 (fail on a
non-biomedical corpus). **The honest reading is that the fan-out's value here is NOT pmid/pmcid — it is
`arxiv` (71), `pii` (96, of which 90 Elsevier), `dblp` (158), `isbn` (12) and `md5`.** The kill
criterion should be re-stated against those schemes before S4.5 builds it, by an agent that did not
propose it.

---

## 6. Disagreements, what nobody verified, and ToS as stated by code

### 6.1 Live disagreements this round opens or moves

| # | question | side A | side B | state |
|---|---|---|---|---|
| 1 | **Does `md5` belong in the identifier table?** | **this synthesis + S1 + S2 + S3 + S5**: it is the shadow tier's work *address*, learned **before** bytes exist, and the join key every library takes; `files.sha256` is the wrong hash and the wrong direction | **S6**: hashes and CIDs are storage locations for a *file*, not identifiers of a *work*; A5's Tier-0/Tier-1 rule draws the same line | **OPEN.** Compromise on the table: `md5` (and `sha1`/`sha256`) in `identifiers` **with `distinct_values = false`**; `ipfs_cid`, `btih`, `server_path`, `torrent_path` in the acquisition ledger beside the attempt row |
| 2 | **Is `sci.bban.top` DOI-case-sensitive?** | survey G1a: an uppercase DOI **404s spuriously** | `kenjoe41/scimon@fce51ce` does **not** lowercase before building the path | **UNRESOLVED. One comparison settles it, and no request was sent by anyone** |
| 3 | **Is Nexus/STC alive?** | S3+S4: the schema and the committed notebook records are real and the crosswalk is the densest in the class | round-2 C1: 2026 threads report `libstc.cc` down; Anna's own builder has the branch **commented out** | **SPLIT AND SETTLED THAT WAY**: STC-as-crosswalk VERIFIED, STC-as-delivery DISPUTED |
| 4 | **Does a LibGen `json.php` call need a full Chrome UA?** | survey G0a: *"only a full Chrome UA works"* | libgen-mcp ships an honest bot UA to `json.php` with no nginx check anywhere and a live e2e suite; calibre-lib needs a UA pool **plus a Referer** for the HTML paths | **NARROWED**: the wall is on the HTML paths. The surviving, cost-free guard is "assert the body is JSON / no nginx marker, never judge health on status" |
| 5 | **Should the arXiv version be kept in the key?** | fatcat: **must include `vN`** — each version is a first-class release | Zotero + litkb + arXiv itself: strip it — *"arXiv OAI API doesn't allow to access individual versions"*, and **the 10.48550 DOI is versionless** | **SETTLED for litkb.** fatcat's rule follows from its own entity model, not from arXiv |
| 6 | **`getscipapers`' DOI→md5 coherence** (survey §7 #7) | `libgen.py:find_md5_by_doi` exists to be the oracle | `anna.py` says there is no working external oracle | **NOW ANSWERED BY THREE OTHER CODEBASES**: `json.php?object=e&doi=` is a working oracle (libgen-mcp, with fixtures), and Anna's `/scidb/<doi>` is a *second* one (doi-fetch, francy2222). The internal contradiction in `getscipapers` is still undated, but it no longer blocks G0a |

### 6.2 What nobody verified

1. **Nothing here has run on litkb's rows** except the orchestrator's read-only crosswalk probe. Every
   model, rung and ordering in §3 and §4 is a **RELAYED DESIGN** under CLAUDE.md §3.4c and is
   **UNVALIDATED** until an agent that did not propose it re-runs it.
2. **No request was sent to any shadow-library host by any of the six crawlers.** Every endpoint,
   status code, challenge shape and quota rule in §1 is read from code, **not observed.**
3. **The Anna's mirrors are mirrors.** `henrylzl/annas-archive@7a261075` (2026-03-29) and
   `drok/annas-archive@093f765` (2025-08-15) are third-party GitHub mirrors of a codebase whose
   canonical home is out of bounds. Several mirrors at different dates agree on `utils.py` and
   `UNIFIED_IDENTIFIERS` — **consistency evidence, not proof. Read every Anna's mechanism as "as this
   mirror states."**
4. **Crosswalk DENSITY inside the shadow tier is unknown.** How many works actually carry `pmid`,
   `oclc` or `isbn13` in their aarecord depends on which upstream source contributed the record, and a
   `scihub_doi` record carries **only** `doi` and a synthetic `filepath`. **For exactly the
   journal-article population litkb cares about, the Anna's crosswalk may be thin.** This is the most
   important open question in §1 and it is answerable offline from the dump.
5. **The LibGen scimag column percentages are the 2017-04-07 dump — eight years old.** Column
   *presence* is likely stable; the completeness figures are not re-measured. The current `.li`-generation
   dump names, sizes and cadence are **unknown** (the only evidence is a 2020 config).
6. **The `add{}` key numbers** (850 TTH, 851 SHA1, 852 SHA256, 853 CRC32, 854 eDonkey, 855 AICH,
   856 BTIH, 861 Library, 877 IPFS CID) come from **one** captured record. Treat the numbers as
   observed and the `name_en` labels as authoritative.
7. **`/dyn/md5/summary/` being reachable without a cookie is INFERRED**, from the absence of
   `protect_db_page`/`check_is_member` in the handler plus bitesized using it unauthenticated. **Not
   measured.**
8. **Whether an STC `links[].md5` equals the LibGen `scimag.MD5` for the same DOI.** No record pair
   shows them equal. **Treat "same DOI" as the join and "same md5" as a hypothesis** — Anna's
   per-collection `ipfs_infos[].from` and its separate `sha1`/`sha256` fields suggest one work commonly
   exists as several distinct files.
9. **Whether a fatcat `md5` ever matches an Anna's/LibGen `md5`.** Structurally plausible for
   IA-scanned and repository PDFs, structurally unlikely for publisher PDFs (watermarks,
   re-serialisation). Untestable without contacting a shadow host. **Do not let a plan rest on it.**
10. **Whether the 2020-07-29 Sci-Hub DOI list is still retrievable.** Only the git-LFS pointer was read.
    **No list after 2020-07-29 appears to exist** — absence of evidence.
11. **`classify.oclc.org` liveness** (the ISBN→OCLC/OWI hop). Read in `isbnlib/_oclc.py` only; zero
    GitHub code hits for the host; OCLC retired Classify in 2024. **Assume dead.**
12. **`api.fatcat.wiki` hit rate on this corpus.** The API is confirmed dead; the "richest ext_ids"
    claim is about the **schema**, not about coverage.
13. **The NCBI idconv batch limit.** NCBI documents 200/request; nobody tested it.
14. **Whether every historical arXiv id has a registered `10.48550` DOI.** arXiv states the
    construction rule as current policy. **Wave 0 must treat the constructed DOI as a CANDIDATE** and
    let DataCite confirm before it is written with `asserted_by='datacite'` rather than `'deterministic'`.
15. **Crossref `relation` population** — schema-verified; MEASURED here at **22 of 466** on this corpus,
    so it is real but thin.
16. **`issn-type: "lissn"` in a live record** — schema-defined, never observed.
17. **The AA derived-mirror dump's size, cadence, and whether fetching it is authorised.** Three repos
    consume it; nobody established any of the three. **Kam's ruling.**
18. **`/codes` cost.** Its handler creates a MariaDB stored function per request and walks a
    `seq_1_to_5000` table; whether the public endpoint is rate-limited or challenged is unknown.
19. **Z-Library's ISBN behaviour.** The eAPI has no ISBN *parameter* (verified); whether
    `message=<isbn>` matches in practice is a live-request question nobody asked.
20. **The Calibre store plugins** `ScottBot10/calibre_annas_archive` (263★) and `a-peirogon/cal-annas`
    (39★, *"Real-time uptime data via SLUM"*) — repo metadata only. The latter would be a second
    mirror-resolver implementation.
21. **fatcat's `fuzzycat`** (`match_release_fuzzy`, `fuzzycat.verify`, the
    `EXACT/STRONG/WEAK/AMBIGUOUS/DIFFERENT` ladder wired in `importers/common.py:414-469`) —
    **the strongest single lead this round did not follow.** It is the title-match confidence model the
    survey's B13 guard asks for.
22. **Memory of the World's own dump**, which would carry the `isni` / `viaf_author_id` / `oclc-owi`
    fields Anna's silently drops. `marcellmars/letssharebooks` located, not read.
23. **UbuWeb** — repo located, files not read. No claim made.
24. **The Codex GitHub pass over this class** — owed for the third round running.

### 6.3 ToS and legal, AS STATED BY CODE (Kam decides; nothing here is a recommendation)

- **Nothing in this class carries a machine-readable licence or ToS assertion.** No crawler found one.
- **`frederikemmer/aa-metadata-worker@0e30d53` states a policy in its own docstring** and it is the
  closest thing to a stated boundary anyone found: *"This service never downloads, hosts or proxies
  book files. It only returns stable public identifiers (AA page URL, IPFS CID when known)…"* That is
  precisely the Tier-0 / Tier-1 split A5 proposed, asserted by a third party as its operating rule.
- **Anna's own architecture does NOT encode a shadow/legitimate split.** Every source module is a peer
  with no capability gate. **If litkb copies the architecture it must add the gate itself** (survey
  H17: a compile-time feature plus a runtime env var, so "authorised" is an auditable switch, not a
  code comment).
- **`F0xhopper/Peritus@dc987b4d` encodes a policy judgement as a numeric prior** — `-5.0` for
  `z-lib.org`, `annas-archive.org`, `libgen.is`, `libgen.rs`, `pdfdrive`, `oceanofpdf`, `dokumen.pub`,
  `epdf.pub`, `ebin.pub`, `pdfcoffee.com`, `vdoc.pub`, `idoc.pub`, `docslib.org` — with the written
  rationale that a corpus built on them cites a download site rather than a work.
- **Z-Library's client exposes account creation** (`sendCode` / `verifyCode` against `/papi/` and
  `/rpc.php`) and a per-account daily quota. **litkb must not use either — account creation is
  prohibited** under this session's standing rules, independent of any ruling.
- **Sci-Net is token-economy fulfilment by other humans**, not an index. Its `--budget-check` is
  described by its own author as *"a guard, not a reservation."* Account risk is Kam's call
  (survey G4).
- **The offline artefacts differ from each other in provenance and should not be ruled on as one
  class**: the greenelab Sci-Hub DOI list and the LibGen scimag TSV are **git-LFS blobs on GitHub**;
  the scimag extract is on **figshare with a DOI** (`10.6084/m9.figshare.5231245`); the AA
  derived-mirror metadata and the LibGen SQL dumps are **torrents/shadow-host files**. Only the last
  group plausibly falls under `litkb-shadow-hosts`.
- **Requests to a shadow host that litkb could avoid entirely** — mirror health (Wikipedia,
  open-slum.org, shadowlibraries.github.io), Sci-Hub membership (GitHub), LibGen membership (GitHub or
  figshare) — are all reachable from non-shadow hosts today. **Every one of them reduces shadow contact
  rather than increasing it**, which is the direction a policy gate should favour.

---

## 7. Verified vs asserted

### 7.1 VERIFIED — read as source at a pinned sha, observed in a committed fixture, or observed live this session

- Anna's `UNIFIED_IDENTIFIERS` (~120 schemes), `LGLI_IDENTIFIERS`, `OPENLIB_TO_UNIFIED_IDENTIFIERS_MAPPING`
  (incl. `"annas_archive": "md5"`), `CODES_HIGHLIGHT`, `FileUnifiedData`, the `source_records[]`
  vocabulary, `merge_unified_fields_with_provenance`, `scidb_info`'s five conditions, the fast-download
  six statuses and `recently_downloaded_md5s`, `/dyn/md5/summary` + `inline_info` and their `text/css`
  comment, `search_text` as `"<scheme>:<value>"`, `/codes?prefix_b64=`, `get_scihub_doi_dicts` and the
  `dois-2022-02-12.7z` provenance comment, the 20-gateway IPFS fan-out, and the per-library ingest
  modules (zlib, libgen, ia, ol, oclc, gbooks, hathi, motw, nexusstc) — **all "as the `henrylzl@7a261075`
  mirror states."**
- LibGen `json.php` `object=e|f`, `addkeys=*`, the `[]` miss, the `add{}` identifier bag, the
  `Library="zlib"` row, the `*_id` collection joins, `scimag_archive_path`, the mismatched-DOI
  regression fixture and its three-state Crossref verdict, `ErrNotIndexed` vs `ErrSourceUnavailable`,
  `VerifyMD5`, the `ads.php`/`get.php?key=` delivery chain and its `"File not found in DB"` marker.
- The LibGen dump schemas (`updated`, `fiction`, `scimag`, `hashes`) and the 2017-04-07 per-column
  completeness census over 64,195,945 rows.
- The greenelab membership test, the DOI-list pointer (71,698,648 B, `sha256 ae1c76aa…cedfa04`,
  82,470,219 DOIs), `state-of-oa-coverage.tsv`, `type-coverage.tsv`, `year-coverage.tsv`.
- Nexus/STC `nexus-science.yaml` `unique_fields` + `field_aliases`, and the committed notebook records
  showing one DOI with three `libgen_ids` and four links each with its own md5 and CID.
- The Z-Library eAPI surface (419-line client), its free-text-only search, the `(bookid, hash)`
  delivery pair, the DiamWall content-type health check, `downloads_limit - downloads_today`.
- Open Library `/api/books` four key types, `search.json?fields=…` live response, `/isbn/{isbn}.json`,
  IA `archive.org/metadata/{ocaid}` live response incl. `access-restricted-item`, `urn:lcp:`,
  `{ocaid}_djvu.txt`; HathiTrust's four key types and hathifiles columns; Google Books
  `industryIdentifiers` and Anna's in-code `OTHER`-prefix census.
- OpenCitations META (three keys, live, bidirectional), NCBI idconv (live), Europe PMC `core` (live),
  Crossref `alternative-id` → `S0034425719305152` (live), DataCite `identifiers[]` and
  `IsVersionOf`/`HasVersion` (live), OpenAlex `ids{}` (live), S2 `externalIds` and its 429 (live),
  NASA ADS bootstrap + `esources`/`property` on three works (live), `hub.toolforge.org` and
  `Special:EntityData` (live), `hdl.handle.net/api/handles/{doi}` → the MDPI landing page (live),
  Citoid (live).
- The verified NEGATIVES: `portal.issn.org?format=json` serves HTML at 200 and `api.issn.org` 403s;
  `openlibrary.org/api/volumes/brief/` returns empty (it is HathiTrust's shape); `api.fatcat.wiki`
  returns curl exit 28 / HTTP 000; OCLC Classify has zero GitHub code hits; Aaaaarg is
  `'selected': 0, 'enabled': 0`; PDFDrive/OceanofPDF appear only as a `-5.0` prior and filename regexes;
  Monoskop has no record id; `papis` has no crosswalk; `oc_idmanager`'s ISBN-13 check is broken.
- litkb's own schema: `0001_core.sql:118` (the twelve-scheme CHECK), `:128` (the blanket partial unique
  index), `:137` (`verified_by`'s five values), `0003_write_functions.sql:11-20` (two normalisers),
  `0013_admission.sql:328` / `0014_referee_p2_fixes.sql:253` (the seven identity-bearing schemes), and
  `D:\tools\annas-mcp\aa_fetch.py:611,615` (one key parsed out of ~120).
- The orchestrator's probe over 466 works, recomputed in §0.4 — including the finding that **90 of 92
  Elsevier DOIs carry a PII in Crossref `alternative-id`**, that **all 36 PMCIDs came from Semantic
  Scholar and none from OpenAlex**, and that **Crossref holds an ISBN for exactly 12 works**.

### 7.2 ASSERTED — publisher documentation, repo metadata, README, or a single unverified source

- arXiv's `10.48550/arXiv.{id}` construction rule and its versionlessness (**ASSERTED-BY-PUBLISHER**;
  the single cheapest change in this report rests on it, so Wave 0 must treat its output as a
  candidate).
- OpenAlex's canonical-external-id policy, its one-DOI-per-work rule and its merged-id 301 behaviour
  (ASSERTED-BY-PUBLISHER, its own docs).
- OpenCitations META's full prefix list (`pmcid`, `isbn`, `wikidata`, `jid` named in docs, none
  observed live).
- fatcat's identifier-snapshot TSV **contents** (the description was read, not a file).
- Sci-Net's protocol (its own doc disclaims being an API contract; single-author repo one day old at
  reading).
- The shadow tier's native keys in §2.2 rows for Anna's/LibGen/Sci-Hub/STC/Z-Library where marked —
  taken from the survey's Stage G and not re-verified, because verifying them requires a shadow request.
- UbuWeb, the two Calibre plugins, Memory of the World's direct dump, `marcellmars/letssharebooks`,
  `adolfosilva/libgen.py`, `tonychg/libgen-cli`, `Yetangitu/books` — located, not read.
- `classify.oclc.org` liveness; the WorldCat Search API's current status; the AA derived-mirror dump's
  size and cadence; the current LibGen dump names and sizes; NCBI idconv's batch limit; Z-Library's
  behaviour on an ISBN passed as free text.

### 7.3 One methodological note

**Four of the six crawlers independently reached the same architectural conclusion from different
corpora of code** — that these systems link identifier-to-identifier rather than library-to-library,
and that the file digest is the pivot. That convergence is the strongest evidence in this synthesis,
and it is the one claim here that does **not** depend on any single mirror being faithful to upstream.
Everything downstream of it — which schemes to add, which rung to promote, which label to rename —
does.
