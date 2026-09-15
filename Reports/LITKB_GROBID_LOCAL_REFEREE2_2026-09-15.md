# Referee report 2 — the GROBID fix round (litkb P4, stage 2)

**Date:** 2026-09-15 · **Branch:** `work/20260914-grobid-local` · **Refereed HEAD:** `90a0d03`
**Under review:** `005ad07..90a0d03` — the builder's answer to the six defects in
`Reports/LITKB_GROBID_LOCAL_REFEREE_2026-09-14.md`
**Contract:** CLAUDE.md §3.4b (instrument → measured file → gated finding), §3.4c (a design is
not accepted on numbers it produced about itself), §3.5 (UNDETERMINED, not "no difference")

**Verdict: STAGE 2 NOT READY — defect D1.** Five of the six referee-1 defects are closed and
reproduced clause by clause. The sixth is closed for `configure`, `start` and
`check-concurrency` but **not for `enable`**, which the brief named and whose own source comment
claims the opposite. The fix is one line and the recheck is one command; the verdict is NOT
READY rather than "ready once" because a gate that does not fire on the path it documents is
not a gate (CLAUDE.md §3.4c).

| Referee-1 defect | Fix | Referee-2 verdict |
|---|---|---|
| 1. no zero-block refusal | `NoTextBlocks` + `check_text_blocks` on `<text><body>` | **CLOSED** — reproduced live, four attacks failed to defeat it |
| 2. concurrency 9 breaks CPU headroom | default 4, `require_concurrency_headroom` | **CLOSED for `configure`/`start`/`check-concurrency`; NOT wired into `enable`** (D1) |
| 3. pdfalto / JVM budget arithmetic wrong | replaced by the measured table in `grobid.sh`'s header | **CLOSED** (read, not re-measured) |
| 4. `extraction_runs.metrics` not written | `extract()` returns the dict; `append_metrics` parks JSONL | **CLOSED** |
| 5. book rate unreplicated | `qc/instruments/litkb_grobid_throughput.py` | **instrument CLOSED; the number 12.11 p/s does NOT reproduce** (D6) |
| 6. §7.1 must name the box | cropbox named in §7.1, the docstring, `page_frames`/`to_mediabox` | **CLOSED** — and the rotation refusal is *necessary*, not cautious (§4) |

Everything below was measured by the referee on 2026-09-15 on the same host, in the worktree
`D:\edmonds-pipeline\treedata-grobid`, `LITKB_TEST_DB=litkb_test_w3`. TEI censuses use the
referee's own `xml.etree` + hand-written `;` splitter, not the adapter, except where the
adapter is itself the object under test. Scratch scripts live in the session scratchpad.
**The service was left stopped** (`is-active` inactive, `is-enabled` disabled, no `java`
process, `grobid.yaml` `concurrency: 4`).

---

## 1. Zero-block refusal — scope, live refusal, and four attempts to defeat it

**Scope is `<text><body>`, confirmed by reading:** `BODY_PATH = ".//t:text/t:body"`;
`body_blocks()` calls `iter_blocks(..., subtree=BODY_PATH)`, which `root.find`s that path and
yields nothing when it is absent; `check_text_blocks` raises when `len(body_blocks(tei)) == 0`.
`process_pdf(..., require_text_blocks=True)` applies it on every 200. The header is therefore
outside the gate, which is the whole point.

**The threshold is `n_blocks >= 1`, on ANY coordinate-bearing element kind** (`kinds=None`), so
one `<s>`, `<p>`, `<note>`, `<head>`, `<ref>` or `<figure>` box anywhere in the body passes. It
is **not tested at 1** — the tests pin Anderson (0 blocks, refused) and a real paper (many,
admitted); nothing pins the boundary.

**Anderson refusal reproduced live** (warm service, pool 4):

```
NoTextBlocks: GROBID returned 200 for Anderson_1957_...pdf but its <text><body> yields no
coordinate-bearing blocks (body text 0 chars, header title 'Institute of Mathematical Statis…')
```

With `require_text_blocks=False` the same TEI is 3,659 B, 22 `<surface>`s, **4 boxes — all of
kind `title`, all in the header**, 1 `biblStruct`, body text 0 chars. Exactly the dangerous
shape referee 1 described, and it is now refused.

**Four attempts to defeat it, all refused.** The attack the brief asks for is "a body with one
junk block":

| Input (referee-built) | Result |
|---|---|
| hand-built one-page PDF whose only content stream is `BT /F1 10 Tf 300 40 Td (42) Tj ET` | **refused** (`NoTextBlocks`) |
| the Anderson scan with that junk page appended (pypdf) | **refused** |
| synthetic PDF: a plausible title line, an author line, and `42` at the foot | **refused** |
| the same plus a `Introduction` heading line | **refused** |

In every case GROBID routed the text into the **header** (`titleStmt`/`persName`) or dropped it,
and emitted an empty `<text><body>`. I could not manufacture a one-junk-block body with a page
number. **Finding: the guard held against every attack I could construct**, but the reason is
GROBID's own behaviour (a page number does not become a body block), not a threshold in the
adapter.

**That the boundary is undefended is measured, not asserted.** Taking the committed
`qc/fixtures/anderson_scan.tei.xml` (0 body blocks, refused) and injecting **one** junk element
into its `<body>` — `<p coords="1,300.0,740.0,12.0,10.0">42</p>`, a page number's worth of box:

```
blocks before: 0
blocks after injecting ONE junk <p> box: 1
check_text_blocks -> 1          # admitted, no refusal, no flag
```

So one spurious body block is enough to pass, and nothing downstream flags it. GROBID declined
to hand me such a TEI on four synthetic PDFs; a real scan with one stray extracted line would.

> **D3 (note, not blocking).** Add that injected fixture as a boundary test, and say in the
> docstring that the rule is `>= 1`, so the next reader does not assume a threshold that is not
> there. Whether `1` is the right number is a stage-2 empirical question; `0` is plainly wrong
> and is now fixed.

## 2. The concurrency guard

Measured by running `grobid.sh` inside the distro, one case per invocation:

| case | rc | behaviour |
|---|--:|---|
| `check-concurrency` (default 4) | 0 | passes |
| `GROBID_CONCURRENCY=5` | **1** | REFUSING … 20% CPU-headroom |
| `GROBID_CONCURRENCY=9` | **1** | REFUSING |
| `GROBID_CONCURRENCY=9 GROBID_BREAK_HEADROOM=1` | 0 | documented bypass |
| **`GROBID_CONCURRENCY=9 GROBID_HEADROOM_MAX_CONCURRENCY=9`** | **0** | **second, undocumented bypass** |
| **`GROBID_CONCURRENCY=abc`** | **0** | `[: abc: integer expected` on stderr, guard PASSES |
| `configure` with `GROBID_CONCURRENCY=9` | **1** | refused; `grobid.yaml` unchanged at 4 |
| **`enable` with `GROBID_CONCURRENCY=9`** | **0** | **not refused**; autostart turned on |
| `configure` with `GROBID_CONCURRENCY=abc` | 0 | **wrote `concurrency: abc` into `grobid.yaml`** |

Restored afterwards: `configure` at the default (yaml back to `concurrency: 4`), `disable`
(`is-enabled` → `disabled`, matching the baseline), service `inactive`.

> **D1 (blocking-class, one line).** `enable) write_unit; systemctl enable grobid` never calls
> `require_concurrency_headroom`, and `write_unit` checks only the JDK. The source comment
> inside `configure()` asserts the opposite in so many words — "the headroom check lives HERE,
> not only in do_start: `configure` (and `enable`, which writes the unit for autostart) is what
> puts a concurrency into grobid.yaml". `enable` does not call `configure` and writes no
> concurrency at all, so the comment is wrong about its own code.
>
> The hole this leaves is real: `GROBID_BREAK_HEADROOM=1 grobid.sh configure` writes 9 into
> `grobid.yaml`, then `grobid.sh enable` arms systemd to run `ExecStart=…/grobid-service server
> …/grobid.yaml` directly on every distro boot — a path that never passes through `do_start` and
> therefore never re-checks the headroom. The knowing override becomes permanent and silent.
> Fix: call `require_concurrency_headroom` (and `configure`) from `enable`, or correct the
> comment and say why `enable` is exempt. Either is a one-liner; a wrong comment in a rulebook
> file is how this project's last several defects propagated (CLAUDE.md preamble).

> **D4 (note).** `GROBID_BREAK_HEADROOM=1` is **not** the only bypass. Raising
> `GROBID_HEADROOM_MAX_CONCURRENCY` bypasses the guard with no warning printed, and a
> non-numeric `GROBID_CONCURRENCY` passes it (`[ abc -gt 4 ]` returns 2, i.e. false) and is then
> `sed`-ed verbatim into `grobid.yaml` — reproduced above, restored. Neither requires malice,
> only a typo. Guard the value is an integer before comparing.

**Kill-criterion mutation test (CLAUDE.md §3.4c: a gate that has never fired is not a gate).**
`[ "$GROBID_CONCURRENCY" -gt "$GROBID_HEADROOM_MAX_CONCURRENCY" ]` → `-gt 99`, then
`LITKB_LIVE=1 pytest qc/test_litkb_grobid.py -k concurrency`:
**1 failed** (`test_launcher_refuses_concurrency_above_the_headroom_default`, `assert 0 != 0`).
Restored; `git diff` on the file empty. The test does fire. It covers only
`check-concurrency`; nothing tests `configure` or `enable`.

## 3. The JDK gate — three cases reproduced

| case | rc | message |
|---|--:|---|
| `GROBID_JDK=/usr/lib/jvm/java-17-openjdk-amd64 check-jdk` | **1** | `REFUSING: '…java-17-openjdk-amd64' is java 17.0.20; GROBID 0.9.1 requires 21 or newer.` |
| `GROBID_JVM_DIR=/opt/nothing check-jdk` | **1** | `REFUSING: no JDK 21 found … falling back to \`java\` on PATH is NOT allowed here.` |
| `check-jdk` (default) | 0 | `JDK ok: /usr/lib/jvm/java-21-openjdk-amd64 (java 21.0.12)` |

All three reproduced. The distro holds four JDK paths (`java-1.17.0-`, `java-1.21.0-`,
`java-17-`, `java-21-openjdk-amd64`), and `find_jdk21`'s `ls -d …/java-21-openjdk*` picks the
21 deterministically.

**Naming note:** the knob is **`GROBID_JDK` / `GROBID_JVM_DIR`, not `JAVA_HOME`.**
`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 check-jdk` returns **0** and reports the 21 —
`find_jdk21` ignores the caller's `JAVA_HOME` entirely and `write_unit` stamps its own
`Environment=JAVA_HOME=` into the unit. That is the correct behaviour (referee 1's defect was
precisely the PATH/`JAVA_HOME` fallback), but it means "the `JAVA_HOME` gate" is a misnomer;
say `GROBID_JDK` when describing it.

## 4. The cropbox frame, and the rotated page the builder left UNCONFIRMED

**Alwan p2/p3 reproduced with the referee's own pypdfium2 census** (union of `get_charbox`
extents for body-block strings occurring exactly once on the page, converted to the mediabox
top-left frame; whole-element single-box strings only):

| | max component offset |
|---|--:|
| GROBID coords compared **raw** against the mediabox | **11.52 pt** (builder: > 5 pt) |
| after `to_mediabox()` | **1.18 pt** (builder: ≤ 2 pt) |

Alwan p2 frame as read by `page_frames`: mediabox `(0,0,612,792)`, cropbox
`(10.3449, 10.7771, 603.4410, 782.9480)`, `dx = 10.345`, `dy = 9.052`. Both clauses reproduce.

**Corpus census (referee's own, `page_frames` over every PDF under `D:\edmonds-pipeline\Literture`
excluding `_quarantine`): 224 PDFs, 4,712 pages, 7 rotated pages, 271 pages with
cropbox ≠ mediabox in 19 files.** The 224 are `Validation` 207, `Labeling` 5,
`_litkb_staging` 5, `ASPP` 4, `other` 3. The builder/referee-1 figures (216 PDFs, 223 pages,
7 rotated) differ because the corpus set differs — 7 rotated pages agrees exactly, the cropped
count does not, so **quote it with its corpus definition or not at all**.

**The rotation finding.** The discriminating question is not the offset on an arbitrary rotated
page — it is whether any rotated page ALSO has cropbox ≠ mediabox, because only there does the
refused conversion cost anything. **The intersection is exactly one page in 4,712:**
`Hall_1985_resampling-coverage-pattern.pdf` p12, rotation 180, mediabox `(0,0,463,685)`,
cropbox `(2,0,463,684)`. (`Guo_2019` p6, the 90° page referee 1 used, has cropbox == mediabox,
so `dx = dy = 0` and the refusal is a no-op there.)

Measured on Hall p12 (551 body blocks; union of every GROBID body box vs the union of every
pypdfium2 character box, the union being robust where unique-string matching found no match):

| interpretation of GROBID's frame | max corner difference |
|---|--:|
| unrotated, cropbox top-left | 10.99 pt |
| **rot-180 displayed, cropbox top-left** | **2.04 pt** |

So GROBID does report a 180° page in the **displayed** frame, as §7.1 and the docstring say —
now measured on the one page where it matters, not assumed.

**And the refusal is necessary, not cautious.** For rotation 180 the map from GROBID's displayed
frame to the canonical mediabox top-left frame is a **reflection**, not a translation:
`x_m = cb.x1 − X`, `y_m = mb.y1 − cb.y0 − Y`. `to_mediabox` applies `x_m = X + dx`,
`y_m = Y + dy`. On Hall p12 those agree nowhere: a block at displayed `x = 49.8` belongs at
`x_m = 413.2` and the translation would put it at `51.8` — **a 361.4 pt error in x**, roughly the
page width; in y a block at displayed `y = 63.2` belongs at `y_m = 621.8` and would land at
`64.2`, a **557.6 pt** error. For a 90° page the axes swap as well. **Not a defect:
refusing is the only correct behaviour available, `frame="cropbox"` tells the caller which
blocks were skipped, and `test_to_mediabox_refuses_a_rotated_page` pins it.** The docstring's
"UNCONFIRMED" understates the case — it is now confirmed that the translation is *wrong* there,
which is a stronger reason to refuse than not knowing.

## 5. The Benedek gate, warm at pool 4

Referee's own census, warm service (a warm-up request first — the instrument's docstring
records that cold TEI differs), `grobid.yaml` `concurrency: 4`:

| clause | builder | referee 2 |
|---|--:|--:|
| TEI bytes | 274,093 | **274,093** |
| coordinate **boxes**, total | 3,760 | **3,760** |
| of which `ref` / `figure` / `head` / `s` | 221 / 37 / 42 / 1,636 | **221 / 37 / 42 / 1,636** |
| `<biblStruct>` | 65 | **65** |
| `<surface>` | 16, numbered 1–16 | **16, numbered 1–16** |
| boxes outside their page | 0 | **0** |
| header title ratio vs tracker **ID 219** | 1.00 | **1.00 PASS** (`title_matches_registry` → `(True, 1.0)`) |

Full kind breakdown, for the record: `s` 1,636, `p` 1,364, `ref` 221, `title` 217, `biblStruct`
182, `head` 42, `formula` 40, `figure` 37, `graphic` 7, `persName` 5, `note` 5, `table` 4.
Identical to referee 1. Reproduced in every clause.

## 6. The metrics dict

`extract()` returns `(tei, metrics)` with exactly:
`body_blocks, concurrency, error, file, frame, host, pages, pages_per_s, peak_rss_bytes,
peak_rss_scope, seconds, stage, started_at, status, tool` — confirmed on Benedek
(`status='ok'`, `pages=16`, `body_blocks=3300`, `frame='cropbox'`, `concurrency=4`,
`peak_rss_bytes=4,586,094,592`).

`extract()` on the Anderson scan **raises**, and the raised error's `.metrics` carries
`status='failed'` with `error="NoTextBlocks: GROBID returned 200 for Anderson_1957…"`.
The §14 clause holds: a refusal is recorded as a failed run, never as an ok run with zero blocks.

> **D5 (note).** The raised type is a bare `GrobidError`, not `NoTextBlocks` — `extract()`
> catches the `NoTextBlocks`, stringifies it into `error`, and re-raises
> `GrobidError(f"{path}: {err}", metrics=metrics)`. A caller writing `except NoTextBlocks`
> around `extract()` (the natural reading of the module docstring) never matches. Re-raise the
> original class, or say in the docstring that `extract` flattens the type.

## 7. The book rate — NOT reproduced

`qc/instruments/litkb_grobid_throughput.py`, 688-page Schneider, `--runs 3`, Benedek warm-up,
pool 4, `--out` to the referee's scratchpad (the tracked JSONL was not touched). Run twice,
because the machine was **not idle**: the brief warned two other agents might be running, and
they were.

Host CPU, `Get-Counter '\Processor(_Total)\% Processor Time'` on the Windows side:

| set | host busy before | run 1 | run 2 | run 3 | median | spread | instrument verdict |
|---|--:|--:|--:|--:|--:|--:|---|
| A | **~47 %** | 7.64 | 8.33 | 12.22 | 8.33 p/s | **55.0 %** | **UNDETERMINED** |
| B | **~15 %** | 9.41 | 9.66 | 9.32 | **9.41 p/s** | **3.6 %** | determined |

Set B satisfies the brief's first condition (spread ≤ 20 %) and **fails the second**: 9.41 vs
the builder's **12.11 p/s** is **22.3 % low**, outside the ±20 % band. Set A's spread is 55 %
and the instrument correctly refused to call it.

**Reading, per §3.5.** The builder's 12.11 p/s is not wrong — my own set A contains a 12.22 p/s
run, and the builder's three committed rows (11.26 / 12.11 / 12.11) are internally tight. It is
**not a property of the workload alone**: across three parties this book has now measured
7.6–12.5 p/s (referee 1: 8.04 p/s median), and the spread tracks host load, not GROBID. So the
honest statement for design §12.10 is a **range with the load stated**, not a point estimate,
and a full-corpus projection built on 12.11 p/s will be optimistic by ~25 %. **That is a
number-quoting correction, not a stage-2 blocker**: the instrument itself behaved exactly as
designed — it fired UNDETERMINED on the contended set and stayed quiet on the clean one.

> **D2 (note, in the instrument).** Its docstring promises "**Idle, and it says so** … because
> 'the machine was idle' is otherwise an assertion", but `cpu_line()` reads `top` and `uptime`
> **inside the distro**, which cannot see Windows-side contention. On set A the distro reported
> `75.6 % id` and `load average: 0.85` while the Windows host was ~47 % busy and the runs varied
> by 55 %. The idleness evidence is measured in the wrong place. Add a host-side counter (one
> `Get-Counter` / `wmic cpu get loadpercentage` line) to the printed record.

## 8. Ladder, diff, and the state left behind

`cd Scripts && LITKB_TEST_DB=litkb_test_w3 PYTHONUTF8=1 py -3.12 qc/check.py --fast`:
ruff **PASS**, compile **PASS**, pytest **1 failed, 2,439 passed, 15 skipped, 1 xfailed** in
1,095.6 s, plus `litkb Postgres tests: 215 passed`. The single failure is the allowed
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]` — **the same one
referee 1 recorded, and the only one**. `check.py` reports FAILED at the pytest rung because of
it; no other test failed.

The 15 skips include the GROBID **live** rungs, which need `LITKB_LIVE=1` and a running JVM and
are therefore NOT part of that pass. They were run separately here, by hand, against the live
service: the JDK and concurrency launcher tests (§2, §3), the Anderson refusal (§1) and the
metrics rungs (§6). A reader should not take the ladder's green as covering them.

`git log -p 005ad07..90a0d03` (1,337 lines) scanned for
`password|secret|api_key|apikey|bearer|PRIVATE KEY|ghp_|AKIA|obuntu` and for any added line
carrying a ≥32-hex run: **no match**. **No credential is committed.** The four added
`.gitignore` lines un-ignore `/phase4/qc/*.jsonl`, whitelisting the measured throughput records
into the same class as the CSVs beside them — correct, and they hide nothing.

Left as found: GROBID `inactive`, autostart `disabled`, no `java` process in the distro,
`grobid.yaml` `concurrency: 4`, worktree clean apart from this report. No other worktree, no
`main`, and no `litkb*` database other than `litkb_test_w3` was touched.

## 9. Defects, in order

1. **D1 — `enable` does not check the concurrency headroom**, and the comment in `configure()`
   states that it does. With a knowing `GROBID_BREAK_HEADROOM=1 configure` beforehand, `enable`
   arms systemd to run the overridden pool on every distro boot through a path that never
   re-checks. One line to fix, or one comment to correct. **Fix before stage 2 runs.**
2. **D4 — the headroom guard has two more ways through**: raising
   `GROBID_HEADROOM_MAX_CONCURRENCY`, and a non-numeric `GROBID_CONCURRENCY`, which passes the
   `[ -gt ]` test and is written verbatim into `grobid.yaml`. Validate the integer.
3. **D2 — the throughput instrument's idleness probe is distro-side** and cannot see the
   contention that actually moves the number. Print a host-side CPU line.
4. **D3 — the zero-block threshold is `>= 1` and is untested at 1.** Four attacks failed to
   defeat it, so this is a gap in the test set, not a demonstrated hole.
5. **D5 — `extract()` flattens `NoTextBlocks` to `GrobidError`**, so `except NoTextBlocks`
   around it never matches.
6. **D6 — the 12.11 p/s book rate does not reproduce** (9.41 p/s determined, 22 % low, on a quieter
   but not idle host). Carry a range into §12.10, not a point.

None of these touch the zero-block refusal, the cropbox frame, the JDK gate, the metrics dict or
the Benedek gate, all of which reproduced clause by clause. **STAGE 2 NOT READY on D1 alone.**
Close it — one line in `grobid.sh`, plus the matching test — and re-run
`LITKB_LIVE=1 pytest qc/test_litkb_grobid.py -k concurrency`; nothing else in this round needs
re-refereeing.
