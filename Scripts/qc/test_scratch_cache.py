"""The ortho scratch cache: pins, the eviction floor, and the crash states.

WHAT THIS GUARDS. `phase4seg/scratchcache.py` turns `LOCAL_SCRATCH` from a place every
step deletes its ortho out of into a keyed cache that survives the step. Measured
motivation: the SAME 11.5 GB ortho `2017_king_rgb.tif` was staged four times across the
pilot and its baseline (`phase4/qc/timing_events.csv`), and re-staging is 42% of all
staged seconds all-time / 53% post-08-30
(Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §2). Keeping bytes instead of deleting
them buys that back — and introduces exactly one new hazard class: something may now be
deleted while another process is reading it, or kept while the disk fills.

So the two gates that make the cache safe are the pin and the floor, and per CLAUDE.md
§3.4c neither counts as a gate until it has been SHOWN TO FIRE on a known-bad input.
Every gate here is therefore tested in PAIRS: the protective case, and the same scenario
with the gate disabled so the opposite outcome is observed. A test that only ever passes
proves the code ran, not that the guard works.

  pin       (a) pinned entry survives eviction  /  (b) same scenario, pin removed → evicted
  floor     (e) floor set → two entries evicted  /  (f) floor zeroed → NOTHING evicted

HARNESS. Every path is under `tmp_path` (`qc/conftest.py` forbids lake writes anyway);
the cache root is injected through `scratchcache.cache_root(root=...)`, which every
public function accepts, so nothing here touches `/content`. `shutil.disk_usage` is
replaced by a fake that computes free space FROM THE FILES IN THE ROOT, so deleting a
payload really does raise free space and the evictor's stopping point is observable
rather than asserted. Sizes are bytes, not gigabytes, with `FLOOR_ABS` scaled to match —
the arithmetic is the same and the fixtures are real files.

TWO PROCESSES, ONE VM is the configuration that matters (two arms per runtime), and it is
simulated rather than spawned: a "peer" is a pin file or a `copying` sidecar carrying a
foreign pid, with `phase4seg.names.pid_alive` steered to say whether that pid is alive.
`names.pid_alive` returns True unconditionally off POSIX (names.py::pid_alive, and
`os.kill` is AST-banned by qc/test_queue_verify.py), so every liveness test MUST patch it
or it would pass on Windows for the wrong reason.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_scratch_cache.py -q
"""
import json
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

scratchcache = pytest.importorskip("phase4seg.scratchcache")
common = pytest.importorskip("phase4seg.common")
names = pytest.importorskip("phase4seg.names")

TOTAL = 10_000          # fake device size, bytes
UNIT = 1_000            # one "ortho"
DEAD_PID = 987_654      # never alive; every liveness test steers pid_alive anyway


@pytest.fixture
def env(tmp_path, monkeypatch, capsys):
    """A cache root on tmp_path with a disk whose free space follows its contents."""
    root = tmp_path / "scratch"
    root.mkdir()
    drive = tmp_path / "drive"
    drive.mkdir()
    state = {"reserved": 0}          # bytes consumed by things outside the root

    def _du(_p):
        # Payload bytes only. The `.cache/` journal is a few hundred bytes per entry
        # against multi-GB payloads, so counting it here would just add noise to the
        # arithmetic these tests are pinning; `state["reserved"]` stands for everything
        # else on the device (tiles/, checkpoints, the OS).
        used = sum(f.stat().st_size for f in root.rglob("*")
                   if f.is_file() and scratchcache.CACHE_DIR_NAME not in f.parts)
        return SimpleNamespace(total=TOTAL, used=used + state["reserved"],
                               free=TOTAL - used - state["reserved"])

    monkeypatch.setattr(shutil, "disk_usage", _du)
    # Only THIS process is alive unless a test says otherwise. Without this the
    # off-POSIX default (True for every pid) would make the dead-pid branches
    # unreachable on the machine these tests actually run on.
    monkeypatch.setattr(names, "pid_alive", lambda pid: int(pid) == os.getpid())

    copies = []
    real_copy2 = shutil.copy2

    def _counting_copy2(src, dst, *a, **kw):
        copies.append((Path(src), Path(dst)))
        return real_copy2(src, dst, *a, **kw)

    monkeypatch.setattr(shutil, "copy2", _counting_copy2)
    # Small, explicit numbers: the floor arithmetic is identical at any scale.
    monkeypatch.setattr(scratchcache, "FLOOR_ABS", 2 * UNIT)
    monkeypatch.setattr(scratchcache, "FLOOR_FRAC", 0.0)
    common._timers.clear()

    def _src(name, nbytes=UNIT):
        p = drive / name
        p.write_bytes(b"x" * nbytes)
        return p

    def _entry(name, nbytes=UNIT, last_use=0.0, state_="ready", src=None,
               ts_start=None):
        """Fabricate a cache entry directly, so `last_use` is controllable.

        `ts_start` DEFAULTS TO NOW, and that default is load-bearing for any `copying`
        record: `_copier_alive` tests the record's AGE before it tests its pid, so a
        hardcoded 0.0 here would make every fabricated copier ~56 years stale and the
        dead-pid leg of the crash-state tests would never be reached. That is not a
        hypothetical — it is how those tests were written first, and mutating the pid
        check to `return True` left the whole suite green.
        """
        s = src if src is not None else _src(name, nbytes)
        payload = scratchcache._payload_path(s, root=root)
        payload.write_bytes(b"y" * nbytes)
        st = s.stat()
        scratchcache._write_sidecar(scratchcache._key(s), root, {
            "state": state_, "key": scratchcache._key(s), "src": str(s),
            "src_size": st.st_size, "src_mtime": st.st_mtime,
            "payload": payload.name, "bytes": nbytes, "pid": os.getpid(),
            "host": "test",
            "ts_start": time.time() if ts_start is None else ts_start,
            "ts_ready": last_use, "last_use": last_use})
        return SimpleNamespace(src=s, payload=payload,
                               key=scratchcache._key(s))

    return SimpleNamespace(root=root, drive=drive, state=state, copies=copies,
                           src=_src, entry=_entry, monkeypatch=monkeypatch,
                           capsys=capsys, tmp=tmp_path)


def _engine_symbol(name):
    """Source of one engine function, LOCATED BY SYMBOL rather than by file path.

    qc/test_status_discovery.py::test_no_gate_still_hardcodes_the_engine_file_it_checks
    bans reading `core.py` by path: four gates did it, three written the same day, and
    each one silently stopped checking anything the moment the function moved. The two
    ordering assertions below are structural claims about a function, not about a file.
    """
    from phase4seg.names import symbol_body

    pkg = Path(__file__).resolve().parents[1] / "pipeline" / "phase4seg"
    body = symbol_body(pkg, name, "function")
    assert body, f"{name} not found in the engine package"
    return body


def _pins(env, key):
    return sorted(p.name for p in scratchcache._pin_dir(env.root).glob(f"{key}.*.pin"))


def _payloads(env):
    return sorted(p.name for p in env.root.iterdir() if p.is_file())


# ══════════════════════════════════════════════════════════════════════════════
#  THE PIN — (a)/(b) are the mutation pair
# ══════════════════════════════════════════════════════════════════════════════

def test_a_pinned_entry_survives_eviction(env):
    """(a) An entry a live process is reading is not evicted, however tight the disk.

    This is the hazard the cache introduces and today's delete-everything cannot have:
    two arms per VM is a real configuration (CLAUDE.md §3.4, concurrency 3-4), and one
    arm's `stage()` must not unlink the ortho the other arm has open.
    """
    keep = env.entry("keep.tif", last_use=1.0)
    other = env.entry("other.tif", last_use=2.0)
    scratchcache.pin(keep.payload, root=env.root)
    env.state["reserved"] = TOTAL - 2 * UNIT - 500       # free = 500

    ok = scratchcache.reserve(UNIT, root=env.root)

    assert keep.payload.exists(), "the pinned entry was evicted under a live reader"
    assert not other.payload.exists(), "the evictor did not free the unpinned entry"
    assert ok is True


def test_b_the_same_entry_is_evicted_once_the_pin_is_gone(env):
    """(b) THE MUTATION. Identical to (a) except the pin file is removed, so the entry
    IS evicted. Without this the pin test above would pass on an implementation that
    never evicts anything at all, and the gate would be decorative."""
    keep = env.entry("keep.tif", last_use=1.0)
    env.entry("other.tif", last_use=2.0)
    scratchcache.pin(keep.payload, root=env.root)
    for p in scratchcache._pin_dir(env.root).glob("*.pin"):
        p.unlink()
    env.state["reserved"] = TOTAL - 2 * UNIT - 500

    scratchcache.reserve(UNIT, root=env.root)

    assert not keep.payload.exists(), "the floor did not evict an UNPINNED entry"


def test_c_a_pin_whose_pid_is_dead_is_absent(env):
    """(c) A pin left by a process that died is not protection. Liveness is
    names.py::pid_alive, patched here — off POSIX it answers True for every pid, so an
    unpatched version of this test would pass without exercising the branch."""
    e = env.entry("keep.tif", last_use=1.0)
    scratchcache._pin_dir(env.root).mkdir(parents=True, exist_ok=True)
    (scratchcache._pin_dir(env.root) / f"{e.key}.{DEAD_PID}.pin").write_text("{}")
    env.state["reserved"] = TOTAL - UNIT - 100

    scratchcache.reserve(UNIT, root=env.root)

    assert not e.payload.exists(), "a dead process's pin held an entry hostage"


def test_d_a_live_pin_blocks_invalidate_and_the_caller_degrades(env):
    """(d) invalidate() is the ONE call that still deletes, so it is the one that must
    refuse under a reader. The caller then degrades to the source path — today's
    behaviour when staging fails — rather than deleting under an open fd."""
    e = env.entry("keep.tif", last_use=1.0)
    scratchcache._pin_dir(env.root).mkdir(parents=True, exist_ok=True)
    peer = os.getpid() + 1
    (scratchcache._pin_dir(env.root) / f"{e.key}.{peer}.pin").write_text("{}")
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: True)

    assert scratchcache.invalidate(e.payload, root=env.root) is False
    assert e.payload.exists()


def test_release_removes_only_our_own_pin(env):
    """A peer's pin is not ours to drop — the discipline queue_ledger.py
    ::publish_phase_marker already applies to its own marker."""
    e = env.entry("keep.tif")
    scratchcache.pin(e.payload, root=env.root)
    peer = os.getpid() + 1
    (scratchcache._pin_dir(env.root) / f"{e.key}.{peer}.pin").write_text("{}")

    scratchcache.release(e.payload, root=env.root)

    assert _pins(env, e.key) == [f"{e.key}.{peer}.pin"]
    assert e.payload.exists(), "release must not delete a cache entry"


def test_a_wedged_reader_cannot_hold_a_pin_forever(env):
    """PIN_MAX_MIN. pid liveness is exact within one VM, but a WEDGED (not dead)
    reader would hold an entry for the life of the runtime. The bound sits above any
    queue-legal reader; the derivation is asserted below, not restated."""
    e = env.entry("keep.tif", last_use=1.0)
    scratchcache.pin(e.payload, root=env.root)
    old = time.time() - (scratchcache.PIN_MAX_MIN + 1) * 60
    for p in scratchcache._pin_dir(env.root).glob("*.pin"):
        os.utime(p, (old, old))
    env.state["reserved"] = TOTAL - UNIT - 100

    scratchcache.reserve(UNIT, root=env.root)

    assert not e.payload.exists()


def test_pin_max_min_is_derived_from_the_queue_budget():
    """GRAFT 6, kept honest by construction. The engine cannot import
    phase4_train_queue (queue_ledger.py::_q explains why: a bare import EXECUTES the
    file a second time), so PIN_MAX_MIN is a module attribute — and this test is what
    stops the restatement rotting. pipeline/phase4_semantic_finetune.py preserves the
    `%run --args` path, and a hand-run step has NO queue timeout, so the bound must sit
    above any queue-legal reader, not at it."""
    q = pytest.importorskip("phase4_train_queue")
    assert scratchcache.PIN_MAX_MIN == 2 * max(q.STEP_TIMEOUT_MIN.values())


# ══════════════════════════════════════════════════════════════════════════════
#  THE FLOOR — (e)/(f) are the mutation pair
# ══════════════════════════════════════════════════════════════════════════════

def test_e_eviction_is_lru_and_stops_the_moment_the_floor_holds(env):
    """(e) Order AND stopping point. Four entries, ascending `last_use`; the evictor
    must take the two coldest and then STOP — an evictor that keeps going would empty
    a cache that had already made room, turning every later step back into a miss."""
    a = env.entry("a.tif", last_use=1.0)
    b = env.entry("b.tif", last_use=2.0)
    c = env.entry("c.tif", last_use=3.0)
    d = env.entry("d.tif", last_use=4.0)
    env.state["reserved"] = TOTAL - 4 * UNIT - 1500          # free = 1500

    ok = scratchcache.reserve(UNIT, root=env.root)           # target = 2000 + 1000

    assert ok is True
    assert not a.payload.exists() and not b.payload.exists(), "not LRU order"
    assert c.payload.exists() and d.payload.exists(), "the evictor did not stop"


def test_f_with_the_floor_zeroed_nothing_is_evicted(env):
    """(f) THE MUTATION. Same four entries, same 1500 free bytes, same 1000-byte
    request — but FLOOR_ABS/FLOOR_FRAC are 0, so the target is the request alone,
    1500 >= 1000 already holds, and NOTHING is evicted. That is what proves the two
    deletions in (e) were the floor firing and not eviction happening unconditionally.
    """
    env.monkeypatch.setattr(scratchcache, "FLOOR_ABS", 0)
    env.monkeypatch.setattr(scratchcache, "FLOOR_FRAC", 0.0)
    kept = [env.entry(f"{n}.tif", last_use=i + 1.0)
            for i, n in enumerate("abcd")]
    env.state["reserved"] = TOTAL - 4 * UNIT - 1500

    ok = scratchcache.reserve(UNIT, root=env.root)

    assert ok is True
    assert all(e.payload.exists() for e in kept), "eviction ran without a floor"


def test_g_when_the_space_is_unreachable_stage_returns_the_source(env):
    """(g) MUST-FIX 2's other half. The floor is the EVICTION TARGET, never the
    admission gate: after evicting everything unpinned we admit iff the bytes FIT.
    When they do not, `stage()` copies nothing and hands back the source — precisely
    today's behaviour when `_stage_imagery_local` fails, and today's
    postproc.py::_resolve_prob_source case (c). A full disk costs speed, never the run.

    AND IT COSTS NOTHING ELSE. The refusal used to arrive with the cache already
    emptied: 100 free against 400 evictable cannot reach a 1000-byte file however much
    is deleted, so every entry went and the stage was refused anyway. The reachability
    ladder (test (u)) evicts nothing here, so the next step's hits survive a refusal.
    """
    kept = [env.entry(f"{n}.tif", nbytes=100, last_use=i + 1.0)
            for i, n in enumerate("abcd")]
    src = env.src("big.tif", UNIT)
    env.state["reserved"] = TOTAL - 400 - 100                # 500 free even when empty

    got = scratchcache.stage(src, root=env.root)

    assert got == src
    assert env.copies == [], "it copied into a disk that cannot hold the file"
    assert all(e.payload.exists() for e in kept), (
        "a refused stage emptied the cache on its way out")


def test_the_floor_is_the_eviction_target_not_the_admission_gate(env):
    """MUST-FIX 2, stated as its own test. An 11.5 GB ortho must not need 33 GB free
    to be staged at all: today `_stage_imagery_local` stages whenever the bytes fit, and
    refusing where today would have staged reintroduces the windowed-FUSE pathology P4.3
    exists to remove. Here the floor (2000) cannot be met even after evicting every
    entry, yet the 1000-byte file fits — so it is staged."""
    env.entry("a.tif", nbytes=100, last_use=1.0)
    src = env.src("fits.tif", UNIT)
    env.state["reserved"] = TOTAL - 100 - 1200               # free = 1200 < floor+size

    got = scratchcache.stage(src, root=env.root)

    assert got == scratchcache._payload_path(src, root=env.root)
    assert got.read_bytes() == src.read_bytes()


def test_an_unreachable_target_does_not_empty_the_cache(env):
    """(s) THE PAIR'S PROTECTIVE HALF. Same entries, same free space as (t) below —
    only the REQUEST is bigger, so big that evicting everything unpinned could not
    reach `floor + nbytes*ADMIT_MARGIN`. Chasing it would delete every hit and buy
    nothing, since the writer either fits without them or fails with them.

    This is not hypothetical: core.py::step_inference used to reserve `img_h * img_w`,
    the UNCOMPRESSED grid (31.5e9 bytes for the 5 cm epochs against a 6.72 GB LZW file),
    which put the target beyond an ~87 GB runtime with the ortho pinned and emptied the
    cache at every inference step — destroying the cross-year hits on the tile step's
    shared rasters that the change exists to buy.
    """
    entries = [env.entry(f"{n}.tif", nbytes=100, last_use=i + 1.0)
               for i, n in enumerate("ab")]
    env.state["reserved"] = TOTAL - 200 - 3000               # free = 3000

    ok = scratchcache.reserve(3 * UNIT, root=env.root)        # target 5450, reach 3200

    assert all(e.payload.exists() for e in entries), "an out-of-reach target evicted"
    assert ok is True                                        # 3000 free >= 3000 asked


def test_a_reachable_target_still_evicts_everything_it_needs(env):
    """(t) THE MUTATION. IDENTICAL entries and IDENTICAL free space to (s) — the only
    change is a request small enough that the target IS reachable, and now BOTH entries
    go. That is what proves (s)'s survivors were the reachability cap firing and not
    eviction quietly being broken.

    It also pins the fallback's other half: the cap drops to `max(floor, nbytes)`, never
    to the floor alone, because a floor-only fallback would refuse a stage that eviction
    could have satisfied — the one regression "never worse than today" forbids.
    """
    entries = [env.entry(f"{n}.tif", nbytes=100, last_use=i + 1.0)
               for i, n in enumerate("ab")]
    env.state["reserved"] = TOTAL - 200 - 3000               # free = 3000, as in (s)

    ok = scratchcache.reserve(UNIT, root=env.root)           # target 3150, reach 3200

    assert not any(e.payload.exists() for e in entries), "the evictor stopped short"
    assert ok is True


def test_u_a_request_beyond_every_byte_in_the_cache_evicts_nothing(env):
    """(u) THE REACHABILITY LADDER's protective half, and the hole (s)/(t) left open.

    (s) only ever showed the cap working where `max(floor, nbytes)` happened to be
    satisfied ALREADY. It is not a bound: with free 250 and 400 evictable bytes, a
    1000-byte request capped to the 2000-byte floor is still out of reach, the loop runs
    off the end of the candidate list, and the cache is emptied to reach nothing —
    exactly the outcome the cap's own comment says must not happen. The ladder takes the
    largest of `floor + nbytes*ADMIT_MARGIN`, `max(floor, nbytes)` and `nbytes` that
    eviction can actually reach, and when even the last is out of reach it evicts
    NOTHING and says how far short it is.
    """
    entries = [env.entry(f"{n}.tif", nbytes=100, last_use=i + 1.0)
               for i, n in enumerate("abcd")]
    env.state["reserved"] = TOTAL - 400 - 250            # free = 250, reach = 650

    ok = scratchcache.reserve(UNIT, root=env.root)       # need 1000 > 650
    out = env.capsys.readouterr().out

    assert all(e.payload.exists() for e in entries), "the cache was emptied for nothing"
    assert ok is False                                   # 250 free < 1000 asked
    assert "short" in out.lower(), out                   # the shortfall is logged


def test_v_a_reachable_request_still_evicts_exactly_the_lru_tail(env):
    """(v) THE MUTATION on (u). IDENTICAL entries, IDENTICAL free space — only the
    request is small enough that the bottom rung (`nbytes` itself) IS reachable. Two
    coldest entries go and the evictor stops; the two warmest survive. That is what
    proves (u)'s survivors were the ladder refusing an impossible target and not
    eviction being broken, AND that the ladder still evicts only what the target
    requires — before it, this same case deleted all four."""
    a, b, c, d = (env.entry(f"{n}.tif", nbytes=100, last_use=i + 1.0)
                  for i, n in enumerate("abcd"))
    env.state["reserved"] = TOTAL - 400 - 250            # free = 250, reach = 650, as (u)

    ok = scratchcache.reserve(400, root=env.root)        # need 400 <= 650

    assert not a.payload.exists() and not b.payload.exists(), "not the LRU tail"
    assert c.payload.exists() and d.payload.exists(), "the evictor did not stop"
    assert ok is True


def test_the_entry_being_made_room_for_is_never_the_one_evicted(env):
    """`keep_key` — a STRUCTURAL guarantee, not a fix for a live bug. Every call site
    today protects the entry it is about to read with a pin instead (`_lookup` pins
    before it validates; postproc.py::_resolve_prob_source pins before it reserves), and
    the one window a pin does not cover is narrow: a peer publishing `ready` for this
    key between our `_lookup` miss and our own eviction, whose fresh copy we would then
    delete and immediately re-make. `stage()` passes its own key so no later refactor
    can widen that."""
    keep = env.entry("keep.tif", nbytes=100, last_use=1.0)     # the COLDEST
    other = env.entry("other.tif", nbytes=100, last_use=2.0)
    env.state["reserved"] = TOTAL - 200 - 250                  # free = 250

    scratchcache._evict_to_target(300, env.root, keep_key=keep.key)

    assert keep.payload.exists(), "the entry being made room for was evicted"
    assert not other.payload.exists(), "the evictor did not free the next-coldest"


def test_without_keep_key_that_same_entry_is_the_first_to_go(env):
    """THE MUTATION on the test above: same two entries, same free space, same request,
    no `keep_key` — and the coldest (the one being made room for) is exactly what LRU
    takes first."""
    keep = env.entry("keep.tif", nbytes=100, last_use=1.0)
    other = env.entry("other.tif", nbytes=100, last_use=2.0)
    env.state["reserved"] = TOTAL - 200 - 250

    scratchcache._evict_to_target(300, env.root)

    assert not keep.payload.exists(), "eviction is not LRU-ordered"
    assert other.payload.exists()


def test_reserve_creates_nothing_when_the_root_is_absent(env):
    """reserve() is a MAKE-ROOM call: an absent root holds nothing to evict and nothing
    yet written into it, so it must not mkdir one.

    THE BUG THIS PINS was outside the cache entirely. `config.LOCAL_SCRATCH` is
    `/content/phase4_scratch`, which on Windows is DRIVE-RELATIVE, so the unpatched
    staging.py::_stage_from_bundle reserve under qc/test_tile_bundle.py created
    `D:\\content\\phase4_scratch` on the dev box and pointed the evictor's scandir at the
    real drive. qc/conftest.py does not catch it — it is not a lake write.
    """
    missing = env.tmp / "not-created-by-a-make-room-call"

    assert scratchcache.reserve(UNIT, root=missing) is True
    assert not missing.exists()


def test_a_sidecarless_payload_is_never_evicted(env):
    """(m) NAMESPACE. The evictor may delete only a payload this cache wrote a `ready`
    sidecar for. Everything else in LOCAL_SCRATCH — tiles/, bundles/, tileout/, every
    common.py::_local_artifact_path write artifact, a pre-cache stump — is un-owned and
    untouchable. Deleting a payload with no sidecar is the one direction that could
    destroy another step's in-flight multi-GB write."""
    stump = env.root / "someone_elses__deadbeef.tif"
    stump.write_bytes(b"z" * UNIT)
    (env.root / "tiles").mkdir()
    (env.root / "tiles" / "t.tif").write_bytes(b"z" * UNIT)
    env.state["reserved"] = TOTAL - 2 * UNIT - 100

    scratchcache.reserve(UNIT, root=env.root)

    assert stump.exists() and (env.root / "tiles" / "t.tif").exists()


# ══════════════════════════════════════════════════════════════════════════════
#  Crash states — what a fresh process trusts
# ══════════════════════════════════════════════════════════════════════════════

def test_h_part_orphans_are_swept_by_pid_not_by_age(env):
    """(h) The pid is IN the filename, so a VM death mid-copy does not have to wait out
    common.py::_sweep_part_orphans' 24 h. A live peer's `.part` is left alone."""
    dead = env.root / f"x__aaaaaaaa.tif.part.{DEAD_PID}.abc123"
    live = env.root / f"y__bbbbbbbb.tif.part.{os.getpid()}.def456"
    dead.write_bytes(b"q" * 10)
    live.write_bytes(b"q" * 10)

    scratchcache.sweep(root=env.root)

    assert not dead.exists(), "a dead process's .part was left to leak"
    assert live.exists(), "a live copy in flight was deleted under the writer"


def test_i_a_complete_payload_under_a_dead_copying_sidecar_is_promoted(env):
    """(i) THE ONE GAP, decided explicitly. A crash between the rename and the sidecar's
    flip to `ready` leaves a COMPLETE payload under `copying`. Promote it iff its size
    matches the source; nothing is left to chance in that window."""
    e = env.entry("a.tif", state_="copying")
    scratchcache._write_sidecar(e.key, env.root, dict(
        scratchcache._read_sidecar(e.key, env.root), pid=DEAD_PID))

    got = scratchcache.stage(e.src, root=env.root)

    assert got == e.payload
    assert env.copies == [], "a complete payload was re-copied instead of promoted"
    assert scratchcache._read_sidecar(e.key, env.root)["state"] == "ready"


def test_j_a_short_payload_under_a_dead_copying_sidecar_is_deleted(env):
    """(j) THE MUTATION on (i): same crash state, payload short → it is an interrupted
    copy, not a completed one. Delete and re-copy. This is the failure
    postproc.py::_resolve_prob_source documents at length, made survivable at last.

    `ts_start` IS FRESH so the record is resolved by its DEAD PID and by nothing else —
    a stale timestamp would resolve it through `_copier_alive`'s age leg and this test
    would pass without ever exercising the liveness check it is named for."""
    src = env.src("a.tif", UNIT)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"y" * 10)                            # short
    st = src.stat()
    scratchcache._write_sidecar(scratchcache._key(src), env.root, {
        "state": "copying", "key": scratchcache._key(src), "src": str(src),
        "src_size": st.st_size, "src_mtime": st.st_mtime, "payload": payload.name,
        "bytes": 0, "pid": DEAD_PID, "host": "test", "ts_start": time.time()})

    got = scratchcache.stage(src, root=env.root)

    assert got == payload
    assert got.stat().st_size == UNIT
    assert env.copies, "the stump was served instead of re-copied"


class _Crash(BaseException):
    """A simulated process death, mid-copy.

    A BaseException on purpose: it escapes BOTH of `scratchcache.py::stage`'s handlers
    (the inner `except OSError` around the copy and the outer `except Exception`), so
    what it leaves on disk is what a SIGKILL leaves — the `.part`, the `copying`
    sidecar, and whatever was already sitting at the canonical payload name. Not
    KeyboardInterrupt, which pytest intercepts for its own reasons.
    """


def test_a_stale_payload_under_a_crashed_copy_is_never_served(env):
    """THE PRE-CLEAR, and `.part` + os.replace is NOT what closes this.

    The publish is already atomic. The hole is one rung down, in `sweep`: its
    crash-state rule reads the CANONICAL name and promotes whatever it finds there iff
    the size matches the record's `src_size` — and it cannot tell our own os.replace
    result from a file that was already at that name (a pre-cache stump, a
    `common.py::_local_artifact_path` write artifact, an entry whose sidecar was lost).
    So: a right-sized WRONG-CONTENT payload, a `copying` record journalled over the top
    of it, a death before `ready` — and the next process gets a hit whose source, size
    and mtime all check out and whose bytes are somebody else's.

    `scratchcache.py::_clear_destination` makes the name absent BEFORE the journal, so
    a complete-sized file under a `copying` record can only have arrived through
    `_publish_payload`. Then the promotion is sound by construction.
    """
    src = env.src("a.tif", UNIT)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"z" * UNIT)          # right SIZE, wrong CONTENT, no sidecar
    counting = shutil.copy2                   # the fixture's counting wrapper

    def _die(s, d, *a, **kw):
        Path(d).write_bytes(b"z" * 10)        # a partial .part, as a real kill leaves
        raise _Crash("killed mid-copy")

    env.monkeypatch.setattr(shutil, "copy2", _die)
    with pytest.raises(_Crash):
        scratchcache.stage(src, root=env.root)

    env.monkeypatch.setattr(shutil, "copy2", counting)
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: False)   # the copier is gone

    got = scratchcache.stage(src, root=env.root)

    assert got.read_bytes() == src.read_bytes(), (
        "a payload this cache never wrote was promoted and served as a hit")
    assert env.copies, "the stale payload was promoted instead of re-copied"


def test_a_live_reader_blocks_the_pre_clear_and_the_caller_degrades(env):
    """The never-delete-under-a-reader rule reaches the pre-clear too. A live foreign
    pin on this key means somebody has the payload OPEN, so `_clear_destination`
    refuses and `stage()` hands back the source — today's behaviour whenever staging
    cannot proceed — rather than unlinking under an open fd."""
    src = env.src("a.tif", UNIT)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"z" * UNIT)
    key = scratchcache._key(src)
    scratchcache._pin_dir(env.root).mkdir(parents=True, exist_ok=True)
    (scratchcache._pin_dir(env.root) / f"{key}.{os.getpid() + 1}.pin").write_text("{}")
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: True)

    got = scratchcache.stage(src, root=env.root)

    assert got == src
    assert payload.exists(), "the pre-clear unlinked a payload a peer had open"
    assert env.copies == []


def test_a_peer_mid_copy_is_left_alone(env):
    """`copying` + a LIVE pid on this host: a peer is mid-copy. Do not touch it, do not
    serve it. We proceed into the copy path exactly as today, which serialises us behind
    that copy under the P11.4 lock and then re-checks."""
    src = env.src("a.tif", UNIT)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"y" * 10)
    peer = os.getpid() + 1
    st = src.stat()
    scratchcache._write_sidecar(scratchcache._key(src), env.root, {
        "state": "copying", "key": scratchcache._key(src), "src": str(src),
        "src_size": st.st_size, "src_mtime": st.st_mtime, "payload": payload.name,
        "bytes": 0, "pid": peer, "host": "test", "ts_start": time.time()})
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: True)

    got = scratchcache.stage(src, root=env.root)

    assert got == src, "a peer's in-flight copy was served as a hit"
    assert env.copies == [], "we copied over a peer's in-flight payload"


def test_a_peer_mid_copy_is_waited_out_under_the_p11_4_lock(env):
    """THE OTHER HALF of the test above, and the regression it exists to stop.

    A `copying` peer must NOT short-circuit to the source before the P11.4 lock. Today a
    >= STAGE_LOCK_MIN_BYTES ortho makes the second arm block on the Drive claim (up to
    STAGE_LOCK_MAX_WAIT_MIN), re-check, and then read NVMe for its whole step. Giving up
    early would make it read 11.5 GB windowed over FUSE instead — the P4.3 pathology,
    reintroduced for exactly the two-arms-per-VM case the cache is built around.

    The lock is simulated: entering it flips the peer's record to `ready`, which is what
    a real peer finishing its copy does.
    """
    src = env.src("a.tif", UNIT)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"y" * 10)
    key = scratchcache._key(src)
    st = src.stat()
    scratchcache._write_sidecar(key, env.root, {
        "state": "copying", "key": key, "src": str(src), "src_size": st.st_size,
        "src_mtime": st.st_mtime, "payload": payload.name, "bytes": 0,
        "pid": os.getpid() + 1, "host": "test", "ts_start": time.time()})
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: True)

    import contextlib as _ctx

    @_ctx.contextmanager
    def _peer_finishes(_src):
        payload.write_bytes(b"x" * UNIT)
        scratchcache._write_sidecar(key, env.root, dict(
            scratchcache._read_sidecar(key, env.root),
            state="ready", bytes=UNIT, ts_ready=time.time(), last_use=time.time()))
        yield

    env.monkeypatch.setattr(common, "_staging_lock_for", _peer_finishes)

    got = scratchcache.stage(src, root=env.root)

    assert got == payload, "the waiter gave up before the P11.4 lock"
    assert env.copies == [], "the waiter copied instead of taking the peer's result"


def _copying_record(env, src, payload, pid=None, ts_start=None, drop_pid=False):
    """Write a `copying` sidecar by hand, so its pid and `ts_start` are controllable."""
    key = scratchcache._key(src)
    st = src.stat()
    rec = {"state": "copying", "key": key, "src": str(src), "src_size": st.st_size,
           "src_mtime": st.st_mtime, "payload": payload.name, "bytes": 0,
           "pid": os.getpid() + 1 if pid is None else pid, "host": "test",
           "ts_start": time.time() if ts_start is None else ts_start}
    if drop_pid:
        rec.pop("pid")
    scratchcache._write_sidecar(key, env.root, rec)
    return key


def test_a_wedged_copier_cannot_hold_its_key_forever(env):
    """THE MUTATION PARTNER of test_a_peer_mid_copy_is_left_alone, and the asymmetry it
    closes. That test's peer is LIVE and RECENT, so it is waited on. This one's pid is
    equally live — `pid_alive` says True — but its `ts_start` is older than PIN_MAX_MIN,
    which no queue-legal step can be (the bound is 2x the queue's own inference timeout).

    A pin had that bound from the start; a `copying` record had none, and the
    consequences were worse: `_lookup` answered "wait" forever, `sweep` skipped the
    record, and `_evict_to_target` takes only `ready` candidates — so the entry could
    neither be served, nor re-copied, nor freed, for the life of the runtime.
    """
    src = env.src("a.tif", UNIT)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"y" * 10)                    # a short, abandoned stump
    stale = time.time() - (scratchcache.PIN_MAX_MIN + 1) * 60
    _copying_record(env, src, payload, ts_start=stale)
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: True)

    got = scratchcache.stage(src, root=env.root)

    assert got == payload, "a wedged copier's key was never resolved"
    assert got.read_bytes() == src.read_bytes()
    assert len(env.copies) == 1, "it did not re-copy after resolving the stale record"


def test_a_copying_record_with_no_pid_reads_as_dead_not_alive(env):
    """`names.pid_alive` fails OPEN — it returns True for anything it cannot interpret
    (names.py::pid_alive). That posture is right for every other caller, where it means
    "assume the peer is alive and keep the protection", and WRONG for exactly this one,
    where it would mean "never resolve this record". So `_copier_alive` requires an int.
    """
    src = env.src("a.tif", UNIT)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"y" * 10)
    _copying_record(env, src, payload, drop_pid=True)  # ts_start is FRESH: only the
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: True)   # pid is missing

    got = scratchcache.stage(src, root=env.root)

    assert got == payload
    assert len(env.copies) == 1


def test_an_entry_a_peer_is_reading_is_not_deleted_even_when_it_looks_stale(env):
    """The never-delete-under-a-reader rule is TOTAL, not just at invalidate()'s door.

    An entry whose size no longer matches its source is normally dropped and re-copied
    (test (k)). But if a peer has it pinned, that peer has it OPEN — and postproc opens
    the probability raster twice (header, then the windowed loop), so an unlink between
    the two ENOENTs the second. Leave it; take the source.
    """
    e = env.entry("a.tif")
    e.src.write_bytes(b"x" * (UNIT + 7))                      # now looks stale
    peer = os.getpid() + 1
    scratchcache._pin_dir(env.root).mkdir(parents=True, exist_ok=True)
    (scratchcache._pin_dir(env.root) / f"{e.key}.{peer}.pin").write_text("{}")
    env.monkeypatch.setattr(names, "pid_alive", lambda pid: True)

    got = scratchcache.stage(e.src, root=env.root)

    assert got == e.src
    assert e.payload.exists(), "a stale-looking entry was deleted under a live reader"
    assert env.copies == []


def test_k_a_ready_payload_whose_size_left_the_source_is_not_served(env):
    """(k) Size-only validation is the weak link and the cache EXTENDS its reach — a
    stale same-size copy used to die with the step and can now survive into the next
    one. So the hit test is re-run against the live source on every hit, and a
    mismatch invalidates rather than serving."""
    e = env.entry("a.tif")
    e.src.write_bytes(b"x" * (UNIT + 7))                      # the source changed

    got = scratchcache.stage(e.src, root=env.root)

    assert got == e.payload
    assert got.stat().st_size == UNIT + 7
    assert env.copies, "a stale payload was served"


def test_a_ready_payload_whose_source_mtime_moved_is_not_served(env):
    """GRAFT 3. `src_mtime` narrows the hit test past size alone. It does NOT prove
    content — the same words postproc.py::_resolve_prob_source uses about itself — but a
    re-uploaded ortho of identical length is exactly the substitution size cannot see,
    and the cost of the extra stat is one syscall against an 87-309 s copy."""
    e = env.entry("a.tif")
    future = time.time() + 10_000
    os.utime(e.src, (future, future))

    scratchcache.stage(e.src, root=env.root)

    assert env.copies, "an mtime-shifted source was served from the cache"


def test_l_a_sidecar_naming_a_different_source_is_refused_loudly(env):
    """(l) The key is an 8-hex sha256 of the FULL source path (common.py::_scratch_name;
    D18 fixed basename aliasing there for exactly this reason). 8 hex is 2^32 — small
    enough that a collision must be LOUD rather than silent, so the sidecar records the
    full source path and it is compared on every hit."""
    e = env.entry("a.tif")
    other = env.src("elsewhere.tif", UNIT)
    scratchcache._write_sidecar(e.key, env.root, dict(
        scratchcache._read_sidecar(e.key, env.root), src=str(other)))

    got = scratchcache.stage(e.src, root=env.root)
    out = env.capsys.readouterr().out

    assert "collision" in out.lower() or "different source" in out.lower(), out
    assert got in (e.payload, e.src)


def test_p_an_unreadable_source_is_a_miss_not_a_hit(env):
    """(p) Mounts that lie. Any OSError on the source stat → UNVERIFIABLE → miss and
    fall back to the source path. Fail CLOSED, the posture
    common.py::_staging_lock_for takes when its own stat fails."""
    e = env.entry("a.tif")
    e.src.unlink()

    got = scratchcache.stage(e.src, root=env.root)

    assert got == e.src
    assert e.payload.exists(), "an unverifiable source deleted a payload"


def test_q_a_zero_byte_source_is_treated_as_unreadable(env):
    """(q) A source stat reporting 0 bytes is a wedged mount answering, not a match.
    Serving a 0-byte 'hit' would hand rasterio an empty file."""
    src = env.src("a.tif", 0)
    payload = scratchcache._payload_path(src, root=env.root)
    payload.write_bytes(b"")
    st = src.stat()
    scratchcache._write_sidecar(scratchcache._key(src), env.root, {
        "state": "ready", "key": scratchcache._key(src), "src": str(src),
        "src_size": 0, "src_mtime": st.st_mtime, "payload": payload.name,
        "bytes": 0, "pid": os.getpid(), "host": "test", "ts_start": 0.0,
        "ts_ready": 0.0, "last_use": 0.0})

    assert scratchcache.stage(src, root=env.root) == src


def test_the_cache_never_raises_out_to_its_caller(env):
    """The never-raises contract postproc.py::_resolve_prob_source already sets, applied
    to the cache: a cache problem costs speed, never the run."""
    src = env.src("a.tif", UNIT)

    def _boom(*a, **kw):
        raise OSError(5, "Input/output error")

    env.monkeypatch.setattr(shutil, "copy2", _boom)

    assert scratchcache.stage(src, root=env.root) == src


# ══════════════════════════════════════════════════════════════════════════════
#  Round trips
# ══════════════════════════════════════════════════════════════════════════════

def test_n_the_same_source_staged_twice_copies_once(env):
    """(n) The whole point, in one test: the second stage is a stat, not 87-309 s of
    Drive. Measured cost this replaces: `2017_king_rgb.tif` (11.5 GB) staged by tile at
    123.5 s and again by inference at 87.1 s on the SAME baseline A100 box
    (phase4/qc/timing_events.csv)."""
    src = env.src("a.tif", UNIT)

    first = scratchcache.stage(src, root=env.root)
    scratchcache.release(first, root=env.root)
    second = scratchcache.stage(src, root=env.root)

    assert first == second != src
    assert len(env.copies) == 1, env.copies


def test_o_an_adopted_probability_raster_is_a_hit_on_the_next_step(env):
    """(o) THE POSTPROC ADOPTION PATH, and it is the one the queue actually takes.
    `POSTPROC_FOLLOWS` is set in exactly one place (cli.py) on the single-invocation
    path; under the queue `phase4_train_queue.py::run_step` launches ONE PROCESS PER
    --step, so it is False, inference used to unlink the raster, and the separate
    postproc process re-staged the whole 2.4-6.7 GB back down. adopt() writes a `ready`
    sidecar for a payload already in place — no bytes move — and the next process hits.
    """
    final = env.drive / "edmonds_canopy_prob_2017k.tif"
    final.write_bytes(b"p" * UNIT)                 # what _copy_to_drive just verified
    payload = scratchcache._payload_path(final, root=env.root)
    payload.write_bytes(b"p" * UNIT)               # the local write artifact, in place

    assert scratchcache.adopt(payload, final, root=env.root) is True
    scratchcache.release(payload, root=env.root)

    assert scratchcache.stage(final, root=env.root) == payload
    assert env.copies == [], "adoption re-copied a file that was already there"


def test_adopt_refuses_when_the_payload_does_not_match_its_source(env):
    """Adoption is only ever called where the verified write has JUST proved size and
    sha256 against Drive (core.py::step_inference, right after _copy_to_drive). If the
    two disagree anyway, write no sidecar: an entry the evictor owns must be one it can
    validate."""
    final = env.drive / "p.tif"
    final.write_bytes(b"p" * UNIT)
    payload = scratchcache._payload_path(final, root=env.root)
    payload.write_bytes(b"p" * 10)

    assert scratchcache.adopt(payload, final, root=env.root) is False
    assert scratchcache._read_sidecar(scratchcache._key(final), env.root) is None


def test_invalidate_removes_the_sidecar_with_the_payload(env):
    """GRAFT 5. A sidecar outliving its payload would leave the evictor counting bytes
    that are already gone, so it would stop freeing space it could actually free."""
    e = env.entry("a.tif")

    assert scratchcache.invalidate(e.payload, root=env.root) is True
    assert not e.payload.exists()
    assert scratchcache._read_sidecar(e.key, env.root) is None


def test_release_of_an_unowned_scratch_file_still_deletes_it(env):
    """`common.py::_unstage_imagery_local` routes here, and its historical contract is
    unlink. A payload with NO sidecar is not a cache entry — nobody would ever free it —
    so release keeps today's behaviour for it. Only OWNED entries survive a release."""
    stump = env.root / "not_ours__12345678.tif"
    stump.write_bytes(b"z" * 10)

    scratchcache.release(stump, root=env.root)

    assert not stump.exists()


# ══════════════════════════════════════════════════════════════════════════════
#  Telemetry contract
# ══════════════════════════════════════════════════════════════════════════════

def test_r_a_hit_emits_no_stage_timing_event(env):
    """(r) THE FABRICATED-WIN GUARD. `⏱ stage <file>: 0.0s` under the exact event name
    this saving will be measured from would put a fake row in
    phase4/qc/timing_events.csv — the series qc/instruments/harvest_timing_events.py
    reads, and the one the 39.7 MB/s Drive-throughput median comes off. Today's
    exists+size early return emits nothing; a hit keeps emitting nothing. Same
    discipline as staging.py::_stage_tiles_local's `untick` calls."""
    src = env.src("a.tif", UNIT)
    first = scratchcache.stage(src, root=env.root)
    scratchcache.release(first, root=env.root)
    env.capsys.readouterr()
    common._timers.clear()

    scratchcache.stage(src, root=env.root)
    out = env.capsys.readouterr().out

    assert "⏱" not in out, out
    assert f"stage {src.name}" not in common._timers, common._timers
    assert "cache hit" in out, out


def test_a_miss_still_emits_the_event_under_its_historical_name(env):
    """The other half: the event name a MISS publishes must not change, or the before/
    after comparison this whole change is validated by would not be comparable. The
    name is the one common.py::_stage_imagery_local has always used."""
    src = env.src("a.tif", UNIT)

    scratchcache.stage(src, root=env.root)
    out = env.capsys.readouterr().out

    assert f"⏱ stage {src.name}:" in out, out


def test_a_retried_copy_times_only_the_attempt_that_succeeded(env):
    """The published duration must be the duration of the copy the row NAMES.

    `stage()` retries once on OSError — ENOSPC is the realistic one and the cache itself
    makes it likelier — and evicts between the attempts. With a single tick outside that
    loop, the failed attempt and the eviction sat inside the interval the row reported,
    so `⏱ stage <file>` overstated a copy that was fast and MB/s came out wrong LOW,
    precisely in the constrained-disk regime this change creates. Those rows are ingested
    by qc/instruments/harvest_timing_events.py into phase4/qc/timing_events.csv, which is
    the series the saving is to be validated against AND the source of the 39.7 MB/s
    Drive-throughput median — so a poisoned duration corrupts the evidence, not just a
    log line. The timer is re-armed per attempt; here the doomed attempt burns 0.3 s and
    the successful one is instant.
    """
    src = env.src("big.tif", UNIT)
    outer = shutil.copy2                      # the fixture's counting wrapper
    attempts = []

    def _flaky(s, d, *a, **kw):
        attempts.append(1)
        if len(attempts) == 1:
            time.sleep(0.30)
            raise OSError(28, "No space left on device")
        return outer(s, d, *a, **kw)

    env.monkeypatch.setattr(shutil, "copy2", _flaky)

    got = scratchcache.stage(src, root=env.root)
    out = env.capsys.readouterr().out

    assert got == scratchcache._payload_path(src, root=env.root)
    assert len(attempts) == 2, attempts
    rows = [ln for ln in out.splitlines() if f"⏱ stage {src.name}:" in ln]
    assert len(rows) == 1, out                # the failed attempt publishes nothing
    assert float(rows[0].rsplit(":", 1)[1].strip().rstrip("s")) < 0.25, rows


# ══════════════════════════════════════════════════════════════════════════════
#  Identity
# ══════════════════════════════════════════════════════════════════════════════

def test_the_key_is_the_hash_common_already_puts_in_the_payload_name(env):
    """One fact, one home (CLAUDE.md §3.3). The payload path stays exactly
    `LOCAL_SCRATCH / common.py::_scratch_name(src)` — nothing moves — which is what
    preserves postproc.py::_resolve_prob_source's "(a) and (b) resolve to the SAME
    scratch path by construction" and common.py::_unstage_imagery_local's
    startswith(LOCAL_SCRATCH) guard. The key must therefore BE the hash that name
    already carries, not a second rule that could drift from it."""
    src = env.src("a.tif", 4)
    assert scratchcache._key(src) in common._scratch_name(src)
    assert (scratchcache._payload_path(src, root=env.root)
            == env.root / common._scratch_name(src))


def test_two_sources_sharing_a_basename_do_not_alias(env):
    """D18's collision, on the cache's own terms: different years' native/ files
    routinely share a basename."""
    a = env.drive / "y1"
    b = env.drive / "y2"
    a.mkdir(); b.mkdir()
    (a / "ortho.tif").write_bytes(b"a" * UNIT)
    (b / "ortho.tif").write_bytes(b"b" * UNIT)

    pa = scratchcache.stage(a / "ortho.tif", root=env.root)
    pb = scratchcache.stage(b / "ortho.tif", root=env.root)

    assert pa != pb
    assert pa.read_bytes() != pb.read_bytes()


# ══════════════════════════════════════════════════════════════════════════════
#  Site-level: every former unlink now releases, and the two new calls are made
# ══════════════════════════════════════════════════════════════════════════════

def test_unstage_releases_an_owned_entry_instead_of_deleting_it(env):
    """common.py::_unstage_imagery_local is the ONE edit that converts every historical
    unlink site at once — labels.py::step_labels, tiling.py::_gather_citywide_coarse
    (x3), core.py::step_inference (x2), postproc.py::step_postproc. The per-site ledger
    of WHY each delete existed lives in that function's docstring."""
    e = env.entry("a.tif")
    scratchcache.pin(e.payload, root=env.root)
    env.monkeypatch.setattr(common, "LOCAL_SCRATCH", env.root)
    env.monkeypatch.setattr(scratchcache, "_DEFAULT_ROOT_OVERRIDE", env.root)

    common._unstage_imagery_local(e.payload)

    assert e.payload.exists(), "a release deleted an owned cache entry"
    assert _pins(env, e.key) == []


def test_step_inference_invalidates_the_destination_before_opening_it_for_write():
    """MUST-FIX 1, pinned as source structure. After adopt(), the probability raster is
    a `ready`, UNPINNED entry at the SAME path a same-VM rerun of that year+tag opens
    with rasterio.open(prob_out, "w"). Mid-write, a peer's stage()/reserve() could evict
    it — unlinking the file under the writer's open fd, so the write completes into an
    orphaned inode and _copy_to_drive then fails on a missing path. The destination must
    stop being a cache entry BEFORE the open: reserve() covers headroom, not the
    destination."""
    import ast
    fn = ast.parse(_engine_symbol("step_inference"))
    order = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in ("invalidate", "reserve",
                                                           "adopt"):
                order.append((n.lineno, f.attr))
            if (isinstance(f, ast.Attribute) and f.attr == "open"
                    and any(isinstance(a, ast.Constant) and a.value == "w"
                            for a in n.args)):
                order.append((n.lineno, "open_w"))
    seq = [k for _, k in sorted(order)]
    assert "invalidate" in seq and "reserve" in seq and "adopt" in seq, seq
    assert seq.index("invalidate") < seq.index("open_w"), seq
    assert seq.index("reserve") < seq.index("open_w"), seq
    assert seq.index("open_w") < seq.index("adopt"), seq


def test_step_inference_does_not_reserve_the_uncompressed_grid():
    """The reservation must be sized from a RASTER, never from the pixel grid.

    `reserve(img_h * img_w)` asked for 31.5e9 bytes on the 5 cm epochs (148736x211968,
    phase4/qc/imagery_geometry.csv) against a 6.72 GB LZW file — the measured spread and
    how it is re-derived live in scratchcache.py::PROB_RASTER_BYTES_ASSUMED, and the
    constant is checked against the CSV by the test below rather than restated here.
    The target it produced was unreachable on an ~87 GB
    runtime with the ortho pinned, so every inference step evicted every unpinned entry
    and the cross-year hits died. The cap in `_evict_to_target` bounds the DAMAGE of an
    out-of-reach target; this stops manufacturing one.
    """
    import ast
    fn = ast.parse(_engine_symbol("step_inference"))
    args = [n.args[0] for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "reserve" and n.args]
    assert args, "step_inference no longer reserves anything"
    for a in args:
        assert not isinstance(a, ast.BinOp), (
            f"the reservation is computed inline ({ast.dump(a)}) — the grid product is "
            "exactly the shape that regressed")
    assert "PROB_RASTER_BYTES_ASSUMED" in _engine_symbol("step_inference")


def test_the_assumed_raster_size_still_covers_every_measured_raster():
    """PROB_RASTER_BYTES_ASSUMED is ASSUMED — but it is assumed ABOVE something measured,
    so the measurement is read here rather than restated (CLAUDE.md §2.2). If a future
    epoch writes a bigger raster this fires, which is the correct outcome: the constant
    is then the thing to revisit, not this test."""
    import csv
    csv_path = (Path(__file__).resolve().parents[2] / "phase4" / "qc"
                / "timing_events.csv")
    if not csv_path.exists():
        pytest.skip("timing_events.csv is harvested from the lake; absent here")
    biggest = 0
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("label") or "").startswith("copy edmonds_canopy_prob_"):
                continue
            try:
                biggest = max(biggest, int(row["bytes"]))
            except (TypeError, ValueError, KeyError):
                continue
    assert biggest > 0, "no probability-raster copy events found to size against"
    assert scratchcache.PROB_RASTER_BYTES_ASSUMED >= biggest, (
        f"the largest raster measured is {biggest / 1e9:.2f} GB, above the assumed "
        f"{scratchcache.PROB_RASTER_BYTES_ASSUMED / 1e9:.2f} GB")


def test_the_bundle_extract_reserves_before_it_copies():
    """MUST-FIX 3. The tar and the extracted tree coexist in LOCAL_SCRATCH until
    staging.py::_stage_from_bundle unlinks the tar, so the reservation is for both."""
    import ast
    fn = ast.parse(_engine_symbol("_stage_from_bundle"))
    reserves = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "reserve"]
    # THE TRANSPORT MOVED (2026-09-08) and this pin had to move with it, or it would
    # have gone green by finding nothing: the 0.5 GB read is no longer
    # `shutil.copyfile` but `staging.py::_bounded_copy`'s chunk loop, a bare Name call
    # rather than an Attribute. Match both, so what is asserted is the write that
    # actually happens.
    copies = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
              and ((isinstance(n.func, ast.Attribute) and n.func.attr == "copyfile")
                   or (isinstance(n.func, ast.Name) and n.func.id == "_bounded_copy"))]
    assert reserves and copies and min(reserves) < min(copies), (reserves, copies)


def test_the_gap_census_names_every_local_scratch_writer():
    """MUST-FIX 3, the honest half. reserve() is only as good as its call sites, so the
    writers it does NOT cover are named in scratchcache.py's module docstring rather
    than left for someone to discover with an ENOSPC. This asserts the census stays
    complete: every module that writes into LOCAL_SCRATCH is mentioned there."""
    doc = scratchcache.__doc__ or ""
    for writer in ("ckpt.py", "tileout", "bundleout", "mask", "gpkg"):
        assert writer in doc, f"{writer} is missing from the LOCAL_SCRATCH gap census"


def test_no_new_constant_was_appended_to_config():
    """config.py is APPEND-ONLY / pure-move protected: its constants feed
    `_tile_signature`, so one more would force a ~20-min re-tile of EVERY year. The
    cache's tunables are module attributes here, as common.py::STAGE_LOCK_MIN_BYTES and
    its siblings are in common.py."""
    from phase4seg import config
    for name in ("FLOOR_ABS", "FLOOR_FRAC", "ADMIT_MARGIN", "PIN_MAX_MIN",
                 "CACHE_DIR_NAME", "PROB_RASTER_BYTES_ASSUMED"):
        assert not hasattr(config, name), f"config.py grew {name}"


def test_the_cache_is_stdlib_only_at_import_time():
    """scratchcache is imported by common.py at module scope, so it must not pull
    rasterio/geopandas/torch, and it must not import common back (a module-level cycle
    would half-initialise both). Engine-side imports are function-local, the same
    lazy-import discipline phase4seg/CLAUDE.md sets for torch."""
    import ast
    src = (Path(__file__).resolve().parents[1] / "pipeline" / "phase4seg"
           / "scratchcache.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    top = []
    for n in tree.body:
        if isinstance(n, ast.Import):
            top += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            top.append(n.module or "")
    banned = {"phase4seg.common", "rasterio", "geopandas", "numpy", "pandas", "torch"}
    assert not (set(top) & banned), top


def test_json_sidecars_survive_a_torn_read(env):
    """A peer reads `.cache/<key>.json` from another process. Publishing it temp +
    os.replace is what stops a half-written object being parsed — the same pattern
    queue_ledger.py::publish_phase_marker uses for its marker."""
    e = env.entry("a.tif")
    side = scratchcache._sidecar_path(e.key, env.root)
    side.write_text("{not json", encoding="utf-8")

    assert scratchcache._read_sidecar(e.key, env.root) is None
    assert scratchcache.stage(e.src, root=env.root) == e.payload
    assert json.loads(side.read_text(encoding="utf-8"))["state"] == "ready"
