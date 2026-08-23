# Agent angle: CoE 2015 service + 2017_coe_rgb.tif  (session 2026-08-23)

## F1 — 2015 "Aug 7 / 4.8 in" contestant is NAIP (USDA FSA), NOT the city basemap. CONTEST DISSOLVED.
PRIMARY: City of Edmonds Urban Tree Canopy Assessment (Davey Resource Group), p.8 exec summary.
URL fetched: https://cdnsm5-hosted.civiclive.com/UserFiles/Servers/Server_16494932/File/Government/Departments/Development%20Services/Planning%20Division/Urban%20Forest%20Mgmt%20Plan/Edmonds-UTC-Assessment---FINAL-no-watermark-20180308.pdf
QUOTE: "Using high-resolution aerial imagery from August 7th, 2015 (USDA, Farm Service Agency) and GIS analysis, Davey Resource Group (DRG) determined the following land cover characteristics within the City of Edmonds"
- Same doc separates the two datasets explicitly: "Points are first assessed on the NAIP imagery ... scrutinised further using sub-meter imagery provided by the client"
- UFMP 2019 (prepared by DAVEY RESOURCE GROUP, not PlanIt Geo) restates it as "high resolution (4.8 inch), leaf-on aerial imagery captured on August 7th, 2015" — the 4.8-inch attribute appears NOWHERE in the primary UTC report.
- NAIP WA 2015 verified: Azure container path is wa_100cm_2015 (=1 m = 39.4 in). FGDC for m_4712214_sw_10_1_20150807: "Calendar_Date: 20150807", "Source_Currentness_Reference: Aerial Photography Date for aerial photo source."
=> the "4.8 inch" figure is UNSOURCED and contradicts the product it names.

## F2 — CoE 2015 basemap is NOT the King County Pictometry product. MEASURED.
Live LOD-20 tile comparison, 5 sites, Edmonds 2015_Aerial_Cached vs KingCo_Aerial_2015:
r = 0.557 / 0.398 / 0.036 / 0.494 / 0.116 ; MAE 22.3-43.7 DN.  Visibly different acquisitions.
COVERAGE CAVEAT: 5 sites only, NOT the 66-window treatment F6 gave the 2017 pair (no held CoE 2015 file exists).
Defensible because the claim is NON-identity and r=0.04-0.56 is nowhere near borderline - but do not read it
as equally sampled.
Control in the same run: CoE 2017 vs King 2017 r = 0.988-0.994, MAE 2.6-4.9.

## F3 — CoE 2017 basemap IS King County's 2017 ortho. MEASURED (two independent ways).
(a) held files: 2017_coe_rgb.tif (LOD21) 2x-boxcar-downsampled vs 2017_king_rgb.tif (LOD20):
    r 0.961-0.995, MAE 2.8-6.7 DN over 8 sites. Control CoE2017 vs CoE2020: r 0.25-0.69, MAE 23-39.
(b) LIVE services (independent of the data lake): r 0.988-0.994, MAE 2.6-4.9 DN over 5 sites.
Visual: identical vehicle in identical stall, identical building relief displacement.
=> King County's MEASURED per-frame dates over the Edmonds polygon (2017-05-04..05-10) apply.

## F4 — The Edmonds REST path is /gis/rest/services, NOT /arcgis/rest/services.
/arcgis/... returns HTTP 500 for EVERY service incl. the Marsh 2018 positive control.
Found via https://maps.edmondswa.gov/Geocortex/Essentials/REST/sites/Edmonds_SSL/map?f=json
2017 service: pixelSizeX 0.07620015240030481 m = exactly 0.25 ftUS; cache LOD 21; JPEG q75.
Source rasters (info/metadata XML): 2017_Aerial.tif (JPEG, 0.25 ft, NAD83 SP WA N ftUS, 120000x150000)
                                    Ed_Aerial_2015.tif (LZW, 0.25 ft, same CRS, 96000x144000)
NO vendor string, NO flight date, no TIFFTAG_SOFTWARE/DATETIME in either. CreaDate 20190130 / 20170123 = ArcGIS metadata stamps, NOT flight dates.

## F5 — GeoTerra 2015 photo centres over the CITY POLYGON: two days only, not three.
https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/ORTHO_IMAGE15C_POINT_2574/FeatureServer/0/query
2015-04-08 VENDOR=VALLEY  CAMERA=UltraCam Xp/X n=135 UTC 21:13:38-22:03:56 (14:13-15:04 PDT)
2015-04-17 VENDOR=GeoTerra CAMERA=UltraCam Xp   n=32  UTC 19:54:49-20:55:23 (12:55-13:55 PDT)
all MAX_GSD__f = 0.225, USED=YES, no reflights. (bbox query also returns Mar 26 / Apr 9 / Apr 18 — those frames fall OUTSIDE the city polygon.)

## F5 CORRECTED (photo-centre vs footprint convention)
ORTHO_IMAGE15C_POINT_2574 is a PHOTO-CENTRE layer, not a footprint layer. Centres in-polygon under-count
days whose frames overlap the city from outside. Queried three ways (all 2026-08-23, all MAX_GSD__f=0.225 ft):
  centres INSIDE city polygon (N=167): 2015-04-08 VALLEY/UltraCam X n=135 (UTC 21:13:38-22:03:56);
                                       2015-04-17 GeoTerra/UltraCam Xp n=32 (UTC 19:54:49-20:55:23)
  centres WITHIN 1 km    (N=833): adds 2015-03-26 GeoTerra n=74; 2015-04-09 GeoTerra n=36 + VALLEY n=20;
                                       2015-04-18 GeoTerra n=20
  centres WITHIN 2 km    (N=1000, transfer limit hit): adds UltraCam Hawk / Valley Air Photos at 0.45 ft
=> candidate flight days over/near Edmonds: 2015-03-26, 04-08, 04-09, 04-17, 04-18. Which frame feeds which
   mosaic pixel is NOT recorded (same caveat as every King row).

## F6 — F3 upgraded from sampling to COVERAGE.
12x12 grid over the city polygon, 512x512 King px (76 WM m) windows, 2x-boxcar CoE->King grid, 66 valid windows:
  r  min 0.9568  p5 0.9786  median 0.9923  max 0.9966 ; MAE min 1.10 median 3.54 max 6.35
  windows with r<0.95: 0 ; r<0.90: 0
No patched-in region anywhere in the city. Identity holds citywide, not at 8 sampled points.

## F7 — the held file could NOT have come from King's cache. MEASURED.
KingCo_Aerial_2015 and KingCo_Aerial_2017 declare tileInfo LODs 0-23 but their /tile/21/... endpoint
returns HTTP 404 at Westgate (-122.3670,47.8095), well inside the city; L20 returns 12713 B / 12000 B.
City of Edmonds 2017_Aerial_Cached declares LODs 0-21 and SERVES L21 (5611 B).
Held 2017_coe_rgb.tif grid = 0.074646 m = exactly LOD 21, which King's /tile/ endpoint does NOT serve and
Edmonds' DOES. This EXCLUDES a King tile-cache export; it is CONSISTENT WITH a city-service export but does
not exclude every other route to an L21 grid (e.g. an exportImage harvest resampled to L21). F6 makes
provenance immaterial to date and pixel size either way.
NOTE: this CONTRADICTS the catalogue Retractions line "the cache reaches LOD 21 ~ 5.0 cm ground" for King.
That retraction was based on an exportImage test, not the /tile/ endpoint - needs reconciliation, not assumed wrong.

## F8 — King County PUBLISHED corroboration for 2017 coverage of Edmonds.
https://gisandyou.org/2018/05/25/2017-aerial-imagery-in-imap/  (fetched 2026-08-23, curl, HTTP 200)
"The imagery was captured by Pictometry International Corp. from mid-February through October of 2017."
"The original photos have a resolution of 3 inches per pixel ("Neighborhood" scale in Pictometry terminology)
 over urbanized, western King County, and 9 inches per pixel ("Community" scale) over rural, eastern King County."
"Also covered at the Neighborhood resolution level in the 2017 imagery are southwestern Snohomish County,
 the U.S. Highway 2 corridor in northeastern King County, and the Alpental area near Snoqualmie Pass."

## F9 — all four CoE aerial services share one native GSD.
pixelSizeX = 0.07620015240030481 m = exactly 0.25 ftUS for 2015/2017/2020/2022; cache LODs 0-21;
CRS NAD_1983_StatePlane_Washington_North_FIPS_4601_Feet; internal host gis1.edmondswa.gov:6443.
2015/2017 = 3 band; 2020/2022 = 4 band.
This EXCLUDES both HXIP candidates for the 2015 service on GSD alone (HXIP 2015 = 1 ft, HXIP 2016 = 1 ft).

## NOT RESOLVED
- Shadow-length ratio coe2015 vs king2015: attempted twice. (a) FFT cross-correlation of bright-roof vs
  dark-shadow masks hit the +/-120 px search boundary on 4 of 9 runs -> failed its own check, DISCARDED.
  (b) manual zoom crops (downtown building, hospital-area residential at LOD20 w/ 10 m grid) had no isolated
  vertical object with a clean shadow on flat open ground. NOT eyeballed into a number. Prediction stands
  untested: ratio 0.5-0.8 => April; ~1.0 => falsifies GeoTerra.
- No Edmonds document naming the 2017 imagery vendor/flight was found: Laserfiche now behind a Sign In wall.
