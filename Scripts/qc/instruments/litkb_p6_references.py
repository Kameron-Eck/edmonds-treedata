"""litkb P6 — run stage 6 (references) over a named paper set and report the measured numbers.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p6_references.py --extract
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p6_references.py --resolve
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p6_references.py --crossref-check
    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p6_references.py --near-miss

The measurement contract (CLAUDE.md 3.4b): this is the instrument; its outputs are the measured
files under ``Reports/`` and the JSONL under the derived root; the findings live in
``Reports/LITKB_REFERENCES_2026-09-15.md``. It writes no database row — P6 is DB-free by design
(the citation columns are applied at merge).

THE PAPER SET IS DERIVED, NOT REMEMBERED (CLAUDE.md "one fact, one home"). :func:`paper_set`
recomputes it from two tracked sources every run: the P4 hard-paper shapes named in
``Reports/LITKB_GROBID_LOCAL_2026-09-14.md`` §4, and a ranking of the manifest's stems by how often
the project's own reports mention them. The 688-page book of the P4 set is deliberately OUT: it
alone carries 1,276 ``<biblStruct>`` and, at the registries' 1 request/s, would be a ~40-minute
resolution run on its own and would dominate every rate in the report.
"""
import argparse
import collections
import csv
import json
import os
import pathlib
import re
import time

from litkb.admit.resolver import RESOLVE_TITLE_RATIO, title_match_ratio
from litkb.extract import grobid
from litkb.extract import references as R
from litkb.netutil import Pacer

SCRIPTS = pathlib.Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
LIT = pathlib.Path(os.environ.get("LITKB_LITERATURE", r"D:\edmonds-pipeline\Literture"))
VALID = LIT / "Validation"
MANIFEST = VALID / "manifest.csv"
BIBLIOS = [REPO / "Reports" / "lit_spatiotemporal_bibliography.csv",
           REPO / "Reports" / "literature_tracker.csv"]
OUT = pathlib.Path(R.DERIVED_ROOT) / "p6"
TEI_DIR = OUT / "tei"
REPORTS = REPO / "Reports"

#: The P4 hard-paper shapes that carry a text layer, from Reports/LITKB_GROBID_LOCAL_2026-09-14.md §4.
#: Schneider_2008 (the 688-page book) is excluded — see the module docstring.
P4_SHAPES = ["Benedek_2015_multilayer-markov-random-field-models",          # two-column
             "Alwan_1988_time-series-modeling-statistical-process",         # two-column, pre-1990
             "Bellettini_2002_total-variation-flow",                        # equation-heavy
             "Abercrombie_2016_improving-consistency",                      # IEEE preprint
             "Anderson_1957_statistical-inference-about-markov"]            # JSTOR scan, pre-1990
SET_SIZE = 20


def manifest_rows():
    with open(MANIFEST, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def mention_rank(rows):
    """Stems ranked by how often the project's own tracked prose names them — the measured stand-in
    for "papers the project cites heavily". Counted over Reports/**/*.md and Scripts/*.md."""
    docs = list((REPO / "Reports").rglob("*.md")) + list(SCRIPTS.glob("*.md"))
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in docs)
    counts = collections.Counter()
    for r in rows:
        stem = r["stem"]
        parts = stem.split("_")
        counts[stem] = text.count(stem) + len(re.findall(
            re.escape(parts[0]) + r"[ _]\(?" + re.escape(parts[1]), text))
    return [s for s, _n in counts.most_common()], counts


def paper_set(n=SET_SIZE):
    rows = manifest_rows()
    have = {r["stem"] for r in rows if (VALID / (r["stem"] + ".pdf")).exists()}
    ranked, counts = mention_rank(rows)
    sel = [s for s in P4_SHAPES if s in have]
    for s in ranked:
        if len(sel) >= n:
            break
        if s in have and s not in sel:
            sel.append(s)
    return sel[:n], {r["stem"]: r for r in rows}, counts


# ── stage A: TEI ────────────────────────────────────────────────────────────────────────

def extract(stems, url=grobid.DEFAULT_URL, force=False):
    """GROBID once per paper, TEI cached on disk. includeRawCitations=1 (stage 6 needs raw)."""
    TEI_DIR.mkdir(parents=True, exist_ok=True)
    out, log = {}, []
    todo = [s for s in stems if force or not (TEI_DIR / f"{s}.tei.xml").exists()]
    if todo:
        grobid.hold_distro()
        if not grobid.start(url):
            raise SystemExit("GROBID did not come up")
    for stem in stems:
        p = TEI_DIR / f"{stem}.tei.xml"
        if p.exists() and not force:
            out[stem] = p.read_bytes()
            log.append({"stem": stem, "status": "cached", "bytes": p.stat().st_size})
            continue
        t0 = time.time()
        try:
            tei = grobid.process_pdf(str(VALID / f"{stem}.pdf"), url=url, include_raw_citations=True)
        except grobid.GrobidError as e:
            log.append({"stem": stem, "status": "failed", "error": f"{type(e).__name__}: {e}"[:300]})
            print(f"  {stem}: FAILED {type(e).__name__}", flush=True)
            continue
        p.write_bytes(tei)
        out[stem] = tei
        log.append({"stem": stem, "status": "ok", "bytes": len(tei), "seconds": round(time.time() - t0, 2)})
        print(f"  {stem}: {len(tei)} B in {time.time() - t0:.1f}s", flush=True)
    R.write_jsonl(log, str(OUT / "extraction_log.jsonl"))
    return out


# ── stage B: parse + resolve ────────────────────────────────────────────────────────────

def make_client(offline=False):
    pacer = R.deferred_pacer(Pacer(interval=1.0))
    client = R.CachedClient(cache=R.DiskCache(), pacer=pacer)
    return client, pacer


def run(stems, teis, resolve=True):
    index = R.corpus_index([str(MANIFEST)] + [str(p) for p in BIBLIOS])
    client, pacer = make_client()
    breaker = R.StageBreaker()
    allrefs, allment, alledges, allcands = [], [], [], []
    per_paper = []
    for stem in stems:
        tei = teis.get(stem)
        if tei is None:
            per_paper.append({"stem": stem, "status": "no-tei"})
            continue
        t0 = time.time()
        res = R.process_tei(tei, stem, client, pacer, index=index, resolve=resolve, breaker=breaker)
        allrefs += res["references"]
        allment += res["citation_mentions"]
        alledges += res["edges"]
        allcands += res["candidates"]
        s = R.resolution_summary(res["references"])
        s.update(stem=stem, status="ok", mentions=len(res["citation_mentions"]),
                 edges=len(res["edges"]), candidates=len(res["candidates"]),
                 seconds=round(time.time() - t0, 1))
        per_paper.append(s)
        print(f"  {stem}: {s['references']} refs  {s['resolved']}R/{s['ambiguous']}A/"
              f"{s['unresolved']}U  {s['edges']} edges  {s['seconds']}s", flush=True)
    R.write_jsonl(allrefs, str(OUT / "references.jsonl"))
    R.write_jsonl(allment, str(OUT / "citation_mentions.jsonl"))
    R.write_jsonl(alledges, str(OUT / "edges.jsonl"))
    R.write_jsonl(allcands, str(OUT / "candidates.jsonl"))
    summary = R.resolution_summary(allrefs)
    summary.update(papers=len([p for p in per_paper if p.get("status") == "ok"]),
                   mentions=len(allment), edges=len(alledges), candidates=len(allcands),
                   network_calls=client.network_calls, cache_hits=client.cache.hits,
                   corpus_index_size=len(index), stages_tripped=breaker.report())
    (OUT / "summary.json").write_text(json.dumps({"summary": summary, "per_paper": per_paper},
                                                 indent=2, sort_keys=True), encoding="utf-8")
    _write_report_csvs(allrefs, alledges, allcands, per_paper)
    return summary, per_paper


def _write_report_csvs(refs, edges, cands, per_paper):
    REPORTS.mkdir(exist_ok=True)
    with open(REPORTS / "litkb_p6_per_paper_2026-09-15.csv", "w", encoding="utf-8", newline="") as fh:
        cols = ["stem", "status", "references", "resolved", "ambiguous", "unresolved",
                "resolved_rate", "mentions", "edges", "candidates", "seconds"]
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        for p in per_paper:
            w.writerow(p)
    # most-cited works NOT in the corpus, by distinct citing papers then mentions
    agg = {}
    for c in cands:
        doi = c.get("doi")
        if not doi:
            continue
        a = agg.setdefault(doi, {"doi": doi, "title": c.get("title") or "", "year": c.get("year") or "",
                                 "citing": set(), "mentions": 0})
        a["citing"].add(c["citing_work_key"])
    for r in refs:
        d = r.get("resolved_doi")
        if d in agg:
            agg[d]["mentions"] += r.get("mention_count", 0)
    top = sorted(agg.values(), key=lambda a: (-len(a["citing"]), -a["mentions"], a["doi"]))
    with open(REPORTS / "litkb_p6_top_uncited_2026-09-15.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["doi", "title", "year", "citing_papers_in_set", "in_text_mentions"])
        for a in top[:50]:
            w.writerow([a["doi"], a["title"][:120], a["year"], len(a["citing"]), a["mentions"]])
    return top


# ── the §14 P6 gate: Crossref's own deposited reference lists ───────────────────────────

def crossref_check(stems, manifest, teis, want=3):
    """Our parsed reference count against the publisher-DEPOSITED list for papers that have one.

    `reference-count` 0 means the publisher deposited nothing — unknown, not zero — so those papers
    are reported as `not-deposited` and are not counted against the parse.
    """
    client, pacer = make_client()
    rows = []
    for stem in stems:
        doi = (manifest.get(stem) or {}).get("doi") or ""
        tei = teis.get(stem)
        if not doi or tei is None:
            continue
        n, reflist, st = R.crossref_reference_list(client, doi, pacer)
        ours = len(R.parse_references(tei))
        rows.append({"stem": stem, "doi": doi, "status": st, "crossref_reference_count": n,
                     "crossref_list_present": len(reflist), "grobid_biblstruct": ours,
                     "delta": (ours - len(reflist)) if reflist else None,
                     "verdict": ("not-deposited" if not reflist else
                                 "match" if ours == len(reflist) else "differs")})
        print(f"  {stem}: crossref {len(reflist)} deposited / count {n} vs grobid {ours}", flush=True)
    with open(REPORTS / "litkb_p6_crossref_lists_2026-09-15.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["stem", "doi", "status", "crossref_reference_count",
                                "crossref_list_present", "grobid_biblstruct", "delta", "verdict"])
        w.writeheader()
        w.writerows(rows)
    return rows


# ── the §14 P6 kill: near misses ────────────────────────────────────────────────────────

def _swap_one_title_word(title):
    """Replace the longest word of the title with a different real word. One field, one change."""
    words = title.split()
    if len(words) < 2:
        return title + " elsewhere"
    i = max(range(len(words)), key=lambda k: len(words[k]))
    words[i] = "bicycles" if words[i].lower() != "bicycles" else "helicopters"
    return " ".join(words)


#: The mutations that ARE the §14 P6 kill: none of them may resolve to the original work.
KILL_MUTATIONS = ("year+3", "year-3", "title-wrong", "doi-digit")
#: Measured, reported, and NOT a kill — see :func:`near_miss`.
CHARACTERISING_MUTATIONS = ("title-word",)


def near_miss(limit=10, offline_refs=None):
    """Alter ONE field of a real resolved reference and require that it not resolve to the original.

    THE SELECTION RULE, stated so nothing is picked to make a kill fire: the first `limit` resolved
    references in (citing stem, reference index) order that carry a title and a four-digit year,
    PLUS the first `limit` resolved references that carry a DOI — without that second list the
    ``doi-digit`` arm never runs at all, because in this corpus only two of the eighteen papers
    print DOIs in their reference lists and they sort late.

    The mutants, per reference:

      * ``year+3`` / ``year-3``  — outside the +/-1 rule by construction (:data:`KILL_MUTATIONS`);
      * ``title-wrong``          — a wholly different real title, same author and year: the §14
                                   wording "real author + year, wrong title";
      * ``doi-digit``            — one digit of the DOI changed, the §14 "DOI one digit off";
      * ``title-word``           — ONE word of the title swapped. This is **NOT counted as a kill**
                                   and must not be: difflib on a long title is deliberately
                                   typo-tolerant, so swapping one word out of twelve leaves the
                                   ratio well above 0.85 and the reference resolves. That is a
                                   MEASURED property of the project's one title rule (0.85,
                                   calibrated in P2, Reports/litkb_title_threshold_2026-09-14.csv),
                                   reported with its per-mutant ratio rather than hidden — and the
                                   fix, if the project wants one, is a threshold decision with its
                                   own calibration, not a quiet change made here by the code that
                                   would benefit from it (CLAUDE.md 3.4c).
    """
    rows = json.loads((OUT / "near_miss_input.json").read_text(encoding="utf-8")) if offline_refs is None \
        else offline_refs
    client, pacer = make_client()
    breaker = R.StageBreaker()
    out = []
    for ref in rows:   # near_miss_input already applied the selection rule; do not re-cut it
        orig_doi = ref["resolved_doi"]
        mutants = [("year+3", dict(ref, year=str(int(ref["year"]) + 3), doi="", doi_norm="")),
                   ("year-3", dict(ref, year=str(int(ref["year"]) - 3), doi="", doi_norm="")),
                   ("title-word", dict(ref, title=_swap_one_title_word(ref["title"]), doi="", doi_norm="")),
                   ("title-wrong", dict(ref, title="Rain forest fragmentation and the dynamics of "
                                                   "Amazonian tree communities", doi="", doi_norm=""))]
        if ref.get("doi_norm"):
            d = ref["doi_norm"]
            digits = [i for i, ch in enumerate(d) if ch.isdigit() and i > d.find("/")]
            if digits:
                i = digits[-1]
                d2 = d[:i] + str((int(d[i]) + 1) % 10) + d[i + 1:]
                mutants.append(("doi-digit", dict(ref, doi=d2, doi_norm=d2)))
        for kind, m in mutants:
            res = R.resolve_reference(m, client, pacer, breaker)
            fired = not (res.state == "resolved" and res.doi == orig_doi)
            out.append({"stem": ref["citing_work_key"], "ref_key": ref["ref_key"],
                        "mutation": kind, "original_doi": orig_doi,
                        "mutant_title": m["title"], "mutant_year": m["year"], "mutant_doi": m.get("doi"),
                        "title_ratio_to_original": round(title_match_ratio(ref["title"], m["title"]), 4),
                        "state": res.state, "doi": res.doi, "reason": res.reason[:160],
                        "is_kill": kind in KILL_MUTATIONS,
                        "resolved_elsewhere": bool(res.state == "resolved" and res.doi != orig_doi),
                        "kill_fired": fired})
            print(f"  {ref['ref_key']} {kind}: {res.state} {res.doi} -> "
                  f"{'FIRED' if fired else 'DID NOT FIRE'}", flush=True)
    with open(REPORTS / "litkb_p6_near_miss_2026-09-15.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["stem", "ref_key", "mutation", "original_doi", "mutant_title",
                                "mutant_year", "mutant_doi", "title_ratio_to_original", "state",
                                "doi", "reason", "is_kill", "resolved_elsewhere", "kill_fired"])
        w.writeheader()
        w.writerows(out)
    return out


def near_miss_input(limit=10):
    """The selection rule of :func:`near_miss`, applied to the run's own references.jsonl."""
    refs = [json.loads(ln) for ln in (OUT / "references.jsonl").read_text(encoding="utf-8").splitlines()]
    ok = [r for r in refs if r["resolution"] == "resolved" and r["title"] and (r["year"] or "").isdigit()]
    ok.sort(key=lambda r: (r["citing_work_key"], r["index"]))
    sel = ok[:limit]
    for r in ok:                       # the DOI-bearing arm: without it doi-digit never runs
        if len([x for x in sel if x.get("doi_norm")]) >= limit:
            break
        if r.get("doi_norm") and r not in sel:
            sel.append(r)
    (OUT / "near_miss_input.json").write_text(json.dumps(sel, indent=1), encoding="utf-8")
    return sel


def fabricated():
    """Sanity: a reference to a paper that does not exist must not resolve."""
    client, pacer = make_client()
    ref = {"title": "Quantised chlorophyll telemetry of municipal streetlamps under vacuum",
           "first_author": "Quimbly", "year": "2011", "authors": [{"family": "Quimbly", "given": "T"}],
           "doi": "", "doi_norm": "", "raw": "fabricated"}
    res = R.resolve_reference(ref, client, pacer, R.StageBreaker())
    return {"state": res.state, "doi": res.doi, "reason": res.reason,
            "kill_fired": res.state != "resolved"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--resolve", action="store_true")
    ap.add_argument("--crossref-check", action="store_true")
    ap.add_argument("--near-miss", action="store_true")
    ap.add_argument("--set", action="store_true", help="print the derived paper set and stop")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args(argv)
    stems, manifest, counts = paper_set()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.set:
        for s in stems:
            print(f"{counts[s]:4d}  {manifest[s]['year']}  {s}")
        return 0
    teis = {}
    if a.extract:
        print("== GROBID ==", flush=True)
        teis = extract(stems, force=a.force)
    if a.resolve or a.crossref_check or a.near_miss:
        for s in stems:
            p = TEI_DIR / f"{s}.tei.xml"
            if p.exists():
                teis[s] = p.read_bytes()
    if a.resolve:
        print("== resolve ==", flush=True)
        summary, _ = run(stems, teis)
        print(json.dumps(summary, indent=2, sort_keys=True))
        near_miss_input(a.limit)
    if a.crossref_check:
        print("== crossref deposited lists ==", flush=True)
        crossref_check(stems, manifest, teis)
    if a.near_miss:
        print("== near miss ==", flush=True)
        rows = near_miss(a.limit)
        fab = fabricated()
        (OUT / "kills.json").write_text(json.dumps({"near_miss": rows, "fabricated": fab},
                                                   indent=1), encoding="utf-8")
        kills = [r for r in rows if r["is_kill"]]
        n_fired = sum(1 for r in kills if r["kill_fired"])
        per = ", ".join(
            f"{k}={sum(1 for r in kills if r['mutation'] == k and r['kill_fired'])}"
            f"/{sum(1 for r in kills if r['mutation'] == k)}" for k in KILL_MUTATIONS)
        print(f"KILL set: {n_fired}/{len(kills)} fired  ({per})")
        for k in CHARACTERISING_MUTATIONS:
            ch = [r for r in rows if r["mutation"] == k]
            lo = min((r["title_ratio_to_original"] for r in ch), default=0)
            hi = max((r["title_ratio_to_original"] for r in ch), default=0)
            print(f"characterisation (NOT a kill) {k}: "
                  f"{sum(1 for r in ch if not r['kill_fired'])}/{len(ch)} still resolved to the "
                  f"original; ratios {lo:.2f}-{hi:.2f} against the {RESOLVE_TITLE_RATIO} rule")
        wrong = [r for r in kills if r["resolved_elsewhere"]]
        if wrong:
            print(f"NOTE {len(wrong)} killed mutants resolved to a DIFFERENT work (the kill held: "
                  "not the original) — flagged resolved_elsewhere in the CSV")
        print(f"fabricated reference fired={fab['kill_fired']}")
        return 0 if n_fired == len(kills) and fab["kill_fired"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
