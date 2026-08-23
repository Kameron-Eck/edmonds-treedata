r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — CATALOG CHECK: every catalog entry resolves, opens, and is
  the file it claims to be.
  Edmonds Temporal Active Learning Pipeline

  WHY THIS EXISTS  (IMAGERY_PLAN.md A1 / A3 / A5, 2026-08-19)
  ------------------------------------------------------------------
    A1  Two files both claimed to be "the" imagery catalog and they
        disagreed. pipeline_config.py's docstring said "single source of
        truth" while omitting every pre-2013 year, so raw_path(2000)
        raised KeyError. phase4seg/config.py:YEAR_CATALOG is what the
        engine actually reads, so THAT is authoritative and this script
        is the test that keeps it honest.
    A3  1936 and 1998 are SINGLE-BAND despite _rgb filenames. A filename
        is a claim; band count is a measurement. Any tool that infers 3
        bands from the name silently misreads them. Both were renamed to
        1936_king_pan.tif / 1998_king_pan.tif on 2026-08-19 — scripts in
        litwatch_scratch/ still reference the OLD names and will raise
        FileNotFoundError until updated.
    A5  The imagery lives in more than one root and lookups silently fell
        through between them. This script reports WHICH root each year
        resolved to, so a cross-root surprise is visible instead of
        invisible.

  WHAT IT CHECKS, per YEAR_CATALOG entry
    resolves   the native_file is found in one of config.imagery_roots()
    opens      rasterio can open it and read its header
    bands      on-disk band count == the catalog's "bands" field
    payload    the file is not a uniform constant fill (an empty shell)
    crs        on-disk EPSG == the catalog's "crs_epsg" field

  It also lists ORPHANS — rasters sitting in an imagery root that no
  catalog entry claims — because that is how 1936/1998/2012/2017_king
  went unnoticed.

  USAGE
    py -3.12 phase4_catalog_check.py            # header checks only, seconds
    py -3.12 phase4_catalog_check.py --fill     # + constant-fill probe (reads
                                                #   one decimated overview each)
  EXIT CODE
    0 = every entry passed. 1 = at least one FAIL. Orphans never fail.
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))  # phase4seg lives in pipeline/

import numpy as np
import rasterio
from rasterio.windows import Window

from phase4seg import config as C

FILL_PROBE_PX = 512          # decimated read edge when overviews exist
FILL_PROBE_GRID = 5          # NxN scattered windows when they do not
FILL_PROBE_WIN = 512         # edge of each scattered window, px


def _epsg(ds):
    try:
        return ds.crs.to_epsg()
    except Exception:
        return None


def _constant_fill(ds):
    """Is band 1 a single constant value (an empty shell)?

    Returns (is_flat, value, how). Cost matters: a decimated full-extent read of
    a raster WITHOUT overviews touches every byte on disk — 48 GB for one CoE
    year — so that path is only taken when overviews exist (see IMAGERY_PLAN.md
    B2). Otherwise we probe a grid of scattered windows, which is a SAMPLE: it
    can prove "varies", and it can only ever say "flat in every window probed".
    """
    if ds.overviews(1):
        h = max(1, min(FILL_PROBE_PX, ds.height))
        w = max(1, min(FILL_PROBE_PX, ds.width))
        a = ds.read(1, out_shape=(h, w))
        return bool(a.min() == a.max()), int(a.min()), "overview"

    lo = hi = None
    n = FILL_PROBE_GRID
    win = FILL_PROBE_WIN
    for iy in range(n):
        for ix in range(n):
            row = int((ds.height - win) * (iy + 0.5) / n)
            col = int((ds.width - win) * (ix + 0.5) / n)
            a = ds.read(1, window=Window(max(0, col), max(0, row),
                                         min(win, ds.width), min(win, ds.height)))
            lo = a.min() if lo is None else min(lo, a.min())
            hi = a.max() if hi is None else max(hi, a.max())
            if lo != hi:
                return False, int(lo), f"{n}x{n} windows"
    return True, int(lo), f"{n}x{n} windows (SAMPLE)"


def check_entry(entry, roots, probe_fill):
    """Return (status, dict) for one catalog entry. status in PASS/FAIL."""
    name = entry["native_file"]
    row = dict(label=entry["label"], source=entry["source"], file=name,
               root="", bands_cat=entry.get("bands"), bands_disk="",
               crs_cat=entry.get("crs_epsg"), crs_disk="", size_gb="",
               fill="", problems="")
    hits = [d for d in roots if (d / name).exists()]
    if not hits:
        row["problems"] = f"NOT FOUND in any of {len(roots)} imagery root(s)"
        return "FAIL", row
    p = hits[0] / name
    row["root"] = str(hits[0])
    if len(hits) > 1:
        # Not a failure, but the reader must know a second copy exists: the two
        # can drift, and which one you get depends on the machine.
        row["problems"] = f"also present in {len(hits) - 1} other root(s); "
    problems = []
    try:
        with rasterio.open(p) as ds:
            row["bands_disk"] = ds.count
            row["crs_disk"] = _epsg(ds)
            row["size_gb"] = round(p.stat().st_size / 1e9, 2)
            if entry.get("bands") is not None and ds.count != entry["bands"]:
                problems.append(f"BAND COUNT {ds.count} != catalog {entry['bands']}")
            if entry.get("crs_epsg") is not None and _epsg(ds) != entry["crs_epsg"]:
                problems.append(f"CRS {_epsg(ds)} != catalog {entry['crs_epsg']}")
            if probe_fill:
                flat, val, how = _constant_fill(ds)
                row["fill"] = (f"constant={val}" if flat else "varies") + f" [{how}]"
                if flat:
                    problems.append(f"CONSTANT FILL (every probed pixel = {val})")
    except Exception as ex:
        problems.append(f"OPEN FAILED: {ex}")
    row["problems"] += "; ".join(problems)
    return ("FAIL" if problems else "PASS"), row


# Rasters that live in an imagery root but are NOT per-year orthos: they have
# their own homes in config.py (HS_PATHS, the C-CAP eval refs, derived masks).
# Listing them as "orphans" every run would bury the ones that matter.
NON_ORTHO_PREFIXES = ("ccap_", "lidar_", "edmonds_canopy_mask_", "2016 land cover")
# Rasters a campaign acquisition has REPLACED in YEAR_CATALOG. Kept on disk for provenance (never deleted,
# never overwritten); listed under their own heading, never as orphans. One line per replacement, with date.
# Campaign rasters held DELIBERATELY without a YEAR_CATALOG key: not per-year citywide acquisitions, so
# the per-year machinery must never tile them — but they are catalogued in qc/imagery_pixelsize_and_date.csv
# and are not "orphans" in the adopt-or-quarantine sense. Own heading below.
ADOPTED_NON_YEAR = {
    "2018_coe_marsh2cm_rgb.tif": "2026-08-23 M18: Edmonds Marsh drone survey 2018-08-01, ~1 km^2 footprint (1% of city) - "
                                 "site-scale reference, not a year; see IMAGERY_FACTS 10.6",
    "1990_snoh_10ft_pan.tif": "2026-08-23 S90: county 10-ft b/w - historical context outside the project span; 1-band, never tiled",
    "1998_snoh_3ft_pan.tif": "2026-08-23 S98: DNR 3-ft b/w scan via county service - pairs with 1998_king_pan; 1-band, never tiled",
    "2001_snoh_1ft_pan.tif": "2026-08-23 S01: county 1-ft b/w (eff 105 cm, scanned film) - 1-band, never tiled",
    "1996_snoh_1m_rgb.tif": "2026-08-23 S96: earliest COLOR imagery of Edmonds held (1-m) - outside the 2000-2024 span; "
                            "extending the span is Kam's decision, not the catalog's",
    "1936_king_pan.tif": "pre-campaign holding (renamed from _rgb 2026-08-19) - historical 1-band scan, never tiled",
    "1998_king_pan.tif": "pre-campaign holding (renamed from _rgb 2026-08-19) - historical 1-band scan, never tiled",
}
SUPERSEDED_FILES = {
    "2016_snoh_rgbi.tif": "2026-08-23 -> 2016_snoh_1ft_rgbi.tif (acquire_imagery S16: full extent, native 1 ft)",
    "2002_king_rgb.tif": "2026-08-23 -> 2002_usgs_30cm_rgb.tif (acquire_imagery U02: original USGS HRO tiles, no JPEG cache)",
    "2021_snoh_rgbi.tif": "2026-08-23 -> 2021_snoh_6in_rgbi.tif (acquire_imagery S21: full extent, snapped grid + nearest, HF 1.43x)",
    "2023_naip_rgbi.tif": "2026-08-23 -> 2023_naip_60cm_rgbi.tif (acquire_imagery N23f: original DOQQs, coverage 100 vs 67%, HF 1.41x)",
    "2019_naip_rgbi.tif": "2026-08-23 -> 2019_naip_60cm_rgbi.tif (acquire_imagery N19f: original DOQQs, coverage 100 vs 67%; reg-loss waived as blur artifact)",
}


def orphans(roots, catalog_files):
    """Ortho-shaped rasters in an imagery root that no catalog entry claims.

    Returns [(name, [roots it is in], first_path)] — a file present in two roots
    is ONE orphan, not two, but the reader still needs to see both copies.
    """
    found = {}
    for d in roots:
        for p in sorted(d.glob("*.tif")):
            if p.name in catalog_files:
                continue
            if p.name.startswith(NON_ORTHO_PREFIXES) or p.name in SUPERSEDED_FILES or p.name in ADOPTED_NON_YEAR:
                continue
            found.setdefault(p.name, ([], p))[0].append(d.drive or str(d))
    return [(n, ds, p) for n, (ds, p) in sorted(found.items())]


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="Check every catalog entry resolves and opens.")
    ap.add_argument("--fill", action="store_true",
                    help="Also probe for constant-fill (empty shell) rasters.")
    args = ap.parse_args(argv)

    roots = C.imagery_roots()
    print("CATALOG CHECK — phase4seg/config.py:YEAR_CATALOG is authoritative")
    print(f"  entries        : {len(C.YEAR_CATALOG)}")
    print("  imagery roots  : (resolution order — first hit wins)")
    for i, d in enumerate(roots, 1):
        print(f"     {i}. {d}")
    if not roots:
        raise SystemExit("no imagery root exists on this machine — see config.imagery_roots()")
    print()

    hdr = f"  {'year':<6} {'src':<14} {'file':<24} {'bnd':>5} {'crs':>6} {'GB':>7}  root"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    fails, rows = [], []
    for e in C.YEAR_CATALOG:
        status, r = check_entry(e, roots, args.fill)
        rows.append(r)
        rootlbl = Path(r["root"]).drive or "?"
        print(f"  {r['label']:<6} {r['source'][:14]:<14} {r['file'][:24]:<24} "
              f"{str(r['bands_disk']):>5} {str(r['crs_disk']):>6} {str(r['size_gb']):>7}  {rootlbl}"
              + ("" if status == "PASS" else "   <-- FAIL"))
        if status == "FAIL":
            fails.append(r)

    if fails:
        print("\n  -- FAILURES " + "-" * 46)
        for r in fails:
            print(f"     {r['label']:<6} {r['file']:<26} {r['problems']}")

    orph = orphans(roots, {e["native_file"] for e in C.YEAR_CATALOG})
    if orph:
        print("\n  -- ORPHANS (present on disk, claimed by no catalog entry) " + "-" * 4)
        for name, drives, p in orph:
            try:
                with rasterio.open(p) as ds:
                    detail = f"{ds.count}b {ds.width}x{ds.height} {ds.dtypes[0]} EPSG:{_epsg(ds)}"
                    if args.fill:
                        flat, val, _how = _constant_fill(ds)
                        detail += "  CONSTANT FILL" if flat else ""
            except Exception as ex:
                detail = f"unreadable: {ex}"
            print(f"     {name:<26} {'/'.join(drives):<6} "
                  f"{round(p.stat().st_size/1e9, 2):>7} GB  {detail}")
        print("     -> adopt into YEAR_CATALOG or quarantine; see IMAGERY_PLAN.md A2.")

    ado = [(n, why, [d for d in roots if (d / n).exists()]) for n, why in ADOPTED_NON_YEAR.items()]
    if ado:
        print("\n  -- HELD WITHOUT A YEAR KEY (deliberate; catalogued in the pixel-size table) " + "-" * 2)
        for n, why, where in ado:
            print(f"     {n:<26} {'/'.join(d.drive or str(d) for d in where) or 'absent':<6} {why}")

    sup = [(n, why, [d for d in roots if (d / n).exists()]) for n, why in SUPERSEDED_FILES.items()]
    if sup:
        print("\n  -- SUPERSEDED (kept on disk, replaced in YEAR_CATALOG) " + "-" * 8)
        for n, why, where in sup:
            print(f"     {n:<26} {'/'.join(d.drive or str(d) for d in where) or 'absent':<6} {why}")

    print(f"\n  {len(C.YEAR_CATALOG) - len(fails)}/{len(C.YEAR_CATALOG)} catalog entries OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
