r"""The litkb nightly soak: one smoke search, one smoke hunt, one row in `Reports/LITKB_SOAK.csv`.

    python -m litkb.ops.nightly_soak --once            run it now against the live database
    python -m litkb.ops.nightly_soak --install-task    register the Windows task (daily 03:17)

WHY IT STARTS IN S1 AND NOT IN S7. S7's done-state is "seven nights unattended", and Kam's ruling
of 2026-09-20 is that those nights are STARTED EARLY: the task goes in now, the nights accumulate
while S2-S6 proceed, and S7 extends this run with the full `litkb doctor` and reads the log. The
alternative was a week of calendar at the end of the plan doing nothing but waiting.

That is also why **the row schema is fixed HERE**: S7's `litkb_acceptance.py soak` subcommand has
to read every night from S1 onward, so a column added later would split the log in two and the
first nights would be the half that cannot be read. `doctor_ok` and `doctor_detail` are therefore
written EMPTY tonight and are not optional — they are the two columns S7 fills in.

WHAT IT SMOKES, AND WHY THOSE TWO THINGS.
  1. `search` — the read path end to end: connection, role, the three lexical legs, the visibility
     join. A fixed query on a work known to be extracted, so a zero-hit night is a defect and not
     a change of subject.
  2. `hunt(spend=False, extract=True)` on one known-extracted DOI — the CACHED-ANSWER path. Hunt
     is meant to answer from the database first: a reference already extracted comes back with its
     state having fetched, converted and written nothing. So this costs no network, no quota and
     no extraction, and it exercises resolve -> look_up -> report, which is the path every hunt
     takes before it decides whether to spend. `spend=False` makes the no-acquisition promise
     structural rather than incidental.

`hunt_ok` is TRUE ONLY WHEN THE STATE IS `extracted`. This is the distinction the soak exists for:
a known-extracted DOI coming back `held` or `held-no-spend` means the file, the run or the blocks
went away, and `ok: true` would be recorded for exactly that regression, because the hunt itself
did not fail — it correctly reported a database that had lost the work.

THE WORKSTREAM AND ITS TOKEN. `hunt` writes (it links, it records attempts), so it needs an open
workstream, and a workstream's token lives in a file next to the worktree it belongs to. This job
belongs to no worktree — it must keep running while branches come and go — so its token directory
is OUTSIDE every repository: `D:\edmonds-pipeline\secrets\litkb-tokens\soak-ws\`, opened once with
`litkb --dir <that dir> ws open soak`. `litkb ws open` accepts a non-git directory (measured
2026-09-20: it records `branch unknown` and does not refuse), which is what makes a standing
workstream possible at all. The token is read from the file BY THE SERVER; nothing here opens it,
prints it or logs it.

`LITKB_WORKTREE` is set explicitly before the search too. Without it `_worktree()` shells out to
`git rev-parse --show-toplevel` from whatever directory the scheduler started in, and a
`.litkb-workstream` sitting in some checkout would widen the search to that workstream's
proposals — so the same query would return a different number of hits depending on where the task
happened to be launched from. A soak whose baseline moves is not a baseline.

Never writes to a database beyond what hunt's own linking does; never fetches; never acquires.
"""
import argparse
import csv
import datetime as dt
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

#: parents[4] is the repository root (this file is Scripts/pipeline/litkb/ops/nightly_soak.py).
#: Pinned by test_the_csv_path_is_inside_the_repo, not by counting in prose.
REPO_ROOT = Path(__file__).resolve().parents[4]
SOAK_CSV = REPO_ROOT / "Reports" / "LITKB_SOAK.csv"

#: The standing workstream's token directory, outside every repository (module docstring).
TOKEN_DIR = Path(os.environ.get("LITKB_SOAK_TOKEN_DIR",
                                r"D:\edmonds-pipeline\secrets\litkb-tokens\soak-ws"))
WORKSTREAM_SLUG = "soak"

#: The smoke hunt's target. Chosen from the LIVE database on 2026-09-20 with `litkb_work`:
#: state `extracted`, 254 blocks, one bound file, DOI verified by crossref. It is also the work
#: proving run 2 was built on, so a night where this one stops being readable is a night that
#: breaks a run already on the record — which is exactly the kind of regression worth an alarm.
SMOKE_KEY = "Kaiser_2017_learning-aerial-image-segmentation"
SMOKE_DOI = "10.1109/tgrs.2017.2719738"

#: A query whose words are in that work's own title block, so a zero-hit night is a defect in the
#: search path and not a question about phrasing. Never a paraphrase: the vector leg is off
#: until P7 and a paraphrase sharing no words with the text will not be found.
SMOKE_QUERY = "learning aerial image segmentation from online maps"

TASK_NAME = "litkb-nightly-soak"
TASK_AT = "03:17"          # after the 02:30 dump, so a night's dump is already on disk

#: FIXED IN S1 so S7 can read every night from S1 onward (module docstring). `doctor_ok` and
#: `doctor_detail` stay empty until S7 fills them.
COLUMNS = ("ts_utc", "host", "repo_head", "migration_tip", "search_ok", "search_ms",
           "search_hits", "hunt_ok", "hunt_ms", "hunt_state", "hunt_key", "doctor_ok",
           "doctor_detail", "error")


def _utc(now=None):
    return (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_passfile():
    """libpq's default pgpass on Windows, resolved now — a scheduled task may run without the
    user profile loaded, so the path is read at install time and passed explicitly (the same
    reasoning as litkb/ops/nightly_dump.py)."""
    appdata = os.environ.get("APPDATA")
    return str(Path(appdata) / "postgresql" / "pgpass.conf") if appdata else None


def _first_line(text):
    lines = [ln.strip() for ln in (str(text) or "").splitlines() if ln.strip()]
    return lines[0][:300] if lines else ""


def repo_head(repo=REPO_ROOT):
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def migration_tip(db, passfile=None):
    """The highest migration version APPLIED to `db`, or "" when it cannot be read.

    `litkb_meta` is readable by `litkb_owner` alone — measured 2026-09-20: litkb_reader and
    litkb_writer both get `permission denied for schema litkb_meta`, and litkb_ingest refuses the
    login. So this is an admin read through the passfile, and an unreadable tip is an EMPTY cell,
    never the on-disk tip substituted for it: "what the repository holds" and "what the database
    has applied" are different facts and the whole reason S7 compares them.
    """
    try:
        from litkb.db import connect as c
        if passfile:
            os.environ["PGPASSFILE"] = str(passfile)
        conn = c.connect_admin(db, c.OWNER, autocommit=True)
        try:
            v = conn.execute("SELECT max(version) FROM litkb_meta.schema_migrations").fetchone()[0]
            return "" if v is None else str(v)
        finally:
            conn.close()
    except Exception:                       # noqa: BLE001 — an unreadable tip is a blank cell
        return ""


# ── the two smokes ───────────────────────────────────────────────────────────────────────────────

def smoke_search(query=SMOKE_QUERY, limit=5):
    """(ok, ms, hits, error). Reads through the same `_search` the MCP tool calls.

    There is no `litkb.search` module: the search implementation lives in `litkb/mcp/server.py`
    and the MCP tool is a thin wrapper over it, so calling `_search` here IS the Python API and
    not a reimplementation of it (CLAUDE.md 3.3 — one fact, one home). Calling it directly rather
    than over MCP is deliberate: an unattended job must not depend on an MCP client being alive.

    It returns a JSON STRING, not a dict — every tool in that module returns through `_out()`,
    which dumps and then runs both redactors over the text. So the parse below is not an
    inefficiency to tidy away: the string is what the tool returns, redactors included, and
    parsing it is what makes this smoke exercise the same bytes a caller would see.
    """
    from litkb.mcp import server
    t0 = time.monotonic()
    try:
        res = json.loads(server._search(query, limit, "blocks"))
        ms = int((time.monotonic() - t0) * 1000)
        hits = len(res.get("blocks") or [])
        if not res.get("ok"):
            return False, ms, hits, _first_line(res.get("message") or res.get("refused") or "not ok")
        if hits == 0:
            return False, ms, 0, f"the fixed smoke query returned no block: {query!r}"
        return True, ms, hits, ""
    except Exception as e:                  # noqa: BLE001 — a failed smoke is a ROW, not a crash
        return False, int((time.monotonic() - t0) * 1000), 0, \
            f"{type(e).__name__}: {_first_line(e)}"


def smoke_hunt(db, worktree=TOKEN_DIR, agent="soak", session=None):
    """(ok, ms, state, error). The cached-answer path on one known-extracted DOI, no spend.

    `ok` is True ONLY at state `extracted` — see the module docstring: a hunt that correctly
    reports a database which has lost the work returns `ok: true`, and that is the regression
    this job exists to catch.
    """
    from litkb import hunt as H
    t0 = time.monotonic()
    try:
        res = H.hunt(SMOKE_DOI, db=db, worktree=Path(worktree), agent=agent,
                     session=session or "nightly", spend=False, extract=True)
    except Exception as e:                  # noqa: BLE001
        return False, int((time.monotonic() - t0) * 1000), "error", \
            f"{type(e).__name__}: {_first_line(e)}"
    ms = int((time.monotonic() - t0) * 1000)
    state = str(res.get("state") or res.get("refused") or "")
    if not res.get("ok"):
        return False, ms, state, _first_line(res.get("message") or "hunt refused")
    if state != "extracted":
        return False, ms, state, (f"{SMOKE_KEY} is known-extracted and came back {state!r}: the "
                                  "file, its current run or its blocks are gone")
    return True, ms, state, ""


# ── the row ──────────────────────────────────────────────────────────────────────────────────────

def append_row(row, path=SOAK_CSV, repo=REPO_ROOT):
    """Append exactly one row, writing the FIXED header on first run. -> the path written.

    `repo` is the containment root, a parameter so the tests can bound a tmp_path run — which is
    the only honest way to exercise the writer: a test that patched the guard away would be
    testing a writer with no guard on it."""
    path = Path(path)
    guard_path(path, repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.is_file() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        if fresh:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLUMNS})
    return path


def guard_path(path, repo=REPO_ROOT):
    """Refuse a soak CSV outside the repository.

    The path is resolved from `__file__`, so under normal use this cannot fire — which is exactly
    why it is here and tested. `--csv` exists for the tests and would otherwise be an unbounded
    write primitive in a job that runs unattended every night as the logged-in user. `report_path`
    in S7 gets the same treatment for the same reason.
    """
    try:
        Path(path).resolve().relative_to(Path(repo).resolve())
    except ValueError:
        raise SystemExit(f"litkb-soak: refusing a CSV outside the repository: {path}") from None


def run(db=None, path=SOAK_CSV, passfile=None, worktree=TOKEN_DIR, session=None, now=None,
        repo=REPO_ROOT):
    """One soak run. -> 0 when both smokes passed, 1 otherwise. ALWAYS writes exactly one row."""
    from litkb.db import connect as c
    db = db or os.environ.get("LITKB_DB") or c.DB_MAIN
    # Pin both for every call below: `_search` reads LITKB_DB and resolves the worktree by shelling
    # to git from the cwd, which for a scheduled task is whatever Start In happens to be.
    os.environ["LITKB_DB"] = db
    os.environ["LITKB_WORKTREE"] = str(worktree)
    if passfile:
        os.environ["PGPASSFILE"] = str(passfile)

    row = {"ts_utc": _utc(now), "host": socket.gethostname(), "repo_head": repo_head(),
           "migration_tip": migration_tip(db, passfile), "hunt_key": SMOKE_KEY,
           "doctor_ok": "", "doctor_detail": ""}
    errors = []

    s_ok, s_ms, s_hits, s_err = smoke_search()
    row.update(search_ok="true" if s_ok else "false", search_ms=s_ms, search_hits=s_hits)
    if s_err:
        errors.append(f"search: {s_err}")

    h_ok, h_ms, h_state, h_err = smoke_hunt(db, worktree=worktree, session=session)
    row.update(hunt_ok="true" if h_ok else "false", hunt_ms=h_ms, hunt_state=h_state)
    if h_err:
        errors.append(f"hunt: {h_err}")

    row["error"] = " | ".join(errors)
    append_row(row, path, repo)
    return 0 if (s_ok and h_ok) else 1


# ── scheduled task ───────────────────────────────────────────────────────────────────────────────

def install_task(at=TASK_AT, logon="S4U", passfile=None):
    """Register TASK_NAME for the current user, daily at `at`.

    Same shape as litkb/ops/nightly_dump.py: S4U runs whether the user is logged on or not without
    storing a password, -Force makes it idempotent, and `$ErrorActionPreference = 'Stop'` is there
    because without it a REFUSED registration still prints 'registered'. Start In is the MAIN
    tree's Scripts\\pipeline, not this file's — a scheduled job must not follow a worktree that
    gets disposed of.

    ONE DIFFERENCE FROM nightly_dump: PowerShell's output is NOT captured and re-printed here. It
    is inherited, so it reaches the operator's console directly, and the only thing this function
    writes is a constant. `qc/instruments/litkb_p2_mutations.py::sink_check` requires every
    stdout sink under this package to take a redactor's return, interpolate nothing, or be named
    in SINK_ALLOW with a reason — nightly_dump's equivalent print is in that allowlist. Inheriting
    the stream instead needs no allowlist entry AND loses nothing: the operator sees PowerShell's
    real error rather than its first line, and a passfile path in a PowerShell error can no longer
    pass through an unredacted interpolation in this module.
    """
    args = f"-m litkb.ops.nightly_soak --passfile \"{passfile or default_passfile()}\""
    start_in = Path(r"D:\edmonds-pipeline\treedata\Scripts\pipeline")
    ps = (
        "$ErrorActionPreference = 'Stop';"
        f"$a = New-ScheduledTaskAction -Execute '{sys.executable}' -Argument '{args}' "
        f"-WorkingDirectory '{start_in}';"
        f"$t = New-ScheduledTaskTrigger -Daily -At {at};"
        "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30);"
        f"$p = New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\\$env:USERNAME\" "
        f"-LogonType {logon} -RunLevel Limited;"
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s "
        "-Principal $p -Force | Out-Null; 'registered'")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], text=True)
    if r.returncode != 0:
        print("litkb-soak: registering the scheduled task FAILED; PowerShell's own message is "
              "above. If the permission classifier refused it, run the command by hand.")
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description="litkb nightly soak: smoke search + cached hunt, one "
                                             "row in Reports/LITKB_SOAK.csv")
    ap.add_argument("--once", action="store_true", help="run it now (the default action)")
    ap.add_argument("--install-task", action="store_true")
    ap.add_argument("--at", default=TASK_AT)
    ap.add_argument("--logon", choices=["S4U", "Interactive"], default="S4U")
    ap.add_argument("--db", default=None)
    ap.add_argument("--csv", default=str(SOAK_CSV), help="the soak CSV (must be inside the repo)")
    ap.add_argument("--passfile", default=None)
    ap.add_argument("--worktree", default=str(TOKEN_DIR),
                    help="the directory holding the standing workstream's token")
    ap.add_argument("--session", default=None)
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if a.install_task:
        return install_task(at=a.at, logon=a.logon, passfile=a.passfile)
    return run(db=a.db, path=Path(a.csv), passfile=a.passfile, worktree=Path(a.worktree),
               session=a.session)


if __name__ == "__main__":
    sys.exit(main())
