r"""
╔══════════════════════════════════════════════════════════════════╗
  CANOPY SEPARABILITY — how visible is canopy in each held acquisition?
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION THIS ANSWERS
  ------------------------------------------------------------------
  The 2026-08-23/24 campaign left the project with 36 catalogued rasters and,
  for twelve calendar years, MORE THAN ONE acquisition of the same year. Nothing
  in the catalog says which of them a canopy model can actually see trees in.
  Grid size does not answer it (a sharp leaf-off frame hides deciduous canopy
  that a blurry leaf-on frame shows); provenance does not answer it either.

  So measure it. For each raster, sample the same ground locations, put every
  acquisition on ONE common grid, compute a per-pixel greenness index, and score
  it against the 2020 citywide canopy mask with AUROC — the probability that a
  random canopy pixel scores higher than a random background pixel. One number
  per acquisition, directly comparable, 0.5 = blind, 1.0 = perfect.

  WHAT THE NUMBER IS AND IS NOT
    * The mask is a MODEL PREDICTION for 2020 (CLAUDE.md gotcha), not hand truth:
      it carries the model's own blind spots (deciduous marsh especially).
    * For a NON-2020 year the mask also carries real canopy change as error.
    Both caveats are CONSTANT across two acquisitions of the SAME year, so the
    honest reading is the WITHIN-YEAR CONTRAST: which acquisition of 2017 shows
    canopy better, not whether 0.83 is a good absolute score. Cross-year
    comparison is indicative only and is labelled as such in the output.

  WHY IT MATTERS TO THE UNDER-PREDICTION PROBLEM
    Every non-2020 year borrows the 2020 labels. If an acquisition's canopy is
    poorly separable (leaf-off deciduous, a flat served stretch, heavy JPEG
    quantisation), the borrowed label says "canopy" where the pixels carry no
    evidence — exactly the regime that teaches a model to under-predict. This
    ranks every acquisition by how much evidence it actually offers.

  USAGE
    py -3.12 qc/imagery_canopy_separability.py             # every catalog raster
    py -3.12 qc/imagery_canopy_separability.py --only 2017 # one year / substring
      --points N     sample locations (default 40, seeded — reproducible)
      --box-m M      ground box edge per location (default 60)
      --grid-cm G    common grid for ALL rasters (default 50 cm)
      --workers N    parallel rasters (default 3)
╚══════════════════════════════════════════════════════════════════╝
"""
import argparse
import csv
import datetime as dt
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform as warp_xy, transform_bounds
from rasterio.windows import from_bounds as win_from_bounds

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
sys.path.insert(0, str(SCRIPTS / "qc"))
from phase4seg import config as C          # noqa: E402
import imagery_measure as im               # noqa: E402
import imagery_qc_suite as QS              # noqa: E402
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

TODAY = dt.date.today().isoformat()
MASK_CANDIDATES = [Path(r"D:/edmonds-pipeline/Imagery/edmonds_canopy_mask_2020.tif"),
                   Path(r"G:/My Drive/treedata/phase3/edmonds_canopy_mask_2020.tif"),
                   Path("/content/drive/MyDrive/treedata/phase3/edmonds_canopy_mask_2020.tif")]
MASK = next((p for p in MASK_CANDIDATES if p.exists()), None)
MAX_NATIVE_EDGE = 2600      # cap the native read edge; finer rasters are decimated on read


def sample_points(n: int, seed: int = 42):
    """n locations inside the city polygon (seeded → the same ground for every raster)."""
    import geopandas as gpd
    from shapely.geometry import Point
    g = gpd.read_file(im.CITY_SHP).to_crs("EPSG:4326")
    poly = g.union_all() if hasattr(g, "union_all") else g.unary_union
    minx, miny, maxx, maxy = poly.bounds
    rng = np.random.default_rng(seed)
    pts = []
    while len(pts) < n:
        x = rng.uniform(minx, maxx); y = rng.uniform(miny, maxy)
        if poly.contains(Point(x, y)):
            pts.append((float(x), float(y)))
    return pts


def grab_common(path: Path, lon: float, lat: float, box_m: float, grid_m: float, bands=None):
    """Read a native window around (lon, lat) and reproject it onto the COMMON grid
    (EPSG:3857 at grid_m ground metres). Every raster therefore contributes pixels of
    the same ground size at the same place — the campaign's standing rule that metrics
    must be read on common footing (IMAGERY_FACTS 10.1)."""
    n = int(round(box_m / grid_m))
    with rasterio.open(path) as ds:
        # common grid centred on the point, in Web Mercator (scale-corrected so grid_m is GROUND metres)
        xs, ys = warp_xy("EPSG:4326", "EPSG:3857", [lon], [lat])
        px_wm = grid_m / np.cos(np.radians(lat))
        x0, y1 = xs[0] - n * px_wm / 2, ys[0] + n * px_wm / 2
        dst_tr = from_origin(x0, y1, px_wm, px_wm)
        # native window covering those bounds (+2 px margin)
        b = transform_bounds("EPSG:3857", ds.crs, x0, y1 - n * px_wm, x0 + n * px_wm, y1)
        win = win_from_bounds(*b, transform=ds.transform).round_offsets().round_lengths()
        if win.width < 2 or win.height < 2:
            return None, None
        win = win.crop(ds.height, ds.width) if hasattr(win, "crop") else win
        if win.col_off < 0 or win.row_off < 0 or win.width < 2 or win.height < 2:
            return None, None
        if (win.col_off + win.width > ds.width) or (win.row_off + win.height > ds.height):
            return None, None
        idx = bands or list(range(1, ds.count + 1))
        dec = max(1, int(max(win.width, win.height) / MAX_NATIVE_EDGE))
        oh, ow = max(1, int(win.height // dec)), max(1, int(win.width // dec))
        A = ds.read(idx, window=win, out_shape=(len(idx), oh, ow))
        src_tr = ds.window_transform(win) * rasterio.Affine.scale(win.width / ow, win.height / oh)
        out = np.zeros((len(idx), n, n), dtype=np.float32)
        reproject(A.astype(np.float32), out, src_transform=src_tr, src_crs=ds.crs,
                  dst_transform=dst_tr, dst_crs="EPSG:3857", resampling=Resampling.average)
        return out, (dst_tr, n)


def grab_mask(dst_tr, n):
    """The 2020 canopy mask on the same common grid (nearest — it is categorical)."""
    with rasterio.open(MASK) as ds:
        x0, y1 = dst_tr.c, dst_tr.f
        px = dst_tr.a
        b = (x0, y1 - n * px, x0 + n * px, y1)
        win = win_from_bounds(*b, transform=ds.transform).round_offsets().round_lengths()
        if (win.col_off < 0 or win.row_off < 0 or win.width < 2 or win.height < 2
                or win.col_off + win.width > ds.width or win.row_off + win.height > ds.height):
            return None
        dec = max(1, int(max(win.width, win.height) / MAX_NATIVE_EDGE))
        oh, ow = max(1, int(win.height // dec)), max(1, int(win.width // dec))
        A = ds.read(1, window=win, out_shape=(oh, ow))
        src_tr = ds.window_transform(win) * rasterio.Affine.scale(win.width / ow, win.height / oh)
        out = np.zeros((n, n), dtype=np.uint8)
        reproject(A, out, src_transform=src_tr, src_crs=ds.crs, dst_transform=dst_tr,
                  dst_crs="EPSG:3857", resampling=Resampling.nearest)
        return out


def canopy_index(A: np.ndarray, bands: int):
    """NDVI where a real NIR band exists, else Excess Green (2G-R-B) — the standard
    RGB vegetation proxy. Returns (index, name). Both are scaled to a comparable range
    but AUROC is rank-based, so only the ORDERING of pixels matters."""
    if bands >= 4:
        red, nir = A[0], A[3]
        return (nir - red) / np.maximum(nir + red, 1e-6), "NDVI"
    if bands >= 3:
        r, g, b = A[0], A[1], A[2]
        s = np.maximum(r + g + b, 1e-6)
        return (2 * g - r - b) / s, "ExG"
    return A[0] * -1.0, "PAN(inverted brightness)"      # 1-band: dark = canopy, weakly


def auroc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Mann-Whitney U / |pos||neg| — rank-based, ties handled, no sklearn dependency."""
    if pos.size < 50 or neg.size < 50:
        return float("nan")
    a = np.concatenate([pos, neg])
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(a.size, dtype=np.float64)
    ranks[order] = np.arange(1, a.size + 1)
    # average ranks over ties
    srt = a[order]
    i = 0
    while i < srt.size:
        j = i
        while j + 1 < srt.size and srt[j + 1] == srt[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    r_pos = ranks[:pos.size].sum()
    u = r_pos - pos.size * (pos.size + 1) / 2.0
    return float(u / (pos.size * neg.size))


def score_raster(rec, pts, args):
    path = rec["path"]
    if path is None:
        return None
    pos_all, neg_all, used, name = [], [], 0, None
    try:
        with rasterio.open(path) as ds:
            nb = ds.count
        for lon, lat in pts:
            A, grid = grab_common(path, lon, lat, args.box_m, args.grid_cm / 100.0)
            if A is None:
                continue
            m = grab_mask(*grid)
            if m is None:
                continue
            idx, name = canopy_index(A, nb)
            valid = np.isfinite(idx) & (A.sum(axis=0) > 0) & (m != 255)
            pos_all.append(idx[valid & (m == 1)])
            neg_all.append(idx[valid & (m == 0)])
            used += 1
        if not used:
            return dict(file=rec["file"], key=rec["key"], note="no usable sample windows")
        pos = np.concatenate(pos_all); neg = np.concatenate(neg_all)
        a = auroc(pos, neg)
        pooled = np.sqrt((pos.var() + neg.var()) / 2) if pos.size and neg.size else np.nan
        d = float((pos.mean() - neg.mean()) / pooled) if pooled and np.isfinite(pooled) and pooled > 0 else float("nan")
        row = dict(file=rec["file"], key=rec["key"], year=QS.year_of(rec["key"]), index=name,
                   windows=used, n_canopy_px=int(pos.size), n_background_px=int(neg.size),
                   canopy_frac=round(float(pos.size / max(pos.size + neg.size, 1)), 4),
                   auroc=round(a, 4) if np.isfinite(a) else None,
                   cohens_d=round(d, 3) if np.isfinite(d) else None,
                   median_canopy=round(float(np.median(pos)), 4) if pos.size else None,
                   median_background=round(float(np.median(neg)), 4) if neg.size else None)
        print(f"  {row['auroc'] if row['auroc'] is not None else ' n/a ':>6} AUROC  {rec['file']:32s} "
              f"{name:5s} d={row['cohens_d']}  ({used} windows, {pos.size:,} canopy px)", flush=True)
        return row
    except Exception as ex:
        return dict(file=rec["file"], key=rec["key"], note=f"ERROR {type(ex).__name__}: {ex}")


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", type=int, default=40)
    ap.add_argument("--box-m", type=float, default=60.0)
    ap.add_argument("--grid-cm", type=float, default=50.0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only")
    ap.add_argument("--outdir", type=Path, default=SCRIPTS.parent / "phase4" / "qc")
    args = ap.parse_args(argv)
    if MASK is None:
        sys.exit("2020 canopy mask not found on this machine")
    args.outdir.mkdir(parents=True, exist_ok=True)

    inv = [r for r in QS.inventory(args.only) if r["path"] is not None]
    pts = sample_points(args.points)
    print(f"CANOPY SEPARABILITY — {len(inv)} rasters x {len(pts)} seeded locations, "
          f"{args.box_m:.0f} m boxes on a common {args.grid_cm:.0f} cm grid\n  mask: {MASK}")
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(lambda rec: score_raster(rec, pts, args), inv):
            if r:
                rows.append(r)
    rows.sort(key=lambda r: -(r.get("auroc") or 0))
    out = args.outdir / f"imagery_canopy_separability_{TODAY}.csv"
    QS.write_csv(rows, out)

    # the honest reading: within-year contrast
    by_year = {}
    for r in rows:
        if r.get("auroc"):
            by_year.setdefault(r.get("year"), []).append(r)
    print("\n  WITHIN-YEAR CONTRAST (the comparison the mask's caveats cancel out of)")
    contrast = []
    for y, rs in sorted(by_year.items()):
        if len(rs) < 2:
            continue
        rs = sorted(rs, key=lambda r: -r["auroc"])
        best, worst = rs[0], rs[-1]
        contrast.append(dict(year=y, n=len(rs), best=best["file"], best_auroc=best["auroc"],
                             worst=worst["file"], worst_auroc=worst["auroc"],
                             spread=round(best["auroc"] - worst["auroc"], 4)))
        print(f"   {y}  spread {best['auroc']-worst['auroc']:.3f}   best {best['file']:30s} {best['auroc']:.3f}"
              f"   worst {worst['file']:30s} {worst['auroc']:.3f}")
    QS.write_csv(contrast, args.outdir / f"imagery_separability_within_year_{TODAY}.csv")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
