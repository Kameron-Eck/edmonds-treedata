"""S4 builder Q2 — the readiness guards: show each one FIRE (CLAUDE.md 3.4c).

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w8 py -3.12 \
        qc/instruments/litkb_s4q2_mutations.py --only S4Q2-1,...

RUN IT THROUGH THIS FILE, not through `litkb_p2_mutations.py`. The rows belong in that one shared
ledger — the per-call-site rule covers the whole package and a second self-check would see half of
it — but S4 has THREE builders adding row files at once (`litkb_s4_mutations.py`,
this one, `litkb_s4r_mutations.py`), and a `_register_s4q2()` call appended to the end of
`litkb_p2_mutations.py` by each of them is a merge conflict in a file none of them owns. So this
module registers ITSELF into the ledger and delegates to the ledger's own `main()`: same edit,
same whole test set, same baselines before and after, same sha256 restore proof, and no shared
file touched. The one-line hook in `litkb_p2_mutations.py` is the merge's to add, the way
`_register_s3a2()` is there today.

THE ONE SHARED FILE THIS BRANCH DID TOUCH, and why, so a reviewer does not have to find it: row
**T20** in `litkb_p2_mutations.py` targeted `OCR_BIND_MAX_PAGES = 400` in `admit/binding.py`. S4
gave the cap one home in `litkb/config.py` (`PAGE_CAP_DEFAULT`), because binding and extraction
were about to answer "is this too big?" from two constants. The row moved with the constant; the
guard, the claim and the test set are unchanged.

THE BASELINE. Every row here runs `qc/test_litkb_readiness.py` and nothing else. That file has no
skips, no database, no GPU and no corpus on purpose: the harness counts a baseline with a SKIP in
it as a failed baseline, and a row measured against a red baseline reports FIRED whatever the
mutation did (the P8 incident recorded in `litkb_p2_mutations.COPY_FILES`).

WHAT EACH ROW IS FOR:

  * **S4Q2-1 is the fail-open hole itself**, reinstated exactly: the old
    ``n = (info or pdf_info(pdf_path)).get("Pages") or ""`` / ``if n.isdigit() and int(n) > cap``.
    It is the only row here that restores real historical code rather than breaking new code, and
    it is the one the brief names: a PDF whose page count cannot be read is handed to OCR
    uncapped, which is the state `admit/binding.py` was in until today.
  * **S4Q2-2 and S4Q2-3 are the probe's two halves.** -2 removes the answer-or-raise guard, so
    `probe_pages` falls off the end and returns `None` — the sentinel the module exists to not
    have, because `None` is the shape a caller forgets to check. -3 removes the closed-set check
    in `ProbeFailed`, so a refusal can carry any word at all and no reader can switch on it.
  * **S4Q2-4 empties the cap**, and it is a separate row from -1 because they are different call
    sites: -1 is binding deciding whether to ASK, -4 is `cap_check` deciding the answer.
  * **S4Q2-5 is the VRAM kill.** Unknown free VRAM becomes "assume it is free", which is the one
    reading that is certainly wrong: a machine with no NVIDIA driver and a card that is already
    full look identical to a policy that guesses, and only one of them survives CUDA.
  * **S4Q2-6 unbounds the CPU fallback**, so a 700-page scan is started on the CPU at 0.0689
    pages/s — a job that a timeout kills three hours later instead of a residue named up front.
  * **S4Q2-7 is `has_text_layer` again, in a new coat**: the file-level share becomes "any page
    needs OCR", so `Abdulkader_2020` — 62 pages, 18,064 blocks, fully extracted — is a scan and
    goes back to the GPU. The share IS the classifier; one page is not.
  * **S4Q2-8 restores the live rule** `any(current_run_id) => extracted`
    (`litkb.mcp.server._work`, `litkb.hunt.look_up`): a run with zero canonical blocks reads
    `extracted`, which is how a scan and a broken conversion both come back readable with
    nothing in them.
  * **S4Q2-9 drops the partial-page threshold**, so a `partial` page nothing covered is called
    read.
  * **S4Q2-10 makes a missing nvidia-smi a huge number** instead of `None`.
  * **S4Q2-11 removes the probe's deadline**, which is the hostile-PDF case: pdfium is a C
    library and a page count that never returns cannot be interrupted from Python, so without the
    subprocess timeout the worker waits for it forever.
"""
import importlib.util
import pathlib
import sys

PKG = "pipeline/litkb"
TESTS = ["qc/test_litkb_readiness.py"]
IDS = [f"S4Q2-{i}" for i in range(1, 12)]

#: The fail-closed guard, as it stands, and the fail-OPEN code it replaced (git d9df4e2,
#: `litkb.admit.binding.ocr_first_pages`). S4Q2-1 puts the second back.
_FAILCLOSED = """    # BEGIN guard: a page count that cannot be read refuses the OCR, never passes it
    try:
        n_pages = readiness.probe_pages(pdf_path)
    except readiness.ProbeFailed:
        return refuse("page-probe-failed")
    if readiness.cap_check(n_pages):
        return refuse("over-page-cap")
    # END guard: a page count that cannot be read refuses the OCR, never passes it
"""
_FAILOPEN = """    n = (pdf_info(pdf_path)).get("Pages") or ""
    if n.isdigit() and int(n) > OCR_BIND_MAX_PAGES:
        return refuse("over-page-cap")
"""


def register(block, replace, site):
    del site                                   # this leg targets no helper in HELPERS
    replace("S4Q2-1", f"{PKG}/admit/binding.py", _FAILCLOSED, _FAILOPEN,
            "the fail-OPEN cap is back: the page count comes from poppler's pdfinfo, which "
            "returns {} when poppler is absent or the file is damaged, and the guard refuses only "
            "when the count IS a number — so a PDF whose page count cannot be read goes to OCR "
            "uncapped, which is exactly the document least likely to survive it", tests=TESTS)
    block("S4Q2-2", f"{PKG}/extract/readiness.py",
          "guard: the page probe answers with a count or with a reason, never with neither",
          "probe_pages returns None: the sentinel the module exists to not have, and the shape a "
          "caller forgets to check — which is how the admit-time cap came to fall through on an "
          "unreadable count in the first place", tests=TESTS)
    block("S4Q2-3", f"{PKG}/extract/readiness.py",
          "guard: a probe failure carries a reason out of the closed set",
          "a refusal can carry any word at all: `ProbeFailed('looks-fine-to-me')` is accepted and "
          "no reader can switch on the reason, so the residue classes stop being a vocabulary",
          tests=TESTS)
    block("S4Q2-4", f"{PKG}/extract/readiness.py",
          "guard: the cap refuses a count it cannot read, and never passes one",
          "cap_check answers None for everything, including a 10,000-page book and a page count "
          "that is not a number: the cap is gone at the site that decides the answer",
          tests=TESTS)
    replace("S4Q2-5", f"{PKG}/extract/readiness.py",
            "    if isinstance(free_mib, int) and not isinstance(free_mib, bool) \\\n"
            "            and free_mib >= OCR_NEED_MIB + VRAM_MARGIN_MIB:\n",
            "    if free_mib is None or free_mib >= OCR_NEED_MIB + VRAM_MARGIN_MIB:\n",
            "unknown free VRAM becomes 'assume it is free': a machine with no NVIDIA driver and a "
            "card that is already full are the same input to this policy, and it sends both to "
            "cuda", tests=TESTS)
    replace("S4Q2-6", f"{PKG}/extract/readiness.py",
            "    if n <= CPU_OCR_MAX_PAGES:\n        return (\"run\", \"cpu\")\n",
            "    if True:\n        return (\"run\", \"cpu\")\n",
            "the CPU fallback is unbounded: a 700-page scan is started at 0.0689 pages/s and "
            "killed by a timeout ~2.8 hours later, instead of being named a residue up front",
            tests=TESTS)
    replace("S4Q2-7", f"{PKG}/extract/readiness.py",
            "    return bool(ocr) and (ocr / len(rows)) >= SCAN_FILE_FRAC\n",
            "    return bool(ocr)\n",
            "`has_text_layer` again in a new coat: ANY page needing OCR makes the file a scan, so "
            "Abdulkader_2020 — 62 pages, 18,064 blocks, fully extracted, 13 pages in the "
            "OCR-needing classes — is a scan and goes back to the GPU", tests=TESTS)
    replace("S4Q2-8", f"{PKG}/extract/readiness.py",
            "    if n > 0:\n        return \"extracted\"\n",
            "    if n >= 0:\n        return \"extracted\"\n",
            "the live rule is back — `any(current_run_id) => extracted` "
            "(litkb.mcp.server._work, litkb.hunt.look_up): a run that produced zero "
            "canonical blocks reads `extracted`, so a "
            "scan nobody OCR'd and a conversion that failed are both readable with nothing in them",
            tests=TESTS)
    replace("S4Q2-9", f"{PKG}/extract/readiness.py",
            "            return float(coverage_share) < PARTIAL_COVERAGE_MIN\n",
            "            return False\n",
            "the partial-page threshold is gone: a page with a raster over it and a native layer "
            "the reconciliation could not cover is called read, and the one class where coverage "
            "is the only evidence stops being asked", tests=TESTS)
    replace("S4Q2-10", f"{PKG}/extract/readiness.py",
            "    except (OSError, subprocess.TimeoutExpired):\n        return None\n",
            "    except (OSError, subprocess.TimeoutExpired):\n        return 999999\n",
            "a machine with no nvidia-smi reports 999,999 MiB free instead of UNKNOWN, and every "
            "OCR job on it is dispatched to a CUDA device that is not there", tests=TESTS)
    replace("S4Q2-11", f"{PKG}/extract/readiness.py",
            "                              timeout=PROBE_TIMEOUT_S if timeout is None "
            "else float(timeout))\n",
            "                              timeout=None)\n",
            "the probe has no deadline: pdfium is a C library, a page count that never returns "
            "cannot be interrupted from Python, and the worker waits for a hostile PDF forever",
            tests=TESTS)


def _ledger():
    here = pathlib.Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("litkb_p2_mutations",
                                                  here / "litkb_p2_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("litkb_p2_mutations", mod)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    L = _ledger()
    if not any(m["id"] in IDS for m in L.M):       # the merge may already have hooked this file in
        register(L.block, L.replace, L.site)
    argv = sys.argv[1:]
    if not any(a.startswith("--only") for a in argv) and "--sites" not in argv:
        argv = ["--only", ",".join(IDS), *argv]
    raise SystemExit(L.main(argv))
