r"""Convert hand-drawn ArcGIS site polygons into pipeline training-site files.

INPUT  D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid\negative_sites_draw.shp
       (Kam's hand work - read-only here, never modified; fields site/kind/role/quality/notes
       [/yr_from/yr_to once added]). Conventions: role=region is the site outline; role=Tree or
       role=hole polygons are cut-outs (trees Kam traced - for a NEGATIVE site both become
       IGNORE holes; a Tree assertion only differs for positive/treatment sites, later).

OUTPUT per negative site (data plane G:\My Drive\treedata):
       polygons/{Name}_regions.gpkg   region = union(role=region) minus buffered cut-outs
       photos/{Name}_rgb.tif          discovery crop, EPSG:3857 @ the anchor pixel (existing
                                      photo convention), from the 2020 3-in county ortho (D:)
       NO crowns file -> load_site_crowns returns (None, False) -> pure true negative
       (the Negative_Parking pattern); name prefixed Negative_ (guard + citywide injection).

Names are sanitized: "Edmonds Heights K-12" -> Negative_Edmonds_Heights_K12.
Only kind=negative sites are converted; anything else is listed and skipped (treatment/control
intake comes later). Re-runnable; refuses to overwrite an existing regions file unless --force.
"""
import argparse
import sys
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_measure as im  # noqa: E402

DRAWN = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid\negative_sites_draw.shp")
BASE = Path(r"G:\My Drive\treedata")
ORTHO = Path(r"D:\edmonds-pipeline\Imagery\2020_snoh_3in_rgb.tif")   # local, 7.6 cm, anchor epoch
PX_3857 = 0.07464553543473991                                        # anchor pixel (photo convention)
HOLE_BUFFER_M = 2.5
PHOTO_MARGIN_M = 25.0


def sanitize(site: str, kind: str) -> str:
    core = re.sub(r"[^A-Za-z0-9]+", "_", site).strip("_")
    if kind.lower() == "negative" and not core.lower().startswith("negative"):
        core = "Negative_" + core
    return core


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling, transform_bounds
    from rasterio.transform import from_origin
    from rasterio.windows import from_bounds as win_from_bounds

    g = gpd.read_file(DRAWN)
    print(f"{len(g)} drawn features, sites: {sorted(g['site'].dropna().unique())}")
    for site, grp in g.groupby("site"):
        kinds = set(grp.loc[grp["role"].str.lower() == "region", "kind"].str.lower())
        if kinds != {"negative"}:
            print(f"  SKIP '{site}': region kind(s) {kinds or 'none'} - only negative converted now")
            continue
        name = sanitize(site, "negative")
        region = grp[grp["role"].str.lower() == "region"].union_all()
        cuts = grp[grp["role"].str.lower().isin(("tree", "hole"))]
        n_cut = len(cuts)
        if n_cut:
            region = region.difference(cuts.union_all().buffer(HOLE_BUFFER_M))
        area_ha = region.area / 1e4  # EPSG:3857 inflated ~2.2x at this latitude; relative only
        print(f"  {site} -> {name}: region minus {n_cut} cut-out(s); "
              f"{'MULTI' if region.geom_type == 'MultiPolygon' else 'single'} polygon")
        if a.dry_run:
            continue

        out_reg = BASE / "polygons" / f"{name}_regions.gpkg"
        out_photo = BASE / "photos" / f"{name}_rgb.tif"
        if out_reg.exists() and not a.force:
            sys.exit(f"{out_reg} exists - use --force to overwrite")

        gpd.GeoDataFrame({"site": [name]}, geometry=[region], crs="EPSG:3857").to_file(
            out_reg, layer=f"{name}_regions", driver="GPKG")
        print(f"    wrote {out_reg}")

        # discovery crop: region bounds + margin, EPSG:3857 @ anchor pixel, from the local ortho
        minx, miny, maxx, maxy = region.bounds
        minx -= PHOTO_MARGIN_M; miny -= PHOTO_MARGIN_M; maxx += PHOTO_MARGIN_M; maxy += PHOTO_MARGIN_M
        w = int(round((maxx - minx) / PX_3857)); h = int(round((maxy - miny) / PX_3857))
        dst_tf = from_origin(minx, maxy, PX_3857, PX_3857)
        with rasterio.open(ORTHO) as src:
            sb = transform_bounds("EPSG:3857", src.crs, minx, miny, maxx, maxy)
            win = win_from_bounds(*sb, transform=src.transform).round_offsets().round_lengths()
            A = src.read([1, 2, 3], window=win)
            src_tf = src.window_transform(win)
            out = np.zeros((3, h, w), dtype=np.uint8)
            reproject(A, out, src_transform=src_tf, src_crs=src.crs,
                      dst_transform=dst_tf, dst_crs="EPSG:3857", resampling=Resampling.bilinear)
        tmp = out_photo.with_suffix(".part.tif")
        with rasterio.open(tmp, "w", driver="GTiff", width=w, height=h, count=3, dtype="uint8",
                           crs="EPSG:3857", transform=dst_tf, compress="deflate", tiled=True,
                           blockxsize=256, blockysize=256) as dst:
            dst.write(out)
            dst.update_tags(SITE=name, SOURCE=str(ORTHO.name), CREATED="convert_drawn_sites 2026-08-24")
        tmp.replace(out_photo)
        print(f"    wrote {out_photo} ({w}x{h} @ {PX_3857:.4f} m, source {ORTHO.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
