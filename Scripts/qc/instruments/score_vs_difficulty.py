r"""score_vs_difficulty.py — mine EVERY prior scored arm against year difficulty.

PURPOSE (the ladder's zero-GPU rung, Kam 2026-09-01): before the 36-run spends
~70 A100-hours, learn from runs ALREADY PAID FOR where quality degrades — with
era, resolution, season. HYPOTHESIS-GENERATING ONLY, by declaration: this ranks
which years belong in the hard-year pilot; the pilot's fresh EPOCH-3 runs make
the go/no-go decision. Prior-campaign noise can at worst mis-prioritise a pilot
slot; it cannot leak into the verdict.

TRUST CONTAINMENT (Kam: "they used improper assumptions at times"):
  * A score is a valid measurement OF ITS ARTIFACT — qc_indep grades the prob
    raster against the reference with TODAY's scorer, whatever assumptions
    trained the arm. What is NOT valid is pooling arms as recipe-equal.
  * So every row carries PROVENANCE: the arm tag, whether it is the year's
    designated champion, and its era class (sector-recipe vs citywide vs pilot).
    Analyse WITHIN strata; never a single pooled fit.
  * ref_epoch_gap_yr rides every row: scoring 2005 against 2021 C-CAP counts 16
    years of real landscape change as model error. Old-year scores are LOWER
    BOUNDS on quality, and the column says by how much suspicion.

Reads: lake qc_indep_report.csv (live=1, forest_wetland, best row per arm),
       the acquisition passport (difficulty axes), champion_arms.
Writes: phase4/qc/score_vs_difficulty.csv

    py -3.12 qc/instruments/score_vs_difficulty.py
"""
import csv
import datetime as _dt
from pathlib import Path

from phase4seg.names import clean_argv  # noqa: F401 — argv hygiene for VM parity

SCRIPTS = Path(__file__).resolve().parents[2]
OUT = SCRIPTS.parent / "phase4" / "qc" / "score_vs_difficulty.csv"
REF_EPOCH = 2021          # C-CAP hi-res reference year (SCHEMAS: qc_indep contract)

COLS = ["year", "tag", "is_champion", "recipe_class", "recall", "precision", "f_half",
        "thresh", "calendar_year", "ref_epoch_gap_yr", "effective_cm", "bands",
        "tier", "crs_family", "date_shot", "month", "leafoff_risk",
        "mmu_epoch2_m2", "generated_utc"]


def recipe_class(tag):
    t = (tag or "").lower()
    if "pilot" in t:
        return "pilot_e2"
    if "sector" in t:
        return "sector_v1"
    if "citywide" in t or "p2" in t or "nir" in t:
        return "citywide"
    return "legacy" if not t else "other"


def main():
    from lake import BASE, read_retry
    from champion import load_champions, prob_arm

    passport = {r["label"]: r for r in csv.DictReader(
        (SCRIPTS.parent / "phase4" / "qc" / "acquisition_passport.csv").open(encoding="utf-8"))}
    champs = load_champions()
    q = BASE / "phase4" / "qc" / "qc_indep_report.csv"
    rows_raw = read_retry(lambda: list(csv.DictReader(q.open(encoding="utf-8"))))

    best = {}
    for r in rows_raw:
        if str(r.get("live", "")) != "1" or r.get("canopy_def") != "forest_wetland":
            continue
        y, tag = str(r["year"]), prob_arm(str(r.get("prob", "")))
        try:
            rec, prec = float(r["recall"]), float(r["precision"])
        except (ValueError, KeyError):
            continue
        # F0.5-ish single number for RANKING only (precision-lean, matching how
        # the pipeline reads its arms); never a headline.
        f = (1.25 * prec * rec) / (0.25 * prec + rec) if (prec + rec) else 0.0
        k = (y, tag)
        if k not in best or f > best[k][0]:
            best[k] = (f, rec, prec, r.get("thresh", ""))

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for (y, tag), (f, rec, prec, thr) in sorted(best.items()):
        p = passport.get(y, {})
        cal = int(p.get("calendar_year") or ("".join(c for c in y if c.isdigit())[:4] or 0))
        date = p.get("date_shot", "")
        month = int(date[5:7]) if len(date) >= 7 and date[5:7].isdigit() else ""
        leafoff = int(month in (1, 2, 3, 4, 11, 12)) if month else ""
        crs = p.get("crs_auth", "")
        fam = {"EPSG:2285": "state_plane_ft", "EPSG:2926": "state_plane_ft",
               "EPSG:3857": "web_mercator", "EPSG:26910": "utm_m"}.get(crs, crs)
        out.append(dict(
            year=y, tag=tag, is_champion=int(champs.get(y) == tag),
            recipe_class=recipe_class(tag),
            recall=round(rec, 4), precision=round(prec, 4), f_half=round(f, 4),
            thresh=thr, calendar_year=cal, ref_epoch_gap_yr=abs(REF_EPOCH - cal),
            effective_cm=p.get("effective_cm", ""), bands=p.get("bands", ""),
            tier=p.get("tier", ""), crs_family=fam, date_shot=date, month=month,
            leafoff_risk=leafoff, mmu_epoch2_m2="", generated_utc=ts))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {OUT}: {len(out)} scored arms across "
          f"{len({r['year'] for r in out})} years")
    champs_only = [r for r in out if r["is_champion"]]
    for r in sorted(champs_only, key=lambda r: r["f_half"]):
        print(f"  {r['year']:<7} f.5={r['f_half']:.3f} rec={r['recall']:.3f} "
              f"prec={r['precision']:.3f}  eff={r['effective_cm'] or '?':>6}cm "
              f"gap={r['ref_epoch_gap_yr']:>2}yr month={r['month'] or '?'} "
              f"[{r['recipe_class']}]")


if __name__ == "__main__":
    main()
