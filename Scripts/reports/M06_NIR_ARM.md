# M06 — NIR as the 4th input channel: runbook (built 2026-08-26, NOT LAUNCHED)

Companion to `reports/sector_campaign_design.md`. The executable spec is
`pipeline/queue_nir_m06.yaml` (its header carries the design rationale); this file
carries only what code cannot say: how to launch it, how to score it, and what the
result may and may not be read as.

## What landed in the engine

`--hs-source nir` — a fourth HS_SOURCE alongside `fr` / `struct` / `chm`, riding the
existing 4th-channel machinery end to end. The one structural difference: **band 4 is
band 4 of the year's own ortho**, so there is no master raster to stage and no warp —
NIR and RGB come from the same window of the same file and are co-registered by
construction (the LIDAR sources are reprojected per tile).

| where | what |
|---|---|
| `phase4seg/config.py` | APPENDED block only (pure-move protected): `HS_SOURCE_NIR`, `HS_STATS["nir"] = ([0.3752], [0.2991])`, `NIR_LIFTED_FLOOR_YEARS`, `nir_mode()`. No `HS_PATHS` entry — there is no raster. |
| `phase4seg/tiling.py` | citywide gather reads band 4 for kept tiles into `_nir_tile`; `step_tile` bakes it as band 4 and tags `HS_SOURCE=nir`. |
| `phase4seg/core.py` | inference `_prep` reads band 4 from the same clipped window of the ortho and concatenates it before the reflect-pad, exactly where the hillshade chip goes. |
| `phase4seg/common.py` | `_hillshade_ds()` returns None in nir mode; `read_hillshade_chip()` raises if ever reached. |
| `phase4seg/cli.py` | per-year band check + incompatible-flag guards before any staging. |

Everything else is untouched and works unchanged because "nir" is now a key in
`HS_STATS`: conv-1 inflation 3→4 zero-init, `IN_CHANNELS` adoption from tiles/ckpt,
the `HS_SOURCE` tile tag → train/eval adoption, ckpt `hs_source` → inference adoption,
`HS_DROPOUT` 0.25 channel dropout, `_input_norm` stats selection.

**No new tiling-signature key.** `hs_source` has always been an unconditional key in
`_tile_signature`, so a nir run gets its own cache and every existing cache stays
valid — verified locally by diffing the chm and nir signatures (same key set, only the
`hs_source` value differs).

**`HS_STATS["nir"]` is measured, not chosen**: /255 non-zero mean/std of band 4 pooled
over the eight healthy-floor NIR acquisitions, from decimated full-extent reads of the
local mirror (2026-08-26). Per-acquisition means run 0.276–0.466; within-acquisition sd
0.291, between-acquisition sd 0.068. One global entry is the same contract the fixed
ImageNet RGB stats already have; the per-year fine-tune and HS_DROPOUT absorb the rest.

## Fail-loud, by design

Never a silent substitution. Under `--hs-source nir` the engine refuses:

- a year whose catalog entry has `bands < 4` (before staging), and again if the raster
  itself has < 4 bands (at tile time and at inference time, against the ckpt's own
  `hs_source`);
- the 6-site path — per-year site crops are written RGB-only, so `--force-citywide` is
  required (every queue job passes it anyway);
- `--aux-height` (it forces RGB-only input, which would drop NIR silently) and
  `--no-hillshade` (no 4th channel at all).

`2015n` / `2021s` only WARN — their exclusion is a campaign-design decision, not an
engine law (IMAGERY_FACTS §12).

## Launch (Kam-gated — P11/P11.5: ask before EVERY launch)

State queue file, GPU tier, number of runtimes, expected wall-clock and rough cost.
Estimate for this queue: **1 runtime, A100 40 GB, ~2 h wall-clock for both jobs.**

1. **Runtime + bootstrap** (COLAB_AUTONOMY_SETUP.md, P11.6 runbook):
   `colab new -s M06 --gpu A100` → `py -3.12 pipeline/colab_cli_vmgen.py --branch <branch> --queue queue_nir_m06.yaml --outdir <scratchpad>` → `colab exec -s M06 -f <outdir>/vm_bootstrap.py --timeout 900` (prints `BOOTSTRAP_DONE`, dry-runs the queue).
2. **Pre-stage the ORTHOS, not the tiles.** `2016_snoh_1ft_rgbi.tif` (~2.6 GB) and
   `2019_naip_60cm_rgbi.tif` — an `rclone copy` of those two onto the VM's NVMe before
   launch keeps the Drive staging lock short and de-risks the FUSE read. **The tile sets
   cannot be pre-staged for this arm**: `phase4/tiles/{2016,2019n}` are rebuilt as 4-band
   NIR tiles — that rebuild *is* the arm. Budget it (~15–20 min/year), do not "fix" it.
3. **Place the queue**: it is committed at `pipeline/queue_nir_m06.yaml`; the bootstrap
   clones the repo, so nothing is copied by hand. `--queue queue_nir_m06.yaml` — the path
   is resolved relative to `pipeline/`, not the cwd.
4. **Launch**: `colab exec -s M06 -f <outdir>/vm_launch.py --timeout 60` → nohup'd,
   logging to `phase4/logs/train_queue_nohup_queue_nir_m06_{ts}.log`.
5. **Confirm the arm is real** in the log before trusting any number:
   `+ NIR band 4 from THIS YEAR'S ortho …` at tile time, `HS_SOURCE=nir` on the tiles,
   and `in_channels=4  +structure[nir]` at inference (the "+structure[…]" wording is the
   shared 4th-channel print; the source name in brackets is the thing to read).

Known false alarm: the queue's dry-run prints `! MISSING INPUT` for both jobs because
its path checker resolves `aoi/sectors_v1.json` against the cwd. `queue_sectors_fullext`
prints the same and ran fine — the engine resolves the AOI against the package dir.

**Hazard:** tile caches are keyed by year only, so this queue must never run concurrently
with any other 2016 or 2019n job (see the queue header).

## Scoring — C-CAP, never the NDVI reference

```
py -3.12 qc/phase4_qc_indep.py --year 2016  --ref <ccap_2016_hires_lc_snohfull.tif> \
    --prob <phase4/masks/edmonds_canopy_prob_2016_nir_m06.tif>
py -3.12 qc/phase4_qc_indep.py --year 2019n --ref <ccap_2021_hires_lc.tif> \
    --prob <phase4/masks/edmonds_canopy_prob_2019n_nir_m06.tif>
```
(epoch-matched refs, the same convention `qc/sector_campaign_loop.py::_ccap_ref` uses:
≤2018 → the 2016 snohfull product, ≥2019 → 2021.)

**The NDVI+CHM reference is CIRCULAR for these arms and must not be the headline.**
CLAUDE.md rule 5 names NDVI+CHM as the independent number for NIR years — that wording
predates this arm and does not hold here: an NDVI-derived reference is computed from the
very band the model now takes as input, so scoring an NIR-input model against it grades
the model on its own input. C-CAP (or photo-interp) is the referee. Same reason neither
job passes `--add-canopy-mask`: that overlay is NDVI-derived too, and would confound the
input-channel effect with a label change.

For **2019n** the contrast arm `p2nir` has a FULL-footprint raster while `nir_m06` is
sector-restricted, so bring them onto the same ground before comparing. Order matters —
each step feeds the next: `qc_indep` first (it writes the live=1 threshold row), then
`py -3.12 qc/phase4_sector_series.py` (scores every year at its live threshold and writes
the `cover1m/cover_1m_{year}_{tag}.tif` sidecar the next step needs; it has no --year flag,
it sweeps what exists), then
`py -3.12 qc/phase4_sector_poststrat.py --arms 2019n:p2nir 2019n:nir_m06` (it refuses any
arm without a sidecar). For **2016** the contrast arm `fullext_sectors_v1` is already
sector-scored on the same strips from the same ortho — a direct comparison, and the
cleanest one available.

**Headline metric is the cross-arm variance of honest recall across the two NIR years,
not either year's IoU** (audit M06: the year-invariance is the prize). Report both arms'
per-year numbers anyway, at matched call rate (M01).

## Promotion rule

Nothing here promotes anything. Per **M04** (MACHINERY_AUDIT_2026-08) a winner is named
on `qc_indep` live=1 threshold-free metrics at a matched operating point, and per the
sector campaign report **no arm is promotable until the noise arm** (identical recipe,
different seed) measures run-to-run sigma. The only empirical bound that exists is the
2013 `xsensor_rgb` .7395 vs `citywide_rgb` .7422 pair — a recall difference of 0.0027,
about what the *same raster* shows between thresholds 0.5 and 0.5026 (0.0023). n = 1 is
not a sigma: **treat any recall delta smaller than ~0.003 as inside the noise band.**
Sector-restricted arms are champion-INELIGIBLE by the campaign's eligibility rule — they
test a model, they do not deliver a year.

## Read the result honestly

The live per-year arms are **not RGB-only**: `sem_best_2016_fullext_sectors_v1.pt` and
`sem_best_2019_citywide_rgb.pt` both log `in_channels=4  +structure[chm]` (measured from
`phase4/logs`, 2026-08-26; the 3-channel models are only the base2020 sector baselines).
So this A/B is a **4th-channel swap, CHM → NIR, at equal channel count** — not "does a
4th channel help". Write it up that way. If the swap comes out ambiguous, the missing
rung is a true RGB-only control (same recipe, `--no-hillshade`, tag `rgb3_m06`), a third
A100 job that is deliberately **not** in this queue.

Second caveat for the pair: 2016 is a summer flight (2016-08-12 morning, INFERRED — see
IMAGERY_FACTS §9.2 / `qc/imagery_pixelsize_and_date.csv`, the one home for dates) and
2019n an autumn one (NAIP, acquired 2019-10-11), and their measured band-4 means differ
accordingly — 0.466 vs 0.286. The fixed `HS_STATS["nir"]` does not remove that; the
per-year fine-tune absorbs it. A 2016-vs-2019n gap is not a clean sensor effect.

## Validation status of the code (2026-08-26, local)

Three gates green: `py_compile`, `phase4seg_preflight.py` (plain and on the exact M06
command line), `phase4seg_smoke.py` on its default year-2000 tiles — unchanged 4-band
LIDAR tiles, i.e. the no-regression check. Beyond the gates, a scratchpad harness exercised the nir path on **real 2016
NIR pixels** on CPU: real `step_tile` wrote 4-band `HS_SOURCE=nir` tiles whose bands 1–4
are byte-identical to the ortho's own; the real `SemanticDataset` / `rgb_to_model_input`
normalised band 4 with `HS_STATS["nir"]` and HS_DROPOUT blanked it; real `step_inference`
produced a prob raster through the new band-4 read and refused a 3-band ortho; the chm and
nir tiling signatures were diffed (same key set, only `hs_source` differs); and every
fail-loud path raised — 3-band ortho at tile time, 3-band ortho at inference time, the
6-site path, `read_hillshade_chip` in nir mode, and the three cli guards (8/8 checks). **Not run locally:** a full-scale citywide tiling or any real
training (Colab-only, by the phase4seg gotcha) — first Colab run is still the first
Colab run.
