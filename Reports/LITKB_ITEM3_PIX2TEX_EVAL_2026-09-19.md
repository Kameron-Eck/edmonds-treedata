# Item 3 — pix2tex as a second formula decoder: evaluation only (2026-09-19)

**Verdict up front:** decoder agreement, as measured here, never once fired on a
both-wrong equation (0/6 agreements in the 20-equation gold set). But its coverage is
low — the two decoders agree on only 30% of the gold set and 12% of a 200-crop sample
drawn from the ingest-**accepted** 6,841 of the 7,164 real-corpus crops (§5; likely an
optimistic subset) — because pix2tex's own accuracy on these archive crops (40%, 8/20)
is meaningfully below CodeFormula's (55%, 11/20) and its failure mode is usually
catastrophic garbling rather than a near-miss. **Agreement looks trustworthy when it
fires, but on this population it fires too rarely to carry most of the `stable` load
alone.** No case of "agree and both wrong" was observed, but n=6 agreements is small: a
95% Wilson interval on 0/6 reaches up to ~39%, so this evaluation does not rule out the
false-signal failure mode — it just did not catch one in twenty equations.

## 1. Setup (pix2tex venv, isolated)

```
D:\edmonds-pipeline\venv-pix2tex   (own venv, NOT added to any requirements file or pyproject.toml)
torch==2.13.0+cu126          torchvision==0.28.0+cu126
pix2tex==0.1.4               transformers==5.17.0
timm==0.5.4                  tokenizers==0.23.2
x-transformers==0.15.0       einops==0.8.2
munch==4.0.0                 numpy==2.5.3
opencv-python-headless==5.0.0.93   pillow==12.3.0   pypdfium2==5.13.0
```
`pip install pix2tex numpy pypdfium2 pillow` pulled its own CPU-only torch/torchvision
(2.14.0+cpu); reinstalling `torch==2.13.0 torchvision --index-url
https://download.pytorch.org/whl/cu126` afterward restored CUDA (`pip check`: no
conflicts). pix2tex's `LatexOCR` defaults `no_cuda=True` unconditionally
(`pix2tex/cli.py` line 72) regardless of `torch.cuda.is_available()`; every run below
passes `Munch({..., "no_cuda": False})` explicitly to get the T2000.
Pretrained weights (`weights.pth` 97.4 MB, `image_resizer.pth` 18.5 MB, release v0.0.1)
downloaded from GitHub on first use — not retrained, not fine-tuned.

Measured GPU use, gold run (20 images): `torch.cuda.max_memory_allocated` **260.7 MiB**,
`max_memory_reserved` **354.0 MiB** — the whole run in one process, so this is the
per-process high-water mark regardless of the fact the 20 images were run one at a time
(no batching). T2000 has 4 GB; headroom is large.

## 2. Locating the gold set and CodeFormula's output — no guessing

- Gold LaTeX (`reading` field) + block_id/file/page/bbox for 20 equations:
  `Reports/gold/p5_gold_2026-09-16.json` → `equation_ids.E01..E20` (authored 2026-09-16,
  frozen before any DB row was consulted, per that file's own `_selection.equations`).
- CodeFormula's stored output + `latex_status`: live Postgres `litkb` (port 5433, role
  `litkb_reader`), joined `litkb.blocks` (by `id = block_id`) → `litkb.extraction_runs`
  (`id = run_id`) → `litkb.main_files` (`file_id`) for `rel_path`; `litkb.equations`
  (`block_id`) for `latex_status`. **The DB's `run_id → current run` join used in
  `litkb_p5_canonical.py` returned NULL for all 20** (those runs are no longer each
  file's *current* run) — resolved by joining `extraction_runs` directly instead of
  requiring `current_run_id`, confirmed correct because the fetched `bbox` matches the
  gold's `bbox` (gold's own values are rounded to 1 decimal place; the DB's full-precision
  values round to them exactly) for all 20 checked.
- Source PDFs: `D:\edmonds-pipeline\Literture\Validation\*.pdf` (all 20 present).
- L4 full-pass population for step 4: `D:\edmonds-pipeline\litkb_derived\formula\
  latex_formula_colab_full.jsonl` — **measured 6,841 rows**, not the 7,164 relayed in
  the task brief. **Not a discrepancy**: `latex_formula_colab_full_verify_queue.jsonl`
  (beside it) holds **323** rows (`wc -l`), and 6,841 + 323 = 7,164 exactly.
  `formula_ingest.py`'s docstring says a row not scored `ok` goes to the verify queue
  "beside" the corpus, never into it — so `latex_formula_colab_full.jsonl` is the
  **ingest-accepted subset** of the 7,164 crops, not the full population. §5's sample is
  drawn from this accepted subset, which matters for reading its agreement rate (see §5).
  Crop PNGs for that pass live in `litkb_derived\formula\shards_full\shard_{shard_id}.zip`
  under `crops/{crop_id}.png` (NOT in `results_full/*.zip`, which hold only decode-result
  JSONL + worker metadata, no images).

Crops for the 20 gold equations do not pre-exist as files — only bbox + page are gold.
Rendered them from the source PDF myself: `pypdfium2` page render at scale 4.0×, pixel
rect = canonical bbox shifted by the page's `(dx, dy)` cropbox offset (reused
`litkb.extract.inventory.page_frames`, the one frame reader in the repo — not
reinvented), expanded 18% of box width/height per side (the same
`expansion_factor` `formula_crop_worker.py` documents for the real CodeFormula crop).
Verified visually on 7/20 crops (E02, E03, E05, E08, E10, E11, E17) against the gold
`reading` and the referee report's own descriptions — all landed correctly on the
equation, including the one page with a nonzero cropbox shift (Conley_1999,
`dx=40.0, dy=37.0`, matching the referee's own finding). **Caveat:** this is a
functionally-equivalent reproduction of the CodeFormula crop, not a byte-identical one.
On E11 specifically, my own rendered crop DOES carry the neighbouring line — its bottom
edge shows "...parts, equals" — the same fragment CodeFormula's stored output garbles as
`\intertext{ i n t s e q u a l s }`. So both decoders saw the same contaminating text;
CodeFormula transcribed it (and was graded wrong for it) and pix2tex did not (and was
graded correct) — a real difference in decoder behaviour on identical input, not a
crop-fidelity artifact. Corrected from an earlier draft of this report, which had this
backwards.

Commands:
```
py -3.12 Scripts/scratch/pix2tex_eval/render_gold_crops.py       # 20 crops + gold_equations_joined.json
venv-pix2tex\Scripts\python.exe Scripts/scratch/pix2tex_eval/run_pix2tex_gold.py
py -3.12 Scripts/scratch/pix2tex_eval/sample_bulk_crops.py       # 200-crop bulk sample
venv-pix2tex\Scripts\python.exe Scripts/scratch/pix2tex_eval/run_pix2tex_bulk.py
py -3.12 Scripts/scratch/pix2tex_eval/score_gold.py              # the matrix below
```

## 3. Agreement / equivalence rule

`Scripts/scratch/pix2tex_eval/normalize_and_score.py`: strip whitespace and pure-spacing
macros (`\,\;\:\!\quad\qquad`, bare control-space `\ `), drop `\left/\right` and all
big-delimiter sizing macros, collapse `\mathrm/\mbox/\text/\operatorname(*)` wrappers to
their bare argument, strip ALL remaining `{}` grouping, fold `\colon`→`:` and
`\arg\min`/`\argmin`, drop one trailing `(N)`/`(d.d)` equation-number tag. **AGREE iff
the two normalized strings are byte-identical** — deliberately strict past that point: a
wrong subscript, dropped term, or swapped accent (`\hat` vs `\bar`) still counts as
disagreement. This rule reproduces my independent manual read on all 20 gold equations
exactly (verified by hand before trusting it on the 200-crop sample).

## 4. The 20-equation matrix (`gold_scored.json`)

| | Agree | Disagree | row |
|---|--:|--:|--:|
| **Both correct** | 6 | — | 6 |
| **CodeFormula correct only** | — | 5 | 5 |
| **pix2tex correct only** | — | 2 | 2 |
| **Both wrong** | **0** | 7 | 7 |
| col | 6 | 14 | 20 |

n=20, agree=6 (30%), CodeFormula correct=11 (55%, matches the relayed state), **pix2tex
correct=8 (40%)**.

Per-equation table (id, agree, CodeFormula-correct, pix2tex-correct, note) is in
`Scripts/scratch/pix2tex_eval/gold_scored.json` and reproduced by `score_gold.py`'s
stdout. Two findings worth flagging on their own:
- **E05**: pix2tex got `S^{d-1}` right where CodeFormula's stored output has `S^{d}`
  (one of CodeFormula's 5 documented math errors) — pix2tex corrected a real
  CodeFormula error here.
- **E08**: the reverse — CodeFormula's 4×4 transition matrix was exactly right;
  pix2tex dropped a `1-e_{32}` term to `0` and dropped the last matrix entry outright.
  Confirmed on the crop both times.
- Catastrophic garbling (a 1–6-char token repeated 15+ times — the same regex used on
  the bulk sample in §5) hit 4/20 pix2tex outputs (**E03, E06, E07, E19** — measured by
  running the regex, not eyeballed; E03's own garbling is a long run of `\:` spacing
  tokens, E06's a long run of `~`) — a failure mode CodeFormula's 20-sample errors never
  showed; CodeFormula's failures are near-misses or contamination, not collapse.

## 5. Bounded sample of the real corpus (agreement rate only — no gold there)

Population: 6,841-row `latex_formula_colab_full.jsonl` — **not** the full 7,164 crops
unfiltered: per §2, this file is the ingest-**accepted** subset (the 323 rows the L4 pass
itself did not stand behind are held in the separate verify queue, never merged in). So
the sample below is drawn from the CLEANER half of the corpus, if anything biased toward
crops CodeFormula itself found more decodable — the true population-wide agreement rate
is likely lower than what follows, not higher.
Sample: N=200, `random.Random("litkb-item3-pix2tex-bulk-2026-09-19").sample(rows, 200)`
over that accepted population, no further filtering. 1/200 crops failed to load
(`ValueError: height and width must be > 0` — a zero-size crop already in the corpus,
not a pix2tex defect); scored 199.

**Agreement rate: 24/199 = 12.1%** — noticeably lower than the gold set's 30%, despite
being drawn from the easier subset. A catastrophic-garbling check (a 1–6-char token
repeated 15+ times, run identically on both sets) fires on **27/199 (13.6%)** of
pix2tex's bulk outputs and on **4/20 (20%)** of the gold set — so gold's catastrophic
rate is if anything the HIGHER of the two by this measure, not "consistent" in the sense
of matching; both say roughly one pix2tex output in five to seven is outright garbage,
not a near-miss. No gold exists for the bulk sample, so correctness (and thus the
both-wrong-and-agree cell) cannot be measured here — only that agreement is rare and
pix2tex's collapse-to-garbage mode is common across the real corpus, not a gold-sample
artifact.

## 6. Verdict on the design question

**Precision of the "agree" signal is good in this sample (0/6 both-wrong); its coverage
is not** — at a 30% (gold) to 12% (bulk) agreement rate, the AGREE bucket would carry
only a minority of equations, pushing most of the corpus to Claude-vision fallback
under Kam's design. That may still be an acceptable cost (agreement-as-`stable` never
misfired here), but it is not evidence agreement lets pix2tex do much load-bearing work
as a cheap first pass on this archive — pix2tex's own accuracy (40%) trails CodeFormula
(55%), and roughly one in seven to one in five of its outputs are outright garbage
rather than near-misses, which is exactly the failure mode agreement-checking is
supposed to catch (and did, here — every garbled pix2tex output disagreed with
CodeFormula). **The honest open question the task asked for:** with only 6 agreements
observed, the "0 both-wrong" result has a wide-enough interval (up to ~39% at 95%
confidence) that a larger gold set is needed before trusting the AGREE bucket
unsupervised at scale.

## 7. Gate: `qc/check.py --fast` against `litkb_test_w13`

```
cd Scripts && LITKB_TEST_DB=litkb_test_w13 PYTHONUTF8=1 py -3.12 qc/check.py --fast
```
`secrets`/`ruff`/`compile` PASS. `pytest`: **1 failed, 2,756 passed, 437 skipped,
1 xfailed** in 598.3s. The one failure is the known-tolerated
`test_pointer_paths_resolve[crown_state_model]` — nothing else broke.

**All 414 litkb Postgres tests were among the 437 skipped, not run against `litkb_test_w13`,
because that database does not exist on the server** — confirmed directly
(`psycopg.connect(dbname="litkb_test_w13", ...)` → `FATAL: database "litkb_test_w13" does
not exist`). Creating it requires `litkb.db.provision.provision_workers`, which connects
as `_c.SUPERUSER` — genuine server-admin access this evaluation-only item has no reason to
hold and should not exercise. This is a blocker for the orchestrator, not something worked
around here: this gate exercised only the non-litkb suite (2,756 passed, 23 skipped for
other reasons, 1 xfailed, the one known-tolerated fail) — zero litkb tests ran, against
`litkb_test_w13` or anywhere else.

## 8. Did NOT test

- The 414 litkb Postgres tests (worker DB `litkb_test_w13` absent — §7).
- Byte-identical crop fidelity against the real L4/Colab pipeline's own crop (my
  rendering is functionally equivalent, confirmed on 7/20 by eye, not byte-compared).
- Correctness of pix2tex (or CodeFormula) on the 200-crop bulk sample — no gold there,
  agreement rate only.
- The 323 verify-queue crops (ingest-rejected; outside both the gold set and the
  ingest-accepted population §5 samples from).

---
*Files: `Scripts/scratch/pix2tex_eval/{render_gold_crops,run_pix2tex_gold,
sample_bulk_crops,run_pix2tex_bulk,normalize_and_score,score_gold}.py`,
`{gold_equations_joined,pix2tex_gold_predictions,gold_scored,bulk_sample_joined,
pix2tex_bulk_predictions}.json`, `crops_gold/E01..E20.png`, `crops_bulk/*.png` (200,
one failed to load). No litkb write attempted — this item is evaluation-only, verified
by `git status --short` showing nothing under `Scripts/pipeline/litkb/` touched.
Built by Claude Sonnet 5 (this session's actual model; the base brief's default
attribution line names Opus 5, per the launch prompt's routing).*
