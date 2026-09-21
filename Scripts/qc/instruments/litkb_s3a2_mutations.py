"""S3 phase 1 — the `absent` split, `litkb_acquire`'s detail and the staging reaper: show each
guard FIRE (CLAUDE.md 3.4c).

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w8 py -3.12 \
        qc/instruments/litkb_p2_mutations.py --only S3A1,S3A2,S3A3,S3A4,S3R1,S3R2,S3R3

Same machinery and the same table as the P6 / S2 legs (`litkb_p6_mutations.py`,
`litkb_s2_mutations.py`): the rows are appended to the ONE shared ledger at import, because the
per-call-site rule covers the whole package and a second self-check would see half of it. They
live in their own file so that two builders working the same stage do not both append to the end
of `litkb_p2_mutations.py`.

WHAT EACH ROW IS FOR:

  * **S3A1 / S3A2 are the two halves of the `absent` split**, and they are separate rows because
    they are two different reads answering two different questions. S3A1 deletes the caller's OWN
    workstream leg: a work this worktree proposed an hour ago goes back to `never-admitted`, and
    the next move it is handed — admit it — is the one admission's check 2 refuses as a duplicate
    identifier. S3A2 deletes the OTHER-workstream leg, which is the kill the brief names: the work
    admitted in workstream X, asked from workstream Y, must never come back `never-admitted`.
    Neither test covers the other's row: the first answers from `ws_identifiers`/`ws_works` under
    the caller's own view, the second from `identifier_versions`/`work_versions` across open
    workstreams, and a session reading the wrong one of those is told its own knowledge base holds
    somebody else's work.
  * **S3A3 restores the one line that was there**, `out = {k: v for k, v in out.items() if k !=
    "detail"}`, immediately before the return. `run.acquire` sets `detail` on exactly the two
    outcomes that have one (`ok`, `duplicate-held`), so that comprehension dropped the sha256, the
    byte count, the binding verdict, the source URL and the filed path on the two calls that
    landed a file — and on every other outcome it was a no-op, which is why it read as harmless.
  * **S3A4 empties the attempt read** rather than deleting it: deleting the statement leaves `rows`
    unbound and the tool fails with a NameError, which "fires" for a reason that is not the defect
    (the RC16 note). Empty is the defect exactly as it was — `attempts` is (route, status) pairs
    and the per-route `detail` each attempt wrote went only to the database.
  * **S3R1 / S3R2 / S3R3 are the reaper's three refusals**, one row each because each alone is the
    difference between a census and a data loss. S3R1 removes ownership: a file whose sha256 IS in
    `litkb.files`, or whose path a `file_versions.rel_path` names, becomes an orphan — the four
    byte-known files in `incoming/` and the sixteen `t*.download` rows a hunt is still working on
    (S3 data survey §9), all quarantined. S3R2 removes the age window: `incoming/` is a WORKING
    directory and a download in flight has no row yet either, so without it the reaper races the
    acquisition it is cleaning up after. S3R3 removes the dry-run gate, which is the one that makes
    `--apply` a decision rather than a default.
"""
PKG = "pipeline/litkb"
TESTS_S3A = ["qc/test_litkb_s3_server.py"]
TESTS_S3R = ["qc/test_litkb_reaper.py"]
IDS = ["S3A1", "S3A2", "S3A2b", "S3A3", "S3A4", "S3R1", "S3R2", "S3R3"]


def register(block, replace, site):
    # `site` is part of the registrar signature the P2 ledger passes (litkb_s2_mutations does the
    # same); this leg adds no per-call-site row because it targets no helper in HELPERS.
    del site
    block("S3A1", f"{PKG}/mcp/server.py",
          "guard: a work the caller's OWN workstream holds is in-this-workstream",
          "a work THIS worktree proposed and no second session has approved comes back "
          "`never-admitted` again, with 'admit it' as the next move — which check 2 then refuses "
          "as a duplicate identifier, telling the session its own proposal is somebody else's "
          "work. `ws_state` disappears with it, so the rung the work HAS reached is unreadable",
          tests=TESTS_S3A)
    block("S3A2", f"{PKG}/mcp/server.py",
          "guard: an identifier another workstream holds is in-another-workstream",
          "THE kill this split exists for: a work admitted in workstream X, asked from workstream "
          "Y, is `never-admitted` again — the one answer that is certainly wrong, because the "
          "admission it invites is refused as a duplicate and no read from this worktree can show "
          "why", tests=TESTS_S3A)
    replace("S3A2b", f"{PKG}/mcp/server.py",
            "\"   AND v.state = 'proposed' AND v.status = 'active' \"",
            "\"   AND v.state = 'proposed' AND v.status = 'active' AND w.state = 'open' \"",
            "the third bucket filters on the holder's state again (the S3 phase-1 audit's defect): an "
            "identifier a workstream ABANDONED while holding it `proposed` answers `never-admitted`, "
            "inviting the admission check 2 refuses as a duplicate — the tool and the gate read "
            "different rows", tests=TESTS_S3A)
    replace("S3A3", f"{PKG}/mcp/server.py",
            '    return _out({"ok": out.get("outcome") in ("ok", "already-held"), "key": work["key"],',
            '    out = {k: v for k, v in out.items() if k != "detail"}\n'
            '    return _out({"ok": out.get("outcome") in ("ok", "already-held"), "key": work["key"],',
            "the strip line is back where it was: `litkb_acquire` drops `detail` on exactly the "
            "two outcomes that have one, so a call that LANDED a file returns no sha256, no byte "
            "count, no binding verdict, no source URL and no filed path", tests=TESTS_S3A)
    replace("S3A4", f"{PKG}/mcp/server.py",
            '            " WHERE work_id = %s AND at >= %s ORDER BY at", (work["work_id"], t0)).fetchall()',
            '            " WHERE work_id = %s AND at >= %s ORDER BY at", (work["work_id"], t0)).fetchall()[:0]',
            "`attempts_detail` comes back empty: the caller is back to (route, status) pairs and "
            "the reason each route failed stays in a table no MCP session can read",
            tests=TESTS_S3A)
    block("S3R1", f"{PKG}/ops/reaper.py",
          "guard: a file the database accounts for by sha or by path is never reaped",
          "ownership is gone: a file whose sha256 IS a litkb.files row, and a file whose path a "
          "file_versions.rel_path names, are both quarantined. That is the four byte-known "
          "downloads in incoming/ and the sixteen t*.download rows a hunt is still working on — "
          "bytes the corpus holds, moved out from under it", tests=TESTS_S3R)
    block("S3R2", f"{PKG}/ops/reaper.py",
          "guard: a file younger than the age window, or held open, is never reaped",
          "the age window is gone: incoming/ is a WORKING directory and a download in flight has "
          "no files row yet, so the reaper quarantines the acquisition that is running beside it",
          tests=TESTS_S3R)
    block("S3R3", f"{PKG}/ops/reaper.py", "guard: a dry run moves nothing",
          "--dry-run stops being a dry run: the default invocation quarantines, and the census a "
          "caller ran to LOOK at staging is the call that emptied it", tests=TESTS_S3R)
