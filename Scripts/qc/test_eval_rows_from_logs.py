"""eval_rows_from_logs.py parses the per-step evaluate logs — the only record that
survives the cross-VM clobber of semantic_eval_report.csv (2026-09-09). Synthetic log
text in tmp_path only; nothing here reads or writes the lake.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_eval_rows_from_logs.py -q
"""
from __future__ import annotations

import csv
from pathlib import Path

from instruments import eval_rows_from_logs as m

# Shapes copied from real logs (phase4_semantic_finetune_evaluate_2006s_2026-09-02T11-20
# and ..._2021s_2026-08-27T02-27), numbers changed.
IN_SAMPLE = """=== phase4_semantic_finetune --step evaluate_2006s ===
started:   2026-09-09T05:42:10.018499
completed: 2026-09-09T05:44:57.926803
elapsed:   2.8min
errors:    none
version:   v048
command:   --year 2006s --step evaluate --infer-batch 32 --run-tag bb18_2006s_base --force-citywide --encoder resnet18 --no-hillshade --sample-manifest /content/x.csv
year       2006s
gsd cm     100
run id     20260909T054202Z_2006s_bb18_2006s_base_evaluate
dry run    False

--- stdout ---

── [2006s] Step 4: Evaluation (coarse) ──
  Tile-index split mode: DEGRADED/LEAKY(degraded_random)
  Eval tiles: 49  [IN-SAMPLE (no held-out test at this GSD)]
  Model: sem_best_2006s_bb18_2006s_base.pt  (phase=B val_bce=0.4391234)
  ----------------------------------------------------
  IoU=0.2939  Dice=0.4543  Acc=0.7728  Prec=0.5776  Rec=0.3744
  AUROC=0.8011  AP=0.5368  LogLoss=0.4988   [AP is the honest headline]
  Best-F1 @ thresh 0.516  (F1=0.4600  vs  0.4543 @ 0.50)
  @ operating thresh 0.516: IoU=0.2990  Dice=0.4600  Prec=0.5900  Rec=0.3800   (vs IoU=0.2939 @ 0.50)
  Precision-floor @ thresh 0.567  (P=0.720  R=0.367, floor=0.72)
  ✓ Eval rows written → semantic_eval_report.csv  (channels=rgb, run_tag=bb18_2006s_base)
  ◆ DG2 note: 2006s coarse-year IoU=0.294 (in-sample), AUROC=0.801, best-F1 thresh=0.516.
"""

HELD_OUT = """=== phase4_semantic_finetune --step evaluate_2021s ===
started:   2026-08-27T01:44:59.870138
completed: 2026-08-27T02:27:40.326703
errors:    none
command:   --year 2021s --step evaluate --infer-batch 32 --run-tag noise_r5 --force-citywide --infer-aoi
run id     20260827T014454Z_2021s_noise_r5_evaluate

--- stdout ---

── [2021s] Step 4: Evaluation (coarse) ──
  Eval tiles: 147  [held-out test]
  Model: sem_best_2021s_noise_r5.pt  (phase=B val_bce=0.7601995468139648)
  ----------------------------------------------------
  IoU=0.7544  Dice=0.8600  Acc=0.8748  Prec=0.8028  Rec=0.9259
  AUROC=0.9389  AP=0.8892  LogLoss=0.3115   [AP is the honest headline]
  Best-F1 @ thresh 0.457  (F1=0.8610  vs  0.8600 @ 0.50)
  @ operating thresh 0.457: IoU=0.7559  Dice=0.8610  Prec=0.7953  Rec=0.9385   (vs IoU=0.7544 @ 0.50)
  ◆ DG2 note: 2021s coarse-year IoU=0.754 (out-of-sample), AUROC=0.939, best-F1 thresh=0.457.
"""

DIED = """=== phase4_semantic_finetune --step evaluate_2011s ===
started:   2026-09-01T21:09:34.951122
completed: 2026-09-01T21:15:16.380693
errors:    1
command:   --year 2011s --step evaluate --run-tag hy_e3_2011s --force-citywide
run id     20260901T210930Z_2011s_hy_e3_2011s_evaluate

--- notes ---
EXCEPTION:
rasterio.errors.RasterioIOError: 'x.tif' not recognized as being in a supported file format.

--- stdout ---

  Eval tiles: 164  [held-out test]
  Model: sem_best_2011s_hy_e3_2011s.pt  (phase=B val_bce=0.7124515771865845)
"""

REPORT_COLS = ["year", "gsd_cm", "channels", "eval_scope", "scope", "site", "iou",
               "run_tag", "run_id", "written_utc", "encoder", "warm_start"]


def _logs(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    (d / "phase4_semantic_finetune_evaluate_2006s_2026-09-09T05-44.log").write_text(
        IN_SAMPLE, encoding="utf-8")
    (d / "phase4_semantic_finetune_evaluate_2021s_2026-08-27T02-27.log").write_text(
        HELD_OUT, encoding="utf-8")
    (d / "phase4_semantic_finetune_evaluate_2011s_2026-09-01T21-15.log").write_text(
        DIED, encoding="utf-8")
    (d / "phase4_semantic_finetune_train_2021s_2026-08-27T01-00.log").write_text(
        "not an evaluate log\n", encoding="utf-8")
    return d


def _read(p):
    with Path(p).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_in_sample_and_held_out_shapes_parse(tmp_path):
    rows = {r["run_tag"]: r for r in m.harvest(_logs(tmp_path))}
    a = rows["bb18_2006s_base"]
    assert a["run_id"] == "20260909T054202Z_2006s_bb18_2006s_base_evaluate"
    assert a["year"] == "2006s" and a["encoder"] == "resnet18" and a["warm_start"] == ""
    assert a["eval_scope"] == "IN-SAMPLE (no held-out test at this GSD)"
    assert a["n_eval_tiles"] == "49"
    assert a["model_file"] == "sem_best_2006s_bb18_2006s_base.pt"
    assert (a["phase"], a["val_bce"]) == ("B", "0.4391234")
    # the headline line, not the operating-thresh line nor the DG2 note
    assert (a["iou"], a["dice"], a["acc"], a["prec"], a["rec"]) == \
        ("0.2939", "0.4543", "0.7728", "0.5776", "0.3744")
    assert (a["op_thresh"], a["iou_op"], a["dice_op"], a["prec_op"], a["rec_op"]) == \
        ("0.516", "0.2990", "0.4600", "0.5900", "0.3800")
    assert (a["auroc"], a["best_f1_thresh"]) == ("0.8011", "0.516")
    assert a["written_utc"] == "2026-09-09T05:44:57Z"
    assert a["note"] == ""

    b = rows["noise_r5"]
    assert b["eval_scope"] == "held-out test" and b["n_eval_tiles"] == "147"
    assert b["encoder"] == "resnet101"          # default when the flag is absent
    assert b["iou"] == "0.7544" and b["iou_op"] == "0.7559" and b["auroc"] == "0.9389"
    assert b["log_file"] == "phase4_semantic_finetune_evaluate_2021s_2026-08-27T02-27.log"


def test_log_without_metrics_line_yields_blank_metrics_and_a_note(tmp_path):
    rows = {r["run_tag"]: r for r in m.harvest(_logs(tmp_path))}
    d = rows["hy_e3_2011s"]
    assert d["note"] == "no metrics line"
    assert d["eval_scope"] == "held-out test" and d["model_file"].endswith("hy_e3_2011s.pt")
    assert all(d[c] == "" for c in ("iou", "dice", "acc", "prec", "rec", "op_thresh",
                                    "iou_op", "auroc", "best_f1_thresh"))


def test_filename_time_is_the_fallback_when_no_timestamp_line():
    r = m.parse_log("command:   --year 2022 --step evaluate --run-tag x\nrun id     r1\n",
                    "phase4_semantic_finetune_evaluate_2022_2026-09-05T19-56.log")
    assert r["written_utc"] == "2026-09-05T19:56:00Z"


def test_output_is_byte_identical_across_runs_and_sorted_by_run_id(tmp_path):
    logs = _logs(tmp_path)
    o1, o2 = tmp_path / "o1", tmp_path / "o2"
    assert m.main(["--logs-dir", str(logs), "--out-dir", str(o1)]) == 0
    assert m.main(["--logs-dir", str(logs), "--out-dir", str(o2)]) == 0
    b1 = (o1 / "eval_from_logs.csv").read_bytes()
    assert b1 == (o2 / "eval_from_logs.csv").read_bytes()
    assert b"\r" not in b1
    rows = _read(o1 / "eval_from_logs.csv")
    assert list(rows[0].keys()) == m.COLS
    assert [r["run_id"] for r in rows] == sorted(r["run_id"] for r in rows)
    assert len(rows) == 3                       # the train log is ignored


def test_compare_lists_run_ids_absent_from_the_eval_report(tmp_path):
    logs = _logs(tmp_path)
    rep = tmp_path / "semantic_eval_report.csv"
    with rep.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLS)
        w.writeheader()
        # noise_r5 present (OVERALL + a site row); bb18 and hy_e3 absent
        for scope, site in (("OVERALL", "ALL"), ("site", "city")):
            w.writerow({"year": "2021s", "scope": scope, "site": site, "iou": "0.7544",
                        "run_tag": "noise_r5",
                        "run_id": "20260827T014454Z_2021s_noise_r5_evaluate"})
    sup = tmp_path / "semantic_eval_report_superseded.csv"
    with sup.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLS)
        w.writeheader()
        w.writerow({"year": "2011s", "scope": "OVERALL", "site": "ALL", "iou": "",
                    "run_tag": "hy_e3_2011s",
                    "run_id": "20260901T210930Z_2011s_hy_e3_2011s_evaluate"})
    out = tmp_path / "out"
    assert m.main(["--logs-dir", str(logs), "--out-dir", str(out), "--compare",
                   "--eval-report", str(rep)]) == 0
    gaps = _read(out / "eval_report_gaps.csv")
    assert list(gaps[0].keys()) == m.GAP_COLS
    by_id = {g["run_id"]: g for g in gaps}
    assert set(by_id) == {"20260909T054202Z_2006s_bb18_2006s_base_evaluate",
                          "20260901T210930Z_2011s_hy_e3_2011s_evaluate"}
    bb18 = by_id["20260909T054202Z_2006s_bb18_2006s_base_evaluate"]
    assert bb18["verdict"] == "clobber_candidate" and bb18["iou"] == "0.2939"
    assert bb18["encoder"] == "resnet18" and bb18["year"] == "2006s"
    assert by_id["20260901T210930Z_2011s_hy_e3_2011s_evaluate"]["verdict"] == "superseded"
    assert not rep.read_text(encoding="utf-8").count("bb18")   # report never modified


def test_a_per_run_file_turns_a_clobber_candidate_into_on_record(tmp_path):
    """core.py::_write_per_run_eval (2026-09-09) writes every evaluate's rows to
    phase4/eval/runs/semantic_eval_<run_id>.csv before the shared report. A log whose
    run_id has such a file is on record in full — `per_run_file`, not a clobber."""
    from phase4seg.names import EVAL_RUNS_DIRNAME, eval_run_name
    logs = _logs(tmp_path)
    rep = tmp_path / "semantic_eval_report.csv"
    with rep.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLS)
        w.writeheader()
        w.writerow({"year": "2021s", "scope": "OVERALL", "site": "ALL", "iou": "0.7544",
                    "run_tag": "noise_r5",
                    "run_id": "20260827T014454Z_2021s_noise_r5_evaluate"})
    runs = tmp_path / EVAL_RUNS_DIRNAME
    runs.mkdir()
    bb18 = "20260909T054202Z_2006s_bb18_2006s_base_evaluate"
    with (runs / eval_run_name(bb18)).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLS)
        w.writeheader()
        w.writerow({"year": "2006s", "scope": "OVERALL", "site": "ALL", "iou": "0.2939",
                    "run_tag": "bb18_2006s_base", "run_id": bb18})
    # a file named for a run whose rows carry no run_id column: the NAME is the id
    (runs / eval_run_name("20260901T210930Z_2011s_hy_e3_2011s_evaluate")).write_text(
        "year,scope,iou\n2011s,OVERALL,\n", encoding="utf-8")
    out = tmp_path / "out"
    assert m.main(["--logs-dir", str(logs), "--out-dir", str(out), "--compare",
                   "--eval-report", str(rep)]) == 0        # default runs dir: <rep dir>/runs
    by_id = {g["run_id"]: g for g in _read(out / "eval_report_gaps.csv")}
    assert by_id[bb18]["verdict"] == "per_run_file"
    assert by_id["20260901T210930Z_2011s_hy_e3_2011s_evaluate"]["verdict"] == "per_run_file"
    # and WITHOUT the per-run files, the same logs are clobber candidates again
    gaps, _ = m.compare(m.harvest(logs), rep, runs_dir=tmp_path / "no_such_dir")
    assert {g["verdict"] for g in gaps} == {"clobber_candidate"}


def test_pre_run_id_era_gaps_are_not_called_clobbers(tmp_path):
    """The report only started carrying run_id on 2026-08-31; a log from before the
    earliest recorded run_id cannot be joined and must not be reported as lost."""
    rep = tmp_path / "r.csv"
    with rep.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLS)
        w.writeheader()
        w.writerow({"scope": "OVERALL", "run_id": "20260831T013952Z_2019_x_evaluate"})
        w.writerow({"scope": "OVERALL", "run_id": ""})       # pre-era row: blank id
    rows = [{**{c: "" for c in m.COLS}, "run_id": rid, "log_file": rid + ".log"}
            for rid in ("20260822T164927Z_2019_citywide_rgb_evaluate",
                        "20260909T054202Z_2006s_bb18_2006s_base_evaluate")]
    gaps, _ = m.compare(rows, rep)
    assert [g["verdict"] for g in gaps] == ["pre_run_id_era", "clobber_candidate"]


def test_unrecorded_run_ids_are_skipped_not_listed(tmp_path):
    rows = [{**{c: "" for c in m.COLS}, "run_id": "unrecorded", "log_file": "a.log"},
            {**{c: "" for c in m.COLS}, "run_id": "r9", "log_file": "b.log"}]
    gaps, skipped = m.compare(rows, tmp_path / "absent.csv")
    assert skipped == 1 and [g["run_id"] for g in gaps] == ["r9"]
