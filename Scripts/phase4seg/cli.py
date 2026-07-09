import argparse
import sys
import pandas as pd

from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (
    discover_site_footprints, entry_for, remaining_entries, _tag_sfx,
    timer_summary,
)
from phase4seg.labels import step_labels
from phase4seg.tiling import step_tile
from phase4seg.core import resolve_p3_ckpt, step_train, step_evaluate, step_inference
from phase4seg.postproc import step_postproc, step_consistency


def _resolve_years(args):
    if args.year:
        labels = [y.strip() for y in args.year.split(",") if y.strip()]
        for lab in labels:
            entry_for(lab)  # validate
        if ANCHOR_LABEL in labels:
            print(f"  (note: {ANCHOR_LABEL} is the Phase 3 anchor — already done)")
        return [entry_for(lab) for lab in labels]
    entries = remaining_entries()
    if args.tier:
        entries = [e for e in entries if tier_of(e["gsd_cm"]) == args.tier]
    return entries


def print_summary(entries):
    print(f"\n{'='*65}\n  PHASE 4 — Per-Year Semantic Fine-Tuning\n{'='*65}")
    print(f"\n  {'Year':<7}{'GSD':>7}{'Tier':>8}{'Model':>8}{'Mask':>7}{'IoU':>8}")
    print(f"  {'-'*7}{'-'*7}{'-'*8}{'-'*8}{'-'*7}{'-'*8}")
    eval_df = pd.read_csv(EVAL_CSV) if EVAL_CSV.exists() else pd.DataFrame()
    for e in entries:
        lab = e["label"]
        model_ok = (MODELS_DIR / f"sem_best_{lab}{_tag_sfx()}.pt").exists()
        mask_ok = (MASKS_DIR / f"edmonds_canopy_mask_{lab}{_tag_sfx()}.tif").exists()
        iou = ""
        if not eval_df.empty:
            sub = eval_df[(eval_df["year"].astype(str) == lab) &
                          (eval_df["scope"] == "OVERALL")]
            if len(sub):
                iou = f"{float(sub.iloc[0]['iou']):.3f}"
        print(f"  {lab:<7}{e['gsd_cm']:>6.1f}{tier_of(e['gsd_cm']):>8}"
              f"{'✓' if model_ok else '—':>8}{'✓' if mask_ok else '—':>7}{iou:>8}")
    print(f"""
  ◆ DECISION GATE 4 (Month 9):
    Do coarse-year masks (2000, 2002, and 50–60cm years) meet the
    minimum IoU? Coarse years tiled city-wide (the default) now report
    OUT-OF-SAMPLE IoU from a geographically-blocked held-out test block
    (>520 m from train); only legacy --coarse-site-tiling runs and
    partial-coverage years that fell back to a degraded split remain
    in-sample (see eval_scope in {EVAL_CSV.name}). For each coarse year
    decide: include in temporal analysis / exclude / flag low-confidence.

  NEXT: Phase 6 — temporal crown linking + per-crown canopy-fraction
        assessment projects the canonical crown layer onto these masks.
""")
    print(f"{'='*65}")


def main():
    # Declared up top: HS_DROPOUT/HS_SOURCE are read below as argparse defaults,
    # and Python forbids any use before the `global` declaration.

    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    p = argparse.ArgumentParser(
        description="Phase 4 — Per-Year Semantic Segmentation Fine-Tuning")
    p.add_argument("--year", type=str, default=None,
                   help="Comma-separated year labels (e.g. 2017 or 2005,2007,2009). "
                        "Default: all 17 remaining.")
    p.add_argument("--tier", choices=["fine", "medium", "coarse"], default=None,
                   help="Restrict to one resolution tier.")
    p.add_argument("--step", choices=ALL_STEPS, default=None,
                   help="Run a single step (default: full per-year pipeline + "
                        "consistency).")
    p.add_argument("--skip-training", action="store_true",
                   help="Skip fine-tuning — use existing per-year checkpoints.")
    p.add_argument("--skip-inference", action="store_true",
                   help="Stop after evaluation.")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--no-compile", action="store_true",
                   help="Skip torch.compile in training — avoids the slow first-build "
                        "warmup (the dynamo/inductor import that can look frozen for "
                        "1-2 min). Steadier for unattended/L4 overnight runs; slightly "
                        "slower steady-state. Eval/inference never compile regardless.")
    p.add_argument("--ckpt", type=str, default=None,
                   help="Override the Phase 3 fine-tune-start checkpoint.")
    p.add_argument("--vi", action="store_true",
                   help="Use 6-channel RGB+VI input (must match the Phase 3 ckpt).")
    p.add_argument("--hillshade", dest="hillshade", action="store_true", default=True,
                   help="Bake a LIDAR structure raster as a 4th input channel at "
                        "tiling time, all years (default on). The model "
                        "auto-matches the tile band count; Phase-3 conv-1 is "
                        "inflated 3→4 (zero-init). Re-tile to (de)activate.")
    p.add_argument("--no-hillshade", dest="hillshade", action="store_false",
                   help="RGB-only tiles (no structure channel).")
    p.add_argument("--hs-source", choices=sorted(HS_STATS), default="chm",
                   help="Structure raster for band 4 (tiling-time choice, default "
                        "chm): 'chm' = REAL 3DEP canopy height in metres (U8-scaled, "
                        "the true grass/tree discriminator); "
                        "'struct' = terrain-cancelled first-return minus "
                        "bare-earth (+127) — slope illumination cancels, grass is "
                        "flat, canopy texture kept; 'fr' = raw first-return "
                        "hillshade (v025 behaviour). Tiles are tagged with the "
                        "source; train/eval/inference adopt the tag/ckpt value, "
                        "so this flag only matters at --step tile.")
    p.add_argument("--hs-dropout", type=float, default=config.HS_DROPOUT,
                   help=f"Training-only channel dropout: per-sample prob of "
                        f"blanking the structure band to its mean (default "
                        f"{config.HS_DROPOUT}). Keeps a pure-RGB pathway so stale-"
                        f"snapshot years degrade gracefully. 0 disables.")
    p.add_argument("--coarse-pos-weight-max", type=float,
                   default=config.COARSE_POS_WEIGHT_MAX,
                   help=f"Clamp ceiling on the coarse-tier BCE pos_weight (default "
                        f"{config.COARSE_POS_WEIGHT_MAX}). The raw pool-ratio value is "
                        f"logged each run; raise toward it to re-weight canopy "
                        f"against a background-heavy tile pool. Train-only — no "
                        f"re-tile needed.")
    p.add_argument("--lr-phase-a", type=float, default=config.LR_PHASE_A,
                   help=f"Phase-A (frozen-encoder) learning rate (default "
                        f"{config.LR_PHASE_A}). Lower (e.g. 2e-5) if the trainable "
                        f"inflated input conv destabilises training on a strong "
                        f"4th channel. Train-only.")
    p.add_argument("--bce-weight", type=float, default=config.BCE_WEIGHT,
                   help=f"Weight on the BCE term of the bce_dice loss (default "
                        f"{config.BCE_WEIGHT}). Train-only.")
    p.add_argument("--dice-weight", type=float, default=config.DICE_WEIGHT,
                   help=f"Weight on the soft-Dice term of the bce_dice loss "
                        f"(default {config.DICE_WEIGHT}). Dice pulls the probability "
                        f"scale down on a background-heavy pixel distribution; "
                        f"set 0.0 to isolate BCE. Train-only.")
    p.add_argument("--epochs-phase-a", type=int, default=config.EPOCHS_PHASE_A,
                   help=f"Phase-A epoch budget (default {config.EPOCHS_PHASE_A}). Lower "
                        f"(e.g. 8) for fast diagnostic runs — the cliff appears by "
                        f"E6, so a short Phase A shows stable-vs-collapse quickly.")
    p.add_argument("--epochs-phase-b", type=int, default=config.EPOCHS_PHASE_B,
                   help=f"Phase-B epoch budget (default {config.EPOCHS_PHASE_B}). Set 0 "
                        f"to skip Phase B entirely (diagnostic runs don't need it "
                        f"— it never recovers from a Phase-A collapse).")
    p.add_argument("--freeze-encoder-bn", dest="freeze_encoder_bn",
                   action="store_true", default=config.FREEZE_ENCODER_BN,
                   help="Pin the frozen encoder's BatchNorm to its pretrained "
                        "running stats during Phase A (stop it tracking batch "
                        "stats). Standard transfer-learning practice; addresses "
                        "the fixed-epoch val_iou cliff caused by BN drift under a "
                        f"trainable input-conv + off-distribution pool. Train-only. "
                        f"Default {config.FREEZE_ENCODER_BN}.")
    p.add_argument("--no-freeze-encoder-bn", dest="freeze_encoder_bn",
                   action="store_false",
                   help="Disable the frozen-encoder BN pin (legacy behaviour; for "
                        "A/B testing the v039 default).")
    p.add_argument("--force-retile", action="store_true",
                   help="Rebuild the city-wide tile set even when a complete one "
                        "for the current sampling constants already exists. "
                        "Default: reuse existing tiles (idempotent — a re-run of "
                        "the full pipeline after a lost session skips the ~20-min "
                        "scan). Use after editing sampling constants if you want "
                        "to force a rebuild without changing them.")
    p.add_argument("--dry-run", action="store_true",
                   help="Plan only — no writes.")
    p.add_argument("--check", action="store_true",
                   help="Local pre-flight: validate the command line, then exit 0 "
                        "without importing torch or running any step. Used by "
                        "phase4seg_preflight.py to catch arg/import errors off-Colab.")
    p.add_argument("--max-tiles", type=int, default=None,
                   help="Cap each year's tile set to N (canopy tiles kept first, "
                        "then negatives). For fast test runs.")
    p.add_argument("--stride", type=int, default=None,
                   help="Override the per-tier tiling stride (smaller = more "
                        "overlapping tiles → more tiles).")
    p.add_argument("--site-buffer", type=float, default=0.0,
                   help="Pad each site footprint by N map units (EPSG:3857 ≈ m) "
                        "before cropping → larger crops → more tiles. Only the "
                        "part falling inside the reviewed regions becomes "
                        "labeled; beyond that is IGNORE. ~200 matches the prep "
                        "buffer.")
    p.add_argument("--coarse-site-tiling", action="store_true",
                   help="Coarse tier: use the legacy 6-site tiling instead of the "
                        "default city-wide stratified tiling (Fix 3). Ignored for "
                        "fine/medium tiers and when --anchor-labels is set.")
    p.add_argument("--anchor-labels", action="store_true",
                   help="Build masks from the 2020 full-city canopy prob raster "
                        "(phase3/edmonds_canopy_prob_2020.tif) instead of the "
                        "review crowns/regions — labels the whole crop, so the "
                        "expanded sites are fully usable.")
    p.add_argument("--prob-hi", type=float, default=0.6,
                   help="--anchor-labels: 2020 prob ≥ this → canopy (1).")
    p.add_argument("--prob-lo", type=float, default=0.4,
                   help="--anchor-labels: 2020 prob ≤ this → background (0); "
                        "values between prob-lo and prob-hi → IGNORE.")
    p.add_argument("--thresh-mode", choices=["best_f1", "precision_floor"],
                   default="best_f1",
                   help="Post-processing operating point (Fix D): 'best_f1' (max-F1 "
                        "threshold, default — nothing changes) or 'precision_floor' "
                        f"(lowest threshold with precision ≥ PRECISION_FLOOR="
                        f"{PRECISION_FLOOR}).")
    p.add_argument("--infer-thresh", type=float, default=None,
                   help="Explicit postproc operating threshold in (0,1); overrides "
                        "--thresh-mode and the eval-CSV best_f1 lookup. Use to LOWER "
                        "an off-year threshold to recover CHM-suppressed canopy, e.g. "
                        "2000: --step postproc --infer-thresh 0.30. Blunt lever — "
                        "prefer an honest reference over the 2020-label best-F1.")
    p.add_argument("--add-canopy-mask", type=str, default=None,
                   help="Path to a canopy_additions_{year}.tif from "
                        "phase4_build_corrected_labels.py (0=no change, 1=ADD canopy, "
                        "2=IGNORE). Layered ADD-ONLY on the coarse 2020-mask label "
                        "path — teaches NIR+CHM-confirmed canopy the conifer-only "
                        "labels miss. One file (built on the 2016 grid) serves 2016 "
                        "and 2000. Coarse-tier only; needs a retile.")
    p.add_argument("--aux-height", action="store_true",
                   help="AUXILIARY HEIGHT reframe: RGB-only input + a 2nd output head that "
                        "PREDICTS canopy height from RGB (masked-L1 vs the CHM), instead of "
                        "feeding CHM as a 4th input band. Bakes tall-vs-flat into the RGB "
                        "features (kills grass FPs, no stale-snapshot). Forces RGB-only input "
                        "+ a retile (height sidecars). Supervised only on CHM-credible years.")
    p.add_argument("--height-lambda", type=float, default=config.HEIGHT_LAMBDA,
                   help="Weight of the auxiliary height loss (--aux-height); small = a "
                        "regularizer. Default %(default)s.")
    p.add_argument("--emit-height", action="store_true",
                   help="(Reserved) With --aux-height, also write a predicted-height raster at "
                        "inference — a bonus diagnostic; not yet wired into step_inference.")
    p.add_argument("--loss-mode", choices=["bce_dice", "focal_dice"], default=None,
                   help="Override the COARSE-tier training loss (Edit F): 'bce_dice' "
                        "(default = run-5 baseline) or 'focal_dice' (focal+dice "
                        "hard-negative emphasis). Loss-only change → run on the same "
                        "tiles to A/B against the baseline. Fine/medium unaffected.")
    p.add_argument("--infer-batch", type=int, default=config.INFER_BATCH,
                   help="Full-city inference batch size (memory knob; output is "
                        "batch-invariant). Default %(default)s fits a 24 GB card; the old "
                        "160 needed 80 GB.")
    p.add_argument("--force-citywide", action="store_true",
                   help="Apply the citywide 2020-mask COARSE recipe (labels + sampler + "
                        "selection metric) to EVERY tier, so only the sensor/GSD varies. "
                        "Removes the tier-recipe confound for cross-year comparison. "
                        "Fine years scan the full ortho → slower tiling; test on one first.")
    p.add_argument("--run-tag", type=str, default=None,
                   help="Suffix all per-year outputs (model/prob/mask/gpkg) with _TAG so "
                        "runs SAVE instead of OVERWRITE — keep variants/recipes for later "
                        "analysis. e.g. --run-tag rgbonly. Score with the QC tools' --prob.")
    args = p.parse_args(filtered)

    if args.check:
        print("[preflight] arguments parsed OK — command is valid.")
        return

    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "Scripts" / "logs"
    SCRIPT_NAME = "phase4_semantic_finetune"

    config.USE_VI = bool(args.vi)
    config.USE_HILLSHADE = bool(args.hillshade)
    config.HS_SOURCE = args.hs_source          # tiling-time; tiles/ckpts override later
    config.HS_DROPOUT = max(0.0, float(args.hs_dropout))
    # Collapse-fix levers (v031/v033): flag-driven so loss/LR experiments need no
    # script edit between runs. Defaults reproduce v030 exactly.
    config.COARSE_POS_WEIGHT_MAX = float(args.coarse_pos_weight_max)
    config.LR_PHASE_A = float(args.lr_phase_a)
    config.BCE_WEIGHT = float(args.bce_weight)
    config.DICE_WEIGHT = float(args.dice_weight)
    # Epoch budgets (v034): flag-driven for fast diagnostic runs. Defaults =
    # full schedule. --epochs-phase-b 0 skips Phase B (never rebuilt below).
    config.EPOCHS_PHASE_A = max(1, int(args.epochs_phase_a))
    config.EPOCHS_PHASE_B = max(0, int(args.epochs_phase_b))
    config.FREEZE_ENCODER_BN = bool(args.freeze_encoder_bn)
    # Module-level fallback; the per-step functions (train/evaluate/inference)
    # override IN_CHANNELS from the actual tile/ckpt band count.
    config.IN_CHANNELS = 3 + (len(VI_NAMES) if config.USE_VI else 0) + (1 if config.USE_HILLSHADE else 0)
    config.THRESH_MODE = args.thresh_mode
    config.INFER_THRESH_OVERRIDE = args.infer_thresh
    config.ADD_CANOPY_MASK = args.add_canopy_mask
    # --aux-height reframe: height becomes a TARGET, so the input goes RGB-only.
    config.AUX_HEIGHT = bool(args.aux_height)
    config.HEIGHT_LAMBDA = max(0.0, float(args.height_lambda))
    config.EMIT_HEIGHT = bool(args.emit_height)
    if config.AUX_HEIGHT:
        config.USE_HILLSHADE = False        # CHM is the regression target, NOT an input band
        config.IN_CHANNELS = 3              # pure RGB-only input
        print("  [--aux-height] RGB-only input + height-prediction head "
              f"(height-lambda={config.HEIGHT_LAMBDA}); CHM used as target only.")
    config.INFER_BATCH = max(1, int(args.infer_batch))
    config.RUN_TAG = ("".join(c if (c.isalnum() or c in "._-") else "_"
                       for c in args.run_tag).strip("_") if args.run_tag else "")
    if config.RUN_TAG:
        print(f"  [--run-tag] outputs suffixed _{config.RUN_TAG} (SAVE, no overwrite)")
    if args.force_citywide:
        print("  [--force-citywide] citywide 2020-mask recipe forced on ALL tiers "
              "(uniform recipe; only the sensor varies).")
    # Edit F: --loss-mode overrides the coarse-tier loss (focal A/B); fine/medium
    # stay bce_dice. Mutating the dict contents (no rebind) → no `global` needed.
    if args.loss_mode:
        TIER_LOSS_MODE["coarse"] = args.loss_mode

    print("=" * 65)
    print("  PHASE 4 — Per-Year Semantic Segmentation Fine-Tuning (17 years)")
    print("  Edmonds Temporal Active Learning Pipeline")
    print("=" * 65)

    entries = _resolve_years(args)
    labels = [e["label"] for e in entries]
    print(f"  Years ({len(labels)}): {', '.join(labels)}")
    if args.dry_run:
        print("  Dry run: True")

    # Which per-year steps to run.
    if args.step == "consistency":
        per_year = []
    elif args.step:
        per_year = [args.step]
    else:
        per_year = list(PER_YEAR_STEPS)
        if args.skip_training:
            per_year.remove("train")
        if args.skip_inference:
            per_year = [s for s in per_year if s not in ("inference", "postproc")]
    if per_year:
        print(f"  Steps: {', '.join(per_year)}")

    for d in (OUT_DIR, SITE_DIR, TILE_DIR, MODELS_DIR, MASKS_DIR, EVAL_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # Site footprints are shared across years — discover once.
    sites = None
    if any(s in per_year for s in ("labels", "tile")):
        sites = discover_site_footprints(site_buffer=args.site_buffer)

    p3 = resolve_p3_ckpt(args.ckpt)
    if "train" in per_year:
        print(f"  Fine-tune start: {p3 if p3 else 'NOT FOUND — train will abort'}")

    # Process each year end-to-end (so a crash leaves complete years behind).
    for e in entries:
        lab = e["label"]
        print(f"\n{'#'*65}\n#  YEAR {lab}  ({e['gsd_cm']:.1f} cm, "
              f"{tier_of(e['gsd_cm'])}, {e['source']}, {e['coverage']})\n{'#'*65}")
        # Coarse tier defaults to city-wide stratified tiling (Fix 3); opt out
        # with --coarse-site-tiling, and the 6-site anchor-label path takes
        # precedence when --anchor-labels is set. --force-citywide extends the
        # citywide recipe to ALL tiers (uniform cross-resolution recipe).
        citywide = ((tier_of(e["gsd_cm"]) == "coarse" or args.force_citywide)
                    and not args.coarse_site_tiling
                    and not args.anchor_labels)
        if "labels" in per_year:
            with StepLogger(SCRIPT_NAME, f"labels_{lab}", LOGS_DIR) as log:
                r = step_labels(lab, sites, dry_run=args.dry_run,
                                anchor_labels=args.anchor_labels,
                                prob_hi=args.prob_hi, prob_lo=args.prob_lo,
                                citywide=citywide)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "tile" in per_year:
            with StepLogger(SCRIPT_NAME, f"tile_{lab}", LOGS_DIR) as log:
                r = step_tile(lab, sites, dry_run=args.dry_run,
                              max_tiles=args.max_tiles, stride_override=args.stride,
                              citywide=citywide, force_retile=args.force_retile)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "train" in per_year:
            with StepLogger(SCRIPT_NAME, f"train_{lab}", LOGS_DIR) as log:
                r = step_train(lab, batch_size=args.batch_size,
                               p3_ckpt=args.ckpt, dry_run=args.dry_run,
                               compile_model=not args.no_compile)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "evaluate" in per_year:
            with StepLogger(SCRIPT_NAME, f"evaluate_{lab}", LOGS_DIR) as log:
                r = step_evaluate(lab, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "inference" in per_year:
            with StepLogger(SCRIPT_NAME, f"inference_{lab}", LOGS_DIR) as log:
                r = step_inference(lab, batch_size=config.INFER_BATCH, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "postproc" in per_year:
            with StepLogger(SCRIPT_NAME, f"postproc_{lab}", LOGS_DIR) as log:
                r = step_postproc(lab, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)

    # Cross-year consistency runs once (default pipeline, or --step consistency).
    if args.step in (None, "consistency"):
        with StepLogger(SCRIPT_NAME, "consistency", LOGS_DIR) as log:
            r = step_consistency(dry_run=args.dry_run)
            _f = {"dry_run": args.dry_run, "errors": 0}
            if isinstance(r, dict): _f.update(r)
            log.finish(**_f)

    print_summary(entries)
    timer_summary()
