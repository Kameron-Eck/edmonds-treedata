"""S4 — the extraction queue: show every guard of migration 0029 and `litkb.queue` FIRE
(CLAUDE.md §3.4c). Rows authored here, appended to the ONE shared ledger at import.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w7 py -3.12 \\
        qc/instruments/litkb_p2_mutations.py --only \\
        S4Q1G0,S4Q1L1,S4Q1L2,S4Q1L3,S4Q1L4,S4Q1U1,S4Q1P1,S4Q1P2,S4Q1O1,S4Q1Z1

Same machinery and the same table as the P6 / S2 / S3 legs; its own file so that S4's three
builders do not all append to the end of one module (`litkb_s3a2_mutations.py`'s reason, and the
S4 brief names this file as Q1's).

Every row's test set is `qc/test_litkb_queue.py` alone — `tests` REPLACES the default, it does not
extend it — because that file is the whole of what these guards are asserted by, and the P2 suite
knows nothing about them. The MIGRATION rows (G0, L1-L4, U1) work because `qc/conftest.py`'s
`litkb_pg_base` fixture does `migrate.reset()` then `migrate.apply()` at the start of every pytest
session: the mutated 0029 is applied to the worker database for that run, and the unmutated one is
applied again on the next.

WHAT EACH ROW IS FOR:

  * **S4Q1G0 is the ownership gate itself** — the body of `litkb._job_lease_held`, emptied so the
    function returns without checking anything. This is the brief's "ownership gate removed": the
    lease test goes GREEN when it must be RED, which is the only way to show that the gate, and
    not something else in the function, is what refuses the expired holder. It is one row and the
    four rows below are four more, on the base brief's per-CALL-SITE rule: the gate is a helper,
    and a call site that forgot to call it is a hole the helper's own test cannot see. That is not
    hypothetical here — `finish_job` and `classify_job` are the two that end a job, `fail_job`
    returns it to the pool and `renew_lease` extends it, and any one of them reachable without a
    live lease lets a worker that was paused, swapped out or simply slow overwrite the verdict of
    the second worker now holding the job.
  * **S4Q1U1 removes the UNIQUE index**, which is where "a repeated sweep is a no-op" actually
    lives. There is no Python-side dedup, deliberately: two sweeps racing each other cannot both
    be stopped by a check in one of them. Without the index the sweep's `ON CONFLICT` has no
    arbiter to name, so the second sweep fails loudly instead of quietly enqueuing a second job
    per file — the guard is gone either way, and the test that asserts `new_queued == 0` on the
    second sweep is what says so.
  * **S4Q1P1 blinds the page probe** (`pages = 0` instead of the probe and its two refusals), so a
    file whose page count cannot be read is converted anyway. That is the 400-page binding cap's
    failure mode exactly (`admit.binding.ocr_first_pages` — a non-digit page count skips the
    OCR_BIND_MAX_PAGES check and OCR runs uncapped), reproduced one layer up. **S4Q1P2 keeps the
    probe and drops the CAP's refusal**: the call still happens, its answer is thrown away. Two rows because they are two
    different holes — one lets an unreadable file through, the other a 700-page book.
  * **S4Q1O1 keeps the OCR policy call and discards its verdict.** A scan then goes to Docling
    with OCR off, which SUCCEEDS and yields no body block: "extracted, 0 chars", the outcome that
    is indistinguishable in the database from a file with nothing to say. The row proves the
    refusal is what stops it, not the converter.
  * **S4Q1Z1 removes the zero-block guard** from `extract/ingest.py`. Note what it fires THROUGH:
    migration 0017's `finish_extraction_run` already refuses to mark a `5-reconcile` run `ok` with
    no blocks, so the mutated ingest raises from Postgres instead of moving the pointer. That is
    the point of the row rather than an accident — 0017 can REFUSE the bad run and cannot
    CLASSIFY it, so without this guard the outcome is an exception with a constraint's name on it
    and no `zero-content` row anywhere.
"""
PKG = "pipeline/litkb"
MIG29 = f"{PKG}/db/migrations/0029_extraction_jobs.sql"
TESTS_S4Q1 = ["qc/test_litkb_queue.py"]
IDS = ["S4Q1G0", "S4Q1L1", "S4Q1L2", "S4Q1L3", "S4Q1L4", "S4Q1U1",
       "S4Q1P1", "S4Q1P2", "S4Q1O1", "S4Q1Z1"]

_GATE = "  PERFORM litkb._job_lease_held(p_job, p_token);\n"


def register(block, replace, site):
    # `site` is part of the registrar signature the P2 ledger passes; this leg targets no helper
    # in HELPERS, so it registers no per-call-site row through it. The four call-site rows below
    # are plain `replace`s because the guard is a SQL PERFORM, not a Python call the AST rewriter
    # can find.
    del site

    block("S4Q1G0", MIG29, "guard: a job is mutated only by the holder of its live lease",
          "`_job_lease_held` returns without looking at the row: every mutating function accepts "
          "any token, including none. A worker whose lease expired finishes the job a SECOND "
          "worker is now extracting, and the two write one file's rows under two runs — the race "
          "`open_extraction_run` makes idempotent but not exclusive, and the loser's "
          "`clear_extraction_rows` can delete the winner's rows while the winner's run is still "
          "`failed`", tests=TESTS_S4Q1)

    replace("S4Q1L1", MIG29,
            _GATE + "  IF coalesce(p_lease_seconds, 0) <= 0 THEN\n"
                    "    RAISE EXCEPTION 'litkb: a lease lasts a positive number of seconds, got %', p_lease_seconds\n",
            "  IF coalesce(p_lease_seconds, 0) <= 0 THEN\n"
            "    RAISE EXCEPTION 'litkb: a lease lasts a positive number of seconds, got %', p_lease_seconds\n",
            "`renew_lease` no longer checks the token: anyone may extend anyone's lease, so the "
            "expiry that returns a dead worker's job to the pool can be pushed out forever by the "
            "worker that died — or by a stale heartbeat thread that outlived its own job",
            tests=TESTS_S4Q1)

    replace("S4Q1L2", MIG29,
            _GATE + "  -- BEGIN guard: a finished job's run is a run of the job's own file\n",
            "  -- BEGIN guard: a finished job's run is a run of the job's own file\n",
            "`finish_job` no longer checks the token: the worker whose lease ran out marks the "
            "job done and points it at ITS run, while the second worker is still converting. The "
            "queue then says the file is extracted and names a run that is not the file's current "
            "one", tests=TESTS_S4Q1)

    replace("S4Q1L3", MIG29,
            _GATE + "  UPDATE extraction_jobs j\n"
                    "     SET state = CASE WHEN j.attempts >= greatest(coalesce(p_max_attempts, 3), 1)\n",
            "  UPDATE extraction_jobs j\n"
            "     SET state = CASE WHEN j.attempts >= greatest(coalesce(p_max_attempts, 3), 1)\n",
            "`fail_job` no longer checks the token: a worker that lost its lease can return to "
            "the queue — or KILL as dead, with a `failed` run row — a job another worker is "
            "finishing successfully at that moment", tests=TESTS_S4Q1)

    replace("S4Q1L4", MIG29,
            _GATE + "  IF p_residue IS NULL THEN\n",
            "  IF p_residue IS NULL THEN\n",
            "`classify_job` no longer checks the token: a stale worker can write a terminal "
            "residue class — `bad-file`, `scan-needs-ocr` — over a job that is being extracted "
            "successfully, and a classified job is never claimed again, so the file stays "
            "unreadable with a reason that was never true", tests=TESTS_S4Q1)

    replace("S4Q1U1", MIG29,
            "CREATE UNIQUE INDEX extraction_jobs_key ON extraction_jobs\n",
            "CREATE INDEX extraction_jobs_key ON extraction_jobs\n",
            "the run key stops being unique, which is the whole of \"a repeated sweep is a "
            "no-op\": nothing in Python dedups, because two sweeps racing each other cannot both "
            "be stopped by a check inside one of them", tests=TESTS_S4Q1)

    replace("S4Q1P1", f"{PKG}/queue.py",
            '        try:\n'
            '            pages = self.policy.probe_pages(path)\n'
            '        except getattr(self.policy, "ProbeFailed", Exception) as e:\n'
            '            return self._classify(ctl, job, "bad-file",\n'
            '                                  f"page-count probe failed: {getattr(e, \'reason\', e)}")\n'
            '        except Exception as e:                                     # noqa: BLE001\n'
            '            return self._classify(ctl, job, "bad-file",\n'
            '                                  f"page-count probe raised {type(e).__name__}: {e}"[:400])\n',
            '        pages = 0\n',
            "the page probe is gone and with it the fail-closed rule: a file whose pages cannot be "
            "counted — a truncated download, an HTML error page saved as .pdf, an encrypted PDF — "
            "goes to GROBID and Docling anyway, and `bad-file` is never written. This is the "
            "400-page binding cap's own failure mode (admit.binding.ocr_first_pages falls "
            "THROUGH on a non-digit page count) reproduced one layer up", tests=TESTS_S4Q1)

    replace("S4Q1P2", f"{PKG}/queue.py",
            '        capped = self.policy.cap_check(pages)\n'
            '        if capped:\n'
            '            return self._classify(ctl, job, capped,\n'
            '                                  f"{pages} pages is over the extraction cap "\n'
            '                                  f"({getattr(self.policy, \'PAGE_CAP\', \'?\')})")\n',
            '        self.policy.cap_check(pages)\n',
            "the cap is consulted and its answer thrown away — the shape of a check that reads as "
            "present in a diff. A document over the cap is converted: on this card that is the "
            "688-page book at 16.6 min of CPU, or an OCR batch whose VRAM peak is a property of "
            "the batch's LENGTH (the measurement block above extract.docling.OCR_PAGE_BATCH), and `over-page-cap` never appears",
            tests=TESTS_S4Q1)

    replace("S4Q1O1", f"{PKG}/queue.py",
            "        if decision != \"run\":\n"
            "            return self._classify(\n"
            "                ctl, job, arg,\n"
            "                f\"{len(ocr_pages)} of {pages} pages need OCR and the readiness policy refused \"\n"
            "                f\"(ocr={'on' if self.ocr else 'off'}, route={rec['route']})\")\n",
            "        arg = arg if decision == \"run\" else None\n",
            "the OCR policy is called and its refusal discarded: a scan is sent to Docling with "
            "OCR off, which SUCCEEDS and returns no body block. That lands as \"extracted, 0 "
            "chars\" — a file the database cannot tell from one that genuinely says nothing, and "
            "the exact outcome the four live scans (Anderson, Hudson, Hwang, Ogata) are waiting "
            "for a verdict on", tests=TESTS_S4Q1)

    block("S4Q1Z1", f"{PKG}/extract/ingest.py",
          "guard: a run with no canonical block never becomes the file's current run",
          "a reconciliation that produced nothing is finished `ok` and `set_current_run` is "
          "called on it. Migration 0017's own guard refuses the `ok` — so the visible effect is "
          "an exception carrying a constraint's name, and NO `zero-content` classification "
          "anywhere: 0017 can refuse the bad run, it cannot say what happened to the file",
          tests=TESTS_S4Q1)
