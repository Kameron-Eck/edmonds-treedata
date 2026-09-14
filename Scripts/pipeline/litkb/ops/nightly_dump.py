"""litkb nightly database dump (decisions.yaml litkb-p0-foundation, design §15.12: a nightly pg_dump
of the database records; no PDFs, no derived artifacts).

    python -m litkb.ops.nightly_dump                    dump litkb as litkb_owner, verify, prune to 14
    python -m litkb.ops.nightly_dump --restore-check    also restore into litkb_restore_check, compare counts
    python -m litkb.ops.nightly_dump --verify-existing  re-verify every dump the manifest lists
    python -m litkb.ops.nightly_dump --install-task     register the Windows scheduled task (daily 02:30)

Run from Scripts/pipeline (or with the package installed). Passwords never appear on a command line:
pg_dump and pg_restore run with -w and read the pgpass file (--passfile, else libpq's default).

WHAT "VERIFIED" MEANS, AND WHAT IT DOES NOT (probed 2026-09-13 on a real litkb_test dump,
Reports/LITKB_OPS_2026-09-13.md):
  1. `pg_restore --list` reads only the table of contents at the head of a custom-format file. A dump
     with its last 200 bytes cut off PASSED it. It is the cheap first stage, never the only one.
  2. `pg_restore -f -` (stdout discarded) reads every data block to the end: every truncation tried
     (1 byte to half the file) FAILED it ("end of file"), and a damaged compressed block fails its zlib
     check. Garbage written into some other regions still passed both stages.
  3. So the sha256 of the file, hashed once it has passed 1 and 2, goes into manifest.json. Retention
     and --verify-existing re-hash against it, which catches damage at rest that pg_restore cannot see.
  4. Weekly, or with --restore-check: restore into a scratch database and compare exact per-table row
     counts with the source. The source is counted inside the SAME snapshot pg_dump used
     (pg_export_snapshot + pg_dump --snapshot), so a write landing during the dump cannot cause a false
     mismatch, and a real mismatch is a failure.

Retention deletes only files the manifest lists (written by this script, only after verification), whose
name has this script's shape and whose bytes still hash to the manifest's sha256. Nothing else in the
directory is ever touched. A dump that fails verification is renamed *.rejected and never listed.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from litkb.db import connect as c

PG_BIN = Path(os.environ.get("LITKB_PGBIN", r"C:\Program Files\PostgreSQL\18\bin"))
OUT_DIR = Path(os.environ.get("LITKB_DUMP_DIR", r"D:\edmonds-pipeline\pgdump\litkb"))
KEEP = 14
RESTORE_EVERY = dt.timedelta(days=7)
SCRATCH_DB = "litkb_restore_check"
TASK_NAME = "litkb-nightly-dump"
MANIFEST = "manifest.json"
LOG = "nightly_dump.log"
SCHEMAS = ("litkb", "litkb_meta")


def default_passfile():
    """libpq's default pgpass location on Windows, resolved now (a scheduled task may run without
    the user profile loaded, so APPDATA is read at install time and passed explicitly)."""
    appdata = os.environ.get("APPDATA")
    return str(Path(appdata) / "postgresql" / "pgpass.conf") if appdata else None


def _exe(name):
    p = PG_BIN / f"{name}.exe"
    return str(p) if p.exists() else name


def _env(passfile):
    env = dict(os.environ)
    if passfile:
        env["PGPASSFILE"] = str(passfile)
    return env


def _utc(now):
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def name_re(db):
    return re.compile(rf"{re.escape(db)}_\d{{8}}T\d{{6}}Z\.dump")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── verification ─────────────────────────────────────────────────────────────────────────────────

def verify_dump(path, expected_sha=None):
    """(ok, stage, reason). Stages: list (TOC), read (every data block), sha (manifest hash)."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return False, "exists", "missing or empty"
    r = subprocess.run([_exe("pg_restore"), "--list", str(path)], capture_output=True, text=True,
                       errors="replace")
    toc = [ln for ln in (r.stdout or "").splitlines() if ln.strip() and not ln.startswith(";")]
    if r.returncode != 0 or not toc:
        return False, "list", _first_line(r.stderr) or f"rc={r.returncode}, {len(toc)} TOC entries"
    r = subprocess.run([_exe("pg_restore"), "-f", "-", str(path)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, text=True, errors="replace")
    if r.returncode != 0:
        return False, "read", _first_line(r.stderr) or f"rc={r.returncode}"
    if expected_sha is not None and sha256_file(path) != expected_sha:
        return False, "sha", "sha256 differs from the manifest"
    return True, "ok", f"{len(toc)} TOC entries"


def _first_line(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[0][:200] if lines else ""


# ── row counts ───────────────────────────────────────────────────────────────────────────────────

def _connect(db, user):
    if user in c.ADMIN_LOGINS:
        return c.connect_admin(db, user, autocommit=False)
    return c.connect(db, user, autocommit=False)


def table_counts(conn, schemas):
    """{schema.table: exact count(*)} for every ordinary and partitioned table in `schemas`."""
    from psycopg import sql
    rels = conn.execute(
        "SELECT n.nspname, cl.relname FROM pg_class cl JOIN pg_namespace n ON n.oid = cl.relnamespace "
        "WHERE n.nspname = ANY (%s) AND cl.relkind IN ('r', 'p') ORDER BY 1, 2", (list(schemas),)).fetchall()
    return {f"{s}.{t}": conn.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(
        sql.Identifier(s), sql.Identifier(t))).fetchone()[0] for s, t in rels}


def compare_counts(source, restored):
    """Human-readable differences; empty means the restore matches the source exactly."""
    out = [f"{t}: missing from the restore" for t in sorted(set(source) - set(restored))]
    out += [f"{t}: in the restore, not the source" for t in sorted(set(restored) - set(source))]
    out += [f"{t}: source {source[t]} rows, restore {restored[t]}"
            for t in sorted(set(source) & set(restored)) if source[t] != restored[t]]
    return out


def restore_and_count(dump_path, source_db, schemas, passfile):
    """Restore into SCRATCH_DB (as the superuser: the owner has no CREATEDB) in the source's tablespace,
    count, and always drop the scratch database. Returns {schema.table: count}."""
    from psycopg import sql
    su = c.connect_admin("postgres", c.SUPERUSER, autocommit=True)
    try:
        ts = su.execute("SELECT t.spcname FROM pg_database d JOIN pg_tablespace t ON t.oid = d.dattablespace "
                        "WHERE d.datname = %s", (source_db,)).fetchone()[0]
        scratch = sql.Identifier(SCRATCH_DB)
        su.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(scratch))
        su.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 TABLESPACE {}").format(
            scratch, sql.Identifier(ts)))
        try:
            # new databases grant CONNECT to PUBLIC; the copy of the records must not be a side door
            su.execute(sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC").format(scratch))
            r = subprocess.run([_exe("pg_restore"), "-w", "-h", c.HOST, "-p", str(c.PORT), "-U", c.SUPERUSER,
                                "-d", SCRATCH_DB, "--exit-on-error", str(dump_path)],
                               capture_output=True, text=True, errors="replace", env=_env(passfile))
            if r.returncode != 0:
                raise RuntimeError(f"pg_restore into {SCRATCH_DB} failed: {_first_line(r.stderr)}")
            k = c.connect_admin(SCRATCH_DB, c.SUPERUSER, autocommit=True)
            try:
                return table_counts(k, schemas)
            finally:
                k.close()
        finally:
            su.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(scratch))
    finally:
        su.close()


# ── manifest and log ─────────────────────────────────────────────────────────────────────────────

def load_manifest(out_dir):
    p = Path(out_dir) / MANIFEST
    if not p.exists():
        return {"dumps": [], "last_restore_check_utc": None}
    return json.loads(p.read_text(encoding="utf-8"))


def save_manifest(out_dir, manifest):
    p = Path(out_dir) / MANIFEST
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def log_line(out_dir, line):
    with open(Path(out_dir) / LOG, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def restore_due(manifest, now):
    last = manifest.get("last_restore_check_utc")
    if not last:
        return True
    return now - dt.datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) >= RESTORE_EVERY


def prune(out_dir, manifest, db, keep):
    """Delete the oldest listed good dumps beyond `keep`. Returns (deleted, notes)."""
    out_dir = Path(out_dir)
    good = sorted((e for e in manifest["dumps"]
                   if e["db"] == db and (e.get("restore_check") or {}).get("ok", True)),
                  key=lambda e: e["name"])
    deleted, notes = [], []
    for e in good[:max(0, len(good) - keep)]:
        path = out_dir / e["name"]
        if not name_re(db).fullmatch(e["name"]) or path.name != e["name"]:
            notes.append(f"{e['name']}: not this script's name shape, left")
            continue
        if not path.exists():
            manifest["dumps"].remove(e)
            notes.append(f"{e['name']}: already gone, unlisted")
            continue
        if sha256_file(path) != e["sha256"]:
            notes.append(f"{e['name']}: sha256 differs from the manifest, left for inspection")
            continue
        path.unlink()
        manifest["dumps"].remove(e)
        deleted.append(e["name"])
    return deleted, notes


# ── the run ──────────────────────────────────────────────────────────────────────────────────────

def _pg_dump(db, user, snapshot, path, dump_schemas, passfile):
    cmd = [_exe("pg_dump"), "-Fc", "-w", "-h", c.HOST, "-p", str(c.PORT), "-U", user, "-d", db,
           "--snapshot", snapshot, "-f", str(path)]
    for s in dump_schemas or ():
        cmd += ["-n", s]
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", env=_env(passfile))


def run(db=c.DB_MAIN, user=c.OWNER, out_dir=OUT_DIR, passfile=None, restore=None, keep=KEEP,
        schemas=SCHEMAS, dump_schemas=None, now=None):
    """One dump. restore: True/False, or None = when the last good restore check is 7+ days old.
    Returns 0 when the dump was kept verified (and the restore check, if run, matched)."""
    import psycopg
    t0 = time.monotonic()
    now = now or dt.datetime.now(dt.timezone.utc)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if passfile:
        os.environ["PGPASSFILE"] = str(passfile)   # libpq in this process (psycopg) too
    name = f"{db}_{now.strftime('%Y%m%dT%H%M%SZ')}.dump"
    final, tmp = out_dir / name, out_dir / (name + ".partial")
    manifest = load_manifest(out_dir)
    if restore is None:
        restore = restore_due(manifest, now)
    fields = {"db": db, "file": name}

    def finish(status, **more):
        fields.update(more)
        fields["secs"] = f"{time.monotonic() - t0:.1f}"
        log_line(out_dir, f"{_utc(now)} status={status} " + " ".join(f"{k}={v}" for k, v in fields.items()))
        return 0 if status == "ok" else 1

    if final.exists() or tmp.exists():
        return finish("FAIL", stage="name", reason="a dump with this timestamp already exists")
    try:
        conn = _connect(db, user)
    except (psycopg.Error, c.LoginRefused) as e:
        return finish("FAIL", stage="connect", reason=_quote(_first_line(str(e))))
    try:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        snapshot = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
        r = _pg_dump(db, user, snapshot, tmp, dump_schemas, passfile)
        source_counts = table_counts(conn, dump_schemas or schemas) if restore and r.returncode == 0 else None
        conn.rollback()
    finally:
        conn.close()
    if r.returncode != 0:
        _reject(tmp)
        return finish("FAIL", stage="pg_dump", reason=_quote(_first_line(r.stderr)))

    ok, stage, reason = verify_dump(tmp)
    if not ok:
        _reject(tmp)
        return finish("FAIL", stage=stage, reason=_quote(reason), kept="no")
    sha = sha256_file(tmp)
    os.replace(tmp, final)
    entry = {"name": name, "db": db, "created_utc": _utc(now), "bytes": final.stat().st_size,
             "sha256": sha, "verified": ["list", "read"], "restore_check": None}
    manifest["dumps"].append(entry)
    save_manifest(out_dir, manifest)
    fields.update(bytes=entry["bytes"], sha256=sha[:16], verify="list+read")

    status = "ok"
    if restore:
        try:
            restored = restore_and_count(final, db, dump_schemas or schemas, passfile)
            diffs = compare_counts(source_counts, restored)
        except Exception as e:  # noqa: BLE001 — any restore failure is a failed check, reported
            diffs = [f"restore failed: {_first_line(str(e))}"]
        entry["restore_check"] = {"utc": _utc(now), "ok": not diffs, "tables": len(source_counts),
                                  "rows": sum(source_counts.values()), "differences": diffs[:20]}
        if diffs:
            status = "FAIL"
            fields.update(restore="MISMATCH", reason=_quote("; ".join(diffs[:3])))
        else:
            manifest["last_restore_check_utc"] = _utc(now)
            fields.update(restore=f"ok({len(source_counts)}tables/{sum(source_counts.values())}rows)")
        save_manifest(out_dir, manifest)
    else:
        fields["restore"] = "skipped"

    deleted, notes = prune(out_dir, manifest, db, keep)
    save_manifest(out_dir, manifest)
    fields.update(pruned=len(deleted), kept=sum(1 for e in manifest["dumps"] if e["db"] == db))
    if notes:
        fields["prune_notes"] = _quote("; ".join(notes))
    return finish(status)


def _reject(tmp):
    if tmp.exists():
        os.replace(tmp, tmp.with_name(tmp.name.replace(".partial", ".rejected")))


def _quote(s):
    return json.dumps(s, ensure_ascii=True)


def verify_existing(out_dir=OUT_DIR):
    out_dir = Path(out_dir)
    manifest, bad = load_manifest(out_dir), 0
    for e in manifest["dumps"]:
        ok, stage, reason = verify_dump(out_dir / e["name"], expected_sha=e["sha256"])
        bad += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {e['name']} {stage}: {reason}")
    log_line(out_dir, f"{_utc(dt.datetime.now(dt.timezone.utc))} status={'ok' if not bad else 'FAIL'} "
                      f"verify-existing dumps={len(manifest['dumps'])} failed={bad}")
    return 1 if bad else 0


# ── scheduled task ───────────────────────────────────────────────────────────────────────────────

def install_task(at="02:30", logon="S4U", passfile=None):
    """Register TASK_NAME for the current user. S4U = "run whether the user is logged on or not"
    without storing a password; Interactive = only while logged on. Idempotent (-Force)."""
    pipeline_dir = Path(__file__).resolve().parents[2]
    passfile = passfile or default_passfile()
    args = f"-m litkb.ops.nightly_dump --passfile \"{passfile}\""
    ps = (
        "$ErrorActionPreference = 'Stop';"   # else a refused registration still prints 'registered'
        f"$a = New-ScheduledTaskAction -Execute '{sys.executable}' -Argument '{args}' "
        f"-WorkingDirectory '{pipeline_dir}';"
        f"$t = New-ScheduledTaskTrigger -Daily -At {at};"
        "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2);"
        f"$p = New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\\$env:USERNAME\" -LogonType {logon} "
        "-RunLevel Limited;"
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s -Principal $p "
        "-Force | Out-Null; 'registered'")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, errors="replace")
    print((r.stdout or "").strip() or _first_line(r.stderr))
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description="litkb nightly pg_dump with verification and retention")
    ap.add_argument("--db", default=c.DB_MAIN)
    ap.add_argument("--user", default=c.OWNER)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--passfile", default=None, help="pgpass file (default: libpq's own lookup)")
    ap.add_argument("--keep", type=int, default=KEEP)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--restore-check", dest="restore", action="store_true", default=None,
                   help="restore into litkb_restore_check and compare row counts (default: weekly)")
    g.add_argument("--no-restore-check", dest="restore", action="store_false")
    ap.add_argument("--verify-existing", action="store_true")
    ap.add_argument("--install-task", action="store_true")
    ap.add_argument("--logon", choices=["S4U", "Interactive"], default="S4U")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if a.install_task:
        return install_task(logon=a.logon, passfile=a.passfile)
    if a.verify_existing:
        return verify_existing(a.out_dir)
    try:
        return run(a.db, a.user, a.out_dir, a.passfile, a.restore, a.keep)
    except Exception as e:  # noqa: BLE001 — an unattended job must leave a line, not only a task result code
        Path(a.out_dir).mkdir(parents=True, exist_ok=True)
        log_line(a.out_dir, f"{_utc(dt.datetime.now(dt.timezone.utc))} status=FAIL db={a.db} stage=crash "
                            f"reason={_quote(type(e).__name__ + ': ' + _first_line(str(e)))}")
        raise


if __name__ == "__main__":
    sys.exit(main())
