r"""Dated-site evaluation scorer (2026-08-26).

WHAT. Scores every canopy-probability raster the project holds against Kam's
HAND-VERIFIED, DATED per-site labels in
    data:phase4/labels_sites/site_labels_timeseries.gpkg  (layer site_labels)
    columns: site, year_from, year_to, cls in {tree, background},
             src in {drawn, complement}, EPSG:3857
Two sites, five (site, interval) label states:
    Development          1996-1998 / 2000 / 2001 / 2002-2005   (clear-and-rebuild)
    Edmonds Heights K-12 1990-2025                             (30-year stable)

WHY THIS EXISTS. Every other honest number in the project is scored against a
2020-derived reference (NDVI+CHM, C-CAP 2016/2021, the 2020 mask). These are
nearly the ONLY hand-verified PRE-2015 labels in the project and nothing scored
against them. The Development parcel is the only DATED pre-anchor truth: it was
tree-covered through 1998 and cleared by 2000, so it is the one place a model's
pre-anchor behaviour can be checked against something other than 2020.

HONESTY RAILS (rule 5 - honest evaluation only)
  * EVAL GROUND, NEVER TRAINING. These labels are held out. If any future run
    trains on a site, that (year, arm) must be EXCLUDED for that site. The
    `trained_on` column is that discipline's home: it is emitted empty today
    because no run has trained on either site. When one does, add its
    (year_label, arm) -> "site;site" entry to TRAINED_ON below; the row then
    carries the contamination in the CSV instead of in someone's memory.
  * THRESHOLDS ARE NEVER INVENTED. The operating point comes ONLY from
    qc_indep_report.csv live=1 primary=1 (latest ts per (year, tag)) - the same
    live_rows() qc/phase4_sector_series.py uses. An arm with a prob raster but
    NO live row is REFUSED and listed, never scored at a guessed threshold.
  * COVERAGE IS MEASURED, NOT ASSUMED. A (site, acquisition, arm) whose labelled
    ground is under --min-valid (default 50%) prob-valid is SKIPPED and listed.
    Sector-restricted arms (tag *sectors_v1*) are footprint-limited by design:
    measured 2026-08-26, the labelled ground sits 7.1% inside sectors_v1 for
    Development (-> skipped) and 71.4% for the school (-> scored, but on a
    SPATIAL SUBSET; read frac_valid before quoting such a row).
  * NOTHING IS FABRICATED. Acquisitions inside an interval with no prob raster,
    and intervals with no acquisition at all, are listed as holes.

WHAT THE TWO SITES MEASURE
  * Edmonds Heights K-12 = the FALSE-POSITIVE CONTROL. Background is 96.9% of
    the labelled ground (158,591 of 163,593 m^2 in 3857) and the state is stable
    for 30 years, so fpr_bg should be LOW and FLAT across all 18 acquisitions.
    Any arm/year calling >5% of that background "tree" is flagged. Its five tree
    cut-outs are labelled tree rows and ARE scored as tree (n is small - see
    caveats).
  * Development = the DATED PRE-ANCHOR truth. Labelled tree fraction by pixel
    runs 79.7% (1996-1998) -> 19.0% (2000) -> 19.5% (2001) -> 16.3% (2002-2005).

INTERVAL MAPPING. A catalog acquisition scores against an interval iff its
CALENDAR year (the label's leading digits: 2019n -> 2019, 2002s -> 2002) is
INSIDE [year_from, year_to]. Strict - no nearest-neighbour stretching. Two
consequences, both real and both reported:
  * 1996-1998 has NO acquisition (the catalog starts at 2000), so the tree-heavy
    pre-clear state cannot be scored until pre-2000 imagery exists.
  * 2001-2001 has no acquisition either.
The measurable pre-anchor recall is therefore the POST-clear remnant/regrowth
(19% / 16% tree) on the 2000, 2002, 2003s and 2005 acquisitions.

OUTPUT
  data:phase4/qc/site_eval.csv  - regenerated wholesale (derived, not authored)
  + two printed tables: the school's FP rate per acquisition per arm, and
    Development's recall trajectory per interval.

RUN (local CPU, windowed boundless reads only):
  PYTHONUTF8=1 py -3.12 qc/phase4_site_eval.py
"""
import argparse
import csv
import datetime as dt
import math
import re
import sys
import warnings
from pathlib import Path

# rasterio's boundless read reshapes its output buffer in place; NumPy 2.5
# deprecates that. It is rasterio's line, not ours, and it fires once per block.
warnings.filterwarnings("ignore", message=".*Setting the shape on a NumPy array.*")

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "qc"))
sys.path.insert(0, str(SCRIPTS / "pipeline"))

from champion import load_champions, prob_arm            # noqa: E402,F401
from phase4_sector_series import live_rows               # noqa: E402

DATA = Path(r"G:\My Drive\treedata")
SITES_GPKG = DATA / "phase4" / "labels_sites" / "site_labels_timeseries.gpkg"
SITES_LAYER = "site_labels"
PROB_DIRS = [DATA / "phase4" / "masks", DATA / "phase3"]
OUT_CSV = DATA / "phase4" / "qc" / "site_eval.csv"

# The contamination register (see the EVAL GROUND rail above). Key = (year_label,
# arm tag as parsed from the prob filename, "" = untagged); value = ";"-joined
# site names that run TRAINED on. EMPTY TODAY - no run has trained on either
# site. Adding an entry does not silently drop the row: it stamps `trained_on`
# so the row is visibly disqualified for that site.
TRAINED_ON: dict[tuple[str, str], str] = {}

PROB_RE = re.compile(r"edmonds_canopy_prob_([0-9a-z]+?)(?:_(.+))?\.tif")
FP_FLAG = 0.05          # school background-called-tree rate that gets flagged
BLOCK_PX = 16_000_000   # max pixels held per windowed read


def cal_year(label):
    """Calendar year from a catalog label: '2019n' -> 2019, '2002s' -> 2002."""
    m = re.match(r"(\d{4})", str(label))
    return int(m.group(1)) if m else None


def prob_index():
    """{year_label: [(path, arm), ...]} over every prob raster on the lake.

    The filename regex is ANCHORED (fullmatch) so the '.tif.stub-*' sidecars do
    not enter, and the year token must match EXACTLY - a '2002*' glob otherwise
    swallows the separate 2002s acquisition.
    """
    idx, seen = {}, set()
    for d in PROB_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("edmonds_canopy_prob_*.tif")):
            m = PROB_RE.fullmatch(p.name)
            if not m:
                continue
            year, arm = m.group(1), (m.group(2) or "")
            if (year, arm) in seen:      # masks/ wins over phase3/
                continue
            seen.add((year, arm))
            idx.setdefault(year, []).append((p, arm))
    return idx


def window_of(bounds, ds, pad=1):
    """Unclipped integer window covering `bounds` (ds.crs) on ds's grid."""
    from rasterio.transform import rowcol
    minx, miny, maxx, maxy = bounds
    xs = [minx, minx, maxx, maxx]
    ys = [miny, maxy, miny, maxy]
    rows, cols = rowcol(ds.transform, xs, ys, op=float)
    r0 = int(math.floor(min(rows))) - pad
    r1 = int(math.ceil(max(rows))) + pad
    c0 = int(math.floor(min(cols))) - pad
    c1 = int(math.ceil(max(cols))) + pad
    return c0, r0, max(1, c1 - c0), max(1, r1 - r0)


def score(ds, tree_geom, bg_geom, thresh):
    """Confusion counts on the labelled ground of one prob raster.

    Reads BOUNDLESS with fill 255 so pixels outside the raster's own extent are
    counted as prob-INVALID rather than silently dropped - that keeps frac_valid
    honest for footprint-limited arms.
    """
    import numpy as np
    import rasterio
    from rasterio.features import rasterize
    from shapely.geometry import shape as shp

    tb = shp(tree_geom).bounds if tree_geom else None
    bb = shp(bg_geom).bounds if bg_geom else None
    bs = [b for b in (tb, bb) if b]
    bounds = (min(b[0] for b in bs), min(b[1] for b in bs),
              max(b[2] for b in bs), max(b[3] for b in bs))
    c0, r0, w, h = window_of(bounds, ds)
    thr_u8 = int(round(thresh * 254))
    blk = max(1, BLOCK_PX // max(1, w))

    tp = fn = fp = tn = 0
    n_tree = n_bg = n_conf = 0
    for i in range(0, h, blk):
        bh = min(blk, h - i)
        win = rasterio.windows.Window(c0, r0 + i, w, bh)
        arr = ds.read(1, window=win, boundless=True, fill_value=255)
        tf = ds.window_transform(win)
        tr = (rasterize([(tree_geom, 1)], out_shape=(bh, w), transform=tf,
                        fill=0, dtype="uint8").astype(bool)
              if tree_geom else np.zeros((bh, w), bool))
        bg = (rasterize([(bg_geom, 1)], out_shape=(bh, w), transform=tf,
                        fill=0, dtype="uint8").astype(bool)
              if bg_geom else np.zeros((bh, w), bool))
        conf = tr & bg
        if conf.any():
            n_conf += int(conf.sum())
            tr = tr & ~conf
            bg = bg & ~conf
        if not (tr.any() or bg.any()):
            continue
        n_tree += int(tr.sum())
        n_bg += int(bg.sum())
        valid = arr != 255
        pred = valid & (arr >= thr_u8)
        tp += int((tr & pred).sum())
        fn += int((tr & valid & ~pred).sum())
        fp += int((bg & pred).sum())
        tn += int((bg & valid & ~pred).sum())
    return dict(tp=tp, fn=fn, fp=fp, tn=tn, n_tree_lab=n_tree, n_bg_lab=n_bg,
                n_conflict=n_conf)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--min-valid", type=float, default=0.50,
                    help="minimum prob-valid fraction of labelled ground to score")
    ap.add_argument("--site", default="", help="score only sites containing this text")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    import geopandas as gpd
    from rasterio.warp import transform_geom
    from shapely.ops import unary_union
    import rasterio
    import imagery_measure as im
    from phase4seg.config import YEAR_CATALOG

    labels = gpd.read_file(SITES_GPKG, layer=SITES_LAYER)
    if labels.crs is None or labels.crs.to_epsg() != 3857:
        print(f"! labels CRS is {labels.crs} - reprojecting to EPSG:3857")
        labels = labels.to_crs("EPSG:3857")
    if a.site:
        labels = labels[labels["site"].str.contains(a.site, case=False)]

    live = live_rows()
    champ = load_champions()
    pidx = prob_index()
    catalog = [(e["label"], cal_year(e["label"])) for e in YEAR_CATALOG]
    catalog = [(l, y) for l, y in catalog if y]

    print(f"labels: {len(labels)} polygons, {SITES_GPKG}")
    print(f"catalog: {len(catalog)} acquisitions; prob rasters: "
          f"{sum(len(v) for v in pidx.values())} in {len(pidx)} year-labels; "
          f"live (year,tag) rows: {len(live)}")

    rows, refused, skipped, noprob, noacq = [], [], [], [], []
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    keys = sorted({(r["site"], int(r["year_from"]), int(r["year_to"]))
                   for _, r in labels.iterrows()},
                  key=lambda k: (k[0], k[1]))
    for site, yf, yt in keys:
        sel = labels[(labels["site"] == site) & (labels["year_from"] == yf)
                     & (labels["year_to"] == yt)]
        tg = list(sel[sel["cls"] == "tree"].geometry)
        bgg = list(sel[sel["cls"] == "background"].geometry)
        tree_u = unary_union(tg) if tg else None
        bg_u = unary_union(bgg) if bgg else None
        interval = f"{yf}-{yt}"
        acqs = [(l, y) for l, y in catalog if yf <= y <= yt]
        print(f"\n[{site} {interval}] tree {(tree_u.area if tree_u else 0)/1e4:.2f} ha3857 / "
              f"bg {(bg_u.area if bg_u else 0)/1e4:.2f} ha3857 ; "
              f"{len(acqs)} acquisition(s) inside the interval")
        if not acqs:
            noacq.append((site, interval))
            print("  ! NO ACQUISITION in this interval - nothing scoreable")
            continue
        for label, year in acqs:
            probs = pidx.get(label, [])
            if not probs:
                noprob.append((site, interval, label))
                continue
            for path, arm in probs:
                key = (label, arm)
                if key not in live:
                    refused.append((site, interval, label, arm or "-", path.name,
                                    "no live=1 primary=1 row in qc_indep_report.csv"))
                    continue
                lr = live[key]
                with rasterio.open(path) as ds:
                    if ds.dtypes[0] != "uint8":
                        refused.append((site, interval, label, arm or "-", path.name,
                                        f"prob dtype {ds.dtypes[0]} - uint8/255-nodata "
                                        f"convention does not apply"))
                        continue
                    tg_ = (transform_geom("EPSG:3857", ds.crs, tree_u.__geo_interface__)
                           if tree_u else None)
                    bg_ = (transform_geom("EPSG:3857", ds.crs, bg_u.__geo_interface__)
                           if bg_u else None)
                    c = score(ds, tg_, bg_, lr["thresh"])
                    gsd_cm = im.true_gsd_cm(ds)[0]
                    crs_txt = str(ds.crs)
                n_lab = c["n_tree_lab"] + c["n_bg_lab"]
                n_val = c["tp"] + c["fn"] + c["fp"] + c["tn"]
                frac = (n_val / n_lab) if n_lab else 0.0
                if frac < a.min_valid:
                    skipped.append((site, interval, label, arm or "-", frac))
                    print(f"  {label:6s}/{arm or '-':20s} SKIPPED - only "
                          f"{frac*100:.1f}% of the labelled ground is prob-valid")
                    continue
                rec = (c["tp"] / (c["tp"] + c["fn"])) if (c["tp"] + c["fn"]) else ""
                fpr = (c["fp"] / (c["fp"] + c["tn"])) if (c["fp"] + c["tn"]) else ""
                prec = (c["tp"] / (c["tp"] + c["fp"])) if (c["tp"] + c["fp"]) else ""
                is_ch = ("" if str(label) not in champ
                         else int(arm == champ[str(label)]))
                rows.append({
                    "site": site, "year_from": yf, "year_to": yt,
                    "interval": interval, "acq_label": label, "acq_year": year,
                    "arm": arm, "prob_file": path.name, "thresh": lr["thresh"],
                    "thresh_u8": int(round(lr["thresh"] * 254)),
                    "gsd_cm": round(gsd_cm, 2), "crs": crs_txt,
                    "tp": c["tp"], "fn": c["fn"], "fp": c["fp"], "tn": c["tn"],
                    "n_tree_px": c["tp"] + c["fn"], "n_bg_px": c["fp"] + c["tn"],
                    "n_labeled_px": n_lab, "n_conflict_px": c["n_conflict"],
                    "frac_valid": round(frac, 4),
                    "label_tree_frac": (round(c["n_tree_lab"] / n_lab, 4) if n_lab else ""),
                    "recall_tree": (round(rec, 4) if rec != "" else ""),
                    "fpr_bg": (round(fpr, 4) if fpr != "" else ""),
                    "precision_site": (round(prec, 4) if prec != "" else ""),
                    "is_champion": is_ch,
                    "trained_on": TRAINED_ON.get(key, ""),
                    "indep_ts": lr["ts"], "generated": stamp,
                })
                print(f"  {label:6s}/{arm or '-':20s} recall {rec if rec=='' else f'{rec:.3f}'}"
                      f"  fpr_bg {fpr if fpr=='' else f'{fpr:.4f}'}"
                      f"  valid {frac*100:5.1f}%  n_tree {c['tp']+c['fn']:>9,}"
                      f"  n_bg {c['fp']+c['tn']:>9,}  thr {lr['thresh']:.4f}")

    cols = ["site", "year_from", "year_to", "interval", "acq_label", "acq_year",
            "arm", "prob_file", "thresh", "thresh_u8", "gsd_cm", "crs",
            "tp", "fn", "fp", "tn", "n_tree_px", "n_bg_px", "n_labeled_px",
            "n_conflict_px", "frac_valid", "label_tree_frac", "recall_tree",
            "fpr_bg", "precision_site", "is_champion", "trained_on",
            "indep_ts", "generated"]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {out} ({len(rows)} rows)")

    # ---- TABLE 1: the school = false-positive control -----------------------
    sch = [r for r in rows if r["site"].startswith("Edmonds Heights")]
    sch.sort(key=lambda r: (r["acq_year"], r["acq_label"], r["arm"]))
    print("\n" + "=" * 100)
    print("TABLE 1  Edmonds Heights K-12 (1990-2025, stable) - FALSE-POSITIVE CONTROL")
    print("  background = 96.9% of the labelled ground; fpr_bg should be LOW and FLAT.")
    print(f"  FLAG = background called tree at >{FP_FLAG*100:.0f}%. ch: 1 champion, "
          "0 non-champion, blank = year undesignated in champion_arms.csv.")
    print("=" * 100)
    hdr = (f"{'acq':7s} {'arm':21s} {'ch':>2s} {'gsd':>6s} {'thr':>6s} "
           f"{'fpr_bg':>8s} {'n_bg_px':>11s} {'recall':>7s} {'n_tree_px':>10s} "
           f"{'valid%':>7s}  flag")
    print(hdr)
    print("-" * 100)
    flagged = []
    for r in sch:
        fl = ""
        if r["fpr_bg"] != "" and r["fpr_bg"] > FP_FLAG:
            fl = f"<== FP {r['fpr_bg']*100:.1f}%"
            flagged.append(r)
        print(f"{r['acq_label']:7s} {(r['arm'] or '-'):21s} {str(r['is_champion']):>2s} "
              f"{r['gsd_cm']:6.1f} {r['thresh']:6.4f} {r['fpr_bg']:8.4f} "
              f"{r['n_bg_px']:11,d} {r['recall_tree']:7.3f} {r['n_tree_px']:10,d} "
              f"{r['frac_valid']*100:7.1f}  {fl}")
    if flagged:
        print(f"\n  {len(flagged)} arm/year FLAGGED over {FP_FLAG*100:.0f}% background-as-tree:")
        for r in flagged:
            print(f"    {r['acq_label']}/{r['arm'] or '-'}: fpr_bg {r['fpr_bg']:.4f} "
                  f"({r['fp']:,} of {r['n_bg_px']:,} background px)")
    else:
        print(f"\n  none over {FP_FLAG*100:.0f}% - the FP control holds for every scored arm.")

    # ---- TABLE 2: Development = dated pre-anchor recall ---------------------
    dev = [r for r in rows if r["site"].startswith("Development")]
    dev.sort(key=lambda r: (r["year_from"], r["acq_year"], r["acq_label"], r["arm"]))
    print("\n" + "=" * 100)
    print("TABLE 2  Development parcel - RECALL TRAJECTORY (the only DATED pre-anchor truth)")
    print("  labelled tree fraction by interval: 1996-1998 79.7% -> 2000 19.0% "
          "-> 2001 19.5% -> 2002-2005 16.3%")
    print("=" * 100)
    print(f"{'interval':11s} {'acq':7s} {'arm':21s} {'ch':>2s} {'gsd':>6s} "
          f"{'tree_frac':>9s} {'recall':>7s} {'fpr_bg':>8s} {'prec':>6s} "
          f"{'n_tree_px':>10s} {'valid%':>7s}")
    print("-" * 100)
    for r in dev:
        print(f"{r['interval']:11s} {r['acq_label']:7s} {(r['arm'] or '-'):21s} "
              f"{str(r['is_champion']):>2s} {r['gsd_cm']:6.1f} "
              f"{r['label_tree_frac']:9.4f} {r['recall_tree']:7.3f} "
              f"{r['fpr_bg']:8.4f} {r['precision_site']:6.3f} "
              f"{r['n_tree_px']:10,d} {r['frac_valid']*100:7.1f}")
    for site, interval in noacq:
        if site.startswith("Development"):
            print(f"{interval:11s} {'-':7s} {'(no acquisition in the catalog falls '
                                             'inside this interval)':<40s}")

    # ---- exception lists ----------------------------------------------------
    print("\n" + "=" * 100)
    print("EXCEPTIONS - nothing here was scored; none of it is estimated")
    print("=" * 100)
    print(f"\nA. NO-ACQUISITION intervals ({len(noacq)}): the labels exist, the imagery does not")
    for site, interval in noacq:
        print(f"   {site} {interval}")
    print(f"\nB. REFUSED - prob raster on the lake, no deployed threshold ({len(refused)})")
    seen = set()
    for site, interval, label, arm, fname, why in refused:
        k = (fname, why)
        if k in seen:
            continue
        seen.add(k)
        print(f"   {fname:52s} {why}")
    print(f"   ({len(refused)} refusals over {len(seen)} distinct rasters; a raster inside "
          "several intervals refuses once per interval)")
    print(f"\nC. SKIPPED - under {a.min_valid*100:.0f}% of the labelled ground is prob-valid ({len(skipped)})")
    for site, interval, label, arm, frac in skipped:
        print(f"   {site} {interval} {label}/{arm}: {frac*100:.1f}% valid")
    print(f"\nD. NO PROB RASTER for an acquisition inside an interval ({len(noprob)})")
    by_site = {}
    for site, interval, label in noprob:
        by_site.setdefault((site, interval), []).append(label)
    for (site, interval), labs in by_site.items():
        print(f"   {site} {interval}: {', '.join(labs)}")

    print("\n" + "=" * 100)
    print("CAVEATS (read before quoting any number above)")
    print("=" * 100)
    print("""  1. LABEL GRANULARITY. The polygons are parcel/stand-scale hand tracing, not
     per-crown. Every tree/background boundary is one polygon edge, so a coarse
     acquisition puts whole mixed pixels on one side of it. all_touched=False and
     no boundary buffer: the halo inflates the school's fpr_bg at 30-100 cm and
     depresses recall on Development's small remnant clumps. It is not corrected
     for, because correcting it would need a rule nobody has measured.
  2. INTERVAL EDGES. An interval is asserted from the imagery Kam reviewed; the
     transition years between intervals are the least certain. Development
     2000-2000 in particular is a single-year interval scored by a single
     acquisition - it is a point, not a trend.
  3. SMALL n. The school's tree class is 5 cut-outs, 3.1% of its labelled ground:
     at 1 m GSD that is a few thousand pixels, so its recall column swings hard.
     The school's LOAD-BEARING column is fpr_bg (n in the millions); its recall
     is context. Development is the site with real tree n.
  4. SEASON. The acquisitions are not season-matched (2015 King is Feb-Mar
     leaf-off). Deciduous recall drops on leaf-off dates for reasons that are not
     model error - the trajectory must be read with the acquisition date in hand
     (see the pixel-size/date table).
  5. SPATIAL SUBSET. Sector-restricted arms cover 71.4% of the school's ground
     and 7.1% of Development's. School rows from those arms are scored on the
     covered part only - frac_valid says how much. They are not comparable
     pixel-for-pixel with a full-footprint arm on the same year.
  6. EVAL GROUND. `trained_on` is empty for every row today. It stays that way
     only as long as no run trains on these sites; a run that does must fill it.""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
