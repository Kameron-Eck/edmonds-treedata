"""trend8 hot spots — WHERE the loss is, the map series' real deliverable.

2 m common grid: LOSS cell = trend8 2016 canopy AND 2024 non-canopy;
PERSISTENT loss additionally already non-canopy in 2021 (an artifact
flickers, a removal stays removed). Clusters >= 0.1 ha reported with
centroid + area; every Panel A verified loss point gets its containing-
cluster distance. Outputs: phase4/qc/trend8_hotspots.csv (clusters),
trend8_hotspot_map.png (city overview), panel_a_loss_crosscheck.csv.
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
from scipy import ndimage

from lake import BASE

MASKS = BASE / "phase4" / "masks"
CITY = BASE / "City Boundry" / "Edmonds Boundry.shp"
QC = BASE / "phase4" / "qc"
OUTD = Path(__file__).resolve().parents[3] / "phase4" / "qc"
CELL, EPSG = 2.0, 26910
MIN_HA = 0.1


def grid_mask(year, tf, w, h):
    p = MASKS / f"edmonds_canopy_mask_{year}_trend8_{year}.tif"
    with rasterio.open(p) as src:
        with WarpedVRT(src, crs=f"EPSG:{EPSG}", transform=tf, width=w, height=h,
                       resampling=Resampling.average, src_nodata=255,
                       nodata=float("nan"), dtype="float32") as v:
            a = v.read(1)
    return a >= 0.5, np.isfinite(a)


def main():
    import geopandas as gpd
    city = gpd.read_file(CITY).to_crs(EPSG)
    minx, miny, maxx, maxy = city.total_bounds
    tf = Affine(CELL, 0, float(np.floor(minx)), 0, -CELL, float(np.ceil(maxy)))
    w = int(np.ceil((maxx - minx) / CELL)) + 1
    h = int(np.ceil((maxy - miny) / CELL)) + 1
    inside = rfeat.rasterize(((g, 1) for g in city.geometry), out_shape=(h, w),
                             transform=tf, fill=0, dtype="uint8").astype(bool)
    c16, v16 = grid_mask("2016", tf, w, h)
    c21, v21 = grid_mask("2021", tf, w, h)
    c24, v24 = grid_mask("2024", tf, w, h)
    ok = inside & v16 & v21 & v24
    loss = ok & c16 & ~c24
    persist = loss & ~c21
    lab, n = ndimage.label(persist, structure=np.ones((3, 3)))
    print(f"loss cells {loss.sum():,} ({loss.sum()*4/1e4:.1f} ha); "
          f"persistent {persist.sum():,} ({persist.sum()*4/1e4:.1f} ha); "
          f"{n} raw clusters")
    sizes = ndimage.sum_labels(np.ones_like(lab), lab, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s * 4 / 1e4 >= MIN_HA]
    cents = ndimage.center_of_mass(persist, lab, keep)
    rows = []
    for cid, (cy, cx) in zip(keep, cents):
        x, y = tf * (cx + 0.5, cy + 0.5)
        rows.append(dict(cluster=cid, area_ha=round(float(sizes[cid - 1]) * 4 / 1e4, 2),
                         x=round(x, 1), y=round(y, 1)))
    rows.sort(key=lambda r: -r["area_ha"])
    with io.open(OUTD / "trend8_hotspots.csv", "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["cluster", "area_ha", "x", "y"])
        wr.writeheader(); wr.writerows(rows)
    print(f"{len(rows)} clusters >= {MIN_HA} ha; top 5:")
    for r in rows[:5]:
        print(f"  {r['area_ha']:6.2f} ha @ ({r['x']:.0f},{r['y']:.0f})")

    # Panel A verified-loss cross-check
    pts = {r["point_id"]: r for r in csv.DictReader(
        io.open(QC / "panel_a_points.csv", encoding="utf-8", newline=""))}
    lab_final = {}
    for fname in ("panel_a_labels.csv", "panel_a_verify.csv"):
        p = QC / fname
        if p.exists():
            for r in csv.DictReader(io.open(p, encoding="utf-8", newline="")):
                if r["label"] == "undo":
                    lab_final.pop(r["point_id"], None)
                else:
                    lab_final[r["point_id"]] = r["label"]
    losses = [pts[pid] for pid, l in lab_final.items()
              if l == "loss" and pts[pid]["kind"] == "live"]
    hit = near = far = 0
    dil = ndimage.binary_dilation(loss, iterations=5)   # 10 m halo
    out = []
    for r in losses:
        col = int((float(r["x"]) - tf.c) / CELL)
        row = int((tf.f - float(r["y"])) / CELL)
        inb = 0 <= row < h and 0 <= col < w
        state = ("in_loss" if inb and loss[row, col] else
                 "within_10m" if inb and dil[row, col] else "not_in_map_loss")
        hit += state == "in_loss"; near += state == "within_10m"; far += state == "not_in_map_loss"
        out.append(dict(point_id=r["point_id"], x=r["x"], y=r["y"], map_state=state))
    with io.open(OUTD / "panel_a_loss_crosscheck.csv", "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["point_id", "x", "y", "map_state"])
        wr.writeheader(); wr.writerows(out)
    print(f"Panel A verified losses vs map loss: in-loss {hit}, within-10m {near}, "
          f"absent {far} of {len(losses)}")

    # overview PNG
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 14))
    base = np.zeros((h, w, 3))
    base[inside] = (0.92, 0.92, 0.90)
    base[ok & c16] = (0.75, 0.85, 0.75)
    base[loss] = (1.0, 0.55, 0.2)
    base[persist] = (0.85, 0.1, 0.1)
    ax.imshow(base)
    for r in losses:
        col = (float(r["x"]) - tf.c) / CELL
        row = (tf.f - float(r["y"])) / CELL
        ax.plot(col, row, "b+", ms=8, mew=1.6)
    ax.set_title("Edmonds canopy loss 2016→2024 (trend8 maps)\n"
                 "green=2016 canopy, orange=loss, red=persistent loss (already gone by 2021), "
                 "blue + = Kam's verified loss points")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUTD / "trend8_hotspot_map.png", dpi=140)
    print(f"wrote {OUTD / 'trend8_hotspot_map.png'}")


if __name__ == "__main__":
    main()
