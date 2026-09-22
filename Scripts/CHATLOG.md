# Edmonds Pipeline — Chat / Progress Log

Running log of work sessions. Newest first. Open this → read STATE + top entries →
caught up. **This STATE block + the active plan ARE the handoff** (per-session
`HANDOFF_*.md` retired 2026-07-06 → `_archive/`). Doc map: `../README.md`.

════════════════ HOW TO LOG  (read before appending) ════════════════

STYLE — caveman, "full" level  (github.com/JuliusBrussee/caveman)
- Drop: articles (a/an/the), filler (just/really/basically/simply/actually),
  pleasantries (sure/happy to), hedging. Fragments OK. Short synonyms
  (big not extensive; fix not "implement a solution for").
- Pattern: "[thing] [action] [reason]. [next]."
- KEEP EXACT (never compress): code, file names, identifiers, numbers, flags,
  quoted errors, version tags. Well-known acronyms OK (DB/API/CRS); never coin
  abbreviations the reader can't decode.
- SUSPEND caveman (write plainly) for: irreversible-action / security warnings,
  and multi-step sequences where dropped conjunctions risk a misread. (skill's
  own auto-clarity rule). This HOW-TO block is instructional → kept plain.

SCALE — one block per SESSION or per landed MILESTONE (decision made / feature
landed / direction changed). NOT per message. Append when a unit of work closes.

ENTRY SCHEMA — fixed fields, omit empty ones:
    ## YYYY-MM-DD  <slug>
    goal:    why this session existed
    did:     what landed — DELTAS only
    decided: key decisions + 1-word why
    killed:  dead-ends / reversals — 1 line each, so we don't retry them
    files:   paths / version tags touched — reference, don't restate
    next:    open threads

SPACE RULES — keep always-loaded context low for continuous logging:
  1. Reference, don't repeat — link version/handoff/file; don't re-explain (see v025).
  2. Deltas not full-state — log what CHANGED; current full state lives in STATE.
  3. Outcomes not tool-noise — no command-by-command narration.
  4. Rolling compaction — keep newest ~6 entries full; older → 1 line each under
     "ARCHIVE (1-liners)". Compact when full entries exceed ~6.
  5. STATE edited IN PLACE (not appended) — always current, small.


════════════════ STATE ════════════════

STATE lives in `WORKPLAN.md` (decision 2026-08-30; this block was 1,489 lines of
transcript before rotation). Read order: `CLAUDE.md` → `WORKPLAN.md` → `STATUS.md`.

════════════════ LOG  (newest first — append new entries directly below this line) ════════════════

## 2026-09-22  litkb SCI-HUB: parking reversed -> diagnosed -> workaround ladder measured; Elsevier key measured
goal:    Kam: "I do want to attempt a work around for scihub. Scihub is a massive loss if we table it."; keys.
found:   Sci-Hub (wf_88f4554c-1ee, D1 own-route + D2 fronts, 30 min, read-only): ledger 26 attempts / 22 works,
         25 blocked 1 bad-file 0 files; 19/22 DOIs post-date the 2022-02-12 freeze, 2 eligible confirmed absent ->
         zero = SAMPLING + MISLABELLING (miss page booked blocked; blocked not in DEAD_STATUSES -> retried until
         sci-hub.ru ALTCHA rate gate). From here: .se DNS dead, .st/.box DDoS-Guard 403, .ren/.wf Cloudflare at
         HTTP 200 (is_challenge fires only 403/503 -> booked no-pdf-link), only .ru serves. Corpus OPEN: bban
         73/104 (D2) + 12/20 random (D1); LibGen.li json.php->ads.php->get.php 75/104; union 77/104; bban
         case-SENSITIVE (as-given then suffix upper-cased, +7). Anna's /scidb dead today (.org/.se NXDOMAIN,
         .li parked, .gl DDoS-Guard); Nexus/STC no HTTP front; library.lol seized; no onion address anywhere.
         Orchestrator re-run qc/instruments/litkb_acq_probe_bban.py: 73/104 (70%) served, 7 via upper suffix,
         %PDF magic 8/8 sampled -> phase4/qc/litkb_acq_probe_bban.csv.
did:     litkb-scihub-parked REVERSED (Kam) + diagnosis appended; plan S4.6 Stage G = measured ladder (freeze gate,
         bban, LibGen.li, mirrors last w/ 3 code fixes, dead fronts named), freeze date 2022-02-12 (was "around
         2021"), (b) += post_freeze_sent=0, shadow_miss_booked_blocked=0, bban_served reported; real negative
         10.1016/j.rse.2024.114101. Elsevier: key placed, re-keyed once, both times Scopus 200 / ScienceDirect
         refused -> H2 gated on a ScienceDirect 200; open action Elsevier API support. No Springer key (Kam).
killed:  Springer key (Kam); institutional access; a captcha/ALTCHA solver (route docstring forbids; rate gate
         not corpus signal).
files:   Scripts/decisions.yaml, Scripts/LITKB_WORKPLAN.md, qc/instruments/litkb_acq_probe_bban.py,
         phase4/qc/litkb_acq_probe_bban.csv, qc/instruments/litkb_acq_probe_elsevier_key.py (+csv);
         D:/tools/claude-config/jobs/litkb-scihub/ (D1, D2, probe scripts, raw JSON).
next:    S4.6 builds the ladder (fixtures from the D1/D2 JSON); Kam: Elsevier API support; nightly dump task;
         launch S4 run 3. Owed: Codex reads r2/r3/r4 + plan.

## 2026-09-22  litkb RULINGS: Kam ruled the eleven open ids in one message -> plan re-bound under them
goal:    close the "Kam-side, open" list from survey rounds 1-4 (options + trade-offs conversation, then Kam's rulings).
decided: (Kam, verbatim in each decisions.yaml `decision:`) litkb-coverage-definition B: pdf + jats + html-doc count, cached
         text/snippets reported never counted; litkb-institutional-access B: NONE, H10/H11 not built, manual-step rows -> shadow
         tier / human queue / metadata-grade; litkb-shadow-hosts a,b,c,d: LibGen DOI lookup + mirrors, sci.bban.top, Nexus/STC
         delivery, Tor transport, browser session vs Anna's — all granted behind policy lines, offline dumps = data;
         litkb-tdm-keys: "Keys for both", amended same evening to ELSEVIER ONLY (key placed in
         secrets/; "We wont be getting a springer api key"); litkb-s47-colab-queue: "as much T4 time as you
         need, its cheap"; "the rest of the reccomendations" accepted: scihub-parked PARK, blocked-works-grade METADATA-GRADE +
         queue on demand, e23-residue-copies RETIRE 53/369 unless load-bearing, crc-book RETIRE (ILL if needed),
         tracker-corrections CORRECTED COLUMN + crossed DOIs fixed in place, from-file-version-state PROPOSAL PATH batched;
         reference stage runs in S4 detached over every file w/ blocks; classical OCR on T2000 first, VLM OCR in S4.7; S4 kit
         work key not a violation; S5 topic = label transfer across years under seasonal difference unless Kam renames.
did:     decisions.yaml 11 entries open -> decided 2026-09-22 (zero litkb-… open). Plan 15 edits: Where-we-are Kam list ->
         rulings list; S4 Kam line ruled; S4.5 Kam line -> operator-bind gate built in item 1; S4.6 Stage G builds LibGen/
         sci.bban.top/Nexus-STC/Anna's-browser/Tor rungs (Sci-Hub parked), Stage H drops H10/H11, both TDM keys granted,
         coverage instrument GATED coverage_fulltext>=0.95 under definition (b) w/ coverage_cached_or_snippet reported; S4.7
         Colab queue approved T4; after-S5 promotion row -> operator-bind gate is S4.5's; S5 names the topic + the pre-run
         tracker edits. Launch kit _derived/s4/s4-prompt.txt line 4 -> the ruled list. Gates: plan 0/0, docs+decisions 29 pass,
         edges 21 pass. Landed main 2ca4869 (plan + decisions); CHATLOG in the follow-up commit.
found:   Elsevier key placed (secrets/, outside repo) and probed same hour: VALID (Scopus Search 200) but every ScienceDirect
         endpoint refuses it at key-config level (Article Retrieval 403 AUTHENTICATION_ERROR even view=META on gold OA;
         SD Search + Metadata 401) -> buys Scopus metadata, NO full text. Instrument qc/instruments/
         litkb_acq_probe_elsevier_key.py -> phase4/qc/litkb_acq_probe_elsevier_key.csv. H2 not built until a re-run shows 200.
files:   Scripts/decisions.yaml, Scripts/LITKB_WORKPLAN.md, _derived/s4/s4-prompt.txt (gitignored),
         qc/instruments/litkb_acq_probe_elsevier_key.py, phase4/qc/litkb_acq_probe_elsevier_key.csv.
next:    Kam: Elsevier API support for non-subscriber ScienceDirect access (re-keyed once same evening: identical refusal); re-register nightly dump task; launch S4 run 3 (_derived/s4/launch-s4.sh). Owed: Codex
         cross-family reads r2/r3/r4 + adversarial plan read (quota). Nothing litkb-… open in decisions.yaml.

## 2026-09-22  litkb SURVEY ROUNDS 3 + 4: shadow-library linkage + identifier coverage; the loop's twelve stages -> plan updated
goal:    Kam: (r3) "review all the github pages that use ... annas archive, lib gen, scihub ... how they link records ... maximize
         identifier coverage"; (r4) "engineering crawls for the lit review pipeline ... launch all 8, and the lower list items".
did:     r3 (wf_a95fe3dd-5d3, 40 min): S1 annas (+ local annas-mcp code, no key) / S2 libgen / S3 scihub + coverage dumps / S4 other
         libraries + OL/IA/HathiTrust/GBooks hubs / S5 crosswalk services + native-key table / S6 crosswalk codebases + data model;
         C3 Codex quota-fail (3rd). Record Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md (+_urls.csv 2961). Plan: S4.5
         item 1 identifier model (scheme_registry w/ distinct_values, md5/pii/core/bibcode/ocaid/oai + tier 2, provenance
         asserted_by + input id, fatcat conflict rule counted, part_of/version_of parents, validators, traps), Stage A Wave-0
         derivations + OFFLINE Sci-Hub/LibGen membership table (GitHub data, no ruling), Stage B fan-out order + closure rule +
         kill re-stated on arxiv/pii/dblp/isbn/md5; S4.6 Stage F ISBN sources (OL search, IA urn:isbn, STC parent_isbns),
         Stage G scidb five-way miss, serialised probes, md5 summary endpoint, freeze date 2022-02-12, PDFDrive/Aaaaarg/Z-Lib
         removed, STC crosswalk first; coverage instrument splits out-of-corpus. litkb-shadow-hosts question += offline dumps.
         Probe qc/instruments/litkb_acq_probe_crosswalk.py (466 DOI works): openalex 466, s2 416, arXiv 71 (litkb holds 6),
         pmid 67, pmcid 36 (all S2), isbn 12, relation 22; joined to files: of 222 no-file works, arXiv id 36, PMID 38, PMCID 24,
         ISBN 8, relation 11. Landed main d67da2a.
         r4 (wf_14029e46-453, 53 min): L1 discovery / L2 quote verification / L3 review+graders / L4 search / L5 citation
         anchoring / L6 synthesis K3 / L7 hermetic replay / L8 numeric evidence / L9 second-session provenance / L10 doctor+soak /
         L11 agent boundary / L12 run protocol; C4 Codex quota-fail (4th). Synthesizer ran in-workflow (Kam asked account 2; not
         re-run to avoid duplicate spend). Record Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md (+_urls.csv 3423). Plan:
         S5 entry conditions = the measured defects (Wave 0/1) w/ counters + kills; S6 K3 reads the WORKSTREAM LEDGER (brief
         admits promoted uses -> laundering surface opens on first promotion), real negative = run-1-only triples; S7 doctor =
         FULL restore (pg_restore --list passed 3 corrupted dumps), soak START sentinel, code stamp, server-side role gate + audit
         middleware (hooks exist, unused); S4.5 item 7 hermetic replay BEFORE the first referee round (replay graded vs its own
         stubs today), decision log + withdraw_version beside the refuse verb; S4 runs the reference stage on every file (17
         anchored not 0; stage 6 ran on 17/233); after-S5 rows: anchoring in order, discovery beyond recall, cell-addressed
         evidence, search after the fixes, reversible promotion, replay cache fold.
found:   MEASURED DEFECTS (crawlers, litkb_reader): litkb_search ~16 s, trigram leg ~14 s and 0 rows (expression-index recheck
         + unreachable 0.3 floor -> two legs in practice); locate_in_text refuses 120/120 ligature-damaged blocks (0025 fixed the
         index only); 3,408 table blocks text='' -> no table evidence row can exist (230k cells w/ bbox); 630 snowball candidates
         written with no workstream; K2 13/13 SUPPORTED on run-2, defects outside the loop; numeric containment fires on the
         mutation, 0/25 real; no run entity; seeding guard reads one file, live S4 prompt carried a work key, title-named
         papers pass; E13 passes replay while its recorded ladder disagrees; 14 worker DBs not 12; MCP intercept/middleware
         unused, all 13 tools to every client. r3: Anna's identifiers_unified (~120 schemes) fetched by aa_fetch.py, one key
         parsed; Crossref alternative-id = Elsevier PII for 90/92; 95 % decomposition (290k articles): oaDOI 37 / Sci-Hub 84.8 /
         both 94.0 / +institutional 97.4 -> two of three needed; Crossref `report` in Sci-Hub 0.046 %.
decided: land r3 and r4 on separate branches immediately (account-1 session limit); adversary pass on r4 blocks OWED as a
         follow-up; Codex OWED x4. No new shadow host built; offline membership table needs no ruling.
files:   Scripts/LITKB_WORKPLAN.md, Scripts/decisions.yaml, Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md,
         Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md (+_urls.csv each), qc/instruments/litkb_acq_probe_crosswalk.py,
         phase4/qc/litkb_acq_probe_crosswalk.csv. Branches work/20260922-litkb-identifiers (merged d67da2a),
         work/20260922-litkb-loop-stages.
next:    Opus adversary + builder-read on the r4 plan blocks (S5 entry, S6, S7, S4.5 item 7) -> fix pass; Kam: the 6 open ids +
         litkb-shadow-hosts' offline-dump half; launch S4 run 3; Codex reads when quota returns.

## 2026-09-22  litkb PDF-SOURCES + OCR SURVEY (2 rounds, 19 crawlers) -> plan overhauled: S4.5 rewritten, S4.6 + S4.7 inserted, 95 % target ruled
goal:    Kam: "how are we closing the gap between the hunter and actual pdfs" -> "massive github crawls ... all free sources ...
         books, studies ... layered pipeline ... 95 percent ... lit review on OCR ... agreement esp. latex ... codex on reddit ...
         second round with a blacklist ... overhaul this plan".
did:     Round 1 (wf_87c486af-659, 63 min): 11 Opus crawlers (A1-A7 sources/orchestration, E1-E4 extraction/OCR/math/QA) + 2 Codex
         forum searches (C1 acquisition, C2 OCR) + synthesizer -> SYNTHESIS-r1 (73 rungs), blacklist-round1 (1796 URLs).
         Round 2 (wf_3c9146c7-518, 55 min): 6 Opus crawlers on r1's unread leads (Zotero translators 748 counted, waterfalls,
         landing-page extractors, calibration/codeless sources, extraction/OCR, GitHub topics) + 2 Codex GitHub searches ->
         Codex QUOTA EXHAUSTED 05:06 PDT, both died with zero findings (owed). Synthesizer-r2 -> merged 125 rungs (52 new,
         32 re-graded), blacklist-round2 (2505). Tracked record: Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md (+ _urls.txt).
         Orchestrator probes (read-only; jobs/litkb-acquisition-survey/probe_*.py): litkb's own Unpaywall resolver on all 35
         no-oa-copy DOIs -> 4 answers, all Elsevier bronze LANDING PAGES; OpenAlex/Crossref link/S2/citation_pdf_url + HEAD ->
         exactly 4 FREE PDFs (S2 -> arXiv siblings); 1 dead author copy in Wayback; every Springer/Wiley/OUP/IOP/Cambridge "pdf"
         = paywall/HTML/token. Baselines: tracker 460 rows (DOI 406 / arXiv 42 / URL 2 / text 10); main_works 486, 263 with file
         (54 %), 233 with blocks; annas misses by Crossref type: 16 article / 5 PREPRINT (routing error) / 3 chapter / 1 book /
         1 proc / 7 no-registry.
         PLAN: S4.5 -> "acquisition ladder part 1" (substrate + ledger vocabulary: typed bad-file x5, blocked x4, stub/volume/
         cited/compressed states, terminal_url/status/dt, page_count/word_count, retriable per attempt, kind, articleVersion,
         unverified_keep, BUDGET + PolicyDecision; Stage A router/canonicalise/class filter; Stage B concurrent fan-out incl.
         S2/OpenAlex/Crossref link[]/CORE/EuropePMC/DataCite/EarthArXiv/NASA ADS; Stage C citation_pdf_url + per-publisher
         rule table ported from Zotero translators incl. MDPI CDN + Elsevier pii->pdfft + the acceptance test replacing
         %PDF-+128B; Stage E Wayback/IA/CommonCrawl; the bad-file rows READ FIRST). NEW S4.6 (Stage D grey/agency: USFS sitemap,
         USGS, OSTI, NTRS, govinfo, DSpace OAI mets w/ MD5, ArcGIS Online, city portals; Stage F ISBN namespace; Stage G under
         EXISTING grant: DDoS-Guard <title> detection, Sci-Hub UA/storage-path/Altcha, Anna's quota-free record; NEW hosts gated
         on litkb-shadow-hosts; Stage H behind litkb-institutional-access / litkb-tdm-keys; the coverage instrument vs the
         tracker). NEW S4.7 (CMap repair layer above ligature fix; qpdf/complexity gates FAIL CLOSED; LM-coherency referee +
         quality TIER, quotes only from HIGH; scans MEASURED before adopted w/ gold pages + CI; math verified w/o ground truth:
         2 independent decoders + KaTeX parse/compile/degeneracy/normalised exact/CDM F1/image-vs-crop/VLM referee).
         decisions.yaml: litkb-coverage-target DECIDED (Kam's words; 95 %, automated, layered) + OPEN litkb-coverage-definition,
         litkb-institutional-access, litkb-shadow-hosts, litkb-tdm-keys, litkb-crc-book. s4-prompt.txt: S4 launches S4.5.
found:   Round-1 finding "census = broken instrument, re-run = biggest jump" REFUTED by measurement (4/35 answer, all landing
         pages); mechanism (missing email / 5-min outage retires the route forever) SURVIVES. Highest-yield missing rung =
         landing-page->PDF (citation_pdf_url; MDPI CDN mdpi-res.com serves application/pdf where www.mdpi.com 403s).
         External base rates (IA ingest notes): OA URLs ~80 % first pass; OAI harvesting ~35 %; no-pdf-link mostly NOT a
         parser bug. finnschwall 582-paper review: ~86 %, 65/82 misses closed-access w/ no free copy. Elsevier TDM key returns
         HTTP 200 first-page STUB (X-ELS-Status). OCR voting precedent COLLAPSED (LV-ROVER = 5 Tesseract configs; untuned
         corpus dCER 0.001, p=0.66 -> UNDETERMINED); post-OCR corrector +5.11 % only WITH sliding-window vote, negative without.
         No 4 GB-GPU scientific-OCR config exists anywhere; T2000 = classical OCR + orchestration; VLM rungs = Colab.
         Dead leads: api.fatcat.wiki ECONNREFUSED, ArcGIS Hub datasets 0 docs, OpenDOAR/ROAR Cloudflare, DTIC PNG decoy,
         allenai/dolma no PDF pipeline, internetarchive/pdftrio absent.
decided: honest bottom line in the plan: ~86 % legitimate-automated demonstrated; 95 % needs institutional access OR shadow
         tier (pre-2021) OR grey layer OR a broader "has the study" definition -> Kam's rulings, recorded as ids, not prose.
         New shadow hosts NOT built until ruled. Codex adversarial read OWED (Opus adversary + builder-read stood in).
         REVIEW (Codex owed): Opus adversary 83 findings (A10 B2 C16 D7 E15 F20 G5 H8) + Opus builder-read (4/17 items
         buildable as written) -> fix pass: 6 stale "S4.5 item N" pointers; free-ceiling counter split MEASURED (must convert)
         vs bronze ESTIMATED (reported); Stage B rows = every no-oa-copy DOI, yield MEASURED by the run, B3/B12 carried as
         measured-zero, NASA ADS probe-not-build; E11/E12 replaced by real acquisition negatives + CONSTRUCTED ones labelled;
         G3a -> litkb-shadow-hosts, G4 -> litkb-blocked-works-grade (questions amended); H5 measured-AGAINST not built; H6
         already in netutil; sub_status column not new state words; copy_kind extended not articleVersion column; pages
         exists (word_count only); volumes_bound_as_article; ISBN attaches to the book, chapter by part_of edge; S4.7 honours
         litkb-second-formula-decoder (verification ladder on ONE decoder; no re-open); LOW-tier refusal in SQL; probes moved
         into qc/instruments (3.4b) writing phase4/qc/litkb_acq_probe_*; litkb-s47-colab-queue open; §M heading in the survey.
killed:  "more OA indexes reach 95 %" (24-tool union added one source: NASA ADS). Cross-engine OCR voting as a given.
files:   Scripts/LITKB_WORKPLAN.md, Scripts/decisions.yaml, Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md (+_urls.txt),
         _derived/s4/s4-prompt.txt, jobs/litkb-acquisition-survey/{STATE,SYNTHESIS-r1,SYNTHESIS-r2,A*,E*,C*,R2*,probe_*}.
         Branch work/20260922-litkb-acquisition-ladder.
next:    Kam: rule litkb-coverage-definition / institutional-access / shadow-hosts / tdm-keys / crc-book (survey §6 is the
         reading); launch S4 run 3 (unchanged line). Codex: re-run R2C-github-{acquisition,ocr} + adversarial read when quota
         returns. First measurement of S4.5: read the bad-file rows.

## 2026-09-21  litkb PLAN REVISED in place: S4 extended, S4.5 inserted, S5 entry condition, post-S5 table, survey verdicts with provenance
goal:    Kam (22:00, then bed): "an exhaustive plan. It will edit the current plan" — LITKB_WORKPLAN.md revised from the wrap-up evidence
         + GitHub survey; no code; STOP after, Kam launches S4 run 3 himself.
did:     6 Opus read-only auditors (acquire/admit/bind/state/survey/carryin) + critic re-derived every fact BEFORE drafting; then
         Codex adversarial read (78 findings: A33 B1 C10 D11 E23 F0) + Opus plan-verify (15 commands run, ~30 measured claims sourced).
         Plan: conventions +1 (a design is a claim); "Where we are" rewritten; S4 += `book` class, DB-visible quarantine state
         (file_versions.status allows 'quarantined', never held), measurement bed w/ commands; NEW S4.5 (spelled with a point: gate
         regex `^### S\d+`) = back-off keyed (route,status,http_codes,at) + in-run transient retry + arXiv discriminator · registry
         identity (relation PROBE first, edges w/ third state, identifier-first dupes, ISBN-13 type-scoped, key-LENGTH rule) ·
         served-bytes sha on attempt row + rejected-sha lookup + landing through check 3 · second-session REFUSE verb (none exists);
         S5 += entry condition (promoted tracker-era metadata: fail-closed citation builder AND repair via versioned path),
         per-hunt time budget, ruled recipe under its own conditions, two ruling-owed builds (ISBN->md5, registry-over-claim);
         "Improvements after S5" table (7 rows, each UNVALIDATED, positive+negative rows, fires-on); "The survey's verdicts" table
         (VERIFIED/LIVE/ASSERTED per mechanism); register: S2 row + "Codex cannot read block context" + S7 tolerated-red DELETED.
         decisions.yaml +5 open (kam): litkb-e23-residue-copies, litkb-blocked-works-grade, litkb-scihub-parked,
         litkb-tracker-corrections, litkb-from-file-version-state. _derived/s4/s4-prompt.txt rewritten (launches S4.5).
         Report Reports/LITKB_PLAN_REVISION_2026-09-21.md: every change w/ source + verified/asserted; hypotheses rejected; gates.
found:   Brief's census cells STALE (run the GROUP BY; Sci-Hub 0 ok all-time holds). "16 E24 rows at 1.00" wrong: registry-quirk
         rows at >=0.85 (13 at 1.00); 293 refuses on YEAR not author -> two waivers. 254-file sweep NOT persisted (test set = tracked
         fixtures + an instrument to build). Re-served bad file is RE-QUARANTINED, not duplicate-held. known_md5 looks up the
         ARCHIVE md5 -> served hash can never suppress its own request. make_key crash = LENGTH (key[:59]) not corporateness.
         Metadata fallback binds a BLANK page 1 at 1.0 on /Title+/Author (latent: 18 live pdf-title binds all have text).
         NO refuse verb for a proposed admission. 187/235 files: OWNED by refused admissions per reaper (orphans=0), unbound.
         `plan` gate has NO rule for restated counts (probed: stays green) — review is the only catch.
decided: S4.5 not S4½; quarantine STATE=S4, LEDGER=S4.5; Sci-Hub default -> Kam (open id), back-off lands regardless; 194 REFUSE intent
         kept (report §9 says approve — conflict recorded, verb first); both metadata fixes; external paths unbackticked.
killed:  Codex A-group counts of agents/sessions/constants rejected (not works/rows); pre-existing S0/S3/disposition-table counts
         left as debt; ISBN->md5 + registry-over-claim moved BACK into S5 (rulings name S5).
files:   Scripts/LITKB_WORKPLAN.md, Scripts/decisions.yaml, Reports/LITKB_PLAN_REVISION_2026-09-21.md, _derived/s4/s4-prompt.txt,
         jobs/litkb-plan-revision/{STATE,*-audit,critic,codex,plan-verify}.md. Branch work/20260921-litkb-plan-revision.
next:    Kam: read the report §2/§3; rule the 5 open ids when convenient; launch S4 run 3:
         `wt.exe -w new "C:\Program Files\Git\bin\bash.exe" -lc /d/edmonds-pipeline/treedata/_derived/s4/launch-s4.sh`.

## 2026-09-21  litkb E23/E24 RULED + RUN; GitHub survey of resolve+admit / acquire+bind; plan-revision prompt for Kam
goal:    Kam: "Lets work on the E23/E24 rulings" -> bring the table, rule, run; then "how do other repos solve this" (Fable -> 5 Opus crawlers); then a prompt
         for a plan-revision session Kam starts himself ("you just give me the prompt").
did:     Pre-ruling measurement: Crossref author lists for the 14 registry-quirk rows (4 coauthor-as-first, 1 AMS year gap, 10 claimed author NOT on the paper) and
         relevance-vs-abstract for the 10 (all describe the registry paper); 187 is in DataCite; 4 E23 rows carry arXiv ids in the tracker's source column, 4 more
         found by arXiv search, 2 by Crossref. Kam ruled: registry authoritative for all 21; 187 admit; E23 10 hunts + 2 URL proposals, drop 50, hold 53/369.
         decisions.yaml litkb-registry-over-claim. RUN (ws ruled-hunts-1, 34 rows, 35 result rows): bound-unextracted 10 (9 PDFs + 194's page), blocked/403 15,
         api-error/registry-transient 8 (arXiv 406 x24 over 30 min), refused 2 (187-URL duplicate-review; 235 check3 0.80). 24 works admitted fresh under registry
         records; Anna's downloads 7; Sci-Hub 15/15 blocked. Register: E23 carrier tracker 25 (Coulter_2008), E24 carrier tracker 22 (Liu_2019), both
         bound-unextracted/already-bound; held_for_ruling now 0; freeze at merged head + replay executed=24 mismatches=0 (Reports/LITKB_EDGE_RUN_2026-09-21_replay-rulings.csv).
         SURVEY: jobs/litkb-s3-wrap/github-survey/{SYNTHESIS,A..E}.md - source-verified at commits; my spot-checks of its litkb claims held (relation dropped by
         parse_crossref; quota-stop folded into blocked; blocked not in DEAD_STATUSES). Pinned in WORKPLAN S5 carry-ins. Plan-revision prompt written
         (_derived/plan-revision/plan-revision-prompt.txt, pasted to Kam); launcher/mcp beside it unneeded.
found:   `--hunt-request` FILLS the drop-off claim into check 1 (hunt.py fill_from_request) -> the brief's recipe refused; worker adapted: bare hunt, then link
         --no-spend (25/34 linked). admit_registry has a `registry_only` mode (0020) = Kam's ruling already in code. Corporate creator crashes works_key_check
         (187 needed --key). 187's 7.6 MB PDF UNBOUND (duplicate-review then duplicate-held). 194's King County page holds NO document - proposal to be refused.
         Tracker vs registry over 24 rows: first author wrong 17, year wrong 8, both right 3. Survey: A two-tier rule (test set = 16 E24 rows), B relation edges
         + JabRef dedupe order + ISBN-13, C Zotero per-host back-off keyed (route,status,codes) + park Sci-Hub (0/9 all-time), D pdf2doi id-in-file + font-size
         title + content gate, E hash on attempt row + quarantine as ledger. ALL relayed, none re-run on real rows (3.4c).
decided: Kam: "don't change the plan yet" -> findings recorded as carry-ins; the plan-revision session edits the plan. Kam launches that session and S4 himself.
next:    Kam: paste the plan-revision prompt into a fresh session in Scripts\; after it, launch S4 (launch-s4.sh). Ops: re-run the 8 arXiv rows when arXiv answers 200;
         a second session REFUSES 194's proposal; 235 manual admission; 187's PDF bind. Kam: copies of 53/369/E20 if he has them.

## 2026-09-21  litkb S3 WRAP-UP: Kam's six rulings encoded and MEASURED; 13 proposals promoted; E25 gate fixed; clean S4 launch kit
goal:    Kam: rulings E20-E25 + the 13 tracker-era proposals ("do the recommendation ... take care of everything else ... do not come back to me"); S4 to rerun clean, launched by Kam.
did:     3 Opus workers in own worktrees + 1 Opus auditor. APPROVE (s3-approve-2, ws approve-2): 13/13 manual proposals approved = promoted (Chrisman's file IS the 1982 paper; no DOI exists);
         Reports/LITKB_APPROVE_SESSION_2026-09-21b.md. TITLE HUNTS (ws title-hunts-1): 37 tracker rows + book + preprint + Chrisman, 40 rows, 556 s, Anna's downloads 0, Sci-Hub 1;
         Reports/LITKB_TITLE_HUNTS_2026-09-21.{md,csv}. E25 (ws e25-rebind-1): binding.py prefix-strips the ROTATED arXiv margin stamp that pdftotext -layout puts on the title's
         own line (Gulrajani 0.6842->1.0, Kumar 0.6410->1.0; sweep 254 files 0 regressions/4 fixed/2 moves; both re-bound live, bound-unextracted); auditor MERGE, every number
         reproduced + a 2778-bind cross-title probe (the strip never binds another work). decisions.yaml: litkb-book-policy, litkb-sibling-edition. Register: E20/E21/E22 executable
         with MEASURED pairs, E25 not-a-hunt, E23/E24 ruled + held with the residue question; final freeze at merged head, replay executed=22 mismatches=0 tracebacks=0
         (Reports/LITKB_EDGE_RUN_2026-09-21_replay-rulings.csv, _derived/edges/rulings-manifest.json). S4 kit: clean-start prompt, LITKB_SESSION=s4-run3, slug readability-2,
         launcher names Git's bash.exe; preflight all 0. All 8 wt-* checkouts parked/removed (S3's six were clean+merged+parity), tokens vaulted (approve-2, title-hunts-1, e25-rebind-1).
found:   E23: 0/15 resolve by title (the low-confidence skip was right). E24: 0/22 - STRUCTURAL: resolve_title -> admit/resolver.py judge_candidate re-applies check 1's three tests to
         the TRACKER's claim, so a title hunt can never rescue a row whose author/year is what's wrong; 16 matched title >=0.85 to the SAME stored DOI; 7 DOI corrections corroborated
         (2,33,48,55,67, crossed pair 177/178); 187's 10.5067 DOI is 404 at Crossref but live in the handle system. E20 book: blocked/403, Crossref carries ISBN 9781466568419 (e-only).
         E21 preprint: OA 200, bound as ITS OWN work, no duplicate refusal. E22: refused/ambiguous-title (crossref best 0.52 Lloyd 1976), gate 0 before admission. The 13 promoted works'
         metadata is poor (authors first+last only, given empty, venue NULL, one title truncated, Krahenbuhl_2011 year unconfirmed) - identity right, citations not. Auditor notes:
         builder-e25's own known-bad test monkeypatches the strip in the test (the OTHER tests gate: 4 red under mutation); DB check 3 is a record check; test_experiments
         pointer gate was red in every worktree (gitignored 18 MB product) -> fixed here (_git_ignored; proven red->green in the worktree). file_versions.state='promoted' with
         promotion_id NULL is what 0003_write_functions.sql sets for every bind - not an anomaly. Two overlapped pytest runs on one worker DB gave a phantom F (lesson in memory).
decided: "acquire the book and don't spend" read as no EXTRACTION spend (recorded in decisions.yaml for correction). Two works for sibling editions. Not-a-hunt for a binding-gate row.
         E23/E24 residue stays Kam's; no registry-overrules-claim path built (S5). No blocked back-off (S5). Kam launches S4 run 3 himself.
next:    Kam: `wt.exe -w new "C:\Program Files\Git\bin\bash.exe" -lc /d/edmonds-pipeline/treedata/_derived/s4/launch-s4.sh`; rulings on E23/E24 residue when convenient.
         S5 carry-ins in LITKB_WORKPLAN.md "### S5" (ISBN harvest + annas ISBN->md5, relation edge, blocked back-off, annas bad-file x3, quarantine DB state, metadata fix, E24 path).

## 2026-09-21  litkb S3 independently re-verified; register hash guard fixed (content, not bytes)
goal:    Kam: "Can S3 be trusted? I didn't monitor any of its work" -> re-run S3's gates myself, not read its report; wrap up what S3 left.
did:     REPRODUCED on main: `edges --replay` w10 -> executed=19 mismatches=0 tracebacks=0 exit 0; pytest -k litkb 1579 passed/25 skipped/3 xfailed;
         SKILL grep 0; DB: Riva_2017 + Abdulkader_2020 in main_works, edges-1 admissions refused x5 only, 14 scihub blocked rows; reaper 27
         __staging-orphan__ reason files at 10:25Z match counters (6 older reason files = binding-time quarantines 09-17 + live run; none from S4).
         FIX: `_register_sha256` folds CRLF->LF before hashing (guard refused S3's own manifest on a CRLF checkout, nothing edited); `fixture_committed`
         recorded at freeze; test c3b (CRLF copy grades, one edited expectation refused) — RED under byte-hash mutation, GREEN intact; SCHEMAS
         edge-run section amended. Replay gate re-run on the CRLF working copy vs S3's unchanged manifest -> exit 0.
found:   S3's manifest names repo_head 568988b but its register sha only exists in 06c42f6 (frozen from the working tree 14 min before commit) — consistent, now
         recorded. Acquisition on the day: 7 attempt rows (scihub blocked x5, open_access blocked x1, annas bad-file x1); annas dead-skipped for
         E03/E07 on 09-15 `not-in-archive`; E13 annas `bad-file` three times on three dates (09-16 x2, 09-21). No new file was acquired live in S3.
         First c3b draft PASSED under mutation (working copy already CRLF == "CRLF copy"); rewritten to freeze on an LF copy and grade a CRLF copy.
decided: content hash for authored fixtures, byte hash for recorded HTML fixtures (the .gitattributes precedent). No `blocked` back-off (S5 carry-in stands).
next:    Kam: rulings E20-E25; the 13 proposals; S4 rerun. S5: annas repeated bad-file on one DOI is a route question, not a host mood.

## 2026-09-21  litkb S4 overnight output PARKED untrusted; checkouts removed
goal:    Kam: "Delete S4 work tree ... happened over night. Can't trust it."
did:     WIP-committed the dirty trees (q2: 5 mod + 7 new incl. Reports/LITKB_OCR_VRAM_2026-09-21.csv; r: 5 mod + 1 new), pushed all three as
         github/archive/2026-09-21-litkb-s4-{q1,q2,r}-untrusted (parity 0/0), `git worktree remove` (no --force) wt-s4-q1/q2/r. Local work/ branches kept (no delete).
found:   live DB has NO extraction_jobs table -> 0029 never applied (reservation only, ecee36c). Workstream readability-1 still `open` (03:52, path treedata; token in main tree).
         S4 PID 74112 not running. NOT checked: other DB rows S4 may have written under readability-1.
decided: nothing from S4 merges. S4 reruns from main when Kam says; the archive branches are reference only, audited before any reuse.
next:    Kam: rerun S4 or not; close/vault readability-1. Rulings E20-E25; the 13 proposals.

## 2026-09-21  litkb S3 — every hunt ends in named state; edges graded live 14/0/0/0 + replay 19/0/0/0; second session approved 2
goal:    S3: closed hunt vocabulary + reason classes; register from REAL rows; gaps (HTML-only to blocks, reaper, mirrors from config, SKILL, absent split, acquire detail); second-session approve; `edges --replay`; (c) fires.
did:     4 Opus builders (own worktrees, w7-w10) + 2 Opus auditors. Phase 1 -> main `7b806c7`: STATES extracted/bound-unextracted/held/refused/api-error/blocked/crashed + REASONS + STAGES (`proposed` NOT a state, `absent` out),
         SCHEMAS table, transients retryable (route raise -> api-error + attempt row; registry 406 -> api-error, no admission row; boundary -> crashed/<stage>:<Exc>), `config.py` LITKB_SCIHUB_MIRRORS (4),
         `absent_kind` 3-way + `holder_state`, `litkb_acquire` detail + attempts_detail, `litkb reap` (sha/rel_path/admissions.checks ownership, 72 h, dry-run default), SKILL "manual --from-file last".
         Phase 2 -> main `568988b`: HTML page -> text snapshot -> proposed admission -> blocks (extractor text-snapshot); register 26 rows (14 execute / 5 replay-only / 6 held_for_ruling / 1 not-a-hunt);
         `litkb_edge_run.py` + `edges --freeze/--manifest/--replay`; 27 mutation rows fired (HV1-6 S3A1-4+2b S3R1-4 HW1-4 S3E1-6). Live: manifest 10:23:01Z -> `executed=14 skipped=0 state_or_reason_mismatches=0 tracebacks=0 held_for_ruling=6 waits_on_migration=0`;
         replay on w10 `executed=19 ... 0/0`; (c) live: edited register refused on sha256; re-frozen valid-but-wrong E11 -> mismatches=1 exit 1. Second headless session (own ws `approve-1`, session s3-approve-1) APPROVED Riva_2017 + Abdulkader_2020 (URL-source proposals since 09-16/17) -> promoted.
         Reaper apply run fb2a1e0f: 27 quarantined (11 incoming 09-15 downloads, 16 stub PDFs leaked test seeds). Report Reports/LITKB_EDGES_2026-09-21.md (8 bounded outcomes); ids in it.
found:   Kam moved session headless -> interactive 00:07; builder A1 died with process, resumed from transcript. First live grade mismatches=3: E03/E07 Sci-Hub answered blocked on all 4 mirrors (prediction about host; re-adjudicated, replay keeps unobtainable class);
         E06 Tkaczyk_2024 already HELD in main -> check 2 duplicate-review (C + auditor adjudicated on fresh replay DB, missed it) -> HTML-to-blocks proven replay-only. Live run created NO proposals. Both merge candidates refused by auditors first
         (p1: absent bucket filtered w.state='open' vs check 2 global; p2: edges replay test poisoned shared DB via global `_title_duplicates` -> 4 red order-dependent; live.inputs missing; E06 allowance). First reaper dry run called FPGA snapshot orphan (admissions.checks leg added).
         `gate | tail; $?` masked mismatches=3 once. `py -m litkb` from worktree runs MAIN install. E13 505 s (blocked never dead-skipped).
decided: `proposed` not a state (web-source gate: blocks searchable from own ws). No migration in S3. Held rows E20-E25 + 13 tracker proposals -> Kam. S4 launched in NEW terminal window (wt.exe + bash script), not headless-to-log.
killed:  S4 instance #1 (session 29720c90, opened readability-1 01a0c398-3441…, committed 0029 reservation ecee36c) — killed by S3 orchestrator 03:56 by MISTAKE: verified by transcript jsonl (interactive sessions flush late), read absent file as stuck. Relaunched 03:57 with recovery note; #2 verified by EFFECT (STATE.md "Kill and restart", one ws row). Rule: verify a session by effects, never by a transcript file.
next:    S4 (readability) running in its own window (PID 74112, `_derived/s4/launch-s4.sh` via Git Bash — `wt.exe … bash` resolves to WSL bash; name Git's bash.exe). Kam: rulings E20-E25; the 13 proposals.

## 2026-09-21  litkb S2 — one unseeded OA work crossed whole loop; `first-work` gate + acquisition-event contract
goal:    S2: freeze manifest BEFORE hunt, prove absent, ONE spending hunt -> block -> verified use -> review -> review-check -> review-context -> Codex -> acceptance. Build acquisition-event contract + test.
did:     Opus builder (own worktree): `first-work --freeze/--manifest` (7 counters), URL hunt path records `acquisition_attempts` via same SQL fn as route path (route `hunt-url`, migration 0028),
         verifier `acquire/events.bound_without_event` feeds `operator_interventions`; 9 known-bads fire. Opus auditor: MERGE WITH FIXES (silent except branch; NOT EXISTS lacked work_id;
         client-clock freeze) -> fixed 84873cb, each with firing test -> merged 0dd8886, full check.py green 713 s, pushed. Sonnet scout: 4 drop-offs (all absent, gold-OA).
         Live: freeze 05:12:37Z (db clock) -> litkb_work absent -> CLI hunt Maiti 2022 (open_access ok, 113 blocks, 105 s, refusals []) -> 3 verified uses (supports / context / refutes)
         -> review (Opus review-writer) PASS 0 findings -> Codex 3/3 SUPPORTED session 01a0c271-712e -> grade `new_works=1 bound=1 extracted=1 searchable=1 verified_uses=3 claims_ungraded=0 operator_interventions=0` exit 0;
         replay manifest (frozen after) -> new_works=0 exit 1. Report Reports/LITKB_FIRST_WORK_2026-09-21.md; ids in it.
found:   agent-frontmatter hook `${CLAUDE_PROJECT_DIR}/.claude/hooks/litkb_guard.py` resolves under Scripts\ (no file) -> `py` exit 2 = BLOCK -> review-writer/librarian lose Read/Grep/Glob
         from every Scripts\ session; measured; tested locator fix in Reports/LITKB_AGENT_HOOK_PATH_2026-09-21.md (Kam's edit, classifier). review draft 1 failed at line 1 for it; draft 2 with grammar inline.
         `k2-never-fired` unreachable for one-work run unless work contradicts itself (`open` does not count) -> tree-class sentence refutes expected ranking -> recorded `refutes`, request `contradicted` (1/1).
         `search_unpaywall` empty for every DOI incl. gold-OA controls. Docling no artifact on native Copernicus PDF (GROBID carried). `gate | tail; $?` masks exit code (bit twice).
decided: run proceeded one migration ahead of live DB (0028 unapplied, Kam's) after 60+10 min silence (away-mode rule); manifest records both tips; DOI/OA path untouched by 0028.
         `record_use` bad-kind refusal now lists the seven kinds. Session rule (Kam): lessons -> project, launch next session headless (Fable), old session ends.
next:    Kam: apply 0028; apply hook fix. S3 launched headless from this session (see next entry / Reports/LITKB_S3_LAUNCH...). Promotion of 3 uses on Kam's track.

## 2026-09-20  litkb post-S1 — preflight subcommand; Codex as a scripted, schema'd stage, gate proven LIVE
goal:    Kam: integrate the next-session tips + the Codex improvements INTO the tree, finished tonight, no spill into S2.
did:     `litkb_acceptance.py preflight` (stray_tokens migration_mismatch mcp_servers_missing main_not_at_parity
         soak_stale; 11 mutation tests; first command in plan protocol). Launch recipe → bash + prompt FILE + first
         ws_open check; SKILL no-topic stop; log reader utf-8-sig. Codex stage (Opus builder, 10 harness rows CX1-10,
         census hole fixed): `litkb review-context`, `qc/fixtures/litkb_codex_report.schema.json`,
         `qc/instruments/litkb_codex_review.py` (prompt on stdin, sha256 stamps, session id), `litkb_acceptance.py
         codex --mutate`. LIVE (2 Codex calls, 0.155.1): run-2 review 13/13 SUPPORTED + run 2's 3 editorial findings
         reproduced; planted causation on citation 5 → OVERREACH, `mutation_not_flagged=0`. Three wrapper defects
         found live, fixed, tested (strict schema needs all-required; refusal on stdout stream; 81-char quote_head).
decided: Reports/codex/ whitelisted (evidence a gate fired = work product). overreach is a FINDING, not a gate fail.
killed:  hand-exported block context (`run2_block_context.md` class) — `review-context` is the producer now.
files:   Reports/LITKB_CODEX_STAGE_2026-09-20.md, Reports/codex/, docs/LITKB_CODEX_PROMPT.md, docs/SCHEMAS.md
         (codex report), Reports/LITKB_SCOUT_LAUNCH.md §4, jobs/litkb-s1/{brief-C,builder-C}-codex-stage.md.
next:    S2. Kam: relay agent step 2 → builder-C report §7 (stdin, not `"$(cat …)"`); pgpass litkb_reader for worker DBs.

## 2026-09-20  litkb S1 — the front door: lit-scout, `title` refs, hunt VALIDATES; first headless scout run (9 drop-offs); soak clock started
goal:    `LITKB_WORKPLAN.md` S1: topic → drop-offs unattended; every ref shape hunt sees ends in named state.
did:     paper-search MCP in `.mcp.json` (strict-config probe lists 13 litkb + 58 paper-search tools). Two Opus
         builders in own worktrees, one auditor, all merged (75df9d3): migration 0027 (`ref_scheme` gains
         `title`; `litkb.hunt_request.REF_SCHEMES` one home, SQL CHECK read by test); `hunt(ref_scheme=)` validates
         (six codes `REF_REFUSALS`), fills title/author/year from hunt_request row; `cmd_discover` retired;
         fixture `qc/fixtures/litkb_ref_shapes.json` + real 1-query Crossref capture for ratio gate (HS10 RED at
         0.80); HS1-12, HQ9-10 fire. `.claude/agents/lit-scout.md` (30 tools, zero download/read/Bash — frontmatter
         enforced per name), SKILL "Stage 1 — discover", `litkb_acceptance.py scout --freeze/--manifest`,
         `qc/instruments/litkb_scout_run.py` (driver, no spend, resumable, `--retry`), `litkb.ops.nightly_soak`
         (03:17 nightly, `Reports/LITKB_SOAK.csv`, standing workstream `soak`). Kam applied 0027 + registered task.
         Scout run scout-1 (leaf-off/leaf-on label transfer): 9 drop-offs, all machinery counters 0, no human
         input, `SCOUT-STOP` reason; nonsense topic → n=0 + reason (the (c), fired). Run found ten pre-S1 hunt codes
         missing from instrument vocabulary → `HUNT_REFUSALS` + AST-scan test (f791331).
decided: `litkb-s1-dropoff-shortfall` — 9 < 10 accepted (honest stop rule; no quota rerun). S1 hunts spend=False
         (S2/S5 own acquisition). Scout attribution via `qc/fixtures/mcp_scout.json`, not `.mcp.json` edit.
killed:  attempt 1 of scout run — PowerShell 5.1 split `claude -p $prompt` at first embedded quote; scout got no
         topic, improvised, opened `scout-2026-09-20` in main tree root, 9 stray drop-offs (workstream left open,
         token vaulted). Launch from bash with prompt FILE. Offline half-synthetic ratio fixture (replaced by live).
files:   Reports/LITKB_SCOUT_RUN_2026-09-20.{md,csv,_retried.csv}, Reports/LITKB_SCOUT_LAUNCH.md,
         docs/LITKB_SCOUT_PROMPT.md, docs/SCHEMAS.md (three litkb sections), jobs/litkb-s1/ (briefs, reports,
         auditor, STATE, fix_permissions.py).
next:    S2 (first unknown work, bounded). Carry-ins: arXiv transient 406 → terminal `admission-refused` (S3
         api-error); launch doc → prompt file + bash; BOM in log reader; scout with no topic → n=0.

## 2026-09-20  litkb S0 — one plan (`LITKB_WORKPLAN.md`), one tree (ten checkouts removed, nothing deleted), acceptance instrument
goal:    Kam: lit-review work plan "fragmented, confusing as human PM". New plan to finish line, multi-session, each session ends in STATE. Ingest all worktrees.
did:     3 explorers (code map, ten worktrees, authored docs) + Codex adversarial review of draft → plan approved. Finding: "operational" run 2 pre-named 3 extracted works + expected_claim strings; open-web discovery + PDF acquisition never exercised. `hunt.ref_kind` classifies (all non-URL → `doi`). Plan = S0–S7 ladder, loop-stage vocabulary, done-state = (a) artifacts (b) command+counters (c) known-bad fires. S0 landed on `work/20260920-litkb-workplan`: `LITKB_WORKPLAN.md` (gated, `NOT_A_CAMPAIGN_PLAN`), WORKPLAN.md litkb section → 8-line pointer, jobs STATE.md/design §14/memory → pointers, decisions `litkb-finish-line`/`plan-home`/`worktree-disposition`/`autonomy-grant` + `k2-no-seeding` (open), `qc/instruments/litkb_acceptance.py` (plan · disposition · guard-checkout; 30 tests; Opus builder), 22 reports archived byte-exact from 8 branches, crossref-proposer merged (gated by unchanged `confirm_s2_candidate`), ligature `da91101` cherry-picked, 3 workstream tokens vaulted (hash-verified), splink dirty re-run committed `68ba778`, ten checkouts removed after guard/parity/clean; counters `0 0 0 0`; known-bads fired (plan ×2, disposition ×3, guard ×1). 12 POSSIBLY-STALE items adjudicated: 7 closed, 5 open with owners.
decided: finish line = topic → graded review → synthesis (promotion beyond line). Plan home = `LITKB_WORKPLAN.md`; counts are commands, rulings are ids, future files unbackticked. WE DON'T DELETE: branches/refs kept, checkouts removed only when parity + token vaulted. Git autonomy grant (CLAUDE.md §3.1). S2 = bounded unknown-work run BEFORE backlog drain (Codex ordering). K2 no-seeding = open question, not ruling.
killed:  full backlog drain as S5 prerequisite (corpus work, proves nothing about discovery). "Browser last" route promise in SKILL.md (manual `--from-file` exists; automated browsing does not — S3 rewords). Counter `undeleted_approved_refs` → `branches_not_at_parity`.
files:   LITKB_WORKPLAN.md; decisions.yaml; WORKPLAN.md; CLAUDE.md §3.1; qc/test_docs_match_code.py; qc/instruments/litkb_acceptance.py; qc/test_litkb_acceptance.py; Reports/LITKB_WORKTREE_DISPOSITION_2026-09-20.{md,json}; 22 archived Reports/LITKB_*; jobs `D:\tools\claude-config\jobs\litkb-s0\` (STATE.md, builder-acceptance.md, grant script)
next:    S1 front door: `lit-scout` agent + `title` ref scheme + `hunt.ref_kind` validation; entry condition paper-search MCP in `.mcp.json`. Kam: `litkb-k2-no-seeding`; re-register nightly dump task.

## 2026-09-20  litkb OPERATIONAL — definition MET on run 2 (Fable 5.1 orchestrating ~20 Opus workers + Codex)
goal:    agentic lit review operational per `litkb-operational-definition` (full loop, unattended, K1 + K2 fire)
did:     3 builds + 8 fix cycles + 8 audits, all merged on `work/20260920-operational` @ 18edc73: web-source gate (2a), index-only ligature normaliser 0025 (2b), stage 8 = review-writer agent + `docs/LITKB_REVIEW_GRAMMAR.md` + grader `litkb review-check` (25 code mutations fire), 0026 quotes verify on canonical newlines. Proving run 1 @ 00bf81c: loop + K2 fired, K1-in-full FAILED (half sentences overreach single-line fragments — record_use rejected quotes crossing `
`, 48.9% of blocks). Fixed, Kam applied 0025+0026 to live (tip 26), run 2 @ a9d6fc2: review-check PASS, Codex 0/13 overreach with block context, K2 fired (1 CONTRADICTED, 1 UNCONFIRMED). Verdict recorded `litkb-operational-verdict`.
decided: grade against the FIXED definition, not Codex's editorial bar (no renegotiation either way). Keep different-model output review as last loop stage (paraphrase is the K1 escape no grader closes). 0024 RETIRED not renumbered (0025 woven through instruments). Merge order 2a→2b (0025 showcase block is a web proposal).
killed:  R1 "append beside token" normaliser rule — lexemes here CONTAIN spaces (collation), any insertion loses lexemes; PREPEND instead (old text = byte suffix, 0/372,192 lost). Per-line quote grammar — 7/8 real verified spans cross CRLF. Fixed byte→ligature table (one C0 byte = two ligatures in one file).
files:   Reports/LITKB_OPERATIONAL_PROVING_RUN_2026-09-20.md; decisions.yaml; WORKPLAN.md litkb section; pipeline/litkb/{visibility,review_check,use,brief,textnorm}.py; db/migrations/0025,0026; qc/test_litkb_{web_gate,review_check,textnorm_index}.py; audit trail `D:\tools\claude-config\jobs\litkb-operational\` (17 reports)
next:    fix/20260920-grammar-residuals (3 Codex editorial items, in flight) → audit → merge. Kam merges to main. Promote proving-run workstreams (never run on live). 209 held works unextracted. Machine: PROJ_LIB/GDAL_DATA deleted by Kam (25 rasterio reds gone).

## 2026-09-12  LIT ROUND 5 — inventory (know / derived / need-by-reading / need-by-measuring / don't know) then 3 searches to move items into "know"
goal:    Kam: "establish what we know, what we don't know, what we need more information on; then find the studies." Inventory given in chat; searches targeted the "closable by reading" bin.
did:     3 Sonnet searchers (stats; urban forestry D_k(τ); misalignment priors) + Fable Sci-Hub pass by DOI (one bare curl per call) + Efron's Stanford page.
         review §4.14 (4.14.1–4.14.3 + negatives), §4.13.1 caveat resolved, §7 round-5 bullet, §8 round-5 bibliography (35 works). framework §14 (14.1–14.4), §12.2 assumption (i) test paragraph, §13.1 bootstrap model [Q], ledger deltas + new row 15.
         Moved into KNOW: Efron identity holds for arbitrary joint f (Efron 2021, author's page — closes the row-6 caveat). λ^k decay + yearly-rate closed form = Bell & Hinojosa 1977 eqs 1–2 (two-state land use, San Juan Island WA) → [D]→[S]. Stationarity test = Anderson & Goodman 1957 (page images) / Bell–Hinojosa power adjustment. Correlated bootstrap: autologistic (Hughes–Guttorp) + MCML (Geyer & Thompson 1992). Mechanism for widened leave-out: Burnicki 2007 — correlated error across dates raises overall change accuracy, not user's accuracy of change. K_R radii: 0.7–1.4 m building / ~20 m works (Morgenroth 2017 via Hilbert table; Guo 2018 abstract). D_k window 4–8 y (Hauer), 4–5 (Guo), 6–7 (Steenberg); replant 2–3 y (Conway 2022). Blur: GRF-offset model (Girard 2019a) + bound-as-radius precedent (Vargas-Muñoz 2019).
decided: k≈5 y as the fit's starting value only (window, not shape). Row 15 (stationarity) not runnable until a third lidar date.
killed:  Not in Sci-Hub archive (post-2017 coverage thin): Takada 2010, Besag 1974, Dai & Khorram 1998, Steenberg 2017/2018, Guo 2018/2019, Morgenroth 2017, Pedley 2025. MDPI 403 on Roman 2022 / Ock 2024 / Hasegawa–Takada 2019; Hokkaido mirror unreachable. Efron 2004 itself unobtained anywhere — 2021 restatement is the citation. Anderson–Goodman 1957 scan has no text layer (read as images). No D_k(τ) curve exists in the field; no Cox/hazard-ratio paper; no published registration-blurred label prior.
files:   Reports/LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md; Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md; Scripts/CHATLOG.md; Literture/Validation/ (+18 PDF/.txt pairs this round)
         Addendum (same day): Kam ruled Sci-Hub the STANDING fallback ("every time"); memory updated. Kam found Dai & Khorram 1998 TGRS by title on Sci-Hub (DOI/title/URL lookups from here all "не найдены") → read, PRIMARY: simulation, no closed form; one-fifth pixel for <10% change error (30 m TM); false change "mainly distributed spatially along the edges"; eq 5 = SV increase equals ACF drop at the lag. Framework §14.5 [D]: false-change fraction ≈ (2/π)·ρ_P·|s| (perimeter density × shift; Crofton form), verified numerically on disc and square; kill = self-shift test on the 2016 epoch. Kam's first upload was the OTHER Dai & Khorram 1998 (IJRS letter, 10.1080/014311698213911) — filed with a NOT_ name, not cited. Round 6 launched: disturbance-ecology delayed-mortality hazard shapes (D_k); GIS epsilon/G-band positional uncertainty (blur prior).
         ROUND 6 (same day) — the two unmoved items taken to unsearched fields. D_k shape: fire ecology has no hazard curve (Hood 2018 review: "predictions are binary"); fragment ecology gives the SHAPE in prose — microclimatic mortality declines over first few years (D'Angelo 2004, Laurance 2011), wind-turbulence mortality RISES as edge closes (Laurance 2011); distance half in Mesquita 1999 (0–20 m strongest, 40–100 m penetration). Framework §14.6: two-term D(τ) = w₁e^{−τ/k₁} + w₂(1−e^{−τ/k₂})·1[τ≤T_max] [S], all coefficients fit. Blur prior: Leung & Yan 1997 boundary r-band law 1−exp(−r²/2σ²) (eq 21) [Q]; exact point-in-polygon only bounded ("not an easy task"). Framework §14.7: π_in(d)=Φ(d/σ) [D], σ from coregistration.csv, no free parameter; rows 10/12.1/14 now share one input. Townshend 1992, Verbyla & Boles 2000 read (PRIMARY): 0.2 px rule origin; false change 5–33% by class count. Salas 2003 (perimeter/area index = §14.5 ρ_P) not in archive → library request. Review §4.15 + round-6 bibliography (21 entries); framework §14.6–14.8. Sci-Hub held 6 of 11 round-6 DOIs tried (hits: Laurance 2011, Mesquita 1999, D'Angelo 2004, Townshend 1992, Verbyla & Boles 2000, Leung & Yan 1997; misses: Laurance 1998 Ecology, Salas 2003, Shi 1998, Leung–Ma–Goodchild 2004 p2 + p4).
         Kam located Salas 2003 + a "goodchild2004" on Sci-Hub (.red storage). Salas READ, PRIMARY: P/A of change clumps vs theoretical one-pixel-strip limits (4/x diagonal, (2/x)(1+1/n) row/col); 9.55%/4.13% area-weighted bound. Different object from §14.5 (post-hoc sliver screen vs a-priori rate) → framework §14.9: premise [Q], rate [D], screen [S] with kill (must flag self-shift slivers, must NOT flag the 42 losses). "goodchild2004" = 2-page JGS editorial intro (DOI …0140-5), not Parts 2/4 — filed as such.
         ROUND 7 — Kam: "You have the ability to use sci hub to find these papers! Go get em!" `sci-hub.ren` = DIFFERENT INDEX: 8/8 outstanding DOIs resolved (`.ru` had said absent). PDFs at `sci.bban.top/pdf/<DOI>.pdf`, need `Referer: https://sci-hub.ren/` (403 otherwise), 429 on bursts >4 — fetched one at a time. Memory updated. Read all 8: Efron 2004 (3.19 conditional covariance; 3.21–3.22 Bernoulli "Steinian" = flip-difference × μ(1−μ), "requires only n recomputations"; "no general equivalent to the Gaussian SURE" except Bernoulli) → framework §15.1: per-cell Ω exact under dependence with Besag's local conditional; correlated bootstrap only for intervals. Besag 1974 (4.8 auto-logistic conditional; §6 coding methods). Takada 2010 (root via eigendecomposition; unique iff n distinct nonzero eigenvalues; negative/multiple-root failures) → §15.2 yearly root [Q], 0<λ<1 guard. LMG Part 2 (confirms gap; bounds need independent normal vertices — wrong regime for a layer offset) + Part 4 filed unread. Shi 1998 (G-band; epsilon band has no confidence relation). Steenberg 2017 (permits predict mortality both scales; 2017 ≠ 2018 paper). Guo 2018 (44% vs 13.5%; 1.4 m; >3×; CT 73.4%). Review §4.16 + round-7 bibliography; framework §15.
         ROUND 8 — Kam: "What other studies do we need the full pdf for? … establish what we know, and what we don't know." Round-7 leftover list cleared via `.ren` + bban.top (Referer; one per call): 11 PDFs filed. READ: StructN2V ("additionally hide (neighboring) pixels that contain information about the noise of the active pixel" → framework §16.1 G(t) rule [Q]); Roberts 2017 ("at least as many units as the range of autocorrelation" — second source for §12.2 block size); BCN 2002 clean copy (TV FLOW: convex C^{1,1} set with curvature ≤ P/|Ω| fades as (1−λt)⁺χ; disc extinct at t=R/2 → §16.2 three-smoother erasure table); Morgenroth 2017 = Morgenroth, O'Neil-Dunne & Apiolaza, Applied Geography (21.6% removed; <7.9 m² within 0.7 m; >20 m from driveway retained; CT 80.4%) — radii now quoted; Guo 2019 (10.84%→10.28% 2011–2015, meshblock-scale only); Steenberg 2018 EPB read: tract-level 2003/2014 regression, NO 806 / NO 6–7 y; Steenberg 2017 JEPM text HAS "re-measured 806 trees" 2007/08→2014 → the Hilbert "2018" row is the JEPM paper (print vol. 61, 2018) — §4.16.5 rewritten at the text; STAPLE negative confirmed; Efron 1986 independence statement (lineage to 2004 §3); Leung & Yan 1998 Rayleigh confirmed; Stow 1999 gradient compensation = third row-14 tool [S], not adopted; Burnicki 2010 + LMG Part 4 abstract only. MISSES: Conley 1999 indexed but storage 403 under both DOI encodings; MDPI four + Laurance 1998 not pursued (uncited). Kam: "retry if a caption blocks it" — the only captcha hit was Pedley 2025, already PRIMARY via OA. Review §4.17 + round-8 bibliography (12 lines: 10 PRIMARY, 1 ABSTRACT, 1 METADATA; Part 4 abstract on its round-7 line); framework §16 + ledger rows 4/6. Verdict: nothing load-bearing unread; remaining rows close by measurement.
         ROUND 9 — Kam: "what mathematical literature do we need to target next … other domains of knowledge can expose solutions to our unknowns" → seven fields named from the [D] list; "launch 9 sonnet agents … then read the articles". 9 Sonnet searchers (OA only; OpenAlex metered out → Crossref); reviewer fetched closed DOIs on `.ru`/`.red` (bban.top behind a Cloudflare JS challenge all afternoon — round-8 "Conley file missing" CORRECTED to bot challenge). 38 PDFs filed (Chrisman already held), 18 PRIMARY lines read, 5 ABSTRACT. MOVED: §14.5 edge-band rate = Matheron covariogram slope (Galerne 2011 Eq. 2; Eq. 1 directional for per-axis medians) [D→Q]; §14.7 σ² composition = Law of Propagation of Errors (Chrisman 1982) [D→Q], Φ(d/σ) still [D] (Kats 2019 dilation = negative); row 3 (β,γ) = Zhu–Huang–Wu 2005 spatio-temporal autologistic regression, MPLE + parametric bootstrap [Q] for EQUAL intervals, undirected in time (Hughes–Haran–Caragea 2011: centered + PL) — irregular-interval γ(Δt) still [D]; row 9 D_k·R = ETAS kernel with piecewise-constant EM estimator (Reinhart §3.2.3 on Marsan–Lengliné; Zhuang 2002 branching probabilities; Ogata 1988 form) [Q estimator / D mapping]; row 6 kill = Kaiser–Lahiri–Nordman 2012 conclique GOF [Q]; Nordman–Lahiri n^{1/3} vs Roberts range rule (different purposes); row 11a guard = Kingman 1962 Prop 2 (2×2 skeleton iff det>0, tr>1 ⟺ 0<λ<1) [Q], Israel–Rosenthal–Wei Thm 2 uniqueness, Charitos 2008 regularisation; row 2 CUSUM threshold = exact Markov-chain run length (Reynolds–Stoumbos 2000 App. C; Q matrix in the challenged 1999 paper) [Q]; Liu 2008 = §6.1 multiplicative transition in RS. Graph-cut nine filed UNREAD (row 4 unchanged). Unobtained: 12 indexed behind the challenge (3 grade-moving: Reynolds 1999, Zhu 2008, Marsan 2008); Blakemore/Page/Hall/Lahiri ch12/Matheron 1975 not indexed; Kreinin, Lewis–Mohler no DOI. Review §4.18 + round-9 bibliography (34 lines); framework §17 + ledger rows 2/3/6. Browser download of the 12 = Kam's call. → Kam: "You do have my permission for browser… use sonnet models to acquire the pdfs, and only use fable for digesting" + allow rule `mcp__claude-in-chrome__javascript_tool`. Sonnet agent passed the Cloudflare check once in Chrome, then a same-origin fetch script pulled the batch (hybrid: browser for the cookie, script for the files). 10/12 landed + header-verified; Steiner 2000 and Conley 1999 failed (partial .tmp). READ: Reynolds–Stoumbos 1999 App A (states (i−1)/m, t=m·h_B, down 1 / up m−1; Eq. 7 corrected-diffusion closed form for h) → row 2 fully [Q]; Zhu–Zheng–Carroll–Aukema 2008: STARM modified "so that the conditional distributions depend only on the past" — FORWARD chain + MRF, MCML with Fisher SEs, AIC for S/L → row 3 forward chain [Q], only irregular intervals [D]; Marsan–Lengliné 2008 MISD two-step iteration confirmed at source. Zheng 2008 / Caragea 2009 / Brook–Evans / Cabo / Liu–Cai / Cai / Melgani ABSTRACT. Review §4.18.10 + bib (44 lines: 21 P, 12 A, 9 unread, 2 M); framework §17.10 + ledger rows 2/3. Other mirrors probed: .box 403, .wf browser-check, Anna's Archive .org/.se unreachable, .li parked, .gl browser-check.
         ROUND 10 (launched) — Kam: "assess what we don't know based on what we know" → "Write into the framework, and launch sonnet agents". Framework §18 + ledger rows 16–23 (second-order gaps): hidden state = rows 1+3 one estimator (identifiability from 𝒞); irregular intervals + misclassification = multi-state panel models (msm); rate attenuation under misclassification; kernel as distributed-lag GLM (cloglog; DLNM); CUSUM under dependence (chart residuals) + multiplicity (FDR over cells); β vs resolution (measure); target erasure radius from 2020 crown sizes vs residual blobs (measure); registration covariate in the emission (design + §14.5 kill). Four Sonnet searchers launched: hidden multi-state/misclassification; DLNM + discrete-time Hawkes GLM; SPC autocorrelation + many streams; unsupervised accuracy estimation (Dawid–Skene/Hui–Walter). Sonnet acquisition agent re-sent for Steiner 2000 + Conley 1999 (OUP bronze OA in browser; cookie-then-fetch; Anna's Archive .gl).
         ROUND 10 (results) — 4 searchers back; Steiner 2000 + Conley 1999 obtained by the browser agent (Steiner via cookie-then-fetch; Conley via the viewer's native download); Lu–Reynolds 2001, Psarakis 2007, Almon 1965, Dawid–Skene 1979, Begg–Greenes 1983 from the first index. MOVED: row 17 [D→Q] Kalbfleisch–Lawless 1985 + Jackson 2011 msm (likelihood = product of P(t_{j+1}−t_j) entries; e_rs misclassification matrix, covariates allowed) + Bureau 2003 binary CT-HMM; row 18 [D→Q] Rosychuk–Thompson 2003 (naive estimators overestimate transitions; bias-adjusted estimators); row 19 [D→Q] Gasparrini 2010 cross-basis W=QC + Truccolo 2005 Bernoulli-logit GLM equivalence — kernel fitted as a lag×distance regression, EM unnecessary; row 20 [S] Lu–Reynolds 2001 caveat (observation charts ≈ residual charts except high autocorrelation + large shift → correlogram decides), Mei 2010 sum-of-local-CUSUMs under global false alarm, Xie–Siegmund mixture ARL, Steiner risk-adjusted CUSUM = ℓ_{t,b}; row 16 identifiability [Q] Platanios 2014 (three independent-error approximations), Parisi 2014 rank-one covariance. Reviewer's own error caught by a searcher: a fabricated 'Browning … R. Soc. Open Sci.' citation in the brief (real paper: PLOS ONE 2021, Rivoirard not Simpson). Review §4.19 + round-10 bib (38 lines); framework §19 + ledger rows 16–20. Browser agent out for 7 leftovers (Hui–Walter, Mousavi 2009, Foody 2010, Alwan 1988, Montgomery 1991, Lu 1999, Schwartz 2000).
         ROUND 10 (leftovers) — browser agent: 6/7 obtained (Hui–Walter, Mousavi–Reynolds 2009, Foody 2010 via the Nottingham repository, Alwan–Roberts 1988, Montgomery–Mastrangelo 1991, Lu–Reynolds 1999); Schwartz 2000 absent from both indexes. Mousavi–Reynolds 2009 CHANGES row 20: Bernoulli CUSUM not robust to autocorrelation, adjusting limits "not an efficient approach" → Markov binary CUSUM (LLR under the two-state dependent chain, exact by Markov chain) [Q] — supersedes the §19.3 correlogram-decided regime. Hui–Walter two-population identifiability → row 16 second route. Review §4.19.5 + bib (39 lines: 17 P, 15 A, 4 unread, 2 M, 1 held); framework §19.6 + ledger row 20; narrative Step 6 updated.
         ACQUISITION PASS (close-out) — Kam: "locating full papers for any articles we cited and never got the full paper … Send sonnet agents"; then "the chrome browser should be the last method since its slowest" (route order rewritten mid-run: OA → .ru → .ren by curl → ONE browser batch last; memory updated). 4 Sonnet agents, 64 targets: 47 obtained + header-verified (RS time series 12/17; canopy/ML 11/16; accuracy + urban forestry 16/16 incl. Laurance 1998 resolved via Mesquita's references to Ecology 79(6):2032–2040; stats 8/15 incl. Allard 2007 DOI 10.1137/060662617 confirmed). Bibliography: 47 lines annotated 'Obtained … unread by the reviewer' (grades unchanged); Roman 2022 duplicate line's authors resolved. Not obtained 17 (3 closed on neither index; 3 OA behind publisher bot checks; 3 too recent; Mishra nowhere; Page/Schwartz + 4 books after a browser permission denial). Concurrency lesson: four agents on one Chrome profile contended (tabs cycling, a /tmp collision, one mis-saved file caught and deleted) — run browser-capable acquisition agents ONE at a time.
         PDF LOSS + RECOVERY — discovered during close-out: 149 PDFs (everything older than ~17:13) gone from Literture/Validation; .txt extracts intact; Recycle Bin empty (shell delete); no delete command found in any agent transcript. Recovered 6 from Downloads by text match; 143 re-fetched by DOI (3 curl-only Sonnet agents: 46+47+28; then 1 browser-last agent: 20/20; then Steiner+Conley whose only extracts were .raw.txt: 2/2), every file verified against its surviving extract; manifest DOI errors from my surname/year fill caught by the agents (Higham–Lin, Parisot, Averkov, BoykovJolly, Mesquita, Valavi). Folder whole: 199 PDFs. Lessons → memory + docs/LITERATURE_CONVENTION.md: acquisition agents get no delete rights; verify by content; browser LAST and ONE browser agent at a time; top-level navigation to ?download=true is the reliable browser download.
         CLOSE-OUT (Kam: Sonnet does the tidying, Fable orchestrates; briefs/findings integrated into the project workflow) — Reports: MATH_NARRATIVE (inputs→outputs), GATED_PLAN (11 gates, failure modes, sourced fallbacks), HANDOFF_SPATIOTEMPORAL_DATA_SESSION (reading order, first 7 measurements, decisions), lit_spatiotemporal_bibliography.csv (292 lines / 268 works, grades, superseded links), lit_stem_rename_map.csv. Folder: rename pass to Surname_Year_slug (199 stems, 7 collisions a/b), manifest.csv with sha256. Workflow hooks: WORKPLAN row → handoff §4; README links; decisions.yaml `canopy-floor` (Kam 2026-09-12: ~2 m trees are not canopy; mask adopts lidar h≥5 m floor pending his value); docs/LITERATURE_CONVENTION.md. Tracker: 250 works appended as IDs 210–459 (Read/To Read/Not Obtained), 12 phase rows, temp sheet removed; flag: Dai&Khorram DOI digit mismatch vs ID 21. Branch ready for Kam to push/merge; PDFs do not travel with it.
         TRACKER QA (Kam: cells confusing — directional refs like 'above', placeholder titles; 'better data collection'; then an adversarial pass by Opus at reasonable tokens) — Sonnet completion pass (7 placeholder titles from Crossref; 13 Relevance rewrites incl. 4 cells holding another paper's text; 11 DOIs normalised) → Opus referee (27 tool calls; sweep of all 250 + 54 rows checked against manifest/Crossref/review: NO invented content; systemic defect = 119 provenance-boilerplate Relevance cells, 61 byte-identical, positional set references, 3 truncated titles, 1 self-contradicting cell (283), 26 Read-without-PDF, 22 empty venues; manifest Locke DOI wrong) → Sonnet fix pass (123→0 boilerplate, 34→0 positional, 8 rows downgraded to To Read, 22 venues filled, ID 460 Locke added, manifest DOI corrected) → orchestrator re-check (2 residual cells fixed: 412, 417). Standard saved to memory `literature-tracker-cell-standard`.
         DECISION (Kam): small ~2 m trees are not canopy ("akin to shrub and doesnt provide canopy services") → canopy has a floor; framework §20 adopts the lidar certification floor (h ≥ 5 m) for the mask unless Kam sets another value. Settles: spatial coupling legitimate; row 22 target = smallest crown at/above the floor from 2020 polygons × lidar height; growth = definitional gain (no third state, one near-floor stratum); 2–5 m uncertified band is intended. Open: the floor's value; the mask's implied floor (min component size in threshold_and_clean vs crown sizes).
         MATH NARRATIVE — Kam: "start to finish compile the mathematical narrative … lay out the inputs, then walk through the manipulations using the math we have found" → `Reports/MATH_NARRATIVE_SPATIOTEMPORAL_CONSISTENCY_2026-09-12.md`: §1 inputs table (one home each), Steps 1–7 (emission → lidar-anchored rates + yearly root → chain/STARM → priors as regressors → smoother erasure table → CUSUM on certified populations → Efron/Steinian + G(t) + Brier identity + conclique GOF), §9 order of operations with kills, §10 what is still ours, §11 symbol table. Every formula carried from the framework with its grade; no new numbers.
next:    Read LMG Part 4 (filed). Remaining unobtained (none load-bearing): Roberts 2017, Conley 1999, StructN2V, STAPLE, BCN 2002 clean, Laurance 1998 Ecology, Barker 2022, Roman 2022, Ock 2024, Hasegawa–Takada 2019 — try `.ren` for these next session. Kam: 𝒞 + LOSS rules; smoother decision; §15.1 kill on a synthetic autologistic field is now the cheapest validation on the table. Read Burnicki 2011 (filed, unread). Kam: 𝒞 + LOSS rules (11b); smoother decision (row 4); rows 1–2 CPU jobs; §14.7 kill on the 2016 CHM is a cheap first measurement.

## 2026-09-12  LIT ROUND 4 — ledger rows 4/6/9/10 taken to Stein theory, TV-L1 geometry, point processes (Sonnet search, Fable read)
goal:    Kam: search other mathematical domains for framework rows 6 (penalty under correlated error), 4 (erasure radius, non-linear), 9–10 (prior free params). Sonnet searches, Fable reads full text.
did:     3 Sonnet searchers, OA routes only → 22 works, 16 PDFs filed `Literture/Validation/` (+ .txt). Fable read 10 at load-bearing passage (Hudson 1978 + Hwang 1982 as JSTOR page images; Vixie p.13 image).
         review §4.13 (4.13.1–4.13.3 + negatives), §5 items 2/3/7/11 narrowed, §5 box line, §7 coverage bullet, §8 "round 4" bibliography block (reviewer-read vs searcher-read marked). framework §13 (13.1–13.4) + ledger rows 4/6/9/10 rewritten.
         Findings: (6) NO unbiased-risk identity for correlated binary obs — PRIMARY negative: Hudson §3 + Hwang eq 2.1 independence-only; Eldar Thm 1 + Chaux Prop 1 Gaussian/continuous-only. Survives: Efron identity w/ CORRELATED parametric bootstrap [S]; leave-one-epoch-out widened to correlation group G(t) [S]. Row 6 → two correlograms on strata (spatial; cross-epoch). (4) TV-L1 erasure EXACT: disc radius R removed whole iff λ<2/R (Chan–Esedoglu §3, Duval §5.1, Vixie n/λ); TV-L1 = opening + perimeter/area test (Duval) → row 8 φ ties to opening radius. Mean-field CRF: no erasure result (PRIMARY negative). Potts flip R<2β/m is [D], in no paper. (9–10) Baddeley&Turner: canonical A by pseudolikelihood, irregular R,k by profile likelihood; NHMM-EM alternative (Hughes–Guttorp, ABSTRACT). Hilbert 2019 names permitting data as unused covariate (→ Steenberg 2017 lead). No joint distance×time hazard; no registration-blur prior form.
decided: row 4 now a smoother CHOICE (TV-L1/opening closes it; mean-field keeps it measurement). Rows 9 and 11b = same LOSS data build.
         Sci-Hub pass (Kam added allow rules; works only as ONE bare `curl …` per Bash call — compound commands still hit the classifier): mirrors .ru/.ren/.box/.wf up, .se/.st DNS-dead. Held 3/10: Hughes–Guttorp 1999, Verburg 2004, Gallagher–Wise 1981 → read, PRIMARY. Hughes–Guttorp = our q·exp(covariate) transition form, published + EM (§6.1 form is theirs; covariate ours). Verburg F = neighbourhood share / study share; R = d at which F→1. Gallagher Thm I: runs ≤N erased, 2N+1 window.
killed:  Efron 2004 own assumption statement NOT re-read (no OA copy; not in Sci-Hub) — flagged in §4.13.1/§13.1; verify before relying. Not in Sci-Hub archive: Efron 2004, Roberts 2017, Conley 1999, StructN2V, STAPLE, BCN 2002, Allard 2007 (DOI 10.1137/040604297 resolves to Chan–Esedoglu, not Allard). Steenberg 2017 not located by title. BCN 2002 author-page PDF UNREADABLE (font encoding). Vincent 1993/Maragos 1989 no DOI route.
files:   Reports/LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md; Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md; Scripts/CHATLOG.md; D:\edmonds-pipeline\Literture\Validation\ (16 new PDF/.txt pairs)
next:    Kam: allow rule / `!` for Sci-Hub remainder; Chrome download for the 3 bot-walled OA papers (needs explicit yes); re-read Efron §2 once a copy lands. Decide smoother (TV-L1 vs mean-field) before (β,γ) fit.

## 2026-09-12  FRAMEWORK §12 — where (r,f) come from; 4 derivations, ledger rows 2+5 closed in form (Fable 5.1)
goal:    Kam: "establish what we know and don't know mathematically, then solve what remains." Framework §2–§5 consume (r_t,f_t) as known; only C-CAP rates exist, biased, detector sensitivity 1/f. Derive lidar-anchored rates at every epoch.
did:     `Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md` §12 (after §11, dated), all [D] UNVALIDATED:
         - §12.1 band-stratified emissions (r_{t,b},f_{t,b}), PACC's 5 bands. Motivation: MASTER §3a pilot — 0–2 m band f≈0.16–0.26 vs ~0 interior (pilot's own caveat kept). FLAT eroded 6 m → no anchor in bands 0–4 m; erosion radius should be coregistration p95, not round number.
         - §12.2 decaying-anchor estimator: a_k=π₀+π₁λ^k, c_k=π₁+π₀λ^k, 2×2 system det=λ^k, f̂,r̂ closed form; var ×1/λ^{2k} (4× at half-life); bridge weight a_k·a_{K−k}/a_K for 2009–2015; naive bias ≈k·q_g·(r−f) upward; (q_g,q_l) closed form from GAIN+LOSS fractions per population/band (λ=(1−Q_g−Q_l)^{1/K}); k in calendar years not chain steps. Kill: 2005 full footprint → propagate 11 y → must reproduce direct 2016 rates, must FAIL under q×10. 2016 epoch present in YEAR_CATALOG (checked).
         - §12.3 CUSUM: blind gain chart on always-canopy cell drifts UP at KL(Bern(r)‖Bern(f))≈1.18 nats/epoch → misspecified. Charts only on certified-start populations (ℱ gain, 𝒞 loss); two-sided problem dissolves; uncertified cells use chain posterior argmax. Row 2 → 1 Monte Carlo per (population,band,α).
         - §12.4 leave-one-epoch-out identity: y_t=(x_t−f)/(r−f) unbiased for z; cross term vanishes (x_t leaf | z_t); true Brier = observable − [π r(1−r)+(1−π)f(1−f)]/(r−f)². Floor 0.76/0.15 at brief rates → stratum means only. Two metrics (Brier here, Efron counting §5.1). Kill: leaking layer must score below floor.
         - ledger: row 2 resolved-in-form, row 5 derived, row 11 split 11a (estimator, derived) / 11b (𝒞 + LOSS populations, NOT built), new 13 (banding, unmeasured) + 14 (erosion vs coregistration p95). §1 revision bullet. All worked numbers re-computed numerically this session (KL, y, floors, identities, estimator recovery, q round-trip) — self-check of arithmetic only, not validation.
decided: estimator needs 𝒞 (PACC A_can rule: lidar canopy both clouds) + LOSS (GAIN mirror `both & (h05>=5.0) & (h16<2.0)`) — two rules in `certified_flat_scoring.py` family; SPEC only, code not touched (Kam's call, pipeline branch). Populations before ledger rows 1–2 (rows need lidar-anchored rates).
killed:  "no certified-canopy population exists" (yesterday's claim) — wrong; PACC pilot built A_can on trend8_stack_2m.npz (MASTER §3a item 1), not in pipeline code. Per-epoch scalar (r_t,f_t) — misspecified at edge per PACC pilot; banded.
files:   Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md (§1 bullet, ledger, §12); Scripts/CHATLOG.md
next:    Kam: build 𝒞 + LOSS rules (11b) on pipeline branch; run §12.2 kill (CPU, files exist); row 14 read coregistration p95; row 13 PACC band re-run on 12 tags; then rows 1–2. Row 12 reader still owed.

## 2026-09-11  LIT REVIEW VERIFIED + ROUND 3 + FRAMEWORK — 31 papers read, 12 gaps ledgered (Sonnet 5 → Fable 5.1)

goal:    Kam: "get the pdfs, internalize, set the record straight" on
         `LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md`; then "transition
         to framework and method … theoretical and mathematical problems we have
         yet to consider."
did:     paper-search-mcp installed as MCP + skill (uv tool; pinned `mcp<2`,
         v2 broke `FastMCP` import). Round-2 verify: 10 flagged citations
         fetched full text (PLOS/PMC/HAL/GFZ/UC-Canterbury/USDA
         Treesearch/Copernicus; Sci-Hub for 2 IEEE/Elsevier-locked). 8 -> PRIMARY.
         Corrections landed: Abercrombie&Friedl "90/10÷(K-1)" matrix = invented
         gloss (paper: constant p=0.1; it DOES validate vs PRODES change);
         Capliez "7-12 F1" misattributed (real unadapted loss 15-18); King&Locke
         = one product's method, not field convention; Martinis&Twele gates
         WHICH cells not HOW MUCH; Guo 1.4 m = CART split, not radius.
         Round 3: 4 adjacent-field threads, 21 works, 16 PRIMARY -> §4.12.
         No gap closes; 3, 7, 10, 12 narrow. Framework doc written: one energy
         E(z)=unary+β·space+γ·time, every equation binned [Q]/[S]/[D], 12-row
         gap ledger, 3 derivations ours (∂ℓ/∂f=−1/f; IGNORE half-life
         ln2/(q_loss+q_gain)≈35 epochs at q_loss=0.02; 42-loss kill resolves
         Δ≳0.12 only). Convention fixed doc-wide: r = recall (round-3 agents
         used miss rate). Code check: prob raster kept per epoch (uint8
         0-254, 255 nodata, `core.py::step_inference`); float logits never
         written. Commits 7d1df07, 56c8e19, 08bfd08 on
         `docs/lit-review-spatiotemporal-consistency`.
         close-out: `check.py --fast` ruff+compile PASS; pytest rung 5/1932
         FAIL, all pre-existing, 0 from this session: `backbone_benchmark.csv`
         + `harm_spread.csv` "STALE" = CRLF-vs-LF byte diff (worktree checkout
         has CRLF, renderer emits LF — line-ending config, not content);
         `crown_state_intervals.csv` pointer, registry 2 manifests behind
         (20260910T154530Z / 20260911T041021Z 2020_in16), SCIENCE.md curves
         130→139 = this docs branch behind `work/20260906-healing-tool` + lake.
         Not regenerated here (wrong branch for lake harvests). `landed.py
         --dry-run`: mechanical rungs = lake harvests, skipped for docs
         milestone; CHATLOG rung clean.
decided: raw-logits patch HELD — emission model (K-bin vs log-odds) decides it
         analytically, not preference (framework §2.3, ledger row 1). Lidar =
         benchmark/calibration only, never input (H2 precedent). Buildings
         soft prior, not veto (King&Locke). Sci-Hub last resort only, OA first.
killed:  "MASTER vs review contradiction on Hoberg 2012" — not contradiction:
         pdftotext drops Symbol-font β/γ glyphs; MASTER's "full text obtained"
         = pdftotext ran, review's "would not parse" = unusable; pypdf reads it.
         2 agent launches denied by auto-mode classifier (Sci-Hub step) ->
         relaunched OA-only, both succeeded via Unpaywall->UC repo.
files:   `Reports/LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md` (§4.12,
         §5, §7, bib), `Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md`
         (new), `Reports/TEMPORAL_SPATIAL_CONSISTENCY_BRAINSTORM_2026-09-10.md`
         (§8 pointer), `D:\edmonds-pipeline\Literture\Validation\Abercrombie_Friedl_2016_*.pdf`.
next:    ledger rows 1+2 first (CPU, files on hand): K-bin emission audit on
         certified cells; MC CUSUM thresholds at n=12 with per-year (r_t,f_t).
         Row 11: lidar-referenced rates do not exist. Row 12: one reader
         re-derives §2.1-2.2 with r=recall. Unsearched: survival analysis
         (§4.2 prior), MacFaden 2012/UVM (roof convention). WORKPLAN board row
         = Kam's call. Sci-Hub tools land after Claude Code restart.

## 2026-09-02  HANDLE-FREE CONTROL CERTIFIED — 4 fire drills, 4 real bugs, ALL PASS (Fable 5)

goal:    Kam: prevent/regain runtime control after CLI-handle death (all 3
         Phase-A staging handles died mid-flight while VMs kept working);
         "iterate through this drill again. We need it work flawlessly."
did:     control plane moved OFF handles: `vm_ops sessions` (account census,
         wraps `colab sessions`), babysitter RULE 4 Drive mailbox
         (status|stop, nonce-once, no-arbitrary-code) + `vm_ops cmd`, browser
         attach URL persisted at launch. Fire drill = repo instrument
         `qc/instruments/vm_control_drill.py` (--yes, one T4, 10 asserted
         stages incl. INDUCED handle death via sessions.json strip). Four
         drills run, each caught a real defect: (1) mailbox status leaked
         ANOTHER session's queue log (shared logs dir bare glob) -> queue-stem
         scoping; (2) census lags unassign ~15 min (watchdog fired ON schedule;
         observation channel slow) -> breadcrumb-first reap detection;
         (3) THE BIG ONE: every RULE-1 beacon resurrection self-diverted to a
         __conflict heartbeat (collision guard could not tell same-VM dead
         predecessor from foreign runtime) — telemetry silently maimed since
         the feature landed; drill 1's "Drive debris" attribution CORRECTED
         -> same-host takeover in name_is_ours + NO_CONFLICT_DIVERSION drill
         stage; (4) registry gate flickered on mirror-lagged heartbeats ->
         60 min campaign window. DRILL 4: ALL PASS 10/10. Commits 52fa08e,
         7aa26e5, 63715a3, 48efdfb, d1beda8, 5ba530b.
killed:  "conflict copies are Drive sync debris" (drill 3 proved otherwise);
         fixed 45 s resurrection wait (raced the 30 s poll boundary).
next:    Phase A staging: A done 7/7; B+C alive (census+heartbeats), ledgers
         mirror-lagged. When staged: Phase B on 2xA100 (queue steps
         train,evaluate then inference w/ --infer-aoi) — VMs get the full
         certified control stack. check.py pytest rung still shows a rare
         pass-on-retry flicker beyond the registry gate; source unidentified.

## 2026-09-01  POLICY C LANDED — dense sweep, plateau selector, pilot masks re-cut (Fable 5)

goal:    Kam: "Let's go with C." Build per-year independent threshold selection,
         prove it end-to-end on pilot arms, pre-register 36-run.
did:     dense u8 sweep in `phase4_qc_indep._write_dense_sweep` — 2x 256-bin
         histograms -> EXACT curve at all 254 cuts, one scan. Immediately
         earned keep: F1 peak ~0.14, FAR below coarse sweep's 0.40 floor, on
         plateau flat within 0.005 across 3x range. Selector
         `qc/instruments/select_indep_threshold.py`: criterion
         f1_plateau_hi_d005 (highest k within 0.005 of peak — precision end of
         metric-indifferent plateau; strict argmax = sloppy recall edge).
         Registry `phase4/qc/indep_thresholds.csv`. Selected (after review fix
         below): 2011s k=81 (0.3189, rec .7625/prec .7552; was rec .499
         @0.643); 2006s k=86 (0.3386, rec .7195/prec .6848; old 0.4743 sat on
         probability CLIFF — recall .68->.42 across 0.45->0.50).
         Ref-sensitivity vs 2016 C-CAP: 0.05-0.10.
review:  13-agent adversarial workflow on the two new code paths — every fix a
         CONFIRMED reproduced finding (commit fce0162). Load-bearing: float64
         plateau compare excluded the row exactly 0.005 below peak (fired 3/4
         sweeps, picks were k=80/85 — one step recall-ward of the rule);
         tick-exact compare now. Also: sweep thresh column floored; nodata
         masked pre-clip; truncated-sweep refusal; atomic registry write.
         Masks re-cut AGAIN at corrected picks (recutC2, free CPU);
         EQUIVALENCE PASS both rounds.
         Masks re-cut on free CPU VM (recutC, registry-read thresholds, never
         hand-typed); EQUIVALENCE PASS (mask within 0.001 of registry rows).
         Quantization fix: floor-truncate thresh (rounded 6dp crossed u8
         boundary — scorer cut k+1 while production cut k). Ledger live rows
         now policy-C. Engine UNTOUCHED (--infer-thresh deploys). Overlay
         delivered (overlay_2011s_policyC.png). Commits 5088ad9, fd70834.
decided: plateau-high criterion (measured rationale in selector docstring);
         36-run = 34 arms + ADOPT 2 pilot arms (~4-6 A100-hr saved) —
         `experiments/full_archive_e3.yaml` status queued.
files:   qc/phase4_qc_indep.py, qc/instruments/select_indep_threshold.py,
         docs/SCHEMAS.md (2 new contracts), experiments/full_archive_e3.yaml,
         phase4/qc/indep_thresholds.csv, run_registry (2 recut rows).
next:    KAM: 36-run launch (GPU gate ask pending: 2xA100, ~65-70 A100-hr).
         Adversarial review workflow on selector code in flight. Post-GPU
         cleanups queued (kernel units, GPKG area_m2). --anchor-labels A/B
         candidate experiment.

## 2026-09-01  RECIPE DEEP-DIVE — threshold only large knob; morph/sieve NEUTRAL (Fable 5)

goal:    Kam: "are we leaving anything obvious on the table like sieve that has
         a large impact?" Audit every recipe stage before 36-run spend.
did:     new instrument `qc/instruments/postproc_variant_score.py` — scores
         production mask semantics (real `threshold_and_clean` + sieve) vs C-CAP,
         ledger-safe. Validated: shipped 2011s mask scored PIXEL-IDENTICAL to
         replica (tp=60,497,713). Measured: threshold sweep 2011s 23 recall pts
         (0.643 chosen circular vs 0.45; canopy AREA 1264 vs 1942 ha = 54% swing);
         morphology NEUTRAL both years incl. 3 m-kernel 2006s (+0.31/-0.17);
         sieve moves 0.016% px. 2020-label uncertainty band measured: 5.2% of
         valid px in model's own 0.4-0.6 band, recipe asserts hard 0/1 on all.
         CSV `phase4/qc/postproc_variant_scores.csv`; narrative
         `Reports/RECIPE_AUDIT_2026-09-01.md`. Commit `aca79eb`.
decided: no postproc edits before Kam's threshold call (provenance); ledger line
         for instrument's one path-insert (precedent: phase4_sector_poststrat).
killed:  "3 m morphology eraser" framing — measured neutral, open+close cancel.
         Sieve suspicion — clean post-EPOCH-3, and mask raster never sieved anyway.
files:   Reports/RECIPE_AUDIT_2026-09-01.md, phase4/qc/postproc_variant_scores.csv,
         qc/instruments/postproc_variant_score.py, qc/test_status_discovery.py,
         WORKPLAN.md row 6.
next:    KAM: threshold policy A/B/C (C recommended) — the ONE gate left before
         36-run. Post-GPU cleanups queued: kernel ground-units, GPKG area_m2
         CRS-unit bug (~30/36 years), redundant vector filter, stale comment.
         Candidate experiment: --anchor-labels A/B on 2011s (~2-3 A100-hr).
         Full ladder (not --fast) before any Colab push.

## 2026-09-01  HARD-YEAR PILOT COMPLETE — recipe hypothesis confirmed (Fable 5)

goal:    the pre-spend gate before the 36-run: are the worst years bad recipe or
         bad imagery? Two arms, rule pre-registered before launch.
did:     2011s 0.471 -> 0.756 f.5 (ABOVE the 0.72 line — recipe CONFIRMED);
         2006s 0.470 -> 0.707 (UNDETERMINED band per rule; residual matches its
         three measured strikes). Verdict in experiments/hard_year_pilot.yaml;
         spent generated queue deleted; mining refreshed with the fresh arms.
         The RIDE was the other experiment: 4 A100 launches survived a FUSE-race
         evaluate crash (tile valid seconds later), 3 beacon deaths (queues kept
         working — beacon bug, cosmetic), 1 guard/split collision (my surgery vs
         the duplicate-tag guard: ~2h idle A100, owned), 1 unverified-checkpoint
         resume denial (safe-by-design re-train). ZERO corrupt artifacts, zero
         silent errors. Reliability answer built the same night: vm_babysitter
         (Tier 1, NO model per Kam) + campaign-aware registry gate + vm_ops
         --queue-args. RECOMMENDATION to Kam: GO for the 36-run, 2006s flagged
         low-confidence + first for degradation synthesis. Decision is Kam's.
next:    Kam: 36-run go/no-go (the ladder's final gate is passed). CU balance
         after-read settles the measured rate on whichever launch he approves.

## 2026-09-01  EPOCH 3 MASKS REGENERATED — 4 parallel free CPU VMs, 19+1 arms

goal:    regenerate every champion + pilot mask under the 3.0 m² TRUE sieve.
did:     Kam's correction applied ("parallel CPU runtimes") -> 20 pairs sliced
         across epoch3/b/c/d (CPU tier = 0 compute units), heavies split. Serial
         attempt first found a LIVE bug on pair 1: step_postproc read `nod` after
         the threshold_and_clean extraction moved it — NameError reachable only
         by real postproc; fixed `e471773` + static scope gate; failed attempts
         kept in registry as provenance. Parallel run: 19/20 OK in ~2.5 h wall
         (2022 65.9 min the pole). 20th = 2023n untagged champion: the engine's
         untagged-overwrite guard REFUSED correctly; re-run --allow-overwrite on
         a fresh VM. min_patch printed 3.0 m² everywhere (9 px NAIP -> 1,194 px
         5 cm Mercator; foot years 48 -> 299 px = the ft² bug's 6.2x, gone).
         FREE regression proof: 2019n pilot_e2_coarse reproduced EXACTLY 12,682
         polygons — UTM years were always right, so EPOCH 3 changed them not at
         all. landed.py absorbed 20 manifest rows. All VMs self-stopped.
         2023n RETRY OK (2.4 min, --allow-overwrite, epoch3g) -> 20/20. EPOCH 3
         COMPLETE: every champion + pilot mask cut at 3.0 m² true. Lesson kept:
         the grep-chained exec on epoch3f hid a failure AND stopped the VM early —
         same swallowed-evidence class as tail'd pipes; capture full exec output.
next:    (none for EPOCH 3.) Open science items: co-registration table, the
         Olofsson area-estimation campaign (needs Kam's photo-interpretation).

## 2026-09-01  EPOCH 3 — sieve re-baselined to 3.0 m² TRUE (Kam: "lets do 3m^2")

goal:    kill the 11.6x minimum-mapping-unit spread (0.279-3.24 m² by CRS family —
         "3.0 m²" read as ft² on 15 survey-foot years).
did:     `01b1de7`. sieve_min_px divides by TRUE-m² pixel area; MMU spread now
         integer-px quantisation only (3.0-3.999 m²). EPOCH 2 -> 3 (not in
         _tile_signature — no re-tile). Geometry table + passport columns
         regenerated; parity gate follows the live function. Census Class-B entry
         struck RESOLVED (history kept) + census correction: _crs_unit_m DOES
         handle 3857 (cos-lat) — reported hectares were already ground-true.
         STATS_CHECKLIST item 7 -> RE-BASELINED. Local postproc canary hit the
         documented fork/Windows wall -> batch rides a CPU Colab runtime (ZERO
         compute units, the one sourced-free tier): vm_ops gained a CPU choice;
         20 (year, tag) pairs = 17 champions + 3 pilot arms, nohup-detached,
         log epoch3_postproc_batch_*.log, watchdog self-stops.
next:    verify batch DONE ok=20; then landed.py (registry rows for the re-runs
         come from manifests). Pilot Atlas mmu column already shows EPOCH 3.

## 2026-09-01  IMAGERY GEOMETRY MEASURED — 4 CRS families, 17 files in FEET (Fable 5)

goal:    Kam: authentic imagery facts, stored so future contexts find them; wrong
         projections "drove stats" before. Items 1-4 approved.
did:     `87bbb76`. imagery_geometry.py -> phase4/qc/imagery_geometry.csv (36 rows,
         rasterio-measured): CRS, unit, naive-vs-TRUE-GROUND pixel size, origin
         alignment, extent, bands, nodata, catalog flags. Instrument's FIRST RUN
         re-derived the founding trap (+48.9% naive on all 13 EPSG:3857 files =
         1/cos(lat)) -> both numbers are now columns. MEASURED: 4 CRS families;
         2285 x15 + 2926 x2 (US SURVEY FEET, 17/36); 3857 x13; 26910 x6 (only
         honest metres). Catalog: ZERO disagreements. nodata declared on 6/36
         only. config.ANALYSIS_GRID_EPSG=26910 appended (declaration, not
         resampling — 3.7 stands) + gates. docs/CRS_CENSUS.md (gated): every
         stats-bearing CRS site by symbol, incl. the two BY-DESIGN exceptions
         (MIN_CANOPY_PATCH sieve, inflated phase-0 crown areas). CLAUDE.md 3.4b:
         the measurement contract (instrument -> measured CSV -> gated finding).
         IMAGERY_FACTS 14 = the finding; SCHEMAS.md = the table contract.
         Also: colab CU balance anchor MEASURED via Kam's browser (173.39 CU
         @ 03:45Z, verbatim in colab_rates.csv) — next launch settles a rate.
next:    grid-congruence arithmetic on the 2019s/2019n class is now one query;
         Kam's calls unchanged (main, tag).

## 2026-09-01  AGENTIC WORKFLOW 7/7 — lifecycle as code, checklist as command (Fable 5)

goal:    Kam: "what remains a problem for agentic workflow... go for all 7"
         (billable time granted).
did:     7 `0deb3d0` lake.read_retry — ONE home for retry-the-answer, pilot_gate
         delegates (3/3 live). 5 same commit: bench covers evaluate/postproc —
         postproc.threshold_and_clean EXTRACTED pure so the bench regresses real
         code; +6 metrics; MATCH x2. 2 `7976cc5` qc/landed.py — 3.12 is a command;
         my own 2 hand-typed canary rows had INVENTED run_ids, replaced by
         manifest-derived; gate asks the tool its own question (0 new). 4 `a727bce`
         qc/experiment_queue.py — queue yamls GENERATE from experiment files,
         drift-gated. 1 `f94fba6` pipeline/vm_ops.py — launch/exec/status/stop
         with the CLI lock, three-state signature verify, token cleanup,
         backoff; PROVEN LIVE on T4 (~4 min): all signatures, heartbeat, clean
         stop. 3 `4c546a7` queue split 1,629 -> 973: queue_verify.py 478 +
         queue_ledger.py ~300, q-context routing preserves all 52 monkeypatches
         (3 subtleties caught by the suite: patched intra-cluster call, shared
         _MERGE_DEFECTS list, q.io module-object patch surface). 6 BLOCKED ON
         EVIDENCE by colab_rates.csv's own correct rules — procedure documented
         there; Kam reads CU balance before/after any launch to settle a
         MEASURED row.
decided: queue guards cluster stays in the queue (main's own surface). vm_ops
         prints 3.4 policy reminders, never bypasses them.
killed:  committed once over a red ladder (tail'd pipe, again) — pipefail now in
         every ladder chain; it caught the very next stray import.
files:   vm_ops.py queue_verify.py queue_ledger.py landed.py experiment_queue.py
         bench.py lake.py + tests
next:    Kam: main merge + tag + one CU-balance read. The repo's agentic loop is
         now: experiments/x.yaml -> experiment_queue -> vm_ops launch -> pilot_gate
         --experiment -> landed.py.

## 2026-09-01  R&D FLEXIBILITY — six agentic-workflow seams landed (Fable 5)

goal:    Kam: "flexible for research and development... what if I wanted to
         implement a different architecture." All six proposals approved; order
         mine (seam -> substrate -> consumers -> protection).
did:     `448b881` ARCH seam: ckpt.ARCHS registry + contract test parametrized
         over it (new arch = one builder + one dict line + check.py; 11 arch
         tests). `ad2c2e7` STATUS.json via pipeline_status --json + anti-rot gate
         (agents query, never parse markdown). `3271caa` docs/SCHEMAS.md — every
         data contract, writers cited BY SYMBOL, gated. `7276f59` experiments/
         one yaml per experiment (hypothesis/arms/decision rule BEFORE results/
         verdict); pilot_gate --experiment gates ANY of them (pilot re-verified
         3/3 through the new loader); schema gate incl. registry provenance for
         complete experiments; seeded with pilot_2019, deeplab_arm (tabled),
         degradation_synth_2000 + resolution_1x2x4 (queued, rules pre-registered).
         `94f22a2` qc/bench.py deterministic micro-benchmark — hermetic synthetic
         tiles through REAL dataset/train/validate, rtol 1e-4 vs stored reference;
         3 nondeterminism sources measured+pinned (CPU threads, algorithms,
         albumentations 2.x seeding from OS entropy ignoring global seeds);
         mutation-tested (DICE_WEIGHT x1.25 diverges every metric). `59cdc02`
         --overrides YAML overlays, manifest-recorded, tile-signature guard
         DERIVED from _tile_signature AST; bench MATCH on the commit touching
         cli/config — its first real assignment.
decided: bench regresses ENGINE math on resnet18, not the shipping arch (that has
         its own registry contract). Overrides never CREATE constants.
files:   phase4seg/{ckpt,overrides}.py, qc/{bench,check,pilot_gate,test_*}.py,
         experiments/, docs/SCHEMAS.md, STATUS.json
next:    Kam: main merge + tag still pending. Queue split (phase4_train_queue
         1,600 L) is the remaining big-file target.

## 2026-09-01  TOOLING + CORE SPLIT — ruff found 7 live bugs; core 2,666 -> 1,579 (Fable 5)

goal:    Kam: "improve the repo to improve the ability of claude code to create
         better code" — approved items: ruff gate, check.py ladder, nested
         CLAUDE.mds, then the core.py split.
did:     `59a3d71` ruff F-gate (F821/F401/F811 only, no style; config.py + frozen/
         excluded) — FIRST RUN caught 7 live bugs: 5 clean_argv imports sitting
         INSIDE module docstrings (py_compile-legal, NameError at main), a
         guaranteed NameError in cost_report's blocked-cost path (`m.group` with
         no m — the path EVERY launch takes), and core's `del model` deleting a
         name _forward closes over (post-cleanup call = NameError; canary-safe by
         call order only). +121 dead imports pruned across 73 files.
         qc/check.py = definition of done: ruff/compile/pytest/preflight/smoke,
         one command, ~75 s; CLAUDE.md 3.1 points at it; CI runs same rungs.
         Nested CLAUDE.mds in phase4seg/ + qc/instruments/ put rules at the edit.
         CORE SPLIT `048b9c5` + `0650782`: splits.py 281 + staging.py 161 (torch-
         free, measured) then ckpt.py 320 (function-local torch after lazy
         _ensure_torch — losses pattern) + select.py 455 (torch-free; MODELS_DIR/
         OUT_DIR read from core AT RUN TIME because tests patch core.X — the
         freeze trap fired in-suite and was fixed, not suppressed). Facade
         re-exports keep every core.X call site + monkeypatch. core.py 1,579 L.
decided: facade contract covers WRITES (dir constants) not just calls. train_test_split
         is facade surface (test_val_split's reference implementation).
killed:  nothing — every gate that fired (preflight module list, citations, F401
         on the facade) was fixed at the source, not suppressed.
files:   phase4seg/{ckpt,select,splits,staging}.py NEW; core.py; check.py NEW;
         pyproject [tool.ruff]; ci.yml; 2 nested CLAUDE.mds; ~80 files import-pruned.
next:    steps/dataset stay in core BY DESIGN (the _ensure_torch injection
         coupling; 3.5 rejected per-module injection). Kam: main merge + tag.

## 2026-09-01  REFACTOR COMPLETE — Stages 4+5 landed, repo is the target tree (Fable 5)

goal:    finish the approved full-repo refactor: tier moves + ingestion docs.
did:     4a `ae6aa63` shared trio qc->pipeline as installed py-modules; 5 reverse
         inserts died. 4b `8dad590` 18 builders -> pipeline/builders/, all anchors
         re-derived, dag+checklist+5 gated docs updated. 4c `d6db126` 70 instruments
         -> qc/instruments/ (qc root 98 -> 29); measured first: NO stayer imports a
         mover; 5 inserts died, ledger rewritten; 49 files of refs. 4d `1f2a59e`
         phase0-3 + label_review pair -> pipeline/frozen/ (zero importers, zero
         anchors, 3 refs). Stage 5: CLAUDE.md tree + install step, README layout
         row. EXIT CHECKS: pilot_gate re-read 3/3 PASS from the lake on the moved
         layout; CI green through 4c (4d in flight); 464 tests + preflight + smoke
         at every commit. Tracked files 883 -> 477 (-46%); pipeline root 88 -> 19;
         qc root 160 -> 29. config.py comments untouched (append-only) — its two
         stale builder refs are deliberate historical record.
decided: phase4_catalog_check STAYS at qc/ root (CLAUDE.md test command + suite
         import). No-op bootstrap sanity rides the NEXT queue launch, not a
         dedicated VM (canary already proved bootstrap+install at 1dbe158; no
         queue-path file moved since).
files:   see the four commits; STATUS.md regenerated each move.
next:    Kam: the tag (git tag deny is his), 36-year run go/no-go, label_review
         archive question, Class-B resolver repairs. Queued: degradation-synthesis
         A/B on 2000 (GPU), 4.4 within-acquisition 1x/2x/4x (GPU).

## 2026-08-31  CANARY 1 PASSED — refactor proven on real Colab, one live catch (Fable 5)

goal:    gate refactor Stages 2+3 on a real VM before Stage 4 tier moves.
did:     L4 VM `canary3b`, ~60 min total. Bootstrap: WRITE_CANARY PASS,
         EDITABLE_INSTALL OK, BOOTSTRAP_READY at branch tip, heartbeat 60 s cadence.
         Steps: inference (6.9 min, 3,501 positions) + postproc (12,682 polygons) on
         pilot-coarse checkpoint+tiles, exit 0 both. REGRESSION MATCH — new prob
         raster stats identical to pilot (mean 50.066, frac_ge128 0.17462); pilot
         originals backed up to masks/_prerefactor_backup/ first. Injection proven:
         KERNEL_ARGV showed colab_kernel_launcher.py -f kernel-*.json; qc suite
         parsed clean through clean_argv. Self-stop FIRED per spec: drain clear
         23:59:17Z, unassign ~10 min after last engine process. Registry: 2 rows.
         LIVE CATCH -> `1dbe158`: kernel-exec'd qc files (imagery_qc_suite,
         phase4_qc_indep) could not import phase4seg — pip -e works via .pth,
         site.py reads .pth at interpreter STARTUP only, so a running kernel never
         sees a mid-session install; subprocesses do. Insert restored to BOTH with
         mechanism comment + ledger lines. 464 green.
decided: kernel-exec keep is a permanent ledger class, not 4c debt.
killed:  v1 qc-suite wrapper printed OK over a swallowed %run traceback — run_cell
         + .success now; also --only matches FILENAMES not labels (2019 not 2019n).
files:   qc/imagery_qc_suite.py qc/phase4_qc_indep.py qc/test_status_discovery.py
         run_registry.csv
next:    Stage 4 tier moves 4a-4d, then Stage 5 ingestion docs. Tag still Kam's
         (git tag deny in his global settings).

## 2026-08-31  REFACTOR 0-3B — repo installable, path hacks dead (Fable 5)

goal:    Kam: "refactor my entire repo... centralize functions, definitions". Approved
         plan: full restructure, history to archive branch.
did:     Stage 0 hygiene. Stage 1 archive split — 883 -> 474 tracked files, branch
         `archive/2026-08-pre-refactor` local, CHATLOG rotated 4,015 -> ~120 lines,
         docs/ARCHIVE_INDEX.md maps it. Stage 2 centralization — shared homes
         names.py/deps.py/lake.py/pipeline_log.py + config.resolve_imagery; clean_argv
         pair filter replaced 96 broken one-liners. Stage 3A `12bcb01` pyproject +
         editable install, all 3 planes (local, ci.yml, VM bootstrap FATAL-on-fail).
         3B `a7dfe6c` path-hack sweep 79 -> 39 sys.path.insert sites; survivors on
         ledger gate test_path_insert_ledger (unlisted insert fails, growth fails,
         removal free). 463 green main env + preflight + smoke; fresh venv (only
         `pip install -e . -r requirements-local.txt pytest`) 402 pass + 5 skip =
         exactly the torch modules requirements-local excludes by design.
decided: preflight/smoke KEEP self-inserts — gate must validate engine sitting next to
         it, not whatever tree the venv install points at. finetune shim untouched.
killed:  first fresh-venv "green" — tail'd pipe swallowed "No module named pytest";
         pytest's number is the gate, never the pipe's exit.
files:   pyproject.toml, .gitignore, ~103 under qc/ + pipeline/, test_status_discovery.py
next:    BLOCKED: session permission mode denies `git push` (tried twice). Canary 1
         clones github (gen_vm_bootstrap.py:60) so it needs the branch pushed.
         Kam: push work/20260824-sectors (+ archive branch + tag when ready).
         Then CANARY 1 -> Stage 4 tier moves (4a-4d) -> Stage 5 ingestion docs.

## 2026-08-31  OVERHAUL EXECUTED + PILOT 3/3 — and 8 plan claims were false (Fable 5, all-night)

goal:    Kam: repo overhaul, then "move forward with the rest of the plan", GPU +
         parallel granted, "only assume 2 gpu run times", "unblock degradation synthesis".
did:     PILOT PASSED 3/3. 2019/2019s/2019n each produced a mask GPKG, a live independent
         score, a manifest carrying epoch=2, and all six steps OK unattended. U3 proven on
         three tiers: postproc had NEVER run under a queue before (it was absent from
         STEPS, so --skip-postproc skipped a step that was never going to happen).
         Gate met -> the 36-year run is unblocked and is KAM'S call, not inferred from
         "the rest of the plan" (the plan scoped itself to machinery + pilot).
         indep: 2019 rec .6492 prec .8365 | 2019s .6331/.7735 | 2019n .6915/.7858.
         COARSE BEAT MEDIUM on the same date, and support-matched rescore at 1/2/4 m
         KILLED the measurement-artifact explanation: gap flat (+.0564/+.0577/+.0571 vs
         +.0584 native), precision gap widens. Live confound is now PROGRAM/SENSOR
         (Snoh HXIP vs NAIP), not the ruler. 1 m result independently reproduces
         qc_indep to .002 — two scoring paths agreeing.
killed:  EIGHT plan/board claims, each checked against source, several my own:
         "+9.2 OA, the largest measured lever" — appears ONCE in this repo, in the
         sentence asserting it. No source anywhere. "A tiling parameter, not a retrain"
         — backwards; tiles ARE the training input.
         "The SDM depends only on the fixed mask, so cache it" — augmentation warps
         89.5% of tiles NON-isometrically; the cache would have been a silent
         correctness bug. Moved into the DataLoader instead: 446 -> 4.7 ms/batch.
         "The ERF is smaller than one crown at fine GSD" — false for EVERY acquisition
         (min 1.07 at 2022/6.5cm; needs <6.09 cm effective, finest measured is 6.5).
         Fine is context-POOREST (2.07 crown-widths vs coarse 15.60), not starved.
         The 2026-08-27 object-ratio note predicted COARSE underperformance — backwards:
         coarse gets 7.5x MORE context per prediction. Tile span is 22.4x, not ~7x.
         "3.6 not started" — step_evaluate had stamped run_tag since D6, a day earlier.
         "2019s/2019n is a same-flight pair" — same DATE, two programs (HXIP vs NAIP).
         "core.py split needs an ensure_torch(globals()) rework, laziness gated twice" —
         gated ONCE (preflight only PRINTS it); function-local imports work, as
         sdm_for_mask already does for scipy. Losses split landed, 2833 -> 2621 lines.
         "There is no R2 radiometry table" (MINE, wrong) — qc/instruments/radiometry_norm.py is
         self-titled R2; I asserted a negative from two .md files without grepping qc/.
         "n_targets=2, so zero residual DOF" (MINE, wrong) — n_points is 6, 4 DOF.
found:   --aux-height BROKEN since 50006ce (my own fail-loud-loads commit): allow_missing
         passed "aux_height_head." but the real keys are "height_head.". Four tests
         passed VACUOUSLY because the fixture was named after the bug, and smoke
         hard-sets AUX_HEIGHT=False so no local gate reached it.
         A dead run credited with a rerun's success in run_registry: the attempt bound
         keyed on a next-RUNNING row, but a launch UPDATES its row in place, so a
         finished rerun erases the marker the bound depends on.
         Leakage that would have made the synthesis A/B report a phantom gain: synthetic
         tiles cover the SAME GROUND as the target year, and ground is partitioned by
         block, so a tile from a val/test block puts that ground into training with
         better labels. Documented before any data existed to be contaminated.
ops:     A100 is CONCURRENCY-capped at 2 (TooManyAssignments, not scarcity; L4 assigned
         in 14 s with both busy). `cmd | tee log` hides the launcher's exit code.
         The G: mirror BLINKS files in and out. I declared a working runtime dead once —
         three signals agreed and all three were wrong; what separates the cases is the
         step's own median/max and the queue's OWN STEP_TIMEOUT_MIN ceiling.
built:   names.py (one status vocabulary, row key, filename parser+formatter, symbol
         locators), test_docs_match_code + test_citations_resolve + pilot_gate +
         tile_object_ratio + support_matched_rescore + degrade_synth (Phase A, two-pass
         Real-ESRGAN chain, deterministic, self-describing). 441 tests, CI green.
next:    KAM'S CALL: the 36-year run; 4.1c (boundary vs perimeter — a science decision);
         4.3 (DeepLabV3+ CONTRADICTS "keep the U-Net and resnet101" recorded in this same
         plan). GPU-ready: 4.4's within-acquisition resolution test (the last confound),
         4.5's synthetic A/B on 2000 (best-fit weak year: red RMS 5.75 vs 47.37).


════════ ROTATED 2026-08-31 (ingestibility refactor, Stage 1) ════════

Everything below this file's newest entry — the full 1,489-line STATE transcript and every
LOG entry from 2026-06-29 through 2026-08-29 — is preserved byte-identical on the archive
branch:

    git show archive/2026-08-pre-refactor:Scripts/CHATLOG.md

The older `_archive/CHATLOG_2026-06-29_to_2026-07-07.md` compaction lives there too. This
stub stays the valid append target required by CLAUDE.md §3.12; the HOW-TO block above is
the unchanged spec for new entries.

## 2026-09-03  tier1-verdicts
goal:    finish tier1 GPU tail, score all arms, write pre-registered verdicts
did:     t1gpuF ran final 9 inference arms then self-stopped via watchdog (0 runtimes left).
         conveyor scored 27/28 (cor02 has no ckpt). built qc/instruments/build_tier1_results.py
         -> phase4/qc/tier1_results.csv. floor .0085 from 2011s replicates. verdicts in
         experiments/tier1_science_sample.yaml: LIDAR-INPUT CONFIRMED 3/3 yrs; ADDER NOT
         CONFIRMED 1/3 (2006s_add16 -.503 epoch poison); NIR CONFIRMED both yrs; corruption
         <=10pct flat. conveyor timeout death fixed (1200->3600s, 2020 scores are 167M cells).
files:   experiments/tier1_science_sample.yaml, qc/instruments/build_tier1_results.py,
         phase4/qc/tier1_results.csv, run_registry.csv, STATUS.*
next:    perf writeup (ledger sync pending), cor02 fate, verdicts -> full_archive_e3 recipe (Kam)

## 2026-09-04  accuracy-batch-overnight
goal:    Kam's approved 8-item CPU batch (reference error + boundary accounting)
did:     sampler repaired (chm2 strata, undo bug) + 2016/2023n REDRAWN (K1 unblocked,
         design-power +/-1.87pp). U1: estimate scores ANY arm at the labelled points.
         E2 covariates joined. certified-flat scoring: C-CAP 2016 over-calls 0.30% of
         physically-empty ground (2021: <=1.17% incl growth); lidar-input slashes
         empty-ground FP (2020 base .256->in16 .037); add16 poison visible (.375).
         C2: ~2-3pt recall / ~2.4pt precision is 1px edge accounting at 1m years.
         C3: same flight two deliveries = 1.3pt citywide area gap, IoU .738 -- the
         trend's consistency floor. C1 lidar anchors (2016_base .751/.712 CLEAN;
         in16-vs-chm2 flagged CIRCULAR). tile-signature anchor-key gap closed +
         tripwire. E1 histograms KILLED the leaf-off premise: gradient is DELIVERY
         RADIOMETRY (2015 Feb bimodal+unharmed; 2019 Apr whole-shift -0.02).
         hybrid_v1 PR closed (AUROC .8946). X6 provenance. MVV-0 epoch-decay record.
files:   qc/instruments/{phase4_accuracy_sample,build_sample_covariates,
         certified_flat_scoring,tier1_block_bootstrap,tier1_buffer_tolerant,
         sameflight_consistency,phase4_qc_leafoff,phase4_arm_pr_curves}.py,
         phase4seg/tiling.py, phase4/qc/*.csv, Reports/{GREENNESS,EPOCH_DECAY}*.md
next:    K1 (Kam labels 250, ~15min), K4 confirmation of the whole documented block,
         radiometric-normalization pilot design, 2016_base reseed (GPU, Kam)

## 2026-09-04  direction-campaign-panel-a
goal:    tell the city the direction of the canopy
did:     direction workflow (5 agents): no sign survives the old instruments; paired-
         change design instead. power gate: 250 FAILS, 1250 GO (hw 1.03pp). decimation
         null REVIVED lidar 2005->2016 net-gain (artifact gain 1.50km2, artifact loss
         ~0 - density cannot fake loss). Panel A built (locators eroded 48->18% share,
         N raised 1000->1250 for power .81), Kam labeled 1250 pairs + 61-call verify
         pass vs leaf-on Oct-2023 (2024 flew Mar-May leaf-off - Kam caught it).
         RESULT: -2.21pp 2016->2024, CI [-3.31,-1.11], DOWN. 42/54 losses real,
         6/7 gains fake. blur 0/30, capture 2/97. C2b metric tolerance: 2020 strict
         score was pixel-harshness (at 2m tolerance 2020 is BEST year .920).
files:   qc/instruments/{panel_a_paired_change,paired_change_power,
         lidar_decimation_null,tier1_metric_tolerance}.py, phase4/qc/panel_a_*,
         metric_tolerance_scores.csv, lidar_decimation_null.csv, paired_change_power.csv
next:    city statement doc (two-leg story: lidar up 2005-2016, human-measured down
         2016-2024); Panel B (2005->2016 paired) decision; Bayesian anchor optional

## 2026-09-05  trend8-verdict-overlap-launch
goal:    8-year map series verdicts + flicker program items 1-8 (Kam approved)
did:     trend8 DONE both A100s one session (16 masks). raw fractions sawtooth
         +-3-6pp; 2m harmonization NULL (detection-time bias); map 2016->2024 +4.2pp
         OPPOSITE Panel A -2.21 - maps disqualified from trend, Panel A stands.
         hot spots: 115ha loss, dispersed (max cluster 0.41ha), 34/42 of Kam's
         verified losses corroborated. lit families 3/4/5 workflow -> ranked program.
         item1 flicker parcels: hard negatives ~0 FP flat (no hallucinated canopy).
         2017k promoted (Kam item-7 approval): catalog append, gsd corrected to
         MEASURED 10.0 (Mercator flag), geometry/coreg/passport regen, pins 36->37
         26->27, coreg 2017k median .01/.21m. overlap_floor pre-registered
         (items 2+5+7: floor kill >1.3pp, factorial, EagleView triple sign test).
files:   experiments/{trend8_uniform_rgb,overlap_floor}.yaml, config.py append,
         qc/instruments/trend8_*.py, phase4/qc/trend8_*, coregistration.csv,
         imagery_geometry.csv, passport, test pins
next:    launch overlap_floor 2xA100; items 3 (Landsat covariate), 4 (degradation
         ladder), 6 (2m stack census); 2020-Aug consortium fetch

## 2026-09-05  housecleaning
goal:    repo hygiene after the week
did:     pr-curves outputs homed to phase4/qc (root pollution from the 4c-move bug,
         instrument still writes cwd - debt). QUARANTINED four 2023n sidecars holding
         2022n byte-copy content (qc_indep/leafoff-control/design_power x2; dot-suffix
         rename + README_2023N_QUARANTINE; sample_2023n itself was already redrawn
         2026-09-03). landed.py absorbed 28 registry rows (trend8+overlap manifests).
         FIXED landed.py CHATLOG gate: re.search took the FIRST ## date (oldest in
         the rotated stub) as "newest" and nagged past entries; now max(findall).
         lit pile complete: 4 papers read+reasoned (MURTreeFormer, JPSL irrational-
         transitions, GeoAI inheritance, ALCC ensemble) - all confirm the diagnosis,
         none validates change vs blind human truth; 3 free tests queued.
files:   qc/landed.py, phase4/qc/arm_pr_curves*, CHATLOG.md, run_registry.csv,
         lake: 2023n quarantine renames + README
next:    overlap GPUs finishing -> floor/factorial/EagleView reads; then the
         synthesis session (Kam). Search budget exhausted this session - skeptic
         hunt brief for a fresh session.

## 2026-09-06  recalibration-campaign-complete
goal:    finish the operating-point recalibration + all overlap reads
did:     14/14 sweeps (3 free CPU VMs + sweep4 + recut2 relays; handle mortality
         worked around; recut1 died on corrupt staged tif -> lake-side logs +
         scratch cleanup fix -> recut2 8/8). VERDICTS WRITTEN, both experiments
         complete: overlap_floor - floor 0.15pp PASS, quartet 10.1->3.55pp with
         residual entirely the 1m arm, season ~0, <=30cm deliveries interchangeable
         (0.15pp); EagleView endpoints -0.94pp/4yr agree with Panel A sign+pace,
         interior wobble = single-year steps unreadable. trend8 - delivered cuts
         RETRACTED, matched cuts flip the sign test to PASS (-3.5 to -5.6pp
         2016->2024), two-leg story reproduced, 41/42 loss corroboration, flicker
         did NOT collapse (47.8%) = pixel noise real, maps need persistence.
         2017k promoted+trained (VERIFY OK) after 2 imagery-visibility failures.
files:   experiments/{trend8_uniform_rgb,overlap_floor}.yaml (verdicts), queues
         removed, phase4/qc/{trend8_policy_cuts,overlap_factorial_read,
         eagleview_sign_test,trend8_*}.csv, hotspot map, payloads
next:    Kam synthesis session (all evidence final); K4 sign-offs; city statement

## 2026-09-06  experiment-registry-built
goal:    Kam: one machine-readable source for every experiment - inputs, outputs,
         variables, imagery, sample size, provenance - always in reach for agents
did:     Diagnosed the .docx ledger's four bottlenecks (unsearchable binary; no
         regeneration path; frozen 09-03 so the recalibration silently superseded
         parts of it; nothing gated it) -> two-layer design. AUTHORED layer =
         experiments/*.yaml extended additively: kind (experiment /
         measurement-campaign / instrument-finding, so Panel A + the lit hunt fit
         without inventing arms), retrospective (gate-enforced: a backfilled
         decision_rule is a reconstruction and must say so, or the registry
         fabricates pre-registration), pinned n/n_source, imagery as catalog keys,
         supersession links, instruments/inputs/outputs. GENERATED layer =
         qc/experiments_index.py joins all entries against run_registry,
         qc_indep_report(live=1), tier1_results, champion_arms, YEAR_CATALOG and
         writes INDEX.md + index.json with RESOLVED values; test_index_is_fresh
         regenerates + byte-compares so it cannot rot the way the doc did.
         Backfill: 6 extract agents + 6 adversarial verifiers (Opus; the Fable
         fleet hit its usage limit first try, zero files written, relaunched).
         32 entries written, 7 errors fixed in place by the verifiers (a 5cm GSD
         that is 30.5, a quote attributed to the wrong file, a date read off a
         checkout mtime, a mis-cited decision leg), 15 substantive findings
         escalated and then applied under a second fix+recheck pass. Biggest
         catch: imagery_qc_suite_2026_08_24 had the grading mechanism INVERTED -
         credited peak ratio with deciding trustworthiness when the instrument
         says confidence comes from site agreement and gating on peak ratio once
         threw away 54 of 100 measurements. recipe_audit's "identical to 4dp"
         disproved by its own CSV -> UNDETERMINED per 3.5. Gate bug found by real
         data: tag ownership keyed on tag alone, but the engine's unit is
         (year,tag) - tiles/{year}__{tag}/ - so one recipe across two years looked
         like a conflict; fixed. 43 entries: 34 complete, 5 needs-kam (verdict
         null - documented but unsigned, or output not in the tracked record),
         3 queued, 1 tabled. check.py all five rungs, 482 tests.
files:   experiments/{INDEX.md,index.json,README.md,BACKFILL_RECONCILIATION.md} +
         32 new *.yaml, qc/experiments_index.py, qc/test_experiments.py,
         CLAUDE.md roadmap row, WORKPLAN DONE row
next:    Kam synthesis session (open INDEX.md first); K4 sign-offs incl. the 5
         needs-kam entries; the docx stays as the audited 09-03 snapshot

## 2026-09-06  run-context-layer-built
goal:    Kam: centralize as much data per run as possible - best performance per
         year, steady points on the curve for objective comparison, tile counts,
         WHICH tiles trained, and a unique ID per tile SET
did:     Five phases, each its own commit. (1) TILE SET IDENTITY: the engine already
         DEFINED it - _tile_signature is the dict deciding cache reuse - but it lived
         only in a lake sidecar. tiling.tileset_id() reduces the STORED dict (not a
         recomputation: _existing_tiles_valid grandfathers old caches by dropping
         keys, so live config can differ from disk) to 12 hex. 81 tile dirs -> 71
         distinct sets, 41,856 tiles. Tile LISTS tracked in full (924 KB pruned to
         row_off/col_off/split/block) because a re-tile overwrites its lake dir in
         place and takes the old answer with it. Immediately showed 4 sets shared by
         >1 arm - the seed replicates, so those noise floors really did hold tiles
         constant. (2) RUN PASSPORT: 535 manifests -> 240 KB tracked CSV, pip_freeze
         hashed to env_sha (37 distinct environments). join_basis declares its own
         weakness: historical runs are inferred_current forever because a manifest
         never recorded its tile set. Found 16 manifests with no run_registry row.
         (3) METRICS: 87 PR sweeps tracked whole (1.15 MB) + arm_metrics.csv, one row
         per (curve, policy) with thresh, counts, population, pr_auc. Policy is a
         closed gated set: best_f1 (what shipped, never valid cross-arm), matched
         p50/p75/p90 (the steady points), scored_live. PR-AUC not AUROC - no tn in a
         sweep, and at 650x skew AUROC flatters everything. (4) ENGINE stamps
         tilesets into the manifest AFTER the step loop (writing it at manifest time
         would stamp a re-tiling run with its PREDECESSOR's set); signature untouched,
         test_tile_signature_scope still green. (5) YEAR SCOREBOARD at a held cut,
         grouped by (ref, eval_scope) so a coverage gap never reads as a skill gap.
bugs:    MY OWN curve_id ignored the evaluation POPULATION - the LOSO
         sample-selection/sample-test halves collided, 87 sweeps became 58, one
         silently dropped. That is exactly the sin the module exists to prevent,
         committed by its own key. eval_scope now keys the curve; halves differ
         materially (2006s_add05 .5215 vs .5676). Also: every pr_auc read nan because
         a sweep's extreme cut has tp=fp=0 -> precision 0/0, and one such point
         poisons the integral; non-finite now parses as ABSENT. Also: the tag
         ownership gate keyed on tag alone when the engine's unit is (year,tag).
files:   qc/instruments/harvest_{tilesets,run_passport,arm_metrics}.py,
         qc/year_scoreboard.py, qc/test_run_context.py (20 gates),
         pipeline/phase4seg/{tiling,cli}.py, qc/experiments_index.py,
         phase4/qc/{tileset_registry,run_passport,arm_metrics}.csv +
         tilesets/ (71) + curves/ (87) + year_scoreboard.md, docs/SCHEMAS.md,
         .gitignore, CLAUDE.md roadmap, WORKPLAN DONE row
next:    re-harvest after each Colab campaign (command in CLAUDE.md 2.2); new runs
         earn join_basis=manifest; Kam synthesis session

## 2026-09-06  context-retrieval-built
goal:    Kam: what is missing that would reduce the bottleneck of getting science
         into context. Measured it instead of guessing, then built the top three.
did:     MEASURED THE BOTTLENECK FIRST: cold-start read order is ~14.7k tokens across
         4 docs, but the context layer built earlier today is ~115k tokens of CSV read
         raw - so capture had stopped being the problem and RETRIEVAL had become it.
         (1) qc/ask.py - one subject, one answer, ~40 lines. Detects whether the
         subject is an acquisition, arm tag, registry entry or tileset id; joins every
         tracked home; names the home each block came from so answers are checkable.
         --gaps and --list. Reads only tracked files: bare checkout, no lake, no GPU.
         (2) qc/coverage_map.py -> phase4/qc/coverage_map.md, per-acquisition matrix.
         Surfaced numbers nobody had: of 37 acquisitions 13 never tiled, 9 NEVER
         SCORED (2002s 2007s 2009s 2013s 2015n 2015s 2021n 2022s 2024s), 21 with no
         matched-cut read, 21 with no champion. Deliberately refuses to imply a
         backlog - blank = no record, not should-have-been-done; gate pins the caveat.
         (3) failure registry: harvest_failures.py counts SYMPTOMS from 863 step logs
         (22 with errors>0 -> 8 distinct failures, normalised signatures so one bug is
         one row); qc/known_failures.yaml is the AUTHORED cause+fix matched by regex.
         All 8 diagnosed from the tracebacks. THREE ARE ONE MECHANISM: Drive FUSE
         dropping I/O under sustained small-file reads (EIO on train, mkdir ENOENT on
         tile, truncated tile -> unsupported-format) = rule 3.9 seen from the read
         side. Undiagnosed rows carry an empty cause BY CONTRACT and surface in
         ask.py --gaps, so "never worked out why" is a to-do not a silence.
files:   qc/{ask,coverage_map,known_failures.yaml}, qc/instruments/harvest_failures.py,
         qc/test_run_context.py (25 gates), phase4/qc/{coverage_map.md,
         failure_registry.csv}, docs/SCHEMAS.md, CLAUDE.md roadmap (ask.py is now the
         FIRST row), WORKPLAN DONE row
next:    still missing per my own assessment: bidirectional claim<->evidence links,
         a decision registry for the AWAITING KAM stack, and automatic re-harvest as
         a landed.py rung (today the harvests are manual and can silently drift)

## 2026-09-06  decisions-claims-autoharvest
goal:    build the three gaps I named in my own assessment last turn
did:     (1) AUTO RE-HARVEST as landed.py rungs - the harvests were manual, so a
         campaign landing without them left every context table describing the
         PREVIOUS lake state (the .docx failure mode, faster). Ten rungs now, docstring
         updated to match. (2) DECISIONS: decisions.yaml, 10 entries, owner + why +
         evidence + blocks/blocked_by edges; ask.py --decisions sorts ready-first
         (5 ready, 5 waiting). WORKPLAN now POINTS instead of restating. The symmetry
         gate caught two one-sided edges in the file I had just written. (3) CLAIMS:
         claims.yaml + qc/claims.py resolver (superset of the n_source grammar: adds
         csv:<col>@<filters> single-cell, regex:, dir_csv_count) + verify_claims.py
         (exit 1 on drift) + test_claims.py. Seven claims seeded, all OK. A drifted
         claim is REPORTED not auto-corrected - which side is wrong is a judgement.
         Mutation-tested all three failure modes (moved value -> drifted; missing file
         -> unresolved; ambiguous selector -> error) before trusting the gate.
         Also answered Kam on how Claude uses ask.py: it is now the FIRST roadmap row
         in CLAUDE.md, so orientation is CLAUDE.md + WORKPLAN + ask.py per subject
         rather than reading four docs and guessing which of ten artifacts to open.
files:   decisions.yaml, claims.yaml, qc/{claims,verify_claims,ask,landed}.py,
         qc/test_{claims,decisions}.py, qc/test_status_discovery.py ledger,
         docs/SCHEMAS.md, CLAUDE.md roadmap, WORKPLAN AWAITING-KAM section
next:    still open from the assessment: nothing. Next real work is Kam's decision
         stack - 5 decisions are READY NOW with nothing above them

## 2026-09-08  speedup-pilot-recording-ledger-recovery
goal:    Kam: "fix bottle necks", "test run on a year we have already run so you can
         compare", "improved record and metric collection", "don't defer to me for
         permissions". Orchestrator + Opus agents; every change refereed (3.4c).
did:     (1) MEASURED where the A100 idles: per-step attribution redone twice — cross-VM
         contamination (29% samples ambiguous) and net TX missing from the dead test.
         Result: tile 71% / postproc 96% of own time with EVERY counter zero = blocked on
         Drive per-file latency; vm_hwlogger counted iowait as idle. Reports §7.
         (2) LANDED, refereed, gate green: checkpoint diet (optim/sched state never read
         back; 1113.1 -> 371.4 MB measured on production arch, Reports §8); postproc
         stage-then-read; step marker + iowait column in hw telemetry (v2, 15 cols);
         harvest_hw_attribution, harvest_timing_events (first MEASURED Drive throughput:
         39.7 MB/s median over 145 large files, p10-p90 7-87), harvest_runtime_sessions;
         queue-side launching/verifying phases + VERIFY minutes; hw_meta runtime facts.
         (3) PILOT offload_pilot_2017k RAN (spdc1 CPU / spdg A100 / spdc2 CPU), verdict
         in experiments/offload_pilot_2017k.yaml from phase4/qc/offload_pilot_2017k.csv:
         K2 PASS tileset a36d6772e88b identical from CPU; R1 PROMOTE A100 span 113.0 ->
         67.3 min; R2 PASS 371.4 MB; R3 FAIL postproc 26.9 vs 18.0 (staging ENGAGED, 2.4 GB
         in 114 s; polygonize 653 vs 436 s on 2 vCPU); R5 same model AP .4338/.4275.
         Unplanned: same recipe retrain moved canopy 19.6% -> 19.1% (threshold .558 ->
         .594) = single-seed noise sample; tile copy 228 s/train (1,264 files, 5.5/s);
         same 11.5 GB ortho staged 4x at 37-133 MB/s; queue start-up 359 s merging 76
         status files over FUSE (fixed 94cb8df, unvalidated); hwlogger lost 26-30% of
         samples to its own flush (fixed e8dec13).
         (4) LEDGER ERASURE FOUND: since 4c546a7 (08-31) queue_ledger._q imported the queue
         a second time under python script start; STATUS_OUT None on the copy -> every
         launch REPLACED the shared train_queue_status.csv with its own rows. Six days
         erased. Fixed e499355 (verified: spdc2 wrote its per-launch file). 25 orphan
         snapshots preserved phase4/qc/ledger_recovery/ (252 rows); rebuild instrument
         -> 450-row candidate; RESTORED to lake as additive train_queue_status_recovered_
         20260901_20260907.csv (Kam delegated). Bootstrap never installed
         requirements-colab.txt since 08-26 (fixed 3f60b0f).
decided: labels+tile -> free CPU runtimes by default (K2+R1). postproc stays on GPU box
         (2 vCPU 1.5x slower; bigger CPU tier untested). Restore recovered ledger to lake:
         additive, readers merge, one free re-run risk accepted. Hand-split queue files
         carry no GENERATED header (drift test would fail) — split is a launch concern.
killed:  "dup-guard opens 72 heartbeat files" — refuted, stat-first, 0 s. "labels VERIFY
         took 7 min" — misread, queue ts = step START; VERIFY 3 s, 6.8 min was engine
         start-up doing 0.0 s of work. "pip installs per step" — per VM, ~13 s A100.
         "891.8 MB checkpoint" — no such file; archive bimodal 773.0 / 1113.2 MB.
         My own gating: two chains continued past failing checks (pipe masked exit code)
         — commits went out with failures; fixed after; set -o pipefail from then on.
files:   Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §7-9; experiments/offload_pilot_
         2017k.yaml; pipeline/{pilot_offload_2017k_cpu1,gpu,cpu2}.yaml; phase4seg/{ckpt,
         select,postproc,names}.py; pipeline/{pipeline_log,vm_hwlogger,queue_ledger,
         queue_verify,phase4_train_queue,gen_vm_bootstrap}.py; qc/instruments/{harvest_hw_
         attribution,harvest_timing_events,harvest_runtime_sessions,offload_pilot_compare,
         rebuild_queue_ledger}.py + tests; phase4/qc/{hw_step_attribution,timing_events,
         runtime_sessions,offload_pilot_2017k}.csv; phase4/qc/ledger_recovery/; docs/SCHEMAS.md
         (many sections); memory queue-ledger-erasure-recovery. Branch work/20260906-healing-tool.
next:    tile-bundle handoff (workflow in flight: one archive per tileset_id, ~13 s vs
         228 s); rebuild instrument session-aware suppression (agent in flight); then
         ortho scratch cache (P3, now measured 4x re-stage), common.py::_publish_replace
         aside guard, per-epoch train profiler (train GPU-busy 20%, CPU>90% 40%, 16
         workers on 12 vCPU), evaluate's un-instrumented +1 min, ledger consolidation
         rung. Validate 94cb8df startup line on next launch. Concurrency cap raise still
         #1 wall-clock lever (Kam).

## 2026-09-08  bundle-validation-run-and-ledger-rebuild-2
goal:    validate five post-pilot machinery changes on a real run (3.4c), close the
         ledger rebuild's two limits, land the follow-ups the pilot exposed.
did:     (1) VALIDATION RAN: experiments/bundle_validation_2017k.yaml (spdvc1 CPU
         labels+tile, spdvg A100 train, PHASE4SEG_TILE_BUNDLE=1 via new `vm_ops launch
         --env`), referee-scored from named files. K1/K2 PASS. R1 FAIL: bundle read
         123.7 s vs 60 s bar (1.85x faster than 228.2 per-file; >= 86 s zero-traffic
         stall, one vCPU in D-state; rclone upload of same files 1302 vs 522 s same
         window; comparator wrong at 0.3 GB size class). Flag stays OFF. R2 PASS startup
         merge 5.1/5.9 s (was 359). R3 PASS 0 installs (was 3). R4 PASS 0 gaps 0 torn
         (was 15-24% lost). R5 PASS phases + VERIFY minutes on every step.
         (2) LANDED: tile-bundle handoff dd71417 (design duel: minimal design's guards
         all inert against same-signature re-tile; robust design sweeps every bundle on
         write); vm_ops --env 961abb0; site-discovery skip under citywide 6276207 (labels
         9.4 min of nothing; tile's cost moved inside step - needs sites for negative
         records); coverage_map/science_digest/ask.py tile SET vs DIRECTORY census
         ee5be4d 271f804 (2017k read 1264 for 632); claims split 71 sets / 83 dirs;
         cpu_model/mhz/bogomips in hw_meta 8bd256c (two "2 vCPU" hosts: 21.0 vs 39.1
         min same tile step, cause UNDETERMINED); rebuild per-LAUNCH suppression +
         start-of-step ts af60d97 (of2017k2 rows back; 496 rows replace 450 on lake).
         (3) FOUND, untimed: saving epochs 58 s vs 24 s non-saving = 11-13 min per
         train step in torch.save / sha256 read-back / publish / verify, A100 idle;
         timed copy 2.5 s of it. 4x the bundle's whole saving.
decided: bundle flag not promoted (pre-registered bar). Recovered ledger on lake
         REPLACED with 496-row version (superset, better ts). Row-count claims
         (tileset-directories) refresh at landed.py - drift expected by design.
killed:  "39.1 MB/s is the bar for a 0.5 GB read" - size-class conditioned: p10 7.5,
         16/82 under 10 at 0.01-0.33 GB. "bundle shortened training" - only 104.5 s of
         240 s delta is the staging line; rest is one fewer save. My "19.7/33.5 min
         tile compute" derivation - sampled minutes are 21.0/39.1 (ratio holds).
files:   experiments/bundle_validation_2017k.yaml; pipeline/bundle_validation_2017k_
         {cpu1,gpu}.yaml; phase4seg/{staging,tiling,cli,common}.py; pipeline/vm_ops.py;
         qc/{coverage_map,science_digest,ask}.py; qc/instruments/{rebuild_queue_ledger,
         harvest_runtime_sessions}.py; pipeline/vm_hwlogger.py; claims.yaml;
         docs/SCHEMAS.md; WORKPLAN board rows.
next:    engine workflow in flight (ortho scratch cache design duel, common.py::
         _publish_replace guard, per-epoch phase timing, evaluate ticks) - commit on
         landing. Probe: re-read aged bundle on a fresh runtime with chunked timing
         (agent writing qc/instruments/probe_bundle_read.py) - settles window vs
         structural. Then chunked copy w/ floor + rclone escape if structural. Ticks
         around torch.save/_sha256/verify_on_drive. Ledger consolidation rung.
         Concurrency cap raise (Kam) still #1 wall-clock lever.

## 2026-09-08  engine-cache-profiler-bounded-read-landed
goal:    land the engine follow-ups the pilot and validation exposed; settle the bundle
         stall question; close the session with every rung clean.
did:     (1) ENGINE 83d1169 (design duel + referees, ladder incl. bench = BENCH MATCH):
         ortho scratch cache phase4seg/scratchcache.py - entries keyed by the existing
         full-path hash, source compared on every hit, journal `copying` BEFORE the copy,
         .part + os.replace, pins per (entry, pid) under flock before validation/open,
         LRU eviction inside cache namespace only, prob raster ADOPTED after verified
         Drive copy (under the queue POSTPROC_FOLLOWS is always False - every step its
         own process - so postproc re-staged 2.4-6.7 GB every time); hit emits NO timing
         row (would fabricate the saving). Residuals closed: pre-clear stale payload
         under flock; eviction ladder never empties cache, never evicts the entry being
         made room for. common.py::_publish_replace aside guard = ledger's (OSError +
         re-probe). Per-epoch phase rows data/gpu(sync at epoch end)/val/save/other +
         evaluate spans; SCHEMAS overlap rule (sum within family). Saving UNVALIDATED
         until a same-VM tile+inference job shows the inference stage row gone.
         (2) PROBE 5aa99e1 (qc/instruments/probe_bundle_read.py, detached, log mirrored
         30 s; first attempt via exec channel timed out on a silent copy): same aged
         bundle 10.6 s copy / 18.0 s end-to-end; chunked re-read stalled 33 s once; aged
         control 66.9 MB/s no stall -> stalls intermittent on any read, not freshness.
         (3) BOUNDED READ a5e58b4: FLOOR_MBPS 6.0 (p5.3 of 0.10-0.33 GB stage rows;
         4.30 trips, 7.50/48.3 don't), MAX_STALL_S 60 (33.3 passes, >=86 fails), escape
         to rclone path; honest limit in source: on the measured trace the gate fires at
         ~101 s then fallback costs ~228 s - protects against never-returning stalls,
         saves nothing on the one seen. Verdict comparator band corrected 0.01->0.10 GB.
         (4) landed.py all mechanical rungs clean; STATUS regenerated; harvests settled.
decided: PHASE4SEG_TILE_BUNDLE stays OFF (R1 FAIL stands); re-validate on next
         campaign train now that the read is bounded. Cache lands OFF nothing - it is
         transparent; first same-VM campaign validates it.
killed:  "stall = fresh object" as sole cause (B's 33 s on a re-read). "bound saves
         time" (it bounds worst case). Exec channel for long silent VM work (times out
         waiting for output; detach + mirror instead).
files:   phase4seg/{scratchcache,common,core,labels,postproc,staging,tiling}.py,
         phase4seg_preflight.py, queue_ledger.py docstring, qc/test_{scratch_cache,
         train_timing,tile_bundle,verified_write,postproc_source}.py,
         qc/instruments/probe_bundle_read.py, phase4/qc/probe_bundle_read_2026*.txt,
         docs/SCHEMAS.md, experiments/bundle_validation_2017k.yaml extra.probe_result,
         STATUS.md/json, WORKPLAN board.
next:    finer save split (torch.save / sha256 read-back / publish / verify are ONE
         `save` bucket today; 11-13 min/train, A100 idle); validate cache + bounded
         bundle on the next campaign (heal_infill queue is ready, ~8 A100-h + 1.2 h
         tile on CPU); ledger consolidation rung; postproc on a >2-vCPU CPU tier;
         concurrency cap raise (Kam) still #1 wall-clock lever.

## 2026-09-08  healing-literature-tests-run
goal:    turn the lit review's three first tests into instruments and run the two that
         need no labels; record what they say about the healer we have.
did:     lit review landed (experiments/lit_healing_analogues.yaml; Reports/LIT_HEALING_
         ANALOGUES_2026-09-08.md; 72 mechanisms, 26 adjudicated): NO field has a measured
         laundering rate for a one-directional temporal fill; convergent formula needs
         gamma_conditional the panel cannot supply. Reasoning §14 maps it onto our design.
         INSTRUMENTS: heal_gap_spectrum (test 2): laundered_at_risk = 0 in EVERY bucket -
         a verified loss's terminal absence runs to series end, a both-sides fill can never
         touch it; 0/42 has NO POWER. heal_infill rule AMENDED on record (22d3a9c): fill-
         side audit + impossible triples are the operative tests. heal_fill_audit_sample
         (test 1): 300 fills + 300 controls drawn, 220 lidar-adjudicable; REVIEW tier has
         zero population on 8 epochs; control = one-sided absences (literal control pop is
         0 by the operator's definition). heal_fill_odds: formula licenses every fill under
         panel gamma; ~20:1 FILL under gamma_rule; inert as predicted. heal_closing_
         baseline: tier-matched closing == healer pre-floor candidate set TO THE CELL
         (449,663) - all shifts round to 0 cells at 2 m, landmark transform inert on this
         grid; healer - closing = the size floor alone (-28.9% cells, -10 triple fixes);
         floor gain UNDETERMINED. Reasoning §15 records all four.
decided: hold the 3-arm heal launch until the 2017 training divergence is refereed
         (Phase B never improved; probabilities compressed; WEAK_CALIBRATION on the
         raster; suspect window is today's engine commit).
killed:  "0 of 42 laundered" as a bound (vacuous for both-sides rules, measured).
         "the landmark transform buys placement accuracy for the healer" at 2 m (inert).
files:   qc/instruments/heal_{gap_spectrum,fill_audit_sample,fill_odds,closing_baseline}.py
         + tests; phase4/qc/heal_*.csv, heal_fill_audit_design.txt; experiments/
         heal_infill_2017_2023.yaml amendment; Reports/HEALING_TOOL_REASONING §14-15;
         docs/SCHEMAS.md; WORKPLAN rows.
next:    Kam reader session on the 300+300 (design note has the power); gamma_conditional
         from adjudicated triples once 12 epochs exist; regression referee verdict ->
         launch 2020/2022/2023 or bisect on GPU; ledger consolidation rung.

## 2026-09-08  harvester-heal2017-score-stack-generalised
goal:    answer "precision/recall of the current recipe per year" honestly; use the
         campaign's idle hours on the healer's next dependency (a stack that is not
         fixed at eight epochs).
did:     TABLE from arm_metrics at matched_p75 vs C-CAP 2021, 14 acquisitions; found
         the tracked qc_indep_report.csv had ZERO rows for any recipe arm — 285 rows /
         9 days behind the lake, hand-copied, no rung. harvest_qc_indep.py LANDED
         (1279019): byte copy + three gates (shrink / header / double-live), each
         shown to fire; landed.py rung 7. heal_2017 SCORED vs C-CAP 2021 locally
         (torch-free, 70 min): R 0.796 / P 0.753 at the held cut beside of_2017's
         0.788 / 0.753 — UNDETERMINED; sweep shows the WEAK_CALIBRATION cliff
         (recall 0.70 at u8 124 = the delivered cut, 0.32 two steps up). heal_2023
         landed on healD (BE12, held-out F1 0.813), healD stopped; heal_2020 trained
         clean (AE11, F1 0.954 at 0.50 — the 2017 divergence did not recur).
         STACK GENERALISED (b7ee58c, Opus workflow + referee PASS): heal_stack_build.py,
         census warp extracted (2009+2011s rebuilt cellwise identical), --stack/--out
         on four instruments, every default cmp IDENTICAL. 10-EPOCH TRIAL on real data
         (scratch only): BLIND 0; no-change triples 124->220, healer removes 173;
         closing launders 7/12 in-interval where the healer launders 0.
decided: 10-epoch numbers are PROVISIONAL and untracked; the experiment's verdict waits
         for the 12-epoch build (heal_2020 postproc + heal_2022 on healC).
killed:  "the delivered-cut rows do not exist for recipe arms" (they did — the tracked
         copy was stale; harvested now).
bugs:    heal_closing_baseline: laundered_in_interval (13-14) exceeds
         n_eligible_in_interval (12) on the 10-epoch stack — count and denominator are
         not the same unit; invisible on 8 epochs where both read 4. heal_gap_spectrum's
         crosscheck and crown columns read the TRACKED 8-epoch heal_vs_gold / crown
         rasters regardless of --stack (MISMATCH printed; needs --heal-vs-gold plumbing).
files:   qc/instruments/{harvest_qc_indep,heal_stack_build}.py + tests; census,
         temporal_heal, heal_vs_gold, heal_gap_spectrum, heal_closing_baseline;
         phase4/qc/qc_indep_* (503->506 rows), curves/efb2813b8a46.csv, arm_metrics,
         year_scoreboard; claims.yaml (72/86/88); landed regens; WORKPLAN rows.
next:    referee + fix the two instrument defects; 12-epoch build; rebuild
         heal_vs_gold / closing / spectrum / fill-audit on it; arm verdicts in
         experiments/heal_infill_2017_2023.yaml (carry WEAK_CALIBRATION for 2017);
         Kam: reader session on the 300+300, the two registered decisions.

## 2026-09-08  healer-closed-out-and-tabled
goal:    Kam: "bring today's healer work to a close, then table it so we can improve the
         system so work like this can move faster"; then "any runtime that is almost
         finished can continue; don't start any new epochs."
did:     DEFECTS FIXED (802a0c8, Opus workflow + referee): closing baseline's
         laundered_in_interval counted (point, epoch) fill EVENTS against a per-point
         denominator (13 of 12 on 10 epochs; both read 4 on 8, so invisible) — both per
         point now, build() refuses any count above its denominator, mutation-tested
         (old code 4 vs 2); the same unit error in laundered_terminal fixed (inert).
         Spectrum given --heal-vs-gold and an explicit crown SKIP with EMPTY cells.
         Every default byte-identical to the tracked CSVs. healD stopped after
         heal_2023 landed (BE12, F1 0.813). heal_2020 landed on healC (AE11, F1
         0.954; VERIFY:postproc OK 19:28Z); heal_2022 NEVER STARTED — healC idled with
         its exec channel lost (404); stopped via the Drive mailbox (queue+engine
         SIGTERMed, watchdog ended the VM; 0 active runtimes). Experiment set
         status: tabled with an explicit NO VERDICT + per-arm notes (2017
         WEAK_CALIBRATION + C-CAP score; 2020 clean; 2023 clean; 2022 not run);
         generated queue retired (regenerates on resumption). ELEVEN-EPOCH STACK
         cached at D:\edmonds-pipeline\heal_stack_2m.npz (8 trend8 + heal_2017/2020/
         2023, date-ordered; parity: 8 shared epochs identical to the published
         cache; 6.6 MB). landed.py: registry +1, harvests, STATUS; ordering fix —
         the experiment index is regenerated BEFORE the consistency gate (it went
         red on every landed run that added registry rows, twice today).
         WORKPLAN: healer TABLED row + SYSTEM WORK queued in leverage order.
decided: (Kam) no new GPU runs; healer science paused until the system work lands:
         (1) measured-file registry gated in the suite, (2) synthetic rehearsal lake
         of non-default shape every instrument must run on, (3) append-only lake
         writes + harvest-on-land, (4) versioned object storage when decided.
killed:  nothing scientific — the decision rule was NOT evaluated; the 10-epoch
         scratch numbers stay provisional and untracked.
files:   qc/instruments/heal_closing_baseline.py, heal_gap_spectrum.py + tests;
         docs/SCHEMAS.md; experiments/heal_infill_2017_2023.yaml + INDEX;
         pipeline/queue_heal_infill_2017_2023.yaml (removed); qc/landed.py;
         WORKPLAN.md; run_registry + harvests + STATUS; memory note
         close-out-then-table-for-system-work.
next:    the system work above (next session); on resumption: regenerate the queue,
         run heal_2022, rebuild the stack to 12, then heal_vs_gold / closing /
         spectrum / fill-audit for the experiment's verdict; Kam: reader session on
         the 300+300, the two registered decisions (augmentation seeding, selection
         metric).

## 2026-09-08  logging-blocks-fixed
goal:    Kam, after scrapping the redesign: "precise fixes to ensure our logging works
         appropriately ... targeted fixes that we have identified as blocks today."
did:     FOUND THE STALL: healC's nohup log (mirrored late) shows heal_2020 VERIFY:postproc
         OK at 19:28Z then silence; the job-level verify() re-opened the 4.1 GB prob
         raster through FUSE with no announcement and no bound (the 2018s_fx class).
         verify() now reuses this launch's VERIFY:inference verdict on a size match
         (postproc never touches the prob raster) and announces the slow path before any
         read. queue_ledger._status_write: shared-ledger fallback REMOVED (refuses out
         loud when STATUS_OUT is unset — the erasure mechanism itself). landed.py: an
         unmounted lake FAILS unless --no-lake is passed on purpose. heal_stack_build
         progress lines flush. qc/test_queue_logging_fixes.py pins all four, each fired
         on the input that slipped. Full ladder green (59f6e8f).
decided: Kam: the repo redesign is SCRAPPED ("I got carried away ... we have a decent
         system going"); overhaul branch deleted; system-work rows in WORKPLAN are
         optional hardening, not a mandate. Appending CSVs on Drive is fine as a
         convention for small laptop-side tables; it closes only the erasure class.
files:   pipeline/phase4_train_queue.py, pipeline/queue_ledger.py, qc/landed.py,
         qc/instruments/heal_stack_build.py, qc/test_queue_logging_fixes.py,
         qc/test_status_discovery.py.
next:    nothing queued; healer stays tabled; the reused-verdict path validates itself
         on the next campaign launch (watch for "reusing VERIFY:inference" in the log).

## 2026-09-09  backbone-sweep-and-encoder-bases
goal:    Kam: benchmark the 101, run resnet18/50 on the same Tier-1 sample arms overnight
         on two A100s with canaries; "I don't want to wake up and find out we had an issue
         with logging." Then: "Begin ResNet-50 base and the ResNet-18 base."
did:     --encoder run flag (b054128; config append-only, BENCH MATCH), 101 BENCHMARK table
         phase4/qc/backbone_benchmark.csv (nine arms at matched_p75; noise floor 0.0085
         recall from the 2011s reseeds). PREMISE CORRECTED: fine-tunes warm-start from the
         Phase-3 2020 base (resnet101) - small encoders started from ImageNet + random
         decoder. SWEEP RAN: bb18 nine arms clean; bb50 six, one train FAIL (Drive EIO on a
         stat, epoch 17), runtime reclaimed at 10:11Z mid-tile, relaunched bb50b, resumed
         correctly, last arm cut on Kam's stop. LOGGING ISSUES FOUND: (1) two VMs clobber
         the shared semantic_eval_report.csv (bb18 2006s rows lost from live AND archive;
         metrics safe in step logs) -> eval_rows_from_logs.py (4ca40c4); (2) resume wrote
         false VERIFY MISSING for five steps-subset jobs; (3) exec handle 404 hours into a
         run. PROVISIONAL READ (evaluate IoU at 0.5, held-out): small encoders worse,
         ~10x noisier across seeds (0.08 vs 0.006), NOT faster (train I/O-bound, ran to the
         epoch cap) - the warm start dominated. BASES: Phase-3 hand-crown tiles
         materialized as tagged tilesets (748 index rows; 141 orphan tiles not copied;
         9035b4b); base18 IoU 0.754 AP 0.919 in 44 min, base50 IoU 0.765 AP 0.930 in 59 min
         vs the 101's 0.772 / 0.944 (Phase-0 init; split not byte-identical). DEBUGGED
         (f85bb3e, referee PASS, BENCH MATCH): per-run eval files + verify evidence; resume
         re-check mirrors verify(); EIO/ENOTCONN retry around publish probes; md5 wait
         logged per poll; lost handle = CLI kernel culled after 1.3-6.3 h idle, not ours
         (documented, mailbox fallback).
decided: encoder_bases COMPLETE, neither promoted; each is the warm start for a
         backbone_sweep re-run (--ckpt sem_best_2020_base{18,50}.pt). backbone_sweep
         stays queued for that re-run; last night's arms are the ImageNet-start record.
killed:  "small encoders are noisier/worse" as an encoder claim - it was the warm start.
bugs:    SECRET EXPOSURE (Kam to act): ~/.config/colab-cli/colab.log holds the SA private
         key + gh token in plaintext (every bootstrap execute_request logged at DEBUG); a
         grep of it persisted ~272 KB incl. the key into this session's tool-results file
         bzwe19wcn.txt (deletion blocked by the classifier). Rotate both, delete the file,
         truncate the log.
files:   phase4seg/{cli,ckpt,core,config,common,names}.py, queue_verify.py,
         phase4_train_queue.py, vm_ops.py; qc/instruments/{backbone_benchmark,
         eval_rows_from_logs,phase3_tiles_as_tileset}.py + tests; experiments/
         {backbone_sweep,encoder_bases}.yaml; queues; phase4/qc/{backbone_benchmark,
         eval_from_logs,eval_report_gaps}.csv; COLAB_AUTONOMY_SETUP.md; known_failures.
next:    Kam: rotate keys; go/no-go on the warm-started sweep re-run (18 arms, ~2 A100
         x 5-6 h at last night's pace; first live test of the per-run eval files);
         then the LOSO inference+scoring pass for the pre-registered metric.

## 2026-09-09  warm-started-resnet50-scored
goal:    Kam: "Yes to scoring" - the pre-registered LOSO matched-cut read for the seven
         warm-started resnet50 arms.
did:     A100 quota refused at first (A100, L4 rejected; T4 unavailable x6) until Kam
         loaded credits; seven sample-block inferences on one A100 (2-17 min each; the
         job-level verify REUSED the inference verdict every time - the stall fix live).
         wb50_2016_in05 FAILED: RasterioIOError on the staged CHM. Diagnosed by an Opus
         workflow (my eviction hypothesis was WRONG): the 8 reader threads of one process
         each staged the 6 MB CHM (below the staging-lock floor; every cache guard was
         pid-keyed), and a sibling's publish unlinked the file another had just opened;
         reproduced unhooked 7-of-8. Fix (0080cce): per-key in-process lock, pre-clear
         refuses under any live pin, bare atomic replace; 9 tests, 4 fail on the old
         code; BENCH MATCH. Validated live on the re-run: one stage line (1.9 s), cache
         hits, no error. Scored 7/7 with the Tier-1 shape (qc_indep --aoi sample-test),
         harvested (+7 curves). RESULT at matched_p75: resnet50 ABOVE the 101 on every
         arm (+0.014..+0.082 recall), seed spread 0.011 vs 0.0085, null pair agrees;
         positive pair DISAGREES (+0.007 vs +0.075) because the 101's 2016 base (0.669)
         was suspect-low and resnet50's sits at the ceiling (0.751).
decided: backbone_sweep -> needs-kam: license recipe search on resnet50 treating the
         2016 lidar effect as unresolved (reseed the 101's 2016 base first), or hold
         the rule literally. ResNet-18 phase 2 gated on that.
bugs:    editable install lost its module map mid-session (champion import) - pip -e
         reinstall; a launch chain proceeded past a failed step because pipefail did
         not bind inside the heredoc chain - the runtime (wb50s3) never started its
         queue and was stopped; relaunched cleanly (wb50s4).
files:   phase4seg/scratchcache.py, common.py + tests; queue_wb50_score.yaml;
         qc/instruments/score_wb50_loso.py; experiments/backbone_sweep.yaml;
         phase4/qc/arm_metrics.csv, curves/ (+7), run_passport, registry.
next:    Kam's call above; then ResNet-18 phase 2 or the 2016 base reseed; key
         rotation still open.

## 2026-09-10  resnet18-licensed-for-recipe-search
goal:    Kam: "move forward with using resnet 18 to refine the recipe" - run the same
         seven-arm check warm-started from base18 and score it.
did:     wb18a/wb18b on two A100s 01:12-03:50Z, seven arms clean (train 14-31 min);
         wb18s sample-block inference 03:55-05:04Z (in05 clean - cache fix confirmed a
         second time); scored 7/7 with the Tier-1 shape, harvested (+7 curves). READ at
         matched_p75: resnet18 at or above the 101 on every arm (2011s equal 0.720-0.727,
         2016 base 0.743 vs 0.669, 2020 0.740 vs 0.640), seed spread 0.0069 (< the 101's
         0.0085), null pair +0.006 inside the floor, positive pair +0.008 (the 101's lidar
         "gain" again absent). vs resnet50: ~0.03 lower on 2011s, equal 2016, higher 2020.
decided: backbone_sweep COMPLETE: recipe refinement runs on resnet18 from base18; the
         101 is reserved for confirmation + deliverables; 2016 lidar effect UNRESOLVED
         until the 101's 2016 base is reseeded (on the board).
files:   experiments/backbone_sweep.yaml; phase4/qc/arm_metrics.csv, curves/ (+7);
         registry/harvests.
next:    first recipe experiments on resnet18 (Kam picks the hypotheses); the 101's
         2016 base reseed; key rotation still open.

## 2026-09-10  overnight: heal_2022 + 12-epoch healer reads, EXP-H1 complete
goal:    Kam (overnight brief): bring the surveys closer for time-series analysis
         (harmonization H1/H2 on resnet18) and work the healer to its 12-epoch verdict.
did:     heal_2022 landed (heal22, BE25, maxprob 0.776); 12-epoch stack built (parity on
         the 8 shared epochs); temporal_heal / heal_vs_gold / closing / spectrum /
         fill-audit run on it -> phase4/qc/*_12ep.csv (SCHEMAS "_12ep"). H1 five arms
         inferred on harmh1s, scored vs BOTH C-CAP refs (2011s/2016/2020 bases + 2016_in05
         re-scored vs 2016 locally), harm_spread rebuilt; harmh1s stopped. H2 arms on
         harmh2 (2019s base AE20 + 2019s_in16 AE20 clean; 2016_in16 running).
read:    HEALER - BLIND inside 2016-2024 is zero; laundered/censored 0/42 (no power, as
         amended); no-change triples 240/327 removed vs 99/124 on 8 epochs (count up,
         share down 6.4 pp: UNDETERMINED on the rule as written); MECHANISM: HEAL tier
         needs a lidar epoch downstream (tier_for, LIDAR_LAST=2016), so the dense stack
         writes NO canopy inside the Panel A window - only REVIEW/IGNORE. The hypothesis's
         first clause is false about the instrument as built. H1 - base spread 0.140 (vs
         2021) / 0.154 (vs 2016): K1 and K2 both NOT fired, premise stands; 2019n is now
         the worst survey (0.603), not 2006s; in16 rows show the epoch-leak signature
         (2016-ref spread collapses to 0.013) - to be read at H2-K1/K2.
decided: nothing promoted. heal_infill verdict stays null pending Kam's fill-audit read
         (598-unit worksheet redrawn on 12 epochs). REVIEW-tier resolution by size
         trajectory is the build that would let the gold score a fill - Kam's call.
files:   experiments/heal_infill_2017_2023.yaml, harmonization_h1_h2.yaml; docs/SCHEMAS.md;
         claims.yaml (curves 116); phase4/qc/*_12ep.*, harm_spread.csv, arm_metrics.csv,
         curves (+14), tilesets (+5), harvests.
next:    H2 finish -> stop harmh2 -> queue_harm_h2_score -> K1/K2/K3/K4 + verdict; morning
         summary; key rotation still open.

## 2026-09-10  EXP-H2 KILLED (epoch leak + change laundering); crown state model pre-registered
goal:    close harmonization H2; start method 1 (Kam: "I'm on board for method 1").
did:     H2 five arms trained on harmh2 (all clean, AE20/BE25/BE12); A100 refused 6x
         (Service Unavailable, after Kam loaded credits) -> scored on an L4 (harmh2s2,
         5 arms 3-28 min each); harmh2/harmh2s2 stopped, no runtimes live. Four arms
         scored locally vs both refs (2020_in16's 999 MB raster still mirroring; waiter
         armed). K2 instrument run on real rasters. heal_2022/2023 scored citywide for
         crown-model rates; heal_2020 read faulted on the mirror mid-raster, rescoring.
read:    H1 CONFIRMED (base spread 0.140/0.154, no kill). H2: converges (-0.084/-0.119)
         BUT K1 LEAK fires both refs (0.043/0.019 > 0.0069), K2 CHANGE LAUNDERING fires
         every year (+0.035..+0.082 extra call-rate rise on lidar-certified gain cells),
         K3 same-flight gap unchanged. Verdict on harmonization_h1_h2.yaml, decided.
decided: fixed-epoch structure channel is a time-stamped prior, not a harmonizer; the
         workstream needs a survey-invariant input or it stops. crown_state_model.yaml
         pre-registered (K1-K4, referee split, dated amendment after the implementer's
         dry-run); instrument + 15 tests landed (9673a03), no model run yet.
files:   experiments/harmonization_h1_h2.yaml (verdict), crown_state_model.yaml;
         phase4/qc/harm_spread.csv, harm_change_laundering.csv, arm_metrics, curves,
         qc_indep harvests; qc/instruments/crown_state_model.py + test.
next:    heal_2020 rate -> referee runs crown_state_model + scores vs gold (K1-K3),
         K4 rate sensitivity incl. 2005/2016 lidar rates; Kam: GitHub push, key rotation.

## 2026-09-10  crown state model v1 KILLED by a unit defect; v2 pre-registered
goal:    referee the pre-registered crown state model on the real 12-epoch stack.
did:     all twelve delivered-cut rates in place (heal_2020/2022/2023 scored citywide;
         heal_2020 needed a rescore after a mid-raster read fault on the mirror). Opus
         referee ran the model (222,435 crowns, ~100 s), wrote crown_state_vs_gold.py
         (+tests, mutation-tested laundering counter), scored vs gold, ran 20 placebo
         draws; K4 not evaluable (no 2016/lidar-referenced rows for the stack tags).
read:    K1 FIRES (3 of 11 at-risk on-crown losses laundered, 12 epochs); K2 111/327 vs
         the healer's 240/327; K3 placebo identical in all 20 draws. MECHANISM (referee,
         demonstrated): emission_fp inverts pixel-measured precision with crown-pooled
         prevalence -> f >= r in 11/12 epochs, saturating in 8 -> observing canopy LOWERS
         P(canopy) -> Viterbi collapses to two constant paths citywide; first_seen never
         moves. Pixel-level prevalence gives f 0.02-0.11 < r everywhere. Also: 60% of the
         gold points are off-crown - the crown unit sees 40% of the gold.
decided: v1 verdict KILLED AS RUN on the yaml (decided). crown_state_model_v2.yaml
         pre-registered BEFORE the fix is written: pixel-level plug-in, a hard f<r gate
         shown FIRING on the v1 derivation, loud warning; kills and denominators
         unchanged; K4 stays not evaluable until 2016/lidar-referenced rates are scored.
         Implementer (Opus) launched on v2; referee to follow.
files:   experiments/crown_state_model.yaml (verdict), crown_state_model_v2.yaml;
         qc/instruments/crown_state_vs_gold.py + test; phase4/qc/crown_state_vs_gold.csv,
         crown_state_placebo.csv, crown_state_intervals.csv, crown_state_posterior.npz.
next:    v2 implement -> referee -> verdict; score stack tags vs ccap_2016 + lidar
         binaries (CPU) for K4; 2020_in16 H2 arm scores when its raster mirrors.

## 2026-09-10  crown state model v2 KILLED — the crown unit is the wrong unit for the gold
goal:    referee the pre-registered emission-unit fix (v2).
did:     Opus implementer: pixel-level prevalence over the whole valid grid (crown-covered
         measured equivalent to the defect, 0.82-0.96, recorded in a dated amendment), hard
         f<r gate, loud clip warning; 33 tests. Opus referee: gate PASSES on the real stack
         (f 0.020-0.106) and FIRES on the v1 derivation (11/12 epochs); model 103 s, 12
         distinct paths (v1: 2), first_seen spreads 2015-2024; scored vs gold; 20 placebo
         draws; K4 not evaluable (2016-referenced rates still scoring).
read:    K1 WORSE: 11/11 at-risk on-crown losses laundered (33 epochs, all 2021-2024, 26
         with the crown observed ABSENT) - at r~0.61 one absence is only LR 2.5, four are
         39:1, and q_loss 0.02 costs 49:1, so the persistence prior beats four absences.
         K2 = 111/111 on-crown = 111/327 on the pre-registered denominator - a CEILING:
         216 of the 327 triples are off-crown, unreachable by any crown model. K3 flat
         for the same reason.
decided: v2 KILLED (yaml, decided). Structural, not tuning: the crown unit sees 40% of
         the gold and cannot beat the healer on K2 by construction; pixel-measured
         recall understates a present crown's observability. Next design is Kam's call:
         pixel-unit model (where the gold lives) and/or crown-level rates measured on
         the 475 on-crown no-change gold points (spends the gold twice - dev-set caveat).
         Neither built. Stale help text fixed; emission_fp's silent EPS return noted.
files:   experiments/crown_state_model_v2.yaml (verdict); phase4/qc/crown_state_v2_vs_gold.csv,
         crown_state_v2_placebo.csv; qc/instruments/crown_state_model.py (help text).
next:    Kam decides the unit; K4 rate scoring lands (12 epochs vs ccap_2016, CPU);
         2020_in16 H2 arm scores when its raster mirrors; GitHub push + key rotation (Kam).

## 2026-09-10  brainstorming brief: temporal + spatial consistency (source of truth)
goal:    Kam: "wrap this all up into a brain storming brief for temporal and spatial
         consistency ... a source of truth."
did:     Reports/TEMPORAL_SPATIAL_CONSISTENCY_BRAINSTORM_2026-09-10.md - measured
         constraints (healer 12ep, H2 kill, crown v1/v2, what exists for space and
         buildings, the MUSCLE-Net paper) separated from the proposed design (three axes
         of agreement, development as a dated local prior, lidar as teacher in three
         roles, deep supervision + resolution curriculum, the LR arithmetic that links
         precision/recall to year-of trust), the kills every design must carry, four
         open questions for Kam, a cheapest-first order. Nothing in it is built.
decided: nothing; the brief is the discussion's home. First move when Kam says go:
         the building-proximity enrichment count on the gold (CPU, ~1 h).
files:   Reports/TEMPORAL_SPATIAL_CONSISTENCY_BRAINSTORM_2026-09-10.md; WORKPLAN row.
next:    Kam's answers to brief section 6; K4 rate scoring finishing; 2020_in16 raster.

## 2026-09-10  K4 rates landed: all twelve stack epochs scored citywide vs C-CAP 2016
did:     12/12 epochs scored (CPU, ~6 h incl. one mirror-fault retry), harvested into
         qc_indep_report + arm_metrics (scored_live 590 rows); crown_state_model
         --rates-ref ccap_2016 passes its emission gate on all 12. Brief section 2.3 and
         the v2 yaml (extra) updated; the v2 verdict stands (K4 was not evaluable then).
next:    successor designs run K4 from the start; lidar-referenced rates still absent.

## 2026-09-10  a 999 MB raster died with its runtime: the stop did not wait for the upload backlog
what:    wb18_2020_in16's sample-block raster: ledger VERIFY OK 16:13Z on harmh2s2, but
         the Drive copy was "NOT CONFIRMED" (md5 absent after 1 s) and I stopped the
         runtime on the verify row. Twelve hours later the file is absent from Drive
         (Drive API search: not found; every sibling found). VERIFY reuses the inference
         stat (size match, no re-read) - it verified the LOCAL file, not the published one.
fix:     vm_ops stop is drain-aware: waits on the heartbeat's vfs_dirty_gb (DRAINED /
         NO_HEARTBEAT / STALE proceed with a printed verdict; TIMEOUT refuses unless
         --force); 3 tests; known_failures.yaml entry. The arm is re-run on an L4, never
         salvaged; the H2 verdict does not depend on it.

## 2026-09-11  resume self-heal: a skipped step whose artifact is GONE is re-run
what:    the rerun launch (harmh2s3, L4) resumed from the merged ledgers, saw inference
         OK for wb18_2020_in16, skipped it, re-checked the raster (stat: GONE), wrote
         VERIFY MISSING and ENDED - an idle L4 and still no raster. Honest, not useful.
fix:     phase4_train_queue: a skipped inference step whose prob raster no longer exists
         on the lake is re-run, not skipped (_artifact_gone, one stat, no re-read;
         steps-subset jobs exempt); test added. The live VM runs the pre-fix clone, so
         the queue was re-launched on it with --no-resume --only <job>; monitor armed.

## 2026-09-11  2020_in16 raster re-inferred and PUBLISHED; the drain gate fired live
did:     harmh2s3 (L4) --no-resume rerun: inference 43 min, VERIFY OK 04:53Z. The new
         drain-aware stop found 0.999 GB still dirty on its first poll, waited, reported
         DRAINED, then stopped. Drive API search: the raster exists (999,115,669 B,
         04:53Z) - the first launch's copy never did. Local scoring waits on the Windows
         mirror (up to 8 h); the H2 verdict does not depend on it.

## 2026-09-11  H2 table complete (5/5 arms scored); verdict unchanged
did:     mirror delivered the re-published 2020_in16 raster in 1 min (the first never
         existed on Drive); scored vs both refs; harm_spread 98 rows. Five-year in16
         spread 0.056 / 0.081 vs base 0.140 / 0.154; convergence -0.084 / -0.073; K1/K3/K4
         unchanged. Completion note on the yaml (extra); verdict untouched.

## 2026-09-11  session end: work tree finished for integration
did:     the two byte-for-byte freshness tests (backbone_benchmark.csv, harm_spread.csv)
         now compare CRLF-normalised bytes - a fresh Windows checkout (autocrlf=true, no
         eol= by design) failed them on line terminators alone (flagged by the docs
         session); the LF-only render property is still asserted separately. Generic
         ingestion sandbox scripts written on request earlier tonight were removed from
         the repo root (unrelated to the pipeline). landed.py run for the final registry /
         harvest / digest refresh. crown_state*_intervals.csv and *_posterior.npz are
         gitignored (18 MB products), so the docs branch will not see them after merge.
state:   no runtimes live; no loops or crons; branch work/20260906-healing-tool ready
         for Kam to push to GitHub and merge into main.
next:    Kam: push + merge; key/token rotation; fill-audit worksheet; brief section 6.

## 2026-09-12  fix: the CRLF-safe compare was committed with REAL CR/LF bytes inside the literal
what:    8411777's patch wrote b"<CR><LF>" instead of b"\r\n" in the two freshness tests
         (an escaping slip, repeated by two shell-heredoc repair attempts); ruff flagged
         invalid syntax on the next full ladder. landed.py's pytest rung is a SUBSET and
         did not collect those files - check.py is the definition of done and was skipped
         at that commit. Fixed by a script file (no shell escaping), verified byte-exact;
         both tests pass; full fast ladder green before this commit.

## 2026-09-13  litkb P1 foundation: built, refereed three times, ACCEPTED
goal:    Kam: design + implement literature knowledge base (Postgres 18 + pgvector); P1 = foundation.
did:     lit-review docs branch merged to main (c67e30b, Kam pushed). Design rev 2 answers Opus referee.
         C++ Build Tools (C: disk pre-check was the real failure) -> pgvector 0.8.6 built + installed on PG18.
         Tablespace litkb_d on D:. Migrations 0001-0012: versioned pointers + compare-and-set writes,
         promote prepare/commit/rebase, roles owner/reader/writer/promoter/ingest/test, workstream tokens
         (hash only stored), catalog grant guard. 3 referee passes (D-, E-, F- defects) all fixed;
         independent acceptance re-ran referee mutations + 5 new: all caught (bd0fa6e).
decided: PG18:5433 (uuidv7); DB on D: (C: full); orchestrator runs promote commit after merge on main
         (tool refuses, DB cannot run git); nightly pg_dump; 2nd-session sign-off; year +-1 only with
         title+author; binding-refused scans wait for OCR; held chains rebased; head-only rebase evidence;
         token + ingest role before P2; secrets ACL accepted risk; P1 waited for pgvector.
killed:  winget upgrade of partial Build Tools (exit 1, "already installed"); unelevated --passive (5007);
         Python-only merge check claimed as DB guard (reworded); sequential tests as race evidence.
files:   Scripts/LITERATURE_KB_DESIGN_2026-09-13.md, Scripts/pipeline/litkb/, Scripts/qc/test_litkb_p1.py,
         Scripts/qc/instruments/litkb_p1_mutations.py, Reports/LITKB_P1_*.md, Reports/LITKB_TOOL_FACTS_2026-09-13.md,
         Scripts/decisions.yaml (litkb-p0-foundation). Secrets outside repo: pgpass.conf, secrets/litkb_*.pgpass.
next:    P2 admission + acquisition (litkb ws open CLI; aa_fetch/paper-search adapters; Averkov/Higham replay kill);
         nightly pg_dump task not built; staged-secrets ladder check not built; §15.9-15.11 before P4/P5.

## 2026-09-15  litkb-p4-adapters-merged
goal:    merge the three refereed P4 adapter branches into the litkb branch, proving each step; I
         wrote none of them.
did:     --no-ff x3 in order: inventory cc36b82 -> d621cfe, GROBID 8f985e5 -> cae333a, Docling
         5b26768 -> 14e3091. Three textual conflicts (extract/__init__.py twice, requirements-litkb
         once), all "keep both". After each merge: --sites, check.py --fast under
         LITKB_TEST_DB=litkb_test_w6 (only crown_state_model fails, as expected), and the branch's
         own tests -- inventory 60 passed; GROBID 54 passed live with the service up in WSL then
         stopped; Docling 40 passed live on the CPU venv. Harness --workers 4 --worker-dbs 1,2,6,9:
         155/155 fired, 43.0 min. Inventory --force census reproduces the tracked CSV byte-identical
         except `seconds`. Migration 0016 applied to litkb; P3 gate re-run read-only unchanged at
         713/243/120/10/0 PASS.
decided: the three page_frames copies are NOT collapsed at the merge -- each is what its referee
         measured against, and refactoring all three with no referee retires refereed numbers
         (3.4c). Recorded as an open item due before stage 5.
killed:  "the throughput instrument refuses a run with no rate or peak RSS -- fires both tools": the
         GROBID instrument has no refusal path at all. Row corrected to Docling-only. Also: the
         brief's premise that three forked copies of the design doc needed reconciling -- only
         GROBID ever edited it.
files:   Scripts/LITERATURE_KB_DESIGN_2026-09-13.md (§7.1, §12.2, §12.10, §14 P4 status),
         Reports/LITKB_P4_MERGE_2026-09-15.md, Reports/LITKB_P3_REPORT_2026-09-15.md,
         Scripts/qc/instruments/litkb_p2_mutations.py (two Docling SINK_ALLOW rows).
next:    the throughput gate (GROBID at >1 pool size with measured per-worker RSS; Docling on the
         corpus; metrics into extraction_runs.metrics), stage 5 reconciliation, and collapsing
         page_frames to one home. GitHub push refused by the permission classifier -- Kam's call.

## 2026-09-15  litkb-stage5-reconciliation
goal:    build P4 stage 5 (reconciliation) and the P5 ingest schema, after first collapsing the
         three page_frames copies the merge left open.
did:     one frame reader: inventory.page_frames(pdf_path, error=...) is the only body, grobid's
         and docling's call it and differ only in the exception class. Referee numbers reproduce
         (Alwan p2 dx 10.3449 / dy 9.052; Hall p12 still refused) and the three now return equal
         dicts. extract/reconcile.py: IoU matching in the mediabox frame, one kind vocabulary,
         Docling's order and cell grids, GROBID's references and figure captions, native-layer
         text with per-field provenance, disagreements KEPT. 0017_extraction.sql (additive):
         table_cells, extraction_disagreements, file_current_run, provenance/text_source/source on
         blocks, coverage columns on pages, five ingest-only SECURITY DEFINER writers, triggers so
         the invariants hold on the direct-INSERT path too. extract/ingest.py: one transaction per
         file, idempotent by (sha256, pipeline version), a not-ok run's rows cleared in the
         resuming transaction. Ran on the 5 gate papers + Ogata_1998 (scan/OCR) + Almon_1965
         (cover sheet): 570/211/314/1323/14367/388/437 blocks, coverage 0.9987-1.0000 on text
         pages, N/A on image-only. 21 harness rows R51-R521, all fire.
decided: the inherited-/MediaBox case is REAL corpus data (16 pages in two files, Platanios_2014
         and Vincent_1993) -- Docling's old copy would have TypeError'd on every one. 0017 NOT
         applied to litkb: the tables.cells retirement trigger changes an existing column's
         meaning, so it is a referee's call.
killed:  my own two writer defects, both found in review and both passing every gate because the
         tests ran the CHECKER on hand-built blocks. (1) reading order was re-derived from
         geometry and interleaved two-column pages -- 21 of 23 snippets out of order on
         Benedek_2015 pp2-3; the order now travels on the block. (2) native text was joined from
         the ink, so every space was gone ("Contentslistsavailable"); coverage could not see it
         because its denominator is the ink. Also killed: "drop the largest block" as a coverage
         kill -- on Alwan p4 it moves coverage 1.0000 -> 0.9723, because canonical blocks overlap
         and the metric asks only whether SOME block is responsible. That limit is in the report.
files:   Scripts/pipeline/litkb/extract/{reconcile,ingest}.py, .../db/migrations/0017_extraction.sql,
         Scripts/pipeline/litkb/extract/{inventory,grobid,docling}.py, Scripts/qc/test_litkb_reconcile.py,
         Scripts/qc/instruments/litkb_stage5_run.py, Scripts/qc/instruments/litkb_p2_mutations.py,
         Scripts/qc/test_litkb_p1.py, Scripts/qc/test_status_discovery.py,
         Scripts/LITERATURE_KB_DESIGN_2026-09-13.md, Reports/LITKB_STAGE5_INGEST_2026-09-15.md,
         Reports/litkb_stage5_2026-09-15.csv.
next:    a referee: no pre-committed gold exists, so all four thresholds are author-chosen and
         UNVALIDATED. Then 0017 on litkb, the throughput gate, stages 6-7.

## 2026-09-15  litkb-p6-merge
goal:    merge the refereed references branch (P6: stage 6 + the Semantic Scholar leg) into
         work/20260913-literature-kb and prove the merged tree. I wrote neither side.
did:     work/20260915-references e176707 merged --no-ff as 7b8afd7. ZERO textual conflicts: the
         three the brief predicted did not fire, because the litkb side never touched
         admit/resolver.py in 8f985e5..8cbed38 and P6 touched neither requirements-litkb*.txt nor
         .gitignore. The harness table auto-merged -- P6 added a tests= kwarg and two registrars,
         the litkb side had rewritten the RD rows -- and the design's stage-6 text has one home
         (P6's two blocks under the §7 stage table; the litkb side's additions are in §7.1/§12/§14).
         Proofs on the merged tree: --sites PASS (75 sites, 72 covered, 3 equivalent; 16 sinks);
         P6's tests 191 passed / 3 skipped, the 3 being litkb_live, so cache-only; the 293-reference
         table 20 resolved / 23 ambiguous / 250 unresolved with requests_total 0; the P3 gate
         read-only on litkb 713/243/120/10/UNEXPLAINED 0, PASS, and litkb_p3_diff.csv regenerates
         with an empty git diff; the full parallel harness --workers 3 --worker-dbs 1,6,9,
         226/226 fired in 115.5 min.
killed:  one defect the merge surfaced and neither branch could see -- s2.py::request::redact is a
         call site of the redaction family, which came under the per-call-site rule on the OTHER
         side of the merge. --sites failed with one PROBLEM line on 7b8afd7. Row P7-RD19 plus a
         test (register a key, have the transport echo it in a status-0 body, assert <KEY>): FIRED
         in the full harness. Fixed in 98f9d1b. Same class as 11db0fa, from the other direction.
decided: NO migration. "references" and citation_mentions come from 0002, candidates from 0001, so
         the tables-do-not-exist trigger never fired and litkb stayed read-only. The live ingest was
         not run either, and could not be: extract/ingest.py has no reference loader at all. Two
         gaps named for whoever writes one -- references.resolution's CHECK has no 'ambiguous'
         (19 of 658 rows are), and edges.jsonl has no table. That is also what references.py:8's
         "the citation-graph columns are applied at merge" was pointing at; this merge applied none.
measured: check.py --fast under LITKB_TEST_DB=litkb_test_w6 fails THREE, not the one allowed:
         crown_state_model plus test_litkb_inventory's two census pins. git diff 8cbed38..HEAD over
         that test, extract/inventory.py and phase4/qc/litkb_inventory.csv is EMPTY -- the corpus
         moved, not the tree. All 22 extra PDFs are in Literture\_litkb_staging\filed, litkb's own
         acquisition store, which sits inside the census root and is excluded by nothing; the five
         newest are timestamped 18:12-18:13 today and are splink/entity-resolution papers, i.e.
         another session's work landing in a shared store. So it is a corpus-DEFINITION question
         for §12, not a re-pin job, and re-pinning refereed numbers unrefereed is 3.4c.
files:   Scripts/qc/test_litkb_s2.py, Scripts/qc/instruments/litkb_s2_mutations.py,
         Reports/LITKB_P4_MERGE_2026-09-15.md ("P6 merged"), Scripts/CHATLOG.md.
next:    a referee for the merged tree if one is wanted; the reference loader (with the resolution
         CHECK and the edges table decided together); stage 7.

## 2026-09-15  litkb-first-use-friction
goal:    close the friction the FIRST real use of the knowledge base exposed. The linkage review
         (LITKB_LINKAGE_REVIEW_2026-09-15.md §8) is a defect list measured on one session that tried
         to follow LITERATURE_CONVENTION.md end to end; LITKB_P8_REFEREE §4 classified it. Kam:
         finish the pipeline, no new evaluations.
did:     ONE migration, 0020_first_use_friction.sql, applied to the worker test DBs and to litkb.
         Additive: three CHECKs widened (discrepancies.source +admission, file_versions.copy_kind
         +web snapshot, references.resolution +ambiguous), _check_registry and clear_extraction_rows
         replaced whole, _feeds_token_ok replaced in place, citation_edges created, four
         litkb_ingest-only writers and one trigger. Then: `litkb use add` + `use list` (step 4 of
         the hunt protocol had no CLI at all); `admit --web` for a source with no DOI, bound against
         the admitter's saved .txt of the page; `admit --doi` alone, declared registry_only on the
         identifier's evidence; the work title joined with its subtitle at admission, with
         bind_any() trying every published form so a first page printing the bare title still binds;
         a claim missing the subtitle kept as a discrepancy; bad downloads quarantined with a reason
         sidecar instead of discarded; the corpus census frozen to a committed sha256 list; and a
         loader for stage 6's parked JSONL.
decided: the feeds vocabulary is brought UP to the convention's seven forms rather than the
         convention cut down to the three that were enforced -- the referee called that "the right
         one" and the cheap one was editing the skill. §8.2 ("a use with no verifiable quote is
         refused at prepare") is FALSE as written and was NOT settled here: two coherent fixes,
         Kam's call, and the convention now says so in place of the false sentence.
measured: live litkb ingest 643 references / 969 citation mentions / 13 citation edges / 630
         citation candidates over 17 stage-6 runs; second run adds 0. The parked file's 1,386 rows
         are bounding boxes -- 1,182 are elements (box_index == 0) and 201 of those have no
         biblStruct target. Chrisman, the one refused paper, holds 24 elements of which 12 are
         targeted; the other 12 are already inside the 201, so the subtraction is 1,182 - 201 - 12
         = 969, not 1,182 - 201 - 24. litkb_test_w9, where every stem has
         a fixture file, loads 658 / 981 / 13 / 645. `citing_work_key` in the P6 JSONL is a FILE
         STEM, not a works.key: only 10 of 18 match a key, 17 of 18 match a held file by rel_path
         stem, so the loader resolves by stem first and refuses Chrisman_1982 by name (a key with no
         active file). `litkb inventory --new`: 28 outside the census, 0 renamed/changed/missing --
         but 13 of the 28 are ~1.6 KB failed downloads saved as .pdf, so 15 real new documents.
         U+FFFD/U+00AD/U+FFFE are now dropped before every title and token comparison, which rejoins
         hyphen-split words -- and does NOT recover Köpcke, whose "ö" the extractor lost entirely;
         that residual is pinned in a test rather than believed fixed.
gates:   check.py --fast under LITKB_TEST_DB=litkb_test_w6: 1 failed / 2904 passed / 22 skipped /
         2 xfailed; the one failure is the pre-existing crown_state_model pointer, not litkb's. 339
         litkb Postgres tests, 244 before. Mutation table parallel on --worker-dbs 1,6,9: 253/253
         fired, baselines passed, 72.8 min over 3 workers (the P6 ingest rows are inside that table;
         stage 6 registers its rows into P2's at import). Stage 0 keeps its own instrument: 23/23
         fired, X1 being the census kill. --sites: 78 call sites, 75 covered by a row, 3 equivalent;
         18 sinks, 2 redacted, 16 allowed; no PROBLEM.
gotcha:  0020 and work/20260915-access-layer's 0018 BOTH CREATE OR REPLACE _feeds_token_ok, written
         independently, with different framework-depth regexes. A CREATE OR REPLACE is decided by
         APPLY order, not by migration number, so litkb (which has 0020) would end up with 0018's
         body while a fresh database ends up with 0020's -- one migration set, two schemas. 0020 is
         applied and checksum-locked; 0018 is not yet. Kam decides which one goes.
gotcha2: the FIRST full table said "253/253 fired; baselines FAILED" after 133.6 min, and the broken
         baseline was the gate's own: freezing the census moved a tracked input (phase4/qc/*) out of
         make_worker_copy()'s domain, inventory.repo_root() resolved it under the COPY, and every
         corpus-backed test errored -- while the row that runs that set still printed FIRED, because
         a broken baseline never shows up in a row's verdict. Second instrument defect this session,
         same class as the missing cross-process lock. Fixed on COPY_FILES + a test. And
         test_new_files_needs_no_database_and_writes_nothing was green only under
         PYTHONPATH=pipeline pytest: its subprocess inherited no path, so check.py (which sets none)
         hit ModuleNotFoundError. litkb is not in the editable install; the subprocess now gets the
         path explicitly, like every other litkb test that spawns one.
files:   Scripts/pipeline/litkb/{use.py, commands.py, admit/*, acquire/*, db/migrate.py,
         db/migrations/0020_first_use_friction.sql, db/migrations/_reserved.txt,
         extract/{inventory.py,references_ingest.py}, migrate_legacy/run.py},
         Scripts/qc/{test_litkb_first_use.py, test_litkb_references_ingest.py, test_litkb_p1.py,
         test_litkb_p2.py, test_litkb_inventory.py, test_litkb_harness_parallel.py,
         test_status_discovery.py, instruments/*},
         Scripts/docs/LITERATURE_CONVENTION.md, phase4/qc/litkb_inventory_census.sha256,
         Reports/LITKB_P3_REPORT_2026-09-15.md ("First-use friction closed"), Scripts/CHATLOG.md.
next:    Kam's two open calls (§8.2's prepare rule; the _feeds_token_ok collision at the 0018 merge);
         the U+FFFD wildcard in tokens_contain if the quarantined Köpcke file is wanted; §8.7's
         open-access misses (a DOI->arXiv fallback recovers S2AND and Enamorado by the review's own
         list); the census re-pin debt on Massari_2023 p13.

## 2026-09-16  litkb-p8-merge
goal:    merge refereed P8 access layer (MCP server, skill, librarian, staged hook) into
         work/20260913-literature-kb, apply its migrations, settle the feeds-validator collision,
         prove merged tree. Wrote neither side.
did:     work/20260915-access-layer fd59bc3 merged --no-ff as c932bea. Three textual conflicts, all
         union, none a disagreement: commands.py::main dispatch (HEAD's `use`+`inventory`, P8's
         `promote`); test_litkb_p1.py::_EXPECTED_EXECUTE twice (HEAD's `_feeds_token_ok` from 0020,
         P8's check_ws_token/norm_search_text/any_term_query/promotion_chains from 0018; and ingest's
         four stage-6 writers beside P8's norm_search_text). .gitignore, netutil.py and the mutation
         harness auto-merged on disjoint regions.
         Migrations: 0018 + 0019 applied to litkb, litkb_test, litkb_test_w1/w6/w9. litkb_test_w2
         left at 19 (P8's own worker). Then 0021_feeds_validator_final.sql, applied everywhere.
         litkb = 21 migrations.
         THE COLLISION, measured not reasoned. 0018 and 0020 each CREATE OR REPLACE
         litkb._feeds_token_ok with a different seven-form body. CREATE OR REPLACE is decided by
         APPLY order, not by number, so one migration set gave two schemas. On litkb_test the moment
         0018 landed on top of 0020: `framework §13.1.1` -> false (0018's depth rule), `report
         notmd#§5` -> TRUE (0018's `[^ ]+`). A from-scratch build answers the other way on both.
         test_litkb_p8.py asserts the first refused; test_litkb_first_use.py asserts the second
         refused. Neither suite wrong.
         0021 states the definition ONCE and, being highest-numbered, applies last everywhere.
         framework §N keeps 0018's at-most-one-sub-level (LITERATURE_CONVENTION.md says so in as
         many words); `report <FILE>#§<loc>` keeps 0020's .md requirement (a token naming no
         document is the hole the 2026-09-13 vocabulary closed). Proof: md5(prosrc) is
         982600bf2bd477aab6565c4b3ad0879a on litkb (0020 first) AND on litkb_test (0001..0021 from
         scratch) -- IDENTICAL.
         Proofs: --sites PASS (89 sites, 86 covered, 3 equivalent; 18 sinks, 2 redacted, 16 allowed
         -- merge dropped none of P8's sinks). P8 + first-use suites 96 passed / 3 skipped; with
         LITKB_LIVE=1 the MCP mini-hunt included, 60 passed / 0 skipped. Feeds vocabulary: same 12
         accepted, 14 refused, on litkb_test and litkb. P3 gate read-only on litkb 1,086 cells ->
         713/243/120/10/UNEXPLAINED 0, PASS, empty git diff on the CSV. 293 table 20/23/250,
         requests_total 0. check.py --fast under w6: only crown_state_model (the two inventory
         census pins now pass).
         Full parallel harness --workers 3 --worker-dbs 1,6,9: 271/272 fired, 71.9 min -- and
         baselines FAILED, which is the real finding.
decided: 0021 rather than editing 0018 (both already applied and checksum-locked, so neither could
         be the one that changes -- the second of the two options _reserved.txt offered).
         Design §9 AMENDED per P8 referee §5: promote prepare exposed as litkb_propose_promotion,
         credential clause kept exactly, reason commit/approve stay absent written down. Referee
         condition (i) recorded as NO LONGER TRUE: his own F-5 fix made prepare write the report, so
         an agent-supplied report_path is a file write with no `..` check. READ FROM SOURCE, not
         exercised. Scoping it is a new guard on a refereed branch -> Kam's, with the decisions.yaml
         line.
         docs/LITKB_AGENT_BASE_BRIEF.md tracked, so a change to the standing agent rules is a diff.
killed:  test_an_undeclared_gap_in_the_migration_numbering_is_still_refused as written -- it
         borrowed its gap from 0018/0019 being absent from disk and asserted nothing once they
         merged. Rewritten to dig its own hole, in the MIDDLE (a missing LAST migration is a shorter
         list, not a gap).
         The first harness run's nineteen X verdicts. P8 put skill/librarian/hook at the REPOSITORY
         root under .claude/ and test_litkb_p8.py reads all three off SCRIPTS.parent; none is under
         COPY_DIRS, so every worker copy was missing them and the P8 baseline ran 14 failed / 43
         passed there against 60/60 in the real tree. run_one calls a row FIRED on ANY failure,
         comparing nothing, so all 19 X rows reported FIRED whatever the mutation did. Only the
         separate baseline check caught it (rc 1, all three workers). Three files added to
         COPY_FILES (not settings.json: git-ignored, per-session, and the test skips when absent).
         Re-run after the fix: baseline 57 passed / 3 deselected per copy, 20/20 fired in 3.5 min.
         A18 DID NOT FIRE -- replaced-function class a FOURTH time, created by this merge: 0019
         CREATE OR REPLACEs _ws_chains and carries 0013's "a fact chain enters main only through
         admission approval" guard with it, so 0013's copy is dead text. Repointed to 0019 (MIG19,
         beside MIG16/MIG20/MIG21), fires on
         test_an_unapproved_manual_admission_is_held_at_promote_prepare.
files:   Scripts/pipeline/litkb/db/migrations/{0018_access_layer.sql, 0019_prepare_requires_evidence.sql,
         0021_feeds_validator_final.sql, _reserved.txt}, Scripts/pipeline/litkb/{commands.py,
         promote.py, netutil.py, mcp/}, Scripts/qc/{test_litkb_p1.py, test_litkb_p8.py,
         instruments/litkb_p2_mutations.py}, .claude/{skills/literature/SKILL.md, agents/librarian.md,
         hooks/litkb_guard.py}, Scripts/LITERATURE_KB_DESIGN_2026-09-13.md (§9),
         Scripts/docs/{LITERATURE_CONVENTION.md, LITKB_AGENT_BASE_BRIEF.md},
         Reports/LITKB_P4_MERGE_2026-09-15.md ("P8 merged"), Scripts/CHATLOG.md.
         Commits c932bea, 6afc566, 0a27c60, 549c5ee, 95c3249, 13f5c45; pushed to github.
next:    Kam: bound report_path (or accept it) with the §9 amendment; the decisions.yaml line §9's
         condition (iii) asks for. Harness owner: run_one should compare a row against its OWN
         baseline rather than count failures absolutely -- the P8 referee flagged the neighbouring
         blind spot ("counts failures, not errors") and called it not his to change; still nobody's.
         litkb_test_w2 stays at 19 migrations. The P3 report's "access-layer had not patched the
         validator" was true at b787fa0 and false after 65dca14; left as history, corrected in the
         merge report.

## 2026-09-16  litkb: bulk pass, operational test, fix sets; pick-up point written (usage fail-safe)
goal:    Kam: "keep working until you reach the goal of a working lit review system"; usage at 12% -> fail-safe.
did:     P5 bulk extraction (225 files, 102k blocks, L4 LaTeX attached); operational test through the skill
         (gold ranks 1/2/2; 3 fresh framework questions answered with DB-verified quotes; 12 chains prepared);
         referee: OPERATIONAL for citing extracted passages; fix set (litkb_work 4-state, my_uses, gates, dy
         clamp, OCR per-process cap, 4 more works bound+extracted); final referee: OPERATIONAL WITH CAVEATS
         (duplicate blocks from two extractors on one region, cross-page page_no, furniture in search,
         LaTeX 11/20 correct); caveat fix (canonical blocks, per-page split, furniture filter, latex_status,
         scan OCR at binding) in flight at time of writing. Pick-up point: WORKPLAN.md litkb table.
decided: lexical search is the operational leg (P7 vectors FAILED pre-committed floors on .txt text);
         Opus builds/referees, Sonnet searches; one full harness after merges; no new evaluations.
killed:  ref-matcher (0/100 as shipped; scoring cannot express the year rule); Splink for duplicates.
files:   Reports/LITKB_P5_BULK_2026-09-16.md, Reports/LITKB_P5_FINAL_REFEREE_2026-09-16.md,
         Reports/LITKB_OPERATIONAL_*_2026-09-16.md (access branch), Scripts/docs/LITKB_AGENT_BASE_BRIEF.md.
next:    verify the caveat fix cheaply (psql), declare, stop the loop; Kam: balance read, promotions, book, MCP registration, merge to main.

## 2026-09-16  litkb: hunt one-shot proven; end-goal loop designed; stopped for budget
did:     `litkb hunt` built (bea983f..75bb3fa): FPGA hardware doc (no DOI) fetched, bound, extracted, ingested unattended (62 pp, 18,064 blocks, 371 s; repeat call 0.55 s). Kam's question answered from ingested text, no vision tokens.
decided: no more builds tonight (12% weekly usage); the Sonnet-review -> drop-off -> hunt -> circle-back -> vet -> brief loop is the next phase (WORKPLAN litkb table).
killed:  admit-then-attach for web sources (a proposal has no current version) -> file arrives with the admission.
next:    ligature normaliser; approve the FPGA proposal from a second session; Kam's decision stack; merge to main.

## 2026-09-16  litkb: two Sonnet improvement reviews through the closed loop (24 drop-offs, 4 full texts landed)
did:     reviews A (extraction/retrieval) and B (identity/linkage/agentic) committed with drop-offs and hunt outcomes; synthesis to Kam; priorities recorded in WORKPLAN's litkb table.
decided: (Kam pending) hunt spend rule for review workstreams. Nougat rejected as decoder #2 (weights CC-BY-NC).
next:    Kam's decision stack; builds when budget allows, in the recorded order.
