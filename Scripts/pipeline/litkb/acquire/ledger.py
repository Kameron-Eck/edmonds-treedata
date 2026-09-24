"""The acquisition ledger's typing, its rejected-hash lookup, word counts and the reviewed backfills
(LITKB_WORKPLAN.md "### S4.5" items 1 and 2; migration 0033). A RELAYED design (CLAUDE.md §3.4c),
UNVALIDATED until an independent referee scores it on the rows the plan names.

  sub_status_for()     the LIVE typing: what the ladder writes into `sub_status` for every attempt
  type_blocked()       the `blocked` classifier — ported from builder-survey-data's hand typing of the
                       14 open-access and 25 Sci-Hub `blocked` rows (jobs/litkb-s4-5/survey-data.md
                       §2.5-2.6): challenge markers in the kept bytes, then the HTTP codes
  bad_file_verdict()   the `bad-file` typing: builder C1b's acceptance test (acquire/accept.py) is THE
                       byte classifier, and this is its one call for typing (S4.5 CONTRACTS: "C1b's
                       acceptance test RETURNS one of the bad-file sub-statuses; C1a's ledger STORES it")
  rejected_match()     the rejected-hash lookup: the served sha against every uncleared
                       `quarantine_payloads` row and every rejected/withdrawn file version — by
                       CONTENT hash, never by path (S4's defect)
  held_file()          does the corpus hold these bytes (an active current version), for THIS work's
                       purposes? A downloaded match that is held is a hit, never known-bad
                       (run._record_result) — unless the bytes were refused for this very work
  no_byte_bad_file_sub()  a `bad-file` that kept no byte, typed from its terminal response (S4.5
                       decision D15; run._type_attempt)
  word_count_of*()     `file_versions.word_count` from a version's text extract
  backfill_*()         the reviewed backfills (ingest role, dry run by default, one decision-log row
                       per applied run in `litkb.acquisition_backfills`)

    py -3.12 -m litkb.acquire.ledger type-blocked --out ../phase4/qc/litkb_acq_probe_blocked.csv   (from Scripts/)
    py -3.12 -m litkb.acquire.ledger backfill-sub-status --csv <file> [--apply] --session <label>
    py -3.12 -m litkb.acquire.ledger backfill-word-count [--apply] --session <label>
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

from litkb import netutil as _netutil
from litkb.acquire import policy as P

# ── the blocked classifier ──────────────────────────────────────────────────────────────────
# The challenge signatures (the marker list, the header signatures, the 64 KiB window) have ONE home,
# `litkb.netutil` (S4.5 decision D24; integrator-w3 moved them there from here). These names stay for the
# readers that already import them from the ledger; they are the same objects, never a second list.
MARKER_WINDOW = _netutil.MARKER_WINDOW
CHALLENGE_MARKERS = _netutil.CHALLENGE_MARKERS
CHALLENGE_HEADERS = _netutil.CHALLENGE_HEADERS


def challenge_cause(body, headers=None):
    """-> the challenge family whose signature these KEPT bytes (or headers) carry, or ''. The one detector,
    `netutil.Client.challenge_cause`, asked with the status unknown (None): a row being typed carries its codes,
    not the status of the answer whose bytes were kept, so every marker in the window is read (D24)."""
    return _netutil.Client.challenge_cause(None, None, body, headers)


def _ints(codes):
    return [int(c) for c in (codes or []) if str(c).lstrip("-").isdigit()]


def type_blocked(codes, body=None, headers=None, tried=None, route=None):
    """-> (sub_status, basis, cause) for a `blocked` attempt. Order, strongest evidence first:

      1. the served bytes (or headers) carry a challenge signature        -> challenge_or_bot_check (bytes)
      1b. the ROUTE's own rule: `open_access` books `blocked` ONLY when `Client.is_challenge` fired on one of
         its locations (acquire/open_access.py::fetch_open_access, unchanged since 5189749, 2026-09-14) —
         and the bytes it kept are the FIRST body served, which need not be the challenging one
                                                                         -> challenge_or_bot_check (detail; with
         no bytes kept, `inferred`: S4.5 decision D30)
      2. the terminal code is 401                                          -> identity_required
         (guard 2: "a subscription answer about one article")
      3. the terminal code is 404 / 410                                    -> not_found
      4. bytes were kept and they are an HTML page with no signature:
           at 403                                                          -> identity_required (bytes)
           else                                                            -> html_or_reader (bytes)
      5. no bytes: a route's own `...=blocked` tried token (Sci-Hub marks blocked only on a challenge,
         a captcha page or a 403 — acquire/scihub.py::fetch_scihub)       -> challenge_or_bot_check (inferred:
         S4.5 decision D30 — the token is the route's own word, written for a challenge, a captcha OR a bare 403
         alike, with no body marker and no kept bytes behind it; a row with either keeps that evidence's basis)
      6. no bytes, codes only: any 200 among them (a landing page answered and served no file)
                                                                           -> html_or_reader (inferred)
         a 403                                                             -> challenge_or_bot_check (inferred;
           survey-data §2.5 MEASURED 12 of 12 kept 403 bodies on this ledger as challenge pages)
      7. nothing to go on                                                  -> (None, None, 'untypable')
    """
    codes = _ints(codes)
    cause = challenge_cause(body, headers)
    if cause:
        return "challenge_or_bot_check", "bytes", cause
    # S4.5 decision D30 (the orchestrator's ruling on auditor-cand2 N3): a row typed from the ROUTE's own word alone
    # (no body marker, no kept bytes) carries basis `inferred`, never `detail`; a row with kept bytes keeps the
    # evidence's basis (rule 1b over the kept first body stays `detail`)
    token_only = "detail"
    # BEGIN guard: a blocked row typed from the route's own word alone is inferred, never detail
    token_only = "inferred"
    # END guard: a blocked row typed from the route's own word alone is inferred, never detail
    if route == "open_access":
        return ("challenge_or_bot_check", "detail" if body else token_only,
                "open_access books blocked only when Client.is_challenge fired")
    last = codes[-1] if codes else None
    if last == 401:
        return "identity_required", ("bytes" if body else "detail"), "401"
    if last in (404, 410):
        return "not_found", ("bytes" if body else "detail"), str(last)
    if body:
        if last == 403:
            return "identity_required", "bytes", "403 page with no challenge signature"
        return "html_or_reader", "bytes", "page with no challenge signature and no file"
    if any(str(t).endswith("=blocked") for t in (tried or [])):
        return "challenge_or_bot_check", token_only, "route token =blocked"
    if 200 in codes:
        return "html_or_reader", "inferred", "a 200 answered and served no file (bytes not kept)"
    if 403 in codes:
        return "challenge_or_bot_check", "inferred", "403 with no bytes kept (12/12 kept 403 bodies were challenges)"
    return None, None, "untypable"


def bad_file_verdict(data, *, headers=None, url=None, terminal_url=None, status=None):
    """THE acceptance test's verdict (`litkb.acquire.accept.accept`, builder C1b) on the bytes a `bad-file`
    row carries: the ONE byte classifier, so a row's sub-status is the gate's own word (S4.5 CONTRACTS:
    "C1b's acceptance test RETURNS one of the bad-file sub-statuses; C1a's ledger STORES it"; seam
    integrator-w1 — this replaced the interim three-answer mapping that stood in for it on C1a's branch).
    -> the Verdict, or None when nothing was served (no byte-level sub-status describes an empty answer).

    The record-reading steps ABSTAIN (`metadata_fetched=False`, guard 18): typing a row the ladder has
    already refused never rests on the record. Bytes the test ACCEPTS carry no sub-status (a PDF the bind's
    page probe could not read: `run.land_and_attach`'s probe-error refusal) — the vocabulary has no word for
    that refusal, so such a row stays untyped and `bad_file_untyped` counts it (integrator-w1, open question).
    `status` is the terminal answer's HTTP status when the caller holds it (the live ladder does; a backfill of a
    historical row does not), for the one challenge detector's window rule (S4.5 decision D24)."""
    from litkb.acquire import accept as A

    if not data:
        return None
    return A.accept(data, headers=headers, url=url, terminal_url=terminal_url, metadata_fetched=False,
                    status=status)


def bad_file_sub(data, headers=None, url=None, terminal_url=None):
    """-> the `bad-file` sub-status THE acceptance test gives these bytes, or None (see bad_file_verdict)."""
    v = bad_file_verdict(data, headers=headers, url=url, terminal_url=terminal_url)
    return v.sub_status if v is not None and v.verdict == "refuse" else None


def not_in_archive_sub(route):
    """-> the `not-in-archive` sub-status a route's miss means. Anna's `not-in-archive` is the archive
    holding no record for the DOI (acquire/annas.py gate 1): not in its corpus. Sci-Hub's is every
    mirror page answering without a PDF link (acquire/scihub.py::fetch_scihub): no PDF link."""
    return {"annas": "not_in_corpus", "scihub": "no_pdf_link"}.get(route)


def sub_status_for(status, route, codes, body=None, headers=None, tried=None):
    """The LIVE typing: -> (sub_status or None, cause). Only the statuses 0033 sub-types are typed."""
    if status == "blocked":
        sub, _basis, cause = type_blocked(codes, body, headers, tried, route)
        return sub, cause
    if status == "bad-file":
        return bad_file_sub(body, headers), ""
    if status == "not-in-archive":
        return not_in_archive_sub(route), ""
    return None, ""


# ── the rejected-hash lookup (item 1) ───────────────────────────────────────────────────────
_REJECTED_SQL = """
SELECT 'quarantine_payloads' AS source, q.id::text, q.rel_path, q.reason, q.recorded_at
  FROM litkb.quarantine_payloads q WHERE q.sha256 = %(sha)s AND q.cleared_at IS NULL
UNION ALL
SELECT 'file_versions', fv.version_id::text, fv.rel_path, fv.state, fv.created_at
  FROM litkb.files f JOIN litkb.file_versions fv ON fv.file_id = f.id
 WHERE f.sha256 = %(sha)s AND fv.state IN ('rejected', 'withdrawn')
 ORDER BY 5, 2 LIMIT 1
"""


def rejected_match(conn, sha256):
    """-> {"source", "id", "rel_path", "reason", "recorded_at"} of the earliest refused-bytes record whose
    CONTENT hash is `sha256`, or None. The refused-bytes record is every uncleared quarantine row
    (migration 0030) plus every rejected or withdrawn file version (plan item 1). Matching is by
    sha256, never by path: E13's three 58-byte payloads sit at three paths under one sha."""
    if not sha256:
        return None
    row = conn.execute(_REJECTED_SQL, {"sha": sha256}).fetchone()
    if not row:
        return None
    return {"source": row[0], "id": row[1], "rel_path": row[2], "reason": row[3], "recorded_at": str(row[4])}


#: held_file's question. The held half is `main_files`' join (an active current version, neither rejected nor
#: withdrawn); the refused-for-this-work half is _REJECTED_SQL's two halves restricted to the work (aliased
#: apart from it, so each of that query's mutation rows still names one occurrence).
_HELD_SQL = """
SELECT EXISTS (
  SELECT 1 FROM litkb.files f JOIN litkb.file_versions cv ON cv.version_id = f.current_version_id
   WHERE f.sha256 = %(sha)s AND cv.status = 'active' AND cv.state NOT IN ('rejected', 'withdrawn')
     AND (cv.work_id = %(wid)s
          OR (NOT EXISTS (SELECT 1 FROM litkb.quarantine_payloads p
                           WHERE p.sha256 = %(sha)s AND p.cleared_at IS NULL AND p.work_id = %(wid)s)
              AND NOT EXISTS (SELECT 1 FROM litkb.file_versions v
                               WHERE v.file_id = f.id AND v.work_id = %(wid)s
                                 AND v.state IN ('rejected', 'withdrawn')))))
"""


def held_file(conn, sha256, work_id):
    """Does the corpus HOLD these bytes, for work `work_id`'s purposes? A `files` row with this sha256 whose
    CURRENT version is `active` and neither `rejected` nor `withdrawn` (`main_files` is that join), and which is
    either THIS work's file or one no refused-bytes record names for this work.

    A refused payload that was bound later is held — and, being a moved payload, is never cleared (0030) — so a
    DOWNLOADED match is a hit, not known-bad (run._record_result; auditor-C1a F3: five such payloads on live, each
    the active file of its own work). But bytes refused FOR this work (a `content-mismatch` or `hash-mismatch`
    against its record, a version of it rejected or withdrawn) are not this work's paper, whoever else holds them:
    they stay known-bad for it (fix round 3, auditor-C1a r2 F3). Bytes another work holds that nothing refused for
    this work stay a hit — the dedupe answers `duplicate-held` in acquire mode (auditor-C1a F3)."""
    if not sha256:
        return False
    return conn.execute(_HELD_SQL, {"sha": sha256, "wid": work_id}).fetchone()[0]


# ── the no-byte bad-file typing (S4.5 decision D15) ──────────────────────────────────────────
def _header(headers, name):
    """One response header, by case-insensitive name, as text; None when absent."""
    return next((str(v) for k, v in (headers or {}).items() if str(k).lower() == name), None)


def no_byte_bad_file_sub(headers):
    """-> (sub_status or None, cause) for a `bad-file` attempt that KEPT NO BYTE, read from its terminal response's
    headers (S4.5 decision D15: "With no bytes kept, the route types from the terminal response (content-type html
    → `html_response`; length under the floor → `too_small`; basis `live`)"; the basis is `live` because 0033's
    writer forces it on every live row). run._type_attempt calls it for every rung:

      a Content-Type naming html                                                -> html_response
      the response's length is 0 — a declared Content-Length of 0, or none declared (no byte was handed back,
        so 0 is the length the ladder knows) — under every byte floor           -> too_small
      a declared Content-Length above 0 but under the acceptance test's byte floor (`accept.MIN_PDF_BYTES`, its
        one home; seam integrator-w2 — builder C1a's branch did not hold it)   -> too_small
      a declared Content-Length at or above the floor, and no byte handed back  -> None: untyped, counted

    The last is the one answer the rules cannot type: a server declared a PDF's worth of bytes the rung never
    handed back — which a rung may not do (run.py: "bytes a route refused are quarantined, never discarded") — so the
    row stays untyped and the gated `bad_file_untyped` names the rung, fail closed."""
    from litkb.acquire import accept as _accept

    ctype = _header(headers, "content-type") or ""
    if "html" in ctype.lower():
        return "html_response", f"no byte kept; the terminal response's Content-Type is {ctype[:80]!r} (D15)"
    declared = (_header(headers, "content-length") or "").strip()
    n = int(declared) if declared.isdigit() else 0
    if n == 0:
        return "too_small", ("no byte kept; the terminal response carried 0 bytes, under every byte floor (D15)"
                             + ("" if declared else "; it declared no Content-Length"))
    # BEGIN guard: a declared length under the byte floor is too_small
    if n < _accept.MIN_PDF_BYTES:
        return "too_small", (f"no byte kept; the terminal response declared {n} bytes, under the acceptance test's "
                             f"{_accept.MIN_PDF_BYTES}-byte floor (D15)")
    # END guard: a declared length under the byte floor is too_small
    return None, f"no byte kept, yet the terminal response declared {n} bytes: no rung handed them back"


# ── word counts (item 2) ────────────────────────────────────────────────────────────────────
def word_count_of(text):
    """Whitespace-separated tokens (the same count `wc -w` makes). The stub heuristics downstream are
    predicates over page_count and word_count (survey §3.4); sandcrawler records both on every success."""
    return len((text or "").split())


def word_count_of_file(path):
    """-> the word count of a text extract on disk, or None when it cannot be read."""
    try:
        return word_count_of(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


# ── the reviewed backfills ──────────────────────────────────────────────────────────────────
#: The CSV the sub-status backfill applies (S4.5 CONTRACTS / brief C1a item 4: builder C1b's item-8
#: CSV has exactly these columns; `type-blocked` below emits the same shape).
TYPING_COLUMNS = ("attempt_id", "sub_status", "basis", "free_to_fix", "cause")


#: The `cause` a typing CSV gives a row whose ledger STATUS is wrong (S4.5 decision D29): it carries no sub-status,
#: is never offered, and is a NAMED exception of `bad_file_untyped` (qc/instruments/litkb_hardening_c1a.py) — typing
#: it inside the wrong family would be a word the fill-null backfill can never correct.
MISBOOKED_CAUSE = "misbooked"


def read_typing_csv(path):
    """-> (rows to offer, refused lines). A row needs an attempt id, a sub-status and a basis; a row
    whose sub-status is empty is the classifier saying "untypable" and is NOT offered (the counter keeps
    counting it, which is the point); a row whose cause is MISBOOKED_CAUSE is refused by NAME (S4.5 decision
    D29), whatever its other columns say."""
    rows, refused = [], []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for i, r in enumerate(csv.DictReader(fh), start=2):
            aid, sub, basis = (r.get("attempt_id") or "").strip(), (r.get("sub_status") or "").strip(), \
                (r.get("basis") or "").strip()
            if not aid:
                refused.append({"line": i, "why": "no attempt_id"})
            elif (r.get("cause") or "").strip() == MISBOOKED_CAUSE:
                refused.append({"line": i, "why": "misbooked (S4.5 decision D29): never typed; a named exception of "
                                                  "bad_file_untyped", "attempt_id": aid})
            elif not sub:
                refused.append({"line": i, "why": "no sub_status (untypable)", "attempt_id": aid})
            else:
                rows.append({"attempt_id": aid, "sub_status": sub, "basis": basis})
    return rows, refused


def _sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def backfill_sub_status(reader, csv_path, *, session, apply=False, recorder=None):
    """Offer a typing CSV to `litkb.backfill_attempt_sub_status`. The DRY RUN (default) reads on the
    reader connection and reports what WOULD be applied; `apply` calls the function on `recorder` (the
    ingest connection) once, which writes every row and one `acquisition_backfills` row atomically."""
    rows, refused = read_typing_csv(csv_path)
    ids = [r["attempt_id"] for r in rows]
    have = {}
    if ids:
        for aid, status, sub in reader.execute(
                "SELECT id::text, status, sub_status FROM litkb.acquisition_attempts WHERE id::text = ANY(%s)",
                (ids,)).fetchall():
            have[aid] = (status, sub)
    plan = {"would_apply": 0, "missing": 0, "already_typed": 0, "wrong_family": 0, "bad_basis": 0}
    for r in rows:
        st = have.get(r["attempt_id"])
        if r["basis"] not in ("bytes", "detail", "inferred"):
            plan["bad_basis"] += 1
        elif st is None:
            plan["missing"] += 1
        elif st[1] is not None:
            plan["already_typed"] += 1
        elif r["sub_status"] not in P.SUB_STATUSES.get(st[0], ()) or st[0] not in (
                "bad-file", "blocked", "not-in-archive"):
            plan["wrong_family"] += 1
        else:
            plan["would_apply"] += 1
    source = f"{Path(csv_path).as_posix()} sha256={_sha256_of(csv_path)}"
    out = {"mode": "apply" if apply else "dry-run", "source": source, "offered": len(rows),
           "refused_lines": refused, "plan": plan}
    if apply:
        from psycopg.types.json import Jsonb
        out["applied"] = recorder.execute("SELECT litkb.backfill_attempt_sub_status(%s, %s, %s)",
                                          (session, source, Jsonb(rows))).fetchone()[0]
    return out


def word_count_rows(reader, root):
    """Every file version with no word count whose text extract can be read under `root`.
    -> (rows [{version_id, word_count}], unreadable [rel paths])."""
    rows, unreadable = [], []
    for vid, txt in reader.execute(
            "SELECT version_id::text, txt_extract_path FROM litkb.file_versions "
            "WHERE word_count IS NULL AND txt_extract_path IS NOT NULL ORDER BY created_at, version_id").fetchall():
        n = word_count_of_file(Path(root) / txt)
        if n is None:
            unreadable.append(txt)
        else:
            rows.append({"version_id": vid, "word_count": n})
    return rows, unreadable


def backfill_word_count(reader, root, *, session, apply=False, recorder=None):
    rows, unreadable = word_count_rows(reader, root)
    source = f"text extracts under {Path(root).as_posix()}"
    out = {"mode": "apply" if apply else "dry-run", "source": source, "offered": len(rows),
           "unreadable": unreadable}
    if apply:
        from psycopg.types.json import Jsonb
        out["applied"] = recorder.execute("SELECT litkb.backfill_file_word_count(%s, %s, %s)",
                                          (session, source, Jsonb(rows))).fetchone()[0]
    return out


# ── the historical blocked typing (brief C1a item 4: "YOU write the typing") ────────────────
_BLOCKED_SQL = """
SELECT a.id::text, a.route, coalesce(a.http_codes, '{{}}'), a.detail, a.at,
       (SELECT q.rel_path FROM litkb.quarantine_payloads q WHERE q.attempt_id = a.id ORDER BY q.recorded_at LIMIT 1),
       (SELECT q.rel_path FROM litkb.quarantine_payloads q
         WHERE q.sha256 = a.detail->>'sha256' ORDER BY q.recorded_at LIMIT 1)
  FROM litkb.acquisition_attempts a
 WHERE a.status = 'blocked' {untyped}
 ORDER BY a.at, a.id
"""


def _has_sub_status(conn):
    """Has this database applied 0033? The census runs on a database that has not (the orchestrator types
    the history BEFORE migrating live, so the CSV is reviewed first); there every `blocked` row is untyped."""
    return conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = 'litkb' "
                        "AND table_name = 'acquisition_attempts' AND column_name = 'sub_status'").fetchone() is not None


def kept_bytes(root, *rels):
    """-> (bytes, rel) of the first readable kept payload among `rels` under `root`, else (None, '')."""
    for rel in rels:
        if not rel:
            continue
        p = Path(root) / rel
        try:
            return p.read_bytes(), rel
        except OSError:
            continue
    return None, ""


def blocked_typing_rows(reader, root):
    """Type every untyped `blocked` attempt from its kept bytes (the quarantine row linked to the
    attempt, else `detail.quarantined`, else the payload whose sha is `detail.sha256`), its route's
    tried tokens and its HTTP codes. -> rows in TYPING_COLUMNS order plus route/codes/kept for review."""
    out = []
    sql = _BLOCKED_SQL.format(untyped="AND a.sub_status IS NULL" if _has_sub_status(reader) else "")
    for aid, route, codes, detail, at, q_linked, q_sha in reader.execute(sql).fetchall():
        detail = detail or {}
        body, kept = kept_bytes(root, q_linked, detail.get("quarantined"), q_sha)
        sub, basis, cause = type_blocked(codes, body, None, detail.get("tried"), route)
        out.append({"attempt_id": aid, "sub_status": sub or "", "basis": basis or "", "free_to_fix": "",
                    "cause": cause, "route": route, "http_codes": " ".join(str(c) for c in codes),
                    "kept": kept, "kept_bytes": len(body) if body is not None else "", "at": str(at)})
    return out


def write_csv(rows, path, columns):
    with open(path, "x", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ── CLI ─────────────────────────────────────────────────────────────────────────────────────
def _connect_reader(db, role):
    from litkb.db import connect as c
    return c.connect(db or c.DB_MAIN, role)


def main(argv=None):
    from litkb import quarantine as Q

    ap = argparse.ArgumentParser(prog="python -m litkb.acquire.ledger", description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=None, help="database (default litkb)")
    ap.add_argument("--role", default="litkb_reader", help="the login the census and the dry run read on")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tb = sub.add_parser("type-blocked", help="type every untyped `blocked` attempt; write the CSV")
    tb.add_argument("--out", required=True)
    tb.add_argument("--root", default=None)
    bs = sub.add_parser("backfill-sub-status", help="apply a typing CSV (dry run unless --apply)")
    bs.add_argument("--csv", required=True)
    bs.add_argument("--apply", action="store_true")
    bs.add_argument("--session", required=True)
    bw = sub.add_parser("backfill-word-count", help="word counts for versions that have none (dry run unless --apply)")
    bw.add_argument("--root", default=None)
    bw.add_argument("--apply", action="store_true")
    bw.add_argument("--session", required=True)
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    from litkb.acquire.store import LITERATURE_ROOT
    root = getattr(args, "root", None) or os.environ.get("LITKB_LITERATURE_ROOT") or str(LITERATURE_ROOT)
    reader = _connect_reader(args.db, args.role)
    recorder = Q.ingest_connect(args.db) if getattr(args, "apply", False) else None
    try:
        if args.cmd == "type-blocked":
            rows = blocked_typing_rows(reader, root)
            write_csv(rows, args.out, TYPING_COLUMNS + ("route", "http_codes", "kept", "kept_bytes", "at"))
            by = {}
            for r in rows:
                by[r["sub_status"] or "(untypable)"] = by.get(r["sub_status"] or "(untypable)", 0) + 1
            out = {"rows": len(rows), "by_sub_status": by, "csv": args.out}
        elif args.cmd == "backfill-sub-status":
            out = backfill_sub_status(reader, args.csv, session=args.session, apply=args.apply, recorder=recorder)
        else:
            out = backfill_word_count(reader, root, session=args.session, apply=args.apply, recorder=recorder)
    finally:
        reader.close()
        if recorder is not None:
            recorder.close()
    sys.stdout.write(json.dumps(out, indent=1, default=str, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
