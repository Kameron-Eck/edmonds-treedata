r"""The `vm_ops exec --file` payload that starts the litkb formula worker on a Colab VM.

WHY THIS FILE EXISTS INSTEAD OF `vm_ops launch --queue`. ``launch_queue()`` emits
``nohup python -u phase4_train_queue.py --queue <name>``, and that orchestrator understands
only phase4seg jobs keyed on ``year``/``tag`` (``phase4_train_queue.py``: ``y, tag =
job["year"], job["tag"]``). litkb has neither. So the launch splits in two, and the split is
the documented recipe:

    # 1. create the runtime and bootstrap it (write canary, editable install, repo clone)
    py -3.12 pipeline/vm_ops.py launch --session litkbf1 --gpu L4 \
        --branch work/20260915-colab-l4-formula
    # 2. start the worker, nohup-detached so it survives the exec handle
    py -3.12 pipeline/vm_ops.py exec --session litkbf1 \
        --file pipeline/litkb_formula_vm_start.py --timeout 900

Step 1 with no ``--queue`` does exactly the lifecycle work and nothing else — it is the same
bootstrap every queue gets, including the server-side-md5 write canary that proves uploads
reach Drive before any writer runs. CLAUDE.md 3.4 still applies to step 1: the FIRST launch
of this queue asks Kam.

ONE QUEUE PER RUNTIME. This payload reads ONE queue file and runs it on one VM. Splitting
across RUNTIMES is done by splitting the queue file, never by two processes over one file —
the results are content-addressed, so a double run wastes GPU rather than corrupting
anything, but it still wastes GPU.

N PROCESSES IS NOT TWO QUEUES. Since 2026-09-15 the queue file may carry ``procs: auto``, and
the worker then decodes one shard with N child processes on the ONE runtime — the canary
measured 2.02 GB of VRAM used on a 24 GB card and GPU utilisation peaking at 35%, so the card
was idle most of the run. Every process still belongs to the one queue, the batch plan is
computed once and shared by construction, and a slice that dies fails only its own crops. The
one-queue-per-runtime rule is about who owns the runtime, and it is unchanged.

WHICH QUEUE THIS PAYLOAD RUNS is the constant ``QUEUE`` below, and it is currently the FULL
CORPUS PASS (``queue_litkb_formula_l4_full.yaml``, 36 shards / 7,164 crops). Both canaries
have run — ``queue_litkb_formula_l4.yaml`` and ``queue_litkb_formula_l4_canary2.yaml`` are
kept as the record of what ran, and each writes to its own out_dir so neither is overwritten.
The out_dir and the process count come from the queue file itself rather than from this
payload, so switching queues is a one-line change here and nothing else.

DEPENDENCIES. The Colab image carries torch; it does NOT carry docling. The bootstrap's
editable install adds phase4seg and the shared modules and deliberately nothing else
(``gen_vm_bootstrap.py``: "pyproject.toml deliberately declares no [project] dependencies"),
so this payload installs docling pinned to the SAME versions as ``venv-docling-cuda``
— which are read from ``Scripts/requirements-litkb-colab.txt``, not retyped here — and REFUSES to
start if the resolved version differs from the pin, because a different docling is a
different CodeFormula and the local byte-for-byte comparison stops meaning anything.

WHAT THE VM'S torch IS, IS UNCONFIRMED. Locally the CUDA venv is ``torch==2.14.0+cu130``.
What Colab's L4 image ships has not been read on this account, and this payload does NOT
pin torch: reinstalling torch on a Colab VM is a 5-minute, occasionally-fatal operation and
the model is a stock transformers VLM. The resolved torch is recorded in every result
archive's ``worker.json``, so the first canary settles it as a measurement.
"""
import json
import subprocess
import time

REPO = "/content/repo"
SCRIPTS = REPO + "/Scripts"
MOUNT = "/content/drive/MyDrive/treedata"
QUEUE = SCRIPTS + "/pipeline/queue_litkb_formula_l4_full.yaml"
REQS = SCRIPTS + "/requirements-litkb-colab.txt"
LOG = MOUNT + "/phase4/logs/litkb_formula_nohup_%s.log" % time.strftime(
    "%Y%m%dT%H%M%SZ", time.gmtime())


def _torch():
    r = subprocess.run(["python", "-c",
                        "import torch;print(torch.__version__, torch.cuda.is_available())"],
                       capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


def main():
    # PRINT TORCH BEFORE AND AFTER THE INSTALL. docling declares a torch RANGE, not a pin, so
    # pip is free to replace the Colab image's CUDA torch with a PyPI wheel while satisfying
    # this file — the exact swap the requirements file says it avoids by not pinning torch.
    # If the two lines below differ, that is what happened, and it is visible in the exec
    # channel instead of being discovered by a CPU-speed run. UNMEASURED on a VM.
    print("LITKB_TORCH_BEFORE " + _torch())
    r = subprocess.run(["python", "-m", "pip", "install", "-q", "-r", REQS],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("LITKB_DEPS FAIL: " + (r.stderr or r.stdout)[-600:])
    probe = subprocess.run(
        ["python", "-c",
         "import json;from importlib.metadata import version;"
         "print(json.dumps({p: version(p) for p in "
         "('docling','docling-core','docling-ibm-models','torch','transformers')}))"],
        capture_output=True, text=True)
    print("LITKB_TORCH_AFTER " + _torch())
    print("LITKB_VERSIONS " + (probe.stdout or probe.stderr).strip())
    v = json.loads(probe.stdout)
    if v.get("docling") != "2.127.0" or v.get("docling-core") != "2.96.0":
        raise SystemExit(
            "LITKB_DEPS FAIL: docling %s / docling-core %s on this VM, but the local "
            "reference LaTeX was produced by 2.127.0 / 2.96.0. A different docling is a "
            "different CodeFormula; refusing to run." % (v.get("docling"),
                                                         v.get("docling-core")))
    # --out-dir and --procs are NOT passed: they are properties of the queue, and the worker
    # reads them from the queue file (load_queue). Passing them here is how canary 1 ended up
    # with a destination the queue file declared and nothing read.
    cmd = (
        "cd %s/pipeline && nohup python -u -m litkb.extract.colab_formula_worker "
        "--queue %s --device cuda > %s 2>&1 &"
        % (SCRIPTS, QUEUE, LOG))
    subprocess.run(cmd, shell=True, check=True)
    time.sleep(10)
    print("LITKB_FORMULA_STARTED " + LOG)


if __name__ == "__main__":
    main()
