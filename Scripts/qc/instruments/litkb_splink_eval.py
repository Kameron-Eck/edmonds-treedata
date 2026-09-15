"""Evaluate Splink (Fellegi-Sunter + EM, DuckDB backend, MIT) as a candidate-SCORING layer
for the literature knowledge base, against the frozen gold.

Splink would PROPOSE a ranking. The registry still CONFIRMS: nothing here changes, or is
designed to change, `resolver.confirm_s2_candidate`. "S2 proposes, Crossref confirms" stands
and this would sit in front of it, not instead of it.

Runs entirely offline. The right-hand candidate pool is harvested from the ALREADY CACHED
registry bodies under litkb_derived/registry/ -- the files are read directly rather than
through `admit.registry`, so there is no code path here that could reach the wire. No
database is opened.

  Task A  reference -> work/record linking, against the 365 confirmed resolutions
  Task B  duplicate detection over the 348 admitted works
  Task C  does the match probability separate the 5 "lost genuine" from the 3 book reviews
  Kills   (1) drop the first-author comparison: the review cases MUST become matches
          (2) drop blocking on a sample: recall MUST NOT change

Venv: D:\\edmonds-pipeline\\venv-splink (requirements-litkb-link.txt). Splink is NOT a
pipeline dependency and nothing under Scripts/pipeline imports it.

  D:\\edmonds-pipeline\\venv-splink\\Scripts\\python.exe qc/instruments/litkb_splink_eval.py
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2].parent
REPORTS = REPO / "Reports"
GOLD = REPORTS / "litkb_splink_gold_2026-09-15.json"
DERIVED = Path(r"D:\edmonds-pipeline\litkb_derived")
REGISTRY_CACHE = DERIVED / "registry"
P6 = DERIVED / "p6"
EXPORT = Path(r"D:\edmonds-pipeline\treedata-litkb\Reports\litkb_export")

STOP = {"the", "of", "and", "a", "an", "in", "on", "for", "to", "with", "from", "by", "at",
        "using", "based", "its", "their"}


# --------------------------------------------------------------------------- normalisation
def norm_doi(d):
    d = (d or "").strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d


def norm_title(t):
    t = re.sub(r"<[^>]+>", " ", (t or ""))
    t = re.sub(r"[^a-z0-9 ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def title_key(t):
    """A blocking key: the two rarest-looking (longest) non-stop tokens, sorted.

    Deliberately cheap and deterministic. It is a BLOCKING key, so it only has to be
    right often enough that the true pair survives; the comparison does the deciding.
    """
    toks = sorted({w for w in norm_title(t).split() if len(w) > 3 and w not in STOP},
                  key=lambda w: (-len(w), w))[:2]
    return " ".join(sorted(toks))


def norm_fam(a):
    return re.sub(r"[^a-z]", "", (a or "").lower())


def as_year(y):
    m = re.search(r"(1[89]\d\d|20\d\d)", str(y or ""))
    return int(m.group(1)) if m else None


def norm_txt(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(s or "").lower())).strip() or None


def pages_first(p):
    m = re.match(r"\s*(\d+)", str(p or ""))
    return m.group(1) if m else None


# --------------------------------------------------------------------------- the two sides
def load_gold():
    return json.loads(GOLD.read_text(encoding="utf-8"))


def _rec(uid, title, fam, year, journal, volume, pages, doi, **extra):
    r = {"unique_id": uid, "title": norm_title(title), "title_key": title_key(title),
         "first_author": norm_fam(fam) or None, "year": as_year(year),
         "journal": norm_txt(journal), "volume": norm_txt(volume),
         "pages": pages_first(pages), "doi": norm_doi(doi) or None}
    r.update(extra)
    return r


def left_rows(gold):
    """658 P6 references, plus one row per near-miss mutation (70 kills + 20 near-positives)."""
    out = []
    for r in (json.loads(line) for line in (P6 / "references.jsonl").open(encoding="utf-8")):
        out.append(_rec(f"{r['citing_work_key']}::{r['ref_key']}", r["title"], r["first_author"],
                        r["year"], r["journal"] or r.get("publisher"), r["volume"], r["pages"],
                        r["doi_norm"], row_kind="reference"))
    by_id = {r["unique_id"]: r for r in out}
    for group, kind in (("must_not_link", "mutant_kill"), ("near_positive_mutations", "mutant_near")):
        for g in gold[group]:
            if "mutation" not in g:
                continue
            base = by_id.get(g["base_ref_id"])
            if base is None:
                continue
            m = dict(base)
            m["unique_id"] = g["ref_id"]
            m["row_kind"] = kind
            m["title"] = norm_title(g["mutant_title"])
            m["title_key"] = title_key(g["mutant_title"])
            m["year"] = as_year(g["mutant_year"])
            m["doi"] = g.get("mutant_doi") or None
            out.append(m)
    return out


def _walk_crossref(body):
    msg = body.get("message") if isinstance(body, dict) else None
    if isinstance(msg, dict):
        if isinstance(msg.get("items"), list):
            yield from msg["items"]
        elif msg.get("DOI"):
            yield msg


def right_rows():
    """The candidate pool: every Crossref work already cached, plus the 348 admitted works.

    Cached bodies only. Nothing in this function can issue a request.
    """
    seen, out = {}, []
    for p in sorted(glob.glob(str(REGISTRY_CACHE / "*" / "*.json"))):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("status") != 200 or "api.crossref.org" not in d.get("url", ""):
            continue
        try:
            body = json.loads(d["body"])
        except Exception:
            continue
        for it in _walk_crossref(body):
            doi = norm_doi(it.get("DOI"))
            if not doi or doi in seen:
                continue
            titles = it.get("title") or []
            sub = it.get("subtitle") or []
            title = titles[0] if titles else ""
            if sub and sub[0]:
                title = f"{title}: {sub[0]}"
            auth = (it.get("author") or [{}])
            fam = (auth[0] or {}).get("family", "") if auth else ""
            dp = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
            year = dp[0] if dp else None
            cont = it.get("container-title") or []
            seen[doi] = True
            out.append(_rec(f"cr::{doi}", title, fam, year, cont[0] if cont else it.get("publisher"),
                            it.get("volume"), it.get("page"), doi,
                            row_kind="crossref", crossref_type=it.get("type")))
    # the corpus itself, so a reference can link to a work the project already holds
    import csv
    corpus = {}
    for name, cols in (("literature_tracker.csv",
                        dict(key="litkb_key", title="Title", auth="Author(s)", year="Year",
                             journal="Journal/Source", doi="DOI/URL")),
                       ("manifest.csv",
                        dict(key="litkb_key", title="title", auth="authors", year="year",
                             venue="venue", doi="doi"))):
        for r in csv.DictReader((EXPORT / name).open(encoding="utf-8-sig")):
            if r.get("litkb_state") != "admitted" or not r.get("litkb_key"):
                continue
            k = r["litkb_key"]
            if k in corpus:
                continue
            fam = re.split(r"[,&]", r[cols["auth"]] or "")[0]
            jr = r.get(cols.get("journal") or cols.get("venue") or "", "")
            corpus[k] = _rec(f"work::{k}", r[cols["title"]], fam, r[cols["year"]], jr, "", "",
                             r[cols["doi"]], row_kind="work", crossref_type=None)
    out.extend(corpus.values())
    return out, len(corpus)


# --------------------------------------------------------------------------- splink config
def year_comparison():
    """exact / within 1 / within 3 / else.

    decisions.yaml 15.15 allows +/-1 year only when title and first author both match, so
    the model is given the same granularity the rule uses -- +/-1 as its own level, with a
    wider +/-3 level below it because the P6 kills mutate by exactly 3 and a model that
    cannot see that distance cannot be scored on it.
    """
    import splink.comparison_level_library as cll
    import splink.comparison_library as cl

    return cl.CustomComparison(
        output_column_name="year",
        comparison_description="year exact / +/-1 / +/-3",
        comparison_levels=[
            cll.NullLevel("year"),
            cll.ExactMatchLevel("year"),
            cll.AbsoluteDifferenceLevel("year", difference_threshold=1),
            cll.AbsoluteDifferenceLevel("year", difference_threshold=3),
            cll.ElseLevel(),
        ],
    )


def settings(link_type, *, with_author=True, with_journal=True, blocking=True):
    import splink.comparison_library as cl
    from splink import SettingsCreator, block_on

    comparisons = [
        cl.JaroWinklerAtThresholds("title", [0.97, 0.92, 0.85]).configure(
            term_frequency_adjustments=False),
    ]
    if with_author:
        comparisons.append(cl.JaroWinklerAtThresholds("first_author", [0.99, 0.90])
                           .configure(term_frequency_adjustments=True))
    comparisons.append(year_comparison())
    if with_journal:
        comparisons.append(cl.JaroWinklerAtThresholds("journal", [0.95, 0.85]))
    comparisons += [
        cl.ExactMatch("volume").configure(term_frequency_adjustments=True),
        cl.ExactMatch("pages").configure(term_frequency_adjustments=True),
    ]
    rules = [block_on("title_key"), block_on("year")] if blocking else ["1=1"]
    return SettingsCreator(link_type=link_type, comparisons=comparisons,
                           blocking_rules_to_generate_predictions=rules,
                           retain_intermediate_calculation_columns=True)


def train(linker):
    """u from random sampling; m by EM on two rules, each blocking on a field whose own m is
    then NOT estimated from that pass (Splink excludes the blocked comparison itself).

    The prior (lambda, "two random records match") is estimated from EXACT NORMALISED TITLE,
    not from DOI. DOI is the obvious deterministic rule and it is the wrong one here, twice
    over: 88 % of the P6 references carry no DOI at all, and in the 348-work dedupe every work
    has a DISTINCT DOI by construction, so the rule matches zero pairs, lambda collapses to its
    floor and every pair scores around -1000 regardless of how well it matches. That is what
    the first run of this script produced for 303/60 (match_weight -996.6, probability 1e-300)
    -- a number that says nothing about the pair. Exact title is the rule that actually fires.
    """
    from splink import block_on
    linker.training.estimate_probability_two_random_records_match(
        [block_on("title")], recall=0.6)
    linker.training.estimate_u_using_random_sampling(max_pairs=2_000_000, seed=1729)
    notes = []
    for rule in (block_on("title_key"), block_on("year")):
        try:
            linker.training.estimate_parameters_using_expectation_maximisation(rule)
        except Exception as e:                                   # noqa: BLE001 - reported, not hidden
            notes.append(f"EM on {rule} did not converge: {type(e).__name__}: {e}")
    notes.append(f"lambda (two random records match) = {prior(linker)!r}")
    return notes


def prior(linker):
    """The estimated lambda, read back so the report can state it. Every match PROBABILITY
    is conditioned on it; the RANKING is not."""
    try:
        return linker._settings_obj._probability_two_random_records_match
    except Exception:                                            # noqa: BLE001
        return None


def match_weights(linker):
    """Per comparison level: m, u and the Bayes factor Splink trained. This is what the brief
    asks for as 'match weights per level'."""
    out = []
    for c in linker._settings_obj.comparisons:
        for lv in c.comparison_levels:
            if lv.is_null_level:
                continue
            m, u = lv._m_probability, lv._u_probability
            bf = (m / u) if (m and u) else None
            out.append({"comparison": c.output_column_name, "level": lv.label_for_charts,
                        "m": m, "u": u, "bayes_factor": bf,
                        "match_weight": math.log2(bf) if bf else None})
    return out


def run_link(left, right, *, with_author=True, with_journal=True, blocking=True, threshold=0.0):
    import pandas as pd
    from splink import DuckDBAPI, Linker

    ldf, rdf = pd.DataFrame(left), pd.DataFrame(right)
    linker = Linker([ldf, rdf], settings("link_only", with_author=with_author,
                                         with_journal=with_journal, blocking=blocking),
                    db_api=DuckDBAPI())
    notes = train(linker)
    preds = linker.inference.predict(threshold_match_probability=threshold)
    return linker, preds.as_pandas_dataframe(), notes


# --------------------------------------------------------------------------- evaluation
def pair_frame(preds):
    """Normalise Splink's l/r columns to (ref_id, cand_id, weight, probability).

    Splink does not promise which input frame lands on the _l side, so orient by the
    unique_id prefix rather than assuming.
    """
    import pandas as pd

    a = preds[["unique_id_l", "unique_id_r", "match_weight", "match_probability"]].copy()
    flip = a["unique_id_l"].str.startswith(("cr::", "work::"))
    ref = a["unique_id_l"].where(~flip, a["unique_id_r"])
    cand = a["unique_id_r"].where(~flip, a["unique_id_l"])
    return pd.DataFrame({"ref_id": ref, "cand_id": cand,
                         "match_weight": a["match_weight"],
                         "match_probability": a["match_probability"]})


def rank_eval(pairs, gold_rows, right_dois, key="gold_doi"):
    """For each gold row: where does the gold DOI rank among that reference's candidates?"""
    by_ref = {}
    for r in pairs.itertuples(index=False):
        by_ref.setdefault(r.ref_id, []).append((r.match_weight, r.cand_id, r.match_probability))
    out = []
    for g in gold_rows:
        doi = g[key]
        cands = sorted(by_ref.get(g["ref_id"], []), reverse=True)
        gold_cands = {f"cr::{doi}"}
        rank, weight, prob = None, None, None
        for i, (w, cid, p) in enumerate(cands, 1):
            if cid in gold_cands:
                rank, weight, prob = i, w, p
                break
        out.append({"ref_id": g["ref_id"], "gold_doi": doi, "rank": rank,
                    "n_candidates": len(cands), "match_weight": weight, "match_probability": prob,
                    "gold_on_right": doi in right_dois,
                    "top_cand": cands[0][1] if cands else None,
                    "top_weight": cands[0][0] if cands else None})
    return out


def mnl_eval(pairs, mnl):
    by = {(r.ref_id, r.cand_id): (r.match_weight, r.match_probability)
          for r in pairs.itertuples(index=False)}
    out = []
    for g in mnl:
        w, p = by.get((g["ref_id"], f"cr::{g['bad_doi']}"), (None, None))
        out.append({"ref_id": g["ref_id"], "kind": g["kind"], "bad_doi": g["bad_doi"],
                    "match_weight": w, "match_probability": p})
    return out


def _stats(vals):
    v = [x for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return {"n": 0}
    v = sorted(v)
    return {"n": len(v), "min": v[0], "median": v[len(v) // 2], "max": v[-1],
            "mean": sum(v) / len(v)}


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="match probability treated as 'a match' when scoring must-not-links")
    ap.add_argument("--out", default=str(REPORTS / "litkb_splink_2026-09-15.json"))
    args = ap.parse_args(argv)

    gold = load_gold()
    gold_sha = hashlib.sha256(GOLD.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    print(f"gold sha256 {gold_sha}")
    print(json.dumps(gold["counts"], indent=2))

    left = left_rows(gold)
    right, n_corpus = right_rows()
    right_dois = {r["doi"] for r in right if r["doi"]}
    print(f"left {len(left)} rows; right {len(right)} rows "
          f"({len(right) - n_corpus} cached Crossref records + {n_corpus} corpus works)")

    result = {"gold_sha256": gold_sha, "left_rows": len(left), "right_rows": len(right),
              "right_crossref": len(right) - n_corpus, "right_corpus_works": n_corpus,
              "threshold": args.threshold}

    # ---------------- Task A --------------------------------------------------------
    linker, preds, notes = run_link(left, right)
    result["em_notes"] = notes
    result["lambda"] = prior(linker)
    result["match_weights"] = match_weights(linker)
    pairs = pair_frame(preds)
    result["task_a"] = {"pairs_scored": int(len(pairs))}

    ranks = rank_eval(pairs, gold["positives"], right_dois)
    present = [r for r in ranks if r["gold_on_right"]]
    result["task_a"].update({
        "positives": len(ranks),
        "gold_doi_absent_from_right": len(ranks) - len(present),
        "rank1": sum(1 for r in present if r["rank"] == 1),
        "rank_top3": sum(1 for r in present if r["rank"] and r["rank"] <= 3),
        "not_retrieved_though_present": sum(1 for r in present if r["rank"] is None),
        "scored_population": len(present),
        "weight_of_gold": _stats([r["match_weight"] for r in present]),
    })

    # --- against the current resolver, on the SAME rows ------------------------------
    # The 365 positives are the rows the resolver already got. The interesting population is
    # the 293 it did not: what does Splink put first there, and with what confidence? A
    # ranking layer that only re-ranks the rows already solved is worth nothing.
    import csv as _csv
    refs_by_id = {f"{r['citing_work_key']}::{r['ref_key']}": r
                  for r in (json.loads(l) for l in (P6 / "references.jsonl").open(encoding="utf-8"))}
    top = {}
    for r in pairs.itertuples(index=False):
        cur = top.get(r.ref_id)
        if cur is None or r.match_weight > cur[0]:
            top[r.ref_id] = (r.match_weight, r.cand_id, r.match_probability)
    by_state = {}
    rows_csv = []
    for rid, ref in refs_by_id.items():
        st = ref["resolution"]
        w, cid, p = top.get(rid, (None, None, None))
        cand_doi = cid[4:] if cid and cid.startswith("cr::") else ""
        agree = bool(cand_doi and norm_doi(ref.get("resolved_doi")) == cand_doi)
        b = by_state.setdefault(st, {"n": 0, "splink_has_candidate": 0, "splink_p_ge_0.5": 0,
                                     "splink_p_ge_0.9": 0, "agrees_with_resolver": 0})
        b["n"] += 1
        if cid:
            b["splink_has_candidate"] += 1
            if p >= 0.5:
                b["splink_p_ge_0.5"] += 1
            if p >= 0.9:
                b["splink_p_ge_0.9"] += 1
        if agree:
            b["agrees_with_resolver"] += 1
        rows_csv.append({"ref_id": rid, "resolver_state": st,
                         "resolver_doi": norm_doi(ref.get("resolved_doi")),
                         "resolver_reason": (ref.get("resolution_detail") or {}).get("reason", ""),
                         "splink_top_candidate": cid or "", "splink_match_weight": w,
                         "splink_match_probability": p, "agrees_with_resolver": agree})
    result["vs_resolver"] = by_state
    cpath = REPORTS / "litkb_splink_vs_resolver_2026-09-15.csv"
    with cpath.open("w", newline="", encoding="utf-8") as fh:
        wtr = _csv.DictWriter(fh, fieldnames=list(rows_csv[0]))
        wtr.writeheader()
        wtr.writerows(rows_csv)
    print(f"wrote {cpath}")

    lost = rank_eval(pairs, gold["lost_genuine"], right_dois)
    mnl = mnl_eval(pairs, gold["must_not_link"])
    reviews = [m for m in mnl if m["kind"] == "book_review"]
    editions = [m for m in mnl if m["kind"] == "edition"]
    mutants = [m for m in mnl if m["kind"].startswith("mutation_")]
    above = lambda rows: sum(1 for m in rows                      # noqa: E731
                            if m["match_probability"] is not None
                            and m["match_probability"] >= args.threshold)
    result["must_not_link"] = {
        "book_review": {"n": len(reviews), "above_threshold": above(reviews),
                        "weights": [m["match_weight"] for m in reviews],
                        "probabilities": [m["match_probability"] for m in reviews]},
        "edition": {"n": len(editions), "above_threshold": above(editions),
                    "weights": [m["match_weight"] for m in editions]},
        "mutations": {"n": len(mutants), "above_threshold": above(mutants),
                      "weight_stats": _stats([m["match_weight"] for m in mutants])},
    }

    # ---------------- Task C --------------------------------------------------------
    result["task_c"] = {
        "lost_genuine": lost,
        "book_review": reviews,
        "lost_weight_stats": _stats([r["match_weight"] for r in lost]),
        "review_weight_stats": _stats([m["match_weight"] for m in reviews]),
    }
    lw = [r["match_weight"] for r in lost if r["match_weight"] is not None]
    rw = [m["match_weight"] for m in reviews if m["match_weight"] is not None]
    result["task_c"]["separable"] = bool(lw and rw and min(lw) > max(rw))

    # ---------------- kills ---------------------------------------------------------
    kills = {}
    review_gold = [m for m in gold["must_not_link"] if m["kind"] == "book_review"]
    ablations = {}
    for name, kw in (("no_author", dict(with_author=False)),
                     ("no_journal", dict(with_journal=False)),
                     ("no_author_no_journal", dict(with_author=False, with_journal=False))):
        _, pa, _ = run_link(left, right, **kw)
        rv = mnl_eval(pair_frame(pa), review_gold)
        ablations[name] = {"reviews_above_threshold": above(rv),
                           "weights": [m["match_weight"] for m in rv],
                           "probabilities": [m["match_probability"] for m in rv]}
    kills["ablation"] = {
        "reviews_above_threshold_full_model": above(reviews),
        "full_model_weights": [m["match_weight"] for m in reviews],
        **ablations,
        # The kill as the brief stated it -- drop the first author and the reviews must become
        # matches -- DID NOT FIRE. The feature that carries the weight is the JOURNAL, not the
        # author: the reference parses a publisher ("john wiley", "cambridge university press")
        # where Crossref has a journal ("technometrics", "geographical review"). Dropping both
        # is the ablation that has to fire for the model to be shown to depend on any of this.
        "FIRED_on_author_alone": ablations["no_author"]["reviews_above_threshold"] > above(reviews),
        "FIRED_on_journal_alone": ablations["no_journal"]["reviews_above_threshold"] > above(reviews),
        "FIRED_on_both": ablations["no_author_no_journal"]["reviews_above_threshold"] > above(reviews),
    }

    # blocking kill: a small sample, cartesian vs blocked, recall must not change
    sample_ids = [g["ref_id"] for g in gold["positives"][:60]]
    sset = set(sample_ids)
    lsub = [r for r in left if r["unique_id"] in sset]
    gsub = [g for g in gold["positives"] if g["ref_id"] in sset]
    need = {f"cr::{g['gold_doi']}" for g in gsub}
    rsub = [r for r in right if r["unique_id"] in need][:400]
    rsub_ids = {r["unique_id"] for r in rsub}
    rsub += [r for r in right if r["unique_id"] not in rsub_ids][:600]
    rec = {}
    for blocking in (True, False):
        _, pr, _ = run_link(lsub, rsub, blocking=blocking)
        rk = rank_eval(pair_frame(pr), gsub, {r["doi"] for r in rsub if r["doi"]})
        rec[str(blocking)] = sum(1 for r in rk if r["rank"] is not None)
    kills["drop_blocking"] = {"sample_left": len(lsub), "sample_right": len(rsub),
                              "retrieved_blocked": rec["True"], "retrieved_cartesian": rec["False"],
                              "FIRED": rec["True"] == rec["False"]}
    result["kills"] = kills

    # ---------------- Task B: dedupe over the 348 works -----------------------------
    # The model is TRANSFERRED from Task A, not re-estimated here, and that is a finding
    # rather than a convenience. Trained in place on these 348 rows, EM has nothing to learn
    # from: the corpus was already deduplicated at admission, so it contains approximately
    # zero true duplicate pairs, `block_on("title")` matches no pair, lambda collapses to 0.0
    # and the m-probabilities come back nonsensical (year EXACT m=0.0 while year +/-3 m=1.0).
    # Every pair then scores near -1000. Those numbers are recorded below under
    # "in_place_em_degenerate" because a degenerate fit that is quietly replaced is exactly
    # the kind of thing CLAUDE.md 3.4c exists to stop being hidden.
    works = [r for r in right if r["row_kind"] == "work"]
    import pandas as pd
    from splink import DuckDBAPI, Linker

    model_path = Path(args.out).with_name("litkb_splink_model_2026-09-15.json")
    linker.misc.save_model_to_json(str(model_path), overwrite=True)
    dcfg = json.loads(model_path.read_text(encoding="utf-8"))
    dcfg["link_type"] = "dedupe_only"
    dpath = model_path.with_name("litkb_splink_model_dedupe.json")
    dpath.write_text(json.dumps(dcfg), encoding="utf-8")

    dl_em = Linker(pd.DataFrame(works), settings("dedupe_only"), db_api=DuckDBAPI())
    dnotes = train(dl_em)
    degenerate = {"lambda": prior(dl_em), "em_notes": dnotes,
                  "match_weights": match_weights(dl_em)}

    dl = Linker(pd.DataFrame(works), str(dpath), db_api=DuckDBAPI())
    dpred = dl.inference.predict(threshold_match_probability=0.5).as_pandas_dataframe()
    clusters = dl.clustering.cluster_pairwise_predictions_at_threshold(
        dl.inference.predict(threshold_match_probability=0.0), 0.95).as_pandas_dataframe()
    sizes = clusters.groupby("cluster_id").size()
    dup_scores = []
    key = {}
    import csv as _csv
    for r in _csv.DictReader((EXPORT / "literature_tracker.csv").open(encoding="utf-8-sig")):
        key[r["ID"]] = r["litkb_key"]
    dmap = {(min(a, b), max(a, b)): (w, p) for a, b, w, p in
            zip(dpred["unique_id_l"], dpred["unique_id_r"],
                dpred["match_weight"], dpred["match_probability"])}
    allp = dl.inference.predict(threshold_match_probability=0.0).as_pandas_dataframe()
    amap = {(min(a, b), max(a, b)): (w, p) for a, b, w, p in
            zip(allp["unique_id_l"], allp["unique_id_r"],
                allp["match_weight"], allp["match_probability"])}
    for g in gold["duplicate_pairs"]:
        a, b = f"work::{g['left_key']}", f"work::{g['right_key']}"
        k = (min(a, b), max(a, b))
        w, p = amap.get(k, (None, None))
        dup_scores.append({"left_id": g["left_id"], "right_id": g["right_id"],
                           "verdict": g["verdict"], "left_key": g["left_key"],
                           "right_key": g["right_key"], "both_admitted": bool(g["left_key"] and g["right_key"]),
                           "match_weight": w, "match_probability": p,
                           "above_0.5": bool(p is not None and p >= 0.5)})
    result["task_b"] = {
        "works": len(works), "model": "transferred from Task A (see comment)",
        "lambda": prior(dl), "in_place_em_degenerate": degenerate,
        "pairs_above_0.5": int(len(dpred)),
        "clusters_at_0.95": int(sizes.shape[0]),
        "multi_member_clusters": int((sizes > 1).sum()),
        "largest_cluster": int(sizes.max()) if len(sizes) else 0,
        "gold_pairs": dup_scores,
        "pairs_above_0.5_detail": sorted(
            [{"a": a, "b": b, "match_weight": w, "match_probability": p}
             for a, b, w, p in zip(dpred["unique_id_l"], dpred["unique_id_r"],
                                   dpred["match_weight"], dpred["match_probability"])],
            key=lambda d: -d["match_weight"]),
    }

    Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "task_c"}, indent=1, default=str)[:6000])
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
