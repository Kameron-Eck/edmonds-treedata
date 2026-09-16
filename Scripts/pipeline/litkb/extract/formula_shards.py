r"""Pack equation-region crops into stateless SHARDS for the Colab formula worker.

THE CONSTRAINT THIS FILE EXISTS TO HONOUR. ``decisions.yaml::litkb-p0-foundation`` answers
"do the PDFs go to Drive?" with **none** — the corpus is local-only. Formula enrichment is
the one stage that wants a GPU (referee §5: ~6,660 regions, ~17 h on a GPU, ~150 h on CPU),
so what travels is not the corpus: it is a packed archive of PAGE-REGION IMAGE CROPS of the
equation regions, at the exact resolution CodeFormula was trained on, and nothing else. No
PDF, no page image, no text. **Crops-only is pending Kam's confirmation** and is built as the
only mode; there is no flag that uploads a PDF.

WHAT A SHARD IS (the design's §11 ideas that survive: stateless shard, packed artifact,
hashed done marker):

    shard_<shard_id>.zip
        manifest.json          — provenance for every crop, and for the shard as a whole
        crops/<crop_id>.png    — one 120-dpi crop, <crop_id> = sha256 of the PNG bytes

A shard carries no state and no ordering assumption: the worker may process it on any VM, in
any order, and the result joins back on ``crop_id``. ``crop_id`` being the content hash is
what makes the whole thing idempotent — re-running the builder over an unchanged corpus
re-emits identical crop bytes, and :func:`plan_shards` skips any crop already packed.

WHERE THE CROPS COME FROM. Not from this process. :mod:`litkb.extract.formula_crop_worker`
runs in the extraction venv and records the crops docling's own ``prepare_element`` cuts;
this module only decides WHICH pages to ask for (the equation-density gate,
``docling.dense_pages``), spawns that worker, and packs what comes back. Nothing here
imports docling, torch or PIL, so ``qc/check.py`` stays free of the 2.5 GB venv (design
referee M9).

WHAT THE INGEST JOINS ON. ``merge_formula_latex`` matches a formula region by
``(page, bbox rounded to 1 pt)`` in the CANONICAL top-left frame. The manifest therefore
carries ``self_ref``, ``page`` and ``bbox_canonical`` for every crop, computed here with the
adapter's own :func:`docling.to_canonical` — so a returned LaTeX string patches onto the
document exactly the way ``formulas="auto"`` would have patched it.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import zipfile

from . import docling as _dg

#: The venv-side crop recorder, spawned exactly the way ``docling.run`` spawns its worker.
CROP_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "formula_crop_worker.py")

#: Crops per shard. 200 is the canary size and a sane production size for the same reason:
#: at the measured mean crop size a 200-crop shard is a few MB, which is one Drive write,
#: and a lost shard costs ~200 regions of GPU time, not a corpus.
SHARD_CROPS = 200

SCHEMA_VERSION = 1


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def md5_file(path, chunk=1 << 20):
    """MD5 because rclone's server-side hash is MD5 — see :mod:`formula_ingest`."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


# ── choosing the pages ──────────────────────────────────────────────────────────────────

def dense_jobs(pdfs, cut=None):
    """[{pdf, pages:[lo,hi], dense_pages:[…]}] — ONE job per file, not per contiguous run.

    ``formulas="auto"`` spawns a worker per contiguous run, and the referee measured what
    that costs: 453 runs across 168 files at 13-18 s of cold start each, **1.6-2.3 h** the
    projection did not carry (referee §5). Crops need layout only, and layout is cheap, so
    this stage converts each file ONCE over the span from its first dense page to its last
    and filters the captured crops back to the dense set. The cold start is paid per FILE,
    and the converter is built once for the whole batch.
    """
    jobs = []
    for pdf in pdfs:
        dense = _dg.dense_pages(pdf, cut)
        if not dense:
            continue
        jobs.append({"pdf": pdf, "pages": [min(dense), max(dense)],
                     "dense_pages": dense})
    return jobs


def cut_crops(jobs, crop_dir, out_json, python=None, threads=4, device="cpu",
              timeout=36000, cwd=None, chunk=12, retry_singly=True):
    """Spawn the crop worker over ``jobs``, in CHUNKS. -> [job record].

    WHY CHUNKS, AND WHY THIS IS NOT A TUNING KNOB. A single worker process over the whole
    corpus died at **exit code 3221226356 = 0xC0000374, STATUS_HEAP_CORRUPTION**, after 168
    files and 6,804 crops (measured 2026-09-15, CUDA venv). That is a native crash inside the
    converter's C extensions, not a Python exception, so no ``except`` in the worker can see
    it and the whole batch's record was lost with the process. Chunking bounds the loss to
    one chunk; ``retry_singly`` then re-runs a crashed chunk one file at a time, so a single
    bad file is isolated and recorded as ``failed`` instead of taking its neighbours down.

    RESUMABLE. ``out_json`` accumulates records across chunks and across invocations, so a
    re-run picks up where the last one stopped; the crops themselves are content-addressed
    and re-cutting one is a no-op.
    """
    py = python or _dg.VENV_PYTHON
    if not os.path.exists(py):
        raise _dg.DoclingError(
            f"the extraction venv python is not at {py}; docling is deliberately NOT "
            f"installed in the project environment (design M9). Set LITKB_EXTRACT_PYTHON.")
    work = cwd or os.path.dirname(os.path.abspath(out_json)) or os.getcwd()
    os.makedirs(work, exist_ok=True)
    os.makedirs(crop_dir, exist_ok=True)

    done = []
    if os.path.exists(out_json):
        with open(out_json, encoding="utf-8") as fh:
            done = json.load(fh)
    seen = {r.get("pdf") for r in done if r.get("status") == "ok"}
    todo = [j for j in jobs if j["pdf"] not in seen]

    for i in range(0, len(todo), max(1, int(chunk))):
        part = todo[i:i + max(1, int(chunk))]
        rows, rc, err = _run_worker(py, part, crop_dir, work, threads, device, timeout)
        if rows is None and retry_singly and len(part) > 1:
            rows = []
            for job in part:
                one, rc1, err1 = _run_worker(py, [job], crop_dir, work, threads, device,
                                             timeout)
                rows += one if one is not None else [{
                    "status": "failed", "file": os.path.basename(job["pdf"]),
                    "pdf": job["pdf"], "crops": [], "n_crops": 0,
                    "error": f"the crop worker exited {rc1} without writing a record "
                             f"(a native crash, not a Python exception): "
                             f"{(err1 or '')[-300:]}"}]
        if rows is None:
            rows = [{"status": "failed", "file": os.path.basename(j["pdf"]),
                     "pdf": j["pdf"], "crops": [], "n_crops": 0,
                     "error": f"the crop worker exited {rc} without writing a record: "
                              f"{(err or '')[-300:]}"} for j in part]
        done += rows
        with open(out_json + ".partial", "w", encoding="utf-8", newline="\n") as fh:
            json.dump(done, fh, ensure_ascii=False)
        os.replace(out_json + ".partial", out_json)
    return done


def _run_worker(py, jobs, crop_dir, work, threads, device, timeout):
    """One worker process over ``jobs``. -> ([record] | None, returncode, stderr)."""
    stamp = int(time.time() * 1000)
    jobs_file = os.path.join(work, f"_crop_jobs_{stamp}.json")
    out_file = os.path.join(work, f"_crop_out_{stamp}.json")
    with open(jobs_file, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(jobs, fh)
    # -P for the same reason docling.run passes it: this package holds a docling.py that
    # shadows the installed package on sys.path[0].
    cmd = [py, "-P", CROP_WORKER, "--jobs", jobs_file, "--crop-dir",
           os.path.abspath(crop_dir), "--out", out_file,
           "--threads", str(threads), "--device", device]
    try:
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout)
        rc, err = proc.returncode, proc.stderr
    except subprocess.TimeoutExpired as e:
        rc, err = -1, f"timed out after {timeout}s: {e}"
    rows = None
    if os.path.exists(out_file):
        with open(out_file, encoding="utf-8") as fh:
            rows = json.load(fh)
    for p in (jobs_file, out_file):
        try:
            os.remove(p)
        except OSError:
            pass
    return rows, rc, err


def crop_records(job_rows):
    """Flatten the worker's per-job records into one crop list, canonical bbox attached.

    The canonical bbox is computed HERE, with the adapter's own :func:`docling.to_canonical`,
    so it is the same number ``merge_formula_latex`` will key on at ingest. A crop whose page
    height is unknown keeps ``bbox_canonical = None`` and is still shipped — the LaTeX is
    usable by ``self_ref``; only the bbox join degrades.
    """
    out = []
    for row in job_rows:
        if row.get("status") != "ok":
            continue
        for c in row.get("crops") or []:
            bb = c["bbox_raw"]
            h = c.get("page_height")
            can = None
            if h:
                can = list(_dg.to_canonical(bb, h))
            d = dict(c)
            d["bbox_canonical"] = can
            d.pop("pdf", None)          # a shard never carries a local path
            out.append(d)
    return out


# ── packing ─────────────────────────────────────────────────────────────────────────────

def plan_shards(crops, done_ids=(), size=SHARD_CROPS):
    """[[crop, …], …] — crops not already done, in stable order, chunked.

    IDEMPOTENT BY SHA256 (kill 4). ``done_ids`` is the set of ``crop_id`` values already
    packed or already returned; a crop whose bytes are unchanged hashes the same and is
    dropped, so a re-run of the builder over an unchanged corpus plans ZERO shards and a
    re-uploaded shard is skipped rather than re-decoded.
    """
    done = set(done_ids)
    seen, todo = set(), []
    for c in sorted(crops, key=lambda c: (c["file"], c["page"], c["crop_id"])):
        cid = c["crop_id"]
        if cid in done or cid in seen:
            continue
        seen.add(cid)
        todo.append(c)
    return [todo[i:i + size] for i in range(0, len(todo), size)]


def write_shard(crops, crop_dir, out_zip, shard_id=None, extra=None):
    """Pack one shard. -> manifest dict (its ``shard_sha256`` is of the CLOSED archive).

    Deterministic: entries are sorted, every ZipInfo gets a fixed timestamp and stored
    external attributes, so the same crops pack to the same bytes. That is what lets the
    ingest's "have I seen this shard?" question be answered by a hash.
    """
    crops = sorted(crops, key=lambda c: c["crop_id"])
    sid = shard_id or sha256_bytes(
        "".join(c["crop_id"] for c in crops).encode())[:16]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "shard_id": sid,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_crops": len(crops),
        "crop_ids": [c["crop_id"] for c in crops],
        "crops": crops,
        "contains": "page-region PNG crops of equation regions ONLY — no PDFs, no full "
                    "page images, no text (decisions.yaml litkb-p0-foundation: the corpus "
                    "is local-only)",
    }
    manifest.update(extra or {})
    body = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
    tmp = out_zip + ".partial"
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        _write(z, "manifest.json", body)
        for c in crops:
            p = os.path.join(crop_dir, c["crop_id"] + ".png")
            with open(p, "rb") as fh:
                png = fh.read()
            if sha256_bytes(png) != c["crop_id"]:
                raise ValueError(f"crop {c['crop_id']} on disk does not hash to its id — "
                                 f"refusing to pack a shard whose contents have moved")
            _write(z, "crops/" + c["crop_id"] + ".png", png)
    os.replace(tmp, out_zip)
    manifest["shard_sha256"] = sha256_file(out_zip)
    manifest["shard_md5"] = md5_file(out_zip)
    manifest["shard_bytes"] = os.path.getsize(out_zip)
    with open(out_zip + ".manifest.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, sort_keys=True, ensure_ascii=False)
    return manifest


def _write(z, name, data):
    zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    zi.external_attr = 0o644 << 16
    zi.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(zi, data)


def read_manifest(shard_zip):
    """The manifest inside a shard, with the ARCHIVE's own hashes filled in from the path.

    WHY THE FILL-IN IS NOT OPTIONAL. ``shard_sha256`` is the hash of the closed archive, so it
    cannot live inside that archive — :func:`write_shard` computes it after the zip closes and
    puts it in the ``.manifest.json`` sidecar and in its return value only. A reader that took
    the embedded manifest at face value would hand :func:`formula_ingest.ingest` a manifest
    whose ``shard_sha256`` is ``None``, ``None in seen_shards`` is False, and the re-upload
    skip would silently never fire while ``shard_manifest_sha256: null`` landed in the metrics
    row. So the one reader that has the path computes them here, once.
    """
    with zipfile.ZipFile(shard_zip) as z:
        man = json.loads(z.read("manifest.json").decode("utf-8"))
    man["shard_sha256"] = sha256_file(shard_zip)
    man["shard_md5"] = md5_file(shard_zip)
    man["shard_bytes"] = os.path.getsize(shard_zip)
    return man


def census(crops):
    """The number the report must carry: how many crops, how many MB, per file and total."""
    total = sum(int(c.get("png_bytes") or 0) for c in crops)
    files = {}
    for c in crops:
        e = files.setdefault(c["file"], {"crops": 0, "bytes": 0, "pages": set()})
        e["crops"] += 1
        e["bytes"] += int(c.get("png_bytes") or 0)
        e["pages"].add(c["page"])
    for e in files.values():
        e["pages"] = len(e["pages"])
    return {"n_crops": len(crops), "total_bytes": total,
            "total_mb": round(total / (1 << 20), 2),
            "mean_crop_bytes": round(total / len(crops)) if crops else 0,
            "n_files": len(files), "per_file": files}
