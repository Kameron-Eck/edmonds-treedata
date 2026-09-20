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
…every SENTENCE carries at least one citation.

## Expectations not supported
…REQUIRED. One entry per expectation that did not come back confirmed.

## Sources
…REQUIRED. A markdown table, one row per work cited.
```

There are exactly **four non-claim sections**, and the list is closed: the **preamble** (anything
before the first `##`), **`Scope`**, **`Expectations not supported`** and **`Sources`**. Every
other `##` heading is a claim section, whatever it is called.

The **first non-blank line** is the header comment. It is the only place the workstream is
named: `litkb review-check` takes the workstream from the document, because a review graded
against a workstream it was not written from would satisfy K2 by holding no expectations at all.
The CLI's `--workstream <id|slug|current>` does not override that — it *asserts* which workstream
the caller believes it is grading, and the grader refuses the run by name when the header
declares another.

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
a delimiter. The citation must follow the closing delimiter on that delimiter's own line.

**The quote must be a BYTE-EXACT substring of the stored block.** Nothing is normalised — not
whitespace, not line breaks, not quotation marks. The grader asks Postgres whether the quoted
span is a substring of the block's own bytes, the same question migration 0007's trigger asks of
a recorded use, and the review file is read with newline translation **off** so that what you
typed is what is compared.

That has one consequence worth stating plainly, because it is the trap:

* **A stored block may contain `\r\n`.** Which line break an extraction wrote is the PDF's
  business, not yours, and the brief prints it as it is.
* **So quote WITHIN one line of the stored text.** A span that crosses a stored line break can
  only match if your file carries that block's exact break bytes — and a review file therefore
  never needs to contain a CR at all. Re-wrapping a quote, joining its lines with a space, or
  letting an editor reflow it all produce `quote-not-verbatim`, correctly: the reader may not
  rewrite the paper.
* A long quote is fine. A long **line** is fine. A quote that spans the block's own line break
  is the one thing to avoid.

## 3. What a citation may name

Only a **VERIFIED line of this workstream's brief** — the (work key, page, block id) triple, as
printed. A block that exists in the database but that no promotable `use_evidence` row anchors
is not what K1 means by a verified quote, and citing one fails as `not-in-brief`.

**And the words you quote must be inside the span that line verified.** The brief prints each
VERIFIED line's quote verbatim; that text is the exact `[char_start, char_end)` the database
re-read and marked `quote_verified`. Your quote must be that text or a **substring** of it.
Being inside the block is not enough, and the difference is not pedantic: a block is a whole
paragraph, so a block verified for its first sentence would otherwise let you quote its fourth —
which nobody checked — under a claim about the fourth. Quoting outside every verified span fails
as `quote-not-verified-span`.

In practice: **copy the quote out of the brief and shorten it if you must.** Never extend it,
and never go back to the block for more words. If you need a different span of the same block,
that is a new `use` with its own verified quote, recorded through `litkb use add` — not a
citation you can write.

The `abstract_passage` of an EXPECTED line is **never quotable**. It is an agent's unverified
prior, the brief labels it so, and a review that quotes one is asserting from an abstract the
project never ingested.

## 4. Claim sections and K1

Every section that is not `Scope`, `Expectations not supported` or `Sources` is a **claim
section**. The unit K1 is enforced per is the **SENTENCE**, not the paragraph.

It was the paragraph until 2026-09-20, and the stage-8 audit measured what that cost: three
uncited assertions followed by one cited one passed as a single unit. So:

* **Every sentence of every unit carries at least one citation.** A unit is a paragraph
  (consecutive non-blank lines), **each list item separately** (one citation cannot cover a
  bulleted list of five claims), or a **table row**; a block quote (`>`) belongs to the unit
  above it, and an HTML comment and a heading are not prose.
* **Table rows are units.** A findings table is the most natural way to present per-year results
  and it used to be outside K1 entirely. Every data row needs its own citation. Exempt: the
  delimiter row (`|---|---|`) and the header row directly above it, which assert nothing.
* **A fenced code block in a claim section is a FAIL** (`fenced-in-claims`). Fenced text carries
  no citation and the grader cannot see inside it, so it is refused rather than ignored. Put a
  code block in `Scope`, or write the claim as a cited sentence. A `## ` heading at the start of
  a line **ends any open fence**, so an unclosed fence cannot swallow the sections after it (that
  was the way round this guard the guard itself could not see). The cost is that a `## ` line
  inside a genuine code block splits it — which fails loudly rather than hiding anything.

**The sentence splitter is deliberately simple:** `.`, `?` or `!` followed by whitespace. It does
not know abbreviations, and it does not need to, because it errs toward FAIL — a split that
should not have happened leaves a fragment with no citation, which you will see. The one that
will actually bite a literature review is **`et al.`**: `Smith et al. found X "…" [cite].` splits
into `Smith et al.` (uncited, FAIL) and the rest. Write `Smith and colleagues`, or keep the
citation in that fragment. The splitter **does not** cut inside a citation's own quote, so a
faithfully copied two-sentence quote is safe.

The preamble and `Scope` are places K1 cannot police, so they may contain **no** citation and
**no** quoted span; `Expectations not supported` and `Sources` may contain no citation token
either. A citation in a non-claim section fails as `claim-outside-claim-section`. Put the
question, the method and the limits in `Scope`, in your own words. (What a citation in a
non-claim section catches, and what it cannot, is §7.)

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

This section is non-claim, so it carries **no citation token**. To show what the verified quote
actually said, write that as a cited sentence in a claim section and refer to it here by the
hunt_request id; the entry here is about the expectation, not about the evidence.

**K2 also has a first half, and it is now checked.** The workstream must HOLD at least one
expectation the database resolved `contradicted` or `unconfirmed`. A workstream in which every
drop-off came back confirmed fails as `k2-never-fired` — not because the review is badly
written, but because a run that never contradicted anything has not exercised the machinery this
section exists to report. That check is on by default and cannot be turned off; it was a
human-run `hunt-request list --state contradicted` count until 2026-09-20, and a step whose
skipping is invisible is not a gate.

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
* **A literature fact asserted in a NON-CLAIM section.** This is the one hole the grammar creates
  on purpose, and it must be said in as many words: `Scope`, `Expectations not supported` and
  `Sources` exist for the writer's own words, so an **uncited sentence asserting something about
  the literature, placed there, is a grammar violation the grader cannot see.** It is a violation
  — the rule is that claims live in claim sections — and nothing machine-checks it. What the
  grader does catch is the cheap version: a claim that was *moved* there brings its citation or
  its quote with it, and a citation token in a non-claim section fails. A writer who strips the
  citation to hide a claim in `Scope` has broken this grammar and produced an unsourced claim,
  and only a reader can catch it.
* **Whether the review is balanced, complete, or read the right literature.** Coverage is a
  question for the brief and the hunt, not for this file.
* **Whether a `confirmed` expectation was confirmed for the right reason.** The database derives
  `resolution_state` from stance-bearing verified quotes; the grader takes that verdict as given.
* **Prose quality, ordering, or the reasoning between citations.**

## 8. Running it

```bash
cd <worktree>/Scripts
PYTHONPATH=pipeline PYTHONUTF8=1 py -3.12 -m litkb review-check ../Reports/reviews/<slug>.md
PYTHONPATH=pipeline PYTHONUTF8=1 py -3.12 -m litkb review-check <path> --workstream current
```

**The writer does not run this; the orchestrator does.** `review-writer` holds no `Bash` tool,
deliberately: the proposer never scores its own proposal (CLAUDE.md §3.4c). The agent hands back
a path and says the review is ready for `review-check`; whoever dispatched it runs the grader.

One JSON object per finding (`line`, `code`, `detail`, `severity`), then a summary line. Exit 1
when any finding has `severity: fail`. The finding codes are `malformed-citation`,
`block-not-found`, `work-mismatch`, `page-mismatch`, `citation-without-quote`,
`quote-not-verbatim`, `quote-not-verified-span`, `not-in-brief`, `uncited-claim`,
`fenced-in-claims`, `claim-outside-claim-section`, `missing-expectations-section`,
`expectation-not-disclosed`, `k2-never-fired`, `missing-sources-section`, `source-not-listed`,
`source-never-cited`.

Each of those is produced by a guard with a mutation row in
`qc/instruments/litkb_p2_mutations.py` (RC1–RC10) and a test in `qc/test_litkb_review_check.py`:
a gate that has never been shown to fire is not known to work (CLAUDE.md §3.4c).

---

*Added 2026-09-20 with stage 8 (brief → written review). Authored here, in the repository,
because it is a rule and not a measurement (CLAUDE.md §2.3).*
