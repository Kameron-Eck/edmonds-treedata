"""harvest_run_passport.py — one wide, machine-readable row per engine invocation.

THE GAP THIS CLOSES. Every run already writes `phase4/runs/{run_id}/manifest.json`
with the provenance no log carries: the commit that ran and whether the tree was
dirty, the GPU, the seed AND the split seed, the architecture and encoder, the exact
imagery file each year resolved to, the label sources with their sizes, the full argv,
and a pip freeze. That is the richest record in the project and it lives ONLY in the
lake, where nothing tracked can read it. `run_registry.csv` is the tracked view of it,
but it is thin and its `headline_metrics` column is free prose.

This instrument flattens all 535 manifests into `phase4/qc/run_passport.csv` — one row
per run, joined to the tile set it used. It is a DERIVED VIEW of the manifests, never a
second home for run facts: to change what a run says, you re-run the harvest, you do
not edit the CSV.

THE JOIN IS HONEST ABOUT ITS OWN WEAKNESS. A manifest does not record which tile set
the run trained on, and a tile directory re-tiles IN PLACE when its signature is
invalidated. So for historical runs the only available join is (year, run_tag) → the
tile set that directory holds TODAY, which can be a set the run never saw. Every row
therefore carries `join_basis`:

    manifest           the manifest names its own tileset_id — trustworthy
    inferred_current   inferred from the tile dir as it stands now — indicative only
    none               no tile dir, or the run had no year (a multi-year or ops run)

Only runs from engines that write `tileset_id` into the manifest can say `manifest`.
That is the point of writing it there (see cli.py `_write_run_manifest`).

pip_freeze is hashed, not stored: 535 runs x ~500 packages is megabytes of noise, but
`env_sha` still answers the only question anyone asks of it — did these two runs have
the same environment.

Run:  py -3.12 qc/instruments/harvest_run_passport.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

COLS = [
    "run_id", "ts_utc", "date", "step", "run_tag", "years",
    "engine_version", "git_sha", "git_dirty", "git_branch",
    "gpu", "gpu_mem_gb",
    "arch", "encoder", "epoch", "seed", "split_seed", "honest_val_split",
    "imagery", "gsd_cm",
    "label_source", "label_source_size", "add_canopy_mask", "force_citywide",
    "tileset_id", "join_basis",
    "env_sha", "n_packages", "python", "argv", "in_run_registry",
]


def _lake_runs(explicit=None):
    if explicit:
        return Path(explicit)
    from phase4seg import config
    for cand in (Path(config.BASE) / "phase4" / "runs",
                 Path(r"G:/My Drive/treedata/phase4/runs")):
        if cand.exists():
            return cand
    return cand


def _tileset_index():
    """(label, run_tag) -> tileset_id, from the tracked tileset registry."""
    p = QC / "tileset_registry.csv"
    if not p.exists():
        return {}
    out = {}
    for r in csv.DictReader(p.read_text(encoding="utf-8").splitlines()):
        if r["tileset_id"]:
            out[(r["label"], r["run_tag"])] = r["tileset_id"]
    return out


def _registry_run_ids():
    p = SCRIPTS / "run_registry.csv"
    if not p.exists():
        return set()
    return {r["run_id"] for r in
            csv.DictReader(p.read_text(encoding="utf-8").splitlines())}


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, separators=(",", ":"))
    return str(v)


def build_rows(runs_root, tilesets, reg_ids):
    rows, bad = [], []
    for mf in sorted(Path(runs_root).glob("*/manifest.json")):
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            bad.append((mf.parent.name, str(e)[:80]))
            continue

        years = m.get("years") or {}
        labels = sorted(years)
        imagery = [Path(v.get("native", "")).name for v in years.values()
                   if isinstance(v, dict)]
        gsd = [v.get("gsd_cm") for v in years.values() if isinstance(v, dict)]
        labels_blk = m.get("labels") or {}
        freeze = m.get("pip_freeze") or []

        # The join, and its honesty column.
        tsid, basis = m.get("tileset_id", ""), "manifest"
        if not tsid:
            tag = m.get("run_tag") or ""
            hits = {tilesets.get((lb, tag)) for lb in labels}
            hits.discard(None)
            if len(hits) == 1:
                tsid, basis = hits.pop(), "inferred_current"
            else:
                tsid, basis = "", "none"

        ts = m.get("ts_utc") or ""
        rows.append({
            "run_id": m.get("run_id", mf.parent.name),
            "ts_utc": ts,
            "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else "",
            "step": _fmt(m.get("step")), "run_tag": _fmt(m.get("run_tag")),
            "years": ",".join(labels),
            "engine_version": _fmt(m.get("engine_version")),
            "git_sha": _fmt(m.get("git_sha"))[:12],
            "git_dirty": _fmt(m.get("git_dirty")),
            "git_branch": _fmt(m.get("git_branch")),
            "gpu": _fmt(m.get("gpu")), "gpu_mem_gb": _fmt(m.get("gpu_mem_gb")),
            "arch": _fmt(m.get("arch")), "encoder": _fmt(m.get("encoder")),
            "epoch": _fmt(m.get("epoch")), "seed": _fmt(m.get("seed")),
            "split_seed": _fmt(m.get("split_seed")),
            "honest_val_split": _fmt(m.get("honest_val_split")),
            "imagery": ",".join(imagery),
            "gsd_cm": ",".join(_fmt(g) for g in gsd),
            "label_source": Path(_fmt(labels_blk.get("source_mask"))).name,
            "label_source_size": _fmt(labels_blk.get("source_mask_size")),
            "add_canopy_mask": Path(_fmt(labels_blk.get("add_canopy_mask"))).name,
            "force_citywide": _fmt(labels_blk.get("force_citywide")),
            "tileset_id": tsid, "join_basis": basis,
            "env_sha": (hashlib.sha256("\n".join(freeze).encode()).hexdigest()[:12]
                        if freeze else ""),
            "n_packages": len(freeze) or "",
            "python": _fmt(m.get("python")),
            "argv": " ".join(m.get("argv") or []),
            "in_run_registry": "1" if m.get("run_id") in reg_ids else "0",
        })
    rows.sort(key=lambda r: (r["ts_utc"], r["run_id"]))
    return rows, bad


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    runs_root = _lake_runs(a.runs_root)
    if not runs_root.exists():
        print(f"FATAL: runs root not found: {runs_root}\n"
              f"       this instrument reads the lake — mount it, or pass --runs-root")
        return 2

    rows, bad = build_rows(runs_root, _tileset_index(), _registry_run_ids())
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not a.dry_run:
        QC.mkdir(parents=True, exist_ok=True)
        (QC / "run_passport.csv").write_text(buf.getvalue(), encoding="utf-8",
                                             newline="")

    basis = {}
    for r in rows:
        basis[r["join_basis"]] = basis.get(r["join_basis"], 0) + 1
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} runs "
          f"→ phase4/qc/run_passport.csv")
    print(f"  tileset join: " + " · ".join(f"{k} {v}" for k, v in sorted(basis.items())))
    print(f"  in run_registry: {sum(1 for r in rows if r['in_run_registry'] == '1')}"
          f" / {len(rows)}")
    print(f"  distinct environments (env_sha): "
          f"{len({r['env_sha'] for r in rows if r['env_sha']})}")
    for name, why in bad:
        print(f"  ! unreadable manifest {name}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
