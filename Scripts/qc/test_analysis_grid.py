"""The declared analysis grid (config.ANALYSIS_GRID_EPSG) and its consistency.

Repo-only. The grid names where cross-year statistics live; these tests pin that
the declaration exists, that its CRS really is ground-metres over the AOI, and that
the instruments already gridding on it agree with the declaration instead of
carrying their own diverging literals.
"""
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def test_grid_is_declared_and_is_true_metres():
    from phase4seg import config
    from phase4seg.common import _crs_unit_m
    assert config.ANALYSIS_GRID_EPSG == 26910
    import rasterio.crs
    crs = rasterio.crs.CRS.from_epsg(config.ANALYSIS_GRID_EPSG)
    assert _crs_unit_m(crs) == 1.0, "the analysis grid must be a metre CRS"
    assert not crs.is_geographic


def test_rescore_grid_matches_the_declaration():
    """support_matched_rescore predates the declaration and carries a literal; it
    must equal the declared grid or one of them is lying about where comparisons
    happen."""
    from phase4seg import config
    src = (SCRIPTS / "qc" / "instruments" / "support_matched_rescore.py").read_text(
        encoding="utf-8")
    assert f'GRID_CRS = "EPSG:{config.ANALYSIS_GRID_EPSG}"' in src


def test_geometry_table_exists_with_the_contract_columns():
    """The measured per-acquisition geometry table (docs/SCHEMAS.md). Regenerate:
    qc/instruments/imagery_geometry.py. 36 rows, one per catalog acquisition."""
    import csv
    p = SCRIPTS.parent / "phase4" / "qc" / "imagery_geometry.csv"
    assert p.exists(), "run qc/instruments/imagery_geometry.py"
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    from phase4seg.config import YEAR_CATALOG
    assert len(rows) == len(YEAR_CATALOG), (
        f"{len(rows)} rows vs {len(YEAR_CATALOG)} catalog acquisitions — regenerate")
    need = {"label", "crs_auth", "unit_name", "px_ground_x_m", "px_x_m_naive",
            "crs_metric_inflation_pct", "epsg_match", "gsd_vs_catalog_pct"}
    assert need <= set(rows[0]), f"missing columns: {need - set(rows[0])}"
    bad = [r["label"] for r in rows if r["epsg_match"] not in ("", "1")]
    assert not bad, f"measured CRS disagrees with the catalog for: {bad}"


def test_mmu_column_matches_the_live_sieve_arithmetic():
    """Integration gate (Kam's 'how do I know it was integrated' question,
    2026-09-01): the geometry table's mmu_effective_m2 must equal what
    postproc.sieve_min_px produces from the same measured pixel sizes. If the
    re-baseline changes the sieve and the table is not regenerated, THIS fails —
    the table can never silently describe a sieve that no longer exists."""
    import csv
    import math
    from phase4seg.postproc import sieve_min_px
    p = SCRIPTS.parent / "phase4" / "qc" / "imagery_geometry.csv"
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    for r in rows:
        if not r.get("mmu_effective_m2"):
            continue
        ground = float(r["px_ground_x_m"]) * float(r["px_ground_y_m"])
        want = sieve_min_px(ground) * ground
        # stored column is rounded to 3 decimals — compare at that precision
        assert math.isclose(float(r["mmu_effective_m2"]), round(want, 3),
                            abs_tol=5e-4), (
            f"{r['label']}: table says {r['mmu_effective_m2']}, live sieve says "
            f"{want:.3f} — regenerate qc/instruments/imagery_geometry.py")


def test_passport_is_fresh():
    """The joined view must agree with its sources — a passport that contradicts a
    home is worse than bouncing between dataframes (Kam's centralization ask,
    2026-09-01, done the one-home-safe way: view generated, sources authoritative)."""
    import csv
    from phase4seg.config import YEAR_CATALOG
    from champion import load_champions
    p = SCRIPTS.parent / "phase4" / "qc" / "acquisition_passport.csv"
    assert p.exists(), "run qc/instruments/acquisition_passport.py"
    rows = {r["label"]: r for r in csv.DictReader(p.open(encoding="utf-8"))}
    assert set(rows) == {str(e["label"]) for e in YEAR_CATALOG}, (
        "passport labels drifted from the catalog — regenerate")
    champ = load_champions()
    for y, tag in champ.items():
        assert rows[y]["champion_tag"] == tag, (
            f"{y}: passport says champion {rows[y]['champion_tag']!r}, "
            f"champion_arms.csv says {tag!r} — regenerate the passport")
    geo = {r["label"]: r for r in csv.DictReader(
        (SCRIPTS.parent / "phase4" / "qc" / "imagery_geometry.csv").open(encoding="utf-8"))}
    for lab, r in rows.items():
        assert r["mmu_effective_m2"] == geo[lab]["mmu_effective_m2"], (
            f"{lab}: passport mmu disagrees with the geometry home — regenerate")


def test_step_postproc_loop_survives_the_extraction():
    """The 2026-09-01 lesson: threshold_and_clean's extraction left step_postproc
    counting valid_px from a name that moved inside the function — a NameError only
    a REAL postproc run could see, and the EPOCH 3 batch saw it on pair 1. Static
    pin: every bare name step_postproc reads must be defined in its own scope."""
    import ast
    import builtins
    src = (SCRIPTS / "pipeline" / "phase4seg" / "postproc.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "step_postproc")
    assigned = {a.arg for a in fn.args.args}
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            assigned.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            assigned |= {(a.asname or a.name.split(".")[0]) for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.comprehension)):
            pass
    module_names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Assign):
            module_names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module_names |= {(a.asname or a.name.split(".")[0]) for a in node.names}
    # names read inside comprehensions bind locally; collect their targets too
    for node in ast.walk(fn):
        if isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
            assigned.add(node.target.id)
    known = assigned | module_names | set(dir(builtins))
    # the star-import surface (config constants) — resolve via the config module
    from phase4seg import config as _cfg
    known |= set(vars(_cfg))
    unknown = sorted({node.id for node in ast.walk(fn)
                      if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                      and node.id not in known})
    assert not unknown, f"step_postproc reads undefined name(s): {unknown}"


def test_coregistration_table_contract():
    """STATS_CHECKLIST item 4's table: one row per non-anchor acquisition, and the
    BRIDGE (2020 vs the 2020s anchor) must stay near-zero — if the label source and
    the anchor ever disagree by more than 5 cm, every leg's interpretation changes
    and this fails loudly. Median = registration proper; p95 = conservative upper
    bound including parallax/lean/change content (its uniform 5-9 m band across
    even same-vendor pairs is the tell)."""
    import csv
    from phase4seg.config import YEAR_CATALOG
    p = SCRIPTS.parent / "phase4" / "qc" / "coregistration.csv"
    assert p.exists(), "run qc/instruments/coregistration.py"
    rows = {r["label"]: r for r in csv.DictReader(p.open(encoding="utf-8"))}
    assert set(rows) == {str(e["label"]) for e in YEAR_CATALOG} - {"2020s"}
    bridge = rows["2020"]
    assert bridge["p95_mag_m"] and float(bridge["p95_mag_m"]) < 0.05, (
        f"label-source bridge degraded: p95 {bridge['p95_mag_m']} m")
    for lab, r in rows.items():
        assert r["n_tried"], f"{lab}: empty row"
        if not r["p95_mag_m"]:
            assert "UNDETERMINED" in r["note"] or "failed" in r["note"], (
                f"{lab}: no magnitude and no honest note")
