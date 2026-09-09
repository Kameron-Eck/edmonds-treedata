# Does the City of Edmonds acquire LiDAR every two years?

**Public-records and data-catalog investigation — 2026-09-09**

Prompted by a September 2026 email from City staff stating (a) *"our LIDAR fly-overs are
conducted in even years, (i.e. 2020, 2022, 2024, etc.)"* and (b) *"we've funded LIDAR imagery
from summer 2026 fly-overs ... to be completed next year or in 2028, depending on budget
outcomes."*

Method: a ten-channel multi-agent sweep of the public record, plus direct machine verification
against the USGS and NOAA lidar catalogs. **Read §7 (Limitations) before relying on any negative
finding** — this session's network egress was heavily restricted and the city-side record could
not be opened directly.

---

## 1. Bottom line

**No LiDAR was flown over Edmonds in 2020, 2022 or 2024, and no city-funded LiDAR acquisition
of any year appears in any record found.** The authoritative USGS national lidar index (WESM,
retrieved 2026-09-09, the day of writing) contains **3,276 work units nationally and not one
collected after 2016 that covers Edmonds**, apart from a sliver of the 2021 King County project
along the southern city limit. Independently, NOAA's coastal lidar catalog shows nothing over
Edmonds after 2016 either.

**The even-year cadence is real — but it is aerial photography, not LiDAR.** A 2021
Edmonds–Snohomish County interlocal agreement commits the County to deliver Edmonds orthogonal
imagery from the *2020, 2022 and 2024* EagleView regional acquisitions. That year list matches
the staff statement exactly. The City republishes each as `2020_Aerial_Cached`,
`2022_Aerial_Cached`, `2024_Aerial_Cached`. **Assessment: staff are describing the County
orthoimagery cycle and calling it LiDAR. Confidence: high.**

**On the funded summer-2026 flight, no authorising record was found**, and no 2026 lidar
acquisition is registered anywhere in 3DEP nationally. What does exist is an Edmonds
solicitation — *2026 Tree Canopy Assessment (RFP 18-26)*, indexed around 11 March 2026 — whose
scope of work could not be retrieved. That RFP is the most likely referent of "we've funded",
and whether it buys a **flight** or only an **analysis of existing imagery** is the single
unresolved question. It is answerable in one phone call or one records request (§8).

Two side findings worth your attention: the **"2017 LiDAR"** in the SavATree/UVM report is
almost certainly the USGS/WADNR 2016 acquisition under its 2017 publication date, not a separate
city holding (§6); and **two lidar vintages over Edmonds are missing from `IMAGERY_FACTS.md`** —
PSLC 2000 and a 2014 USACE/USGS survey whose project area is literally named "Edmonds" (§5).

---

## 2. What LiDAR demonstrably exists over Edmonds

Coverage below is **tile-verified**, not inferred from project footprints: for each dataset the
per-tile bounding boxes were downloaded from the NOAA/USGS S3 mirrors, reprojected to EPSG:26910
and intersected with the Edmonds bounding box (−122.42…−122.32, 47.77…47.87).

| Collected | Project | Sponsor / who paid | Contractor | Tiles over Edmonds | Latitude span | Coverage | Edmonds a named funder? |
|---|---|---|---|---|---|---|---|
| 2000-12-01 → 2001-01-30 | PSLC 2000 Puget Sound Lowlands (`m2485`, WESM `WA_PSLC_2000`) | Puget Sound Lidar Consortium | TerraPoint | 28 | 47.7624–47.8129 | **Southern Edmonds only** — stops around downtown | No |
| 2004-11-11 → 2005-07-15 | PSLC 2005 North Puget Lowlands (`m2579`) | Puget Sound Lidar Consortium | Terrapoint | 48 | 47.7769–47.8754 | **Full city** | No |
| 2014-09-04 | USACE/USGS Puget Sound topo-bathy (`m4909`) — project area named **"Edmonds"** | USGS / USACE JALBTCX | JALBTCX (CZMIL) | 3 | 47.7981–47.8753 | **Shoreline strip only** | No |
| 2016-03-17 → 2017-06-06 | Western Washington 3DEP QL1 (`m6331`, WESM `WA_Western_North_2016`) | **USGS in collaboration with WA DNR** | Quantum Spatial | 41 | 47.7765–47.8750 | **Full city** | No |
| 2016-02-24 → 2017-05-25 | PSLC King County 2016–2017 (`m8588`) | PSLC with Kitsap County DEM | Quantum Spatial | — | reaches only 47.829 | Southern margin | No |
| 2021-04-01 → 2021-04-24 | 3DEP King County Delivery 1 (WESM `WA_KingCo_1_2021`) | USGS | NV5 Geospatial | — | reaches ~47.79 | Southern city limit only | No |
| **2018, 2019, 2020, 2022, 2023, 2024, 2025, 2026** | **— nothing —** | | | **0** | | **No lidar exists** | |

The funding line for the dataset you actually use is explicit in the delivery record:

> "In March 2016, Quantum Spatial (QSI) was contracted by the United States Geological Survey
> (USGS) in collaboration with the Washington Department of Natural Resources (WADNR), to
> collect Light Detection and Ranging (LiDAR) data for the Western Washington 3DEP QL1 LiDAR
> Project area (Contract No. G16PC00016, Task Order No. G16PD00383)."
>
> — [Western Washington North 3DEP USGS Cover Letter, Quantum Spatial to USGS NGTOC, 1 Sept 2017](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WA_Western_WA_QL1_LiDAR__2016__B16/WA_Western-North_2016/reports/Western_Washington_North_3DEP_USGS_Cover_Letter.pdf)

Thirteen counties including Snohomish. **USGS and WADNR are the only funders named. No city,
no county, no cost-share partner appears anywhere in the acquisition record.**

### The definitive negative

[`WESM.gpkg`](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WESM.gpkg)
is USGS's Work-unit Extent Spatial Metadata — the national index of every 3DEP lidar work unit,
**including planned and in-progress ones**. Verified forward-looking: it carries 447 work units
with no publication date, 58 marked "Expected to meet", 5 "Under review", and 30 with a
collection start in 2025 or later. Queried on the copy last modified **2026-09-09**:

- Work units whose geometry covers Edmonds: **`WA_PSLC_2000`, `WA_Western_North_2016`,
  `WA_KingCo_1_2021` — and nothing else.**
- Washington work units collected after 2024-01-01: **exactly one**, `WA_6County_1_A24`
  (Eastern Washington, 27 Sept–19 Dec 2024, ~200 miles away — its own metadata gives a bounding
  box of −119.47…−116.98 longitude).
- Work units **anywhere in the United States** with a collection start on or after 2026-01-01:
  **zero.**

*Caveat: a purely city- or county-funded flight need not enter 3DEP. But in Washington, lidar
overwhelmingly flows through the USGS/WA DNR partnership, and WA DNR's own portal republishes
it. A regional flight invisible to both would be unusual.*

---

## 3. Evidence that the City acquires or funds LiDAR

**None was found.** Not one contract, purchase order, budget line, interlocal agreement, grant
application, consortium membership or vendor project page ties the City of Edmonds to a LiDAR
acquisition, in any year.

Specifically searched and empty:

- **Vendor side.** No project page, portfolio entry, press release, case study or delivery
  report from NV5 Geospatial, Quantum Spatial, Watershed Sciences, Woolpert, Sanborn, Dewberry,
  Fugro, Merrick, Surdex, Kucera, Axis, GeoTerra, Aerial Services, Digital Mapping, Terra
  Remote Sensing, EagleView, Pictometry, Nearmap, Vexcel or Hexagon names the City of Edmonds
  as a LiDAR client. If a city had hired a lidar contractor, this is the search that normally
  surfaces it.
- **Cost-share programs.** Edmonds appears in no USGS 3DEP Broad Agency Announcement partner
  list, no WA DNR lidar cost-share, and not in the Puget Sound Lidar Consortium partner list
  that surfaced (which named Kitsap, City of Seattle, Clallam and Island counties).
- **Acquisition metadata.** The technical data reports and FGDC metadata for every lidar
  dataset covering Edmonds name their funders. Edmonds is never among them.

The one Edmonds-commissioned aerial acquisition with machine-readable capture metadata on the
City's own GIS server is a **30-minute sortie over Edmonds Marsh on 2018-08-01** — roughly one
square kilometre of imagery, no lidar attributes.

---

## 4. The conflation: what the even-year cycle actually is

This is the load-bearing finding, and it is already in your own evidence ledger
(`Scripts/qc/imagery_pixelsize_and_date.csv`), captured from the City's Laserfiche WebLink
repository, document id 1462454:

> "Upon completion of the **2020, 2022 and 2024 EagleView regional aerial imagery acquisition
> projects** and receipt of imagery by County, County will provide Edmonds with **orthogonal
> imagery** for Edmonds's identified area of interest"
>
> — City of Edmonds / Snohomish County Interlocal Agreement (2021), Work Order p.14

The chain, each link independently recorded:

1. **Contract vehicle** — King County RFP 1166-18-PCR (EagleView Technology Corp.), used by
   Snohomish County via piggyback **PB-19-14BC**.
2. **The County's own description** of what it buys: *"The 2022 3 inch resolution aerial photos
   in the urban areas, were captured between April 6, 2022 and July, 11 2022"*; and for 2024,
   *"The 2024 3 inch resolution aerial photos ... captured between March 31, 2024 and May, 31
   2024."* **Aerial photos.** The word lidar does not appear.
3. **What Edmonds publishes** — `Basemap/2015_Aerial_Cached`, `2017_Aerial_Cached`,
   `2020_Aerial_Cached`, `2022_Aerial_Cached`, `2024_Aerial_Cached` on `maps.edmondswa.gov`.
   No lidar, DEM, DSM, hillshade or canopy-height service appears in any query of that server.
4. **Product fingerprint** — a neighbouring city's copy of the identical 2022 county product is
   a MrSID photo mosaic whose service metadata records only `"IMAGE__MODIFICATIONS":"COMPRESSED
   EMBEDDED MASKED MOSAICKED"`. That is an orthophoto, with no elevation channel.
5. **Your own ledger's summary line**: *"The odd/even supplier pattern stands: odd years King
   County, even years Snohomish County"* (`IMAGERY_FACTS.md` §9.2).

And Edmonds *does* pay into imagery cost-shares — just not lidar ones. The City is a named
participant in the 2015 Western Washington Regional Orthophotography consortium (King County
lead, 88 participants, agreement signed 2015-06-23) at a cost of **$3,696.21**. That is the
shape of Edmonds' aerial-data spending: a few thousand dollars to join a county photo buy —
roughly three orders of magnitude below what a dedicated municipal lidar flight costs.

**Verdict: staff almost certainly mean the Snohomish County EagleView orthoimagery cycle.
Confidence: high.** Every element of the staff statement — the even years, the specific list
2020/2022/2024, the word "fly-overs" — maps onto it exactly, and no competing lidar explanation
survives the catalog evidence in §2.

One point of genuine ambiguity in staff's favour: EagleView delivers photogrammetric 3D
products (a DSM and point-cloud-like surface) alongside its imagery, and those are loosely
called "3D" in vendor marketing. If Edmonds receives such a product, a non-specialist could
reasonably call it lidar. It still is not lidar, and it carries none of lidar's under-canopy
returns.

---

## 5. Two lidar vintages missing from your inventory

`IMAGERY_FACTS.md` §8.1 records exactly two vintages, PSLC 2005 and USGS 2016. Two more cover
Edmonds:

**PSLC 2000** (`WA_PSLC_2000`, NOAA `m2485`) — TerraPoint for the Puget Sound Lidar Consortium,
collected 2000-12-01 to 2001-01-30, leaf-off. **28 tiles overlap Edmonds, spanning latitude
47.7624–47.8129** — that is southern Edmonds up to roughly downtown, *not* the whole city. The
source description confirms the limit: the survey *"covers part of Kitsap Peninsula, the Seattle
area north to the King-Snohomish county border."* Rated "Does not meet" 3DEP quality; the point
cloud is not staged on the USGS S3 mirror, but the COPC tiles **are** on the NOAA mirror at
`noaa-nos-coastal-lidar-pds/laz/geoid18/2485/`. Given your project's baseline year is 2000, an
era-matched height layer for the southern half of the city may be worth the download.

**2014 USACE/USGS Puget Sound topo-bathy** (NOAA `m4909`) — collected **2014-09-04**, one of
nine project areas, the relevant one **named "Edmonds"** in the metadata; sample tile
`20140904_usgs_wa_edmonds_47122g4b.copc.laz`. Only **3 tiles** overlap the city: a coastal
strip. Classified topo/bathy (classes 1, 2, 7, 9, 29). Not usable for citywide canopy, but it is
a dated height reference in the middle of your 2013–2015 imagery gap.

> **Correction to a hypothesis raised mid-investigation.** The WESM footprint polygon for
> `WA_Western_North_2016` appears to stop near latitude 47.82, which would leave north Edmonds
> without 2016 lidar and would undercut the "no-lidar zone is water" conclusion in
> `Edmonds_Verified_Results_2026-08-19.md`. **That is an artifact of a generalised polygon.**
> The delivered tile bounds run 47.7765–47.8750 across 41 tiles — matching the 41 tiles
> `IMAGERY_FACTS.md` §8.2 records. 2016 coverage of Edmonds is complete; the existing conclusion
> stands. WESM geometry is reliable for *which projects exist*, not for footprint edges.

---

## 6. The "2017 LiDAR" question — resolved

The SavATree/UVM *Tree Canopy Assessment 2015–2020* cites *"LiDAR acquired 2017"* with sources
including "City of Edmonds". Two candidate explanations; the evidence settles it.

- **The only other Washington lidar project with 2017 collection dates is
  `WA_3_County_Lidar_2017_B17` — Columbia, Garfield and Walla Walla counties, southeastern
  Washington.** Its metadata: *"approximately 2,917 square miles of south eastern Washington."*
  Definitively eliminated.
- **The USGS/WADNR Western Washington acquisition ran to 2017-06-06 and was published
  2017-08-31.** Its northern block, which contains Edmonds, flew to 2017-05-28, and QSI
  *"provided the Northern portion ... to USGS on September 1st, 2017."*

**Conclusion: SavATree's "2017 LiDAR" is the USGS/WADNR 2016 acquisition under its
delivery/publication year. No separate city-owned 2017 lidar exists. Confidence: high.** The
"City of Edmonds" credit in the source list is best read as the City supplying imagery and
boundary/GIS layers — which it demonstrably has — not lidar.

This matters for your dossier: it means the 34.6% (2020) figure and the 2016 lidar you hold rest
on **the same** height data, so they are not independent in the way the vendor list implies.

---

## 7. Limitations — read before citing any negative

**This session's network egress was blocked for essentially every relevant host.** The proxy
returned HTTP 403 at CONNECT for `edmondswa.gov`, `weblink.edmondswa.gov` (the City's Laserfiche
repository), `edmondswa.primegov.com` (the agenda portal), `cdnsm5-hosted.civiclive.com` (the
document CDN holding budgets and RFPs), `snohomishcountywa.gov`, `myedmondsnews.com`,
`bxwa.com`, `dnr.wa.gov`, `fisheries.noaa.gov`, `web.archive.org` — and even Wikipedia. Only
AWS S3 was reachable, which is why the catalog evidence in §2 is strong and the city-side
evidence in §3 is weak.

Consequences you must weight:

- **The §2 catalog findings are machine-verified against primary USGS/NOAA metadata and are
  reliable.**
- **The §3 negatives are search-index-level, not full-text-verified.** No agent opened the
  2025–2026 biennial budget, any council packet, or any Edmonds RFP. I specifically do **not**
  assert "the budget contains no occurrence of 'lidar'" — nobody read it.
- A shared **WebSearch budget of 200 calls was exhausted** partway through, so the last three
  channels (planning, records, part of catalogs) ran with little or no search capability. The
  planning channel — the 2019 UFMP, the 2024 Comprehensive Plan, the PlanIT Geo and SavATree
  scopes of work — **was not executed** and should be re-run from an unrestricted network.
- Verification agents could not re-fetch city-side URLs either, so most city-side findings
  carry a verdict of UNREACHABLE rather than CONFIRMED. They are leads, not established facts.

Nothing in this report was accepted without a source; where a source could not be opened, the
finding is labelled rather than dressed up.

---

## 8. Recommended next steps, ranked

1. **Ask the question directly — highest value, lowest cost.** Reply to the staff member:
   *"Could you point me to the vendor or contract for the 2020/2022/2024 flights? I'd like the
   point clouds. I can only find the Snohomish County EagleView orthoimagery for those years,
   and no lidar over Edmonds after the 2016 USGS/DNR flight."* Framed as a data request rather
   than a challenge, this resolves it immediately and, if it is a conflation, lets them correct
   it without embarrassment.
2. **Open two URLs you can reach and I could not.** `edmondswa.gov/doing_business/bids_rfp_s_and_rfq_s`
   for **RFP 18-26, "2026 Tree Canopy Assessment"** — its scope of work decides whether the
   "funded" 2026 work is a flight or a desk analysis. And Laserfiche WebLink document **1462454**
   to confirm whether a successor or amended ILA covers a 2026 acquisition.
3. **File the Public Records Act request in Appendix A.** It is drafted to force a written
   yes/no on the lidar-versus-imagery question, and Part 3's "avoidance of doubt" paragraph lets
   the City answer with one statement instead of a document search. File a parallel request with
   Snohomish County DoIT/GIS, citing King County RFP 1166-18-PCR and piggyback PB-19-14BC.
4. **Re-run the planning channel** from an unrestricted network — the UFMP, Comprehensive Plan
   appendices, and the PlanIT Geo and SavATree scopes of work were never opened, and the PlanIT
   Geo scope is also where the unexplained "2021 canopy data" provenance would be documented.
5. **Consider pulling PSLC 2000** from the NOAA mirror for the southern half of the city (§5) —
   it is era-matched to your 2000 baseline, which nothing else you hold is.
6. **Note for the dossier** (§6): the 2020 SavATree figure and your 2016 lidar share a single
   height source, so they are not independent measurements.

---

## Appendix A — drafted Public Records Act request

*Verify the recipient address and intake channel on the City's public records page before
sending; the City Clerk's Office is the conventional PRA custodian for a Washington code city of
this size.*

**To:** Public Records Officer, City Clerk's Office, City of Edmonds, 121 5th Avenue North,
Edmonds, WA 98020

**Re:** Public Records Act request — LiDAR and aerial data acquisition records, 2014 to present

Pursuant to the Washington Public Records Act, chapter 42.56 RCW, I request copies of the
following identifiable public records of the City of Edmonds. Unless otherwise noted, my date
range is **January 1, 2014 through the date the search is run**. I prefer electronic copies in
native format, delivered electronically, and I consent to production in installments.

**Part 1 — Acquisition of LiDAR data (point clouds; DEM, DSM or canopy-height models derived
from LiDAR)**

1. All contracts, professional services agreements, task orders, work orders, statements of
   work, amendments, purchase orders, requisitions, invoices, and payment vouchers between the
   City and any of the following, to the extent they concern LiDAR, elevation, point-cloud, or
   canopy-height data: NV5 Geospatial; Quantum Spatial; Watershed Sciences; Woolpert; Sanborn
   Map Company; Dewberry; Fugro; Merrick & Company; Axis GeoSpatial; GeoTerra; Digital Mapping
   Inc.; Surdex; Aerometric; Terra Remote Sensing; Hexagon or Leica Geosystems; Vexcel; Nearmap;
   EagleView Technology Corporation; Pictometry International Corp.; David Evans and Associates;
   Perteet; KPFF; WSP; PlanIT Geo, Inc.; SavATree or SavATree Consulting Group; and Davey
   Resource Group.
2. All interlocal agreements, memoranda of understanding, cost-share or joint-funding
   agreements, and participation or buy-in letters to which the City is a party or a named
   beneficiary concerning LiDAR acquisition, including any involving: Snohomish County; King
   County; the Puget Sound Lidar Consortium; the Puget Sound Regional Council; the Washington
   State Department of Natural Resources or Washington Geological Survey lidar program; the
   U.S. Geological Survey 3D Elevation Program (3DEP), including any Broad Agency Announcement
   application, award, or cost-share commitment; FEMA Risk MAP; and any Washington State
   Department of Enterprise Services master contract used for such a purchase.
3. Records sufficient to identify every LiDAR dataset the City holds, has licensed, or has
   received, including delivery receipts and data transmittals, FGDC or ISO metadata records,
   project or technical data reports, QA/QC and accuracy reports, and license or use agreements.
   If the City maintains a GIS data catalog, data dictionary, or data inventory, I request the
   current version and any earlier version showing LiDAR holdings.

**Part 2 — The stated summer 2026 flight**

4. All records documenting the acquisition described by City staff as "LIDAR imagery from
   summer 2026 fly-overs," including any contract, task order, purchase order, interlocal
   agreement, county participation form, grant application or award, and any scope of work or
   technical specification.
5. All budget records funding that acquisition: budget decision packages, budget amendment
   ordinances and their exhibits, Capital Improvement Program and Capital Facilities Plan
   sheets, and any council or committee agenda memo or packet in which the funding was requested
   or approved, for the 2025–2026 and 2027–2028 budget cycles.
6. All email and other correspondence, **January 1, 2025 to present**, to or from the Urban
   Forest Planner; the Director of Parks, Recreation & Human Services; the Public Works
   Director; the City Engineer; the City's GIS Analyst or GIS Coordinator; the Planning &
   Development Director; and the Finance Director, containing any of the following terms:
   "LiDAR", "lidar", "point cloud", "canopy height", "CHM", "flyover", "fly-over", "aerial
   acquisition", "orthophoto", "orthoimagery", "oblique imagery", "EagleView", "Pictometry",
   "NV5", "Quantum Spatial", "3DEP", "Puget Sound Lidar Consortium", or "Washington Geological
   Survey".

**Part 3 — Distinguishing orthoimagery from LiDAR (central to this request)**

7. All interlocal agreements, work orders, amendments and renewals between the City and
   Snohomish County concerning aerial imagery, specifically including the agreement covering the
   County's 2020, 2022 and 2024 EagleView regional aerial imagery acquisition projects, and any
   successor agreement, amendment, or participation form covering a 2026 acquisition.
8. Records sufficient to show, for **each even-numbered year from 2016 through 2026**, what the
   City actually acquired or received — orthophotography, oblique imagery, or LiDAR — including
   the delivery record, product name, sensor or product type, and acquisition dates.
9. Records concerning the City's participation in any county-led or consortium orthoimagery
   purchase, including any use of King County RFP 1166-18-PCR (EagleView Technology Corp.) or
   Snohomish County's related piggyback contract.

*For the avoidance of doubt: I am asking about LiDAR specifically, and separately about aerial
photography and oblique imagery. If the City's even-year aerial acquisitions consist only of
orthophotography and oblique imagery obtained through Snohomish County, and the City holds no
LiDAR of its own beyond publicly available USGS or Washington DNR datasets, then a written
statement to that effect from the responsible department would be fully responsive to Parts 1
and 3, and I would accept it in lieu of a document-by-document search for those parts.*

**Part 4 — Canopy assessments and the elevation data they used**

10. The complete 2024 Urban Tree Canopy Assessment prepared by PlanIT Geo, Inc. — the full
    report, not the summary handout — including its methodology section, the imagery and/or
    LiDAR source and acquisition dates, and any accuracy assessment; together with the contract,
    scope of work, and deliverables list under which it was produced.
11. Records identifying the LiDAR dataset that the City provided to, or that was used by,
    SavATree Consulting Group and the University of Vermont Spatial Analysis Laboratory for the
    *Tree Canopy Assessment 2015–2020* (published February 2022), which cites "2017 LiDAR"
    sourced in part from the City of Edmonds — including any data transmittal, file-transfer
    record, data-sharing agreement, or correspondence identifying that dataset.

**Administrative**

- Please treat each numbered item as severable. Produce what you have for each item as it
  becomes available, and do not delay production of one item pending completion of another.
- If any responsive record is withheld or redacted, please provide the exemption log required by
  RCW 42.56.210(3), identifying the record, the specific statutory exemption claimed, and a
  brief explanation of how it applies.
- If the City determines that no responsive records exist for a given item, please state that in
  writing and identify the records retention schedule and series under which such records would
  have been filed had they existed.
- If responsive records are held by Snohomish County or another agency rather than the City,
  please say so and identify the agency; I will direct a separate request there.

---

## Appendix B — reproducing the catalog evidence

Every §2 finding is reproducible from two public S3 buckets, no credentials required.

| What | Where |
|---|---|
| USGS national lidar work-unit index (incl. planned) | `s3://prd-tnm/StagedProducts/Elevation/metadata/WESM.gpkg` (3.7 GB; a smaller `WESM.csv` sits beside it) |
| 2016 project delivery reports and FGDC metadata | `s3://prd-tnm/StagedProducts/Elevation/metadata/WA_Western_WA_QL1_LiDAR__2016__B16/` |
| 2016 per-tile bounds | `s3://noaa-nos-coastal-lidar-pds/laz/geoid18/6331/minmax_wa2016_west_wa_m6331.csv` |
| PSLC 2005 per-tile bounds + COPC tiles | `s3://noaa-nos-coastal-lidar-pds/laz/geoid18/2579/` |
| PSLC 2000 per-tile bounds + COPC tiles | `s3://noaa-nos-coastal-lidar-pds/laz/geoid18/2485/` |
| 2014 USACE/USGS "Edmonds" tiles | `s3://noaa-nos-coastal-lidar-pds/laz/geoid18/4909/` |
| Dataset-level descriptions (STAC) | `s3://noaa-nos-coastal-lidar-pds/entwine/stac/DigitalCoast_mission_<id>.json` |

Method for the coverage column: parse each `minmax_*.csv`, reproject the Edmonds bounding box to
EPSG:26910, intersect, and report the latitude span of the overlapping tiles. WESM was queried
by parsing GeoPackage geometry envelopes and running point-in-polygon against sample points
across the city — reliable for project membership, unreliable at footprint edges (§5).
