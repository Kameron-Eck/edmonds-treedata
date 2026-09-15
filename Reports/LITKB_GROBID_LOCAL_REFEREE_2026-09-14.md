# Referee report — GROBID 0.9.1 local stand-up (litkb P4, gate 1)

**Date:** 2026-09-14 · **Branch:** `work/20260914-grobid-local` · **Refereed HEAD:** `adb2110`
**Builder's report:** `Reports/LITKB_GROBID_LOCAL_2026-09-14.md` · **Contract:** CLAUDE.md §3.4b, §3.4c

**Verdict**

| Gate | Verdict |
|---|---|
| **P4 path-A boot gate** (design §14: GROBID 0.9.1 CRF boots under WSL2 and returns TEI with coordinates for a real paper; the JDK-17 kill fires; the §7.1 adapter test fails with the adapter arithmetic removed) | **MET** — reproduced independently, every clause |
| **§14 throughput gate** (pages/s and peak RSS per worker at ≥2 pool sizes; written to `extraction_runs.metrics`; the instrument reports a lower rate pinned to one core) | **NOT MET** — measured here at three pool sizes and the slowdown kill fires, but (a) the configured concurrency 9 saturates all 12 logical CPUs, violating the 20% CPU-headroom rule this configuration was derived from, and (b) no `extraction_runs.metrics` row exists (P4's job table is not built) |

Everything below was measured by the referee on 2026-09-14, on the same host, from the referee's own
TEI census code (`xml.etree` + a hand-written `;`-splitter), not through `litkb.extract.grobid`. The
adapter is only exercised where it is itself the object under test (§4). Scratch scripts live in the
session scratchpad, not in the repo.

---

## 1. The boot gate on Benedek 2015 — reproduced

Service started from `grobid.sh start` (cold, alive after **28 s**), `/api/version` → `0.9.1`; a
warm-up request (**46.9 s**, the CRF model load) before any measurement.

| Clause | Builder | Referee | |
|---|---|---|---|
| HTTP / TEI bytes | 200 / 274,093 | **200 / 274,093** | identical |
| header title ratio (`litkb.admit.resolver.title_match_ratio`, threshold 0.85) | 1.00 PASS | **1.00 PASS** | vs tracker ID **219** |
| `<biblStruct>` | 65 | **65** | |
| coordinate **boxes**: total / ref / figure / head / s | 3,760 / 221 / 37 / 42 / 1,636 | **3,760 / 221 / 37 / 42 / 1,636** | identical |
| `<surface>` elements | 16, numbered 1–16 | **16, numbered 1–16** | page 1 = 595.276 × 793.701 |
| boxes outside their page | 0 | **0** | |

Two notes on the reproduction, neither of which changes the verdict:

* The builder's §6.1 count of **elements** carrying `coords` (1,295) does not reproduce: the referee
  counts **1,116** elements (ref 189, figure 14, head 32, s 491 — those four match exactly). The
  per-kind numbers agree; the total does not, so the 1,295 figure should not be quoted.
* The builder's §3 clause "title ratio 1.0 … against the work's `Reports/literature_tracker.csv` row"
  is right, but the tracker holds **two** Benedek rows — 218 (2009, *Change Detection in Optical
  Aerial Images…*) and 219 (2015). Matching by author substring picks 218 and scores **0.41 FAIL**.
  This is exactly the §4.1 lesson in the other direction: identity must come from the registry
  record, matched by ID, never by a fuzzy author or title lookup.

## 2. Throughput at three pool sizes, with RSS

Workload: the five shapes ×3 = 15 requests (2,361 pages), longest-first, `segmentSentences=1` and all
ten `teiCoordinates` fields, service warm, one pool size per run, nothing else driving the distro.
RSS sampled at 2 Hz from `/proc/<pid>/status` over every `java` and `pdfalto` process; CPU from
`/proc/stat` deltas (whole-system non-idle, 12 logical CPUs). All 45 requests returned **HTTP 200**;
no 503, no pool exhaustion.

| pool | wall | pages/s | peak JVM RSS | peak Σ pdfalto | max one pdfalto | max concurrent pdfalto | peak CPU |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 305.6 s | **7.73** | 8,243 MiB | 20.3 MiB | 20.3 MiB | 1 | 58.6 % |
| 4 | 116.9 s | **20.2** | 11,655 MiB | 66.5 MiB | 20.5 MiB | 4 | 76.5 % |
| 9 | 111.9 s | **21.1** | 13,758 MiB | 109.5 MiB | 20.5 MiB | 6 | **100.0 %** |

`systemctl show grobid -p MemoryPeak` after the three runs: **14,855,753,728 B = 13.84 GiB**, which
corroborates the 13,758 MiB sampled peak.

**There is no per-worker process.** GROBID serves the pool from ONE JVM, so "peak RSS per worker" can
only be derived: JVM RSS rises **≈ 689 MiB per added worker** over the 1→9 span. pdfalto is the only
per-request process and it peaks at **20.5 MiB**, not the 1,536 MiB it is capped at.

**Scaling saturates at 4, and the workload is why.** Each 688-page book takes 110–117 s wall, and the
run's wall clock is the book's; the other twelve requests finish inside it. So conc-4 → conc-9 buys
4 %. This is a property of the corpus (one document is 87 % of the pages), not evidence that GROBID
does not scale — but it does mean **no pool size above 4 can be justified from this measurement**.

**Per-request latency, concurrency 1** (referee vs builder §4, warm):

| | Benedek 16 p | Alwan 10 p | Anderson 22 p | Bellettini 51 p | Schneider 688 p |
|---|--:|--:|--:|--:|--:|
| builder | 6.94 s | 3.43 s | 1.06 s | 6.03 s | 63.05 s |
| referee (3 runs) | 3.97–4.27 s | 2.27–2.67 s | 1.04–1.05 s | 5.15–6.14 s | **83.1 / 85.4 / 97.1 s** |

The articles reproduce or beat the builder's times. **The book's 63.05 s does not reproduce**: three
serial warm runs gave 83–97 s (median 85.4 s → **8.04 pages/s**, not 10.91). Some Windows-side
referee work overlapped the conc-1 run, which would inflate a long request more than a short one, so
the honest reading is **UNDETERMINED, not "the builder is wrong"** — but 10.91 pages/s is a single
unreplicated observation and should not be carried into the §12.10 projection as measured.

### 2.1 The slowdown kill fires

Same paper, warm service, same request. Whole pool (12 CPUs): **8.14 s**. The unit then confined to
one logical CPU (`systemctl set-property --runtime grobid AllowedCPUs=0`, `cpuset.cpus.effective` =
`0`): **12.65 s**, **1.55× slower**. The property reverted afterwards. The instrument can see a
slowdown.

### 2.2 The 20% headroom arithmetic does not survive measurement

`decisions.yaml` §15.16 keeps 20% of RAM **and CPU** free. The builder's budget is
heap 8 + (9 × 1.5 pdfalto) = 21.5 GiB ≤ 24.8 GiB. Measured, both terms are wrong:

* pdfalto never exceeded **20.5 MiB** — the 1.5 GiB term (13.5 GiB of the budget) is ~0.1 GiB in fact.
* the JVM is **not** 8 GiB: it reached 8,243 MiB at concurrency 1 and **13,758 MiB at 9**, i.e. ~5.7 GiB
  of non-heap on top of `-Xmx8g`.

The total, 13.84 GiB, does sit inside 24.8 GiB — but by coincidence, not because the stated model
holds. **CPU headroom does not hold at all:** at concurrency 9 the system reached 100% non-idle,
leaving Kam nothing. Concurrency 4 (76.5% peak) is the setting the 20% rule actually supports, and it
gives 96% of the conc-9 rate on this workload. *Recommendation: `GROBID_CONCURRENCY=4`.*

Base note: WSL sees 31 GiB of the host's 63.76 GiB, and 12 logical CPUs of the host's 12. So the RAM
budget is computed on half the machine (conservative), while the CPU budget is computed on all of it
(not conservative) — the two terms of §15.16 are not on the same base.

## 3. Correctness probes

| Probe | Result |
|---|---|
| `teiCoordinates` sent **comma-joined** as one field | HTTP **200**, TEI valid, header intact — and **8 boxes on `graphic` only**; zero on ref, figure, head, s. **Silent truncation CONFIRMED** (repeated fields on the same paper: 3,760 boxes). |
| `teiCoordinates` sent as **repeated fields** | 3,760 boxes, as §1. |
| JSTOR scan with an image body (`Anderson_1957`) | HTTP **200**, 3,659 B, **4 boxes**, 1 `biblStruct`, header title = the JSTOR access boilerplate. **Confirmed**: a caller checking only the status code records this as a successful extraction. |
| **truly image-only PDF** (referee-built: one page of Benedek rasterised to JPEG and wrapped, `pdftotext` → 0 bytes) | HTTP **500**, body `[NO_BLOCKS] PDF parsing resulted in empty content`. |
| corrupt: first 4 KB of a valid PDF | HTTP **500** `[BAD_INPUT_DATA] PDF to XML conversion failed with error code: 1` |
| corrupt: plain text, no PDF header | HTTP **500**, same body |
| corrupt: `%PDF-1.4` + 2 KB random | HTTP **500**, same body |
| **zero-byte file** (referee addition) | HTTP **500**, same body |

**500 not empty TEI: confirmed on four inputs.** And the builder's §8.3 statement that "an image-only
scan returns 200 with an empty body parse" needs narrowing: a file with **no** text layer anywhere is
refused with a distinct `[NO_BLOCKS]` 500. The 200-with-nothing case requires a text layer somewhere
in the file — which on a JSTOR scan is the cover page. The dangerous class is *partially* extractable
scans, not image-only ones.

**Defect — the adapter does NOT refuse by block count.** The task brief and the builder's
`GrobidError` docstring ("treating that as *empty but fine* would let a silently unextracted file into
the lake as a zero-block run") describe a guard that is not implemented: `process_pdf` returns the
body on any 200 and no caller-side zero-block check exists anywhere in `Scripts/pipeline/litkb/`
(`grep` for a block-count gate returns only `iter_blocks`/`blocks`/`implausible_blocks`, none of which
refuses). No test asserts it either. The Anderson TEI — 4 boxes, a boilerplate title — passes the
adapter unchallenged. This must be written before stage 2 runs on the corpus.

## 4. Adapter kills — all three fire on the real file

Source-level mutations of `Scripts/pipeline/litkb/extract/grobid.py`, then
`pytest qc/test_litkb_grobid.py` (21 fixture tests; 3 live tests skipped), then `git checkout --`.

| Mutation | Result |
|---|---|
| `boxes.append((page, x, y, x + w, y + h))` → `(page, x, y, w, h)` | **7 failed**, 14 passed — incl. `test_every_fixture_box_sits_inside_its_page` |
| `(value or "").split(";")` → `[(value or "")]` | **5 failed**, 16 passed — incl. `test_figure_yields_one_block_per_box` |
| out-of-page predicate → `elif False:` (referee addition) | **1 failed** — `test_implausible_blocks_flags_an_escaping_box` |
| unmutated | 21 passed, 3 skipped |

Restored: worktree blob `0f78ba3487433b299e2465330e545ddd169db833` = `HEAD:…/grobid.py`, `git diff`
empty. (The file's sha256 on disk changed, 77bd5ac3… → 679d7524…, because `git checkout` re-materialised
it with CRLF while the builder's working copy was LF. Git content identical; nothing was altered.)

### 4.1 The bbox-origin claim, checked against pypdfium2

Claim: page 1-indexed, PDF points, origin upper-left. Method: for each test string, union pypdfium2's
per-character boxes (`get_charbox`, bottom-left origin, mediabox user space) and convert to GROBID's
frame; only strings occurring **exactly once** on the page were used.

| PDF | pages | strings | max component offset |
|---|---|--:|--:|
| Benedek_2015 (uncropped, unrotated) | 1, 5 | 6 | **2.41 pt** |
| Alwan_1988 (**cropbox ≠ mediabox**) | 2, 3 | 5 | **4.71 pt** (1.18 pt excluding one partial-string match) |
| Guo_2019 page 6 (**rotated 90°**) | 6 | 1 | **3.38 pt** |

**Max offset over all 12 strings: 4.71 pt**; ≤ 1.28 pt wherever the matched string is the whole
element. The residual is glyph-extent vs layout-box, not a frame error. Page indexing, units and the
upper-left origin are **confirmed**.

Two facts the design and the adapter docstring do not state, both of which would produce silent
misplacement downstream:

1. **GROBID's frame is the CROPBOX, not the mediabox.** On Alwan, mediabox `(0,0,612,792)`, cropbox
   `(10.34, 10.78, 603.44, 782.95)`; `<surface>` is 593.096 × 772.171 = the cropbox, and boxes are
   measured from the cropbox's upper-left. Comparing without subtracting the cropbox origin gives a
   systematic **10.9 pt** error in x and y (that is exactly the 121 pt/11 pt mismatch the referee saw
   before correcting the conversion). **223 pages across the 216-PDF corpus have cropbox ≠ mediabox**,
   including one of the five gate papers. §7.1 says "PDF points, origin top-left of the page" without
   naming the box; it must.
2. **Rotation IS applied.** Guo page 6 (`/Rotate 90`) gets `<surface n="6" lrx="793.701"
   lry="595.276"/>` — landscape — and its coords are in the displayed frame. This satisfies §7.1's
   "as displayed (rotation applied)" and is now measured rather than assumed. Corpus census:
   7 rotated pages in 216 PDFs.

Also corrected: the builder's §6 says the surfaces' sizes "match the PDF's own **A4** page box".
595.276 × 793.701 is not A4 (841.89 pt tall). They match the PDF's own mediabox/cropbox, which is the
load-bearing part; the word A4 is wrong.

## 5. Service kills — reproduced, with one addition that does not refuse

| Kill | Result |
|---|---|
| **JDK 17** (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`, built launcher) | `UnsupportedClassVersionError: … class file version 65.0, this version … recognizes up to 61.0`, **exit 1**. Reproduced verbatim. |
| **`JAVA_HOME` at a non-existent JDK** (`/opt/no-such-jdk`) | `ERROR: JAVA_HOME is set to an invalid directory`, **exit 1**. Reproduced. |
| **`JAVA_HOME` UNSET** (referee addition) | **The launcher does NOT refuse.** It falls back to `java` on `PATH` (21.0.12), boots Dropwizard, and dies later on an unrelated error (`Could not read GROBID_HOME … does not exist` — GROBID_HOME resolved relative to the caller's cwd). The "missing `JAVA_HOME`" refusal is really an *invalid-directory* refusal; an unset `JAVA_HOME` on a host whose `PATH` java is 17 would fail with the version error, and on a host whose `PATH` java is 21 would start. The systemd unit always sets `JAVA_HOME`, so this does not affect the gate. |

Service left **stopped**: `grobid.sh status` → `inactive` / `isalive: unreachable`, `pgrep java`
empty. The unit is not enabled.

## 6. `.gitattributes` `*.sh text eol=lf`

`git ls-files '*.sh'` → exactly one tracked file, `Scripts/pipeline/litkb/extract/grobid.sh`; a
case-insensitive sweep finds no other. The rule therefore affects nothing else. `git ls-files --eol`
over all 1,189 tracked files: 1,175 `w/crlf`, 12 `w/-text`, 1 `w/none`, and **1 `w/lf` — the script**.
A fresh `git clone -b work/20260914-grobid-local` into a clean directory gives a shebang of
`#!/usr/bin/env bash\n` (`od -c`: `b a s h \n`) and **zero CR bytes in the file**. Confirmed.

## 7. Ladder and diff

`cd Scripts && LITKB_TEST_DB=litkb_test_w3 PYTHONUTF8=1 py -3.12 qc/check.py --fast`:
secrets PASS, ruff PASS, compile PASS, pytest **1 failed, 2,426 passed, 8 skipped, 1 xfailed** in
679 s — the single failure is the allowed `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`.
`litkb Postgres tests: 215 passed`. No other failure.

`git log -p 4256e4e..adb2110` (1,475 lines) scanned for `password|secret|api_key|token|PRIVATE KEY|ghp_|sk-…|AKIA|obuntu`:
**no match**. No credential is committed.

## 8. Defects and what is still owed

1. **No zero-block refusal** (§3). The guard the docstring describes does not exist in code or tests.
   Blocking for stage 2.
2. **Concurrency 9 violates the CPU half of §15.16** (§2.2) — 100% peak. Set it to 4; it costs 4% of
   the rate on this workload.
3. **The pdfalto memory term in the budget is off by ~75×** (20.5 MiB measured vs 1,536 MiB budgeted)
   and the JVM term by ~1.7× the other way. The arithmetic in `grobid.sh`'s header comment and the
   builder's §2 should be replaced with the measured figures.
4. **`extraction_runs.metrics` is not written** — P4's job tables are not built, so the §14 clause
   "written to `extraction_runs.metrics` and the phase report" is half done and the §12.10 projection
   cannot be filled from a table. Rates exist; the row is owed.
5. **The book's 10.91 pages/s is unreplicated** (§2) and should not enter the projection.
6. **§7.1 must name the box the origin sits on** (cropbox), and the adapter docstring with it (§4.1).
7. **Scaling above 4 workers is untested in substance** — one document is 87% of the pages, so the
   conc-9 wall clock is that document's. A gate rerun on an article-only set would settle it.
8. Cosmetic: the builder's element total 1,295 (§1) and "A4" (§4.1) do not reproduce.

Nothing here contradicts the boot gate. The path-A gate is met; the throughput gate is not, for the
two reasons in the table at the top.
