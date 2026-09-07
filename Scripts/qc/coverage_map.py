"""coverage_map.py — the archive's own holes, per acquisition.

"What don't we know yet" is the question that should choose the next experiment, and
until now it was uncomputable without writing a throwaway script. This generates
`phase4/qc/coverage_map.md`: one row per acquisition, showing how far each one has
travelled — tiled, trained, scored, read at a held cut, given a champion, written up.

WHAT IT DOES NOT DO IS DECIDE. A blank cell means "no record", never "should have been
done": several acquisitions are deliberately out of scope (the Atlas trend is
2016→2024; some deliveries exist only as overlap controls). Distinguishing deliberate
from overlooked is Kam's call, and the file says so rather than implying a backlog.

Derives ONLY from tracked homes, so it regenerates identically from a bare checkout
and is byte-compared by test_run_context.py::test_coverage_map_is_fresh.

Run:  py -3.12 qc/coverage_map.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"


def _rows(path):
    p = Path(path)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def build():
    from phase4seg import config
    import champion

    cat = {e["label"]: e for e in config.YEAR_CATALOG}
    champs = champion.load_champions()
    tiles, metrics = _rows(QC / "tileset_registry.csv"), _rows(QC / "arm_metrics.csv")
    runs = _rows(QC / "run_passport.csv")

    tiled, trained = {}, {}
    for t in tiles:
        tiled.setdefault(t["label"], []).append(t)
    for r in runs:
        if r["step"] == "train":
            for y in r["years"].split(","):
                trained[y] = trained.get(y, 0) + 1
    scored, matched, aps = {}, {}, {}
    for m in metrics:
        scored.setdefault(m["year"], set()).add(m["run_tag"])
        if m["policy"] == "matched_p75":
            matched.setdefault(m["year"], []).append(m)
            if m["pr_auc"]:
                aps.setdefault(m["year"], []).append(float(m["pr_auc"]))

    import json
    idx = SCRIPTS / "experiments" / "index.json"
    entries = (json.loads(idx.read_text(encoding="utf-8")).get("entries", [])
               if idx.exists() else [])
    written = {}
    for e in entries:
        for im in (e.get("imagery") or []):
            lab = im.get("label") if isinstance(im, dict) else str(im)
            written[lab] = written.get(lab, 0) + 1

    out = ["# COVERAGE MAP — how far each acquisition has travelled — GENERATED", "",
           "Regenerate: `py -3.12 qc/coverage_map.py` "
           "(drift-gated by `test_run_context.py::test_coverage_map_is_fresh`).",
           "",
           "A blank cell means **no record**, never *should have been done*. Some",
           "acquisitions are deliberately out of scope — the Atlas trend is 2016→2024,",
           "and several deliveries exist only as overlap controls. Telling deliberate",
           "from overlooked is a decision, not a measurement, and this file does not",
           "make it. `py -3.12 qc/ask.py <label>` opens any single row in full.",
           "",
           "| acq | gsd | bands | tile sets | tiles | train runs | arms scored "
           "| matched cut | best AP | champion | entries |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]

    n_gap = {"tiled": 0, "scored": 0, "matched": 0, "champ": 0}
    for lab in sorted(cat):
        e = cat[lab]
        ts = tiled.get(lab, [])
        n_tiles = sum(int(t["n_tiles"]) for t in ts)
        arms = scored.get(lab, set())
        mp = matched.get(lab, [])
        best_ap = max(aps.get(lab, []), default=None)
        ch = champs.get(lab, "")
        if not ts:
            n_gap["tiled"] += 1
        if not arms:
            n_gap["scored"] += 1
        if not mp:
            n_gap["matched"] += 1
        if not ch:
            n_gap["champ"] += 1
        out.append(
            f"| {lab} | {e.get('gsd_cm')} | {e.get('bands')} "
            f"| {len(ts) or ''} | {n_tiles or ''} | {trained.get(lab, '') or ''} "
            f"| {len(arms) or ''} | {len(mp) or ''} "
            f"| {f'{best_ap:.4f}' if best_ap is not None else ''} "
            f"| {ch} | {written.get(lab, '') or ''} |")

    out += ["",
            f"**{len(cat)} acquisitions.** No tile set: **{n_gap['tiled']}** · "
            f"never scored: **{n_gap['scored']}** · no matched-cut read: "
            f"**{n_gap['matched']}** · no champion: **{n_gap['champ']}**.",
            "",
            "Columns: *tile sets* counts distinct sets (`tileset_registry.csv`); "
            "*tiles* sums them. *train runs* counts `step=train` rows in "
            "`run_passport.csv`. *arms scored* and *matched cut* count distinct arms "
            "in `arm_metrics.csv`; *best AP* is the highest average precision "
            "recorded at any cut. *champion* is `pipeline/champion_arms.csv`. "
            "*entries* counts registry entries naming this acquisition.",
            ""]
    return "\n".join(out)


def main(argv=None):
    md = build()
    (QC / "coverage_map.md").write_text(md, encoding="utf-8", newline="\n")
    print(f"wrote phase4/qc/coverage_map.md ({md.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
