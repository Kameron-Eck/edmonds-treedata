# Imagery QC — findings, 2026-08-24

Branch `work/20260824-qc`. QC of all 43 held rasters after the 2026-08-23/24 acquisition campaign
(29 new files, 5 replacements, catalog 19 → 36 entries). Two planes measured independently: the
local D: originals and the Google Drive data lake (via a Colab CPU VM reading Google's servers,
not the local cache). Tools: `qc/imagery_qc_suite.py` (6 checks), `qc/imagery_canopy_separability.py`,
`qc/separability_index_control.py`, `qc/investigate_2024_offset.py`. All CSVs in `phase4/qc/`.

**Nothing here changes the catalog or the data.** QC measures; decisions are Kam's.

---

## 1. The finding that changes what the campaign was worth

**Resolution buys essentially nothing for canopy detection. The NIR band is the entire advantage.**

Measured as AUROC of a per-pixel greenness index against the 2020 canopy mask, 40 seeded citywide
locations, 60 m boxes, all rasters resampled to one common 50 cm grid. The raw ranking is
confounded (4-band files get NDVI, 3-band get ExG, and NDVI is simply the stronger index), so
`separability_index_control.py` recomputes **both indices on the same pixels** to separate the effects:

| effect | measurement |
|---|---|
| sensor resolution → separability | **Spearman −0.036** (n=36) — no relationship |
| ≤10 cm files | median ExG AUROC **0.737** (n=12) |
| ≥60 cm files | median ExG AUROC **0.759** (n=7) — *coarser scores slightly higher* |
| being a 4-band product, scored on ExG | +0.013 — negligible |
| **actually using the NIR band** | **median +0.099** (range −0.008 … +0.159, n=10 paired) |

The three 3-inch years — 91 GB of download — land mid-pack (2020s 0.790, 2022s 0.752, 2024s 0.735)
**below 1 m NAIP files** (2017n 0.855, 2015n 0.842). The 2020 anchor itself scores 0.790, mid-pack.
Best like-for-like is 2017_naip at 0.855; the floor is `1996_snoh_1m_rgb` at 0.551 (d = −0.02,
essentially no canopy signal) and `1936_king_pan` at 0.466, below chance.

**The honest limit of this claim.** AUROC of a *per-pixel index* measures how separable canopy is by
colour alone. It cannot see texture, crown shape or context — exactly what a CNN uses fine resolution
for, and exactly what per-crown instance delineation needs. So the correct reading is: **for
pixel-level canopy *detection*, resolution is not the lever and NIR is; for crown *delineation*, this
measurement says nothing.** It does not retroactively make the 3-inch acquisitions a mistake — it
says they should be justified by delineation, not by detection.

**And NIR is not a guaranteed win**: `2017_naip_1m_rgbi` scores −0.008 with NDVI (NDVI *worse* than
plain ExG), `2015_naip` gains only +0.011. The mechanism deserves a look before NIR is assumed
universally superior.

## 2. Seasonality is measurable, and it is large

2015 is the clean natural experiment — two acquisitions of one year, both 3-band, so the same index
scores both and every caveat about the mask cancels:

| | AUROC |
|---|---|
| `2015_king_rgb` (Feb–Mar, leaf-off) | **0.6415** |
| `2015_snoh_1ft_rgb` (Aug 7, leaf-on) | **0.7867** |
| difference | **+0.145** |

The NIR values tell the same story independently: forest NDVI runs 0.84 (2021n, mid-July) down to
0.42 (2023n, October) — **October acquisitions carry roughly half the vegetation signal of July ones**.

This bears directly on the standing under-prediction problem. Every non-2020 year borrows the 2020
labels; where an acquisition is leaf-off, the label says "canopy" over pixels that carry little
evidence for it, which is the regime that teaches a model to under-predict. Leaf state now has a
number attached to it per acquisition.

## 3. `2024_coe_rgb.tif` is displaced by ~1.28 m

The city and county copies of 2020 and 2022 are the same pixels twice (r 0.995 / 0.996, offset
0.00 m at every site). 2024 is not: a **1.29 m offset, systematic to 0.03 m across five scattered
sites**. Two experiments settle what that means (`investigate_2024_offset.py`):

- **Same imagery?** Yes. Removing the shift lifts correlation from 0.682 to **0.985**.
- **Which file moved?** The city's. `2024_coe` sits **1.28 m** from both 2020 reference files;
  `2024_snoh_3in` sits **0.17 m** from both. Control: `2022_coe` vs `2020_coe` = **0.004 m**, so the
  city product line is normally aligned to millimetres.

**Consequence:** for anything positional in 2024 — per-crown work above all — use `2024_snoh_3in_rgb.tif`
(key `2024s`), or shift-correct the city copy. A 1.28 m error is ~17 px at 7.6 cm and would move
every crown.

### The rest of the cross-registration table

All 20 same-year pairs, graded on whether the five sites *agree* (see §7.1). Ten pairs earn a
verdict; ten are inconclusive because the sites disagree — reported as such rather than averaged
into a number that would look authoritative and mean nothing.

| grade | pair | median offset | site spread |
|---|---|---|---|
| OK | 2020_coe ↔ 2020_snoh_3in | 0.00 m | 0.00 |
| OK | 2022_coe ↔ 2022_snoh_3in | 0.00 m | 0.00 |
| OK | 2019_naip ↔ 2019_snoh | 0.07 m | 0.03 |
| OK | 2021_king ↔ 2021_snoh_6in | 0.15 m | 0.04 |
| OK | 2021_naip ↔ 2021_snoh_6in | 0.42 m | 0.17 |
| OK | 2017_naip ↔ 2017_snoh | 0.58 m | 0.11 |
| OK | 2002_snoh ↔ 2002_usgs | 0.74 m | 0.05 |
| OK | 2017_coe ↔ 2017_snoh | 0.88 m | 0.21 |
| **WARN** | **2024_coe ↔ 2024_snoh_3in** | **1.29 m** | **0.01** |
| **WARN** | **2013_king ↔ 2013_snoh_1m** | **2.76 m** | **0.41** | (investigated → inconclusive, below) |

**Clean bill for the campaign's own georeferencing**: every pair of campaign-acquired files sits
sub-metre with tight agreement (2019n↔2019s 0.07 m, 2021n↔2021s 0.42 m, 2017n↔2017s 0.58 m,
2002s↔2002u 0.74 m).

**2013 was investigated and the answer is "we cannot tell" — not a finding.** `2013_king` vs
`2013_snoh_1m` reads 2.76 m (spread 0.41), so it was put through the same triangulation
(`qc/investigate_displacement.py`, generalised from the 2024 work) against four reference files.
The first run returned a confident "2013_snoh is displaced" — from inputs whose site spreads were
**2.1, 5.0, 9.0 and 14.8 m**, all larger than the 2.76 m question being asked. Cross-*year*
triangulation at 1 m resolution, across six to eight years of real change, simply does not have the
signal. The tool now applies the same agreement gate as the cross-registration summary, and with it
**0 of 4 references on either side survive → INCONCLUSIVE**.

*Positive control for that gate* (otherwise a gate that rejects everything proves nothing): re-run
on the 2024 pair against the 2020 and 2022 county files, **2 of 2 references survive** (spreads
0.07–0.27 m) and it independently reproduces `2024_coe_rgb.tif is displaced`, 1.27 m vs 0.26 m. The
gate discriminates; it does not merely refuse.

The ten NOISY pairs all involve either a King County web-Mercator cache product or a cross-season
comparison; those are exactly the cases where a per-pixel correlation has least to lock onto.

## 4. Data integrity: the strongest evidence we have, plus one real gap

**Byte verification (Drive plane, run on the VM against `MANIFEST.sha256` computed from the D:
originals): 220 files, 60.4 GB, 0 mismatches, 0 size errors.** Every campaign raster that has
reached Google's servers is byte-identical to its local original. This check had never been run —
mirrors were only ever size-verified.

**A defect in the acquisition engine, found and fixed.** `acquire_imagery.do_mirror` used a
non-recursive `glob("*")`, so **subdirectories of a source dir were never mirrored**. The
consequence: the **39 original USGS HRO source tiles** — the delivered government product, the
reason 2002 became a replacement — sat single-copy on D: with no data-lake backup, while
`MANIFEST.sha256` listed all 45 entries as though they were there. Fixed to `rglob` (relative paths
preserved, `chunks` still excluded); the 12 acquisition tests still pass; all 39 tiles are now
mirrored.

**"Mirrored" did not mean "in the cloud."** The VM sees the three 3-inch rasters as *absent* from
Drive: the ~61 GB that reported `rc=0` today is still uploading through the local cache. The mirror's
size-verify compares against that cache, so **it structurally cannot detect this**. Not a corruption
— but the lake is not complete until the uploads drain, and no Colab work can use those files yet.

**Files with no data-lake copy at all:** `1936_king_pan.tif`, `1998_king_pan.tif` — single-copy on D:.

## 5. Clean bills

- **NIR identity: 10/10 pass.** Every four-band file has forest NDVI well above parking NDVI, so the
  band order the engine assumes (R,G,B,NIR) is correct in all of them and every "NIR" band is real.
- **Integrity: 0 failures** across 38 locally-resident rasters. 27 fully clean.
- **Radiometry: 2 files flagged of 42** (210 file-site rows). `2000_king_rgb` clips 6–7% high in
  bands 1 and 3 at the parking site; `1936_king_pan` is degenerate (below).
- **Drive-side integrity: 25/25 campaign rasters** open with correct bands/CRS/GSD and varying data.

## 6. Other findings worth a decision

- **11 files have no overview pyramid** — every one a pre-campaign King County file
  (2000/2005/2007/2009/2013/2015/2019/2021/2023_king, both King pans) plus the CoE orthos. Every
  campaign-acquired raster has overviews. This is not cosmetic: a "decimated" read of an
  overview-less 48 GB ortho touches every byte, which is what caused today's disk incident (§7).
  Building overviews on these would make all future QC and tiling dramatically cheaper.
- **`1936_king_pan.tif` is ~90% padding**: 37% value 0, 38% value 253, 15% value 255, leaving ~10%
  real photographic content — and **all five reference sites land in blank padding**. It contributes
  nothing to any site-based analysis.
- **Interior-gap check flags 3 files**: `2001_snoh_1ft_pan` (251 ha), `2000_king_rgb` (71 ha),
  `1990_snoh_10ft_pan` (67 ha) — all old scanned products. These numbers come from a rule corrected
  minutes earlier (§7) and have **not been visually confirmed**; treat as "needs eyes", not as fact.
- **Duplication across 20 same-year pairs** confirms the campaign's provenance claims by measurement:
  `2019_naip` ↔ `2019_snoh` r = **0.970**, independently corroborating that both came from the same
  Hexagon 2019-10-11 flight — a date that had been argued from filenames and footprint layers.

## 7. Corrections to my own method (recorded so they are not repeated)

Four, all caught by a number that looked wrong rather than by review:

1. **Cross-registration confidence.** A first pass gated on correlation *peak height* ≥ 50 and
   discarded **54 of 100 measurements**, including valid ones. Peak height measures how *alike* two
   images are, not whether the offset is *right*, so it punished genuinely different seasons.
   Replaced with **agreement between sites**: a real georeferencing offset is systematic (2024 agreed
   to 0.03 m across five sites), a wrong correlation peak is idiosyncratic (the 18–24 m forest
   outliers agreed with nothing).
2. **Shift-correction sign error.** Correcting the 2024 shift made correlation *worse* (0.68 → 0.53),
   which is backwards. A synthetic test with a known (17, −9) px shift showed the negation was
   missing: as fixed, r recovers to **1.0000**. Had this gone unchecked the reported verdict would
   have been the opposite of the truth — "different acquisitions" instead of "same imagery,
   mis-georeferenced".
3. **Padding detection over-fired.** Treating any DN over 20% of the frame as padding mis-read
   `2009_snoh`, whose most common value is 40 — a legitimate dark-vegetation tone — inventing a
   41 ha interior gap. Requiring padding to be *extreme* (≤2 or ≥250) as well as dominant fixed it:
   2009 moved to 0.74 ha and its valid fraction from 0.78 to 0.98.
4. **Full-extent reads of Drive-resident files are hazardous.** Reading a Drive file pulls every byte
   into the local DriveFS cache, which lives on D: — the disk holding every original. The integrity
   pass over overview-less CoE orthos drove D: free down **0.4–0.6 GB/min**, about an hour from
   filling. Killing that one job recovered 24.8 → 36.2 GB within minutes. Encoded as `--local-only`,
   with the narrower true rule documented: full-extent reads are dangerous, windowed reads are fine.

## 8. Suggested next steps (for Kam — nothing here has been actioned beyond the fixes noted)

1. **Use `2024s` for positional work in 2024**, not `2024_coe`; or shift-correct the city copy by the
   measured 1.28 m.
2. **Build overviews on the 11 legacy files** — cheapest single win for all future QC and tiling cost.
3. **Weight the NIR years** in any retraining. The separability numbers say they carry the signal.
4. **Treat leaf-off acquisitions as a distinct regime** when borrowing 2020 labels; the +0.145 AUROC
   gap between 2015 leaf-off and leaf-on is a measured lower bound on what season costs.
5. **Confirm the three interior-gap flags visually** before acting on them.
6. Optional: investigate why NDVI *underperforms* ExG on `2017_naip`.
7. 2013 needs a *same-epoch* reference to resolve (a third 2013-or-adjacent acquisition), not more
   cross-year triangulation — that avenue is measured out.
