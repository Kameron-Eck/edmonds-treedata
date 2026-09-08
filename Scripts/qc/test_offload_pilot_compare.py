"""The offload-pilot comparison instrument, on fixtures whose answers are hand-computed.

WHY THESE CASES. `offload_pilot_compare.py` is the file the pilot's PRE-REGISTERED
verdict gets read from (experiments/offload_pilot_2017k.yaml), so the ways it could
quietly lie are the ways the verdict could quietly be wrong:

  a  a full baseline session and a three-runtime pilot — every number present, minutes
     and both spans hand-computed. The pilot's A100 span must cover the GPU SLICE only
     (02:00 to 03:00 = 60 min), not the 165-minute wall clock across three bootstraps.
  b  the pilot has not run. Every pilot cell must be BLANK — and the hardware rows are
     the trap: the first cut filtered `if sessions and session not in sessions`, so an
     empty session set matched EVERY session in the archive and the pilot column filled
     with another campaign's numbers while the pilot had zero queue rows.
  c  tile-set identity, both ways. K2 kills the offload if the CPU-tiled set differs, so
     MATCH and DIFF both have to be produced from the registry, not assumed.
  d  `elapsed:` parsing. StepLogger writes "46.4min", "59.2s" and "1.02h" — three units
     in one field — and the yaml's decision rule quotes those numbers directly. Also:
     `--run-tag` is matched by EQUALITY, so a decoy `of_2017k_b` log cannot be read as
     the baseline's, and the LATEST log per (step, tag) wins.
  e  two runs, byte-identical. A tracked CSV that churns produces a diff on every
     harvest and stops being read.

  f  THE PIN. A tag is not an arm: after the 2026-09-07 ledger recovery, `of_2017k`
     resolves to rows from THREE launches, two of which FAILED, and the run before the
     pin published `tile 9.0 min` and `a100_span 11.5 min` from them. So: the session pin
     picks the right launch out of three; a blank-session row (every row the recovery
     synthesised carries `session=""`) is admitted ONLY inside the window; and both the
     ORACLE shape (an undamaged ledger, full equality with
     `git show 3131741:phase4/qc/offload_pilot_2017k.csv`) and the DAMAGED shape (today's
     real ledger) are asserted — the second one for its exact known blanks and nothing
     else. Two fixtures because a synthetic undamaged ledger tests the pin code and says
     nothing about the archive (CLAUDE.md 3.4c).
  g  the postproc reads: threshold, canopy, polygon count and the two ⏱ ticks. The traps
     are real lines from real logs — `Polygonizing…` and `(vectorized shapely 2.x
     polygonize)` both carry the word and neither is a measurement; `45,532 polygons`
     arrives thousands-separated; and `stage_prob_s` is ABSENT on the arm that read the
     probability raster over FUSE, which is the P4.3 difference under test, not a gap.

Plus the three joins that are easy to get wrong and expensive to get wrong:
  · K1 — a step that RAN AND FAILED must not look like a step that never ran.
  · the machine per step, on each of its three bases in turn (run manifest via
    run_passport, then the per-session heartbeat, then the train log's `Device:` line),
    because the queue records the GPU tier nowhere in its status CSV.
  · the eval report's replace key is (year, channels) and NOT run_tag, so the pilot
    evaluating 2017k/rgb DISPLACES the baseline's rows into
    semantic_eval_report_superseded.csv. The fixture puts the two arms in the two files
    to prove both are read.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_offload_pilot_compare.py -q
"""
import csv
import json

from instruments.offload_pilot_compare import (
    COLS, RECOVERED_PREFIX, STEPS, Pin, main, parse_window, postproc_metrics)
from phase4seg.names import is_status_file

YEAR = "2017k"
BASE_TAG = "of_2017k"
PILOT_TAG = "spd_2017k"

STATUS_HEADER = "job,year,tag,step,state,exit,minutes,detail,ts,host,session"
STATUS_NAME = "train_queue_status_queue_p_20260906T010000Z.csv"

# The shape the pilot really launches in: three hand-split queue files, so THREE status
# files, one per runtime (names.status_out_name = train_queue_status_{stem}_{launch_ts}).
PILOT_STATUS_FILES = [
    ("pilot_offload_2017k_cpu1", "cpu1", "20260907T120000Z"),
    ("pilot_offload_2017k_gpu", "gpu1", "20260907T130000Z"),
    ("pilot_offload_2017k_cpu2", "cpu2", "20260907T140000Z"),
]

# One A100 session, start to finish: 01:00:00 -> 02:20:00 = 80.0 min, and the whole
# session is the GPU slice.  (step, state, minutes, ts, session)
BASELINE = [
    ("labels", "OK", "2.0", "01:00:00", "base1"),
    ("VERIFY:labels", "OK", "", "01:02:00", "base1"),
    ("tile", "OK", "20.0", "01:02:00", "base1"),
    ("VERIFY:tile", "OK", "", "01:22:00", "base1"),
    ("train", "OK", "40.0", "01:22:00", "base1"),
    ("VERIFY:train", "OK", "", "02:02:00", "base1"),
    ("evaluate", "OK", "1.0", "02:02:00", "base1"),
    ("inference", "OK", "10.0", "02:03:00", "base1"),
    ("postproc", "OK", "5.0", "02:13:00", "base1"),
    ("VERIFY", "OK", "", "02:20:00", "base1"),
]

# Three runtimes in sequence. GPU slice = session gpu1: 02:00:00 -> 03:00:00 = 60.0 min.
# Whole pilot = 01:00:00 -> 03:45:00 = 165.0 min, which the yaml states up front will be
# WORSE than the baseline and is not a failure.
PILOT = [
    ("labels", "OK", "1.0", "01:00:00", "cpu1"),
    ("tile", "OK", "25.0", "01:05:00", "cpu1"),
    ("VERIFY:tile", "OK", "", "01:30:00", "cpu1"),
    ("train", "OK", "38.0", "02:00:00", "gpu1"),
    ("VERIFY:train", "OK", "", "02:40:00", "gpu1"),
    ("evaluate", "OK", "1.0", "02:40:00", "gpu1"),
    ("inference", "OK", "16.0", "02:42:00", "gpu1"),
    ("VERIFY:inference", "OK", "", "03:00:00", "gpu1"),
    ("postproc", "OK", "12.0", "03:30:00", "cpu2"),
    ("VERIFY:postproc", "OK", "", "03:45:00", "cpu2"),
]

EVAL_HEADER = ("year,gsd_cm,tier,channels,eval_scope,scope,site,iou,auroc,ap,"
               "run_tag,run_id,written_utc")

# ── the pin fixtures ──────────────────────────────────────────────────────────
# The arm experiments/offload_pilot_2017k.yaml pre-registered, and the two failed
# launches that share its tag.  See `case f` above.
BASE_SESSION = "of2017k2"
BASE_WINDOW = "2026-09-06T01:40:00..2026-09-06T03:34:00"

# THE ORACLE, as the ledger held it before the recovery: 13 queue-written rows, session
# of2017k2, `ts` = the queue-side START of each step. 01:40:30 -> 03:33:31 = 113.0 min.
# The minutes are the baseline column of `git show 3131741:phase4/qc/offload_pilot_2017k.csv`.
ORACLE_MINUTES = {"labels": "2.3", "tile": "21.1", "train": "47.8",
                  "evaluate": "1.1", "inference": "20.3", "postproc": "19.0"}
ORACLE_A100_SPAN = "113.0"
UNDAMAGED = [
    ("labels", "OK", "2.3", "2026-09-06 01:40:30", BASE_SESSION),
    ("VERIFY:labels", "OK", "", "2026-09-06 01:42:50", BASE_SESSION),
    ("tile", "OK", "21.1", "2026-09-06 01:42:50", BASE_SESSION),
    ("VERIFY:tile", "OK", "", "2026-09-06 02:03:57", BASE_SESSION),
    ("train", "OK", "47.8", "2026-09-06 02:03:57", BASE_SESSION),
    ("VERIFY:train", "OK", "", "2026-09-06 02:51:45", BASE_SESSION),
    ("evaluate", "OK", "1.1", "2026-09-06 02:51:45", BASE_SESSION),
    ("VERIFY:evaluate", "OK", "", "2026-09-06 02:52:52", BASE_SESSION),
    ("inference", "OK", "20.3", "2026-09-06 02:52:52", BASE_SESSION),
    ("VERIFY:inference", "OK", "", "2026-09-06 03:13:10", BASE_SESSION),
    ("postproc", "OK", "19.0", "2026-09-06 03:13:10", BASE_SESSION),
    ("VERIFY:postproc", "OK", "", "2026-09-06 03:32:10", BASE_SESSION),
    ("VERIFY", "OK", "", "2026-09-06 03:33:31", BASE_SESSION),
]

# The two FAILED launches, copied from the shape of the real ledger dump: the 09-05
# overlap-floor session where VERIFY:tile came back MISSING, and the 09-06 00:22 launch
# that died. Same year, same tag, different work.
FAILED = [
    ("labels", "OK", "6.4", "2026-09-05 15:02:36", "ofB"),
    ("VERIFY:labels", "OK", "", "2026-09-05 15:09:52", "ofB"),
    ("tile", "OK", "4.1", "2026-09-05 15:09:53", "ofB"),
    ("VERIFY:tile", "MISSING", "", "2026-09-05 15:14:04", "ofB"),
    ("tile", "OK", "9.0", "2026-09-06 00:28:55", "of2017k"),
]

# TODAY'S REAL SHAPE. of2017k2's rows were erased from the shared status CSV by a later
# launch; `rebuild_queue_ledger.py` re-synthesised only the four steps NO snapshot row
# already covered (labels and tile were suppressed, because the failed launches above had
# written rows under those keys), every one with `session=""` and with `ts` set to the
# ENGINE's `completed:` rather than the queue-side start.
_REC = RECOVERED_PREFIX + 'nohup outcome verbatim: "…"; ts=engine-completed@…'
DAMAGED = [
    ("train", "OK", "47.8", "2026-09-06 02:50:58", "", _REC),
    ("VERIFY:train", "OK", "", "2026-09-06 02:50:58", "", _REC),
    ("evaluate", "OK", "1.1", "2026-09-06 02:53:29", "", _REC),
    ("VERIFY:evaluate", "OK", "", "2026-09-06 02:53:29", "", _REC),
    ("inference", "OK", "20.3", "2026-09-06 03:13:02", "", _REC),
    ("VERIFY:inference", "OK", "", "2026-09-06 03:13:02", "", _REC),
    ("postproc", "OK", "19.0", "2026-09-06 03:32:42", "", _REC),
    ("VERIFY:postproc", "OK", "", "2026-09-06 03:32:42", "", _REC),
    ("VERIFY", "OK", "", "2026-09-06 03:32:42", "", _REC),
]


def _status(path, blocks):
    """`ts` may be a bare time (dated 2026-09-06) or a full stamp; `detail` is optional.

    Written with `csv.writer`, the way `queue_ledger.py::_status_write` writes the real
    ledger — NOT by string-joining with hand-placed quotes. A recovered row's `detail`
    quotes the nohup log's outcome line verbatim and so contains `"` of its own; hand
    quoting emits a field the csv reader only recovers from because it is non-strict, and
    a fixture that parses by accident is the failure this file's own docstring warns
    about twice.
    """
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(STATUS_HEADER.split(","))
        for tag, rows in blocks:
            for row in rows:
                step, state, mins, ts, sess = row[:5]
                detail = row[5] if len(row) > 5 else ""
                if "-" not in ts:
                    ts = f"2026-09-06 {ts}"
                w.writerow(["j1", YEAR, tag, step, state, "0", mins, detail,
                            ts, "h1", sess])


def _postproc_stdout(tag, threshold, ha, pct, npoly, polyg_s, stage_s=None):
    """The postproc stdout block, VERBATIM in shape from the real logs — including the
    two decoys (`Polygonizing…`, `(vectorized shapely 2.x polygonize)`) that carry the
    word `polygonize` and are not measurements."""
    stage = (f"  ⏱ stage edmonds_canopy_prob_{YEAR}_{tag}.tif: {stage_s}s\n"
             "  staged the probability raster to local scratch (2.4 GB, one sequential "
             "copy)\n") if stage_s else ""
    return (
        f"\n── [{YEAR}] Step 6: Post-processing ──\n"
        + stage +
        f"  threshold={threshold} [best_f1_thresh (best_f1, rgb, "
        f"semantic_eval_report.csv)] (u8≥142)  min_patch=3.0m²(299px)  "
        f"morph=3×3\n"
        f"  ✓ Mask (local): edmonds_canopy_mask_{YEAR}_{tag}__53fa9684.tif (96 MB)\n"
        f"  Canopy: 1,401,177,099px = {ha} ha true ({pct}% of imaged area)\n"
        f"  Polygonizing…\n"
        f"  (vectorized shapely 2.x polygonize)\n"
        f"  ⏱ polygonize: {polyg_s}s\n"
        f"  ✓ Canopy GeoPackage: edmonds_canopy_mask_{YEAR}_{tag}__a9b212a6.gpkg  "
        f"({npoly} polygons)\n"
        f"  ⏱ postproc: 1079.5s\n")


def _steplog(logs, step, tag, started, elapsed, extra=""):
    name = f"phase4_semantic_finetune_{step}_{YEAR}_2026-09-06T{started}.log"
    (logs / name).write_text(
        f"=== phase4_semantic_finetune --step {step}_{YEAR} ===\n"
        f"started:   2026-09-06T{started.replace('-', ':')}.000000\n"
        f"completed: 2026-09-06T{started.replace('-', ':')}.000000\n"
        f"elapsed:   {elapsed}\n"
        f"errors:    none\n"
        f"command:   --year {YEAR} --step {step} --run-tag {tag} --force-citywide\n"
        f"{extra}\n", encoding="utf-8")
    return name


def _heartbeat(logs, session, gpu):
    """`gpu` is written VERBATIM. vm_heartbeat._gpu() returns None on a CPU runtime —
    nvidia-smi produces no `name,util,mem` line — so `"gpu": null` is the production
    shape of a CPU VM's beacon, not a stand-in for one."""
    (logs / f"heartbeat_{session}.json").write_text(
        json.dumps({"session": session, "gpu": gpu}), encoding="utf-8")


def _passport(path, rows):
    """The tracked view of the run manifests. `gpu` is null on a CPU runtime, which is
    exactly how a CPU-run step is recognised."""
    lines = ["run_id,ts_utc,date,step,run_tag,years,gpu,gpu_mem_gb"]
    for tag, step, gpu in rows:
        lines.append(f"20260906T000000Z_{YEAR}_{tag}_{step},20260906T000000Z,"
                     f"2026-09-06,{step},{tag},{YEAR},{gpu},{'40.0' if gpu else ''}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _registry(path, rows):
    lines = ["tileset_id,label,run_tag,tile_dir,n_tiles"]
    for tag, tsid, n in rows:
        lines.append(f"{tsid},{YEAR},{tag},{YEAR}__{tag},{n}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _evalcsv(path, rows):
    lines = [EVAL_HEADER]
    for tag, scope, ap, auroc, written in rows:
        lines.append(f"{YEAR},10.0,fine,rgb,held-out test,{scope},city,0.34,"
                     f"{auroc},{ap},{tag},rid,{written}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _hw(path, rows):
    """Only the columns this instrument reads; harvest_hw_attribution writes more.

    `phase` is optional per row and defaults to "open"; it is written LAST, where
    harvest_hw_attribution.py::build_rows appends it in the real file.
    """
    lines = ["session,step,basis,gpu_busy_frac,nothing_frac,source_file,phase"]
    for row in rows:
        sess, step, basis, busy, nothing = row[:5]
        phase = row[5] if len(row) > 5 else "open"
        lines.append(f"{sess},{step},{basis},{busy},{nothing},hw_{sess}.csv,{phase}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _sized(path, nbytes):
    path.write_bytes(b"\0" * nbytes)


class Lake:
    """A whole fixture lake under tmp_path, plus the runner that reads it."""

    # The fixture's own sessions ARE its pin. Passing them explicitly (rather than
    # letting the production defaults `of2017k2` / `spdc1,spdg,spdc2` apply) is the
    # point: with the shipped defaults every fixture row would be refused and every
    # assertion below would pass for the wrong reason — blank because nothing matched.
    BASE_PIN = "base1"
    PILOT_PIN = "cpu1,gpu1,cpu2"

    def __init__(self, tmp_path, pilot_rows=PILOT, ids=("ts_base", "ts_pilot"),
                 with_hw=True, with_passport=True, with_heartbeats=True,
                 split_status=False, base_pin=None, pilot_pin=None,
                 base_window="", pilot_window="", baseline_rows=BASELINE,
                 extra_baseline=(), with_late_tile_log=False):
        self.base_pin = self.BASE_PIN if base_pin is None else base_pin
        self.pilot_pin = self.PILOT_PIN if pilot_pin is None else pilot_pin
        self.base_window, self.pilot_window = base_window, pilot_window
        self.root = tmp_path
        self.status = tmp_path / "status"
        self.logs = tmp_path / "logs"
        self.models = tmp_path / "models"
        self.masks = tmp_path / "masks"
        for d in (self.status, self.logs, self.models, self.masks):
            d.mkdir(parents=True)

        blocks = [(BASE_TAG, list(baseline_rows) + list(extra_baseline))]
        if pilot_rows and not split_status:
            blocks.append((PILOT_TAG, pilot_rows))
        _status(self.status / STATUS_NAME, blocks)
        if pilot_rows and split_status:
            for stem, sess, ts in PILOT_STATUS_FILES:
                _status(self.status / f"train_queue_status_{stem}_{ts}.csv",
                        [(PILOT_TAG, [r for r in pilot_rows if r[4] == sess])])

        # (d) three elapsed units, an older attempt, and a PREFIX-matching decoy tag.
        _steplog(self.logs, "train", BASE_TAG, "01-22-00", "46.4min",
                 "  Device: cuda  GPU: NVIDIA A100-SXM4-40GB")
        _steplog(self.logs, "evaluate", BASE_TAG, "02-02-00", "59.2s")
        _steplog(self.logs, "tile", BASE_TAG, "00-30-00", "9.9min")      # older attempt
        _steplog(self.logs, "tile", BASE_TAG, "01-02-00", "20.5min")     # the latest
        _steplog(self.logs, "train", BASE_TAG + "_b", "23-00-00", "99.9min")   # decoy
        if with_late_tile_log:
            # A LATER attempt under the SAME tag — the real shape of the of_2017k logs,
            # where two failed launches wrote 2017k step logs carrying `--run-tag
            # of_2017k`. Latest-by-`started:` picks this one; only the window rejects it.
            _steplog(self.logs, "tile", BASE_TAG, "04-00-00", "77.7min")
        # (g) the postproc reads. The baseline prints NO staging line — that arm read the
        # probability raster over FUSE — so `stage_prob_s` must come out blank for it.
        _steplog(self.logs, "postproc", BASE_TAG, "02-13-00", "5.0min",
                 _postproc_stdout(BASE_TAG, "0.558", "1408.5", "19.6", "45,532", "436.1"))
        if pilot_rows:
            _steplog(self.logs, "train", PILOT_TAG, "02-00-00", "1.02h")
            _steplog(self.logs, "postproc", PILOT_TAG, "03-30-00", "600.0s",
                     _postproc_stdout(PILOT_TAG, "0.594", "1373.1", "19.1", "46,150",
                                      "653.1", stage_s="114.1"))

        if with_heartbeats:
            a100 = {"name": "NVIDIA A100-SXM4-40GB", "util_pct": 0, "util_n": 15}
            _heartbeat(self.logs, "base1", a100)
            _heartbeat(self.logs, "gpu1", a100)
            _heartbeat(self.logs, "cpu1", None)        # what a CPU runtime really writes
            _heartbeat(self.logs, "cpu2", {"name": ""})   # defensive: a nameless device

        self.passport = tmp_path / "run_passport.csv"
        if with_passport:
            rows = [(BASE_TAG, s, "NVIDIA A100-SXM4-40GB") for s in STEPS]
            if pilot_rows:      # no run, no manifest — so no passport row either
                rows += [(PILOT_TAG, s,
                          "NVIDIA A100-SXM4-40GB"
                          if s in ("train", "evaluate", "inference") else "")
                         for s in STEPS]
            _passport(self.passport, rows)

        self.registry = tmp_path / "tileset_registry.csv"
        _registry(self.registry,
                  [(BASE_TAG, ids[0], 632)]
                  + ([(PILOT_TAG, ids[1], 632)] if pilot_rows else []))

        # The baseline's rows sit in the SUPERSEDED archive and the pilot's in the live
        # report — the shape the (year, channels) replace key produces.
        self.eval = tmp_path / "semantic_eval_report.csv"
        _evalcsv(self.eval,
                 [(PILOT_TAG, "site", "0.9900", "0.9900", "2026-09-06T04:00:00Z"),
                  (PILOT_TAG, "OVERALL", "0.4400", "0.8900", "2026-09-06T04:00:00Z")]
                 if pilot_rows else [])
        _evalcsv(self.eval.with_name("semantic_eval_report_superseded.csv"),
                 [(BASE_TAG, "OVERALL", "0.4275", "0.8851", "2026-09-06T02:53:26Z")])

        self.hw = tmp_path / "hw_step_attribution.csv"
        if with_hw:
            _hw(self.hw, [("base1", "train", "interval", "0.1792", "0.2618"),
                          ("base1", "inference", "interval", "0.7586", "0.0985"),
                          ("base1", "ALL", "interval", "0.1933", "0.5083"),
                          # one step, three phases, in the order build_rows sorts
                          # them: launching < open < verifying.
                          ("gpu1", "train", "marker", "0.0000", "0.9500",
                           "launching"),
                          ("gpu1", "train", "marker", "0.6000", "0.1000"),
                          ("gpu1", "train", "marker", "0.0000", "0.9900",
                           "verifying"),
                          ("gpu1", "train", "interval", "0.1111", "0.9999"),
                          ("cpu2", "postproc", "marker", "0.0000", "0.4000"),
                          ("other", "train", "marker", "0.7777", "0.7777")])

        _sized(self.models / f"sem_best_{YEAR}_{BASE_TAG}.pt", 2_000_000)
        _sized(self.masks / f"edmonds_canopy_prob_{YEAR}_{BASE_TAG}.tif", 2_400_000)
        _sized(self.masks / f"edmonds_canopy_mask_{YEAR}_{BASE_TAG}.tif", 500_000)
        _sized(self.masks / f"edmonds_canopy_mask_{YEAR}_{BASE_TAG}.gpkg", 100_000)
        if pilot_rows:
            _sized(self.models / f"sem_best_{YEAR}_{PILOT_TAG}.pt", 1_000_000)

    def run(self, out_name="out.csv"):
        out = self.root / out_name
        assert main(["--year", YEAR, "--baseline-tag", BASE_TAG,
                     "--pilot-tag", PILOT_TAG, "--out", str(out),
                     "--baseline-session", self.base_pin,
                     "--pilot-sessions", self.pilot_pin,
                     "--baseline-window", self.base_window,
                     "--pilot-window", self.pilot_window,
                     "--status-dir", str(self.status), "--logs-dir", str(self.logs),
                     "--models-dir", str(self.models), "--masks-dir", str(self.masks),
                     "--tileset-registry", str(self.registry),
                     "--eval-report", str(self.eval),
                     "--run-passport", str(self.passport),
                     "--hw-attribution", str(self.hw)]) == 0
        return out

    def table(self, out_name="out.csv"):
        out = self.run(out_name)
        rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
        return {(r["metric"], r["step"]): r for r in rows}, out


def test_the_fixture_ledger_file_is_one_the_discovery_rule_admits():
    """Every case below reads the ledger through names.status_files. A fixture name that
    rule REJECTED would leave the instrument reading an EMPTY ledger, and every "blank"
    assertion would pass for the wrong reason. So ask the one rule directly."""
    assert is_status_file(STATUS_NAME)


def _col(t, metric, side):
    return [t[(metric, s)][side] for s in STEPS]


# ── a ─────────────────────────────────────────────────────────────────────────

def test_every_number_is_present_and_hand_checkable(tmp_path):
    t, out = Lake(tmp_path).table()
    assert out.read_text(encoding="utf-8").splitlines()[0] == ",".join(COLS)

    # 1 — the queue's own minutes, both arms
    assert _col(t, "step_minutes", "baseline") == \
        ["2.0", "20.0", "40.0", "1.0", "10.0", "5.0"]
    assert _col(t, "step_minutes", "pilot") == \
        ["1.0", "25.0", "38.0", "1.0", "16.0", "12.0"]
    assert "session=base1" in t[("step_minutes", "train")]["baseline_source"]
    assert "session=gpu1" in t[("step_minutes", "train")]["pilot_source"]

    # 3 — which runtime ran each step: the pilot's split, recovered from the manifests
    assert _col(t, "machine", "baseline") == ["GPU"] * 6
    assert _col(t, "machine", "pilot") == \
        ["CPU", "CPU", "GPU", "GPU", "GPU", "CPU"]
    assert "run_passport.gpu" in t[("machine", "tile")]["note"]

    # 4 — R1. The pilot's A100 span is the GPU SLICE, not the three-runtime wall clock.
    assert t[("a100_span_min", "")]["baseline"] == "80.0"
    assert t[("a100_span_min", "")]["pilot"] == "60.0"
    assert t[("total_span_min", "")]["baseline"] == "80.0"
    assert t[("total_span_min", "")]["pilot"] == "165.0"
    assert "session gpu1" in t[("a100_span_min", "")]["note"]

    # 5 — artifact sizes, decimal MB
    assert t[("sem_best_mb", "train")]["baseline"] == "2.0"
    assert t[("sem_best_mb", "train")]["pilot"] == "1.0"
    assert t[("prob_raster_mb", "inference")]["baseline"] == "2.4"
    assert t[("mask_mb", "postproc")]["baseline"] == "0.5"
    assert t[("gpkg_mb", "postproc")]["baseline"] == "0.1"
    # the pilot has not produced these yet: blank, not zero
    assert t[("prob_raster_mb", "inference")]["pilot"] == ""

    # 7 — the baseline's eval row is in the SUPERSEDED file; both are read
    assert t[("eval_ap", "evaluate")]["baseline"] == "0.4275"
    assert t[("eval_auroc", "evaluate")]["baseline"] == "0.8851"
    assert t[("eval_ap", "evaluate")]["pilot"] == "0.4400"
    assert "superseded" in t[("eval_ap", "evaluate")]["baseline_source"]

    # 8 — sessions come from the queue rows; marker beats interval; `other` is not ours
    assert t[("hw_nothing_frac", "train")]["baseline"] == "0.2618"
    assert t[("hw_gpu_busy_frac", "inference")]["baseline"] == "0.7586"
    assert t[("hw_nothing_frac", "train")]["pilot"] == "0.1000"       # marker, not 0.9999
    assert "basis=marker" in t[("hw_nothing_frac", "train")]["pilot_source"]
    assert t[("hw_nothing_frac", "postproc")]["pilot"] == "0.4000"
    assert t[("hw_nothing_frac", "labels")]["baseline"] == ""         # no sample landed


# ── b ─────────────────────────────────────────────────────────────────────────

def test_pilot_side_is_blank_before_the_pilot_runs(tmp_path):
    """Blank means NOT MEASURED. Nothing on the pilot side may borrow another arm's
    number — the hardware rows especially, whose session filter used to fall open."""
    t, _ = Lake(tmp_path, pilot_rows=None).table()
    for (metric, _step), r in t.items():
        assert r["pilot"] == "", f"{metric} leaked a pilot value: {r['pilot']!r}"
    assert t[("hw_nothing_frac", "train")]["baseline"] == "0.2618"    # baseline intact
    assert t[("step_minutes", "train")]["baseline"] == "40.0"
    assert "pilot not tiled yet" in t[("tileset_id_match", "tile")]["note"]


# ── c ─────────────────────────────────────────────────────────────────────────

def test_tileset_identity_is_read_from_the_registry_both_ways(tmp_path):
    t, _ = Lake(tmp_path / "diff", ids=("a36d6772e88b", "beefcafe1234")).table()
    assert t[("tileset_id", "tile")]["baseline"] == "a36d6772e88b"
    assert t[("tileset_id", "tile")]["pilot"] == "beefcafe1234"
    assert t[("tileset_id_match", "tile")]["note"].startswith("DIFF")
    assert "K2 FIRES" in t[("tileset_id_match", "tile")]["note"]
    assert t[("n_tiles", "tile")]["baseline"] == "632"

    t2, _ = Lake(tmp_path / "match", ids=("a36d6772e88b", "a36d6772e88b")).table()
    assert t2[("tileset_id_match", "tile")]["note"].startswith("MATCH")
    assert "K2 satisfied" in t2[("tileset_id_match", "tile")]["note"]


# ── d ─────────────────────────────────────────────────────────────────────────

def test_elapsed_units_and_run_tag_equality(tmp_path):
    """46.4min, 59.2s, 1.02h and 600.0s — and the decoy tag stays out."""
    t, _ = Lake(tmp_path).table()
    assert t[("step_elapsed_log", "train")]["baseline"] == "46.40"
    assert t[("step_elapsed_log", "evaluate")]["baseline"] == "0.99"   # 59.2 s
    assert t[("step_elapsed_log", "tile")]["baseline"] == "20.50"      # latest, not 9.9
    assert t[("step_elapsed_log", "train")]["pilot"] == "61.20"        # 1.02 h
    assert t[("step_elapsed_log", "postproc")]["pilot"] == "10.00"     # 600 s
    # steps with no log at all stay blank rather than borrowing the queue's minutes
    assert t[("step_elapsed_log", "inference")]["baseline"] == ""
    # the of_2017k_b decoy is a different arm: 99.9 must appear nowhere
    assert "99.90" not in t[("step_elapsed_log", "train")]["baseline"]


# ── e ─────────────────────────────────────────────────────────────────────────

def test_two_runs_are_byte_identical(tmp_path):
    lake = Lake(tmp_path)
    a, b = lake.run("one.csv"), lake.run("two.csv")
    assert a.read_bytes() == b.read_bytes()
    # deterministic emission order: metric blocks in a fixed order, steps in pipeline
    # order — never a set iteration
    rows = list(csv.DictReader(a.read_text(encoding="utf-8").splitlines()))
    assert [r["step"] for r in rows[:6]] == STEPS
    assert [r["metric"] for r in rows[:6]] == ["step_minutes"] * 6


# ── K1, and the two machine fallbacks ─────────────────────────────────────────

def test_a_failed_step_is_not_the_same_as_a_step_that_never_ran(tmp_path):
    """K1: `a step fails on a CPU runtime` has to be readable FROM THIS FILE."""
    rows = [r for r in PILOT if r[0] not in ("postproc", "VERIFY:postproc")]
    rows.append(("postproc", "FAIL", "", "03:30:00", "cpu2"))
    t, _ = Lake(tmp_path, pilot_rows=rows).table()
    assert t[("step_minutes", "postproc")]["pilot"] == ""
    assert "latest state FAIL" in t[("step_minutes", "postproc")]["note"]
    assert t[("step_minutes", "postproc")]["pilot_source"].endswith("session=cpu2")


def test_machine_falls_back_to_the_heartbeat_then_to_the_step_log(tmp_path):
    """The tracked passport is re-harvested AFTER a campaign, so it lags the pilot; the
    per-session heartbeat is what populates the machine column in the meantime."""
    t, _ = Lake(tmp_path / "hb", with_passport=False).table()
    assert _col(t, "machine", "pilot") == ["CPU", "CPU", "GPU", "GPU", "GPU", "CPU"]
    assert "heartbeat" in t[("machine", "train")]["note"]
    assert t[("a100_span_min", "")]["pilot"] == "60.0"

    # last resort: only step_train prints `Device: cuda`, so only train resolves — and
    # the session-level span still covers the whole GPU session.
    t2, _ = Lake(tmp_path / "log", with_passport=False, with_heartbeats=False).table()
    assert t2[("machine", "train")]["baseline"] == "GPU"
    assert t2[("machine", "tile")]["baseline"] == ""
    assert "step log Device" in t2[("machine", "train")]["note"]
    assert t2[("a100_span_min", "")]["baseline"] == "80.0"


def test_three_runtimes_write_three_status_files_and_merge_to_the_same_numbers(tmp_path):
    """PRODUCTION SHAPE. The pilot launches three hand-split queue files, so the queue
    writes three status CSVs — `train_queue_status_pilot_offload_2017k_{cpu1,gpu,cpu2}_
    <ts>.csv` — and every number here comes out of the MERGE across them, not out of one
    file. It also pins that the one discovery rule admits those names: names.py's header
    records a near-miss where a `pilot_*` queue would have been globbed out of the ledger
    and its runs would have appeared in no cost report."""
    for stem, _sess, ts in PILOT_STATUS_FILES:
        assert is_status_file(f"train_queue_status_{stem}_{ts}.csv")

    t, _ = Lake(tmp_path, split_status=True).table()
    assert _col(t, "step_minutes", "pilot") == \
        ["1.0", "25.0", "38.0", "1.0", "16.0", "12.0"]
    assert t[("a100_span_min", "")]["pilot"] == "60.0"
    assert t[("total_span_min", "")]["pilot"] == "165.0"
    assert _col(t, "machine", "pilot") == ["CPU", "CPU", "GPU", "GPU", "GPU", "CPU"]
    # the source names the file the row actually came from, per runtime
    assert "cpu1" in t[("step_minutes", "tile")]["pilot_source"]
    assert "gpu" in t[("step_minutes", "train")]["pilot_source"]
    assert "cpu2" in t[("step_minutes", "postproc")]["pilot_source"]


def test_queue_phase_rows_never_displace_the_engine_step(tmp_path):
    """R4 must read the ENGINE step, not the queue window either side of it.

    hw_step_attribution.csv is one row per (session, step, basis, phase) since the
    marker gained a phase, so one step legitimately owns several rows and they arrive
    in the order harvest_hw_attribution.py::build_rows sorts them — launching, open,
    verifying. This instrument keys on the step alone and keeps the last row at equal
    basis rank, so before the phase filter the alphabetically-last phase won and a
    one-sample VERIFY window was published as the training step's hardware profile.
    """
    t, _ = Lake(tmp_path).table()
    assert t[("hw_gpu_busy_frac", "train")]["pilot"] == "0.6000"   # not 0.0000
    assert t[("hw_nothing_frac", "train")]["pilot"] == "0.1000"    # not 0.9900/0.9500


def test_absent_hardware_attribution_is_reported_not_zeroed(tmp_path):
    """Another instrument owns that file; this one must not fail or fabricate when it is
    not there yet."""
    t, _ = Lake(tmp_path, with_hw=False).table()
    for s in STEPS:
        assert t[("hw_nothing_frac", s)]["baseline"] == ""
        assert t[("hw_gpu_busy_frac", s)]["pilot"] == ""
        assert t[("hw_nothing_frac", s)]["note"] == "hw_step_attribution.csv absent"
    assert t[("step_minutes", "train")]["baseline"] == "40.0"     # nothing else broke


# ── f — THE PIN: a tag is not an arm ──────────────────────────────────────────

class Ledger:
    """A status dir and one heartbeat, and NOTHING else — the pin under a microscope.

    Every other home is deliberately absent (no passport, no registry, no eval report, no
    hardware attribution), so an assertion here can only be about which QUEUE ROWS the
    pin admitted. The machine column then resolves on the heartbeat, which is what makes
    this fixture also exercise `step_session`'s fall-back to the pin: the damaged rows
    carry `session=""` and would otherwise have no session to look a beacon up by.
    """

    def __init__(self, tmp_path, rows, base_pin=BASE_SESSION, base_window=BASE_WINDOW,
                 with_failed=True):
        self.root = tmp_path
        self.base_pin, self.base_window = base_pin, base_window
        for name in ("status", "logs", "models", "masks"):
            setattr(self, name, tmp_path / name)
            getattr(self, name).mkdir(parents=True)
        _status(self.status / STATUS_NAME,
                [(BASE_TAG, list(rows) + (list(FAILED) if with_failed else []))])
        _heartbeat(self.logs, BASE_SESSION,
                   {"name": "NVIDIA A100-SXM4-40GB", "util_pct": 0, "util_n": 15})

    def table(self, out_name="out.csv"):
        out = self.root / out_name
        assert main(["--year", YEAR, "--baseline-tag", BASE_TAG,
                     "--pilot-tag", PILOT_TAG, "--out", str(out),
                     "--baseline-session", self.base_pin,
                     "--baseline-window", self.base_window,
                     "--pilot-sessions", "", "--pilot-window", "",
                     "--status-dir", str(self.status), "--logs-dir", str(self.logs),
                     "--models-dir", str(self.models), "--masks-dir", str(self.masks),
                     "--tileset-registry", str(self.root / "nope_registry.csv"),
                     "--eval-report", str(self.root / "nope_eval.csv"),
                     "--run-passport", str(self.root / "nope_passport.csv"),
                     "--hw-attribution", str(self.root / "nope_hw.csv")]) == 0
        rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
        return {(r["metric"], r["step"]): r for r in rows}, out


def test_the_session_pin_picks_one_launch_out_of_three_that_share_the_tag(tmp_path):
    """THE DEFECT THIS ARGUMENT EXISTS FOR. After the ledger recovery landed on the lake,
    `of_2017k` resolved to rows from three launches — the pre-registered `of2017k2`, an
    earlier 09-06 launch that died, and the 09-05 session where the arm failed at
    VERIFY:tile — and the tag-only selector published `labels 6.4` and `tile 9.0` from
    the failures. Pinning the session has to leave the failures out and say so."""
    t, _ = Ledger(tmp_path, UNDAMAGED).table()
    assert _col(t, "step_minutes", "baseline") == [ORACLE_MINUTES[s] for s in STEPS]
    assert t[("step_minutes", "labels")]["baseline"] != "6.4"     # ofB's
    assert t[("step_minutes", "tile")]["baseline"] not in ("4.1", "9.0")
    for s in STEPS:
        assert f"session={BASE_SESSION}" in t[("step_minutes", s)]["baseline_source"]


def test_the_oracle_baseline_is_reproduced_from_an_undamaged_ledger(tmp_path):
    """EQUALITY WITH THE PUBLISHED ORACLE — the baseline column of
    `git show 3131741:phase4/qc/offload_pilot_2017k.csv`, harvested BEFORE the recovered
    ledger reached the lake. What this proves is that the pin reads an intact ledger the
    way the pre-pin instrument did; it says nothing about today's archive, which is what
    the next case is for (CLAUDE.md 3.4c: a synthetic fixture validates the code, never
    the claim)."""
    t, _ = Ledger(tmp_path, UNDAMAGED).table()
    for step, minutes in ORACLE_MINUTES.items():
        assert t[("step_minutes", step)]["baseline"] == minutes, step
    # 01:40:30 -> 03:33:31, first ts to last VERIFY* ts, over the one pinned session
    assert t[("a100_span_min", "")]["baseline"] == ORACLE_A100_SPAN
    assert t[("total_span_min", "")]["baseline"] == ORACLE_A100_SPAN
    assert f"session {BASE_SESSION}" in t[("a100_span_min", "")]["note"]


def test_the_damaged_ledger_blanks_exactly_what_the_recovery_lost(tmp_path):
    """TODAY'S REAL SHAPE, and the exact diff against the oracle — no more, no less.

    of2017k2's rows were erased from the shared status CSV and exist only as rows
    `rebuild_queue_ledger.py` re-synthesised from a nohup log. Two consequences, both of
    which have to show on the face of the file:

      · `labels` and `tile` were never synthesised at all — the recovery writes a row
        only for a key NO snapshot row covers, and the two failed launches had already
        written rows under those keys. Blank, with a note that distinguishes it from a
        step that never ran.
      · a recovered row's `ts` is the engine's `completed:`, so the span opens 46 minutes
        late: 41.7 min against the session's real 113.0. Publishing that next to the
        pilot's 67.3 would read as a REGRESSION. Blank, with the would-be number in the
        note so nobody recomputes it by hand and trusts it.

    Everything else must be untouched, which is why the assertion is on the DIFF SET."""
    good, _ = Ledger(tmp_path / "undamaged", UNDAMAGED).table()
    bad, _ = Ledger(tmp_path / "damaged", DAMAGED).table()

    changed = {k for k in good if good[k]["baseline"] != bad[k]["baseline"]}
    assert changed == {("step_minutes", "labels"), ("step_minutes", "tile"),
                       ("a100_span_min", ""), ("total_span_min", "")}

    for step in ("labels", "tile"):
        assert bad[("step_minutes", step)]["baseline"] == ""
        assert "NO SURVIVING ROW" in bad[("step_minutes", step)]["note"]
    # the four steps the recovery DID reconstruct still publish their minutes
    for step in ("train", "evaluate", "inference", "postproc"):
        assert bad[("step_minutes", step)]["baseline"] == ORACLE_MINUTES[step]
        assert "blank-session, in-window" in \
            bad[("step_minutes", step)]["baseline_source"]

    for metric in ("a100_span_min", "total_span_min"):
        note = bad[(metric, "")]["note"]
        assert bad[(metric, "")]["baseline"] == ""
        assert "NOT PUBLISHED" in note and "RECOVERED-FROM-LOGS" in note
        assert "41.7" in note          # the lower bound, stated rather than published


def test_a_blank_session_row_is_admitted_only_inside_the_window(tmp_path):
    """The window is the ONLY thing standing between a blank-session row and the arm, so
    it has to hold at both edges and be genuinely optional."""
    inside = list(DAMAGED) + [("labels", "OK", "99.9", "2026-09-06 01:45:00", "", _REC)]
    t, _ = Ledger(tmp_path / "in", inside).table()
    assert t[("step_minutes", "labels")]["baseline"] == "99.9"
    assert "blank-session, in-window" in t[("step_minutes", "labels")]["baseline_source"]

    outside = list(DAMAGED) + [("labels", "OK", "99.9", "2026-09-06 00:50:00", "", _REC)]
    t2, _ = Ledger(tmp_path / "out", outside).table()
    assert t2[("step_minutes", "labels")]["baseline"] == ""

    # no window at all: a blank-session row has nothing to be admitted BY, so the whole
    # recovered baseline drops out — which is why the window is not optional in practice
    t3, _ = Ledger(tmp_path / "nowin", DAMAGED, base_window="").table()
    for s in STEPS:
        assert t3[("step_minutes", s)]["baseline"] == ""


def test_the_pin_admits_nothing_it_was_not_asked_for():
    """A pin that is too tight is the same defect mirrored, so an empty pin still has to
    mean the pre-pin behaviour exactly — every row of the tag, blank sessions included."""
    assert Pin().empty
    assert Pin().admits({"session": "", "ts": "2026-01-01 00:00:00"}) == (True, "")
    assert Pin(["a"]).admits({"session": "a"}) == (True, "session=a")
    ok, rule = Pin(["a"]).admits({"session": "b"})
    assert not ok and "not this arm" in rule
    ok, rule = Pin(["a"]).admits({"session": "", "ts": "2026-01-01 00:00:00"})
    assert not ok and "no window" in rule


def test_the_window_reads_all_three_timestamp_shapes():
    """One window is compared against the ledger's `ts`, the step log's `started:` and
    run_passport's `ts_utc`, which are written in three different formats by three
    different writers. All three are UTC on the same clock."""
    pin = Pin([BASE_SESSION], parse_window(BASE_WINDOW))
    assert pin.in_window("2026-09-06 02:50:58")              # ledger
    assert pin.in_window("2026-09-06T02:04:35.961159")       # step log
    assert pin.in_window("20260906T014248Z")                 # run_passport
    assert not pin.in_window("2026-09-06 00:28:55")          # the failed 00:22 launch
    assert not pin.in_window("20260905T150242Z")             # the 09-05 session
    assert not pin.in_window("")                             # unreadable is never inside


def test_a_later_failed_attempt_does_not_win_the_step_log(tmp_path):
    """`--run-tag` equality is not enough to identify a step log: the failed launches ran
    under the SAME tag and wrote their own. Without the window, latest-by-`started:`
    picks the retry; with it, the arm's own log wins. The passport is pinned on the same
    window for the same reason, so here it drops out and the machine column falls through
    to the heartbeat."""
    t, _ = Lake(tmp_path / "nowin", with_late_tile_log=True).table()
    assert t[("step_elapsed_log", "tile")]["baseline"] == "77.70"   # the wrong log

    t2, _ = Lake(tmp_path / "win", with_late_tile_log=True,
                 base_window="2026-09-06T01:00:00..2026-09-06T02:30:00").table()
    assert t2[("step_elapsed_log", "tile")]["baseline"] == "20.50"
    assert "heartbeat" in t2[("machine", "train")]["note"]      # passport windowed out
    assert t2[("step_minutes", "train")]["baseline"] == "40.0"  # session-pinned rows


# ── g — what postproc actually produced ───────────────────────────────────────

def test_the_postproc_reads_come_off_the_pinned_step_log(tmp_path):
    """R3 is an elapsed time, but a cheaper postproc that segmented a different city is
    not a win. The two arms pick their operating threshold independently — each from its
    OWN eval report — so the cut, the canopy and the polygon count are read, never
    assumed equal."""
    t, _ = Lake(tmp_path).table()
    assert t[("operating_threshold", "postproc")]["baseline"] == "0.558"
    assert t[("operating_threshold", "postproc")]["pilot"] == "0.594"
    assert t[("canopy_pct", "postproc")]["baseline"] == "19.6"
    assert t[("canopy_pct", "postproc")]["pilot"] == "19.1"
    assert t[("canopy_ha", "postproc")]["baseline"] == "1408.5"
    assert t[("canopy_ha", "postproc")]["pilot"] == "1373.1"
    assert t[("n_polygons", "postproc")]["baseline"] == "45532"     # comma stripped
    assert t[("n_polygons", "postproc")]["pilot"] == "46150"
    assert t[("polygonize_s", "postproc")]["baseline"] == "436.1"
    assert t[("polygonize_s", "postproc")]["pilot"] == "653.1"
    # the P4.3 difference: the baseline printed no staging line at all
    assert t[("stage_prob_s", "postproc")]["baseline"] == ""
    assert t[("stage_prob_s", "postproc")]["pilot"] == "114.1"
    assert "BLANK means" in t[("stage_prob_s", "postproc")]["note"]


def test_postproc_parsing_ignores_the_lines_that_only_look_like_measurements():
    """`Polygonizing…` and `(vectorized shapely 2.x polygonize)` both carry the word and
    neither is a number; `staged write:` is not the probability-raster staging tick."""
    text = ("  Polygonizing…\n"
            "  (vectorized shapely 2.x polygonize)\n"
            "  staged write: edmonds_canopy_mask_2017k_of_2017k.tif (96 MB)\n"
            "  ⏱ copy edmonds_canopy_mask_2017k_of_2017k.tif: 0.2s\n"
            "  ⏱ postproc: 1079.5s\n")
    assert postproc_metrics(text) == {}
    assert postproc_metrics("") == {}
    got = postproc_metrics(_postproc_stdout(
        BASE_TAG, "0.594", "1373.1", "19.1", "1,046,150", "653.1", stage_s="114.1"))
    assert got == {"operating_threshold": "0.594", "canopy_ha": "1373.1",
                   "canopy_pct": "19.1", "n_polygons": "1046150",
                   "polygonize_s": "653.1", "stage_prob_s": "114.1"}
