r"""Post-stratified sector canopy + within-strip E-W gradient bins (sector program, 2026-08-26).

WHY. `sector_canopy_series.csv` gives one number per (year, tag, sector). That single number
mixes two things a reader wants separated: (1) how much canopy each LAND-COVER TYPE carries, and
(2) where in the strip the canopy sits. A sector whose developed fraction rose will show a canopy
drop even if neither forest nor developed changed at all. This script decomposes each sector two
ways — by C-CAP stratum and by west->east position — so composition shifts and real level shifts
stop being the same column.

ZERO NEW INFERENCE. Every input is already on the lake:
  * the 1-m cover sidecars phase4/qc/sector_campaign/cover1m/cover_1m_{year}[_{tag}].tif written
    by qc/phase4_sector_series.py (float32 cover fraction per 1-m cell, nodata -1, already
    clipped to sector ∩ city − waterbody and thresholded at that arm's deployed threshold);
  * the sector polygons phase4/qc/sectors/{version}.gpkg + pipeline/aoi/{version}.json;
  * the C-CAP rasters.

STRATA COME FROM A FIXED EPOCH. The spine is the 2016 C-CAP (`ccap_2016_hires_lc_snohfull.tif`,
the only variant that reaches S1/S2 — the clipped pair ends at y=6,079,042 in EPSG:3857). Holding
stratum membership fixed across all years is the point: if strata were re-cut per year, real
land-cover change would be absorbed into stratum MEMBERSHIP and vanish from the canopy numbers.
The cost is that a cell developed in 2019 is still scored inside its 2016 stratum — which is
exactly what you want when the question is "did canopy change on ground that was forest in 2016".

STABLE CORE. A second variant restricts to cells where the 2016 and 2021 C-CAP epochs agree at
GROUP level (deciduous->mixed inside `forest` is not an eviction). That is the subset whose
stratum label is not epoch-dependent, so its levels are the cleanest. It exists only for S3-S5:
the 2021 raster does not reach S1/S2, whose rows are flagged `single_epoch=1` with EMPTY (never
zero) stable columns.

LEVELS INHERIT THE CITYWIDE OPERATING-POINT CAVEAT. Cover comes from each arm's DEPLOYED
threshold, chosen citywide. Per-stratum levels are therefore comparable ACROSS STRATA within an
arm and across years within a stratum, but they are not calibrated per stratum — a stratum where
the model is systematically shy (deciduous marsh; see the phase3 mask gotcha) stays shy here.
These are raw thresholded cover fractions: the precision/recall adjustment `p_adj` that
sector_canopy_series applies is NOT applied per stratum, because the live qc_indep row's
precision and recall are citywide, not per stratum. Compare LEVELS, not absolute truth.

REGISTRATION GUARD (2026-08-26 — READ THIS). The cover sidecars are NOT all spatially registered.
qc/phase4_sector_series.py accumulates each native strip into the 1-m plane with

    c0 = int(np.floor(bb[0] - b3857[0])); r0m = int(np.floor(b3857[3] - bb[3]))
    cc = slice(max(0, c0), max(0, c0) + dstw)        # <- clamps the DESTINATION offset
    cov_sum[rr.start:..., cc.start:...][sub_ok] += tgt[:h2, :w2][sub_ok]   # <- never trims tgt

so whenever a strip starts WEST of (or NORTH of) the cover grid — i.e. whenever the prob raster
is wider than the sector envelope — the reprojected plane is written translated by |c0| east
(|r0m| south). Measured: 2013/citywide_rgb is a clean +458 m eastward translation in S2-S5
(predicted 459 from the raster's west edge); 2020s/sectors_v1 varies 497-667 m by sector because
its EPSG:2285 source gives a different per-strip 3857 bbox; 2019n/p2nir, whose raster starts EAST
of the grid, matches the land footprint to +/-2 m. S1 sits on the grid's top edge, so the strips
above it pile into row 0 and S1 is corrupted or empty for essentially every arm.

This script therefore verifies registration per (arm, sector) against the rasterised land polygon
before using a sidecar, and SKIPS what does not register. Fixing the writer is the owner's job
(the fix is to trim the source instead of clamping the destination: sx = -min(0, c0),
sy = -min(0, r0m), then index tgt[sy:sy+h2, sx:sx+w2]); once sidecars regenerate, rerun this
script unchanged. Nothing here un-shifts anything — an auto-correction would silently corrupt
clean sidecars the day the writer is fixed.

GRADIENT BINS. Each sector is split into 4 west->east bins by the anchor lattice's BLOCK-COLUMN
index (152.874 m per block-col), using west_col/east_col from the aoi json. Edges are
`west_col + floor(k*(east_col-west_col)/4)` for k=0..4 and are written into every row, so the bin
definition travels with the data. Cells in the westward water-extension (block-col < west_col)
fall in bin 0. Each bin also carries the true-ground distance from its centre to the PUGET SOUND
polygon (`dist_sound_m_mid`) — the corrected shore covariate, not the old any-waterbody one.

OUTPUTS (data:phase4/qc/sector_campaign/)
  sector_poststrat.csv        (year, tag, sector, ccap_group) x {spine, stable core}
  sector_gradient_bins.csv    (year, tag, sector, ew_bin)
  sector_cover1m_registration.csv   the guard's verdict for EVERY (arm, sector) it looked at,
                                    including the ones it refused to use — the durable evidence
                                    for the sidecar defect, and the re-check after it is fixed
Both files carry '#'-prefixed header comments — read them with
`pd.read_csv(p, comment='#')` or skip leading '#' lines before csv.DictReader.

USAGE
  py -3.12 qc/phase4_sector_poststrat.py                       # every cover1m sidecar
  py -3.12 qc/phase4_sector_poststrat.py --arms 2013:citywide_rgb 2020s:sectors_v1 2019n:p2nir
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_measure as im                      # noqa: E402  (CITY_SHP local-first)
from phase4_qc_indep import CCAP_DEFAULT          # noqa: E402  (ONE home for the class->group map)

DATA = Path(r"G:\My Drive\treedata")
CAMP = DATA / "phase4" / "qc" / "sector_campaign"
COV1M = CAMP / "cover1m"
WATER_SHP = DATA / "bathology" / "GDBA_HYDROGRAPHY__waterbody_snoco.shp"
CRS = "EPSG:3857"
COS_LAT = float(np.cos(np.radians(47.81)))

# the anchor lattice (pipeline/make_sectors.py — block-col index for the E-W bins)
ORIGIN_X = -13625893.973200373
BLOCK_M = 4 * 512 * 0.07464553543473991      # 152.8740565…
N_EW_BINS = 4

# C-CAP epoch spine + the second epoch used only for the stable core. Same resolution order as
# pipeline/make_sectors.CCAP_SOURCES: the snohfull 2016 variant is the only one covering S1/S2.
CCAP_SPINE = ("ccap_2016_hires_lc_snohfull.tif", "ccap_2016_hires_lc.tif")
CCAP_SECOND = ("ccap_2021_hires_lc.tif",)
IMAGERY_ROOTS = (Path(r"D:\edmonds-pipeline\Imagery"), DATA / "Full_Image" / "Pipeline Imagery")


def ccap_path(cands):
    for name in cands:
        for root in IMAGERY_ROOTS:
            p = root / name
            if p.exists():
                return p
    return None


def group_lut():
    """256-entry code->group-index LUT from qc/phase4_qc_indep.CCAP_DEFAULT (one home)."""
    groups = CCAP_DEFAULT["groups"]
    names = list(groups.keys())
    if "other" not in names:
        names.append("other")                     # codes the legend does not name
    idx = {g: i for i, g in enumerate(names)}
    lut = np.full(256, idx["other"], dtype=np.uint8)
    for g, codes in groups.items():
        for c in codes:
            lut[int(c)] = idx[g]
    return names, lut


def parse_arm(path):
    """cover_1m_{year}[_{tag}].tif -> (year, tag). Year may carry a season/sensor letter."""
    m = re.fullmatch(r"cover_1m_([0-9]{4}[a-z]?)(?:_(.+))?", path.stem)
    return (m.group(1), m.group(2) or "") if m else None


def series_p_raw():
    """(year, tag) -> {sector: p_raw} from sector_canopy_series.csv, for the sanity check."""
    p = CAMP / "sector_canopy_series.csv"
    out = {}
    if not p.exists():
        return out
    for r in csv.DictReader(open(p, encoding="utf-8")):
        try:
            out.setdefault((r["year"], r.get("tag", "")), {})[r["sector"]] = float(r["p_raw"])
        except (KeyError, ValueError):
            continue
    return out


def _mean(cov, mask):
    n = int(mask.sum())
    return n, (round(float(cov[mask].mean()), 5) if n else "")


def _edges(profile, thresh=20):
    """(first, last) index where a row/column profile carries >= thresh cells, or (None, None)."""
    idx = np.flatnonzero(profile >= thresh)
    return (int(idx[0]), int(idx[-1])) if idx.size else (None, None)


def check_registration(valid, land, tol):
    """Compare a sidecar's valid FOOTPRINT with the sector's land raster.

    The sector_series clamp bug translates the plane east/south, so the WEST and NORTH edges are
    the diagnostic ones (east/south get clipped by the window and are reported, not tested).
    Conservative by design: an arm with genuinely partial west-side coverage also trips this —
    the measured deltas are printed and written so a human can adjudicate.
    """
    n_land = int(land.sum())
    n_ov = int((valid & land).sum())
    cov_frac = (n_ov / n_land) if n_land else 0.0
    vc, lc = valid.sum(0), land.sum(0)
    vr, lr = valid.sum(1), land.sum(1)
    (vw, ve), (lw, le) = _edges(vc), _edges(lc)
    (vn, vs), (ln, ls) = _edges(vr), _edges(lr)
    if vw is None or lw is None or cov_frac < 0.02:
        return {"ok": 0, "status": "empty", "dW": "", "dE": "", "dN": "", "dS": "",
                "cov_frac": round(cov_frac, 4)}
    d = {"dW": vw - lw, "dE": ve - le, "dN": vn - ln, "dS": vs - ls,
         "cov_frac": round(cov_frac, 4)}
    ok = abs(d["dW"]) <= tol and abs(d["dN"]) <= tol
    d["ok"] = int(ok)
    d["status"] = "ok" if ok else "shifted"
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="pipeline/aoi/sectors_v1.json")
    ap.add_argument("--arms", nargs="*", default=None,
                    help="year:tag selectors (e.g. 2013:citywide_rgb). Default: every sidecar.")
    ap.add_argument("--min-cells", type=int, default=500,
                    help="strata/bins with fewer valid cells are written with an empty mean")
    ap.add_argument("--reg-tol-m", type=int, default=3,
                    help="max |west/north footprint edge delta| (m) still counted as registered")
    ap.add_argument("--allow-misregistered", action="store_true",
                    help="write rows for sectors that FAIL the registration guard, flagged "
                         "registration_ok=0. Off by default — those numbers are wrong.")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    import geopandas as gpd
    import rasterio
    import rasterio.features
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import Resampling
    from shapely.geometry import Point
    from shapely.ops import unary_union

    aoi_p = Path(a.aoi) if Path(a.aoi).is_absolute() else SCRIPTS / a.aoi
    aoi = json.loads(aoi_p.read_text(encoding="utf-8"))
    ver = aoi["version"]
    aoi_sec = {s["id"]: s for s in aoi["sectors"]}
    gpkg = DATA / "phase4" / "qc" / "sectors" / f"{ver}.gpkg"
    sectors = gpd.read_file(gpkg, layer="sectors")
    print(f"{ver}: {len(sectors)} sectors; covariates_updated="
          f"{aoi.get('covariates_updated', 'UNSTAMPED')}")

    # the 1-m cover grid is DERIVED from the gpkg total_bounds by phase4_sector_series.py;
    # every sidecar is asserted against it below rather than assumed.
    tb = sectors.total_bounds
    cov_w, cov_h = int(np.ceil(tb[2] - tb[0])), int(np.ceil(tb[3] - tb[1]))
    from rasterio.transform import from_origin
    cov_tf = from_origin(tb[0], tb[3], 1.0, 1.0)

    # per-sector LAND polygon (sector ∩ city − water) — the year-independent post-strat denominator
    city = gpd.read_file(im.CITY_SHP).to_crs(CRS)
    city_poly = city.union_all() if hasattr(city, "union_all") else city.unary_union
    water = gpd.read_file(WATER_SHP)
    if water.crs is not None and water.crs.to_epsg() != 3857:
        water = water.to_crs(CRS)
    water = water[water.geometry.notna() & water.is_valid]
    minx, miny, maxx, maxy = city_poly.buffer(2000).bounds
    water = water.cx[minx:maxx, miny:maxy]
    water_u = unary_union(list(water.geometry))
    # Puget Sound ONLY (largest waterbody near the city) — same robust pick as make_sectors.py
    w_area = water.geometry.area.sort_values(ascending=False)
    sound = water.loc[w_area.index[0]].geometry
    assert float(w_area.iloc[0]) > 25 * float(w_area.iloc[1]), "Puget Sound pick ambiguous"
    sound_shore = sound.boundary

    names, lut = group_lut()
    spine_p, second_p = ccap_path(CCAP_SPINE), ccap_path(CCAP_SECOND)
    assert spine_p, f"no C-CAP spine raster found ({CCAP_SPINE})"
    print(f"stratum spine (2016 epoch): {spine_p}")
    print(f"second epoch (2021, stable core only): {second_p or 'NOT FOUND'}")

    # ── per-sector context, computed ONCE and reused by every arm ────────────────────────
    ctx = {}
    with ExitStack() as st:
        vrts = {}
        for key, p in (("g16", spine_p), ("g21", second_p)):
            if p is None:
                continue
            src = st.enter_context(rasterio.open(p))
            vrts[key] = st.enter_context(WarpedVRT(
                src, crs=CRS, transform=cov_tf, width=cov_w, height=cov_h,
                resampling=Resampling.nearest, src_nodata=0, nodata=0))
        for _, srow in sectors.iterrows():
            sid = srow["id"]
            geom = srow.geometry
            win = rasterio.windows.from_bounds(*geom.bounds, transform=cov_tf
                                               ).round_offsets().round_lengths()
            c0, r0 = max(0, int(win.col_off)), max(0, int(win.row_off))
            c1 = min(cov_w, int(win.col_off + win.width))
            r1 = min(cov_h, int(win.row_off + win.height))
            win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
            wtf = rasterio.windows.transform(win, cov_tf)
            shape = (int(win.height), int(win.width))

            land_poly = geom.intersection(city_poly).difference(water_u)
            land = rasterio.features.rasterize(
                [(land_poly, 1)], out_shape=shape, transform=wtf, fill=0,
                dtype="uint8").astype(bool)

            raw16 = vrts["g16"].read(1, window=win)
            g16 = lut[raw16]
            if "g21" in vrts:
                raw21 = vrts["g21"].read(1, window=win)
                g21, has21 = lut[raw21], raw21 != 0
            else:
                g21, has21 = None, np.zeros(shape, bool)
            two_epoch = bool(has21[land].mean() > 0.01) if land.any() else False

            # E-W bins by anchor-lattice block-column. NOTE wtf.c, not tb[0]: these are WINDOW
            # columns, and only the westernmost sector's window starts at the grid origin.
            xs = wtf.c + np.arange(shape[1]) + 0.5
            bc = np.floor((xs - ORIGIN_X) / BLOCK_M).astype(np.int64)
            wc, ec = int(aoi_sec[sid]["west_col"]), int(aoi_sec[sid]["east_col"])
            n_cols = ec - wc
            edges = [wc + int(np.floor(k * n_cols / N_EW_BINS)) for k in range(N_EW_BINS + 1)]
            edges[-1] = ec
            ew = np.clip(np.searchsorted(np.array(edges[1:-1]), bc, side="right"),
                         0, N_EW_BINS - 1).astype(np.int8)
            ew_row = np.broadcast_to(ew, shape)
            ymid = (geom.bounds[1] + geom.bounds[3]) / 2
            bin_meta = []
            for k in range(N_EW_BINS):
                xlo = ORIGIN_X + edges[k] * BLOCK_M
                xhi = ORIGIN_X + edges[k + 1] * BLOCK_M
                d = Point((xlo + xhi) / 2, ymid).distance(sound_shore) * COS_LAT
                bin_meta.append({"block_col_lo": edges[k], "block_col_hi": edges[k + 1],
                                 "x_lo_3857": round(xlo, 3), "x_hi_3857": round(xhi, 3),
                                 "dist_sound_m_mid": round(d, 1)})

            land_by_g = {names[gi]: int((land & (g16 == gi)).sum())
                         for gi in np.unique(g16[land])} if land.any() else {}
            ctx[sid] = {"win": win, "land": land, "g16": g16, "g21": g21, "has21": has21,
                        "two_epoch": two_epoch, "ew": ew_row, "bins": bin_meta,
                        "edges": edges, "land_n": int(land.sum()), "land_by_g": land_by_g,
                        "land_by_bin": {k: int((land & (ew_row == k)).sum())
                                        for k in range(N_EW_BINS)}}
            print(f"  {sid}: window {shape[1]}x{shape[0]} px; land {ctx[sid]['land_n']:,} cells; "
                  f"2021 epoch {'yes' if two_epoch else 'NO (single-epoch sector)'}; "
                  f"ew edges(block-col) {edges}")

    # ── arms ─────────────────────────────────────────────────────────────────────────────
    files = sorted(COV1M.glob("cover_1m_*.tif"))
    arms = [(parse_arm(p), p) for p in files]
    arms = [(k, p) for k, p in arms if k]
    if a.arms:
        want = {tuple(s.split(":", 1)) if ":" in s else (s, "") for s in a.arms}
        arms = [(k, p) for k, p in arms if k in want]
        missing = want - {k for k, _ in arms}
        if missing:
            raise SystemExit(f"no cover1m sidecar for {sorted(missing)}")
    print(f"{len(arms)} arm(s): " + ", ".join(f"{y}/{t or '-'}" for (y, t), _ in arms))

    ref = series_p_raw()
    strat_rows, bin_rows, checks, reg_rows = [], [], [], []
    n_reg = {"ok": 0, "shifted": 0, "empty": 0}
    for (year, tag), cpath in arms:
        with rasterio.open(cpath) as ds:
            assert (ds.width, ds.height) == (cov_w, cov_h) and \
                np.allclose(np.asarray(ds.transform)[:6], np.asarray(cov_tf)[:6]), (
                    f"{cpath.name} is not on the sector 1-m grid "
                    f"({ds.width}x{ds.height} @ {ds.transform} vs {cov_w}x{cov_h} @ {cov_tf})")
            for sid in sorted(ctx):
                c = ctx[sid]
                cov = ds.read(1, window=c["win"])
                # REGISTRATION GUARD — see the module docstring. Test the raw footprint against
                # the land raster BEFORE the land mask is applied (masking hides the shift).
                reg = check_registration(cov >= 0, c["land"], a.reg_tol_m)
                reg_rows.append({"year": year, "tag": tag, "sector": sid,
                                 "registration_ok": reg["ok"], "reg_status": reg["status"],
                                 "dW_m": reg["dW"], "dE_m": reg["dE"], "dN_m": reg["dN"],
                                 "dS_m": reg["dS"], "land_covered_frac": reg["cov_frac"],
                                 "land_cells": c["land_n"], "sidecar": cpath.name})
                if not reg["ok"]:
                    n_reg[reg["status"]] += 1
                    print(f"    ! {year}/{tag or '-'} {sid}: registration {reg['status'].upper()} "
                          f"(dW={reg['dW']} dN={reg['dN']} dE={reg['dE']} dS={reg['dS']} m; "
                          f"land covered {reg['cov_frac']:.0%})"
                          + ("" if a.allow_misregistered else " — rows SKIPPED"))
                    if not a.allow_misregistered:
                        continue
                else:
                    n_reg["ok"] += 1
                valid = (cov >= 0) & c["land"]
                n_valid = int(valid.sum())
                if n_valid == 0:
                    continue
                sec_mean = float(cov[valid].mean())
                # post-stratified sector estimate: FIXED (2016-epoch) stratum weights from the
                # land raster, renormalised over the strata this arm actually observed.
                num = den = 0.0
                per_g = {}
                for gi in np.unique(c["g16"][valid]):
                    g = names[gi]
                    m = valid & (c["g16"] == gi)
                    n, mean = _mean(cov, m)
                    per_g[g] = (n, mean, m)
                    if mean != "" and n >= a.min_cells:
                        w = c["land_by_g"].get(g, 0)
                        num += w * mean
                        den += w
                p_ps = round(num / den, 5) if den else ""
                for g, (n, mean, m) in sorted(per_g.items()):
                    if c["two_epoch"] and c["g21"] is not None:
                        stable = m & c["has21"] & (c["g21"] == c["g16"])
                        ns, ms = _mean(cov, stable)
                        stable_frac = round(ns / n, 4) if n else ""
                    else:
                        ns, ms, stable_frac = "", "", ""
                    strat_rows.append({
                        "year": year, "tag": tag, "sector": sid, "ccap_group": g,
                        "n_cells": n,
                        "mean_cover": mean if (mean != "" and n >= a.min_cells) else "",
                        "land_cells": c["land_by_g"].get(g, 0),
                        "w_ref": round(c["land_by_g"].get(g, 0) / c["land_n"], 5)
                                 if c["land_n"] else "",
                        "cover_frac_of_stratum": round(n / c["land_by_g"][g], 4)
                                                 if c["land_by_g"].get(g) else "",
                        "n_cells_stable": ns,
                        "mean_cover_stable": ms if (ms != "" and ns != "" and ns >= a.min_cells)
                                             else "",
                        "stable_frac": stable_frac,
                        "single_epoch": 0 if c["two_epoch"] else 1,
                        "sector_land_cells": c["land_n"], "sector_valid_cells": n_valid,
                        "sector_mean_cover": round(sec_mean, 5),
                        "sector_p_poststrat": p_ps,
                        "ccap_spine": spine_p.name,
                        "ccap_second": (second_p.name if (second_p and c["two_epoch"]) else ""),
                        "registration_ok": reg["ok"], "reg_status": reg["status"],
                        "reg_dW_m": reg["dW"], "reg_dN_m": reg["dN"],
                    })
                for k in range(N_EW_BINS):
                    m = valid & (c["ew"] == k)
                    n, mean = _mean(cov, m)
                    row = {"year": year, "tag": tag, "sector": sid, "ew_bin": k}
                    row.update(c["bins"][k])
                    row.update({"n_cells": n,
                                "mean_cover": mean if (mean != "" and n >= a.min_cells) else "",
                                "land_cells": c["land_by_bin"][k],
                                "cover_frac_of_bin": round(n / c["land_by_bin"][k], 4)
                                                     if c["land_by_bin"][k] else "",
                                "sector_mean_cover": round(sec_mean, 5),
                                "registration_ok": reg["ok"], "reg_status": reg["status"],
                                "reg_dW_m": reg["dW"], "reg_dN_m": reg["dN"]})
                    bin_rows.append(row)
                # free consistency check against the shipped series (same thresholded quantity)
                p_raw = ref.get((year, tag), {}).get(sid)
                if p_raw is not None:
                    checks.append((year, tag, sid, p_raw, sec_mean, sec_mean - p_raw))
        print(f"  {year}/{tag or '-'}: {cpath.name}")

    hdr_common = [
        f"# generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by "
        f"qc/phase4_sector_poststrat.py ({ver}, covariates_updated="
        f"{aoi.get('covariates_updated', 'UNSTAMPED')})",
        "# read with pandas.read_csv(path, comment='#')",
        "# ZERO new inference: 1-m cover sidecars from qc/phase4_sector_series.py, thresholded at "
        "each arm's DEPLOYED threshold.",
        "# CAVEAT: those thresholds are chosen CITYWIDE, so per-stratum/per-bin LEVELS inherit the "
        "citywide operating point —",
        "#   comparable across strata within an arm and across years within a stratum, but NOT "
        "calibrated per stratum. No",
        "#   precision/recall adjustment is applied here (the live qc_indep row's p/r are citywide, "
        "not per stratum).",
        "# mean_* blank = fewer than the --min-cells threshold of valid cells.",
        "# REGISTRATION GUARD: every (arm, sector) is checked against the rasterised land polygon; "
        "sectors whose cover",
        "#   sidecar is translated (the qc/phase4_sector_series.py destination-clamp defect, "
        "2026-08-26) are SKIPPED unless",
        "#   --allow-misregistered. registration_ok / reg_status / reg_dW_m / reg_dN_m record the "
        "verdict on every row.",
    ]
    hdr_strat = hdr_common + [
        f"# STRATA COME FROM A FIXED EPOCH ({spine_p.name}, 2016) so real land-cover change is "
        "never absorbed into stratum",
        "#   MEMBERSHIP — a cell developed in 2019 is still scored inside its 2016 stratum.",
        f"# class->group map: qc/phase4_qc_indep.CCAP_DEFAULT (NOT make_sectors.CCAP_GROUPS — the "
        "aoi json's ccap_* fractions",
        "#   use a coarser, different grouping and will not match these).",
        "# stable core = cells where the 2016 and 2021 epochs agree at GROUP level (class churn "
        "inside a group is not an",
        "#   eviction). 2021 does not reach S1/S2 -> single_epoch=1 and EMPTY (not zero) stable "
        "columns.",
        "# w_ref = fixed stratum weight from the sector's rasterised LAND polygon (year-independent); "
        "sector_p_poststrat =",
        "#   sum(w_ref*mean_cover) renormalised over the strata this arm observed.",
    ]
    hdr_bins = hdr_common + [
        "# ew_bin 0=west(shoreward) .. 3=east(upland). Edges are anchor-lattice BLOCK-COLUMNS "
        "(152.874 m each):",
        f"#   west_col + floor(k*(east_col-west_col)/{N_EW_BINS}) for k=0..{N_EW_BINS}, per "
        f"sector, from pipeline/aoi/{ver}.json.",
        "#   Cells in the westward water-extension (block-col < west_col) fall in bin 0.",
        "# dist_sound_m_mid = true-ground distance from the bin centre to the PUGET SOUND polygon "
        "(the corrected covariate;",
        "#   the json's dist_shore_m is any-waterbody distance and is kept only for back-compat).",
    ]
    hdr_reg = hdr_common[:2] + [
        "# The cover1m sidecar registration audit: valid-footprint edges vs the rasterised sector "
        "land polygon, per (arm, sector).",
        "# d*_m = valid-footprint edge minus land edge, metres. reg_status: ok | shifted (the "
        "qc/phase4_sector_series.py",
        "#   destination-clamp defect translates the plane east/south) | empty (the strip was "
        "displaced out of the sector).",
        f"# Tolerance: |dW| and |dN| <= {a.reg_tol_m} m. Rows with registration_ok=0 were NOT used "
        "for the poststrat/gradient tables.",
    ]
    CAMP.mkdir(parents=True, exist_ok=True)
    for name, rows, hdr in (("sector_poststrat.csv", strat_rows, hdr_strat),
                            ("sector_gradient_bins.csv", bin_rows, hdr_bins),
                            ("sector_cover1m_registration.csv", reg_rows, hdr_reg)):
        if not rows:
            print(f"!! {name}: no rows — not written")
            continue
        with open(CAMP / name, "w", newline="", encoding="utf-8") as f:
            for line in hdr:
                f.write(line + "\n")
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"-> {CAMP / name} ({len(rows)} rows)")

    print(f"registration: {n_reg['ok']} sector-arms OK, {n_reg['shifted']} SHIFTED, "
          f"{n_reg['empty']} EMPTY"
          + (" (misregistered rows WRITTEN and flagged)" if a.allow_misregistered
             else " (misregistered rows skipped)"))
    if checks:
        d = [abs(x[5]) for x in checks]
        print(f"consistency vs sector_canopy_series p_raw: n={len(checks)} "
              f"max|delta|={max(d):.4f} mean|delta|={float(np.mean(d)):.4f}")
        for y, t, sid, pr, sm, dd in sorted(checks, key=lambda r: -abs(r[5]))[:5]:
            print(f"    {y}/{t or '-'} {sid}: series p_raw {pr:.4f} vs cover1m mean {sm:.4f} "
                  f"({dd:+.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
