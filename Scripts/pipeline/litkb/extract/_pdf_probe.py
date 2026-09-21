"""The page-count probe's CHILD — stdlib and pypdfium2 only, run as a script, never imported by litkb.

:func:`litkb.extract.readiness.probe_pages` runs this file as

    <sys.executable> -P <this file> <pdf>

and reads one JSON object from stdout. Three properties of that command are load-bearing and each
one is here rather than in the parent because the parent cannot enforce them:

* **A SUBPROCESS, because a deadline has to be enforceable.** pdfium is a C library: a page count
  that does not come back is stuck below the Python frame, where no signal, no exception and no
  thread flag reaches it. A worker thread with a timeout returns control to the caller and leaves
  the hung thread running — and a non-daemon one then holds the interpreter open at exit while a
  daemon one keeps a C library alive inside a process that is tearing down. A child process is the
  only bound a caller can actually enforce: ``subprocess.run(timeout=…)`` kills it.

* **``-P``, because the cwd must not reach ``sys.path``.** ``D:\\edmonds-pipeline\\secrets\\`` is a
  directory, and a ``secrets`` entry at the head of ``sys.path`` shadows the stdlib module numpy's
  ``bit_generator`` imports — the failure measured on 2026-09-15 that made
  :mod:`litkb.extract.docling_worker` choose its own cwd. ``-P`` also keeps THIS file's directory
  off the path, which matters next door: ``pipeline/litkb/extract/docling.py`` shadows the
  installed ``docling`` package the same way.

* **NO litkb import, because the parent may be a worktree and the install is MAIN's.** litkb is not
  in the editable install; a child that imported ``litkb`` would resolve it through whatever
  ``PYTHONPATH`` the parent happened to carry, which in a worktree is main's tree. Then a probe run
  from a branch would answer with main's code. This file imports pypdfium2 and the stdlib, so there
  is nothing for a path to get wrong.

WHAT THE ERROR CODES MEAN, measured 2026-09-21 on inputs built in the scratchpad (pypdfium2 5.13.0):

    0-byte file            PdfiumError, FPDF_GetLastError() = 3 (FORMAT)    -> unopenable
    first 1,000 bytes of a real PDF   same, 3 (FORMAT)                      -> unopenable
    a PDF whose /Pages has /Count 0 and no kids
                           PdfiumError, FPDF_GetLastError() = 0 (SUCCESS)   -> zero-pages
    /Encrypt with an /O and /U the empty user password does not authenticate
                           PdfiumError, FPDF_GetLastError() = 4 (PASSWORD)  -> encrypted
    a 3-page PDF           loads, security handler revision -1, len(doc) = 3 -> 3

The SUCCESS row is the one worth stating plainly: pdfium refuses a document that holds no pages and
leaves its error code at SUCCESS, so "the load failed and pdfium reports no error" is read here as
``zero-pages``. If some future pdfium fails that way for a different reason, this call labels it
``zero-pages`` when ``probe-error`` would have been truer — and the CONSEQUENCE is identical,
because every reason in this file is a refusal. The label moves; the fail-closed answer does not.
"""
import json
import sys

#: FPDF_GetLastError() -> the reason this probe reports. The codes are pdfium's, the same table
#: :func:`litkb.extract.inventory._last_error` names them by; the mapping is this module's.
PDFIUM_REASON = {
    0: "zero-pages",    # measured: a document with no pages, refused with the code left at SUCCESS
    1: "unopenable",    # UNKNOWN
    2: "unopenable",    # FILE
    3: "unopenable",    # FORMAT — a truncated, empty or non-PDF body
    4: "encrypted",     # PASSWORD
    5: "encrypted",     # SECURITY — a handler pdfium will not open at all
    6: "unopenable",    # PAGE
}


def classify_load_failure(code):
    """-> the probe reason for a pdfium load that raised, from its error code.

    An unknown or unreadable code is ``probe-error``: a number this table does not know is not a
    number to guess a specific cause from.
    """
    try:
        return PDFIUM_REASON[int(code)]
    except (KeyError, TypeError, ValueError):
        return "probe-error"


def classify_opened(security_revision, pages):
    """-> (pages, None) or (None, reason) for a document that pdfium DID open.

    ``security_revision`` is ``FPDF_GetSecurityHandlerRevision``: ``-1`` on an unencrypted
    document, the handler's revision number on an encrypted one. A PDF encrypted with an OWNER
    password only opens with the empty user password, so this is the branch that catches it, and
    it is a refusal for the same reason the password branch is: the permissions on such a file say
    the owner did not mean it to be extracted, and docling would be making that decision silently.
    """
    try:
        encrypted = int(security_revision) != -1
    except (TypeError, ValueError):
        encrypted = False
    if encrypted:
        return None, "encrypted"
    try:
        n = int(pages)
    except (TypeError, ValueError):
        return None, "probe-error"
    if n <= 0:
        return None, "zero-pages"
    return n, None


def probe(path):
    """-> {"pages": n} or {"reason": …, …}. Never raises."""
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as praw
    except Exception as exc:  # noqa: BLE001 - no pypdfium2 is a probe that cannot answer
        return {"reason": "probe-error", "error": f"{type(exc).__name__}: {exc}"}
    try:
        doc = pdfium.PdfDocument(path)
    except Exception as exc:  # noqa: BLE001
        try:
            code = int(praw.FPDF_GetLastError())
        except Exception:  # noqa: BLE001
            code = None
        return {"reason": classify_load_failure(code), "pdfium_error": code,
                "error": f"{type(exc).__name__}: {exc}"}
    try:
        try:
            rev = praw.FPDF_GetSecurityHandlerRevision(doc.raw)
        except Exception:  # noqa: BLE001
            rev = -1
        pages, reason = classify_opened(rev, len(doc))
    except Exception as exc:  # noqa: BLE001
        return {"reason": "probe-error", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            doc.close()
        except Exception:  # noqa: BLE001
            pass
    return {"pages": pages} if reason is None else {"reason": reason}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1:
        sys.stdout.write(json.dumps({"reason": "probe-error",
                                     "error": "usage: _pdf_probe.py <pdf>"}))
        return 2
    sys.stdout.write(json.dumps(probe(argv[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
