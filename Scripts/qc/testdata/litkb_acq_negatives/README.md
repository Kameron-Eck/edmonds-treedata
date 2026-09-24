# litkb_acq_negatives — the acceptance test's CONSTRUCTED negatives

Every file in this folder is **CONSTRUCTED** (CLAUDE.md §3.4c: a constructed input says so in its name and in
its description). LITKB_WORKPLAN.md "### S4.5", Test set: "NEGATIVE, CONSTRUCTED — and this line says so in
those words, per §3.4c, because the base holds none of them".

Built by `qc/instruments/litkb_acq_negatives.py` (deterministic bytes: no timestamp, no random id).
`PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acq_negatives.py --check` rebuilds each PDF
and compares it with the committed file; `qc/test_litkb_accept.py` does the same on every run. The PDFs are
`binary` under the repository's `*.pdf` rule, so a Windows and a Linux checkout hold the same bytes.

| file | what it is | the verdict `litkb.acquire.accept.accept` must give |
|---|---|---|
| `CONSTRUCTED_bom_valid_article.pdf` | a valid 3-page article (>3,000 characters, a References section) behind a UTF-8 byte-order mark | ACCEPT after the header repair (offset 3); `missing_pdf_header` with the repair removed — `bytes.lstrip()` does not strip a BOM |
| `CONSTRUCTED_tdm_stub_first_page.pdf` | one first page (title, authors, abstract; <3,000 characters, no references), padded past the 5,000-byte floor by an unreferenced stream | `stub_not_article` (`chars_no_refs`, and `x_els_status` with its header record) |
| `CONSTRUCTED_tdm_stub_first_page.headers.json` | the response headers that stub is served with; the `X-ELS-Status` VALUE is invented (litkb never recorded Elsevier's real wording) and says so | — |
| `CONSTRUCTED_proceedings_volume_60p.pdf` | 60 pages whose first 12 are the requested paper, offered for a record whose page range is `101-112` | `volume_not_article` |
| `CONSTRUCTED_cites_requested_doi.pdf` | a 5-page report whose only print of `10.5555/litkb-constructed-requested-0001` is in its bibliography on page 5 | `cited_document_not_this_article` when that DOI is requested |
| `CONSTRUCTED_scan_no_text_layer.pdf` | a scanned article as an archive serves one: a text cover sheet (under 200 characters), then 5 image-only pages (one uncompressed gray raster each, no text); <3,000 characters, no reference heading | ACCEPT — the stub rule abstains on image pages (decision D13; auditor-C1b F1: the four real scans on live were refused `stub_not_article` before the abstention); `stub_not_article` with the abstention removed |

The REAL negative beside them is E20's publisher preview, `qc/fixtures/litkb_e20_preview.pdf` (recorded once;
provenance in `qc/fixtures/litkb_e20_preview.provenance.json`).
