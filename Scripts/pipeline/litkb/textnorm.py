"""The ONE Python normalisation of DOIs, session/agent labels and line endings. The database is the authority
(litkb.norm_identifier and litkb.norm_label, migration 0014); these functions must return exactly what those
return, and qc/test_litkb_p2.py drives both over the shared table qc/testdata/litkb_p2/doi_forms.csv and over
every invisible code point below (referee fixes D1 and D7, Reports/LITKB_P2_REFEREE_2026-09-14.md).

    normalize_doi(" https://www.doi.org/10.1890/0012-9658(1998)079[2032:RFFATD]2.0.CO;2/ ")
        -> "10.1890/0012-9658(1998)079[2032:rffatd]2.0.co;2"
    norm_label("sess-admit ") -> "sess-admit"
    canonical_newlines("a line\\r\\nand more") -> "a line\\nand more"

`canonical_newlines` HAD no litkb.* twin: until migration 0026 its database side was written inline in one
query (litkb/review_check.py::_BLOCK_SQL). 0026 gives it one — `litkb.canonical_newlines(text)` — because
the recording path needed the same rule in three more places (the 0007 verify trigger, use.locate_quote's
WHERE, and review_check's), and three inline copies is the drift CLAUDE.md 3.3 is about. `sql_canonical_newlines`
below is the ONE Python-side spelling of that call; its own docstring names the single test that binds the
two halves.

Invisible characters: every code point that Python 3.12 (Unicode 15.0) classes as whitespace (str.isspace) or
as category Zs, Zl, Zp or Cf — NBSP, zero-width space/joiners, BOM, bidi marks, tag characters. They are REMOVED
wherever they occur, not only at the ends: a label or a DOI never legitimately carries one.

DOI rule, in order: remove invisible characters; lower-case ASCII letters only (DOIs are case-insensitive for
ASCII; the database's libc collation must not decide anything else); cut everything before the FIRST "10." (so
doi:, doi: , DOI:, doi.org/, www.doi.org/, http(s)://(dx.)doi.org/ and urn:doi: all go); strip trailing "/", ".",
",", ";" and ":". A value with no "10." normalises to "" (not a DOI). Percent-encoded DOIs are NOT decoded.
"""
import re

INVISIBLE_RANGES = (
    (0x0009, 0x000D), (0x001C, 0x0020), (0x0085, 0x0085), (0x00A0, 0x00A0), (0x00AD, 0x00AD),
    (0x0600, 0x0605), (0x061C, 0x061C), (0x06DD, 0x06DD), (0x070F, 0x070F), (0x0890, 0x0891),
    (0x08E2, 0x08E2), (0x1680, 0x1680), (0x180E, 0x180E), (0x2000, 0x200F), (0x2028, 0x202F),
    (0x205F, 0x2064), (0x2066, 0x206F), (0x3000, 0x3000), (0xFEFF, 0xFEFF), (0xFFF9, 0xFFFB),
    (0x110BD, 0x110BD), (0x110CD, 0x110CD), (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0001, 0xE0001), (0xE0020, 0xE007F),
)
_INVISIBLE = re.compile("[" + "".join(
    re.escape(chr(a)) if a == b else f"{re.escape(chr(a))}-{re.escape(chr(b))}" for a, b in INVISIBLE_RANGES) + "]")
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_DOI_TAIL = re.compile(r"[/.,;:]+$")
#: One LINE ENDING -> one "\n". `\r\n` is ONE ending, a lone `\r` is one, `\n` is already one.
#: Deliberately NOT a collapse of consecutive endings: see canonical_newlines.
_LINE_ENDING = re.compile(r"\r\n|\r")


def canonical_newlines(s):
    """`s` with every line ENDING written as a single "\\n" -- the one newline canonicalisation
    litkb uses when it compares a review's quote with a block's stored text (2026-09-20).

    Measured on the 2026-09-19 corpus: 48.9 % of current-run blocks contain `\\r\\n` and 7 of the
    8 verified spans the project holds cross one, so a byte-exact comparison against the review
    file's bytes made almost every existing verified quote unquotable -- it could only match if
    an LLM writer emitted a raw CR, which nobody has ever observed. The fix is to make the LINE
    ENDING ENCODING canonical on BOTH sides and nothing else: every non-newline byte, its order,
    and the NUMBER of line breaks are preserved exactly, so a match still means the reader did
    not rewrite the paper.

    `\\r\\n` -> `\\n`, `\\r` -> `\\n`, `\\n` -> `\\n`. It is NOT a run collapse: `"a\\r\\n\\r\\nb"`
    becomes `"a\\n\\nb"`, never `"a\\nb"`. Collapsing runs would let a quote silently join two
    paragraphs of the stored block, which is a change of CONTENT, not of encoding.

    The database side of the same rule is `litkb.canonical_newlines(text)` (migration 0026),
    called from SQL through `sql_canonical_newlines` below -- Postgres's own `position()` keeps
    the substring test (the module docstring in review_check.py says why it is not re-implemented
    in Python). The two are bound by
    `qc/test_litkb_review_check.py::test_the_sql_and_python_newline_canonicalisations_agree`,
    which is the ONLY thing that binds them: a function and a regex cannot share a definition.
    """
    # BEGIN guard: a line ending is canonicalised to "\n", and nothing else is normalised
    return None if s is None else _LINE_ENDING.sub("\n", str(s))
    # END guard: a line ending is canonicalised to "\n", and nothing else is normalised


def sql_canonical_newlines(expr):
    """The SQL expression that canonicalises `expr`'s line endings -- the ONE spelling of
    migration 0026's `litkb.canonical_newlines(text)`, so a query that has to compare stored text
    with a quote does not carry its own `replace(replace(...))`.

    `expr` is SQL the caller composed (a column reference such as `b.text`), never a value: a
    value is bound as a parameter by the caller, as everywhere else in litkb.

    WHY A FUNCTION AND NOT A CONSTANT STRING: the same rule is needed inside a migration (the
    0007/0026 `quote_verified` trigger), and a migration is a .sql file that can import nothing
    from Python. Either the migration carries a copy of the expression, or the expression becomes
    a call to what the migration defines. The second is one home; the first is three.

    A database that has not had 0026 applied has no such function and every query built with this
    will error there. That is deliberate: `use.newline_canon_available` is how a caller asks
    first, and `litkb_record_use` refuses (`no-newline-canon`) rather than writing a row the old
    trigger would mark unverified -- see its docstring.
    """
    # BEGIN guard: the SQL line-ending rule is migration 0026's function, not a second copy
    return f"litkb.canonical_newlines({expr})"
    # END guard: the SQL line-ending rule is migration 0026's function, not a second copy


def norm_label(s):
    """A session or agent label with every invisible character removed (None stays None)."""
    # BEGIN guard: labels lose invisible characters (Python)
    return None if s is None else _INVISIBLE.sub("", str(s))
    # END guard: labels lose invisible characters (Python)


def normalize_doi(doi):
    """The canonical DOI (see the module docstring); "" when the value holds no "10."."""
    d = norm_label(doi or "").translate(_ASCII_LOWER)
    i = d.find("10.")
    if i < 0:
        return ""
    # BEGIN guard: a DOI loses its trailing punctuation (Python)
    return _DOI_TAIL.sub("", d[i:])
    # END guard: a DOI loses its trailing punctuation (Python)


def jsonb_safe(obj):
    """`obj` with every NUL character removed from its strings and keys. Postgres jsonb refuses \\u0000, and old
    scanned PDFs carry NULs in their metadata (Bell 1977: Creator 'Acrobat 3.0 Capture Plug-in' + NULs), so every
    JSON document litkb sends goes through this first (Reports/LITKB_EDGE_PRE1990_2026-09-14.md, D-nul)."""
    # BEGIN guard: JSON sent to the database carries no NUL
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    # END guard: JSON sent to the database carries no NUL
    if isinstance(obj, dict):
        return {jsonb_safe(k): jsonb_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonb_safe(v) for v in obj]
    return obj
