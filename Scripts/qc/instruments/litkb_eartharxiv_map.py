r"""Harvest EarthArXiv's OAI-PMH feed OFFLINE into a published-DOI -> preprint-PDF map (S4.5 builder C2a; plan
item 3's A7, "EarthArXiv's OAI map of published DOI to preprint PDF", MEASURED in the PDF-sources survey's
round 2: 7,670 records, in one 50-record page 50/50 carry a direct PDF URL and 32/50 the PUBLISHED-version DOI).

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_eartharxiv_map.py            # the plan; nothing sent
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_eartharxiv_map.py --live     # the orchestrator's pass

`--live` walks `ListRecords` (metadataPrefix `oai_dc`) through every `resumptionToken`, ONE request per page at
litkb's registry pace (1 s, admit/resolver.py REGISTRY_MIN_INTERVAL) through `netutil.Client` (the cassette seam),
and writes the map the `eartharxiv` rung reads (litkb.acquire.stage_a.eartharxiv_map; config.EARTHARXIV_MAP):
phase4/qc/litkb_eartharxiv_map.csv, columns `stage_a.EARTHARXIV_COLUMNS`. The survey's ~154 pages at 1 s is a
few minutes. NOT RUN by builder C2a: eartharxiv.org is not in its network grant — until the orchestrator runs it
the `eartharxiv` rung answers `api-error` "the EarthArXiv map is not harvested" and asks nothing.

THE PARSE (`parse_page`), from the oai_dc elements (Dublin Core, the OAI-PMH default): the preprint's OWN DOI is the
`10.31223/...` DOI among the record's `dc:identifier` / `dc:relation` / `dc:source` values (EarthArXiv's prefix,
survey A3); every OTHER DOI there is taken as a published version's DOI (the survey's "32/50 carry the
PUBLISHED-version DOI" does not name the element — this is the widest reading, and a DOI that is not the
published article only produces a map row a work never looks up); the PDF URL is an http identifier containing
`/download` or ending `.pdf` (the survey's HEAD on a download URL: 200 application/pdf). A record with no PDF URL is
skipped. The parse is tested on a CONSTRUCTED page (qc/test_litkb_stage_ab.py); it is UNVALIDATED on a real page
until the live pass runs.

A PARTIAL WALK IS NEVER THE MAP (auditor-C2a F14; survey A7's guard, "a harvested map cannot record an outage as a
permanent verdict"): a page that answers anything but 200, or a walk stopped before the last resumptionToken, writes
NOTHING at the map path — the rows read so far go to `<out>.partial.csv`, which no rung reads, and the exit is 1.
A map that is missing pages would book `no-oa-copy` for every work on them; no map books `api-error` (retriable).
An OAI-PMH protocol ERROR is carried INSIDE an HTTP 200 (OAI-PMH 2.0 §3.6: `<error code="badResumptionToken">` —
resumption tokens expire), and such a page parses with no record and no token, so a 200 alone is not a complete walk
(auditor-C2a round 2 F4): a page carrying any `<error>` stops the walk INCOMPLETE — except `noRecordsMatch` on the
FIRST page, which the protocol defines as the empty list (a complete walk of nothing); an unparseable 200 page stops
it too.

ONE REPAIR, AND ONLY ONE CLASS (builder-fix4, S4.5; `repair_xml10`): the live walk stopped INCOMPLETE on page 7
twice on 2026-09-23 because that page carries ONE literal U+FFFE — a Unicode noncharacter outside XML 1.0 §2.2's
`Char` production — inside a record's dc:description (MEASURED on the real page, kept as
qc/fixtures/litkb_eartharxiv_oai_page7_37129fe75ccb.xml; record oai:EA:id:1336), and expat refuses the whole page
for it. Before a page is read, every character outside `Char` is replaced by U+FFFD, so the record is KEPT (never
dropped) with the repair visible in its text; the walk counts the pages and the characters repaired and prints
both on its output line. Nothing else is repaired: a page that is not UTF-8 (OAI-PMH 2.0 §3.2 requires UTF-8), a
character REFERENCE to an illegal character, or any other malformation still leaves the page unparseable, and the
walk stops INCOMPLETE as before.
"""
import argparse
import csv
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS.parent / "phase4" / "qc" / "litkb_eartharxiv_map.csv"
OAI = "https://eartharxiv.org/api/oai/"
#: EarthArXiv's own DOI prefix (survey A3 "10.31223 -> EarthArXiv").
PREPRINT_PREFIX = "10.31223/"
_DOI = re.compile(r"10\.[0-9]{4,9}/[^\s\"<>]+")


def _local(tag):
    return re.sub(r"^\{[^}]*\}", "", tag or "")


def parse_page(xml_bytes):
    """One ListRecords page -> (rows, resumption token or ''). Rows carry stage_a.EARTHARXIV_COLUMNS."""
    from litkb import identifiers as I

    root = ET.fromstring(xml_bytes)
    rows, token = [], ""
    for el in root.iter():
        if _local(el.tag) == "resumptionToken":
            token = (el.text or "").strip()
    for rec in (e for e in root.iter() if _local(e.tag) == "record"):
        oai_id = next((x.text or "" for x in rec.iter() if _local(x.tag) == "identifier" and
                       (x.text or "").startswith("oai:")), "")
        stamp = next((x.text or "" for x in rec.iter() if _local(x.tag) == "datestamp"), "")
        values = [(x.text or "").strip() for x in rec.iter()
                  if _local(x.tag) in ("identifier", "relation", "source") and x.text]
        rights = next((x.text or "" for x in rec.iter() if _local(x.tag) == "rights"), "")
        dois = []
        for v in values:
            for m in _DOI.findall(v):
                d = I.norm("doi", m)
                if d and d not in dois:
                    dois.append(d)
        pdf = next((v for v in values if v.startswith("http") and ("/download" in v or v.lower().endswith(".pdf"))), "")
        preprint = next((d for d in dois if d.startswith(PREPRINT_PREFIX)), "")
        if not pdf:
            continue
        published = [d for d in dois if d != preprint] or [""]
        for pub in published:
            rows.append({"published_doi": pub, "preprint_doi": preprint, "pdf_url": pdf, "oai_identifier": oai_id,
                         "datestamp": stamp, "rights": rights})
    return rows, token


#: Every character XML 1.0 §2.2's `Char` production excludes: C0 controls but TAB / LF / CR, the surrogates, and
#: U+FFFE / U+FFFF (the class of the MEASURED page-7 defect, a literal U+FFFE — see the module docstring).
XML10_ILLEGAL = re.compile("[^\u0009\u000a\u000d -퟿-�\U00010000-\U0010ffff]")
#: What an illegal character becomes: U+FFFD REPLACEMENT CHARACTER, legal XML, so the repair stays visible.
REPLACEMENT = "�"


def repair_xml10(xml_bytes):
    """-> (bytes, characters replaced). Every XML-1.0-illegal character of a UTF-8 page becomes U+FFFD; a page with
    none, or one that is not UTF-8, comes back unchanged with 0 (never repaired: that is another defect)."""
    try:
        text = (xml_bytes or b"").decode("utf-8")
    except UnicodeDecodeError:
        return xml_bytes, 0
    fixed, n = XML10_ILLEGAL.subn(REPLACEMENT, text)
    return (fixed.encode("utf-8"), n) if n else (xml_bytes, 0)


def oai_error(xml_bytes):
    """The OAI-PMH `<error code=...>` a page carries (OAI-PMH 2.0 §3.6), '' when none; an unparseable page answers
    `unparseable` (a 200 that is not the protocol's XML is not a page of the feed)."""
    try:
        root = ET.fromstring(xml_bytes or b"")
    except ET.ParseError:
        return "unparseable"
    for el in root.iter():
        if _local(el.tag) == "error":
            return (el.get("code") or "").strip() or "error"
    return ""


#: The one OAI-PMH error that is an ANSWER, and only on the first page: the list is empty (OAI-PMH 2.0 §3.6).
EMPTY_LIST = "noRecordsMatch"


def harvest(client=None, pace_s=1.0, max_pages=None):
    """Walk every page. -> (rows, pages asked, last status, complete, repaired). `complete` is True only when the
    last page answered 200 AND carried no resumptionToken: every page of the feed was read. A page carrying an
    OAI-PMH `<error>` (but `noRecordsMatch` on the first page) stops the walk with its URL unread, so it is not
    complete. `repaired` is {"pages": n, "chars": n}: the pages `repair_xml10` changed, and how many characters."""
    from litkb.netutil import Client, Pacer

    client = client or Client(base="")
    pacer = Pacer(interval=pace_s)
    url = OAI + "?" + urllib.parse.urlencode({"verb": "ListRecords", "metadataPrefix": "oai_dc"})
    rows, pages, st = [], 0, 0
    repaired = {"pages": 0, "chars": 0}
    while url and (max_pages is None or pages < max_pages):
        pacer.wait()
        st, _hd, body = client.get(url, accept="application/xml", timeout=120)
        pages += 1
        if st != 200:
            break
        # BEGIN guard: an XML-1.0-illegal character is repaired, counted and printed, never the page refused for it
        body, fixed = repair_xml10(body)
        if fixed:
            repaired["pages"] += 1
            repaired["chars"] += fixed
        # END guard: an XML-1.0-illegal character is repaired, counted and printed, never the page refused for it
        # BEGIN guard: an OAI-PMH error served at 200 stops the walk incomplete
        err = oai_error(body)
        if err and not (err == EMPTY_LIST and pages == 1):
            break
        # END guard: an OAI-PMH error served at 200 stops the walk incomplete
        got, token = parse_page(body)
        rows += got
        url = (OAI + "?" + urllib.parse.urlencode({"verb": "ListRecords", "resumptionToken": token})) if token else ""
    complete = True             # the unguarded default: whatever was read is the map (the partial-map hazard)
    # BEGIN guard: only a complete walk of the OAI feed is the map
    complete = st == 200 and not url
    # END guard: only a complete walk of the OAI feed is the map
    return rows, pages, st, complete, repaired


def run_live(out=OUT, client=None, pace_s=1.0, max_pages=None, printer=print):
    """The live pass: walk the feed; write the map ONLY on a complete walk (else `<out>.partial.csv`). -> exit code.
    The output line always names the pages and characters `repair_xml10` repaired (0 and 0 when none)."""
    rows, pages, st, complete, repaired = harvest(client, pace_s=pace_s, max_pages=max_pages)
    fixed = f"repaired_pages={repaired['pages']} repaired_chars={repaired['chars']}"
    if not complete:
        partial = write(rows, Path(str(out)[:-4] + ".partial.csv" if str(out).endswith(".csv") else f"{out}.partial"))
        printer(f"pages={pages} last_status={st} rows={len(rows)} {fixed} INCOMPLETE: the map was NOT written; the "
                f"rows read so far -> {partial} (no rung reads it)")
        return 1
    path = write(rows, out)
    printer(f"pages={pages} last_status={st} rows={len(rows)} {fixed} complete -> {path}")
    return 0


def write(rows, path=OUT):
    from litkb.acquire.stage_a import EARTHARXIV_COLUMNS

    path = Path(path)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(EARTHARXIV_COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in EARTHARXIV_COLUMNS})
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="walk the OAI feed (otherwise print the plan)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    if not a.live:
        print(f"GET {OAI}?verb=ListRecords&metadataPrefix=oai_dc, then every resumptionToken, 1 s apart -> {a.out}")
        print("(dry run: nothing sent; pass --live)")
        return 0
    return run_live(a.out)


if __name__ == "__main__":
    sys.exit(main())
