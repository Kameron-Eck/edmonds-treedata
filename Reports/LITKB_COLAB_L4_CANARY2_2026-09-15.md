# Canary 2 — N decode processes on one L4, and the token-stability finding it returned

**Date:** 2026-09-15 · **Worktree:** `D:\edmonds-pipeline\treedata-colab`, branch
`work/20260915-colab-l4-formula`, launched at **`29768fd`** (the VM's own `BOOTSTRAP_READY`
line reports that commit, so this is read, not asserted)
**Design this executes:** `Reports/LITKB_COLAB_L4_FORMULA_2026-09-15.md` §9
**Baseline:** `Reports/LITKB_COLAB_L4_CANARY_2026-09-15.md` (canary 1, sequential)
**Contract:** CLAUDE.md §3.4 (one queue per runtime; stopping is autonomous), §3.9, §3.11,
§3.4b, §3.4c

The run did what it was built to do — **200/200 and 5/5 crops decoded, 0 failed**, N chosen on
the VM from a measured card, both archives verified server-side before the stop, the watchdog's
liveness beat observed advancing three times during the run, and the runtime stopped at
**17 min 38 s**.

It also returned a finding the design did not expect and which is more important than the rate:
**14 of the 200 crops decoded to different LaTeX than canary 1 did**, and the differences are
concentrated in the long regions — up to a 5,157 → 710 character collapse. The five referee
equations are still byte-identical on every device. §5 is that finding; read it before using any
canary-1 LaTeX as a reference.

---

## 1. Timeline (UTC, 2026-09-15)

| when | what |
|---|---|
| 18:56 | both shards confirmed on the lake by **server-side md5 through the service account** — `shard_canary200.zip` `1a07553aed6782c05c37cc04a74d8426`, `shard_ref5.zip` `3131154f666df312ab8cc76500e5d166`, both matching canary 1. **Nothing was uploaded for this run.** `results_procs/` confirmed absent, so kill 4 (skip a shard whose result is already present) could not swallow the run |
| 18:58:14 | `vm_ops launch --session litkbf2 --gpu L4 --branch work/20260915-colab-l4-formula` issued |
| 18:59:56 | **VM READY** — all five bootstrap signatures, incl. `WRITE_CANARY PASS` and `BOOTSTRAP_READY 29768fd`. **1 min 42 s**, against 2.5 min in canary 1 |
| 19:00:10 | `vm_ops exec --file pipeline/litkb_formula_vm_start.py --timeout 900` issued |
| 19:00:54 | the parent worker's **first liveness beat** (read off the VM at 19:02:07) |
| 19:01:00 | exec returned — **50 s** for pip install + version gate + nohup detach, against 49 s in canary 1. `LITKB_TORCH_BEFORE` == `LITKB_TORCH_AFTER` == `2.11.0+cu128 True`; docling 2.127.0 / docling-core 2.96.0 / ibm-models 4.0.2 / transformers 5.17.0 — identical to canary 1 |
| 19:02:07 | **writer side probed on the VM, 1 min 7 s after the exec returned** — parent worker alive (pid 4526), beat file written, GPU idle (the shard read and the cost-proxy pass over 200 PNGs precede any decode) |
| 19:03:48 | second probe: **six children spawned**, `--slice-of 6`, `--threads 1` each, 898 MiB apiece on the card during model load |
| 19:04:28 | fourth probe: **beat advanced to 19:02:39** (the second and third probes lost their beat line to `vm_ops exec`'s head truncation — §10) |
| ~19:11 | `result_shard_canary200.zip` + `.sha256` visible server-side |
| 19:12:52 | the **last beat** (read at 19:15:31, after the worker had exited) |
| 19:13:48 | worker's step log written; `result_shard_ref5.zip` + `.sha256` on the lake at 19:14:07 |
| 19:15:31 – 19:15:48 | **both archives md5-verified server-side and pulled**, local md5 == server md5 for both (`e1aac8023374acf946e1f06dd6d37d84`, `bd6d06b2c6c133a2ca19e6976110fa06`) — done **before** the stop was issued |
| 19:15:48 | `vm_ops stop --session litkbf2` — printed **`drain check litkbf2: DRAINED (dirty 0.0 GB)`**. Canary 1's stop printed `NO_HEARTBEAT (dirty None GB)`; the gate that could not read a backlog then, read one now |
| 19:15:52 | `litkbf2: stopped`, and `vm_ops sessions`: **`0 active runtime(s) on the account`** |

**Launch span 18:58:14 → 19:15:52 = 17 min 38 s (0.2939 h)** for 205 crops, against canary 1's
28 min 37 s for the same 205. That span, not the worker's seconds, is what Colab bills.

**The operator-visibility gap §9.1 left open is confirmed as still open.** `vm_ops status`
during the run read `session litkbf2: beat … gpu NVIDIA L4 util 0% queue_step None dirty 0.0 GB`
— `queue_step None`, exactly as predicted and exactly as in canary 1, because `vm_heartbeat`
still derives its queue fields from `phase4_train_queue`. The `util 0%` in that line is a single
instantaneous sample, not the run's utilisation; three independent `nvidia-smi` probes also read
0% while six processes were loading models, which is what a model load looks like.

---

## 2. Cost is UNMEASURED, and it is the same reason as canary 1

The CU delta for this launch is **UNMEASURED**. `colab_rates.csv`'s procedure needs a verbatim
balance reading immediately before and after the launch; this session's permission layer refuses
to navigate a browser to Colab (`Browser Navigate Exfil`), the brief instructed that the page not
be attempted, and Kam is in the field. **No reading was taken and none appeared in the
conversation.** Nothing was written to `colab_rates.csv`'s data rows, for the reason canary 1
gives: `cost_report.py` takes the first matching pattern, so an inert `NVIDIA L4` row would
shadow the real one when it is finally measured.

What this run adds to the cost question is a second **known launch span attached to a known
GPU** — 0.2939 h on an `NVIDIA L4` — so the moment any L4 before/after pair is read, both
canaries convert to cost at once. The pre-approved ~200 CU was a ceiling on the spend, not a
measurement of it.

---

## 3. N, and what chose it

`plan_procs` ran on the VM and returned, verbatim from the merged `worker.json`:

```json
{"procs": 6, "bound_by": ["vram"],
 "limits": {"vram": 6, "cpu": 11, "batches": 40},
 "per_proc_bytes": 3100000000, "vram_safety_fraction": 0.8}
```

**N = 6, bound by the memory term.** The CPU term was the UNMEASURED one in §9.2, and it is now
measured: **Colab's L4 image reports `os.cpu_count() == 12`**, read directly off the VM, so the
CPU term was 11 and never came close to binding. §9.2's worry — that a 4-vCPU image would bind N
at 3 — does not apply to this image. Per-process threads came out at `(12-1)//6 = 1`.

**The ref5 shard chose N = 1, bound by `batches`**, because five crops are one batch. That is the
`n_batches` term in the formula doing exactly what it is for, and it is the only live evidence in
this run that any term other than `vram` can bind.

---

## 4. The rate, the imbalance, and the VRAM the design had to assume

### 4.1 Aggregate

| | canary 1 (sequential) | canary 2 (N=6) |
|---|--:|--:|
| crops | 200 | 200 |
| ok / failed | 200 / 0 | **200 / 0** |
| wall seconds (the worker's own `seconds`) | 1157.929 | **439.115** |
| **regions/s** | 0.1727 | **0.4555** |
| launch span | 28 m 37 s | **17 m 38 s** |

**Measured scaling factor: 0.4555 / 0.1727 = 2.638×** on N = 6 — **44% of linear**. The design
said "treat 193 s as a floor on the decode"; the floor held, and the real number is 439 s, 2.3×
above it. Nothing here is a surprise in direction, only in size, and §4.2 says where most of it
went.

The two `seconds` figures are not measured at quite the same seam and the comparison is slightly
generous to canary 2 in one respect and harsh in another: canary 1's 1157.9 s **excludes** its
20.1 s model load, while canary 2's 439.1 s is the parent's wall clock and **includes** the child
spawn, all six model loads, the merge and the archive write. Correcting for that would move the
factor up, not down, so 2.638× is reported as the conservative figure.

### 4.2 Per-process — and the imbalance is most of the missing speed

| slice | crops | seconds | regions/s | peak alloc GB | peak reserved GB |
|--:|--:|--:|--:|--:|--:|
| 0 | 30 | 185.09 | 0.1621 | 1.734 | 2.865 |
| 1 | 35 | 110.46 | **0.3169** | 2.201 | 3.399 |
| 2 | 35 | 205.25 | 0.1705 | 1.932 | 2.582 |
| 3 | 35 | 311.82 | 0.1122 | 1.825 | 2.491 |
| 4 | 30 | 208.36 | 0.1440 | 1.720 | 2.022 |
| 5 | 35 | **315.03** | 0.1111 | 2.022 | 2.487 |

**The slowest slice took 2.85× the fastest**, and the shard cannot finish before its slowest
slice does. Perfect balance at the *same* per-process rates would have finished the decode in the
mean, ~223 s, not 315 s — so roughly **92 s of the 439 s is imbalance alone**.

**The other 122 s is startup, and it is measured, not inferred.** The parent's `started_at` is
19:02:37 and **all six children's are 19:04:39** — a flat 122 s before a single crop is decoded,
after which 315.03 s of slowest slice and ~2 s of merge and archive write close the 439.115 s
almost exactly. The ref5 shard shows the same cost with the decode taken out from under it: one
child, five crops, a parent-to-child gap of **59 s** (19:10:51 → 19:11:50), **5.772 s of decode**,
and a parent wall of **120.189 s**. Five crops cannot be planning, so a large fixed cost sits on
both sides of a child — roughly a minute before it starts decoding, and, on ref5, a further ~55 s
after it stops that the canary200 run does not show. **What that cost is made of is UNMEASURED**
(§9.9): interpreter start, torch and docling imports, weight load, CUDA context teardown and
archive writes to the FUSE mount are all candidates, and nothing here separates them.

What IS measured is the total and that it is **paid per shard, not per crop**: 122 s on a 200-crop
shard is **28% of the wall**, and it is the strongest argument in this report for shards longer
than 200.

**`model_load_seconds` is a measurement defect, and it reads `0.0` for every slice.** The child
path calls `build_model` itself and then hands the already-built model to `process_shard` as
`_model=` **without** the matching `load_seconds=` the sequential path passes, so `process_shard`
times a load that has already happened and records zero. Canary 1, which took the sequential
path, measured 20.096 s. **The 122 s and 59 s figures above therefore come from the `started_at`
deltas, not from that field**, and the split between interpreter/import and weight load is
UNMEASURED — the slice logs carry the weight-loading progress bar but no timestamps. The fix is
one keyword argument; it is not made here because this session changed no source file.

**The cost proxy is what failed here, and §9.2 said in advance that it is uncalibrated.** Crop
width × ink density is a property of the PNG; §5 is about to show that decode time is driven by
the number of tokens the model *emits*, which the proxy cannot see. Slice 1 got 35 crops and
finished in 110 s; slice 5 got 35 crops and took 315 s. The longest-processing-time assignment
was fed costs that do not rank the work. **This is a measurement of the proxy, not of `--procs`**
— the split mechanism did what it claims, and a better ranking is a cheap, separate change.

Per-process rates are also all **at or below** canary 1's 0.1727 except slice 1's 0.3169. Six
processes sharing one L4's SMs do contend; the aggregate still wins because one process left the
card 65% idle.

### 4.3 VRAM — the assumed constant, replaced by a measurement

`plan_procs` used **3.10 GB per process**, read off canary 1's single end-of-run
`device_free_bytes` sample, and §9.2 flagged it as "neither an upper nor a lower bound". Canary 2
sampled `mem_get_info` **every batch**, so it returns a real one:

* minimum free across all six slices' per-batch samples: **7.430 GB of 23.659 GB**
* → **device-wide peak footprint 16.23 GB for all six processes = 2.705 GB per process**
* per-process allocator peaks: 1.720 – 2.201 GB (reserved 2.022 – 3.399 GB)

**The 3.10 GB assumption was conservative by ~15%, in the safe direction — and it did not change
the answer.** At the measured 2.705 GB the memory term is `floor(0.80 × 23.659 / 2.705) =
floor(6.996) = 6`: **the same N**, by the narrowest of margins. Substituting the measurement for
the assumption is therefore a free correction — it makes the constant a measurement without moving
a single decision — and it is **not made in this report**, because one card and one shard mix is
thin ground for a constant that sizes every future run, and because §4.2 has just shown this run is
bound by imbalance, not by parallelism.

---

## 5. The finding: 14 of 200 crops decoded differently, and it is the long ones

The free comparison §9.4 promised — canary 2 batches the same 200 crops differently, so a row-by-
row LaTeX join answers design UNCONFIRMED #3 — **did not settle in the expected direction.**

```
LaTeX canary200 vs canary 1: 186 identical, 14 differ, 0 only-in-c1, 0 only-in-c2
batch_index changed for 197/200 crops (the batchings really do differ)
```

The 14, sorted by canary 1's decoded length:

| c1 chars | c2 chars | Δ | file · page · self_ref | batch c1 → c2 |
|--:|--:|--:|---|---|
| 48 | 73 | +25 | Burnicki_2010 p19 `#/texts/239` | b14 → b28 |
| 180 | 203 | +23 | Eldar_2009 p16 `#/texts/139` | b2 → b15 |
| 202 | 194 | −8 | Foody_2010 p8 `#/texts/167` | b38 → b24 |
| 207 | 203 | −4 | Zhu_2008 p6 `#/texts/3` | b23 → b18 |
| 290 | 317 | +27 | Wehmann_2015 p4 `#/texts/72` | b39 → b6 |
| 306 | 374 | +68 | Duval_2009 p32 `#/texts/593` | b37 → b11 |
| 336 | 333 | −3 | Boykov_2003 p6 `#/texts/126` | b9 → b10 |
| 441 | 437 | −4 | Leung_2004b p5 `#/texts/20` | b36 → b8 |
| 563 | **5051** | **+4488** | Ratner_2017 p15 `#/texts/615` | b29 → b6 |
| 799 | 826 | +27 | Singer_1976 p15 `#/texts/2` | b5 → b8 |
| 2776 | 285 | **−2491** | Nordman_2004 p17 `#/texts/311` | b13 → b27 |
| 3768 | 1017 | **−2751** | Charitos_2008 p11 `#/texts/518` | b28 → b2 |
| 5157 | 710 | **−4447** | Xie_2013 p13 `#/texts/110` | b22 → b23 |
| 5486 | 1043 | **−4443** | journal.pone.0343729 p7 `#/texts/1` | b25 → b1 |

**Length predicts it.** The identical 186 have median 180 and p90 694 characters; the 14 have
median 388 and p90 3,768. **4 of the 18 crops whose canary-1 LaTeX is ≥ 1,000 characters differ
(22%), against 2 of the 102 under 200 characters (2%).** Eight of the fourteen differ by fewer
than 70 characters — a token or two at a boundary; the other six move by thousands.

**What the differences look like.** The biggest mover in absolute terms is Ratner_2017, and the
two strings share a long identical prefix and then diverge: canary 1 ran to 563 characters ending
mid-word (`\text {cause}`), canary 2 to 5,051. Canary 1's own §3 already recorded that this
checkpoint emits up to 5,486 characters and that decode time correlates 0.974 with the longest
string in the batch. Read together, the picture is a **generation-length effect**: on regions
where the model runs long, where it stops is not stable, and a stop is worth thousands of
characters.

**What this comparison can and cannot say, stated precisely.** It compares two runs that differ
in *two* ways at once — batch composition **and** being a different run — so it establishes that
**decoded LaTeX for long regions is not reproducible across runs**, and it does **not** separate
batch composition from ordinary run-to-run nondeterminism. Design UNCONFIRMED #3 asked
specifically about batch composition; this measurement **refutes the stability the question
presumed** without isolating its cause. Isolating it is one cheap experiment — re-decode the same
shard twice with the same batching — and it is not run here.

**What it does NOT undermine.** Both runs pass the ingest gate: no row claims `status="ok"` with
empty LaTeX in either, `ok` is 200/200 in both, and no crop failed. The instability is in *how
much* is emitted on long regions, not in whether a decode succeeds.

**Consequence for the corpus run, and it is the actionable part.** A per-crop LaTeX row is
**not** a content-addressed function of the crop bytes, which is what the shard design's
"decoding them again could only produce the same answer at GPU cost" (kill 4's rationale) assumes.
That assumption holds for the 93% of crops that are short and fails for the long tail. Any claim
that a re-decode is a no-op, and any downstream diff that treats a LaTeX change as a pipeline
regression, needs this section.

### 5.1 The five referee equations are unaffected

| page | self_ref | chars | c2 == c1 | c2 == CPU | c2 == T2000 |
|---|---|--:|---|---|---|
| 3 | `#/texts/5` | 127 | yes | yes | yes |
| 3 | `#/texts/7` | 74 | yes | yes | yes |
| 4 | `#/texts/13` | 196 | yes | yes | yes |
| 4 | `#/texts/14` | 104 | yes | yes | yes |
| 4 | `#/texts/21` | 258 | yes | yes | yes |

**5/5 byte-identical, four devices/configurations deep** (CPU, T2000, L4 sequential, L4 under the
process split). All five are ≤ 258 characters — squarely inside the length band §5 finds stable —
and ref5 is one batch of five in both canaries, so its batching did **not** change. It is
therefore evidence that the **process split** moves nothing, and no evidence at all about
batching or about long regions.

**A join note, because the first pass looked like a failure.** Keyed on `(page, self_ref)` the
CPU reference appears to match only 2/5: its page-4 entries are `#/texts/5` and `#/texts/6` where
the shard's are `#/texts/13` and `#/texts/14`. The CPU reference was produced by converting
**single pages**, so docling renumbers `self_ref` per document — the key is not portable across
that boundary. On `(page, LaTeX)` the multisets are identical for both references. This is the
same class of silent-joiner error canary 1 §5 recorded with the bbox-floor key, hit again with a
different key, and it is written down for the same reason.

---

## 6. The kills, live

**1. The watchdog's beat advanced during the run — kill 6, and it fired as designed.** Read off
the VM at `/content/litkb_worker_beat`, which is local to the runtime and gone at stop, so three
`vm_ops exec` probes were taken while it was alive (sequential, never concurrent, nothing killed):

| probe at | beat mtime | age |
|---|---|--:|
| 19:02:07 | **19:00:54** | 72 s |
| 19:04:28 | **19:02:39** | 109 s |
| 19:15:31 (after the worker exited) | **19:12:52** | 159 s |

(Probes at 19:03:48 and ~19:04:05 confirmed the six children and the card but are omitted from
this table: their beat line was cut by `vm_ops exec`'s head truncation — see §10.)

Three distinct, monotonically advancing timestamps. The first is the parent's beat **before the
model load**, which is the W3 ordering §9.1 argued for; the last is within a minute of the
worker's step log at 19:13:48, so the beat tracked the work to its end. The watchdog was never
called on to act — nothing hung — so this confirms **the evidence the watchdog reads is live and
advancing**, which is the half that could not be tested off a VM. That a stale beat causes a stop
remains established by the mutation campaign (W1), not by this run.

**2. No `ok` row carries empty LaTeX.** `formula_ingest`'s refusal (4) ran over both archives and
did not fire: 0 of 205 rows claim success with empty or whitespace LaTeX. As in canary 1, the
rule's *firing* rests on the referee's real CUDA OOM, not on this run.

**3. A process failure failing only its slice: NOT EXERCISED.** `slice_errors` is `{}` for both
shards; all six children exited 0 and all six slice archives carried a matching DONE marker. **No
failure was manufactured to make the path fire**, so the claim that a dead slice costs only its
own crops remains where §9.6's mutation campaign left it (M1, M2 FIRED against the real source),
and is **unconfirmed on a live VM**. The parent's re-verification of each child archive's DONE
marker *did* run six times and passed six times, which is the guard around that path rather than
the path itself.

**4. Bytes.** Both archives verified by **done marker + sha256 sidecar + server-side md5** before
a single row was believed, and the server-side verification was done **before** the stop. The
stop's own drain gate reported `DRAINED (dirty 0.0 GB)` — it worked this time, but the md5s, not
the gate, are what say nothing was lost.

---

## 7. The ingest, run for real

```
== canary200
   status ok · n_crops 200 · ok 200 · failed 0
   shard_manifest_sha256 9bebebf1e1342f7cf267012e1e9dc943b7a31371ad9258eb14593f4a6bb75468
   result_sha256         6f712121e33149d2996235283f877296b3a3521583b887e21bdc7d49c041a3f8
   latex_rows_written 200 · verified "done marker + sha256 + server-side md5"
== ref5
   status ok · n_crops 5 · ok 5 · failed 0
   shard_manifest_sha256 4f83ad83243f62b812f95edc8417f9ecc65bdcffe7a02762278ae65f6320f54f
   result_sha256         af9b0dccbe2f931eaa1ae5584a4747f55ac30dea0dc77f954012ba5847ee757c
   latex_rows_written 5 · verified "done marker + sha256 + server-side md5"
```

`shard_manifest_sha256` for canary200 is **the same hash canary 1 ingested**, which is the point
of the re-decode and also a trap: `ingest`'s `seen_shards` skip (kill 4) would refuse it as
already ingested. Canary 2 is therefore parked in **separate files** —
`litkb_derived/formula/{metrics_formula_colab_procs.jsonl, latex_formula_colab_procs.jsonl}` —
with `seen_shards` deliberately not passed, so canary 1's rows stay untouched as the comparison
baseline. **No `litkb*` database was touched.** Both archives carried exactly `results.jsonl`,
`worker.json`, `DONE`; no crop, page image or PDF crossed back.

Artefacts, outside the repo like every other litkb one:
`D:\edmonds-pipeline\litkb_derived\formula\results_procs\` — both result archives, their
`.sha256` sidecars, **all seven per-slice archives and their logs**, the worker's nohup log and
the step-log JSON.

---

## 8. What the corpus now costs

At the measured aggregate **0.4555 regions/s**, the corpus census's **7,164 crops** are
**15,728 s = 4.37 h**, against 11.5 h at canary 1's sequential rate. That rate is the parent's
wall clock, so it **already carries** the 122 s of per-shard startup §4.2 measures — but only at
this shard's length, 200 crops, which is also the length the 36-shard plan uses. On top of it sits
1 m 42 s launch-to-READY and 50 s of install, **once per runtime**.

Three qualifications, all load-bearing:

* **This is a floor that assumes the shard mix.** The 200 crops were drawn seeded round-robin
  across 136 files, so the length mix is the corpus's. But §4.2 shows the run is bound by the
  **slowest slice**, and the slice imbalance depends on how the cost proxy ranks a given shard's
  crops. A shard drawn from `Schneider_2008` — 2,653 crops, 37% of the corpus on its own — has
  not been measured at all.
* **Fixing the proxy is worth more than raising N.** Perfect balance at the measured per-process
  rates finishes this shard in ~223 s instead of 315 s; removing those 92 s takes the aggregate to
  ~0.577 regions/s and the corpus to **~3.45 h**, at zero extra VRAM and no extra process.
  Raising N is not an alternative: §4.3 shows the measured per-process footprint leaves the memory
  term at 6 anyway.
* **Longer shards are the other free win, and they are independent of the first.** The 122 s of
  startup is 28% of this shard's wall and is paid once per shard whatever the shard's length. At
  400 crops per shard it would be ~16%, at 800 ~9%. Doubling the shard halves the number of times
  the corpus pays it — 36 shards × 122 s is **73 minutes of pure startup** in the current plan.
  This is arithmetic on a measured constant, not a measured speedup; no long shard has been run.

---

## 9. What is still UNCONFIRMED

1. **The compute-unit cost of anything on a GPU.** §2. Two L4 launch spans now sit ready for the
   first balance reading.
2. **Whether batch composition specifically — as opposed to run-to-run nondeterminism — moves the
   decoded tokens.** §5 refutes reproducibility and does not attribute it. The separating
   experiment is one shard decoded twice with identical batching.
3. **Whether the long-region instability is bounded, or how.** Nothing here measures which of the
   two strings is *better*; the long regions have no reference of any kind (canary 1 §7.4 still
   stands), and producing one on CPU costs hours.
4. **A dead slice failing only its own crops, on a live VM.** §6.3.
5. **Kill 3's worker-side firing on real GPU data.** Nothing failed, again.
6. **A decode-only T2000 rate**, and therefore a clean L4-vs-T2000 factor.
7. **The heap-corruption crash** of the local crop-cutting stage — untouched by this run.
8. **How `--procs` behaves on a shard with a pathological length distribution**, e.g. one drawn
   from `Schneider_2008`. §8.
9. **What the 122 s of per-shard startup is made of.** §4.2 measures the total from the
   `started_at` deltas, and that is all it measures: interpreter start, imports, weight load,
   parent planning, CUDA teardown and FUSE archive writes are not separated. `model_load_seconds`
   would have carried the weight-load half and instead reads `0.0` on the slice path — a
   one-keyword defect (§4.2) — and the slice logs carry a progress bar but no timestamps. Nor is
   it clear why ref5's parent wall exceeds its child's start-plus-decode by ~55 s while
   canary200's exceeds its slowest slice by only ~2 s; that asymmetry is unexplained.

---

## 10. Hygiene

* **One runtime**, created and stopped inside one session; `vm_ops sessions` confirms
  `0 active runtime(s)`. **Six execs, strictly sequential, never concurrent, none killed
  mid-exec** — one worker start and five read-only probes.
* **An operator defect worth naming: `vm_ops exec` truncates the HEAD of a long exec's output.**
  Two probes returned starting mid-line, with the beat timestamp — the one line the probe exists
  for — already gone; the six children's cmdlines had filled the window. The probe was amended to
  print the beat **last as well as first**, and every beat figure in §6 comes from a call where it
  survived. Anything read back through `exec` that matters should be printed last until that is
  fixed.
* The probe payload
  (`scratchpad/beat_probe.py`) reads a file mtime, `ps` and `nvidia-smi`. It writes nothing,
  starts nothing and kills nothing. It exists because the beat file lives on the runtime and is
  destroyed at stop, so kill 6's evidence cannot be collected after the fact.
* **Nothing was uploaded to the lake for this run** — both shards were already there and were
  re-verified server-side before the launch. Both results were verified server-side **before** the
  stop.
* No `litkb*` database was touched. `D:\edmonds-pipeline\Literture` was read only — in fact not
  read at all by this run, which read only crops already inside a shard archive. No other worktree
  was touched, `main` did not move, no secret or service-account key was printed.
* **§3.11, the worker's log read from Drive, not pasted from a terminal** —
  `phase4/logs/litkb_formula_nohup_20260915T190014Z.log`, pulled to
  `results_procs/` alongside the step log `litkb_formula_colab_20260915T191348Z.json`.
* **No source file was changed by this session** — this report is the only thing it adds. The
  ladder was run anyway, `LITKB_PGPORT=1 py -3.12 qc/check.py --fast`, and its verdict is quoted
  rather than summarised. Stated in those words: **the litkb Postgres guards were NOT exercised**
  (216 skipped, no server on this machine).

  ```
  litkb Postgres tests: 216 skipped  <- 216 SKIPPED: litkb server/role/psycopg absent,
                                        so those guards were NOT tested
  FAILED qc\test_experiments.py::test_pointer_paths_resolve[crown_state_model]
  1 failed, 2282 passed, 225 skipped, 74 warnings in 507.39s (0:08:27)
  check: FAILED at rung 'pytest' — fix, then rerun.
  ```

  **The verdict is FAILED, not PASSED.** The single failure is `crown_state_model`, the same
  expected one this branch and its base carry; nothing in this session touches experiments.
  Because the ladder stops at the first failing rung, **preflight did not run**, and `--fast`
  skips the smoke by definition.
* Cost: **UNMEASURED**, §2.
