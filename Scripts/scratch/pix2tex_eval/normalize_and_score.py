"""Normalization + agreement scoring, shared between the gold (20) and bulk (200) sets.

Equivalence rule (stated explicitly, applied identically both places):
 1. Strip ALL whitespace.
 2. Drop pure-spacing macros: \\, \\; \\: \\! \\quad \\qquad \\hspace{...} \\thinspace.
 3. Drop \\left / \\right (keep the following delimiter character).
 4. Collapse \\mathrm{X}, \\mbox{X}, \\text{X}, \\operatorname{X}, \\operatorname*{X} to bare X
    (their argument), since these differ by decoder house-style, not math content.
 5. Drop a single trailing parenthesised equation-number tag, e.g. "...(59)" or "...(4.3)",
    matched only at the very end of the string, since one decoder including a page's printed
    tag and the other omitting it is a crop-boundary artifact, not a content disagreement.
 6. Collapse repeated/degenerate brace groups {{X}} -> X (pix2tex's array/stackrel wrapping
    idiom) so its layout-heavy rendering compares fairly against CodeFormula's flatter output.
After normalization: AGREE iff the two strings are byte-identical. This is deliberately
STRICT beyond step 6 -- a single wrong subscript, dropped term, or swapped accent (\\hat vs
\\bar) still counts as a disagreement, because those are exactly the errors this evaluation
exists to catch.
"""
import re


def normalize(latex):
    if latex is None:
        return None
    s = latex
    # drop spacing macros, including a bare control-space ("\ ", backslash immediately
    # followed by whitespace -- how docling's space-joined tokenizer renders one)
    s = re.sub(r"\\(,|;|:|!|quad|qquad|thinspace|hspace\{[^}]*\})", "", s)
    s = re.sub(r"\\(?=\s)", "", s)
    # left/right and all big-delimiter sizing macros -> bare delimiter
    s = re.sub(r"\\(left|right|[Bb]ig{1,2}[lr]?)\s*", "", s)
    # collapse text-role wrappers to their argument (one level, applied repeatedly);
    # CodeFormula's tokenizer sometimes leaves a space between the macro name and its brace
    for _ in range(4):
        s = re.sub(r"\\(mathrm|mbox|text|operatorname\*?)\s*\{([^{}]*)\}", r"\2", s)
    # strip ALL remaining brace grouping -- after the macro/wrapper collapse above, any brace
    # left is pure LaTeX grouping syntax with no surviving semantic role in these equations
    # (docling and pix2tex disagree constantly on whether e.g. a single \frac argument or a
    # \mathcal target is wrapped), so drop them rather than let grouping style masquerade as
    # a content disagreement.
    s = s.replace("{", "").replace("}", "")
    # LaTeX tie (~) is a fixed space, not content
    s = s.replace("~", "")
    # strip all remaining whitespace
    s = re.sub(r"\s+", "", s)
    # \colon -> : (docling and pix2tex disagree on spelling, never on meaning); fold the two
    # spellings of arg-min into one now that whitespace/braces are gone
    s = s.replace(r"\colon", ":")
    s = s.replace(r"\arg\min", r"\argmin")
    # drop a single trailing (N) or (d.d) tag
    s = re.sub(r"\([0-9]+(\.[0-9]+)?\)$", "", s)
    return s


def agree(a, b):
    na, nb = normalize(a), normalize(b)
    if na is None or nb is None:
        return None
    return na == nb
