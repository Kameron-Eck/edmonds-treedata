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
import atexit
import datetime
import difflib
import hashlib
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
MIG = "pipeline/litkb/db/migrations"
PKG = "pipeline/litkb"
TESTS = ["qc/test_litkb_p2.py", "qc/test_litkb_annas.py"]
TESTS_P1P2 = ["qc/test_litkb_p1.py", *TESTS]
TESTS_P3 = [*TESTS, "qc/test_litkb_p3.py"]
MIG15 = f"{MIG}/0015_discrepancies.sql"
MIG14 = f"{MIG}/0014_referee_p2_fixes.sql"
#: 0016 CREATE OR REPLACEs litkb._check_binding (the OCR-queue evidence it records for P4, referee P3 F9),
#: so 0014's copy of that function is DEAD TEXT from here on: a mutation in it is overwritten when 0016 runs.
#: Every _check_binding row therefore targets 0016 - the live definition is the only one worth mutating, and
#: a row left pointing at 0014 would report DID NOT FIRE for a reason that is about the migration order, not
#: about the guard.
MIG16 = f"{MIG}/0016_held_reason.sql"
#: The same thing happened again on 2026-09-15, for the same reason, and it is worth naming as a CLASS
#: rather than as a second special case: 0020 CREATE OR REPLACEs litkb._check_registry (check 1's
#: registry-only branch and its title-forms rule) and litkb.clear_extraction_rows (the stage-6 rows it
#: has to clear as well), so 0013's and 0017's copies of those two functions are now DEAD TEXT.
#: A1-A4 and R59 therefore point HERE. Whenever a migration replaces a function, every mutation row on
#: the old body stops testing anything and reports DID NOT FIRE for a reason about migration order.
MIG20 = f"{MIG}/0020_first_use_friction.sql"
#: And a third time at the P8 merge, 2026-09-16, with the twist the class predicts once two branches are
#: open at once: 0018 and 0020 BOTH CREATE OR REPLACE litkb._feeds_token_ok, so the live body depended on
#: which was applied last and the mutation rows on BOTH of them (0018's X12, 0020's U1) were mutating text
#: that some databases never ran. 0021 states the definition once and is applied last everywhere, so it is
#: the live body on every database and the only one worth mutating. X12 and U1 both point HERE.
MIG21 = f"{MIG}/0021_feeds_validator_final.sql"
#: A FOURTH instance, and this one the P8 merge itself created: 0019 CREATE OR REPLACEs litkb._ws_chains
#: to add the evidence clause, and carries 0013's "a fact chain enters main only through admission
#: approval" guard along with it — so 0013's copy of that guard is dead text and A18, which deleted it,
#: reported DID NOT FIRE on the first full run after the merge. It points HERE. X15 already did.
MIG19 = f"{MIG}/0019_prepare_requires_evidence.sql"

M = []

# the guard helpers the per-call-site rule covers: the ones a mutation row targets, plus the wrapper each one is
# reached through (front._jsonb / run._jsonb around jsonb_safe, front._labels / commands._labels around
# norm_label, resolver.normalize_doi around textnorm.normalize_doi — a wrapper is a COPY of the guard).
HELPERS = ("jsonb_safe", "normalize_doi", "window_refusal", "tokens_contain", "parse_quota", "read_quota",
           "norm_label", "_jsonb", "_labels", "verdict",
           # the secret-redaction family, brought under the rule on 2026-09-14 (it was DEFERRED_HELPERS until
           # then): netutil.redact and its wrapper run._redacted, plus netutil.add_secret, which is what ARMS
           # redact for a run — a site that fails to register the key disarms every later site in that process.
           "redact", "add_secret", "_redacted",
           # P8's access-layer guards, brought under the rule after the referee counted what the X
           # rows did NOT cover (Reports/LITKB_P8_REFEREE_2026-09-15.md §6.1): the SHAPE redactor,
           # which masks a credential no add_secret could have registered, and the token check the
           # READ tools present — the guard whose absence let a forged token read a workstream.
           "redact_shapes", "_require_token")


def block(id_, file, marker, what, sites=None, tests=None):
    M.append(dict(id=id_, kind="block", file=file, marker=marker, what=what,
                  **({"tests": tests} if tests else {}), **({"sites": sites} if sites else {})))


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
block("A1", MIG20, "guard: check 1 the work is the registry record",
      "check 1: stop requiring the work's title and year to be the registry record's")
block("A2", MIG20, "guard: check 1 claimed record matches the registry",
      "check 1: stop comparing the claimed title ratio and first author")
block("A3", MIG20, "guard: check 1 year rule", "check 1: drop the year rule")
replace("A3b", MIG20, "ELSIF abs(v_cy - v_ry) = 1 AND", "ELSIF abs(v_cy - v_ry) <= 2 AND",
        "check 1: widen +/-1 to +/-2 years")
block("A4", MIG20, "guard: check 1 a registry identifier is confirmed",
      "check 1: a registry admission with no registry-confirmed identifier passes")
block("A5", MIG16, "guard: check 3 no text layer waits for OCR",
      "check 3: a file with no text layer is not binding-pending")
block("A6", MIG16, "guard: check 3 binding evidence",
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
block("A18", MIG19, "guard: a fact chain enters main only through admission approval",
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
replace("R2", MIG16, "  IF v_ratio IS NULL OR v_ratio < 0.85 THEN\n", "  IF v_ratio IS NULL OR v_ratio < 0.50 THEN\n",
        "_check_binding: evidence ratio 0.85 -> 0.50 (live 0016)")
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
block("C11", MIG16, "guard: check 3 region and author-near evidence",
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

# ── friction 5: a failed download is QUARANTINED, never deleted ───────────────────────────
# Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9: a curl answered with an HTML error page, the 295,657 bytes
# landed as _litkb_staging/incoming/IFLA_2017_library-reference-model.pdf, and they were removed with `rm -f` to
# free the name — a delete inside the tree that exists because 149 PDFs were lost on 2026-09-12. F5a and F5b are
# the two ways acquisition could go back to dropping such bytes; F5c is the delete itself, planted where the
# tidy-up would naturally be written, and it is answered by the no-delete SOURCE SCAN rather than by behaviour.
block("F5a", f"{PKG}/acquire/run.py", "guard: bytes a route refused are quarantined, never discarded",
      "acquire: bytes a route refused (an HTML error page served as a .pdf) are dropped instead of quarantined")
block("F5b", f"{PKG}/acquire/run.py", "guard: a download that is not a whole PDF is quarantined, never discarded",
      "land_and_attach: a truncated download is sent to binding instead of quarantine, and nothing records why")
replace("F5c", f"{PKG}/acquire/run.py",
        '    qpdf, _qtxt = store.to_quarantine(from_file, txt if txt.exists() else None, work["key"], shape, sha)\n',
        '    qpdf, _qtxt = store.to_quarantine(from_file, txt if txt.exists() else None, work["key"], shape, sha)\n'
        '    Path(from_file).unlink(missing_ok=True)      # "tidy up the file we just moved"\n',
        "acquire --from-file: a delete is added to the acquire path after the move (a no-op at runtime: the "
        "no-delete source scan is what must catch it)")
# F5d-F5f: the two defects the same live run found next. F5d is the from-file self-dedupe (a handed-in file in
# incoming/ was `duplicate-held` against its own hash, and the field workaround was to rename it to `.download`).
# F5e/F5f are the two CALL SITES of one rule — a work is stored under "title: subtitle" since migration 0020, and
# the page prints whichever form the publisher chose — which is exactly the shape the per-call-site rule exists
# for: land_and_attach binds a download, front.file_evidence binds a file held in place.
block("F5d", f"{PKG}/acquire/run.py",
      "guard: the dedupe asks what the corpus HOLDS, and staging and quarantine hold nothing",
      "acquire: incoming/ and _quarantine/ count as holdings again - a hand-fetched file in incoming is deduped "
      "against ITSELF, and a quarantined file is locked out for ever")
replace("F5g", f"{PKG}/acquire/run.py",
        '    skip = (f"{STAGING}/incoming/", f"{QUARANTINE}/")\n',
        '    skip = (f"{STAGING}/incoming/",)\n',
        "acquire: _quarantine/ is a holding again - a file quarantined under a wrong record can never bind after "
        "the record is corrected (the live Konda_2016 / Kopcke_2010 / Enamorado_2019 lockout)")
replace("F5e", f"{PKG}/acquire/run.py",
        '    b = _binding.bind_any(pdf, _forms(work), work["first_author"], info=info)\n',
        '    b = _binding.bind(pdf, work["title"], work["first_author"], info=info)\n',
        "acquire: a download is bound against the work's stored title alone, so a paper whose page prints the "
        "bare title of a subtitled work is quarantined as binding-failed")
replace("F5f", f"{PKG}/acquire/run.py",
        '                                title_forms=_forms(work)[1:])\n',
        '                                )\n',
        "acquire: a file bound IN PLACE is bound against the work's stored title alone (the second call site of "
        "the same rule)")

# ── the per-call-site rows (see the module docstring) ─────────────────────────────────────
# E3f is the acceptance's surviving mutation: the SECOND copy of the NUL guard, on the admission path.
_JSONB = "__import__('psycopg.types.json', fromlist=['Jsonb']).Jsonb({a0})"
site("E3f", "litkb/admit/front.py::_jsonb::jsonb_safe", "{a0}", tests=TESTS_P1P2,
     what="front._jsonb no longer removes NULs (the `admit --file` copy of the E3 guard)")
site("E3r", "litkb/acquire/run.py::_jsonb::jsonb_safe", "{a0}", tests=TESTS_P1P2,
     what="run._jsonb no longer removes NULs (the acquisition copy of the E3 guard)")
site("E3rec", "litkb/textnorm.py::jsonb_safe::jsonb_safe", "{a0}", tests=TESTS_P1P2,
     what="jsonb_safe stops recursing: NULs survive inside dicts and lists")
# The third reached copy of the E3 guard: stage 0 reads the PDF /Info dictionary straight off the file, and the
# NUL that started E3 (Bell 1977's 'Acrobat 3.0 Capture Plug-in' producer string) lives in exactly that
# dictionary. Stage 0's own set carries the case, so it is the set this row runs.
site("E3inv", "litkb/extract/inventory.py::probe_file::jsonb_safe", "{a0}",
     tests=["qc/test_litkb_inventory.py"],
     what="stage 0 passes a PDF's /Info dictionary on with its NULs (the inventory copy of the E3 guard)")
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

# -- P3: migration + exports (design 13, 14 P3 row; Reports/LITKB_P3_REPORT_2026-09-15.md) --
# The P3 kills: a planted duplicate DOI and the planted Averkov wrong DOI are rejected at load; a planted
# disagreeing title produces a discrepancy record; loading twice admits nothing new.
def p3(fn, *a, **kw):
    fn(*a, **kw)
    M[-1]["tests"] = TESTS_P3


p3(block, "P1a", f"{PKG}/migrate_legacy/run.py", "guard: every disagreeing legacy field is recorded",
   "the discrepancy WRITER is removed: a disagreeing field is compared and then dropped")
p3(block, "P1b", MIG15, "guard: record_discrepancy presents the workstream token",
   "record_discrepancy without the token check")
p3(block, "P1c", MIG15, "guard: a discrepancy names the work or the candidate it belongs to",
   "a discrepancy may name neither a work nor a candidate")
p3(block, "P1d", MIG15, "guard: a discrepancy's candidate belongs to its workstream",
   "a discrepancy may point at another workstream's candidate")
p3(block, "P1e", MIG15, "guard: writer executes record_discrepancy and holds no direct write on discrepancies",
   "the writer loses EXECUTE on record_discrepancy (and the reader its SELECT)")
replace("P2a", f"{PKG}/migrate_legacy/plan.py", '        shape = "held"\n', '        shape = "claimed"\n',
        "case C admits on a claim the registry contradicts, with no file: check 1 bypassed", tests=TESTS_P3)
replace("P2b", f"{PKG}/migrate_legacy/plan.py",
        '    return all(fields[f]["agrees"] for f in ("title", "authors", "year"))',
        '    return all(fields[f]["agrees"] for f in ("title", "authors"))',
        "the year is no longer part of whether the claim agrees", tests=TESTS_P3)
replace("P3b", f"{PKG}/migrate_legacy/run.py",
        "    seen = ctx.already_loaded(detail)\n    if seen:\n", "    seen = None\n    if seen:\n",
        "idempotence: the TRACKER loader stops recognising a row it has already loaded", tests=TESTS_P3)
replace("P3c", f"{PKG}/migrate_legacy/run.py",
        "    seen = ctx.already_loaded(detail)\n    if seen or _stem_held(ctx, stem):\n",
        "    seen = None\n    if seen or _stem_held(ctx, stem):\n",
        "idempotence: the MANIFEST loader stops recognising a stem it has already loaded", tests=TESTS_P3)
p3(block, "P4a", f"{PKG}/migrate_legacy/run.py",
   "guard: a manifest sha256 that is not the file on disk is a discrepancy, never a silent pass",
   "a manifest sha256 that does not match the held file passes unflagged")
# (no P5a: the a/b key suffix is the DATABASE's rule, migration 0014 D5, mutated by C15. P3 briefly carried a
# Python copy of it in migrate_legacy.free_key; this harness is what found the copy, by reporting a mutation
# that removed it as DID NOT FIRE — nothing depended on it. The copy is gone; the P3 collision test now
# exercises 0014's rule through the loader, and TESTS_P3 runs under C15.)
site("P6a", "litkb/migrate_legacy/plan.py::doi_discrepancy::normalize_doi", "{a0}", tests=TESTS_P3,
     what="the DOI discrepancy compares raw spellings: a case variant reads as a changed DOI")
site("P6b", "litkb/migrate_legacy/plan.py::plan_row::normalize_doi", "{a0}", tests=TESTS_P3,
     what="the loader confirms the DOI as the tracker spelled it, uncanonicalised")
site("P6d", "litkb/migrate_legacy/run.py::discrepancy::_jsonb", _JSONB, tests=TESTS_P3,
     what="a discrepancy's detail JSON goes to jsonb unguarded (a NUL from PDF metadata survives)")
site("P6e", "litkb/migrate_legacy/run.py::record_use::_jsonb", _JSONB, tests=TESTS_P3,
     what="the use version's identity and fields go to jsonb unguarded")
site("P6f", "litkb/commands.py::cmd_migrate::_labels", "(args.agent, args.session)", tests=TESTS_P3,
     what="litkb migrate records the raw agent/session labels, unnormalised")
p3(block, "P7a", f"{PKG}/migrate_legacy/run.py",
   "guard: a row that reached a work records its use, DEDUPED rows included",
   "a row deduped against an existing work loses its Relevance, grade and Feeds")
p3(block, "P7b", f"{PKG}/migrate_legacy/run.py",
   "guard: a resumed load finishes a row it had already admitted but not finished",
   "a load interrupted between the admission and the use leaves the use missing forever")
p3(block, "P7c", f"{PKG}/export.py", "guard: a refused file is still exported as a manifest row",
   "a file the database refused is dropped from the manifest export")
site("P6g", "litkb/migrate_legacy/run.py::discrepancy::jsonb_safe", "{a0}", tests=TESTS_P3,
     what="a discrepancy's claimed/registry TEXT values are sent with their NULs (the load dies on one)")
site("P6h", "litkb/migrate_legacy/run.py::_load_tracker_row::jsonb_safe", "{a0}", tests=TESTS_P3,
     what="the candidate's title is sent as text with its NULs")
p3(block, "P7h", f"{PKG}/migrate_legacy/run.py",
   "guard: a legacy row naming a file the store does not hold is recorded",
   "a manifest row whose file is missing or quarantined is unbound with nothing saying why")
p3(block, "P7g", f"{PKG}/migrate_legacy/run.py",
   "guard: a file another work already holds is recorded as a sha256 collision",
   "one sha256 filed under two works: the second is left unbound with nothing saying why")
replace("P7e", f"{PKG}/export.py",
        '            u = _use_for_row(uses.get(work_id), r) if not (r.get("Duplicate of") or "").strip() else None\n',
        '            u = (uses.get(work_id) or [None])[-1] if not (r.get("Duplicate of") or "").strip() else None\n',
        "two tracker rows on one work: each prints whichever use was written last", tests=TESTS_P3)
replace("P7d", f"{PKG}/export.py",
        '            u = _use_for_row(uses.get(work_id), r) if not (r.get("Duplicate of") or "").strip() else None\n',
        "            u = _use_for_row(uses.get(work_id), r)\n",
        "a `Duplicate of` row is painted with the original row's Relevance and Feeds", tests=TESTS_P3)

# -- P3 after the referee (Reports/LITKB_P3_REFEREE_2026-09-15.md): the gate's value test, the held branch,
# the one year parser, a held row's reason, a pending binding's evidence. The gate instrument is mutated the
# same way as any other source: `--sites` does not reach qc/, but the mutator takes any path under Scripts/
# and the worker copies carry the whole tree.
P3DIFF = "qc/instruments/litkb_p3_diff.py"
p3(block, "P8a", P3DIFF, "guard: the explaining record must EQUAL the exported value",
   "the gate's `explained` bucket needs only a record NAMING the cell, so a fabricated value passes")
p3(replace, "P8b", P3DIFF,
   '                                      or (_FIELD_ALIAS.get(field, field) == "doi" and _same_doi(hit[1] or "", b)))',
   '                                      )',
   "the gate's value test is normalised equality alone: 19 real DOI cells fail the gate")
p3(block, "P8c", P3DIFF, "guard: a changed cell on a HELD row is a bug, whatever record names it",
   "the HELD branch is shadowed again: 91 of 109 held rows carry a record, so a corrupt held cell reads as explained")
p3(replace, "P8d", f"{PKG}/migrate_legacy/plan.py", "    claimed_year_i = year_int(claimed_year)\n",
   "    claimed_year_i = int(claimed_year) if str(claimed_year or '').isdigit() else None\n",
   "two year parsers again: `2019a` reads as 2019 in the loader and as None in the comparison")
p3(block, "P8e", f"{PKG}/migrate_legacy/run.py", "guard: a held candidate records WHY it is held",
   "a held candidate is recorded with no reason: why it is held must be inferred from the missing admission")
p3(block, "P8f", MIG16, "guard: a pending binding records the evidence it waited on",
   "a binding-pending check records a verdict and a sentence, and none of the numbers P4's OCR queue needs")

# -- stage 5: the unified frame reader, reconciliation and the P5 ingest -----------------------
# (Reports/LITKB_STAGE5_INGEST_2026-09-15.md; tests qc/test_litkb_reconcile.py, plus the P1 set for
# the rows that move a role's privileges.)
MIG17 = f"{MIG}/0017_extraction.sql"
TESTS_S5 = ["qc/test_litkb_reconcile.py"]
TESTS_S5P1 = ["qc/test_litkb_p1.py", "qc/test_litkb_reconcile.py"]


def s5(fn, *a, **kw):
    """Like p3(): run the row against the stage-5 set, whatever the row helper's default is."""
    fn(*a, **kw)
    M[-1]["tests"] = TESTS_S5


# THE FRAME. One reader now; these rows are what stops it from silently becoming three again.
replace("R51", f"{PKG}/extract/inventory.py",
        "    try:\n        return tuple(round(float(v), 4) for v in fallback())\n    except Exception:  # noqa: BLE001\n        return None\n",
        "    return None\n",
        "the inherited-/MediaBox fallback removed: the 16 corpus pages whose /MediaBox comes from "
        "the page tree lose their box (Platanios_2014, Vincent_1993)", tests=TESTS_S5)
replace("R52", f"{PKG}/extract/grobid.py",
        "    return inventory.page_frames(pdf_path, error=GrobidError)",
        "    return inventory.page_frames(pdf_path, error=ValueError)",
        "the GROBID adapter stops raising its own error on a page with no mediabox", tests=TESTS_S5)
replace("R53", f"{PKG}/extract/reconcile.py", "IOU_MATCH = 0.5", "IOU_MATCH = 0.02",
        "the match threshold collapsed: a partial overlap (a column one tool merged and the other "
        "split) is recorded as one region and its disagreement is lost", tests=TESTS_S5)
replace("R54", f"{PKG}/extract/reconcile.py", "IOU_MATCH = 0.5", "IOU_MATCH = 0.999",
        "the match threshold raised past agreement: every region becomes single-tool", tests=TESTS_S5)
replace("R55", f"{PKG}/extract/reconcile.py", "COVERAGE_FLOOR = 0.80", "COVERAGE_FLOOR = 0.0",
        "the coverage floor removed: a page whose body went unassigned passes the gate", tests=TESTS_S5)
replace("R56", f"{PKG}/extract/reconcile.py",
        "        if b.box_index == 0 or cur is None:",
        "        if True or cur is None:",
        "per-line boxes are no longer unioned: a paragraph's FIRST LINE is matched against the "
        "other tool's whole paragraph (8 matched regions on Alwan_1988, against 84)", tests=TESTS_S5)
replace("R57", f"{PKG}/extract/reconcile.py",
        "        if hit is None or hit < last:", "        if False:",
        "the reading-order CHECKER accepts any order: an interleaved two-column extraction passes",
        tests=TESTS_S5)
# R57 mutates the checker. R519/R520 mutate the WRITER, which is where the defect actually was:
# the first `_assign_order` re-derived order from geometry and put 21 of 23 body snippets on
# Benedek_2015 pp2-3 out of Docling's order, and no test saw it because the order test ran on
# hand-built blocks. These two rows are §14's "a deliberately interleaved column extraction fails
# the reading-order metric" applied to the producer.
replace("R519", f"{PKG}/extract/reconcile.py",
        "    keyed.sort(key=lambda t: t[:7])",
        "    keyed.sort(key=lambda t: (t[2], t[4], t[5]))",
        "reading order goes back to geometry (page, y, x): a two-column page is read across the "
        "gutter", tests=TESTS_S5)
replace("R520", f"{PKG}/extract/reconcile.py",
        "        if min(b.x1, block.x1) - max(b.x0, block.x0) <= 0:\n            continue",
        "        if False:\n            continue",
        "the anchor stops requiring horizontal overlap: a GROBID-only block in the left column "
        "takes the right column's order", tests=TESTS_S5)
replace("R522", f"{PKG}/extract/ingest.py",
        'conn.execute("INSERT INTO litkb.figures (block_id) VALUES (%s)", (bid,))',
        'conn.execute("INSERT INTO litkb.figures (block_id, description) VALUES (%s, %s)",\n'
        '                             (bid, b.payload.get("caption") or None))',
        "a figure's CAPTION is written into figures.description, which is stage 8's vision field: "
        "later readers cannot tell a caption from a model's description of the picture",
        tests=TESTS_S5)
replace("R521", f"{PKG}/extract/reconcile.py",
        '    inside = [i for _c, x, y, i in layer["pts"] if _in_box(x, y, box, tol)]\n'
        '    if not inside:\n        return ""\n'
        '    return layer["text"][min(inside):max(inside) + 1]',
        '    return "".join(_c for _c, x, y, _i in layer["pts"] if _in_box(x, y, box, tol))',
        "the native text is joined from the ink again: every space is gone, so no quote can be "
        "verified against a block and no chunker can use one", tests=TESTS_S5)

# THE SCHEMA (migration 0017) and the ingest.
s5(block, "R58", MIG17, "guard: tables.cells JSON is retired in favour of table_cells",
   "a table's cells may be written as a JSON blob beside the rows: two homes for one fact")
s5(block, "R59", MIG20, "guard: an ok run's rows are never cleared",     # 0020 replaces the function
   "the resume path can empty a LIVE run: the evidence rows citing it lose their text")
s5(block, "R510", MIG17, "guard: a reconciliation run with no blocks cannot be declared ok",
   "a reconciliation that produced nothing is recorded as an ok run and can become current")
s5(block, "R511", MIG17, "guard: a cell belongs to a table block",
   "a table cell may hang below a paragraph")
s5(block, "R512", MIG17, "guard: a block's run belongs to the block's file",
   "a block may name another file's run — on the direct-INSERT path 0010 left open")
s5(block, "R513", MIG17, "guard: a canonical block carries a reading order",
   "a canonical block with no reading order: the set cannot be read back in order")
replace("R514", f"{PKG}/extract/ingest.py",
        '        _clear_run(conn, run_id)',
        '        pass  # _clear_run(conn, run_id)',
        "a killed worker's leftover blocks are appended to instead of cleared: the file ends with "
        "two sets of blocks and no unique key can see them", tests=TESTS_S5)
replace("R515", f"{PKG}/extract/ingest.py",
        "        if _after_blocks is not None:\n            _after_blocks(conn, run_id)\n",
        "        conn.commit()\n        if _after_blocks is not None:\n            _after_blocks(conn, run_id)\n",
        "THE P5 KILL: text rows are committed outside the run's transaction, so another session "
        "sees a half-written file", tests=TESTS_S5)
replace("R516", f"{PKG}/extract/ingest.py",
        "    if existing and status == \"ok\":",
        "    if False:",
        "the idempotence check removed: a second ingest of the same file at the same pipeline "
        "version writes a second set of rows", tests=TESTS_S5)
replace("R517", MIG17,
        "GRANT EXECUTE ON FUNCTION litkb.add_disagreement(uuid, uuid, integer, text, text, double precision, double precision[], text, text, text, text, text, text, uuid) TO litkb_ingest;",
        "GRANT EXECUTE ON FUNCTION litkb.add_disagreement(uuid, uuid, integer, text, text, double precision, double precision[], text, text, text, text, text, text, uuid) TO litkb_ingest, litkb_writer;",
        "the writer gains the disagreement writer: it can put text of its choosing below a run",
        tests=TESTS_S5P1)
# 0007's copy of the ok-run rule became DEAD TEXT the moment 0017 CREATE OR REPLACEd the
# function (the same reason MIG16 makes 0014's _check_binding dead, above): the live copy is the
# one below, and a mutation of 0007's would not fire.
block("R518", MIG17, "guard: current run is an ok run of this file",
      "set_current_run accepts a FAILED run, another file's run or NULL: a failed extraction "
      "becomes the file's answer and un-promotes its evidence")
M[-1]["tests"] = TESTS_S5P1

# -- stage 5, after the referee (Reports/LITKB_STAGE5_REFEREE_2026-09-15.md §10) --------------
#
# THE THRESHOLDS AT +/-20 %. The referee moved all four by a fifth in both directions and the
# suite passed eight times out of eight: R53/R54/R55 pin only the extremes (0.02, 0.999, 0.0),
# and IOU_TOUCH and TEXT_AGREE had no row at all. These eight rows are the fifth, and each one
# fails a gold-derived boundary case in qc/test_litkb_reconcile.py rather than a round number.
replace("R523", f"{PKG}/extract/reconcile.py", "IOU_MATCH = 0.5", "IOU_MATCH = 0.4",
        "IOU_MATCH down a fifth: Benedek p9's pair at 0.4559 — two tools regioning one area "
        "DIFFERENTLY — is recorded as one region and its disagreement is lost", tests=TESTS_S5)
replace("R524", f"{PKG}/extract/reconcile.py", "IOU_MATCH = 0.5", "IOU_MATCH = 0.6",
        "IOU_MATCH up a fifth: Benedek p7's pair at 0.5334 — real agreement — becomes two "
        "single-tool blocks", tests=TESTS_S5)
replace("R525", f"{PKG}/extract/reconcile.py", "IOU_TOUCH = 0.1", "IOU_TOUCH = 0.08",
        "IOU_TOUCH down a fifth: boxes that do not overlap enough to be about one region are "
        "recorded as a partial-overlap disagreement", tests=TESTS_S5)
replace("R526", f"{PKG}/extract/reconcile.py", "IOU_TOUCH = 0.1", "IOU_TOUCH = 0.12",
        "IOU_TOUCH up a fifth: the corpus's real touching pairs (Benedek p5 0.1029, Alwan p8 "
        "0.1003, Almon p5 0.1020) vanish from the disagreement table entirely", tests=TESTS_S5)
replace("R527", f"{PKG}/extract/reconcile.py", "TEXT_AGREE = 0.90", "TEXT_AGREE = 0.72",
        "TEXT_AGREE down a fifth: two tools reading a region differently (Almon p4, 0.8932) is "
        "recorded as agreement and the conflict is never written down", tests=TESTS_S5)
replace("R528", f"{PKG}/extract/reconcile.py", "TEXT_AGREE = 0.90", "TEXT_AGREE = 0.99",
        "TEXT_AGREE up a fifth: real agreement (Benedek p9, 0.9015) is recorded as a "
        "text_conflict and every matched region's confidence drops to 0.7", tests=TESTS_S5)
replace("R529", f"{PKG}/extract/reconcile.py", "COVERAGE_FLOOR = 0.80", "COVERAGE_FLOOR = 0.64",
        "COVERAGE_FLOOR down a fifth: a page at 0.70 — a third of its body unassigned — passes "
        "the gate", tests=TESTS_S5)
replace("R530", f"{PKG}/extract/reconcile.py", "COVERAGE_FLOOR = 0.80", "COVERAGE_FLOOR = 0.96",
        "COVERAGE_FLOOR up a fifth: an ordinary page at 0.90 is refused", tests=TESTS_S5)

# THE FOUR FIXES. Each row removes one and must fail the test that measures it on the real file.
replace("R531", f"{PKG}/extract/reconcile.py",
        '    return jsonb_safe(s).replace(HYPHEN_NONCHAR, "") if isinstance(s, str) else jsonb_safe(s)',
        "    return s",
        "THE BLOCKER: the reconcile boundary stops cleaning. Docling's NULs reach Postgres and "
        "Benedek_2015's whole transaction aborts — the file lands nothing — and U+FFFE reaches "
        "blocks.text at every hyphenated line", tests=TESTS_S5)
site("R531s", "litkb/extract/reconcile.py::_clean::jsonb_safe", "{a0}", tests=TESTS_S5,
     what="the NUL strip is dropped at the reconcile call site while the helper stays: the "
          "per-call-site rule's own case, on the site the blocker was found at")
replace("R532", f"{PKG}/extract/reconcile.py",
        "    canonical = _dedupe_figures(canonical)\n", "",
        "the figure dedupe removed: two figure blocks over one figure both reach ingest and "
        "litkb.figures holds two rows for it", tests=TESTS_S5)
replace("R533", f"{PKG}/extract/reconcile.py",
        'GROBID_BODY_REGIONS = tuple(k for k in GROBID_REGIONS if k != "figure")',
        "GROBID_BODY_REGIONS = GROBID_REGIONS",
        "GROBID's <figure> goes back into the BODY matcher: every figure is entered twice, 24 "
        "figure blocks for Benedek_2015's 8 figures", tests=TESTS_S5)
replace("R534", f"{PKG}/extract/reconcile.py",
        "            for col in _column_groups(bs):",
        "            for col in [bs]:",
        "an element's line boxes are unioned across the column gutter again: the cross-column "
        "paragraph becomes a page-wide box ordered ahead of its own column", tests=TESTS_S5)
replace("R535", f"{PKG}/extract/reconcile.py",
        "              _column_bucket(c.x0), c.y0, c.x0, i, c)",
        "              0, c.y0, c.x0, i, c)",
        "the reading-order tie-break goes back to y0 alone: two fragments of one element read "
        "right column before left", tests=TESTS_S5)
replace("R536", f"{PKG}/extract/reconcile.py",
        "        if want and any(t.startswith(want) or want in t[:len(want) + lead] for t in texts):",
        "        if want and any(want in t for t in texts):",
        "per-region recall stops asking whether a block BEGINS at the region: an overlapping "
        "neighbour that merely contains the text counts as the region, which is exactly the "
        "blindness the character share already has", tests=TESTS_S5)

# ── P5: the bulk driver's own three guards (2026-09-16) ───────────────────────────────────
# These four rows are the exception to the file rule above and are here deliberately. The
# per-call-site self-check enumerates Scripts/pipeline/litkb only, so a guard written in an
# INSTRUMENT is outside its reach and would otherwise carry no row at all — and P5's driver
# holds three guards nothing else covers: the `ok`-only filter that keeps the L4 pass's 323
# held rows (132 unstable, 191 degenerate) out of `equations.latex`; the cropbox shift that
# makes the LaTeX join land at all (measured: Conley_1999 attaches 138/138 with it, 0/138
# without); and the sidecar check that is §14 P5's kill (b).
TESTS_P5 = ["qc/test_litkb_p5_bulk.py"]
P5B = "qc/instruments/litkb_p5_bulk.py"

replace("P51", P5B,
        '        if r.get("status") not in (None, "ok"):\n            continue',
        "        if False:\n            continue",
        "load_latex admits every row: a decode that did not reproduce, and a repetition loop, "
        "land in equations.latex where a reader takes them for the equation", tests=TESTS_P5)
replace("P52", P5B,
        '            sx, sy = (dx, dy) if c.frame == "mediabox" else (0.0, 0.0)',
        "            sx, sy = 0.0, 0.0",
        "the formula box is compared to the block's box without the cropbox shift: on a cropped "
        "page nothing joins, and at a loose tolerance the wrong region does", tests=TESTS_P5)
replace("P53", P5B,
        "    return bool(want) and _sha256_file(path) == want",
        "    return True",
        "_artifact_ok stops hashing: a half-written TEI or DoclingDocument is reused as a "
        "finished one — §14 P5 kill (b)", tests=TESTS_P5)
replace("P54", P5B,
        "            if i in taken:\n                continue",
        "            if False:\n                continue",
        "attach_latex stops claiming a block once: two L4 rows over one region overwrite each "
        "other instead of leaving the second unmatched", tests=TESTS_P5)

DEFERRED_HELPERS = {}

site("T18", "litkb/admit/binding.py::bind::verdict", '"bound"', tests=TESTS_P1P2,
     what="bind returns 'bound' without consulting verdict() at all")

# ── P8: the MCP server, the agents' one path into the knowledge base (design §9, §9.1) ────
# The server lives under Scripts/pipeline/litkb/, so the per-call-site rule reaches it the moment
# the file exists — which is why it was built with ONE redact() and ONE add_secret(), each in one
# function: every tool result goes through _out(), every write tool through _session(). Answered by
# qc/test_litkb_p8.py, whose non-database tests need no Postgres, so these rows fire anywhere.
TESTS_P8 = ["qc/test_litkb_p8.py"]
site("X1", "litkb/mcp/server.py::_out::redact", "{a0}", tests=TESTS_P8,
     what="the MCP output boundary stops redacting: whatever a route said reaches the model verbatim")
site("X2", "litkb/mcp/server.py::_session::add_secret", "None", tests=TESTS_P8,
     what="_session stops ARMING redaction with the workstream token, so redact() is left with "
          "nothing registered and the token survives every later _out()")
site("X3", "litkb/mcp/server.py::_labels::norm_label", "{a0}", tests=TESTS_P8,
     what="MCP labels keep invisible characters: a label of zero-width characters is no longer "
          "blank, so a write records an agent and session no comparison will match")
site("X4", "litkb/mcp/server.py::_admit::_labels", '("a", "s")', tests=TESTS_P8,
     what="litkb_admit stops demanding agent and session labels and invents a pair")
site("X5", "litkb/mcp/server.py::_acquire::_labels", '("a", "s")', tests=TESTS_P8,
     what="litkb_acquire stops demanding agent and session labels and invents a pair")
site("X6", "litkb/mcp/server.py::_record_use::_labels", '("a", "s")', tests=TESTS_P8,
     what="litkb_record_use stops demanding agent and session labels and invents a pair")

# The referee's §6.1: "a guard with no row is a guard not yet shown to be load-bearing, and two of
# P8's four best properties are in that position". These are those rows, plus one for each fix the
# referee's five findings asked for. Every one of them is answered by a test in qc/test_litkb_p8.py
# that does NOT carry the litkb_live mark, because the harness deselects live tests.
site("X7", "litkb/mcp/server.py::_out::redact_shapes", "{a0}", tests=TESTS_P8,
     what="the output boundary stops masking credential SHAPES: a pgpass line planted in a block "
          "comes back verbatim, exactly as the referee got it out of a search result (F-4)")
site("X17", "litkb/netutil.py::redact_shapes::redact_shapes", "{a0}", tests=TESTS_P8,
     what="redact_shapes stops recursing: a credential inside the dicts and lists a tool result is "
          "built from survives, and every hit litkb_search returns is inside one (the twin of RD15)")
site("X8", "litkb/mcp/server.py::_candidates::_require_token", "None", tests=TESTS_P8,
     what="litkb_candidates stops presenting the workstream token: a forged token reads the "
          "workstream's candidates and admissions (F-1)")
site("X9", "litkb/mcp/server.py::_ws_status::_require_token", "None", tests=TESTS_P8,
     what="litkb_ws_status stops presenting the workstream token: a forged token reads the "
          "workstream's whole status, which is what the referee did (F-1)")
block("X10", f"{PKG}/mcp/server.py", "guard: evidence comes from the work the use is about",
      "a caller may name work A while quoting a block of work B, and is not told")
M[-1]["tests"] = TESTS_P8
site("X18", "litkb/mcp/server.py::_propose_promotion::_require_token", "None", tests=TESTS_P8,
     what="litkb_propose_promotion stops presenting the workstream token: a forged token prepares "
          "ANOTHER workstream's proposals under the promoter credential, writes its chain report "
          "into this worktree, and blocks its owner's own prepare")
replace("X19", f"{PKG}/netutil.py", "_SECRET_KEY_RE.fullmatch(str(k))", "None", tests=TESTS_P8,
        what="the output boundary stops reading a result's FIELD NAMES: a value under a key called "
             "`password` or `token` is carried out whenever its own shape is unremarkable (F-4's "
             "second half — the regexes see leaf TEXT, not the key above it)")
# X11/X13/X14 neuter the LOGIC rather than deleting the CREATE. Deleting it left the COMMENT and the
# GRANT behind, migration 0018 failed to apply, and every Postgres test ERRORED — which this harness
# does not read as a failure, so all three reported DID NOT FIRE on the first run. A row that breaks
# the FILE proves the file is load-bearing; only a row that breaks the RULE proves the rule is
# (CLAUDE.md 3.4c). Each of these leaves a valid migration whose function does the wrong thing.
replace("X11", f"{MIG}/0018_access_layer.sql",
        "  SELECT coalesce((SELECT t.token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')\n"
        "                     FROM workstream_tokens t WHERE t.workstream_id = p_ws), false)\n",
        "  SELECT true\n",
        "check_ws_token accepts ANY token: the read tools verify and are told yes, which is the "
        "referee's forged-token read with the check in place", tests=TESTS_P8)
# F-3's row, repointed from 0018 to 0021 at the P8 merge (see MIG21). 0018's copy of this function is
# DEAD TEXT from 0021 on, so a row that deleted it would report DID NOT FIRE for a reason about
# migration order rather than about the guard — the class MIG16 and MIG20 already name. Deleting the
# guarded block in 0021 leaves a VALID migration (the function still exists, from 0020) whose body is
# 0020's LOOSER one, which is the whole point: what fires is the DEPTH rule the convention states and
# 0020 did not enforce. The coverage half of the same guard is U1.
block("X12", MIG21,
      "guard: the feeds vocabulary has one definition, independent of apply order",
      "the one definition is gone, so the live validator is whichever earlier migration ran last — on a "
      "database built from scratch that is 0020's, which takes `framework §13.1.1` where the convention "
      "allows at most one sub-level (F-3, and the 0018/0020 apply-order split)")
M[-1]["tests"] = TESTS_P8
M.append(dict(id="X13", kind="multi", tests=TESTS_P8,
              what="norm_search_text becomes a whitespace collapser: it stops dropping the "
                   "extractor's replacement characters and stops joining line-break hyphenation, so "
                   "`overesti- mate` is two words again on both sides of the comparison",
              edits=[
    dict(file=f"{MIG}/0018_access_layer.sql",
         old="             translate(coalesce(p_text, ''), chr(65533) || chr(173), ''),",
         new="             coalesce(p_text, ''),"),
    dict(file=f"{MIG}/0018_access_layer.sql",
         old="             '-[ \\t\\r\\n]+', '', 'g'),",
         new="             'ZZZZ-[ \\t\\r\\n]+', '', 'g'),")]))
replace("X14", f"{MIG}/0018_access_layer.sql",
        "    t := plainto_tsquery('simple', w);\n",
        "    t := NULL::tsquery;\n",
        "any_term_query returns nothing, so the any-term leg matches no block and search is "
        "all-terms again: one word the extractor mangled drops the passage, the Q3 miss",
        tests=TESTS_P8)
block("X15", f"{MIG}/0019_prepare_requires_evidence.sql",
      "guard: a use is prepared only on at least one verified evidence row",
      "a use with NO evidence at all reaches prepared again — the convention error the referee "
      "confirmed by running (§3.6)")
M[-1]["tests"] = TESTS_P8
block("X16", f"{PKG}/commands.py", "guard: prepare WRITES the promotion report",
      "prepare records a report path and writes no file, as it did when the skill and the P8 report "
      "both said it wrote one onto the work branch (F-5)")
M[-1]["tests"] = TESTS_P8

# ── the operational fix set (2026-09-16) ──────────────────────────────────────────────────
# From LITKB_OPERATIONAL_REFEREE_2026-09-16.md. R-1 was not a weakened guard — `litkb_work` named
# two columns the schema does not have and had NEVER been called on a work the database holds — so
# what X20 mutates is the four-state LADDER the fix replaced it with. The rung is the thing a
# session acts on, and collapsing it reproduces the symptom exactly: a tool that looks alive and
# tells a session nothing it can act on. X21-X23 are the two gates the referee found missing at
# `record_use` (R-5, R-6).
replace("X20", f"{PKG}/mcp/server.py",
        '    if not files:\n        state = "held"\n'
        '    elif not any(f[4] for f in files):\n        state = "bound-unextracted"\n'
        '    else:\n        state = "extracted"\n',
        '    state = "extracted"\n',
        "litkb_work answers `extracted` for every work it holds: `held` (no file bound) and "
        "`bound-unextracted` (a PDF bound and never read) become indistinguishable from a "
        "searchable work — the state the operational test needed psql twice to reach (R-2)",
        tests=TESTS_P8)
block("X21", f"{PKG}/mcp/server.py", "guard: the statement is a statement",
      "a use records a BLANK claim beside a perfectly verified quote, and an essay-length one: the "
      "database's own CHECK is `statement <> ''`, which a single space satisfies, so both promote "
      "clean (R-5/R-6)")
M[-1]["tests"] = TESTS_P8
site("X22", "litkb/mcp/server.py::_record_use::norm_label", "{a0}", tests=TESTS_P8,
     what="the statement's emptiness test stops seeing invisible characters: a statement of "
          "zero-width joiners is truthy and is recorded as a claim — the hole row X3 closes for a "
          "LABEL, at the call site the statement gate added")
site("X24", "litkb/mcp/server.py::_my_uses::_require_token", "None", tests=TESTS_P8,
     what="litkb_my_uses stops presenting the workstream token: a forged .litkb-workstream naming a "
          "real workstream id reads back every statement, quote and work key that workstream has "
          "recorded — the tenth tool walking straight into F-1's hole on the day it was added")
block("X23", f"{PKG}/mcp/server.py", "guard: every feeds token is in the convention's vocabulary",
      "feeds tokens are stored unvalidated again and first checked a whole session later at "
      "`promote prepare`: a use carrying `§16.2` or `nonsense token` records clean and its author "
      "finds out at promotion, if at all")
M[-1]["tests"] = TESTS_P8

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


# ── P6 (stage 6, references) ────────────────────────────────────────────────────────────────────────
# Stage 6 adds six calls of normalize_doi under Scripts/pipeline/litkb/, and the per-call-site rule covers the
# PACKAGE, not a phase. Its rows are authored in litkb_p6_mutations.py and appended to this table at import, so
# there is ONE self-check (and one qc/test_litkb_harness_sites.py) over the whole package rather than two that
# each see half of it. The engine below then runs P2 and P6 rows identically.
def _register_p6():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "litkb_p6_mutations", Path(__file__).resolve().parent / "litkb_p6_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.register(block, replace, site)


_register_p6()


# ── P7 (the Semantic Scholar leg) ───────────────────────────────────────────────────────────────────
# Same arrangement, same reason: litkb/admit/s2.py adds two calls of normalize_doi, and the per-call-site rule
# covers the PACKAGE. Rows authored in litkb_s2_mutations.py.
def _register_s2():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "litkb_s2_mutations", Path(__file__).resolve().parent / "litkb_s2_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.register(block, replace, site)


_register_s2()


# ── the first real use of the KB (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8, migration 0020) ────
# These kills are asserted in qc/test_litkb_first_use.py, which is NOT in TESTS, so every row names its
# own set — `tests` REPLACES the default, it does not extend it, and a row that forgot this would run
# the P2 suite against a mutation the P2 suite knows nothing about and report DID NOT FIRE.
TESTS_FU = [*TESTS, "qc/test_litkb_first_use.py"]


def fu(fn, *a, **kw):
    fn(*a, **kw)
    M[-1]["tests"] = TESTS_FU


# §8.6 — the feeds vocabulary, COVERAGE. The mutation is the validator as 0005 left it: the three forms
# of §4.5, which is why the linkage review wrote 15 uses with an empty feeds array. Repointed from 0020
# to 0021 at the P8 merge — see MIG21: 0018 and 0020 each replaced this function, so from 0021 on the
# live body is 0021's on every database and a mutation in either earlier file tests nothing.
# X12 is the other half of the same guard and is deliberately a separate row: it deletes the definition
# instead of narrowing it, which falls back to 0020's LOOSER body and so tests the depth rule, where this
# row tests the coverage. One guard, two ways to break it, two different suites that catch them.
fu(replace, "U1", MIG21,
   "    'framework §[0-9]+(\\.[0-9]+)?' ||\n"
   "    '|narrative §[0-9]+' ||\n"
   "    '|gated-plan gate [0-9]+' ||\n"
   "    '|review §[0-9]+(\\.[0-9]+)*' ||\n"
   "    '|gap row [0-9]+' ||\n"
   "    '|decision [a-z0-9][a-z0-9-]*' ||\n"
   "    '|report [A-Za-z0-9][A-Za-z0-9._-]*\\.md#§[A-Za-z0-9][A-Za-z0-9._§-]*' ||\n",
   "    'framework §[0-9]+(\\.[0-9]+)?' ||\n"
   "    '|gap row [0-9]+' ||\n"
   "    '|decision [a-z0-9][a-z0-9-]*' ||\n",
   "the feeds validator goes back to 0005's three forms: a use that feeds a report, a narrative "
   "section, a gate or a review section carries no valid token at all")
fu(block, "U2", f"{PKG}/commands.py", "guard: feeds tokens are checked before the use is written",
   "`use add` writes first and lets prepare find the bad token later — which is how the 15 uses of the "
   "linkage review ended up with no feeds at all")

# §8.3 — a quote is anchored in an extracted block, or the use is refused. The mutation is the exact
# fallback the review had to use: the quote survives in free text the database cannot check.
fu(block, "U3", f"{PKG}/commands.py", "guard: a quote is anchored in an extracted block or the use is refused",
   "a quote that is in no block is accepted and the use is written anyway: unverifiable evidence, "
   "recorded as though it were evidence")
fu(replace, "U4", f"{PKG}/use.py",
   '    sql += " AND b.page_no = %s"', '    sql += " AND %s IS NOT NULL"',
   "locate_quote stops honouring --page: a quote that occurs on two pages is anchored to whichever "
   "block the ordering happens to return first")
fu(replace, "U5", f"{PKG}/use.py",
   "           \"  JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id \"",
   "           \"  JOIN litkb.files f ON f.id = b.file_id \"",
   "a quote may be anchored in a SUPERSEDED run's blocks, which is text that is no longer the file's "
   "answer — the same thing use_evidence_status.promotable refuses at prepare")

# §8.5 — a DOI with no claim. The database guard and the client declaration are two rows, because the
# declaration is what makes the case auditable and the guard is what makes it a declaration.
fu(block, "U6", MIG20, "guard: check 1 a registry-only admission says so",
   "check 1: an admission with no claim, no bound file and no registry_only marker passes anyway — the "
   "rule 0013 wrote is gone rather than made sayable")
fu(block, "U7", f"{PKG}/admit/front.py", "guard: an admission with no claim and no file says it is registry-only",
   "the client stops declaring a registry-only admission, so `admit --doi` alone is refused again")

# P4 — the title and its subtitle.
fu(replace, "U8", f"{PKG}/admit/registry.py",
   '    return f"{title}: {sub}"', "    return title",
   "the work title goes back to the registry's BARE title: Konda 2016 is 'Magellan' again and its key "
   "is minted from one word")
fu(replace, "U9", f"{PKG}/admit/binding.py",
   "    results = [(t, bind(pdf_path, t, first_author, page_text=text, info=info)) for t in forms]",
   "    results = [(forms[0], bind(pdf_path, forms[0], first_author, page_text=text, info=info))]",
   "the binder tries only the work's own title form: a first page printing the bare title of a "
   "subtitled work stops binding")
fu(block, "U10", f"{PKG}/admit/front.py", "guard: a claim that lacks the subtitle is a discrepancy, not a refusal",
   "a claim that named the work but not its subtitle is admitted and the disagreement is dropped "
   "instead of being kept for review")
# A1 (repointed to 0020 above) already blocks that whole guard. This row is its NEW half: the work's
# title may be any form the REGISTRY published, which is what lets a stored "title: subtitle" through.
# Mutated back to the bare title alone, every subtitled work reads as a different study.
fu(replace, "U11", MIG20,
   "    IF jsonb_typeof(e->'registry_titles') = 'array' THEN",
   "    IF false THEN",
   "check 1: only the registry's BARE title is accepted as the work's, so a work stored under the "
   "title-plus-subtitle form the registry itself published is refused")

# §8.4 — a source with no PDF stays a manual PROPOSAL.
fu(replace, "U12", f"{PKG}/admit/front.py",
   '    return _call_admit(conn, ws, token, candidate_id, "manual", k, work, ids, file_json,',
   '    return _call_admit(conn, ws, token, candidate_id, "registry", k, work, ids, file_json,',
   "a web source is admitted as a registry FACT: no second session ever signs off on a page one "
   "session saved and one session bound")

# stage 6 — the resolution a reference claims must be shown, on the direct path too.
fu(block, "U13", MIG20, "guard: a reference's resolution is shown",
   "a reference may say `resolved` with no DOI, or name a resolved work while calling itself "
   "unresolved — including on the DIRECT INSERT path the ingest login holds, and an edge is drawn "
   "from exactly that row")

# the per-call-site rows for the three sites these changes add
fu(site, "U14", "litkb/admit/front.py::record_discrepancy::_jsonb", _JSONB,
   what="the discrepancy's detail goes to the database without jsonb_safe: a NUL in a legacy title "
        "aborts the write")
fu(site, "U15", "litkb/use.py::write_use::_jsonb", _JSONB,
   what="a use's statement, rationale and feeds go to write_proposal without jsonb_safe")
fu(site, "U16", "litkb/commands.py::cmd_use::_labels", "(args.agent, args.session)",
   what="`use add` writes with unnormalised agent/session labels: an invisible character makes one "
        "session look like two")


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
    # Stage 3 (Docling), added at the P4 merge 2026-09-15. The docling branch forked before this
    # sink checker existed, so these two sites reach it for the first time here.
    "litkb/extract/colab_formula_worker.py::main::print": (6,
        "The Colab formula worker's per-shard progress, read at the merge of work/20260915-colab-l4-formula "
        "(2026-09-16). Four of the six are json.dumps of a FIXED key projection of the shard record — shard_id, "
        "status, slice_index/slice_of, n_crops, ok/failed/unstable/degenerate, regions_per_s, the load and "
        "re-decode seconds, peak_alloc_bytes, device_min_free_bytes, proc_plan: the keys are literals in the "
        "call, so no value outside that set can reach the sink. The other two are {'shard': sid, 'skipped': …} "
        "with sid a basename this function builds from the shard path, and {'model_load_seconds': float}. This "
        "module opens no socket and no database connection — it reads a shard archive, runs a local VLM and "
        "writes a result archive — so no credential is in scope in it at all. Its 'token' is the model's, "
        "never a secret."),
    "litkb/extract/colab_formula_worker.py::_write_step_log::print": (3,
        "The step log's own three lines: the PATH the records were written to (built from BASE / phase4 / logs, "
        "or the --log-dir the caller typed), and on the fallback branch the same path plus "
        "'STEP LOG FAILED: {type}: {e}' — the exception from os.makedirs or json.dump, which is a filesystem "
        "error about a path this function built. Same module as above: no credential is in scope."),
    "litkb/extract/formula_crop_worker.py::main::print": (2,
        "Two calls, read at the same merge. The --verify-crop line is json.dumps of Docling self_refs, booleans "
        "and two floats (images_scale, expansion_factor); the per-job line is a fixed four-key projection "
        "(file, status, n_crops, seconds) whose keys are literals. This worker runs inside the Docling venv, "
        "converts a PDF and writes crops to disk; it holds no database credential and no archive key."),
    "litkb/extract/docling.py::<module>::print": (1,
        "The hand loop's summary: json.dumps of the metrics dict extract() returns — page counts, seconds, "
        "pages_per_s, peak RSS, the source path the caller typed on the command line. This module holds no "
        "credential at all: it never connects to the database or the network, and the heavy tool runs as a "
        "subprocess in its own virtual environment."),
    "litkb/extract/docling_worker.py::main::print": (1,
        "One line per finished job: a fixed seven-key projection of the metrics dict — file, status, pages, "
        "seconds, pages_per_s, peak_rss_bytes, cpu_cores_busy. The keys are literals in this call, so no "
        "value outside that set can reach the sink. The worker runs in the Docling venv with no database "
        "credential and no archive key in scope."),
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
    "litkb/extract/inventory.py::run::print": (2,
        "Stage 0's progress lines: an index, a route word from the fixed ROUTES vocabulary, and the PDF's own "
        "basename. This module reads no credential at all — it opens files under Literture read-only and never "
        "connects to the database or the network."),
    "litkb/extract/inventory.py::main::print": (5,
        "Stage 0's summary: json.dumps of the derived counts (ints, route words, file basenames), the wall "
        "clock, and the two output paths inside the repo. Same reason as above — no secret is in scope in this "
        "module. The fifth call, re-read 2026-09-15 when --freeze-census was added, interpolates len(rows) — an "
        "int — and census_path(args.census), a path built from repo_root() or from the path the caller typed."),
    "litkb/extract/inventory.py::report_new::print": (4,
        "The --new report, added 2026-09-15. Four calls, interpolating: the literature root and the census path "
        "(both either module constants or what the caller typed on the command line), integer counts from "
        "collections.Counter, the fixed status vocabulary new/renamed/changed/missing, sha256 digests of file "
        "bytes, and corpus relpaths. Every one of those is a fact about a FILE. This function is the reason the "
        "module's reporting path prints instead of calling a bound stream .write: an aliased sink is invisible "
        "to this checker, so the call site is written to be visible to it and argued here."),
    "litkb/ops/nightly_dump.py::install_task::print": (1,
        "The first line of PowerShell's own output from Register-ScheduledTask. The command it ran embeds a task "
        "name and a script path, no credential."),
    # stage 6's ingest (migration 0020), appended 2026-09-15.
    "litkb/extract/references_ingest.py::main::print": (1,
        "json.dumps of the report load() builds, and that report is closed: the artifact directory the caller "
        "named, file stems and the refusal sentences built from them, the route words 'file-stem'/'works.key', "
        "and integer counts. Nothing on it comes from the network or from a credential — this module opens no "
        "socket, and its one connection goes through litkb.ingest.connect(), whose password libpq reads from the "
        "passfile and Python never sees."),
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


ONE_CAMPAIGN_LOCK = Path(os.environ.get("LITKB_HARNESS_LOCK", str(SCRIPTS / ".litkb-harness.lock")))


def take_lock(path=None):
    """ONE campaign per working tree. -> the lock path (release_lock() takes it back), or SystemExit naming the holder.

    A campaign edits the REAL sources in place, so two of them in one tree corrupt each other, and BOTH failure
    modes were seen live on 2026-09-15:
      * main() pre-flights every row's target against the file AS IT IS ON DISK, so a row whose target is
        currently mutated by the other campaign reads as "mutation target occurs 0 times" and aborts the WHOLE
        table - for a row that is perfectly sound;
      * worse, make_worker_copy() copytree's the tree as it is, so a mutant applied at that instant is inherited
        by every worker copy, and every verdict that comes back from it is wrong while saying nothing.
    The second one is silent, which is why this is a lock and not a convention.

    Workers do NOT take it: they run inside their own copies as children of the process that holds it (and the
    lock's own name is in COPY_IGNORE, so it is neither copied nor hashed into a worker's manifest).

    The lock is a file created O_EXCL carrying the holder's pid and start time, released by atexit. A process
    killed outright leaves it behind; the refusal prints what is in it, so a stale one can be read and removed by
    hand rather than guessed at."""
    p = Path(path or ONE_CAMPAIGN_LOCK)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            who = p.read_text(encoding="utf-8").strip()
        except OSError:
            who = ""
        raise SystemExit(f"another mutation campaign holds {p} ({who or 'nothing recorded in it'}): the harness "
                         f"edits the real sources in place, so two campaigns in one tree corrupt each other - a "
                         f"row whose target is mutated right now reads as 'occurs 0 times', and a worker copy "
                         f"made right now inherits the mutant silently. Wait for it, or delete that file if the "
                         f"process is gone.") from None
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(f"pid {os.getpid()} started {datetime.datetime.now().isoformat(timespec='seconds')}\n")
    return p


def release_lock(path=None):
    """Give the lock back. Releasing one that is already gone is not an error (atexit may run twice over)."""
    try:
        os.unlink(Path(path or ONE_CAMPAIGN_LOCK))
    except OSError:
        pass


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
COPY_IGNORE = ("__pycache__", ".pytest_cache", "*.pyc", "_litkb_ws", ".litkb-workstream",
               ".litkb-harness.lock")
# files copied individually AFTER copytree (they are not all under COPY_DIRS). The guard's domain must equal
# the copy's domain, so tree_manifest() hashes exactly this list too (referee 2 E-2, 2026-09-14): the repo-root
# .gitignore was copied and never hashed, so a stale one was invisible to manifest_diff.
#
# The two phase4/qc rows are here for the same class of reason and were added on 2026-09-15 by a FAILING
# BASELINE, not by reading: the corpus census was frozen to `phase4/qc/litkb_inventory_census.sha256`, which
# `inventory.repo_root()` resolves relative to the package — so inside a worker copy it resolves under the COPY,
# where phase4/ did not exist. Every corpus-backed inventory test errored and the E3inv row ran against a broken
# baseline. A test's whole read domain must be inside the copy; when a tracked input moves OUT of COPY_DIRS,
# it belongs on this list.
#
# And a THIRD time on 2026-09-16, at the P8 merge, found the same way — by a failing baseline, not by
# reading. P8's access layer put the skill, the librarian and the staged hook at the REPOSITORY ROOT
# (`.claude/`, design §9.1: Claude Code walks up from the session's cwd, so a root-level directory is
# what reaches a session opened in Scripts/), and `qc/test_litkb_p8.py` reads all three by path off
# SCRIPTS.parent. None of them is under COPY_DIRS, so inside a worker copy all three were missing and
# the P8 baseline ran at 14 failed / 43 passed — while the same file passes 60/60 in the real tree.
#
# That is worse than a wrong number, and it is why this list matters: `run_one` calls a mutation FIRED
# when the run has any failure at all, comparing nothing against the baseline. With a baseline already
# red, all nineteen X rows report FIRED whatever the mutation does. The separate baseline check is the
# only thing that caught it, and it did — "baselines FAILED", rc 1 from every worker.
#
# `.claude/settings.json` is deliberately NOT copied: it is git-ignored, it is the one file P8's
# design says must not carry the hook registration, and the test that checks it skips when it is
# absent. Copying a per-session, untracked file into a worker would make the verdict depend on
# whichever session last edited it.
COPY_FILES = (".gitignore", "Scripts/.gitignore",
              "phase4/qc/litkb_inventory_census.sha256", "phase4/qc/litkb_inventory.csv",
              ".claude/hooks/litkb_guard.py", ".claude/agents/librarian.md",
              ".claude/skills/literature/SKILL.md")


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
            (dst / gi).parent.mkdir(parents=True, exist_ok=True)   # phase4/qc/ is not under COPY_DIRS
            shutil.copy2(repo / gi, dst / gi)
    subprocess.run(["git", "init", "-q", str(dst)], check=True, capture_output=True)
    return dst


def run_workers(chosen, n, root, extra_args=(), worker_dbs=None):
    """Partition `chosen` round-robin over n workers, run each as a subprocess in its own copy against its own
    database, and return [(mutation, fired, summary)] in the original order plus whether every baseline passed.

    `worker_dbs` names WHICH worker databases to use, as indices (`[1, 2, 6, 8, 9]`). Default: 1..n. It exists
    because parallel worktrees share one Postgres server: another agent's session holds some of the nine, and a
    run that reset a database in use would destroy its work. The copies are still numbered 1..n; only the
    database each one is pointed at changes."""
    import concurrent.futures as cf
    import json
    import os
    import time

    from litkb.db.provision import worker_db

    if worker_dbs:
        n = min(n, len(worker_dbs))
    parts = partition(chosen, n)
    check_partition(parts, chosen)                 # D-5: a row lost in the split is named, not a KeyError
    n = len(parts)
    dbs = list(worker_dbs)[:n] if worker_dbs else list(range(1, n + 1))
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    src_manifest = root / "source.manifest.json"   # D-2: hashed ONCE, before any copy is made
    src_manifest.write_text(json.dumps(tree_manifest(SCRIPTS.parent), indent=0), encoding="utf-8")
    print(f"parallel: {len(chosen)} rows over {n} workers, copies under {root}")

    def one(i, rows):
        t0 = time.monotonic()
        copy = make_worker_copy(i, root)
        script = copy / "Scripts" / "qc" / "instruments" / Path(__file__).name
        env = dict(os.environ, LITKB_TEST_DB=worker_db(dbs[i - 1]), PYTHONUTF8="1",
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
            print(f"worker {i} ({worker_db(dbs[i - 1])}): {len(rows)} rows, {sum(fired.values())} fired, baselines "
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
    ap.add_argument("--worker-dbs", help="comma-separated worker-database indices to use (default 1..N). "
                                         "Parallel worktrees share one server: name only the databases no "
                                         "other session is holding, or a reset destroys its work")
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
    if not a.worker:
        # one campaign per tree, taken BEFORE the pre-flight below reads any target (see take_lock)
        atexit.register(release_lock, take_lock())
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
                                    extra_args=["--plant-equivalent"] if a.plant_equivalent else [],
                                    worker_dbs=[int(x) for x in a.worker_dbs.split(",")] if a.worker_dbs else None)
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
