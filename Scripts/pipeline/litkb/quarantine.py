"""The database-visible quarantine state: one row per refused payload (migration 0030,
LITKB_WORKPLAN.md "### S4", S4 run 3 decision D5).

    from litkb import quarantine as Q
    Q.try_record(Q.record, writer, ws, token, rel_path=..., sha256=..., nbytes=..., reason=..., origin=...)
    Q.try_record(Q.record_system, ingest, rel_path=..., ...)
    Q.backfill(reader, root=..., apply=False)              # the census; writes nothing
    Q.quarantined_without_db_state(reader, root=...)       # the acceptance counter

WHY. Until S4 `_quarantine/` was a directory and nothing else: `Store.to_quarantine` writes the status
and the sha into the FILENAME, no code read that name back, and `hunt.land_download` and the staging
reaper left no database row at all (S4 run 3 code survey C7). A refused file was invisible to
`litkb_work`, and "what did we refuse, and why" had no answer a query could give.

THE TWO VOCABULARIES have ONE home, here. Migration 0030's CHECK constraints spell the same lists
and qc/test_litkb_quarantine.py holds them equal, so neither can grow alone.

  REASONS  derived from every label a Store call site writes into a quarantined NAME, plus the disk
           census (data survey D4) and the two S4 refusals:
             the shapes `store.pdf_shape` names ............ not-a-pdf, truncated-pdf
             route statuses handed back WITH bytes .......... blocked, bad-file, not-in-archive,
                                                              partner-404, hash-mismatch
             binding verdicts / attach outcomes ............. binding-failed, binding-pending,
                                                              duplicate-held
             the legacy `annas.fetch_one` labels ............ duplicate-hash, content-mismatch
             the staging reaper ............................. staging-orphan
             S4: the fail-closed probe, the classifier ...... probe-error, zero-content
             a pre-litkb name with no label ................. legacy
  ORIGINS  the code path that refused the bytes. The brief's six, checked against the code:
             acquisition-guard  `acquire.run.quarantine_bytes` (a download that is not a whole PDF, or
                                bytes a route refused) and `from_file_not_a_pdf`
             bind-refusal       `acquire.run.land_and_attach` (binding verdict, attach refused, the
                                probe) and an admission's probe refusal (`admit.front`)
             hunt-url           `hunt.land_download` and the URL path's probe refusal
             reaper             `ops.reaper.reap --apply`
             classifier         `litkb.readability` refusing a BOUND file where it lies
             legacy-backfill    `backfill --apply` over what was already on disk
           `acquire.annas.fetch_one` (the legacy aa_fetch filing path) is deliberately NOT an origin:
           it holds no database connection and no workstream (its only caller is the standalone
           `annas.main`), so it cannot present a token and writes no row; what it quarantines is
           picked up by `backfill` and, until then, counted by `quarantined_without_db_state`.

A FAILED ROW NEVER LOSES THE BYTES. Every writer here is called AFTER the move (the bytes are already
where the row would say they are), inside a savepoint, and its failure is returned, never raised:
`try_record` answers {"ok": False, "error": ...} and the caller reports it in its own result. The
ACCEPTANCE COUNTER is the gate, not the write — `quarantined_without_db_state` names every payload
under `_quarantine/` that no row accounts for (the `hunt-url` acquisition event is the precedent,
docs/SCHEMAS.md "litkb.acquisition_attempts").
"""
import hashlib
import json
import re
from pathlib import Path

REASONS = ("not-a-pdf", "truncated-pdf",
           "blocked", "bad-file", "not-in-archive", "partner-404", "hash-mismatch",
           "binding-failed", "binding-pending", "duplicate-held",
           "duplicate-hash", "content-mismatch",
           "staging-orphan",
           "probe-error", "zero-content",
           "legacy")
ORIGINS = ("acquisition-guard", "bind-refusal", "hunt-url", "reaper", "classifier", "legacy-backfill")
WRITER_ORIGINS = ("acquisition-guard", "bind-refusal", "hunt-url")
SYSTEM_ORIGINS = ("reaper", "classifier", "legacy-backfill")

#: The label a quarantined NAME carries tells which door it came through on the acquisition path:
#: the binding and attach outcomes (and the S4 probe) are refusals AT THE BIND; everything else a
#: `land_and_attach`/`acquire` name carries is the acquisition guard's (a shape, or a route status).
BIND_LABELS = ("binding-failed", "binding-pending", "duplicate-held", "probe-error")

QUARANTINE_DIR = "_quarantine"
SIDECAR_SUFFIX = ".reason.json"

#: `<stem>__<label>__<token><.N>?<suffix>` — `Store.to_quarantine`/`quarantine_new` write sha256[:12]
#: as the token and `free_name` adds `.2`, `.3` … before the suffix; the legacy `annas._quarantine`
#: writes the md5 (32 hex). The stem is non-greedy and the whole name anchored, so a stem that itself
#: holds `.2` (the reaper keeps a staging name's own stem) still parses.
_NAME = re.compile(r"^(?P<stem>.+?)__(?P<label>[a-z][a-z0-9-]*)__(?P<token>[0-9a-f]{12,64})(?:\.(?P<n>\d+))?$")


def parse_name(name):
    """{"stem", "label", "token"} for a `<stem>__<label>__<token>` quarantine name, else None."""
    m = _NAME.match(Path(name).stem)
    return m.groupdict() if m else None


def origin_of_label(label):
    """The origin an ACQUISITION-path quarantine name implies (see BIND_LABELS)."""
    return "bind-refusal" if label in BIND_LABELS else "acquisition-guard"


# ── the writers ───────────────────────────────────────────────────────────────────────────────

def _detail(v):
    from psycopg.types.json import Jsonb

    from litkb.textnorm import jsonb_safe

    # a quarantined name or a served error page can carry a NUL, which jsonb refuses outright
    return Jsonb(jsonb_safe(v or {}))


def record(conn, ws, token, *, rel_path, sha256, nbytes, reason, origin, work_id=None, file_id=None,
           attempt_id=None, detail=None):
    """The WRITER-side row (litkb.record_quarantine): presents the workstream token. -> the row id."""
    return conn.execute(
        "SELECT litkb.record_quarantine(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (ws, token, rel_path, sha256, int(nbytes), reason, origin, work_id, file_id, attempt_id,
         _detail(detail))).fetchone()[0]


def record_system(conn, *, rel_path, sha256, nbytes, reason, origin, work_id=None, file_id=None,
                  attempt_id=None, detail=None):
    """The INGEST-side row (litkb.record_quarantine_system): no token, system origins only."""
    return conn.execute(
        "SELECT litkb.record_quarantine_system(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (rel_path, sha256, int(nbytes), reason, origin, work_id, file_id, attempt_id,
         _detail(detail))).fetchone()[0]


def ingest_connect(dbname=None):
    """The connection `record_quarantine_system` is called on: the INGEST login for `litkb`
    (`litkb.ingest.connect`, the one path to that login and its own passfile), and on a test database
    — where that login has no password, by design (`db.provision`) — the test login with SET ROLE
    litkb_ingest, so the privileges exercised are the real ones. The same rule, and the same reason,
    as `litkb.extract.references_ingest.connect`."""
    from litkb.db import connect as c

    if dbname is None or dbname == c.DB_MAIN:
        from litkb import ingest as ingest_login

        return ingest_login.connect(dbname)
    if not c.is_test_db(dbname):
        raise RuntimeError(f"quarantine: {dbname!r} is neither {c.DB_MAIN} nor a test database")
    conn = c.connect(dbname, "litkb_test", autocommit=True)
    conn.execute("SET ROLE litkb_ingest")
    return conn


def try_record(fn, conn, *args, **kw):
    """`fn(conn, ...)` inside a savepoint. -> {"ok": True, "id": str} or {"ok": False, "error": str}.

    NEVER RAISES: the bytes have already moved when this runs, and an exception here would turn a kept
    payload into a crashed caller. The savepoint keeps a refused row from aborting the caller's own
    transaction. 300 characters of the error for the reason `hunt._record_acquisition_event` gives."""
    try:
        with conn.transaction():
            rid = fn(conn, *args, **kw)
        return {"ok": True, "id": str(rid), "rel_path": kw.get("rel_path")}
    except Exception as e:                  # noqa: BLE001 — the counter is the gate, not this write
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}", "rel_path": kw.get("rel_path")}


# ── what lies under _quarantine/ ──────────────────────────────────────────────────────────────

def payloads(root):
    """Every PAYLOAD under `<root>/_quarantine/` (recursively), sorted: every file except the
    `.reason.json` sidecars and the `.txt` companion of a payload stem (`Store.extract` writes the
    pdftotext extract beside a quarantined PDF; `to_quarantine` moves the two together). A `.txt` with
    no primary sibling IS a payload (a reaped `web/` snapshot is one)."""
    q = Path(root) / QUARANTINE_DIR
    if not q.is_dir():
        return []
    files = [p for p in q.rglob("*") if p.is_file()]
    primary = {(p.parent, p.stem) for p in files
               if not p.name.endswith(SIDECAR_SUFFIX) and p.suffix.lower() != ".txt"}
    out = []
    for p in files:
        if p.name.endswith(SIDECAR_SUFFIX):
            continue
        if p.suffix.lower() == ".txt" and (p.parent, p.stem) in primary:
            continue
        out.append(p)
    return sorted(out)


def rel_of(root, path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def sha256_of(path):
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def table_present(conn):
    """False on a database that has not applied migration 0030 (live, until the orchestrator does)."""
    return conn.execute("SELECT to_regclass('litkb.quarantine_payloads') IS NOT NULL").fetchone()[0]


def recorded_paths(conn):
    """{rel_path: id} of every row; {} when the table does not exist yet."""
    if not table_present(conn):
        return {}
    return {r[0]: str(r[1]) for r in conn.execute("SELECT rel_path, id FROM litkb.quarantine_payloads").fetchall()}


def quarantined_without_db_state(conn, *, root):
    """The ACCEPTANCE COUNTER (plan "### S4" (b)): payloads under `<root>/_quarantine/` — the same
    payload rule as `backfill` — with no row for their path. -> (count, [rel paths]).

    `root` is a parameter so a test (and `fire_quarantine`) can point it at a temp tree."""
    rows = recorded_paths(conn)
    missing = [rel_of(root, p) for p in payloads(root)]
    missing = [r for r in missing if r not in rows]
    return len(missing), missing


# ── the backfill ──────────────────────────────────────────────────────────────────────────────

def _sidecar(path):
    s = Path(path).with_suffix(SIDECAR_SUFFIX)
    if not s.is_file():
        return None, None
    try:
        return s, json.loads(s.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return s, None


def reason_of(path):
    """(reason, source, label) for one payload: the sidecar first, then the name's label, then `legacy`.

    The sidecar shapes on disk (data survey D4): the acquisition guard's (`label`, `status`, `shape`
    — `acquire.run._reason`), the hunt's (`shape`, `status`), and the reaper's (`census_run`, `why`,
    no label). A label outside REASONS is returned as `(None, ...)`: it is REPORTED, never defaulted
    into a class."""
    side, body = _sidecar(path)
    parsed = parse_name(Path(path).name)
    label = parsed["label"] if parsed else None
    if isinstance(body, dict):
        if body.get("label"):
            lab = str(body["label"])
            return (lab if lab in REASONS else None), "sidecar:label", lab
        if "census_run" in body:
            return "staging-orphan", "sidecar:reaper", label
        if body.get("shape") and body["shape"] != "pdf":
            lab = str(body["shape"])
            return (lab if lab in REASONS else None), "sidecar:shape", lab
    if label:
        return (label if label in REASONS else None), "name", label
    return "legacy", "no-label", None


def _attempts_by_sha(conn, shas):
    if not shas:
        return {}
    out = {}
    for aid, sha, work_id, q in conn.execute(
            "SELECT id::text, detail->>'sha256', work_id::text, detail->>'quarantined' "
            "  FROM litkb.acquisition_attempts WHERE detail->>'sha256' = ANY(%s) ORDER BY at, id",
            (list(shas),)).fetchall():
        out.setdefault(sha, []).append({"id": aid, "work_id": work_id, "quarantined": q})
    return out


def _files_by_sha(conn, shas):
    if not shas:
        return {}
    out = {}
    for fid, sha, work_id in conn.execute(
            "SELECT f.id::text, f.sha256, fv.work_id::text FROM litkb.files f "
            "  LEFT JOIN litkb.file_versions fv ON fv.version_id = f.current_version_id "
            " WHERE f.sha256 = ANY(%s) ORDER BY f.id", (list(shas),)).fetchall():
        out.setdefault(sha, []).append({"id": fid, "work_id": work_id})
    return out


def backfill_plan(conn, *, root):
    """One planned row per payload, with its links. Reads the database and the disk; writes nothing.

    Links (decision D5's nullable work/file/attempt): `attempt_id` is the attempt whose
    `detail->>'quarantined'` IS this path; failing that, the one attempt whose `detail->>'sha256'`
    matches — several matches with no path match link NONE and list the candidates in the detail,
    because choosing one would be a guess. `file_id` is the `files` row with this sha256 (identical
    bytes quarantined AND bound: data survey D4 names five). `work_id` comes from the attempt, else the
    file. One sha under several names is one row PER PATH (the Chen_2024/Song_2026 pair)."""
    from litkb.acquire.store import LITERATURE_ROOT

    root = Path(root or LITERATURE_ROOT)
    recorded = recorded_paths(conn)
    items = []
    for p in payloads(root):
        sha, n = sha256_of(p)
        reason, source, label = reason_of(p)
        items.append({"rel_path": rel_of(root, p), "sha256": sha, "bytes": n, "reason": reason,
                      "reason_source": source, "label": label})
    atts = _attempts_by_sha(conn, {i["sha256"] for i in items})
    fils = _files_by_sha(conn, {i["sha256"] for i in items})
    for it in items:
        cands = atts.get(it["sha256"], [])
        exact = [a for a in cands if a["quarantined"] == it["rel_path"]]
        pick = exact[0] if exact else (cands[0] if len(cands) == 1 else None)
        it["attempt_id"] = pick["id"] if pick else None
        it["attempt_candidates"] = [a["id"] for a in cands] if (cands and not pick) else []
        f = fils.get(it["sha256"], [])
        it["file_id"] = f[0]["id"] if len(f) == 1 else None
        it["file_candidates"] = [x["id"] for x in f] if len(f) > 1 else []
        it["work_id"] = (pick or {}).get("work_id") or (f[0]["work_id"] if len(f) == 1 else None)
        it["recorded_id"] = recorded.get(it["rel_path"])
        side = Path(it["rel_path"]).with_suffix(SIDECAR_SUFFIX).as_posix()
        it["sidecar"] = side if (root / side).is_file() else None
    return items


def backfill(conn, *, root, apply=False, recorder=None):
    """`litkb quarantine backfill [--apply]`: every payload gets a row (origin `legacy-backfill`).

    Dry run (the default) writes nothing and reports what it WOULD write. `apply=True` writes through
    `recorder` (an ingest connection: `record_quarantine_system` is granted to litkb_ingest alone),
    idempotently — a path already recorded is skipped, and the database refuses a recorded path offered
    with different bytes. A payload whose label is outside REASONS is NOT written: it is counted
    `unmapped` and listed, never defaulted."""
    items = backfill_plan(conn, root=root)
    written, errors = [], []
    for it in items:
        it["action"] = ("already-recorded" if it["recorded_id"] else
                        "unmapped" if it["reason"] is None else "record")
        if not apply or it["action"] != "record":
            continue
        detail = {"reason_source": it["reason_source"], "label": it["label"], "sidecar": it["sidecar"],
                  "attempt_candidates": it["attempt_candidates"], "file_candidates": it["file_candidates"]}
        res = try_record(record_system, recorder, rel_path=it["rel_path"], sha256=it["sha256"],
                         nbytes=it["bytes"], reason=it["reason"], origin="legacy-backfill",
                         work_id=it["work_id"], file_id=it["file_id"], attempt_id=it["attempt_id"],
                         detail=detail)
        it["result"] = res
        (written if res["ok"] else errors).append(it["rel_path"])
    by_reason = {}
    for it in items:
        by_reason[it["reason"] or "UNMAPPED"] = by_reason.get(it["reason"] or "UNMAPPED", 0) + 1
    counters = {"payloads": len(items),
                "already_recorded": sum(1 for i in items if i["action"] == "already-recorded"),
                "to_record": sum(1 for i in items if i["action"] == "record"),
                "unmapped": sum(1 for i in items if i["action"] == "unmapped"),
                "with_attempt": sum(1 for i in items if i["attempt_id"]),
                "ambiguous_attempt": sum(1 for i in items if i["attempt_candidates"]),
                "with_file": sum(1 for i in items if i["file_id"]),
                "distinct_sha256": len({i["sha256"] for i in items}),
                "written": len(written), "errors": len(errors)}
    from litkb.acquire.store import LITERATURE_ROOT

    return {"applied": bool(apply), "root": str(root or LITERATURE_ROOT), "table_present": table_present(conn),
            "counters": counters,
            "by_reason": dict(sorted(by_reason.items())), "rows": items, "errors": errors}


# ── the known-bad ─────────────────────────────────────────────────────────────────────────────

def fire_quarantine(conn, *, root):
    """The acceptance's known-bad (plan "### S4" (c), last row): a CONSTRUCTED payload placed in
    `<root>/_quarantine/` with no database row. -> the counter AFTER the placement, which must be
    exactly one more than before it.

    `root` must be a throwaway tree — this WRITES a file there; it refuses the real literature root."""
    from litkb.acquire.store import LITERATURE_ROOT

    root = Path(root)
    if root.resolve() == Path(LITERATURE_ROOT).resolve():
        raise RuntimeError("fire_quarantine plants a file; point it at a temp root, never the literature root")
    before, _ = quarantined_without_db_state(conn, root=root)
    q = root / QUARANTINE_DIR
    q.mkdir(parents=True, exist_ok=True)
    body = b"CONSTRUCTED orphan payload for fire_quarantine\n"
    sha = hashlib.sha256(body).hexdigest()
    target = q / f"CONSTRUCTED_orphan__staging-orphan__{sha[:12]}.download"
    n = 2
    while target.exists():
        target = q / f"CONSTRUCTED_orphan__staging-orphan__{sha[:12]}.{n}.download"
        n += 1
    with open(target, "xb") as fh:
        fh.write(body)
    after, missing = quarantined_without_db_state(conn, root=root)
    return {"quarantined_without_db_state": after, "before": before, "planted": rel_of(root, target),
            "missing": missing}
