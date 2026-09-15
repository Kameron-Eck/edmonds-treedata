"""Reading the legacy files. Read-only, always: nothing here writes, moves or renames a source file.

The three sources and what each is the authority for today:
  * `Reports/literature_tracker.csv`  — the tracker sheet's machine twin (460 rows; the xlsx is its source)
  * `Reports/literature_tracker_phases.csv` — the Search Phase Reference sheet
  * `Literture\\Validation\\manifest.csv` — one row per held file, with its sha256
"""
import csv
import os
import re
from pathlib import Path

from litkb.acquire.store import LITERATURE_ROOT

SCRIPTS = Path(__file__).resolve().parents[3]      # …/Scripts/pipeline/litkb/migrate_legacy/sources.py
REPO = SCRIPTS.parent                              # Reports/ sits at the repository root, not under Scripts/
TRACKER_CSV = REPO / "Reports" / "literature_tracker.csv"
PHASES_CSV = REPO / "Reports" / "literature_tracker_phases.csv"
BIBLIOGRAPHY_CSV = REPO / "Reports" / "lit_spatiotemporal_bibliography.csv"
MANIFEST_TOPIC = "Validation"

TRACKER_COLUMNS = ["ID", "Author(s)", "Year", "Title", "Journal/Source", "Relevance (max 3 sentences)",
                   "Search Phase", "DOI/URL", "Status", "Evidence grade", "Feeds", "Duplicate of",
                   "File stem", "Bib line", "Read date", "Notes"]
MANIFEST_COLUMNS = ["stem", "title", "authors", "year", "venue", "doi", "arxiv", "source_route",
                    "obtained_date", "sha256", "verified_against_extract", "cited_by"]

_ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/[0-9]{7})", re.I)


def _rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in csv.DictReader(fh)]


def tracker_rows(path=None):
    return _rows(path or TRACKER_CSV)


def phase_rows(path=None):
    return _rows(path or PHASES_CSV)


def manifest_path(root=None, topic=MANIFEST_TOPIC):
    return Path(root or LITERATURE_ROOT) / topic / "manifest.csv"


def manifest_rows(path=None, root=None, topic=MANIFEST_TOPIC):
    return _rows(path or manifest_path(root, topic))


def manifest_by_stem(path=None, root=None, topic=MANIFEST_TOPIC):
    return {r["stem"]: r for r in manifest_rows(path, root, topic) if r.get("stem")}


def pdf_for(stem, root=None, topic=MANIFEST_TOPIC):
    """The held PDF for a manifest stem, or None. Bound IN PLACE: the path is read, never changed."""
    if not stem:
        return None
    p = Path(root or LITERATURE_ROOT) / topic / f"{stem}.pdf"
    return p if p.exists() else None


def identifiers_of(row):
    """(doi, arxiv) as the tracker row spells them. `DOI/URL` may hold either, or a bare URL, or 'N/A — …'."""
    raw = (row.get("DOI/URL") or "").strip()
    if not raw or raw.upper().startswith("N/A"):
        return None, None
    m = _ARXIV_URL.search(raw)
    if m:
        return None, m.group(1)
    if "10." in raw and ("doi.org/" in raw.lower() or raw.lower().startswith(("10.", "doi:"))):
        return raw, None
    return None, None


def claimed_of(row):
    """The tracker's CLAIM about the work — compared with the registry, never admitted as fact."""
    return {"title": row.get("Title") or "", "authors": row.get("Author(s)") or "",
            "year": row.get("Year") or "", "venue": row.get("Journal/Source") or ""}


def feeds_tokens(value):
    """`Feeds` is semicolon-separated doc-qualified tokens (LITERATURE_CONVENTION.md). Order kept, blanks
    dropped, duplicates dropped once. A token's TARGET is not resolved here: the convention's mechanical
    check owns that, and P3 never silently drops a token it cannot resolve."""
    out = []
    for tok in re.split(r"\s*;\s*", value or ""):
        tok = tok.strip().rstrip(".")
        if tok and tok not in out:
            out.append(tok)
    return out


def literature_root():
    return Path(os.environ.get("LITKB_LITERATURE_ROOT", str(LITERATURE_ROOT)))
