"""Check 3 — the file is that study (design §4.6).

    b = bind(pdf_path, registry_title, first_author_family)

A file binds only when BOTH hold (referee fix D2, Reports/LITKB_P2_REFEREE_2026-09-14.md):

  1. the REGISTRY title is found at normalised difflib ratio >= 0.85 either in the PDF's own Title metadata or
     in a window of 1-3 consecutive lines of `pdftotext -f 1 -l 1` that
       * starts within the first TITLE_REGION_LINES non-empty lines (the header / title region),
       * does not lie under a "References" / "Bibliography" heading,
       * is not inside a reference list (>= 2 reference-shaped lines within REF_NEIGHBOURHOOD lines of it:
         numbered or bracketed entries, or "Surname, I." with a year), and
       * is not on a citation instruction ("please cite this article as", "to cite this article", "citation for
         published version", "how to cite") or on the COVER_CONTINUATION lines its citation wraps onto;
  2. the registry's first author's SURNAME is on the page as a whole token (Unicode-normalised, diacritics
     folded; a multi-part name as consecutive tokens or joined; a hyphenated word is ONE token, so "Li" is
     not found in "Li-ion" and "Ward" is not found in "towards") within AUTHOR_NEAR_LINES lines of that title
     window. For a title found in the PDF metadata, the surname must be a whole token of the PDF Author
     metadata or of an admissible line of the title region.

The two line constants were measured on every held paper with a recorded title and first author
(qc/instruments/litkb_binding_region.py -> Reports/litkb_binding_region_2026-09-14.csv).

A first page with no text layer and no title match is `binding-pending`: it waits for OCR in P4
(decisions.yaml §15.14). Anything else that fails is `binding-failed`. The evidence goes into files.binding; the
database re-checks it (litkb._check_binding, migrations 0013 and 0014).

Reads only. The PDF is never moved, renamed or written: the first-page text goes to a temporary directory.
"""
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from litkb.admit.resolver import _norm_text, _UNDECODABLE_RE, strip_tags, title_match_ratio
from litkb.extract import readiness

BIND_RATIO = 0.85
MIN_TEXT_CHARS = 200     # below this (normalised characters) the first page has no usable text layer
# Measured (qc/instruments/litkb_binding_region.py, Reports/LITKB_P2_REPORT_2026-09-14.md "Fixes after referee"): on
# 188 held papers that bound under the old rule, the page-1 title window started at line <= 12 on 186, at 26 and at
# 43 on the other two; the surname sat <= 3 lines from the title on all but 6 (9, 14, 15, 22, 58 and one found only
# via metadata). Over the grid region {15, 20, 30, 45, 50} x near {3, 5, 10, 15, 25, 60} the smallest pair that
# loses none of the 188 is 45 / 15 (chosen after reading the distribution, not fixed before it).
TITLE_REGION_LINES = 45
AUTHOR_NEAR_LINES = 15
REF_NEIGHBOURHOOD = 2
COVER_CONTINUATION = 3   # a citation instruction's own line and the lines its citation wraps onto
# a glued affiliation marker ("Pengraa,", "GEYERt") is accepted only on surnames at least this long, so a short
# surname never matches a longer word ("Li" -> "lie", "Park" -> "parks")
MARKER_MIN_SURNAME = 5

_REF_HEADING = re.compile(r"^\s*(references?( and notes)?|bibliography|literature cited|works cited|cited literature)"
                          r"\s*:?\s*$", re.I)
_REF_NUMBERED = re.compile(r"^\s*(\[\s*\d{1,3}\s*\]|\d{1,3}\.)\s+\S")
_REF_AUTHOR_YEAR = re.compile(r"\b[A-Z][A-Za-z'’\-]+,\s+(?:[A-Z]\.\s*-?\s*){1,3}.*\b(1[89]|20)\d{2}[a-z]?\b")
_COVER = re.compile(r"please\s+cite|to\s+cite\s+this|cite\s+this\s+article|citation\s+for\s+published\s+version|"
                    r"how\s+to\s+cite", re.I)
# intra-word joiners: a hyphenated or apostrophised word is one token ("O'Neil-Dunne", "Li-ion")
_JOINERS = "-'‐‑’ʼ"


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


def page_lines(text):
    """The page's non-empty lines, whitespace collapsed (the unit every window and distance counts in)."""
    return [" ".join(ln.split()) for ln in (text or "").splitlines() if _norm_text(ln)]


def fold_tokens(s):
    """Whole-word tokens: NFKD, diacritics dropped, casefolded; words split on anything but letters, digits and
    intra-word joiners; each word keeps only its letters ("Wang1,2" -> "wang", "O'Neil-Dunne" -> "oneildunne")."""
    # the extractor's own damage is REMOVED before the split, not treated as a word boundary:
    # "K<FFFD>pcke" is one token that lost a letter, not the two tokens "k" and "pcke"
    # (resolver.UNDECODABLE — the same three characters the title comparator drops).
    s = _UNDECODABLE_RE.sub("", strip_tags(s or ""))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    out = []
    for word in re.split(r"[^\w" + re.escape(_JOINERS) + r"]+", s):
        letters = "".join(c for c in word if c.isalpha())
        if letters:
            out.append(letters)
    return out


def surname_tokens(family):
    """The registry family name as tokens ('De la Cruz' -> ['de', 'la', 'cruz'])."""
    return fold_tokens(family)


def tokens_contain(tokens, fam):
    """The surname as consecutive whole tokens, or as consecutive tokens that join to it ('De La Cruz' and
    'DelaCruz' both match 'De la Cruz'). Never a substring of a token."""
    if not fam or not tokens:
        return False
    joined = "".join(fam)
    for s in range(len(tokens)):
        acc = ""
        for t in tokens[s:]:
            acc += t
            if acc == joined or (len(joined) >= MARKER_MIN_SURNAME and len(acc) == len(joined) + 1
                                 and acc.startswith(joined)):
                return True
            if len(acc) > len(joined) or not joined.startswith(acc):
                break
    return False


def author_on_page(family, text):
    """The folded surname as a whole token anywhere in `text` (kept for callers outside check 3)."""
    return tokens_contain(fold_tokens(text), surname_tokens(family))


def _line_flags(lines):
    """-> (under_references, reference_shaped, cover) per line."""
    under, ref, cover = [], [], []
    seen_heading = False
    for ln in lines:
        if _REF_HEADING.match(ln):
            seen_heading = True
        under.append(seen_heading)
        ref.append(bool(_REF_NUMBERED.match(ln) or _REF_AUTHOR_YEAR.search(ln)))
        cover.append(bool(_COVER.search(ln)))
    return under, ref, cover


def window_refusal(lines, start, n, flags=None):
    """Why the window lines[start:start+n] cannot carry the title ('' when it can)."""
    under, ref, cover = flags or _line_flags(lines)
    end = start + n - 1
    # BEGIN guard: binding title region
    if start >= TITLE_REGION_LINES:
        return f"outside the title region (line {start} >= {TITLE_REGION_LINES})"
    # END guard: binding title region
    # BEGIN guard: binding refuses reference-list windows
    if any(under[start:end + 1]):
        return "under a References/Bibliography heading"
    lo, hi = max(0, start - REF_NEIGHBOURHOOD), min(len(lines), end + REF_NEIGHBOURHOOD + 1)
    if sum(ref[lo:hi]) >= 2:
        return "inside a reference list"
    # END guard: binding refuses reference-list windows
    # BEGIN guard: binding refuses citation-instruction windows
    if any(cover[max(0, start - COVER_CONTINUATION):end + 1]):
        return "next to a citation instruction (a cover sheet or a 'please cite' line)"
    # END guard: binding refuses citation-instruction windows
    return ""


def best_window(title, text):
    """-> (ratio, window): the best 1-3 consecutive-line window of `text` against `title`, ANY position (a
    diagnostic; binding itself uses only admissible windows)."""
    lines = page_lines(text)
    best, win = 0.0, ""
    for i in range(len(lines)):
        for n in (1, 2, 3):
            if i + n > len(lines):
                break
            w = " ".join(lines[i:i + n])
            r = title_match_ratio(title, w)
            if r > best:
                best, win = r, w
    return best, win


def verdict(ratio, author_near_title, text_layer):
    """The binding verdict from the three measured facts."""
    # BEGIN guard: binding verdict
    if ratio >= BIND_RATIO and author_near_title:
        return "bound"
    if not text_layer and ratio < BIND_RATIO:
        return "binding-pending"
    return "binding-failed"
    # END guard: binding verdict


def bind_any(pdf_path, titles, first_author, *, page_text=None, info=None):
    """bind() against every title form the registry published; the best result wins.

    A registry that publishes a subtitle publishes two forms of the title, and since migration 0020
    the WORK is stored under the joined one ("Magellan: toward building entity matching management
    systems"). The first page of a PDF prints whichever form its publisher chose — often the bare
    one. Binding against the work's title alone would therefore start refusing papers it used to
    bind, on a change that was about keys, not about files.

    So every form is tried and the best is kept, which is the same rule `judge_candidate` has always
    used on the registry side (max ratio over `rec["titles"]`). The result records `registry_title`
    as the WORK's title — `_check_binding` (migration 0013) refuses a binding measured against
    another title than the work's, and that guard is right — plus `matched_title_form`, which names
    the form that actually matched, so the two can never be confused for one another.

    `titles` in the order registry.title_forms() returns them: the work's own title first.
    """
    forms = [t for t in (titles or []) if (t or "").strip()]
    if not forms:
        raise ValueError("bind_any needs at least one title form")
    text = first_page_text(pdf_path) if page_text is None else page_text
    info = pdf_info(pdf_path) if info is None else info
    results = [(t, bind(pdf_path, t, first_author, page_text=text, info=info)) for t in forms]
    form, best = max(results, key=lambda tb: (tb[1]["verdict"] == "bound", tb[1]["ratio"],
                                              tb[1]["author_near_title"]))
    best["registry_title"] = forms[0]
    best["matched_title_form"] = form
    if len(forms) > 1:
        best["title_forms_tried"] = {t: b["ratio"] for t, b in results}
    return best


#: How many pages OCR reads when a first page has no text layer. The title, the authors and the
#: affiliation of a scanned paper are on page 1; page 2 is there for the cover-sheet case, where
#: page 1 is the repository's own banner and the paper's own first page is behind it.
OCR_BIND_PAGES = 2

#: The largest document OCR is offered for a BINDING. A book is not a cover sheet: the corpus's
#: 688-page `Schneider_2008` would spend an hour of GPU to answer a question its first page
#: already answers, and the decision to extract a book at all is not this function's to make.
#:
#: The NUMBER is no longer this module's (S4): it is `litkb.config.PAGE_CAP`, because the
#: extraction side needs the same cap and two routes answering "too big?" from two constants is
#: how they drift. The NAME stays, because what it means here — the cap *for a binding OCR* — is
#: this module's fact and every caller and mutation row reads it by this name.
OCR_BIND_MAX_PAGES = readiness.PAGE_CAP

#: Why :func:`ocr_first_pages` refused, when it did. A CLOSED set, in the order the function tests
#: them: the count could not be read (the fail-open hole S4 closed), the document is past the cap,
#: there is no docling environment on this machine, the conversion refused or produced no text.
#: `bind_any_with_ocr` records the code in the binding evidence as `ocr_refusal`, so a
#: `binding-pending` that never got its OCR says which of five things happened instead of leaving
#: a reader to guess from `ocr_attempted`.
OCR_BIND_REFUSALS = ("page-probe-failed", "over-page-cap", "no-worker", "convert-refused",
                     "no-text")


def ocr_first_pages(pdf_path, pages=OCR_BIND_PAGES, python=None, timeout=1800, refusals=None):
    """The first ``pages`` pages as DOCLING'S OCR reads them, or ``''``. Reads only.

    The scan's own defect, stated plainly: :func:`first_page_text` runs ``pdftotext``, a scan has
    no text layer for it to read, and the binding rule needs the TITLE off page 1. So the four
    scans in the corpus (`Anderson_1957`, `Hudson_1978`, `Hwang_1982`, `Ogata_1998`) have sat at
    `binding-pending` since P2 — admitted, with no file bound, invisible to search — and
    `bound-unextracted` had no live instance to exercise because nothing ever became bound.

    Returns ``''`` rather than raising on every failure a caller cannot act on: no Docling
    environment on this machine, a document past :data:`OCR_BIND_MAX_PAGES`, a conversion that
    refuses. The caller then keeps whatever verdict it already had, which is the state before
    this function existed. ``refusals``, when a list is passed, collects the
    :data:`OCR_BIND_REFUSALS` code for whichever of those it was — the empty string alone cannot
    tell a book from a machine with no GPU.

    THE CAP IS NOW FAIL-CLOSED (S4). It used to read ``n = pdf_info(...).get("Pages") or ""`` and
    refuse only ``if n.isdigit() and int(n) > OCR_BIND_MAX_PAGES``. `pdf_info` runs poppler's
    `pdfinfo` and returns ``{}`` when poppler is absent or the file is damaged — so a page count
    that could not be READ fell straight through the guard and OCR ran uncapped, on exactly the
    documents least likely to survive it. The count now comes from
    :func:`litkb.extract.readiness.probe_pages`, in-process pypdfium2 under a deadline, and a
    probe that cannot answer is the refusal `page-probe-failed`, not a pass.
    """
    def refuse(code):
        if refusals is not None:
            refusals.append(code)
        return ""

    # BEGIN guard: a page count that cannot be read refuses the OCR, never passes it
    try:
        n_pages = readiness.probe_pages(pdf_path)
    except readiness.ProbeFailed:
        return refuse("page-probe-failed")
    if readiness.cap_check(n_pages):
        return refuse("over-page-cap")
    # END guard: a page count that cannot be read refuses the OCR, never passes it
    from litkb.extract import docling as D

    if not D.worker_available(python):
        return refuse("no-worker")
    with tempfile.TemporaryDirectory(prefix="litkb_ocrbind_") as d:
        out, met = Path(d) / "ocr.json", Path(d) / "metrics.jsonl"
        try:
            doc, _m = D.extract(str(pdf_path), str(out), str(met), require_text_blocks=False,
                                pages=list(range(1, int(pages) + 1)), ocr=True,
                                python=python, timeout=timeout)
        except Exception:  # noqa: BLE001 - an OCR that refuses leaves the binding where it was
            return refuse("convert-refused")
        text = "\n".join(b.text for b in D.blocks(doc) if (b.text or "").strip())
        return text or refuse("no-text")


def bind_any_with_ocr(pdf_path, titles, first_author, *, info=None, ocr=True, python=None):
    """:func:`bind_any`, and — only when it comes back ``binding-pending`` — again on OCR text.

    The trigger is **no page-1 text layer**, not the ``binding-pending`` verdict, and the corpus
    is why. ``binding-pending`` is `not text_layer AND ratio < BIND_RATIO`; `Ogata_1998`'s first
    page carries one form-feed and nothing else, and the empty page scores a spurious ratio of
    1.000 that sends it down the `binding-failed` branch instead. Both files have the same
    problem — there is nothing on page 1 for ``pdftotext`` to read — and a rule written on the
    verdict would have offered OCR to one of them. A page that HAS text and does not bind is left
    alone: re-reading it with OCR asks a second oracle the question the first one answered.

    The evidence records where the text came from (``page_text_source``), because a binding read
    off an OCR of a scan and one read off a publisher's text layer are not the same evidence and
    a later reader must be able to tell them apart.
    """
    info = pdf_info(pdf_path) if info is None else info
    b = bind_any(pdf_path, titles, first_author, info=info)
    if not ocr or b["verdict"] == "bound" or b["text_layer"]:
        b.setdefault("page_text_source", "pdftotext")
        return b
    refusals = []
    text = ocr_first_pages(pdf_path, python=python, refusals=refusals)
    if not _norm_text(text):
        b.setdefault("page_text_source", "pdftotext")
        b["ocr_attempted"] = True
        # WHICH refusal, not just "it was attempted". A `binding-pending` on a machine with no
        # docling and one on a 700-page book are the same row today; the code says which, and the
        # first is retryable where the second is a decision.
        if refusals:
            b["ocr_refusal"] = refusals[0]
        return b
    after = bind_any(pdf_path, titles, first_author, page_text=text, info=info)
    # `text_layer` stays the PDF's own fact, not the OCR's. It is what stage 0 routes on and what
    # `files.has_text_layer` records, and a scan that OCR bound is still a scan: saying otherwise
    # would send the extraction down the native path and get one page of nothing.
    after["text_layer"] = b["text_layer"]
    after["page_text_source"] = f"docling-ocr p1-{OCR_BIND_PAGES}"
    after["ocr_attempted"] = True
    after["verdict_before_ocr"] = b["verdict"]
    return after


def bind(pdf_path, registry_title, first_author, *, page_text=None, info=None):
    """-> binding evidence dict (the files.binding JSON)."""
    text = first_page_text(pdf_path) if page_text is None else page_text
    info = pdf_info(pdf_path) if info is None else info
    text_layer = len(_norm_text(text)) >= MIN_TEXT_CHARS
    lines = page_lines(text)
    flags = _line_flags(lines)
    fam = surname_tokens(first_author)
    toks = [fold_tokens(ln) for ln in lines]
    any_ratio, _any_win = best_window(registry_title, text)

    windows, refused = [], {}
    for i in range(len(lines)):
        for n in (1, 2, 3):
            if i + n > len(lines):
                break
            r = title_match_ratio(registry_title, " ".join(lines[i:i + n]))
            why = window_refusal(lines, i, n, flags)
            if why:
                if r >= BIND_RATIO:
                    refused.setdefault(why, round(r, 4))
                continue
            windows.append((r, i, n))
    windows.sort(key=lambda w: (-w[0], w[1], w[2]))

    def near(i, n):
        # BEGIN guard: binding author near the title
        lo, hi = max(0, i - AUTHOR_NEAR_LINES), min(len(lines), i + n + AUTHOR_NEAR_LINES)
        return any(tokens_contain(toks[j], fam) for j in range(lo, hi))
        # END guard: binding author near the title

    ratio, matched, source, line, author_near = 0.0, "", "page1", None, False
    if windows:
        ratio, line, n = windows[0]
        matched = " ".join(lines[line:line + n])
        author_near = near(line, n)
        for r, i, k in windows:
            if r < BIND_RATIO:
                break
            if near(i, k):
                ratio, line, matched, author_near = r, i, " ".join(lines[i:i + k]), True
                break
    meta_title = info.get("Title") or ""
    if meta_title and not (ratio >= BIND_RATIO and author_near):
        mr = title_match_ratio(registry_title, meta_title)
        if mr > ratio or mr >= BIND_RATIO:
            # the metadata title has no line on the page: its author is the PDF Author field or an admissible
            # line of the title region
            region = [j for j in range(min(len(lines), TITLE_REGION_LINES)) if not window_refusal(lines, j, 1, flags)]
            meta_author = tokens_contain(fold_tokens(info.get("Author") or ""), fam) or \
                any(tokens_contain(toks[j], fam) for j in region)
            if (mr >= BIND_RATIO and meta_author) or mr > ratio:
                ratio, matched, source, line, author_near = mr, meta_title, "pdf-title", None, meta_author
    author_found = author_near or tokens_contain([t for ts in toks for t in ts], fam) or \
        tokens_contain(fold_tokens(info.get("Author") or ""), fam)
    v = verdict(ratio, author_near, text_layer)
    out = {"verdict": v, "ratio": round(ratio, 4), "matched": matched[:300], "source": source, "page": 1,
           "line": line, "registry_title": registry_title, "first_author": first_author,
           "author_found": author_found, "author_near_title": author_near, "title_region": True,
           "text_layer": text_layer, "page1_chars": len(_norm_text(text)), "best_any_ratio": round(any_ratio, 4)}
    if refused:
        out["refused_windows"] = refused
    if v != "bound":
        out["reason"] = ("; ".join(f"title window {k} (ratio {r})" for k, r in refused.items()) or
                         ("title ratio below 0.85 in the title region" if ratio < BIND_RATIO else
                          "first author not a whole token near the title"))
    return out
