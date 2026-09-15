# Docling "decision A" — independent referee (equation-density gate + CUDA trial)

**Date:** 2026-09-15 · **Worktree:** `D:\edmonds-pipeline\treedata-docling`, branch
`work/20260915-docling-local`, HEAD **7e2fa40** · **Contract:** CLAUDE.md §3.4b, §3.4c
**Under review:** `Reports/LITKB_DOCLING_LOCAL_2026-09-15.md` §8 ("Decision A implemented")
**Referee:** an agent that did not build the gate and did not choose the cut.

Everything below was re-run by this referee on this laptop. Reproductions were computed into
a scratchpad, never into the builder's tracked evidence CSVs; the builder's
`Reports/litkb_equation_density_2026-09-15.csv` and
`Reports/litkb_docling_throughput_2026-09-15.csv` are untouched, and `git diff --stat` on the
adapter was clean after every mutation. `D:\edmonds-pipeline\Literture` was read only.

**VERDICT: the gate and the CUDA trial are ACCEPTED, with two numbers corrected downward.**
Every load-bearing number in §8 reproduced. The two corrections are (a) the gate's precision
against *hand* truth is **0.87**, not the 0.974 the four gate papers report, and (b) the corpus
formula projection rests on a regions-per-page figure this referee measured at **4.24**, not
5.16. Neither changes the decision; both change the hours. The one thing §8.2 marked
**UNVALIDATED** — the fail-closed kill on a real out-of-memory — this referee **fired on real
data**, and it closes correctly.

**Ambient state, recorded before every timing** (CLAUDE.md: other agents run on this machine).
GPU is a Quadro T2000, 4,096 MiB, WDDM, driving the display. Idle VRAM baseline **226 MiB**
across the session (the builder's baseline was 901 MiB — other sessions' work). System CPU
before the layout batch **57%**, before the formula batch **30%**; 12 logical cores. The
referee's ambient CPU load was *higher* than the builder's (21–27%), not lower.

---

## 1. Density gate — the census reproduces EXACTLY

`litkb.extract.docling.page_densities` re-run over the census scope (`ASPP`, `Labeling`,
`Validation`, `other`; `_litkb_staging` and `_quarantine` excluded), writing to scratch:

| | builder | referee |
|---|--:|--:|
| PDFs | 219 | **219** |
| pages | 4,655 | **4,655** |
| pages with no text layer | 86 | **86** |
| pages above the 0.05 cut | 1,571 (33.8%) | **1,571** |

Joined row-by-row on `(file, page)` against the tracked CSV: keys identical, **0 density
mismatches** at 1e-9. The census is deterministic and correctly reported.

### 1.1 The recall/precision table reproduces exactly

Recomputed against docling's layout `formula` labels over the same four text-layer gate papers
(**177 pages, 655 regions** — both counts reproduce):

| cut | recall | precision | regions captured |
|--:|--:|--:|--:|
| 0.01 | 0.978 | 0.918 | 652/655 |
| 0.02 | 0.949 | 0.978 | 645/655 |
| 0.04 | 0.877 | 0.976 | 620/655 |
| **0.05** | **0.804** | **0.974** | **588/655 = 89.8%** |
| 0.06 | 0.732 | 0.990 | 549/655 |
| 0.10 | 0.522 | 1.000 | 406/655 |

Every published figure — 0.804, 0.974, 588/655, 89.8%, 5.16 regions per dense page — matches to
three decimals. The report's arithmetic is sound.

### 1.2 Challenging the target: 30 hand-labelled pages

The brief's concern is that the evaluation is partly self-referential, since docling's own
layout labels are what the gate is scored against. Test: 30 pages drawn seeded
(`random.Random(20260915)`) from the census, 15 above the cut and 15 below, **rendered to
anonymised PNGs** (`p00.png … p29.png`, shuffled) and labelled by eye — *does this page carry a
display equation?* — **before** the density or the filename was unblinded.

| | hand YES | hand NO |
|---|--:|--:|
| **selected** (d > 0.05) | 13 | **2** |
| **not selected** | **2** | 13 |

* **Precision against hand truth = 0.867** (13/15). Precision is directly estimable from the
  above-cut stratum and needs no reweighting.
* **Recall**, stratum 0.867; **reweighted by stratum size** (1,571 above / 2,998 text-bearing
  below — the 86 no-text pages were excluded from the sampling frame) = **0.773**. A
  15-per-stratum draw makes this interval very wide — it is consistent with the
  published 0.804 and cannot distinguish the two.

**The two false positives are a real class, and the brief predicted it.** `Solberg_1996` p9
(d=0.167) is two dense numeric TABLES with `±` values; `Pauls_2025` p8 (d=0.105) is a FIGURE
page of scatterplots whose panel labels are `R² = 0.819` and similar. The 12-character
line term reads a table cell and an axis label the same way it reads a broken display-equation
fragment. The false negatives are `Psarakis_2007` p14 (d=0.032) and `Bacry_2015` p36 (d=0.024) —
pages with one or a few display equations set in a page of prose.

**And this is the finding that answers the self-reference worry.** This referee ran docling's
layout pass on all four disagreement pages:

| page | hand truth | density gate | docling layout `formula` regions |
|---|---|---|--:|
| Solberg_1996 p9 | no equation | selected | **0** |
| Pauls_2025 p8 | no equation | selected | **0** |
| Psarakis_2007 p14 | has equations | rejected | **3** |
| Bacry_2015 p36 | has equations | rejected | **1** |

**The layout target agrees with hand truth on every one of the four.** Where the gate is wrong,
the layout labels say so too. The evaluation is therefore *not* inflated by self-reference — the
target is a good proxy for truth on exactly the pages that matter. What the 0.974 figure
overstates is something simpler and less interesting: **the four gate papers are not the
corpus.** On a corpus-wide draw the gate's precision is ~0.87, roughly a 13% false-positive rate,
and those FPs are table and figure pages. That costs hours (regions that are not there decode in
zero time, but the pages are still enriched), not correctness.

### 1.3 The ToUnicode rescue holds on three other math-font papers

The builder's claim is that on a paper with a broken Type-1 encoding the LINE terms, not the
math-character term, carry the signal. Probe: rank the corpus by mojibake rate (`¼`, `ð`, `Þ`
per non-space character over the first 12 pages), then re-run the census on the top papers with
`_is_math_char` forced to return `False` — line terms alone.

| paper | mojibake rate | pages selected, full | pages selected, line terms only |
|---|--:|--:|--:|
| `Leung_2004b` | 0.0453 | 19 | **19** |
| `Leung_2004a` | 0.0248 | 10 | **10** |
| `Kolmogorov_2004` | 0.0193 | 5 | **5** |
| `Bellettini_2002` (the builder's case, for reference) | 0.0403 | 48 | 47 |

**100% retained on all three.** On broken-encoding papers the math-character term contributes
essentially nothing and the line terms do all the work. The builder's justification for the two
line terms generalises beyond the single paper it was discovered on. (Note also that
`Leung_2004b` outranks Bellettini on mojibake — the class is larger than one paper.)

### 1.4 A knife-edge population the report does not mention — minor defect

`Bellettini` p3 scores **0.0501** against a cut of 0.05 with a strict `d > cut`: the builder's own
gold page clears by one part in ten thousand. Counted from the census: **206 corpus pages lie in
[0.045, 0.055]**, 13% of everything the gate selects. Any change to pypdfium2's line breaking
moves them across. This is not an error — the cut is a policy choice and the curve is published —
but a reader should know the selection near the cut is not stable, and the gold page that
anchors the test is the least stable member of it.

---

## 2. Mutations — all five fire; no defect

Method: mutate `pipeline/litkb/extract/docling.py`, run `qc/test_litkb_docling.py`
(`LITKB_PGPORT=1`), restore, re-run. Baseline: **37 passed, 3 skipped**.

| mutation | result |
|---|---|
| `EQUATION_DENSITY_CUT = 0.0` | **2 failed** (incl. `test_the_cut_meets_its_stated_recall_and_precision`) |
| `EQUATION_DENSITY_CUT = 1.0` | **3 failed** |
| **drop the equation-number line term** (`_EQ_NUMBER.search(ln) or …` removed) | **2 failed** |
| drop the display-fragment line term (`DISPLAY_FRAGMENT_CHARS = 0`) | **2 failed** |
| `_EQ_NUMBER` widened to four digits (a reference year becomes an equation number) | **1 failed** — `test_a_reference_year_at_a_line_end_is_not_an_equation_number` |

The brief asked whether a mutation that drops the equation-number line term escapes the suite.
**It does not** — the gate fires, so there is no defect and **no new test was needed**. The
adapter was byte-identical after the sweep (`git diff --stat` empty).

---

## 3. GPU — reproduced, and the VRAM reading needs correcting

Same instrument, same five papers, CUDA venv, `--threads 4`, CSV redirected to scratch.

| | builder | referee | agreement |
|---|--:|--:|---|
| layout + tables, 199 pp | 46.58 s, **4.272 p/s** | 51.57 s, **3.859 p/s** | −9.7%, inside ±20% |
| body blocks (5 papers) | 377/157/1/819/1011 | **identical** | exact |
| formula, Bellettini pp. 3–4, 5 regions | 42.52 s, **0.047 p/s** | 40.33 s, **0.0496 p/s** | +5.5% |
| formula peak VRAM | **3,918 MiB** | **3,917 MiB** | exact |

Rates reproduce and the documents are identical, which is the corroboration that matters more
than the rate. The layout shortfall is explained by ambient load (57% vs 21%).

**The "178 MiB of headroom" reading is wrong, and this is the referee's substantive correction
to §8.3.** The builder measured a 901 MiB baseline and a 3,918 MiB peak, and read the 178 MiB
gap as the margin before an OOM. This referee measured a **226 MiB baseline — 675 MiB more free
VRAM — and the peak was 3,917 MiB**. Device-wide peak minus baseline was **+1,383 MiB** for
layout (builder: +1,482) but **+3,691 MiB** for formula (builder: +3,017). The delta is not a
constant, so it is not a requirement.

*Measured:* the two peaks, 1 MiB apart, from baselines 675 MiB apart. *Inferred:* why. **Two
mechanisms fit and this referee did not separate them** — either CodeFormulaV2's PyTorch caching
allocator expanded into whatever was free, or the card saturates near 3.9 GiB and WDDM demoted
the other tenants' allocations to shared system memory when the CUDA job asked. **The conclusion
is the same under both**: the peak measures device saturation, not the job's requirement. The
consequence:
the ~178 MiB gap is not slack that a second process could be denied, and it is not evidence that
the job needs 3.9 GB. Section 4 below establishes what it actually needs.

---

## 4. The fail-closed kill — FIRED on a real OOM. §8.2's UNVALIDATED caveat is CLOSED

§8.2 states, correctly and in the right words, that the three fail-closed tests are synthetic
documents and therefore validate the code, not the claim. The claim is now validated.

**Method.** The worker is spawned with `-P` only, not `-I`, so `PYTHONPATH` survives. A
scratchpad `sitecustomize.py` calls `torch.cuda.set_per_process_memory_fraction(f, 0)` inside the
worker process before any model loads. Two fractions were run against the real
`extract(..., formulas="auto", pages=[3,4])` path on the real Bellettini PDF.

**Control, no cap:** `status="ok"`, `formula_patched=5`, `formula_missing=0`, five LaTeX strings
in the output. §8.2's end-to-end auto result reproduces independently.

**f = 0.40 (≈1.6 GiB, enough for layout, not for CodeFormula):**

```
RAISED litkb.extract.docling.FormulaEnrichmentFailed
  5 of 5 formula regions on enriched pages came back with no LaTeX — refusing to
  record a half-enriched run (first: page 3, #/texts/5)
metrics.status: failed   error: 5 formula regions without LaTeX
```

**The mechanism, read off the worker's own stderr rather than inferred.** The base pass
succeeded. The enrichment pass hit a genuine allocator failure —

> `Error processing code/formula batch: CUDA out of memory. Tried to allocate 76.00 MiB.
> GPU 0 has a total capacity of 4.00 GiB … 1.60 GiB allowed`

— and **docling caught it internally, per batch, and carried on.** The conversion reported
`SUCCESS`. Every formula item kept its native text. A caller that trusted docling's status would
have written five empty/mojibake strings into a `latex` column and recorded the run as enriched.
`merge_formula_latex` saw five regions whose text had not moved, and `extract` refused the run.
**This is precisely the failure the gate was written for, it happened for the stated reason, and
the named class is the one that fires.** Never an empty LaTeX recorded as success.

**f = 0.15 (≈600 MiB, below the 611 MB weights):** the worker dies at warm-up and `run()` raises
`DoclingError: the docling worker exited 1`. Also closed, via the generic path rather than the
named one — worth knowing, because a reader of §8.2 could expect `FormulaEnrichmentFailed` in
every OOM case and it is the harder starvation that produces the other exception.

**Per-paper VRAM headroom, corrected.** Enrichment fails between a 1.6 GiB cap and the 4.0 GiB
card, and succeeds with 3.87 GiB available. Its true working set is therefore bounded but
**unmeasured** — it is somewhere in (1.6, 3.9] GiB, and the caching allocator makes the observed
peak useless as an estimate of it. **UNDETERMINED, and this referee's measurement makes the
builder's "it fit with 178 MiB to spare" reading unsafe to quote.** What is now certain is the
consequence the builder cared about: if Kam opens something that takes the VRAM, the job fails
loudly with a named error rather than writing empty LaTeX. §8.3's conclusion stands; its
diagnosis of *how close* it came does not.

**One minor hazard, not a defect.** After `FormulaEnrichmentFailed`, the base-pass output JSON
remains on disk with formula regions carrying no LaTeX (the merged rewrite only happens on
success). The metrics row says `status="failed"`, so an ingest keyed on status is safe; an
ingest that globs output files is not.

---

## 5. Projection — "per region" is right; the region count is 18% too high

**Is "per region" the right unit?** Yes. CodeFormulaV2 is autoregressive and `is_processable`
filters on the item label, so the model runs once per formula region; the measurement agrees
(5 regions on 2 pages, ~8 s each). The residual assumption, which no one has measured, is that
the per-region cost is *constant* — decode time scales with the length of the LaTeX, and the
five regions measured are short. Flagged, not resolved.

**How many regions does the corpus have above the cut?** The builder projects **8,103** =
1,571 dense pages × 5.16 regions/page, where 5.16 comes from the four gate papers and nothing
else. This referee measured it on the corpus instead: a seeded sample of **12 files**, first
dense run of each (capped at 8 pages), layout pass on the GPU — **29 dense pages, 123 formula
regions, 4.24 per dense page.** Three of the twelve files had a dense page carrying **zero**
regions, which is the §1.2 false-positive class showing up again. Corpus regions above the cut:

> **≈ 1,571 × 4.24 = 6,660 regions** — about **18% fewer** than 8,103.

**A cost the projection omits: `auto` pays a cold converter build per contiguous run.** The
dense pages form **453 contiguous runs across 168 files** (counted from the census with
`page_runs`), and each run is a separate worker process: a converter build (**measured**
7.7–9.4 s) plus a CodeFormula load (**not measured directly**; inferred from the 15.3 s warm-up,
and cross-checked against the builder's own auto row — 72.1 s total − ~40 s enrichment − ~6 s
base pass ≈ 26 s for two spawns ≈ 13 s each). At an **estimated 13–18 s per run** that is
**1.6–2.3 h** the table does not carry; the 2.3 h figure used below is the upper end.

| | builder | referee |
|---|--:|--:|
| regions above the cut | 8,103 | **≈6,660** |
| formula, GPU | 19 h | **≈14.9 h decode + ≈2.3 h per-run cold start ≈ 17 h** |
| formula, CPU | 179 h | **≈147 h + ≈3 h ≈ 150 h** |

Both remain projections, not measurements, and both now rest on a corpus sample rather than on
four papers. The conclusion is unchanged and slightly improved: **gate + GPU turns an
impossible job into an overnight one.** Layout (0.3 h) and OCR (0.04 h) stay negligible.

---

## 6. Ladder and hygiene

* `py -3.12 qc/check.py --fast` was run from this worktree **with `LITKB_PGPORT=1`, stated here
  in those words**. Observed output, quoted rather than summarised:

  ```
  litkb Postgres tests: 216 skipped  <- 216 SKIPPED: litkb server/role/psycopg absent,
                                        so those guards were NOT tested
  FAILED qc\test_experiments.py::test_pointer_paths_resolve[crown_state_model]
  1 failed, 2230 passed, 224 skipped, 74 warnings in 870.33s (0:14:30)
  check: FAILED at rung 'pytest' — fix, then rerun.
  ```

  **The ladder's own verdict line is FAILED, not PASSED**, and this referee reports that rather
  than the harness's exit code 0. The single failure is `crown_state_model`, which the brief
  named as the expected one; **2,230 tests passed and nothing else failed.** The 216 litkb
  Postgres tests are **unexercised** by this referee, as they were by the builder and the
  previous referee; a merge reviewer must run them against a database they are willing to have
  reset. No `litkb*` database was touched. `qc/test_litkb_docling.py` alone: **37 passed,
  3 skipped**.
* `git log -p 414d51a..7e2fa40` scanned for `password|secret|token|api_key|hf_…|postgres://|sk-…`:
  **no secrets**. The only hits are the English word "token(s)" in the OCR discussion and the
  `tokenizers==0.23.2` pin in both requirements files.
* Reproduction scripts live in this session's scratchpad. Per CLAUDE.md §3.4b they are the
  evidence behind §1–§5 and are named at each claim; they were deliberately not added to the
  repo, since the brief allows one file.

---

## 7. Defects and corrections, collected

1. **Precision against hand truth is 0.87, not 0.974** (§1.2). The 0.974 is correct *as measured*
   but generalises poorly: the four gate papers are not the corpus. The false-positive class is
   **numeric tables and figure-label pages**, read as display-maths by the 12-character line
   term. Not a correctness problem — a cost problem.
2. **The "178 MiB of headroom" reading is unsafe** (§3). With 675 MiB more free VRAM the peak was
   the same to within 1 MiB, so the peak measures the allocator, not the requirement. Real
   working set: unmeasured, in (1.6, 3.9] GiB.
3. **The corpus region count is ~18% too high** (§5): 4.24 regions per dense page measured on a
   12-file corpus sample, against 5.16 from four papers.
4. **`auto`'s per-run cold start is missing from the projection** (§5): 453 contiguous runs,
   ~2.3 h on GPU.
5. **206 pages sit within ±0.005 of the cut** (§1.4), including the gold page the test anchors on
   (Bellettini p3 = 0.0501). Worth a sentence in the report; not an error.
6. **A failed enrichment leaves an un-enriched output JSON on disk** (§4). The metrics row says
   `failed`; an ingest that globs files rather than reading status could pick it up.

**None of these is in the gate's logic or in the fail-closed path.** The gate does what it says,
its kills fire, and the kill that mattered most — the one §8.2 honestly marked UNVALIDATED — has
now been fired on a real CUDA out-of-memory and closes correctly.

---

*Referee: Claude Opus 5 · session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED*
