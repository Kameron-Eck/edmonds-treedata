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
