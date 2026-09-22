"""litkb acquisition probe 5 (read-only): WHAT DOES KAM'S ELSEVIER KEY BUY? One request per endpoint per test DOI,
recording the HTTP status and the X-ELS-Status header Elsevier uses to say why. Bodies are never saved (a PDF request
carries Range: bytes=0-2047 and only the %PDF check is kept). The key is read from the untracked secrets folder; with
no key file the instrument writes one `key-missing` row and exits 0.

Endpoints: Scopus Search (a default individual key's entitlement), ScienceDirect Search v2, Article Metadata search,
Article Retrieval at view=META / META_ABS / FULL, and Article Retrieval as PDF. Test DOIs: one gold open-access, one
bronze, one closed Elsevier article, all from litkb's own no-file rows (OpenAlex oa_status measured 2026-09-22).

Writes phase4/qc/litkb_acq_probe_elsevier_key.csv. First run 2026-09-22, within the hour of the key's placement:
the key was VALID (Scopus Search 200) and refused by every ScienceDirect endpoint at the key-configuration level.
"""
import csv
import datetime as dt
import json
import pathlib
import urllib.error
import urllib.request

OUT = pathlib.Path(__file__).resolve().parents[3] / "phase4" / "qc" / "litkb_acq_probe_elsevier_key.csv"
KEY_FILE = pathlib.Path(r"D:\edmonds-pipeline\secrets\Elsevier_key.txt")
UA = "litkb-probe/0.1 (mailto:chillozone1@gmail.com)"
DOIS = [  # doi, pii, OpenAlex oa_status (2026-09-22)
    ("10.1016/j.jag.2022.102806", "S1569843222000085", "gold"),
    ("10.1016/j.rse.2019.111261", "S0034425719302809", "bronze"),
    ("10.1016/j.rse.2010.07.008", "", "closed"),
]
COLS = ["ts_utc", "endpoint", "doi", "oa_status_openalex", "http_status", "x_els_status", "content_type", "bytes_seen", "starts_pdf"]


def call(key, url, method="GET", data=None, accept="application/json", rng=None):
    headers = {"X-ELS-APIKey": key, "Accept": accept, "User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if rng:
        headers["Range"] = rng
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            head = r.read(2048)
            return r.status, r.headers.get("X-ELS-Status") or "", r.headers.get("Content-Type") or "", len(head), head[:4] == b"%PDF"
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("X-ELS-Status") or "", e.headers.get("Content-Type") or "", 0, False
    except Exception as exc:  # noqa: BLE001 - a probe records the failure, never raises
        return -1, f"exception: {type(exc).__name__}", "", 0, False


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    if not KEY_FILE.exists():
        rows.append(dict(ts_utc=ts, endpoint="key-missing", doi="", oa_status_openalex="", http_status="", x_els_status="", content_type="", bytes_seen=0, starts_pdf=""))
    else:
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        for doi, pii, oa in DOIS:
            probes = [
                ("scopus-search", f"https://api.elsevier.com/content/search/scopus?query=DOI({doi})", "GET", None, "application/json", None),
                ("sciencedirect-search-v2", "https://api.elsevier.com/content/search/sciencedirect", "PUT",
                 json.dumps({"qs": doi, "display": {"show": 3}}).encode(), "application/json", None),
                ("article-metadata-search", f"https://api.elsevier.com/content/metadata/article?query=DOI({doi})", "GET", None, "application/json", None),
                ("article-view-META", f"https://api.elsevier.com/content/article/doi/{doi}?view=META", "GET", None, "application/json", None),
                ("article-view-META_ABS", f"https://api.elsevier.com/content/article/doi/{doi}?view=META_ABS", "GET", None, "application/json", None),
                ("article-view-FULL", f"https://api.elsevier.com/content/article/doi/{doi}?view=FULL", "GET", None, "application/json", None),
                ("article-pdf", f"https://api.elsevier.com/content/article/doi/{doi}", "GET", None, "application/pdf", "bytes=0-2047"),
            ]
            if pii:
                probes.append(("article-pii-pdf", f"https://api.elsevier.com/content/article/pii/{pii}?httpAccept=application/pdf", "GET", None, "application/pdf", "bytes=0-2047"))
            for name, url, method, data, accept, rng in probes:
                status, els, ctype, nbytes, is_pdf = call(key, url, method, data, accept, rng)
                rows.append(dict(ts_utc=ts, endpoint=name, doi=doi, oa_status_openalex=oa, http_status=status, x_els_status=els[:120],
                                 content_type=ctype[:60], bytes_seen=nbytes, starts_pdf=is_pdf))
                print(f"{name:26s} {doi:32s} {oa:7s} HTTP {status} {els[:90]}")
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    ok = sum(1 for r in rows if r["http_status"] == 200)
    print(f"rows={len(rows)} http_200={ok} -> {OUT}")


if __name__ == "__main__":
    main()
