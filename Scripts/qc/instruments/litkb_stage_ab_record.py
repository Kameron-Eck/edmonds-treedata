r"""Record Stage A/B's fixtures ONCE, through builder A's cassette in RECORD mode (S4.5 builder-C2a;
LITKB_WORKPLAN.md "### S4.5" items 3-4). The only network this builder was granted, by name and host
(brief-C2a-stage-ab.md item 5):

  * the FREE-PDF rows' Crossref / OpenAlex / Semantic Scholar / arXiv answers — the four DOIs whose
    `phase4/qc/litkb_acq_probe_head.csv` verdict is FREE-PDF (read from the CSV, never listed by hand): the
    three identifier services' records for each (the exact URLs the rungs build: `stage_b.crossref_url`,
    `openalex_url`, `s2_url`), and ONE arXiv request — the PDF at export.arxiv.org of the one FREE-PDF work with
    no file today (Kats_2019; survey-data §2.1), which measures B10's host rewrite. Its body is a paper, so it is
    recorded into a SEPARATE cassette under --pdf-out (untracked scratch), never into the tracked fixture
    (litkb.cassette's rule: a PDF never enters the repository);
  * ONE preprint's native-API answers: the OSF preprint 10.31235/osf.io/cxp4q (DelgadoQuiros_2025, a
    `preprint` with no file — survey-data §2.8), its APIv2 record and its primary-file record — no download;
  * ONE crosswalk arXiv-id work's answers: 10.1145/3534678.3539043 (E13, Pfitzmann_2022; the crosswalk probe
    gives it arXiv 2206.01062 — S4.5 decision D10): its Crossref / OpenAlex / Semantic Scholar records;
  * plus, reported and NOT stored: the ONE read-only probe of NASA ADS's link gateway the brief allows (B15 is
    not built; "it enters the after-S5 table if it answers") — status and redirect host only, no redirect
    followed.

Nothing else: no `link[]`, `pdf_url` or `openAccessPdf` URL a record names is fetched here (those hosts are not in
the grant); the rungs' byte steps are tested on CONSTRUCTED answers.

    cd Scripts
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_stage_ab_record.py --live \
        --pdf-out D:\tools\claude-config\jobs\litkb-s4-5\scratch\builder-C2a\kats_pdf

`--live` is required: without it the script prints the plan and sends nothing. The tracked index lands in
`qc/fixtures/litkb_cassettes/stage_ab/index.jsonl`, bodies above the inline limit in `bodies/` beside it (JSON
metadata only). The contact email (`stage_b.contact_email`) is registered for redaction before any request and
the cassette masks the `mailto`/`email` query values (litkb.cassette SCRUB_PARAMS).
"""
import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
OUT = SCRIPTS / "qc" / "fixtures" / "litkb_cassettes" / "stage_ab"
HEAD_CSV = REPO / "phase4" / "qc" / "litkb_acq_probe_head.csv"

#: The grant's named rows (brief-C2a-stage-ab.md item 5). The FREE-PDF DOIs are READ from the head probe CSV.
PREPRINT_DOI = "10.31235/osf.io/cxp4q"          # DelgadoQuiros_2025, OSF (survey-data §2.8)
CROSSWALK_DOI = "10.1145/3534678.3539043"       # E13, Pfitzmann_2022, arXiv 2206.01062 (decision D10)
KATS_DOI = "10.1007/978-3-030-32248-9_57"       # the one FREE-PDF row with no file (survey-data §2.1)
#: ONE link-gateway request. The bibcode is the one ADS answers for arXiv 1505.04597 in the linkage survey's
#: edge row 34 (VERIFIED live there); EPRINT_PDF is a link type the survey's B15 row names (mosaic's PUB_PDF /
#: EPRINT family). Not followed: only whether the gateway answers is asked.
ADS_GATEWAY = "https://ui.adsabs.harvard.edu/link_gateway/2015arXiv150504597R/EPRINT_PDF"

#: Seconds between two requests: litkb's registry pace (admit/resolver.py REGISTRY_MIN_INTERVAL); arXiv's own
#: 3 s is the rung's pacer (stage_b.pacer_for).
PACE_S = 1.0


def tag(doi):
    return f"c2a:{doi}"


def free_pdf_dois(path=HEAD_CSV):
    with open(path, encoding="utf-8", newline="") as fh:
        return sorted({r["doi"] for r in csv.DictReader(fh) if r.get("verdict") == "FREE-PDF"})


def plan():
    rows = [(tag(d), "Crossref + OpenAlex + Semantic Scholar records") for d in free_pdf_dois()]
    rows.append((tag(CROSSWALK_DOI), "Crossref + OpenAlex + Semantic Scholar records (crosswalk arXiv-id work)"))
    rows.append((tag(PREPRINT_DOI), "OSF APIv2 preprint record + its primary-file record (no download)"))
    rows.append((tag(KATS_DOI) + " (pdf cassette)", "ONE export.arxiv.org PDF request for the arXiv id S2 names"))
    rows.append(("ads", f"ONE GET of {ADS_GATEWAY}, redirects not followed; not stored"))
    return rows


def _ctx():
    from litkb.netutil import Client, Pacer

    class Ctx:
        pass
    c = Ctx()
    c.pacer = Pacer(interval=PACE_S)
    c.clients = {}
    c.work_class = ""
    c.shared = Client(base="")
    return c


def record(out_dir, pdf_out):
    from litkb import cassette as CAS
    from litkb.acquire import stage_b as B
    from litkb.acquire import stage_b_repos as R
    from litkb.netutil import Client

    out_dir, pdf_out = Path(out_dir), Path(pdf_out)
    index = out_dir / "index.jsonl"
    if index.exists():
        raise SystemExit(f"{index} exists: a recording is made once (move it aside to re-record)")
    email = B.contact_email()                        # registered for redaction before any request
    cas = CAS.Cassette(index, "record", bodies=out_dir / "bodies")
    results, kats_arxiv = {}, None
    with CAS.use(cas):
        ctx = _ctx()
        for doi in free_pdf_dois() + [CROSSWALK_DOI]:
            cas.begin_row(tag(doi))
            got = {}
            for route, url in (("crossref-link", B.crossref_url(doi, email)), ("openalex", B.openalex_url(doi, email)),
                               ("s2", B.s2_url({"doi": doi}))):
                st, data, _t = B.get_json(ctx, route, url)
                got[route] = st
                if route == "s2" and isinstance(data, dict):
                    got["s2_arxiv"] = (data.get("externalIds") or {}).get("ArXiv")
                    got["s2_open_access_pdf"] = (data.get("openAccessPdf") or {}).get("url")
                    if doi == KATS_DOI:
                        kats_arxiv = got["s2_arxiv"]
                if route == "openalex" and isinstance(data, dict):
                    got["openalex_pdf_urls"] = [u for u, _m in B.openalex_candidates(data)]
                if route == "crossref-link" and isinstance(data, dict):
                    got["crossref_link_pdfs"] = [u for u, _m in B.link_candidates(data.get("message") or {})]
            results[tag(doi)] = got
        cas.begin_row(tag(PREPRINT_DOI))
        pid = R.osf_id(PREPRINT_DOI)
        st, data, _t = B.get_json(ctx, "osf", R.osf_url(pid), accept="application/vnd.api+json")
        got = {"preprint": st}
        rel = (((data or {}).get("data") or {}).get("relationships") or {}).get("primary_file") or {}
        href = ((rel.get("links") or {}).get("related") or {}).get("href") if isinstance(rel.get("links"), dict) else None
        if href:
            st2, f, _t2 = B.get_json(ctx, "osf", href, accept="application/vnd.api+json")
            got.update({"primary_file": st2, "download_named": bool(((f or {}).get("data") or {}).get("links", {})
                                                                        .get("download"))})
        results[tag(PREPRINT_DOI)] = got
    # the ONE arXiv PDF request, into a SEPARATE, untracked cassette (a PDF never enters the repository)
    if kats_arxiv:
        pcas = CAS.Cassette(pdf_out / "index.jsonl", "record", bodies=pdf_out / "bodies")
        with CAS.use(pcas):
            pcas.begin_row(tag(KATS_DOI))
            st, hd, body, _t = B.get(_ctx(), "arxiv", B.arxiv_pdf(kats_arxiv), accept=B.PDF_ACCEPT,
                                     timeout=B.PDF_TIMEOUT)
        import hashlib

        from litkb.acquire import accept as ACC
        results["kats_pdf"] = {"url": B.arxiv_pdf(kats_arxiv), "status": st,
                               "content_type": {k.lower(): v for k, v in hd.items()}.get("content-type"),
                               "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                               "pdf": ACC.quick_magic(body), "stored_in": str(pdf_out)}
    # the ONE ADS link-gateway probe: status and the redirect's host, nothing stored
    st, hd, _body = Client(base="").get(ADS_GATEWAY, accept="*/*", timeout=60, follow=False)
    loc = {k.lower(): v for k, v in (hd or {}).items()}.get("location", "")
    import urllib.parse

    results["ads_gateway"] = {"url": ADS_GATEWAY, "status": st, "redirect_host": urllib.parse.urlparse(loc).netloc}
    return {"index": str(index), "recorded": len(cas.recorded), "results": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="send the granted requests (otherwise print the plan)")
    ap.add_argument("--out", default=str(OUT), help="the tracked cassette directory (index.jsonl + bodies/)")
    ap.add_argument("--pdf-out", help="an UNTRACKED directory for the one arXiv PDF's cassette (required with --live)")
    a = ap.parse_args(argv)
    if not a.live:
        for row, what in plan():
            print(f"{row}: {what}")
        print("(dry run: nothing sent; pass --live --pdf-out <untracked dir> to record)")
        return 0
    if not a.pdf_out:
        ap.error("--live needs --pdf-out <an untracked directory>: the arXiv PDF never enters the repository")
    print(json.dumps(record(a.out, a.pdf_out), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
