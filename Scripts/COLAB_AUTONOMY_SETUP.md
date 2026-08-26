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
        --daemon --allow-other \
        --vfs-cache-mode writes --vfs-cache-max-size 40G \
        --drive-pacer-min-sleep 10ms --transfers 8
`--vfs-cache-mode writes` is REQUIRED: the engine's verified-copy pattern re-reads
what it wrote (size+sha256) and a write-through mount fails that read-back.

## The canary (first rclone-mounted runtime only)
Cheap proof the engine's I/O patterns survive the mount change: stage one year's tiles
local (exercises bulk read), run one `_copy_to_drive` with checksum=True on a ~1 GB file
(exercises write + read-back + atomic rename), read back a raster window. All three green
→ record in CHATLOG and trust the mount; any red → fall back to human drive.mount and
report. The E02 os.replace smoke already passed on drivefs; rerun it once on rclone.

## Policy (P11.5 revision — takes effect when Kam merges CLAUDE.md)
- STOP: always autonomous, never asked. Idle runtimes are a defect, not a resource.
- CREATE for a queue Kam already approved by name (the kickoff-ask pattern): autonomous,
  logged with tier + purpose in CHATLOG.
- CREATE cold (no pre-approved queue): still asked, with tier/hours/cost.
- The 2-concurrent-runtime cap stays.

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
