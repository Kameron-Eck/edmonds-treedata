# KB tooling facts (researched 2026-09-13; all URLs fetched that day unless marked)

## 1. GROBID
- Latest release **0.9.1, published 2026-08-04**; 0.9.0 2026-04-07 ("Upgraded to JDK 21 and Gradle 9"; Docker base -> eclipse-temurin 21.0.10_7; "TensorFlow 2.17 with Python 3.10-3.11"). https://api.github.com/repos/kermitt2/grobid/releases
  (Note: the HTML releases page summary gave contradictory Java 11 claims and 2024 dates; the API JSON above is the reliable source.)
- JDK: "OpenJDK 21 for building GROBID from source" / install doc "OpenJDK 21 or higher". https://github.com/grobidOrg/grobid , https://grobid.readthedocs.io/en/latest/Install-Grobid/ . Java 23 specifically: **UNCONFIRMED** (docs say "21 or higher"; no test statement found).
- Windows: "should run properly 'out of the box' on Linux (64 bits) and macOS (Intel and ARM). We cannot ensure currently support for Windows as we did before (help welcome!)." (GitHub README). Docker is the documented alternative; "GPU usage via a container on Windows and MacOS machine is currently not supported by Docker." https://grobid.readthedocs.io/en/latest/Grobid-docker/
- Images: `grobid/grobid:0.9.1-crf` ~500 MB (CRF only) vs `grobid/grobid:0.9.1-full` ~8 GB (deep learning). Full adds "2-4 points F1" on bibliographic reference parsing and "2-5 points" on citation-context identification; BidLSTM-CRF ref segmentation ~+1 F1 bioRxiv / +0.5 PMC. DL is "2-3 times slower overall"; "With a GPU (at least 4GB GPU memory required), the processing runtime is similar as with the CRF-only image with CPU only". RAM: 4 GB for full structuring, 6-8 GB for batch. (Grobid-docker page)
- Throughput: "10.6 PDF per second (around 915,000 PDF per day, around 20M pages per day)" on one 16-CPU, 32 GB machine (README). Low-profile 8-thread Linux: 4000 PDFs in ~26 min (~2.5 PDF/s); 0.8.2 benchmark 2000 PDFs in 1713 s on 16 CPU + GTX 1080 Ti; "around 120 pages per second" — these three from search-result snippets of grobid.readthedocs.io/en/latest/Introduction/ and benchmark pages, not fetched verbatim -> treat as **partly UNCONFIRMED**.
- TEI coordinates: `teiCoordinates` param; elements `ref, biblStruct, persName, figure, formula, head, s, p, note, title, affiliation`; format "page,x,y,w,h", page 1-indexed, PDF units, origin upper-left. https://grobid.readthedocs.io/en/latest/Coordinates-in-PDF/
- TEI content: "68 final labels" incl. footnotes, figure captions, tables, reference callouts with citation linking (README). Exact `<ref type="bibr" target="#b0">` syntax: **UNCONFIRMED** this session (not quoted in fetched pages).
- License: Apache 2.0 (code), CC-0 docs, CC-BY annotated data (README).
- Colab recipe: no official mention (README). **UNCONFIRMED** whether apt JDK 21 + `./gradlew` works on Colab; Docker is not available on Colab (general knowledge, **UNCONFIRMED** here).
- **Rec:** run GROBID `crf`-equivalent (CRF models, CPU) on Colab/Linux for the bulk pass, not on native Windows — Windows is explicitly unsupported and the laptop has no Docker.

## 2. Docling
- License MIT; "Works on macOS, Linux and Windows ... x86_64 and arm64"; features "page layout, reading order, table structure, code, formulas, image classification"; VLM option GraniteDocling; "Extensive OCR support for scanned PDFs". https://github.com/docling-project/docling . Current version number: **UNCONFIRMED**.
- Formula enrichment: `do_formula_enrichment=True` / `docling --enrich-formula`; model `CodeFormula` (ds4sd/CodeFormula); emits "LaTeX representation" (HTML export renders MathML). Picture classifier `DocumentFigureClassifier-v2.5`; picture description via Granite Vision / SmolVLM / API. https://docling-project.github.io/docling/usage/enrichments/
- Speed (standard pipeline, no OCR): CPU-only 1.5 p/s (RTX 5090 host) and 1.2 p/s (RTX 5070 Windows 11 host); GPU 7.9 p/s (5090), 4.2 p/s (5070), 3.1 p/s (L40S g6e.2xlarge). VLM GraniteDocling: 2.0-4.5 p/s on those GPUs. Recommended layout/OCR batch 64 (default 4). VRAM need **not stated** -> 4 GB sufficiency **UNCONFIRMED**. https://docling-project.github.io/docling/usage/gpu/
- DoclingDocument: `texts` (paragraph, heading, equation...), `tables`, `pictures`, `key_value_items`; `body` tree (reading order = body tree child order) and `furniture` (headers/footers); `groups`; "bounding boxes for all items, if available"; JSON-pointer refs. https://docling-project.github.io/docling/concepts/docling_document/ . Exact prov field names (`page_no`, `bbox`, `charspan`), bbox origin, TableFormer cell schema: **UNCONFIRMED** (not in fetched text).
- OCR engine list (EasyOCR/Tesseract/RapidOCR) and which is best on old scans: **UNCONFIRMED** — reference/OCR and installation pages returned 404.
- **Rec:** use Docling as the layout/table/figure engine on Colab CPU fan-out; at vendor CPU rates (1.2-1.5 p/s, different hardware) 7,400 pages ≈ 1.4-1.7 h single-process — arithmetic, not measured on Colab.

## 3. Math OCR
- **Marker** (datalab-to/marker): code Apache-2.0; weights "Modified AI Pubs Open Rail-M", free for research/personal/startups under $5M funding/revenue. Now runs against an inference server: vLLM (NVIDIA GPU; README says Docker + NVIDIA Container Toolkit) or llama.cpp `llama-server` (CPU). olmocr-bench: balanced GPU 76.0% @2.9 p/s; fast GPU 66.6% @7.4 p/s; fast no-OCR CPU 43.6% @23.7 p/s. Inline math -> LaTeX in balanced mode. VRAM: **not stated**. https://github.com/datalab-to/marker
- **Surya 2**: 650M-param VLM; code Apache-2.0, weights same Rail-M terms; math returned as `<math>` KaTeX LaTeX inline in page OCR; CPU via llama.cpp. Per-equation bbox: **UNCONFIRMED**. https://github.com/datalab-to/surya
- **MinerU 3.4 (2026-06-18)**: license changed from AGPLv3 to "MinerU Open Source License, a custom license based on Apache 2.0". Backends: pipeline (CPU-capable, min 4 GB VRAM, OmniDocBench v1.6 86.47), hybrid/vlm (GPU, 8 GB VRAM, 95.26-95.39). RAM min 16 GB, 32 GB rec. Windows supported, Python 3.10-3.12. https://github.com/opendatalab/MinerU . `content_list.json` equation blocks: `type:"equation"`, `text` (LaTeX), `text_format:"latex"`, `bbox` normalized 0-1000, `page_idx` 0-based; middle.json has block/line/span bboxes. https://opendatalab.github.io/MinerU/reference/output_files/ . Formula model name in 3.4: **UNCONFIRMED** (UniMERNet only in acknowledgments).
- **Nougat**: code MIT, weights CC-BY-NC; last commits 2025-02-21 and before that 2023-10-04 -> effectively unmaintained. README warns of false `[MISSING_PAGE]` on CPU/older GPUs; "Chinese, Russian, Japanese etc. will not work". https://github.com/facebookresearch/nougat , https://api.github.com/repos/facebookresearch/nougat/commits . Hallucination/repetition on scans: **UNCONFIRMED** from primary source.
- UniMERNet, Texify, pix2tex state/licenses: **UNCONFIRMED** (not checked; budget).
- LaTeX + per-equation bbox confirmed only for **MinerU** (content_list) and GROBID `formula` coordinates (GROBID formula content is not LaTeX — **UNCONFIRMED**).
- **Rec:** MinerU pipeline backend for equations (LaTeX + bbox + page, fits 4 GB/CPU, Windows, permissive-ish license) — but its 16 GB RAM minimum exceeds Colab free (~13 GB), so test one runtime first.

## 4. PyMuPDF / alternatives
- PyMuPDF 1.28.2; dual license "open-source AGPL and commercial" (Artifex). https://pymupdf.readthedocs.io/en/latest/about.html . AGPL obligations bite on conveying the software or offering it to users over a network; a private, undistributed research repo is generally unaffected — legal interpretation, **UNCONFIRMED / not legal advice**.
- pypdfium2: "Apache-2.0 / BSD-3-Clause"; bounded text extraction (`textpage.get_text_bounded(left,bottom,right,top)`), `get_text_range`, `page.render()` to PIL; prebuilt Windows wheels. https://github.com/pypdfium2-team/pypdfium2 . Per-char box API name and version: **UNCONFIRMED**.
- **Rec:** pypdfium2 for text/coords/rendering — no copyleft question if the repo is ever shared.

## 5. Embeddings
- BAAI/bge-m3: MIT, 1024-d, 8192 tokens, dense + sparse + ColBERT multi-vector in one model. https://huggingface.co/BAAI/bge-m3 . Param count: **UNCONFIRMED** on card fetch.
- nomic-embed-text-v1.5: Apache-2.0, 0.1B params, 8192 tokens, Matryoshka 768/512/256/128/64 (MTEB 62.28 at 768), needs `search_document:`/`search_query:` prefixes. https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
- allenai/specter2: Apache-2.0, SciBERT base, 512 tokens, input title[SEP]abstract, adapters proximity/adhoc_query/classification/regression; SciRepEval avg 71.1 vs SPECTER 67.5. Paper-level, not chunk-level. https://huggingface.co/allenai/specter2 . Dimension (768 implied by BERT-base): **UNCONFIRMED** on card.
- bge-large-en-v1.5, e5-large-v2, nomic-embed-text-v2, gte: **UNCONFIRMED** (not fetched). Scientific-retrieval benchmark (SciFact/SCIDOCS per model): **UNCONFIRMED**.
- pgvector constraint: HNSW/IVFFlat `vector` <= 2,000 d, `halfvec` <= 4,000, `bit` <= 64,000, `sparsevec` <= 1,000 non-zeros (HNSW). https://github.com/pgvector/pgvector . Every model above is <= 1024 d -> no constraint.
- **Rec:** bge-m3 dense (1024-d, 8192 ctx covers whole sections, MIT) as the chunk embedder; SPECTER2 optional for paper-to-paper similarity.

## 6. pgvector on Windows / PG18
- Current release **0.8.6 (2026-07-29)**; 0.8.7 unreleased. PG18: "Added support for Postgres 18 rc1" in 0.8.1 (2025-09-04); 0.8.2 (2026-02-25) "Improved install target on Windows", fixed EXPLAIN for PG18; 0.8.3 fixed a PG18 Hamming/Jaccard perf regression. https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md
- Windows install (README, as fetched): "Ensure C++ support in Visual Studio is installed"; run "x64 Native Tools Command Prompt for VS [version]" as administrator; build and install with `nmake /F Makefile.win`. README mentions no prebuilt Windows binary. The exact PGROOT-setting and install-target lines were not in the fetched text: **UNCONFIRMED**, read them on the page. Third-party prebuilt (e.g. EDB StackBuilder): **UNCONFIRMED**.
- Full-text search (tsvector/tsquery) is core Postgres; `pg_trgm` is a contrib module normally shipped with the Windows installer — both **UNCONFIRMED** this session (not fetched).
- **Rec:** build pgvector 0.8.6 with VS Build Tools against PG18; hybrid = tsvector/pg_trgm + HNSW, fused in SQL.

## 7. Postgres MCP servers
- crystaldba/postgres-mcp ("Postgres MCP Pro"): MIT; `--access-mode=restricted` = "read-only transactions and ... constraints on resource utilization (presently only execution time)"; pglast parsing rejects COMMIT/ROLLBACK to stop escaping the read-only txn; tools list_schemas, list_objects, get_object_details, execute_sql, explain_query (hypothetical indexes), get_top_queries, analyze_*; install `uvx postgres-mcp` / pipx / Docker. https://github.com/crystaldba/postgres-mcp . Version/date: **UNCONFIRMED**.
- hovecapital/read-only-local-postgres-mcp-server: SELECT-only validation. https://github.com/hovecapital/read-only-local-postgres-mcp-server (search snippet; maturity **UNCONFIRMED**).
- Secondary sources say the original reference Postgres MCP server is deprecated. https://tygartmedia.com/claude-code-postgres-mcp-setup/ (search snippet, **UNCONFIRMED** from Anthropic/modelcontextprotocol primary).
- **Rec:** postgres-mcp in restricted mode, connected as a Postgres role with only SELECT grants — two independent locks, since parser-based guards are defense-in-depth, not a guarantee.

## 8. Colab constraints
- Official FAQ: VMs "have a maximum lifetime enforced by the Colab service"; "Runtimes will time out if you are idle"; "dynamic usage limits that sometimes fluctuate". Free tier disallows "remote control (SSH/RDP), bypassing notebook UI ... distributed computing workers". https://research.google.com/colaboratory/faq.html — **relevant: headless multi-VM fan-out could be read as "bypassing the notebook UI"/"distributed workers"; check against the project's existing CPU fan-out practice.**
- Free CPU runtime 2 vCPU Xeon, ~13 GB RAM; free sessions max 12 h; idle disconnect ~90 min — secondary sources only (https://saturncloud.io/blog/whats-the-hardware-spec-for-google-colaboratory/ , https://joshthompson.co.uk/ai/google-colab-2026-guide-free-compute-automations-pro-tips/), **UNCONFIRMED** officially.
- Disk size, apt/Java install behavior, reported Docling/GROBID throughput on Colab: **UNCONFIRMED**.
- Implication (arithmetic, unmeasured): 2 vCPU is ~8x fewer threads than GROBID's 16-CPU benchmark and below Docling's benchmark hosts; measure on one runtime before sizing a fan-out.

## UNCONFIRMED list
1. GROBID on Java 23 (docs only say 21 or higher); GROBID build on Colab via apt JDK + gradlew.
2. GROBID `<ref type="bibr" target=...>` exact syntax; whether formula content is LaTeX; ~120 pages/s and 2.5 PDF/s figures (search snippets).
3. Docling version; OCR engine list and scan quality ranking; prov field names/bbox origin; TableFormer JSON schema; VRAM needs / 4 GB fit.
4. Marker/Surya VRAM; Surya per-equation bbox; whether Marker GPU mode works without Docker on Windows.
5. MinerU 3.4 formula model name; MinerU on 13 GB Colab RAM.
6. Nougat scan hallucination (primary source); UniMERNet, Texify, pix2tex state and licenses.
7. AGPL implications for a private repo (legal interpretation).
8. pypdfium2 version and per-char box API name.
9. bge-large-en-v1.5, e5-large-v2, nomic-embed-text-v2, gte specs; SPECTER2 dimension; bge-m3 params; any scientific retrieval benchmark per model.
10. Prebuilt pgvector Windows binaries; pg_trgm shipped with the Windows PG18 installer; exact PGROOT lines.
11. postgres-mcp version/date; deprecation of reference server (primary source); hovecapital maturity.
12. Colab free CPU specs, 12 h / 90 min limits, disk, apt/Java, tool throughput on Colab.
