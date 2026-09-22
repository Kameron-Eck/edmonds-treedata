"""S4 — the database-visible quarantine state (migration 0030, `litkb.quarantine`).

Until S4 `_quarantine/` was a directory and nothing else: the status and the sha lived in the
FILENAME, no code read it back, and `hunt.land_download` and the staging reaper left no database
row at all. These tests hold the new state to its contract:

  vocabulary   the CHECKs in 0030 are exactly `quarantine.REASONS` / `ORIGINS` (one home)
  writers      the writer function needs the token and takes only the workstream origins; the
               system function (ingest) takes only the system origins; neither role writes the
               table directly (the role matrix, qc/test_litkb_p1.py)
  idempotent   one row per PATH; the same path offered with other bytes is refused
  every write  acquisition (route guard, bind refusal, --from-file), the bind probe (landed, in
               place, admission), hunt's land_download and its URL-path probe refusal each leave a
               row; a row that cannot be written never loses the bytes and is reported
  backfill     the dry run writes nothing; --apply writes one row per payload with its links;
               a label outside the vocabulary is counted `unmapped`, never defaulted
  known-bads   fire_quarantine (a payload planted with no row -> the counter moves by one) and
               fire_probe (a CONSTRUCTED unopenable PDF through the bind path -> refused, never
               bound; with the guard mutated off it BINDS with pages NULL)

Every file here lives under pytest's tmp_path; the real literature root is never written.

    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w9 py -3.12 -m pytest qc/test_litkb_quarantine.py -q
"""
import hashlib
import importlib.util
import json
import re
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
pg_only = pytest.mark.requires_litkb_pg


def _p2():
    """P2's helpers (the one-page PDF builder, the route stub, the synthetic admission), loaded by
    path — the same way qc/test_litkb_p8.py reaches them. Two builders would drift."""
    spec = importlib.util.spec_from_file_location("_litkb_p2_for_quarantine", SCRIPTS / "qc" / "test_litkb_p2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P2M = _p2()


@pytest.fixture
def pg(litkb_pg_base):
    psycopg, conn, _ran = litkb_pg_base
    h = P2M.P2(psycopg, conn)
    yield h
    while h.opened:
        h.opened.pop().close()


def _store(tmp_path):
    from litkb.acquire.store import Store

    root = tmp_path / "Lit"
    (root / "Validation").mkdir(parents=True, exist_ok=True)
    return Store(root, index_cache=tmp_path / "index.json")


def _rows(pg, **where):
    k, v = next(iter(where.items()))
    return pg.conn.execute(
        f"SELECT rel_path, sha256, bytes, reason, origin, work_id::text, file_id::text, attempt_id::text, "
        f"workstream_id::text, detail FROM litkb.quarantine_payloads WHERE {k} = %s ORDER BY recorded_at, id",
        (v,)).fetchall()


def _unopenable():
    """CONSTRUCTED (`readability._constructed_unopenable_pdf`), salted per call: `files.sha256` is
    UNIQUE across the shared worker database."""
    from litkb import readability as R

    return R._constructed_unopenable_pdf(salt=uuid.uuid4().hex)


# ── the vocabulary has one home ───────────────────────────────────────────────────────────────

@pg_only
def test_the_check_constraints_are_the_python_vocabularies(pg):
    from litkb import quarantine as Q

    defs = dict(pg.conn.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'litkb.quarantine_payloads'::regclass AND contype = 'c'").fetchall())
    reason = next(d for n, d in defs.items() if "reason" in d and "ANY" in d and "origin" not in d)
    origin = next(d for n, d in defs.items() if d.lstrip().startswith("CHECK ((origin = ANY"))
    assert re.findall(r"'([a-z0-9-]+)'::text", reason) == list(Q.REASONS), reason
    assert re.findall(r"'([a-z0-9-]+)'::text", origin) == list(Q.ORIGINS), origin
    assert set(Q.WRITER_ORIGINS) | set(Q.SYSTEM_ORIGINS) == set(Q.ORIGINS)
    assert not set(Q.WRITER_ORIGINS) & set(Q.SYSTEM_ORIGINS)


def test_every_label_a_store_call_site_writes_is_a_reason():
    """The labels acquisition, hunt and the reaper put in a quarantined NAME (store.pdf_shape's
    shapes, the route statuses returned with bytes, the binding verdicts, the attach outcomes, the
    reaper's word, the legacy annas labels) are all reasons, so reading a name back never lands
    outside the vocabulary."""
    from litkb import quarantine as Q
    from litkb.ops import reaper

    labels = {"not-a-pdf", "truncated-pdf", "blocked", "bad-file", "not-in-archive", "partner-404",
              "hash-mismatch", "binding-failed", "binding-pending", "duplicate-held", "duplicate-hash",
              "content-mismatch", reaper.QUARANTINE_LABEL, "probe-error"}
    assert labels <= set(Q.REASONS), labels - set(Q.REASONS)


def test_a_quarantine_name_parses_back_to_its_label():
    from litkb import quarantine as Q

    sha = "a3b93f589df6"
    assert Q.parse_name(f"Chen_2023_urban-tree__blocked__{sha}.pdf")["label"] == "blocked"
    assert Q.parse_name(f"Chen_2023_urban-tree__blocked__{sha}.2.pdf")["label"] == "blocked"
    assert Q.parse_name(f"Averkov_2009_x.2__staging-orphan__{sha}.pdf")["stem"] == "Averkov_2009_x.2"
    md5 = "73543a97140df1be662267e0a29c218c"
    assert Q.parse_name(f"Page_1954_x__content-mismatch__{md5}.pdf")["label"] == "content-mismatch"
    assert Q.parse_name("Bellettini_2002_total-variation-flow-garbled.stray-recovered.pdf") is None
    assert Q.origin_of_label("binding-failed") == "bind-refusal"
    assert Q.origin_of_label("blocked") == "acquisition-guard"


# ── the two writers ───────────────────────────────────────────────────────────────────────────

def _sha():
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


@pg_only
def test_the_writer_row_needs_the_token_and_a_workstream_origin(pg):
    from litkb import quarantine as Q

    ws, w = pg.ws(), pg.session("litkb_writer")
    rel = f"_quarantine/W_2026_x__blocked__{uuid.uuid4().hex[:12]}.pdf"
    rid = Q.record(w, ws, pg.tokens[ws], rel_path=rel, sha256=_sha(), nbytes=10, reason="blocked",
                   origin="acquisition-guard")
    assert rid and _rows(pg, rel_path=rel)[0][3:5] == ("blocked", "acquisition-guard")
    assert _rows(pg, rel_path=rel)[0][8] == str(ws), "a writer row belongs to its workstream"
    with pytest.raises(pg.errors.InsufficientPrivilege, match="token refused"):
        Q.record(w, ws, "not-the-token", rel_path=rel + ".x", sha256=_sha(), nbytes=1, reason="blocked",
                 origin="acquisition-guard")
    with pytest.raises(pg.errors.InsufficientPrivilege, match="system origin"):
        Q.record(w, ws, pg.tokens[ws], rel_path=rel + ".y", sha256=_sha(), nbytes=1,
                 reason="staging-orphan", origin="reaper")
    with pytest.raises(pg.errors.InsufficientPrivilege):          # no EXECUTE on the system writer
        Q.record_system(w, rel_path=rel + ".z", sha256=_sha(), nbytes=1, reason="staging-orphan",
                        origin="reaper")
    with pytest.raises(pg.errors.InsufficientPrivilege):          # and no direct write on the table
        w.execute("INSERT INTO litkb.quarantine_payloads (rel_path, sha256, bytes, reason, origin, workstream_id) "
                  "VALUES (%s, %s, 1, 'blocked', 'acquisition-guard', %s)", (rel + ".w", _sha(), ws))


@pg_only
def test_the_system_row_takes_only_system_origins_and_the_in_place_rule_holds(pg):
    from litkb import quarantine as Q

    ing = pg.session("litkb_ingest")
    rel = f"_quarantine/S_2026_x__staging-orphan__{uuid.uuid4().hex[:12]}.download"
    assert Q.record_system(ing, rel_path=rel, sha256=_sha(), nbytes=3, reason="staging-orphan", origin="reaper")
    assert _rows(pg, rel_path=rel)[0][8] is None, "a system row belongs to no workstream"
    with pytest.raises(pg.errors.InsufficientPrivilege, match="needs a workstream token"):
        Q.record_system(ing, rel_path=rel + ".2", sha256=_sha(), nbytes=1, reason="blocked",
                        origin="acquisition-guard")
    # a path OUTSIDE _quarantine/ is a file refused where it lies: only the classifier (with a file_id)
    with pytest.raises(pg.errors.CheckViolation):
        Q.record_system(ing, rel_path="Validation/somewhere.pdf", sha256=_sha(), nbytes=1,
                        reason="staging-orphan", origin="reaper")
    with pytest.raises(pg.errors.CheckViolation):
        Q.record_system(ing, rel_path="Validation/somewhere.pdf", sha256=_sha(), nbytes=1,
                        reason="zero-content", origin="classifier")        # no file_id
    with pytest.raises(pg.errors.CheckViolation):
        Q.record_system(ing, rel_path=rel + ".3", sha256=_sha(), nbytes=1, reason="no-such-reason",
                        origin="reaper")


@pg_only
def test_a_row_is_idempotent_on_its_path_and_one_path_holds_one_payload(pg):
    from litkb import quarantine as Q

    ing = pg.session("litkb_ingest")
    rel, sha = f"_quarantine/I_2026_x__legacy__{uuid.uuid4().hex[:12]}.pdf", _sha()
    a = Q.record_system(ing, rel_path=rel, sha256=sha, nbytes=5, reason="legacy", origin="legacy-backfill")
    b = Q.record_system(ing, rel_path=rel, sha256=sha, nbytes=5, reason="legacy", origin="legacy-backfill")
    assert a == b and len(_rows(pg, rel_path=rel)) == 1
    with pytest.raises(pg.errors.UniqueViolation, match="already recorded"):
        Q.record_system(ing, rel_path=rel, sha256=_sha(), nbytes=5, reason="legacy", origin="legacy-backfill")


@pg_only
def test_a_writer_row_links_only_its_own_workstreams_attempt(pg):
    from litkb import quarantine as Q

    ws1, ws2, w = pg.ws(), pg.ws(), pg.session("litkb_writer")
    cand = P2M._cand(pg, w, ws1)
    aid = w.execute("SELECT litkb.record_acquisition_attempt(%s, %s, NULL, %s, 'open_access', NULL, 'blocked', "
                    "'{}'::jsonb, NULL)", (ws1, pg.tokens[ws1], cand)).fetchone()[0]
    rel = f"_quarantine/L_2026_x__blocked__{uuid.uuid4().hex[:12]}.pdf"
    with pytest.raises(pg.errors.InsufficientPrivilege, match="is not workstream"):
        Q.record(w, ws2, pg.tokens[ws2], rel_path=rel, sha256=_sha(), nbytes=1, reason="blocked",
                 origin="acquisition-guard", attempt_id=aid)
    assert Q.record(w, ws1, pg.tokens[ws1], rel_path=rel, sha256=_sha(), nbytes=1, reason="blocked",
                    origin="acquisition-guard", attempt_id=aid)


@pg_only
def test_a_detail_carrying_a_nul_is_still_recorded(pg):
    """`quarantine._detail` runs every detail through `textnorm.jsonb_safe` (mutation row S4Q1): a
    quarantined NAME or a served error page can carry a NUL, which jsonb refuses outright."""
    from litkb import quarantine as Q

    ing = pg.session("litkb_ingest")
    rel = f"_quarantine/N_2026_x__staging-orphan__{uuid.uuid4().hex[:12]}.download"
    Q.record_system(ing, rel_path=rel, sha256=_sha(), nbytes=1, reason="staging-orphan", origin="reaper",
                    detail={"was": "incoming/odd\x00name.download"})
    assert _rows(pg, rel_path=rel)[0][9]["was"] == "incoming/oddname.download"


@pg_only
def test_a_failed_row_is_returned_never_raised_and_the_connection_survives(pg):
    """`try_record` runs inside a savepoint: a refused row does not abort the caller's transaction."""
    from litkb import quarantine as Q

    ing = pg.session("litkb_ingest")
    ing.autocommit = False
    try:
        res = Q.try_record(Q.record_system, ing, rel_path="Validation/x.pdf", sha256=_sha(), nbytes=1,
                           reason="staging-orphan", origin="reaper")
        assert res["ok"] is False and "CheckViolation" in res["error"], res
        assert ing.execute("SELECT 1").fetchone() == (1,), "the transaction survived the refused row"
    finally:
        ing.rollback()


# ── what lies under _quarantine/ ──────────────────────────────────────────────────────────────

def test_the_payload_rule(tmp_path):
    from litkb import quarantine as Q

    q = tmp_path / "_quarantine"
    (q / "sub").mkdir(parents=True)
    for name in ("A__blocked__aaaaaaaaaaaa.pdf", "A__blocked__aaaaaaaaaaaa.txt",
                 "A__blocked__aaaaaaaaaaaa.reason.json", "lone-snapshot.txt", "B.download",
                 "sub/C__legacy__bbbbbbbbbbbb.pdf"):
        (q / name).write_bytes(b"x")
    got = [Q.rel_of(tmp_path, p) for p in Q.payloads(tmp_path)]
    assert got == ["_quarantine/A__blocked__aaaaaaaaaaaa.pdf", "_quarantine/B.download",
                   "_quarantine/lone-snapshot.txt", "_quarantine/sub/C__legacy__bbbbbbbbbbbb.pdf"], got


def _plant(root, name, body, sidecar=None):
    p = Path(root) / "_quarantine" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)
    if sidecar is not None:
        p.with_suffix(".reason.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return p


@pg_only
def test_the_backfill_dry_run_writes_nothing_and_apply_writes_one_row_per_path(pg, tmp_path):
    """The four ways a payload names its reason (an acquisition sidecar's `label`, a reaper sidecar,
    the name's label, nothing -> `legacy`), one label outside the vocabulary (REPORTED `unmapped`,
    never written), identical bytes under two names (one row PER PATH), an attempt linked by its
    `quarantined` path and a file linked by its sha256."""
    from litkb import quarantine as Q

    root = tmp_path / "Lit"
    tag = uuid.uuid4().hex[:8]
    same = f"identical bytes {tag}".encode()
    s12 = hashlib.sha256(same).hexdigest()[:12]
    guard = _plant(root, f"G{tag}__blocked__{s12}.pdf", same,
                   {"label": "blocked", "status": "blocked", "shape": "not-a-pdf"})
    twin = _plant(root, f"H{tag}__blocked__{s12}.pdf", same)
    reaped = _plant(root, f"R{tag}__staging-orphan__{'c' * 12}.download", f"reaped {tag}".encode(),
                    {"census_run": "x", "why": "orphan"})
    legacy = _plant(root, f"Legacy{tag}_2013_old-name.pdf", f"legacy {tag}".encode())
    odd = _plant(root, f"O{tag}__weird-label__{'d' * 12}.pdf", f"odd {tag}".encode())
    held_bytes = f"bytes also bound {tag}".encode()
    held = _plant(root, f"F{tag}__binding-failed__{'e' * 12}.pdf", held_bytes)
    # the links: an attempt that names the guard payload's path, and a file row holding `held`'s bytes
    ws, w = pg.ws(), pg.session("litkb_writer")
    cand = P2M._cand(pg, w, ws)
    aid = w.execute("SELECT litkb.record_acquisition_attempt(%s, %s, NULL, %s, 'open_access', NULL, 'blocked', "
                    "%s, NULL)", (ws, pg.tokens[ws], cand,
                                  pg.jsonb({"sha256": hashlib.sha256(same).hexdigest(),
                                            "quarantined": Q.rel_of(root, guard)}))).fetchone()[0]
    fid = pg.conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, 's', 's')",
        (pg.jsonb({"key": f"Q_2026_backfill-{tag}"}), pg.jsonb({"type": "report", "title": "q", "authors": []}),
         ws)).fetchone()[0]
    file_id = pg.conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, 's', 's')",
        (pg.jsonb({"sha256": hashlib.sha256(held_bytes).hexdigest()}),
         pg.jsonb({"work_id": str(fid), "status": "active", "rel_path": f"Validation/{tag}.pdf"}), ws)).fetchone()[0]

    before = pg.conn.execute("SELECT count(*) FROM litkb.quarantine_payloads").fetchone()[0]
    dry = Q.backfill(pg.conn, root=root)
    assert pg.conn.execute("SELECT count(*) FROM litkb.quarantine_payloads").fetchone()[0] == before
    by = {r["rel_path"]: r for r in dry["rows"]}
    assert by[Q.rel_of(root, guard)]["reason"] == "blocked" and by[Q.rel_of(root, guard)]["reason_source"] == "sidecar:label"
    assert by[Q.rel_of(root, twin)]["reason"] == "blocked" and by[Q.rel_of(root, twin)]["reason_source"] == "name"
    assert by[Q.rel_of(root, reaped)]["reason"] == "staging-orphan"
    assert by[Q.rel_of(root, legacy)]["reason"] == "legacy"
    assert by[Q.rel_of(root, odd)]["reason"] is None and by[Q.rel_of(root, odd)]["action"] == "unmapped"
    assert by[Q.rel_of(root, guard)]["attempt_id"] == str(aid)
    assert by[Q.rel_of(root, twin)]["attempt_id"] == str(aid), "the one attempt with these bytes"
    assert by[Q.rel_of(root, held)]["file_id"] == str(file_id)
    assert dry["counters"]["payloads"] == 6 and dry["counters"]["unmapped"] == 1, dry["counters"]
    assert dry["counters"]["distinct_sha256"] == 5 and dry["counters"]["written"] == 0

    ing = pg.session("litkb_ingest")
    done = Q.backfill(pg.conn, root=root, apply=True, recorder=ing)
    assert done["counters"]["written"] == 5 and done["errors"] == [], done["counters"]
    assert _rows(pg, rel_path=Q.rel_of(root, twin))[0][7] == str(aid)
    assert _rows(pg, rel_path=Q.rel_of(root, held))[0][6] == str(file_id)
    assert all(r[4] == "legacy-backfill" for r in (_rows(pg, rel_path=Q.rel_of(root, p))[0]
                                                   for p in (guard, twin, reaped, legacy, held)))
    again = Q.backfill(pg.conn, root=root, apply=True, recorder=ing)
    assert again["counters"]["already_recorded"] == 5 and again["counters"]["written"] == 0
    n, missing = Q.quarantined_without_db_state(pg.conn, root=root)
    assert (n, missing) == (1, [Q.rel_of(root, odd)]), "the unmapped payload is exactly what stays uncounted"


# ── the known-bad: a payload with no row ──────────────────────────────────────────────────────

@pg_only
def test_fire_quarantine_moves_the_counter_by_one(pg, tmp_path):
    """Plan "### S4" (c), last row: a file placed in `_quarantine/` with no database row ->
    `quarantined_without_db_state` = 1 (from 0 on an empty tree)."""
    from litkb import quarantine as Q
    from litkb.acquire.store import LITERATURE_ROOT

    out = Q.fire_quarantine(pg.conn, root=tmp_path / "Lit")
    assert (out["before"], out["quarantined_without_db_state"]) == (0, 1), out
    assert out["missing"] == [out["planted"]] and "CONSTRUCTED" in out["planted"]
    with pytest.raises(RuntimeError, match="temp root"):
        Q.fire_quarantine(pg.conn, root=LITERATURE_ROOT)


# ── a row at every quarantine write: acquisition ─────────────────────────────────────────────

def _acquire(pg, w, ws, work, store, body, **kw):
    from litkb.acquire import run

    clients = {"open_access": P2M.RouteStub({"oa.example": (200, {}, body)})}
    return run.acquire(w, ws, pg.tokens[ws], work, store=store, routes=("open_access",), agent="q",
                       session="q-1", clients=clients, pacer=P2M._nopace(), printer=lambda *a: None, **kw)


def _attempt(pg, wid, route):
    return pg.conn.execute("SELECT id::text, status, detail FROM litkb.acquisition_attempts "
                           "WHERE work_id = %s AND route = %s ORDER BY at, id", (wid, route)).fetchall()


@pg_only
@pytest.mark.parametrize("case", ["route-refused-bytes", "does-not-bind"])
def test_every_acquisition_quarantine_leaves_a_row_linked_to_its_attempt(pg, tmp_path, monkeypatch, case):
    from litkb import quarantine as Q

    P2M._need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    P2M._oa(monkeypatch)
    body = (P2M.HTML_SERVED_AS_PDF if case == "route-refused-bytes"
            else P2M.paper_pdf("Tidal mixing fronts in the Irish Sea", "J. Simpson"))
    out = _acquire(pg, w, ws, work, store, body)
    aid, status, detail = _attempt(pg, work["work_id"], "open_access")[0]
    rows = _rows(pg, attempt_id=aid)
    assert len(rows) == 1 and rows[0][0] == detail["quarantined"], (rows, detail)
    want = ("bad-file", "acquisition-guard") if case == "route-refused-bytes" else ("binding-failed", "bind-refusal")
    assert rows[0][3:5] == want and rows[0][5] == str(work["work_id"]) and rows[0][8] == str(ws), rows
    assert rows[0][1] == hashlib.sha256(body).hexdigest() and rows[0][2] == len(body)
    assert out["quarantine_rows"] and all(q["ok"] for q in out["quarantine_rows"]), out
    assert Q.quarantined_without_db_state(pg.conn, root=store.root) == (0, [])


@pg_only
def test_a_hand_fetched_bad_file_leaves_a_row(pg, tmp_path):
    from litkb import quarantine as Q
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    src = store.incoming / "handed-in.pdf"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(P2M.HTML_SERVED_AS_PDF)
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, from_file=src, agent="q", session="q-ff",
                      pacer=P2M._nopace(), printer=lambda *a: None)
    aid, _s, detail = _attempt(pg, work["work_id"], "browser")[0]
    rows = _rows(pg, attempt_id=aid)
    assert [r[3:5] for r in rows] == [("not-a-pdf", "acquisition-guard")] and rows[0][0] == detail["quarantined"]
    assert out["quarantine_rows"][0]["ok"], out
    assert Q.quarantined_without_db_state(pg.conn, root=store.root) == (0, [])


@pg_only
def test_a_quarantine_whose_row_fails_keeps_the_bytes_and_says_so(pg, tmp_path, monkeypatch):
    """The move happens first; the row second. A row that cannot be written is RETURNED (`ok: False`
    in `quarantine_rows`), the attempt row still exists, the bytes are kept, and the acceptance
    counter names the payload — the counter is the gate, not the write."""
    from litkb import quarantine as Q

    P2M._need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    P2M._oa(monkeypatch)

    def refuse(*a, **k):
        raise RuntimeError("the database refused the row")
    monkeypatch.setattr(Q, "record", refuse)
    out = _acquire(pg, w, ws, work, store, P2M.HTML_SERVED_AS_PDF)
    assert out["quarantine_rows"] and out["quarantine_rows"][0]["ok"] is False, out
    _aid, status, detail = _attempt(pg, work["work_id"], "open_access")[0]
    assert status == "bad-file" and (store.root / detail["quarantined"]).read_bytes() == P2M.HTML_SERVED_AS_PDF
    n, missing = Q.quarantined_without_db_state(pg.conn, root=store.root)
    assert missing == [detail["quarantined"]], missing


# ── the fail-closed bind probe ────────────────────────────────────────────────────────────────

@pg_only
def test_a_landed_file_whose_page_count_cannot_be_read_is_never_bound(pg, tmp_path, monkeypatch):
    """The real binder, the real probe: a CONSTRUCTED file with a %PDF- header and a %%EOF trailer
    (so the shape guard passes it) whose catalog pypdfium2 cannot load. It is quarantined
    `probe-error` with its row, the attempt says why, and nothing is bound."""
    from litkb import quarantine as Q

    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    P2M._oa(monkeypatch)
    data = _unopenable()
    out = _acquire(pg, w, ws, work, store, data)
    assert out["outcome"] == "not-acquired", out
    aid, status, detail = _attempt(pg, work["work_id"], "open_access")[0]
    assert status == "bad-file" and detail["probe_error"] and "__probe-error__" in detail["quarantined"], detail
    assert "attach" not in detail, "a file whose page count failed was offered to attach_file"
    rows = _rows(pg, attempt_id=aid)
    assert [r[3:5] for r in rows] == [("probe-error", "bind-refusal")], rows
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work["work_id"],))[0] == 0
    assert list(store.filed.glob("*")) == [] if store.filed.exists() else True
    assert Q.quarantined_without_db_state(pg.conn, root=store.root) == (0, [])


@pg_only
def test_a_bound_file_always_carries_its_page_count(pg, tmp_path, monkeypatch):
    """`pages` is never NULL on a new bind: it is the probe's count, not pdfinfo's `Pages`."""
    P2M._need_pdftotext()
    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    P2M._oa(monkeypatch)
    out = _acquire(pg, w, ws, work, store, P2M.paper_pdf(work["title"], "T. Tester"))
    assert out["outcome"] == "ok", out
    assert pg.one("SELECT pages FROM litkb.main_files WHERE work_id = %s", (work["work_id"],)) == (1,)


@pg_only
def test_fire_probe_refuses_with_the_guard_and_binds_pages_null_without_it(tmp_path):
    """The acceptance's known-bad (plan "### S4" (c)): the CONSTRUCTED unopenable PDF through the bind
    path. With the guard: refused, never bound. With the guard mutated off (the probe replaced by one
    that never raises and counts nothing — the pre-S4 `pdf_info` behaviour): it BINDS, with pages NULL."""
    from litkb import readability as R
    from litkb.db import connect as c

    on = R.fire_probe(c.DB_TEST, root=tmp_path / "on")
    assert (on["probe_refused"], on["bound"], on["bound_pages_null"]) == (1, 0, 0), on
    off = R.fire_probe(c.DB_TEST, root=tmp_path / "off", guard=False)
    assert (off["probe_refused"], off["bound"], off["bound_pages_null"]) == (0, 1, 1), off
    with pytest.raises(RuntimeError, match="worker database"):
        R.fire_probe("litkb", root=tmp_path / "never")


@pg_only
def test_a_topic_folder_file_whose_page_count_cannot_be_read_is_refused_in_place(pg, tmp_path):
    """`attach_in_place` goes through `front.file_evidence`, where the admission side of the guard
    lives. The file is not acquisition's: it is left exactly where it lies, and its row is recorded
    against THAT path (the row is the state)."""
    from litkb.acquire import run

    ws, w = pg.ws(), pg.session("litkb_writer")
    work, store = P2M._admitted(pg, w, ws), _store(tmp_path)
    src = store.root / "Validation" / "Unopenable_2020_in-place.pdf"
    src.write_bytes(_unopenable())
    before = src.read_bytes()
    out = run.acquire(w, ws, pg.tokens[ws], work, store=store, from_file=src, agent="q", session="q-ip",
                      pacer=P2M._nopace(), printer=lambda *a: None)
    assert out["outcome"] == "bad-file", out
    aid, status, detail = _attempt(pg, work["work_id"], "browser")[0]
    assert detail["in_place"] == "Validation/Unopenable_2020_in-place.pdf" and detail["probe_error"], detail
    rows = _rows(pg, attempt_id=aid)
    assert [(r[0], r[3], r[4]) for r in rows] == [(detail["in_place"], "probe-error", "bind-refusal")], rows
    assert src.read_bytes() == before and not (store.root / "_quarantine").exists()
    assert pg.one("SELECT count(*) FROM litkb.main_files WHERE work_id = %s", (work["work_id"],))[0] == 0


@pg_only
def test_an_admission_whose_file_cannot_be_probed_is_refused_with_a_row(pg, tmp_path):
    """`admit --manual --file` on an unopenable file: `BindProbeError` (an AdmissionError), no
    admission written, the file untouched, and a row against the file where it lies."""
    from litkb.admit import front

    ws, w = pg.ws(), pg.session("litkb_writer")
    root = tmp_path / "Lit"
    f = root / "Validation" / "Unopenable_1999_manual.pdf"
    f.parent.mkdir(parents=True)
    f.write_bytes(_unopenable())
    n0 = pg.one("SELECT count(*) FROM litkb.admissions")[0]
    with pytest.raises(front.BindProbeError) as ei:
        front.admit_manual(w, ws, pg.tokens[ws], title="An unopenable manual", authors="Nobody, N.", year=1999,
                           file_path=f, source_note="test", root=root, agent="q", session="q-adm")
    assert ei.value.quarantine_row["ok"], ei.value.quarantine_row
    rows = _rows(pg, rel_path="Validation/Unopenable_1999_manual.pdf")
    assert [(r[3], r[4], r[8]) for r in rows] == [("probe-error", "bind-refusal", str(ws))], rows
    assert pg.one("SELECT count(*) FROM litkb.admissions")[0] == n0


# ── a row at every quarantine write: hunt ────────────────────────────────────────────────────

@pytest.fixture
def henv(tmp_path, monkeypatch, litkb_pg_base):
    """qc/test_litkb_hunt.py's env: a literature root, a worktree with a real workstream, and the
    throwaway database, with `litkb_test` standing in for reader, writer and ingest."""
    from litkb import workstream
    from litkb.db import connect as c

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    (root / "Validation").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws_id = workstream.open_workstream(conn, f"qhunt-{uuid.uuid4().hex[:8]}", "test", "quarantine hunt",
                                       directory=wt)
    for k, v in {"LITKB_DB": c.DB_TEST, "LITKB_WORKTREE": str(wt), "LITKB_LITERATURE_ROOT": str(root),
                 "LITKB_AGENT": "qhunt", "LITKB_SESSION": f"qhunt-{uuid.uuid4().hex[:8]}"}.items():
        monkeypatch.setenv(k, v)
    return {"conn": conn, "root": root, "wt": wt, "ws_id": str(ws_id), "db": c.DB_TEST, "tmp": tmp_path}


def _hunt(henv, ref, **kw):
    from litkb import hunt as H
    from litkb.acquire.store import Store

    return H.hunt(ref, db=henv["db"], worktree=henv["wt"], agent="qhunt", session="qhunt-session",
                  reader_role="litkb_test", writer_role="litkb_test",
                  store=Store(root=henv["root"], index_cache=henv["tmp"] / "index.json"),
                  derived=str(henv["tmp"] / "derived"), **kw)


@pg_only
def test_a_hunted_download_that_is_not_a_pdf_leaves_a_row(henv):
    from litkb import quarantine as Q

    url = f"https://example.org/{uuid.uuid4().hex}.pdf"
    res = _hunt(henv, url, fetch=lambda u, timeout=180: (200, P2M.HTML_SERVED_AS_PDF), key="Html_2026_q-row")
    assert res["ok"] is False and res["refused"] == "not-a-pdf", res
    assert res["quarantine_row"]["ok"], res
    got = henv["conn"].execute("SELECT reason, origin, workstream_id::text, sha256 FROM litkb.quarantine_payloads "
                               "WHERE rel_path = %s", (res["quarantined"],)).fetchone()
    assert got == ("not-a-pdf", "hunt-url", henv["ws_id"], hashlib.sha256(P2M.HTML_SERVED_AS_PDF).hexdigest()), got
    assert Q.quarantined_without_db_state(henv["conn"], root=henv["root"]) == (0, [])


@pg_only
def test_a_hunted_pdf_the_bind_probe_refuses_is_quarantined_with_a_row(henv):
    """The URL path: the bytes pass the shape guard (header + trailer), the claimed fields are given,
    and the admission's file evidence cannot count the pages. The hunt ends where an admission that
    refused its file already ends — `refused` / `admission-refused`, no new state or reason — with the
    download moved to `_quarantine/` under `probe-error` and its row written."""
    from litkb import hunt as H
    from litkb import quarantine as Q

    url = f"https://example.org/{uuid.uuid4().hex}.pdf"
    data = _unopenable()
    res = _hunt(henv, url, fetch=lambda u, timeout=180: (200, data), key="Unopenable_2026_q-probe",
                title="An unopenable hunted document", author="Nobody", year=2026)
    assert (res["state"], res["reason"]) == ("refused", "admission-refused"), res
    assert H.reason_ok(res["state"], res["reason"])
    assert "__probe-error__" in res["quarantined"] and res["quarantine_row"]["ok"], res
    got = henv["conn"].execute("SELECT reason, origin FROM litkb.quarantine_payloads WHERE rel_path = %s",
                               (res["quarantined"],)).fetchone()
    assert got == ("probe-error", "hunt-url"), got
    assert (henv["root"] / res["quarantined"]).read_bytes() == data
    assert not list((henv["root"] / "_litkb_staging" / "filed").glob("Unopenable_2026_q-probe*"))
    assert Q.quarantined_without_db_state(henv["conn"], root=henv["root"]) == (0, [])


@pg_only
def test_the_backfill_cli_dry_runs_by_default_and_applies_on_the_ingest_login(pg, tmp_path, capsys):
    """`litkb quarantine backfill` on the worker database: the dry run writes nothing and exits 0;
    `--apply` opens the INGEST connection (SET ROLE litkb_ingest on a test database) and writes."""
    from litkb import commands
    from litkb import quarantine as Q
    from litkb.db import connect as c

    root = tmp_path / "Lit"
    tag = uuid.uuid4().hex[:8]
    p = _plant(root, f"Cli{tag}__blocked__{'a' * 12}.pdf", f"cli {tag}".encode())
    args = ["--db", c.DB_TEST, "quarantine", "backfill", "--role", "litkb_test", "--root", str(root)]
    assert commands.main(args) == 0
    assert "mode=dry-run" in capsys.readouterr().out
    assert _rows(pg, rel_path=Q.rel_of(root, p)) == []
    assert commands.main(args + ["--apply"]) == 0
    assert "written=1" in capsys.readouterr().out
    assert [(r[3], r[4]) for r in _rows(pg, rel_path=Q.rel_of(root, p))] == [("blocked", "legacy-backfill")]
    _plant(root, f"Odd{tag}__weird-label__{'b' * 12}.pdf", f"odd {tag}".encode())
    assert commands.main(args) == 1, "an unmapped label is a non-zero exit, never a default"
