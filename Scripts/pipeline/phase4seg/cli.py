import argparse
import sys
import pandas as pd

from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (
    discover_site_footprints, entry_for, remaining_entries, _tag_sfx,
    timer_summary, resolve_native_path,
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
        entries = [e for e in entries if tier_for(e) == args.tier]
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
        print(f"  {lab:<7}{e['gsd_cm']:>6.1f}{tier_for(e):>8}"
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

    # Colab injects `-f /root/.local/.../kernel-XXX.json` into argv; strip THE PAIR,
    # not every .json-suffixed value — the old any-.json filter silently ate the
    # --infer-aoi value (aoi/sectors_v1.json), found 2026-08-25 on the first VM dry-run.
    filtered, _skip = [], False
    for a in sys.argv[1:]:
        if _skip:
            _skip = False
            continue
        if a == "-f":
            _skip = True
            continue
        if a.endswith(".json") and (not filtered or not filtered[-1].startswith("--")):
            continue          # a bare kernel-json with no owning flag (belt and braces)
        filtered.append(a)

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
    p.add_argument("--skip-postproc", action="store_true",
                   help="Skip postproc (polygonize → crown GPKG). The cross-sensor "
                        "autopsy scores the prob raster, not the GPKG, so this avoids "
                        "the fine-year polygonize on experimental runs.")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--seed", type=int, default=None,
                   help="Override RANDOM_SEED (42) for TRAINING stochasticity only — "
                        "init, augmentation order, loader shuffling. Tiling is "
                        "untouched by design: tiling.py binds seed=RANDOM_SEED as "
                        "default args at import, so tile selection and the "
                        "train/val/test split stay fixed across --seed values. That "
                        "isolation is the point: seed-varied repeats under one tag "
                        "family measure TRUE retrain sigma (the 2026-08-27 noise "
                        "campaign was same-seed and is a LOWER bound). Recorded in "
                        "the manifest `seed` field. Default None = 42, byte-for-byte "
                        "the historical behaviour.")
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
    p.add_argument("--hs-source", choices=sorted(HS_STATS) + ["auto"], default="chm",
                   help="Source of band 4 (tiling-time choice, default "
                        "chm). 'nir' (M06) = THE YEAR'S OWN NIR band, read from "
                        "the same ortho window as the RGB (no LIDAR, no warp); "
                        "only the ten bands=4 acquisitions can supply it and "
                        "every other year fails loud. The LIDAR sources: "
                        "'chm' = REAL 3DEP canopy height in metres (U8-scaled, "
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
    p.add_argument("--epochs-phase-a", "--max-epochs-a", dest="epochs_phase_a",
                   type=int, default=config.EPOCHS_PHASE_A,
                   help=f"Phase-A epoch budget (default {config.EPOCHS_PHASE_A}). Lower "
                        f"(e.g. 8) for fast diagnostic runs — the cliff appears by "
                        f"E6, so a short Phase A shows stable-vs-collapse quickly. "
                        f"--max-epochs-a is an alias.")
    p.add_argument("--epochs-phase-b", "--max-epochs-b", dest="epochs_phase_b",
                   type=int, default=config.EPOCHS_PHASE_B,
                   help=f"Phase-B epoch budget (default {config.EPOCHS_PHASE_B}). Set 0 "
                        f"to skip Phase B entirely (diagnostic runs don't need it "
                        f"— it never recovers from a Phase-A collapse). RAISE it "
                        f"(--max-epochs-b 60) to test whether the cap, not "
                        f"convergence, is deciding a result: four of five 2009 arms "
                        f"stopped at EPOCH_CAP=30, one with its best epoch LAST, "
                        f"which biases every A/B where one side learns slower. This "
                        f"flag is per-run — the constant stays 30 because raising it "
                        f"permanently is a recipe change. --max-epochs-b is an alias.")
    p.add_argument("--select-smooth", type=int, default=config.SELECT_SMOOTH_K,
                   help=f"Choose the DEPLOYED checkpoint by a K-epoch CENTRED moving "
                        f"average of the early-stopping metric instead of its raw "
                        f"per-epoch peak (default {config.SELECT_SMOOTH_K} = raw peak, "
                        f"today's behaviour exactly). The metric is measured on ~120 "
                        f"val tiles, so a max over 20-50 epochs both inflates the "
                        f"reported number and adds run-to-run variance — the chosen "
                        f"threshold wobbled .440-.499 across five identical 2009 runs. "
                        f"SELECTION ONLY: training, optimiser, LR schedule and the "
                        f"early-stop patience counter all still run off the raw value, "
                        f"and Phase B still resumes from the raw-best Phase-A "
                        f"checkpoint, so K is one variable. Window is edge-truncated "
                        f"(never zero-padded) and smoothed WITHIN a phase; the saved "
                        f"weights are one real epoch's, never an average. Even K is "
                        f"rounded up to odd. Train-only — no re-tile (the epoch "
                        f"budgets and K key no part of the tile signature).")
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
    p.add_argument("--sample-manifest", type=str, default=None,
                   help="Path to a C-CAP-stratified tile manifest (.gpkg/.csv from "
                        "phase4_ccap_sample.py). Citywide-coarse tiling then uses ONLY "
                        "those fixed geographic locations (reprojected per year), so a "
                        "cross-sensor run trains/infers on the same representative, "
                        "forest-oversampled sample instead of the full city. Retiles.")
    p.add_argument("--infer-aoi", type=str, default=None,
                   help="Sector AOI file (pipeline/aoi/sectors_v1.json or a .gpkg). "
                        "step_inference infers ONLY tiles whose write-crop intersects a "
                        "sector rectangle; the rest of the full-grid prob raster stays "
                        "PROB_NODATA (the sample-manifest output shape, which every "
                        "downstream scorer already handles). Relative paths resolve "
                        "against the repo pipeline/ dir. Other steps are unaffected; "
                        "the tile cache never re-tiles for an AOI change.")
    p.add_argument("--stride", type=int, default=None,
                   help="Override the per-tier TILING stride ONLY (smaller = more "
                        "overlapping tiles → more tiles). It keys the tile "
                        "signature, so changing it triggers a ~20-min re-tile. "
                        "There is NO inference-stride flag — INFER_STRIDE is a "
                        "config constant (E08).")
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
    p.add_argument("--allow-overwrite", action="store_true",
                   help="P7 gate: an UNTAGGED run that would overwrite existing "
                        "model/raster artifacts is refused unless this is passed "
                        "(prefer --run-tag).")
    args = p.parse_args(filtered)

    if args.seed is not None:
        # Propagate to every module-level RANDOM_SEED read at RUN time:
        # core._seed_everything (train start), core._worker_init and
        # core._loader_generator (loader construction), and this module's
        # manifest line. tiling.py's defaults were bound at import and stay
        # at 42 ON PURPOSE (see --seed help: fixed split, varied training).
        global RANDOM_SEED
        RANDOM_SEED = int(args.seed)
        config.RANDOM_SEED = int(args.seed)
        from phase4seg import core as _core_mod
        _core_mod.RANDOM_SEED = int(args.seed)
        print(f"  [--seed] RANDOM_SEED overridden to {args.seed} for training "
              f"(tile selection/split unchanged, still 42)")

    if args.check:
        print("[preflight] arguments parsed OK — command is valid.")
        return

    from pipeline_log import StepLogger

    def _stat_or_none(path, field):
        """os.stat field for a path that may be None/absent/on a flaky FUSE
        mount — provenance must not be able to kill a run."""
        try:
            return getattr(Path(path).stat(), field) if path else None
        except OSError:
            return None

    def _write_run_manifest(args, entries):
        """P6.1: one manifest per engine invocation → phase4/runs/{run_id}/manifest.json.

        Records what no log used to record: the commit that ran (+ dirty flag),
        the installed packages, the seed, the full argv, and which imagery file
        each year actually resolved to. Never raises — provenance must not be
        able to kill a run.
        """
        import datetime as _dtm
        import json as _json
        import subprocess as _sp
        try:
            import phase4seg as _pkg
            ts = _dtm.datetime.now(_dtm.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            tag = config.RUN_TAG or "untagged"
            lbls = "-".join(e["label"] for e in entries) or "none"
            step0 = args.step or "full"
            run_id = f"{ts}_{lbls}_{tag}_{step0}"
            # Publish it so artifacts can carry their own identity (D2). Until now
            # the run_id existed only inside the manifest, so a checkpoint could not
            # say which run produced it and nothing downstream could check.
            config.RUN_ID = run_id
            config.RUN_YEARS = lbls
            # repo root: walk up from the RUNNING entrypoint (the shim copies
            # phase4seg/ off to /content/_phase4seg_pkg, so __file__ here may
            # not live in the repo — the shim does).
            main_file = getattr(sys.modules.get("__main__"), "__file__", None)
            anchor = Path(main_file).resolve() if main_file else Path(__file__).resolve()
            repo_root = next((p for p in anchor.parents if (p / ".git").exists()), None)
            sha, dirty, branch = "unknown", None, None
            if repo_root is not None:
                try:
                    sha = _sp.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, timeout=20
                                  ).stdout.strip() or "unknown"
                    dirty = bool(_sp.run(["git", "-C", str(repo_root), "status",
                                          "--porcelain"], capture_output=True,
                                         text=True, timeout=20).stdout.strip())
                    branch = _sp.run(["git", "-C", str(repo_root), "rev-parse",
                                      "--abbrev-ref", "HEAD"], capture_output=True,
                                     text=True, timeout=20).stdout.strip() or None
                except Exception:
                    pass
            # P11.5: which GPU ran this (tier attribution for cost + timing); torch-free
            # so the manifest never forces an import. None on CPU/local.
            gpu, gpu_mem_gb = None, None
            try:
                r = _sp.run(["nvidia-smi", "--query-gpu=name,memory.total",
                             "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=20)
                q = r.stdout.strip()
                if r.returncode == 0 and q:
                    name, mem = [s.strip() for s in q.splitlines()[0].split(",")[:2]]
                    gpu = name or None                 # keep the name even if the
                    try:                               # memory field is "[N/A]"
                        gpu_mem_gb = round(float(mem) / 1024, 1)
                    except ValueError:
                        pass
            except Exception:
                pass
            try:
                freeze = _sp.run([sys.executable, "-m", "pip", "freeze"],
                                 capture_output=True, text=True,
                                 timeout=120).stdout.splitlines()
            except Exception:
                freeze = []
            man = {
                "run_id": run_id, "ts_utc": ts,
                "engine_version": getattr(_pkg, "__version__", "unset"),
                "git_sha": sha, "git_dirty": dirty, "git_branch": branch,
                "gpu": gpu, "gpu_mem_gb": gpu_mem_gb,
                "repo_root": str(repo_root) if repo_root else None,
                "argv": sys.argv[1:],
                "run_tag": config.RUN_TAG, "step": step0,
                "seed": int(RANDOM_SEED),
                "years": {e["label"]: {"native": str(resolve_native_path(e)),
                                       "gsd_cm": e.get("gsd_cm")}
                          for e in entries},
                # Configured label inputs (E06). Recorded on EVERY step (postproc
                # consumes none — the block describes configuration, not use).
                # path+size for the base mask, never sha256 on FUSE (the P6.6
                # precedent); the overlay keeps mtime because it is keyed that
                # way in the tile signature.
                "labels": {
                    "source_mask": str(MASK_2020),
                    "source_mask_size": _stat_or_none(MASK_2020, "st_size"),
                    "add_canopy_mask": (str(config.ADD_CANOPY_MASK)
                                        if config.ADD_CANOPY_MASK else None),
                    "add_canopy_mask_size": _stat_or_none(config.ADD_CANOPY_MASK,
                                                          "st_size"),
                    "add_canopy_mask_mtime": _stat_or_none(config.ADD_CANOPY_MASK,
                                                           "st_mtime"),
                    "force_citywide": bool(args.force_citywide),
                },
                "python": sys.version.split()[0],
                "pip_freeze": freeze,
            }
            out = OUT_DIR / "runs" / run_id
            out.mkdir(parents=True, exist_ok=True)
            (out / "manifest.json").write_text(_json.dumps(man, indent=2),
                                               encoding="utf-8")
            print(f"  run_id: {run_id}  (git {sha[:8]}{' DIRTY' if dirty else ''}"
                  f" on {branch or '?'}; GPU {gpu or 'none'}"
                  f"{f' {gpu_mem_gb} GB' if gpu_mem_gb else ''})  → runs/{run_id}/manifest.json")
            return run_id
        except Exception as e:                                  # noqa: BLE001
            print(f"  WARNING: run manifest not written ({e})")
            return "unrecorded"
    LOGS_DIR = BASE / "phase4" / "logs"
    SCRIPT_NAME = "phase4_semantic_finetune"

    config.USE_VI = bool(args.vi)
    config.USE_HILLSHADE = bool(args.hillshade)
    # --hs-source auto: pick the TEMPORALLY-NEAREST height raster for this year
    # (config.CHM_BY_YEAR). Opt-in only — never the default — because changing the
    # height input silently would break comparability with every existing baseline.
    # Resolved here, before tiling, so the choice lands in the tile signature, the
    # HS_SOURCE tile tag, the checkpoint field and argv. A year with no mapping
    # falls back to CHM_BY_YEAR_DEFAULT and SAYS SO rather than quietly using it.
    if args.hs_source == "auto":
        # `years` is not resolved until later in main(); read the flag directly so
        # this cannot NameError the first time someone uses it.
        _years = [y.strip() for y in (args.year or "").split(",") if y.strip()]
        _picked = {y: config.chm_for_year(y) for y in _years}
        if len(set(_picked.values())) > 1:
            raise SystemExit(
                "--hs-source auto resolves to DIFFERENT rasters across the requested "
                f"years {_picked} — band 4 is a tiling-time choice, so run one year "
                "per invocation (or pass an explicit --hs-source).")
        _src = next(iter(_picked.values())) if _picked else config.CHM_BY_YEAR_DEFAULT
        for _y in _years:
            _mapped = _y in config.CHM_BY_YEAR
            print(f"  [--hs-source auto] {_y} -> {_src}"
                  + ("" if _mapped else f"  (no mapping; CHM_BY_YEAR_DEFAULT)"))
        args.hs_source = _src
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
    # Checkpoint-SELECTION smoothing (2026-08-29). 1 = raw per-epoch peak = the
    # historical path (core never even builds the selector). A centred window has
    # no unambiguous centre at even K, so round up and say so.
    _k = max(1, int(args.select_smooth))
    if _k % 2 == 0:
        print(f"  [--select-smooth] {_k} is even — a centred window has no centre; "
              f"using {_k + 1}.")
        _k += 1
    config.SELECT_SMOOTH_K = _k
    if _k > 1:
        print(f"  [--select-smooth {_k}] deployed checkpoint = peak of the {_k}-epoch "
              f"centred moving average of the early-stop metric (training, patience "
              f"and the Phase-B resume point are UNCHANGED).")
    config.FREEZE_ENCODER_BN = bool(args.freeze_encoder_bn)
    # Module-level fallback; the per-step functions (train/evaluate/inference)
    # override IN_CHANNELS from the actual tile/ckpt band count.
    config.IN_CHANNELS = 3 + (len(VI_NAMES) if config.USE_VI else 0) + (1 if config.USE_HILLSHADE else 0)
    config.THRESH_MODE = args.thresh_mode
    config.INFER_THRESH_OVERRIDE = args.infer_thresh
    config.ADD_CANOPY_MASK = args.add_canopy_mask
    config.SAMPLE_MANIFEST = args.sample_manifest
    config.INFER_AOI = args.infer_aoi
    if config.INFER_AOI and config.SAMPLE_MANIFEST:
        print("  WARNING: both --sample-manifest and --infer-aoi given — sample-manifest "
              "wins for citywide runs; the AOI is ignored wherever sample mode engages.")
    if config.SAMPLE_MANIFEST and not args.force_citywide:
        print("  WARNING: --sample-manifest applies only to citywide/coarse tiers. "
              "Fine/medium years without --force-citywide tile + infer FULL (manifest "
              "ignored) — pass --force-citywide for a uniform sampled cross-sensor run.")
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

    # ── M06 --hs-source nir: refuse every silent-substitution path up front ────
    if config.nir_mode():
        if args.aux_height:
            sys.exit("--hs-source nir with --aux-height: --aux-height forces "
                     "RGB-only input (CHM becomes the target), so the NIR band "
                     "would be silently dropped. Pick one.")
        if not config.USE_HILLSHADE:
            sys.exit("--hs-source nir with --no-hillshade: no 4th channel would "
                     "be baked at all. Drop --no-hillshade.")
        _no_nir = [e["label"] for e in entries if int(e.get("bands", 3)) < 4]
        if _no_nir:
            sys.exit(f"--hs-source nir: no NIR band in {', '.join(_no_nir)} "
                     f"(YEAR_CATALOG bands<4). The ten NIR acquisitions are "
                     f"2015n 2016 2017n 2017s 2018s 2019n 2019s 2021n 2021s "
                     f"2023n. Refusing to substitute RGB or LIDAR.")
        _lifted = [lb for lb in labels if lb in NIR_LIFTED_FLOOR_YEARS]
        if _lifted:
            print(f"  ⚠ [--hs-source nir] {', '.join(_lifted)} has a LIFTED NIR "
                  f"BLACK POINT (IMAGERY_FACTS §12): absolute NIR level is not "
                  f"comparable to the healthy eight HS_STATS['nir'] was measured "
                  f"on. Excluded from the M06 A/B arm by design.")
        print(f"  [--hs-source nir] band 4 = each year's own NIR band "
              f"(hs-dropout={config.HS_DROPOUT} keeps the pure-RGB pathway).")
    run_id = _write_run_manifest(args, entries)
    config.RUN_ID = run_id

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

    # P7 gate: an untagged run writes the LEGACY artifact names — refuse to
    # clobber silently. (Every queue job passes --run-tag, so this only fires on
    # hand-typed runs, which is exactly where the accidents happen.)
    if not config.RUN_TAG and not args.allow_overwrite and not args.dry_run:
        _danger = [s for s in per_year if s in ("train", "inference", "postproc")]
        _clobber = []
        if _danger:
            for _e in entries:
                _lab = _e["label"]
                for _p in (MODELS_DIR / f"sem_best_{_lab}.pt",
                           MASKS_DIR / f"edmonds_canopy_prob_{_lab}.tif",
                           MASKS_DIR / f"edmonds_canopy_mask_{_lab}.tif"):
                    if _p.exists():
                        _clobber.append(_p.name)
        if _clobber:
            sys.exit("REFUSING untagged overwrite of: " + ", ".join(_clobber)
                     + "\n  Pass --run-tag TAG (preferred) or --allow-overwrite.")

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
              f"{tier_for(e)}, {e['source']}, {e['coverage']})\n{'#'*65}")
        # Coarse tier defaults to city-wide stratified tiling (Fix 3); opt out
        # with --coarse-site-tiling, and the 6-site anchor-label path takes
        # precedence when --anchor-labels is set. --force-citywide extends the
        # citywide recipe to ALL tiers (uniform cross-resolution recipe).
        citywide = ((tier_for(e) == "coarse" or args.force_citywide)
                    and not args.coarse_site_tiling
                    and not args.anchor_labels)
        if "labels" in per_year:
            with StepLogger(SCRIPT_NAME, f"labels_{lab}", LOGS_DIR) as log:
                r = step_labels(lab, sites, dry_run=args.dry_run,
                                anchor_labels=args.anchor_labels,
                                prob_hi=args.prob_hi, prob_lo=args.prob_lo,
                                citywide=citywide)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"], "run_id": run_id,
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "tile" in per_year:
            with StepLogger(SCRIPT_NAME, f"tile_{lab}", LOGS_DIR) as log:
                r = step_tile(lab, sites, dry_run=args.dry_run,
                              max_tiles=args.max_tiles, stride_override=args.stride,
                              citywide=citywide, force_retile=args.force_retile)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"], "run_id": run_id,
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "train" in per_year:
            with StepLogger(SCRIPT_NAME, f"train_{lab}", LOGS_DIR) as log:
                r = step_train(lab, batch_size=args.batch_size,
                               p3_ckpt=args.ckpt, dry_run=args.dry_run,
                               compile_model=not args.no_compile)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"], "run_id": run_id,
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "evaluate" in per_year:
            with StepLogger(SCRIPT_NAME, f"evaluate_{lab}", LOGS_DIR) as log:
                r = step_evaluate(lab, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"], "run_id": run_id,
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "inference" in per_year:
            with StepLogger(SCRIPT_NAME, f"inference_{lab}", LOGS_DIR) as log:
                r = step_inference(lab, batch_size=config.INFER_BATCH,
                                   dry_run=args.dry_run, citywide=citywide)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"], "run_id": run_id,
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "postproc" in per_year and not args.skip_postproc:
            with StepLogger(SCRIPT_NAME, f"postproc_{lab}", LOGS_DIR) as log:
                r = step_postproc(lab, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"], "run_id": run_id,
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
