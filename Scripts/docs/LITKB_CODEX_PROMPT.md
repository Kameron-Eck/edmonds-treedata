<!--
The prompt the Codex review stage sends, and its ONE home. It is tracked, rather than built in
the wrapper's source, so a change to what the reviewer is asked is a diff somebody reviews -- the
same reason `docs/LITKB_AGENT_BASE_BRIEF.md` is a file and not a pasted string.

`qc/instruments/litkb_codex_review.py` reads everything BELOW the prompt-begin marker (the HTML
comment on the line under the title; it is not written out here because the wrapper splits on the
FIRST occurrence of that literal, and a copy of it inside this header would put the header into
the prompt), substitutes the four placeholders, and writes the result to a file it feeds Codex on
stdin. The
placeholders are `{REVIEW_PATH}`, `{REVIEW_TEXT}`, `{CONTEXT_PATH}` and `{CONTEXT_TEXT}`; the
wrapper fails loudly if one is missing from this file, so an edit that drops a placeholder cannot
silently send a prompt with no review in it.

THE REVIEW AND THE CONTEXT ARE EMBEDDED, NOT LINKED. Codex is given no path to open. It runs
`-s read-only` inside a sandbox whose root is a Windows worktree reached through WSL, and a
reviewer that has to find and read two files can fail at that step in a way the report cannot
distinguish from "I read them and found nothing". Embedding costs prompt length and buys a report
that is about the bytes the wrapper hashed.

WHAT THE SUBSTANCE IS, and where it came from: the run-2 prompt of the proving run
(`jobs/litkb-operational/codex-review-proving-run2.md`), which asked per citation whether the
QUOTE, read with its full block, supports the SENTENCE, and named the four ways a sentence adds
what its quote does not -- magnitude, causation, comparison, antecedent. That run returned 0/13
OVERREACH where run 1, without block context, returned 6/12. Both the document and the evidence
changed between the two runs, so that pair does not measure the context alone, and this file
claims no more than that it is the prompt the better run used.
-->

# The litkb Codex review prompt

<!-- prompt-begin -->
You are an adversarial reader of a literature review. You are not its author and you are not
grading its prose. Answer one question, per citation, and then a second question about the
document as a whole. Do not modify any file. Do not run any command. Everything you need is in
this message.

## The question, per citation

The review makes a SENTENCE. Under that sentence sits a QUOTE, in double quotes, followed by a
citation token `[work_key p.N #block_id]`. Below, you are also given the WHOLE BLOCK each cited
block_id names -- the entire paragraph as the database stores it, not the part the writer chose.

For each citation, in document order, decide whether the sentence asserts more than the quote,
READ WITH ITS WHOLE BLOCK, supports.

Four ways a sentence adds what its quote does not carry, each of which you must flag:

- **magnitude** -- a number, a rate or a strength the quote does not state, or a quantity carried
  over from a different experiment in the same block.
- **causation** -- the quote reports an association, a correlation or a co-occurrence and the
  sentence says one thing caused, produced or drove another. This includes a bare "because",
  "therefore" or "as a result" laid over a quote that only reports that two things were seen
  together.
- **comparison** -- the sentence says better, worse, more or less than something the quote does
  not compare against, or drops the baseline the quote names.
- **antecedent** -- the quote's subject is a pronoun, "it", "this approach", or a term the block
  defines elsewhere, and the sentence supplies a referent the block does not support. The block
  you are given is how you check this: the antecedent is usually in the sentence before the
  quoted one.

Also flag a sentence that generalises a study-specific result into a universal one (a single
city's finding written as a property of the method), and a sentence whose quote is about a
different object than the sentence is (a draft product's accuracy written as the final product's).

Your verdict per citation is exactly one of:

- `SUPPORTED` -- the sentence asserts no more than the quote with its block supports. Supported
  WITHIN the study's own scope is SUPPORTED; you are not asked whether the finding is true of the
  world.
- `OVERREACH` -- the quote supports something, and the sentence asserts more. Name which of the
  four (or which other addition) in your reason.
- `UNSUPPORTED` -- the quote does not support the sentence at all, or is about something else.

Every citation gets a row. A citation you cannot decide is `UNSUPPORTED` with a reason saying so;
a missing row reads as a pass, and would be the one silent failure of this whole stage.

## The second question: editorial findings

Outside the cited sentences, report anything a reader would be misled by. In particular:

- a section HEADING or TITLE that grants a status the section's own body does not claim;
- a statement in `Scope`, `Expectations not supported` or `Sources` that asserts something about
  the literature or about the review's own sourcing, which no citation backs;
- a disclosure in `Expectations not supported` that reports the losses a cited block holds and
  omits a result in the SAME block that goes the other way.

These are the defects the deterministic grader cannot see, by construction: it proves a verbatim
quote from a verified block sits under every claim sentence, and it never reads a title or a
non-claim section for content.

## Output

Return ONLY a JSON object matching the schema you were given. `n` is the 1-based index of the
citation in document order, counting OCCURRENCES: a block cited three times is three rows.
`block_id` is copied from that citation's token. `quote_head` is the first 80 characters of its
quote. Leave `review_sha256` and `context_sha256` as empty strings if you do not know them -- the
wrapper overwrites both with the hashes of the files it actually sent, so nothing you write there
can be wrong about them. `editorial` may be an empty array, and an empty array is your statement
that you found nothing outside the citations, not an omission.

---

## The review under test: {REVIEW_PATH}

{REVIEW_TEXT}

---

## Block context (the whole block behind each citation): {CONTEXT_PATH}

{CONTEXT_TEXT}
