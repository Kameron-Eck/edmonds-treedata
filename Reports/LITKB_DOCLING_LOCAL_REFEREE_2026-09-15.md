# Docling stage 3, local — INDEPENDENT REFEREE (litkb P4, gate 2)

**Date:** 2026-09-15 · **Referee:** a separate agent from the builder · **Contract:** CLAUDE.md
§3.4b, §3.4c ("the proposer never scores its own proposal")
**Under review:** `Reports/LITKB_DOCLING_LOCAL_2026-09-15.md`, worktree
`D:\edmonds-pipeline\treedata-docling`, branch `work/20260915-docling-local`, HEAD `afc052c`
**Method:** the frame set by `Reports/LITKB_GROBID_LOCAL_REFEREE2_2026-09-15.md` — reproduce
every load-bearing number from the artefacts, with the referee's OWN gold, and try to break it.

## Verdict — **STAGE 3 READY**, with five recorded defects, none of them in the adapter

Every gate reproduced against gold the referee read off the rendered pages, not off the
builder's fixtures or its test constants. Every timing reproduced inside 20% on a quieter
machine. Five source mutations fired with exactly the counts the report claims. The two
formula errors the builder marked UNCONFIRMED are **confirmed wrong**, and the three it called
correct are **confirmed correct** — by an independent reading of the rendered pages plus a
re-run that reproduced all five LaTeX strings byte-for-byte.

The defects are in the **pin**, the **report's OCR characterisation**, and two **stale or
false statements of fact inside the report**. A sixth item, N1, is a note about the referee
BRIEF rather than about the branch. **Nothing here blocks a merge**, and nothing is in the
adapter.

---

## 1. The pin does NOT reproduce the environment (defect D1)

Rebuilt from the file, not from the builder's venv:

```
py -3.12 -m venv <scratchpad>\venv-ref
<scratchpad>\venv-ref\Scripts\python.exe -m pip install -r Scripts\requirements-litkb-extract.txt
```

| package | builder's venv | rebuilt from the pin | |
|---|---|---|---|
| docling | 2.127.0 | 2.127.0 | same |
| **docling-core** | **2.96.0** | **2.96.1** | **DRIFTED** |
| docling-parse / -ibm-models | 7.19.1 / 4.0.2 | 7.19.1 / 4.0.2 | same |
| torch / torchvision | 2.14.0+cpu / 0.29.0 | 2.14.0+cpu / 0.29.0 | same |
| transformers / numpy | 5.17.0 / 2.5.3 | 5.17.0 / 2.5.3 | same |
| rapidocr / pypdfium2 / psutil | 3.9.2 / 5.13.0 / 7.2.2 | 3.9.2 / 5.13.0 / 7.2.2 | same |

`torch.__version__` is `2.14.0+cpu` and `torch.cuda.is_available()` is `False` in **both**
venvs (`pip list` prints the bare `2.14.0`; the `+cpu` local label is only on the dunder, which
is why it is worth stating which one was read).

**The drift is the point.** The file pins three packages — `docling`, `psutil`, `pypdfium2` —
and names every other version in a COMMENT. A comment constrains nothing, so `docling-core`
moved 2.96.0 → 2.96.1 **within the same day**. The report's §7.1 asks a referee to "rebuild from
the pin and check the versions match before trusting the timings": they do not all match, and
on a machine rebuilt next month they will match less. This is a requirements file, not a lock
file. **Fix:** `pip freeze` the builder's venv into the file, or add a second locked file
beside it. Nothing downstream is wrong — but the claim "changing one changes the numbers in
that report, so it is a re-measurement, not an upgrade" is not enforced by the artefact that
makes it.

**All timings below were run in the REBUILT venv**, so they measure the pin as a referee would
get it, drift included.

---

## 2. Gates reproduced, with the referee's own gold

### 2.1 Reading order — **PASS**

Three paragraph openings read off the rendered `Benedek_2015` page 2 (`render(scale=3)`),
deliberately NOT the three in `BENEDEK_P2_ORDER`:

| # | referee's snippet | where on the page | order_index returned |
|---|---|---|--:|
| 1 | `Another important point of view is distinguishing` | left column, head of §1.1.2 | **34** |
| 2 | `Differences between approaches can also be taken regarding the` | left column, foot, §1.1.3 | **36** |
| 3 | `Since conventional MRFs show some limitations` | **right** column, mid | **40** |

Strictly increasing, zero violations. The third snippet sits GEOMETRICALLY ABOVE the second —
that is what makes it a test rather than a formality: re-indexed by `geometric_order()` the
same three come back `38, 30, …` and `reading_order_violations` fires. The gate and its kill
both reproduce on gold the builder never saw.

*(First attempt used a snippet that turned out to be in the same paragraph as snippet 1 — both
resolved to order 34 and the check reported a violation. That is the check behaving correctly,
and it is worth recording that a tie is treated as a violation, not as a pass.)*

### 2.2 Table cells — **PASS**, and the `Method` hole is real

Eleven values read off the rendered page 14, none of them the builder's eight:

* **Table 2** (8 × 10, 73 cells): `(1,4)=F-A`, `(3,2)=1.98`, `(4,9)=11.87`, `(5,6)=6.38`,
  `(6,8)=3.06`, `(7,9)=8.66` — **all six correct**.
* **Table 3** (7 × 4, 28 cells): `(1,1)=21.7`, `(2,3)=23.5`, `(3,2)=35.5`, `(4,0)=MLP`,
  `(5,3)=43.8` — **all five correct**.

`table_cell_errors` returns `[]` for both gold sets. The row-span hole is confirmed exactly as
reported: `at(0,0)` is `Method` with `row_span=1`, and **`at(1,0)` is `None`** while the page
shows `Method` spanning both header rows. Stage 5 must not assume a dense grid; the report says
so and is right.

### 2.3 OCR — **PASS on the gate, but the report UNDERSTATES the damage (defect D2)**

Title: the first non-empty block is `STATISTICAL INFERENCE ABOUT MARKOV CHAINS`, label
`section_header`, **page 1**. The referee's own render of page 1 confirms the title IS on page 1
(no JSTOR cover sheet; the folio reads `89`). The report's correction of the brief's "page 2" is
correct.

**The 100-word transcription.** The referee transcribed the first 100 words of the Summary from
the page image before reading any OCR output, then diffed:

| | |
|---|--:|
| gold words compared | 94 (the 100th fell mid-token) |
| gold words wrong or missing | **13** |
| **word error rate** | **13.8%** |
| of which, inside ONE contiguous dropout | **12** |
| outside that dropout | 1 (`χ²` → `x²`) |

*(A first pass of this diff reported 24.5%. It counted ten words of slice overhang — the OCR
window ran past the 94th gold word — as errors. 13.8% is the corrected figure; the dropout
below is unaffected by it.)*

The dropout is the finding. Where the page reads

> *…of a first order chain **are constant, (b) that in case the transition probabilities are
> constant, they are** specified numbers…*

the OCR'd block reads

> `…of a first order chain aorae nt Gtnt e sn nt  ea  tt ( Gtt are specified numbers…`

**Twelve words of the abstract are replaced by ten tokens of gibberish that is still
word-shaped.** That is a different failure from the report's `usualiy` / `sncreases` /
`x²`-for-`χ²` list. Those are per-character slips a fuzzy quote matcher survives; this is
**silent content loss inside a block that otherwise reads cleanly**, with no marker, no
confidence drop at block level (there is no block-level confidence), and a `mean_grade` of
`excellent` on the page. The report's §4.3 sentence — "OCR quality on a 1957 letterpress scan
is good but not clean" — is true of 86% of the words and false of the passage that matters.

**Scored on the referee's OWN run, not on the builder's fixture** (CLAUDE.md §3.4c), and
**deterministic**: the 22-page OCR batch re-run in the rebuilt venv produced the identical
`aorae nt Gtnt e sn nt  ea  tt ( Gtt`, so this is a reproducible property of rapidocr+torch on
this page rather than a one-off sampling artefact. **Fix:** say in §4.3 that a contiguous
12-word clause was destroyed, and state the measured word error rate rather than three example
typos. The downstream consequence the report draws
(an exact-match quote gate would reject true quotes) is correct but too weak: a quote gate over
this text can also find a *plausible-looking* string that the page never said.

### 2.4 Formula LaTeX — builder's UNCONFIRMED readings are **CONFIRMED**

Re-ran enrichment on Bellettini pp. 3–4 in the rebuilt venv. **All five LaTeX strings came back
identical to the report's §6.1**, character for character. Read against the referee's own
render of pages 3 and 4 (scale 4):

| # | page | referee's reading of the rendered page | verdict |
|---|--:|---|---|
| 1 | 3 | `u(t,x) = (1 − λ_C t)⁺ χ_C(x), λ_C := P(C)/|C|` | **correct** |
| 2 | 3, eq. (5) | page reads `ess sup` with **`p ∈ ∂C` set under it**; LaTeX has `\text{ess sup }` and no subscript | **WRONG — subscript lost** |
| 3 | 4 | page reads `… ⊆ E ⊆ ℝ² **\** ⋃_{j=k+1}^{m} C_{i_j}`; LaTeX has `\mathbb{R}^{2} \rangle \ \bigcup` | **WRONG — set difference read as `\rangle`** |
| 4 | 4, eq. (6) | `P(E_{i_1,…,i_k}) ⩾ Σ_{j=1}^{k} P(C_{i_j}).` | **correct** |
| 5 | 4, eq. (7) | `min_{u∈L²(ℝ²)∩BV(ℝ²)} { ∫_{ℝ²} |Du| + (1/2λ) ∫_{ℝ²} (u−f)² dx },` | **correct** |

Three of five right, two silently wrong — **exactly as the builder reported**, now independently
scored. Both errors produce LaTeX that parses and renders; neither is detectable without the
page. The report's rule ("treat them as a candidate, not a fact") is the right one.

---

## 3. Timing reproduced — all three inside 20%

**Ambient load, recorded before each batch** (the referee's threshold, fixed before running:
< 30% system CPU and no foreign pytest campaign): **13.9%** over a 5 s sample, 13 python
processes of which 10 idle MCP servers. The builder's own cpu-t4 batch ran at 34% → 61%.
**The config-A and OCR batches are clean** — each ran in the foreground with nothing else of the
referee's in flight. **The formula run is CONTENDED and is marked as such below**: the mutation
sweep of §5, the zero-block probe and the tail of `qc/check.py` all shared the machine with it.

**Config A, `num_threads=4`, CPU, tables on, OCR off — rebuilt venv**

| paper | pages | referee s | referee p/s | builder p/s | peak RSS MB | body blocks (ref / builder) |
|---|--:|--:|--:|--:|--:|---|
| Benedek 2015 | 16 | 28.66 | 0.558 | 0.481 | 1,719 | 377 / 377 |
| Alwan 1988 | 10 | 13.50 | 0.741 | 0.601 | 1,835 | 157 / 157 |
| Anderson 1957 | 22 | 28.04 | 0.785 | 0.741 | 2,007 | 1 / 1 |
| Bellettini 2002 | 51 | 62.42 | 0.817 | 0.789 | 2,044 | 819 / 819 |
| Schneider 2008 (pp. 1–100) | 100 | 126.02 | 0.794 | 0.737 | 2,621 | 1,011 / 1,011 |
| **aggregate** | **199** | **258.6** | **0.769** | **0.711** | **2,621** | |

**0.769 vs 0.711 p/s = +8.2%** — inside 20%, on a machine at 14% ambient rather than 34–61%.
**DETERMINED: reproduced.**

**OCR, Anderson 1957, engine `auto`:** 22 pages in **199.45 s = 0.110 p/s**, peak 2,397 MB,
**179 body blocks**. Builder: 234.08 s, 0.094 p/s, 179 blocks. **+17.3% — inside 20%,
DETERMINED: reproduced.** OCR is 7.0× slower than the same file without it (referee), 7.9×
(builder); both say the same thing.

**Formula, pp. 3–4 — CONTENDED (see the load paragraph above):** 2 pages in
**417.97 s = 0.0048 p/s**, peak 2,249 MB. Builder: 161.5 + 235.4
= 396.9 s for the same two pages. **+5.3% — reproduced**, and the "120–190× slower" claim holds:
0.769 / 0.0048 = **160×**.

**The body-block counts are identical in all six rows.** That is the strongest single piece of
corroboration here: the same pipeline, rebuilt from the pin with a drifted `docling-core`,
produced the same document structure on five papers.

---

## 4. The canonical frame — referee's own pypdfium2 census

Three pages, one of them cropped, with the referee's own needles:

| PDF, page | mediabox | cropbox | dx, dy | docling page size | needle (whole element) | offset | contained |
|---|---|---|---|---|---|--:|---|
| Benedek p1 | (0,0,595.276,793.701) | identical | 0, 0 | 595.276 × 793.701 | *(title: not unique → reported as `None`, not a silent pass)* | — | — |
| Benedek p2 | same | identical | 0, 0 | 595.276 × 793.701 | `1.1.2. Supervised and unsupervised models` | **1.113 pt** | yes |
| Benedek p2 | " | " | " | " | `1.1.3. Targeted scenarios` | **1.113 pt** | yes |
| **Alwan p2 (CROPPED)** | (0,0,612,792) | (10.345,10.777,603.441,782.948) | **10.345, 9.052** | **593.096 × 772.171** | `1. INTRODUCTION` | **3.446 pt** | yes |

**Max component offset across the referee's census: 3.45 pt**, under the builder's 5.52 and well
under the 8 pt tolerance.

* **The cropbox claim is measured, not assumed.** Docling's page size for Alwan p2 equals the
  cropbox extent to three decimals and differs from the mediabox. Against a MEDIABOX-based
  character-box union the same block is **11.02 pt** out — past tolerance. The frame is the
  cropbox.
* **`dy = media[3] − crop[3]` is the right shift for a top-left frame** (792 − 782.948 = 9.052),
  and `dx = crop[0] − media[0]` = 10.345. Confirmed by the 3.45 pt agreement after the shift and
  the 11.02 pt disagreement without it.
* **The y-flip is right**, and its removal is caught (§5, M1/M2).
* **The degenerate-first-character quirk is real and reproduced exactly.** On Benedek p1 the
  `1` of `1. Introduction` returns `(561.0, 326.6, 561.0, 326.6)` — the referee called
  `get_charbox` directly and got the builder's number to one decimal. The `I` of `Introduction`
  is degenerate too, so this is a property of run starts generally, not one glyph. Dropping
  zero-area boxes is correct and is not a fudge: without it the string's box inflates by ~458 pt
  and the alignment check reports a frame error that does not exist.

---

## 5. Kills — five source mutations, re-applied in the referee's own words

Baseline on `afc052c`: **25 passed, 3 skipped** (matches the report). Each mutation applied by
the referee, suite run, `git checkout --` between; final `git status --short` clean of source.

| referee's mutation | edit | result |
|---|---|---|
| **M1 — the y-flip is deleted** | `y0, y1 = page_height - top, page_height - bottom` → `y0, y1 = top, bottom` | **3 failed** |
| **M2 — the `coord_origin` field is never read** (every box treated TOPLEFT) | `if origin.endswith("BOTTOMLEFT"):` → `if False:` | **3 failed** |
| **M3 — the cropbox shift is zeroed** | `dx, dy = f["dx"], f["dy"]` → `dx, dy = 0.0, 0.0` | **1 failed** |
| **M4 — only the first prov box survives** | `provs = item.get("prov") or []` → `…[:1]` | **1 failed** |
| **M5 — `Table.at` stops filling spans** | span-range test → `if c.row == row and c.col == col:` | **1 failed** |

Counts identical to the report's sweep. M2 is worth naming separately: it is the mutation that
tests the claim the module docstring makes most loudly — that both coordinate origins coexist in
one JSON file and the adapter must branch on the FIELD. It fires.

### 5.1 The zero-block gate does miss the JSTOR scan — and the report's account of WHY is wrong

Re-ran `Anderson_1957` with OCR **off**. `check_text_blocks` returns **1** and does not raise.
Confirmed: the gate misses it.

But the surviving body block is **not** the JSTOR boilerplate. It is a single character:

```
page 1, kind=text, layer=body, text='®'
```

— the registered-trademark glyph from the JSTOR logo. The report says "that run returns one body
block (the JSTOR boilerplate)". **It does not** (defect D3). This matters in one direction: a
trivial body-character floor (say ≥ 200 characters of body text) would catch *this* file, which
the report's "one is ≥ 1, so it passes" framing implies nothing cheap can. The report's
conclusion — that the fix belongs to stage 0 — is still right, because a character floor alone
would not catch a scan whose text layer holds a real paragraph of front matter.

**What stage 0 must provide to close it.** A per-page text-layer census read from the PDF, not
from docling. Prototyped by the referee in five lines and **shown to fire on this file**:

```python
doc = pdfium.PdfDocument(pdf)
chars = [len((doc[i].get_textpage().get_text_range() or "").strip()) for i in range(len(doc))]
# Anderson_1957: 22 pages, 1 page with any text, 166 characters total, 7.5 chars/page
```

| statistic | Anderson 1957 | a floor that fires |
|---|--:|---|
| pages | 22 | — |
| pages with any text layer | **1** | text-page fraction **0.045** < 0.5 → FIRES |
| total characters | **166** | — |
| characters per page | **7.5** | < 100 → FIRES |

Stage 0 needs to record all four and refuse — or force OCR — when either floor trips. The
report's numbers for this file (22 pages, 1 with text, 166 characters) are confirmed exactly.

---

## 6. GPU feasibility — documentation only, nothing installed

**A compatible CUDA wheel exists.** Constraints, read from the installed metadata:
`docling` pins no torch at all; `docling-ibm-models` requires `torch<3.0.0,>=2.2.2`;
**`torchvision 0.29.0` requires `torch==2.14.0` exactly**, so the CUDA build must be torch
**2.14.0**, not a newer one.

Querying PyTorch's own wheel indexes (read-only HTTP, no download):

| channel | `torch-2.14.0+<ch>-cp312-cp312-win_amd64.whl` | `torchvision-0.29.0+<ch>-…` |
|---|---|---|
| cu126 | **present** | — |
| cu128 | absent | — |
| cu129 | absent | — |
| **cu130** | **present** | **present** |

**The card:** `nvidia-smi` reports `Quadro T2000, driver 581.42, 4096 MiB total, 955 MiB in use,
compute capability 7.5` — Turing, sm_75, ~3.1 GB free. Per PyTorch's 2.14 CUDA support matrix
discussion and NVIDIA's CUDA 13 notes, **CUDA 13.x drops Maxwell/Pascal/Volta and supports
Turing (sm_75) upward**, so `cu130` covers this card; `cu126` is the legacy fallback and also
covers it.

**VRAM expectation, from the measured weight sizes only — NOT tested:** layout (`docling-layout-heron`)
164 MB + TableFormer (`docling-models`) 342 MB ≈ 0.5 GB of fp32 weights, comfortably inside
3.1 GB with room for activations at these page sizes. **CodeFormulaV2 at 611 MB is the marginal
one**: it is autoregressive, so its KV cache grows with the decoded sequence, and 4 GB total
with ~0.9 GB already resident is not a lot of headroom. The honest statement is that layout +
tables on GPU is very likely to fit and formula enrichment on GPU is **UNDETERMINED until
measured**.

**Recommended wording change (defect D4, cosmetic):** §3.2 says "Docling itself supports CUDA;
this installation does not have it." True, and it should now add that the replacement wheel is
`torch==2.14.0+cu130` with `torchvision==0.29.0+cu130`, that the card is sm_75 and in support,
and that swapping it **re-pins the requirements file and invalidates every number in §3** —
which is the real cost, not the availability.

---

## 7. Stale text and branch hygiene

* **Defect D3b — `§7.4` of the report is stale.** It reads "The book was measured on its first
  100 pages, not all 688." Commit `afc052c` added the full 688-page row to §3 and rewrote §3's
  prose accordingly, but left the blocker list untouched. One line to delete. (The referee did
  not re-run the 688-page book; §3's row and its 4.12 GB peak are accepted on the CSV and on the
  100-page row's peak RSS reproducing to under 1%.)
* **N1 — the brief's `litkb_test_w5` has no mechanism here, and this is a note about the
  BRIEF, not a defect in the branch.** Checked, not inferred: `pipeline/litkb/db/connect.py`
  sets `DB_TEST = "litkb_test"` with **no environment override**; `grep` finds **no reference
  to `litkb_test_w*` anywhere in this worktree**; and `git show main:Scripts/pipeline/litkb/db/connect.py`
  fails because **`main` does not carry the litkb tree at all**. The server does hold
  `litkb_test_w1 … litkb_test_w9`, but they are created by something outside this worktree —
  most plausibly the 9-worker mutation harness the brief names — not by a per-worktree
  mechanism this branch could use. This branch's `qc/conftest.py` states the opposite design in
  its own docstring: the suite logs in "ONLY as litkb_test, to litkb_test, under the advisory
  lock (parallel worktrees serialise)". Sharing one database is deliberate here.

  The residual risk is real but narrower than a merge blocker: the advisory lock serialises
  concurrent suites, yet `migrate.reset()` still destroys whatever is in `litkb_test` when it
  acquires the lock, so a session holding state there loses it. Because the brief restricted
  this review to `litkb_test_w5` and no code path reaches that name, the referee ran the ladder
  with `LITKB_PGPORT=1`: every PG fixture skipped on "connection refused" and **no database was
  opened, read or written by this review**. The cost is recorded above — 216 litkb Postgres
  tests went unexercised, and a merge reviewer must run them.
* **`qc/check.py --fast`, run with `LITKB_PGPORT=1`: one failure, and it is the expected one.**
  `1 failed, 2217 passed, 224 skipped in 988.9 s`; the single failure is
  `qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, pre-existing and
  unrelated to stage 3 — the one failure the brief named. **216 litkb Postgres tests skipped**
  as a direct consequence of N1 —
  those guards were **not** exercised by this referee, and a merge reviewer must run them
  against a database they are willing to have reset.
* **`git log -p 4256e4e..afc052c` (3 commits): no secrets.** The only hits for
  `password|secret|key|token` are the prose and docstrings describing the
  `D:\edmonds-pipeline\secrets\` **directory shadowing the stdlib `secrets` module** — a real
  and well-documented trap, not a credential. `qc/secrets_check.py`: **clean, 1,195 indexed
  files.**
* Working tree after the mutation sweep holds only this report.

---

## 8. What the referee did NOT check

1. **The 688-page book run** (995.9 s, 4.12 GB peak). Accepted on the CSV row plus the
   100-page row of the same file, whose **peak RSS reproduced to under 1%** (2,621 vs
   2,641 MB); its wall clock is 7% faster here (126.0 vs 135.7 s), consistent with the lower
   ambient load rather than with a different pipeline. The pool-sizing conclusion — size on the longest document,
   not the median — follows from 2.6 GB at 100 pages vs 4.12 GB at 688 and is not disputed, but
   it rests on **one** long document.
2. **Parallel workers.** The report says the memory is per worker and does not measure a pool.
   Still not measured. Four workers at 4 GB each is 16 GB and ~14 cores on a 12-core machine —
   the CPU, not the RAM, is the binding constraint, and nobody has measured it.
3. **`num_threads=8`.** The referee reproduced only config A; the 7%-for-1.9×-CPU conclusion is
   accepted on the builder's CSV.
4. **Any GPU run.** Documentation and `nvidia-smi` only, as the brief required.
5. **Postgres.** Nothing was touched (see D5). `extraction_runs.metrics` remains unbuilt, the
   same gap the GROBID referee recorded, and the `NaN` normalisation problem in §7.8 remains
   real and untested.

---

## 9. Defects, in the order they should be fixed

| | defect | severity | fix |
|---|---|---|---|
| **D2** | §4.3 understates OCR damage: a contiguous 12-word clause is replaced by word-shaped gibberish; measured WER **13.8%** over 94 gold words, and deterministic | **high** — it is the basis of a downstream quote rule | state the dropout and the rate |
| **D1** | the pin constrains 3 packages and comments the rest; `docling-core` drifted 2.96.0 → 2.96.1 in one day | medium | freeze, or add a lock file |
| **D3** | the one surviving OCR-off body block is `®`, not the JSTOR boilerplate | low, but it is a stated fact that is false | correct it; note a character floor would catch this file |
| **D3b** | §7.4 still says the book was measured on 100 pages | low | delete the line |
| **D4** | §3.2 does not name the wheel that would work | cosmetic | name `torch==2.14.0+cu130` / sm_75 |
| **N1** | not a branch defect: the brief's `litkb_test_w5` has no code path; the suite is designed to share `litkb_test` under an advisory lock | note | decide whether per-worktree databases are wanted; 216 PG tests remain unexercised here |

None of these is in `litkb/extract/docling.py` or `docling_worker.py`. The adapter, its frame
handling, its refusals and its tests all survived everything the referee threw at them.

**Sources for §6:** [pytorch/pytorch#190385 — CUDA support matrix](https://github.com/pytorch/pytorch/issues/190385) ·
[pytorch/pytorch#159779 — Enable CUDA 13.0 binaries](https://github.com/pytorch/pytorch/issues/159779) ·
[NVIDIA Turing Compatibility Guide](https://docs.nvidia.com/cuda/turing-compatibility-guide/index.html) ·
`https://download.pytorch.org/whl/{cu126,cu128,cu129,cu130}/`
