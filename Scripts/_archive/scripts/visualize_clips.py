"""
build_clip_viewer.py — Interactive before/after clip alignment viewer
======================================================================
Builds a self-contained HTML viewer with side-by-side BEFORE/AFTER panels.
Each year gets a tile. Clicking flips both panels simultaneously between
the year imagery and the 2020 base — so you see unregistered vs registered
alignment quality side by side.

USAGE (Colab cell):
    %run /content/drive/MyDrive/treedata/Scripts/build_clip_viewer.py

OUTPUT:
    /content/drive/MyDrive/treedata/clips/clip_viewer.html
    Download and open in any browser — fully self-contained.

CONTROLS:
    Click tile        — flip that tile (both panels) between year / 2020
    Space             — flip all tiles simultaneously
    Arrow left/right  — step through tiles one at a time
    Auto-flip button  — cycle automatically at set speed
    Speed slider      — 100–1200 ms flip interval
    Show all 2020     — reset all to reference
    Show all years    — reset all to year imagery
"""

import sys, base64, json
from pathlib import Path
from io import BytesIO
import numpy as np
from PIL import Image

DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
from pipeline_config import DRIVE_BASE, CLIPS_DIR, IMAGERY_DIR
REGISTERED_DIR = CLIPS_DIR / "registered"
OUTPUT_HTML    = CLIPS_DIR / "clip_viewer.html"

REFERENCE_YEAR = 2020
TARGET_YEARS   = [2013, 2015, 2017, 2019, 2021, 2022, 2023, 2024]

SOURCE = {
    2013:"King Co.", 2015:"King Co.", 2017:"Edmonds",
    2019:"King Co.", 2020:"Edmonds", 2021:"King Co.",
    2022:"Edmonds",  2023:"King Co.", 2024:"Edmonds",
}
RMSE = {
    2013:0.2930, 2015:0.2793, 2017:0.2570, 2019:0.2841,
    2021:0.2896, 2022:0.3103, 2023:0.2562, 2024:0.3559,
}
PAIRS = {
    2013:946, 2015:1046, 2017:658,  2019:1027,
    2021:750, 2022:458,  2023:1264, 2024:168,
}

THUMB_PX   = 380
PATCH_HALF = 600


def extract_thumb(path, half, size):
    import rasterio, rasterio.windows
    with rasterio.open(path) as src:
        cx = src.width  // 2
        cy = src.height // 2
        col_off = max(0, min(cx - half, src.width  - 2*half))
        row_off = max(0, min(cy - half, src.height - 2*half))
        win  = rasterio.windows.Window(col_off, row_off, 2*half, 2*half)
        data = src.read(window=win)
    rgb = np.stack([data[0], data[1], data[2]], axis=-1).astype(np.float32) \
          if data.shape[0] >= 3 \
          else np.stack([data[0]]*3, axis=-1).astype(np.float32)
    lo, hi = np.percentile(rgb, (1, 99))
    rgb = np.clip((rgb-lo)/(hi-lo)*255, 0, 255) if hi > lo else rgb*0
    return Image.fromarray(rgb.astype(np.uint8)).resize((size, size), Image.LANCZOS)


def to_b64(img):
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def run():
    print("=" * 60)
    print("  BUILD CLIP VIEWER — before / after")
    print("=" * 60)

    ref_clip = CLIPS_DIR / f"{REFERENCE_YEAR}_edmonds_clip.tif"
    if not ref_clip.exists():
        print(f"  Reference clip not found: {ref_clip}"); return

    print(f"  Extracting 2020 reference...", end=" ", flush=True)
    ref_b64 = to_b64(extract_thumb(ref_clip, PATCH_HALF, THUMB_PX))
    print(f"done  ({len(ref_b64)//1024} KB)")

    tiles = []
    for year in TARGET_YEARS:
        raw_clip = CLIPS_DIR      / f"{year}_edmonds_clip.tif"
        reg_clip = REGISTERED_DIR / f"{year}_clip_registered.tif"

        if not raw_clip.exists():
            print(f"  {year}: raw clip not found — skipping"); continue
        if not reg_clip.exists():
            print(f"  {year}: registered clip not found — skipping"); continue

        print(f"  {year}: extracting raw...",        end=" ", flush=True)
        raw_b64 = to_b64(extract_thumb(raw_clip, PATCH_HALF, THUMB_PX))
        print(f"done  extracting registered...", end=" ", flush=True)
        reg_b64 = to_b64(extract_thumb(reg_clip, PATCH_HALF, THUMB_PX))
        print(f"done")

        tiles.append({
            "year":    year,
            "source":  SOURCE.get(year, ""),
            "rmse":    RMSE.get(year, 0),
            "pairs":   PAIRS.get(year, 0),
            "raw_b64": raw_b64,
            "reg_b64": reg_b64,
        })

    if not tiles:
        print("  No clips found."); return

    tiles_json = json.dumps(tiles)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Clip alignment viewer — Edmonds</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: system-ui, -apple-system, sans-serif;
  background: #0e0e12; color: #d8d8d8; padding: 20px;
}}
h1 {{ font-size: 15px; font-weight: 500; color: #bbb; margin-bottom: 3px; }}
.sub {{ font-size: 12px; color: #555; margin-bottom: 16px; }}
.controls {{
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 16px; flex-wrap: wrap;
}}
.controls label {{ font-size: 12px; color: #666; }}
input[type=range] {{ width: 140px; accent-color: #3d9e6e; }}
.controls span {{ font-size: 12px; color: #888; min-width: 50px; }}
button {{
  background: transparent; border: 0.5px solid #383840;
  color: #aaa; padding: 5px 12px; border-radius: 6px;
  font-size: 12px; cursor: pointer;
}}
button:hover {{ background: #1a1a22; color: #ddd; }}
button.active {{ border-color: #3d9e6e; color: #3d9e6e; }}

.grid {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}}

.card {{
  border-radius: 10px; overflow: hidden;
  border: 1.5px solid #22222c;
  cursor: pointer; user-select: none;
}}
.card:focus {{ outline: 2px solid #3d9e6e; outline-offset: 2px; }}
.card.showing-base .panel-left  {{ border-color: #1a4060; }}
.card.showing-base .panel-right {{ border-color: #1a4060; }}
.card.showing-year .panel-left  {{ border-color: #2a5c8a; }}
.card.showing-year .panel-right {{ border-color: #1a4a28; }}

.card-header {{
  background: #14141c;
  padding: 7px 12px;
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 0.5px solid #22222c;
}}
.year-src {{ display: flex; align-items: baseline; gap: 8px; }}
.year {{ font-size: 15px; font-weight: 500; color: #eee; }}
.src  {{ font-size: 11px; color: #666; }}
.badge {{
  font-size: 10px; padding: 2px 7px; border-radius: 4px; font-weight: 500;
  background: #0d3320; color: #4ec98a;
}}
.rmse-txt {{ font-size: 11px; color: #555; }}

.panels {{
  display: grid; grid-template-columns: 1fr 6px 1fr;
}}
.panel {{ position: relative; overflow: hidden; }}
.panel img {{
  display: block; width: 100%; aspect-ratio: 1;
  transition: opacity 0.1s ease;
}}
.panel-label {{
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 4px 8px;
  background: rgba(8,8,14,0.80);
  font-size: 10px;
  display: flex; justify-content: space-between;
}}
.lbl-before {{ color: #c06040; }}
.lbl-after  {{ color: #40c080; }}
.lbl-ref    {{ color: #6090c0; }}

.divider {{
  background: #1a1a22;
  display: flex; align-items: center; justify-content: center;
}}
.divider-line {{
  width: 1px; height: 80%; background: #333340;
}}

.card-footer {{
  background: #14141c;
  padding: 5px 12px;
  font-size: 10px; color: #444;
  border-top: 0.5px solid #1e1e28;
  display: flex; justify-content: space-between;
}}
.state-dot {{
  display: inline-block; width: 6px; height: 6px;
  border-radius: 50%; margin-right: 4px; vertical-align: middle;
}}

.legend {{
  display: flex; gap: 20px; margin-top: 14px; font-size: 11px; color: #555;
}}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.ldot {{ width: 8px; height: 8px; border-radius: 50%; }}
</style>
</head>
<body>

<h1>Clip alignment viewer — Edmonds temporal pipeline</h1>
<p class="sub">Click tile (or Space / ← →) to flip between year and 2020 reference. Left = unregistered · Right = registered.</p>

<div class="controls">
  <label>Speed</label>
  <input type="range" id="speed" min="100" max="1500" step="50" value="600">
  <span id="speed-out">600 ms</span>
  <button id="btn-auto" onclick="toggleAuto()">Auto-flip</button>
  <button onclick="showAll('base')">All → 2020</button>
  <button onclick="showAll('year')">All → year</button>
</div>

<div class="grid" id="grid"></div>

<div class="legend">
  <div class="legend-item">
    <div class="ldot" style="background:#2a5c8a"></div>
    <span>Left border: showing unregistered year</span>
  </div>
  <div class="legend-item">
    <div class="ldot" style="background:#1a4a28"></div>
    <span>Right border: showing registered year</span>
  </div>
  <div class="legend-item">
    <div class="ldot" style="background:#4ec98a"></div>
    <span>Showing 2020 reference</span>
  </div>
</div>

<script>
const REF   = "data:image/jpeg;base64,{ref_b64}";
const TILES = {tiles_json};
const state = {{}};
let autoTimer = null, autoIdx = 0, autoOn = false;

function build() {{
  const grid = document.getElementById("grid");
  TILES.forEach((t, i) => {{
    state[i] = "year";
    const card = document.createElement("div");
    card.className = "card showing-year";
    card.tabIndex  = 0;
    card.dataset.idx = i;
    card.innerHTML = `
      <div class="card-header">
        <div class="year-src">
          <span class="year">${{t.year}}</span>
          <span class="src">${{t.source}}</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span class="rmse-txt">RMSE ${{t.rmse.toFixed(3)}} m &middot; ${{t.pairs.toLocaleString()}} pairs</span>
          <span class="badge">PASS</span>
        </div>
      </div>
      <div class="panels">
        <div class="panel panel-left" id="pl-${{i}}">
          <img id="img-raw-${{i}}" src="data:image/jpeg;base64,${{t.raw_b64}}" alt="before">
          <div class="panel-label">
            <span class="lbl-before" id="lbl-raw-${{i}}">before</span>
            <span style="color:#444">unregistered</span>
          </div>
        </div>
        <div class="divider"><div class="divider-line"></div></div>
        <div class="panel panel-right" id="pr-${{i}}">
          <img id="img-reg-${{i}}" src="data:image/jpeg;base64,${{t.reg_b64}}" alt="after">
          <div class="panel-label">
            <span class="lbl-after" id="lbl-reg-${{i}}">after</span>
            <span style="color:#444">registered</span>
          </div>
        </div>
      </div>
      <div class="card-footer">
        <span>
          <span class="state-dot" id="dot-${{i}}" style="background:#4ec98a"></span>
          <span id="state-txt-${{i}}">showing year ${{t.year}}</span>
        </span>
        <span>click to compare with 2020</span>
      </div>`;
    card.addEventListener("click",   () => flip(i));
    card.addEventListener("keydown", e => {{
      if (e.key === " " || e.key === "Enter") {{ e.preventDefault(); flip(i); }}
    }});
    grid.appendChild(card);
  }});
}}

function flip(i) {{
  const t        = TILES[i];
  const card     = document.querySelector(`[data-idx="${{i}}"]`);
  const imgRaw   = document.getElementById(`img-raw-${{i}}`);
  const imgReg   = document.getElementById(`img-reg-${{i}}`);
  const lblRaw   = document.getElementById(`lbl-raw-${{i}}`);
  const lblReg   = document.getElementById(`lbl-reg-${{i}}`);
  const dot      = document.getElementById(`dot-${{i}}`);
  const stxt     = document.getElementById(`state-txt-${{i}}`);
  const isYear   = state[i] === "year";

  imgRaw.style.opacity = "0.25";
  imgReg.style.opacity = "0.25";

  setTimeout(() => {{
    if (isYear) {{
      imgRaw.src = REF;
      imgReg.src = REF;
      state[i]   = "base";
      card.className = "card showing-base";
      lblRaw.textContent = "2020";
      lblReg.textContent = "2020";
      lblRaw.className = "lbl-ref";
      lblReg.className = "lbl-ref";
      dot.style.background  = "#4488bb";
      stxt.textContent = "showing 2020 reference";
    }} else {{
      imgRaw.src = `data:image/jpeg;base64,${{t.raw_b64}}`;
      imgReg.src = `data:image/jpeg;base64,${{t.reg_b64}}`;
      state[i]   = "year";
      card.className = "card showing-year";
      lblRaw.textContent = "before";
      lblReg.textContent = "after";
      lblRaw.className = "lbl-before";
      lblReg.className = "lbl-after";
      dot.style.background  = "#4ec98a";
      stxt.textContent = `showing year ${{t.year}}`;
    }}
    imgRaw.style.opacity = "1";
    imgReg.style.opacity = "1";
  }}, 80);
}}

function showAll(which) {{
  TILES.forEach((_, i) => {{ if (state[i] !== which) flip(i); }});
}}

function toggleAuto() {{
  autoOn = !autoOn;
  const btn = document.getElementById("btn-auto");
  btn.classList.toggle("active", autoOn);
  btn.textContent = autoOn ? "Stop" : "Auto-flip";
  if (autoOn) tick(); else clearTimeout(autoTimer);
}}

function tick() {{
  if (!autoOn) return;
  flip(autoIdx % TILES.length);
  autoIdx++;
  autoTimer = setTimeout(tick, +document.getElementById("speed").value);
}}

document.getElementById("speed").addEventListener("input", function() {{
  document.getElementById("speed-out").textContent = this.value + " ms";
}});

document.addEventListener("keydown", e => {{
  if (e.target.dataset.idx !== undefined) return;
  if (e.key === " ") {{ e.preventDefault(); TILES.forEach((_, i) => flip(i)); }}
  if (e.key === "ArrowRight") {{ autoIdx++; flip(autoIdx % TILES.length); }}
  if (e.key === "ArrowLeft")  {{ autoIdx = (autoIdx - 1 + TILES.length) % TILES.length; flip(autoIdx); }}
}});

build();
</script>
</body>
</html>"""

    OUTPUT_HTML.write_text(html)
    size_kb = OUTPUT_HTML.stat().st_size // 1024
    print(f"\n  Written: {OUTPUT_HTML.name}  ({size_kb:,} KB)")
    print(f"  {len(tiles)} year tiles  ·  3 images each (raw, registered, reference)")
    print(f"\n  Download clip_viewer.html and open in any browser.")


if __name__ == "__main__":
    sys.argv = sys.argv[:1]
    run()