"""Retiring a superseded extraction run set: migration 0030 and `litkb retire-runs` (S4).

267,545 of the 372,305 blocks on the 2026-09-21 live corpus (71.9 %) belonged to a run no file
points at, and every one of them carried `canonical = true`. Nothing in the schema said
"superseded": `extraction_runs.status` was `CHECK (status IN ('ok','failed'))`, there was no
`superseded_by` and no `retired_at`, and `clear_extraction_rows` refuses an `ok` run's rows
outright — so retiring a run set was not merely undone, it had no door at all. 0030 adds the third
status and the ONE function that may set it.

  what is tested                                                name
  the third status exists                                       test_a_run_may_be_superseded
  the current run is never retired                              test_retire_run_refuses_the_files_own_current_run
  a run a use quotes is never retired                           test_retire_run_refuses_a_run_a_use_is_anchored_in
  what retiring does, and what it does NOT do                   test_retire_run_uncanonicalises_its_blocks_and_deletes_nothing
  a retired block leaves every read path                        test_a_retired_blocks_text_leaves_the_search_predicate
                                                                test_a_retired_block_can_no_longer_anchor_a_quote
  retiring twice is a no-op                                     test_retiring_a_retired_run_is_a_no_op_not_a_refusal
  a run that does not exist                                     test_retire_run_refuses_a_run_that_does_not_exist
  the driver's counters                                         test_retire_runs_counts_the_census_then_applies_it
"""
import json
import uuid
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

QUOTE = "a sentence the first extraction found and the second one kept"


class KB:
    def __init__(self, psycopg, conn):
        self.psycopg, self.errors, self.conn = psycopg, psycopg.errors, conn
        self.tokens = {}

    def one(self, q, params=()):
        return self.conn.execute(q, params).fetchone()

    def jsonb(self, v):
        from psycopg.types.json import Jsonb
        return Jsonb(v)

    def ws(self, directory=None):
        ws_id, token = self.one(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/retire', %s, "
            "'retire test', NULL)",
            (f"rt-{uuid.uuid4().hex[:12]}", str(directory) if directory else None))
        self.tokens[ws_id] = token
        if directory:
            (Path(directory) / ".litkb-workstream").write_text(
                json.dumps({"workstream_id": str(ws_id), "token": token}), encoding="utf-8")
        return ws_id

    def kept(self):
        """The session connection with close() disarmed: `commands.main` and `retire_runs` each
        close the connection they are handed, and this one is the whole module's."""
        conn = self.conn

        class _Kept:
            def __getattr__(self, name):
                return getattr(conn, name)

            def close(self):
                pass
        return _Kept()


@pytest.fixture
def kb(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    return KB(psycopg, conn)


def _crossref(doi, title):
    return {"DOI": doi, "title": [title], "type": "journal-article",
            "container-title": ["A Journal"],
            "author": [{"family": "Tester", "given": "P.", "sequence": "first"}],
            "issued": {"date-parts": [[2024, 1]]}}


class _CrossrefStub:
    base = ""

    def __init__(self, records):
        self.records = {k.lower(): v for k, v in records.items()}

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        import urllib.parse
        if "api.crossref.org/works/" in url:
            rec = self.records.get(urllib.parse.unquote(url.split("/works/", 1)[1]).lower())
            return (200, {}, json.dumps({"message": rec}).encode()) if rec else (404, {}, b"")
        return 404, {}, b""


class _NoPace:
    def __getattr__(self, _n):
        return lambda *a, **k: None


def _bound_file(kb, ws):
    """An admitted work with ONE bound file and no run yet. -> (work_id, file_id, doi)."""
    from litkb.admit import front

    doi = f"10.5555/rt-{uuid.uuid4().hex[:10]}"
    title = f"A retire fixture {uuid.uuid4().hex[:10]}"
    res = front.admit_registry(kb.conn, ws, kb.tokens[ws], doi=doi, claimed=None, agent="agentR",
                               session="sessR", client=_CrossrefStub({doi: _crossref(doi, title)}),
                               pacer=_NoPace())
    assert res["outcome"] == "admitted", res
    fj = {"sha256": (uuid.uuid4().hex + uuid.uuid4().hex)[:64],
          "rel_path": f"_litkb_staging/filed/rt-{uuid.uuid4().hex[:8]}.pdf", "bytes": 2048,
          "pages": 4,
          "binding": {"verdict": "bound", "ratio": 0.99, "matched": title,
                      "registry_title": title, "author_found": True, "author_near_title": True,
                      "text_layer": True, "page": 1, "title_region": True}}
    att = kb.one("SELECT litkb.attach_file(%s, %s, %s, %s, %s, %s)",
                 (ws, kb.tokens[ws], res["work_id"], kb.jsonb(fj), "agentR", "sessR"))[0]
    assert att["outcome"] == "attached", att
    return res["work_id"], att["file_id"], doi


def _run(kb, file_id, text, *, version="v1", current=True):
    run = kb.one("SELECT litkb.open_extraction_run(%s, '5-reconcile', 'litkb-reconcile', %s, "
                 "'h1', %s, 'local', 'ok', NULL, '{}'::jsonb)", (file_id, version, version))[0]
    kb.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text, canonical, "
           "reading_order) VALUES (%s, %s, 1, 'paragraph', %s, true, 1) RETURNING id",
           (file_id, run, text))
    if current:
        prev = kb.one("SELECT current_run_id FROM litkb.files WHERE id = %s", (file_id,))[0]
        kb.one("SELECT litkb.set_current_run(%s, %s, %s)", (file_id, prev, run))
    return run


def _two_runs(kb, ws):
    """The live shape: run 1 is ok and superseded, run 2 is ok and current."""
    work_id, file_id, doi = _bound_file(kb, ws)
    old = _run(kb, file_id, f"preamble {QUOTE} tail", version="v1")
    new = _run(kb, file_id, f"preamble {QUOTE} tail, re-extracted", version="v2")
    return {"work_id": work_id, "file_id": file_id, "doi": doi, "old": old, "new": new}


# ── the schema ─────────────────────────────────────────────────────────────────────────────

@pg_only
def test_a_run_may_be_superseded(kb):
    """0001's CHECK named two statuses. `finish_extraction_run` still refuses anything but ok and
    failed — a run is FINISHED ok or failed and becomes superseded later, through one function."""
    d = kb.one("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
               "WHERE conname = 'extraction_runs_status_check'")[0]
    assert "superseded" in d and "'ok'" in d and "'failed'" in d
    with pytest.raises(kb.errors.InvalidParameterValue) as e:
        kb.one("SELECT litkb.finish_extraction_run(%s, 'superseded', NULL)",
               (str(uuid.uuid4()),))
    assert "neither ok nor failed" in str(e.value)


# ── the two refusals ───────────────────────────────────────────────────────────────────────

@pg_only
def test_retire_run_refuses_the_files_own_current_run(kb):
    """Retiring the pointer's own target leaves a file whose current run holds no canonical block:
    a work that reads `extracted` and answers nothing."""
    ws = kb.ws()
    w = _two_runs(kb, ws)
    with pytest.raises(kb.errors.InvalidParameterValue) as e:
        kb.one("SELECT litkb.retire_run(%s)", (w["new"],))
    assert "is the current run of file" in str(e.value)
    assert kb.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s AND canonical",
                  (w["new"],))[0] == 1


@pg_only
def test_retire_run_refuses_a_run_a_use_is_anchored_in(kb, tmp_path):
    """THE refusal this function exists for. `use_evidence` is the one of the eleven foreign keys
    into `blocks` that another actor wrote at another time; the other ten are rows of the same run.
    A use recorded against run 1 and then superseded by run 2 is exactly the live case — 6 of the
    676 superseded runs on the 2026-09-21 corpus are quoted this way."""
    from litkb import commands

    ws = kb.ws(tmp_path)
    work_id, file_id, doi = _bound_file(kb, ws)
    old = _run(kb, file_id, f"preamble {QUOTE} tail", version="v1")
    rc = commands.main(["--dir", str(tmp_path), "--agent", "agentR", "--session", "sessR",
                        "use", "add", "--doi", doi, "--statement", "it supplies the comparator",
                        "--kind", "method", "--feeds", "framework §13.1", "--quote", QUOTE],
                       connect=lambda _db: kb.kept())
    assert rc == 0
    assert kb.one("SELECT count(*) FROM litkb.use_evidence e JOIN litkb.blocks b ON b.id = "
                  "e.block_id WHERE b.run_id = %s", (old,))[0] == 1
    new = _run(kb, file_id, f"preamble {QUOTE} tail, re-extracted", version="v2")
    assert new != old
    with pytest.raises(kb.errors.InvalidParameterValue) as e:
        kb.one("SELECT litkb.retire_run(%s)", (old,))
    assert "use_evidence" in str(e.value)
    assert kb.one("SELECT status FROM litkb.extraction_runs WHERE id = %s", (old,))[0] == "ok"


@pg_only
def test_retire_run_refuses_a_run_that_does_not_exist(kb):
    with pytest.raises(kb.errors.ForeignKeyViolation) as e:
        kb.one("SELECT litkb.retire_run(%s)", (str(uuid.uuid4()),))
    assert "no extraction run" in str(e.value)


# ── what retiring does ─────────────────────────────────────────────────────────────────────

@pg_only
def test_retire_run_uncanonicalises_its_blocks_and_deletes_nothing(kb):
    """Design §12.4, no deletes: the row, the metrics, the blocks and every child row stay. What
    changes is that the run SAYS it is superseded and its blocks say they are not canonical."""
    ws = kb.ws()
    w = _two_runs(kb, ws)
    before = kb.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (w["old"],))[0]
    assert kb.one("SELECT litkb.retire_run(%s)", (w["old"],))[0] == before
    assert kb.one("SELECT status FROM litkb.extraction_runs WHERE id = %s",
                  (w["old"],))[0] == "superseded"
    assert kb.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s", (w["old"],))[0] == before
    assert kb.one("SELECT count(*) FROM litkb.blocks WHERE run_id = %s AND canonical",
                  (w["old"],))[0] == 0


@pg_only
def test_retiring_a_retired_run_is_a_no_op_not_a_refusal(kb):
    """`retire-runs --apply` re-run over the same file must be safe: the second call has nothing
    to do rather than something to complain about."""
    ws = kb.ws()
    w = _two_runs(kb, ws)
    assert kb.one("SELECT litkb.retire_run(%s)", (w["old"],))[0] >= 1
    assert kb.one("SELECT litkb.retire_run(%s)", (w["old"],))[0] == 0


@pg_only
def test_a_retired_blocks_text_leaves_the_search_predicate(kb):
    """`canonical = false` MEANS not searchable, and that is one predicate at every read site
    (`readability.current_run_join`). Asked here as the search asks it."""
    from litkb import readability

    ws = kb.ws()
    work_id, file_id, _doi = _bound_file(kb, ws)
    only_old = f"a line the second extraction lost {uuid.uuid4().hex[:8]}"
    old = _run(kb, file_id, only_old, version="v1")
    sql = ("SELECT count(*) FROM litkb.blocks b " + readability.current_run_join() +
           " WHERE b.text = %s")
    assert kb.one(sql, (only_old,))[0] == 1                 # current and canonical
    _run(kb, file_id, "the second extraction's own text", version="v2")
    assert kb.one(sql, (only_old,))[0] == 0                 # superseded: out by the run join
    kb.one("SELECT litkb.retire_run(%s)", (old,))
    assert kb.one("SELECT count(*) FROM litkb.blocks b WHERE b.canonical AND b.text = %s",
                  (only_old,))[0] == 0                      # and out by canonical alone
    assert kb.one("SELECT count(*) FROM litkb.blocks b WHERE b.text = %s", (only_old,))[0] == 1


@pg_only
def test_a_retired_block_can_no_longer_anchor_a_quote(kb):
    """`use.locate_quote` reads the same fragment, so the CLI cannot end up able to quote text the
    search cannot find — which is the reason the join has one home."""
    from litkb import use as _use

    ws = kb.ws()
    work_id, file_id, _doi = _bound_file(kb, ws)
    text = f"preamble {QUOTE} tail {uuid.uuid4().hex[:8]}"
    old = _run(kb, file_id, text, version="v1")
    assert _use.locate_quote(kb.conn, work_id, QUOTE, ws=ws)
    kb.conn.execute("UPDATE litkb.files SET current_run_id = NULL WHERE id = %s", (file_id,))
    _run(kb, file_id, "the second extraction lost it", version="v2")
    kb.one("SELECT litkb.retire_run(%s)", (old,))
    assert _use.locate_quote(kb.conn, work_id, QUOTE, ws=ws) == []


# ── the driver ─────────────────────────────────────────────────────────────────────────────

@pg_only
def test_retire_runs_counts_the_census_then_applies_it(kb, tmp_path):
    """Dry run is the DEFAULT and changes nothing (`reap`'s rule); `--apply` retires what the
    census listed, and a referenced run is excluded from both by the same EXISTS the function
    refuses on."""
    from litkb import commands

    ws = kb.ws(tmp_path)
    w = _two_runs(kb, ws)
    counters, rows = commands.retire_runs(kb.conn, apply=False, file_id=w["file_id"])
    assert counters["files"] == 1 and counters["runs_superseded"] == 1
    assert counters["blocks_retired"] == 0 and counters["refused_referenced"] == 0
    assert [r["verdict"] for r in rows] == ["would-retire"]
    assert kb.one("SELECT status FROM litkb.extraction_runs WHERE id = %s", (w["old"],))[0] == "ok"

    counters, rows = commands.retire_runs(kb.conn, apply=True, file_id=w["file_id"],
                                          ingest_connect=lambda _db: kb.kept())
    assert counters["runs_superseded"] == 1 and counters["blocks_retired"] == 1
    assert counters["skipped_errors"] == 0 and counters["refused_current"] == 0
    assert [r["verdict"] for r in rows] == ["retired"]
    assert kb.one("SELECT status FROM litkb.extraction_runs WHERE id = %s",
                  (w["old"],))[0] == "superseded"
    # and the census is now empty for that file: nothing left to do, said by the same query
    assert commands.retire_runs(kb.conn, apply=False, file_id=w["file_id"])[0]["runs_superseded"] == 0
