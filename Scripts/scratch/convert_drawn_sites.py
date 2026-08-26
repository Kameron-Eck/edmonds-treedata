r"""Convert Kam's hand-drawn ArcGIS site polygons into pipeline label artifacts.

INPUT (READ-ONLY, NEVER MODIFIED)
  D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid\negative_sites_draw.shp
  Fields: site / kind / role / quality / notes / yr_from / yr_to.  It stays Kam's
  drawing surface; every output of this script is a NEW file beside it.

THE CONVENTIONS (decoded with Kam 2026-08-25 — authoritative)
  1. role='Tree'      -> ASSERT CANOPY over that polygon, for that year interval.
     role='Not Tree'  -> ASSERT BACKGROUND (a real background label, NOT ignore).
  2. INVERSE COMPLETION. Within one (site, yr_from..yr_to) interval Kam drew
     whichever class was easier to trace; the UNDRAWN remainder of the site
     region is the OPPOSITE class.  Drawn Tree -> remainder background; drawn
     Not Tree -> remainder tree.  Every existing (site, interval) uses exactly
     ONE role, so the rule is unambiguous — and this script REFUSES (nonzero
     exit) to guess if a future interval ever mixes Tree and Not Tree rows.
  3. Multipart features are legitimate — they are exploded to singlepart.
  4. Case is inconsistent ('positive'/'Positive'/'negative') — normalised
     case-insensitively.  Rows with no site/role (stray digitising) are dropped
     with a warning naming the count.
  5. The region row's `kind` is blank; kind lives on the children.  The region
     row is identified by role=='region' and inherits the majority child kind.

OUTPUTS
  A. sites_drawn_clean.shp        (beside the original, EPSG:3857)
        singlepart, case-normalised, blank rows dropped, region kind filled.
        For Kam to LOOK at / optionally continue in.  README_clean.txt sidecar.
  B. site_labels_timeseries.gpkg  (beside the original, + copy to the data plane
        G:\My Drive\treedata\phase4\labels_sites\), layer 'site_labels':
          site, year_from, year_to, cls in {tree, background},
          src in {drawn, complement}, geometry (EPSG:3857)
        Per (site, interval): the drawn polygons dissolved AS their class, PLUS
        the site region minus that union as the OPPOSITE class.  Exact
        complement — no buffer — so the two classes tile the region exactly.
  C. {Negative_*}_regions_v2.gpkg  (data plane polygons/, _v2 SUFFIX, never
        overwriting v1) for any site that is a STATIC training negative: region
        MINUS its Tree features buffered by HOLE_BUFFER_M, matching the v1
        format exactly (layer '{name}_regions', columns site/geometry).
        _tile_signature() does NOT key on the regions file, so replacing v1 in
        place would silently reuse stale tiles — promotion is deliberate:
        rename v2 over v1 and re-run with --force-retile.

  NO photos/*_rgb.tif are written.  discover_site_footprints() globs
  photos/*_rgb.tif, and a site with a photo but no crowns file is treated as a
  wall-to-wall negative by _is_negative_site — which would be flatly wrong for a
  timeseries site like Development (forested in its early years).

Geometry hygiene: make_valid/buffer(0), singlepart explode, parts < 1 m2 dropped.
Areas are TRUE GROUND m2 (computed in EPSG:32610); geometries stay EPSG:3857.

Usage:  py -3.12 scratch/convert_drawn_sites.py --dry-run
        py -3.12 scratch/convert_drawn_sites.py
"""
import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

SITE_GRID = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\site_grid")
DRAWN = SITE_GRID / "negative_sites_draw.shp"          # READ-ONLY. Kam's hand work.
CLEAN_SHP = SITE_GRID / "sites_drawn_clean.shp"
CLEAN_README = SITE_GRID / "README_clean.txt"
TS_GPKG = SITE_GRID / "site_labels_timeseries.gpkg"

BASE = Path(r"G:\My Drive\treedata")
DRIVE_LABELS = BASE / "phase4" / "labels_sites"
POLYGONS = BASE / "polygons"

CRS = "EPSG:3857"          # the pipeline working CRS — all geometry is written in it
AREA_CRS = "EPSG:32610"    # UTM 10N — areas only (3857 inflates ~2.2x at 47.8 N)
LAYER = "site_labels"
SLIVER_M2 = 1.0            # true-ground m2; parts smaller than this are dropped
HOLE_BUFFER_M = 2.5        # C only: tree cut-out buffer, matches the v1 artifact

ROLE_MAP = {"region": "region", "tree": "tree",
            "not_tree": "not_tree", "nottree": "not_tree"}
KINDS = ("negative", "positive")
CLS_OF_ROLE = {"tree": "tree", "not_tree": "background"}
OPPOSITE = {"tree": "background", "background": "tree"}

# Sites already known to be static training negatives. A newly-detected one is a
# real decision (it injects wall-to-wall background tiles into training), so the
# script stops and makes you say --allow-new-negatives.
BASELINE_NEGATIVES = {"Edmonds Heights K-12"}


# ─────────────────────────────────────────────────────────────── helpers ──
def _blank(v):
    s = str(v).strip()
    return s == "" or s.lower() in ("nan", "none", "<na>")


def sanitize(site, kind):
    core = re.sub(r"[^A-Za-z0-9]+", "_", str(site)).strip("_")
    if not core.lower().startswith("negative"):
        core = "Negative_" + core
    return core


def _years(yr_from, yr_to):
    return set(range(int(yr_from), int(yr_to) + 1))


def _fmt(n):
    return f"{n:,.1f}"


# ────────────────────────────────────────────────────────────────── main ──
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print the full plan; write nothing")
    ap.add_argument("--allow-new-negatives", action="store_true",
                    help="permit static-negative sites beyond the recorded baseline")
    ap.add_argument("--no-drive-copy", action="store_true",
                    help="skip the copy of the timeseries GPKG to the data plane")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    import fiona
    import geopandas as gpd
    from shapely.geometry import MultiPolygon
    from shapely.ops import unary_union
    try:
        from shapely import make_valid as _mkvalid
    except ImportError:                                    # shapely < 2.0
        _mkvalid = None

    errors = []      # (site, reason) — any entry => nonzero exit, nothing written
    warns = []
    slivers = [0, 0.0]   # [count, total true-ground m2] of dropped parts

    def fail(site, reason):
        errors.append((str(site), reason))

    def clean_geom(g):
        """make_valid -> buffer(0) fallback. Returns a possibly-empty geometry."""
        if g is None or g.is_empty:
            return None
        if not g.is_valid:
            g = _mkvalid(g) if _mkvalid is not None else g.buffer(0)
        if g is None or g.is_empty:
            return None
        return g

    def parts(g):
        """Singlepart polygon parts of g, slivers dropped (true-ground m2)."""
        g = clean_geom(g)
        if g is None:
            return []
        geoms = list(getattr(g, "geoms", [g]))
        polys = [p for p in geoms if p.geom_type == "Polygon" and not p.is_empty]
        if not polys:
            return []
        s = gpd.GeoSeries(polys, crs=CRS).to_crs(AREA_CRS).area
        for ar in s:
            if float(ar) < SLIVER_M2:
                slivers[0] += 1
                slivers[1] += float(ar)
        return [p for p, ar in zip(polys, s) if float(ar) >= SLIVER_M2]

    def m2(g):
        """True ground area of a geometry (EPSG:32610)."""
        if g is None or (hasattr(g, "is_empty") and g.is_empty):
            return 0.0
        return float(gpd.GeoSeries([g], crs=CRS).to_crs(AREA_CRS).area.iloc[0])

    # ── read + normalise ─────────────────────────────────────────────────
    if not DRAWN.exists():
        sys.exit(f"missing input: {DRAWN}")
    raw = gpd.read_file(DRAWN)
    if raw.crs is None or raw.crs.to_epsg() != 3857:
        raw = raw.to_crs(CRS)
    print(f"INPUT  {DRAWN}")
    print(f"       {len(raw)} features, CRS {raw.crs}, "
          f"{(raw.geometry.type == 'MultiPolygon').sum()} multipart")

    rows, n_blank = [], 0
    for fid, r in raw.iterrows():
        if _blank(r.get("site")) or _blank(r.get("role")):
            n_blank += 1
            continue
        role = ROLE_MAP.get(re.sub(r"[^a-z]+", "_", str(r["role"]).strip().lower()).strip("_"))
        if role is None:
            fail(r.get("site"), f"fid {fid}: unknown role {r['role']!r} — decoded roles are "
                                f"region/Tree/'Not Tree'. (A 'hole'/IGNORE role has no agreed "
                                f"meaning under the inverse-completion rule — ask Kam.)")
            continue
        kind = str(r.get("kind")).strip().lower()
        kind = kind if kind in KINDS else ""
        if role != "region" and kind == "" and not _blank(r.get("kind")):
            warns.append(f"fid {fid} ({r['site']}): unrecognised kind {r['kind']!r} -> blank")
        for p in parts(r.geometry):
            rows.append({"site": str(r["site"]).strip(), "kind": kind, "role": role,
                         "quality": "" if _blank(r.get("quality")) else str(r["quality"]).strip(),
                         "notes": "" if _blank(r.get("notes")) else str(r["notes"]).strip(),
                         "yr_from": int(r.get("yr_from") or 0), "yr_to": int(r.get("yr_to") or 0),
                         "src_fid": int(fid), "geometry": p})
    if n_blank:
        warns.append(f"dropped {n_blank} blank row(s) (no site/role) — stray digitising")

    if not rows:
        errors.append(("<all>", "no usable rows after normalisation"))
    clean = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)

    # region kind <- majority child kind (ties broken by total child area)
    kind_note = []
    for site, grp in clean.groupby("site"):
        kids = grp[(grp["role"] != "region") & (grp["kind"] != "")]
        if not len(kids):
            continue
        cnt = kids["kind"].value_counts()
        top = [k for k in cnt.index if cnt[k] == cnt.iloc[0]]
        if len(top) > 1:
            ar = {k: sum(m2(g) for g in kids.loc[kids["kind"] == k, "geometry"]) for k in top}
            pick = max(ar, key=ar.get)
            warns.append(f"{site}: child-kind tie {dict(cnt)} -> '{pick}' by area {ar}")
        else:
            pick = top[0]
        clean.loc[(clean["site"] == site) & (clean["role"] == "region"), "kind"] = pick
        kind_note.append(f"{site}: region kind <- '{pick}' ({dict(cnt)})")

    clean["part"] = clean.groupby("src_fid").cumcount()
    clean = clean[["site", "kind", "role", "quality", "notes",
                   "yr_from", "yr_to", "src_fid", "part", "geometry"]]
    print(f"\nA. CLEAN COPY  {len(clean)} singlepart features "
          f"({len(raw)} drawn - {n_blank} blank -> exploded)")
    for ln in kind_note:
        print(f"     {ln}")

    # ── B. timeseries labels ────────────────────────────────────────────
    label_rows, table = [], []
    negatives = {}                       # site -> (name, geometry, n_cuts)
    for site, grp in clean.groupby("site"):
        reg_parts = list(grp.loc[grp["role"] == "region", "geometry"])
        if not reg_parts:
            fail(site, "no role='region' row — the site footprint is undefined; "
                       "the complement cannot be computed")
            continue
        region = clean_geom(unary_union(reg_parts))
        if region is None:
            fail(site, "region geometry is empty/invalid after make_valid")
            continue
        reg_m2 = m2(region)
        reg_yr = grp.loc[grp["role"] == "region", ["yr_from", "yr_to"]].iloc[0]

        kids = grp[grp["role"] != "region"]
        if not len(kids):
            fail(site, "region row but no Tree / 'Not Tree' children — nothing to label")
            continue
        bad_yr = kids[(kids["yr_from"] <= 0) | (kids["yr_to"] <= 0) |
                      (kids["yr_to"] < kids["yr_from"])]
        if len(bad_yr):
            fail(site, f"{len(bad_yr)} child row(s) with no/invalid yr_from-yr_to "
                       f"(fids {sorted(set(bad_yr['src_fid']))}) — intervals are required")
            continue

        ivals = {}
        for (yf, yt), g in kids.groupby(["yr_from", "yr_to"]):
            roles = sorted(set(g["role"]))
            if len(roles) > 1:            # rule 2 guard — NEVER guess
                fail(site, f"interval {yf}-{yt} MIXES roles {roles} "
                           f"(fids {sorted(set(g['src_fid']))}). The inverse-completion rule "
                           f"needs exactly one drawn class per interval; refusing to guess.")
                continue
            ivals[(int(yf), int(yt))] = (roles[0], g)
        if not ivals:
            continue

        # cross-interval contradiction check
        keys = sorted(ivals)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a_k, b_k = keys[i], keys[j]
                if _years(*a_k) & _years(*b_k):
                    ra, rb = ivals[a_k][0], ivals[b_k][0]
                    msg = (f"intervals {a_k[0]}-{a_k[1]} and {b_k[0]}-{b_k[1]} OVERLAP in years "
                           f"{sorted(_years(*a_k) & _years(*b_k))}")
                    if ra != rb:
                        fail(site, msg + f" with different classes ({ra} vs {rb}) — "
                                         f"the complement would be contradictory")
                    else:
                        warns.append(f"{site}: {msg} (same class '{ra}')")

        for (yf, yt) in keys:
            role, g = ivals[(yf, yt)]
            drawn_raw = clean_geom(unary_union(list(g["geometry"])))
            drawn = clean_geom(drawn_raw.intersection(region)) if drawn_raw else None
            spill = m2(drawn_raw) - m2(drawn)
            if spill > SLIVER_M2:
                warns.append(f"{site} {yf}-{yt}: {_fmt(spill)} m2 of drawn '{role}' fell OUTSIDE "
                             f"the region and was clipped away")
            d_parts = parts(drawn) if drawn else []
            comp = clean_geom(region.difference(drawn)) if drawn else region
            c_parts = parts(comp) if comp else []
            d_cls = CLS_OF_ROLE[role]
            c_cls = OPPOSITE[d_cls]
            d_m2 = sum(m2(p) for p in d_parts)
            c_m2 = sum(m2(p) for p in c_parts)
            for p in d_parts:
                label_rows.append({"site": site, "year_from": yf, "year_to": yt,
                                   "cls": d_cls, "src": "drawn", "geometry": p})
            for p in c_parts:
                label_rows.append({"site": site, "year_from": yf, "year_to": yt,
                                   "cls": c_cls, "src": "complement", "geometry": p})
            table.append({"site": site, "interval": f"{yf}-{yt}", "region_m2": reg_m2,
                          "drawn_cls": d_cls, "drawn_m2": d_m2, "drawn_n": len(d_parts),
                          "comp_cls": c_cls, "comp_m2": c_m2, "comp_n": len(c_parts),
                          "comp_pct": 100.0 * c_m2 / reg_m2 if reg_m2 else 0.0,
                          "resid_m2": reg_m2 - d_m2 - c_m2})

        # ── C. static training negative? ────────────────────────────────
        all_tree = all(r == "tree" for r, _ in ivals.values())
        covered = set().union(*[_years(*k) for k in keys])
        reg_span = _years(reg_yr["yr_from"], reg_yr["yr_to"]) if reg_yr["yr_from"] > 0 else None
        full = reg_span is not None and reg_span <= covered
        why = (f"all-intervals-are-Tree={all_tree}; region span "
               f"{reg_yr['yr_from']}-{reg_yr['yr_to']} covered by intervals={full}")
        if all_tree and full:
            cuts = clean_geom(unary_union(list(kids["geometry"])))
            neg = clean_geom(region.difference(cuts.buffer(HOLE_BUFFER_M)))
            neg_parts = parts(neg)
            geom = neg_parts[0] if len(neg_parts) == 1 else MultiPolygon(neg_parts)
            negatives[site] = (sanitize(site, "negative"), geom, len(kids))
            print(f"     STATIC NEGATIVE: {site} -> {sanitize(site, 'negative')}  ({why})")
        else:
            print(f"     timeseries site: {site}  (not a static negative: {why})")

    # baseline guard
    if set(negatives) != BASELINE_NEGATIVES and not a.allow_new_negatives:
        new = set(negatives) - BASELINE_NEGATIVES
        gone = BASELINE_NEGATIVES - set(negatives)
        errors.append(("<negatives>",
                       f"static-negative set changed: new={sorted(new)} missing={sorted(gone)}. "
                       f"A new wall-to-wall background site is a training decision — "
                       f"re-run with --allow-new-negatives once reviewed."))

    # ── the sanity table ────────────────────────────────────────────────
    print("\nB. TIMESERIES LABELS — per (site, interval), true ground m2 (EPSG:32610)")
    hdr = (f"{'site':<22}{'interval':<12}{'region m2':>12}  {'drawn':<11}{'drawn m2':>11}"
           f"{'n':>4}  {'complement':<11}{'comp m2':>11}{'n':>4}{'comp%':>8}{'resid':>8}")
    print("   " + hdr)
    print("   " + "-" * len(hdr))
    for t in table:
        print(f"   {t['site']:<22}{t['interval']:<12}{_fmt(t['region_m2']):>12}  "
              f"{t['drawn_cls']:<11}{_fmt(t['drawn_m2']):>11}{t['drawn_n']:>4}  "
              f"{t['comp_cls']:<11}{_fmt(t['comp_m2']):>11}{t['comp_n']:>4}"
              f"{t['comp_pct']:>7.1f}%{t['resid_m2']:>8.1f}")
    print(f"   {len(label_rows)} label rows total "
          f"({sum(1 for r in label_rows if r['src'] == 'drawn')} drawn / "
          f"{sum(1 for r in label_rows if r['src'] == 'complement')} complement)")

    if slivers[0]:
        warns.append(f"dropped {slivers[0]} polygon part(s) smaller than {SLIVER_M2:g} m2 "
                     f"({slivers[1]:.2f} m2 total) across all geometry ops (input explode, "
                     f"clip-to-region and complement)")
    for w in warns:
        print(f"   WARN  {w}")

    if errors:
        print("\nFAILED — nothing written:")
        for s, r in errors:
            print(f"   ERROR [{s}] {r}")
        return 2

    print("\nC. TRAINING NEGATIVES")
    for site, (name, geom, n_cuts) in negatives.items():
        v1 = POLYGONS / f"{name}_regions.gpkg"
        v2 = POLYGONS / f"{name}_regions_v2.gpkg"
        print(f"   {name}: region minus {n_cuts} Tree cut-out(s) buffered {HOLE_BUFFER_M} m "
              f"-> {m2(geom):,.1f} m2, {geom.geom_type}")
        if v1.exists():
            g1 = gpd.read_file(v1)
            u1 = clean_geom(unary_union(list(g1.geometry)))
            sd = m2(clean_geom(u1.symmetric_difference(geom))) if u1 is not None else float("nan")
            print(f"     v1 exists ({v1.name}, layer '{fiona.listlayers(v1)[0]}') — "
                  f"symmetric difference v1 vs v2 = {sd:,.3f} m2 "
                  f"(v1 {m2(u1):,.1f} m2 vs v2 {m2(geom):,.1f} m2)")
            print(f"     writing {v2.name} BESIDE it; v1 untouched. _tile_signature() does NOT "
                  f"key on the regions file, so promotion is manual and deliberate:")
            print(f"       ren \"{v2}\" \"{v1.name}\"  &&  re-run tiling with --force-retile")
        else:
            print(f"     no v1 present — v2 still written with the _v2 suffix (never auto-live)")

    if a.dry_run:
        print("\nDRY RUN — no files written.")
        return 0

    # ── writes ──────────────────────────────────────────────────────────
    for p in (CLEAN_SHP, TS_GPKG):
        assert p != DRAWN and p.parent == SITE_GRID, p
    clean.to_file(CLEAN_SHP, driver="ESRI Shapefile")
    print(f"\nwrote {CLEAN_SHP}  ({len(clean)} features)")

    CLEAN_README.write_text(_readme(kind_note, warns), encoding="utf-8")
    print(f"wrote {CLEAN_README}")

    labels = gpd.GeoDataFrame(label_rows, geometry="geometry", crs=CRS)[
        ["site", "year_from", "year_to", "cls", "src", "geometry"]]
    if TS_GPKG.exists():
        TS_GPKG.unlink()
    labels.to_file(TS_GPKG, layer=LAYER, driver="GPKG")
    print(f"wrote {TS_GPKG}  (layer '{LAYER}', {len(labels)} rows)")

    if not a.no_drive_copy:
        DRIVE_LABELS.mkdir(parents=True, exist_ok=True)
        dst = DRIVE_LABELS / TS_GPKG.name
        shutil.copy2(TS_GPKG, dst)                    # local-first then copy2 (rule 3)
        print(f"wrote {dst}  ({dst.stat().st_size:,} bytes)")

    with tempfile.TemporaryDirectory(prefix="convert_drawn_sites_") as td:
        for site, (name, geom, _n) in negatives.items():
            v1 = POLYGONS / f"{name}_regions.gpkg"
            v2 = POLYGONS / f"{name}_regions_v2.gpkg"
            assert v2 != v1 and v2.name.endswith("_v2.gpkg"), v2
            stage = Path(td) / v2.name
            gpd.GeoDataFrame({"site": [name]}, geometry=[geom], crs=CRS).to_file(
                stage, layer=f"{name}_regions", driver="GPKG")   # v1's layer name — drop-in on rename
            shutil.copy2(stage, v2)
            print(f"wrote {v2}  ({v2.stat().st_size:,} bytes, layer '{name}_regions')")

    print("\nNOTE  no photos/*_rgb.tif written — a photo makes a site discoverable, and a "
          "photo without a crowns file turns a TIMESERIES site into a wall-to-wall negative.")
    return 0


def _readme(kind_note, warns):
    return f"""SITES — CLEANED COPY (written by scratch/convert_drawn_sites.py, 2026-08-25)
========================================================================

negative_sites_draw.shp IS STILL THE DRAWING SURFACE.
Keep drawing there. sites_drawn_clean.shp is a BUILD PRODUCT, regenerated from
scratch on every run — anything you draw into it will be silently overwritten.
(If you would rather continue in the clean copy, say so and the converter's
input can be switched; until then, draw in negative_sites_draw.shp.)

WHAT THE CLEANING DID
  - exploded multipart features to singlepart (field `part` = part index,
    `src_fid` = the row it came from in negative_sites_draw.shp)
  - normalised case: kind -> lower ('negative' / 'positive');
    role -> one of 'region' / 'tree' / 'not_tree'
  - dropped rows with no site and no role (stray digitising)
  - dropped polygon parts smaller than {SLIVER_M2:g} m2 (true ground area)
  - make_valid / buffer(0) on every geometry
  - filled the blank region-row `kind` from the majority child kind:
{chr(10).join('      ' + n for n in kind_note) or '      (none)'}
    NOTE this is mechanical: 'Development' has 17 Tree children and 3 Not Tree
    children, so its region row reads kind='positive' even though the site is a
    clear-and-rebuild sequence. The region `kind` is descriptive only — nothing
    downstream branches on it. Class comes from role + the interval.

WHAT THE ROLES MEAN (as decoded with you, 2026-08-25)
  role='Tree'      = ASSERT CANOPY here, for yr_from..yr_to
  role='Not Tree'  = ASSERT BACKGROUND here (a real background label, not ignore)
  INVERSE COMPLETION: inside one (site, yr_from..yr_to) you draw whichever class
  is easier; the rest of the site region is automatically the OPPOSITE class.
  So ONE interval must use ONE role only. Mixing Tree and Not Tree rows in the
  same interval makes the converter stop with an error rather than guess.
  Overlapping intervals with different classes are an error too.

  There is no decoded meaning yet for a role='hole' (pure IGNORE) row — the old
  README.txt mentioned one. The converter errors on it instead of guessing. Say
  the word if you want IGNORE back as a third role.

OTHER OUTPUTS OF THIS RUN
  site_labels_timeseries.gpkg (here, + G:\\My Drive\\treedata\\phase4\\labels_sites\\)
    layer 'site_labels' — site / year_from / year_to / cls (tree|background) /
    src (drawn|complement) / geometry. This is the file that finally consumes
    yr_from and yr_to.
  G:\\My Drive\\treedata\\polygons\\Negative_*_regions_v2.gpkg
    the training-negative footprint (region minus Tree cut-outs buffered
    {HOLE_BUFFER_M:g} m). Written with a _v2 suffix and NOT live: the tiling cache
    signature does not key on this file, so swapping it in must be done by hand
    (rename over the v1 name) together with a --force-retile.

WARNINGS FROM THE RUN THAT WROTE THIS FILE
{chr(10).join('  - ' + w for w in warns) or '  (none)'}
"""


if __name__ == "__main__":
    sys.exit(main())
