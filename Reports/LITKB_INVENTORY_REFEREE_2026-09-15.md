# litkb P4 stage 0 — independent referee (CLAUDE.md §3.4c)

Referee: a separate agent from the author of `Scripts/pipeline/litkb/extract/inventory.py`.
Worktree `D:\edmonds-pipeline\treedata-inventory`, branch `work/20260915-inventory-stage0`,
HEAD `0e5b9ff`. `D:\edmonds-pipeline\Literture\` opened read-only throughout; no `litkb*`
database other than `litkb_test_w7` was touched; no other worktree, and `main` untouched.

## Verdict — **STAGE 0 READY**, with three limitations that must be written into §9 first

Everything stage 0 *claims to measure*, it measures, and an independent reader reproduces it
exactly. What it does **not** see, it mostly already says it does not see; three blind spots
found here are not yet stated, and none of them has a live instance in this corpus. That is
the difference between a limitation and a defect, and it is why this is READY and not a hold:

1. **Invisible text is invisible to the probe** (my kill K1). A text layer that is white-on-white
   or drawn off the page counts as `chars` and routes `native`. §9.1 covers a *wrong* layer
   (Kingman); it does not cover an *unrenderable* one. **Measured: zero real instances in the
   corpus** (see K1 below), so this is a limitation, not a blocker.
2. **A second boilerplate page is not detected** (K2). `is_cover_sheet` reads page 1 only, so a
   two-page front matter makes `title_page` point at the second cover page. Route is unaffected.
   No corpus file has two front pages.
3. **The ±20 % band around `IMAGE_COVER` is not guarded by the gate** (§3 below). At 0.30 a real
   scanned content page silently leaves the OCR queue, and the twelve-file gate does not see it.

Two smaller corrections to the report, neither load-bearing, are in §7.

---

## 1. Census reproduced with an independent reader

`pdfplumber 0.11.10` (pdfminer.six), **not** the builder's pypdfium2, over every PDF under
`Literture`, frames read from `page.mediabox` / `page.cropbox` / `page.rotation`:

| | referee (pdfplumber) | report §3 | agree |
|---|--:|--:|:--:|
| files, all | 241 | 241 | yes |
| pages, all | 5,038 | 5,038 | yes |
| files / pages, excluding `_quarantine` | 224 / 4,712 | 224 / 4,712 | yes |
| rotated pages (active) | 7 | 7 | yes |
| cropped pages / files (active) | 271 / 19 | 271 / 19 | yes |
| cropped pages / files (all) | 296 / 20 | 296 / 20 | yes |
| rotated **and** cropped | `Hall_1985…` p12, and only that | same | yes |
| files pdfplumber could not open | 0 | (0 unreadable) | yes |

**Per-file, not just in aggregate: 0 disagreements across all 241 files** on page count, on the
set of rotated pages, and on the set of cropped pages. The seven rotated pages come back with
the same quarter turns the report lists — Burnicki p16 p17 (1), Chrisman p8 (3), Guo p6 (1),
**Hall p12 (2)**, Kalinicheva p20 (1), Verburg p10 (1).

**Per-file text characters, the 6 `scan` and 8 `cover-sheet` files** (non-whitespace characters,
pdfminer's extraction vs pdfium's). No page in any of the 14 differs by more than 10 %, and no
page class or route would change on either engine's numbers:

| route | file | pages | plumber / pdfium, whole file | page 1 |
|---|---|--:|--:|--:|
| scan | Ogata 1998 | 24 | 0 / 0 | 0 |
| scan | Anderson 1957 | 22 | 142 / 142 | 142 |
| scan | Hudson 1978 | 12 | 130 / 130 | 130 |
| scan | Hwang 1982 | 11 | 130 / 130 | 130 |
| scan | Politis 1994 | 20 | 130 / 130 | 130 |
| scan | Schwartz 2000 (`_quarantine`) | 3 | 0 / 0 | 0 |
| cover-sheet | Almon 1965 | 20 | 39,894 / 39,893 | 886 |
| cover-sheet | Begg 1983 | 10 | 22,718 / 22,714 | 929 |
| cover-sheet | Cabo 1995 | 22 | 32,006 / 32,004 | 923 |
| cover-sheet | Dawid 1979 | 10 | 22,109 / 22,099 | 1,021 |
| cover-sheet | Hui 1980 | 6 | 12,819 / 12,819 | 886 |
| cover-sheet | Page 1954 | 17 | 39,441 / 39,436 | 849 |
| cover-sheet | Page 1954 (`_quarantine` twin) | 17 | 39,441 / 39,436 | 849 |
| cover-sheet | Satten 1996 | 36 | 115,402 / 115,314 | 1,082 |

The four stamped scans' **whole-file** count equals their **page-1** count, which is the
independent confirmation of report §5's sharpest claim: every page after the stamp holds zero
characters, so `EDGE_PRE1990` P-2's "read page 2" would return nothing. The report is right and
P-2 is wrong.

**CSV row-by-row.** A cold run of the builder into a scratchpad produced a CSV that matches the
tracked `phase4/qc/litkb_inventory.csv` in **every cell of all 241 rows except `seconds`**
(238 of 241 `seconds` cells differ). See §7 for what that means.

## 2. Hand inspection, twelve files I chose

Pages rendered with pypdfium2 and looked at. I deliberately picked files the author did **not**
inspect where one was available (Politis and Hwang rather than Anderson; Begg and Satten rather
than Almon; Cardille, MacFaden and Pauls for `mixed`), plus the four the brief named.

| file | page | what I saw in the render | class | route | agrees |
|---|--:|---|---|---|:--:|
| Schneider 2008 (688 pp) | 1 | Springer cover art, yellow Voronoi, no selectable text | image-only | mixed | yes |
| " | 4 | born-digital half-title: two authors, title, Springer imprint — that is all the text on it | text | | yes |
| Ogata 1998 | 1 | scanned title page, no text layer | image-only | scan | yes |
| " | **24** | scanned references page, **half-empty**, no text layer | image-only | | yes |
| Politis 1994 | 1 | the article's own title page as image; IMS stamp printed in the bottom margin | partial | scan | yes |
| " | 2 | scanned body page, nothing native | image-only | | yes |
| Hwang 1982 | 1 | same pattern — title in the raster, stamp in the margin | partial | scan | yes |
| Begg 1983 | 1 | standalone JSTOR cover: IBS masthead, `Author(s):`/`Source:`/`Published by:`/`Stable URL:`, terms paragraph, nothing else | text | cover-sheet | yes |
| " | 2 | the article's first page — a scan with a complete OCR layer | text | | yes |
| Satten 1996 | 1 | standalone JSTOR cover, same four fields | text | cover-sheet | yes |
| " | 2 | article opening, full-page raster **with** a complete text layer | text | | yes |
| Kingman 1962 | 1 | scanned first page, text layer complete | text | native | yes |
| Verburg 2004 | 10 | landscape Table 2, text runs sideways (rotation 1), layer fine, no raster | text | native | yes |
| Zhu 2008 | 1 | plain born-digital first page | text | native | yes |
| Cardille 2016 | 12 | **native** figure page: six Landsat panels, 134-char caption | partial | mixed | yes |
| MacFaden 2012 | 1 | **native** SPIE title page; title and authors are real text, the "image" is the journal masthead banner (`image_frac` 1.12) | partial | mixed | yes |
| Pauls 2025 | 17 | **native** 7×7 grid of canopy-height rasters, 119 images, 337-char caption | partial | mixed | yes |

**12 of 12 agree** on route, and every per-page class agrees with the render.

**For the `mixed` files, which pages need OCR:** on my reading, **none of them do.** Cardille
p12–14, MacFaden p1 and Pauls p14/16/17 are born-digital pages whose words are already in the
text layer; the raster is figure content, and OCR would return the figure's own baked-in tick
labels at best. The per-page class (`partial`) is nonetheless *correct as defined* — "this page's
text layer does not account for its imagery" — and the consequence is one wasted OCR page, which
is the conservative direction. This confirms report §9.2 rather than contradicting it, and puts
a number on it: of the 14 `mixed` files, the ones I inspected are 4 for 4 native figure pages,
not scanned inserts. The single `mixed` page that genuinely needs OCR is Schneider p1, the book
cover, and that one carries no text at all.

## 3. Threshold sensitivity — the gate catches 1 of 6 ±20 % moves

Thresholds are frozen module constants (`CHARS_TRACE=100`, `CHARS_BODY=400`, `IMAGE_COVER=0.25`,
`COVER_MAX_CHARS=200`, `SCAN_FILE_FRAC=0.5`, `COVER_MIN_FIELDS=2`) and enter the run key through
`params_hash()`. I replayed `classify_page` over all 5,038 measured pages at each constant ±20 %
and asked which pages change class, and whether any of them is pinned by the twelve-file gate:

| move | pages that change class | in a gate file? | gate catches it |
|---|--:|---|:--:|
| `CHARS_TRACE` 100 → 80 | **0** | — | **no (nothing to catch)** |
| `CHARS_TRACE` 100 → 120 | 1 (Guo p6 partial→image-only) | yes, Guo p6 is pinned `partial` | **yes** |
| `CHARS_BODY` 400 → 320 | 4 (Gros p18 p19, Pauls p17, Pesonen p13: partial→text) | no | **no** |
| `CHARS_BODY` 400 → 480 | 10 (text→partial, incl. Kaiser p8, Lahiri p27) | no | **no** |
| `IMAGE_COVER` 0.25 → 0.20 | 1 (remotesensing-14-05911 p25 text→partial) | no | **no** |
| `IMAGE_COVER` 0.25 → 0.30 | 3, one of them **Ogata p24 image-only→`empty`** | Ogata is pinned, but only p1 and p12 | **no** |

The last row is the one that matters. `empty` pages are deliberately **not** queued for OCR, so
at `IMAGE_COVER = 0.30` a page of a pure scan leaves the backlog with no error and no count
change anyone would notice — and I rendered Ogata p24 to be sure it is real content (a
half-filled references page, no text layer at all). Its `image_frac` is **0.2764**, a 10.6 %
margin above the threshold, and it is the corpus's *entire* margin: the next zero-character page
sits at 0.5069. The existing harness probes `IMAGE_COVER` only at 0.95 (T4) and 0.01 (T5), which
are far outside the band where the corpus actually lives.

`CHARS_BODY` is unguarded by the gate in both directions, and `CHARS_TRACE` −20 % cannot be
caught by any test because it changes nothing on this corpus.

**Recommendation (not a blocker):** pin `Ogata p24` as `image-only` in `GATE`, and add the
measured margin (0.2764 vs 0.25) to §2 so the next reader knows how thin it is.

## 4. Kills

### Four harness rows re-applied in my own words

I did not run `litkb_inventory_mutations.py`. I wrote my own applier with my own edit texts,
one row from each of four different families, each run against the full
`qc/test_litkb_inventory.py` set and then restored:

| my row | family | my edit | result |
|---|---|---|---|
| R-A | image coverage | `IMAGE_COVER = 0.25` → `0.60` (not the harness's 0.95) | **FIRED**, 2 failed |
| R-B | the image probe | `images += 1` → `images += 0` (not the harness's `for obj in []`) | **FIRED**, 2 failed |
| R-C | frame reading | `int(FPDFPage_GetRotation(...))` → `... % 1` (not a hard `0`) | **FIRED**, 1 failed |
| R-D | resume key | `ph` → the literal `'CONSTANT'` in `resume_key` (not dropping the element) | **FIRED**, 2 failed |

Baseline `50 passed` before and after; `inventory.py` sha256 restored, `match: True` on all four.

### Three kills of my own

| kill | input | result |
|---|---|---|
| **K1** invisible text must not be `native` | a fixture whose body is drawn with `1 1 1 rg` (white on white), and a second whose text is placed at `-9000 -9000 Td` | **DID NOT FIRE.** Both: `chars=1750`, `image_frac=0.0`, class `text`, route `native`. `classify_page` reads neither colour nor position |
| **K2** a cover sheet whose page 2 is also boilerplate | JSTOR cover, a second boilerplate page, then body | **DID NOT FIRE.** `route=cover-sheet`, `cover_sheet=True`, `title_page=2` — pointing at the second cover page (519 chars), not at the article |
| **K3** same sha256, changed mtime (resume) | recorded file, `st_mtime` pushed a day forward, re-run | **PASSES** — JSONL byte-identical. The resume is content-addressed, so mtime is irrelevant. Inverse also checked: same path, changed bytes → re-probed (1 page → 2 pages), one record, stale record dropped |

**K1 measured against the real corpus, because a non-firing kill is only acceptable with no live
instance.** I scanned all 5,038 pages with pdfplumber for pages whose characters are ≥90 % white
fill or ≥90 % outside the cropbox. 55 page-level flags appeared, across 7 files — and **every one
is a false positive of my detector, confirmed by rendering**:

* the white-fill flags (Caragea 2009, Weakly_Supervised…, Stehman/Xing) report
  `non_stroking_color == (1.0,)`, a one-component ink value in a Separation/ICC space where 1.0
  is *full ink*, not DeviceGray white. Caragea p7 renders as ordinary black body text.
* the off-page flags (Anderson/Hudson/Hwang p1) are an artifact of my own arithmetic on pages
  whose mediabox has `y0 = 51`, not 0. Rendering Hudson p1 shows the IMS stamp plainly printed in
  the bottom margin.

**So: zero real invisible-text pages in the corpus.** K1 stands as a limitation to state, not a
defect to fix. Likewise no corpus file has a second front page, so K2 is a limitation too.

`resume_key` carries `(sha256, path, params_hash)` but **not** the tool version, while §12.4's run
key includes `tool="pypdfium2@<version>"`. A pypdfium2 upgrade therefore replays stale records on
a `--force`-free run. Worth a line in §7 of the author's report.

## 5. The duplicate-sha256 finding — confirmed, and it goes further than reported

Hashes and page-1 text taken independently (pdfplumber):

| sha256[:16] | files carrying these bytes | **the work these bytes actually are** |
|---|---|---|
| `bb14fdbc0a1052b1` | `_quarantine\Chen_2024_coarse-to-fine…`, `_quarantine\Chen_2024_retry2`, `_quarantine\Song_2026_monocular-height…`, `_quarantine\Song_2026_retry2` | **Mufti & Mahony, "Statistical analysis of signal measurement in time-of-flight cameras", ISPRS J. Photogramm. Remote Sens. 66 (2011) 720–731** |
| `3a65f9825495cca1` | `_quarantine\Stehman_2022_incorporating-interpreter-variability`, `_quarantine\Xing_2024_interpenetrating-subsampling-interpreter` | **Wang, Zhang & Atkinson, "Sub-pixel mapping with point constraints", Remote Sens. Environ. 244 (2020) 111817** |

Two corrections to report §3, both in the direction of *less* alarm, and one of them the report
should carry because it changes what admission has to do:

* It is not "one sha256 filed under both Chen 2024 and Song 2026". **Neither name is right.** The
  bytes are a third, unrelated paper, and the same for Stehman/Xing. The question for admission
  is not "which of the two is it" but "none of these four downloads succeeded".
* **All six files are already in `_quarantine`** — the report does not say so for these two groups
  (it does for the Page 1954 twin), and §8 offers them to admission as if they were live. They are
  not in the active 224.
* A **genuine** Song 2026 exists and is fine: `Validation\Song_2026_monocular-height-sparse-lidar-correction.pdf`,
  sha256 `33a975645d26b4a0…`, page 1 "Enhancing Monocular Height Estimation via Sparse
  LiDAR-Guided Correction", Song / Chen / Yokoya. Two different files share that filename at two
  paths, which is exactly the case `resume_key`'s path element exists for, and it handles it.

## 6. Idempotence, the ladder, secrets

* **Idempotence.** Cold run into a scratchpad, then a second run over the same JSONL:
  `sha256(jsonl)` and `sha256(csv)` identical across both runs
  (`70d7ac0deb1f38c8…`, `9a22a84f717b6ad3…`). **No output byte changed.**
* **Wall clock** on this machine: 71.8 s cold, 4.3 s resumed (241 files / 5,038 pages). The
  report's 47.9 s / 3.3 s is the same order but not reproduced; timing is cache- and
  machine-dependent and should not be quoted as a measurement without that caveat.
* **`LITKB_TEST_DB=litkb_test_w7 py -3.12 qc/check.py --fast`**: secrets PASS, ruff PASS, compile
  PASS, pytest **1 failed, 2,489 passed, 5 skipped, 1 xfailed** in 593.8 s — the one failure is
  `test_pointer_paths_resolve[crown_state_model]`, the pre-existing one this branch is allowed.
  Exactly what the report claims.
* **`git log -p 63c9b59..0e5b9ff`** (the two stage-0 commits): no credential, key, or token. Every
  hit for `password`/`secret` is prose about PDF *owner passwords* or about the sink rule.

## 7. Two report corrections

* **§2 / the module docstring disagree about the `IMAGE_COVER` floor.** §2 says "every page with
  no text at all has image coverage ≥ 0.276" (true — 0.2764, Ogata p24). The docstring says the
  floor "is Ogata 1998 … and still reaches 0.51", which reads as though 0.51 were the floor.
  Ogata's *own* minimum is 0.2764. One fact, one home; the docstring restatement is the rotted copy.
* **`seconds` is a nondeterministic column in tracked measured text.** Every other cell of the
  tracked CSV reproduces exactly on a cold re-run, but 238 of 241 `seconds` cells do not — so the
  tracked file can never be byte-reproduced cold, only by resuming from the untracked JSONL. It
  is not wrong (it is a measurement), but a reader diffing the CSV after a re-run will see 238
  changed rows and should be told why.

## 8. What would make me say NOT READY, and did not

A real invisible-text page in the corpus, or a real page that flips to `empty` at the *current*
threshold. I looked for both. The first has zero instances; the second has zero instances at
0.25 and one at 0.30, which is a sensitivity to record, not a live error.
