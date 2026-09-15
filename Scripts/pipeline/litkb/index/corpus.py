"""The P7 text corpus: which ``.txt`` extracts are indexed, and how they are decoded.

Stage 5 blocks do not exist for the corpus yet (only the 7 gate papers), so P7 reads the
``.txt`` extracts under ``Literture\\Validation`` directly. This module is the ONE place
that decides membership and decoding, so the gold set, the chunker and the evaluation all
see byte-identical text.

Membership rules (deliberately narrow, stated so a referee can re-derive the list):

* only ``Literture\\Validation\\*.txt`` — ``_litkb_staging`` and ``_quarantine`` are
  admission holding pens, not corpus;
* ``*.raw.txt`` is EXCLUDED. It is a pre-cleaning twin of the same paper; 29 of them exist
  and every one has a plain ``.txt`` sibling (checked), so including them would put two
  near-identical copies of one paper in the index and split its rank;
* a file whose decoded text is shorter than :data:`MIN_CHARS` is EXCLUDED as an empty
  extract. These are image-only scans whose PDF carried no text layer: four of them
  (Hudson 1978, Hwang 1982, Politis 1994, Anderson 1957) extract to a JSTOR cover sheet of
  ~21 words and nothing else. Indexing them would put a cover sheet in the corpus and
  claim the paper is searchable when it is not. They come back when stage 3 OCR runs;
* a file is decoded utf-8 first, then cp1252 (206 of 236 files are cp1252, 30 utf-8).
  The chosen codec is recorded per file so the decode is reproducible.

Text is NOT normalised beyond newline canonicalisation: char offsets in the gold set are
offsets into the string this module returns.
"""
from __future__ import annotations

import hashlib
import os
from typing import Dict, List, Tuple

#: The corpus root. Read-only (Kam's rule); nothing here writes under it.
CORPUS_DIR = os.path.join("D:", os.sep, "edmonds-pipeline", "Literture", "Validation")

#: Tried in order. First codec that decodes the whole file wins.
CODECS = ("utf-8", "cp1252")

#: Below this many decoded characters a ``.txt`` is an empty extract, not a paper.
MIN_CHARS = 2000


def candidate_stems(corpus_dir: str = CORPUS_DIR) -> List[str]:
    """Every ``.txt`` stem, raw twins excluded — before the empty-extract rule."""
    out = []
    for name in os.listdir(corpus_dir):
        if not name.endswith(".txt") or name.endswith(".raw.txt"):
            continue
        out.append(name[: -len(".txt")])
    return sorted(out)


def excluded_stems(corpus_dir: str = CORPUS_DIR) -> List[Tuple[str, int]]:
    """``(stem, n_chars)`` for each candidate dropped by the :data:`MIN_CHARS` rule."""
    out = []
    for stem in candidate_stems(corpus_dir):
        text, _ = read_text(stem, corpus_dir)
        if len(text) < MIN_CHARS:
            out.append((stem, len(text)))
    return out


def stems(corpus_dir: str = CORPUS_DIR) -> List[str]:
    """Sorted corpus stems: raw twins and empty extracts excluded."""
    return [
        s for s in candidate_stems(corpus_dir)
        if len(read_text(s, corpus_dir)[0]) >= MIN_CHARS
    ]


def read_text(stem: str, corpus_dir: str = CORPUS_DIR) -> Tuple[str, str]:
    """Return ``(text, codec)`` for one stem. Newlines canonicalised to ``\\n``.

    Raises ``UnicodeDecodeError`` if no codec in :data:`CODECS` decodes the file — never
    silently replaces bytes, because a replacement character would move every later offset.
    """
    with open(os.path.join(corpus_dir, stem + ".txt"), "rb") as fh:
        raw = fh.read()
    last = None
    for codec in CODECS:
        try:
            text = raw.decode(codec)
        except UnicodeDecodeError as exc:  # pragma: no cover - cp1252 decodes everything
            last = exc
            continue
        return text.replace("\r\n", "\n").replace("\r", "\n"), codec
    raise last  # type: ignore[misc]


def manifest(corpus_dir: str = CORPUS_DIR) -> List[Dict[str, object]]:
    """One row per corpus file: stem, codec, char count, sha256 of the DECODED text.

    The hash is of the decoded, newline-canonicalised string — the exact bytes the chunker
    sees — so a change in the file OR in the decode rule shows up as a different hash.
    """
    rows = []
    for stem in stems(corpus_dir):
        text, codec = read_text(stem, corpus_dir)
        rows.append({
            "stem": stem,
            "codec": codec,
            "n_chars": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
    return rows


def corpus_hash(rows: List[Dict[str, object]]) -> str:
    """A single hash over the manifest — the corpus identity quoted in the report."""
    h = hashlib.sha256()
    for row in rows:
        h.update(("%s\t%s\t%s\n" % (row["stem"], row["codec"], row["sha256"])).encode("utf-8"))
    return h.hexdigest()
