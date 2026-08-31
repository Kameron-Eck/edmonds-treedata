r"""Per-crown cover matrix on sectors (sector program, 2026-08-24).

Crowns intersecting the sector polygons x every (year, tag) with a 1-m cover sidecar from
qc/phase4_sector_series.py -> mean cover fraction per crown per year. The rasterize+bincount
pattern is phase1a_autolabel's (the only crown_id->pixel machinery in the project).

Crowns come from the D: mirror first (D:\edmonds-pipeline\backup\inference\
edmonds_crowns_2020.gpkg, 222,435 features) with the Drive copy as fallback; only crowns
whose bbox intersects a sector are loaded. Crowns with <30 valid 1-m cells in a given year
get NaN (low-confidence), not a fabricated number.

OUTPUT  data:phase4/qc/sector_campaign/crown_cover_matrix.parquet
        (crown_id, sector, area_m2, n_cells, cover_{year}[_{tag}] ... columns)
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]
DATA = Path(r"G:\My Drive\treedata")
CAMP = DATA / "phase4" / "qc" / "sector_campaign"
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
CROWNS_FALLBACK = DATA / "inference" / "edmonds_crowns_2020.gpkg"
MIN_CELLS = 30


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="pipeline/aoi/sectors_v1.json")
    a = ap.parse_args(clean_argv())

    import geopandas as gpd
    import pandas as pd
    import rasterio
    import rasterio.features

    aoi = json.loads((SCRIPTS / a.aoi if not Path(a.aoi).is_absolute() else Path(a.aoi))
                     .read_text(encoding="utf-8"))
    ver = aoi["version"]
    sectors = gpd.read_file(DATA / "phase4" / "qc" / "sectors" / f"{ver}.gpkg", layer="sectors")

    crowns_path = CROWNS if CROWNS.exists() else CROWNS_FALLBACK
    parts = []
    for _, s in sectors.iterrows():
        g = gpd.read_file(crowns_path, bbox=tuple(s.geometry.bounds), engine="pyogrio")
        g = g[g.geometry.intersects(s.geometry)].copy()
        g["sector"] = s["id"]
        parts.append(g)
    crowns = pd.concat(parts, ignore_index=True).drop_duplicates(subset="crown_id")
    print(f"{len(crowns):,} crowns intersect {ver} sectors "
          f"(of 222,435 citywide; {len(crowns)/222435:.1%})")

    covers = sorted((CAMP / "cover1m").glob("cover_1m_*.tif"))
    if not covers:
        sys.exit("no cover sidecars — run qc/phase4_sector_series.py first")
    out = crowns[["crown_id", "sector", "area_m2"]].copy()
    with rasterio.open(covers[0]) as ds0:
        shape0, tf0, crs0 = (ds0.height, ds0.width), ds0.transform, ds0.crs
    ids = np.arange(1, len(crowns) + 1, dtype=np.int32)
    id_raster = rasterio.features.rasterize(
        [(geom, i) for geom, i in zip(crowns.geometry.values, ids)],
        out_shape=shape0, transform=tf0, fill=0, dtype="int32")
    out["n_cells"] = np.bincount(id_raster.ravel(), minlength=len(crowns) + 1)[1:]
    for p in covers:
        col = "cover_" + p.stem[len("cover_1m_"):]
        with rasterio.open(p) as ds:
            assert (ds.height, ds.width) == shape0 and ds.transform == tf0, \
                f"{p.name}: cover grid mismatch — sidecars must share one grid"
            cov = ds.read(1)
        ok = cov >= 0
        sums = np.bincount(id_raster[ok].ravel(), weights=cov[ok].ravel(),
                           minlength=len(crowns) + 1)[1:]
        cnts = np.bincount(id_raster[ok].ravel(), minlength=len(crowns) + 1)[1:]
        with np.errstate(invalid="ignore"):
            vals = np.where(cnts >= MIN_CELLS, sums / np.maximum(cnts, 1), np.nan)
        out[col] = np.round(vals, 4)
        print(f"  {col}: {np.isfinite(vals).sum():,} crowns covered "
              f"(median {np.nanmedian(vals):.3f})")
    CAMP.mkdir(parents=True, exist_ok=True)
    dest = CAMP / "crown_cover_matrix.parquet"
    out.to_parquet(dest, index=False)
    print(f"-> {dest} ({dest.stat().st_size:,} B, {len(out):,} rows x {len(out.columns)} cols)")
    # E05: column->arm map with is_champion, so the deliverable per-crown series
    # filters by fact, not by guessing among per-(year, tag) duplicates.
    sys.path.insert(0, str(SCRIPTS / "qc"))
    from champion import load_champions
    champ = load_champions()
    colmap = {}
    for c in out.columns:
        if not c.startswith("cover_"):
            continue
        year, _, tag = c[len("cover_"):].partition("_")
        colmap[c] = {"year": year, "tag": tag,
                     "is_champion": (None if year not in champ
                                     else tag == champ[year])}
    side = CAMP / "crown_cover_matrix.columns.json"
    side.write_text(json.dumps(colmap, indent=2), encoding="utf-8")
    undes = sorted({v["year"] for v in colmap.values() if v["is_champion"] is None})
    if undes:
        print(f"  ! UNDESIGNATED years in column map (is_champion null): {undes}")
    print(f"-> {side}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
