"""S3 — the staging reaper: what it reaps, and the four things it must not.

`_litkb_staging/` accumulates bytes nothing accounts for: a hunt that landed a download and then
refused `incomplete-round` leaves it in `incoming/`, and `land_and_attach` between the landing and
the attach leaves one too. On 2026-09-15 eleven such files were made in one 80-minute window (S3
data survey §9). Nothing has ever cleaned them up, and the obvious cleanup — delete what no row
names — is precisely the 2026-09-12 incident that cost 149 PDFs.

So the four kills here are all about what is NOT reaped:

  young       a planted orphan younger than --min-age-hours is `young`, never touched. `incoming/`
              is a WORKING directory: a download in flight has no row yet either
  owned       a file whose sha256 IS in litkb.files is left alone however old it is — four real
              files in `incoming/` are byte-identical to files already recorded under `filed/`,
              and a path-keyed reaper quarantines all four
  by path     a file no sha knows, whose PATH a file_versions.rel_path names, is owned too: that
              is the sixteen `t*.download` rows a hunt is still working on
  dry run     the default moves nothing, proved by hashing the directory before and after

and one about what IS: an old, unowned file is QUARANTINED — moved, under a name carrying its sha,
with a .reason.json beside it — and never deleted.

Every test runs against a temp literature root. Nothing here can see D:\\edmonds-pipeline\\Literture.

Run:
    PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w8 py -3.12 -m pytest \
        qc/test_litkb_reaper.py
"""
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import pytest

pg_only = pytest.mark.requires_litkb_pg

HOUR = 3600.0


def _jsonb(obj):
    from psycopg.types.json import Jsonb

    return Jsonb(obj)


@pytest.fixture
def env(tmp_path, litkb_pg_base):
    """A literature root under tmp_path with the three staging directories, and a workstream to
    seed file rows into. The REAL literature root is never constructed: `Store(root=...)` takes the
    temp one, and no test here reads LITKB_LITERATURE_ROOT."""
    from litkb import workstream
    from litkb.acquire.store import Store

    _psycopg, conn, _ran = litkb_pg_base
    root = tmp_path / "Literture"
    for d in ("incoming", "filed", "web"):
        (root / "_litkb_staging" / d).mkdir(parents=True)
    (root / "_quarantine").mkdir(parents=True)
    wt = tmp_path / "worktree"
    wt.mkdir()
    ws_id = workstream.open_workstream(conn, f"reap-{uuid.uuid4().hex[:8]}", "test",
                                       "reaper tests", directory=wt)
    store = Store(root=root, index_cache=tmp_path / "index.json")
    return {"conn": conn, "root": root, "store": store, "ws": str(ws_id), "tmp": tmp_path}


def _plant(env, where, name, body=b"%PDF-1.4 planted\n%%EOF\n", *, age_hours=0.0):
    p = env["root"] / "_litkb_staging" / where / name
    p.write_bytes(body)
    t = time.time() - age_hours * HOUR
    os.utime(p, (t, t))
    return p


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _seed_file_row(env, *, sha, rel_path):
    """A work and a file version in the database — the ownership the reaper reads. Written as
    FACTS through `_write_version`, the way every other litkb suite seeds a file."""
    conn, ws = env["conn"], env["ws"]
    key = f"Seeded_2026_reap-{uuid.uuid4().hex[:8]}"
    work_id, _v = conn.execute(
        "SELECT entity_id, version_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, "
        "%s, NULL, %s, 'reap-seed', 'reap-seed')",
        (_jsonb({"key": key}),
         _jsonb({"type": "report", "title": "A seeded reaper target", "authors": [],
                 "year": 2026}), ws)).fetchone()
    conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'file', NULL, %s, NULL, %s, NULL, %s, "
        "'reap-seed', 'reap-seed')",
        (_jsonb({"sha256": sha}),
         _jsonb({"work_id": str(work_id), "status": "active", "rel_path": rel_path,
                 "bytes": 10, "pages": 1}), ws))
    return key


def _reap(env, **kw):
    from litkb.ops import reaper

    return reaper.reap(env["conn"], store=env["store"], **kw)


def _row(out, name):
    return next(r for r in out["rows"] if r["rel_path"].endswith(name))


def _listing(root):
    """{relpath: sha256} for every file under the literature root — the before/after the dry-run
    kill compares. It is keyed by PATH and valued by BYTES, so a move and an edit both show."""
    return {p.relative_to(root).as_posix(): _sha(p)
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


# ── what is NOT reaped ────────────────────────────────────────────────────────────────────

@pg_only
def test_a_planted_orphan_younger_than_the_threshold_is_not_reaped(env):
    """The known-bad the real corpus cannot supply: every orphan on disk on 2026-09-15 is the same
    age, so there is no young one to find and the builder must plant it (data survey §9)."""
    p = _plant(env, "incoming", "young.download", age_hours=1.0)
    out = _reap(env, min_age_hours=72, apply=True)
    assert out["counters"]["young"] == 1 and out["counters"]["quarantined"] == 0, out["counters"]
    assert _row(out, "young.download")["verdict"] == "young", out["rows"]
    assert p.exists(), "a young file is left exactly where it was"


@pg_only
def test_a_file_the_database_knows_by_sha_is_not_reaped_however_old(env):
    """The sha-keyed rule. Four real files in `incoming/` are byte-identical to files recorded
    under `filed/`; a path-keyed reaper calls all four orphans and quarantines bytes the corpus
    holds."""
    p = _plant(env, "incoming", "known.download", b"%PDF-1.4 known\n%%EOF\n", age_hours=500.0)
    _seed_file_row(env, sha=_sha(p), rel_path="_litkb_staging/filed/elsewhere.pdf")
    out = _reap(env, min_age_hours=72, apply=True)
    assert out["counters"]["owned"] == 1 and out["counters"]["quarantined"] == 0, out["counters"]
    assert _row(out, "known.download")["rule"] == "sha256 is a litkb.files row", out["rows"]
    assert p.exists()


@pg_only
def test_a_file_a_rel_path_names_is_owned_whatever_its_sha_is(env):
    """The path leg, and the sixteen `t*.download` rows it exists for: a hunt has bound the PATH
    and the bytes at it are not yet any `files.sha256`."""
    p = _plant(env, "incoming", "t0001.download", b"in flight\n", age_hours=500.0)
    _seed_file_row(env, sha=uuid.uuid4().hex + uuid.uuid4().hex,
                   rel_path="_litkb_staging/incoming/t0001.download")
    out = _reap(env, min_age_hours=72, apply=True)
    assert out["counters"]["owned"] == 1 and out["counters"]["quarantined"] == 0, out["counters"]
    assert "rel_path" in _row(out, "t0001.download")["rule"], out["rows"]
    assert p.exists()


@pg_only
def test_a_download_held_open_by_a_lock_sibling_is_young_at_any_age(env):
    p = _plant(env, "incoming", "inflight.download", age_hours=500.0)
    (env["root"] / "_litkb_staging" / "incoming" / "inflight.part").write_bytes(b"")
    out = _reap(env, min_age_hours=72, apply=True)
    assert _row(out, "inflight.download")["verdict"] == "young", out["rows"]
    assert p.exists()


@pg_only
def test_a_dry_run_moves_nothing(env):
    """The default. The whole literature root is hashed before and after: a dry run that moved a
    file would change a path, and one that rewrote a file would change a sha."""
    _plant(env, "incoming", "old.download", age_hours=500.0)
    before = _listing(env["root"])
    out = _reap(env, min_age_hours=72)
    after = _listing(env["root"])
    assert out["applied"] is False, out
    assert out["counters"]["orphans"] == 1 and out["counters"]["quarantined"] == 0, out["counters"]
    assert before == after, "a dry run changed the literature root"


# ── what IS reaped ────────────────────────────────────────────────────────────────────────

@pg_only
def test_an_old_orphan_is_quarantined_with_a_reason_beside_it(env):
    """Quarantined, never deleted: the bytes stay, under a name that says what is wrong with them,
    with a sidecar naming the census run, the sha, the age and the rule (acquire/store.py's own
    shape, and the reason the 2026-09-15 `rm -f` is not repeatable)."""
    p = _plant(env, "incoming", "orphan.download", b"%PDF-1.4 orphan\n%%EOF\n", age_hours=500.0)
    sha = _sha(p)
    out = _reap(env, min_age_hours=72, apply=True)
    assert out["counters"] == {"scanned": 1, "owned": 0, "young": 0, "orphans": 1,
                               "quarantined": 1, "skipped_errors": 0}, out["counters"]
    assert not p.exists(), "the orphan left incoming/"
    row = _row(out, "orphan.download")
    moved = env["root"] / row["quarantined"]
    assert moved.exists() and moved.read_bytes() == b"%PDF-1.4 orphan\n%%EOF\n"
    assert moved.suffix == ".download", f"the extension is kept: {moved.name}"
    assert sha[:12] in moved.name and "staging-orphan" in moved.name, moved.name
    reason = json.loads((env["root"] / row["reason_path"]).read_text(encoding="utf-8"))
    assert reason["census_run"] == out["run_id"], reason
    assert reason["sha256"] == sha and reason["was"] == row["rel_path"], reason
    assert reason["min_age_hours"] == 72 and reason["age_hours"] >= 500, reason
    assert "no database row" in reason["why"], reason


@pg_only
def test_the_txt_extract_travels_with_the_file_and_is_not_judged_alone(env):
    """`Store.land` writes `<stem>.txt` beside every download. Judged on its own account the
    extract of an OWNED file is an orphan — its bytes are in no `files` row and its path is in no
    `rel_path` — so a reaper that scanned it would quarantine the text of a file the corpus
    holds."""
    p = _plant(env, "incoming", "pair.download", b"%PDF-1.4 pair\n%%EOF\n", age_hours=500.0)
    txt = _plant(env, "incoming", "pair.txt", b"the extracted text\n", age_hours=500.0)
    out = _reap(env, min_age_hours=72, apply=True)
    assert out["counters"]["scanned"] == 1, out["rows"]
    assert out["counters"]["quarantined"] == 1, out["counters"]
    assert not p.exists() and not txt.exists(), "both moved together"
    moved = env["root"] / _row(out, "pair.download")["quarantined"]
    assert moved.with_suffix(".txt").exists(), "the extract followed its file"


@pg_only
def test_the_web_snapshot_is_scanned_and_owned_by_its_rel_path(env):
    """`_litkb_staging/web/` holds one file on live — a `.txt` snapshot that IS the bound file of
    a manual proposal. It has no primary sibling, so it is judged on its own account, and the
    path leg is what keeps it."""
    _plant(env, "web", "snapshot.txt", b"a web snapshot\n", age_hours=500.0)
    _seed_file_row(env, sha=uuid.uuid4().hex + uuid.uuid4().hex,
                   rel_path="_litkb_staging/web/snapshot.txt")
    out = _reap(env, min_age_hours=72, apply=True)
    assert _row(out, "snapshot.txt")["verdict"] == "owned", out["rows"]
    assert out["counters"]["quarantined"] == 0, out["counters"]


@pg_only
def test_the_reaper_writes_no_database_row(env):
    """It reads `litkb.files` and `litkb.file_versions` and nothing else. Asserted by counting the
    two tables and every acquisition attempt across a run that quarantines."""
    conn = env["conn"]
    _plant(env, "incoming", "counted.download", age_hours=500.0)

    def counts():
        return tuple(conn.execute(
            "SELECT (SELECT count(*) FROM litkb.files), "
            "       (SELECT count(*) FROM litkb.file_versions), "
            "       (SELECT count(*) FROM litkb.acquisition_attempts)").fetchone())

    before = counts()
    out = _reap(env, min_age_hours=72, apply=True)
    assert out["counters"]["quarantined"] == 1, out["counters"]
    assert counts() == before, "the reaper wrote to the database"
