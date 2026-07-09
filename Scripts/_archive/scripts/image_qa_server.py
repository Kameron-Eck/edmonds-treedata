"""
Aerial Imagery Quality Assessment Tool
Interactive browser-based viewer for downloaded USGS imagery

Architecture
────────────
Single HTTP server on port 8889 handles everything:
  GET  /manifest.json        → image list + metadata
  GET  /images/.../*.tif     → serve TIF as JPEG thumbnails
  GET  /qa_app.html          → serve the QA UI
  POST /save_qa              → save QA decision to Drive CSV
  POST /save_fiducials       → save fiducial marks to Drive JSON

Features
────────
- Canvas-based image viewer with rotation (0-360°)
- Click to mark fiducial locations (red circles)
- Keyboard shortcuts: Arrow keys rotate, A=accept, R=reject, Z=undo
- Real-time save to Google Drive
- Progress tracking with visual dots
- Auto-resume session from localStorage

Usage
─────
    %run image_qa_server.py
    # Opens browser URL, review all images, results save to Drive
"""

import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import csv

import numpy as np
from PIL import Image

# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════

IMAGE_DIR  = Path("/content/edmonds_imagery")
DRIVE_BASE = Path("/content/drive/MyDrive/treedata/Full_Image/USGS")
QA_CSV     = DRIVE_BASE / "Image_QA_Results.csv"
FID_JSON   = DRIVE_BASE / "Fiducial_Marks.json"
LOCAL_DIR  = Path("/content/image_qa")
PORT       = 8889

CSV_FIELDS = ["filepath", "year", "dataset", "filename", "status", 
              "rotation", "num_fiducials", "timestamp", "reviewer"]

# ══════════════════════════════════════════════════════════════
#  SCAN IMAGES
# ══════════════════════════════════════════════════════════════

def scan_images():
    """Find all TIF images and create manifest, excluding camera calibration PDFs"""
    print("\n── Scanning images ──")
    
    images = []
    skipped = 0
    
    for tif in sorted(IMAGE_DIR.rglob("*.tif")):
        # Check if it's a PDF (camera calibration report)
        with open(tif, 'rb') as f:
            header = f.read(4)
        
        if header == b'%PDF':
            skipped += 1
            continue
        
        # Also skip very small files (likely metadata/reports, not imagery)
        file_size_mb = tif.stat().st_size / (1024 * 1024)
        if file_size_mb < 1:  # Skip files under 1 MB
            skipped += 1
            continue
        
        rel_path = tif.relative_to(IMAGE_DIR)
        year = tif.parent.parent.name
        dataset = tif.parent.name
        
        images.append({
            "id": len(images),
            "filepath": str(tif),
            "rel_path": str(rel_path),
            "year": year,
            "dataset": dataset,
            "filename": tif.name
        })
    
    print(f"  Found {len(images)} images")
    if skipped:
        print(f"  Skipped {skipped} PDFs/metadata files")
    return images

# ══════════════════════════════════════════════════════════════
#  GENERATE THUMBNAILS
# ══════════════════════════════════════════════════════════════

def generate_thumbnail(tif_path, max_size=800):
    """Convert TIF to JPEG thumbnail for browser display"""
    print(f"  Generating thumbnail for {tif_path.name}...", end=" ", flush=True)
    try:
        import rasterio
        import gzip
        from io import BytesIO
        
        # Check if file is gzipped
        with open(tif_path, 'rb') as f:
            header = f.read(10)
        
        # Detect format
        if header[:2] == b'\x1f\x8b':  # gzip
            print("[gzip]", end=" ", flush=True)
            with gzip.open(tif_path, 'rb') as gz:
                tif_data = BytesIO(gz.read())
            tif_source = tif_data
        elif header[:2] in (b'II', b'MM'):  # TIF magic bytes
            print("[tif]", end=" ", flush=True)
            tif_source = tif_path
        else:
            # Unknown format - try as-is and report
            print(f"[unknown:{header[:4].hex()}]", end=" ", flush=True)
            tif_source = tif_path
        
        # Open with rasterio
        with rasterio.open(tif_source) as src:
            # Read RGB bands (typically 1,2,3)
            # Downsample on read for speed
            out_shape = (
                min(src.height, max_size),
                min(src.width, max_size)
            )
            
            data = src.read(
                [1, 2, 3] if src.count >= 3 else [1],
                out_shape=out_shape
            )
            
            # Convert to uint8 if needed
            if data.dtype != np.uint8:
                # Scale to 0-255
                data = np.clip(data, 0, 255).astype(np.uint8)
            
            # Transpose to HWC for PIL
            if data.shape[0] == 3:
                img_array = np.transpose(data, (1, 2, 0))
            else:
                # Single band - make it grayscale RGB
                img_array = np.stack([data[0]] * 3, axis=-1)
            
            # Convert to PIL Image
            img = Image.fromarray(img_array, mode='RGB')
            
            # Resize if still too large
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert to JPEG bytes
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=82)
            result = buf.getvalue()
            print(f"✓ {len(result)/1024:.0f}KB")
            return result
            
    except Exception as e:
        print(f"✗ {e}")
        import traceback
        traceback.print_exc()
        return None

# ══════════════════════════════════════════════════════════════
#  HTTP HANDLER
# ══════════════════════════════════════════════════════════════

def make_handler(images, static_dir):
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)
        
        def do_GET(self):
            print(f"→ GET {self.path}", flush=True)
            
            if self.path.startswith("/thumb/"):
                try:
                    # Serve TIF as JPEG thumbnail
                    img_id = int(self.path.split("/")[-1])
                    img = images[img_id]
                    
                    print(f"  Requested image {img_id}: {img['filename']}", flush=True)
                    jpeg_data = generate_thumbnail(Path(img["filepath"]))
                    
                    if jpeg_data:
                        self.send_response(200)
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(len(jpeg_data)))
                        self.send_header("Cache-Control", "public, max-age=3600")
                        self.end_headers()
                        self.wfile.write(jpeg_data)
                    else:
                        print(f"  ✗ Thumbnail generation returned None", flush=True)
                        self.send_error(500, "Thumbnail generation failed")
                except Exception as e:
                    print(f"  ✗ Handler error: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    self.send_error(500, str(e))
                return
            
            super().do_GET()
        
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            
            if self.path == "/save_qa":
                # Save QA decision
                row = {
                    "filepath": payload.get("filepath", ""),
                    "year": payload.get("year", ""),
                    "dataset": payload.get("dataset", ""),
                    "filename": payload.get("filename", ""),
                    "status": payload.get("status", ""),
                    "rotation": payload.get("rotation", 0),
                    "num_fiducials": payload.get("num_fiducials", 0),
                    "timestamp": datetime.now().isoformat(),
                    "reviewer": payload.get("reviewer", "")
                }
                
                # Write to CSV
                file_exists = QA_CSV.exists()
                with open(QA_CSV, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(row)
                
                self._json({"status": "ok"})
            
            elif self.path == "/save_fiducials":
                # Save fiducial marks
                filepath = payload.get("filepath")
                fiducials = payload.get("fiducials", [])
                
                # Load existing
                if FID_JSON.exists():
                    with open(FID_JSON, 'r') as f:
                        all_fids = json.load(f)
                else:
                    all_fids = {}
                
                all_fids[filepath] = fiducials
                
                # Save
                with open(FID_JSON, 'w') as f:
                    json.dump(all_fids, f, indent=2)
                
                self._json({"status": "ok"})
            
            else:
                self.send_error(404)
        
        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        
        def log_message(self, fmt, *args):
            # Only log save requests, suppress other HTTP logs
            try:
                msg = fmt % args
                if "/save" in msg:
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")
            except:
                pass  # Ignore logging errors
    
    return Handler

# ══════════════════════════════════════════════════════════════
#  QA APP HTML
# ══════════════════════════════════════════════════════════════

QA_APP_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Aerial Imagery QA Tool</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background:#0d1117; color:#c9d1d9;
  font-family:monospace,sans-serif; font-size:12px;
  height:100vh; overflow:hidden; display:flex; flex-direction:column;
}
.topbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:10px 16px; background:#161b22; border-bottom:1px solid #21262d;
}
.topbar .title { font-size:14px; font-weight:700; color:#58a6ff; }
.main { display:flex; flex:1; overflow:hidden; }
.canvas-area {
  flex:1; display:flex; flex-direction:column;
  align-items:center; justify-content:center; position:relative;
}
#imgCanvas {
  border:2px solid #21262d; border-radius:8px;
  max-width:90%; max-height:70vh; cursor:crosshair;
}
.ctrls {
  display:flex; gap:8px; margin-top:12px; flex-wrap:wrap;
  align-items:center; justify-content:center;
}
.btn {
  background:#21262d; border:1px solid #30363d; color:#c9d1d9;
  padding:8px 16px; border-radius:5px; cursor:pointer;
  font-family:inherit; font-size:11px; font-weight:600;
}
.btn-accept { background:#2e7d32; color:#fff; }
.btn-reject { background:#c62828; color:#fff; }
.slider-wrap { display:flex; align-items:center; gap:8px; }
.slider { width:200px; }
.rot-val { color:#58a6ff; min-width:45px; text-align:right; }
.panel {
  width:260px; background:#161b22; border-left:1px solid #21262d;
  padding:16px; display:flex; flex-direction:column; gap:14px;
  overflow-y:auto;
}
.sec-title {
  color:#484f58; font-size:9px; text-transform:uppercase;
  letter-spacing:0.8px; margin-bottom:8px;
}
.row { display:flex; justify-content:space-between; margin-bottom:4px; }
.row .lbl { color:#484f58; }
.row .val { color:#c9d1d9; font-weight:600; }
.dot-grid { display:flex; flex-wrap:wrap; gap:2px; }
.dot {
  width:6px; height:6px; border-radius:1px;
  background:#21262d; transition:background 0.1s;
}
.dot.cur { background:#58a6ff; }
.dot.accept { background:#2e7d32; }
.dot.reject { background:#c62828; }
.setup-ov {
  position:fixed; inset:0; background:rgba(0,0,0,0.85);
  display:flex; align-items:center; justify-content:center; z-index:100;
}
.setup-box {
  background:#161b22; border:1px solid #30363d; border-radius:10px;
  padding:24px 28px; max-width:360px; width:90%;
}
.setup-box h2 { color:#58a6ff; font-size:15px; margin-bottom:16px; }
.setup-box input {
  width:100%; background:#0d1117; border:1px solid #30363d;
  color:#c9d1d9; padding:8px; border-radius:5px;
  font-family:inherit; font-size:12px; margin-bottom:14px;
}
.btn-start {
  width:100%; background:#2e7d32; border:none; color:#fff;
  padding:10px; border-radius:6px; cursor:pointer;
  font-family:inherit; font-size:12px; font-weight:700;
}
</style>
</head>
<body>

<div class="setup-ov" id="setupOv">
  <div class="setup-box">
    <h2>🗺️ Aerial Imagery QA</h2>
    <label style="color:#484f58;font-size:10px;display:block;margin-bottom:5px">
      Your name or ID
    </label>
    <input type="text" id="reviewerInput" placeholder="e.g. Kam"
           onkeydown="if(event.key==='Enter'&&this.value.trim())startSession()">
    <button class="btn-start" onclick="startSession()">Start QA →</button>
  </div>
</div>

<div class="topbar">
  <span class="title">🗺️ AERIAL IMAGERY QA</span>
  <div style="display:flex;gap:8px">
    <span id="navPos">— / —</span>
  </div>
</div>

<div class="main">
  <div class="canvas-area">
    <canvas id="imgCanvas" width="800" height="800"></canvas>
    
    <div class="ctrls">
      <div class="slider-wrap">
        <button class="btn" onclick="rotate(-90)">↶ 90° CCW</button>
        <input type="range" id="rotSlider" class="slider"
               min="0" max="360" value="0" step="1"
               oninput="rotation=parseInt(this.value);render()">
        <span class="rot-val" id="rotVal">0°</span>
        <button class="btn" onclick="rotate(90)">↷ 90° CW</button>
      </div>
    </div>
    
    <div class="ctrls">
      <button class="btn btn-reject" onclick="mark('REJECT')">
        ✗ Reject [R]
      </button>
      <button class="btn" onclick="mark('SKIP')">Skip [S]</button>
      <button class="btn btn-accept" onclick="mark('ACCEPT')">
        ✓ Accept [A]
      </button>
    </div>
    
    <div style="color:#484f58;font-size:10px;margin-top:8px;text-align:center">
      Left-click: add fiducial · Right-click: remove last<br>
      Arrow keys: rotate · A/R/S: accept/reject/skip
    </div>
  </div>

  <div class="panel">
    <div>
      <div class="sec-title">Image</div>
      <div class="row"><span class="lbl">Year</span>
           <span class="val" id="iYear">—</span></div>
      <div class="row"><span class="lbl">Dataset</span>
           <span class="val" id="iDataset">—</span></div>
      <div class="row"><span class="lbl">File</span>
           <span class="val" id="iFile" style="font-size:10px">—</span></div>
      <div class="row"><span class="lbl">Fiducials</span>
           <span class="val" id="iFid">0</span></div>
    </div>
    
    <div>
      <div class="sec-title">Session</div>
      <div class="row"><span class="lbl">Reviewer</span>
           <span class="val" id="sReviewer">—</span></div>
      <div class="row"><span class="lbl">Reviewed</span>
           <span class="val" id="sReviewed">0 / 0</span></div>
      <div class="row"><span class="lbl">Accepted</span>
           <span class="val" style="color:#4CAF50" id="sAccept">0</span></div>
      <div class="row"><span class="lbl">Rejected</span>
           <span class="val" style="color:#f44336" id="sReject">0</span></div>
    </div>
    
    <div>
      <div class="sec-title">Progress</div>
      <div class="dot-grid" id="dotGrid"></div>
    </div>
  </div>
</div>

<script>
var images=[], currentIdx=0, rotation=0, fiducials=[];
var qa={}, reviewer="", imgCache={};

function startSession(){
  reviewer=document.getElementById("reviewerInput").value.trim();
  if(!reviewer)return;
  document.getElementById("setupOv").style.display="none";
  
  // Load saved QA
  var key="img_qa_"+reviewer.replace(/\s+/g,"_");
  var saved=localStorage.getItem(key);
  if(saved){
    try{ qa=JSON.parse(saved); }catch(e){}
  }
  
  loadManifest();
}

async function loadManifest(){
  console.log("Loading manifest...");
  try{
    var resp=await fetch("manifest.json");
    var data=await resp.json();
    images=data.images;
    console.log("Loaded "+images.length+" images");
    buildDots();
    updateUI();
    await render();
  }catch(e){
    console.error("Manifest load failed:",e);
    alert("Failed to load manifest: "+e);
  }
}

async function loadImg(idx){
  if(imgCache[idx])return imgCache[idx];
  console.log("Loading image "+idx+"...");
  var img=new Image();
  return new Promise(function(res,rej){
    img.onload=function(){
      console.log("Image "+idx+" loaded");
      imgCache[idx]=img;
      res(img);
    };
    img.onerror=function(e){
      console.error("Image "+idx+" failed:",e);
      rej(e);
    };
    img.src="/thumb/"+idx;
  });
}

async function render(){
  if(!images.length){
    console.log("No images to render");
    return;
  }
  
  console.log("Rendering image "+currentIdx);
  var img=images[currentIdx];
  var canvas=document.getElementById("imgCanvas");
  var ctx=canvas.getContext("2d");
  
  // Show loading
  ctx.fillStyle="#0d1117";
  ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle="#484f58";
  ctx.font="12px monospace";
  ctx.textAlign="center";
  ctx.fillText("Loading image...",canvas.width/2,canvas.height/2);
  
  try{
    // Load and draw image
    var imgObj=await loadImg(currentIdx);
    
    // Clear
    ctx.fillStyle="#0d1117";
    ctx.fillRect(0,0,canvas.width,canvas.height);
    
    // Rotate
    ctx.save();
    ctx.translate(canvas.width/2, canvas.height/2);
    ctx.rotate(rotation * Math.PI / 180);
    
    var scale=Math.min(canvas.width/imgObj.width, canvas.height/imgObj.height)*0.9;
    var w=imgObj.width*scale, h=imgObj.height*scale;
    ctx.drawImage(imgObj, -w/2, -h/2, w, h);
    ctx.restore();
    
    // Draw fiducials
    fiducials.forEach(function(f){
      ctx.beginPath();
      ctx.arc(f.x, f.y, 20, 0, 2*Math.PI);
      ctx.strokeStyle="#f44336";
      ctx.lineWidth=2;
      ctx.stroke();
    });
    
    console.log("Render complete");
  }catch(e){
    console.error("Render failed:",e);
    ctx.fillStyle="#0d1117";
    ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle="#c62828";
    ctx.font="12px monospace";
    ctx.textAlign="center";
    ctx.fillText("Failed to load image",canvas.width/2,canvas.height/2-10);
    ctx.fillStyle="#484f58";
    ctx.fillText("Check console for details",canvas.width/2,canvas.height/2+10);
  }
  
  updateUI();
}

function updateUI(){
  if(!images.length)return;
  
  var img=images[currentIdx];
  
  // Update rotation UI
  document.getElementById("rotVal").textContent=rotation+"°";
  document.getElementById("rotSlider").value=rotation;
  document.getElementById("navPos").textContent=(currentIdx+1)+" / "+images.length;
  document.getElementById("rotVal").textContent=rotation+"°";
  document.getElementById("rotSlider").value=rotation;
  document.getElementById("navPos").textContent=(currentIdx+1)+" / "+images.length;
  document.getElementById("iYear").textContent=img.year;
  document.getElementById("iDataset").textContent=img.dataset;
  document.getElementById("iFile").textContent=img.filename;
  document.getElementById("iFid").textContent=fiducials.length;
  document.getElementById("sReviewer").textContent=reviewer;
  
  var total=Object.keys(qa).length;
  var accept=Object.values(qa).filter(function(v){return v.status==="ACCEPT";}).length;
  var reject=Object.values(qa).filter(function(v){return v.status==="REJECT";}).length;
  document.getElementById("sReviewed").textContent=total+" / "+images.length;
  document.getElementById("sAccept").textContent=accept;
  document.getElementById("sReject").textContent=reject;
  
  updateDots();
}

function rotate(deg){
  rotation=(rotation+deg)%360;
  if(rotation<0)rotation+=360;
  render();
}

function mark(status){
  var img=images[currentIdx];
  qa[currentIdx]={status:status,rotation:rotation,fiducials:fiducials.length};
  
  // Save to Drive
  fetch("/save_qa",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      filepath:img.filepath, year:img.year, dataset:img.dataset,
      filename:img.filename, status:status, rotation:rotation,
      num_fiducials:fiducials.length, reviewer:reviewer
    })
  });
  
  // Save fiducials if any
  if(fiducials.length>0){
    fetch("/save_fiducials",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        filepath:img.filepath,
        fiducials:fiducials
      })
    });
  }
  
  // Save locally
  localStorage.setItem("img_qa_"+reviewer.replace(/\s+/g,"_"),JSON.stringify(qa));
  
  // Next
  fiducials=[];
  rotation=0;
  currentIdx++;
  if(currentIdx<images.length)render();
  else alert("All images reviewed!");
}

document.getElementById("imgCanvas").addEventListener("click",function(e){
  if(e.button===0){
    var rect=this.getBoundingClientRect();
    fiducials.push({x:e.clientX-rect.left, y:e.clientY-rect.top});
    render();
  }
});

document.getElementById("imgCanvas").addEventListener("contextmenu",function(e){
  e.preventDefault();
  if(fiducials.length>0){
    fiducials.pop();
    render();
  }
});

document.addEventListener("keydown",function(e){
  if(e.target.tagName==="INPUT")return;
  if(e.key==="a"||e.key==="A"){mark("ACCEPT");}
  else if(e.key==="r"||e.key==="R"){mark("REJECT");}
  else if(e.key==="s"||e.key==="S"){mark("SKIP");}
  else if(e.key==="ArrowLeft"){rotate(-10);}
  else if(e.key==="ArrowRight"){rotate(10);}
  else if(e.key==="ArrowUp"){rotate(90);}
  else if(e.key==="ArrowDown"){rotate(-90);}
});

function buildDots(){
  var grid=document.getElementById("dotGrid");
  grid.innerHTML="";
  var n=Math.min(100,images.length);
  for(var i=0;i<n;i++){
    var d=document.createElement("div");
    d.className="dot";
    d.dataset.i=i;
    d.onclick=(function(idx){return function(){currentIdx=idx;fiducials=[];render();};})(i);
    grid.appendChild(d);
  }
}

function updateDots(){
  document.querySelectorAll(".dot").forEach(function(d){
    var i=parseInt(d.dataset.i);
    d.className="dot";
    if(i===currentIdx)d.classList.add("cur");
    else if(qa[i]&&qa[i].status==="ACCEPT")d.classList.add("accept");
    else if(qa[i]&&qa[i].status==="REJECT")d.classList.add("reject");
  });
}
</script>
</body>
</html>
"""

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("="*60)
    print("  AERIAL IMAGERY QA TOOL")
    print("="*60)
    
    # Scan images
    images = scan_images()
    
    if not images:
        print("\n✗ No images found in /content/edmonds_imagery")
        return
    
    # Create manifest
    LOCAL_DIR.mkdir(exist_ok=True)
    manifest_data = {"images": images}
    
    manifest_path = LOCAL_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data))
    print(f"\n✓ Manifest created: {len(images)} images")
    
    # Write HTML
    app_path = LOCAL_DIR / "qa_app.html"
    app_path.write_text(QA_APP_HTML)
    print(f"✓ App written: {app_path}")
    
    # Kill any existing server on this port (aggressive cleanup)
    print(f"\n── Cleaning up port {PORT} ──")
    os.system(f'fuser -k {PORT}/tcp 2>/dev/null')
    os.system(f'pkill -f "port {PORT}" 2>/dev/null')
    
    # Try to bind and release to force cleanup
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', PORT))
        s.close()
        print(f"✓ Port {PORT} available")
    except Exception as e:
        print(f"⚠ Port may still be in use: {e}")
    
    time.sleep(2)
    
    # Start server
    print(f"\n── Starting server on port {PORT} ──")
    
    Handler = make_handler(images, LOCAL_DIR)
    
    try:
        server = socketserver.ThreadingTCPServer(("", PORT), Handler)
        server.allow_reuse_address = True
        
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        
        time.sleep(2)
        print(f"✓ Server started successfully")
        
    except Exception as e:
        print(f"✗ Server startup failed: {e}")
        return None
    
    # Get Colab proxy URL
    try:
        from google.colab.output import eval_js
        from IPython.display import display, HTML
        
        print(f"\nGenerating Colab proxy URL...")
        proxy_url = eval_js(f"google.colab.kernel.proxyPort({PORT})")
        qa_url = proxy_url + "/qa_app.html"
        
        print(f"\n{'='*60}")
        print(f"✓ QA TOOL READY")
        print(f"{'='*60}")
        print(f"\nOpen this URL in a new tab:")
        print(f"\n  {qa_url}\n")
        
        display(HTML(
            f'<div style="background:#161b22;padding:20px;border:1px solid #30363d;'
            f'border-radius:8px;margin:10px 0">'
            f'<div style="color:#58a6ff;font-size:16px;font-weight:700;margin-bottom:10px">'
            f'🗺️ Image QA Tool Ready</div>'
            f'<a href="{qa_url}" target="_blank" '
            f'style="display:inline-block;background:#2e7d32;color:#fff;'
            f'padding:12px 24px;text-decoration:none;border-radius:6px;'
            f'font-family:monospace;font-size:14px;font-weight:700">'
            f'→ Open QA Tool</a>'
            f'<div style="color:#484f58;font-size:11px;margin-top:12px;line-height:1.6">'
            f'<b>Controls:</b> Arrow keys rotate · A=accept · R=reject · '
            f'Click to mark fiducials<br>'
            f'<b>Output:</b> {QA_CSV.name}</div>'
            f'</div>'
        ))
        
        print(f"\n── Controls ──")
        print(f"  Rotation : Arrow keys (←→ 10°, ↑↓ 90°)")
        print(f"  Fiducials: Left-click add, Right-click remove")
        print(f"  Accept   : A key")
        print(f"  Reject   : R key")
        print(f"  Skip     : S key")
        
        print(f"\n── Output ──")
        print(f"  QA results  : {QA_CSV}")
        print(f"  Fiducials   : {FID_JSON}")
        
        print(f"\n✓ Reviewing {len(images)} images")
        print(f"  Keep this cell running during review")
        print(f"{'='*60}")
        
        # Keep server alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n✓ Server stopped")
            server.shutdown()
        
    except Exception as e:
        print(f"\n✗ Could not generate Colab URL: {e}")
        print(f"\nTry accessing via:")
        print(f"  In Colab, look for the proxy URL in the notebook output")
        return None
    
    return server

if __name__ == "__main__":
    DRIVE_BASE.mkdir(parents=True, exist_ok=True)
    server = main()