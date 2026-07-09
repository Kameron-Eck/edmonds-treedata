# Infra audit — make_positive_site.py / make_grass_negatives.py / fetch_build_chm.py / fetch_be_build_struct.py / pipeline_config.py / pipeline_log.py

Scope: read in full. `py -3.12 -m py_compile` clean on all six. Cross-checked pipeline_log.py
consumers via grep across the whole Scripts/ tree (10+ call sites in phase1*/phase2*/phase3*/phase4*).

---

## pipeline_log.py (SHARED INFRA — every phase script)

### 1. `write_step_log()` bypasses `finish()`'s exception guard — SEVERITY: HIGH, CONFIDENCE: HIGH
`pipeline_log.py:233-235`
```python
logger = StepLogger(script, step, logs_dir, capture_stdout=False)
logger._t0 = datetime.datetime.now()
logger._write(datetime.datetime.now(), 0.0, errors, notes, fields, stdout_text)
```
This calls `StepLogger._write()` **directly**, not `StepLogger.finish()`. `finish()` wraps
`_write()` in `try/except Exception` specifically so a log-writing failure "cannot crash a
running pipeline step" (module docstring, line 39-40; this is also the literal function named
in CLAUDE.md rule 2). `write_step_log()` has no such guard — any failure inside `_write()`
(disk full, permission error on the Drive mount, a bad `notes`/`fields` type, or the
UnicodeEncodeError in finding #3 below) propagates uncaught out of `write_step_log()` and
crashes the caller, exactly the failure mode the module exists to prevent.
**Currently dead code**: grep confirms no script in Scripts/ imports `write_step_log` from
`pipeline_log` — every consumer (phase1*/phase2*/phase3*/phase4*) uses the `StepLogger`
class + `.finish()` instead. So blast radius today is zero, but it is the API shown first in
the module's own docstring (lines 33-37) and is the literal name CLAUDE.md rule 2 uses
("Every script `write_step_log()`s..."), so it will very plausibly be reached for by a future
script or session.
**Fix**: make `write_step_log()` a thin wrapper that goes through `finish()`'s try/except (e.g.
factor the `try/except Exception: print(...)` out of `finish()` into a small helper both paths
call, or simply have `write_step_log()` call `logger.finish(errors=errors, notes=notes, **fields)`
after manually stuffing `stdout_text` into `notes`/a dedicated field).

### 2. Field-label column glues key to value when key ≥ 11 chars — SEVERITY: MEDIUM, CONFIDENCE: HIGH (confirmed firing in production logs today)
`pipeline_log.py:178`
```python
lines.append(f"{key:<11}{v_str}")
```
`f"{key:<11}"` only **pads to a minimum width of 11** — it does not guarantee a separating
space. Any `key` whose underscore→space form is already ≥ 11 characters long gets zero
whitespace before its value, producing unreadable glued text, e.g.
`manifest_items=14476` → `"manifest items14476"` (no space). Confirmed real, not
hypothetical: `phase1c_review.py:1723` calls
`log.finish(crowns=len(gdf), manifest_items=len(manifest), errors=0)` — `"manifest_items"` is
14 chars, so every log this produces has `manifest items` glued directly to the count. The
module's own docstring (lines 116-117) lists `manifest_mb` and `output_path` as "Common
keys" — both are exactly 11 chars and would also glue with zero separator. `phase4_semantic_finetune.py`
also merges arbitrary `dict` results from `step_*()` functions into `**_f` (lines 3896-3945),
so any future long key from those dicts hits the same bug.
**Fix**: `f"{key:<11} {v_str}"` (explicit space) or widen the field to the longest expected
key + 1, or use `f"{key}: {v_str}"` unconditionally.

### 3. Fallback error-print is itself unguarded against the failure class it exists to catch — SEVERITY: MEDIUM, CONFIDENCE: MEDIUM
`pipeline_log.py:139-142` and `:191`
```python
try:
    self._write(t1, elapsed, errors, notes, fields, stdout_capture)
except Exception as e:
    print(f"  ⚠ pipeline_log: failed to write log — {e}", flush=True)
```
and inside `_write()`:
```python
print(f"  ✓ log → {path}", flush=True)
```
Both prints use non-ASCII glyphs (✓ U+2713, ⚠ U+26A0). On Windows, when stdout is not a
real UTF-8 console — e.g. output redirected/piped, or a non-UTF8 codepage without
`PYTHONUTF8=1` (CLAUDE.md only mandates `PYTHONUTF8=1` for the `py_compile` step, not for
running the scripts) — `print()` of these characters can raise `UnicodeEncodeError`. If that
happens inside `_write()`'s trailing print, it's caught by the `except Exception` above and
degrades gracefully — but the fallback print at line 142 that reports the failure uses the
same glyph class (⚠) with **no protection of its own**. If the environment can't encode ✓ it
generally can't encode ⚠ either, so the fallback handler can raise the very exception class it
was written to swallow, propagating out of `finish()` and violating "failures are printed but
never raise." Medium confidence because it depends on console/redirection encoding, which
wasn't independently verified live.
**Fix**: wrap the fallback print itself in `try/except`, or use ASCII-only markers
(`"OK"`/`"WARN"`) in this module since it is infra code whose robustness matters more than
cosmetics.

### 4. Same-minute re-run silently clobbers the previous log — SEVERITY: LOW, CONFIDENCE: HIGH
`pipeline_log.py:145-147`, `190`
`_log_path()` timestamps to the minute (`%Y-%m-%dT%H-%M`) and `_write()` calls
`path.write_text(...)` (always overwrite, no existence check). Re-running the same
`--step` twice within 60s (common during interactive debugging) silently destroys the first
run's log with no warning. Not a crash, but a real idempotency/history-loss gap given the
project relies on these logs as the durable record of what ran (CLAUDE.md rule 2).
**Fix**: append a disambiguating suffix (`_2`, `_3`, ...) or use second-resolution timestamps.

### 5. `start()` called twice without an intervening `finish()` leaves stdout permanently wrapped — SEVERITY: LOW, CONFIDENCE: MEDIUM
`pipeline_log.py:96-102`. `_Tee.__init__` captures `original = sys.stdout` at construction
time. If `start()` is invoked twice back-to-back (e.g. a bug in caller control flow, or reusing
one `StepLogger` instance across two `--step`s), the second `_Tee` wraps the *first* `_Tee`
as `original`. `finish()` only restores `sys.stdout = self._tee.original`, which is now the
first Tee, not the real terminal stdout — real stdout is never restored. Edge case, not
currently hit by any observed call site (all call sites use one `StepLogger`/`with` block per
step), but worth a guard (`assert self._tee is None` in `start()`).

Otherwise pipeline_log.py is solid: the `_finished` idempotency guard on `finish()` is
correctly implemented and well-commented; `write_text(..., encoding="utf-8")` for the actual
log *file* is correct and avoids the Windows-cp1252 trap (issue #3 only affects the terminal
print, not the file contents); `_Tee.__getattr__` forwarding is correct.

---

## fetch_build_chm.py

### 6. `--max-height` CLI flag is a no-op above its own default — SEVERITY: MEDIUM, CONFIDENCE: HIGH
`fetch_build_chm.py:85-86, 143-146`
```python
ap.add_argument("--max-height", type=float, default=MAX_H_M, ...)   # MAX_H_M = 50.6
...
h_m = np.clip(np.where(valid, acc, 0.0), 0.0, args.max_height)
dn = (1 + np.round(h_m / M_PER_DN)).astype(np.int32)
out[valid] = np.clip(dn[valid], 1, 254).astype(np.uint8)
```
`h_m` is clipped to `args.max_height` first, but the encode step re-clips `dn` to `[1, 254]`
regardless — `254` decodes back to exactly `253*0.2 = 50.6 m`. So raising `--max-height`
above 50.6 (e.g. `--max-height 80` for an unusually tall conifer stand) changes nothing: any
real height in (50.6, 80] m still saturates at DN 254 = 50.6 m, silently. The flag only ever
lowers the effective ceiling, never raises it above the hardcoded U8 encoding range.
**Fix**: either derive `M_PER_DN` from `args.max_height` (`M_PER_DN = args.max_height / 253`)
so the full DN range always spans the requested ceiling, or clearly state in `--help` that the
ceiling is capped at 50.6 m and the flag can only lower it.

### 7. `src_nodata=src.nodata` trusts the STAC asset's nodata tag — SEVERITY: LOW, CONFIDENCE: LOW (unverified against live data)
`fetch_build_chm.py:129-132`. If a `3dep-lidar-hag` COG doesn't carry a `nodata` tag (or
mistags it), `reproject()` would treat sentinel/fill values as real height data, silently
polluting the accumulated HAG mosaic. Not verified against a live asset; flagged for
awareness only. The rest of the HAG→U8 encoding (nodata=0 sentinel, `0.2 m/DN`, clip to
valid range, "keep first valid" accumulation) is internally consistent and matches the
docstring exactly — no other CHM-build correctness issues found.

### 8. No Colab `-f`/`.json` argv filter — SEVERITY: LOW, CONFIDENCE: MEDIUM
`fetch_build_chm.py:87` calls `ap.parse_args()` directly on `sys.argv`. CLAUDE.md rule 4 says
"every `main()` filters" the Colab `%run` `-f <json>` injection. This script's own docstring
only documents `!python fetch_build_chm.py` (not `%run`), so it may never actually receive
that argv shape — but it is a literal deviation from the stated blanket rule, and inconsistent
with `make_positive_site.py`, which does filter (line 216) despite also being a local-run
script. Would crash under `%run` if ever invoked that way.

---

## fetch_be_build_struct.py (documented superseded/dead script — CLAUDE.md Drive Layout: "older struct experiments (superseded)")

### 9. Vertical strip offsets use the x-resolution pixel size — SEVERITY: LOW, CONFIDENCE: MEDIUM
`fetch_be_build_struct.py:47-57`
```python
px = (fr_bounds.right - fr_bounds.left) / W       # x-resolution only
...
top = fr_bounds.top - r0 * px
bot = fr_bounds.top - r1 * px
```
`px` is derived purely from width/x-extent and then reused to convert *row* indices into a
*y*-coordinate offset for each strip's bbox. If the reference raster's y-resolution differs
from its x-resolution (non-square pixels), each strip's requested bbox is mis-sized
vertically, causing the exported strip to be stretched relative to the true fr grid before the
final exact-grid reproject "fixes" it via resampling — introducing sub-pixel vertical error
per strip. In practice lidar hillshade rasters are usually square-pixel, so this likely doesn't
bite, but it's an unstated assumption. Low priority given the file is superseded.

### 10. `MemoryFile` objects never explicitly closed — SEVERITY: LOW, CONFIDENCE: MEDIUM
`fetch_be_build_struct.py:74-78`. `m2 = MemoryFile(); ... srcs.append(m2.open())` — only the
*dataset* opened from `m2` is later `.close()`d (line 82); the `MemoryFile` wrapper itself is
never closed, relying on GC. Minor resource leak, dead-code priority.

### 11. Final `reproject()` call has no explicit nodata — SEVERITY: LOW, CONFIDENCE: LOW
`fetch_be_build_struct.py:86-90`. No `src_nodata`/`dst_nodata` passed; relies on `be` being
pre-zeroed and reproject only touching covered pixels. Works in practice but is implicit;
would be clearer with explicit `dst_nodata=0`. Dead-code priority.

---

## make_positive_site.py

### 12. `src` raster reopened a second time just for `.crs`, handle leaked — SEVERITY: LOW, CONFIDENCE: HIGH
`make_positive_site.py:97-123`
```python
with rasterio.open(src) as s:
    ...
    prof = s.profile.copy()          # prof["crs"] already has the CRS
    ...
return out, arr, footprint_bounds, str(rasterio.open(src).crs)   # <-- reopened, never closed
```
The first `with rasterio.open(src) as s:` block already captured everything needed
(`prof["crs"]` == `s.crs`). Line 123 opens `src` **again** solely to read `.crs`, and the
resulting `DatasetReader` is never closed (no `with`, no `.close()`) — a real, trivially
avoidable file-handle leak, worse on a network Drive mount where repeated GDAL
open/close cycles are more expensive.
**Fix**: `return out, arr, footprint_bounds, str(prof["crs"])`.

### 13. Crown area computed in EPSG:3857 (Web Mercator) — ~2.2x area inflation at this latitude — SEVERITY: MEDIUM, CONFIDENCE: MEDIUM
`make_positive_site.py:146-148`
```python
gdf = gpd.GeoDataFrame(geometry=geoms, crs=mask_crs).to_crs(CROWN_CRS)   # CROWN_CRS = "EPSG:3857"
gdf["area_m2"] = gdf.geometry.area
gdf = gdf[gdf["area_m2"] >= float(min_area_m2)].reset_index(drop=True)
```
EPSG:3857 is Web Mercator — a conformal, **not equal-area**, projection whose area scale
factor is `1/cos²(lat)`. At Edmonds' latitude (~47.8°N), that's `1/cos²(47.8°) ≈ 2.22`, i.e.
`gdf.geometry.area` here reports roughly **2.2x the true ground area** of every derived crown
polygon. Two concrete effects: (a) `--min-area-m2` (default 3.0) is actually filtering at
~1.35 true m², about 2.2x more permissive than the flag name/help text implies; (b) the
printed "canopy area X ha" (lines 171, 189-190) overstates real hectares by ~2.2x. Medium
confidence because it's unverified whether downstream consumers (phase4 tiling/training)
ever read `area_m2` for anything beyond this filter/print — if it's display-only + a loose
filter threshold, actual training impact is limited, but the numbers reported to a human
reviewer (the whole point of the staging/preview workflow) are quantitatively wrong.
**Fix**: compute `area_m2` after `to_crs` to a local UTM zone (EPSG:32610, UTM 10N) or any
other equal-area/equidistant CRS appropriate for Puget Sound, then reproject geometries to
`CROWN_CRS` for storage only.

### 14. Preview title hardcodes "(2015 imagery)" regardless of actual crop source — SEVERITY: LOW, CONFIDENCE: HIGH
`make_positive_site.py:90, 183`
```python
CROP_SRC_CANDIDATES = ["2015_king_rgb.tif", "2020_coe_rgb.tif", "2016_snoh_rgbi.tif"]
...
ax[0].set_title(f"{name} — footprint (2015 imagery)", fontsize=11)
```
`resolve()` picks the first candidate that exists in `IMAGERY_DIRS`, which may resolve to
`2020_coe_rgb.tif` or `2016_snoh_rgbi.tif` if the 2015 file is missing from both the local
D:\ mirror and Drive — but the preview title always says "(2015 imagery)" unconditionally.
A reviewer using this title to sanity-check the derived crowns against the pictured imagery
would misjudge which year's imagery is shown.
**Fix**: use the actual resolved `src.name`/year instead of the hardcoded string.

### 15. No Colab `-f`/`.json` filter question — not applicable / already handled
`make_positive_site.py:216` — this one **does** filter (`filtered = [a for a in sys.argv[1:] ...]`), correctly, unlike `make_grass_negatives.py` (see below). Included here only to note the inconsistency across the two sibling scripts.

Otherwise clean: `derive_crowns()`'s window math (bounds→window→intersection with full
raster) is correct and handles out-of-raster gracefully via `RuntimeError` on empty geoms;
`commit()`'s existence checks are correct; `buffer(0)` geometry repair is a reasonable
approach though it runs *after* the area filter (so the filter/print use un-repaired
geometry, a minor ordering nit, not flagged as a separate item).

---

## make_grass_negatives.py

### 16. No Colab `-f`/`.json` argv filter — SEVERITY: LOW, CONFIDENCE: MEDIUM
`make_grass_negatives.py:92` — `args = ap.parse_args()` with no filtering, same class of
issue as fetch_build_chm.py finding #8. The module docstring documents `!python
make_grass_negatives.py` (not `%run`), so likely dormant, but is a literal deviation from
CLAUDE.md rule 4 and inconsistent with `make_positive_site.py`.

### 17. `--commit` with zero site names silently "succeeds" — SEVERITY: LOW, CONFIDENCE: HIGH
`make_grass_negatives.py:89, 94-103`. `nargs="*"` means bare `--commit` (no names) yields
`args.commit == []` (not `None`), so the commit branch runs, the loop body never executes,
and it prints "Committed 0 grass negative site(s)." — a silent no-op rather than a usage
error. Cosmetic/UX only.

`crop_site()`'s bounds check (line 78-80) only tests whether the box **center** is inside the
source raster's bounds, not the whole box — but since the read is `boundless=True,
fill_value=0`, out-of-bounds portions are deliberately zero-filled rather than erroring, so
this is working as designed, not a bug. Everything else (staged-dir workflow, montage
preview, `--commit` copy-then-print-next-step) is correct and matches its own docstring.

---

## pipeline_config.py

No bugs found. Pure path/catalog definitions; `_catalog_key()`/`raw_path()`/
`registered_path()`/`get_available_registered()` logic all checked against
`IMAGERY_CATALOG`/`SOURCE_CODES`/`TARGET_YEARS`/`SUPPLEMENTAL_YEARS` and is internally
consistent — string star-keys, standalone-band keys, and the base-year (2020, never
registered) special case are all handled correctly. This file is Colab-only by its own
docstring (hardcoded `/content/drive/MyDrive/treedata`), which matches how it's actually
used (imagery registration, run on Colab) — the absence of a `G:\` local fallback (unlike
`make_positive_site.py`/`make_grass_negatives.py`) is intentional, not a gap.
