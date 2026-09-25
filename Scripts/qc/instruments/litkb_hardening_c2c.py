"""litkb S4.5 builder C2c — Stage E's counters and fires (Wayback E1, Internet Archive E3, Common Crawl E5), for
`litkb_acceptance.py hardening`.

Loaded BY PATH by builder A's `hardening` subcommand (qc/instruments is not a package; S4.5 CONTRACTS "Counters and
fires"). It defines:

  COUNTERS  {}  — no gated counter is Stage E's alone. The plan's (b) gates Stage E only through
                `free_ceiling_measured_unconverted` ("the FREE-PDF and Wayback rows still without a file"), which is
                builder C2a's counter; its WAYBACK HALF is `wayback_rows_unconverted` below, ONE home, for C2a's
                counter to call (brief-C2c item 6). S4.5 item 5b's four gated counters are NOT BUILT (orchestrator
                scope ruling 2026-09-23) and are not defined here.
  REPORTED  rung_conversions_<route> / rung_asked_<route> for wayback, ia, commoncrawl (from ATTEMPT rows, CONTRACTS
            D1: "a rung's yield is never read from a work's file state alone"); wayback_rows_unconverted;
            wayback_negatives_mistyped; wayback_wrong_work_counted.
  FIRES     five (below), each also a pytest test in qc/test_litkb_stage_e.py (the S4.5 fix wave FX-E's two
            also in qc/test_litkb_fx_stage_e.py).

THE PLAN'S TWO E1 ROWS, RE-GRADED AGAINST THE RECORDED TRUTH (the rule of S4.5 decision D10: a row whose prediction
the recording contradicts is re-graded against what was recorded, never hand-edited to pass). `WAYBACK_ROWS` below
is the ONE home of the grades; the orchestrator confirms or overrides them there, or per run through the manifest.
  * The plan's POSITIVE, the census.gov copy named for 10.1002/wics.1317, is a DIFFERENT WORK (auditor-C2c-r2 F1,
    re-read by builder-C2c round 3). The recorded capture is William E. Winkler's U.S. Bureau of the Census paper
    "Matching and Record Linkage": 38 pages, "This chapter focuses on ...", report number rr93-8 in its URL, no
    citation later than 1993. 10.1002/wics.1317 is his 2014 WIREs overview of the same name, which live already holds
    (13 pages). Same title, same author: the binder's title-and-author check cannot tell the two apart, and MEASURE
    mode checks no identity at all. Graded `wrong-work`: E1 hitting it is a FALSE conversion, counted by
    `wayback_wrong_work_counted` and never by `wayback_rows_unconverted`. Hardening-1 counted it (referee-stage-e
    L022); since the S4.5 fix wave FX-E the Stage E rungs' identity rule books it `hash-mismatch` (the capture prints
    no year after 1993, the record's is 2014: `litkb.acquire.recovery.capture_identity`), fire
    `stage_e_wrong_work_capture_credited`.
  * The plan's NEGATIVE, the IIASA copy of 10.5067/doc/ceoswgcv/lpv/lc.001 ("never archived", survey §M), IS archived
    and IS the work (auditor-C2c-r2 F2): availability names capture 20251206182454, whose id_ fetch is the 188-page
    CEOS LPV "Land Cover and Change Map Accuracy Assessment and Area Estimation Good Practices Protocol", whose own
    citation line carries that DOI; live holds no file for the work. Graded `positive`: E1's real positive row.
  * So E1 has NO real NEGATIVE row. `wayback_negatives_mistyped` reads 1 on an empty negative list (fail closed: the
    plan's never-archived negative is unmet) until a never-archived REAL URL is named under a new grant.

WHAT THE RECORDING SHOWED about the brief's three fires (qc/fixtures/litkb_cassettes/stage_e/, recorded 2026-09-23
through builder A's cassette; provenance.json there):
  * `stage_e_wayback_rung_disabled` replays the REAL census capture for a CONSTRUCTED admission: it shows E1 is asked
    and converts a real archived PDF, never that the PDF is 10.1002/wics.1317;
  * the capture WITHOUT a raw modifier served the SAME PDF bytes (same sha256) to this client: the brief's
    "the id_ modifier removed -> the recorded positive is refused as HTML" CANNOT fire on the real row (MEASURED; the
    survey's "MANDATORY or you store the wrapper" is not what this capture did). The fire here is therefore
    `stage_e_raw_modifier_removed_constructed`: a CONSTRUCTED wrapper page at the bare capture URL — the survey's claim,
    not an observation — so it tests the rung's handling of a wrapper, not whether the Wayback Machine sends one;
  * no real never-archived URL exists (above), so the `not_found` typing's fire is
    `stage_e_not_found_typing_removed_constructed`, on a CONSTRUCTED never-archived URL (availability `{}`, CDX `[]`).

Counter scoping (S4.5 decision D1): the rung counters are RUN-SCOPED (after `frozen_at`, in `run_workstream_ids`);
`wayback_rows_unconverted`, `wayback_negatives_mistyped` and `wayback_wrong_work_counted` are ALL-TIME
(`free_ceiling_measured_unconverted` is on D1's all-time list), keyed by DOI through `litkb.main_identifiers`. Manifest
keys read beyond CONTRACTS' list (named for builder A): `wayback_positive_dois`, `wayback_negative_dois`,
`wayback_wrong_work_dois` — optional; absent, the grades in `WAYBACK_ROWS` are used. An EMPTY positive or negative
list is never a pass: those two counters read 1 on it. No fire touches the network: the REAL recording is replayed (a
socket-free cassette replay) or a stub answers.
"""
import contextlib
import hashlib
import json
import uuid
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
CASSETTE_DIR = SCRIPTS / "qc" / "fixtures" / "litkb_cassettes" / "stage_e"
INDEX = CASSETTE_DIR / "index.jsonl"
BODIES = CASSETTE_DIR / "bodies"

#: The plan's two E1 rows, as the plan names them (LITKB_WORKPLAN.md "### S4.5" item 6 + the Test set; PDF-sources
#: survey §M; the URLs are the two 404 rows of phase4/qc/litkb_acq_probe_head.csv, which builder A's `wayback` run
#: selector reads). Their GRADES are `WAYBACK_ROWS`, not the plan's roles.
CENSUS_DOI = "10.1002/wics.1317"
CENSUS_URL = "http://www.census.gov/srd/papers/pdf/rr93-8.pdf"
IIASA_DOI = "10.5067/doc/ceoswgcv/lpv/lc.001"
IIASA_URL = ("https://pure.iiasa.ac.at/id/eprint/20873/1/"
             "CEOS_WGCV_LPV_Land_Cover_protocol_Sept2025_V1.pdf")
#: THE RE-GRADE (module docstring): (doi, url, the plan's role, the grade by the recorded truth, the evidence).
#: Grades: "positive" (E1 must convert the row), "negative" (E1 must end it blocked/not_found), "wrong-work" (the
#: archived copy is another work: an E1 hit on it is a false conversion).
WAYBACK_ROWS = (
    (CENSUS_DOI, CENSUS_URL, "positive", "wrong-work",
     "the recorded capture is Winkler's U.S. Census Bureau paper rr93-8 (38 pages, no citation after 1993), not the "
     "2014 WIREs overview live holds for the DOI (13 pages): auditor-C2c-r2 F1"),
    (IIASA_DOI, IIASA_URL, "negative", "positive",
     "archived 2025-12-06 (capture 20251206182454), the 188-page CEOS LPV protocol itself, citing the DOI; live holds "
     "no file for the work: auditor-C2c-r2 F2"),
)
WAYBACK_POSITIVE_DOIS = tuple(r[0] for r in WAYBACK_ROWS if r[3] == "positive")
WAYBACK_NEGATIVE_DOIS = tuple(r[0] for r in WAYBACK_ROWS if r[3] == "negative")
WAYBACK_WRONG_WORK_DOIS = tuple(r[0] for r in WAYBACK_ROWS if r[3] == "wrong-work")
#: 10.1002/wics.1317's work as `litkb.acquire.run.work_record` returns it on the live database (read as
#: litkb_reader, 2026-09-23: Winkler_2014_matching-record-linkage) — the fields the recorded IA search was built from.
#: It is the DOI's record, NOT the identity of the census capture (`CENSUS_CAPTURE_IDENTITY`).
CENSUS_ROW_WORK = {"doi": CENSUS_DOI, "arxiv": None, "key": "Winkler_2014_matching-record-linkage",
                   "title": "Matching and record linkage", "title_forms": ["Matching and record linkage"],
                   "first_author": "Winkler", "year": 2014}
#: What live holds for 10.1002/wics.1317 (read as litkb_reader by builder-C2c round 3, 2026-09-23, before any
#: S4.5 migration): its active file, from `annas`.
WICS_1317_HELD_PAGES = 13
WICS_1317_HELD_SHA256 = "6ff2296259e76135c2031cc8f306bd1adc86b4a5a890b32fb04cd7ec5438f7e7"
#: The census capture's OWN identity: page 1's title and author, and the year of its report number (rr93-8, in the
#: URL) which is also the latest year it cites (pdftotext over the tracked body, builder-C2c round 3). The PDF's own
#: CreationDate reads 1996-09-05 (pdfinfo): a later rendering, not the paper's year. 38 pages (pdfinfo).
CENSUS_CAPTURE_IDENTITY = {"title": "Matching and Record Linkage", "first_author": "Winkler", "year": 1993}
CENSUS_CAPTURE_PAGES = 38
#: The recorded bytes of the census capture (index.jsonl; provenance.json), and of the IIASA capture (not kept).
CENSUS_PDF_SHA256 = "b3cd70fd5120cdcc2071646a16a87fc6e70d215958e0c98a70bc36df68956f9d"
CENSUS_CAPTURE_TS = "20210322000835"
IIASA_PDF_SHA256 = "bb6237b65bd3fd3ad49f764e0245492a441122f4d627aebaf150b2d9dc12f7e2"
IIASA_CAPTURE_TS = "20251206182454"

#: The cassette rows (litkb.cassette.Cassette.begin_row tags).
ROW_CENSUS = f"stage-e:wayback:{CENSUS_DOI}"
ROW_CENSUS_NO_RAW = f"stage-e:wayback-no-raw-modifier:{CENSUS_DOI}"
ROW_CENSUS_IF = f"stage-e:wayback-if:{CENSUS_DOI}"
ROW_IIASA = f"stage-e:wayback:{IIASA_DOI}"
ROW_IA = f"stage-e:ia:{CENSUS_DOI}"
ROW_COMMONCRAWL = f"stage-e:commoncrawl:{CENSUS_DOI}"

STAGE_E_ROUTES = ("wayback", "ia", "commoncrawl")
HIT_STATUSES = ("ok", "measured")


# ── scoping ─────────────────────────────────────────────────────────────────────────────────
def _scope(manifest):
    """-> (frozen_at, [workstream ids]) for a run-scoped counter (S4.5 decision D1); refused without them."""
    frozen = (manifest or {}).get("frozen_at")
    ws = list((manifest or {}).get("run_workstream_ids") or [])
    if not ws and (manifest or {}).get("workstream_id"):
        ws = [manifest["workstream_id"]]
    if not frozen or not ws:
        raise ValueError("a run-scoped counter needs manifest frozen_at and run_workstream_ids (S4.5 decision D1)")
    return frozen, [str(w) for w in ws]


def _non_spend():
    from litkb.acquire import backoff as B
    return sorted(B.NON_SPEND_STATUSES)


# ── the rung counters (REPORTED, run-scoped) ───────────────────────────────────────────────
def _conversions(route):
    def fn(conn, manifest):
        """Run-scoped: works with an attempt on this route that HIT (`ok` landed, `measured` would have)."""
        frozen, ws = _scope(manifest)
        return conn.execute(
            "SELECT count(DISTINCT work_id) FROM litkb.acquisition_attempts WHERE route = %s AND at > %s "
            "AND workstream_id::text = ANY(%s) AND status = ANY(%s)", (route, frozen, ws, list(HIT_STATUSES))
        ).fetchone()[0]
    fn.__name__ = f"rung_conversions_{route}"
    return fn


def _asked(route):
    def fn(conn, manifest):
        """Run-scoped: works this route was ASKED for (a spent attempt: not a skip, not a budget stop)."""
        frozen, ws = _scope(manifest)
        return conn.execute(
            "SELECT count(DISTINCT work_id) FROM litkb.acquisition_attempts WHERE route = %s AND at > %s "
            "AND workstream_id::text = ANY(%s) AND status <> ALL(%s)", (route, frozen, ws, _non_spend())
        ).fetchone()[0]
    fn.__name__ = f"rung_asked_{route}"
    return fn


# ── the Wayback rows (REPORTED, all-time) ───────────────────────────────────────────────────
_UNCONVERTED_SQL = """
SELECT d.doi FROM unnest(%s::text[]) AS d(doi)
 WHERE NOT EXISTS (
   SELECT 1 FROM litkb.main_identifiers i JOIN litkb.acquisition_attempts a ON a.work_id = i.work_id
    WHERE i.scheme = 'doi' AND i.active AND i.value_norm = litkb.norm_identifier('doi', d.doi)
      AND a.route = 'wayback' AND a.status = ANY(%s))
 ORDER BY 1
"""


#: How a row list with NO row reads: the plan names a Wayback row that MUST convert and a link that MUST end
#: `not_found`; a list the re-grade (or a manifest) left empty is that requirement unmet, never a pass.
NO_ROW = "(no row)"


def _dois(manifest, key, default):
    """The manifest's list under `key` when it names one (an explicit empty list included), else `default`."""
    got = (manifest or {}).get(key)
    return [str(d) for d in (default if got is None else got)]


def wayback_rows_unconverted_list(conn, manifest):
    """The Wayback POSITIVE rows (the manifest's `wayback_positive_dois`, else `WAYBACK_POSITIVE_DOIS`) with NO
    `wayback` attempt that hit (`ok` or `measured`), all time. A work that already holds a file from another route
    still counts until E1 itself converts or measures it — reading the file state would grade the file, not the
    rung (CONTRACTS D1). With no positive row at all the list is [NO_ROW]: unmet, never passed."""
    dois = _dois(manifest, "wayback_positive_dois", WAYBACK_POSITIVE_DOIS)
    if not dois:
        return [NO_ROW]
    return [r[0] for r in conn.execute(_UNCONVERTED_SQL, (dois, list(HIT_STATUSES))).fetchall()]


def wayback_rows_unconverted(conn, manifest):
    """THE WAYBACK HALF of builder C2a's gated `free_ceiling_measured_unconverted` (its one home; C2a's counter
    adds this to its FREE-PDF half): -> how many of the Wayback positive rows E1 has not converted."""
    return len(wayback_rows_unconverted_list(conn, manifest))


_NEGATIVE_SQL = """
SELECT d.doi,
       (SELECT a.status || '/' || coalesce(a.sub_status, '')
          FROM litkb.main_identifiers i JOIN litkb.acquisition_attempts a ON a.work_id = i.work_id
         WHERE i.scheme = 'doi' AND i.active AND i.value_norm = litkb.norm_identifier('doi', d.doi)
           AND a.route = 'wayback' AND a.status NOT IN ('skipped', 'budget-stop')
         ORDER BY a.at DESC, a.id DESC LIMIT 1)
  FROM unnest(%s::text[]) AS d(doi) ORDER BY 1
"""


def wayback_negatives_list(conn, manifest):
    """[(doi, latest spent `wayback` attempt as 'status/sub_status', or None)] for the NEGATIVE rows (the
    manifest's `wayback_negative_dois`, else `WAYBACK_NEGATIVE_DOIS`); [(NO_ROW, None)] when there is none — the
    re-grade leaves E1 none (module docstring)."""
    dois = _dois(manifest, "wayback_negative_dois", WAYBACK_NEGATIVE_DOIS)
    if not dois:
        return [(NO_ROW, None)]
    return conn.execute(_NEGATIVE_SQL, (dois,)).fetchall()


def wayback_negatives_mistyped(conn, manifest):
    """All time: Wayback NEGATIVE rows whose latest spent `wayback` attempt is NOT `blocked/not_found` (no attempt
    at all counts: the plan's "must end `not_found` at E1" is unmet). With no negative row it reads 1 (NO_ROW): the
    plan's IIASA row is archived and re-graded positive, and E1 has no real never-archived row (module docstring)."""
    return sum(1 for _doi, last in wayback_negatives_list(conn, manifest) if last != "blocked/not_found")


_HIT_SQL = """
SELECT d.doi FROM unnest(%s::text[]) AS d(doi)
 WHERE EXISTS (
   SELECT 1 FROM litkb.main_identifiers i JOIN litkb.acquisition_attempts a ON a.work_id = i.work_id
    WHERE i.scheme = 'doi' AND i.active AND i.value_norm = litkb.norm_identifier('doi', d.doi)
      AND a.route = 'wayback' AND a.status = ANY(%s))
 ORDER BY 1
"""


def wayback_wrong_work_list(conn, manifest):
    """The WRONG-WORK rows (the manifest's `wayback_wrong_work_dois`, else `WAYBACK_WRONG_WORK_DOIS`) that hold a
    `wayback` attempt that hit (`ok` or `measured`), all time: E1 counted an archived copy of ANOTHER work as this
    one's. MEASURE mode judges the bytes, and the bind checks title and first author only, so the census capture
    passes both for 10.1002/wics.1317 (module docstring); the Stage E rungs' own identity rule
    (`litkb.acquire.recovery.capture_identity`, S4.5 fix wave FX-E) is what now books it `hash-mismatch`. Each is a
    false conversion that `rung_conversions_wayback` also counts."""
    dois = _dois(manifest, "wayback_wrong_work_dois", WAYBACK_WRONG_WORK_DOIS)
    if not dois:
        return []
    return [r[0] for r in conn.execute(_HIT_SQL, (dois, list(HIT_STATUSES))).fetchall()]


def wayback_wrong_work_counted(conn, manifest):
    """REPORTED, all time: how many wrong-work rows E1 counted as converted (`wayback_wrong_work_list`)."""
    return len(wayback_wrong_work_list(conn, manifest))


def _negative_detail(doi, last):
    if doi == NO_ROW:
        return ("no real NEGATIVE row: the plan's IIASA row is archived and re-graded positive (WAYBACK_ROWS); a "
                "never-archived real URL needs a new grant")
    return f"{doi}: latest wayback attempt {last or 'none'}"


COUNTERS = {}
REPORTED = {
    **{f"rung_conversions_{r}": _conversions(r) for r in STAGE_E_ROUTES},
    **{f"rung_asked_{r}": _asked(r) for r in STAGE_E_ROUTES},
    "wayback_rows_unconverted": wayback_rows_unconverted,
    "wayback_negatives_mistyped": wayback_negatives_mistyped,
    "wayback_wrong_work_counted": wayback_wrong_work_counted,
}
DETAILS = {
    "wayback_rows_unconverted": lambda conn, m: [
        "no Wayback POSITIVE row" if d == NO_ROW else f"unconverted: {d}" for d in wayback_rows_unconverted_list(conn, m)],
    "wayback_negatives_mistyped": lambda conn, m: [_negative_detail(d, last)
                                                   for d, last in wayback_negatives_list(conn, m)
                                                   if last != "blocked/not_found"],
    "wayback_wrong_work_counted": lambda conn, m: [f"a wayback hit on {d}, whose archived copy is another work"
                                                   for d in wayback_wrong_work_list(conn, m)],
}


# ── the recording ───────────────────────────────────────────────────────────────────────────
def census_pdf():
    """The census.gov capture's REAL recorded bytes, checked against the recorded sha256."""
    p = BODIES / CENSUS_PDF_SHA256[:2] / f"{CENSUS_PDF_SHA256}.bin"
    data = p.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != CENSUS_PDF_SHA256:
        raise RuntimeError(f"{p.name}: sha256 {got} is not the recorded {CENSUS_PDF_SHA256}")
    return data


def replay_client(row):
    """A real `litkb.netutil.Client` answering from the recorded cassette (REPLAY: no socket), on `row`."""
    from litkb import cassette as CAS
    from litkb.netutil import Client

    cas = CAS.Cassette(INDEX, "replay", bodies=BODIES)
    cas.begin_row(row)
    return Client(base="", cassette=cas), cas


def recorded_entries(row=None):
    """The index's interactions (optionally one row's), as JSON dicts."""
    lines = INDEX.read_bytes().splitlines()
    out = [json.loads(ln) for ln in lines[1:] if ln.strip()]
    return [e for e in out if row is None or e.get("row") == row]


# ── CONSTRUCTED answers (the two fires the recording could not supply) ────────────────────────
#: CONSTRUCTED: a never-archived URL — no host was asked about it.
CONSTRUCTED_DEAD_URL = "https://reports.constructed.invalid/never-archived-report.pdf"
#: CONSTRUCTED: the Wayback Machine's HTML page around a capture, as the PDF-sources survey §1 E1 says it is served
#: without a raw modifier. The recording did NOT show one for the census capture (module docstring).
CONSTRUCTED_WRAPPER = (b"<!DOCTYPE html><html><head><title>Wayback Machine</title></head><body>"
                       b"<div id='wm-ipp'>CONSTRUCTED wrapper page (litkb S4.5 builder-C2c): not a recording.</div>"
                       b"<iframe id='playback' src='https://web.archive.org/web/" + CENSUS_CAPTURE_TS.encode() +
                       b"if_/" + CENSUS_URL.encode() + b"'></iframe></body></html>")


class StubClient:
    """Answers by URL substring (the FIRST key that matches); an unknown URL is a 404, never the network."""
    base = ""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        self.calls.append(url)
        for frag, resp in self.routes.items():
            if frag in url:
                return resp(url) if callable(resp) else resp
        return 404, {}, b""


def constructed_never_archived():
    """CONSTRUCTED: the availability API with no capture, the CDX index with no row — for CONSTRUCTED_DEAD_URL."""
    return StubClient({"archive.org/wayback/available": (200, {"Content-Type": "application/json"}, json.dumps(
        {"url": CONSTRUCTED_DEAD_URL, "archived_snapshots": {}}).encode()),
        "/cdx/search/cdx": (200, {"Content-Type": "application/json"}, b"[]")})


def constructed_wrapper_client():
    """CONSTRUCTED around REAL bytes: the recorded availability answer and the recorded PDF at the id_ capture, and a
    CONSTRUCTED wrapper at the bare capture URL (and an empty CDX)."""
    avail = next(e for e in recorded_entries(ROW_CENSUS) if "/wayback/available" in e["key"]["url"])
    import base64
    body = base64.b64decode(avail["response"]["body"]["inline_b64"])
    pdf = census_pdf()
    bare = f"/web/{CENSUS_CAPTURE_TS}/{CENSUS_URL}"
    return StubClient({
        "archive.org/wayback/available": (200, {"Content-Type": "application/json"}, body),
        f"/web/{CENSUS_CAPTURE_TS}id_/": (200, {"Content-Type": "application/pdf"}, pdf),
        f"/web/{CENSUS_CAPTURE_TS}if_/": (200, {"Content-Type": "application/pdf"}, pdf),
        bare: (200, {"Content-Type": "text/html; charset=utf-8"}, CONSTRUCTED_WRAPPER),
        "/cdx/search/cdx": (200, {"Content-Type": "application/json"}, b"[]")})


# ── the fires' world: a worker database only ────────────────────────────────────────────────
class World:
    """A workstream, CONSTRUCTED admissions and a writer session on a WORKER database (never `litkb`)."""

    def __init__(self, conn, workdir):
        from litkb.acquire.store import Store
        from litkb.db import connect as c

        dbname = conn.info.dbname
        # BEGIN guard: a C2c fire runs only on a worker database
        if not c.is_test_db(dbname):
            raise RuntimeError(f"a C2c fire runs only on a litkb_test* worker database, not {dbname!r}")
        # END guard: a C2c fire runs only on a worker database
        self.owner = conn
        self.writer = c.connect(dbname, "litkb_test", autocommit=True)
        self.writer.execute("SET ROLE litkb_writer")
        self.workdir = Path(workdir)
        self.store = Store(self.workdir / "Lit", index_cache=self.workdir / "index.json")
        self.tokens = {}

    def close(self):
        self.writer.close()

    def ws(self, slug):
        ws_id, token = self.owner.execute(
            "SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/c2c-fire', NULL, %s, NULL)",
            (f"c2c-{slug}-{uuid.uuid4().hex[:10]}", "S4.5 builder C2c fire (worker database)")).fetchone()
        self.tokens[ws_id] = token
        return ws_id

    def work(self, ws, title=None, author=CENSUS_CAPTURE_IDENTITY["first_author"],
             year=CENSUS_CAPTURE_IDENTITY["year"]):
        """A CONSTRUCTED registry admission: a salted synthetic DOI (a DOI admits once per database, and a
        worker database holds none of the plan's works). Its author and year default to the census capture's OWN
        (`CENSUS_CAPTURE_IDENTITY`), so a fire that replays that capture never pairs it with 10.1002/wics.1317's
        2014 record. -> run.work_record's dict."""
        from psycopg.types.json import Jsonb

        from litkb.acquire import run

        hexid = uuid.uuid4().hex[:12]
        doi = f"10.5555/c2c-fire-{hexid}"
        title = title or f"A constructed Stage E work {hexid}"
        ev = {"registry": "crossref", "registry_title": title, "registry_first_author": author, "registry_year": year,
              "claimed": {"title": title, "first_author": author, "year": year, "title_ratio": 1.0,
                          "author_match": True}}
        tok = self.tokens[ws]
        cand = self.writer.execute(
            "SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
            (ws, tok, title)).fetchone()[0]
        res = self.writer.execute(
            "SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, 'c2c-fire', 'c2c-fire-1')",
            (ws, tok, cand, f"{author}_{year}_constructed-{hexid}",
             Jsonb({"type": "article", "title": title, "authors": [{"family": author, "given": "W."}], "year": year}),
             Jsonb([{"scheme": "doi", "value": doi, "verified_by": "crossref", "evidence": ev}]), Jsonb({}))).fetchone()[0]
        if res.get("outcome") != "admitted":
            raise RuntimeError(f"the constructed admission was refused: {res}")
        return run.work_record(self.writer, work_id=res["work_id"])

    def dead_link(self, ws, work, url, route="s2"):
        """CONSTRUCTED ledger row standing in for the Stage B answer the head probe MEASURED
        (phase4/qc/litkb_acq_probe_head.csv: the resolver's URL answered GET 404 text/html): the dead URL E1 is
        then asked about (litkb.acquire.recovery.ledger_urls)."""
        from litkb.acquire import run

        return run.record_attempt(self.writer, ws, self.tokens[ws], work["work_id"], route, work["doi"], "blocked",
                                  {"detail": "CONSTRUCTED stand-in for a Stage B answer (c2c fire)"}, [404],
                                  sub_status="not_found", terminal={"url": url, "status_code": 404})

    def ladder(self, ws, work, clients, *, mode="measure", **kw):
        from litkb.acquire import run
        from litkb.netutil import Pacer

        fn = run.measure if mode == "measure" else run.acquire
        return fn(self.writer, ws, self.tokens[ws], work, store=self.store, agent="c2c-fire", session="c2c-fire-1",
                  clients=clients, pacer=Pacer(interval=0, sleep=lambda s: None), printer=lambda *a, **k: None,
                  pacing={}, **kw)


def _rows(conn, work_id, route="wayback"):
    return conn.execute("SELECT status, sub_status, detail FROM litkb.acquisition_attempts WHERE work_id = %s "
                        "AND route = %s ORDER BY at, id", (work_id, route)).fetchall()


# ── S4.5 decision D39 (builder-fix6): a test that needs a switched-off rung ACTIVE ─────────────────
def policy_with_route_on(route):
    """-> a COPY of `litkb.acquire.policy.POLICY` in which `route`'s lines carry no `off_why` (CONSTRUCTED: E5's two
    hosts are switched off by D39, and a test of the rung's own mechanics needs it asked). The table is never
    edited. `litkb.acquire.run` is imported first: its rungs append their own lines to POLICY at import, and a copy
    taken before them would lose those lines when the override is lifted."""
    import dataclasses

    from litkb.acquire import policy as P
    from litkb.acquire import run  # noqa: F401 — the registry's own lines first (docstring)

    return tuple(dataclasses.replace(p, off_why="") if p.route == route else p for p in P.POLICY)


@contextlib.contextmanager
def route_switched_on(route):
    """`policy_with_route_on(route)` as the module POLICY for the with-block ONLY — every ladder decision reads the
    module table — and the table as it was after it. An explicit override in the test that asks for it, never a
    global clearing of `off_why`; it lives here, in the instrument, and in no pipeline module."""
    from litkb.acquire import policy as P

    with mock.patch.object(P, "POLICY", policy_with_route_on(route)):
        yield


# ── S4.5 decision D53 (integrator-w4): Common Crawl is back ON; a test of D39's switch installs hardening-1's table ──
def policy_with_route_off(route, why):
    """-> a COPY of `litkb.acquire.policy.POLICY` in which `route`'s lines carry `off_why=why` (CONSTRUCTED: the table
    as it stood in hardening-1 after D39 switched E5's two hosts off with `policy.COMMONCRAWL_OFF_WHY`; D53 switched
    them back on, so the switch's own mechanics — the refusal, the recorded skip, D42's per-row replay switch — are
    tested against this copy, never by editing the module table). `litkb.acquire.run` is imported first, as in
    :func:`policy_with_route_on`."""
    import dataclasses

    from litkb.acquire import policy as P
    from litkb.acquire import run  # noqa: F401 — the registry's own lines first (policy_with_route_on's docstring)

    return tuple(dataclasses.replace(p, off_why=why) if p.route == route else p for p in P.POLICY)


@contextlib.contextmanager
def route_switched_off(route, why):
    """`policy_with_route_off(route, why)` as the module POLICY for the with-block ONLY, and the table as it was after
    it (the mirror of :func:`route_switched_on`). It lives here, in the instrument, and in no pipeline module."""
    from litkb.acquire import policy as P

    with mock.patch.object(P, "POLICY", policy_with_route_off(route, why)):
        yield


# ── the fires ───────────────────────────────────────────────────────────────────────────────
def fire_wayback_rung_disabled(conn, arm, workdir):
    """(brief item 6) "the E1 rung disabled -> the positive row's Wayback attempt disappears (the counter moves)".
    REAL answers: the recorded census.gov capture (a real archived PDF — of Winkler's Census paper, NOT of
    10.1002/wics.1317: module docstring), replayed through the ladder in MEASURE mode (D9) for a CONSTRUCTED
    admission whose dead link is the census.gov URL; the counter is read on that admission's DOI alone. Control: the
    registry holds E1 and the ladder asks every Stage E rung it holds -> `measured` -> 0. Known-bad: the registry
    WITHOUT E1 (D19's failure: a rung that is never registered is never asked) -> no attempt -> 1."""
    from litkb.acquire import run

    w = World(conn, workdir)
    try:
        ws = w.ws("rung-disabled")
        work = w.work(ws)
        w.dead_link(ws, work, CENSUS_URL)
        rungs = list(run.RUNGS) if arm == "control" else [r for r in run.RUNGS if r.route != "wayback"]
        client, _cas = replay_client(ROW_CENSUS)
        w.ladder(ws, work, {"wayback": client}, rungs=rungs,
                 routes=tuple(r.route for r in rungs if r.route == "wayback"))
        return wayback_rows_unconverted(conn, {"wayback_positive_dois": [work["doi"]]})
    finally:
        w.close()


def fire_raw_modifier_removed(conn, arm, workdir):
    """(brief item 6, re-stated) "the id_ modifier removed -> the positive is refused as HTML instead of landing".
    The REAL recording cannot fire it (the bare capture served the same PDF: module docstring), so this arm serves
    a CONSTRUCTED wrapper page at the bare capture URL around the REAL recorded bytes. Control: RAW_MODIFIERS as
    shipped -> `measured` -> 0. Known-bad: no raw modifier -> the wrapper -> `bad-file/html_response` -> 1."""
    from litkb.acquire import wayback

    w = World(conn, workdir)
    try:
        ws = w.ws("raw-modifier")
        work = w.work(ws)
        w.dead_link(ws, work, CENSUS_URL)
        patch = (contextlib.nullcontext() if arm == "control"
                 else mock.patch.object(wayback, "RAW_MODIFIERS", ("",)))
        with patch:
            w.ladder(ws, work, {"wayback": constructed_wrapper_client()}, routes=("wayback",))
        return wayback_rows_unconverted(conn, {"wayback_positive_dois": [work["doi"]]})
    finally:
        w.close()


def fire_not_found_typing_removed(conn, arm, workdir):
    """(brief item 6, re-stated) "the IIASA row typed anything but `not_found` -> red". The IIASA row IS archived
    and re-graded positive (module docstring), so the negative is CONSTRUCTED: a never-archived URL (availability
    `{}`, CDX `[]`). Control: `blocked/not_found` -> 0. Known-bad: the rung's own `not_found` typing dropped (the
    ledger's generic typing then reads codes [200, 200] as `html_or_reader`) -> 1."""
    from litkb.acquire import wayback

    w = World(conn, workdir)
    try:
        ws = w.ws("not-found")
        work = w.work(ws)
        w.dead_link(ws, work, CONSTRUCTED_DEAD_URL)
        if arm == "control":
            patch = contextlib.nullcontext()
        else:
            real = wayback.fetch_wayback

            def untyped(*a, **k):
                r = real(*a, **k)
                r.pop("sub_status", None)
                return r
            patch = mock.patch.object(wayback, "fetch_wayback", untyped)
        with patch:
            w.ladder(ws, work, {"wayback": constructed_never_archived()}, routes=("wayback",))
        return wayback_negatives_mistyped(conn, {"wayback_negative_dois": [work["doi"]]})
    finally:
        w.close()


# ── S4.5 fix wave FX-E (referee-stage-e REJECT, brief-FIXWAVE.md "FX-E"): two fires on the seams it fixed ─────────
#: CONSTRUCTED: a location page that refuses this client with a plain 403 (no challenge signature) — the shape of
#: L054's ScienceDirect accepted-manuscript page, which Unpaywall listed FIRST, so its body is the one the open-access
#: route kept and the dead location after it survived only as a `host:code` token.
CONSTRUCTED_PAGE_URL = "https://publisher.constructed.invalid/article/accepted-manuscript"
CONSTRUCTED_403_PAGE = (b"<!DOCTYPE html><html><head><title>Forbidden</title></head><body>CONSTRUCTED 403 page "
                        b"(litkb S4.5 builder-FX-E): not a recording.</body></html>")


class SplitClient:
    """Answers a request whose URL carries `frag` from `first` (a replay), every other from `rest` (a stub)."""
    base = ""

    def __init__(self, frag, first, rest):
        self.frag, self.first, self.rest = frag, first, rest

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        c = self.first if self.frag in url else self.rest
        return c.get(url, accept=accept, timeout=timeout, follow=follow, data=data, headers=headers)


def constructed_open_access_client():
    """CONSTRUCTED Unpaywall answer and location answers (L054's shape): the refusing page first, the census.gov URL
    second, answering 404."""
    return StubClient({
        "api.unpaywall.org": (200, {"Content-Type": "application/json"}, json.dumps(
            {"is_oa": True, "oa_status": "green",
             "oa_locations": [{"url": CONSTRUCTED_PAGE_URL}, {"url": CENSUS_URL}]}).encode()),
        CONSTRUCTED_PAGE_URL: (403, {"Content-Type": "text/html; charset=utf-8"}, CONSTRUCTED_403_PAGE),
        "www.census.gov": (404, {"Content-Type": "text/html"}, b"<html>CONSTRUCTED 404 page</html>")})


def fire_dead_location_behind_a_kept_page(conn, arm, workdir):
    """(FX-E item 1; referee-stage-e N1, rows L007 and L054) "pass every dead candidate's FULL URL". A CONSTRUCTED
    admission (the census capture's own identity); the open-access route (CONSTRUCTED answers, L054's shape) keeps
    the refusing page and meets the census.gov URL dead after it; E1 answers the page as never archived (CONSTRUCTED)
    and the census.gov URL from the REAL recording. Control: the ladder reads every URL the rung asked from the
    request gate (`recovery.asked_urls`) -> E1 is asked about the census.gov URL -> `measured` -> 0. Known-bad: the
    gate record unread (411c3ce's seam: the rung dict's own fields only) -> E1 asks the page alone -> 1."""
    from litkb.acquire import open_access, recovery

    w = World(conn, workdir)
    try:
        ws = w.ws("dead-location")
        work = w.work(ws)
        census, _cas = replay_client(ROW_CENSUS)
        clients = {"open_access": constructed_open_access_client(),
                   "wayback": SplitClient("www.census.gov", census, constructed_never_archived())}
        patch = (contextlib.nullcontext() if arm == "control"
                 else mock.patch.object(recovery, "asked_urls", lambda r: []))
        with patch, mock.patch.object(open_access, "unpaywall_email", lambda: "c2c-fire@example.invalid"):
            w.ladder(ws, work, clients, routes=("open_access", "wayback"))
        return wayback_rows_unconverted(conn, {"wayback_positive_dois": [work["doi"]]})
    finally:
        w.close()


def fire_wrong_work_capture_credited(conn, arm, workdir):
    """(FX-E item 3; referee-stage-e L022) "a capture credited as a MEASURED conversion must be the work". The REAL
    recorded census.gov capture (Winkler's 1993 Census chapter) for a CONSTRUCTED admission carrying 10.1002/wics.1317's
    author and YEAR (`CENSUS_ROW_WORK`: 2014; a salted DOI and title), graded wrong-work through the manifest key.
    Control: the Stage E identity rule (`recovery.capture_identity`) books it `hash-mismatch` -> 0. Known-bad: the rule
    answering "no contradiction" (411c3ce's identity-blind MEASURE) -> `measured` -> 1."""
    from litkb.acquire import recovery

    w = World(conn, workdir)
    try:
        ws = w.ws("wrong-work")
        work = w.work(ws, year=CENSUS_ROW_WORK["year"])
        w.dead_link(ws, work, CENSUS_URL)
        client, _cas = replay_client(ROW_CENSUS)
        patch = (contextlib.nullcontext() if arm == "control"
                 else mock.patch.object(recovery, "capture_identity", lambda *a, **k: ""))
        with patch:
            w.ladder(ws, work, {"wayback": client}, routes=("wayback",))
        return wayback_wrong_work_counted(conn, {"wayback_wrong_work_dois": [work["doi"]]})
    finally:
        w.close()


FIRES = {
    "stage_e_dead_location_behind_a_kept_page": {"counter": "wayback_rows_unconverted", "bound": "=0",
                                                 "run": fire_dead_location_behind_a_kept_page},
    "stage_e_wrong_work_capture_credited": {"counter": "wayback_wrong_work_counted", "bound": "=0",
                                            "run": fire_wrong_work_capture_credited},
    "stage_e_wayback_rung_disabled": {"counter": "wayback_rows_unconverted", "bound": "=0",
                                      "run": fire_wayback_rung_disabled},
    "stage_e_raw_modifier_removed_constructed": {"counter": "wayback_rows_unconverted", "bound": "=0",
                                                 "run": fire_raw_modifier_removed},
    "stage_e_not_found_typing_removed_constructed": {"counter": "wayback_negatives_mistyped", "bound": "=0",
                                                     "run": fire_not_found_typing_removed},
}
