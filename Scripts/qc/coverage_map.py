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


def tileset_census(rows):
    """`tileset_registry.csv` rows -> {label: (n_sets, n_tiles, n_dirs)}.

    A registry row is one tile DIRECTORY — keyed (`label`, `run_tag`) — and several
    rows can share one `tileset_id`: the same set of tiles materialised under two
    tags. So "how many tile sets" and "how many directories" are two different
    measurements, and this returns both rather than letting one stand for the other:

      n_sets   distinct `tileset_id` under the label
      n_tiles  `n_tiles` summed over those DISTINCT ids — never over rows
      n_dirs   rows, i.e. how many times those sets were materialised on disk

    Summing over rows double-counts. Measured 2026-09-07: it read 2009 as 18 sets /
    11,036 tiles where the archive holds 10 / 6,124, and made 2017k's offload pilot —
    a CPU-tiled set reproducing the A100-tiled one byte-for-byte, which is the pilot's
    RESULT (`experiments/offload_pilot_2017k.yaml`) — read as a doubling.

    A row with no `tileset_id` counts as its own set: unidentified directories must
    not collapse into one another. Raises ValueError if one id carries two different
    `n_tiles` — that is a harvester bug in `qc/instruments/harvest_tilesets.py`, not
    something to average away.
    """
    ids, dirs = {}, {}
    for r in rows:
        lab = r["label"]
        key = r["tileset_id"] or f"(no id) {r['tile_dir']}"
        n = int(r["n_tiles"])
        seen = ids.setdefault(lab, {})
        if seen.setdefault(key, n) != n:
            raise ValueError(
                f"{lab}: tile set {key} carries n_tiles {seen[key]} and {n}. One id "
                f"must mean one set of tiles — fix harvest_tilesets.py, do not average")
        dirs[lab] = dirs.get(lab, 0) + 1
    return {lab: (len(s), sum(s.values()), dirs[lab]) for lab, s in ids.items()}


def build():
    from phase4seg import config
    import champion

    cat = {e["label"]: e for e in config.YEAR_CATALOG}
    champs = champion.load_champions()
    tiles, metrics = _rows(QC / "tileset_registry.csv"), _rows(QC / "arm_metrics.csv")
    runs = _rows(QC / "run_passport.csv")

    tiled, trained = tileset_census(tiles), {}
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
           "| acq | gsd | bands | tile sets | tiles | tile dirs | train runs "
           "| arms scored | matched cut | best AP | champion | entries |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]

    n_gap = {"tiled": 0, "scored": 0, "matched": 0, "champ": 0}
    for lab in sorted(cat):
        e = cat[lab]
        n_sets, n_tiles, n_dirs = tiled.get(lab, (0, 0, 0))
        arms = scored.get(lab, set())
        mp = matched.get(lab, [])
        best_ap = max(aps.get(lab, []), default=None)
        ch = champs.get(lab, "")
        if not n_sets:
            n_gap["tiled"] += 1
        if not arms:
            n_gap["scored"] += 1
        if not mp:
            n_gap["matched"] += 1
        if not ch:
            n_gap["champ"] += 1
        out.append(
            f"| {lab} | {e.get('gsd_cm')} | {e.get('bands')} "
            f"| {n_sets or ''} | {n_tiles or ''} | {n_dirs or ''} "
            f"| {trained.get(lab, '') or ''} "
            f"| {len(arms) or ''} | {len(mp) or ''} "
            f"| {f'{best_ap:.4f}' if best_ap is not None else ''} "
            f"| {ch} | {written.get(lab, '') or ''} |")

    n_sets_all = sum(v[0] for v in tiled.values())
    n_dirs_all = sum(v[2] for v in tiled.values())
    out += ["",
            f"**{len(cat)} acquisitions.** No tile set: **{n_gap['tiled']}** · "
            f"never scored: **{n_gap['scored']}** · no matched-cut read: "
            f"**{n_gap['matched']}** · no champion: **{n_gap['champ']}**.",
            "",
            "Columns: *tile sets* counts distinct `tileset_id` in "
            "`tileset_registry.csv`; *tiles* sums `n_tiles` over those DISTINCT sets. "
            "*tile dirs* counts registry ROWS — one per tile directory, so one set "
            "materialised under two run tags is one set and two directories "
            f"(archive-wide: {n_sets_all} sets in {n_dirs_all} directories). Summing "
            "over rows instead double-counts — why, and what it once got wrong, is "
            "in `docs/SCHEMAS.md`. *train runs* counts `step=train` "
            "rows in `run_passport.csv`. *arms scored* and *matched cut* count "
            "distinct arms in `arm_metrics.csv`; *best AP* is the highest average "
            "precision recorded at any cut. *champion* is "
            "`pipeline/champion_arms.csv`. *entries* counts registry entries naming "
            "this acquisition.",
            ""]
    return "\n".join(out)


def main(argv=None):
    md = build()
    (QC / "coverage_map.md").write_text(md, encoding="utf-8", newline="\n")
    print(f"wrote phase4/qc/coverage_map.md ({md.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
