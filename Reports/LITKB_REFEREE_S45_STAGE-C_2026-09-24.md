# litkb S4.5 — referee report, rung class STAGE-C (plan item 5: landing page to bytes, the rule table, the Range probe, the acceptance test's stub/volume rules)

Referee: `referee-stage-c` (Opus). I did not build, propose, integrate or audit this class. Checkout: detached
`D:\edmonds-pipeline\wt-s45-ref-stage-c` at main `2ef3d68`; worker DB `litkb_test_w7` (pg_locks checked free first);
live `litkb` read only as `litkb_reader`; the manifest, run CSV, recording report, cassette index and body store
read-only; NO network. Inputs: `hardening-1-manifest.json` (frozen_at 2026-09-24T08:22:40.799Z, head cd2f23b,
sha256 5873d3fc…), `LITKB_LADDER1_2026-09-24_run.csv` (sha256 8ddad087…, 195 rows), the ladder-1 cassette index
(3,632 request entries, every body present in the store).

## Verdict: REJECT — narrow: ONE sub-rule of the rung is wrong on real rows; everything else scores CORRECT

- **WRONG on real rows (the rung):** C6-RG's marker-free rule in `litkb.acquire.landing.classify` ("200 + text/html
  + no citation metadata at all = an interstitial") typed 5 real landing attempts `blocked/challenge_or_bot_check`
  when the recorded page had no bot check in it: **L007** LPVSubgroup_2025 (a NASA LPV document-index page that
  lists this work's own PDF), **L061** Tkaczyk_2024, **L064** Tkaczyk_2025, **L166** Tkaczyk_2018 (the Crossref
  blog posts themselves: 17–18 K visible characters, `dc:*`/`og:*` metadata, the HTML-is-the-work rows of D12) and
  **L167** DelgadoQuiros_2025 (osf.io's Angular app shell, nginx, no WAF). For L061 L064 L166 L167 that label is the
  ONLY blocked attempt of the work, so the run CSV's hunt outcome `blocked/challenge` for those four rows rests on it.
  C6-RG decided 5 attempts in this run and was wrong on 5; every real interstitial of the run (96 attempts) was caught
  by a vendor signature, so on this corpus the rule added 0 true positives. A fix changes rung code after the run →
  re-freeze and re-run those five rows (never these rows graded under new code).
- **A GATED counter reads RED on the run (for the orchestrator to rule):** `landing_pages_booked_bad_file=3`, read by
  the gate itself as `litkb_reader` and reproduced by my own reader: **L062** VelasquezCamacho_2025, **L139**
  Miller_2013, **L146** Ma_2021 — each a `doaj` (Stage B) answer, the article's HTML page carrying
  `citation_pdf_url`, booked `bad-file/html_response`, with no Stage C attempt after it. Stage C was not asked because
  `open_access` bound each work in the same concurrent Stage B wave (a hunt stops at its first landing) — no file was
  lost. This is the gate's definition meeting the ladder's concurrency, not a Stage C mislabel: either the gate
  excludes works bound before Stage C could run, or a Stage B rung books an HTML landing page the way `publisher-url`
  already does (`blocked/html_or_reader`, SCHEMAS). A plan-level ruling, not mine.
- **A yield defect (not a label error):** the MDPI CDN template converted **12/12** real rows whose volume has two
  digits and **0/5** whose volume has one digit (**L071** Morgan_2024 geomatics vol 4 — a row the run plan named as an
  expected conversion — **L074** Coulter_2008 sensors 8, **L147** Gong_2017 ijgi 6, **L155** Martinis_2010 and
  **L156** Motohka_2010 remotesensing 2): each CDN URL answered a real 404. The template pads the article number
  (`{art:0>5}`) but not the volume (`geomatics-4-00022`). The cause is INFERRED from the 12-vs-5 split; confirming the
  padded form needs one live GET, outside my grant. The builder's own unit test pins `sensors-8-02161` — the exact
  URL the real Coulter row saw 404.
- Everything else: 128/133 landing attempts CORRECT against my oracle; 76/76 PDFs bound in the run CORRECT by my
  own reader (0 stubs, 0 volumes, title match 1.00 on every one); D24 holds on 68/68 MDPI Akamai 403s across six
  routes; 10/10 re-fires FIRED; my own mutation FIRED.

## The oracle (mine; X9 — imports nothing from litkb)

Scripts in `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-stage-c\`: `cas.py` (my own cassette reader:
index format → body inline/base64 or store `<sha[:2]>/<sha>.bin`), `oracle.py` (types one recorded answer),
`score_landing.py`, `score_files.py`, `score_other.py`.
- **Answer typing** (`oracle.classify`): `pdf` = 2xx + `%PDF-` after lstrip; redirects into perfdrive/captcha/
  `validate.` hosts = challenge; vendor interstitials by TITLE / HEADER / inline options written from the WAF
  products (Cloudflare `cf-mitigated: challenge`, "Just a moment" / "Attention Required! | Cloudflare",
  `cf_chl_opt`; Akamai "Access Denied" title + edgesuite/"Reference #"; F5 title "Client Challenge"; AWS WAF 202 +
  its challenge script; Radware perfdrive; DataDome; PerimeterX; Imperva; browser-check text; ScienceDirect's
  Cloudflare-fronted CPE00001 page); 429 with rate-limit text = transient; 404/410 not_found; 401, login URLs, a 403
  with no interstitial = identity; a PDF request answered by HTML = `html_for_pdf` (paywall text → identity); a page
  = `landing` if it carries citation metadata, else `plain_html`.
- **Revised on the real rows, and said so:** three revisions, each making my oracle agree MORE with the rung, never
  less: (1) Cloudflare's injected `/cdn-cgi/challenge-platform/` script include is NOT a marker (MEASURED on
  Cambridge's 998 KB abstract page, OUP's ordinary 404s, bioRxiv's 429); (2) bioRxiv's 429 "Attention Required |
  Cloudflare" page states "a high number of requests from this session" = a rate limit → transient (the rung's
  `api-error`, retriable, is CORRECT); (3) the DOI page is matched by URL AND recorded status (IEEE serves one URL
  twice: the 202 WAF page, later the 200 document page).
- **Binding** (`score_files.py`): each bound file opened read-only; page count by `pikepdf` AND `pypdfium2`; text of
  every page by pypdfium2; stub = < 3,000 characters AND no reference-section heading; volume = ≥ 60 pages vs a
  Crossref `a-b` range < 60; identity = share of the Crossref title's words (> 3 letters) on pages 1–2, where the
  Crossref (or DataCite) record is the one THE RUN RECORDED (`api.crossref.org/works/…` in the cassette; 71 of 76).

## Scored rows — the rows the plan names for STAGE-C (run-plan §5)

| row | work | plan / recorded expectation | what the rung did (ledger; run CSV) | my oracle | verdict |
|---|---|---|---|---|---|
| L072 | Wang_2025 (plants 14) | + MDPI CDN conversion | `landing ok` via `mdpi.cdn` (206 %PDF); bound fresh | 21 pp (pikepdf=pdfium), title 1.00 vs Crossref | CORRECT |
| L073 | Chen_2023 (rs 15) | + MDPI CDN conversion | `landing ok` via `mdpi.cdn`; bound fresh | 24 pp, title 1.00 | CORRECT |
| L071 | Morgan_2024 (geomatics 4) | + MDPI CDN conversion | CDN 404, `/pdf` Akamai 403 → `blocked/challenge_or_bot_check`; hunt blocked/403 | 404 is real; www.mdpi.com Akamai page | label CORRECT; conversion MISSED — WRONG (yield; unpadded one-digit volume, cause inferred) |
| L074 | Coulter_2008 (sensors 8, measure) | + measure the CDN rung | CDN 404 ×2, Akamai 403 → blocked/challenge | same pattern | label CORRECT; yield miss (same cause) |
| L023 L024 L026 | McRoberts_2018, Pengra_2020, Nowak_2018 (measure) | REPORTED (survey: 0 expected; challenge → S4.6) | pdfft + `/am/` rewrite → 403 → blocked/challenge (`elsevier:cpe00001`) | ScienceDirect 403 served by Cloudflare (`server: cloudflare`, `cf-ray`, the CLOUDFLARE_ERROR_1000S box, CPE00001), no login, no metadata: a bot block | CORRECT |
| L025 | Stehman_2022 (hunt) | REPORTED; PREDICTION challenge | same; hunt blocked/403 | same | CORRECT (prediction held) |
| L006 | AllenMatthew_2026 (E07, Apollo) | convert / challenge / held | `not-in-archive/no_pdf_link`; hunt blocked/challenge (Wayback `not_found`, D43) | page carries citation metadata, NO `citation_pdf_url`, no `rel=alternate` PDF; it DOES carry a FAIR-Signposting `<link rel="item" type="application/pdf">` to the bitstream | CORRECT per the plan's C2 list; NOTE a missed lead no survey read |
| L003 | VanDenHout_2016 (E20) | − `stub_not_article`, never bound | `bad-file/stub_not_article` on the T&F S3 `preview.pdf`; not bound | 47 pp; last page prints "234 BIBLIOGRAPHY" → an excerpt of a ≥ 234-page book; bytes sha256 9b23b0e2… = the stub_e20 fixture | CORRECT (my content rule would NOT flag it: 85,074 chars + a bibliography; only the `preview_url` signal did) |
| L029 | Kingman_1962 (Springer) | − never bound | blocked/challenge (F5); hunt held/duplicate-held (Wayback) | title "Client Challenge" at 200 | CORRECT, not bound |
| L040 | Strong_2003 (IOP) | − never bound | blocked/challenge (302 into validate.perfdrive.com, never followed) | Radware redirect | CORRECT, not bound |
| L037 | Enamorado_2019 (Cambridge) | − identity_required or html_or_reader | blocked/html_or_reader | the PDF endpoint redirects to the abstract page (citation metadata + "access through your institution") | CORRECT (plan accepts either; my oracle prefers identity_required) |
| L048 L049 | Kopcke_2010, Konda_2016 (ACM) | − never bound | blocked/challenge (dl.acm.org 403) | Cloudflare `cf-mitigated: challenge` 403 | CORRECT, not bound |
| — | the 5 CONSTRUCTED negatives (`qc/testdata/litkb_acq_negatives/`, each named CONSTRUCTED) | as labelled | used by the fires below | BOM prefix (EF BB BF %PDF-); 60-page volume (pikepdf=pdfium=60); 1-page TDM stub (1,496 chars, no refs) + CONSTRUCTED X-ELS-Status header; 6-page scan (203 chars) | CORRECT (they are what their names say) |

## Scored rows — the whole Stage C population of the run

All 133 `landing` attempts of the run (128 works): `blocked/challenge_or_bot_check` 101 · `ok` 14 · `measured` 4 ·
`not-in-archive/no_pdf_link` 4 · `skipped/dead_in_run` 4 · `api-error` 2 · `known-bad` 2 · `bad-file/stub_not_article`
1 · `blocked/html_or_reader` 1. My oracle: **CORRECT 128, WRONG 5 (all C6-RG), UNDETERMINED 0**.

| terminal host | attempts → final label | my oracle's evidence | verdict |
|---|---|---|---|
| www.sciencedirect.com | 36 blocked/challenge | Cloudflare-fronted CPE00001 403 (114 identical 832,805 B answers) | CORRECT |
| link.springer.com / www.nature.com / bmcmedresmethodol.biomedcentral.com | 13 / 3 / 1 blocked/challenge | F5 "Client Challenge" at 200 | CORRECT |
| www.tandfonline.com, dl.acm.org, academic.oup.com, ingentaconnect, science.org, siam, ssrn, ascelibrary, worldscientific, wiley | 29 blocked/challenge | Cloudflare `cf-mitigated: challenge` | CORRECT |
| ieeexplore.ieee.org / journals.ametsoc.org | 7 / 1 blocked/challenge | AWS WAF 202 + challenge script | CORRECT |
| www.mdpi.com | 5 blocked/challenge | Akamai "Access Denied" + edgesuite | CORRECT |
| iopscience.iop.org | 1 blocked/challenge | redirect into validate.perfdrive.com | CORRECT |
| mdpi-res.com / commons.clarku.edu / besjournals.onlinelibrary.wiley.com | 12 / 1 / 1 ok | recorded %PDF; binds scored below | CORRECT |
| arxiv.org | 4 measured, 1 known-bad | recorded %PDF via the abs page's citation_pdf_url | CORRECT |
| isprs-archives.copernicus.org | 1 known-bad | recorded %PDF (sha matched a rejected copy) | CORRECT |
| S3 (T&F preview) | 1 bad-file/stub_not_article | E20, above | CORRECT |
| www.cambridge.org | 1 blocked/html_or_reader | the PDF endpoint answers the paywalled abstract page | CORRECT (either label accepted) |
| www.repository.cam.ac.uk, www.dlib.org ×2, www.ovid.com | 4 not-in-archive/no_pdf_link | no citation_pdf_url / rel=alternate PDF on any recorded page | CORRECT |
| www.biorxiv.org | 2 api-error (retriable) | Cloudflare 429 whose text is a request-rate notice | CORRECT |
| — | 4 skipped/dead_in_run | a reason, no request recorded in the window | CORRECT |
| **www.crossref.org ×3, osf.io, lpvs.gsfc.nasa.gov** | **5 blocked/challenge (C6-RG)** | **a real blog post (×3), an app shell, a document index — no interstitial marker of any vendor** | **WRONG** |

Per reported URL (the DOI page and every candidate each attempt names, 298): the rung's own per-URL verdict equals
my label on 257. The 41 others: the 5 C6-RG pages; 28 IEEE candidates whose chain passes
`/Xplore/login.jsp?…authDecision=-203` (an entitlement login the rule table's `login_wall_url_markers` do not list →
rung `html_or_reader`, my oracle `identity`; the plan's paywalled negative accepts either); 2 Cambridge candidates
(paywall text on a real page → `html_or_reader`; accepted either way); Wiley's OIDC login loop
(`/action/oidcStart` → `error=login_required`) typed `unexpected` on 3 candidates (a second visit to the same
pdfdirect URL then served Weinstein_2020's open PDF, which bound); the 2 D-Lib pages (`landing` vs my `plain_html`,
both not a challenge); 1 Chernozhukov candidate. None of these moves a final label the plan forbids. Also noted:
Rodman_2021 (Elsevier) — an OpenAIRE lead to ANOTHER work's MDPI URL made the MDPI rule build two candidates for that
other article (both refused by the host; nothing bound; the binder would refuse the title anyway).

### Every PDF the run bound (76 file versions since frozen_at; 14 via `landing`)
76/76 CORRECT by my reader: pikepdf page count == pdfium page count on all 76; 0 below 3,000 characters without a
reference section; 0 volumes; the recorded Crossref title's words all on pages 1–2 (share 1.00) for every file.
Page-count differences from the Crossref range occur only on preprint/accepted-manuscript routes (e.g. Pontius_2011,
`landing` from commons.clarku.edu: 53 pp vs a 23-page range — an author manuscript, title 1.00). Refused PDF payloads
in the quarantine since frozen_at: 5 (E20's preview above; 4 `binding-failed` copies — LPVSubgroup_2025 188 pp is D23's
named corporate-author exception). The gates read on live as `litkb_reader`: `stubs_bound=0`,
`volumes_bound_as_article=0` — my reader agrees (0, 0).

### D24 on the run
Every run attempt whose terminal host is an MDPI host and whose terminal status is 403: **68 of 68** typed
`blocked/challenge_or_bot_check` (crossref-link 17, doaj 16, open_access 15, openalex 14, landing 5, openaire 1); my
oracle finds Akamai's "Access Denied" + edgesuite page in every recorded body; 0 booked `bad-file/html_response`.

### The gated/reported counters of this class, read on the run (reader) vs my oracle
| counter | gate on the run | my oracle | note |
|---|---|---|---|
| `landing_pages_booked_bad_file` (gated =0) | **3** (L062 L139 L146, doaj) | 3, the same rows (their recorded pages carry `citation_pdf_url`; no landing attempt after) | RED; see the verdict |
| `landing_pages_after_stage_c` (reported) | 2 (Wayback captures, Herzog_2007, Burnicki_2012) | 2 | Stage C had already asked those works' live pointers |
| `stubs_bound` / `volumes_bound_as_article` (gated) | 0 / 0 | 0 / 0 | |
| `bronze_landing_unconverted` (reported) | 4 | 4 (L023–L026 all end at the Cloudflare block) | the survey's ESTIMATED zero held |
| `manual_step_rows` (reported) | 54 | not scored | |

## Re-fires (verbatim; `PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w7 py -3.12 qc/instruments/litkb_acceptance.py hardening --fire <name> --db litkb_test_w7`)

```
fire=stage_c_disabled (litkb_hardening_c2b) arm=control landing_pages_booked_bad_file=0 (bound =0)
fire=stage_c_disabled (litkb_hardening_c2b) arm=known_bad landing_pages_booked_bad_file=1 (bound =0)
fire=stage_c_disabled FIRED
EXIT=0
fire=mdpi_cdn_rule_disabled (litkb_hardening_c2b) arm=control mdpi_landings_unconverted=0 (bound =0)
fire=mdpi_cdn_rule_disabled (litkb_hardening_c2b) arm=known_bad mdpi_landings_unconverted=1 (bound =0)
fire=mdpi_cdn_rule_disabled FIRED
EXIT=0
fire=paywalled_probe_disabled (litkb_hardening_c2b) arm=control landing_html_booked_bad_file=0 (bound =0)
fire=paywalled_probe_disabled (litkb_hardening_c2b) arm=known_bad landing_html_booked_bad_file=1 (bound =0)
fire=paywalled_probe_disabled FIRED
EXIT=0
fire=e13_challenge_rule_disabled (litkb_hardening_c2b) arm=control landing_challenges_mistyped=0 (bound =0)
fire=e13_challenge_rule_disabled (litkb_hardening_c2b) arm=known_bad landing_challenges_mistyped=1 (bound =0)
fire=e13_challenge_rule_disabled FIRED
EXIT=0
fire=stub_constructed (litkb_hardening_c1b) arm=control stubs_bound=0 (bound =0)
fire=stub_constructed (litkb_hardening_c1b) arm=known_bad stubs_bound=1 (bound =0)
fire=stub_constructed FIRED
EXIT=0
fire=stub_e20 (litkb_hardening_c1b) arm=control stubs_bound=0 (bound =0)
fire=stub_e20 (litkb_hardening_c1b) arm=known_bad stubs_bound=1 (bound =0)
fire=stub_e20 FIRED
EXIT=0
fire=stub_ladder (litkb_hardening_c1b) arm=control stubs_bound=0 (bound =0)
fire=stub_ladder (litkb_hardening_c1b) arm=known_bad stubs_bound=1 (bound =0)
fire=stub_ladder FIRED
EXIT=0
fire=stub_ladder_header_only (litkb_hardening_c1b) arm=control stubs_bound=0 (bound =0)
fire=stub_ladder_header_only (litkb_hardening_c1b) arm=known_bad stubs_bound=1 (bound =0)
fire=stub_ladder_header_only FIRED
EXIT=0
fire=volume (litkb_hardening_c1b) arm=control volumes_bound_as_article=0 (bound =0)
fire=volume (litkb_hardening_c1b) arm=known_bad volumes_bound_as_article=1 (bound =0)
fire=volume FIRED
EXIT=0
fire=bom_repair (litkb_hardening_c1b) arm=control bom_valid_pdfs_refused=0 (bound =0)
fire=bom_repair (litkb_hardening_c1b) arm=known_bad bom_valid_pdfs_refused=1 (bound =0)
fire=bom_repair FIRED
EXIT=0
```
**10/10 FIRED.** The stub_e20 fixture (`qc/fixtures/litkb_e20_preview.pdf`, sha256 9b23b0e2…) is byte-identical to the
payload the LIVE run refused on L003 (`_quarantine/VanDenHout_2016_…__bad-file__9b23b0e2303c.pdf`), so that fire's
known-bad arm replays exactly the real row's bytes.

fired: landing_pages_booked_bad_file=1 on the REAL recorded Cambridge page carrying citation_pdf_url with Stage C disabled (stage_c_disabled, litkb_test_w7)
fired: mdpi_landings_unconverted=1 on the recorded MDPI row Chen_2023 (real doi.org 302 and Akamai 403 hops) with the CDN candidate removed (mdpi_cdn_rule_disabled, litkb_test_w7)
fired: landing_html_booked_bad_file=1 on the recorded paywalled Cambridge row with the Range-probe typing disabled (paywalled_probe_disabled, litkb_test_w7)
fired: landing_challenges_mistyped=1 on E13's REAL recorded Cloudflare 403 page with the landing rung's challenge rule disabled (e13_challenge_rule_disabled, litkb_test_w7)
fired: stubs_bound=1 on E20's real T&F preview PDF (sha256 9b23b0e2, byte-identical to the run's refused L003 payload) with the stub detector disabled (stub_e20, litkb_test_w7)
fired: stubs_bound=1 on the CONSTRUCTED first-page TDM stub with the stub detector disabled (stub_constructed, litkb_test_w7)
fired: stubs_bound=1 on the CONSTRUCTED TDM stub served through the ladder with the landing's acceptance test removed (stub_ladder, litkb_test_w7)
fired: stubs_bound=1 on a whole article served with only the CONSTRUCTED X-ELS-Status header through the ladder with the acceptance test removed (stub_ladder_header_only, litkb_test_w7)
fired: volumes_bound_as_article=1 on the CONSTRUCTED 60-page proceedings volume offered for a 12-page record with the volume detector disabled (volume, litkb_test_w7)
fired: bom_valid_pdfs_refused=1 on the CONSTRUCTED BOM-prefixed valid article with the header repair removed (bom_repair, litkb_test_w7)
fired: mdpi_landings_unconverted=1 on the recorded MDPI row with the CDN template's article zero-padding removed from landing_rules.json (referee-stage-c's own mutation, litkb_test_w7)

## My own mutation (not in `qc/instruments/litkb_p2_mutations.py`: no row there mutates the rule TABLE at all)

`pipeline/litkb/acquire/landing_rules.json`, MDPI rule, candidate `cdn`, exactly one occurrence:
`"template": "…/{journal}-{vol}-{art:0>5}/article_deploy/{journal}-{vol}-{art:0>5}.pdf"` →
`"…/{journal}-{vol}-{art}/article_deploy/{journal}-{vol}-{art}.pdf"` (the one data line behind all 12 real MDPI
conversions). One pytest on w7: `PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w7 py -3.12 -m pytest
qc/test_litkb_landing.py -q -p no:cacheprovider -k mdpi`.
- baseline (unmutated): `4 passed, 105 deselected`, EXIT=0.
- mutated (sha256 adb0a3ae…): **`4 failed, 105 deselected`, EXIT=1** — every red a failed assertion on a WORSE answer:
  `test_each_recorded_page_reproduces_its_rules_expectations[mdpi]` (candidates changed);
  `test_the_mdpi_cdn_slug_comes_from_the_venue_and_the_doi_code_and_the_article_is_padded`;
  `test_the_mdpi_cdn_rule_lands_the_recorded_row` (`('landing', 'blocked') == ('landing', 'ok')` — the recorded row no
  longer lands); `test_each_c2b_fire_holds_its_bound_on_control_and_breaks_it_with_its_guard_off[mdpi_cdn_rule_disabled]`
  (control arm `assert 1 == 0`). No error.
- restored: sha256 b053387767f1321a7dfe6e98e3ed83a3757be4dd99c016f08d4550dd908ca3de == the original; `git status --short`
  empty. **FIRED.**

## The survey's design claims the real rows decide

| claim (source) | real rows | ruling |
|---|---|---|
| C6-RG: 200 + text/html + no citation metadata = an interstitial (PDF-sources survey C6-RG, VERIFIED-in-source there) | decided 5 attempts; 0 of the 5 pages is an interstitial; 0 real interstitial was caught by it alone | **CONTRADICTED** on this corpus |
| MDPI's CDN answers `application/pdf` where www.mdpi.com answers 403 (survey A6, one live probe, remotesensing vol 14) | 12/12 two-digit volumes converted; 0/5 one-digit volumes (all 404) | CONFIRMED for two-digit volumes; the one-digit form UNVALIDATED (template likely wrong; one GET decides) |
| Elsevier's `pdfft` sits behind a challenge; bronze rows ESTIMATED zero (survey §2.1 / plan test set) | 4/4 bronze rows and all 36 ScienceDirect attempts end at the Cloudflare-fronted CPE00001 403 | CONFIRMED (the converter is S4.6's browser rung) |
| Closed publishers answer a bot check before any paywall; `identity_required` rare (builder-C2b §6.1 PREDICTION) | 96 real vendor interstitials; 0 final `identity_required` of 133 | CONFIRMED |
| E20's own `citation_pdf_url` serves a preview that must type `stub_not_article` (plan test set) | typed and refused; not bound | CONFIRMED — but the preview is 47 pages / 85 K characters with a bibliography: the plan's content stub rules (< 3,000 chars; ≥ 60 pages) would not catch it; only the URL `preview` signal did |
| The paywalled remainder ends identity_required / html_or_reader, never bound (plan test set) | Kingman, Strong, Enamorado, Kopcke, Konda: none bound; 4 × challenge, 1 × html_or_reader | CONFIRMED for "never bound"; the typing is challenge far more than the plan's two named sub-statuses (the vocabulary allows it) |
| "Frontiers JS/bot-walled in practice" (survey §2.1) | no Frontiers work reached Stage C (Ma_2021 bound by open_access) | UNDETERMINED |

**Resting on a survey no different-model-family read covered:** Codex's design review (`codex-design-review.md`,
item 5) read the Stage C design cards (publisher rules, C2-RG, C9/C10, decompression order, the preview detectors,
the rule-table exclusions) but not C6-RG's marker-free rule, not A6's CDN template form, not the refusal precedence
(challenge > identity > html_or_reader > not_found — the builder's own choice, no survey), not the login-wall URL
marker list (IEEE's `login.jsp`, Wiley's OIDC loop are absent from it), and nobody read FAIR Signposting
(`rel="item"`, on Apollo's page). Codex's own note says it read DESIGNS; the BUILT code was still owed to it.

## Notes for the orchestrator (not defects of this rung's contract)
- The recorded cassette bodies (ScienceDirect's 403 page, bioRxiv's 429 page) print the client's public address
  (D31's leak class); the index is untracked by Q1, so nothing leaked into git — do not track it.
- IEEE `…/Xplore/login.jsp?…authDecision=-203` and Wiley `/action/oidcStart … error=login_required` are login walls
  the table does not name; adding them changes per-candidate labels only (plan-accepted either way).
- Apollo (E07) offers its bitstream by Signposting `rel="item"` — a free lead for a later session.

Full working notes, commands and every intermediate output: `D:\tools\claude-config\jobs\litkb-s4-5\referee-stage-c.md`.
