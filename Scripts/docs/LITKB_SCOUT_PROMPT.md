# The lit-scout launch prompt (template)

The prompt a headless scout run is launched with carries **a topic and a workstream slug, and
nothing else**. Everything else the scout needs — the query plan, the source ladder, the eight
required fields, the stop rule, the `SCOUT-STOP:` line — is in the two tracked files it reads:
`.claude/agents/lit-scout.md` and the "Stage 1 — discover" section of
`.claude/skills/literature/SKILL.md`.

## Why the prompt may not name a paper

Proving run 2 (2026-09-20) handed its agent four works by key and DOI with the expected claim
written out for it. That run proved the *recording* machinery: given a prior, does the pipeline
test it. It could not prove the *discovery* machinery, because there was nothing left to discover
— and it could not prove the priors were honest, because the prompt supplied them.

`decisions.yaml` → `litkb-k2-no-seeding` (Kam, 2026-09-20) rules that the scout's expectations
must be its own: it states a confidence per expectation, and the honesty check fires naturally or
the run is UNDETERMINED and gets one bounded rerun. A prompt that names the paper, or names the
claim, hands back exactly what the ruling removes.

So the template below is enforced by a test, not by care:
`qc/test_litkb_acceptance.py::test_the_scout_prompt_template_names_no_work` fails if this file
contains a DOI, an arXiv id or a work key. The test is on THIS file, so the template cannot rot
into one that seeds.

## The template

Substitute `<TOPIC>` and `<SLUG>`. Nothing else changes.

```text
You are the lit-scout. Work unattended; nobody will answer a question. Read, in this order:
.claude/agents/lit-scout.md (your role), then the "Stage 1 - discover" section of
.claude/skills/literature/SKILL.md (your procedure). Follow that section exactly.

TOPIC: <TOPIC>

STEP 1 - open the workstream: litkb_ws_open(slug="<SLUG>", purpose="lit-scout discovery run on
the topic above; drop-offs only, no full text read").

STEP 2 - run Stage 1 to its stop rule. Every drop-off carries all eight required fields, and
why_relevant ends with your stated confidence. Do not read any full text.

STEP 3 - end with the SCOUT-STOP line as the first line of your last message, then the list of
drop-offs.
```

## What is NOT in the prompt, and why each one is absent

| absent | why |
|---|---|
| any DOI, arXiv id or work key | `litkb-k2-no-seeding`: the scout discovers, the prompt does not |
| any expected claim | same ruling — the expectation must be the scout's own, with its own confidence |
| the field list, the stop rule, the ladder | they are in the SKILL section; a prompt that restates them is a copy that rots (CLAUDE.md §3.3) |
| a drop-off target number | 15 is a cap. A prompt asking for "at least ten" turns a cap into a quota and a thin topic into fabricated rows |
| `--allowedTools` reasoning | the agent frontmatter carries the tool set; see `Reports/LITKB_SCOUT_LAUNCH.md` for the measured enforcement and the exact command |

## The nonsense-topic run

The acceptance counters' known-bad (`litkb_acceptance.py scout`) is a topic the literature does not
address. It uses the SAME template with a different `<TOPIC>`, and it passes only by ending at
`n=0` with a stated reason — never with a drop-off. `dropoffs>=10` is deliberately not asserted for
that run; `stated_reason=1` is what it reads.
