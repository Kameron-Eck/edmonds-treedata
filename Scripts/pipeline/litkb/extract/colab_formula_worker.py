r"""Decode a shard of equation crops with CodeFormula on a Colab GPU. RUNS ON COLAB ONLY.

This is the only litkb code that runs off this laptop. It reads a shard archive written by
:mod:`litkb.extract.formula_shards`, decodes every PNG crop with docling's
``CodeFormulaVlmModel``, and writes a packed result archive with a hashed done marker. It
never sees a PDF: the shard contains page-region crops and a manifest, which is the whole
point (``decisions.yaml::litkb-p0-foundation`` — the corpus stays local).

STATELESS. The worker holds no state between shards and assumes no ordering. Everything it
needs is in the shard; everything it produces is in the result archive; the join key is the
``crop_id``, which is the sha256 of the crop's own PNG bytes. A shard can therefore be run
twice with no harm, run on any VM, or abandoned mid-corpus.

FAIL CLOSED, PER CROP (CLAUDE.md §3.6's spirit, and the exact failure the adapter's
``FormulaEnrichmentFailed`` was written for). ``CodeFormulaVlmModel.__call__`` catches its own
batch exceptions — read in the installed package, docling 2.127.0,
``models/stages/code_formula/code_formula_vlm_model.py``: on any engine error it sets
``outputs = [""] * len(images)`` and the conversion still reports success. A CUDA
out-of-memory therefore arrives as EMPTY STRINGS, not as an exception. So: **an empty LaTeX
string is recorded as ``status="failed"``, never as a successful decode with empty text.**
That is the same rule the local adapter enforces per page; here it is per crop, because a
crop is the unit that can be retried.

WHAT IT REPORTS. Peak VRAM (``torch.cuda.max_memory_allocated`` AND the device-wide
``torch.cuda.mem_get_info`` low-water mark — the referee showed that the allocator peak
measures saturation, not requirement, so both are recorded and neither is called the
requirement), regions per second, per-crop seconds, batch composition, and the resolved
package versions. None of those are quoted from anywhere; they are measured on the VM.

BATCH COMPOSITION IS A VARIABLE, NOT A DETAIL. ``CodeFormulaVlmModel.elements_batch_size``
is 5 and the engine decodes a batch together. Whether padding inside a batched greedy decode
moves a token is not established anywhere in this repo, so the batch size is recorded on
every row and ``--batch-size 1`` exists to answer the question.

ONE RUNTIME, N DECODE PROCESSES (2026-09-15, from the L4 canary). The canary measured a
**2.02 GB allocator peak on a 23.66 GB L4** with the decode strictly sequential and GPU
utilisation peaking at 35% — the card was idle most of the run. ``--procs`` runs N decode
processes on the one runtime, each owning a slice of the shard. Two rules make that safe:

* **The batch plan does not depend on N.** Crops are ordered by an estimated-cost proxy
  (:func:`crop_cost`) ONCE, globally, chunked into batches, and only then are whole BATCHES
  handed to processes (:func:`assign_batches`, longest-processing-time). So every N decodes
  exactly the same batches with exactly the same members, and the only fields that may differ
  between N=1 and N>1 are the two timing fields — which are measurements of the run, not
  results of it. Ordering by cost is also what balances the slices: the canary showed batch
  wall-clock spans 17× and tracks decoded length at r=0.974, so a naive contiguous split
  would leave one process running long after the others finished.
* **A slice that dies fails only its own crops.** :func:`merge_slices` is driven by the PLAN,
  not by what came back: a crop with no row, or a row a child marked ``ok`` while carrying no
  LaTeX, is written out as ``status="failed"`` with the slice named. A child's exit code is
  never trusted on its own.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import time
import zipfile

DONE_NAME = "DONE"
RESULTS_NAME = "results.jsonl"
WORKER_NAME = "worker.json"
SCHEMA_VERSION = 1

# The two row fields that are MEASUREMENTS of a run rather than RESULTS of it. A slice plan
# cannot change what the model decodes (the batches are identical for every N) but it does
# change how long each batch waited for the GPU, so an N=1 vs N>1 comparison is made over
# every other field. Named here so the test and the report quote one list, not two.
TIMING_FIELDS = ("batch_seconds", "seconds_per_crop_in_batch")

# ── the VM's liveness beat ──────────────────────────────────────────────────────────────
# The self-stop watchdog in gen_vm_bootstrap.py could not see this worker at all until
# 2026-09-15 (canary report §6), so a hung decode burned to the 2-hour fallback. The
# watchdog now scans for this process AND reads the mtime of this file; a worker that is
# alive but has not finished a batch in 10 minutes is treated as idle. The beat is touched
# BEFORE the model is built — a stale beat left by an earlier exec on the same runtime would
# otherwise make the watchdog stop the VM during the 20 s model load.
WORKER_BEAT = "/content/litkb_worker_beat"


def beat(path=None):
    """Touch the liveness file the VM watchdog reads. Never raises; off-VM it no-ops."""
    p = path or os.environ.get("LITKB_WORKER_BEAT") or WORKER_BEAT
    try:
        if not os.path.isdir(os.path.dirname(p) or "."):
            return None
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
        return p
    except Exception:                     # noqa: BLE001 — a liveness beat must never kill a run
        return None


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def done_marker(results_bytes, worker_bytes):
    """The hashed done marker: sha256 of each member, in a fixed order.

    Written LAST inside the archive. A result archive without it is an interrupted run and
    the ingest refuses it (kill 2) — the whole reason a marker exists rather than a flag.
    """
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        RESULTS_NAME: _sha256(results_bytes),
        WORKER_NAME: _sha256(worker_bytes),
    }, sort_keys=True).encode("utf-8")


# ── the model ───────────────────────────────────────────────────────────────────────────

def build_model(device="cuda", threads=4, artifacts_path=None):
    """The real ``CodeFormulaVlmModel``, loaded ONCE. -> (model, batch_size)."""
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import CodeFormulaVlmOptions
    from docling.pipeline.standard_pdf_pipeline import CodeFormulaVlmModel

    # The same options object StandardPdfPipeline builds for formula enrichment: docling's
    # OWN default preset (``pipeline_options.py``: ``_default_code_formula_options =
    # CodeFormulaVlmOptions.from_preset("codeformulav2")``) plus the two extract_* switches
    # the pipeline sets in its model_copy. Read from the package, never invented — a bare
    # ``CodeFormulaVlmOptions()`` is not constructible: engine_options and model_spec are
    # required fields and only the preset fills them.
    opts = CodeFormulaVlmOptions.from_preset("codeformulav2").model_copy(
        update={"extract_code": False, "extract_formulas": True})
    model = CodeFormulaVlmModel(
        enabled=True, enable_remote_services=False, artifacts_path=artifacts_path,
        options=opts, accelerator_options=AcceleratorOptions(num_threads=threads,
                                                             device=device))
    return model, int(CodeFormulaVlmModel.elements_batch_size)


def _formula_element(image, index):
    """One synthetic ``ItemAndImageEnrichmentElement`` holding a crop.

    ``__call__`` reads exactly three things off the element — ``item.label`` (for the
    prompt), ``el.image`` (the crop) and, on the way out, ``item.text`` — and ignores its
    ``doc`` argument entirely. So a minimal item carrying the FORMULA label is a faithful
    stand-in for the item the pipeline would have passed, and the crop is the crop
    ``prepare_element`` cut locally.

    It must be a ``FormulaItem``, not a ``TextItem``: docling-core 2.96.0 constrains
    ``TextItem.label`` to a literal set that does NOT include ``formula`` (measured — the
    pydantic error names every member), and ``FormulaItem`` is the TextItem subclass that
    carries it. ``__call__``'s ``isinstance(el.item, CodeItem | TextItem)`` assertion and
    ``is_processable``'s TextItem test both accept the subclass.
    """
    from docling_core.types.doc import FormulaItem
    from docling.datamodel.base_models import ItemAndImageEnrichmentElement

    item = FormulaItem(self_ref=f"#/texts/{index}", orig="", text="", prov=[])
    return ItemAndImageEnrichmentElement(item=item, image=image)


def decode_batch(model, images):
    """-> [latex string], one per image, in order. Empty strings are the model's OOM path."""
    els = [_formula_element(im, i) for i, im in enumerate(images)]
    return [it.text for it in model(None, els)]


# ── the plan: cost proxy, batches, slices, and how many processes ───────────────────────

INK_LEVEL = 200          # a pixel darker than this is ink; lighter is page


def crop_cost(image):
    """Estimated decode cost of one crop: **width in pixels × ink density**.

    The canary settled that decode time is not constant per region — it tracks the DECODED
    LaTeX length at r=0.974 (canary report §3). The decoded length is not knowable before the
    decode, so this is a proxy for it: a formula's LaTeX grows with how much ink is laid out
    across the line, which is width × the fraction of the crop that is ink. Both terms are
    read off the crop itself, so the proxy is a pure function of the PNG bytes — which is what
    makes the batch plan below identical in every process and on every machine.

    It is a PROXY and is not claimed to be calibrated: nothing here measures proxy against
    decoded length. Its only job is to put the expensive batches first so the slices balance;
    if it ranked randomly the results would still be identical, only slower.
    """
    g = image.convert("L")
    w, h = g.size
    if not w or not h:
        return 0.0
    hist = g.histogram()
    ink = sum(hist[:INK_LEVEL])
    return w * (ink / float(w * h))


def plan_batches(crops, images, batch_size):
    """-> [[crop dict, …], …]: the global batch plan. THE SAME FOR EVERY N.

    Order by descending cost, ties broken by ``crop_id`` (content hash — a total order that
    exists on every machine), then chunk. Because the plan is computed before any slicing,
    every process decodes batches whose membership is what a single process would have
    decoded, so ``--procs`` cannot move a token even if batching does.
    """
    order = sorted(crops, key=lambda c: (-crop_cost(images[c["crop_id"]]), c["crop_id"]))
    bs = int(batch_size)
    return [order[i:i + bs] for i in range(0, len(order), bs)]


def batch_costs(plan, images):
    return [sum(crop_cost(images[c["crop_id"]]) for c in b) for b in plan]


def assign_batches(costs, n):
    """-> [slice index per batch]. Longest-processing-time, deterministic.

    Heaviest batch first into the least-loaded slice; ties to the lowest slice index. LPT is
    the standard greedy bound for this (makespan ≤ 4/3 of optimal) and, more to the point
    here, it is deterministic — two processes computing it independently agree, so no plan
    needs to be shipped between them.
    """
    n = max(1, int(n))
    load = [0.0] * n
    out = [0] * len(costs)
    for bi in sorted(range(len(costs)), key=lambda i: (-costs[i], i)):
        j = min(range(n), key=lambda k: (load[k], k))
        out[bi] = j
        load[j] += costs[bi]
    return out


# Measured on the L4 canary (Reports/LITKB_COLAB_L4_CANARY_2026-09-15.md §3), not assumed:
# the torch allocator's peak RESERVED was 2.840 GB, and the device-wide footprint implied by
# the same worker.json — total 23.66 GB minus 20.56 GB free at exit — is 3.10 GB. The second
# is larger because it includes the CUDA context and the cuBLAS workspaces the allocator peak
# does not. The planner takes the larger of the two, because the quantity that has to fit N
# times on one card is the device-wide one.
#
# CAVEAT, stated because it is load-bearing: `device_free_bytes` is a SINGLE SAMPLE taken
# after the decode loop, not a low-water mark, so 3.10 GB is neither an upper nor a lower
# bound on the true per-process footprint — it is the only device-wide figure measured so
# far. `_vram()` now tracks a real per-batch minimum (`device_min_free_bytes`), so canary 2
# returns a measured one and this constant can be replaced by it.
MEASURED_PEAK_RESERVED_BYTES = 2_840_000_000
MEASURED_DEVICE_FOOTPRINT_BYTES = 3_100_000_000
VRAM_SAFETY_FRACTION = 0.80


def plan_procs(vram_total_bytes, per_proc_bytes=None, cpu_count=None, n_batches=None,
               cap=None):
    """How many decode processes fit on one runtime. -> (N, the arithmetic behind it).

        per_proc = max(measured peak_reserved, measured device-wide footprint)
        N = min( floor(0.80 × VRAM_total / per_proc),   # memory
                 cpu_count - 1,                         # leave the OS a core
                 n_batches,                             # never more slices than work
                 --max-procs )                          # the operator's ceiling

    The 0.80 is a headroom fraction, not a measurement: it leaves the card a fifth of its
    memory for fragmentation and for the allocator peak being a saturation figure rather than
    a requirement (the referee's point, canary report §3). Every term is reported so an
    operator can see WHICH one bound N.
    """
    per = int(per_proc_bytes or max(MEASURED_PEAK_RESERVED_BYTES,
                                    MEASURED_DEVICE_FOOTPRINT_BYTES))
    terms = {"per_proc_bytes": per, "vram_safety_fraction": VRAM_SAFETY_FRACTION}
    limits = {}
    if vram_total_bytes and per > 0:
        limits["vram"] = int(VRAM_SAFETY_FRACTION * int(vram_total_bytes) // per)
    if cpu_count:
        limits["cpu"] = int(cpu_count) - 1
    if n_batches:
        limits["batches"] = int(n_batches)
    if cap:
        limits["max_procs"] = int(cap)
    n = max(1, min([v for v in limits.values()] or [1]))
    terms["limits"] = limits
    terms["bound_by"] = sorted(k for k, v in limits.items() if v == n) or ["floor"]
    terms["procs"] = n
    return n, terms


# ── VRAM ────────────────────────────────────────────────────────────────────────────────

_MIN_FREE = [None]        # device-wide low-water mark, sampled once per batch


def _sample_free():
    """Track the device-wide free-memory MINIMUM across the run.

    `device_free_bytes` alone is one sample taken after the loop; the canary's 3.10 GB
    device-wide footprint rests on it, and a single sample is not a low-water mark. Sampling
    every batch turns that into a measurement, which is what `plan_procs`'s per-process
    constant needs in order to stop being a constant.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return
        free, _total = torch.cuda.mem_get_info()
        if _MIN_FREE[0] is None or free < _MIN_FREE[0]:
            _MIN_FREE[0] = int(free)
    except Exception:                     # noqa: BLE001 — a probe never kills the run
        return


def _vram():
    try:
        import torch
        if not torch.cuda.is_available():
            return {}
        free, total = torch.cuda.mem_get_info()
        return {
            "device_min_free_bytes": _MIN_FREE[0],
            "peak_alloc_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            "device_free_bytes": int(free),
            "device_total_bytes": int(total),
            "gpu": torch.cuda.get_device_name(0),
            "peak_scope": "torch allocator high-water mark for THIS process; the referee "
                          "(LITKB_DOCLING_A_REFEREE_2026-09-15 §3) showed the device-wide "
                          "peak measures saturation, not the job's requirement",
        }
    except Exception as e:                # noqa: BLE001 — a probe must never kill the run
        return {"vram_error": f"{type(e).__name__}: {e}"}


# ── the run ─────────────────────────────────────────────────────────────────────────────

def read_shard(shard_zip, limit=None):
    """-> (manifest, crops, {crop_id: PIL image}). ``limit`` applies in MANIFEST order.

    The limit is taken before the cost ordering on purpose: ``--limit 20`` must name the same
    twenty crops whatever N is and whatever the proxy ranks, or a dry-run comparison is
    comparing two different sets.
    """
    from PIL import Image

    with zipfile.ZipFile(shard_zip) as z:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        crops = manifest["crops"]
        if limit:
            crops = crops[:limit]
        images = {}
        for c in crops:
            png = z.read("crops/" + c["crop_id"] + ".png")
            if _sha256(png) != c["crop_id"]:
                raise ValueError(f"crop {c['crop_id']} in the shard does not hash to its id")
            images[c["crop_id"]] = Image.open(io.BytesIO(png)).convert("RGB")
    return manifest, crops, images


def process_shard(shard_zip, out_zip, device="cuda", threads=4, batch_size=None,
                  artifacts_path=None, limit=None, _model=None, load_seconds=None,
                  slice_index=None, slice_of=None):
    """Decode ``shard_zip`` (or one slice of it); write ``out_zip``. -> the worker record.

    With ``slice_of`` set this process decodes only the batches LPT assigned to
    ``slice_index`` and ``out_zip`` is a plain results archive for the parent to merge; the
    parent, not this process, owns the DONE marker for the shard.
    """
    manifest, crops, images = read_shard(shard_zip, limit)

    t_load = time.time()
    if _model is None:
        model, default_bs = build_model(device, threads, artifacts_path)
    else:
        model, default_bs = _model
    # The model is loaded ONCE per queue, so a shard that reused it reports the load it
    # was handed, not a zero it did not measure.
    load_s = (time.time() - t_load) if load_seconds is None else float(load_seconds)
    bs = int(batch_size or default_bs)

    # THE PLAN IS GLOBAL AND N-INDEPENDENT (see the module docstring). Every process builds
    # the identical batch list from the identical crop set; slicing only chooses which of
    # those batches this process decodes.
    plan = plan_batches(crops, images, bs)
    mine = range(len(plan))
    if slice_of:
        who = assign_batches(batch_costs(plan, images), int(slice_of))
        mine = [i for i in range(len(plan)) if who[i] == int(slice_index)]

    rows, t0 = [], time.time()
    ok = failed = 0
    beat()
    for i in mine:
        chunk = plan[i]
        tb = time.time()
        try:
            latex = decode_batch(model, [images[c["crop_id"]] for c in chunk])
            err = None
        except Exception as e:            # noqa: BLE001 — the whole batch fails closed
            latex, err = [""] * len(chunk), f"{type(e).__name__}: {e}"
        dt = time.time() - tb
        for j, c in enumerate(chunk):
            tex = latex[j] if j < len(latex) else ""
            # FAIL CLOSED. docling swallows a batch exception and returns "", so an empty
            # string is a FAILURE, not a formula with no content. Never an empty LaTeX
            # recorded as success.
            good = bool(tex and tex.strip())
            ok, failed = ok + good, failed + (not good)
            rows.append({
                "crop_id": c["crop_id"], "file": c["file"], "page": c["page"],
                "self_ref": c.get("self_ref"),
                "status": "ok" if good else "failed",
                "latex": tex if good else None,
                "error": None if good else (err or "the model returned no LaTeX for this "
                                            "crop (docling's batch handler returns empty "
                                            "strings on an engine error)"),
                "confidence": None,
                "confidence_basis": "not produced: CodeFormulaVlmModel.__call__ reads only "
                                    "output.text from the VLM engine and requests no scores",
                "batch_index": i, "batch_size": len(chunk),
                "batch_seconds": round(dt, 3),
                "seconds_per_crop_in_batch": round(dt / len(chunk), 4),
            })
        _sample_free()
        beat()          # per batch: the watchdog's only evidence this worker is not hung
    seconds = time.time() - t0

    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": "3-formula-colab",
        "shard_id": manifest["shard_id"],
        "shard_sha256": sha256_file(shard_zip),
        # n_crops is what THIS process decoded. Unsliced that is the whole shard; sliced it
        # is this slice, and `shard_crops` carries the whole so a slice record is never read
        # as a short shard.
        "n_crops": len(rows),
        "shard_crops": len(crops),
        "slice_index": slice_index, "slice_of": slice_of,
        "ok": ok, "failed": failed,
        "seconds": round(seconds, 3),
        "regions_per_s": round(len(rows) / seconds, 4) if seconds > 0 else None,
        "model_load_seconds": round(load_s, 3),
        "batch_size": bs,
        "device": device,
        "threads": threads,
        "host": platform.node(),
        "python": sys.version.split()[0],
        "versions": _versions(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "status": "ok" if failed == 0 else "partial",
    }
    record.update(_vram())
    _write_result_archive(out_zip, rows, record)
    return record


# ── N processes on one runtime ──────────────────────────────────────────────────────────

def _stub_row(c, bi, bsz, error):
    """A crop the merge never got a trustworthy row for. FAILED, never empty-LaTeX-as-ok."""
    return {
        "crop_id": c["crop_id"], "file": c["file"], "page": c["page"],
        "self_ref": c.get("self_ref"),
        "status": "failed", "latex": None, "error": error,
        "confidence": None,
        "confidence_basis": "not produced: CodeFormulaVlmModel.__call__ reads only "
                            "output.text from the VLM engine and requests no scores",
        "batch_index": bi, "batch_size": bsz,
        "batch_seconds": None, "seconds_per_crop_in_batch": None,
    }


def merge_slices(plan, who, slice_rows, slice_errors=None):
    """-> (rows in global batch order, ok, failed). DRIVEN BY THE PLAN, NOT BY THE RETURNS.

    Two kills live here, and both are the reason a child's exit code is never enough:

    * **a slice that died fails only its own crops.** Every crop in the plan gets exactly one
      row. One with nothing returned for it becomes ``failed``, naming its slice and whatever
      the child said on the way out — the other slices' rows are untouched.
    * **kill 3, once more at the merge.** A row a child called ``ok`` while carrying no LaTeX
      is rewritten to ``failed``. The worker already refuses to emit one; this is the check
      that an emptied, truncated or partially-written child archive cannot smuggle one in.
    """
    errs = slice_errors or {}
    by_id = {}
    for si, rows in sorted(slice_rows.items()):
        for r in rows:
            by_id[r.get("crop_id")] = (si, r)
    out, ok, failed = [], 0, 0
    for bi, chunk in enumerate(plan):
        sl = who[bi] if bi < len(who) else None
        for c in chunk:
            got = by_id.get(c["crop_id"])
            if got is None:
                r = _stub_row(c, bi, len(chunk),
                              "slice %s returned no row for this crop: %s"
                              % (sl, errs.get(sl) or "the slice reported no error, so the "
                                                     "shortfall itself is the failure"))
            elif got[1].get("status") == "ok" and not (got[1].get("latex") or "").strip():
                r = _stub_row(c, bi, len(chunk),
                              "slice %s reported status=ok with no LaTeX — coerced to failed "
                              "at the merge (docling returns empty strings on an engine "
                              "error, so an empty decode is never a success)" % got[0])
            else:
                r = dict(got[1], batch_index=bi, batch_size=len(chunk))
            ok, failed = ok + (r["status"] == "ok"), failed + (r["status"] != "ok")
            out.append(r)
    return out, ok, failed


def _gpu_total_bytes():
    """Total VRAM via nvidia-smi, NOT via torch — importing torch here would create a CUDA
    context in the parent and hold ~0.3 GB for the whole run, against the children."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True)
        return int(float(r.stdout.strip().splitlines()[0])) * (1 << 20)
    except Exception:                     # noqa: BLE001
        return None


def default_batch_size():
    """``CodeFormulaVlmModel.elements_batch_size`` — read from the class, never retyped."""
    from docling.pipeline.standard_pdf_pipeline import CodeFormulaVlmModel
    return int(CodeFormulaVlmModel.elements_batch_size)


def spawn_child(cmd, log_path):
    """Start one slice, its output going to a FILE. -> (Popen, the handle we must close).

    EACH CHILD GETS A FILE, NOT A PIPE. With ``stdout=PIPE`` the parent would have to read
    every child concurrently; waiting on slice 0 while slice 3 fills its 64 KB pipe buffer
    deadlocks both, and the model load alone prints a weight-loading progress bar per
    process. And the handle is OURS to close: ``Popen(stdout=<file object>)`` leaves
    ``p.stdout`` as None, so there is nothing on the Popen to close afterwards — closing it
    there raised on the first real parallel run (2026-09-15) and took the whole shard with it.
    """
    fh = open(log_path, "wb")
    return subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT), fh


def wait_child(proc, handle, log_path, tail_bytes=400):
    """Wait for one slice and close its log. -> (returncode, the tail of its output)."""
    proc.wait()
    try:
        handle.close()
    except OSError:
        pass
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            tail = fh.read()[-tail_bytes:]
    except OSError:
        tail = "(no log)"
    return proc.returncode, tail


def process_shard_parallel(shard_zip, out_zip, procs="auto", device="cuda", threads=4,
                           batch_size=None, artifacts_path=None, limit=None,
                           peak_bytes=None, max_procs=None, python=None, work_dir=None):
    """Decode one shard with N child processes on this runtime. -> the parent's record."""
    bs = int(batch_size or default_batch_size())
    manifest, crops, images = read_shard(shard_zip, limit)
    plan = plan_batches(crops, images, bs)
    costs = batch_costs(plan, images)

    cpu = os.cpu_count() or 2
    if procs == "auto" or procs is None:
        n, terms = plan_procs(_gpu_total_bytes(), peak_bytes, cpu, len(plan), max_procs)
    else:
        n = max(1, min(int(procs), len(plan)))
        terms = {"procs": n, "bound_by": ["operator"], "limits": {"batches": len(plan)}}
    who = assign_batches(costs, n)
    # Leave the OS a core and split the rest: N processes each asking for 4 threads on an
    # 8-vCPU runtime is oversubscription, and the decode is GPU-bound anyway.
    per_threads = max(1, min(int(threads), (cpu - 1) // n if n else int(threads)))

    work = work_dir or (os.path.splitext(out_zip)[0] + ".slices")
    os.makedirs(work, exist_ok=True)
    py = python or sys.executable
    procs_running, slice_out, slice_log, log_handles = [], {}, {}, []
    t0 = time.time()
    for i in range(n):
        slice_out[i] = os.path.join(work, "slice_%d.zip" % i)
        slice_log[i] = os.path.join(work, "slice_%d.log" % i)
        cmd = [py, "-u", "-m", "litkb.extract.colab_formula_worker",
               "--shard", shard_zip, "--out-file", slice_out[i],
               "--slice-index", str(i), "--slice-of", str(n),
               "--device", device, "--threads", str(per_threads),
               "--batch-size", str(bs), "--no-log"]
        if limit:
            cmd += ["--limit", str(limit)]
        if artifacts_path:
            cmd += ["--artifacts-path", artifacts_path]
        # EACH CHILD GETS A FILE, NOT A PIPE. With stdout=PIPE the parent would have to read
        # every child concurrently; waiting on slice 0 while slice 3 fills its 64 KB pipe
        # buffer deadlocks both, and the model load alone prints a progress bar per process.
        p, fh = spawn_child(cmd, slice_log[i])
        procs_running.append(p)
        log_handles.append(fh)
    slice_rows, slice_errors, slice_records = {}, {}, {}
    for i, p in enumerate(procs_running):
        rc, tail = wait_child(p, log_handles[i], slice_log[i])
        beat()
        if rc != 0:
            slice_errors[i] = "child exit %d: %s" % (rc, tail)
        try:
            with zipfile.ZipFile(slice_out[i]) as z:
                names = set(z.namelist())
                if DONE_NAME not in names:
                    raise ValueError("slice archive has no DONE marker — interrupted")
                rb, wb = z.read(RESULTS_NAME), z.read(WORKER_NAME)
                if z.read(DONE_NAME) != done_marker(rb, wb):
                    raise ValueError("slice done marker does not match its members")
            slice_rows[i] = [json.loads(ln) for ln in rb.decode("utf-8").splitlines() if ln]
            slice_records[i] = json.loads(wb.decode("utf-8"))
        except Exception as e:            # noqa: BLE001 — one dead slice is not a dead shard
            slice_rows[i] = []
            slice_errors[i] = "%s; %s" % (slice_errors.get(i, ""), f"{type(e).__name__}: {e}")
    seconds = time.time() - t0

    rows, ok, failed = merge_slices(plan, who, slice_rows, slice_errors)
    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": "3-formula-colab",
        "shard_id": manifest["shard_id"],
        "shard_sha256": sha256_file(shard_zip),
        "n_crops": len(rows), "shard_crops": len(crops),
        "ok": ok, "failed": failed,
        "seconds": round(seconds, 3),
        "regions_per_s": round(len(rows) / seconds, 4) if seconds > 0 else None,
        "batch_size": bs, "device": device, "threads": per_threads,
        "procs": n, "proc_plan": terms,
        "slice_errors": {str(k): v for k, v in slice_errors.items()},
        "slice_logs": {str(k): v for k, v in slice_log.items()},
        "slice_records": {str(k): slice_records.get(k) for k in range(n)},
        "host": platform.node(), "python": sys.version.split()[0],
        "versions": _versions(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "status": "ok" if failed == 0 else "partial",
    }
    _write_result_archive(out_zip, rows, record)
    return record


def _write_result_archive(out_zip, rows, record):
    """results.jsonl + worker.json + the DONE marker LAST, then the .sha256 sidecar."""
    results_bytes = ("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
                     .encode("utf-8"))
    worker_bytes = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
    tmp = out_zip + ".partial"
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)) or ".", exist_ok=True)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        _w(z, RESULTS_NAME, results_bytes)
        _w(z, WORKER_NAME, worker_bytes)
        _w(z, DONE_NAME, done_marker(results_bytes, worker_bytes))   # LAST, always
    os.replace(tmp, out_zip)
    record["result_sha256"] = sha256_file(out_zip)
    record["result_bytes"] = os.path.getsize(out_zip)
    with open(out_zip + ".sha256", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(record["result_sha256"] + "  " + os.path.basename(out_zip) + "\n")
    return record


def _w(z, name, data):
    zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    zi.external_attr = 0o644 << 16
    zi.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(zi, data)


def _versions():
    from importlib.metadata import version
    out = {}
    for p in ("docling", "docling-core", "docling-ibm-models", "torch", "transformers",
              "tokenizers", "pillow"):
        try:
            out[p] = version(p)
        except Exception:                 # noqa: BLE001
            out[p] = None
    return out


# ── entry point ─────────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="litkb formula worker (Colab GPU)")
    ap.add_argument("--queue", default=None,
                    help="YAML/JSON list of shards to process, one queue per runtime")
    ap.add_argument("--shard", action="append", default=[],
                    help="a shard archive; repeatable. Overrides --queue")
    ap.add_argument("--out-dir", default=None, help="where result archives are written")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=None,
                    help="default: CodeFormulaVlmModel.elements_batch_size (5). Pass 1 to "
                         "test whether batching moves the decoded tokens.")
    ap.add_argument("--artifacts-path", default=None)
    ap.add_argument("--limit", type=int, default=None, help="first N crops of each shard")
    ap.add_argument("--log-dir", default=None,
                    help="phase4/logs on the lake; defaults to the step log's own home")
    ap.add_argument("--procs", default=None,
                    help="decode processes on THIS runtime: an integer, or 'auto' to size "
                         "them from measured VRAM (plan_procs). 1 = the sequential path. "
                         "Default: the queue file's `procs`, else 1.")
    ap.add_argument("--max-procs", type=int, default=None,
                    help="operator ceiling on --procs auto")
    ap.add_argument("--peak-bytes", type=int, default=None,
                    help="measured single-process peak for plan_procs; default is the L4 "
                         "canary's (see MEASURED_* in this module)")
    # The child-process side of --procs. Not for operators: the parent sets these.
    ap.add_argument("--slice-index", type=int, default=None)
    ap.add_argument("--slice-of", type=int, default=None)
    ap.add_argument("--out-file", default=None, help="exact output path (child slices)")
    ap.add_argument("--no-log", action="store_true", help="skip the step log (child slices)")
    # CLAUDE.md §3.10: the ONE shared pair filter. A hand-rolled copy drops --flag=value.json
    # whole and falls back to the default with no error.
    if argv is None:
        try:
            from phase4seg.names import clean_argv
            argv = clean_argv()          # already sys.argv[1:], Colab's -f pair removed
        except Exception:                 # noqa: BLE001 — a bare python run has no phase4seg
            argv = sys.argv[1:]
    a = ap.parse_args(argv)

    queued, queue_out, queue_procs = load_queue(a.queue)
    shards = list(a.shard) or queued
    a.out_dir = a.out_dir or queue_out
    a.procs = str(a.procs or queue_procs or "1")
    if not shards:
        raise SystemExit("no shards: pass --shard or a --queue file listing them")
    if not (a.out_dir or a.out_file):
        raise SystemExit("pass --out-dir (a queue) or --out-file (one archive)")
    beat()   # BEFORE the 20 s model load: a beat left by an earlier exec on this runtime
             # would otherwise read as stale and the watchdog would stop a healthy VM.

    # ── the child-slice path ────────────────────────────────────────────────────────────
    # One shard, one slice of its batch plan, one archive for the parent to merge.
    if a.slice_of:
        model = build_model(a.device, a.threads, a.artifacts_path)
        rec = process_shard(shards[0], a.out_file, device=a.device, threads=a.threads,
                            batch_size=a.batch_size, artifacts_path=a.artifacts_path,
                            limit=a.limit, _model=model,
                            slice_index=a.slice_index, slice_of=a.slice_of)
        print(json.dumps({k: rec.get(k) for k in
                          ("shard_id", "status", "slice_index", "slice_of", "n_crops",
                           "ok", "failed", "regions_per_s", "peak_alloc_bytes",
                           "device_min_free_bytes")}), flush=True)
        return 0

    os.makedirs(a.out_dir, exist_ok=True)

    # ── N processes on this runtime ─────────────────────────────────────────────────────
    # The model is NOT loaded in the parent: each child loads its own, and a parent CUDA
    # context would take memory from the children for nothing.
    if a.procs != "1":
        records, t0 = [], time.time()
        for s in shards:
            sid = os.path.basename(s).replace(".zip", "")
            out = os.path.join(a.out_dir, f"result_{sid}.zip")
            if os.path.exists(out):
                print(json.dumps({"shard": sid, "skipped": "result already present"}),
                      flush=True)
                continue
            try:
                rec = process_shard_parallel(
                    s, out, procs=a.procs, device=a.device, threads=a.threads,
                    batch_size=a.batch_size, artifacts_path=a.artifacts_path,
                    limit=a.limit, peak_bytes=a.peak_bytes, max_procs=a.max_procs)
            except Exception as e:        # noqa: BLE001 — one bad shard never kills a queue
                rec = {"shard": sid, "status": "failed", "error": f"{type(e).__name__}: {e}"}
            records.append(rec)
            print(json.dumps({k: rec.get(k) for k in
                              ("shard_id", "status", "n_crops", "ok", "failed", "procs",
                               "regions_per_s", "proc_plan")}), flush=True)
        if not a.no_log:
            _write_step_log(a.log_dir, {
                "shards": len(records),
                "crops": sum(int(r.get("n_crops") or 0) for r in records),
                "ok": sum(int(r.get("ok") or 0) for r in records),
                "failed": sum(int(r.get("failed") or 0) for r in records),
                "seconds": round(time.time() - t0, 1),
                "records": records,
            })
        return 0

    t_load = time.time()
    model = build_model(a.device, a.threads, a.artifacts_path)
    load_s = time.time() - t_load
    print(json.dumps({"model_load_seconds": round(load_s, 2)}), flush=True)
    records, t0 = [], time.time()
    for s in shards:
        sid = os.path.basename(s).replace(".zip", "")
        out = os.path.join(a.out_dir, f"result_{sid}.zip")
        if os.path.exists(out):
            # IDEMPOTENT (kill 4): a shard whose result is already on the lake is skipped.
            print(json.dumps({"shard": sid, "skipped": "result already present"}), flush=True)
            continue
        try:
            rec = process_shard(s, out, device=a.device, threads=a.threads,
                                batch_size=a.batch_size, artifacts_path=a.artifacts_path,
                                limit=a.limit, _model=model, load_seconds=load_s)
        except Exception as e:            # noqa: BLE001 — one bad shard never kills a queue
            rec = {"shard": sid, "status": "failed", "error": f"{type(e).__name__}: {e}"}
        records.append(rec)
        print(json.dumps({k: rec.get(k) for k in
                          ("shard_id", "status", "n_crops", "ok", "failed",
                           "regions_per_s", "peak_alloc_bytes")}), flush=True)

    if not a.no_log:
        _write_step_log(a.log_dir, {
            "shards": len(records),
            "crops": sum(int(r.get("n_crops") or 0) for r in records),
            "ok": sum(int(r.get("ok") or 0) for r in records),
            "failed": sum(int(r.get("failed") or 0) for r in records),
            "seconds": round(time.time() - t0, 1),
            "records": records,
        })
    return 0


def load_queue(path):
    """-> (shards, out_dir or None, procs or None).

    ``out_dir`` was declared in every queue file and READ BY NOTHING: the destination was a
    string in the launch payload, so two runs of different queues wrote into the same
    directory and the idempotent-skip then made the second one a no-op against the first
    one's results. The queue file is the right home for its own destination, so it is now
    honoured; an explicit ``--out-dir`` still wins.
    """
    if not path:
        return [], None, None
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except ValueError:
        import yaml
        data = yaml.safe_load(text)
    out_dir = procs = None
    if isinstance(data, dict):
        out_dir, procs = data.get("out_dir"), data.get("procs")
        data = data.get("shards") or []
    return [d["shard"] if isinstance(d, dict) else d for d in data], out_dir, procs


def _write_step_log(log_dir, payload):
    """CLAUDE.md §3.11 — every step logs to ``{BASE}/phase4/logs/`` before it exits.

    ``write_step_log(script, step, logs_dir, **fields)`` is the shared writer, and its
    ``**fields`` render one per line as ``name  value``. The per-shard records are therefore
    passed as SCALARS (a count and a one-line summary) rather than as a nested list, which
    that renderer flattens into an unreadable single line; the full records go beside it as
    JSON. Both paths were exercised locally on 2026-09-15 — the primary in the project env,
    the fallback in the extraction venv, which has no ``pipeline_log``.

    The fallback exists because this process may run on a VM where the editable install did
    not take, and a step that finished its work must not lose its log to an ImportError.
    """
    d = log_dir
    records = payload.get("records") or []
    scalars = {k: v for k, v in payload.items() if k != "records"}
    scalars["shard_ids"] = " ".join(str(r.get("shard_id") or r.get("shard") or "?")
                                    for r in records)
    scalars["shard_status"] = " ".join(str(r.get("status")) for r in records)
    try:
        from pathlib import Path

        from lake import BASE
        from pipeline_log import write_step_log
        logs = Path(d) if d else Path(BASE) / "phase4" / "logs"
        write_step_log(script="litkb_formula_colab_worker", step="formula", logs_dir=logs,
                       errors=int(payload.get("failed") or 0), **scalars)
        p = logs / ("litkb_formula_colab_%s.json"
                    % time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, sort_keys=True, ensure_ascii=False, indent=1)
        print("step log + records: " + str(p), flush=True)
        return str(p)
    except Exception:                     # noqa: BLE001 — never lose the log to an import
        d = d or "/content/drive/MyDrive/treedata/phase4/logs"
        try:
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "litkb_formula_colab_%s.json"
                             % time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, sort_keys=True, ensure_ascii=False, indent=1)
            print("step log: " + p, flush=True)
            return p
        except Exception as e:            # noqa: BLE001
            print(f"STEP LOG FAILED: {type(e).__name__}: {e}", flush=True)
            return None


if __name__ == "__main__":
    raise SystemExit(main())
