r"""litkb formula / Colab L4 — show each kill FIRE (CLAUDE.md §3.4c: a gate that has never
fired on a known-bad input is not known to work).

For every row below: weaken ONE guard in the real source, run the test that should catch it,
record whether it FAILED, then restore the file byte-for-byte and verify the restore by
sha256. Before and after the campaign the unmutated tests are run and must pass, so a "fired"
result cannot be a broken baseline.

    LITKB_PGPORT=1 PYTHONUTF8=1 py -3.12 qc/instruments/litkb_formula_mutations.py [--only ID,…]

No database, no GPU, no lake: the whole set runs in seconds on the laptop, which is the point
— these guards protect a BILLING RUNTIME and a corpus-scale decode, and the evidence that they
fire must not cost a GPU hour to refresh. Exit 0 only if every chosen row fired and both
baselines passed.

WHY THESE FIVE. They are the failure modes the L4 canary either hit or walked past:

  W1  the watchdog's stale-beat branch — the canary's own §6 defect was a litkb worker the
      watchdog could not see at all; the fix is only worth anything if the branch fires.
  W2  the work registry — drop the litkb marker and the blindness comes straight back.
  W3  the worker's beat before the model load — a stale beat from an earlier exec on the same
      runtime (the canary ran TWO execs) would otherwise stop a healthy VM mid-load.
  M1  the merge's plan-driven stub — a slice that dies must fail its own crops, not vanish
      them from the shard.
  M2  the merge's empty-LaTeX coercion — kill 3, at the one place a child process can smuggle
      an empty decode in as a success.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
GEN = "pipeline/gen_vm_bootstrap.py"
WORKER = "pipeline/litkb/extract/colab_formula_worker.py"
TEST = "qc/test_litkb_formula_colab.py"

MUTATIONS = [
    dict(id="W1", file=GEN,
         what="the watchdog stops treating a stale liveness beat as a hang",
         kill="a hung litkb worker (alive, no beat for 11 min) is stopped",
         test="test_a_hung_litkb_worker_is_stopped",
         old='"    if busy and beat_age is not None and beat_age > idle:",',
         new='"    if busy and False and beat_age > idle:",'),
    dict(id="W2", file=GEN,
         what="the litkb worker is dropped from the work registry",
         kill="the litkb worker is in the registry the watchdog scans for",
         test="test_the_litkb_worker_is_in_the_work_registry",
         old='    "litkb.extract.colab_formula_worker",  # litkb formula decode (2026-09-15)\n',
         new=""),
    dict(id="W3", file=WORKER,
         what="the worker no longer beats before it loads the model",
         kill="a beat left by an earlier exec on the same runtime cannot read as stale",
         test="test_the_worker_beats_before_it_loads_the_model",
         old="    beat()   # BEFORE the 20 s model load",
         new="    pass     # BEFORE the 20 s model load"),
    dict(id="W4", file=GEN,
         what="the work registry stops being substituted into the emitted bootstrap",
         kill="the emitted bootstrap can actually BUILD its watchdog, not merely parse",
         test="test_the_emitted_bootstrap_can_actually_BUILD_the_watchdog",
         old="WORK_MARKERS = {WORK_MARKERS!r}\n",
         new=""),
    dict(id="M1", file=WORKER,
         what="a crop no slice returned a row for is reported ok instead of failed",
         kill="a dead slice fails only its own crops, and fails them",
         test="test_a_dead_slice_fails_only_its_own_crops",
         old='        "status": "failed", "latex": None, "error": error,',
         new='        "status": "ok", "latex": None, "error": error,'),
    dict(id="M2", file=WORKER,
         what="the merge stops coercing a child's ok-with-no-LaTeX row to failed",
         kill="kill 3 at the merge: an empty decode is never a success",
         test="test_a_child_row_claiming_ok_with_no_latex_is_failed",
         old='            elif got[1].get("status") == "ok" and not (got[1].get("latex") or "").strip():',
         new="            elif False:"),
]


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pytest(selector=None):
    cmd = [sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider"]
    if selector:
        cmd += ["-k", selector]
    r = subprocess.run(cmd, cwd=SCRIPTS, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run(only=None):
    rows = [m for m in MUTATIONS if not only or m["id"] in only]
    unknown = sorted(set(only or []) - {m["id"] for m in MUTATIONS})
    if unknown:
        sys.exit("unknown mutation id(s): " + ", ".join(unknown))

    rc, out = _pytest()
    print("baseline before: " + ("PASS" if rc == 0 else "FAIL"))
    if rc:
        print(out[-2000:])
        return 1
    fired = []
    for m in rows:
        p = SCRIPTS / m["file"]
        # BYTES, not text. `read_text` translates CRLF to LF on the way in, so a text-mode
        # restore rewrites every line ending in the file and the sha256 check — the whole
        # point of the restore — fails on a working tree that is checked out CRLF.
        before, raw = _sha(p), p.read_bytes()
        nl = b"\r\n" if b"\r\n" in raw else b"\n"
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if m["old"] not in text:
            print(f"{m['id']}  TARGET GONE  {m['what']}")
            fired.append(False)
            continue
        assert text.count(m["old"]) == 1, f"{m['id']}: the target is not unique"
        try:
            mutated = text.replace(m["old"], m["new"]).replace("\n", nl.decode())
            p.write_bytes(mutated.encode("utf-8"))
            rc, out = _pytest(m["test"])
        finally:
            p.write_bytes(raw)
            assert _sha(p) == before, f"{m['id']}: RESTORE FAILED on {m['file']}"
        got = rc != 0
        fired.append(got)
        print(f"{m['id']}  {'FIRED' if got else 'DID NOT FIRE'}  {m['what']}")
        if not got:
            print("    the kill that should have caught it: " + m["kill"])
    rc, _out = _pytest()
    print("baseline after:  " + ("PASS" if rc == 0 else "FAIL"))
    return 0 if all(fired) and rc == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default=None, help="comma-separated mutation ids")
    a = ap.parse_args()
    return run([s.strip() for s in a.only.split(",")] if a.only else None)


if __name__ == "__main__":
    raise SystemExit(main())
