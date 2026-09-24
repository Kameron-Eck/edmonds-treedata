"""builder-C1b's counters and known-bads for `litkb_acceptance.py hardening` (LITKB_WORKPLAN.md "### S4.5" (b)/(c);
the S4.5 CONTRACTS module contract). Loaded BY PATH (qc/instruments is not a package).

    COUNTERS  gated:   quarantines_without_reason (ALL TIME), stubs_bound, volumes_bound_as_article (RUN-SCOPED)
    REPORTED           page_ranges_unparsed, stub_rule_abstained_image_pages, bound_files_unreadable (RUN-SCOPED)
    FIRES     sidecar, stub_constructed, stub_e20, volume, bom_repair,
              stub_ladder, stub_ladder_header_only (through `run.acquire`; integrator-w2, S4.5 decisions D21 D22)

A counter is `fn(conn, manifest) -> int` on a READ-ONLY connection. Manifest keys read: `frozen_at`,
`run_workstream_ids`, and `literature_root` — a key the CONTRACTS list does not name yet (builder-A adds it;
absent, the default literature root `litkb.acquire.store.LITERATURE_ROOT` is read, which is right for the live
run and wrong for nothing else).

HOW A BOUND FILE IS RE-CLASSIFIED (stubs_bound, volumes_bound_as_article). The counter does NOT trust the verdict
the gate recorded — in a known-bad arm that verdict is exactly what was switched off. It re-runs the detectors
itself (`litkb.acquire.accept.stub_signals` / `volume_check`) on:
  * the bound file's bytes on disk (its text and its image pages: the `chars_no_refs` signal, which abstains
    on a document holding an image page exactly as the gate does; its page count: the volume rule),
  * the EVIDENCE the landing attempt recorded (`detail->'acceptance'->'facts'->'evidence'`: the served headers
    and the terminal URL — the `x_els_status` and `preview_url` signals), falling back to the file version's
    `source_url` when the landing wrote no acceptance record (a bind that never went through `offer_to_bind`),
    joined to the attempt BY THE FILE'S sha256 (a work can have several `ok` attempts),
  * the landing attempt's OWN record, which the ladder writes independent of the acceptance test (S4.5 decision
    D22, integrator-w2): `detail->'served_headers'` (Content-Type, Content-Length, X-ELS-Status,
    Content-Disposition) and the row's `terminal_url`,
  * the work's record page range, read by the gate's own reader (`litkb.acquire.accept.record_pages_of`:
    the main record first, else the latest version) — one source for one fact (auditor-C1b F9).
A header-only stub bound by a path that recorded neither evidence nor served headers (a bind outside the ladder,
or a row written before D22) cannot be re-detected from its bytes: the counter then under-counts, and says
nothing — a stated limit, not a hidden one. A document holding ANY image page — a
scan, or a short text stub followed by one image-only page — is not re-detected by its text either (the gate's
own abstention, `litkb.acquire.accept` step 10, whose limit it states); `stub_rule_abstained_image_pages` REPORTS
how many run-bound files that abstention covered, so the limit is counted, not hidden. A bound file the counter
cannot read from disk (moved, unreadable) is still asked the EVIDENCE signals (`accept.evidence_signals`: the
recorded headers and URLs need no bytes) and is REPORTED as `bound_files_unreadable`: its text and page count
were not re-read (auditor-C1b round 2, F11).

A FIRE is `fn(conn, arm, workdir) -> int`: `arm` is "control" or "known_bad" on an already reset+migrated WORKER
database (the owner login); the known-bad switches ONE guard off IN THIS PROCESS and restores it before the
counter is read, so the counter always runs the real code. Nothing here touches the network or the live store:
every Store is rooted under `workdir`.
"""
import contextlib
import importlib.util
import json
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
NEG_DIR = SCRIPTS / "qc" / "testdata" / "litkb_acq_negatives"
E20_PDF = SCRIPTS / "qc" / "fixtures" / "litkb_e20_preview.pdf"
E20_PROV = SCRIPTS / "qc" / "fixtures" / "litkb_e20_preview.provenance.json"


def _negatives():
    spec = importlib.util.spec_from_file_location("litkb_acq_negatives", Path(__file__).with_name(
        "litkb_acq_negatives.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _root(manifest):
    from litkb.acquire.store import LITERATURE_ROOT

    return Path(manifest.get("literature_root") or LITERATURE_ROOT)


# ── the counters ──────────────────────────────────────────────────────────────────────────

def quarantines_without_reason(conn, manifest):
    """ALL TIME: payloads under the quarantine root with no `.reason.json` (litkb.quarantine.without_reason)."""
    from litkb import quarantine as Q

    return Q.without_reason(_root(manifest))[0]


#: `landed` is the landing attempt's OWN record, written by the ladder independent of the acceptance test (S4.5
#: decision D22, seam integrator-w2: `detail.served_headers` on every attempt that was served bytes, and the row's
#: `terminal_url`) — what a landing the test did not judge still leaves for this counter to re-read.
_BOUND_SQL = """
SELECT fv.file_id::text, fv.work_id::text, fv.rel_path, fv.pages, fv.source_url, f.sha256,
       (SELECT a.detail -> 'acceptance' -> 'facts' -> 'evidence' FROM litkb.acquisition_attempts a
         WHERE a.work_id = fv.work_id AND a.status = 'ok' AND a.detail ->> 'sha256' = f.sha256
         ORDER BY a.at DESC LIMIT 1) AS evidence,
       (SELECT jsonb_build_object('headers', a.detail -> 'served_headers', 'terminal_url', a.terminal_url)
          FROM litkb.acquisition_attempts a
         WHERE a.work_id = fv.work_id AND a.status = 'ok' AND a.detail ->> 'sha256' = f.sha256
         ORDER BY a.at DESC LIMIT 1) AS landed
  FROM litkb.file_versions fv JOIN litkb.files f ON f.id = fv.file_id
 WHERE fv.status = 'active' AND fv.state IN ('proposed', 'prepared', 'promoted')
   AND fv.created_at > %s AND fv.workstream_id::text = ANY(%s)
 ORDER BY fv.created_at, fv.file_id
"""


def bound_since_freeze(conn, manifest):
    """RUN-SCOPED (S4.5 decision D1): the file versions bound after `frozen_at` in the run's workstreams, each
    re-classified by the acceptance test's own detectors. -> list of dicts."""
    from litkb.acquire import accept as A

    ws = [str(w) for w in manifest.get("run_workstream_ids") or []]
    if not ws:
        return []
    root = _root(manifest)
    out = []
    for fid, wid, rel, pages, src, sha, ev, landed in conn.execute(_BOUND_SQL,
                                                                    (manifest["frozen_at"], ws)).fetchall():
        ev = ev if isinstance(ev, dict) else (json.loads(ev) if ev else {})
        landed = landed if isinstance(landed, dict) else (json.loads(landed) if landed else {})
        # the ladder's own record of the served headers (D22) beside the acceptance test's evidence: a landing the
        # test did not judge (a known-bad arm, a path that never called it) is still re-read by its headers
        heads = {**(landed.get("headers") or {}), **(ev.get("headers") or {})}
        rec = A.record_pages_of(conn, wid)
        row = {"file_id": fid, "work_id": wid, "rel_path": rel, "pages": pages, "record_pages": rec,
               "evidence": bool(ev)}
        p = root / rel
        texts = images = None
        if p.is_file():
            texts, images, _err = A.page_facts(p.read_bytes())
        row["readable"] = texts is not None
        row["image_pages"] = len(A.image_pages_of(texts, images)) if texts is not None else 0
        tf = A.text_facts(texts or [])
        row["short_text"] = texts is not None and tf["chars"] < A.STUB_MAX_CHARS and not tf["has_reference_section"]
        urls = ((ev.get("url") or src, ev.get("terminal_url")) if ev else (src,)) + (landed.get("terminal_url"),)
        row["stub_signals"] = (A.stub_signals(texts, headers=heads, urls=urls, images=images)
                               if texts is not None else A.evidence_signals(headers=heads, urls=urls))
        row["volume"] = A.volume_check(pages if pages is not None else (len(texts) if texts else None), rec)
        out.append(row)
    return out


def stubs_bound(conn, manifest):
    """Files bound in the run whose bytes (or recorded evidence) the stub detector calls a stub."""
    return sum(1 for r in bound_since_freeze(conn, manifest) if r["stub_signals"])


def volumes_bound_as_article(conn, manifest):
    """Files bound in the run with pages >= VOLUME_PAGES against a record range (a-b digits ONLY) under that."""
    return sum(1 for r in bound_since_freeze(conn, manifest) if r["volume"] == "volume")


def page_ranges_unparsed(conn, manifest):
    """REPORTED: files bound in the run with pages >= VOLUME_PAGES whose record range does not parse as `a-b`
    digits (empty included): the volume question was asked of them and could not be answered."""
    from litkb.acquire import accept as A

    return sum(1 for r in bound_since_freeze(conn, manifest)
               if (r["pages"] or 0) >= A.VOLUME_PAGES and r["volume"] in ("unparsed", "absent"))


def stub_rule_abstained_image_pages(conn, manifest):
    """REPORTED (not a plan (b) name; builder-C1b's, auditor-C1b F1): files bound in the run holding an IMAGE page
    (decision D13) and under the stub rule's character count with no reference heading — the ones `chars_no_refs`
    did not ask. A scanned article belongs here; so does ANY short document with one image page, a text stub
    followed by an image-only cover or advertisement included, which is this abstention's stated limit
    (auditor-C1b round 2, F1). Counted so the referee sees the size of what the rule did not judge; a file with
    an image page and a long text is not here (the rule would not have fired on it either)."""
    return sum(1 for r in bound_since_freeze(conn, manifest) if r["image_pages"] and r["short_text"])


def bound_files_unreadable(conn, manifest):
    """REPORTED (not a plan (b) name; builder-C1b's, auditor-C1b round 2 F11): files bound in the run that the
    counters could not read from disk (moved, or pdfium could not open them). The evidence signals are still
    asked of them; their text signal and their page count from the bytes are not — this says how many."""
    return sum(1 for r in bound_since_freeze(conn, manifest) if not r["readable"])


COUNTERS = {"quarantines_without_reason": quarantines_without_reason, "stubs_bound": stubs_bound,
            "volumes_bound_as_article": volumes_bound_as_article}
REPORTED = {"page_ranges_unparsed": page_ranges_unparsed,
            "stub_rule_abstained_image_pages": stub_rule_abstained_image_pages,
            "bound_files_unreadable": bound_files_unreadable}


# ── the fires ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _swap(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def _refuse_live(conn):
    from litkb.db import connect as c

    db = conn.execute("SELECT current_database()").fetchone()[0]
    if not c.is_test_db(db):
        raise RuntimeError(f"litkb_hardening_c1b fires run on a worker database only, never on {db!r}")
    return db


def _salted(data, what):
    """A per-call comment after %%EOF (the `queue_fire._salt` precedent): `files.sha256` is UNIQUE, so the same
    bytes could bind once per database. No page, no text, no page count changes."""
    return data + f"\n% {what} salt {uuid.uuid4().hex}\n".encode()


def _setup(conn, workdir, arm, *, title, family, pages=None, work_type="article"):
    """A workstream with its token, a main work carrying `title` / `family` / `pages`, a Store under workdir,
    and the DB clock before anything is bound (the run-scoped counters' `frozen_at`)."""
    from psycopg.types.json import Jsonb

    from litkb.acquire import run
    from litkb.acquire.store import Store

    _refuse_live(conn)
    ws, token = conn.execute("SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/test', NULL, "
                             "'c1b fire', NULL)", (f"c1b-{uuid.uuid4().hex[:12]}",)).fetchone()
    frozen = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    key = f"{family.split()[-1].capitalize()}_2099_c1b-fire-{uuid.uuid4().hex[:8]}"
    fields = {"type": work_type, "title": title, "authors": [{"family": family, "given": "A."}], "year": 2099}
    if pages:
        fields["pages"] = pages
    wid = conn.execute("SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, "
                       "'setup', 'setup')", (Jsonb({"key": key}), Jsonb(fields), ws)).fetchone()[0]
    base = Path(workdir) / f"{arm}-{uuid.uuid4().hex[:6]}"
    store = Store(base / "Lit", index_cache=base / "index.json")
    (store.root / "Validation").mkdir(parents=True, exist_ok=True)
    return ws, token, frozen, run.work_record(conn, work_id=wid), store


def _offer(conn, ws, token, work, data, store, **kw):
    """offer_to_bind, then the attempt row the ladder writes (so the counter finds the landing's evidence)."""
    from litkb.acquire import accept as A
    from litkb.acquire import run

    status, detail = A.offer_to_bind(conn, ws, token, work, data, route="open_access",
                                     source_url=kw.pop("source_url", "https://constructed.example/paper.pdf"),
                                     store=store, index=store.disk_index(), agent="c1b-fire", session="c1b-fire",
                                     **kw)
    # the verdict's sub-status reaches the ledger as the ladder writes it (seam integrator-w1, A x C1a x C1b)
    run.record_attempt(conn, ws, token, work["work_id"], "open_access", work.get("doi"), status, detail,
                       sub_status=detail.get("sub_status"))
    return status, detail


def _manifest(ws, frozen, store):
    return {"frozen_at": frozen, "run_workstream_ids": [str(ws)], "literature_root": str(store.root)}


def _to_quarantine_without_its_sidecar(original):
    """`Store.to_quarantine` with ITS sidecar write switched off and nothing else: the instance's `write_reason`
    is shadowed for the length of that one call only, so `quarantine_new` (the acceptance test's refusal path)
    still writes its own sidecar (auditor-C1b F6: switching `Store.write_reason` off globally broke that path
    with a TypeError, which the harness can only print as DID-NOT-FIRE (error))."""
    def no_sidecar(self, *a, **k):
        self.write_reason = lambda quarantined, reason: None
        try:
            return original(self, *a, **k)
        finally:
            del self.write_reason
    return no_sidecar


def fire_sidecar(conn, arm, workdir):
    """(c) "the sidecar write removed and a bad download quarantined -> quarantines_without_reason=1".
    The bad download: the CONSTRUCTED BOM article offered to a work it is NOT (binding-failed -> to_quarantine)."""
    from litkb.acquire.store import Store

    ws, token, _frozen, work, store = _setup(conn, workdir, arm, title="A work whose file this is not at all",
                                             family="Otherauthor")
    data = _salted((NEG_DIR / "CONSTRUCTED_bom_valid_article.pdf").read_bytes(), "fire_sidecar")
    ctx = (_swap(Store, "to_quarantine", _to_quarantine_without_its_sidecar(Store.to_quarantine))
           if arm == "known_bad" else contextlib.nullcontext())
    with ctx:
        _offer(conn, ws, token, work, data, store)
    return quarantines_without_reason(conn, {"literature_root": str(store.root)})


def _fire_stub(conn, arm, workdir, data, *, title, family, work_type="article", **offer):
    from litkb.acquire import accept as A

    ws, token, frozen, work, store = _setup(conn, workdir, arm, title=title, family=family, work_type=work_type)
    ctx = _swap(A, "stub_signals", lambda *a, **k: []) if arm == "known_bad" else contextlib.nullcontext()
    with ctx:
        _offer(conn, ws, token, work, data, store, **offer)
    return stubs_bound(conn, _manifest(ws, frozen, store))


def fire_stub_constructed(conn, arm, workdir):
    """(c) the CONSTRUCTED first-page TDM stub (with its CONSTRUCTED X-ELS-Status header) offered to a bind
    with the stub detector disabled -> stubs_bound=1; control 0 (refused stub_not_article)."""
    N = _negatives()
    headers = json.loads((NEG_DIR / "CONSTRUCTED_tdm_stub_first_page.headers.json").read_text(encoding="utf-8"))
    data = _salted((NEG_DIR / "CONSTRUCTED_tdm_stub_first_page.pdf").read_bytes(), "fire_stub_constructed")
    return _fire_stub(conn, arm, workdir, data, title=N.TDM_TITLE, family=N.TDM_AUTHOR, headers=headers)


def fire_stub_e20(conn, arm, workdir):
    """(c) E20's REAL publisher preview (qc/fixtures/litkb_e20_preview.pdf) offered to its own work with the stub
    detector disabled -> stubs_bound=1; control 0 (refused stub_not_article by its terminal URL)."""
    prov = json.loads(E20_PROV.read_text(encoding="utf-8"))
    data = _salted(E20_PDF.read_bytes(), "fire_stub_e20")
    return _fire_stub(conn, arm, workdir, data, title="Multi-State Survival Models for Interval-Censored Data",
                      family="van den Hout", work_type="book", source_url=prov["url_requested"],
                      terminal_url=prov["terminal_url"], headers={"Content-Type": prov["content_type"]})


def fire_volume(conn, arm, workdir):
    """(c) the CONSTRUCTED 60-page volume offered for a 12-page record with the volume detector disabled
    -> volumes_bound_as_article=1; control 0 (refused volume_not_article)."""
    from litkb.acquire import accept as A

    N = _negatives()
    ws, token, frozen, work, store = _setup(conn, workdir, arm, title=N.VOLUME_TITLE, family=N.VOLUME_AUTHOR,
                                            pages=N.VOLUME_RECORD_PAGES)
    data = _salted((NEG_DIR / "CONSTRUCTED_proceedings_volume_60p.pdf").read_bytes(), "fire_volume")
    ctx = _swap(A, "volume_check", lambda *a, **k: "article") if arm == "known_bad" else contextlib.nullcontext()
    with ctx:
        _offer(conn, ws, token, work, data, store)
    return volumes_bound_as_article(conn, _manifest(ws, frozen, store))


def fire_bom_repair(conn, arm, workdir):
    """(c) the CONSTRUCTED BOM article with the header repair removed -> refused `missing_pdf_header` (the
    ordering caveat: lstrip does not strip a BOM). The counter is this fire's own — `bom_valid_pdfs_refused`,
    NOT a plan (b) counter — so its bound is carried here (`=0`, the harness's bound grammar:
    an int 0 read as "no bound" and the fire could only print DID-NOT-FIRE; seam integrator-w1). No database is read."""
    from litkb.acquire import accept as A

    data = (NEG_DIR / "CONSTRUCTED_bom_valid_article.pdf").read_bytes()
    ctx = _swap(A, "repair_offset", lambda d: 0) if arm == "known_bad" else contextlib.nullcontext()
    with ctx:
        v = A.accept(data)
    return int(v.verdict == "refuse" and v.sub_status == "missing_pdf_header")


def _served_by_a_constructed_rung(data, headers, url):
    """A CONSTRUCTED rung registry of ONE rung on route `open_access` (a real route with a policy line) that serves
    `data` with `headers` — no network, no client. `needs=("key",)`: a fire's work carries no DOI."""
    from litkb.acquire import run

    def fn(work, ctx):
        return {"status": "downloaded", "pdf": data, "source_url": url, "http_codes": [200],
                "terminal": {"url": url, "status_code": 200, "headers": dict(headers)}}
    return [run.Rung("open_access", fn, needs=("key",))]


def _fire_ladder_stub(conn, arm, workdir, data, headers, *, title, family):
    """THE LADDER-LEVEL stub fire (S4.5 decision D21, seam integrator-w2): the bytes reach the bind through
    `run.acquire` — the path the live run lands with — from a CONSTRUCTED rung, never through `offer_to_bind`
    called directly. The known-bad removes the landing's acceptance test IN-PROCESS (`accept.offer_to_bind` is
    None, so `run._land` falls back to the bind alone, its unguarded default) and restores it before the counter
    runs."""
    from litkb.acquire import accept as A
    from litkb.acquire import run
    from litkb.netutil import Pacer

    ws, token, frozen, work, store = _setup(conn, workdir, arm, title=title, family=family)
    rungs = _served_by_a_constructed_rung(data, headers, "https://constructed.example/ladder/paper.pdf")
    ctx = _swap(A, "offer_to_bind", None) if arm == "known_bad" else contextlib.nullcontext()
    with ctx:
        run.acquire(conn, ws, token, work, store=store, routes=("open_access",), rungs=rungs, agent="c1b-fire",
                    session="c1b-fire", pacer=Pacer(interval=0), printer=lambda *a, **k: None, pacing={})
    return stubs_bound(conn, _manifest(ws, frozen, store))


def fire_stub_ladder(conn, arm, workdir):
    """(c) the CONSTRUCTED first-page TDM stub (its CONSTRUCTED X-ELS-Status header with it) served by a rung
    THROUGH THE LADDER (D21) with the landing's acceptance test removed -> stubs_bound=1; control 0 (the ladder's
    landing refuses it stub_not_article)."""
    N = _negatives()
    headers = json.loads((NEG_DIR / "CONSTRUCTED_tdm_stub_first_page.headers.json").read_text(encoding="utf-8"))
    data = _salted((NEG_DIR / "CONSTRUCTED_tdm_stub_first_page.pdf").read_bytes(), "fire_stub_ladder")
    return _fire_ladder_stub(conn, arm, workdir, data, headers, title=N.TDM_TITLE, family=N.TDM_AUTHOR)


def fire_stub_ladder_header_only(conn, arm, workdir):
    """(c) a WHOLE, binding article (the CONSTRUCTED BOM article with its BOM removed: >3,000 characters and a
    References section, so its bytes carry no stub signal) served with ONLY the CONSTRUCTED X-ELS-Status header,
    through the ladder with the acceptance test removed -> stubs_bound=1. The counter can see it ONLY in the headers
    the ladder recorded itself (`detail.served_headers`, S4.5 decision D22): with that record gone this arm reads 0
    and the harness prints DID-NOT-FIRE. Control 0 (refused `stub_not_article` on the header)."""
    N = _negatives()
    headers = {"Content-Type": "application/pdf", **N.TDM_HEADERS}
    data = _salted((NEG_DIR / "CONSTRUCTED_bom_valid_article.pdf").read_bytes()[len(N.BOM):],
                   "fire_stub_ladder_header_only")
    return _fire_ladder_stub(conn, arm, workdir, data, headers, title=N.BOM_TITLE, family="Constructor")


FIRES = {"sidecar": {"counter": "quarantines_without_reason", "run": fire_sidecar},
         "stub_constructed": {"counter": "stubs_bound", "run": fire_stub_constructed},
         "stub_e20": {"counter": "stubs_bound", "run": fire_stub_e20},
         "volume": {"counter": "volumes_bound_as_article", "run": fire_volume},
         "bom_repair": {"counter": "bom_valid_pdfs_refused", "run": fire_bom_repair, "bound": "=0"},
         # integrator-w2 (S4.5 decisions D21, D22): the same stub, and a header-only stub, through the LADDER
         "stub_ladder": {"counter": "stubs_bound", "run": fire_stub_ladder},
         "stub_ladder_header_only": {"counter": "stubs_bound", "run": fire_stub_ladder_header_only}}
