from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE          = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR    = BASE / "photos"                       # training-site footprints
POLYGONS_DIR  = BASE / "polygons"                     # training-site crown polygons

# Per-year native orthos. phase2 catalogues them under .../native/; older phase1
# code kept some at the "Pipeline Imagery" root. We resolve both.
IMAGERY_DIR   = BASE / "Full_Image/Pipeline Imagery"
NATIVE_DIR    = IMAGERY_DIR / "native"
# LIDAR structure rasters (USGS Western-WA 3DEP, ~2016), EPSG:3857 @ 1 m, clipped
# to the imagery extent. Reprojected onto each tile's native grid as a 4th input
# channel. Three selectable sources (--hs-source):
#   fr      raw first-return (DSM) hillshade — v025 original.
#   struct  terrain-cancelled structure = clip(fr - bare_earth + 127, 1, 254).
#           Bare-earth shading subtracts out, so slope/aspect illumination
#           (fixed 315° sun) cancels: mowed grass → flat ~127, canopy keeps its
#           full texture, flat rooftops are suppressed. 0 stays nodata. WEAK: it
#           is a hillshade DIFFERENCE (relief texture), NOT height — a flat 20 m
#           roof reads ~127 like grass, so it can't resolve grass↔tree.
#   chm     REAL canopy height (v030). USGS 3DEP Height-Above-Ground in metres,
#           U8-scaled DN = 1 + round(clip(h,0,50.6)/0.2): DN 1 = 0 m (grass),
#           DN 254 ≈ 50.6 m; 0 stays nodata. The true grass↔tree discriminator
#           (height, not texture). Build with fetch_build_chm.py.
# See fetch_lidar / fetch_be_build_struct / fetch_build_chm in the handoffs.
HS_PATHS = {
    "fr":     IMAGERY_DIR / "lidar_snoh_hillshade_fr.tif",
    "struct": IMAGERY_DIR / "lidar_snoh_structure.tif",
    "chm":    IMAGERY_DIR / "lidar_snoh_chm.tif",
}

# Phase 3 semantic checkpoint — the fine-tune starting point for every year.
P3_DIR        = BASE / "phase3"
PROB_2020     = P3_DIR / "edmonds_canopy_prob_2020.tif"  # full-city 2020 canopy prob
MASK_2020     = P3_DIR / "edmonds_canopy_mask_2020.tif"  # full-city 2020 BINARY canopy
                                                         # mask — coarse city-wide
                                                         # label source (Fix 3)
P3_CKPT_CANDIDATES = [
    P3_DIR / "sem_best_2020.pt",
    P3_DIR / "checkpoints" / "sem_best_2020.pt",
]

# phase2 coverage matrix (optional; consulted if present for partial-coverage years).
COVERAGE_CSV  = BASE / "phase2" / "training_site_coverage.csv"

# Phase 4 outputs
OUT_DIR       = BASE / "phase4"
SITE_DIR      = OUT_DIR / "sites"      # /{year}/{site}_img.tif, {site}_mask.tif
TILE_DIR      = OUT_DIR / "tiles"      # /{year}/{train,test}/{images,masks}/...
MODELS_DIR    = OUT_DIR / "models"     # sem_best_{year}.pt
MASKS_DIR     = OUT_DIR / "masks"      # prob/mask rasters + canopy gpkg
EVAL_DIR      = OUT_DIR / "eval"       # semantic_eval_report.csv + consistency
EVAL_CSV      = EVAL_DIR / "semantic_eval_report.csv"
CONSISTENCY_CSV = EVAL_DIR / "cross_year_consistency.csv"

# Local SSD scratch for staging large orthos (avoid Drive FUSE stalls).
LOCAL_SCRATCH = Path("/content/phase4_scratch")

CROWN_CRS     = "EPSG:3857"   # the hand-traced crowns / training photos live here

# ── Imagery resolution order — ONE HOME (IMAGERY_PLAN.md A5) ──────────────────
# A catalog entry names a FILE, not a path. Every consumer — the Colab engine and
# the local QC/diagnostic scripts alike — resolves that filename through the
# ordered root list below; the first existing root that holds the file wins.
#
# Why this is centralised: local QC preferred D:\edmonds-pipeline\Imagery while
# the engine read Drive, and NATIVE_DIR ("native/") does not exist at all, so
# every lookup silently fell through to the Drive root. Two runs could therefore
# read different pixels for the same year and nothing would say so. Callers MUST
# record WHICH root they opened (see phase4_catalog_check.py) — a silent
# cross-root fallback is the bug this ordering exists to make visible.
#
# NOTE: the D: mirror is PARTIAL — it holds the King/Snohomish/NAIP years but
# none of the four City of Edmonds orthos (2017/2020/2022/2024, ~127 GB), which
# resolve to Drive. Measured 2026-08-19.
LOCAL_MIRROR_DIR = Path(r"D:\edmonds-pipeline\Imagery")
LOCAL_DRIVE_DIR  = Path(r"G:\My Drive\treedata\Full_Image\Pipeline Imagery")


def imagery_roots():
    """Ordered imagery roots for this machine; first existing root wins.

    On Colab: NATIVE_DIR -> IMAGERY_DIR (unchanged from the original
    resolve_native_path order). Locally: the fast D: mirror -> the Drive mount.
    """
    if BASE.exists():                     # Colab / anywhere the Drive base mounts
        return [NATIVE_DIR, IMAGERY_DIR]
    return [d for d in (LOCAL_MIRROR_DIR, LOCAL_DRIVE_DIR) if d.exists()]


# ── Hyperparameters (Method Pipeline v5.0 "Fine-Tuning" block) ────────────────

ENCODER          = "resnet101"
DECODER_CHANNELS = (1024, 512, 256, 128, 64)
DECODER_DROPOUT  = 0.3

TILE_SIZE        = 512
NEGATIVE_SAMPLE_RATE = 0.15      # fine/medium; coarse overridden below
RANDOM_SEED      = 42

# Coarse-tier city-wide stratified tiling (Fix 3). For coarse years the default
# tiling path samples tiles across the whole city ortho (not just the 6 site
# footprints), labelled from the 2020 binary canopy mask, balanced across
# canopy-fraction bins so the set isn't all-forest or all-background.
COARSE_CITYWIDE_TILES     = 800  # total tile budget across canopy-fraction bins
CITYWIDE_CANDIDATE_STRIDE = 256  # candidate origin stride FLOOR (coarse orthos)
# Cap the city-wide candidate scan. At the fixed 256 stride a FINE ortho
# (74k×106k @14.9cm) yields ~120k candidates → a ~2 h scan that times out / OOMs
# on Colab just to pick 800 tiles. Adapt the stride so the scan is bounded to
# ~this many candidates on any GSD; coarse orthos already sit below it (stride
# stays 256, unchanged). Makes --force-citywide feasible on fine years.
CITYWIDE_CANDIDATE_TARGET = 8000

# Green hard-negative mining (Fix B). Background (canopy_frac==0) tiles whose
# mean GRVI = (G-R)/(G+R) exceeds GREEN_GRVI_THRESHOLD are vegetated-but-non-
# canopy (grass, lawn, field) — the exact confusers driving false canopy. We
# reserve HARD_NEG_FRACTION of the background tile budget for them so the model
# sees the grass/canopy boundary.
# Tune Fix 3: softened from 0.05/0.25 — GRVI≥0.05 grabbed 242 tiles (too many,
# risk of labelling missed-tree tiles as background). Raise the greenness bar so
# only strongly-green tiles qualify, and reserve a smaller slice.
# Re-baseline (run-5): the audit showed the green-hard-neg reservation was part of
# the negative-emphasis stack that did NOT beat run 5. Reserve 0.0 → no forced
# green slice (green tiles can still be picked as ordinary background; mining is
# still computed/logged). Raise to re-enable.
# v030 grass-FP fix: RE-ENABLED. Diagnostics showed grass = 64% of all false
# positives / 29.5% grass-FP rate. Reserve 30% of the bg budget for green
# hard-negs and lower the greenness bar (0.10→0.08) so more lawn/field tiles
# qualify. Paired with the CHM height channel + dedicated grass negative sites.
# v032 collapse fix: 0.30/0.30 overshot — train pool hit 44% near-empty tiles
# (canopy_frac<5%), and the per-sample dice term snowballs on empty tiles once
# probability mass drops (grad ∝ 1/(P+1)^2) → all-background cliff at E6 in
# THREE runs (chm/pw1.3, rgb-equiv/pw1.3, chm/pw2.774 — channel and pos_weight
# both eliminated empirically). Soften toward the stable v029-era pool.
GREEN_GRVI_THRESHOLD = 0.08
HARD_NEG_FRACTION    = 0.15

# Background share of the coarse city-wide tile budget (Fix C). Raised above the
# equal 5-bin baseline (~20%) so negatives are well represented. The remaining
# budget is split among the canopy bins (1..4), balanced among themselves.
# Curated negative-site tiles are added on top and don't count against this
# fraction. Tune Fix 4: backed off 0.35→0.25. Re-baseline (run-5): run 5 used the
# equal 5-bin selection (~21% background); 0.20 reproduces that as the controlled
# baseline. Raise to re-test a heavier background share.
# v030 grass-FP fix: 0.20→0.30 so background (incl. the reserved grass hard-neg
# slice above) is better represented against the grass over-prediction.
# v032 collapse fix: 0.30→0.22 (actual was 36% incl. neg-sites) — see the
# HARD_NEG_FRACTION note above; grass emphasis stays via the reserved slice +
# committed negative sites, just not enough empty tiles to feed the dice cliff.
BACKGROUND_BUDGET_FRACTION = 0.22

# Spatially-blocked train/val/test split for coarse city-wide tiles (Fix 4).
# Whole geographic blocks are assigned to each split, then train tiles within
# CANOPY_AUTOCORR_M of any held-out tile are dropped so val/test are honestly
# separated. 520 m is the upper bound of the canopy spatial-autocorrelation
# range (250–520 m); the block edge is several × that so blocks aren't trivially
# small.
CANOPY_AUTOCORR_M    = 520.0
SPATIAL_BLOCK_SIZE_M = 1500.0
COARSE_VAL_FRAC      = 0.20
COARSE_TEST_FRAC     = 0.20

# Fine-tune schedule — identical values to Phase 3 / Method Pipeline.
EPOCHS_PHASE_A   = 20            # decoder only, encoder frozen
LR_PHASE_A       = 5e-5
EPOCHS_PHASE_B   = 30            # full model
LR_PHASE_B       = 5e-6
EARLY_STOP_PAT   = 15
# Phase-A frozen-encoder BN handling. requires_grad=False does NOT stop BN from
# updating running stats (model.train() re-enables it every epoch). When True,
# encoder BN is pinned to its pretrained running stats for Phase A (standard
# transfer-learning practice). Default False = legacy behaviour. See
# _set_encoder_bn_eval for the collapse mechanism this addresses.
# v039: default ON — standard transfer-learning practice; leaving frozen-encoder
# BN in train mode let running stats drift off a background-heavy batch stream and
# destabilised Phase A. --no-freeze-encoder-bn (or setting this False) restores the
# legacy behaviour for A/B testing.
FREEZE_ENCODER_BN = True
BATCH_SIZE       = 10
NUM_WORKERS      = 16
SAVE_EVERY       = 5
SPATIAL_BUFFER_PX = 512          # see phase3 note; 512 keeps all non-val train tiles
L1_LAMBDA        = 1e-6

# Segmentation loss = BCE_WEIGHT * masked_BCE + DICE_WEIGHT * masked_Dice
# (Fix 1). Both terms are IGNORE-aware (255 pixels excluded exactly like
# _masked_bce). Dice supplies a region-overlap gradient that BCE alone lacks,
# which helps the compressed-probability coarse years. Tunable.
BCE_WEIGHT       = 0.5
DICE_WEIGHT      = 0.5
DICE_SMOOTH      = 1.0           # Laplace smoothing on the soft-Dice ratio

# Focal loss for hard-negative emphasis (Edit F). Up-weights hard / misclassified
# pixels by prediction CONFIDENCE, not class frequency, so it targets the
# grass/developed confusers without re-coupling to the sampler. Active only when a
# tier's loss mode is "focal_dice"; the paired Dice term is REQUIRED (focal's
# gradient is unstable alone at this gamma). FOCAL_ALPHA=0.5 disables alpha
# balancing; 0.25 (literature default) emphasises the background/non-canopy class.
FOCAL_GAMMA  = 2.0
FOCAL_ALPHA  = 0.25
FOCAL_WEIGHT = 0.5              # paired with DICE_WEIGHT in focal_dice mode

# BCE pos_weight for class imbalance (Fix 2). Applied to coarse + medium tiers
# only (fine tier stays at 1.0 / None). Clamped to this range so a canopy-scarce
# split can't blow up the gradient.
POS_WEIGHT_MIN   = 1.0
POS_WEIGHT_MAX   = 10.0
# Coarse tier gets a much tighter cap (Tune Fix 1): the background-fraction knob
# (Fix C) changes the tile-pool class ratio, which moved raw pos_weight
# 1.16→1.96 and pushed the model into over-prediction. Hard-capping coarse
# pos_weight decouples it from tile-pool composition so the two knobs stop
# fighting. Raw (pre-clamp) value is still logged.
COARSE_POS_WEIGHT_MAX = 1.3
# Single-rebalancing-channel rule (one channel, not two — Cui et al. 2019;
# "Simplifying NN Training Under Class Imbalance" 2023). v039: the coarse sampler
# is now NATURAL/instance-balanced (shuffle; preserves the true ~40% canopy prior)
# — it no longer rebalances — so the frequency-invariant region (Dice) term of the
# BCE+Dice loss owns class balance, and BCE pos_weight is retired to 1.0 (=None)
# for coarse. This keeps predictions better calibrated near 0.5 (a strong
# pos_weight shifts the operating point, which is what drove the earlier
# probability-scale drift). Flip True (with COARSE_POS_WEIGHT_MAX) only to A/B a
# loss-side pixel reweight. Medium/fine unaffected.
# WATCH: per-sample Dice can under-predict on empty tiles (~29% of the balanced
# pool); if the validation run shows low recall / under-prediction, mask the Dice
# term to target-present tiles (audit finding, deferred from this round).
COARSE_USE_POS_WEIGHT = False

# Inference (same center-crop streaming as Phase 0 / Phase 3)
INFER_BATCH_SIZE = 160
INFER_STRIDE     = 256
INFER_PAD        = (TILE_SIZE - INFER_STRIDE) // 2

# --infer-batch: full-city inference batch. The old default (BATCH_SIZE*16=160)
# fp32 forward spikes ~76 GB → an 80 GB card only. Inference output is
# batch-invariant (eval mode, no grad, running BN stats), so this is a pure
# memory/speed knob; 32 + autocast fits a 24 GB card with negligible speed cost.
INFER_BATCH = 32
# --run-tag: when set, every per-year output (model/prob/mask/gpkg) is suffixed
# _TAG so successive Colab runs SAVE instead of OVERWRITE — for keeping variants
# / recipes for later analysis. Empty = legacy behaviour (overwrite).
RUN_TAG = ""

# Post-processing (Method Pipeline "Semantic Thresholding" block)
CANOPY_PROB_THRESHOLD = 0.5

# Operating-point selection for the final mask threshold (Fix D).
#   "best_f1"         → threshold maximising F1 on the eval PR curve (default;
#                       nothing changes unless --thresh-mode is passed)
#   "precision_floor" → lowest threshold whose precision ≥ PRECISION_FLOOR
#                       (highest recall meeting the floor; trades recall for
#                       precision to fight canopy over-prediction)
THRESH_MODE     = "best_f1"
PRECISION_FLOOR = 0.72
# Explicit numeric override for the postproc operating threshold. When set to a
# value in (0,1), _operating_threshold returns it verbatim, bypassing the per-year
# best_f1 / precision_floor lookup. Used to LOWER an off-year threshold (e.g. 2000
# 0.513→~0.30) to recover canopy the stale-2016 CHM suppressed. Blunt lever —
# prefer an honest reference (Phase 1 NAIP-NDVI / Phase 5 photo-interp) over
# hand-tuning against the circular 2020-derived best-F1. Flag: --infer-thresh.
INFER_THRESH_OVERRIDE = None
# Optional ADD-ONLY corrected-label overlay for the coarse city-wide path. Path to
# a canopy_additions_{year}.tif (phase4_build_corrected_labels.py): 0=no change,
# 1=ADD canopy, 2=IGNORE, 255=nodata. Reprojected onto each crop and layered on top
# of the 2020 mask — 1 forces canopy, 2 forces IGNORE (never background). Teaches
# NIR+CHM-confirmed canopy the conifer-only labels miss, without rewriting the
# 148k×212k 2020 mask. One file (built on the 2016 grid) serves 2016 AND 2000 (most
# trees are static). Flag: --add-canopy-mask.
ADD_CANOPY_MASK = None
SAMPLE_MANIFEST = None  # --sample-manifest: C-CAP-stratified fixed tile locations (phase4_ccap_sample.py)
INFER_AOI = None        # --infer-aoi: sector AOI file (pipeline/aoi/*.json|.gpkg); step_inference is
                        # restricted to tiles intersecting the sector rects, rest of the full-grid
                        # raster stays PROB_NODATA (the sample-manifest output shape). 2026-08-24.
# ── Auxiliary height-supervision reframe (--aux-height) ────────────────────────
# Teach the model to PREDICT canopy height from RGB (a 2nd output head) instead of
# feeding the 2016 CHM as an outvoted 4th INPUT channel. Inference stays RGB-only, so
# "tall vs flat" is baked into the RGB features (fixes recurring grass FPs + the stale
# 2016-snapshot problem). The CHM is repurposed as the regression TARGET (masked-L1).
# The height head is supervised only on CHM-credible years (2020 base + near-2016);
# other years inherit it via the shared encoder. See the plan / CHATLOG.
AUX_HEIGHT         = False       # --aux-height: RGB-only input + height head + masked-L1
HEIGHT_LAMBDA      = 0.2         # --height-lambda: weight of the aux height loss
HEIGHT_SCALE_M     = 40.0        # normalise the height target: h_norm = metres / SCALE
CHM_CREDIBLE_YEARS = {"2015", "2016", "2017", "2020"}  # write a height sidecar only here
EMIT_HEIGHT        = False       # --emit-height: also write a predicted-height raster
MIN_CANOPY_PATCH      = 3.0      # m²
MORPH_KERNEL_SIZE     = 3
SIMPLIFY_TOLERANCE_M  = 0.5
POLYGON_CONNECTIVITY  = 8

# A pixel is treated as "no data" (outside coverage) if all three RGB bands are
# exactly the nodata fill (or exactly 0 when nodata is undefined). Used to blank
# the un-imaged 33% of Snohomish partial-coverage years in the canopy mask, and
# to skip uncovered training sites during label generation.
COVERAGE_NODATA_MAX = 0.95       # site skipped if >95% of its window is nodata
PROB_NODATA         = 255        # reserved sentinel in the uint8 prob raster

# Three-state training mask: 0 = background (reviewed non-canopy), 1 = canopy
# (approved crown valid for this year), 255 = IGNORE (unreviewed / imagery
# nodata) — excluded from the loss and from evaluation. Legacy masks contain
# only {0,1}, so all IGNORE-aware code is a no-op for years without review data.
IGNORE_LABEL        = 255

# ImageNet normalisation
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

# Vegetation-index input channels (parity with Phase 3 --vi). Default OFF: the
# deployed Phase 3 checkpoint is the 3-channel RGB model. IN_CHANNELS must match
# the checkpoint being fine-tuned, so only enable --vi if Phase 3 trained a VI
# model and you point --ckpt at it.
USE_VI      = False
VI_NAMES    = ("GCC", "GRVI", "ExG")
VI_MEAN     = [0.33, 0.00, 0.10]
VI_STD      = [0.10, 0.30, 0.25]
# LIDAR structure raster as a uniform 4th input channel (structure signal that
# separates trees from grass; one ~2016 snapshot co-registered per tile, all
# years). Stats are /255 over non-zero pixels (measured from each raster).
# The 3-channel Phase-3 RGB checkpoint is inflated to 4ch with the new conv-1
# channel ZERO-initialised, so the pretrained RGB behaviour is preserved at
# fine-tune start and structure weights are learned. Temporal caveat: best for
# 2015-2017 imagery; highest drift for 2000-2012 (canopy changed since 2016).
#
# HS_SOURCE selects the raster (--hs-source). It is a *tiling-time* choice:
# step_tile stamps the tag HS_SOURCE on every image tile, train/evaluate read it
# back off the tiles, checkpoints record it, and inference reads it from the
# ckpt — so stats/raster always match the data the model actually saw,
# regardless of the flag on later steps (same philosophy as the band-count
# auto-match).
#
# HS_DROPOUT: per-sample prob of blanking the structure channel to its mean
# during TRAINING only (channel dropout). Keeps a strong pure-RGB pathway so
# the model degrades gracefully where the ~2016 snapshot is stale (early years)
# and never over-trusts structure against RGB evidence.
USE_HILLSHADE = True
HS_SOURCE   = "chm"               # 'fr' | 'struct' | 'chm' (see HS_PATHS)
HS_STATS = {                      # /255 non-zero mean/std per source
    "fr":     ([0.58],   [0.26]),
    "struct": ([0.3867], [0.2175]),
    "chm":    ([0.2306], [0.2305]),   # 3DEP HAG U8-scaled, /255 nonzero (fetch_build_chm.py 2026-07-04)
}
HS_DROPOUT  = 0.25                # 0 disables; training only
IN_CHANNELS = 3   # module default; set per-run from the tile/ckpt band count


# ══════════════════════════════════════════════════════════════════════════════
#  18-ENTRY IMAGERY CATALOG  (verbatim from phase2_data_prep.py — the authority)
# ══════════════════════════════════════════════════════════════════════════════

SEG_INSTANCE_SEMANTIC = "instance+semantic"
SEG_SEMANTIC_ONLY     = "semantic_only"

# ── gsd_cm CORRECTED 2026-08-18 — it was CRS units x 100, not ground cm ──────
# The old values assumed every CRS was metric. They were not:
#   EPSG:3857  Web Mercator inflates distance by 1/cos(lat) = 1.49 at Edmonds
#              -> King County years were overstated by 49%
#   EPSG:2285  NAD83 / Washington North is US SURVEY FEET, not metres
#              -> the Snohomish years were overstated by 3.24x (50.0 vs 15.4)
#   EPSG:26910 UTM 10N is metric -> the NAIP years were already right
# TRUE values below are measured from each file's WGS84 span and pixel count
# (phase4_data_inventory.py), so they cannot be fooled by either effect.
#   2000/2002 59.7->40.1 · 2005/07/09 29.9->20.1 · King 14.9->10.0
#   CoE 7.5->5.0 · NAIP 60.0->60.7 · SNOH 50.0->15.4
# TIER is unchanged for every year: see tier_for() for why 2016/2021s pin it.
# "coverage" is now the MEASURED share of the phase3 2020-mask study area.
YEAR_CATALOG = [
    {"key": 2000, "label": "2000", "source": "King County", "gsd_cm": 40.1,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2000_king_rgb.tif"},
    # 2026-08-23 REPLACED: 2002_king_rgb.tif (JPEG tile-cache export, effective 57.8 cm, 8x8 block signature)
    # -> 2002_usgs_30cm_rgb.tif (the 39 ORIGINAL USGS HRO Seattle-Tacoma GeoTIFF tiles via WAGDA's Download
    # capability, mosaicked; effective 41.4 cm, no block signature; common-grid 56 vs 91 cm, HF ratio 1.54;
    # city coverage 100%). Same flight the cache served — better provenance, not a different acquisition.
    {"key": 2002, "label": "2002", "source": "USGS HRO Seattle-Tacoma (Selkirk) via WAGDA", "gsd_cm": 30.0,
     "bands": 3, "crs_epsg": 26910, "coverage": "100% of city polygon, 80.6% of study extent (measured 2026-08-23; remainder is Puget Sound)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2002_usgs_30cm_rgb.tif"},
    # 2026-08-23 campaign S02: the county's OWN 2002 acquisition — NOT a duplicate of the USGS HRO flight
    # (dup test r median 0.847 at the 5 sites on a common 1-ft grid; same-flight pairs measure 0.98-0.997;
    # dup_test_vs_U02.json beside the ledger). Date NOT FOUND (year from the service name only). COMPLEMENT.
    {"key": "2002s", "label": "2002s", "source": "Snohomish Co.", "gsd_cm": 30.5,
     "bands": 3, "crs_epsg": 2285, "coverage": "87.6% of study extent (measured 2026-08-23; NW water gap)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2002_snoh_1ft_rgb.tif"},
    # 2026-08-23 campaign S03: 2003 — a year the project had NO imagery for. Date NOT FOUND. COMPLEMENT
    # (new calendar year; 1-ft county RGB, effective 41.6 cm).
    {"key": "2003s", "label": "2003s", "source": "Snohomish Co.", "gsd_cm": 30.5,
     "bands": 3, "crs_epsg": 2285, "coverage": "87.5% of study extent (measured 2026-08-23; NW water gap)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2003_snoh_1ft_rgb.tif"},
    {"key": 2005, "label": "2005", "source": "King County", "gsd_cm": 20.1,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2005_king_rgb.tif"},
    # 2026-08-23 campaign S06: 2006 — a calendar year the project had NO imagery for (likely the NAIP 2006
    # republished by the county; untested). Date NOT FOUND. 1-m RGB.
    {"key": "2006s", "label": "2006s", "source": "Snohomish Co. (1 m; likely NAIP 2006 republish)", "gsd_cm": 100.0,
     "bands": 3, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2006_snoh_1m_rgb.tif"},
    {"key": 2007, "label": "2007", "source": "King County", "gsd_cm": 20.1,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2007_king_rgb.tif"},
    # 2026-08-23 campaign S07: the county's 2007 1-ft RGB. The planned flip test vs 2007_king FAILED
    # (effective 38.5 vs the required < 25.5x0.9 = 22.95 cm), so the King file KEEPS the 2007 key and this
    # is a second-acquisition COMPLEMENT. 100% study extent (no water gap in the 2007 product).
    {"key": "2007s", "label": "2007s", "source": "Snohomish Co.", "gsd_cm": 30.5,
     "bands": 3, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2007_snoh_1ft_rgb.tif"},
    {"key": 2009, "label": "2009", "source": "King County", "gsd_cm": 20.1,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2009_king_rgb.tif"},
    # 2026-08-23 campaign S09: the county's 2009 (Aerials Express product per the service). Sharper than the
    # King cache on a common grid (HF 1.13, no JPEG signature) but held as COMPLEMENT per plan. Date NOT FOUND.
    {"key": "2009s", "label": "2009s", "source": "Snohomish Co. (Aerials Express)", "gsd_cm": 30.5,
     "bands": 3, "crs_epsg": 2285, "coverage": "98.4% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2009_snoh_1ft_rgb.tif"},
    # 2026-08-23 campaign S11: 2011 — a calendar year the project had NO imagery for. Date NOT FOUND.
    {"key": "2011s", "label": "2011s", "source": "Snohomish Co.", "gsd_cm": 30.5,
     "bands": 3, "crs_epsg": 2926, "coverage": "99.6% of city, 79.9% of study extent (measured 2026-08-23; NW water)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2011_snoh_1ft_rgb.tif"},
    # 2026-08-23 campaign S12: the county 9-in 2012 (the year the county sells on media — exported from the
    # free public service). SHARPER than the 2012_king orphan on a common grid (29.6 vs 38.9 cm, HF 1.57, no
    # JPEG signature) but partial coverage (82.3%) -> COMPLEMENT; the King orphan adoption stays a pending
    # decision. Date NOT FOUND.
    {"key": "2012s", "label": "2012s", "source": "Snohomish Co. (9-in)", "gsd_cm": 22.9,
     "bands": 3, "crs_epsg": 2926, "coverage": "99.6% of city, 82.3% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2012_snoh_9in_rgb.tif"},
    {"key": 2013, "label": "2013", "source": "King County", "gsd_cm": 10.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2013_king_rgb.tif"},
    # 2026-08-23 campaign S13: the county 1-m 2013. COMPLEMENT to 2013_king. Date NOT FOUND.
    {"key": "2013s", "label": "2013s", "source": "Snohomish Co. (1 m)", "gsd_cm": 100.0,
     "bands": 3, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2013_snoh_1m_rgb.tif"},
    {"key": 2015, "label": "2015", "source": "King County", "gsd_cm": 10.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2015_king_rgb.tif"},
    # 2026-08-23 REPLACED: 2016_snoh_rgbi.tif (0.5 ft served upsample, 53.4% clip) -> 2016_snoh_1ft_rgbi.tif
    # (native 1 ft = 30.5 cm, full study extent; acquire_imagery S16: 100% of the city polygon, 82% of the
    # study extent (rest is Puget Sound), HF energy 1.01x on a common grid = same source pixels; the wins
    # are coverage + provenance, NIR real). The old
    # file stays on disk for provenance (SUPERSEDED_FILES in qc/phase4_catalog_check.py). Tier stays pinned.
    {"key": 2016, "label": "2016", "source": "Snohomish Co. (HXIP 2016, county 1-ft delivery)", "gsd_cm": 30.5, "tier": "coarse",
     "bands": 4, "crs_epsg": 2285, "coverage": "100% of city polygon, 82.3% of study extent (measured 2026-08-23; remainder is Puget Sound)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2016_snoh_1ft_rgbi.tif"},
    {"key": 2017, "label": "2017", "source": "City of Edmonds", "gsd_cm": 5.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2017_coe_rgb.tif"},
    {"key": 2019, "label": "2019", "source": "King County", "gsd_cm": 10.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2019_king_rgb.tif"},
    # 2026-08-23 campaign N15: NAIP 2015 (flown 2015-08-07, leaf-on), 8 DOQQ quads mosaicked to the study
    # extent — the leaf-on pair to the Feb–Mar leaf-off 2015 King file. COMPLEMENT (new year key).
    {"key": "2015n", "label": "2015n", "source": "NAIP (acquired 2015-08-07)", "gsd_cm": 100.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2015_naip_1m_rgbi.tif"},
    # 2026-08-23 campaign S15: the same 2015-08-07 HXIP 1-ft flight the county serves (flown 15:31, sun el
    # 46°) — 3.3x the NAIP grid, same day. Band 4 is a CONSTANT ALPHA under both rendering modes (pilot), so
    # exported 3-band; the year's NIR remains 2015n only. COMPLEMENT (new key).
    {"key": "2015s", "label": "2015s", "source": "Snohomish Co. (HXIP, acquired 2015-08-07)", "gsd_cm": 30.5,
     "bands": 3, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2015_snoh_1ft_rgb.tif"},
    # 2026-08-23 campaign S17/S19: Snohomish County's own HXIP 1-ft 4-band flights (Aug 2017-08-15/21 and
    # 2019) — genuinely different acquisitions from the May Pictometry mosaics held for those years, with NIR
    # at 2x NAIP resolution. COMPLEMENT keys; 100% coverage incl. water (statewide product).
    {"key": "2017s", "label": "2017s", "source": "Snohomish Co. (HXIP, acquired 2017-08-15/21)", "gsd_cm": 30.5,
     "bands": 4, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2017_snoh_1ft_rgbi.tif"},
    {"key": "2019s", "label": "2019s", "source": "Snohomish Co. (HXIP)", "gsd_cm": 30.5,
     "bands": 4, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2019_snoh_1ft_rgbi.tif"},
    # 2026-08-23 campaign N17: NAIP 2017 (flown 2017-08-15/21, leaf-on), 8 DOQQ quads — an August 4-band
    # acquisition of the year held twice as the May Pictometry mosaic. COMPLEMENT (new year key).
    {"key": "2017n", "label": "2017n", "source": "NAIP (acquired 2017-08-15/21)", "gsd_cm": 100.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2017_naip_1m_rgbi.tif"},
    # 2026-08-23 campaign S18: the WA consortium HXIP 6-inch 2018 flight (city sortie 2018-08-07 per the
    # consortium footprint layer) served by the county's Aerial_2018 ImageServer — the ONLY citywide 2018
    # imagery held, 4-band with real NIR. Fills the 2017->2019 gap year. COMPLEMENT (new key).
    {"key": "2018s", "label": "2018s", "source": "Snohomish Co. (HXIP 6-in, acquired 2018-08-07)", "gsd_cm": 15.2,
     "bands": 4, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2018_snoh_6in_rgbi.tif"},
    # 2026-08-23 REPLACED: 2019_naip_rgbi.tif (69% clip, smoothed re-export) -> 2019_naip_60cm_rgbi.tif
    # (the 8 original Azure DOQQs; acquire_imagery N19f: coverage 100% vs 67%, HF 1.36x common grid, all
    # quads flown 2019-10-11 per the container listing = the S19/HXIP date). The recorded 0.148-px blue
    # registration "loss" vs held was PROVEN a blur artifact of the metric (registration_blur_test.json:
    # smoothing the new file sigma=1 drops it to 0.06; the held re-export reads 0.001) - waiver in the
    # manifest. Old file stays on disk (SUPERSEDED_FILES).
    {"key": "2019n", "label": "2019n", "source": "NAIP (acquired 2019-10-11)", "gsd_cm": 60.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2019_naip_60cm_rgbi.tif"},
    {"key": 2020, "label": "2020", "source": "City of Edmonds", "gsd_cm": 5.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2020_coe_rgb.tif"},
    # 2026-08-24 campaign S20: the county's own 3-inch serving of the 2020 EagleView programme (the anchor's
    # flight family) at full study extent, source-aligned pixels, NO JPEG cache signature (the held CoE copy
    # has one). The ANCHOR (2020_coe_rgb.tif) is NEVER flipped — this is a clean-provenance COMPLEMENT.
    {"key": "2020s", "label": "2020s", "source": "Snohomish Co. (EagleView 3-in)", "gsd_cm": 7.6,
     "bands": 3, "crs_epsg": 2285, "coverage": "100% of city, 98.1% of study extent (measured 2026-08-24)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2020_snoh_3in_rgb.tif"},
    {"key": 2021, "label": "2021", "source": "King County", "gsd_cm": 10.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2021_king_rgb.tif"},
    # 2026-08-23 REPLACED: 2021_snoh_rgbi.tif (53.4% clip served bilinear on an unsnapped grid) ->
    # 2021_snoh_6in_rgbi.tif (native 0.5 ft lattice, nearest, full study extent; acquire_imagery S21:
    # coverage 100% vs 39.5%, common-grid effective 20.05 vs 21.09 cm, HF energy 1.43x = the old serving
    # path blurred it, NIR real, registration 0.006 px, PSNR 37.6 = same flight). Old file stays on disk
    # (SUPERSEDED_FILES in qc/phase4_catalog_check.py). Tier stays pinned per tier_for().
    {"key": "2021s", "label": "2021s", "source": "Snohomish Co.", "gsd_cm": 15.2, "tier": "coarse",
     "bands": 4, "crs_epsg": 2285, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2021_snoh_6in_rgbi.tif"},
    # 2026-08-23 campaign N21: NAIP 2021 (flown 2021-07-13, mid-July leaf-on), 8 DOQQ quads at 60 cm —
    # the third NAIP epoch, between the held October 2019n and 2023n. COMPLEMENT (new year key).
    {"key": "2021n", "label": "2021n", "source": "NAIP (acquired 2021-07-13)", "gsd_cm": 60.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2021_naip_60cm_rgbi.tif"},
    {"key": 2022, "label": "2022", "source": "City of Edmonds", "gsd_cm": 5.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2022_coe_rgb.tif"},
    # 2026-08-24 campaign S22: as 2020s for 2022. COMPLEMENT to the CoE MrSID copy.
    {"key": "2022s", "label": "2022s", "source": "Snohomish Co. (EagleView 3-in)", "gsd_cm": 7.6,
     "bands": 3, "crs_epsg": 2285, "coverage": "100% of city, 98.1% of study extent (measured 2026-08-24)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2022_snoh_3in_rgb.tif"},
    # 2026-08-23 REPLACED: 2023_naip_rgbi.tif (69% clip; a smoothed service re-export with band 4 tagged
    # alpha) -> 2023_naip_60cm_rgbi.tif (the 8 original Azure DOQQs mosaicked; acquire_imagery N23f:
    # coverage 100% vs 67%, HF energy 1.41x on a common grid, NIR real NDVI p90 0.53; all 8 quads flown
    # 2023-10-07 per the container listing). Old file stays on disk (SUPERSEDED_FILES).
    {"key": "2023n", "label": "2023n", "source": "NAIP (acquired 2023-10-07)", "gsd_cm": 60.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "100% of study extent (measured 2026-08-23)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2023_naip_60cm_rgbi.tif"},
    {"key": 2023, "label": "2023", "source": "King County", "gsd_cm": 10.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2023_king_rgb.tif"},
    {"key": 2024, "label": "2024", "source": "City of Edmonds", "gsd_cm": 5.0,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2024_coe_rgb.tif"},
    # 2026-08-24 campaign S24: as 2020s for 2024. COMPLEMENT to the CoE MrSID copy.
    {"key": "2024s", "label": "2024s", "source": "Snohomish Co. (EagleView 3-in)", "gsd_cm": 7.6,
     "bands": 3, "crs_epsg": 2285, "coverage": "100% of city, 98.1% of study extent (measured 2026-08-24)",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2024_snoh_3in_rgb.tif"},
]

# ── Pre-2000 holdings — DOCUMENTARY ONLY, deliberately NOT in YEAR_CATALOG ────
# These files sit in the imagery mirror but had NO catalog entry, which is why
# "the pipeline is limited to 2000" is literally true: no entry, no tier, no
# path resolution (found 2026-08-27 while extracting the degraded-imagery lit
# review, Reports/DEGRADED_IMAGERY_RESEARCH_2026-08-27.md).
#
# They are registered HERE rather than in YEAR_CATALOG on purpose. Consumers
# iterate the catalog wholesale — e.g. make_building_masks.py builds a mask for
# every entry — so appending these would silently expand the modelled series and
# start processing years nobody has approved. Project scope is fixed at
# 2000-2024 (IMAGERY_FACTS header, 2026-08-19). PROMOTING an entry from this
# list into YEAR_CATALOG is the deliberate act that changes scope; it is Kam's
# call, not a side effect of documenting what exists.
#
# gsd_cm below is TRUE GROUND resolution, MEASURED 2026-08-27 from each file's
# own centre latitude — never the raw CRS unit. Both unit traps are present in
# this set and both have burned this project before (the gsd_cm defect,
# WORKPLAN 1.5; the 2.215x Mercator AREA inflation, 2026-08-27):
#   EPSG:2285  = US survey FEET  -> x 0.3048006096
#   EPSG:3857  = Mercator metres -> x cos(47.82 deg) = 0.6714 at Edmonds
PRE2000_CATALOG = [
    {"key": 1990, "label": "1990", "source": "Snohomish Co.", "gsd_cm": 304.8,
     "bands": 1, "crs_epsg": 2285, "coverage": "unmeasured",
     "native_file": "1990_snoh_10ft_pan.tif",
     "note": "10 US survey ft. Panchromatic. Almost certainly too coarse to be useful "
             "(a 6 m crown is ~2 px); registered for completeness only."},
    {"key": 1996, "label": "1996", "source": "Snohomish Co.", "gsd_cm": 100.0,
     "bands": 3, "crs_epsg": 2285, "coverage": "5.7% zero pixels in a 40x-decimated read",
     "native_file": "1996_snoh_1m_rgb.tif",
     "note": "3.2808 US survey ft = 1.000 m. RGB, NOT grayscale — the lit review assumed "
             "1996 was panchromatic, so its colorization thread does not apply to this year. "
             "This is the genuine ~100 cm target if the series is ever extended."},
    {"key": "1998s", "label": "1998s", "source": "Snohomish Co.", "gsd_cm": 91.4,
     "bands": 1, "crs_epsg": 2285, "coverage": "unmeasured",
     "native_file": "1998_snoh_3ft_pan.tif",
     "note": "3 US survey ft. Panchromatic — the historical-grayscale literature applies "
             "HERE, not to 1996."},
    {"key": 1998, "label": "1998", "source": "King County", "gsd_cm": 40.1,
     "bands": 1, "crs_epsg": 3857, "coverage": "0.0% zero pixels in a 40x-decimated read",
     "native_file": "1998_king_pan.tif",
     "note": "40.1 cm true (0.5972 Mercator m) — same King product line as 2000/2002, far "
             "finer than the lit review's 1 m assumption. Single-band."},
    # 1936_king_pan.tif is DELIBERATELY ABSENT. It carries a CRS and a transform and reads
    # as real imagery (37% zeros, so IMAGERY_FACTS' 2026-08-19 'NOT an empty shell'
    # correction stands), but Kam states it is NOT GEOREFERENCED (2026-08-27). A rough
    # world file on a scan is worse than no entry: it would align plausibly and be wrong.
    # Verify registration against a known feature before it is ever listed here.
]

# 2020 is the anchor (already segmented in Phase 3); Phase 4 does the other 17.
ANCHOR_LABEL = "2020"


# ── Resolution-tier logic ─────────────────────────────────────────────────────
# Drives tiling density. Coarse years get no held-out test split (too few tiles);
# their IoU is reported in-sample and feeds Decision Gate 4.

def tier_of(gsd_cm):
    if gsd_cm <= 15.0:
        return "fine"      # 5.0, 10.0
    if gsd_cm <= 35.0:
        return "medium"    # 20.1
    return "coarse"        # 40.1, 60.7


def tier_for(entry):
    """Tier for a catalog entry: an EXPLICIT "tier" wins over the derived one.

    gsd_cm was corrected to TRUE GROUND RESOLUTION on 2026-08-18 (see the note
    on YEAR_CATALOG). Re-deriving tier from the corrected numbers moves ONLY the
    two Snohomish years, 2016 and 2021s, from coarse to medium — and that is not
    a harmless reclassification:

        citywide = (tier == "coarse" or --force-citywide)      [cli.py]

    so "medium" would switch them off the citywide 2020-mask label path and onto
    per-site CROWN POLYGONS — the ones CLAUDE.md records as overwritten with
    accept-all test data. It would also silently invalidate every 2016 result in
    CHATLOG STATE, all of which were produced under the coarse recipe.

    So those two carry "tier": "coarse" explicitly. The metadata is now true AND
    the behaviour is unchanged; re-tiering them becomes a deliberate one-line
    edit, taken when the crown polygons are trustworthy, rather than a side
    effect of fixing a units bug.
    """
    t = entry.get("tier")
    return t if t else tier_of(entry["gsd_cm"])
TIER_TILE_PARAMS = {
    #          stride  neg_rate  test_frac  has_test
    "fine":   dict(stride=512, neg_rate=0.15, test_frac=0.20, has_test=True),
    "medium": dict(stride=256, neg_rate=0.15, test_frac=0.20, has_test=True),
    # neg_rate raised 0.30→0.60 (Fix 3) to lift negative representation. Used only
    # by the legacy 6-site coarse path (--coarse-site-tiling); the default coarse
    # path is now city-wide stratified tiling, which balances negatives by bin.
    "coarse": dict(stride=128, neg_rate=0.60, test_frac=0.00, has_test=False),
}

# Early-stop / best-checkpoint selection metric per tier.
#   "val_bce"    → minimize (fine/medium; stable log-loss with plenty of tiles)
#   "val_iou"    → MAXIMIZE, IoU at a FIXED 0.5 threshold.
#   "val_iou_bt" → MAXIMIZE, IoU at the BEST threshold on a swept grid (coarse).
#     Why coarse switched val_iou→val_iou_bt: BCE on the canopy-scarce coarse pool
#     with clamped pos_weight calibrates predictions toward the low base rate, so
#     the probability scale drifts BELOW 0.5 after a few epochs. val_iou@0.5 then
#     reads a false "collapse" (→0) even though the model keeps improving and
#     scores ~0.58 at threshold 0.3–0.4 (2016 diagnostic: E7 val_iou@0.5=0.004 but
#     iou_bt=0.58@0.4). Selecting on val_iou@0.5 froze the checkpoint at an
#     undertrained epoch. Best-threshold IoU is threshold-independent (== val_iou
#     when 0.5 is optimal) and tracks true model quality. Inference still picks its
#     own operating point via best_f1, so training + deployment agree.
TIER_EARLYSTOP = {"fine": "val_bce", "medium": "val_bce", "coarse": "val_iou_bt"}

# Per-tier segmentation loss mode (Edit F): "bce_dice" (default = run-5 baseline)
# or "focal_dice". Coarse stays bce_dice by default so we reproduce run 5; the
# --loss-mode CLI flag overrides the COARSE entry to A/B focal against the
# baseline (loss-only change → same tiles → measurable). Fine/medium unaffected.
TIER_LOSS_MODE = {"fine": "bce_dice", "medium": "bce_dice", "coarse": "bce_dice"}
PER_YEAR_STEPS = ["labels", "tile", "train", "evaluate", "inference", "postproc"]
ALL_STEPS = PER_YEAR_STEPS + ["consistency"]


# ══════════════════════════════════════════════════════════════════════════════
#  M06 — NIR AS THE 4th INPUT CHANNEL   (APPENDED 2026-08-26; nothing above this
#  line was edited — config.py is pure-move protected)
# ══════════════════════════════════════════════════════════════════════════════
# `--hs-source nir` reuses the whole 4th-channel machinery (tiling bakes band 4 +
# stamps HS_SOURCE, conv-1 is inflated 3→4 zero-init, HS_DROPOUT keeps a pure-RGB
# pathway, train/eval/inference adopt the tag/ckpt value) but takes band 4 from
# **the year's own ortho**, not from a LIDAR master. Consequences of that swap:
#   * NO entry is added to HS_PATHS — there is no raster to stage, and no warp:
#     NIR is read from the SAME window of the SAME file as the RGB, so it is
#     co-registered by construction (the LIDAR path has to reproject per tile).
#   * Only the TEN 4-band acquisitions can supply it (YEAR_CATALOG "bands": 4 —
#     2015n 2016 2017n 2017s 2018s 2019n 2019s 2021n 2021s 2023n). Every other
#     year FAILS LOUD under --hs-source nir; substituting RGB or a LIDAR band
#     silently is exactly the failure this mode exists to avoid.
#   * Unlike the ~2016 LIDAR snapshot, this channel is contemporaneous with the
#     RGB — no temporal drift, but also no coverage outside those ten years.
# Rationale (MACHINERY_AUDIT_2026-08 M06): NDVI separability is near year-
# invariant across this archive (AUROC 0.835-0.886, sd 0.016) while RGB swings
# 2.5x (sd 0.057); the deployed per-year models never see NIR at all.
HS_SOURCE_NIR = "nir"

# /255 non-zero mean/std of band 4, POOLED over the eight healthy-floor NIR
# acquisitions (2015n/2021s excluded — see NIR_LIFTED_FLOOR_YEARS). MEASURED
# 2026-08-26 from decimated (~3000 px long side) full-extent band-4 reads of the
# local mirror D:\edmonds-pipeline\Imagery: per-acquisition means 0.276-0.466
# (within-acquisition sd 0.291, between-acquisition sd 0.068), pooled as
# sqrt(mean(var) + var(means)). One global entry — same contract as the ImageNet
# RGB stats, which are likewise fixed while measured RGB brightness swings across
# years; the per-year fine-tune and HS_DROPOUT absorb the residual offset.
HS_STATS[HS_SOURCE_NIR] = ([0.3752], [0.2991])

# IMAGERY_FACTS §12 (MEASURED 2026-08-26, nir-stack build): two of the ten NIR
# acquisitions have LIFTED BLACK POINTS — 2015n NIR p1 = 33 DN (traced to the
# source NAIP DOQQs) and 2021s p1 = 28 DN (confirmed on both county servings of
# the flight), vs 1-16 DN on the healthy eight. Within-band structure and
# vegetation LOCATION stay honest there, but the absolute level does not — so
# these two are excluded from the pooled stats above and from the M06 A/B arm
# (queue_nir_m06.yaml). Tiling only WARNS: the exclusion is a campaign-design
# decision, not an engine law.
NIR_LIFTED_FLOOR_YEARS = {"2015n", "2021s"}


def nir_mode():
    """True when band 4 is the year's own NIR band (`--hs-source nir`).

    Reads the LIVE module global, so it tracks the value cli/tiles/ckpts adopt at
    runtime — never capture it via `from config import *`.
    """
    return HS_SOURCE == HS_SOURCE_NIR


# ══════════════════════════════════════════════════════════════════════════════
#  chm2 — CANOPY HEIGHT REBUILT FROM THE RAW 2016 POINTS   (APPENDED 2026-08-29;
#  nothing above this line was edited — config.py is pure-move protected. The
#  CLI derives --hs-source choices from sorted(HS_STATS), so these two
#  assignments are all that is needed to make it selectable. _tile_signature
#  hashes config.HS_SOURCE — the SELECTED value, not these dicts — so adding a
#  key invalidates no existing tile cache and re-tiles nothing.)
# ══════════════════════════════════════════════════════════════════════════════
# WHY: band 4 is worth ~10 pp of recall (4-band .6989 vs 3-band .5990 at matched
# precision, common 198.8 Mpx footprint) and its value concentrates in SMALL
# crowns (+7.3 pp <5 m2, +8.0 pp 5-10 m2, +0.3 pp >100 m2). The raster carrying
# it, HS_PATHS["chm"], is 3DEP HAG bilinear-upsampled from ~2 m onto a 1 m
# EPSG:3857 grid (= 67 cm ground, Mercator-distorted). chm2 rebuilds the height
# model from the 863.5M-return 2016 USGS COPC cloud on a 0.5 m EPSG:26910 grid
# with NO reprojection, per-cell MAX height above ground, and the IDENTICAL uint8
# encoding (DN = 1 + round(clip(h,0,50.6)/0.2), 0 = nodata) so the A/B is one
# variable.  Builder: qc/build_chm2_2016.py.
#
# MEASURED 2026-08-29 against the raw points (interpolation-free: max return vs
# min class-2 return in the SAME 2 m cell, 8.82M cells) — the old raster does NOT
# read low on apexes as IMAGERY_FACTS 8.3 states, it reads HIGH almost
# everywhere, because its effective support is ~3-6 m and it reports a
# NEIGHBOURHOOD MAXIMUM rather than the height at the cell:
#   * on ground the points measure as BARE (0.14 m), old says 4.90 m mean, and
#     calls 57.3% of it taller than 2 m;
#   * the +4.1 to +5.4 m offset holds in EVERY height bin, 0 m through 30 m;
#   * zero shift minimises MAE, so it is not misregistration (r = 0.889);
#   * independent check on verified_background_lidar_2005_2016.tif (flat in BOTH
#     the 2005 and 2016 clouds, eroded 6 m, 691,905 cells): old mean 0.86 m and
#     8.82% of certified-FLAT ground called taller than 2 m; chm2 mean 0.19 m
#     and 0.01%.
# Coverage is NOT the confound: 93.98% of the city polygon vs the old 95.13%, and
# 84.1% of that 1.15 pp deficit is cells the old itself calls <2 m (its bilinear
# bleed across shoreline/water nodata edges). The larger gap over the wider
# extent is acquisition, not method — chm2 covers 91.41% inside the footprint of
# the 40 laz tiles actually acquired, and nothing outside it.
HS_PATHS["chm2"] = IMAGERY_DIR / "lidar_chm2_2016_50cm.tif"

# /255 non-zero mean/std, computed by the SAME procedure as every entry above
# (fetch_build_chm.py:153 — nz = arr[arr>0]/255, mean/std over the whole written
# raster). Lower than "chm" because chm2 does not inflate open ground: its DN-1
# (flat) share is 27.9% against the old raster's 10.1%.
HS_STATS["chm2"] = ([0.1437], [0.2003])

# ══════════════════════════════════════════════════════════════════════════════
#  CHECKPOINT-SELECTION SMOOTHING   (APPENDED 2026-08-29; nothing above this line
#  was edited — config.py is pure-move protected. This is a TRAINING parameter:
#  _tile_signature (tiling.py:629) hashes neither it nor the epoch budgets, so
#  changing it invalidates NO tile cache and re-tiles nothing. Verified
#  empirically — see the flag's --select-smooth help text.)
# ══════════════════════════════════════════════════════════════════════════════
# WHY: the deployed checkpoint is today the SINGLE BEST epoch by the early-stop
# metric, measured on ~120 validation tiles. Taking a max over 20-50 noisy epochs
# both inflates the reported validation number and adds run-to-run variance — you
# select whichever epoch drew a lucky val batch. MEASURED symptom: the chosen
# threshold wobbled .440-.499 across five otherwise identical 2009 runs.
#
# SELECT_SMOOTH_K > 1 picks the deployed epoch by a K-epoch CENTRED moving
# average of that same metric (edge-truncated, never zero-padded), then saves
# that epoch's REAL weights — weights are never averaged. It changes the
# SELECTION SIGNAL ONLY: training, optimiser, LR schedule, and the early-stop
# patience counter all still run off the RAW per-epoch value, and Phase B still
# resumes from the RAW-best Phase-A checkpoint, so K is one variable.
#
# 1 = today's behaviour exactly (raw per-epoch peak). At K=1 the selector object
# is never even constructed, so the default path is the historical code path.
# Odd values only; the CLI rounds an even K up and says so.
SELECT_SMOOTH_K = 1

# ─────────────────────────────────────────────────────────────────────────────
#  chm2005 — CANOPY HEIGHT FROM THE RAW 2005 PSLC POINT CLOUD  (APPENDED 2026-08-29)
#
#  WHY. Every height-channel run to date fed a ~2016 raster to imagery from
#  2000-2024. For the early half of the archive that is a 7-16 year mismatch:
#  the comment at "best for 2015-2017 imagery; highest drift for 2000-2012"
#  says so, and CHM_CREDIBLE_YEARS excludes 2009 outright — while the pipeline
#  still used that raster as an INPUT for 2009. chm2005 is temporally native to
#  roughly half the archive. Builder: qc/build_chm2005.py.
#
#  MEASURED, not assumed (qc/audit_lidar_2005_coverage.py, 2026-08-29):
#    * 46 non-empty PSLC tiles, median 1.68 pts/m² — reproducing IMAGERY_FACTS
#      exactly. The SAME audit measured 2016's local density at 17.47 pts/m²,
#      not the 4-5 recorded there (that figure is a dataset-wide average over
#      13,205 tiles, not these 41). The real inter-epoch gap is ~10.4x, not ~3x.
#    * ground-return occupancy 44.6 / 69.5 / 80.3 / 86.5% at 1 / 2 / 3 / 4 m.
#      The 2016 build used a 2 m ground grid at ~80% occupancy; 2005 reaches
#      that only at 3 m, and the builder needs the ground grid to nest inside
#      the canopy grid, so 2.0 m canopy / 4.0 m ground is the nesting-compatible
#      pair that MEETS the precedent (86.5%) instead of undershooting it.
#
#  VALIDATED (qc/validate_chm2005.py) on ground certified flat in BOTH epochs
#  and eroded 6 m — the test that exposed the original raster:
#      chm2005  0.48 m mean, asserts >2 m on  0.17% of certified-flat ground
#      chm2     0.19 m mean,                  0.01%
#      chm(old) 0.86 m mean,                  8.82%     <- the defect
#  52x better than the raster it replaces for early years; 17x behind chm2,
#  which is what 4x coarser cells and 10x lower density predict, not a defect.
#
#  THE TRADE, STATED HERE SO IT IS NOT REDISCOVERED: chm2005 is 4x COARSER than
#  chm2, and the height channel's measured value is CONCENTRATED IN SMALL CROWNS
#  (+7.3 pp under 5 m² ≈ 2.2 m across) — the size of its own cell. It buys
#  temporal correctness and pays in resolution. Which wins is EMPIRICAL and
#  untested; do not assume either way.
#
#  CRS is EPSG:3740 (NAD83(HARN)/UTM 10N), the cloud's declared CRS, not the
#  26910 chm2 carries. Sub-cell difference; the engine reprojects on read.
HS_PATHS["chm2005"] = IMAGERY_DIR / "lidar_chm2005_2m.tif"
# nonzero DN/255 mean/std, measured on the raster itself. The same routine
# reproduces chm2's ([0.1437],[0.2003]) exactly, which is why these are trusted.
HS_STATS["chm2005"] = ([0.1554], [0.1998])

#  PER-YEAR HEIGHT SOURCE — opt-in via `--hs-source auto`, NEVER the default.
#  Making this the default would silently change every future run and break
#  comparability with every existing baseline, which is a re-baselining decision,
#  not a config tweak. Left explicit so an arm that uses it says so in its argv.
#  Split at 2013: the 2005 cloud was flown 2004-11..2005-07 and the 2016 cloud
#  2016-03..2017-06, so 2013 is very nearly equidistant and later years are
#  unambiguously closer to 2016.
CHM_BY_YEAR_DEFAULT = "chm2"
CHM_BY_YEAR = {y: "chm2005" for y in
               ("2000", "2002", "2003s", "2005", "2006s", "2007", "2009",
                "2011s", "2012s")}


def chm_for_year(year, default=None):
    """Temporally-nearest height source for a year label. Used only when the
    caller asks for it (`--hs-source auto`); returns the default otherwise."""
    return CHM_BY_YEAR.get(str(year), default or CHM_BY_YEAR_DEFAULT)
