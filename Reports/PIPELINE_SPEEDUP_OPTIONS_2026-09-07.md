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
