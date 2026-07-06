"""
build_clip_viewer.py — Interactive clip alignment viewer
=========================================================
Extracts patch thumbnails from all clip files and builds a
self-contained HTML viewer where each year tile flips between
the registered year and 2020 base on click or spacebar.

USAGE (Colab cell):
    %run /content/drive/MyDrive/treedata/Scripts/build_clip_viewer.py

OUTPUT:
    /content/drive/MyDrive/treedata/clips/clip_viewer.html
    Open this file in any browser — no server needed.
"""

import sys, base64, json
from pathlib import Path
from io import BytesIO
import numpy as np
from PIL import Image

DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
from pipeline_config import DRIVE_BASE, CLIPS_DIR
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
    2013:946, 2015:1046, 2017:658, 2019:1027,
    2021:750, 2022:458,  2023:1264, 2024:168,
}

THUMB_PX   = 400   # thumbnail size in output
PATCH_HALF = 600   # pixels to extract from clip centre


def extract_thumb(path, half, size):
    """Extract centre patch from a clip and return as PIL Image."""
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


def img_to_b64(img):
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def run():
    print("=" * 60)
    print("  BUILD CLIP VIEWER")
    print("=" * 60)

    ref_clip = CLIPS_DIR / f"{REFERENCE_YEAR}_edmonds_clip.tif"
    if not ref_clip.exists():
        print(f"  Reference clip not found: {ref_clip}"); return

    print(f"  Extracting reference ({REFERENCE_YEAR})...", end=" ", flush=True)
    ref_img = extract_thumb(ref_clip, PATCH_HALF, THUMB_PX)
    ref_b64 = img_to_b64(ref_img)
    print("done")

    tiles = []
    for year in TARGET_YEARS:
        tgt_path = REGISTERED_DIR / f"{year}_clip_registered.tif"
        if not tgt_path.exists():
            print(f"  {year}: not found — skipping")
            continue
        print(f"  Extracting {year}...", end=" ", flush=True)
        tgt_img = extract_thumb(tgt_path, PATCH_HALF, THUMB_PX)
        tgt_b64 = img_to_b64(tgt_img)
        tiles.append({
            "year":   year,
            "source": SOURCE.get(year, ""),
            "rmse":   RMSE.get(year, 0),
            "pairs":  PAIRS.get(year, 0),
            "b64":    tgt_b64,
        })
        print(f"done  ({len(tgt_b64)//1024} KB)")

    if not tiles:
        print("  No registered clips found."); return

    tiles_json = json.dumps(tiles)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Clip alignment viewer — Edmonds temporal pipeline</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: system-ui, -apple-system, sans-serif;
    background: #0e0e12;
    color: #e0e0e0;
    padding: 24px;
  }}
  h1 {{ font-size: 16px; font-weight: 500; color: #ccc; margin-bottom: 4px; }}
  .subtitle {{ font-size: 13px; color: #666; margin-bottom: 20px; }}
  .controls {{
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 20px; flex-wrap: wrap;
  }}
  .controls label {{ font-size: 13px; color: #888; }}
  .controls input[type=range] {{
    width: 180px; accent-color: #3d9e6e;
  }}
  .controls span {{ font-size: 13px; color: #aaa; min-width: 36px; }}
  button {{
    background: transparent;
    border: 0.5px solid #444;
    color: #ccc;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
  }}
  button:hover {{ background: #1e1e26; }}
  button.active {{ border-color: #3d9e6e; color: #3d9e6e; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }}
  .tile {{
    border-radius: 8px;
    overflow: hidden;
    border: 1.5px solid #2a2a32;
    cursor: pointer;
    position: relative;
    user-select: none;
  }}
  .tile:focus {{ outline: 2px solid #3d9e6e; outline-offset: 2px; }}
  .tile.showing-base {{ border-color: #2a5c8a; }}
  .tile.flipping {{ border-color: #3d9e6e; }}
  .tile-img {{
    display: block; width: 100%; aspect-ratio: 1;
    transition: opacity 0.12s ease;
  }}
  .tile-header {{
    position: absolute; top: 0; left: 0; right: 0;
    padding: 6px 10px;
    display: flex; justify-content: space-between; align-items: center;
    background: rgba(10,10,16,0.82);
  }}
  .year-label {{ font-size: 15px; font-weight: 500; color: #fff; }}
  .source-label {{ font-size: 11px; color: #888; }}
  .badge {{
    font-size: 11px; padding: 2px 7px; border-radius: 4px;
    font-weight: 500;
  }}
  .badge-pass {{ background: #0d3320; color: #4ec98a; }}
  .badge-base {{ background: #0d2040; color: #5599cc; }}
  .tile-footer {{
    position: absolute; bottom: 0; left: 0; right: 0;
    padding: 5px 10px;
    background: rgba(10,10,16,0.82);
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11px; color: #888;
  }}
  .rmse-val {{ color: #aaa; }}
  .state-indicator {{
    font-size: 11px; color: #3d9e6e;
    opacity: 0; transition: opacity 0.2s;
  }}
  .tile.showing-base .state-indicator {{ color: #5599cc; opacity: 1; }}
  .tile.flipping .state-indicator {{ opacity: 1; }}
  .legend {{
    display: flex; gap: 20px; margin-top: 16px;
    font-size: 12px; color: #666;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot {{
    width: 10px; height: 10px; border-radius: 50%;
  }}
</style>
</head>
<body>

<h1>Clip alignment viewer — Edmonds temporal pipeline</h1>
<p class="subtitle">
  Click any tile (or press Space / ← →) to flip between 2020 reference and registered year.
  All clips: 1.6 km × 1.6 km study area patch · affine registration · 8/8 passed.
</p>

<div class="controls">
  <label>Flip speed</label>
  <input type="range" id="speed" min="100" max="1200" step="50" value="500">
  <span id="speed-out">500 ms</span>
  <button id="btn-auto" onclick="toggleAuto()">Auto-flip all</button>
  <button onclick="showAll('base')">Show all 2020</button>
  <button onclick="showAll('year')">Show all years</button>
</div>

<div class="grid" id="grid"></div>

<div class="legend">
  <div class="legend-item">
    <div class="legend-dot" style="background:#5599cc"></div>
    <span>Showing 2020 reference</span>
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:#3d9e6e"></div>
    <span>Showing registered year</span>
  </div>
</div>

<script>
const REF_B64  = "data:image/jpeg;base64,{ref_b64}";
const TILES    = {tiles_json};
const state    = {{}};
let autoTimer  = null;
let autoIndex  = 0;
let autoActive = false;

function buildGrid() {{
  const grid = document.getElementById("grid");
  TILES.forEach((t, i) => {{
    state[i] = "year";
    const div = document.createElement("div");
    div.className = "tile flipping";
    div.tabIndex  = 0;
    div.dataset.idx = i;

    div.innerHTML = `
      <img class="tile-img" id="img-${{i}}"
           src="data:image/jpeg;base64,${{t.b64}}" alt="${{t.year}}">
      <div class="tile-header">
        <div>
          <span class="year-label">${{t.year}}</span>
          <span class="source-label" style="margin-left:6px">${{t.source}}</span>
        </div>
        <span class="badge badge-pass">PASS</span>
      </div>
      <div class="tile-footer">
        <span class="rmse-val">RMSE ${{t.rmse.toFixed(3)}} m · ${{t.pairs.toLocaleString()}} pairs</span>
        <span class="state-indicator" id="state-${{i}}">year</span>
      </div>`;

    div.addEventListener("click",   () => flipTile(i));
    div.addEventListener("keydown", e => {{
      if (e.key === " " || e.key === "Enter") {{ e.preventDefault(); flipTile(i); }}
    }});
    grid.appendChild(div);
  }});
}}

function flipTile(i) {{
  const tile      = document.querySelector(`[data-idx="${{i}}"]`);
  const img       = document.getElementById(`img-${{i}}`);
  const indicator = document.getElementById(`state-${{i}}`);
  const isBase    = state[i] === "base";

  img.style.opacity = "0.3";
  setTimeout(() => {{
    if (isBase) {{
      img.src      = `data:image/jpeg;base64,${{TILES[i].b64}}`;
      state[i]     = "year";
      tile.className = "tile flipping";
      indicator.textContent = "year";
    }} else {{
      img.src      = REF_B64;
      state[i]     = "base";
      tile.className = "tile showing-base";
      indicator.textContent = "2020";
    }}
    img.style.opacity = "1";
  }}, 80);
}}

function showAll(which) {{
  TILES.forEach((_, i) => {{
    if (state[i] !== which) flipTile(i);
  }});
}}

function toggleAuto() {{
  autoActive = !autoActive;
  const btn = document.getElementById("btn-auto");
  btn.classList.toggle("active", autoActive);
  btn.textContent = autoActive ? "Stop auto-flip" : "Auto-flip all";
  if (autoActive) runAuto(); else clearTimeout(autoTimer);
}}

function runAuto() {{
  if (!autoActive) return;
  flipTile(autoIndex % TILES.length);
  autoIndex++;
  const spd = parseInt(document.getElementById("speed").value);
  autoTimer = setTimeout(runAuto, spd);
}}

document.getElementById("speed").addEventListener("input", function() {{
  document.getElementById("speed-out").textContent = this.value + " ms";
}});

document.addEventListener("keydown", e => {{
  if (e.target.classList.contains("tile")) return;
  if (e.key === " ") {{
    e.preventDefault();
    TILES.forEach((_, i) => flipTile(i));
  }}
  if (e.key === "ArrowRight") {{ autoIndex++; flipTile(autoIndex % TILES.length); }}
  if (e.key === "ArrowLeft")  {{ autoIndex--; flipTile(((autoIndex % TILES.length) + TILES.length) % TILES.length); }}
}});

buildGrid();
</script>
</body>
</html>"""

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html)
    size_kb = OUTPUT_HTML.stat().st_size // 1024
    print(f"\n  Viewer written: {OUTPUT_HTML}")
    print(f"  {size_kb:,} KB  — open in any browser, no server needed")
    print(f"  {len(tiles)} year tiles embedded as JPEG thumbnails")
    print()
    print("  Controls:")
    print("    Click tile       — flip that tile between year / 2020")
    print("    Space            — flip all tiles simultaneously")
    print("    Arrow left/right — step through tiles one at a time")
    print("    Auto-flip button — cycle through all tiles automatically")
    print("    Speed slider     — control flip interval (100–1200 ms)")


if __name__ == "__main__":
    sys.argv = sys.argv[:1]
    run()
