# litkb formula enrichment on a Colab L4 — worker, shards, ingest gate, and a canary

**Date:** 2026-09-15 · **Worktree:** `D:\edmonds-pipeline\treedata-colab`, branch
`work/20260915-colab-l4-formula` (from the Docling branch at `5b26768`)
**Contract:** CLAUDE.md §2.3, §3.4, §3.9, §3.10, §3.11, §3.4b, §3.4c
**Upstream:** `Reports/LITKB_DOCLING_A_REFEREE_2026-09-15.md` (the gate, the rates, the OOM)

**NOTHING WAS LAUNCHED.** No Colab runtime was created, no `colab` CLI call was made, no
compute unit was spent. The canary is prepared and its exact command is in §6; the first
launch of this queue is the orchestrator's to make, per CLAUDE.md 3.4.

---

## 1. What crosses the wire, and what does not

`decisions.yaml::litkb-p0-foundation` answers "do the PDFs go to Drive?" with **none**. So
the artifact that travels is a **shard**: a packed archive of 120-dpi PNG **crops of the
equation regions only**, plus a manifest. No PDF, no full page image, no page text. There is
no flag anywhere in this code that uploads a PDF, and
`test_a_shard_contains_only_crops_and_a_manifest` asserts the archive's contents rather than
trusting the intent.

**This is built crops-only pending Kam's confirmation.** If Kam declines even crops, nothing
here runs and the fallback is the referee's CPU figure — ~150 h — on this laptop.

    shard_<id>.zip
        manifest.json          provenance per crop + for the shard
        crops/<crop_id>.png    <crop_id> = sha256 of the PNG bytes

    result_<id>.zip
        results.jsonl          one row per crop: latex | failed, timing, batch
        worker.json            peak VRAM, regions/s, resolved versions, GPU
        DONE                   sha256 of the two members above — written LAST

Three §11 ideas from the retired Colab plan survive and nothing else does: the **stateless
shard**, the **packed artifact**, and the **hashed done marker**.

---

## 2. The crop is docling's crop, not a reimplementation of it

This is the load-bearing design decision, so it is stated with its evidence.

CodeFormula decodes an image that `BaseItemAndImageEnrichmentModel.prepare_element` cuts
(read in the installed package, `docling/models/base_model.py` lines 184–221, docling
2.127.0): the item's `prov[0].bbox`, expanded by `expansion_factor`, rendered through
`Page.get_image(scale=images_scale, cropbox=…)`. Both constants live on the model —
`images_scale = 1.67  # = 120 dpi, aligned with training data resolution` and
`expansion_factor = 0.18` — and this code reads them off the class rather than copying them.

`Page.get_image` has **two** paths: a direct backend render when the scale is not already in
`_image_cache`, and a PIL crop of the cached full-page render when it is. Which one fires
depends on pipeline state at enrichment time. Cutting the crop outside the pipeline means
guessing that state, so this code does not: `litkb/extract/formula_crop_worker.py` runs the
**real pipeline** with `do_formula_enrichment=True` and replaces the enrichment model's
`__init__`/`__call__` with a recorder that loads no weights and changes no text.
`prepare_element` is untouched, and the page backends are alive because docling sets
`keep_backend` whenever formula enrichment is on (`standard_pdf_pipeline.py`).

**Which class matters.** docling 2.127.0's `StandardPdfPipeline` builds `CodeFormulaVlmModel`
(the new VLM runtime), **not** the older `CodeFormulaModel`. Both exist in the package with
the same two constants; patching the wrong one would have silently loaded 611 MB of weights.

**Measured, not argued** — the recorder's crop against an unpatched `prepare_element` call on
the same page:

```
$ venv-docling\Scripts\python.exe -P formula_crop_worker.py \
      --verify-crop Bellettini_2002_total-variation-flow.pdf --verify-page 3 --device cpu
{"verify": [{"self_ref": "#/texts/5", "identical": true},
            {"self_ref": "#/texts/7", "identical": true}],
 "images_scale": 1.67, "expansion_factor": 0.18, "all_identical": true}
```

---

## 3. Corpus crop census

**Instrument:** `litkb/extract/formula_shards.py` (`dense_jobs` → `cut_crops` → `census`), run
over `Literture\{ASPP,Labeling,Validation,other}` — the referee's scope, `_litkb_staging` and
`_quarantine` excluded. Layout only (tables off, OCR off), the CUDA venv on the T2000,
4 threads. **Measured 2026-09-15**, not projected:

| | measured |
|---|--:|
| PDFs scanned | 219 |
| files with pages above the 0.05 density cut | 168 |
| dense pages | 1,571 |
| **equation-region crops** | **7,164** |
| **total crop bytes** | **67.29 MB** (70,560,678 B) |
| files that actually carry a crop | 136 |
| mean / median crop | 9,849 B / 6,838 B (p95 27,888 B, max 156,602 B) |
| regions per dense page | **4.56** |
| shards at 200 crops | **36** |
| density gate over the whole corpus | 44.8 s |
| crop cutting, 168 files | 1,481.5 s (24.7 min) |
| jobs failed | 0 |

**The census reproduces the referee's exactly on the pages** — 219 PDFs, 1,571 dense pages —
which is the join that says this is the same gate. On the REGIONS it lands slightly above the
referee's projection: **7,164 measured against ≈6,660 projected**, +7.6%, and 4.56 regions per
dense page against the 4.24 estimated from a 12-file sample. The projection was sound; this is
the full count.

**32 of the 168 dense files carry ZERO formula regions** (168 − 136). That is the referee's
§1.2 false-positive class showing up at corpus scale: numeric tables and figure pages that the
12-character line term reads as display maths. They cost a layout pass and nothing more —
there is no crop to ship and no region to decode.

**The distribution is extremely skewed, and that matters for sharding.** One file,
`Schneider_2008_stochastic-integral-geometry.pdf`, carries **2,653 crops (27.22 MB) — 37% of
the corpus** on its own; the median file carries 17. A shard plan that chunked by file would
put a third of the GPU bill in one job. `plan_shards` chunks by CROP, so the 36 shards are even
by construction.

**67 MB total is the number that answers the upload question.** The whole formula workload
crosses the wire in about the size of one aerial tile.

#### A defect found and fixed while measuring this

The first corpus run — one worker process over all 168 files — died at **exit code
3221226356 = 0xC0000374, STATUS_HEAP_CORRUPTION**, after 6,804 crops. That is a native crash
inside the converter's C extensions, so no Python `except` in the worker can see it, and the
whole batch's record went with the process. `cut_crops` now runs the corpus in **chunks of 12
files**, retries a crashed chunk **one file at a time** to isolate the offender, records an
unisolatable file as `failed`, and accumulates its record across chunks so a re-run resumes.
The re-run completed all 168 files with zero failures — the crash did not reproduce at a
12-file chunk size, which is consistent with a resource-exhaustion mode rather than one bad
file, and is stated as consistent-with rather than diagnosed.

---

## 4. Local dry-run of the worker — correctness, not speed

**The comparison is controlled for device and weights.** The reference LaTeX was regenerated
in the **same CPU venv** (`venv-docling`, docling 2.127.0 / docling-core 2.96.0,
torch 2.14.0, CPU) by the local adapter's own `extract(..., formulas="auto", pages=[3,4])`
path, so the only variable between the two sides is the crop path.

**Setup.** 20 crops in one shard, packed by the real packer; the worker run by
`venv-docling\Scripts\python.exe` with `--device cpu`. The 5 regions the referee checked —
Bellettini 2002 pp. 3–4 — are among them, and `write_shard` sorts by `crop_id`, so they were
**scattered across three different batches** (indices 0, 1 and 3 of 4) mixed with unrelated
crops, rather than decoded together the way docling's own enrichment decoded them.

**Result — 5 of 5 byte-identical**, joined on `(page, bbox rounded to 1 pt)`, which is
`merge_formula_latex`'s own key:

```
{"n_ref": 5, "n_identical": 5, "worker_ok": 20, "worker_failed": 0,
 "seconds": 1208.163, "regions_per_s": 0.0166, "batch_size": 5}
```

All 20 crops decoded; none failed. **Batch composition did not move the output** for these
five — they matched despite being decoded in different batches, alongside different
neighbours, from the batch the reference came from. That is a measurement about **five short
regions**, not a general claim about batched greedy decode; `--batch-size 1` exists in the
worker to answer the general question, and it has not been run.

**0.0166 regions/s is a CPU number on a laptop under other agents' load**, reported because it
is what the correctness run happened to measure. It is not the rate anything should be planned
from; the referee's T2000 GPU rate is 0.0496 regions/s and the L4's is unknown (§6).

---

## 5. Kills

`qc/test_litkb_formula_shards.py` — **19 passed**. Each kill below was fed a known-bad input
and observed to refuse it. **That is not a mutation test**: the gate CODE was not mutated the
way `qc/claims.py` was, so what is established is that each refusal fires on the input it
names, not that no edit to the gate could escape the suite.

| # | kill | fires on | real data? |
|---|---|---|---|
| 1 | **a corrupted crop archive fails ingest verification** | one byte flipped in the middle of a REAL result archive; sha256 sidecar mismatch. A truncated archive with the sidecar removed is refused by `zipfile` itself (second test) | yes — real bytes from the real packer |
| 2 | **a result with no done marker is refused** | the archive repacked without `DONE`; and separately, `DONE` left stale while a member is edited | yes |
| 3 | **a crop whose LaTeX is empty is recorded `failed`** | the worker's own path: `status="failed"`, `latex=None`, an error string. A forged `ok`-with-empty-LaTeX row is refused at ingest too | **partly** — the worker's batch-level refusal fired on a real defect; docling's empty-string OOM path is stubbed. See below |
| 4 | **a shard re-uploaded is skipped by sha256** | `ingest` with `seen_shards` returns `skipped` and writes nothing; `plan_shards` plans zero shards for crops already done | yes |
| + | a short result (2 crops against a 3-crop shard), with a *consistent* marker | refused on the crop-set check | yes |
| + | a packed crop whose bytes moved under its own id | `write_shard` refuses to pack it | yes |
| + | a stale local copy against a server-side md5 that disagrees, and a missing server-side md5 | both refused | the md5 call is stubbed; the RULE is real |
| + | a manifest with no `shard_sha256` reaching `ingest` | refused, naming `read_manifest` | yes — see below |

**Kill 3, said in the required words.** Making CodeFormula return an empty string on purpose
needs the model and a starved GPU, so the worker-side half of this kill is exercised with a
stubbed decode and is **UNVALIDATED on real data in this report**. It is not unvalidated in the
project: the same fail-closed rule one level up was **fired on a real CUDA out-of-memory** in
`LITKB_DOCLING_A_REFEREE_2026-09-15.md` §4, where docling reported `SUCCESS`, returned empty
strings for all five regions, and the adapter refused the run. This worker's rule is the
per-crop form of that one, and the mechanism it guards against —
`CodeFormulaVlmModel.__call__` setting `outputs = [""] * len(images)` inside its own `except` —
is read in the installed package, not assumed.

**Kill 4 had a hole, found in review and closed.** `ingest` skips a re-upload on
`shard_sha256` — but that is the hash of the *closed archive*, so it cannot be inside the
archive; `write_shard` put it only in the sidecar and its return value. A caller who had just
the shard file and read its manifest got `None`, `None in seen_shards` is False, the skip
never fired, and `shard_manifest_sha256: null` would have landed in the metrics row silently.
`read_manifest` now computes it from the path it was handed, `ingest` refuses a manifest
without one rather than skipping the skip, and
`test_a_manifest_read_from_the_archive_carries_the_archive_hash` ingests twice through exactly
the §6 recipe and asserts the second returns `skipped`.

Note the worker's own skip is by result **filename**, not by hash: a shard re-sent under the
same name is not re-decoded, and a *different* shard sent under an already-used name is caught
at ingest by the crop-set check (kill +1), not on the VM.

**The crop-path check is not a kill but it is the one correctness proof that matters** (§2):
`--verify-crop` compares the recorder's crop against an unpatched `prepare_element` and reports
`identical: true`.

**And the worker's fail-closed path fired unprompted on a real defect.** An earlier build
built the synthetic element as a `TextItem`, which docling-core refuses to label `formula`.
The `ValidationError` was raised in `_formula_element` — *before* `CodeFormulaVlmModel.__call__`
was ever reached, so docling's own empty-string handler never saw it. What caught it was the
worker's **own per-batch `except`** in `process_shard`, which recorded **20 of 20 crops as
`failed` with `latex=None`**; the giveaway in the record is `regions_per_s: 20025` and a null
VRAM peak. So half of kill 3 — the worker's batch-level refusal — is now **validated on real
bytes**. The other half, docling's `outputs = [""] * len(images)` path (the OOM signature),
remains **stubbed here and UNVALIDATED on real data in this report**; it is the half that was
fired on a real CUDA out-of-memory in the referee's §4.

---

## 6. The canary — prepared, NOT launched

> **CORRECTED BY THE RUN, 2026-09-15.** This section was written before the launch and two
> of its statements are wrong; `Reports/LITKB_COLAB_L4_CANARY_2026-09-15.md` is the home for
> both. (1) The `rclone copy … treedata-sa:` upload in the recipe below **cannot work on
> this account** — the service account has no Drive storage quota (403
> `storageQuotaExceeded`); it can list, read and md5sum only, so the upload goes through the
> Drive Desktop mount and is *verified* server-side through the SA. (2) The T2000 rate quoted
> below as "0.0496 regions/s" is the source metrics row's `pages_per_s` (2 pages / 40.331 s);
> regions/s for that run is 5 / 40.331 = 0.124, and every wall-clock scaled from it here
> inherits the mislabel. The measured L4 rate is **0.1727 regions/s**.

**Shard, built and sitting locally — not uploaded, not launched:**

    D:\edmonds-pipeline\litkb_derived\formula\shards\shard_canary200.zip
    200 crops drawn seeded (random.Random(20260915)) round-robin across 136 files
    2,201,004 B (2.10 MB)
    sha256 9bebebf1e1342f7cf267012e1e9dc943b7a31371ad9258eb14593f4a6bb75468
    md5    1a07553aed6782c05c37cc04a74d8426

The draw is spread across files on purpose: a canary taken from one paper measures that
paper's equations, not the corpus's.

**Queue file:** `Scripts/pipeline/queue_litkb_formula_l4.yaml`, tier L4, one shard, one
runtime.

**`vm_ops launch --queue` CANNOT run this, and that is not a workaround.** `launch_queue()`
emits `nohup python -u phase4_train_queue.py --queue <name>`, and that orchestrator understands
only phase4seg jobs keyed on `year`/`tag` (`phase4_train_queue.py`: `y, tag = job["year"],
job["tag"]`). litkb has neither. So the launch is two calls, and the second is the litkb front
door:

```bash
# 0. upload the shard (local-then-copy, CLAUDE.md 3.9 — written locally, then copied)
rclone copy D:\edmonds-pipeline\litkb_derived\formula\shards\shard_canary200.zip \
    treedata-sa:phase4/litkb/formula/shards/
rclone md5sum treedata-sa:phase4/litkb/formula/shards/shard_canary200.zip
#   must print 1a07553aed6782c05c37cc04a74d8426 — server-side, before any launch

# 1. create + bootstrap the runtime (write canary, editable install, repo clone)
py -3.12 pipeline/vm_ops.py launch --session litkbf1 --gpu L4 \
    --branch work/20260915-colab-l4-formula

# 2. start the worker, nohup-detached so it survives the exec handle
py -3.12 pipeline/vm_ops.py exec --session litkbf1 \
    --file pipeline/litkb_formula_vm_start.py --timeout 900

# 3. once LITKB_FORMULA_STARTED has been seen: watch, then stop the moment it drains
py -3.12 pipeline/vm_ops.py status --session litkbf1
py -3.12 pipeline/vm_ops.py stop   --session litkbf1

# 4. locally: pull the result and gate it
rclone copy treedata-sa:phase4/litkb/formula/results/result_shard_canary200.zip <local>
#   then litkb.extract.formula_ingest.ingest(result, manifest, metrics_jsonl, latex_jsonl,
#   remote="treedata-sa:phase4/litkb/formula/results/result_shard_canary200.zip")
```

Step 1 with no `--queue` does the lifecycle work and nothing else — including the
server-side-md5 write canary that proves uploads reach Drive before any writer runs.
**CLAUDE.md 3.4: this is the first launch of this queue, so it asks Kam.**

### Expected wall-clock — the scaled number, and how unsourced it is

The only GPU formula rate this repo has measured is on a **Quadro T2000**: the referee's §3,
5 regions in 40.33 s = **0.0496 regions/s**. Scaling that to 200 crops gives **67 minutes**.

**There is no L4 factor in this repo.** No measurement, no quote, no source. Numbers like "an
L4 is 3–6× a T2000" circulate; `colab_rates.csv`'s own header is this repository's rule about
exactly that kind of number, and it applies here.

| | |
|---|---|
| 200 crops at the **MEASURED** T2000 rate | **67 min** |
| 200 crops at an **UNCONFIRMED** 3–6× L4 factor | 11–22 min |
| plus model load and the pip install of the docling stack | **UNMEASURED on a VM** |
| the full corpus, 7,164 crops, at the T2000 rate | 40.1 h |
| the full corpus at the same **UNCONFIRMED** 3–6× | 7–13 h |

**Every row but the first is an inference, and the 3–6× has no source at all.** The canary's
job is to replace them with one measurement.

### The compute-unit procedure — the canary's other job

`pipeline/colab_rates.csv` ships **schema-only for GPUs**: "zero GPU rate rows. Add one only
WITH its evidence". Its own instruction for settling one is followed literally:

1. **Before** step 1, screen-read the balance at
   `https://colab.research.google.com/signup` (or Runtime > View resources) and record the
   reading **verbatim**, with a UTC timestamp. The last anchor on this account is
   `2026-09-03T01:40Z, 91.79 CU`.
2. Note the launch span: the timestamp of `LITKB_FORMULA_STARTED` and of `vm_ops stop`.
3. **Immediately after** the stop, read the balance again, verbatim.
4. Put `(before − after)` in `gpu_launches.csv::measured_cu_delta` for that launch.
5. Only then add a row to `colab_rates.csv` with `evidence_tier = MEASURED`,
   `gpu_name_pattern` matching the GPU string the worker recorded in `worker.json`
   (`torch.cuda.get_device_name(0)`, e.g. `NVIDIA L4`), `cu_per_hour = delta / span_hours`,
   `source_url` naming this report, and the two verbatim balance quotes in `quote`.

`usd_per_cu` stays BLANK unless an invoice is read: the 0.0999 in that file is the PAYG
marginal price, not this subscription's effective rate. And per that file's header, the rate
applies to a **launch span**, not to the worker's own seconds — the span is what Colab bills.

---

## 7. Everything UNCONFIRMED

Everything below is named because it is not measured. None of it blocks the canary; all of it
is what the canary settles.

1. **The L4's regions/s.** No measurement, no source. Every wall-clock in §6 is scaled from a
   T2000 by a factor with **no source in this repo**.
2. **The compute-unit rate for any GPU.** `colab_rates.csv` has zero GPU rows by design. The
   canary's CU delta would be the first one.
3. **Colab's torch on the L4 image.** Locally the CUDA venv is `torch==2.14.0+cu130`; what the
   VM ships has not been read on this account. `Scripts/requirements-litkb-colab.txt`
   deliberately does **not** pin torch, and the resolved version lands in every `worker.json`.
4. **Whether CodeFormula's weights download cleanly on the VM.** ~611 MB from HuggingFace at
   first use. Not tried.
4b. **Whether the docling install finishes inside the 900 s exec.** `litkb_formula_vm_start.py`
   runs `pip install -r Scripts/requirements-litkb-colab.txt` synchronously inside the exec,
   and `vm_ops exec` defaults to a 900 s timeout. The install has **never been timed on a
   VM**; if it overruns, the exec dies before the nohup line and nothing starts.
4c. **Whether that install replaces Colab's torch.** docling declares a torch *range*, not a
   pin, so pip may satisfy this file by installing a PyPI torch over the image's CUDA one —
   the exact swap the requirements file claims to avoid by not pinning torch. The payload now
   prints `LITKB_TORCH_BEFORE` and `LITKB_TORCH_AFTER` so a swap is visible in the exec
   channel rather than discovered later as a CPU-speed run. **Unmeasured.**
5. **Peak VRAM on a 24 GB card.** The referee established that the T2000 peak measures
   saturation, not requirement, and that the true working set is somewhere in (1.6, 3.9] GiB —
   **UNDETERMINED**. The worker records the allocator peak and the device-wide figures and
   calls neither the requirement.
6. **Whether batching moves decoded tokens in general.** Answered for 5 short regions (§4);
   unanswered for long ones. `--batch-size 1` is the instrument.
7. **Whether per-region decode cost is constant.** The referee flagged it: decode time scales
   with LaTeX length and every region measured so far is short. The canary's 200 crops across
   136 files is the first sample wide enough to say.
8. **Kam's confirmation that crops may leave the machine at all.** Built crops-only; not asked.
9. **The heap-corruption crash** (§3) did not reproduce at a 12-file chunk size. Consistent
   with resource exhaustion; **not diagnosed**.
10. **P5 ingest.** The rows are parked in JSONL, as every other stage parks them. Nothing here
    writes to any `litkb*` database, and none was touched.

---

## 8. Ladder and hygiene

* `py -3.12 qc/check.py --fast` was run from this worktree **with `LITKB_PGPORT=1`, stated
  here in those words**, so the litkb Postgres guards were NOT exercised. Observed output,
  quoted rather than summarised:

  ```
  litkb Postgres tests: 216 skipped  <- 216 SKIPPED: litkb server/role/psycopg absent,
                                        so those guards were NOT tested
  FAILED qc\test_experiments.py::test_pointer_paths_resolve[crown_state_model]
  1 failed, 2255 passed, 224 skipped, 74 warnings in 544.03s (0:09:04)
  check: FAILED at rung 'pytest' — fix, then rerun.
  ```

  (Re-run after the final edit, so the quote is of the state that was committed, not of an
  earlier one.)

  **The ladder's own verdict line is FAILED, not PASSED**, and that is reported here rather
  than the harness's exit code 0. The single failure is `crown_state_model`, the expected one:
  it fails on this branch's base commit and nothing added here touches it. 2,253 tests passed
  and nothing else failed. Because the ladder stops at the first failing rung, **preflight did
  not run**, and `--fast` skips the smoke by definition; the ruff F-rule and compile rungs did
  pass, since pytest is downstream of both. `ruff check --select F` over the seven added files
  separately: **All checks passed!**.
* `qc/test_litkb_formula_shards.py` alone: **19 passed**.
* No Colab runtime was created; no `colab` CLI call was made; no compute unit was spent.
* No `litkb*` database was touched. `D:\edmonds-pipeline\Literture` was read only. No other
  worktree was touched. No file added here prints a secret.
* Reproduction scripts for §3 and §4 live in this session's scratchpad; per CLAUDE.md §3.4b
  they are the evidence behind those sections and are named at each claim.

---

## 9. Canary 2 prepared — the two fixes the first canary asked for

**Nothing in this section has been launched.** Canary 1 left two defects behind, one named in
its own §6 and one implied by its §3, and both are fixed on this branch with tests that fire.

### 9.1 Fix 1 — the VM watchdog can see a litkb worker

The self-stop watchdog arms its idle timer only after it has SEEN a work process, and it
scanned `/proc` for three phase4 script names written inline in its own source. The litkb
worker is started as `python -u -m litkb.extract.colab_formula_worker`, matched none of them,
so `seen` never became True: the runtime's only backstop was the 2-hour "bootstrapped but no
queue" timer, and a hung decode would have burned all of it.

Two changes, both in `pipeline/gen_vm_bootstrap.py`:

* **`WORK_MARKERS`** — one home for "what counts as real work on a VM", with the litkb entry
  added. The watchdog is built from `repr(WORK_MARKERS)`, so the constant and the emitted
  literal cannot drift; `qc/test_litkb_formula_colab.py` also checks the marker against the
  text `litkb_formula_vm_start.py` actually runs, because a registry entry is a substring test
  against a cmdline and a changed launch line would silently blind the watchdog again.
* **A liveness beat, so ALIVE and WORKING stop being the same question.** Process presence
  only ever detected a worker that *exited*. `colab_formula_worker.beat()` writes
  `/content/litkb_worker_beat` before the model load and after every batch; the watchdog reads
  its mtime and, when a litkb process is present with a beat older than the idle window,
  treats it as hung.

**The semantics are the phase4 ones, deliberately.** A stale beat does not start a new clock:
the idle clock starts **at the last beat**, so a hung worker is stopped after the same 10 idle
minutes a vanished queue gets, measured from when the work actually stopped rather than from
when the watchdog noticed. Then the same `_drain()` on the real rclone upload backlog, then
`runtime.unassign()`. A phase4 queue leaves no beat, `beat_age` is `None` for it, and its path
through the decision is byte-for-byte what it was — asserted in
`test_phase4_semantics_are_unchanged`.

**`None` means alive.** No beat file — a worker build without the beat, or one whose first
beat has not landed — is *no evidence*, and the watchdog falls back to process presence. It
must never stop a running process because a file is missing.

**Why the beat comes before the model load.** Canary 1 ran **two execs on one runtime**. A
worker that only beat after its first batch would inherit the previous exec's beat file, read
minutes-stale, and the watchdog would stop a healthy VM during the 20 s model load. That
ordering is its own mutation row (W3).

The watchdog's decision is now a pure function, `_tick(now, pid, beat_age, seen, idle_since,
t0, boot_ok)`, sitting above the `while True:` loop, so the tests `exec` the watchdog's OWN
source lines — the ones the bootstrap emits — rather than a copy of its logic.

**Still open, and not fixed here:** the operator-visibility half. `vm_heartbeat.sample()`
derives `queue_proc`, the queue stem, `run_tags` and the status-CSV lookup from
`phase4_train_queue`, so `vm_ops status` will still show `queue_step None` for a litkb
runtime, exactly as it did in canary 1. Wiring litkb into those fields changes what each of
them means; that deserves its own change, not a rider on this one.

### 9.2 Fix 2 — N decode processes on one runtime

Canary 1 used **2.02 GB of a 23.66 GB card**, with GPU utilisation peaking at 35%. `--procs`
now runs N decode processes on the one runtime, each owning a slice of the shard.

**The batch plan does not depend on N — that is the whole safety argument.** Crops are ordered
by an estimated-cost proxy once, globally, chunked into batches, and only then are whole
**batches** assigned to processes. So every N decodes the same batches with the same members,
and `--procs` cannot move a token even if batching does (which is still UNCONFIRMED). Slicing
chooses *who* decodes a batch, never *what is in it*.

**Balance.** Cost proxy = **crop width in pixels × ink density** (the fraction of pixels darker
than L=200), a pure function of the PNG bytes. It stands in for decoded LaTeX length, which
canary 1 showed is what decode time tracks (r=0.974, batch wall-clock spanning 17×). It is
**not calibrated** — nothing here measures proxy against decoded length — and its only job is
to put the expensive batches first; if it ranked randomly the results would still be
identical, only slower. Batches then go to slices by longest-processing-time: heaviest first
into the least-loaded slice, ties to the lowest index. Deterministic, so two processes compute
the same assignment independently and no plan has to be shipped between them.

**A slice that dies fails only its own crops.** `merge_slices` is driven by the PLAN, not by
what came back. A crop with no row becomes `status="failed"` naming its slice and the child's
exit; a row a child called `ok` while carrying no LaTeX is rewritten to `failed`. **A child's
exit code is never trusted on its own** — the parent re-verifies each slice archive's DONE
marker against its members before reading a row, and enforces kill 3 again at the merge,
because an emptied or truncated child archive is exactly how an empty decode could arrive as
a success.

**How many processes — the formula.**

    per_proc = max(measured peak_reserved, measured device-wide footprint)
             = max(2.840 GB, 23.66 - 20.56 = 3.10 GB) = 3.10 GB
    N = min( floor(0.80 x VRAM_total / per_proc),   # memory
             cpu_count - 1,                          # leave the OS a core
             n_batches,                              # never more slices than work
             --max-procs )                           # the operator's ceiling

Both memory figures are **read off canary 1's `worker.json`**, not assumed. The device-wide
one is larger because it carries the CUDA context and the cuBLAS workspaces the allocator peak
does not, and that is the quantity which has to fit N times on one card. The 0.80 is a
headroom fraction, not a measurement: it leaves a fifth of the card for fragmentation and for
the allocator peak being a saturation figure rather than a requirement.

**One caveat, stated because it is load-bearing:** `device_free_bytes` is a *single sample*
taken after the decode loop, so 3.10 GB is neither an upper nor a lower bound on the true
per-process footprint — it is the only device-wide figure measured so far. The worker now
samples `mem_get_info` every batch and reports `device_min_free_bytes`, so canary 2 returns a
real one and this constant can be replaced by a measurement.

**Chosen N: 6**, bound by the memory term — `floor(0.80 x 23.66 / 3.10) = 6`. The CPU term is
**UNMEASURED**: nothing in this repo records the vCPU count of Colab's L4 image (canary 1's
heartbeat carries GPU and CPU *percent*, not core count), so N is computed **on the VM**, where
`os.cpu_count()` is read. At 8 vCPU the CPU term is 7 and memory still binds at 6; at 4 vCPU
it binds at **3**. The returned `proc_plan` names which term bound it, so the result says what
actually happened rather than what was expected. Per-process threads are `max(1,
min(--threads, (cpu_count - 1) // N))` — N processes each asking for 4 threads on an 8-vCPU
runtime is oversubscription, and the decode is GPU-bound anyway.

### 9.3 The local dry run — N=1 vs N=2, on the CPU venv

The same 20 crops (`--limit 20`, applied in MANIFEST order before the cost ordering, so both
arms decode the same set), the same shard, the CPU venv `D:\edmonds-pipeline\venv-docling`
(docling 2.127.0 / docling-core 2.96.0 / torch 2.14.0 — the pinned pair), `--device cpu`.

| | N=1 | N=2 |
|---|--:|--:|
| rows | 20 | 20 |
| ok / failed | 20 / 0 | 20 / 0 |
| slice errors | — | none |
| decode seconds | 1642.16 | 1662.53 |
| regions/s | 0.0122 | 0.0120 |
| sha256 of the canonical rows | `c963abde6e7a5a162a46c7c392cc363d49dc73294ba561cc9a0432dc346fb155` | **the same** |

**The results match.** "Canonical rows" is `results.jsonl` with exactly the two
`TIMING_FIELDS` — `batch_seconds` and `seconds_per_crop_in_batch` — dropped, and nothing else:
`crop_id`, `file`, `page`, `self_ref`, `status`, `latex`, `error`, `confidence`,
`confidence_basis`, `batch_index` and `batch_size` are all compared and all identical. The two
dropped fields are how long each batch waited for a shared CPU; they differ by construction
and are measurements of the run rather than results of it. **The raw files are NOT identical**
and the report does not claim they are — `"raw_files_identical": false` is printed by the
comparison itself.

**On speed this dry run says nothing, and is not meant to.** N=2 was 20 s SLOWER (1.2%). One
process with 4 threads already saturates this 4-core laptop, so a second only adds contention
— the whole premise of `--procs` is a GPU sitting at 35% utilisation with 2 GB of 24 GB used,
which a CPU box cannot reproduce. The dry run's job is the correctness claim: **the process
split does not change what is decoded.** Scaling is UNCONFIRMED until canary 2.

**One real bug was found by running it, and is fixed with a regression test.** The first N=2
attempt failed the whole shard. `subprocess.Popen(stdout=<file object>)` leaves `p.stdout` as
`None`, so the parent's `p.stdout.close()` raised — and because the parent raised before
waiting on the rest, slice 0's work was discarded and slice 1 was left **orphaned, still
decoding after the run had exited** (it had to be killed by hand). The child-spawn seam is now
`spawn_child()` / `wait_child()`, and `test_a_child_that_floods_its_output_neither_deadlocks_
nor_loses_its_exit_code` covers both of its hazards: the handle the parent must close itself,
and the 200 KB of child output that would deadlock a `PIPE`-based parent waiting on a
different slice. The N=2 numbers above are from the rerun on the fixed code.

### 9.4 The canary 2 run — prepared, NOT launched

Queue: `Scripts/pipeline/queue_litkb_formula_l4_canary2.yaml` — **one L4 runtime**, the same
`shard_canary200` (200 crops) plus `shard_ref5` (the five referee equations), `procs: auto`.
Both shards are already on the lake and were md5-verified server-side during canary 1, so
nothing is uploaded for this run.

**The out_dir is new, and it has to be.** The worker skips a shard whose result archive is
already present (kill 4), so writing into canary 1's `…/formula/results` would skip both
shards and return nothing at all. Canary 2 writes to `…/formula/results_procs`, which also
keeps canary 1's archives intact as the comparison baseline. While fixing that: `out_dir` was
declared in every queue file and **read by nothing** — the destination was a string in the
launch payload — so the worker now reads `out_dir` and `procs` from the queue file, and the
payload passes neither.

```bash
# 1. create + bootstrap the runtime (write canary, editable install, repo clone)
py -3.12 pipeline/vm_ops.py launch --session litkbf2 --gpu L4 \
    --branch work/20260915-colab-l4-formula

# 2. start the worker, nohup-detached so it survives the exec handle
py -3.12 pipeline/vm_ops.py exec --session litkbf2 \
    --file pipeline/litkb_formula_vm_start.py --timeout 900

# 3. watch, then stop the moment it drains
py -3.12 pipeline/vm_ops.py status --session litkbf2
py -3.12 pipeline/vm_ops.py stop   --session litkbf2
```

**Expected wall-clock — UNCONFIRMED, and the scaling term is the weak part.** Canary 1's
decode was **1157.9 s at 0.1727 regions/s**. Dividing by N=6 gives **≈193 s** of decode for
the 200-crop shard, plus ~6 s for ref5, plus one model load per process (20.1 s measured, in
parallel), plus the 2.5 min launch-to-READY and 49 s install measured in canary 1 — call it
**≈10 minutes of launch span**, which is what Colab bills. The division assumes the N
processes scale linearly, and **nothing has measured that**: utilisation peaked at 35% on one
process, so there is headroom, but six processes sharing one L4's SMs and PCIe will not be six
times one. Treat 193 s as a floor on the decode, and the launch span as the number that
matters. `--timeout 900` is the recipe's default and is enough; canary 1's `--timeout 2400`
was an unnecessary deviation.

**A free measurement rides along.** The batch plan now orders crops by cost, so canary 2's 200
crops are batched *differently* from canary 1's. Comparing the two runs' LaTeX row by row
answers design UNCONFIRMED #3 — whether batch composition moves the decoded tokens — at no
extra GPU cost. Identical LaTeX across the two batchings settles it in the direction the five
referee crops already suggest; a difference is a finding.

### 9.5 The balance read — Kam has to do this, and it is two lines

Canary 1's compute-unit delta is **UNMEASURED** because this session's permission layer
refuses to navigate a browser to Colab (`Browser Navigate Exfil`), and there is no other path
on this machine that reads the balance. `colab_rates.csv` still has **zero GPU data rows**.
That will not change on canary 2 unless Kam takes the readings himself:

> **1.** Immediately **before** step 1 above, open <https://colab.research.google.com/signup>
> and copy the line reading **"You currently have N compute units"** — verbatim, including the
> number.
> **2.** Immediately **after** `vm_ops stop` returns, reload the same page and copy the same
> line again, verbatim.

Those two lines plus the launch span are the whole measurement: the first MEASURED GPU rate
row that `colab_rates.csv` has been waiting for. Without them, canary 2 measures throughput
and nothing about cost.

### 9.6 Kills, and that they fire

`qc/instruments/litkb_formula_mutations.py` weakens one guard at a time in the real source,
runs the test that should catch it, and restores the file byte-for-byte with a sha256 check.
No database, no GPU, no lake — seconds on the laptop, which is the point: these guards protect
a billing runtime and a corpus-scale decode, and the evidence that they fire must not cost a
GPU hour to refresh.

```
baseline before: PASS
W1  FIRED  the watchdog stops treating a stale liveness beat as a hang
W2  FIRED  the litkb worker is dropped from the work registry
W3  FIRED  the worker no longer beats before it loads the model
W4  FIRED  the work registry stops being substituted into the emitted bootstrap
M1  FIRED  a crop no slice returned a row for is reported ok instead of failed
M2  FIRED  the merge stops coercing a child's ok-with-no-LaTeX row to failed
baseline after:  PASS
```

W1 is *also* fired inside the ordinary suite
(`test_the_stale_beat_gate_fires_when_it_is_removed`), which execs the watchdog head with that
one condition weakened and asserts the hung worker then survives — because a real hang is not
reproducible off a VM, and "the watchdog stops a hung worker" would otherwise rest on a test
that would pass just as well if the branch did nothing.
`test_every_mutation_row_still_has_a_target` fails the ordinary suite if a refactor moves a
guarded line out from under a row, so a stale campaign cannot quietly become no evidence.

**W4 exists because review found the fix itself would have killed the launch, and every gate
in this repo was blind to it.** `_WD` is a list of source lines built **on the VM**, inside the
bootstrap's f-string body — so a name it reads, `repr(WORK_MARKERS)`, has to be substituted
into the *emitted* script's namespace by the body header, exactly as `MOUNT` is. The constants
were added at the generator's module level and the three header lines were not. On the VM that
is a `NameError` at bootstrap line 15: **before `SELFSTOP_ARMED`, before the mount, before
anything** — a live, billing runtime with no watchdog and no beacon, which is the D14 failure
mode the watchdog was moved to the top of the bootstrap to prevent.

Nothing caught it because **parsing the emitted script is not running it**: `ast.parse` accepts
a `NameError` without complaint, and the static flattener every existing gate uses rewrites
`repr(WORK_MARKERS)` to a string literal *before* anyone looks at it — so the very tool that
makes the emitted script readable off-VM is what hid the missing binding.
`test_the_emitted_bootstrap_can_actually_BUILD_the_watchdog` now **executes** the emitted
script's prefix — imports, constants, the `_WD` literal, stopping before the first line that
touches the filesystem — and asserts every name the header must bind is bound. W4 is the
mutation that deletes one header line and shows it fires.

### 9.7 Ladder and hygiene for this change

* `LITKB_PGPORT=1 py -3.12 qc/check.py --fast`, run after the final edit. Stated in those
  words: **the litkb Postgres guards were NOT exercised** (216 skipped, no server on this
  machine). Verdict line quoted rather than summarised:

  ```
  litkb Postgres tests: 216 skipped  <- 216 SKIPPED: litkb server/role/psycopg absent,
                                        so those guards were NOT tested
  FAILED qc\test_experiments.py::test_pointer_paths_resolve[crown_state_model]
  1 failed, 2283 passed, 224 skipped, 74 warnings in 634.44s (0:10:34)
  check: FAILED at rung 'pytest' — fix, then rerun.
  ```

  (Re-run after the FINAL edit — the §9.6 header fix and its test — so the quote is of the
  state that was committed, not of an earlier one.)

  **The ladder's verdict is FAILED, not PASSED.** The single failure is `crown_state_model`,
  the same expected one this branch's base commit and §8 already carry; nothing in this change
  touches experiments. Because the ladder stops at the first failing rung, **preflight did not
  run**, and `--fast` skips the smoke by definition. `ruff check --select F` over the five
  touched/added Python files separately: **All checks passed!**
* `qc/test_litkb_formula_colab.py` alone: **26 passed**. The vm/litkb/ci subset: 423 passed.
* **No Colab runtime was created**, no `colab` CLI call was made, no compute unit was spent.
  Canary 2 is prepared and NOT launched.
* No `litkb*` database was touched; `LITKB_PGPORT=1` was set for every run. No other worktree
  was touched, `main` did not move, and no secret was printed.
* One process was killed by hand: the orphaned slice-1 child left running by the crashed first
  N=2 attempt (§9.3). It was a local CPU decode into the scratch dry-run directory, nothing on
  the lake, and it was identified by its own cmdline before being stopped.
* Dry-run evidence, outside the repo like every other litkb artefact:
  `D:\edmonds-pipeline\litkb_derived\formula\dryrun_procs\{n1,n2}\` — both result archives,
  their `.sha256` sidecars, and the per-slice logs under `n2\…​.slices\`.
