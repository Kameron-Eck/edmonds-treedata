"""What is the project's own definition of "Edmonds", and what fraction of it
does each year's imagery actually cover?

The 2020 citywide mask / crown layer is the working definition of the study
area, so compare every ortho footprint against it.
"""
import rasterio
from rasterio.warp import transform_bounds
from pathlib import Path
from math import cos, radians

IMG = Path(r"D:\edmonds-pipeline\Imagery")
DRIVE = Path(r"G:\My Drive\treedata")

CANDIDATES = [
    ("2020 mask (phase3)", DRIVE / "phase3" / "edmonds_canopy_mask_2020.tif"),
    ("2016 mask (local)", IMG / "edmonds_canopy_mask_2016.tif"),
    ("2000 mask (local)", IMG / "edmonds_canopy_mask_2000.tif"),
]
ORTHOS = [
    ("2000", IMG / "2000_king_rgb.tif"),
    ("2013", IMG / "2013_king_rgb.tif"),
    ("2015", IMG / "2015_king_rgb.tif"),
    ("2016", IMG / "2016_snoh_rgbi.tif"),
    ("2021s", IMG / "2021_snoh_rgbi.tif"),
    ("2019n", IMG / "2019_naip_rgbi.tif"),
    ("2023n", IMG / "2023_naip_rgbi.tif"),
    ("ccap2016", IMG / "ccap_2016_hires_lc.tif"),
    ("chm", IMG / "lidar_snoh_chm.tif"),
]


def wgs(p):
    with rasterio.open(p) as s:
        return transform_bounds(s.crs, "EPSG:4326", *s.bounds, densify_pts=21)


print("STUDY-AREA CANDIDATES (the project's own 'Edmonds')")
ref = None
for name, p in CANDIDATES:
    if p.exists():
        b = wgs(p)
        print(f"  {name:<22} {b[0]:.5f},{b[1]:.5f},{b[2]:.5f},{b[3]:.5f}")
        if ref is None:
            ref = b
    else:
        print(f"  {name:<22} (absent)")

if ref is None:
    raise SystemExit("no study-area raster found")

W, S, E, N = ref
mid = (S + N) / 2
km_w = (E - W) * 111.320 * cos(radians(mid))
km_h = (N - S) * 110.574
print(f"\nREFERENCE EXTENT = {km_w:.2f} x {km_h:.2f} km "
      f"(lat {S:.4f}..{N:.4f}, lon {W:.4f}..{E:.4f})")

print(f"\n{'layer':<10} {'covers % of ref BBOX':>21} {'lat covered':>22}  missing")
for name, p in ORTHOS:
    if not p.exists():
        continue
    b = wgs(p)
    iw = max(0.0, min(E, b[2]) - max(W, b[0]))
    ih = max(0.0, min(N, b[3]) - max(S, b[1]))
    frac = (iw * ih) / ((E - W) * (N - S)) * 100
    miss = []
    if b[3] < N - 1e-4:
        miss.append(f"N {(N-b[3])*110.574:.2f}km")
    if b[1] > S + 1e-4:
        miss.append(f"S {(b[1]-S)*110.574:.2f}km")
    if b[0] > W + 1e-4:
        miss.append(f"W {(b[0]-W)*111.320*cos(radians(mid)):.2f}km")
    if b[2] < E - 1e-4:
        miss.append(f"E {(E-b[2])*111.320*cos(radians(mid)):.2f}km")
    print(f"{name:<10} {frac:>20.1f}% {b[1]:.4f}..{b[3]:.4f}  "
          + (", ".join(miss) if miss else "-- full coverage --"))
