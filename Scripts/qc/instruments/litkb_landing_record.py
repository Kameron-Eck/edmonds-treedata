"""Record each Stage C rule's EXAMPLE PAGE as a regression fixture (S4.5 builder-C2b; survey C4 / C4-RG: "every rule
carries its own example_page, so the table is its own regression suite").

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_landing_record.py            # dry run: what it would GET
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_landing_record.py --live [--only mdpi,iop] [--rerecord]

For every rule of pipeline/litkb/acquire/landing_rules.json whose `example.doi` is set, ONE landing page: the rung's
own `litkb.acquire.landing.walk` from `https://doi.org/<doi>` with the rung's own page Accept, through a real
`litkb.netutil.Client` (the ladder's one socket path), every hop kept — the redirects and a meta refresh are how
the page is reached, and the rung makes exactly these requests. Nothing else is fetched: no PDF, no Range probe, no
candidate (the builder's network grant: "one GET of one real landing page per publisher rule").

Written under qc/fixtures/litkb_landing_pages/<rule id>/ (`binary` in the repo-root .gitattributes):
  recording.json   what was asked and what came back per hop (status, headers minus Set-Cookie, body file,
                   length, sha256), the rung's verdict on the final page, and the grant it was made under
  hop<N>.body      the bytes each hop served, exactly (after the registered-secret scrub, which the recording
                   says it applied: litkb.cassette.scrub_bytes / scrub_url — the same scrub the cassette uses)
An existing recording is never overwritten without --rerecord. The tests read these files through
qc/instruments/litkb_hardening_c2b.py's `load_recording`, which re-checks every body's sha256.
"""
import argparse
import datetime
import hashlib
import json
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS / "qc" / "fixtures" / "litkb_landing_pages"
GRANT = ("brief-C2b-stage-c.md item 2 (S4.5, 2026-09-23): one GET of one real landing page per publisher rule, a "
         "DOI of that publisher from the corpus; nothing else")
#: seconds between two rules' pages (the hosts differ; doi.org is asked once per rule). The ladder's own Pacer
#: default is 3.0 s (litkb.acquire.run.acquire's `Pacer(interval=3.0)`); the same here.
GAP_S = 3.0
#: response headers never written: a session credential is not a fixture
DROP_HEADERS = ("set-cookie",)

# ── the client-address scrub ─────────────────────────────────────────────────────────────────
# MEASURED on the first recording (2026-09-23): three hosts ECHO the recording machine's public address back —
# Elsevier's linkinghub page and ScienceDirect's error page in plain text, and IOP's bot manager (Radware) inside
# base64 twice: a redirect parameter that is the address alone, and a script variable that ends with it after
# other text. The fixtures are TRACKED, so the address must not reach them in any of those forms. The recorder
# never learns the address from a lookup (that would be a request outside the grant) and never writes it anywhere:
# it infers it from the recording itself — a public IPv4 literal that two different hosts echo, or one found inside
# a base64 token — plus any `--client-ip` given, and masks every form it can see.
import base64 as _b64  # noqa: E402
import ipaddress as _ip  # noqa: E402
import re as _re  # noqa: E402

_IPV4 = _re.compile(rb"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
_B64_TOKEN = _re.compile(rb"[A-Za-z0-9+/_-]{12,}={0,2}")
IP_MASK = b"<CLIENT-IP>"
B64_MASK = b"<CLIENT-IP-B64>"
# MEASURED by auditor-C2b (F9, 2026-09-23): Cambridge Core's server-rendered page state names OTHER visitors'
# addresses under "remoteAddress" — four in cambridge/hop3.body, none of them the recording machine's (their
# currentTime stamps precede the recording), so neither rule above sees them. A public address a page names under an
# ADDRESS KEY is masked whoever's it is: remoteAddress / remoteAddr / clientIp / ipAddress / x-forwarded-for /
# x-real-ip, as `key":"v"`, `key: 'v'` or `key=v`, IPv4 or IPv6.
_KEYED_IP = _re.compile(rb"(?i)((?:remote_?addr(?:ess)?|client_?ip|ip_?address|x-forwarded-for|x-real-ip)"
                        rb"[\"']?\s*[:=]\s*[\"']?)([0-9a-f:.]{2,45})(?![0-9a-z:.])")
KEYED_MASK = b"<PAGE-IP>"


def _public(ip):
    try:
        return _ip.ip_address(ip.decode("ascii") if isinstance(ip, bytes) else ip).is_global
    except ValueError:
        return False


def _decodes(tok):
    """A base64 token's decoding, or b'' — and b'' for decoded MARKUP too: an inline SVG's path data is dotted
    numbers that read as addresses (MEASURED: the first version of this scrub masked three decorative
    data:image/svg+xml icons — two in elsevier/hop3.body, one in cambridge/hop3.body — for that reason)."""
    t = tok.rstrip(b"=")
    for fn in (_b64.b64decode, _b64.urlsafe_b64decode):
        try:
            out = fn(t + b"=" * (-len(t) % 4))
        except Exception:        # noqa: BLE001 - not base64 is the common answer
            continue
        return b"" if out.lstrip()[:1] == b"<" or b"<svg" in out[:512].lower() else out
    return b""


def client_ips(blobs, given=()):
    """The addresses to mask (bytes): every `given` one; a public IPv4 literal found in the answers of two or more
    DIFFERENT hosts; and a public IPv4 found inside a base64 token. `blobs` is [(host, bytes)]."""
    seen = {}
    out = {g.encode("ascii") for g in given if g}
    for host, data in blobs:
        for m in _IPV4.finditer(data or b""):
            if _public(m.group(1)):
                seen.setdefault(m.group(1), set()).add(host)
        for tok in _B64_TOKEN.findall(data or b""):
            for m in _IPV4.finditer(_decodes(tok)):
                if _public(m.group(1)):
                    out.add(m.group(1))
    out |= {ip for ip, hosts in seen.items() if len(hosts) >= 2}
    return out


def scrub_ips(data, ips):
    """-> (bytes, changed): every literal of `ips` masked, every public address a page names under an address key
    (`_KEYED_IP`, whoever's it is), and every base64 token whose decoding holds one of `ips`."""
    if not data:
        return data, False
    out = data
    for ip in ips or ():
        out = _re.sub(rb"(?<![\d.])" + _re.escape(ip) + rb"(?![\d.])", IP_MASK, out)
    # BEGIN guard: a public address a page names under an address key is masked, whoever's it is
    out = _KEYED_IP.sub(lambda m: m.group(1) + KEYED_MASK if _public(m.group(2)) else m.group(0), out)
    # END guard: a public address a page names under an address key is masked, whoever's it is

    def tok(m):
        dec = _decodes(m.group(0))
        return B64_MASK if any(ip in dec for ip in ips) else m.group(0)
    if ips:
        out = _B64_TOKEN.sub(tok, out)
    return out, out != data


def _scrub_text(s, ips):
    got, _ = scrub_ips(str(s).encode("utf-8"), ips)
    return got.decode("utf-8")


class RecordingClient:
    """Wraps a real netutil.Client and keeps every (request, response) it made, in order."""

    def __init__(self, client):
        self.client, self.log = client, []

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        st, hd, body = self.client.get(url, accept=accept, timeout=timeout, follow=follow, data=data, headers=headers)
        self.log.append({"url": url, "accept": accept, "follow": follow, "headers": dict(headers or {}),
                         "status": int(st or 0), "response_headers": dict(hd or {}), "body": body or b""})
        return st, hd, body


def _write(d, rule, doi, log, final_hop, verdict, why, ips, recorded_at, ua, urls_scrubbed=False):
    """Scrub (registered secrets, then the client address) and write one recording. -> the recording dict.
    `urls_scrubbed`: the URLs and header values come from a recording already written (a rescrub), so the cassette's
    URL scrub is NOT applied again - litkb.cassette.scrub_url is not idempotent on its own output (a masked `key=<KEY>`
    becomes `key=<KEY><KEY>`: its value class stops at `<`); repeated masks are collapsed either way."""
    import re as _r

    from litkb import cassette as CAS

    def url_scrub(v):
        out = str(v) if urls_scrubbed else CAS.scrub_url(str(v))
        return _r.sub(r"(?:<KEY>)+", "<KEY>", out)
    rows = []
    for n, e in enumerate(log):
        body, s1 = CAS.scrub_bytes(e["body"])
        s2 = False
        # BEGIN guard: a recorded body carries no client address
        body, s2 = scrub_ips(body, ips)
        # END guard: a recorded body carries no client address
        name = f"hop{n}.body"
        (d / name).write_bytes(body)

        def clean(v):
            return _scrub_text(url_scrub(v), ips)
        rows.append({"n": n, "request": {"url": clean(e["url"]), "accept": e["accept"], "follow": e["follow"],
                                         "headers": {k: clean(v) for k, v in e["headers"].items()}},
                     "response": {"status": e["status"],
                                  "headers": {k: clean(v) for k, v in e["response_headers"].items()
                                              if str(k).lower() not in DROP_HEADERS},
                                  "body_file": name, "length": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                                  # read off the content, so a second pass over a scrubbed body still says so
                                  "scrubbed": bool(s1 or s2 or any(m in body for m in (IP_MASK, B64_MASK, KEYED_MASK,
                                                                                       CAS.MASK.encode())))}})
    rec = {"kind": "litkb-landing-recording", "version": 1, "rule": rule["id"], "doi": doi,
           "work_key": rule["example"].get("work_key"), "recorded_at": recorded_at,
           "client": {"class": "litkb.netutil.Client", "user_agent": ua}, "grant": GRANT,
           "scrub": "litkb.cassette.scrub_bytes / scrub_url (registered secrets), then the client-address mask of "
                    "qc/instruments/litkb_landing_record.py (client_ips / scrub_ips); a scrubbed body's sha256 is "
                    "of the bytes as written",
           "walk": {"accept": _page_accept(), "max_hops": _max_hops(), "meta_refresh": True},
           "hops": rows, "final": {"url": _scrub_text(url_scrub(final_hop["url"]), ips),
                                   "status": final_hop["status"], "verdict": verdict, "why": why}}
    (d / "recording.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                      newline="\n")
    return rec


def _page_accept():
    from litkb.acquire import landing as L
    return L.PAGE_ACCEPT


def _max_hops():
    from litkb.acquire import landing as L
    return L.MAX_HOPS


def _blobs(log):
    out = []
    for e in log:
        host = _host(e["url"])
        out.append((host, e["body"]))
        out.append((host, str(e["url"]).encode("utf-8")))
        out += [(host, str(v).encode("utf-8")) for v in e["response_headers"].values()]
    return out


def _host(url):
    import urllib.parse
    return (urllib.parse.urlsplit(str(url)).hostname or "").lower()


def record_rule(rule, *, client_factory=None, out_root=OUT, given_ips=()):
    """-> the recording dict written for one rule (and its bodies)."""
    from litkb.acquire import landing as L
    from litkb.netutil import UA, Client

    doi = rule["example"]["doi"]
    rc = RecordingClient((client_factory or Client)())
    hops = L.walk(rc, L.doi_url(doi), accept=L.PAGE_ACCEPT, timeout=L.PAGE_TIMEOUT_S)
    d = out_root / rule["id"]
    d.mkdir(parents=True, exist_ok=True)
    final = hops[-1]
    verdict, why = ("unexpected", f"guard 9: {final.refused}") if final.refused else L.classify(
        final.status, final.headers, final.body, final.url, rules=L.rules_for(doi, [h.url for h in hops]),
        purpose="page", chain=[h.url for h in hops])
    ips = client_ips(_blobs(rc.log), given_ips)
    return _write(d, rule, doi, rc.log, {"url": final.url, "status": final.status}, verdict,
                  _scrub_text(why, ips), ips, datetime.datetime.now(datetime.timezone.utc).isoformat(), UA)


def rescrub(rule_id, *, out_root=OUT, given_ips=()):
    """Re-apply the scrub to a recording ALREADY on disk (no request): read its hops back, scrub, re-hash, rewrite.
    -> (the recording dict, the number of addresses masked)."""
    d = out_root / rule_id
    old = json.loads((d / "recording.json").read_text(encoding="utf-8"))
    log = []
    for h in old["hops"]:
        log.append({"url": h["request"]["url"], "accept": h["request"]["accept"], "follow": h["request"]["follow"],
                    "headers": h["request"]["headers"], "status": h["response"]["status"],
                    "response_headers": h["response"]["headers"], "body": (d / h["response"]["body_file"]).read_bytes()})
    ips = client_ips(_blobs(log), given_ips)
    rule = {"id": rule_id, "example": {"work_key": old.get("work_key")}}
    f = old["final"]
    rec = _write(d, rule, old["doi"], log, {"url": f["url"], "status": f["status"]}, f["verdict"],
                 _scrub_text(f["why"], ips), ips, old["recorded_at"], old["client"]["user_agent"], urls_scrubbed=True)
    return rec, len(ips)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="make the requests (default: a dry run that makes none)")
    ap.add_argument("--only", default="", help="comma-separated rule ids")
    ap.add_argument("--rerecord", action="store_true", help="overwrite an existing recording")
    ap.add_argument("--rescrub", action="store_true",
                    help="re-apply the scrub to the recordings on disk (no request is made)")
    ap.add_argument("--client-ip", action="append", default=[],
                    help="an address to mask besides the ones inferred (never written anywhere)")
    a = ap.parse_args(argv)
    from litkb.acquire import landing as L

    only = {x.strip() for x in a.only.split(",") if x.strip()}
    rules = [r for r in L.TABLE["rules"] if (r.get("example") or {}).get("doi") and (not only or r["id"] in only)]
    if a.rescrub:
        for rule in rules:
            if (OUT / rule["id"] / "recording.json").exists():
                rec, n = rescrub(rule["id"], given_ips=a.client_ip)
                changed = sum(1 for h in rec["hops"] if h["response"]["scrubbed"])
                print(f"{rule['id']}: rescrubbed, {n} address(es) masked, {changed} hop body(ies) changed")
        return 0
    first = True
    for rule in rules:
        target = OUT / rule["id"] / "recording.json"
        if target.exists() and not a.rerecord:
            print(f"{rule['id']}: recorded already ({target.relative_to(SCRIPTS)}); --rerecord to replace")
            continue
        if not a.live:
            print(f"{rule['id']}: would GET {L.doi_url(rule['example']['doi'])} and follow its redirects")
            continue
        if not first:
            time.sleep(GAP_S)
        first = False
        rec = record_rule(rule, given_ips=a.client_ip)
        f = rec["final"]
        print(f"{rule['id']}: {len(rec['hops'])} hop(s), final {f['status']} {f['url']} -> {f['verdict']} ({f['why']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
