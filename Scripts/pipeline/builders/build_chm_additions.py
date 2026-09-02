r"""build_chm_additions.py — epoch-specific lidar label-context additions (Tier 1).

Plan: TIER1_SCIENCE_SAMPLE_PLAN_2026-09-02.md; arms t1_*_add05 / t1_*_add16 in
experiments/tier1_science_sample.yaml. Precedent: phase4_build_corrected_labels.py
(NDVI+CHM additions, ADD-only, 2016 grid). This builder differs deliberately:

  - EPOCH-SPECIFIC CHMs: lidar_chm2005_2m.tif and lidar_chm2_2016_50cm.tif
    (both uint8, DN = 1 + round(clip(h,0,50.6)/0.2), 0 = nodata — the chm2
    encoding note in config.py; VERIFIED on both rasters before this was
    written, p50 ~3 m p99 ~39 m).
  - NO NDVI: must serve RGB years (2006s, 2011s). Credibility comes from
    height + the buildings layer instead of height + greenness.
  - BOTH DIRECTIONS via the ADD-ONLY code vocabulary (labels.apply_additions):
      code 3  IGNORE unconditionally — where the 2020 mask says CANOPY but the
              epoch's CHM says < LOW_H. The audit's central label defect:
              2020 labels assert trees that did not exist yet. Code 3 removes
              the assertion without ever teaching background (rule 3.6 holds).
      code 1  ADD canopy — where the 2020 mask says background, the CHM says
              >= HIGH_H, and no building sits within BLDG_BUF_M: a tree
              present in this epoch and gone by 2020.
      code 2  IGNORE-unless-canopy — same tall evidence but building-adjacent
              (roof edges, overhang ambiguity): suppress the background
              assertion, add nothing.
  - THE KILL-TEST is computed in-pass: per-code pixel counts citywide AND
    inside the science sample's train+selection regions ->
    phase4/qc/chm_label_contradictions.csv. Pre-registered rule
    (tier1_science_sample.yaml): an adder arm whose additions touch < 2% of
    labeled sample px is STRUCK before launch.

Outputs (lake): phase4/labels_corrected/add_chm{2005,2016}.tif (+ .lineage.json,
same sidecar pattern as the corruption overlays). The additions path is part of
the tile signature (path+size+mtime), so arms re-tile automatically when these
change. Zero GPU; window-streamed; ~minutes.
"""
import argparse
import datetime as _dt
import json
from pathlib import Path

import numpy as np

from phase4seg.deps import ensure_deps as _ensure_deps
_ensure_deps([("rasterio", "rasterio"), ("geopandas", "geopandas"),
              ("shapely", "shapely"), ("pandas", "pandas")])

import geopandas as gpd
import pandas as pd
import rasterio
import rasterio.features
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window

from lake import BASE

LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
CHMS = {
    "2005": (LOCAL_IMG / "lidar_chm2005_2m.tif",
             BASE / "Full_Image" / "Pipeline Imagery" / "lidar_chm2005_2m.tif"),
    "2016": (LOCAL_IMG / "lidar_chm2_2016_50cm.tif",
             BASE / "Full_Image" / "Pipeline Imagery" / "lidar_chm2_2016_50cm.tif"),
}
MASK2020 = BASE / "phase3" / "edmonds_canopy_mask_2020.tif"
BUILDINGS = BASE / "buildings" / "buildings_canonical.gpkg"
SAMPLE_CSV = BASE / "phase4" / "qc" / "science_sample_manifest.csv"
OUT_DIR = BASE / "phase4" / "labels_corrected"
KILL_CSV = BASE / "phase4" / "qc" / "chm_label_contradictions.csv"

LOW_H = 2.0        # m; 2020-canopy over less height than this -> code 3
HIGH_H = 4.0       # m; background under more height than this -> code 1/2
BLDG_BUF_M = 6.0   # same pull-back the lidar-background builder uses
BLOCK = 2048


def dn_to_h(dn):
    h = (dn.astype(np.float32) - 1.0) * 0.2
    h[dn == 0] = np.nan
    return h


def build_epoch(epoch, chm_path, bldg, sample_regions, dry_run):
    import tempfile
    final_tif = OUT_DIR / f"add_chm{epoch}.tif"
    out_tif = Path(tempfile.gettempdir()) / f"_add_chm{epoch}.tif"   # local-first (3.9)
    with rasterio.open(chm_path) as chm, rasterio.open(MASK2020) as m20:
        H, W = chm.height, chm.width
        prof = {"driver": "GTiff", "dtype": "uint8", "width": W, "height": H,
                "count": 1, "crs": chm.crs, "transform": chm.transform,
                "compress": "lzw", "nodata": 255}
        bldg_epoch = bldg.to_crs(chm.crs)
        # THE RING RULE (measured lesson, first dry-run: a plain 6 m buffer
        # swallowed 17.9% of sample labels as code 2 — including ROOF INTERIORS,
        # which are the classic hard negative and MUST stay background
        # supervision). chm2 is per-cell MAX of ALL returns (config chm2 note),
        # so roofs read tall: interiors are forced code 0; only the edge RING
        # (buffer minus footprint) is overhang-ambiguous.
        bldg_on = [(g, 1) for g in bldg_epoch.geometry]
        bldg_ring = [(g, 1) for g in bldg_epoch.geometry.buffer(BLDG_BUF_M)]
        regions = (sample_regions.to_crs(chm.crs)
                   if sample_regions is not None else None)
        reg_shapes = ([(g, 1) for g in regions.geometry]
                      if regions is not None else [])

        counts = {k: 0 for k in ("labeled", "c1", "c2", "c3",
                                 "s_labeled", "s_c1", "s_c2", "s_c3")}
        vrt = WarpedVRT(m20, crs=chm.crs, transform=chm.transform,
                        width=W, height=H, resampling=Resampling.mode,
                        src_nodata=255, nodata=255)
        with vrt, rasterio.open(out_tif, "w", **prof) as dst:
            for r0 in range(0, H, BLOCK):
                rows = min(BLOCK, H - r0)
                win = Window(0, r0, W, rows)
                wtf = rasterio.windows.transform(win, chm.transform)
                h = dn_to_h(chm.read(1, window=win))
                c20 = vrt.read(1, window=win)
                on_b = rasterio.features.rasterize(
                    bldg_on, out_shape=(rows, W), transform=wtf,
                    fill=0, dtype="uint8").astype(bool)
                ring = rasterio.features.rasterize(
                    bldg_ring, out_shape=(rows, W), transform=wtf,
                    fill=0, dtype="uint8").astype(bool) & ~on_b
                add = np.zeros((rows, W), np.uint8)
                valid = ~np.isnan(h)
                stale = valid & (c20 == 1) & (h < LOW_H)
                # CROWN-EDGE HALO GUARD (measured lesson, second dry-run: 8.2%
                # "adds" — cells straddling a crown edge read background in the
                # mode-resampled 2020 mask but tall in the max-return CHM, so
                # every crown grew a ring of false adds that would TEACH
                # dilation). Adds must clear a ~2 m dilation of existing canopy.
                from scipy.ndimage import binary_dilation
                halo_px = max(1, int(round(2.0 / abs(chm.transform.a))))
                c20_near = binary_dilation(c20 == 1, iterations=halo_px)
                tall_bg = valid & (c20 == 0) & ~c20_near & (h >= HIGH_H) & ~on_b
                add[stale] = 3
                add[tall_bg & ~ring] = 1
                add[tall_bg & ring] = 2
                add[~valid] = 255
                dst.write(add[np.newaxis], window=win)

                lab = valid & (c20 != 255)
                counts["labeled"] += int(lab.sum())
                for c, k in ((1, "c1"), (2, "c2"), (3, "c3")):
                    counts[k] += int((add == c).sum())
                if reg_shapes:
                    inreg = rasterio.features.rasterize(
                        reg_shapes, out_shape=(rows, W), transform=wtf,
                        fill=0, dtype="uint8").astype(bool)
                    counts["s_labeled"] += int((lab & inreg).sum())
                    for c, k in ((1, "s_c1"), (2, "s_c2"), (3, "s_c3")):
                        counts[k] += int(((add == c) & inreg).sum())

    lineage = dict(
        purpose=("EPOCH-SPECIFIC lidar label context (Tier 1). ADD-ONLY codes; "
                 "code 3 removes non-credible 2020-canopy assertions, never "
                 "asserts background."),
        epoch=epoch, chm=chm_path.name,
        chm_encoding="uint8 DN = 1 + round(clip(h,0,50.6)/0.2); 0 = nodata",
        chm_limitation=("per-cell MAX of ALL returns (building-inclusive) — "
                        "code 1 can admit UNMAPPED tall structures; roof "
                        "interiors are forced code 0 (ring rule) so hard "
                        "negatives keep background supervision"),
        mask2020=str(MASK2020.name), resampling="mode",
        rules=dict(code3=f"mask2020==1 & h<{LOW_H}m",
                   code1=f"mask2020==0 & h>={HIGH_H}m & outside building+{BLDG_BUF_M}m",
                   code2=f"mask2020==0 & h>={HIGH_H}m & in the {BLDG_BUF_M}m ring",
                   code0_forced="building interiors (roof = true background)"),
        counts=counts, built=_dt.datetime.now().isoformat(timespec="seconds"),
        builder="pipeline/builders/build_chm_additions.py")
    if dry_run:
        out_tif.unlink(missing_ok=True)
    else:
        import shutil
        shutil.copy2(out_tif, final_tif)
        if final_tif.stat().st_size != out_tif.stat().st_size:
            raise RuntimeError(f"size mismatch copying {final_tif.name}")
        out_tif.unlink(missing_ok=True)
        (OUT_DIR / f"add_chm{epoch}.lineage.json").write_text(
            json.dumps(lineage, indent=2), encoding="utf-8")
    tot = max(counts["labeled"], 1)
    stot = max(counts["s_labeled"], 1)
    print(f"[chm{epoch}] citywide: labeled {counts['labeled']:,} px | "
          f"add {100*counts['c1']/tot:.2f}% ignore {100*counts['c2']/tot:.2f}% "
          f"kill-stale {100*counts['c3']/tot:.2f}%")
    print(f"[chm{epoch}] sample  : labeled {counts['s_labeled']:,} px | "
          f"add {100*counts['s_c1']/stot:.2f}% ignore {100*counts['s_c2']/stot:.2f}% "
          f"kill-stale {100*counts['s_c3']/stot:.2f}%")
    return counts


def main():
    ap = argparse.ArgumentParser(description="Build epoch-specific CHM additions.")
    ap.add_argument("--epochs", nargs="+", default=["2005", "2016"])
    ap.add_argument("--dry-run", action="store_true",
                    help="compute counts, write no raster/lineage/CSV")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bldg = gpd.read_file(BUILDINGS, layer="buildings")
    print(f"buildings: {len(bldg):,} footprints")
    sample_regions = None
    if SAMPLE_CSV.exists():
        sm = pd.read_csv(SAMPLE_CSV)
        sm = sm[sm.role.isin(["train", "selection"])]
        from shapely.geometry import box as _box
        sample_regions = gpd.GeoDataFrame(
            sm, geometry=[_box(r.minx, r.miny, r.maxx, r.maxy)
                          for r in sm.itertuples()],
            crs=f"EPSG:{int(sm.epsg.iloc[0])}")
        print(f"sample regions: {len(sample_regions)} (train+selection)")
    else:
        print("WARNING: science_sample_manifest.csv not found — sample-scoped "
              "kill-test columns will be zero")

    rows = []
    for ep in args.epochs:
        chm = next((p for p in CHMS[ep] if p.exists()), None)
        if chm is None:
            raise FileNotFoundError(f"no CHM found for epoch {ep}")
        c = build_epoch(ep, chm, bldg, sample_regions, args.dry_run)
        tot, stot = max(c["labeled"], 1), max(c["s_labeled"], 1)
        rows.append(dict(
            epoch=ep, chm=chm.name,
            labeled_px=c["labeled"], add_pct=round(100 * c["c1"] / tot, 3),
            ignore_pct=round(100 * c["c2"] / tot, 3),
            kill_stale_pct=round(100 * c["c3"] / tot, 3),
            sample_labeled_px=c["s_labeled"],
            sample_add_pct=round(100 * c["s_c1"] / stot, 3),
            sample_ignore_pct=round(100 * c["s_c2"] / stot, 3),
            sample_kill_stale_pct=round(100 * c["s_c3"] / stot, 3),
            sample_touched_pct=round(
                100 * (c["s_c1"] + c["s_c2"] + c["s_c3"]) / stot, 3),
            low_h_m=LOW_H, high_h_m=HIGH_H, bldg_buf_m=BLDG_BUF_M,
            ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    if not args.dry_run:
        pd.DataFrame(rows).to_csv(KILL_CSV, index=False)
        print(f"wrote {KILL_CSV.name} — the pre-registered kill-test input "
              f"(arm struck if sample_touched_pct < 2)")


if __name__ == "__main__":
    main()
