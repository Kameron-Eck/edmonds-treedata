# Speeding up the pipeline — options, costed against the logs

**2026-09-07.** Three option lanes (I/O code, training internals, infrastructure), each
with an adversarial referee required to re-derive every projected saving from the measured
logs. The referees corrected two headline recommendations and one of my own framings.

---

## 0. The measurement that reframes the question

**The A100 is idle 82% of the time it is paid for.** Pooled across 28,993 valid 5-second
samples from 10 GPU-bearing VM sessions (`phase4/logs/hw_*.csv`): mean utilisation
**11.4%**, median **0%**, **82.1% of samples at exactly 0%**, only 1.3% at or above 90%.

That single number decides most of what follows. A faster GPU cannot help a GPU that is
waiting, and the entire storage bill — ortho staging 6.42 h + tile staging 4.10 h +
copies 0.87 h = 11.39 h of 68.45 h — caps a *perfect* storage purchase at **16.6%**.

## 1. Where the time is, measured

134 h of logged engine time: train 45%, tile 17%, inference 15%, postproc 13%,
evaluate 10%. Drive gives **40 MB/s on one big sequential file** and **1.3 MB/s on many
small files** — a 30× penalty for file count, and every slow phase is a many-small-files
phase.

## 2. Code changes, ranked by measured forward saving

| # | change | forward saving | risk |
|---|---|---|---|
| 1 | Strip `optim_state` from `sem_best` (891.8 MB → 371 MB) | **3.6 h** | low, ~15 lines |
| 2 | Keep the staged ortho instead of re-staging it | **2.32 h** | needs disk eviction |
| 3 | Tile handoff: `rmtree` → tagged `os.replace` | **1.78 h** | low, self-contained |
| 4 | Write `sem_best` at phase boundaries, not every improving epoch | 2.2 h | reintroduces lost-checkpoint-on-VM-death |

**#2 is the referee's pick and it is understated in the proposal.** Five unlink sites
(`labels.py:353`, `tiling.py:459/461/463`, `core.py:1333/1598`) throw away an ortho the
next step re-stages. Re-staging is **42% of all staged seconds all-time, 53% post-08-30**;
the worst single case is `2020_coe_rgb.tif` at **1.02 h of pure re-staging**. It also
reaches inference, whose ortho staging is a 5.25 h pool (n=110). It must ship as a
capacity-aware scratch cache with LRU eviction, not as three deleted lines: `hw_t1gpuF.csv`
shows an ~87 GB runtime already down to **6.0 GB free** under today's delete-everything
behaviour, and commit `5096b03` has just started holding 3.0–6.7 GB probability rasters too.

**A correction to my own framing.** I flagged "15 checkpoint copies × 773 MB" as expensive.
The *copy* is not: all 1,376 `sem_best` copies in the entire log history total **1.24 h**,
median **1.9 s** — an implied ~407 MB/s, because the write lands in the rclone VFS cache.
Pricing a write at the Drive *read* rate is what produced the inflated estimate, and the
same error appeared in two lane proposals. The real cost is the **per-save tax of
+30.56 s (se 1.31)** — sha256 + md5, the read-back verify, and serialisation — which is a
different quantity from the copy.

## 3. What to buy

**Concurrency. It is the only purchasable lever that divides the total rather than shaving
a slice of it.** Post-fix, a full-archive arm needs **26.8 A100-hours** of GPU-bearing
steps (train 31.9 + evaluate 6.4 + inference 5.1 min per acquisition × 37):

| concurrent A100s | wall-clock for a full-archive arm |
|---|---|
| 2 (today's cap) | 13.4 h |
| 4 | 6.7 h |
| 6 | 4.5 h |
| 8 | 3.4 h |

The cap is an account-level assignment limit (`TooManyAssignmentsError`), not scarcity —
so this is a purchasing/quota question, not an engineering one.

**Storage** is real but bounded: a perfect purchase caps at 16.6%. GCS with a read cache is
sound physics and was oversized in the proposal.

## 4. What NOT to do, each refuted by measurement

- **Buy a bigger or faster GPU** (H100, A100-80GB, the RTX PRO 6000 already available).
  The GPU is idle 82% of the time. This is the intuitive purchase and the measurements
  refute it outright.
- **Replace the ortho copy with windowed reads off Drive.** `_gather_citywide_coarse`
  reads `CITYWIDE_CANDIDATE_TARGET = 8000` positions of 512×512×3 = **6.3 GB decompressed
  regardless of ortho size**, and `CITYWIDE_CANDIDATE_STRIDE = 256` against `TILE_SIZE =
  512` means coarse years scan roughly **4× the raster**. Trading one 40 MB/s sequential
  copy for 8,000 random FUSE reads is the access-shape mistake pointed the wrong way.
- **Cut the epoch budget or drop Phase A.** Both phases are TRUNCATED, NOT CONVERGED:
  Phase A's best epoch is a median 18 of a 20 cap with 51 of 87 runs peaking at ≥18;
  Phase B's best-epoch mode is 29 of 30, with 37 of 71 runs peaking in epochs 23–30. This
  is evidence we are UNDER-training, and any epoch cut is a science change, not a speedup.
- **Retrofit-convert the 82 existing tile sets to archives.** 48.9 GB at 1.3 MB/s is
  **10.4 h of download** to buy a 7.4 h saving that the tile handoff mostly already takes.

## 5. Recommended order

1. **Ask for a higher concurrency cap** — costs nothing to ask, blocks on a third party,
   and is worth more than every code change combined.
2. **Ortho scratch cache with LRU eviction** (2.32 h, and it reaches inference).
3. **Strip `optim_state`** (3.6 h, ~15 lines, low risk).
4. **Tile handoff** (1.78 h, self-contained).
5. **Profile one training epoch** before anything else in the training loop — the free
   gate that tells us whether the remaining GPU time is real compute or more waiting.

Every number above is either from a tracked file or from a referee's re-derivation over
`phase4/logs/`. Where a lane's arithmetic did not survive re-derivation, the corrected
figure is the one printed.

---

## 6. WHY the GPU is idle — attributed to the step that was running

The 82% figure is not one problem. Matching every 5-second hardware sample to the engine
step running at that timestamp (39.5 h of paid GPU time, 11 GPU-bearing sessions):

| step | idle h | busy h | share of ITS OWN time spent idle |
|---|---|---|---|
| train | 10.3 | 2.1 | **83%** |
| tile | 6.3 | 0.1 | **98%** |
| inference | 5.7 | 4.7 | 54% |
| postproc | 5.2 | 0.2 | **96%** |
| (between steps) | 4.2 | 0.0 | **100%** |
| evaluate | 0.6 | 0.0 | 95% |

**Two distinct causes, and they need different fixes.**

**(a) ~15.7 h — 40% of all paid GPU time — is spent running things that never needed a
GPU.** Tiling is 98% idle, postproc 96%, and 4.2 h is dead time between steps with the
runtime alive and nothing executing. These steps are torch-free or nearly so, and CPU
runtimes cost zero compute units. Postproc has already been moved to free CPU VMs for some
campaigns; tiling has not.

**(b) Training itself runs the GPU only 17% of the time.** 10.3 h idle against 2.1 h busy.
Classifying those idle samples by what else was active: model loaded with **CPU pegged
above 50% for 3.0 h** (augmentation and dataloading cannot feed the device), **nothing
busy at all for 4.9 h**, local disk busy 1.7 h, and network only 0.3 h. So training is
starved by CPU-side work and by the per-save tax, not by Drive bandwidth.

**Why this refutes buying a faster GPU, arithmetically.** The device does **7.2 h of real
work inside 39.5 h of paid time**. A GPU twice as fast finishes that work in 3.6 h and the
total becomes 35.9 h — a **9% saving**. A GPU that took literally zero time would save
**18%**. Concurrency divides the whole 39.5 h; a faster device can only ever touch the 7.2.

---

## 7. Where the idle time actually goes — corrected attribution, and what to do about it

§6's per-step table had **two defects that are fixed here**, so where the numbers differ,
**the ones below supersede it**.

**(a) Cross-VM contamination.** §6 matched every hardware sample against step intervals
from *all* VMs, first hit wins. The sessions overlap heavily — `trend8A2`/`trend8B2` run
concurrently for ~8 h, `ofA`/`ofB` for ~6 h, `t1gpuE` sits entirely inside `t1gpuD` — so a
`train` sample from one VM could be labelled `tile` because another VM's tiling matched
first. Only `of2017k2` carries a `session` value in `train_queue_status.csv`, so a clean
per-VM join exists for that one session and nowhere else.
**(b) The dead-sample test omitted network TX.** It tested `net_rx_mb_s` and never
`net_tx_mb_s`, so checkpoint uploads and mask writes counted as "nothing happening".

Recomputed with TX included, dropping the 29% of samples where concurrently-open
intervals disagree (8,304 of 28,999):

| step | hours | GPU>5% | CPU>50% | net TX | net RX | disk | **NOTHING** |
|---|---|---|---|---|---|---|---|
| train | 8.6 | 13% | 34% | **26%** | 6% | 19% | 31% |
| inference | 6.5 | **44%** | 0% | 1% | 22% | 31% | 29% |
| (between steps) | 5.0 | 0% | 0% | 8% | 7% | 2% | **84%** |
| postproc | 4.2 | 0% | 0% | 3% | 2% | 0% | **96%** |
| tile | 3.7 | 0% | 0% | 9% | 18% | 13% | **71%** |
| evaluate | 0.6 | 4% | 0% | 5% | 3% | 1% | **87%** |

Validated against the one session with verified attribution (`of2017k2`, joined on the
queue `session` column): postproc **100%** nothing, tile 76%, train 26%, inference 76%
GPU-busy. Same picture at n=1 VM, so the ambiguity filter is not manufacturing the result.

### 7.1 The mechanism — why every counter reads zero at once

`NOTHING` means GPU <5%, CPU <15%, disk <5 MB/s, and **both** network directions
<1 MB/s simultaneously. That is not idleness; it is a process blocked on Drive FUSE
per-file latency. Two things conspire to make it invisible: `vm_hwlogger.cpu_pct` computes
`idle = vals[3] + vals[4]  # idle + iowait`, so blocked-on-I/O time is **counted as idle**,
and the cost is round-trips rather than bytes, so **no bandwidth counter registers it**.

The repo already contains the proof and the cure, in `staging.py`'s own comment: *613 tiles
took 55+ min with the GPU at 0%*, replaced by one bulk `rclone copy` at **78–138 s** — a
~30× improvement on identical volume. That fix was applied to the tile READ direction
(2026-08-29) and the tile WRITE direction (`tiling.py`). **`core.py:1559` holds the only
`ThreadPoolExecutor` in the engine**; every other transfer is a sequential `shutil.copy2`.

### 7.2 Two corrections to committed numbers

**`evaluate` is not meaningfully GPU-bearing.** It is GPU-busy in **4%** of its samples and
"nothing" in 87%, scoring a median of ~200 held-out tiles in a **median 7.8 min (max 56.3)**
— the forward pass is seconds and the rest is checkpoint load and report write. §3 priced a
full-archive arm at 43.4 min of GPU-bearing steps by counting evaluate's 6.4 min; the
honest figure is **~37 min**, which improves every row of the concurrency table.

**Training spends a quarter of its time uploading.** Net TX exceeds 1 MB/s in **26%** of
train samples — ~2.2 h of the 8.6 h sampled. That is the checkpoint path, and it is
independent measured support for stripping `optim_state` (891.8 MB → 371 MB), already
ranked first among code changes in §2.

### 7.3 The offload rule, stated from the measurement

**A step belongs on a free CPU runtime when its GPU-busy fraction is ~0 AND its handoff to
a GPU step is bulk-transferable.** Applied to the logged totals:

| step | GPU busy | logged total | verdict |
|---|---|---|---|
| postproc | 0% | 9.0 h | **offload, unconditional** |
| tile | 0% | 22.8 h | **offload** — safe only because `_bulk_stage_tiles` now exists |
| evaluate | 4% | 12.6 h | offload-capable; better fixed in-process after train |
| train | 13% (34% CPU>50%) | 39.5 h | keep on GPU |
| inference | 44% | 12.0 h | keep on GPU — the only step genuinely using the device |

**31.8 h of logged engine time (tile + postproc) never needed a GPU at all.** Tiling could
not have been offloaded before 2026-08-29: without the bulk path the tiles would have
crossed the many-small-files FUSE penalty between VMs, which is worse than the idling.

**One interaction to state rather than let a referee find it:** offloaded tiling stages the
ortho on the CPU VM, so the GPU box no longer arrives with that ortho warm for inference.
That trades against §2's LRU scratch-cache option and the two must be designed together.

### 7.4 What offloading does and does not buy

Offloading moves waste to a machine that costs 0 compute units. It converts **money**, not
wall-clock — the pipeline finishes no sooner unless the offloaded work runs *concurrently*
with GPU work on other years. Wall-clock comes from three separable levers, and they are
not interchangeable:

| lever | saves wall-clock | saves money |
|---|---|---|
| more concurrent runtimes (§3, still ranked first) | yes, divides everything | no |
| bulk / parallel I/O instead of per-file FUSE | yes, on every machine | yes |
| offload torch-free steps to CPU VMs | only if run concurrently | yes |

### 7.5 Standing caveat on all of §6 and §7

**Every hardware sample predates commit `5096b03`** (last sample 2026-09-06 03:44; the fix
landed 2026-09-07 09:33). That commit stopped the multi-GB probability-raster FUSE
round-trip between inference and postproc, so **the 96%-nothing postproc figure describes
pre-fix behaviour and may already be partly obsolete**. Postproc must be re-measured, not
re-fixed. The queued `heal_infill_2017_2023` campaign is the natural post-fix measurement
run: it produces fresh `hw_*.csv` at no additional cost beyond the GPU time already sought.

## 8. Implementation record (2026-09-07)

§2 row 1 ("strip `optim_state` from `sem_best`") shipped. This section is the tracked home
for the two measurements behind it — they were quoted in `phase4seg/ckpt.py` and
`qc/test_select_smooth.py` docstrings as "measured" with no file anywhere holding them,
which is the kind of number that rots the day it is re-taken (CLAUDE.md 3.4b). Both were
**re-derived independently here**, not copied from the implementing pass's report
(CLAUDE.md 3.4c).

### 8.1 Parameter census — MEASURED, local CPU

```
py -3.12 -c "from phase4seg import ckpt, core, config; \
m=ckpt.ARCHS['unet']['build'](); tot=sum(p.numel() for p in m.parameters()); \
core._freeze_encoder(m); \
print(tot, sum(p.numel() for p in m.parameters() if p.requires_grad))"
```

Production build (`ARCHS["unet"]`, `IN_CHANNELS=3`, `AUX_HEIGHT=False`): **92,680,577
parameters**, of which **50,180,417** still require grad after
`phase4seg/core.py::_freeze_encoder`. AdamW carries two fp32 moment buffers per **stepped**
parameter, so Phase A — which freezes first and builds the optimiser over `requires_grad`
params only — has ~1.08× the weights in optimiser state where Phase B has ~2×. That is the
whole reason the saving is not one number.

### 8.2 Checkpoint size, with and without optimiser state — MEASURED, local CPU

Method: build the production model; construct `torch.optim.AdamW` over its `requires_grad`
parameters; set zero grads and call `.step()` once so the two moment buffers actually
materialise (a freshly-constructed AdamW has an EMPTY state dict and would understate the
payload by the whole amount at issue); attach a `StepLR`; then `torch.save` the
`phase4seg/ckpt.py::_save_ckpt_state` payload twice — once with `optim_state` /
`sched_state`, once with both `None` — to a local temp file, and `stat` each. Phase A is
the same recipe with `phase4seg/core.py::_freeze_encoder` applied before the optimiser is
built. Nothing written to the lake.

| write | with optim+sched | with both `None` | ratio | saving |
|---|---|---|---|---|
| Phase-B best (encoder trainable) | 1,113,136,145 B | 371,405,107 B | **2.997×** | 741.7 MB (66.6%) |
| Phase-A best (encoder frozen) | 772,875,507 B | 371,405,107 B | **2.081×** | 401.5 MB (51.9%) |

Byte-weighted over the archive's 106/28 split (§8.3) the saving is **64.4%** of bytes
written. **Do not quote the Phase-B ratio alone as "the" per-write saving**: `sem_best` is
written on every improving epoch and Phase A runs first.

The implementing pass reported this pair as 1,113,134,613 B → 371,403,223 B. That
reproduces here **to within 1.5–1.9 kB** — payload metadata (the `history` dict and the
phase/epoch scalars) differs between the two recipes, and nothing else can differ at this
scale. The claim is confirmed; the exact bytes are recipe-dependent and only the numbers
in the table above have a stated method behind them.

### 8.3 Lake census, and a correction to §2 row 1 — MEASURED

```
stat -c '%s' "G:/My Drive/treedata/phase4/models/sem_best_"*.pt | sort -n
```

135 files, in **three** clusters and nothing between them:

| files | size range | what it is |
|---|---|---|
| 1 | 371,405,955 B (371.4 MB) | `sem_best_2009_smooth5.pt` — the only pre-existing on-disk instance of the post-diet size, and only `phase4seg/select.py::_SmoothCkptSelector` could have written it (it has passed `None, None` since 2026-08-29) |
| 28 | 772,888,667 – 773,021,944 B (772.9–773.0 MB) | Phase-A best |
| 106 | 1,113,161,289 – 1,113,244,581 B (1113.2 MB) | Phase-B best |

**§2 row 1's "891.8 MB → 371 MB" is wrong at the 891.8 end.** The archive's `sem_best`
sizes are bimodal, and 891.8 MB sits in the empty gap between the two clusters — zero
files fall in 773.1–1113.1 MB. It was never a real file, and where it came from is NOT
reconciled here — it is neither cluster, nor their plain mean (943.1 MB), nor the
106/28-weighted mean (1042.1 MB). The 371 MB end is right (it is 8.2's measured
`without`, and the one 371.4 MB file on disk). **Treat §2 row 1's 3.6 h forward saving as
a PROJECTION built on that figure, not a measurement.** Independent measured support for
the change itself is §7.2: net TX exceeds 1 MB/s in 26% of `train` hardware samples,
~2.2 h of the 8.6 h sampled — which is this upload path — subject to the §7.5 caveat.

---

## 9. The pilot ran — what held, what did not (2026-09-08)

One acquisition (2017k), the same recipe as its baseline, split across three runtimes.
The verdict with every number and its pointer lives in
`experiments/offload_pilot_2017k.yaml`; the comparison table is
`phase4/qc/offload_pilot_2017k.csv`. In one line each:

- **Tile offload promoted.** CPU tiling reproduced the baseline tile set byte-for-byte
  (`a36d6772e88b`, 632 tiles) and the A100-bearing span fell 113.0 → **67.3 min**.
- **Checkpoint diet validated.** 1113.2 → **371.4 MB** on Drive; train 46.4 → 39.9 min with
  the tile copy identical in both runs.
- **Postproc staging validated as a mechanism, not as a default.** The staged read
  engaged (2.4 GB in 114 s, then NVMe), but a 2-vCPU runtime polygonizes 1.5× slower
  than the A100 box (653 vs 436 s), so postproc stays on the GPU box until a bigger CPU
  tier is measured. Same-machine benefit: UNDETERMINED.
- **Model unchanged.** AP 0.4338 vs 0.4275, AUROC 0.8860 vs 0.8851 — and yet the delivered
  canopy fraction moved 19.6% → 19.1% because the best-F1 threshold moved 0.558 → 0.594:
  a measured single-seed noise sample for any map number quoted at a delivered cut.
- **Four new bottlenecks measured, all now instrumented:** the ~230 s per-file tile copy
  on every train (bundle handoff in progress), the same 11.5 GB ortho staged four times
  at 37–133 MB/s (scratch cache next), 359 s of status-file merging at every queue start
  (`94cb8df`, unvalidated until the next launch), and the hardware logger losing 26% of
  samples to its own flush (fix in progress).
- **§3's concurrency table stands, with a smaller numerator:** per-acquisition GPU-bearing
  time measured here is train 39.9 + evaluate 2.1 + inference 21.6 ≈ 64 min — the tile
  and postproc minutes are off the device, and the model is the same.
