"""litkb P2 — show every admission and acquisition guard FIRE (CLAUDE.md 3.4c: a kill must be shown to fire on a
known-bad input before it counts).

For every mutation: weaken ONE guard in the real source, run the WHOLE P2 test set (qc/test_litkb_p2.py and
qc/test_litkb_annas.py, live tests deselected), record whether it failed, restore the file byte-for-byte and
check the restore by sha256. Before and after all mutations the unmutated set must pass with nothing skipped.
Everything runs against litkb_test (the suite resets and migrates it from the files on disk); nothing here
touches the litkb database, and no mutation touches cluster grants.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p2_mutations.py [--only ID,...]

Exit 0 only if every chosen mutation fired and both baselines passed.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
MIG = "pipeline/litkb/db/migrations"
PKG = "pipeline/litkb"
TESTS = ["qc/test_litkb_p2.py", "qc/test_litkb_annas.py"]
TESTS_P1P2 = ["qc/test_litkb_p1.py", *TESTS]
MIG14 = f"{MIG}/0014_referee_p2_fixes.sql"

M = []


def block(id_, file, marker, what):
    M.append(dict(id=id_, kind="block", file=file, marker=marker, what=what))


def replace(id_, file, old, new, what, tests=None):
    M.append(dict(id=id_, kind="replace", file=file, old=old, new=new, what=what, **({"tests": tests} if tests else {})))


# ── the database (migration 0013, and the live 0003/0009 texts P2 relies on) ──
block("A1", f"{MIG}/0013_admission.sql", "guard: check 1 the work is the registry record",
      "check 1: stop requiring the work's title and year to be the registry record's")
block("A2", f"{MIG}/0013_admission.sql", "guard: check 1 claimed record matches the registry",
      "check 1: stop comparing the claimed title ratio and first author")
block("A3", f"{MIG}/0013_admission.sql", "guard: check 1 year rule", "check 1: drop the year rule")
replace("A3b", f"{MIG}/0013_admission.sql", "ELSIF abs(v_cy - v_ry) = 1 AND", "ELSIF abs(v_cy - v_ry) <= 2 AND",
        "check 1: widen +/-1 to +/-2 years")
block("A4", f"{MIG}/0013_admission.sql", "guard: check 1 a registry identifier is confirmed",
      "check 1: a registry admission with no registry-confirmed identifier passes")
block("A5", MIG14, "guard: check 3 no text layer waits for OCR",
      "check 3: a file with no text layer is not binding-pending")
block("A6", MIG14, "guard: check 3 binding evidence",
      "check 3: the database stops checking the binding evidence")
block("A7", MIG14, "guard: check 4 a manual admission carries a bound file",
      "check 4: a manual admission without a bound file proceeds")
block("A8", MIG14, "guard: check 2 identifier lock",
      "check 2: no advisory lock on the normalised identifier")
block("A9", MIG14, "guard: check 2 identifier lookup",
      "check 2: no lookup of an already-admitted identifier")
block("A10", MIG14, "guard: check 2 title duplicate review",
      "check 2: no title-similarity review for a work without identifiers")
replace("A11", f"{MIG}/0013_admission.sql", "AS $$ SELECT 0.70::real $$;", "AS $$ SELECT 1.01::real $$;",
        "check 2: the calibrated threshold replaced by one no title can reach")
block("A12", MIG14, "guard: admit presents the workstream token", "admit without the token check")
block("A13", MIG14, "guard: approve_admission presents the workstream token",
      "approve_admission without the token check")
block("A14", f"{MIG}/0013_admission.sql", "guard: attach_file presents the workstream token",
      "attach_file without the token check")
block("A15", MIG14, "guard: the candidate belongs to the admitting workstream",
      "admit takes another workstream's candidate")
block("A16", f"{MIG}/0013_admission.sql", "guard: attach_file sha256 dedupe", "attach_file without the sha256 lookup")
block("A17", f"{MIG}/0013_admission.sql", "guard: attach_file binding", "attach_file without the binding check")
block("A18", f"{MIG}/0013_admission.sql", "guard: a fact chain enters main only through admission approval",
      "promote_prepare may carry an unapproved work/identifier/file chain")
block("A19", MIG14, "guard: approval moves main's pointer only from nothing",
      "approve_admission moves no pointer")
block("A20", f"{MIG}/0013_admission.sql", "guard: writer executes the admission functions",
      "the writer loses EXECUTE on admit / approve_admission / attach_file")
# A5-A10, A12, A13, A15, A19, A21, A22 target 0014 since the P2 referee's fixes: 0014 REPLACES _check_binding, admit,
# approve_admission, norm_identifier and the 0009 label constraints, so the 0013/0009/0003 texts are dead code.
replace("A21", MIG14,
        "\n      AND litkb.norm_label(approver_session) <> litkb.norm_label(admitter_session)));",
        "));", "the approver session <> admitter session clause dropped (live constraint, 0014)")
replace("A22", MIG14,
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')", "'', '')",
        "DOIs no longer lower-cased by norm_identifier (live 0014 text)")
# ── Python ──
# B1/B1b target verdict() since the D2 fix: the binding verdict now reads author_near_title
replace("B1", f"{PKG}/admit/binding.py", "if ratio >= BIND_RATIO and author_near_title:", "if True:",
        "binding: every file binds")
replace("B1b", f"{PKG}/admit/binding.py", "if ratio >= BIND_RATIO and author_near_title:", "if ratio >= BIND_RATIO:",
        "binding: the first author is not required")
replace("B2", f"{PKG}/admit/resolver.py", "if abs(cy - wy) == 1:", "if abs(cy - wy) <= 2:",
        "resolver: +/-2 years accepted")
block("B3", f"{PKG}/acquire/store.py", "guard: store writes only into staging or quarantine",
      "store: writes allowed into topic folders")
block("B4", f"{PKG}/acquire/store.py", "guard: store never overwrites", "store: no existing-target refusal")
replace("B5", f"{PKG}/acquire/store.py", "        os.rename(s, d)\n",
        "        __import__('shutil').copyfile(s, d)\n        os.remove(s)\n",
        "store: a move becomes copy-then-delete (a delete path)")
block("B6", f"{PKG}/acquire/run.py", "guard: acquisition sha256 dedupe against the database",
      "acquire: no sha256 lookup in the database")
block("B7", f"{PKG}/acquire/run.py", "guard: acquisition sha256 dedupe against the disk",
      "acquire: no sha256 lookup on disk")
block("B8", f"{PKG}/acquire/run.py", "guard: a file that does not bind is quarantined",
      "acquire: an unbound file is offered to the database instead of quarantined")
block("B9", f"{PKG}/acquire/run.py", "guard: dead routes are not retried blindly", "acquire: dead routes retried")
block("B10", f"{PKG}/acquire/run.py", "guard: the archive route stops at the quota margin or the run cap",
      "acquire: no quota stop")
M.append(dict(id="B11", kind="multi", what="acquire: the key is no longer redacted on the attempt path", edits=[
    dict(file=f"{PKG}/acquire/run.py", old="return redact(obj) if isinstance(obj, str) else obj",
         new="return obj"),
    dict(file=f"{PKG}/acquire/run.py", old="            add_secret(key)             # an injected session's key is redacted like open_session()'s\n",
         new="")]))
block("B12", f"{PKG}/acquire/annas.py", "guard: annas known md5 spends no download",
      "annas: a known md5 still spends a download")
block("B13", f"{PKG}/acquire/annas.py", "guard: annas gate 3 bytes are the record's md5 and size",
      "annas: bytes not checked against the record md5/size")
block("B14", f"{PKG}/acquire/annas.py", "guard: annas gate 1 a redirect to /search is not-in-archive",
      "annas gate 1: a redirect to /search is followed")
block("B15", f"{PKG}/acquire/annas.py", "guard: annas gate 2 the record carries the requested DOI",
      "annas gate 2: the record's DOI is not checked")
block("B16", f"{PKG}/acquire/annas.py", "guard: fetch_one never writes a literature topic folder",
      "annas fetch_one may file into Validation")

# ── the referee's surviving mutations (Reports/LITKB_P2_REFEREE_2026-09-14.md), re-expressed on the fixed code ──
replace("R1", f"{PKG}/admit/binding.py", "BIND_RATIO = 0.85\n", "BIND_RATIO = 0.60\n",
        "binding: BIND_RATIO 0.85 -> 0.60")
replace("R2", MIG14, "  IF v_ratio IS NULL OR v_ratio < 0.85 THEN\n", "  IF v_ratio IS NULL OR v_ratio < 0.50 THEN\n",
        "_check_binding: evidence ratio 0.85 -> 0.50 (live 0014)")
replace("R3", f"{PKG}/admit/binding.py", '    joined = "".join(fam)\n',
        '    joined = "".join(fam)\n    return joined[:3] in "".join(tokens)\n',
        "binding: the author check is the surname's first 3 letters as a substring")
M.append(dict(id="R4", kind="multi", tests=TESTS_P1P2,
              what="SQL norm_identifier no longer cuts the prefix before '10.' (live 0014; P1 + P2 files)", edits=[
    dict(file=MIG14, old="coalesce(substring(\n", new="coalesce((\n"),
    dict(file=MIG14, old="                          from '10\\..*$'), ''),\n", new="                          ), ''),\n")]))
block("R9", MIG14, "guard: check 2 file sha256 lookup", "admit: no file sha256 lookup (live 0014)")
replace("R10", f"{PKG}/acquire/store.py", 'for p in sorted(self.root.rglob("*.pdf")):',
        'for p in sorted((self.root / "Validation").rglob("*.pdf")):', "store: disk hash index covers only Validation/")
replace("R11", f"{PKG}/acquire/run.py", "budget.used >= budget.max_archive_downloads",
        "budget.used > budget.max_archive_downloads", "acquire: archive run cap >= -> >")
replace("R12", f"{PKG}/acquire/store.py",
        "        d = self.guard_new(dst)\n        d.parent.mkdir(parents=True, exist_ok=True)\n        os.rename(s, d)\n        return d\n",
        "        import shutil\n        return shutil.move(str(s), str(dst))\n", "store: move_new becomes an unguarded shutil.move")
# ── the guards the referee fixes added ──
replace("C1", f"{PKG}/textnorm.py", '    return _DOI_TAIL.sub("", d[i:])\n', '    return d[i:].rstrip("/")\n',
        "D1 Python: trailing . , ; : no longer stripped from a DOI")
replace("C2", f"{PKG}/textnorm.py", '    return None if s is None else _INVISIBLE.sub("", str(s))\n',
        '    return None if s is None else str(s).strip()\n', "D1/D7 Python: invisible characters only trimmed at the ends")
replace("C3", MIG14, "                        '[/.,;:]+$', '')\n", "                        '/+$', '')\n",
        "D1 SQL: trailing . , ; : no longer stripped from a DOI")
replace("C4", MIG14, "regexp_replace(p_value, '[", "regexp_replace(btrim(p_value), 'ZZZ[",
        "D1 SQL: norm_identifier no longer removes invisible characters from a DOI")
replace("C5", MIG14, "'value', CASE WHEN i->>'scheme' = 'doi' THEN norm_identifier('doi', i->>'value')\n"
        "                                                               ELSE i->>'value' END,",
        "'value', i->>'value',", "D1: admit stores the raw DOI spelling")
block("C6", f"{PKG}/admit/binding.py", "guard: binding title region", "D2: a title window anywhere on page 1")
block("C7", f"{PKG}/admit/binding.py", "guard: binding refuses reference-list windows", "D2: reference-list windows allowed")
block("C8", f"{PKG}/admit/binding.py", "guard: binding refuses citation-instruction windows",
      "D2: 'please cite' / cover citation windows allowed")
replace("C9", f"{PKG}/admit/binding.py",
        "        lo, hi = max(0, i - AUTHOR_NEAR_LINES), min(len(lines), i + n + AUTHOR_NEAR_LINES)\n",
        "        lo, hi = 0, len(lines)\n", "D2: the author anywhere on the page counts as near the title")
replace("C10", f"{PKG}/admit/binding.py", "MARKER_MIN_SURNAME = 5\n", "MARKER_MIN_SURNAME = 1\n",
        "D2: a glued one-letter marker accepted on short surnames (Park -> parks)")
block("C11", MIG14, "guard: check 3 region and author-near evidence",
      "D2 DB: _check_binding stops requiring title_region / author_near_title")
block("C12", MIG14, "guard: approve_admission locks the admitter's workstream open",
      "D3: approve_admission ignores the admitter's workstream")
block("C13", f"{PKG}/acquire/run.py", "guard: an issued download URL spends the run cap",
      "D4: an issued download URL does not count against the run cap")
replace("C14", f"{PKG}/acquire/annas.py", "        if issued is not None:\n            issued.append(di)\n", "",
        "D4: fetch_for_litkb never reports an issued URL")
block("C15", MIG14, "guard: a key collision takes the convention's a/b suffix", "D5: no a/b suffix on a key collision")
replace("C16", MIG14, "      AND litkb.norm_label(approver_session) <> litkb.norm_label(admitter_session)));",
        "      AND btrim(approver_session) <> btrim(admitter_session)));",
        "D7 DB: the sign-off constraint compares btrim()med sessions")
replace("C17", MIG14, "  SELECT regexp_replace(p_label, '[", "  SELECT regexp_replace(p_label, 'ZZZ[",
        "D7 DB: norm_label removes nothing")
block("C18", f"{PKG}/admit/front.py", "guard: approve compares labels without invisible characters (Python)",
      "D7 Python: approve does not pre-check the admitter's session")
# ── the P2 acceptance's surviving mutation (Reports/LITKB_P2_ACCEPTANCE_2026-09-14.md) ──
replace("V2b", f"{PKG}/admit/binding.py", "    if sum(ref[lo:hi]) >= 2:\n", "    if sum(ref[lo:hi]) >= 3:\n",
        "D2: the reference-list rule needs 3 reference-shaped lines instead of 2 (boundary)")
# ── the account-wide quota counter (litkb edge-pre1990 task, Reports/LITKB_EDGE_PRE1990_2026-09-14.md) ──
block("Q1", f"{PKG}/acquire/annas.py", "guard: annas the account counter gates every download request",
      "quota: the archive route ignores the account counter")
replace("Q2", f"{PKG}/acquire/annas.py", "    if len(found) != 1:\n        return None\n",
        "    if len(found) != 1:\n        return (0, 1000)\n", "quota: an unreadable counter reads as 0 / 1000 (fail open)")
replace("Q3", f"{PKG}/acquire/run.py", "quota_margin=budget.quota_margin)", "quota_margin=None)",
        "quota: acquire never asks the archive route to read the counter")
# ── defects found by the edge-pre1990 run ──
replace("E1", f"{PKG}/admit/front.py", '(p[1:].lower() if p.isupper() else p[1:])', "p[1:]",
        "make_key keeps a registry's all-capitals surname (PAGE_1954_ next to Page_1954_)")
block("E2", f"{PKG}/acquire/run.py", "guard: acquire from a file already in a topic folder binds it in place",
      "acquire --from-file lands a copy of a topic-folder file (and stops at duplicate-held against itself)")
block("E4", f"{PKG}/acquire/run.py", "guard: a work reached by one of its DOIs is acquired by that DOI",
      "work_record returns an arbitrary DOI of a work that carries two")
block("E3", f"{PKG}/textnorm.py", "guard: JSON sent to the database carries no NUL",
      "a NUL in PDF metadata reaches jsonb (UntranslatableCharacter)")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _pytest(tests=None):
    r = subprocess.run([sys.executable, "-m", "pytest", *(tests or TESTS), "-q", "-p", "no:cacheprovider", "-m", "not litkb_live",
                        "-rf"], cwd=str(SCRIPTS), capture_output=True, text=True, errors="replace")
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines) if " in " in ln and
                    any(w in ln for w in ("passed", "failed", "error", "skipped"))), "?")
    failed = [ln.split(" - ")[0].replace("FAILED ", "") for ln in lines if ln.startswith("FAILED ")]
    return r.returncode, summary.strip("= ").strip(), failed


def _count(summary, word):
    """The pytest summary's count for `word` as a whole word: '1 xfailed' is not a failure."""
    import re

    m = re.search(rf"(?<![\w])(\d+) {word}\b", summary)
    return int(m.group(1)) if m else 0


def _edit(text, old, new, mid):
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{mid}: mutation target occurs {n} times")
    return text.replace(old, new)


def _mutations(m):
    """[(path, original bytes, mutated bytes)] for one mutation."""
    edits = m["edits"] if m["kind"] == "multi" else [m]
    out = {}
    for e in edits:
        path = SCRIPTS / e["file"]
        original = out[path][0] if path in out else path.read_bytes()
        text = (out[path][1] if path in out else original).decode("utf-8")
        if m["kind"] in ("replace", "multi"):
            mutated = _edit(text, e["old"], e["new"], m["id"])
        else:
            begin, end = f"BEGIN {e['marker']}", f"END {e['marker']}"
            lines = text.splitlines(keepends=True)
            bi = [i for i, ln in enumerate(lines) if begin in ln]
            ei = [i for i, ln in enumerate(lines) if end in ln]
            if len(bi) != 1 or len(ei) != 1 or ei[0] <= bi[0] + 1:
                raise RuntimeError(f"{m['id']}: markers not found exactly once in {e['file']}")
            mutated = "".join(lines[:bi[0] + 1] + lines[ei[0]:])
        if mutated == text:
            raise RuntimeError(f"{m['id']}: mutation changed nothing")
        out[path] = (original, mutated.encode("utf-8"))
    return [(p, o, n) for p, (o, n) in out.items()]


def run_one(m):
    edits = _mutations(m)
    before = {p: _sha(o) for p, o, _n in edits}
    for p, _o, n in edits:
        p.write_bytes(n)
    try:
        rc, summary, failed = _pytest(m.get("tests"))
    finally:
        for p, o, _n in edits:
            p.write_bytes(o)
    for p, _o, _n in edits:
        ok = _sha(p.read_bytes()) == before[p]
        print(f"     restored {p.relative_to(SCRIPTS)} sha256 {before[p][:16]}... match: {ok}")
        if not ok:
            raise RuntimeError(f"{m['id']}: {p} was not restored byte-for-byte")
    return rc != 0 and _count(summary, "failed") > 0, summary, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="show each litkb P2 guard fire")
    ap.add_argument("--only", help="comma-separated mutation ids (default: all)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    chosen = M
    if a.only:
        wanted = [s.strip() for s in a.only.split(",") if s.strip()]
        unknown = sorted(set(wanted) - {m["id"] for m in M})
        if unknown:
            raise SystemExit(f"unknown mutation ids: {unknown}")
        chosen = [m for m in M if m["id"] in wanted]
    for m in chosen:                       # every target must exist before anything runs
        _mutations(m)
    rc, summary, _ = _pytest()
    print(f"baseline (unmutated, {' + '.join(TESTS)}): {summary}")
    base_ok = rc == 0 and not any(_count(summary, w) for w in ("failed", "skipped", "error", "errors", "xpassed"))
    rows = []
    for m in chosen:
        fired, summ, failed = run_one(m)
        rows.append((m, fired))
        print(f"{m['id']:<4} {'FIRED' if fired else 'DID NOT FIRE':<13} {m['what']}")
        print(f"     -> {summ}")
        for f in failed[:4]:
            print(f"        {f}")
    rc2, summary2, _ = _pytest()
    print(f"baseline again (restored): {summary2}")
    base2_ok = rc2 == 0 and not any(_count(summary2, w) for w in ("failed", "skipped", "error", "errors", "xpassed"))
    n = sum(f for _m, f in rows)
    print(f"\n{n}/{len(rows)} mutations fired; baselines {'passed' if base_ok and base2_ok else 'FAILED'}")
    sys.exit(0 if n == len(rows) and base_ok and base2_ok else 1)


if __name__ == "__main__":
    main()
