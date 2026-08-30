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


# ── STATUS.md ────────────────────────────────────────────────────────────────
#
# Split in two ON PURPOSE, and the split is what makes the drift gate possible.
#
#   CODE section  — derived from the repo alone. No Drive, no torch, so CI can
#                   regenerate it on ubuntu and fail the build when it disagrees.
#                   These are exactly the facts that drifted: CLAUDE.md told every
#                   session "18 acquisitions / 15 calendar years / 4 NIR years"
#                   against a catalog holding 36 / 20 / 10, and nobody noticed for
#                   weeks because nothing compared the two.
#   LAKE section  — derived from the Drive data lake. CI cannot see it, and the
#                   repo's harvested copies always lag (qc_indep_report.csv read 70
#                   live rows in the repo against 172 in the lake). So it carries
#                   its own generation timestamp and SAYS it may be stale, rather
#                   than presenting itself as current. Making the lag visible is the
#                   honest fix; pretending harvesting keeps up is not.
#
# The markers are load-bearing — test_docs_match_code extracts the CODE block and
# compares it against a fresh render.
CODE_BEGIN = "<!-- STATUS:code:begin -->"
CODE_END = "<!-- STATUS:code:end -->"
NL = chr(10)


def code_facts():
    """Facts derived from the repo ALONE. Must not touch Drive or import torch."""
    from collections import Counter
    from phase4seg import config as C
    import phase4seg

    cat = C.YEAR_CATALOG
    gsd = sorted(e["gsd_cm"] for e in cat)
    years = sorted({"".join(c for c in e["label"] if c.isdigit())[:4] for e in cat})
    nir = sorted(e["label"] for e in cat if e["bands"] >= 4)
    tiers = Counter(C.tier_for(e) for e in cat)
    dag = _read_dag()
    return {
        "engine_version": getattr(phase4seg, "__version__", "?"),
        "acquisitions": len(cat),
        "calendar_years": len(years),
        "year_span": f"{years[0]}-{years[-1]}",
        "gsd_min": gsd[0], "gsd_max": gsd[-1],
        "gsd_hist": dict(sorted(Counter(gsd).items())),
        "nir_labels": nir,
        "rgb_only": len(cat) - len(nir),
        "tiers": dict(sorted(tiers.items())),
        "dag_stages": len(dag.get("stages", {})),
        "dag_bad": len(validate_dag(dag)),
    }


def render_code_block(f):
    """The CI-gatable half. Deterministic — no timestamps, no paths, no host."""
    hist = "  ".join(f"{k:g}x{v}" for k, v in f["gsd_hist"].items())
    tiers = "  ".join(f"{k} {v}" for k, v in f["tiers"].items())
    return "\n".join([
        CODE_BEGIN,
        "### Derived from the code — regenerated and gated in CI",
        "",
        "| fact | value |",
        "|---|---|",
        f"| engine | `phase4seg {f['engine_version']}` |",
        f"| acquisitions | **{f['acquisitions']}** |",
        f"| calendar years | **{f['calendar_years']}** ({f['year_span']}) |",
        f"| GSD span | **{f['gsd_min']:g} - {f['gsd_max']:g} cm** |",
        f"| GSD histogram | {hist} |",
        f"| NIR-bearing (`bands>=4`) | **{len(f['nir_labels'])}** - {' '.join(f['nir_labels'])} |",
        f"| RGB-only | **{f['rgb_only']}** |",
        f"| seg tiers | {tiers} |",
        f"| DAG stages | {f['dag_stages']} ({f['dag_bad']} with a missing script) |",
        "",
        "Every number above is read from `pipeline/phase4seg/config.py:YEAR_CATALOG` and",
        "`pipeline/dag.yaml` at generation time. Do not hand-edit this block - regenerate",
        "with `py -3.12 qc/pipeline_status.py --markdown`.",
        CODE_END,
    ])



def render_lake_block(when):
    """The half CI cannot see. Carries its own timestamp and says so.

    The repo's harvested copies lag the lake by design - measured on 2026-08-30,
    qc_indep_report.csv held 70 live rows in the repo against 172 in the lake, seven
    days apart. Rather than pretend a harvest keeps up, this block states when it was
    generated and shows the two counts side by side so the lag is visible.
    """
    import pandas as pd
    out = ["### Derived from the data lake - generated " + when,
           "",
           "**This half is only as current as the last run of this script.** CI cannot",
           "regenerate it (no Drive mount), so it is NOT gated. Treat every number below",
           "as of the timestamp above, not as of now.",
           ""]

    # the one comparison that makes the lag concrete
    rows = []
    repo_qc = REPO_SCRIPTS.parent / "phase4" / "qc" / "qc_indep_report.csv"
    for label, path in (("repo", repo_qc),
                        ("lake", BASE / "phase4" / "qc" / "qc_indep_report.csv")):
        try:
            d = pd.read_csv(path)
            live = d[d["live"] == 1] if "live" in d.columns else d
            rows.append((label, len(d), len(live), live["year"].nunique(),
                         str(d["ts"].max()) if "ts" in d.columns else "?"))
        except Exception as e:                                    # noqa: BLE001
            rows.append((label, "-", "-", "-", f"unreadable ({type(e).__name__})"))
    out += ["#### Scored results - repo copy vs lake", "",
            "| copy | rows | live | years | newest |", "|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
    if len({str(r[1]) for r in rows}) > 1:
        out += ["", "The repo copy is BEHIND. Run `py -3.12 pipeline/harvest_results.py`",
                "to close the gap, or read the lake directly."]
    out.append("")

    try:
        df = pd.DataFrame(year_rows())
        out += ["#### Per-year state", "", df.to_markdown(index=False), ""]
    except Exception as e:                                        # noqa: BLE001
        out += [f"_per-year table unavailable: {type(e).__name__}: {e}_", ""]
    return NL.join(out)


def write_status_md(dest):
    """STATUS.md = the gated code block + the timestamped lake block."""
    import datetime as _dt
    when = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = ["# Project status - GENERATED, do not hand-edit",
             "",
             "Regenerate: `py -3.12 qc/pipeline_status.py --markdown`",
             "",
             render_code_block(code_facts()),
             ""]
    if BASE.exists():
        parts.append(render_lake_block(when))
    else:
        parts += ["### Derived from the data lake",
                  "",
                  f"_Not available: the lake is not mounted at `{BASE}` "
                  f"(checked {when}). The code block above is complete regardless._",
                  ""]
    Path(dest).write_text(NL.join(parts) + NL, encoding="utf-8")
    return dest



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    ap.add_argument("--mermaid", action="store_true")
    ap.add_argument("--markdown", nargs="?", const=str(REPO_SCRIPTS / "STATUS.md"),
                    default=None, metavar="PATH",
                    help="write STATUS.md (default: Scripts/STATUS.md). The code-derived "
                         "block is regenerated and gated in CI; the lake block carries its "
                         "own timestamp because CI cannot see Drive.")
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

    if args.markdown:
        dest = write_status_md(args.markdown)
        print("")
        print(f"wrote {dest}")
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
