"""claims.py — resolve a claim's evidence, and check the claim still matches it.

THE ASYMMETRY THIS FIXES. Registry entries point AT evidence, but no claim in a report
points BACK at the row that proves it, and no measured row knows which claims depend on
it. That is why the findings ledger's era F-numbers went stale for three days after the
recalibration superseded them, and why the supersessions had to be found by hand. With
links in both directions, "what breaks if this number moves" stops being an archaeology
exercise and becomes a check that runs in the test suite.

A claim is: a sentence someone wrote, a VALUE inside it, and a POINTER to the tracked
row that value came from. `verify()` resolves the pointer and compares. A claim whose
evidence has moved is reported as DRIFTED — it is not silently corrected, because which
side is wrong (the number, or the sentence around it) is a judgement.

POINTER GRAMMAR — a superset of the n_source grammar in experiments/README.md, so the
two registries speak one language:

    path#csv:<col>@<k>=<v>[;<k2>=<v2>]   one cell: column <col> of the single row
                                          matching every filter. Zero or many matching
                                          rows is an ERROR, never a silent first-match.
    path#json:<key>                       a top-level key (ints, floats, strings)
    path#regex:<pattern>                  first capture group of the first match
    path#rows[:<col>=<val>]               a row count
    path#lines                            non-blank, non-comment line count
    dir#dir_csv_count                     how many .csv files a tracked directory
                                          holds — for claims about the archive itself
                                          ("87 curves are tracked")

Lake paths and globs are UNCHECKABLE by design (CI has no lake) and resolve to None,
which `verify` reports as unresolved rather than failing.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
CLAIMS = SCRIPTS / "claims.yaml"

_UNCHECKABLE = ("G:", "/content/", "D:", "http", "~")


class Unresolved(Exception):
    """The pointer is well-formed but cannot be read here (lake path, missing file)."""


def _find(rel):
    if str(rel).startswith(_UNCHECKABLE) or "*" in str(rel):
        raise Unresolved(f"{rel} is not checkable from a checkout")
    for root in (REPO, SCRIPTS):
        p = root / rel
        if p.exists():
            return p
    raise Unresolved(f"{rel} does not exist")


def _csv_rows(path):
    body = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def resolve(pointer):
    """Resolve an evidence pointer to a value (str). Raises Unresolved or ValueError."""
    if "#" not in str(pointer):
        raise ValueError(f"evidence {pointer!r} has no '#<selector>'")
    rel, sel = str(pointer).split("#", 1)
    p = _find(rel)

    if sel.startswith("csv:"):
        spec = sel[4:]
        if "@" not in spec:
            raise ValueError(f"{pointer!r}: csv selector needs <col>@<filters>")
        col, filt = spec.split("@", 1)
        want = dict(kv.split("=", 1) for kv in filt.split(";") if kv)
        hits = [r for r in _csv_rows(p)
                if all(str(r.get(k, "")).strip() == v for k, v in want.items())]
        if len(hits) != 1:
            raise ValueError(f"{pointer!r}: matched {len(hits)} rows, need exactly 1")
        if col not in hits[0]:
            raise ValueError(f"{pointer!r}: no column {col!r}")
        return str(hits[0][col]).strip()

    if sel.startswith("json:"):
        return str(json.loads(p.read_text(encoding="utf-8"))[sel[5:]])

    if sel.startswith("regex:"):
        m = re.search(sel[6:], p.read_text(encoding="utf-8"), re.M)
        if not m:
            raise ValueError(f"{pointer!r}: pattern matched nothing")
        return (m.group(1) if m.groups() else m.group(0)).strip()

    if sel == "dir_csv_count":
        if not p.is_dir():
            raise ValueError(f"{pointer!r}: {rel} is not a directory")
        return str(sum(1 for _ in p.glob("*.csv")))

    if sel == "lines":
        return str(sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                       if ln.strip() and not ln.lstrip().startswith("#")))

    if sel == "rows" or sel.startswith("rows:"):
        rows_ = _csv_rows(p)
        if sel == "rows":
            return str(len(rows_))
        col, _, val = sel[5:].partition("=")
        return str(sum(1 for r in rows_ if str(r.get(col, "")).strip() == val))

    raise ValueError(f"{pointer!r}: unknown selector {sel!r}")


def load():
    if not CLAIMS.exists():
        return []
    import yaml
    return (yaml.safe_load(CLAIMS.read_text(encoding="utf-8")) or {}).get("claims", [])


def verify(claim):
    """Return (state, detail). state ∈ ok | drifted | unresolved | error."""
    try:
        got = resolve(claim["evidence"])
    except Unresolved as e:
        return "unresolved", str(e)
    except (ValueError, KeyError, OSError) as e:
        return "error", str(e)

    want = str(claim["value"]).strip()
    tol = claim.get("tolerance")
    if tol is not None:
        try:
            if abs(float(got) - float(want)) <= float(tol):
                return "ok", got
            return "drifted", f"evidence says {got}, claim says {want} (tol {tol})"
        except ValueError:
            return "error", f"tolerance given but {got!r}/{want!r} are not numbers"
    if got == want:
        return "ok", got
    return "drifted", f"evidence says {got!r}, claim says {want!r}"


def verify_all():
    return [(c, *verify(c)) for c in load()]
