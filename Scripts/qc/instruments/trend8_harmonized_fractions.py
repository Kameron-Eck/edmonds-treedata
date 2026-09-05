"""trend8 harmonized canopy fractions — one common 2 m grid for all 8 years.

The raw per-native-pixel fractions sawtooth +-3-6pp with acquisition GSD and
season (2024@5cm reads 29.1%, 2011s@30cm reads 21.2%) around a true signal of
~2pp — fine grids resolve small canopy coarse grids cannot, so the raw series
fakes GAIN toward recent years. Harmonization: every trend8 mask resampled to
the SAME 2 m lattice (majority rule via Resampling.average >= 0.5 on the 0/1
band, 255 masked), city-clipped, then fraction = canopy / valid. If the
sawtooth collapses, the raw swings were measurement grain, not trees.

Output: phase4/qc/trend8_harmonized_fractions.csv
"""
import csv
import io
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features as rfeat
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from affine import Affine

from lake import BASE

MASKS = BASE / "phase4" / "masks"
CITY = BASE / "City Boundry" / "Edmonds Boundry.shp"
OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "trend8_harmonized_fractions.csv"
YEARS = ("2009", "2011s", "2013", "2015", "2016", "2019", "2021", "2024")
CELL = 2.0
EPSG = 26910


def main():
    import geopandas as gpd
    city = gpd.read_file(CITY).to_crs(EPSG)
    minx, miny, maxx, maxy = city.total_bounds
    tf = Affine(CELL, 0, float(np.floor(minx)), 0, -CELL, float(np.ceil(maxy)))
    w = int(np.ceil((maxx - minx) / CELL)) + 1
    h = int(np.ceil((maxy - miny) / CELL)) + 1
    inside = rfeat.rasterize(((g, 1) for g in city.geometry), out_shape=(h, w),
                             transform=tf, fill=0, dtype="uint8").astype(bool)
    rows = []
    for y in YEARS:
        p = MASKS / f"edmonds_canopy_mask_{y}_trend8_{y}.tif"
        with rasterio.open(p) as src:
            # dtype float32 in the VRT: averaging 0/1 in uint8 floors the
            # 0..1 mean back to 0 and the majority rule dies silently.
            with WarpedVRT(src, crs=f"EPSG:{EPSG}", transform=tf, width=w,
                           height=h, resampling=Resampling.average,
                           src_nodata=255, nodata=float("nan"),
                           dtype="float32") as v:
                a = v.read(1)
        valid = inside & np.isfinite(a)
        can = valid & (a >= 0.5)
        frac = float(can.sum() / max(valid.sum(), 1))
        rows.append(dict(year=y, canopy_frac_2m=round(frac, 4),
                         valid_cells=int(valid.sum())))
        print(f"{y:6s} {100*frac:6.2f}%  (valid {valid.sum():,})", flush=True)
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wcsv.writeheader(); wcsv.writerows(rows)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
