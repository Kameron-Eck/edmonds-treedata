# Edmonds Tree Canopy Reports — Data & Method Dossier

Compiled 2026-08-16. Scope: reports and studies that **measure, assess, or inventory** Edmonds trees
and canopy. Policy documents (comprehensive plans, climate action plans, PROS, ordinances, SEPA
notices) are deliberately excluded — they consume these reports, they are not reports.

**Core finding up front:** Edmonds has **six canopy percentages** from **four sources**, produced by
**five different methods** on **two different denominators** — and one of the six is not a measurement
at all but an acknowledged assumption. They are routinely quoted side by side as a trend line. They are
not comparable. Normalizing the denominators (see below) closes about half the gap between the two
genuine measurements; the rest is method.

---

## Comparison table

| Report | Vendor | Year measured | Data source | Method | Denominator | Canopy | Accuracy stated |
|---|---|---|---|---|---|---|---|
| UTC Assessment (2018) | Davey Resource Group | 2005 | Google Earth historical image | **i-Tree Canopy, 1,000 points interpreted by eye** | total area | **32.3%** | none — Davey warns it is "not considered as accurate" |
| UTC Assessment (2018) | Davey Resource Group | 2015 | USDA FSA color-infrared aerial, flown 2015-08-07 | **OBIA semi-automated extraction** (Feature Analyst / ArcGIS) + manual QA/QC at 1:1500 | **total area incl. 402 ac water** (1,844 ÷ 6,095) | **30.3%** | yes — confusion matrix, producer's accuracy 89.87%, kappa reported |
| UFMP (Jul 2019) | Davey Resource Group | carries 2015 forward | — | none of its own | total area | "about 30.3%" | inherits above |
| Tree Canopy Assessment 2015–2020 (Feb 2022) | SavATree Consulting Group + **UVM Spatial Analysis Laboratory** | 2015 & 2020 | 2015 + 2020 imagery **plus 2017 LiDAR** | automated feature extraction + manual review, **LiDAR height data added** | **land area, water excluded** | **34.3% → 34.6%** | **none stated in document** — "accuracy" appears once, rhetorically |
| Forecast Analysis of Planting Scenarios (Jan 2026) | **PlanIT Geo, Inc.** | "2024" — see below | **assumption from 2021 canopy data** | **not stated in delivered memo** | not stated | **32.4%** | none stated |
| Tree Canopy Contribution by Zone Type (Feb 2026) | **unattributed** — found locally, see below | 2021 | **NOAA 2021 Urban Tree Canopy model** | zonal statistics per zoning district | **land area** | **33.27%** | none stated |

---

## The 32.4% trace — RESOLVED

**Verdict: traced.** The figure originates in **PlanIT Geo, "A Forecast Analysis of Possible Planting
Scenarios," prepared for the City of Edmonds**, delivered as **Attachment 3 to the Jan 28, 2026 Edmonds
Planning Board packet**. A shorter edition dated 2024-07-25 is published on PlanIT Geo's own website
(archived here as `planitgeo_edmonds_factsheet.pdf`); the underlying 2024 assessment remains unpublished.

Verified directly in the packet PDF (`2026-01-28_planning-board-packet_planitgeo-forecast.pdf`,
attachment begins ~p.117 of 122). Two verbatim strings confirmed by text extraction:

> **"Edmonds' 2024 canopy cover is an assumption based on 2021 canopy data."**

> "Report prepared for The City of Edmonds | Project conducted by PlanIT Geo, Inc."

The chain by which it became binding code:

1. PlanIT Geo states 32.4% / 1,855 acres as "current state," footnoted as an **assumption**, not a
   measurement, derived from **2021** data.
2. The Jan 28 2026 **staff report** presents it as fact: *"In Edmonds' 2024 analysis, consultant
   PlanITGeo estimated that existing tree canopy cover is 32.4%... notably lower than Edmonds' 2020
   estimated tree canopy cover of 34.6 percent."*
3. Planning Board motion converts it to a target: maintain 32.4% annually "so that it is 35% by 2036."
4. Draft **ECDC 17.130.000.D** codifies it: *"a minimum citywide tree canopy cover goal of 35 percent by
   2036, with a no net loss of 32.4 percent canopy cover based on 2021 imagery."*

### Three defects in that chain

**(a) An assumption is presented as a measurement.** The label "2024 analysis" describes a number the
consultant explicitly declined to call a 2024 measurement. City staff elsewhere conceded it is "most
likely based on older imagery."

**(b) The decline is method-driven, not necessarily tree-driven.** 32.4% (PlanIT Geo, AI/ML, assumed)
is compared against 34.6% (SavATree/UVM, LiDAR + imagery, measured) to assert canopy loss. Different
vendor, different sensor stack, different method, different year. PlanIT Geo's own companion whitepaper
concedes the point: *"Exact tree canopy percentages vary based on the data source. Timing and
methodologies of studies is not consistent."*

**(c) A denominator change is embedded in the record.** Davey divides canopy by **total city area
including 402 acres of open water** (1,844 ÷ 6,095 = 30.3%). SavATree divides by **land area, water
excluded**. Applying SavATree's convention to Davey's own 2015 canopy gives 1,844 ÷ 5,693 = **32.4%** —
numerically identical to the figure now in draft code. This is almost certainly coincidence, since
PlanIT Geo documents a different provenance, but it demonstrates the magnitude of the problem: a ~2-point
swing is available purely from choosing a denominator, with no tree gaining or losing a leaf.

**Goal year: 2036**, per both the packet record and the draft code text. A "35% by 2045" figure appears
in search-engine summaries of My Edmonds News coverage; the primary record does not support it. Treat
2045 as garbled.

---

## Report entries

### 1. Urban Tree Canopy Assessment — Davey Resource Group, 2017/2018
`2018_davey_urban-tree-canopy-assessment.pdf` · cover 2017, file stamped 2018-03-08 · prepared for
Shane Hope, Development Services

- **Data:** high-resolution color-infrared aerial imagery, USDA Farm Service Agency, flown **2015-08-07**
  (leaf-on). NAIP imagery used as the accuracy reference image.
- **Method:** object-based image analysis (OBIA), semi-automated feature extraction via **Feature
  Analyst**, an ArcGIS extension clustering by spectral and spatial/contextual traits. Canopy layer
  extracted first to limit shadow loss; small individual trees hand-digitized as buffered points;
  final edit at **1:2000**, QA/QC at **1:1500**.
- **Accuracy:** full protocol present — random plots, blind assessment against NAIP, confusion matrix,
  four metrics (overall accuracy, kappa, quantity disagreement, allocation disagreement). **Producer's
  accuracy 89.87%.** This is the only Edmonds canopy report with a fully documented accuracy assessment.
- **Numbers:** 6,095 ac total city area; **1,844 ac canopy = 30.3%**; 2,080 ac impervious; 402 ac water;
  1,651 ac potential planting area. Max potential canopy 57%.
- **The 2005 figure (32.3%) is a different animal:** estimated with **i-Tree Canopy — 1,000 random points
  dropped on a 2005 Google Earth image and classified by eye.** Davey states plainly it is "not
  considered as accurate as the percentages from the UTC." The 2005→2015 "loss of 114 acres" therefore
  compares an eyeball point-sample to a mapped extraction. The UFMP carried this comparison forward
  anyway, and elsewhere mislabels the year as 2004.

### 2. Urban Forest Management Plan — Davey Resource Group (with Nature Insight Consulting), July 2019
`2019_davey_urban-forest-management-plan.pdf`

- 20-year plan, horizon **2038**. Benchmarks canopy at **30.3%**, inherited wholesale from the 2018 UTC
  Assessment — it performs **no independent measurement**.
- Goal 1 "maintain or enhance citywide canopy"; Goal 1B "no net loss." **Contains no 35% target and no
  2036 date.** Both are later inventions.

### 3. Tree Canopy Assessment 2015–2020 — SavATree Consulting Group + UVM Spatial Analysis Lab, Feb 22 2022
`2022_savatree-uvm_tree-canopy-assessment-2015-2020.pdf`

- **Data:** imagery from **2015 and 2020**, plus **LiDAR acquired 2017**. Sources: City of Edmonds,
  Snohomish County, State of Washington, USDA, USGS.
- **Method:** automated feature extraction integrated with detailed manual review. The decisive
  difference from Davey is **LiDAR 3D height data**, which resolves trees from spectrally similar
  shrubs and recovers canopy lost to shadow — the report says so explicitly. Land cover classes: tree
  canopy, grass/shrub, bare soil, water, buildings, roads/rail, other impervious. Methods developed
  with USDA Forest Service; compute via Gund Institute / VACC.
- **Denominator:** existing canopy = canopy ÷ **land area, which excludes water**. Stated explicitly.
- **Numbers:** **34.3% (2015) → 34.6% (2020)** (both verified in document text), net **+17.6 ac** over
  five years — i.e. essentially flat. 1,427 ac Possible-Vegetation (~25% of land base), 995 ac of it
  single-family lawn. 10 of 28 watersheds lost canopy; Lund's Gulch most treed at >70%.
- **Accuracy: none stated in the document.** The word "accuracy" appears exactly once in the whole
  report, and only rhetorically — "LiDAR... enhances the accuracy of the mapping." There is no
  confusion matrix, no sample, no reported error rate. This matters because **34.6% is the figure the
  2024 Comprehensive Plan adopted** (Goal LU-26), and because a +17.6 acre change over 1,900+ acres is
  well inside the margin an unquantified classifier could produce. The "slight increase" may not be
  distinguishable from noise, and the report provides no way to tell.
- **Note:** its 2015 figure (34.3%) and Davey's 2015 figure (30.3%) describe **the same year** and differ
  by 4 points. That gap is pure method-and-denominator. It is the cleanest available proof that these
  reports cannot be chained into a trend.
- Press repeatedly cites 34.6% as a "2023" number. It is **2020**.

### 4. A Forecast Analysis of Possible Planting Scenarios — PlanIT Geo, Inc., Jan 2026
`2026-01-28_planning-board-packet_planitgeo-forecast.pdf` (packet; report at ~p.117)

- **Data:** stated as 2024, footnoted as **an assumption based on 2021 canopy data**. The underlying
  full 2024 PlanIT Geo UTC assessment is cited but **not published anywhere** — see gaps below.
- **Method: not stated in the delivered memo.** This is itself the finding. The document reports a
  canopy figure without describing how it was produced. The vendor's companion whitepaper (Attachment 2
  to the same packet) advertises a general AI/ML partially-automated canopy product on a two-year
  subscription, but that is marketing collateral describing PlanIT Geo's offerings in general — **it is
  not a methods statement for Edmonds**, and nothing in the record ties it to the 2021 data behind
  32.4%. The actual method is unavailable to the public because the parent 2024 assessment is
  unpublished. No accuracy assessment.
- **Numbers:** UTC **32.4% / 1,855 ac**; PPA 26.8%; unsuitable 36.8%. Models 20-year planting
  scenarios (2024–2044) via "Canopy Calculator." Recommends a goal **range of 31–38%**.
- The adopted 35% sits inside that recommended range; the 32.4% floor is its lower anchor.

**Vendor-published fact sheet — added 2026-08-17.** `planitgeo_edmonds_factsheet.pdf`, 3 pp, InDesign
2024-07-25, from PlanIT Geo's public website. A shorter, earlier edition of the same work (**four**
scenarios; the packet version has five). It resolves several open questions and adds new material:

- **Denominator confirmed:** 6,091 total ac / **5,725 land ac** / 42,593 residents. 1,855 ÷ 5,725 =
  32.40%. Land basis, water excluded.
- **Same assumption footnote**, verbatim — so the caveat is not an artifact of the packet edition.
- **Still no method statement and still no accuracy figure.** The core finding is unchanged: neither
  published document says how the canopy was mapped.
- **Scenario outcomes (to 2044):** business-as-usual 170 trees/yr → **31%, a 1-point loss**; maintain
  220/yr → 32%; attainable +2% 325/yr → 34%; aggressive +4% 425/yr → 36%. **The city's own consultant
  projects canopy decline under current practice.**
- **Canopy Calculator assumptions:** 20-yr horizon; 4% new-tree mortality; 2% annual canopy loss to
  mortality; **29 ac/yr canopy loss to development**; 0.5% natural regeneration; 0.5% annual canopy
  growth; crown-size mix 10% small (12.5 ft), 25% medium (15 ft), 65% large (30 ft).
- **Plantable land by ownership:** private 1,293 ac (31% of PPA), ROW 197 ac (18%), **city public only
  26 ac (13%)** — and city property is **95% used in every scenario including business-as-usual.**
  Independent confirmation of the private-land ceiling from the city's own consultant.
- **Land use:** Single Family Residential is >75% of city land, ~80% of tree cover (1,425 ac), and
  ~90% of plantable area (1,529 ac). Open Space has the highest coverage rate at 70%. Corroborates the
  NOAA zone analysis (79%) from an independent source.
- **90% of canopy overhangs pervious surfaces; only 10% over impervious** — relevant to heat/stormwater
  benefit arguments.
- Cites Edmonds' 2:1 replacement policy (ECDC 23.10.080) and the Green Streets Guide depaving strategy
  as the levers for reaching goals.
- **Internal inconsistencies to avoid quoting loosely:** narrative text says "maintain" needs 4,425
  trees at 325/yr while Table 1 says 4,398 at 220/yr; narrative says aggressive needs 8,540 at 427/yr
  while Table 1 says 8,499 at 425/yr. Land-use areas sum to 5,675 ac / 1,850 ac canopy, slightly off
  the 5,725 / 1,855 headline. Prefer Table 1 and the headline figures.

**Correction to earlier note in this dossier:** the planting-scenario summary is *not* packet-only —
a version has been public on the vendor's site since July 2024. What remains unpublished is the
**parent 2024 UTC assessment** that the summary is built on. The records-request rationale is
unchanged and arguably sharpened: the conclusion is public, the work behind it is not.

### 5. Tree Canopy Contribution by Zone Type: Edmonds, WA (2021) — unattributed, Feb 2026
`2026-02_noaa-2021-utc_canopy-by-zone-type.pdf` · 2 pages · found at
`C:\Users\Kameron\Documents\Edmonds Urban Tree Canopy Analysis.pdf`, Acrobat export dated 2026-02-17

**Provenance unknown — verify before citing.** No author, title metadata, or issuing body. It was not
found by any of the four discovery agents and is not published on any city channel; it surfaced on the
local machine. It may be CAB-produced, self-produced, or received from a third party. **Pin down who
made it before using it publicly.**

- **Data:** NOAA's **2021 Urban Tree Canopy model**. Zoning polygons from the City of Edmonds GIS site.
- **Method:** zonal statistics — canopy as a percentage of **land area** per zoning district.
- **Headline:** *"As of 2021, 33.27% of Edmonds is covered by the tree canopy."*
- **Canopy distribution by zone (percent of total canopy):** Low-Density Residential **79%**;
  Public Use 10%; Multiple Residential 5%; General Commercial 2%; Open Space 2%; Master Plan Mixed-Use
  1%; all remaining zones <0.5%.

**Why this document matters — two independent reasons:**

**(a) It contradicts the number in draft code, on the same year.** PlanIT Geo's 32.4% is footnoted as
"an assumption based on **2021** canopy data." This is an actual 2021 measurement, and it reports
**33.27%** — nearly a full point higher, and on the land-area denominator. Either PlanIT Geo used a
different 2021 source, a different boundary, or adjusted the value downward. The figure being written
into ECDC 17.130 as a no-net-loss floor is the *lower* of the two 2021-vintage numbers. Since the
parent PlanIT Geo assessment is unpublished, the discrepancy cannot currently be reconciled from public
documents — which strengthens the case for the records request.

**(b) It quantifies the private-land ceiling.** 79% of Edmonds' canopy is on Low-Density Residential
land; Public Use and Open Space together hold 12%. This is direct, independent support for the ceiling
argument: the city cannot move the citywide percentage materially through public planting, because the
canopy is overwhelmingly in private yards. It corroborates the SavATree finding that 995 of 1,427
plantable acres are single-family lawn.

**Caveat on the source model:** NOAA-derived canopy products have documented bias issues in developed
land (see pre-2017 section — Nowak & Greenfield 2010 on NLCD). 33.27% is not automatically more correct
than 32.4%; it is *another method*. The point is not that one is right, but that Edmonds now has six
canopy percentages spanning 30.3–34.6% with no method-consistent series among them.

### 6. Per-permit arborist reports (document class, not catalogued individually)
Site-specific reports filed with development permits, under the city's public-notices path. Example:
PLN2021-0024, 8929 220th St SW. These are tree-level, not canopy-level, and are useful only as ground
truth samples — not as canopy measurements.

---

## Denominator normalization — putting all figures on one basis

The published numbers use two different denominators. This section converts them to a single
**land-area basis (water excluded)** so the remaining differences are attributable to method alone.
Land basis is chosen because every source except Davey already uses it.

**Base quantities** (all from Davey 2018 UTC, the only report publishing a full land-cover budget):
total city area **6,095 ac**, open water **402 ac**, therefore **land area = 5,693 ac**;
2015 canopy **1,844 ac**.

**Validation:** 1,844 ÷ 6,095 = 30.25%, which reproduces Davey's published 30.3%. The land base and
numerator are therefore correct as used by Davey.

| Year | Source | As published | Basis used | **On land basis** | Method |
|---|---|---|---|---|---|
| 2005 | Davey i-Tree | 32.3% | total | **~34.6%** ⚠ see caveat 2 | 1,000 points by eye |
| 2015 | Davey | 30.3% | total | **32.4%** | OBIA / Feature Analyst |
| 2015 | SavATree/UVM | 34.3% | land | 34.3% | LiDAR + imagery |
| 2020 | SavATree/UVM | 34.6% | land | 34.6% | LiDAR + imagery |
| 2021 | NOAA UTC model | 33.27% | land | 33.27% | zonal statistics |
| "2024" (2021 data) | PlanIT Geo | 32.4% | land (implied) | 32.4% | assumption, method unstated |

### The twin-2015 test — decomposing the gap

Davey and SavATree both measured **2015**. Any difference between them is definitionally error, not
canopy change, which makes this the cleanest available decomposition:

| | Davey 2015 | SavATree 2015 | Gap |
|---|---|---|---|
| As published | 30.3% | 34.3% | **4.0 pts** |
| Both on land basis | 32.4% | 34.3% | **1.9 pts** |

**Denominator accounts for 2.1 pts. Method accounts for 1.9 pts.** Roughly half the discrepancy
between Edmonds' only two genuine measurements is not about trees — it is about whether 402 acres of
Puget Sound count as part of the city. The residual 1.9 pts is the real method difference, and its
direction is expected: LiDAR height data recovers canopy that spectral-only classification loses to
shadow and confuses with shrubs, so the LiDAR study should read higher.

### Anticipated objection: "so is the code's 32.4% just Davey's 2015 number restated?"

Normalizing Davey's 2015 measurement to the land basis produces **32.4%** — numerically identical to
the figure in draft ECDC 17.130. A hostile reader will ask whether the city simply recycled a
decade-old measurement. **The answer is no, and the reason should be stated plainly rather than
left for someone else to find:**

- **The numerators differ.** Davey maps **1,844 ac** of canopy; PlanIT Geo reports **1,855 ac** —
  11 acres apart. Identical percentages from different acreages means different underlying data,
  not a restatement.
- **PlanIT Geo documents a different provenance** — 2021 canopy data, not 2015 imagery.

So the coincidence is real but it is a coincidence. Its evidentiary value is not "the city reused an
old number"; it is that **a ~2-point swing is available from denominator choice alone**, which is why
the figures circulating in the public debate cannot be read as a trend. Do not overclaim this.

### Side result: PlanIT Geo appears to be on the land basis

**CONFIRMED 2026-08-17.** PlanIT Geo's published fact sheet (`planitgeo_edmonds_factsheet.pdf`, dated
2024-07-25, from the vendor's own site) states the base quantities outright: **6,091 total acres,
5,725 land acres.** And 1,855 ÷ 5,725 = **32.40%**, reproducing the published figure exactly.

**32.4% is a land-area figure, water excluded** — the same convention as SavATree, the opposite of
Davey. This was previously inferred from the acreage; it is now documented. (Prior inference: implied
denominator ~5,725 ac. Correct.)

Note the boundary differs slightly from Davey's: PlanIT Geo counts 6,091 total / 366 water, Davey
6,095 total / 402 water — a 36-acre disagreement about how much of Edmonds is water. Immaterial at
this precision, but it means the two land bases (5,725 vs 5,693) are not identical.

On that reading, 32.4% is **directly comparable to NOAA's 33.27%** for the same 2021 vintage. That
~0.9 pt gap has no denominator explanation available; it is method, or it is the undocumented
adjustment inside the unpublished parent assessment.

### Caveats — read before using these conversions

1. **SavATree's land base is corroborated by its own internal figures.** The report never states its
   land acreage directly (totals live in figure graphics, not extractable text), but it does state:
   *"With over 1,427 acres of land, comprising nearly 25% of the city's land base falling into the
   Possible-Vegetation category."* Back-calculating, 1,427 ÷ 0.25 ≈ **5,708 ac** — within **0.3%** of
   Davey's 5,693 ac land area. Checked the other way, 1,427 ÷ 5,693 = **25.07%**, which matches
   "nearly 25%" exactly. **The two studies are working from effectively the same land base**, so the
   twin-2015 decomposition below is not resting on an assumption.
   (Note: back-calculating from the +17.6 ac net change instead is *not* viable — the percentages are
   rounded to one decimal, admitting land bases from ~4,400 to ~8,800 ac. Use the 1,427 ac route.)
2. **The 2005 rescale (~34.6%) is the weakest number in this dossier and should not be used.** It
   assumes i-Tree's 1,000 points were distributed across total area including water, which is plausible
   but unverified. The source figure was itself eyeballed off a Google Earth image with no accuracy
   assessment. It is shown only to demonstrate that the direction of Davey's reported 2005→2015 decline
   survives normalization (−2.2 pts normalized vs −2.0 pts as published), not as a usable value.
3. **NOAA's denominator comes from zoning polygons**, not the Davey land budget. Zoning coverage may
   not sum exactly to the municipal land area.
4. **Normalization does not create a time series.** It removes one of three incompatibilities.
   Sensor, algorithm, and accuracy rigor all still differ. Two of the six figures have no accuracy
   assessment at all and one is not a measurement. Harmonized numbers are more honestly *comparable*;
   they are not *equivalent*.

**Reproduce:** land = 6,095 − 402 = 5,693. To convert a total-basis figure to land basis, multiply by
6,095 ÷ 5,693 = 1.0706. To go the other way, multiply by 0.9341.

---

## Pre-2017: there is no earlier canopy measurement (searched 2026-08-16)

**Edmonds has no canopy measurement of any kind before 2017.** The Davey 2017/2018 UTC Assessment is
genuinely the city's first. This is a searched negative, not an untested assumption.

**What does exist, and why none of it is a measurement:**

- **1983 Street Tree Plan → 2002 → 2006 → 2015 Streetscape Plan.** The oldest Edmonds tree document
  found. Per the Oct 23 2002 Planning Board minutes (consultant Terry Reckord, MacLeod Reckord), the
  2002 plan was "basically an update of the 1983 Street Tree Plan," recommending "specific species and
  their locations." Resources did not permit citywide work, so it **covered only the downtown bowl** —
  a board member observed "ninety-nine percent of the content focuses on the downtown area." Its only
  map assigns functional use-zones to downtown streets from **field observation**. No inventory, no
  tree count, no canopy percentage. A design document, not a measurement.
  Minutes: `.../Planning Board Minutes Archive/pb021023f.pdf`; merged 2015 doc:
  `.../Planning Division/Streetscape_Plan_and_Street_Tree_Plans_2015.pdf`
- **No public tree inventory has ever existed.** The 2019 UFMP states it plainly: *"no comprehensive
  public tree inventory exists,"* and the City "does not maintain data about these trees as a
  collective inventory of their green infrastructure assets."
- **Tree City USA designation began 2011** (Tree Board created 2010, ECC Ch. 10.95), so there is no
  1990s/2000s annual reporting that could contain tree counts.
- **Snohomish County** UTC reporting starts **2014** and covers unincorporated area only, explicitly
  excluding cities like Edmonds. County tree canopy code (SCC 30.25.016) dates to 2014.
- **No academic study** (UW, WSU) used Edmonds as a canopy study site. UW work in the window is
  Seattle-focused or landscape-scale.

**Regional datasets that covered Edmonds but never published an Edmonds number** — data existed, an
Edmonds figure was derivable, nobody derived one:

| Dataset | Epochs | Why not an Edmonds measurement |
|---|---|---|
| American Forests, *Regional Ecosystem Analysis: Puget Sound Metropolitan Area* (1999) | 1972, 1996 | Landsat sub-pixel; published breakouts are regional or Seattle-only (15% 1972, 10% 1996 for Seattle). Print-only report; no suburb table evidenced in citing literature. |
| NOAA C-CAP | 1992, 1996, 2001, 2006, 2011 | 30m regional land cover; summaries published at county/watershed scale |
| NLCD Percent Tree Canopy | 2001, 2011 | national raster; MRLC distributes rasters, not municipal tables |
| UW Urban Ecology Research Lab | 1986–2007 (6 epochs) | land-use/land-cover classes, not canopy %; no municipal breakouts |
| USGS Puget Lowland Ecoregion | 1973–2000 | ecoregion-scale forest %, not municipal |

**Methodological caution if any of these are ever used as a historical anchor:** Nowak & Greenfield
(2010) found NLCD 2001 tree canopy underestimated developed-land canopy by 13.7% nationally, and
Richardson & Moskal (2014, *UFUG* 13:152–157) document the same underestimation problem in the American
Forests Landsat sub-pixel method for Seattle. A number recovered from these products would not be
comparable to the Davey/i-Tree/LiDAR figures without correction.

**Instructive parallel:** Seattle's widely-repeated "40% canopy in 1972" has no clear source, and
Richardson & Moskal speculate it may be a misapplied borrowing from the American Forests regional
report. That is structurally identical to Edmonds' 32.3%-in-2005 — a figure generated elsewhere,
retrofitted to a city and a year, then cited as history. Both cases argue for stating provenance
whenever a historical canopy number is used.

**Residual uncertainty (one stone unturned):** whether the print-only American Forests 1999 Puget Sound
report contained a suburb-by-suburb table including Edmonds. Nothing in the citing literature suggests
it did. Resolving it requires an interlibrary or American Forests archive request. Low expected value.

---

## Gaps and unresolved items

- **The full 2024 PlanIT Geo UTC assessment is missing.** It is the parent of the number now being
  written into ECDC 17.130 and it appears nowhere on edmondswa.gov, the CivicLive CDN, the PrimeGov
  portal, or a Wayback CDX sweep of 3,673 archived city document URLs. Only the derivative forecast
  summary is public — in two editions (vendor fact sheet Jul 2024, packet attachment Jan 2026), neither
  of which states a method or an accuracy figure. **This warrants a public records request** — the methodology, imagery date, and
  accuracy of the binding baseline are currently unavailable to the public.
- **No post-2022 measured re-assessment exists.** The Urban Forest Planner described future LiDAR
  flyovers plus ground truthing as planned, not delivered.
- **No pre-2017 study exists.** The 2005 number is a retrospective 2017 estimate, not a contemporaneous
  report.
- **No standalone public street-tree inventory exists.** The UFMP recommends field inventory as
  still-needed work; none was found published.
- **Regional products covering Edmonds, not extracted:** TNC/Davey Central Puget Sound UTC (2022, all 77
  municipalities, WA DNR open data portal) and American Forests Tree Equity Score. Both are ArcGIS/API
  gated; Edmonds-specific values not pulled. Worth a second pass if an independent third-party number
  would be useful.
- The city's **Tree Code Updates page is now "under construction"** with its document list removed;
  archived snapshots exist but Wayback playback was rate-limiting during this sweep.

---

## Relevance to this project

**Edmonds has no canopy measurement for the entire 2000s decade** — nothing exists before the 2017
Davey study (see pre-2017 section). For roughly the first seventeen years of the pipeline's 2000–2024
span there is no municipal figure to compare against, because none was ever produced. The pipeline is
not improving on a bad historical series; for that period it would be creating the only one.

The pipeline's value proposition is also visible in the comparison table: the city has never had a
method-consistent canopy time series. Six numbers, five methods, two denominators, one of them an
undocumented assumption now headed into binding code. A single classifier applied uniformly across
18 imagery years 2000–2024 produces the first internally comparable series Edmonds would have — which
is precisely the thing the current record cannot supply.

Per the project's honest-measurement principle: the pipeline's own output will need its denominator
stated explicitly (land vs. total area) and its accuracy assessed, or it becomes the fifth
incomparable number rather than the fix.
