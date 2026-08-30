"""
pipeline_status.py — one cold-start state table for the whole pipeline (overhaul P7).

A fresh session (or a fresh human) runs this ONCE and knows where everything
stands: per year — tiles, models, prob raster (+size sanity), mask, queue VERIFY
state, and the honest qc_indep number (live rows only). Also validates dag.yaml
(every stage script exists) and renders it to Mermaid.

Read-only. Local (reads the Drive mount + the repo).

Usage:
    py -3.12 pipeline_status.py                 # the state table
    py -3.12 pipeline_status.py --csv out.csv   # also write it as CSV
    py -3.12 pipeline_status.py --mermaid       # print the DAG as Mermaid
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_SCRIPTS = HERE.parent
sys.path.insert(0, str(REPO_SCRIPTS / "pipeline"))
from phase4seg.names import status_files

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

DAG = REPO_SCRIPTS / "pipeline" / "dag.yaml"


def _read_dag():
    import yaml
    with open(DAG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_dag(dag):
    """Every stage's script (first token, before any ' --'/'…') must exist in the repo."""
    bad = []
    for name, st in dag.get("stages", {}).items():
        script = str(st.get("script", "")).split(" --")[0].split(" …")[0].strip()
        first = script.split()[0] if script else ""
        if first and not (REPO_SCRIPTS / first).exists():
            bad.append((name, first))
    return bad


def mermaid(dag):
    lines = ["graph TD"]
    for name, st in dag.get("stages", {}).items():
        where = st.get("runs_on", "?")
        lines.append(f'    {name}["{name}<br/><i>{where}</i>"]')
    for e in dag.get("edges", []):
        a, b = [s.strip() for s in str(e).split("->")]
        lines.append(f"    {a} --> {b}")
    return "\n".join(lines)


def year_rows():
    import pandas as pd
    from phase4seg import config as C

    qdir, mdir, tdir = BASE / "phase4" / "qc", BASE / "phase4" / "masks", BASE / "phase4" / "tiles"
    models = BASE / "phase4" / "models"

    # queue VERIFY states (job-end rows), newest wins. P11.1: queues write
    # per-launch status files — merge every train_queue_status*.csv.
    vstate = {}
    frames = []
    for scsv in status_files(qdir):
        try:
            frames.append(pd.read_csv(scsv))
        except Exception:
            pass
    if frames:
        sdf = pd.concat(frames, ignore_index=True).sort_values("ts")
        for _, r in sdf[sdf["step"].astype(str).str.startswith("VERIFY")].iterrows():
            vstate[(str(r["year"]), str(r["tag"]))] = str(r["state"])

    # honest numbers: qc_indep live rows, primary canopy_def — CHAMPION arm only
    # (E05: year-keyed last-wins collapsed multiple live arms into whichever row
    # came last; undesignated years are listed, never guessed).
    honest = {}
    qcsv = qdir / "qc_indep_report.csv"
    if qcsv.exists():
        from champion import load_champions, prob_arm
        champ = load_champions()
        undesignated = set()
        qdf = pd.read_csv(qcsv)
        if "live" in qdf.columns:
            qdf = qdf[qdf["live"] == 1]
        if "canopy_def" in qdf.columns:
            qdf = qdf[qdf["canopy_def"] == "forest_wetland"]
        for _, r in qdf.iterrows():
            y = str(r["year"])
            if y not in champ:
                undesignated.add(y)
                continue
            if prob_arm(str(r.get("prob", ""))) != champ[y]:
                continue
            try:
                honest[y] = f"rec {float(r['recall']):.3f} prec {float(r['precision']):.3f}"
            except Exception:
                pass
        if undesignated:
            print("  ! UNDESIGNATED years (live rows, no champion_arms.csv row — "
                  f"numbers withheld): {sorted(undesignated)}")

    rows = []
    entries = sorted(C.YEAR_CATALOG, key=lambda e: str(e.get("label", "")))
    for e in entries:
        label = str(e["label"])
        def _mine(p, stem):
            # exact-label match: '2019' must not swallow '2019n' artifacts
            rest = p.name[len(stem):]
            return rest == p.suffix or rest.startswith("_")
        tiles = (tdir / label / f"tile_index_{label}.csv").exists()
        mods = (sorted(p.name for p in models.glob(f"sem_best_{label}*.pt")
                       if _mine(p, f"sem_best_{label}")) if models.exists() else [])
        probs = (sorted(p for p in mdir.glob(f"edmonds_canopy_prob_{label}*.tif")
                        if _mine(p, f"edmonds_canopy_prob_{label}"))
                 if mdir.exists() else [])
        probs = [p for p in probs if ".stub" not in p.name]
        masks = (sorted(p for p in mdir.glob(f"edmonds_canopy_mask_{label}*.tif")
                        if _mine(p, f"edmonds_canopy_mask_{label}"))
                 if mdir.exists() else [])
        prob_desc = "; ".join(f"{p.name.replace('edmonds_canopy_prob_', '')}"
                              f"[{p.stat().st_size/1e6:.0f}MB]" for p in probs) or "—"
        ver = "; ".join(f"{t}:{s}" for (y, t), s in vstate.items() if y == label) or "—"
        rows.append(dict(year=label, gsd_cm=e.get("gsd_cm"),
                         tiles="Y" if tiles else "—",
                         models=len(mods), prob=prob_desc,
                         mask="Y" if masks else "—",
                         verify=ver, honest=honest.get(label, "—")))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    ap.add_argument("--mermaid", action="store_true")
    args = ap.parse_args([a for a in sys.argv[1:]
                          if not (a == "-f" or a.endswith(".json"))])

    dag = _read_dag()
    bad = validate_dag(dag)
    if bad:
        print("DAG VALIDATION FAILURES (script missing from repo):")
        for name, s in bad:
            print(f"  {name}: {s}")
    else:
        print(f"dag.yaml: {len(dag.get('stages', {}))} stages, "
              f"{len(dag.get('edges', []))} edges — all scripts present.")

    if args.mermaid:
        print("\n```mermaid\n" + mermaid(dag) + "\n```")
        return

    rows = year_rows()
    import pandas as pd
    df = pd.DataFrame(rows)
    with pd.option_context("display.max_colwidth", 60, "display.width", 200):
        print("\n" + df.to_string(index=False))
    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
