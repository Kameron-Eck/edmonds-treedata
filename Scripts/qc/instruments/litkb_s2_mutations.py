"""The Semantic Scholar leg (`litkb/admit/s2.py`): show every guard FIRE (CLAUDE.md 3.4c).

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_s2_mutations.py
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_s2_mutations.py --only P7-G1

Same machinery, same table, same reason as P6 (`litkb_p6_mutations.py`): the per-call-site rule
covers the PACKAGE, and `s2.py` adds two calls of `normalize_doi`, so these rows are appended to the
one shared table at import rather than kept in a second self-check that would see half the package.

WHAT EACH ROW IS FOR:

  * **P7-G1 is the kill this module was written around.** The batch response is aligned with the ids
    that were sent, positionally, with a null for an unknown one. Remove the length check and a short
    response is zipped anyway — every record after the gap attaches to the WRONG reference, and the
    resolutions that follow are confidently wrong rather than missing. This is the failure a batched
    client has that a per-item one cannot.
  * **P7-G2** caches an unsettled answer, so one 429 becomes a permanent phantom miss (P6-G4's twin,
    in the module that does its own caching).
  * **P7-G3** drops the schema version from the cache key, so a body written for an older parser is
    served to a newer one.
  * **P7-G4** empties the back-off ladder: a rate-limited stage then gives up on the first 429 with
    no wait and no retry, which is the behaviour the phase exists to remove.
  * **P7-G5** makes a failed batch indistinguishable from a batch full of misses, turning one
    transport error into a run-wide "not found" that costs no further request.
  * **P7-G6** sends a DOI-bearing reference to the batch endpoint. The DOI decides above this leg, so
    the answer is never read: the slot, and on a DOI-heavy corpus the whole request, is spent on
    nothing. It is also the per-call-site row for `normalize_doi` inside `batch_prefill`.
  * **P7-G7** removes the pacer, so requests go to a pool measured as exhausted back to back and the
    client manufactures the 429s its own ladder then waits out.
  * **P7-C1/C2/C3 are the "S2 proposes, Crossref confirms" rows**, the ones that close the
    book-review class. C1 and C2 delete the guard at each of the two doors — stage 6 and gate 0 —
    and the three real review cases resolve again. C3 removes only the review DETECTOR: the cases
    are still refused, by the weaker `crossref_author_mismatch`, so the row fires only because the
    tests pin the reason by name. That is deliberate — a kill for a class that is invisible in the
    outcome has to be asserted on the name.
  * **P7-C4/C5/C6 are the round-2 rows** (`Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md`). C4
    removes the name-independent half of the review detector, so a reviewer who shares the book
    author's surname is invisible again — the hole the referee planted and walked through. C5 and C6
    are the two halves of the arXiv refusal at the acquisition door: gate 0 returning no DOI for the
    `10.48550` form, and `fetch_one` refusing it whatever it is handed. They are separate rows on
    purpose — one test through `run_jobs` would let either half mask the other.
  * **P7-C7/P7-C8 are the task-3 rows** (missing-vs-contradicted author asymmetry, 2026-09-18). C7
    reverts the fix wholesale: a Crossref record with no author is refused `crossref_no_author`
    again, and the two lost-genuine cases (Swain 1978, Chrisman 1989) go back to being lost. C8
    narrows to the hazard the referee flagged rather than the fix itself: it removes only the
    requirement that an authorless record's YEAR still independently clear, so an authorless
    candidate confirms on title alone — caught by `test_an_authorless_wrong_year_candidate_is_still_refused`
    in `qc/test_litkb_confirm_asymmetry.py`, never by the corpus fixture (both its real authorless
    cases happen to carry an exact year).
  * **P7-S1/S2** are the per-call-site rows for `normalize_doi` inside `s2.py`: at each site the
    canonicalisation simply does not happen, so `DOI:10.1/A` and `DOI:10.1/a` become two identifiers
    and a candidate's DOI no longer matches the corpus index.
"""
import argparse
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TESTS_S2 = ["qc/test_litkb_s2.py"]
#: The confirmation rows reach two doors: stage 6 (`test_litkb_s2.py`) and gate 0, the acquisition
#: path (`test_litkb_annas.py`), so both suites run for them.
TESTS_CONFIRM = ["qc/test_litkb_s2.py", "qc/test_litkb_annas.py"]
#: P7-C7/P7-C8 (referee task 3, 2026-09-18): the missing-vs-contradicted author asymmetry. Its
#: dedicated pin -- the 12-case fixture plus the synthetic authorless kills -- lives in its own
#: file, so `tests=` here EXTENDS TESTS_CONFIRM rather than replacing it (the module docstring's
#: own hazard: `tests` replaces the default, it does not add to it).
TESTS_ASYMMETRY = [*TESTS_CONFIRM, "qc/test_litkb_confirm_asymmetry.py"]
S2 = "pipeline/litkb/admit/s2.py"
RESOLVER = "pipeline/litkb/admit/resolver.py"
REFS = "pipeline/litkb/extract/references.py"
ANNAS = "pipeline/litkb/acquire/annas.py"
PASSTHROUGH = "({a0})"

IDS = ["P7-G1", "P7-G2", "P7-G3", "P7-G4", "P7-G5", "P7-G6", "P7-G7", "P7-S1", "P7-S2",
       "P7-S3", "P7-C1", "P7-C2", "P7-C3", "P7-C4", "P7-C5", "P7-C6", "P7-C7", "P7-C8"]


def register(block, replace, site):
    """Append the P7 rows to the shared table. Called from `litkb_p2_mutations` at import."""
    block("P7-G1", S2, "guard: s2 a batch response must align with the ids it answers",
          "a short batch response is zipped anyway, attaching each record to the wrong id "
          "(THE batching kill)", tests=TESTS_S2)
    block("P7-G2", S2, "guard: s2 only a settled answer is cached",
          "a 429 or an error body is cached as if it were an answer", tests=TESTS_S2)
    replace("P7-G3", S2, 'raw = f"{CACHE_SCHEMA}|{method}|{url}|', 'raw = f"{method}|{url}|',
            "the cache key loses its schema version, so an entry written for an older parser is "
            "served to a newer one", tests=TESTS_S2)
    replace("P7-G4", S2, "BACKOFFS = (5.0, 10.0, 20.0, 40.0)", "BACKOFFS = ()",
            "the back-off ladder is emptied: the first 429 ends the request with no wait and no "
            "retry", tests=TESTS_S2)
    replace("P7-G5", S2, "    if not err:\n        s2.prefill.update(", "    if True:\n        s2.prefill.update(",
            "a FAILED batch fills the prefill with misses, so every reference in it is answered "
            "'not found' without ever being asked", tests=TESTS_S2)
    block("P7-G6", S2, "guard: s2 only a reference that can reach this leg takes a batch slot",
          "a DOI-bearing reference takes a batch slot, spending a shared-pool request on an answer "
          "nothing reads (the DOI decides above this leg)", tests=TESTS_S2,
          sites=["litkb/admit/s2.py::batch_prefill::normalize_doi"])
    block("P7-G7", S2, "guard: s2 a wire request is paced",
          "requests go to the exhausted shared pool back to back, so the client causes the 429s it "
          "then waits out", tests=TESTS_S2)
    site("P7-S1", f"litkb/admit/s2.py::paper_id_for::normalize_doi", PASSTHROUGH,
         "paper_id_for: the DOI is not normalised, so one work takes two batch identifiers",
         tests=TESTS_S2)
    site("P7-S2", f"litkb/admit/s2.py::to_candidate::normalize_doi", PASSTHROUGH,
         "to_candidate: a candidate's DOI is returned as the registry spelled it", tests=TESTS_S2)
    site("P7-S3", "litkb/admit/resolver.py::confirm_s2_candidate::normalize_doi", PASSTHROUGH,
         "confirm_s2_candidate: the DOI is confirmed under the registry's own spelling, so one work "
         "costs two Crossref lookups and two cache entries", tests=TESTS_CONFIRM)
    # Written at the P6 MERGE, not on either branch: s2.py's status-0 branch is a call site of the
    # redaction family, and that family came under the per-call-site rule (RD1-RD18) on the OTHER
    # side of this merge. Each branch's own `--sites` run was blind to it; the merged one is not.
    site("P7-RD19", "litkb/admit/s2.py::request::redact", PASSTHROUGH,
         "s2.request: the status-0 error embeds up to 120 raw response bytes, so a registered key "
         "echoed by the transport reaches the error string, the breaker's report and the log",
         tests=TESTS_S2)
    block("P7-C1", REFS, "guard: s2 proposes, crossref confirms",
          "stage 6 resolves on Semantic Scholar's own record again, so a JSTOR REVIEW of the cited "
          "book resolves as the book — the three measured cases come back", tests=TESTS_CONFIRM)
    block("P7-C2", RESOLVER, "guard: s2 proposes, crossref confirms",
          "gate 0, the acquisition door, resolves on Semantic Scholar's own record again and hands "
          "the fetcher the review's DOI", tests=TESTS_CONFIRM)
    replace("P7-C3", RESOLVER,
            '    if (rec.get("raw_type") or "") != "journal-article":',
            '    if True:',
            "the review detector alone is removed. The three cases are still REFUSED — by the "
            "weaker crossref_author_mismatch — so this row fires only because the tests pin the "
            "reason BY NAME. A test written against the outcome rather than the reason would go "
            "quiet here: the P7-G4 lesson again", tests=TESTS_CONFIRM)
    # ---- the round-2 rows (`Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md`) ----
    replace("P7-C4", RESOLVER,
            "    if ours and len(fams) == len(ours) + 1",
            "    if False and len(fams) == len(ours) + 1",
            "the NAME-INDEPENDENT half of the review detector is removed, leaving only the shape that "
            "requires the reviewer to be called something other than the book's author. A review "
            "whose reviewer shares that surname walks past it, and on a reference that parsed "
            "neither a journal nor a publisher nothing else can speak", tests=TESTS_S2)
    replace("P7-C5", RESOLVER,
            '            if cd.lower().startswith(ARXIV_DOI_PREFIX.lower()):',
            '            if False:',
            "gate 0 returns the 10.48550 DOI again, and its only caller hands what it returns "
            "straight to the fetcher: the archive is asked for a preprint arXiv serves itself",
            tests=TESTS_CONFIRM)
    block("P7-C6", ANNAS, "guard: gate 0 an arxiv DOI is record-only and is never fetched",
          "the fetcher's own refusal is removed, so the property holds only as far as gate 0's "
          "caller does — the belt behind the brace, mutated on its own", tests=TESTS_CONFIRM)
    # ---- the task-3 rows: missing-vs-contradicted author asymmetry (2026-09-18) ----
    replace("P7-C7", RESOLVER,
            '    if rec.get("first_author") or "":\n'
            '        if not family_matches(rec["first_author"], ref.get("first_author") or ""):\n'
            '            return "refused", (f"crossref_author_mismatch ({doi}; crossref first author "\n'
            '                               f"{rec[\'first_author\']!r} != reference {ref.get(\'first_author\')!r})"), rec\n'
            '    if cy is None or wy is None:',
            '    if not (rec.get("first_author") or ""):\n'
            '        return "refused", f"crossref_no_author ({doi}; crossref carries no author for this record)", rec\n'
            '    if not family_matches(rec["first_author"], ref.get("first_author") or ""):\n'
            '        return "refused", (f"crossref_author_mismatch ({doi}; crossref first author "\n'
            '                           f"{rec[\'first_author\']!r} != reference {ref.get(\'first_author\')!r})"), rec\n'
            '    if cy is None or wy is None:',
            "the missing-vs-contradicted asymmetry reverted whole: an authorless record refuses "
            "crossref_no_author again, and the two lost-genuine cases (Swain 1978, Chrisman 1989) "
            "are lost", tests=TESTS_ASYMMETRY)
    replace("P7-C8", RESOLVER,
            '    if rec.get("first_author") or "":\n'
            '        if not family_matches(rec["first_author"], ref.get("first_author") or ""):\n'
            '            return "refused", (f"crossref_author_mismatch ({doi}; crossref first author "\n'
            '                               f"{rec[\'first_author\']!r} != reference {ref.get(\'first_author\')!r})"), rec\n'
            '    if cy is None or wy is None:',
            '    if not (rec.get("first_author") or ""):\n'
            '        return "confirmed", f"crossref_confirmed_no_author_unchecked ({doi})", rec\n'
            '    if not family_matches(rec["first_author"], ref.get("first_author") or ""):\n'
            '        return "refused", (f"crossref_author_mismatch ({doi}; crossref first author "\n'
            '                           f"{rec[\'first_author\']!r} != reference {ref.get(\'first_author\')!r})"), rec\n'
            '    if cy is None or wy is None:',
            "an authorless record confirms the instant its author check is skipped, before the "
            "year gate runs at all: the year-independence half of the fix is gone, and a "
            "wrong-year authorless candidate is confirmed instead of crossref_year_mismatch",
            tests=TESTS_ASYMMETRY)


def _p2():
    spec = importlib.util.spec_from_file_location("litkb_p2_mutations", HERE / "litkb_p2_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("litkb_p2_mutations", mod)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser(description="show each litkb S2-leg guard fire")
    ap.add_argument("--only", help="comma-separated P7 mutation ids (default: all P7 rows)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    chosen = [s.strip() for s in a.only.split(",")] if a.only else IDS
    return _p2().main(["--only", ",".join(chosen)])


if __name__ == "__main__":
    main()
