"""
imagery_measure.py -- measurements that decide whether an acquired raster is "better" (campaign 2026-08-23).

Everything here is MEASURED from pixels; nothing is copied from a service's advertised resolution.
  describe(path)                true GSD from the WGS84 span (unit-safe), CRS unit, size, bands, dtype
  effective_cm_*()              10-90% edge-response rise x true GSD; esf()/rise_px() copied VERBATIM
                                from scratch/litwatch_scratch/q138b.py (the script behind Effective_Resolution)
  band_verdict_array()          band 4 = NIR or ALPHA or UNDETERMINED (std / unique / corr / NDVI at forest sites)
  jpeg_block_score()            8x8 DCT-block boundary signature (boundary/within gradient ratio, z-score)
  band_registration_px()        sub-pixel phase-correlation shift of blue and red against green
  study_coverage_pct()          % of the study extent with non-zero data (decimated read)
  compare_to_held_arrays()      new vs held on a common grid: HF-energy ratio, PSNR, Pearson r
  decide()                      the lexicographic replacement test from the plan
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np

PX, HALF, SUB = 512, 6, 4     # q138b: profile reaches +/-6 px, sampled at 1/4 px
# the five Method_Provenance sites (WGS84); all land, all inside every held footprint
SITES = {"S1_forest_nw": (-122.3580, 47.8225), "S2_parking": (-122.3270, 47.8060), "S3_residential": (-122.3700, 47.8100),
         "S4_forest_s": (-122.3545, 47.7855), "S5_suburb_ne": (-122.3400, 47.8250)}
FOREST = ("S1_forest_nw", "S4_forest_s")


# ----------------------------------------------------------------------------- q138b.py, verbatim
def esf(a):
    """Average Edge Spread Function from the strongest edges in the window."""
    gy, gx = np.gradient(a)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 97.0)
    ys, xs = np.nonzero(mag >= thr)
    keep = (ys > HALF+1) & (ys < a.shape[0]-HALF-1) & (xs > HALF+1) & (xs < a.shape[1]-HALF-1)
    ys, xs = ys[keep], xs[keep]
    if ys.size < 40: return None
    if ys.size > 900:
        sel = np.linspace(0, ys.size-1, 900).astype(int); ys, xs = ys[sel], xs[sel]
    off = np.arange(-HALF, HALF + 1/SUB, 1/SUB)
    prof = []
    for y, x in zip(ys, xs):
        d = np.hypot(gx[y, x], gy[y, x])
        if d < 1e-6: continue
        ux, uy = gx[y, x]/d, gy[y, x]/d          # unit vector ACROSS the edge
        yy = np.clip(y + off*uy, 0, a.shape[0]-1)
        xx = np.clip(x + off*ux, 0, a.shape[1]-1)
        v = a[np.round(yy).astype(int), np.round(xx).astype(int)].astype(np.float32)
        lo, hi = v[:3].mean(), v[-3:].mean()
        if hi - lo < 6: continue                  # need a real step, not noise
        prof.append((v - lo) / (hi - lo))
    if len(prof) < 20: return None
    return off, np.median(np.array(prof), axis=0)


def rise_px(off, e):
    """10-90% rise distance in PIXELS by explicit crossing search."""
    e = np.asarray(e, dtype=np.float64)
    lo, hi = np.percentile(e[:4], 50), np.percentile(e[-4:], 50)
    if hi - lo < 0.5: return np.nan
    e = (e - lo) / (hi - lo)
    c = int(np.argmin(np.abs(off)))          # centre of the profile

    def cross(level, direction):
        rng = range(c, len(e)-1) if direction > 0 else range(c, 0, -1)
        for i in rng:
            j = i + 1 if direction > 0 else i - 1
            a_, b_ = e[i], e[j]
            if (a_ - level) * (b_ - level) <= 0 and abs(b_ - a_) > 1e-9:
                t = (level - a_) / (b_ - a_)
                return off[i] + t * (off[j] - off[i])
        return np.nan

    x90 = cross(0.90, +1)
    x10 = cross(0.10, -1)
    if not (np.isfinite(x10) and np.isfinite(x90)): return np.nan
    w = x90 - x10
    return float(w) if 0 < w < 2*HALF - 0.2 else np.nan


# ----------------------------------------------------------------------------- helpers
def _window_at(ds, lon, lat, size_px):
    """Native window of `size_px` centred on (lon, lat); origin snapped to a multiple of 16 (Method_Provenance)."""
    from rasterio.warp import transform as warp_xy
    from rasterio.windows import Window
    xs, ys = warp_xy("EPSG:4326", ds.crs, [lon], [lat])
    row, col = ds.index(xs[0], ys[0])
    if not (0 <= row < ds.height and 0 <= col < ds.width):
        return None
    r0 = max(0, min(ds.height - size_px, row - size_px // 2)); c0 = max(0, min(ds.width - size_px, col - size_px // 2))
    r0 -= r0 % 16; c0 -= c0 % 16
    return Window(c0, r0, min(size_px, ds.width - c0), min(size_px, ds.height - r0))


def true_gsd_cm(ds) -> tuple[float, str]:
    """Ground metres per pixel from the WGS84 span of the raster (unit-safe by construction)."""
    from rasterio.warp import transform_bounds
    b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
    mid = (b[1] + b[3]) / 2
    km_w = (b[2] - b[0]) * 111.320 * math.cos(math.radians(mid))
    unit = ds.crs.linear_units if ds.crs else "?"
    return km_w * 1000 / ds.width * 100, unit


def describe(path: Path) -> dict:
    import rasterio
    with rasterio.open(path) as ds:
        g, unit = true_gsd_cm(ds)
        return {"file": Path(path).name, "bytes": Path(path).stat().st_size, "width": ds.width, "height": ds.height,
                "bands": ds.count, "dtype": ds.dtypes[0], "epsg": ds.crs.to_epsg() if ds.crs else None, "units": unit,
                "px": float(ds.res[0]), "true_gsd_cm": round(g, 3), "nodata": ds.nodata,
                "overviews": ds.overviews(1), "descriptions": list(ds.descriptions), "tags": ds.tags()}


def effective_cm_array(a: np.ndarray, true_cm: float) -> dict:
    a = a.astype(np.float32)
    if a.std() < 3:
        return {"rise_px": None, "effective_cm": None, "note": "flat window"}
    out = esf(a)
    if out is None:
        return {"rise_px": None, "effective_cm": None, "note": "too few edges"}
    v = rise_px(*out)
    if not np.isfinite(v):
        return {"rise_px": None, "effective_cm": None, "note": "no 10-90 crossing"}
    return {"rise_px": round(float(v), 3), "effective_cm": round(float(v) * true_cm, 2)}


def effective_cm_file(path: Path, band=1, sites=SITES) -> dict:
    """Median over the five sites of the 10-90% rise x true GSD (the Effective_Resolution method)."""
    import rasterio
    per = {}
    with rasterio.open(path) as ds:
        g, _ = true_gsd_cm(ds)
        for name, (lon, lat) in sites.items():
            w = _window_at(ds, lon, lat, PX)
            if w is None:
                per[name] = {"note": "outside"}; continue
            a = ds.read(band, window=w)
            per[name] = effective_cm_array(a, g)
    vals = [p["effective_cm"] for p in per.values() if p.get("effective_cm")]
    return {"true_gsd_cm": round(g, 3), "sites": per, "n_sites": len(vals),
            "effective_cm": round(float(np.median(vals)), 2) if vals else None,
            "oversampling": round(float(np.median(vals)) / g, 2) if vals else None}


def effective_cm_at(path: Path, lon: float, lat: float, box_m: float, band=1) -> dict:
    import rasterio
    with rasterio.open(path) as ds:
        g, _ = true_gsd_cm(ds)
        n = int(box_m / (g / 100)); n -= n % 16
        w = _window_at(ds, lon, lat, max(128, n))
        if w is None:
            return {"note": "outside held footprint"}
        a = ds.read(band, window=w)
    r = effective_cm_array(a, g); r["true_gsd_cm"] = round(g, 3); return r


def band_verdict_array(A: np.ndarray, names=None, forest_mask=None) -> dict:
    """A = (bands, h, w). Band 4 verdict: ALPHA (constant), NIR (varying, decorrelated from red, NDVI>0.2 over
    vegetation), else UNDETERMINED. Positive controls: Aerial_2017 must be NIR, Aerial_2015 default ALPHA."""
    out = {"bands": int(A.shape[0]), "per_band": []}
    for i in range(A.shape[0]):
        b = A[i]; out["per_band"].append({"band": i + 1, "name": (names or [None] * 9)[i] if names and i < len(names) else None,
                                          "min": int(b.min()), "max": int(b.max()), "mean": round(float(b.mean()), 2),
                                          "std": round(float(b.std()), 2), "unique": int(len(np.unique(b[::7, ::7])))})
    if A.shape[0] >= 4:
        b4 = A[3].astype(np.float32); r = A[0].astype(np.float32)
        std = float(b4.std()); uniq = out["per_band"][3]["unique"]
        corr = float(np.corrcoef(b4.ravel()[::13], r.ravel()[::13])[0, 1]) if std > 0 and r.std() > 0 else None
        ndvi = (b4 - r) / np.maximum(b4 + r, 1)
        veg = ndvi[(b4 > 20) & (r > 5)]
        p90 = float(np.percentile(ndvi, 90)) if ndvi.size else None
        if std == 0:
            v = "ALPHA"
        elif std > 5 and uniq > 32 and corr is not None and corr < 0.98 and (p90 is not None and p90 > 0.2):
            v = "NIR"
        else:
            v = "UNDETERMINED"
        out["band4"] = {"verdict": v, "std": round(std, 2), "unique": uniq, "corr_with_red": round(corr, 3) if corr is not None else None,
                        "ndvi_p90": round(p90, 3) if p90 is not None else None}
    return out


def jpeg_block_score(a: np.ndarray) -> dict:
    """Mean |first difference| at 8x8 block boundaries vs within blocks (both axes). A ratio well above 1
    with a large z means the pixels carry a JPEG 8x8 quantisation grid (the tile-cache signature)."""
    a = a.astype(np.float32)
    dx = np.abs(np.diff(a, axis=1)); dy = np.abs(np.diff(a, axis=0))
    def ratio(d, axis):
        idx = np.arange(d.shape[axis]) + 1     # diff i sits between column i and i+1
        bnd = (idx % 8 == 0)
        if axis == 1:
            b = d[:, bnd].mean(); w = d[:, ~bnd].mean()
        else:
            b = d[bnd, :].mean(); w = d[~bnd, :].mean()
        return float(b / max(w, 1e-6))
    rx, ry = ratio(dx, 1), ratio(dy, 0)
    # phase test: is the boundary phase 7 (mod 8) the unique maximum?
    prof_x = [float(dx[:, (np.arange(dx.shape[1]) + 1) % 8 == k].mean()) for k in range(8)]
    prof_y = [float(dy[(np.arange(dy.shape[0]) + 1) % 8 == k, :].mean()) for k in range(8)]
    zx = (prof_x[0] - np.mean(prof_x[1:])) / max(np.std(prof_x[1:]), 1e-6)
    zy = (prof_y[0] - np.mean(prof_y[1:])) / max(np.std(prof_y[1:]), 1e-6)
    sig = bool(rx > 1.05 and ry > 1.05 and zx > 3 and zy > 3)
    return {"ratio_x": round(rx, 4), "ratio_y": round(ry, 4), "z_x": round(float(zx), 2), "z_y": round(float(zy), 2), "signature": sig}


def band_registration_px(A: np.ndarray) -> dict:
    """Sub-pixel shift of blue and red relative to green by phase correlation (the 0.224-px metric)."""
    def shift(a, b):
        a = a.astype(np.float32) - a.mean(); b = b.astype(np.float32) - b.mean()
        F = np.fft.fft2(a) * np.conj(np.fft.fft2(b)); F /= np.maximum(np.abs(F), 1e-9)
        c = np.fft.ifft2(F).real
        py, px = np.unravel_index(np.argmax(c), c.shape)
        h, w = c.shape
        def par(v_m, v_0, v_p):
            d = v_m - 2 * v_0 + v_p
            return 0.0 if abs(d) < 1e-12 else 0.5 * (v_m - v_p) / d
        dy = py + par(c[(py - 1) % h, px], c[py, px], c[(py + 1) % h, px])
        dx = px + par(c[py, (px - 1) % w], c[py, px], c[py, (px + 1) % w])
        if dy > h / 2: dy -= h
        if dx > w / 2: dx -= w
        return float(dx), float(dy)
    if A.shape[0] < 3:
        return {}
    bx, by = shift(A[1], A[2]); rx, ry = shift(A[1], A[0])
    return {"blue_vs_green_px": round(math.hypot(bx, by), 3), "red_vs_green_px": round(math.hypot(rx, ry), 3)}


def study_coverage_pct(path: Path, extent_3857, step=8) -> dict:
    """% of the study extent (EPSG:3857 box) whose pixels are non-zero in at least one band; decimated read."""
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    with rasterio.open(path) as ds:
        b = transform_bounds("EPSG:3857", ds.crs, *extent_3857)
        win = from_bounds(*b, transform=ds.transform)
        full_px = win.width * win.height
        win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
        inter_px = max(0, win.width) * max(0, win.height)
        if inter_px <= 0:
            return {"study_coverage_pct": 0.0, "extent_overlap_pct": 0.0}
        win = win.round_offsets().round_lengths()
        out_shape = (ds.count, max(1, int(win.height // step)), max(1, int(win.width // step)))
        a = ds.read(window=win, out_shape=out_shape)
        data = np.any(a != (ds.nodata if ds.nodata is not None else 0), axis=0)
        frac = float(data.mean()) * (inter_px / full_px)
        return {"study_coverage_pct": round(100 * frac, 2), "extent_overlap_pct": round(100 * inter_px / full_px, 2), "decimation": step}


def compare_to_held_arrays(new_path: Path, held_path: Path, lon: float, lat: float, box_m: float) -> dict:
    """Resample both to a common grid (the coarser of the two true GSDs) and compare band 1:
    HF-energy ratio (new/held), PSNR, Pearson r. >1.0 HF ratio = new resolves more detail."""
    import rasterio
    from rasterio.warp import reproject, Resampling, transform as warp_xy
    from rasterio.transform import from_origin
    with rasterio.open(new_path) as n, rasterio.open(held_path) as h:
        gn, _ = true_gsd_cm(n); gh, _ = true_gsd_cm(h)
        g = max(gn, gh) / 100.0
        # common grid in the HELD crs (metres-equivalent handled by true gsd); use held crs + its own px scaled
        px_h = float(h.res[0]) * (g / (gh / 100.0))
        xs, ys = warp_xy("EPSG:4326", h.crs, [lon], [lat])
        n_px = int(box_m / g); n_px -= n_px % 16
        x0 = xs[0] - n_px * px_h / 2; y1 = ys[0] + n_px * px_h / 2
        tr = from_origin(x0, y1, px_h, px_h)
        def grab(src):
            dst = np.zeros((n_px, n_px), dtype=np.float32)
            reproject(rasterio.band(src, 1), dst, dst_transform=tr, dst_crs=h.crs, resampling=Resampling.average)
            return dst
        A, B = grab(n), grab(h)
    ok = (A > 0) & (B > 0)
    if ok.mean() < 0.5:
        return {"note": "less than half the box has data in both files", "overlap_frac": float(ok.mean())}
    def hf(x):
        gy, gx = np.gradient(x); return float(np.mean(gx[ok] ** 2 + gy[ok] ** 2))
    mse = float(np.mean((A[ok] - B[ok]) ** 2)); psnr = 10 * math.log10(255 ** 2 / max(mse, 1e-9))
    r = float(np.corrcoef(A[ok], B[ok])[0, 1])
    # edge rise measured on the SAME grid for both (the native-grid rise metric cannot read below ~1 px,
    # so it flatters an interpolated copy - pilot S16 2026-08-23: 41 cm native vs 34 cm on the 2x upsample)
    en, eh = effective_cm_array(A, g * 100), effective_cm_array(B, g * 100)
    return {"common_px_cm": round(g * 100, 2), "hf_ratio_new_over_held": round(hf(A) / max(hf(B), 1e-9), 3), "psnr_db": round(psnr, 2),
            "pearson_r": round(r, 4), "overlap_frac": round(float(ok.mean()), 3),
            "effective_cm_common_new": en.get("effective_cm"), "effective_cm_common_held": eh.get("effective_cm")}


def pilot_site(site: str, held: Path | None, service_extent: dict | None, epsg: int):
    """'auto' -> first Method_Provenance site inside the held file (if any) and the service extent; 'centre' ->
    service-extent centre; 'S1_forest_nw' etc. -> that site."""
    from pyproj import Transformer
    if site in SITES:
        return SITES[site]
    if site == "centre" and service_extent:
        t = Transformer.from_crs(epsg, 4326, always_xy=True)
        return t.transform((service_extent["xmin"] + service_extent["xmax"]) / 2, (service_extent["ymin"] + service_extent["ymax"]) / 2)
    cands = list(SITES.values())
    if held and Path(held).exists():
        import rasterio
        from rasterio.warp import transform as warp_xy
        with rasterio.open(held) as ds:
            keep = []
            for lon, lat in cands:
                xs, ys = warp_xy("EPSG:4326", ds.crs, [lon], [lat])
                r, c = ds.index(xs[0], ys[0])
                if 300 <= r < ds.height - 300 and 300 <= c < ds.width - 300:
                    keep.append((lon, lat))
        cands = keep or cands
    if service_extent:
        t = Transformer.from_crs(4326, epsg, always_xy=True)
        keep = []
        for lon, lat in cands:
            x, y = t.transform(lon, lat)
            if service_extent["xmin"] < x < service_extent["xmax"] and service_extent["ymin"] < y < service_extent["ymax"]:
                keep.append((lon, lat))
        cands = keep or cands
    return cands[0]


def measure_file(path: Path, study_extent_3857, held: Path | None = None) -> dict:
    import rasterio
    d = describe(path)
    eff = effective_cm_file(path)
    with rasterio.open(path) as ds:
        w = _window_at(ds, *SITES["S3_residential"], PX) or rasterio.windows.Window(0, 0, min(PX, ds.width), min(PX, ds.height))
        A = ds.read(window=w)
        forest = []
        for nm in FOREST:
            wf = _window_at(ds, *SITES[nm], PX)
            if wf is not None: forest.append(ds.read(window=wf))
    bands = band_verdict_array(np.concatenate([A] + forest, axis=1) if forest else A, names=d["descriptions"])
    meas = dict(d, effective_cm=eff["effective_cm"], oversampling=eff["oversampling"], sites=eff["sites"], n_sites=eff["n_sites"],
                band_verdict=bands, jpeg_block=jpeg_block_score(A[0]), registration=band_registration_px(A) if A.shape[0] >= 3 else {},
                **study_coverage_pct(path, study_extent_3857))
    if held is not None and Path(held).exists():
        hd = describe(held); he = effective_cm_file(held)
        with rasterio.open(held) as hs:
            wh = _window_at(hs, *SITES["S3_residential"], PX)
            H = hs.read(window=wh) if wh is not None else None
        meas["held"] = {"file": hd["file"], "true_gsd_cm": hd["true_gsd_cm"], "bands": hd["bands"], "effective_cm": he["effective_cm"],
                        "jpeg_block": jpeg_block_score(H[0]) if H is not None else None,
                        "registration": band_registration_px(H) if H is not None and H.shape[0] >= 3 else {},
                        **study_coverage_pct(held, study_extent_3857)}
        lon, lat = SITES["S3_residential"]
        meas["compare_to_held"] = compare_to_held_arrays(path, held, lon, lat, 300)
    return meas


def decide(t: dict, meas: dict) -> dict:
    """Lexicographic replacement test. REPLACE needs at least one strict win and no loss; else COMPLEMENT;
    any hard failure (licence blocked, required NIR absent, coverage below the floor) -> REJECT."""
    test = t.get("test", {}); reasons = []; wins = []; losses = []
    lic = str(t.get("licence", ""))
    if "BLOCKED" in lic.upper():
        return {"verdict": "REJECT", "reasons": ["licence blocked"]}
    b4 = (meas.get("band_verdict") or {}).get("band4", {}).get("verdict")
    if test.get("nir") == "required" and b4 != "NIR":
        reasons.append(f"band 4 verdict {b4}, NIR required")
    cov = meas.get("study_coverage_pct")
    if test.get("coverage_min_pct") and cov is not None and cov < test["coverage_min_pct"]:
        reasons.append(f"coverage {cov}% < {test['coverage_min_pct']}%")
    eff = (meas.get("compare_to_held") or {}).get("effective_cm_common_new") or meas.get("effective_cm")
    if test.get("effective_max_cm") and eff and eff > test["effective_max_cm"] and not ((meas.get("compare_to_held") or {}).get("hf_ratio_new_over_held", 0) >= 1.0):
        reasons.append(f"effective {eff} cm > {test['effective_max_cm']} cm and not sharper on a common grid")
    if test.get("block_signature") == "absent" and (meas.get("jpeg_block") or {}).get("signature"):
        reasons.append("JPEG 8x8 block signature present")
    if reasons:
        return {"verdict": "REJECT", "reasons": reasons}
    held = meas.get("held")
    if held:
        if meas.get("bands", 0) > held.get("bands", 0): wins.append("more bands")
        elif meas.get("bands", 0) < held.get("bands", 0): losses.append("fewer bands")
        if cov is not None and held.get("study_coverage_pct") is not None:
            if cov > held["study_coverage_pct"] + 1: wins.append(f"coverage {cov} > {held['study_coverage_pct']}")
            elif cov < held["study_coverage_pct"] - 1: losses.append("less coverage")
        cmp = meas.get("compare_to_held") or {}
        e, eh = cmp.get("effective_cm_common_new"), cmp.get("effective_cm_common_held")
        if e and eh:                                   # same grid for both - the only fair rise comparison
            if e <= eh * 0.9: wins.append(f"effective (common grid) {e} vs {eh} cm")
            elif e > eh * 1.10: losses.append(f"effective (common grid) {e} vs {eh} cm")
        hfr = cmp.get("hf_ratio_new_over_held")
        if hfr is not None:
            if hfr >= 1.10: wins.append(f"HF energy ratio {hfr} (sharper on a common grid)")
            elif hfr < 0.90: losses.append(f"HF energy ratio {hfr} (softer on a common grid)")
        if held.get("jpeg_block", {}).get("signature") and not (meas.get("jpeg_block") or {}).get("signature"): wins.append("no JPEG block signature (held has one)")
        r, rh = (meas.get("registration") or {}).get("blue_vs_green_px"), (held.get("registration") or {}).get("blue_vs_green_px")
        if r is not None and rh is not None and r > rh + 0.1: losses.append(f"blue registration {r} px worse than held {rh}")
        if t.get("replaces"):
            if wins and not losses:
                return {"verdict": "REPLACE", "wins": wins, "losses": losses, "reasons": ["one or more strict wins, no loss"]}
            return {"verdict": "COMPLEMENT", "wins": wins, "losses": losses, "reasons": ["no strict win or a loss vs the incumbent"]}
        return {"verdict": "COMPLEMENT", "wins": wins, "losses": losses, "reasons": ["complements the incumbent (not a replacement candidate)"]}
    return {"verdict": "COMPLEMENT", "wins": wins, "losses": losses, "reasons": ["no incumbent"]}


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(json.dumps(measure_file(Path(p), [-13625876.424, 6068463.621, -13614805.955, 6084271.153]), indent=1, default=str))
