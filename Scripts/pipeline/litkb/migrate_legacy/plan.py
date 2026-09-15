"""The case table: what a legacy row's identity is, and therefore how it is admitted.

Kam's P3 rule (decisions.yaml `litkb-p0-foundation`) is that identity comes from the registry record
and the verified file. The tracker's own title, authors, year and journal are a CLAIM. That leaves
exactly five cases, and this module is their one home:

  A  registry confirms the DOI and the claim AGREES      -> admit_registry(claimed=row, file if held)
  B  registry confirms the DOI, the claim DISAGREES,
     and a file is held                                   -> admit_registry(claimed=None, file) — the file's
                                                             binding IS the comparison (P2 judgement 2), and
                                                             every disagreeing field becomes a discrepancy
  C  registry confirms the DOI, the claim DISAGREES,
     and no file is held                                  -> HELD. Not admitted, not skipped: a DOI alone
                                                             proves only that SOME work exists (0013
                                                             `_check_registry`, "no claimed record to compare
                                                             with the registry and no bound file"). Admitting
                                                             it would bypass check 1
  D  no DOI, or the DOI does not confirm, but the title +
     first author + year resolve to one                   -> the resolved DOI, then A or B, plus a `doi`
                                                             discrepancy against what the row spelled
  E  nothing resolves                                     -> a MANUAL admission (a proposal, approved in
                                                             another session) when a file is held; otherwise
                                                             HELD as a proposal that needs a file

Nothing here decides a refusal on the database's behalf: a binding that fails or waits for OCR is the
database's verdict on the admission it is given, recorded as a refused admission, never pre-empted.
"""
from litkb.admit import registry as _registry
from litkb.admit.resolver import RESOLVE_TITLE_RATIO, family_matches, title_match_ratio
from litkb.migrate_legacy.export_shape import authors_line, norm_cell
from litkb.textnorm import normalize_doi

CASES = ("A", "B", "C", "D", "E")

#: the fields a legacy row claims that the registry also states, and where each is read from
COMPARED_FIELDS = ("title", "authors", "year", "journal", "doi")


def _norm_venue(s):
    return " ".join((s or "").lower().replace(".", " ").replace("&", "and").split())


def compare_row(rec, claimed):
    """The legacy row's claim against the registry record, field by field.

    -> {field: {"claimed", "registry", "ratio", "agrees", "differs"}}.

    TWO predicates, and conflating them was a real bug caught before the live load:

      * **`agrees`** is check-1 acceptability — `registry.compare_claimed`, which is
        `resolver.judge_candidate`, the SAME comparator admission uses, so this file never invents a
        second copy of the rule (CLAUDE.md 3.3). It decides the ADMISSION SHAPE.
      * **`differs`** is plain normalised inequality. It decides what is RECORDED. Kam's words are
        "every tracker or manifest field that disagrees with the registry is kept as a flagged
        discrepancy" — every field that disagrees, not every field check 1 rejects. A title accepted at
        ratio 0.92, a year accepted at ±1, an abbreviated venue: each prints differently in the export
        from what the tracker says today, so each needs a record explaining the difference, even though
        admission was right to accept it.
    """
    cmp_ = _registry.compare_claimed(rec, claimed)
    ratio, author_ok = cmp_["title_ratio"], bool(cmp_["author_match"])
    reg_year, claimed_year = rec.get("year"), claimed.get("year")
    try:
        claimed_year_i = int(str(claimed_year).strip()) if str(claimed_year or "").strip() else None
    except ValueError:
        claimed_year_i = None
    # decisions.yaml §15.15, as P2 implements it: ±1 only when the title AND first author both match
    year_agrees = (claimed_year_i is not None and reg_year is not None
                   and (claimed_year_i == reg_year
                        or (abs(claimed_year_i - reg_year) == 1 and ratio >= RESOLVE_TITLE_RATIO and author_ok)))
    venue_ratio = title_match_ratio(claimed.get("venue") or "", rec.get("venue") or "")
    reg_authors = authors_line(rec.get("authors"))
    out = {
        "title": {"claimed": claimed.get("title"), "registry": rec.get("title"), "ratio": ratio,
                  "agrees": ratio >= RESOLVE_TITLE_RATIO,
                  "differs": norm_cell(claimed.get("title")) != norm_cell(rec.get("title"))},
        # the registry value recorded is the line the EXPORT will print, so the diff gate can match a
        # discrepancy to the cell it explains. The registry's WHOLE author list goes in the detail: the
        # commonest real disagreement here is a record that split a name the other way round ("Hao Qin" as
        # family Hao), which the first author alone does not show. That changes no rule — `agrees` is still
        # the resolver's `family_matches`, the comparator admission uses.
        "authors": {"claimed": claimed.get("authors"), "registry": reg_authors, "ratio": None,
                    "agrees": author_ok,
                    "differs": norm_cell(claimed.get("authors")) != norm_cell(reg_authors),
                    "detail": {"registry_first_author": rec.get("first_author"),
                               "registry_authors": [
                                   " ".join(x for x in ((a or {}).get("given"), (a or {}).get("family")) if x)
                                   for a in (rec.get("authors") or []) if isinstance(a, dict)][:12]}},
        "year": {"claimed": claimed_year, "registry": reg_year, "ratio": None, "agrees": year_agrees,
                 "differs": norm_cell(claimed_year) != norm_cell(reg_year)},
        "journal": {"claimed": claimed.get("venue"), "registry": rec.get("venue"), "ratio": round(venue_ratio, 4),
                    # a blank claim is no claim, so nothing disagrees with it
                    "agrees": (not (claimed.get("venue") or "").strip()
                               or _norm_venue(claimed.get("venue")) == _norm_venue(rec.get("venue"))
                               or venue_ratio >= RESOLVE_TITLE_RATIO),
                    "differs": (bool((claimed.get("venue") or "").strip())
                                and norm_cell(claimed.get("venue")) != norm_cell(rec.get("venue")))},
    }
    for f in out.values():
        f.setdefault("detail", {})
        f["detail"]["agrees_check1"] = f["agrees"]
    out["_judgement"] = cmp_
    return out


def claim_agrees(fields):
    """Whether check 1 will accept the claim as written. Title, first author and year only: those are the
    three the database compares (0013 `_check_registry`). Journal is never a check-1 field — a venue
    disagreement is recorded, and never a reason to withhold the claim."""
    return all(fields[f]["agrees"] for f in ("title", "authors", "year"))


def doi_discrepancy(spelled, resolved):
    """A row whose DOI had to be resolved, or whose spelling is not the canonical DOI."""
    a, b = normalize_doi(spelled or "") or "", normalize_doi(resolved or "") or ""
    if a == b:
        return None
    return {"claimed": (spelled or "").strip() or None, "registry": resolved, "ratio": None, "agrees": False}


def plan_row(*, doi, arxiv, claimed, has_file, confirm, resolve):
    """Decide the case for one legacy row, doing the registry work through the two callables given.

    `confirm(doi)  -> (record | None, tried)` is `registry.confirm_doi` bound to a client and pacer.
    `resolve(title, surname, year) -> (doi | None, source, evidence)` is `resolver.resolve_doi`, bound the same way.

    -> dict(case, doi, record, fields, resolved, tried). `fields` is None when no record was found.
    """
    tried, resolved, rec = [], None, None
    if doi:
        canonical = normalize_doi(doi)
        if canonical:
            rec, tried = confirm(canonical)
            if rec:
                doi = canonical
    if rec is None and (claimed.get("title") or "").strip():
        from litkb.admit.front import first_author_of
        found, _source, _ev = resolve(claimed.get("title"), first_author_of(claimed.get("authors")),
                                      claimed.get("year"))
        if found:
            resolved = found
            rec2, tried2 = confirm(found)
            tried = tried + tried2
            if rec2:
                rec, doi = rec2, found
    if rec is None:
        return {"case": "E", "shape": "manual" if has_file else "held", "doi": None, "arxiv": arxiv,
                "record": None, "fields": None, "resolved": resolved, "tried": tried, "has_file": has_file}
    fields = compare_row(rec, claimed)
    # the ADMISSION SHAPE: whether the claim is offered to check 1, or the file's binding stands in for it
    if claim_agrees(fields):
        shape = "claimed"
    elif has_file:
        shape = "file"
    else:
        shape = "held"
    # the CASE is the shape, except that a DOI the row did not spell is case D whichever shape follows
    case = "D" if resolved else {"claimed": "A", "file": "B", "held": "C"}[shape]
    return {"case": case, "shape": shape, "doi": doi, "arxiv": arxiv, "record": rec, "fields": fields,
            "resolved": resolved, "tried": tried, "has_file": has_file}


def author_surname_agrees(rec, claimed_authors):
    """Kept as its own name because the report quotes it; the rule itself is the resolver's."""
    from litkb.admit.front import first_author_of

    return family_matches(rec.get("first_author"), first_author_of(claimed_authors))
