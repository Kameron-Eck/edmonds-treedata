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
