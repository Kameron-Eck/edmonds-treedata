"""
Log Integration Reference
=========================
This file shows the exact patch for phase4_label_review.py main()
and the canonical pattern Claude Code follows for every other script.

Do NOT import this file — it is a reference only.
"""

# ══════════════════════════════════════════════════════════════
# PATTERN: how to integrate StepLogger into a --step script
# ══════════════════════════════════════════════════════════════

# 1. Add this import near the top of the script (after std imports):
#
#    from pipeline_log import StepLogger
#    LOGS_DIR = BASE / "Scripts" / "logs"
#    SCRIPT_NAME = "phase4_label_review"   # stem of this file

# 2. Replace main() with the version below.
#    Key changes:
#      - Each step branch is wrapped in StepLogger as a context manager
#      - finish() receives step-specific summary fields
#      - serve step is NOT logged on start (it runs forever); log on shutdown
#
# serve is special: it blocks indefinitely. The logger wraps only the
# setup phase, then logs once the server is interrupted.

# ── PATCHED main() for phase4_label_review.py ────────────────

PATCHED_MAIN = '''
def main():
    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "Scripts" / "logs"
    SCRIPT_NAME = "phase4_label_review"

    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    p = argparse.ArgumentParser(description="Phase 4 temporal-anchor crown reviewer")
    p.add_argument("--step", choices=["prep", "serve", "compile"], required=True)
    p.add_argument("--year", type=int, default=YEAR)
    p.add_argument("--sites", default=None)
    p.add_argument("--to-polygons", action="store_true")
    args = p.parse_args(filtered)

    sites_filter = set(args.sites.split(",")) if args.sites else None

    if args.step == "prep":
        with StepLogger(SCRIPT_NAME, "prep", LOGS_DIR) as log:
            manifest = step_prep(args.year, sites_filter)
            sites_done = sorted({m["site"] for m in manifest})
            log.finish(
                year=args.year,
                crowns=len(manifest),
                sites=sites_done,
                manifest_mb=round(
                    (local_root(args.year) / "manifest.json").stat().st_size / 1e6, 1
                ),
                errors=0,
            )

    elif args.step == "serve":
        # serve blocks; log setup only, then log shutdown
        logger = StepLogger(SCRIPT_NAME, "serve", LOGS_DIR, capture_stdout=False)
        logger.start()
        server = step_serve(args.year)
        rows_start = _csv_row_count(review_root(args.year) / CSV_NAME)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\\n  server stopped.")
        rows_end = _csv_row_count(review_root(args.year) / CSV_NAME)
        logger.finish(
            year=args.year,
            labels_this_session=rows_end - rows_start,
            total_labels=rows_end,
        )

    elif args.step == "compile":
        with StepLogger(SCRIPT_NAME, "compile", LOGS_DIR) as log:
            result = step_compile(args.year, sites_filter,
                                  to_polygons=args.to_polygons)
            log.finish(
                year=args.year,
                to_polygons=args.to_polygons,
                errors=0,
                # step_compile should return a summary dict; adjust as needed
            )
'''


# ══════════════════════════════════════════════════════════════
# PATTERN for scripts with multiple per-year steps
# (phase4_semantic_finetune, phase1_preprocess, etc.)
# ══════════════════════════════════════════════════════════════

PATTERN_PER_YEAR = '''
# For scripts that loop over years and steps, log at the year+step level:

for e in entries:
    lab = e["label"]
    if "train" in per_year:
        with StepLogger("phase4_semantic_finetune", f"train_{lab}", LOGS_DIR) as log:
            metrics = step_train(lab, batch_size=args.batch_size,
                                 p3_ckpt=args.ckpt, dry_run=args.dry_run)
            log.finish(
                year=lab,
                gsd_cm=e["gsd_cm"],
                best_iou=metrics.get("best_iou"),
                best_epoch=metrics.get("best_epoch"),
                errors=0,
            )
    if "evaluate" in per_year:
        with StepLogger("phase4_semantic_finetune", f"evaluate_{lab}", LOGS_DIR) as log:
            result = step_evaluate(lab, dry_run=args.dry_run)
            log.finish(year=lab, **result)
'''


# ══════════════════════════════════════════════════════════════
# CLAUDE CODE WORKFLOW
# ══════════════════════════════════════════════════════════════
#
# 1. User triggers a Colab run:
#       %run .../Scripts/phase4_label_review.py --step prep
#
# 2. Step completes. Script writes:
#       .../Scripts/logs/phase4_label_review_prep_2026-06-22T14-33.log
#
# 3. Claude Code reads the log:
#       drive_mcp.read("treedata/Scripts/logs/phase4_label_review_prep_*.log")
#
# 4. Claude Code assesses. If a fix is needed:
#       python version_script.py --script .../phase4_label_review.py --tag "fix crop padding"
#       # edit the script
#
# 5. User re-runs in Colab.
#
# No pasting of terminal output. No manual diff application.
# ══════════════════════════════════════════════════════════════
