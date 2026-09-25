"""S4.5 decision D59 (integrator-w4 fix round 2): binding must not depend on the launching shell.

`litkb.admit.binding.first_page_text` runs whichever `pdftotext` PATH finds. This machine holds two: Git for Windows'
xpdf 4.00 (first on Git Bash's PATH), whose default text encoding is Latin-1, and Poppler 25.07 (first on
PowerShell's), whose default is UTF-8. The binder reads the page as UTF-8, so under xpdf's default a first author with
a non-ASCII letter reads U+FFFD and check 3 refuses the file — MEASURED on hardening-1's REAL L145 (Gräler) in the
whole-run replay (integrator-w4 §8.3b, Q3; auditor-cand4 N6). The fix: `-enc UTF-8` (`binding.PDFTOTEXT_ENCODING`),
which both binaries accept; and the freeze and the run record `binding.pdftotext_version()`.

THE REAL FILE: `_litkb_staging/filed/Graler_2016_spatio-temporal-interpolation-gstat.pdf` (hardening-1 row L145's work,
bound there by open_access; sha256 pinned below) — COPIED into the test's tmp dir, never read in place for pdftotext's
output. Skipped, named, where it is absent or holds other bytes, and per binary where that binary is not installed.
Each leg puts ONE binary's directory first on PATH (the only way the binder chooses), so the test runs the code path
the ladder runs.
"""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

GRALER_REL = "_litkb_staging/filed/Graler_2016_spatio-temporal-interpolation-gstat.pdf"
#: sha256 of the bytes hardening-1's L145 attempt bound (live `acquisition_attempts.served_sha256` of the open_access
#: attempt 01a0d492-2540-7261-87bd-066ca8d25675, read as litkb_reader by integrator-w4 r2)
GRALER_SHA = "b9f439c51870a436ee7734381927e73bbfc157a802fbdd289c0809cde673ae5b"
#: the work's registry title and first author as that attempt's `detail.binding` records them
GRALER_TITLE = "Spatio-Temporal Interpolation using gstat"
GRALER_AUTHOR = "Gräler"
#: where Git for Windows installs its xpdf (not on a PowerShell PATH, so it is looked for here as well)
GIT_MINGW_BIN = Path(r"C:\Program Files\Git\mingw64\bin")


def _kind(exe):
    """'xpdf' | 'poppler' | None, from the binary's own `-v`: Poppler names itself ("The Poppler Developers") and ALSO
    carries Glyph & Cog's copyright (it is xpdf's fork), so Poppler is asked first; xpdf prints Glyph & Cog's alone."""
    try:
        r = subprocess.run([str(exe), "-v"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (r.stderr + r.stdout).decode("utf-8", "replace")
    if "poppler" in text.lower():
        return "poppler"
    if "Glyph & Cog" in text:
        return "xpdf"
    return None


def _binaries():
    """{kind: pdftotext path} over every PATH directory plus Git for Windows' mingw64/bin — the first of each kind."""
    names = ("pdftotext.exe", "pdftotext") if os.name == "nt" else ("pdftotext",)
    dirs = [Path(d) for d in os.environ.get("PATH", "").split(os.pathsep) if d] + [GIT_MINGW_BIN]
    found = {}
    for d in dirs:
        for n in names:
            p = d / n
            if p.is_file():
                k = _kind(p)
                if k and k not in found:
                    found[k] = p
    return found


BINARIES = _binaries()


@pytest.fixture
def graler(tmp_path):
    from litkb.acquire.store import LITERATURE_ROOT

    src = Path(LITERATURE_ROOT) / GRALER_REL
    if not src.is_file():
        pytest.skip(f"literature corpus file not present: {src}")
    dst = tmp_path / "graler.pdf"
    shutil.copyfile(src, dst)
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    if sha != GRALER_SHA:
        pytest.skip(f"{GRALER_REL} holds other bytes than the ones hardening-1 bound (sha256 {sha[:12]})")
    return dst


@pytest.mark.parametrize("kind", ["xpdf", "poppler"])
def test_d59_a_non_ascii_first_author_binds_under_either_pdftotext(kind, graler, monkeypatch):
    """REAL L145 (Gräler): with the binary of `kind` FIRST on PATH, `pdftotext_version()` names it, page 1 reads
    "Gräler" with no U+FFFD, and `bind_any` binds the file against the work's title and first author. Under xpdf the
    leg also shows it exercises the hazard: the SAME binary at its default encoding prints a Latin-1 byte the binder's
    UTF-8 read turns into U+FFFD (so without `-enc UTF-8` this leg is `binding-failed`)."""
    from litkb.admit import binding

    exe = BINARIES.get(kind)
    if exe is None:
        pytest.skip(f"no {kind} pdftotext on this machine (PATH or {GIT_MINGW_BIN})")
    monkeypatch.setenv("PATH", str(exe.parent) + os.pathsep + os.environ.get("PATH", ""))
    ver = binding.pdftotext_version()
    assert Path(ver["path"]).resolve().parent == exe.parent.resolve(), ver
    assert (ver["version"] or "").startswith("pdftotext version"), ver
    assert ver["encoding"] == binding.PDFTOTEXT_ENCODING == "UTF-8", ver
    if kind == "xpdf":
        raw = graler.parent / "default-enc.txt"
        subprocess.run([str(exe), "-f", "1", "-l", "1", "-layout", str(graler), str(raw)], check=False,
                       capture_output=True, timeout=120)
        assert "Gr\ufffdler" in raw.read_text(encoding="utf-8", errors="replace"), \
            "xpdf's default no longer prints Latin-1: this leg would not exercise D59"
    text = binding.first_page_text(graler)
    assert "Benedikt Gräler" in text and "\ufffd" not in text, [ln for ln in text.splitlines() if "Gr" in ln][:3]
    b = binding.bind_any(graler, [GRALER_TITLE], GRALER_AUTHOR)
    assert (b["verdict"], b["author_near_title"]) == ("bound", True), b


def test_d59_pdftotext_version_names_no_binary_when_none_is_on_path(monkeypatch, tmp_path):
    """CONSTRUCTED: an empty PATH -> path None, version None, the encoding still named (a freeze on a machine
    without pdftotext records that, instead of failing)."""
    from litkb.admit import binding

    monkeypatch.setenv("PATH", str(tmp_path))
    assert binding.pdftotext_version() == {"path": None, "version": None, "encoding": "UTF-8"}
