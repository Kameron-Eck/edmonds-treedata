# Audit: phase4 viz / QA / review tools

Scope: phase4_viz.py, phase4_qa_overlay.py, phase4_threshold_diagnostic.py,
phase4_sentinel_snap.py, phase4_label_review.py, phase4_label_review_prep.py.
All read in full. Cross-checked mask/prob raster provenance against
phase4_semantic_finetune.py (step_inference / step_postproc / _operating_threshold)
and CHATLOG.md where relevant.

---

## 1. [HIGH][conf: HIGH] phase4_qa_overlay.py:156-164, 213-218 — "same grid" check only compares width/height, never transform/CRS; crop panels silently drop the overlay with no warning on mismatch

```
156 def read_window_band(path, win, ortho_wh):
157     """Read the same geographic window from a mask/prob raster of the same grid."""
158     with rasterio.open(path) as src:
159         # If the raster shares the ortho grid, the window indices line up directly.
160         if (src.width, src.height) != ortho_wh:
161             # Different grid → reproject the window by bounds instead of indices.
162             return None, src.nodata
163         a = src.read(1, window=win, boundless=True, fill_value=255)
164         return a, src.nodata
```

- **What's wrong:** "Same grid" is verified only by `(width, height) == ortho_wh`. Two
  rasters can have identical pixel dimensions yet different `transform`/`crs` (shifted
  origin, different real-world extent) — the check passes, the function reads window
  `win` (computed from the ortho's own transform) directly against the mask/prob
  raster's pixel grid, and the overlay is drawn at the wrong location with **no
  warning at all**, unlike the overview path (`fig_overview`, lines 213-218) which at
  least prints a warning when shapes differ. In `fig_crops` (line ~287-290), when
  `read_window_band` returns `None` (shape mismatch), the code just falls back to
  showing the plain RGB crop with **no overlay and no message** — a reviewer would
  read that as "model predicts no canopy here" when it's actually a data/registration
  problem.
- **Why it's real:** Verified against `phase4_semantic_finetune.py` (`step_inference`
  line ~3218 `prob_profile = {..., "crs": img_crs, "transform": img_tf}`) — in the
  normal pipeline path the prob/mask raster genuinely inherits the *exact* transform
  of the ortho used for inference, so this bug is usually dormant. It becomes live if
  `phase4_qa_overlay.py`'s own `resolve_ortho()` (glob/catalog fallback, lines 88-100)
  ever picks a *different* copy of the year's ortho than the one that was staged for
  inference (e.g. after an ortho file is replaced/re-registered), or if a stale
  mask/prob from an older ortho version is compared against a newer, same-sized ortho.
- **Also:** the comment at line 161 ("reproject the window by bounds instead of
  indices") describes a fallback that was never implemented — the function just bails.
  Dead/misleading comment.
- **Fix sketch:** Compare `src.transform` and `src.crs` (not just width/height) against
  the ortho's; if they differ, actually reproject the *bounds* (not the pixel window)
  into the mask's CRS and read that window, or at minimum surface the same warning
  `fig_overview` prints so a mismatched crop panel doesn't read as "no canopy here."

---

## 2. [MEDIUM-HIGH][conf: MEDIUM-HIGH] phase4_sentinel_snap.py:219-220 — default `--thresh 0.4615` is a fixed cross-year *comparison* constant, not each year's real deployed operating threshold

```
219    ap.add_argument("--thresh", type=float, default=0.4615,
220                    help="canopy threshold when --mask is a prob raster")
```

- **What's wrong:** `0.4615` traces back to a specific QC analysis (CHATLOG.md
  ~line 224-227): "scored 2000,2002,2013 ... first at each year's DEPLOYED threshold,
  then re-run at a FIXED 0.4615" to isolate a threshold confound. It is a deliberately
  *non-deployed*, cross-year-normalizing constant for that one analysis — not the
  actual operating threshold for any given year's model. The real per-year deployed
  threshold is computed in `phase4_semantic_finetune.py`'s `_operating_threshold()`
  (~line 3330-3353) from `semantic_eval_report.csv`'s `best_f1_thresh` /
  `prec_floor_thresh`, and differs year to year. `phase4_sentinel_snap.py` never reads
  that CSV — it just silently applies 0.4615 to whatever year's prob raster you point
  it at unless you remember to pass `--thresh` explicitly.
- **Why it's real:** Confirmed by grepping CHATLOG.md for the literal constant — it's
  documented as a fixed comparison value from one specific autopsy, not a general
  default. `phase4_viz.py`, by contrast, does the right thing (reads
  `best_f1_thresh` from the eval report per year, lines 205-218).
- **Impact:** a sentinel snapshot run for any year without an explicit `--thresh`
  shows canopy at the wrong cut point — a misleadingly high or low canopy % / extent
  for exactly the "watch recall fill in over time" purpose this tool exists for.
- **Fix sketch:** Mirror `phase4_viz.py`'s pattern — look up the year's
  `best_f1_thresh` from `semantic_eval_report.csv` when `--thresh` isn't passed, falling
  back to 0.5 (not 0.4615) if unavailable.

---

## 3. [MEDIUM-HIGH][conf: MEDIUM] phase4_label_review.py:296 vs :603 — compile recomputes crown_id from raw row order instead of trusting the manifest's persisted id; silently desyncs if the site package is regenerated between prep and compile

```
296            crown_id = f"{site}_{int(i):05d}"          # extract_site_crops (prep)
...
603            cid = f"{site}_{int(i):05d}"                # step_compile — identical scheme
604            lab = "present" if accept_all else decisions.get(cid)
```

- **What's wrong:** Both `--step prep` (crops/manifest build) and `--step compile`
  independently derive `crown_id` from `{site}_crowns_review.gpkg`'s row position
  after `reset_index(drop=True)` — there is no stored, order-independent key. `compile`
  never reads the manifest's own `id` field (`extract_site_crops` writes it, line
  292-296, but `discover_package`/`step_compile` re-reads the crowns gpkg from scratch
  and recomputes the id). If `phase4_label_review_prep.py` is re-run between a
  reviewer's `serve` session and the later `compile` (e.g. buffer changed, more
  city-crowns pulled in, crown count/order shifts by even one row), the ids baked into
  `reviews_live.csv` during review no longer line up with the ids `compile` recomputes.
  Reviewed decisions silently land on the wrong crown, or appear as "unreviewed" and
  get cut from the region (`step_compile` lines 617-621) — with **no error, no warning**.
- **Why it's real:** Confirmed no versioning/hash of the source gpkg is stored anywhere
  in the manifest (`step_prep`, lines 353-368) that `compile` cross-checks; the whole
  contract rests on `gpd.read_file(...).reset_index(drop=True)` producing an identical
  row order both times. Plausible trigger given the iterative site/buffer tuning
  workflow this pipeline documents (`phase4_label_review_prep.py --buffer ...`).
- **Fix sketch:** Have `extract_site_crops` write `crown_id` back into the crowns gpkg
  itself (persisted, order-independent) at prep time, and have `compile` join on that
  stored id rather than recomputing from row position; or store a content hash of the
  source gpkg in the manifest and refuse to compile if it doesn't match the current
  file.

---

## 4. [MEDIUM][conf: MEDIUM] phase4_label_review.py:151-158, 500 — unlocked concurrent CSV writes across reviewer threads

```
151 def _write_csv_row(path: Path, row: dict):
152     is_new = not path.exists()
153     path.parent.mkdir(parents=True, exist_ok=True)
154     with open(path, "a", newline="") as f:
155         w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
...
500    server = socketserver.ThreadingTCPServer(("", PORT), Handler)
```

- **What's wrong:** `ThreadingTCPServer` spins a new thread per request; `do_POST`
  calls `_write_csv_row` on the shared `csv_local`/`csv_drive` files with no lock. Two
  reviewers (or the offline-retry buffer in the JS client, `setInterval(...5000)`,
  firing concurrently with a live submit) posting at the same moment can interleave
  partial `open/write/close` sequences on the same file.
- **Why it's real:** The tool's own docstring describes multi-reviewer "conflict
  handling" (same-label→merged, different-label→flagged) as a supported scenario,
  implying concurrent access is expected, but nothing serializes the actual file
  append.
- **Fix sketch:** Guard `_write_csv_row` (and the read-then-append `_check_conflict`
  path) with a `threading.Lock`, or move to one writer thread consuming a queue.

---

## 5. [MEDIUM][conf: MEDIUM-LOW — needs GDAL-behavior verification] phase4_qa_overlay.py:223 vs :252 — probability overview panel resamples a nodata-sentinel raster with `Resampling.average` instead of `nearest`

```
223        p, p_nd, _ = read_decimated_band(prob_path, h, w, Resampling.average)   # fig_overview
...
252    p, p_nd, _ = read_decimated_band(prob_path, 1200, 1200, Resampling.nearest)  # fig_prob_hist
```

- **What's wrong:** The prob raster is uint8 with 255 as a hard nodata *sentinel*
  baked into real pixel values (0-254 = probability, 255 = un-imaged), confirmed at
  `phase4_semantic_finetune.py` `step_inference` (`PROB_NODATA`, ~line 3216-3220,
  3252-3254). `prob_to_display()` masks nodata *after* the decimated read
  (`p[prob_arr == nd] = np.nan`). If GDAL's average-resample path for a plain
  `dataset.read(out_shape=..., resampling=average)` blends raw sample values without
  excluding the registered nodata band value before averaging, a decimated block
  straddling an un-imaged boundary would mix e.g. a real value of 10 with the 255
  sentinel into a bogus mid-value that is no longer exactly 255 and therefore survives
  the nodata mask — showing a wrong color on the city-wide probability heatmap right
  at partial-coverage edges. The histogram panel for the *same* raster deliberately
  uses `Resampling.nearest` (safe — no blending), suggesting this wasn't a considered
  choice for the overview panel.
- **Confidence caveat:** modern GDAL's average-resample implementation is generally
  nodata-aware when the band's nodata metadata is set (which it is here,
  `"nodata": PROB_NODATA`), so this may already be handled correctly at the GDAL
  level — flagging for verification rather than asserting as confirmed.
- **Fix sketch:** Use `Resampling.nearest` for the prob overview panel too (consistent
  with the histogram), or explicitly pass `masked=True` / verify GDAL honors nodata
  during the average resample before trusting the panel at scene edges.

---

## 6. [LOW][conf: HIGH] phase4_label_review.py:206-216 — glob `*_crowns_review.gpkg` also matches the combined `all_crowns_review.gpkg`, synthesizing a spurious "all" pseudo-site

```
206    for crown_gpkg in sorted(root.glob("*_crowns_review.gpkg")):
207        site = crown_gpkg.name.replace("_crowns_review.gpkg", "")
```
`phase4_label_review_prep.py` writes `all_crowns_review.gpkg` (line 540-542) as the
combined-output file. `"all_crowns_review.gpkg"` matches `*_crowns_review.gpkg`
(prefix `"all"` + suffix `"_crowns_review.gpkg"`), producing `site == "all"`. Currently
harmless only because no `all_{year}_crop.tif` / `all_crop.tif` exists, so
`discover_package` prints a warning and skips it (lines 215-216). If a real site is
ever named such that this collision becomes ambiguous, or if a crop file named `all_*`
is ever added, this would silently misprocess. Low severity today, but worth a
`name != "all"` guard or renaming the combined output to avoid the glob entirely.

---

## 7. [LOW][conf: HIGH] Inefficiencies — repeated full inference and repeated raster opens

- `phase4_viz.py`: the scoring pass (lines 228-244, over every test tile) and the
  panel-rendering pass (lines 280-300, over the ~24 selected tiles) each independently
  call `read_tile()` + `infer_prob()` for the same rows — inference is redone from
  scratch for every tile that lands in a displayed bucket. Low impact (only ~24 tiles
  re-run), but avoidable by caching `(img, prob)` for the tiles selected into `buckets`
  during pass 1.
- `phase4_sentinel_snap.py`: `snap()` (lines 135-176) reopens both the ortho
  (`read_window` → fresh `rasterio.open()` each call, line 148) and the mask/prob
  raster (`canopy_from_mask` → `read_window`, line 122) once per site, inside the
  per-site loop — for ~10-20 sentinel sites that's ~20-40 fresh file opens of a
  multi-hundred-MB ortho where one open + reused handle would do (as
  `phase4_qa_overlay.py`'s `fig_crops` already does correctly for its ortho, opening it
  once outside the per-crop loop). Cheap (header-only opens, not full reads) but a
  real, fixable inefficiency matching the review's ask.

---

## 8. [LOW-MEDIUM][conf: MEDIUM] phase4_label_review.py:317-329 — crown outline shown to reviewer is naively decimated (`coords[::2]`), which can visibly distort the very shape the human is judging

```
325        coords = coords[::2]  # halve point count
```
Blindly dropping every other vertex (rather than a proper simplification like
Douglas-Peucker with a small tolerance) can noticeably distort a crown's outline for
polygons with few vertices — exactly the tool where geometry fidelity matters, since
the reviewer is deciding "is this really a tree" partly from the drawn outline. Low
severity (most crowns likely have enough vertices that this is imperceptible) but a
correctness gap for outlier polygons.

---

## Notes / clean areas checked, no bug found
- Mask/prob raster provenance (CRS, transform, nodata=255 sentinel) verified
  consistent across `phase4_semantic_finetune.py` writers and all six viz/QA/review
  readers — the 0/1/255 and 0-254/255 conventions are applied uniformly; no
  R/G/B↔B/G/R band-order swap found anywhere (`_rgb_first3`, `read_tile`,
  `extract_site_crops` all consistently treat bands 1,2,3 as R,G,B).
- `phase4_threshold_diagnostic.py`'s "cleanest negative" selection (first alphabetical
  `Negative_*` site with finite data) is looser than the docstring implies ("the
  cleanest negative we have is Negative_Parking") but the chosen site name is always
  printed in the verdict, so it's disclosed, not silently misleading — not flagged as
  a bug.
- All rasterio/file handles use `with` context managers throughout; no handle leaks
  found. `phase4_label_review.py`'s HTTP handler correctly inherits
  `SimpleHTTPRequestHandler`'s standard `..`-stripping `translate_path`, so no path
  traversal on `GET /crops/*.jpg` etc.
- `phase4_label_review_prep.py`'s `render_preview` extent/bounds passed to `imshow`
  matches the actual crop bounds used to produce the image (`clipped`, not the
  original un-clipped `expanded_bounds` the parameter name implies) — verified
  consistent, not a bug despite the slightly misleading parameter name.
