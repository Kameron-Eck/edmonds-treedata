"""`confirm_s2_candidate` (referee task 3, 2026-09-18): the missing-vs-contradicted author
asymmetry, and the 12-case pin from the independent referee's re-score.

No database, no network: every Crossref body here is either the cached verbatim body in
`qc/fixtures/litkb_confirm_s2_task3.json` (the referee's fixture — real `/works/{doi}` responses,
copied whole so `_year_from`'s `created` fallback and every other field `parse_crossref` reads
survive) or a synthetic record built for the mutation kill in the second half of this file, named
as such.

THE FIXTURE'S THREE GROUPS (all 12 cases pinned permanently):
  * `book_review_planted` (3) — Wadsworth/Getis/Serra: a journal's review of the cited book, which
    must stay REFUSED under its measured reason (`type_mismatch` or `review_record`).
  * `lost_genuine` (2) — Abercrombie_2016::b16 (Swain 1978) and Burnicki_2011::b12 (Chrisman
    1989): a genuine match whose Crossref record carries no author. Before this fix both were
    refused `crossref_no_author` (the fixture's own `observed_verdict`/`observed_reason` — the
    MEASURED "before"); after it both must be CONFIRMED.
  * `must_not_link_real_7` (7) — 3 more book reviews (still refused) plus 4 sibling editions
    (still `ambiguous`/`edition_mismatch`, never refused: a sibling edition is a correct call,
    not a defect to fix).

THE MUTATION KILL (P7-C7/P7-C8, `qc/instruments/litkb_s2_mutations.py`): P7-C7 reverts the
asymmetry (the 2 lost-genuine cases refuse again); P7-C8 removes the requirement that an
authorless record's YEAR still independently clear, which
`test_an_authorless_wrong_year_candidate_is_still_refused` below is written to catch (title ratio
is untouched and out of scope — `test_an_authorless_wrong_title_candidate_is_still_refused` pins
that it was never a hole).
"""
import json
from pathlib import Path

import pytest

from litkb.admit import resolver as RES

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "litkb_confirm_s2_task3.json")
                     .read_text(encoding="utf-8"))


class _StubClient:
    """Always answers the one cached `/works/{doi}` body it was built with -- confirm_s2_candidate
    asks exactly one Crossref URL per call, so nothing is lost by not routing on it."""

    def __init__(self, body):
        self._body = body

    def get(self, url, accept="application/json", timeout=60, **kw):
        return 200, {}, json.dumps(self._body).encode("utf-8")


def _confirm(case, doi_field):
    client = _StubClient(case["cached_crossref_body"])
    return RES.confirm_s2_candidate({"doi": case[doi_field]}, case["reference_input"], client, None)


# ── book_review_planted (3): must stay refused, by the fixture's own measured reason ───────────

@pytest.mark.parametrize("case", FIXTURE["book_review_planted"], ids=lambda c: c["label"])
def test_book_review_planted_cases_are_refused_by_their_measured_reason(case):
    verdict, reason, _rec = _confirm(case, "candidate_doi")
    assert verdict == "refused", (case["label"], verdict, reason)
    want = case["observed_reason"].split(" (", 1)[0]
    assert reason.startswith(want + " ("), (case["label"], reason)


# ── lost_genuine (2): THE FIX. Refused before (fixture's observed_*), confirmed after ──────────

@pytest.mark.parametrize("case", FIXTURE["lost_genuine"], ids=lambda c: c["ref_id"])
def test_lost_genuine_authorless_records_now_admit(case):
    # The measured "before": the referee's own fixture records what the unfixed resolver did.
    assert case["observed_verdict"] == "refused"
    assert case["observed_reason"].startswith("crossref_no_author (")
    # The fix: the same record, same reference, through the current resolver.
    verdict, reason, rec = _confirm(case, "gold_doi")
    assert verdict == "confirmed", (case["ref_id"], verdict, reason)
    assert reason.startswith("crossref_confirmed ("), reason
    assert "crossref carries no author" in reason, reason
    assert rec is not None and not (rec.get("first_author") or "")


# ── must_not_link_real_7 (7): 3 refused book reviews, 4 ambiguous sibling editions ─────────────

@pytest.mark.parametrize("case", [c for c in FIXTURE["must_not_link_real_7"] if c["kind"] == "book_review"],
                        ids=lambda c: c["ref_id"])
def test_the_three_real_book_reviews_in_the_must_not_link_set_stay_refused(case):
    verdict, reason, _rec = _confirm(case, "bad_doi")
    assert verdict == "refused", (case["ref_id"], verdict, reason)
    assert reason.startswith("review_record ("), reason


@pytest.mark.parametrize("case", [c for c in FIXTURE["must_not_link_real_7"] if c["kind"] == "edition"],
                        ids=lambda c: c["ref_id"])
def test_the_four_sibling_editions_stay_ambiguous_not_refused_and_not_confirmed(case):
    """The referee's explicit caveat: these 4 are CORRECTLY ambiguous. Not a defect, never fixed."""
    verdict, reason, _rec = _confirm(case, "bad_doi")
    assert verdict == "ambiguous", (case["ref_id"], verdict, reason)
    assert reason.startswith("edition_mismatch ("), reason


def test_the_fixture_groups_are_the_twelve_case_set_the_task_pins():
    assert len(FIXTURE["book_review_planted"]) == 3
    assert len(FIXTURE["lost_genuine"]) == 2
    assert len(FIXTURE["must_not_link_real_7"]) == 7
    editions = [c for c in FIXTURE["must_not_link_real_7"] if c["kind"] == "edition"]
    reviews = [c for c in FIXTURE["must_not_link_real_7"] if c["kind"] == "book_review"]
    assert len(editions) == 4 and len(reviews) == 3


# ── synthetic cases for the mutation kill (P7-C7/P7-C8) — NOT from the corpus, named as such ────
#
# `family_name("")` folds to `""`, and `_year_int` on a record with no date fields at all folds to
# `None` -- both real shapes an authorless Crossref record can take, constructed here because the
# fixture's two real authorless cases both happen to have an exact year and a near-exact title, so
# neither exercises the guards that stand between "uninformative on authorship" and "admitted on
# nothing at all". CLAUDE.md 3.4c: these are unit-test constructions for a code guard, not a
# design being validated against itself -- the guard itself is the asymmetry fixed in
# `resolver.confirm_s2_candidate`, read at :file:`pipeline/litkb/admit/resolver.py`, not re-derived
# here.

_AUTHORLESS_REF = {"title": "A dual-polarimetric canopy index", "first_author": "Wang", "year": "2015",
                   "journal": "Remote Sensing of Environment", "publisher": "",
                   "authors": [{"family": "Wang"}], "raw": "L. Wang, A dual-polarimetric canopy index, 2015."}


def _authorless_client(title, year_parts):
    """A `crossref_record`-shaped stub: the {"message": {...}} envelope `parse_crossref` reads,
    with no `author` key at all -- the shape `crossref_record` sees for a genuinely authorless
    record (parse_crossref's `authors=[]`, `first_author=""`)."""
    msg = {"type": "journal-article", "title": [title], "subtitle": [],
           "container-title": ["Remote Sensing of Environment"]}
    if year_parts is not None:
        msg["issued"] = {"date-parts": [year_parts]}
    return _StubClient({"message": msg})


def test_an_authorless_exact_match_confirms():
    """The control the two kills below are read against."""
    verdict, reason, _rec = RES.confirm_s2_candidate(
        {"doi": "10.9/x"}, _AUTHORLESS_REF, _authorless_client(_AUTHORLESS_REF["title"], [2015]), None)
    assert verdict == "confirmed", reason


def test_an_authorless_wrong_year_candidate_is_still_refused():
    """THE KILL for P7-C8: title ratio clears (same title), the record carries no author, and the
    year is 3 out. Dropping the no-author refusal must not have dropped the year requirement with
    it -- if it had, this would confirm."""
    verdict, reason, _rec = RES.confirm_s2_candidate(
        {"doi": "10.9/x"}, _AUTHORLESS_REF, _authorless_client(_AUTHORLESS_REF["title"], [2018]), None)
    assert verdict == "refused", reason
    assert reason.startswith("crossref_year_mismatch ("), reason


def test_an_authorless_record_with_no_year_at_all_is_refused_as_year_unknown():
    """The other half of "year independently clear": a record with no date fields parses to
    `year=None`, and the missing-vs-contradicted asymmetry is about a missing AUTHOR, not a
    missing year -- `_year_int(None)` is unknown, not uninformative-and-forgiven."""
    verdict, reason, _rec = RES.confirm_s2_candidate(
        {"doi": "10.9/x"}, _AUTHORLESS_REF, _authorless_client(_AUTHORLESS_REF["title"], None), None)
    assert verdict == "refused", reason
    assert reason.startswith("crossref_year_unknown ("), reason


def test_an_authorless_wrong_title_candidate_is_still_refused():
    """The title-ratio rung is untouched and out of scope for this fix; pinned here so a future
    change cannot quietly fold it into the authorless branch."""
    verdict, reason, _rec = RES.confirm_s2_candidate(
        {"doi": "10.9/x"}, _AUTHORLESS_REF,
        _authorless_client("A completely different paper about soil moisture", [2015]), None)
    assert verdict == "refused", reason
    assert reason.startswith("crossref_title_ratio ("), reason
