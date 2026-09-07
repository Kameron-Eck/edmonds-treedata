# Queue-ledger recovery, 2026-09-01 .. 2026-09-07 — CANDIDATE

Writer: `qc/instruments/rebuild_queue_ledger.py::main`  ·  output `train_queue_status_recovered_20260901_20260907.csv`

**NOTHING WAS WRITTEN TO THE DATA LAKE.** Both output paths are checked against every lake root (`lake.BASE`, `lake.COLAB_BASE`, `lake.LOCAL_BASE`) by `rebuild_queue_ledger.py::assert_not_lake` before a byte is written; the lake is opened read-only, for the nohup and step logs. This CSV is a CANDIDATE and is **not part of any ledger** until a human copies it beside the others on the lake — at which point every reader (`phase4seg/names.py::status_files`) merges it.

## What the rows are

- **252 snapshot-native rows** — copied byte-for-byte from the orphaned `.part.*`/`.prev.*` temps. No prefix, no rewrite.
- **198 rows synthesised from logs** — `detail` begins `RECOVERED-FROM-LOGS:` and quotes the line that is the evidence. Synthesis happens only where NO snapshot row covers `(year, tag, step)`.
- **450 rows total** after de-duplication on the full 11-tuple.

## Two things a reader must know about the synthesised rows

1. **`ts` means something slightly different.** A queue-written row carries the step's START (`phase4_train_queue.py::run_step` stamps `ts` before launching the child and mutates the same dict on completion). The nohup log has no timestamps, so a recovered row carries the engine step log's `completed:` — up to `minutes` LATER than the queue would have written. Because synthesis only fills keys with no queue-written row, no reader's latest-wins ever compares the two for one key.
2. **`minutes` is the queue's own number, never the step log's `elapsed`.** That field is a formatted string whose unit varies with magnitude (`pipeline_log.py::StepLogger._write` emits `0.0s`, `1.1min` or `1.10h`) and it spans the ENGINE's `started:`→`completed:`, while the queue's clock also covers spawning the child, its pip bootstrap and its imports. Measured: labels/2011s reads `0.0s` against the queue's `5.4`, and postproc/2017 reads `1.10h` against the queue's `66.6`. `cost_report` sums this column, so a `TIMEOUT` row — which prints no minutes — is left blank rather than filled from the step log.

Consequence of the `detail` prefix, recorded rather than hidden: `queue_verify.py::_mb_from_verdict` anchors `(\d+)MB` at the START of a VERIFY detail, so a prefixed detail reads as "no size recorded" and a later fully-skipped-job re-check degrades from `OK_CACHED`/`SIZE_CHANGED` to `UNVERIFIED` (existence only). That keeps the resume credit and forces a re-verify; it can never produce a false OK.

## Rows per source

### Snapshots

| snapshot file | rows |
|---|---|
| train_queue_status.csv.part.100013a8e6 | 12 |
| train_queue_status.csv.part.11595b5648 | 20 |
| train_queue_status.csv.part.1159bc2ad9 | 15 |
| train_queue_status.csv.part.12427521346 | 30 |
| train_queue_status.csv.part.12427807b6b | 33 |
| train_queue_status.csv.part.124279fc032 | 7 |
| train_queue_status.csv.part.12427a6a62d | 17 |
| train_queue_status.csv.part.1674856ff79 | 10 |
| train_queue_status.csv.part.172813574f | 18 |
| train_queue_status.csv.part.1732359839 | 3 |
| train_queue_status.csv.part.2265ac40d0 | 36 |
| train_queue_status.csv.part.2265e8e280 | 43 |
| train_queue_status.csv.part.23178e1c5e | 15 |
| train_queue_status.csv.part.2317948d4d | 38 |
| train_queue_status.csv.part.23610151a2 | 11 |
| train_queue_status.csv.part.2653611e73 | 1 |
| train_queue_status.csv.part.26537e81ea | 4 |
| train_queue_status.csv.part.33780a58c4 | 1 |
| train_queue_status.csv.part.49301e749d | 27 |
| train_queue_status.csv.part.49305a5b36 | 25 |
| train_queue_status.csv.part.493080da1b | 9 |
| train_queue_status.csv.part.4930819223 | 13 |
| train_queue_status.csv.prev.2d5587 | 13 |
| train_queue_status.csv.prev.aa5c64 | 51 |
| train_queue_status.csv.prev.bf1499 | 17 |

Raw snapshot rows read: **469**; distinct on the full 11-tuple: **252**, of which **125** appear in more than one snapshot (a launch flushes its whole table after every step, so its earlier rows are re-written into every later orphan). The shared `train_queue_status.csv` copy is EXCLUDED (it is the clobbered file, not a launch orphan); including it with `--include-shared` adds its single row, which is where the README's 252 and a naive 253 differ.

### Nohup logs (queue-level lines)

| nohup log | queue | step outcomes | VERIFY lines | blocks w/o outcome |
|---|---|---|---|---|
| train_queue_nohup_pilot_offload_2017k_cpu1_20260907T214557Z.log | pilot_offload_2017k_cpu1 | 2 | 3 | 0 |
| train_queue_nohup_queue_hard_year_pilot_20260901T172249Z.log | queue_hard_year_pilot | 2 | 2 | 1 |
| train_queue_nohup_queue_hard_year_pilot_20260901T180008Z.log | queue_hard_year_pilot | 0 | 0 | 0 |
| train_queue_nohup_queue_hard_year_pilot_20260901T194701Z.log | queue_hard_year_pilot | 4 | 3 | 0 |
| train_queue_nohup_queue_hard_year_pilot_20260901T211844Z.log | queue_hard_year_pilot | 6 | 7 | 0 |
| train_queue_nohup_queue_hard_year_pilot_only2006s_20260901T175906Z.log | queue_hard_year_pilot_only2006s | 4 | 5 | 0 |
| train_queue_nohup_queue_overlap_floor_20260905T145647Z.log | queue_overlap_floor | 18 | 21 | 0 |
| train_queue_nohup_queue_overlap_floor_20260905T145756Z.log | queue_overlap_floor | 14 | 16 | 0 |
| train_queue_nohup_queue_overlap_floor_20260906T002156Z.log | queue_overlap_floor | 1 | 1 | 0 |
| train_queue_nohup_queue_overlap_floor_20260906T014007Z.log | queue_overlap_floor | 6 | 7 | 0 |
| train_queue_nohup_queue_tier1_science_sample_20260902T051246Z.log | queue_tier1_science_sample | 14 | 21 | 0 |
| train_queue_nohup_queue_tier1_science_sample_20260902T180915Z.log | queue_tier1_science_sample | 4 | 6 | 1 |
| train_queue_nohup_queue_tier1_science_sample_20260902T195556Z.log | queue_tier1_science_sample | 23 | 32 | 0 |
| train_queue_nohup_queue_tier1_science_sample_20260902T235247Z.log | queue_tier1_science_sample | 0 | 0 | 0 |
| train_queue_nohup_queue_tier1_science_sample_20260902T235317Z.log | queue_tier1_science_sample | 0 | 0 | 0 |
| train_queue_nohup_queue_tier1_science_sample_20260903T001427Z.log | queue_tier1_science_sample | 18 | 36 | 0 |
| train_queue_nohup_queue_tier1_science_sample_20260903T032756Z.log | queue_tier1_science_sample | 9 | 18 | 0 |
| train_queue_nohup_queue_trend8_uniform_rgb_20260905T023256Z.log | queue_trend8_uniform_rgb | 0 | 0 | 0 |
| train_queue_nohup_queue_trend8_uniform_rgb_20260905T023448Z.log | queue_trend8_uniform_rgb | 0 | 0 | 0 |
| train_queue_nohup_queue_trend8_uniform_rgb_20260905T031154Z.log | queue_trend8_uniform_rgb | 24 | 28 | 0 |
| train_queue_nohup_queue_trend8_uniform_rgb_20260905T031304Z.log | queue_trend8_uniform_rgb | 24 | 28 | 0 |

**Join integrity, re-measured this run.** 175 `$` command blocks; 173 closed with a queue outcome line (2 did not); 173 of those name exactly one step log through the `✓ log → …` path the engine prints, and 173 of those step logs are present on the lake. That path is the join key rather than `run_id`, because it survives the block whose run manifest failed to write (measured: 2017/postproc, 2026-09-05, `[Errno 5]`). Step logs actually opened for a timestamp: **93** — only an uncovered event needs dating.

Also on the mount: the unstamped `train_queue_nohup.log` — the pre-P11 default name, which carries no launch stamp, so no window can admit it. Measured, not assumed: it names queue `queue_2024_finish.yaml` and holds 0 queue-level event(s) plus 5 line(s) that write no row (resume skips and unclosed blocks). Not read into this candidate.

## Coverage by tag

`snapshot` / `recovered` name where each step's row came from; `—` means no row exists in either source. A `—` is not proof the step never ran: a job may declare a steps SUBSET, and a resume skip writes no row at all. Launch-level `GUARD:runtag` rows (19 of them) carry no year or tag and form no arm, so they appear in no line here.

| tag | year | campaign (queue file) | labels | tile | train | evaluate | inference | postproc | VERIFY |
|---|---|---|---|---|---|---|---|---|---|
| hy_e3_2006s | 2006s | queue_hard_year_pilot | recovered | recovered | recovered | recovered | recovered | recovered | recovered |
| hy_e3_2011s | 2011s | queue_hard_year_pilot | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | recovered |
| of_2017 | 2017 | queue_overlap_floor | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot |
| of_2017k | 2017k | queue_overlap_floor | snapshot | snapshot | recovered | recovered | recovered | recovered | recovered |
| of_2017n | 2017n | queue_overlap_floor | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | recovered |
| of_2017s | 2017s | queue_overlap_floor | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot |
| of_2020 | 2020 | queue_overlap_floor | snapshot | snapshot | snapshot | snapshot | recovered | recovered | recovered |
| of_2022 | 2022 | queue_overlap_floor | recovered | recovered | recovered | recovered | recovered | recovered | recovered |
| spd_2017k | 2017k | pilot_offload_2017k_cpu1 | snapshot | snapshot | — | — | — | — | recovered |
| t1_2006s_add05 | 2006s | queue_tier1_science_sample | recovered | recovered | snapshot | snapshot | snapshot | — | snapshot |
| t1_2006s_add16 | 2006s | queue_tier1_science_sample | recovered | recovered | snapshot | snapshot | snapshot | — | snapshot |
| t1_2006s_base | 2006s | queue_tier1_science_sample | recovered | recovered | snapshot | snapshot | snapshot | — | snapshot |
| t1_2006s_in05 | 2006s | queue_tier1_science_sample | recovered | recovered | snapshot | snapshot | snapshot | — | snapshot |
| t1_2006s_in16 | 2006s | queue_tier1_science_sample | recovered | recovered | snapshot | snapshot | recovered | — | snapshot |
| t1_2011s_add05 | 2011s | queue_tier1_science_sample | — | — | snapshot | snapshot | recovered | — | snapshot |
| t1_2011s_add16 | 2011s | queue_tier1_science_sample | — | — | snapshot | — | recovered | — | recovered |
| t1_2011s_base | 2011s | queue_tier1_science_sample | — | — | snapshot | snapshot | recovered | — | snapshot |
| t1_2011s_base_s2 | 2011s | queue_tier1_science_sample | — | — | snapshot | snapshot | recovered | — | snapshot |
| t1_2011s_base_s3 | 2011s | queue_tier1_science_sample | — | — | snapshot | — | recovered | — | recovered |
| t1_2011s_cor02 | 2011s | queue_tier1_science_sample | — | — | snapshot | — | — | — | — |
| t1_2011s_cor05 | 2011s | queue_tier1_science_sample | — | snapshot | snapshot | snapshot | recovered | — | snapshot |
| t1_2011s_cor10 | 2011s | queue_tier1_science_sample | snapshot | snapshot | snapshot | snapshot | recovered | — | snapshot |
| t1_2011s_in05 | 2011s | queue_tier1_science_sample | — | — | snapshot | snapshot | recovered | — | snapshot |
| t1_2011s_in16 | 2011s | queue_tier1_science_sample | — | — | snapshot | — | recovered | — | recovered |
| t1_2016_add05 | 2016 | queue_tier1_science_sample | — | — | — | — | recovered | — | recovered |
| t1_2016_add16 | 2016 | queue_tier1_science_sample | — | — | — | — | recovered | — | recovered |
| t1_2016_base | 2016 | queue_tier1_science_sample | snapshot | snapshot | snapshot | — | recovered | — | recovered |
| t1_2016_in05 | 2016 | queue_tier1_science_sample | — | — | snapshot | snapshot | snapshot | — | snapshot |
| t1_2016_in16 | 2016 | queue_tier1_science_sample | — | — | snapshot | snapshot | snapshot | — | snapshot |
| t1_2016_nir | 2016 | queue_tier1_science_sample | — | — | snapshot | snapshot | snapshot | — | snapshot |
| t1_2019n_base | 2019n | queue_tier1_science_sample | recovered | recovered | recovered | recovered | recovered | — | recovered |
| t1_2019n_nir | 2019n | queue_tier1_science_sample | recovered | recovered | recovered | recovered | recovered | — | recovered |
| t1_2020_add05 | 2020 | queue_tier1_science_sample | — | — | recovered | recovered | snapshot | — | recovered |
| t1_2020_add16 | 2020 | queue_tier1_science_sample | — | — | snapshot | — | recovered | — | recovered |
| t1_2020_base | 2020 | queue_tier1_science_sample | — | — | snapshot | recovered | snapshot | — | snapshot |
| t1_2020_in05 | 2020 | queue_tier1_science_sample | recovered | recovered | recovered | recovered | recovered | — | recovered |
| t1_2020_in16 | 2020 | queue_tier1_science_sample | recovered | recovered | recovered | recovered | recovered | — | recovered |
| trend8_2009 | 2009 | queue_trend8_uniform_rgb | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot |
| trend8_2011s | 2011s | queue_trend8_uniform_rgb | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot |
| trend8_2013 | 2013 | queue_trend8_uniform_rgb | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot |
| trend8_2015 | 2015 | queue_trend8_uniform_rgb | snapshot | snapshot | snapshot | recovered | recovered | recovered | recovered |
| trend8_2016 | 2016 | queue_trend8_uniform_rgb | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot |
| trend8_2019 | 2019 | queue_trend8_uniform_rgb | recovered | recovered | recovered | recovered | recovered | recovered | recovered |
| trend8_2021 | 2021 | queue_trend8_uniform_rgb | recovered | recovered | recovered | recovered | recovered | recovered | recovered |
| trend8_2024 | 2024 | queue_trend8_uniform_rgb | snapshot | snapshot | snapshot | snapshot | snapshot | snapshot | recovered |

## Refused — evidence present, but not enough to write a row

| source | line | year/tag/step | why | evidence |
|---|---|---|---|---|
| train_queue_nohup_queue_hard_year_pilot_20260901T172249Z.log | 307 | — | the queue never printed a terminal outcome for this step — the runtime died mid-step; no state to record | `-u /content/repo/Scripts/pipeline/phase4_semantic_finetune.py --year 2006s --step train --infer-batch 32 --run-tag hy_e3_2006s --force-citywide --no-hillshade` |
| train_queue_nohup_queue_tier1_science_sample_20260902T180915Z.log | 826 | — | the queue never printed a terminal outcome for this step — the runtime died mid-step; no state to record | `-u /content/repo/Scripts/pipeline/phase4_semantic_finetune.py --year 2006s --step train --infer-batch 32 --run-tag t1_2006s_add16 --force-citywide --sample-manifest /content/drive/MyDrive/treedata/phase4/qc/sample_tiles_2006s.csv --no-hillshade --add-canopy-mask /content/drive/MyDrive/treedata/phase4/labels_corrected/add_chm2016.tif` |

Also not synthesised, by design: `GUARD:runtag` rows (not step outcomes, and the nohup log carries no timestamp for them — the snapshots already hold 19); resume skips (`- skip job/step (already OK)`, 3 in the window); D7 re-verifies of skipped steps (0 in the window).

## Diagnostic — a later hard outcome the log shows and the ledger may not

Keys the snapshots DO cover, where a nohup log shows a hard state newer than the newest surviving snapshot row. Nothing is written for these (the suppression rule stands); they are listed because this is exactly the D10 hazard — a later FAIL that revoked an earlier OK — and a ledger missing one grants resume credit for a step that failed.

Both diagnostics below are computed over the SNAPSHOT rows only. A synthesised row can never be the newest for one of these keys — synthesis happens exclusively where no snapshot row exists — so merging cannot move either answer.

`later in the logs` is what any log shows for the SAME key afterwards — a hard state with a later OK behind it was already recovered by a relaunch and is not a standing failure. Both of those rows are suppressed here (the key is snapshot-covered), so the log is the only place that recovery is visible at all.

| year/tag/step | log state | log ts | newest snapshot ts | later in the logs | source | line |
|---|---|---|---|---|---|---|
| 2017k/of_2017k/VERIFY:tile | MISSING | 2026-09-06 00:37:50 | 2026-09-05 15:14:04 | OK @ 2026-09-06 02:03:07 | train_queue_nohup_queue_overlap_floor_20260906T002156Z.log | 91 |

### And the mirror case: a surviving row that is still mid-step

`phase4_train_queue.py::run_step` appends its row as `RUNNING`, flushes, then mutates that SAME dict on completion. An orphan snapshotted between those two flushes preserves the `RUNNING`, and if it is the newest surviving row for that key the ledger's last word is a state `queue_ledger.py::_completed_steps` counts as a REVOCATION — so the step is marked for re-run even though the log says it finished. Suppression keeps the log's terminal row out (the key is covered), so these are listed instead.

| year/tag/step | newest snapshot | at | log says | at | source | line |
|---|---|---|---|---|---|---|
| 2024/trend8_2024/postproc | RUNNING | 2026-09-05 10:15:47 | OK | 2026-09-05 11:21:46 | train_queue_nohup_queue_trend8_uniform_rgb_20260905T031154Z.log | 5085 |

### Rows that share a timestamp and disagree on state

**1 key(s)** carry two states at ONE timestamp — the same mid-step artefact, both halves surviving. `_merged_rows` sorts by `ts` alone and its sort is stable, so which one a reader consumes LAST is decided by ROW ORDER, not by the timestamp. `rebuild_queue_ledger.py::_sort_key` puts the non-terminal row FIRST within such a group, so the terminal row has the final word — which is what the queue's own per-launch file (one mutated row per step) would have shown.

| job/year/tag/step | ts | states |
|---|---|---|
| trend8_uniform_rgb_trend8_2011s/2011s/trend8_2011s/tile | 2026-09-05 04:44:54 | OK, RUNNING |

## What to do with this file

Nothing, until Kam decides. Restoring means copying `train_queue_status_recovered_20260901_20260907.csv` into `phase4/qc/` **on the lake**, after which resume credit, `cost_report`, `registry_from_manifests` and `pilot_gate` all merge it. That changes the audit trail and is not an autonomous action (`phase4/qc/ledger_recovery/README.md`).

