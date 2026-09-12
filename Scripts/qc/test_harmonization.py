"""experiments/harmonization_h1_h2.yaml and its two instruments — the gates.

Four things are pinned here, and each one exists because the harmonization design can
fail in that exact way:

  QUEUE SPLIT   Every job in the four hand-split files byte-equals its job in the
                GENERATED pipeline/queue_harmonization_h1_h2.yaml, the two training files
                cover all ten arms exactly once, and EVERY ARM OF ONE YEAR SITS IN ONE
                FILE. That last rule is operational: two A100 runtimes rewrite the shared
                phase4/eval/semantic_eval_report.csv on every evaluate and on 2026-09-09
                one arm's rows landed nowhere (backbone_sweep.yaml
                extra.cross_vm_eval_report_clobber). It is MUTATION-TESTED — a copy with
                one 2006s job moved into the other file must fail — because a rule that
                has never been shown to fire is not known to work (CLAUDE.md 3.4c).
  SCORE SHAPE   Each scoring job is its training twin minus the --sample-manifest pair
                plus --infer-aoi <science blocks>, steps [inference], --encoder and
                --ckpt carried, --hs-source preserved, 2020 last where it appears.
  harm_spread   The tracked phase4/qc/harm_spread.csv is exactly what the instrument
                regenerates; the run_tag parser refuses everything that is not a
                harmonization treatment; and every kill FIRES on a known-bad synthetic
                input and stays silent on the matched control. Two of those known-bad
                inputs are ones this design creates for itself: a SIXTH year (2019s is
                queued here) silently re-populating the pre-registered five-year spread,
                and a cross-year compression whose same-flight gap does not move.
  harm_change_laundering
                The K2 instrument's arithmetic and its kill, on synthetic rasters in
                tmp_path. This tests the CODE, not the claim: the instrument is
                UNVALIDATED on real rasters until the in16 arms land.

Repo-and-tmp_path only — nothing here touches the lake (qc/conftest.py forbids it).

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_harmonization.py -q
"""
import csv
import importlib.util
import io
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
PIPE = SCRIPTS / "pipeline"
EXP = SCRIPTS / "experiments" / "harmonization_h1_h2.yaml"
GEN = PIPE / "queue_harmonization_h1_h2.yaml"
BLOCKS = "/content/drive/MyDrive/treedata/phase4/qc/science_sample_blocks.gpkg"
TRAIN_FILES = ["queue_harm_h1.yaml", "queue_harm_h2.yaml"]
SCORE_FILES = ["queue_harm_h1_score.yaml", "queue_harm_h2_score.yaml"]


def _load(name):
    """Load an instrument by path — qc/instruments/ is not a package and this repo bans
    new sys.path inserts (test_status_discovery::test_path_insert_ledger)."""
    spec = importlib.util.spec_from_file_location(
        name, SCRIPTS / "qc" / "instruments" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _jobs(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _generated():
    """The generated queue view of the experiment. While the experiment was live this
    was the tracked pipeline/queue_harmonization_h1_h2.yaml; a complete experiment
    carries no generated queue (test_experiments.py), so the view is rebuilt in memory
    from the spec with its status forced back to queued — the historical split checks
    below stay meaningful without a stale file on disk."""
    if GEN.exists():
        return {j["id"]: j for j in _jobs(GEN)}
    import tempfile
    from experiment_queue import generate
    spec = yaml.safe_load(EXP.read_text(encoding="utf-8"))
    spec["status"] = "queued"
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=EXP.parent, delete=False,
                                     encoding="utf-8", prefix="_tmp_harm_") as fh:
        fh.write(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
        tmp = Path(fh.name)
    try:
        text, _ = generate(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return {j["id"]: j for j in yaml.safe_load(text)}


# --------------------------------------------------------------- the queue split

def test_generated_queue_holds_every_arm_of_the_experiment():
    spec = yaml.safe_load(EXP.read_text(encoding="utf-8"))
    gen = _generated()
    assert len(gen) == len(spec["arms"]) == 10, (len(gen), len(spec["arms"]))
    assert {j["tag"] for j in gen.values()} == {a["tag"] for a in spec["arms"]}


def test_hand_split_queues_are_subsets_of_the_generated_queue():
    gen = _generated()
    covered = set()
    for name in TRAIN_FILES:
        head = (PIPE / name).read_text(encoding="utf-8")
        assert head.startswith("# HAND-SPLIT from experiments/harmonization_h1_h2.yaml"), name
        for j in _jobs(PIPE / name):
            g = gen.get(j["id"])
            assert g, f"{name}: job {j['id']} is not in the generated queue"
            for k in ("year", "tag", "extra", "steps"):
                assert j[k] == g[k], (name, j["id"], k, j[k], g[k])
            assert j["steps"] == ["labels", "tile", "train", "evaluate"], j["id"]
            assert j["extra"][-2] == "--sample-manifest", ("manifest LAST", j["id"])
            assert j["id"] not in covered, ("job launched twice", j["id"])
            covered.add(j["id"])
    assert covered == set(gen), {"unlaunched": sorted(set(gen) - covered)}


def year_file_map(files, root=PIPE):
    """{year: {file names holding a job for it}} — the one-runtime-per-year read."""
    out = {}
    for name in files:
        for j in _jobs(Path(root) / name):
            out.setdefault(str(j["year"]), set()).add(name)
    return out


def test_every_arm_of_one_year_sits_on_one_runtime():
    for year, files in year_file_map(TRAIN_FILES).items():
        assert len(files) == 1, (
            f"year {year} is split across {sorted(files)} — two A100 runtimes rewrite "
            f"phase4/eval/semantic_eval_report.csv on every evaluate and one arm's rows "
            f"land nowhere (backbone_sweep.yaml extra.cross_vm_eval_report_clobber)")


def test_the_one_runtime_per_year_rule_fires_on_a_split_year(tmp_path):
    """MUTATION TEST. Move one 2006s job out of h1 and into h2 and the rule must fail —
    a gate that has never fired is not known to work (CLAUDE.md 3.4c)."""
    h1 = _jobs(PIPE / "queue_harm_h1.yaml")
    h2 = _jobs(PIPE / "queue_harm_h2.yaml")
    moved = next(j for j in h1 if str(j["year"]) == "2006s")
    h1 = [j for j in h1 if j["id"] != moved["id"]]
    (tmp_path / "queue_harm_h1.yaml").write_text(yaml.safe_dump(h1), encoding="utf-8")
    (tmp_path / "queue_harm_h2.yaml").write_text(yaml.safe_dump(h2 + [moved]),
                                                 encoding="utf-8")
    spread = year_file_map(TRAIN_FILES, root=tmp_path)
    assert len(spread["2006s"]) == 2, "the mutation did not actually split the year"
    assert any(len(f) > 1 for f in spread.values()), "the rule failed to notice"


def test_score_queues_are_the_inference_twins():
    for train_name, score_name in zip(TRAIN_FILES, SCORE_FILES):
        trained = {j["id"]: j for j in _jobs(PIPE / train_name)}
        head = (PIPE / score_name).read_text(encoding="utf-8")
        assert head.startswith("# HAND-WRITTEN from experiments/harmonization_h1_h2.yaml"), score_name
        jobs = _jobs(PIPE / score_name)
        assert [j["id"] for j in jobs] == list(trained), (
            f"{score_name}: one scoring job per trained job, same order")
        for j in jobs:
            t = trained[j["id"]]
            assert j["steps"] == ["inference"], (j["id"], j["steps"])
            assert (j["year"], j["tag"]) == (t["year"], t["tag"]), j["id"]
            ex, tx = [str(x) for x in j["extra"]], [str(x) for x in t["extra"]]
            assert "--sample-manifest" not in ex, j["id"]
            i = tx.index("--sample-manifest")
            assert ex[:-2] == tx[:i] + tx[i + 2:], (j["id"], ex, tx)
            assert ex[-2:] == ["--infer-aoi", BLOCKS], j["id"]
            assert ex[ex.index("--encoder") + 1] == "resnet18" and "--ckpt" in ex, j["id"]
            if "--hs-source" in tx:
                assert ex[ex.index("--hs-source") + 1] == tx[tx.index("--hs-source") + 1]
        tags = [j["tag"] for j in jobs]
        slow = [t for t in tags if "_2020_" in t]
        if slow:
            assert tags[-1] == slow[-1], f"{score_name}: the 2020 arm must run last"


def test_no_arm_passes_the_inert_tier_flag():
    """--tier is consulted only when --year is absent (cli.py::_resolve_years) and the queue always
    passes --year, so a --tier in a job is a recipe claim the run will not honour."""
    for name in TRAIN_FILES + SCORE_FILES:
        for j in _jobs(PIPE / name):
            assert "--tier" not in [str(x) for x in j["extra"]], (name, j["id"])
    for j in _generated().values():
        assert "--tier" not in [str(x) for x in j["extra"]], ("generated", j["id"])


# --------------------------------------------------------------- harm_spread

HEADER = ("curve_id,year,run_tag,ref,prob,canopy_def,eval_scope,policy,k,thresh,recall,"
          "precision,f1,tp,fn,fp,population,pr_auc,n_cuts,n_eligible_cuts,source,"
          "curve_file\n")


def _metrics(tmp_path, rows, name="arm_metrics.csv"):
    """A synthetic arm_metrics.csv: rows are (run_tag, year, ref, recall)."""
    p = tmp_path / name
    body = "".join(
        f"c{i:04d},{year},{tag},{ref},prob.tif,forest_wetland,sample-test,matched_p75,"
        f",0.3,{recall},0.75,0.7,1,1,1,pop,,,,x,\n"
        for i, (tag, year, ref, recall) in enumerate(rows))
    p.write_text(HEADER + body, encoding="utf-8")
    return p


LABELS = {"2006s", "2011s", "2016", "2019n", "2019s", "2020"}
R21 = "ccap_2021_hires_lc.tif"
R16 = "ccap_2016_hires_lc.tif"


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def _pick(rows, **kw):
    hits = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    assert len(hits) == 1, (kw, hits)
    return hits[0]


def test_tracked_harm_spread_csv_is_fresh():
    hs = _load("harm_spread")
    p = REPO / "phase4" / "qc" / "harm_spread.csv"
    assert p.exists(), "run: py -3.12 qc/instruments/harm_spread.py"
    # CRLF-safe: a fresh Windows checkout (core.autocrlf=true, no eol= by design —
    # see .gitattributes) writes CRLF while the renderer emits LF; compare content,
    # not line terminators. The LF-only property is asserted separately below.
    assert p.read_bytes().replace(b"\r\n", b"\n") == hs.render().encode("utf-8"), (
        "harm_spread.csv is STALE — regenerate: py -3.12 qc/instruments/harm_spread.py")


def test_render_is_deterministic_and_lf_only():
    hs = _load("harm_spread")
    assert hs.render() == hs.render()
    assert "\r" not in hs.render()


def test_the_parser_refuses_everything_that_is_not_a_treatment():
    hs = _load("harm_spread")
    assert hs.parse_tag("wb18_2016_in16", LABELS) == ("wb18", "2016", "in16")
    for bad in ("wb18_2011s_base_s2",     # a seed replicate, not a treatment
                "wb18_2011s_cor05",       # a corruption dose
                "t1_2016_nir",            # a different input
                "t1_2006s_add16",         # an adder arm
                "hy_e3_2006s",            # another campaign entirely
                "wb18_1999_base"):        # not a YEAR_CATALOG label
        assert hs.parse_tag(bad, LABELS) is None, bad


def test_real_arm_metrics_reproduce_the_designs_cited_spreads():
    """REAL DATA, not synthetic (CLAUDE.md 3.4c). The design cites a five-year resnet101
    base spread and a three-year warm-started resnet18 base spread, both read from
    phase4/qc/arm_metrics.csv. If this instrument does not reproduce them, its filter or
    its parser is wrong and every number it prints tonight would be wrong with it."""
    hs = _load("harm_spread")
    rows = _rows(hs.render())
    t1 = _pick(rows, prefix="t1", treatment="base", ref=R21, quantity="spread")
    assert t1["n_years"] == "5" and t1["value"] == "0.1406", t1
    wb = _pick(rows, prefix="wb18", treatment="base", ref=R21, quantity="spread")
    if wb["n_years"] == "3":          # the pre-EXP-H1 record; it grows to 5 tonight
        assert wb["value"] == "0.0224", wb
    # ...and the H2-K1 interaction the design predicts will fire, on the r101 record
    k1 = _pick(rows, prefix="t1", ref=R21, quantity="k1_interaction")
    assert k1["flag"] == "H2-K1 LEAK" and k1["value"] == "0.0325", k1
    # ...and it fires against BOTH references on the real record (0.0325 / 0.0256), so
    # the two-reference clause reads LEAK rather than UNDETERMINED.
    v = _pick(rows, prefix="t1", quantity="k1_ref_verdict")
    assert v["flag"] == "H2-K1 LEAK (BOTH REFS)" and v["value"] == "0.0256", v


def test_h1_k1_fires_when_the_spread_collapses(tmp_path):
    """KNOWN-BAD INPUT: five base years inside 2x the floor. The premise of EXP-H2 is
    that the years disagree; if they do not, H2 has nothing to compress."""
    hs = _load("harm_spread")
    flat = [(f"wb18_{y}_base", y, R21, 0.7400 + i * 0.002)
            for i, y in enumerate(hs.H1_YEARS)]        # spread 0.008 <= 0.014
    rows = _rows(hs.render(_metrics(tmp_path, flat), LABELS))
    r = _pick(rows, prefix="wb18", treatment="base", ref=R21, quantity="h1_premise")
    assert r["flag"] == "H2 premise dead" and r["n_years"] == "5", r


def test_h1_k1_stays_silent_on_a_real_spread_and_on_an_incomplete_one(tmp_path):
    hs = _load("harm_spread")
    wide = [(f"wb18_{y}_base", y, R21, 0.60 + i * 0.03) for i, y in enumerate(hs.H1_YEARS)]
    r = _pick(_rows(hs.render(_metrics(tmp_path, wide), LABELS)),
              prefix="wb18", treatment="base", ref=R21, quantity="h1_premise")
    assert r["flag"] == "SPREAD EXCEEDS 2xFLOOR", r
    short = [(f"wb18_{y}_base", y, R21, 0.740) for y in hs.H1_YEARS[:3]]
    r = _pick(_rows(hs.render(_metrics(tmp_path, short, "short.csv"), LABELS)),
              prefix="wb18", treatment="base", ref=R21, quantity="h1_premise")
    assert r["flag"] == "INCOMPLETE", (
        "a three-year set inside the floor is UNDETERMINED, never a premise-dead pass", r)


def test_h2_k1_separates_a_leak_from_a_uniform_chm_quality_effect(tmp_path):
    """The leak signature is the INTERACTION. A channel that helps EVERY year equally is
    a CHM-quality effect (experiments/old_chm_defect.yaml) and must NOT fire."""
    hs = _load("harm_spread")
    leak = [("wb18_2006s_in05", "2006s", R21, 0.60), ("wb18_2006s_in16", "2006s", R21, 0.65),
            ("wb18_2016_in05", "2016", R21, 0.75), ("wb18_2016_in16", "2016", R21, 0.75)]
    r = _pick(_rows(hs.render(_metrics(tmp_path, leak), LABELS)),
              prefix="wb18", ref=R21, quantity="k1_interaction")
    assert r["flag"] == "H2-K1 LEAK" and r["value"] == "0.0500", r
    uniform = [("wb18_2006s_in05", "2006s", R21, 0.60), ("wb18_2006s_in16", "2006s", R21, 0.65),
               ("wb18_2016_in05", "2016", R21, 0.75), ("wb18_2016_in16", "2016", R21, 0.80)]
    r = _pick(_rows(hs.render(_metrics(tmp_path, uniform, "u.csv"), LABELS)),
              prefix="wb18", ref=R21, quantity="k1_interaction")
    assert r["flag"] == "" and r["value"] == "0.0000", r


def test_h1_k2_fires_when_the_spread_is_mostly_reference_epoch(tmp_path):
    hs = _load("harm_spread")
    rows = ([(f"wb18_{y}_base", y, R21, r) for y, r in
             zip(hs.H1_YEARS, (0.60, 0.70, 0.72, 0.74, 0.76))]
            + [(f"wb18_{y}_base", y, R16, r) for y, r in
               zip(hs.H1_YEARS, (0.700, 0.705, 0.710, 0.715, 0.720))])
    r = _pick(_rows(hs.render(_metrics(tmp_path, rows), LABELS)),
              prefix="wb18", quantity="ref_epoch_share")
    assert r["flag"] == "H1-K2 METRIC KILLED", r      # 0.02 <= 0.4 * 0.16


def test_h2_convergence_and_same_flight_gap(tmp_path):
    hs = _load("harm_spread")
    base = [(f"wb18_{y}_base", y, R21, r) for y, r in
            zip(hs.H1_YEARS, (0.60, 0.70, 0.72, 0.74, 0.76))]
    in16 = [(f"wb18_{y}_in16", y, R21, r) for y, r in
            zip(hs.H1_YEARS, (0.70, 0.72, 0.73, 0.74, 0.75))]
    pair = [("wb18_2019s_base", "2019s", R21, 0.68), ("wb18_2019s_in16", "2019s", R21, 0.735)]
    rows = _rows(hs.render(_metrics(tmp_path, base + in16 + pair), LABELS))
    p = _pick(rows, prefix="wb18", quantity="convergence_p", ref=R21)
    assert p["flag"] == "H2-P CONVERGENCE" and p["value"] == "-0.1100", p
    gb = _pick(rows, prefix="wb18", treatment="base", quantity="same_flight_gap")
    gi = _pick(rows, prefix="wb18", treatment="in16", quantity="same_flight_gap")
    assert gb["value"] == "0.0600" and gi["value"] == "0.0050"
    assert "sampling support" in gb["note"], (
        "the row must carry what still differs between the two 2019 arms — sampling "
        "support, NOT recipe: every arm runs --force-citywide", gb["note"])
    # H2-K3 is the CHANGE in that gap, and it is COMPUTED, not left to the reader.
    k3 = _pick(rows, prefix="wb18", quantity="k3_gap_change", ref=R21)
    assert k3["value"] == "-0.0550" and k3["flag"] == "H2-K3 GAP SHRINKS", k3


def test_h2_k3_does_not_pass_a_gap_that_holds(tmp_path):
    """KNOWN-BAD INPUT for K3: the cross-year spread compresses but the same-flight gap
    barely moves. That is the case the design calls UNINTERPRETABLE, and the kill has to
    say so rather than staying silent while (P) promotes."""
    hs = _load("harm_spread")
    base = [(f"wb18_{y}_base", y, R21, r) for y, r in
            zip(hs.H1_YEARS, (0.60, 0.70, 0.72, 0.74, 0.76))]
    in16 = [(f"wb18_{y}_in16", y, R21, r) for y, r in
            zip(hs.H1_YEARS, (0.70, 0.72, 0.73, 0.74, 0.75))]
    pair = [("wb18_2019s_base", "2019s", R21, 0.68), ("wb18_2019s_in16", "2019s", R21, 0.682)]
    rows = _rows(hs.render(_metrics(tmp_path, base + in16 + pair), LABELS))
    p = _pick(rows, prefix="wb18", quantity="convergence_p", ref=R21)
    assert p["flag"] == "H2-P CONVERGENCE", "(P) still promotes — that is the whole point"
    k3 = _pick(rows, prefix="wb18", quantity="k3_gap_change", ref=R21)
    assert k3["value"] == "-0.0020", k3            # inside the 0.0069 floor
    assert k3["flag"] == "H2-K3 NO SHRINK - CROSS-YEAR UNINTERPRETABLE", k3


def test_a_sixth_year_cannot_enter_the_pre_registered_spread(tmp_path):
    """KNOWN-BAD INPUT, and it is the input this design itself creates: the 2019s arms
    are queued here, so the five-year spread would quietly become a six-year one.

    On the old code this exact table read spread(base)=0.3400 and (P)=-0.0100 with NO
    flag — a promote at 4x the spread floor suppressed by an unregistered population,
    because a six-element set is neither a superset failure nor a strict subset. The
    aggregates are DEFINED on H1_YEARS; 2019s keeps its per-arm recall row and nothing
    more."""
    hs = _load("harm_spread")
    base = [(f"wb18_{y}_base", y, R21, r) for y, r in
            zip(hs.H1_YEARS, (0.60, 0.70, 0.72, 0.74, 0.74))]      # spread 0.14
    in16 = [(f"wb18_{y}_in16", y, R21, r) for y, r in
            zip(hs.H1_YEARS, (0.66, 0.70, 0.72, 0.74, 0.74))]      # spread 0.08
    out = [("wb18_2019s_base", "2019s", R21, 0.94),                # would stretch to 0.34
           ("wb18_2019s_in16", "2019s", R21, 0.99)]                # ...and (P) to -0.01
    rows = _rows(hs.render(_metrics(tmp_path, base + in16 + out), LABELS))
    sp = _pick(rows, prefix="wb18", treatment="base", ref=R21, quantity="spread")
    assert sp["value"] == "0.1400" and sp["n_years"] == "5", sp
    assert "2019s" not in sp["years"], sp
    prem = _pick(rows, prefix="wb18", treatment="base", ref=R21, quantity="h1_premise")
    assert prem["flag"] == "SPREAD EXCEEDS 2xFLOOR" and prem["value"] == "0.1400", prem
    p = _pick(rows, prefix="wb18", quantity="convergence_p", ref=R21)
    assert p["value"] == "-0.0600" and p["flag"] == "H2-P CONVERGENCE", p
    assert _pick(rows, prefix="wb18", treatment="base", quantity="recall",
                 year="2019s", ref=R21)["value"] == "0.9400", "the recall row stays"


def test_h2_k1_two_reference_clause_is_applied_not_left_to_the_reader(tmp_path):
    """An interaction that fires against C-CAP 2021 and vanishes against C-CAP 2016 is
    reference-epoch confounding (design 1.7) — UNDETERMINED, never a pass. The design
    pre-registers that sentence; if the instrument does not apply it, someone must, by
    hand, after the numbers exist."""
    hs = _load("harm_spread")

    def k1_rows(r16_2016_in16):
        return [("wb18_2006s_in05", "2006s", R21, 0.60), ("wb18_2006s_in16", "2006s", R21, 0.65),
                ("wb18_2016_in05", "2016", R21, 0.75), ("wb18_2016_in16", "2016", R21, 0.75),
                ("wb18_2006s_in05", "2006s", R16, 0.70), ("wb18_2006s_in16", "2006s", R16, 0.75),
                ("wb18_2016_in05", "2016", R16, 0.75), ("wb18_2016_in16", "2016", R16, r16_2016_in16)]

    both = _rows(hs.render(_metrics(tmp_path, k1_rows(0.75)), LABELS))
    v = _pick(both, prefix="wb18", quantity="k1_ref_verdict")
    assert v["flag"] == "H2-K1 LEAK (BOTH REFS)" and v["value"] == "0.0500", v
    # ...and the same 2021-side leak with the 2016-side interaction gone
    one = _rows(hs.render(_metrics(tmp_path, k1_rows(0.80), "one.csv"), LABELS))
    assert _pick(one, prefix="wb18", quantity="k1_interaction",
                 ref=R21)["flag"] == "H2-K1 LEAK"
    v = _pick(one, prefix="wb18", quantity="k1_ref_verdict")
    assert v["flag"] == "H2-K1 UNDETERMINED - FIRES ON ONE REFERENCE ONLY", v


# ------------------------------------------------- harm_change_laundering (H2-K2)

def _grid_tifs(tmp_path, in16_paints):
    """A 20x20 2 m synthetic lake: chm2005/chm2 with a known GAIN block, a certified-flat
    strip, one sample-test block covering everything, and a base/in16 prob pair.

    `in16_paints` is "gain" (canopy only on gain cells -> laundering) or "all" (canopy
    everywhere -> an honest uniform rise). base calls nothing in both cases.
    """
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    img = tmp_path / "img"
    img.mkdir()
    lake = tmp_path / "lake"
    (lake / "phase4" / "masks").mkdir(parents=True)
    n = 20
    tr = from_origin(500000.0, 5300000.0, 2.0, 2.0)
    prof = dict(driver="GTiff", height=n, width=n, count=1, dtype="uint8",
                crs="EPSG:26910", transform=tr)

    def write(path, arr):
        with rasterio.open(path, "w", **prof) as d:
            d.write(arr.astype("uint8"), 1)

    # h = (DN - 1) * 0.2 m.  DN 5 -> 0.8 m (< 2);  DN 30 -> 5.8 m (>= 5)
    gain = np.zeros((n, n), bool)
    gain[2:6, 2:6] = True                       # 16 of 400 cells
    write(img / "lidar_chm2005_2m.tif", np.full((n, n), 5))
    write(img / "lidar_chm2_2016_50cm.tif", np.where(gain, 30, 5))
    flat = np.zeros((n, n), np.uint8)
    flat[10:14, :] = 1                          # certified-flat strip, disjoint from gain
    write(img / "verified_background_lidar_2005_2016.tif", flat)

    write(lake / "phase4" / "masks" / "edmonds_canopy_prob_2006s_wb18_2006s_base.tif",
          np.zeros((n, n)))
    painted = gain if in16_paints == "gain" else np.ones((n, n), bool)
    write(lake / "phase4" / "masks" / "edmonds_canopy_prob_2006s_wb18_2006s_in16.tif",
          np.where(painted, 200, 0))

    man = tmp_path / "science_sample_manifest.csv"
    man.write_text(
        "block_id,role,stratum,minx,miny,maxx,maxy,area_ha,epsg\n"
        "TE00,test,,500000,5299960,500040,5300000,0.16,26910\n"
        "TR00,train,,400000,5299960,400040,5300000,0.16,26910\n", encoding="utf-8")
    return img, lake, man


def _k2(tmp_path, in16_paints):
    hcl = _load("harm_change_laundering")
    img, lake, man = _grid_tifs(tmp_path, in16_paints)
    rows = hcl.build(lake, [("2006s", "wb18_2006s_base", "wb18_2006s_in16")],
                     img=img, manifest=man, thresh=0.5)
    return hcl, {r["population"]: r for r in rows}


def test_k2_fires_when_in16_paints_only_the_certified_gain_cells(tmp_path):
    """KNOWN-BAD INPUT: the treatment adds canopy exactly where the 2016 lidar grew
    trees. That is the failure the criterion exists to catch, and it must fire."""
    _hcl, by = _k2(tmp_path, "gain")
    assert by["gain"]["n_cells"] == "16" and by["gain"]["rise"] == "1.00000"
    assert by["all"]["n_cells"] == "400" and by["all"]["rise"] == "0.04000"
    assert by["flat"]["rise"] == "0.00000", "no canopy was painted on the flat strip"
    assert by["gain_minus_all"]["rise"] == "0.96000"
    assert by["gain_minus_all"]["flag"] == "H2-K2 CHANGE LAUNDERING"


def test_k2_passes_on_an_honest_uniform_rise(tmp_path):
    """THE MATCHED CONTROL: the same treatment size, spread evenly. A criterion that
    fired here would kill every arm that simply detects more canopy."""
    _hcl, by = _k2(tmp_path, "all")
    assert by["gain"]["rise"] == "1.00000" and by["all"]["rise"] == "1.00000"
    assert by["gain_minus_all"]["rise"] == "0.00000"
    assert by["gain_minus_all"]["flag"] == "K2 PASSES"


def test_k2_scores_only_inside_the_sample_test_blocks(tmp_path):
    """Inference is AOI-limited to the science blocks; a rate computed outside them would
    divide by nodata. The train block in the manifest must be excluded."""
    hcl = _load("harm_change_laundering")
    img, lake, man = _grid_tifs(tmp_path, "gain")
    grid = hcl.grid_of(img / "lidar_chm2005_2m.tif")
    assert int(hcl.aoi_mask(man, grid, ("test",)).sum()) == 400
    assert int(hcl.aoi_mask(man, grid, ("train",)).sum()) == 0, (
        "the train block is far away — it must not land on this grid")


def test_k2_refuses_to_invent_a_threshold(tmp_path):
    """An arm with no scored curve has no deployed cut. Guessing one would score two arms
    at different, unrecorded operating points."""
    hcl = _load("harm_change_laundering")
    img, lake, man = _grid_tifs(tmp_path, "gain")
    empty = tmp_path / "empty_metrics.csv"
    empty.write_text(HEADER, encoding="utf-8")
    with pytest.raises(SystemExit, match="no matched_p75 cut"):
        hcl.build(lake, [("2006s", "wb18_2006s_base", "wb18_2006s_in16")],
                  img=img, manifest=man, arm_metrics=empty)


def test_k2_dry_run_lists_inputs_and_writes_nothing(tmp_path, capsys):
    hcl = _load("harm_change_laundering")
    img, lake, man = _grid_tifs(tmp_path, "gain")
    out = tmp_path / "harm_change_laundering.csv"
    assert hcl.main(["--base", str(lake), "--img", str(img), "--manifest", str(man),
                     "--out", str(out), "--dry-run"]) == 0
    cap = capsys.readouterr().out
    assert "DRY RUN" in cap and "UNVALIDATED" in cap
    assert "lidar_chm2005_2m.tif" in cap and "edmonds_canopy_prob_2006s_wb18_2006s_in16" in cap
    assert not out.exists(), "--dry-run must never write"
