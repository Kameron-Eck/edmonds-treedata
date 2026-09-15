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
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import sys
import time
import zipfile

DONE_NAME = "DONE"
RESULTS_NAME = "results.jsonl"
WORKER_NAME = "worker.json"
SCHEMA_VERSION = 1


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


# ── VRAM ────────────────────────────────────────────────────────────────────────────────

def _vram():
    try:
        import torch
        if not torch.cuda.is_available():
            return {}
        free, total = torch.cuda.mem_get_info()
        return {
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

def process_shard(shard_zip, out_zip, device="cuda", threads=4, batch_size=None,
                  artifacts_path=None, limit=None, _model=None, load_seconds=None):
    """Decode every crop in ``shard_zip``; write ``out_zip``. -> the worker record."""
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

    t_load = time.time()
    if _model is None:
        model, default_bs = build_model(device, threads, artifacts_path)
    else:
        model, default_bs = _model
    # The model is loaded ONCE per queue, so a shard that reused it reports the load it
    # was handed, not a zero it did not measure.
    load_s = (time.time() - t_load) if load_seconds is None else float(load_seconds)
    bs = int(batch_size or default_bs)

    rows, t0 = [], time.time()
    ok = failed = 0
    for i in range(0, len(crops), bs):
        chunk = crops[i:i + bs]
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
                "batch_index": i // bs, "batch_size": len(chunk),
                "batch_seconds": round(dt, 3),
                "seconds_per_crop_in_batch": round(dt / len(chunk), 4),
            })
    seconds = time.time() - t0

    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": "3-formula-colab",
        "shard_id": manifest["shard_id"],
        "shard_sha256": sha256_file(shard_zip),
        "n_crops": len(crops),
        "ok": ok, "failed": failed,
        "seconds": round(seconds, 3),
        "regions_per_s": round(len(crops) / seconds, 4) if seconds > 0 else None,
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
    ap.add_argument("--out-dir", required=True, help="where result archives are written")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=None,
                    help="default: CodeFormulaVlmModel.elements_batch_size (5). Pass 1 to "
                         "test whether batching moves the decoded tokens.")
    ap.add_argument("--artifacts-path", default=None)
    ap.add_argument("--limit", type=int, default=None, help="first N crops of each shard")
    ap.add_argument("--log-dir", default=None,
                    help="phase4/logs on the lake; defaults to the step log's own home")
    # CLAUDE.md §3.10: the ONE shared pair filter. A hand-rolled copy drops --flag=value.json
    # whole and falls back to the default with no error.
    if argv is None:
        try:
            from phase4seg.names import clean_argv
            argv = clean_argv()          # already sys.argv[1:], Colab's -f pair removed
        except Exception:                 # noqa: BLE001 — a bare python run has no phase4seg
            argv = sys.argv[1:]
    a = ap.parse_args(argv)

    shards = list(a.shard) or _load_queue(a.queue)
    if not shards:
        raise SystemExit("no shards: pass --shard or a --queue file listing them")
    os.makedirs(a.out_dir, exist_ok=True)

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

    _write_step_log(a.log_dir, {
        "shards": len(records),
        "crops": sum(int(r.get("n_crops") or 0) for r in records),
        "ok": sum(int(r.get("ok") or 0) for r in records),
        "failed": sum(int(r.get("failed") or 0) for r in records),
        "seconds": round(time.time() - t0, 1),
        "records": records,
    })
    return 0


def _load_queue(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except ValueError:
        import yaml
        data = yaml.safe_load(text)
    if isinstance(data, dict):
        data = data.get("shards") or []
    return [d["shard"] if isinstance(d, dict) else d for d in data]


def _write_step_log(log_dir, payload):
    """CLAUDE.md §3.11 — every step logs to ``{BASE}/phase4/logs/`` before it exits.

    ``write_step_log(script, step, logs_dir, **fields)`` is the shared writer; the fallback
    below exists because this process may run on a VM where the editable install did not
    take, and a step that finished its work must not lose its log to an ImportError.
    """
    d = log_dir
    try:
        from pathlib import Path

        from lake import BASE
        from pipeline_log import write_step_log
        return write_step_log(script="litkb_formula_colab_worker", step="formula",
                              logs_dir=Path(d) if d else Path(BASE) / "phase4" / "logs",
                              errors=int(payload.get("failed") or 0), **payload)
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
