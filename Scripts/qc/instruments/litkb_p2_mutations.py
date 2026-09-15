"""litkb P2 — show every admission and acquisition guard FIRE (CLAUDE.md 3.4c: a kill must be shown to fire on a
known-bad input before it counts).

For every mutation: weaken ONE guard in the real source, run the WHOLE P2 test set (qc/test_litkb_p2.py and
qc/test_litkb_annas.py, live tests deselected), record whether it failed, restore the file byte-for-byte and
check the restore by sha256. Before and after all mutations the unmutated set must pass with nothing skipped.
Everything runs against litkb_test (the suite resets and migrates it from the files on disk); nothing here
touches the litkb database, and no mutation touches cluster grants.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p2_mutations.py [--only ID,...]
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p2_mutations.py --sites
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p2_mutations.py --workers 9
        (parallel: first `py -3.12 -m litkb.db.provision --workers 9`; see run_workers below and
        Reports/LITKB_HARNESS_PARALLEL_2026-09-14.md — the whole table in tens of minutes, not hours.
        Row counts and timings live in that report and in LITKB_P2_REPORT_2026-09-14.md; the table below is
        the only place the row count is stated, because it is the only place it cannot rot.)
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p2_mutations.py --workers 2 --only B6 --plant-equivalent
        (the harness's own kill check: the planted no-op row must be reported DID NOT FIRE, exit 1)

Exit 0 only if every chosen mutation fired and both baselines passed.

THE PER-CALL-SITE RULE (2026-09-14).  Twice a guard written in ONE helper and called from SEVERAL places was
tested at one place only, and the harness passed a mutant that removed it everywhere else: the binding
reference-window rule (V2b, Reports/LITKB_P2_ACCEPTANCE_2026-09-14.md) and textnorm.jsonb_safe (E3f,
Reports/LITKB_P2_ACCEPTANCE2_2026-09-14.md — tested on acquire/run.py's `_jsonb`, not on admit/front.py's).
Mutating the helper's BODY only proves that ONE reached call site is asserted somewhere.

So `--sites` (and test_litkb_harness_sites.py, which runs it inside qc/check.py) enumerates, statically, every
call of every targeted helper in Scripts/pipeline/litkb/ and requires a mutation row AT EACH ONE:

  * a call SITE is (file, innermost enclosing function, helper); several textual calls of the same helper in one
    function are one site and are mutated together;
  * imports are alias-resolved (`from litkb.textnorm import normalize_doi as _canonical` counts), because a
    renamed import is exactly how E3f hid;
  * a row covers a site only if the bytes it changes overlap one of that site's CALL lines — a row that only
    moves the helper's body cannot claim the site;
  * a site with no such row must be listed in EQUIVALENT with the reason a mutation there cannot change
    behaviour. There is no third bucket: anything else fails the self-check.
  * a declared site that no longer exists also fails (it catches a rename or a deletion).

One helper family — netutil.redact / add_secret / run._redacted — was DEFERRED rather than covered until
2026-09-14, when a row and a test were written at each of its 20 sites. DEFERRED_HELPERS is now empty, and
qc/test_litkb_harness_sites.py::test_the_redaction_family_is_under_the_rule asserts that it stays empty and that
the family stays in HELPERS, so a new deferral cannot be added quietly.

`--sites` also runs the STRUCTURAL guard, sink_check(): the per-call-site rule protects the redact() calls that
exist, and that one protects against the next one that is never written. Every print / sys.std{out,err}.write
under Scripts/pipeline/litkb must take a redactor's return, interpolate nothing, or be named in SINK_ALLOW with a
reason AND the number of sink calls that reason was read against. It is syntactic: it cannot follow a string
redacted in one function and printed in another. See the comment above SINK_ALLOW for what is deliberately left
to the call-site rule instead.
"""
import argparse
import ast
import difflib
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

# the guard helpers the per-call-site rule covers: the ones a mutation row targets, plus the wrapper each one is
# reached through (front._jsonb / run._jsonb around jsonb_safe, front._labels / commands._labels around
# norm_label, resolver.normalize_doi around textnorm.normalize_doi — a wrapper is a COPY of the guard).
HELPERS = ("jsonb_safe", "normalize_doi", "window_refusal", "tokens_contain", "parse_quota", "read_quota",
           "norm_label", "_jsonb", "_labels", "verdict",
           # the secret-redaction family, brought under the rule on 2026-09-14 (it was DEFERRED_HELPERS until
           # then): netutil.redact and its wrapper run._redacted, plus netutil.add_secret, which is what ARMS
           # redact for a run — a site that fails to register the key disarms every later site in that process.
           "redact", "add_secret", "_redacted")


def block(id_, file, marker, what, sites=None):
    M.append(dict(id=id_, kind="block", file=file, marker=marker, what=what, **({"sites": sites} if sites else {})))


def replace(id_, file, old, new, what, tests=None, sites=None):
    M.append(dict(id=id_, kind="replace", file=file, old=old, new=new, what=what,
                  **({"tests": tests} if tests else {}), **({"sites": sites} if sites else {})))


def site(id_, site_id, repl, what, tests=None):
    """Mutate the CALL, not the helper: every call of `helper` inside `site_id`'s function becomes `repl`, with
    {a0}/{a1}/{args} filled from that call's own argument source. The guard is simply not applied there."""
    file = site_id.split("::")[0].split("/", 1)[1]
    M.append(dict(id=id_, kind="site", file=f"{PKG}/{file}", site=site_id, repl=repl, what=what,
                  sites=[site_id], **({"tests": tests} if tests else {})))


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
M.append(dict(id="B11", kind="multi", what="acquire: the key is no longer redacted on the attempt path",
              edits=[
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
      "D7 Python: approve does not pre-check the admitter's session",
      sites=["litkb/admit/front.py::approve::norm_label"])
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
      "work_record returns an arbitrary DOI of a work that carries two",
      sites=["litkb/acquire/run.py::work_record::normalize_doi"])
block("E3", f"{PKG}/textnorm.py", "guard: JSON sent to the database carries no NUL",
      "a NUL in PDF metadata reaches jsonb (UntranslatableCharacter)")

# ── the per-call-site rows (see the module docstring) ─────────────────────────────────────
# E3f is the acceptance's surviving mutation: the SECOND copy of the NUL guard, on the admission path.
_JSONB = "__import__('psycopg.types.json', fromlist=['Jsonb']).Jsonb({a0})"
site("E3f", "litkb/admit/front.py::_jsonb::jsonb_safe", "{a0}", tests=TESTS_P1P2,
     what="front._jsonb no longer removes NULs (the `admit --file` copy of the E3 guard)")
site("E3r", "litkb/acquire/run.py::_jsonb::jsonb_safe", "{a0}", tests=TESTS_P1P2,
     what="run._jsonb no longer removes NULs (the acquisition copy of the E3 guard)")
site("E3rec", "litkb/textnorm.py::jsonb_safe::jsonb_safe", "{a0}", tests=TESTS_P1P2,
     what="jsonb_safe stops recursing: NULs survive inside dicts and lists")
site("S1", "litkb/admit/front.py::add_candidate::_jsonb", _JSONB, tests=TESTS_P1P2,
     what="add_candidate sends raw/authors/ids to jsonb unguarded")
site("S2", "litkb/admit/front.py::_call_admit::_jsonb", _JSONB, tests=TESTS_P1P2,
     what="admit sends work/identifiers/file/checks to jsonb unguarded")
site("S3", "litkb/acquire/run.py::record_attempt::_jsonb", _JSONB, tests=TESTS_P1P2,
     what="record_acquisition_attempt's detail goes to jsonb unguarded")
site("S4", "litkb/acquire/run.py::land_and_attach::_jsonb", _JSONB, tests=TESTS_P1P2,
     what="attach_file's file JSON (a download) goes to jsonb unguarded")
site("S5", "litkb/acquire/run.py::attach_in_place::_jsonb", _JSONB, tests=TESTS_P1P2,
     what="attach_file's file JSON (a file bound in place) goes to jsonb unguarded")
site("S6", "litkb/admit/front.py::_labels::norm_label", "{a0}", tests=TESTS_P1P2,
     what="the admitter's agent/session keep their invisible characters")
site("S7", "litkb/admit/front.py::_call_admit::_labels", "({a0}, {a1})", tests=TESTS_P1P2,
     what="admit sends the raw agent/session labels, unnormalised")
site("S8", "litkb/admit/front.py::approve::_labels", "({a0}, {a1})", tests=TESTS_P1P2,
     what="approve sends the raw approver labels, unnormalised")
site("S9", "litkb/admit/front.py::admit_registry::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="admit_registry stores and confirms the DOI as typed")
site("S10", "litkb/textnorm.py::normalize_doi::norm_label", "{a0}", tests=TESTS_P1P2,
     what="normalize_doi stops removing invisible characters first")
site("S11", "litkb/admit/resolver.py::normalize_doi::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="resolver.normalize_doi — the wrapper every annas call goes through — normalises nothing")
site("S12", "litkb/admit/resolver.py::resolve_doi::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="the resolver judges candidates on raw DOI spellings")
site("S13", "litkb/admit/binding.py::bind::window_refusal", '""', tests=TESTS_P1P2,
     what="bind accepts every title window (region, reference-list and cover rules not applied)")
site("S14", "litkb/admit/binding.py::bind::tokens_contain", "bool({a1})", tests=TESTS_P1P2,
     what="bind's metadata/page author checks pass on any non-empty surname")
site("S15", "litkb/admit/binding.py::bind.near::tokens_contain", "bool({a1})", tests=TESTS_P1P2,
     what="the author-near-the-title check passes on any non-empty surname")
site("S16", "litkb/acquire/annas.py::read_quota::parse_quota", "(0, 1000)", tests=TESTS_P1P2,
     what="read_quota invents a counter instead of parsing the page")
site("S17", "litkb/acquire/annas.py::fetch_for_litkb::read_quota", "((0, 1000), 200)", tests=TESTS_P1P2,
     what="the archive route invents a counter instead of reading the account page")
site("S18", "litkb/acquire/annas.py::fetch_for_litkb::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="the archive route resolves the DOI as given")
site("S19", "litkb/acquire/annas.py::fetch_one::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="aa_fetch's filing route resolves the DOI as given")
site("S20", "litkb/acquire/annas.py::audit_one::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="the audit compares a held file against the DOI as spelled in the manifest")
site("S21", "litkb/acquire/annas.py::run_audit::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="an audit row that raises is logged under the DOI as spelled")
site("S22", "litkb/acquire/annas.py::tier1::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="audit-fast tier 1 registers the DOI as spelled")
site("S23", "litkb/acquire/annas.py::repair_truncated_dois::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="the truncated-DOI repair matches raw spellings")
site("S24", "litkb/acquire/annas.py::run_jobs::normalize_doi", "{a0}", tests=TESTS_P1P2,
     what="a fetch job is run and logged under the DOI as spelled")
site("S25", "litkb/commands.py::_labels::norm_label", "{a0}", tests=TESTS_P1P2,
     what="the CLI passes --agent/--session with their invisible characters")
site("S26", "litkb/commands.py::cmd_admit::_labels", "(args.agent, args.session)", tests=TESTS_P1P2,
     what="litkb admit takes the raw labels, bypassing _labels")
site("S27", "litkb/commands.py::cmd_approve::_labels", "(args.agent, args.session)", tests=TESTS_P1P2,
     what="litkb approve takes the raw labels, bypassing _labels")
site("S28", "litkb/commands.py::cmd_acquire::_labels", "(args.agent, args.session)", tests=TESTS_P1P2,
     what="litkb acquire takes the raw labels, bypassing _labels")

# ── the secret-redaction sites (closed 2026-09-14; DEFERRED_HELPERS is now empty) ─────────
# The family was excluded until now: 1 of its 20 sites fired. Each row below strips the guard at ONE site and is
# answered by a test that plants a unique fake key where that site is the only thing between it and a sink. The
# add_secret rows are the odd ones: stripping them leaves redact() armed but with nothing registered, so the key
# reaches the sink through the OTHER sites — which is exactly what their tests assert.
site("RD1", "litkb/acquire/annas.py::result::redact", "{a0}", tests=TESTS_P1P2,
     what="annas.result: the attempt detail (incl. a fast_download URL's key=) is stored as given")
site("RD2", "litkb/acquire/annas.py::log_line::redact", "{a0}", tests=TESTS_P1P2,
     what="annas.log_line: the printed line's stem/doi/md5 fields are not redacted")
site("RD3", "litkb/acquire/annas.py::download_pdf::redact", "{a0}", tests=TESTS_P1P2,
     what="annas.download_pdf: the archive's API error, which echoes the refused key, enters `tried`")
site("RD4", "litkb/acquire/annas.py::fetch_for_litkb.done::redact", "{a0}", tests=TESTS_P1P2,
     what="annas.fetch_for_litkb: resolve()'s detail (a redirect Location) is returned unredacted")
site("RD5", "litkb/acquire/annas.py::_csv_row::redact", "{a0}", tests=TESTS_P1P2,
     what="annas._csv_row: the audit-fast CSV keeps whatever the manifest and the archive said")
site("RD6", "litkb/acquire/annas.py::run_audit_fast::redact", "{a0}", tests=TESTS_P1P2,
     what="annas.run_audit_fast: the DOI-REPAIR / T1 / T2 / T3 / SUMMARY lines print unredacted")
site("RD7", "litkb/acquire/open_access.py::fetch_open_access::redact", "{a0}", tests=TESTS_P1P2,
     what="open_access: the Unpaywall note (built from a URL carrying the account email) is returned as given")
site("RD8", "litkb/acquire/scihub.py::fetch_scihub::redact", "{a0}", tests=TESTS_P1P2,
     what="scihub: the mirrors tried — netloc and all, userinfo included — are returned as given")
site("RD9", "litkb/admit/resolver.py::resolution_log_line::redact", "{a0}", tests=TESTS_P1P2,
     what="resolver.resolution_log_line: the registry evidence prints unredacted")
site("RD10", "litkb/netutil.py::_raw_get::redact", "{a0}", tests=TESTS_P1P2,
     what="netutil: a transport error returns the failing URL, key and all, as the response body")
site("RD11", "litkb/acquire/annas.py::open_session::add_secret", "None", tests=TESTS_P1P2,
     what="annas.open_session: the key read from the key file is never registered for redaction")
site("RD12", "litkb/acquire/annas.py::main::add_secret", "None", tests=TESTS_P1P2,
     what="annas --audit: the CLI's own key read is never registered")
site("RD13", "litkb/acquire/annas.py::main_audit_fast.get_archive::add_secret", "None", tests=TESTS_P1P2,
     what="annas --audit-fast: the lazy archive login's key is never registered")
site("RD14", "litkb/acquire/run.py::record_attempt::_redacted", "{a0}", tests=TESTS_P1P2,
     what="run.record_attempt: acquisition_attempts.detail is sent to jsonb unredacted")
site("RD15", "litkb/acquire/run.py::_redacted::_redacted", "{a0}", tests=TESTS_P1P2,
     what="run._redacted stops recursing: a key inside a dict or a list in the detail survives")
site("RD16", "litkb/acquire/run.py::_redacted::redact", "{a0}", tests=TESTS_P1P2,
     what="run._redacted: the strings it reaches are passed through unredacted")
site("RD17", "litkb/acquire/run.py::acquire::redact", "{a0}", tests=TESTS_P1P2,
     what="run.acquire: the route's source_url is stored on the file version as fetched")
site("RD18", "litkb/acquire/run.py::acquire::add_secret", "None", tests=TESTS_P1P2,
     what="run.acquire: an injected annas session's key is never registered")

DEFERRED_HELPERS = {}

site("T18", "litkb/admit/binding.py::bind::verdict", '"bound"', tests=TESTS_P1P2,
     what="bind returns 'bound' without consulting verdict() at all")

# Call sites a mutation cannot change the behaviour of. The reason must be about the CODE, never about the tests.
EQUIVALENT = {
    "litkb/admit/binding.py::author_on_page::tokens_contain":
        "binding.author_on_page is defined and called by NOTHING — not by litkb, not by qc (grep over "
        "Scripts/pipeline and Scripts/qc: one hit, its own def). Its docstring says it is 'kept for callers "
        "outside check 3'; there are none, so no mutation inside it can reach any behaviour. It is dead code, "
        "and the entry should be removed from this table by deleting the function, not by testing it.",
    "litkb/acquire/annas.py::run_audit::redact":
        "The value is built ONLY as `detail=f\"{type(e).__name__}: {redact(e)}\"` and handed straight to "
        "result(), whose next statement is `r['detail'] = redact(r['detail'])` — the same function over the same "
        "string. Removing this call cannot change a byte of the returned result, of log_line(result), or of any "
        "row built from it. (The result() call is itself covered, by RD1.)",
    "litkb/acquire/annas.py::run_jobs::redact":
        "Identical shape to run_audit's: `detail=f\"{type(e).__name__}: {redact(e)}\"` passed to result(), which "
        "redacts r['detail'] immediately. The outer redact is an unreachable second application, not a guard "
        "with its own reach.",
}


def call_sites(root=None):
    """Every call of a HELPERS name under Scripts/pipeline/litkb -> {site_id: {"file", "lines", "calls"}}.

    site_id is "litkb/<path>::<enclosing function>::<helper>"; `lines` are the call lines in that function and
    `calls` the ast.Call nodes. `from X import helper as alias` is resolved, so a renamed import still counts."""
    root = Path(root or (SCRIPTS / PKG))
    out = {}
    for p in sorted(root.rglob("*.py")):
        out |= sites_of_text(p.read_text(encoding="utf-8"), p.relative_to(root.parent).as_posix())
    return out


# ── the structural guard: every stdout/stderr sink in litkb passes through a redactor ─────
# The per-call-site rule protects the redact() calls that EXIST. This protects against the next one that is never
# written: a new print() of a route's own words, with no redact around it, fails the ordinary suite.
#
# What it can enforce is syntactic: the argument of a print / sys.stdout.write / sys.stderr.write is either a call
# to a redacting function, or carries nothing dynamic at all, or is named here with a reason. What it CANNOT do is
# follow data: a string redacted in one function and printed in another is indistinguishable, statically, from one
# that was never redacted. Two other sinks are therefore left to the call-site rule instead of this one:
#   * acquisition_attempts.detail — every write goes through run.record_attempt, whose _redacted call is row RD14
#     (and the DB grants let nothing else write the table);
#   * exception text — the sink is whichever handler catches it, and the handlers (run.acquire, annas.run_audit,
#     annas.run_jobs) put it through redact()/result() at the point of catching, which is RD1 / RD4 / RD16.
REDACTORS = ("redact", "_redacted", "log_line", "resolution_log_line", "_csv_row")
SINKS = ("print", "sys.stdout.write", "sys.stderr.write", "stdout.write", "stderr.write")

# Each entry is (how many sink calls that function may have, why they are safe). The COUNT is what keeps the
# allowlist from becoming a per-function amnesty: an entry excuses the calls that were read, not the function
# for ever, so adding a print() inside an already-allowed function fails the self-check and the reason has to be
# re-argued. A count (unlike a line number) only moves when a sink is added or removed — exactly when review is
# due — so it does not rot on every edit above it.
SINK_ALLOW = {
    "litkb/acquire/annas.py::run_audit::print": (3,
        "AUDIT pacing / AUDIT SUMMARY: the row count, the pacing interval and the per-status counts. Every "
        "interpolated value is an int or a status word from the fixed `status` vocabulary — no route text. (The "
        "third call is print(log_line(res)), which is redacted; it shares the site with the other two.)"),
    "litkb/acquire/annas.py::main_audit_fast.get_archive::sys.stderr.write": (1,
        "'login failed (status %s)' — the HTTP status of the login, an int. The key itself is never in scope "
        "as a formatted value here."),
    "litkb/acquire/annas.py::main::sys.stderr.write": (2,
        "annas.main's two refusals: the job-mode refusal (a constant) and 'login failed (status %s)', the login's "
        "HTTP status as an int. The key is in scope in this function and is never formatted into either."),
    "litkb/commands.py::_print::print": (1,
        "The CLI's only writer, and it prints json.dumps(obj) of what the litkb front returns. Its callers are "
        "listed below; the redaction of those payloads happens where they are BUILT (run.acquire -> RD16/RD17, "
        "front.admit -> the admission functions), because by the time _print sees a dict the strings are "
        "already stored in the database in that same form."),
    "litkb/commands.py::cmd_ws::print": (1,
        "The workstream id, slug, branch and the PATH the token was written to — the line itself says '(never "
        "printed)' of the token, and `token` is not in scope as a formatted value in this branch."),
    "litkb/db/migrate.py::main::print": (2,
        "Database name, runner role name, migration filenames and counts. This module reads no secret: it "
        "connects through the passfile, which libpq opens and Python never reads."),
    "litkb/db/provision.py::provision::print": (6,
        "This is the one place litkb holds a secret other than the archive key — a freshly generated role "
        "password — and it prints only WHICH role and whether the password was reset or created. `password` is "
        "appended to pgpass and `del`eted on the next line; it is never a formatted value."),
    "litkb/db/provision.py::provision_workers::print": (3,
        "The nine worker test databases, created on the merge of the parallel harness (2026-09-14). All three "
        "calls interpolate only `db` — a name this function BUILDS itself as f'{DB_TEST}_w{i}' — plus the "
        "module constants TEST_ROLE and TABLESPACE. No password is generated or read in this function: the "
        "worker databases reuse the role provision() already created, so the one secret this module handles "
        "is not in scope here at all. `db` is worker_db(i)'s return, f'{_c.TEST_DB_PREFIX}_w{i}' — built from "
        "a module constant and the loop counter, never from anything read."),
    "litkb/ops/nightly_dump.py::verify_existing::print": (1,
        "Dump filename, verification stage and reason, all filesystem facts from verify_dump(). No credential "
        "is in scope: the dump runs under the passfile."),
    "litkb/ops/nightly_dump.py::install_task::print": (1,
        "The first line of PowerShell's own output from Register-ScheduledTask. The command it ran embeds a task "
        "name and a script path, no credential."),
}


def sink_sites(root=None):
    """Every stdout/stderr write under Scripts/pipeline/litkb -> {site_id: {"file", "line", "ok", "how"}}.

    site_id is "litkb/<path>::<enclosing function>::<sink>". ok is True when the argument is a call to a
    REDACTOR, or when it interpolates nothing (a constant, or an f-string with no {} fields)."""
    root = Path(root or (SCRIPTS / PKG))
    out = {}
    for p in sorted(root.rglob("*.py")):
        out |= sink_sites_of_text(p.read_text(encoding="utf-8"), p.relative_to(root.parent).as_posix())
    return out


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _redacted_expr(node, rel=""):
    """True if this argument cannot carry an unredacted secret: a redactor's return, a literal, an f-string with
    no interpolation, or a concatenation/join of such parts.

    `rel` guards a name collision that would otherwise pass a real sink: litkb/ops/nightly_dump.py has its OWN
    log_line(), which appends to a file and redacts nothing. Only redact/_redacted are recognised everywhere; the
    wrappers are recognised only in the modules that define them (acquire/ and admit/)."""
    if isinstance(node, ast.Call):
        name = _dotted(node.func).split(".")[-1]
        if name in ("redact", "_redacted"):
            return True
        if name in REDACTORS and (rel.startswith("litkb/acquire/") or rel.startswith("litkb/admit/")):
            return True
        if name == "join" and node.args:                       # "".join(<parts>) -> judge the parts
            return _redacted_expr(node.args[0], rel)
        return False
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.JoinedStr):
        return not any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _redacted_expr(node.left, rel) and _redacted_expr(node.right, rel)
    return False


def sink_sites_of_text(text, rel):
    """sink_sites() for ONE module's source."""
    tree = ast.parse(text)
    out, stack = {}, []

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            stack.append(n.name)
            self.generic_visit(n)
            stack.pop()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, n):
            name = _dotted(n.func)
            if name in SINKS:
                sid = f"{rel}::{'.'.join(stack) or '<module>'}::{name}"
                ok = bool(n.args) and _redacted_expr(n.args[0], rel)
                e = out.setdefault(sid, {"file": rel, "lines": set(), "calls": 0, "ok": True})
                e["lines"].add(n.lineno)
                e["calls"] += 1
                e["ok"] = e["ok"] and ok
            self.generic_visit(n)
    V().visit(tree)
    return out


def sink_check(verbose=True):
    """The structural guard. -> (ok, rows) with one row per stdout/stderr sink."""
    sites, problems, rows = sink_sites(), [], []
    for sid in sorted(SINK_ALLOW):
        if sid not in sites:
            problems.append(f"{sid}: allowed but no longer a sink (renamed or removed?)")
    for sid, info in sorted(sites.items()):
        pinned, why = SINK_ALLOW.get(sid, (None, None))
        if not info["ok"] and not why:
            problems.append(f"{sid}: writes to a sink without passing through {'/'.join(REDACTORS)}, "
                            f"and is not named in SINK_ALLOW")
        if info["ok"] and why:
            problems.append(f"{sid}: already redacted AND allowed — drop the SINK_ALLOW entry")
        if why and pinned != info["calls"]:
            problems.append(f"{sid}: SINK_ALLOW pins {pinned} sink call(s), the function now has "
                            f"{info['calls']} — the new one is not covered by that reason")
        rows.append((sid, sorted(info["lines"]), info["ok"], why))
    if verbose:
        print(f"\n{'stdout/stderr sink':<62} {'lines':<16} through a redactor?")
        for sid, lines, ok, why in rows:
            print(f"{sid:<62} {str(lines):<16} {'yes' if ok else 'ALLOWED: ' + (why or 'NO')}")
        print(f"\n{len(rows)} sinks, {sum(1 for r in rows if r[2])} redacted, {sum(1 for r in rows if r[3])} allowed")
        for p in problems:
            print("  PROBLEM " + p)
    return not problems, rows


def sites_of_text(text, rel):
    """call_sites() for ONE module's source (the mutator uses it on text it already holds)."""
    tree = ast.parse(text)
    alias = {a.asname or a.name: a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             for a in n.names if a.name in HELPERS}
    out, stack = {}, []

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            stack.append(n.name)
            self.generic_visit(n)
            stack.pop()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, n):
            f = n.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            nm = alias.get(nm, nm)
            if nm in HELPERS:
                sid = f"{rel}::{'.'.join(stack) or '<module>'}::{nm}"
                e = out.setdefault(sid, {"file": rel, "lines": set(), "calls": []})
                e["lines"].add(n.lineno)
                e["calls"].append(n)
            self.generic_visit(n)
    V().visit(tree)
    return out


def _site_mutate(text, sid, repl, mid):
    """Replace every call at `sid` with `repl`, filled from that call's own argument source. Offsets are spliced
    on the UTF-8 BYTES (ast column offsets are byte offsets) and from the end, so nothing else in the file moves:
    no reformatting, no unparse."""
    got = sites_of_text(text, sid.split("::")[0]).get(sid)
    if not got:
        raise RuntimeError(f"{mid}: call site {sid} does not exist")
    raw = text.encode("utf-8")
    starts, pos = [], 0
    for ln in raw.splitlines(keepends=True):
        starts.append(pos)
        pos += len(ln)
    spans = []
    for call in got["calls"]:
        # parenthesised, or the splice changes precedence: `norm_label(d or "").translate(...)` must become
        # `(d or "").translate(...)`, not `d or "".translate(...)` — which would mutate a second guard by accident
        args = [f"({ast.get_source_segment(text, a)})" for a in call.args]
        sub = repl.format(args=", ".join(args), **{f"a{i}": a for i, a in enumerate(args)})
        spans.append((starts[call.lineno - 1] + call.col_offset,
                      starts[call.end_lineno - 1] + call.end_col_offset, sub.encode("utf-8")))
    for a, b, sub in sorted(spans, reverse=True):
        raw = raw[:a] + sub + raw[b:]
    return raw.decode("utf-8")


def changed_lines(original, mutated):
    """The ORIGINAL line numbers a mutation changes (1-based)."""
    a, b = original.splitlines(), mutated.splitlines()
    out = set()
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out |= set(range(i1 + 1, max(i2, i1 + 1) + 1))
    return out


def self_check(verbose=True):
    """The per-call-site rule. -> (ok, rows) with one row per call site."""
    sites = call_sites()
    covered = {}
    for m in M:
        for sid in m.get("sites", []):
            covered.setdefault(sid, []).append(m["id"])
    problems, rows = [], []
    for sid in sorted(set(covered) | set(EQUIVALENT)):
        if sid not in sites:
            problems.append(f"{sid}: declared but no longer a call site (renamed or removed?)")
    for sid, info in sorted(sites.items()):
        ids, why = [], EQUIVALENT.get(sid)
        for mid in covered.get(sid, []):
            m = next(x for x in M if x["id"] == mid)
            hits = set()
            for path, orig, mut in _mutations(m):
                if path.relative_to(SCRIPTS / PKG).as_posix() == info["file"].split("/", 1)[1]:
                    hits |= changed_lines(orig.decode("utf-8"), mut.decode("utf-8"))
            if hits & info["lines"]:
                ids.append(mid)
            else:
                problems.append(f"{sid}: row {mid} claims it but changes no call line {sorted(info['lines'])}")
        if not ids and not why:
            problems.append(f"{sid}: NO mutation row at this call site, and no equivalence reason")
        if ids and why:
            problems.append(f"{sid}: both covered by {ids} and declared equivalent — pick one")
        rows.append((sid, sorted(info["lines"]), ids, why))
    if verbose:
        print(f"{'call site':<58} {'lines':<16} rows / equivalent")
        for sid, lines, ids, why in rows:
            print(f"{sid:<58} {str(lines):<16} {', '.join(ids) or 'EQUIVALENT: ' + (why or '')}")
        print(f"\n{len(rows)} call sites, {sum(1 for r in rows if r[2])} covered by a row, "
              f"{sum(1 for r in rows if r[3])} equivalent")
        for helper, why in DEFERRED_HELPERS.items():
            print(f"  DEFERRED (not under the rule) {helper}: {why}")
        for p in problems:
            print("  PROBLEM " + p)
    return not problems, rows


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
    if "\r\n" in text and "\r\n" not in old:      # a CRLF checkout (core.autocrlf=true on a fresh worktree)
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
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
        if m["kind"] == "site":
            mutated = _site_mutate(text, e["site"], e["repl"], m["id"])
        elif m["kind"] in ("replace", "multi"):
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


# ── parallel workers (2026-09-14, Kam: "organizing the work schedule to compliment the quality of the build") ──
# Serial, one row is ~4.5 min: the whole test set against Postgres, every time. N workers each get a PRIVATE COPY
# of the tree (a mutation edits the copy, never this tree) and a PRIVATE test database litkb_test_w<i>
# (provisioned by `py -3.12 -m litkb.db.provision --workers N`; the suite's advisory lock is per database, so
# workers never wait on each other). Each worker is this same script, run inside its copy with --only <its rows>,
# so nothing about a row changes: same edit, same whole test set, same baselines before and after, same sha256
# restore proof. The parent only partitions, launches, and reads the rows back.

WORKER_ROOT_DEFAULT = Path(r"D:\edmonds-pipeline\_litkb_harness_workers")
COPY_DIRS = ("Scripts", "Reports")          # tests read Reports/literature_tracker.csv
# the ONE ignore set: shutil.copytree and tree_manifest() must agree exactly, or every worker's
# stale-copy check (D-2) fails on files that were never copied in the first place
COPY_IGNORE = ("__pycache__", ".pytest_cache", "*.pyc", "_litkb_ws", ".litkb-workstream")
# files copied individually AFTER copytree (they are not all under COPY_DIRS). The guard's domain must equal
# the copy's domain, so tree_manifest() hashes exactly this list too (referee 2 E-2, 2026-09-14): the repo-root
# .gitignore was copied and never hashed, so a stale one was invisible to manifest_diff.
COPY_FILES = (".gitignore", "Scripts/.gitignore")


def default_workers():
    """Kam's 20 % headroom rule: leave a fifth of the threads free; each worker is one pytest process."""
    import os

    return max(1, int((os.cpu_count() or 4) * 0.8))


def tree_manifest(root):
    """{posix relative path: sha256} over COPY_DIRS under `root`, using COPY_IGNORE.

    D-2 (referee 2026-09-14): a STALE worker copy produced a FALSE SURVIVOR — the copy baselined 82 tests
    where a correct one baselines 241, and nothing compared the copy to the source. A worker now hashes its
    own tree and refuses to report any verdict unless it matches the parent's source manifest."""
    import fnmatch

    root = Path(root)
    out = {}
    for d in COPY_DIRS:
        base = root / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(part, pat) for part in Path(rel).parts for pat in COPY_IGNORE):
                continue
            if p.is_file():
                out[rel] = _sha(p.read_bytes())
    for rel in COPY_FILES:                 # E-2: the individually-copied files, or a stale one is invisible
        p = root / rel
        if p.is_file():
            out[rel] = _sha(p.read_bytes())
    return out


def manifest_diff(source, copy):
    """[(path, what)] for every file that differs — missing, extra or changed. Empty means identical."""
    bad = [(p, "MISSING from the copy") for p in sorted(set(source) - set(copy))]
    bad += [(p, "EXTRA in the copy") for p in sorted(set(copy) - set(source))]
    bad += [(p, "CHANGED") for p in sorted(set(source) & set(copy)) if source[p] != copy[p]]
    return bad


def partition(chosen, n):
    """Round-robin `chosen` over at most n workers, dropping empty parts. An EMPTY part is never launched:
    a worker whose --only is empty used to fall through to the whole table (referee Break C)."""
    n = max(1, min(n, len(chosen)))
    return [p for p in (chosen[i::n] for i in range(n)) if p]


def check_partition(parts, chosen):
    """Every chosen row reaches exactly one worker. Raises naming the rows that do not."""
    flat = [m["id"] for part in parts for m in part]
    want = [m["id"] for m in chosen]
    dropped = sorted(set(want) - set(flat))
    dup = sorted({i for i in flat if flat.count(i) > 1})
    if any(not part for part in parts):
        raise RuntimeError("partition produced an empty worker partition")
    if dropped or dup:
        raise RuntimeError(f"partition does not cover the chosen rows: dropped={dropped} duplicated={dup}")


def parse_worker_log(text):
    """A worker's log -> ({id: fired}, baselines_ok, stale_lines). The parent trusts nothing else."""
    import re

    fired = {}
    for ln in text.splitlines():
        mm = re.match(r"^(\S+)\s+(FIRED|DID NOT FIRE)\s", ln)
        if mm:
            fired[mm.group(1)] = mm.group(2) == "FIRED"
    base_ok = bool(re.search(r"mutations fired; baselines passed", text))
    stale = [ln for ln in text.splitlines() if ln.startswith("STALE COPY:")]
    return fired, base_ok, stale


def make_worker_copy(i, root):
    import shutil

    dst = Path(root) / f"w{i}"
    if dst.exists():
        shutil.rmtree(dst)
    repo = SCRIPTS.parent
    ignore = shutil.ignore_patterns(*COPY_IGNORE)
    for d in COPY_DIRS:
        shutil.copytree(repo / d, dst / d, ignore=ignore)
    # the suite's git-ignore test needs a checkout with the repo's .gitignore files: an empty git repo plus the
    # ignore files is enough for `git check-ignore --no-index`, and nothing here is ever committed
    for gi in COPY_FILES:
        if (repo / gi).exists():
            shutil.copy2(repo / gi, dst / gi)
    subprocess.run(["git", "init", "-q", str(dst)], check=True, capture_output=True)
    return dst


def run_workers(chosen, n, root, extra_args=()):
    """Partition `chosen` round-robin over n workers, run each as a subprocess in its own copy against its own
    database, and return [(mutation, fired, summary)] in the original order plus whether every baseline passed."""
    import concurrent.futures as cf
    import json
    import os
    import time

    from litkb.db.provision import worker_db

    parts = partition(chosen, n)
    check_partition(parts, chosen)                 # D-5: a row lost in the split is named, not a KeyError
    n = len(parts)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    src_manifest = root / "source.manifest.json"   # D-2: hashed ONCE, before any copy is made
    src_manifest.write_text(json.dumps(tree_manifest(SCRIPTS.parent), indent=0), encoding="utf-8")
    print(f"parallel: {len(chosen)} rows over {n} workers, copies under {root}")

    def one(i, rows):
        t0 = time.monotonic()
        copy = make_worker_copy(i, root)
        script = copy / "Scripts" / "qc" / "instruments" / Path(__file__).name
        env = dict(os.environ, LITKB_TEST_DB=worker_db(i), PYTHONUTF8="1",
                   PYTHONPATH=str(copy / "Scripts" / "pipeline"))
        log = root / f"w{i}.log"
        with log.open("w", encoding="utf-8") as fh:
            r = subprocess.run([sys.executable, "-u", str(script), "--worker", *extra_args,
                                "--manifest", str(src_manifest),
                                "--only", ",".join(m["id"] for m in rows)],
                               cwd=str(copy / "Scripts"), env=env, stdout=fh, stderr=subprocess.STDOUT, text=True)
        fired, base_ok, stale = parse_worker_log(log.read_text(encoding="utf-8", errors="replace"))
        return i, rows, fired, base_ok, stale, r.returncode, time.monotonic() - t0, log

    results, all_base = {}, True
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        for i, rows, fired, base_ok, stale, rc, dt, log in ex.map(lambda a: one(*a), enumerate(parts, 1)):
            missing = [m["id"] for m in rows if m["id"] not in fired]
            print(f"worker {i}: {len(rows)} rows, {sum(fired.values())} fired, baselines "
                  f"{'passed' if base_ok else 'FAILED'}, rc {rc}, {dt / 60:.1f} min, log {log}"
                  + (f", NO RESULT for {missing}" if missing else "")
                  + (f", {stale[0]}" if stale else ""))
            all_base = all_base and base_ok and rc in (0, 1) and not missing and not stale
            for m in rows:
                results[m["id"]] = fired.get(m["id"])      # D-6: None = no verdict, never a survivor
    return [(m, results.get(m["id"])) for m in chosen], all_base


def verdict_label(fired):
    """D-6: 'no verdict' and 'survivor' are different findings and must never print the same word."""
    return "FIRED" if fired else ("NO RESULT" if fired is None else "DID NOT FIRE")


def main(argv=None):
    ap = argparse.ArgumentParser(description="show each litkb P2 guard fire")
    ap.add_argument("--only", help="comma-separated mutation ids (default: all)")
    ap.add_argument("--sites", action="store_true",
                    help="run only the self-checks: the per-call-site table and the stdout/stderr sink scan "
                         "(both static; no database, no tests)")
    ap.add_argument("--workers", type=int, default=0,
                    help=f"run the rows in parallel over N private copies + databases (0 = serial; "
                         f"'auto' rule gives {default_workers()} here)")
    ap.add_argument("--worker-root", default=str(WORKER_ROOT_DEFAULT), help="where the worker copies live")
    ap.add_argument("--plant-equivalent", action="store_true",
                    help="KILL CHECK for the harness itself: add a comment-only row that cannot change behaviour; "
                         "the run must report it DID NOT FIRE and exit 1, serial or parallel")
    ap.add_argument("--allow-oversubscribe", action="store_true",
                    help=f"permit --workers above the headroom rule's {default_workers()} on this machine")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)   # set by run_workers
    ap.add_argument("--manifest", help=argparse.SUPPRESS)                      # set by run_workers (D-2)
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if a.sites:
        sites_ok = self_check()[0]
        sinks_ok = sink_check()[0]
        sys.exit(0 if sites_ok and sinks_ok else 1)
    # D-5: a worker must NEVER fall through to the whole table. An --only that is present and empty is an
    # error, not "everything"; and a worker without --only is an error too.
    if a.only is not None and not [s for s in a.only.split(",") if s.strip()]:
        raise SystemExit("--only was given with no mutation ids: refusing to run (an empty partition is a bug)")
    if a.worker and a.only is None:
        raise SystemExit("--worker requires --only: a worker runs exactly the ids the parent gave it")
    if a.workers > default_workers() and not a.allow_oversubscribe:
        raise SystemExit(f"--workers {a.workers} exceeds the headroom rule's {default_workers()} on this "
                         f"machine; pass --allow-oversubscribe to override deliberately")
    if a.manifest:                     # D-2: the stale-copy kill, before baselines and before any row runs
        import json

        bad = manifest_diff(json.loads(Path(a.manifest).read_text(encoding="utf-8")),
                            tree_manifest(SCRIPTS.parent))
        if bad:
            print(f"STALE COPY: {len(bad)} file(s) differ from the source tree, e.g. "
                  + "; ".join(f"{p} {w}" for p, w in bad[:5]))
            print("this worker reports NO verdict: a stale copy produces false survivors (referee D-2)")
            sys.exit(2)
    if a.plant_equivalent:
        replace("ZZ0", f"{PKG}/textnorm.py", "The ONE Python normalisation of DOIs",
                "The ONE Python normalisation of DOIs (planted equivalent: docstring only)",
                "PLANTED EQUIVALENT: a comment-only edit; the harness must report it DID NOT FIRE", tests=TESTS)
        if a.only and not a.worker and "ZZ0" not in a.only.split(","):
            a.only += ",ZZ0"           # a worker runs exactly the ids the parent gave it
    chosen = M
    if a.only is not None:
        wanted = [s.strip() for s in a.only.split(",") if s.strip()]
        unknown = sorted(set(wanted) - {m["id"] for m in M})
        if unknown:
            raise SystemExit(f"unknown mutation ids: {unknown}")
        chosen = [m for m in M if m["id"] in wanted]
    for m in chosen:                       # every target must exist before anything runs
        _mutations(m)
    ok, _rows = self_check()
    sinks_ok, _sink_rows = sink_check()
    if not ok or not sinks_ok:
        raise SystemExit("the harness self-check failed (see PROBLEM lines above)")
    if a.workers:
        import time

        t0 = time.monotonic()
        rows, base_ok = run_workers(chosen, a.workers, a.worker_root,
                                    extra_args=["--plant-equivalent"] if a.plant_equivalent else [])
        for m, fired in rows:
            print(f"{m['id']:<4} {verdict_label(fired):<13} {m['what']}")
        n = sum(1 for _m, f in rows if f)
        print(f"\n{n}/{len(rows)} mutations fired; baselines {'passed' if base_ok else 'FAILED'}; "
              f"wall-clock {(time.monotonic() - t0) / 60:.1f} min over {a.workers} workers")
        sys.exit(0 if n == len(rows) and base_ok else 1)
    # EVERY test set a chosen row runs is baselined, not just the default one: a row running P1+P2+annas against
    # an already-failing P1 would "fire" on a failure it did not cause. The flake of 2026-09-14 handed three rows
    # exactly that false pass.
    sets = sorted({tuple(m.get("tests") or TESTS) for m in chosen})

    def baselines(when):
        ok = True
        for ts in sets:
            rc, summary, failed = _pytest(list(ts))
            print(f"baseline {when} ({' + '.join(ts)}): {summary}")
            for f in failed[:4]:
                print(f"        {f}")
            ok = ok and rc == 0 and not any(_count(summary, w)
                                            for w in ("failed", "skipped", "error", "errors", "xpassed"))
        return ok

    base_ok = baselines("(unmutated)")
    rows = []
    for m in chosen:
        fired, summ, failed = run_one(m)
        rows.append((m, fired))
        print(f"{m['id']:<4} {'FIRED' if fired else 'DID NOT FIRE':<13} {m['what']}")
        print(f"     -> {summ}")
        for f in failed[:4]:
            print(f"        {f}")
    base2_ok = baselines("again (restored)")
    n = sum(f for _m, f in rows)
    print(f"\n{n}/{len(rows)} mutations fired; baselines {'passed' if base_ok and base2_ok else 'FAILED'}")
    sys.exit(0 if n == len(rows) and base_ok and base2_ok else 1)


if __name__ == "__main__":
    main()
