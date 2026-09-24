"""litkb acquisition probe: the bad-file read (LITKB_WORKPLAN.md "### S4.5" item 8, "the measurement that comes
FIRST"). READ-ONLY: connects as litkb_reader, reads kept bytes under the literature root, makes NO network
request, and writes ONE file — phase4/qc/litkb_acq_probe_badfile.csv.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acq_probe_badfile.py [--db litkb] [--root D:\\...]

Every `bad-file` acquisition attempt is typed into ONE sub-status of the S4.5 `bad-file` vocabulary
(`litkb.acquire.accept.SUB_STATUSES`), with the evidence it rests on in `basis`:
  bytes     this attempt's own kept bytes, typed by THE acceptance test (`litkb.acquire.accept.accept`) — one
            classifier: this instrument never re-implements a byte rule
  detail    the attempt's own `detail` records what the body was (Sci-Hub's `no-pdf-link(<n>B)` token is a page
            with no PDF link on it)
  inferred  neither: the codes and hosts in `detail`, or a later attempt's kept bytes on the same work, route
            and hosts (the per-key `.download` name was reused, so the later attempt overwrote the earlier one's)
and the CAUSE, which is what a fix needs and what the ledger's word cannot say (see CAUSES). This CSV is
builder-C1a's backfill input for `acquisition_attempts.sub_status`: its `sub_status` column holds vocabulary
values only, so the gated `bad_file_untyped` can reach 0 on history.

HOW THE KEPT BYTES ARE FOUND (the survey prototype's order, D:\\tools\\claude-config\\jobs\\litkb-s4-5\\scratch\\
survey-data\\badfile_retype.py; its fourth, looser key+mtime match is dropped — it matched a BROWSER route's later
PDF and an extraction .txt in the survey's first cut, and in the final cut it matched nothing):
  1. sha256       detail.sha256 equals a file's sha256 under _quarantine/ or _litkb_staging/ that no
                  litkb.files row holds (bound bytes are never refused bytes)
  2. qp.attempt   a litkb.quarantine_payloads row names this attempt_id
  3. was+mtime    a staging-orphan sidecar whose `was` is _litkb_staging/incoming/<key>.download and whose
                  recorded mtime is within MTIME_WINDOW_S of the attempt's `at`
  4. sibling      no bytes of its own: typed from a LATER attempt on the same work, route and `tried` hosts

THE FIRST TRACKED NUMBER it prints: rows whose cause a FREE rung fixes, split by grade (measured from the bytes,
estimated where the fix's own access is untested, inferred where no bytes were kept) — with `html_is_the_work`
counted on its own line and REPORTED, never in that number (S4.5 decision D12: S4.5 builds no HTML-document
landing, so no rung of this session converts those rows).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "phase4" / "qc" / "litkb_acq_probe_badfile.csv"
DSN = "host=localhost port=5433 dbname={db} user=litkb_reader"
SCAN_DIRS = ("_quarantine", "_litkb_staging")
#: The survey prototype's window (survey-data §3: chosen from the observed 5-35 s gaps between an attempt's
#: `at` and its .download's mtime on the 2026-09-15 open_access rows; uncalibrated beyond them).
MTIME_WINDOW_S = 120

COLUMNS = ["attempt_id", "work_key", "route", "identifier", "year", "at", "workstream", "http_codes", "tried",
           "detail_excerpt", "bytes_recorded", "sha256_recorded", "bytes_kept", "bytes_kept_path",
           "bytes_kept_length", "match_method", "sub_status", "basis", "cause", "free_to_fix", "fix_grade", "fix",
           "reason", "landing_pdf_pointer", "work_has_file_now"]

#: The closed cause list (docs/SCHEMAS.md, "phase4/qc/litkb_acq_probe_badfile.csv"). `misbooked` causes are
#: rows whose ledger status is wrong — a vocabulary fix, which lands no file.
CAUSES = {
    "landing_page": "an HTML landing page of a work with a PDF edition: Stage C (citation_pdf_url, the per-publisher rules)",
    "html_is_the_work": "the served HTML IS the work (no PDF edition exists): kind=html-doc, not built in S4.5 (D12)",
    "html_no_pointer": "an HTML page carrying no PDF pointer and not the work itself",
    "challenge_interstitial": "misbooked: HTTP 202 with no PDF is a WAF interstitial's shape -> blocked/challenge_or_bot_check",
    "blocked_not_bad_file": "misbooked: no host answered 200 (403 + transport 0) -> blocked",
    "transport_error_string": "misbooked: the 'payload' is the client's own transport-error text, never served bytes -> a retriable transport failure",
    "mirror_miss_page": "misbooked: a shadow mirror's page with no PDF link -> not-in-archive/not_in_corpus",
    "mirror_sweep_no_pdf": "every archive host answered 404, 0 or a non-PDF page; no bytes kept",
    "other": "typed by the acceptance test; no finer cause read",
}
MISBOOKED = {"challenge_interstitial", "blocked_not_bad_file", "transport_error_string", "mirror_miss_page"}


def require_reader(conn):
    """The connection, if it is litkb_reader's; SystemExit otherwise (this instrument writes nothing, and a
    login that COULD write is refused before the first query)."""
    # BEGIN guard: the bad-file read connects as the reader and nothing else
    if conn.execute("SELECT current_user").fetchone()[0] != "litkb_reader":
        raise SystemExit("litkb_acq_probe_badfile reads as litkb_reader only")
    # END guard: the bad-file read connects as the reader and nothing else
    return conn


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def scan_corpus(root, want_sizes):
    """Every file under the scanned folders; sha256 only for the sizes some attempt recorded (the others
    cannot match a recorded sha, and the filed folder holds 100 MB PDFs)."""
    files = []
    for d in SCAN_DIRS:
        for base, _, names in os.walk(root / d):
            for n in names:
                p = Path(base) / n
                st = p.stat()
                f = {"rel": p.relative_to(root).as_posix(), "path": p, "size": st.st_size,
                     "mtime": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc)}
                if st.st_size in want_sizes and not n.endswith(".json"):
                    f["sha"] = sha256_file(p)
                files.append(f)
    return files


def orphan_sidecars(files):
    out = []
    by_rel = {f["rel"]: f for f in files}
    for f in files:
        if not (f["rel"].endswith(".reason.json") and "__staging-orphan__" in f["rel"]):
            continue
        try:
            j = json.loads(Path(f["path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stem = f["rel"][: -len(".reason.json")]
        cands = [g for r, g in by_rel.items() if r.startswith(stem) and not r.endswith(".json")]
        if cands and j.get("was") and j.get("mtime"):
            out.append({"was": j["was"], "mtime": dt.datetime.fromisoformat(j["mtime"]), "file": cands[0]})
    return out


def _desc(data):
    """Body markers the cause rules read (never written to the CSV beyond these words)."""
    low = data[:400000].decode("utf-8", "replace").lower()
    return {k for k in ("linkinghub.elsevier.com", "articleselectsingleperm", "crossref.org", "dlib.org",
                        "getaddrinfo failed", "urlerror") if k in low}


def type_kept(data):
    """(sub_status, cause, free_to_fix, grade, fix, reason, pointer) from this attempt's own kept bytes."""
    from litkb.acquire import accept as A

    v = A.accept(data)
    marks = _desc(data)
    ptr = (v.facts.get("landing") or {}).get("pdf_pointer", False)
    if v.verdict == "accept":
        return "", "other", "n", "", "", "the acceptance test ACCEPTS these bytes: the booking was wrong", ptr
    st = v.sub_status
    if st == "html_response":
        if ptr:
            return st, "landing_page", "y", "measured", "Stage C: citation_pdf_url / link rel=alternate", v.reason, ptr
        if {"linkinghub.elsevier.com", "articleselectsingleperm"} & marks:
            return (st, "landing_page", "y", "estimated",
                    "Stage C Elsevier rule: linkinghub PII -> /pdfft (survey §2; ESTIMATED: /pdfft may sit behind a "
                    "challenge)", "an Elsevier linkinghub 'Redirecting' page carrying the PII, no PDF link", ptr)
        if {"crossref.org", "dlib.org"} & marks:
            # survey-data §3 read these pages: Crossref's blog posts and a D-Lib article ARE the works.
            return (st, "html_is_the_work", "n", "", "kind=html-doc capture (not built in S4.5; decision D12)",
                    "the served HTML is the work itself", ptr)
        return st, "html_no_pointer", "n", "", "", v.reason, ptr
    if st == "too_small" and {"getaddrinfo failed", "urlerror"} & marks:
        return (st, "transport_error_string", "n", "", "book it a transport failure (retriable), not a download",
                "the bytes are a Python URLError message the client wrote; no host served them", ptr)
    return st, "other", "n", "", "", v.reason, ptr


def type_detail(route, codes, tried, identifier, year):
    """(sub_status, basis, cause, free_to_fix, grade, fix, reason) when no bytes of this attempt were kept."""
    t = " ".join(tried)
    codes = codes or []
    if route == "scihub" and "no-pdf-link" in t:
        return ("html_response", "detail", "mirror_miss_page", "n", "",
                "not-in-archive/not_in_corpus" + ("; the freeze gate refuses it before any request (post-2021)"
                                                  if (year or 0) > 2021 else ""),
                "the mirror answered a page with no PDF link (the tried token records it)")
    if codes and all(c == 202 for c in codes):
        return ("html_response", "inferred", "challenge_interstitial", "n", "", "blocked/challenge_or_bot_check",
                "HTTP 202 and no %PDF-: a WAF interstitial's shape (C7; bytes not kept)")
    if route == "annas":
        return ("html_response", "inferred", "mirror_sweep_no_pdf", "n", "", "",
                "the archive sweep's hosts answered 404, 0 or a 200 non-PDF page; no bytes were kept")
    if codes and all(c in (403, 0) for c in codes):
        return ("html_response", "inferred", "blocked_not_bad_file", "n", "", "blocked (identity or challenge)",
                "403 and a transport failure; no host answered 200")
    if 200 in codes:
        return ("html_response", "inferred", "landing_page", "y", "inferred",
                "Stage C on the landing page (INFERRED: the page was not kept)",
                "a host answered 200 with no %PDF-: the shape of a landing page (bytes not kept)")
    return ("html_response", "inferred", "other", "n", "", "", "no rule fits; typed by the route's own words")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default="litkb", help="the database read as litkb_reader (default: %(default)s)")
    from litkb.acquire.store import LITERATURE_ROOT     # the store's one home for the root (auditor-C1b r2 F10)

    ap.add_argument("--root", default=str(LITERATURE_ROOT), help="the literature root (default: %(default)s)")
    ap.add_argument("--out", default=str(OUT), help="the CSV written (default: %(default)s)")
    a = ap.parse_args(argv)
    import psycopg

    root = Path(a.root)
    c = require_reader(psycopg.connect(DSN.format(db=a.db)))
    rows = c.execute(
        """SELECT a.id::text, a.route, a.identifier_used, w.key, wv.year, a.at, a.http_codes, a.detail, ws.slug
             FROM litkb.acquisition_attempts a
             LEFT JOIN litkb.works w ON w.id = a.work_id
             LEFT JOIN litkb.work_versions wv ON wv.version_id = w.current_version_id
             LEFT JOIN litkb.workstreams ws ON ws.id = a.workstream_id
            WHERE a.status = 'bad-file' ORDER BY a.route, w.key, a.at, a.id""").fetchall()
    qp = dict(c.execute("SELECT attempt_id::text, rel_path FROM litkb.quarantine_payloads "
                        "WHERE attempt_id IS NOT NULL").fetchall()) if c.execute(
        "SELECT to_regclass('litkb.quarantine_payloads') IS NOT NULL").fetchone()[0] else {}
    bound = {r[0] for r in c.execute("SELECT sha256 FROM litkb.files").fetchall()}
    has_file = {r[0] for r in c.execute("SELECT DISTINCT w.key FROM litkb.main_files f JOIN litkb.main_works w "
                                        "ON w.work_id = f.work_id WHERE f.status = 'active'").fetchall()}
    want = {int((r[7] or {}).get("bytes")) for r in rows if str((r[7] or {}).get("bytes", "")).isdigit()}
    files = scan_corpus(root, want)
    by_sha = {}
    for f in files:
        if f.get("sha") and f["sha"] not in bound:
            by_sha.setdefault(f["sha"], []).append(f)
    by_rel = {f["rel"]: f for f in files}
    orphans = orphan_sidecars(files)

    typed = []
    for aid, route, ident, key, year, at, codes, det, slug in rows:
        det = det or {}
        tried = det.get("tried") or []
        kept, method = None, "none"
        sha = det.get("sha256")
        if sha and sha in by_sha:
            kept, method = by_sha[sha][0], "sha256" + ("+qp.attempt" if aid in qp else "")
        elif aid in qp and qp[aid] in by_rel:
            kept, method = by_rel[qp[aid]], "qp.attempt"
        if kept is None and key:
            want_was = f"_litkb_staging/incoming/{key}.download"
            for o in orphans:
                if o["was"] == want_was and abs((o["mtime"] - at).total_seconds()) <= MTIME_WINDOW_S:
                    kept, method = o["file"], "was+mtime"
                    break
        rec = {"attempt_id": aid, "work_key": key or "", "route": route, "identifier": ident or "", "year": year,
               "at": at.isoformat(), "workstream": slug or "", "http_codes": json.dumps(codes),
               "tried": " | ".join(tried)[:400],
               "detail_excerpt": "; ".join(str(det[k])[:160] for k in ("note", "via", "probe_error", "shape")
                                           if det.get(k))[:300],
               "bytes_recorded": det.get("bytes", ""), "sha256_recorded": sha or "",
               "bytes_kept": "y" if kept else "n", "bytes_kept_path": kept["rel"] if kept else "",
               "bytes_kept_length": kept["size"] if kept else "", "match_method": method,
               "work_has_file_now": "y" if key in has_file else "n", "_tried": tried, "_at": at}
        if kept:
            st, cause, free, grade, fix, why, ptr = type_kept(Path(kept["path"]).read_bytes())
            rec.update(sub_status=st, basis="bytes", cause=cause, free_to_fix=free, fix_grade=grade, fix=fix,
                       reason=why, landing_pdf_pointer="y" if ptr else "n")
        else:
            st, basis, cause, free, grade, fix, why = type_detail(route, codes, tried, ident or "", year)
            rec.update(sub_status=st, basis=basis, cause=cause, free_to_fix=free, fix_grade=grade, fix=fix,
                       reason=why, landing_pdf_pointer="")
        typed.append(rec)
    # the sibling pass: an attempt with no bytes of its own takes the typing of a LATER attempt on the same work,
    # route and `tried` hosts that kept some
    for r in typed:
        if r["bytes_kept"] == "y":
            continue
        for q in typed:
            if (q["bytes_kept"] == "y" and q["work_key"] == r["work_key"] and q["route"] == r["route"]
                    and q["_tried"] == r["_tried"] and q["_at"] > r["_at"]):
                r.update(sub_status=q["sub_status"], basis="inferred", cause=q["cause"], free_to_fix=q["free_to_fix"],
                         fix_grade="inferred" if q["free_to_fix"] == "y" else "", fix=q["fix"],
                         reason=f"typed from the later attempt {q['attempt_id']}'s kept bytes (same work, route and "
                                f"hosts): {q['reason']}", match_method=f"sibling:{q['attempt_id']}")
                break

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(typed)
    free = [r for r in typed if r["free_to_fix"] == "y"]
    grades = Counter(r["fix_grade"] for r in free)
    html_work = [r for r in typed if r["cause"] == "html_is_the_work"]
    print(f"bad_file_rows={len(typed)} -> {out}")
    print("sub_status", dict(Counter(r["sub_status"] for r in typed)))
    print("basis", dict(Counter(r["basis"] for r in typed)))
    print("cause", dict(Counter(r["cause"] for r in typed)))
    print("misbooked_rows", sum(1 for r in typed if r["cause"] in MISBOOKED))
    print(f"FREE_TO_FIX rows={len(free)} (measured {grades.get('measured', 0)}, estimated "
          f"{grades.get('estimated', 0)}, inferred {grades.get('inferred', 0)}) "
          f"works={len({r['work_key'] for r in free})} "
          f"works_without_file={len({r['work_key'] for r in free if r['work_has_file_now'] == 'n'})}")
    print(f"html_is_the_work rows={len(html_work)} works={len({r['work_key'] for r in html_work})} "
          f"(REPORTED, decision D12; not in FREE_TO_FIX)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
