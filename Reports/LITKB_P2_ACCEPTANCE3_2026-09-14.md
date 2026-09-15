# litkb P2 — independent acceptance, round 3, 2026-09-14

Scope: the fix for round 2's surviving mutation (E3f) and the **per-call-site rule** that was built around it, as landed
in 1becbbc. Worktree `D:\edmonds-pipeline\treedata-litkb`, branch `work/20260913-literature-kb`, HEAD 1becbbc. I wrote
none of this code and none of these tests. Every number below was produced by me, re-running everything (CLAUDE.md
3.4c); no figure reported by the builder is used as evidence.

**Import provenance, checked first.** The main tree carries an editable install of the package, so a mutation applied
here could have "survived" against code loaded from elsewhere. Measured before anything ran, in the exact test
environment: `litkb.__file__` and `litkb.admit.front.__file__` both resolve under `D:\edmonds-pipeline\treedata-litkb\
Scripts\pipeline\litkb\`. `pdfinfo` (poppler 25.07.0) is on PATH, which the E3f-closing test needs.

## Verdict: **P2 ACCEPTED** — no survivor

E3f, the round-2 survivor, is closed. Six further mutations of my own, written from the source at six different guard
helpers, all fired. The harness's static call-site table matches my own scan of the package exactly, and I found no
reference to a guard helper that its `ast` scan cannot see. The three informational mutations at the *deferred*
`redact` / `add_secret` sites all survived, as the builder's own deferral says they would.

## Method

**Fingerprints.** sha256 of **56** tracked files before anything ran: every `*.py` and `*.sql` under
`pipeline/litkb/` (all 14 migrations), `qc/test_litkb_p1.py`, `qc/test_litkb_p2.py`, `qc/test_litkb_annas.py`,
`qc/test_litkb_ops.py`, `qc/test_litkb_harness_sites.py`, `qc/conftest.py`, the litkb testdata and every
`qc/instruments/litkb_*.py`. Re-computed after the last run: **56/56 match**. `__pycache__` excluded.

**Test set.** Every mutation ran the WHOLE `qc/test_litkb_p1.py qc/test_litkb_p2.py qc/test_litkb_annas.py` with
`-m "not litkb_live"`, `-p no:cacheprovider`, on `litkb_test` only (the suite resets and migrates it from the files on
disk). I did not inherit the harness's default of P2 + annas.

**Runner.** My own, in the session scratchpad, not committed, not `qc/instruments/litkb_p2_mutations.py`. Per mutation:
exact-once text edit per file (a target occurring any number but once aborts and rolls back) → run the set → restore the
original bytes → confirm the restore by sha256. "FIRED" = pytest exit ≠ 0 **and** a whole-word `N failed` count > 0
(a strict xfail is not a failure; the baseline carries one).

**Baselines.** `390 passed, 5 deselected, 1 xfailed`, exit 0, before (61.9 s) and after (60.1 s). Separately,
`qc/test_litkb_ops.py qc/test_litkb_harness_sites.py`: `34 passed` — that includes the gate `qc/check.py` actually
runs. Restores: 11/11 byte-identical by sha256; `git status --short` empty at the end.

## 1. E3f, applied exactly as round 2 quotes it

`admit/front.py`'s `_jsonb` still reads `    return Jsonb(jsonb_safe(v))` verbatim, so the round-2 mutation applies
unchanged: strip `jsonb_safe`, leaving `Jsonb(v)`.

| ID | Mutation | Result | First failing tests |
|---|---|---|---|
| E3f | `front._jsonb`: `Jsonb(jsonb_safe(v))` → `Jsonb(v)` | **FIRED** (2 failed) | `test_litkb_p2.py::test_a_nul_in_pdf_metadata_never_breaks_a_registry_admission`, `::test_add_candidate_sends_no_nul_to_the_database` |

Both failures name the guard, not a collateral crash: one drives the `admit --file` registry path that round 2 found
unasserted, the other the candidate path through the same helper. Restored, sha256 match.

## 2. Six mutations of my own, at six different helpers

Each was written by me from the current source (not copied from the harness's `repl` strings), with arguments spliced
parenthesised so no second guard changes by precedence. Where a site has several textual calls in one function I
mutated all of them, as the rule requires.

| ID (site) | Helper | My edit | Result | First failing test |
|---|---|---|---|---|
| S2 `front._call_admit::_jsonb` | `_jsonb` | all four `_jsonb(...)` in the `litkb.admit(...)` argument tuple → `Jsonb(...)` direct | **FIRED** (1) | `test_a_nul_in_pdf_metadata_never_breaks_a_registry_admission` |
| S26 `commands.cmd_admit::_labels` | `_labels` | `agent, session = _labels(args)` → `(args.agent, args.session)` | **FIRED** (1) | `test_the_cli_normalises_its_labels_before_any_write[admit]` |
| S13 `binding.bind::window_refusal` | `window_refusal` | both calls (the window loop and the title-region list) → `""` | **FIRED** (7) | `test_binding_refuses_a_title_that_appears_only_in_a_reference_list[heading, bracketed, author_year]` |
| S16 `annas.read_quota::parse_quota` | `parse_quota` | `parse_quota(body)` → `(0, 1000)` | **FIRED** (5) | `test_read_quota_fails_closed_on_a_bad_answer`, `test_archive_reads_the_account_counter_before_every_download_request[at_margin, past_limit]` |
| T18 `binding.bind::verdict` | `verdict` | `v = verdict(ratio, author_near, text_layer)` → `v = "bound"` | **FIRED** (23) | `test_binding_matches_the_surname_as_a_whole_token[Ward/Hall/Long…]` |
| S12 `resolver.resolve_doi::normalize_doi` | `normalize_doi` | both calls → the raw value | **FIRED** (1) | `test_litkb_annas.py::TestResolveDoi::test_a_candidate_doi_is_canonicalised_and_one_without_a_doi_resolves_to_nothing` |

6/6 fired; each first failure names the guard that was removed. Restores: 6/6 sha256 match.

## 3. The `--sites` table against my own scan

I ran `py -3.12 qc/instruments/litkb_p2_mutations.py --sites` myself: **35 call sites, 34 covered by a row, 1
equivalent**, no PROBLEM lines, exit 0 — the same 35 the P2 report's table lists, helper for helper.

**My independent check, for the blind spot the rule cannot see by construction.** `sites_of_text` only recognises a
guard used as an `ast.Call`. A guard passed as a *value* — `map(normalize_doi, …)`, `key=normalize_doi`,
`functools.partial`, a helper stashed in a dict and called later, or used as a decorator — would be invisible to it and
would reproduce exactly the E3f class. I walked every `.py` under `pipeline/litkb/` with my own `ast` pass and listed
every `Name`/`Attribute` node naming one of the ten `HELPERS` that is **not** the `func` of a `Call`:

> **zero bare references**, and one decorator in the package (`staticmethod`, on `netutil.is_challenge`).

So every use of every targeted helper inside the package is a direct call, and the scan sees all of them. I also
grepped for litkb imports outside the package: only `qc/conftest.py` (`db.connect`, `db.migrate`) and two instruments
(`litkb_binding_region.py`, `litkb_title_threshold.py`) — none calls a guarded helper, so the rule's scope over
`pipeline/litkb/` misses nothing reachable.

**Call sites the harness misses: none found.** The one `EQUIVALENT` entry, `binding.author_on_page::tokens_contain`, I
re-checked by grep: one hit across `Scripts/pipeline` and `Scripts/qc`, its own `def`. It is dead code and the reason
given is about the code, not about the tests, which is what the rule demands.

## 4. Three mutations at the DEFERRED redaction sites — informational

These do not block acceptance: `DEFERRED_HELPERS` declares the `redact` / `add_secret` / `_redacted` family out of
scope, with a measurement behind it. I re-derived a piece of that measurement rather than take the builder's 19-of-20
on trust. Sites chosen outside B11's two:

| ID | Site | My edit | Result |
|---|---|---|---|
| RD1 | `annas.result` (the attempt-record builder) | `r["detail"] = redact(r["detail"])` → pass-through | **SURVIVED** (390 passed) |
| RD2 | `annas.open_session` | `add_secret(key)` → removed (the session's key is never registered for redaction) | **SURVIVED** (390 passed) |
| RD3 | `resolver.resolution_log_line` | `redact(" | ".join([...]))` → pass-through | **SURVIVED** (390 passed) |

3 of 3 survived, consistent with the builder's declared 19-of-20. **What a survivor means, plainly:** at that site the
archive key can reach a printed log line, a stored `acquisition_attempts.detail` row or an exception string
**unstripped, and no test in the P1+P2+annas set would notice.** The guard is real code and is called; what is missing
is any assertion that it is called *there*. RD2 is the widest of the three, because `open_session` is where the key is
first read, so failing to register it disarms redaction for every later site in that run. Closing these is a test job,
as the deferral says, and it is properly out of P2's scope — but it is a live gap, not a theoretical one.

## 5. Read-only probes on `litkb`

All probes ran with `default_transaction_read_only = on`; everything as `litkb_reader` except the migration count
(`litkb_meta` needs the owner, opened via `connect_admin`). No write reached `litkb`. Port 5433; no password printed.

- **Migrations: 14**, the highest `version` 14 (`0014_referee_p2_fixes.sql`).
- **No duplicate normalised DOIs.** 30 works, 30 active DOI identifiers; **0** whose stored `value_norm` differs from
  `litkb.norm_identifier('doi', value)`; **0** differing from Python `textnorm.normalize_doi`; **0** normalised DOIs —
  SQL-canonical or Python-canonical — sitting on more than one work.
- **The 5 gate works are bound.** `litkb-p2-gate` is `open`; admissions 7 `admitted` / 3 `refused` over 7 distinct
  works; its 5 current file versions are each `bound` at binding ratio `1.000`.
- **`edge-pre1990` is `open`.** Candidates `admitted` 23 / `duplicate` 3 / `duplicate-review` 1 / `rejected` 9;
  admissions `admitted` 22 / `proposed` 1 / `refused` 13 — every count equal to round 2's, independently read.
- One difference from round 2, stated rather than smoothed over: the work count is **30**, where round 2 read 29. That
  is one work admitted since; the DOI-uniqueness probe is over the current 30 and is clean.

## 6. Secrets, `30a44fe..1becbbc`

**2** commits, 67,866 bytes of patch, 687 added lines, searched in Python for the **actual values**; only names and
present/absent were printed.

- **Absent, all of them:** the 5 passwords in the shared `pgpass.conf`, the promoter and ingest passfile passwords, the
  Anna's Archive key, the paper-search env value, the Drive folder id, the service-account `private_key`,
  `private_key_id`, `client_email` and `client_id`, and the `token` of **both** `.litkb-workstream` files (the repo
  root's and `edge-pre1990`'s).
- **Shapes in added lines:** 0 pgpass-shaped lines, 0 64-hex values, 0 `key=` / `token=` / `password=` literals.
- A broad scan of every ≥16-character token in `D:\edmonds-pipeline\secrets\` returned two patch hits; both were
  resolved and are **not** credentials: the service account's `project_id` (a project name; its private key is absent)
  and the literal field name `workstream_id`, which appears as JSON text in both the secret file and the patch.
- Both `.litkb-workstream` files are git-ignored (`.gitignore:2:/*` and `.gitignore:136`).
- **Secrets rung:** `py -3.12 qc/secrets_check.py` → `clean — 1182 indexed files`.

## End state

- Final baseline `390 passed, 5 deselected, 1 xfailed`, exit 0; `test_litkb_ops.py` + `test_litkb_harness_sites.py`
  `34 passed`; 56/56 fingerprints match; `git status --short` clean.
- `litkb` received no writes; `litkb_test` was used only by the suite.
- Nothing under `D:\edmonds-pipeline\Literture\` was read, moved or written. No network request, no archive download;
  `LITKB_LIVE` was never set (the 5 deselected tests are the `litkb_live` ones).
