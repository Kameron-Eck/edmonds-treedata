# QC script audit — phase4_qc_* / phase4_build_corrected_labels.py

Scope: phase4_qc_ndvi.py, phase4_qc_score.py, phase4_qc_indep.py,
phase4_qc_forest_misses.py, phase4_qc_site.py, phase4_qc_flicker.py,
phase4_build_corrected_labels.py. All read fully.

Overall: NDVI band order (R,G,B,NIR; band index `nir=4`) is applied
**consistently** across every script that computes NDVI — no NIR/Red swap found.
The CHM DN→metres formula `(dn-1)*0.2, dn==0→nodata` round-trips correctly
against the documented `DN = 1 + round(height_m/0.2)` and is consistent across
all 5 files that touch CHM. Division-by-zero is guarded everywhere via
`_safe()`/`_pct()` helpers. Streaming/block-read pattern is used throughout —
no whole-raster loads found. The one substantive class of bug is CHM-nodata
handling in the *reference builder* (finding 1), which is a real violation of
the CLAUDE.md invariant ("areas outside CHM coverage must be nodata, not
height 0") and is corroborated by contrast with `phase4_build_corrected_labels.py`,
which gets the identical situation right.

---

## Finding 1 — CHM-nodata leaks in as "short" (height 0), not IGNORE/nodata
**File:** `phase4_qc_ndvi.py:169` and `:191`
**Severity:** HIGH  **Confidence:** HIGH
**Category:** nodata masking / domain-invariant violation

```python
166   height = dn_to_height_m(chm_dn)            # NaN where no CHM
...
169   tall = np.nan_to_num(height, nan=-1.0) >= min_height_m
170   canopy = veg & tall
```
and in the threshold sweep:
```python
191   cm = vmask & (np.nan_to_num(height, nan=-1.0) >= hm)
```

`dn_to_height_m` correctly turns CHM DN=0 (nodata) into `NaN` (`phase4_qc_ndvi.py:115`).
But immediately before the "is this pixel tall" test, `nan_to_num(..., nan=-1.0)`
converts that NaN to -1, which is `< min_height_m` for any positive threshold —
functionally identical to "treat missing CHM as height 0/short". CHM covers only
**~60% of the city** (per CLAUDE.md), so for the remaining ~40%, real vegetated
(NDVI-positive) pixels can *never* be classified `canopy(2)` in the reference —
they are silently downgraded to `grass(1)` regardless of true height. There is
no IGNORE/uncertain bucket for "vegetated but no CHM data" in the 4-class output
(`0/1/2/255`).

**Why this is real, not a nit:** CLAUDE.md states explicitly: *"Areas outside
CHM coverage must be handled as nodata, NOT as height 0."* This code does
exactly the forbidden thing. Downstream impact is direct and mechanical:
- `phase4_qc_score.py` and `phase4_qc_site.py` score model recall/precision
  against `ndvi_ref_{year}.tif`. In the ~40% of the city without CHM, any real
  canopy the model correctly detects gets counted as `FP_grass` (ref says
  grass, model says canopy) — **precision is punished for being right**, and
  that same canopy never enters the recall denominator (`ref_canopy`), so the
  headline "honest recall" number is a recall-vs-partial-reference number, not
  recall vs. all real canopy.
- This is silent — nothing in `ndvi_ref_{year}.txt` reports what fraction of
  "grass" pixels are actually "vegetated, no-CHM" vs. true short grass.

**Corroboration this is a slip, not an intentional design choice:**
`phase4_build_corrected_labels.py:190-197` handles the *identical* situation
correctly — it computes `has_chm = ~np.isnan(height)` and gates every
height-based test on it (`add = green & has_chm & (h_fill >= min_height_m)`),
so pixels without CHM are simply left "no change" rather than misclassified as
short. The reference-builder script (`phase4_qc_ndvi.py`) is the one place
this pattern was dropped.

**Fix sketch:** add a `has_chm = ~np.isnan(height)` mask; either (a) emit a 4th
non-nodata class (e.g. `3 = vegetated, height unknown`) and exclude it from
both the canopy reference *and* the recall/precision denominators downstream,
or (b) at minimum, report in the `.txt` summary what fraction of `grass`-class
pixels lack CHM coverage so the bias is visible and auditable. The sweep
accumulator (`sweep_can`, line 191) needs the same fix.

---

## Finding 2 — grid-match check omits the affine transform
**File:** `phase4_qc_score.py:109-111`
**Severity:** MEDIUM  **Confidence:** MEDIUM
**Category:** CRS/reprojection alignment

```python
108   with rasterio.open(ref_path) as ref, rasterio.open(prob_path) as prob:
109       if (ref.width, ref.height) != (prob.width, prob.height) or str(ref.crs) != str(prob.crs):
110           raise ValueError(f"grid mismatch: ref {ref.width}x{ref.height}/{ref.crs} "
111                            f"vs prob {prob.width}x{prob.height}/{prob.crs}")
```

This "same grid" guard checks width, height, and CRS, but never the
**affine transform** (origin/pixel size). Two rasters can have identical
width/height/CRS yet different origins or pixel sizes (e.g. a half-pixel or
one-tile offset from a re-tiled/re-exported prob raster) — the guard would
pass and the script would then do a raw per-pixel `ref.read(...)` vs.
`prob.read(...)` window comparison assuming pixel `[i,j]` in one is the same
ground location as `[i,j]` in the other. A misalignment here silently
corrupts every TP/FN/FP count with no error raised.

**Fix sketch:** also assert `ref.transform == prob.transform` (or compare
`ref.bounds`/`ref.res` within a small epsilon), and fail loudly on mismatch.

---

## Finding 3 — CHM aligned via naive index-resize, not reprojection
**File:** `phase4_qc_site.py:109-122` (`read_chm_window`) and `:164-165`
**Severity:** MEDIUM-HIGH  **Confidence:** MEDIUM
**Category:** CRS/reprojection alignment

```python
109 def read_chm_window(bounds_wgs84, ref_crs):
110     """CHM (EPSG:3857) reprojected/read for a WGS84 window, returned in metres."""
...
164    chm = read_chm_window(bounds, None)
165    chm = _resize_to(chm, shp) if chm is not None else None
```

Unlike every other script that combines CHM with imagery/prob
(`phase4_qc_forest_misses.py:230-237`, `phase4_build_corrected_labels.py:173-176`
— both use `WarpedVRT(chm_path, crs=..., transform=...)` to properly reproject
CHM onto the target grid), `phase4_qc_site.py` reads CHM as an independent
window in **its own native CRS/resolution** (floor/ceil-rounded to its own
pixel grid) and then force-fits it to the RGB window's array shape with
`_resize_to`, a pure index-proportional nearest-neighbor stretch — not a
georeferenced reprojection. If CHM's CRS differs from the imagery's CRS (the
docstring says CHM is EPSG:3857; nothing here confirms imagery shares that
CRS), or even if same CRS but different native resolution/origin snapping,
the two independently-rounded windows do not necessarily cover the exact same
ground extent, and the stretch will misregister CHM against RGB/prob/ref by
some sub-window fraction. This numbers feed directly into the printed
recall/precision and the FN-by-height cross-tab (`_crosstab_fn`), i.e. this is
not just a cosmetic panel — the height-bin attribution can be measurably off
near stand edges.

**Fix sketch:** replace `read_chm_window` + `_resize_to` with a `WarpedVRT`
against the RGB/prob raster's own CRS+transform+shape (same pattern as
`phase4_qc_forest_misses.py`), so all four layers (RGB, prob, ref, CHM) are
pixel-exact.

---

## Finding 4 — reference-nodata fallback can misclassify sentinel nodata as a real group
**File:** `phase4_qc_indep.py:263-266`
**Severity:** MEDIUM  **Confidence:** MEDIUM
**Category:** nodata masking (edge case, reference-agnostic path)

```python
263    codes = np.clip(rc.astype(np.int64), 0, 255)
264    gid = lut[codes]
265    if ref_nodata is not None and 0 <= int(ref_nodata) < 256:
266        gid[rc == ref_nodata] = ignore_id
```

The explicit nodata-masking line only fires when the reference's nodata value
is itself in `[0,255]`. For a reference raster using an out-of-range sentinel
(e.g. `-9999`, common for int16 land-cover/DEM-derived rasters), `np.clip`
silently folds those nodata pixels to code `0` before the mask check ever
sees the real nodata value, so they get bucketed into whatever group code `0`
maps to. For the built-in `CCAP_DEFAULT` map, code 0 happens to be `"ignore"`,
so C-CAP usage is safe by coincidence — but the script is explicitly
advertised as **"reference-agnostic"** (works with "hand-drawn canopy polygons
or photo-interp points rasterized elsewhere", `--ref-map` override), and for
a user-supplied reference/`--ref-map` where code 0 is a real class (or absent,
falling to `"other"`), out-of-range nodata would be silently scored as real
land cover instead of excluded.

**Fix sketch:** check/mask `ref_nodata` on `rc` *before* the `np.clip`, not
after (i.e. build the ignore mask from the raw `rc` values, independent of the
256-clamp used only for the LUT lookup).

---

## Finding 5 — convoluted/self-cancelling nodata==0 logic in the binary-scheme branch
**File:** `phase4_qc_indep.py:254-261`
**Severity:** LOW  **Confidence:** HIGH (verified net-correct, but fragile)
**Category:** style / correctness-adjacent

```python
254    if ref_scheme == "binary":
255        gid = np.full(pr.shape, names.index("other"), dtype=np.int16)
256        gid[rc > 0] = names.index("canopy")
257        if ref_nodata is not None:
258            gid[rc == ref_nodata] = ignore_id
259        gid[rc == 0] = names.index("other")
260        if ref_nodata == 0:
261            gid[rc == 0] = ignore_id     # 0 was nodata, not 'other'
```

Line 259 unconditionally overwrites whatever line 257-258 assigned at
`rc==0` back to `"other"`, and then line 260-261 re-applies `ignore_id` only
if `ref_nodata==0`. The net result is correct in both branches (verified by
hand-tracing both `ref_nodata==0` and `ref_nodata!=0` cases), but the
sequence is confusing and one dead/self-cancelling assignment (259 vs
257-258 when `ref_nodata==0`) makes this fragile to future edits (e.g. adding
a third nodata-adjacent case would be easy to get wrong given the current
ordering). Not currently producing wrong output.

**Fix sketch:** compute nodata mask once (`nodata_mask = (rc == ref_nodata) if ref_nodata is not None else np.zeros_like(rc, bool)`), then `other`/`canopy` assignment, then `gid[nodata_mask] = ignore_id` last, unconditionally.

---

## Finding 6 (style/DRY) — `deployed_threshold()` / `resolve_prob()` duplicated 3x
**Files:** `phase4_qc_score.py:74-95`, `phase4_qc_indep.py:126-153`,
`phase4_qc_forest_misses.py:128-140` (deployed_threshold only; forest_misses
has its own smaller prob-resolution logic in `main()`/`run_compare()`)
**Severity:** LOW  **Confidence:** HIGH
**Category:** maintainability nit (not a correctness bug)

Same channel-preference logic (`"rgb+chm", "rgb+struct", "rgb"`) and CSV
column names (`op_thresh`/`best_f1_thresh`) copy-pasted verbatim across
files. A future change to the eval-CSV schema (new column name, new channel
tag) has to be remembered in 3 places; a fix applied to one silently leaves
the others stale. Not urgent (scripts explicitly documented as "standalone"),
but worth a shared helper module if these scripts are touched again.

---

## Finding 7 (minor inefficiency) — per-block list-comprehension rebuild
**File:** `phase4_qc_indep.py:284`
**Severity:** LOW  **Confidence:** HIGH
**Category:** inefficiency (negligible in practice)

```python
284   prim = valid & np.isin(gid, [names.index(g) for g in primary_groups])
```
`[names.index(g) for g in primary_groups]` is recomputed every block
iteration inside the main loop, even though `primary_groups` is fixed for the
whole run. Cost is trivial (`len(primary_groups)` `O(n)` list lookups per
block, `primary_groups` has ≤3 elements) — not worth fixing unless touching
this code anyway; listed for completeness only.

---

## Things checked and found CLEAN (no bug)
- NDVI band order (`R,G,B,NIR`, NIR = band 4) consistent in
  `phase4_qc_ndvi.py`, `phase4_qc_site.py`, `phase4_qc_forest_misses.py`,
  `phase4_build_corrected_labels.py`.
- CHM DN↔metres formula (`(dn-1)*0.2`, `dn==0→nodata`) consistent and
  round-trips correctly against the documented encoding, in all 5 files that
  touch CHM.
- Categorical reference resampling is `Resampling.nearest` in both
  `phase4_qc_indep.py` and `phase4_qc_forest_misses.py` (correct — avoids
  blending land-cover codes).
- CHM resampling is also `nearest` even though CHM is continuous — this is
  the *correct* choice here (bilinear would blend real height values with the
  `0`=nodata sentinel at coverage edges, corrupting heights near boundaries).
- `phase4_qc_score.py` confusion-matrix construction (TP/FN/FP_grass/FP_nonveg/TN)
  is mutually exclusive/exhaustive over the `valid` mask; recall/precision
  formulas are correctly `TP/(TP+FN)` and `TP/(TP+FP)`.
- `phase4_qc_indep.py` nested canopy-definition construction
  (`canopy_definitions()`) correctly builds the cumulative
  forest_only ⊆ forest_wetland ⊆ forest_wetland_scrub nesting.
- `phase4_build_corrected_labels.py` ADD-ONLY invariant is correctly enforced:
  base array starts at `0` (no-change), only ever writes `1` (add) or `2`
  (ignore), "add wins over ignore" is deliberate and documented, and the
  holdout-strip logic correctly reverts additions/ignores to `0` without
  touching `255` (nodata).
- `phase4_qc_flicker.py` false-canopy-fraction and per-parcel std/flicker
  math is straightforward and correctly guarded against empty-parcel and
  <2-year cases.
- Division-by-zero guarded everywhere via `_safe()`/`_pct()` (or histogram
  `max(..., 1)` denominators) — no unguarded divisions found.
- All scripts stream in `block_rows`-sized windows; no whole-raster loads.
