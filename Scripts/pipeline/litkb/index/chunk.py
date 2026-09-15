"""Structure-aware chunking of the ``.txt`` extracts (design §7 stage 7).

Design constraint: "structure-aware chunks; embed". What structure a flat ``.txt`` extract
still carries is paragraph breaks (a blank line) and, for tables and displayed equations,
a run of short lines dense in digits or maths operators. So:

* **paragraph-bounded** — a chunk never starts or ends inside a paragraph; paragraphs are
  the atoms and are packed until the token budget is reached;
* **~300-500 tokens** — tokens estimated by whitespace words (a model-free proxy; the real
  tokenizer belongs to the model, and the chunker must not depend on which model runs);
* **15% overlap** — the packer backs up by whole paragraphs until it has re-covered at
  least 15% of the emitted chunk's tokens;
* **tables and equations kept whole** — a paragraph that :func:`is_structural` calls
  structural is never SPLIT across chunks. If it is substantial on its own
  (``min_structural_tokens``) it becomes its own chunk; if it is a two-line displayed
  equation it is packed into the surrounding prose chunk instead of being isolated. The
  first draft isolated every one, and on the maths-heavy papers (Duval 2009, Nordman 2004)
  that put ~53% of chunks at ~20 tokens each — too small to embed usefully. This is a
  heuristic on flat text, not a parse;
* **char offsets into the decoded source** — every chunk carries ``char_start``/``char_end``
  so a gold passage anchored on the source can be mapped to the chunks that contain it.

A paragraph longer than ``max_tokens`` on its own is emitted alone (never split mid-word);
it is the one case where the size band is exceeded, and the report counts them.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Sequence

#: A blank line, possibly with trailing spaces, is a paragraph break.
_PARA_SPLIT = re.compile(r"\n[ \t]*\n+")

_MATH_CHARS = set("=+−±≤≥∑∫√αβλμσφ∂<>|")


def n_tokens(text: str) -> int:
    """Whitespace-word count — the model-free token proxy used for the size band."""
    return len(text.split())


def paragraphs(text: str) -> List[Dict[str, object]]:
    """Split into paragraphs, keeping each one's char span in the source string."""
    out: List[Dict[str, object]] = []
    pos = 0
    for piece in _PARA_SPLIT.split(text):
        start = text.find(piece, pos) if piece else pos
        if piece.strip():
            # trim leading/trailing whitespace but keep the offsets honest
            lead = len(piece) - len(piece.lstrip())
            trail = len(piece) - len(piece.rstrip())
            out.append({
                "text": piece[lead: len(piece) - trail],
                "char_start": start + lead,
                "char_end": start + len(piece) - trail,
            })
        pos = start + len(piece)
    return out


def is_structural(para: str) -> bool:
    """True for a paragraph that looks like a table, a caption or a displayed equation.

    Three signals, any of which is enough, chosen because they survive a flat text dump:

    * a caption opener (``Table 3``, ``Fig. 2``, ``Figure 4``, ``Eq. (7)``);
    * a numeric block — at least two lines, and over 30% of the non-space characters are
      digits or column separators, which is what a stripped table looks like;
    * a maths block — at least 15% of characters are maths operators or Greek letters and
      the paragraph is short (under 60 words), which is what a displayed equation looks
      like once its layout is gone.
    """
    stripped = para.strip()
    if not stripped:
        return False
    if re.match(r"^(table|fig(ure|\.)?|eq(uation|\.)?|algorithm)\s*\.?\s*\d", stripped, re.I):
        return True
    dense = [c for c in stripped if not c.isspace()]
    if not dense:
        return False
    lines = [ln for ln in stripped.split("\n") if ln.strip()]
    digits = sum(1 for c in dense if c.isdigit() or c in "|\t")
    if len(lines) >= 2 and digits / len(dense) > 0.30:
        return True
    maths = sum(1 for c in dense if c in _MATH_CHARS)
    if n_tokens(stripped) < 60 and maths / len(dense) >= 0.15:
        return True
    return False


def chunk_text(
    text: str,
    stem: str,
    min_tokens: int = 300,
    max_tokens: int = 500,
    overlap: float = 0.15,
    min_structural_tokens: int = 50,
) -> List[Dict[str, object]]:
    """Chunk one document. Returns chunk dicts with id, stem, text, offsets, token count.

    ``min_tokens`` is the target at which a prose chunk is closed; ``max_tokens`` is the
    ceiling a chunk is never packed past (a single oversized paragraph excepted).
    """
    paras = paragraphs(text)
    chunks: List[Dict[str, object]] = []

    def emit(items: Sequence[Dict[str, object]], kind: str) -> None:
        if not items:
            return
        start = int(items[0]["char_start"])
        end = int(items[-1]["char_end"])
        body = text[start:end]
        chunks.append({
            "chunk_id": "%s#%06d" % (stem, start),
            "stem": stem,
            "kind": kind,
            "char_start": start,
            "char_end": end,
            "n_tokens": n_tokens(body),
            "text": body,
        })

    buf: List[Dict[str, object]] = []
    buf_tokens = 0
    for para in paras:
        body = str(para["text"])
        tok = n_tokens(body)
        if is_structural(body) and tok >= min_structural_tokens:
            emit(buf, "prose")
            buf, buf_tokens = [], 0
            emit([para], "structural")
            continue
        if buf and buf_tokens + tok > max_tokens:
            emit(buf, "prose")
            # overlap: back up over whole paragraphs until >= overlap of the emitted chunk
            want = overlap * buf_tokens
            tail: List[Dict[str, object]] = []
            got = 0
            for prev in reversed(buf):
                if got >= want:
                    break
                tail.insert(0, prev)
                got += n_tokens(str(prev["text"]))
            # never let the carried tail alone exceed the ceiling
            while tail and got + tok > max_tokens:
                got -= n_tokens(str(tail[0]["text"]))
                tail.pop(0)
            buf, buf_tokens = list(tail), got
        buf.append(para)
        buf_tokens += tok
        if buf_tokens >= min_tokens:
            emit(buf, "prose")
            want = overlap * buf_tokens
            tail, got = [], 0
            for prev in reversed(buf):
                if got >= want:
                    break
                tail.insert(0, prev)
                got += n_tokens(str(prev["text"]))
            buf, buf_tokens = list(tail), got
    emit(buf, "prose")

    # A chunk emitted as the overlap tail of the previous one, with nothing added, is a
    # duplicate: drop it.
    seen = set()
    unique = []
    for ch in chunks:
        key = (ch["char_start"], ch["char_end"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(ch)
    return unique


def build_corpus_chunks(stems_: Iterable[str], reader) -> List[Dict[str, object]]:
    """Chunk every stem. ``reader(stem) -> (text, codec)``; see :mod:`litkb.index.corpus`."""
    out: List[Dict[str, object]] = []
    for stem in stems_:
        text, _codec = reader(stem)
        out.extend(chunk_text(text, stem))
    return out


def chunks_covering(chunks: Sequence[Dict[str, object]], stem: str, start: int, end: int) -> List[str]:
    """Chunk ids whose span OVERLAPS ``[start, end)`` in ``stem``.

    This is how a gold passage anchored on source char offsets becomes a set of correct
    chunks. Overlap, not containment: an anchor that straddles a chunk boundary has more
    than one correct chunk, and both count as a hit (the report counts the straddlers).
    """
    return [
        str(c["chunk_id"])
        for c in chunks
        if c["stem"] == stem and int(c["char_start"]) < end and int(c["char_end"]) > start
    ]


def chunks_hash(chunks: Sequence[Dict[str, object]]) -> str:
    """Identity of a chunk set — id + span, in order."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(("%s\t%s\t%s\n" % (c["chunk_id"], c["char_start"], c["char_end"])).encode("utf-8"))
    return h.hexdigest()
