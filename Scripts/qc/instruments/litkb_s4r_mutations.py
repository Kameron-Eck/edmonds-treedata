"""S4 builder R — the completeness rule, the one current-run join, and retiring a run set: show
each guard FIRE (CLAUDE.md 3.4c).

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w9 py -3.12 \
        qc/instruments/litkb_p2_mutations.py --only S4R1,S4R3,S4R4,S4R5,S4R6,S4R7,S4R8,S4R9

Same machinery and the same ledger as the P6 / S2 / S3 legs: the rows are appended to the ONE
shared table at import, because the per-call-site rule covers the whole package. They live in
their own file so that three builders working S4 in parallel do not all append to the end of
`litkb_p2_mutations.py`.

WHAT EACH ROW IS FOR:

  * **S4R1 and U5 are the two halves of one guard**, and they are separate rows for the reason
    U1/X12 are: one guard, two ways to break it, two different failures. The current-run join used
    to be written out at five sites; it is now `litkb.readability.current_run_join()`, and it says
    two things. S4R1 drops the CANONICAL half: a run `litkb.retire_run` has retired comes back
    into search, into `use.locate_quote` and into the review grader, which makes migration 0030's
    `canonical = false` mean nothing at all. **U5**, in the P2 ledger, drops the CURRENT-RUN half:
    every reader sees every run's blocks, which on the 2026-09-21 live corpus is 3.55x the corpus,
    71.9 % of it text that is no longer the file's answer. U5 used to mutate the copy in `use.py`;
    that copy is gone, so it is REPOINTED here and now breaks all five sites at once — which is
    what moving a guard into one place is supposed to cost. It is not restated as an S4R row,
    because two rows making the identical edit would be one break counted twice.

  * **S4R3, S4R4 and S4R5 are the three branches of the completeness rule**, one row each because
    each alone is a different wrong answer to a different question. S4R3 removes the zero-content
    branch: a file whose extraction RAN and produced nothing reads `extracted` again, with
    `blocks: 0` — a work litkb_search cannot return one word of, reported as readable. S4R4
    removes the every-file branch, restoring `any(current_run_id)`: one readable file beside one
    unreadable one reads `extracted`, so a search answers from the first and silently misses
    everything in the second. S4R5 removes the disagreement branch: a work whose files disagree
    reports the first file's reason as though it were the work's. Neither S4R3's nor S4R4's case
    has ever fired on live data (0 works with more than one active file, 0 current runs with no
    blocks), which is exactly why the rule could stay wrong for as long as it did.

  * **S4R6 and S4R7 are `retire_run`'s two refusals**, one row each. S4R6 removes the current-run
    refusal: the pointer's own target is retired, leaving a file whose current run holds no
    canonical block — `extracted`, answering nothing, by the very operation that was supposed to
    clean up. S4R7 removes the `use_evidence` refusal: a run a USE is anchored in is retired, so
    somebody's recorded evidence is left quoting text the database now calls non-canonical. On the
    live corpus that is 6 of the 676 superseded runs and 3,766 blocks — the refusal fires on real
    data, not only in a fixture.

  * **S4R8 puts the reason derivation back on the ARTIFACTS**, which is the expression `hunt.py`
    carried until S4: `"fresh" if detail["tei"] and detail["docling"] else …`. The live
    `Maiti_2022` run has a `.docling.json` on disk, 69 `grobid_regions` and 0 `docling_regions`,
    and that expression calls it `fresh` — a two-tool extraction reported for a run docling
    contributed nothing to.

  * **S4R9 is the GROBID lifecycle**, found by builder Q1 on 2026-09-21 and fixed here because
    `hunt.py` is this brief's. `extract/grobid.py::start` is idempotent and returns True when the
    service was ALREADY ALIVE, so the hunt's `finally` — which read that return as "I started it"
    — stopped a GROBID somebody else was holding open on every hunt. The mutation removes the
    `not was_alive` half of the condition, which is the code as it stood.

NOT COVERED BY A ROW, and said rather than left out: the `_classified` guard in
`readability.py` (a bound file with a classification row is named by its residue class rather than
`already-bound`) reads `litkb.extraction_jobs`, which builder Q1's migration 0029 creates. Against
a database at 0028 the branch is unreachable, so a mutation there fires nothing. It needs a row
once 0029 lands.
"""
PKG = "pipeline/litkb"
MIG30 = "pipeline/litkb/db/migrations/0030_retire_runs.sql"
TESTS_S4R = ["qc/test_litkb_readability.py", "qc/test_litkb_retire.py",
             "qc/test_litkb_hunt_grobid.py",
             "qc/test_litkb_first_use.py", "qc/test_litkb_hunt.py"]
IDS = ["S4R1", "S4R3", "S4R4", "S4R5", "S4R6", "S4R7", "S4R8", "S4R9"]


def register(block, replace, site):
    # `site` is part of the registrar signature the P2 ledger passes; this leg adds no
    # per-call-site row because it targets no helper in HELPERS.
    del site

    replace("S4R1", f"{PKG}/readability.py",
            'f"  AND {file}.current_run_id = {block}.run_id AND {block}.canonical ")',
            'f"  AND {file}.current_run_id = {block}.run_id ")',
            "`canonical = false` stops meaning anything: a run litkb.retire_run has retired is "
            "searchable, quotable and gradable again, at all five read sites at once",
            tests=TESTS_S4R)
    block("S4R3", f"{PKG}/readability.py",
          "guard: a current run with no canonical block is zero-content, never extracted",
          "a file whose extraction RAN and produced nothing reads `extracted` again with "
          "`blocks: 0` — a work litkb_search cannot return one word of, reported as readable, "
          "which is the state the old ladder called deliberate",
          tests=TESTS_S4R)
    block("S4R4", f"{PKG}/readability.py",
          "guard: extracted means EVERY active file has current-run canonical text",
          "the ladder goes back to `any(current_run_id)`: one readable file beside one unreadable "
          "one reads `extracted`, so a search answers from the first and silently misses "
          "everything in the second",
          tests=TESTS_S4R)
    block("S4R5", f"{PKG}/readability.py",
          "guard: files that disagree are partial",
          "a work whose files disagree reports the FIRST unreadable file's reason as the work's, "
          "so `partial` is never said and the caller is sent to fix one file when there are two "
          "different problems",
          tests=TESTS_S4R)
    block("S4R6", MIG30, "guard: the file's current run is never retired",
          "retire_run retires the pointer's own target: the file keeps a current run whose blocks "
          "are all non-canonical — `extracted`, answering nothing, produced by the very operation "
          "meant to clean up",
          tests=TESTS_S4R)
    block("S4R7", MIG30, "guard: a run a use quotes is never retired",
          "a run a USE is anchored in retires: recorded evidence is left quoting text the database "
          "now calls non-canonical. 6 of the 676 superseded runs on the live corpus are in exactly "
          "this state",
          tests=TESTS_S4R)
    block("S4R9", f"{PKG}/hunt.py",
          "guard: a hunt stops GROBID only when the hunt started it",
          "every hunt calls G.stop() again, whoever started the service: an operator holding a "
          "wsl.exe client open for a batch, or the run that is about to hunt the next reference, "
          "loses GROBID under it — the state S4 found the machine in after S3's hunts",
          tests=TESTS_S4R)
    # A REPLACE, not a block: deleting the guarded region would leave `reason` unbound and the
    # hunt would die with a NameError, which "fires" for a reason that is not the defect (the RC16
    # note). The replacement is the expression hunt.py actually carried until S4.
    replace("S4R8", f"{PKG}/hunt.py",
            '    reason = readability.extracted_reason(detail["stats"], fresh=True)',
            '    reason = ("fresh" if detail["tei"] and detail["docling"] else\n'
            '              "docling-only" if detail["docling"] else "grobid-only")',
            "the reason goes back to ARTIFACT EXISTENCE: the live Maiti_2022 run has a "
            "`.docling.json` on disk, 69 grobid_regions and 0 docling_regions, and is reported "
            "`fresh` — a two-tool extraction claimed for a run docling contributed nothing to",
            tests=TESTS_S4R)
