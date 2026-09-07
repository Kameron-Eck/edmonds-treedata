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

from instruments.offload_pilot_compare import COLS, STEPS, main
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


def _status(path, blocks):
    lines = [STATUS_HEADER]
    for tag, rows in blocks:
        for step, state, mins, ts, sess in rows:
            lines.append(f"j1,{YEAR},{tag},{step},{state},0,{mins},,"
                         f"2026-09-06 {ts},h1,{sess}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


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
    """Only the columns this instrument reads; harvest_hw_attribution writes more."""
    lines = ["session,step,basis,gpu_busy_frac,nothing_frac,source_file"]
    for sess, step, basis, busy, nothing in rows:
        lines.append(f"{sess},{step},{basis},{busy},{nothing},hw_{sess}.csv")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _sized(path, nbytes):
    path.write_bytes(b"\0" * nbytes)


class Lake:
    """A whole fixture lake under tmp_path, plus the runner that reads it."""

    def __init__(self, tmp_path, pilot_rows=PILOT, ids=("ts_base", "ts_pilot"),
                 with_hw=True, with_passport=True, with_heartbeats=True,
                 split_status=False):
        self.root = tmp_path
        self.status = tmp_path / "status"
        self.logs = tmp_path / "logs"
        self.models = tmp_path / "models"
        self.masks = tmp_path / "masks"
        for d in (self.status, self.logs, self.models, self.masks):
            d.mkdir(parents=True)

        blocks = [(BASE_TAG, BASELINE)]
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
        if pilot_rows:
            _steplog(self.logs, "train", PILOT_TAG, "02-00-00", "1.02h")
            _steplog(self.logs, "postproc", PILOT_TAG, "03-30-00", "600.0s")

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
                          ("gpu1", "train", "marker", "0.6000", "0.1000"),
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


def test_absent_hardware_attribution_is_reported_not_zeroed(tmp_path):
    """Another instrument owns that file; this one must not fail or fabricate when it is
    not there yet."""
    t, _ = Lake(tmp_path, with_hw=False).table()
    for s in STEPS:
        assert t[("hw_nothing_frac", s)]["baseline"] == ""
        assert t[("hw_gpu_busy_frac", s)]["pilot"] == ""
        assert t[("hw_nothing_frac", s)]["note"] == "hw_step_attribution.csv absent"
    assert t[("step_minutes", "train")]["baseline"] == "40.0"     # nothing else broke
