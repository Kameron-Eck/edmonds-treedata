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

A download that is not a usable PDF at all never reaches binding: quarantine_new() writes those bytes STRAIGHT
into _quarantine/ under the same name, with a <same name>.reason.json beside them saying what was wrong, where
they came from and when. That sidecar is what makes a delete unnecessary
(Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9: an HTML error page written as
_litkb_staging/incoming/IFLA_2017_library-reference-model.pdf was removed with `rm -f` to free the name; now the
bytes are kept under a name of their own and the fetch can simply be repeated). Since S4.5 EVERY quarantine
writes that sidecar: to_quarantine() writes it itself (LITKB_WORKPLAN.md "### S4.5" item 8 — until then only
quarantine_new() did, and every binding refusal left a payload nobody could explain).

Whether bytes are a PDF is decided by litkb.acquire.accept, THE acceptance test (S4.5 item 5). pdf_shape() is
its thin caller for the paths that read it on every byte string acquisition receives: the header and trailer
rules only, in the old shape vocabulary (accept.shape says why only those).
"""
import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path

LITERATURE_ROOT = Path(os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture"))
STAGING = "_litkb_staging"
QUARANTINE = "_quarantine"
_INDEX_CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "litkb" / "disk_hash_index.json"
#: The sidecar beside a quarantined payload: `<same name>.reason.json`. `litkb.quarantine.SIDECAR_SUFFIX` is the
#: reader's spelling of the same suffix; qc/test_litkb_accept.py holds the two equal.
SIDECAR_SUFFIX = ".reason.json"


def pdf_shape(data):
    """What a byte string acquisition received IS, decided before anything is written. -> (shape, reason)

      "pdf"            the PDF signature (at the start, or after leading bytes such as a byte-order mark inside
                       the first 1,024) and a %%EOF near the end: a whole file, whatever it turns out to hold.
      "not-a-pdf"      no PDF signature at all - an HTML error page, a login page or a search page served under a
                       .pdf name. This is the shape of the 2026-09-15 incident
                       (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9): 295,657 bytes of HTML written as
                       IFLA_2017_library-reference-model.pdf.
      "truncated-pdf"  the signature is there and there is no %%EOF near the end: the transfer stopped before
                       the trailer, so the file has no xref and no reader can open it.

    The two failures are told apart because their CAUSES differ - a wrong URL against a dropped connection - and
    whoever reads _quarantine/ should learn which without opening the file. The rules themselves are the
    acceptance test's (`litkb.acquire.accept.shape`, its header and trailer steps); this is their thin caller,
    kept so every path that read pdf_shape keeps its contract. Imported inside the function, like the HTML
    check it reaches: `acquire` must not import `extract` at module scope."""
    from litkb.acquire import accept as _accept

    return _accept.shape(data)


def reason_path(quarantined):
    """Where the sidecar of a quarantined payload lives: `<same name>.reason.json`."""
    return Path(quarantined).with_suffix(SIDECAR_SUFFIX)


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
        """<directory>/<stem><suffix>, or <stem>.2<suffix>, .3 ... — the first name that does not exist, and
        whose .txt companion and .reason.json sidecar do not exist either (a sidecar left beside no payload
        would otherwise refuse the sidecar of the next file given that name)."""
        d = Path(directory)
        cand = d / f"{stem}{suffix}"
        n = 2
        while cand.exists() or cand.with_suffix(".txt").exists() or reason_path(cand).exists():
            cand = d / f"{stem}.{n}{suffix}"
            n += 1
        return cand

    def extract(self, pdf):
        """The pdftotext -layout extract beside `pdf`, when the tool is installed and can read the file.
        -> the .txt path, or None. One home: every landing path writes its extract through this."""
        txt = Path(pdf).with_suffix(".txt")
        self.guard_new(txt)
        try:
            subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return txt if txt.exists() else None

    def land(self, data, stem, sha):
        """Write downloaded bytes into incoming/ and the pdftotext -layout extract beside them, at once
        (the convention: the .txt is the durable copy and is written the moment a PDF lands)."""
        pdf = self.write_new(self.free_name(self.incoming, f"{stem}.{sha[:12]}"), data)
        return pdf, self.extract(pdf)

    def write_reason(self, quarantined, reason):
        """The sidecar beside a quarantined file: WHY it is there, as JSON, at <same name>.reason.json.

        It goes through write_new() like every other byte this module writes - there is no second kind of write
        here, and `open(..., "w")` / Path.write_text are exactly what qc/test_litkb_p2.py's scan refuses."""
        body = json.dumps(reason, indent=2, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return self.write_new(reason_path(quarantined), body)

    def quarantine_new(self, data, stem, label, sha, reason):
        """Bytes that are NOT a usable paper - an HTML error page served as a .pdf, a truncated download, a bot
        challenge - written straight into _quarantine/ under the name to_quarantine() would have given them, with
        the reason sidecar beside them. -> (pdf, txt|None, reason path)

        They never touch incoming/ and they are never discarded: keeping a bad download, named for what is wrong
        with it, is what makes deleting one unnecessary (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9)."""
        dst = self.free_name(self.quarantine, f"{stem}__{label}__{sha[:12]}")
        pdf = self.write_new(dst, data)
        return pdf, self.extract(pdf), self.write_reason(pdf, reason)

    def to_quarantine(self, pdf, txt, stem, status, sha, suffix=None, reason=None):
        """Move a file acquisition created into _quarantine/ AND write its .reason.json beside it.
        -> (payload, txt|None); the sidecar is at reason_path(payload).

        `suffix` (default `.pdf`, which is every acquisition caller) keeps a quarantined file's
        own extension: the staging reaper moves `.download`, `.html` and `.txt` bytes, and naming
        an HTML error page `.pdf` in _quarantine/ is the exact mislabelling this module's docstring
        is about (Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md §8.9).

        `reason` is the caller's sidecar (every caller that knows WHY passes it: `run._reason`'s shape, the
        hunt's, the reaper's). A caller that passes none still gets one — the status, the sha256, where the
        file came from and when — because the sidecar is written HERE, once, for every caller (S4.5 item 8:
        `to_quarantine` used to write only the filename, and the four acquisition call sites that reach it
        left 25 of the store's 69 payloads with no reason). The sidecar path is checked BEFORE the move, so a
        move that could not take its sidecar with it is never made."""
        dst = self.free_name(self.quarantine, f"{stem}__{status}__{sha[:12]}", suffix or ".pdf")
        self.guard_new(reason_path(dst))
        was = self.rel(pdf) if self._inside(pdf, self.root) else str(pdf)
        out = self.move_new(pdf, dst)
        tout = self.move_new(txt, dst.with_suffix(".txt")) if txt else None
        body = reason if reason is not None else {
            "status": status, "label": status, "sha256": sha, "stem": stem, "moved_from": was,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "reason_source": "Store.to_quarantine (the caller passed no reason)"}
        # BEGIN guard: every quarantine move writes its reason sidecar
        self.write_reason(out, body)
        # END guard: every quarantine move writes its reason sidecar
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
