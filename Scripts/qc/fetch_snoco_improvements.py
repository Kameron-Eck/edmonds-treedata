"""Fetch the Snohomish County per-structure YEAR BUILT record for the study area.

WHY: Kam's roof-presence problem ("did a roof exist here in year Y?") has a
DETERMINISTIC answer for most of Edmonds that needs no imagery model at all.
The county Assessor publishes an Improvement Records table with a YrBuilt field
per structure, keyed on the parcel number, and publishes parcel polygons keyed
on the same number. Joining the two gives a per-parcel construction year.

VERIFIED 2026-08-26 (this script's own run is the retrieval evidence):
  parcels    https://gis.snoco.org/host/rest/services/Hosted/
             CADASTRAL__parcels/FeatureServer/0   (EPSG:2285, field parcel_id)
  improvements  https://www.arcgis.com/sharing/rest/content/items/
             3c5edc985cec4fba8b3938d16ed1d3c3/data   (xlsx, ~99 MB,
             sheet "Improvements", 286,222 rows countywide, field PIN)
  parcels.parcel_id == improvements.PIN  (14-char string; confirmed on
  00370400000100 = 23806 101ST PL W, YrBuilt 1954)

CAVEATS THAT LIMIT WHAT YrBuilt CAN PROVE — read before trusting an output row:
  - It is the year of the improvement AS IT STANDS. A teardown-and-rebuild
    carries the NEW year; the older structure that occupied the same ground
    leaves no row. So YrBuilt is an upper bound on "something was built here".
  - DEMOLISHED structures are absent entirely. The roll is current-state, the
    same blind spot the footprint layer has.
  - It is PARCEL-keyed, not footprint-keyed. A parcel with a house and a
    detached garage has two rows; this script keeps min/max/count per parcel.
  - Condominiums and mobile homes stack many parcels on one polygon.

Terms: Snohomish County open data. The portal's Terms of Use and Data
Disclaimer state the data is "for illustrative purposes only" and is not an
official citation to the County Code — cite it as a reference, not as a survey.

USAGE
  py -3.12 qc/fetch_snoco_improvements.py            # full study bbox
  py -3.12 qc/fetch_snoco_improvements.py --keep-xlsx
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon

PARCELS_URL = ("https://gis.snoco.org/host/rest/services/Hosted/"
               "CADASTRAL__parcels/FeatureServer/0/query")
IMPROVE_URL = ("https://www.arcgis.com/sharing/rest/content/items/"
               "3c5edc985cec4fba8b3938d16ed1d3c3/data")

# The study extent — identical to the bbox of Kam's ONEGEO footprint order
# (building_footprints/index.json), so the two layers cover the same ground.
BBOX = (-122.39697, 47.77759, -122.31936, 47.85954)

OUT_DIR = Path(r"G:\My Drive\treedata\phase4\qc\roof_presence")
PAGE = 2000

KEEP = ("PIN", "ImprType", "UseDesc", "YrBuilt", "FinSize", "Stories",
        "RoofTypeDesc", "RoofMatDesc", "ImpStat")


def _get(url, params, timeout=240):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params),
                                timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_parcels():
    """Page every parcel polygon intersecting the study bbox."""
    recs, geoms, offset = [], [], 0
    while True:
        d = _get(PARCELS_URL, {
            "where": "1=1",
            "geometry": ",".join(str(v) for v in BBOX),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "parcel_id,situscity,situsline1,usecode",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultOffset": str(offset),
            "resultRecordCount": str(PAGE),
            "f": "json",
        })
        feats = d.get("features", [])
        for f in feats:
            rings = (f.get("geometry") or {}).get("rings")
            if not rings:
                continue
            # Esri rings: first is outer, clockwise; holes are counter-clockwise.
            polys = [Polygon(r) for r in rings if len(r) >= 4]
            polys = [p if p.is_valid else p.buffer(0) for p in polys]
            polys = [p for p in polys if not p.is_empty]
            if not polys:
                continue
            geoms.append(polys[0] if len(polys) == 1 else MultiPolygon(
                [g for p in polys for g in
                 (p.geoms if p.geom_type == "MultiPolygon" else [p])]))
            recs.append(f["attributes"])
        print(f"  parcels offset={offset} -> {len(feats)} "
              f"(total {len(recs)})", flush=True)
        if not d.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
        time.sleep(0.25)
    return gpd.GeoDataFrame(recs, geometry=geoms, crs="EPSG:4326")


def fetch_improvements(xlsx, pins):
    if not xlsx.exists():
        print(f"  downloading improvement records -> {xlsx} ...", flush=True)
        xlsx.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(IMPROVE_URL, xlsx)
    print(f"  streaming {xlsx.name} ({xlsx.stat().st_size/1e6:.0f} MB) ...",
          flush=True)
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb["Improvements"]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    idx = {k: hdr.index(k) for k in KEEP}
    rows, n = [], 0
    for r in it:
        n += 1
        if r[idx["PIN"]] in pins:
            rows.append({k: r[idx[k]] for k in KEEP})
    wb.close()
    print(f"  scanned {n:,} rows; kept {len(rows):,} in the study bbox")
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--xlsx", default=None,
                    help="cached Improvement Records xlsx (downloaded if absent)")
    ap.add_argument("--keep-xlsx", action="store_true")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx = Path(args.xlsx) if args.xlsx else \
        out_dir / "Snohomish_County_Improvement_Records.xlsx"

    print("fetching parcel polygons ...", flush=True)
    par = fetch_parcels()
    print(f"parcels: {len(par):,}")

    pins = set(par.parcel_id)
    imp = fetch_improvements(xlsx, pins)

    imp["YrBuilt"] = pd.to_numeric(imp["YrBuilt"], errors="coerce")
    imp.loc[~imp.YrBuilt.between(1850, 2030), "YrBuilt"] = pd.NA

    agg = defaultdict(dict)
    for pin, grp in imp.groupby("PIN"):
        yrs = grp.YrBuilt.dropna()
        agg[pin] = {
            "yrbuilt_min": int(yrs.min()) if len(yrs) else None,
            "yrbuilt_max": int(yrs.max()) if len(yrs) else None,
            "n_improvements": len(grp),
            "roof_mat": (grp.RoofMatDesc.dropna().iloc[0]
                         if grp.RoofMatDesc.notna().any() else None),
            "roof_type": (grp.RoofTypeDesc.dropna().iloc[0]
                          if grp.RoofTypeDesc.notna().any() else None),
            "use_desc": (grp.UseDesc.dropna().iloc[0]
                         if grp.UseDesc.notna().any() else None),
            "fin_size": pd.to_numeric(grp.FinSize, errors="coerce").max(),
        }
    adf = pd.DataFrame.from_dict(agg, orient="index")
    adf.index.name = "parcel_id"
    out = par.merge(adf.reset_index(), on="parcel_id", how="left")

    gpkg = out_dir / "snoco_parcels_yrbuilt.gpkg"
    out.to_file(gpkg, layer="parcels_yrbuilt", driver="GPKG")
    csv = out_dir / "snoco_improvements_studybbox.csv"
    imp.to_csv(csv, index=False)
    print(f"\nwrote {gpkg}")
    print(f"wrote {csv}  ({len(imp):,} improvement rows)")

    have = out.yrbuilt_min.notna()
    print(f"\nparcels with a YrBuilt: {int(have.sum()):,} / {len(out):,}")
    yrs = out.loc[have, "yrbuilt_min"].astype(int)
    dec = yrs.floordiv(10).mul(10).value_counts().sort_index()
    for d, c in dec.items():
        print(f"  {int(d)}s  {c:6,}")
    inrec = yrs.between(2000, 2024)
    print(f"BUILT INSIDE THE 2000-2024 IMAGERY RECORD: {int(inrec.sum()):,} "
          f"({100*inrec.mean():.1f}%)  -> everything else predates the record "
          f"and is present in EVERY year of it (barring demolition)")

    if not args.keep_xlsx and xlsx.exists():
        xlsx.unlink()
        print(f"removed the {xlsx.name} cache (--keep-xlsx to retain)")
    return 0


if __name__ == "__main__":
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    sys.exit(main(filtered))
