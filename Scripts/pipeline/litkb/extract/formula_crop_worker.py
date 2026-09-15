r"""Cut the equation-region CROPS docling itself would have fed to CodeFormula.

Runs ONLY in the extraction venv (``D:\edmonds-pipeline\venv-docling\Scripts\python.exe``),
spawned by :mod:`litkb.extract.formula_shards`. Same subprocess contract, same reasons, as
:mod:`litkb.extract.docling_worker` — see that file's docstring for why the heavy venv never
joins the project's ``sys.path`` and why the cwd is load-bearing.

WHY THE CROPS ARE NOT CUT BY HAND. The Colab worker must reproduce local LaTeX byte for
byte, so the crop it decodes has to be the crop docling would have decoded. That crop is
produced by ``BaseItemAndImageEnrichmentModel.prepare_element`` (read in the installed
package, ``docling/models/base_model.py`` lines 184-221, docling 2.127.0):

    bbox     = element.prov[0].bbox
    expanded = bbox.expand_by_scale(expansion_factor, expansion_factor)
    image    = conv_res.pages[page_ix].get_image(scale=images_scale, cropbox=expanded)

with ``images_scale = 1.67`` (= 120 dpi, "aligned with training data resolution") and
``expansion_factor = 0.18`` read off ``CodeFormulaVlmModel``, never hardcoded here.

``Page.get_image`` has TWO paths — a direct backend render when the scale is not in
``_image_cache``, and a PIL crop of the cached full-page render when it is — and which one
fires depends on pipeline state at enrichment time. Reimplementing the crop outside the
pipeline means GUESSING that state. So this worker does not reimplement it: it runs the real
pipeline with ``do_formula_enrichment=True`` and replaces the enrichment model's weights with
a recorder. ``prepare_element`` is untouched, the page backends are alive because docling sets
``keep_backend`` whenever formula enrichment is on (``standard_pdf_pipeline.py`` ~line 680),
and the crop is byte-identical BY CONSTRUCTION rather than by argument.

WHICH CLASS. docling 2.127.0's ``StandardPdfPipeline`` builds ``CodeFormulaVlmModel`` (the
new VLM runtime), NOT the older ``CodeFormulaModel``. Both classes exist in the installed
package and both carry the same ``images_scale``/``expansion_factor``; patching the wrong one
would silently load 611 MB of weights and decode the corpus on a T2000. The patch therefore
asserts the pipeline's own import, and ``--verify-crop`` re-proves the crop path against an
unpatched ``prepare_element``.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time

# See docling_worker.py: this directory holds ``docling.py``, the project's ADAPTER, which
# shadows the installed package. The launcher passes -P; this is the belt to that suspenders.
_SELF_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path
               if p and os.path.abspath(p) not in (_SELF_DIR, os.path.abspath(os.getcwd()))]

#: Filled by the patched ``__call__``; drained once per job.
_CAPTURED = []


def _patch_recorder():
    """Replace the enrichment model's engine with a recorder. -> (scale, expansion, name).

    Returns the model's OWN constants so every caller downstream quotes docling's numbers
    rather than a copy of them.
    """
    from docling.pipeline import standard_pdf_pipeline as spp

    cls = spp.CodeFormulaVlmModel        # the class the pipeline actually instantiates

    def _init(self, enabled, enable_remote_services, artifacts_path, options,
              accelerator_options):
        # No engine, no weights, no HuggingFace download. is_processable() reads only
        # self.enabled and self.options, both of which are set here exactly as the real
        # __init__ sets them, so the element FILTER is unchanged.
        self.enabled = enabled
        self.options = options
        self.engine = None

    def _call(self, doc, element_batch):
        for el in element_batch:
            _CAPTURED.append(el)
            yield el.item                 # text untouched: this pass enriches nothing

    cls.__init__ = _init
    cls.__call__ = _call
    return float(cls.images_scale), float(cls.expansion_factor), cls.__name__


def _png_bytes(img):
    """Deterministic PNG bytes for one crop. The sha256 of these bytes IS the crop id."""
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _build_converter(threads, device):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = False
    opts.do_table_structure = False       # crops need layout only; TableFormer is dead weight
    opts.do_formula_enrichment = True     # the switch that makes prepare_element run at all
    opts.accelerator_options = AcceleratorOptions(num_threads=threads, device=device)
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}), opts


def run_job(conv, job, crop_dir, scale, expansion):
    """Convert one file/page-range and write every formula crop. -> metrics dict."""
    src, lo, hi = job["pdf"], job["pages"][0], job["pages"][1]
    want = set(job.get("dense_pages") or [])
    _CAPTURED.clear()
    status, err, crops = "ok", None, []
    t0 = time.time()
    try:
        res = conv.convert(src, page_range=(lo, hi))
        doc = res.document
        # Page sizes come off the exported dict (STRING keys, cropbox frame) — the same
        # source the adapter's page_size() reads, so the canonical bbox the ingest joins on
        # is computed from the same height the adapter would use.
        sizes = {}
        exported = doc.export_to_dict()
        for k, p in (exported.get("pages") or {}).items():
            sizes[int(k)] = (p["size"]["width"], p["size"]["height"])
        fsha = file_sha256(src)
        for el in _CAPTURED:
            item = el.item
            prov = (item.prov or [None])[0]
            if prov is None or el.image is None:
                continue
            page = int(prov.page_no)
            if want and page not in want:
                continue                  # a dense RUN can span a non-dense page
            png = _png_bytes(el.image)
            cid = _sha256(png)
            with open(os.path.join(crop_dir, cid + ".png"), "wb") as fh:
                fh.write(png)
            bb = prov.bbox
            h = sizes.get(page, (None, None))[1]
            crops.append({
                "crop_id": cid,
                "file": os.path.basename(src),
                "pdf": src,
                "file_sha256": fsha,
                "page": page,
                "self_ref": item.self_ref,
                "label": str(item.label),
                "native_text": item.text,
                "bbox_raw": {"l": bb.l, "t": bb.t, "r": bb.r, "b": bb.b,
                             "coord_origin": str(bb.coord_origin)},
                "page_height": h,
                "png_bytes": len(png),
                "width": el.image.width,
                "height": el.image.height,
            })
    except Exception as e:                # noqa: BLE001 — the failure IS the measurement
        status, err = "failed", f"{type(e).__name__}: {e}"
    return {
        "status": status, "error": err, "file": os.path.basename(src), "pdf": src,
        "page_range": [lo, hi], "crops": crops, "n_crops": len(crops),
        "seconds": round(time.time() - t0, 3),
        "images_scale": scale, "expansion_factor": expansion,
    }


def verify_crop(pdf, page, threads, device):
    """Prove the recorder's crop equals an UNPATCHED ``prepare_element`` crop.

    The recorder claims byte-identity by construction. This is the one test that shows it:
    convert the page with the recorder, then re-derive the same element's crop through the
    real ``BaseItemAndImageEnrichmentModel.prepare_element`` on a model instance whose
    ``is_processable`` is satisfied but whose engine is never built. -> [(self_ref, bool)]
    """
    from docling.models.base_model import BaseItemAndImageEnrichmentModel
    from docling.pipeline import standard_pdf_pipeline as spp

    scale, expansion, _ = _patch_recorder()
    conv, _ = _build_converter(threads, device)
    _CAPTURED.clear()
    res = conv.convert(pdf, page_range=(page, page))
    recorded = [(el.item.self_ref, _png_bytes(el.image)) for el in _CAPTURED if el.image]

    ref = spp.CodeFormulaVlmModel.__new__(spp.CodeFormulaVlmModel)
    ref.enabled, ref.engine = True, None
    ref.options = type("O", (), {"extract_code": True, "extract_formulas": True})()
    out = []
    by_ref = {}
    for el in _CAPTURED:
        by_ref[el.item.self_ref] = el.item
    for sref, png in recorded:
        got = BaseItemAndImageEnrichmentModel.prepare_element(ref, res, by_ref[sref])
        out.append((sref, got is not None and _png_bytes(got.image) == png))
    return out, scale, expansion


def main(argv=None):
    ap = argparse.ArgumentParser(description="litkb formula-crop worker (extraction venv)")
    ap.add_argument("--jobs", help="JSON: [{pdf, pages:[lo,hi], dense_pages:[...]}, ...]")
    ap.add_argument("--crop-dir", help="directory the PNG crops are written to")
    ap.add_argument("--out", help="JSON file: one record per job")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--verify-crop", default=None, metavar="PDF",
                    help="prove the recorder crop == prepare_element crop, then exit")
    ap.add_argument("--verify-page", type=int, default=1)
    a = ap.parse_args(argv)

    if a.verify_crop:
        rows, scale, expansion = verify_crop(a.verify_crop, a.verify_page,
                                             a.threads, a.device)
        print(json.dumps({"verify": [{"self_ref": r, "identical": ok} for r, ok in rows],
                          "images_scale": scale, "expansion_factor": expansion,
                          "all_identical": bool(rows) and all(ok for _, ok in rows)}))
        return 0 if rows and all(ok for _, ok in rows) else 2

    scale, expansion, cls_name = _patch_recorder()
    os.makedirs(a.crop_dir, exist_ok=True)
    with open(a.jobs, encoding="utf-8") as fh:
        jobs = json.load(fh)
    conv, _ = _build_converter(a.threads, a.device)
    rows = []
    for job in jobs:
        m = run_job(conv, job, a.crop_dir, scale, expansion)
        m["recorder_class"] = cls_name
        rows.append(m)
        print(json.dumps({k: m[k] for k in ("file", "status", "n_crops", "seconds")}),
              flush=True)
    tmp = a.out + ".partial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, ensure_ascii=False)
    os.replace(tmp, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
