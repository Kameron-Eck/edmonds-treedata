r"""Stable-crown miner — stability-mined labels v0 (2026-08-26, Kam-approved
"move forward with stable groves").

LABEL-MINING EVIDENCE, NOT A DELIVERABLE. A crown listed here is a CANDIDATE
whose 2020 crownV5 polygon may serve as a verified-canopy training label for
OLD imagery years; nothing here is a canopy measurement and nothing here feeds
reports. Stability is judged across EVERY live arm with a cover sidecar —
INCLUDING legacy-era rasters whose provenance Kam declined for publication
(2026-08-26): acceptable for MINING because a crown that reads as full canopy
under every model of every era is exactly the invariance being sought, and the
mined labels are verified against current-workflow arms before any training
use (the A/B gate in the stability-mined-labels plan).

Rule: a crown is STABLE iff
  - it is validly observed (finite cover) in >= --min-years DISTINCT years, and
  - its cover fraction is >= --min-cover in EVERY (year, arm) column where it
    is observed (NaN = unobserved, never counts against — the nodata
    semantics verified 2026-08-26: partial footprint -> NaN, not 0).

INPUT   data:phase4/qc/sector_campaign/crown_cover_matrix.parquet
        (from qc/phase4_crown_cover_matrix.py; columns cover_{year}[_{tag}])
OUTPUT  data:phase4/qc/stable_crowns_v0.csv
        [--gpkg] data:phase4/qc/stable_crowns_v0.gpkg  (joined 2020 polygons,
        for ArcGIS inspection; crowns from the D: mirror, Drive fallback —
        same source as the matrix builder)

Rerun after the PoC years' sidecars exist (phase4_sector_series.py sweep +
phase4_crown_cover_matrix.py rebuild) — the matrix then carries the 6 new
fullext columns and this miner picks them up with no flag changes.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

DATA = Path(r"G:\My Drive\treedata")
MATRIX = DATA / "phase4" / "qc" / "sector_campaign" / "crown_cover_matrix.parquet"
OUT_CSV = DATA / "phase4" / "qc" / "stable_crowns_v0.csv"
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
CROWNS_FALLBACK = DATA / "inference" / "edmonds_crowns_2020.gpkg"


def main():
    ap = argparse.ArgumentParser(description="Mine stability-verified crowns (label mining, not a deliverable).")
    ap.add_argument("--matrix", default=str(MATRIX))
    ap.add_argument("--min-cover", type=float, default=0.8,
                    help="cover floor a crown must hold in EVERY observed year-arm (default 0.8)")
    ap.add_argument("--min-years", type=int, default=4,
                    help="minimum DISTINCT years observed (default 4)")
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--gpkg", action="store_true",
                    help="also write stable_crowns_v0.gpkg (2020 polygons joined) beside --out")
    a = ap.parse_args(clean_argv())

    import pandas as pd

    df = pd.read_parquet(a.matrix)
    cover_cols = [c for c in df.columns if c.startswith("cover_")]
    if not cover_cols:
        sys.exit(f"no cover_* columns in {a.matrix}")
    col_year = {c: c[len("cover_"):].partition("_")[0] for c in cover_cols}
    years = sorted(set(col_year.values()))
    print(f"matrix: {len(df):,} crowns x {len(cover_cols)} year-arm columns "
          f"({len(years)} distinct years: {', '.join(years)})")

    vals = df[cover_cols].to_numpy(dtype="float64")
    obs = np.isfinite(vals)
    # distinct-years-observed per crown (a year with 3 arms counts once)
    year_obs = np.zeros((len(df), len(years)), dtype=bool)
    for j, c in enumerate(cover_cols):
        year_obs[:, years.index(col_year[c])] |= obs[:, j]
    n_years = year_obs.sum(axis=1)
    import warnings
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        # crowns observed in zero columns produce all-NaN slices; they get
        # n_years=0 and are excluded by --min-years — the warning is noise
        warnings.simplefilter("ignore", RuntimeWarning)
        min_cov = np.nanmin(np.where(obs, vals, np.nan), axis=1)
        mean_cov = np.nanmean(np.where(obs, vals, np.nan), axis=1)
    stable = (n_years >= a.min_years) & (min_cov >= a.min_cover)

    yr_arr = np.array(years)
    rows = pd.DataFrame({
        "crown_id": df["crown_id"],
        "n_years_observed": n_years,
        "min_cover": np.round(min_cov, 4),
        "mean_cover": np.round(mean_cov, 4),
        "years_observed": [";".join(yr_arr[m]) for m in year_obs],
    })[stable]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(out, index=False)
    print(f"considered {len(df):,} crowns -> STABLE {stable.sum():,} "
          f"({stable.sum()/max(len(df),1):.1%}) at min_cover>={a.min_cover} "
          f"in every observed arm, >={a.min_years} distinct years")
    print(f"-> {out}")

    if a.gpkg:
        import geopandas as gpd
        src = CROWNS if CROWNS.exists() else CROWNS_FALLBACK
        g = gpd.read_file(src, engine="pyogrio")
        g = g[g["crown_id"].isin(set(rows["crown_id"]))].merge(rows, on="crown_id")
        gp = out.with_suffix(".gpkg")
        g.to_file(gp, layer="stable_crowns", driver="GPKG")
        print(f"-> {gp} ({len(g):,} polygons, from {src})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
