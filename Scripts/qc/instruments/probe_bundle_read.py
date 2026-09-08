"""probe_bundle_read.py -- why did a 512 MB tile bundle take 119.2 s to read?

WHAT THIS ANSWERS, and why it is a separate instrument rather than a queue job.
experiments/bundle_validation_2017k.yaml scored R1 FAIL: the engine's tile-bundle
read of phase4/tiles/2017k__spdv_2017k/_bundle_a36d6772e88b.tar took 119.2 s
("bundle copy" in timing_events.csv) for 512 MB -- 4.3 MB/s -- and hw_spdvg.csv
showed >= 86 s with ZERO bytes on every channel, CPU 0.4-4.5%, iowait pinned at
8.4%.  A stall, not a slow copy.  That verdict's own "NEXT, in order" names this
measurement first:

    "(1) re-stage the now-aged a36d6772e88b bundle on a fresh A100 with the trace
     running (~1 min GPU): >= 30 MB/s says window/freshness, ~4 MB/s with the same
     zero-traffic stall says structural"

The pilot's stall was INFERRED from a hardware sampler that reads the counters every
5 s (pipeline/vm_hwlogger.py::sample_loop, --interval default 5.0).  This probe
measures it directly, three ways on one runtime:

    PASS A  the engine's OWN read path -- staging.py::_stage_from_bundle, called with
            the same inputs staging.py::_stage_tiles_local builds -- while a sampler
            thread watches the destination tar GROW.  The engine's copy is a bare
            `shutil.copyfile`; it cannot be instrumented from inside, but its output
            file can be sized once a second, which turns the same call into a
            bytes-vs-time curve with zero engine changes.
    PASS B  a chunked read of the SAME tar over the mount, 8 MiB at a time, timing
            every single read() syscall.  A stall becomes an offset and a duration
            instead of a gap in a 5 s trace.
    PASS C  the SAME chunked reader on a control object: the smallest ortho/overlay
            >= 200 MiB under Full_Image/Pipeline Imagery -- an object this campaign
            did not write, whose mtime is printed so its age is a read fact and not
            a claim.  If C stalls the same way, the effect is the mount or the host,
            not the bundle, and neither hypothesis in the verdict survives.

READ THE ORDERING CAVEAT BEFORE READING THE NUMBERS.  In the default order A,B,C
pass B is a WARM read by construction -- pass A has already pulled those 512 MB
through the mount, and the kernel page cache over FUSE may serve the second read
from RAM.  A fast B after a slow A is evidence about CACHING, not about throughput.
The probe attempts `sync; echo 3 > /proc/sys/vm/drop_caches` between passes and
prints whether that worked, but a cold chunked read wants `--order B,A,C` on its own
fresh runtime.  Say which order produced any number you quote.

THIS INSTRUMENT NEVER WRITES TO THE LAKE.  Every byte it writes goes under one
mkdtemp directory beneath --scratch (default /content), which is refused outright if
it resolves under the Drive mount, and which is removed in a finally.  It writes no
step log, so the "bundle copy 2017k" line the ENGINE prints in pass A is never
harvested into phase4/qc/timing_events.csv -- that series stays the queue's.

HOW IT IS RUN (a fresh Colab runtime, via the front door).  From Scripts/:

    py -3.12 pipeline/vm_ops.py exec --session <s> --timeout 2400
        --file qc/instruments/probe_bundle_read.py

(one line; broken here only for width -- a real backslash continuation inside this
docstring would splice the two lines together in __doc__)

`colab exec -f` UPLOADS AND RUNS THE FILE WITH NO ARGUMENT PASS-THROUGH, and
gen_vm_bootstrap.py's D13 note says every exec is a fresh shell that inherits no
environment, so there is no way to reach the flags below through that call.  To run
any non-default option -- `--order B,A,C` for the cold chunked read especially --
write a three-line wrapper to local scratch and exec THAT instead, the same
bake-the-constants-in pattern gen_vm_bootstrap.py uses:

    import runpy, sys
    sys.argv = ["probe_bundle_read.py", "--order", "B,A,C"]
    runpy.run_path("/content/repo/Scripts/qc/instruments/probe_bundle_read.py",
                   run_name="__main__")

run_name="__main__" is what fires the guard at the bottom of this file.

The 900 s default timeout is NOT enough: the pilot's own read was 119 s and its worst
case is unbounded (the read is a bare copyfile with no throughput floor), so pass A
alone can legitimately outlast it.  Ask for 2400 s.

THE BRANCH MATTERS.  gen_vm_bootstrap.py's --branch defaults to work/20260824-sectors,
which predates the tile bundle entirely.  Launch naming a PUSHED branch whose
staging.py actually has _stage_from_bundle, or this probe dies at import with
INPUTS FAILED after paying for the runtime.  Check before launching:
`git log origin/<branch> -1 -- Scripts/pipeline/phase4seg/staging.py`.

THE HARDWARE TRACE IS ALREADY RUNNING.  gen_vm_bootstrap.py starts vm_hwlogger.py
itself (the HWLOGGER_STARTED line), sampling every 5 s onto phase4/logs/
hw_{session}.csv, so a bare exec on a bootstrapped VM is traced with no extra step.
This probe deliberately does NOT write the hw step marker -- inventing a step name
would put a fabricated row in hw_step_attribution.csv -- so its samples land under
`(between)`, and the join back to a pass is by the UTC stamps printed around each.

PHASE4SEG_TILE_BUNDLE: set to "1" here BEFORE phase4seg.staging is imported, because
staging binds `_BUNDLE_ENABLED` at import time.  Strictly it is belt-and-braces --
the flag is read only by `_bundle_enabled()`, which only `_stage_tiles_local`
consults, and this probe calls `_stage_from_bundle` directly -- but a probe whose
result depends on how the runtime happened to be launched is not a measurement.

TARGETS COMMITTED CODE.  Written against `git show HEAD:Scripts/pipeline/phase4seg/
staging.py` (staging._stage_from_bundle / _stage_tiles_local / _bundle_names) and
core.py's `pd.read_csv(index_path)` -> `_stage_tiles_local(idx_df, label)` call, which
passes the WHOLE frame, unfiltered.  A VM clones the repo, so it runs whatever is on
the branch it cloned; if the working tree's uncommitted `scratchcache.reserve()` call
inside `_stage_from_bundle` has landed by then it runs too -- it is advisory (it
never refuses) and does not change what is being measured.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from phase4seg import config
from phase4seg.names import clean_argv, tile_dir_name

# The stopwatch marker is written as an escape so this FILE stays pure ASCII while
# its OUTPUT carries U+23F1 -- the exact character common.py::tock prints and
# qc/instruments/harvest_timing_events.py::_EVENT matches.  The file is shipped to
# the VM through the colab CLI; an ASCII source cannot be mangled in transit.
CLK = "\u23f1"

# The subject.  label/tag name the arm the pilot ran; EXPECT_ID is the tile-set id
# experiments/bundle_validation_2017k.yaml records under K1 (and the name of the tar
# actually sitting in that directory).  It is PRINTED as MATCH/DIFFER, never gated on.
LABEL = "2017k"
TAG = "spdv_2017k"
EXPECT_ID = "a36d6772e88b"

# rclone's VFS reads a file in doubling range requests -- default --vfs-read-chunk-size
# 128M with no limit -- so cumulative request boundaries fall at 128, 384, 896, 1920
# MiB.  0.41 GB (where the pilot's traffic stopped) is 391 MiB, one buffer past 384.
# A slow chunk starting near a boundary is a NEW range request hanging, which is a
# specific mechanism rather than "the mount was slow".  ANNOTATION ONLY: these are
# rclone's documented defaults, not this mount's measured settings, which is why the
# probe also prints the live rclone command line for anyone checking.
_VFS_BOUNDARIES_MIB = (128, 384, 896, 1920)


def say(msg=""):
    """Every line flushed.  vm_ops.exec_file only shows output when the exec RETURNS;
    if the timeout kills the probe mid-stall, anything still in the buffer is lost --
    and the stall is the measurement."""
    print(msg, flush=True)


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def mib(n):
    return n / (1 << 20)


def size_or_none(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return None


def run_out(cmd, timeout=30):
    """Best-effort stdout of a shell probe.  Never raises; returns '' on any failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:                                   # noqa: BLE001
        return f"(unavailable: {type(e).__name__}: {e})"


# ---------------------------------------------------------------------------
#  Context: what host, what mount, what cache
# ---------------------------------------------------------------------------
def print_context():
    say("=== CONTEXT " + "=" * 55)
    say(f"  utc                {utc()}")
    say(f"  COLAB_SESSION      {os.environ.get('COLAB_SESSION', '(unset)')}"
        "   <- hw_{session}.csv joins on this")
    say(f"  hostname           {os.uname().nodename if hasattr(os, 'uname') else '?'}")
    say(f"  python             {sys.version.split()[0]}   cwd {os.getcwd()}")
    say(f"  PHASE4SEG_TILE_BUNDLE={os.environ.get('PHASE4SEG_TILE_BUNDLE', '(unset)')}")
    # WHICH CODE ACTUALLY RAN.  The docstring's claim to target committed code is an
    # assertion; these three lines are the evidence, and they join to `git log`.
    # A branch without _stage_from_bundle makes PASS A die at import, and this is
    # where that shows up as a fact rather than a traceback to interpret.
    from phase4seg import __version__ as _v
    say(f"  phase4seg          {_v}")
    for what, cmd in (("repo branch", ["git", "-C", "/content/repo", "rev-parse",
                                       "--abbrev-ref", "HEAD"]),
                      ("repo commit", ["git", "-C", "/content/repo", "rev-parse",
                                       "--short", "HEAD"]),
                      ("staging.py  ", ["git", "-C", "/content/repo", "log", "-1",
                                        "--format=%h %ad %s", "--date=short", "--",
                                        "Scripts/pipeline/phase4seg/staging.py"])):
        line = (run_out(cmd).strip().splitlines() or ["(none)"])[0]
        say(f"  {what}        {line[:120]}")
    for src, cmd in (("mounts", ["grep", "-m3", "drive", "/proc/mounts"]),
                     ("rclone", ["pgrep", "-af", "rclone"]),
                     ("df /content", ["df", "-h", "/content"]),
                     ("free", ["free", "-m"]),
                     ("nproc", ["nproc"])):
        out = run_out(cmd).strip().splitlines()
        say(f"  {src}:")
        for ln in out[:4]:
            say(f"    {ln[:150]}")
        if not out:
            say("    (no output)")
    say("")


def drop_caches(enabled):
    """Best-effort page-cache drop between passes.  Colab runs as root, but the
    container may still present /proc/sys/vm/drop_caches read-only -- the result is
    PRINTED either way, because a pass B that could not be cooled is a different
    measurement from one that could."""
    if not enabled:
        return "skipped (--no-drop-caches)"
    try:
        subprocess.run(["sync"], timeout=120)
        with open("/proc/sys/vm/drop_caches", "w") as fh:
            fh.write("3\n")
        return "ok (sync + drop_caches=3)"
    except Exception as e:                                   # noqa: BLE001
        return f"FAILED ({type(e).__name__}: {e}) -- later passes may read from RAM"


# ---------------------------------------------------------------------------
#  Inputs, built the way staging._stage_tiles_local builds them
# ---------------------------------------------------------------------------
def build_inputs(label, tag):
    """(tile_dir, index_path, idx_df, src_root, cols, kinds, sidecar, tar_path).

    Mirrors core.py -> staging.py exactly:
      core.py            index_path = tile_dir_for(label) / f"tile_index_{label}.csv"
                         idx_df     = pd.read_csv(index_path)      # WHOLE frame
      _stage_tiles_local kinds      = {img_path: images, mask_path: masks,
                                       height_path: heights}
                         cols       = [c for c in kinds if c in idx_df.columns]
                         src_root   = Path(idx_df.iloc[0].img_path).parents[2]

    tile_dir_for() is NOT called, so config.RUN_TAG is never mutated: the rule it
    applies lives in names.tile_dir_name (stdlib-only, the shared home), and joining
    that name to config.TILE_DIR reproduces it without touching engine state that a
    later import might read.  Both paths are printed so the two can be compared.
    """
    import pandas as pd

    tile_dir = config.TILE_DIR / tile_dir_name(label, tag)
    index_path = tile_dir / f"tile_index_{label}.csv"
    say(f"  tile dir           {tile_dir.as_posix()}")
    t0 = time.perf_counter()
    idx_df = pd.read_csv(index_path)
    say(f"  index read         {len(idx_df)} rows in {time.perf_counter() - t0:.2f}s"
        f"  ({index_path.name})")

    kinds = {"img_path": "images", "mask_path": "masks", "height_path": "heights"}
    cols = [c for c in kinds if c in idx_df.columns]
    first = str(idx_df.iloc[0]["img_path"]) if len(idx_df) else ""
    say(f"  cols               {cols}")
    say(f"  first img_path     {first}")
    if not first.startswith("/content/drive"):
        say("  NOTE: img_path is not under /content/drive -- the live engine would "
            "SKIP staging entirely here (_stage_tiles_local's first guard).")
    src_root = Path(first).parents[2]
    say(f"  src_root (derived) {src_root.as_posix()}"
        f"   {'== tile_dir' if src_root == tile_dir else '!= tile_dir (using derived)'}")

    # The tile-set id from the meta BESIDE THE INDEX -- staging's step 1-2, same call.
    from phase4seg.tiling import tileset_id_from_meta
    from phase4seg.staging import _bundle_names
    t0 = time.perf_counter()
    tsid = tileset_id_from_meta(src_root / f"tile_index_{label}.meta.json")
    say(f"  tileset id         {tsid}  ({time.perf_counter() - t0:.2f}s to derive)"
        f"   {'MATCH' if tsid == EXPECT_ID else 'DIFFER from ' + EXPECT_ID}"
        "  <- experiments/bundle_validation_2017k.yaml K1")
    if not tsid:
        raise RuntimeError("no tile-set id -- the bundle is unreachable by name; "
                           "staging would refuse at step 1")
    tar_name, json_name, _done = _bundle_names(tsid)
    tar_path = src_root / tar_name

    t0 = time.perf_counter()
    sidecar = json.loads((src_root / json_name).read_text())
    say(f"  sidecar            {json_name}  {len(sidecar.get('files', []))} members, "
        f"read in {time.perf_counter() - t0:.2f}s")
    say(f"  sidecar records    tar_size={sidecar.get('tar_size')} "
        f"({mib(sidecar.get('tar_size') or 0):.1f} MiB)  n_files="
        f"{sidecar.get('n_files')}  created_utc={sidecar.get('created_utc')}")
    say(f"  sidecar tar_sha256 {str(sidecar.get('tar_sha256'))[:16]}...")

    st = os.stat(tar_path)
    say(f"  tar on the mount   {tar_path.name}  {st.st_size} bytes "
        f"({mib(st.st_size):.1f} MiB)  mtime "
        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(st.st_mtime))}")
    if st.st_size != sidecar.get("tar_size"):
        say("  NOTE: on-mount size != sidecar tar_size -- staging would refuse at "
            "step 9 AFTER paying for the whole read.")
    return tile_dir, index_path, idx_df, src_root, cols, kinds, sidecar, tar_path


# ---------------------------------------------------------------------------
#  PASS A -- the engine's own read path, with a growth sampler on its output file
# ---------------------------------------------------------------------------
def pass_a(src_root, dst_root, idx_df, cols, kinds, label, tar_dir, sidecar,
           budget_s, sample_s):
    say("=== PASS A -- engine path (staging._stage_from_bundle) " + "=" * 14)
    say(f"  start utc          {utc()}")
    say(f"  dst_root           {dst_root}   (fresh mkdtemp: no .done marker can "
        "short-circuit step 7)")
    say(f"  tar_dir            {tar_dir}")

    from phase4seg import staging

    # WHERE THE BYTES LAND.  staging step 8 builds this name itself:
    #     local_tar = tar_dir / f"{dst_root.name}__{want}.tar"
    # Reproduced here ONLY to point a sampler at it.  If staging ever changes that
    # name the sampler simply sees nothing and says so; it cannot corrupt pass A.
    want = sidecar.get("tileset_id")
    local_tar = Path(tar_dir) / f"{Path(dst_root).name}__{want}.tar"
    full = int(sidecar.get("tar_size") or 0)

    result = {}

    def _run():
        try:
            rep = {}
            result["ret"] = staging._stage_from_bundle(
                src_root, dst_root, idx_df, cols, kinds, label,
                tar_dir=tar_dir, report=rep)
            result["report"] = rep
        except BaseException as e:                           # noqa: BLE001
            result["exc"] = f"{type(e).__name__}: {e}"
            result["tb"] = traceback.format_exc()

    th = threading.Thread(target=_run, name="engine-stage", daemon=True)
    t0 = time.perf_counter()
    th.start()

    # --- the sampler -------------------------------------------------------
    # One getsize() per tick on a LOCAL file: cheap, and it never touches the mount,
    # so the instrument cannot slow the thing it measures.  A row is printed when
    # bytes moved, and every 10 s when they did not -- which is what a stall looks
    # like from outside a copyfile that reports nothing.
    #
    # THE ZERO-GROWTH CLOCK STARTS AT t=0, NOT AT THE FIRST BYTE.  An earlier shape
    # of this loop only began counting once bytes appeared, so a copy that opened the
    # source and then hung before delivering anything -- a first-byte stall, exactly
    # the shape a hanging range request has -- would have been reported as
    # "longest zero-growth run 0.0s".  Starting the clock at zero makes the two
    # stall shapes report the same way.
    prev, last_print, first_byte, longest_zero, zero_start = None, 0.0, None, 0.0, 0.0
    peak, copy_done_at, samples = 0, None, 0
    while th.is_alive() and (time.perf_counter() - t0) < budget_s:
        time.sleep(sample_s)
        el = time.perf_counter() - t0
        cur = size_or_none(local_tar)
        samples += 1
        if cur is None or cur == 0:
            # Before the copy creates/fills the file, or after step 13 unlinks it.
            if prev is not None:
                if copy_done_at is None:
                    copy_done_at = el
                say(f"    t=+{el:6.1f}s  tar gone (extract finished / refused)")
                prev = None
            elif first_byte is None and el - last_print >= 10.0:
                say(f"    t=+{el:6.1f}s  no bytes yet  STALL {el - zero_start:.1f}s "
                    "and counting (first-byte stall)")
                last_print = el
            continue
        peak = max(peak, cur)
        if first_byte is None:
            first_byte = el
            longest_zero = max(longest_zero, el - zero_start)
            zero_start = None
            say(f"    t=+{el:6.1f}s  FIRST BYTES  size={cur} ({mib(cur):.1f} MiB)")
            prev, last_print = cur, el
            continue
        delta = cur - (prev or 0)
        if delta > 0:
            if zero_start is not None:
                longest_zero = max(longest_zero, el - zero_start)
                zero_start = None
            say(f"    t=+{el:6.1f}s  size={cur} ({mib(cur):7.1f} MiB)  "
                f"+{mib(delta):.1f} MiB  {mib(delta) / max(el - last_print, 1e-9):6.1f} MB/s")
            prev, last_print = cur, el
        else:
            if zero_start is None:
                zero_start = last_print
            if full and cur >= full:
                if copy_done_at is None:
                    copy_done_at = el
                    say(f"    t=+{el:6.1f}s  COPY COMPLETE at full size {cur} -- "
                        "everything after this is sha256 + extract, not transfer")
            elif el - last_print >= 10.0:
                say(f"    t=+{el:6.1f}s  size={cur} ({mib(cur):7.1f} MiB)  delta=0  "
                    f"STALL {el - zero_start:.1f}s and counting")
                last_print = el
    if zero_start is not None and copy_done_at is None:
        longest_zero = max(longest_zero, (time.perf_counter() - t0) - zero_start)

    th.join(timeout=max(0.0, budget_s - (time.perf_counter() - t0)))
    dt = time.perf_counter() - t0
    contaminated = th.is_alive()
    if contaminated:
        say(f"  !! engine call STILL RUNNING at the {budget_s:.0f}s budget "
            f"({utc()}).  Abandoning the wait; it keeps pulling on the mount, so "
            "PASSES B AND C FROM HERE ARE CONTAMINATED.")

    say(f"  {CLK} probe bundle engine: {dt:.1f}s")
    if "exc" in result:
        say(f"  engine RAISED: {result['exc']}")
        for ln in (result.get("tb") or "").strip().splitlines()[-6:]:
            say("    " + ln)
    elif contaminated:
        say("  engine return: UNKNOWN (call did not finish inside the budget)")
    elif result.get("ret") is None:
        say("  engine return: None -> REFUSED.  The refusal reason is the "
            "'(tile bundle not used: ...)' line staging printed above.")
    else:
        say(f"  engine return: staged, {len(result['ret'])} column(s) rewritten; "
            f"report={result.get('report')}  (copied=False means the step-7 local "
            "reuse hit, which cannot happen on a fresh mkdtemp)")
    say(f"  sampler: {samples} samples at {sample_s}s, first bytes at "
        f"{('+%.1fs' % first_byte) if first_byte is not None else 'NEVER'}, "
        f"peak {peak} bytes ({mib(peak):.1f} MiB), longest zero-growth run "
        f"{longest_zero:.1f}s, copy complete at "
        f"{('+%.1fs' % copy_done_at) if copy_done_at is not None else 'n/a'}")
    say(f"  end utc            {utc()}")
    say("")
    # "refused" means the engine RETURNED None -- its own decision.  A call that
    # never finished has no return at all, and calling that a refusal would put a
    # verdict on the timing sheet the engine never gave.
    return {"seconds": dt, "contaminated": contaminated,
            "refused": ("ret" in result) and result["ret"] is None,
            "longest_zero": longest_zero, "first_byte": first_byte}


# ---------------------------------------------------------------------------
#  Chunked reader -- PASS B and PASS C share it
# ---------------------------------------------------------------------------
def chunked_read(path, buf_bytes, slow_s, max_bytes=None, do_sha256=False):
    """Read `path` one raw read() at a time, timing every call.

    buffering=0 so each read() is ONE syscall of at most buf_bytes -- a buffered
    stream would coalesce the very latency this is trying to see, and a short read
    is itself a datum (it is what a range request boundary looks like from here).
    sha256, when asked for, is folded in during the same pass and timed SEPARATELY,
    so the throughput number stays a read number and the hash costs no second
    512 MB pull through the mount.
    """
    import hashlib

    h = hashlib.sha256() if do_sha256 else None
    total, n_chunks, n_short, hash_s = 0, 0, 0, 0.0
    slow = []                       # (index, offset, seconds, nbytes)
    t_open0 = time.perf_counter()
    fh = open(path, "rb", buffering=0)
    open_s = time.perf_counter() - t_open0
    say(f"    open() {open_s:.2f}s")
    t0 = time.perf_counter()
    try:
        while True:
            if max_bytes is not None and total >= max_bytes:
                break
            want = buf_bytes
            if max_bytes is not None:
                want = min(want, max_bytes - total)
            off = total
            c0 = time.perf_counter()
            b = fh.read(want)
            el = time.perf_counter() - c0
            if not b:
                break
            if h is not None:
                hs0 = time.perf_counter()
                h.update(b)
                hash_s += time.perf_counter() - hs0
            n_chunks += 1
            if len(b) < want:
                n_short += 1
            total += len(b)
            is_slow = el > slow_s
            if is_slow:
                # THE OFFSET IS THE POINT, not just the duration. rclone's VFS reads
                # a file in doubling range requests, so a chunk that hangs just past
                # a cumulative boundary is a NEW range request stalling -- a
                # mechanism -- while one hanging mid-request is the transfer itself.
                slow.append((n_chunks, off, el, len(b)))
            if is_slow or n_chunks == 1:
                near = [m for m in _VFS_BOUNDARIES_MIB
                        if 0 <= mib(off) - m < mib(buf_bytes) * 2]
                if n_chunks == 1:
                    note = "  FIRST CHUNK (first-byte cost)"
                elif near:
                    note = (f"  follows the {near[0]} MiB rclone VFS range boundary "
                            "(rclone's default chunking; annotation, not a verdict)")
                else:
                    note = ""
                say(f"    chunk={n_chunks:5d} offset={off} ({mib(off):8.1f} MiB) "
                    f"got={len(b)} took={el:6.2f}s{note}")
    finally:
        fh.close()
    read_s = time.perf_counter() - t0 - hash_s
    return {"total": total, "n_chunks": n_chunks, "n_short": n_short,
            "open_s": open_s, "read_s": read_s, "hash_s": hash_s,
            "slow": slow, "sha256": h.hexdigest() if h is not None else None}


def pass_b(tar_path, sidecar, buf_bytes, slow_s):
    say("=== PASS B -- chunked read of the same tar over the mount " + "=" * 10)
    say(f"  start utc          {utc()}")
    say(f"  file               {tar_path.as_posix()}")
    say(f"  buffer             {buf_bytes} bytes ({mib(buf_bytes):.0f} MiB), "
        f"slow threshold {slow_s}s")
    r = chunked_read(tar_path, buf_bytes, slow_s, do_sha256=True)
    mbs = (r["total"] / 1e6) / max(r["read_s"], 1e-9)
    longest = max([s[2] for s in r["slow"]], default=0.0)
    say(f"  {CLK} probe bundle chunked: {r['read_s']:.1f}s, {mbs:.1f} MB/s, "
        f"stalls>{slow_s:.0f}s={len(r['slow'])}, longest={longest:.1f}s")
    say(f"  {CLK} probe bundle sha256: {r['hash_s']:.1f}s")
    say(f"  bytes {r['total']}  chunks {r['n_chunks']}  short reads {r['n_short']}  "
        f"open {r['open_s']:.2f}s  (sha256 folded into the same pass, CPU time "
        "excluded from the throughput above)")
    want = sidecar.get("tar_sha256")
    say(f"  sha256 {r['sha256'][:16]}...  vs sidecar {str(want)[:16]}...  "
        f"{'MATCH' if r['sha256'] == want else 'DIFFER'}")
    if r["slow"]:
        say(f"  slow chunks (>{slow_s}s), offset in MiB:")
        for i, off, el, nb in r["slow"][:20]:
            say(f"    #{i} at {mib(off):.1f} MiB  {el:.2f}s  ({nb} bytes)")
    say(f"  end utc            {utc()}")
    say("")
    return {"seconds": r["read_s"], "mbs": mbs, "stalls": len(r["slow"]),
            "longest": longest}


def pick_control(min_bytes, explicit=None):
    """The control object, chosen by a rule and not by taste.

    Rule: under Full_Image/Pipeline Imagery, regular .tif/.tiff files at least
    min_bytes, ordered by (size, name), take the FIRST -- i.e. the smallest object
    that still clears the bar, so the control is close to the tar's size class
    without spending minutes reading a 30 GB ortho.  The top candidates are printed
    so the choice is auditable, and every candidate's mtime is printed because the
    hypothesis under test is object FRESHNESS: the bundle was written the day it was
    read; these files were not.
    """
    root = config.IMAGERY_DIR
    say(f"  listing            {root.as_posix()}")
    t0 = time.perf_counter()
    cands = []
    with os.scandir(root) as it:
        for e in it:
            try:
                if not e.is_file(follow_symlinks=False):
                    continue
                if not e.name.lower().endswith((".tif", ".tiff")):
                    continue
                sz = e.stat().st_size
            except OSError:
                continue
            if sz >= min_bytes:
                cands.append((sz, e.name, e.stat().st_mtime))
    say(f"  listed             {len(cands)} .tif >= {mib(min_bytes):.0f} MiB in "
        f"{time.perf_counter() - t0:.2f}s")
    cands.sort(key=lambda t: (t[0], t[1]))
    for sz, name, mt in cands[:5]:
        say(f"    candidate  {name}  {sz} bytes ({mib(sz):.1f} MiB)  mtime "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(mt))}")
    if explicit:
        for sz, name, mt in cands:
            if name == explicit:
                return root / name, sz, mt
        say(f"  --control {explicit!r} is not among the candidates; falling back to "
            "the rule")
    if not cands:
        raise RuntimeError(f"no .tif >= {min_bytes} bytes under {root}")
    sz, name, mt = cands[0]
    return root / name, sz, mt


def pass_c(buf_bytes, slow_s, min_bytes, max_bytes, explicit, tar_size=0):
    say("=== PASS C -- control: an aged object of the same size class " + "=" * 8)
    say(f"  start utc          {utc()}")
    path, sz, mt = pick_control(min_bytes, explicit)
    say(f"  CHOSEN             {path.name}  {sz} bytes ({mib(sz):.1f} MiB)  mtime "
        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(mt))}"
        "   (rule: smallest .tif clearing the floor, ties by name)")
    read_cap = min(sz, max_bytes) if max_bytes else sz
    if tar_size and read_cap < tar_size:
        # THE CONTROL IS SMALLER THAN THE SUBJECT, and that bounds what it can prove.
        # The pilot's traffic stopped near 391 MiB; a control read that never gets
        # that far cannot say whether the mount stalls past there.  --control names
        # a bigger file (and --control-max-mib raises the cap) when that matters.
        say(f"  SCOPE              control reads {mib(read_cap):.1f} MiB vs the tar's "
            f"{mib(tar_size):.1f} MiB -- a clean control here says nothing about "
            "offsets beyond that point.  Use --control <bigger file> to extend it.")
    r = chunked_read(path, buf_bytes, slow_s, max_bytes=max_bytes)
    mbs = (r["total"] / 1e6) / max(r["read_s"], 1e-9)
    longest = max([s[2] for s in r["slow"]], default=0.0)
    say(f"  {CLK} probe control chunked: {r['read_s']:.1f}s, {mbs:.1f} MB/s, "
        f"stalls>{slow_s:.0f}s={len(r['slow'])}, longest={longest:.1f}s")
    say(f"  bytes {r['total']}  chunks {r['n_chunks']}  short reads {r['n_short']}  "
        f"open {r['open_s']:.2f}s  file {path.name}")
    if r["slow"]:
        say(f"  slow chunks (>{slow_s}s), offset in MiB:")
        for i, off, el, nb in r["slow"][:20]:
            say(f"    #{i} at {mib(off):.1f} MiB  {el:.2f}s  ({nb} bytes)")
    say(f"  end utc            {utc()}")
    say("")
    return {"seconds": r["read_s"], "mbs": mbs, "stalls": len(r["slow"]),
            "longest": longest, "file": path.name}


# ---------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(
        description="re-read the aged 2017k tile bundle three ways and time it")
    ap.add_argument("--label", default=LABEL)
    ap.add_argument("--tag", default=TAG)
    ap.add_argument("--order", default="A,B,C",
                    help="pass order.  Default A,B,C runs the engine path first, "
                         "which makes B a WARM read; use B,A,C on a second fresh "
                         "runtime for a cold chunked number")
    ap.add_argument("--buf-mib", type=float, default=8.0,
                    help="chunk size for passes B and C (default 8 MiB)")
    ap.add_argument("--slow-s", type=float, default=2.0,
                    help="print any chunk slower than this (default 2 s)")
    ap.add_argument("--budget-s", type=float, default=1200.0,
                    help="hard cap on PASS A.  The engine read is a bare copyfile "
                         "with no throughput floor, so its worst case is unbounded; "
                         "past this the probe stops waiting and marks B and C "
                         "contaminated")
    ap.add_argument("--sample-s", type=float, default=1.0,
                    help="PASS A tar-growth sampling interval (default 1 s)")
    ap.add_argument("--control-min-mib", type=float, default=200.0,
                    help="size floor for the control object (default 200 MiB); the "
                         "smallest .tif clearing it wins")
    ap.add_argument("--control-max-mib", type=float, default=600.0,
                    help="stop the control read here so a big ortho cannot run away")
    ap.add_argument("--control", default=None,
                    help="control file NAME to force (must clear the size floor)")
    ap.add_argument("--scratch", default="/content",
                    help="parent of the mkdtemp working dir.  REFUSED if it "
                         "resolves under the Drive mount")
    ap.add_argument("--no-drop-caches", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and touch nothing -- safe on Windows")
    return ap


def plan_lines(a):
    tile_dir = config.TILE_DIR / tile_dir_name(a.label, a.tag)
    return [
        "=== DRY RUN -- plan only, nothing read, nothing written " + "=" * 12,
        f"  label / tag        {a.label} / {a.tag}",
        f"  tile dir           {tile_dir.as_posix()}",
        f"  index              {(tile_dir / ('tile_index_' + a.label + '.csv')).as_posix()}",
        f"  meta               {(tile_dir / ('tile_index_' + a.label + '.meta.json')).as_posix()}",
        f"  expected tar       _bundle_{EXPECT_ID}.tar  (+ .json sidecar)",
        f"  control search     {config.IMAGERY_DIR.as_posix()}  .tif >= "
        f"{a.control_min_mib:.0f} MiB, smallest wins, read capped at "
        f"{a.control_max_mib:.0f} MiB",
        f"  pass order         {a.order}   "
        f"({'B is WARM after A' if a.order.strip().upper().startswith('A') else 'B first: cold'})",
        f"  chunk / slow       {a.buf_mib:.0f} MiB / >{a.slow_s:.0f}s",
        f"  PASS A budget      {a.budget_s:.0f}s, sampled every {a.sample_s:.0f}s",
        f"  scratch parent     {a.scratch}  (mkdtemp under it; removed in finally)",
        "  writes to the lake NONE.  No step log is written, so the engine's own",
        "                     'bundle copy' line is not harvested into",
        "                     phase4/qc/timing_events.csv.",
        "  engine entry       staging._stage_from_bundle(src_root, dst_root, idx_df,",
        "                     cols, kinds, label, tar_dir=..., report=...)",
        "  config mutated     NONE (names.tile_dir_name is used instead of",
        "                     common.tile_dir_for, so config.RUN_TAG is untouched)",
        "  env set            PHASE4SEG_TILE_BUNDLE=1, before phase4seg.staging is",
        "                     imported (staging binds the flag at import time)",
    ]


def main(argv=None):
    # LINE-BUFFER THE WHOLE PROCESS, not just say().  The two lines a referee most
    # needs from pass A are printed by the ENGINE, not by this file -- the refusal
    # reason, and staging's own "bundle copy {label}: Ns" from common.tock -- and
    # stdout to a pipe is block-buffered, so under `colab exec` they would sit in a
    # 4 KB buffer until something else flushed. If the exec timeout kills the process
    # during the post-copy hash with no sampler row pending, they are lost with it.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:                                        # noqa: BLE001
        pass
    a = build_parser().parse_args(clean_argv(argv))
    if a.dry_run:
        for ln in plan_lines(a):
            say(ln)
        return 0

    # The flag is bound at IMPORT in staging.py, so it must be set before any
    # phase4seg.staging import anywhere in this process.
    os.environ["PHASE4SEG_TILE_BUNDLE"] = "1"

    say("### probe_bundle_read.py -- tile-bundle read, measured three ways")
    say("### experiments/bundle_validation_2017k.yaml R1 FAIL follow-up, item (1)")
    say("")
    print_context()

    # Never write to the lake: the working dir must not resolve under the mount.
    scratch = Path(a.scratch).resolve()
    if str(scratch).startswith(str(Path(str(config.BASE)))):
        say(f"REFUSED: --scratch {scratch} resolves under the data lake "
            f"({config.BASE}).  This instrument never writes there.")
        return 1
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="probe_bundle_", dir=str(scratch)))
    dst_root = tmp / "tiles" / tile_dir_name(a.label, a.tag)
    tar_dir = tmp / "bundles"
    tar_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    ok = 0
    try:
        say("=== INPUTS " + "=" * 56)
        try:
            (_tile_dir, _index_path, idx_df, src_root, cols, kinds, sidecar,
             tar_path) = build_inputs(a.label, a.tag)
        except Exception as e:                               # noqa: BLE001
            say(f"  INPUTS FAILED: {type(e).__name__}: {e}")
            for ln in traceback.format_exc().strip().splitlines()[-8:]:
                say("    " + ln)
            say("  Nothing downstream can run without them.")
            return 1
        say("")

        buf = int(a.buf_mib * (1 << 20))
        cmax = int(a.control_max_mib * (1 << 20))
        cmin = int(a.control_min_mib * (1 << 20))
        contaminated = False

        for step in [s.strip().upper() for s in a.order.split(",") if s.strip()]:
            say(f"  cache drop before pass {step}: {drop_caches(not a.no_drop_caches)}")
            try:
                if step == "A":
                    results["A"] = pass_a(src_root, dst_root, idx_df, cols, kinds,
                                          a.label, tar_dir, sidecar, a.budget_s,
                                          a.sample_s)
                    contaminated = contaminated or results["A"]["contaminated"]
                    ok += 1
                elif step == "B":
                    if contaminated:
                        say("  (PASS B runs with a live engine copy still pulling on "
                            "the mount -- treat its number as an upper bound only)")
                    results["B"] = pass_b(tar_path, sidecar, buf, a.slow_s)
                    ok += 1
                elif step == "C":
                    results["C"] = pass_c(buf, a.slow_s, cmin, cmax, a.control,
                                          tar_size=int(sidecar.get("tar_size") or 0))
                    ok += 1
                else:
                    say(f"  (unknown pass {step!r} in --order, skipped)")
            except Exception as e:                           # noqa: BLE001
                # One pass failing must never hide the other two.
                say(f"  PASS {step} FAILED: {type(e).__name__}: {e}")
                for ln in traceback.format_exc().strip().splitlines()[-8:]:
                    say("    " + ln)
                say(f"  end utc            {utc()}")
                say("")
    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            say(f"  cleanup: removed {tmp} (exists={tmp.exists()})")
        except Exception as e:                               # noqa: BLE001
            say(f"  cleanup FAILED: {type(e).__name__}: {e} -- {tmp} left behind "
                "(ephemeral VM disk, dies with the runtime)")

    say("")
    say("=== SUMMARY " + "=" * 55)
    say(f"  order              {a.order}")
    for k in ("A", "B", "C"):
        r = results.get(k)
        if not r:
            say(f"  PASS {k}             (not run or failed -- see above)")
            continue
        if k == "A":
            say(f"  PASS A engine      {r['seconds']:.1f}s"
                f"  first-byte {('+%.1fs' % r['first_byte']) if r['first_byte'] is not None else 'never'}"
                f"  longest zero-growth {r['longest_zero']:.1f}s"
                f"{'  REFUSED' if r['refused'] else ''}"
                f"{'  CONTAMINATED (budget hit)' if r['contaminated'] else ''}")
        else:
            say(f"  PASS {k} chunked     {r['seconds']:.1f}s  {r['mbs']:.1f} MB/s  "
                f"stalls={r['stalls']}  longest={r['longest']:.1f}s"
                + (f"  [{r.get('file')}]" if k == "C" else ""))
    say("  READING RULE (from the experiment's own next-step): >= 30 MB/s on the "
        "bundle says the pilot hit a Drive window / object-freshness effect; ~4 MB/s "
        "with the same zero-traffic stall says structural.  A control that stalls "
        "the same way says neither -- it is the mount or the host.")
    if a.order.strip().upper().startswith("A") and "B" in results:
        say("  CAVEAT: this order read the tar in PASS A first, so PASS B is a WARM "
            "read unless the cache drop above reported ok.  For a cold chunked "
            "number, run --order B,A,C on a second fresh runtime.")
    say(f"  end utc            {utc()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
