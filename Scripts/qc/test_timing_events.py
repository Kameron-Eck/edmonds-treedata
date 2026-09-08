"""The timing-event instrument, on synthetic logs whose answers are hand-computed.

WHY THESE CASES. `harvest_timing_events.py` turns 2,823 `⏱` lines into the project's
first MEASURED Drive throughput, and every way it can be wrong is a way a storage
decision gets priced wrong:

  a  the two label shapes that carry a filename — `stage X: 309.4s` and `copy Y: 0.0s`.
     The zero-second copy is the division-by-zero the real archive contains 43 times;
     `mb_per_s` must be blank, not a crash and not an infinity.
  b  the header block — run_id / year / run_tag / step read off the log, with `step`
     taken from the command line's bare `--step`, never from the banner's
     year-suffixed one.
  c  the size join, all three outcomes: hit, miss (no such basename), and AMBIGUOUS
     (two different sizes answer to one name — `phase4/masks/` vs its
     `_prerefactor_backup/`). Ambiguous must blank, not pick a side; the same size in
     two directories is not ambiguous.
  d  a label that names no file at all (`inference`) — blank bytes by construction.
  e  the two non-event shapes, kept apart because they are excluded by DIFFERENT parts
     of the pattern: the echoed source line one archived log contains,
     `print(f"  ⏱ {label}: {elapsed:.1f}s")`, is excluded by the required DIGIT RUN;
     a trailing-text line `⏱ copy foo.pt: 12.3s (retry 2/3)` is excluded by the end
     anchor, and it is the only case that exercises the anchor at all.
  f  an unmounted lake — the timings still publish, with every size blank.
  g  byte-identical output across two runs. A tracked CSV that churns produces a diff
     on every harvest and stops being read.
  h  the two ways a blink can erase the archive: an empty log listing (retried) and a
     zero-row harvest landing on a populated CSV (refused).

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_timing_events.py -q
"""
from pathlib import Path

from instruments.harvest_timing_events import (
    COLS,
    build_size_index,
    harvest,
    main,
    parse_header,
    size_for,
)

HEADER = """=== phase4_semantic_finetune --step {banner} ===
started:   2026-09-05T03:00:00.000000
completed: 2026-09-05T03:30:00.000000
elapsed:   30.0min
errors:    none
command:   --year {year} --step {step} --run-tag {tag} --force-citywide
year       {year}
run id     {rid}
dry run    False

--- stdout ---
"""


def _log(logs, name, *, banner, step, year, tag, rid, events=()):
    body = HEADER.format(banner=banner, step=step, year=year, tag=tag, rid=rid)
    body += "".join(f"  ⏱ {label}: {secs}s\n" for label, secs in events)
    (logs / f"phase4_semantic_finetune_{name}.log").write_text(
        body, encoding="utf-8", newline="")


def _lake(root, files):
    """files: {relative path: size in bytes} -> a fake lake root."""
    for rel, size in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\0" * size)
    return root


def test_header_fields_come_from_the_command_line_not_the_banner():
    """(b) The banner's step carries the year label (`evaluate_2006s`); the command
    line's does not. Rows are joined to the queue on the bare step."""
    text = HEADER.format(banner="evaluate_2006s", step="evaluate", year="2006s",
                         tag="t1_2006s_base", rid="20260902T111058Z_2006s_x_evaluate")
    rid, year, tag, step = parse_header(text)
    assert step == "evaluate"
    assert year == "2006s"
    assert tag == "t1_2006s_base"
    assert rid == "20260902T111058Z_2006s_x_evaluate"


def test_header_is_blank_never_guessed_when_absent():
    """The 2026-08 `tile`/`labels` logs predate `--run-tag` entirely."""
    rid, year, tag, step = parse_header(
        "=== phase4_semantic_finetune --step tile_2000 ===\n"
        "command:   --year 2000 --step tile\n")
    assert (rid, year, tag, step) == ("", "2000", "", "tile")


def test_stage_and_copy_rows_carry_rates_and_the_zero_second_copy_does_not(tmp_path):
    """(a) + (c-hit) + (d). 4 000 000 B over 0.1 s is exactly 40.00 MB/s — the figure
    `Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md` §1 quotes unmeasured. The fixture is
    scaled down (a real ortho is 11.5 GB over 309 s); the arithmetic is the same."""
    logs = tmp_path / "logs"
    logs.mkdir()
    lake = _lake(tmp_path / "lake", {
        "Full_Image/Pipeline Imagery/native/big.tif": 4_000_000,
        "phase4/eval/report.csv": 500,
    })
    _log(logs, "a", banner="tile_2020", step="tile", year="2020", tag="tg",
         rid="R1", events=[("stage big.tif", "0.1"),
                           ("copy report.csv", "0.0"),
                           ("inference", "42.5")])

    rows = harvest(logs, build_size_index(lake))
    assert [r["label"] for r in rows] == ["stage big.tif", "copy report.csv",
                                          "inference"]
    stage, copy, infer = rows
    assert stage["bytes"] == 4_000_000
    assert stage["seconds"] == "0.1"
    assert stage["mb_per_s"] == "40.00"
    assert stage["run_id"] == "R1" and stage["step"] == "tile"
    assert stage["log_file"] == "phase4_semantic_finetune_a.log"

    # the file was found, so `bytes` is known — but a rate over zero seconds is not a
    # rate. Blank, never inf, never a ZeroDivisionError.
    assert copy["bytes"] == 500
    assert copy["seconds"] == "0.0"
    assert copy["mb_per_s"] == ""

    # `inference` is a phase, not a transfer: no filename to join on.
    assert infer["bytes"] == "" and infer["mb_per_s"] == ""


def test_size_join_miss_and_ambiguity_both_blank(tmp_path):
    """(c-miss, c-ambiguous). Two DIFFERENT sizes under one basename cannot be told
    apart from the log, so the cell stays empty rather than picking the first walk
    order. The same size in two directories is NOT ambiguous."""
    lake = _lake(tmp_path / "lake", {
        "phase4/masks/m.tif": 100,
        "phase4/masks/_prerefactor_backup/m.tif": 101,        # ambiguous
        "phase4/eval/viz_2000/same.png": 40,
        "phase4/eval/viz_2016/same.png": 40,                  # agrees -> usable
        "phase4/models/only.pt": 7,
    })
    sizes = build_size_index(lake)
    assert sizes["m.tif"] is None
    assert sizes["same.png"] == 40
    assert sizes["only.pt"] == 7

    assert size_for("stage m.tif", sizes) is None             # ambiguous
    assert size_for("copy same.png", sizes) == 40
    assert size_for("stage tiles 2009", sizes) is None        # not a filename at all
    assert size_for("postproc", sizes) is None                # not a transfer

    logs = tmp_path / "logs"
    logs.mkdir()
    _log(logs, "b", banner="postproc_2019n", step="postproc", year="2019n",
         tag="tg", rid="R2", events=[("copy m.tif", "10.0"),
                                     ("stage nosuchfile.tif", "5.0"),
                                     ("copy same.png", "2.0")])
    rows = harvest(logs, sizes)
    assert [(r["bytes"], r["mb_per_s"]) for r in rows] == [
        ("", ""),            # ambiguous
        ("", ""),            # miss
        (40, "0.00"),        # 40 B / 1e6 / 2 s rounds to 0.00 — small, not absent
    ]


def test_the_writers_own_source_line_is_not_an_event(tmp_path):
    """(e) One archived log echoes `print(f"  ⏱ {label}: {elapsed:.1f}s")`. What keeps it
    out is the required DIGIT RUN — `{elapsed:.1f}s` has no digits between the colon and
    the `s`. NOT the end anchor: measured 2026-09-07 over all 507 archived step logs,
    anchored and unanchored patterns match the same 2,823 of 2,824 glyph lines."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _log(logs, "c", banner="train_2016", step="train", year="2016", tag="tg",
         rid="R3", events=[("real", "1.0")])
    with open(logs / "phase4_semantic_finetune_c.log", "a", encoding="utf-8") as f:
        f.write('    print(f"  ⏱ {label}: {elapsed:.1f}s")\n')

    rows = harvest(logs, {})
    assert [r["label"] for r in rows] == ["real"]


def test_a_duration_with_trailing_text_is_not_an_event(tmp_path):
    """(e) THE test that exercises the end anchor, added because the one above does not:
    with the anchor removed this file still passed, so the guard was ungated
    (CLAUDE.md 3.4c — a criterion never shown to fire is not a gate). Trailing text after
    the seconds means the line is not `tock`'s output, and its `12.3` is not a duration
    this instrument may price."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _log(logs, "c2", banner="train_2016", step="train", year="2016", tag="tg",
         rid="R3", events=[("real", "1.0")])
    with open(logs / "phase4_semantic_finetune_c2.log", "a", encoding="utf-8") as f:
        f.write("  ⏱ copy foo.pt: 12.3s (retry 2/3)\n")

    rows = harvest(logs, {})
    assert [r["label"] for r in rows] == ["real"]


def test_unmounted_lake_publishes_timings_with_blank_sizes(tmp_path):
    """(f) The durations come from the LOGS. A lake that is not mounted costs the size
    join, not the measurement."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _log(logs, "d", banner="tile_2020", step="tile", year="2020", tag="tg",
         rid="R4", events=[("stage big.tif", "300.0")])

    sizes = build_size_index(tmp_path / "no-such-lake")
    assert sizes == {}
    rows = harvest(logs, sizes)
    assert len(rows) == 1
    assert rows[0]["seconds"] == "300.0"
    assert rows[0]["bytes"] == "" and rows[0]["mb_per_s"] == ""


def test_rows_sort_by_run_id_then_log_line_order(tmp_path):
    """Deterministic order, and the within-log order is the order the engine printed
    them — the sequence is itself the evidence (stage, then the work, then copy)."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _log(logs, "z_late", banner="tile_2020", step="tile", year="2020", tag="tg",
         rid="R2", events=[("one", "1.0"), ("two", "2.0")])
    _log(logs, "a_early", banner="tile_2020", step="tile", year="2020", tag="tg",
         rid="R1", events=[("three", "3.0")])
    rows = harvest(logs, {})
    assert [(r["run_id"], r["label"]) for r in rows] == [
        ("R1", "three"), ("R2", "one"), ("R2", "two")]


def test_output_is_byte_identical_across_runs(tmp_path):
    """(g) A tracked CSV that churns produces a diff on every harvest, and a file that
    always diffs stops being read."""
    logs = tmp_path / "logs"
    logs.mkdir()
    lake = _lake(tmp_path / "lake",
                 {"Full_Image/Pipeline Imagery/o.tif": 3_000_000})
    _log(logs, "e", banner="tile_2020", step="tile", year="2020", tag="tg",
         rid="R9", events=[("stage o.tif", "0.1"), ("copy o.tif", "0.0")])

    out = tmp_path / "timing_events.csv"
    argv = ["--logs-dir", str(logs), "--lake-root", str(lake), "--out", str(out)]
    assert main(argv) == 0
    first = out.read_bytes()
    assert main(argv) == 0
    assert out.read_bytes() == first

    text = first.decode("utf-8")
    assert text.splitlines()[0] == ",".join(COLS)
    assert "\r" not in text, "lineterminator must be \\n on Windows too"
    assert "3000000,30.00" in text          # 3 MB / 0.1 s


def _populated(out):
    out.write_text("run_id,year,run_tag,step,label,seconds,bytes,mb_per_s,log_file\n"
                   "R1,2020,tg,tile,stage big.tif,309.4,11549324736,37.33,x.log\n",
                   encoding="utf-8", newline="")
    return out.read_bytes()


def test_zero_rows_refuses_to_replace_a_populated_csv(tmp_path):
    """(h) The blink's second door. A log dir that lists fine but yields no events —
    wrong --logs-dir, a mount that vanished mid-walk — must not publish a header-only
    file over 2,823 measured rows and report success."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _log(logs, "f", banner="tile_2020", step="tile", year="2020", tag="tg",
         rid="R0")                                   # a real log, but no ⏱ lines
    out = tmp_path / "timing_events.csv"
    before = _populated(out)

    assert main(["--logs-dir", str(logs), "--lake-root", str(tmp_path / "no-lake"),
                 "--out", str(out)]) == 2
    assert out.read_bytes() == before, "a zero-row harvest must not touch the archive"


def test_allow_empty_is_the_deliberate_override(tmp_path):
    """The refusal is a guard, not a wall: a genuinely emptied archive is publishable
    on purpose."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _log(logs, "g", banner="tile_2020", step="tile", year="2020", tag="tg", rid="R0")
    out = tmp_path / "timing_events.csv"
    _populated(out)

    assert main(["--logs-dir", str(logs), "--lake-root", str(tmp_path / "no-lake"),
                 "--out", str(out), "--allow-empty"]) == 0
    assert out.read_text(encoding="utf-8") == ",".join(COLS) + "\n"


def test_an_empty_log_listing_is_retried_not_believed(tmp_path, monkeypatch):
    """(h) The blink's first door, and the reason the PRIMARY input needs the same
    `lake.py::read_retry` guard the size scan already had: the Drive mirror hands back
    an empty listing for a directory populated a second later (measured 2026-08-31).

    THE SLEEP IS THE GUARD, so it is paid here: one blink costs one 1 s pause, and a
    directory that is genuinely empty costs three before the instrument believes it.
    Do not "optimize" that away.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    seen = []
    real = Path.glob

    def blink_once(self, pat):
        seen.append(pat)
        if len(seen) == 1:
            return iter(())                  # the mirror lies on the first listing
        return real(self, pat)

    _log(logs, "h", banner="tile_2020", step="tile", year="2020", tag="tg",
         rid="R5", events=[("stage big.tif", "2.0")])
    monkeypatch.setattr(Path, "glob", blink_once)
    rows = harvest(logs, {})
    assert len(seen) > 1, "an empty listing must be retried, not published"
    assert [r["label"] for r in rows] == ["stage big.tif"]
