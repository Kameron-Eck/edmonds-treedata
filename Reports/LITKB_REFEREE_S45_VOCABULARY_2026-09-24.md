# litkb S4.5 referee — rung class `vocabulary` (plan item 2)

Referee: `referee-vocabulary` (Opus 5.5, fresh agent; built, proposed, integrated and audited nothing in S4.5).
Checkout: detached `D:\edmonds-pipeline\wt-s45-ref-vocabulary` at main `2ef3d68`. Worker DB: `litkb_test_w4` (no
advisory lock and no session on it before use; the only advisory lock on the cluster was `litkb_test_w9`'s). Live
`litkb` read only as `litkb_reader`; the corpus, the manifest, the run CSV, the recording report, the cassette index
and the body store read only; no network. Written 2026-09-24 after the live run ended (manifest `hardening-1`,
frozen 2026-09-24T08:22:40.799Z at head `cd2f23b`; passes 1–3; last attempt 18:18:51Z).
Full working notes: `D:\tools\claude-config\jobs\litkb-s4-5\referee-vocabulary.md`.

## Verdict: REJECT — scoped to the challenge typing (item 2's "a challenge at ANY status" and D24's one detector)

On the real rows, item 2's machinery does what the plan says: every row that must say WHY does (1,960 of 1,960),
every request row carries its terminal facts, `retriable`, `kind`, served sha and a PolicyDecision; every skip has a
reason that the ledger itself confirms; the budget stops are real and none is silent; D15, D29, the 59 backfilled
rows, the 277 sidecars the run wrote and D43 all check out.

But the WORD is wrong on **35 of 625** typed / `api-error` rows (5.6%), and **2 more are UNDETERMINED**. 26 of the
35 are the plan's own named rule failing on real pages:

- **17 rows: a bot check the ladder did not call a challenge** (booked `bad-file/html_response` or `api-error`):
  HAL's Anubis page "Making sure you're not a bot!" at HTTP 200 (8 rows, 5 works), AWS WAF's empty 202 with
  `x-amzn-waf-action: challenge` (6 rows, 4 works), an Imperva Incapsula block page at 200 (2 rows), and a
  reCAPTCHA page at 404 (1 row). Plan item 2: "a challenge page is a challenge at ANY status".
- **4 rows: ScienceDirect's Cloudflare block page typed `identity_required`** on the Stage B rungs (openalex, doaj),
  while the SAME page class is typed `challenge_or_bot_check` on 37 other rows (landing, open_access). Its markers
  sit ~773 KB into an 832,805-byte page, past the one detector's 64 KB window; only the landing rung reads the
  whole body. D24 said there is ONE challenge detector; in effect there are two.
- **5 rows: ordinary pages typed `challenge_or_bot_check`** by the landing rung's C6-RG marker-free rule
  ("200 + text/html + no citation metadata = an interstitial"): NASA's LPV documents page, three Crossref blog posts
  (the HTML IS the work, D12) and OSF's app shell. The rule decided 5 DOI-page verdicts in the run; 0 of 5 were
  interstitials.

The other 9 WRONG rows: one bioRxiv 429 rate-limit page typed a challenge on openaire while landing typed the same
page class `api-error`; one Internet Archive query-syntax ERROR typed `not-in-archive/not_in_corpus` (the query for
187's corporate author was malformed; IA never searched); seven Wayback captures of HTML article pages, served with
HTTP `Content-Encoding: gzip`, typed `compressed_or_archived_payload` (the word the survey gives a PDF inside a
wrapper; the other 11 Wayback HTML captures are `html_response`).

None of this moves a gated counter of this class: `bad_file_untyped`, `blocked_untyped` and
`budget_exceeded_silently` count MISSING words and silence, and read 0 honestly (7 D29 rows excused). **No gated
counter measures whether a word is RIGHT** — that is the gap these rows fall through.

A fix changes rung code after the run, so it needs a re-freeze and a re-run of the affected rows, never these rows
re-graded under new code. The affected run rows: L007 L019 L037 L040 L044 L045 L052 L054 L059 L060 L061 L064 L065
L066 L090 L108 L113 L114 L134 L135 L136 L166 L167 L193 (and L092 for the undetermined pair).

fired: bad_file_untyped=1 on a CONSTRUCTED 200 HTML page served for a PDF link with the typing step disabled (typing_disabled_bad_file, litkb_test_w4, re-fired by referee-vocabulary at 2ef3d68)
fired: blocked_untyped=1 on E13's real recorded 403 challenge with the typing step disabled (typing_disabled_blocked, litkb_test_w4, re-fired by referee-vocabulary at 2ef3d68)
fired: budget_exceeded_silently=1 on E13's two-rung ladder run past a frozen one-attempt budget with the budget object removed (budget_removed, litkb_test_w4, re-fired by referee-vocabulary at 2ef3d68)

## 1. The oracle (mine, independent of the builders' code — Codex X9)

Scripts under `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-vocabulary\`. None imports `litkb` or
`qc/instruments`; none calls `Client.challenge_cause`, `is_challenge`, `ledger.type_blocked`, `accept.accept` or
`landing.classify`. I read the builders' detector only AFTER my reader had typed every row, to explain the
disagreements.

- `cas.py` reads the cassette index (3,632 entries, 199 takes over 195 rows) and the body store directly, and pairs
  each attempt with its recorded terminal response by (URL, status, served sha, nearest time). **2,171 of 2,171
  attempts that carry a terminal URL were matched**; the 250 that carry none made no request (191 EarthArXiv map
  misses, 54 `browser/manual-step`, 5 in-run duplicate arXiv asks).
- `oracle.py` types one recorded response from status, headers and body with rules written from the plan text:
  challenge at ANY status (item 2; D24's MDPI case); `not_found` = 404/410, and for Wayback an availability/CDX
  answer with no capture (item 6, D43); `identity_required` = 401/407, a 403 whose text asks the reader to log in,
  or a redirect to a login endpoint (C13); `html_or_reader` = HTML where the file was asked (C13); the bad-file words
  from C1-RG (lstrip magic, 5,000-byte floor, `%%EOF` in the last 8 KiB) and C18 (gzip / zip / tar magic); transport
  and transient from D15 and guard 15. The vendor marker list is my own.
- `score2.py` types EVERY recorded response an attempt names (terminal, `detail.tried`, `detail.detail` host:code
  pairs, `detail.landing` DOI page and candidates) and compares word by word with the ledger.
- **Revisions after the first pass, stated because an oracle tuned on the rows it scores can fit them.** Each was
  prompted by a page my reader misread, and each is a vendor's own self-description, not a fit to the ledger:
  (1) markers matched on the HTML-entity-decoded page too (MDPI's Akamai page writes `Reference&#32;&#35;`); the
  bare `/cdn-cgi/challenge-platform` marker DROPPED (Cloudflare injects it into ordinary pages — clarku.edu's real
  Digital Commons record carried it, and my first pass wrongly called that page a challenge while the ladder was
  right); a 403 whose visible text asks the reader to log in (OpenReview); titles that name the check ("Client
  Challenge", "Making sure you're not a bot"); Cloudflare's error-box token. (2) response HEADERS
  `x-amzn-waf-action: challenge` / `cf-mitigated: challenge`; the whole body read (to 4 MB), not 300 KB. (3) a 3xx
  read by its Location (Radware's `validate.perfdrive.com` = challenge; an SSO endpoint = identity). (4) in the
  judge, `html_or_reader` accepts any HTML answer at a PDF candidate (the word reads "HTML or reader").
  The revisions moved rows both ways. Toward agreement with the ledger: the entity decoding (MDPI), the "Client
  Challenge" title, the Cloudflare error box, the login text (OpenReview), the perfdrive redirect (IOP), the
  `html_or_reader` reading, and dropping the injected-script marker (clarku.edu, 2 rows back to CORRECT). To WRONG:
  the Anubis title (8 rows), the AWS WAF header (6 rows) and the whole-body read (4 ScienceDirect rows typed
  `identity_required`) — 18 rows, each checked by eye against the recorded page (§2.2).

## 2. The scored rows

### 2.1 Every typed and `api-error` row of the run (625 rows) — ledger word vs my reader

| status / sub_status | route | rows | CORRECT | WRONG | UNDET |
|---|---|---|---|---|---|
| api-error / — | commoncrawl | 14 | 14 | 0 | 0 |
| api-error / — | crossref-link | 1 | 0 | 1 | 0 |
| api-error / — | landing | 2 | 2 | 0 | 0 |
| api-error / — | ncbi-idconv | 2 | 2 | 0 | 0 |
| api-error / — | openaire | 4 | 4 | 0 | 0 |
| api-error / — | openalex | 1 | 0 | 1 | 0 |
| api-error / — | s2 | 2 | 2 | 0 | 0 |
| api-error / — | wayback | 60 | 60 | 0 | 0 |
| bad-file / compressed_or_archived_payload | wayback | 7 | 0 | 7 | 0 |
| bad-file / html_response | crossref-link | 21 | 21 | 0 | 0 |
| bad-file / html_response | doaj | 3 | 3 | 0 | 0 |
| bad-file / html_response | hal | 6 | 0 | 6 | 0 |
| bad-file / html_response | open_access | 32 | 24 | 7 | 1 |
| bad-file / html_response | openalex | 3 | 2 | 1 | 0 |
| bad-file / html_response | s2 | 8 | 7 | 1 | 0 |
| bad-file / html_response | wayback | 11 | 11 | 0 | 0 |
| bad-file / stub_not_article | landing | 1 | 1 | 0 | 0 |
| blocked / challenge_or_bot_check | crossref-link | 64 | 64 | 0 | 0 |
| blocked / challenge_or_bot_check | doaj | 28 | 28 | 0 | 0 |
| blocked / challenge_or_bot_check | europepmc | 11 | 11 | 0 | 0 |
| blocked / challenge_or_bot_check | landing | 101 | 96 | 5 | 0 |
| blocked / challenge_or_bot_check | open_access | 44 | 44 | 0 | 0 |
| blocked / challenge_or_bot_check | openaire | 11 | 10 | 1 | 0 |
| blocked / challenge_or_bot_check | openalex | 26 | 26 | 0 | 0 |
| blocked / challenge_or_bot_check | publisher-url | 18 | 18 | 0 | 0 |
| blocked / html_or_reader | landing | 1 | 1 | 0 | 0 |
| blocked / identity_required | doaj | 2 | 0 | 2 | 0 |
| blocked / identity_required | openaire | 1 | 1 | 0 | 0 |
| blocked / identity_required | openalex | 3 | 0 | 2 | 1 |
| blocked / identity_required | venue | 7 | 7 | 0 | 0 |
| blocked / not_found | s2 | 2 | 2 | 0 | 0 |
| blocked / not_found | wayback | 26 | 26 | 0 | 0 |
| not-in-archive / no_pdf_link | landing | 4 | 4 | 0 | 0 |
| not-in-archive / not_in_corpus | ia | 98 | 97 | 1 | 0 |
| **total** | | **625** | **588** | **35** | **2** |

The 297 correct challenge rows, by the signature my reader found: `cf-mitigated: challenge` header 113, Akamai 71,
Springer Nature's "Client Challenge" 64, Cloudflare page 37, AWS WAF header 9 (all landing's), Radware 2, Anubis 1.
The 60 Wayback `api-error` rows: 30 transient (429/503/504) and 30 stopped part-way by the host cool-down with the
skipped URL recorded and `retriable` true (builder-fix7, D45). The 98 IA rows: 96 zero-hit answers and 1 whose two
hits are other works (Sinopoli's two 2010 arXiv papers) — the builder's extension of `not_in_corpus` to an archive
miss (the plan names only the freeze gate and a shadow front's miss page for that word; noted, not scored wrong).

The 1,546 rows with an untyped status (`no-oa-copy`, `unresolved`, `ok`, `measured`, `known-bad`, `binding-failed`,
`duplicate-held`, `manual-step`) — no response of theirs is a challenge by my reader, except `ok`/`measured` rows
where one candidate was challenged and another served the PDF (a hit is not a refusal). 0 challenges booked as a miss.

### 2.2 The 35 WRONG and 2 UNDETERMINED rows, named (attempt id prefix / route; run row)

| class | rows | attempts | run rows | what the recorded response is | ledger word |
|---|---|---|---|---|---|
| A1 Anubis at 200 | 8 | 01a0d2a1-64a4 hal, 01a0d2eb-4068 hal, 01a0d459-c890 hal, 01a0d46a-3509 hal, 01a0d477-97c2 hal, 01a0d48d-f774 hal, 01a0d477-973f open_access, 01a0d477-9cdc s2 | L019 L066 L090 L108 L136 | hal.science / inria.hal.science / hal.inrae.fr: "Making sure you're not a bot!" (Anubis proof-of-work page) | bad-file/html_response |
| A2 AWS WAF 202 | 6 | 01a0d452-9124, 01a0d455-d67c, 01a0d48d-9507, 01a0d48d-c187 open_access; 01a0d455-d69a crossref-link; 01a0d455-d69e openalex | L059 L060 L134 L135 | empty body, `x-amzn-waf-action: challenge` (doi.org, journals.ametsoc.org, infoscience.epfl.ch) | bad-file/html_response ×4; api-error ×2 (with `retriable` false) |
| A3 Incapsula at 200 | 2 | 01a0d4a3-83a6 open_access, 01a0d4a3-8401 openalex | L193 | projecteuclid.org: "Request unsuccessful. Incapsula incident ID" | bad-file/html_response |
| A4 reCAPTCHA at 404 | 1 | 01a0d44b-089e open_access | L054 | hdl.handle.net → a reCAPTCHA "security verification" page at 404 (plus two ScienceDirect block pages) | bad-file/html_response |
| B ScienceDirect block page | 4 | 01a0d284-f605 openalex, 01a0d44b-08c8 openalex, 01a0d284-f70c doaj, 01a0d449-3c9c doaj | L052 L054 L065 | 403, "There was a problem providing the content you requested … Reference number … IP Address", Cloudflare error box — at bytes 772,869–773,838 of 832,805 | blocked/identity_required ("403 page with no challenge signature") |
| C C6-RG marker-free | 5 | 01a0d293-8334, 01a0d456-9293, 01a0d458-989b, 01a0d49a-5965, 01a0d49b-bf42 (all landing) | L007 L061 L064 L166 L167 | NASA LPV documents page; 3 Crossref blog posts; OSF's app shell — ordinary 200 HTML, no vendor marker | blocked/challenge_or_bot_check |
| D bioRxiv 429 | 1 | 01a0d48d-f721 openaire | L136 | Cloudflare page at 429: "We have received a high number of requests from this session … will reload automatically" (a rate notice; landing typed the same page class `api-error`, retriable) | blocked/challenge_or_bot_check |
| E IA query error | 1 | 01a0d294-075c ia | L007 | `{"error":"a structure was opened but not closed (group open at position 1)"}` — the creator clause carried the corporate author's parentheses | not-in-archive/not_in_corpus ("0 hit(s)") |
| F gzip-coded HTML | 7 | 01a0d301-47d3, 01a0d308-6c4d, 01a0d30f-889d, 01a0d314-4ba3, 01a0d458-535e, 01a0d47d-d440, 01a0d47f-09fe (wayback) | L037 L040 L044 L045 L061 L113 L114 | Wayback `id_` captures of article/abstract HTML (Cambridge, IOP, OUP, Science, Crossref, T&F ×2) served with `Content-Encoding: gzip`; decoded, each is an HTML page | bad-file/compressed_or_archived_payload |
| U bare 403 | 2 (UNDET) | 01a0d46a-fc20 open_access (bad-file/html_response), 01a0d46a-fc4c openalex (blocked/identity_required) | L092 | linkinghub.elsevier.com 403 "403 Forbidden", 520 B, no marker | two words for one page; the plan text does not say which |

Why each class happens (read in the code AFTER scoring): `netutil.Client.challenge_cause` reads the whole marker
list only at 403/503 and only in the first `MARKER_WINDOW` (64 KB); at any other status it reads the TITLE only
(survey G0d) — Anubis's title carries no listed marker, Incapsula's page has no title, the 404 reCAPTCHA title is
"Verificación de seguridad"; `CHALLENGE_HEADERS` holds `cf-mitigated` and `x-datadome`, not `x-amzn-waf-action`
(A1–A4). The landing rung adds rules of its own in `landing._challenge` — the WAF status 202 (`waf-202`), per-rule
signatures searched in the WHOLE body (its comment records the ScienceDirect text "far past guard 3's 64 KB
window") — and `landing.classify`'s transient-first guard; the Stage B rungs and open access do not share them, so
one page gets two words (A2, B, D). `landing.classify` purpose "page" returns `challenge_or_bot_check` for any 2xx
HTML page without citation metadata (C6-RG) (C).

What the wrong words do downstream: a challenge booked `bad-file` is not dead in the run and is invisible to any
count of challenge rows — HAL's report line `yield: hal=0/187` reads as "HAL had nothing" when HAL served a bot
check on 5 works; `identity_required` on Elsevier's bot block tells S4.6 to send those works to credentials, not
the browser rung; the C6-RG rows make the landing route dead for those works in the run; the IA error row records a
search that never happened as a miss for 187 (D23's corporate-author gap reaching Stage E3).

## 3. Structural checks on EVERY ladder-1 attempt row (3,842 rows, 187 works) — `structural.py`

| check (plan item 2 / ruling) | rows checked | offences |
|---|---|---|
| a sub-status on every `bad-file` `blocked` `not-in-archive` `skipped` `budget-stop` row | 1,960 | 0 |
| sub-status in the plan's word list for its status | 1,960 | 0 |
| basis `live` on every sub-status the run wrote | 1,960 | 0 |
| terminal URL / status / dt on every row with HTTP codes; terminal code among the codes | 2,118 | 0 |
| `retriable` set on every request row, NULL on every skip / stop | 3,842 | 0 |
| `blocked` never retriable; `bad-file` never retriable | 345 / 92 | 0 / 0 |
| `api-error` retriable (84 true; a transient terminal code never false) | 86 | **2** false (A2's two rows, code 202) |
| D15: every row whose EVERY code is 0 is `api-error`, retriable true (the negative) | 7 | 0 |
| `kind` = `pdf` exactly when the served body (read from the store) starts with `%PDF-` | 558 with a served sha | 0 |
| served sha present in the cassette; every hit carries one | 558 | 0 / 0 |
| a PolicyDecision `allowed` for its own route in `detail.policy` before every request | 2,118 | 0 |
| no shadow request: 216 annas/scihub rows all `skipped`; no cassette entry to a shadow host | 216 / 3,632 | 0 / 0 |
| shadow refusals carry "the shadow tier is switched off" | 197 | 0 |
| `dead_route` / `dead_in_run` skips: the named prior row exists, has that status, is not retriable, is DEAD for the route (run.DEAD_STATUSES) / is `blocked` in ladder-1 | 37 / 9 | 0 |
| `backoff_window` skips: trigger attempt exists with 429/503 on the cooled host; skip before `cool_until` | 20 | 0 |
| `policy_refused` skips carry a refusal with its reason (shadow 197; Common Crawl 102 with D39's measured text) | 299 | 0 |
| `budget-stop`: route `ladder`, `budget_seconds`, elapsed past 505 s (533 / 613 / 642 s), `not_asked` named | 3 | 0 |
| a work that launched a rung at ≥ 505 s with no budget row (my own reading of `detail.ladder.elapsed_s`) | 187 works | 0 |

Notes (not offences): 249 rows with empty `http_codes` carry terminal facts — 196 no-request rows (EarthArXiv map
misses, in-run duplicate arXiv asks) carry `terminal_dt`, and 53 `open_access/no-oa-copy` rows carry Unpaywall's
200 terminal while `http_codes` omits the lookup's own code. The 1,053
`no_identifier` skips record the closure text under a `detail.policy` key that is not a PolicyDecision; for
`publisher-url` (173) the work HOLDS a DOI and the real reason is "no template for this prefix" — the word is a
stretch. 19 `annas` rows are `dead_route` (history) rather than `policy_refused`; with the tier off both are true and
no request was made. Across Stage B rungs the same miss is spelled `no-oa-copy` or `unresolved` (0013's words).
33 historical `not-in-archive` rows (Anna's) are untyped; no counter or backfill covers that status.

## 4. The named rows of the plan for this class

- **The 59 backfilled rows** (`backfill.py`): the live typing equals the tracked CSVs on 59 of 59 (bad-file 20,
  blocked 39), and both CSVs hash to the shas the two `acquisition_backfills` rows recorded (`68a28516…`,
  `6411325e…`). Where bytes were kept my reader re-typed them: bad-file 6 of 6 agree, blocked 12 of 12 agree
  (Li_2022's kept ScienceDirect page included — the label is right, and D38's `inferred` basis is the conservative
  choice because the one detector cannot see its marker). 41 rows have no kept bytes; their `inferred` basis is the
  honest word (D30), not re-typable. CORRECT.
- **The 7 D29 misbooked rows**: all 7 untyped on live, and they are exactly the 7 NULL `bad-file` rows all-time
  (`blocked` NULL all-time 0). CORRECT (negative).
- **MDPI L071–L073** (and every MDPI work in the run, 17 works): every `www.mdpi.com` Akamai 403, on every route that
  asked it (open_access, crossref-link, openalex, doaj, landing), is `blocked/challenge_or_bot_check` — never
  `bad-file` (D24). MDPI was asked per work on every work (guard 29: no host suppression on a single 403). CORRECT.
- **Shadow `skipped/policy_refused` rows**: 197 policy refusals with the switch's reason + 19 `dead_route`; 0 shadow
  requests; bban has no rows (item 5b not built — out of scope by the Scope ruling). CORRECT.
- **In-run `dead_in_run` skips**: 9, each after a `blocked` row of ladder-1 on the same work and route, and my
  reader calls every one of those priors correctly typed. Three of them are the canary rows' SECOND takes skipping
  routes their first take blocked (D40) — true, and worth knowing for the replay. CORRECT.
- **D15 negative** (a transport-only failure is `api-error`, never `bad-file`): 7 of 7. CORRECT.

## 5. D36 N3 — the CONTENT of every sidecar the run wrote (`sidecars.py`)

277 `quarantine_payloads` rows were recorded after `frozen_at`, all in ladder-1 (blocked 202, bad-file 67,
not-in-archive 4, binding-failed 4). For every one: the payload file exists and hashes to the row's sha and length;
the `.reason.json` exists at `<stem>.reason.json`, parses, and agrees with the row and its attempt on `sha256`,
`bytes`, `label` = the row's reason, `status` and `route` = the attempt's, `work_key`, `at` (within 2 min of the
row), `source_url` (an URL the attempt names) and the attempt's served sha; none says `backfilled`; no two payloads
share a sidecar path. **277 of 277 consistent.** One note: 276 of 277 sidecars do not carry the attempt's
sub-status — the sidecar's `reason` is the byte-shape note ("they look like HTML") and the WHY lives only on the
attempt row, so a sidecar read alone cannot tell a challenge from an HTML page.

## 6. D43 — Wayback's `not_found` under a hunt that says `challenge`

E07 (L006, 10.17863/cam.133934) and E20 (L003, 10.1201/9781315374321): the run CSV pair is `blocked/challenge` for
both. On each work the ONLY `blocked` attempt is `wayback blocked/not_found`, and my reader reads each recorded
availability answer as `"archived_snapshots": {}` — no capture. No attempt on either work is a challenge (E07's
landing is `not-in-archive/no_pdf_link` on Apollo's page, E20's is `bad-file/stub_not_article`). **The attempt rows
carry the truth; the hunt's `challenge` is false**, exactly the reported limit D43 names.

## 7. Re-fires (verbatim, `litkb_test_w4`, checkout `2ef3d68`)

```
$ PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w4 py -3.12 qc/instruments/litkb_acceptance.py hardening --fire typing_disabled_bad_file --db litkb_test_w4
fire=typing_disabled_bad_file (litkb_hardening_c1a) arm=control bad_file_untyped=0 (bound =0)
fire=typing_disabled_bad_file (litkb_hardening_c1a) arm=known_bad bad_file_untyped=1 (bound =0)
fire=typing_disabled_bad_file FIRED
$ ... --fire typing_disabled_blocked --db litkb_test_w4
fire=typing_disabled_blocked (litkb_hardening_c1a) arm=control blocked_untyped=0 (bound =0)
fire=typing_disabled_blocked (litkb_hardening_c1a) arm=known_bad blocked_untyped=1 (bound =0)
fire=typing_disabled_blocked FIRED
$ ... --fire budget_removed --db litkb_test_w4
fire=budget_removed (litkb_hardening_c1a) arm=control budget_exceeded_silently=0 (bound =0)
fire=budget_removed (litkb_hardening_c1a) arm=known_bad budget_exceeded_silently=1 (bound =0)
fire=budget_removed FIRED
```
Each exited 0. **3 of 3 FIRED.**

D24's mutation rows through the harness (`LITKB_TEST_DB=litkb_test_w4 py -3.12 qc/instruments/litkb_p2_mutations.py
--only I3W1,I3W2,I3W3,I3W4,I3W5,I3W6,I3W7`, exit 0), verbatim verdict lines:
```
baseline (unmutated) (qc/test_litkb_s45_w3.py): 23 passed in 5.98s
baseline (unmutated) (qc/test_litkb_s45_w3.py + qc/test_litkb_landing.py): 132 passed in 30.32s
baseline (unmutated) (qc/test_litkb_s45_w3.py + qc/test_litkb_ledger.py): 83 passed in 21.75s
I3W1 FIRED  -> 8 failed, 75 passed in 19.90s    (restored netutil.py sha256 fd7c2df4ab053717... match: True)
I3W2 FIRED  -> 3 failed, 20 passed in 5.72s     (restored accept.py sha256 bedf150dfdc61768... match: True)
I3W3 FIRED  -> 1 failed, 22 passed in 5.81s     (restored run.py sha256 4ece8af68a829d44... match: True)
I3W4 FIRED  -> 1 failed, 22 passed in 5.83s     (restored run.py sha256 4ece8af68a829d44... match: True)
I3W5 FIRED  -> 1 failed, 22 passed in 5.55s     (restored landing.py sha256 e0635eb85beffa2c... match: True)
I3W6 FIRED  -> 8 failed, 124 passed in 29.10s   (restored open_access.py sha256 7e5a5f155ae8e203... match: True)
I3W7 FIRED  -> 1 failed, 22 passed in 5.47s
baseline again (restored) (qc/test_litkb_s45_w3.py): 23 passed in 5.59s
baseline again (restored) (qc/test_litkb_s45_w3.py + qc/test_litkb_landing.py): 132 passed in 29.97s
baseline again (restored) (qc/test_litkb_s45_w3.py + qc/test_litkb_ledger.py): 83 passed in 19.78s
7/7 mutations fired; baselines passed
```
(The harness prints each row's "restored" line before the NEXT row's verdict; they are regrouped per row here.)

## 8. My own mutations (not in any builder's table: no row touches `CHALLENGE_HEADERS`, `MARKER_WINDOW`, a single marker or `REFUSAL_STATUSES`)

- **M1 — FIRED.** `pipeline/litkb/netutil.py`: `CHALLENGE_HEADERS = (("cf-mitigated", "challenge"), ("x-datadome",
  "protected"))` → `CHALLENGE_HEADERS = (("x-datadome", "protected"),)` (exactly one occurrence). 113 of the run's correctly
  typed challenge rows carry that header on their recorded response (29 landing rows name it as their cause). `LITKB_TEST_DB=litkb_test_w4 py -3.12 -m pytest qc/test_litkb_landing.py
  qc/test_litkb_s45_w3.py qc/test_litkb_ledger.py` → **3 failed, 189 passed in 41.89s**: `[wiley]`, `[oup]` (cause
  `cloudflare` instead of `header:cf-mitigated`) and
  `test_the_one_detector_reads_mdpis_real_akamai_403_and_every_caller_agrees`, whose last assert answered WORSE:
  `Client.challenge_cause(200, …, b"<html>ok</html>", {"CF-Mitigated": "challenge"})` returned `''` — a header-only
  challenge no longer a challenge. Restored: sha256 `fd7c2df4ab05371784c5bf25837276ddc3c285bef115d36bf338cb34c8db6231`
  before = after; `git status` clean.
- **M2 — DID-NOT-FIRE (a gate gap, not counted as a fire).** `MARKER_WINDOW = 64 * 1024` → `MARKER_WINDOW = 4 * 1024`:
  the same three suites plus `qc/test_litkb_accept.py` → 255 passed, exit 0. Nothing tests the window's size, and
  the window is exactly what mis-types class B's 4 real rows (markers at ~773 KB). Restored, sha match.

## 9. The design claims the real rows decide

| claim (source) | real rows | ruling |
|---|---|---|
| a challenge is a challenge at ANY status (plan item 2) | 17 bot checks at 200 / 202 / 404 missed (A1–A4) | **REFUTED as built** — the rule exists (C1A10) but its title-only reading at non-refusal statuses misses Anubis, Incapsula, AWS WAF, reCAPTCHA |
| ONE challenge detector (D24) | the same page two words across routes (A2, B, D) | **NOT MET in effect** — `landing._challenge`'s WAF-status, whole-body rule signatures and transient-first order are the landing rung's alone |
| guard 3: "first-64 KB markers" | ScienceDirect's markers at 772–774 KB of 832 KB | **REFUTED on this corpus** (the builders measured it and fixed landing only; M2 shows no test holds the window) |
| survey G0d: at a non-refusal status read the TITLE only (a solved page names its guard in its scripts) | clarku.edu's real page carries Cloudflare's injected script; the ladder did not call it a challenge | **CONFIRMED** in principle; the title list is stale (A1, A3, A4) |
| C6-RG marker-free: 200 + HTML + no citation metadata = an interstitial | decided 5 DOI-page verdicts; 0 of 5 were interstitials | **REFUTED on this corpus** (precision 0/5) |
| C6-RG's second marker table (`_fs-ch-`, "client challenge") | 64 Springer Nature rows | CONFIRMED |
| D24's MDPI case: Akamai 403 = challenge, never bad-file | 17 works, every route | CONFIRMED |
| guard 29: no host suppression on a single 403 | MDPI asked per work on 17 works | CONFIRMED |
| guard 14: a skip is a row with a reason | 1,421 skips, 0 NULL; every reason checked against the ledger | CONFIRMED |
| guard 12: a declarative budget, never silent | 3 stops; 0 silent | CONFIRMED |
| guard 15: `retriable` per attempt | 3,842 rows; 2 offences (A2) | CONFIRMED with 2 exceptions |
| D15: transport-only is `api-error`, retriable | 7 of 7 | CONFIRMED |
| C18: `compressed_or_archived_payload` = a PDF inside a wrapper | 7 uses, all HTML under HTTP content-coding | **the word is used for a meaning the survey did not give** (F) |

Different-model-family coverage: Codex's design review (`codex-design-review.md`, item 2) read the taxonomy mapping,
guard 15's trace and the refusal-ladder predicate. It did NOT read guard 3's 64 KB window, G0d's title-only rule,
the C6-RG marker-free rule, the vendor marker list, or D24's one-detector consistency — every ruling above on those
rests on the survey plus same-family builders and auditors only.

## 10. What I did not do

No fix, no commit, no live write, no network. I did not score the Stage C rules themselves (stage-c's), the kill
criterion (stage-b's) or the replay (replay's); I scored only the WORDS those rungs wrote. The 41 backfilled rows
with no kept bytes cannot be re-typed from evidence (UNDETERMINED by construction; D30's `inferred`). I did not
decide whether a bare 403 is `identity_required` or a challenge (U) — the plan text does not say. The recording
report counts `entries` 3,509 while the index file holds 3,632 lines (superseded takes); not scored here.

## 11. Commands the claims rest on (scratch = `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-vocabulary\`)

- `py -3.12 dump.py` (reader: every ladder-1 attempt after `frozen_at` → `attempts.json`, 3,842 rows)
- `py -3.12 score2.py` (my reader over the cassette → `score2_rows.csv`; the §2 tables)
- `py -3.12 structural.py` (§3; → `struct_out.json`), `py -3.12 backfill.py` (§4), `py -3.12 sidecars.py` (§5),
  `py -3.12 counters.py` (all-time NULL counts)
- `sha256sum` of the two typing CSVs; the re-fires and the harness (§7); `mutate.py apply|restore` + pytest (§8)
- scratch file shas at writing: `oracle.py` 4d261acf…, `score2.py` fff24ef0…, `cas.py` da463a61…,
  `structural.py` f838a648…, `sidecars.py` 47c6f096…, `backfill.py` 3d48aafc…
