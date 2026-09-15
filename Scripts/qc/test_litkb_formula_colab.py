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


def test_crop_cost_is_width_times_ink_density(worker):
    assert worker.crop_cost(_Img(200, 100, 5_000)) == pytest.approx(200 * 0.25)
    assert worker.crop_cost(_Img(0, 0, 0)) == 0.0


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
    who = worker.assign_batches(costs, 3)
    assert who == worker.assign_batches(costs, 3)
    load = [sum(c for c, w in zip(costs, who) if w == k) for k in range(3)]
    assert max(load) - min(load) <= 1.0, load
    assert sorted(set(who)) == [0, 1, 2], "a slice got no work at all"
    # every batch is assigned exactly once, to exactly one slice
    assert len(who) == len(costs)


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
    rows, ok, failed = worker.merge_slices(
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
    rows, ok, failed = worker.merge_slices(plan, who, slices)
    assert (ok, failed) == (8, 2)
    bad = [r for r in rows if r["status"] == "failed"]
    assert all(r["latex"] is None and "coerced to failed" in r["error"] for r in bad)


def test_the_merge_emits_one_row_per_crop_in_global_batch_order(worker):
    crops, images = _fake(17)
    plan = worker.plan_batches(crops, images, 5)
    who = worker.assign_batches(worker.batch_costs(plan, images), 3)
    rows, _ok, _failed = worker.merge_slices(plan, who, _rows_for(plan, who, {0, 1, 2}))
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


def test_canary2_is_prepared_and_does_not_overwrite_canary1():
    """Canary 2 is PREPARED, not launched. What is checked here is the part that would be
    discovered on the VM: a queue pointed at canary 1's out_dir returns nothing, because both
    shards would be skipped as already present."""
    import re
    c1 = (SCRIPTS / "pipeline" / "queue_litkb_formula_l4.yaml").read_text(encoding="utf-8")
    c2 = (SCRIPTS / "pipeline" / "queue_litkb_formula_l4_canary2.yaml").read_text(
        encoding="utf-8")
    out1 = re.search(r"^out_dir:\s*(\S+)", c1, re.M).group(1)
    out2 = re.search(r"^out_dir:\s*(\S+)", c2, re.M).group(1)
    assert out1 != out2, "canary 2 would write into canary 1's results and skip every shard"
    assert re.search(r"^procs:\s*auto", c2, re.M), "canary 2 does not ask for N processes"
    for s in ("shard_canary200.zip", "shard_ref5.zip"):
        assert s in c2
    assert "queue_litkb_formula_l4_canary2.yaml" in \
        VM_START.read_text(encoding="utf-8"), "the launch payload still points at canary 1"


def test_every_mutation_row_still_has_a_target():
    """The mutation campaign is only evidence while its targets exist. A refactor that moves a
    guarded line makes the row a no-op that reports TARGET GONE — and nobody reruns a campaign
    to find that out, so the ordinary suite checks it."""
    harness = _load(SCRIPTS / "qc" / "instruments" / "litkb_formula_mutations.py",
                    "litkb_formula_mutations_under_test")
    assert len(harness.MUTATIONS) >= 5
    for m in harness.MUTATIONS:
        text = (SCRIPTS / m["file"]).read_text(encoding="utf-8")
        assert text.count(m["old"]) == 1, \
            f"{m['id']}: its target is missing or no longer unique in {m['file']}"
        assert m["test"] in Path(__file__).read_text(encoding="utf-8"), \
            f"{m['id']} names a test that does not exist here"


def test_the_timing_fields_are_named_once(worker):
    """The N=1 vs N>1 comparison drops exactly these two, and the report quotes this tuple."""
    assert worker.TIMING_FIELDS == ("batch_seconds", "seconds_per_crop_in_batch")
    crops, images = _fake(5)
    plan = worker.plan_batches(crops, images, 5)
    rows, _ok, _f = worker.merge_slices(plan, [0], _rows_for(plan, [0], {0}))
    for f in worker.TIMING_FIELDS:
        assert f in rows[0]
