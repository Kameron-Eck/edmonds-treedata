"""Build qc/imagery_pixelsize_and_date.csv — true pixel size (four senses) + date shot, per held acquisition.

Authored 2026-08-23. Grid/CRS cells are re-measured from the local rasters when present (MEASURED);
everything else is authored here with its source URL and verbatim quote. Rules (from the task spec):
  evidence_grade  MEASURED | PUBLISHED | INFERRED | NOT FOUND   (grades the DATE cell)
  px_evidence     grades the pixel-size cells (grid/true = MEASURED from the file; native = source stated)
  a PUBLISHED date needs source_url + verbatim_quote or it is downgraded to NOT FOUND (gate below)
  CONTESTED rows carry both readings (alt_* columns) and are never collapsed to one.
Run:  PYTHONUTF8=1 py -3.12 scratch/imagery_pixelsize_date_build.py
"""
import csv, math, pathlib
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "qc" / "imagery_pixelsize_and_date.csv"
LAT = 47.81                      # Edmonds; cos = 0.67159
COS = math.cos(math.radians(LAT))
FTUS = 0.3048006096012192
LOCAL = [pathlib.Path(r"D:\edmonds-pipeline\Imagery"), pathlib.Path(r"D:\edmonds-pipeline\backup\Full_Image\Pipeline Imagery"),
         pathlib.Path(r"G:\My Drive\treedata\Full_Image\Pipeline Imagery")]

COLS = ["file","year_label","source","grid_px","grid_units","crs","true_ground_cm","effective_cm","native_flight_cm",
        "date_shot","date_precision","single_or_multi_date","evidence_grade","source_url","verbatim_quote","notes",
        "px_evidence","alt_date_shot","alt_source_url","alt_verbatim_quote","row_type"]

def measure(fname):
    """grid/CRS straight from the file (rasterio); None if the file is not reachable."""
    try:
        import rasterio
    except Exception:
        return None
    for d in LOCAL:
        p = d / fname
        if p.exists():
            try:
                with rasterio.open(p) as ds:
                    unit = ds.crs.linear_units if ds.crs else "?"
                    px = ds.res[0]
                    epsg = ds.crs.to_epsg() if ds.crs else None
                    if epsg == 3857:
                        true_cm = px * COS * 100
                    elif "foot" in (unit or "").lower():
                        true_cm = px * FTUS * 100
                    else:
                        true_cm = px * 100
                    return dict(grid_px=round(px, 6), grid_units=("US survey foot" if "foot" in (unit or "").lower() else "metre (Web Mercator, inflated 1/cos(lat))" if epsg == 3857 else unit),
                                crs=f"EPSG:{epsg}", true_ground_cm=round(true_cm, 2))
            except Exception as e:
                return {"error": repr(e)}
    return None

KC_SDC = "https://www5.kingcounty.gov/sdc/?Layer=IMAGE_%s"
KC_IDX = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/%s/FeatureServer/0/query"
SCOPI = "https://snohomishcountywa.gov/5414/Interactive-Map-SCOPI"
WA16 = "https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/NAIP_2016_6in_Ortho_Dates_and_Times_83s/FeatureServer/0/query"
WA15 = "https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/NAIP_2015_1ft_Ortho_Dates_and_Times_83s/FeatureServer/0/query"
ILA = "https://weblink.edmondswa.gov/WebLink/DocView.aspx?id=1462454&dbid=0&repo=EdmondsWA"
NAIP19 = "https://naipeuwest.blob.core.windows.net/naip/v002/wa/2019/wa_fgdc_2019/47122/m_4712214_sw_10_060_20191011.txt"
NAIP23 = "https://naipeuwest.blob.core.windows.net/naip/v002/wa/2023/wa_fgdc_2023/47122/m_4712214_sw_10_060_20231007_20240209.xml"

IDX_NOTE = ("MEASURED 2026-08-23: King County public nadir-frame index queried with the Edmonds city POLYGON "
            "(City Boundry/Edmonds Boundry.shp, esriSpatialRelIntersects); counts are frames intersecting the city, "
            "not the mosaic's seam assignment. Which frame feeds each mosaic pixel is NOT recorded, so the mosaic over "
            "any given crown is one of these days, unknown which.")
KC_CACHE = ("Held pixels are an export of the KingCo_Aerial_YYYY ArcGIS tile cache (gismaps.kingcounty.gov), EPSG:3857, "
            "JPEG-quantised; grid is exactly Web-Mercator LOD %s. In-file metadata: NONE (sweep 2026-08-23: no DateTime/"
            "Software/XMP/IPTC/EXIF/GDAL_METADATA in any held raster).")

ROWS = [
 # ---------------- King County (tile-cache exports) ----------------
 dict(file="1936_king_pan.tif", year_label="1936", source="King County GIS (IMAGE_Ortho1936KCPAN)",
      effective_cm="not measured", native_flight_cm="30.48 (scanned prints: 0.5 ft scan resampled to 1 ft)",
      date_shot="1936", date_precision="year only", single_or_multi_date="unknown (scanned print mosaic)",
      evidence_grade="PUBLISHED", source_url=KC_SDC % "Ortho1936KCPAN",
      verbatim_quote="1936 aerial imagery for western King County from scanned 3 foot by 3 foot prints (boards 0.5 in pixels resampled to 1 foot).",
      notes=KC_CACHE % "18" + " Content covers only 24.4% of the study area (Retractions sheet). No month/season anywhere on the page; change-history dates (2006-2007) are digitisation dates.",
      px_evidence="grid/true MEASURED; native PUBLISHED (SDC page)"),
 dict(file="1998_king_pan.tif", year_label="1998", source="WA DNR via King County GIS (IMAGE_Ortho1998WADNRPAN)",
      effective_cm="not measured", native_flight_cm="91.44 (3 ft product; film 1:12000, 12,000 ft AGL)",
      date_shot="summer 1998", date_precision="season", single_or_multi_date="multi (frame dates stated unavailable)",
      evidence_grade="PUBLISHED", source_url=KC_SDC % "Ortho1998WADNRPAN",
      verbatim_quote="Acquisition period was Summer, 1998. Individual frame or tile acquisition dates are not available.",
      notes=KC_CACHE % "18" + " Held grid 40.1 cm is 2.3x FINER than the 3 ft native: pure oversampling.",
      px_evidence="grid/true MEASURED; native PUBLISHED (SDC page)"),
 dict(file="2000_king_rgb.tif", year_label="2000", source="Emerge Inc. via King County GIS (IMAGE_Ortho2000EmergeNAT, natural-colour DERIVATIVE of EmergeCIR)",
      effective_cm="109 red / 70 green / 68 blue (band-dependent; published 110.8 is red-only)", native_flight_cm="60.96 (2 ft)",
      date_shot="late spring to early fall 2000", date_precision="season (~5 months)", single_or_multi_date="multi (township-level flight-date graphic referenced by the page is a 404)",
      evidence_grade="PUBLISHED", source_url=KC_SDC % "Ortho2000EmergeNAT",
      verbatim_quote="collected in lat spring to early fall 2000 [sic]. Detailed photodate information is not available.",
      notes=KC_CACHE % "18" + " Sensor Kodak DSC460CIR: no blue light recorded, all three held bands NIR-contaminated (Retractions). Wayback target for an agent: https://www5.kingcounty.gov/sdc/raster/ortho/images/ortho2000emergegeneralflightdate.jpg (404 live).",
      px_evidence="grid/true MEASURED; effective MEASURED (Effective_Resolution); native PUBLISHED"),
 dict(file="2002_king_rgb.tif", year_label="2002", source="USGS High Resolution Orthoimagery Seattle/Tacoma 2002 (Selkirk Remote Sensing) as retiled by King County (IMAGE_Ortho2002USGSNAT)",
      effective_cm="57.1", native_flight_cm="33 acquired, delivered at 30.48 (1 ft)",
      date_shot="NOT FOUND", date_precision="-", single_or_multi_date="unknown",
      evidence_grade="NOT FOUND", source_url=KC_SDC % "Ortho2002USGSNAT",
      verbatim_quote="(no acquisition statement on the page; catalog LastUpdated 2003-01-01 is maintenance metadata)",
      notes=KC_CACHE % "18" + " Over Edmonds the cache serves the USGS/NGA Seattle-Tacoma product, NOT IMAGE_Ortho2002KCNAT (which is 'acquired in July 2002' but covers the county-only project). AGENT TARGET: USGS HRO Seattle/Tacoma FGDC metadata (EarthExplorer / TNM / Wayback) carries the per-project acquisition dates.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (REST description: 'acquired at a resolution of 0.33 meter per pixel ... resampled to 1 foot per pixel')",
      alt_date_shot="July 2002 (sibling product IMAGE_Ortho2002KCNAT — does NOT serve Edmonds)", alt_source_url=KC_SDC % "Ortho2002KCNAT",
      alt_verbatim_quote="Natural color orthophotography acquired in July 2002"),
 dict(file="2005_king_rgb.tif", year_label="2005", source="Aerials Express via King County GIS (IMAGE_Ortho2005AerialsExpressNAT)",
      effective_cm="80.7", native_flight_cm="30.48 (1 ft)",
      date_shot="July 2005", date_precision="month", single_or_multi_date="unknown (no per-frame index exists before 2007)",
      evidence_grade="PUBLISHED", source_url=KC_SDC % "Ortho2005AerialsExpressNAT",
      verbatim_quote="Year 2005 (July)",
      notes=KC_CACHE % "19" + " Held grid 20.1 cm vs 1 ft native = 1.5x oversampled, and the file resolves at 80.7 cm — coarser than 2000's nominal grid.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2007_king_rgb.tif", year_label="2007", source="Pictometry International via King County GIS (IMAGE_Ortho2007KCNAT); per-frame index ORTHO_IMAGE07_AREA_759",
      effective_cm="25.5", native_flight_cm="15.24 (0.5 ft west county)",
      date_shot="2007-06-30 to 2007-08-13 (6 days over the city: Jun 30 n=252, Jul 7 481, Jul 8 15, Jul 10 36, Jul 11 173, Aug 13 121)",
      date_precision="window of 45 days, 6 flight days", single_or_multi_date="MULTI (6 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE07_AREA_759",
      verbatim_quote="SHOTDATE field, 1078 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "19" + " " + IDX_NOTE + " SDC page: 'Final version 2007 (July)' — the August frames show 'July' is a simplification.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (SDC: 6 in west)",
      alt_date_shot="July 2007", alt_source_url=KC_SDC % "Ortho2007KCNAT", alt_verbatim_quote="Final version 2007 (July) King County Natural Color orthoimagery acquired by Pictometry"),
 dict(file="2009_king_rgb.tif", year_label="2009", source="Pictometry International via King County GIS (IMAGE_Ortho2009KCNAT); per-frame index ORTHO_IMAGE09_AREA_760",
      effective_cm="26.1", native_flight_cm="15.24 (0.5 ft west county)",
      date_shot="2009-05-01 to 2009-05-16 (3 days over the city: May 1 n=179, May 9 121, May 16 172)",
      date_precision="window of 16 days, 3 flight days", single_or_multi_date="MULTI (3 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE09_AREA_760",
      verbatim_quote="SHOTDATE/YYYYMMDD fields, 472 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "19" + " " + IDX_NOTE + " Early leaf-out. SDC page states no month ('Final version 2009'); the 11/1/2009 change-history date is delivery, not flight.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2012_king_rgb.tif", year_label="2012", source="USGS/NGA Puget Sound Urban Area ortho (Mapcon Mapping, Vexcel UltraCamX/Xp) via King County GIS (IMAGE_Ortho2012KCNAT); photo-centre index ORTHO_IMAGE12_POINT_1447",
      effective_cm="33.7", native_flight_cm="30 (delivered 0.3 m; SP orthos at 0.25/0.50/1.00 ft resampled bilinear)",
      date_shot="2012-03-23 (30 photo centres, 13:25-13:44) and 2012-04-07 (45 photo centres, 12:08-12:46)",
      date_precision="2 flight days", single_or_multi_date="MULTI (2 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE12_POINT_1447",
      verbatim_quote="DATE_STR/TIME_STR fields, 75 photo centres inside the city polygon (query 2026-08-23); DATACOLOR='nir' for all 75",
      notes=KC_CACHE % "19" + " " + IDX_NOTE + " Leaf-off to barely budding. Countywide window PUBLISHED on the SDC page (alt). Index RESOLUTION field = 1 (Apr 7) / 2 (Mar 23), units not stated.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED",
      alt_date_shot="2012-03-23 to 2012-05-08 (countywide)", alt_source_url=KC_SDC % "Ortho2012KCNAT",
      alt_verbatim_quote="The imagery was collected between March 23, 2012 and May 8, 2012."),
 dict(file="2013_king_rgb.tif", year_label="2013", source="Pictometry International via King County GIS (IMAGE_Ortho2013KCNAT); per-frame index ORTHO_IMAGE13_AREA_2061",
      effective_cm="12.6-13.7 (five z20 years measured together; IMAGERY_FACTS 2.2)", native_flight_cm="10.16 (4 in west county)",
      date_shot="2013-06-02 to 2013-06-06 (4 days over the city: Jun 2 n=111, Jun 4 137, Jun 5 218, Jun 6 222)",
      date_precision="window of 5 days, 4 flight days", single_or_multi_date="MULTI (4 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE13_AREA_2061",
      verbatim_quote="ShotDate/YYYYMMDD fields, 688 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " Fully leaf-on. Only year whose held grid (10.0 cm) ~= native (10.16 cm).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2015_king_rgb.tif", year_label="2015 (King)", source="Pictometry International via King County GIS (IMAGE_Ortho2015KCNAT); per-frame index ORTHO_IMAGE15_AREA_2499",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in west county)",
      date_shot="2015-02-15 to 2015-03-08 (6 days over the city: Feb 15 n=5, Feb 18 5, Feb 21 26, Feb 28 111, Mar 7 348, Mar 8 206)",
      date_precision="window of 22 days, 6 flight days", single_or_multi_date="MULTI (6 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE15_AREA_2499",
      verbatim_quote="ShotDate/YYYYMMDD fields, 701 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " LEAF-OFF. This held file is the Pictometry KCNAT product; the three-way 2015 CONTEST (Apr 8/9/17 GeoTerra 2.7 in / Aug 7 4.8 in UFMP) belongs to the City of Edmonds 2015 SERVICE, a different product — see the CoE 2015 row.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2017_king_rgb.tif", year_label="2017 (King)", source="Pictometry International via King County GIS (IMAGE_Ortho2017KCNAT); per-frame index ORTHO_IMAGE17_AREA_2685",
      effective_cm="13.2", native_flight_cm="7.62 (3 in west county); index per-frame GSD median ~6.4 cm",
      date_shot="2017-05-04 to 2017-05-10 (5 days over the city: May 4 n=16, May 6 90, May 8 48, May 9 192, May 10 364)",
      date_precision="window of 7 days, 5 flight days", single_or_multi_date="MULTI (5 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE17_AREA_2685",
      verbatim_quote="ShotDate/YYYYMMDD fields, 710 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " Resolves the May 18 discrepancy in MASTER: May 18 frames (n=215) fall inside the wider bbox -122.42,47.76,-122.32,47.87 but outside the city polygon. Countywide capture window 2017-02-17 to 2017-10-30 (PUBLISHED, SDC index change history).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2019_king_rgb.tif", year_label="2019 (King)", source="Pictometry/EagleView via King County GIS (IMAGE_Ortho2019KCNAT); per-frame index ORTHO_IMAGE19_AREA_2852",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in west county)",
      date_shot="2019-04-25 to 2019-05-08 (7 days over the city: Apr 25 n=92, Apr 30 387, May 1 20, May 4 160, May 6 185, May 7 332, May 8 58)",
      date_precision="window of 14 days, 7 flight days", single_or_multi_date="MULTI (7 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE19_AREA_2852",
      verbatim_quote="ShotDate field (date only, no time), 1234 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " 2019 index also carries CameraLat/CameraLon/Bearing/Alt/FocalLen per frame (photo-centre data).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2021_king_rgb.tif", year_label="2021 (King)", source="Pictometry/EagleView via King County GIS (IMAGE_Ortho2021KCNAT); per-frame index ORTHO_IMAGE21_AREA_2912",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in west county)",
      date_shot="2021-04-14 to 2021-04-17 (4 days over the city: Apr 14 n=135, Apr 15 248, Apr 16 259, Apr 17 20)",
      date_precision="window of 4 days", single_or_multi_date="MULTI (4 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE21_AREA_2912",
      verbatim_quote="ShotDate field, 662 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " NARROWED vs earlier bbox query (Apr 12/14 - May 5): the May 5 frames are outside the city polygon.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2023_king_rgb.tif", year_label="2023 (King)", source="EagleView Technologies via King County GIS (IMAGE_Ortho2023KCNAT); per-frame index ORTHO_IMAGE23_AREA_3073",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in 'Neighborhood' tier incl. SW Snohomish); index per-frame GSD median 6.41 cm",
      date_shot="2023-04-19 to 2023-05-07 (7 days over the city: Apr 19 n=57, Apr 20 84, Apr 25 64, Apr 26 381, Apr 27 169, May 3 336, May 7 34)",
      date_precision="window of 19 days, 7 flight days", single_or_multi_date="MULTI (7 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE23_AREA_3073",
      verbatim_quote="ShotDate field, 1125 frames intersecting the city polygon (query 2026-08-23)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE,
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED",
      alt_date_shot="2023-04-14 to 2023-06-28 (countywide)", alt_source_url=KC_SDC % "Ortho2023KCNAT",
      alt_verbatim_quote="captured by EagleView Technologies between April 14 and June 28, 2023"),
 # ---------------- Snohomish County (HXIP) ----------------
 dict(file="2016_snoh_rgbi.tif", year_label="2016", source="Hexagon Imagery Program (HXIP) via Snohomish County Imagery/Aerial_2016 ImageServer",
      effective_cm="35.4", native_flight_cm="30.48 (1 ft): county mosaic-catalog LowPS=1 and item pixelSizeX=1 for every primary tile over Edmonds (MEASURED 2026-08-23); the 2016 consortium 6-in (15 cm) buy-up exists over Edmonds but is NOT what the county serves",
      date_shot="2016-08-11 (16:52) and 2016-08-12 (09:05, 09:30) — WA consortium 2016 6-in footprints over Edmonds",
      date_precision="window of 2 days, 3 sorties", single_or_multi_date="MULTI (2 days / 3 sorties over the city; footprint = quarter-quarter quads)",
      evidence_grade="INFERRED", source_url=WA16,
      verbatim_quote="SDATE '08/11/2016 16:52' (SUNEL 31) / '08/12/2016 09:05' (SUNEL 34) / '08/12/2016 09:30' (SUNEL 37), THEMENAME hxip_m_4712213/4712214_*_10_15, 11 footprints intersecting the city bbox",
      notes=("Held file = export of the county service (window means identical to exportImage, 2026-08-23) and pixel-DISTINCT from Aerial_2015 and Aerial_2017. "
             "Why INFERRED not PUBLISHED: the dated footprints are the 15 cm consortium product; the county's 1-ft tiles are a different delivery of (presumably) the same flight — "
             "the county mosaic was built from a geodatabase literally named HXIP_2015_Snohomishv3 (service /info/metadata lineage), so the 2015-08-07 HXIP 1-ft flight was a live alternative until the pixel test excluded it. "
             "OPEN: held-file shadows in the footprint labelled 16:52 point WEST (morning), so either that SDATE is UTC (=09:52 PDT) or the county product is a different sortie. Geocortex blurb 'acquired in August 2016' is mis-titled '2017 Aerial Photos'."),
      px_evidence="grid/true MEASURED; effective MEASURED; native MEASURED (service catalog)",
      alt_date_shot="2015-08-07 15:31 (HXIP 2015 1-ft flight; EXCLUDED by pixel comparison against Aerial_2015)", alt_source_url=WA15,
      alt_verbatim_quote="SDATE '08/07/2015 15:31', THEMENAME hxip_m_4712213_ne_10_30, SUNEL 46"),
 dict(file="2021_snoh_rgbi.tif", year_label="2021 (Snoh)", source="HXIP via Snohomish County Imagery/Aerial_2021 ImageServer",
      effective_cm="20.6", native_flight_cm="15.24 (0.5 ft): mosaic-catalog LowPS=0.5, item pixelSizeX=0.5 (MEASURED)",
      date_shot="2021-06-25 to 2021-11-11", date_precision="window of 140 days", single_or_multi_date="unknown (countywide window only)",
      evidence_grade="PUBLISHED", source_url=SCOPI,
      verbatim_quote="The 2021 aerial photos are 6 inch resolution and cover mainly the urban areas. The imagery was collected between June 25, 2021 and November 11, 2021.",
      notes="AGENT TARGET: a WA consortium 2021 flight-date footprint layer (as exists for 2015-2020) would narrow this to days. Service metadata carries no date (sweep 2026-08-23).",
      px_evidence="grid/true MEASURED; effective MEASURED; native MEASURED (service catalog)"),
 # ---------------- City of Edmonds ----------------
 dict(file="2017_coe_rgb.tif", year_label="2017 (CoE)", source="City of Edmonds Basemap/2017_Aerial_Cached (source raster 2017_Aerial.tif, 0.25 ftUS EPSG:2285); acquirer NOT ESTABLISHED",
      effective_cm="7.6 (indicative; per-site sd +/-0.41-1.17 px)", native_flight_cm="7.62 (0.25 ftUS source raster)",
      date_shot="NOT FOUND", date_precision="-", single_or_multi_date="unknown",
      evidence_grade="NOT FOUND", source_url="https://weblink.edmondswa.gov/WebLink/0/edoc/1654952/",
      verbatim_quote="In 2017 flyovers and imagery was done by the consultant who did the public engagement, PlanIt Geo, for Pierce, Snohomish and King Counties as part of a stormwater modeling project.",
      notes="The quote (council minutes 2023-07-25 p.15) is WEAK: conflates collector with analytics consultant. Candidate: King County 2017 flight 2017-05-04..05-10 over Edmonds (MEASURED on 2017_king_rgb.tif) — attribution to the city file UNPROVEN; Snohomish Aerial_2017 is a 1-ft HXIP product (2017-08-15/21) and cannot be a 3-in source. AGENT TARGET: 2017 CoE contract/budget line, sibling products, neighbour cities.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (service source-raster XML)"),
 dict(file="2020_coe_rgb.tif", year_label="2020 (ANCHOR)", source="City of Edmonds Basemap/2020_Aerial_Cached; source = Snohomish County 2020 EagleView/Pictometry regional project (WASNOH20_3in) per the 2021 ILA",
      effective_cm="7.0", native_flight_cm="7.62 (0.25 ftUS; county Aerial_2020 LowCellSize 0.25, dimResol 0.250000 ftUS)",
      date_shot="2020-04-13 to 2020-07-13", date_precision="window of 92 days", single_or_multi_date="unknown — whether the Edmonds AOI is single- or multi-date is UNRESOLVED and outranks the date",
      evidence_grade="INFERRED", source_url=SCOPI,
      verbatim_quote="The 2020 aerial photos are 3 inch resolution in the urban areas and 9 inch resolution in the rural areas, excluding much of the unpopulated mountainous portion of eastern Snohomish County, and were taken between April 13th and July 13th, 2020.",
      notes=("Chain: ILA 2021 (Laserfiche id 1462454) Work Order p.14 'Upon completion of the 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects ... County will provide Edmonds with orthogonal imagery'; "
             "city service keyProperties carry NO acquisition date (MrSID/MG4 mosaic lost it). The window is PUBLISHED for the county product; the link to the city file is documented by contract but inferential. "
             "DEFINITIVE PIN = EagleView flight log / photo-centre index via Snohomish County DoIT (PRR citing Contract Routing Form No. 20210127) or a CONNECTExplorer capture-date screenshot (city holds up to 10 accounts)."),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (county service)",
      alt_date_shot="(ILA text, for the chain)", alt_source_url=ILA,
      alt_verbatim_quote="Upon completion of the 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects and receipt of imagery by County, County will provide Edmonds with orthogonal imagery for Edmonds's identified area of interest"),
 dict(file="2022_coe_rgb.tif", year_label="2022 (CoE)", source="City of Edmonds Basemap/2022_Aerial_Cached; source = Snohomish County 2022 regional project (WASNOH22_3in) per the 2021 ILA",
      effective_cm="6.5", native_flight_cm="7.62 (0.25 ftUS; county Aerial_2022 LowCellSize 0.25; MrSID input GeoTIFF geokeys EPSG:2285 ftUS)",
      date_shot="2022-04-06 to 2022-07-11 (urban 3 in)", date_precision="window of 96 days", single_or_multi_date="unknown",
      evidence_grade="INFERRED", source_url=SCOPI,
      verbatim_quote="The 2022 3 inch resolution aerial photos in the urban areas, were captured between April 6, 2022 and July, 11 2022.",
      notes="Same chain and same definitive pin as 2020 (one PRR covers 2020/2022/2024).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (county service)",
      alt_date_shot="(ILA text)", alt_source_url=ILA, alt_verbatim_quote="Upon completion of the 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects ..."),
 dict(file="2024_coe_rgb.tif", year_label="2024 (CoE)", source="City of Edmonds Basemap/2024_Aerial_Cached (Edmonds2024.sid); source = Snohomish County 2024 regional project (WASNOH24_3in) per the 2021 ILA",
      effective_cm="6.8", native_flight_cm="7.62 (0.25 ftUS; county Aerial_2024 LowCellSize 0.25)",
      date_shot="2024-03-31 to 2024-05-31 (urban 3 in)", date_precision="window of 61 days", single_or_multi_date="unknown",
      evidence_grade="INFERRED", source_url=SCOPI,
      verbatim_quote="The 2024 3 inch resolution aerial photos in the urban areas, were captured between March 31, 2024 and May, 31 2024.",
      notes="Same chain and same definitive pin as 2020.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (county service)",
      alt_date_shot="(ILA text)", alt_source_url=ILA, alt_verbatim_quote="Upon completion of the 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects ..."),
 dict(file="(not held) City of Edmonds Basemap/2015_Aerial_Cached", year_label="2015 (CoE service)", source="City of Edmonds (source raster Ed_Aerial_2015.tif, 0.25 ftUS, LZW)",
      grid_px="LOD 21 cache (0.0746 WM m)", grid_units="metre (Web Mercator)", crs="EPSG:3857 (cache); source EPSG:2285", true_ground_cm="5.01 (cache) / 7.62 (source)",
      effective_cm="not measured", native_flight_cm="7.62 (0.25 ftUS source) — vs 6.86 (0.225 ft, GeoTerra consortium spec) vs 12.19 (4.8 in, UFMP)",
      date_shot="CONTESTED: 2015-04-08/09/17 (GeoTerra consortium photo centres) vs 2015-02-15..03-08 (King Pictometry) vs 2015-08-07 (UFMP '4.8 in')",
      date_precision="-", single_or_multi_date="unknown",
      evidence_grade="NOT FOUND", source_url="(see Contradictions sheet; three sources)",
      verbatim_quote="-",
      notes="Included so the contest stops contaminating the held 2015_king_rgb.tif row. Likely explanation: the UFMP canopy-assessment imagery is a different dataset from the city basemap. Edmonds signed the 2015 consortium agreement 2015-06-23 ($3,696.21).",
      px_evidence="grid PUBLISHED (service); native PUBLISHED (source-raster XML)", row_type="context (not held)"),
 # ---------------- NAIP ----------------
 dict(file="2019_naip_rgbi.tif", year_label="2019n", source="USDA FSA NAIP WA 2019 (DOQQ m_4712213/m_4712214; flown by Hexagon under the 2019 program)",
      effective_cm="95.1", native_flight_cm="60 (collected and delivered at 60 cm)",
      date_shot="2019-10-11", date_precision="single day", single_or_multi_date="single (all Edmonds DOQQs carry 20191011)",
      evidence_grade="PUBLISHED", source_url=NAIP19,
      verbatim_quote="Time_Period_of_Content: Time_Period_Information: Single_Date/Time: Calendar_Date: 20191011",
      notes="OCTOBER — weakens the 'NAIP is leaf-on by spec' assumption. Corroborated by the WA consortium 2019 1-ft flight-area layer IDATE '2019 -10-11'.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2023_naip_rgbi.tif", year_label="2023n (was mislabelled 2022n)", source="USDA FSA NAIP WA 2023 (DOQQ m_4712213/m_4712214)",
      effective_cm="83.1", native_flight_cm="60 delivered (2021/2023-era WA NAIP collected finer and rectified to 60 cm)",
      date_shot="2023-10-07", date_precision="single day", single_or_multi_date="single (all 8 Edmonds QQs: m_47122{13,14}_*_10_060_20231007_20240209)",
      evidence_grade="PUBLISHED", source_url=NAIP23,
      verbatim_quote="m_4712214_ne_10_060_20231007.tif (date field of the DOQQ file name, ISO metadata)",
      notes="OCTOBER. Held bands 1-3 byte-identical to rgb_2023, band 4 to ir_2023 (DataLake_Issues).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 # ---------------- reference rasters (flagged, not imagery acquisitions) ----------------
 dict(file="lidar_snoh_chm.tif", year_label="~2016 (lidar)", source="USGS 3DEP HAG via Planetary Computer, reprojected by the project",
      effective_cm="n/a (bilinear-upsampled ~2 m product)", native_flight_cm="~200 (HAG raster); lidar 0.7 m spacing",
      date_shot="2016-03-17 to 2017-06-06 (USGS/WADNR lidar collection)", date_precision="window of 15 months", single_or_multi_date="multi",
      evidence_grade="PUBLISHED", source_url="https://www.fisheries.noaa.gov/inport/item/51853",
      verbatim_quote="(collection window per IMAGERY_FACTS 8.1, sourced from InPort 51853 — REFETCH NEEDED)",
      notes="UNITS TRAP #4: grid is 1.0 m in EPSG:3857 = 67.2 cm true ground at 47.81N, not 1 m. Row included for completeness; excluded from the imagery count.",
      px_evidence="grid/true MEASURED; native PUBLISHED", row_type="reference raster"),
 dict(file="ccap_2016_hires_lc_snohfull.tif", year_label="2016 (C-CAP ref)", source="NOAA OCM C-CAP hi-res land cover, Snohomish County 2016 (InPort 53263)",
      effective_cm="n/a (thematic)", native_flight_cm="100 (1 m product)",
      date_shot="NOT FOUND (source-imagery date; InPort 53263 returns 'Catalog Item Not Retrievable')", date_precision="-", single_or_multi_date="n/a",
      evidence_grade="NOT FOUND", source_url="https://www.fisheries.noaa.gov/inport/item/53263", verbatim_quote="Catalog Item Not Retrievable",
      notes="AGENT TARGET: Wayback copy of InPort 53263 / the .img sidecar metadata (wa_snohomish_co_ccap_hr_landcover20190314.img). Reference raster, not an imagery acquisition.",
      px_evidence="grid/true MEASURED; native PUBLISHED", row_type="reference raster"),
 dict(file="ccap_2021_hires_lc.tif", year_label="2020-21 (C-CAP v2 ref)", source="NOAA OCM C-CAP hi-res v2 'Refined' (Ecopia extraction, NV5 refinement)",
      effective_cm="n/a (thematic)", native_flight_cm="100 (1 m extraction from <=30 cm imagery)",
      date_shot="2020-2021 vintage (source imagery dates not stated per pixel)", date_precision="year range", single_or_multi_date="multi (mosaic of vendor imagery)",
      evidence_grade="PUBLISHED", source_url="(lineage XML cc_wa_puget_2021_ccap_v2_hires_landcover.xml — URL to be re-fetched)",
      verbatim_quote="Initial 1m spatial resolution feature extraction for Impervious, Water, and Canopy (tree and scrub/shrub) mapping was conducted by Ecopia AI",
      notes="Reference raster, not an imagery acquisition. Date of the underlying imagery is the agent question.",
      px_evidence="grid/true MEASURED; native PUBLISHED", row_type="reference raster"),
]

def gate(r):
    """A date that claims PUBLISHED must carry a fetched URL and a quote; otherwise downgrade."""
    if r.get("evidence_grade") == "PUBLISHED":
        if not str(r.get("source_url","")).startswith("http") or not str(r.get("verbatim_quote","")).strip("-( "):
            r["evidence_grade"] = "NOT FOUND"; r["notes"] = "GATE: published date without fetched URL+quote -> downgraded. " + r.get("notes","")
    return r

def main():
    rows = []
    for r in ROWS:
        r = dict(r); r.setdefault("row_type", "held imagery")
        m = measure(r["file"]) if r["row_type"] != "context (not held)" else None
        if m and "error" not in m:
            for k, v in m.items(): r[k] = v
        elif r["row_type"] != "context (not held)":
            r.setdefault("grid_px", "file not reachable at build time")
        rows.append(gate(r))
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in COLS})
    n_held = sum(1 for r in rows if r["row_type"] == "held imagery")
    print(f"wrote {OUT}: {len(rows)} rows ({n_held} held imagery, {len(rows)-n_held} reference/context)")
    for r in rows: print(f"  {r['file'][:42]:42s} grid={r.get('grid_px')} true={r.get('true_ground_cm')} | {r['evidence_grade']:9s} | {str(r['date_shot'])[:60]}")

if __name__ == "__main__":
    main()
