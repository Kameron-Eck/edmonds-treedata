r"""Verify a Colab formula result archive, then park its rows for P5's ingest. LOCAL ONLY.

Colab writes artifacts; ingest is local. This module is the gate between the two, and it is
deliberately suspicious of everything that crossed the wire.

THE FOUR REFUSALS (each one is a kill the report must show firing):

1. **The bytes did not arrive intact.** Before anything is read, the archive is checked
   against the hash the worker wrote beside it, and — when the file is still on the lake —
   against the SERVER-SIDE md5 that ``rclone md5sum`` reports through the service account.
   That is the pattern ``gen_vm_bootstrap.py``'s write canary already uses, and for the
   reason its comment gives: the v1 canary read its own vfs cache and was blind to a failed
   upload. A local read of a FUSE-mounted file proves nothing about what Drive holds.
2. **No done marker.** The worker writes ``DONE`` last, holding the sha256 of the other two
   members. An archive without it is an interrupted run; an archive whose marker disagrees
   with its members is a corrupted one. Both are refused, unread.
3. **The crop count does not match the shard.** A result is only usable against the manifest
   it was produced from, so the returned ``crop_id`` set must equal the shard's.
4. **A row claims success with no LaTeX.** The worker already records those as ``failed``
   (docling returns empty strings on an engine error and still reports success). This is the
   belt to that suspenders: a row with ``status="ok"`` and empty ``latex`` fails the whole
   archive rather than entering the record.

WHAT IT WRITES. Rows go to the SAME metrics JSONL the other extraction stages park in until
P5's ingest — ``docling.append_metrics`` — one row per result archive, plus a per-crop
``latex`` JSONL keyed by ``(file, page, self_ref, bbox_canonical)`` so the LaTeX patches onto
a DoclingDocument exactly the way ``merge_formula_latex`` patches it.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile

from . import docling as _dg
from .colab_formula_worker import DONE_NAME, RESULTS_NAME, WORKER_NAME, done_marker


class ResultRefused(Exception):
    """A returned archive did not pass verification. Nothing was ingested."""


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def md5_file(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def server_md5(remote, rclone="rclone", timeout=300):
    """``rclone md5sum <remote>`` -> the hex digest Drive holds, or None.

    Server-side, through the service account, independent of every cache in the write path.
    ``md5sum`` and not ``lsjson --hashes``: the flag does not exist on the VM's rclone build
    (measured 2026-08-26 — gen_vm_bootstrap.py's canary comment), and the same binary is what
    this side calls.
    """
    try:
        r = subprocess.run([rclone, "md5sum", remote], capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    parts = (r.stdout or "").split()
    return parts[0] if parts else None


# ── verification ────────────────────────────────────────────────────────────────────────

def verify_result(result_zip, shard_manifest=None, expect_sha256=None, remote=None,
                  rclone="rclone"):
    """Refuse or accept one result archive. -> (worker record, [row]).

    Raises :class:`ResultRefused` on any of the four refusals. It reads members only after
    the marker has been checked, so a corrupted archive is never partially believed.
    """
    if not os.path.exists(result_zip):
        raise ResultRefused(f"no such result archive: {result_zip}")

    # (1) the bytes. Sidecar first — it is written by the worker after the archive closes.
    want = expect_sha256
    side = result_zip + ".sha256"
    if want is None and os.path.exists(side):
        with open(side, encoding="utf-8") as fh:
            want = fh.read().split()[0]
    got = sha256_file(result_zip)
    if want and got != want:
        raise ResultRefused(
            f"{os.path.basename(result_zip)}: sha256 {got} != the {want} recorded beside it "
            f"— the archive is corrupt or truncated; nothing ingested")
    if remote:
        srv = server_md5(remote, rclone)
        local_md5 = md5_file(result_zip)
        if srv is None:
            raise ResultRefused(
                f"{remote}: rclone reported no server-side md5 — a local read of a FUSE "
                f"mount proves nothing about what Drive holds (gen_vm_bootstrap.py's write "
                f"canary v1 was blind to exactly this)")
        if srv != local_md5:
            raise ResultRefused(f"{remote}: server-side md5 {srv} != local {local_md5} — the "
                                f"upload is incomplete or the local copy is stale")

    try:
        z = zipfile.ZipFile(result_zip)
    except zipfile.BadZipFile as e:
        raise ResultRefused(f"{os.path.basename(result_zip)}: not a readable archive ({e})")
    with z:
        names = set(z.namelist())
        # (2) the done marker
        if DONE_NAME not in names:
            raise ResultRefused(
                f"{os.path.basename(result_zip)}: no {DONE_NAME} marker — the worker writes "
                f"it LAST, so this is an interrupted run and its rows are not a record")
        missing = {RESULTS_NAME, WORKER_NAME} - names
        if missing:
            raise ResultRefused(f"{os.path.basename(result_zip)}: missing {sorted(missing)}")
        results_bytes = z.read(RESULTS_NAME)
        worker_bytes = z.read(WORKER_NAME)
        marker = z.read(DONE_NAME)
        if marker != done_marker(results_bytes, worker_bytes):
            raise ResultRefused(
                f"{os.path.basename(result_zip)}: the {DONE_NAME} marker does not match the "
                f"members it covers — the archive changed after the worker closed it")

    record = json.loads(worker_bytes.decode("utf-8"))
    rows = [json.loads(ln) for ln in results_bytes.decode("utf-8").splitlines() if ln.strip()]

    # (3) the crop set
    if shard_manifest is not None:
        want_ids = set(shard_manifest["crop_ids"])
        got_ids = {r["crop_id"] for r in rows}
        if got_ids != want_ids:
            raise ResultRefused(
                f"{os.path.basename(result_zip)}: {len(got_ids)} crops returned against "
                f"{len(want_ids)} in shard {shard_manifest['shard_id']} "
                f"({len(want_ids - got_ids)} missing, {len(got_ids - want_ids)} unknown)")
        if record.get("shard_id") != shard_manifest["shard_id"]:
            raise ResultRefused(
                f"shard id mismatch: result says {record.get('shard_id')!r}, manifest says "
                f"{shard_manifest['shard_id']!r}")

    # (4) no empty LaTeX recorded as success
    bad = [r["crop_id"] for r in rows
           if r.get("status") == "ok" and not (r.get("latex") or "").strip()]
    if bad:
        raise ResultRefused(
            f"{os.path.basename(result_zip)}: {len(bad)} rows claim status=ok with no LaTeX "
            f"(first {bad[0]}) — docling returns empty strings on an engine error and still "
            f"reports success; an empty LaTeX is a FAILURE, never an enriched region")
    return record, rows


# ── ingest ──────────────────────────────────────────────────────────────────────────────

def ingest(result_zip, shard_manifest, metrics_path, latex_path, remote=None,
           rclone="rclone", seen_shards=()):
    """Verify, then park. -> the metrics row that was appended.

    ``seen_shards`` makes the re-upload skip explicit (kill 4): a shard whose sha256 has
    already been ingested is a no-op, because the crops are content-addressed and decoding
    them again could only produce the same answer at GPU cost.

    ``shard_manifest`` must carry ``shard_sha256`` — :func:`formula_shards.read_manifest`
    fills it from the archive path, since the hash of a closed archive cannot live inside it.
    A manifest without one is refused rather than silently skipping the skip.
    """
    if not shard_manifest.get("shard_sha256"):
        raise ResultRefused(
            f"shard {shard_manifest.get('shard_id')!r} has no shard_sha256 — read it with "
            f"formula_shards.read_manifest(<shard path>), which computes the archive hash "
            f"the embedded manifest cannot carry; without it the re-upload skip is inert")
    if shard_manifest.get("shard_sha256") in set(seen_shards):
        return {"status": "skipped", "reason": "shard sha256 already ingested",
                "shard_id": shard_manifest["shard_id"],
                "shard_sha256": shard_manifest.get("shard_sha256")}
    record, rows = verify_result(result_zip, shard_manifest, remote=remote, rclone=rclone)

    by_id = {c["crop_id"]: c for c in shard_manifest["crops"]}
    os.makedirs(os.path.dirname(os.path.abspath(latex_path)) or ".", exist_ok=True)
    n = 0
    with open(latex_path, "a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            if r.get("status") != "ok":
                continue
            c = by_id.get(r["crop_id"], {})
            fh.write(json.dumps({
                "crop_id": r["crop_id"],
                "file": c.get("file", r.get("file")),
                "file_sha256": c.get("file_sha256"),
                "page": c.get("page", r.get("page")),
                "self_ref": c.get("self_ref"),
                # merge_formula_latex keys on (page, bbox rounded to 1 pt) in the canonical
                # frame — carried here so the patch-back is the same join, not a new one.
                "bbox_canonical": c.get("bbox_canonical"),
                "native_text": c.get("native_text"),
                "latex": r["latex"],
                "confidence": r.get("confidence"),
                "confidence_basis": r.get("confidence_basis"),
                "shard_id": shard_manifest["shard_id"],
                "batch_size": r.get("batch_size"),
            }, sort_keys=True, ensure_ascii=False) + "\n")
            n += 1

    row = dict(record)
    row.update({
        "tool": "docling-%s" % (record.get("versions", {}).get("docling") or "unknown"),
        "stage": "3-formula-colab",
        "shard_manifest_sha256": shard_manifest.get("shard_sha256"),
        "result_sha256": sha256_file(result_zip),
        "latex_rows_written": n,
        "verified": "done marker + sha256" + (" + server-side md5" if remote else ""),
    })
    _dg.append_metrics(row, metrics_path)
    return row


def ingested_shard_hashes(metrics_path):
    """The ``shard_sha256`` of every result already parked — the skip set for :func:`ingest`."""
    out = set()
    if not os.path.exists(metrics_path):
        return out
    with open(metrics_path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            for k in ("shard_manifest_sha256", "shard_sha256"):
                if r.get(k):
                    out.add(r[k])
    return out
