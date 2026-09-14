"""Check 3 — the file is that study (design §4.6).

    b = bind(pdf_path, registry_title, first_author_family)

A file binds only when the REGISTRY title is found in its first page's text (every window of 1-3 consecutive
lines, not just the first line: the Averkov 2009 extract opens with a running header, a copyright line and
the author names) or in the PDF's own Title metadata, at normalised difflib ratio >= 0.85, AND the registry's
first-author family name appears on the first page (or in the PDF Author metadata). The measured evidence
goes into files.binding; the database re-checks it (litkb._check_binding, migration 0013).

A first page with no text layer and no metadata match is `binding-pending`: it waits for OCR in P4
(decisions.yaml §15.14). Anything else that fails is `binding-failed`.

Reads only. The PDF is never moved, renamed or written: the first-page text goes to a temporary directory.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from litkb.admit.resolver import _ascii_fold, _norm_text, family_name, strip_tags, title_match_ratio

BIND_RATIO = 0.85
MIN_TEXT_CHARS = 200     # below this (normalised characters) the first page has no usable text layer


def first_page_text(pdf_path):
    """pdftotext -f 1 -l 1 -layout into a temporary directory. '' when pdftotext is missing or fails."""
    with tempfile.TemporaryDirectory(prefix="litkb_bind_") as d:
        out = Path(d) / "p1.txt"
        try:
            subprocess.run(["pdftotext", "-f", "1", "-l", "1", "-layout", str(pdf_path), str(out)],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
        return out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""


def pdf_info(pdf_path):
    """pdfinfo key/value pairs ({} when pdfinfo is missing)."""
    try:
        r = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    info = {}
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info


def best_window(title, text):
    """-> (ratio, window): the best 1-3 consecutive-line window of `text` against `title`."""
    raw = [" ".join(ln.split()) for ln in (text or "").splitlines() if _norm_text(ln)]
    best, win = 0.0, ""
    for i in range(len(raw)):
        for n in (1, 2, 3):
            if i + n > len(raw):
                break
            w = " ".join(raw[i:i + n])
            r = title_match_ratio(title, w)
            if r > best:
                best, win = r, w
    return best, win


def author_on_page(family, text):
    """The folded family name on the page: as a substring of the squashed alphanumerics when it is 4+
    characters (multi-part names like 'De la Cruz' -> 'delacruz'), else as a whole word."""
    fam = family_name(family) if family else ""
    if not fam:
        return False
    folded = _ascii_fold(strip_tags(text)).lower()
    if len(fam) >= 4:
        return fam in re.sub(r"[^0-9a-z]+", "", folded)
    return re.search(r"(?<![0-9a-z])" + re.escape(fam) + r"(?![0-9a-z])", _norm_text(folded)) is not None


def bind(pdf_path, registry_title, first_author, *, page_text=None, info=None):
    """-> binding evidence dict (the files.binding JSON)."""
    text = first_page_text(pdf_path) if page_text is None else page_text
    info = pdf_info(pdf_path) if info is None else info
    text_layer = len(_norm_text(text)) >= MIN_TEXT_CHARS
    ratio, matched = best_window(registry_title, text)
    source = "page1"
    meta_title = info.get("Title") or ""
    if meta_title:
        mr = title_match_ratio(registry_title, meta_title)
        if mr > ratio:
            ratio, matched, source = mr, meta_title, "pdf-title"
    author_found = author_on_page(first_author, text) or author_on_page(first_author, info.get("Author") or "")
    # BEGIN guard: binding verdict
    if ratio >= BIND_RATIO and author_found:
        verdict = "bound"
    elif not text_layer and ratio < BIND_RATIO:
        verdict = "binding-pending"
    else:
        verdict = "binding-failed"
    # END guard: binding verdict
    return {"verdict": verdict, "ratio": round(ratio, 4), "matched": matched[:300], "source": source, "page": 1,
            "registry_title": registry_title, "first_author": first_author, "author_found": author_found,
            "text_layer": text_layer, "page1_chars": len(_norm_text(text))}
