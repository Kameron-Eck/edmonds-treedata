# The full-corpus formula pass — 7,164 crops on one L4, and the guard that held 323 rows back

**Date:** 2026-09-16 · **Worktree:** `D:\edmonds-pipeline\treedata-colab`, branch
`work/20260915-colab-l4-formula`, launched at **`4b4b73e`** (the VM's own `BOOTSTRAP_READY`
line reports that commit, so this is read off the runtime, not asserted)
**Queue:** `Scripts/pipeline/queue_litkb_formula_l4_full.yaml` — 36 shards, `procs: auto`
**Executes:** `Reports/LITKB_COLAB_L4_FORMULA_2026-09-15.md` §3 (the census) and
`Reports/LITKB_COLAB_L4_CANARY2_2026-09-15.md` §11 (the two guards, the new planner)
**Contract:** CLAUDE.md §3.4 (one queue per runtime; stopping is autonomous), §3.9, §3.11,
§3.4b, §3.4c

**36 of 36 shards, 7,164 of 7,164 crops, 0 failed, 0 slice errors, 0 restarts.** Every
archive passed the local gate on all three checks — done marker, sha256 sidecar and the
server-side md5 through the service account. The runtime was stopped 38 s after the last done
marker landed, at a **launch span of 5 h 03 min 30 s**.

Two things the run settles that a simulation could not, and they point opposite ways. The
**stability guard's price came in as predicted** — ×1.219 on decode against the ×1.269 canary
2 projected — and it held **323 rows (4.5% of the corpus) out of the LaTeX corpus** that both
canaries would have written as `ok`. The **slice planner did not**: §11.5 simulated a max/min
slice ratio of 1.63× and the corpus measured **3.21×** decode-only, twice that, over a spread
of 1.53–6.61× across the 36 shards. §6 is that finding, including the three things that vary
together and which it therefore cannot separate.

---

## 1. Timeline (UTC, 2026-09-16)

| when | what |
|---|---|
| 05:08:30 – 05:08:38 | 36 shards copied to the Drive Desktop mount (local NVMe first, CLAUDE.md §3.9) |
| **05:09:05** | **all 36 verified SERVER-SIDE by md5 through the service account** — 36/36 matched on the first pass, 0 missing, 0 mismatched. `results_full/` confirmed **absent** on the lake beforehand, so kill 4 (skip a shard whose result is already present) could not swallow the run |
| 05:10:48 | `vm_ops sessions`: **`0 active runtime(s) on the account`** before the launch |
| 05:41:47 | `vm_ops launch --session litkbf3 --gpu L4 --branch work/20260915-colab-l4-formula` issued |
| 05:44:13 | launch returned — all five bootstrap signatures, incl. `WRITE_CANARY PASS` and **`BOOTSTRAP_READY 4b4b73e`**, the commit pushed to GitHub immediately before this call. **2 min 26 s** |
| 05:44:20 | `vm_ops exec --file pipeline/litkb_formula_vm_start.py --timeout 900` issued |
| 05:44:52 | the payload's own log stamp — the worker's nohup log opens |
| 05:45:39 | exec returned — **79 s** for pip install + version gate + nohup detach. `LITKB_TORCH_BEFORE` == `LITKB_TORCH_AFTER` == `2.11.0+cu128 True`; docling 2.127.0 / docling-core 2.96.0 / ibm-models 4.0.2 / transformers 5.17.0 — identical to both canaries, so the version gate did not fire and the local reference LaTeX still describes the same CodeFormula |
| 05:45:55 | shard `full00`'s parent starts |
| **05:47:53** | **writer side probed on the VM, 2 min 14 s after the exec returned** — parent worker alive (pid 2737), beat file written at 05:45:32Z, 5,422 MiB already on the card (the children loading their models) |
| 05:54:48 | **first result archive + sidecar visible server-side** |
| 06:47 | mid-run audit: `full00`'s `worker.json` pulled and read without touching the VM — `procs 6, bound_by ["vram"]`, 190 ok / 10 degenerate / 0 unstable / 0 failed, slice spread 125–210 s |
| 10:35:34 | shard `full35`'s parent starts |
| **10:44:39** | **the last done marker lands**; the worker writes its step log and exits |
| 10:45:14 | `vm_ops stop --session litkbf3` — printed **`drain check litkbf3: DRAINED (dirty 0.0 GB)`** |
| 10:45:17 | **`litkbf3: stopped`** |
| 10:45:24 | `vm_ops sessions`: **`0 active runtime(s) on the account`** |
| 10:47:55 | all 36 archives pulled, verified and parked locally |

**Launch span 05:41:47 → 10:45:17 = 5 h 03 min 30 s (5.0583 h)** on an `NVIDIA L4`. That
span, not the worker's seconds, is what Colab bills.

**The stop was 38 s after the last marker.** The self-stop watchdog never had to fire; it was
armed the whole run (`SELFSTOP_ARMED` at bootstrap, the litkb work marker in the registry, the
liveness beat advancing) and its 10-idle-minute branch was simply never reached.

---

## 2. Cost: the span is here, the delta is Kam's to read

The CU delta is **UNMEASURED in this report, deliberately.** The brief instructed that the
Colab balance page not be attempted from this session, and it was not. What this run
contributes is the other half of the arithmetic:

* **BEFORE:** `199.33 CU`, read by Kam at `2026-09-16T03:43Z` and already recorded as the
  anchor in `pipeline/colab_rates.csv` (commit `42691de`).
* **launch span:** `2026-09-16T05:41:47Z → 10:45:17Z` = **5.0583 h**, GPU string
  `NVIDIA L4` as recorded by `torch.cuda.get_device_name(0)` in every `worker.json`.

One AFTER reading turns those into the first `evidence_tier = MEASURED` GPU row
`colab_rates.csv` has been waiting for: `cu_per_hour = (199.33 − after) / 5.0583`. Nothing was
written to that file's data rows here, for the reason canary 1 gives — `cost_report.py` takes
the first matching pattern, so an inert `NVIDIA L4` row would shadow the real one.

**Three launch spans now sit on this GPU** (0.2939 h canary 2, 0.4769 h canary 1, 5.0583 h
here), so a single before/after pair converts all three at once.

---

## 3. What came back

| | measured |
|---|--:|
| shards planned / cut / uploaded / verified / decoded / ingested | **36 / 36 / 36 / 36 / 36 / 36** |
| crops | **7,164** — the census exactly, no crop lost or duplicated |
| **ok** (written to the LaTeX corpus) | **6,841** (95.49%) |
| **failed** | **0** |
| **unstable** (the decode did not reproduce) | **132** (1.84%) |
| **degenerate** (a repetition loop) | **191** (2.67%) |
| rows on the verification queue | **323** = unstable + degenerate, exactly |
| slice errors, across 216 child processes | **0** |
| restarts | **0** |
| shard archives on the wire | **66.34 MB** (69,558,980 B), 36 files |

`latex ∪ verify_queue` = 7,164 with an **empty intersection** — every crop is in exactly one
of the two, which is the property the three-destination ingest exists to hold.

### 3.1 Rate and wall clock

| | |
|---|--:|
| sum of the 36 parents' own wall clock | **15,891.8 s** (4.414 h) |
| **aggregate regions/s** over that | **0.4508** |
| the worker's own queue wall (first parent to step log) | **17,940 s** (4.983 h) |
| end-to-end regions/s over the queue wall | 0.3993 |
| per-shard parent wall | min 285.5 s · mean 441.4 s · max 655.0 s |
| between shards (queue wall − Σ parent wall) ÷ 36 | **57 s** per shard — read the shard, build the images, plan, merge, write the archive |
| model load, per child (the §11.6 fix working) | mean **10.8 s**, max 19.0 s — it read `0.0` for every slice in canary 2 |

**§11.7 projected 5.54 h of worker time with the guard on. It came in at 4.98 h**, 10% under.
The projection is therefore confirmed in direction and slightly conservative in size — but see
§6: two things changed at once between canary 2 and this run, and the projection's inputs only
covered one of them.

### 3.2 VRAM — the assumed constant, now measured over 36 shards

`plan_procs` chose **N = 6 on every shard, bound by the memory term** (`{"vram": 6, "cpu": 11,
"batches": 40}`; `full35` reports `batches: 33`, its 164 crops being 33 batches, and `vram`
still bound). The CPU term never came close: Colab's L4 image reports 12 vCPU, so per-process
threads came out at `(12−1)//6 = 1`.

| | |
|---|--:|
| per-process allocator peak, worst across 216 slices | **2.835 GB** |
| device-wide minimum free, worst across the run | **5.301 GB of 23.659 GB** |
| → device-wide peak footprint for six processes | **18.36 GB = 3.06 GB per process** |

**The 3.10 GB constant `plan_procs` assumes is now a measurement, and it was very nearly
exact.** Canary 2's single shard measured 2.705 GB/process and this report's §4.3 predecessor
called the 3.10 conservative by ~15%; over 36 shards and a far wider crop mix the true figure
is **3.06 GB**, 1.3% below the assumption. At the measured value the memory term is
`floor(0.80 × 23.659 / 3.06) = floor(6.19) = 6` — **the same N, with 0.19 of a process in
hand.** The headroom fraction of 0.80 is what kept that margin; at 0.85 the same numbers would
have chosen 6 with essentially none.

---

## 4. The two guards at corpus scale

### 4.1 They fired, and on rows both canaries called `ok`

**323 rows — 4.51% of the corpus — were kept out of the LaTeX corpus and routed to
`latex_formula_colab_full_verify_queue.jsonl`**, carrying both candidate strings (for
`unstable`), the repetition signature (for `degenerate`), and the same
`(file_sha256, page, bbox_canonical)` join key every corpus row carries, so a verified row
patches back like any other.

**The spot-check the brief asked for, done against the RESULT ARCHIVES rather than the parked
files** — i.e. against the worker's own rows, not against the thing under test:

```
non-ok rows in the 36 archives:   323   {unstable: 132, degenerate: 191}
NON-OK LEAKED INTO THE CORPUS:      0
NON-OK MISSING FROM THE QUEUE:      0
QUEUE ROWS THAT ARE NOT NON-OK:     0
latex (6,841) + verify (323) = 7,164, intersection 0
```

Twenty rows drawn seeded (`random.Random(20260916)`) from the 323 were then read one by one:
all twenty `in_corpus=False, in_queue=True`; every `unstable` row carried **both** `latex` and
`latex_redecode`; every `degenerate` row carried its loop signature (`' \\,'`, `' c'`,
`'cdot'`, `' { }'`, `' &'`, `' a n'` … each repeated past the detector's threshold); all
twenty carried `bbox_canonical` and `file_sha256`.

### 4.2 The price, and it is the predicted one

| | |
|---|--:|
| total slice-seconds (216 child processes) | 32,918.7 s |
| of which re-decode | **5,912.8 s = 18.0%** |
| → **guard multiplier on decode time** | **×1.219** |
| rows re-decoded (5% sample ∪ rows ≥ 1,000 chars, minus rows already ruled degenerate) | **492 = 6.9% of the corpus** |
| of those, disagreed | 132 = **26.8% of what was re-decoded** |

**×1.219 measured against the ×1.269 canary 2 projected**, on a corpus 36× the size of the
shard the projection was fitted on. The set arithmetic behind §11.7 — 9.0% of rows triggered,
26.9% of the decode — comes out here at **6.9% of rows and 18.0% of slice time**: the same
shape, both terms slightly smaller, which is what a corpus with proportionally fewer runaways
than the canary shard looks like.

**More than a quarter of everything re-decoded disagreed with itself.** That is the number
worth carrying out of this run: on the rows the guard chose to look at, instability is not
rare.

### 4.3 The degeneracy guard ran on ONE of its two tests, and that is a measured shortfall

**`tokenizer_reached` is `false` on every one of the 216 slices.** The engine's tokenizer was
not reachable through `_tokenizer_of(model)` on this VM, so the `max_new_tokens` half of guard
2 — the token count, which canary 2 §11.3 calls the ground truth — **never ran**. Every one of
the 191 degenerate rows was caught by the tokenizer-free repeated-tail test alone.

That fallback's cost is not a guess: canary 2 measured it directly, catching **12 of 13** and
**9 of 10** capped generations, the misses being loops whose period exceeds the detector's
60-character window. So **191 is a lower bound, and the true count is plausibly ~5–10% higher**
— roughly 10–20 more rows still sitting in the 6,841 as `ok`. The exact shortfall for this
corpus is **UNMEASURED**: nothing here re-tokenised the 6,841, and doing so needs the
checkpoint's tokenizer, not a GPU.

**Why it was unreachable is also UNMEASURED.** Canary 2 reached for `engine.vlm_model` and
found no such attribute; this run records only the boolean. It is a cheap, GPU-free fix to
chase — the accessor, not the model — and it is the single highest-value follow-up in this
report, because it is the half of the guard that sees a loop *both* runs would agree on.

For scale: the degenerate rate here is **2.67%** against canary 1's 6.5% and canary 2's 5.0%.
Those two figures are from one 200-crop shard drawn seeded across 136 files; the corpus is
sharded contiguously and is a different population, so the gap is **not** evidence the guard
weakened — it is two different crop mixes plus the tail-only shortfall above, and this run does
not separate them.

---

## 5. The 36 shards

`ratio` is the slowest slice ÷ the fastest within that shard. `dominant file share` is the
fraction of the shard's 200 crops that come from its single largest file — shards are chunked
by CROP over a `(file, page, crop_id)` ordering, so a paper with thousands of equations fills
whole shards on its own.

| shard | crops | MB | ok | unstable | degen | parent s | reg/s | slice min–max s | ratio | dominant file |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| full00 | 200 | 1.47 | 190 | 0 | 10 | 481.9 | 0.4150 | 125–210 | 1.68 | 100% |
| full01 | 200 | 1.48 | 193 | 1 | 6 | 455.7 | 0.4389 | 59–203 | 3.43 | 60% |
| full02 | 200 | 1.55 | 196 | 2 | 2 | 369.1 | 0.5418 | 46–192 | 4.14 | 58% |
| full03 | 200 | 1.69 | 192 | 3 | 5 | 535.5 | 0.3735 | 56–313 | 5.58 | 52% |
| full04 | 200 | 1.87 | 191 | 2 | 7 | 442.6 | 0.4519 | 55–365 | **6.61** | 32% |
| full05 | 200 | 1.96 | 192 | 4 | 4 | 301.0 | 0.6644 | 94–185 | 1.98 | 36% |
| full06 | 200 | 1.57 | **200** | 0 | 0 | 343.9 | 0.5815 | 43–119 | 2.75 | 100% |
| full07 | 200 | 2.17 | 198 | 2 | 0 | 360.6 | 0.5547 | 61–179 | 2.93 | 69% |
| full08 | 200 | 1.52 | 184 | 1 | 15 | 414.4 | 0.4826 | 150–277 | 1.85 | 50% |
| full09 | 200 | 1.15 | **200** | 0 | 0 | 285.5 | **0.7006** | 30–45 | **1.53** | 66% |
| full10 | 200 | 1.51 | 195 | 1 | 4 | 354.3 | 0.5646 | 46–190 | 4.10 | 46% |
| full11 | 200 | 2.39 | 186 | 8 | 6 | 405.3 | 0.4935 | 76–311 | 4.11 | 21% |
| full12 | 200 | 1.56 | 190 | 4 | 6 | 536.4 | 0.3729 | 73–294 | 4.03 | 27% |
| full13 | 200 | 1.39 | 189 | 3 | 8 | 459.8 | 0.4350 | 50–212 | 4.24 | 32% |
| full14 | 200 | 2.21 | 190 | 7 | 3 | 391.9 | 0.5104 | 73–207 | 2.84 | 24% |
| full15 | 200 | 1.76 | 189 | 2 | 9 | 418.7 | 0.4777 | 65–254 | 3.88 | 40% |
| full16 | 200 | 2.65 | 187 | 8 | 5 | 480.7 | 0.4161 | 171–314 | 1.83 | 66% |
| full17 | 200 | 1.84 | 191 | 2 | 7 | 502.6 | 0.3980 | 128–284 | 2.21 | 40% |
| full18 | 200 | 1.51 | 195 | 4 | 1 | 417.5 | 0.4790 | 44–157 | 3.54 | 28% |
| full19 | 200 | 1.64 | 191 | 3 | 6 | 599.1 | 0.3338 | 61–312 | 5.07 | 62% |
| full20 | 200 | 1.59 | 194 | 1 | 5 | 351.5 | 0.5690 | 64–199 | 3.10 | 100% |
| full21 | 200 | 1.84 | 197 | 1 | 2 | 426.3 | 0.4692 | 43–236 | 5.48 | 100% |
| full22 | 200 | 2.11 | 192 | 4 | 4 | 497.8 | 0.4018 | 71–260 | 3.68 | 100% |
| full23 | 200 | 2.49 | 183 | 9 | 8 | 414.0 | 0.4831 | 170–290 | 1.70 | 100% |
| full24 | 200 | 2.53 | 186 | 9 | 5 | 538.1 | 0.3717 | 73–383 | 5.22 | 100% |
| full25 | 200 | 2.27 | 188 | 4 | 8 | **655.0** | **0.3053** | 79–343 | 4.37 | 100% |
| full26 | 200 | 2.10 | 189 | 8 | 3 | 417.7 | 0.4788 | 74–282 | 3.83 | 100% |
| full27 | 200 | 1.82 | 193 | 3 | 4 | 438.9 | 0.4557 | 60–232 | 3.87 | 100% |
| full28 | 200 | 1.88 | 189 | 6 | 5 | 355.8 | 0.5621 | 55–231 | 4.17 | 100% |
| full29 | 200 | 2.23 | 189 | 8 | 3 | 468.8 | 0.4266 | 77–336 | 4.36 | 100% |
| full30 | 200 | 2.35 | 191 | 5 | 4 | 372.7 | 0.5366 | 65–251 | 3.87 | 100% |
| full31 | 200 | 1.56 | 193 | 0 | 7 | 396.4 | 0.5045 | 66–211 | 3.21 | 100% |
| full32 | 200 | 1.52 | 192 | 2 | 6 | 428.4 | 0.4668 | 54–260 | 4.80 | 64% |
| full33 | 200 | 1.57 | 186 | 7 | 7 | 434.2 | 0.4607 | 65–262 | 4.02 | 59% |
| full34 | 200 | 1.31 | 191 | 3 | 6 | 596.2 | 0.3355 | 53–210 | 3.94 | 52% |
| full35 | 164 | 2.29 | 149 | 5 | 10 | 543.4 | **0.3018** | 144–313 | 2.17 | 29% |

Two shards came back **200/200 `ok`** with nothing held back at all (`full06`, `full09`), and
`full09` is also the fastest at 0.7006 regions/s — a shard of short inline fragments. The
slowest, `full25` at 0.3053, is 2.3× slower on the same hardware with the same N. **Per-shard
rate spans 2.3×, and it is a property of the equations, not of the runtime.**

---

## 6. The finding: the planner did not reproduce its simulation

Canary 2 §11.5 replaced the slice planner on the strength of a **simulation over its own
measured batch seconds**: cost-ordered batches dealt round-robin instead of
longest-processing-time, with a proxy rebuilt from ink pixels. The simulated slowest/fastest
ratio was **1.63×**, against **3.71×** for the planner canary 2 actually ran, and the section
says in its own words that no run had used it.

One has now. **It did not land anywhere near 1.63×.**

| | slowest ÷ fastest slice |
|---|--:|
| canary 2, MEASURED, old proxy + LPT, one shard | 2.85× |
| §11.5 simulation of old proxy + LPT | 3.71× |
| §11.5 simulation of **new proxy + DEAL — what shipped** | **1.63×** |
| **this run, MEASURED, new proxy + DEAL, 36 shards** | **mean 3.61× · median 3.87× · range 1.53–6.61×** |
| the same, with re-decode time subtracted from every slice | **mean 3.21× · median 3.33×** |

The guard is part of the story but only a small part: removing every re-decode second moves the
mean from 3.61 to **3.21**, and in **19 of 36 shards the slowest slice was also the one that
did the most re-decoding** — the long rows both trigger the guard and take longest to decode,
so the guard lands on the slice that is already behind. Subtract it entirely and the planner
still delivers 3.21× on average, **twice its simulated figure**.

**The comparison to canary 2's 2.85× is a mean against a single sample, and is stated that
way.** That figure is one shard; this is 36, and **9 of the 36 came in below it** (as low as
1.53×) while the worst reached 6.61×. The defensible claim is the first one — the simulation
predicted 1.63× and the corpus measured 3.21× — not a ranking of the two planners, which this
run does not have the design to support.

**What this run cannot separate, said plainly.** Three things differ between canary 2's 2.85×
and this run's 3.21×, and the run varies all of them at once:

1. **the planner** (new proxy + DEAL against old proxy + LPT) — the thing under test;
2. **the crop population.** Canary 2's shard was 200 crops drawn seeded round-robin across 136
   files; these shards are contiguous runs over a `(file, page, crop_id)` ordering, and 14 of
   the 36 are a single paper end to end. A shard of one author's display equations has a
   different length distribution from a spread draw, and the proxy is fitted on the spread one.
3. **the guard**, quantified above and worth ~0.4 of the ratio.

So the honest verdict is not "DEAL is worse than LPT". It is: **the 1.63× was a number the
design produced about itself, on one shard's timings, and it did not transfer to the corpus.**
CLAUDE.md §3.4c is the rule that anticipated exactly this, and the reason it survived to be
measured is that §11.5 labelled itself a simulation rather than a result.

**The throughput comparison inherits the same confound.** Canary 2 measured 0.4555 regions/s
with no guard; this run measured **0.4508 regions/s with the guard doing 21.9% more decode
work**. Read one way the planner bought back the guard's cost exactly; read another the corpus
is simply easier than the canary shard. **Two changes moved together and this run does not
separate them** — an A/B would be one shard decoded twice with `ASSIGN_MODE` flipped, which is
about 15 minutes of L4 and has not been spent.

A cheaper diagnosis exists and costs no GPU at all: every slice's realised seconds are in the
36 `worker.json` records, and `crop_cost` is a pure function of the PNG bytes. Re-fitting the
proxy against 7,164 measured outcomes instead of 200 is a laptop job, and it would say whether
the ranking or the assignment is what failed. It is not done here.

---

## 7. What ran clean, and is worth recording as such

* **No restart, no stall, no intervention.** The worker took all 36 shards in queue order, one
  after another, for 5 hours. Every poll of progress was server-side (`rclone lsf` through the
  service account) so **no `colab exec` was spent on watching**: the session handle carried the
  launch, two execs after it — the start payload and one writer-side probe — and the stop, and
  was still alive five hours later when the stop was issued.
* **The mid-run audit needed no VM at all.** At 06:47, with 7 shards done, `full00`'s
  `worker.json` was pulled off the lake and read: `procs 6, bound_by ["vram"]`, slice spread
  125–210 s, 10 degenerate. That is the whole design verified against real returned bytes while
  the run continued — no exec, no risk to the handle.
* **The drain gate read a real backlog.** `stop` printed `DRAINED (dirty 0.0 GB)`, and the
  server-side listing already held all 36 archives and all 36 sidecars before the stop was
  issued.
* **`model_load_seconds` reports a real number now** (mean 10.8 s), closing the canary 2 §4.2
  measurement defect where every slice reported `0.0`.

### One correction made during the run

The first writer-side probe took **120 seconds inside the VM** and skewed its own arithmetic —
it computed the beat age at the top and printed the timestamp at the bottom, two minutes apart,
so the two disagreed by exactly that gap. The cause was `tail` on the worker's nohup log
*through the rclone mount*: the file is open and appending, `--vfs-cache-mode writes` uploads
on close, so Drive has nothing to serve and the read blocks on a fetch that cannot succeed.
**A litkb worker's nohup log is not readable from Drive until the worker exits** — which is
also why every progress signal in this run is `rclone lsf` over the result directory instead.
The probe was rewritten to touch no mounted path and answers only from `/proc`, `/content` and
`nvidia-smi`.

---

## 8. Where the results are

Parked as JSONL for P5's ingest, which joins to blocks on
`(file sha256, page, bbox_canonical)`. **Nothing here wrote to any `litkb*` database and none
was touched.**

| | |
|---|---|
| **LaTeX corpus, 6,841 rows** | `D:\edmonds-pipeline\litkb_derived\formula\latex_formula_colab_full.jsonl` |
| **verification queue, 323 rows** | `…\latex_formula_colab_full_verify_queue.jsonl` |
| **metrics, one row per shard** | `…\metrics_formula_colab_full.jsonl` |
| per-shard ingest summary | `…\results_full\_ingest_summary.json` |
| verified result archives (local copies) | `…\results_full\result_shard_full{00..35}.zip` + `.sha256` |
| the shards, their manifests and hashes | `…\shards_full\shard_full{00..35}.zip`, index `_shard_index.json` |
| on the lake | `phase4/litkb/formula/shards/` and `phase4/litkb/formula/results_full/` |
| the worker's step log (CLAUDE.md §3.11) | `phase4/logs/litkb_formula_colab_worker_formula_2026-09-16T10-44.log` + `litkb_formula_colab_20260916T104439Z.json` |
| the worker's nohup log | `phase4/logs/litkb_formula_nohup_20260916T054452Z.log` |

The step log's own totals — 36 shards, 7,164 crops, 6,841 ok, 0 failed, 132 unstable, 191
degenerate — are the worker's independent count and **agree with the ingest exactly**. They
were produced on the VM before the archives were pulled, so the agreement is a join between two
sides of the wire, not a restatement.

---

## 9. What is still UNCONFIRMED

1. **The compute-unit delta** (§2). BEFORE and the span are recorded; the AFTER is Kam's.
2. **Why the engine's tokenizer was unreachable** (§4.3), and how many capped loops the
   tail-only fallback therefore missed. Both are laptop questions, not GPU ones.
3. **Whether the new planner or the shard composition caused §6.** The A/B is one shard decoded
   twice with `ASSIGN_MODE` flipped, ~15 min of L4.
4. **Which candidate is right for each of the 132 `unstable` rows.** Nothing here scores them;
   that is what the verification queue is for, and canary 1 §7.4 still stands — the long
   regions have no reference of any kind.
5. **Whether lowering `max_new_tokens` or adding a repetition stopping criterion is right.** It
   would end the waste at source — a 2048-token loop is ~28 s of L4 returning nothing, and
   there were at least 191 of them — but it changes every output against all three runs, so it
   stays Kam's decision.
6. **The 200 canary crops are inside this corpus** and were decoded here a third time, under a
   third batching. Comparing the three is free and is not done in this report.

---

## 10. Hygiene

* `LITKB_PGPORT=1 PYTHONUTF8=1 py -3.12 qc/check.py --fast`, run from this worktree after the
  final edit and before the push. Stated in those words: **the litkb Postgres guards were NOT
  exercised** (216 skipped, no server on this machine). The verdict quoted rather than
  summarised:

  ```
  litkb Postgres tests: 216 skipped  <- 216 SKIPPED: litkb server/role/psycopg absent,
                                        so those guards were NOT tested
  FAILED qc\test_experiments.py::test_pointer_paths_resolve[crown_state_model]
  1 failed, 2298 passed, 224 skipped, 74 warnings in 2066.23s (0:34:26)
  check: FAILED at rung 'pytest' — fix, then rerun.
  ```

  **The ladder's verdict is FAILED, not PASSED.** The single failure is `crown_state_model`,
  the expected one this branch's base commit and both canary reports already carry; nothing in
  this change touches experiments. The `secrets`, `ruff` and `compile` rungs passed; because
  the ladder stops at the first failing rung **preflight did not run**, and `--fast` skips the
  smoke by definition. The change is a queue file, one constant in the launch payload and one
  test — no engine code — which is why the smoke was not run separately and is said here rather
  than left implied.
* `qc/test_litkb_formula_colab.py` + `qc/test_litkb_formula_shards.py` alone: **56 passed**.
  `ruff check --select F` over the two touched Python files: **All checks passed!**
* **The 7 h cap was operator-enforced**, not built into the worker. `vm_ops exec --timeout`
  bounds how long the CLI waits for the *start* payload (which nohup-detaches in ~50 s) and
  would have held the single-CLI-call lock for the whole timeout had it hung, so it stayed at
  the proven 900 s. The backstops on the runtime itself were the self-stop watchdog (10 idle
  minutes after the last beat, then a real upload drain, then `runtime.unassign()`) and this
  session's foreground poll. The run finished at 5.06 h and neither backstop was needed.
* **One queue, one runtime** (CLAUDE.md §3.4). One L4 for the whole pass; `vm_ops sessions`
  read `0 active runtime(s)` both before the launch and after the stop.
* No `litkb*` database was touched and `LITKB_PGPORT=1` was set for every local run. No other
  worktree was touched, `main` did not move, and no secret was printed. `D:\edmonds-pipeline\Literture`
  was not read at all — this run consumed only crops cut on 2026-09-15.
* The analysis scripts behind §3–§6 (the shard cutter, the server-side upload verifier, the
  server-side poller, the writer-side probe and the ingest driver) live in this session's
  scratchpad; per CLAUDE.md §3.4b they are the evidence behind those sections and each is named
  where its numbers appear.
