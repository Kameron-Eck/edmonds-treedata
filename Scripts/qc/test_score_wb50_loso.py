"""qc/instruments/score_wb50_loso.py — the phase-2 LOSO scoring driver, gated dry.

Two properties: on a complete synthetic lake layout the dry run prints exactly seven
qc_indep commands in the Tier-1 shape (--aoi ... --aoi-roles test, no --thresh) plus the
harvest; with one prob raster absent it refuses (exit 2) before printing any command.
Everything lives under tmp_path — the driver takes --base, so lake.BASE is never
resolved and nothing on G: is touched.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_score_wb50_loso.py -q
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "score_wb50_loso", SCRIPTS / "qc" / "instruments" / "score_wb50_loso.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _layout(tmp_path, drop=None, prefix="wb50"):
    m = _mod()
    base = tmp_path / "lake"
    (base / "phase4" / "masks").mkdir(parents=True)
    for year, tag in m.arms_for(prefix):
        if tag != drop:
            m.prob_path(base, year, tag).write_bytes(b"x")
    ref = base / "Full_Image" / "Pipeline Imagery" / m.REF_NAME
    ref.parent.mkdir(parents=True)
    ref.write_bytes(b"x")
    aoi = tmp_path / "science_sample_manifest.csv"
    aoi.write_text("block_id,role,stratum,minx,miny,maxx,maxy,area_ha,epsg\n",
                   encoding="utf-8")
    return m, base, aoi


def test_dry_run_prints_seven_tier1_shaped_commands(tmp_path, capsys):
    m, base, aoi = _layout(tmp_path)
    rc = m.main(["--base", str(base), "--aoi", str(aoi), "--python", "PY", "--dry-run"])
    assert rc == 0
    lines = [ln.strip() for ln in capsys.readouterr().out.splitlines()
             if "phase4_qc_indep.py" in ln]
    assert len(lines) == 7
    for (year, tag), ln in zip(m.ARMS, lines):
        assert ln.startswith("PY ")
        assert f"--year {year} " in ln
        # list2cmdline quotes the space in "Pipeline Imagery" — match by name
        assert "--ref " in ln and m.REF_NAME in ln
        assert f"edmonds_canopy_prob_{year}_{tag}.tif" in ln
        assert "--aoi " in ln and aoi.name in ln and ln.endswith("--aoi-roles test")
        assert "--thresh" not in ln
    assert [t for _, t in m.ARMS][-1] == "wb50_2020_base", "2020 (the slow arm) runs last"


def test_dry_run_lists_the_harvest_after_the_seven(tmp_path, capsys):
    m, base, aoi = _layout(tmp_path)
    m.main(["--base", str(base), "--aoi", str(aoi), "--python", "PY", "--dry-run"])
    out = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("  PY ")]
    assert len(out) == 8 and out[-1].endswith("harvest_arm_metrics.py")


def test_refuses_on_a_missing_prob_raster(tmp_path, capsys):
    m, base, aoi = _layout(tmp_path, drop="wb50_2016_in05")
    with pytest.raises(SystemExit) as e:
        m.main(["--base", str(base), "--aoi", str(aoi), "--dry-run"])
    assert e.value.code == 2
    cap = capsys.readouterr()
    assert "REFUSING" in cap.err and "edmonds_canopy_prob_2016_wb50_2016_in05.tif" in cap.err
    assert "phase4_qc_indep.py" not in cap.out, "no command may print before the refusal"


def test_refuses_on_a_missing_reference(tmp_path):
    m, base, aoi = _layout(tmp_path)
    (base / "Full_Image" / "Pipeline Imagery" / m.REF_NAME).unlink()
    with pytest.raises(SystemExit) as e:
        m.main(["--base", str(base), "--aoi", str(aoi), "--dry-run"])
    assert e.value.code == 2


def test_prefix_wb18_scores_the_resnet18_arms(tmp_path, capsys):
    """--prefix wb18 (phase 3) is the same conveyor over the wb18_ tags: seven
    commands, identical shape, 2020 last. tmp_path only — lake.BASE is never resolved."""
    m, base, aoi = _layout(tmp_path, prefix="wb18")
    rc = m.main(["--base", str(base), "--aoi", str(aoi), "--python", "PY",
                 "--prefix", "wb18", "--dry-run"])
    assert rc == 0
    lines = [ln.strip() for ln in capsys.readouterr().out.splitlines()
             if "phase4_qc_indep.py" in ln]
    assert len(lines) == 7
    for (year, tag), ln in zip(m.arms_for("wb18"), lines):
        assert tag.startswith("wb18_")
        assert f"--year {year} " in ln
        assert f"edmonds_canopy_prob_{year}_{tag}.tif" in ln
        assert ln.endswith("--aoi-roles test") and "--thresh" not in ln
    assert m.arms_for("wb18")[-1][1] == "wb18_2020_base", "2020 (the slow arm) runs last"
    # the wb50 rasters are absent from this layout, so the default prefix must refuse
    with pytest.raises(SystemExit) as e:
        m.main(["--base", str(base), "--aoi", str(aoi), "--dry-run"])
    assert e.value.code == 2


# ---- --arms / --refs (2026-09-10, the harmonization design) -------------------
# EXP-H1's secondary read needs the SAME arm scored against BOTH references, because one
# frozen 2006s mask swings 0.097 in recall on the reference year alone
# (Reports/HARMONIZATION_DESIGN_2026-09-10.md section 1.7). These gate the two flags that
# made that possible; the five tests above are unchanged and pin the old behaviour.

def _harm_layout(tmp_path, tags, refs):
    m = _mod()
    base = tmp_path / "lake"
    (base / "phase4" / "masks").mkdir(parents=True)
    for year, tag in m.arms_from_tags(tags):
        m.prob_path(base, year, tag).write_bytes(b"x")
    d = base / "Full_Image" / "Pipeline Imagery"
    d.mkdir(parents=True)
    for r in refs:
        (d / r).write_bytes(b"x")
    aoi = tmp_path / "science_sample_manifest.csv"
    aoi.write_text("block_id,role,stratum,minx,miny,maxx,maxy,area_ha,epsg\n",
                   encoding="utf-8")
    return m, base, aoi


def test_year_of_reads_the_catalog_label_out_of_a_tag():
    m = _mod()
    assert m.year_of("wb18_2006s_in16") == "2006s"
    assert m.year_of("wb18_2019s_base") == "2019s"
    assert m.year_of("wb18_2011s_base_s2") == "2011s"


def test_year_of_refuses_a_tag_with_no_catalog_label():
    """A guessed year would score the arm against another acquisition's AOI and cut."""
    m = _mod()
    with pytest.raises(SystemExit, match="YEAR_CATALOG"):
        m.year_of("wb18_1999_base")


def test_arms_and_refs_cross_every_arm_with_every_reference(tmp_path, capsys):
    m, base, aoi = _harm_layout(
        tmp_path, ["wb18_2006s_base", "wb18_2006s_in16"],
        ["ccap_2021_hires_lc.tif", "ccap_2016_hires_lc.tif"])
    rc = m.main(["--base", str(base), "--aoi", str(aoi), "--python", "PY", "--dry-run",
                 "--arms", "wb18_2006s_base", "wb18_2006s_in16",
                 "--refs", "ccap_2021_hires_lc.tif", "ccap_2016_hires_lc.tif"])
    assert rc == 0
    lines = [ln.strip() for ln in capsys.readouterr().out.splitlines()
             if "phase4_qc_indep.py" in ln]
    assert len(lines) == 4, lines            # arms OUTER, refs INNER
    for ln in lines:
        assert "--year 2006s " in ln and ln.endswith("--aoi-roles test")
    assert m.REF_NAME in lines[0] and m.REF_2016 in lines[1]
    assert "wb18_2006s_base" in lines[0] and "wb18_2006s_in16" in lines[2]


def test_a_missing_second_reference_refuses_before_any_command(tmp_path, capsys):
    m, base, aoi = _harm_layout(tmp_path, ["wb18_2006s_base"],
                                ["ccap_2021_hires_lc.tif"])
    with pytest.raises(SystemExit) as e:
        m.main(["--base", str(base), "--aoi", str(aoi), "--dry-run",
                "--arms", "wb18_2006s_base",
                "--refs", "ccap_2021_hires_lc.tif", "ccap_2016_hires_lc.tif"])
    assert e.value.code == 2
    cap = capsys.readouterr()
    assert m.REF_2016 in cap.err and "phase4_qc_indep.py" not in cap.out


def test_the_default_shape_is_byte_identical_after_the_new_flags(tmp_path, capsys):
    """The Tier-1 invocation must not have moved: one ref, seven arms, same order."""
    m, base, aoi = _layout(tmp_path)
    m.main(["--base", str(base), "--aoi", str(aoi), "--python", "PY", "--dry-run"])
    lines = [ln.strip() for ln in capsys.readouterr().out.splitlines()
             if "phase4_qc_indep.py" in ln]
    assert len(lines) == 7
    assert all(m.REF_NAME in ln and "--aoi-roles test" in ln for ln in lines)
