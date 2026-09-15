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
S2 = "pipeline/litkb/admit/s2.py"
PASSTHROUGH = "({a0})"

IDS = ["P7-G1", "P7-G2", "P7-G3", "P7-G4", "P7-G5", "P7-S1", "P7-S2"]


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
    site("P7-S1", f"litkb/admit/s2.py::paper_id_for::normalize_doi", PASSTHROUGH,
         "paper_id_for: the DOI is not normalised, so one work takes two batch identifiers",
         tests=TESTS_S2)
    site("P7-S2", f"litkb/admit/s2.py::to_candidate::normalize_doi", PASSTHROUGH,
         "to_candidate: a candidate's DOI is returned as the registry spelled it", tests=TESTS_S2)


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
