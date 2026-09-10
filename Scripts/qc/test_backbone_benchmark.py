"""phase4/qc/backbone_benchmark.csv — GENERATED, byte-compared, pinned to its sources.

The resnet101 reference table for the backbone sweep is a projection of
arm_metrics.csv (qc/instruments/backbone_benchmark.py). Three things are gated: the
tracked file is exactly what the instrument regenerates (so it cannot drift from
arm_metrics.csv), the noise-floor rows are what the three 2011s seeds imply (so the
floor cannot be typed), and the sweep experiment's arms are derived from the
instrument's list (so the queue cannot benchmark an arm the table does not hold).

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_backbone_benchmark.py -q
"""
import csv
import io
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent


def _bb():
    """Load the instrument by path — qc/instruments/ is not a package and this repo
    bans new sys.path inserts (test_status_discovery::test_path_insert_ledger)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "backbone_benchmark", SCRIPTS / "qc" / "instruments" / "backbone_benchmark.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_benchmark_csv_is_fresh():
    bb = _bb()
    p = REPO / "phase4" / "qc" / "backbone_benchmark.csv"
    assert p.exists(), "run: py -3.12 qc/instruments/backbone_benchmark.py"
    assert p.read_bytes() == bb.render().encode("utf-8"), (
        "backbone_benchmark.csv is STALE — regenerate: "
        "py -3.12 qc/instruments/backbone_benchmark.py")


def test_render_is_deterministic():
    bb = _bb()
    assert bb.render() == bb.render()
    assert "\r" not in bb.render()


def test_every_arm_has_both_policies_on_the_one_population():
    bb = _bb()
    rows = _rows(bb.render())
    arms = [r for r in rows if r["arm"] != bb.NOISE_FLOOR_LABEL]
    assert len(arms) == len(bb.BENCHMARK_ARMS) * len(bb.POLICIES)
    for r in arms:
        assert r["encoder"] == bb.REFERENCE_ENCODER
        assert r["policy"] in bb.POLICIES
        assert r["curve_id"] and r["thresh"] and r["population"]
    # matched_p75 really holds its floor
    for r in arms:
        if r["policy"] == "matched_p75":
            assert float(r["precision"]) >= 0.75, r


def test_noise_floor_rows_are_derived_from_the_three_seeds():
    bb = _bb()
    rows = _rows(bb.render())
    for pol in bb.POLICIES:
        seeds = [r for r in rows if r["arm"] in bb.NOISE_FLOOR_ARMS and r["policy"] == pol]
        assert len(seeds) == 3
        floor = {r["treatment"]: r for r in rows
                 if r["arm"] == bb.NOISE_FLOOR_LABEL and r["policy"] == pol}
        assert set(floor) == {"min", "max", "spread"}
        for col in ("recall", "precision", "f1"):
            vals = [float(s[col]) for s in seeds]
            assert abs(float(floor["min"][col]) - min(vals)) < 1e-9
            assert abs(float(floor["max"][col]) - max(vals)) < 1e-9
            assert abs(float(floor["spread"][col]) - (max(vals) - min(vals))) < 1e-9


def test_the_recall_floor_matches_the_tier1_verdict():
    """The Tier-1 verdict states the floor it used and names its basis; the table
    must reproduce it or one of the two is wrong."""
    bb = _bb()
    rows = _rows(bb.render())
    spread = next(r for r in rows if r["arm"] == bb.NOISE_FLOOR_LABEL
                  and r["treatment"] == "spread" and r["policy"] == "matched_p75")
    verdict = yaml.safe_load((SCRIPTS / "experiments" / "tier1_science_sample.yaml")
                             .read_text(encoding="utf-8"))["verdict"]
    assert f"= {float(spread['recall']):.4f}" in verdict, (
        f"table floor {spread['recall']} is not the floor the verdict states")


def test_benchmark_encoder_matches_the_run_passports():
    """REFERENCE_ENCODER names what the Tier-1 manifests recorded — checked, not assumed."""
    bb = _bb()
    tags = {t for _, t in bb.BENCHMARK_ARMS}
    seen = set()
    with (REPO / "phase4" / "qc" / "run_passport.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["run_tag"] in tags and r["step"] == "train":
                seen.add(r["encoder"])
    assert seen, "no train passports for the benchmark arms"
    assert seen == {bb.REFERENCE_ENCODER}, seen


def _sweep_spec():
    return yaml.safe_load((SCRIPTS / "experiments" / "backbone_sweep.yaml")
                          .read_text(encoding="utf-8"))


def _phase1_arms(spec):
    """bbNN_ arms — the ImageNet-start record (phase 1)."""
    return [a for a in spec["arms"] if a["tag"].startswith("bb")]


def _warm_arms(spec, prefix="wb"):
    """Warm-started arms. `wb` (any) is the phase-1/phase-2+3 split used by the arm
    census; a full prefix (wb50 / wb18) selects one phase."""
    return [a for a in spec["arms"] if a["tag"].startswith(prefix + "_")
            or (prefix == "wb" and a["tag"].startswith("wb"))]


# (arm prefix, phase-1 twin prefix, ckpt key, tags key, encoder) — one row per warm
# phase, so a new encoder is a row here and not a fork of every gate below.
WARM_PHASES = [
    ("wb50", "bb50", "phase2_ckpt", "phase2_tags", "resnet50"),
    ("wb18", "bb18", "phase3_ckpt", "phase3_tags", "resnet18"),
]


def test_sweep_arms_are_derived_from_the_benchmark_list():
    """experiments/backbone_sweep.yaml: each phase-1 arm is bbNN_<treatment-tag>
    for an encoder in the sweep and a (year, tag) in BENCHMARK_ARMS — every one
    of them, for every encoder. Phase-2 (wb) arms are pinned separately."""
    bb = _bb()
    spec = _sweep_spec()
    encoders = spec["extra"]["encoders"]
    want = set()
    for enc in encoders:
        pre = f"bb{enc.replace('resnet', '')}_"
        for year, tag in bb.BENCHMARK_ARMS:
            want.add((year, pre + tag[len("t1_"):]))
    got = {(str(a["year"]), a["tag"]) for a in _phase1_arms(spec)}
    assert got == want, {"missing": sorted(want - got), "extra": sorted(got - want)}
    assert len(_phase1_arms(spec)) + len(_warm_arms(spec)) == len(spec["arms"]), (
        "an arm is neither bb (phase 1) nor wb (phase 2)")
    for a in _phase1_arms(spec):
        enc = next(e for e in encoders if a["tag"].startswith(f"bb{e.replace('resnet', '')}_"))
        ex = [str(x) for x in a.get("extra") or []]
        assert ex[:2] == ["--encoder", enc], a
        assert "--sample-manifest" in ex, a
        assert "--ckpt" not in ex, ("phase-1 arms are the ImageNet-start record", a)


@pytest.mark.parametrize("prefix,twin_prefix,ckpt_key,tags_key,encoder", WARM_PHASES,
                         ids=[w[0] for w in WARM_PHASES])
def test_warm_arms_are_their_imagenet_twins_plus_the_base_ckpt(
        prefix, twin_prefix, ckpt_key, tags_key, encoder):
    """Phases 2 and 3 (extra.phase2_warm_started / phase3_warm_started_resnet18): each
    wbNN_<t> arm is exactly the bbNN_<t> arm's flags with `--ckpt <base ckpt>` spliced
    in before the trailing --sample-manifest, and the set is the declared tags — which
    must be the subset (a)(b)(c) need: the three-seed floor, the null pair, the positive
    pair and the 2020 base, all derived from the instrument's constants."""
    bb = _bb()
    spec = _sweep_spec()
    ex_ = spec["extra"]
    ck = "/content/drive/MyDrive/treedata/" + ex_[ckpt_key]
    pw = {a["tag"]: a for a in _warm_arms(spec, prefix)}
    assert set(pw) == set(ex_[tags_key]), (set(pw) ^ set(ex_[tags_key]))
    # the subset the decision rule needs, from instrument constants + the declared pairs
    need = {f"{prefix}_{t[len('t1_'):]}" for t in bb.NOISE_FLOOR_ARMS}
    for pair in (ex_["positive_pair"], ex_["null_pair"]):
        need |= {t.replace("bbNN_", prefix + "_") for t in pair}
    need.add(f"{prefix}_2020_base")
    assert set(pw) == need, {"missing": sorted(need - set(pw)), "extra": sorted(set(pw) - need)}
    twins = {a["tag"]: a for a in _phase1_arms(spec) if a["tag"].startswith(twin_prefix + "_")}
    for tag, a in pw.items():
        twin = twins[twin_prefix + "_" + tag[len(prefix) + 1:]]
        assert str(a["year"]) == str(twin["year"]), (tag, a["year"], twin["year"])
        tex = [str(x) for x in twin["extra"]]
        i = tex.index("--sample-manifest")
        want = tex[:i] + ["--ckpt", ck] + tex[i:]
        assert [str(x) for x in a["extra"]] == want, (tag, a["extra"], want)
        assert a["extra"][-2] == "--sample-manifest", ("manifest path must stay LAST", tag)
        assert want[want.index("--encoder") + 1] == encoder, tag


def test_hand_split_queues_are_subsets_of_the_generated_queue(tmp_path):
    """queue_backbone_r18/r50.yaml are HAND-SPLIT (not GENERATED-headered, so the
    drift gate skips them). Every non-canary job must equal a job of the in-memory
    regeneration; canary jobs are short-budget, distinct-tag copies that run first."""
    from experiment_queue import generate
    # The experiment is needs-kam / complete after its runs, and generate() refuses
    # those by design (the result is unsigned; launching is not the next move), so the
    # regeneration this gate compares against runs on a copy with the status flipped
    # to queued — the arms and launch defaults are what the gate compares.
    src = (SCRIPTS / "experiments" / "backbone_sweep.yaml").read_text(encoding="utf-8")
    copy = tmp_path / "backbone_sweep.yaml"
    copy.write_text(src.replace("status: needs-kam", "status: queued", 1)
                       .replace("status: complete", "status: queued", 1), encoding="utf-8")
    text, _ = generate(copy)
    gen = {j["id"]: j for j in yaml.safe_load(text)}
    files = sorted((SCRIPTS / "pipeline").glob("queue_backbone_r*.yaml"))
    assert len(files) == 2, [f.name for f in files]
    # phases 2 and 3 (warm-started wbNN arms): two hand-split files each, NO canary —
    # the flag and the cycle were proven by phase 1; every job carries --ckpt.
    covered = set()
    for prefix, _twin, _ck, _tags, encoder in WARM_PHASES:
        p2_all = sorted((SCRIPTS / "pipeline").glob(f"queue_{prefix}_*.yaml"))
        assert [f.name for f in p2_all] == [f"queue_{prefix}_a.yaml",
                                            f"queue_{prefix}_b.yaml",
                                            f"queue_{prefix}_score.yaml"]
        p2_files, score_file = p2_all[:2], p2_all[2]
        trained = {}
        for q in p2_files:
            head = q.read_text(encoding="utf-8")
            assert head.startswith("# HAND-SPLIT from experiments/backbone_sweep.yaml"), q.name
            for j in yaml.safe_load(head):
                assert j["tag"].startswith(prefix + "_"), (q.name, j["id"])
                assert "--ckpt" in [str(x) for x in j["extra"]], (q.name, j["id"])
                g = gen.get(j["id"])
                assert g, f"{q.name}: job {j['id']} is not in the generated queue"
                for k in ("year", "tag", "extra", "steps"):
                    assert j[k] == g[k], (q.name, j["id"], k, j[k], g[k])
                assert j["id"] not in covered, ("job launched twice", j["id"])
                covered.add(j["id"])
                trained[j["id"]] = j
        # The SCORING queue (Tier-1 Phase-B2 shape, commit ac0e79e): one inference-only
        # job per trained job, same id/year/tag, the training flags with the
        # --sample-manifest pair removed and --infer-aoi <science blocks> appended.
        # --encoder and --ckpt ride along (see the file header for why inference needs both).
        head = score_file.read_text(encoding="utf-8")
        assert head.startswith("# HAND-WRITTEN from experiments/backbone_sweep.yaml"), score_file.name
        score_jobs = yaml.safe_load(head)
        assert [j["id"] for j in score_jobs] == list(trained), "one scoring job per trained job, same order"
        assert score_jobs[-1]["tag"] == f"{prefix}_2020_base", "the slow 2020 arm runs last"
        for j in score_jobs:
            t_ = trained[j["id"]]
            assert j["steps"] == ["inference"], (j["id"], j["steps"])
            assert (j["year"], j["tag"]) == (t_["year"], t_["tag"]), j["id"]
            ex, tx = [str(x) for x in j["extra"]], [str(x) for x in t_["extra"]]
            assert "--sample-manifest" not in ex, j["id"]
            i = tx.index("--sample-manifest")
            assert ex[:-2] == tx[:i] + tx[i + 2:], (j["id"], ex, tx)
            assert ex[-2:] == ["--infer-aoi", "/content/drive/MyDrive/treedata/phase4/qc/"
                                              "science_sample_blocks.gpkg"], j["id"]
            assert ex[ex.index("--encoder") + 1] == encoder and "--ckpt" in ex, j["id"]
    for q in files:
        head = q.read_text(encoding="utf-8")
        assert head.startswith("# HAND-SPLIT from experiments/backbone_sweep.yaml"), q.name
        jobs = yaml.safe_load(head)
        assert jobs[0]["id"].startswith("canary_"), f"{q.name}: first job is not the canary"
        for j in jobs:
            if j["id"].startswith("canary_"):
                assert j["tag"].startswith("canary_"), j
                ex = [str(x) for x in j["extra"]]
                assert "--epochs-phase-a" in ex and "--epochs-phase-b" in ex, j
                assert "--encoder" in ex and "--force-citywide" in ex, j
                assert j["steps"] == ["labels", "tile", "train", "evaluate"], j
                continue
            g = gen.get(j["id"])
            assert g, f"{q.name}: job {j['id']} is not in the generated queue"
            for k in ("year", "tag", "extra", "steps"):
                assert j[k] == g[k], (q.name, j["id"], k, j[k], g[k])
            covered.add(j["id"])
    assert covered == set(gen), {"unlaunched": sorted(set(gen) - covered)}
