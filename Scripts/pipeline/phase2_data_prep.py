"""
Phase 2 — Data Preparation (Validation & QA)
Edmonds Temporal Active Learning Pipeline

NOTE: Upsampling and spectral extraction are handled by
phase1_preprocess.py (Step 0 and Steps 6-7). This script is
for validation and QA only.

STEPS
  Step 1  catalog     Print full imagery catalog for review
  Step 2  validate    Validate every acquisition (CRS, GSD, bands, extent)
  Step 3  coverage    Document training site coverage per year
  Step 4  overlay     Temporal overlay QA — 2020 crowns on any year

OUTPUTS
  phase2/imagery_validation_report.csv
  phase2/training_site_coverage.csv
  phase2/overlays/overlay_{year}_{site}.png

USAGE
  %run phase2_data_prep.py
  %run phase2_data_prep.py --step validate
  %run phase2_data_prep.py --step coverage
  %run phase2_data_prep.py --step overlay --year 2005 --site 1
  %run phase2_data_prep.py --dry-run
"""

import argparse, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
import rasterio
from shapely.geometry import box

warnings.filterwarnings("ignore")

BASE           = Path("/content/drive/MyDrive/treedata")
IMAGERY_DIR    = BASE / "Full_Image/Pipeline Imagery"
UPSAMPLE_DIR   = IMAGERY_DIR / "upsample"
CROWNS_PATH    = BASE / "phase1/edmonds_crowns_phase1.gpkg"
PHOTOS_DIR     = BASE / "photos"
POLYGONS_DIR   = BASE / "polygons"
BOUNDARY_PATH  = BASE / "boundary/edmonds_boundary.shp"
OUT_DIR        = BASE / "phase2"
VALIDATION_OUT = OUT_DIR / "imagery_validation_report.csv"
COVERAGE_OUT   = OUT_DIR / "training_site_coverage.csv"
OVERLAY_DIR    = OUT_DIR / "overlays"

SEG_INST = "instance+semantic"
SEG_SEM  = "semantic_only"
ALIGNED_CRS_EPSG = 3857
ALIGNED_GSD_CM   = 7.5

YEAR_CATALOG = [
    {"key": 2000,    "label": "2000",    "source": "King County",     "gsd_cm": 59.7, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_SEM,  "native_file": "2000_king_rgb.tif",    "aligned_file": "2000_king_rgb_upsampled.tif"},
    {"key": 2002,    "label": "2002",    "source": "King County",     "gsd_cm": 59.7, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_SEM,  "native_file": "2002_king_rgb.tif",    "aligned_file": "2002_king_rgb_upsampled.tif"},
    {"key": 2005,    "label": "2005",    "source": "King County",     "gsd_cm": 29.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_SEM,  "native_file": "2005_king_rgb.tif",    "aligned_file": "2005_king_rgb_upsampled.tif"},
    {"key": 2007,    "label": "2007",    "source": "King County",     "gsd_cm": 29.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_SEM,  "native_file": "2007_king_rgb.tif",    "aligned_file": "2007_king_rgb_upsampled.tif"},
    {"key": 2009,    "label": "2009",    "source": "King County",     "gsd_cm": 29.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_SEM,  "native_file": "2009_king_rgb.tif",    "aligned_file": "2009_king_rgb_upsampled.tif"},
    {"key": 2013,    "label": "2013",    "source": "King County",     "gsd_cm": 14.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2013_king_rgb.tif",    "aligned_file": "2013_king_rgb_upsampled.tif"},
    {"key": 2015,    "label": "2015",    "source": "King County",     "gsd_cm": 14.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2015_king_rgb.tif",    "aligned_file": "2015_king_rgb_upsampled.tif"},
    {"key": 2016,    "label": "2016",    "source": "Snohomish Co.",   "gsd_cm": 50.0, "bands": 4, "crs_epsg": 2285,  "coverage": "67%",  "seg_tier": SEG_SEM,  "native_file": "2016_snoh_rgbi.tif",   "aligned_file": "2016_snoh_rgbi_upsampled.tif"},
    {"key": 2017,    "label": "2017",    "source": "City of Edmonds", "gsd_cm": 7.5,  "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2017_coe_rgb.tif",     "aligned_file": "2017_coe_rgb.tif"},
    {"key": 2019,    "label": "2019",    "source": "King County",     "gsd_cm": 14.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2019_king_rgb.tif",    "aligned_file": "2019_king_rgb_upsampled.tif"},
    {"key": "2019n", "label": "2019n",   "source": "NAIP",            "gsd_cm": 60.0, "bands": 4, "crs_epsg": 26910, "coverage": "full", "seg_tier": SEG_SEM,  "native_file": "2019_naip_rgbi.tif",   "aligned_file": "2019_naip_rgbi_upsampled.tif"},
    {"key": 2020,    "label": "2020",    "source": "City of Edmonds", "gsd_cm": 7.5,  "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2020_coe_rgb.tif",     "aligned_file": "2020_coe_rgb.tif"},
    {"key": 2021,    "label": "2021",    "source": "King County",     "gsd_cm": 14.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2021_king_rgb.tif",    "aligned_file": "2021_king_rgb_upsampled.tif"},
    {"key": "2021s", "label": "2021s",   "source": "Snohomish Co.",   "gsd_cm": 50.0, "bands": 4, "crs_epsg": 2285,  "coverage": "67%",  "seg_tier": SEG_SEM,  "native_file": "2021_snoh_rgbi.tif",   "aligned_file": "2021_snoh_rgbi_upsampled.tif"},
    {"key": 2022,    "label": "2022",    "source": "City of Edmonds", "gsd_cm": 7.5,  "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2022_coe_rgb.tif",     "aligned_file": "2022_coe_rgb.tif"},
    {"key": "2022n", "label": "2022n",   "source": "NAIP",            "gsd_cm": 60.0, "bands": 4, "crs_epsg": 26910, "coverage": "full", "seg_tier": SEG_SEM,  "native_file": "2022_naip_rgbi.tif",   "aligned_file": "2022_naip_rgbi_upsampled.tif"},
    {"key": 2023,    "label": "2023",    "source": "King County",     "gsd_cm": 14.9, "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2023_king_rgb.tif",    "aligned_file": "2023_king_rgb_upsampled.tif"},
    {"key": 2024,    "label": "2024",    "source": "City of Edmonds", "gsd_cm": 7.5,  "bands": 3, "crs_epsg": 3857,  "coverage": "full", "seg_tier": SEG_INST, "native_file": "2024_coe_rgb.tif",     "aligned_file": "2024_coe_rgb.tif"},
]

def catalog_by_key(key):
    for e in YEAR_CATALOG:
        if e["key"] == key: return e
    return None

def discover_training_sites():
    sites = []
    if not PHOTOS_DIR.exists(): return sites
    for i, tif in enumerate(sorted(PHOTOS_DIR.glob("*_rgb.tif")), 1):
        site = {"site_id": i, "site_name": tif.stem.replace("_rgb",""), "photo_path": tif}
        poly = POLYGONS_DIR / (tif.stem.replace("_rgb","") + ".shp")
        site["polygon_path"] = poly if poly.exists() else None
        try:
            with rasterio.open(tif) as src:
                site["bounds"], site["crs"] = src.bounds, src.crs
        except Exception:
            site["bounds"], site["crs"] = None, None
        sites.append(site)
    return sites

# ═══════════════════════════ STEP 1 — CATALOG ════════════════════════════════

def step_catalog():
    print(f"\n── Step 1: Imagery Catalog ({len(YEAR_CATALOG)} acquisitions) ──")
    print(f"\n  {'Year':<8} {'Source':<18} {'GSD':>6} {'Bands':>5} {'CRS':>10} {'Cov':>5} {'Tier':<20}")
    print(f"  {'─'*8} {'─'*18} {'─'*6} {'─'*5} {'─'*10} {'─'*5} {'─'*20}")
    for e in YEAR_CATALOG:
        print(f"  {e['label']:<8} {e['source']:<18} {e['gsd_cm']:>5.1f}  {e['bands']:>4}  EPSG:{e['crs_epsg']:<5} {e['coverage']:>5} {e['seg_tier']:<20}")
    n_n = sum(1 for e in YEAR_CATALOG if (IMAGERY_DIR/e["native_file"]).exists())
    n_a = sum(1 for e in YEAR_CATALOG if (UPSAMPLE_DIR/e["aligned_file"]).exists())
    print(f"\n  Native found : {n_n}/{len(YEAR_CATALOG)}   Aligned found: {n_a}/{len(YEAR_CATALOG)}")
    miss = [e["label"] for e in YEAR_CATALOG if not (UPSAMPLE_DIR/e["aligned_file"]).exists()]
    if miss:
        print(f"  Missing aligned: {', '.join(miss)}")
        print(f"  → Run: %run phase1_preprocess.py --upsample-only")

# ═══════════════════════════ STEP 2 — VALIDATE ═══════════════════════════════

def validate_acquisition(entry, boundary_geom=None):
    result = {"year": entry["label"], "source": entry["source"],
              "expected_gsd_cm": entry["gsd_cm"], "expected_bands": entry["bands"],
              "expected_crs_epsg": entry["crs_epsg"], "seg_tier": entry["seg_tier"]}
    for cat, base, fkey in [("native", IMAGERY_DIR, "native_file"), ("aligned", UPSAMPLE_DIR, "aligned_file")]:
        path = base / entry[fkey]; pfx = f"{cat}_"
        result[pfx+"file"] = entry[fkey]; result[pfx+"exists"] = path.exists()
        if not path.exists():
            for k in ["readable","crs_ok","gsd_ok","bands_ok","coverage_pct","width_px","height_px","actual_gsd","actual_crs","actual_bands"]:
                result[pfx+k] = False if k == "readable" else None
            continue
        try:
            with rasterio.open(path) as src:
                result[pfx+"readable"] = True
                result[pfx+"width_px"], result[pfx+"height_px"] = src.width, src.height
                result[pfx+"actual_bands"] = src.count
                aepsg = src.crs.to_epsg() if src.crs else None
                result[pfx+"actual_crs"] = aepsg
                agsd = round(src.res[0]*100, 2); result[pfx+"actual_gsd"] = agsd
                if cat == "native":
                    result[pfx+"crs_ok"] = aepsg == entry["crs_epsg"]
                    result[pfx+"gsd_ok"] = abs(agsd - entry["gsd_cm"])/entry["gsd_cm"] <= 0.15
                else:
                    result[pfx+"crs_ok"] = aepsg == ALIGNED_CRS_EPSG
                    result[pfx+"gsd_ok"] = abs(agsd - ALIGNED_GSD_CM)/ALIGNED_GSD_CM <= 0.05
                result[pfx+"bands_ok"] = src.count == entry["bands"]
                if boundary_geom:
                    try:
                        inter = boundary_geom.intersection(box(*src.bounds))
                        result[pfx+"coverage_pct"] = round(100*inter.area/boundary_geom.area, 1)
                    except: result[pfx+"coverage_pct"] = None
                else: result[pfx+"coverage_pct"] = None
        except Exception as exc:
            for k in ["readable","crs_ok","gsd_ok","bands_ok","coverage_pct","width_px","height_px","actual_gsd","actual_crs","actual_bands"]:
                result[pfx+k] = False if k == "readable" else None
            print(f"    ERROR: {path.name}: {exc}")
    return result

def step_validate(dry_run=False):
    print(f"\n── Step 2: Validating {len(YEAR_CATALOG)} acquisitions ──")
    bg = None
    if BOUNDARY_PATH.exists():
        bg = gpd.read_file(BOUNDARY_PATH).geometry.unary_union
        print(f"  Boundary loaded")
    rows = []
    for entry in YEAR_CATALOG:
        print(f"\n  {entry['label']} ({entry['source']}):")
        r = validate_acquisition(entry, bg); rows.append(r)
        for ct in ["native","aligned"]:
            pfx = f"{ct}_"
            if not r.get(pfx+"exists"):
                print(f"    {ct:>7}: MISSING"); continue
            parts = []
            for cn, vk, ok in [("CRS","actual_crs","crs_ok"),("GSD","actual_gsd","gsd_ok"),("bands","actual_bands","bands_ok")]:
                if r.get(pfx+ok) is True: parts.append(f"{cn} ✓")
                elif r.get(pfx+ok) is False: parts.append(f"{cn} ✗ ({r.get(pfx+vk)})")
            cov = r.get(pfx+"coverage_pct")
            if cov is not None: parts.append(f"cov {cov}%")
            print(f"    {ct:>7}: {' · '.join(parts)}")
    df = pd.DataFrame(rows)
    for ct in ["native","aligned"]:
        ne = df[f"{ct}_exists"].sum()
        nv = (df[f"{ct}_crs_ok"].fillna(False) & df[f"{ct}_gsd_ok"].fillna(False) & df[f"{ct}_bands_ok"].fillna(False)).sum()
        print(f"  {ct.capitalize():>7}: {ne}/{len(YEAR_CATALOG)} exist, {nv} valid")
    if not dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(VALIDATION_OUT, index=False)
        print(f"\n  ✓ → {VALIDATION_OUT}")
    return df

# ═══════════════════════════ STEP 3 — COVERAGE ═══════════════════════════════

def step_coverage(dry_run=False):
    print(f"\n── Step 3: Training Site Coverage ──")
    sites = discover_training_sites()
    if not sites: print("  No sites found"); return None
    print(f"  Sites: {len(sites)}")
    rows = []
    for entry in YEAR_CATALOG:
        np_ = IMAGERY_DIR / entry["native_file"]
        for site in sites:
            row = {"year": entry["label"], "site_id": site["site_id"], "site_name": site["site_name"],
                   "source": entry["source"], "gsd_cm": entry["gsd_cm"], "seg_tier": entry["seg_tier"]}
            if not np_.exists():
                row.update(imagery_exists=False, site_covered=False, coverage_pct=0.0, include=False, exclude_reason="imagery_missing")
            elif site["bounds"] is None:
                row.update(imagery_exists=True, site_covered=None, coverage_pct=None, include=None, exclude_reason="bounds_unknown")
            else:
                try:
                    with rasterio.open(np_) as src:
                        ib = box(*src.bounds); sb = box(*site["bounds"])
                        if site["crs"] and src.crs and site["crs"] != src.crs:
                            sb = gpd.GeoDataFrame(geometry=[sb], crs=site["crs"]).to_crs(src.crs).geometry.iloc[0]
                        c = round(100*ib.intersection(sb).area/sb.area, 1)
                        row.update(imagery_exists=True, site_covered=c>=95, coverage_pct=c, include=c>=95,
                                   exclude_reason=None if c>=95 else "partial")
                except Exception as exc:
                    row.update(imagery_exists=True, site_covered=None, coverage_pct=None, include=False, exclude_reason=str(exc))
            rows.append(row)
    df = pd.DataFrame(rows)
    sids = sorted(df["site_id"].unique())
    print(f"\n  {'Year':<8} " + " ".join(f"S{s}" for s in sids))
    for entry in YEAR_CATALOG:
        yr = df[df["year"]==entry["label"]]
        m = []
        for s in sids:
            sr = yr[yr["site_id"]==s]
            if len(sr)==0 or sr.iloc[0]["include"] is None: m.append(" ?")
            elif sr.iloc[0]["include"]: m.append(" ✓")
            else: m.append(" ✗")
        print(f"  {entry['label']:<8} " + "  ".join(m))
    if not dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(COVERAGE_OUT, index=False)
        print(f"\n  ✓ → {COVERAGE_OUT}")
    return df

# ═══════════════════════════ STEP 4 — OVERLAY ════════════════════════════════

def step_overlay(year_filter=None, site_filter=None, dry_run=False):
    print(f"\n── Step 4: Temporal Overlay QA ──")
    entries = [e for e in YEAR_CATALOG if e["key"]==year_filter] if year_filter else YEAR_CATALOG
    sites = discover_training_sites()
    if site_filter: sites = [s for s in sites if s["site_id"]==site_filter]
    if not sites: print("  No sites"); return
    crowns = None
    if not dry_run and CROWNS_PATH.exists():
        crowns = gpd.read_file(CROWNS_PATH); print(f"  Loaded {len(crowns):,} crowns")
    for entry in entries:
        for site in sites:
            ek = entry["key"]; sid = site["site_id"]
            ap = UPSAMPLE_DIR/entry["aligned_file"]; np_ = IMAGERY_DIR/entry["native_file"]
            ip = ap if ap.exists() else np_
            if not ip.exists(): print(f"  SKIP {entry['label']} — no imagery"); continue
            if site["bounds"] is None: print(f"  SKIP site {sid} — no bounds"); continue
            if dry_run: print(f"  DRY RUN — {entry['label']} site {sid}"); continue
            try:
                import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
            except ImportError: print("  Need matplotlib"); return
            if crowns is None: print("  No crowns loaded"); return
            sb = site["bounds"]
            with rasterio.open(ip) as src:
                w = rasterio.windows.from_bounds(*sb, transform=src.transform)
                w = w.intersection(rasterio.windows.Window(0,0,src.width,src.height))
                img = np.moveaxis(src.read([1,2,3], window=w), 0, -1)
                ic = src.crs
            sbox = box(*sb); cs = crowns[crowns.geometry.intersects(sbox)].copy()
            if cs.crs != ic: cs = cs.to_crs(ic)
            fig, ax = plt.subplots(1,1,figsize=(16,16),dpi=100)
            ax.imshow(img, extent=[sb[0],sb[2],sb[1],sb[3]])
            for _,r in cs.iterrows():
                g = r.geometry
                polys = [g] if g.geom_type=="Polygon" else list(g.geoms)
                for p in polys:
                    x,y = p.exterior.xy; ax.plot(x,y,color="cyan",lw=0.5,alpha=0.7)
            ax.set_title(f"2020 crowns on {entry['label']} (site {sid})")
            OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
            out = OVERLAY_DIR/f"overlay_{entry['label']}_site{sid}.png"
            fig.savefig(out, bbox_inches="tight", dpi=150); plt.close(fig)
            print(f"  ✓ {out}")

# ═══════════════════════════ MAIN ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Phase 2 — Validation & QA")
    parser.add_argument("--step", choices=["catalog","validate","coverage","overlay"])
    parser.add_argument("--year", type=str)
    parser.add_argument("--site", type=int)
    parser.add_argument("--dry-run", action="store_true")
    filtered = [a for a in sys.argv[1:] if not (a=="-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)
    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "phase4" / "logs"
    SCRIPT_NAME = "phase2_data_prep"
    yk = None
    if args.year:
        try: yk = int(args.year)
        except ValueError: yk = args.year
        if not catalog_by_key(yk): print(f"  ERROR: '{args.year}' not in catalog"); sys.exit(1)
    print("="*60); print("  PHASE 2 — Data Preparation (Validation & QA)"); print("  Edmonds Temporal Pipeline"); print("="*60)
    run_all = args.step is None
    if run_all or args.step=="catalog":
        with StepLogger(SCRIPT_NAME, "catalog", LOGS_DIR) as log:
            step_catalog()
            log.finish(errors=0)
    if run_all or args.step=="validate":
        with StepLogger(SCRIPT_NAME, "validate", LOGS_DIR) as log:
            step_validate(dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)
    if run_all or args.step=="coverage":
        with StepLogger(SCRIPT_NAME, "coverage", LOGS_DIR) as log:
            step_coverage(dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)
    if args.step=="overlay":
        with StepLogger(SCRIPT_NAME, "overlay", LOGS_DIR) as log:
            step_overlay(year_filter=yk, site_filter=args.site, dry_run=args.dry_run)
            log.finish(year=args.year, site=args.site, dry_run=args.dry_run, errors=0)
    elif run_all: print(f"\n── Step 4: Overlay QA — use --step overlay --year YYYY --site N")
    print(f"\n{'='*60}"); print("  PHASE 2 COMPLETE"); print(f"{'='*60}")

if __name__ == "__main__":
    main()