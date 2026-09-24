# litkb S4.5 referee — rung class `stage-a` (plan item 3)

Referee: `referee-stage-a` (Opus 5.5, fresh agent; built, proposed, integrated and audited nothing in S4.5).
Checkout: detached `D:\edmonds-pipeline\wt-s45-ref-stage-a` at main `2ef3d68`. Worker DB: `litkb_test_w1`
(no advisory lock and no session on it before use). Live `litkb` read only as `litkb_reader`; the corpus read
only; no network. Written 2026-09-24 after the live run completed.
Full working notes: `D:\tools\claude-config\jobs\litkb-s4-5\referee-stage-a.md`.

Inputs, read-only from the main tree:
- manifest `_derived/hardening/hardening-1-manifest.json` (frozen 2026-09-24T08:22:40.799Z, head `cd2f23b`;
  file sha256 `5873d3fc…`)
- run CSV `_derived/hardening/LITKB_LADDER1_2026-09-24_run.csv` (195 rows; sha256 `8ddad087…`)
- cassette index `_derived/hardening/cassettes/ladder-1/index.jsonl` (3,632 recorded interactions; sha256 `4566ea28…`)
- the ladder-1 attempt rows after `frozen_at`, read live as `litkb_reader`

## Verdict: ACCEPT-WITH-NOTES

On the real rows the plan names, Stage A does what item 3 says:
- The router classes every preprint as a preprint. It never lets one reach a shadow route.
- The DOI-prefix router names the right native server, and the ladder reaches that server where litkb has a route
  for it.
- The one Wave-0 derivation that the real rows exercise, a `10.48550/arXiv.<id>` DOI to its arXiv id, is right on
  10 of 10 works.
- The publisher-URL rung builds the Atypon URL exactly as I build it, on 18 of 18 works, and types every refusal
  correctly.
- The EarthArXiv map lookup agrees with my own lookup on all 191 attempts (187 works). There is no hit in either.

One row is WRONG, on the class label only: Hickey_2014 (L057). The router has no way to call a work that carries a
DOI "HTML-only", so the 4 works that S4.5 decision D12 names as HTML-is-the-work get `paper` or `preprint` instead
(F1). No outcome in ladder-1 depends on that label, because the shadow tier was off. It matters before S4.6
switches the tier on.

Several parts of Stage A had NO real input in this run, so they are UNDETERMINED:
- ISBN-10 → 13: live holds no ISBN-10 at all.
- The arXiv → `10.48550` DOI candidate: the 8 arXiv-only rows were refused at admission, before Stage A ran (F3).
- A0 flags and A1 rejections.
- A7's positive path.

The gated counter this class owns, `preprints_sent_to_shadow=0`, is **VACUOUS on live**. The shadow tier was
switched OFF (S4.5 decision D27), so no shadow spend was possible whatever the router did. The router's evidence is
below: my class oracle over all 195 rows, the re-fire, and my own mutation.

fired: preprints_sent_to_shadow=1 on a preprint hunted with the Stage A router disabled (router_disabled_preprint, litkb_test_w1, re-fired by referee-stage-a at 2ef3d68)
fired: preprints_sent_to_shadow=1 on DelgadoQuiros_2025 hunted with the router intact and CLASS_OF_TYPE mapping preprint to paper (referee mutation RSA1, the router fire's control arm, litkb_test_w1)
fired: router_decisions_disagreeing=18 on the 187 real ladder-1 works re-classified under referee mutation RSA1 and scored by the referee's own class oracle (restored code: 1, L057)

**Scope, stated.**
- The shadow tier was OFF for the whole run. Every `annas`/`scihub` row is `skipped`: 193 are `policy_refused`
  ("the shadow tier is switched off") and 19 are `annas` `dead_route`.
- No `bban` row exists, because item 5b was not built (Scope ruling).
- The recorded cassette holds 0 interactions with any shadow host (annas-archive, sci-hub, bban, scidb, libgen).
- So on live, the router's decision is visible ONLY as the class it recorded (`detail.stage_a.class` on each work's
  first attempt row). The router's own refusal reason appears on no live row, because the tier switch refuses
  first.
- NOT BUILT, and out of scope by ruling, not defects: the offline Sci-Hub/LibGen membership table (Scope ruling
  2026-09-23), ISBN-13 → ISBN-A (C2a: needs a hyphenated ISBN that A1 does not keep), and shortDOI expansion (it
  costs a request; there are 0 shortDOIs in the base).

## 1. The oracle (mine; X9)

The scripts are in `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-stage-a\`. They never call
`stage_a.work_class`, `routed`, `native_route`, `derive`, `publisher_urls` or `eartharxiv_map` as the
oracle. Those are called only to REPLAY the code under my mutation, in section 5.

- **Class** (`oracle.py`, rule written from the plan text):
  - `html-only` if the work is one of D12's HTML-is-the-work works (cause `html_is_the_work` in the tracked item-8
    CSV).
  - Else `preprint` if `main_works.type` is `preprint` OR the crosswalk CSV's `cr_type` is `posted-content`. This
    is plan (b)'s two-part definition.
  - Else `book` / `chapter` / `report` / `thesis` from the type or Crossref's type vocabulary.
  - Else `paper`.
  - The expected shadow decision is "refused" for `preprint`, `book` and `html-only`.
  - A third input is Crossref's type as RECORDED at run time in the cassette (175 records). It drifted from the
    09-22 crosswalk CSV on 0 rows.
- **Native API** (`named.py`, `claims.py`): my own registrant-prefix table. `10.48550` is arXiv, `10.31235` is
  OSF (SocArXiv), `10.1101` is bioRxiv, and `10.2139` (SSRN), `10.13003` (Crossref's blog) and `10.64000` (Rogue
  Scholar) have no route in the 0033 vocabulary. For each row I checked whether the native host was actually asked:
  the hosts recorded for that row's tag in the cassette.
- **Wave 0**: I parse the arXiv id out of the DOI string myself and compare it with the live
  `identifier_versions` row and its provenance. Independent confirmation comes from DataCite's RECORDED record
  (`url` = `arxiv.org/abs/<id>`, `alternateIdentifiers` arXiv) or, where DataCite was never asked, the arxiv.org
  PDF URL that Unpaywall named and that was bound.
- **ISBN**: my own ISBN-10 and ISBN-13 check-digit code and my own 10→13 conversion, run over every live `isbn`
  row.
- **A4**: my own Atypon URL (`https://<host>/doi/pdf/<doi>`, with the host from the registrant). I compare it with
  the recorded URL. I type the recorded bodies with my own markers: `<title>`, Cloudflare `cf-chl` /
  "Just a moment", and the `cf-mitigated` header.
- **A7**: my own CSV read of the harvested `phase4/qc/litkb_eartharxiv_map.csv` (11,360 DOIs that carry a
  `pdf_url`), joined to every DOI each run work holds.
- **Refused bytes** (for the named negatives): I read page 1 of each quarantined PDF with pypdfium2 and compare it
  with `main_works.title`/`authors`.

## 2. Scored rows — the rows run-plan §5 names for this class

Row ids are the frozen manifest's.

| row(s) | expected (plan / recorded truth) | what the rung did (ledger, run CSV) | my oracle | verdict |
|---|---|---|---|---|
| L070 Schindler_2024 `10.2139/ssrn.4979539` hunt | a preprint among the archive misses: routed to its native API, never to a shadow route | class `preprint`, native `''`; shadow rows `skipped` (dead_route, policy_refused); `blocked/403` | preprint; SSRN has no route in the vocabulary, so `''` is right; 0 shadow requests | CORRECT |
| L075 Thakur_2021 `10.48550/arxiv.2104.08663` hunt | preprint → arXiv | `preprint`, native `arxiv`; arxiv.org asked 4× (open_access 1, landing 3); the arXiv PDF matched a known-bad sha (`binding-failed`); `held/not-acquired` | preprint → arXiv, reached | CORRECT (F2) |
| L167 DelgadoQuiros_2025 `10.31235/osf.io/cxp4q` hunt | preprint → OSF | `preprint`, native `osf`; `osf` rung asked (api.osf.io ×2, osf.io ×4) → `known-bad` (sha b045d360, `binding-failed`); `blocked/challenge` | preprint → OSF, reached | CORRECT (F2) |
| L168 L169 L170 L171 Vixie/Jaffe/Kumar/Gulrajani `10.48550/arxiv.*` measure | preprint → arXiv; never shadow (D18 as well) | `preprint`, native `arxiv`; arxiv.org asked 4× each (open_access 1, landing 3; both `measured`); shadow `skipped/policy_refused` | same | CORRECT ×4 |
| L061 L063 L064 Tkaczyk ×3 (`10.13003/ief7aibi`, `10.64000/e6ey2-wce96`, `10.64000/vgpgj-j8126`) hunt | run-plan: "HTML-only, never sent to a PDF archive"; plan (b): `posted-content` = preprint | class `preprint`, native `''`. L061/L064: shadow `skipped` (dead_route / policy_refused), `blocked/challenge`. L063: bound at Stage B (`crossref-link` → Rogue Scholar PDF), no shadow row | D12 → `html-only`; both classes are routed away; no native server; 0 shadow requests | CORRECT on the decision and the negative; label disputed (F1) |
| Tkaczyk ×3 negative: never sent to a PDF archive | no shadow-route request | 0 non-skip shadow rows; 0 shadow-host interactions in the cassette. They did reach Stage E Wayback/IA, which are legitimate web archives. I read "PDF archive" as the plan's "scidb-by-DOI archive path". | agrees | CORRECT ×3 |
| Thakur / DelgadoQuiros negative: binding refusals named | each refusal named, never silent | every route that fetched their bytes wrote `known-bad` with `known_bad {id, reason: binding-failed, source: quarantine_payloads, rel_path}`: Thakur on open_access, landing and wayback; DelgadoQuiros on open_access and osf | named. BUT my page-1 reader says both refused PDFs ARE the works (F2) | CORRECT ×2 (as named); F2 |
| Wave 0, `10.48550` DOI → arXiv id: L075 L161 L162 L168 L169 L170 L171 L196 L197 L198 | the arXiv id, with provenance | 10 `identifier_versions` rows `arxiv`, `asserted_by=deterministic`, `derived_from=doi:<the DOI>`, promoted, agent `ladder-run`, session `s4-5`, written in the run; 0 write errors | my parse = the written id on 10/10. DataCite's recorded record confirms 5/5 where asked (L075, L168–L171). On the other 5 the hunt landed at `open_access` first (DataCite never asked), and Unpaywall's bound `arxiv.org/pdf/<id>` names the same id | CORRECT ×10 |
| ISBN-10 → 13 on the ISBN carriers in the run: L003 L005 L027 L028 L046 L076 L077 L173 L174 | an ISBN-10 held → its ISBN-13 written | `stage_a.derived = []` on all 9; each gained its ISBN-13 rows from Crossref in Stage B (`asserted_by=crossref`) | 0 ISBN-10 held by any of the 9, and 0 `isbn` values of length 10 anywhere in live `main_identifiers`; all 15 values pass my ISBN-13 check digit; A1 rejected none | UNDETERMINED ×9 (the rule never had an input); A1 on these values CORRECT |
| A4, Atypon template: L002 (ACM), L047 (ACM), L039 L067 L068 L069 L112–L123 (T&F) | a PDF URL built from the DOI; an HTML/challenge answer typed, never bound | recorded URL = `https://<host>/doi/pdf/<doi>` on 18/18; every one `blocked/challenge_or_bot_check`, 403 | my URL = the recorded URL on 18/18. All 43 recorded responses at an Atypon `/doi/pdf/` path (the rung's 18 plus other rungs' `?needAccess` variants) are 403, `<title>Just a moment...</title>`, Cloudflare markers and `cf-mitigated` → a challenge | CORRECT ×18 (yield 0/18) |
| A4, every other run row (169 rows, 173 attempt rows incl. second takes) | no template → no request | `skipped/no_identifier` | no Atypon prefix | CORRECT |

Named-row checks: **43 CORRECT, 0 WRONG, 9 UNDETERMINED.**

## 3. Every run row through the class oracle (and A3, A7)

`oracle_class.csv` in my scratch folder has one line per run row (195).

| outcome | rows | which |
|---|---|---|
| class = my class, decision agrees | 183 | paper 158, preprint 14, chapter 8, report 2, book 1 |
| decision agrees, label disputed | 3 | L061 L063 L064 (Tkaczyk ×3): code `preprint`, mine `html-only` (F1) |
| label WRONG | 1 | L057 Hickey_2014 (D-Lib, `10.1045/july2014-hickey`): code `paper`, mine `html-only` (D12). The router's shadow decision is "eligible" where the builder's own `SHADOW_REFUSED_CLASSES` intends "refused" (F1). Latent: the tier was OFF |
| UNDETERMINED | 8 | L010–L017, the ruled arXiv-only tracker rows: admission refused `api-error/registry-transient` (arXiv answered 406) before Stage A ran; no summary exists (F3) |

- **All-rows verdict: 186 CORRECT, 1 WRONG (L057, label only), 8 UNDETERMINED.**
- **Live shadow requests: 0** (DB: every `annas`/`scihub` row is a skip; cassette: 0 shadow-host interactions).
- Crossref's live answer never tightened a class. On no real row was Crossref's type more restrictive than
  `main_works.type`, so `tighten` is UNDETERMINED on real rows.
- **A3**: the recorded `native` equals my registrant table on 191/191 Stage A summaries (10 `arxiv`, 1 `osf`,
  1 `biorxiv` with no route, 179 none).
- **A7**: 191 `eartharxiv` attempts (187 works, 4 of them with second takes), all `no-oa-copy`. My lookup finds 0
  of the run's DOIs in the map, and 0 of the base's 467 DOIs. The driver's line `yield: eartharxiv=0/187` agrees.
  CORRECT on 191 negatives; the positive path is UNDETERMINED.
- **A1 / A0**: 0 identifiers rejected and 0 A0 flags across the 191 summaries. My read of the 175 recorded Crossref
  records finds 0 `update-to`, 0 not-an-article types and 0 `other` types (so the A2 salvage never had an input).
  UNDETERMINED: there is no positive input. The one record with a Crossref `correction` relation
  (10.3390/rs14081777) is the ORIGINAL article, and it was rightly not flagged.

## 4. Re-fire of this class's (c) known-bad (verbatim)

```
$ PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w1 py -3.12 qc/instruments/litkb_acceptance.py hardening --fire router_disabled_preprint --db litkb_test_w1
fire=router_disabled_preprint (litkb_hardening_c2a) arm=control preprints_sent_to_shadow=0 (bound =0)
fire=router_disabled_preprint (litkb_hardening_c2a) arm=known_bad preprints_sent_to_shadow=1 (bound =0)
fire=router_disabled_preprint FIRED
EXIT=0
```
Re-fired: 1 of 1 FIRED. The fire pins the shadow tier ON (`shadow_tier_on`), so it grades the router and not the
switch.

## 5. My own mutation (RSA1), not in the builders' harness (C2A1–C2A36 do not touch the class table)

**The mutation.** Exactly one occurrence, in `pipeline/litkb/acquire/stage_a.py` `CLASS_OF_TYPE`:
`"preprint": "preprint"` became `"preprint": "paper"`. The guard, the call site and the seam are all left
intact. Only the data that feeds them is wrong, so a work typed preprint is classed `paper` and is
shadow-eligible.

**Baseline** (unmutated, sha256 `d397e642…`): `PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w1 py
-3.12 -m pytest qc/test_litkb_stage_ab.py -q -p no:cacheprovider` → `47 passed in 37.38s`, exit 0.

**Mutant**, the same command, one process:
```
FAILED qc\test_litkb_stage_ab.py::test_the_work_class_router_classes_and_the_crossref_salvage
FAILED qc\test_litkb_stage_ab.py::test_every_c2a_fire_fires[router_disabled_preprint]
FAILED qc\test_litkb_stage_ab.py::test_the_ladder_writes_each_rung_s_harvest_on_its_attempt_and_the_router_s_refusal_as_a_skip
FAILED qc\test_litkb_stage_ab.py::test_stage_a_writes_the_certain_wave_0_row_with_deterministic_provenance
FAILED qc\test_litkb_stage_ab.py::test_stage_a_s_record_reaches_the_first_attempt_row_even_when_its_wave_0_write_fails
FAILED qc\test_litkb_stage_ab.py::test_the_router_fire_grades_the_router_with_the_shadow_tier_switched_off
6 failed, 41 passed in 44.14s
```
Every failure is an `AssertionError`, none an import or syntax error, so the mutant answered WORSE:
- `assert 'paper' == 'preprint'`.
- The router fire reads `{'control': 1, 'known_bad': 1}`: with the router intact, the CONTROL arm already sent
  DelgadoQuiros_2025 to the shadow stub.
- The ladder's `annas` row became `not-in-archive` instead of `skipped`.

**My oracle catches the mutant on the real rows.** `oracle_vs_code.py` replays the importable `work_class` on each
of the 187 reached works' live inputs (`main_works.type` plus its own active identifiers) and scores it with my
oracle.
- Under RSA1: **18 decision disagreements**. These are all 17 routed-away preprint/Tkaczyk works: L001 L061 L063
  L064 L070 L075 L161 L162 L166 L167 L168 L169 L170 L171 L196 L197 L198, plus the standing L057.
- Restored: 1 disagreement (L057 only) and 183 exact class matches. That is the same count as the recorded classes,
  so the replay reproduces the ledger.

**Restore.** `sed` rewrote the file with LF endings (content equal, sha `05f0736f…`), so I restored it
byte-exactly with `git checkout -- pipeline/litkb/acquire/stage_a.py`:
- sha256 `d397e6420581d2c3d9390c7fa6882f34b9acb833a9c2d34382ae41e0c0eea763`, equal to the pre-mutation sha;
- `git status --short` is empty;
- the suite re-run gives `47 passed in 40.96s`, exit 0.

## 6. Rulings on the design claims the real rows can decide

- **Survey §M, "shadow libraries never index preprints"** (why A2 routes preprints away): SUPPORTED on litkb's
  own pre-freeze ledger, with a small n.
  - 10 of 10 type-preprint works sent to `annas` came back `not-in-archive`; 2 sent to `scihub` came back
    `blocked`; 0 preprints ever landed from a shadow route.
  - Comparator: `annas` returned `ok` on 22 non-preprint works.
  - The run itself cannot decide it (tier OFF).
- **A3, "prefixes are registrant-owned, so false positives are near-impossible"**: SUPPORTED on the 12
  prefix-routed works. There were 0 false positives, and DataCite confirmed each of the 5 `10.48550` DOIs it was
  asked about.
- **A7, EarthArXiv "disproportionately relevant here"**: MEASURED ZERO on this corpus. 0 of 467 base DOIs are in
  the 11,360-DOI harvested map, and the base holds no `10.31223` DOI. The rung makes no request on a miss, so the
  plan's rule applies: keep it as free and report it as measured-zero.
- **A4 (the Atypon subset built)**: MEASURED ZERO, 0/18.
  - The survey's MEASURED A4 positives were ISPRS and Project Euclid, not Atypon.
  - On the real rows the constructed URL is right, and every T&F/ACM host answers a Cloudflare 403 challenge to
    this client.
  - Cost: one request per 10.1080/10.1145/10.1177 work. The plan's keep rule ("its cost per miss is one free
    call") is met, but its yield here is zero.
- **Wave 0, "a `10.48550` DOI → its arXiv id is certain" (the builder writes it as a fact)**: CORRECT on 10/10.
  - The run-plan's paraphrase "(inverse derivation as CANDIDATE until DataCite confirms)" misreads the plan. The
    plan attaches CANDIDATE to arXiv id → DOI only.
  - Note: `verified_by` stays NULL even on the 5 rows DataCite later confirmed in the same ladder run. The
    confirmation is visible only in the `datacite` row's harvest (`held`).
- **A2 salvage, A0 flags, A1 rejection, `tighten`, ISBN-10 → 13, the arXiv → DOI candidate**: UNDETERMINED. The
  real rows hold no input for any of them (sections 2–3, and F3).
- **Kill criterion**: Stage A has none of its own in the plan. The fan-out kill criterion is stage-b's to score.

**Which conclusions rest on no different-model-family read.** Codex's design review (item 3) checked the digest's
TRANSCRIPTION of the survey: A0/A1/A2/A3/A4/A7 "follow the survey", the salvage rule, and the shortDOI cost. No
different-family read tested the survey's EMPIRICAL claims:
- §M's preprint claim;
- A3's false-positive claim;
- A7's relevance;
- A4's yield;
- the builder's extension of `SHADOW_REFUSED_CLASSES` to `html-only`.

My rulings above are the only independent check on them, and I am the same model family as the builders.

## 7. Findings

- **F1 (WRONG label on L057; a disputed label on L061 L063 L064).** `stage_a.work_class` returns `html-only` only
  for a work holding a `url` and no work-level identifier, which in practice means a page from a URL hunt.
  - Every work that D12 names HTML-is-the-work carries a DOI, so none of the 4 can reach that class.
  - Hickey_2014 (D-Lib) is classed `paper` and is shadow-eligible. The builder's own design says an `html-only`
    work is refused.
  - The Tkaczyk posts are classed `preprint`. That is still refused, and it is consistent with plan (b)'s
    `posted-content` definition. L063's bound Rogue Scholar PDF (page 1: "Blog post published December 18, 2018 in
    Crossref Blog", the work's DOI) also shows that "HTML-only" is not strictly true for every D12 work.
  - Consequence in ladder-1: none, because the tier was OFF and the class is used only by `routed` and `tighten`.
  - To fix before S4.6 enables the shadow tier: give the router a signal for DOI-bearing HTML works (e.g. D12's
    `html_is_the_work` cause), or rule that the plan does not require `html-only` to be refused. A fix changes no
    recorded ladder-1 outcome, so a re-freeze or re-run is not needed for this class.
- **F2 (substrate / binder; not a Stage A defect).** The two named refusals block real works. My page-1 reader says
  both quarantined PDFs ARE the works:
  - Thakur_2021: 24 pages; page 1 has the title "BEIR: A Heterogeneous Benchmark…" and Thakur, Reimers, Rücklé,
    Srivastava, Gurevych. The record's title says "Heterogenous", the arXiv v1 spelling.
  - DelgadoQuiros_2025: 38 pages; page 1 matches the title exactly, with Delgado-Quirós and Ortega.
  - Both `quarantine_payloads` rows have origin `legacy-backfill`, reason `binding-failed`, and
    `reason_source: name`: the reason was read from the FILE NAME.
  - Item 1's rejected-hash lookup now refuses these bytes on every route in the run: Thakur on 3 routes,
    DelgadoQuiros on 2. Two free preprints stay unobtainable on a stale label.
  - Route: the substrate referee and the orchestrator.
- **F3 (substrate; it limits Stage A's reach).** The 8 arXiv-only tracker rows (L010–L017) were refused at
  admission.
  - The recorded requests are `GET http://export.arxiv.org/api/query?id_list=<id>` with
    `Accept: application/atom+xml`, and the answer is 406. That is the survey's B10 warning: the API "406s without
    a browser-ish Accept".
  - The resolver books a 406 as `registry-transient`, but a 406 is deterministic.
  - As a result, the plan's motivating rows for the arXiv → `10.48550` DOI CANDIDATE ("the tracker's arXiv-only
    rows gain a DOI this way") never reach Stage A.
- **F4 (stage-b; latent).** Crossref's `relation.correction` target `10.3390/rs14225898` is a different work (the
  correction notice). It was accumulated into Moghimi_2022's in-run identifier set (`detail.stage_b.gained`).
  - Nothing asked with it (0 cassette requests) and nothing was written, so there was no harm on the real row.
  - A later rung asking with "the work's DOIs" could address the notice. The notice is exactly A0's `correction`
    class.
- **F5 (stage-b; attribution).** On L168–L171 (MEASURE mode) the `arxiv` rung records `no-oa-copy` "already asked
  in this ladder run by open_access". The file IS at arxiv.org; the yield is credited to `open_access` and not to
  the native route.

## 8. What I did not do

- No live write, no network, no fix.
- No full suite: one pytest file, run three times (baseline, mutant, restored), one process at a time on w1.
- I did not score the membership table, 5b, ISBN-A or shortDOI (not built, by ruling).
- I did not score the kill criterion (stage-b's).
- I did not run the binder on F2's bytes.

## 9. Commands (scratch = `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-stage-a\`)

- `py -3.12 dbfree.py`: w1 had no advisory lock and 0 backends.
- `PYTHONUTF8=1 py -3.12 oracle.py` → `oracle_class.csv`, `oracle.out`: rows run 195; 0 shadow-host interactions;
  class agree 183/195; shadow requests sent 0.
- `PYTHONUTF8=1 py -3.12 named.py` → `named.out`: sections (1)–(6) of the named rows.
- `PYTHONUTF8=1 py -3.12 extra.py` → `extra.out`: Wave-0 vs DataCite; my A0 read; my read of the A4 bodies.
- `PYTHONUTF8=1 py -3.12 claims.py` → `claims.out`: A3 table, §M history, A7 coverage.
- `PYTHONUTF8=1 py -3.12 firstpage.py <key>=<rel_path> …`: page 1 of the refused and bound PDFs.
- `PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 counter_live.py <manifest>` → `preprints_sent_to_shadow` (C2a's
  counter, reader) = 0.
- The re-fire (section 4) → `refire_router.out`. The three pytest runs (section 5) →
  `pytest_{baseline,mutant,restored}.out`. `oracle_vs_code.py` → `oracle_vs_{mutant,restored}.out`.
