# Imagery acquisition — the four asks only Kam can send (drafted 2026-08-23)

Each block is ready to paste. Fill the `[affiliation]` placeholder. Record the send date in CHATLOG when sent.
Why these matter: (a) is the only route to every King County original including the star target
`Ortho2000EmergeCIR`; (b) settles the licence position for the Snohomish exports already proceeding under
Kam's decision of 2026-08-23 and carries the flight-log request that pins the 2020/2022/2024 anchor dates;
(c) is the only route to the 6-inch consortium products; (d) decides whether the C-CAP v2 map may be used
at all in an ML project.

---

## (a) King County GIS Center — giscenter@kingcounty.gov

**Subject:** Orthoimagery source tiles over Edmonds (T27N R3E / T27N R4E) for non-commercial research

Hello,

I am [affiliation] working on a non-commercial research project measuring per-tree canopy change in the
City of Edmonds from 2000 to 2024. Edmonds is in Snohomish County, but several King County orthoimagery
products cover it — your 2017 description, for example, names "southwestern Snohomish County" at the
Neighborhood (3-inch) level.

Your SDC catalog records for these products are marked IsPublic=false and "not yet available in ArcGIS
Online", so I am asking whether the source tiles (not the cached web-map tiles) can be provided for the
tiles intersecting T27N R3E and T27N R4E only:

1. IMAGE_Ortho2000EmergeCIR — the original TIFF tiles (of the 373), plus the tile index / per-tile
   acquisition dates (emerge_cir.dbf). This is the highest-value item: the colour-infrared parent of the
   2000 natural-colour derivative we already hold.
2. IMAGE_Ortho2009AerialsExpressCIR
3. IMAGE_Ortho2010KCCIR and IMAGE_Ortho2010KCNAT — the 7,500-ft tiles
4. IMAGE_Ortho2012KCNAT — or confirmation of the USGS distribution path, since the page states it is
   public domain via The National Map
5. IMAGE_Ortho2015CITYCIR — the uncompressed GeoTIFF tiles
6. IMAGE_Ortho2023KCCIR and IMAGE_Ortho2025KCCIR/KCNAT — only if the EagleView licence allows release to
   researchers; if it does not, a plain "no" is fine and I will stop asking.

Licence: your terms page permits copying and use and prohibits sale. Could you confirm that research use,
publication of derived products (canopy masks, statistics, figures) and non-commercial academic
publication are permitted? The imagery itself will not be redistributed or sold.

Delivery: a download link / FTP, or I can provide a drive. Thank you — and if there is a standard data
request form I should use instead, please point me to it.

---

## (b) Snohomish County GIS / DoIT (Viggo Forde, Director)

**Subject:** Two questions on the Imagery/Aerial_YYYY services and the 2020/2022/2024 EagleView projects

Hello,

I am [affiliation] on a non-commercial research project measuring canopy change in the City of Edmonds.

1. **Use of the public image services.** gis.snoco.org/img serves `Imagery/Aerial_YYYY` ImageServers for
   1990–2024 with exportImage enabled and no licence text. Your Orthophoto Data Products page notes that
   "more recent imagery may not be distributed due to contractual terms." Which years may be harvested at
   native resolution via exportImage for non-commercial research, and which years does the restriction cover
   (specifically 2015–2024)? The rasters stay internal to the project; only derived products (canopy masks,
   statistics, figures) are published.
2. **Per-frame acquisition dates for the EagleView regional projects.** For the 2020, 2022 and 2024 EagleView
   projects (King County RFP 1166-18-PCR, Snohomish County Piggyback PB-19-14BC; the City of Edmonds received
   its orthos under Contract Routing Form No. 20210127), could you share the flight log or photo-centre index
   with per-frame capture dates/times, or the `acquisitionStartDate/EndDate` metadata from the delivered
   GeoTIFF tiles, for the Edmonds area of interest? The published SCOPI windows (e.g. 13 April – 13 July 2020)
   are too wide to control for leaf-on/leaf-off in a canopy analysis.
3. Related: does the county hold the 2016 HXIP 6-inch delivery (`HXIP_2016_SNOHOMISH.gdb`), and can it be
   shared under the county's consortium membership for research use?

If a public records request is the right vehicle for item 2, please treat this as one. Thank you.

---

## (c) WA OCIO / Statewide Imagery Consortium — joanne.markert@ocio.wa.gov, 360.407.8691

**Subject:** Consortium eligibility for a research project (HXIP 6-inch 2016/2018/2020 over Edmonds)

Hello Joanne,

I am [affiliation] on a non-commercial research project on canopy change in Edmonds (Snohomish County). The
consortium's 6-inch products for 2016, 2018 and 2020 (and the 1-ft 2015/2017/2019 flights) cover Edmonds and
would materially improve the analysis. Your AGOL items say access "is restricted to those within the state
imagery consortium" and invite governmental organisations and non-profits to join. Is a [university /
non-profit / private] research project eligible, what does membership cost, and would it cover downloading
those products (not just viewing) for research use with only derived products published? Thank you.

---

## (d) NOAA Office for Coastal Management — coastal.info@noaa.gov

**Subject:** C-CAP high-resolution v2 (Puget Sound 2021) — machine-learning use restriction

Hello,

I am [affiliation] using the 2021 C-CAP High-Resolution Land Cover for Puget Sound (InPort 79723) as an
**evaluation reference** for an independently trained tree-canopy segmentation model over Edmonds, WA —
the product is not used for training, and no similar land-cover product is being created from it.

The landing page (coast.noaa.gov/digitalcoast/data/ccaphighres.html) states the data "may not be used for
the purpose of creating, training, improving, modifying, validating, testing, or evaluating machine learning
algorithms" for five years, while the product's own metadata sidecar limits the restriction to leveraging
ML "in order to explicitly create similar land cover data". Could you confirm which text governs, and whether
use solely as an accuracy reference (scoring a model's canopy map against C-CAP classes) is permitted?
Until we hear back the file is held unused. Thank you.

---

## (e) Not an email — Kam's own decisions still open

- **Empty the Google Drive trash** (drive.google.com/drive/trash): the 1,009 GB `upsample/` folder was deleted
  on 2026-08-22 but Drive free space is unchanged at ~46 GB, so it is almost certainly still in the trash.
- **2017 duplicate:** `2017_coe_rgb.tif` (48.4 GB) and `2017_king_rgb.tif` (11.5 GB) are the same orthomosaic.
  Recommendation: keep both on D:/backup; decide the Drive copy after the trash is emptied; never acquire a third.
- **CONNECTExplorer:** the 2021 ILA grants Edmonds up to ten EagleView CONNECTExplorer accounts; a screenshot of
  the per-image capture dates over Edmonds would pin the 2020/2022/2024 anchor dates without a records request.
