# Imagery Alignment, Characterisation and Recipe Plan

**Opened 2026-08-19.** Companion to `WORKPLAN_2026-08-19.md` (which covers the model and the
measurement work). This one covers the *inputs*: getting every acquisition lined up,
documenting what each one actually is, and testing our way to a defensible common recipe.

**Why now.** Every cross-year claim this project has made has been confounded by something
about the imagery that nobody had measured — nominal GSD that was wrong by up to 6×, a
colour cast that drifts .80 → .11 across the King series, footprints that differ by 2×,
recipes whose effect varies in *sign* by year. We have been comparing models when much of
the variance was in the pictures. This plan fixes the inputs before any more modelling.

**The uncomfortable possibility this plan exists to test.** The single labelled year, 2020,
sits **fourth-lowest of 18 in scene greenness**. If that is phenological rather than
radiometric, then the hand labels were drawn on imagery where deciduous canopy was least
visible — which would *manufacture* the conifer-only blind spot, and every coarse year
taught from that mask inherits it. That would make the project's central defect an artefact
of one acquisition date. It is currently **untestable** because no raster carries a date.

---

## Phase A — Inventory: establish what we actually have

Nothing here is modelling. It is finding out what is on disk and making one place tell the
truth about it.

### A1. Resolve the catalog conflict *(blocking — do first)*

Two files both claim to be the imagery catalog and they disagree. The one whose comment says
"single source of truth" is the wrong one: it contains no pre-2013 year at all, so
`raw_path(2000)` raises `KeyError`. This breaks the one-fact-one-home rule directly.

**Do:** pick `phase4seg/config.py: YEAR_CATALOG` as authoritative (it is what the engine
reads), reduce the other to a pointer, and add a test that every catalog entry resolves to a
file that opens.

### A2. Adopt or reject the orphans

On disk, not in the catalog, not used by anything:

| file | status | disposition |
|---|---|---|
| `1936_king_rgb.tif` | **empty shell** — uniform 253/0 fill, King County survey does not reach into Snohomish | **delete or quarantine.** It is not imagery |
| `1998_king_rgb.tif` | real, **single-band**, whole-city, same grid as 2000 | keep; candidate panchromatic pilot, but see A4 |
| `2017_king_rgb.tif` | real, 14.93 cm — **a second, different 2017** | **keep — this is the experiment**, see C1 |
| `2012_king_rgb.tif` | real, on Drive, uncatalogued | assess and adopt or archive |

### A3. Fix the filename lie

`1936` and `1998` are **single-band** despite `_rgb` filenames. Any tool that assumes three
bands from the name will silently misread them. Rename to `_pan`, or record band count in the
catalog and have loaders assert it.

### A4. Acquisition dates — the biggest missing variable

**No raster in this project carries an acquisition date.** Phenology and sun angle have
therefore been uncontrolled across all 18 acquisitions and every cross-year comparison. The
literature is blunt that leaf-off imagery *underestimates* canopy in deciduous regions, and
that seasonality is the single largest error source where leaf-on/off contrast is strong.

**Do:** recover dates from the source archives (King County, Snohomish County, NAIP, City of
Edmonds) and write them into the catalog. NAIP is leaf-on by specification and anchors the
scale. **Until dates exist, no phenology claim in this project is testable** — including the
2020-label hypothesis above, which is the one that matters most.

### A5. One home for the pixels

Training (Colab) reads Drive; local QC prefers `D:\edmonds-pipeline\Imagery` and falls back to
Drive. `native/` is empty so everything silently resolves to the Drive root. Document the
resolution order in one place and make both paths assert they opened the file they intended.

---

## Phase B — Characterisation: measure every acquisition the same way

The goal is one table, one row per acquisition, every column **measured from the file** rather
than copied from a config. Two of these instruments already exist and were re-verified today.

| property | instrument | status |
|---|---|---|
| CRS, transform, bounds, dtype, nodata | `phase4_data_inventory.py` | **built** |
| footprint as % of study area | `phase4_data_inventory.py` | **built** |
| true ground GSD (unit-safe) | `phase4_data_inventory.py` | **built** |
| **effective** resolution (edge response) | `litwatch_scratch/q138b.py` | **built, verified** |
| per-band radiometry + colour cast | `litwatch_scratch/cast2.py` | **built, verified** |
| band count, fill/constant detection | — | **to add to the inventory** |
| overviews present | — | **to add**, and see B2 |
| acquisition date | — | blocked on A4 |

### B1. Merge the instruments into one report

Fold effective resolution and colour cast into `phase4_data_inventory.py` so a single run
produces the whole table. Add the band-count and constant-fill checks, which would have caught
the empty 1936 file and the `_rgb` mislabels automatically.

**Deliverable:** `phase4/qc/imagery_inventory.csv` — the one table, regenerable, in git.

### B2. Build overviews *(cheapest win available)*

**No raster in this project has overviews**, so every decimated read silently reads the entire
multi-GB file. This is why full-raster QC runs take 30–60 minutes each. `gdaladdo` on the
orthos and the reference rasters will speed up every QC tool here, permanently.

### B3. Characterise, don't just tabulate

Two numbers per year that the table above will not give you on its own:

- **Oversampling ratio** = effective ÷ nominal. Already known for 11 years: 1998 **6.1×**,
  2005 **4.0×**, 2000 **2.8×**, the rest 1.26–1.42×. Extend to all acquisitions.
- **Radiometric distance** from a chosen anchor, per sensor era — the quantity any
  normalisation has to close.

---

## Phase C — Tests: earn the common recipe

Only now does modelling make sense, and each test below is designed so a **negative result is
still informative**.

### C1. The matched 2017 pair — the experiment nobody has run

`2017_king_rgb.tif` (14.93 cm) and `2017_coe_rgb.tif` (7.46 cm) are **the same ground in the
same year from two different sources**. That removes canopy change, season and sun angle
*simultaneously* — every other cross-source comparison in this project is confounded by all
three. It is the cleanest natural experiment available, and it is free.

**Measure:** the CoE-vs-King domain gap directly, after matching resolution. This is exactly
the quantity per-(sensor × era) anchors are supposed to absorb, and until now it could only be
inferred from clustering.

**Then test each candidate normalisation on the pair**, in increasing order of commitment:

1. per-image mean/std matching
2. per-image **saturation and channel balance** (the specification the 2015 colour-contrast
   finding produced — brightness matching provably does nothing for 2015)
3. histogram matching to an anchor
4. frequency-domain amplitude swap (FDA)

**Success criterion, stated in advance:** a normalisation succeeds if the model's output on
the King image converges toward its output on the CoE image over the same ground. The pair
gives us that comparison with no reference product in the loop at all.

### C2. Is the softness ours?

Every King file is EPSG:3857, and reprojection to Web Mercator is itself a blurring resample.
2000 is 2.8× oversampled and 2005 is 4.0×. **If our own mosaicking introduced that, then
native-projection sources recover real detail that no retraining can.** Compare a
native-projection source tile against our reprojected copy on the same ground. Cheap, and the
payoff is high enough to run before any further modelling on the early years.

### C3. What actually explains the 2000/2002 deficit?

Three explanations have now failed — nominal GSD, spectral sharpness, effective resolution.
Remaining candidates: scanned film versus digital capture, compression artefacts, a different
contractor's processing chain, or genuinely different canopy. **Three failures is a signal to
stop guessing and look at the imagery.** Pull matched crops from 2000, 2002 and 2005 over the
same ground and inspect them side by side before proposing a fourth hypothesis.

### C4. The phenology test *(blocked on A4)*

Once dates exist: correlate scene greenness against acquisition date **within a single sensor
era**, so the colour cast cannot masquerade as phenology. Then answer the question that
matters — was the 2020 labelling imagery leaf-off, and did that create the conifer bias?

**Do not** run any cross-sensor greenness comparison. The cast drifts .80 → .11 across the
King series from processing alone, which is larger than any plausible phenological effect.

---

## Order of work

| # | task | needs | why this order |
|---|---|---|---|
| 1 | A1 catalog conflict | local | everything downstream reads it |
| 2 | A2/A3 orphans + band lies | local | stops silent misreads |
| 3 | B2 overviews | local | makes every later step faster |
| 4 | B1 merged inventory | local | the table the rest depends on |
| 5 | C2 is the softness ours | local | may change what "resolution" means before we model it |
| 6 | A4 acquisition dates | **external** — archives | long lead time, start early, blocks C4 |
| 7 | C1 the 2017 pair | Colab | the experiment; needs 1–4 done |
| 8 | C3 look at 2000/2002 | local | after C2, which may explain it |
| 9 | C4 phenology | blocked on A4 | the highest-stakes question |

**Rules carried in from what went wrong before:** measure from the file, never the config;
never compare greenness across sensors; hold recipe constant or the comparison is void; and
re-score rather than reason when a result surprises you — three "surprising reversals"
dissolved that way this week.
