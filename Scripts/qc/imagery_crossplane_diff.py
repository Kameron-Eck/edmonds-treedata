r"""
╔══════════════════════════════════════════════════════════════════╗
  CROSS-PLANE DIFF — does the Drive copy of every raster still agree with
  the D: original it was mirrored from?
  Edmonds Temporal Active Learning Pipeline

  WHY THIS EXISTS  (2026-08-24, after the acquisition campaign)
  ------------------------------------------------------------------
  The campaign mirrored ~29 new rasters (hundreds of GB) from the local D:
  archive to the Drive data lake. Every copy was verified by SIZE only
  (`acquire_imagery.py mirror` compares st_size after shutil.copy2). A size
  check cannot see a copy that is the right length and the wrong bytes —
  the exact failure a FUSE-mounted, upload-cached, quota-throttled network
  drive is most likely to produce.

  Hashing hundreds of GB back over that mount would take many hours of
  bandwidth we do not have. This does the next-best independent thing, and
  it costs nothing extra because both halves already exist:

      `qc/imagery_qc_suite.py integrity` was run TWICE —
        * locally, where imagery_roots() resolves D:\edmonds-pipeline\Imagery
        * on the Colab VM, where it resolves the Drive data lake
      Two independent readings of what are supposed to be the same files.

  This joins those two CSVs per file and diffs every measured property:
  dimensions, band count, CRS, true GSD, byte size, the zero fraction and
  the distinct-DN count of band 1, and the constant-fill verdict. The last
  two are the interesting ones — they are computed from PIXEL CONTENT, so a
  silently corrupted copy changes them even when the header still matches.

  WHAT A DISAGREEMENT MEANS
    bytes differ            -> the copy is not the file (re-mirror)
    width/height/bands/epsg -> a truncated or partially-written copy
    zero_frac / unique_b1   -> SAME header, DIFFERENT PIXELS: corruption
    fill                    -> one plane reads an empty shell
  Agreement is NOT proof of byte-identity (two different files can share
  these statistics), but disagreement IS proof of a problem. Stated plainly
  so nobody reads a clean run as a checksum.

  USAGE
    py -3.12 qc/imagery_crossplane_diff.py
      --local  DIR   default D:\edmonds-pipeline\treedata\phase4\qc
      --drive  DIR   default "G:\My Drive\treedata\phase4\qc"
      --date   D     default: today (picks imagery_qc_integrity_<date>.csv)
      --out    F     default <local>/imagery_crossplane_diff_<date>.csv

  EXIT CODE
    0 = every file present on both planes agrees on every property.
    1 = at least one disagreement (a corruption finding).
    2 = inputs missing (one of the two runs has not finished).
╚══════════════════════════════════════════════════════════════════╝
"""
import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

# Properties compared per file. HEADER facts first, then the two that are derived from
# pixel CONTENT (a corrupt copy with an intact header shows up only in those).
HEADER_COLS = ["bytes", "width", "height", "bands", "epsg", "true_gsd_cm"]
CONTENT_COLS = ["zero_frac", "unique_b1", "fill"]
COMPARE = HEADER_COLS + CONTENT_COLS
# zero_frac is a float measured off a decimated read; identical files can differ in the
# last digit through float formatting alone, so it gets a tolerance, everything else is exact.
TOL = {"zero_frac": 1e-4, "true_gsd_cm": 1e-3}


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["file"]: r for r in csv.DictReader(f) if r.get("file")}


def differs(col: str, a: str, b: str) -> bool:
    a, b = (a or "").strip(), (b or "").strip()
    if a == b:
        return False
    if a == "" or b == "":
        return True
    if col in TOL:
        try:
            return abs(float(a) - float(b)) > TOL[col]
        except ValueError:
            return True
    return True


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", type=Path, default=Path(r"D:/edmonds-pipeline/treedata/phase4/qc"))
    ap.add_argument("--drive", type=Path, default=Path(r"G:/My Drive/treedata/phase4/qc"))
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)

    lp = a.local / f"imagery_qc_integrity_{a.date}.csv"
    dp = a.drive / f"imagery_qc_integrity_{a.date}.csv"
    L, D = load(lp), load(dp)
    print("CROSS-PLANE DIFF — D: originals vs Drive data-lake copies")
    print(f"  local (D:)   {lp}  -> {len(L)} rows")
    print(f"  drive (lake) {dp}  -> {len(D)} rows")
    if not L or not D:
        print("\n  MISSING INPUT — one of the two integrity runs has not written its CSV yet.")
        return 2
    if len(D) < 5:
        print(f"\n  WARNING: the Drive-side CSV has only {len(D)} row(s) — that is the bootstrap")
        print("  smoke run, not the full sweep. Wait for the VM run to finish before trusting this.")

    both = sorted(set(L) & set(D))
    only_local = sorted(set(L) - set(D))
    only_drive = sorted(set(D) - set(L))

    rows, bad = [], 0
    for f in both:
        l_, d_ = L[f], D[f]
        diffs = [c for c in COMPARE if differs(c, l_.get(c), d_.get(c))]
        content = [c for c in diffs if c in CONTENT_COLS]
        rec = dict(file=f, agree="YES" if not diffs else "NO",
                   differing="; ".join(diffs),
                   severity=("" if not diffs else
                             "CORRUPTION (same header, different pixels)" if content and not [c for c in diffs if c in HEADER_COLS]
                             else "COPY MISMATCH"))
        for c in COMPARE:
            rec[f"local_{c}"] = l_.get(c)
            rec[f"drive_{c}"] = d_.get(c)
        rows.append(rec)
        if diffs:
            bad += 1
            print(f"  DIFFER  {f:34s} {rec['severity']}")
            for c in diffs:
                print(f"            {c:14s} local={l_.get(c)!r}  drive={d_.get(c)!r}")

    # A file missing from the Drive-side CSV is NOT evidence that it is missing from Drive:
    # the VM run may legitimately have measured a subset (the 2026-08-24 run skipped four
    # 11-48 GB pre-campaign orthos whose decimated read touches every byte over FUSE). Stat
    # the lake directly so "not measured" is never reported as "not present".
    lake = [Path(r"G:/My Drive/treedata/Full_Image/Pipeline Imagery"),
            Path(r"G:/My Drive/treedata/Full_Image/Pipeline Imagery/native"),
            Path("/content/drive/MyDrive/treedata/Full_Image/Pipeline Imagery")]
    for f in only_local:
        on_lake = any((d / f).exists() for d in lake if d.exists())
        if on_lake:
            # CAREFUL: the local G: mount is NOT the lake. Google Drive for desktop shows files
            # that are still queued for upload exactly as it shows files that are in the cloud, so
            # a hit here means "present in the local Drive VIEW" and cannot distinguish the two.
            # Measured 2026-08-24: the 3-inch rasters were visible on G: while a Colab VM reading
            # the actual cloud could not see them at all — they were still uploading. Only the
            # Drive-side (VM) run can settle it, which is why absence there is reported this way.
            rows.append(dict(file=f, agree="NOT MEASURED ON DRIVE",
                             severity="visible in the local Drive view but NOT measured on the Drive plane — "
                                      "may be a pending upload rather than a file in the cloud; confirm from a VM"))
            print(f"  not measured on the Drive plane (visible in the local mount — may be a pending upload)  {f}")
        else:
            rows.append(dict(file=f, agree="NOT ON DRIVE", severity="no data-lake copy — single-copy on D: only"))
            print(f"  NO DRIVE COPY  {f}")
    for f in only_drive:
        rows.append(dict(file=f, agree="NOT ON D:", severity="present in the lake, absent locally"))
        print(f"  NOT ON D:      {f}")

    out = a.out or (a.local / f"imagery_crossplane_diff_{a.date}.csv")
    cols = ["file", "agree", "severity", "differing"] + [f"{p}_{c}" for c in COMPARE for p in ("local", "drive")]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n  compared on both planes : {len(both)}")
    print(f"  agree on every property : {len(both) - bad}")
    print(f"  DISAGREE                : {bad}")
    print(f"  on D: only              : {len(only_local)}")
    print(f"  in the lake only        : {len(only_drive)}")
    print(f"  -> {out}")
    print("\n  NOTE: agreement is strong evidence, not a checksum — two different files can share")
    print("  these statistics. Disagreement, however, is proof of a problem.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
