"""litkb acquisition probe 4 (read-only): IDENTIFIER CROSSWALK YIELD. For every DOI-bearing work in main, ask
OpenAlex (ids: openalex, pmid, pmcid, mag), Semantic Scholar (externalIds: ArXiv, PubMed, PubMedCentral, MAG,
CorpusId, DBLP) and Crossref (ISBN, alternative-id, relation types) and record which identifiers the corpus would
GAIN per scheme — the measured yield of a metadata fan-out for identifier coverage, against litkb's own table where
only doi, arxiv and url are populated today. Metadata calls only; nothing downloaded.

Writes phase4/qc/litkb_acq_probe_crosswalk.csv (one row per work) and prints a per-scheme gain summary.
First run 2026-09-22 (survey round 3).
"""
import collections
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "litkb_acq_probe_crosswalk.csv"
UA = "litkb-probe/0.1 (mailto:chillozone1@gmail.com)"


def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:  # noqa: BLE001 - a probe records the failure, never raises
        return -1, None


def openalex(doi):
    s, d = get_json(f"https://api.openalex.org/works/doi:{doi}?mailto=chillozone1@gmail.com&select=ids,type,primary_location")
    if s != 200 or not d:
        return s, {}
    ids = d.get("ids") or {}
    out = {"openalex": (ids.get("openalex") or "").rsplit("/", 1)[-1], "pmid": (ids.get("pmid") or "").rsplit("/", 1)[-1],
           "pmcid": (ids.get("pmcid") or "").rsplit("/", 1)[-1], "mag": str(ids.get("mag") or ""), "oa_type": d.get("type") or ""}
    src = ((d.get("primary_location") or {}).get("source") or {})
    out["issn_l"] = src.get("issn_l") or ""
    return s, out


def s2(doi):
    s, d = get_json(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=externalIds")
    if s != 200 or not d:
        return s, {}
    e = d.get("externalIds") or {}
    return s, {"s2_corpus": str(e.get("CorpusId") or ""), "s2_arxiv": e.get("ArXiv") or "", "s2_pmid": str(e.get("PubMed") or ""),
               "s2_pmcid": e.get("PubMedCentral") or "", "s2_mag": str(e.get("MAG") or ""), "s2_dblp": e.get("DBLP") or "", "s2_acl": e.get("ACL") or ""}


def crossref(doi):
    s, d = get_json(f"https://api.crossref.org/works/{doi}")
    if s != 200 or not d:
        return s, {}
    m = d.get("message") or {}
    rel = m.get("relation") or {}
    return s, {"cr_type": m.get("type") or "", "cr_isbn": ";".join(m.get("ISBN") or []), "cr_issn": ";".join(m.get("ISSN") or []),
               "cr_alt_id": ";".join(m.get("alternative-id") or [])[:80], "cr_relation_types": ";".join(sorted(rel.keys())),
               "cr_has_link": "1" if m.get("link") else ""}


def main():
    c = psycopg.connect("host=localhost port=5433 dbname=litkb user=litkb_reader")
    rows = c.execute("""SELECT w.key, i.value FROM litkb.main_identifiers i JOIN litkb.main_works w ON w.work_id=i.work_id
                        WHERE i.scheme='doi' AND i.active ORDER BY 1""").fetchall()
    have = collections.defaultdict(set)
    for scheme, key in c.execute("SELECT i.scheme, w.key FROM litkb.main_identifiers i JOIN litkb.main_works w ON w.work_id=i.work_id WHERE i.active").fetchall():
        have[scheme].add(key)
    print(len(rows), "DOI-bearing works; schemes populated today:", {k: len(v) for k, v in have.items()}, file=sys.stderr)
    cols = ["key", "doi", "openalex_status", "openalex", "pmid", "pmcid", "mag", "oa_type", "issn_l", "s2_status", "s2_corpus", "s2_arxiv",
            "s2_pmid", "s2_pmcid", "s2_mag", "s2_dblp", "s2_acl", "cr_status", "cr_type", "cr_isbn", "cr_issn", "cr_alt_id", "cr_relation_types", "cr_has_link"]
    gain = collections.Counter()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i, (key, doi) in enumerate(rows, 1):
            so, oa = openalex(doi)
            time.sleep(0.15)
            ss, s2d = s2(doi)
            time.sleep(1.2)
            sc, cr = crossref(doi)
            time.sleep(0.3)
            row = {"key": key, "doi": doi, "openalex_status": so, "s2_status": ss, "cr_status": sc, **oa, **s2d, **cr}
            w.writerow({k: row.get(k, "") for k in cols})
            f.flush()
            for scheme, val in (("openalex", oa.get("openalex")), ("pmid", oa.get("pmid") or s2d.get("s2_pmid")), ("pmcid", oa.get("pmcid") or s2d.get("s2_pmcid")),
                                ("mag", oa.get("mag") or s2d.get("s2_mag")), ("s2", s2d.get("s2_corpus")), ("arxiv", s2d.get("s2_arxiv")),
                                ("dblp", s2d.get("s2_dblp")), ("isbn", cr.get("cr_isbn")), ("issn", cr.get("cr_issn") or oa.get("issn_l")),
                                ("relation", cr.get("cr_relation_types"))):
                if val and key not in have.get(scheme, set()):
                    gain[scheme] += 1
            if i % 25 == 0:
                print(f"{i}/{len(rows)} gain so far {dict(gain)}", file=sys.stderr)
    print(f"works_probed={len(rows)} new_identifiers_per_scheme={dict(sorted(gain.items()))} -> {OUT}")


if __name__ == "__main__":
    main()
