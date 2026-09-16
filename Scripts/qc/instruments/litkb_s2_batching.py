"""Measure the Semantic Scholar leg, before and after, on the SAME references.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_s2_batching.py --arm before
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_s2_batching.py --arm after
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_s2_batching.py --report

The measurement contract (CLAUDE.md 3.4b): this is the instrument; its outputs are
``Reports/litkb_s2_arms_2026-09-15.csv`` and ``…_rows_…``; the finding lives in
``Reports/LITKB_S2_BATCHING_2026-09-15.md``.

THE INPUT IS THE P6 RUN'S OWN OUTPUT, not a fresh extraction: every reference in
``{DERIVED}/p6/references.jsonl`` whose resolution was `unresolved` or `ambiguous` (274 + 19). Same
rows, same order, both arms — the only difference between the arms is the S2 client.

WHAT THE ARMS ARE. `before` is the resolver exactly as P6 ran it: per-reference
`/paper/search?query=…&limit=3`, a single 10 s back-off on a rate-limit answer, and the
`StageBreaker` that trips the stage after two consecutive ones. `after` swaps that stage for
`litkb.admit.s2`: one batch call for the identifier-bearing references, then one
`/paper/search/match` per distinct title, narrow fields, jittered ladder with `Retry-After`
honoured, answers cached on disk. `confirmed` is `after` re-run against the CURRENT tree, in which
"S2 proposes, Crossref confirms" is live: every Semantic Scholar candidate's DOI is looked up at
Crossref and refused unless the Crossref record passes the shared rules and is type-compatible
(`resolver.confirm_s2_candidate`). The `after` arm's saved rows are the paced measurement of
`Reports/LITKB_S2_BATCHING_2026-09-15.md` §3 and are NOT re-runnable on this tree — there is
deliberately no flag that turns the confirmation off, because a flag would make the kill "flip a
default" instead of "delete the guard".

The ACCEPTANCE RULES ARE IDENTICAL in the `before`/`after` pair — DOI-first, the
0.85 ratio filter, the first-author family and the decisions.yaml §15.15 year rule — so a difference
in outcome is a difference in what the registry was asked, never in what was accepted.

WHAT THE WALL CLOCK MEANS. The Crossref leg answers from the P6 disk cache in both arms (those
requests were made yesterday and are on disk), so the wall clock here is dominated by the S2 and
arXiv legs — which is the point. `crossref_network` in the summary is the check on that: it should be
near zero, and if it is not the two arms are not comparable and the report must say so.
"""
import argparse
import collections
import csv
import json
import pathlib
import time

from litkb.admit import s2 as S2
from litkb.extract import references as R
from litkb.netutil import Client, Pacer

SCRIPTS = pathlib.Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
OUT = pathlib.Path(R.DERIVED_ROOT) / "p6"
REPORTS = REPO / "Reports"
ARMS_CSV = REPORTS / "litkb_s2_arms_2026-09-15.csv"
ROWS_CSV = REPORTS / "litkb_s2_rows_2026-09-15.csv"
STATE = pathlib.Path(R.DERIVED_ROOT) / "s2_arms"

#: The reference fields the resolver reads. Carried over verbatim from the P6 rows so neither arm
#: re-parses anything: a difference in parsing would be a difference in the INPUT.
#: `authors`, `journal`, `publisher` and `raw` are carried for the Crossref-confirmation rule
#: (`resolver.confirm_s2_candidate`): the review signature reads the reference's author list and the
#: type-compatibility test reads publisher-and-no-journal. Dropping them would make the confirmed
#: arm refuse on the weaker `crossref_author_mismatch` and never show the named reasons.
REF_FIELDS = ("title", "first_author", "year", "doi", "doi_norm", "arxiv", "ref_key",
              "citing_work_key", "authors", "journal", "publisher", "raw")
RESOLVER_FIELDS = ("title", "first_author", "year", "doi", "doi_norm", "arxiv", "authors",
                   "journal", "publisher", "raw")


class CountingClient:
    """A `netutil.Client` that records every request by host and status. The count is the headline
    number of this measurement, so it is taken at the socket, not inferred from the code path."""

    def __init__(self, inner=None):
        self.inner = inner if inner is not None else Client()
        self.by_host = collections.Counter()
        self.rate_limited = collections.Counter()
        self.statuses = collections.Counter()

    @staticmethod
    def _host(url):
        return url.split("//", 1)[-1].split("/", 1)[0]

    def get(self, url, accept="application/json", timeout=120, **kw):
        h = self._host(url)
        self.by_host[h] += 1
        st, hd, body = self.inner.get(url, accept=accept, timeout=timeout, **kw)
        self.statuses[(h, st)] += 1
        if st in (429, 403):
            self.rate_limited[h] += 1
        return st, hd, body


def refs_under_test():
    """The 274 unresolved + 19 ambiguous P6 rows, in file order."""
    path = OUT / "references.jsonl"
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("resolution") in ("unresolved", "ambiguous"):
                out.append({k: row.get(k) for k in REF_FIELDS})
    return out


def run_arm(arm, refs, limit=None):
    """-> (rows, summary). One resolver pass over `refs`, counted at the socket."""
    net = CountingClient()
    pacer = R.deferred_pacer(Pacer(interval=1.0))
    cached = R.CachedClient(client=net, cache=R.DiskCache(), pacer=pacer)
    breaker = R.StageBreaker()
    s2 = None
    if arm in ("after", "confirmed"):
        # Its OWN client (not the CachedClient): this module does its own versioned caching, and
        # routing it through the URL cache as well would double-count a hit.
        s2 = S2.S2Client(client=net, cache=R.DiskCache(), pacer=Pacer(interval=1.0))
        S2.batch_prefill(refs, s2)
    todo = refs[:limit] if limit else refs
    rows, transient, t0 = [], [], time.time()
    for r in todo:
        ref = {k: v for k, v in r.items() if k in RESOLVER_FIELDS}
        t1 = time.time()
        res = R.resolve_reference(ref, cached, pacer, breaker, s2=s2) if s2 is not None \
            else R.resolve_reference(ref, cached, pacer, breaker)
        rows.append({"arm": arm, "citing_work_key": r["citing_work_key"], "ref_key": r["ref_key"],
                     "title": (r.get("title") or "")[:120], "state": res.state,
                     "doi": res.doi or "", "source": res.source or "",
                     "ratio": res.ratio if res.ratio is not None else "",
                     "reason": res.reason[:220], "seconds": round(time.time() - t1, 3)})
        if res.transient:
            # LOGGED, NEVER PERSISTED. `Resolution.transient` carries what THIS run's breakers did.
            # Writing it into the row is what made the committed artefact differ between two runs
            # over the same cache in 42 of 293 rows with no state and no DOI changed.
            transient.append(f"{r['citing_work_key']}:{r['ref_key']} {res.transient}")
    if transient:
        print(f"[run-dependent, not persisted] {len(transient)} rows skipped a stage: "
              + "; ".join(sorted({t.split(' ', 1)[1] for t in transient})), flush=True)
    wall = time.time() - t0
    states = collections.Counter(x["state"] for x in rows)
    summary = {
        "arm": arm, "references": len(todo), "wall_seconds": round(wall, 1),
        "requests_total": sum(net.by_host.values()),
        "requests_s2": net.by_host["api.semanticscholar.org"],
        "requests_crossref": net.by_host["api.crossref.org"],
        "requests_arxiv": net.by_host["export.arxiv.org"],
        "rate_limited_total": sum(net.rate_limited.values()),
        "rate_limited_s2": net.rate_limited["api.semanticscholar.org"],
        "rate_limited_arxiv": net.rate_limited["export.arxiv.org"],
        "resolved": states["resolved"], "ambiguous": states["ambiguous"],
        "unresolved": states["unresolved"],
        "stages_tripped": ",".join(sorted(breaker.report())) or "-",
        "s2_stats": s2.stats.asdict() if s2 is not None else {},
        "statuses": {f"{h} {st}": n for (h, st), n in sorted(net.statuses.items())},
        "reasons": dict(collections.Counter(
            x["reason"].split(" (")[0].split(";")[0][:60] for x in rows).most_common(12)),
    }
    return rows, summary


def write_arm(arm, rows, summary):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{arm}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2),
                                       encoding="utf-8")
    print(json.dumps(summary, indent=2))


def report():
    """Join the two saved arms into the two tracked CSVs."""
    arms = {}
    for arm in ("before", "after", "confirmed"):
        p = STATE / f"{arm}.json"
        if p.exists():
            arms[arm] = json.loads(p.read_text(encoding="utf-8"))
    if not arms:
        raise SystemExit("no arm has been run")
    keys = ["arm", "references", "wall_seconds", "requests_total", "requests_s2",
            "requests_crossref", "requests_arxiv", "rate_limited_total", "rate_limited_s2",
            "rate_limited_arxiv", "resolved", "ambiguous", "unresolved", "stages_tripped"]
    REPORTS.mkdir(exist_ok=True)
    with open(ARMS_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys + ["s2_stats", "statuses"])
        w.writeheader()
        for arm, data in arms.items():
            s = data["summary"]
            w.writerow({**{k: s.get(k) for k in keys},
                        "s2_stats": json.dumps(s.get("s2_stats") or {}),
                        "statuses": json.dumps(s.get("statuses") or {})})
    seen = set()
    with open(ROWS_CSV, "w", encoding="utf-8", newline="") as fh:
        w = None
        for arm, data in arms.items():
            for row in data["rows"]:
                if w is None:
                    w = csv.DictWriter(fh, fieldnames=list(row))
                    w.writeheader()
                w.writerow(row)
                seen.add((row["citing_work_key"], row["ref_key"]))
    # The change tables: same key, each consecutive pair of arms that were both run.
    for lo, hi in (("before", "after"), ("after", "confirmed")):
        if lo not in arms or hi not in arms:
            continue
        b = {(r["citing_work_key"], r["ref_key"]): r for r in arms[lo]["rows"]}
        a = {(r["citing_work_key"], r["ref_key"]): r for r in arms[hi]["rows"]}
        both = sorted(set(b) & set(a))
        moved = [k for k in both if (b[k]["state"], b[k]["doi"]) != (a[k]["state"], a[k]["doi"])]
        print(f"\n{lo} -> {hi}: {len(both)} references in both arms; "
              f"{len(moved)} changed state or DOI")
        for k in moved:
            print(f"  {k[0]} {k[1]}: {b[k]['state']}({b[k]['doi'] or '-'}) -> "
                  f"{a[k]['state']}({a[k]['doi'] or '-'})  {a[k]['reason'][:110]}")
    print(f"wrote {ARMS_CSV.name}, {ROWS_CSV.name}")


VERIFY_CSV = REPORTS / "litkb_s2_verify_2026-09-15.csv"


def verify():
    """Ask CROSSREF what each newly resolved DOI is, and compare it with the parsed reference.

    The point of the arm table is that 20 references resolved; the point of this rung is that they
    resolved to the RIGHT works. It must not use Semantic Scholar — a registry confirming its own
    answer is not a check (CLAUDE.md 3.4c, "the proposer never scores its own proposal"), so the DOI
    goes to Crossref and the comparison uses the same shared rules the resolver uses.

    A `no` in `verdict` is a row to READ, not a defect count: Crossref carries no author for some
    records, parses a given name as the family for others, and truncates subtitles — all of which
    fail this check without the resolution being wrong. The report names each one.
    """
    from litkb.admit.resolver import family_matches, title_match_ratio
    state = json.loads((STATE / "after.json").read_text(encoding="utf-8"))
    before = {(r["citing_work_key"], r["ref_key"]): r
              for r in json.loads((STATE / "before.json").read_text(encoding="utf-8"))["rows"]}
    src = {}
    with open(OUT / "references.jsonl", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            src[(d["citing_work_key"], d["ref_key"])] = d
    pacer = R.deferred_pacer(Pacer(interval=1.0))
    client = R.CachedClient(cache=R.DiskCache(), pacer=pacer)
    rows = []
    for r in state["rows"]:
        k = (r["citing_work_key"], r["ref_key"])
        if r["state"] != "resolved" or before.get(k, {}).get("state") == "resolved":
            continue
        ref = src[k]
        rec, tried = R.confirm_doi(client, r["doi"], pacer)
        if rec is None:
            rows.append({"citing_work_key": k[0], "ref_key": k[1], "doi": r["doi"],
                         "reference_title": (ref.get("title") or "")[:120], "crossref_title": "",
                         "ratio": "", "crossref_first_author": "",
                         "reference_first_author": ref.get("first_author") or "",
                         "crossref_year": "", "reference_year": ref.get("year"),
                         "verdict": "no", "why": f"not registered ({tried})"})
            continue
        ratio = max(title_match_ratio(ref.get("title") or "", t) for t in rec["titles"])
        fam = family_matches(rec["first_author"], ref.get("first_author") or "")
        rows.append({
            "citing_work_key": k[0], "ref_key": k[1], "doi": r["doi"],
            "reference_title": (ref.get("title") or "")[:120], "crossref_title": rec["title"][:120],
            "ratio": round(ratio, 4), "crossref_first_author": rec["first_author"],
            "reference_first_author": ref.get("first_author") or "",
            "crossref_year": rec["year"], "reference_year": ref.get("year"),
            "verdict": "yes" if (ratio >= 0.85 and fam) else "no",
            "why": "" if (ratio >= 0.85 and fam) else
                   (f"ratio {ratio:.2f}" if ratio < 0.85 else "first author differs")})
    # Fixed column list, not `list(rows[0])`: both branches above write the same keys, and taking
    # them from the first row would raise on every later row the moment the first one is a
    # not-registered DOI.
    cols = ["citing_work_key", "ref_key", "doi", "reference_title", "crossref_title", "ratio",
            "crossref_first_author", "reference_first_author", "crossref_year", "reference_year",
            "verdict", "why"]
    with open(VERIFY_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    yes = sum(1 for r in rows if r["verdict"] == "yes")
    print(f"{yes} of {len(rows)} newly resolved DOIs verify at Crossref; wrote {VERIFY_CSV.name}")
    for r in rows:
        if r["verdict"] == "no":
            print(f"  {r['citing_work_key']} {r['ref_key']} {r['doi']}: {r['why']}")
            print(f"     ref : {r.get('reference_title', '')}")
            print(f"     cref: {r['crossref_title']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", choices=("before", "after", "confirmed"))
    ap.add_argument("--limit", type=int, help="first N references only (a probe, not the measurement)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="ask Crossref what each newly resolved DOI is (independent of S2)")
    a = ap.parse_args(argv)
    if a.arm:
        refs = refs_under_test()
        print(f"{len(refs)} references under test (P6 unresolved + ambiguous)", flush=True)
        rows, summary = run_arm(a.arm, refs, a.limit)
        write_arm(a.arm, rows, summary)
    if a.report:
        report()
    if a.verify:
        verify()
    if not a.arm and not a.report and not a.verify:
        ap.error("--arm, --report or --verify")


if __name__ == "__main__":
    main()
