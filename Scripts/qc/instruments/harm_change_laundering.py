r"""harm_change_laundering.py — EXP-H2's K2, the DIRECT (non-circular) laundering test.

THE QUESTION. `--hs-source chm2` hands every year the SAME 2016 lidar canopy-height model
as a fourth input band. If that band compresses the cross-survey recall spread by supplying
generic structure, it is a harmonization surrogate. If it compresses the spread by PAINTING
2016 TREES ONTO 2006 IMAGERY, it manufactures false temporal stability — the precise
failure this project exists to avoid — and the spread number is worthless whatever (P) says.

WHY A NEW INSTRUMENT WAS NEEDED. The design (Reports/HARMONIZATION_DESIGN_2026-09-10.md,
K2) names the population: cells that GAINED canopy between the 2005 and 2016 lidar epochs.
That population is defined inside `qc/instruments/certified_flat_scoring.py` and the file
it writes, `phase4/qc/certified_change_cells.csv`, is a four-column COUNT table
(quantity,cells,km2,definition) — a total, not a per-cell raster, so it cannot be
intersected with a prediction. This instrument REBUILDS the mask from the same rule and the
same warp convention:

    both = (chm2005_2m > 0) & (chm2_2016 max-warped to that grid > 0)
    h    = (DN - 1) * 0.2                       # metres, both products
    GAIN = both & (h05 < 2.0) & (h16 >= 5.0)    # certified_flat_scoring.py::main
    FLAT = verified_background_lidar_2005_2016 == 1   # < 2 m in BOTH clouds, eroded 6 m

GRID. Everything is computed on the chm2005 2 m grid, because that is the grid the GAIN
rule is defined on. Probability rasters and the certified-flat mask are warped ONTO it:
probs with `Resampling.max` — the file's stated convention, "asserts vegetation anywhere in
the cell" — and the flat mask with `Resampling.nearest`, because it is an already-eroded
binary and `max` would grow it back.

POPULATION LIMIT, AND IT IS NOT OPTIONAL. These arms infer only inside
`science_sample_blocks.gpkg`; outside it the prob raster is PROB_NODATA. There is no
citywide rate to compare against, so every rate here is computed inside the LOSO
sample-TEST blocks of `phase4/qc/science_sample_manifest.csv` and nowhere else.

THE READ. For each (base arm, in16 arm) pair, the canopy-call rate at each arm's own
deployed matched_p75 cut, over three populations:

    gain    certified GAIN cells inside the sample-test blocks
    flat    certified-FLAT cells inside them (a physically empty control — a rise here is
            absolute false positive, not laundering, and it separates "the channel adds
            canopy everywhere" from "the channel adds canopy where 2016 grew trees")
    all     every valid sample-test cell

    K2 = [rate_in16(gain) - rate_base(gain)] - [rate_in16(all) - rate_base(all)]

    K2 > FLOOR (0.0069)  ->  the channel is painting 2016 trees onto older imagery: KILL,
    whatever the spread does. The precedent is on the ADDER path, not the input band —
    "2016-epoch additions on 2006 imagery poison the labels" (add16 -0.503,
    experiments/tier1_science_sample.yaml verdict) — which is why the band must be checked
    and not assumed clean.

**UNVALIDATED ON REAL RASTERS.** As of 2026-09-09 no in16 arm exists on resnet18, so this
instrument has never run against a real pair. Its arithmetic, its grid handling and its
kill firing are gated on synthetic rasters in `qc/test_harmonization.py` — which tests the
CODE, not the CLAIM (CLAUDE.md 3.4c). Nothing it prints may be cited until the arms land
and it has run on them.

Run:
  PYTHONUTF8=1 py -3.12 qc/instruments/harm_change_laundering.py --dry-run
  PYTHONUTF8=1 py -3.12 qc/instruments/harm_change_laundering.py
"""
import argparse
import csv
import io
from pathlib import Path

HERE = Path(__file__).resolve().parent            # Scripts/qc/instruments
SCRIPTS = HERE.parents[1]                         # Scripts/
REPO = SCRIPTS.parent

IMG = Path(r"D:\edmonds-pipeline\Imagery")        # certified_flat_scoring.py::IMG
CHM05 = "lidar_chm2005_2m.tif"
CHM16 = "lidar_chm2_2016_50cm.tif"
VB = "verified_background_lidar_2005_2016.tif"
MANIFEST = REPO / "phase4" / "qc" / "science_sample_manifest.csv"
ARM_METRICS = REPO / "phase4" / "qc" / "arm_metrics.csv"
OUT_DEFAULT = REPO / "phase4" / "qc" / "harm_change_laundering.csv"

REF_DEFAULT = "ccap_2021_hires_lc.tif"
POLICY = "matched_p75"
EVAL_SCOPE = "sample-test"
CANOPY_DEF = "forest_wetland"
FLOOR = 0.0069                     # experiments/backbone_sweep.yaml verdict
PROB_NODATA = 255                  # phase4seg prob rasters
PROB_SCALE = 254.0                 # certified_flat_scoring.py: arr >= t * 254.0

# The in16-vs-base pairs EXP-H2 owns. 2006s is the one the design calls decisive; the
# others are reported because a rise that appears on every year is a CHM-quality effect,
# not a leak (experiments/old_chm_defect.yaml).
PAIRS = [
    ("2006s", "wb18_2006s_base", "wb18_2006s_in16"),
    ("2011s", "wb18_2011s_base", "wb18_2011s_in16"),
    ("2016", "wb18_2016_base", "wb18_2016_in16"),
    ("2019n", "wb18_2019n_base", "wb18_2019n_in16"),
    ("2019s", "wb18_2019s_base", "wb18_2019s_in16"),
    ("2020", "wb18_2020_base", "wb18_2020_in16"),
]
POPULATIONS = ("gain", "flat", "all")
FIELDS = ["year", "base_tag", "in16_tag", "ref", "population", "n_cells",
          "base_thresh", "in16_thresh", "base_call_rate", "in16_call_rate", "rise",
          "floor", "flag", "note"]


# ---------------------------------------------------------------- raster helpers

def _open(path):
    import rasterio
    return rasterio.open(path)


def grid_of(chm05_path):
    """The chm2005 2 m grid every population is computed on."""
    with _open(chm05_path) as src:
        return {"crs": src.crs, "transform": src.transform,
                "width": src.width, "height": src.height}


def warp_onto(path, grid, resampling, band=1):
    """Warp a raster onto `grid`. Convention per certified_flat_scoring.py::warp_max."""
    import rasterio
    from rasterio.vrt import WarpedVRT
    with rasterio.open(path) as src:
        with WarpedVRT(src, crs=grid["crs"], transform=grid["transform"],
                       width=grid["width"], height=grid["height"],
                       resampling=resampling) as v:
            return v.read(band)


def gain_and_flat(chm05_path, chm16_path, vb_path, grid):
    """(GAIN, FLAT) boolean masks on `grid` — certified_flat_scoring.py's own rule."""
    import numpy as np
    from rasterio.enums import Resampling
    with _open(chm05_path) as c05:
        a05 = c05.read(1)
    a16 = warp_onto(chm16_path, grid, Resampling.max)
    both = (a05 > 0) & (a16 > 0)
    h05 = (a05.astype(np.float32) - 1) * 0.2
    h16 = (a16.astype(np.float32) - 1) * 0.2
    gain = both & (h05 < 2.0) & (h16 >= 5.0)
    # nearest, NOT max: vb is a binary mask already eroded 6 m; max would regrow it.
    flat = warp_onto(vb_path, grid, Resampling.nearest) == 1
    return gain, flat


def aoi_mask(manifest, grid, roles=("test",)):
    """Boolean mask of the manifest's role blocks, rasterized onto `grid`."""
    import rasterio.warp
    from rasterio.features import geometry_mask
    from shapely.geometry import box as _box
    shapes = []
    with Path(manifest).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["role"] not in roles:
                continue
            poly = _box(float(r["minx"]), float(r["miny"]),
                        float(r["maxx"]), float(r["maxy"]))
            shapes.append(rasterio.warp.transform_geom(
                f"EPSG:{int(r['epsg'])}", grid["crs"], poly.__geo_interface__))
    if not shapes:
        raise SystemExit(f"{manifest}: no rows with role in {roles}")
    return geometry_mask(shapes, out_shape=(grid["height"], grid["width"]),
                         transform=grid["transform"], invert=True)


def call_and_valid(prob_path, grid, thresh):
    """(called canopy, valid) on `grid` for one prob raster at one cut."""
    from rasterio.enums import Resampling
    arr = warp_onto(prob_path, grid, Resampling.max)
    valid = arr != PROB_NODATA
    return valid & (arr >= thresh * PROB_SCALE), valid


def prob_path(base, year, tag):
    return Path(base) / "phase4" / "masks" / f"edmonds_canopy_prob_{year}_{tag}.tif"


# ---------------------------------------------------------------- thresholds

def deployed_thresholds(arm_metrics=ARM_METRICS, ref=REF_DEFAULT):
    """{run_tag: matched_p75 cut} on the pre-registered basis. Missing tags stay absent —
    an arm with no scored curve has no deployed cut and must not be given one."""
    out = {}
    p = Path(arm_metrics)
    if not p.exists():
        return out
    with p.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if (r["policy"] == POLICY and r["eval_scope"] == EVAL_SCOPE
                    and r["canopy_def"] == CANOPY_DEF and r["ref"] == ref
                    and r["thresh"]):
                out[r["run_tag"]] = float(r["thresh"])
    return out


# ---------------------------------------------------------------- the read

def _rate(called, population):
    n = int(population.sum())
    return (int((called & population).sum()) / n if n else None), n


def rows_for_pair(year, base_tag, in16_tag, masks, base_call, in16_call,
                  base_valid, in16_valid, thr_base, thr_in16, ref):
    """The three population rows plus the K2 row, for one pair. Pure arithmetic."""
    valid = base_valid & in16_valid          # score both arms on the same cells
    rises = {}
    rows = []
    for pop in POPULATIONS:
        m = masks[pop] & valid
        rb, n = _rate(base_call, m)
        ri, _ = _rate(in16_call, m)
        rise = None if (rb is None or ri is None) else ri - rb
        rises[pop] = rise
        rows.append({
            "year": year, "base_tag": base_tag, "in16_tag": in16_tag, "ref": ref,
            "population": pop, "n_cells": str(n),
            "base_thresh": f"{thr_base:.6f}", "in16_thresh": f"{thr_in16:.6f}",
            "base_call_rate": "" if rb is None else f"{rb:.5f}",
            "in16_call_rate": "" if ri is None else f"{ri:.5f}",
            "rise": "" if rise is None else f"{rise:.5f}",
            "floor": f"{FLOOR:.4f}", "flag": "" if n else "EMPTY POPULATION",
            "note": {"gain": "certified 2005->2016 canopy gain, sample-test only",
                     "flat": "certified flat (absolute FP control), sample-test only",
                     "all": "every valid sample-test cell"}[pop]})
    k2 = (None if rises["gain"] is None or rises["all"] is None
          else rises["gain"] - rises["all"])
    rows.append({
        "year": year, "base_tag": base_tag, "in16_tag": in16_tag, "ref": ref,
        "population": "gain_minus_all", "n_cells": "",
        "base_thresh": f"{thr_base:.6f}", "in16_thresh": f"{thr_in16:.6f}",
        "base_call_rate": "", "in16_call_rate": "",
        "rise": "" if k2 is None else f"{k2:.5f}",
        "floor": f"{FLOOR:.4f}",
        "flag": ("" if k2 is None else
                 ("H2-K2 CHANGE LAUNDERING" if k2 > FLOOR else "K2 PASSES")),
        "note": "K2 = gain-cell rise minus all-cell rise; kill above the floor"})
    return rows


def build(base, pairs=PAIRS, img=IMG, manifest=MANIFEST, ref=REF_DEFAULT,
          arm_metrics=ARM_METRICS, thresh=None, roles=("test",)):
    """Every row, for the pairs whose prob rasters exist."""
    img = Path(img)
    grid = grid_of(img / CHM05)
    gain, flat = gain_and_flat(img / CHM05, img / CHM16, img / VB, grid)
    aoi = aoi_mask(manifest, grid, roles)
    masks = {"gain": gain & aoi, "flat": flat & aoi, "all": aoi}
    thr = deployed_thresholds(arm_metrics, ref)
    rows = []
    for year, base_tag, in16_tag in pairs:
        pb, pi = prob_path(base, year, base_tag), prob_path(base, year, in16_tag)
        if not (pb.exists() and pi.exists()):
            continue
        tb = thresh if thresh is not None else thr.get(base_tag)
        ti = thresh if thresh is not None else thr.get(in16_tag)
        if tb is None or ti is None:
            raise SystemExit(
                f"{year}: no {POLICY} cut in {Path(arm_metrics).name} for "
                f"{base_tag if tb is None else in16_tag} — score the arm first, or pass "
                f"--thresh (which applies ONE cut to both arms and is for tests only)")
        cb, vb_ = call_and_valid(pb, grid, tb)
        ci, vi = call_and_valid(pi, grid, ti)
        rows += rows_for_pair(year, base_tag, in16_tag, masks, cb, ci, vb_, vi,
                              tb, ti, ref)
    return rows


def render(rows):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def inputs_for(base, pairs=PAIRS, img=IMG, manifest=MANIFEST):
    """Every path this instrument reads — what --dry-run lists."""
    img = Path(img)
    want = [img / CHM05, img / CHM16, img / VB, Path(manifest)]
    for year, base_tag, in16_tag in pairs:
        want += [prob_path(base, year, base_tag), prob_path(base, year, in16_tag)]
    return want


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None, help="Lake root (default lake.BASE)")
    ap.add_argument("--img", default=str(IMG), help="Local imagery mirror")
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--arm-metrics", default=str(ARM_METRICS))
    ap.add_argument("--ref", default=REF_DEFAULT,
                    help="Reference whose matched_p75 cut is the deployed cut")
    ap.add_argument("--thresh", type=float, default=None,
                    help="ONE cut for both arms — tests and diagnostics only; the real "
                         "read uses each arm's own deployed matched_p75 cut")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--dry-run", action="store_true",
                    help="List every input and whether it exists; write nothing")
    if argv is None:
        from phase4seg.names import clean_argv
        argv = clean_argv()
    a = ap.parse_args(argv)

    if a.base:
        base = Path(a.base)
    else:
        from lake import BASE
        base = Path(BASE)

    if a.dry_run:
        print("DRY RUN — inputs:")
        missing = 0
        for p in inputs_for(base, PAIRS, a.img, a.manifest):
            ok = p.exists()
            missing += 0 if ok else 1
            print(f"  [{'ok ' if ok else 'MISSING'}] {p}")
        print(f"{missing} missing. UNVALIDATED on real rasters until the in16 arms land.")
        return 0

    rows = build(base, PAIRS, a.img, a.manifest, a.ref, a.arm_metrics, a.thresh)
    text = render(rows)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    fired = [r for r in rows if r["flag"] == "H2-K2 CHANGE LAUNDERING"]
    print(f"wrote {out} ({len(rows)} rows)"
          + (f"; K2 FIRES on {[r['year'] for r in fired]}" if fired else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
