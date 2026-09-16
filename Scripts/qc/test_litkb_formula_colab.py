r"""The two fixes the L4 canary asked for: the VM watchdog can see the litkb worker, and one
runtime decodes with N processes instead of one.

NOTHING HERE NEEDS A GPU, A DATABASE OR THE LAKE. The watchdog tests `exec` the watchdog's own
source lines — the ones `gen_vm_bootstrap.py` emits — up to its `while True:`, and call the
decision function directly. The parallel-decode tests drive the planner and the merge with
synthetic rows; the only thing they cannot test off-GPU is the decode itself, which is why the
dry run in Reports/LITKB_COLAB_L4_FORMULA_2026-09-15.md §"Canary 2 prepared" exists.

Every kill in here is mutation-tested by qc/instruments/litkb_formula_mutations.py
(CLAUDE.md §3.4c: a gate that has never fired is not known to work). One mutation — the
watchdog's stale-beat branch — is also fired INSIDE this file, by exec'ing the watchdog head
with that one line weakened, because that gate protects a billing runtime and the evidence
that it fires should not depend on remembering to run a separate campaign.
"""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
GEN = SCRIPTS / "pipeline" / "gen_vm_bootstrap.py"
WORKER = SCRIPTS / "pipeline" / "litkb" / "extract" / "colab_formula_worker.py"
VM_START = SCRIPTS / "pipeline" / "litkb_formula_vm_start.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    return _load(GEN, "gen_vm_bootstrap_under_test")


@pytest.fixture(scope="module")
def worker():
    """The worker module by path. It imports docling/torch/PIL only inside functions, so the
    module itself loads anywhere — which is the point: the planner and the merge are testable
    on a laptop with no GPU."""
    return _load(WORKER, "colab_formula_worker_under_test")


# ── the watchdog, as source ─────────────────────────────────────────────────────────────

def _emitted_bootstrap():
    """The bootstrap text with a placeholder for each substitution — no secret needed."""
    body = None
    for node in ast.walk(ast.parse(GEN.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "body" for t in node.targets):
            body = node.value
    assert body is not None and isinstance(body, ast.JoinedStr)
    return "".join(v.value if isinstance(v, ast.Constant) else "'_SUBST_'"
                   for v in body.values)


def test_the_emitted_bootstrap_can_actually_BUILD_the_watchdog():
    """PARSING THE EMITTED SCRIPT IS NOT RUNNING IT, and that gap hid a launch-killing bug.

    `_WD` is a list built on the VM. A name used inside it — `repr(WORK_MARKERS)` — must be
    substituted into the emitted script's namespace by the body header, exactly as `MOUNT` is.
    Add the constant to this module and forget the header line and the bootstrap dies with a
    NameError at its line 15: before SELFSTOP_ARMED, before the mount, before anything. That
    is the D14 failure mode — a live billing VM with no watchdog and no beacon — and every
    other gate here is blind to it, because `ast.parse` accepts a NameError happily and the
    static flattener rewrites the offending call to a string literal before anyone looks.

    So this one EXECUTES the emitted script's prefix: imports, constants, and the `_WD` list
    literal, stopping before the first line that touches the filesystem.
    """
    emitted = _emitted_bootstrap()
    cut = emitted.index('open("/content/vm_selfstop.py"')
    prefix = emitted[:cut]
    assert "_WD = [" in prefix and "subprocess" in prefix
    ns = {}
    exec(compile(prefix, "<emitted bootstrap>", "exec"), ns)   # noqa: S102 — the code under test
    assert isinstance(ns.get("_WD"), list) and ns["_WD"], "_WD did not build on the VM side"
    assert all(isinstance(x, str) for x in ns["_WD"])
    # Every name `_WD` reads must be bound in that namespace. The flattener replaces each
    # substitution with a placeholder, so the VALUES here are '_SUBST_' — what is being
    # checked is that the header binds the names at all, which is the half that was missing.
    for name in ("MOUNT", "WORK_MARKERS", "BEAT_MARKER_PREFIX", "WORKER_BEAT"):
        assert name in ns, f"the body header never substitutes {name} into the emitted script"
    # the real values are checked against the generator's own constants elsewhere
    # (test_the_litkb_worker_is_in_the_work_registry, test_the_registry_reaches_the_emitted_watchdog)


def _watchdog_lines():
    """The self-stop watchdog's own source lines, read out of the generator's `_WD` literal.

    Same two-layer read qc/test_ci_gates.py does: the generator holds an f-string that is the
    bootstrap, and the bootstrap holds a list of strings that is the watchdog. A runtime
    fragment (`"MARKERS = " + repr(WORK_MARKERS)`) keeps its literal half and gets a quoted
    placeholder for the rest, so the reassembled source still parses.
    """
    body = None
    for node in ast.walk(ast.parse(GEN.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "body" for t in node.targets):
            body = node.value
    assert body is not None and isinstance(body, ast.JoinedStr)
    emitted = "".join(v.value if isinstance(v, ast.Constant) else "'_SUBST_'"
                      for v in body.values)
    wd = None
    for node in ast.walk(ast.parse(emitted)):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "_WD" for t in node.targets):
            wd = node.value
    assert wd is not None and isinstance(wd, ast.List)

    def flat(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            return n.value
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            return flat(n.left) + flat(n.right)
        return "'_SUBST_'"
    return [flat(e) for e in wd.elts]


def _watchdog_head(mutate=None):
    """`_tick` and its helpers, exec'd. Everything above the `while True:` loop is function
    definitions and constants — no file is opened, no environment is read — so it is safe to
    exec on a laptop. `mutate` is (old, new) applied to the head first."""
    src = "\n".join(_watchdog_lines())
    head = src.split("while True:")[0]
    assert "def _tick(" in head, "the watchdog's decision is no longer a function above the loop"
    if mutate:
        old, new = mutate
        assert old in head, "the mutation target is gone from the watchdog"
        head = head.replace(old, new)
    ns = {}
    exec(compile(head, "<watchdog>", "exec"), ns)      # noqa: S102 — the code under test
    return ns


# ── FIX 1: the watchdog can see the litkb worker ────────────────────────────────────────

def test_the_litkb_worker_is_in_the_work_registry(gen):
    """The defect itself: the watchdog scanned for three phase4 names, so a litkb runtime
    never armed its idle timer (canary report §6)."""
    assert "litkb.extract.colab_formula_worker" in gen.WORK_MARKERS
    # and the three that were always there are still there
    for m in ("phase4_train_queue.py", "phase4_semantic_finetune.py", "phase4_qc_indep.py"):
        assert m in gen.WORK_MARKERS


def test_the_marker_is_the_text_that_will_actually_be_in_the_cmdline(gen):
    """A registry entry is a substring test against /proc/<pid>/cmdline. If the launch payload
    changes how it starts the worker, the marker silently stops matching and the watchdog is
    blind again — with nothing failing. So the marker is checked against the payload."""
    payload = VM_START.read_text(encoding="utf-8")
    litkb = [m for m in gen.WORK_MARKERS if m.startswith(gen.BEAT_MARKER_PREFIX)]
    assert litkb, "no litkb marker in the registry"
    for m in litkb:
        assert m in payload, f"{m} does not appear in the command litkb_formula_vm_start.py runs"


def test_the_registry_reaches_the_emitted_watchdog(gen):
    """The constant and the emitted literal must not drift: the watchdog is built from
    `repr(WORK_MARKERS)`, never from a second copy of the names."""
    src = "\n".join(_watchdog_lines())
    assert "MARKERS = " in src and "for _m in MARKERS:" in src
    assert '"MARKERS = " + repr(WORK_MARKERS)' in GEN.read_text(encoding="utf-8"), \
        "the watchdog no longer builds its scan list from WORK_MARKERS"
    assert '"BEAT = " + repr(WORKER_BEAT)' in GEN.read_text(encoding="utf-8")


def test_a_live_worker_with_fresh_beats_is_never_killed():
    tick = _watchdog_head()["_tick"]
    seen, idle = False, None
    now = 10_000.0
    for _ in range(200):                  # 200 minutes of healthy decoding
        act, seen, idle = tick(now, "4242", 30.0, seen, idle, 0.0, True)
        assert act == "run", act
        now += 60
    assert seen is True, "a live litkb worker never armed the idle timer"


def test_a_hung_litkb_worker_is_stopped():
    """ALIVE BUT NOT WORKING. The process is still in /proc — process presence alone says
    nothing — and its beat is 11 minutes old."""
    tick = _watchdog_head()["_tick"]
    act, seen, idle = tick(10_000.0, "4242", 30.0, False, None, 0.0, True)
    assert act == "run"
    act, seen, idle = tick(10_700.0, "4242", 660.0, seen, idle, 0.0, True)
    assert act == "stop:idle", act
    assert idle == pytest.approx(10_700.0 - 660.0), \
        "the idle clock did not start at the last beat"


def test_the_stale_beat_gate_fires_when_it_is_removed():
    """CLAUDE.md §3.4c, in-file: weaken the one branch and show the hung worker survives.

    Without this, 'the watchdog stops a hung worker' rests on a test that would also pass if
    the branch did nothing, because a real hang is not reproducible off a VM."""
    tick = _watchdog_head(mutate=(
        "if busy and beat_age is not None and beat_age > idle:",
        "if False and beat_age is not None and beat_age > idle:"))["_tick"]
    act, seen, idle = tick(10_000.0, "4242", 30.0, False, None, 0.0, True)
    act, _seen, _idle = tick(10_700.0, "4242", 660.0, seen, idle, 0.0, True)
    assert act == "run", ("the mutant still stopped the hung worker — this test is not "
                          "measuring the stale-beat branch")


def test_no_beat_file_means_alive_not_hung():
    """`_beat_age` returns None when there is no beat — a worker build that does not beat, or
    one whose first beat has not landed. None is 'no evidence', and the watchdog must then
    fall back to process presence, never stop a running process on a missing file."""
    tick = _watchdog_head()["_tick"]
    act, seen, idle = tick(10_000.0, "4242", None, True, 9_000.0, 0.0, True)
    assert act == "run" and idle is None


def test_phase4_semantics_are_unchanged():
    """A phase4 queue carries no beat, so `beat_age` is None for it and the path it takes is
    byte-for-byte the one it took before: seen while present, 10 idle minutes after it goes."""
    tick = _watchdog_head()["_tick"]
    act, seen, idle = tick(10_000.0, "77", None, False, None, 0.0, True)
    assert (act, seen) == ("run", True)
    act, seen, idle = tick(10_100.0, "", None, seen, None, 0.0, True)
    assert act == "run" and idle == 10_100.0
    act, seen, idle = tick(10_500.0, "", None, seen, idle, 0.0, True)
    assert act == "run", "stopped before 10 idle minutes"
    act, seen, idle = tick(10_800.0, "", None, seen, idle, 0.0, True)
    assert act == "stop:idle"


def test_the_two_bootstrap_backstops_survive():
    tick = _watchdog_head()["_tick"]
    assert tick(1_300.0, "", None, False, None, 0.0, False)[0] == "stop:bootstrap"
    assert tick(1_300.0, "", None, False, None, 0.0, True)[0] == "run"
    assert tick(7_300.0, "", None, False, None, 0.0, True)[0] == "stop:noqueue"


def test_the_worker_beats_before_it_loads_the_model(worker):
    """A second exec on the same runtime inherits the first exec's beat file. If the worker
    only beat after its first batch, the watchdog would read a beat from the previous run,
    call it stale and stop a healthy VM during the 20 s model load."""
    src = WORKER.read_text(encoding="utf-8")
    fn = src[src.index("def main("):]
    assert "beat()" in fn, "main() never beats"
    assert fn.index("beat()") < fn.index("build_model("), \
        "main() loads the model before it beats — a stale beat from an earlier exec survives"


def test_beat_writes_where_the_watchdog_looks(worker, tmp_path, monkeypatch):
    p = tmp_path / "litkb_worker_beat"
    monkeypatch.setenv("LITKB_WORKER_BEAT", str(p))
    assert worker.beat() == str(p)
    assert p.exists()
    # off a VM the default path does not exist, and the beat must no-op rather than raise
    monkeypatch.setenv("LITKB_WORKER_BEAT", "/no/such/dir/beat")
    assert worker.beat() is None


def test_the_beat_path_is_one_fact(gen, worker):
    assert gen.WORKER_BEAT == worker.WORKER_BEAT, \
        "the watchdog and the worker disagree about where the beat file lives"


# ── FIX 2: N decode processes on one runtime ────────────────────────────────────────────

class _Img:
    """A stand-in crop: `crop_cost` reads only size and the L-histogram."""

    def __init__(self, w, h, ink):
        self.size = (w, h)
        self._ink = ink
        self._n = w * h

    def convert(self, _mode):
        return self

    def histogram(self):
        h = [0] * 256
        h[0] = self._ink                   # black
        h[255] = self._n - self._ink       # page
        return h


def _fake(n, seed=7):
    """n crops with spread-out costs, and their images."""
    crops, images = [], {}
    for i in range(n):
        cid = "%064x" % (seed * 1_000 + i)
        crops.append({"crop_id": cid, "file": "f%d.pdf" % (i % 3), "page": i,
                      "self_ref": "#/texts/%d" % i})
        images[cid] = _Img(100 + 37 * ((i * 13) % 11), 60, 300 + 90 * ((i * 7) % 9))
    return crops, images


def test_crop_cost_is_predicted_seconds_from_ink(worker):
    """Superseded 2026-09-15. The proxy used to be `width x ink density` and returned an
    arbitrary unit; it now returns PREDICTED SECONDS from the ink pixel count, because that
    is the unit assign_batches has to balance in. The ranking contract is the test below,
    `test_the_cost_proxy_ranks_by_ink_not_by_ink_over_height`."""
    ink = 5_000
    assert worker.crop_cost(_Img(200, 100, ink)) == pytest.approx(
        worker.predicted_seconds(ink))
    assert worker.crop_cost(_Img(0, 0, 0)) == pytest.approx(worker.BATCH_SECONDS_INTERCEPT)


def test_the_batch_plan_does_not_depend_on_n(worker):
    """The claim the whole design rests on: N changes who decodes a batch, never what is in
    it. If it did, a token could move between N=1 and N=4 and the dry run would be the only
    thing standing between that and the corpus."""
    crops, images = _fake(23)
    plan = worker.plan_batches(crops, images, 5)
    assert [c["crop_id"] for b in plan for c in b] == \
           [c["crop_id"] for b in worker.plan_batches(list(reversed(crops)), images, 5)
            for c in b], "the plan depends on the order the crops arrived in"
    assert sum(len(b) for b in plan) == 23
    assert {c["crop_id"] for b in plan for c in b} == {c["crop_id"] for c in crops}
    costs = [worker.crop_cost(images[c["crop_id"]]) for b in plan for c in b]
    assert costs == sorted(costs, reverse=True), "crops are not ordered most expensive first"


def test_assignment_is_deterministic_and_balances(worker):
    costs = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0]
    for mode in ("lpt", "deal"):
        who = worker.assign_batches(costs, 3, mode=mode)
        assert who == worker.assign_batches(costs, 3, mode=mode), mode
        assert sorted(set(who)) == [0, 1, 2], "a slice got no work at all"
        # every batch is assigned exactly once, to exactly one slice
        assert len(who) == len(costs)
        # each slice gets the same NUMBER of batches under either mode on this input
        assert [who.count(k) for k in range(3)] == [2, 2, 2], (mode, who)
    # LPT equalises the declared LOAD; dealing deliberately does not, because it does not
    # believe the numbers (see assign_batches' docstring).
    lpt = worker.assign_batches(costs, 3, mode="lpt")
    load = [sum(c for c, w in zip(costs, lpt) if w == k) for k in range(3)]
    assert max(load) - min(load) <= 1.0, load


def test_the_default_assignment_DEALS_rather_than_trusting_the_costs(worker):
    """The proxy earns its ORDER believed, not its NUMBERS. LPT trusts the numbers, so one
    badly under-estimated batch loads a slice it thinks is light and that slice runs long
    after the others have finished; dealing cost-ordered batches round-robin cannot
    concentrate the mistakes. Measured on canary 2's timings: 3.71x under LPT against 1.63x
    dealt, the latter exactly the spread a perfect oracle reaches
    (qc/instruments/litkb_formula_balance.py)."""
    assert worker.ASSIGN_MODE == "deal"
    # one batch wildly under-costed — a repetition loop no pixel proxy could have seen
    costs = [9.0, 8.0, 7.0, 0.1, 6.0, 5.0, 4.0, 3.0]
    assert worker.assign_batches(costs, 3) == [0, 1, 2, 0, 1, 2, 0, 1]
    lpt = worker.assign_batches(costs, 3, mode="lpt")
    assert lpt != worker.assign_batches(costs, 3), "deal and lpt agree — one of them is inert"
    # the cheat batch is 4th-heaviest by rank but nearly free; under LPT it rides with the
    # heaviest, under deal it lands on the slice that took the heaviest and nothing since.
    assert worker.assign_batches(costs, 3)[3] == 0


def test_plan_procs_states_which_term_bound_it(worker):
    l4 = 23_660_000_000
    n, terms = worker.plan_procs(l4, cpu_count=12, n_batches=40)
    assert n == int(0.80 * l4 // terms["per_proc_bytes"])
    assert terms["bound_by"] == ["vram"]
    assert terms["limits"]["cpu"] == 11
    # the cpu term can bind instead, and says so
    n2, t2 = worker.plan_procs(l4, cpu_count=3, n_batches=40)
    assert (n2, t2["bound_by"]) == (2, ["cpu"])
    # never more slices than batches, and never zero
    assert worker.plan_procs(l4, cpu_count=12, n_batches=2)[0] == 2
    assert worker.plan_procs(None, cpu_count=None, n_batches=None)[0] == 1
    # the operator's ceiling wins when it is the smallest
    assert worker.plan_procs(l4, cpu_count=12, n_batches=40, cap=2)[0] == 2


def test_the_per_process_footprint_is_the_larger_measured_one(worker):
    """Not invented: both numbers are read off the canary's worker.json (report §3). The
    device-wide figure is larger because it carries the CUDA context, and that is the
    quantity that has to fit N times."""
    assert worker.MEASURED_DEVICE_FOOTPRINT_BYTES > worker.MEASURED_PEAK_RESERVED_BYTES
    _n, terms = worker.plan_procs(23_660_000_000, cpu_count=12, n_batches=40)
    assert terms["per_proc_bytes"] == worker.MEASURED_DEVICE_FOOTPRINT_BYTES


def _rows_for(plan, who, slices, latex="x^2"):
    out = {}
    for bi, chunk in enumerate(plan):
        s = who[bi]
        if s not in slices:
            continue
        for c in chunk:
            out.setdefault(s, []).append({
                "crop_id": c["crop_id"], "file": c["file"], "page": c["page"],
                "self_ref": c["self_ref"], "status": "ok", "latex": latex, "error": None,
                "batch_index": bi, "batch_size": len(chunk),
                "batch_seconds": 1.0, "seconds_per_crop_in_batch": 0.2})
    return out


def test_a_dead_slice_fails_only_its_own_crops(worker):
    crops, images = _fake(20)
    plan = worker.plan_batches(crops, images, 5)
    who = worker.assign_batches(worker.batch_costs(plan, images), 2)
    rows, ok, failed, _u, _d = worker.merge_slices(
        plan, who, _rows_for(plan, who, {0}) | {1: []},
        {1: "child exit 1: CUDA error"})
    assert len(rows) == 20, "the merge lost crops — it is driven by the returns, not the plan"
    dead = [r for r in rows if r["status"] == "failed"]
    assert failed == len(dead) > 0 and ok == 20 - failed
    assert all(r["latex"] is None for r in dead)
    assert all("slice 1" in r["error"] and "CUDA error" in r["error"] for r in dead)
    # and the surviving slice is untouched
    assert all(r["latex"] == "x^2" for r in rows if r["status"] == "ok")


def test_a_child_row_claiming_ok_with_no_latex_is_failed(worker):
    """Kill 3 once more at the merge: docling returns empty strings on an engine error, so an
    empty decode is never a success — not even when a child says it is."""
    crops, images = _fake(10)
    plan = worker.plan_batches(crops, images, 5)
    who = worker.assign_batches(worker.batch_costs(plan, images), 1)
    slices = _rows_for(plan, who, {0})
    slices[0][0]["latex"] = ""
    slices[0][1]["latex"] = "   "
    rows, ok, failed, _u, _d = worker.merge_slices(plan, who, slices)
    assert (ok, failed) == (8, 2)
    bad = [r for r in rows if r["status"] == "failed"]
    assert all(r["latex"] is None and "coerced to failed" in r["error"] for r in bad)


def test_the_merge_emits_one_row_per_crop_in_global_batch_order(worker):
    crops, images = _fake(17)
    plan = worker.plan_batches(crops, images, 5)
    who = worker.assign_batches(worker.batch_costs(plan, images), 3)
    rows, _ok, _failed, _u, _d = worker.merge_slices(plan, who,
                                                     _rows_for(plan, who, {0, 1, 2}))
    assert [r["crop_id"] for r in rows] == [c["crop_id"] for b in plan for c in b]
    assert [r["batch_index"] for r in rows] == \
           [bi for bi, b in enumerate(plan) for _ in b]


def test_a_child_that_floods_its_output_neither_deadlocks_nor_loses_its_exit_code(worker,
                                                                                  tmp_path):
    """The seam that broke on the first real parallel run, in both of its ways.

    (1) `Popen(stdout=<file object>)` leaves `p.stdout` as None, so closing it on the Popen
    raises and takes the whole shard down — the parent reported the shard `failed` and the
    other slice was orphaned mid-decode. (2) With a PIPE instead of a file, a child printing
    more than the 64 KB pipe buffer blocks forever while the parent waits on a different
    child; the model load alone prints a per-process progress bar. 200 KB of child output and
    a non-zero exit cover both.
    """
    log = tmp_path / "slice.log"
    p, fh = worker.spawn_child(
        [sys.executable, "-c", "print('x' * 200_000); raise SystemExit(3)"], str(log))
    rc, tail = worker.wait_child(p, fh, str(log))
    assert rc == 3, "the child's exit code did not survive"
    assert tail.strip().endswith("x"), tail[:80]
    assert log.stat().st_size > 200_000
    assert fh.closed, "the log handle was left open — the parent leaks one per slice"


def test_the_queue_file_owns_its_destination_and_its_process_count(worker, tmp_path):
    """`out_dir` was declared in every queue file and read by nothing, so two queues wrote
    into one directory and the idempotent skip turned the second run into a no-op."""
    q = tmp_path / "q.yaml"
    q.write_text("out_dir: /x/y\nprocs: auto\nshards:\n  - shard: /a/b.zip\n",
                 encoding="utf-8")
    assert worker.load_queue(str(q)) == (["/a/b.zip"], "/x/y", "auto")
    assert worker.load_queue(None) == ([], None, None)


def test_no_queue_writes_into_another_queues_results():
    """THE DEFECT THIS GUARDS is discovered only on the VM, and it is silent: the worker skips
    a shard whose result archive is already present (kill 4), so a queue pointed at an earlier
    queue's out_dir returns NOTHING and reports success. Canary 2 would have skipped both of
    its shards; the full pass shares canary 1's `shard_canary200` crops by construction, so it
    would have skipped those too. One out_dir per queue, asserted rather than remembered.

    It also holds the OTHER half — which queue the launch payload actually runs. The payload
    is the only place that names it, and pointing it at a queue whose results already exist is
    how a launch burns a runtime and returns an empty log.
    """
    import re
    qs = {}
    for name in ("queue_litkb_formula_l4.yaml", "queue_litkb_formula_l4_canary2.yaml",
                 "queue_litkb_formula_l4_full.yaml"):
        qs[name] = (SCRIPTS / "pipeline" / name).read_text(encoding="utf-8")
    outs = {n: re.search(r"^out_dir:\s*(\S+)", t, re.M).group(1) for n, t in qs.items()}
    assert len(set(outs.values())) == len(outs), \
        f"two queues share an out_dir and the second would skip every shard: {outs}"
    full = qs["queue_litkb_formula_l4_full.yaml"]
    assert re.search(r"^procs:\s*auto", full, re.M), "the full pass does not ask for N processes"
    shards = re.findall(r"shard_full(\d\d)\.zip", full)
    assert shards == [f"{i:02d}" for i in range(36)], \
        f"the full pass does not list the 36 census shards in order: {shards}"
    assert "queue_litkb_formula_l4_full.yaml" in VM_START.read_text(encoding="utf-8"), \
        "the launch payload does not point at the full-corpus queue"


def test_every_mutation_row_still_has_a_target():
    """The mutation campaign is only evidence while its targets exist. A refactor that moves a
    guarded line makes the row a no-op that reports TARGET GONE — and nobody reruns a campaign
    to find that out, so the ordinary suite checks it."""
    harness = _load(SCRIPTS / "qc" / "instruments" / "litkb_formula_mutations.py",
                    "litkb_formula_mutations_under_test")
    assert len(harness.MUTATIONS) >= 11
    # The campaign now spans TWO test files — the ingest's routing kill (G4) lives with the
    # other ingest refusals, not here — so the search is over exactly the files the harness
    # hands pytest. Reading that list OFF the harness rather than retyping it is the point:
    # a campaign that runs one file while this test checks another is a silent no-op.
    suites = "\n".join((SCRIPTS / f).read_text(encoding="utf-8")
                       for f in (harness.TEST, harness.TEST_SHARDS))
    for m in harness.MUTATIONS:
        text = (SCRIPTS / m["file"]).read_text(encoding="utf-8")
        assert text.count(m["old"]) == 1, \
            f"{m['id']}: its target is missing or no longer unique in {m['file']}"
        assert m["test"] in suites, \
            f"{m['id']} names a test that exists in neither suite the campaign runs"


def test_the_timing_fields_are_named_once(worker):
    """The N=1 vs N>1 comparison drops exactly these two, and the report quotes this tuple."""
    assert worker.TIMING_FIELDS == ("batch_seconds", "seconds_per_crop_in_batch")
    crops, images = _fake(5)
    plan = worker.plan_batches(crops, images, 5)
    rows, _ok, _f, _u, _d = worker.merge_slices(plan, [0], _rows_for(plan, [0], {0}))
    for f in worker.TIMING_FIELDS:
        assert f in rows[0]


# ── the two decode guards (2026-09-15, canary 2's Determinism section) ───────────────────
# The canary re-decoded 200 crops it had already decoded and 14 came back different, six of
# them by thousands of characters because one side had run to max_new_tokens inside a
# repetition loop. These tests hold the two guards that answer that, and each is
# mutation-tested in qc/instruments/litkb_formula_mutations.py (G1..G5).

import hashlib as _hashlib    # noqa: E402
import io as _io              # noqa: E402
import json as _json          # noqa: E402
import zipfile as _zipfile    # noqa: E402


def _shard_zip(tmp_path, n=20, shard_id="s1"):
    """A real shard archive: PNG crops whose bytes hash to their crop_id.

    Sizes are distinct per crop, which is what lets a stub decoder identify which image it
    was handed without the worker having to tell it.
    """
    from PIL import Image
    crops, blobs = [], []
    z = tmp_path / "shard.zip"
    with _zipfile.ZipFile(z, "w") as zf:
        for i in range(n):
            buf = _io.BytesIO()
            Image.new("RGB", (40 + i, 20 + i), (255 - i, 255, 255)).save(buf, "PNG")
            b = buf.getvalue()
            cid = _hashlib.sha256(b).hexdigest()
            blobs.append((cid, b))
            crops.append({"crop_id": cid, "file": "f%d.pdf" % (i % 3), "page": i,
                          "self_ref": "#/texts/%d" % i, "_size": (40 + i, 20 + i)})
        for cid, b in blobs:
            zf.writestr("crops/%s.png" % cid, b)
        zf.writestr("manifest.json", _json.dumps(
            {"shard_id": shard_id,
             "crops": [{k: v for k, v in c.items() if k != "_size"} for c in crops]}))
    return z, crops


def _run(worker, monkeypatch, shard, out, decoder, verify=True):
    monkeypatch.setattr(worker, "decode_batch", decoder)
    monkeypatch.setattr(worker, "_tokenizer_of", lambda m: None)
    rec = worker.process_shard(str(shard), str(out), device="cpu", _model=(object(), 5),
                               load_seconds=1.0, verify=verify)
    with _zipfile.ZipFile(out) as zf:
        rows = [_json.loads(ln) for ln in
                zf.read("results.jsonl").decode().splitlines() if ln]
    return rec, rows


def test_a_planted_flip_is_recorded_unstable_with_BOTH_strings(worker, monkeypatch,
                                                               tmp_path):
    """THE KILL. One crop decodes differently on the re-decode. With the guard it is
    `unstable` and both candidates survive; the mutation campaign (G1) shows that with the
    guard removed the very same flip is recorded `ok` and one string is silently dropped."""
    shard, crops = _shard_zip(tmp_path)
    # the victim must be a crop the guard actually re-checks, or the test is measuring the
    # sample rather than the guard: take it FROM the sample the worker itself will compute.
    # the salt is the shard's OWN sha256 — the same thing process_shard passes, computed the
    # same way, so the test cannot drift from the worker's choice of sample.
    sampled = worker.stability_sample([{k: v for k, v in c.items() if k != "_size"}
                                       for c in crops], worker.sha256_file(str(shard)))
    victim = [c for c in crops if c["crop_id"] in sampled][0]
    vsize = victim["_size"]

    def decoder(_model, images):
        # a single-image call is the RE-decode (the guard decodes alone, on purpose); flip
        # the victim's answer only there, which is exactly what a real flip looks like.
        return ["FLIPPED" if (len(images) == 1 and im.size == vsize) else "x ^ 2"
                for im in images]

    rec, rows = _run(worker, monkeypatch, shard, tmp_path / "out.zip", decoder)
    hit = [r for r in rows if r["crop_id"] == victim["crop_id"]][0]
    assert hit["stability"] == "unstable", "the re-decode disagreed and nothing said so"
    assert hit["status"] == "unstable", "an unstable row must NOT be ok"
    assert hit["latex"] == "x ^ 2" and hit["latex_redecode"] == "FLIPPED", \
        "both strings must survive — picking one invents a decision"
    assert rec["unstable"] >= 1 and rec["status"] == "partial"
    assert victim["crop_id"] not in {r["crop_id"] for r in rows if r["status"] == "ok"}


def test_without_the_guard_the_same_flip_is_recorded_ok(worker, monkeypatch, tmp_path):
    """The other half of the kill: --no-verify reproduces the pre-fix behaviour, and a row
    that was never checked is an ordinary `ok` with no trace that it was ever in doubt."""
    shard, crops = _shard_zip(tmp_path)
    rec, rows = _run(worker, monkeypatch, shard, tmp_path / "o.zip",
                     lambda _m, ims: ["x ^ 2"] * len(ims), verify=False)
    assert rec["ok"] == len(crops) and rec["unstable"] == 0
    assert all(r["stability"] == "unchecked" for r in rows)
    assert rec["n_rechecked"] == 0


def test_every_long_row_is_rechecked_not_just_the_sample(worker, monkeypatch, tmp_path):
    """Length is the whole signal: 22% of rows over 1,000 characters differed against 2% of
    those under 200. A 5% random sample alone would have missed most of them."""
    shard, crops = _shard_zip(tmp_path, n=40)
    # NOT a repeated string: "y " * n ends in a repeated tail and the degeneracy guard would
    # claim it first, which would make this test measure the wrong guard.
    long_tex = " ".join("x_{%d} + y^{%d}" % (i, i * 7 % 13)
                        for i in range(worker.REDECODE_LONG_CHARS))
    assert len(long_tex) >= worker.REDECODE_LONG_CHARS
    assert not worker.degeneracy_of(long_tex)[0]
    rec, rows = _run(worker, monkeypatch, shard, tmp_path / "o.zip",
                     lambda _m, ims: [long_tex] * len(ims))
    assert rec["n_rechecked"] == len(crops), "a long row escaped the re-decode"
    assert all(r["stability"] == "stable" for r in rows)


def test_the_stability_sample_is_deterministic_and_N_independent(worker):
    """The same invariant plan_batches rests on: seeded from the SHARD, never from `random`,
    so every slice of a shard agrees about which crops were checked."""
    crops = [{"crop_id": "%064x" % i} for i in range(200)]
    a = worker.stability_sample(crops, "shard-A")
    assert a == worker.stability_sample(list(reversed(crops)), "shard-A")
    assert a != worker.stability_sample(crops, "shard-B"), "the salt does nothing"
    assert len(a) == 10 == int(round(200 * worker.REDECODE_FRACTION))
    assert worker.stability_sample(crops, "s", fraction=0.0) == set()


def test_a_repetition_loop_is_degenerate_even_when_it_is_perfectly_stable(worker,
                                                                          monkeypatch,
                                                                          tmp_path):
    """THE SECOND KILL, and the one a stability check cannot reach. Nine of canary 1's capped
    rows were capped IDENTICALLY in canary 2 — two runs agreeing on the same garbage. The
    string here is the real shape one of those rows ended in."""
    loop = "\\underset { n } {" * 300
    assert worker.repeated_tail(loop), "the tail detector missed a 300x repeat"
    deg, why = worker.degeneracy_of(loop)
    assert deg and "repetition loop" in why
    # the token-cap arm, independent of the text
    deg2, why2 = worker.degeneracy_of("an ordinary looking formula", n_tokens=2036)
    assert deg2 and "max_new_tokens" in why2
    # an ordinary formula is neither
    assert worker.degeneracy_of("a _ { 2 2 } = k ^ { 1 / 2 } \\sigma _ { 2 }") == (False, None)
    assert worker.repeated_tail("x + y + z") is None

    shard, crops = _shard_zip(tmp_path, n=10)
    rec, rows = _run(worker, monkeypatch, shard, tmp_path / "o.zip",
                     lambda _m, ims: [loop] * len(ims))
    assert rec["degenerate"] == len(crops) and rec["ok"] == 0
    assert all(r["status"] == "degenerate" and r["degenerate_reason"] for r in rows)
    # STABLE AND WRONG: the re-decode agreed, and that is exactly the point
    assert all(r["stability"] in ("stable", "unchecked") for r in rows)


def test_the_merge_passes_unstable_and_degenerate_through_untouched(worker):
    """The merge catches a slice that lied or vanished; it does not re-litigate a verdict a
    child reached with the model in hand. Coercing these would erase the queue's contents."""
    crops, images = _fake(10)
    plan = worker.plan_batches(crops, images, 5)
    who = worker.assign_batches(worker.batch_costs(plan, images), 1)
    slices = _rows_for(plan, who, {0})
    slices[0][0].update(status="unstable", latex="A", latex_redecode="B",
                        stability="unstable")
    slices[0][1].update(status="degenerate", latex="L" * 50,
                        degenerate_reason="repetition loop")
    rows, ok, failed, unstable, degenerate = worker.merge_slices(plan, who, slices)
    assert (ok, failed, unstable, degenerate) == (8, 0, 1, 1)
    u = [r for r in rows if r["status"] == "unstable"][0]
    assert u["latex"] == "A" and u["latex_redecode"] == "B", \
        "the merge dropped a candidate string"
    assert [r for r in rows if r["status"] == "degenerate"][0]["degenerate_reason"]


def test_the_child_slice_path_passes_the_load_it_measured(worker):
    """model_load_seconds read 0.0 for all six of canary 2's slices: the child built the
    model itself and handed it over as `_model=` without the matching `load_seconds=`, so
    process_shard timed a load that had already happened. One keyword."""
    src = WORKER.read_text(encoding="utf-8")
    head = src.split("if a.slice_of:", 1)[1].split("return 0", 1)[0]
    assert "t_load = time.time()" in head and "load_seconds=load_s" in head, \
        "the child path builds the model without timing it — model_load_seconds will be 0.0"
    assert head.index("t_load = time.time()") < head.index("build_model")


# ── the cost proxy (canary 2 §4.2: the proxy, not --procs, is what failed) ───────────────

def test_the_cost_proxy_ranks_by_ink_not_by_ink_over_height(worker):
    """The old proxy was `width x ink density`, which cancels to `ink / height` — blind to
    height, and height is what separates a multi-line array (the long emitters) from an
    inline fragment. Measured against canary 1's decoded lengths over the same 200 crops,
    ink pixel count ranks at Spearman +0.873 and the old form at +0.389."""
    tall = _Img(100, 400, 20_000)     # same ink, four times the height
    wide = _Img(400, 100, 20_000)
    assert worker.crop_cost(tall) == pytest.approx(worker.crop_cost(wide)), \
        "the proxy still depends on the aspect ratio rather than on the ink"
    assert worker.crop_cost(_Img(200, 100, 20_000)) > worker.crop_cost(_Img(200, 100, 500))
    assert worker.crop_cost(_Img(0, 0, 0)) == pytest.approx(worker.BATCH_SECONDS_INTERCEPT)
    # and it saturates: a generation cannot emit past the token cap
    assert worker.predicted_chars(10 ** 9) == worker.MAX_EMITTED_CHARS


def test_a_batch_costs_its_LONGEST_member_not_the_sum(worker):
    """A batched greedy decode steps every sequence together and stops when the longest one
    finishes, so four short crops riding with a long one cost nothing extra. Summing was the
    other half of the balance defect — it made five medium crops look dearer than one
    runaway, and LPT then separated them the wrong way round."""
    crops, images = _fake(10)
    plan = worker.plan_batches(crops, images, 5)
    costs = worker.batch_costs(plan, images)
    for b, c in zip(plan, costs):
        peak = max(worker.predicted_chars(worker.crop_ink(images[x["crop_id"]])[0])
                   for x in b)
        assert c == pytest.approx(worker.BATCH_SECONDS_INTERCEPT
                                  + worker.BATCH_SECONDS_PER_CHAR * peak)
        assert c < sum(worker.crop_cost(images[x["crop_id"]]) for x in b), \
            "the batch is being charged the sum of its members again"
