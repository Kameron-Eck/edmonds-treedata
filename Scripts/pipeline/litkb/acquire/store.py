"""The literature store as acquisition sees it: staging, quarantine, and hash indexes. NO DELETE PATH.

On 2026-09-12 an acquisition run deleted 149 PDFs (Scripts/docs/LITERATURE_CONVENTION.md). So this module,
and every acquisition module, holds no call that deletes, truncates or overwrites a file: no os.remove,
os.unlink, Path.unlink, shutil.rmtree, os.rmdir, os.replace, and no open(..., "w"/"wb") under the store.
qc/test_litkb_p2.py scans the acquisition and admission sources for those calls.

Every write goes through guard_new():
  * the target must lie under <root>/_litkb_staging/ or <root>/_quarantine/, never a topic folder
    (Validation/, ASPP/, Labeling/, other/), and never the store root itself;
  * the target must not exist; bytes are written with open(..., "xb") (create, fail if present) and files are
    moved with os.rename, which refuses an existing target on Windows (and the guard checks first anyway).
A file is moved only if it lies under staging: files acquisition did not create are never moved.

Layout (judgement call, Reports/LITKB_P2_REPORT_2026-09-14.md): a download lands in
_litkb_staging/incoming/, its .txt extract beside it at once; a file that binds is filed to
_litkb_staging/filed/<stem>.pdf (+ .txt) and recorded in the database with that rel_path; a file that does not
bind moves to _quarantine/<stem>__<status>__<sha12>.pdf (+ .txt). Moving filed papers into the topic folders
is P3's, together with the manifest export.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

LITERATURE_ROOT = Path(os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture"))
STAGING = "_litkb_staging"
QUARANTINE = "_quarantine"
_INDEX_CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "litkb" / "disk_hash_index.json"


class StoreRefused(RuntimeError):
    """A write that would leave staging/quarantine or touch an existing file."""


class Store:
    def __init__(self, root=None, *, index_cache=None):
        self.root = Path(root or LITERATURE_ROOT).resolve()
        self.staging = self.root / STAGING
        self.incoming = self.staging / "incoming"
        self.filed = self.staging / "filed"
        self.quarantine = self.root / QUARANTINE
        self.index_cache = Path(index_cache) if index_cache else _INDEX_CACHE

    # ── guards ────────────────────────────────────────────────────────────────────────────
    def _inside(self, path, base):
        try:
            Path(path).resolve().relative_to(base.resolve())
            return True
        except ValueError:
            return False

    def guard_new(self, path):
        """The one gate for every write and every move target."""
        p = Path(path).resolve()
        # BEGIN guard: store writes only into staging or quarantine
        if not (self._inside(p, self.staging) or self._inside(p, self.quarantine)):
            raise StoreRefused(f"refused: {p} is outside {self.staging} and {self.quarantine}")
        # END guard: store writes only into staging or quarantine
        # BEGIN guard: store never overwrites
        if p.exists():
            raise StoreRefused(f"refused: {p} already exists; nothing in the literature store is overwritten")
        # END guard: store never overwrites
        return p

    def rel(self, path):
        return Path(path).resolve().relative_to(self.root).as_posix()

    # ── writes (create-only) ──────────────────────────────────────────────────────────────
    def write_new(self, path, data):
        p = self.guard_new(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "xb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        return p

    def move_new(self, src, dst):
        """Move a file acquisition created (under staging) to a new path under staging or quarantine."""
        s = Path(src).resolve()
        if not self._inside(s, self.staging):
            raise StoreRefused(f"refused: {s} was not created by acquisition (not under {self.staging}); it is never moved")
        d = self.guard_new(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        os.rename(s, d)
        return d

    def free_name(self, directory, stem, suffix=".pdf"):
        """<directory>/<stem><suffix>, or <stem>.2<suffix>, .3 ... — the first name that does not exist."""
        d = Path(directory)
        cand = d / f"{stem}{suffix}"
        n = 2
        while cand.exists() or cand.with_suffix(".txt").exists():
            cand = d / f"{stem}.{n}{suffix}"
            n += 1
        return cand

    def land(self, data, stem, sha):
        """Write downloaded bytes into incoming/ and the pdftotext -layout extract beside them, at once
        (the convention: the .txt is the durable copy and is written the moment a PDF lands)."""
        pdf = self.write_new(self.free_name(self.incoming, f"{stem}.{sha[:12]}"), data)
        txt = pdf.with_suffix(".txt")
        self.guard_new(txt)
        try:
            subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return pdf, (txt if txt.exists() else None)

    def to_quarantine(self, pdf, txt, stem, status, sha):
        dst = self.free_name(self.quarantine, f"{stem}__{status}__{sha[:12]}")
        out = self.move_new(pdf, dst)
        tout = self.move_new(txt, dst.with_suffix(".txt")) if txt else None
        return out, tout

    def to_filed(self, pdf, txt, stem):
        dst = self.free_name(self.filed, stem)
        out = self.move_new(pdf, dst)
        tout = self.move_new(txt, dst.with_suffix(".txt")) if txt else None
        return out, tout

    # ── hash index of every PDF on disk (read-only) ───────────────────────────────────────
    def disk_index(self):
        """{"sha256": {sha: [rel paths]}, "md5": {md5: [rel paths]}} over every *.pdf under the root, topic
        folders, staging and quarantine alike. Hashes are cached OUTSIDE the store, keyed by path, size and
        mtime, so a changed file is re-hashed."""
        try:
            cache = json.loads(self.index_cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        fresh, by_sha, by_md5 = {}, {}, {}
        for p in sorted(self.root.rglob("*.pdf")):
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(self.root).as_posix()
            key = f"{rel}|{st.st_size}|{st.st_mtime_ns}"
            hit = cache.get(key)
            if not hit:
                h256, h5 = hashlib.sha256(), hashlib.md5()
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h256.update(chunk)
                        h5.update(chunk)
                hit = {"sha256": h256.hexdigest(), "md5": h5.hexdigest()}
            fresh[key] = hit
            by_sha.setdefault(hit["sha256"], []).append(rel)
            by_md5.setdefault(hit["md5"], []).append(rel)
        try:
            self.index_cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.index_cache.with_name(self.index_cache.name + ".new")
            tmp.write_text(json.dumps(fresh), encoding="utf-8")   # store-scan: allow (cache outside the store)
            # the cache lives outside the literature store, so replacing it touches no paper
            os.replace(tmp, self.index_cache)   # store-scan: allow (cache outside the store)
        except OSError:
            pass
        return {"sha256": by_sha, "md5": by_md5}


def file_facts(path):
    """sha256, md5, bytes of a file (read-only)."""
    h256, h5, n = hashlib.sha256(), hashlib.md5(), 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h256.update(chunk)
            h5.update(chunk)
            n += len(chunk)
    return {"sha256": h256.hexdigest(), "md5": h5.hexdigest(), "bytes": n}
