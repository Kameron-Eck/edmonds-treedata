# Golden-gate v2 — launch runbook

**What this launches.** Five INFERENCE-ONLY jobs (`pipeline/queue_golden_v2.yaml`) that
re-run five existing checkpoints over `pipeline/aoi/sentinel_v1.json` — the 12 frozen
sentinel windows — under five NEW run tags, so `qc/phase4_golden_gate.py` can score all
12 windows for arms whose shipped prob rasters cover only ~1 of them. No training, no
tiling, no label build, no existing raster touched (P7: new tags are mandatory).

**Cost.** ~2–5 min GPU per job (the AOI is 2.50% of the 2016 grid) plus imagery staging,
which the AOI does **not** shrink. Two orthos across five jobs. Budget ~45–75 min
wall-clock for the whole queue, most of it staging and checkpoint load.

**Utilization.** This rides the warm session the noise queue frees. **One queue per
runtime (P11)** — the launch script refuses if `phase4_train_queue.py` is still running.

---

## Preconditions

| # | Check | How |
|---|-------|-----|
| 1 | Noise queue has EXITED | `pgrep -af phase4_train_queue.py` returns nothing (the launch script asserts this) |
| 2 | Data lake mounted | `/content/drive/MyDrive/treedata/phase4` is a dir (setup asserts) |
| 3 | Repo clone present | `/content/repo/Scripts/pipeline` exists (setup asserts) |
| 4 | Engine supports `--infer-aoi` | Already true — the noise queue used it on this same clone |
| 5 | Kam's GPU permission | P11.5 first-launch rule: **ask before this launch**, stating queue file, tier, runtimes, wall-clock, cost |

**Do not** `git clean` the VM clone at any point after setup — two of the three files this
runbook places are untracked-in-the-clone by design (see below).

---

## The two-uncommitted-files problem — read this before anything else

Nothing in this build was committed or pushed. The VM's clone therefore has **neither**
`aoi/sentinel_v1.json` **nor** `queue_golden_v2.yaml`, and re-fetching the branch will not
bring them. Both must be written VM-side:

- **`sentinel_v1.json` must land at `/content/repo/Scripts/pipeline/aoi/sentinel_v1.json`.**
  `phase4_train_queue.run_step` launches the engine with `cwd = <repo>/Scripts/pipeline`,
  and `phase4seg/core.py::_aoi_pixel_rects` resolves a relative `--infer-aoi` against
  `Path.cwd()` first. The engine's *staged package* dir has no `aoi/` (found 2026-08-25),
  so cwd is the only reliable anchor. Miss this and every job dies with
  `FileNotFoundError: --infer-aoi aoi/sentinel_v1.json: not found`.
- **`queue_golden_v2.yaml` goes to `/content/`** and is passed as an absolute
  `--queue /content/queue_golden_v2.yaml`. `_load_queue` only prefixes the pipeline dir
  for *relative* paths, so an absolute path is accepted as-is.

---

## Step 1 — emit the VM scripts (local, no network, no secrets)

Save the block below as `%LOCALAPPDATA%\Temp\sector_campaign_vm\emit_golden_v2_vm.py`
and run `py -3.12 emit_golden_v2_vm.py`. It reads the three repo artifacts and inlines
them into two `colab exec` payloads. It was compiled and run during the build; the
emitted scripts were `py_compile`d clean.

```python
r"""Emit the golden-gate v2 VM scripts to local scratch (no secrets, no network).

Reads the three repo artifacts (AOI json, queue yaml, ckpt map) and inlines them into
two scripts the orchestrator feeds to `colab exec`. Nothing is committed and nothing is
pushed, so the VM's repo clone does NOT have the AOI or the queue — this is how they get
there.

  py -3.12 emit_golden_v2_vm.py
  colab exec -s <session> -f <scratch>/vm_golden_v2_setup.py  --timeout 900
  colab exec -s <session> -f <scratch>/vm_golden_v2_launch.py --timeout 120
"""
import csv
import io
import os
from pathlib import Path

SCRIPTS = Path(r"D:\edmonds-pipeline\treedata\Scripts")
SCRATCH = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "sector_campaign_vm"
QUEUE_NAME = "queue_golden_v2.yaml"
SEED_CSV = "train_queue_status_queue_golden_v2_seed.csv"
SEED_STEPS = ["labels", "tile", "train", "evaluate"]

AOI_TXT = (SCRIPTS / "pipeline" / "aoi" / "sentinel_v1.json").read_text(encoding="utf-8")
QUEUE_TXT = (SCRIPTS / "pipeline" / QUEUE_NAME).read_text(encoding="utf-8")
_map = (SCRIPTS / "pipeline" / "golden_v2_ckpt_map.csv").read_text(encoding="utf-8")
PAIRS = [(r["job"], r["year"], r["tag"], r["src"], r["dst"])
         for r in csv.DictReader(io.StringIO(_map))]

SETUP = f'''# golden-gate v2 SETUP — place files, seed the queue, copy checkpoints. Idempotent.
import csv, datetime, os, shutil, subprocess, time

MOUNT = "/content/drive/MyDrive/treedata"
REPO  = "/content/repo"
AOI_TXT   = {AOI_TXT!r}
QUEUE_TXT = {QUEUE_TXT!r}
PAIRS     = {PAIRS!r}
SEED_STEPS = {SEED_STEPS!r}

assert os.path.isdir(MOUNT + "/phase4"), "data lake not mounted — run the bootstrap first"
assert os.path.isdir(REPO + "/Scripts/pipeline"), "repo clone missing at " + REPO

# 1 ── AOI must sit beside the engine. phase4_train_queue runs the engine with
#      cwd = <repo>/Scripts/pipeline, and _aoi_pixel_rects resolves a relative
#      --infer-aoi against cwd FIRST (the staged package dir has no aoi/).
aoi_dir = REPO + "/Scripts/pipeline/aoi"
os.makedirs(aoi_dir, exist_ok=True)
open(aoi_dir + "/sentinel_v1.json", "w", encoding="utf-8").write(AOI_TXT)
print("AOI", aoi_dir + "/sentinel_v1.json", os.path.getsize(aoi_dir + "/sentinel_v1.json"), "bytes")

# 2 ── queue at /content (uncommitted; _load_queue accepts an absolute path)
open("/content/{QUEUE_NAME}", "w", encoding="utf-8").write(QUEUE_TXT)
print("QUEUE /content/{QUEUE_NAME}", os.path.getsize("/content/{QUEUE_NAME}"), "bytes")

# 3 ── seed CSV: labels/tile/train/evaluate = OK so ONLY inference runs.
#      Column contract is the queue's own header — a "job_id" header is invisible to
#      _completed_steps() and the queue starts full fine-tunes (cost that lesson once).
#      ts is UTC now + 5 min so the seed wins the ts-sorted merge against any row,
#      including a stale RUNNING row that would revoke an earlier OK.
ts = (datetime.datetime.now(datetime.timezone.utc)
      + datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
seed = MOUNT + "/phase4/qc/{SEED_CSV}"
cols = ["job", "year", "tag", "step", "state", "exit", "minutes", "detail", "ts"]
with open(seed, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    n = 0
    for job, year, tag, _src, _dst in PAIRS:
        for s in SEED_STEPS:
            w.writerow(dict(job=job, year=year, tag=tag, step=s, state="OK", exit=0,
                            minutes=0, ts=ts,
                            detail="SEEDED: golden-gate v2 inference-only re-run "
                                   "(existing ckpt copied to the golden tag; no fine-tune)"))
            n += 1
print("SEED", seed, n, "rows, ts", ts)

# 4 ── checkpoints. The engine loads sem_best_{{year}}_{{tag}}.pt, so each job needs its
#      source ckpt under the golden tag name. rclone copyto on ONE remote is a Drive
#      SERVER-SIDE copy: seconds, ~0 bytes through the VM, owned by the user token.
#      shutil.copy2 through the mount is the fallback (~1.1 GB each).
def remote(p):
    assert p.startswith(MOUNT + "/")
    return "treedata-user:" + p[len(MOUNT) + 1:]

todo = []
for job, year, tag, src, dst in PAIRS:
    assert os.path.exists(src), "SOURCE CKPT MISSING: " + src
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        print("  SKIP (already correct)", os.path.basename(dst))
        continue
    r = subprocess.run(["rclone", "copyto", remote(src), remote(dst)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print("  server-side copy ->", os.path.basename(dst))
        todo.append((src, dst))
    else:
        print("  rclone rc=%d, falling back to mount copy: %s"
              % (r.returncode, (r.stderr or "")[-200:]))
        shutil.copy2(src, dst)
        print("  mount copy ->", os.path.basename(dst), os.path.getsize(dst))

# 4b ─ a server-side copy is invisible to the FUSE mount until its dir cache refreshes
#      (rclone polls Drive ~1 min). The engine calls ckpt.exists() THROUGH the mount,
#      so wait for visibility rather than launching into a false "run step train first".
deadline = time.time() + 480
while todo and time.time() < deadline:
    todo = [(s, d) for s, d in todo
            if not (os.path.exists(d) and os.path.getsize(d) == os.path.getsize(s))]
    if todo:
        time.sleep(15)
for s, d in todo:
    print("  ! not visible on the mount after 8 min — copying through it:", os.path.basename(d))
    shutil.copy2(s, d)

bad = []
for job, year, tag, src, dst in PAIRS:
    ok = os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src)
    print("  CKPT", os.path.basename(dst),
          os.path.getsize(dst) if os.path.exists(dst) else "MISSING", "OK" if ok else "BAD")
    if not ok:
        bad.append(os.path.basename(dst))
if bad:
    print("SETUP_FAIL", bad)
else:
    print("SETUP_READY")
'''

LAUNCH = f'''# golden-gate v2 LAUNCH — nohup the queue. Run ONLY after SETUP_READY and only when
# no other queue is running on this runtime (one queue per runtime, P11).
import datetime, os, subprocess

MOUNT = "/content/drive/MyDrive/treedata"
REPO  = "/content/repo"
q = "/content/{QUEUE_NAME}"
assert os.path.exists(q), "queue missing — run vm_golden_v2_setup.py first"
assert os.path.exists(REPO + "/Scripts/pipeline/aoi/sentinel_v1.json"), \\
    "AOI missing — run vm_golden_v2_setup.py first"

busy = subprocess.run(["pgrep", "-af", "phase4_train_queue.py"],
                      capture_output=True, text=True).stdout.strip()
assert not busy, "another queue is still running on this runtime:\\n" + busy

ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
log = MOUNT + "/phase4/logs/train_queue_nohup_queue_golden_v2_" + ts + ".log"
p = subprocess.Popen("cd " + REPO + "/Scripts/pipeline && nohup python -u "
                     "phase4_train_queue.py --queue " + q + " > " + log + " 2>&1 & echo $!",
                     shell=True, stdout=subprocess.PIPE, text=True)
out, _ = p.communicate(timeout=30)
print("LAUNCHED pid", out.strip())
print("LOG", log)
'''

SCRATCH.mkdir(parents=True, exist_ok=True)
(SCRATCH / "vm_golden_v2_setup.py").write_text(SETUP, encoding="utf-8")
(SCRATCH / "vm_golden_v2_launch.py").write_text(LAUNCH, encoding="utf-8")
print(f"wrote {SCRATCH / 'vm_golden_v2_setup.py'}  ({len(SETUP):,} bytes)")
print(f"wrote {SCRATCH / 'vm_golden_v2_launch.py'} ({len(LAUNCH):,} bytes)")
print(f"{len(PAIRS)} ckpt copies, {len(PAIRS) * len(SEED_STEPS)} seed rows")
```

Expected local output: `5 ckpt copies, 20 seed rows`.

---

## Step 2 — setup (VM)

```
colab exec -s <session> -f %LOCALAPPDATA%\Temp\sector_campaign_vm\vm_golden_v2_setup.py --timeout 900
```

It does four things, all idempotent (safe to re-run):

1. writes `sentinel_v1.json` to `/content/repo/Scripts/pipeline/aoi/`;
2. writes `queue_golden_v2.yaml` to `/content/`;
3. writes the **20-row seed** to
   `/content/drive/MyDrive/treedata/phase4/qc/train_queue_status_queue_golden_v2_seed.csv`;
4. makes the **five checkpoint copies** from `pipeline/golden_v2_ckpt_map.csv`.

**Gate: it must print `SETUP_READY`.** If it prints `SETUP_FAIL [...]`, do not launch —
the named checkpoints are missing or the wrong size.

### Seed contract (why it is written the way it is)

`phase4_train_queue._completed_steps()` merges **every** `train_queue_status*.csv` in
`phase4/qc/` and keys on `(job, step)`. The seed marks `labels, tile, train, evaluate`
as `state=OK` for all five jobs, so the queue skips straight to `inference`.

- **Header must be exactly** `job,year,tag,step,state,exit,minutes,detail,ts`. A
  `job_id` header is silently invisible and the queue starts five full fine-tunes — that
  exact bug cost a run on 2026-08-25.
- **`ts` must sort after any real row.** The property that matters is "later than
  anything already on disk", because a stale `RUNNING` row revokes an earlier `OK`. The
  proven `sector_campaign_loop._seed_ts()` uses **UTC now + 5 min** and this runbook
  matches it (the E07 brief said +2 min; +5 is strictly safer and never harmful, since
  the queue itself never writes rows for a seeded step).
- **Written VM-side** so the seed is visible in the same place the queue's own status
  files land, and so it cannot be stale relative to launch.
- Verified locally against the real reader before shipping: with this seed in place,
  `_completed_steps()` returns 20 pairs and every job's remaining work is exactly
  `['inference']`.

### Checkpoint copies

The engine loads `MODELS_DIR / f"sem_best_{label}{_tag_sfx()}.pt"` and
`_tag_sfx()` is `f"_{RUN_TAG}"` — so a job tagged `golden_v1_2016cw` on year `2016`
looks for `sem_best_2016_golden_v1_2016cw.pt`. Source → destination is
`pipeline/golden_v2_ckpt_map.csv`:

| job | source | destination |
|-----|--------|-------------|
| `2016cw_g` | `sem_best_2016.pt` | `sem_best_2016_golden_v1_2016cw.pt` |
| `2016corr_g` | `sem_best_2016_corrected.pt` | `sem_best_2016_golden_v1_2016corr.pt` |
| `2016fx_g` | `sem_best_2016_fullext_sectors_v1.pt` | `sem_best_2016_golden_v1_2016fx.pt` |
| `2021sp2_g` | `sem_best_2021s_p2nir.pt` | `sem_best_2021s_golden_v1_2021sp2.pt` |
| `2021sfx_g` | `sem_best_2021s_fullext_sectors_v1.pt` | `sem_best_2021s_golden_v1_2021sfx.pt` |

All under `phase4/models/`. All five sources verified present on the lake at build time
(1.11 GB each; ~5.5 GB of copies).

`rclone copyto` between two paths on the **same** remote (`treedata-user:`) is a Drive
**server-side** copy — seconds, no bytes through the VM, and the copy is owned by the
user token (the service account has zero storage quota and its uploads fail silently).
The mount does not see a server-side copy until its dir cache refreshes, so setup polls
`os.path.exists` **through the mount** for up to 8 min before giving up and copying
through it; the engine's `ckpt.exists()` goes through the mount too, which is why this
wait exists rather than launching immediately.

---

## Step 3 — launch (VM)

```
colab exec -s <session> -f %LOCALAPPDATA%\Temp\sector_campaign_vm\vm_golden_v2_launch.py --timeout 120
```

Asserts no other queue is running, then `nohup`s:

```
cd /content/repo/Scripts/pipeline && nohup python -u phase4_train_queue.py \
    --queue /content/queue_golden_v2.yaml \
    > /content/drive/MyDrive/treedata/phase4/logs/train_queue_nohup_queue_golden_v2_<ts>.log 2>&1 &
```

It prints `LAUNCHED pid <n>` and `LOG <path>`. Record both.

---

## Step 4 — what a healthy run looks like

Read the nohup log from Drive (never ask for pasted terminal output). Per job expect:

- **THE KILL GATE — the first `$ …` command line printed under each job header must say
  `--step inference`.** If any job's first step line says `--step labels` (or `tile`, or
  `train`), the seed did not take: **kill the process immediately**, five full fine-tunes
  are starting on a warm GPU. Do **not** use the `RESUME: N step(s) already OK` line as
  the gate — `N` counts every OK pair in the whole merged history (hundreds), so it looks
  healthy either way and would not catch this.
  The healthy line is:
  `$ --year 2016 --step inference --infer-batch N --run-tag golden_v1_2016cw --force-citywide --infer-aoi aoi/sentinel_v1.json --skip-postproc`
- `- skip <job>/labels (already OK)` ×4 per job, then inference. Same signal, stated the
  other way round.
- `AOI: 12 rect(s) from sentinel_v1.json (~2.5% of the grid; rest → nodata)` — **12 is
  the number that matters.** Fewer means a rect fell off the ortho.
- For `2021sp2_g` only: `ckpt was trained with --hs-source nir — adopting it.` If that
  line is absent the NIR arm is being run as RGB; stop and report.
- `phase4/masks/edmonds_canopy_prob_{year}_{tag}.tif` on the lake, one per job.

Status rows land in `phase4/qc/train_queue_status_queue_golden_v2_<launchts>.csv`
(readers merge all `train_queue_status*.csv`).

### EXPECTED: every job ends `VERIFY:inference MOSTLY_NODATA`. That is not a failure.

`_check_prob_raster` calls a raster `MOSTLY_NODATA` when under **5%** of sampled pixels
are valid, and `MOSTLY_NODATA` is in `_VERIFY_HARD_FAIL`. That floor was calibrated on
the ~10–17%-valid sector arms (base2020 measured 10.7–16.7%, all `OK`). **This AOI is
2.5% by design**, so all five jobs will hard-fail verification and log:

```
! <job> step 'inference' exited 0 but its ARTIFACT failed verification.
  Stopping this job before spending more GPU.
```

What this does and does not mean:

- **The prob raster is already written and verified-copied to the lake** before
  `verify_step` runs, and inference is the LAST step — so nothing is lost and no GPU is
  wasted. The rasters are scorable.
- The `break` exits that job's step loop only; **the queue continues to the next job.**
  All five still run.
- The job-end `VERIFY <job>` row is skipped (it is only written when every step passed),
  and the queue's closing summary will list the jobs as failures. Read past it.
- **Acceptance test instead:** read each `VERIFY:inference` detail —
  `NNMb valid≈2.5% maxprob=… p99.9=…`. `valid` near 2.5% with a sane `maxprob`/`p99.9`
  (compare the arm's own sector run) means the raster is good. `valid` far from 2.5%,
  or `maxprob < 0.5`, is a real problem.
- **Consequence for restarts:** a `MOSTLY_NODATA` VERIFY row revokes the step's `OK` in
  `_completed_steps()`, so re-launching this same queue file re-runs **all five**
  inferences rather than resuming. Only relaunch if you actually want them re-run.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: --infer-aoi aoi/sentinel_v1.json` | AOI not placed in the clone's `pipeline/aoi/` | re-run setup; do not `git clean` |
| A job's first `$ …` line says `--step labels` / `--step train` | seed missing / wrong header / stale `ts` | **kill the process now**, re-run setup, relaunch, confirm the first step line reads `--step inference` |
| `VERIFY:inference … MOSTLY_NODATA` on every job | expected at 2.5% valid — the 5% floor was set for ~10% sector AOIs | none; see the section above. Judge the raster by `maxprob` / `p99.9`, not by the state |
| `ERROR: ... sem_best_<year>_<tag>.pt not found — run step train first` | ckpt copy not visible through the mount | re-run setup (it will copy through the mount on the second pass) |
| `AOI: 0 rect(s)` / `--infer-aoi has no overlap` | wrong CRS or a truncated json | re-emit locally; `py -3.12 pipeline/make_sentinel_aoi.py --check` prints the 12/12 on-grid count |
| Job id already `OK` in history | a reused job id | job ids here (`*_g`) were checked against all 17 historical status files — none collide. Never reuse `2016_fx` / `2021s_fx` |

## After the run

Score each new arm with `qc/phase4_golden_gate.py` (year + tag). That is a separate step
with its own threshold contract and is deliberately **not** part of this runbook.

## Non-goals

Nothing here trains, re-tiles, rebuilds labels, or overwrites an existing raster. If a
step other than `inference` runs, that is a bug in the seed, not a plan.
