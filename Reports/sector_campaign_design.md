# Sector campaign — design condensate (2026-08-24)

The executable spec IS the committed artifacts; this note records only what code cannot say:

- Design produced by a Plan agent this session (full text in the session transcript). The
  authoritative pieces now live in: `pipeline/sector_campaign_checklist.yaml` (the checklist),
  `pipeline/make_sectors.py` (sector calculator), `pipeline/aoi/sectors_v1.json` (the AOIs),
  `pipeline/queue_sectors_base2020.yaml` + `queue_sectors_fullext.yaml` (queues),
  `qc/sector_campaign_loop.py` (autonomous executor), `qc/phase4_sector_series.py` (series +
  design-based totals), `qc/phase4_crown_cover_matrix.py` (crown matrix), and the `--infer-aoi`
  diff in `phase4seg/{config,cli,core}.py`.
- Key mechanics verified against source before design: origins grid core.py:1419-1425;
  sample-manifest nodata-prefill core.py:1479-1487 (the output shape --infer-aoi reuses);
  queue `extra` pass-through phase4_train_queue.py:325-326; seed-CSV resume :229-262
  (`_completed_steps` merges every train_queue_status*.csv → seeded OK rows skip steps);
  `_VERIFY_HARD_FAIL` :465-466 (queue_verify tests NOT-hard-fail, never ==OK);
  postproc threshold fallback to 0.5 postproc.py:42-67 (forbidden path — the loop refuses
  postproc without a live qc_indep row).
- Estimator: strata = the 5 sector bands, weights by true land area (3857 × cos²47.81°);
  successive-difference variance (Wolter) with t(0.975, df=4)=2.776; err-adjusted fraction
  p·precision/recall from the year's live row.
- Measured baseline: sectors touch ~9-10% of raster pixels (unit-tested on the 2285 1-ft and
  3857 anchor grids) → ~10× inference-tile cut per iteration. A100 estimate for the baseline
  campaign: ~15 min of sector inference + ~2.5-3 h fullext training ≈ 5-7 A100-hours.
- base2020 outputs are a COPY of phase3/sem_best_2020.pt (RGB-only, NOT fine-tuned) and are
  labelled base2020/sectors_v1 everywhere they appear.
