"""The ONE Python normalisation of DOIs and session/agent labels. The database is the authority
(litkb.norm_identifier and litkb.norm_label, migration 0014); these functions must return exactly what those
return, and qc/test_litkb_p2.py drives both over the shared table qc/testdata/litkb_p2/doi_forms.csv and over
every invisible code point below (referee fixes D1 and D7, Reports/LITKB_P2_REFEREE_2026-09-14.md).

    normalize_doi(" https://www.doi.org/10.1890/0012-9658(1998)079[2032:RFFATD]2.0.CO;2/ ")
        -> "10.1890/0012-9658(1998)079[2032:rffatd]2.0.co;2"
    norm_label("sess-admit ") -> "sess-admit"

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
