"""
Flicker Viewer — Edmonds Temporal Registration QA
==================================================
Produces two HTML flicker outputs for visual QA:

  Output 1 — all_years_flicker.html
    Single crop cycling through all years in sequence.

  Output 2 — pairwise_flicker.html
    One panel per year, each flickering between that year and 2020.

USAGE
-----
    %run flicker_viewer.py                          # image centre, 200m crop
    %run flicker_viewer.py --cx -13620800 --cy 6076200
    %run flicker_viewer.py --size 400
    %run flicker_viewer.py --preset downtown
    %run flicker_viewer.py --force                  # re-crop even if cached

OPEN IN COLAB
-------------
    # Download and open locally in your browser
    from google.colab import files
    files.download('/content/flicker_viewer/all_years_flicker.html')
    files.download('/content/flicker_viewer/pairwise_flicker.html')
"""

import argparse
import base64
import io
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.windows
from PIL import Image
from tqdm import tqdm

# ── Paths ─────────────────────────────────────────────────────────────────────

UPSAMPLE_DIR = Path("/content/drive/MyDrive/treedata/Full_Image/Pipeline Imagery/upsample")
OUT_DIR      = Path("/content/flicker_viewer")
CROP_DIR     = OUT_DIR / "crops"

# ── Imagery catalogue ─────────────────────────────────────────────────────────
# Matches upsample_imagery.py output exactly.
# CoE years keep original filename; others get _upsampled suffix.

YEARS = [
    {"key": 2013,    "file": "2013_king_rgb_upsampled.tif",   "label": "2013",        "source": "King County",     "season_risk": "higher"},
    {"key": 2015,    "file": "2015_king_rgb_upsampled.tif",   "label": "2015",        "source": "King County",     "season_risk": "higher"},
    {"key": 2016,    "file": "2016_snoh_rgbi_upsampled.tif",  "label": "2016",        "source": "Snohomish Co.",   "season_risk": "moderate"},
    {"key": 2017,    "file": "2017_coe_rgb.tif",              "label": "2017",        "source": "City of Edmonds", "season_risk": "moderate"},
    {"key": 2019,    "file": "2019_king_rgb_upsampled.tif",   "label": "2019",        "source": "King County",     "season_risk": "low"},
    {"key": "2019n", "file": "2019_naip_rgbi_upsampled.tif",  "label": "2019 (NAIP)", "source": "NAIP",            "season_risk": "low"},
    {"key": 2020,    "file": "2020_coe_rgb.tif",              "label": "2020",        "source": "City of Edmonds", "season_risk": "anchor"},
    {"key": 2021,    "file": "2021_king_rgb_upsampled.tif",   "label": "2021",        "source": "King County",     "season_risk": "moderate"},
    {"key": "2021s", "file": "2021_snoh_rgbi_upsampled.tif",  "label": "2021 (Snoh)", "source": "Snohomish Co.",   "season_risk": "moderate"},
    {"key": 2022,    "file": "2022_coe_rgb.tif",              "label": "2022",        "source": "City of Edmonds", "season_risk": "low"},
    {"key": "2022n", "file": "2022_naip_rgbi_upsampled.tif",  "label": "2022 (NAIP)", "source": "NAIP",            "season_risk": "low"},
    {"key": 2023,    "file": "2023_king_rgb_upsampled.tif",   "label": "2023",        "source": "King County",     "season_risk": "moderate"},
    {"key": 2024,    "file": "2024_coe_rgb.tif",              "label": "2024",        "source": "City of Edmonds", "season_risk": "low"},
]

# ── Location presets (EPSG:3857) ──────────────────────────────────────────────

PRESETS = {
    "downtown":    (-13620800, 6076200),
    "park":        (-13621500, 6077800),
    "residential": (-13619500, 6075000),
}

# ── Display settings ──────────────────────────────────────────────────────────

DEFAULT_SIZE_M  = 200
DISPLAY_PX      = 600
FLICKER_MS_ALL  = 300
FLICKER_MS_PAIR = 600


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def metres_per_pixel(transform) -> float:
    return abs(transform.a)


def centre_from_image(path: Path):
    with rasterio.open(path) as src:
        b = src.bounds
    return (b.left + b.right) / 2, (b.bottom + b.top) / 2


def crop_to_jpeg_bytes(path: Path, cx: float, cy: float,
                       size_m: float) -> bytes:
    """
    Crop size_m × size_m centred on (cx, cy).
    Uses bands 1-3 (RGB) only — 4-band RGBI files handled automatically.
    Applies 2-98 percentile stretch per channel.
    Saves as JPEG (much smaller than PNG — critical for keeping HTML under 50 MB).
    """
    with rasterio.open(path) as src:
        half = size_m / 2
        win  = rasterio.windows.from_bounds(
            cx - half, cy - half, cx + half, cy + half,
            src.transform)
        win  = win.intersection(
            rasterio.windows.Window(0, 0, src.width, src.height))
        data = src.read([1, 2, 3], window=win)   # (3, H, W)

    out = np.zeros_like(data, dtype=np.uint8)
    for i in range(3):
        band = data[i].astype(np.float32)
        valid = band[band > 0]
        p2, p98 = np.percentile(valid, [2, 98]) if valid.size > 0 else (0, 255)
        out[i] = np.clip(
            (band - p2) / max(p98 - p2, 1) * 255, 0, 255
        ).astype(np.uint8)

    img = Image.fromarray(np.transpose(out, (1, 2, 0)), mode="RGB")
    img = img.resize((DISPLAY_PX, DISPLAY_PX), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True)
    return buf.getvalue()


def to_data_uri(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()


# ─────────────────────────────────────────────────────────────────────────────
#  Crop all years
# ─────────────────────────────────────────────────────────────────────────────

def build_crops(cx: float, cy: float, size_m: float,
                force: bool = False) -> dict:
    """Returns dict: year_key -> data URI string."""
    CROP_DIR.mkdir(parents=True, exist_ok=True)
    data_uris = {}

    print(f"\n── Cropping {size_m:.0f}m × {size_m:.0f}m at "
          f"({cx:.0f}, {cy:.0f}) ──")

    missing = [e["file"] for e in YEARS
               if not (UPSAMPLE_DIR / e["file"]).exists()]
    if missing:
        print(f"  WARNING: {len(missing)} file(s) missing from upsample folder:")
        for f in missing:
            print(f"    {f}")

    for entry in tqdm(YEARS, desc="  Cropping"):
        key  = entry["key"]
        path = UPSAMPLE_DIR / entry["file"]
        cache = CROP_DIR / (
            entry["file"].replace(".tif", "")
            + f"_crop_{int(cx)}_{int(cy)}_{int(size_m)}.jpg"
        )

        if cache.exists() and not force:
            jpeg_bytes = cache.read_bytes()
            print(f"  {entry['label']:<16} cached  "
                  f"({cache.stat().st_size // 1024} KB)")
        elif not path.exists():
            print(f"  {entry['label']:<16} SKIP — not found: {entry['file']}")
            continue
        else:
            jpeg_bytes = crop_to_jpeg_bytes(path, cx, cy, size_m)
            cache.write_bytes(jpeg_bytes)
            print(f"  {entry['label']:<16} cropped "
                  f"({len(jpeg_bytes) // 1024} KB)")

        data_uris[key] = to_data_uri(jpeg_bytes)

    # Report estimated HTML size
    total_kb = sum(len(v) for v in data_uris.values()) // 1024
    print(f"  {len(data_uris)}/{len(YEARS)} years ready  "
          f"(~{total_kb // 1024} MB embedded)")
    return data_uris


# ─────────────────────────────────────────────────────────────────────────────
#  Shared CSS and JS constants
# ─────────────────────────────────────────────────────────────────────────────

SHARED_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f5f4f0; color: #1a1a18; padding: 24px; }
h1   { font-size: 17px; font-weight: 500; margin-bottom: 4px; }
.sub { font-size: 13px; color: #73726c; margin-bottom: 20px; }
button { font-size: 13px; padding: 6px 14px; border: 0.5px solid #b4b2a9;
         background: #fff; border-radius: 6px; cursor: pointer; }
button:hover  { background: #f1efe8; }
button.active { background: #1a1a18; color: #fff; border-color: #1a1a18; }
label { font-size: 13px; color: #73726c; }
input[type=range] { width: 140px; }
.badge { display:inline-block; font-size:11px; padding:2px 7px;
         border-radius:20px; font-weight:500; margin-left:6px;
         vertical-align:middle; }
.badge-anchor   { background:#E6F1FB; color:#185FA5; }
.badge-low      { background:#EAF3DE; color:#3B6D11; }
.badge-moderate { background:#FAEEDA; color:#854F0B; }
.badge-higher   { background:#FCEBEB; color:#A32D2D; }
"""

BADGE_LABELS_JS = """{anchor:'anchor',low:'leaf-on',
  moderate:'transitional',higher:'leaf-off risk'}"""


# ─────────────────────────────────────────────────────────────────────────────
#  Output 1 — All-years flicker
# ─────────────────────────────────────────────────────────────────────────────

def build_all_years_html(data_uris: dict, cx: float, cy: float,
                         size_m: float) -> str:
    frames = [e for e in YEARS if e["key"] in data_uris]

    uris_js    = "[" + ",".join(f'"{data_uris[e["key"]]}"' for e in frames) + "]"
    labels_js  = "[" + ",".join(f'"{e["label"]}"'          for e in frames) + "]"
    sources_js = "[" + ",".join(f'"{e["source"]}"'         for e in frames) + "]"
    risks_js   = "[" + ",".join(f'"{e["season_risk"]}"'    for e in frames) + "]"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>All-years flicker — Edmonds {int(size_m)}m</title>
<style>
{SHARED_CSS}
.viewer   {{ display:inline-block; position:relative; }}
#frame    {{ width:{DISPLAY_PX}px; height:{DISPLAY_PX}px; display:block;
             border:1px solid #d3d1c7; border-radius:6px; object-fit:cover; }}
.overlay  {{ position:absolute; top:10px; left:10px;
             background:rgba(0,0,0,.6); color:#fff;
             font-size:15px; font-weight:500; padding:5px 11px;
             border-radius:5px; pointer-events:none; }}
.controls {{ margin-top:14px; display:flex; align-items:center;
             gap:12px; flex-wrap:wrap; }}
.filmstrip {{ display:flex; gap:5px; margin-top:14px; flex-wrap:wrap; }}
.thumb {{ width:54px; height:54px; border-radius:4px; cursor:pointer;
          border:2px solid transparent; opacity:.65; transition:all .15s;
          object-fit:cover; }}
.thumb:hover  {{ opacity:1; }}
.thumb.active {{ border-color:#1a1a18; opacity:1; }}
.prog  {{ display:flex; gap:4px; margin-top:10px; flex-wrap:wrap;
          align-items:center; }}
.dot   {{ width:9px; height:9px; border-radius:50%;
          background:#d3d1c7; cursor:pointer; transition:background .15s; }}
.dot.active {{ background:#1a1a18; }}
</style>
</head>
<body>
<h1>All-years flicker — {int(size_m)} × {int(size_m)} m</h1>
<p class="sub">Centre ({cx:.0f}, {cy:.0f}) EPSG:3857 &nbsp;·&nbsp;
{len(frames)} years &nbsp;·&nbsp; click thumbnail to jump · drag slider to change speed</p>

<div class="viewer">
  <img id="frame" src="" alt="imagery frame">
  <div class="overlay">
    <span id="lbl-year">—</span>
    <span id="lbl-src" style="font-size:11px;font-weight:400;
          margin-left:7px;opacity:.8"></span>
    <span id="lbl-badge" class="badge"></span>
  </div>
</div>

<div class="controls">
  <button id="btn-play" class="active" onclick="togglePlay()">Pause</button>
  <label>Speed
    <input type="range" id="spd" min="80" max="1500" step="40"
           value="{FLICKER_MS_ALL}" oninput="setSpeed(+this.value)">
  </label>
  <span id="spd-lbl" style="font-size:13px;color:#73726c">
    {FLICKER_MS_ALL} ms/frame</span>
  <button onclick="step(-1)">&#8592; prev</button>
  <button onclick="step(1)">next &#8594;</button>
</div>

<div class="prog"      id="prog"></div>
<div class="filmstrip" id="film"></div>

<script>
const URIS=    {uris_js};
const LABELS=  {labels_js};
const SOURCES= {sources_js};
const RISKS=   {risks_js};
const BL=      {BADGE_LABELS_JS};
const N= URIS.length;
let cur=0, playing=true, iv=null, speed={FLICKER_MS_ALL};

const imgEl= document.getElementById('frame');
const lblY=  document.getElementById('lbl-year');
const lblS=  document.getElementById('lbl-src');
const lblB=  document.getElementById('lbl-badge');

function show(i){{
  cur=(i+N)%N;
  imgEl.src=URIS[cur];
  lblY.textContent=LABELS[cur];
  lblS.textContent=SOURCES[cur];
  const r=RISKS[cur];
  lblB.textContent=BL[r]||r;
  lblB.className='badge badge-'+r;
  document.querySelectorAll('.dot').forEach((d,j)=>
    d.classList.toggle('active',j===cur));
  document.querySelectorAll('.thumb').forEach((t,j)=>
    t.classList.toggle('active',j===cur));
}}
function step(d){{show(cur+d);}}
function togglePlay(){{
  playing=!playing;
  document.getElementById('btn-play').textContent=playing?'Pause':'Play';
  document.getElementById('btn-play').classList.toggle('active',playing);
  if(playing)startIv(); else clearInterval(iv);
}}
function setSpeed(ms){{
  speed=ms;
  document.getElementById('spd-lbl').textContent=ms+' ms/frame';
  if(playing){{clearInterval(iv);startIv();}}
}}
function startIv(){{clearInterval(iv);iv=setInterval(()=>show(cur+1),speed);}}

for(let i=0;i<N;i++){{
  const d=document.createElement('div');
  d.className='dot'+(i===0?' active':'');
  d.onclick=()=>show(i);
  document.getElementById('prog').appendChild(d);
}}
URIS.forEach((uri,i)=>{{
  const img=document.createElement('img');
  img.src=uri; img.className='thumb'+(i===0?' active':'');
  img.title=LABELS[i]; img.onclick=()=>{{show(i);if(playing)togglePlay();}};
  document.getElementById('film').appendChild(img);
}});

show(0); startIv();
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Output 2 — Pairwise vs 2020 flicker
# ─────────────────────────────────────────────────────────────────────────────

def build_pairwise_html(data_uris: dict, cx: float, cy: float,
                        size_m: float) -> str:
    anchor_uri = data_uris.get(2020)
    if anchor_uri is None:
        raise ValueError("2020 anchor crop not found in data_uris")

    others = [e for e in YEARS if e["key"] != 2020 and e["key"] in data_uris]

    panels_js = "[" + ",".join(
        f'{{label:"{e["label"]}",source:"{e["source"]}",'
        f'risk:"{e["season_risk"]}",uri:"{data_uris[e["key"]]}"}}' 
        for e in others
    ) + "]"

    thumb = 220

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pairwise flicker vs 2020 — Edmonds</title>
<style>
{SHARED_CSS}
.grid  {{ display:flex; flex-wrap:wrap; gap:16px; }}
.panel {{ background:#fff; border:0.5px solid #d3d1c7; border-radius:8px;
          padding:10px; width:{thumb+20}px; }}
.ptitle {{ font-size:12px; font-weight:500; margin-bottom:6px;
           display:flex; align-items:center; gap:6px; flex-wrap:wrap; }}
.viewer {{ position:relative; width:{thumb}px; height:{thumb}px; }}
.viewer img {{ width:{thumb}px; height:{thumb}px; display:block;
               border-radius:4px; border:1px solid #e8e6e0;
               object-fit:cover; }}
.flbl {{ position:absolute; bottom:5px; left:5px;
         background:rgba(0,0,0,.6); color:#fff;
         font-size:11px; padding:2px 6px; border-radius:3px;
         pointer-events:none; }}
.pctrl {{ display:flex; align-items:center; gap:6px; margin-top:8px; }}
.pctrl button {{ font-size:11px; padding:3px 8px; }}
.gctrls {{ margin-bottom:20px; display:flex; align-items:center;
           gap:12px; flex-wrap:wrap; }}
</style>
</head>
<body>
<h1>Pairwise flicker — each year vs 2020</h1>
<p class="sub">Centre ({cx:.0f}, {cy:.0f}) EPSG:3857 &nbsp;·&nbsp;
{int(size_m)} × {int(size_m)} m &nbsp;·&nbsp; {len(others)} comparisons</p>

<div class="gctrls">
  <button id="g-play" class="active" onclick="globalToggle()">Pause all</button>
  <label>Speed
    <input type="range" id="g-spd" min="100" max="2000" step="100"
           value="{FLICKER_MS_PAIR}" oninput="globalSpeed(+this.value)">
  </label>
  <span id="g-spd-lbl" style="font-size:13px;color:#73726c">
    {FLICKER_MS_PAIR} ms/frame</span>
</div>

<div class="grid" id="grid"></div>

<script>
const ANCHOR= "{anchor_uri}";
const PANELS= {panels_js};
const BL=    {BADGE_LABELS_JS};
let gPlaying=true, gSpeed={FLICKER_MS_PAIR};
const states=[];

function showFrame(idx,f){{
  states[idx].cur=f;
  const p=PANELS[idx];
  document.getElementById('img-'+idx).src= f===0?ANCHOR:p.uri;
  document.getElementById('flbl-'+idx).textContent= f===0?'2020':p.label;
}}

function buildPanel(p,idx){{
  const div=document.createElement('div');
  div.className='panel';
  div.innerHTML=`
    <div class="ptitle">
      ${{p.label}}
      <span class="badge badge-${{p.risk}}">${{BL[p.risk]||p.risk}}</span>
    </div>
    <div class="viewer">
      <img id="img-${{idx}}" src="${{ANCHOR}}" alt="${{p.label}} vs 2020">
      <div class="flbl" id="flbl-${{idx}}">2020</div>
    </div>
    <div class="pctrl">
      <button id="btn-${{idx}}" class="active"
              onclick="togglePanel(${{idx}})">Pause</button>
      <span style="font-size:11px;color:#73726c">${{p.source}}</span>
    </div>`;
  document.getElementById('grid').appendChild(div);
  const state={{cur:0,playing:true,iv:null}};
  states.push(state);
  state.iv=setInterval(()=>showFrame(idx,states[idx].cur===0?1:0),gSpeed);
}}

PANELS.forEach(buildPanel);

function togglePanel(idx){{
  const s=states[idx];
  s.playing=!s.playing;
  const btn=document.getElementById('btn-'+idx);
  btn.textContent=s.playing?'Pause':'Play';
  btn.classList.toggle('active',s.playing);
  clearInterval(s.iv);
  if(s.playing)
    s.iv=setInterval(()=>showFrame(idx,states[idx].cur===0?1:0),gSpeed);
}}

function globalToggle(){{
  gPlaying=!gPlaying;
  document.getElementById('g-play').textContent=
    gPlaying?'Pause all':'Play all';
  document.getElementById('g-play').classList.toggle('active',gPlaying);
  states.forEach((s,i)=>{{
    clearInterval(s.iv);
    s.playing=gPlaying;
    const btn=document.getElementById('btn-'+i);
    if(btn){{btn.textContent=s.playing?'Pause':'Play';
             btn.classList.toggle('active',s.playing);}}
    if(s.playing)
      s.iv=setInterval(()=>showFrame(i,states[i].cur===0?1:0),gSpeed);
  }});
}}

function globalSpeed(ms){{
  gSpeed=ms;
  document.getElementById('g-spd-lbl').textContent=ms+' ms/frame';
  states.forEach((s,i)=>{{
    clearInterval(s.iv);
    if(s.playing)
      s.iv=setInterval(()=>showFrame(i,states[i].cur===0?1:0),gSpeed);
  }});
}}
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Flicker viewer for upsampled imagery QA")
    parser.add_argument("--cx",     type=float, default=None)
    parser.add_argument("--cy",     type=float, default=None)
    parser.add_argument("--size",   type=float, default=DEFAULT_SIZE_M)
    parser.add_argument("--preset", type=str,   default=None)
    parser.add_argument("--force",  action="store_true")

    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Resolve centre ─────────────────────────────────────────
    if args.cx is not None and args.cy is not None:
        cx, cy = args.cx, args.cy
        print(f"  Centre: ({cx:.0f}, {cy:.0f}) from --cx/--cy")
    elif args.preset and args.preset in PRESETS:
        cx, cy = PRESETS[args.preset]
        print(f"  Centre: ({cx:.0f}, {cy:.0f}) preset '{args.preset}'")
    else:
        ref = UPSAMPLE_DIR / "2020_coe_rgb.tif"
        cx, cy = centre_from_image(ref)
        print(f"  Centre: ({cx:.0f}, {cy:.0f}) image centre")

    size_m = args.size
    print(f"  Crop  : {size_m:.0f} × {size_m:.0f} m")

    # ── Crop ───────────────────────────────────────────────────
    data_uris = build_crops(cx, cy, size_m, force=args.force)
    if len(data_uris) < 2:
        print("  ERROR: fewer than 2 years cropped — check UPSAMPLE_DIR")
        return

    # ── Build HTML ─────────────────────────────────────────────
    print("\n── Building all-years flicker ──")
    out1 = OUT_DIR / "all_years_flicker.html"
    out1.write_text(
        build_all_years_html(data_uris, cx, cy, size_m), encoding="utf-8")
    print(f"  ✓ {out1.name}  ({out1.stat().st_size // 1024} KB)")

    print("\n── Building pairwise flicker ──")
    out2 = OUT_DIR / "pairwise_flicker.html"
    out2.write_text(
        build_pairwise_html(data_uris, cx, cy, size_m), encoding="utf-8")
    print(f"  ✓ {out2.name}  ({out2.stat().st_size // 1024} KB)")

    print(f"""
============================================================
  DONE — {len(data_uris)}/{len(YEARS)} years
  Crop: {size_m:.0f}m × {size_m:.0f}m at ({cx:.0f}, {cy:.0f})

  Download and open locally in your browser:
    from google.colab import files
    files.download('/content/flicker_viewer/all_years_flicker.html')
    files.download('/content/flicker_viewer/pairwise_flicker.html')

  Try a different location:
    %run flicker_viewer.py --cx -13620800 --cy 6076200
    %run flicker_viewer.py --preset downtown
    %run flicker_viewer.py --size 400 --force
============================================================""")


if __name__ == "__main__":
    main()