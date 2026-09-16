"""litkb P6 — show every stage-6 (references) guard FIRE (CLAUDE.md 3.4c).

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p6_mutations.py
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p6_mutations.py --only P6-G1

Same machinery as P2 (`litkb_p2_mutations.py`): weaken ONE guard in the real source, run
`qc/test_litkb_references.py`, record whether it failed, restore the file byte-for-byte and check
the restore by sha256; the unmutated set is baselined before and after. Nothing here touches a
database — stage 6 is DB-free — and nothing touches the network: every test in the set answers from
a stub client.

WHY THE ROWS LIVE HERE AND THE ENGINE THERE. The per-call-site rule (P2's docstring) is enforced by
ONE self-check over every call of a guarded helper under `Scripts/pipeline/litkb/`, and stage 6 adds
six calls of `normalize_doi`. Rather than a second, competing self-check, :func:`register` hands
these rows to P2's table at import time (the tail of `litkb_p2_mutations.py` calls it), so the one
self-check — and `qc/test_litkb_harness_sites.py` inside `qc/check.py` — sees the whole package.

WHAT EACH ROW IS FOR, in the §14 P6 terms:

  * **P6-G1** is THE KILL. It removes the DOI-first decision, so a reference that carries a DOI falls
    through to a title search. A DOI one digit off then re-finds the intended work by title and is
    reported `resolved` — the near-miss the phase forbids. If this row ever stops firing, the kill
    is not being tested any more.
  * **P6-G2** lets a DOI resolve to a DIFFERENT work (the Averkov class).
  * **P6-G3** collapses an ambiguity to its first candidate.
  * **P6-G4** caches a 429, turning one transient rate-limit into a permanent phantom miss.
  * **P6-G5** admits a citation candidate, which no extraction stage may do.
  * **P6-G6** opens the branch the P6 referee named (§4): a reference whose DOI is registered but
    whose title GROBID did not parse. With no title the first-author family and an EXACT year are
    the only discriminators left (decisions.yaml §15.15 reserves the +/-1 arm for pairs where title
    AND author match), and this row removes them, accepting the DOI on nothing.
  * **P6-G7** collapses `doi_title_contained` back into `doi_title_mismatch`, so a truncated parse
    and a genuinely wrong DOI become indistinguishable to P5's triage again.
  * **P6-M1** counts a mention per bounding BOX instead of per `<ref>` element — the F1 defect:
    a line-wrapped marker then counts twice, inflating `mention_count` and the most-cited table.
  * **P6-R1/R2/R3** weaken the three shared text rules in `admit/resolver.py` — the ratio, the
    surname, the year — each of which stage 6 depends on and each of which the phase requires to
    fail a test when mutated.
  * **P6-S1..S6** are the per-call-site rows for `normalize_doi`: at each site the guard is simply
    not applied (the call becomes its own argument).
"""
import argparse
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TESTS_P6 = ["qc/test_litkb_references.py"]
REFS = "pipeline/litkb/extract/references.py"
RESOLVER = "pipeline/litkb/admit/resolver.py"

#: `normalize_doi(x)` -> `(x)`: the canonicalisation simply does not happen at that call.
PASSTHROUGH = "({a0})"

IDS = ["P6-G1", "P6-G2", "P6-G3", "P6-G4", "P6-G5", "P6-G6", "P6-G7", "P6-M1",
       "P6-R1", "P6-R2", "P6-R3",
       "P6-S1", "P6-S2", "P6-S3", "P6-S4", "P6-S5", "P6-S6"]


def register(block, replace, site):
    """Append the P6 rows to the shared table. Called from `litkb_p2_mutations` at import."""
    block("P6-G1", REFS, "guard: p6 a reference with a DOI is decided by that DOI",
          "DOI-first: a reference with a DOI falls through to a title search (THE §14 P6 kill)",
          tests=TESTS_P6)
    block("P6-G2", REFS, "guard: p6 a reference DOI must resolve to the reference's own work",
          "a DOI that resolves to a different title is reported resolved", tests=TESTS_P6)
    block("P6-G3", REFS, "guard: p6 two accepted works are ambiguous, not a resolution",
          "two accepted works collapse to the first instead of reporting ambiguous", tests=TESTS_P6)
    block("P6-G4", REFS, "guard: p6 only a settled registry answer is cached",
          "a 429 or a dead connection is cached as if it were an answer", tests=TESTS_P6)
    replace("P6-G5", REFS, '"state": "new", "reason": res.reason', '"state": "admitted", "reason": res.reason',
            "a citation candidate is written admitted", tests=TESTS_P6)
    block("P6-G6", REFS, "guard: p6 a DOI with no parsed title is verified on author and year",
          "a DOI on a title-less reference is accepted on the DOI alone (the referee's §4 hole, "
          "opened wide)", tests=TESTS_P6)
    replace("P6-G7", REFS, 'kind = "doi_title_contained" if cont else "doi_title_mismatch"',
            'kind = "doi_title_mismatch"',
            "a truncated parse and a wrong DOI carry the same terminal reason again", tests=TESTS_P6)
    replace("P6-M1", REFS, '+ (1 if m["box_index"] == 0 else 0)', "+ 1",
            "a mention is counted per bounding box again, so a line-wrapped marker counts twice",
            tests=TESTS_P6)
    replace("P6-R1", RESOLVER, "RESOLVE_TITLE_RATIO = 0.85", "RESOLVE_TITLE_RATIO = 0.60",
            "the title rule is lowered from 0.85 to 0.60", tests=TESTS_P6)
    replace("P6-R2", RESOLVER, "if not family_matches(cand.get(\"family\"), surname):",
            "if False:", "the first-author surname is no longer checked", tests=TESTS_P6)
    block("P6-R3", RESOLVER, "guard: year rule (decisions.yaml §15.15)",
          "the +/-1 year rule is dropped (any year within the other two rules is accepted)",
          tests=TESTS_P6)
    for n, (mid, fn) in enumerate([
            ("P6-S1", "parse_reference"), ("P6-S2", "resolve_reference"), ("P6-S3", "resolve_by_doi"),
            ("P6-S4", "resolve_by_search"), ("P6-S5", "corpus_index"),
            ("P6-S6", "crossref_reference_list")], 1):
        site(mid, f"litkb/extract/references.py::{fn}::normalize_doi", PASSTHROUGH,
             f"{fn}: the DOI is not normalised at this call site", tests=TESTS_P6)


def _p2():
    spec = importlib.util.spec_from_file_location("litkb_p2_mutations", HERE / "litkb_p2_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("litkb_p2_mutations", mod)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser(description="show each litkb P6 guard fire")
    ap.add_argument("--only", help="comma-separated P6 mutation ids (default: all P6 rows)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    chosen = [s.strip() for s in a.only.split(",")] if a.only else IDS
    return _p2().main(["--only", ",".join(chosen)])


if __name__ == "__main__":
    main()
