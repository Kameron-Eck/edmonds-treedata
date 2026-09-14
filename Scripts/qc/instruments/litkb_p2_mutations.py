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

M = []


def block(id_, file, marker, what):
    M.append(dict(id=id_, kind="block", file=file, marker=marker, what=what))


def replace(id_, file, old, new, what):
    M.append(dict(id=id_, kind="replace", file=file, old=old, new=new, what=what))


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
block("A5", f"{MIG}/0013_admission.sql", "guard: check 3 no text layer waits for OCR",
      "check 3: a file with no text layer is not binding-pending")
block("A6", f"{MIG}/0013_admission.sql", "guard: check 3 binding evidence",
      "check 3: the database stops checking the binding evidence")
block("A7", f"{MIG}/0013_admission.sql", "guard: check 4 a manual admission carries a bound file",
      "check 4: a manual admission without a bound file proceeds")
block("A8", f"{MIG}/0013_admission.sql", "guard: check 2 identifier lock",
      "check 2: no advisory lock on the normalised identifier")
block("A9", f"{MIG}/0013_admission.sql", "guard: check 2 identifier lookup",
      "check 2: no lookup of an already-admitted identifier")
block("A10", f"{MIG}/0013_admission.sql", "guard: check 2 title duplicate review",
      "check 2: no title-similarity review for a work without identifiers")
replace("A11", f"{MIG}/0013_admission.sql", "AS $$ SELECT 0.70::real $$;", "AS $$ SELECT 1.01::real $$;",
        "check 2: the calibrated threshold replaced by one no title can reach")
block("A12", f"{MIG}/0013_admission.sql", "guard: admit presents the workstream token", "admit without the token check")
block("A13", f"{MIG}/0013_admission.sql", "guard: approve_admission presents the workstream token",
      "approve_admission without the token check")
block("A14", f"{MIG}/0013_admission.sql", "guard: attach_file presents the workstream token",
      "attach_file without the token check")
block("A15", f"{MIG}/0013_admission.sql", "guard: the candidate belongs to the admitting workstream",
      "admit takes another workstream's candidate")
block("A16", f"{MIG}/0013_admission.sql", "guard: attach_file sha256 dedupe", "attach_file without the sha256 lookup")
block("A17", f"{MIG}/0013_admission.sql", "guard: attach_file binding", "attach_file without the binding check")
block("A18", f"{MIG}/0013_admission.sql", "guard: a fact chain enters main only through admission approval",
      "promote_prepare may carry an unapproved work/identifier/file chain")
block("A19", f"{MIG}/0013_admission.sql", "guard: approval moves main's pointer only from nothing",
      "approve_admission moves no pointer")
block("A20", f"{MIG}/0013_admission.sql", "guard: writer executes the admission functions",
      "the writer loses EXECUTE on admit / approve_admission / attach_file")
replace("A21", f"{MIG}/0009_referee2_fixes.sql",
        "\n      AND btrim(approver_session, E' \\t\\n\\r\\f\\x0b') <> btrim(admitter_session, E' \\t\\n\\r\\f\\x0b')));",
        "));", "the approver session <> admitter session clause dropped (live constraint, 0009)")
replace("A22", f"{MIG}/0003_write_functions.sql",
        "WHEN 'doi'   THEN regexp_replace(lower(btrim(p_value)),", "WHEN 'doi'   THEN regexp_replace(btrim(p_value),",
        "DOIs no longer lower-cased by norm_identifier (live 0003 text)")
# ── Python ──
replace("B1", f"{PKG}/admit/binding.py", "if ratio >= BIND_RATIO and author_found:", "if True:",
        "binding: every file binds")
replace("B1b", f"{PKG}/admit/binding.py", "if ratio >= BIND_RATIO and author_found:", "if ratio >= BIND_RATIO:",
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


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _pytest():
    r = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-m", "not litkb_live",
                        "-rf"], cwd=str(SCRIPTS), capture_output=True, text=True, errors="replace")
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines) if " in " in ln and
                    any(w in ln for w in ("passed", "failed", "error", "skipped"))), "?")
    failed = [ln.split(" - ")[0].replace("FAILED ", "") for ln in lines if ln.startswith("FAILED ")]
    return r.returncode, summary.strip("= ").strip(), failed


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
        rc, summary, failed = _pytest()
    finally:
        for p, o, _n in edits:
            p.write_bytes(o)
    for p, _o, _n in edits:
        ok = _sha(p.read_bytes()) == before[p]
        print(f"     restored {p.relative_to(SCRIPTS)} sha256 {before[p][:16]}... match: {ok}")
        if not ok:
            raise RuntimeError(f"{m['id']}: {p} was not restored byte-for-byte")
    return rc != 0 and "failed" in summary, summary, failed


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
    base_ok = rc == 0 and "failed" not in summary and "skipped" not in summary and "error" not in summary
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
    base2_ok = rc2 == 0 and "failed" not in summary2 and "skipped" not in summary2 and "error" not in summary2
    n = sum(f for _m, f in rows)
    print(f"\n{n}/{len(rows)} mutations fired; baselines {'passed' if base_ok and base2_ok else 'FAILED'}")
    sys.exit(0 if n == len(rows) and base_ok and base2_ok else 1)


if __name__ == "__main__":
    main()
