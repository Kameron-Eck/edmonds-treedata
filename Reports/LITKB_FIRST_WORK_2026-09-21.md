# litkb S2 — the first unknown work crossed the whole loop (2026-09-20/21)

Session S2 of `Scripts/LITKB_WORKPLAN.md`. One genuinely unknown open-access work — discovered by
the scout, absent from the base, never seeded — crossed drop-off → hunt (the one spending hunt) →
extraction → verified use → review → `review-check` → `review-context` → Codex → the acceptance
grade, against a manifest frozen before the hunt. Every number below is read from a tracked file
or a tool's own output; nothing is restated from a session's report.

## The grade

`py -3.12 qc/instruments/litkb_acceptance.py first-work --manifest
Reports/LITKB_FIRST_WORK_2026-09-21_manifest.json --review Reports/reviews/first-work-1-2026-09-21.md
--codex-report Reports/codex/first-work-1-2026-09-21.codex.json`:

```
new_works=1 bound=1 extracted=1 searchable=1 verified_uses=3 claims_ungraded=0 operator_interventions=0
```
exit 0. The replay known-bad, run live: a second manifest frozen AFTER the work
(`_derived/first-work/first-work-1-manifest-AFTER.json`, untracked) grades `new_works=0 …` and
exits 1. The URL-landing-without-event known-bad is
`qc/test_litkb_hunt.py::test_a_url_landing_with_no_acquisition_event_makes_the_verifier_go_red`.

## Every id

| what | id |
|---|---|
| workstream `first-work-1` | `01a0c1c6-6549-710e-a70c-98e3a0bfe173` (main tree, branch `work/20260920-litkb-s2-run`) |
| manifest frozen (db clock) | 2026-09-21T05:12:37.763019Z, head `0dd8886`, repo tip 28 / **db tip 27** |
| baseline | works 447 · files 235 · blocks 86 583 · hunt_requests 4 · uses 0 |
| `litkb_work` before the hunt | `absent` (after the freeze) |
| drop-off (lit-scout, Sonnet) | `01a0c1cb-1ef7-7fe1-b521-e9beaf105eec` · DOI 10.5194/isprs-annals-v-2-2022-275-2022 |
| hunt | CLI `py -3.12 -m litkb hunt <doi> --hunt-request …`, 104.9 s, `refusals: []` |
| work | `01a0c261-a50b-7541-aec3-4f8a09da2724` · `Maiti_2022_effect-label-noise-semantic` |
| admission | `01a0c261-a531-7833-a731-895ab59d0745` (registry, crossref-verified DOI) |
| acquisition attempt | route `open_access` → `ok` (14.9 s) |
| file | `01a0c261-df48-777c-8ff9-f2012c0edddd` · sha256 `3f82736e…928081` · 8 pages |
| extraction run | `01a0c263-3977-7483-bdb9-f483890782be` · 113 blocks · GROBID TEI · **docling=false** |
| use, supports | `01a0c264-fe44-74d7-a4be-46e088007b5f` (p.6 block `…3a57-…-53d78f24af5f`) |
| use, context | `01a0c265-2086-7495-a95b-54d1f31f2b71` (p.5 block `…3a21-…-b44f2f8368fc`) |
| use, refutes | `01a0c26d-f68a-7462-b812-ed7e81246b59` (same p.5 span) |
| drop-off resolution | `contradicted` (1 confirming, 1 contradicting — the 0023 conflict case) |
| review | `Reports/reviews/first-work-1-2026-09-21.md` — `review-check` PASS, 0 findings |
| context | `_derived/first-work/first-work-1.context.md`, `missing: []` |
| Codex | `Reports/codex/first-work-1-2026-09-21.codex.json`, session `01a0c271-712e-78f1-8599-231b0a6171b1`, 3/3 SUPPORTED, gate `overreach=0 unsupported=0 hash_mismatch=0` |

Three other drop-offs (`…1f83`, `…1fe7`, `…20ab`) remain `open`: S2 hunts one work.

## The contract (S2 Work, second bullet)

Merged as `0dd8886` (branch `work/20260920-litkb-s2`, builder report
`jobs/litkb-s2/builder-first-work.md`, audit `jobs/litkb-s2/auditor-first-work.md`). The URL path of
`hunt` now records an `acquisition_attempts` row through the same `record_acquisition_attempt` the
route path uses (route `hunt-url`; detail `sha256 md5 bytes source_url filed http_status`);
`litkb.acquire.events.bound_without_event(conn, ws, since)` names every file bound in a workstream
after an instant with no `ok` event **for the work it is bound to**, and feeds
`operator_interventions`. Migration `0028` widens the route CHECK. The audit's three findings —
a silent except branch, a `NOT EXISTS` with no `work_id` predicate, a client-clock freeze — were
fixed in `84873cb` with a firing test each. Nine known-bads fire in
`qc/test_litkb_acceptance.py` / `qc/test_litkb_hunt.py`.

## Bounded failure outcomes, said plainly

1. **The run happened with the repo one migration ahead of the live database** (0028 unapplied;
   applying live migrations is Kam's). The executed path — DOI → open-access route — does not
   touch the `hunt-url` route, and the manifest records both tips. Preflight read
   `migration_mismatch=1` throughout; the freeze went ahead on the away-mode rule after 70
   minutes. The URL half of the contract is therefore proven by its tests, not live.
2. **The review's first draft failed `review-check` at line 1.** The writer could not read
   `docs/LITKB_REVIEW_GRAMMAR.md`: the agent-frontmatter hook in `review-writer.md` and
   `librarian.md` names `${CLAUDE_PROJECT_DIR}/.claude/hooks/litkb_guard.py`, and
   `CLAUDE_PROJECT_DIR` is `Scripts\` (where every session opens) while `.claude/` is one level
   up. `py` on a missing script exits 2 — the BLOCK code — so a warn-only guard has been blocking
   every Read/Grep/Glob of both agents from `Scripts\`. Measured; the tested fix (a locator
   one-liner that fails open) is `Reports/LITKB_AGENT_HOOK_PATH_2026-09-21.md`, Kam's to apply (agent
   hook frontmatter is classifier-refused for Claude). Draft 2 was dispatched with the grammar
   inline; the writer wrote it, the orchestrator only renamed the file. No hand edit of the review.
3. **K2's first half and a one-work run.** `review-check` fails `k2-never-fired` unless the
   workstream holds a `contradicted` or `unconfirmed` expectation; `open` does not count, and a
   second no-spend admission would have made `new_works=2`. The honest resolution was in the
   text: the drop-off expected shift to be the most damaging mode, and for the tree class — the
   one class this pipeline segments — the paper says the reverse. A `refutes` use on that span
   resolved the request `contradicted` alongside its aggregate confirmation. S5's runs hunt
   several works and will not meet this corner; S2's plan bullet did not anticipate it.
4. **Docling produced no artifact** on a native 8-page Copernicus PDF (`docling=false`, 38 s);
   GROBID carried the extraction, coverage min_share 0.66 with one page below the 0.8 floor.
   Not a refusal; S4 (readability) classifies it.
5. **paper-search `search_unpaywall` returned empty for every DOI**, including known gold-OA
   controls; the scout used OpenAlex `pdf_url` instead and said so in every drop-off. An
   `api-error` instance for S3's register.
6. **A pipe masks a gate's exit code.** `gate | tail -N; echo $?` reports `tail`'s 0 — it hid
   `review-check`'s first refusal and the replay mutation's exit 1 for one call each. Read `$?`
   from the gate alone (or `${PIPESTATUS[0]}`).

## Not done

- `litkb-s2` decisions: none needed; no science ruling was taken.
- The `first-work-1` token: vaulted at landing (`D:\edmonds-pipeline\secrets\litkb-tokens\first-work-1\`).
- Promotion of the three uses is on Kam's track (`litkb-operational-verdict`).
