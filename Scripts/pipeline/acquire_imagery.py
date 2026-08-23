#!/usr/bin/env python3
"""
acquire_imagery.py -- manifest-driven imagery acquisition (campaign of 2026-08-23).

Deterministic core for the plan at D:/tools/claude-config/plans/you-are-running-an-foamy-tulip.md.
Reads pipeline/imagery_acquisition_manifest.json; nothing downloads without `fetch --approved`.

Subcommands
  plan      --batch N [--mirror]          size/disk gates, no network (HEADs `files` items to fill bytes)
  probe     --id X                        service JSON -> _acq/X.probe.json; asserts manifest px/bands/CRS
  pilot     --id X [--box-m N] [--site S] [--controls] [--geometry-sweep] [--rendering default|none]
  fetch     --batch N | --id X  --approved "<date> Kam: <quote>"  [--workers --core --overlap --strip
                                         --cooldown --timeout --compression --regrid --accept-empty]
  status    --id X                        rolling throughput, timings, error rates, ETA, verdict
  assemble  --id X [--accept-empty]       chunk files -> final BigTIFF (+overviews, tags); spot-verified
  verify    --id X                        measurements + replacement decision -> _acq/X.measure.json
  manifest  --id X                        MANIFEST.sha256 (mirror_sync tab format) for the source dir
  mirror    --id X                        copy2 to Drive + size verify (Drive floor gate)
  register  --id X                        prints the rows/dicts to paste; edits nothing
  clean     --id X                        delete chunk files (only after assemble verified + MANIFEST)

Design (from the code review of _archive/scripts/unified_downloader.py):
  grid snapped to the service lattice + RSP_NearestNeighbor (no server resampling)  [#1]
  four-corner study envelope                                                          [#2]
  per-chunk ledger + gap report; run fails on any missing chunk                       [#3,#4,#7]
  hard band assertion (fewer bands than declared is fatal)                            [#5]
  rasterio decode + transform check                                                   [#6]
  chunk files on disk, one assemble                                                   [#8]
  local-then-copy: D: first, MANIFEST, then Drive                                     [#9]
  one retry stack, capped backoff, Retry-After honoured                               [#10]
  shared token-bucket rate limiter                                                    [#11]
  --core/--strip geometry, --compression LZ77, one session per worker                 [#12-14]
  per-chunk telemetry so `status` can diagnose a slow run                             [agentic loop]
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, io, json, math, os, random, shutil, statistics, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent          # Scripts/pipeline
SCRIPTS = HERE.parent
MANIFEST_JSON = HERE / "imagery_acquisition_manifest.json"
FTUS = 0.3048006096012192
UA = "EdmondsCanopyAcquire/1.0 (research; kameron4321@gmail.com)"


# ----------------------------------------------------------------------------- manifest / paths
def load_manifest(path: Path = MANIFEST_JSON) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def target_by_id(m: dict, tid: str) -> dict:
    for t in m["targets"]:
        if t["id"] == tid:
            return t
    sys.exit(f"no target with id {tid!r}")


def targets_in_batch(m: dict, batch) -> list[dict]:
    return [t for t in m["targets"] if str(t.get("batch")) == str(batch)]


def local_root(m): return Path(m["local_root"])
def drive_root(m): return Path(m["drive_root"])


def src_dir(m, t) -> Path:
    d = local_root(m) / t["source_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def acq_dir(m, t) -> Path:
    d = src_dir(m, t) / "_acq" / t["id"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def ledger_path(m, t) -> Path:
    d = src_dir(m, t) / "_acq"; d.mkdir(parents=True, exist_ok=True)
    return d / f"{t['id']}.chunks.jsonl"
def out_path(m, t) -> Path:
    name = t.get("out_name") or (t.get("mosaic") or t.get("clip") or {}).get("out_name")
    return src_dir(m, t) / name


def profile_for(m: dict, url: str, overrides: dict | None = None) -> dict:
    prof = dict(m["profiles"]["default"])
    for host, p in m["profiles"].items():
        if host != "default" and host in url:
            prof.update(p); break
    for k, v in (overrides or {}).items():
        if v is not None:
            prof[k] = v
    return prof


# ----------------------------------------------------------------------------- geometry
def study_bbox(m: dict, epsg: int) -> tuple[float, float, float, float]:
    """Four-corner envelope of the EPSG:3857 study extent in `epsg` (review defect #2)."""
    x0, y0, x1, y1 = m["extent_3857"]
    if epsg == 3857:
        return (x0, y0, x1, y1)
    from pyproj import Transformer
    t = Transformer.from_crs(3857, epsg, always_xy=True)
    xs, ys = [], []
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        a, b = t.transform(x, y); xs.append(a); ys.append(b)
    return (min(xs), min(ys), max(xs), max(ys))


def snap_grid(bbox, px: float, origin_x: float, origin_y: float):
    """Output grid whose pixel lattice coincides with the service lattice (origin = service extent
    xmin / ymax). Returns (x0, y1, width, height): x0/y1 = top-left corner, px square."""
    bx0, by0, bx1, by1 = bbox
    x0 = origin_x + math.floor((bx0 - origin_x) / px) * px
    x1 = origin_x + math.ceil((bx1 - origin_x) / px) * px
    y1 = origin_y - math.floor((origin_y - by1) / px) * px
    y0 = origin_y - math.ceil((origin_y - by0) / px) * px
    w = int(round((x1 - x0) / px)); h = int(round((y1 - y0) / px))
    return x0, y1, w, h


class Chunk:
    __slots__ = ("row", "col", "c0", "r0", "w", "h", "rc0", "rr0", "rw", "rh")

    def __init__(self, row, col, c0, r0, w, h, rc0, rr0, rw, rh):
        self.row, self.col, self.c0, self.r0, self.w, self.h = row, col, c0, r0, w, h
        self.rc0, self.rr0, self.rw, self.rh = rc0, rr0, rw, rh      # request window (with overlap)

    @property
    def key(self): return f"r{self.row:04d}_c{self.col:04d}"

    def crop(self):           # core window relative to the request window
        return (self.c0 - self.rc0, self.r0 - self.rr0, self.w, self.h)


def build_grid(W: int, H: int, core_w: int, core_h: int, overlap: int) -> list[Chunk]:
    out = []
    nrows = math.ceil(H / core_h); ncols = math.ceil(W / core_w)
    for r in range(nrows):
        for c in range(ncols):
            c0, r0 = c * core_w, r * core_h
            w, h = min(core_w, W - c0), min(core_h, H - r0)
            rc0, rr0 = max(0, c0 - overlap), max(0, r0 - overlap)
            rc1, rr1 = min(W, c0 + w + overlap), min(H, r0 + h + overlap)
            out.append(Chunk(r, c, c0, r0, w, h, rc0, rr0, rc1 - rc0, rr1 - rr0))
    return out


def grid_spec(m, t, probe, overrides=None) -> dict:
    prof = profile_for(m, t["url"], overrides)
    px = float(t["px"])
    bbox = study_bbox(m, t["native_epsg"]) if t.get("extent", "study") == "study" else \
        (probe["extent"]["xmin"], probe["extent"]["ymin"], probe["extent"]["xmax"], probe["extent"]["ymax"])
    if t.get("grid_origin") == "webmercator":
        ox, oy = -20037508.342787, 20037508.342787
    else:
        ox, oy = probe["extent"]["xmin"], probe["extent"]["ymax"]
    x0, y1, W, H = snap_grid(bbox, px, ox, oy)
    core_w = core_h = int(prof["core_px"])
    if prof.get("strip"):
        core_w, core_h = int(probe["maxImageWidth"]) - 2 * int(prof["overlap_px"]), int(probe["maxImageHeight"]) - 2 * int(prof["overlap_px"])
        core_w -= core_w % 16; core_h -= core_h % 16
    ov = int(prof["overlap_px"])
    if core_w + 2 * ov > probe["maxImageWidth"] or core_h + 2 * ov > probe["maxImageHeight"]:
        sys.exit(f"request geometry {core_w + 2*ov}x{core_h + 2*ov} exceeds the service cap "
                 f"{probe['maxImageWidth']}x{probe['maxImageHeight']}")
    return {"x0": x0, "y1": y1, "px": px, "W": W, "H": H, "core_w": core_w, "core_h": core_h,
            "overlap": ov, "epsg": int(t["native_epsg"]), "bands": int(t["bands"]),
            "pixel_type": t.get("pixel_type", "U8"), "compression": prof.get("compression"), "band_ids": t.get("band_ids"),
            "rendering": prof.get("rendering", "default"), "profile": prof}


def grid_signature(gs: dict) -> str:
    keys = ("x0", "y1", "px", "W", "H", "core_w", "core_h", "overlap", "epsg", "bands")
    return hashlib.sha256(json.dumps({k: gs[k] for k in keys}, sort_keys=True).encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------- HTTP
_tls = threading.local()


def session():
    import requests
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session(); s.headers["User-Agent"] = UA
        from requests.adapters import HTTPAdapter
        s.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=0))
        _tls.s = s
    return s


class RateLimiter:
    """Shared token bucket: at most one request START per `interval` seconds across all workers."""
    def __init__(self, interval: float):
        self.interval = float(interval); self._next = 0.0; self._lock = threading.Lock()

    def acquire(self):
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic(); wait = self._next - now
            self._next = max(now, self._next) + self.interval
        if wait > 0:
            time.sleep(wait)


def probe_service(url: str) -> dict:
    import requests
    r = requests.get(url, params={"f": "json"}, timeout=30, headers={"User-Agent": UA}); r.raise_for_status()
    d = r.json()
    if "error" in d:
        sys.exit(f"probe error: {d['error']}")
    ext = d.get("extent") or d.get("fullExtent")
    sr = (ext or {}).get("spatialReference") or d.get("spatialReference") or {}
    return {"url": url, "name": d.get("name"), "pixelSizeX": d.get("pixelSizeX"), "pixelSizeY": d.get("pixelSizeY"),
            "bandCount": d.get("bandCount"), "pixelType": d.get("pixelType"),
            "maxImageWidth": d.get("maxImageWidth", 4096), "maxImageHeight": d.get("maxImageHeight", 4096),
            "capabilities": d.get("capabilities"), "copyrightText": d.get("copyrightText"),
            "extent": {"xmin": ext["xmin"], "ymin": ext["ymin"], "xmax": ext["xmax"], "ymax": ext["ymax"],
                       "wkid": sr.get("latestWkid") or sr.get("wkid")} if ext else None,
            "probed_at": dt.datetime.now().isoformat(timespec="seconds")}


def export_params(gs: dict, ch: Chunk, interpolation="RSP_NearestNeighbor"):
    x0 = gs["x0"] + ch.rc0 * gs["px"]; x1 = x0 + ch.rw * gs["px"]
    y1 = gs["y1"] - ch.rr0 * gs["px"]; y0 = y1 - ch.rh * gs["px"]
    p = {"bbox": f"{x0:.6f},{y0:.6f},{x1:.6f},{y1:.6f}", "bboxSR": gs["epsg"], "imageSR": gs["epsg"],
         "size": f"{ch.rw},{ch.rh}", "format": "tiff", "pixelType": gs["pixel_type"],
         "interpolation": interpolation, "f": "image"}
    if gs.get("compression"):
        p["compression"] = gs["compression"]
    if gs.get("rendering") == "none":
        p["renderingRule"] = json.dumps({"rasterFunction": "None"})
    if gs.get("band_ids"):
        p["bandIds"] = gs["band_ids"]
    return p, (x0, y0, x1, y1)


class Fatal(Exception):
    pass


def fetch_chunk(url: str, gs: dict, ch: Chunk, prof: dict, limiter: RateLimiter, chunk_file: Path,
                fetcher=None, interpolation: str = "RSP_NearestNeighbor") -> dict:
    """Download one chunk, verify it, crop the overlap, write `chunk_file`. Returns the ledger record.
    `fetcher(params) -> (status, headers, body)` can be injected for offline tests."""
    import numpy as np, rasterio
    from rasterio.io import MemoryFile
    params, bbox = export_params(gs, ch, interpolation=interpolation)
    rec = {"key": ch.key, "row": ch.row, "col": ch.col, "attempts": 0, "status": "fail", "err": "",
           "t_queue": 0.0, "ttfb": None, "t_xfer": None, "t_proc": None, "bytes": 0, "content_length": None,
           "http": None, "sha256": None, "all_zero": None, "extra_bands": 0, "worker": threading.get_ident() % 10000}
    max_retry = int(prof.get("max_retry", 5)); base = float(prof.get("backoff_base", 2.0)); cap = float(prof.get("backoff_cap", 60))
    timeout = float(prof.get("timeout", 120))
    t_enq = time.monotonic()
    for attempt in range(1, max_retry + 1):
        rec["attempts"] = attempt
        limiter.acquire()
        rec["t_queue"] = round(time.monotonic() - t_enq, 3)
        t0 = time.monotonic()
        try:
            if fetcher is not None:
                status, headers, body = fetcher(params); ttfb = time.monotonic() - t0
            else:
                r = session().get(url + "/exportImage", params=params, timeout=timeout, stream=True)
                ttfb = time.monotonic() - t0
                status, headers = r.status_code, {k.lower(): v for k, v in r.headers.items()}
                body = r.content; r.close()
            t_xfer = time.monotonic() - t0 - ttfb
            rec.update(http=status, ttfb=round(ttfb, 3), t_xfer=round(t_xfer, 3), bytes=len(body))
            ct = str(headers.get("content-type", "")).lower()
            cl = headers.get("content-length")
            rec["content_length"] = int(cl) if cl is not None and str(cl).isdigit() else None
            if status == 429 or 500 <= status < 600:
                ra = headers.get("retry-after")
                wait = float(ra) if ra and str(ra).replace(".", "").isdigit() else min(cap, base ** attempt)
                rec["err"] = f"http {status}"; time.sleep(wait + random.random()); continue
            if status != 200:
                rec["err"] = f"http {status}: {body[:200]!r}"; break
            if "json" in ct or "html" in ct or "text" in ct:
                text = body[:800].decode("utf-8", "replace").lower()
                if any(k in text for k in ("token required", "unauthorized", "forbidden", "access denied", "authentication")):
                    raise Fatal(f"auth: {text[:160]}")
                if "exceed" in text or "too large" in text or "maximum" in text:
                    raise Fatal(f"request too large for the service: {text[:160]}")
                rec["err"] = f"non-image body ({ct}): {text[:160]}"
                time.sleep(min(cap, base ** attempt)); continue
            if rec["content_length"] is not None and rec["content_length"] != len(body):
                rec["err"] = f"truncated: {len(body)} of {rec['content_length']}"; time.sleep(min(cap, base ** attempt)); continue
            tp = time.monotonic()
            with MemoryFile(body) as mf, mf.open() as ds:
                if ds.count < gs["bands"]:
                    raise Fatal(f"server returned {ds.count} bands for a {gs['bands']}-band target (no silent padding)")
                rec["extra_bands"] = ds.count - gs["bands"]
                if (ds.width, ds.height) != (ch.rw, ch.rh):
                    rec["err"] = f"size mismatch {ds.width}x{ds.height} != {ch.rw}x{ch.rh}"; break
                tr = ds.transform
                tol = gs["px"] * 1e-3
                if abs(tr.c - bbox[0]) > tol or abs(tr.f - bbox[3]) > tol or abs(tr.a - gs["px"]) > gs["px"] * 1e-6 or abs(-tr.e - gs["px"]) > gs["px"] * 1e-6:
                    rec["err"] = f"transform mismatch: origin ({tr.c},{tr.f}) px ({tr.a},{tr.e}) vs ({bbox[0]},{bbox[3]}) {gs['px']}"; break
                cx, cy, cw, chh = ch.crop()
                arr = ds.read(list(range(1, gs["bands"] + 1)), window=rasterio.windows.Window(cx, cy, cw, chh))
                dtype = ds.dtypes[0]
            rec["all_zero"] = bool(not np.any(arr))
            chunk_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = chunk_file.with_suffix(".part.tif")
            from rasterio.transform import from_origin
            core_tr = from_origin(gs["x0"] + ch.c0 * gs["px"], gs["y1"] - ch.r0 * gs["px"], gs["px"], gs["px"])
            with rasterio.open(tmp, "w", driver="GTiff", width=cw, height=chh, count=gs["bands"], dtype=dtype,
                               crs=rasterio.crs.CRS.from_epsg(gs["epsg"]), transform=core_tr,
                               compress="deflate", zlevel=1, tiled=False) as dst:
                dst.write(arr)
            os.replace(tmp, chunk_file)
            h = hashlib.sha256(); h.update(chunk_file.read_bytes())
            rec.update(sha256=h.hexdigest(), file_bytes=chunk_file.stat().st_size, status="ok", err="",
                       t_proc=round(time.monotonic() - tp, 3))
            return rec
        except Fatal:
            raise
        except Exception as e:       # timeouts, connection errors, decode errors
            rec["err"] = f"{type(e).__name__}: {str(e)[:160]}"
            time.sleep(min(cap, base ** attempt) + random.random())
    return rec


# ----------------------------------------------------------------------------- ledger / status
def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out


def ledger_ok(recs: list[dict], chunk_dir: Path, rehash=False) -> set[str]:
    ok = set()
    for r in recs:
        if r.get("status") != "ok":
            continue
        f = chunk_dir / f"{r['key']}.tif"
        if not f.exists() or f.stat().st_size != r.get("file_bytes"):
            continue
        if rehash and hashlib.sha256(f.read_bytes()).hexdigest() != r.get("sha256"):
            continue
        ok.add(r["key"])
    return ok


def ledger_header(recs):
    for r in recs:
        if r.get("type") == "header":
            return r
    return None


def gap_report(grid: list[Chunk], recs: list[dict], chunk_dir: Path, extent_ok=None) -> dict:
    ok = ledger_ok(recs, chunk_dir)
    last = {}
    for r in recs:
        if "key" in r:
            last[r["key"]] = r
    empty_in, failed = [], []
    for ch in grid:
        r = last.get(ch.key)
        if ch.key in ok:
            if r and r.get("all_zero"):
                empty_in.append(ch.key)
        else:
            failed.append({"key": ch.key, "err": (r or {}).get("err", "never attempted"), "attempts": (r or {}).get("attempts", 0)})
    return {"total": len(grid), "ok": len(ok), "empty": len(empty_in), "empty_keys": empty_in, "failed": failed}


def chunk_map_png(grid: list[Chunk], rep: dict, path: Path):
    try:
        from PIL import Image
    except ImportError:
        return
    nrows = max(c.row for c in grid) + 1; ncols = max(c.col for c in grid) + 1
    img = Image.new("RGB", (ncols, nrows), (200, 40, 40))
    failed = {f["key"] for f in rep["failed"]}; empty = set(rep["empty_keys"])
    for ch in grid:
        col = (200, 40, 40) if ch.key in failed else (150, 150, 150) if ch.key in empty else (40, 160, 60)
        img.putpixel((ch.col, ch.row), col)
    scale = max(1, 600 // max(ncols, nrows))
    img.resize((ncols * scale, nrows * scale), Image.NEAREST).save(path)


def status_report(m, t, window_s=300) -> dict:
    recs = read_ledger(ledger_path(m, t)); hdr = ledger_header(recs)
    data = [r for r in recs if "key" in r]
    if not data:
        return {"id": t["id"], "verdict": "no ledger"}
    now = time.time()
    recent = [r for r in data if now - r.get("ts", 0) <= window_s]
    ok_recent = [r for r in recent if r["status"] == "ok"]
    tot_ok = sum(1 for r in data if r["status"] == "ok")
    total = hdr.get("n_chunks") if hdr else None
    elapsed = (now - hdr["ts"]) if hdr else None
    mb = sum(r["bytes"] for r in ok_recent) / 1e6
    span = min(window_s, now - min(r["ts"] for r in recent)) if recent else 0
    rate_mb = mb / span if span > 0 else 0.0
    rate_ch = len(ok_recent) / span * 60 if span > 0 else 0.0

    def pct(vals, q):
        vals = [v for v in vals if v is not None]
        if not vals: return None
        vals = sorted(vals); return round(vals[min(len(vals) - 1, int(q * (len(vals) - 1)))], 2)
    errs = sum(1 for r in recent if r["status"] != "ok")
    retries = sum(max(0, r.get("attempts", 1) - 1) for r in recent)
    http_bad = sum(1 for r in recent if r.get("http") in (429,) or (r.get("http") or 0) >= 500)
    ttfb50, ttfb95 = pct([r["ttfb"] for r in ok_recent], .5), pct([r["ttfb"] for r in ok_recent], .95)
    xfer50 = pct([r["t_xfer"] for r in ok_recent], .5); proc50 = pct([r["t_proc"] for r in ok_recent], .5)
    px_per_chunk = (hdr["core_w"] * hdr["core_h"] * hdr["bands"]) if hdr else None
    bpp = (statistics.median([r["bytes"] / max(1, (r.get("bytes_px") or px_per_chunk)) for r in ok_recent]) if ok_recent and px_per_chunk else None)
    eta_min = ((total - tot_ok) / rate_ch) if (total and rate_ch > 0) else None
    verdict = "healthy"
    n = max(1, len(recent))
    if not recent and elapsed and elapsed > 600 and total and tot_ok < total:
        verdict = "STALL: no ledger activity in the window -> cancel and resume (fresh sessions)"
    elif (errs + http_bad) / n > 0.05:
        verdict = "THROTTLED/ERRORS > 5% -> halve workers, longer cooldown/timeout"
    elif ttfb50 and xfer50 is not None and ttfb50 > 3 * max(xfer50, 0.05):
        verdict = "RENDER-BOUND (TTFB >> transfer) -> larger requests (--core 4096 or --strip)"
    elif proc50 and xfer50 is not None and proc50 >= xfer50:
        verdict = "LOCAL-BOUND (decode/write >= transfer) -> zlevel 1 / NVMe / fewer verify reads"
    elif xfer50 and ttfb50 is not None and xfer50 > 3 * max(ttfb50, 0.05):
        verdict = "TRANSFER-BOUND -> try --compression LZ77; check the local link"
    return {"id": t["id"], "total": total, "ok": tot_ok, "pct": round(100 * tot_ok / total, 2) if total else None,
            "window_s": window_s, "recent": len(recent), "rate_MBps": round(rate_mb, 2), "rate_chunks_per_min": round(rate_ch, 1),
            "ttfb_p50": ttfb50, "ttfb_p95": ttfb95, "xfer_p50": xfer50, "proc_p50": proc50,
            "err_rate": round(errs / n, 3), "retries": retries, "http_429_5xx": http_bad,
            "bytes_per_px": round(bpp, 3) if bpp else None, "elapsed_min": round(elapsed / 60, 1) if elapsed else None,
            "eta_min": round(eta_min, 1) if eta_min else None, "verdict": verdict,
            "profile": hdr.get("profile") if hdr else None}


# ----------------------------------------------------------------------------- fetch / assemble
def do_probe(m, t) -> dict:
    p = probe_service(t["url"])
    problems = []
    if p["pixelSizeX"] is not None and abs(float(p["pixelSizeX"]) - float(t["px"])) > 1e-9 * max(1, float(t["px"])):
        problems.append(f"service pixelSizeX {p['pixelSizeX']} != manifest px {t['px']} (served grid; native may differ - see notes)")
    if p["bandCount"] is not None and int(p["bandCount"]) < int(t["bands"]):
        problems.append(f"service bandCount {p['bandCount']} < manifest bands {t['bands']}")
    if p["extent"] and p["extent"]["wkid"] not in (t["native_epsg"], {2285: 102748, 2926: 102748}.get(t["native_epsg"])):
        problems.append(f"service wkid {p['extent']['wkid']} != manifest epsg {t['native_epsg']}")
    p["manifest_mismatches"] = problems
    (acq_dir(m, t) / "probe.json").write_text(json.dumps(p, indent=1), encoding="utf-8")
    return p


def load_probe(m, t) -> dict:
    f = acq_dir(m, t) / "probe.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else do_probe(m, t)


def do_fetch(m, t, args) -> int:
    overrides = {"workers": args.workers, "core_px": args.core, "overlap_px": args.overlap, "cooldown": args.cooldown,
                 "timeout": args.timeout, "compression": args.compression, "strip": args.strip or None}
    probe = load_probe(m, t)
    gs = grid_spec(m, t, probe, overrides)
    if args.rendering: gs["rendering"] = args.rendering
    prof = gs["profile"]
    grid = build_grid(gs["W"], gs["H"], gs["core_w"], gs["core_h"], gs["overlap"])
    sig = grid_signature(gs)
    lp = ledger_path(m, t); chunk_dir = acq_dir(m, t) / "chunks"
    recs = read_ledger(lp); hdr = ledger_header(recs)
    if hdr and hdr.get("grid_sig") != sig:
        if not args.regrid:
            sys.exit(f"ledger grid {hdr.get('grid_sig')} != requested {sig}: chunk geometry is frozen once chunks exist; "
                     f"pass --regrid to restart this target from scratch")
        print(f"--regrid: discarding {len(recs)} ledger lines and {chunk_dir}")
        shutil.rmtree(chunk_dir, ignore_errors=True); lp.unlink(missing_ok=True); recs, hdr = [], None
    if hdr is None:
        hdr = {"type": "header", "id": t["id"], "ts": time.time(), "grid_sig": sig, "n_chunks": len(grid), **{k: gs[k] for k in
               ("x0", "y1", "px", "W", "H", "core_w", "core_h", "overlap", "epsg", "bands")}, "profile": prof,
               "approved": args.approved, "url": t["url"]}
        with open(lp, "a", encoding="utf-8") as f:
            f.write(json.dumps(hdr) + "\n")
    with open(lp, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "run", "ts": time.time(), "approved": args.approved, "profile": prof, "argv": sys.argv[1:]}) + "\n")
    done = ledger_ok(recs, chunk_dir, rehash=args.rehash)
    todo = [c for c in grid if c.key not in done]
    print(f"[{t['id']}] grid {gs['W']}x{gs['H']} px @ {gs['px']} {t.get('px_units','')} EPSG:{gs['epsg']}, {len(grid)} chunks "
          f"({gs['core_w']}x{gs['core_h']}+{gs['overlap']}), {len(done)} done, {len(todo)} to fetch, workers={prof['workers']} "
          f"cooldown={prof['cooldown']} compression={gs.get('compression')}")
    if not todo:
        rep = gap_report(grid, recs, chunk_dir); print(json.dumps({k: v for k, v in rep.items() if k != 'empty_keys'}))
        return 0 if not rep["failed"] else 2
    limiter = RateLimiter(float(prof.get("cooldown", 0)))
    lock = threading.Lock(); fatal = {"err": None}; n_done = 0; t_start = time.monotonic(); bytes_done = 0

    def work(ch):
        if fatal["err"]:
            return None
        try:
            return fetch_chunk(t["url"], gs, ch, prof, limiter, chunk_dir / f"{ch.key}.tif")
        except Fatal as e:
            fatal["err"] = str(e); return {"key": ch.key, "row": ch.row, "col": ch.col, "status": "fatal", "err": str(e), "attempts": 1, "bytes": 0}

    with ThreadPoolExecutor(max_workers=int(prof["workers"])) as pool, open(lp, "a", encoding="utf-8") as f:
        futs = [pool.submit(work, c) for c in todo]
        for fut in as_completed(futs):
            rec = fut.result()
            if rec is None:
                continue
            rec["ts"] = time.time(); rec["bytes_px"] = gs["core_w"] * gs["core_h"] * gs["bands"]
            with lock:
                f.write(json.dumps(rec) + "\n"); f.flush()
                n_done += 1; bytes_done += rec.get("bytes", 0)
                if n_done % 25 == 0 or rec["status"] != "ok":
                    el = time.monotonic() - t_start
                    print(f"  {n_done}/{len(todo)} {rec['key']} {rec['status']} {rec.get('err','')[:80]} "
                          f"| {bytes_done/1e6/max(el,1e-9):.2f} MB/s, {n_done/max(el,1e-9)*60:.1f} chunks/min", flush=True)
            if fatal["err"]:
                for fu in futs: fu.cancel()
    recs = read_ledger(lp)
    rep = gap_report(grid, recs, chunk_dir)
    (acq_dir(m, t) / "gaps.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    chunk_map_png(grid, rep, acq_dir(m, t) / "chunkmap.png")
    print(f"[{t['id']}] ok {rep['ok']}/{rep['total']}, empty {rep['empty']}, failed {len(rep['failed'])}"
          + (f"  FATAL: {fatal['err']}" if fatal["err"] else ""))
    if fatal["err"]:
        return 4
    return 2 if rep["failed"] else 0


def do_assemble(m, t, accept_empty=False, keep_chunks=True) -> int:
    import numpy as np, rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    lp = ledger_path(m, t); recs = read_ledger(lp); hdr = ledger_header(recs)
    if not hdr:
        sys.exit("no ledger header - run fetch first")
    chunk_dir = acq_dir(m, t) / "chunks"
    grid = build_grid(hdr["W"], hdr["H"], hdr["core_w"], hdr["core_h"], hdr["overlap"])
    rep = gap_report(grid, recs, chunk_dir)
    if rep["failed"]:
        sys.exit(f"{len(rep['failed'])} chunks missing/failed - assemble refused (see gaps.json)")
    if rep["empty"] and not accept_empty:
        sys.exit(f"{rep['empty']} all-zero chunks inside the extent - eyeball chunkmap.png then pass --accept-empty")
    out = out_path(m, t); tmp = out.with_suffix(".partial.tif")
    first = chunk_dir / f"{grid[0].key}.tif"
    with rasterio.open(first) as c0:
        dtype = c0.dtypes[0]
    transform = from_origin(hdr["x0"], hdr["y1"], hdr["px"], hdr["px"])
    prof = {"driver": "GTiff", "dtype": dtype, "width": hdr["W"], "height": hdr["H"], "count": hdr["bands"],
            "crs": rasterio.crs.CRS.from_epsg(hdr["epsg"]), "transform": transform, "compress": "deflate", "predictor": 2,
            "tiled": True, "blockxsize": 512, "blockysize": 512, "BIGTIFF": "YES", "NUM_THREADS": "ALL_CPUS"}
    t0 = time.monotonic()
    with rasterio.open(tmp, "w", **prof) as dst:
        for i, ch in enumerate(grid):
            with rasterio.open(chunk_dir / f"{ch.key}.tif") as src:
                dst.write(src.read(), window=rasterio.windows.Window(ch.c0, ch.r0, ch.w, ch.h))
            if i % 200 == 0:
                print(f"  wrote {i}/{len(grid)} chunks ({time.monotonic()-t0:.0f}s)", flush=True)
        for b, name in enumerate(t.get("band_names", []), 1):
            dst.set_band_description(b, name)
        dst.update_tags(ACQ_ID=t["id"], SOURCE_URL=t["url"], REQUEST_GRID=f"{hdr['core_w']}x{hdr['core_h']}+{hdr['overlap']} px, origin {hdr['x0']},{hdr['y1']} EPSG:{hdr['epsg']}",
                        RESAMPLING="RSP_NearestNeighbor (server), grid snapped to service lattice", FETCH_DATE=dt.date.today().isoformat(),
                        LEDGER_SHA256=hashlib.sha256(lp.read_bytes()).hexdigest(), CAMPAIGN="imagery_acquisition 2026-08-23")
    with rasterio.open(tmp, "r+") as dst:
        thematic = bool((t.get("clip") or {}).get("thematic"))
        dst.build_overviews([2, 4, 8, 16, 32, 64], Resampling.nearest if thematic else Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="nearest" if thematic else "average")
    # spot-verify: N random chunks byte-equal
    rng = random.Random(42); sample = rng.sample(grid, min(12, len(grid)))
    with rasterio.open(tmp) as dst:
        for ch in sample:
            with rasterio.open(chunk_dir / f"{ch.key}.tif") as src:
                a = src.read(); b = dst.read(window=rasterio.windows.Window(ch.c0, ch.r0, ch.w, ch.h))
            if not np.array_equal(a, b):
                sys.exit(f"spot-verify FAILED at {ch.key}")
    os.replace(tmp, out)
    print(f"[{t['id']}] assembled {out} ({out.stat().st_size/1e9:.2f} GB) in {time.monotonic()-t0:.0f}s; spot-verified {len(sample)} chunks")
    return 0


# ----------------------------------------------------------------------------- files mode
def head_size(url: str) -> int | None:
    import requests
    r = requests.head(url, timeout=60, headers={"User-Agent": UA}, allow_redirects=True)
    cl = r.headers.get("Content-Length")
    return int(cl) if cl and cl.isdigit() else None


def fetch_file(url: str, dest: Path, expect: int | None = None, fetcher=None) -> dict:
    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part"); h = hashlib.sha256(); n = 0; t0 = time.monotonic()
    if fetcher is not None:
        body = fetcher(url); tmp.write_bytes(body); h.update(body); n = len(body); cl = expect
    else:
        with requests.get(url, stream=True, timeout=120, headers={"User-Agent": UA}) as r:
            r.raise_for_status(); cl = r.headers.get("Content-Length"); cl = int(cl) if cl and cl.isdigit() else None
            with open(tmp, "wb") as f:
                for blk in r.iter_content(1 << 20):
                    f.write(blk); h.update(blk); n += len(blk)
    if cl is not None and n != cl:
        tmp.unlink(missing_ok=True)
        return {"file": dest.name, "status": "fail", "err": f"truncated {n} of {cl}", "bytes": n}
    os.replace(tmp, dest)
    return {"file": dest.name, "status": "ok", "bytes": n, "content_length": cl, "sha256": h.hexdigest(), "secs": round(time.monotonic() - t0, 1), "url": url}


def do_fetch_files(m, t, args) -> int:
    lp = ledger_path(m, t); d = src_dir(m, t); recs = read_ledger(lp)
    done = {r["file"] for r in recs if r.get("status") == "ok" and (d / r["file"]).exists() and (d / r["file"]).stat().st_size == r.get("bytes")}
    todo = [n for n in t["items"] if n not in done]
    workers = int(args.workers or 4)          # files mode: parallel streams (single-stream NOAA blob ~1 MB/s, 2026-08-23)
    lock = threading.Lock()

    def one(name):
        url = t["base_url"] + name
        rec = {}
        for attempt in range(1, 4):
            rec = fetch_file(url, d / name); rec["ts"] = time.time(); rec["attempts"] = attempt
            with lock, open(lp, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"  {name}: {rec['status']} {rec.get('bytes',0)/1e6:.1f} MB in {rec.get('secs','?')}s {rec.get('err','')}", flush=True)
            if rec["status"] == "ok":
                return rec
            time.sleep(5 * attempt)
        return rec

    with open(lp, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "run", "ts": time.time(), "approved": args.approved, "argv": sys.argv[1:], "workers": workers}) + "\n")
    if todo:
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, todo))
        got = sum(r.get("bytes", 0) for r in results if r.get("status") == "ok")
        el = time.monotonic() - t0
        print(f"[{t['id']}] {len(todo)} files, {got/1e6:.0f} MB in {el:.0f}s = {got/1e6/max(el,1e-9):.2f} MB/s aggregate ({workers} streams)", flush=True)
    recs = read_ledger(lp)
    okf = {r["file"] for r in recs if r.get("status") == "ok"}
    missing = [n for n in t["items"] if n not in okf]
    if missing:
        print(f"[{t['id']}] MISSING {missing}"); return 2
    print(f"[{t['id']}] {len(t['items'])}/{len(t['items'])} files ok")
    return 0


def do_fetch_download(m, t, args) -> int:
    """Services with the `Download` capability (e.g. WAGDA): pull the ORIGINAL source tiles over the study extent via
    /query (catalog) -> /download (file list with exact sizes, <= 20 per request) -> /file. Verified by the size the
    service itself published (the /file response carries no Content-Length). Items recorded in _acq/<id>/download_items.json
    so `assemble` can mosaic them like NAIP quads."""
    import requests
    B = t["url"]; d = src_dir(m, t) / "tiles"; d.mkdir(parents=True, exist_ok=True)
    bb = study_bbox(m, int(t["native_epsg"]))
    q = {"where": "1=1", "geometry": f"{bb[0]},{bb[1]},{bb[2]},{bb[3]}", "geometryType": "esriGeometryEnvelope", "inSR": t["native_epsg"],
         "spatialRel": "esriSpatialRelIntersects", "outFields": "OBJECTID,Name,Category", "returnGeometry": "false", "f": "json"}
    fs = requests.get(B + "/query", params=q, timeout=120, headers={"User-Agent": UA}).json().get("features", [])
    prim = [f["attributes"]["OBJECTID"] for f in fs if f["attributes"].get("Category") == 1]
    items = []
    for i in range(0, len(prim), 20):
        dl = requests.get(B + "/download", params={"rasterIds": ",".join(map(str, prim[i:i + 20])), "f": "json"}, timeout=120, headers={"User-Agent": UA}).json()
        for rf in dl.get("rasterFiles", []):
            items.append({"id": rf["id"], "bytes": int(rf["size"]), "rasterId": rf["rasterIds"][0], "filename": rf["id"].replace("\\", "/").split("/")[-1]})
    (acq_dir(m, t) / "download_items.json").write_text(json.dumps({"n_catalog": len(fs), "n_primary": len(prim), "items": items}, indent=1), encoding="utf-8")
    print(f"[{t['id']}] {len(prim)} primary tiles over the extent, {sum(i['bytes'] for i in items)/1e9:.2f} GB published size")
    lp = ledger_path(m, t); recs = read_ledger(lp)
    done = {r["file"] for r in recs if r.get("status") == "ok" and (d / r["file"]).exists() and (d / r["file"]).stat().st_size == r.get("bytes")}
    todo = [it for it in items if it["filename"] not in done]
    workers = int(args.workers or 4); lock = threading.Lock()

    def one(it):
        url = B + "/file?" + urllib_encode({"id": it["id"], "rasterId": it["rasterId"]})
        rec = {}
        for attempt in range(1, 4):
            rec = fetch_file(url, d / it["filename"], expect=it["bytes"]); rec["ts"] = time.time(); rec["attempts"] = attempt
            if rec["status"] == "ok" and rec["bytes"] != it["bytes"]:
                rec["status"] = "fail"; rec["err"] = f"size {rec['bytes']} != published {it['bytes']}"; (d / it["filename"]).unlink(missing_ok=True)
            with lock, open(lp, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"  {it['filename']}: {rec['status']} {rec.get('bytes',0)/1e6:.1f} MB in {rec.get('secs','?')}s {rec.get('err','')}", flush=True)
            if rec["status"] == "ok":
                return rec
            time.sleep(5 * attempt)
        return rec

    with open(lp, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "run", "ts": time.time(), "approved": args.approved, "argv": sys.argv[1:], "via": "download", "workers": workers}) + "\n")
    if todo:
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            res = list(pool.map(one, todo))
        got = sum(r.get("bytes", 0) for r in res if r.get("status") == "ok"); el = time.monotonic() - t0
        print(f"[{t['id']}] {len(todo)} tiles, {got/1e6:.0f} MB in {el:.0f}s = {got/1e6/max(el,1e-9):.2f} MB/s aggregate ({workers} streams)", flush=True)
    recs = read_ledger(lp); okf = {r["file"] for r in recs if r.get("status") == "ok"}
    missing = [it["filename"] for it in items if it["filename"] not in okf]
    if missing:
        print(f"[{t['id']}] MISSING {missing}"); return 2
    print(f"[{t['id']}] {len(items)}/{len(items)} source tiles ok"); return 0


def urllib_encode(params):
    import urllib.parse
    return urllib.parse.urlencode(params)


def do_mosaic(m, t) -> int:
    """NAIP quads -> one raster on the study extent (tile CRS/grid, nearest, no resampling)."""
    import numpy as np, rasterio
    from rasterio.merge import merge
    from rasterio.enums import Resampling
    spec = t.get("mosaic") or {"out_name": t["out_name"], "epsg": t["native_epsg"], "bands": t["bands"], "band_names": t.get("band_names", [])}
    d = src_dir(m, t)
    dlf = acq_dir(m, t) / "download_items.json"
    if dlf.exists():
        items = json.loads(dlf.read_text(encoding="utf-8"))["items"]
        tifs = [d / "tiles" / it["filename"] for it in items if it["filename"].lower().endswith(".tif")]
        tifs = [p for p in tifs if p.exists()]
    else:
        tifs = [d / n for n in t["items"] if n.lower().endswith(".tif")]
    srcs = [rasterio.open(p) for p in tifs]
    try:
        epsg = srcs[0].crs.to_epsg(); res = srcs[0].res[0]
        bbox = study_bbox(m, epsg)
        ox, oy = srcs[0].transform.c, srcs[0].transform.f
        x0, y1, W, H = snap_grid(bbox, res, ox, oy)
        arr, tr = merge(srcs, bounds=(x0, y1 - H * res, x0 + W * res, y1), res=res, nodata=0, method="first",
                        resampling=Resampling.nearest, indexes=list(range(1, spec["bands"] + 1)))
    finally:
        for s in srcs: s.close()
    out = d / spec["out_name"]; tmp = out.with_suffix(".partial.tif")
    prof = {"driver": "GTiff", "dtype": arr.dtype, "width": arr.shape[2], "height": arr.shape[1], "count": arr.shape[0],
            "crs": rasterio.crs.CRS.from_epsg(epsg), "transform": tr, "compress": "deflate", "predictor": 2, "tiled": True,
            "blockxsize": 512, "blockysize": 512, "BIGTIFF": "YES", "nodata": 0}
    with rasterio.open(tmp, "w", **prof) as dst:
        dst.write(arr)
        for b, name in enumerate(spec.get("band_names", []), 1):
            dst.set_band_description(b, name)
        dst.update_tags(ACQ_ID=t["id"], SOURCE_URL=t.get("base_url") or t.get("url"), SOURCE_TILES=",".join(p.name for p in tifs),
                        FETCH_DATE=dt.date.today().isoformat(), CAMPAIGN="imagery_acquisition 2026-08-23")
    with rasterio.open(tmp, "r+") as dst:
        dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
    os.replace(tmp, out)
    print(f"[{t['id']}] mosaic {out.name} {arr.shape} EPSG:{epsg} res {res} -> {out.stat().st_size/1e9:.2f} GB")
    return 0


def do_clip(m, t) -> int:
    """Thematic clip of a large raster to the study extent (nearest, same grid, colormap kept)."""
    import rasterio
    from rasterio.enums import Resampling
    spec = t["clip"]; d = src_dir(m, t)
    src_name = [n for n in t["items"] if n.lower().endswith(".tif")][0]
    with rasterio.open(d / src_name) as src:
        epsg = src.crs.to_epsg(); res = src.res[0]
        x0, y1, W, H = snap_grid(study_bbox(m, epsg), res, src.transform.c, src.transform.f)
        win = rasterio.windows.from_bounds(x0, y1 - H * res, x0 + W * res, y1, transform=src.transform)
        win = win.round_offsets().round_lengths()
        arr = src.read(window=win)
        tr = src.window_transform(win)
        cmap = None
        try: cmap = src.colormap(1)
        except Exception: pass
        prof = src.profile.copy()
    prof.update(width=arr.shape[2], height=arr.shape[1], transform=tr, compress="deflate", tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
    out = d / spec["out_name"]; tmp = out.with_suffix(".partial.tif")
    with rasterio.open(tmp, "w", **prof) as dst:
        dst.write(arr)
        if cmap: dst.write_colormap(1, cmap)
        dst.update_tags(ACQ_ID=t["id"], SOURCE_URL=t["base_url"] + src_name, FETCH_DATE=dt.date.today().isoformat(), CAMPAIGN="imagery_acquisition 2026-08-23")
    with rasterio.open(tmp, "r+") as dst:
        dst.build_overviews([2, 4, 8, 16], Resampling.nearest)
    os.replace(tmp, out)
    print(f"[{t['id']}] clip {out.name} {arr.shape} EPSG:{epsg} res {res}")
    return 0


# ----------------------------------------------------------------------------- gates / manifest / mirror
def free_gb(path) -> float:
    try: return shutil.disk_usage(str(path)).free / 1e9
    except Exception: return float("nan")


def target_bytes(m, t, head=False) -> int:
    if t.get("expect_bytes_verified"):
        return int(t["expect_bytes"])
    if t.get("mode") == "files" and head:
        tot = 0
        for n in t["items"]:
            s = head_size(t["base_url"] + n); tot += s or 0
        return tot
    return int(t.get("expect_bytes", 0))


def do_plan(m, batch, mirror=False, head=False) -> int:
    ts = [t for t in targets_in_batch(m, batch) if t.get("mode") in ("export", "files")]
    tot = 0
    for t in ts:
        b = target_bytes(m, t, head); tot += b
        print(f"  {t['id']:6s} {t.get('mode'):6s} {b/1e9:6.2f} GB  {t.get('licence','')[:60]}  -> {(t.get('out_name') or (t.get('mosaic') or t.get('clip') or {}).get('out_name'))}")
    g = m["gates"]; d_free = free_gb(local_root(m)); g_free = free_gb(drive_root(m))
    print(f"batch {batch}: {tot/1e9:.2f} GB; D: free {d_free:.1f} GB -> {d_free - 2*tot/1e9:.1f} after (chunks+final); Drive free {g_free:.1f} GB"
          + (f" -> {g_free - tot/1e9:.1f} after mirror" if mirror else ""))
    rc = 0
    if tot / 1e9 > g["batch_max_gb"]:
        print(f"GATE: batch {tot/1e9:.1f} GB > {g['batch_max_gb']} GB -> explicit OK from Kam required"); rc = 3
    if d_free - 2 * tot / 1e9 < g["local_floor_gb"]:
        print(f"GATE: D: would fall below {g['local_floor_gb']} GB"); rc = 3
    if mirror and g_free - tot / 1e9 < g["drive_floor_gb"]:
        print(f"GATE: Drive would fall below {g['drive_floor_gb']} GB"); rc = 3
    print("plan OK" if rc == 0 else "plan BLOCKED")
    return rc


def do_manifest(m, t) -> int:
    sys.path.insert(0, str(HERE))
    import mirror_sync
    d = src_dir(m, t)
    mirror_sync.write_manifest(d)
    print(f"[{t['id']}] MANIFEST.sha256 written for {d}")
    return 0


def do_mirror(m, t) -> int:
    g = m["gates"]; d = src_dir(m, t); out = out_path(m, t)
    dest_dir = drive_root(m) / t["source_dir"]; dest_dir.mkdir(parents=True, exist_ok=True)
    pipe_dir = drive_root(m) / "Pipeline Imagery"
    need = out.stat().st_size if out.exists() else 0
    if free_gb(drive_root(m)) - need / 1e9 < g["drive_floor_gb"]:
        print(f"GATE: Drive free {free_gb(drive_root(m)):.1f} GB - mirroring {need/1e9:.2f} GB would cross the {g['drive_floor_gb']} GB floor"); return 3
    copied = []
    # the catalogued raster -> Pipeline Imagery (unless quarantined); sidecars + MANIFEST + source tiles -> Full_Image/<SOURCE>
    if out.exists():
        dest = (dest_dir if "_quarantine" in t["source_dir"] else pipe_dir) / out.name
        if not dest.exists() or dest.stat().st_size != out.stat().st_size:
            t0 = time.monotonic(); shutil.copy2(out, dest)
            if dest.stat().st_size != out.stat().st_size:
                print(f"SIZE MISMATCH after copy: {dest}"); return 1
            copied.append((dest, out.stat().st_size, time.monotonic() - t0))
    for p in sorted(d.glob("*")):
        if p.is_file() and p.name != out.name and not p.name.endswith((".part", ".partial.tif")):
            dest = dest_dir / p.name
            if not dest.exists() or dest.stat().st_size != p.stat().st_size:
                t0 = time.monotonic(); shutil.copy2(p, dest); copied.append((dest, p.stat().st_size, time.monotonic() - t0))
    side = d / "_acq"
    if side.exists():
        for p in side.rglob("*"):
            if p.is_file() and "chunks" not in p.parts:
                dest = dest_dir / "_acq" / p.relative_to(side); dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists() or dest.stat().st_size != p.stat().st_size:
                    shutil.copy2(p, dest); copied.append((dest, p.stat().st_size, 0))
    for dest, n, secs in copied:
        print(f"  -> {dest} {n/1e6:.1f} MB" + (f" @ {n/1e6/max(secs,1e-9):.1f} MB/s" if secs else ""))
    print(f"[{t['id']}] mirrored {len(copied)} files")
    return 0


def do_clean(m, t) -> int:
    d = src_dir(m, t); out = out_path(m, t)
    if not out.exists() or not (d / "MANIFEST.sha256").exists():
        sys.exit("clean refused: final raster or MANIFEST.sha256 missing")
    cd = acq_dir(m, t) / "chunks"
    n = sum(1 for _ in cd.glob("*.tif")) if cd.exists() else 0
    shutil.rmtree(cd, ignore_errors=True)
    print(f"[{t['id']}] removed {n} chunk files")
    return 0


# ----------------------------------------------------------------------------- pilot / verify / register
def do_pilot(m, t, args) -> int:
    import numpy as np, rasterio
    sys.path.insert(0, str(SCRIPTS / "qc")); import imagery_measure as im
    probe = load_probe(m, t)
    px = float(t["px"]); epsg = int(t["native_epsg"])
    box_m = float(args.box_m or (t.get("pilot") or {}).get("box_m") or 500)
    unit_m = FTUS if "ft" in t.get("px_units", "") else (1.0 if t.get("px_units", "").startswith("m") else 1.0)
    if epsg == 3857:
        unit_m = 1.0 / math.cos(math.radians(47.81))   # WM metres are inflated; box_m is ground metres
    box_px = int(round(box_m / (px * unit_m)))
    box_px -= box_px % 16
    site = args.site or (t.get("pilot") or {}).get("site") or "auto"
    lon, lat = im.pilot_site(site, held=(local_root(m) / t["replaces"]) if t.get("replaces") else None,
                             service_extent=probe["extent"], epsg=epsg)
    from pyproj import Transformer
    tx = Transformer.from_crs(4326, epsg, always_xy=True); cx, cy = tx.transform(lon, lat)
    gs = grid_spec(m, t, probe); gs["rendering"] = args.rendering or "default"
    # a small grid centred on the site, snapped to the service lattice
    x0, y1, _, _ = snap_grid((cx - box_px * px / 2, cy - box_px * px / 2, cx + box_px * px / 2, cy + box_px * px / 2), px, probe["extent"]["xmin"], probe["extent"]["ymax"])
    g2 = dict(gs, x0=x0, y1=y1, W=box_px, H=box_px)
    pd = acq_dir(m, t) / "pilot"; pd.mkdir(exist_ok=True)
    limiter = RateLimiter(float(gs["profile"].get("cooldown", 0)))
    res = {"id": t["id"], "site": [lon, lat], "box_px": box_px, "box_m": box_m, "px": px, "epsg": epsg, "predictions": {}, "results": {}}
    # 1) direct single request (nearest) vs chunked (core 512 + overlap 64) -> must be identical
    direct = build_grid(box_px, box_px, box_px, box_px, 0)[0]
    r_direct = fetch_chunk(t["url"], g2, direct, gs["profile"], limiter, pd / "direct_nearest.tif")
    if r_direct["status"] != "ok":
        print(f"direct request failed: {r_direct['err']}"); return 1
    chunks = build_grid(box_px, box_px, 512, 512, 64)
    recs = [fetch_chunk(t["url"], g2, c, gs["profile"], limiter, pd / "chunks" / f"{c.key}.tif") for c in chunks]
    bad = [r for r in recs if r["status"] != "ok"]
    if bad:
        print(f"chunked pilot: {len(bad)} failed: {bad[0]['err']}"); return 1
    with rasterio.open(pd / "direct_nearest.tif") as d0:
        A = d0.read()
    B = np.zeros_like(A)
    for c in chunks:
        with rasterio.open(pd / "chunks" / f"{c.key}.tif") as s:
            B[:, c.r0:c.r0 + c.h, c.c0:c.c0 + c.w] = s.read()
    diff = np.abs(A.astype(np.int32) - B.astype(np.int32))
    res["results"]["stitch_vs_direct"] = {"n_diff": int((diff > 0).sum()), "max_diff": int(diff.max()), "pass": bool(diff.max() == 0)}
    res["predictions"]["stitch_vs_direct"] = "n_diff == 0 (overlap+crop is exact)"
    # 2) nearest vs bilinear direct -> identical iff the grid is source-aligned
    rb = fetch_chunk(t["url"], g2, direct, gs["profile"], limiter, pd / "direct_bilinear.tif", interpolation="RSP_BilinearInterpolation")
    if rb["status"] == "ok":
        with rasterio.open(pd / "direct_bilinear.tif") as d1:
            C = d1.read()
        d2 = np.abs(A.astype(np.int32) - C.astype(np.int32))
        res["results"]["nearest_vs_bilinear"] = {"n_diff": int((d2 > 0).sum()), "max_diff": int(d2.max()), "frac_diff": float((d2 > 0).mean()),
                                                "aligned": bool((d2 > 0).mean() < 0.01)}
        res["predictions"]["nearest_vs_bilinear"] = "identical (or <1% of pixels differ) when the grid is snapped to the source lattice"
    # 3) band verdict
    res["results"]["bands"] = im.band_verdict_array(A, names=t.get("band_names"))
    # 4) effective resolution on the pilot box vs the held file at the same ground
    true_cm = px * unit_m * 100 if epsg != 3857 else px * math.cos(math.radians(lat)) * 100
    res["results"]["effective_cm_new"] = im.effective_cm_array(A[0], true_cm)
    if t.get("replaces") or t.get("complements"):
        held = local_root(m) / (t.get("replaces") or t.get("complements"))
        if held.exists():
            res["results"]["effective_cm_held_same_ground"] = im.effective_cm_at(held, lon, lat, box_m)
            res["results"]["compare_to_held"] = im.compare_to_held_arrays(pd / "direct_nearest.tif", held, lon, lat, box_m)
    res["results"]["jpeg_block_new"] = im.jpeg_block_score(A[0])
    # 5) geometry sweep
    if args.geometry_sweep:
        sweep = []
        for core, comp in ((2048, None), (4096, None), (2048, "LZ77"), ("strip", None)):
            gsw = dict(gs); gsw["compression"] = comp
            if core == "strip":
                cw, chh = int(probe["maxImageWidth"]) - 128, int(probe["maxImageHeight"]) - 128
                cw -= cw % 16; chh -= chh % 16
            else:
                cw = chh = core
            if cw + 128 > probe["maxImageWidth"] or chh + 128 > probe["maxImageHeight"]:
                continue
            sx0, sy1, _, _ = snap_grid((cx - cw * px / 2, cy - chh * px / 2, cx + cw * px / 2, cy + chh * px / 2), px, probe["extent"]["xmin"], probe["extent"]["ymax"])
            gsw.update(x0=sx0, y1=sy1, W=cw + 128, H=chh + 128)
            c = build_grid(cw + 128, chh + 128, cw, chh, 64)[0]
            times = []
            for k in range(2):
                r = fetch_chunk(t["url"], gsw, c, gs["profile"], limiter, pd / f"sweep_{core}_{comp}_{k}.tif")
                times.append(r)
            okr = [r for r in times if r["status"] == "ok"]
            sweep.append({"core": core, "compression": comp, "req_px": (cw + 128) * (chh + 128), "n_ok": len(okr),
                          "ttfb_mean": round(statistics.mean(r["ttfb"] for r in okr), 2) if okr else None,
                          "xfer_mean": round(statistics.mean(r["t_xfer"] for r in okr), 2) if okr else None,
                          "bytes_mean": int(statistics.mean(r["bytes"] for r in okr)) if okr else None,
                          "MB_per_s": round(statistics.mean(r["bytes"] for r in okr) / 1e6 / statistics.mean(r["ttfb"] + r["t_xfer"] for r in okr), 2) if okr else None,
                          "Mpx_per_s": round((cw + 128) * (chh + 128) / 1e6 / statistics.mean(r["ttfb"] + r["t_xfer"] for r in okr), 2) if okr else None,
                          "err": [r["err"] for r in times if r["status"] != "ok"]})
            print("  sweep", sweep[-1])
        res["results"]["geometry_sweep"] = sweep
    if args.controls:
        res["results"]["controls"] = "run `pilot --id S17` (expect NIR) and `pilot --id S15` (expect ALPHA) and compare the bands verdicts"
    (pd / "pilot.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["results"]["stitch_vs_direct"]["pass"] else 1



def do_verify(m, t) -> int:
    sys.path.insert(0, str(SCRIPTS / "qc")); import imagery_measure as im
    out = out_path(m, t)
    if not out.exists():
        sys.exit(f"{out} missing - assemble/mosaic first")
    held = local_root(m) / t["replaces"] if t.get("replaces") else (local_root(m) / t["complements"] if t.get("complements") else None)
    meas = im.measure_file(out, study_extent_3857=m["extent_3857"], held=held if (held and held.exists()) else None)
    decision = im.decide(t, meas)
    (acq_dir(m, t) / "measure.json").write_text(json.dumps(meas, indent=1, default=str), encoding="utf-8")
    (acq_dir(m, t) / "decision.json").write_text(json.dumps(decision, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"measure": {k: v for k, v in meas.items() if k != "sites"}, "decision": decision}, indent=1, default=str))
    return 0


def do_register(m, t) -> int:
    mf = acq_dir(m, t) / "measure.json"; df = acq_dir(m, t) / "decision.json"
    meas = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    dec = json.loads(df.read_text(encoding="utf-8")) if df.exists() else {}
    out = out_path(m, t)
    print("# --- YEAR_CATALOG entry (pipeline/phase4seg/config.py; append, never reformat) ---")
    print(json.dumps({"key": t.get("year_label"), "label": t.get("year_label"), "source": t.get("source_dir"),
                      "gsd_cm": meas.get("true_gsd_cm"), "bands": meas.get("bands"), "crs_epsg": meas.get("epsg"),
                      "coverage": f"{meas.get('study_coverage_pct')}% of study extent (measured {dt.date.today().isoformat()})",
                      "seg_tier": "semantic_only", "native_file": out.name}, indent=1))
    print("# --- Pixel_Size_And_Date row (scratch/imagery_pixelsize_date_build.py ROWS) ---")
    print(json.dumps({"file": out.name, "year_label": t.get("year_label"), "source": t.get("url") or t.get("base_url"),
                      "grid_px": meas.get("px"), "grid_units": meas.get("units"), "crs": f"EPSG:{meas.get('epsg')}",
                      "true_ground_cm": meas.get("true_gsd_cm"), "effective_cm": meas.get("effective_cm"),
                      "native_flight_cm": "(from the source's own statement; see manifest)", "px_evidence": "grid/true/effective MEASURED (acquire_imagery verify)",
                      "notes": f"decision {dec.get('verdict')}: {dec.get('reasons')}"}, indent=1))
    print("# --- MASTER flip: Already in data lake?=YES; Data-lake file=" + out.name + "; Replace with a better version?=" + str(dec.get("verdict")))
    print("# --- CHATLOG: did: " + f"{t['id']} {out.name} acquired; {dec.get('verdict')}; effective {meas.get('effective_cm')} cm; coverage {meas.get('study_coverage_pct')}%")
    return 0


# ----------------------------------------------------------------------------- main
def main(argv=None):
    argv = [a for a in (argv if argv is not None else sys.argv[1:]) if not (a == "-f" or a.endswith(".json"))]   # Colab rule 4
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "probe", "pilot", "fetch", "status", "assemble", "mosaic", "clip", "verify", "manifest", "mirror", "register", "clean"])
    ap.add_argument("--id"); ap.add_argument("--batch"); ap.add_argument("--manifest", default=str(MANIFEST_JSON))
    ap.add_argument("--approved", help='e.g. "2026-08-23 Kam: plan approved (ExitPlanMode)"')
    ap.add_argument("--workers", type=int); ap.add_argument("--core", type=int); ap.add_argument("--overlap", type=int)
    ap.add_argument("--strip", action="store_true"); ap.add_argument("--cooldown", type=float); ap.add_argument("--timeout", type=float)
    ap.add_argument("--compression", choices=["LZ77", "NONE"]); ap.add_argument("--regrid", action="store_true"); ap.add_argument("--rehash", action="store_true")
    ap.add_argument("--accept-empty", action="store_true"); ap.add_argument("--mirror", action="store_true"); ap.add_argument("--head", action="store_true")
    ap.add_argument("--box-m", type=float); ap.add_argument("--site"); ap.add_argument("--rendering", choices=["default", "none"])
    ap.add_argument("--controls", action="store_true"); ap.add_argument("--geometry-sweep", action="store_true")
    ap.add_argument("--window", type=int, default=300); ap.add_argument("--via", choices=["export", "download"], default="export")
    a = ap.parse_args(argv)
    if a.compression == "NONE": a.compression = None
    m = load_manifest(Path(a.manifest))
    if a.cmd == "plan":
        return do_plan(m, a.batch, mirror=a.mirror, head=a.head)
    ts = [target_by_id(m, a.id)] if a.id else (targets_in_batch(m, a.batch) if a.batch else [])
    if not ts:
        sys.exit("give --id or --batch")
    rc = 0
    for t in ts:
        mode = t.get("mode")
        if a.cmd == "probe" and mode == "export":
            p = do_probe(m, t); print(json.dumps(p, indent=1))
        elif a.cmd == "pilot" and mode == "export":
            rc |= do_pilot(m, t, a)
        elif a.cmd == "fetch":
            if not a.approved:
                sys.exit("fetch refused: --approved \"<date> Kam: <quote>\" is required (nothing downloads without approval)")
            if mode == "export" and a.via == "download":
                rc |= do_fetch_download(m, t, a)
            elif mode == "export":
                rc |= do_fetch(m, t, a)
            elif mode == "files":
                rc |= do_fetch_files(m, t, a)
            else:
                print(f"[{t['id']}] mode {mode}: nothing to fetch")
        elif a.cmd == "status":
            print(json.dumps(status_report(m, t, a.window), indent=1))
        elif a.cmd == "assemble" and mode == "export" and (acq_dir(m, t) / "download_items.json").exists():
            rc |= do_mosaic(m, t)
        elif a.cmd == "assemble" and mode == "export":
            rc |= do_assemble(m, t, accept_empty=a.accept_empty)
        elif a.cmd in ("assemble", "mosaic") and mode == "files" and t.get("mosaic"):
            rc |= do_mosaic(m, t)
        elif a.cmd in ("assemble", "clip") and mode == "files" and t.get("clip"):
            rc |= do_clip(m, t)
        elif a.cmd == "verify":
            rc |= do_verify(m, t)
        elif a.cmd == "manifest":
            rc |= do_manifest(m, t)
        elif a.cmd == "mirror":
            rc |= do_mirror(m, t)
        elif a.cmd == "register":
            rc |= do_register(m, t)
        elif a.cmd == "clean":
            rc |= do_clean(m, t)
        else:
            print(f"[{t['id']}] {a.cmd}: not applicable to mode {mode}")
    try:
        sys.path.insert(0, str(HERE)); from pipeline_log import write_step_log
        from phase4seg.config import BASE
        for base in (BASE, Path(r"G:\My Drive	reedata")):
            logs = base / "phase4" / "logs"
            if logs.exists():
                break
        if logs.exists():
            write_step_log(script="acquire_imagery", step=a.cmd, logs_dir=logs, targets=[t["id"] for t in ts], rc=rc, argv=argv)
    except Exception:
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
