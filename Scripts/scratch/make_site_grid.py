r"""Negative-site snapping grid + drawing template for the ArcGIS "MachineLearning" project.

WHY (2026-08-24, Kam): of the five negative training sites only Parking and Water are clean, and a
contaminated negative teaches the model to suppress real canopy — the standing under-prediction
mechanism. Kam will draw many new negative sites in ArcGIS, snapping to a grid aligned with the
model's own tile lattice, into one shapefile this script pre-creates with the right schema.

THE LATTICE. Training crops tile at TILE_SIZE = 512 px (phase4seg/config.py:100) and the label
frame is the 2020 anchor mask: EPSG:3857, origin (-13625893.973200373, 6084272.795957603), pixel
0.07464553543473991 m. One tile = 38.2185 m; a 4x4-tile block = 152.874 m. Every cell corner this
script writes is computed EXACTLY as origin + k*512*px, so a site snapped to the grid never has a
tile straddling its boundary in the anchor frame.

OUTPUTS -> D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid\
  snap_blocks_153m.shp    4x4-tile cells over the city polygon + 500 m margin (the site unit)
  snap_tiles_38m.shp      single-tile cells over the city + 250 m margin (fine edge adjustment)
  city_boundary_3857.shp  the city polygon, reprojected to the working CRS
  negative_sites_draw.shp EMPTY polygon template Kam draws into (schema below)
  README.txt              snap settings, the ornamental-tree hole-punch rule, pipeline hand-off

One-shot writer (scratch/ convention): safe to re-run — it overwrites its own outputs only.
"""
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_measure as im  # noqa: E402  (CITY_SHP resolves local-first)

# the 2020 anchor lattice (verified against edmonds_canopy_mask_2020.tif this session)
ORIGIN_X = -13625893.973200373
ORIGIN_Y = 6084272.795957603          # top edge; rows grow downward (negative e)
PX = 0.07464553543473991
TILE = 512
TILE_M = TILE * PX                    # 38.2185 m
BLOCK = 4                             # tiles per block edge
BLOCK_M = BLOCK * TILE_M              # 152.874 m
CRS = "EPSG:3857"

OUT = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid")

README = """SITE GRID — snap-to lattice for drawing training sites (2026-08-24)
=====================================================================

WHAT THESE ARE
  snap_blocks_153m.shp   152.874 m squares = 4x4 model tiles. THE SITE UNIT — build site
                         outlines from whole blocks where you can.
  snap_tiles_38m.shp     38.2185 m squares = one 512-px model tile, for fine edge adjustment.
  city_boundary_3857.shp the Edmonds city polygon in the working CRS (EPSG:3857).
  negative_sites_draw.shp DRAW HERE. Empty polygon layer, EPSG:3857, one feature per site
                         (or per hole — see below). Fields:
                           site    site name, e.g. Negative_Ballfield_1 (keep the Negative_ prefix)
                           kind    'negative' (or 'positive' if you also trace positives)
                           role    'region' for the site outline, 'hole' for a tree cut-out
                           quality your own grade, e.g. clean / minor-trees / edge-risk
                           notes   anything worth remembering (mowing, new construction, ...)

  Every grid corner lies EXACTLY on the 2020 anchor raster lattice (origin + k*512*0.0746455 m),
  so a snapped site boundary never splits a training tile.

ARCGIS SETUP
  1. Add all four shapefiles to the MachineLearning project (they are already in EPSG:3857 —
     matches the pipeline; let ArcGIS reproject on the fly for display if your map is different).
  2. Enable Snapping (toolbar) -> vertex + edge snapping; in List By Snapping, leave ONLY
     snap_blocks_153m (and snap_tiles_38m when you need a finer edge) as snap targets.
  3. Draw site outlines as rectangles/polygons with edges on the block lines. Fill the fields.

THE ORNAMENTAL-TREE RULE (why 'role' exists)
  A tree pixel labelled background actively teaches the model to suppress isolated small trees —
  the exact under-prediction failure the negatives exist to fix. But IGNORE pixels are free.
  So a few small trees in an otherwise good site are FINE, handled like this:
    - draw the site outline (role='region');
    - over each recognisable tree/shrub (crown >= ~2 m), draw a small polygon with role='hole',
      same site name, with ~2-3 m of buffer. Circles are fine; snapping NOT needed for holes.
    - don't agonise below ~2 m; when unsure, punch the hole — conservatism costs nothing.
  The pipeline turns region-minus-holes into background and the holes into IGNORE (255), per the
  three-state mask rule (CLAUDE.md rule 6).

HAND-OFF (done by a script later — you only draw)
  When you're done, say so: a converter reads negative_sites_draw.shp, subtracts each site's
  holes from its region, and writes one {site}_regions.gpkg per site into the data plane
  (polygons/). A site with no crowns file is a pure true negative (the Negative_Parking pattern).
  Each site also needs a photos/{site}_rgb.tif crop for discovery — the converter will handle it.
"""


def main():
    import fiona
    import geopandas as gpd
    from shapely.geometry import box
    from shapely.prepared import prep

    OUT.mkdir(parents=True, exist_ok=True)

    city = gpd.read_file(im.CITY_SHP).to_crs(CRS)
    poly = city.union_all() if hasattr(city, "union_all") else city.unary_union
    print(f"city polygon: {poly.area / 1e6:.2f} km2 in {CRS}")

    def grid_layer(cell_m, margin_m, name, id_prefix, tiles_per_cell):
        g = poly.buffer(margin_m)
        minx, miny, maxx, maxy = g.bounds
        # exact lattice indices covering the buffered polygon (origin_y is the TOP edge)
        c0 = int(np.floor((minx - ORIGIN_X) / cell_m))
        c1 = int(np.ceil((maxx - ORIGIN_X) / cell_m))
        r0 = int(np.floor((ORIGIN_Y - maxy) / cell_m))
        r1 = int(np.ceil((ORIGIN_Y - miny) / cell_m))
        prepared = prep(g)
        cells, cols, rows = [], [], []
        for r in range(r0, r1):
            y1 = ORIGIN_Y - r * cell_m
            y0 = y1 - cell_m
            for c in range(c0, c1):
                x0 = ORIGIN_X + c * cell_m
                b = box(x0, y0, x0 + cell_m, y1)
                if prepared.intersects(b):
                    cells.append(b)
                    cols.append(c)
                    rows.append(r)
        gdf = gpd.GeoDataFrame(
            {"cell_col": cols, "cell_row": rows,
             "tile_col0": [c * tiles_per_cell for c in cols],
             "tile_row0": [r * tiles_per_cell for r in rows]},
            geometry=cells, crs=CRS)
        p = OUT / f"{name}.shp"
        gdf.to_file(p)
        print(f"{name}: {len(gdf)} cells of {cell_m:.4f} m -> {p}")
        return gdf

    blocks = grid_layer(BLOCK_M, 500, "snap_blocks_153m", "B", BLOCK)
    tiles = grid_layer(TILE_M, 250, "snap_tiles_38m", "T", 1)

    city.to_file(OUT / "city_boundary_3857.shp")
    print(f"city_boundary_3857: {len(city)} feature(s)")

    # the empty drawing template — fiona so the schema exists with zero features
    schema = {"geometry": "Polygon",
              "properties": {"site": "str:32", "kind": "str:16", "role": "str:8",
                             "quality": "str:16", "notes": "str:254"}}
    with fiona.open(OUT / "negative_sites_draw.shp", "w",
                    driver="ESRI Shapefile", schema=schema, crs=CRS):
        pass
    print("negative_sites_draw.shp: empty template written (site/kind/role/quality/notes)")

    (OUT / "README.txt").write_text(README, encoding="utf-8")

    # alignment proof: 5 random block corners are exact lattice multiples
    rng = np.random.default_rng(0)
    for i in rng.choice(len(blocks), size=min(5, len(blocks)), replace=False):
        x0 = blocks.geometry.iloc[int(i)].bounds[0]
        k = (x0 - ORIGIN_X) / BLOCK_M
        assert abs(k - round(k)) < 1e-9, (x0, k)
    print("alignment proof: block corners are exact anchor-lattice multiples (5/5)")
    print(f"\nDONE -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
