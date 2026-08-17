# Audit — phase4_semantic_finetune.py (v048)

Target: `G:\My Drive\treedata\Scripts\phase4_semantic_finetune.py` (3953 lines).
Auditor pass: full read (lines 1–3953). Domain invariants treated as intentional
design and NOT flagged (three-state masks, ADD-ONLY overlays, circular 2020
metrics, native resolution, `-f json` argparse filter, local-NVMe staging,
Colab-only torch).

Legend: SEV = CRITICAL / HIGH / MED / LOW. conf = high / med / low.
cat = bug / inefficiency / bottleneck.

---

## HIGH

### H1 — postproc `np.where(data==1,1,0)` materializes a full-city **int64** array
`file:3415` (`step_postproc`) — cat: inefficiency/bottleneck — conf: high

```python
with rasterio.open(mask_out) as src:
    data = src.read(1)                     # full-city uint8 in RAM
clean = rasterio.features.sieve(np.where(data == 1, 1, 0).astype(np.uint8), ...)
```
Verified empirically: `np.where(uint8_cond, 1, 0)` returns **int64** (8 bytes/px)
because the `1`/`0` literals are Python ints. The `.astype(np.uint8)` cast happens
*after* the int64 array is fully materialized. For a fine (7.5 cm) year the mask is
~148k×212k ≈ 3.1e10 px, so the int64 intermediate is ~**248 GB** (plus the 31 GB
`data` read plus 31 GB `clean`). This OOMs on any realistic Colab RAM.

Why real: coarse years (50–60 cm) are small enough to survive, but the pipeline
runs postproc for every year including the three 7.5 cm fine years (2017/2022/2024);
the full-res path is effectively broken. Even at coarse GSD the int64 blow-up is 8×
the needed memory.

Fix: `clean = rasterio.features.sieve((data == 1).astype(np.uint8), size=min_px, connectivity=...)`
— the boolean→uint8 cast is 1 byte/px and never allocates int64. Better still,
window the read/sieve/polygonize for full-res years instead of `src.read(1)` of the
whole raster.

### H2 — postproc reads the entire full-city mask into RAM for polygonize
`file:3413-3417` — cat: bottleneck — conf: med (magnitude depends on year GSD)

`data = src.read(1)` loads the whole mask (31 GB uint8 at 7.5 cm) in one array, then
H1's `np.where` copy and the `clean` sieve output are held simultaneously. The
threshold pass just above (lines 3388-3400) is carefully chunked at CHUNK=4096 rows
precisely to avoid a full-raster load — but the polygonize immediately below throws
that away and reads the whole thing. Inconsistent and OOM-prone for fine years.

Fix: polygonize per-window (rasterio can `shapes()` per block and merge), or at
least fix H1 so only two full-res arrays (uint8) coexist rather than an int64 one.

---

## MED

### M1 — `_operating_threshold` doesn't disambiguate the eval-CSV row by channels / run-tag
`file:3342-3349` (lookup) + `file:3110-3118` (writer) — cat: bug — conf: med

`semantic_eval_report.csv` is a FIXED path (line 257) — it is **not** suffixed by
`--run-tag` even though models/prob/mask/gpkg all are (`_tag_sfx()`). The eval writer
replaces rows keyed only on `(year, channels)` (3115-3116). So:
- Two `--run-tag` variants with the **same** channel arm (e.g. two RGB-only recipes)
  overwrite each other's eval rows.
- `_operating_threshold` filters only on `year` + `scope=="OVERALL"` and takes
  `sub.iloc[-1][col]` (3347) — it does **not** filter by `channels`. When several
  ablation arms (rgb / rgb+chm …) coexist for a year, postproc for a specific run may
  read a *different arm's* best-F1 threshold. This silently corrupts the deployed
  operating point → wrong canopy mask.

Fix: key the eval CSV (and the threshold lookup) on `(year, channels, run_tag)`, or
suffix the eval CSV by run-tag like every other output.

### M2 — eval accumulates ALL pixels in RAM and concatenates the pool twice
`file:3012-3061` (`step_evaluate`) — cat: inefficiency — conf: high

`all_prob`/`all_gt` collect every valid eval pixel across all tiles. The
TI_MAX_PIXELS=40M subsample happens **inside** `_threshold_independent_metrics`
*after* a full `np.concatenate` (3919). Then lines 3056 concatenate the **same**
full lists again (`yp = np.concatenate(all_prob); yt = np.concatenate(all_gt)`) for
the operating-threshold confusion counts — a second full-pool concat + no subsample.
For the coarse city-wide held-out block (hundreds of tiles) this is ~hundreds of MB
duplicated; still wasteful and redundant.

Fix: concatenate once, subsample once, reuse the arrays for both TI metrics and the
op-threshold confusion counts.

### M3 — augmentation RNG not reseeded per DataLoader worker under `fork`
`file:2701-2708` (no `worker_init_fn`) + `file:2200-2203` (own comment) — cat: bug —
conf: med

`multiprocessing.set_start_method("fork")` (3952) + `num_workers=16`, no
`worker_init_fn`. PyTorch reseeds torch (and Python `random`) per worker but **not**
numpy. The `SemanticDataset` transforms (`_make_spatial_transform` /
`_make_pixel_transform*`) are built in `__init__` in the parent process and forked
into every worker with identical internal RNG state; albumentations 2.x samples from
per-instance Python+numpy generators seeded at construction, so all 16 workers
produce the **same augmentation parameter sequence**. The code itself acknowledges
this ("np.random … under fork") at 2200 and works around it only for HS_DROPOUT via
`torch.rand`. Net effect: correlated/duplicated augmentations across workers →
reduced augmentation diversity (not a crash; a quiet training-quality regression).

Fix: pass a `worker_init_fn` that reseeds numpy and calls the compose's
`set_random_seed(base_seed + worker_id)` per worker.

### M4 — tile-cache signature records the wrong stride and omits the scan-density constants
`file:1800` + `file:1548-1550` + `file:1732-1755` — cat: bug (stale cache) — conf: med

`step_tile` builds the signature with `stride = tp["stride"]` (128 for coarse), but
the actual city-wide candidate scan uses an **adaptive** stride computed inside
`_gather_citywide_coarse` from `img_h*img_w / CITYWIDE_CANDIDATE_TARGET` (1549). The
signature therefore does not reflect the stride that actually produced the tiles, and
`_tile_signature` omits `CITYWIDE_CANDIDATE_TARGET` and `CITYWIDE_CANDIDATE_STRIDE`
entirely. Changing either constant (which changes the candidate set → the selected
tiles) will **not** invalidate the cache — `_existing_tiles_valid` returns True and
stale tiles are silently reused. Contradicts the header claim that the signature
"captures every constant that changes which tiles are selected."

Fix: add both constants to `_tile_signature`, and record the effective adaptive
stride rather than `tp["stride"]`.

---

## LOW

### L1 — coarse label downsampling uses nearest-neighbour on a 7.5 cm categorical mask
`file:983-993` (`canopy_label_from_2020_mask`) — cat: bug (label quality) — conf: med

The 7.5 cm 2020 binary mask is decimated to a coarse (50–60 cm) crop with
`Resampling.nearest` on both the windowed read and the reproject. A coarse pixel
covering an ~8×8 block of fine pixels takes a single nearest sample, not the
majority, so canopy edges alias and the per-tile `canopy_frac` used for
bin-stratification is noisy. Defensible (categorical) but `Resampling.mode` would
give truer coarse labels. Consistent across years, so not corrupting comparisons.

### L2 — per-strip morphology creates horizontal seam artifacts
`file:3389-3400` (`step_postproc`) — cat: bug (minor artifact) — conf: high

`binary_opening`/`binary_closing` are applied independently to each CHUNK=4096-row
strip. The 3×3 kernel cannot see across strip boundaries, so a 1-px erosion/dilation
seam can appear every 4096 rows. Cosmetic at 3×3 but real. Fix: overlap strips by
`MORPH_KERNEL_SIZE-1` rows and trim, or morph the full array (memory permitting after
H1/H2 fixes).

### L3 — inconsistent OVERALL-row pick: summary uses iloc[0], threshold uses iloc[-1]
`file:3599` vs `file:3347` — cat: bug (reporting) — conf: high

`print_summary` reads `sub.iloc[0]['iou']` while `_operating_threshold` reads
`sub.iloc[-1][col]` for the same `(year, OVERALL)` selection. With multiple ablation
arms per year the displayed IoU and the deployed threshold come from different arms.
Cosmetic but misleading. Fix: pick the same arm consistently (and see M1 — filter by
channels).

### L4 — inference edge-origin additions duplicate already-covered output
`file:3208-3213` (`step_inference`) — cat: inefficiency — conf: med

The main grid `range(0,img_h,stride)` already covers the full output (the last origin
covers `[ro_last, img_h)`), so the explicitly-added `img_h-TILE_SIZE` bottom/right
origins re-predict output regions that are already tiled. Their center crops overlap
main-grid crops → redundant forward passes and last-writer-wins over the overlap
(harmless but nondeterministic which context wins). Minor compute waste on a
full-city pass.

### L5 — `step_inference` default `batch_size=INFER_BATCH_SIZE` (160) can OOM a 24 GB card
`file:3144` — cat: bug (latent) — conf: high

The signature default is the legacy 160 (needs ~80 GB per the comment at 408-411);
`main` overrides it to `INFER_BATCH` (32). Only main is the entrypoint, so it's safe
in practice, but a direct call to `step_inference(label)` would use 160 and OOM.
Fix: default the parameter to `INFER_BATCH`.

### L6 — numpy sigmoid can overflow to inf on large-magnitude logits
`file:3025`, `file:3247` — cat: inefficiency (robustness) — conf: high

`1.0/(1.0+np.exp(-logits))` overflows `np.exp` for very negative logits (RuntimeWarning
suppressed by the global `warnings.filterwarnings("ignore")`). The limits are still
correct (→0 / →1), so no numeric corruption, but relying on suppressed overflow is
fragile. A stable expit (`scipy.special.expit`) is cleaner.

---

## Checked and found CLEAN (no finding)

- **Masked loss IGNORE handling** (`_masked_bce` 2362, `_masked_dice` 2375,
  `_masked_focal` 2395): 255 is excluded from both terms and from `valid.sum()`
  denominators (clamped `min=1.0`); pos_weight only touches target==1. Correct.
- **Sampler weighting**: the known `1/count[site]` inverse-SITE sampler is now used
  ONLY for the 6-site pool (2694-2699); the city-wide pool uses natural shuffle
  (2689-2692). No residual double-rebalance. Matches the documented v039 fix.
- **uint8/float casts around augmentation**: the RGB→float32 upcast from
  `np.concatenate` is cast back with `.astype(np.uint8)` before the colour augs in
  both the aux-height (2173) and hillshade (2190-2192) paths; the plain-RGB path stays
  uint8 into `A.Normalize`. Correct — the historic upcast-corruption bug is handled.
- **AMP order** (2466-2480): scale→backward→unscale→clip→step→update. Correct.
  Inference OOM fallback (3224-3241) halves batch and retries; output is
  batch-invariant (eval/no-grad/running BN). Correct.
- **First-conv 3→4 inflation** (`_inflate_first_conv` 2267): copies RGB weights,
  zero-inits the 4th channel, keeps the inflated stem trainable in Phase A (2553).
  Correct.
- **Frozen-encoder BN pin** (`_set_encoder_bn_eval` 2565, re-applied after each
  `model.train()` at 2453). Correct.
- **Global pooled val IoU** (`_validate` 2493): inter/pred/tgt pooled over the whole
  val set, one IoU per threshold, best-threshold selection. Correct.
- **CRS/window math** in `anchor_mask_from_2020` / `canopy_label_from_2020_mask` /
  `additions_from_mask`: decimated windowed read → scaled `src_tf` → reproject with
  matched nodata; WindowError / empty-window guards return all-IGNORE. Correct.
- **Inference center-crop tiling** (3205-3256): pad=(512-256)/2=128, center
  `[128:384]`=256, origins step by 256 → non-overlapping center crops that tile the
  output; nodata blanked to PROB_NODATA=255. Correct.
- **prob u8 scale ↔ threshold**: prob stored `round(p*254)` clip 0-254, 255=nodata;
  postproc `thr_u8=round(thr*254)`, `prob>=thr_u8 & prob!=255`. Consistent.
- **ADD-ONLY overlay** (`apply_additions` 1037): code1→canopy, code2→IGNORE only when
  not already canopy; never canopy→background; nodata re-applied after. Matches the
  domain invariant.
- **rasterio dataset lifetimes**: all short-lived opens use `with`; the hillshade
  master is a deliberate process-lifetime cache. No leaks.
