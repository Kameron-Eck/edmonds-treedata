"""experiments_index.py — the GENERATED layer of the experiment registry.

The AUTHORED layer is `experiments/*.yaml`: pointers, never restated numbers
(schema: experiments/README.md). This script loads every entry, joins it against
the measured homes at build time, and writes:

    experiments/INDEX.md     scannable — one row per entry, resolved values
    experiments/index.json   machine — the full join

Restating a value is illegal in the authored layer and legal here, because here
it is HARVESTED: every number in the outputs is read from its measured home at
build time, and `test_experiments.py::test_index_is_fresh` regenerates both
files and fails on drift. Same pattern as phase4/qc/acquisition_passport.csv.

Joined homes (all tracked in the repo — a bare checkout regenerates identically):
    run_registry.csv                     what ran, when
    phase4/qc/qc_indep_report.csv        honest scored results (live=1)
    phase4/qc/tier1_results.csv          Tier-1 arm metrics at matched precision
    pipeline/champion_arms.csv           which arm is the deliverable per year
    phase4seg config.YEAR_CATALOG        imagery labels -> gsd/bands

Run after ANY edit under experiments/:   py -3.12 qc/experiments_index.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
EXP_DIR = SCRIPTS / "experiments"

# Prefixes that mark a pointer as NOT repo-relative: the data lake (both mounts),
# absolute local mirrors, URLs, globs. Legitimate provenance, unverifiable from a
# checkout. test_experiments.py imports this — one home.
_UNCHECKABLE = ("G:", "/content/", "D:", "http", "~")


# ---------------------------------------------------------------- n / n_source

def resolve_n(source, root=REPO):
    """Resolve an `n_source` pointer to an integer. Grammar in experiments/README.md.

    Returns None when the pointer cannot be resolved from a checkout (missing file,
    lake path) — the caller decides whether that is a failure. Raises ValueError on a
    malformed pointer, which IS always a failure.
    """
    if "#" not in str(source):
        raise ValueError(f"n_source {source!r} has no '#<selector>'")
    rel, sel = str(source).rsplit("#", 1)
    if rel.startswith(_UNCHECKABLE):
        return None
    p = root / rel
    if not p.exists():
        p = SCRIPTS / rel                       # bare names resolve under Scripts/
    if not p.exists():
        return None
    if sel == "lines":
        return sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.lstrip().startswith("#"))
    if sel.startswith("json:"):
        val = json.loads(p.read_text(encoding="utf-8"))[sel[5:]]
        return int(val)
    if sel == "rows" or sel.startswith("rows:"):
        # `#` comment lines are stripped before the header is read — champion_arms.csv
        # style banners would otherwise be parsed as data.
        body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
        rows = list(csv.DictReader(body))
        if sel == "rows":
            return len(rows)
        col, _, want = sel[5:].partition("=")
        return sum(1 for r in rows if str(r.get(col, "")).strip() == want)
    raise ValueError(f"n_source {source!r}: unknown selector {sel!r}")


# ---------------------------------------------------------------- measured homes

def _csv_rows(path):
    if not path.exists():
        return []
    body = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _load_homes():
    import champion
    from phase4seg import config

    registry = _csv_rows(SCRIPTS / "run_registry.csv")
    indep = [r for r in _csv_rows(REPO / "phase4" / "qc" / "qc_indep_report.csv")
             if r.get("live", "").strip() == "1"]
    tier1 = {(r["year"], r["tag"]): r
             for r in _csv_rows(REPO / "phase4" / "qc" / "tier1_results.csv")}
    champs = champion.load_champions()          # year label -> champion tag
    catalog = {e["label"]: e for e in config.YEAR_CATALOG}
    return registry, indep, tier1, champs, catalog


# ---------------------------------------------------------------- the join

def _first_sentence(text, cap=200):
    if not text:
        return ""
    s = " ".join(str(text).split())
    for stop in (". ", "; "):
        i = s.find(stop)
        if 0 < i < cap:
            return s[: i + 1]
    return s[:cap] + ("…" if len(s) > cap else "")


def build():
    """Return the joined registry: a list of dicts, one per entry, sorted."""
    registry, indep, tier1, champs, catalog = _load_homes()
    indep_by_tag = {}
    for r in indep:
        indep_by_tag.setdefault(r.get("run_tag", "").strip(), []).append(r)

    entries = []
    for path in sorted(EXP_DIR.glob("*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        name = spec.get("name", path.stem)
        arms = spec.get("arms") or []
        tags = [a.get("tag") for a in arms if isinstance(a, dict) and a.get("tag")]

        # run_registry: rows naming any owned tag or listed run_id
        rids = {str(r) for r in (spec.get("run_ids") or [])}
        reg_rows = [r for r in registry
                    if r["run_id"] in rids or any(t in r["run_id"] for t in tags)]
        reg_dates = sorted(r["date"] for r in reg_rows if r.get("date"))

        # scored results for owned tags
        arm_scores = {}
        for t in tags:
            row = tier1.get((next((a["year"] for a in arms if a.get("tag") == t), ""), t))
            if row:
                arm_scores[t] = {"recall_at_p75": row["recall_at_p75"],
                                 "prec_at_p75": row["prec_at_p75"], "home": "tier1_results.csv"}
            elif indep_by_tag.get(t):
                r = indep_by_tag[t][0]
                arm_scores[t] = {"recall": r["recall"], "precision": r["precision"],
                                 "ref": r["ref"], "home": "qc_indep_report.csv"}

        champion_tags = sorted(t for a in arms for t in [a.get("tag")]
                               if t and champs.get(str(a.get("year"))) == t)

        imagery = [str(l) for l in (spec.get("imagery") or [])]
        imagery_resolved = [{"label": l,
                            "gsd_cm": catalog[l]["gsd_cm"],
                            "bands": catalog[l]["bands"]}
                           for l in imagery if l in catalog]

        n = spec.get("n")
        entries.append({
            "name": name,
            "kind": spec.get("kind", "experiment"),
            "status": spec.get("status"),
            "retrospective": bool(spec.get("retrospective", False)),
            "decided": str(spec.get("decided")) if spec.get("decided") else None,
            "category": spec.get("category"),
            "tags": spec.get("tags") or [],
            "hypothesis": spec.get("hypothesis"),
            "decision_rule": spec.get("decision_rule"),
            "verdict": spec.get("verdict"),
            "headline": _first_sentence(spec.get("verdict") or spec.get("hypothesis")),
            "n": n,
            "n_source": spec.get("n_source"),
            "sample": spec.get("sample"),
            "arms": arms,
            "arm_scores": arm_scores,
            "champion_tags": champion_tags,
            "imagery": imagery_resolved or imagery,
            "metric": spec.get("metric"),
            "design_doc": spec.get("design_doc"),
            "reports": spec.get("reports") or [],
            "instruments": spec.get("instruments") or [],
            "inputs": spec.get("inputs") or [],
            "outputs": spec.get("outputs") or [],
            "run_ids": sorted(rids),
            "registry_rows": len(reg_rows),
            "last_run": reg_dates[-1] if reg_dates else None,
            "commit": spec.get("commit"),
            "supersedes": spec.get("supersedes") or [],
            "superseded_by": spec.get("superseded_by") or [],
            "extra": spec.get("extra") or {},
        })

    # newest decided first; undecided after, alphabetical
    entries.sort(key=lambda e: (e["decided"] is None, e["decided"] or "", e["name"]),
                 reverse=False)
    entries.sort(key=lambda e: e["decided"] or "", reverse=True)
    entries.sort(key=lambda e: e["decided"] is None)
    return entries


# ---------------------------------------------------------------- rendering

def render():
    """Return (index_md, index_json) as strings. Deterministic — no timestamps."""
    entries = build()
    by_status = {}
    for e in entries:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    counts = " · ".join(f"{v} {k}" for k, v in sorted(by_status.items()))

    md = []
    md.append("# EXPERIMENT REGISTRY INDEX — GENERATED, do not edit")
    md.append("")
    md.append(f"Regenerate: `py -3.12 qc/experiments_index.py` "
              f"(drift-gated by `test_experiments.py::test_index_is_fresh`).")
    md.append(f"Authored layer + schema: this directory's `README.md`. "
              f"{len(entries)} entries: {counts}.")
    md.append("")

    pending = [e for e in entries if e["status"] == "needs-kam"]
    if pending:
        md.append("## Awaiting Kam sign-off")
        md.append("")
        for e in pending:
            why = e["extra"].get("needs_kam_reason") or e["headline"]
            md.append(f"- **{e['name']}** — {_first_sentence(why, 160)}")
        md.append("")

    md.append("## All entries (newest decided first)")
    md.append("")
    md.append("| entry | kind | status | decided | N | imagery | headline |")
    md.append("|---|---|---|---|---|---|---|")
    for e in entries:
        img = ",".join(i["label"] if isinstance(i, dict) else str(i)
                       for i in e["imagery"]) or "—"
        star = " ★" if e["champion_tags"] else ""
        n = e["n"] if e["n"] is not None else "—"
        md.append(f"| {e['name']}{star} | {e['kind']} | {e['status']} "
                  f"| {e['decided'] or '—'} | {n} | {img} "
                  f"| {(e['headline'] or '').replace('|', '/')} |")
    md.append("")
    md.append("★ = owns a champion arm (pipeline/champion_arms.csv). "
              "N = the gated n/n_source pair. Full join: `index.json`; "
              "provenance + pointers: each entry's yaml.")
    md.append("")

    js = json.dumps({"entries": entries}, indent=2, sort_keys=True,
                    ensure_ascii=False, default=str) + "\n"
    return "\n".join(md), js


def main():
    md, js = render()
    (EXP_DIR / "INDEX.md").write_text(md, encoding="utf-8", newline="\n")
    (EXP_DIR / "index.json").write_text(js, encoding="utf-8", newline="\n")
    print(f"wrote {EXP_DIR / 'INDEX.md'} and index.json "
          f"({md.count(chr(10))} md lines)")


if __name__ == "__main__":
    main()
