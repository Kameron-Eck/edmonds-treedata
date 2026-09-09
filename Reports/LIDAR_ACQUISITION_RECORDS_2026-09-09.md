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
of any year surfaced.** The authoritative USGS national lidar index (WESM, retrieved 2026-09-09,
the day of writing) contains **3,276 work units nationally and not one collected after 2016 that
covers Edmonds**, apart from a sliver of the 2021 King County project along the southern city
limit. Independently, NOAA's coastal lidar catalog shows nothing over Edmonds after 2016 either.
The one live threat to that conclusion — a cost-shared 2022 NV5 project, `WA_LidarGaps_C22`,
that is *missing from WESM entirely* — was chased down separately: all 48,596 of its tiles were
tested and **none touches Edmonds** (see §2). That closes the gap rather than leaving it open.

The two halves of this report differ in strength and should be cited differently: **the "no
lidar exists" finding is machine-verified against primary USGS/NOAA catalogs and is solid**; the
"no city record exists" finding is search-index-level only, because the network blocked every
city-side host this session (§7).

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
| 2016-03-17 → 2017-06-06 (**Edmonds tiles: 2016-03-30**) | Western Washington 3DEP QL1 (`m6331`, WESM `WA_Western_North_2016`) | **USGS in collaboration with WA DNR** | Quantum Spatial | 41 | 47.7765–47.8750 | **Full city** | No |
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
no county, no cost-share partner appears anywhere in the acquisition record.** (The report says
"thirteen counties" and then lists ten — an internal inconsistency in the source, noted so it
does not get cited as a clean fact.)

### A pipeline-relevant detail: the Edmonds 2016 lidar is a single leaf-off day

The project as a whole ran 2016-03-17 to 2017-06-06, which is what `IMAGERY_FACTS.md` §8.1
records. But **all 41 tiles covering Edmonds carry one acquisition date: 2016-03-30** — late
March, leaf-off. That is the same structural situation §8.1 already documents for PSLC 2005
("ALL named 20050227 — one leaf-off Feb-27-2005 acquisition"). Both of the full-coverage lidar
vintages over Edmonds are therefore **single-day leaf-off** acquisitions, which bears directly
on any deciduous canopy or crown-height inference drawn from either. Worth adding to §8.1.

Note also that "Edmonds" appearing in the PSLC 2005 metadata is a **delivery-area name**, not a
funding credit — the same wording lists Arlington, Marysville, Mukilteo and others.

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

### WESM has a blind spot — it was found, checked, and closed

WESM is not complete. Diffing the 24 Washington project folders on the USGS staging mirror
against WESM project names turns up **two staged Washington projects with no WESM rows at all**:
`Elwha_River_WA_LiDAR` (Olympic Peninsula, irrelevant here) and — the one that matters —
**`WA_LidarGaps_C22`**, a delivered QL1 project flown by NV5 Geospatial from **2022-07-23 to
2023-02-24** under contract mechanism **"Contributed"** (i.e. cost-shared). A 2022 Washington
lidar project, cost-shared, invisible to the index every negative above rests on, is precisely
the way the staff claim of a 2022 flight could have been correct.

**It was checked directly and it does not cover Edmonds.** All four work-unit tile indexes were
downloaded and every tile envelope tested against the Edmonds bounding box (E 1,168,240–1,193,670,
N 893,816–930,872 ftUS in EPSG:2927):

| Work-unit block | Extent (EPSG:2927 ftUS) | Where that is | Tiles over Edmonds |
|---|---|---|---|
| 1 | E 1,050,750–1,617,750 / N 150,750–679,828 | southern Washington | 0 |
| 2 | E 717,750–1,001,250 / N 794,250–1,028,250 | Olympic Peninsula / west | 0 |
| 3 | E 1,017,000–1,390,500 / N 978,750–1,352,250 | **north of Everett** | 0 |
| 4 | E 1,338,750–1,599,750 / N 888,750–1,343,250 | eastern Washington | 0 |
| | | **48,596 tiles total** | **0** |

The four blocks surround Edmonds without touching it — which is exactly what a project named
"LidarGaps" should do, since Edmonds already had QL1 coverage from 2016 and was therefore not a
gap. Block 3 is the "Snohomish gap": its southern edge sits at N 978,750, about **13 miles north
of Edmonds** (N 909,098), starting just above Everett (N 969,404) and running north over
Marysville and Arlington.

This also explains a lead that surfaced from the Everett side — a City of Everett council item
cost-sharing (~$21,268 from its utilities fund) into an NV5 lidar collection under a WA DNR work
order covering "Thurston, Adams, and Snohomish Counties and the Cities of Marysville and
Everett". That is this project. **Snohomish County's portion of it is the northern county, not
Edmonds** — so it is a genuine post-2016 Puget Sound lidar cost-share that nonetheless delivers
nothing over Edmonds.

*Remaining caveat: a purely city- or county-funded flight need not enter 3DEP at all, and the
LidarGaps case proves the staging mirror can hold projects the index misses. But in Washington
lidar overwhelmingly flows through the USGS/WA DNR partnership, and both mirrors were checked.
A regional flight invisible to both would be unusual — not impossible.*

---

## 3. Evidence that the City acquires or funds LiDAR

**None was found — but read this section's evidentiary weight carefully.** The catalog evidence
in §2 is machine-verified and strong. This section is *not*: no agent could open a single
Edmonds budget, council packet, ordinance, RFP or contract, because the network blocked every
city host (§7). What follows is "nothing surfaced in indexed search", not "the records were
searched and are empty". Four of ten channels returned zero findings for this reason.

With that scoping: not one contract, purchase order, budget line, interlocal agreement, grant
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
   County, even years Snohomish County"* (`IMAGERY_FACTS.md` §9.2). **Qualify this before using
   it:** it holds cleanly for the *modern regional programs* — the held King County series runs
   2013, 2015, 2017, 2019, 2021, 2023 and the Snohomish regional deliveries are 2020, 2022,
   2024 — but the pre-2013 King holdings (2000, 2005, 2007, 2009, 2012) are mixed, and the 2016
   and 2021 Snohomish rows are Hexagon HXIP statewide flights, a separate program. The
   even-year=Snohomish half of the pattern, which is the half that matters here, is sound.

And Edmonds *does* pay into imagery cost-shares — just not lidar ones. The City is a named
participant in the 2015 Western Washington Regional Orthophotography consortium (King County
lead, 88 participants, agreement signed 2015-06-23) at a cost of **$3,696.21**. That is the
shape of Edmonds' aerial-data spending: a few thousand dollars to join a county photo buy —
roughly three orders of magnitude below what a dedicated municipal lidar flight costs.

**Verdict: staff almost certainly mean the Snohomish County EagleView orthoimagery cycle.
Confidence: moderate-to-high.** Every element of the staff statement — the even years, the
specific list 2020/2022/2024, the word "fly-overs" — maps onto it exactly, and no competing
lidar explanation survives the catalog evidence in §2.

*Why not "high": the single ILA sentence carrying this conclusion was never read from the live
Laserfiche document this session. It is quoted from your own QC ledger, which transcribed it
earlier — so citing it back to the ledger is circular. The $3,696.21 consortium figure has the
same weakness: it sits in an unsourced free-text `notes` field with no contract number or
document ID. Both are almost certainly right, and both need one look at the source document
(next steps 2 and 3) before you put them in writing to the City.*

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

### Still open — modalities never searched

A completeness pass over the sweep found whole funding routes that no channel touched. These are
where a genuine city-funded acquisition would hide if one exists, ranked by how likely they are
to change the answer:

- **Grant funding — never searched by any channel.** "We've funded… depending on budget
  outcomes" plus no council action plus no budget line fits *grant* money, not city money. Check
  WA DNR Urban & Community Forestry awards FY2024–FY2026 for "Edmonds", including federal
  Inflation Reduction Act urban-forestry subawards. A grant explains funding with no
  appropriation and a schedule contingent on a legislative outcome — every feature of the email.
- **Expenditure records, not appropriations.** Every "no budget line" negative looked in the
  wrong place for a purchase this size. A $3,700–$25,000 buy-in never generates an appropriation;
  it appears only as a vendor name on a claim-check voucher listing in a council consent packet.
  Pull those for 2019–2026 and search for EagleView, Pictometry, NV5, Quantum Spatial, GeoTerra,
  Nearmap, Vexcel, Snohomish County, PlanIT Geo, SavATree.
- **Capital-project survey budgets** — the most common way a small Washington city actually pays
  for a flight, and the most likely thing a non-GIS staffer would generalise into "our
  fly-overs". Check Hwy 99 Revitalization task orders, the Edmonds Marsh / Willow Creek
  daylighting basis-of-design, and the Storm & Surface Water Comprehensive Plan (stormwater
  utilities are the usual municipal lidar funder — that is exactly the fund Everett used).
- **Laserfiche WebLink full-text search** — recommended by six channels, executed by none. It is
  the only Edmonds system with true full-text search across packets, contracts and vouchers.
- **The June 2026 council video/captions.** Every account of what the Urban Forest Planner said
  is a search-engine paraphrase of an article nobody opened, and it is *prospective* ("will work
  with lidar teams") where the email is *past tense* ("we've funded"). A verbatim transcript
  decides whether this is a staff misstatement or a reporter's compression — the difference
  between a correction and an accusation. Worth getting before you write back.
- **Whether EagleView's even-year delivery includes a photogrammetric DSM or point cloud.** This
  is the strongest good-faith reading of the staff claim and it currently rests on nothing. If
  Edmonds does receive a 3D product, staff are loosely labelling something real and your reply
  should say so; if it is RGB rasters only, it is a category error. Ask Snohomish County DoIT.
- **Neighbouring jurisdictions never searched** (the county channel ran out of search budget):
  Lynnwood, Mountlake Terrace, Woodway, Shoreline, plus Sound Transit's Lynnwood Link and WSDOT
  SR-104/SR-99 mapping. A neighbour-led buy is one of the few remaining routes to lidar over
  Edmonds without an Edmonds contract.
- **PlanIT Geo's TreePlotter CANOPY** instance for Edmonds, if one exists — a live vendor-hosted
  viewer states its source imagery and lidar vintage in layer metadata, which would resolve the
  unexplained "2021 canopy data" provenance without the City having to produce anything.

One item explicitly *not* worth further effort: the "34.6% in 2023" press figure. Your dossier
already settles it — it is a 2020 number, repeatedly miscited.

---

## 9. Closing the gap from an unrestricted network

The §7 limitation is mechanical, not analytical: the documents exist and are public, this
session just could not reach the hosts. That is fixed by running the fetch somewhere with
ordinary network access and committing the retrieved text back here, where any later session
reads it without egress.

**On a machine with normal internet (home wifi), run:**

```
Scripts\qc\fetch_city_records.cmd
```

It checks out this branch, pulls, retrieves every source in `Reports/sources/SOURCES.tsv`,
extracts the text, commits it, and pushes. Safe to re-run — sources already fetched are
skipped, so a second run only retries failures. To re-attempt just the failures:

```
Scripts\qc\fetch_city_records.cmd --retry-failed
```

**Then, in a Claude Code session on that machine**, one line is enough to resume the work:

> Read `Reports/LIDAR_ACQUISITION_RECORDS_2026-09-09.md`, then the retrieved documents in
> `Reports/sources/text/`. Answer the open questions in §8: does RFP 18-26 buy a flight or a
> desk analysis; does the 2021 interlocal work order list any elevation deliverable or have a
> 2026 successor; and is the 2026 canopy work grant-funded. Update the report with what the
> documents actually say.

### What lands, and what is deliberately not tracked

`Reports/sources/` holds three tracked things and one untracked one:

| Path | Tracked | What it is |
|---|---|---|
| `SOURCES.tsv` | yes | The target list — 16 sources, ranked, each with why it matters. Rows are marked VERIFIED (retrieved in this investigation, or recorded in `inventory.csv`) or **UNVERIFIED** (reconstructed from search indexing and never opened). An UNVERIFIED URL that 404s is information, not a bug. |
| `MANIFEST.tsv` | yes | Provenance per fetch: HTTP status, final URL after redirects, content type, byte count, sha256, UTC timestamp. A failure is recorded **as a failure with its error**, so a later reader can tell "checked, absent" from "never checked". |
| `text/*.txt` | yes | Extracted text — small, diffable, greppable. This is the point: the record becomes readable from a sandboxed session. |
| `raw/` | **no** | The bytes as served. Git-ignored for the same reason the consultant PDFs are: the planning-board packet alone is 16 MB and they re-download. |

### The one thing the script cannot do

It does not execute JavaScript. **Laserfiche WebLink and PrimeGov are portal applications**, so
a plain GET may return an application shell rather than the document. The script tries three
known WebLink endpoint forms for the interlocal agreement and refuses to accept an HTML
response under 8 KB as a document — such a response is logged as a portal shell, not silently
saved as if it were the record. If those rows come back FAILED, the fallback is a browser
(Playwright, or simply saving the PDF by hand from the viewer). The two highest-value targets —
Laserfiche doc 1462454 and the Laserfiche full-text search for "lidar" — are the most likely to
need that manual step, and they are also the two that would most change the report.

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
| The 2022 project missing from WESM | `s3://prd-tnm/StagedProducts/Elevation/metadata/WA_LidarGaps_C22/` — project report, and tile indexes under `vertical_accuracy/USGS/created_gpkg/gdal_tile_index_{1,2,3,4}.gpkg` |

Method for the coverage column: parse each `minmax_*.csv`, reproject the Edmonds bounding box to
EPSG:26910, intersect, and report the latitude span of the overlapping tiles. WESM was queried
by parsing GeoPackage geometry envelopes and running point-in-polygon against sample points
across the city — reliable for project membership, unreliable at footprint edges (§5).
