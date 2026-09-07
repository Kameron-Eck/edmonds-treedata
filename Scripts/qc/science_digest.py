"""science_digest.py — ALL the science, in one file small enough to actually load.

THE CORRECTION THIS ENCODES (Kam, 2026-09-06): "the goal of the csv is to load all the
science into context — why is it 100,000 tokens?" Measured, the premise was mine and it
was wrong. The big CSVs are not the science. They are the AUDIT TRAIL, and they are
10.1x the size of the science they support:

    the science   (verdicts, rankings, claims, gaps, decisions)   ~10,600 tokens
    the audit trail (run_passport + arm_metrics + tileset_registry)  ~107,600 tokens

They are large because they are denormalised for joining, not written for reading:
54-76% of their cell bytes are values already present in another row (`label_source`
has 2 distinct values across 535 rows; `sig_keys` has 7 distinct values costing 20 KB
of a 45 KB file; gzip crushes all three from 420 KB to 44 KB). And they are COMPLETE
rather than selected — 528 operating points of which 87 are the matched-cut reads
anyone actually compares at, and 73 KB of argv nobody reads.

So the CSVs stay as they are: evidence you can check, joined by ask.py on demand. This
file is the other half — the conclusions, in one load, under ~8k tokens. Read it to
KNOW; query the CSVs to CHECK.

Derives only from tracked homes, so it regenerates from a bare checkout and is
byte-compared by test_run_context.py::test_science_digest_is_fresh.

Run:  py -3.12 qc/science_digest.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

POLICY = "matched_p75"


def _rows(p):
    p = Path(p)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _yaml(p, key):
    p = Path(p)
    if not p.exists():
        return []
    import yaml
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get(key, [])


def _index():
    p = SCRIPTS / "experiments" / "index.json"
    return (json.loads(p.read_text(encoding="utf-8")).get("entries", [])
            if p.exists() else [])


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build():
    import champion
    from phase4seg import config

    entries = _index()
    metrics = _rows(QC / "arm_metrics.csv")
    tiles = _rows(QC / "tileset_registry.csv")
    champs = champion.load_champions()
    cat = {e["label"]: e for e in config.YEAR_CATALOG}

    o = ["# SCIENCE DIGEST — everything concluded, in one load — GENERATED", "",
         "Regenerate: `py -3.12 qc/science_digest.py`. This is the KNOW half; the",
         "CSVs under `phase4/qc/` are the CHECK half — evidence, joined on demand by",
         "`py -3.12 qc/ask.py <subject>`. Reading them raw costs ~107k tokens and is",
         "never the right move: they are denormalised for joining and complete rather",
         "than selected. Everything below is resolved from them at build time.", ""]

    # ---------------------------------------------------------------- the answer
    o += ["## 1. What we can say about the canopy", ""]
    claims = _yaml(SCRIPTS / "claims.yaml", "claims")
    sys.path.insert(0, str(SCRIPTS / "qc"))          # ledger: test_status_discovery.py
    import claims as _c
    for cl in claims:
        state, detail = _c.verify(cl)
        mark = "" if state == "ok" else f"  **[{state.upper()}: {detail}]**"
        o.append(f"- **{cl['value']}** — {' '.join(cl['statement'].split())}{mark}")
        o.append(f"  <br>evidence `{cl['evidence']}`")
    o.append("")

    # ---------------------------------------------------------------- per year
    o += ["## 2. Best arm per year, at one held cut", "",
          f"Ranked at `{POLICY}` — highest recall while precision stays >= 0.75. A",
          "ranking is only meaningful at a held cut: at per-arm best-F1 every arm is",
          "best at something. `pop` is the scored population; **rows with different",
          "refs or populations are NOT comparable to each other** — that is a coverage",
          "difference, not a skill difference. Full detail: `phase4/qc/year_scoreboard.md`.",
          "",
          "| year | best arm | recall | prec | AP | ref / scope | pop | tiles |",
          "|---|---|---|---|---|---|---|---|"]
    by_year = {}
    for m in metrics:
        if m["policy"] != POLICY:
            continue
        by_year.setdefault(m["year"], []).append(m)
    tiles_by = {}
    for t in tiles:
        tiles_by.setdefault(t["label"], []).append(t)
    for year in sorted(by_year):
        best = max(by_year[year], key=lambda m: _f(m["recall"]) or -1)
        star = " ★" if champs.get(year) == best["run_tag"] else ""
        n_tiles = sum(int(t["n_tiles"]) for t in tiles_by.get(year, []))
        pop = f"{int(best['population']):,}" if best["population"] else "—"
        o.append(f"| {year} | {best['run_tag'] or '(untagged)'}{star} "
                 f"| {best['recall']} | {best['precision']} | {best['pr_auc'] or '—'} "
                 f"| {best['ref']} / {best['eval_scope'] or 'citywide'} "
                 f"| {pop} | {n_tiles or '—'} |")
    o += ["", f"{len(by_year)} of {len(cat)} acquisitions have a matched-cut read. "
              "★ = designated champion.", ""]

    # ---------------------------------------------------------------- verdicts
    done = [e for e in entries if e["status"] == "complete"]
    o += [f"## 3. What {len(done)} completed investigations concluded", ""]
    for e in sorted(done, key=lambda e: e["decided"] or "", reverse=True):
        o.append(f"- **{e['name']}** ({e['decided'] or 'n/d'}) — "
                 f"{' '.join((e['headline'] or '').split())}")
    o.append("")

    # ---------------------------------------------------------------- unknowns
    o += ["## 4. What is NOT known", ""]
    scored = set(by_year)
    tiled = set(tiles_by)
    labels = set(cat)
    o.append(f"- never tiled ({len(labels - tiled)}): "
             f"{', '.join(sorted(labels - tiled)) or 'none'}")
    o.append(f"- no matched-cut read ({len(labels - scored)}): "
             f"{', '.join(sorted(labels - scored)) or 'none'}")
    o.append(f"- no champion ({len(labels - set(champs))}): "
             f"{', '.join(sorted(labels - set(champs))) or 'none'}")
    pend = [e for e in entries if e["status"] == "needs-kam"]
    o.append(f"- results documented but UNSIGNED ({len(pend)}): "
             f"{', '.join(e['name'] for e in pend) or 'none'}")
    o += ["", "A gap here is a record, not a backlog — some acquisitions are "
              "deliberately out of scope. `phase4/qc/coverage_map.md` has the matrix.",
          ""]

    # ---------------------------------------------------------------- decisions
    ds = [d for d in _yaml(SCRIPTS / "decisions.yaml", "decisions")
          if d["status"] == "open"]
    ids = {d["id"] for d in ds}
    ready = [d for d in ds if not (set(d.get("blocked_by") or []) & ids)]
    o += [f"## 5. What is blocked, and on whom ({len(ds)} open)", "",
          f"**Ready now ({len(ready)}) — nothing above them:**", ""]
    for d in ready:
        o.append(f"- `{d['id']}` [{d['owner']}] — {' '.join(d['question'].split())[:110]}")
    o += ["", f"**Waiting ({len(ds) - len(ready)}):** " +
          ", ".join(f"`{d['id']}` after {', '.join(d.get('blocked_by') or [])}"
                    for d in ds if d not in ready), "",
          "Full entries with evidence: `py -3.12 qc/ask.py --decisions`.", ""]
    return "\n".join(o)


def main(argv=None):
    md = build()
    (SCRIPTS / "SCIENCE.md").write_text(md, encoding="utf-8", newline="\n")
    print(f"wrote Scripts/SCIENCE.md — {len(md) / 1024:.1f} KB "
          f"(~{len(md) // 4:,} tokens), {md.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
