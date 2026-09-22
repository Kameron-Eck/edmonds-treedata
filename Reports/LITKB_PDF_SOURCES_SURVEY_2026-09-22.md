# litkb — PDF sources and extraction survey, rounds 1+2 merged (2026-09-22)

**What this is.** The findings file Kam asked for on 2026-09-22 ("massive GitHub crawls … how other codebases
get their PDFs from every free source … and how they extract information from them … a layered pipeline …
95 percent of the studies having PDFs … a lit review on the OCR process … agreement, especially for LaTeX …
use Codex to search reddit"). It is the record the plan (`Scripts/LITKB_WORKPLAN.md`) points at for every
acquisition and extraction rung it schedules. Every rung here is a DESIGN read in someone else's code
(CLAUDE.md §3.4c): nothing below has run on litkb's rows except the orchestrator's own probes in §0, and no
rung counts until an agent that did not propose it re-runs it on the named rows and its kill criterion fires.

**How it was made.** Two rounds, orchestrated by Fable from the plan-revision session's chat.
Round 1 (workflow `wf_87c486af-659`, 63 min): eleven Opus crawlers, one per source class or extraction
layer (A1 OA resolvers · A2 preprints and repositories · A3 publisher pages · A4 grey, government, theses,
the open web · A5 shadow libraries, read through code and docs only · A6 books and formats · A7 orchestration ·
E1 PDF extraction · E2 OCR of scans · E3 math/LaTeX OCR and verification · E4 post-extraction QA), plus two
Codex agents with web search on reddit and forums (C1 acquisition, C2 OCR), then a synthesizer. Every agent
recorded every URL it fetched; the union became `blacklist-round1.txt` (1,796 lines, seeded with the 26 URLs
of the 2026-09-21 survey). Round 2 (workflow `wf_3c9146c7-518`, 55 min): six Opus crawlers on the leads
round 1 named but did not read (the Zotero translator corpus · waterfall clients · landing-page extractors ·
calibration data and codeless sources · extraction/OCR repos · GitHub topics and awesome-lists), each holding
the blacklist, plus two Codex GitHub searches that DID NOT RUN — Codex's quota was exhausted at 05:06 PDT and
both agents died before a single result (their files hold failure records, not findings; the Codex pass over
GitHub is OWED and is listed in the plan). The round-2 synthesizer merged both rounds into the body below
(125 rungs, 52 new in round 2, 32 re-graded) and `blacklist-round2.txt` (2,505 lines; tracked beside this file as
`Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22_urls.csv`, one URL per line). Worker reports and
blacklists: `D:\tools\claude-config\jobs\litkb-acquisition-survey\`.

## M. Measured by the orchestrator between the rounds

**Measured on litkb's real rows (read-only; metadata and HEAD
requests only; nothing downloaded).** These are the only numbers in this file that were measured on this
corpus, and §0.2 and §6 of the body are built on them:

| measurement | result |
|---|---|
| litkb's own Unpaywall resolver (email configured), asked for all 35 `no-oa-copy` DOIs | answers for 4, all Elsevier bronze, each URL the landing page (`probe_no_oa_copy.csv`, in-process call) |
| OpenAlex `pdf_url`, Crossref `link[]`, Semantic Scholar `openAccessPdf`, landing-page `citation_pdf_url` for the same 35 | 19 advertise a PDF URL; HEAD shows exactly 4 are free `application/pdf` (all arXiv preprints via Semantic Scholar); every Springer, Wiley, OUP, IOP, Cambridge and Elsevier link is HTML or a token-gated endpoint (`probe_head.csv`) |
| Wayback availability for the two dead author copies | census.gov copy archived 2021; the IIASA copy never archived |
| the CRC book's own `citation_pdf_url` (re-run of the head probe as a repository instrument) | HEAD answers 200 `application/pdf`, but the final URL is a Taylor and Francis `preview.pdf` of about 1 MB — a valid PDF that is not the work; the instrument now marks it `PREVIEW-PDF`, and it is S4.5's real row for the stub gate |
| the tracker (`Reports/literature_tracker.csv`) | 460 rows: 406 DOI, 42 arXiv, 2 URL, 10 text only — the 95 % denominator before the record-class filter |
| corpus today (`litkb.main_works`, `main_files`) | 486 works, 263 with an active file (54 %), 233 with searchable blocks |
| Crossref type of the 33 Anna's `not-in-archive` DOIs | 16 journal articles, 5 preprints (a routing error: shadow libraries never index preprints), 3 chapters, 1 book, 1 proceedings, 7 that no Crossref record exists for |
| Crossref type of the 21 Sci-Hub `blocked` DOIs | 12 articles, 2 chapters, 1 book, 2 proceedings, 1 preprint, 3 with no record |
| Crossref type of the 13 open-access `bad-file` DOIs | 10 articles, 3 preprints — landing pages served where a PDF was expected |

Scripts: `qc/instruments/litkb_acq_probe_no_oa_copy.py`, `litkb_acq_probe_head.py`, `litkb_acq_probe_baselines.py` (the repository copies of the jobs-folder probes); outputs under phase4/qc/ as `litkb_acq_probe_*`.

**The honest bottom line, in one paragraph** (body §6.3, which the orchestrator endorses). The demonstrated
number for a corpus of this shape, by legitimate automated means, is about 86 percent: a self-reported
582-paper review of the same shape reached it, and 65 of its 82 misses were closed-access papers with no
free copy anywhere. On litkb's own rows the open-access miss bucket's free ceiling is 9 of 35. Reaching
95 percent therefore requires at least one of: institutional access (never asked; a one-sentence answer
from Kam), the shadow tier for the pre-2021 paywalled slice under Kam's existing grant, the grey-literature
layer round 2 made measurable (USFS Treesearch, USGS, ArcGIS Online, state-library DSpace), or a definition
of "has the study" that admits a quotable non-PDF source. No combination of more open-access indexes gets
there: round 2's union of 24 tools found exactly one source worth adding (NASA ADS).

**Two corrections the orchestrator makes to the body.** (1) Round 1's finding that the census was "a
measurement of a broken instrument" was refuted by measurement and the body's §0.2 now says so; keep the
mechanism (a missing email or a five-minute outage retires the route for a work forever), drop the
conclusion. (2) Codex's round-2 GitHub pass is missing; the body's rung counts and "independent
implementations" column rest on the Opus crawlers alone plus round 1's two Codex forum reports.

---

# PDF sources and extraction — survey rounds 1+2, merged (2026-09-22)

Supersedes `SYNTHESIS-r1.md` wherever round 2 corrected it. Round 1 stands where round 2 is silent;
every round-1 row is reproduced here so this file can be read alone.

**Round-2 reports read** (all under `D:\tools\claude-config\jobs\litkb-acquisition-survey\`):
`R2-zotero-translators.md` (74 URLs), `R2-waterfalls.md` (111), `R2-landing-extractors.md` (82),
`R2-calibration-codeless.md` (127), `R2-extraction-ocr.md` (133), `R2-topics-awesome.md` (188).

**Round-2 reports MISSING**: `R2C-github-acquisition.md` and `R2C-github-ocr.md` — both Codex runs
died on the same quota exhaustion at 05:06–05:07 PDT ("You've hit your usage limit… try again at
9:13 AM"). Both files exist on disk but contain a failure record, **not findings**; between them they
contributed zero of the twenty requested items. The prompts are staged byte-exact and re-runnable
(`R2C-github-ocr.codex.prompt.txt`, md5 `99c73b5ed08c3921931c930dedff99eb`, plus the acquisition
sibling's staged prompt in the session scratchpad). **Two invocation bugs were found and fixed in the
process and are worth keeping**: `codex -C <dir>` / `--cd` is dead in build 0.155.1 on this machine
(`Error: No such file or directory (os error 2)`, reproduces for `/tmp` too) — use
`wsl.exe -e bash -lc 'cd <dir> && exec codex …'`; and the stdin/stdout redirects must happen *inside*
the bash string, because Git Bash cannot open `/mnt/c/...` and a cross-boundary stdin into `wsl.exe`
gives the same `os error 2`.

Nothing in round 2 re-fetched anything on `blacklist-round1.txt` except one deliberate exception
(`unstructured/partition/pdf.py`, because `is_pdf_too_complex` lives in it and round-1 §6.7 assigned
it) and one diagnostic (`api.github.com/rate_limit`).

---

## 0. The gap, the target, and the census AS MEASURED

### 0.1 Where litkb is (unchanged from round 1)

litkb's acquisition ladder today has five rungs: `open_access` (arXiv by id, then Unpaywall's OA
locations via the paper-search MCP), Anna's Archive (`scidb` by DOI, then md5), Sci-Hub mirrors, a URL
hunt, and a manual `--from-file`. There is no institutional proxy.

All-time ledger census by route and status:

| Route | ok | no-oa-copy | not-in-archive | bad-file | blocked | manual-step |
|---|---|---|---|---|---|---|
| open_access | 22 | 35 | — | 19 | 14 | — |
| annas | 22 | — | 33 | 7 | — | — |
| scihub | **0** | — | — | — | 25 | — |
| browser | 17 | — | — | — | — | 45 |
| hunt-url | 1 | — | — | — | — | — |

Bucket totals used throughout this document: **35 `no-oa-copy`**, **33 `not-in-archive`**,
**26 `bad-file`** (19 + 7), **39 `blocked`** (14 + 25), **45 `manual-step`**.

### 0.2 THE CENSUS, AS MEASURED — round 1's finding 1 corrected

Round 1's most consequential claim was: *"The census is not a measurement of what is available. It is
a measurement of a broken instrument."* **That claim overstated the case, and the correction is a
measurement, not an argument.** The orchestrator ran the miss bucket against the live resolvers
between rounds. Verbatim:

> Of the ledger's **35 open-access misses**, litkb's own Unpaywall resolver (email configured) answers
> for **exactly 4** — all **Elsevier bronze**, and in every case the URL is **the landing page**, not a
> file. Semantic Scholar's `openAccessPdf` gives **4 free arXiv preprints** of IEEE / Springer /
> World Scientific papers. **One** dead author copy is in Wayback. **Every** Springer / Wiley / OUP /
> IOP / Cambridge "pdf" link is a paywall page or a token-gated TDM endpoint.
> So the census is **NOT** a broken-instrument artefact (round-1 finding 1 overstated that); the
> open-access miss bucket's **free ceiling is about 9 of 35** without shadow libraries, and the
> remaining **~26 are paywalled**.

What survives of round 1's finding and what does not:

- **SURVIVES — the mechanism.** Every code path round 1 identified is real and still a defect:
  `paper-search-mcp` `unpaywall.py:resolve_best_pdf_url` @ `eabccbc` returns `None` at
  `if not self.email: return None` before any HTTP request (A2); `ourresearch/oadoi` `views.py` returns
  **HTTP 422** when `email` is missing or a placeholder, and the parameter is `?email=`, not `?mailto=`
  (C1); `run.py:43` `DEAD_STATUSES` makes `no-oa-copy` permanently dead and `run.py:391` skips the
  route unless `--retry-dead`; `_fetch_doi_record` collapses 404, 422, 403, 500, timeout **and a broken
  import** into `None`. **A five-minute outage still permanently retires the open_access route for a
  work.** Round 2 found the same class of failure four more times, independently: CatMaster defaults
  `catmaster@example.invalid` (W17); `unpywall@7909fde` and `roadoi@fcadcf7` both validate the email
  client-side while oadoi rejects `example.com` server-side with 422 (W16); exomind `paper-fetch`
  **skips the source and runs the rest** instead of recording a permanent miss (W28).
- **DOES NOT SURVIVE — the conclusion.** With the email configured the resolver answers for 4 of 35.
  The other 31 are not instrument error. **The bucket is mostly paywalled, and no amount of ladder
  hygiene changes that.** Round 1's own A5 boundary said as much from the other side and should have
  been weighted more heavily.
- **SURVIVES AND IS SHARPENED — the landing-page gap.** All 4 Unpaywall answers are **landing pages**.
  litkb requires `body.startswith(b'%PDF-')`, so all 4 book `bad-file` today. That is exactly round-1
  rung C2's territory, and round 2 supplies the missing half: the *choice* among candidates and the
  *acceptance* test (§2).
- **ALSO SURVIVES — the other three structural readings.** A5's reading of the Anna's
  `not-in-archive` rows as probably-false-negatives (challenge pages have no `a[href^='/md5/']`, so a
  block reads as a miss), A5's three separable causes behind the 25 Sci-Hub `blocked` rows, and
  E4/E2's finding that `bad-file` is one bucket where mature codebases have five to eight, are all
  untouched by the new measurement. Round 2 raises sandcrawler's eight to **twelve** (§3).

### 0.3 The target, and what "layered" means

Kam's target is **95 percent of the tracker's studies with a PDF, by automated means**, through a
ladder where a rung worth 3 percent is worth having if it costs nothing when it misses.

Round-1 calibration points, all kept:

- **finnschwall's 582-paper review**: ~500 obtained (**~86%**), 82 missing, of which **65 are
  closed-access with no free copy anywhere** (48 IEEE conference papers) and only 17 OA-but-bot-walled.
- **A5's boundary**: no shadow rung reaches USFS / USGS / NOAA / King County / Seattle reports or theses.
- **A6's boundary**: a book has no DOI, so litkb's `scidb`-by-DOI archive route cannot address books
  **by construction**.
- **E2's boundary**: 95% with a *searchable text layer* is achievable; 95% with *quote-grade* accuracy
  on 1950s–90s scans is not. The plan must say which it means.
- **C1's dissent**: a 95% automated target is **unsubstantiated** by any same-corpus published evidence.

**Round 2 adds an external denominator** (§3) and one new operational principle beyond round 1's eight:

9. **A budget must bound the WORK, not only the host.** Round 1's guards are all per-host or
   per-source; nothing stops a hopeless work consuming the whole ladder. DocsToKG carries a declarative
   budget object (total timeout / attempts / concurrency) checked between every tier and every source
   (W22). *This is what makes "a 3% rung is free" true in wall-clock as well as in request count.*

Round 1's eight principles stand, with two sharpened:

- **Principle 8 ("a miss must be typed") is RE-GRADED in its valuation.** Round 1 called `no-pdf-link`
  "the failure most worth fixing". The Internet Archive's own per-domain triage of its largest
  `no-pdf-link` domains finds **four causes and only one is a parser bug** (§3). Keep the status; drop
  the claim about its value.
- **Principle 2 ("a failed index is a recorded Attempt, never silence") gains two more independent
  implementations** — DocsToKG makes `breaker_open` an `AttemptResult` and carries a `retrieval_trace[]`;
  `docxology/literature` records `retriable: true|false` **per attempt** (W24, C14). litkb hard-codes
  retriability per *status*, which is precisely what `DEAD_STATUSES` is made of.

---

## 1. The master acquisition ladder, MERGED

Ordered by **(cost per miss ascending, expected catch descending)**. **★ = litkb already has it.**
**NEW** = added in round 2. **RE-GRADE** rows sit directly beneath the round-1 rung they correct.
The **impl** column counts *independent* implementations read as code at a pinned sha across both
rounds (`R2-topics-awesome` §4 and `R2-waterfalls` §5, with the fetchpdf/finnschwall shared identity
lineage collapsed to one).

**Counts: 125 rungs** (73 from round 1 + **52 new in round 2**), **32 round-1 rungs and guards
re-graded** (28 rungs: A4, B2, B4, B7, B12, B14, C1, C2, C4, C5, C6, C7, D1, D6, D8, D10, D11, E1, E2,
E5, F5, F6, F10, H1, H2, H4, H5, H6 — plus guards 2, 3, 4 and 6), and **29 guards** (10 from round 1 +
19 new). D7 and D18 are recorded NEGATIVES, not rungs.

### Stage A — zero network at hunt time (cost literally 0 requests)

| # | Rung | Returns | Converts | Expected catch | Guard | Code | Impl | Grade |
|---|---|---|---|---|---|---|---|---|
| A0 | **Record-class filter** — drop `conference_abstract`, `poster`, `withdrawn`, `correction`, `paratext`, `not_an_article` from Crossref metadata | a routing decision | — | Removes works that can never have a PDF from the 95% denominator | flag, don't delete; keep `retracted` fetchable | `finnschwall` | 2 | VERIFIED |
| A1 | **Identifier canonicalisation** — `isbnlib.to_isbn13`, DOI lowercase, strip `https://doi.org/` | canonical ids | — | Silent-miss removal (an uppercase DOI 404s on `sci.bban.top`; an ISBN-10 kept makes every ISBN rung miss) | `isbnlib.notisbn` rejects, never coerces | `xlcnd/isbnlib@ddc62f2` | 2 | VERIFIED |
| A2 | **Work-class classifier** — paper / chapter / book / report / thesis / HTML-only | a routing decision | not-in-archive | **This is what unblocks the book path** | Crossref salvage: `other + ISBN + container-title → bookSection` | Crossref routing, Zotero | 2 | VERIFIED |
| A3 | **DOI-prefix router** — `10.48550`→arXiv, `10.31223`→EarthArXiv, `10.31219/31235/31234/32942`→OSF, `10.21203`→Research Square, `10.22541`/`10.36227`→Authorea/TechRxiv, `10.26434`→ChemRxiv, `10.1101`→bioRxiv, `10.5281`→Zenodo, `10.20944`→Preprints.org | a native API to call | no-oa-copy | EarthArXiv is the geoscience preprint server — disproportionately relevant here | prefixes are registrant-owned, so false positives are near-impossible | Zotero `OSF Preprints.js@c830037` | 3 | VERIFIED |
| A4 | **Deterministic publisher URL construction from the DOI** — Copernicus/ISPRS, Project Euclid, Springer `/content/pdf/{doi}.pdf`, Frontiers, MDPI `+"/pdf"`, JMIR, Atypon `/doi/pdf/{doi}`, ACM `?download=true`, JSTOR `pdfplus…acceptTC=true` | a candidate URL | no-oa-copy, blocked | **MEASURED (r1 A1)**: ISPRS → 200 `application/pdf` **1,916,748 B**; Project Euclid 1979 *Ann. Statist.* → 200 **2,337,841 B**. Any ISPRS or old-stats row in `no-oa-copy` is a plumbing bug | a 200 that is HTML → the Stage-C gate | Zotero `c830037`; `findpapers`; `ref-downloader` | 4 | VERIFIED |
| **A4-RG** | **RE-GRADE — Springer's template has NO access check.** `Springer Link.js` pushes `/content/pdf/{DOI}.pdf` unconditionally, so **every closed Springer item yields a paywall page** | — | — | — | **pair the template with an identity gate (C10) or it manufactures `bad-file` rows** | `Springer Link.js@c830037` | 1 | VERIFIED |
| A5 | **Rule-based openness pre-check** — DOAJ ISSN, OA publisher, DOI prefix, licence URL | an ordering hint | — | ordering only | the next rung checks bytes | `oa_local.py` (oadoi family) | 1 | VERIFIED |
| **A6** | **NEW — MDPI CDN URL built from the DOI**: `mdpi-res.com/d_attachment/{journal}/{journal}-{vol}-{art}/article_deploy/{journal}-{vol}-{art}.pdf` | PDF bytes | **blocked, bad-file, no-oa-copy** | **The highest-yield single item of round 2, and MEASURED**: `mdpi-res.com/d_attachment/remotesensing/remotesensing-14-05081/article_deploy/remotesensing-14-05081.pdf` → **200, `application/pdf`, 2,366,188 bytes** for `10.3390/rs14205081` — **the exact DOI round 1 measured as HTTP 403 Cloudflare on `www.mdpi.com`**. Negative control (article 99999) → 404 `text/html`, so the rung declines cleanly. A second journal (`forests-11-00001`) also 200/PDF. A second team reports 16/17 sampled DOIs hitting on 2026-09-05 | slug tried as DOI code **and** as the de-spaced journal title; the source's journal map lacks an `rs` entry — a data fix, not a mechanism fix | `drpwchen/paper-fetch@85ecdf81`; live probe by R2-waterfalls | 2 | **MEASURED** |
| **A7** | **NEW — EarthArXiv OAI-PMH harvested OFFLINE into a published-DOI → preprint-PDF map**: `GET https://eartharxiv.org/api/oai/?verb=ListRecords&metadataPrefix=oai_dc` (also `jats`) | a local lookup table | no-oa-copy | **MEASURED**: 7,670 records; in one 50-record page **50/50 carry a direct PDF URL**, **32/50 (64%) carry the PUBLISHED-version DOI**, 50/50 carry `dc:rights`. HEAD on a download URL → 200 `application/pdf`, 9,507,602 B, with `Content-Disposition` filename. ~154 pages harvests the whole server | a harvested map **cannot be blocked and cannot record an outage as a permanent verdict** — the defect class of §0.2 | Janeway 1.8.0 OAI (`resumptionToken` carries `completeListSize`); live probe by R2-calibration | 1 | **MEASURED** |
| **A8** | **NEW — USFS Treesearch sitemap enumeration** → `research.fs.usda.gov/download/treesearch/{id}.pdf` | PDF URL | not-in-archive | **MEASURED**: JSON:API is OFF (404 on `/jsonapi/`, `/jsonapi/node`, `/jsonapi/node/publication`). `/sitemap.xml` is a Drupal simple_sitemap index of **15 pages**; page 3 alone holds **5,000 `<loc>`, all `/treesearch/{id}`**; each record page carries `<meta citation_doi>` **and** `<meta citation_pdf_url>`; ids are dense integers, so the PDF URL is constructible without the landing page. HEAD `/download/treesearch/5630.pdf` → **200 `application/pdf` 95,065,463 B**. This settles round-1 D1's open endpoint question | title + author + year identity at 0.85 | live probe by R2-calibration | 1 | **MEASURED** |
| **A9** | **NEW — extended DOI-prefix → PDF-URL table** beyond A4: **Cambridge Core** `core/services/aop-cambridge-core/content/view/{seg}/{seg}.pdf` (*the only implementation found in either round*), IOP `article/{doi}/pdf`, World Scientific, ASM, Liebert, De Gruyter, PLOS `article/file?id={doi}&type=printable`, Hindawi CDN, eLife `articles/{id}.pdf`, APS `link.aps.org/doi/{doi}`→`/pdf/{doi}`, SciEngine, JMIR, PNAS / JNeurosci `full.pdf`, IJCAI, ISCA, SAGE, IOS Press, Sciendo, SciELO, Pensoft, AIMS, CSP, F1000, IET-on-Wiley, `10.31234`/`10.31219`→`osf.io/{id}/download` | candidate URLs | no-oa-copy, bad-file | 0–2 works each; **each costs a GET already being spent on a landing page**. World Scientific matters specifically — §0.2 names it among the publishers whose "pdf" links are paywall pages in litkb's own bucket | **one row is WRONG and flagged**: FedHarv's `10.3390` → `www.mdpi.com/{doi}/pdf` is not MDPI's path shape; use A6 | `pvcalarco/FedHarv@f6041f72` (22 prefixes + 27 domain transforms); `Panda-of-Axin/Freepaper@4e7c51b0`; `docxology/literature` `doi_to_pdf_urls` | 4 | VERIFIED (except the MDPI row) |
| **A10** | **NEW — candidate-URL canonicalisation with ROLES** (`metadata` / `landing` / `artifact`), de-duplicating without destroying signed CDN parameters | a deduped, typed candidate list | cost per work | Free, and it is what stops a 12-index fan-out spending six GETs on one file. Round 1 canonicalises *identifiers* (A1) but never *candidates* | Zotero's own de-dup strips every param except `download`; a signed `sciencedirectassets` URL must be exempt from that | DocsToKG; Zotero `attachments.js` | 2 | VERIFIED |

### Stage B — metadata fan-out (≈1 cheap API call each, ALL CONCURRENT; wall-clock = slowest, not sum)

| # | Rung | Returns | Converts | Expected catch | Guard | Code | Impl | Grade |
|---|---|---|---|---|---|---|---|---|
| B1 | **Identifier already carries the file** — S2 `openAccessPdf`, arXiv id, ACL id, CVF title, OSTI `links[rel=fulltext]` | PDF URL | no-oa-copy | **0 extra requests.** **MEASURED between rounds: S2's `openAccessPdf` yields 4 free arXiv preprints of IEEE / Springer / World Scientific papers inside litkb's own 35-row miss bucket** | a `doi.org` URL in `openAccessPdf` is not a PDF; **for MDPI, S2's `openAccessPdf` URL is the walled `www.mdpi.com` one** | `finnschwall`; orchestrator probe | 14 | **MEASURED** |
| B2 ★ | **Unpaywall, iterating `oa_locations` — not just `best_oa_location`** | 0–n locations | no-oa-copy, bad-file | 25.26% hit on 10k random Crossref DOIs, 78.17% of hits a direct PDF. **On litkb's own miss bucket: 4 of 35, all Elsevier bronze, all landing pages** | `best_oa_location.pdf_url` is null for ~50% of gold-OA MDPI works (r1 A7) → iterate the whole array and keep `url_for_landing_page` as a Stage-C input. Needs `?email=` or 422 | `oadoi@f3f5391`; `unpywall@7909fde`; `roadoi@fcadcf7` | 11 | VERIFIED |
| **B2-RG** | **RE-GRADE — Unpaywall has NO batch DOI endpoint.** Round 1's B2 claims a batch `POST /v2/dois`. **Neither canonical client uses one**: `roadoi@fcadcf7` loops `plyr::llply(dois, oadoi_fetch_, email)` with `query = list(email = email)`; `unpywall@7909fde` loops `for doi in dois` over a disk cache; roadoi sets `api_limit <- 100000` above a comment pointing heavy users at the **data dump**. OpenAlex batches; **Unpaywall does not** | — | planning | do not budget wall-clock as if it batched | `roadoi`, `unpywall` | 2 | VERIFIED |
| B3 | **OpenAlex** `works/doi:{doi}`, batched `filter=doi:A\|B\|C` | `locations[].pdf_url` + identifiers | no-oa-copy | **DISPUTED (§7 #1)** — excellent keyless title→identifier resolver; **measured 0 net-new full text** over Unpaywall on 69 previously-unretrievable DOIs | as B2 | `pyalex`; computron issue #11 | 13 | MEASURED both ways |
| B4 | **Crossref `link[]` TDM array** | PDF URL **including for CLOSED works** | no-oa-copy, blocked | **r1 A1 measured 7 of 7 controls returning a PDF URL**, including closed IEEE TGRS and OUP Forestry. litkb queries Crossref for metadata and never reads `link[]` | match `'pdf' in content_type` **OR** `'pdf' in the URL path` — MDPI's content-type is `unspecified`. **BUG: `oadoi` `pub.py:crossref_text_mining_pdf` tests `content-version` twice, so the TDM hint is dead in Unpaywall production** | `metapub@5149380`; `olivettigroup/article-downloader@dfe77aa` | 16 | VERIFIED |
| **B4-RG** | **CONFIRM + SHARPEN — Crossref's MDPI `link[]` points at the Cloudflare-403 host.** MEASURED this round: MDPI rows return `www.mdpi.com/2072-4292/{v}/{i}/{a}/pdf` with content-type `unspecified` and `intended-application: similarity-checking`. **B4 is not wrong, it is incomplete: B4/B2 identify the article, A6 fetches it.** Also MEASURED: `has-full-text:true` on `/journals/2072-4292/works` → **43,455** works; `full-text-type` is rejected **HTTP 400 filter-not-available** on the `/works` route, so the filter vocabulary is per-route and must be probed | — | — | — | Crossref live probe | 1 | **MEASURED** |
| B5 | **Semantic Scholar Graph** `openAccessPdf`, `externalIds`, `references.openAccessPdf` | PDF URL + ids | no-oa-copy | Genuinely distinct from OpenAlex — r1 A1 found `hal.inria.fr` for a TGRS DOI OpenAlex reports `closed` | unauthenticated 429s poison it; `SEMANTIC_SCHOLAR_API_KEY` is BLANK in `D:\edmonds-pipeline\secrets\paper_search.env` | `danielnsilva/semanticscholar` | 14 | VERIFIED |
| B6 | **DataCite** `dois/{doi}` + `?query=` title search | metadata + file links | no-oa-copy | **The blind spot**: `10.48550/arXiv.1706.03762` is 404 in Unpaywall, OpenAlex **and** Crossref, 200 in DataCite. Every DataCite-registered DOI (arXiv, Zenodo, figshare, many theses and agency reports) is invisible to the three Crossref-derived resolvers | verify the returned DOI against the requested one | — | 1 | VERIFIED |
| B7 | **CORE v3** `search/works?q=doi:"{doi}"` (**quoted** — 3.1M results vs 56 unquoted) | `downloadUrl`, `sourceFulltextUrls`, `fullText` | no-oa-copy, not-in-archive, blocked, scan-needs-ocr | 300M+ records, **32.8M hosted by CORE itself → publisher blocks do not apply**. Best single rung for theses and agency reports | **`fullText` can be the literal 35-char string "Not available for public API users." — truthy, means no.** `CORE_API_KEY` is BLANK | `NatLabRockies/elm@d227fd6`; `finnschwall` | 8 | VERIFIED |
| **B7-RG** | **RE-GRADE — there is no vendor CORE v3 client, and the v3 schema is STILL unresolved.** CORE's own `oacore/pyoacore` (pushed 2026-08) targets `https://core.ac.uk/api-v2` with a two-field Article model `{'id','title'}`. Live this round: `api.core.ac.uk/v3/` → **404**; `/v3/outputs/1` → **429** unauthenticated with no body; `api.core.ac.uk/swagger/v3.json` still unreachable. **Salvage**: CORE's bulk idiom is `articles_search_api_call(query='repositories.id:'+id, pageSize=1000)` — a whole-repository dump by id (D15) | — | — | round 3 needs `CORE_API_KEY` set to record the v3 field list | `oacore/pyoacore` | 1 | MIXED |
| B8 | **DOAJ** `api/v2/search/articles/doi:{doi}` → `link[type=fulltext]` | a non-publisher fulltext link | no-oa-copy | Low-moderate; confirms gold and gives a link that is not the blocking publisher | **Query the API, not the article page** (the page 403s with `cf-mitigated: challenge` a second after the API 200s). **CONFIRMED by a negative**: Zotero's `DOAJ.js` loads Embedded Metadata then executes `item.attachments = [];` — it **discards the PDF on purpose**, so there is nothing to port from Zotero here | Zotero `DOAJ.js@c830037` (2025-08-08) | 7 | VERIFIED |
| B9 | **OpenAIRE** `search/publications?doi=&format=json` | instance URLs | no-oa-copy | Low on a US corpus; it lists Crossref and Unpaywall among its own sources, so do not add its coverage to theirs | feed URLs back to Stage C | `paper-search-mcp` (installed) | 5 | VERIFIED |
| B10 ★ | **arXiv API** by id or title | PDF URL | no-oa-copy, blocked | **High for the ML/CV/statistics slice, and the route to paywalled IEEE TGRS**: r1 A7 measured 5 of 8 OA TGRS PDFs live at arXiv and never at IEEE; §0.2 measured 4 such preprints in litkb's own bucket | **rewrite the host to `export.arxiv.org`** (`arxiv.py` issue #87 records bulk users being blocked); `_parse_feed` retries recursively with no back-off and no 429 handling; paperscraper's regex misses pre-2007 ids (`math/0309285`); the API **406s without a browser-ish `Accept`** | `lukasschwab/arxiv.py@09d1b8b` | 14 | VERIFIED |
| B11 | **OSF APIv2** two-hop `/v2/preprints/{id}/` → `relationships.primary_file` → `data.links.download` | PDF bytes | no-oa-copy | ~30 preprint servers on one API; **EcoEvoRxiv is the forestry/ecology community** | 404 is a clean miss | Zotero `OSF Preprints.js@c830037` | 2 | VERIFIED |
| B12 | **Europe PMC** via `ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf`, or `/fullTextXML` for JATS | PDF or JATS | no-oa-copy, scan-needs-ocr | **r1 A1 measured no hit for ALL 7 control DOIs — budget ZERO yield from the whole PMC family.** Keep only because a GET costs nothing; r1 A7's counterpoint is that as a *late* rung it recovered 12 of 109 failures | `/fullTextPDF` **404s**; `/fullTextXML` is the documented route | `Aperivue/medsci-skills@d7df514`; `finnschwall` | 9 | MEASURED ZERO here |
| **B12-RG** | **RE-GRADE — selection needs THREE fields, not two.** Round 1 keys on `inEPMC` + `hasPDF`. `ContentMine/getpapers` `lib/eupmc.js@915fc89` keys on `hasPDF !== 'N'`, then filters `fullTextUrl` on `documentStyle === 'pdf'` **AND** `availabilityCode === 'OA'`; Zotero's `Europe PMC.js` reaches the same rule independently. Cheaper to get right; **does not change the zero-yield verdict** | — | — | — | `getpapers@915fc89`; Zotero `Europe PMC.js` | 2 | VERIFIED |
| B13 | **Conference venue ladder** — OpenReview `/notes/search`, `papers.nips.cc`, CVF, ACL Anthology, PMLR, ECVA, AAAI | direct PDF | no-oa-copy, not-in-archive | ~100% for those venues; **CVF is the ONLY route for CVPR/ICCV papers whose IEEE DOI is unserved by IEEE** | title-match false positives are the real risk → author-surname **and** year agreement, record the matched title. OpenReview's `content.title=` form 403s; CVF's directory listing 403s (parse the conference index) | `J1mL1/arxiv2conf@2aac563`; `openreview-py@6144ee9` | 3 | VERIFIED |
| B14 | **Zenodo / HAL / figshare direct** | PDF | no-oa-copy | individually low, collectively the classic 3%-rung | **`HAL._resolve_pdf_url` accepts any 200 even when content-type is not PDF** — it hands landing pages downstream as PDF URLs | `paper-search-mcp@eabccbc` | 5 | VERIFIED (incl. the bug) |
| **B14-RG** | **RE-GRADE — Zotero's Zenodo rule lives in `InvenioRDM.js`, not `Zenodo.js`** (which does not exist at `c8300377`). It covers Zenodo **plus 12 hosts** (CERN, Caltech Data, TU Graz, TU Wien, NYU UltraViolet, Tübingen FDAT, Hamburg FDR, RODARE, Aperta, INFN, BNL) with one rule: the `citation_pdf_url` meta, metadata from `{record}/export/csl`. **HAL has no Zotero translator at all** | — | — | — | `InvenioRDM.js@c830037` (2026-05-19) | 1 | VERIFIED |
| **B15** | **NEW — NASA ADS**: keyless `GET api.adsabs.harvard.edu/v1/accounts/bootstrap` → `access_token`; `POST /v1/export/ris` with Bearer; PDF at `ui.adsabs.harvard.edu/link_gateway/{bibcode}/ARTICLE` (mosaic uses `PUB_PDF`, reads the `OPENACCESS` property, and takes the arXiv id out of `identifier[]`) | PDF URL + a second independent arXiv id | no-oa-copy | **The one genuinely new source in a 24-tool union that is aimed at this corpus** — ADS indexes IEEE TGRS, ISPRS and Remote Sensing of Environment well | verify the bibcode maps to the requested DOI | `szaghi/mosaic@64b9919` `sources/nasa_ads.py`; Zotero `NASA ADS.js` → `ADS Bibcode.js` | 2 | MIXED (route read twice, gateway never probed) |
| **B16** | **NEW — DSpace 7 REST bitstream walk**: `/server/api/core/items/{uuid}` → `_links.bundles` → bundle `ORIGINAL` → `_links.bitstreams` → first `*.pdf` → `_links.content.href` | PDF bytes | no-oa-copy, not-in-archive | **Every DSpace 7 site answers this with no key** — NOAA IR, World Bank OKR, most institutional repositories since 2022. **Strictly better than D6's OAI-PMH METS route**, which returns metadata rather than files | bitstream URLs carry **no `.pdf` extension**, so the acceptance gate must not filter on extension (C21) | Zotero `FAO Knowledge Repository.js@c830037` `addPDFAttachment` (2026-02-09) | 1 | VERIFIED |
| **B17** | **NEW — CORE download endpoint** `core.ac.uk/download/{id}.pdf`, with id-variant retry | PDF bytes | no-oa-copy, bad-file | The **byte-delivery half** of B7, which is a search rung only. CORE indexes exactly the grey/agency material this corpus needs | CORE's redirect instability is a distinct failure mode from a miss — type it | `mims-harvard/ToolUniverse` | 1 | VERIFIED |
| **B18** | **NEW — Semantic Scholar web page JSON-LD**: `script.schema-data` → `@graph[1][0].mainEntity` when it contains `pdfs.semanticscholar.org` or `.pdf` | PDF URL | no-oa-copy | A second, independent S2 surface for when the Graph API's `openAccessPdf` is null; needs no browser to parse | as B5 | Zotero `Semantic Scholar.js@c830037` | 1 | VERIFIED |
| **B19** | **NEW — PubMed `free full text[sb]`** when Unpaywall says closed | an openness answer | no-oa-copy | Low here (~1–3%): PubMed's remote-sensing and forestry coverage is thin. Worth it because Unpaywall records *closed* for articles a publisher opens without a CC licence — two independent openness indexes | two cheap GETs | `drpwchen/paper-fetch@85ecdf81` | 1 | VERIFIED |
| **B20** | **NEW — Europe PMC `fulltextRepo` format manifest** (`type=METADATA` → `files[]` → `type=FILE`) | what formats exist, before any bytes move | no-oa-copy, bad-file | Low (0–3%); one GET on a PMCID already held. **Round 1's ladder never had `fulltextRepo` at all** | — | `drpwchen/paper-fetch@85ecdf81` | 1 | VERIFIED |
| **B21** | **NEW — DOI→PMCID across two converters, then `europepmc.org/articles/{PMCID}?pdf=render`** | PDF bytes | no-oa-copy | Same slice as B20. **The operative fact is a negative**: the `pmc.ncbi` PDF path serves **reCAPTCHA**, and the REST `fullTextXML` is XML not PDF — so `?pdf=render` on europepmc.org is the byte route. Confirms r1 A1 rung 6 / A6 / E4, whose `?pdf=render` the round-1 master ladder had dropped | reCAPTCHA marker in the first 4 KB (guard 3) | `drpwchen/paper-fetch@85ecdf81` | 2 | VERIFIED |
| **B22** | **NEW — PMC OA Web Service** `oa.fcgi?id={PMCID}` | a file location | no-oa-copy, blocked | Bytes with no publisher in the path; same slice as B20 | `%PDF-` gate | named in r1 A6, implemented in `paper-fetch` | 1 | MIXED |
| **B23** | **NEW — bioRxiv/medRxiv version resolution** via `api.biorxiv.org/details` **before** building the PDF URL | the current version number | no-oa-copy, bad-file | Tiny for this corpus, but **the failure it fixes is total**: a hardcoded `v1` 404s whenever a v2 exists, and three tools read this round hardcode v1 | — | `kermitt2/biblio_glutton_harvester@a011f149` | 1 | VERIFIED |
| **B24** | **NEW — ERIC**: keyless `api.ies.ed.gov/eric/?search=id:{n}&format=json&fields=*`; file at `files.eric.ed.gov/fulltext/{id}.pdf` | PDF | not-in-archive | Education-side grey literature; the record page's "PDF on ERIC" image **is** the access check | that image gate | Zotero `ERIC.js@c830037` (2024-07-05) | 1 | VERIFIED |
| **B25** | **NEW — Europe PMC `supplementaryFiles`** | datasets / appendices | the extraction layer | Near-zero for PDFs, non-zero for appendices. Round 1 only ever *rejects* supplementary material | never let a supplement win the main-article slot (C9) | `mims-harvard/ToolUniverse` | 1 | VERIFIED |
| **B26** | **NEW — Ai2 Asta MCP `snippet_search`** — full-text excerpts **without a PDF** | a quotable passage | no-oa-copy | **The only route found in either round that supplies a quotable passage for a work litkb may never hold a file of** — it serves `record_use` directly rather than the file count | a snippet is `kind != pdf` and must not enter the 95%-with-PDF numerator | named in a skill document; **never called** | 1 | ASSERTED |
| **B27** | **NEW (ordering rung) — prefer structured full text over PDF.** `fetchpdf`'s `--prioritize-xml` takes JATS/TEI **when it exists**, changing the ladder's ordering and not merely its bookkeeping | JATS/TEI | extraction quality | ~0 for the PDF count; **medium for extraction**, because JATS needs no OCR, no dehyphenation and no ligature repair | a JATS capture is `kind=jats`, a different outcome from a PDF (r1 principle 7) | `The-Metascience-Observatory/fetchpdf@82a4c474` | 1 | VERIFIED |

### Stage C — turn a candidate into bytes (ordered; each rung spends bytes)

Round 2's single largest contribution is here. Round 1 §0.2 framed `bad-file` as "a missing
landing-page→PDF step"; that is right but incomplete. **All eleven implementations read in round 2
have the landing-page step. What separates them is the CHOICE among candidates and the ACCEPTANCE
test.** OmicsOracle has a landing-page parser and still cannot fetch a PLOS PDF, because its validator
requires `'pdf'` in the URL while its own PLOS selector targets `article/file?id=…&type=printable`.
**Adding C2 to litkb without C9's scoring and C10's identity predicate converts `bad-file` into
wrong-file, which is worse.**

| # | Rung | Returns | Converts | Expected catch | Guard | Code | Impl | Grade |
|---|---|---|---|---|---|---|---|---|
| C1 ★ | **GET the candidate; accept only on body magic** | bytes or a reason | bad-file | The gate, not a source | body magic beats the header; an ENCRYPTED PDF (`/Encrypt N N X >> startxref`) is rejected outright | `oadoi@f3f5391` `webpage.py:is_a_pdf_page`, `pdf_util.py:is_pdf` | 5 | VERIFIED |
| **C1-RG** | **RE-GRADE — round 1's acceptance rule is weak in three ways and one of them REJECTS VALID PDFs.** Replace `body.startswith(b'%PDF-') AND Content-Length >= 128` with the five-verdict function: (a) **`body[:32].lstrip().startswith(b'%PDF')`** — a bare `startswith` rejects a PDF whose body begins with whitespace or a BOM; (b) **minimum 5,000 bytes**, not 128 — 128 is 1,000× below `MIN_PDF_BYTES` and passes nearly every publisher stub; (c) **mojibake test on the first 64 bytes**; (d) **`%%EOF` within the last 8 KiB**, else `early_eof_with_trailing_payload`. Verdicts: `html_response` / `too_small` / `missing_pdf_header` / `corrupt_pdf_header` / `early_eof_with_trailing_payload` / ok — **directly usable as litkb `bad-file` sub-statuses** | five verdicts | **bad-file split** | — | `Rimagination/instsci@836cd6b6`; `EvenStarArwen/CiteClaw@2b448046`; `ZimoLiao/scholaraio@c3a4b265` | 3 | VERIFIED |
| C2 | **If HTML → `citation_pdf_url` meta-tag scrape**, suffix-matched so it also catches `bepress_citation_pdf_url` and `eprints.citation_pdf_url`; plus `wkhealth_pdf_url`, `eprints.document_url`, raw-regex fallback | PDF URL | **bad-file, blocked, no-oa-copy** | **THE highest-yield single rung in the whole survey**, named independently by every round-1 crawler and by five independent implementations in round 2. MDPI, Copernicus, USFS Treesearch, DSpace, bepress, EPrints, OJS, Janeway and ResearchGate all emit it; **147 Zotero publishers have no other rule at all** | the tag can point at a different article, an abstract, an appendix, or a 1-page purchase interstitial that is itself a valid PDF → C9 + C10 | Zotero `Embedded Metadata.js@c830037`; `paperscraper@7cce0a1` | 5 | VERIFIED |
| **C2-RG** | **RE-GRADE — round 1's selector is a SILENT MISS in three ways.** (a) It suffix-matches `@name` only; **`ResearchGate.js` reads `meta[property="citation_pdf_url"]`** — match **both attributes**. (b) Zotero's `getContent` XPath searches **`<body>` as well as `<head>`** (`/x:html/*[local-name()="head" or local-name()="body"]/x:meta[…]`); several CMSes emit citation meta in the body. (c) **The PDF URL is never resolved against the document base** — Embedded Metadata pushes `pdfURL` raw and Zotero resolves it later in the browser; its own comment says "URLs in meta tags can technically be relative", so **a Python port must `urljoin` it itself**, and must append `/` to a base with no trailing slash before doing so, or the rescue URL resolves under the parent path and 404s (the PMC case). Also new: **`og:pdf`** as a second meta key, an attribute-order-tolerant regex, and a labelled-anchor heuristic | — | **bad-file** | — | Zotero `Embedded Metadata.js` / `ResearchGate.js@c830037`; `roomi-fields/paper-trail@ada3cec2`; `EvenStarArwen/CiteClaw@2b448046` | 3 | VERIFIED |
| C3 | **URL rewrites on whatever C2 found** — `/epdf/`→`/pdf/`; Wiley `/pdf/`→`/pdfdirect/`; `/doi/reader/`→`/doi/pdf/`; `/doi/full/`→`/doi/pdf/`; Copernicus `.html`→`.pdf`; ScienceDirect `/pii/`→`/am/pii/` carrying landing-page cookies | PDF URL | bad-file, no-oa-copy | Medium-high and free. oadoi and Zotero converged on these rewrites independently | **rewrite only AFTER the original URL fails**, as oadoi does | `oadoi@f3f5391` `webpage.py:find_pdf_link`; Zotero Wiley translator | 4 | VERIFIED |
| C4 | **Declarative selector table** — sandcrawler's `PDF_FULLTEXT_PATTERNS`: ~60 ordered rules of `{in_doc_url, selector, attr, in_fulltext_url, technique, example_page}` | PDF URL | no-oa-copy, not-in-archive | **Very high leverage and the structure to fork**: a new publisher is a *data* change, and **every rule carries its own `example_page`, so the table is its own regression suite** | sandcrawler's `FULLTEXT_URL_PATTERNS_SKIP`, `url_fuzzy_equal` self-link hold-aside, `doi.org`/`javascript:` skip-list; the generic `url + ".pdf"` guess fires only if that exact string appears in the body | `internetarchive/sandcrawler@e23e2bd` `html_metadata.py` | 4 | VERIFIED |
| **C4-RG** | **EXTEND — three shipped schemas now exist for the same table and they agree on shape.** (i) Zotero's **custom-resolver schema**: `{name, method, url (must contain {doi}), mode html\|json, selector, attribute, index, mappings, automatic}` — validation already written. (ii) `everywall/ladder`'s **per-domain YAML ruleset** (`headers`, `urlMods`, `regexRules`, `googleCache`, `useFlareSolverr`) shipped as a community `rulesets/<cc>/<domain>.yaml` directory. (iii) instsci's **publisher access catalog** as machine-readable data (`anonymous_access`, `challenge_risk`, `link_characteristics`, `sample_doi`, `expected_pdf_markers`, `batch_policy`) — **`sample_doi` + `expected_pdf_markers` make every row its own regression test**, the property round 1 praised in sandcrawler's `example_page`. One table can serve C2–C4 and guard 7 at once | — | — | — | Zotero `attachments.js`; `everywall/ladder@76143f74`; `Rimagination/instsci@836cd6b6` | 3 | VERIFIED |
| C5 | **Generic anchor / inline-JS heuristics** — `get_useful_links` scoring after removing reference/TOC sections; `"pdfUrl":"…"`, `"exportPdfDownloadUrl":"…"` regexes on raw HTML | PDF URL | no-oa-copy, not-in-archive | Medium-high **for the grey literature specifically** — King County, Seattle, USFS, NOAA and USGS pages are plain HTML with a plain PDF link | **highest false-positive risk of the free rungs** → oadoi's `is_purchase_link`, `has_bad_href_word` (`/suppl_file/`, `/eab/`), `has_bad_anchor_word` ("Buy PDF", "Rent this article"), plus a hard cap | `oadoi@f3f5391` `webpage.py`, `util.py` | 3 | VERIFIED |
| **C5-RG** | **EXTEND — four more discovery patterns, all free on a page already fetched**: JS `window.open(…)`, `href=`, `location=`, and the `data-pdf-url` attribute; **PDF.js viewer `defaultUrl` config** (this is what Wiley `/epdf/`, T&F, SAGE and World Scientific "reader" pages actually are); **query-param unwrapping** (`file=`, `pdf=`, `src=`, `url=`); and quoted-then-unquoted `href\|content\|src="…pdf"`. Aimed squarely at agency and city pages that open a PDF from script | — | no-pdf-link | — | `pypaperretriever@04607e9`; `Rimagination/instsci@836cd6b6` | 2 | VERIFIED |
| C6 | **Classify the failure before spending anything** — terminal-URL match against a login-wall list (`?SAMLRequest=`, `/login?TARGET=`, `acw.elsevier.com/SSOCore`, `login.bepress.com`), a cookie-wall list (`/cookieAbsent`, `cookieSet=1`), a body list (`ShieldSquare Captcha`, `429 - Too many requests`) | one of four verdicts | **splits `blocked` into `blocked-wall` / `blocked-cookie` / `blocked-captcha` / `no-pdf-link`** | No direct yield; it is what makes the expensive rungs worth aiming, and it says whether a 403 is retryable | — | `sandcrawler@e23e2bd` `ingest_file.py`; `oadoi` `util.py:is_bad_landing_page` | 5 | VERIFIED |
| **C6-RG** | **EXTEND — marker-free challenge detection**, for when the vendor marker list is stale or the vendor is unknown: **200 + `text/html` + NO citation metadata at all = an interstitial**, and **that URL must not be recorded as the paper's landing page**. Plus a second independent marker table (`_fs-ch-`, `client challenge`, `recaptcha`, `just a moment`, `attention required`, first 4 KB) which adds the **reCAPTCHA-on-the-PMC-PDF-path** fact | — | blocked / bad-file | — | `cxy0714/research-news@0956cd46`; `drpwchen/paper-fetch@85ecdf81` | 5 | VERIFIED |
| C7 | **Byte-size fingerprints as a cheap BAD detector** — Akamai 399 B (MDPI), Incapsula 212 B, Cloudflare ~5.6 KB, IEEE AWS WAF 202 + ~2 KB JS, Elsevier 800 KB HTML-403 | a verdict | bad-file, blocked | free; catches a wall before you parse it | — | `finnschwall` | 2 | VERIFIED |
| **C7-RG** | **EXTEND — HEAD before GET, with a content-length ceiling, recorded in the attempt trace.** C7's fingerprints only fire *after* the bytes are spent; a HEAD catches the 800 KB Elsevier HTML-403 and oversize scans before the body moves, and yields a second signal (content-type) for zero extra cost | — | bad-file, bandwidth | — | `szaghi/mosaic@64b9919` | 1 | VERIFIED |
| **C8** | **NEW — port Zotero's `getFileResolvers` → `downloadFirstAvailableFile` engine.** The four-method resolver chain `['doi','url','oa','custom']`; for each entry try `url` directly, else load `pageURL` and **save the bytes immediately if the Content-Type is `application/pdf` or `application/epub+zip`**, else parse the HTML and run the landing-page stack | bytes | bad-file, blocked | **This is the landing-page→bytes stage round 1 inferred but never found implemented** — a production implementation of C1–C7 plus guards 1–4, already debugged against these same publishers. ~200 lines of control flow | its own guards: `maxURLs = 6` per resolver; URL de-dup **stripping every param except `download`**; a manual redirect walk (`followRedirects:false`, `redirectLimit 10`, `maxTriesPerRedirectURL 2`, **meta-refresh following** — exactly ScienceDirect's intermediate page); per-domain delay skipped only for an already-contacted domain; 3-try backoff | `zotero/zotero` `xpcom/attachments.js@main` | 1 | VERIFIED |
| **C8-RG** | **STRUCTURAL CONTRADICTION inside C8 — `getFileFromDocument` runs translator DETECTION on the landing page and then uses ONLY `translators[0]`** (`translate.setTranslator(translators[0]); // TEMP: Until there's a generic webpage translator`). So **a page carrying `citation_pdf_url` can still yield nothing**: a more specific translator wins, returns no attachment, and Embedded Metadata (priority 320, the universal fallback) is never reached. **A port should do what Zotero does not: run the specific rule, then FALL THROUGH to the generic `citation_pdf_url` rung.** That single change is probably worth more than any individual publisher rule | — | no-pdf-link | — | `zotero/zotero` `utilities_internal.js@main` | 1 | VERIFIED |
| **C9** | **NEW — `pdf_candidate_score`: rank landing-page candidates so the main-article PDF beats supplementary material.** −100 supplementary, −40 rightslink/citation/appendix, +50 belongs-to-article, +80/+120 for the exact publisher rewrite | an ordered candidate list | **prevents `bad-file` becoming wrong-file** | **High — a landing page exposes 3–10 PDF-ish links and choosing wrong is the dominant C5 failure.** This is the ordering rule round 1 had nowhere | pair with C10 | `deathcats4/instsci-workflow@3c3bb4f4`; `Panda-of-Axin/Freepaper@4e7c51b0` (scored URL shapes: 120 for `/pdfft`, 100 for `/doi/epdf/`) | 2 | VERIFIED |
| **C10** | **NEW — `belongs_to_current_article`: a per-publisher IDENTITY predicate on the candidate URL** — Elsevier PII equality, APS DOI-in-path, **Springer-vs-Nature cross-family rejection**, eLife id, MDPI landing-path equality, IEEE arnumber equality | accept / reject | bad-file, wrong-file | **The guard that makes C2/C5 safe to run at all.** Round 1 could only *name* this ("the tag can point at a different article"); this is the implementation | it is itself the guard | `Rimagination/instsci@836cd6b6`; fork `3c3bb4f4` | 1 | VERIFIED |
| **C11** | **NEW — ScienceDirect signed-asset extraction**: embedded JSON `pdfDownload.urlMetadata` → signed `pdf.sciencedirectassets.com/…/main.pdf`; plus PII from the URL (`/pii/(S\d{15,})`, `/retrieve/pii/`, `pii=`, `1-s2.0-`) → `/science/article/pii/{PII}/pdfft?isDTMRedir=true&download=true` | PDF bytes | **the measured miss** | **Aimed exactly at litkb's own bucket: all four resolvable open-access misses are Elsevier bronze with a landing-page URL. Up to 4 works, ~11% of the 35-row `no-oa-copy` bucket, from one extractor** | source PII must equal candidate PII; reject `-mmc`, `_mmc`, `/content/image/`; A10 must not strip the signature | `VisionXLab/CitationClaw@88a8d3d0`; `Rimagination/instsci@836cd6b6`; `lsempe77/mhaa_screening@72ff47df` | 3 | MIXED (code VERIFIED, access untested) |
| **C12** | **NEW — two-hop HTML→PDF→HTML re-extraction** (IEEE `stamp.jsp` is an HTML shell): arnumber → `stampPDF/getPDF.jsp` → `stamp/stamp.jsp` → **extract again from that HTML** (iframe/embed `src`, or a raw `iel[x7]…\.pdf` URL) → `"pdfUrl"`/`"stampUrl"`/`"pdfPath"` JSON → `citation_pdf_url` | PDF bytes | bad-file, blocked | **A single-hop extractor books IEEE `bad-file` every time; this is the fix.** A direct route where round-1 B10 diverts to arXiv | arnumber must match; AWS WAF fingerprint (C7) aborts the rung | `Rimagination/instsci@836cd6b6`; `CitationClaw@88a8d3d0`; `InfoLab-SKKU@ba8c08d0` | 3 | VERIFIED |
| **C13** | **NEW — Range-GET probe `bytes=0-4095` with a seven-way response classifier** | a verdict for 4 KB | splits `blocked` into `identity_required` / `challenge_or_bot_check` / `not_found` / `html_or_reader` | **Free reconnaissance**: 4 KB instead of a whole file to learn that a URL is a wall. Round-1 C6 named no implementing code; this is it | — | `WenyuChiou/research-hub@9877f929` | 1 | VERIFIED |
| **C14** | **NEW — PDF-header REPAIR**: when `%PDF-` is found at offset > 0 within the first 1,024 bytes, rewrite the file from that offset rather than discarding it | a valid PDF | bad-file | Small but free; **detect-then-repair instead of detect-then-discard**. litkb's exact `body.startswith(b'%PDF-')` rejects a PDF with a leading BOM or newline | the repaired file still faces C1-RG's other four checks | `ZimoLiao/scholaraio@c3a4b265` | 1 | VERIFIED |
| **C15** | **NEW — login/paywall detection INSIDE an otherwise-valid PDF** (Tj-string regex over the first 512 KiB) | a verdict | **types `bad-file`** | Medium. Catches publisher purchase interstitials that are **syntactically valid PDFs and pass `%PDF-` + pypdf + page-count** — exactly what round-1 C2 warns `citation_pdf_url` can point at. No parse, no full read | — | `q734738781/CatMaster` (scansci) | 1 | VERIFIED |
| **C16** | **NEW — pre-proof / cover-sheet content gate** → the bind-time state **`stub-not-article`**: markers "journal pre-proof", "article in press"; `< 3000` chars; no reference section | a verdict | ok → typed miss | Medium: Elsevier in-press DOIs and TDM first-page responses. **Free — it runs on bytes already in hand. Observed at 876 KB, so file size cannot discriminate.** Extends sandcrawler's eight states, which have no "valid PDF, wrong content" | pairs with H2-RG's `X-ELS-Status` check | `drpwchen/paper-fetch@85ecdf81` | 1 | VERIFIED |
| **C17** | **NEW — whole-volume detection (`VOLUME_PAGES = 60`) plus in-place article extraction by contiguous title match, keeping the volume as audit trail** → state **`volume-not-article`** | the article's pages | ok-on-a-400-page-proceedings | Medium-low frequency, high value per hit: **ISPRS Archives and AGU/IEEE proceedings volumes are exactly this shape**, and so is a conference abstract hung on a supplement DOI | keep the volume; never delete it | `drpwchen/paper-fetch@85ecdf81` | 1 | VERIFIED |
| **C18** | **NEW — transparent decompression BEFORE the `%PDF-` check**: libmagic sniff, gzip decompress-and-replace, PMC `.tar.gz` unpack | usable bytes | **bad-file, directly** | Medium. litkb requires `body.startswith(b'%PDF-')`; **a gzip- or tar-wrapped PDF fails that while being a good PDF**. Round-1 A7 had `bad-gzip-encoding` as a status; nobody had the fix. **The cheapest of all `bad-file` conversions: it spends no network at all** | — | `kermitt2/biblio_glutton_harvester@a011f149` | 1 | VERIFIED |
| **C19** | **NEW — reject preview endpoints by URL SHAPE before transfer**: `/previewpdf/`, `/preview-pdf/`, `previewpdf?` | a typed miss at zero bytes | ok → typed miss | Low-medium (Taylor & Francis shape); **both markers observed serving 2 pages of a 17- and a 32-page article**. The cheapest rejection is the one that never transfers a file | — | `The-Metascience-Observatory/fetchpdf@82a4c474` | 1 | VERIFIED |
| **C20** | **NEW — DSpace bitstream enumeration**: repository download endpoints carry **no `.pdf` extension**, so enumerate all `…/content` URLs and let the acceptance gate reject non-PDFs | PDF bytes | fixes a silent zero in D6/B16 | Medium for the grey tail: **NOAA IR, theses, WHO IRIS.** An extractor that only accepts `*.pdf` hrefs finds nothing on a modern DSpace page | C1-RG is what makes enumeration safe | `lsempe77/mhaa_screening@72ff47df` `step2b_no_doi.py` | 1 | VERIFIED |
| **C21** | **NEW — `libmagic` MIME check as the bind gate**: `magic.from_file(path, mime=True) != 'application/pdf'` → delete and report | a verdict | bad-file | Catches a captcha page or landing page saved under a `.pdf` name, which litkb's `%PDF-` prefix test passes. Same class as round-1's `qpdf --check` lead, one library call, no network | expected catch is the polyglot/HTML-with-PDF-header slice — **unmeasured** | `brunneis/scihub-downloader` | 1 | VERIFIED |
| **C22** | **NEW — schema.org record-class filter on the landing page** (`@type` `NewsArticle` / `Report`) | a routing decision | denominator | Low here (few magazine DOIs in a canopy corpus) but **free — it reads a page already fetched**, and it is a second signal independent of A0's Crossref `type` | flag, don't delete | `The-Metascience-Observatory/fetchpdf@82a4c474` | 1 | VERIFIED |
| **C23** | **NEW — `landing_url()`, the REVERSE PDF→landing transform** (18 host rules, with an explicit scoping rule) | a landing page to re-mine | a new path when an index gave you only a PDF URL that 403s | Covers Project Euclid (Incapsula), JMLR, PMLR, OpenReview, Project MUSE, SciPost, eLife, biorxiv/medrxiv, Springer, Wiley, Science, T&F, ACM, MDPI, PLOS | scope each rule to its host | `cxy0714/research-news@0956cd46` | 1 | VERIFIED |
| **C24** | **NEW — degrade to HTML-as-text with a distinct `cached_text` state instead of failing** | text + a typed outcome | no-oa-copy | **For agency and city HTML-only reports — the layer round-1 A7 says has no rung at all — this is often the only artefact that will ever exist.** Feeds litkb's quote layer directly | it is `kind = html-doc`, never `pdf` (r1 §3.3) | `pypaperretriever@04607e9` | 2 | VERIFIED |
| **C25** | **NEW — LLM as the LAST-RESORT link extractor on an already-fetched page** | a candidate URL | the `no_pdf_link_in_html` backlog | Unknown; costs one LLM call and **zero extra network** on a page already in memory. Bottom of Stage C | every candidate it returns still passes C9/C10/C1-RG | `VisionXLab/CitationClaw@88a8d3d0` `_llm_find_pdf_link` | 1 | ASSERTED |
| **C26** | **NEW — typed extraction-step misses**: `no_pdf_link_in_html`, `html_not_pdf`, `empty_response`, `paywall_403`, `not_found_404`, `too_large`, `not_pdf` | a typed miss | round-1 §0.3 item 8 | No direct yield; it is the **backlog generator** that makes a fixable parser failure visible. litkb's four statuses cannot express `no-pdf-link` at all | see §3 for how much of that backlog is actually fixable | `WenyuChiou/research-hub@9877f929` | 3 | VERIFIED |

### Stage D — title-keyed grey literature and agency portals (fires on a work-class hint)

| # | Rung | Returns | Converts | Expected catch | Guard | Code | Impl | Grade |
|---|---|---|---|---|---|---|---|---|
| D1 | **USFS Treesearch** | PDF | no-oa-copy, not-in-archive | **High — the corpus names USFS explicitly**, ~60,000 full-text publications. **r1 A7: this layer is the difference between ~85% and ~92%, and litkb has NO rung for it** | title identity at **0.85, never 0.6** | Zotero `Treesearch.js@c830037` | 2 | **RE-GRADED MIXED → VERIFIED by A8** |
| D2 | **USGS Publications Warehouse** `pubs.usgs.gov/pubs-services/publication?q=…` | `records[].links[]` typed **Document vs Index Page** | no-oa-copy | **r1 A1 measured 1,198 records for `q=canopy`.** No auth, public domain, exact-title searchable | title + year + report-number | `Navteca/usgs-pub-wh-mcp@c81d3af`; `elm@d227fd6` | 2 | VERIFIED |
| D3 | **DOE OSTI** `/api/v1/records` → `rel=='fulltext'` → `/servlets/purl/{id}` | PDF | no-oa-copy | Low here but free; corroborated by two independent repos | as D1 | `elm@d227fd6`; `r-three/common-pile@9457f04` | 2 | VERIFIED |
| D4 | **NASA NTRS** — `/citations/{id}` → `/api/citations/{id}` → `downloads[].links.pdf` | PDF | no-oa-copy | Medium. NASA holds historic photogrammetry and aerial-photo-interpretation literature directly relevant here | as D1 | Zotero `NASA NTRS.js`; `elm` | 2 | VERIFIED |
| D5 | **govinfo** `api.govinfo.gov/packages/{id}/summary` | PDF | no-oa-copy | Low-medium; US federal documents; free `api.data.gov` key | as D1 | `common-pile@9457f04`; Zotero `govinfo.js` | 2 | VERIFIED |
| D6 | **DSpace 5/6 and EPrints via OAI-PMH `metadataPrefix=mets`** | bitstream URL **+ MD5 + byte size**, often a pre-extracted `.txt` sibling | no-oa-copy, bad-file, **scan-needs-ocr** | High for the grey tail and theses. The METS `USE="TEXT"` group is **free OCR for scanned agency reports**; the CHECKSUM lets you verify before downloading | `dc:identifier` is usually a landing page → feed to C2 | Zotero `DSpace Intermediate Metadata.js@c830037`; `miku/metha` | 2 | VERIFIED |
| **D6-RG** | **RE-GRADE — narrow D6 to DSpace 5/6 and EPrints.** For **DSpace 7** the REST bitstream walk (B16) is a *direct file route needing no OAI-PMH*. Also: `DSpace Intermediate Metadata.js` is a **METS import translator, not a web translator** — `DSpace.js` does not exist at `c8300377`. And the 244,347-endpoint figure is **badly mis-sized for theses** (see D13-RG) | — | — | — | Zotero `FAO Knowledge Repository.js`; metha census | 2 | VERIFIED |
| D7 | **NEGATIVE — do NOT reuse the installed OAI-PMH connector.** `paper-search-mcp`'s `OAIPMHSearcher` issues `verb=ListRecords` and filters locally; `download_pdf` is search-then-guess. **It cannot answer "give me the PDF for DOI X."** | — | — | — | — | `paper-search-mcp@eabccbc` `oaipmh.py` | — | VERIFIED |
| D8 | **King County Socrata / city portal title search** | PDF | not-in-archive | Low-medium but squarely on-topic. r1 A1 confirmed King County Socrata works | returns a *dataset* page → C2 | — | 1 | MIXED |
| **D8-RG** | **CONTRADICTED — ArcGIS Hub `api/v3/datasets` holds NO documents.** MEASURED: `filter[type]=document` → **total 0**. The type aggregation over 277,240 "tree canopy" hits is entirely GIS artefacts (feature layer 121,828 / web map 45,624 / storymap 21,736 / web mapping application 13,247 / feature service 9,990 / table 8,850 / image 8,137 / raster layer 6,970 / form 4,818 / web scene 4,187 — **zero document types in the top ten**). Expected catch: **zero**. Use D12 instead | — | — | removes a round-1 lead before it is built | live probe by R2-calibration | 1 | **MEASURED NEGATIVE** |
| D9 | **OpenAlex title search** (`?search=`) | a work record + identifiers | not-in-archive, no-oa-copy | **The only free rung for works with NO DOI at all.** r1 A1 measured 5,656 hits for "Seattle tree canopy assessment" | title-similarity cut + author/year | — | 13 | VERIFIED |
| D10 | **Multi-engine web search, `"<exact title>" filetype:pdf`** on a trusted-domain allowlist | candidate URLs | no-oa-copy, not-in-archive | `elm`'s `SEARCH_ENGINE_OPTIONS` fans out over **14 backends** (DuckDuckGo / Google CSE / Serper / SerpAPI / Tavily / Bing / Yahoo + Playwright + stealth-Camoufox). **The existence of the browser backends is itself evidence that API quotas bind in production** | 8 connect timeouts per paper when an engine is blocked → circuit breaker; identity check mandatory; never accept a host outside the allowlist | `elm@d227fd6` `web/search/run.py` | 2 | VERIFIED (impl); ASSERTED (yield for papers) |
| **D10-RG** | **EXTEND — emit a reproducible query report** (query string, date, time, timezone) with every site-scoped Boolean grey-lit search. **That report string is what makes the search auditable under CLAUDE.md §3.4b**, and it is the missing half of round-1 §5.1 #5 | — | — | High for the grey layer where litkb's USFS / USGS / NOAA / King County / Seattle reports live | — | `nealhaddaway/greylitsearcher@4d35c6e8` | 1 | VERIFIED |
| D11 | **Google Scholar `eprint_url`** (`div.gs_ggs.gs_fl > a @href`) | PDF on a repository / personal page | no-oa-copy, blocked | **Would be high-yield if it worked**, and it is the best single route to 1950s–90s statistics papers and author self-archived copies. In practice Scholar captchas within tens of requests | `scholarly`'s `_CAPTCHA_IDS`/`_DOS_CLASSES`; **budget single-digit requests per hour**; Scholar's free copy may be a *different version* — record which. Round 2 adds `undetected_chromedriver` + SOCKS chaining as a fourth transport option, and notes **Scholar's own block string literally names JavaScript** | `scholarly`; `ferru97/PyPaperBot` | 2 | VERIFIED (mechanism); ASSERTED (ToS) |
| **D12** | **NEW — ArcGIS ONLINE item search**: `www.arcgis.com/sharing/rest/search?f=json&q=… AND (type:"PDF")`, bytes at `/sharing/rest/content/items/{id}/data` | PDF | **not-in-archive, for city/county canopy reports** | **MEASURED**: `q="tree canopy" AND (type:"PDF")` → **total 99**, and the first result is literally *"Tree Canopy Assessment Report for the City of Vancouver"* (owner `CityOfVancouverGISAdmin`); `(type:"PDF") AND ("urban forest" OR "canopy assessment")` → total 45. HEAD on an item's `/data` → **200 `application/pdf` 23,950,710 B** with a `Content-Disposition` filename. **This is the grey-literature layer round-1 A7 said has no rung at all** | free, keyless, paginated JSON; `licenseInfo` and `access` come back in the same row so the licence check is free; title identity still required | live probe by R2-calibration | 1 | **MEASURED** |
| **D13** | **NEW — the 45 `.gov` OAI-PMH endpoints, enumerated**: `repository.library.noaa.gov/fedora/oai`, `stacks.cdc.gov/fedora/oai`, `rosap.ntl.bts.gov/fedora/oai`, `eprints.nwisrl.ars.usda.gov/cgi/oai2` (USDA-ARS), `agspace.nal.usda.gov:8080/dspace-oai/request`, `ntrs.nasa.gov/oai`, and — regionally — **`www.sos.wa.gov/library/digcolls.aspx/oai/oai.php` (Washington State Library, NOT probed, the highest-value round-3 item)** | records → bitstreams | not-in-archive | Probed this round: `dc.statelibrary.sc.gov/oai/request` → **200 `text/xml`, a working DSpace OAI**, which establishes **state-library DSpace as a real unexploited class**. The three federal Fedora endpoints 403; USDA-ARS connection failure | see D14-RG for the host gate | metha `contrib/sites.tsv` mined by R2-calibration | 1 | MIXED |
| **D13-RG** | **RE-GRADE of round 1's metha sizing — the 244,347 endpoints are NOT 34,335 `.edu`/`.gov`.** MEASURED platform split: **OJS 184,797 (75.6%)**, DSpace `/oai/request` 3,676, Islandora 1,157, EPrints `/cgi/oai2` 959, Digital Commons `/do/oai` 832, DSpace-7 `/server/oai` 332, Janeway 48 — **repository platforms total only ~6,200**, and only **1,109** of those are `.edu`. Hosts: `.edu` 4,830, `.ac.uk` 913, **`.gov` 45**. 177,368/244,347 are https. **So it is a strong OJS-journal route and a weak thesis route; round 1 over-promised it by roughly an order of magnitude.** Also unnamed in round 1 and present in the same repo: `contrib/sites-roar.tsv` (84,610 B) and `contrib/ping-crossref-2025-12-08.ndjson.zst` — liveness data that would turn this census into a REACHABLE census | — | — | — | `miku/metha` `contrib/` | 1 | **MEASURED** |
| **D14** | **NEW — agency Zotero translators round 1 did not name**: NIST Publications (2026-05), National Transportation Library ROSA-P, NTSB Accident Reports, National Agriculture Library (pubag + naldc), EPA National Library Catalog, Data.gov, Open Knowledge Repository (World Bank), ERIC (B24). **Dead by construction: National Technical Reports Library — its PDF is POST-only** | PDF | not-in-archive | Low individually — **this is exactly the "3% rung that costs nothing" class Kam's target depends on** | each is a title-keyed rung → D1's identity guard | `zotero/translators@c830037` | 1 | VERIFIED |
| **D14-RG** | **NOAA IR is FEDORA, not DSpace — and it is behind a UA-independent Akamai host block from this egress.** NOAA's own library documents a keyless JSON API `/fedora/export/view/collection/noaa:{pid}?rows=N` (Solr shape: `response.numFound`, `response.docs[]` with `mods.sm_digital_object_identifier` = **the DOI**, so it joins straight to a DOI-keyed ledger), a whole-repo dump `/fedora/export/download`, and OAI-PMH `/fedora/oai` — *"No API key or authentication required"*. MEASURED: every one of those paths **and the bare host root** returns Akamai **403 Access Denied**, unchanged under a Chrome UA; **the same edge covers `stacks.cdc.gov` and `rosap.ntl.bts.gov`**. **Ledger this as a HOST GATE, not as per-work `no-oa-copy`** | — | — | it may simply work from another egress | live probe by R2-calibration | 1 | **MEASURED** |
| **D15** | **NEW — CORE whole-repository dump by id**: `query='repositories.id:'+repo_id, pageSize=1000` | every output of one repository | not-in-archive | **The institution→repository route OpenDOAR/Sherpa was meant to supply** (see D16-RG) | needs `CORE_API_KEY` | `oacore/pyoacore` `dumpRepositories.py` | 1 | VERIFIED |
| **D16-RG** | **CONTRADICTED — OpenDOAR / ROAR is dead for scripted access.** `GET v2.sherpa.ac.uk/cgi/retrieve?item-type=repository&format=Json` → **403 with `<title>Jisc - Error 403</title>`, a Cloudflare "Web page blocked" page** — not a 401, so the request never reaches the application and **a key would not help**. Round-1 §3.1 builds its entire thesis ladder's discovery layer on this. **Substitutes: metha `contrib/sites-roar.tsv`, or D15** | — | — | removes a round-1 lead | live probe by R2-calibration | 1 | **MEASURED NEGATIVE** |
| **D17-RG** | **CONTRADICTED — DTIC has no usable public API today.** `discover.dtic.mil/wp-json/wp/v2/` → **401** `{"code":"rest_cannot_access","message":"DRA: Only authenticated users can access the REST API."}` (a WordPress front end with REST deliberately closed); `apps.dtic.mil/dtic/api/search` → 200 but an "Under Maintenance" stub; `discover.dtic.mil/api/search?q=canopy` → **a 9 KB PNG** (a decoy); `/results/?q=canopy` → client-rendered with no extractable API hints. Confirmed from the code side too: Zotero's `Defense Technical Information Center.js` still targets the long-dead `^https?://oai\.dtic\.mil/oai/`. Expected catch: **zero** | — | — | removes a round-1 lead | live probe by R2-calibration; `zotero/translators@c830037` | 2 | **MEASURED NEGATIVE** |
| **D18** | **NEGATIVE, recorded — no Zotero translator exists for USGS Publications Warehouse, NOAA, King County / Socrata / ArcGIS, CORE or BASE**; Open Library, HathiTrust and Google Books translators carry **no PDF logic at all**; the one non-US government translator pack found (`BR_GOV_Est_*.js`, `BR_ACAD_Uni_*.js`) attaches `text/html` snapshots, not PDFs, and **no US-agency pack surfaced** | — | — | Confirms round-1 §6.6's gaps and **closes the hope that Zotero fills them** — saves a round-3 search | — | `zotero/translators@c830037` | 2 | VERIFIED |

### Stage E — archives and recovery (the only rungs that convert a DEAD link)

| # | Rung | Returns | Converts | Expected catch | Guard | Code | Impl | Grade |
|---|---|---|---|---|---|---|---|---|
| E1 | **Wayback availability API**, then **CDX** `filter=statuscode:200&filter=mimetype:application/pdf&collapse=digest` | archived PDF | **blocked, bad-file, no-oa-copy** | **High for the city/county/agency slice, and unique — no other rung recovers a 404'd report URL.** §0.2 measured **one** such copy in litkb's own bucket (a dead author copy) | **the raw-bytes modifier is MANDATORY** or you store Wayback's HTML wrapper and book another `bad-file`. Round 1 gives `id_`; **round 2 adds `if_`** — Zotero's `Fatcat.js` rewrites `/web/<ts>/` → `/web/<ts>if_/`. Carry both. Availability API answers 200; **CDX gave 503 and a 40 s timeout — back off hard** | `jsvine/waybackpack@c5507a0`; `edgi-govdata-archiving/wayback`; Zotero `Fatcat.js@c830037` | 3 | VERIFIED |
| **E1-CORRECTION (synthesizer)** | Two round-2 reports state that round-1 §1 rung E1 "is missing the `id_` modifier" / "carries neither `id_` nor `collinfo`". **Both are wrong about round 1.** The round-1 E1 row reads verbatim: *"**THE `id_` SUFFIX IS MANDATORY**: fetch `web.archive.org/web/{ts}id_/{url}`"*, and the round-1 E5 row names `collinfo.json` explicitly. **What is genuinely new is only the `if_` variant.** Recorded so round 3 does not "fix" something that was never broken | — | — | — | — | `SYNTHESIS-r1.md` §1 E1/E5 | — | VERIFIED |
| E2 | **IA Scholar / fatcat** `api.fatcat.wiki/v0/release/lookup?doi=…&expand=files` | file entities with **sha1/md5/size/mimetype** + `web.archive.org` capture URLs | blocked, no-oa-copy, not-in-archive, **and bad-file via its checksums** | r1 A2's leading hypothesis for the old-paper tail: IA crawled publisher PDFs *before* current bot defences hardened | prefer `application/pdf`; prefer the capture over the original host; **verify bytes against the catalog sha1/md5** | Zotero `Internet Archive Scholar.js` / `Fatcat.js` | 1 | see E2-RG |
| **E2-RG** | **RE-GRADE — `api.fatcat.wiki` is dead SERVER-SIDE, not blocked locally. Settled.** DoH resolves `api.fatcat.wiki` → CNAME `lb.fatcat.wiki` → A **207.241.225.9** (an Internet Archive address); `archive.org` answers 200 from 207.241.224.2 **on the same egress in the same minute**; local curl times out twice (21 s, two new DOIs) and an independent fetcher returns **ECONNREFUSED 207.241.225.9:443**. Two paths, one refusing connection → **nothing is listening**. **No client-side fix reaches it; Stage E2 cannot be specified today. Expected catch: zero.** The round-1 file-entity response shape stays ASSERTED | — | — | — | — | live probe by R2-calibration | 1 | **MEASURED NEGATIVE** |
| E3 | **Internet Archive item search + download** — `advancedsearch.php`, `/services/search/v1/scrape`, `be-api.us.archive.org/ia-pub-fts-api` (**searches INSIDE scanned books by phrase**), `archive.org/metadata/{id}` | PDF, DjVu, EPUB, **and `{identifier}_djvu.txt`** | not-in-archive, **scan-needs-ocr** | **Highest-yield single book rung** for old agency reports and pre-1990 statistics volumes, and **OCR text arrives free alongside the scan** | reject `is_dark` early; title+year from `metadata`; **treat a lending-restricted item as `blocked`, not `not-found`** | `internetarchive/internetarchive`; `sea9401/philosophy-mcp@96a3929` | 2 | VERIFIED (client); ASSERTED (`_djvu.txt`, lending) |
| E4 | **Memento aggregator (MemGator / Time Travel)** | an archived copy beyond Wayback | blocked, not-in-archive | Low-medium; a second chance on a dead agency or city URL | as E1 | **`MemGator/archives.json` 404'd — which archives it federates is still unenumerated** | 1 | ASSERTED |
| E5 | **Common Crawl index** | bytes via S3 range GET at the WARC offset | blocked | Low yield, near-zero cost | truncated WARC payload → parse-before-bind | — | 2 | VERIFIED |
| **E5-RG** | **EXTEND — the byte path, stated**: Range GET into `data.commoncrawl.org` then WARC-decode; index list from `collinfo.json` | — | — | — | — | `karust/gogetcrawl` | 1 | VERIFIED |
| **E6** | **NEW — the Wayback FALLBACK pattern: every success stores a SECOND, block-immune URL.** fatcat stores two urls per accepted ingest — the live terminal URL (`rel` `'publisher'` when `link_source=='doi'`, else `'web'`) and `https://web.archive.org/web/{terminal_dt}/{terminal_url}` with `rel` `'webarchive'` | a permanent re-fetch path | **blocked, on re-fetch** | Makes **every bound file permanently re-fetchable**, which is what a quote-verifying knowledge base actually needs. Cost: one extra column (the 14-digit capture timestamp) | `parse_terminal` normalises the timestamp from either the terminal or the older CDX shape | `internetarchive/fatcat@8f3f4c6d` `importers/ingest.py` | 1 | VERIFIED |
| **E6-RG** | **litkb stores `terminal_url`, `terminal_dt` and `terminal_status_code` NOWHERE — and those three fields are the ENTIRE input to E6, to C6's cookie-wall split, and to §3's per-host determinism.** This is the single cheapest schema change in the whole survey | — | — | — | — | — | — | VERIFIED |

### Stage F — books, chapters and ISBN

**Round 2 added NO new book rungs.** Round 1's F1–F11 stand unchanged; what round 2 contributes here is
four negatives and one correction, all of which *narrow* the book path rather than widen it. See §4.

| # | Rung | Grade after round 2 |
|---|---|---|
| F1 | `isbnlib.editions(isbn, service='merge')` — unions Open Library + LibraryThing + Wikipedia; **one call multiplies every downstream book rung by 4–6** | VERIFIED |
| F2 | Open Library `/api/books?bibkeys=ISBN:X&jscmd=details` → `details.ocaid` → an Internet Archive item id — **the cheapest ISBN→file bridge that exists** | VERIFIED |
| F3 | Crossref chapter-DOI routing → ISBN + `container-title` (the enabling rung for F1/F2/F4/F5) | VERIFIED |
| F4 | DOAB / OAPEN via OAI-PMH `metadataPrefix=xoai` (**prefer OAI-PMH**; the DSpace-7 REST path returned Cloudflare 403 in 2026-08) | MIXED |
| F5 | Google Books v1 `accessInfo.pdf.downloadLink` — **and round 2 confirms Zotero's `Google Books.js` has no PDF logic at all**, so there is no translator to crib | MIXED |
| F6 | HathiTrust Bib API as a *locator* (a); hathifiles bulk dump (b); OAuth1 `getdocumentocr` (c, **needs partner access we do not have**). **Round 2 independently re-confirms `HathiTrust.js` attaches no PDF** | VERIFIED |
| F7 | Publisher book URL rewriters (MDPI `pdfview`→`pdfdownload`; Springer `/content/pdf/{doi}.pdf` + `/download/epub/{doi}.epub`; OpenEdition) | VERIFIED (these three) |
| F8 | T&F / CRC `api.taylorfrancis.com/v4/content/{productId}` — **ZERO without an entitlement.** The corpus's one CRC book (ISBN 9781466568419) is a purchase / ILL / manual decision for Kam | VERIFIED |
| F9 | LibGen book index `search.php?column=identifier` (ISBN) / `column=title` / topics `articles`, `standards`, `libgen` | VERIFIED |
| F10 | Z-Library eAPI — **RE-GRADE: there is nothing to read.** `baroxyton/zlibrary-eapi-documentation` at `e2184c46` is **one file, `README.md`, 2,892 bytes** — no code, no schema, no client — and round 1 already fetched that README (blacklist line 502) | ASSERTED, unimprovable from this source |
| F11 | Project Gutenberg / Standard Ebooks / Gallica OPDS / Wikisource — **approximately zero for this corpus** | MIXED |

### Stage G — shadow libraries (Kam-authorised; runs only after every legitimate rung has missed)

**A5's structural rule stands: separate address resolution (Tier 0, no bytes) from delivery (Tier 1+),
and keep a `doi → {md5, cid, storage_path}` cache — it is the ladder's real state.**

| # | Rung | Converts | Key fact | Grade |
|---|---|---|---|---|
| G0a | **LibGen `json.php?object=e&doi=<doi>` → the md5** | address only | **The highest-value new rung of round 1 in this class.** UA TRAP: every mirror answers a UA-less request with nginx's default page **under HTTP 200**, and a bare `Mozilla/5.0` earns a 500 — only a full Chrome UA works. **Assert the marker `Welcome to nginx` is ABSENT; mirror health cannot be decided on status code.** Mirrors: `libgen.li/.la/.bz/.gl/.vg`, **not** the `.rs/.is/.st` generation | VERIFIED |
| G0b | **Nexus / STC** `stc-geck` over the Summa index at `/ipns/libstc.cc/data` → an IPFS CID | not-in-archive, no-oa-copy | Account-free, challenge-free transport litkb has never tried. **C1 counterpoint: 2026 threads report `libstc.cc` down and the "95%" coverage is one guide author's unsupported claim** | VERIFIED / disputed |
| G0c ★ | **Sci-Hub article page on the first non-challenging mirror, to harvest the portable `/storage/…pdf` path** | blocked | `is_scihub_robot_check` BEFORE concluding a miss. **The Altcha challenge fires INTERMITTENTLY rather than by request rate**, so `SCI_HUB_GATE_RETRIES = 5` **immediate** re-asks ("spacing the retries does not help and immediate ones are cheap") | VERIFIED |
| G0d ★ | **Anna's `/search?content=journal`**, `content=book_any` + ISBN for books | not-in-archive | **Check `<title> == "DDoS-Guard"` FIRST. Never detect the challenge by searching the body for "ddos-guard" — a solved record page mentions it in its own scripts.** Without this check the rung *manufactures* `not-in-archive` | VERIFIED |
| G1a | **`sci.bban.top/pdf/<LOWERCASED-doi>.pdf`** | no-oa-copy, blocked | **A DOI-addressed Sci-Hub PDF host with NO bot check.** `getscipapers` tries it before any mirror; litkb does not have it and it is the cheapest rung in the class. Uppercase DOI 404s spuriously | VERIFIED |
| G1b ★ | **The `/storage/…pdf` path re-pointed at `sci-hub.vn`, `.su`, `.box`, `.ru` in turn** | blocked, bad-file | This is the change that converts the 25 blocked rows, because it stops discarding resolutions produced by mirrors that cannot serve | VERIFIED |
| G1c | **Nexus/STC HTTP gateway** `libstc-cc.ipns.dweb.link/dois/<double-urlencoded lowercased DOI>.pdf` | no-oa-copy, blocked, not-in-archive | Exactly Kam's "3-percent rung that costs nothing" | VERIFIED |
| G1d | **LibGen delivery** `/ads.php?md5=` → `get.php?md5=`, `/file.php?md5=`, across all four labelled mirrors | blocked, bad-file, not-in-archive | **Expired links answer 200 with a page** → `discard_invalid_download` before the mirror counts as a success | VERIFIED |
| G2a | **Anna's `/db/aarecord_elasticsearch/md5:<md5>.json`** + member cookie → the `ipfs_urls` | not-in-archive, blocked | **QUOTA-FREE — this is why it precedes G2b.** Not challenge-gated; guarded only by a membership check. **Paired with G0a this is the strongest single addition to litkb's ladder in this class** | VERIFIED |
| G2b ★ | **Anna's `/dyn/api/fast_download.json?md5=&key=`** | blocked | Reliable but **metered**. Two independent sources confirm it is not behind DDoS-Guard | MIXED |
| G3a | **Real browser for Anna's** — Chromium with `--use-angle=swiftshader`, `MAX_BROWSER_ATTEMPTS = 3` | blocked, not-in-archive | **cloudscraper and FlareSolverr are the WRONG tools here — Anna's uses DDoS-Guard and Sci-Hub uses Altcha; neither is Cloudflare IUAM.** The swiftshader flags are load-bearing: a GPU-less host blocklists WebGL and the check degrades to hCaptcha, which never solves | VERIFIED |
| G4 | **Deferred human fulfilment** — sci-net.xyz, AbleSci, WoSonHJ, the Nexus Telegram bot | no-oa-copy | **The only route in the class that reaches POST-2021 paywalled articles**, since the Sci-Hub corpus froze around 2021 — i.e. recent IEEE TGRS and Elsevier remote-sensing work. **A pending drop-off with a due date, not a rung.** Account risk; **Kam's ruling** | MIXED |
| **G5** | **NEW — Tor as a transport is TWO CONFIG LINES, not a library.** A Dockerfile installs tor + privoxy and appends `forward-socks5 / localhost:9050 .` to `/etc/privoxy/config`; the fetcher then only sets `ProxyHandler({'http':'127.0.0.1:8118'})`. **Any existing litkb fetcher gets Tor from an `HTTP_PROXY` env var with no code change.** The repo itself is Python 2, last touched 2021, targets the long-dead `sci-hub.tw` — **read as source only; nothing in it runs**, and no request was sent to any shadow host in either round | blocked | removes a round-3 slot | **RE-GRADE: VERIFIED as a two-line mechanism, DEAD as an implementation** |

### Stage H — credentialed, anti-block and terminal

| # | Rung | Converts | Key fact | Grade |
|---|---|---|---|---|
| H1 | **Springer Nature API** — `openaccess/json` and **`xmldata/jats`** | no-oa-copy, **scan-needs-ocr** | The JATS route is born-digital full text and bypasses OCR entirely. **RE-GRADE (T26): the API resolves but hands you URLs on the walled host** | VERIFIED, re-graded |
| H2 | **Elsevier full-text API** `api.elsevier.com/content/article/doi:{doi}` + `X-ELS-APIKey` | no-oa-copy (OA content only without an institutional token) | **The main publisher gap for this corpus** — ISPRS J. P&RS and Remote Sensing of Environment are Elsevier | VERIFIED |
| **H2-RG** | **RE-GRADE — round 1's H2 is wrong in BOTH halves.** (a) **`?view=FULL` returns HTTP 400 `INVALID_INPUT` for a subset**, while the bare request with `Accept: application/pdf` succeeds — drop `view=FULL`. (b) **An unentitled key gets HTTP 200 + a real `%PDF` that is the FIRST PAGE ONLY, announced only in the `X-ELS-Status` RESPONSE HEADER.** Round 1 has no header check, so a litkb built from §1 as written would **silently bind first-page stubs that pass a title match** — the first page carries title, authors and abstract. **Read `X-ELS-Status`; pair with C16 and with round-1 guard 4's truncation rule** | — | Decisive wherever H2 is used | **VERIFIED** |
| H3 | **Wiley TDM** `api.wiley.com/onlinelibrary/tdm/v1/articles/{doi}` + `Wiley-TDM-Client-Token` | no-oa-copy, blocked | Moderate-high for the Wiley slice (Ecol. Appl., MEE, Ecology, GCB). **Wiley's TDM URL is also handed to you free by Crossref `link[]` (B4).** 60 req / 10 min | MIXED |
| H4 | **IEEE `stamp.jsp`** no-credential route | no-oa-copy | Low. **sandcrawler's domain blocklist contains `'://ieeexplore.ieee.org/'` under `# robot blocking / rate-limited`** | VERIFIED (route) |
| **H4-RG** | **RE-GRADE — round 1 names only `stamp/stamp.jsp`.** Freepaper handles **`stampPDF/getPDF.jsp`** as a separate path (and it is IEEE's actual first hop, see C12), and **doiget implements the SANCTIONED route** `ieeexploreapi.ieee.org/api/v1/search/articles` (prefixes 10.1109, 10.23919) with a test literally named `an_empty_articles_array_is_a_miss_not_a_hit`. **Ceiling, from Aut_Sci_Download's own docstring: "The IEEE API provides `pdf_url` but actual download requires institutional access (via IP or proxy)" — so a key buys metadata and a URL, not bytes** | blocked on IEEE TGRS/JSTARS | Potentially high **only with entitlement**; r1 A7 measured 4/12 IEEE TGRS works absent from OA indexes and 5 of the remaining 8 present only as arXiv | **VERIFIED, with a zero-without-entitlement ceiling** |
| H5 | **`curl_cffi` with `impersonate=…`** — TLS/JA3 + HTTP/2 fingerprint, one dependency, no browser | blocked | **DISPUTED — see §7 #2** | MEASURED both ways |
| **H5-RG** | **RE-GRADE from "the answer" to "the answer for SOME walls", with three named counter-examples and one correction.** (i) **MDPI**: `lsempe77/mhaa_screening@72ff477f` ran round-1's own recommended experiment in production and lost — `step2d_browser.py` exists *because* TLS impersonation failed, its docstring naming bot challenges "that defeat plain HTTP (cloudscraper, curl_cffi)" with "**Primary target: MDPI (10.3390), which is fully OA but serves an Akamai interstitial**". Two different evasions, same host, both failed; a real browser was required. (ii) **Springer, dated 2026-09-05**: `link.springer.com/content/pdf/{doi}.pdf` returns HTTP 200 + a ~3 KB "Client Challenge" JS page **to any UA, with landing-page cookies, and with a curl_cffi Chrome TLS fingerprint**. (iii) **The zotero/translators maintainers' own skill doc**: faking the browser with `--user-agent` "makes Chrome drop its `Sec-CH-UA` client hints, which is a **worse signal than the one it hides**", headless Chrome "is refused outright", and a solved challenge should be cached in a **reused browser profile**. **Correction to round 1's characterisation of the disputed rung**: findpapers' impersonation is `impersonate="chrome"` (an **unpinned alias**, asserted by its own test at `3b42b66`), not `chrome131`, and `curl_cffi` appears **only** in `runners/download_runner.py`, `connectors/web_scraping.py` and `utils/logging_config.py` — `connector_base.py` uses a plain `requests.Session`. **It is a scraping/PDF-fetch transport, not a general one, and the `Referer: google.com` detail belongs to pypaperretriever, not necessarily findpapers.** None of this kills H5 (curl_cffi impersonates TLS/JA3 and HTTP/2, not just the UA) but it **forbids a bare UA override** and favours a persisted real-Chrome profile | — | **For MDPI specifically the dispute is now largely moot: A6's CDN route is measured and sidesteps the wall entirely** | **MEASURED against, twice** |
| H6 | **FlareSolverr on the landing page**, then `solution.cookies` + `solution.userAgent` into your own fetch | blocked | **FlareSolverr CANNOT return a PDF — `solution.response` is HTML text.** The clearance cookie only works if you also send FlareSolverr's own UA. Re-run C6 on `solution.response` | VERIFIED |
| **H6-RG** | **RE-GRADE — prefer a PERSISTED profile over a stateless solve, and cache the solve when you do one.** Zotero's maintainers cache a solved challenge in a reused browser profile; `sarperavci/CloudflareBypassForScraping@0f628b9c` caches a TTL'd `{cookies, user_agent, expires_at, exit_ip}` **bound to the exit IP** and replays it through an **LRU of curl_cffi sessions keyed `host:proxy`**. **That cache is what makes a browser rung affordable across a batch** — round-1 H6 treats each solve as per-request | — | Medium where Cloudflare is the wall | VERIFIED |
| H7 | **Commercial anti-bot proxy (Zyte / Crawlera)** with a per-domain policy table | blocked | **Recorded because it is the measured answer of Unpaywall itself** (`oadoi` ships `zyte_session.py`: `ZytePolicy(type, regex, profile ∈ {proxy, api, bypass}, priority)`, `X-Crawlera-Profile: desktop`, `requestHeaders.referer = 'https://www.google.com/'`). **Kam's call** | VERIFIED |
| H8 ★ | **Human-in-the-loop browser** (litkb's existing `browser` route) | — | Where `blocked-wall` / `blocked-captcha` items go to **die honestly**. **45 rows live here today** | VERIFIED |
| **H9** | **NEW — institutional-proxy transports as CONFIG**: `ezproxy_enabled`, `carsi_enabled`, `vpnsci_enabled`, `tor_proxy`, `network_proxy`, all under a `download_strategy='legal_only'` master flag | blocked (39 rows) and the ~26 paywalled works | **The only automated rung that can reach the paywalled residue legitimately.** Fires only if Kam has an institutional login — **an input the survey has never established (§7 #9)**. Config surface VERIFIED in `CatMaster` `acquisition.py:_scansci_config@5246749`; the transports themselves live in the PyPI package `scansci-pdf` and **were not read** | MIXED |
| **H10** | **NEW — drive the user's OWN already-logged-in browser profile**: `launch_persistent_context` on `%LOCALAPPDATA%\Microsoft\Edge\User Data`, `channel=msedge`, with a 7-state outcome vocabulary | blocked, manual-step | **Conditional and binary. If Kam has institutional access this is the single largest converter of the ~26 genuinely paywalled works; if not, the catch is 0.** No credentials are handled, scripted or stored. Round 1 states flatly "There is no institutional proxy" and its whole H stage is API-token routes | VERIFIED (mechanism) |
| **H11** | **NEW — persisted per-domain browser sessions**: log in once headed, reuse headless via `storage_state` | blocked, and the 45 `manual-step` rows | **Pays the human cost once per publisher instead of once per paper** — and it is the only rung that survives `doi.org → linkinghub → sciencedirect`, whose last hop is a JS redirect. Yield ASSERTED | VERIFIED (mechanism) |
| **H12** | **NEW — which real browser matters**: `szaghi/mosaic` `auth.py@64b9919` states **headless Playwright Firefox passes Cloudflare Bot Management where headless Chromium is blocked**, and that `cf_clearance` is **fingerprint-bound**, so login and headless reuse must use the same engine. PyPaperBot uses `undetected_chromedriver` instead; Zotero's maintainers drive **real** Chrome | blocked | Adds a third and fourth position to §7 #2. **Neither is measured — this is the cheapest open question in the entire survey** | ASSERTED |
| **H13** | **NEW — API-key-else-browser factory per publisher, gated on `available()`** | blocked | No new yield, but **it removes a class of dead rungs**: a keyless Springer/Elsevier/Wiley API rung currently occupies a ladder slot and always misses. Collapses H1–H3 and H6–H8 into one rung with two implementations | VERIFIED |
| **H14** | **NEW — crawler-identity request shaping**: default UA `Googlebot/2.1`, per-rule `Referer` defaulting to the target's own URL, per-rule `X-Forwarded-For` | blocked, on publishers that serve indexers the full text | Unknown for scholarly publishers — ladder's rulesets are news sites and nothing was run. **It is deliberate misrepresentation of the client, so it belongs in the same POLICY bucket as the shadow rungs, not the free-and-harmless tier** | MIXED |
| **H15** | **NEW — browser rungs that are NOT shadow**: `publisher_headful` and a ResearchGate rung gated on **the user's own exported session cookies**, auto-disabled with a printed reason when absent | blocked, no-oa-copy | Medium for a forestry / remote-sensing corpus where **author self-archiving is common** — author-uploaded copies are a different population from the OA indexes. ResearchGate appears in five round-1 reports but in **no round-1 ladder row** | VERIFIED |
| **H16** | **NEW — declarative per-domain ruleset as a shipped data directory** (`headers`, `urlMods`, `regexRules`, `googleCache`, `useFlareSolverr`, one YAML per domain) | blocked, no-pdf-link | Structural — **the right shape for litkb's per-publisher knowledge, which currently has nowhere to live**. Extends C4 (sandcrawler's table is selectors only) and confirms guard 7 | VERIFIED |
| **H17** | **NEW — capability tiers as a COMPILE-TIME and runtime gate**: Tier 1 always on; Tier 2 behind a Cargo feature **and** an env var; the shipped binary built `--features oa-only` | governance | **Makes "Kam-authorised shadow rung" a build-and-policy fact rather than a code comment**, and directly serves CLAUDE.md §3.4c's "a gate that has never fired is not known to work" | MIXED |

### Guards that sit BETWEEN rungs (29 — round 1's ten, plus nineteen from round 2)

**Round 1's ten, kept, with round-2 corrections inline:**

1. **Host gate before every request** — per-host concurrency + `min_interval` with ≤30% jitter; default
   `(1, 1.0 s)`; 3.0 s for known-banning publishers; API hosts fast. *(finnschwall `host_gate.py`;
   four independent implementations now.)*
2. **Refusal ladder, PERSISTED atomically**: 15 min → 6 h → 48 h over a 7-day window, triggered on
   `{202, 403, 429, 503}` **with** a small/empty body or a refusal marker. **401 deliberately
   EXCLUDED** — "a subscription answer about one article, not an edge denial of the whole site".
   **401/403/404 NEVER retried.**
   **RE-GRADE (W25): the fixed ladder is missing its complement — decay LINEARLY on every 2xx.**
   `pypaperretriever` `http_client.py@04607e9` runs AIMD: `backoff_decay_s=1.0` against
   `backoff_multiplier=2.0`, `backoff_max_s=300`, so a recovered host is forgiven in seconds instead
   of 15 minutes. Honour `Retry-After` / `RateLimit-Reset`. **Adopt the decay.**
   **REJECT its `suppress_on_403=True` default (W26)**: one 403 short-circuits every later request to
   that host, which would retire `www.mdpi.com` — the corpus's largest slice — after the first article.
   A 403 from MDPI is a *per-article* answer, not an edge denial. *(Default verified in the signature;
   the harm is reasoned, not measured.)*
3. **Challenge state, flat 1 h, NOT persisted** — "waiting longer cannot turn this client into a
   browser". Detected by header (`cf-mitigated: challenge`, `x-datadome: protected`) or first-64 KB
   markers (`validate.perfdrive.com`, `_incapsula_resource`, `px-captcha`). Non-retryable.
   **EXTEND (C6-RG)**: add the **marker-free** rule — 200 + `text/html` + *no citation metadata at
   all* = an interstitial — and a second independent marker table (`_fs-ch-`, `client challenge`,
   `recaptcha`, `just a moment`, `attention required`, first 4 KB). **And never store an interstitial
   URL as the paper's landing page.**
4. **Leaf identity verification, MUTATION-TESTED**: `DOI_PAGES=3`, `TITLE_PAGES=2` (so a bibliography
   cannot fake a DOI match), `TITLE_BLOCK_MIN=0.85`, `TRUNCATION_RATIO=0.5`; ten ordered checks; **six
   verdicts, and only `WRONG`/`TRUNCATED` reject** — "a wrong file that is kept can be found again by
   re-running the audit and a right file deleted cannot". Validated on 500 real PDFs (499 verified,
   1 genuine `wrong_article`).
   **RE-GRADE (C1 of R2-topics): this is ONE implementation, not several.** `fetchpdf`
   `retrieval/pdf_identity.py@82a4c474` declares the **same** constants, the **same** six verdicts and
   a **near-verbatim** rationale sentence with no credit either way — textual identity VERIFIED, shared
   lineage ASSERTED. The genuine second implementation is `drpwchen/paper-fetch` `pdf_verify.py`
   (`PAGES_TO_READ=4`, `VOLUME_PAGES=60`, `ACCEPT=0.60`), and a third is paper-trail's
   `_validate_page1`. **And the 0.6 threshold round 1 warns against now has a name attached**:
   `VisionXLab/CitationClaw@88a8d3d0` sets `TITLE_MATCH_THRESHOLD = 0.6`; `mhaa_screening` uses 0.82.
   **EXTEND (T13): never delete on a verdict resting on metadata you could not fetch.** Measured
   regression by fetchpdf's author: re-judging **706 known-good PDFs** with metadata unavailable
   **deleted 8**, and **every DataCite-only DOI (Zenodo / OSF / figshare) was destroyed on sight**
   because "no Crossref record" read as "no title".
   **EXTEND (T15): Crossref page-range as an identity signal** — `expected_page_count`,
   `PAGE_COUNT_SLACK=2`, `PAGE_COUNT_MIN_SPAN=2`. Separates TRUNCATED from WRONG with no second fetch,
   from metadata already held.
   **EXTEND (T14): "the PDF you fetched is one the paper CITES" is a named false-positive class.**
   Observed: `10.1111/all.14949` bound the USDA's 164-page *Dietary Guidelines* as an 11-page Wiley
   allergy paper. **`DOI_PAGES=3` exists precisely so a long report's own bibliography cannot supply
   the requested DOI and fake a match.** litkb's hunt ends on the first `%PDF`, and a bibliography is
   a list of other people's files.
   **EXTEND (W30): a publisher-PREVIEW detector** (`is_suspicious_pdf`) with `page_count>=2` and 0.80
   token coverage over the first four pages — a second team converging on the same design with
   different constants. *(The predicate itself lives in `scansci-pdf` and was not read.)*
5. **The OCR hand-off**: a file that parses, has ≥3 pages and **no text layer** is not a failure — it
   is `scan-needs-ocr`. That is precisely the 1950s–90s statistics papers.
6. **Per-source EMA scoring** (`scansci-pdf` `sources/scoring.py`): `success_ema` + latency tiebreak,
   `sort_sources` by `(-score, latency)`, `classify_error()` per miss, persisted to
   `source_scores.json`. **This is the mechanism that makes a 3%-rung genuinely free.**
   **EXTEND (Z): `lastUpdated` in every Zotero translator header is a free per-rule freshness prior**,
   so a ported rule starts warm instead of cold — ScienceDirect 2026-06-05, Silverchair 2026-08-10,
   SAGE 2026-07-21, Annual Reviews 2026-08-05, Cambridge 2026-08-06, ACM 2026-03-09 **vs** IOP
   2016-11-01, PLoS 2017-01-22, Open Library 2017-05-25, ResearchGate 2020-10-18. **And a nightly diff
   of the ~25 files you ported is a change-detection loop for free.**
   **EXTEND (C5/C6 of §3): the empirical case for learned order over a fixed one** — sandcrawler's
   `release_stage` yield **flips direction between batches** (2020-10 cumulative: accepted 95.0%
   success vs published 75.7%; 2021-07 fresh batch: accepted 61.0% vs published 83.9%).
7. **Circuit breaker + externally-hosted source registry**: 3 failures disables a source, 300 s before
   re-enable, 5 s between items; the registry fetched at startup from a companion repo and cached on
   disk **so mirrors rotate without a code change**.
   **CONFIRMED twice more**: `obsfx/libgen-downloader` probes a remote mirror list at startup; a
   versioned 2,271-byte `sources.json` (`"version": 1`, per-source objects, some with a `mirrors[]`
   array of five) is fetched and cached by its consumer. **litkb's Sci-Hub / Anna's mirror lists are
   compiled into `run.py` today.**
8. **Identity costs nothing**: Unpaywall sends
   `User-Agent: Unpaywall (http://unpaywall.org/; mailto:team@impactstory.org)` plus a `From:` header.
   Adopt the shape `litkb/<version> (+<contact url>; mailto:<address>)` and honour `Retry-After`.
   **EXTEND (W18): Crossref's polite pool wants the same string sent TWICE — as `User-Agent` and as
   `X-USER-AGENT`.**
9. **Refuse private / loopback / link-local addresses on EVERY redirect hop** — candidate URLs come
   from external indexes.
10. **Atomic writes**, so a partial download can never be bound.

**Nineteen new guards from round 2:**

11. **AIMD host back-off** — see guard 2. *(W25)*
12. **A declarative BUDGET object over the whole ladder** — total timeout / attempts / concurrency,
    checked between every tier and every source. Round 1's guards are per-host and per-source; **none
    bounds the work**. *(W22, DocsToKG)*
13. **Retryable `{429,502,503,504}` vs terminal `{400,401,403,404,405,410}` declared as DATA**, not
    code. Free, and an independent confirmation of guard 2's 401/403/404 rule. *(W23)*
14. **A skip is an Attempt with a reason, never silence** — `breaker_open` as an `AttemptResult`, plus
    a `retrieval_trace[]`. **This is what stops litkb's census being a measurement of a broken
    instrument a second time.** *(W24; two more implementations beyond DOI2PDF's `query_failed`)*
15. **A typed, resumable failure ledger with a per-attempt `retriable` flag** — per work:
    `failure_reason`, `failure_message`, the **full `attempted_urls` list including which variant was
    tried**, source, timestamp, `retriable: true|false`. The variant ladder is **eight tries on one
    URL** — bare, mirror host, two browser UAs, minimal headers, `head_ok`, referer,
    `academic_referer(scholar.google.com)` — the cheapest possible answer to a 403.
    **`retriable` as a per-attempt fact is exactly what litkb hard-codes per status in
    `run.py:43 DEAD_STATUSES`.** *(C14; the shipped ledger has only 2 entries, so this is a SHAPE, not
    a calibration set — no yield claimed.)*
16. **No email → SKIP that source and still run the rest.** *(W28; the exact one-line difference
    between §0.2's census and a true census.)*
17. **Unverified-keep accounting** — a PDF kept because its metadata could not be fetched is a **third
    outcome**, reported at end of run. litkb has no equivalent: a bound file is a bound file.
    **This is the ledger column that makes a 95% claim auditable at all.** *(T12)*
18. **Never delete on a metadata-less verdict** — see guard 4. *(T13)*
19. **Crossref page-range identity** — see guard 4. *(T15)*
20. **Per-source robots policy** — `true` for landing pages and DOI redirects, `false` for API
    sources. Round 1 has no robots rung; this is the difference between polite and unable to scrape a
    landing page at all. *(W21)*
21. **A pre-fetch source POLICY object** (allowlist + host denylist → `PolicyDecision`). **It makes
    "shadow tier authorised" a one-line auditable switch rather than a code path.** Four independent
    codebases implement the same shape. *(W27)*
22. **Capability tiers as a compile-time AND runtime gate** — see H17. *(T20)*
23. **`articleVersion` carried on EVERY candidate** — `submittedVersion` / `acceptedVersion` /
    `publishedVersion`, straight out of Zotero's OA resolver. **An accepted manuscript has different
    pagination from the version of record; litkb records no version, so a quoted page number can
    silently come from the wrong artefact.** This is a quote-grade citation guard, not a fetch guard.
    *(Z)*
24. **Referer policy: the LANDING PAGE if same-origin, else its ORIGIN — never Google.** Two
    independent Zotero production paths agree: `attachments.js` sets
    `{ referrer: responseURL }` → `headers.Referer`, and the connector's
    `itemSaver.js:_setAttachmentReferer` sets `attachment.referrer = sameOrigin ? url.href : url.origin`.
    **RE-GRADE of round-1 rung 18 / A3 §2.2, which recommend `Referer: https://www.google.com/`.**
    They fix different failures — Google is a *spoof* aimed at paywall softening, Zotero's is the
    *honest* referer that hotlink protection expects. **Carry both; default to Zotero's.** *(Z)*
25. **Per-rule freshness from `lastUpdated`** — see guard 6. *(Z)*
26. **Collect-then-try candidate pooling, with grey-source candidates in a SEPARATE, cleared pool** —
    a hard tier boundary so a grey URL can never be silently preferred. *(W36)*
27. **Per-provider capability grading** — `FULL / OA_ONLY / INFO_ONLY / BEST_EFFORT / FALLBACK_ONLY /
    UNSUPPORTED / SKELETON`. **This is the vocabulary in which "this rung catches 3% and costs
    nothing" gets written down.** *(W38; the enum is verified, the per-provider values live in a
    blacklisted file.)*
28. **fatcat's admission gate — nine NAMED refusal counters where litkb has one `bad-file`**:
    `want_file` refuses on `skip-file-meta`, `skip-grobid` (**GROBID `status_code` must be 200 for
    PDFs**), `skip-mimetype` (exactly `application/pdf`), `skip-ingest-type`; `want_ingest` on
    `skip-hit`, `skip-ingest_request_source`, `skip-link-source`, `skip-savepapernow`; `parse_urls` on
    `skip-url`. Every refusal increments a named counter. **`want()`'s own docstring flags the same gap
    round 1 found: "We should filter/block things like single-page PDFs here"** — the stub heuristic
    that needs `page_count` and `word_count`. *(C8–C9)*
29. **Reject `suppress_on_403=True`** — see guard 2. Recorded as a guard because it is a
    plausible-looking default that would silently retire the corpus's largest publisher. *(W26)*

---

## 2. The landing-page → PDF rule table, per publisher of THIS corpus

Merged from `R2-landing-extractors` §5 (eleven implementations) and `R2-zotero-translators` §2.3
(748 translators, read whole). **This table is the concrete content of rungs C2, C3, C4, C9, C10 and
A9.** Every row is adaptable as a fixture: instsci's `data/publisher_access_catalog.json@836cd6b6`
carries `sample_doi` + `expected_pdf_markers` per publisher, so each row is its own regression test.

### 2.0 Shared preconditions and the shared validity check

**Headers for every row**: `User-Agent` a real Chrome string (CiteClaw: an academic-crawler UA gets
403 from bioRxiv and Wiley); `Accept: application/pdf,text/html;q=0.8,*/*;q=0.5`; **`Referer` = the
landing page whenever the candidate came from that page** (guard 24); follow redirects; **accept only
by body magic, never by content-type.**

**Validity check V** (C1-RG + C14 + C10 + C9, in order):
`body[:32].lstrip().startswith(b"%PDF")` **after** normalising a `%PDF-` found at offset > 0 within
the first 1,024 bytes → `len >= 5000` → no `\xef\xbf\xbd` in the first 64 bytes → `%%EOF` within the
last 8 KiB → `belongs_to_current_article` → `pdf_candidate_score > 0`.

**The ordering all eleven implementations agree on** (they disagree only about what comes after step
③): ① a pasted or index-supplied URL that already looks like a PDF; ② `citation_pdf_url` from the
landing page; ③ the publisher's deterministic rule; ④ page-discovered candidates, **scored**;
⑤ index-supplied alternates (OpenAlex `locations[].pdf_url`); ⑥ transport escalation
(cloudscraper → render proxy → real browser); ⑦ credentialed route (API key, EZproxy).
**Round-1's Stage-C order is compatible; the additions are ④'s scoring and ⑥ as an explicit,
separate axis.**

### 2.1 The table

| Publisher | Detection | PDF-URL rule, in order | Identity / validity | Challenge signature | Zotero rule (+`lastUpdated`) |
|---|---|---|---|---|---|
| **MDPI** | DOI `10.3390`; `www.mdpi.com`, `mdpi-res.com` | **(0) A6: `mdpi-res.com/d_attachment/{journal}/{journal}-{vol}-{art}/article_deploy/{journal}-{vol}-{art}.pdf` — MEASURED 200/PDF/2,366,188 B**; 1) DOI → `{issn}/{vol}/{issue}/{art}` via an ISSN table (`rs`=2072-4292) then `+"/pdf"`; 2) landing numeric path `+"/pdf"`; 3) `citation_pdf_url`; 4) real browser, download event | V + landing-path equality | **Akamai interstitial**, 399-byte body; **defeats cloudscraper AND curl_cffi** (measured in production); the catalog's `challenge_risk: low` is wrong for anonymous clients | `MDPI Journals.js` has **no PDF code at all** — pure Embedded Metadata delegation (2022-01-24) |
| **Copernicus / ISPRS** | DOI `10.5194`; `*.copernicus.org` | DOI regex `{journal}-{vol}-{page}-{year}` → `https://{journal}.copernicus.org/articles/{vol}/{page}/{year}/{suffix}.pdf` | V | none observed; `usually_open_access` | `Copernicus.js` — EM, plus `.pdf` ↔ `.html` are the same string with the extension swapped (2023-01-25) |
| **Elsevier / ScienceDirect** | DOI `10.1016`; `sciencedirect.com`, `linkinghub.elsevier.com` | 1) **keyed API** `api.elsevier.com/content/article/doi/{doi}` + `X-ELS-APIKey` (+`X-ELS-Insttoken`), `Accept: application/pdf`, **no `view=FULL`**; 2) PII from the URL (`/pii/(S\d{15,})`, `/retrieve/pii/`, `pii=`, `1-s2.0-`) → `/science/article/pii/{PII}/pdfft?isDTMRedir=true&download=true`; 3) embedded JSON `pdfDownload.urlMetadata` → signed `pdf.sciencedirectassets.com/…/main.pdf`; 4) `"pdfLink"`/`"linkToPdf"`/`"pdfUrl"`; 5) `citation_pdf_url` | V + **source PII must equal candidate PII**; reject `-mmc`, `_mmc`, `/content/image/`; **read `X-ELS-Status` or bind a first-page stub** | Cloudflare "Are you a robot?" on `/pdfft` (2026-06-07); `CPE00001 / There was a problem providing the content you requested`; `auth.elsevier.com/ShibAuth/`, `id.elsevier.com`; in `BROWSER_ONLY_PREFIXES` | `ScienceDirect.js` — **the ONLY true access detector in the whole corpus** (`.accessContent`, `.access-options-link-text`, `#check-access-popover` → returns false); then `#pdfLink@href` → `citation_pdf_url` → `.PdfEmbed > object@data` → click (browser-only by its own comment) → embedded JSON → canonical `/pdfft?download=true`; every hop through `parseIntermediatePDFPage` (meta-refresh). **2026-06-05** |
| **Springer / BMC** | DOI `10.1007`, `10.1186`, `10.1140`; `link.springer.com` | `link.springer.com/content/pdf/{doi_quoted}.pdf`; landing `/article/` or `/chapter/` → `/content/pdf/{doi}.pdf`; `citation_pdf_url` | V + **reject a `nature.com` candidate for a `10.1007` DOI**; **the template has no access check, so pair it with C10** | **"Client Challenge", dated 2026-09-05: HTTP 200 + ~3 KB JS to ANY UA, with landing-page cookies, and with a curl_cffi Chrome TLS fingerprint.** Auth markers `wayf.springernature.com`, `login.openathens.net`, `/saml/`, `/sso/`. Stated fallbacks: PMC / Europe PMC, or a real browser | `Springer Link.js` — pure template, **attaches regardless of access** (2024-07-22) |
| **Nature** | DOI `10.1038`; `nature.com` | `www.nature.com/articles/{doi_suffix}.pdf`; landing `/articles/{id}` `+".pdf"` | V + **reject a `link.springer.com/content/pdf/` candidate for a `10.1038` DOI**; reject `mediaobjects` (supplementary) | as Springer | `Nature Publishing Group.js` — `…/(full\|abs)/X.html` → `…/pdf/X.pdf`, else `a[data-track-action="download pdf"]@href` (2025-06-12) |
| **Wiley** (+Hindawi `10.1155`, IET `10.1049`) | DOI `10.1002`, `10.1111`; `onlinelibrary.wiley.com` | `/doi/pdfdirect/{doi}` → `/doi/pdf/{doi}` → `/doi/epdf/{doi}`; landing `/doi/(abs\|full\|epdf)/` → `/doi/pdfdirect/`; optional `?download=true` | V + DOI must appear in the candidate path; **exclude** `suppl_file`, `suppdata`, `supporting-information`, `/pb-assets/` | 403 to a non-browser UA; `/action/showlogin`, `login.openathens.net`; **`epdf` is a PDF.js viewer → read `defaultUrl`** | `Wiley Online Library.js` — `citation_pdf_url` then `.replace('/pdf/','/pdfdirect/')`, plus a reverse rewrite back to the landing page (2025-06-11) |
| **IEEE** | DOI `10.1109`, `10.23919`; `ieeexplore.ieee.org` | arnumber from `/document/(\d+)` or `arnumber=` → **`stampPDF/getPDF.jsp?tp=&isnumber=&arnumber={n}`** → `stamp/stamp.jsp?tp=&arnumber={n}` → **extract AGAIN from that HTML** (iframe/embed `src`, or a raw `iel[x7]…\.pdf`) → `"pdfUrl"`/`"stampUrl"`/`"pdfPath"` JSON → `citation_pdf_url`; sanctioned alternative `ieeexploreapi.ieee.org/api/v1/search/articles` (**metadata + URL only, no bytes without entitlement**) | V + arnumber match | **AWS WAF: 202 + ~2 KB JS**; `ieeexplore.ieee.org/servlet/wayf`; `challenge_risk: high`; in `BROWSER_ONLY_PREFIXES`; **sandcrawler blocklists the host outright** | `IEEE Xplore.js` — builds `stamp.jsp`, regexes the iframe `src`/meta-refresh out of it, last resort `stampPDF/getPDF.jsp` (2025-04-04) |
| **Oxford (OUP)** | DOI `10.1093`; `academic.oup.com` | landing `/{journal}/article/{rest}` → `/{journal}/article-pdf/{rest}/{doi_suffix}.pdf`; then `/doi/pdf/{doi}`, `/doi/epdf/{doi}`; `citation_pdf_url` | V + `/article-pdf/` present; reject `suppl_file` | `login.openathens.net`, `/my-account/login`; Silverchair `challenge_risk: medium`. **IA measured `academic.oup.com` 1,240 no-pdf-link + 1,010 link-loop of 2,405** | **`Silverchair.js`, NOT `Oxford University Press.js`** (which targets the *book store*): `a.article-pdfLink@href`, fallback `a#pdf-link@data-article-url`. **2026-08-10** |
| **IOP** | DOI `10.1088`; `iopscience.iop.org` | `iopscience.iop.org/article/{doi}/pdf`; landing `+ "/pdf"` | V | `challenge_risk: high`; `myiopscience.iop.org/signin`, `sesame.cld.iop.org`, `connect.openathens.net` | `Institute of Physics.js` — `url.replace(/(\/meta)?([#?].+)?$/,"") + "/pdf"`. **2016-11-01 — the stalest rule in the table; staleness is the risk, not the rule** |
| **Cambridge Core** | `cambridge.org/core` | `www.cambridge.org/core/services/aop-cambridge-core/content/view/{last-segment}/{same}.pdf` | V | not characterised in any repo read | `Cambridge Core.js` — `citation_pdf_url`, else `.actions a[target="_blank"][href*=".pdf"]`. **2026-08-06.** FedHarv's transform is **the only code implementation found in either round** |
| **Atypon family** — T&F, SAGE, ACS, ACM, PNAS, Science, Annual Reviews, Royal Society, **World Scientific**, AIP, AMS | DOI `10.1080`, `10.1177`, `10.1021`, `10.1145`, `10.1073`, `10.1126`, `10.1146`, `10.1098`, **`10.1142`**, `10.1063`, `10.1175` | `/doi/epdf/{doi}` → `/doi/pdf/{doi}` → `/doi/pdf/{doi}?download=true`; ACS `?ref=article_openPDF`; AMS `…/{art}.xml` → `/downloadpdf/view/journals/…/{art}.pdf`; landing `/doi/(abs\|full)/` → `/doi/pdf/` | V + DOI in path; reject `suppl_file`, `supplementary`, `supporting-information` | `/action/showLogin`, `login.openathens.net`, `/saml/`, `/sso/`; body "institutional login" / "access through your institution"; ACS `prewarm_required`; Science/PNAS `challenge_risk` high/medium. **IA measured `dl.acm.org` 2,230/2,319 blocked-cookie** | `Atypon Journals.js` `buildPdfUrl`: tries `['/doi/pdf/','/doi/epdf/','/doi/pdfplus/']` and **accepts a path only if an `<a href>` containing it exists on the page — the anchor-existence test IS the access check** (2022-10-25; SAGE 2026-07-21, Annual Reviews 2026-08-05, ACM **2026-03-09** gated on `#downloadPdfUrl`) |
| **APS** | DOI `10.1103` | `link.aps.org/doi/{doi}` → `/pdf/{doi}`; `journals.aps.org/{code}/abstract/{doi}` → `/{code}/pdf/{doi}` | V + DOI (raw or `%2f`) in a `/pdf/` or `/doi/` path; **reject `/accepted`** | `login_inst_user` (username/password, not SSO) | — |
| **PLOS** | DOI `10.1371`; `journals.plos.org` | journal path from the DOI code table → `journals.plos.org/{journal}/article/file?id={doi}&type=printable`; landing `article?id=` → same | V. **Do NOT require "pdf" in the URL** — the printable URL has none (this is OmicsOracle's exact bug) | none | `PLoS Journals.js` — EM only (2017-01-22) |
| **Frontiers** | DOI `10.3389` | `www.frontiersin.org/articles/{doi}/pdf`; landing `/full` → `/pdf` | V | JS/bot-walled in practice; in `OA_BROWSER_PREFIXES`. **IA measured 17,503 no-pdf-link, files served from `*.blob.core.windows.net`** | `Frontiers.js` — `${ARTICLE_BASEURL}/${doi}/pdf`, and **wipes the EM snapshot first** (2025-04-03) |
| **eLife** | DOI `10.7554` | `elifesciences.org/articles/{id}.pdf` | V + id match | none characterised | — |
| **RSC** | DOI `10.1039` | landing `/en/content/articlelanding/{rest}` → `/en/content/articlepdf/{rest}` | V; the exact landing→articlepdf rewrite scores +80 | `pubs.rsc.org/en/account`, OpenAthens | — |
| **GeoScienceWorld** | DOI `10.1130`, `10.2113` | `citation_pdf_url`; markers `/article-pdf/`, `/doi/pdf/` (Silverchair) | V | `showLogin`, `/institutional-login`; `batch_policy: single_only` | — |
| **Project Euclid** | `projecteuclid.org` | `/(10\.\d+/…)\.full` → `journalArticle/Download?urlId={doi}`; or `.full` → `.pdf` | V | **Incapsula, 212-byte body** — the named reason the host rule exists | r1 A1 measured a constructed Euclid PDF at 200, 2,337,841 B |
| **JSTOR** | `jstor.org` | `/stable/pdfplus/{jid}.pdf?acceptTC=true` | V | — | `JSTOR.js` — **`acceptTC` is a terms-acceptance flag, Kam's call** (2024-03-31) |
| **PMC / Europe PMC** | `pmc.ncbi.nlm.nih.gov`, `europepmc.org` | `europepmc.org/articles/{PMCID}?pdf=render`; `ptpmcrender.fcgi?accid=&blobtype=pdf`; `oa.fcgi?id=`; landing `+"/pdf"` else first `href="…pdf"` (**relative — append `/` to the base before `urljoin`**) | V | **the `pmc.ncbi` PDF path serves reCAPTCHA** | `Europe PMC.js` — site API → first `fullTextUrl` with `documentStyle=='pdf'`, stops replacing once one has `availabilityCode=='OA'` (2024-03-23) |
| **Conference venues** (CVF, OpenReview, ACL, NeurIPS, PMLR, JMLR) | host match | CVF `/html/…_paper.html` → `/papers/…_paper.pdf`; OpenReview `/forum?` → `/pdf?`; ACL `/abs/`→`/pdf/` else `+".pdf"`; NeurIPS `-Abstract*.html` → `-Paper*.pdf`; PMLR `{base}/{slug}.pdf`; JMLR `/papers/v{n}/{slug}.html` → `/papers/volume{n}/{slug}/{slug}.pdf` | V | none (static hosts) | — |
| **arXiv** | `10.48550`; `arxiv.org` | `versionedArXivURL.replace("/abs/","/pdf/")` with version capture `v(\d+)`; **host rewritten to `export.arxiv.org`** | V | none. **IA measured `arxiv.org` 17,370/17,817 success — the most reliable host in the whole base-rate table** | `arXiv.org.js` **2026-05-19** |
| **Zenodo + 12 InvenioRDM hosts** | `10.5281`; `zenodo.org` | `citation_pdf_url` meta; metadata from `{record}/export/csl` | V | none | `InvenioRDM.js` **2026-05-19** |
| **DSpace 7** | `/server/api/core/items/{uuid}` | the REST bitstream walk (B16) | V (bitstreams carry **no `.pdf` extension**) | usually none | `FAO Knowledge Repository.js` **2026-02-09** |
| **DSpace 5/6 · EPrints · bepress · OJS** (incl. NOAA IR, theses, WHO IRIS) | `/view/abstract/`, `/article/view/`, `cgi/viewcontent`, `/handle/` | `citation_pdf_url` / `bepress_citation_pdf_url` / `eprints.document_url`; else **enumerate all bitstream `…/content` URLs** and let V reject non-PDFs | V | usually none | **`EPrints.js`, `DSpace.js` and `bepress Digital Commons.js` DO NOT EXIST** at `c8300377`; `DSpace Intermediate Metadata.js` is a METS **import** translator. The coverage is Embedded Metadata's **suffix match** on `eprints.` / `bepress_` `citation_pdf_url` |
| **ResearchGate** | `researchgate.net` | **`meta[property="citation_pdf_url"]` — `property`, NOT `name`** | V | RG blocks scripted access; needs H15's exported session cookies | `ResearchGate.js` 2020-10-18 |
| **USFS Treesearch** | `research.fs.usda.gov` | A8's sitemap → `/download/treesearch/{id}.pdf`, or the record page's `citation_pdf_url` | V + title/author/year at 0.85 | none | `Treesearch.js` 2021-06-07 |
| **NASA NTRS** | `ntrs.nasa.gov` | `/citations/{id}` → `/api/citations/{id}` → `downloads[].links.pdf \|\| .original` | V | none | `NASA NTRS.js` 2024-03-21 |
| **Unknown host (default)** | — | 1) `citation_pdf_url` **and any meta key ending `pdf_url` on `name`/`property`/`itemprop`, in `<head>` OR `<body>`**, plus `og:pdf` and `fulltext_pdf_url`; 2) `<link>`/`<iframe>`/`<embed>`/`<object>` with a PDF type or target; 3) **PDF.js `defaultUrl`**; 4) query-param unwrap (`file=`, `pdf=`, `src=`, `url=`); 5) JS `window.open(…)` / `href=` / `location=` / `data-pdf-url`; 6) quoted then unquoted `href\|content\|src="…pdf"`; 7) LLM link extraction on the same HTML | V + `pdf_candidate_score` ranking; **cap the candidates tried** | **200 + `text/html` + no citation metadata at all = an interstitial; discard the URL and do NOT record it as the landing page** | Embedded Metadata is **147 publishers' entire recipe** |

### 2.2 Two corpus-level facts about this table

- **382 of Zotero's 748 translators can never yield a PDF. Of the 366 that can, 147 need NO per-site
  code at all** (pure Embedded Metadata — i.e. the `citation_pdf_url` rung, ~40 lines of Python) **and
  334 of 366 (91%) reference no browser-only API.** The 32 that do — ScienceDirect, Wiley, IEEE,
  JSTOR, Semantic Scholar, Frontiers, OSF among them — all keep the browser path as a *fallback branch
  beside a non-browser one*. **VERDICT: port the rules; do not run the Docker container.**
- **`translation-server` cannot return a PDF URL and there is no workaround.** No flag, no format, no
  env var, no maintained fork. Issue #97 open since 2019-03-13; **PR #99 (`wetneb:attachments`, 4
  commits, tests updated) open and unreviewed for 6.5 years** with maintainer pings in Apr 2019, Dec
  2019, Mar 2020 and 2025-11-11 and no reply; PR #151 closed abandoned 2022-12-24; issue #70 says it
  cannot translate a direct PDF URL at all. The filter moved from `translation-server/src/utilities.js:68`
  (2019) to `zotero/utilities` `utilities_item.js:itemToAPIJSON` (2026) **but survived**.
  **RE-GRADE of round-1 §6.1 and A3 §1 row 3, which framed this as "a 1-line patch or
  reimplementation": it is reimplementation.** The one thing Docker is still worth: **a ONE-OFF run of
  the patched PR-#99 branch over litkb's 35 `no-oa-copy` and 26 `bad-file` landing pages, to MEASURE
  recovery before committing to a port.**

---

## 3. Base rates and calibration — what a mature ladder actually achieves

All numbers in this section are the Internet Archive's, measured on its own ingest pipeline and
recorded in `internetarchive/sandcrawler` `notes/ingest/` @ `e23e2bd5` (47 dated files, 2019-10 →
2023-12). **They are not litkb's numbers and not this corpus's numbers** — they are the only external
denominator either round found, and they are the answer to round-1 C1's objection that a 95% target is
unsubstantiated.

### 3.1 The two base-rate tables

**Unpaywall corpus, cumulative 2020-08-28, n = 27,652,868** — i.e. a mature ladder run on gold/green
OA URLs:

| status | count | share |
|---|---:|---:|
| success | 22,063,013 | **79.79 %** |
| no-pdf-link | 2,192,606 | 7.93 % |
| redirect-loop | 1,471,135 | 5.32 % |
| terminal-bad-status | 995,106 | 3.60 % |
| no-capture | 359,440 | 1.30 % |
| cdx-error | 358,909 | 1.30 % |
| wrong-mimetype | 111,685 | 0.40 % |
| wayback-error | 50,705 | 0.18 % |
| link-loop | 29,359 | 0.11 % |
| null-body | 13,667 | 0.05 % |

A later snapshot (2021-04) adds **`wayback-content-error` 357,345 — a status class litkb has no
analogue for at all.**

**OAI-PMH corpus (the repository / grey-literature analogue), 2023-06, n = 58,212,158**:
success 20,749,080 (**35.64 %**), no-capture 15,930,221 (27.37 %), no-pdf-link 15,789,081 (27.12 %),
redirect-loop 4.72 %, terminal-bad-status 2.19 %, wrong-mimetype 1.23 %, link-loop 1.20 %, plus
`skip-wall` 57,808 and `blocked-wall` 3,060. The 2020-05 snapshot over its eight largest
(n = 51,011,715) reads no-capture 32.94 %, no-pdf-link 29.20 %, **success 27.25 %**.

**The two readings that matter for Kam's target:**

1. **A mature ladder on OA URLs lands ~80% on the first pass.** So **the last fifteen points of a 95%
   target must come from later rungs, not from more OA indexes.** That is independent, external
   support for the layered design — and it is consistent with finnschwall's self-reported ~86% on a
   582-paper review, and with §0.2's measurement that litkb's own OA miss bucket has a free ceiling of
   about 9 of 35.
2. **Repository harvesting is a one-in-three business at IA scale, three years apart.** Budget **~30%,
   not ~80%**, for Stage D/E repository rungs including the metha idea. Round 1 priced that layer as
   "the difference between ~85% and ~92%"; this says the *gross* yield is low even when the rung works.

### 3.2 What fraction of misses is our-parser-failed vs transport-blocked vs truly-absent

**This is the question round 1 could not answer, and the answer CONTRADICTS round-1 §0.3 item 8.**
IA's own per-domain triage of its largest `no-pdf-link` domains (`2021-05_daily_improvements.md`),
verbatim:

| domain | no-pdf-link / total | IA's own annotation | cause class |
|---|---|---|---|
| `apex.ipk-gatersleben.de` | 1,132 / 1,253 | "seem to be datasets/species, not articles" | **not-an-article** |
| `books.openedition.org` | 1,466 / 1,784 | "these are not actually OA books (or at least, not all are)" | **not-actually-OA** |
| `apps.crossref.org` | 4,075 / 4,693 | "they are doing a dynamic/AJAX thing, so access links are not in the HTML" | **JS-injected link** |
| `acervus.unicamp.br` | 1,853 / 1,967 | "captures with a blank page? … messy, going to move on" | **blank capture** |

**Four causes, and only one (`apps.crossref.org`) is a parser bug.** Round 1 called `no-pdf-link` "the
failure most worth fixing"; on IA's own largest instances that is the minority case. **Keep the status
— it is still the only status that names a fixable backlog — but a pure parser-fix programme recovers
well under the 7.9% / 27.1% headline.**

Three more calibration facts that change how litkb should type its misses:

- **Per-host determinism (the measurement behind round-1 rule R4, "blame the host, not the work").**
  30-day CUBE over `fatcat-changelog`: `acervus.unicamp.br` 21,978/21,980 no-pdf-link;
  `doi.ala.org.au` 2,373/2,373; `apps.crossref.org` 2,537/2,537; `cas.columbia.edu` 1,038/1,038;
  `dl.acm.org` 2,230/2,319 blocked-cookie; `aip.scitation.org` 843/1,071 blocked-cookie;
  `brill.com` link-loop 2,681 + no-pdf-link 1,410 of 4,272; `arxiv.org` 17,370/17,817 success.
  **A host's outcome is near-deterministic, so a per-work retry of a host-gated failure is wasted
  spend.** That is the fix for Sci-Hub burning 26 per-work attempts for 0 files, stated as a number.
- **`cookieAbsent` — a 200-OK wall that looks like a miss.** `www.ahajournals.org` booked 5,738
  `no-pdf-link`; every sampled row's `terminal_url` was `/action/cookieAbsent` with
  `terminal_status_code` **200**. IA, verbatim: *"Ah, the ol' annoying 'cookieAbsent'… needed custom
  pdf-link detection. FIXED: added pdf-link detection"*. **litkb stores neither `terminal_url` nor
  `terminal_status_code`, so it cannot make this distinction at all** (see E6-RG).
- **MDPI has been hostile to crawlers since 2020**: `www.mdpi.com` 13,866 `terminal-bad-status`,
  2,693 `wrong-mimetype`, **436 success**. The same wall round 1 hit — and A6 now walks around it.

### 3.3 What a crawl converts, and how a patch pass behaves

2022-04 Unpaywall patch crawl: before, `no-capture` 3,330,232 and `success` 2,455,102; after,
`success` 4,784,948 = **+2,329,669, about 77% of the no-capture pool**, with `redirect-loop` +288,153
(~10%), `terminal-bad-status` +185,235 (~6%), `no-pdf-link` +85,257, `blocked-cookie` +95,294.
**This is the price of round-1 Stage E: a targeted crawl converts roughly three quarters of
"we never captured it", and almost nothing else.**

### 3.4 What this implies for litkb's ledger vocabulary

litkb has **four** statuses. sandcrawler has ~25, with **eight distinguishable bind-time states**
(`not-pdf`, `bad-pdf` by sha1 blocklist, `empty-pdf`, `empty-page0`, `parse-error`, `text-too-large`,
`bad-unicode`, `success`) and `page_count` + `word_count` on every success.

**Round 2 shows eight is not the ceiling. At least twelve are distinguishable**, and the four new ones
are all states litkb would otherwise book as `success` or as an undifferentiated `bad-file`:

| # | State | How it is detected | Source |
|---|---|---|---|
| 9 | **`stub-not-article`** — a valid PDF that is a pre-proof or a TDM first-page cover sheet | "journal pre-proof" / "article in press" markers, < 3,000 chars, no reference section; **and the `X-ELS-Status` response header** | C16, H2-RG |
| 10 | **`volume-not-article`** — a 60+ page proceedings booked as one paper | `page_count >= VOLUME_PAGES(60)` + contiguous title match to extract in place | C17 |
| 11 | **`cited-document-not-this-article`** — the PDF you fetched is one the paper CITES | `DOI_PAGES=3` so a bibliography cannot supply the DOI | guard 4 / T14 |
| 12 | **`compressed-or-archived-payload`** — a good PDF inside gzip or tar.gz | libmagic sniff before the `%PDF-` test | C18 |

Plus, from C1-RG, `bad-file` itself splits five ways (`html_response`, `too_small`,
`missing_pdf_header`, `corrupt_pdf_header`, `early_eof_with_trailing_payload`), and from C13 `blocked`
splits four ways (`identity_required`, `challenge_or_bot_check`, `not_found`, `html_or_reader`).

**The minimum schema change, in order of cheapness:**
`terminal_url`, `terminal_status_code`, `terminal_dt` (three columns — they are the entire input to
E6, to the `cookieAbsent` split and to per-host determinism) → `page_count`, `word_count` (every stub
heuristic downstream is a predicate over those two) → `retriable` **per attempt**, not per status →
`kind` (`pdf | jats | text | html-doc | cached_text | snippet`) → `articleVersion` → an
`unverified_keep` counter.

---

## 4. Books, chapters, theses, reports — merged

### 4.1 The routing decision, restated

Stage F (books/ISBN) and Stage D (agency/thesis) are only reachable at all through **A2, the
work-class classifier**. A book routed to a DOI-keyed paper rung misses **by construction**, not by
bad luck: LibGen's book table is ISBN-addressed (`search.php?column=identifier`) while its paper table
is `scimag/ads.php?doi=`, and litkb's archive route is `scidb`-by-DOI.

### 4.2 What round 2 changed here — four negatives and one correction, all NARROWING

**Round 2 added no new book rungs.** It removed or shrank four leads:

1. **The thesis discovery layer named in round-1 §3.1 is dead.** `v2.sherpa.ac.uk/cgi/retrieve?item-type=repository&format=Json`
   → **403 with `<title>Jisc - Error 403</title>`, a Cloudflare "Web page blocked" page.** Not a 401 —
   the request never reaches the application, **so a free key would not help**. Substitutes:
   `miku/metha` `contrib/sites-roar.tsv` (84,610 B, already in that repo), or CORE's
   `repositories.id:` whole-repository dump (D15).
2. **The metha endpoint census is mis-sized for theses by roughly 10×.** Round 1 (§3.1 and D6) says
   "244,347 OAI-PMH endpoints, 34,335 of them on `.edu` or `.gov`". MEASURED: **OJS 184,797 (75.6%)**;
   all repository platforms together ~6,200 (DSpace 3,676 + Islandora 1,157 + EPrints 959 + Digital
   Commons 832 + DSpace-7 332 + Janeway 48); **only 1,109 of those are `.edu`**; `.edu` overall 4,830,
   `.ac.uk` 913, **`.gov` 45**. **It is a strong OJS-journal route and a weak thesis route.**
3. **Z-Library's eAPI documentation contains no code.** `baroxyton/zlibrary-eapi-documentation` at
   `e2184c46` is one file — `README.md`, 2,892 bytes — which round 1 already fetched. F10 cannot be
   improved from this source.
4. **Zotero cannot help with books.** `Open Library.js` (2017-05-25), `HathiTrust.js` (2025-04-29) and
   `Google Books.js` (2026-07-22) all carry **no PDF logic whatsoever**; Open Library's translator does
   not even hand off the `ocaid` to Internet Archive. `OAPEN.js` only checks whether a Full Text PDF
   attachment already exists. **This independently re-confirms round-1's F5/F6 negatives and closes the
   hope that the translator corpus fills the book gap.**

And it corrected one thing in litkb's favour: **DSpace 7's REST bitstream walk (B16) plus bitstream
enumeration (C20) is a real, keyless file route into institutional repositories, theses and WHO IRIS**,
and it is strictly better than D6's OAI-PMH METS route for any repository upgraded since 2022.

### 4.3 The agency / grey layer after round 2

| Source | Status after round 2 |
|---|---|
| **USFS Treesearch** | **SOLVED** — sitemap enumeration + `citation_pdf_url`, measured (A8) |
| **USGS Publications Warehouse** | working, measured in round 1 (1,198 records for `q=canopy`) |
| **City / county canopy reports** | **NEW ROUTE, measured** — ArcGIS **Online** item search, 99 canopy PDFs, the first one literally a city tree-canopy assessment (D12). ArcGIS **Hub** datasets is a dead end (D8-RG) |
| **NOAA IR / CDC Stacks / BTS ROSA-P** | keyless Fedora JSON + OAI documented by NOAA itself, **behind a UA-independent Akamai 403 on this egress** — a host gate, possibly egress-specific (D14-RG) |
| **DTIC** | **dead** — REST closed 401, search API an "Under Maintenance" stub, `/api/search` returns a PNG decoy (D17-RG) |
| **State libraries** | **new, unexploited class** — `dc.statelibrary.sc.gov/oai/request` answers 200 `text/xml`; **`www.sos.wa.gov/library/digcolls.aspx/oai/oai.php` (Washington State Library) is the highest-value unprobed item in the survey** (D13) |
| **USDA-ARS, NAL, NIST, NTL ROSA-P, NTSB, EPA NLC, ERIC, World Bank OKR** | Zotero translators exist (D14); ERIC has a keyless API and a direct `files.eric.ed.gov/fulltext/{id}.pdf` (B24) |
| **Theses** | `CORE (with key) → OpenAlex/DataCite → the university's own DSpace 7 REST / OAI-PMH`. **Not ProQuest.** Dead or dying: EThOS (offline since the Oct-2023 British Library attack), OATD (403, no API), PQDT Open (521), DART-Europe (closed 2025-02-03), OpenDOAR/ROAR (Cloudflare) |
| **Proceedings volumes** | **NEW** — C17's whole-volume detection matters here specifically: **ISPRS Archives** and AGU/IEEE proceedings are exactly the shape that binds a 400-page book as one article |
| **HTML-only agency reports** | **NEW** — C24's `cached_text` state. For this layer "degrade to HTML-as-text" is often the only artefact that will ever exist |

### 4.4 Format conversions (round 1, unchanged and still VERIFIED at pinned shas)

| From | Tool | Note |
|---|---|---|
| DjVu | `ddjvu --format=pdf` | `ispras/dedoc@a023004` |
| `.doc` / `.docx` / `.pptx` / `.odt` / `.rtf` | `soffice --headless --convert-to` | **this is what makes city and agency reports usable** |
| EPUB / MOBI / AZW3 | `calibre ebook-convert`, or markitdown `EpubConverter` | |
| TIFF / JPEG bundle | `img2pdf` then `ocrmypdf` | |
| HTML | trafilatura + newspaper4k arbitration | record `kind="html-doc"`, never `pdf` |
| JATS / TEI | direct to sectioned text | **better than a two-column PDF** — real section boundaries, no header bleed, no column interleaving. Round 2 makes this a *preference*, not just a fallback (B27) |
| gzip / tar.gz | libmagic sniff → decompress in place | **NEW (C18)** — a wrapped PDF currently books `bad-file` |

**Guard on every conversion**: dedoc's `_run_subprocess(expected_path=…)` shape, so "the tool exited 1
but wrote the file" and "the tool exited 0 and wrote nothing" are distinguishable.

### 4.5 The admission gate that protects the 95% number

Accept only when **(a)** the magic family matches the extension; **(b)** for EPUB the OCF `mimetype`
entry is exact; **(c)** page-1 text overlaps the expected title **or** an expected identifier appears
in the front matter; **(d)** the recorded `kind` is one of `pdf | jats | text | html-doc | cached_text`.
**A work that reaches the gate with `kind != pdf` is a DIFFERENT outcome from a miss and needs its own
ledger status**, or the 95%-with-PDF target silently absorbs works for which no PDF exists at all.
Round 2 adds the counterpart for the *other* kind of silent inflation: **guard 17's unverified-keep
counter**, for a file kept only because its metadata could not be fetched.

---

## 5. The extraction and OCR ladder, MERGED

### 5.1 The scope boundary, stated first (unchanged)

**Extraction converts only `bad-file` and `scan-needs-ocr`. It cannot unlock a paywalled PDF, and it
does not move the 95-percent-with-PDFs target at all.** It determines whether the PDFs already held
are usable.

Two exceptions where extraction feeds acquisition: **GROBID's citation model +
`consolidateCitations`** turns a held PDF into resolved DOIs for works litkb does not have; and
**CERMINE's standalone `CRFBibReferenceParser -reference "<string>"`** parses a single reference
string with no document — exactly what you need when all that survives of a scanned 1970s paper is an
OCR'd bibliography page.

### 5.2 The layer round 2 added at the TOP: repair the CAUSE, not the symptom

Round 1's §4.2 has firecrawl's `text_quality.rs` as "the best garble detector found". **That detector
is a symptom test over an already-decoded string. The four files round-1 §6.7 named are the CAUSE
layer, and they are worth more, because a repaired CMap means there is no garble to detect.**
All at `firecrawl/pdf-inspector@7a34011`.

**The five-source ToUnicode fallback ladder**, in the order `font_cmap_entry` consults it:
1. the stream's own `/ToUnicode` CMap;
2. `try_remap_subset_cmap` — a sequential remap of it;
3. `build_fallback_tounicode_from_encoding` — the simple font's `/Encoding /Differences` glyph names;
4. `build_cmap_from_truetype` on the embedded program, repaired through `get_cid_to_gid_map`;
5. `build_cmap_from_cid_system_info` — the CID collection (`adobe_korea1.rs`, 17,056 entries,
   binary-searched; Japan1 / GB1 / CNS1 via the bundled pdf.js bcmaps).

**Two thresholds that decide the roles**: a ToUnicode CMap with **fewer than 10 entries** yields the
primary role to the font's own reading; and, from the source's own comment, *"Subset fonts number GIDs
by document encounter order, so the sorted sequential remap scrambles characters. The TrueType cmap
table maps the real GID→Unicode and is authoritative."*

**`ControlDestination` — the NAMED CAUSE of ligature garble.** From the source: a producer writes a
ligature glyph's own index as its ToUnicode destination (*"a ligature glyph at index 18 gets
`<0012> <0012>`"*), so `ffi` decodes to a C0 control and reads as U+FFFD. `repair_control_destinations`
recovers it from the fallback CMap, then the program reading, then — for a Type0 font — by mapping
glyphs with an advance but **no outline** to a space. **This is litkb's ligature migration, stated one
layer up.**

**The quality metric and the abandon rule**: `CidDecodeStats{codes, interpolated, unmapped}`, and
`if stats.codes > 0 && stats.unmapped - control_destinations > stats.codes / 2 { return empty }` —
**more than half the codes unmapped ⇒ return nothing so the caller falls through to another method**,
with `ControlDestination` deliberately excluded from the count because *"its U+FFFD is the CMap's own
reading of the code, not a sign that the CMap is the wrong reading"*. **This is the explicit
"this reading is the wrong reading, fall through" predicate litkb's GROBID/Docling rule-based
reconciliation lacks.**

**Gap interpolation is heavily guarded** — seven conditions before one character is invented: gap ≥2
and ≤ `MAX_GAP_FILL_WIDTH = 32`; both bounding codes read as exactly one non-U+FFFD character; both in
the same `gap_fill_class` (Digit, or Upper/Lower within one of ten cased script blocks); codepoint
distance equals code distance; every codepoint between of the same class; and the runs on both sides
must rise monotonically.

**`glyph_name_to_string` decomposes ligatures AT SOURCE** — AGL spec, components first:
`glyph_name_to_string("f_i.liga") == "fi"` (two ASCII letters) while `glyph_name_to_string("fi") ==
"\u{FB01}"`. **Where a PDF names glyphs compositionally, no downstream ligature fold is needed at
all.** Its fidelity rule is quotable for litkb directly: *"Every component must read, or the name does
not"* — a name that cannot be read stays **unread** rather than half-read. It refuses `uni0066X`,
`uni006`, `u12`, `f_zzz`, `f__t` outright.

**Overlong `/BBox` numerals → an EMPTY page that is NOT a scan.** A re-save pattern writes the form
XObject's `/BBox` as four **308-digit** integers (±DBL_MAX/2 written out, meaning "unbounded"); a
64-bit parser cannot hold them, the object is dropped, the page's `Do` draws nothing, **and the page
comes out empty**. Rare but silent, and an OCR rung would "fix" it by transcribing a blank. The repair
is byte-level and offset-preserving, bounded at `MAX_OBJECT_SPAN = 64 KiB` per object and
`MAX_BYTES_EXAMINED = 16 MiB`.

**Consequence for round-1 §4.2 and §4.6 tier 6**: the ftfy and GROBID ligature rows are **not wrong but
downstream of the cause**. **The fidelity rule should read: repair at the CMap, normalise only what
survives.** And round-1 §4.6's mutation test ("corrupt a known-good PDF's ToUnicode CMap") now has a
repair to assert as well as a detector: the test must show **both** that the gate fires **and** that
the repair recovers the text.

### 5.3 Bind-time validity gates

- **`qpdf --check`** (round-1's C1 lead, now read at `qpdf/qpdf@54d6053`): full traversal, full stream
  decode to `Pl_Discard`, per-page content parse. Three states — **0 clean, 3 warnings (recoverable
  damage), 2 errors**. Catches truncated downloads, broken Flate, dead object streams and zero-page
  files that `%PDF-` magic does not. **GUARD: `--is-encrypted` / `--requires-password` reuse exit codes
  2 and 3 with completely different meanings** (`qpdf_exit_is_not_encrypted = 2`), **so a ladder that
  reads "2 = damaged" invents `bad-file` rows.**
- **`is_pdf_too_complex`** (`Unstructured-IO/unstructured@0ca5563`) — round 1 saw the call site, not the
  heuristic. It is **10,000 graphics ops AND a ratio > 20:1**, counted **by regex on the raw decoded
  stream**, with a **100 KB `min_raw_stream_bytes` skip**, an early exit before text counting, five
  CVE-2026-33123 caps that also return True (50 MB/page, 10k array entries, 1 GB doc, 1M entries),
  `DEFAULT_MIN_FILE_SIZE_BYTES = 0` (inspect every file), and — critically — **the whole function is
  wrapped in `except Exception: return False`, i.e. it FAILS OPEN.** **High value for this corpus**:
  it is the pre-filter for vector-heavy GIS figures (classification maps, contour plots) that hang
  pdfminer.
- **libmagic MIME check** (C21) and **transparent decompression** (C18) at bind.

### 5.4 The tool table (round 1, condensed, with round-2 corrections marked)

| Layer | Tool | Fit vs 4 GB T2000 / free CPU Colab | Licence | Measured number (who measured) | Note |
|---|---|---|---|---|---|
| **0 Prefer a better input** | **s2orc-doc2json `tex2json`** | CPU (LaTeXML) | Apache-2.0 | exact by construction | **Exact text, exact equations, exact section structure. No OCR, no ligature repair, no dehyphenation** |
| 0 | Europe PMC `/fullTextXML`; Springer `xmldata/jats` | CPU | open / free key | 3–6% of this corpus (E4); A1 measured 0/7 | **round 2 makes this a PREFERENCE (B27), not a fallback** |
| **1 Triage** | **firecrawl `text_quality.rs@7a340112`** | CPU, pure string statistics | — | ships its own calibration: garbled page vowel ratio **0.245**, case-shift **0.225**, English cosine **0.532**; closest legitimate document **0.264 / 0.021 / 0.801**. Gates: `vowel_ratio > 0.30` clears; `case_shift_bigrams >= 0.10 × letter_bigrams` OR (`english_cosine < 0.60` AND `english_shape_cosine >= 0.90`) condemns; requires ≥200 ASCII letters | **per-page**, so you OCR three bad pages of a thirty-page report. **RE-GRADE: §5.2's CMap repair runs BEFORE this** |
| 1 | MinerU PUA detector | CPU, milliseconds | AGPL-3 (asserted) | PUA `count >= 2` AND (`max_run >= 2` OR `ratio >= 0.05`), plus a `(cid:N)` frequency check | **span-level and REVERSIBLE** (`_restore_post_ocr_fallback`) |
| 1 | marker `detect_bad_ocr` | CPU, no model | Apache-2.0 | spaces>0.7, newlines>0.6, alphanum<0.3, U+FFFD > max(6, 3%) | **collapses TOC dot-leader runs `(?:[.·•…_\-]\s*){3,}` BEFORE the ratio tests**, or every agency-report contents page goes to needless OCR |
| 1 | marker `LineBuilder@8a1d2344` | CPU, no model | Apache-2.0 | a line overlapping >2 others at >0.1 overlap; page condemned when that fraction exceeds 0.5 | **The ONLY detector for "a scanned PDF that already carries a BAD OCR text layer" — it binds, extracts "successfully", is searchable, and every verbatim quote from it is subtly wrong. litkb cannot see this today** |
| 1 | sandcrawler bind-time ladder | CPU | — | 8 states + `page_count` + `word_count` | **round 2 raises it to 12 (§3.4)** |
| **2 Born-digital** | **GROBID 0.9.x + pdfalto 0.6.3** | CPU (Java); already in use | GPL-2 | PMC_sample_1943 @0.9.0: header all-fields **F1 58.79 strict / 88.51 Levenshtein**; citation all-fields **83.64 / 87.69**; in-text callout linking **58.47 strict** | reference PARSING is good enough to mine DOIs; callout LINKING is not |
| 2 | **Docling** | CPU; reading order is rule-based, no model | MIT | 50.3 olmOCR-bench overall (per marker) — lowest of the GPU pipelines | already in use; **three shipped features unused**: `rate_text_quality`, confidence grades (<0.5 POOR … documented for "unattended batch conversions"), `OcrMode.PDF_AWARE_LAYOUT_REGIONS` |
| 2 | **MinerU 4.x tier `basic` + ONNX** | **~0.8 GB models, 2 GB RAM, CPU works — FITS the T2000 and fans out free on CPU Colab** | AGPL-3 (asserted) | 72.7 olmOCR-bench overall; **86.47 OmniDocBench**; 261 scanned pages in 9.9 min / ~7 GB VRAM peak on an 8 GB 4060 | **RE-GRADE: MinerU collapses to 54.6 on Old-scans-math** (§5.6) |
| 2 | marker + pdftext | `--mode fast --disable_ocr` is pure CPU, **23.7 pg/s** | Apache-2.0 code / OpenRAIL-M weights | 43.6 overall / 55.8 digital in fast mode vs 20.4 for a raw text dump | four liftable heuristics: triage; `detect_bad_ocr`; `IgnoreTextProcessor` running-head removal (~40 lines, no model); cross-page continuation via `.*[\p{Ll}\|\d][-—¬]\s?$` |
| 2 | PyMuPDF | CPU | **AGPL-3** | — | `get_textpage_ocr(full=False)` is **genuine partial OCR**. **VERIFIED FALSE CLAIM: `sort=True` is a plain y-then-x sort that INTERLEAVES two-column pages** |
| 2 | pdfminer.six / pypdfium2 / `pdftotext` / pdfplumber | CPU | pypdfium2 **Apache-2.0/BSD-3 — the AGPL-free engine under pdftext and marker** | PyMuPDF / pypdfium2 ~0.1 s avg, `pdftotext` ~0.3 s | `LAParams.boxes_flow` is a **free untouched lever** on two-column behaviour; `all_texts=False` **silently drops text inside figure XObjects** |
| **3 Repair** | **OCRmyPDF** | CPU, page-parallel | **MPL-2.0** | — | **The right spine — do not rewrite grafting, page parallelism, deskew, per-page timeout or PDF/A.** `--redo-ocr` targets an invisible/corrupt layer; **`--force-ocr` when `has_corrupt_text`** (its own advice: `--redo-ocr` is WRONG there). Timeouts write `[skipped page]` to the sidecar = **a free per-page failure census.** Default mode RAISES `PriorOcrFoundError` rather than guessing |
| **4 Classical OCR** | **Tesseract 5** | CPU only, free | Apache-2.0 | **1960s-scan head-to-head, 88 pages, cosine-sim: Tesseract 92.4% overall (typed 97.6%, handwritten 42.6%), 10 s on 16 cores** vs Surya 188 s on a 3080. **Absent from olmOCR-Bench entirely** | several rungs for almost nothing: PSM 0/1/2/4/6/11/12 (**psm 1 = auto+OSD, the right choice for two-column scans**); OEM 0–3; three binarizations from one `-c` flag; `tessdata_fast` vs `tessdata_best`; `--user-words` for a domain lexicon |
| 4 | RapidOCR (ONNX) | `pip install rapidocr onnxruntime` — no torch, no GPU | Apache-2.0 code | — | **SHARES WEIGHTS WITH PADDLEOCR — counting both as independent voters is a correlated-error trap** |
| 4 | Windows.Media.Ocr via `winocr` | **built into Kam's Windows 11**, one `Add-WindowsCapability` | MS | — | **a genuinely different lineage → a real independent voter**, but **no confidence field**, so it votes unweighted |
| 4 | **docTR** *(NEW, round 2)* | CPU-capable, PyTorch | Apache-2.0 | — | **a classical voter lineage not weight-correlated with the Paddle family** |
| **5 VLM** | olmOCR v0.4.0 | ~20 GB VRAM → Colab | **Apache-2.0 code AND weights** | see §5.6 | **the best-engineered per-page ladder found** |
| 5 | Chandra / Surya | vLLM; Colab | modified OpenRAIL-M | see §5.6 | **RE-GRADE: the Overall gap to olmOCR is inside the error bars** |
| 5 | Nougat | GPU | weights **CC-BY-NC-4.0** | — | keep one mechanism: `StoppingCriteriaScores` takes the **variance of the variance of max-logit over a 200-token window**, stops at **<0.015**; post-hoc detector at **<0.045**, `minlen=120`, accept if only the tail is affected (`idx/N > 0.9`), **DISCARD the page if the loop began within the first 30 windows** |
| 5 | PaddleOCR-VL / PP-StructureV3 | GPU for VL | Apache-2.0 | 80.0 overall, 97.0 headers-and-footers (author-reported) | **the only pipeline with first-class `use_doc_unwarping` and `use_doc_orientation_classify`** — photocopied/curled agency reports — plus **separate WIRED and WIRELESS table models** |
| 5 | Mistral OCR (hosted) | hosted | commercial | **Old scans 29.3 — the WORST measured, below every open model.** $1–2 / 1,000 pages | **paying does not buy you old scans** |
| 5 | MonkeyOCR *(re-graded)* | **"even the 4060 with 8GB of VRAM (suitable for … quantized 3B and 1.2B)"** | **Apache-2.0 — relicensed since round 1** | — | the licence-clean end of the field is wider than round 1 recorded |
| 5 | Dolphin v1.5 *(NEW)* | 0.3B | **MIT** | — | smallest licence-clean VLM found; **still does not reach 4 GB** |
| **6 Math** | pix2tex / LaTeX-OCR | CPU/GPU; **already in litkb** | MIT | UniMER-Test CDM/exact **0.636 / 0.291** | **it SAMPLES** (`temperature=0.25`) → self-consistency across k samples is a free confidence signal. Returns a bare `str` with **no score** |
| 6 | UniMERNet | GPU | — | **0.968 / 0.811 — best measured** | explicitly trained for **real-world degraded formulas**; README numbers are images → ASSERTED |
| 6 | PP-FormulaNet (S/M/L + ONNX) | CPU option | Apache-2.0 | — | **a genuinely different training lineage → a real independent vote** |
| 6 | Pix2Text | CPU/GPU | — | — | **the ONLY decoder surveyed that returns a per-formula confidence** (`_cal_scores` → `exp(sequences_scores)`) |
| 6 | RapidLaTeXOCR | CPU ONNX | — | — | a **deterministic** pix2tex — **SAME WEIGHTS, not an independent vote** |
| **7 Normalise** | ftfy | CPU | Apache-2.0 | — | default is `normalization="NFC"`, **not NFKC**, deliberately; `fix_latin_ligatures` is a separate targeted fix; `badness()` counts mojibake |
| 7 | GROBID `TextUtilities.clean` | CPU | GPL | — | **dehyphenation decided on LAYOUT** — removes a hyphen only when the token Y coordinate changed and the next token is all-lowercase. **Folds U+FB00–FB06 but DELIBERATELY refuses ae/oe (issue #728). It also flattens curly quotes and bullets — fine for search, fatal for a verbatim quote** |
| 7 | pd3f/dehyphen | flair LM, CPU | — | — | scores the three candidate joins by **character-LM perplexity**; `is_split_paragraph` does the same for cross-page joins |
| 7 | refextract `remove_page_boundary_lines@218f5b64` | CPU | GPL | — | **the only IMPLEMENTED generic running-head mechanism**: it **infers how many lines each header/footer occupies from repetition across page breaks**, so it generalises to the JSTOR stamp, OUP's banner and MDPI's per-page DOI line **with no rule per publisher** |
| 7 | **analiticcl / SymSpell / natas** *(NEW)* | Rust / any / Python | GPLv3 / MIT / — | SymSpell's "1 million times faster" is a README claim with no benchmark table | all three are in the correct **ADD-ONLY** shape (ranked candidates with scores, never an in-place rewrite). analiticcl: anagram-hash retrieval, score = weighted Damerau-Levenshtein + LCS + prefix/suffix + casing, plus frequency and a per-pattern confusable list. **natas is trainable from litkb's OWN registry vocabulary** |
| **8 Provenance** | docling-core `ProvenanceItem@51bc31b3` | CPU | MIT | — | `page_no` + `bbox` + `charspan` on **every** item |
| 8 | **papermage data model** *(NEW, read)* | CPU | — | — | typed annotation layers over one `symbols` string; **`Entity.text` three-tier resolution (metadata → spans → boxes→tokens)**; `intersect_by_span` yields disagreement regions for free; **tier 3 is how a SECOND extractor whose text differs from `symbols` still lives in the same document.** **CAVEAT: `Entity.text` joins with `' '` and strips newlines, so only the raw `doc.symbols[start:end]` slice is safe for litkb's verbatim-offset contract** |
| 8 | paper-qa `chunk_pdf@57e89f72` | CPU | Apache-2.0 | — | the poor-man's version, adoptable immediately: `{page_no: page_text}`, chunks named `"pages {lo}-{hi}"` |
| **9 Harness** | olmOCR-Bench | CPU to run | Apache-2.0 | 1,403 single-page PDFs, ~8,400 pass/fail tests, 8 categories | **the only benchmark with explicit Old-scans and Headers-&-footers axes and a text-ABSENCE test class.** "We stay away from soft metrics like edit distance comparisons." Its **SHAPE** is what litkb needs |
| 9 | OmniDocBench v1.5 | — | — | ranks MinerU-Pipeline **86.47** above Marker **78.44** | **has NO old-scan axis and ranks the two the OPPOSITE way to olmOCR-bench. Do not pick an extractor from one leaderboard** |
| 9 | dinglehopper (OCR-D) | CPU | Apache-2.0 | — | **the instrument for engine disagreement**: Unicode **NFC** before comparison, and **grapheme clusters** rather than codepoints. **Use it to measure, never to gate** |
| 9 | ISRI `ocreval` (UNLV 1996) | CPU | Apache-2.0 | — | **still the reference OCR voting implementation**: `vote` takes 2–16 voters with **separate weights for characters an engine marked suspect**; `nonstopacc` is the right metric when the goal is retrieval |

### 5.5 Agreement design for TEXT — multi-extractor reconciliation

**The single most liftable mechanism in the survey**: **olmOCR `topcoherency`** — run `pdftotext`,
`pdfium` and `pypdf` on the same page and pick the winner by **SmolLM-135M mean log-likelihood per
token**. ~12 lines, ~270 MB, **run on CPU by construction in the source**, engine-agnostic. It matters
because **litkb already reconciles GROBID + Docling by RULE, and a rule cannot tell you it was
wrong.** It also generalises better than OCRmyPDF's dictionary hit-ratio, **which would wrongly reject
good OCR of exactly litkb's maths-heavy 1950s–90s statistics papers**.

Prior art for the merge itself — **no general multi-extractor reconciler exists on GitHub** (E1 ran
five queries with near-zero results), so litkb's referee rung is a small piece of original work:
Unstructured's `array_merge_inferred_layout_with_extracted_layout` (six numbered rules, IoU 0.75,
**iterated to `max_rounds=5` so absorption is order-independent**); Docling's R-tree priority merge;
**papermage's data model** (§5.4, now read); Unstructured's `determine_pdf_or_image_strategy`, which
degrades on **missing dependencies** as well as document properties and raises an actionable error
when all three are impossible; and **Docling `OcrAutoModel`**, which records a typed `_Rejection` per
miss separating "no model for this language" from "not installed".

**Round-2 RE-GRADE of the OCR-D path**: `ocrd-cis-align` **requires the N inputs to share region and
line INDICES, not merely a format** — `align()` iterates `pcgtst[0]`'s TextRegion/TextLine and indexes
every other input at the same `[mi][mj]`. **So it cannot run at all without a shared segmentation
source**, which is a hard blocker for engines that segment independently (Tesseract vs RapidOCR vs
Windows.Media.Ocr). Two details worth copying anyway: the master gets `index=1` and others are
appended with `dataTypeDetails` naming the producing file group; **a missing word is recorded as an
indexed EMPTY TextEquiv, so deletions survive the merge**; word confidence is the min over tokens.

**The blocker has a solution**: **`qurator-spk/eynollah`** — old-scan layout analysis with 10
segmentation classes, curved and vertical textlines, its own binarization (pixelwise or hybrid
CNN-Transformer), heuristic or trainable reading order, ONNX Runtime, **Apache-2.0**, PAGE-XML out.
**`eynollah → N recognizers on the SAME line polygons → ocrd-cis-align → ocrd-keraslm-rate` is a
coherent, CPU-only, licence-clean pipeline that dissolves the `ocrd-cis-align` blocker.** Caveats:
Linux only (→ WSL), the README says processing can be slow, and it was evaluated on historical prints,
not journal photocopies. **ASSERTED — nothing was run.**

**What the ladder must write back to litkb**: not `extracted: true`. Per work — the winning rung, the
per-rung rejection reasons in `_Rejection` shape, pairwise CER among candidates, the coherency score,
and **a quality tier**. **The tier is what lets litkb honour its own evidence rules: a verbatim quote
should only be promotable from HIGH-tier text, while LOW-tier text is still worth having for search.**
That mirrors the project's own three-state mask rule.

### 5.6 Agreement design for SCANS — and the round-2 re-grade of the whole voting layer

**Round 1's voting precedent does not survive contact with its own repository.** Two corrections, both
from `adamd1985/lv-rover-mlt@a80e31d`:

1. **The five "voters" behind CER 1.605% → 1.317% are five CONFIGURATIONS OF TESSERACT 5** — `mlt`,
   `mlt+ita` (the anchor), `mlt+ita+fra`, stock `mlt`, and `mlt+ita` on a 2× upscale. The README says
   so itself: *"Arbitration adds no second neural network."* **Do not cite it as evidence that
   cross-engine voting works.**
2. **The same repo measured the same arbitration on Hungarian — a corpus it was NOT fine-tuned for —
   and found NO significant gain**: 200 pages, five streams, CER 0.13543 → 0.13438, **Δ 0.00105, 95%
   CI [−0.0037, +0.0054], permutation p = 0.6555, `significant_alpha05: false`**; its
   `ablation_ckpt.jsonl` shows page i=3 **worse** with five streams (163 vs 143 errors / 3,293).
   **Per CLAUDE.md §3.5 that is UNDETERMINED, not "voting works".**

**What survives, and is worth more than the voting claim, is LV-ROVER's arbitration SHAPE** — because
it inverts round 1's lexicon warning. Round 1 says a general-English lexicon will silently "correct"
*Pseudotsuga* and *heteroscedasticity* into nonsense. **`_decide` makes the lexicon a SHIELD instead of
a target**: `if self._in_lex(anchor): return anchor` — **an anchor word already in the lexicon is NEVER
overridden**, so a lexicon built from litkb's own registry metadata **protects** exactly the words
round 1 feared losing. Its companion rules are the same ADD-ONLY shape as CLAUDE.md §3.6: never shorten
alphabetic length; never touch tokens with <3 alpha characters (`a_alpha < 3 → keep anchor`, which
protects numbers and units); never drop a non-ASCII letter; edit distance ≤ 2; plurality with anchor
fallback.

**An honest ceiling for post-OCR correction, measured, reproducible, same task**
(`jarobyte91/post_ocr_correction@4db2e40`, ICDAR-2019 English, public CSV at a pinned sha): a trained
character seq2seq corrector buys **+5.11% relative (CER 19.467 → 18.472)** with sliding-window voting,
greedy, uniform weights, 197 s — and is **NEGATIVE in every configuration that omits the vote**
(−4.29%, −13.81%, −3.80%, **−30.71%**). Beam search costs 1,537 s vs 197 s and is **not better**
(18.500 vs 18.472). The weighting function barely matters (5.11 / 4.85 / 4.89). **So the vote is
load-bearing, not an optimisation** — and this is the number to pair with round 1's GPT-4o 58.1%
relative-gain figure, which has no such control.

**A voting design that needs no second engine**: **self-ensembling ONE model by sliding character
n-gram windows** — cut every offset (`string[i:i+w] for i in range(len(s)-w+1)`) and vote per
character. It sidesteps the RapidOCR/PaddleOCR shared-weights trap entirely. AAAI-2022; the English
CSV above is the verified part, the "SOTA in 5 of 9 ICDAR-2019 languages" README claim is ASSERTED.

**Round 1's two traps stand unchanged**: voter independence is real (RapidOCR and PaddleOCR share
weights — not two votes; Tesseract / RapidOCR / Windows.Media.Ocr / docTR are four genuinely different
lineages), and **more voters is not monotonically better** (`ocr_ensemble` scored 8 preprocessing×engine
combinations and found **6 of 8 beat all 8**).

**Preprocessing is a VARIANT rung, not a mandatory step.** Copy OCRmyPDF's unpaper arg set rather than
deriving one — **five of its seven flags DISABLE unpaper features** because the maintainers found the
aggressive filters destroy content. Counterpoint from kraken's own `binarization.py`: *"Binarization is
no longer necessary for most workflows"*. **NEW: `ocrd-binarize-olena` gives nine binarization
algorithms from one CPU CLI** — otsu, niblack, sauvola, kim, wolf, sauvola-ms, sauvola-ms-fg,
sauvola-ms-split (the OCR-D default), singh — vs Tesseract's three. **Hazard, stated per §3.4c: nine
binarizers is nine chances to pick the one that flatters the gold set.** C++ built from source → WSL.

**Stop rules — two engineered answers**: **Nougat DETECTS** the pathology (§5.4), **olmOCR RECOVERS**
from it (escalating temperature `[0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 0.9, 1.0]`; schema-enforced front
matter with retry on malformed output; **sequential** retries for rotation but **parallel** fan-out the
moment the vLLM queue empties; **terminal fallback to `pdftotext` marked `is_fallback=True` so a page
never comes back empty**). Both are worth having.

**THE DANGEROUS RUNG IS THE VLM**, unchanged and now with a concrete example of the failure mode: *a
VLM will fluently invent plausible text where a scan is illegible, and that output scores WELL on both
a dictionary gate and an LM coherency gate because it is fluent English.* The only strong guard found
is **requiring agreement with the classical consensus above a CER threshold before accepting VLM text
at HIGH tier**. The concrete example round 2 supplies: `sarahalang/LLM-powered-OCR-correction` is a
**105-line DHd workshop demo** whose system prompt tells GPT it is *"comparing a supplied initial OCR
output with the original image"* — **`korr-ocr.py` computes `image_path` and never passes it to the
model**; `gpt-3.5-turbo` at temperature 0.7; `generate-diff.py` only prints git-diff command strings;
no measured number anywhere. **RE-GRADE of round-1 §6.7: not "a working diff workflow" — keep it only
as the instance of the hallucination warning.**

**`ocrd-keraslm-rate`, re-graded**: the line-granularity beam-search ceiling above `topcoherency` is
real (`beam_width 10`, `lm_weight 0.5` mixing LM against OCR confidence, per-page character and
segment perplexity — **the explicit LM-vs-OCR-confidence mixture litkb's rule-based reconciler has no
analogue for**). But **three facts change adoption**: `textequiv_level` defaults to **GLYPH, not
line**; it **DELETES each non-best alternative**; and its only shipped model is
`model_dta_full.h5` — 2×128 char LSTM, window 256, 1,769,684 bytes, trained on the **Deutsches
Textarchiv**, i.e. German. It is tiny enough to retrain on the T2000. Also: **beam search measured
7.8× slower and no better than greedy** in the closest comparable setting.

**`ocrd-cis-postcorrect` is NOT adoptable as-is**: `ocrd-tool.json` marks `profilerPath`,
`profilerConfig` **and** `model` all `required: true`; no English scientific profile ships, and
training one is its own project.

### 5.7 Agreement design for MATH (round 1, unchanged — no round-2 evidence arrived)

**THE CORE FINDING: litkb does not need ground truth to mark a formula verified.** **CDM**
(`opendatalab/UniMERNet` `cdm/@378adbcf`, CVPR 2025) renders two LaTeX strings with every token in a
unique colour, recovers per-token bboxes by exact colour match, Hungarian-matches them, RANSAC-rejects
spatially inconsistent pairs, and returns recall / precision / F1. `cdmtest.py:evaluation` takes
`[{img_id, gt, pred}]` from JSON and **nothing requires `gt` to be truth** — put decoder A in `gt` and
decoder B in `pred` and **CDM becomes a symmetric, structure-aware AGREEMENT score plus a green/red
visual diff PNG**. **C2's caveat is real: that measures AGREEMENT, not faithfulness to the scan**,
which is why rung 6 below is not optional. The whole verification layer is **CPU-only** (pdflatex +
ImageMagick + node/KaTeX), so under this project's free-CPU-runtime rule **verification is not the
constraint — decoding is.**

Decoders chosen for **independent lineage**: UniMERNet (Swin + mBART) primary; PP-FormulaNet (Paddle);
pix2tex plus **self-consistency at k=3 samples at its native temperature 0.25**. **Do NOT count
RapidLaTeXOCR as independent of pix2tex.**

**Ladder B — verify LaTeX** (stop at the first rung that decides): 1) **parse** `katex.__parse`
(~1 ms) → REJECT if unparseable; 2) **compile** `pdflatex -interaction=nonstopmode`, 15–30 s kill →
REJECT if no PDF; 3) **degeneracy** (n-gram repeat / Nougat `repeats`) → REJECT; 4) **exact agreement**
after KaTeX-AST normalisation → VERIFIED; 5) **CDM agreement** F1 ≥ τ → VERIFIED, band → HELD, low →
REJECT; 6) **image check vs the ACTUAL CROP** (render the winner, im2markup image edit distance against
the source crop) → the one rung that catches **both decoders agreeing on the same wrong reading**;
7) **VLM referee** on whatever is still HELD.

**Rung 6 is the one E3 would not let the plan drop** — rungs 4–5 compare decoders to each other, and
decoders trained on overlapping data (arXiv LaTeX is in nearly every training set) can agree and both
be wrong. **Only rung 6 compares to the page. Same structural point as CLAUDE.md §3.4c.**

**Proposed thresholds, explicitly E3's PROPOSAL and not measured**: exact normalised match or
CDM F1 == 1.0 → `verified`; F1 ≥ 0.95 with 2 of 3 decoders agreeing → `verified`; 0.80 ≤ F1 < 0.95 →
`held`, escalate to rung 6; F1 < 0.80 → `unverified`, keep the crop; **any rung 1–3 failure →
`unverified` immediately regardless of agreement.** Per §3.4c they must be calibrated and **the kill
criterion shown to fire on known-bad LaTeX** before any of it counts as a gate.

**The correct LaTeX comparator** (olmOCR `bench/katex/render.py`): render both with KaTeX via
Playwright (SQLite-cached by sha1), **strip the `<annotation>` element so the original LaTeX source
cannot leak into the comparison**, normalise away all whitespace including zero-width, test **MathML
containment**, then fall back to per-character span expansion with interpolated bboxes matched
geometrically (neighbour tolerance 5 units at 24 px font). **Diffing LaTeX source reports disagreement
on every stylistic difference and is useless as a gate.** **CAS equivalence is a TRAP as a
transcription gate**: Math-Verify normalises units away ("10 cm → 10"); SymPy's ANTLR parser silently
accepts `x -` as `x`. Store `equivalent` / `not_equivalent` / `unknown` **separately** from visual
fidelity.

**Free triage first** (marker `EquationProcessor._block_has_inline_math`): flag blocks by **math font
name** (`cmmi`/`cmsy`/`cmex`/`msam`/`msbm`/`stix` — "math font is a high-precision signal") or
math-unicode fraction > 0.02, then escalate the whole page above `inline_math_doc_ratio = 0.3`.
**E3's own measurement gap, stated plainly: it did not read the litkb corpus**, so whether the
math-bearing works are old scans (GPU rungs matter) or born-digital MDPI/ISPRS PDFs (free text-layer
triage does most of the work) is **still unknown after two rounds**.

### 5.8 Model selection — rank on the OLD-SCAN axes, not on Overall

Round 1 reported olmOCR-Bench Oldscans only. **The bench has a second old-document axis — Old-scans-MATH
— and it separates the systems differently.** Since litkb's hardest works are **scanned statistics
papers**, that is a separate and decisive criterion:

| System | Old scans | Old-scans-math | Overall |
|---|---:|---:|---:|
| Mistral API | 29.3 | 67.5 | 72.0 ±1.1 |
| Marker 1.10.1 | 33.5 | 66.8 | 76.1 ±1.1 |
| **MinerU 2.5.4** | 33.7 | **54.6** | 75.2 ±1.1 |
| DeepSeek-OCR | 33.3 | 73.6 | 75.7 ±1.0 |
| PaddleOCR-VL | 37.8 | 71.0 | 80.0 ±1.0 |
| dots.ocr | 40.9 | 64.2 | 79.1 ±1.0 |
| **Nanonets-OCR2-3B** | 40.9 | **46.1** | 69.5 ±1.1 |
| Infinity-Parser 7B | 47.9 | 83.8 | 82.5 |
| **olmOCR v0.4.0** | 47.7 | 82.3 | 82.4 ±1.1 |
| dots.mocr | 48.2 | 85.5 | — |
| **Chandra 0.1.0** | **50.4** | 80.3 | 83.1 ±0.9 |

**Two re-grades fall out:**

- **The Overall-axis rankings round 1 built on are INSIDE the error bars.** Chandra 83.1 ±0.9 vs
  olmOCR 82.4 ±1.1 **overlap** — round 1 called it "a ~3-point trade for licence cleanliness"; on
  Overall it is 0.7 and not measurable, and the real gap is on Old scans (2.7). Marker 76.1 ±1.1 /
  DeepSeek 75.7 ±1.0 / MinerU 75.2 ±1.1 likewise all overlap. **Rank on Old-scans and Old-scans-math
  only.**
- **MinerU — the CPU-friendly rung round 1 recommends — collapses to 54.6 on Old-scans-math**, and
  Nanonets-OCR2-3B to 46.1, while both score respectably overall. For a maths-heavy scanned corpus that
  is disqualifying for the quality tier, though MinerU remains the right *triage* tier because it fits
  the T2000.

**Round 1's boundary stands, reinforced: every system scores 29–50 on Old scans while scoring 75–99 on
every other axis. 95% with a searchable text layer is achievable; 95% with quote-grade accuracy on
1950s–90s scans is not.**

### 5.9 What runs on the 4 GB T2000 (and what does not)

**Runs locally on the T2000 or plain CPU**: Tesseract 5 (all PSM/OEM/binarization variants), unpaper,
kraken `nlbin`, **`ocrd-binarize-olena`'s nine algorithms** (C++ → WSL), RapidOCR-on-ONNX, **docTR**,
Windows.Media.Ocr, SmolLM-135M coherency, dinglehopper, Calamari voters, SymSpell / analiticcl / natas,
**MinerU tier `basic` + ONNX (~0.8 GB models, 2 GB RAM)**, marker `--mode fast --disable_ocr`
(23.7 pg/s), GROBID, Docling, the whole CDM math-verification layer (pdflatex + ImageMagick + node),
**`ocrd-keraslm-rate`'s 1.77 MB model** (small enough to RETRAIN on English), **eynollah** (ONNX,
GPU optional, → WSL).

**Colab-only**: olmOCR (~20 GB VRAM), Chandra/Surya, Nougat, PaddleOCR-VL, UniMERNet, texify.

**The hard fact, unchanged after two rounds: no measured 4 GB-GPU scientific-OCR configuration exists
anywhere either round could find.** The lowest verified fits are **8 GB** (DeepSeek-OCR with
`max_num_seqs=1`; MonkeyOCR's README claims "even the 4060 with 8GB … quantized 3B and 1.2B") and
12 GB; 24 GB olmOCR still OOMs on big jobs (allenai/olmocr issue #50). **The T2000 is a classical-OCR
and orchestration machine; every VLM rung is a Colab rung** — which fits the project's existing
free-parallel-CPU-runtime pattern.

### 5.10 Extraction leads REMOVED by round 2

- **`allenai/dolma` has NO PDF pipeline.** At HEAD (`669f534`, 794 tree entries) the package dirs are
  `cli / core / data / taggers / tokenizer / warc`; the only `pdf` paths are four `docs/assets/*.pdf`
  and `configs/dolma2-resharding/s2pdf*` — **dataset-mixing YAML for a corpus merely NAMED `s2pdf`**.
  The string `olmocr` appears nowhere in the tree. **Round-1 §6.7's "obvious next read" is not there.**
- **`internetarchive/pdftrio` does not exist on GitHub.** `repos/internetarchive/pdftrio/commits` → 404;
  `search/repositories?q=pdftrio` → zero items. What *is* public is only sandcrawler's deployment note:
  two TF-Serving models (`bert_models` + `pdf_image_classifier_model`) behind 16 uwsgi processes,
  `PDFTRIO_MODELS_DATE=2020-01-01`, throughput 31 → 69.7 docs/sec after moving TEMP to tmpfs, **and the
  bottleneck is `pdftotext`, not the classifier** (*"Worker CPU basically blocked on pdftotext"*).
  **No precision/recall figure is published anywhere reachable.**
- **`open-parse` is a RAG chunker**, not an extractor (its own comparison section positions it against
  text splitters, not GROBID/Docling; tables are delegated to unitable).
- **`ParsCit` at HEAD is the 2010-era Perl/CRF++ toolkit** — LGPL `COPYING.LESSER`, no `README.md`
  (404), vendored `bibutils_4.10` binaries.
- **`zerox` is a hosted-VLM client with no local model.** Its one transferable idea is `maintainFormat`
  — feed page N−1's markdown into page N.

---

## 6. A projected coverage account for the 95 percent target

**Read the grades before the numbers.** `MEASURED` = someone ran it and reported the result, with the
measuring party named. `ESTIMATED` = reasoning from a verified mechanism plus a known corpus property.
`UNDETERMINED` = the input does not exist yet and no honest number can be given. **Per CLAUDE.md §3.5,
an effect smaller than the measurement noise is UNDETERMINED, not "no difference" — and per §3.4c none
of this counts until an agent that did not write it re-runs the rungs on the real rows.**

**A denominator problem, stated first.** Neither round established **how many studies the tracker
holds**. The ledger census counts *route attempts by status*, and round 1's own funnel note says
"~100 drop-offs recorded, under half linked to a work, about half of those with a file". **A "95% of
the tracker's studies" target cannot be evaluated until that denominator is written down**, and A0 /
C16 / C17 / C22 will legitimately shrink it by removing works that can never have a PDF (abstracts,
posters, corrections, datasets-not-articles, news items). **That is the first measurement round 3
should take, and it costs one query.**

### 6.1 Bucket by bucket

#### `no-oa-copy` — 35 rows. **The only bucket with a MEASURED ceiling.**

| Sub-population | n | Rung | Conversion | Grade |
|---|---:|---|---|---|
| Elsevier **bronze**, Unpaywall answers with a **landing page** | **4** | C11 (PII → `/pdfft`, or `pdfDownload.urlMetadata` → signed `sciencedirectassets` asset), then C1-RG | **0–4.** The identification is MEASURED (orchestrator); the landing-page→bytes step is VERIFIED as a mechanism in three independent codebases but **not measured on these four**, and Elsevier sits in `BROWSER_ONLY_PREFIXES` with a documented Cloudflare "Are you a robot?" on `/pdfft` | MEASURED (identification) / ESTIMATED (conversion) |
| IEEE / Springer / World Scientific papers with a **free arXiv preprint** | **4** | B1 (S2 `openAccessPdf`) or B10 (arXiv, host rewritten to `export.arxiv.org`) | **4.** arXiv is the most reliable host in the entire base-rate table (17,370/17,817 success at IA). **Record `articleVersion` (guard 23): a preprint is not the version of record and its pagination differs** | MEASURED |
| a dead **author copy in Wayback** | **1** | E1 with the `id_` / `if_` raw-bytes modifier | **1** | MEASURED |
| **paywalled residue** — Springer / Wiley / OUP / IOP / Cambridge, every "pdf" link a paywall page or a token-gated TDM endpoint | **~26** | nothing in Stages A–F | **0 by legitimate automated means.** See §6.2 | MEASURED |
| | **35** | | **free ceiling ≈ 9 (26%)** | MEASURED |

**This is the single most important number in the document, and it is a correction to round 1.** Round
1 implied most of this bucket was instrument error. It is not: **74% of it is genuinely paywalled.**

#### `bad-file` — 26 rows (19 `open_access` + 7 `annas`). **UNDETERMINED, and the cheapest measurement in the survey.**

Nobody in either round read these 26 rows. Round-1 §5.2 flagged it (*"That is a one-hour measurement
and it should happen before this ladder is built"*) and it is still true. What round 2 changes is the
number of *distinct causes* a reader should expect to find, and the fact that **several of them are
free to fix**:

| Cause to look for | Rung that converts it | Cost |
|---|---|---|
| the bytes are an HTML **landing page** (the shape §0.2 measured for all 4 Unpaywall hits) | C2 + C9 + C10 | 0 extra requests — the page is already fetched |
| a valid PDF whose body starts with a **BOM or newline** | C14 header repair | free |
| a good PDF **inside gzip or tar.gz** | C18 | **no network at all** |
| a **stub under 5,000 bytes** that passed litkb's 128-byte floor | C1-RG | free |
| a **publisher preview / purchase interstitial that IS a valid PDF** | C15 (Tj-string scan of the first 512 KiB), C19 (URL shape), guard 4's preview detector | free |
| an **Elsevier first-page-only TDM response at HTTP 200** | H2-RG (`X-ELS-Status`) + C16 | free |
| a **whole proceedings volume** bound as one article | C17 | free |
| a **cited document, not this article** | guard 4 (`DOI_PAGES=3`) | free |
| broken fonts / ToUnicode damage | §5.2's CMap repair ladder | CPU only |
| a **truncated download** | qpdf `--check` exit 3, guard 4's `TRUNCATION_RATIO` | free |

**E2's warning still applies: if these rows are truncated downloads rather than broken fonts, the whole
PUA/garble layer does nothing for them.** The measurement is: for each of the 26, read
`acquisition_attempt.detail`, the stored bytes' first 1 KB, and the byte length. **ESTIMATED
conversion: high but unquantified** — every cause above except truncation is free to fix, and the one
structural fact that *is* measured (Unpaywall returns landing pages) points at the largest and cheapest
of them.

#### `blocked` — 39 rows (25 Sci-Hub + 14 `open_access`). **Mechanism VERIFIED, yield UNDETERMINED.**

- **The 25 Sci-Hub rows are one host decision, not 25 work decisions.** IA's per-host determinism
  measurement (§3.2) is the general form of round-1 rule R4. The three separable causes A5 found — no
  User-Agent; *resolving* a DOI and *serving* a file being different jobs, so a portable
  `/storage/<bucket>/<shard>/<hash>/<name>.pdf` path from a non-serving mirror is discarded; and
  nothing distinguishing the Altcha challenge from a genuine miss — are all VERIFIED in
  `getscipapers@f033717`. **The cheapest new rung in the class is G1a (`sci.bban.top/pdf/<lowercased
  doi>.pdf`, no bot check, unambiguous 404).** **Ceiling caveat: the Sci-Hub corpus froze around 2021**,
  so for post-2021 IEEE TGRS and Elsevier remote-sensing work this bucket converts to **G4 (deferred
  human fulfilment), which is Kam's ruling, not a rung.**
- **The 14 `open_access` blocked rows** should first be *typed*, not retried: C13's 4 KB Range probe
  splits them into `identity_required` / `challenge_or_bot_check` / `not_found` / `html_or_reader` for
  4 KB each. **Any MDPI row among them is a MEASURED conversion via A6** — that is the one place in
  this bucket where a number exists.

#### `not-in-archive` — 33 rows (all Anna's). **Probably mostly false negatives; mechanism VERIFIED.**

A5's finding is unchanged and round 2 adds nothing against it: Anna's challenge-gates `/search`,
`/md5/`, `/doi/`, `/scidb/` and `/slow_download/` behind DDoS-Guard, an interstitial contains no
`a[href^='/md5/']`, and the standard lookup therefore returns "no paper found for DOI" — **a miss, when
what happened was a block**. The fix is three rungs and one guard: **G0d's `<title> == "DDoS-Guard"`
check FIRST** (never search the body for "ddos-guard" — a solved record page mentions it in its own
scripts), **G0a** (LibGen `json.php?object=e&doi=` → md5, with the nginx-UA trap guard), and **G2a**
(Anna's quota-free `aarecord_elasticsearch` → `ipfs_urls`). **Whatever share of the 33 are books is
unreachable until A2 routes them to the ISBN namespace** — `scidb`-by-DOI cannot address a book.

#### `manual-step` — 45 rows (the `browser` route). **Binary on one unanswered question.**

H10 (drive the user's own already-logged-in Edge/Chrome profile via `launch_persistent_context`) and
H11 (log in once headed, reuse headless via `storage_state`) are **the only rungs in either round that
convert this bucket**, and H11 is also the only rung that survives
`doi.org → linkinghub → sciencedirect`, whose last hop is a JS redirect. **If Kam has institutional
access, this is the single largest converter in the whole survey; if not, the catch is 0.** No
credentials are handled, scripted or stored in either design. **See §7 #9 — this input has never been
established by any round, and it is a one-sentence answer.**

#### The grey / agency layer — no ledger bucket, and round-1 A7 says it decides the last ten points

Round 1 had **no rung at all** here. Round 2 supplies three **measured** ones and one class:
**A8** (USFS Treesearch, 5,000+ enumerable records, `citation_pdf_url` on every page, HEAD 200
`application/pdf`), **D12** (ArcGIS Online, 99 canopy PDFs, the first result literally a city tree-canopy
assessment, HEAD 200 `application/pdf` 23.9 MB), **D2** (USGS, 1,198 records for `q=canopy`, round 1),
and **D13's state-library DSpace class** (one probed 200 `text/xml`; **Washington State Library
unprobed**). Against these sits §3.1's warning: **repository harvesting is a one-in-three business at
IA scale — budget ~30% gross yield, not ~80%.**

### 6.2 The paywalled remainder — what actually closes it

About **26 works** in `no-oa-copy` alone, plus an unknown share of `blocked`. Four closers, in
descending order of legitimacy:

1. **Institutional access (H9 / H10 / H11 / H15).** The only *legitimate automated* route to a
   paywalled article. Conditional on an input nobody has asked Kam for. If it exists, it likely closes
   most of the 26 **and** the 45 `manual-step` rows. **UNDETERMINED.**
2. **Publisher TDM keys (H1 / H2 / H3 / H4-RG).** Free keys exist for Springer and Elsevier. **They buy
   OA content only**: Elsevier's `X-ELS-Insttoken` is what unlocks non-OA and we have none, an
   unentitled key returns **a first-page stub at HTTP 200**, and Aut_Sci_Download's own docstring says
   the IEEE API returns a `pdf_url` but not bytes without institutional access. **ESTIMATED yield on
   the paywalled residue: near zero.**
3. **The shadow tier (Stage G), under Kam's existing authorisation.** Mechanically the strongest route
   for **pre-2021** paywalled journal articles, and the pairing of G0a (LibGen DOI→md5) with G2a
   (Anna's quota-free IPFS record) is the strongest single addition. **Two hard ceilings**: the corpus
   froze around 2021, and **no shadow rung will ever deliver the USFS / USGS / NOAA / King County /
   Seattle reports or the theses.** Policy shape: guard 21's pre-fetch `PolicyDecision` object and
   H17's compile-time tier, so "authorised" is an auditable switch rather than a code path.
4. **Metadata-grade, honestly recorded.** For whatever remains: **B26 (Asta `snippet_search`) supplies a
   quotable passage without a file**, and **C24 (`cached_text`) supplies HTML-as-text for agency
   reports that will never exist as PDFs**. Both are `kind != pdf` and **must not enter a
   95%-with-PDF numerator** (§4.5) — but for litkb's actual purpose, which is `record_use` with a
   verifiable quote, they are a *correct* terminal state rather than a miss. **If Kam's 95% means "has
   a searchable, quotable source", these count; if it means "has a PDF", they do not. The plan must
   say which** — the same distinction E2 forces on the OCR side.

### 6.3 The honest bottom line

- **MEASURED, external**: a mature ladder on OA URLs lands **~80%** first pass; repository harvesting
  lands **~35%**; a targeted crawl converts **~77%** of "never captured".
- **MEASURED, self-reported, same shape as this corpus**: finnschwall's 582-paper review reached
  **~86%**, and **65 of its 82 misses were closed-access with no free copy anywhere**.
- **MEASURED, on litkb's own rows**: the OA miss bucket's free ceiling is **9 of 35**.
- **Therefore**: **~86% by legitimate automated means is the demonstrated number for a corpus of this
  shape.** Getting from there to **95%** requires **at least one of**: institutional access (§7 #9),
  the shadow tier for the pre-2021 paywalled slice, the grey-literature layer that round 2 has just
  made measurable (A8 / D12 / D13 / D2), or a definition of "has the study" that admits
  `jats | html-doc | cached_text | snippet`. **No combination of more OA indexes reaches it** — round
  2's 24-tool union found exactly one new source worth adding (NASA ADS), which is itself strong
  evidence that Stage B is complete.

---

## 7. Disagreements and what nobody verified, merged

### 7.1 Live disagreements

| # | Question | Side A | Side B | State after round 2 |
|---|---|---|---|---|
| 1 | **Is OpenAlex a location source or only a resolver?** | A1: make it PRIMARY — oadoi's own 410 handler calls it "the successor to Unpaywall, from the same team… the same data" | A7: **measured 0 net-new full text** on 69 previously-unretrievable DOIs | **Unchanged.** Keep it, rank it as a resolver, do not expect files from it. Round 2 adds only that **OpenAlex batches and Unpaywall does not** (B2-RG) |
| 2 | **Does TLS impersonation defeat the walls?** | A3 + findpapers + ref-downloader in code | A7 + C1: finnschwall TESTED it and reports the discriminator is **JavaScript execution**, not TLS/UA/IP | **RESOLVED AGAINST, for the two hosts that matter, and it is now a FOUR-sided question.** (i) MDPI: a production pipeline adopted cloudscraper, then built a browser step *because both cloudscraper and curl_cffi were defeated by the Akamai interstitial*. (ii) Springer, dated 2026-09-05: a "Client Challenge" to any UA, with cookies, and with a Chrome TLS fingerprint. (iii) Zotero's maintainers: a `--user-agent` override **drops `Sec-CH-UA`, a worse signal than the one it hides**; headless Chrome is "refused outright". (iv) **Which real browser is now the open question** (§7 #10). **And the dispute matters much less than it did: A6's MDPI CDN route is MEASURED and sidesteps the wall for the corpus's largest slice.** Round 1's characterisation also needs correcting: findpapers uses `impersonate="chrome"` (unpinned) on the scraping path only |
| 3 | **Does Sci-Hub need back-off or immediate retries?** | exponential back-off | A5, from `getscipapers`: the Altcha challenge fires **intermittently rather than by rate**, so `SCI_HUB_GATE_RETRIES = 5` **immediate** re-asks | **Unchanged**: host-gate Sci-Hub globally, retry the challenge immediately *within* one attempt. Round 2 adds the general complement — **AIMD, decaying linearly on every 2xx** (guard 2) |
| 4 | **Is Europe PMC worth a rung?** | A1: **MEASURED ZERO**, 0/7 controls | A7: 12 of 109 recoverable as a *late* rung; E4/A6: 3–6% | **Unchanged — keep it at the bottom, budget no yield.** Round 2 makes it cheaper to get right (three selection fields, B12-RG) and adds four byte paths (B20–B22, B25) |
| 5 | **Is the `filetype:pdf` web-search rung real?** | A4: `elm`'s 14-backend fan-out is VERIFIED | A3: no maintained repo implements it *for papers*; "I claim no yield" | **Partly settled**: `greylitsearcher` is a real implementation **for grey literature**, with a reproducible query report. The *paper* case is still unevidenced. Gate on an allowlist, require 0.85 identity |
| 6 | **Marker vs MinerU** | olmOCR-bench: Marker above MinerU-pipeline | OmniDocBench v1.5: MinerU **86.47** above Marker **78.44** | **SHARPENED and partly dissolved**: on Overall the two are **inside the error bars** (76.1 ±1.1 vs 75.2 ±1.1), so the disagreement was partly noise. **The axis that separates them is Old-scans-math, where MinerU collapses to 54.6** (§5.8) |
| 7 | **Is `getscipapers`' DOI→md5 story coherent?** | `libgen.py:find_md5_by_doi` exists to be the oracle | `anna.py` says "there is no working external oracle" | **STILL UNRESOLVED.** Nobody dated the two files against each other in round 2 either. **Verify before building G0a** |
| 8 | **Is a 5% CER disagreement trigger a real rule?** | a plausible practitioner default | C2: no practitioner-validated rule exists | **Worse than unresolved — the precedent collapsed.** LV-ROVER's 1.605→1.317 is five *Tesseract configs*, and on an unseen corpus the same arbitration gives Δ CER 0.00105, p = 0.6555, **not significant**. The only trustworthy number is +5.11% relative from a purpose-trained corrector **that is negative without its vote**. Treat 5% as an explicitly uncalibrated litkb experiment; trigger review on numbers/signs/formulas regardless |
| **9** | **NEW, and the highest-leverage unanswered question in the survey: does Kam have institutional access?** | H9/H10/H11/H15 exist, are implemented in four independent codebases, handle no credentials, and would convert most of the ~26 paywalled works **and** the 45 `manual-step` rows | If not, every one of those rungs has catch **0**, and the paywalled residue closes only via the shadow tier, G4, or metadata-grade | **UNASKED after two rounds. It is one sentence to Kam and it changes the shape of the whole plan.** Round 1 states flatly "There is no institutional proxy" — which is a statement about litkb's code, not about Kam |
| **10** | **NEW: WHICH real browser?** | mosaic `auth.py@64b9919`: headless **Playwright Firefox** passes Cloudflare Bot Management where headless Chromium is blocked, and `cf_clearance` is **fingerprint-bound** so login and reuse must use the same engine | PyPaperBot uses `undetected_chromedriver`; Zotero's maintainers drive **real** Chrome with a persisted profile and say Playwright's bundled Chromium "can't get through at all, headed or not" | **Two code-carried positions in direct conflict, neither measured. The cheapest open question in the survey** — and it gates every browser rung, including the one that might convert the 45 `manual-step` rows |
| **11** | **NEW: how valuable is `no-pdf-link`?** | round 1: "the failure most worth fixing" — a fixable parser backlog | IA's own triage: four causes on its five largest domains, **only one a parser bug** | **Round 2 wins on evidence.** Keep the status, drop the valuation (§3.2) |
| **12** | **NEW: is metha a thesis source?** | round 1: 244,347 endpoints, 34,335 on `.edu`/`.gov` | measured: **~6,200 repository platforms, 1,109 of them `.edu`, 45 `.gov`**; 75.6% of the file is OJS journals | **Round 2 wins — it is measured.** Strong OJS-journal route, weak thesis route (D13-RG) |
| **13** | **NEW: the Referer** | round-1 rung 18 / A3: `Referer: https://www.google.com/`, as Zyte's own profile does | **two independent Zotero production paths** use the landing page or its origin, never Google | **Both, with Zotero's as the default** — they fix different failures (spoof vs honest hotlink referer). Guard 24 |

### 7.2 What round 2 could NOT verify

**The same largest gap as round 1, unchanged: no rung has been run against litkb's real rows.**
Every yield number in every round-2 report except A6's, B4-RG's, A7's, A8's and D12's is reasoning from
mechanism. **No round-2 crawler opened litkb's database.** Per §3.4c these are claims about what
*would* happen.

**Endpoints that could not be reached or confirmed in round 2:**

- **`api.fatcat.wiki` — now definitively dead server-side** (E2-RG). Round 1's leading hypothesis for
  the old-paper tail cannot be specified today.
- **NOAA IR / CDC Stacks / BTS ROSA-P** — Akamai 403 on the bare host root from this egress, UA
  independent. **Might work from another egress; untested.**
- **Washington State Library OAI (`www.sos.wa.gov/library/digcolls.aspx/oai/oai.php`) — NOT probed**,
  and it is the most regionally relevant grey-literature endpoint either round found.
- **CORE v3's field list** — `api.core.ac.uk/swagger/v3.json` unreachable in both rounds; `/v3/` 404s;
  `/v3/outputs/1` 429s unauthenticated. Round 3 needs `CORE_API_KEY` set.
- **NASA ADS `link_gateway/{bibcode}/PUB_PDF`** — read in mosaic's code, **never probed**; the sibling
  forms `EPRINT_PDF` and `ADS_PDF` appear in ADS documentation generally but **not** in that code.
- **Ai2 Asta `snippet_search`** — named in a skill document, **never called, never schema-checked**.
- **`MemGator/archives.json`** — still 404; which archives Memento federates is still unenumerated.
- **The MDPI CDN's behaviour at scale** — A6 is measured on three DOIs (two journals) plus one negative
  control, and reported at 16/17 by a second party. **Not a rate.**

**Bodies of code named but not read in round 2:**

- **`scansci-pdf`'s internals** — `try_unpaywall`, `try_openalex_oa`, `try_crossref`, `is_pdf_file`,
  **`is_suspicious_pdf`**, **`belongs_to_current_article`**, **`sources/scoring.py`**, and every proxy
  transport behind H9. **The single largest unread body**, and it sits under round-1 guards 4 and 6 as
  well as H9 and guard 4's preview detector. It is on PyPI, pinned by exact version in CatMaster.
- `paperhub-cli`'s per-provider capability *values*; findpapers' `web_scraping.py` /
  `download_runner.py` call sites; olivettigroup's `link[]` filter implementation; all eight SciDownl
  files; PyPaperBot's `Downloader.py` / `HTMLparsers.py` / `NetInfo.py`.
- `Knowledge-Engineering-with-Big-Data/PaperDownloader` (a Scrapy crawler against Web of Science,
  judged out of scope without confirming the judgement from code).
- **Recorded as contributing NO rung, so round 3 need not revisit**: `NLeSC/litstudy` (bibliometrics,
  no acquisition path), `sadraehdi/article-finder`, `hossam1522/VerifiSci` (both metadata-first;
  VerifiSci fetches a URL with **no `%PDF-` check and no identity check**), `croumegous/doi2pdf` and
  `byigitt/doi2pdf` (both OpenAlex→`oa_url`→Sci-Hub, both feeding landing pages straight to the
  downloader — the same `bad-file` bug), `ZimoLiao/scholaraio` (**mis-filed in round-1 §6.3 as a
  landing-page implementation; it contains none** — its contribution is an extraction parser chain plus
  C14's header repair).

**Numbers that are author-reported or vendor-run and must not be load-bearing** (round 1's list, with
round 2's additions): Chandra's Old-scans 50.4, Infinity-Parser 47.9, PaddleOCR-VL 37.8 and MinerU 33.7
are **author-reported by olmOCR-Bench's own statement**, not reproduced; the 2019 CORE-vs-Unpaywall
study was **run by the CORE team**, in 2019, on a random Crossref sample; finnschwall's ~86% is
self-reported; UniMERNet's accuracy claims are **images in a README**; SymSpell's "1 million times
faster" has **no benchmark table**; the self-ensembling "SOTA in 5 of 9 languages" is a README claim;
and **A6's 16/17 MDPI figure is a second party's report, not a measurement in this survey** — the
survey's own MDPI evidence is three successful DOIs and one clean negative control.

**Two process notes for round 3, both from the crawlers themselves:**

- **`blacklist-round1.txt` contains five files that DO NOT EXIST** at `zotero/translators@c8300377`:
  `Zenodo.js`, `EPrints.js`, `DSpace.js`, `bepress Digital Commons.js`, `HAL Archives Ouvertes.js`.
  All five 404 from `cdn.jsdelivr.net` at that sha and none appears among the tarball's 748 root `.js`
  files (two independent listings agree), while `Embedded Metadata.js` and `Institute of Physics.js`
  return 200 from the same probe — **so it is not a fetch-method artefact.** No round-1 report *body*
  cites them, so no published claim is wrong, but **round 1 had no Zotero evidence for Zenodo, EPrints,
  DSpace, bepress or HAL** (see B14-RG, D6-RG).
- **The scratchpad directory is SHARED between concurrent sibling crawlers, and one crawler's URL log
  was overwritten mid-run by another.** Round-3 crawlers must use uniquely-named scratch files.
- **Topic and awesome-list discovery reaches a nearly disjoint sampling frame from code search**: 842
  repositories outside the 1,796-line round-1 blacklist against only 40 inside it. **So any "how many
  projects do X" count taken from round 1 alone is a floor, not an estimate** — and the same channel
  produced the strongest extraction measurement of round 2 (`post_ocr_correction`) plus `eynollah` and
  `natas`, none of which thirteen code-search crawlers had surfaced.

**Legal / ToS questions the crawlers recorded and explicitly refused to answer — these are Kam's**:
JSTOR's `acceptTC=true`; Atypon's `?download=true`; Elsevier's insttoken; every "impersonate" library;
**crawler-identity spoofing (H14) — deliberate misrepresentation of the client, which belongs in the
policy bucket with the shadow rungs**; Google Scholar scraping; ResearchGate; Anna's member `scidb`
perk being restricted to "normal browser use"; and G4's account risk and public posting.

---

## 8. Verified vs asserted

**What is VERIFIED and safe to build on is the MECHANISM.** Every rung in §1 carries a repo, a file, a
symbol and a sha, and the crawlers read those files at those commits; where round 2 could, it added an
*independent-implementation count*, and the five rungs with five or six independent implementations —
`citation_pdf_url` scraping, `oa_locations[]` traversal, cascade-with-typing, challenge detection as a
distinct outcome, and an anti-block engine — are settled consensus **and are all things litkb does not
do**. **What is MEASURED is a much shorter list, and it is the strongest content in this document**:
litkb's Unpaywall resolver answering for 4 of its own 35 misses, all Elsevier bronze, all landing pages
(orchestrator); S2's `openAccessPdf` yielding 4 arXiv preprints and Wayback one author copy from the
same bucket (orchestrator); the MDPI CDN returning 200 / `application/pdf` / 2,366,188 bytes for the
exact DOI that 403s on `www.mdpi.com`, with a clean 404 negative control (R2-waterfalls); EarthArXiv's
OAI returning 50/50 direct PDF URLs and 32/50 published DOIs over 7,670 records, and USFS Treesearch
enumerating 5,000 records per sitemap page with `citation_pdf_url` on each and a 200 `application/pdf`
HEAD, and ArcGIS Online returning 99 canopy PDFs whose first result is a city canopy assessment
(R2-calibration); Crossref's `has-full-text:true` returning 43,455 *Remote Sensing* works while
`full-text-type` is rejected 400 on that route (R2-waterfalls); the Zotero corpus census of
748 / 366 / 147 / 32 (R2-zotero); and the Internet Archive's own base rates over 27.6M and 58.2M
ingests (R2-calibration). The **negative** measurements are equally solid and equally useful: fatcat
refusing connection at an IA address while archive.org answers from the same egress, ArcGIS Hub holding
zero documents, OpenDOAR/ROAR Cloudflare-blocked, DTIC's REST closed and its search API serving a PNG
decoy, NOAA IR / CDC / BTS behind one Akamai edge, `dolma` having no PDF pipeline, `pdftrio` not
existing, and LV-ROVER's own arbitration showing **p = 0.6555** on a corpus it was not tuned for.

**What is ASSERTED and must not be load-bearing is every YIELD number.** Not one rung in either round
was run against litkb's real 35 `no-oa-copy` / 33 `not-in-archive` / 26 `bad-file` / 39 `blocked` /
45 `manual-step` rows; no crawler in either round opened litkb's database; the tracker's denominator has
never been written down; the 26 `bad-file` rows have still not been read, which is a one-hour
measurement round 1 already asked for; and the two Codex briefs that were meant to cover forum and
issue evidence for both halves of this survey **did not run at all**. Several endpoint patterns remain
inferred rather than exercised (NASA ADS's gateway, Asta's snippet API, CORE v3's schema, MemGator's
federation list, the Washington State Library OAI), one measured win is a three-DOI sample rather than a
rate, and most licences are still read from package metadata rather than LICENSE files.
**Per CLAUDE.md §3.4c this whole document remains a set of claims about what would happen: every rung
must be prototyped against the real ledger by an agent that did not write it, and every gate — the
five-verdict acceptance, `belongs_to_current_article`, the challenge detectors, the CDM threshold, the
`X-ELS-Status` check — must be shown to FIRE on a known-bad input before it counts as a gate.**
