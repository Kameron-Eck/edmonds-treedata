# GROBID 0.9.1 (CRF) local stand-up — litkb P4 first gate

**Date:** 2026-09-14 · **Branch:** `work/20260914-grobid-local` · **Host:** Ubuntu 26.04 LTS under
WSL2 (systemd, 12 logical threads, 31 GiB visible to the distro)

**Verdict: the P4 path-A boot gate PASSES.** GROBID 0.9.1 CRF boots under WSL2 on this laptop and
returns TEI with coordinates for a real paper. Both kill criteria fire. What is NOT done is the §14
throughput gate at two or more pool sizes — see §8.

Every number below was measured on this machine on 2026-09-14. Nothing is quoted from a vendor page.

---

## 1. Install layout

| Thing | Where |
|---|---|
| JDK | `/usr/lib/jvm/java-21-openjdk-amd64` — OpenJDK **21.0.12** (`openjdk-21-jdk-headless`, Ubuntu package) |
| GROBID source | `/opt/grobid-0.9.1` (symlink `/opt/grobid`), from the GitHub tag zip `0.9.1` |
| Launcher | `/opt/grobid-0.9.1/grobid-service/build/install/grobid-service/bin/grobid-service` |
| Config | `/opt/grobid-0.9.1/grobid-home/config/grobid.yaml` (stock copy kept as `grobid.yaml.orig`) |
| Service unit | `/etc/systemd/system/grobid.service`, **enabled** |
| Log | `/var/log/grobid.log` |
| Ports | 8070 application, 8071 admin |
| Manager script | `Scripts/pipeline/litkb/extract/grobid.sh` — `install / configure / start / stop / restart / status / health`, all idempotent |
| Python adapter | `Scripts/pipeline/litkb/extract/grobid.py` |
| Tests | `Scripts/qc/test_litkb_grobid.py`, fixture `Scripts/qc/fixtures/grobid_sample.tei.xml` |

**Why not a repo-root `scripts/wsl/grobid.sh`.** The repo root already carries `Scripts/`, and
Windows is case-insensitive: `ls -d scripts` at the root resolves to `Scripts`. A lowercase sibling
would be the same directory. The manager therefore lives beside the adapter it serves.

**Build.** `./gradlew clean install --no-daemon -x test`, then `:grobid-service:installDist`. Two
things had to be worked around, both recorded in `grobid.sh` so the next install is clean:

1. GROBID 0.9.1 ships Gradle 9.6.1, and `installDist` fails with
   `Entry lib/langdetect-1.1-20120112.jar is a duplicate but no duplicate handling strategy has been set`.
   Gradle 9 dropped the implicit strategy. Fixed with a Gradle **init script** setting
   `duplicatesStrategy = EXCLUDE`, so the vendored source tree is not edited.
2. `installDist` then refuses a non-empty partial install directory; the script removes it first.

**CRF, not deep learning.** All 10 active `engine:` entries in `grobid.yaml` read `wapiti`; there is
no active `delft` entry and no DeLFT install. This is the CRF build the design chose (§7 stage 2),
and it needs no GPU.

## 2. Resource settings and the arithmetic behind them

`decisions.yaml` §15.16: local workers keep 20% of RAM and CPU free for Kam's own work.

| Setting | Stock | Set to | Why |
|---|---|---|---|
| JVM heap | (unset) | **`-Xmx8g`** | design §12.7 cites GROBID 6–8 GiB for batch |
| `concurrency` | 10 | **9** | 12 logical threads × 0.8 = 9.6 |
| `pdf.pdfalto.memoryLimitMb` | 6096 | **1536** | this is a **per-subprocess** cap; 9 × 6096 MB = 54 GiB, far over budget |
| `pdf.pdfalto.timeoutSec` | 120 | **300** | headroom for the 688-page book |
| consolidation | crossref | **off per request** (`consolidateHeader=0`, `consolidateCitations=0`) | keeps stage 2 offline; no network consolidation was enabled for any run below |

Budget: usable RAM = 31 × 0.8 = **24.8 GiB**. Heap 8 + (9 × 1.5) = **21.5 GiB ≤ 24.8 GiB**.

**Measured peak:** `systemctl show grobid -p MemoryPeak` after the 688-page book = **7,831,412,736 B
(7.29 GiB)**. That is the whole unit cgroup at concurrency 1, so it is a floor for a loaded pool, not
a pool figure. Only the first two `timeoutSec` keys under `grobid.pdf.pdfalto` are rewritten; the
consolidation timeouts stay at 60 (verified after the edit).

## 3. The gate

Gate (task §3, design §14 P4 path A): TEI returned; header title matches the registry title ≥ 0.85;
≥ 1 `<biblStruct>`; `coords` on refs/figures/heads with 1-indexed pages and plausible boxes.

**On `Benedek_2015_multilayer-markov-random-field-models.pdf` the gate PASSES on every clause:**
TEI returned (HTTP 200, 274,093 B); title ratio **1.0**; **65** `<biblStruct>`; **221** `<ref>`,
**37** `<figure>` and **42** `<head>` coordinate blocks; 16 `<surface>` elements numbered 1–16; and
**0** boxes that fall outside their page.

Title ratio uses the project's one rule — `litkb.admit.resolver.title_match_ratio` with
`RESOLVE_TITLE_RATIO = 0.85` — against the work's `Reports/literature_tracker.csv` row. That is the
project's **claimed** record, not a live Crossref fetch; no network call was made.

## 4. Five shapes: timings and TEI census

Warm service, one request at a time, from inside the distro. The cold CRF model load was absorbed by
a separate warm-up run (**45.4 s** for an 11-page paper); no timing below carries it.

| Shape | File | Pages | Wall | pages/s | HTTP | biblStruct | blocks | refs | figs | heads | sents | bad boxes | title ratio |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| two-column | `Benedek_2015_multilayer-markov-random-field-models` | 16 | 6.94 s | 2.31 | 200 | 65 | 3,760 | 221 | 37 | 42 | 1,636 | 0 | **1.00 PASS** |
| two-column (was the 3-col candidate) | `Alwan_1988_time-series-modeling-statistical-process` | 10 | 3.43 s | 2.91 | 200 | 15 | 1,966 | 40 | 9 | 29 | 975 | 0 | **1.00 PASS** |
| JSTOR scan, no text layer | `Anderson_1957_statistical-inference-about-markov` | 22 | 1.06 s | 20.67 | 200 | 1 | 4 | 0 | 0 | 0 | 0 | 0 | 0.25 FAIL |
| equation-heavy | `Bellettini_2002_total-variation-flow` | 51 | 6.03 s | 8.46 | 200 | 39 | 6,199 | 123 | 97 | 15 | 2,909 | 0 | **0.98 PASS** |
| 688-page book | `Schneider_2008_stochastic-integral-geometry` | 688 | **120.61 s** | 5.70 | 200 | 1,276 | 65,266 | 1,410 | 1,319 | 495 | 31,148 | 0 | 0.38 FAIL |
| (warm-up, IEEE preprint) | `Abercrombie_2016_improving-consistency` | 11 | 45.4 s cold | — | 200 | 41 | 2,355 | 73 | 55 | 16 | 1,076 | 0 | 0.21 FAIL |

The book ran **in full in 2 minutes**, well inside the 20-minute budget, so no 50-page subset was
needed. Across all six files, **0 of 79,550 boxes** fell outside their page.

**Windows-side timing** (same service, over WSL's localhost relay): the 3.3 MB two-column paper
took **5.17 s** warm — no measurable penalty versus the in-distro 6.94 s.

### 4.1 The three title failures are real findings, not noise

* **`Anderson_1957` (0.25)** — an image-only JSTOR scan: `pdftotext` yields **0 characters/page**.
  GROBID returned **HTTP 200** with a 3.7 KB TEI whose "title" is the JSTOR boilerplate. It did not
  return 204. **A caller that checks only the status code will record this file as successfully
  extracted with 4 blocks.** Scans need the design's OCR path before stage 2 means anything.
* **`Schneider_2008` (0.38)** — the book's header parse returns the Springer *series* name
  "Probability and Its Applications" instead of "Stochastic and Integral Geometry". The body parse is
  fine (1,276 references, 65k blocks); it is the header model that is mislead by a series title page.
* **`Abercrombie_2016` (0.21)** — GROBID took the IEEE banner "This article has been accepted for
  inclusion in a future issue of this journal…" as the title. A publisher stamp beats the real title.

For P5 this means the header title is **not** a safe identity key on books or stamped preprints; the
registry record must stay the identity, exactly as `litkb-p0-foundation` already has it.

### 4.2 No genuine three-column paper exists in this corpus

A shape census over **216 PDFs** in `Validation/`, `ASPP/` and `Labeling/` (word x-centres binned
across a page, gutters counted) found no paper with three body columns. Every candidate the first
pass flagged resolved to one or two columns when the raw histogram was inspected: `Alwan_1988`, the
strongest candidate at 3 runs on 8 of 8 pages, has two body columns plus a narrow marginal artefact
at x≈0.03. **The three-column shape is therefore untested — it is absent, not skipped.**

## 5. Kill criteria — both fire

**Kill 1a — the same boot under a JDK older than 21.** Same launcher, same config, only
`JAVA_HOME` changed to `/usr/lib/jvm/java-17-openjdk-amd64` (OpenJDK 17.0.20):

```
Error: LinkageError occurred while loading main class org.grobid.service.main.GrobidServiceApplication
	java.lang.UnsupportedClassVersionError: org/grobid/service/main/GrobidServiceApplication has been
	compiled by a more recent version of the Java Runtime (class file version 65.0), this version of
	the Java Runtime only recognizes class file versions up to 61.0
```
Exit 1. (Class file 65.0 = Java 21; 61.0 = Java 17.)

**Kill 1b — `JAVA_HOME` at a non-existent JDK** (`/opt/no-such-jdk`):
`ERROR: JAVA_HOME is set to an invalid directory: /opt/no-such-jdk`, exit 1.

These ran against the **built launcher**, not `./gradlew run`, so the refusal is GROBID's own and not
Gradle failing for unrelated reasons.

**Kill 2 — a corrupted PDF must error, not return empty TEI.** Three damaged inputs, all three
**HTTP 500** with `[BAD_INPUT_DATA] PDF to XML conversion failed with error code: 1`:

| Input | HTTP | Body |
|---|--:|---|
| first 4 KB of a valid PDF (truncated) | 500 | `[BAD_INPUT_DATA] PDF to XML conversion failed with error code: 1` |
| plain text, no PDF header | 500 | same |
| `%PDF-1.4` header + 2 KB of random bytes | 500 | same |

The adapter treats **every** non-200 as an error, 204 included, so a "no content" answer can never be
mistaken for a clean empty extraction.

## 6. The §7.1 bbox adapter

GROBID emits `coords="page,x,y,w,h"`, page 1-indexed, PDF points, origin upper-left. The canonical
frame in design §7.1 is PDF points, 1-indexed pages, origin top-left, `(x0, y0, x1, y1)`. So the
adapter is **`x1 = x + w`, `y1 = y + h`, with no page offset and no y-flip** — confirmed against the
`<facsimile><surface n="1" ulx="0.0" uly="0.0" lrx="595.276" lry="793.701"/>` elements, whose sizes
match the PDF's own A4 page box and whose numbering starts at 1.

`Block` carries `page, x0, y0, x1, y1, kind, text, extractor, confidence, element_id, box_index,
box_count`. **`confidence` is `None`**: GROBID's TEI carries no per-element confidence for these
elements, and a made-up number would be worse than an absent one.

Two properties of the real output that the adapter must honour, both measured:

* **A `coords` value can hold several boxes separated by `;`** — one per line for a wrapped span, and
  for a figure one per caption line plus one for the graphic. The title of `Benedek_2015` has 2
  boxes, its `fig_0` has 3. Taking only the first box silently drops most of a multi-line region.
* **`<s>` coordinates appear only with `segmentSentences=1`.**

### 6.1 `teiCoordinates` is a REPEATED form field

Not documented in `LITKB_TOOL_FACTS_2026-09-13.md`, and it silently degrades. Passing the element
list as one comma-joined value is **accepted with HTTP 200** but yields almost nothing:

| How `teiCoordinates` was sent | total `coords` | ref | figure | head | s |
|---|--:|--:|--:|--:|--:|
| one comma-joined value | 7 | 0 | 0 | 0 | 0 |
| one field per element | **1,295** | 189 | 14 | 32 | 491 |

(Same paper — `Benedek_2015` — same service, same request otherwise. These count *elements carrying
a `coords` attribute*; the §4 table counts *boxes*, which is larger because one element can carry
several `;`-separated boxes — 189 `<ref>` elements yield 221 ref boxes.) A caller that gets this wrong sees a valid TEI
with a valid header and no coordinates, and nothing reports an error.

### 6.2 Tests

`Scripts/qc/test_litkb_grobid.py`: **21 fixture-only tests** (no GROBID needed) and **3**
`@pytest.mark.litkb_live` tests that skip unless `LITKB_LIVE=1`. All 24 pass with the service up;
21 pass + 3 skip without it.

§7.1 requires the adapter test to fail when a y-flip or page offset is removed. GROBID needs neither,
so the equivalent mutations are tested instead, and both are shown to be **detected on real
geometry**: dropping the `x1 = x + w` addition, and dropping the `;` multi-box split. The
out-of-page box check is likewise mutation-tested — it is shown to *fire* on a widened box and on a
page with no `<surface>`, so it is a gate and not decoration.

## 7. A WSL lifecycle trap that P5 will hit

When the last `wsl.exe` client exits, WSL begins shutting the distro down and systemd stops every
unit. Observed as `grobid.service: Main process exited, code=exited, status=143` (SIGTERM) while the
distro's own uptime kept climbing — the shutdown was aborted by the next command, but the units
stayed stopped. From the Windows side the symptom is nasty: the service accepts one request, drops it
mid-flight (`RemoteDisconnected` after ~25 s), then refuses every request after. It looks like a
flaky JVM; it is not.

Two fixes, both in this branch:

* the unit is **`systemctl enable`d**, so a genuine distro boot brings it back (seen working: the
  journal shows a `-- Boot --` line followed by `Started grobid.service`);
* the adapter's `start()` **holds the distro open** with one long-lived `sleep infinity` client for
  the life of the Python process, released at interpreter exit. With the hold, Windows-side runs are
  clean. Callers working purely inside the distro should keep a batch in **one** `wsl.exe`
  invocation beginning with `grobid.sh start`.

`process_pdf` also wraps `http.client.HTTPException`/`OSError` into `GrobidError`:
`RemoteDisconnected` is **not** wrapped by urllib, so without that arm it escapes a caller's
`except GrobidError` entirely. This was found by the live test, not by reasoning.

**The machine-wide alternative was deliberately not taken:** setting `vmIdleTimeout` in
`%UserProfile%\.wslconfig` would change Kam's WSL globally.

## 8. What is UNCONFIRMED or not done

1. **The §14 throughput gate is NOT met.** Every timing above is concurrency 1. The gate wants
   pages/s and peak RSS per worker at **two or more pool sizes**, written to
   `extraction_runs.metrics`, with a referee reproducing one rate. Not started. The 7.29 GiB peak is
   a single-worker cgroup figure, not a per-worker RSS.
2. **Three-column layout untested** — measured absent from all 216 PDFs (§4.2).
3. **Scanned pages are not usable from GROBID alone.** An image-only scan returns 200 with an empty
   body parse. OCR must come first; which engine is still open.
4. **204 No Content was never observed.** The design's expectation that an unextractable PDF yields
   204 did not hold for the scan (200, near-empty) or for corrupt files (500). Callers must check
   block counts as well as status.
5. **Whether `<formula>` content is LaTeX** — still unconfirmed; `figure`/`formula` coordinate counts
   were measured but the content was not inspected.
6. **`<ref>` syntax is now confirmed** (it was UNCONFIRMED in the tool facts report):
   `<ref type="bibr" coords="2,99.89,109.80,88.14,7.53" target="#b40">`.
7. **Java 23+ still untested** — this stands up on 21.0.12 only.
8. **Registry titles came from `literature_tracker.csv`**, the claimed record, not a live Crossref
   fetch. A live comparison may move the three failing ratios in either direction.
9. **Reference-parsing quality was not scored.** Counts of `<biblStruct>` are not accuracy; the
   pre-committed gold set of §14 has not been built.
