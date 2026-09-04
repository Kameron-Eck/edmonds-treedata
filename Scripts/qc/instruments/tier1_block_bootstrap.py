"""Per-block histograms + paired-blocks bootstrap CI on the Tier-1 primary
statistic (recall@precision>=0.75, test blocks) — the reviewer's must-do #2.

For each scored t1 arm: window-read the prob raster over each TEST block,
accumulate per-block 256-bin histograms (ref-canopy / valid non-canopy px,
same mapping as phase4_qc_indep: forest_wetland primary definition, nearest-
resampled C-CAP reference on the prob grid, pr==255 invalid). Bootstrap:
resample the blocks with replacement (B=10000), recompute the exact curve
from summed histograms, read the statistic. Paired deltas vs the year's base
use the SAME resample indices (blocks are the pairing unit).

Outputs (repo, tracked measured text):
  phase4/qc/tier1_block_hists.npz         raw per-(arm, block) histograms
  phase4/qc/tier1_bootstrap_ci.csv        per-arm CI + paired-delta CI vs base
"""
import csv
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(SCRIPTS / "qc"))  # import the scorer's mapping helpers
import phase4_qc_indep as qci  # noqa: E402

BASE = Path(r"G:\My Drive\treedata")
MASKS = BASE / "phase4" / "masks"
REF = Path(r"D:\edmonds-pipeline\Imagery\ccap_2021_hires_lc.tif")
MAN = SCRIPTS.parent / "phase4" / "qc" / "science_sample_manifest.csv"
OUT_DIR = SCRIPTS.parent / "phase4" / "qc"
PREC_FLOOR = 0.75
B = 10_000
SEED = 20260903


def block_hists(prob_path, geoms, aoi_epsg):
    import rasterio
    import rasterio.features as rf
    import rasterio.warp
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.windows import Window, from_bounds

    names, canopy_order, grass_group, code_to_group = qci.load_ref_map("ccap", None)
    ignore_id = names.index("ignore")
    lut = qci.build_lut(names, code_to_group)
    defs = qci.canopy_definitions(canopy_order)
    primary_groups = defs[1][1] if len(defs) >= 2 else defs[0][1]

    hc = np.zeros((len(geoms), 256), dtype=np.int64)
    hn = np.zeros((len(geoms), 256), dtype=np.int64)
    with rasterio.open(prob_path) as prob, rasterio.open(REF) as ref_src:
        ref_nodata = ref_src.nodata
        with WarpedVRT(ref_src, crs=prob.crs, transform=prob.transform,
                       width=prob.width, height=prob.height,
                       resampling=Resampling.nearest) as ref_vrt:
            prim_ids = [names.index(g) for g in primary_groups]
            for i, g in enumerate(geoms):
                gw = rasterio.warp.transform_geom(f"EPSG:{aoi_epsg}", prob.crs, g)
                xs = [p[0] for p in gw["coordinates"][0]]
                ys = [p[1] for p in gw["coordinates"][0]]
                win = from_bounds(min(xs), min(ys), max(xs), max(ys),
                                  prob.transform).round_offsets().round_lengths()
                win = win.intersection(Window(0, 0, prob.width, prob.height))
                if win.width <= 0 or win.height <= 0:
                    continue
                pr = prob.read(1, window=win)
                rc = ref_vrt.read(1, window=win)
                codes = np.clip(rc.astype(np.int64), 0, 255)
                gid = lut[codes]
                if ref_nodata is not None:
                    gid[rc == ref_nodata] = ignore_id
                valid = (gid != ignore_id) & (pr != 255)
                wtf = rasterio.windows.transform(win, prob.transform)
                inaoi = rf.rasterize([(gw, 1)], out_shape=pr.shape, transform=wtf,
                                     fill=0, dtype="uint8").astype(bool)
                valid &= inaoi
                prim = valid & np.isin(gid, prim_ids)
                hc[i] += np.bincount(pr[prim], minlength=256)[:256]
                hn[i] += np.bincount(pr[valid & ~prim], minlength=256)[:256]
    return hc, hn


def stat_from_hists(hc, hn):
    """recall@precision>=PREC_FLOOR over integer cuts 1..254 (vectorized)."""
    # tp(k) = sum hc[k:255]; exclude 255 (invalid by construction, but safe)
    c = hc[:255].astype(np.float64)
    n = hn[:255].astype(np.float64)
    tp = np.cumsum(c[::-1])[::-1]   # tp[k] = sum c[k:]
    fp = np.cumsum(n[::-1])[::-1]
    tot = c.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
        rec = np.where(tot > 0, tp / tot, 0.0)
    elig = prec[1:255] >= PREC_FLOOR
    return float(rec[1:255][elig].max()) if elig.any() else float("nan")


def main():
    geoms, epsg, nb = qci.load_aoi(str(MAN), ("test",))
    print(f"{nb} test blocks (EPSG:{epsg})")
    arms = {}
    for p in sorted(MASKS.glob("edmonds_canopy_prob_*_t1_*.tif")):
        import re
        m = re.search(r"prob_([0-9a-z]+)_(t1_.+)\.tif", p.name)
        if m:
            arms[(m.group(1), m.group(2))] = p
    store = {}
    for (year, tag), p in arms.items():
        print(f"histing {year} {tag} ...", flush=True)
        hc, hn = block_hists(p, geoms, epsg)
        store[f"{year}|{tag}|c"] = hc
        store[f"{year}|{tag}|n"] = hn
    np.savez_compressed(OUT_DIR / "tier1_block_hists.npz", **store)

    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, nb, size=(B, nb))
    rows = []
    keys = sorted({k.rsplit("|", 1)[0] for k in store})
    boots = {}
    for k in keys:
        hc, hn = store[k + "|c"], store[k + "|n"]
        point = stat_from_hists(hc.sum(0), hn.sum(0))
        bs = np.array([stat_from_hists(hc[ix].sum(0), hn[ix].sum(0)) for ix in idx])
        boots[k] = bs
        lo, hi = np.nanpercentile(bs, [2.5, 97.5])
        rows.append({"year": k.split("|")[0], "tag": k.split("|")[1],
                     "recall_at_p75": round(point, 4),
                     "ci_lo": round(float(lo), 4), "ci_hi": round(float(hi), 4)})
        print(f"  {k}: {point:.4f} [{lo:.4f}, {hi:.4f}]", flush=True)
    for r in rows:
        bk = f"{r['year']}|t1_{r['year']}_base"
        k = f"{r['year']}|{r['tag']}"
        if bk in boots and k != bk:
            d = boots[k] - boots[bk]           # same resample indices: paired
            lo, hi = np.nanpercentile(d, [2.5, 97.5])
            r["delta_ci_lo"], r["delta_ci_hi"] = round(float(lo), 4), round(float(hi), 4)
            r["delta_sig"] = int(lo > 0 or hi < 0)
        else:
            r["delta_ci_lo"] = r["delta_ci_hi"] = r["delta_sig"] = ""
    cols = ["year","tag","recall_at_p75","ci_lo","ci_hi",
            "delta_ci_lo","delta_ci_hi","delta_sig"]
    with open(OUT_DIR / "tier1_bootstrap_ci.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    print(f"wrote {OUT_DIR / 'tier1_bootstrap_ci.csv'} ({len(rows)} arms)")


if __name__ == "__main__":
    main()
