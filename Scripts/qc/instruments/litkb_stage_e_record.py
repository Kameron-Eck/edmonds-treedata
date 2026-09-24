r"""Record Stage E's fixtures ONCE, through builder A's cassette in RECORD mode (S4.5 builder-C2c; plan "### S4.5"
item 6). The only network this builder was granted, by name and host (brief-C2c-scihub-stage-e.md item 5):

  * the Wayback availability + CDX answers for the two URLs the plan names — the census.gov copy it names for
    10.1002/wics.1317 (the plan's E1 POSITIVE) and the IIASA copy of 10.5067/doc/ceoswgcv/lpv/lc.001 (the plan's E1
    NEGATIVE, "never archived") — and, for the census row, the captures the E1 rung fetches: with its raw-bytes
    modifier (`id_`), with `if_`, and WITHOUT one (the wrapper page the survey says a bare capture URL serves; the
    recording of 2026-09-23 found the SAME PDF there instead, and the IIASA copy archived — the fixture's
    provenance.json). What the recording showed RE-GRADES both rows (`litkb_hardening_c2c.WAYBACK_ROWS`): the
    census capture is another work than 10.1002/wics.1317, and the IIASA copy is E1's real positive;
  * ONE Internet Archive item search for the census row's DOI;
  * ONE Common Crawl index query for the census URL (plus the crawl list it is asked against, collinfo.json —
    the E5 rung's first request; named in the builder report as a reading of the grant).

Nothing else: the IA search's hits are not opened and a Common Crawl capture is not fetched (the WARC range and
the IA metadata/download steps are tested on CONSTRUCTED inputs).

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_stage_e_record.py --live [--out DIR]

`--live` is required: without it the script prints the plan and sends nothing. The index lands in
`qc/fixtures/litkb_cassettes/stage_e/index.jsonl` (tracked; `.gitattributes` marks the cassette tree `binary`)
and every body above the inline limit or starting `%PDF-` in `bodies/` beside it (litkb.cassette's store layout).
The PDF body is a U.S. Census Bureau research report (a work of the U.S. federal government), which is why it may
sit in the repository beside its index where a publisher's article may not (litkb.cassette's module docstring).
"""
import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS / "qc" / "fixtures" / "litkb_cassettes" / "stage_e"


def _c2c():
    """The rows and cassette names have ONE home, the C2c counter module (loaded by path: qc/instruments is not a
    package)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("litkb_hardening_c2c",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_hardening_c2c.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C2C = _c2c()
CENSUS_DOI, CENSUS_URL, IIASA_URL = C2C.CENSUS_DOI, C2C.CENSUS_URL, C2C.IIASA_URL
CENSUS_ROW_WORK = C2C.CENSUS_ROW_WORK
ROW_CENSUS, ROW_CENSUS_NO_RAW, ROW_CENSUS_IF = C2C.ROW_CENSUS, C2C.ROW_CENSUS_NO_RAW, C2C.ROW_CENSUS_IF
ROW_IIASA, ROW_IA, ROW_COMMONCRAWL = C2C.ROW_IIASA, C2C.ROW_IA, C2C.ROW_COMMONCRAWL

#: Seconds between two requests (politeness to archive.org; the ladder's own default pacer interval is 3.0 s,
#: litkb.acquire.run.acquire).
PACE_S = 3.0


def plan():
    return [
        (ROW_CENSUS, "E1 rung on the census.gov URL: availability, then the capture with id_ (then if_ / CDX only "
                       "if the rung needs them)"),
        (ROW_CENSUS_NO_RAW, "E1 rung with RAW_MODIFIERS=('',): availability, the wrapper page, CDX, a second "
                              "capture's wrapper (the known-bad's requests)"),
        (ROW_CENSUS_IF, "the availability capture fetched with if_ (the second raw modifier)"),
        (ROW_IIASA, "E1 rung on the IIASA URL: availability, CDX"),
        (ROW_IA, "ONE advancedsearch request for the positive work"),
        (ROW_COMMONCRAWL, "collinfo.json, then ONE index query (the newest crawl) for the census.gov URL"),
    ]


def record(out_dir):
    from litkb import cassette as CAS
    from litkb.acquire import commoncrawl, ia, wayback
    from litkb.netutil import Client, Pacer

    out_dir = Path(out_dir)
    index = out_dir / "index.jsonl"
    if index.exists():
        raise SystemExit(f"{index} exists: a recording is made once (move it aside to re-record)")
    cas = CAS.Cassette(index, "record", bodies=out_dir / "bodies")
    pacer = Pacer(interval=PACE_S)
    results = {}
    with CAS.use(cas):
        client = Client(base="")
        cas.begin_row(ROW_CENSUS)
        r = wayback.fetch_wayback([CENSUS_URL], client, pacer=pacer)
        results[ROW_CENSUS] = {k: r.get(k) for k in ("status", "sub_status", "tried", "http_codes")}
        snap_ts = next((t.split()[1].split("id_")[0] for t in r.get("tried") or [] if t.startswith("capture ")),
                       None)

        cas.begin_row(ROW_CENSUS_NO_RAW)
        saved = wayback.RAW_MODIFIERS
        wayback.RAW_MODIFIERS = ("",)
        try:
            r = wayback.fetch_wayback([CENSUS_URL], Client(base=""), pacer=pacer)
        finally:
            wayback.RAW_MODIFIERS = saved
        results[ROW_CENSUS_NO_RAW] = {k: r.get(k) for k in ("status", "sub_status", "tried", "http_codes")}

        cas.begin_row(ROW_CENSUS_IF)
        if snap_ts:
            pacer.wait()
            st, _hd, body = Client(base="").get(wayback.capture_url(snap_ts, CENSUS_URL, "if_"),
                                                accept=wayback.PDF_ACCEPT)
            results[ROW_CENSUS_IF] = {"status_code": st, "bytes": len(body or b""),
                                        "pdf": (body or b"")[:5] == b"%PDF-"}
        else:
            results[ROW_CENSUS_IF] = {"skipped": "the E1 rung fetched no capture"}

        cas.begin_row(ROW_IIASA)
        r = wayback.fetch_wayback([IIASA_URL], Client(base=""), pacer=pacer)
        results[ROW_IIASA] = {k: r.get(k) for k in ("status", "sub_status", "tried", "http_codes")}

        cas.begin_row(ROW_IA)
        pacer.wait()
        st, _hd, body = Client(base="").get(ia.search_url(CENSUS_ROW_WORK), accept="application/json")
        hits = ia.parse_search(body)
        results[ROW_IA] = {"status_code": st, "hits": len(hits),
                           "identified": [h.get("identifier") for h in hits if ia.identified(h, CENSUS_ROW_WORK)]}

        cas.begin_row(ROW_COMMONCRAWL)
        cc = Client(base="")
        pacer.wait()
        st, _hd, body = cc.get(commoncrawl.COLLINFO, accept="application/json")
        crawls = commoncrawl.parse_collinfo(body) if st == 200 else []
        results[ROW_COMMONCRAWL] = {"collinfo_status": st, "crawls": len(crawls)}
        if crawls:
            pacer.wait()
            st, _hd, body = cc.get(commoncrawl.index_url(crawls[0], CENSUS_URL), accept="application/json")
            caps = commoncrawl.parse_index(body) if st == 200 else []
            results[ROW_COMMONCRAWL].update({"index": crawls[0], "index_status": st, "captures": len(caps),
                                             "pdf_captures": sum(1 for c in caps if commoncrawl.is_pdf_capture(c))})
    return {"index": str(index), "recorded": len(cas.recorded), "results": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="send the granted requests (otherwise print the plan)")
    ap.add_argument("--out", default=str(OUT), help="the cassette directory (index.jsonl + bodies/)")
    a = ap.parse_args(argv)
    if not a.live:
        for row, what in plan():
            print(f"{row}: {what}")
        print("(dry run: nothing sent; pass --live to record)")
        return 0
    out = record(a.out)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
