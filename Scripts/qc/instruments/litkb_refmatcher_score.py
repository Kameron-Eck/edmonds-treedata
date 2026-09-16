"""Score every ref-matcher arm against the frozen Splink gold, beside our own resolver.

Reads only files: the gold (sha256 asserted), the arm result files written by
`litkb_refmatcher_eval.py`, `litkb_derived/p6/references.jsonl` for the P6 resolver state,
and `Reports/litkb_s2_rows_2026-09-15.csv` for the S2/confirmed arms on the 293 hard set.
Our resolver's 20/23/250 is DERIVED from that CSV here, never typed in -- the same rule that
CLAUDE.md 3.12 states for registry rows.

The scoring buckets, and why each exists:

  positives (365)   the gold's ref_id -> gold_doi pairs. correct / wrong / miss.
  hard set (293)    every reference P6 left `unresolved` or `ambiguous`. The gold labels
                    only part of it, so a DOI an arm returns here is `graded_right`,
                    `graded_wrong`, or **UNGRADED** -- counted separately and never folded
                    into a "resolves N more" headline, because nothing in the gold says
                    whether an ungraded DOI is right.
  must_not_link     7 real references (3 book reviews, 4 sibling editions) that must NOT
                    come back as `bad_doi`, plus 70 mutants that must not return the DOI
                    of the work they were mutated away from.
  near_positive     20 one-word title corruptions carrying `gold_doi`. Returning the
                    original is reported as a NUMBER, under both readings, not as a verdict:
                    a fuzzy matcher recovering a typo'd title may be right or may be
                    insufficiently discriminating, and the gold does not settle which.
  lost_genuine (5)  correct resolutions our confirmation rule refuses because Crossref's
                    record is thin. The question the brief asks of them is whether someone
                    else's matcher gets them without giving up the refusals.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

DERIVED = Path(os.environ.get("LITKB_DERIVED", r"D:\edmonds-pipeline\litkb_derived"))
P6 = DERIVED / "p6"
OUT = DERIVED / "refmatch"
GOLD_SHA256 = "d6dbbac3e0e8fc473e431568cfb77ebdfaff0c687647e69e3ef2274d974846a0"


def normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                "http://dx.doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip()


def gold_sha256(path: Path) -> str:
    """CRLF-SAFE, the same way `litkb_splink_eval.py` computes it.

    `.gitattributes` marks *.json as text and `core.autocrlf` is true, so the working copy
    on Windows has CRLF while the blob has LF. Hashing the raw bytes would make the frozen
    digest depend on which OS checked the file out; normalising first makes the pin mean
    "the same gold", not "the same line endings".
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_gold(path: Path) -> dict:
    digest = gold_sha256(path)
    if digest != GOLD_SHA256:
        raise SystemExit(f"gold sha256 {digest} != frozen {GOLD_SHA256} -- refusing to score")
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def load_arm(path: Path) -> tuple[dict, dict]:
    if not path.exists():
        return {}, {}
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = recs[0].get("_meta", {}) if recs and "_meta" in recs[0] else {}
    body = {r["ref_id"]: r for r in recs if "ref_id" in r}
    return meta, body


def load_refs() -> dict:
    rows = [json.loads(line) for line in
            (P6 / "references.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return {f"{r['citing_work_key']}::{r['ref_key']}": r for r in rows}


def load_s2_rows(csv_path: Path) -> dict:
    """-> {arm: {ref_id: (state, doi)}}  from the tracked S2 per-row CSV."""
    out: dict[str, dict] = {}
    if not csv_path.exists():
        return out
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rid = f"{row['citing_work_key']}::{row['ref_key']}"
            out.setdefault(row["arm"], {})[rid] = (row["state"], normalize_doi(row.get("doi") or ""))
    return out


def score_positives(gold, arm_body, cut=None) -> dict:
    """`cut` drops any top hit whose own relevance/matching score is below it.

    The Crossref arm returns a top hit for almost every query -- Crossref's search always
    ranks something first -- so an unconditional top hit has no precision to read. The
    published search-based number applies a cut; this makes the same arm readable at one.
    """
    c = Counter()
    wrong, scores_right, scores_wrong = [], [], []
    for p in gold["positives"]:
        rid, want = p["ref_id"], normalize_doi(p["gold_doi"])
        r = arm_body.get(rid)
        if r is None:
            c["absent_from_run"] += 1
            continue
        got = normalize_doi(r.get("doi") or "")
        s = r.get("score")
        if cut is not None and got and isinstance(s, (int, float)) and s < cut:
            c["below_cut"] += 1
            continue
        if not r.get("matched") or not got:
            c["miss"] += 1
        elif got == want:
            c["correct"] += 1
            if isinstance(s, (int, float)):
                scores_right.append(s)
        else:
            c["wrong"] += 1
            if isinstance(s, (int, float)):
                scores_wrong.append(s)
            wrong.append({"ref_id": rid, "want": want, "got": got,
                          "score": s, "title": r.get("title", "")[:80]})

    def _q(v):
        if not v:
            return None
        v = sorted(v)
        return {"n": len(v), "min": round(v[0], 1), "p25": round(v[len(v) // 4], 1),
                "median": round(v[len(v) // 2], 1), "max": round(v[-1], 1)}

    return {"counts": dict(c), "wrong": wrong[:40], "cut": cut,
            "score_dist_correct": _q(scores_right), "score_dist_wrong": _q(scores_wrong)}


def score_hard_set(gold, arm_body, refs) -> dict:
    """The 293 P6 left unresolved/ambiguous, with an explicit UNGRADED column."""
    hard = [rid for rid, r in refs.items() if r["resolution"] in ("unresolved", "ambiguous")]
    wrongmap: dict[str, str] = {}
    for e in gold["must_not_link"]:
        if "#mut" not in e["ref_id"]:
            wrongmap[e["ref_id"]] = normalize_doi(e["bad_doi"])
    c = Counter()
    detail = []
    for rid in hard:
        r = arm_body.get(rid)
        if r is None:
            c["absent_from_run"] += 1
            continue
        if not r.get("matched") or not normalize_doi(r.get("doi") or ""):
            c["no_match"] += 1
            continue
        got = normalize_doi(r["doi"])
        by_id = {e["ref_id"]: normalize_doi(e["gold_doi"]) for e in gold["lost_genuine"]}
        if rid in by_id and got == by_id[rid]:
            c["graded_right"] += 1
            detail.append({"ref_id": rid, "verdict": "graded_right", "doi": got})
        elif rid in wrongmap and got == wrongmap[rid]:
            c["graded_wrong"] += 1
            detail.append({"ref_id": rid, "verdict": "graded_wrong", "doi": got})
        else:
            c["ungraded"] += 1
            detail.append({"ref_id": rid, "verdict": "ungraded", "doi": got,
                           "score": r.get("score"), "title": r.get("title", "")[:80]})
    return {"hard_n": len(hard), "counts": dict(c), "detail": detail}


def our_gate_verdict(returned_doi: str, ref: dict, crossref_items: dict):
    """Run OUR confirmation rule over the record an arm returned. -> (verdict, detail).

    Exact-DOI must-not-link scoring UNDERSTATES the failure, and measurably so: on the three
    book reviews the Crossref arm returned a review every time, but only ONE of them was the
    specific DOI the gold names -- S2 had proposed that one; the other two are DIFFERENT
    reviews of the same book (a QREI review and a Cytometry review). Scored on DOI equality
    those two read as `other_doi`, i.e. as having avoided the trap. They did not. This asks
    the question the gold cannot: is the record the arm returned a review of the cited work,
    or the wrong type for it?
    """
    try:
        from litkb.admit.resolver import (RESOLVE_TITLE_RATIO, _shares_authorship, _year_int,
                                          family_matches, reference_is_book, review_hint,
                                          review_signature, title_match_ratio)
    except ImportError:
        return "gate_unavailable", "litkb not importable"
    msg = crossref_items.get(normalize_doi(returned_doi))
    if msg is None:
        return "no_record", "the returned DOI's Crossref body was not captured"
    rec = {
        "raw_type": msg.get("type") or "",
        "raw_subtype": msg.get("subtype") or "",
        "title": (msg.get("title") or [""])[0],
        "titles": list(msg.get("title") or []),
        "venue": next((c for c in (msg.get("container-title") or []) if c), None),
        "first_author": ((msg.get("author") or [{}])[0].get("family")
                         or (msg.get("author") or [{}])[0].get("name") or ""),
        "authors": [{"family": a.get("family") or a.get("name") or "",
                     "given": a.get("given") or ""} for a in (msg.get("author") or [])],
        # Crossref's issued.date-parts is [[yyyy, mm, dd]]; the year is the first element.
        "year": (((msg.get("issued") or {}).get("date-parts") or [[None]])[0] or [None])[0],
    }
    why = review_signature(rec, ref)
    if why:
        return "review_record", why
    why = review_hint(rec, ref)
    if why:
        return "review_suspected", why
    if reference_is_book(ref) and rec["raw_type"] == "journal-article":
        return "type_mismatch", (f"reference is a book (publisher {ref.get('publisher')!r}); "
                                 f"crossref says journal-article in {rec['venue']!r}")
    # The remaining rungs of confirm_s2_candidate, in its order: title ratio, then the
    # edition test (same title + shared authorship + year apart = a sibling, not this one),
    # then first author, then year. Run here so the comparison is against the WHOLE rule and
    # not only its review half -- otherwise the four edition cases read as "passes our gate"
    # when it is simply that the rung which refuses them was not run.
    ratio = max([title_match_ratio(ref.get("title") or "", t)
                 for t in (rec.get("titles") or [])] or [0.0])
    if ratio < RESOLVE_TITLE_RATIO:
        return "crossref_title_ratio", f"ratio {ratio:.2f} < {RESOLVE_TITLE_RATIO}"
    cy, wy = _year_int(rec.get("year")), _year_int(ref.get("year"))
    if cy is not None and wy is not None and abs(cy - wy) > 1 and _shares_authorship(rec, ref):
        return "edition_mismatch", f"crossref {cy} vs reference {wy}, shared authorship"
    if not (rec.get("first_author") or ""):
        return "crossref_no_author", "crossref carries no author for this record"
    if not family_matches(rec["first_author"], ref.get("first_author") or ""):
        return "crossref_author_mismatch", (f"crossref {rec['first_author']!r} != "
                                            f"reference {ref.get('first_author')!r}")
    if cy is None or wy is None:
        return "crossref_year_unknown", f"crossref {cy}, reference {wy}"
    if abs(cy - wy) > 1:
        return "crossref_year_mismatch", f"crossref {cy} != reference {wy}"
    return "passes_our_gate", f"ratio {ratio:.2f}; year {cy}"


def score_must_not_link(gold, arm_body, presence=None) -> dict:
    """`presence` maps DOI -> bool (is it in the registry the arm searches).

    Without it a wrong answer the registry simply does not hold counts as `refused`, and a
    matcher gets credit for discrimination it never exercised. With it, that case is
    `bad_absent_from_registry` and is excluded from the refusal count.
    """
    presence = presence or {}
    real, mut = Counter(), Counter()
    hits = []
    for e in gold["must_not_link"]:
        rid, bad = e["ref_id"], normalize_doi(e["bad_doi"])
        bucket = mut if "#mut" in rid else real
        r = arm_body.get(rid)
        if r is None:
            bucket["absent_from_run"] += 1
            continue
        got = normalize_doi(r.get("doi") or "") if r.get("matched") else ""
        if not got and presence.get(bad) is False:
            bucket["bad_absent_from_registry"] += 1
        elif not got:
            bucket["refused"] += 1
        elif got == bad:
            bucket[f"returned_bad::{e['kind']}"] += 1
            bucket["returned_bad"] += 1
            hits.append({"ref_id": rid, "kind": e["kind"], "doi": got, "score": r.get("score")})
        else:
            bucket["other_doi"] += 1
    return {"real": dict(real), "mutants": dict(mut), "returned_bad": hits}


def score_must_not_link_through_our_gate(gold, arm_body, refs, crossref_items) -> dict:
    """The same 7 real cases, judged by OUR rule on the record the arm actually returned."""
    c = Counter()
    rows = []
    for e in gold["must_not_link"]:
        if "#mut" in e["ref_id"]:
            continue
        r = arm_body.get(e["ref_id"])
        got = normalize_doi((r or {}).get("doi") or "") if (r and r.get("matched")) else ""
        if not got:
            c["no_answer"] += 1
            rows.append({"ref_id": e["ref_id"], "kind": e["kind"], "doi": "",
                         "verdict": "no_answer", "detail": ""})
            continue
        verdict, detail = our_gate_verdict(got, refs.get(e["ref_id"], {}), crossref_items)
        c[verdict] += 1
        c["is_the_named_bad_doi"] += int(got == normalize_doi(e["bad_doi"]))
        rows.append({"ref_id": e["ref_id"], "kind": e["kind"], "doi": got,
                     "verdict": verdict, "detail": detail[:160],
                     "is_named_bad_doi": got == normalize_doi(e["bad_doi"])})
    return {"counts": dict(c), "rows": rows}


def score_near_positive(gold, arm_body) -> dict:
    c = Counter()
    for e in gold["near_positive_mutations"]:
        r = arm_body.get(e["ref_id"])
        if r is None:
            c["absent_from_run"] += 1
            continue
        got = normalize_doi(r.get("doi") or "") if r.get("matched") else ""
        if not got:
            c["no_match"] += 1
        elif got == normalize_doi(e["gold_doi"]):
            c["returned_original"] += 1
        else:
            c["other_doi"] += 1
    return dict(c)


def score_lost_genuine(gold, arm_body) -> list:
    out = []
    for e in gold["lost_genuine"]:
        r = arm_body.get(e["ref_id"])
        got = normalize_doi((r or {}).get("doi") or "") if (r and r.get("matched")) else ""
        out.append({"ref_id": e["ref_id"], "gold_doi": normalize_doi(e["gold_doi"]),
                    "got": got, "correct": got == normalize_doi(e["gold_doi"]),
                    "score": (r or {}).get("score"),
                    "our_refusal": e["refusal_reason"]})
    return out


def score_unparsed(refs, arm_body, gold) -> dict:
    """The 50 GROBID left with no title or no first author."""
    ids = [rid for rid, r in refs.items()
           if not (r.get("title") or "").strip() or not (r.get("first_author") or "").strip()]
    goldmap = {p["ref_id"]: normalize_doi(p["gold_doi"]) for p in gold["positives"]}
    c = Counter()
    rows = []
    for rid in ids:
        r = arm_body.get(rid)
        if r is None:
            c["absent_from_run"] += 1
            continue
        got = normalize_doi(r.get("doi") or "") if r.get("matched") else ""
        if not got:
            c["no_match"] += 1
            continue
        c["returned_a_doi"] += 1
        if rid in goldmap:
            c["gold_agrees" if got == goldmap[rid] else "gold_disagrees"] += 1
        else:
            c["ungraded"] += 1
        rows.append({"ref_id": rid, "doi": got, "score": r.get("score"),
                     "gold": goldmap.get(rid, ""), "raw": (refs[rid].get("raw") or "")[:220],
                     "title": r.get("title", "")[:100]})
    return {"n": len(ids), "counts": dict(c), "rows": rows}


def render_markdown(report: dict) -> str:
    """The report's tables, generated. CLAUDE.md 3.4b: a number in the report is written
    by the instrument that measured it, never retyped from a console summary."""
    L = []
    g = report.get("p6_resolver", {})
    L.append("| arm | registry | positives correct / wrong / miss (365) |"
             " hard-293 right / wrong / ungraded / none | must-not-link real (7) |")
    L.append("|---|---|---|---|---|")
    ours = report.get("our_resolver_on_293", {})
    oc = report.get("our_confirmed_graded", {})
    if ours:
        b = ours.get("confirmed", {})
        L.append(f"| **ours (P6 + confirm)** | crossref | "
                 f"{g.get('resolved', 0)} / – / {g.get('unresolved', 0) + g.get('ambiguous', 0)}"
                 f" *(P6 state)* | {oc.get('graded_right', 0)} / {oc.get('graded_wrong', 0)}"
                 f" / {oc.get('ungraded', 0)} / {b.get('unresolved', 0)}"
                 f" (+{b.get('ambiguous', 0)} amb) | 0 returned |")
    for arm, e in report.get("arms", {}).items():
        if e.get("status") == "NOT RUN" or "positives" not in e:
            continue
        p = e["positives"]["counts"]
        h = e["hard_set"]["counts"]
        m = e["must_not_link"]["real"]
        reg = e.get("meta", {}).get("registry", "?")
        L.append(f"| {arm} | {reg} | {p.get('correct', 0)} / {p.get('wrong', 0)}"
                 f" / {p.get('miss', 0)} | {h.get('graded_right', 0)} / {h.get('graded_wrong', 0)}"
                 f" / {h.get('ungraded', 0)} / {h.get('no_match', 0)} |"
                 f" {m.get('returned_bad', 0)} returned,"
                 f" {m.get('refused', 0)} refused,"
                 f" {m.get('bad_absent_from_registry', 0)} absent-from-registry |")
    L.append("")
    L.append("| arm | the 50 unparsed footnotes: returned a DOI / gold agrees / disagrees / ungraded |")
    L.append("|---|---|")
    for arm, e in report.get("arms", {}).items():
        if "unparsed_50" not in e:
            continue
        u = e["unparsed_50"]["counts"]
        L.append(f"| {arm} | {u.get('returned_a_doi', 0)} / {u.get('gold_agrees', 0)}"
                 f" / {u.get('gold_disagrees', 0)} / {u.get('ungraded', 0)}"
                 f"  (no match {u.get('no_match', 0)} of {e['unparsed_50']['n']}) |")
    L.append("")
    L.append("| kill arm | mutants returning the ORIGINAL doi (70 must-not-link) |"
             " near-positive returning the original (20) |")
    L.append("|---|---|---|")
    for arm, e in report.get("arms", {}).items():
        if not arm.startswith("mutants") or e.get("status") == "NOT RUN":
            continue
        mm = e["must_not_link"]["mutants"]
        np_ = e["near_positive"]
        L.append(f"| {arm} | {mm.get('returned_bad', 0)} of 70"
                 f" (other DOI {mm.get('other_doi', 0)}, none {mm.get('refused', 0)}) |"
                 f" {np_.get('returned_original', 0)} of 20 |")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--s2-rows", default="")
    ap.add_argument("--arms", nargs="*", default=["parsed", "parsed-unpatched", "raw-crossref",
                                                  "mutants", "mutants-noauthor"])
    ap.add_argument("--crossref-cut", type=float, default=0.0,
                    help="relevance cut for the Crossref SBM arm; chosen AFTER seeing the "
                         "score distribution, which the report states")
    ap.add_argument("--json-out", default=str(OUT / "score.json"))
    args = ap.parse_args(argv)

    gold = load_gold(Path(args.gold))
    refs = load_refs()
    report = {"gold_sha256": GOLD_SHA256, "arms": {}}

    # Registry presence, so an absent record is never scored as a refusal.
    _, pres_body = load_arm(OUT / "results_presence.jsonl")
    presence = {normalize_doi(r["doi"]): bool(r.get("in_oc_meta"))
                for r in pres_body.values() if r.get("doi")}
    report["oc_meta_presence"] = {
        "probed": len(presence),
        "absent": sorted(d for d, ok in presence.items() if not ok),
    }

    # Our own resolver, derived from the tracked per-row CSV -- never typed in.
    if args.s2_rows:
        s2 = load_s2_rows(Path(args.s2_rows))
        ours = {}
        for arm, body in s2.items():
            ours[arm] = dict(Counter(st for st, _ in body.values()))
        report["our_resolver_on_293"] = ours
        conf = s2.get("confirmed", {})
        if conf:
            lg = {e["ref_id"]: normalize_doi(e["gold_doi"]) for e in gold["lost_genuine"]}
            mnl = {e["ref_id"]: normalize_doi(e["bad_doi"])
                   for e in gold["must_not_link"] if "#mut" not in e["ref_id"]}
            c = Counter()
            for rid, (st, doi) in conf.items():
                if st == "resolved" and doi:
                    if rid in lg and doi == lg[rid]:
                        c["graded_right"] += 1
                    elif rid in mnl and doi == mnl[rid]:
                        c["graded_wrong"] += 1
                    else:
                        c["ungraded"] += 1
                elif st == "ambiguous":
                    c["ambiguous"] += 1
                else:
                    c["unresolved"] += 1
            report["our_confirmed_graded"] = dict(c)

    p6 = Counter(r["resolution"] for r in refs.values())
    report["p6_resolver"] = dict(p6)

    # Crossref bodies captured by the SBM run, indexed by DOI, so our own gate can be run
    # over the records an arm returned rather than only over the DOI strings.
    crossref_items: dict[str, dict] = {}
    cpath = OUT / "cache_crossref_search.jsonl"
    if cpath.exists():
        for line in cpath.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                for it in json.loads(line).get("v") or []:
                    d = normalize_doi(it.get("DOI") or "")
                    if d and d not in crossref_items:
                        crossref_items[d] = it
            except (json.JSONDecodeError, AttributeError):
                continue
    report["crossref_bodies_captured"] = len(crossref_items)

    for arm in args.arms:
        meta, body = load_arm(OUT / f"results_{arm}.jsonl")
        if not body:
            report["arms"][arm] = {"status": "NOT RUN"}
            continue
        entry = {"meta": meta, "rows_in_run": len(body)}
        # Presence is a fact about OpenCitations Meta; it says nothing about Crossref, so
        # the Crossref arm is scored without it rather than against the wrong registry.
        pres = presence if meta.get("registry") == "opencitations-meta" else None
        if arm.startswith("mutants"):
            entry["must_not_link"] = score_must_not_link(gold, body, pres)
            entry["near_positive"] = score_near_positive(gold, body)
        else:
            entry["positives"] = score_positives(gold, body)
            if args.crossref_cut and meta.get("registry") == "crossref":
                entry["positives_at_cut"] = score_positives(gold, body, cut=args.crossref_cut)
            entry["hard_set"] = score_hard_set(gold, body, refs)
            entry["must_not_link"] = score_must_not_link(gold, body, pres)
            if crossref_items:
                entry["must_not_link_our_gate"] = score_must_not_link_through_our_gate(
                    gold, body, refs, crossref_items)
            entry["lost_genuine"] = score_lost_genuine(gold, body)
            entry["unparsed_50"] = score_unparsed(refs, body, gold)
        report["arms"][arm] = entry

    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                   encoding="utf-8")
    # Console summary
    print(f"gold sha256 OK  |  P6 resolver: {report['p6_resolver']}")
    if "our_resolver_on_293" in report:
        for a, c in report["our_resolver_on_293"].items():
            print(f"  ours[{a:9}] {c}")
    for arm, e in report["arms"].items():
        if e.get("status") == "NOT RUN":
            print(f"  {arm:18} NOT RUN")
            continue
        if "positives" in e:
            print(f"  {arm:18} positives={e['positives']['counts']}")
            print(f"  {'':18} hard293={e['hard_set']['counts']}")
            print(f"  {'':18} unparsed50={e['unparsed_50']['counts']}")
            print(f"  {'':18} must_not_link_real={e['must_not_link']['real']}")
        else:
            print(f"  {arm:18} mnl_mutants={e['must_not_link']['mutants']}")
            print(f"  {'':18} near_positive={e['near_positive']}")
    md = render_markdown(report)
    md_path = Path(args.json_out).with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\nwrote {args.json_out} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
