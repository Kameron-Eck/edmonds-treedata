"""How a work's fields are PRINTED in the tracker and manifest exports.

One home, shared by `litkb.export` (which writes the cell) and `litkb.migrate_legacy.plan` (which
compares the legacy cell against it). If the two disagreed, the diff gate would report differences the
discrepancy table could not explain — which is exactly what the gate exists to catch.
"""
import re


def authors_line(authors):
    """A work version's author list as the tracker prints it.

    The tracker's own style, read off `Reports/literature_tracker.csv`: `Nowak, D.J. & Greenfield, E.J.`
    for two, `Freudenberg, M. et al.` for three or more, initials joined WITHOUT a space.
    """
    if not authors:
        return ""
    names = []
    for a in authors if isinstance(authors, list) else []:
        if isinstance(a, dict):
            fam, giv = (a.get("family") or a.get("name") or ""), (a.get("given") or "")
            initials = "".join(f"{p[0]}." for p in re.split(r"[\s.\-]+", giv) if p)
            names.append(f"{fam}, {initials}" if (fam and initials) else fam)
        elif a:
            names.append(str(a))
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) > 2:
        return f"{names[0]} et al."
    return " & ".join(names)


def norm_cell(s):
    """Normalised comparison of two printed cells: case, punctuation and whitespace folded away.

    This is the FORMAT-ONLY test the diff gate uses. Two cells that normalise equal say the same thing
    in different type (`D.J.` and `D. J.`, a trailing full stop, `&` and `and`); anything else is a real
    difference and needs a discrepancy record to explain it.
    """
    s = str(s if s is not None else "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def year_int(v):
    """The 4-digit year at the front of a legacy cell, or None.

    Tracker rows 327 and 329 carry `2019a` and `2019b` — the filename convention's same-year suffix written
    into the YEAR column. There is no correction pass (decisions.yaml, P3 load), so the cell is carried as it
    is and read leniently here; the suffix survives as a `year` discrepancy against the registry's plain year.
    Without this the load stops on the row: `int('2019a')` raises, and one malformed cell would end the pass.
    """
    m = re.match(r"\s*([0-9]{4})", str(v if v is not None else ""))
    return int(m.group(1)) if m else None
