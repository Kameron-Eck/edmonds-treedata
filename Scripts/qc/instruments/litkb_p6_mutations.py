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
  * **P6-G8/P6-G9 are Item 2's rows** (Crossref SEARCH as a second proposer, 2026-09-19,
    `resolve_by_raw_search`, `Reports/LITKB_REFMATCHER_2026-09-15.md` §9). G8 deletes the
    confirmation call and accepts the raw-string search's top hit directly — a real book review
    (the fixture cases in `qc/test_litkb_crossref_raw_search.py`) then resolves instead of being
    refused, which is exactly the class the registry-confirmation gate exists to catch. G9 removes
    the gate that reaches this leg only for the title/author-blind class, so it reverts to the old
    immediate `no_title_or_author` bail — the routing test in the same file, which expects the raw
    string to reach Crossref at all, then fails.
  * **P6-M1** counts a mention per bounding BOX instead of per `<ref>` element — the F1 defect:
    a line-wrapped marker then counts twice, inflating `mention_count` and the most-cited table.
  * **P6-R1/R2/R3** weaken the three shared text rules in `admit/resolver.py` — the ratio, the
    surname, the year — each of which stage 6 depends on and each of which the phase requires to
    fail a test when mutated.
  * **P6-S1..S6** are the per-call-site rows for `normalize_doi`: at each site the guard is simply
    not applied (the call becomes its own argument).

And the INGEST rows, P6-I1..I4 (`litkb/extract/references_ingest.py`, migration 0020). Stage 6 is
still DB-free; the loader that carries its output into the database is the stage's, so its rows live
here and run `qc/test_litkb_references_ingest.py` against `litkb_test`:

  * **P6-I1** stops the loader REFUSING a stem litkb does not hold and has it substitute some other
    paper's file instead. `"references".file_id` is NOT NULL, and filling a NOT NULL with a file
    that is not the paper's is how a whole reference list ends up filed under the wrong work.
    MEASURED: 1 of the 18 citing stems (Chrisman_1982) is exactly that case on the live `litkb`.
  * **P6-I2** is P6-M1's defect one layer down: every bounding BOX becomes a citation_mention row
    again, so a line-wrapped marker is stored twice and the stored counts stop matching the
    `mention_count` stage 6 computed.
  * **P6-I3** is the §14 P5 kill re-expressed on stage 6: the references are committed BEFORE the
    rest of the paper, so a kill leaves a run with half a citation graph under it.
  * **P6-I4** removes the idempotence check, so a second load writes a second set of rows.

And the S4 DRIVER rows, P6-D1..D7 (S4 run 3, builder D1): the file-keyed stage-6 driver
(`qc/instruments/litkb_references_stage.py`) and the one predicate it shares with the REPORTED
counters (`litkb/extract/references_coverage.py`). They run `qc/test_litkb_references_stage.py`
against `LITKB_TEST_DB`:

  * **P6-D1** breaks the owed-file filter itself: every file with stage-5 blocks counts as owing
    stage 6, so `files_without_reference_stage` never falls and the driver re-selects finished
    files (THE known-bad of the S4 brief).
  * **P6-D2** drops `status = 'ok'` from "the stage ran": a killed run's `failed` carcass then
    counts as done, and the file is never retried.
  * **P6-D3** drops the params hash from the key: a run made under OLDER resolution thresholds
    counts as the current one.
  * **P6-D4** gives the anchor rate the WRONG denominator (every reference), the headline R4's kill
    line says must fail review.
  * **P6-D5** posts bytes that no longer hash to the file row, and caches the TEI under that row's sha.
  * **P6-D6** stops GROBID at the end of a batch whether or not this driver started it.
  * **P6-D7** lets a second driver run beside a detached one on the same database.
  * **P6-D8** removes the rel-path citing-stem override: two files sharing a stem share one list.
  * **P6-D9** drops `f.status = 'active'`: a quarantined/superseded version with blocks is owed.
  * **P6-D10** starts a GROBID whose unit systemd says is running (a busy service missed the probe).
  * **P6-D11** takes ownership of a GROBID on any successful launch, "already alive" included.

THE HARNESS SCORES `rc != 0 and failed > 0` AS FIRED, so a mutant that makes the code ERROR (invalid
SQL, a NameError) "fires" without showing the guard matters. Every P6-D row's failures must be
read and be AssertionErrors (or a DID-NOT-RAISE) — the first P6-D3 was not (see its row).
"""
import argparse
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TESTS_P6 = ["qc/test_litkb_references.py"]
#: Item 2's rows (G8/G9) also need the routing/fixture pins in their own file, so their `tests=`
#: EXTENDS TESTS_P6 rather than replacing it (the same hazard the P7-C7/P7-C8 rows in
#: `litkb_s2_mutations.py` name for their own dedicated file).
TESTS_P6_RAWSEARCH = [*TESTS_P6, "qc/test_litkb_crossref_raw_search.py"]
#: The ingest rows need a database; their set is the one that has one.
TESTS_P6I = ["qc/test_litkb_references_ingest.py"]
#: The S4 driver rows (P6-D*): the driver's own file, which seeds its own database rows.
TESTS_P6D = ["qc/test_litkb_references_stage.py"]
REFS = "pipeline/litkb/extract/references.py"
REFING = "pipeline/litkb/extract/references_ingest.py"
REFCOV = "pipeline/litkb/extract/references_coverage.py"
REFDRV = "qc/instruments/litkb_references_stage.py"
RESOLVER = "pipeline/litkb/admit/resolver.py"

#: `normalize_doi(x)` -> `(x)`: the canonicalisation simply does not happen at that call.
PASSTHROUGH = "({a0})"

IDS = ["P6-G1", "P6-G2", "P6-G3", "P6-G4", "P6-G5", "P6-G6", "P6-G7", "P6-G8", "P6-G9", "P6-M1",
       "P6-R1", "P6-R2", "P6-R3",
       "P6-S1", "P6-S2", "P6-S3", "P6-S4", "P6-S5", "P6-S6", "P6-S7",
       "P6-I1", "P6-I2", "P6-I3", "P6-I4",
       "P6-D1", "P6-D2", "P6-D3", "P6-D4", "P6-D5", "P6-D6", "P6-D7",
       "P6-D8", "P6-D9", "P6-D10", "P6-D11"]


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
    replace("P6-G8", REFS, "verdict, why, rec = confirm_s2_candidate(cand, ref, client, pacer)",
            'verdict, why, rec = "confirmed", "accepted_without_confirmation (mutated)", None',
            "the raw-string search's top hit is accepted directly, without the registry-"
            "confirmation gate -- a real book review then resolves instead of being refused",
            tests=TESTS_P6_RAWSEARCH)
    replace("P6-G9", REFS,
            "    if not title or not surname:\n"
            "        return resolve_by_raw_search(ref, client, pacer, breaker)\n",
            '    if not title or not surname:\n'
            '        return Resolution("unresolved", reason="no_title_or_author (nothing to search on)")\n',
            "the title/author-blind class no longer reaches the Crossref raw-string proposer at "
            "all -- back to the old immediate bail", tests=TESTS_P6_RAWSEARCH)
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
    # Item 2's own call site (2026-09-19): a separate row, not folded into the loop above, because
    # its test needs TESTS_P6_RAWSEARCH -- test_litkb_references.py never reaches this function.
    site("P6-S7", "litkb/extract/references.py::resolve_by_raw_search::normalize_doi", PASSTHROUGH,
         "resolve_by_raw_search: the DOI is not normalised at this call site", tests=TESTS_P6_RAWSEARCH)
    # ── the stage-6 ingest (migration 0020). Appended last: see the docstring. ────────────
    replace("P6-I1", REFING,
            '    if hit is None or hit.get("file_id") is None:\n'
            "        return None, _unheld(stem, hit)\n",
            '    if hit is None or hit.get("file_id") is None:\n'
            '        hit = next(h for h in index.values() if h.get("file_id"))\n',
            "a stem litkb does not hold is given ANOTHER paper's file instead of being refused, so "
            "a whole reference list is filed under the wrong work", tests=TESTS_P6I)
    replace("P6-I2", REFING, '        if m.get("box_index") == 0 or not out:', "        if True:",
            "a citation_mention is written per bounding BOX again, so a line-wrapped marker is "
            "stored twice and the stored counts stop matching stage 6's own", tests=TESTS_P6I)
    replace("P6-I3", REFING,
            "        if _after_references is not None:\n            _after_references(conn, run_id)\n",
            "        conn.commit()\n        if _after_references is not None:\n"
            "            _after_references(conn, run_id)\n",
            "THE P5 KILL on stage 6: the references are committed outside the paper's transaction, "
            "so a kill leaves a run with half a citation graph under it", tests=TESTS_P6I)
    replace("P6-I4", REFING, '    if existing and status == "ok":', "    if False:",
            "the idempotence check removed: a second load of the same paper at the same pipeline "
            "version writes a second set of rows", tests=TESTS_P6I)
    # ── the S4 file-keyed driver and its counters (S4 run 3, builder D1) ─────────────────
    replace("P6-D1", REFCOV, '_OWES_STAGE6 = f"NOT EXISTS ({_OK_STAGE6_AT_KEY})"', '_OWES_STAGE6 = "TRUE"',
            "the owed-file filter broken: every file with stage-5 blocks counts as owing stage 6, so "
            "files_without_reference_stage never falls and finished files are re-selected",
            tests=TESTS_P6D)
    replace("P6-D2", REFCOV, "\"AND r6.status = 'ok'\")", "\"AND TRUE\")",
            "a killed stage-6 run's failed carcass counts as the stage having run", tests=TESTS_P6D)
    # The condition is DROPPED, not replaced by a placeholder test: the first form of this row
    # ("%(k_params_hash)s IS NOT NULL") was invalid SQL (psycopg IndeterminateDatatype on every
    # query), so its 11 "failures" were errors, not the guard's absence — the S4 run 3 auditor of
    # D1 scored it DID NOT FIRE. A mutant must answer WORSE, never fail to answer.
    replace("P6-D3", REFCOV, '"AND r6.params_hash = %(k_params_hash)s AND r6.pipeline_version',
            '"AND r6.pipeline_version',
            "the params hash dropped from the key: a run under older thresholds counts as current",
            tests=TESTS_P6D)
    replace("P6-D4", REFCOV, '"       count(*) FILTER (WHERE held_doi), "', '"       count(*), "',
            "the anchor rate's denominator becomes every reference (R4's kill line)", tests=TESTS_P6D)
    block("P6-D5", REFDRV, "guard: the stage-6 driver posts only the bytes its file row names",
          "bytes that no longer hash to the file row are posted and cached under the row's sha256",
          tests=TESTS_P6D)
    replace("P6-D6", REFDRV, "        if self.started_here and not self.stopped:",
            "        if not self.stopped:",
            "GROBID is stopped at the end of a batch even when another process started it",
            tests=TESTS_P6D)
    block("P6-D7", REFDRV, "guard: one stage-6 driver per database at a time",
          "a second stage-6 driver runs beside a detached one on the same database", tests=TESTS_P6D)
    # ── the S4 run 3 audit of D1: three guards the first campaign did not reach ───────────
    block("P6-D8", REFDRV, "guard: the citing stem names THIS file, never another file sharing the stem",
          "the rel-path override removed: two files sharing a stem get one reference list between "
          "them, filed under whichever file held_index saw first", tests=TESTS_P6D)
    replace("P6-D9", REFCOV, "\"f.status = 'active' AND cr.stage = %(stage5)s", "\"cr.stage = %(stage5)s",
            "a quarantined or superseded current file version with blocks is selected and counted",
            tests=TESTS_P6D)
    block("P6-D10", REFDRV, "guard: a running GROBID unit someone else started is waited for, never started",
          "a busy GROBID that misses the 5 s health probe is 'started' (grobid.sh restarts it under "
          "the worker that owns it)", tests=TESTS_P6D)
    replace("P6-D11", REFDRV, "        self.started_here = bool(ok and launched)",
            "        self.started_here = bool(ok)",
            "ownership taken whenever a launch succeeds, including 'already alive' (someone else's "
            "GROBID), so the driver stops it at the end", tests=TESTS_P6D)


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
