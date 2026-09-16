"""litkb stage 0 — show every threshold and guard FIRE (CLAUDE.md §3.4c).

A gate that has never fired is not known to work. For each row below: change ONE thing in
the real source, run the whole stage-0 test set, record whether it failed, restore the file
byte-for-byte and verify the restore by sha256. Before and after every mutation the
unmutated set must pass.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_inventory_mutations.py
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_inventory_mutations.py --only T4

The corpus-backed rows (the twelve-file gate, the census) need ``Literture\\`` mounted; the
rest do not. A row that does not fire exits 1 and names itself — including the deliberate
no-op self-check ``--plant-equivalent``, which must be reported DID NOT FIRE.

Exit 0 only if every chosen row fired and both baselines passed.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
TARGET = SCRIPTS / "pipeline" / "litkb" / "extract" / "inventory.py"
TESTS = "qc/test_litkb_inventory.py"

#: id -> (what it proves, old text, new text)
MUTATIONS = {
    "T1": ("CHARS_TRACE lowered: a stamped scan page reads as content, not image-only",
           "CHARS_TRACE = 100        #", "CHARS_TRACE = 10        #"),
    "T2": ("CHARS_TRACE raised over the partial band: cover stamps read as image-only",
           "CHARS_TRACE = 100        #", "CHARS_TRACE = 300        #"),
    "T3": ("CHARS_BODY lowered: a scanned table page reads as a finished text page",
           "CHARS_BODY = 400         #", "CHARS_BODY = 150         #"),
    "T4": ("IMAGE_COVER raised: a strip-cut scan (Ogata, 0.51) stops being a scan",
           "IMAGE_COVER = 0.25       #", "IMAGE_COVER = 0.95       #"),
    "T5": ("IMAGE_COVER lowered: any page with a small figure reads as image-covered",
           "IMAGE_COVER = 0.25       #", "IMAGE_COVER = 0.01       #"),
    # ── the ±20 % band, one row per threshold per side ──────────────────────────────────
    # T1..T5 move the thresholds far (0.01, 0.95, 10, 300) — outside the band the corpus
    # actually lives in. The referee replayed classify_page over all 5,038 pages at each
    # constant ±20 % and measured that the twelve-file gate caught ONE of the six moves
    # (Reports/LITKB_INVENTORY_REFEREE_2026-09-15.md §3). These six rows are that band, and
    # BOUNDARY_PINS in the test file is what they fire on.
    "B1": ("CHARS_TRACE -20% (100 -> 80): no CORPUS page changes class, so only the "
           "synthetic unit row (99, 0.90) -> image-only can catch it",
           "CHARS_TRACE = 100        #", "CHARS_TRACE = 80        #"),
    "B2": ("CHARS_TRACE +20% (100 -> 120): Guo p6, a 117-character figure caption, "
           "drops from partial to image-only",
           "CHARS_TRACE = 100        #", "CHARS_TRACE = 120        #"),
    "B3": ("CHARS_BODY -20% (400 -> 320): Gros p19 (390 chars) reads as a finished text "
           "page and leaves the OCR queue",
           "CHARS_BODY = 400         #", "CHARS_BODY = 320         #"),
    "B4": ("CHARS_BODY +20% (400 -> 480): Parisi p22 (402 chars) reads partial and "
           "enters the OCR queue",
           "CHARS_BODY = 400         #", "CHARS_BODY = 480         #"),
    "B5": ("IMAGE_COVER -20% (0.25 -> 0.20): remotesensing-14-05911 p25 (0.2242) reads "
           "partial",
           "IMAGE_COVER = 0.25       #", "IMAGE_COVER = 0.20       #"),
    "B6": ("IMAGE_COVER +20% (0.25 -> 0.30): Ogata p24 (0.2764, a real scanned references "
           "page) becomes `empty` and silently leaves the OCR backlog",
           "IMAGE_COVER = 0.25       #", "IMAGE_COVER = 0.30       #"),
    "T6": ("SCAN_FILE_FRAC raised: a whole scan is priced as a mixed native document",
           "SCAN_FILE_FRAC = 0.5     #", "SCAN_FILE_FRAC = 0.99     #"),
    "T7": ("COVER_MIN_FIELDS raised: a real JSTOR cover page is never recognised",
           "COVER_MIN_FIELDS = 2     #", "COVER_MIN_FIELDS = 5     #"),
    "T8": ("COVER_MAX_CHARS cut: the IMS stamp is no longer seen as boilerplate-only",
           "COVER_MAX_CHARS = 200    #", "COVER_MAX_CHARS = 10    #"),
    "I1": ("the image probe removed: a rasterised page reads as `empty`, not `image-only`",
           "for obj in page.get_objects(filter=[praw.FPDF_PAGEOBJ_IMAGE], max_depth=8):",
           "for obj in []:"),
    "I2": ("nested images no longer reached: a page whose raster sits in a form XObject "
           "stops being image-covered",
           "max_depth=8):", "max_depth=0):"),
    "U1": ("a document that will not open is routed `native` instead of `unreadable`",
           'rec.update(pages=0, page_detail=[], route="unreadable",',
           'rec.update(pages=0, page_detail=[], route="native",'),
    "C1": ("the cover-sheet host marker dropped: a cover page routes native",
           "if not any(m in low for m in COVER_HOST_MARKERS):\n        return False\n    return sum",
           "if False:\n        return False\n    return 0 * sum"),
    "F1": ("the §7.1 cropbox origin dropped: dx/dy become 0 and the frame census breaks",
           '"dx": round(crop[0] - media[0], 4), "dy": round(media[3] - crop[3], 4),',
           '"dx": 0.0, "dy": 0.0,'),
    "R1": ("rotation reported as 0: the census loses its seven rotated pages",
           '"rotation": int(praw.FPDFPage_GetRotation(page.raw)),',
           '"rotation": 0,'),
    "S1": ("the resume key drops the path: a second copy of a file is never recorded",
           "    return (sha256, str(path), ph)", "    return (sha256, ph)"),
    "S2": ("the resume key drops the params hash: a moved threshold is never re-probed",
           "    return (sha256, str(path), ph)", "    return (sha256, str(path))"),
    # ── the frozen census ───────────────────────────────────────────────────────────────
    # The pinned corpus numbers were measured over a NAMED list of 241 files
    # (phase4/qc/litkb_inventory_census.sha256). This row removes the list and lets the
    # census walk the corpus again, which is what it used to do and how it came to read
    # `assert 246 == 224` from acquisition alone (Reports/LITKB_P4_MERGE_2026-09-15.md).
    # Needs the corpus mounted, and needs it to have GROWN since the freeze — if the corpus
    # is ever byte-identical to the census this row cannot fire, and that is honest: there
    # would be nothing for the freeze to protect against.
    "X1": ("the census reader falls back to walking the corpus: the pinned census is "
           "re-measured over today's files and stops being a measurement of anything",
           "files=census_pdfs(root, census))", "files=None)"),
}

#: A deliberate no-op, for the harness's own kill: it must be reported DID NOT FIRE.
EQUIVALENT = ("PLANT", ("a comment reworded — nothing can fail",
                        "# ── the run ─", "# ── the run (comment reworded) ─"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pytest():
    r = subprocess.run([sys.executable, "-m", "pytest", TESTS, "-q", "--no-header", "-rf"],
                       cwd=SCRIPTS, capture_output=True, text=True, errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_one(mid, what, old, new):
    text = TARGET.read_text(encoding="utf-8")
    before = sha(TARGET)
    if text.count(old) != 1:
        raise SystemExit(f"{mid}: the target text occurs {text.count(old)} times, not once")
    TARGET.write_text(text.replace(old, new), encoding="utf-8")
    try:
        rc, out = pytest()
    finally:
        TARGET.write_text(text, encoding="utf-8")
    ok = sha(TARGET) == before
    fired = rc != 0
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    print(f"  {mid:<6} {'FIRED' if fired else 'DID NOT FIRE':<13} {tail}")
    # WHICH test failed, not just how many: a row is only a guard if the failure it causes
    # names the thing that moved, and that is unreadable from the count line alone.
    failed = sorted({ln.split(" ")[1].split("::")[-1]
                     for ln in out.splitlines() if ln.startswith("FAILED ")})
    for name in failed:
        print(f"         failed: {name}")
    print(f"         restored inventory.py sha256 {before[:16]}... match: {ok}")
    if not ok:
        raise SystemExit(f"{mid}: inventory.py was not restored byte-for-byte")
    print(f"         {what}")
    return fired


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--plant-equivalent", action="store_true",
                    help="run the deliberate no-op; it must NOT fire")
    args = ap.parse_args(argv)

    chosen = [m.strip() for m in args.only.split(",") if m.strip()] or list(MUTATIONS)
    print("baseline (unmutated):")
    rc, out = pytest()
    print("  " + (out.strip().splitlines() or [""])[-1])
    if rc != 0:
        raise SystemExit("the unmutated set must pass before any mutation is run")

    results = {}
    print("mutations:")
    for mid in chosen:
        what, old, new = MUTATIONS[mid]
        results[mid] = run_one(mid, what, old, new)
    if args.plant_equivalent:
        pid, (what, old, new) = EQUIVALENT
        results[pid] = run_one(pid, what, old, new)

    print("baseline (after):")
    rc, out = pytest()
    print("  " + (out.strip().splitlines() or [""])[-1])
    if rc != 0:
        raise SystemExit("the unmutated set must pass after the mutations")

    bad = [m for m in chosen if not results[m]]
    if args.plant_equivalent and results.get("PLANT"):
        bad.append("PLANT (a no-op must not fire)")
    print(f"\n{len(chosen) - len([b for b in bad if b in chosen])}/{len(chosen)} fired")
    if bad:
        print("DID NOT FIRE: " + ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
