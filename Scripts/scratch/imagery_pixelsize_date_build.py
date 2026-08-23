"""Build qc/imagery_pixelsize_and_date.csv — true pixel size (four senses) + date shot, per held acquisition.

Authored 2026-08-23; v1 merged the 9-agent hunt + refetch-verify pass of 2026-08-23 (evidence: qc/imagery_date_evidence/). Grid/CRS cells are re-measured from the local rasters when present (MEASURED);
everything else is authored here with its source URL and verbatim quote. Rules (from the task spec):
  evidence_grade  MEASURED | PUBLISHED | INFERRED | NOT FOUND   (grades the DATE cell)
  px_evidence     grades the pixel-size cells (grid/true = MEASURED from the file; native = source stated)
  a PUBLISHED date needs source_url + verbatim_quote or it is downgraded to NOT FOUND (gate below)
  CONTESTED rows carry both readings (alt_* columns) and are never collapsed to one.
Run:  PYTHONUTF8=1 py -3.12 scratch/imagery_pixelsize_date_build.py
"""
import csv, math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
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

WB = "https://web.archive.org/web/%s/http://www.metrokc.gov/gis/sdc/raster/ortho/%s"
ILA = "https://weblink.edmondswa.gov/WebLink/DocView.aspx?id=1462454&dbid=0&repo=Edmonds"      # repo=Edmonds (repo=EdmondsWA lands on Sign In)
MIN2023 = "https://weblink.edmondswa.gov/WebLink/DocView.aspx?id=1654952&dbid=0&repo=Edmonds"
EV2020 = "https://gismaps.everettwa.gov/manarcgis/rest/services/Imagery/Image2020jp2/ImageServer?f=json"
EV2022 = "https://gismaps.everettwa.gov/manarcgis/rest/services/Imagery/Image2022_3in_sid/ImageServer/keyProperties?f=json"
COE = "https://maps.edmondswa.gov/gis/rest/services/Basemap/%s"
WX = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=KPAE&data=skyc1&data=skyl1&data=vsby&data=wxcodes&year1=%s&month1=%s&day1=%s&year2=%s&month2=%s&day2=%s&tz=America%%2FLos_Angeles&format=onlycomma&report_type=3"
EVID = "qc/imagery_date_evidence"
WX_NOTE = ("Weather elimination (ASOS KPAE+KSEA+KBFI, criterion calibrated to 46/46 known Edmonds flight days; %s): %s. "
           "ELIMINATES ONLY - no surviving day is favoured. Per-day table: " + EVID + "/weather/flyable_days.csv.")
SNOH_CHAIN = ("ILA 2021 (Laserfiche id 1462454, repo=Edmonds) Work Order p.14: 'Upon completion of the 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects "
              "... County will provide Edmonds with orthogonal imagery for Edmonds's identified area of interest'. Contract vehicle for a records request: King County RFP 1166-18-PCR "
              "(EagleView Technology Corp) via Snohomish County Piggyback PB-19-14BC (Legistar matter 2024-1168). DEFINITIVE PIN = EagleView flight log / photo-centre index "
              "via Snohomish County DoIT (Viggo Forde), or a CONNECTExplorer capture-date screenshot (Edmonds holds up to ten accounts under the ILA).")

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
      verbatim_quote="Acquisition period was Summer, 1998.  Individual frame or tile acquisition dates are not available.",
      notes=KC_CACHE % "18" + " Held grid 40.1 cm is 2.3x FINER than the 3 ft native: pure oversampling.",
      px_evidence="grid/true MEASURED; native PUBLISHED (SDC page)"),
 dict(file="2000_king_rgb.tif", year_label="2000", source="Emerge Inc. (contracted via Pacific Meridian / Space Imaging) via King County GIS (IMAGE_Ortho2000EmergeNAT, natural-colour DERIVATIVE of EmergeCIR)",
      effective_cm="109 red / 70 green / 68 blue (band-dependent; published 110.8 is red-only)", native_flight_cm="60.96 (2 ft)",
      date_shot="2000-06-26 (the township block containing Edmonds: T27N R3E / T27N R4E, per King County's flight-date graphic)",
      date_precision="single day (township-block generalisation, NOT per-frame)", single_or_multi_date="single date for the Edmonds block per the graphic; project is multi-date (2000-05-24 to 09-23)",
      evidence_grade="PUBLISHED", source_url=WB % ("20081010173648if_", "images/ortho2000emergegeneralflightdate.jpg"),
      verbatim_quote="2000-06-26 (callout label on the graphic's peach block containing cells t27r03, t27r04, t27r05, t28r04, t28r05) ... [live SDC page, IMAGE_Ortho2000EmergeNAT:] Detailed photodate information is not available. ... A general overview at the township-level for data capture dates can interpolated from https://www5.kingcounty.gov/sdc/raster/ortho/images/ortho2000emergegeneralflightdate.jpg",
      notes=(KC_CACHE % "18" + " The graphic 404s live; the ONLY Wayback capture (CDX domain search on metrokc.gov, capture 20081010173648) was read by the agent and re-read by the session lead (" + EVID + "/king2000/). "
             "Edmonds township identity from BLM PLSS (T27N R03E at -122.3775,47.8107; T27N R04E at -122.3150,47.8100). Per-tile YYYYMMDD dates once existed in vendor filenames but King renamed tiles to tileXX.tif; the surviving index is emerge_nat.dbf. "
             "Sensor Kodak DSC460CIR: 'Blue light is outside the filter's bandpass, so that none of the incident blue light reaches the sensor' (archived EmergeCIR FGDC)."),
      px_evidence="grid/true MEASURED; effective MEASURED (Effective_Resolution); native PUBLISHED",
      alt_date_shot="2000-05-24 to 2000-09-23 (countywide project window, Currentness_Reference: Acquisition date)", alt_source_url=WB % ("20040102162255if_", "Ortho2000EmergeCIRMetadata.html"),
      alt_verbatim_quote="Time_Period_of_Content: Time_Period_Information: Range_of_Dates/Times: Beginning_Date:  20000524 Ending_Date:  20000923 Currentness_Reference:  Acquisition date"),
 dict(file="2002_king_rgb.tif", year_label="2002", source="USGS High Resolution Orthoimagery, Seattle/Tacoma 2002 (Homeland Security; flown by Selkirk Remote Sensing) as retiled by King County (IMAGE_Ortho2002USGSNAT)",
      effective_cm="57.1", native_flight_cm="33 acquired; delivered grid 0.98 ft = 29.9-30.0 cm (NOT 30.48): tile names '_02n098' = 98/100 ft; WA state copy LowPS 0.9846 ftUS = 30.01 cm",
      date_shot="NOT FOUND for the Edmonds pixels. CONTESTED product-level date 2002-06-11 (two named Selkirk frames near Bellevue, ~24 km south)",
      date_precision="-", single_or_multi_date="unknown",
      evidence_grade="NOT FOUND", source_url=WB % ("20040225060658if_", "Ortho2002USGSNATMetadata.html"),
      verbatim_quote="Description_of_Geographic_Extent: WRIA 8 Bounding_Coordinates: West_Bounding_Coordinate:  -122.05233309 East_Bounding_Coordinate:  -122.03790177 North_Bounding_Coordinate:  47.60259646 South_Bounding_Coordinate:  47.58876645",
      notes=(KC_CACHE % "18" + " The live SDC page for this layer returns HTTP 500 (2026-08-23, 3 attempts) - cite the archived FGDC. Over Edmonds the cache serves the USGS/NGA Seattle-Tacoma product, NOT IMAGE_Ortho2002KCNAT ('acquired in July 2002', county-only project). "
             "The archived FGDC's top-level block self-labels 'Beginning_Date: 20020611 Ending_Date: 20020611 Currentness_Reference: Publication date', while its lineage block labels the same date 'Aerial photography used in orthorectification' for frames 1192_6574_089 / 1193_6574_090 and 'Field control and ABGPS' 20020611-20020620. "
             "No per-frame or per-township index exists for 2002 (CDX sweep of both King hosts: the 2000 graphic is the only flight-date graphic ever published). HRO is retired from The National Map; ScienceBase has no project record. Remaining route: EarthExplorer HRO entity-level FGDC (M2M login)."),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (archived FGDC + WA state service)",
      alt_date_shot="2002-06-11 (product-level; CONTESTED currentness - see notes)", alt_source_url=WB % ("20040225060658if_", "Ortho2002USGSNATMetadata.html"),
      alt_verbatim_quote="Source_Time_Period_of_Content: Time_Period_Information: Single_Date/Time: Calendar_Date:  20020611 Source_Citation_Abbreviation:  1192_6574_089 Source_Contribution:  Aerial photography used in orthorectification"),
 dict(file="2005_king_rgb.tif", year_label="2005", source="Aerials Express via King County GIS (IMAGE_Ortho2005AerialsExpressNAT)",
      effective_cm="80.7", native_flight_cm="30.48 (1 ft)",
      date_shot="July 2005", date_precision="month", single_or_multi_date="unknown (no per-frame index exists before 2007; no finer date exists in King County's archive - established by CDX sweep, not assumed)",
      evidence_grade="PUBLISHED", source_url=WB % ("20061008084602if_", "Ortho2005AexpNatMetadata.html"),
      verbatim_quote="Time_Period_of_Content: Time_Period_Information: Range_of_Dates/Times: Beginning_Date:  200507 Ending_Date:  200507 Currentness_Reference:  Ground Condition",
      notes=(KC_CACHE % "19" + " Held grid 20.1 cm vs 1 ft native = 1.5x oversampled, and the file resolves at 80.7 cm - coarser than 2000's nominal grid. Delivery (Aug 2006, portable hard drive) is NOT the flight date. "
             "The record's Bounding_Coordinates (North 47.74) are JUNK and would exclude Edmonds; the published extent graphic (Ortho2005AexpNatExtent.jpg, archived) shows Edmonds inside coverage."),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED",
      alt_date_shot="July 2005", alt_source_url=KC_SDC % "Ortho2005AerialsExpressNAT", alt_verbatim_quote="Year 2005 (July)"),
 dict(file="2007_king_rgb.tif", year_label="2007", source="Pictometry International via King County GIS (IMAGE_Ortho2007KCNAT); per-frame index ORTHO_IMAGE07_AREA_759",
      effective_cm="25.5", native_flight_cm="15.24 (0.5 ft west county)",
      date_shot="2007-06-30 to 2007-08-13 (6 days over the city: Jun 30 n=252, Jul 7 481, Jul 8 15, Jul 10 36, Jul 11 173, Aug 13 121)",
      date_precision="window of 45 days, 6 flight days", single_or_multi_date="MULTI (6 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE07_AREA_759",
      verbatim_quote="\"IMAGENAME\":\"WAKING035400NeighOrtho1546_070707\" ... \"SHOTDATE\":\"2007/07/07 18:27:03\" (first of 1078 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2007_ORTHO_IMAGE07_AREA_759_citypoly_first3.json)",
      notes=KC_CACHE % "19" + " " + IDX_NOTE + " SDC page: 'Final version 2007 (July)' - the August frames show 'July' is a simplification.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (SDC: 6 in west)",
      alt_date_shot="July 2007", alt_source_url=KC_SDC % "Ortho2007KCNAT", alt_verbatim_quote="Final version 2007 (July) King County Natural Color orthoimagery acquired by Pictometry"),
 dict(file="2009_king_rgb.tif", year_label="2009", source="Pictometry International via King County GIS (IMAGE_Ortho2009KCNAT); per-frame index ORTHO_IMAGE09_AREA_760",
      effective_cm="26.1", native_flight_cm="15.24 (0.5 ft west county)",
      date_shot="2009-05-01 to 2009-05-16 (3 days over the city: May 1 n=179, May 9 121, May 16 172)",
      date_precision="window of 16 days, 3 flight days", single_or_multi_date="MULTI (3 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE09_AREA_760",
      verbatim_quote="\"IMAGENAME\":\"WAKING042400NeighOrtho77930_090509\" ... \"SHOTDATE\":\"2009/05/09 20:58:13\" (first of 472 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2009_ORTHO_IMAGE09_AREA_760_citypoly_first3.json)",
      notes=KC_CACHE % "19" + " " + IDX_NOTE + " Early leaf-out. SDC page states no month ('Final version 2009'); the 11/1/2009 change-history date is delivery, not flight.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2012_king_rgb.tif", year_label="2012", source="USGS/NGA Puget Sound Urban Area ortho (Mapcon Mapping, Vexcel UltraCamX/Xp) via King County GIS (IMAGE_Ortho2012KCNAT); photo-centre index ORTHO_IMAGE12_POINT_1447",
      effective_cm="33.7", native_flight_cm="30 (delivered 0.3 m; SP orthos at 0.25/0.50/1.00 ft resampled bilinear)",
      date_shot="2012-03-23 (30 photo centres in the city, 13:25-13:44 local) and 2012-04-07 (45 photo centres, 12:08-12:46 local)",
      date_precision="2 flight days", single_or_multi_date="MULTI (2 days) - and the split is MEASURABLE per location: north Edmonds = Mar 23 geometry (6/7 sites), south Edmonds includes Apr 7 geometry (shadow solar dating, " + EVID + "/shadow_dating_2020/ctrl_scored.csv)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE12_POINT_1447",
      verbatim_quote="\"DATACOLOR\":\"nir\" ... \"DATE_STR\":\"Apr.07.2012\" ... \"TIME_STR\":\"12:46:28\" (first of 75 photo centres inside the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2012_ORTHO_IMAGE12_POINT_1447_citypoly_first3.json)",
      notes=(KC_CACHE % "19" + " " + IDX_NOTE + " Leaf-off to barely budding. Index times are LOCAL (13:35 UTC would put the sun below the horizon). Over the wider bbox the windows are 13:25-13:46 (Mar 23, n=61) and 11:51-13:11 (Apr 7, n=184). "
             "Index RESOLUTION field = 1 (Apr 7) / 2 (Mar 23), units not stated. Used as the POSITIVE CONTROL for shadow-geometry dating: 8/10 sites recovered an azimuth inside a real flight window (chance 0.197, P=6.9e-5)."),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED",
      alt_date_shot="2012-03-23 to 2012-05-08 (countywide)", alt_source_url=KC_SDC % "Ortho2012KCNAT",
      alt_verbatim_quote="The imagery was collected between March 23, 2012 and May 8, 2012."),
 dict(file="2013_king_rgb.tif", year_label="2013", source="Pictometry International via King County GIS (IMAGE_Ortho2013KCNAT); per-frame index ORTHO_IMAGE13_AREA_2061",
      effective_cm="12.6-13.7 (five z20 years measured together; IMAGERY_FACTS 2.2)", native_flight_cm="10.16 (4 in west county)",
      date_shot="2013-06-02 to 2013-06-06 (4 days over the city: Jun 2 n=111, Jun 4 137, Jun 5 218, Jun 6 222)",
      date_precision="window of 5 days, 4 flight days", single_or_multi_date="MULTI (4 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE13_AREA_2061",
      verbatim_quote="\"ImageName\":\"WAKING042400NeighOrtho8690_130602\" ... \"ShotDate\":\"2013/06/02 18:04:31\" (first of 688 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2013_ORTHO_IMAGE13_AREA_2061_citypoly_first3.json)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " Fully leaf-on. Only year whose held grid (10.0 cm) ~= native (10.16 cm).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2015_king_rgb.tif", year_label="2015 (King)", source="Pictometry International via King County GIS (IMAGE_Ortho2015KCNAT); per-frame index ORTHO_IMAGE15_AREA_2499",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in west county)",
      date_shot="2015-02-15 to 2015-03-08 (6 days over the city: Feb 15 n=5, Feb 18 5, Feb 21 26, Feb 28 111, Mar 7 348, Mar 8 206)",
      date_precision="window of 22 days, 6 flight days", single_or_multi_date="MULTI (6 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE15_AREA_2499",
      verbatim_quote="\"ImageName\":\"WAKING041401NeighOrtho4281_150228\" ... \"ShotDate\":\"2015/02/28 14:51:01\" (first of 701 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2015_ORTHO_IMAGE15_AREA_2499_citypoly_first3.json)",
      notes=(KC_CACHE % "20" + " " + IDX_NOTE + " LEAF-OFF. This held file is the Pictometry KCNAT product and is PIXEL-DISTINCT from the City of Edmonds 2015 basemap (tile correlation r=0.04-0.56 at 5 sites vs 0.99 control) - the 2015 CONTEST belongs to the CoE service row, not here. "
             "Weather note: 2015-02-15 was flown (CLR, 10 sm all day) with a maximum solar elevation of only 29.3 deg - a 30-deg sun floor is falsified by a known flight day."),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2017_king_rgb.tif", year_label="2017 (King)", source="Pictometry International via King County GIS (IMAGE_Ortho2017KCNAT); per-frame index ORTHO_IMAGE17_AREA_2685",
      effective_cm="13.2", native_flight_cm="7.62 (3 in west county); index per-frame GSD median ~6.4 cm",
      date_shot="2017-05-04 to 2017-05-10 (5 days over the city: May 4 n=16, May 6 90, May 8 48, May 9 192, May 10 364)",
      date_precision="window of 7 days, 5 flight days", single_or_multi_date="MULTI (5 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE17_AREA_2685",
      verbatim_quote="\"ImageName\":\"WAKING043402NeighOrtho01390_170509\" ... \"ShotDate\":\"2017/05/09 17:20:09\" (first of 710 frames intersecting the city polygon - an independent re-query returned 695, all 15 missing on May 10, same days; raw response qc/imagery_date_evidence/raw_records/kc_2017_ORTHO_IMAGE17_AREA_2685_citypoly_first3.json)",
      notes=(KC_CACHE % "20" + " " + IDX_NOTE + " Resolves the May 18 discrepancy in MASTER: May 18 frames (n=215) fall inside the wider bbox -122.42,47.76,-122.32,47.87 but outside the city polygon. Countywide capture 'from mid-February through October of 2017' (gisandyou.org, King County GIS). "
             "Frame counts track flyable hours (May 4 fog until 09:53 + afternoon thunderstorm -> n=16; May 9/10 clear 08:53-16:53 -> n=192/364). This file is the SAME ORTHOMOSAIC as 2017_coe_rgb.tif (see that row)."),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2019_king_rgb.tif", year_label="2019 (King)", source="Pictometry/EagleView via King County GIS (IMAGE_Ortho2019KCNAT); per-frame index ORTHO_IMAGE19_AREA_2852",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in west county)",
      date_shot="2019-04-25 to 2019-05-08 (7 days over the city: Apr 25 n=92, Apr 30 387, May 1 20, May 4 160, May 6 185, May 7 332, May 8 58)",
      date_precision="window of 14 days, 7 flight days", single_or_multi_date="MULTI (7 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE19_AREA_2852",
      verbatim_quote="\"ImageName\":\"WAKING042402NeighOrtho5255_190425\" ... \"ShotDate\":\"2019/04/25\" (date-only field; first of 1234 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2019_ORTHO_IMAGE19_AREA_2852_citypoly_first3.json)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " 2019 index also carries CameraLat/CameraLon/Bearing/Alt/FocalLen per frame (photo-centre data).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2021_king_rgb.tif", year_label="2021 (King)", source="Pictometry/EagleView via King County GIS (IMAGE_Ortho2021KCNAT); per-frame index ORTHO_IMAGE21_AREA_2912",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in west county)",
      date_shot="2021-04-14 to 2021-04-17 (4 days over the city: Apr 14 n=135, Apr 15 248, Apr 16 259, Apr 17 20)",
      date_precision="window of 4 days", single_or_multi_date="MULTI (4 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE21_AREA_2912",
      verbatim_quote="\"ImageName\":\"WAKING022033NeighOrtho9795_210415\" ... \"ShotDate\":\"2021/04/15 14:54:55\" (first of 662 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2021_ORTHO_IMAGE21_AREA_2912_citypoly_first3.json)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " NARROWED vs earlier bbox query (Apr 12/14 - May 5): the May 5 frames are outside the city polygon.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 dict(file="2023_king_rgb.tif", year_label="2023 (King)", source="EagleView Technologies via King County GIS (IMAGE_Ortho2023KCNAT); per-frame index ORTHO_IMAGE23_AREA_3073",
      effective_cm="12.6-13.7", native_flight_cm="7.62 (3 in 'Neighborhood' tier incl. SW Snohomish); index per-frame GSD median 6.41 cm",
      date_shot="2023-04-19 to 2023-05-07 (7 days over the city: Apr 19 n=57, Apr 20 84, Apr 25 64, Apr 26 381, Apr 27 169, May 3 336, May 7 34)",
      date_precision="window of 19 days, 7 flight days", single_or_multi_date="MULTI (7 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE23_AREA_3073",
      verbatim_quote="\"ImageName\":\"WAKING022033NeighOrtho8996_230503\" ... \"ShotDate\":\"2023/05/03 18:48:58\" (first of 1125 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2023_ORTHO_IMAGE23_AREA_3073_citypoly_first3.json)",
      notes=KC_CACHE % "20" + " " + IDX_NOTE + " A 2025 index (ORTHO_IMAGE25_AREA_3074, 'Index to 2025 Pictometry nadir images', 3 in west / 6 in east) now exists on the same org and was NOT queried over Edmonds - a follow-up would date 2025 the same way.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED",
      alt_date_shot="2023-04-14 to 2023-06-28 (countywide)", alt_source_url=KC_SDC % "Ortho2023KCNAT",
      alt_verbatim_quote="captured by EagleView Technologies between April 14 and June 28, 2023"),
 # ---------------- Snohomish County (HXIP) ----------------
 dict(file="2016_snoh_rgbi.tif", year_label="2016", source="Hexagon Imagery Program (HXIP; 'Seattle' Urban Area Coverage tier of the WA Statewide Imagery Consortium) via Snohomish County Imagery/Aerial_2016 ImageServer (mosaic gdb HXIP_2016_SNOHOMISH.gdb)",
      effective_cm="35.4", native_flight_cm="30.48 (1 ft): county mosaic-catalog LowPS=1 and item pixelSizeX=1 for every primary tile over Edmonds (MEASURED); the consortium's 15 cm (6 in) 2016 product exists over Edmonds but the county serves a 1-ft delivery",
      date_shot="2016-08-12 morning (consortium sorties 09:05 / 09:30 PDT; a 09:50 sortie also lies within the city bbox) - CONDITIONAL on the county 1-ft product being the same flight as the dated 15 cm consortium product. The 2016-08-11 16:52 sortie is EXCLUDED for the held extent (shadows point WNW = morning sun)",
      date_precision="window of 2 days by the consortium labels (Aug 11-12); held pixels consistent with Aug 12 only", single_or_multi_date="consortium labels: MULTI (2 days, 3-4 sorties over the city); held file: shadow azimuth uniformly morning (283-295 deg over 24 windows, R=1.00) - consistent with a single morning, single date NOT proven",
      evidence_grade="INFERRED", source_url=WA16,
      verbatim_quote="\"THEMENAME\":\"hxip_m_4712213_se2_10_15\",\"SDATE\":\"08/12/2016 09:30\",\"SUNEL\":37,\"ACCURACY\":\"0.68m (ce 95%)\" (city-centroid point query) ... \"THEMENAME\":\"hxip_m_4712214_sw3_10_15\",\"SDATE\":\"08/12/2016 09:05\",\"SUNEL\":34 ... \"THEMENAME\":\"hxip_m_4712214_sw2_10_15\",\"SDATE\":\"08/11/2016 16:52\",\"SUNEL\":31 (city bbox, 11 footprints; raw responses qc/imagery_date_evidence/raw_records/wa_2016_6in_*.json)",
      notes=("*** SUPERSEDED 2026-08-23 by 2016_snoh_1ft_rgbi.tif (full study extent at the native 1-ft grid; this clipped 0.5-ft server upsample is kept for provenance) *** Held file = export of the county service (window means identical to exportImage) and pixel-DISTINCT from Aerial_2015 and Aerial_2017 (MEASURED). SDATE is LOCAL clock time: a 7034-footprint fit of published SUNEL vs pvlib gives RMSE 6.9 deg for UTC-7 vs 55.6 for UTC, and 09:05 read as UTC puts the sun 26 deg below the horizon. "
             "The county gdb is HXIP_2016_SNOHOMISH.gdb (the 'HXIP_2015' tokens in the lineage are a stale parent-folder / dataset-name carry-over, not 2015 imagery); the 2015-08-07 flight is excluded three ways (pixel comparison, afternoon vs morning shadows, lineage). "
             "6-in coverage reached Edmonds because it lies inside the Valtus/Hexagon 'Seattle' UAC polygon, not via a county buy-up. The Geocortex blurb 'acquired in August 2016 as part of a Washington Statewide Imagery consortium. Pixel size of the raster is 6 inch' sits on a layer titled '2017 Aerial Photos' and contradicts the county's 1-ft tiles - CONTESTED, month-level corroboration only. "
             "Both Aug 11 and Aug 12 2016 were flyable at all three ASOS stations (Aug 11 morning marine stratus at KPAE only). C-CAP 2016 Snohomish (InPort 53263) says its source imagery is 'NAIP ... summer 2016' but no WA NAIP 2016 exists - most plausibly this HXIP flight. Held file is a study-area CROP (lon -122.404..-122.316, lat 47.783..47.828)."),
      px_evidence="grid/true MEASURED; effective MEASURED; native MEASURED (service catalog)",
      alt_date_shot="2015-08-07 15:31 (HXIP 2015 1-ft flight = the NAIP 2015 delivery; EXCLUDED for this file)", alt_source_url=WA15,
      alt_verbatim_quote="\"THEMENAME\":\"hxip_m_4712213_se_10_30\",\"SDATE\":\"08/07/2015 15:31\",\"SUNEL\":46,\"ACCURACY\":\"0.72m (ce 95%)\" (city-centroid point query; raw response qc/imagery_date_evidence/raw_records/wa_2015_1ft_citycentroid.json)"),
 dict(file="2016_snoh_1ft_rgbi.tif", year_label="2016 (campaign S16, REPLACES 2016_snoh_rgbi.tif)", source="Hexagon Imagery Program (HXIP) via Snohomish County Imagery/Aerial_2016 ImageServer, exported 2026-08-23 by pipeline/acquire_imagery.py at the native 1-ft lattice (grid snapped to the service origin, RSP_NearestNeighbor: nearest == bilinear to 0 differing pixels in the pilot)",
      effective_cm="40.6 (median of 5 Method_Provenance sites on the native 1-ft grid; 1.33x oversampled) - on a common 30.48 cm grid the old and new files resolve alike (43.0 vs 43.2 cm, HF-energy ratio 1.01): same source pixels, no server resampling",
      native_flight_cm="30.48 (1 ft = the county's delivered tile size; served pixelSize 0.5 ft is an upsample)",
      date_shot="2016-08-12 morning (consortium sorties 09:05 / 09:30 PDT; 09:50 within the city bbox) - CONDITIONAL on the county 1-ft product being the same flight as the dated 15 cm consortium product; the 2016-08-11 16:52 sortie is EXCLUDED for the old extent by shadow azimuth",
      date_precision="window of 2 days by the consortium labels (Aug 11-12); pixels consistent with Aug 12", single_or_multi_date="consortium labels MULTI (2 days, 3-4 sorties); shadows uniformly morning over the old extent - the new full extent has not been re-measured for shadow direction",
      evidence_grade="INFERRED", source_url=WA16,
      verbatim_quote="\"THEMENAME\":\"hxip_m_4712213_se2_10_15\",\"SDATE\":\"08/12/2016 09:30\",\"SUNEL\":37,\"ACCURACY\":\"0.68m (ce 95%)\" (city-centroid point query) ... \"THEMENAME\":\"hxip_m_4712214_sw3_10_15\",\"SDATE\":\"08/12/2016 09:05\",\"SUNEL\":34 ... \"THEMENAME\":\"hxip_m_4712214_sw2_10_15\",\"SDATE\":\"08/11/2016 16:52\",\"SUNEL\":31 (city bbox, 11 footprints; raw responses qc/imagery_date_evidence/raw_records/wa_2016_6in_*.json)",
      notes=("MEASURED on arrival (D:/edmonds-pipeline/Imagery/SnoCo/_acq/S16/measure.json): 25,116 x 35,259 px, 4 bands uint8, EPSG:2285, 2,586,179,492 B; city-polygon coverage 100% (old file 66.7%), study-extent coverage 82.3% (the rest is Puget Sound); band 4 NIR (std 66, NDVI p90 0.73); no JPEG 8x8 block signature; blue-vs-green registration 0.075 px. "
             "Fetch: 234 chunks of 2048 px + 64 px overlap, 0 failures, 30 empty (water), 9.5 min at 5.8 MB/s; stitched BigTIFF spot-verified against 12 chunks; MANIFEST.sha256 on both planes. Decision REPLACE (wins: coverage; no losses). Date evidence is inherited from the superseded row (same flight, same service)."),
      px_evidence="grid/true/effective MEASURED (acquire_imagery verify 2026-08-23); native MEASURED (service catalog LowPS=1)",
      alt_date_shot="2015-08-07 15:31 (HXIP 2015 1-ft flight; EXCLUDED for this product)", alt_source_url=WA15,
      alt_verbatim_quote="\"THEMENAME\":\"hxip_m_4712213_se_10_30\",\"SDATE\":\"08/07/2015 15:31\",\"SUNEL\":46,\"ACCURACY\":\"0.72m (ce 95%)\" (city-centroid point query; raw response qc/imagery_date_evidence/raw_records/wa_2015_1ft_citycentroid.json)"),
 dict(file="2021_snoh_rgbi.tif", year_label="2021 (Snoh)", source="HXIP via Snohomish County Imagery/Aerial_2021 ImageServer (mosaic gdb HXIP_2021_SNOHOMISH.gdb - a Hexagon delivery, not EagleView)",
      effective_cm="20.6", native_flight_cm="15.24 (0.5 ft): mosaic-catalog LowPS=0.5, item pixelSizeX=0.5 (MEASURED)",
      date_shot="2021-06-25 to 2021-11-11", date_precision="window of 140 days (weather trims to 108 feasible days; 18 late days never reach 30 deg sun)", single_or_multi_date="unknown; held crop flown in the AFTERNOON (shadow azimuth 67-91 deg = sun at 247-256 deg, uniform over 24 windows) - a time-of-day constraint, not a date",
      evidence_grade="PUBLISHED", source_url=SCOPI,
      verbatim_quote="The 2021 aerial photos are 6 inch resolution and cover mainly the urban areas. The imagery was collected between June 25, 2021 and November 11, 2021.",
      notes=("*** SUPERSEDED 2026-08-23 by 2021_snoh_6in_rgbi.tif (full study extent on the native 0.5-ft lattice, nearest; this 53.4% clip was served bilinear on an unsnapped grid and is kept for provenance) *** "
             "CLOSED LEADS: no WA consortium flight-date layer exists for 2021 or later (all 68 WAGeoservices services + 225 items enumerated; series ends 2020); the mosaic-catalog schema has no date field at all; WA NAIP 2021 does not cover quad 47122 (eastern WA only), so no NAIP ride-along date. "
             "Remaining route: the Hexagon flight log via Snohomish County DoIT, or the consortium contact (Joanne Markert, WA OCIO). " + WX_NOTE % ("2021-06-25..11-11", "32 of 140 days eliminated; longest feasible blocks Jul 22-Aug 6, Jul 2-15, Aug 9-19")),
      px_evidence="grid/true MEASURED; effective MEASURED; native MEASURED (service catalog)"),
 # ---------------- City of Edmonds ----------------
 dict(file="2017_coe_rgb.tif", year_label="2017 (CoE)", source="City of Edmonds Basemap/2017_Aerial_Cached (source raster 2017_Aerial.tif, 0.25 ftUS EPSG:2285, JPEG); CONTENT = King County IMAGE_Ortho2017KCNAT (Pictometry International, 3-in 'Neighborhood' tier covering southwestern Snohomish County) - MEASURED identity",
      effective_cm="7.6 (indicative; per-site sd +/-0.41-1.17 px)", native_flight_cm="7.62 (0.25 ftUS source raster; service pixelSizeX 0.07620015240030481 m = 0.250000 ftUS exactly)",
      date_shot="2017-05-04 to 2017-05-10 (5 days over the city: May 4 n=16, May 6 90, May 8 48, May 9 192, May 10 364) - transferred from the King County per-frame index because the two files are the SAME ORTHOMOSAIC",
      date_precision="window of 7 days, 5 flight days", single_or_multi_date="MULTI (5 days)",
      evidence_grade="MEASURED", source_url=KC_IDX % "ORTHO_IMAGE17_AREA_2685",
      verbatim_quote="\"ImageName\":\"WAKING043402NeighOrtho01390_170509\" ... \"ShotDate\":\"2017/05/09 17:20:09\" (King County 2017 index, first of 710 frames intersecting the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2017_ORTHO_IMAGE17_AREA_2685_citypoly_first3.json). Dates transfer because the two files are the same orthomosaic - see notes.",
      notes=("Identity MEASURED 2026-08-23: held 2017_coe_rgb.tif (2x boxcar-downsampled) vs 2017_king_rgb.tif over a 12x12 grid on the city polygon, 66 valid 512-px windows -> r min 0.9568, p5 0.9786, median 0.9923, max 0.9966, MAE median 3.54 DN; live services 2017_Aerial_Cached vs KingCo_Aerial_2017 LOD-20 tiles at 5 sites r = 0.9876-0.9935. Identical vehicles in identical stalls and identical building relief displacement -> same orthorectification, not merely the same flight. Retires the 8.5-month candidate window and the council-minutes line (2023-07-25 p.15, 'PlanIt Geo ... 2017 flyovers') as evidence - the 2019 UFMP was written by Davey Resource Group and its canopy work used Aug 2015 imagery; PlanIt Geo appears nowhere in it. "
             "No City of Edmonds document naming the 2017 vendor was found; attribution rests on measured pixel identity plus King County's published coverage statement (alt). Snohomish County's own 2017 product is a 1-ft HXIP flight (2017-08-15/21) and cannot be a 3-in source. "
             "Grid note: the held grid is exactly LOD 21, which King's tile endpoint does not serve (404 at L21) but Edmonds' does - consistent with a city-service export. Method detail: " + EVID + "/coe2017_identity/."),
      px_evidence="grid/true MEASURED; effective MEASURED; native MEASURED (live service)",
      alt_date_shot="mid-February through October 2017 (countywide), with SW Snohomish at 3 in", alt_source_url="https://gisandyou.org/2018/05/25/2017-aerial-imagery-in-imap/",
      alt_verbatim_quote="The imagery was captured by Pictometry International Corp. from mid-February through October of 2017. The original photos have a resolution of 3 inches per pixel (\"Neighborhood\" scale in Pictometry terminology) over urbanized, western King County ... Also covered at the Neighborhood resolution level in the 2017 imagery are southwestern Snohomish County"),
 dict(file="2020_coe_rgb.tif", year_label="2020 (ANCHOR)", source="City of Edmonds Basemap/2020_Aerial_Cached (MrSID/MG4 mosaic, GeoExpress 10.0.1.5035, input GeoTIFF set 665,235,977,256 B); source = Snohomish County 2020 EagleView/Pictometry regional project WASNOH20_3in per the 2021 ILA; product identity corroborated by Everett's copy ('Aerial Photos 2020 Pictometry Mosiac 3 inch resolution urban areas', 0.25 ftUS)",
      effective_cm="7.0", native_flight_cm="7.62 (0.25 ftUS; county Aerial_2020 LowCellSize 0.25, dimResol 0.250000 ftUS; Everett Image2020jp2 pixelSizeX 0.25 in EPSG:2285)",
      date_shot="2020-04-13 to 2020-07-13 (county window; the single published window is the UNION of the 3-in urban and 9-in rural sub-projects - unlike 2022/2024 the county did not publish them separately). Shadow solar geometry excludes the head: 2020-04-25 to 07-13 survive (80 of 92 days)",
      date_precision="window of 80-92 days", single_or_multi_date="CONSISTENT WITH ONE CONTINUOUS PASS, single date NOT PROVEN: 10 QC-passing sites of 34 on a ~850 m city-wide grid give sun azimuths 120.8-192.5 deg = local times ~10:22-13:39 PDT straddling solar noon, increasing monotonically east-to-west (az vs lon r=-0.75, p=0.013; permutation p=0.026) - the signature of successive flight lines in one pass, not of day-blocks. Not excluded: several dates each flown at the same time of day.",
      evidence_grade="INFERRED", source_url=SCOPI,
      verbatim_quote="The 2020 aerial photos are 3 inch resolution in the urban areas and 9 inch resolution in the rural areas, excluding much of the unpopulated mountainous portion of eastern Snohomish County, and were taken between April 13th and July 13th, 2020.",
      notes=(SNOH_CHAIN + " City keyProperties (correct endpoint <ImageServer>/keyProperties?f=json; /info/keyProperties 400s on this server, positive control Edmonds_Marsh_2018 returns acquisitionStartDate 2018-08-01T16:22:13+00:00 / End 16:52:13) carry NO date: IMAGE__MODIFICATIONS 'COMPRESSED EMBEDDED MASKED MOSAICKED' - a validated null. "
             "Everett's 2020 copy is JPEG2000 and also carries no date; no 2020 MrSID twin with a surviving date was found. A per-frame index CANNOT exist on the county service (mosaic catalog = two whole-project items WASNOH20_3in / WASNOH20_9in). "
             "HAZARD: a SECOND 2020 acquisition covers Edmonds - the WA consortium 6-in Hexagon/ADS100 flight of 2020-08-27/28 (program window 2020-08-03..09-06) - DO NOT borrow its date (see context row). "
             "Shadow dating (" + EVID + "/shadow_dating_2020/): azimuth is reliable (2012 control 8/10 in-window), elevation reads LOW and saturates above ~45 deg, so 2020 elevations are lower bounds - hence no calendar date. 2020 ortho co-registered to 2012 within <=1.5 WM m. "
             + WX_NOTE % ("2020-04-13..07-13", "22 of 92 days eliminated; longest feasible blocks May 7-15 (9 d), Apr 13-17, May 26-30, Jun 1-5, Jun 22-26")),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (county + Everett services)",
      alt_date_shot="(ILA text, for the chain)", alt_source_url=ILA,
      alt_verbatim_quote="Upon completion of the 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects and receipt of imagery by County, County will provide Edmonds with orthogonal imagery for Edmonds's identified area of interest"),
 dict(file="2022_coe_rgb.tif", year_label="2022 (CoE)", source="City of Edmonds Basemap/2022_Aerial_Cached; = Snohomish County 2022 regional project WASNOH22_3in. IDENTITY MEASURED: the Edmonds and Everett 2022 MrSIDs are the same county encode (identical input-set byte count 675,609,635,568 B, GeoExpress 10.0.1.5035, EPSG:2285 ftUS geokeys)",
      effective_cm="6.5", native_flight_cm="7.62 (0.25 ftUS; county Aerial_2022 LowCellSize 0.25; MrSID input GeoTIFF geokeys 'Linear_Foot_US_Survey' / 2285)",
      date_shot="2022-04-06 to 2022-07-11 (urban 3 in); the rural 9-in sub-project ran 2022-05-31 to 08-11 and does not apply to Edmonds", date_precision="window of 96 days", single_or_multi_date="unknown",
      evidence_grade="PUBLISHED", source_url=SCOPI,
      verbatim_quote="The 2022 3 inch resolution aerial photos in the urban areas, were captured between April 6, 2022 and July, 11 2022. The 2022 9 inch resolution aerial photos in the rural areas, were captured between May, 31 2022 and August, 11 2022.",
      notes=("Upgraded INFERRED -> PUBLISHED 2026-08-23: the window is published for a product whose identity with the held file is now measured (byte-count identity of the input set with Everett's Image2022_3in_sid, 'Aerial Photos 2022 Pictometry Mosaic 3 inch resolution urban areas'), not only contractual. Same definitive pin as 2020 (one PRR covers 2020/2022/2024). "
             + WX_NOTE % ("2022-04-06..07-11", "19 of 97 days eliminated (weakest of the four windows - a settled spring); longest feasible block May 16-28 (13 d)")),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (county + Everett services)",
      alt_date_shot="(Everett keyProperties - identity proof)", alt_source_url=EV2022,
      alt_verbatim_quote="\"IMAGE__ENCODING_APPLICATION\":\"GeoExpress 10.0.1.5035\",\"IMAGE__FORMAT\":\"MrSID/MG4\",\"IMAGE__INPUT_FILE_SIZE\":\"675609635568.000000\",\"IMAGE__INPUT_FORMAT\":\"GeoTIFF\" ... \"IMAGE__MODIFICATIONS\":\"COMPRESSED EMBEDDED MASKED MOSAICKED\""),
 dict(file="2024_coe_rgb.tif", year_label="2024 (CoE)", source="City of Edmonds Basemap/2024_Aerial_Cached (MapServer over Edmonds2024.sid - no ImageServer, so no keyProperties resource exists); source = Snohomish County 2024 regional project WASNOH24_3in per the 2021 ILA",
      effective_cm="6.8", native_flight_cm="7.62 (0.25 ftUS; county Aerial_2024 LowCellSize 0.25)",
      date_shot="2024-03-31 to 2024-05-31 (urban 3 in); the rural 9-in sub-project ran 2024-03-16 to 06-09", date_precision="window of 62 days", single_or_multi_date="unknown",
      evidence_grade="INFERRED", source_url=SCOPI,
      verbatim_quote="The 2024 3 inch resolution aerial photos in the urban areas, were captured between March 31, 2024 and May, 31 2024. The 2024 9 inch resolution aerial photos in the rural areas, were captured between March, 16 2024 and June, 9 2024.",
      notes=("Stays INFERRED: no neighbour city holds a 2024 county copy (Everett stops at 2022, Mukilteo at 2019, Lynnwood publishes none), so there is no 2024 analogue of the 2022 byte-identity proof. Same definitive pin as 2020. "
             + WX_NOTE % ("2024-03-31..05-31", "18 of 62 days eliminated (29%, strongest of the four); longest feasible block Apr 16-24 (9 d)")),
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED (county service)",
      alt_date_shot="(ILA text)", alt_source_url=ILA, alt_verbatim_quote="Upon completion of the 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects ..."),
 dict(file="(not held) City of Edmonds Basemap/2015_Aerial_Cached", year_label="2015 (CoE service)", source="City of Edmonds (source raster Ed_Aerial_2015.tif, 0.25 ftUS EPSG:2285, LZW); content INFERRED = 2015 Western Washington Regional Orthophotography (King County lead, 88 participants; prime GeoTerra, Edmonds frames flown by Valley Air and GeoTerra)",
      grid_px="LOD 21 cache (0.0746 WM m)", grid_units="metre (Web Mercator)", crs="EPSG:3857 (cache); source EPSG:2285", true_ground_cm="5.01 (cache) / 7.62 (source)",
      effective_cm="not measured", native_flight_cm="<= 6.86 flown (MAX_GSD 0.225 ft 'as planned' for all 346 Edmonds frames; two cameras at two altitudes both back-compute to ~6.6-6.9 cm), delivered at the 0.25 ft = 7.62 cm tier (service pixelSizeX 0.07620015240030481 m = 0.250000 ftUS)",
      date_shot="2015-04-08 (n=135 photo centres in the city polygon; Valley Air, UltraCam X, 14:13-15:04 PDT) and 2015-04-17 (n=32; GeoTerra, UltraCam Xp, 12:54-13:55 PDT). CONTEST largely resolved: the King Pictometry leg is EXCLUDED by pixel comparison, the 'Aug 7 2015' leg is a DIFFERENT dataset (NAIP/HXIP 2015-08-07), leaving the consortium dates; attribution of Ed_Aerial_2015.tif to the consortium remains INFERRED and the UFMP's '4.8 in' figure is unexplained",
      date_precision="2 flight days (window of 10 days) for the consortium product", single_or_multi_date="MULTI - two days, two vendors, two cameras within the city (flightlines 16002-16011 Zone 16 / 13007-13015 Zone 13)",
      evidence_grade="INFERRED", source_url="https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/ORTHO_IMAGE15C_POINT_2574/FeatureServer/0/query",
      verbatim_quote="\"FILENAME\":\"13009_57445\" ... \"UTC_TIME\":\"19:54:49\",\"MAX_GSD__f\":0.225 ... \"VENDOR\":\"GeoTerra\",\"CAMERA\":\"UltraCam Xp\" ... \"FLIGHTLINE\":\"13009\",\"ACQ_DATE\":1429228800000 (= 2015-04-17 UTC; first of the photo centres inside the city polygon; raw response qc/imagery_date_evidence/raw_records/kc_2015C_ORTHO_IMAGE15C_POINT_2574_citypoly_first3.json). Layer description: It is a reference for the raw image scans, it is not a index for tiled ortho imagery",
      notes=("Photo-centre DAYS are MEASURED; binding them to Ed_Aerial_2015.tif is INFERRED via (a) 0.25 ftUS cell size matching the consortium tier, (b) CRS NAD83 SP WA North ftUS, (c) Edmonds named in GeoTerra's participant table and the consortium agreement signed 2015-06-23 ($3,696.21), (d) leaf-off/high-sun spec matching the tiles. NOTE: no Apr 9 frames exist over Edmonds (the catalogue's 'Apr 8/9/17' was wrong); one Mar 26 frame sits just outside the polygon. "
             "King leg excluded: CoE 2015 vs KingCo_Aerial_2015 LOD-20 tiles r=0.036-0.557 at 5 sites vs r=0.988-0.994 for the CoE-2017/King-2017 control. 'Aug 7 2015 / 4.8 in' (UFMP 2019 p.26) traces to the Davey Resource Group 2018 UTC Assessment which names 'USDA, Farm Service Agency' = NAIP 2015 (2015-08-07, 1 m = the same Hexagon flight as the HXIP 1-ft consortium product); '4.8 in' matches no known 2015 product. "
             "Phenology caveat from the project's own survey report: 'the need to begin immediate image acquisition due an earlier than normal bud break' - Apr 8/17 is late in a leaf-off window. Vendor/camera cross-validated at serial-number level against the Flight Subcontractor PDF (UCX 60418665 / UCXp 10411033)."),
      px_evidence="grid MEASURED (live service); native MEASURED (index MAX_GSD) + PUBLISHED (tier)", row_type="context (not held)",
      alt_date_shot="2015-08-07 15:31 (UFMP/Davey 'August 7th, 2015' imagery = NAIP/HXIP 2015, NOT the city basemap)", alt_source_url="https://naipeuwest.blob.core.windows.net/naip/v002/wa/2015/wa_fgdc_2015/47122/m_4712214_sw_10_1_20150807.txt",
      alt_verbatim_quote="Time_Period_of_Content: Time_Period_Information: Single_Date/Time: Calendar_Date: 20150807 Currentness_Reference: Ground Condition"),
 # ---------------- NAIP ----------------
 dict(file="2019_naip_rgbi.tif", year_label="2019n", source="USDA FSA NAIP WA 2019 (DOQQ m_4712213/m_4712214; the WA consortium 2019 1-ft flight carries the same date, i.e. the Hexagon flight)",
      effective_cm="95.1", native_flight_cm="60 (collected and delivered at 60 cm)",
      date_shot="2019-10-11", date_precision="single day", single_or_multi_date="single (all Edmonds DOQQs carry 20191011; consortium flight-area IDATE '2019 -10-11' at the city centroid)",
      evidence_grade="PUBLISHED", source_url=NAIP19,
      verbatim_quote="Time_Period_of_Content: Time_Period_Information: Single_Date/Time: Calendar_Date: 20191011 Currentness_Reference: Ground Condition",
      notes="OCTOBER. No NAIP metadata record (2015/2017/2021 Digital Coast) contains any leaf-on/leaf-off statement - only 'peak crop growing conditions'; the 'NAIP is leaf-on by spec' assumption has no documentary basis.",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED",
      alt_date_shot="2019-10-11", alt_source_url="https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/2019_Statewide_imagery_consortium_1_foot_flight_areas/FeatureServer/0/query",
      alt_verbatim_quote="\"IDATE\":\"2019 -10-11\" (stray space verbatim; city-centroid point query, raw response qc/imagery_date_evidence/raw_records/wa_2019_1ft_citycentroid.json)"),
 dict(file="2023_naip_rgbi.tif", year_label="2023n (was mislabelled 2022n)", source="USDA FSA NAIP WA 2023 (DOQQ m_4712213/m_4712214)",
      effective_cm="83.1", native_flight_cm="60 delivered (2021/2023-era WA NAIP collected finer and rectified to 60 cm)",
      date_shot="2023-10-07", date_precision="single day", single_or_multi_date="single (all 8 Edmonds QQs: m_47122{13,14}_*_10_060_20231007_20240209)",
      evidence_grade="PUBLISHED", source_url=NAIP23,
      verbatim_quote="<gco:CharacterString>m_4712214_sw_10_060_20231007.tif</gco:CharacterString> (the DOQQ file name in the ISO metadata record; 20231007 = acquisition date field)",
      notes="*** SUPERSEDED 2026-08-23 by 2023_naip_60cm_rgbi.tif (the 8 original Azure DOQQs mosaicked, full study extent; this 69% smoothed re-export is kept for provenance) *** OCTOBER. Held bands 1-3 byte-identical to rgb_2023, band 4 to ir_2023 (DataLake_Issues). Context: NAIP 2021 over Edmonds exists (all 8 QQs STAC datetime 2021-07-13, INFERRED from file names - the FGDC sidecars for quad 47122 are absent from the Azure mirror).",
      px_evidence="grid/true MEASURED; effective MEASURED; native PUBLISHED"),
 # ---------------- reference rasters / lidar (flagged, not imagery acquisitions) ----------------
 dict(file="lidar_snoh_chm.tif", year_label="2016 (lidar)", source="USGS 3DEP HAG via Planetary Computer, reprojected by the project; underlying lidar = USGS_LPC_WA_Western_North_2016 (QSI for USGS/WADNR)",
      effective_cm="n/a (bilinear-upsampled ~2 m product)", native_flight_cm="~200 (HAG raster); lidar 0.7 m spacing",
      date_shot="2016-03-17 to 2016-09-30 (Western Washington 3DEP NORTH AOI; all 46 tiles over the city are North-block)", date_precision="window of 198 days", single_or_multi_date="multi",
      evidence_grade="PUBLISHED", source_url="https://www.fisheries.noaa.gov/inport/item/51853",
      verbatim_quote="North: March 17 - Sept 30, 2016 ... South: March 17, 2016 - June 6, 2017",
      notes="UNITS TRAP #4: grid is 1.0 m in EPSG:3857 = 67.2 cm true ground at 47.81N, not 1 m. Narrowed from 15 months (whole project) to the North window by point-in-polygon on NOAA's tile index (46/46 tiles /north/). Reference raster, excluded from the imagery count.",
      px_evidence="grid/true MEASURED; native PUBLISHED", row_type="reference raster",
      alt_date_shot="2016-03-30 (INFERRED from the tile filename prefix 20160330_USGS_LPC_WA_Western_North_2016_q47122G4405 - a FILE NAME; 3/30/16 is a flight day for all three contractors in QSI report Table 3)", alt_source_url="https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/laz/geoid18/6331/tileindex_wa2016_west_wa_m6331.gpkg",
      alt_verbatim_quote="20160330_USGS_LPC_WA_Western_North_2016_q47122G4405_LAS_2018.copc.laz"),
 dict(file="PSLC_2005/ (47 laz tiles)", year_label="2005 (lidar)", source="Puget Sound LiDAR Consortium 2005 North Puget Sound Lowlands (Terrapoint), InPort 50149",
      grid_px="point cloud (no grid)", grid_units="-", crs="NAD83(HARN) UTM 10N, NAVD88 GEOID18", true_ground_cm="n/a (point cloud)",
      effective_cm="n/a", native_flight_cm="n/a (2 m nominal spacing)",
      date_shot="2005-02-27 (Edmonds sub-project, 11 sq mi)", date_precision="single day", single_or_multi_date="single (sub-project row)",
      evidence_grade="PUBLISHED", source_url="https://www.fisheries.noaa.gov/inport/item/50149",
      verbatim_quote="project, area (sq mi), date(s) collected, vert. acc (cm), horiz acc. (cm), RMSE (m) - ... - Edmonds, 11, 2/27/2005, 25, 60, 0.100 - Mt. Lake Terrace, 4, 7/15/2005-9/15/2005, 25, 60, 0.100 - Mukilteo, 16, 2/27/2005, 25, 60, 0.100",
      notes="Density 0.25 pts/m2 stated (~0.17 cross-checked, IMAGERY_FACTS 8.1). LEAF-OFF (late February). Record-internal inconsistency: Mt. Lake Terrace sub-project dates run past the record's own Time Frame end (2005-07-15). Held at D:/edmonds-pipeline/Imagery/PSLC_2005 and Full_Image/PSLC_2005 (IMAGERY_FACTS 8.2).",
      px_evidence="density PUBLISHED", row_type="reference lidar"),
 dict(file="ccap_2016_hires_lc_snohfull.tif", year_label="2016 (C-CAP ref)", source="NOAA OCM C-CAP hi-res land cover, Snohomish County 2016 (InPort 53263 - record RECOVERED as an InPort XML export on coast.noaa.gov; fisheries.noaa.gov still 403)",
      effective_cm="n/a (thematic)", native_flight_cm="100 (1 m product)",
      date_shot="summer 2016 (source imagery, stated as NAIP) - CONTESTED: no WA NAIP 2016 exists (Azure NAIP v002/wa/ holds 2011, 2013, 2015, 2017, 2019, 2021, 2023 only)", date_precision="season", single_or_multi_date="n/a",
      evidence_grade="PUBLISHED", source_url="https://chs.coast.noaa.gov/htdata/raster1/landcover/bulkdownload/hires/wa/WA_Snohomish_2016_lc.xml",
      verbatim_quote="The timeframe for this metadata is summer 2016. These maps are developed utilizing high resolution National Agriculture Imagery Program (NAIP) imagery, and can be used to track changes in the landscape through time.",
      notes="Candidate reconciliation (INFERENCE): the 'summer 2016' imagery is the HXIP Aug 11-12 2016 flight (the WA consortium product is itself branded 'NAIP_2016' on AGOL), or NOAA used NAIP 2015 (2015-08-07) and labelled the product 2016 - UNRESOLVED. Traps in the record: <start-date-time>2016-01-01 is a year placeholder; <publish-date>2019-03-14 is publication. Ancillary: NGS MLLW orthoimagery 2014 for shore classes. Reference raster.",
      px_evidence="grid/true MEASURED; native PUBLISHED", row_type="reference raster"),
 dict(file="ccap_2021_hires_lc.tif", year_label="2021 (C-CAP v2 ref)", source="NOAA OCM C-CAP hi-res v2 'Refined' Puget Sound 2021 (InPort 79723; Ecopia extraction, NV5 refinement)",
      effective_cm="n/a (thematic)", native_flight_cm="100 (1 m extraction from '30cm or better' imagery)",
      date_shot="2021 (year only; 'Acquisition date of the Aerial Imagery')", date_precision="year only", single_or_multi_date="multi (mosaic of vendor imagery)",
      evidence_grade="PUBLISHED", source_url="https://ocmgeodatastor1.blob.core.windows.net/ccap/bulk_download/C-CAP_High-Resolution_Data/Refined_C-CAP_High-Resolution_Land_Cover_Classification/CONUS/wa_puget_2021_ccap_v2_hires_landcover.xml",
      verbatim_quote="<currentness-reference>Acquisition date of the Aerial Imagery</currentness-reference> ... <time-frame-type>Discrete</time-frame-type> <start-date-time>2021</start-date-time> ... Initial 1m spatial resolution feature extraction for Impervious, Water, and Canopy (tree and scrub/shrub) mapping was conducted by Ecopia AI",
      notes=("The record was created 2026-04-28 and may post-date the held clip (2026-07-06); best-available lineage, not proven identical. Record defects: Ohio/Houston copy-paste text, 'Never Published', 'best-available-metadata: No'. "
             "LICENSING (verbatim, for the Licensing_Risk sheet): 'Users are granted a perpetual, non-exclusive, irrevocable, worldwide license to use these data ... with the exception of creating, training, improving, modifying, validating, testing, evaluating, or otherwise leveraging machine learning algorithms in order to explicitly create similar land cover data for a period of five years from its date of creation.' The Phase-1 canopy record (InPort 70562, created 2023-09-30) carries the broader unqualified form ('may not be used for the purpose of ... testing, or evaluating machine learning algorithms ... except with the express written consent of Ecopia Tech Corporation'). This project uses the product as an EVALUATION reference - flag for Kam."),
      px_evidence="grid/true MEASURED; native PUBLISHED", row_type="reference raster"),
 # ---------------- context rows: other acquisitions over Edmonds that are NOT held (recorded to prevent conflation) ----------------
 dict(file="(not held) WA Statewide Imagery Consortium 2020 6-inch (Hexagon, Leica ADS100)", year_label="2020 (SECOND 2020 acquisition - NOT the anchor)", source="WA OCIO/WaTech Statewide Imagery Consortium, flown by Hexagon under the 2020 NAIP Imaging Program",
      grid_px="n/a", grid_units="-", crs="-", true_ground_cm="15 (6 in product), nominal flight GSD 20", effective_cm="n/a", native_flight_cm="20 (nominal)",
      date_shot="2020-08-28 (flight-area polygon at the city centroid; 2020-08-27 also intersects the city bbox); program window 2020-08-03 to 2020-09-06", date_precision="day (coarse flight-area block, 911-1263 sq mi)", single_or_multi_date="multi (2 blocks over the city)",
      evidence_grade="PUBLISHED", source_url="https://www.arcgis.com/sharing/rest/content/items/dd83978971d8421eb6b1a7273ba51f6e?f=json",
      verbatim_quote="Digital aerial imagery for Washington state was collected by Hexagon as part of the 2020 NAIP Imaging Program. Imagery was collected between August 3, 2020 and September 6, 2020 using Leica ADS100 digital camera systems. The project was flown at heights ranging from 8,000 ft msl to 15,500 ft msl resulting in a nominal GSD of 20cm.",
      notes="HAZARD ROW: a different vendor, camera, resolution and season from 2020_coe_rgb.tif (EagleView 3 in, Apr-Jul). Year-matched substitution would introduce a ~4.5-month error - exactly the 2015 three-way pattern. Not held; a late-August leaf-on 15 cm 4-band product if ever wanted.",
      px_evidence="PUBLISHED", row_type="context (not held)",
      alt_date_shot="2020-08-28 / 2020-08-27", alt_source_url="https://services.arcgis.com/jsIt88o09Q0r1j8h/ArcGIS/rest/services/2020_Statewide_imagery_consortium_6_inch_flight_areas/FeatureServer/0/query",
      alt_verbatim_quote="\"IDATE\":\"2020-08-28\" (city centroid) ... \"IDATE\":\"2020-08-27\" (also intersects the city bbox; raw responses qc/imagery_date_evidence/raw_records/wa_2020_6in_*.json)"),
 dict(file="(not held) WA Statewide Imagery Consortium 2018 6-inch; Edmonds_Marsh_2018 drone", year_label="2018 (two distinct acquisitions)", source="WA consortium (Hexagon) / City of Edmonds Imagery/Edmonds_Marsh_2018 ImageServer",
      grid_px="n/a", grid_units="-", crs="-", true_ground_cm="15 (consortium) / 2.5 (Marsh cache LOD)", effective_cm="n/a", native_flight_cm="n/a / 3.36 (Marsh pixelSizeX 0.0336 m)",
      date_shot="2018-08-07 (consortium flight area over Edmonds) ; 2018-08-01 16:22-16:52 UTC (Marsh drone sortie) - six days apart, NOT the same acquisition", date_precision="day / exact timestamp", single_or_multi_date="-",
      evidence_grade="PUBLISHED", source_url="https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/2018FlightAreas/FeatureServer/0/query",
      verbatim_quote="\"IDATE\":\"2018-08-07\" (city-centroid point query; raw response qc/imagery_date_evidence/raw_records/wa_2018_6in_citycentroid.json)",
      notes="Recorded to prevent conflation. The Marsh service is the project's only Edmonds layer with a machine-readable timestamp and the positive control for keyProperties queries (correct path: /gis/rest/services/.../ImageServer/keyProperties?f=json).",
      px_evidence="PUBLISHED", row_type="context (not held)",
      alt_date_shot="2018-08-01T16:22:13+00:00 to 16:52:13 (Marsh)", alt_source_url=COE % "Edmonds_Marsh_2018/ImageServer/keyProperties?f=json",
      alt_verbatim_quote="\"acquisitionEndDate\":\"2018-08-01T16:52:13+00:00\",\"acquisitionStartDate\":\"2018-08-01T16:22:13+00:00\""),
]
try:
    from imagery_pixelsize_date_campaign import build_campaign_rows
    ROWS += build_campaign_rows({r["file"] for r in ROWS})
except Exception as _e:                      # the campaign module is optional at build time
    print(f"campaign rows skipped: {_e}")


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
