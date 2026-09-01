r"""imagery_geometry.py — the per-acquisition GEOMETRY table, measured from the files.

WHY (Kam, 2026-09-01): "having imagery in the wrong projection system can lead to
faulty assumptions that drive stats. This is something that happened quite a bit."
It did, HERE, with numbers: areas computed in EPSG:2285 US-survey-FEET units ran
10.76x large; EPSG:3857 ran 2.215x inflated at this latitude (WORKPLAN, 2026-08-27
finding). And nominal resolution lies (2005: nominal 20 cm, resolves at 80.7).
Nothing recorded, in one machine-readable home, what CRS and LINEAR UNIT each
acquisition actually carries — this instrument measures it with rasterio from every
catalog raster and writes ONE row per acquisition.

ONE FACT, ONE HOME. This table owns file-measured GEOMETRY: CRS, unit, pixel size
(CRS units AND true meters), grid origin + alignment, extent, bands, dtype, nodata.
It does NOT own resolution-quality (effective_cm — qc/imagery_pixelsize_and_date.csv)
or flight/delivery lineage (same table's date_shot + notes; 2019s/2019n one-flight-
two-deliveries). The origin/extent/pixel columns are what make lineage questions
ANSWERABLE (grid congruence is measurable); the answers belong in IMAGERY_FACTS.md.

DISAGREEMENT FLAGS are the point: every row compares the measured CRS and pixel
size against what YEAR_CATALOG claims. A silent catalog drift is the disease this
repo keeps finding; this makes the imagery half of it loud.

Writes (repo, tracked measured text — the imagery_qc_suite outdir precedent):
    phase4/qc/imagery_geometry.csv

    py -3.12 qc/instruments/imagery_geometry.py
    py -3.12 qc/instruments/imagery_geometry.py --only 2019   (filename fragment)
"""
import argparse
import csv
import datetime as _dt
from pathlib import Path

from phase4seg.names import clean_argv

SCRIPTS = Path(__file__).resolve().parents[2]  # instruments/ -> qc/ -> Scripts/
OUT = SCRIPTS.parent / "phase4" / "qc" / "imagery_geometry.csv"

COLS = ["label", "file", "root", "crs_auth", "crs_name", "unit_name", "unit_to_m",
        "px_x_crs", "px_y_crs", "px_x_m_naive", "px_ground_x_m", "px_ground_y_m",
        "crs_metric_inflation_pct", "origin_x", "origin_y",
        "origin_aligned_to_px", "width", "height", "minx", "miny", "maxx", "maxy",
        "n_bands", "dtype", "nodata", "size_mb",
        "catalog_epsg", "epsg_match", "catalog_gsd_cm", "gsd_vs_catalog_pct",
        "measured_utc", "note"]


def measure_one(entry, rasterio):
    from phase4seg.config import resolve_imagery
    label, fname = str(entry["label"]), entry["native_file"]
    path, root = resolve_imagery(fname, required=False)
    if path is None:
        return dict(label=label, file=fname, root="NOT FOUND",
                    note="no imagery root holds this file on this machine")
    with rasterio.open(path) as src:
        crs = src.crs
        row = dict(label=label, file=fname,
                   root="local" if str(path).lower().startswith("d:") else "drive")
        if crs is None:
            row["crs_auth"] = "NONE"
            row["note"] = "raster carries NO CRS — every projected use is a guess"
            return row
        auth = crs.to_authority()
        row["crs_auth"] = f"{auth[0]}:{auth[1]}" if auth else "custom"
        row["crs_name"] = (crs.to_wkt().split('"')[1] if crs.to_wkt() else "")[:60]
        if crs.is_geographic:
            row["unit_name"], row["unit_to_m"] = "degree", ""
            row["note"] = "GEOGRAPHIC CRS — pixel size in degrees; meters vary by latitude"
            u2m = None
        else:
            uname, ufac = crs.linear_units, crs.linear_units_factor[1]
            row["unit_name"], row["unit_to_m"] = uname, round(ufac, 10)
            u2m = ufac
        t = src.transform
        px, py = abs(t.a), abs(t.e)
        row["px_x_crs"], row["px_y_crs"] = round(px, 6), round(py, 6)
        if u2m:
            # NAIVE meters: CRS units x unit factor — what unit-blind code computes.
            row["px_x_m_naive"] = round(px * u2m, 6)
        # TRUE GROUND meters: warp one pixel at the raster CENTRE into EPSG:26910
        # (the AOI's true-meter CRS) and measure it. This is the number the catalog's
        # gsd_cm means. For EPSG:3857 the two differ by 1/cos(lat) ~ +48.9% at
        # Edmonds — px_x_m_naive REPRODUCES the documented 2.215x-area trap on
        # purpose, so the trap is visible per row instead of rediscovered per bug.
        from rasterio.warp import transform as _warp
        from phase4seg.config import ANALYSIS_GRID_EPSG
        cx = t.c + (src.width // 2) * t.a
        cy = t.f + (src.height // 2) * t.e
        gx, gy = _warp(crs, f"EPSG:{ANALYSIS_GRID_EPSG}",
                       [cx, cx + px, cx], [cy, cy, cy - py])
        gdx = ((gx[1] - gx[0]) ** 2 + (gy[1] - gy[0]) ** 2) ** 0.5
        gdy = ((gx[2] - gx[0]) ** 2 + (gy[2] - gy[0]) ** 2) ** 0.5
        row["px_ground_x_m"], row["px_ground_y_m"] = round(gdx, 6), round(gdy, 6)
        if u2m:
            row["crs_metric_inflation_pct"] = round(100.0 * (px * u2m - gdx) / gdx, 2)
        row["origin_x"], row["origin_y"] = round(t.c, 4), round(t.f, 4)
        # alignment: is the grid origin an integer number of pixels from (0,0)?
        # Two rasters in the same CRS with aligned origins and nested pixel sizes
        # can be compared without resampling error — the measurable half of the
        # same-flight-different-delivery question.
        row["origin_aligned_to_px"] = int(
            abs((t.c / px) - round(t.c / px)) < 1e-6
            and abs((t.f / py) - round(t.f / py)) < 1e-6)
        row["width"], row["height"] = src.width, src.height
        b = src.bounds
        row["minx"], row["miny"] = round(b.left, 3), round(b.bottom, 3)
        row["maxx"], row["maxy"] = round(b.right, 3), round(b.top, 3)
        row["n_bands"] = src.count
        row["dtype"] = src.dtypes[0] if src.dtypes else ""
        row["nodata"] = "" if src.nodata is None else src.nodata
        row["size_mb"] = round(path.stat().st_size / 1e6, 1)
        # disagreement flags vs the catalog's claims
        cat_epsg = entry.get("crs_epsg")
        row["catalog_epsg"] = cat_epsg if cat_epsg is not None else ""
        if cat_epsg is not None and auth:
            row["epsg_match"] = int(str(auth[1]) == str(cat_epsg))
        cat_gsd = entry.get("gsd_cm")
        row["catalog_gsd_cm"] = cat_gsd if cat_gsd is not None else ""
        if cat_gsd:
            meas_cm = gdx * 100.0          # TRUE ground, matching gsd_cm's meaning
            row["gsd_vs_catalog_pct"] = round(100.0 * (meas_cm - float(cat_gsd))
                                              / float(cat_gsd), 2)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="filename fragment filter")
    a = ap.parse_args(clean_argv())
    import rasterio
    from phase4seg.config import YEAR_CATALOG
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, flagged = [], []
    for e in sorted(YEAR_CATALOG, key=lambda e: str(e["label"])):
        if a.only and a.only.lower() not in e["native_file"].lower():
            continue
        r = measure_one(e, rasterio)
        r["measured_utc"] = ts
        r.setdefault("note", "")
        rows.append(r)
        if r.get("epsg_match") == 0 or r.get("root") == "NOT FOUND" \
                or (isinstance(r.get("gsd_vs_catalog_pct"), float)
                    and abs(r["gsd_vs_catalog_pct"]) > 1.0):
            flagged.append(r)
        print(f"  {r['label']:<7} {r.get('crs_auth', ''):<11} "
              f"unit={r.get('unit_name', ''):<13} px={r.get('px_ground_x_m', '?')} m ground  "
              f"bands={r.get('n_bands', '?')}  "
              f"{'FLAG: ' + (r['note'] or 'catalog disagreement') if r in flagged else ''}")
    if a.only:
        print(f"({len(rows)} rows — filtered run, NOT writing {OUT.name})")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})
    print(f"\nwrote {OUT} ({len(rows)} acquisitions, {len(flagged)} flagged)")
    if flagged:
        print("FLAGGED (catalog disagreement or unreachable):")
        for r in flagged:
            print(f"  {r['label']}: {r.get('note') or 'epsg_match=' + str(r.get('epsg_match')) + ' gsd_delta=' + str(r.get('gsd_vs_catalog_pct')) + '%'}")


if __name__ == "__main__":
    main()
