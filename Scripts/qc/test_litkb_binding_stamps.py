"""Check 3's title region vs the arXiv/bioRxiv margin stamp (register E25, Kam's ruling 2026-09-21).

THE MECHANISM, measured on the two real refused files (not assumed): arXiv prints its identifier in a
ROTATED strip down the left margin of page 1, and `pdftotext -layout` emits rotated text in the y-band it
occupies — the title's band. So page 1 line 0 of both papers is ONE line carrying the stamp AND the title:

    arXiv:2007.01434v1 [cs.LG] 2 Jul 2020 In Search of Lost Domain Generalization     ratio 0.6842
    arXiv:1909.10155v2 [cs.LG] 31 Jan 2020 Verified Uncertainty Calibration           ratio 0.6337

Both are below BIND_RATIO, so both correct papers were quarantined (Reports/LITKB_HELD_QUEUE_2026-09-15.md
lines 110-111). The report's account of 291 — "check 3's title-region match picked the line
'https://pypi.org/project/uncertainty-calibration', ratio 0.641" — is true but is only the window that WON;
the title's own line was there, at 0.6337, and losing the URL line would still not have bound it. A rule
that DROPPED the offending line would have dropped the title with it. The stamp has to come off the FRONT
of the title's line, which is what `binding.title_text` does.

The fixtures are the first page as `binding.first_page_text` itself reads it (`pdftotext -f 1 -l 1 -layout`),
stored LF-only under qc/testdata/litkb_binding_stamps/; the quarantined PDFs are never opened by this module
and never moved. The third fixture, Mahoney 2023 (arXiv 2303.07334, already in the corpus, stamped the same
way), is the WRONG-PAPER control: the strip must not make the gate accept a page that does not print the
registry title.

  what                                                               test
  the two correct papers were refused, ratio < 0.85, before the fix   test_the_stamped_title_line_was_refused_before_the_strip
  and they bind now, with the author near the title                   test_the_stamped_title_line_binds_with_the_strip
  a page of ANOTHER paper is still refused                            test_a_different_paper_is_still_refused_with_the_strip
  a URL inside a real title is not touched                           test_a_url_inside_a_title_is_not_stripped
  a line that is ONLY a URL or a DOI carries no title                test_a_whole_line_url_or_doi_is_not_a_title
  every line keeps its index, so the region bound is unchanged        test_the_strip_does_not_move_a_line_into_the_title_region

Mutated by qc/instruments/litkb_p2_mutations.py rows E25a (the strip in bind), E25b (the strip in
best_window) and E25c (the whole-line URL rule made permissive).
"""
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
FIX = SCRIPTS / "qc" / "testdata" / "litkb_binding_stamps"

#: fixture, registry title, registry first author, the ratio the gate measured BEFORE the strip
#: (measured 2026-09-21 by running binding.bind on the quarantined PDFs; 0.6842 is the number
#: LITKB_HELD_QUEUE_2026-09-15.md:110 records for tracker 151)
REFUSED = [
    ("gulrajani_2020_p1.txt", "In Search of Lost Domain Generalization", "Gulrajani", 0.6842),
    ("kumar_2019_p1.txt", "Verified Uncertainty Calibration", "Kumar", 0.6410),
]

CONTROL = "mahoney_2023_p1.txt"
CONTROL_TITLE = "Assessing the performance of spatial cross-validation approaches for models of " \
                "spatially structured data"


def _text(name):
    t = (FIX / name).read_text(encoding="utf-8")
    assert "\r" not in t, f"{name} must be stored LF-only"
    return t


def _no_strip(monkeypatch, binding):
    """The gate as it stood before this fix: the scored text is the printed line."""
    monkeypatch.setattr(binding, "title_text", lambda ln: " ".join((ln or "").split()))


# ── (a) the known-bad: without the strip, both correct papers are refused ─────────────────────────
@pytest.mark.parametrize("name,title,author,ratio", REFUSED, ids=[r[0].split("_")[0] for r in REFUSED])
def test_the_stamped_title_line_was_refused_before_the_strip(name, title, author, ratio, monkeypatch):
    from litkb.admit import binding

    _no_strip(monkeypatch, binding)
    b = binding.bind(None, title, author, page_text=_text(name), info={})
    assert b["verdict"] == "binding-failed", b
    assert b["ratio"] < binding.BIND_RATIO and b["ratio"] == pytest.approx(ratio, abs=5e-4), b
    # the page DOES print the title and DOES carry the author: only the title-window match failed
    assert b["author_found"], b
    assert title.lower() in _text(name).lower(), "the fixture must print the registry title"


# ── (b) with the fix, both bind, and on the author-near rule, unchanged ───────────────────────────
@pytest.mark.parametrize("name,title,author,_ratio", REFUSED, ids=[r[0].split("_")[0] for r in REFUSED])
def test_the_stamped_title_line_binds_with_the_strip(name, title, author, _ratio):
    from litkb.admit import binding

    b = binding.bind(None, title, author, page_text=_text(name), info={})
    assert b["verdict"] == "bound", b
    assert b["ratio"] >= binding.BIND_RATIO and b["author_near_title"] and b["source"] == "page1", b
    assert b["best_any_ratio"] >= binding.BIND_RATIO, b
    # the evidence keeps BOTH the string the ratio was measured on and the line the page prints
    assert b["matched"] == title, b
    assert b["matched_printed"].startswith("arXiv:") and b["matched_printed"].endswith(title), b


# ── (c) the control: the strip must not make the gate permissive ──────────────────────────────────
@pytest.mark.parametrize("title,author", [(t, a) for _n, t, a, _r in REFUSED])
def test_a_different_paper_is_still_refused_with_the_strip(title, author):
    from litkb.admit import binding

    b = binding.bind(None, title, author, page_text=_text(CONTROL), info={})
    assert b["verdict"] == "binding-failed", b
    assert b["ratio"] < binding.BIND_RATIO and b["best_any_ratio"] < binding.BIND_RATIO, b


def test_the_control_page_binds_its_own_paper(monkeypatch):
    """The control is refused because it is another paper, not because its page cannot bind: the same
    stamped page binds its OWN title, and did not before the strip."""
    from litkb.admit import binding

    b = binding.bind(None, CONTROL_TITLE, "Mahoney", page_text=_text(CONTROL), info={})
    assert b["verdict"] == "bound" and b["source"] == "page1" and b["author_near_title"], b
    with monkeypatch.context() as m:
        _no_strip(m, binding)
        before = binding.bind(None, CONTROL_TITLE, "Mahoney", page_text=_text(CONTROL), info={})
    assert before["verdict"] == "binding-failed" and before["ratio"] < binding.BIND_RATIO, before


# ── (d) a URL inside a real title is title text ───────────────────────────────────────────────────
def test_a_url_inside_a_title_is_not_stripped():
    from litkb.admit import binding

    title = "Introducing www.treecanopy.org as a public canopy registry"
    assert binding.title_text(title) == title
    page = "\n".join([title, "Jane Q. Tester and A. Coauthor", "Abstract", "Body text follows."])
    b = binding.bind(None, title, "Tester", page_text=page, info={})
    assert b["verdict"] == "bound" and b["ratio"] == pytest.approx(1.0) and b["matched"] == title, b
    assert "matched_printed" not in b, b


def test_a_whole_line_url_or_doi_is_not_a_title():
    from litkb.admit import binding

    for line in ("https://pypi.org/project/uncertainty-calibration",
                 "http://example.org/a/b?c=d",
                 "www.treecanopy.org/data",
                 "https://doi.org/10.1101/2020.05.03.074922",
                 "doi: 10.1016/j.rse.2019.111310",
                 "10.1016/j.rse.2019.111310"):
        assert binding.title_text(line) == "", line


@pytest.mark.parametrize("line,left", [
    # the two real lines, and the bare stamp forms the same margin prints
    ("arXiv:2007.01434v1 [cs.LG] 2 Jul 2020 In Search of Lost Domain Generalization",
     "In Search of Lost Domain Generalization"),
    ("arXiv:1909.10155v2 [cs.LG] 31 Jan 2020 Verified Uncertainty Calibration",
     "Verified Uncertainty Calibration"),
    ("arXiv:2007.01434 A Title Without A Version", "A Title Without A Version"),
    ("arXiv:math/0501001v3 [math.AG] 4 Feb 2005 An Old Style Identifier", "An Old Style Identifier"),
    ("arXiv:2007.01434v1 [cs.LG] 2 Jul 2020", ""),
    ("bioRxiv preprint doi: https://doi.org/10.1101/2020.05.03.074922; this version posted May 4, 2020. "
     "A Preprint About Crowns", "A Preprint About Crowns"),
    ("medRxiv preprint doi: https://doi.org/10.1101/2021.01.02.20248784; this version posted January 4, 2021.",
     ""),
    # NOT a stamp: left alone
    ("Archival Practice for arXiv: Ten Years On", "Archival Practice for arXiv: Ten Years On"),
    ("A Title With A Version v2 In It", "A Title With A Version v2 In It"),
])
def test_title_text_strips_only_the_stamp(line, left):
    from litkb.admit import binding

    assert binding.title_text(line) == left


# ── the non-permissiveness the fix rests on: no line moves ────────────────────────────────────────
def test_the_strip_does_not_move_a_line_into_the_title_region():
    from litkb.admit import binding

    title = "A Title Printed Far Down The Page"
    stamped = f"arXiv:2007.01434v1 [cs.LG] 2 Jul 2020 {title}"
    filler = ["https://example.org/noise"] * (binding.TITLE_REGION_LINES + 2)
    b = binding.bind(None, title, "Tester", page_text="\n".join([*filler, stamped, "Tester and A. Coauthor"]),
                     info={})
    assert b["verdict"] == "binding-failed", b
    assert "outside the title region" in " ".join(b.get("refused_windows", {})), b
    # the same line one row above the bound is admissible: the bound is what refused it, not the strip
    near_top = "\n".join([*filler[:binding.TITLE_REGION_LINES - 1], stamped, "Tester and A. Coauthor"])
    assert binding.bind(None, title, "Tester", page_text=near_top, info={})["verdict"] == "bound"


def test_scored_lines_keeps_the_line_count_and_order():
    from litkb.admit import binding

    for name in [n for n, *_ in REFUSED] + [CONTROL]:
        lines = binding.page_lines(_text(name))
        scored = binding.scored_lines(lines)
        assert len(scored) == len(lines), name
        # cleaning only ever removes characters from a line
        assert all(len(s) <= len(ln) for s, ln in zip(scored, lines)), name
        assert all(s == "" or s in ln for s, ln in zip(scored, lines)), name
