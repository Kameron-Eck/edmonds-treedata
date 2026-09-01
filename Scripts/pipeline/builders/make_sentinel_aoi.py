r"""Sentinel-window AOI — the inference footprint that makes the golden gate scorable
on EVERY frozen window (E07 v2, 2026-08-26).

WHY. The golden gate (`qc/phase4_golden_gate.py`) scores the 12 frozen sentinel windows
in `Scripts/sentinel_sites.json`. Sector-restricted arms (`--infer-aoi aoi/sectors_v1.json`)
only intersect ~1 of those 12 windows, so the five grass / impervious / water NEGATIVES —
the ones that watch FP regression — are unscorable for every sector arm. This AOI is the
union of the 12 windows, so an INFERENCE-ONLY re-run under a new run tag gives an existing
checkpoint full 12-window golden coverage for a few GPU-minutes.

SCHEMA. Deliberately the schema `phase4seg/core.py::_aoi_pixel_rects` already consumes:
`{"crs": ..., "sectors": [{"bounds_3857": [minx, miny, maxx, maxy]}, ...]}`. The engine
reads ONLY `crs` and each entry's `bounds_3857`; every other key here is documentation.
"sectors" is the engine's word for "rects" — these are windows, not sectors.

GEOMETRY. Window bounds come from `pipeline/phase4_sentinel_snap.py::site_bounds` — IMPORTED,
never re-implemented, so the AOI cannot drift from what the gate actually scores when a
window is edited. Each window is padded by PAD_M in TRUE metres (WGS84 dlat/dlon
expansion, the same idiom site_bounds uses for its lon/lat/radius entries) to absorb
write-crop overhang at the rect edges. Note that a raw +30 in EPSG:3857 units would be
only ~20 ground metres at this latitude (1/cos(47.8) ≈ 1.49), which is why the pad is
applied before the projection, not after.

OVERLAP. Two window pairs genuinely overlap: forest_4 sits inside the 400 m marsh_deciduous
disc (17.3 ha shared) and marsh_deciduous clips neg_cemetery (1.4 ha). The rects are left
SEPARATE rather than dissolved: the engine writes identical values to a doubly-covered
pixel, and one rect per named window keeps the file traceable back to sentinel_sites.json
— which is also how the gate reports, one row per window.

FREEZE. The windows are frozen for cross-run comparability, so this script REFUSES to
overwrite an existing sentinel_v1.json whose bounds differ (pass --force when a window
edit is deliberate — and expect it to break comparability for that window).

USAGE
  py -3.12 pipeline/make_sentinel_aoi.py            # write pipeline/aoi/sentinel_v1.json
  py -3.12 pipeline/make_sentinel_aoi.py --check    # verify only, never write
"""
import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows

SCRIPTS = Path(__file__).resolve().parents[2]   # builders/ -> pipeline/ -> Scripts/
import phase4_sentinel_snap as SNAP                 # noqa: E402  window/bounds helpers

OUT = Path(__file__).resolve().parent.parent / "aoi" / "sentinel_v1.json"
VERSION = "sentinel_v1"
PAD_M = 30.0                    # true metres of write-crop overhang tolerance
M_PER_DEG_LAT = 111320.0        # the constant SNAP.site_bounds uses — kept identical

# A representative full-extent ortho for the "% of grid" report. The engine prints the
# real number per year at run time; this one just gives the order of magnitude locally.
REF_ORTHO = "2016_snoh_1ft_rgbi.tif"


def padded_bounds_3857(site, pad_m=PAD_M):
    """(id, [minx, miny, maxx, maxy] EPSG:3857) for one sentinel site, padded pad_m TRUE m."""
    w, s, e, n = SNAP.site_bounds(site)
    lat_c = 0.5 * (s + n)
    dlat = pad_m / M_PER_DEG_LAT
    dlon = pad_m / (M_PER_DEG_LAT * float(np.cos(np.radians(lat_c))))
    b = rasterio.warp.transform_bounds("EPSG:4326", "EPSG:3857",
                                       w - dlon, s - dlat, e + dlon, n + dlat)
    return site["name"], [round(v, 3) for v in b], lat_c


def true_area_m2(bounds_3857, lat_c):
    """EPSG:3857 rect area -> ground m^2 (Mercator scale is 1/cos(lat) per axis)."""
    minx, miny, maxx, maxy = bounds_3857
    k = float(np.cos(np.radians(lat_c)))
    return (maxx - minx) * k * (maxy - miny) * k


def build():
    sites = json.loads(SNAP.SITES_JSON.read_text(encoding="utf-8"))["sites"]
    rects, areas = [], []
    for site in sites:
        sid, b, lat_c = padded_bounds_3857(site)
        a = true_area_m2(b, lat_c)
        areas.append(a)
        rects.append({
            "id": sid,
            "bounds_3857": b,
            "why": site.get("why", ""),
            "pad_m_true": PAD_M,
            "area_m2_true": round(a, 1),
        })
    return sites, rects, areas


def _git_sha():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(SCRIPTS),
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or "unknown"
    except Exception:                                            # noqa: BLE001
        return "unknown"


def pixel_rects(rects, ortho):
    """Replica of phase4seg/core.py::_aoi_pixel_rects — the same transform + clamp, run
    locally against a real ortho so a CRS or clamp bug surfaces here, not on the GPU."""
    with rasterio.open(ortho) as src:
        img_h, img_w, img_crs, img_tf = src.height, src.width, src.crs, src.transform
    out = []
    for r in rects:
        minx, miny, maxx, maxy = r["bounds_3857"]
        bx = rasterio.warp.transform_bounds("EPSG:3857", img_crs, minx, miny, maxx, maxy)
        win = rasterio.windows.from_bounds(*bx, transform=img_tf)
        r0 = max(0, int(np.floor(win.row_off)))
        c0 = max(0, int(np.floor(win.col_off)))
        r1 = min(img_h, int(np.ceil(win.row_off + win.height)))
        c1 = min(img_w, int(np.ceil(win.col_off + win.width)))
        out.append((r["id"], r0, r1, c0, c1))
    return out, img_h, img_w


def report(rects, areas):
    tot = sum(areas)
    print(f"\n  {len(rects)} windows, +{PAD_M:.0f} m true pad each")
    for r in rects:
        print(f"    {r['id']:20s} {r['area_m2_true']/1e4:7.2f} ha")
    print(f"  {'TOTAL (sum of rects)':20s} {tot/1e4:7.2f} ha  ({tot:,.0f} m² true)")
    try:
        import itertools
        from shapely.geometry import box
        from shapely.ops import unary_union
        boxes = {r["id"]: box(*r["bounds_3857"]) for r in rects}
        k = float(np.cos(np.radians(47.81))) ** 2      # single-lat scale, as make_sectors
        u = unary_union(list(boxes.values()))
        print(f"  {'TOTAL (dissolved)':20s} {u.area*k/1e4:7.2f} ha  "
              f"(unique ground; single-lat scale)")
        for a, b in itertools.combinations(rects, 2):
            ia = boxes[a["id"]].intersection(boxes[b["id"]]).area * k
            if ia > 0:
                print(f"    overlap: {a['id']} ∩ {b['id']} = {ia/1e4:.2f} ha "
                      f"(harmless — identical values written twice)")
    except ImportError:
        print("  (shapely unavailable — dissolved area not computed)")

    ortho = None
    for d in SNAP.IMAGERY_DIRS:
        if (d / REF_ORTHO).exists():
            ortho = d / REF_ORTHO
            break
    if ortho is None:
        print(f"  ! {REF_ORTHO} not found locally — grid % not computed")
        return
    prs, img_h, img_w = pixel_rects(rects, ortho)
    bad = [i for i, r0, r1, c0, c1 in prs if not (r1 > r0 and c1 > c0)]
    px = sum((r1 - r0) * (c1 - c0) for _, r0, r1, c0, c1 in prs if r1 > r0 and c1 > c0)
    print(f"\n  vs {ortho.name} ({img_w}×{img_h} px, {img_w*img_h:,} px):")
    print(f"    {len(prs) - len(bad)}/{len(prs)} rects non-degenerate and on-grid; "
          f"{px:,} px = {100*px/(img_h*img_w):.3f}% of the grid")
    if bad:
        print(f"    ! DEGENERATE/OFF-GRID: {bad}")
    pct = 100 * px / (img_h * img_w)
    print(f"    sectors_v1 covers ~10% of the same grid, so sentinel_v1 inference is "
          f"~{10/pct:.1f}× cheaper than a sector arm")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="Compute + report only; never write.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing sentinel_v1.json whose bounds differ "
                         "(breaks cross-run comparability for the moved window).")
    # Colab injects `-f <kernel.json>`: strip THE PAIR, never every .json-suffixed value
    # (the any-.json filter silently ate --infer-aoi's value; fixed 2026-08-25).
    filtered, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
        elif a == "-f":
            skip = True
        else:
            filtered.append(a)
    args = ap.parse_args(filtered)

    sites, rects, areas = build()
    print(f"[sentinel-aoi] {len(sites)} frozen windows from {SNAP.SITES_JSON}")
    report(rects, areas)

    doc = {
        "version": VERSION,
        "crs": "EPSG:3857",
        "_doc": (
            "UNION of the 12 frozen sentinel windows (Scripts/sentinel_sites.json), each "
            "padded +30 m TRUE metres, as EPSG:3857 rects. Written for INFERENCE-ONLY "
            "re-runs (--infer-aoi) so qc/phase4_golden_gate.py can score all 12 windows "
            "for an arm whose citywide/sector prob raster does not cover them. The engine "
            "(phase4seg/core.py::_aoi_pixel_rects) reads ONLY 'crs' and each entry's "
            "'bounds_3857'; 'sectors' is the engine's key name, not a claim that these are "
            "sectors. Rects are NOT dissolved — forest_4 lies inside the marsh_deciduous "
            "disc and marsh_deciduous clips neg_cemetery; the engine writes identical "
            "values to the doubly-covered pixels, which is harmless, and one rect per "
            "named window keeps the file traceable to sentinel_sites.json."
        ),
        "params": {"pad_m_true": PAD_M, "n_windows": len(rects),
                   "source": "Scripts/sentinel_sites.json",
                   "bounds_fn": "pipeline/phase4_sentinel_snap.py::site_bounds (imported)"},
        "generated": {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                      "git": _git_sha(), "script": "pipeline/make_sentinel_aoi.py"},
        "sectors": rects,
    }

    if args.check:
        print("\n  --check: nothing written")
        return 0

    if OUT.exists() and not args.force:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        old_b = {s["id"]: s["bounds_3857"] for s in old.get("sectors", [])}
        new_b = {s["id"]: s["bounds_3857"] for s in rects}
        if old_b != new_b:
            print(f"\n  REFUSED: {OUT.name} exists with DIFFERENT bounds — the sentinel "
                  f"windows are frozen for cross-run comparability. Pass --force only if "
                  f"the window edit is deliberate.")
            return 1
        print(f"\n  bounds unchanged — refreshing metadata in {OUT.name}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"\n  wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
