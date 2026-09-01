r"""acquisition_passport.py — ONE row per acquisition, everything joined. GENERATED.

WHY (Kam, 2026-09-01): "the goal should always be to centralize information so we do
not have to bounce around multiple dataframes." The one-fact-one-home rule is what
keeps facts from rotting, so the homes stay separate — catalog (config.YEAR_CATALOG),
geometry (phase4/qc/imagery_geometry.csv), resolution+dates
(qc/imagery_pixelsize_and_date.csv), champions (pipeline/champion_arms.csv), honest
scores (lake qc_indep_report.csv live rows). This table is the JOINED VIEW of all
five: a passport per acquisition, for reading — never for editing. Fix the source,
regenerate this; the gate (test_analysis_grid.py::test_passport_is_fresh) fails when
this view disagrees with its sources.

Writes: phase4/qc/acquisition_passport.csv

    py -3.12 qc/instruments/acquisition_passport.py
"""
import csv
import datetime as _dt
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]  # instruments/ -> qc/ -> Scripts/
OUT = SCRIPTS.parent / "phase4" / "qc" / "acquisition_passport.csv"

COLS = ["label", "calendar_year", "native_file", "bands", "tier",
        # geometry home
        "crs_auth", "unit_name", "px_ground_x_m", "crs_metric_inflation_pct",
        "city_bounds_coverage_pct", "black_px_pct_in_city", "mmu_effective_m2",
        # resolution/date home
        "effective_cm", "date_shot", "date_precision", "evidence_grade",
        # decision + score homes
        "champion_tag", "honest_score",
        "generated_utc"]


def _geometry():
    p = SCRIPTS.parent / "phase4" / "qc" / "imagery_geometry.csv"
    return {r["label"]: r for r in csv.DictReader(p.open(encoding="utf-8"))}


def _dates():
    """year_label-keyed rows from the pixelsize/date table (primary rows only)."""
    p = SCRIPTS / "qc" / "imagery_pixelsize_and_date.csv"
    out = {}
    for r in csv.DictReader(p.open(encoding="utf-8")):
        if not r.get("row_type", "").startswith("held imagery"):
            continue                       # references/context rows are not acquisitions
        # year_label carries campaign suffixes ("2002s (campaign S02)") — the join
        # key is the leading token, matching the catalog's label vocabulary
        key = str(r.get("year_label", "")).strip().split(" ")[0]
        out.setdefault(key, r)
    return out


def _champions():
    from champion import load_champions
    return load_champions()


def _honest():
    """Champion-arm live scores, the pipeline_status derivation (its rules, not new
    ones): live=1, forest_wetland, champion arm only."""
    from lake import BASE
    from champion import load_champions, prob_arm
    q = BASE / "phase4" / "qc" / "qc_indep_report.csv"
    out = {}
    if not q.exists():
        return out
    champ = load_champions()
    for r in csv.DictReader(q.open(encoding="utf-8")):
        y = str(r.get("year", ""))
        if (str(r.get("live", "")) == "1"
                and r.get("canopy_def") == "forest_wetland"
                and y in champ and prob_arm(str(r.get("prob", ""))) == champ[y]):
            try:
                out[y] = (f"rec {float(r['recall']):.3f} "
                          f"prec {float(r['precision']):.3f}")
            except (ValueError, KeyError):
                pass
    return out


def main():
    from phase4seg import config as C
    from phase4seg.common import tier_for
    geo, dates, champ, honest = _geometry(), _dates(), _champions(), _honest()
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for e in sorted(C.YEAR_CATALOG, key=lambda e: str(e["label"])):
        lab = str(e["label"])
        g = geo.get(lab, {})
        d = dates.get(lab, {})
        rows.append({
            "label": lab,
            "calendar_year": "".join(c for c in lab if c.isdigit())[:4],
            "native_file": e["native_file"], "bands": e["bands"],
            "tier": tier_for(e),
            "crs_auth": g.get("crs_auth", ""), "unit_name": g.get("unit_name", ""),
            "px_ground_x_m": g.get("px_ground_x_m", ""),
            "crs_metric_inflation_pct": g.get("crs_metric_inflation_pct", ""),
            "city_bounds_coverage_pct": g.get("city_bounds_coverage_pct", ""),
            "black_px_pct_in_city": g.get("black_px_pct_in_city", ""),
            "mmu_effective_m2": g.get("mmu_effective_m2", ""),
            "effective_cm": d.get("effective_cm", ""),
            "date_shot": d.get("date_shot", ""),
            "date_precision": d.get("date_precision", ""),
            "evidence_grade": d.get("evidence_grade", ""),
            "champion_tag": champ.get(lab, ""),
            "honest_score": honest.get(lab, ""),
            "generated_utc": ts,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    n_champ = sum(1 for r in rows if r["champion_tag"])
    n_dated = sum(1 for r in rows if r["date_shot"])
    print(f"wrote {OUT}: {len(rows)} acquisitions | {n_champ} with champions | "
          f"{n_dated} with flight dates")


if __name__ == "__main__":
    main()
