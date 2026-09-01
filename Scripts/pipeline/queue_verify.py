"""queue_verify.py — the queue's artifact-verification layer, split from
phase4_train_queue.py (2026-09-01; the core.py facade precedent at orchestration
level).

EVERY former module-global — path roots, verify-state sets, and the two helper
functions — resolves through the QUEUE MODULE at call time (`q = _q()` first line
of each function). That is not style: test_queue_verify patches q.BASE / q.QC_DIR /
q.MASKS / q._status_write 50+ times, and a from-import here would freeze the real
lake paths behind the tests' backs (the select.py MODELS_DIR lesson, same night).
phase4_train_queue re-exports these names, so q.verify_step etc. keep working.
"""
import datetime as _dt
import re
import subprocess
import time
from pathlib import Path


def _q():
    """The queue module as runtime context — lazy to avoid the import cycle."""
    import phase4_train_queue
    return phase4_train_queue


def _md5_of(path, chunk=1 << 20):
    q = _q()
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()

def _parse_utc(s):
    """"2026-08-29T04:05:06Z" → epoch seconds, or None. Timezone-aware on purpose:
    the report stamps real UTC while step_start is a local time.time(), and
    comparing those two through a naive datetime is how an off-by-8-hours
    'freshness' check would quietly pass everything."""
    q = _q()
    try:
        return (_dt.datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ")
                .replace(tzinfo=_dt.timezone.utc).timestamp())
    except (ValueError, TypeError):
        return None

def _mb_from_verdict(detail):
    """The MB figure a recorded VERIFY verdict measured, or None.

    _check_prob_raster's detail always opens with "{mb:.0f}MB " — anchored at the
    start so a stray number later in the string (valid=…, maxprob=…) can never be
    mistaken for a size.
    """
    q = _q()
    m = re.match(r"(\d+)MB\b", str(detail or "").strip())
    return int(m.group(1)) if m else None

def _check_prob_raster(out, attempts=3, backoff_s=10):
    """Decimated sanity read of a prob raster → (state, detail).

    D7 (2026-08-29), two defects in the old version:

      * `mb == 0` was UNREACHABLE. A 0-byte raster does not survive
        rasterio.open() — it raises first, the caller's blanket except caught it,
        and an empty file was reported UNCHECKED (a PASSING state) instead of
        EMPTY (a hard failure). The size test now runs BEFORE the open, which is
        the only place it can ever fire.
      * an unopenable raster and a broken checker were the same state. They are
        not the same thing: UNREADABLE means the artifact is bad, UNCHECKED means
        this function is. Only the first should stop a job.

    The open is retried with backoff first, because transient EIO on this mount is
    documented in _copy_to_drive's own comments and UNREADABLE costs a re-run of a
    4-hour inference. Three failures in ~30 s is a broken raster, not a hiccup.
    """
    q = _q()
    if not out.exists():
        return "MISSING", f"no raster at {out.name}"
    nbytes = out.stat().st_size
    mb = nbytes / 1e6
    if nbytes == 0:
        return "EMPTY", f"{out.name} is 0 bytes"
    try:
        import rasterio
        from rasterio.enums import Resampling
    except Exception as e:                                      # noqa: BLE001
        return "UNCHECKED", f"rasterio unavailable: {type(e).__name__}: {e}"[:200]
    a = nd = None
    last = None
    for i in range(attempts):
        try:
            with rasterio.open(out) as s:
                scale = min(1.0, (q._PROB_SAMPLE_PX / float(s.width * s.height)) ** 0.5)
                h = max(1200, min(s.height, int(s.height * scale)))
                w = max(1, int(s.width * h / s.height))
                a = s.read(1, out_shape=(h, w), resampling=Resampling.nearest)
                nd = 255 if s.nodata is None else s.nodata
            break
        except Exception as e:                                  # noqa: BLE001
            last = e
            a = None
            if i < attempts - 1:
                print(f"    (raster read failed: {type(e).__name__}: {e} — retrying "
                      f"in {backoff_s * (i + 1)}s [{i + 1}/{attempts}])", flush=True)
                time.sleep(backoff_s * (i + 1))
    if a is None:
        return "UNREADABLE", (f"{mb:.0f}MB but rasterio could not open it after "
                              f"{attempts} tries: {type(last).__name__}: {last}")[:200]
    v = a != nd
    vf = float(v.mean())
    mx = float(a[v].max()) / 254.0 if v.any() else float("nan")
    state = "OK"
    if not v.any():
        state = "EMPTY"
    elif vf < 0.05:
        state = "MOSTLY_NODATA"
    elif mx < 0.50:
        state = "NO_CONFIDENCE"
    elif mx < 0.75:
        state = "WEAK_CALIBRATION"
    # p99.9 travels with the state: max is one pixel and says nothing about the shape of
    # the tail. 2022 read max 1.000 but p99.9 0.665 with only 0.014% of pixels above 0.7 —
    # a compressed upper tail the max alone would have hidden from the scoring step.
    import numpy as _np
    p999 = float(_np.percentile(a[v], 99.9)) / 254.0 if v.any() else float("nan")
    return state, (f"{mb:.0f}MB valid={vf:.1%} maxprob={mx:.3f} p99.9={p999:.3f} "
                   f"[{h}x{w} sample]")

def _drive_matches_mount(path, wait_s=600, poll_s=15):
    """Does DRIVE hold the same bytes this VM reads at `path`? → (state, note).

    THE DEFECT THIS ANSWERS. Everything else in this file reads artifacts through
    the rclone mount, and `--vfs-cache-mode writes` serves reads of a freshly
    written file out of the VM's OWN CACHE. So every check — size, zip magic,
    epoch, run_tag, run_id — can pass against a file that never reached Drive. On
    2026-08-29 the cache held epoch B24, Drive held B7, the log said B24, and
    VERIFY:train passed. The only way to see that is to ask Drive, over the API,
    through credentials that share nothing with the write: `rclone md5sum` on the
    service-account remote (the same channel as gen_vm_bootstrap.py's write canary).

    States: "ok" (Drive has these bytes), "mismatch" (it does not, after wait_s),
    "unavailable" (no rclone / no SA remote / not under the mount — nothing was
    checked, and the caller must not pretend otherwise).

    A mismatch is reported, never fatal. rclone uploads asynchronously, so shortly
    after a write the server legitimately still holds the previous file; wait_s is
    generous for exactly that reason. Waiting once per job, on a checkpoint whose
    last write was usually many minutes before training ended, costs nothing in the
    normal case and is the whole ballgame in the abnormal one.

    NOT applied to the inference raster: that is multi-GB, and hashing it back
    through FUSE is the read that hung the queue in uninterruptible disk sleep
    (2018s_fx, 2026-08-27). The checkpoint is ~150-300 MB and worth the seconds.
    """
    q = _q()
    p = str(path)
    if not p.startswith(q._DRIVE_MOUNT_PREFIX):
        return "unavailable", "drive check n/a (not under the mount)"
    rel = p[len(q._DRIVE_MOUNT_PREFIX):].strip("/")
    try:
        r = subprocess.run(["rclone", "listremotes"], capture_output=True,
                           text=True, timeout=60)
        if r.returncode != 0 or f"{q._SA_REMOTE}:" not in (r.stdout or "").split():
            return "unavailable", f"drive check n/a (no {q._SA_REMOTE}: remote)"
    except Exception as e:                                      # noqa: BLE001
        return "unavailable", f"drive check n/a ({type(e).__name__})"
    try:
        want = _md5_of(path)                     # as THIS VM sees it, cache and all
    except OSError as e:
        return "unavailable", f"drive check n/a (local md5 failed: {type(e).__name__})"
    t0 = time.time()
    got = None
    while True:
        try:
            r = subprocess.run(["rclone", "md5sum", f"{q._SA_REMOTE}:{rel}"],
                               capture_output=True, text=True, timeout=120)
            tok = (r.stdout or "").split()
            got = tok[0].lower() if r.returncode == 0 and tok and len(tok[0]) == 32 else None
        except Exception:                                       # noqa: BLE001
            got = None
        if got == want:
            return "ok", f"drive md5 ok ({int(time.time() - t0)}s)"
        if time.time() - t0 >= wait_s:
            return "mismatch", (
                f"DRIVE HOLDS DIFFERENT BYTES: mount md5 {want[:8]}, drive "
                f"{(got or 'absent')[:8]} after {int(time.time() - t0)}s — this VM is "
                f"reading a file the lake does not have")
        time.sleep(poll_s)

def _verify_ckpt_identity(ck, year, tag, mb, step_start):
    """Open the checkpoint and assert it belongs to THIS run.

    WHY (2026-08-29). The previous gate asserted size >= 50 MB and zip magic, and
    nothing else. It passed on a checkpoint that was phase B epoch 7 while the
    training log reported deploying epoch 24 — the artifacts on Drive were simply
    not what the run produced (the VM was unassigned before its upload backlog
    drained). Size and zip magic cannot see that; identity can.

    Checks, in order of how badly each would mislead:
      1. mtime NEWER than the step started — a stale file from an earlier arm is
         the failure that actually happened;
      2. run_tag matches the job's tag — catches cross-arm contamination;
      3. run_id present and non-empty — catches a file written before identity
         stamping, which cannot be attributed at all.

    Fails OPEN on an unreadable payload but says UNVERIFIED rather than OK, so the
    distinction between "checked and fine" and "could not check" survives into the
    status CSV instead of being flattened to a pass.
    """
    q = _q()
    import datetime as _d
    try:
        import torch
        d = torch.load(ck, map_location="cpu", weights_only=False)
    except Exception as e:                                        # noqa: BLE001
        return "UNVERIFIED", f"{mb:.0f}MB, zip ok; payload unreadable ({type(e).__name__})"

    age = ck.stat().st_mtime
    parts = [f"{mb:.0f}MB", f"{d.get('phase','?')}E{d.get('epoch','?')}"]
    if step_start and age < step_start - 5:
        stale = _d.datetime.fromtimestamp(age).strftime("%H:%M:%S")
        return "BAD_CKPT", (f"{mb:.0f}MB but mtime {stale} PREDATES this step — the "
                            f"file on disk is not what this run produced")
    got = (d.get("run_tag") or "")
    if tag and got and got != tag:
        return "BAD_CKPT", f"{mb:.0f}MB, run_tag={got!r} but this job is {tag!r}"
    rid = d.get("run_id") or ""
    if not rid:
        parts.append("no run_id (pre-identity build)")
    else:
        parts.append(f"run_id ok")
    # THE CHECK THAT ACTUALLY CATCHES THE 2026-08-29 FAILURE (D1, added here after
    # noticing everything above it would have PASSED that night). Every test so far
    # read the checkpoint through the rclone mount, and with --vfs-cache-mode writes
    # the mount serves this VM's own write cache. On the night in question the cache
    # held epoch B24 and DRIVE HELD B7: the mount answers with the good file, the
    # identity fields are the good file's, and the artifact that survives the VM is
    # the wrong one. Identity stamping cannot see that — only asking Drive can.
    #
    # ONLY when this VM wrote the file (step_start set). On the D7 resume-recheck
    # path the checkpoint came from a DEAD runtime, so this VM holds no dirty cache
    # entry for it — a mount read IS a Drive read and the comparison is vacuously
    # equal. It would buy nothing and cost a second full 150-300 MB read through
    # FUSE, in a function with no watchdog over it: the uninterruptible-disk-sleep
    # shape that hung the queue on 2018s_fx.
    if step_start:
        # via q, NOT a direct sibling call: the resume-recheck test patches
        # q._drive_matches_mount and the patch must intercept this call too
        state, note = q._drive_matches_mount(ck)
        parts.append(note)
        if state == "mismatch":
            return "UNVERIFIED", ", ".join(parts)
    else:
        # ...and WITHOUT the freshness test or the Drive comparison there is very
        # little left. run_tag and run_id say "this file belongs to this arm"; they
        # cannot say "this file is the epoch the log described", which is the exact
        # thing that went wrong. Returning OK here laundered the failure: a step left
        # UNVERIFIED by a crashed launch was re-checked by the next launch, passed on
        # identity fields alone, and _completed_steps then DISCARDED its reverify
        # marker (line ~388) — so the B24/B7 corpse would have become a permanent OK
        # after one relaunch. UNVERIFIED keeps the marker, so it is re-checked every
        # launch and never silently graduates.
        parts.append("drive check skipped (re-verify: another runtime wrote this)")
        return "UNVERIFIED", (", ".join(parts) +
                              " — identity fields only; freshness and Drive-side"
                              " comparison are not available on a re-verify")
    return "OK", ", ".join(parts)

def _verify_eval_rows(rep, y, tag, step_start):
    """Did THIS run's evaluate step write rows to the shared report? → (state, detail).

    D6 (2026-08-29). The old check was `(df["year"] == y).any()` against
    semantic_eval_report.csv — a cumulative file that every year, every arm and
    every campaign appends into. Any historical row for the year passed it, so a
    job could "verify" its evaluate step against a number some other model
    measured weeks earlier, and an evaluate step that exited 0 without writing
    anything was indistinguishable from one that worked.

    Rows now carry run_tag / run_id / written_utc (core.py step_evaluate), so the
    check can be the one that was always meant: rows for this year, under THIS
    job's tag, written since this step started.

      MISSING     no rows for the year at all, or none under this tag (another
                  arm's rows are not this run's evidence)
      STALE_EVAL  rows under this tag, but written BEFORE this step began — the
                  step exited 0 and left the previous run's numbers in place
      UNVERIFIED  a pre-identity report, or an untagged job: the columns needed to
                  attribute the rows are not there, so nothing is claimed
    """
    q = _q()
    if not rep.exists():
        return "MISSING", f"no {rep.name}"
    import pandas as pd
    df = pd.read_csv(rep)
    sub = df[df["year"].astype(str) == str(y)]
    if not len(sub):
        return "MISSING", f"no rows for year {y} in {rep.name}"
    if "run_tag" not in df.columns:
        return "UNVERIFIED", (f"{len(sub)} rows for year {y}, but {rep.name} predates "
                              f"run-identity stamping — cannot tell whose they are")
    if not tag:
        return "UNVERIFIED", (f"{len(sub)} rows for year {y}; job has no run tag, so "
                              f"they cannot be attributed to this run")
    mine = sub[sub["run_tag"].astype(str) == str(tag)]
    if not len(mine):
        others = sorted({str(t) for t in sub["run_tag"].astype(str)})[:4]
        return "MISSING", (f"{len(sub)} rows for year {y} but NONE under tag {tag!r} "
                           f"(found {others}) — these are not this run's numbers")
    written = [_parse_utc(w) for w in mine.get("written_utc", [])]
    newest = max([w for w in written if w is not None], default=None)
    if newest is None:
        return "UNVERIFIED", (f"{len(mine)} rows for {y}/{tag} but no readable "
                              f"written_utc — freshness unknown")
    when = _dt.datetime.fromtimestamp(newest).strftime("%H:%M:%S")
    if step_start and newest < step_start - 5:
        return "STALE_EVAL", (f"{len(mine)} rows for {y}/{tag} but the newest was "
                              f"written {when}, BEFORE this step started — the step "
                              f"exited 0 without writing its metrics")
    return "OK", f"{len(mine)} rows for {y}/{tag}, written {when}"

def verify_step(job, step, rows, step_start=None, reverify=False):
    """P4.3: per-step artifact check, recorded as a VERIFY:{step} row.

    The old job-end-only VERIFY let a broken artifact license every later step
    (the 2024 stub trained+evaluated fine and then died at inference; 2017's
    bad raster was only caught by a human a day later). Never raises; returns
    False on a hard failure so the caller aborts the job.

    `reverify=True` marks a check re-run on a step this launch SKIPPED, because
    the last launch's verdict was "could not check" (D7). `step_start` is None
    there — there is no step to be newer than — so the freshness tests stand down
    and say so, rather than comparing against a timestamp that does not exist.
    """
    q = _q()
    y, tag = job["year"], job["tag"]
    state, detail = "OK", ""
    try:
        if step == "labels":
            if "--force-citywide" in job.get("extra", []):
                detail = "citywide: labels step is skipped by design"
            else:
                site_dir = q.BASE / "phase4" / "sites" / y
                n = len(list(site_dir.glob("*_mask.tif"))) if site_dir.exists() else 0
                state, detail = ("OK", f"{n} site masks") if n else \
                                ("MISSING", f"no site masks in {site_dir}")
        elif step == "tile":
            import pandas as pd
            # THE TAGGED PATH, NOT THE LEGACY ONE. Every queue job passes --run-tag
            # (line ~532), so the engine tiles into tiles/{y}__{tag}/ via
            # common.tile_dir_for(). This check read tiles/{y}/ — the pre-branch
            # untagged directory, which for every year still holds an index from
            # some earlier arm. So VERIFY:tile did not fail; it PASSED, against a
            # completely different arm's tiles, and reported their count as this
            # arm's. A false OK is worse than a false MISSING, so when the tagged
            # index is absent this now reports MISSING and NAMES the legacy index
            # rather than quietly accepting it.
            idx = q._tagged_tile_index(y, tag)
            if not idx.exists():
                legacy = q.BASE / "phase4" / "tiles" / y / f"tile_index_{y}.csv"
                extra = (f"; legacy untagged {legacy.name} exists and is NOT this "
                         f"arm's — not accepted") if legacy.exists() else ""
                state, detail = "MISSING", f"no {idx.parent.name}/{idx.name}{extra}"
            else:
                df = pd.read_csv(idx)
                if not len(df):
                    state, detail = "NO_TILES", "index has 0 rows"
                else:
                    probe = pd.concat([df.head(10), df.tail(10)])
                    n_miss = sum(1 for p in probe["img_path"]
                                 if not Path(str(p)).exists())
                    state = "BAD_INDEX" if n_miss else "OK"
                    detail = (f"{len(df)} tiles indexed; probed {len(probe)} "
                              f"paths, {n_miss} missing")
        elif step == "train":
            import zipfile
            ck = q.BASE / "phase4" / "models" / f"sem_best_{y}_{tag}.pt"
            if not ck.exists():
                state, detail = "MISSING", f"no {ck.name}"
            else:
                mb = ck.stat().st_size / 1e6
                if mb < 50:
                    state, detail = "BAD_CKPT", f"{mb:.0f}MB — truncated?"
                elif not zipfile.is_zipfile(ck):
                    state, detail = "BAD_CKPT", f"{mb:.0f}MB, not a zip archive"
                else:
                    state, detail = _verify_ckpt_identity(ck, y, tag, mb, step_start)
        elif step == "evaluate":
            rep = q.BASE / "phase4" / "eval" / "semantic_eval_report.csv"
            state, detail = _verify_eval_rows(rep, y, tag, step_start)
        elif step == "inference":
            out = q.MASKS / f"edmonds_canopy_prob_{y}_{tag}.tif"
            state, detail = _check_prob_raster(out)
        elif step == "postproc":
            # THE DELIVERABLE. step_postproc writes two artifacts and both matter:
            # the binary mask raster and the polygonised GPKG. Checking only one
            # would pass a run that produced half a deliverable.
            mtif = q.MASKS / f"edmonds_canopy_mask_{y}_{tag}.tif"
            gpkg = q.MASKS / f"edmonds_canopy_mask_{y}_{tag}.gpkg"
            missing = [q.name for q in (mtif, gpkg) if not q.exists()]
            if missing:
                state, detail = "MISSING", f"no {', '.join(missing)}"
            else:
                mb_t = mtif.stat().st_size / 1e6
                mb_g = gpkg.stat().st_size / 1e6
                if mb_g < 0.01:
                    state, detail = "EMPTY", f"GPKG is {mb_g*1000:.0f}KB — no polygons"
                else:
                    state = "OK"
                    detail = f"mask {mb_t:.0f}MB, gpkg {mb_g:.1f}MB"
                    if step_start:
                        old = [q.name for q in (mtif, gpkg)
                               if q.stat().st_mtime < step_start - 5]
                        if old:
                            state = "BAD_CKPT"
                            detail = (f"{', '.join(old)} PREDATE this step — not "
                                      f"what this run produced")
        else:
            # AN UNRECOGNISED STEP MUST NOT PASS. `state` is initialised to "OK",
            # so before this branch existed any step without an elif fell through
            # every test and was recorded OK with an empty detail — verified
            # having checked nothing. That is the silent-pass class this queue has
            # spent a week closing, and adding postproc above would have widened it.
            state, detail = "UNCHECKED", f"no verifier for step {step!r}"
    except Exception as e:                                      # noqa: BLE001
        state, detail = "UNCHECKED", f"{type(e).__name__}: {e}"[:200]
    if reverify:
        detail = f"[re-verify of a skipped step] {detail}"
    rec = dict(job=job["id"], year=y, tag=tag, step=f"VERIFY:{step}",
               state=state, exit="", minutes="", detail=detail, **q._ident(),
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    rows.append(rec)
    q._status_write(rows)
    if state in q._VERIFY_UNVERIFIED:
        # Loud, and worded so it can never be misread as a pass. It does not stop
        # the job (a checker that throws is not proof the artifact is bad), but it
        # is not evidence of anything either, and the next launch re-checks.
        print(f"  VERIFY:{step} {job['id']}: {state} — COULD NOT CHECK THIS "
              f"ARTIFACT, continuing UNPROVEN.  {detail}", flush=True)
    else:
        print(f"  VERIFY:{step} {job['id']}: {state}  {detail}")
    return state not in q._VERIFY_HARD_FAIL

def _recheck_skipped_verify(job, rows, prior):
    """A job whose every step was skipped: is its raster STILL what was verified?

    D9 (2026-08-29). The old branch printed "already OK" and read nothing at all —
    a launch could report a job verified having opened no file, so a raster deleted,
    truncated or overwritten between launches still counted as this launch's pass.

    Re-READING it is not the answer: a relaunch re-verify hung the queue in
    uninterruptible disk sleep on a 146 MB FUSE read (2018s_fx, 2026-08-27), which
    is exactly why the skip exists. But a stat() is one metadata call, and it is
    enough to catch the artifact being gone or a different size than the verdict
    measured.

    The row it writes is deliberately NOT "OK": this launch did not re-read the
    raster and must not claim it did. OK_CACHED means "the recorded verdict stands
    and the file still matches it", which is a weaker and truer statement.
    """
    q = _q()
    out = q.MASKS / f"edmonds_canopy_prob_{job['year']}_{job['tag']}.tif"
    p_state, p_detail, p_ts = prior if prior else ("", "", "")
    try:
        if not out.exists():
            state, detail = "MISSING", (f"recorded {p_state} at {p_ts} but the raster "
                                        f"is GONE now: {out.name}")
        else:
            mb = out.stat().st_size / 1e6
            want = _mb_from_verdict(p_detail)
            if want is None:
                state = "UNVERIFIED"
                detail = (f"{mb:.0f}MB on disk; the recorded verdict ({p_state} at "
                          f"{p_ts}) carries no size to compare — existence only")
            elif abs(round(mb) - want) > 1:
                state = "SIZE_CHANGED"
                detail = (f"{mb:.0f}MB now vs {want}MB when verified at {p_ts} — "
                          f"this is not the raster that passed")
            else:
                state = "OK_CACHED"
                detail = (f"{mb:.0f}MB, unchanged since {p_state} at {p_ts}; not "
                          f"re-read (FUSE read hang guard, 2018s_fx 2026-08-27)")
    except Exception as e:                                      # noqa: BLE001
        state, detail = "UNCHECKED", f"{type(e).__name__}: {e}"[:200]
    rec = dict(job=job["id"], year=job["year"], tag=job["tag"], step="VERIFY",
               state=state, exit="", minutes="", detail=detail, **q._ident(),
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    rows.append(rec)
    q._status_write(rows)
    print(f"  VERIFY {job['id']}: {state}  {detail}")
    return state not in q._VERIFY_HARD_FAIL
