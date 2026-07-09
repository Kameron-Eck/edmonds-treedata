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

YEAR_CATALOG = [
    {"key": 2000, "label": "2000", "source": "King County", "gsd_cm": 59.7,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2000_king_rgb.tif"},
    {"key": 2002, "label": "2002", "source": "King County", "gsd_cm": 59.7,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2002_king_rgb.tif"},
    {"key": 2005, "label": "2005", "source": "King County", "gsd_cm": 29.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2005_king_rgb.tif"},
    {"key": 2007, "label": "2007", "source": "King County", "gsd_cm": 29.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2007_king_rgb.tif"},
    {"key": 2009, "label": "2009", "source": "King County", "gsd_cm": 29.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2009_king_rgb.tif"},
    {"key": 2013, "label": "2013", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2013_king_rgb.tif"},
    {"key": 2015, "label": "2015", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2015_king_rgb.tif"},
    {"key": 2016, "label": "2016", "source": "Snohomish Co.", "gsd_cm": 50.0,
     "bands": 4, "crs_epsg": 2285, "coverage": "67%",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2016_snoh_rgbi.tif"},
    {"key": 2017, "label": "2017", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2017_coe_rgb.tif"},
    {"key": 2019, "label": "2019", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2019_king_rgb.tif"},
    {"key": "2019n", "label": "2019n", "source": "NAIP", "gsd_cm": 60.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2019_naip_rgbi.tif"},
    {"key": 2020, "label": "2020", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2020_coe_rgb.tif"},
    {"key": 2021, "label": "2021", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2021_king_rgb.tif"},
    {"key": "2021s", "label": "2021s", "source": "Snohomish Co.", "gsd_cm": 50.0,
     "bands": 4, "crs_epsg": 2285, "coverage": "67%",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2021_snoh_rgbi.tif"},
    {"key": 2022, "label": "2022", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2022_coe_rgb.tif"},
    {"key": "2022n", "label": "2022n", "source": "NAIP", "gsd_cm": 60.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2022_naip_rgbi.tif"},
    {"key": 2023, "label": "2023", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2023_king_rgb.tif"},
    {"key": 2024, "label": "2024", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2024_coe_rgb.tif"},
]

# 2020 is the anchor (already segmented in Phase 3); Phase 4 does the other 17.
ANCHOR_LABEL = "2020"


# ── Resolution-tier logic ─────────────────────────────────────────────────────
# Drives tiling density. Coarse years get no held-out test split (too few tiles);
# their IoU is reported in-sample and feeds Decision Gate 4.

def tier_of(gsd_cm):
    if gsd_cm <= 15.0:
        return "fine"      # 7.5, 14.9
    if gsd_cm <= 35.0:
        return "medium"    # 29.9
    return "coarse"        # 50.0, 59.7, 60.0
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
