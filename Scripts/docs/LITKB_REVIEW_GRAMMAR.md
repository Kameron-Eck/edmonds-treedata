# litkb review grammar — the one home for what a written review must look like

A review is the last stage of the literature pipeline: a brief goes in
(`py -3.12 -m litkb brief`), a cited `.md` comes out under `Reports/reviews/`. This file is the
**only** authoritative statement of its form. The writer agent
(`.claude/agents/review-writer.md`) points here rather than restating it, and the grader
(`Scripts/pipeline/litkb/review_check.py`, `litkb review-check`) implements it. A rule written
in two places is a bug — fix this file, not the copy (CLAUDE.md §3.3).

The grammar exists to make `decisions.yaml::litkb-operational-definition` machine-checkable:

> **K1** any claim in the review that does not trace to a verified quote (work key + page +
> block_id) = FAIL.
> **K2** at least one dropped-off expectation must return CONTRADICTED or UNCONFIRMED **and the
> review must say so** — the honesty machinery is required to FIRE, not merely to be present.

---

## 1. The document

```markdown
<!-- litkb-review workstream=<workstream id or slug> -->

# <title>

## Scope
…what question this review answers, what it read, what it did not. No citations, no quotes.

## <any claim section>
…every paragraph carries at least one citation.

## Expectations not supported
…REQUIRED. One entry per expectation that did not come back confirmed.

## Sources
…REQUIRED. A markdown table, one row per work cited.
```

The **first non-blank line** is the header comment. It is the only place the workstream is
named: `litkb review-check` takes the workstream from the document and offers no flag to
override it, because a review graded against a workstream it was not written from would satisfy
K2 by holding no expectations at all.

Headings are matched case-insensitively at `##`. A deeper heading (`###`) does not open a new
section — it stays inside the section above it, so demoting a heading cannot move a claim
paragraph out of K1.

## 2. The citation token

```
[work_key p.N #block_id]
```

* `work_key` — the key exactly as the brief prints it (`Test_2020_abcd1234-paper`).
* `p.N` — the page the brief's VERIFIED line gives, a plain integer.
* `#block_id` — the block uuid the brief's VERIFIED line gives.

Every citation must be **immediately preceded by the verbatim quote it rests on**, in double
quotes, with nothing but spaces or tabs between the closing quote and the `[`:

```markdown
Douglas-fir crowns keep their shape through leaf-off: "the optimism identity holds under an
arbitrary joint model" [Test_2020_abcd1234-paper p.1 #0199a7d2-…-4c1b].
```

Straight (`"…"`) and curly (`“…”`) delimiters are both accepted. A quote may not itself contain
a delimiter. A quote may span a line break **inside** the quotation, but the citation must
follow the closing delimiter on that delimiter's own line.

**Whitespace is not normalised.** The grader asks Postgres whether the quoted span is a
substring of the block's bytes, the same question migration 0007's trigger asks of a recorded
use. An extraction that reflows a line differently from the PDF will not match a quote the
writer re-wrapped. Prefer a span that sits **within one line of the block's text**; if a longer
quote is needed, copy it from the brief unaltered and let the line be long.

## 3. What a citation may name

Only a **VERIFIED line of this workstream's brief** — the (work key, page, block id) triple, as
printed. A block that exists in the database but that no promotable `use_evidence` row anchors
is not what K1 means by a verified quote, and citing one fails as `not-in-brief`.

The `abstract_passage` of an EXPECTED line is **never quotable**. It is an agent's unverified
prior, the brief labels it so, and a review that quotes one is asserting from an abstract the
project never ingested.

## 4. Claim sections and K1

Every section that is not `Scope`, `Expectations not supported` or `Sources` is a **claim
section**. Every prose unit in one carries at least one citation. A prose unit is:

* a paragraph — consecutive non-blank lines;
* **each list item separately** — one citation cannot cover a bulleted list of five claims;
* a block quote (`>`) belongs to the unit above it.

Table rows (`|…`), HTML comments, fenced code and headings are not prose and carry no citation.

The preamble and `Scope` are the two places K1 does not police, so they may contain **no**
citation and **no** quoted span: that is what stops a writer from relabelling its claims as
scope. Put the question, the method and the limits there, in the writer's own words.

## 5. Expectations not supported, and K2

This section is required **unconditionally**, even when it holds nothing — "every expectation
was confirmed" is a claim about the run and must be stated, not left to silence.

For every EXPECTED line of the brief whose `resolution_state` is:

| state | what the review must do | grader |
|---|---|---|
| `contradicted` | name it (hunt_request id or ref), give its `expected_claim`, and say what the verified quote actually said | **fail** if absent |
| `unconfirmed` | name it, and say that nothing ingested has confirmed or refuted it | **fail** if absent |
| `open` | name it, and say it was never linked to a work | notice if absent |
| `confirmed` | nothing (its quote carries the claim in the body) | — |

"Name it" means the hunt_request's **id or its ref appears literally** in the section. A
paraphrase the grader cannot match is, to the grader, an omission.

## 6. Sources

A markdown table, one row per work cited, with the key in backticks so the grader can read it:

```markdown
| work | key | pages cited |
|---|---|---|
| Author (2020), Title | `Test_2020_abcd1234-paper` | 1, 4 |
```

A key cited in the body and missing from the table **fails** (`source-not-listed`). A key listed
and never cited is a **notice** (`source-never-cited`) — a bibliography of things the review did
not use.

## 7. What the grader does NOT check

Stated here so a PASS is never read as more than it is:

* **Whether the claim a sentence makes is the claim its quote supports.** The grader proves a
  verbatim quote from a verified block sits under every assertion. It cannot prove the sentence
  says what the quote says. Paraphrase fidelity is a reader's judgement, and it is the single
  largest thing a green `review-check` does not buy you.
* **Whether the honesty machinery fired at all — K2's first half.** The grader checks that every
  expectation the database resolved `contradicted`/`unconfirmed` is disclosed. A workstream
  holding *none* has nothing to disclose and passes. The operational definition also requires that
  at least one expectation *came back* that way, and that is a property of the run, not of the
  document: count it with `litkb hunt-request list --state contradicted` and `--state unconfirmed`
  before calling a proving run green.
* **Whether the review is balanced, complete, or read the right literature.** Coverage is a
  question for the brief and the hunt, not for this file.
* **Whether a `confirmed` expectation was confirmed for the right reason.** The database derives
  `resolution_state` from stance-bearing verified quotes; the grader takes that verdict as given.
* **Prose quality, ordering, or the reasoning between citations.**

## 8. Running it

```bash
cd <worktree>/Scripts
PYTHONPATH=pipeline PYTHONUTF8=1 py -3.12 -m litkb review-check ../Reports/reviews/<slug>.md
```

One JSON object per finding (`line`, `code`, `detail`, `severity`), then a summary line. Exit 1
when any finding has `severity: fail`. The finding codes are `malformed-citation`,
`block-not-found`, `work-mismatch`, `page-mismatch`, `citation-without-quote`,
`quote-not-verbatim`, `not-in-brief`, `uncited-claim`, `claim-outside-claim-section`,
`missing-expectations-section`, `expectation-not-disclosed`, `missing-sources-section`,
`source-not-listed`, `source-never-cited`.

Each of those is produced by a guard with a mutation row in
`qc/instruments/litkb_p2_mutations.py` (RC1–RC7) and a test in `qc/test_litkb_review_check.py`:
a gate that has never been shown to fire is not known to work (CLAUDE.md §3.4c).

---

*Added 2026-09-20 with stage 8 (brief → written review). Authored here, in the repository,
because it is a rule and not a measurement (CLAUDE.md §2.3).*
