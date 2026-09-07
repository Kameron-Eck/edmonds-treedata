"""ask.py — one question, one answer. The front door to everything measured.

THE PROBLEM THIS SOLVES. As of 2026-09-06 the project records almost everything it
does: 37 acquisitions, 71 tile sets, 535 runs, 87 PR curves, 43 registry entries. Read
raw, that context layer is ~115,000 tokens of CSV, so no session ever opens it, and
"the data exists" quietly stopped meaning "the data is in reach". Orientation still
cost a session four documents and a guess about which of eight artifacts to open.

    py -3.12 qc/ask.py 2016            an acquisition: imagery, tiles, runs, best arm
    py -3.12 qc/ask.py t1_2016_base    an arm: its curve, its cuts, what trained it
    py -3.12 qc/ask.py panel_a         a registry entry: verdict, pointers, provenance
    py -3.12 qc/ask.py 742fe8d54c43    a tile set: knobs, split, who used it
    py -3.12 qc/ask.py --gaps          what the archive does NOT know yet

The subject type is detected, not declared. Everything printed is READ FROM a tracked
home at call time and the home is named, so an answer can be checked and never has to
be believed. Nothing here is a new fact store: this is a reading view, like
acquisition_passport.csv and experiments/INDEX.md.

READS ONLY TRACKED FILES — no lake, no GPU, works from a bare checkout.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

RULE = "─" * 78


def rows(path):
    p = Path(path)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _catalog():
    try:
        from phase4seg import config
        return {e["label"]: e for e in config.YEAR_CATALOG}
    except Exception:
        return {}


def _champions():
    try:
        import champion
        return champion.load_champions()
    except Exception:
        return {}


def _index():
    p = SCRIPTS / "experiments" / "index.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("entries", [])


def _fmt_int(v):
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v or "—")


def _section(out, title):
    out.append("")
    out.append(f"── {title} {'─' * max(0, 74 - len(title))}")


# ------------------------------------------------------------------ subjects

def answer_year(label, out):
    cat, champs = _catalog(), _champions()
    e = cat.get(label, {})
    out.append(f"ACQUISITION {label}" + (f"   ★ champion arm: {champs[label]}"
                                         if champs.get(label) else
                                         "   (no champion designated)"))
    if e:
        out.append(f"  {e.get('gsd_cm')} cm nominal · {e.get('bands')} bands · "
                   f"{e.get('epsg', '?')}   [phase4seg config.YEAR_CATALOG]")
    passport = [r for r in rows(QC / "acquisition_passport.csv")
                if r.get("label") == label or r.get("year") == label]
    for p in passport[:1]:
        bits = [f"{k}={v}" for k, v in p.items()
                if k in ("acq_date", "effective_cm", "source", "program", "crs_epsg")
                and v]
        if bits:
            out.append("  " + " · ".join(bits) + "   [acquisition_passport.csv]")

    ts = [t for t in rows(QC / "tileset_registry.csv") if t["label"] == label]
    _section(out, "TILES")
    if not ts:
        out.append("  never tiled")
    for t in ts:
        out.append(f"  {t['tileset_id'] or '(no id)'}  {t['tile_dir']:34} "
                   f"{_fmt_int(t['n_tiles']):>6} tiles "
                   f"(train {t['n_train']} / val {t['n_val']} / test {t['n_test']})"
                   f"  split={t['split_mode'] or '?'}")
    if ts:
        out.append(f"  tile lists: phase4/qc/tilesets/<id>.csv     "
                   f"[tileset_registry.csv]")

    runs = [r for r in rows(QC / "run_passport.csv") if label in r["years"].split(",")]
    _section(out, f"RUNS ({len(runs)})")
    for r in runs[-6:]:
        out.append(f"  {r['date']}  {r['step']:10} {r['run_tag'] or '(untagged)':22} "
                   f"{r['gpu'][:18] or 'cpu':18} git {r['git_sha'][:8]}"
                   f"{' DIRTY' if r['git_dirty'] == 'true' else ''}")
    if len(runs) > 6:
        out.append(f"  … {len(runs) - 6} earlier   [run_passport.csv]")

    m = [x for x in rows(QC / "arm_metrics.csv") if x["year"] == label]
    _section(out, "PERFORMANCE — matched_p75 (recall at precision ≥ .75)")
    mp = sorted([x for x in m if x["policy"] == "matched_p75"],
                key=lambda x: -(float(x["recall"]) if x["recall"] else -1))
    if not mp:
        out.append("  never scored at a matched cut")
    for x in mp[:8]:
        star = " ★" if champs.get(label) == x["run_tag"] else ""
        out.append(f"  {x['run_tag'] or '(untagged)':22}{star:2} rec {x['recall']:>6} "
                   f"prec {x['precision']:>6}  thr {x['thresh']:>9}  "
                   f"AP {x['pr_auc'] or '—':>6}  pop {_fmt_int(x['population']):>13}  "
                   f"[{x['ref']} / {x['eval_scope'] or 'citywide'}]")
    if mp:
        out.append("  ranked ONLY within one (ref, scope); populations differ "
                   "— see year_scoreboard.md")

    ents = [e for e in _index()
            if label in [str(i.get("label", i)) if isinstance(i, dict) else str(i)
                         for i in (e.get("imagery") or [])]
            or any(str(a.get("year")) == label for a in (e.get("arms") or []))]
    _section(out, f"WHAT WE CONCLUDED ({len(ents)} registry entries)")
    for e in ents[:8]:
        out.append(f"  [{e['status']:9}] {e['name']:32} {(e['headline'] or '')[:70]}")
    if ents:
        out.append("  full entries: experiments/<name>.yaml   [experiments/INDEX.md]")

    fails = [f for f in rows(QC / "failure_registry.csv")
             if label in (f.get("years") or "")]
    if fails:
        _section(out, "KNOWN FAILURES ON THIS YEAR")
        for f in fails[:5]:
            out.append(f"  {f['exception_class']:26} x{f['n_occurrences']:<3} "
                       f"{f['status']:11} {(f.get('cause') or 'UNDIAGNOSED')[:44]}")


def answer_arm(tag, out):
    champs = _champions()
    m = [x for x in rows(QC / "arm_metrics.csv") if x["run_tag"] == tag]
    ts = [t for t in rows(QC / "tileset_registry.csv") if t["run_tag"] == tag]
    runs = [r for r in rows(QC / "run_passport.csv") if r["run_tag"] == tag]
    year = (m or ts or runs)[0].get("year") or (ts[0]["label"] if ts else "")
    star = " ★ CHAMPION" if champs.get(year) == tag else ""
    out.append(f"ARM {tag}   year {year or '?'}{star}")

    _section(out, "OPERATING POINTS — every cut this arm has been read at")
    if not m:
        out.append("  never scored")
    for grp in sorted({(x["ref"], x["eval_scope"]) for x in m}):
        out.append(f"  ref {grp[0]} · scope {grp[1] or 'citywide'}")
        for x in sorted([y for y in m if (y["ref"], y["eval_scope"]) == grp],
                        key=lambda y: y["policy"]):
            out.append(f"    {x['policy']:14} rec {x['recall']:>6} "
                       f"prec {x['precision']:>6}  thr {x['thresh']:>9}  "
                       f"cuts {x['n_eligible_cuts'] or '—':>4}  "
                       f"pop {_fmt_int(x['population']):>13}")
        cf = next((y["curve_file"] for y in m
                   if (y["ref"], y["eval_scope"]) == grp and y["curve_file"]), "")
        if cf:
            out.append(f"    full curve: {cf}")
    out.append("  a pair without its policy and population is not a measurement")

    _section(out, "TRAINED ON")
    for t in ts:
        out.append(f"  tileset {t['tileset_id']}  {_fmt_int(t['n_tiles'])} tiles "
                   f"(train {t['n_train']})  ortho {t['ortho_name'] or '?'}  "
                   f"hs={t['hs_source'] or '—'}  split={t['split_mode'] or '?'}")
        out.append(f"  which tiles: phase4/qc/tilesets/{t['tileset_id']}.csv")
    if not ts:
        out.append("  no tile set recorded for this tag")

    _section(out, f"RUNS ({len(runs)})")
    for r in runs:
        out.append(f"  {r['date']}  {r['step']:10} seed {r['seed']}/{r['split_seed']} "
                   f"{r['arch']}/{r['encoder']}  git {r['git_sha'][:8]} "
                   f"join={r['join_basis']}")

    owner = [e for e in _index()
             if any(a.get("tag") == tag for a in (e.get("arms") or []))]
    if owner:
        _section(out, "OWNED BY")
        for e in owner:
            out.append(f"  {e['name']} [{e['status']}] — {(e['headline'] or '')[:64]}")


def answer_entry(entry, out):
    out.append(f"REGISTRY ENTRY {entry['name']}   [{entry['kind']} · {entry['status']}"
               f"{' · retrospective' if entry['retrospective'] else ''}]")
    if entry.get("decided"):
        out.append(f"  decided {entry['decided']}")
    if entry.get("n"):
        out.append(f"  N = {entry['n']}   [{entry.get('n_source')}]")
    _section(out, "VERDICT")
    for line in (entry.get("verdict") or "(none — undecided)").split("\n"):
        out.append("  " + line.strip()[:100])
    _section(out, "POINTERS")
    for k in ("design_doc", "reports", "instruments", "inputs", "outputs"):
        v = entry.get(k)
        if v:
            out.append(f"  {k:12} {v if isinstance(v, str) else ', '.join(v)}")
    for k in ("supersedes", "superseded_by", "tilesets", "run_ids"):
        if entry.get(k):
            out.append(f"  {k:12} {', '.join(entry[k])[:96]}")
    if entry.get("arm_scores"):
        _section(out, "ARM SCORES (resolved at build time)")
        for tag, pts in list(entry["arm_scores"].items())[:6]:
            for pol, d in list(pts.items())[:2]:
                out.append(f"  {tag:22} {pol:14} rec {d.get('recall')} "
                           f"prec {d.get('precision')} @ {d.get('thresh')}")


def answer_tileset(tsid, out):
    ts = [t for t in rows(QC / "tileset_registry.csv") if t["tileset_id"] == tsid]
    if not ts:
        return False
    t0 = ts[0]
    out.append(f"TILE SET {tsid}   {_fmt_int(t0['n_tiles'])} tiles "
               f"(train {t0['n_train']} / val {t0['n_val']} / test {t0['n_test']})")
    out.append(f"  ortho {t0['ortho_name']}  labels {t0['label_source'] or '—'}  "
               f"tile_size {t0['tile_size']}  stride {t0['stride']}  "
               f"hs={t0['hs_source'] or '—'}")
    out.append(f"  split {t0['split_mode'] or '?'} · {t0['blocks'] or '?'} blocks "
               f"of {t0['block_px'] or '?'} px"
               f"{'  DEGRADED' if t0['split_degraded'] == 'True' else ''}")
    _section(out, f"USED BY {len(ts)} ARM(S) — same id means the same tiles")
    for t in ts:
        out.append(f"  {t['label']:8} {t['run_tag'] or '(untagged)'}")
    if len(ts) > 1:
        out.append("  these arms are directly comparable: identical tiles and split")
    out.append(f"\n  which tiles: phase4/qc/tilesets/{tsid}.csv")
    return True


# ------------------------------------------------------------------ the gaps

def answer_gaps(out):
    cat = _catalog()
    champs = _champions()
    scored = {x["year"] for x in rows(QC / "arm_metrics.csv")}
    tiled = {t["label"] for t in rows(QC / "tileset_registry.csv")}
    matched = {x["year"] for x in rows(QC / "arm_metrics.csv")
               if x["policy"] == "matched_p75"}
    labels = sorted(cat)
    out.append(f"WHAT THE ARCHIVE DOES NOT KNOW YET   ({len(labels)} acquisitions)")
    out.append("")
    out.append(f"  never tiled            {len(labels) - len(set(labels) & tiled):>3}"
               f"   {', '.join(sorted(set(labels) - tiled)) or '—'}")
    out.append(f"  never scored           {len(labels) - len(set(labels) & scored):>3}"
               f"   {', '.join(sorted(set(labels) - scored)) or '—'}")
    out.append(f"  no matched-cut read    "
               f"{len(labels) - len(set(labels) & matched):>3}"
               f"   {', '.join(sorted(set(labels) - matched)) or '—'}")
    out.append(f"  no champion            "
               f"{len(labels) - len(set(labels) & set(champs)):>3}"
               f"   {', '.join(sorted(set(labels) - set(champs))) or '—'}")
    _section(out, "UNDIAGNOSED FAILURES (symptom recorded, cause not written down)")
    und = [f for f in rows(QC / "failure_registry.csv")
           if not (f.get("cause") or "").strip()]
    if not und:
        out.append("  none — every recorded failure has a cause on file")
    for f in und[:10]:
        out.append(f"  {f['exception_class']:26} x{f['n_occurrences']:<3} "
                   f"last {f['last_seen']}  {f['example_log'][:44]}")
    _section(out, "REGISTRY ENTRIES AWAITING KAM")
    for e in _index():
        if e["status"] == "needs-kam":
            out.append(f"  {e['name']:34} {(e['headline'] or '')[:60]}")
    out.append("")
    out.append("  Deliberate exclusions are NOT distinguished from oversights here —")
    out.append("  that judgement is Kam's. See experiments/BACKFILL_RECONCILIATION.md")
    out.append("  for the same distinction applied to the registry backfill.")


# ------------------------------------------------------------------ dispatch

def resolve(subject):
    """Return (kind, payload). Detection order is most-specific first."""
    if subject in _catalog():
        return "year", subject
    ts = {t["tileset_id"] for t in rows(QC / "tileset_registry.csv") if t["tileset_id"]}
    if subject in ts:
        return "tileset", subject
    for e in _index():
        if e["name"] == subject:
            return "entry", e
    tags = {x["run_tag"] for x in rows(QC / "arm_metrics.csv") if x["run_tag"]}
    tags |= {t["run_tag"] for t in rows(QC / "tileset_registry.csv") if t["run_tag"]}
    tags |= {r["run_tag"] for r in rows(QC / "run_passport.csv") if r["run_tag"]}
    if subject in tags:
        return "arm", subject
    return "unknown", subject


def suggest(subject, out):
    out.append(f"No exact subject named {subject!r}. Near matches:")
    pool = []
    pool += [(f"acquisition  {k}", k) for k in _catalog()]
    pool += [(f"entry        {e['name']}", e["name"]) for e in _index()]
    pool += [(f"arm          {t}", t) for t in
             sorted({x["run_tag"] for x in rows(QC / "arm_metrics.csv") if x["run_tag"]})]
    s = subject.lower()
    hits = [label for label, key in pool if s in key.lower()]
    for h in hits[:15]:
        out.append("  " + h)
    if not hits:
        out.append("  (none) — try: py -3.12 qc/ask.py --list")


def listing(out):
    out.append("SUBJECTS")
    out.append("  acquisitions: " + " ".join(sorted(_catalog())))
    out.append("")
    out.append("  entries:      " + " ".join(sorted(e["name"] for e in _index())))
    out.append("")
    tags = sorted({x["run_tag"] for x in rows(QC / "arm_metrics.csv") if x["run_tag"]})
    out.append(f"  arms ({len(tags)}):    " + " ".join(tags[:40]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("subject", nargs="?", help="acquisition, arm tag, entry, tileset id")
    ap.add_argument("--gaps", action="store_true", help="what is NOT known yet")
    ap.add_argument("--list", action="store_true", help="list every subject")
    a = ap.parse_args(argv)

    out = []
    if a.gaps:
        answer_gaps(out)
    elif a.list:
        listing(out)
    elif not a.subject:
        ap.print_help()
        return 0
    else:
        kind, payload = resolve(a.subject)
        if kind == "year":
            answer_year(payload, out)
        elif kind == "tileset":
            answer_tileset(payload, out)
        elif kind == "entry":
            answer_entry(payload, out)
        elif kind == "arm":
            answer_arm(payload, out)
        else:
            suggest(payload, out)

    print(RULE)
    print("\n".join(out))
    print(RULE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
