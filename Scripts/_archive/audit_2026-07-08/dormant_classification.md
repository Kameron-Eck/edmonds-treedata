# Dormant script triage — G:\My Drive\treedata\Scripts

Enumerated all `*.py` directly in `Scripts\` (not recursive; `.versions\` and `_archive\` excluded).
Safety check: grepped the whole folder for `^\s*(import|from)\s+<modulename>` and for `%run` /
`<modulename>.py` mentions in every file, to catch any active script that depends on a candidate.

**Result of safety check:** No file in the ACTIVE list (shared infra, phase0–phase4 suite,
make_positive_site.py, make_grass_negatives.py, fetch_build_chm.py, version_script.py) imports,
`%run`s, or otherwise references any candidate script. All cross-references found were either
(a) a script referencing itself in its own usage docstring, or (b) one candidate referencing
another candidate (e.g. `patch_scripts.py` lists old downloader/registration scripts it once
patched; `run_registration.py` imports `coregister_imagery`; `edmonds_batch_orchestrator.py`
shells out to `edmonds_single_batch.py`). One informational (non-import) comment was found:
`phase4_semantic_finetune.py:229` mentions `fetch_be_build_struct` in a prose comment pointing
at historical handoffs — not a code dependency.

| filename | verdict | reason | imported-by-active? |
|---|---|---|---|
| Snoco_tiles.py | ARCHIVE | Snohomish County aerial imagery downloader; acquisition complete | no |
| USGS_pipe.py | ARCHIVE | unified discover/download pipeline (pre-Phase-0 acquisition); superseded by unified_downloader.py | no |
| batch.py | ARCHIVE | old memory-safe chunked batch downloader for 2020/2022; acquisition complete | no |
| build_clip_viewer.py | ARCHIVE | interactive HTML viewer for coregistration clip alignment QA; registration complete | no |
| burn_annotations.py | ARCHIVE | one-off color-burn composite generator for hand-annotated photo extents | no |
| cleanup_imagery.py | ARCHIVE | one-time Full_Image folder rename/cleanup utility; done | no |
| cleanup_registration.py | ARCHIVE | one-time scratch-clear utility for re-running coregistration; registration complete | no |
| clip_study_area.py | ARCHIVE | extracts test clips for coregistration validation; registration complete | no |
| colab_georeference_test.py | ARCHIVE | Colab test-cell for one NHAP scene georeference; one-off | no |
| collect_scene_metadata.py | ARCHIVE | M2M API metadata collector for imagery discovery; acquisition complete | no |
| color_burn_composite.py | ARCHIVE | multi-year overlap color-burn diagnostic composite; one-off viewer | no |
| coregister_imagery.py | ARCHIVE | core co-registration engine; Phase 1 registration complete | no |
| coverage_test.py | ARCHIVE | quick 25-point bbox coverage sampler for imagery discovery | no |
| diagnostic.py | ARCHIVE | comprehensive Edmonds imagery server diagnostic; acquisition-era debugging | no |
| discover_edmonds_imagery.py | ARCHIVE | M2M API imagery discovery/inventory builder; acquisition complete | no |
| download_high_coverage.py | ARCHIVE | downloads scenes ≥95% coverage from optimal-scenes list; acquisition complete | no |
| download_tiles.py | ARCHIVE | maps.edmondswa.gov tile downloader; acquisition complete | no |
| edmonds_2020_aerial_downloader.py | ARCHIVE | City of Edmonds 2020 aerial downloader; acquisition complete | no |
| edmonds_2020_diagnostic.py | ARCHIVE | server diagnostic for exportImage endpoint support; one-off | no |
| edmonds_batch_orchestrator.py | ARCHIVE | subprocess-isolated batch download orchestrator; acquisition complete | no |
| edmonds_single_batch.py | ARCHIVE | single-batch downloader invoked by edmonds_batch_orchestrator.py; acquisition complete | no |
| fetch_be_build_struct.py | ARCHIVE | superseded by fetch_build_chm.py (older terrain-structure-raster experiment; only mentioned in a historical comment) | no |
| flicker_viewer.py | ARCHIVE | HTML flicker-compare QA viewer for registration; registration complete | no |
| image_qa_server.py | ARCHIVE | browser-based QA viewer for downloaded imagery; acquisition-era tool | no |
| image_viewer_qa.py | ARCHIVE | image viewer/rotator/fiducial-marker tool; acquisition-era tool | no |
| imagery_stats.py | ARCHIVE | per-image statistics extractor for a literature-review write-up; one-off | no |
| inspect_anchor_labels.py | ARCHIVE | one-off QA of 2020 anchor labels for a single site (self-described "one-off") | no |
| inspect_api_responses.py | ARCHIVE | raw M2M API response structure inspector; one-off | no |
| inspect_kc_imagery.py | ARCHIVE | King County tile-service max-zoom prober; acquisition-era diagnostic | no |
| investigate_high_res_ortho.py | ARCHIVE | one-off diagnostic for HIGH_RES_ORTHO load failures in the QA tool | no |
| king_county.py | ARCHIVE | King County aerial imagery downloader; acquisition complete | no |
| log_integration_patch.py | ARCHIVE | reference/template patch showing how logging was wired into phase4_label_review.py; migration already applied | no |
| master_imagery_downloader.py | ARCHIVE | "all sources" master downloader; superseded by unified_downloader.py | no |
| merge_rgb_ir.py | ARCHIVE | merges RGB+IR TIFs into 4-band GeoTIFF; one-time naming/merge step, done | no |
| naip_edmonds_downloader.py | ARCHIVE | NAIP 4-band downloader; acquisition complete | no |
| nhap_georeference.py | ARCHIVE | applies GCPs to un-georeferenced NHAP TIFFs; acquisition complete | no |
| nhap_scene_finder.py | ARCHIVE | NHAP 1980 scene finder via M2M API; acquisition complete | no |
| nhap_scene_finder_TEST.py | ARCHIVE | synthetic-data test harness for nhap_scene_finder.py; dev/test scaffold | no |
| patch_scripts.py | ARCHIVE | one-time migration patcher (pushed pipeline_config.py imports into old scripts); job done | no |
| phase0_coreg_gifs.py | ARCHIVE | side-by-side coregistration QC GIF generator; registration complete | no |
| probe_imagery_sharpness.py | ARCHIVE | Laplacian-variance sharpness prober for KC imagery; acquisition-era diagnostic | no |
| proof_of_concept_colab.py | ARCHIVE | paste-into-Colab-cell POC visualization snippet; early prototype | no |
| run_registration.py | ARCHIVE | registration orchestrator (calls coregister_imagery.py); registration complete | no |
| sample_imagery.py | ARCHIVE | multi-year patch sampler/comparison PNG tool; registration-era QA | no |
| select_optimal_scenes.py | ARCHIVE | selects 1-3 best M2M scenes per year by coverage; acquisition complete | no |
| setup_folders.py | ARCHIVE | one-time Full_Image directory-tree creator ("run once") | no |
| setup_naming_convention.py | ARCHIVE | one-time file renaming + RGB+IR merge; done | no |
| temporal_overlay.py | ARCHIVE | overlays phase0 crown polygons on multi-year imagery for visual QA; superseded by later phase4 QC/QA tools | no |
| unified_downloader.py | ARCHIVE | unified multi-source downloader v3.6; acquisition complete | no |
| unified_downloader_v2.py | ARCHIVE | unified multi-source downloader v2 (older than unified_downloader.py despite the name); acquisition complete | no |
| upsample_imagery.py | ARCHIVE | reprojects source imagery onto 2020 reference grid; Phase 1 registration/upsample complete | no |
| visualize_bands.py | ARCHIVE | 4-band tile visualizer for 2020 aerial chunks; one-off | no |
| visualize_clips.py | ARCHIVE | before/after clip alignment HTML viewer (dup of build_clip_viewer.py); registration complete | no |
| pipeline_config.py | KEEP | shared infra (paths/config) | n/a |
| pipeline_log.py | KEEP | shared infra (write_step_log/StepLogger) | n/a |
| phase0_instance_seg.py | KEEP | Phase 0 instance seg | n/a |
| phase1_preprocess.py | KEEP | Phase 1 | n/a |
| phase1a_autolabel.py | KEEP | Phase 1 | n/a |
| phase1b_sampling.py | KEEP | Phase 1 | n/a |
| phase1c_review.py | KEEP | Phase 1 | n/a |
| phase1d_classifier.py | KEEP | Phase 1 | n/a |
| phase2_data_prep.py | KEEP | Phase 2 | n/a |
| phase3_semantic_dev.py | KEEP | Phase 3 | n/a |
| phase3_make_segmentation_png.py | KEEP | Phase 3 | n/a |
| phase4_semantic_finetune.py | KEEP | live Phase 4 engine | n/a |
| phase4_label_review.py | KEEP | Phase 4 review | n/a |
| phase4_label_review_prep.py | KEEP | Phase 4 review | n/a |
| phase4_qc_ndvi.py | KEEP | Phase 4 QC | n/a |
| phase4_qc_score.py | KEEP | Phase 4 QC | n/a |
| phase4_qc_indep.py | KEEP | Phase 4 QC | n/a |
| phase4_qc_forest_misses.py | KEEP | Phase 4 QC | n/a |
| phase4_qc_site.py | KEEP | Phase 4 QC | n/a |
| phase4_qc_flicker.py | KEEP | Phase 4 QC | n/a |
| phase4_build_corrected_labels.py | KEEP | Phase 4 label overlay | n/a |
| phase4_viz.py | KEEP | Phase 4 viz | n/a |
| phase4_qa_overlay.py | KEEP | Phase 4 QA | n/a |
| phase4_threshold_diagnostic.py | KEEP | Phase 4 diagnostic | n/a |
| phase4_sentinel_snap.py | KEEP | Phase 4 sentinel snapshots | n/a |
| make_positive_site.py | KEEP | site staging | n/a |
| make_grass_negatives.py | KEEP | site staging | n/a |
| fetch_build_chm.py | KEEP | live CHM builder | n/a |
| version_script.py | KEEP | retired-but-referenced in docs, keep in place per instructions | n/a |

## Notes / uncertain items

- **log_integration_patch.py** — this is functionally a *documentation-as-code* file (shows
  the exact patch pattern used to wire `pipeline_log.py` into scripts). It's not imported by
  anything, but it may still have reference value as a "how we did the logging migration"
  note. Safe to archive by the no-import rule, but flagging in case you want it kept as a
  how-to reference rather than filed away as dead acquisition code.
- **temporal_overlay.py** — doesn't fit the "pre-Phase-0 acquisition" bucket as cleanly as the
  downloaders; it's a QA overlay tool (phase0 crowns onto multi-year imagery) that could have
  been used during Phase 1/2 development. No active script references it and nothing in the
  current phase4 QC suite calls it, so it reads as superseded by the phase4_qc_* tools, but
  flagging since its purpose is closer to the live pipeline's domain than the downloaders.
- **fetch_be_build_struct.py** — only functional evidence of "superseded" status is CLAUDE.md's
  own note that `lidar_snoh_structure.tif` / `_hillshade_fr.tif` are "older struct experiments
  (superseded)" and one comment in `phase4_semantic_finetune.py` mentioning the script name in
  prose (not a code import). Confident this is dormant, just noting the evidence is doc-based
  rather than a hard import-grep hit.
- **unified_downloader.py vs unified_downloader_v2.py** — naming is inverted: the internal
  header of `unified_downloader.py` says "v3.6" while `unified_downloader_v2.py` says "v2", so
  `unified_downloader.py` is actually the newer/final one. Both are dormant either way (acquisition
  complete), just flagging so you don't archive assuming the "_v2" file is newer.
