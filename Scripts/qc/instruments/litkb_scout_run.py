r"""The scout run driver: every drop-off the scout left, resolved through `hunt`, one CSV row each.

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_scout_run.py \
        --manifest <frozen.json> --out Reports/LITKB_SCOUT_RUN_2026-09-20.csv

WHY IT IS A SEPARATE PROCESS FROM THE SCOUT. The scout holds no `litkb_hunt` tool, on purpose: it
drops off BEFORE any full text exists, so its expectation is a prior the pipeline can later test.
Something has to follow the drop-offs up, and it must not be the agent that wrote them — the
proposer never scores its own proposal (CLAUDE.md 3.4c). This driver is that something: it is
deterministic, runs no model, and takes no input but the frozen manifest and the database.

WHAT IT DOES NOT DO. It does not spend. Every call passes `spend=False`, so a reference that
resolves to `held` stops there and is recorded as `held-no-spend` — a named, deliberate outcome.
Acquisition is a decision with a cost and it is not this instrument's to make; the manifest
records `spend: false` so a reader can see the run was bounded that way before it started.

IDEMPOTENT AND RESUMABLE. The CSV is the ledger. A drop-off whose `hr_id` already has a row is
skipped and its row is preserved byte for byte, so a run interrupted after seven of fifteen hunts
resumes at the eighth and the seven cost nothing. That matters more than it looks: a hunt that
reaches extraction is minutes, not seconds, and a driver that redid its work on every crash would
make the acceptance run unaffordable exactly when it was already going badly.

THE `ref_scheme` ARGUMENT. `hunt(ref, ref_scheme=…)` is the contract the ref-VALIDATING `ref_kind`
introduces (S1): the scout says what kind of thing it dropped off, and hunt refuses a mismatch
(`ref-scheme-mismatch`) instead of re-guessing. The scheme travels from the drop-off row, never
from this driver's own reading of the string — re-classifying here would be a second home for the
same fact (CLAUDE.md 3.3) and would hide exactly the disagreement the refusal exists to surface.

Every hunt is wrapped: a raised exception becomes a row with `hunt_ok=false` and
`hunt_state_or_refusal=error`, never a dead run with nothing written. `error` is outside
`litkb_acceptance.CLOSED_STATES`, so a crash lands on `unknown_states` and the acceptance command
refuses the run — which is the point. A driver that swallowed a crash into a "known" state would
report a clean sheet for a run that did nothing.

Stdlib plus the litkb package; the heavy imports are lazy. Not run on Colab (CLAUDE.md 3.10
applies to the Colab entry points).
"""
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
ACCEPTANCE = SCRIPTS / "qc" / "instruments" / "litkb_acceptance.py"


def _acceptance():
    """The sibling instrument, by path: `qc/instruments/` is deliberately not a package
    (pyproject), so there is no import to make. One home for the column list, the required-field
    set and the frozen-manifest reader — this driver must not grow a second copy of any of them."""
    spec = importlib.util.spec_from_file_location("litkb_acceptance", ACCEPTANCE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def existing_rows(path):
    """(rows already written, in file order). The resume ledger."""
    p = Path(path)
    if not p.is_file():
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _hunt_once(hunt, row, *, db, worktree, agent, session, spend):
    """One drop-off through `hunt`. -> (ok, state_or_refusal, message, seconds)."""
    t0 = time.monotonic()
    try:
        res = hunt(row["ref"],
                   ref_scheme=row.get("ref_scheme"),
                   hunt_request_id=str(row["id"]),
                   spend=spend,
                   db=db,
                   worktree=worktree,
                   agent=agent,
                   session=session,
                   title=row.get("claimed_title"),
                   author=row.get("claimed_authors"),
                   year=row.get("claimed_year"))
    except Exception as e:                  # noqa: BLE001 — a crash is a ROW, never a dead run
        return False, "error", f"{type(e).__name__}: {str(e).splitlines()[0][:300]}", \
            round(time.monotonic() - t0, 2)
    secs = round(time.monotonic() - t0, 2)
    if not isinstance(res, dict):
        return False, "error", f"hunt returned {type(res).__name__}, not a dict", secs
    ok = bool(res.get("ok"))
    state = res.get("state") or res.get("refused") or ""
    return ok, str(state), str(res.get("message") or "")[:500], secs


def run(manifest, out, *, hunt=None, rows=None, agent="scout-driver", session=None, limit=None):
    """Drive every drop-off in the manifest's workstream. -> (written, skipped, [row dicts])."""
    acc = _acceptance()
    db = manifest["db"]
    role = manifest.get("reader_role") or "litkb_reader"
    since = acc._parse_utc(manifest["frozen_at"])
    worktree = manifest.get("worktree") or manifest["repo"]
    spend = bool(manifest.get("spend", False))
    session = session or f"scout-run-{manifest['frozen_at']}"

    if rows is None:
        ws_id = manifest.get("workstream_id") or acc.resolve_workstream(
            db, role, manifest["workstream_slug"])
        if not ws_id:
            raise SystemExit(f"litkb_scout_run: no OPEN workstream {manifest['workstream_slug']!r} "
                             f"in {db}")
        rows = acc._hunt_request_rows(db, role, ws_id, since)
    if hunt is None:
        import litkb.hunt as H
        hunt = H.hunt

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = existing_rows(out)
    seen = {str(r.get("hr_id", "")).strip() for r in done}
    written = list(done)
    n_new = 0
    for row in rows:
        hr_id = str(row["id"])
        if hr_id in seen:
            continue
        if limit is not None and n_new >= limit:
            break
        ok, state, message, secs = _hunt_once(hunt, row, db=db, worktree=worktree, agent=agent,
                                              session=session, spend=spend)
        written.append({"hr_id": hr_id,
                        "ref": row.get("ref") or "",
                        "ref_scheme": row.get("ref_scheme") or "",
                        "claimed_title": row.get("claimed_title") or "",
                        "claimed_year": "" if row.get("claimed_year") is None
                                        else row["claimed_year"],
                        "fields_missing": ";".join(acc.missing_fields(row)),
                        "hunt_ok": "true" if ok else "false",
                        "hunt_state_or_refusal": state,
                        "message": message,
                        "seconds": secs})
        n_new += 1
        _write(out, written, acc.RUN_CSV_COLUMNS)      # after EVERY hunt: the ledger is the resume
    if not written:
        _write(out, written, acc.RUN_CSV_COLUMNS)      # the header alone, so the file always exists
    return n_new, len(done), written


def _write(path, rows, columns):
    """Whole-file rewrite through a temp file, so an interrupted write cannot leave a half row in
    the ledger the next run resumes from."""
    tmp = Path(str(path) + ".partial")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in columns})
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="resolve every scout drop-off through hunt, one CSV "
                                             "row each (no spend)")
    ap.add_argument("--manifest", required=True, help="the manifest frozen before the scout run")
    # DEFAULTS TO THE MANIFEST'S OWN `run_csv`, and that is the point. The freeze names the CSV
    # after the FREEZE DATE, and the acceptance checker reads the manifest's path. A recipe that
    # spelled the date out here would put the rows in one file and look for them in another the
    # first time a run crossed midnight — every drop-off scoring `missing_hunt_results`, a false
    # red produced by the recipe rather than by the run. Passing --out still works, for a replay
    # into a scratch file; the acceptance command then needs --csv to match.
    ap.add_argument("--out", default=None,
                    help="the run CSV (default: the manifest's own run_csv, which is what the "
                         "acceptance command reads)")
    ap.add_argument("--agent", default="scout-driver")
    ap.add_argument("--session", default=None)
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after this many NEW hunts (a bounded first pass)")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    out = a.out or manifest["run_csv"]
    n_new, n_skipped, rows = run(manifest, out, agent=a.agent, session=a.session, limit=a.limit)
    states = {}
    for r in rows:
        states[r["hunt_state_or_refusal"]] = states.get(r["hunt_state_or_refusal"], 0) + 1
    print(f"hunted={n_new} resumed={n_skipped} rows={len(rows)} out={out}")
    print(" ".join(f"{k}={v}" for k, v in sorted(states.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
