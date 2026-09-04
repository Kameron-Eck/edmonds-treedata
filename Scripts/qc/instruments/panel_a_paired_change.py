r"""PANEL A — paired-change photo-interpretation kit (2016 -> 2024).

The direction campaign's human instrument (design gated by
qc/instruments/paired_change_power.py: GO at N=1000, capture ~0.9,
differential error <=0.005 — both MEASURED by this kit, not assumed).

One human judges the SAME physical point in 2016 and 2024 imagery,
side-by-side. Pairing cancels the model, thresholds, reference vintage,
radiometry, and the interpreter's private canopy definition. Statement
produced: net canopy change 2016->2024 +/- 95% CI.

STEPS
  --step design    strata + draw -> panel_a_points.csv / _meta.json
  --step chips     cut side-by-side chip PNGs (registration vectors applied)
  --step serve     paired browser UI -> panel_a_labels.csv (append-only, undo ok)
  --step estimate  paired Olofsson net change + capture audit + duplicate
                   agreement + blur-control false-change rate

STRATA (2 m lattice on EPSG:26910, clipped to the city polygon)
  1 cand_change   locator union: C-CAP 2016 vs 2021 canopy flip | 2016 vs
                  2024 citywide model masks disagree | chm2>=5 m and the
                  2024 mask says non-canopy | buildings with yr_built
                  2017-2024 (+10 m). Locators LOCATE; they never label.
  2 srs_floor     pure SRS over the whole city — the capture audit: change
                  found here that the locators missed measures (1-capture).
  3 stable_canopy both model masks canopy, not candidate
  4 stable_other  everything else
Allocation (N=1000): 550 / 100 / 150 / 200.
QC extras shuffled in, indistinguishable in the UI: 30 blind DUPLICATES
(differential-error measurement) + 30 BLUR CONTROLS (2024 chip vs 2024
blurred to 2016 sharpness — true answer no-change; catches sharpness-driven
false change, the one bias pairing cannot cancel).

Imagery: 2016_snoh_1ft_rgbi.tif (30.5 cm) vs 2024_snoh_3in_rgb.tif (7.6 cm,
local; the CoE 5 cm product is Drive-only — recorded in meta). Registration:
each epoch's chip window shifted by its measured median vector vs the 2020s
anchor (phase4/qc/coregistration.csv; 2016: dx .493 dy .011; 2024s: .017 -.02).
"""
import argparse
import csv
import http.server
import io
import json
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features as rfeat
import rasterio.warp
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.transform import xy as tf_xy

from phase4seg.names import clean_argv
from lake import BASE

QC_DIR = BASE / "phase4" / "qc"
IMG = Path(r"D:\edmonds-pipeline\Imagery")
MASKS = BASE / "phase4" / "masks"
CITY = BASE / "City Boundry" / "Edmonds Boundry.shp"
BLD = BASE / "buildings" / "buildings_canonical.gpkg"
CHIP_DIR = Path(r"D:\edmonds-pipeline\panel_a_chips")   # local NVMe (3.9)

EPSG = 26910
CELL = 2.0
# N=1250: at the drawn shares (cand 18.3%) 1000 gave power .75 < the .8 gate;
# 1250 restores power .81 / hw 1.03pp (verified 2026-09-04, paired_change_power).
N = {"cand_change": 700, "srs_floor": 120, "stable_canopy": 180, "stable_other": 250}
N_DUP, N_BLUR = 30, 30
SEED = 20260904
CHIP_M = 56.0                       # chip width on the ground
ORTHO16 = IMG / "2016_snoh_1ft_rgbi.tif"
ORTHO24 = IMG / "2024_snoh_3in_rgb.tif"
COREG = {"2016": (0.493, 0.011), "2024": (0.017, -0.02)}   # coregistration.csv medians
MASK16 = MASKS / "edmonds_canopy_mask_2016_fullext_sectors_v1.tif"
MASK24 = MASKS / "edmonds_canopy_mask_2024_citywide_rgb.tif"
CCAP_CANOPY = [9, 10, 11, 13, 16]   # phase4_accuracy_sample.py::CCAP_CANOPY


def _grid():
    import geopandas as gpd
    from affine import Affine
    city = gpd.read_file(CITY).to_crs(EPSG)
    minx, miny, maxx, maxy = city.total_bounds
    tf = Affine(CELL, 0, float(np.floor(minx)), 0, -CELL, float(np.ceil(maxy)))
    w = int(np.ceil((maxx - minx) / CELL)) + 1
    h = int(np.ceil((maxy - miny) / CELL)) + 1
    inside = rfeat.rasterize(((g, 1) for g in city.geometry), out_shape=(h, w),
                             transform=tf, fill=0, dtype="uint8").astype(bool)
    return tf, w, h, inside


def _warp_bool(path, tf, w, h, pred, resampling=Resampling.nearest):
    with rasterio.open(path) as src:
        with WarpedVRT(src, crs=f"EPSG:{EPSG}", transform=tf, width=w, height=h,
                       resampling=resampling) as v:
            return pred(v.read(1))


def step_design():
    import geopandas as gpd
    tf, w, h, inside = _grid()
    print(f"lattice {w}x{h} @ {CELL}m, city cells {inside.sum():,}")

    c16 = _warp_bool(IMG / "ccap_2016_hires_lc.tif", tf, w, h,
                     lambda a: np.isin(a, CCAP_CANOPY))
    c21 = _warp_bool(IMG / "ccap_2021_hires_lc.tif", tf, w, h,
                     lambda a: np.isin(a, CCAP_CANOPY))
    m16 = _warp_bool(MASK16, tf, w, h, lambda a: a == 1, Resampling.max)
    m24 = _warp_bool(MASK24, tf, w, h, lambda a: a == 1, Resampling.max)
    tall16 = _warp_bool(IMG / "lidar_chm2_2016_50cm.tif", tf, w, h,
                        lambda a: (a.astype(np.float32) - 1) * 0.2 >= 5.0,
                        Resampling.max)
    bld = gpd.read_file(BLD, layer="buildings").to_crs(EPSG)
    yb = bld["yr_built"].fillna(0).astype(float)
    new = bld[(yb >= 2017) & (yb <= 2024)]
    if len(new):
        newb = rfeat.rasterize(((g.buffer(10.0), 1) for g in new.geometry
                                if g is not None and not g.is_empty),
                               out_shape=(h, w), transform=tf, fill=0,
                               dtype="uint8").astype(bool)
    else:
        newb = np.zeros((h, w), bool)
    print(f"locators: ccap-flip {(c16 != c21).sum():,}  model-disagree "
          f"{(m16 != m24).sum():,}  tall16-now-clear {(tall16 & ~m24).sum():,}  "
          f"new-bldg {newb.sum():,}  (cells, pre-clip)")

    # Erode each raster locator to its 3x3 CORE: a candidate cell must sit
    # inside a >=6 m body of evidence. Kills the boundary-jitter flood — the
    # raw union covered 48.2% of the city (2026-09-04 first draw), which
    # collapses the design toward SRS (the power gate's FAIL case). Real
    # change (a crown, a clearing) survives 1-cell erosion at 2 m; 1-px mask
    # jitter (C3: most inter-delivery disagreement) does not.
    from scipy import ndimage as _ndi
    def _core(a):
        return _ndi.binary_erosion(a, structure=np.ones((3, 3), bool))
    # model-disagree gets a deeper (5x5, >=10 m) core: the two arms differ in
    # operating point, producing coherent disagreement BODIES (23.9% cand share
    # on the 3x3 draw). Crown-scale LOSS is independently caught by the lidar
    # locator, so the deeper cut costs gain-side capture only for <10 m patches
    # — audited by the SRS floor either way.
    def _core5(a):
        return _ndi.binary_erosion(a, structure=np.ones((5, 5), bool))
    cand = inside & (_core(c16 != c21) | _core5(m16 != m24)
                     | _core(tall16 & ~m24) | newb)
    stable_can = inside & m16 & m24 & ~cand
    stable_oth = inside & ~cand & ~stable_can
    strata = np.zeros((h, w), np.uint8)
    strata[cand], strata[stable_can], strata[stable_oth] = 1, 3, 4

    rng = np.random.default_rng(SEED)
    rows, meta_strata = [], {}
    areas = {1: int(cand.sum()), 2: int(inside.sum()),
             3: int(stable_can.sum()), 4: int(stable_oth.sum())}
    names = {1: "cand_change", 2: "srs_floor", 3: "stable_canopy", 4: "stable_other"}
    pid = 0
    for sid, nm in names.items():
        k = N[nm]
        pool = np.flatnonzero((inside if sid == 2 else (strata == sid)).ravel())
        pick = rng.choice(pool, size=k, replace=False)
        rr, cc = np.unravel_index(pick, (h, w))
        for i in range(k):
            pid += 1
            x, y = tf_xy(tf, int(rr[i]), int(cc[i]), offset="center")
            rows.append(dict(point_id=str(pid), stratum=sid, stratum_name=nm,
                             x=x, y=y, kind="live",
                             overlap_stratum=int(strata[rr[i], cc[i]]) if sid == 2 else sid))
        meta_strata[sid] = dict(name=nm, cells=areas[sid], sampled=k,
                                area_share=areas[sid] / areas[2])
    live = [r for r in rows if r["kind"] == "live"]
    for s in rng.choice(live, N_DUP, replace=False):
        pid += 1
        rows.append({**s, "point_id": str(pid), "kind": "dup",
                     "dup_of": s["point_id"]})
    stab = [r for r in live if r["stratum"] in (3, 4)]
    for s in rng.choice(stab, N_BLUR, replace=False):
        pid += 1
        rows.append({**s, "point_id": str(pid), "kind": "blur",
                     "dup_of": s["point_id"]})
    order = rng.permutation(len(rows))
    rows = [rows[i] for i in order]

    QC_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["point_id", "stratum", "stratum_name", "x", "y", "kind",
            "overlap_stratum", "dup_of"]
    with io.open(QC_DIR / "panel_a_points.csv", "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        for r in rows:
            wr.writerow({c: r.get(c, "") for c in cols})
    meta = dict(panel="A", interval="2016->2024", epsg=EPSG, cell=CELL,
                seed=SEED, n_live=sum(N.values()), n_dup=N_DUP, n_blur=N_BLUR,
                ortho16=ORTHO16.name, ortho24=ORTHO24.name,
                note24="local snoh 3in used; CoE 5cm is Drive-only",
                coreg_applied=COREG, chip_m=CHIP_M,
                mask16=MASK16.name, mask24=MASK24.name,
                strata=meta_strata)
    (QC_DIR / "panel_a_meta.json").write_text(json.dumps(meta, indent=2),
                                              encoding="utf-8")
    print(f"\n  PANEL A drawn: {sum(N.values())} live + {N_DUP} dup + {N_BLUR} blur "
          f"= {len(rows)} presentations")
    for sid, m in meta_strata.items():
        print(f"  {m['name']:<14} cells {m['cells']:>12,}  share "
              f"{100*m['area_share']:5.1f}%  pts {m['sampled']}")
    print(f"  wrote {QC_DIR / 'panel_a_points.csv'} + _meta.json")
    print("  Next: --step chips")


def _chip_png(src, x, y, dx, dy, blur_to_m=None):
    """Chip around (x,y) in EPSG:26910; (dx,dy) = this epoch's median
    registration vector vs the anchor, SUBTRACTED so both chips show the
    same physical ground."""
    from PIL import Image, ImageDraw
    with rasterio.open(src) as s:
        xs, ys = rasterio.warp.transform(f"EPSG:{EPSG}", s.crs, [x - dx], [y - dy])
        cx, cy = xs[0], ys[0]
        unit = s.crs.linear_units.lower()
        to_units = 3.280839895 if unit.startswith(("us", "foot", "ft")) else 1.0
        half = (CHIP_M / 2.0) * to_units
        win = from_bounds(cx - half, cy - half, cx + half, cy + half, s.transform)
        img = s.read((1, 2, 3), window=win, boundless=True, fill_value=0)
    a = np.transpose(img, (1, 2, 0)).astype(np.uint8)
    im = Image.fromarray(a)
    if blur_to_m:
        px_m = CHIP_M / max(im.width, 1)
        factor = max(int(round(blur_to_m / px_m)), 1)
        if factor > 1:
            im = im.resize((max(im.width // factor, 8), max(im.height // factor, 8)),
                           Image.BILINEAR).resize((im.width, im.height), Image.NEAREST)
    im = im.resize((420, 420), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    c = 210
    for seg in ((c - 14, c, c - 4, c), (c + 4, c, c + 14, c),
                (c, c - 14, c, c - 4), (c, c + 4, c, c + 14)):
        d.line(seg, fill=(255, 40, 40), width=2)
    return im


def step_chips():
    rows = list(csv.DictReader(io.open(QC_DIR / "panel_a_points.csv",
                                       encoding="utf-8", newline="")))
    CHIP_DIR.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(rows, 1):
        pid = r["point_id"]
        x, y = float(r["x"]), float(r["y"])
        if r["kind"] == "blur":
            left = _chip_png(ORTHO24, x, y, *COREG["2024"], blur_to_m=0.305)
            right = _chip_png(ORTHO24, x, y, *COREG["2024"])
        else:
            left = _chip_png(ORTHO16, x, y, *COREG["2016"])
            right = _chip_png(ORTHO24, x, y, *COREG["2024"])
        left.save(CHIP_DIR / f"{pid}_L.png")
        right.save(CHIP_DIR / f"{pid}_R.png")
        if i % 100 == 0 or i == len(rows):
            print(f"  chips {i}/{len(rows)}", flush=True)
    print(f"wrote {2*len(rows)} chips -> {CHIP_DIR}")
    print("Next: --step serve")


PAGE = """<!doctype html><meta charset=utf-8><title>Panel A</title>
<style>body{font-family:system-ui;margin:14px;background:#111;color:#eee;text-align:center}
img{width:420px;height:420px;border:1px solid #444}
#bar{margin:12px}button{font-size:17px;margin:4px;padding:9px 19px;cursor:pointer}
#prog{color:#aaa}</style>
<h3>Panel A - canopy AT THE CROSSHAIR: same, gain, or loss? <span id=prog></span></h3>
<div><img id=L> <img id=R></div>
<div id=bar>
<button onclick="lab('nochange')">same [s]</button>
<button onclick="lab('gain')">gain [g]</button>
<button onclick="lab('loss')">loss [l]</button>
<button onclick="lab('unsure')">unsure [u]</button>
<button onclick="lab('undo')">undo [z]</button>
</div>
<script>
let q=[],i=0;
async function load(){q=await (await fetch('/queue')).json();i=0;show();}
function show(){if(i>=q.length){document.body.innerHTML='<h2>DONE - run --step estimate</h2>';return}
 L.src='/chip/'+q[i]+'_L.png';R.src='/chip/'+q[i]+'_R.png';
 prog.textContent='('+(i+1)+'/'+q.length+')';}
async function lab(v){await fetch('/label?pid='+q[i]+'&label='+v);
 if(v=='undo'){i=Math.max(0,i-1)}else{i++};show();}
document.addEventListener('keydown',e=>{const k={s:'nochange',g:'gain',l:'loss',u:'unsure',z:'undo'}[e.key];if(k)lab(k)});
load();
</script>"""


def step_serve(port):
    labels_csv = QC_DIR / "panel_a_labels.csv"
    rows = list(csv.DictReader(io.open(QC_DIR / "panel_a_points.csv",
                                       encoding="utf-8", newline="")))
    done = set()
    if labels_csv.exists():
        for r in csv.DictReader(io.open(labels_csv, encoding="utf-8", newline="")):
            if r["label"] == "undo":
                done.discard(r["point_id"])
            else:
                done.add(r["point_id"])
    queue = [r["point_id"] for r in rows if r["point_id"] not in done]
    if not labels_csv.exists():
        labels_csv.write_text("point_id,label,ts\n", encoding="utf-8")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            import datetime
            import urllib.parse as up
            u = up.urlparse(self.path)
            if u.path == "/":
                b = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b)
            elif u.path == "/queue":
                b = json.dumps(queue).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b)
            elif u.path.startswith("/chip/"):
                p = CHIP_DIR / Path(u.path).name
                if p.exists() and p.suffix == ".png":
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.end_headers()
                    self.wfile.write(p.read_bytes())
                else:
                    self.send_error(404)
            elif u.path == "/label":
                qd = dict(up.parse_qsl(u.query))
                ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                with io.open(labels_csv, "a", encoding="utf-8", newline="") as f:
                    f.write(f'{qd["pid"]},{qd["label"]},{ts}\n')
                self.send_response(200)
                self.end_headers()
            else:
                self.send_error(404)

    print(f"{len(queue)} to label -> http://localhost:{port}   (Ctrl+C to stop; "
          f"labels append-only, resume anytime)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def step_estimate():
    import math
    meta = json.loads((QC_DIR / "panel_a_meta.json").read_text(encoding="utf-8"))
    pts = {r["point_id"]: r for r in csv.DictReader(
        io.open(QC_DIR / "panel_a_points.csv", encoding="utf-8", newline=""))}
    labels = {}
    for r in csv.DictReader(io.open(QC_DIR / "panel_a_labels.csv",
                                    encoding="utf-8", newline="")):
        if r["label"] == "undo":
            labels.pop(r["point_id"], None)
        else:
            labels[r["point_id"]] = r["label"]
    delta = {"loss": -1.0, "gain": 1.0, "nochange": 0.0}

    blur_bad = sum(1 for pid, lab in labels.items()
                   if pts[pid]["kind"] == "blur" and lab in ("gain", "loss"))
    blur_n = sum(1 for pid in labels if pts[pid]["kind"] == "blur")
    dup_dis = dup_n = 0
    for pid, lab in labels.items():
        if pts[pid]["kind"] == "dup":
            orig = labels.get(pts[pid]["dup_of"])
            if orig is not None and lab != "unsure" and orig != "unsure":
                dup_n += 1
                dup_dis += int(lab != orig)

    # paired stratified estimate on LIVE points; srs_floor points contribute
    # through the stratum they physically fall in (overlap_stratum).
    acc = {}
    for pid, lab in labels.items():
        p = pts[pid]
        if p["kind"] != "live" or lab not in delta:
            continue
        sid = int(p["overlap_stratum"]) if p["stratum_name"] == "srs_floor" \
            else int(p["stratum"])
        acc.setdefault(sid, []).append(delta[lab])
    net = var = 0.0
    tot_cells = meta["strata"]["2"]["cells"]
    for sid, vals in sorted(acc.items()):
        wgt = meta["strata"][str(sid)]["cells"] / tot_cells
        v = np.asarray(vals)
        net += wgt * v.mean()
        if len(v) > 1:
            var += wgt * wgt * v.var(ddof=1) / len(v)
    hw = 1.96 * math.sqrt(var)

    srs_out = [labels[pid] for pid, p in pts.items()
               if p["stratum_name"] == "srs_floor" and p["kind"] == "live"
               and int(p["overlap_stratum"]) != 1 and pid in labels]
    missed = sum(1 for lab in srs_out if lab in ("gain", "loss"))

    L = [f"PANEL A ESTIMATE - {meta['interval']}   (paired Olofsson)",
         f"  labelled {len([1 for pid in labels if pts[pid]['kind'] == 'live'])} "
         f"live / {meta['n_live']}   unsure "
         f"{sum(1 for pid, l in labels.items() if l == 'unsure')} (excluded)",
         f"  NET CHANGE {100*net:+.2f} pp of city area   95% CI +/-{100*hw:.2f} pp",
         f"  QC: duplicate disagreement {dup_dis}/{dup_n} "
         f"(differential error ~{dup_dis/max(2*dup_n, 1):.3f}; gate needs <=0.005)",
         f"      blur-control false change {blur_bad}/{blur_n} "
         f"(sharpness-asymmetry bias; pairing cannot cancel this one)",
         f"      capture audit: {missed}/{len(srs_out)} SRS points OUTSIDE the "
         f"locators showed change (0-1 supports capture ~0.9+)"]
    txt = "\n".join(L)
    print("\n" + txt)
    (QC_DIR / "panel_a_estimate.txt").write_text(txt, encoding="utf-8")
    print(f"\nwrote {QC_DIR / 'panel_a_estimate.txt'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True,
                    choices=["design", "chips", "serve", "estimate"])
    ap.add_argument("--port", type=int, default=8741)
    a = ap.parse_args(clean_argv())
    if a.step == "design":
        step_design()
    elif a.step == "chips":
        step_chips()
    elif a.step == "serve":
        step_serve(a.port)
    else:
        step_estimate()


if __name__ == "__main__":
    main()
