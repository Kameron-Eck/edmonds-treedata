r"""Per-sector canopy series + design-based city totals (sector program, 2026-08-24).

WHAT. For every year-label with a probability raster (the new sector arms AND the existing
full-city rasters, clipped to the same sector polygons so the series spans all acquisitions
comparably), compute per-sector canopy fractions at the year's DEPLOYED threshold, then a
design-based city total with a confidence interval.

HONESTY RAILS (from the QC campaign's lessons):
  * thresholds come ONLY from qc_indep_report.csv live=1 primary=1 rows — a year without a
    live row is skipped and listed, never scored at a made-up threshold;
  * pixels are clipped by the SECTOR POLYGON (gpkg layer), not "valid prob pixels" — the
    inference write-crop paints up to ~19 m past the rectangle;
  * areas are TRUE ground areas (3857 area x cos^2(lat));
  * the err-adjusted fraction p_adj = p_raw * precision / recall from the same live row;
  * water (bathology waterbody union) and outside-city pixels are excluded from land.

ESTIMATOR. Strata = the sampled sector strips; weight W_h = strip true land area /
SAMPLED true land area (563 ha total, NOT the city). P_hat = sum W_h * p_adj_h estimates
the city land-canopy FRACTION under the design assumption (strips represent their bands).
canopy_ha_sampled = P_hat * A_land_sampled is canopy within the SAMPLED strips only —
the city-area expansion (P_hat * city land area) is deliberately NOT emitted until the
city land area is measured from CITY_SHP minus waterbody (found mislabeled 'area_ha'
by the 2026-08-26 report cross-check). Variance by the
successive-difference estimator (systematic sample of L=5 bands):
  V = (sum W_h^2) * [ 1/(2(L-1)) * sum_{h=1..L-1} (p_{h+1}-p_h)^2 ],  CI95 = t(0.975, L-1)*sqrt(V)
Also writes a 1-m cover sidecar per (year, tag) for the crown matrix.

OUTPUTS (data:phase4/qc/sector_campaign/)
  sector_canopy_series.csv       year, tag, sector, p_raw, p_adj, thresh, precision, recall,
                                 valid_land_px, gsd_cm, canopy_ha_true
  city_canopy_totals_design.csv  year, tag, P_hat, canopy_ha_sampled, se, ci_lo, ci_hi, n_sectors
  cover1m/cover_1m_{y}_{tag}.tif (float32, EPSG:3857, 1 m, nodata -1)
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_measure as im  # noqa: E402

DATA = Path(r"G:\My Drive\treedata")
CAMP = DATA / "phase4" / "qc" / "sector_campaign"
MASKS = DATA / "phase4" / "masks"
COS2 = float(np.cos(np.radians(47.81))) ** 2
T975_DF4 = 2.776


def live_rows():
    p = DATA / "phase4" / "qc" / "qc_indep_report.csv"
    out = {}
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if str(r.get("live", "")).strip() != "1" or str(r.get("primary", "")).strip() != "1":
            continue
        prob = r.get("prob", "")
        m = re.search(r"edmonds_canopy_prob_([0-9a-z]+?)(?:_(.+))?\.tif", prob)
        if not m:
            continue
        key = (m.group(1), m.group(2) or "")
        if key not in out or r.get("ts", "") >= out[key]["ts"]:
            out[key] = {"thresh": float(r["thresh"]), "recall": float(r["recall"]),
                        "precision": float(r["precision"]), "ts": r.get("ts", ""),
                        "prob": prob}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="pipeline/aoi/sectors_v1.json")
    ap.add_argument("--box-px", type=int, default=4096, help="strip read height (native px)")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    import geopandas as gpd
    import rasterio
    import rasterio.features
    from rasterio.warp import transform_geom
    from shapely.geometry import shape, box
    from shapely.ops import unary_union

    aoi = json.loads((SCRIPTS / a.aoi).read_text(encoding="utf-8")
                     if not Path(a.aoi).is_absolute() else Path(a.aoi).read_text(encoding="utf-8"))
    ver = aoi["version"]
    gpkg = DATA / "phase4" / "qc" / "sectors" / f"{ver}.gpkg"
    sectors = gpd.read_file(gpkg, layer="sectors")     # EPSG:3857 polygons w/ water ext
    city = gpd.read_file(im.CITY_SHP).to_crs("EPSG:3857")
    city_poly = city.union_all() if hasattr(city, "union_all") else city.unary_union
    water = gpd.read_file(DATA / "bathology" / "GDBA_HYDROGRAPHY__waterbody_snoco.shp")
    water = water[water.geometry.notna() & water.is_valid]
    minx, miny, maxx, maxy = city_poly.buffer(2000).bounds
    water_u = unary_union(list(water.cx[minx:maxx, miny:maxy].geometry))

    # per-sector LAND polygon (sector ∩ city − water), in 3857
    land_polys = {}
    for _, s in sectors.iterrows():
        land_polys[s["id"]] = s.geometry.intersection(city_poly).difference(water_u)
    A_land_true = {k: v.area * COS2 for k, v in land_polys.items()}
    A_city = sum(A_land_true.values())
    W = {k: v / A_city for k, v in A_land_true.items()}
    print(f"{ver}: {len(land_polys)} sectors; sampled land {A_city/1e4:,.0f} ha true; "
          f"weights {[round(W[k],3) for k in sorted(W)]}")

    live = live_rows()
    (CAMP / "cover1m").mkdir(parents=True, exist_ok=True)
    series, totals = [], []
    for (year, tag), row in sorted(live.items()):
        prob_p = MASKS / Path(row["prob"]).name
        if not prob_p.exists():
            alt = DATA / "phase3" / Path(row["prob"]).name
            prob_p = alt if alt.exists() else prob_p
        if not prob_p.exists():
            print(f"  {year}/{tag or '-'}: prob raster missing on the lake — skipped")
            continue
        thr_u8 = int(round(row["thresh"] * 254))
        per_sector, cov_writers = {}, {}
        with rasterio.open(prob_p) as ds:
            # rasterize sector land polys once onto this grid, id-coded
            geoms = []
            for i, (sid, poly) in enumerate(sorted(land_polys.items()), start=1):
                g = transform_geom("EPSG:3857", ds.crs, poly.__geo_interface__)
                geoms.append((shape(g), i))
            sid_order = sorted(land_polys)
            acc = {sid: [0, 0] for sid in sid_order}          # [canopy_px, valid_px]
            # 1-m cover accumulation grid (3857)
            b3857 = sectors.total_bounds
            cov_w = int(np.ceil((b3857[2] - b3857[0])))
            cov_h = int(np.ceil((b3857[3] - b3857[1])))
            cov_sum = np.zeros((cov_h, cov_w), dtype=np.float32)
            cov_cnt = np.zeros((cov_h, cov_w), dtype=np.uint32)
            from rasterio.transform import from_origin as _fo
            cov_tf = _fo(b3857[0], b3857[3], 1.0, 1.0)
            from rasterio.warp import transform_bounds as _tb
            for r0 in range(0, ds.height, a.box_px):
                rh = min(a.box_px, ds.height - r0)
                win = rasterio.windows.Window(0, r0, ds.width, rh)
                arr = ds.read(1, window=win)
                if not (arr != 255).any():
                    continue
                wtf = ds.window_transform(win)
                sid_r = rasterio.features.rasterize(
                    geoms, out_shape=(rh, ds.width), transform=wtf, fill=0, dtype="uint8")
                valid = (arr != 255) & (sid_r > 0)
                if not valid.any():
                    continue
                canopy = valid & (arr >= thr_u8)
                for i, sid in enumerate(sid_order, start=1):
                    m = sid_r == i
                    acc[sid][0] += int((canopy & m).sum())
                    acc[sid][1] += int((valid & m).sum())
                # accumulate the 1-m cover plane (mean of thresholded values per 1-m cell)
                bb = _tb(ds.crs, "EPSG:3857", *rasterio.windows.bounds(win, ds.transform))
                c0 = int(np.floor(bb[0] - b3857[0])); r0m = int(np.floor(b3857[3] - bb[3]))
                # coarse accumulation: bin native pixels into 1-m cells via reproject-average
                from rasterio.warp import reproject, Resampling
                dsth = max(1, int(np.ceil(bb[3] - bb[1]))); dstw = max(1, int(np.ceil(bb[2] - bb[0])))
                tgt = np.full((dsth, dstw), -1.0, dtype=np.float32)
                src = np.where(valid, canopy.astype(np.float32), np.nan)
                reproject(src, tgt, src_transform=wtf, src_crs=ds.crs,
                          dst_transform=_fo(bb[0], bb[3], 1.0, 1.0), dst_crs="EPSG:3857",
                          resampling=Resampling.average, src_nodata=np.nan, dst_nodata=-1.0)
                ok = tgt >= 0
                rr = slice(max(0, r0m), max(0, r0m) + dsth)
                cc = slice(max(0, c0), max(0, c0) + dstw)
                h2 = min(dsth, cov_h - rr.start); w2 = min(dstw, cov_w - cc.start)
                if h2 > 0 and w2 > 0:
                    sub_ok = ok[:h2, :w2]
                    cov_sum[rr.start:rr.start+h2, cc.start:cc.start+w2][sub_ok] += tgt[:h2, :w2][sub_ok]
                    cov_cnt[rr.start:rr.start+h2, cc.start:cc.start+w2][sub_ok] += 1
            gsd_cm = im.true_gsd_cm(ds)[0]
        ps = {}
        for sid in sid_order:
            c, v = acc[sid]
            if v < 1000:
                continue
            p_raw = c / v
            p_adj = p_raw * row["precision"] / max(row["recall"], 1e-6)
            ps[sid] = p_adj
            series.append({"year": year, "tag": tag, "sector": sid, "p_raw": round(p_raw, 5),
                           "p_adj": round(p_adj, 5), "thresh": row["thresh"],
                           "precision": row["precision"], "recall": row["recall"],
                           "valid_land_px": v, "gsd_cm": round(gsd_cm, 2),
                           "canopy_ha_true": round(p_adj * A_land_true[sid] / 1e4, 2)})
        if len(ps) == len(sid_order):
            vals = [ps[s] for s in sid_order]
            P = sum(W[s] * ps[s] for s in sid_order)
            sd = sum((vals[i+1] - vals[i]) ** 2 for i in range(len(vals) - 1)) / (2 * (len(vals) - 1))
            V = sum(W[s] ** 2 for s in sid_order) * sd
            se = float(np.sqrt(V))
            totals.append({"year": year, "tag": tag, "P_hat": round(P, 5),
                           "canopy_ha_sampled": round(P * A_city / 1e4, 1),
                           "se": round(se, 5),
                           "ci_lo": round(max(0.0, P - T975_DF4 * se), 5),
                           "ci_hi": round(P + T975_DF4 * se, 5),
                           "n_sectors": len(sid_order)})
            print(f"  {year}/{tag or '-'}: P_hat {P:.3f} ± {T975_DF4*se:.3f} "
                  f"({P*A_city/1e4:,.0f} ha) from {len(ps)} sectors")
        else:
            print(f"  {year}/{tag or '-'}: only {len(ps)}/{len(sid_order)} sectors valid — "
                  f"series rows written, no city total")
        # write the cover sidecar
        with np.errstate(invalid="ignore"):
            cov = np.where(cov_cnt > 0, cov_sum / np.maximum(cov_cnt, 1), -1.0).astype(np.float32)
        import rasterio as rio
        cov_p = CAMP / "cover1m" / f"cover_1m_{year}{('_' + tag) if tag else ''}.tif"
        with rio.open(cov_p, "w", driver="GTiff", width=cov.shape[1], height=cov.shape[0],
                      count=1, dtype="float32", crs="EPSG:3857", transform=cov_tf,
                      compress="deflate", nodata=-1.0, tiled=True) as dst:
            dst.write(cov[np.newaxis])

    CAMP.mkdir(parents=True, exist_ok=True)
    # E05: stamp is_champion so the deliverable series filters without dropping
    # arms. A year with no champion_arms.csv row stamps "" (undesignated) —
    # visible, never guessed.
    from champion import load_champions
    champ = load_champions()
    for r in series + totals:
        y = str(r["year"])
        r["is_champion"] = ("" if y not in champ
                            else int((r.get("tag") or "") == champ[y]))
    undes = sorted({str(r["year"]) for r in series if r["is_champion"] == ""})
    if undes:
        print(f"  ! UNDESIGNATED years (is_champion left blank): {undes}")
    for name, rows, cols in (
            ("sector_canopy_series.csv", series,
             ["year", "tag", "sector", "p_raw", "p_adj", "thresh", "precision", "recall",
              "valid_land_px", "gsd_cm", "canopy_ha_true", "is_champion"]),
            ("city_canopy_totals_design.csv", totals,
             ["year", "tag", "P_hat", "canopy_ha_sampled", "se", "ci_lo", "ci_hi", "n_sectors",
              "is_champion"])):
        with open(CAMP / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"-> {CAMP / name} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
