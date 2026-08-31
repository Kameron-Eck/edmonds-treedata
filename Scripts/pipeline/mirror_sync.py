"""
mirror_sync.py — checksum-manifested backup plane (overhaul P1 manifests / P9 sync).

Modes:
    py -3.12 mirror_sync.py --manifest D:\\edmonds-pipeline\\backup\\phase3
        Walk the dir, write MANIFEST.sha256 (relpath<TAB>size<TAB>sha256).
    py -3.12 mirror_sync.py --verify D:\\edmonds-pipeline\\backup\\phase3
        Re-hash and compare against MANIFEST.sha256; exit 1 on any mismatch.
    py -3.12 mirror_sync.py --verify-sizes D:\\edmonds-pipeline\\backup\\phase3
        Fast pass: sizes only (for multi-100GB dirs between full verifies).

The P9 sync mode (one-way Drive→D: robocopy wrapper with a preserved-exceptions
list for the D:-only files, replacing the 2026-07-05 hand-robocopy) is the next
step and will live here; manifests are its foundation.
"""
from phase4seg.names import clean_argv
import argparse
import hashlib
import sys
from pathlib import Path

MANIFEST = "MANIFEST.sha256"


def _sha(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _files(root):
    for p in sorted(root.rglob("*")):
        if (p.is_file() and p.name != MANIFEST and not p.name.endswith(".log")
                and ".part." not in p.name):    # E02: skip atomic-publish staging files
            yield p


def write_manifest(root):
    root = Path(root)
    out = []
    total = 0
    for p in _files(root):
        size = p.stat().st_size
        total += size
        print(f"  hashing {p.relative_to(root)}  ({size/1e6:.0f} MB)", flush=True)
        out.append(f"{p.relative_to(root).as_posix()}\t{size}\t{_sha(p)}")
    (root / MANIFEST).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{root}: {len(out)} files, {total/1e9:.1f} GB → {MANIFEST}")


def _parse_manifest(text):
    """Two formats share the MANIFEST.sha256 name: this script's `relpath<TAB>size<TAB>sha256`, and the
    plain `sha256sum` form `<sha256>  <relpath>` the 2026-08-22 lidar directories were landed with (no
    size column, so size checks are skipped for those lines). Returns {rel: (size|None, sha)}."""
    want = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if "\t" in line:
            rel, size, sha = line.split("\t")
            want[rel] = (int(size), sha)
        else:
            sha, rel = line.split(None, 1)
            want[rel.strip().lstrip("*")] = (None, sha)
    return want


def verify(root, sizes_only=False):
    root = Path(root)
    mf = root / MANIFEST
    if not mf.exists():
        sys.exit(f"no {MANIFEST} in {root} — run --manifest first")
    want = _parse_manifest(mf.read_text(encoding="utf-8"))
    bad, missing = [], []
    for rel, (size, sha) in want.items():
        p = root / rel
        if not p.exists():
            missing.append(rel)
            continue
        if size is not None and p.stat().st_size != size:
            bad.append((rel, "size"))
            continue
        if size is None and sizes_only:
            bad.append((rel, "no-size-in-manifest(sha256sum form; run --verify)"))
            continue
        if not sizes_only and _sha(p) != sha:
            bad.append((rel, "sha256"))
    extra = [str(p.relative_to(root)) for p in _files(root)
             if p.relative_to(root).as_posix() not in want]
    mode = "sizes-only" if sizes_only else "full sha256"
    print(f"{root}: {len(want)} manifested — {len(missing)} missing, "
          f"{len(bad)} mismatched, {len(extra)} unmanifested extras ({mode})")
    for rel in missing:
        print(f"  MISSING  {rel}")
    for rel, kind in bad:
        print(f"  BAD-{kind.upper()}  {rel}")
    if missing or bad:
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--manifest", metavar="DIR")
    g.add_argument("--verify", metavar="DIR")
    g.add_argument("--verify-sizes", metavar="DIR")
    args = ap.parse_args(clean_argv())
    if args.manifest:
        write_manifest(args.manifest)
    elif args.verify:
        sys.exit(verify(args.verify))
    else:
        sys.exit(verify(args.verify_sizes, sizes_only=True))


if __name__ == "__main__":
    main()
