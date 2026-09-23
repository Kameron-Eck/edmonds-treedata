"""S4 run 3, builder-D2 — retiring superseded run sets (migration 0031) and the per-page text of a
TOOL-text fragment (reconcile stage5-4): show each guard FIRE (CLAUDE.md 3.4c).

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w9 py -3.12 \
        qc/instruments/litkb_p2_mutations.py --only D2R1,D2R2,D2R3,D2R4,D2R5,D2R6,D2R7,D2R8,D2R9,D2R10,D2S1,D2F1,D2F2,D2F3,D2F4,D2F5

Rows are appended to the ONE shared ledger in `litkb_p2_mutations.py` at import (the arrangement
`litkb_s3a2_mutations.py` describes), in a file of their own so two S4 builders never append to the
end of the same file. Every row names `qc/test_litkb_retire.py` or `qc/test_litkb_reconcile.py` —
`tests` REPLACES the default set. Each row's kill is an ASSERTION in its test (auditor-D2 F2): a
refusal is caught and its class and words asserted, a bypassed CLI refusal reaches a login stub
that says so.

  * **D2R1-D2R4, D2R10** are the five `-- BEGIN guard` blocks of 0031: current run, evidence-cited
    run, not superseded, already retired, and set_current_run's refusal of a retired run.
  * **D2R3 is doubled by a constraint**: `run_retirements.superseded_by` is NOT NULL, so with the
    guard gone the op still fails — on a NotNullViolation instead of the guard's refusal, which the
    kill test asserts against. The constraint firing on its own is
    `test_the_not_null_superseded_by_is_the_backstop_under_the_superseded_guard`.
  * **D2R5-D2R9** are the rule's parts in `run_retirement_status`: the `evidence` verdict, the
    evidence boundary (one row holds a run — auditor A2), "only ok runs are superseded" (auditor
    A1), the stage-6 "newer run" check, and the UNION that counts each evidence row once (F4).
  * **D2S1** is the per-call-site row for `cmd_runs`' session label (textnorm.norm_label).
  * **D2F1-D2F5** are the fragment text: the fix itself, the fragment's piece, the two Docling join
    rules (hyphen, and the space-join check — auditor A3) and GROBID's sentence-start placement.
"""
MIG31 = "pipeline/litkb/db/migrations/0031_retire_runs.sql"
PKG = "pipeline/litkb"
T_RETIRE = ["qc/test_litkb_retire.py"]
T_REC = ["qc/test_litkb_reconcile.py"]


def register(block, replace, site):
    block("D2R1", MIG31, "guard: a file's current run is never retired",
          "retire_extraction_runs no longer refuses a file's CURRENT run itself (defence in depth: "
          "the superseded guard still refuses it, under the wrong name)", tests=T_RETIRE)
    block("D2R2", MIG31, "guard: a run use_evidence cites is never retired",
          "a run a prepared use quotes is marked retired", tests=T_RETIRE)
    block("D2R3", MIG31, "guard: only a run superseded at its stage is retired",
          "a run nothing superseded is handed to the INSERT; only the NOT NULL on superseded_by "
          "stops it, as a constraint error instead of the named refusal", tests=T_RETIRE)
    block("D2R4", MIG31, "guard: a run is retired once",
          "retiring a retired run again fails on the primary key instead of the named refusal",
          tests=T_RETIRE)
    block("D2R10", MIG31, "guard: a retired run never becomes current",
          "set_current_run moves the pointer back onto a retired run", tests=T_RETIRE)
    replace("D2R5", MIG31, "           WHEN j.evidence_rows > 0 THEN 'evidence'\n", "",
            "the verdict forgets evidence: the dry run lists a cited run as retirable and the op "
            "hands it to the database", tests=T_RETIRE)
    replace("D2R6", MIG31, "   WHERE s.evidence_rows > 0;\n", "   WHERE s.evidence_rows > 1;\n",
            "the evidence guard's boundary: a run cited by exactly ONE evidence row is retired",
            tests=T_RETIRE)
    replace("D2R7", MIG31, "             WHEN fa.status <> 'ok' THEN NULL\n", "",
            "a FAILED run older than an ok run at the current key is called superseded",
            tests=T_RETIRE)
    replace("D2R8", MIG31, "                   AND n.id <> fa.id AND n.created_at > fa.created_at\n",
            "                   AND n.id <> fa.id\n",
            "a caller naming an OLDER key as current makes the newer run superseded", tests=T_RETIRE)
    replace("D2R9", MIG31, "    SELECT e.id AS eid, e.run_id AS rid FROM use_evidence e\n    UNION\n",
            "    SELECT e.id AS eid, e.run_id AS rid FROM use_evidence e\n    UNION ALL\n",
            "evidence_rows counts an evidence row once per leg it is found by: the doubled count "
            "of auditor-D2 F4",
            tests=T_RETIRE)
    site("D2S1", "litkb/commands.py::cmd_runs::norm_label", "{a0}", tests=T_RETIRE,
         what="`runs retire --apply` takes a session label of invisible characters as a label: it "
              "is truthy and survives .strip(), so the op is signed by a session nobody can read")
    replace("D2F1", f"{PKG}/extract/reconcile.py",
            "chosen, how = text_for(page, box, own if own is not None else text, fragment=bool(info))",
            "chosen, how = text_for(page, box, text, fragment=bool(info))",
            "stage5-4 reverted: a tool-text fragment stores the WHOLE element under every page",
            tests=T_REC)
    replace("D2F2", f"{PKG}/extract/reconcile.py",
            '**({"piece": ("".join(pieces) if all(p is not None for p in pieces) else None)}',
            '**({"piece": None}',
            "union_boxes drops the fragment's piece: every fragment falls back to the element",
            tests=T_REC)
    replace("D2F3", f"{PKG}/extract/docling.py", "            starts.append(s - 2)\n",
            "            starts.append(s)\n",
            "a Docling hyphen join is read as a space join: the cut lands two characters late",
            tests=T_REC)
    replace("D2F4", f"{PKG}/extract/docling.py",
            '            if s < 1 or s > len(text) or text[s - 1] != " ":\n',
            "            if False:\n",
            "a span that says 'space join' over text with no space is cut anyway — a guessed cut",
            tests=T_REC)
    replace("D2F5", f"{PKG}/extract/grobid.py", "            where = _line_of(sb[0], boxes)\n",
            "            where = _line_of(sb[-1], boxes)\n",
            "a GROBID sentence over the break is placed on the page where it ENDS", tests=T_REC)
