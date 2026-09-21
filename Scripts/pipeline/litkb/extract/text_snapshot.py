"""An HTML page's readable text, as the heading and paragraph lines a snapshot is made of.

    kind, why = classify(data, content_type)      # 'html' | 'not-html', and the sentence for it
    blocks    = parse(data, content_type)         # [{"kind": "heading"|"paragraph", "text": …}]
    text      = render(blocks)                    # what lands as the `.txt` snapshot

WHY THIS EXISTS. ``litkb hunt``'s URL branch asked every server for ``application/pdf`` and handed
whatever came back to :func:`litkb.hunt.land_download`, whose shape check quarantined anything
without a ``%PDF-`` header and refused the hunt ``not-a-pdf``. That is right for a *paper* — the
2026-09-15 incident was 295,657 bytes of a sign-in page filed as
``IFLA_2017_library-reference-model.pdf`` — and it is wrong for the other half of what the
convention calls a web source. ``Scripts/docs/LITERATURE_CONVENTION.md`` records a blog post, a
documentation page or a standard as a manual proposal carrying the URL and the retrieval date, and
`litkb.admit.front.web_snapshot_evidence` has been able to bind one since the P8 work — but
nothing could ever REACH it, because the fetch refused the bytes two functions earlier. Six sources
the 2026-09-15 linkage review depends on have no KB record for exactly that reason.

STDLIB ONLY, and deliberately. ``html.parser`` ships with Python; BeautifulSoup, lxml, readability
and trafilatura do not, and a new dependency for a text extractor is a new thing to pin, audit and
carry into every venv the package runs in. What this gives up is the boilerplate-removal a
readability algorithm does: :data:`SKIP` drops the tags whose content is never the document
(script, style, nav, header, footer, aside, form), and nothing here scores a block for
"articleness". A page's navigation menu therefore survives as short paragraph lines. That is said
out loud rather than hidden, because the alternative — dropping every short line — silently loses
real headings and one-sentence paragraphs, and a snapshot that quietly omits the document's own
words is worse than one that carries its menu.

THE BYTES ARE THE RECORD, NOT THIS TEXT. `litkb.hunt` writes the raw body's sha256 beside the
snapshot's own, so a later reader can ask whether this extraction is what those bytes say without
trusting this module.
"""
import html.parser
import re

#: The media types whose body IS a web page. ``application/xhtml+xml`` is the same document served
#: under its XML type; nothing else here is treated as a page.
HTML_MEDIA = ("text/html", "application/xhtml+xml")

#: The media types that say "this is a PDF", and so are never a page whatever the bytes look like.
PDF_MEDIA = ("application/pdf", "application/x-pdf")

#: Tags whose CONTENT is never the document. Dropped with everything nested inside them.
SKIP = frozenset((
    "script", "style", "noscript", "template", "svg", "math", "iframe", "object", "embed",
    "nav", "header", "footer", "aside", "form", "button", "select", "option", "datalist",
))

#: Tags that open a heading line. The level is kept in the block so a later reader can see the
#: document's shape; the ingest stores every one of them as a `heading` block.
HEADINGS = {f"h{n}": n for n in range(1, 7)}

#: Tags that end the current line. A `div` is here because pages that use no `<p>` at all are
#: ordinary, and without it such a page renders as one block of every word it holds.
BLOCKS = frozenset((
    "p", "li", "dd", "dt", "blockquote", "pre", "figcaption", "caption", "td", "th", "tr",
    "div", "section", "article", "main", "details", "summary", "address", "hr", "ul", "ol",
    "dl", "table", "thead", "tbody", "tfoot", "fieldset", "legend", "title",
))

#: Elements that never close. A tag stack that pushed these would never pop and every later
#: `</div>` would close the wrong element.
VOID = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                  "param", "source", "track", "wbr"))

#: A SITE's furniture, named by the `id`/`class` token its container carries. MEASURED, not
#: guessed: the Crossref blog article of the fixture puts its menu in `<div id="nav2019"
#: class="nav-container">` and `<div class="nav-wrapper">` — no `<nav>` element anywhere — and
#: renders 80 lines of menu, social links and other posts' teasers ahead of the article's own
#: title. That is not cosmetic. `litkb.admit.binding` binds a claimed title only inside the first
#: `TITLE_REGION_LINES` (45) lines and wants the first author within `AUTHOR_NEAR_LINES` (15) of
#: it, so a snapshot carrying the whole page CANNOT be admitted for the work it is a page of: the
#: article's title lands at line 84 and the check refuses it `outside the title region`. Dropping
#: the furniture is what makes the snapshot a snapshot OF THE ARTICLE.
#:
#: WHOLE TOKENS, split on non-alphanumerics, and deliberately NOT `header` or `search`: an
#: `article-header` is where a byline lives and a page whose title sat in one would lose exactly
#: the lines check 3 reads. Each token here names furniture and nothing else.
SKIP_TOKENS = frozenset((
    "nav", "navbar", "navigation", "menu", "submenu", "megamenu", "sidebar", "footer",
    "breadcrumb", "breadcrumbs", "cookie", "cookies", "consent", "banner", "social", "share",
    "sharing", "newsletter", "subscribe", "promo", "advert", "ads", "masthead", "skiplink",
    "skip", "sitenav", "topbar", "pagination", "widget", "related", "recirculation",
))

_WS = re.compile(r"\s+")
_TOKENS = re.compile(r"[^a-z0-9]+")
#: `<meta charset=…>` / `<meta http-equiv="content-type" content="…; charset=…">`, looked for in the
#: head only (the first 4 KiB), which is where the standard puts it.
_META_CHARSET = re.compile(rb"""charset\s*=\s*["']?\s*([A-Za-z0-9_.:+-]+)""", re.I)

#: The first bytes a page is recognised by. The same window and the same two markers
#: `litkb.acquire.store.pdf_shape` uses to say "they look like HTML" in a quarantine reason — and
#: it now READS this function rather than carrying its own copy, so the two cannot drift into
#: disagreeing about the same bytes (CLAUDE.md §3.3).
SNIFF_WINDOW = 512


def looks_like_html(data):
    """Do these bytes open like an HTML document? -> bool

    A marker scan, not a parse: `html.parser` accepts ANY byte string and returns no blocks for
    bytes that are not markup, so "did the parser succeed" is not a test. The window is the head of
    the response because a served page puts its doctype there and a binary that happens to contain
    the word `<html>` a megabyte in is not a page."""
    head = (data or b"")[:SNIFF_WINDOW].lower()
    return b"<html" in head or b"<!doctype html" in head


def media_type(content_type):
    """The bare media type out of a Content-Type header, lowercased. `''` when there is none."""
    return str(content_type or "").split(";")[0].strip().lower()


def charset_of(content_type):
    """The charset the SERVER declared, lowercased, or `''`."""
    for part in str(content_type or "").split(";")[1:]:
        k, _, v = part.partition("=")
        if k.strip().lower() == "charset":
            return v.strip().strip('"\'').lower()
    return ""


def classify(data, content_type):
    """Is this response a web PAGE the hunt should snapshot? -> (`'html'` | `'not-html'`, why)

    THE SERVER'S OWN DECLARATION DECIDES, and that is the whole of the rule that keeps the
    2026-09-15 guard standing. Three clauses, in order:

      1. bytes that begin with ``%PDF-`` are a PDF whatever the header says;
      2. a declared ``text/html`` / ``application/xhtml+xml`` is a page. This is the live case: the
         Crossref blog article of the fixture answers exactly this;
      3. a declared type that is NEITHER html nor pdf (``application/octet-stream`` is the one
         that happens) is a page only if the bytes themselves open like one.

    AND WHEN THE RESPONSE DECLARED NOTHING AT ALL, these bytes are `not-html` even when they parse
    as HTML. That is not an oversight and it is the reason this function returns a sentence: an
    unlabelled body is exactly the shape of the 2026-09-15 incident (a sign-in page served under a
    `.pdf` name), `litkb.hunt.land_download` has quarantined it since, and that guard
    (`qc/instruments/litkb_p2_mutations.py` row H1) keeps every byte of its behaviour. A real
    server sends a Content-Type; a body with none has told us nothing, and "the bytes look like
    HTML" is precisely what the incident's bytes also looked like.
    """
    if (data or b"").startswith(b"%PDF-"):
        return "not-html", "the bytes begin with %PDF-: this is a document, not a page"
    mt = media_type(content_type)
    # BEGIN guard: a body the response did not label gets the PDF shape check it always got
    if not mt:
        return "not-html", ("the response declared no content type, so these bytes get the PDF "
                            "shape check they have always had — an unlabelled body is the shape "
                            "of the 2026-09-15 sign-in page")
    # END guard: a body the response did not label gets the PDF shape check it always got
    if mt in HTML_MEDIA:
        return "html", f"the server declared {mt}"
    if mt in PDF_MEDIA:
        return "not-html", f"the server declared {mt}"
    if looks_like_html(data):
        return "html", f"the server declared {mt} and the bytes open as an HTML document"
    return "not-html", f"the server declared {mt} and the bytes do not open as an HTML document"


def decode(data, content_type=None):
    """The page's text, decoded by the server's charset, then the document's, then UTF-8.

    `errors='replace'` at every step: a snapshot of a page in an encoding nobody declared is still
    worth more than a refusal, and the raw bytes' sha256 travels beside it either way."""
    data = data or b""
    for enc in (charset_of(content_type), _declared_charset(data), "utf-8"):
        if not enc:
            continue
        try:
            return data.decode(enc, "replace")
        except LookupError:                       # a charset Python has never heard of
            continue
    return data.decode("utf-8", "replace")


def _declared_charset(data):
    m = _META_CHARSET.search((data or b"")[:4096])
    return m.group(1).decode("ascii", "ignore").lower() if m else ""


def is_furniture(attrs):
    """Does this element's `id`/`class` name it as a site's furniture? -> bool

    Whole tokens out of both attributes, against :data:`SKIP_TOKENS`. `class="nav-container"`
    is furniture; `id="nav2019"` is not, because `nav2019` is one token and is not `nav` — the
    rule is deliberately literal rather than a substring test, since a substring test makes
    `navigate`, `menuitem` and `promotion` furniture too."""
    words = set()
    for name, value in attrs or ():
        if str(name).lower() in ("id", "class"):
            words |= {w for w in _TOKENS.split(str(value or "").lower()) if w}
    return bool(words & SKIP_TOKENS)


class _Reader(html.parser.HTMLParser):
    """Text out of markup: headings as their own lines, everything else as paragraph lines.

    A TAG STACK, not a counter. The first version counted skip-tag opens and closes, which is
    correct only while every skipped element is a tag no other element uses — and the moment a
    `<div class="nav-container">` became skippable it stopped being: the matching `</div>` is
    indistinguishable from the twenty `</div>`s inside it, so the counter never came back down and
    the rest of the document vanished. The stack records WHERE the skip began, and it ends when
    the element that began it is popped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self._buf, self._head = [], [], 0
        self._stack, self._skip_at = [], None

    @property
    def _skip(self):
        return self._skip_at is not None

    # ── the line under construction ────────────────────────────────────────────────────────
    def _flush(self, kind="paragraph", level=None):
        text = _WS.sub(" ", "".join(self._buf)).strip()
        self._buf = []
        if not text:
            return
        if self.blocks and self.blocks[-1]["text"] == text and self.blocks[-1]["kind"] == kind:
            return                                # a repeated line (a menu printed twice)
        b = {"kind": kind, "text": text}
        if level:
            b["level"] = level
        self.blocks.append(b)

    # ── the parser's own hooks ─────────────────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self._stack.append(tag)
            # BEGIN guard: a site's furniture is dropped with everything nested inside it
            if not self._skip and (tag in SKIP or is_furniture(attrs)):
                self._flush("heading", self._head) if self._head else self._flush()
                self._skip_at = len(self._stack)
                return
            # END guard: a site's furniture is dropped with everything nested inside it
        if self._skip:
            return
        if tag == "br":
            self._buf.append(" ")
            return
        if tag in HEADINGS:
            self._flush()
            self._head = HEADINGS[tag]
            return
        if tag in BLOCKS:
            self._flush("heading", self._head) if self._head else self._flush()

    def handle_startendtag(self, tag, attrs):
        if not self._skip and tag == "br":
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag not in VOID and tag in self._stack:
            # the LAST open element of this name is the one being closed — the innermost `</div>`
            # closes the innermost `<div>`, not the page's outermost one. Unbalanced markup is
            # ordinary, so everything left open inside it is closed with it.
            del self._stack[len(self._stack) - 1 - self._stack[::-1].index(tag):]
            if self._skip and len(self._stack) < self._skip_at:
                self._skip_at = None
                return
        if self._skip:
            return
        if tag in HEADINGS:
            self._flush("heading", HEADINGS[tag])
            self._head = 0
            return
        if tag in BLOCKS:
            self._flush("heading", self._head) if self._head else self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush("heading", self._head) if self._head else self._flush()


def parse(data, content_type=None):
    """-> [{"kind": "heading"|"paragraph", "text": str, "level": int (headings only)}]"""
    r = _Reader()
    r.feed(decode(data, content_type))
    r.close()
    return r.blocks


def render(blocks):
    """The `.txt` snapshot's body: one line per block, a blank line between them.

    The file that lands under `_litkb_staging/web/` and that
    `litkb.admit.front.web_snapshot_evidence` binds the claimed title against — so the FIRST lines
    have to be the page's own opening words, which is what check 3 reads."""
    return "\n\n".join(b["text"] for b in blocks) + ("\n" if blocks else "")
