r"""One-shot READ-ONLY lineage stamper for pre-E06 corrected-label overlays.

Backfills `canopy_additions_{year}.lineage.json` beside the existing artifact
WITHOUT touching the .tif: the overlay is keyed into the tile signature by
path+size+mtime (`_add_canopy_mask_sig`, tiling.py), so re-running the builder
(fixed filename → mtime bump) would spuriously invalidate every overlay-keyed
tile cache. Fields come from the existing .txt sidecar; build_date comes from
the step-log filename (never the Drive mtime — the phantom-M lesson).

Future builds are born stamped by `_write_summary` in
pipeline/phase4_build_corrected_labels.py; this script exists only for the
artifacts that predate it (today: exactly canopy_additions_2016).
"""
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

DATA = Path(r"G:\My Drive\treedata")
LAB_DIR = DATA / "phase4" / "labels_corrected"
LOGS = DATA / "phase4" / "logs"


def _sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _txt_field(text, key):
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def stamp(tif: Path) -> Path:
    year = tif.stem.rsplit("_", 1)[-1]
    txt = tif.with_suffix(".txt")
    body = txt.read_text(encoding="utf-8") if txt.exists() else ""
    rule = _txt_field(body, "rule") or ""
    m = re.search(r"NDVI>=([\d.]+) AND height>=([\d.]+)", rule)
    counts = {}
    for label, key in (("imaged px", "imaged"), ("ADD canopy(1)", "add"),
                       ("IGNORE   (2)", "ignore"), ("no change(0)", "nochange"),
                       ("nodata (255)", "nodata")):
        mm = re.search(rf"^\s*{re.escape(label)}\s*:\s*([\d,]+)", body, re.M)
        if mm:
            counts[key] = int(mm.group(1).replace(",", ""))
    build_date = None
    # pre-2026-08-20 step logs live in the FROZEN Drive Scripts copy (read-only
    # fallback — never edit that tree); newer ones in phase4/logs.
    for logdir in (LOGS, DATA / "Scripts" / "logs"):
        logs = sorted(logdir.glob(f"phase4_build_corrected_labels_{year}_*.log"))
        if logs:
            ts = re.search(r"_(\d{4})(\d{2})(\d{2})_\d{6}\.log$", logs[-1].name)
            if ts:
                build_date = "-".join(ts.groups())
            break
    lineage = {
        "source_year": year,
        "imagery": _txt_field(body, "imagery"),
        "chm": _txt_field(body, "chm"),
        "rule": rule or None,
        "veg_thresh": float(m.group(1)) if m else None,
        "min_height_m": float(m.group(2)) if m else None,
        "holdout": _txt_field(body, "holdout"),
        "pixel_counts": counts or None,
        "size": tif.stat().st_size,
        "sha256": _sha256(tif),
        "build_date": build_date,
        "builder_script": "phase4_build_corrected_labels.py",
        "stamped_by": "qc/instruments/stamp_label_lineage.py (read-only backfill, "
                      + dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d") + ")",
    }
    out = tif.with_suffix(".lineage.json")
    out.write_text(json.dumps(lineage, indent=2), encoding="utf-8")
    print(f"stamped {out.name}: size={lineage['size']:,} sha256={lineage['sha256'][:16]}… "
          f"build_date={build_date}")
    return out


def main():
    tifs = sorted(LAB_DIR.glob("canopy_additions_*.tif"))
    if not tifs:
        sys.exit(f"no overlays under {LAB_DIR}")
    for t in tifs:
        if t.with_suffix(".lineage.json").exists():
            print(f"already stamped: {t.name} — skipped (delete the .json to re-stamp)")
            continue
        stamp(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
