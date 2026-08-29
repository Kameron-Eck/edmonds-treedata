# Colab runtime autonomy — automated mount + delegated lifecycle (2026-08-26)

Goal (Kam): Claude manages runtime lifecycle — especially STOPPING idle runtimes —
without the per-runtime human steps. Two human gates exist today: the permission
classifier on `colab new` (Claude-side) and the Drive-mount OAuth click (Google-side).
This doc is the one-time setup that removes the second and delegates the first.

## One-time setup (Kam, ~10 min total)

### A. Service account + key (~5 min)
1. https://console.cloud.google.com → create/select a project (e.g. `edmonds-pipeline`).
2. IAM & Admin → Service Accounts → Create. Name e.g. `treedata-mount`. No roles needed
   (Drive access comes from the folder share, not IAM).
3. On the new account → Keys → Add key → JSON. Save the file LOCALLY as
   `D:\edmonds-pipeline\secrets\treedata-mount-sa.json`
   (create the folder; it is OUTSIDE both git repos and never syncs anywhere).
4. Enable the Google Drive API for the project (APIs & Services → Enable → Drive API).

### B. Share ONLY the data lake with the service account (~1 min)
In Drive, right-click `treedata` → Share → the service account's email
(`treedata-mount@<project>.iam.gserviceaccount.com`) → Editor.
The account can now see exactly that folder and nothing else you own.

### C. Delegate the colab verbs (Claude Code settings, ~2 min)
Add Bash allow rules for the delegated verbs (Kam edits settings — /permissions or
settings file), e.g.:
    Bash(/c/Users/Kameron/.local/bin/colab.exe stop *)      ← always autonomous
    Bash(/c/Users/Kameron/.local/bin/colab.exe exec *)
    Bash(/c/Users/Kameron/.local/bin/colab.exe new *)       ← only if pre-approved-queue
                                                              creation is delegated (P11.5 rev)

## Per-runtime flow after setup (fully automated)
1. `colab new -s <name> [--gpu A100]`
2. `py -3.12 pipeline/gen_vm_bootstrap.py --session <name>` → emits a token-bearing
   one-shot script into local scratch (embeds the SA key + repo token; DELETE after use).
3. `colab exec -s <name> -f <scratch>/vm_bootstrap_<name>.py` → installs rclone, mounts
   the shared folder at `/content/drive/MyDrive/treedata` (the exact path every script
   expects), clones/updates the repo, prints `BOOTSTRAP_READY <commit>`.
4. First run on an rclone mount only: the CANARY (below) before any real queue.

## rclone mount parameters (chosen for this workload, tune only with evidence)
    rclone mount treedata-sa: /content/drive/MyDrive/treedata \
        --daemon \
        --vfs-cache-mode writes --vfs-cache-max-size 40G \
        --drive-pacer-min-sleep 10ms --transfers 8
`--allow-other` is deliberately ABSENT: it needs user_allow_other in /etc/fuse.conf and
root needs no it — MEASURED mount failure 2026-08-26. `--vfs-cache-mode writes` is REQUIRED: the engine's verified-copy pattern re-reads
what it wrote (size+sha256) and a write-through mount fails that read-back.

## The canary (first rclone-mounted runtime only)
Cheap proof the engine's I/O patterns survive the mount change: stage one year's tiles
local (exercises bulk read), run one `_copy_to_drive` with checksum=True on a ~1 GB file
(exercises write + read-back + atomic rename), read back a raster window. All three green
→ record in CHATLOG and trust the mount; any red → fall back to human drive.mount and
report. The E02 os.replace smoke already passed on drivefs; rerun it once on rclone.

## ONE VM PER QUEUE — chaining a second queue onto a finished VM DOES NOT WORK
### (measured twice, 2026-08-29)

**The session handle dies when the queue finishes.** Both times a VM completed its
queue and went idle, its entry vanished from `~/.config/colab-cli/sessions.json`
while the VM was still alive and beaconing, and `colab exec` returned
`Session '<name>' not found`:

| VM | queue finished | handle gone by | what failed |
|----|----------------|----------------|-------------|
| gpu34 | 11:58:35Z (seed777) | 12:00Z | chained smooth5 launch |
| gpu35 | 12:48:56Z (nodec_s1234) | 12:50Z | chained smooth5 launch, again |

Every SUCCESSFUL launch that night went to a **fresh** VM (`colab new` → bootstrap
→ launch). Every chain-onto-an-existing-VM attempt failed this way. The likely
cause is the Colab frontend dropping the kernel once it goes idle, with the CLI
pruning the session on its next state write — but the cause does not matter
operationally. The rule does:

> **Never plan to run a second queue on a VM that has finished its first.**
> Create a new runtime per queue and let the watchdog reclaim the old one.

Consequences for scheduling:
- Wall-clock per arm includes a fresh bootstrap (~2-3 min), not just train time.
- A100 scarcity is the real throughput limit — `colab new` returned
  `Precondition Failed` repeatedly on 2026-08-29 and needed a 240 s backoff loop.
- Launchers must grep FAILURE signatures, not just success ones. A chain that
  greps only `LAUNCHED` exits 0 having launched nothing, and the VM then idles out
  to the watchdog with the work silently undone (this happened once, 2026-08-29).

## NEVER run two colab CLI calls at once (measured 2026-08-29)

A `colab exec` issued against a DYING session while another launcher was mid-
bootstrap on a DIFFERENT session killed that launcher with SIGTERM (exit 15) and
left a created-but-unbootstrapped VM behind. The CLI printed
`Session 'gpu38' appears to be lost (404/401). Cleaning up.` and the cleanup took
the sibling process with it.

> **One colab CLI call at a time, always.** Bootstrap and launch belong in ONE
> sequential script (see `seq_gpu39_smooth5.sh`), and no diagnostic exec may be
> issued while any launcher is running. Check heartbeats — which are plain file
> reads — instead of exec'ing when something else is in flight.

This is the same discipline as "never kill mid-exec": these handles die
permanently, and a lost handle strands a live VM that then bills until its
watchdog fires.

## Killing a launcher LOCALLY does not stop the work REMOTELY (2026-08-29)

`colab new` and `colab exec` dispatch to the runtime and return; the runtime keeps
going even if the local process dies. Measured twice in one night:

- A launcher killed with TaskStop at 11:50Z had already asked for a runtime.
  `gpu36` appeared in the session file ~2 h later, created and idle the whole time.
- A launcher SIGTERM'd mid-bootstrap at 13:27Z still completed its bootstrap AND
  launched its queue on `gpu39`; the arm I believed dead had been training for
  five minutes when I found it.

Two consequences, one of them expensive:

1. **A created-but-unbootstrapped VM has NO WATCHDOG.** The self-stop watchdog is
   armed BY the bootstrap, so a VM that was created and then abandoned idles until
   Google reclaims it — not the 10-min/2-h bounds the watchdog would give. `gpu36`
   burned ~2 h that way. **After stopping any launcher, check `colab ls` and the
   session file for a VM it may have created anyway, and either bootstrap it or
   stop it.**
2. **"I killed that job" is not a safe assumption.** Before relaunching an arm,
   check the status CSVs on the lake for a run you think never started — and check
   for contamination before reusing anything it touched.

## Runtimes can vanish mid-queue

`gpu38` (L4) died ~5 min into its queue: heartbeat stopped, and the next exec
returned 404/401. Nothing was recoverable and the arm had to be relaunched from
scratch. Treat any beacon older than ~4 min as a dead VM, not a slow one, and
relaunch rather than investigate — investigating costs an exec, and the exec is
what strands other sessions.

## Policy (P11.5 revision — takes effect when Kam merges CLAUDE.md)
- STOP: always autonomous, never asked. Idle runtimes are a defect, not a resource.
- CREATE for a queue Kam already approved by name (the kickoff-ask pattern): autonomous,
  logged with tier + purpose in CHATLOG.
- CREATE cold (no pre-approved queue): still asked, with tier/hours/cost.
- Concurrency: 3-4 runtimes OK (Kam 2026-08-26; Google throttles ~5+). Bulk
  Drive copies still serialize via the staging lock.

## Security notes
- The SA key and gh token live ONLY in `D:\edmonds-pipeline\secrets\` and local scratch;
  never in either git repo, never on Drive. Scratch bootstrap scripts are deleted after
  use (they embed both).
- Blast radius of a leaked SA key = the shared `treedata` folder (revocable by unsharing
  or deleting the key in the console), not the Google account.

## STATUS: setup COMPLETE 2026-08-26 (all steps done via browser automation with Kam present)
- Project `edmonds-pipeline` created (billing attached; Drive API usage is $0).
- SA `treedata-mount@edmonds-pipeline.iam.gserviceaccount.com`, key at
  `D:\edmonds-pipeline\secrets\treedata-mount-sa.json`; folder id saved beside it.
- Drive API enabled; `treedata` shared with the SA (Editor, no notification).
- PROVEN end-to-end from the qc VM: `rclone lsd` + deep `ls` under the SA — SA_ACCESS OK.
- Still owed: the MOUNT canary on the next fresh VM (rclone mount ≠ rclone ls; see
  the canary section). Kam's remaining step: the settings allowlist for colab.exe verbs.

## STATUS 2: MOUNT CANARY PASS 2026-08-26 (the flow is fully proven)
All four stages green on the qc VM (alternate mount point, live mount untouched):
101 MB read hash-identical via rclone vs drivefs (4.9s vs 1.1s — cold reads slower,
moot given local staging); the E02 atomic publish (copy -> verify -> os.replace)
works through rclone (replace 0.00s); rasterio window reads work. Root causes fixed
along the way, both now encoded in gen_vm_bootstrap.py: --allow-other dropped
(fuse.conf), fuse3 auto-installed (fusermount3 absent on Colab images).
The runtime lifecycle is now fully automatable: create -> bootstrap -> mounted ->
repo-ready -> work -> stop, zero human clicks.

## STATUS 3: FULL LIFECYCLE PROVEN UNATTENDED 2026-08-26
create (allowlisted, no prompt) -> gen_vm_bootstrap -> exec on a VIRGIN VM ->
BOOTSTRAP_READY @ repo HEAD, canonical mount path, zero clicks -> stop. Kam's
allowlist is live. The agentic runtime workflow is DONE.

---

# Oversight — the VM pushes, the local tool judges (2026-08-26)

Kam's directive: *"introduce oversight tools into the agentic GPU and CPU runtimes —
quality feedback to show when it's working — deterministic tools to reduce active
oversight, to reduce token usage."*

**The problem this replaces.** Checking on a runtime used to cost a `colab exec`
round-trip: slow, and token-heavy every time Claude drove it. Repeated every few
minutes across a long queue, routine "is it still alive?" probing was the single
largest avoidable token cost of an unattended run.

**The inversion.** The VM now PUSHES its own state to the data lake once a minute;
oversight becomes a local file read.

    pipeline/vm_heartbeat.py   ON the VM, stdlib-only, launched by the bootstrap under
                               nohup. Every 60 s it OVERWRITES (atomic tmp+rename, <2 KB)
                                   {BASE}/phase4/logs/heartbeat_{session}.json
                               = ts_utc, gpu {name, util_pct (mean of 3 samples),
                               util_max_pct, mem_used_mb}, queue_proc pid, engine_proc
                               args tail, newest_nohup {name, size, prev_size},
                               newest_status {name, size, last_line}, scratch_gb,
                               prev_scratch_gb, mount_ok.
    qc/runtime_health.py       LOCAL. Reads those heartbeats off the G: mirror + the
                               merged status CSVs (via watch_queue._rows — one home for
                               that merge) + the colab CLI's session store FILE.
                               One line per session, one exit code, no colab exec.

## The contract

- **Routine checks are `py -3.12 qc/runtime_health.py`** — near-zero tokens, no GPU
  touched, no billing, no `colab exec`. This is what Claude runs each tick.
- **`colab exec` probing is for DIAGNOSIS AFTER a flag fires**, never for "is it alive?".
  A flag names what to go look at; that is when a round-trip is worth its cost.
- The beacon **reads state and never acts on it** — no killing, no restarting, no
  writing outside its own heartbeat file. Judgement is the reader's, action is Kam's.

The one-liner Claude uses each tick (exit code IS the answer; 0 = quiet, 1 = read the
line, 2 = go look):

    py -3.12 qc/runtime_health.py

## Rules (each prints its NAME when it fires — the name is the finding)

| Flag | Sev | Fires when |
|---|---|---|
| `HEARTBEAT_STALE` | crit (2) | beat older than `--stale-min` (default 5) **for a session the CLI still lists** — VM dead, beacon dead, or mount broken |
| `OLD_HEARTBEAT` | ok (0) | stale beat for a session the CLI no longer lists — the file a deliberately stopped VM left behind (see below); quiet by design |
| `MOUNT_LOST` | crit (2) | a heartbeat that says `mount_ok=false` |
| `QUEUE_DEAD` | crit (2) | beat FRESH but no queue process, while its status file still shows RUNNING steps |
| `STALL` | warn (1) | engine process alive but its nohup log has not grown since the previous sample |
| `GPU_IDLE_IN_TRAIN` | warn (1) | util < `--idle-pct` during `--step train` AND scratch stable (stable scratch = not staging, so the idle is real) |
| `NO_HEARTBEAT` | warn (1) | a live CLI session with no heartbeat file (pre-beacon VM, or the nohup line never ran) |
| `ORPHAN_HEARTBEAT` | warn (1) | a FRESH beat with no CLI session entry = the 2026-08-22 prune failure (a billing VM the CLI forgot) — `qc/colab_readopt.py` |
| `TERMINAL` | ok (0) | every job in the launch has its job-end VERIFY row; prints the verdict. Exit 1, not 0, if any verdict is a BAD state |

Also: `--json` (machine-readable), `--watch N` (poll locally, still zero `colab exec`),
`--base` (point at another lake — how the rules are tested without a VM).

**Three design points worth keeping:**
1. **Stateless locally.** The heartbeat carries its OWN previous samples
   (`prev_size`, `prev_scratch_gb`), so STALL and GPU_IDLE_IN_TRAIN need no local
   history and no second poll. Both rules **no-op while a prev field is null** —
   otherwise every beacon restart would read as a stall.
2. **Launch-scoped, not merged.** A crashed launch leaves RUNNING rows in its status
   file forever. QUEUE_DEAD is judged only against the status file THIS VM's heartbeat
   names, which is what stops dead launches from flagging critical for all eternity.
   Same reason the beacon filters its own globs by its queue stem: with 2 concurrent
   runtimes, both write into the same Drive dirs.
3. **The G: mirror lags the VM.** A single STALE beat is not proof of death — the tool
   says so in its own footer. Confirm with `colab exec` before acting. QUEUE_DEAD has
   the same transient: a queue that exits before its final rows sync shows RUNNING rows
   with no process for a tick or two. **A CRIT that clears on the next tick was lag.**
4. **A stopped VM must read OK, not CRITICAL.** Nothing deletes a heartbeat file when a
   VM stops, but `colab stop` DOES delete the session entry (`state.store.remove` in the
   CLI's `commands/session.py` — read, not guessed). Since "STOP: always autonomous"
   makes that the state after *every* normal run, a stale beat for a session the CLI no
   longer lists is reported as `OLD_HEARTBEAT` at severity OK. Only a **fresh** beat with
   no session entry is a finding — that one is a live billing VM the CLI forgot.
   HEARTBEAT_STALE therefore requires the session to still be in the store.

Timestamps: heartbeat `ts_utc` is real UTC; the status CSV `ts` is the queue's naive
`datetime.now()` on a UTC-clocked VM, so it is read as UTC (documented assumption).

## Testing it without a VM

    py -3.12 pipeline/vm_heartbeat.py --session test --once --base <scratch>\lake \
        --scratch <scratch>\scratch --breadcrumb <scratch>
    py -3.12 qc/runtime_health.py --base <scratch>\lake \
        --sessions-json <scratch>\no_sessions.json      # {} = "no VM is running"

`--sessions-json` exists so the post-shutdown case (leftover beat, no CLI entry) can be
proven to exit 0 without stopping a live runtime. `--cycles N` on the beacon writes N
heartbeats and exits.

On Windows `ps`/`nvidia-smi`/the mount are absent — every affected field degrades to
null instead of raising. **Never write test heartbeats into the real G: logs dir**:
`runtime_health` globs `heartbeat_*.json` there and a stray test file becomes a
phantom session.

## Future: the dashboard reads the same beat (NOT implemented)

`qc/runtime_dashboard.py` still learns freshness from its own `colab exec` probe. The
integration point for a future PR is `probe_session()` (called from
`Collector.probe_all`): read
`{BASE}/phase4/logs/heartbeat_{session}.json` FIRST and skip the exec probe entirely
while the beat is fresh (< `--stale-min`), falling back to the probe only when it is
stale or when the tqdm tail is actually wanted — the tail is the one field the beacon
deliberately does not carry (it would blow the 2 KB budget). That turns the dashboard
from a per-interval spender into a near-free reader too. Deliberately left for its own
PR; nothing in the dashboard was touched by this change.

## STATUS 4: WRITE PATH BROKEN — SA storage quota is ZERO (measured server-side 2026-08-26)
`drive.about.storageQuota.limit = '0'` for the service account: Google grants SAs no
Drive storage, and files uploaded via the SA mount are OWNED BY THE SA -> every large
file upload silently fails (folders/metadata succeed, which is why BOOTSTRAP_READY and
run-folder creation looked healthy). The mount canary was structurally blind: it
verified through the local vfs write-cache and deleted its test file before any
server-side stat. MEASURED COST: the 3-repeat noise queue's artifacts (3 ckpts, 3
rasters, eval rows, status CSVs) never reached Drive and died with the VM (~3.5 A100-h
to re-run once fixed).

RULES UNTIL FIXED: the SA-rclone mount is READ-SAFE ONLY. Any VM that WRITES uses
Kam's manual drive.mount. Canary v2 must verify uploads SERVER-SIDE (Drive API stat of
size+md5 with independent credentials), never through the writing mount.

THE FIX (one-time, Kam ~2 min): a user-OAuth rclone token — files then owned by Kam
(2TB quota). Locally: install rclone (winget install Rclone.Rclone), run
`rclone authorize "drive"` (browser click), save the token JSON to
D:\edmonds-pipeline\secrets\rclone_user_token.json; gen_vm_bootstrap then ships a
user-token remote for WRITER VMs and keeps the SA remote for reader VMs. Shared
Drives would be cleaner but need Workspace (personal account: unavailable).
