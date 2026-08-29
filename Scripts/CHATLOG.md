# Edmonds Pipeline — Chat / Progress Log

Running log of work sessions. Newest first. Open this → read STATE + top entries →
caught up. **This STATE block + the active plan ARE the handoff** (per-session
`HANDOFF_*.md` retired 2026-07-06 → `_archive/`). Doc map: `../README.md`.

════════════════ HOW TO LOG  (read before appending) ════════════════

STYLE — caveman, "full" level  (github.com/JuliusBrussee/caveman)
- Drop: articles (a/an/the), filler (just/really/basically/simply/actually),
  pleasantries (sure/happy to), hedging. Fragments OK. Short synonyms
  (big not extensive; fix not "implement a solution for").
- Pattern: "[thing] [action] [reason]. [next]."
- KEEP EXACT (never compress): code, file names, identifiers, numbers, flags,
  quoted errors, version tags. Well-known acronyms OK (DB/API/CRS); never coin
  abbreviations the reader can't decode.
- SUSPEND caveman (write plainly) for: irreversible-action / security warnings,
  and multi-step sequences where dropped conjunctions risk a misread. (skill's
  own auto-clarity rule). This HOW-TO block is instructional → kept plain.

SCALE — one block per SESSION or per landed MILESTONE (decision made / feature
landed / direction changed). NOT per message. Append when a unit of work closes.

ENTRY SCHEMA — fixed fields, omit empty ones:
    ## YYYY-MM-DD  <slug>
    goal:    why this session existed
    did:     what landed — DELTAS only
    decided: key decisions + 1-word why
    killed:  dead-ends / reversals — 1 line each, so we don't retry them
    files:   paths / version tags touched — reference, don't restate
    next:    open threads

SPACE RULES — keep always-loaded context low for continuous logging:
  1. Reference, don't repeat — link version/handoff/file; don't re-explain (see v025).
  2. Deltas not full-state — log what CHANGED; current full state lives in STATE.
  3. Outcomes not tool-noise — no command-by-command narration.
  4. Rolling compaction — keep newest ~6 entries full; older → 1 line each under
     "ARCHIVE (1-liners)". Compact when full entries exceed ~6.
  5. STATE edited IN PLACE (not appended) — always current, small.

════════════════ STATE  (current — edit in place) ════════════════

>>> READ Scripts/WORKPLAN_2026-08-19.md FIRST. <<<
    This STATE block is 937 lines and has become a TRANSCRIPT, not a reference — results
    were appended in the order they were discovered, with corrections and withdrawals
    layered on top. That is why it is hard to follow. The WORKPLAN reorganises the same
    material by WHAT YOU NEED TO KNOW: verified / withdrawn / blocked / next, plus the two
    sample budgets that are the commonest source of confusion. Where the two disagree, the
    WORKPLAN wins and STATE should be corrected.
    Use STATE below for detail and provenance on a specific result. Do not read it start to
    finish; that is what the WORKPLAN is for.
    OWED: this block needs compaction to ~150 lines against the file's own SPACE RULE 5
    ("STATE edited IN PLACE — always current, small"). Deferred deliberately — it is a
    judgement-heavy rewrite of the project's memory and should not be done at the end of a
    long session.

sectors: ** ACTIVE WORKSTREAM 2026-08-24/25 — SECTOR CAMPAIGN. Source of truth =
         pipeline/sector_campaign_checklist.yaml + state_*.jsonl + RESUME_NOTES.md in
         data:phase4/qc/sector_campaign/. Branch work/20260824-sectors. **
         DONE: 5 W-E sectors (sectors_v1, ~10% of px); engine --infer-aoi; base2020 queue —
         6 arms (2003s/2006s/2011s/2012s/2018s/2020s) inference VERIFY OK on A100, scored vs
         C-CAP (qc_indep live rows @0.5 = base-model calibration, pre-registered baseline
         operating point), postproc masks 5/6 (2020s mask MISSING — qc VM died mid-copy).
         LIVE 2026-08-26 ~18Z: campaign closed (S24 report done, promotion UNDECIDABLE
         pending noise sigma). Runtime autonomy WORKS: user-token rclone writer mount +
         SA server-side write canary v2 (gen_vm_bootstrap.py; SA has ZERO Drive quota —
         SA-owned uploads silently fail, cost noise campaign v1 ~3.5 A100-h). Branch
         pushed (workflow scope fixed), CI green. gpu = noise queue r1 OK / r2 train
         CRASHED epoch 24 (copystat EIO on rclone mount — fixed common.py 457bc85, both
         VMs hot-patched) / r3 running; watcher chain-launches queue_noise_2021s_b
         (nr2r rerun + r4 + r5) on warm VM at r3 terminal → n=5 sigma → promotion
         verdict. gpu2 = NIR M06 queue; tiling bulk-write fix (71ee388) VALIDATED live:
         2016 retile 26.8 min vs 100+ min FUSE per-file (VERIFY:tile OK, 612 tiles).
         Watchers read status CSVs in phase4/qc ONLY (live nohup invisible server-side
         until close). Buildings: citywide roof matrix 1728/1728 merged; per-year masks
         rebuilt. Champion designations RESOLVED 2026-08-26: Kam DECLINED legacy-era arms
         (pre-workflow provenance) — six contested years stay undesignated; deliverables
         come from post-promotion citywide re-runs under current workflow
         (champion_arms.csv header). BLOCKED ON KAM: main merge. Golden-v2 queue staged for next warm GPU
         (golden_v2_launch_README.md).
ebacklog: ** 2026-08-25 — BEST-PRACTICES REVIEW (Kam-approved plan, D:\tools\...\plans\) **
         3 research passes + 8-agent adversarial verify; every top-8 item corrected; plan =
         E01-E10. LANDED Lane 1: E01 registry year-join+SEEDED fix · E02 atomic .part
         publish (drivefs smoke OWED) · E03 CI gates (push blocked, see above) · E05
         champion_arms.csv + 4 consumers fail-loud (2013 wrong-arm bug fixed) · E06
         label lineage (manifest labels block, lineage.json stamper, Method_Pipeline
         provenance home) · E08 audit corrections (Hygiene #16 false premise; new #18-20).
         PENDING: E04 cost layers (agent) · E07 golden gate v1 (agent) · E09/E10 + Lane 3
         (noise arm first GPU ask post-fullext). KEY REVERSALS: no output overlap exists
         (blending/stride REJECTED); train resume economics inverted (0.7 GPU-min lost ever
         vs 3+ GPU-h in tile/inference → E10 inference resume is the payer).
overhaul: ** ACTIVE WORKSTREAM 2026-08-20 — OPTION A OVERHAUL. PLAN = Scripts/OVERHAUL_PLAN_2026-08-20.md **
         Adopted by Kam. Re-plumb planes: code → normal git repo on D: + GitHub live remote; Colab
         clones code; Drive = data lake ONLY.
         DONE 2026-08-20: P0 bookkeeping · P1 backup STARTED (robocopy Drive→D:\edmonds-pipeline\
         backup, ~310GB after trims) · P2 clone at D:\edmonds-pipeline\treedata (CANONICAL — open
         sessions THERE; Drive Scripts now FROZEN fallback) · P3 reorg (pipeline/qc/scratch/archive,
         299 renames, all gates green) · P4 run-protection (verified writes, tile staging, per-step
         VERIFY) · P5 cockpit notebook · P6 manifests+seeds+queue-as-data · P7 harvest + overwrite gate.
         ** P1 COMPLETE 2026-08-21 15:53 ** — ~313GB on D:\edmonds-pipeline\backup, every dir
         sha256-manifested (mirror_sync.py MANIFEST.sha256) + size-verified 0 mismatches:
         phase3 1871f/112.7GB (prob_2020 102GiB byte-verified, 5h37m copy); models 58f/35GB;
         masks 61f/29GB; Full_Image 17f/130.4GB (all 4 CoE orthos BYTE-VERIFIED vs source —
         2017 48,377,405,327B exact); crowns/polygons/parquets/eval/runs/small-sources.
         Trims per plan: sem_latest twins, crops, phase5, KingCo(75GB raw, flagged), upsample
         skipped; dedupe vs D:\Imagery. Battle notes: Google download-throttle hit twice after
         ~300GB pulled (measured 390kB/s vs 5MB/s healthy; recovers on rolling window); Drive
         client wedged once (restart fixed); 2020/2022/2024 landed via Kam's browser downloads
         (byte-verified), 2017 via robocopy. One benign skip: USGS M2M Documentation.gdoc
         (cloud-native pointer, uncopyable). GitHub pushed through 4320839; 62016ea+ unpushed.
         DEFERRED to next session (explicitly): registry generator (needs real run manifests —
         first appears at the canary), QC provenance headers, P9 sync mode in mirror_sync.py.
         DRIVE DETACHED (Kam ran the rm, 2026-08-20) — G: has no .git; D: repo is the only git.
         D2 DECIDED (Kam "Adopt", 2026-08-20): mid-height woody COUNTS as canopy, own interpreter
         class, reversible — recorded in canopy_definition_PROPOSAL.md + WORKPLAN §3. D1/D3-D6 open.
         KAM OWES: git push github main --tags · PAT → Colab Secrets · canary +
         queue_2024_finish.yaml + queue3.yaml GPU windows.
         2024 inference DEAD (2.5MB stub, set aside .stub-20260819) — queue_2024_finish.yaml re-runs it.
         DEFERRED: registry-generator from manifests, QC-provenance headers, pipeline_status.py,
         watch_queue.py, dag.yaml (P8), mirror_sync.py (P9), P10 cleanups.
         Read the plan file; do not restate it here.
         ** 2026-08-22 01:50Z RESUME (local 08-21 eve) ** — colab-mcp: last session's LOCAL-scope entry (`uvx` by name) never
         connected — uvx not on PATH; re-registered USER scope w/ absolute uvx.exe path 02:10Z; CONNECTED
         02:20Z after cache warm-up; read-only tool inventory owed in a fresh session (see LOG). 2024-finish + queue3 runtimes (both cloned 57bc07b = pre-P11.1 clobber-prone status
         writer) SILENT since 01:12Z: Drive API shows no write from either after 01:12:52Z / 01:03:07Z; cause
         NOT established (throttle suspected — measured 08-21 — but unproven; wedged Drive mount or dead VMs fit too). Nothing newly
         VERIFIED → nothing scored. main PUSHED through b1b8516 == github/main (P11.4 prereqs incl. lock/ceiling/resume fixes +
         queue_A/queue_B are on GitHub). work/p11-5-autonomy PUSHED, NOT merged — launch from it via cockpit cell 1
         BRANCH, or Kam merges to main first. 2013 citywide .7422
         row is live=0 in qc_indep_report.csv (re-score owed; see LOG). 02:05Z Kam STOPPED both runtimes — nothing landed; stale RUNNING rows closed
         INTERRUPTED + harvested; monitor stopped. NO relaunch tonight — Kam: wait for the agentic MCP path and launch the
         queues in PARALLEL (P11.4). Prereqs LANDED 2026-08-22 (staging lock,
         ceilings, resume fix, per-queue logs, queue_A_2024_2017 / queue_B_2019_2022, runbook = OVERHAUL_PLAN P11);
         MCP inventory done (1 gate tool; notebook tools unlock after the browser connect); colab-mcp +
         colab-mcp-b both CONNECTED 03:40Z (runtime B possible). ** P11.5 RULED 03:55Z (Kam): ** first
         launches ask-first; crash-recovery AUTONOMOUS (fix branch -> small-GPU canary -> A100 rerun; no cap
         tonight; every launch logged); main PROTECTED (deny rules); A100 default; loop backoff 10->60 min.
         Prep on branch work/p11-5-autonomy (cockpit BRANCH + nvidia-smi, manifest git_branch/gpu, docs).
         ALLOWLIST INSTALLED 2026-08-22 in user settings (20 allow / 28 deny; verified: `git push github main`
         DENIED in-session, hot-reload); stray home-dir allows removed; colab-mcp + colab-mcp-b CONNECTED.
         PowerShell GAP CLOSED for this session (Kam): 28 PowerShell(...) deny twins appended to user settings
         (deny = 56, allow = 20); `git push github main` via the PowerShell tool DENIED. Kam: twins are the
         right fix -> P11.5 block CANONICALIZED to the live 56-rule list (OVERHAUL_PLAN + plan file).
         ** MCP TOOL INVENTORY 2026-08-22 (prompt B step 2, Kam "yes both") ** both open_colab_browser_connection
         calls -> true; each server then proxies 7 notebook tools: get_cells (read; optional outputs),
         add_code_cell / add_text_cell / update_cell / move_cell / delete_cell (edit), run_code_cell (EXECUTE —
         returns the output) -> the MCP path CAN run cells, so cell 3 launches and crash-recovery relaunches
         are ACTIONS. NO tool sets the runtime type/GPU, opens a notebook file, or lists runtimes: each tab
         opened at colab.research.google.com/notebooks/empty.ipynb (1 empty code cell, id lIYdn1woOS1n on
         both); the GPU tier is chosen by Kam in the tab UI (Runtime > Change runtime type) and confirmed by
         cell 2 nvidia-smi; cockpit cells are inserted through add_code_cell. Colab Secrets (the PAT) need
         the per-notebook grant click in the browser on first use.
         STEP 3 ZERO-GPU CHECK 2026-08-22 (CPU runtime, cells 1-2 inserted via the MCP tools, BRANCH =
         work/p11-5-autonomy): tab A clone at 2bf0835, requirements installed, catalog 18/18 OK (orphan
         2012_king_rgb.tif noted as before), --dry-run queue_A = 10 commands (2024 + 2017); tab B dry-run
         queue_B = 10 commands (2019 + 2022). ** FINDING: both tabs share ONE runtime ** — tab B's cell 1
         printed "Drive already mounted" + "repo already cloned" (same empty.ipynb under one account = one
         session). Two tabs != two runtimes; tab B must be a DIFFERENT notebook to get its own VM, and the
         MCP binding is to the page (URL fragment mcpProxyToken/mcpProxyPort), so re-pointing tab B needs
         Kam in the browser (or human-paste for B, the runbook's fallback). No runtime-type tool: Kam sets
         A100 per tab (Runtime > Change runtime type; the VM restarts -> cells 1-2 re-run on the GPU VM).
         NIT: phase4_train_queue.py:603 prints "qc\train_queue_status_*.csv" (display literal only; the
         real path, line 635, is a pathlib join) — cosmetic, not fixed tonight.
         ** P11.6 ADOPTED (Kam, 2026-08-22): ** GPU work runs HEADLESS via google-colab-cli
         (colab new -s A --gpu A100 / colab exec / colab stop); the MCP tabs are FALLBACK (both server
         instances open the same scratch notebook -> ONE shared runtime). Probed on CPU sessions: auth
         once, exec + detached nohup + named GPU VMs are all agent-drivable; drivemount is KAM's terminal,
         once per VM (per-VM Drive consent; verified NOT to carry to a new VM). Machine-local CLI fixes
         (termios stub, jupyter-kernel-client<1.0 pin), the generator pipeline/colab_cli_vmgen.py, the
         flow and the permission notes = OVERHAUL_PLAN P11.6.
         ** MOUNT TEST 2026-08-22 15:22Z: FAILED, CAUSE FOUND (D: session). ** colab new -s mounttest (CPU) READY;
         Kam ran `colab drivemount -s mounttest` in PowerShell: URL printed, consent granted, then
         `ValueError: mount failed` (google/colab/drive.py:272, the drive-timeout branch) after 120 s with NO
         '[colab] Authorizing VM...' line. ROOT CAUSE = the CLI, not Google: colab_cli/commands/automation.py
         drivefs_hook reads the Enter via open('/dev/tty'), which does not exist on Windows ->
         FileNotFoundError, swallowed by runtime.py:81 (logging.debug: colab.log 08:22:48 'Error in
         colab_request hook: [Errno 2] No such file or directory: /dev/tty') -> the credentials-propagation
         POST (dryrun=false) and the kernel input_reply never happen -> DriveFS times out. Same failure is in
         the other session's history/probe2.jsonl. So 'works in Kam's terminal' was false for the SAME reason
         the agent shell fails: both are Windows. FIX CANDIDATE (machine-local, same class as the termios
         stub): replace the /dev/tty readline with a stdin read when /dev/tty is absent (Kam still consents
         in the browser and presses Enter) -> retry on mounttest -> agent-side exec listing. NO A100 until
         the mount is proven. Fallbacks: MCP-tab path, rclone/service-account mount. mounttest left READY.
         ** MOUNT TEST PASSED 15:4xZ after fix #4 (Kam: "patch") ** — automation.py /dev/tty read wrapped in
         try/except OSError -> sys.stdin.readline() (backup automation.py.orig; documented OVERHAUL_PLAN P11.6
         fix 4). Kam's PowerShell drivemount -> Mounted; agent exec on the SAME VM fb2becee74e3 listed treedata
         (35 entries, phase4/locks + logs present). Both unknowns proven. mounttest STOPPED. GATE OPEN for A100.
         PERMISSIONS LOOSENED (Kam: policy C stays; back off rules for harness dev): +18 allow (read-only git,
         shell readers, cp/mkdir, Edit on the jobs scratchpad) -> user settings 42 allow / 56 deny; doc
         blocks re-canonicalized from the live file. No rm rule (py does deletions); no VAR= prefixes.
         ** LAUNCH A 2026-08-22 15:55:52Z (Kam: "Yes" 15:5xZ) ** colab session A = A100-SXM4-40GB, 1 VM
         (created 15:53:22Z, billing from then); Kam drivemount -s A OK (fix #4); bootstrap at cce075f on
         work/p11-5-autonomy, BOOTSTRAP_DONE; vm_launch -> pid 1881, log
         phase4/logs/train_queue_nohup_queue_A_2024_2017_20260822T155552Z.log; header shows the A100.
         Expected ~5 h (2024 inference-only resume, then 2017 full path). Success = VERIFY rows in
         phase4/qc/train_queue_status_queue_A_2024_2017_<ts>.csv + job-end VERIFY; first health tock =
         2024 ortho staging line within ~25 min. Token scripts deleted. Cost line: Colab's posted A100
         rate x ~5 h (rate not verified in-session). colab stop -s A when the job-end VERIFY lands.
         ** LAUNCH B 2026-08-22 16:03:28Z (Kam: "Launch B") ** colab session B = A100-SXM4-40GB, 1 VM (created
         15:59:21Z); Kam drivemount -s B OK; bootstrap at f148447 on work/p11-5-autonomy, BOOTSTRAP_DONE;
         vm_launch -> pid 1712, log phase4/logs/train_queue_nohup_queue_B_2019_2022_20260822T160328Z.log;
         7.5 min after A (lock window OK). Expected ~4 h (2019 from tile, then 2022 full path). Success =
         VERIFY rows in train_queue_status_queue_B_2019_2022_<ts>.csv + job-end VERIFY. Token scripts
         deleted. Two A100s live = the P11 cap. `colab url -s A` gives a browser window onto a CLI VM
         (Kam: 'runtime not started' when opened — the page is a viewer; the nohup queue is independent).
         HARNESS: user settings env PYTHONUTF8=1 + PYTHONIOENCODING=utf-8 (colab.exe's cp1252 stdout
         crashed on the manifest arrow in a log tail; env avoids VAR= prefixes). Probes sanitize to ASCII.
         ** STEP 6 16:05Z: BOTH HEALTHY, MONITOR ARMED, /loop HANDED TO KAM. ** A: pid 1881 + engine pid 1889
         (2024 inference), 2024_coe_rgb.tif staging 16.0/26.9 GB at 16:04Z (~33 MB/s -> tock ~16:10Z), GPU
         idle as expected. B: pid 1712 + engine 1716 (2019 tile), log says 'staging lock held by
         ba5d4bc9133a:1889 for 2024_coe_rgb.tif; waiting for 2019_king_rgb.tif (poll 30s)' = FIRST IN-THE-WILD
         PROOF of the P11.4 cross-runtime staging lock. Monitor = per-VM probe_live (procs, GPU, scratch, log
         tails, ASCII-sanitized) via colab exec + local G: reads of train_queue_status_*.csv, run manifests,
         masks, nohup logs + lock WARNING grep + colab status/log. Loop prompt = plan file prompt C.
         `colab url -s A` DOES NOT attach the Colab UI to a CLI VM: the page opened idle; 'Connect to a hosted
         runtime' allocated a NEW CPU runtime (hostname 4476d385f348 != A's ba5d4bc9133a; appears as a [?]
         orphan m-s-kkb-usc1a0-14k5a40t66s1b, no compute units, Kam deletes it from the tab; CLI cannot stop
         [?] entries by name). Watching = colab exec probes / colab ls / log tails, not a browser.
         ** LOCAL DASHBOARD BUILT 16:23Z (Kam: 'a local interface that tracks those runtimes'): **
         qc/runtime_dashboard.py — stdlib http.server on 127.0.0.1:8765; per-session card (GPU tier/util,
         queue, per-job step chips from the merged status CSVs incl. VERIFY:<step>, live tqdm bar + ETA,
         elapsed vs STEP_TIMEOUT_MIN, staging/lock line, scratch dir, log tail, flags). Fresh data = a
         VM-side probe via `colab exec` every 60 s (ps, nvidia-smi, scratch, the VM's OWN log tail + whole-
         file scan for the last step/lock line); G: for CSVs/manifests/locks every 15 s (the G: mirror of a
         growing log lags minutes). Read-only, no torch on the VM. Kam runs it in his own terminal:
         py -3.12 qc/runtime_dashboard.py --sessions A,B --open. Snapshot 16:23Z: A 2024 inference 7%
         (31.9k/481k, 39 tile/s, ETA 3:10 -> ~19:35Z, GPU 37%); B 2019 tile OK + VERIFY:tile OK (done
         ~16:18Z incl. 7.1 min lock wait), train started 16:18:03Z (GPU warming). No flags.
         ** LOST-SESSION INCIDENT + RECOVERY 16:54-17:00Z (loop, autonomous). ** Session A disappeared from
         sessions.json while its A100 kept running (probe: 'Session A not found'; colab sessions showed a
         [?] orphan). CAUSE: common.sync_sessions() prunes any local session whose endpoint is missing
         from the CURRENT list_assignments() (regions differ: A asia-southeast1, B us-central1); a 401/404
         exec also triggers execution.py's 'appears to be lost. Cleaning up.' — B hit that minutes later.
         A pruned VM BILLS but cannot be stopped by name. FIX (new): qc/colab_readopt.py rebuilds the entry
         from list_assignments() (fresh url+token per assignment) -> A re-adopted as A2, B as B2, both
         queues verified untouched (A2 pid 1889 2024 inference 25%; B2 pid 15090 2019 inference 14%).
         Dashboard hardened: reads sessions.json directly (never `colab sessions`, which prunes) and flags
         any live assignment with no local name as a billing orphan (the CPU [?] from the browser tab shows
         up that way now). LOOP NAMES ARE NOW A2/B2. Doc: OVERHAUL_PLAN P11.6 'Lost-session hazard'.
         ** VM A TERMINATED ~17:08Z — 2024 inference LOST (no raster). ** Kam ended the CPU [?] orphan in the
         browser; A2's A100 assignment vanished at the same moment (list_assignments now shows only B2), so
         both went together — most likely both were ended from Colab's own session manager, which lists
         CLI VMs as unnamed runtimes. State at death: 2024 inference ~39% of 481,068 tiles after ~1.2 h of
         A100 (15:53-17:08Z); the prob raster existed only in /content/phase4_scratch (472 MB at 16:57Z), so
         the verified-write path left NOTHING on Drive - no stub, no partial. Stale RUNNING row closed by
         local audit -> INTERRUPTED exit=vm_gone (resume already treats RUNNING as not-OK). Queue A's other
         job (2017) never started. B2 UNAFFECTED: 2019 inference 39% at 17:15Z, ETA ~17:55Z. Per the loop
         rule a DEAD VM needs Kam (fresh colab new + drivemount), so the relaunch of queue A is an ASK, not
         autonomous. MEASURED while diagnosing: inference is INPUT-BOUND on the A100 - nvidia-smi dmon over
         20 s on B2 read sm% 0,0,47,0,28,56,0,...,77,7,0 (mean 16%, peak 79%, 12/20 point samples exactly 0)
         with the engine at 105% CPU/55 threads and 21 GB VRAM held; ~34-40 tile/s is the same order as the
         L4-era estimate, i.e. the A100 buys little on inference (it earns its keep on train). Dashboard now
         samples utilisation (15 reads over 3 s, mean/peak) instead of one instantaneous read.
         ** RELAUNCH A 2026-08-22 17:20:57Z (Kam: "yes") ** colab session A3 = A100-SXM4-40GB (created ~17:19Z,
         host 96266dad3f53), Kam drivemount OK, bootstrap at d2d6e65 on work/p11-5-autonomy, BOOTSTRAP_DONE,
         vm_launch -> pid 8496, log train_queue_nohup_queue_A_2024_2017_20260822T172057Z.log. Resume re-runs
         2024 inference from scratch (~3 h; the lost run left nothing) then 2017 full path (~5 h) = ~8 h A100.
         Two A100s live again (A3 + B2) = the P11 cap. RULE RESTATED to Kam: end VMs with colab stop -s NAME,
         never from the Colab UI session manager (that is what took A down with the CPU orphan).
         ** B2 ALSO RECLAIMED ~17:22Z — ROOT CAUSE FOUND (both losses, one mechanism). ** prune_session()
         KILLS the session's keep-alive daemon, and that daemon is the only caller of
         keep_alive_assignment() = the idle-timer refresh for the assignment. No heartbeat -> Colab
         reclaims the VM in ~15-25 min EVEN MID-COMPUTE. A: pruned 16:54, dead 17:08 (2024 inference 39%).
         B: cleaned up on a 401 at 16:57, re-adopted 16:59 (name restored, daemon NOT), dead ~17:22 (2019
         inference 40%). So Kam ending the CPU orphan did NOT kill A - the sequence only looked that way.
         Neither wrote to Drive (verified-write keeps the raster in /content until the step ends); 2019's
         labels/tile/train/evaluate VERIFY:OK rows STAND, so a relaunch resumes at inference (~1 h) while
         2024 needs its full ~3 h again. Both stale RUNNING rows closed by local audit (exit=vm_gone /
         vm_reclaimed). FIXES: colab_readopt.py now respawns the daemon on re-adoption; the dashboard
         flags a dead keep-alive pid (~20 min of warning); GPU util sampled in a python loop (this
         driver rejects -lms/-l alongside --query-gpu); hard-fail flags scoped to the current launch file.
         A3 is healthy: daemon pid 4504 alive, 2024 ortho staging 11.6/26.9 GB at 17:29Z.
         ** RELAUNCH B 2026-08-22 17:33:55Z (Kam: "Remount B") ** colab session B3 = A100-SXM4-40GB (host
         dff1f387a881), keep-alive pid 38184 (A3: 4504 — both heartbeating, the reclaim mechanism is closed);
         Kam drivemount OK, bootstrap at bcdd4c6 on work/p11-5-autonomy, BOOTSTRAP_DONE, vm_launch -> pid 5005,
         log train_queue_nohup_queue_B_2019_2022_20260822T173355Z.log. Dry-run confirms the resume: 2019 runs
         INFERENCE ONLY (~1 h; its labels/tile/train/evaluate VERIFY:OK stand), then 2022 full path (~5.5 h).
         Two A100s live (A3 2024+2017 ~8 h, B3 2019+2022 ~6.5 h).
         ** INFERENCE THROUGHPUT (Kam: "aiming for 85% GPU utilisation ... maximize value per GPU hour") **
         MEASURED the bottleneck on B3 (CPU-only, no GPU risk): the serial read path is 16.5 ms/tile, of
         which ~12 ms is the PER-TILE CHM WARP (read_hillshade_chip reprojects for every tile); 8 threads
         take it to 3.1 ms/tile (rasterio/GDAL release the GIL). The old loop ALSO ran numpy exp() over
         8.4M fp32 values per 32-tile batch on the same thread that fed the GPU. => GPU was starved, not
         slow: ~40 tile/s at 14-28% mean util.
         FIX on fix/20260822-inference-throughput: (1) ThreadPoolExecutor(8) tile prefetch with bounded
         look-ahead, consumed in submission order so write order is unchanged (EDMONDS_INFER_WORKERS=1
         restores the serial path); (2) sigmoid + centre crop + uint8 quantisation ON THE GPU (~5x less
         host traffic, no numpy exp); (3) cudnn.benchmark (constant shapes). Bench on the real VM+model,
         640 tiles: 16.5 -> 108.2 tile/s (x6.55), GPU util 36% -> 73% mean / 100% peak, output
         BYTE-IDENTICAL (max|diff|=0 over 41.9M px).
         ** THEN IT FAILED IN PRODUCTION (17:55Z, both queues) ** 'IReadBlock failed at X offset 0, Y
         offset 0: TIFFReadEncodedTile() failed' — a GDAL DatasetReader is NOT thread-safe and the pool
         shared one ortho handle. The benchmark missed it because it read an INTERIOR block; production
         starts at the raster origin where every thread hits the same first blocks. Lesson: a throughput
         benchmark must reproduce the production access pattern, not just the code path.
         FIXED (84c935a): one handle per reader thread for BOTH the ortho and the cached hillshade master
         (_HS_TLS thread-local; _HILLSHADE_DS now holds the staged PATH), closed in-thread at teardown.
         Re-verified from (0,0) with 8 threads: no failure, byte-identical, 46 -> 118 tile/s on a VM that
         was also running a tile step. Gates: py_compile + preflight + smoke green (smoke does NOT cover
         step_inference — that is why the equivalence bench exists).
         COST OF THE MISS: 2024 inference (11%, ~35 min) and 2019 inference (22%) were stopped for the
         relaunch (rows INTERRUPTED exit=perf_relaunch) and both then FAILED in ~0.2 min on the thread
         bug; the queues moved on to 2017 tile / 2022 tile, which are CPU steps and are running fine on
         the fixed code. 2019 inference carries a FAIL row and needs a re-run; 2024 inference likewise.
         Both VMs re-bootstrapped to 84c935a WITHOUT interrupting the tile steps (the shim re-copies
         phase4seg per step subprocess, so the next step picks up the new code).
         ** THIRD VM LOSS 18:20Z — A3 GONE, ROOT CAUSE COMPLETE. ** At the 18:43Z loop check both names
         had vanished from sessions.json and only ONE assignment was live. Forensics from colab.log:
         18:19:55Z GET/POST /api/kernels on A3's endpoint returned 404, 18:31:41Z the same on B3's.
         execution.py deletes a session on ANY such transient error ('appears to be lost. Cleaning up.')
         -> entry gone + keep-alive daemon killed -> Colab reclaimed A3 ~15-25 min later, mid tile step
         (2017, ~20 min into staging the 48 GB ortho behind the staging lock; nothing on Drive, row
         closed INTERRUPTED exit=vm_reclaimed). B3 survived only because I re-adopted it in time (now
         B4, daemon pid 39108, 2022 train 31 min in, GPU 54%/91% - the threaded build is healthy).
         SECOND HALF OF THE CAUSE: the stored runtime-proxy token lives EXACTLY 1 h (measured: issued
         18:43:57Z, exp 19:43:57Z), so any session older than an hour 401s on its next exec and prunes
         itself - a per-minute monitoring loop GUARANTEES this on runs longer than an hour. That is why
         it happened three times tonight and never during the short probes.
         FIX (35e77f3): qc/colab_readopt.py --heal = re-adopt orphans + refresh tokens with >25 min
         margin + respawn dead daemons; the dashboard runs it every 2 min BEFORE reading the store, and
         shows what it did. Kam can run it by hand any time; it is a no-op when healthy.
         OPEN: queue A (2017 tile onward + the 2024 inference re-run) needs a NEW VM = Kam's drivemount
         = an ASK. Queue B continues on B4 (2022 train -> evaluate -> inference, then the staged
         queue_2019_inference.yaml).
         ** THREADED INFERENCE VALIDATED IN PRODUCTION 19:13Z: ** 2022 citywide (481,068 tiles, 5 cm grid) at
         122.3 tile/s, GPU 63% mean / 79% peak, 30% in 20 min -> ~66 min total vs ~3.3 h on the serial path
         (~3x end-to-end; the x6.55 bench compared against a serial run that was itself contending). Byte
         equivalence was proven before the deploy. NEXT LEVER if more is wanted: the per-tile CHM warp is
         12 of the 16.5 ms serial read cost - pre-warping the CHM onto each ortho grid once per year would
         remove it and should take GPU util past 85%; EDMONDS_INFER_WORKERS>8 did NOT help the read path in
         the bench (326 tile/s at 8 vs 305 at 12).
         ** RELAUNCH A 2026-08-22 19:32:10Z (Kam: "Start A") ** colab session A5 = A100-SXM4-40GB (host
         1b6ab59ed0dc, keep-alive pid 9636); FIRST drivemount attempt failed with "Error propagating: 400"
         (the auth URL's state token had gone stale between print and Enter) — the retry, approved promptly,
         worked. Bootstrap at 87391aa on fix/20260822-inference-throughput, BOOTSTRAP_DONE, vm_launch -> pid
         3562, log train_queue_nohup_queue_A_2024_2017_20260822T193210Z.log. Queue A resumes 2017 at TILE
         (its 18:20Z attempt died with the VM) then train/evaluate/inference; the 2024 inference re-run
         follows via queue_2024_inference.yaml. Two A100s live again (A5 + B4).
         DRIVEMOUNT NOTE for the runbook: approve the URL within ~a minute and press Enter promptly; a slow
         approval yields "Error propagating: 400" and the mount silently does not happen (verify with a
         colab exec listing before spending GPU).
         ** P6 CLOSED (plan work done while the queues ran): pipeline/registry_from_manifests.py **
         Generates run_registry.csv rows from phase4/runs/*/manifest.json, joining held-out metrics (the
         eval report's OVERALL row, incl. its channels tag = the rgb+chm scoring gate), honest live=1
         numbers (qc_indep_report), and per-attempt outcome/timing from the merged status CSVs; artifact
         paths recorded only when the file exists. APPEND-ONLY: the 24 hand-written rows are untouched
         (verified 20 insertions / 0 deletions; a second run reports 0 new). TWO CORRECTNESS FIXES found
         in test: (1) each attempt must pair with its OWN status row by timestamp AND be bounded by the
         next attempt's start - otherwise the 01:03 tile run inherited the 16:18 re-run's OK and all five
         2024 inference attempts showed the newest state; (2) in-flight RUNNING attempts are skipped
         (append-only could never correct them) unless --include-running. Backfilled 20 rows including
         every failure of tonight with its real cause. ALSO FIXED (advisor caught it): runtime_dashboard
         --once did NOT heal before probing, so an hourly check would 401 on the 1 h token and prune/kill
         the VM it was checking on - heal now runs first on that path too.
         ** 2022 CITYWIDE DONE 19:58:50Z (3927 MB, valid 74.7%) - and its WEAK_CALIBRATION VERIFY was a
         FALSE ALARM IN THE CHECK. ** _check_prob_raster read a fixed 1200-ROW overview, which is ~1:45 of a
         10 cm raster but ~1:177 of a 5 cm CoE raster (211,968 rows), so the 5 cm years sample ~15x sparser
         and miss their rare high-confidence pixels. Measured on the SAME raster: max 0.728 at 1200 rows,
         1.000 at 4800 rows, 1.000 on a full block-wise pass. 2022 was the first 5 cm citywide raster to
         reach this check; 2024 and 2017 would have repeated it. FIX (this branch): sample a fixed 4M-PIXEL
         budget (floor 1200 rows) so density is comparable across tiers, and report p99.9 + the sample shape
         beside maxprob - max is one pixel and hides the tail. Re-check now returns OK maxprob=0.909
         p99.9=0.665. Corrected VERIFY rows appended by audit; the original rows stay as history.
         REAL FINDING KEPT: 2022's confidence IS compressed - full-raster histogram p50 0.087, p99 0.614,
         p99.9 0.665, only 0.014% of valid pixels >0.7 and 1,627 >0.9 out of 23.5e9. Discrimination is fine
         (held-out IoU .73 rgb+chm); it is the upper tail that is thin, which matters when the scorer
         searches an operating threshold. 23.7% of valid pixels exceed 0.5 - a plausible canopy fraction.
         B4 relaunched 20:01:01Z on queue_2019_inference.yaml (pid 46969, ~15-20 min) so it did not idle.
         ** 2019 CITYWIDE DONE 20:19:22Z: inference OK in 18.3 min ** (vs ~1 h serial), VERIFY:inference OK
         2289 MB valid=89.6% maxprob=0.965 - a healthy tail, unlike 2022. B4 had nothing left queued ->
         colab stop -s B4 at 20:20Z (only A5 still live, on 2024 then 2017). SCORING: 2022 started locally
         against ccap_2021_hires_lc.tif; the gate is satisfied - the scorer printed "deployed threshold
         0.4988 (channels=rgb+chm)". 2019 scores next, serially, so two multi-GB readers do not fight for
         the disk.
         ** 2024 CITYWIDE DONE 20:46:12Z: ** VERIFY OK 4652 MB valid=100.0% maxprob=0.783 (A5 still on the
         pre-fix checker, so this passed the old max<0.75 rule by a whisker - under the fixed sampler it is
         comfortably OK). A5 moves to 2017 (tile -> train -> evaluate -> inference).
         ** FIRST HONEST NUMBER OF THE NIGHT - 2022 (independent, live=1, thresh 0.4988, rgb+chm gate met) **
         PRIMARY forest_wetland: recall .6818 precision .8012, grass_reject .9256, ref_canopy 27.85%.
         forest_only .6797/.7891; forest_wetland_scrub .6686/.8186. Per-surface: forest .6797, wetland
         .8578, scrub .3542 (the usual scrub weakness); FP-rates grass .0744, developed .0607, water .0397,
         emergent_wetland .5558 (the one bad non-canopy group). Threshold sweep: recall climbs to .7355 at
         0.20 for precision .7677 - i.e. ~5 pp of recall is available for ~3 pp of precision, consistent
         with the thin upper tail measured in the calibration check. Sits inside the series range
         (.55-.80).
         ** 2019 HONEST (independent, live=1, thresh 0.332, gate met: channels=rgb+chm) ** PRIMARY
         forest_wetland: recall .6346 precision .8242, grass_reject .9291, ref_canopy 26.81%.
         forest_only .6314/.8094; forest_wetland_scrub .6259/.8464. Per-surface FP-rates: grass .0709,
         developed .0429, water .0159, emergent_wetland .4929 (same weak group as 2022); scrub recall
         .4138. Threshold sweep: .6772/.8084 at 0.20 vs .5762/.8410 at 0.50 - about 12 pp of recall for
         3 pp of precision across that span, a steeper trade than 2022's. NOTE the deployed thresholds
         differ by year (2019 0.332 vs 2022 0.4988), so the two recalls are NOT read side by side as a
         model comparison - they are each that year's deployed operating point.
         2024 scoring started next. Kam's field note (2026-08-22, recorded, no action taken): of the five
         curated negative sites only PARKING and WATER are clean negatives; the others are contaminated,
         and even Parking holds a sliver of an unnoticed street tree. Relevant to the standing
         under-prediction question - a contaminated negative teaches the model to suppress real canopy.
         Session prompts: D:\tools\claude-config\plans\because-we-are-not-parallel-codd.md. NEXT SESSION =
         prompt B, CLI edition: first launch of each queue ask-first; crash-recovery per P11.5 = push the
         fix branch + re-exec on the LIVE VM (a live VM keeps its Drive mount).
provenance: ** PIXEL SIZE + DATE SHOT, ONE HOME (2026-08-23) ** = Scripts/qc/imagery_pixelsize_and_date.csv (29 rows:
         22 held imagery + 7 reference/context; catalogue sheet Pixel_Size_And_Date; evidence qc/imagery_date_evidence/;
         builder scratch/imagery_pixelsize_date_build.py, sheet-adder _sheet.py, quote gate _quote_gate.py = 0 misses
         vs fetched pages). Grades: 12 MEASURED, 6 PUBLISHED, 3 INFERRED (2020 ANCHOR, 2024, 2016s), 1 NOT FOUND (2002).
         Branch work/20260823-pixelsize-date (Kam merges). Headlines: 2017_coe = SAME ORTHOMOSAIC as 2017_king ->
         2017-05-04..05-10 MEASURED; 2000 -> 2000-06-26 (Wayback flight-date graphic); 2022_coe identity MEASURED
         (MrSID twin with Everett) -> PUBLISHED; 2020 ANCHOR still a WINDOW (04-25..07-13) but CONSISTENT WITH ONE
         PASS (shadow geometry, 10 sites); 2016_snoh native 1 ft (30.5 cm), date INFERRED Aug 12 2016 morning;
         in-file metadata NULL on all 33 rasters. OPEN: anchor pin = PRR to Snohomish DoIT (RFP 1166-18-PCR /
         PB-19-14BC) or CONNECTExplorer screenshot; 2002 Edmonds date (EarthExplorer M2M); KAM DECISION: C-CAP v2
         Ecopia ML-use clause ('testing, evaluating ... machine learning') vs our evaluation use. Hazard: a SECOND
         2020 acquisition (Hexagon 2020-08-27/28) exists over Edmonds - never borrow its date.
acquire: ** IMAGERY ACQUISITION CAMPAIGN (2026-08-23, ACTIVE) ** — engine pipeline/acquire_imagery.py (plan/probe/
         pilot/fetch/status/assemble/mosaic/clip/verify/manifest/mirror/register; per-chunk jsonl ledger; gap report;
         snapped grid + nearest; --via download = original source tiles) + qc/imagery_measure.py (decide(): common-grid
         effective + HF ratio) + manifest pipeline/imagery_acquisition_manifest.json. Branch work/20260823-acquire.
         LANDED batches 1-2 (9 rasters): REPLACES 2016 (S16 native-1ft full extent) + 2002 (U02 = 39 ORIGINAL USGS HRO
         tiles via WAGDA Download capability — common-grid 56 vs 91 cm, HF 1.54, no JPEG signature); COMPLEMENTS
         2015n/2017n/2021n (NAIP), 2017s/2019s (county HXIP Aug/Oct 1-ft NIR), M18 (marsh drone 2.5 cm, band4=ALPHA →
         _rgb, display-cache waiver). CC16 closed ZERO-download (vsicurl header+3 windows == held _snohfull). NIR
         acquisitions 4 → 8. Records: IMAGERY_FACTS §10.1-10.6; table 37 rows quote-gate 0 misses; catalog_check 23/23
         + SUPERSEDED_FILES. Ops facts: NOAA blob hosts cap ~1.3-2 MB/s/client regardless of streams; snoco ignores
         compression=LZ77, 15000-px strips → HTTP 500; WAGDA uncapped 8.3 MB/s. BATCH 3 LANDED: S21 REPLACE #3
         (2021_snoh_6in_rgbi.tif 10.76 GB, coverage 100 vs 39.5%, common-grid 20.05 vs 21.09 cm HF 1.432 — old serving
         path blurred it; NIR real; reg 0.006 px; 875 chunks 0 fail) + S15 COMPLEMENT key 2015s (3-band, band4=ALPHA
         both renderings; 2015-08-07 15:31 sortie PUBLISHED). CC21 CLOSED: landed 1,432,994,003 B exact → clip
         ccap_2021_hires_lc_pugetfull.tif EPSG:5070 (v2 CONUS = Albers, byte-equality impossible) → gate 99.794%
         class agreement on held 26910 grid, diffs = symmetric boundary jitter → PATCH verdict; file QUARANTINED
         until NOAA ask (d) answered, read by no script (IMAGERY_FACTS §10.9). Table 39 rows gate 0 misses; check
         24/24 + ADOPTED_NON_YEAR heading (M18). Kam EMPTIED Drive trash (msg 2026-08-23 ~12:45); batch-3 + CC21
         mirrors LANDED size-exact (S21+S15 -> Pipeline Imagery; CC21 raster+clip -> Full_Image/CCAP/_quarantine/,
         NEVER Pipeline Imagery); Drive free 41.5 GB, quota reconciliation may still be running — later mirrors
         re-check the 25 GB floor themselves. BATCH 4 + N23f LANDED: S18 = the 2018 gap year
         (2018_snoh_6in_rgbi.tif 11.47 GB, HXIP 6-in flown 2018-08-07 PUBLISHED, NIR NDVI p90 .713, eff 20.9 cm,
         key 2018s) + pan years S90/S98/S01 (NOT FOUND dates; 1998 = DNR scan per keyProperties leak; S01 eff 105 cm
         scanned film, 14 water chunks accepted after chunkmap eyeball; all three ADOPTED_NON_YEAR, never tiled —
         1936/1998 King pans moved there too; orphans now exactly 2012_king + 2017_king). N23f = REPLACE #4
         (2023_naip_60cm_rgbi.tif from the 8 original Azure DOQQs: coverage 100 vs 67%, HF 1.406; all quads
         2023-10-07 confirms held date; 2023n flipped). Engine fix c95b992: HTTP 4xx = per-file failure never
         retried/never a crash (N19f 404 exposed it — Azure 2019 folder is wa_60cm_2019 NO leading zero). Azure
         naipeuwest caps ~0.65 MB/s/client. Table 44 rows gate 0 misses; check 25/25. BATCH 5 SNOCO LANDED:
         S02 dup test vs U02 = NOT A DUPLICATE (r median 0.847 at 5 sites; same-flight pairs 0.98-0.997) — the
         county 2002 is a SECOND distinct 2002 acquisition, key 2002s; S03 = key 2003s, a calendar year the project
         had NO imagery for; S07 flip test vs 2007_king FAILED (eff 38.5 vs required <22.95) — complement key 2007s,
         King keeps 2007. All 3: city 100%, dates NOT FOUND. Catalog 28 entries. Table 47 rows gate 0 misses.
         DRIVE-MOUNT CORRECTION (measured): G: reports the LOCAL CACHE DISK (C:, same 510.8 GB volume), NOT cloud
         quota — Kam's cloud = 808 GB of 2 TB, the upsample purge DID land; every 'Drive floor' event was C: filling
         with staged uploads (gate still operationally right — writes to G: fail when C: fills). Kam moving the
         DriveFS cache to D:\DriveFS-cache (client refuses until uploads flush; a mid-move wrong setting briefly
         remounted My Drive as a folder — reverted to G:). imagery_measure.CITY_SHP now local-first
         (D:\edmonds-pipeline\Imagery\City Boundry mirror) so a Drive outage can't blank city coverage.
         N19f LANDED = REPLACE #5 (2019_naip_60cm_rgbi.tif: coverage 100 vs 67%, HF 1.358, all quads
         2019-10-11 = the S19 Hexagon flight; the 0.148-px blue reg 'loss' vs held PROVEN a blur artifact —
         registration_blur_test.json: sigma-1 smoothing of the new file drops the metric 0.148 -> 0.06, held
         smoothed re-export reads 0.001 — waiver recorded, original verdict preserved in decision.json; the
         registration twin of the S16 rise-metric lesson). Catalog 28/28, 5 REPLACES total, table 48 rows.
         BATCH 6 LANDED (all COMPLEMENT, dates NOT FOUND): keys 2009s, 2011s (NEW year), 2012s (the
         sellable 9-in year exported free; common-grid 29.6 vs 2012_king 38.9 cm HF 1.57 but 82.3% coverage — King
         orphan adoption still pending), 2006s (NEW year), 2013s; 1996 = earliest color, outside span -> held
         WITHOUT a year key (span extension = Kam's call). 2011s/2012s are EPSG:2926 HARN as delivered. Campaign:
         26 rasters, 5 REPLACES, 4 new years; catalog 33/33; table 54 rows gate 0 misses.
         3-INCH YEARS LANDED 2026-08-24 (keys 2020s/2022s/2024s): 31.0+30.2+29.6 GB, 3,450 chunks each 0 failed,
         eff 9.5-10.2 cm, 100% city, NO JPEG signature (all held CoE copies have one); ANCHOR untouched; pilots'
         300m direct request = HTTP 500 on all three (render limit; 150m passes; chunked path unaffected).
         DOWNLOAD PROGRAMME COMPLETE: 29 rasters, 5 REPLACES, 4 new years, NIR 4->10, catalog 19->36 entries
         36/36, table 57 rows gate 0. Batches 1-6 mirrored BOTH planes. LAST TRANSFER: the three 3-in Drive
         mirrors (~91 GB) — blocked until the DriveFS cache moves off C: (31 GB copy can't clear a 25 GB floor
         on a 510 GB disk); watcher armed, fires at G: free > 60 GB (= cache on D:). REMAINING: King/consortium/
         NOAA replies; Kam decisions (2012_king orphan, 2017 dup).
         NEXT: 3-inch pilots S20/S22/S24
         (per-year OK, ~23 GB each, anchor NEVER flipped), K00 ★ EmergeCIR on King reply. Kam sends: 4 asks in
         IMAGERY_ACQUISITION_ASKS_2026-08-23.md; decisions (e): 2017 duplicate, CONNECTExplorer (trash DONE).
qc:      ** IMAGERY QC AFTER THE CAMPAIGN (2026-08-24) ** branch work/20260824-qc, report
         Scripts/IMAGERY_QC_FINDINGS_2026-08-24.md, CSVs phase4/qc/imagery_qc_*. Tools: qc/imagery_qc_suite.py
         (integrity/radiometry/ndvi/crossreg/duplication/coverage), imagery_canopy_separability.py,
         separability_index_control.py, investigate_2024_offset.py. Ran on BOTH planes (local D: + a Colab CPU VM
         reading Google's servers).
         HEADLINE: resolution buys ~NOTHING for canopy DETECTION (Spearman -0.036 res vs AUROC; >=60cm files
         median .759 vs <=10cm .737) and the NIR band is the entire advantage (+0.099 median, paired same-pixel
         control). 3-inch years land MID-PACK (.735-.790) below 1m NAIP (.842-.855); the 2020 anchor is .790.
         LIMIT: this is a PER-PIXEL index metric - it says nothing about texture/crown delineation, which is what
         fine resolution is actually for. NIR not universally better: 2017n NDVI is WORSE than ExG (-0.008).
         SEASONALITY MEASURED: 2015 same-year pair, same index - leaf-off .6415 vs leaf-on .7867 = +0.145;
         forest NDVI runs .84 (July 2021n) to .42 (Oct 2023n). Directly relevant to borrowed-label under-prediction.
         2024_coe_rgb.tif IS DISPLACED ~1.28 m (same imagery: shift-corrected r .682 -> .985; 2024_coe sits 1.28m
         from both 2020 refs, 2024_snoh 0.17m; 2022_coe vs 2020_coe control = 0.004m). USE 2024s FOR POSITIONAL
         WORK. 2013_king vs 2013_snoh 2.76m spread .41 = suspect, not yet investigated.
         INTEGRITY: Drive bytes verified vs MANIFEST.sha256 - 220 files / 60.4 GB / 0 mismatches (never run before).
         NIR identity 10/10 pass. Integrity 0 FAIL. ENGINE BUG FOUND+FIXED: do_mirror used non-recursive glob ->
         39 ORIGINAL USGS HRO tiles were single-copy on D: (now rglob, tiles mirrored, 12 tests green).
         'Mirrored' != 'in the cloud': the 3-inch 91GB is still uploading and size-verify compares the local CACHE,
         so it cannot detect this. 1936/1998_king_pan have NO Drive copy. 11 legacy King/CoE files have NO
         OVERVIEWS (cause of a disk incident: full-extent reads of Drive files cache every byte onto D:, -0.5
         GB/min, ~1h from full; killed the job, 24.8 -> 36.2 GB; encoded as qc --local-only).
         MY OWN METHOD CORRECTED 4x (all caught by a suspicious number): peak-height gate discarded 54/100 valid
         measurements -> agreement-between-sites; shift-correction SIGN ERROR would have inverted the 2024 verdict
         (synthetic test: r recovers to 1.0000); padding rule over-fired on 2009 (DN 40 = dark vegetation, not
         padding) inventing a 41ha gap; --local-only. 1936_king_pan is ~90% padding, blank at all 5 QC sites.
         COVERAGE CORRECTED TWICE + VERIFIED BY RENDERING THE MAPS: sub-64px speckle ignored, analysis
         confined to the CITY POLYGON. 2001's '251 ha interior gap' was DN-0 speckle in Puget Sound -> 1.54 ha;
         every campaign raster 0.0 ha / valid 1.000 over the city; only historical scans have real holes
         (1936 1989 ha, 2000_king 27, 1990 26, 2011/2012 ~9). 2013 displacement INVESTIGATED -> INCONCLUSIVE
         (cross-year triangulation at 1m lacks signal: site spreads 2-15m vs a 2.76m question; 0/4 refs survived
         the agreement gate). That gate has a POSITIVE CONTROL: it still resolves 2024 (2/2 refs, spreads
         .07-.27). Engine mirror bug fixed (rglob) + 39 USGS tiles re-mirrored; 884 stale chunks cleaned (6.4 GB).
         All three 3-inch mirrors now local; cloud upload still draining.
         ADVERSARIALLY REVIEWED (11-agent verify+attack workflow; IMAGERY_QC_REVIEW_2026-08-24.md): 147
         findings, 0 critical / 6 major / 35 minor. FACTS all reproduce; CONFIDENCE corrected: resolution claim
         scoped to 'at the 50 cm analysis grid' (common-grid resampling erases sub-50cm info = the design cannot
         see a native-res advantage) + resolution confounded with product/season; Spearman null CI (-.35,+.31);
         '+0.013 negligible' -> unresolved; per-file AUROCs lack computable uncertainty (no per-window values
         recorded — effective n ~40 clusters, unpaired diffs <.03-.05 unresolved); byte-verify headline
         double-counted overlapping runs -> 259 distinct files / 63.4 GB, 0 mismatches (conclusion unchanged);
         NDVI invariance survives at ~2.5x logit-scale (p=.019); 2024 displacement survived every attack.
         Report amended in place (marked 'amended in review'); 3 code fixes (phase_shift docstring falsehood,
         MAD mislabel, _city_mask silent-fallback warning + city_confined CSV column).
         NEXT: build overviews on the 11 legacy files (cheapest win); weight NIR years in retraining; 2013 needs
         a SAME-EPOCH reference, not more cross-year triangulation; emit per-window AUROCs; resolve the CoE GSD
         inconsistency (config 5.0 vs measured 7.62 cm).
proj:    Edmonds temporal canopy pipeline, phase 4 (per-year semantic seg, 18 imagery yrs).
live:    ENGINE MODULARIZED 2026-07-08 → phase4seg/ package (config/common/labels/tiling/core[all torch]/
         postproc/cli) + 97L phase4_semantic_finetune.py SHIM (preserves `%run ... --args`). Behavior =
         v048, BYTE-IDENTICAL (AST-verified: 89/89 defs, 106/106 consts; py_compile+torch-free-import OK).
         NOT yet Colab-smoke-tested — GATE: `%run phase4_semantic_finetune.py --year 2000 --step tile`;
         revert = git revert df08f89. Tag v049 after smoke passes.
         phase4_semantic_finetune.py = v048. v048 = FIX: --force-citywide crashed on FINE years —
         the citywide candidate scan used a fixed 256px stride → a fine ortho (74k×106k @14.9cm) =
         119,770 candidates = ~2h scan → Colab timeout/OOM (just to pick 800 tiles). Now the scan
         stride ADAPTS to ortho size (CITYWIDE_CANDIDATE_TARGET=8000; floor 256), so fine 2013 = 8,025
         candidates (~few min) and COARSE IS UNCHANGED (2002 still 7,592 @ stride 256). --stride
         override still honoured. This unblocks the --force-citywide cross-sensor run.
         v047 = GPU-MEM + RECIPE-UNIFY + NO-OVERWRITE (Kam):
         (1) --infer-batch [def 32] replaces the old BATCH_SIZE*16=160 fp32 inference batch (the
         ~76GB spike → 80GB-only); inference forward now torch.amp.autocast + logits .float() before
         sigmoid. Output batch-invariant → pure memory knob → fits a 24GB L4 (~2-3x cheaper). Training
         ALREADY had AMP (autocast+GradScaler) → untouched. (2) --force-citywide: forces the citywide
         2020-mask coarse recipe on ALL tiers; keyed SAMPLER[already]/SELECTION-METRIC/pos_weight on
         use_blocked_val (the POOL) not gsd-tier → fully unifies + behavior-preserving. Removes the
         tier-recipe confound. Tile signature has citywide → auto-retiles; fine years scan full ortho
         (slower — test one first). (3) --run-tag TAG: suffixes model/prob/mask/gpkg _TAG so runs SAVE
         not OVERWRITE (_tag_sfx() + RUN_TAG global). py_compiled; run on Colab (torch). 
         v046 = AUX-HEIGHT BUGFIX (2016 aux run crashed): (1)
         RGB was upcast to float32 by the height-stack in __getitem__ → colour augs (uint8-
         assuming) corrupted it → training DIVERGED (val_bce→8-10); fix = cast RGB back to uint8
         before pixel_tf. (2) 4th forward site in step_evaluate not tuple-unpacked → 'tuple has no
         squeeze'; fix = unpack seg. RE-RUN 2016 --aux-height on v046. Ablation BASELINE (v045
         --no-hillshade, RGB-only no height) landed: honest rec .626 / prec .952 / GRASS-REJECTION
         .891 (RGB-only floor; CHM-input was .98) — that's the gap the height head must close.
         v045 = AUX-HEIGHT REFRAME (teach height, don't feed
         it), flag-gated (default OFF = identical to v044). --aux-height: RGB-only input + a 2nd
         output head that PREDICTS canopy height from RGB (UnetWithHeight subclass of smp.Unet,
         keeps encoder/decoder/segmentation_head keys → P3 ckpt loads strict=False; forward →
         (seg, height)). Height TARGET = CHM DN sidecar per tile (masked-L1, _masked_l1;
         _height_to_target normalizes (DN-1)*.2/40, -1 sentinel), written only for CHM_CREDIBLE_
         YEARS {2015,2016,2017,2020}; other years → aux loss auto-zeros. Wired: build_model,
         3 forward sites (tuple-safe), SemanticDataset.__getitem__ (height stacked thru
         spatial_tf then split), train/val loop unpack, tile sidecar + _tile_signature (forces
         retile) + _save_ckpt aux_height_head flag. --height-lambda [0.2], --emit-height
         (reserved). PHASE3 base NOT yet mirrored (next step for full transfer) — but the
         existing sem_best_2020.pt is already 3-ch RGB, so phase4 --aux-height fine-tunes fit
         from it directly (height head trains during the 2016 fine-tune) → the 2016 ablation
         runs NOW without touching phase3. py_compiled. plan = drifting-swinging-dolphin.md.
         v044 = INFERENCE OOM FIX: gc+empty_cache before
         inference (frees train/eval mem in the same process) + OOM-resilient flush (_forward
         auto-halves the batch on CUDA OOM). 2026-07-06 run: corrected labels APPLIED (overlay
         printed, full retile, 566/800 canopy tiles), train great (val_iou_bt .8829) but
         inference OOM'd at batch=160 (34GB + ~5GB train leftover > 40GB A100) → prob raster
         empty → qc_score returned 0 valid px (NO honest number yet). circular eval IoU .82 is
         INFLATED (test tiles now carry corrected labels) — ignore it; qc_score vs NDVI is the
         test. NEXT: fresh runtime → --step inference → postproc → phase4_qc_score.
         v043 = FIX: _tile_signature now includes
         --add-canopy-mask (path+size+mtime) so the corrected-label overlay invalidates
         cached tiles. v042 BUG: idempotent tiling (v035) reused stale tiles → the 2026-07-06
         2016 run REUSED 685 old tiles, corrected labels NEVER applied (eval ≈ v039 baseline
         IoU .7695). Overlay baked at tile time → MUST retile. Key only present when overlay
         set (no spurious retile for other years). RE-RUN 2016 --add-canopy-mask (auto-retiles
         now) → qc_score vs NDVI is the real test, NOT the circular eval.
         v042 = --add-canopy-mask: ADD-ONLY corrected-
         label overlay (canopy_additions_{year}.tif from phase4_build_corrected_labels.py)
         on the coarse 2020-mask label path. additions_from_mask (reproject onto crop) +
         apply_additions (code 1→canopy, 2→IGNORE, NEVER canopy→bg), applied in
         _gather_citywide_coarse after canopy_label_from_2020_mask. one file (2016 grid)
         serves 2016 AND 2000 (reprojected; outside strip → plain 2020 mask). NEEDS RETILE.
         v041 = --infer-thresh: explicit postproc
         op-threshold override in (0,1); bypasses eval-CSV best_f1 lookup. LOWERS an
         off-yr thresh (e.g. 2000 .513→.30) to recover CHM-suppressed stands. blunt —
         honest ref pending Phase 1/5. (_operating_threshold top + argparse + global).
         v039 (RESEARCH-BACKED ROUND 1, Phases 1+2):
         P0 fixes: (1) SAMPLER — citywide-coarse now natural/shuffle (was inverse-
         SITE weighting → gave each pure-neg site = "city" mass → batches ~83% bg;
         THE underperformance bug); (2) FREEZE_ENCODER_BN default True (+--no-
         freeze-encoder-bn); (3) Phase B resumes from BEST ckpt not last-epoch;
         (4) COARSE_USE_POS_WEIGHT=False → Dice owns balance (single channel, natural
         sampler). Validity: (5) _validate pools global IoU (was per-batch mean);
         (6) eval reports *_op metrics at deployed op-thresh + AP headline; (7) aug
         borders fill_mask=IGNORE not bg; (8) medium/fine random-split leakage
         caveat in eval_scope. v038 = coarse select val_iou→val_iou_bt. RUN with
         --freeze-encoder-bn now DEFAULT.
         v040 = postproc polygonize VECTORIZED (shapely 2.x simplify/make_valid/
         area C ufuncs over whole array + fiona.writerecords batch; was per-polygon
         Python loop w/ simplify preserve_topology=True — slow on 100k+ city
         crowns). Fallback to old loop if shapely<2. preserve_topology now False.
         pins frozen-encoder BN to pretrained running stats in Phase A [def OFF].
         PRIME SUSPECT for the fixed-epoch E6 cliff — BN drift under trainable
         input-conv + off-dist pool. _set_encoder_bn_eval re-applied after every
         model.train()). v035 = IDEMPOTENT TILING: citywide
         step_tile skips the ~20-min scan when a complete tile set matching the
         sampling signature already exists on Drive [sidecar tile_index_*.
         meta.json]; --force-retile overrides. Re-running full pipeline after a
         lost Colab session now reuses tiles. 2016 sidecar pre-seeded).
         v034 = flags --epochs-phase-a [def 20] / --epochs-phase-b [def 30]; =0
         skips Phase B → fast diagnostic runs. Phase B → _run_phase_b helper.
         v033 = flags --bce-weight/
         --dice-weight [def .5/.5] to isolate the dice term; train-only. v032 =
         SOFTENED SAMPLING HARD_NEG_FRACTION .30→.15, BACKGROUND_BUDGET_FRACTION
         .30→.22 (needs retile; DID NOT fix cliff). v031 = flags
         --coarse-pos-weight-max [def 1.3] / --lr-phase-a [def 5e-5]. v030 =
         (RGB+CHM 4ch; --hs-source chm default
         [was struct]; grass hard-negs RE-ENABLED HARD_NEG_FRAC .30 / GRVI .08 /
         bg-frac .30; no-coverage band4 → neutral fill; --hs-dropout 0.25; v029
         Phase-A trainable inflated stem). HS_STATS['chm'] :445 = ([.2306],[.2305])
         pasted (real, from fetch_build_chm.py).
data:    Full_Image/Pipeline Imagery/: lidar_snoh_hillshade_fr.tif, _be.tif,
         lidar_snoh_structure.tif = clip(fr-be+127,1,254) [TEXTURE not height,
         weak, AUC~.70], all EPSG:3857 1m ~2016 3DEP QL1 same grid. struct stats
         /255 nonzero: mean .3867 std .2175. NEW lidar_snoh_chm.tif = REAL canopy
         height (3DEP HAG metres, U8-scaled 0.2m/DN, 0=nodata). BUILT 2026-07-04:
         coverage 59.8% (~= struct 57%; same lidar footprint — rest is Puget Sound
         W edge + S margin = water, no canopy). height p50 6.7m p90 30.9m p99 44.6m.
         stats /255 nonzero mean .2306 std .2305. HAG includes buildings (fine —
         RGB flags non-green).
open:    (0) [2026-07-10 ACTIVE — plan = cozy-skipping-jellyfish.md + AMENDMENT 2026-07-10 at top]
         TWO-STREAM, ONE SHARED RGB BACKBONE, LABELS-FIRST, INSTANCE-ON-FINE FIRST. 3-agent architecture
         review (instance-first champ / semantic-unified champ / adversarial referee) synthesis:
         DELIVERABLE = ALL urban trees incl. yard/street/ornamental (3-30-300/equity). VISUAL GROUNDING:
         8/8 missed stands (2 top-fn + 6 mid-fn 0.50-0.66) = SUBURBAN (houses+lawns+ornamental yard trees,
         many purple-leaf LOW-NDVI), ZERO deciduous forest. So the ~0.68 honest-recall gap splits into
         (a) C-CAP definitionally OVER-counting leafy suburbs as "Upland Forest" (NOT a model error — counts
         lawns/roofs between yard trees) + (b) the model genuinely under-detecting SCATTERED suburban/
         ornamental (incl. non-green) trees. → Phase B target CHANGES from "deciduous forest stands" to
         "suburban/ornamental crowns in representative neighborhoods". 3 CONSENSUS FINDINGS (settled):
         (a) augmentation bridges RESOLUTION only, NOT sensor/contractor/radiometry — "one model spans all
         yrs via aug" is HALF-true (spans 8x GSD, NOT the King-contractor change / NAIP / Snoh); King-2019
         != King-2000 radiometrically. (b) the residual miss needs REAL labels — norm/aug can't reach
         low-NDVI ornamentals. (c) King 2000/02 = HARD FLOOR: unfalsifiable (no labeled sibling post-
         contractor-change, no NIR, C-CAP starts 2016, CHM stale) → un-trainable AND un-measurable from
         2020 labels; give them own labels + in-yr Olofsson, or ship LOW-CONFIDENCE. ARCH: one shared
         U-Net ResNet-101 RGB backbone, TWO heads — instance (DTM→watershed, ≤14.9cm only, Qin 2023) +
         semantic (BCE, all 18 yr); crowns dissolve→semantic FREE at fine res (& better: ornamental = a
         discrete DTM object vs a greenness-keyed BCE pixel). SEQUENCING = fine-res INSTANCE-FIRST *after*
         the label-bias fix (else you master a biased detector), coarse semantic 2nd w/ per-(sensor×era)
         anchors + radiometric normalization. LABEL RULE: instance where ≤14.9cm, semantic where coarse.
         ANNOTATION PLAN (merged, priority; 1-4 committed): 1) 2020 CoE 7.5cm INSTANCE +3-5 suburban/
         ornamental/low-NDVI sites ~1-3k crowns (root fix, both heads); 2) 2015/2013 King 14.9cm INSTANCE
         2-4 stands (anchors 5-yr King cluster); 3) 2016 Snoh 50cm SEMANTIC top-FN stands (best-
         instrumented coarse yr); 4) 2000/2002 King 60cm SEMANTIC + in-yr Olofsson pts; 5) NAIP 2019n/22n
         MEASURE first (C-CAP2021+NDVI), label only if gap. Olofsson harness GATES any pre-2016 number.
         NEXT: stage item-1 package (2020 suburban/ornamental sites + Phase-0 crown draft to correct);
         reconcile Method_Pipeline/buildtracker/xlsx to TWO-STREAM. SUPERSEDES the base plan's "semantic-
         only, labels-at-≥2-res" framing (now: two-stream, labels-per-domain).
         (0-old) [2026-07-05 SUPERSEDED] CORRECTED-LABEL workstream (supersedes 2015-flagship +
         deciduous-positive-site idea). user reframe: we have 2020 labels + CHM yet miss
         deciduous marsh → INVERT the QC instrument: use 2016 NIR+CHM to LABEL the misses,
         not just measure. NEW phase4_build_corrected_labels.py → canopy_additions_2016.tif
         (ADD-ONLY: NDVI>=.3 & CHM>=3m → canopy; green 2-3m → IGNORE; 31.97% of strip =
         hiconf canopy). v042 --add-canopy-mask layers it on coarse 2020-mask path. trees
         static → same file serves 2000. honest-recall baseline still .605 rec / .970 prec
         vs NDVI+CHM (phase4_qc_*). plan = drifting-swinging-dolphin.md. principle: lidar
         informs, never vetoes. NEXT (Colab): retile+retrain 2016 w/ overlay → qc_score vs
         NDVI; PRECISION GUARD (grass-reject ~.98, precision not down) or reject/tighten to
         .35/4m. then 2000 same overlay. measurement: NDVI now spent on labels → use
         --holdout-frac strip or build photo-interp (open item 2).
         (1) [FABLE — RESOLVED 2026-07-05] 2016 chm "collapse" root cause was the
         SAMPLER (1/count[site] → citywide batches ~83% bg) + val_iou@0.5 metric
         artifact. v039 fixed both + 6 more (see live). 2016 chm now BEATS rgb on
         held-out TEST: IoU .7725 / AUROC .938 / AP .883 / Prec .823 / Rec .927
         (vs rgb .7245/.929/.856/.773/.921; broken chm was .49/.784/.58). recall
         recovered, precision UP (grass-FP signal). CHM helps once sampler honest.
         NEXT: phase4_viz grass-FP confirm → carry config to 2000 → then Phase 4.
         (2) [NOW THE PRIORITY per user] honest-accuracy INDEPENDENT yardstick.
         RIGOR LADDER: circular proxy < C-CAP < human photo-interp. RUNG 1 DONE
         2026-07-07 = phase4_qc_indep.py + NOAA C-CAP hi-res 1m acquired (ccap_{2016,
         2021}_hires_lc.tif, EVAL-ONLY). FIRST non-circular number IN: 2016 model
         recall .684 / prec .865 / grass-rej .935 (vs NDVI+CHM .59/.96 — the two refs
         BRACKET truth). STILL PENDING = the variant RANKING (Colab-gated: only the
         current prob_2016.tif on disk; regen aux/CHM/RGB variant rasters → --prob
         each). RUNG 2 (deliverable-grade arbiter) = random-point photo-interp
         (Olofsson 2014 stratified + area-adjusted CIs) — still unbuilt. (3) radiometric normalization +
         test-time BN across years (temporal domain shift) — unbuilt. (4) coarse
         labels from 2020 mask → label-circularity ceiling until (2) exists.
blocked: none.
docs:    SOURCES OF TRUTH CENTRALIZED 2026-07-06. HANDOFFS RETIRED (5 old ones →
         Scripts/_archive/handoffs/) — this STATE + the active plan ARE the handoff now.
         Front-door doc map = treedata/README.md. To resume: read this STATE + top ~4 LOG
         entries + the ACTIVE PLAN = Scripts/OVERHAUL_PLAN_2026-08-20.md. Do NOT create a new
         HANDOFF. one-fact-one-home: live state here, method=Method_Pipeline.md, build
         status=pipeline_buildtracker.md, schedule=edmonds_combined_workplan.xlsx.
measure: WORKSTREAM (opened 2026-08-17; its plan demoted 2026-08-19 → WORKPLAN_2026-08-19.md wins).
         WHY: Kam — "became too reliant on AI judgement"; wants defensible numbers + better
         tests/visuals. FOUR PHASES, run order 1 -> 2 -> 4 -> 3 (Kam's choice).
         ---- RESUME HERE  (REWRITTEN 2026-08-19 — a long session ended, a fresh one starts) ----
         WHAT HAPPENED 2026-08-18/19, in one paragraph: a measurement session ran U1-U6 to
         answer, corrected several of its own published numbers, found and fixed three
         METADATA bugs (config gsd_cm was CRS-units x100 not ground cm; the 2016 imagery
         covers only 41.9% of the study area; the C-CAP reference we score against was a
         CLIPPED copy at 51.9% — the real source covers 91%), rebuilt the honest baseline on
         the full reference, and completed a recipe-matched series. In parallel a second
         session ran a 4,660-line lit-watch, then was stopped; its literature is sound, its
         empirical numbers are NOT REPRODUCIBLE (its scratchpad is gone) but several of its
         arguments are strong enough to overturn results here. See LIT-WATCH INTAKE below.
         THE ONE-LINE STATE: the pipeline can now MEASURE honestly; what blocks it is U1, a
         written canopy definition, which is a human judgment call and Kam's to make.
         READ FIRST, IN THIS ORDER:
           0. LIT-WATCH INTAKE (below in this block) — six items that CHANGE results 1-17.
              Read it before quoting any number in this file.
           1. this STATE block
           2. Reports/Measurement_Validity_Assessment_2026-08-18.md  <- 351-line assessment; it is
              SHARPER THAN THE PLAN on what P3 can and cannot answer. Its U1-U8 are the live question
              list. Treat it as the agenda.
           3. Scripts/WORKPLAN_2026-08-19.md (supersedes honest-measurement-overhaul.md, demoted 08-19)
           4. Scripts/pipeline_architecture.html (self-contained; open in a browser)
         PHASE STATUS
           P1 DONE · P2 DONE + replicated x4 · P4 dashboard + height plot DONE
           P4 DONE 2026-08-18: sentinel TP/FN/FP overlays landed (phase4_sentinel_qc_overlay.py).
           The photos/ footprint blocker was STALE — sentinel_sites.json already carries explicit
           bounds_wgs84 for every site. P1/P2/P4 ALL COMPLETE. Only P3 remains, gated on U1.
           P3 TOOLING BUILT, NOT YET RUN BY A HUMAN. Samples drawn for 2016 / 2022n / 2000.
         ---- THE ELEVEN RESULTS THAT MATTER ----
         (1) DETECTION IS A FUNCTION OF CANOPY HEIGHT. 2016: .16 (0-2m) .16 (2-5) .36 (5-10) .57
         (10-15) .74 (15-20) .83 (20-25) .88 (25-30) .93 (30+). 5-15m holds 53% of ALL misses;
         lifting those two bands to the 20-25m rate takes recall .68 -> ~.80. qc/height_curves.png
         (2) ** IT SURVIVES THE CONFOUND TEST (2026-08-18). ** Inside the P2 BOTH-AGREE partition the
         staircase is intact: .2278 (2-5m) -> .9496 (30+m), overall .7611 on n=22.0M. So it is NOT
         C-CAP suburban over-counting in disguise. In the CONTESTED zone the model calls canopy only
         9.2% of the time — it sides with the NDVI ref against C-CAP almost completely.
         CAVEAT: the NDVI ref requires height >= 2m BY CONSTRUCTION, so the both-agree 0-2m band is
         near-empty and MUST NOT be quoted. Finding holds above 2m.
         (3) THE DEFICIT IS INHERITED. phase3/edmonds_canopy_mask_2020.tif — the label source for all
         coarse years — has the same staircase and sits BELOW its own students at every band (.5455 vs
         the 2016 model's .6821). Improving that one mask lifts every coarse year at once.
         (4) MODEL STRENGTH DOES NOT MOVE THE NUMBER. 9 years span IoU .49-.76 / AUROC .938-.954;
         honest recall stays .51-.78 with no correlation.
         (5) ** U2 IS A DEFINITION PROBLEM, NOT AN ACCURACY PROBLEM (2026-08-18, latent class). **
         Foody-2022 LCA on C-CAP x NDVI-ref x model, fitted WITHIN CHM height bands.
         4 baseline yrs give latent prevalence pi = .2912 / .2820 (2021s) / .2931 (2019n) /
         .2863 (2022n) — i.e. ON C-CAP's total (.265-.295), NOT the NDVI ref's (.338-.387).
         Global se/sp 2016: ccap .894/.951 · ndvi_ref .987/.873 · model .750/.992. So the NDVI
         ref is HIGH-SENSITIVITY / LOW-SPECIFICITY (liberal) and the model is the STRICTEST of
         the three — a new instrument reproducing "high-precision under-predictor".
         BUT the two candidate answers are two DEFINITIONS, not a right and a wrong one: the
         NDVI ref's surplus concentrates in the 2-5m band (its sp .78, lowest of any cell) =
         shrubs/hedges. If U1 counts woody veg >=2m, pi ~ .35 is correct; if U1 requires tree
         form, pi ~ .29 is correct. NO ESTIMATOR CAN SETTLE THAT — U1 does. That is the finding.
         (5b) THE INSTRUMENT SELF-DIAGNOSED ITS OWN LIMIT. Feeding the CORRECTED 2016 model
         instead of the baseline moves pi .2912 -> .3490 and hands that model se .948/sp .966
         (best of the three) — because 2016c was TRAINED on the NDVI-derived overlay, so it is
         not a third independent test. Latent prevalence must not depend on which model you
         score; it moved 5.8pp. => LCA IS INADMISSIBLE FOR THE 2016c DEPLOY DECISION, in EITHER
         direction. Do not quote 2016c's LCA win as evidence to deploy.
         (5c) ADVERSARIAL TEST PASSED. Competing account: model+C-CAP are the correlated pair,
         they out-vote the NDVI ref, truth really is .378. Simulated that world holding the
         observed call rates fixed: NO dependence strength reproduces the observed
         (pi .291, ndvi sp .873) pair, and rho=.7 needs the model's TRUE sensitivity to be
         .115. The account fails. -> phase4_qc_latent_class_adversarial.py
         CAVEATS THAT RIDE WITH (5): do NOT quote the 0-2m row (the NDVI ref requires >=2m BY
         CONSTRUCTION); do NOT quote tall-band C-CAP sp (30+ sp .36 rides on a ~5% non-canopy
         sliver); no goodness-of-fit exists (7 params on 7 d.f. = just-identified, fits exactly
         by construction); 2022n ndvi se dips to .911 (the one wobble, not a finding).
         (6) ** n=250 IS NOT THE BINDING LIMIT — INTERPRETER FIDELITY IS (2026-08-18). **
         Simulated the REAL design (true W_h + allocation from sample_{year}_meta.json,
         Olofsson estimator w/ full multinomial covariance) instead of the SRS approximation.
         2016, 1500 simulated studies per cell:
           interp err   half-width   power(H_CCAP)  power(H_NDVI)
                   0%      .0122          1.000          1.000    <- RIGGED, see below
                   5%      .0346           .889          1.000
                  10%      .0469           .436           .997
         So §3.1's "+/-5.9pp, cannot arbitrate" was an SRS artefact — the real stratified
         half-width is .0122-.0469 vs SRS .0620, because the allocation deliberately
         over-samples the contested zone. CORRECTION TO THE ASSESSMENT, not to a model.
         THE 0% ROW IS RIGGED and must never be quoted alone: truth is DEFINED as one of the
         two references, so inside strata BUILT from those references every point shares one
         truth and within-stratum variance collapses. The honest rows are 5%/10%.
         ASYMMETRY WORTH KNOWING: symmetric interpreter error pulls every estimate toward .5,
         i.e. UPWARD from both hypotheses — so sloppy interpretation systematically favours
         the LIBERAL (higher-canopy) definition. power(H_CCAP) collapses .889 -> .436 while
         power(H_NDVI) stays ~1.0. Interpreter error does not merely widen the CI; it BIASES
         toward the shrub-inclusive answer.
         YEAR CHOICE, now evidenced: reference separation 2016 = 8.24pp but 2022n = 4.65pp,
         so 2022n is already MARGINAL at 5% error (power .340). Do 2016 DEEP rather than
         250 x 3 spread thin — which is exactly assessment amendment 3, now with a reason.
         => the duplicate-interpreted subset (amendment 5, Stehman 2022 ID 100) is NOT
         optional; it measures the one quantity the whole study now turns on.
         (7) ** U4 ANSWERED — CALIBRATION IS A REAL LEVER, AND THE OLD PER-YEAR SPREAD WAS A
         RECIPE ARTEFACT (2026-08-18). ** Reran phase4_qc_forest_misses.py --years
         2000,2002,2013,2015 --prob-suffix _citywide_rgb --thresh 0.5 (ONE recipe, FIXED
         threshold — the confound the tool's own footer warns about). NO NEW CODE.
           year  gsd_cm  recall   conf%(deep, prob<.12)  near-thresh  dbright  ht_fn/tp
           2013   14.9   .7107          30.8               69.2       + 6.3   11.4/23.7
           2015   14.9   .7075          48.2               51.8       - 3.8   11.3/23.8
           2000   59.7   .5086          27.7               72.3       +27.1   14.5/25.6
           2002   59.7   .5670          31.8               68.2       +13.9   13.9/24.9
         (a) MOST MISSES ARE NEAR-THRESHOLD IN ALL FOUR YEARS (52-72%) -> the operating point is
         a genuine lever; hand-tracing stands is NOT the only option. But threshold-lowering is
         NOT free: it lifts every band and costs precision (the tool says so in its own output).
         (b) THE OLD SPREAD DISSOLVED. Mixed-recipe conf% was 24.1/19.4/9.3; on one recipe it is
         27.7/31.8/30.8 — three years now agree. A recipe change moved 2013 by 22 POINTS. The
         cross-year variation that motivated the question was mostly the tier-recipe confound.
         (c) 2015 IS THE REAL OUTLIER at 48.2% deep, and its signature INVERTS: misses are
         DARKER (dbright -3.8) and slightly GREENER (dgrvi +0.011) where every other year's
         misses are brighter and less green. 2015 is a different failure, not more of the same.
         (d) [PARTLY SUPERSEDED by result (11b) — the "dbright scales with sensor era" half is
         WRONG, 2015 breaks it. The GSD half stands.]
         RECALL TRACKS GSD, NOT CONF%: 14.9cm -> .71/.71 vs 59.7cm -> .51/.57. A RESOLUTION
         effect on top of the radiometric one (dbright scales with sensor era, +27 in 2000 down
         to +6 in 2013 = the King contractor change).
         (e) misses are TALL — mean 11.3-14.5 m vs recalled 23.7-25.6 m. Not scrub. Sits exactly
         in the 5-15 m band result (1) says holds 53% of all misses. Results (1) and (7) agree.
         (e) [RESOLVED 2026-08-18, same day, NO Colab needed] I had recorded that 2016 was
         not comparable for lack of a _citywide_rgb raster. WRONG PREMISE, caught by reading
         config.py instead of the file listing: 2016 is 50.0 cm = COARSE tier, and coarse
         years ALREADY train on the citywide 2020 mask — the exact recipe --force-citywide
         forces onto the FINE years (2013/2015). The recipes always matched; only the
         SCORING settings differed. Rescored 2016 at the same fixed thresh 0.5, no
         --stable-with: 
           deep(<.12)%  2000 27.7 · 2013 30.8 · 2002 31.8 · 2015 48.2 · 2016 66.2
         ** 2016 IS THE OUTLIER AFTER ALL — and by MORE than the old ~60% suggested, not
         less. ** So the caution in (b) was right to demand the test and wrong about the
         answer; the original 2016 figure was not a recipe artefact.
         (f) THE IMPLICATION THAT MATTERS: 2016 is our DEFAULT TEST YEAR — the only NIR year
         with matched CHM, the year the corrected labels were built for, the year most
         results are measured on — and it is the LEAST calibration-recoverable of the five.
         Conclusions drawn on 2016 SYSTEMATICALLY UNDERSTATE how much the operating point can
         help elsewhere. "Labels or calibration" has no single answer: 2016 says labels
         (66% deep), 2000/2002/2013 say calibration is a real lever (~70% near-threshold).
         Do not generalise either way from one year — that is the mistake correction (3)
         warned about, and it very nearly repeated here in the opposite direction.
         (8) ** ~42% OF MISSES ARE CROWN PERIMETER — AND THE HEIGHT STAIRCASE SURVIVES ANYWAY
         (2026-08-18). ** Tested the sentinel ring pattern by eroding the agreed-canopy mask
         (2016, decim 4 = 2 m lattice). BOTH halves of the question came back positive:
         (a) PERIMETER EFFECT IS REAL AND GENERAL. Edge = outer 2 m = 16.3% of agreed-canopy
         AREA but carries 41.8% OF ALL MISSES. interior recall .8191 vs edge recall .3306.
         At a 4 m edge: 29.3% of area, 65.5% of misses, interior .8729 / edge .4176. So the
         ring pattern was not two cherry-picked windows — it is how this model fails.
         => A SECOND LEVER exists that is not labels and not the threshold: boundary/soft-label
         handling. Suburban recall .575 is substantially UNDER-SEGMENTATION, not blindness.
         (b) BUT IT DOES NOT EXPLAIN AWAY RESULT (1). Inside crown INTERIORS the staircase is
         intact: 5-15 m .6218 -> 20 m+ .9333, spread +0.3115 — essentially IDENTICAL to the
         edge spread +0.3105. The two effects are INDEPENDENT AND ADDITIVE, not a confound.
         Robustness: at a 4 m edge the interior spread is still +0.2528, so a modest part of
         the staircase is edge-associated but HEIGHT DOMINATES. Result (1) STANDS; U3 reinforced.
         (c) THE CAVEAT IS NOW BOUNDED, AND THE LOSS IS ONLY PARTLY CHEAP. Added a miss-depth
         + CHM diagnostic to the same tool:
           part       deep<.06  .06-.12  .12-thr   CHM miss  CHM hit  miss>=3m
           interior      .148     .314     .538      13.4 m   24.5 m    .980
           edge          .329     .345     .326      11.6 m   18.4 m    .954
         * 95% OF EDGE MISSES CARRY CHM >= 3 m -> they are REAL CANOPY the model lost, NOT the
           reference bleeding onto bare ground. The reference-error caveat is bounded, not fatal.
         * BUT only ~33% of edge misses are near-threshold vs 54% of interior misses, and edge
           misses are TWICE as often DEEP (.329 vs .148). The model is MORE CONFIDENTLY WRONG at
           crown boundaries than inside them. So the operating point recovers roughly a third of
           the perimeter loss; the rest needs BOUNDARY-AWARE SUPERVISION (soft//distance-weighted
           edge labels), which is a real engineering item, not a threshold tweak.
         REMAINING CAVEAT: reference disagreement still concentrates at boundaries; CHM>=3m
         bounds how much of that is ground-bleed but cannot rule out mis-registration.
         (d) REPLICATED ON 2021s (different year, sensor, C-CAP epoch). Three of the four
         findings replicate almost exactly; ONE DOES NOT:
           edge share of area/misses  2016 16.3%/41.8%  ·  2021s 16.1%/42.8%   REPLICATES
           interior staircase spread  2016 +.3115      ·  2021s +.3900         REPLICATES
           edge misses w/ CHM>=3m     2016 .954        ·  2021s .928           REPLICATES
           edge misses DEEP (<.06)    2016 .329        ·  2021s .633           DOES NOT
         => the SIZE and REALITY of the perimeter loss are stable properties of the model;
         HOW RECOVERABLE it is is YEAR-SPECIFIC. Do not quote a single "x% is threshold-
         recoverable" number across years — 2016 says a third, 2021s says a fifth.
         (Interior recall reads .8191 in BOTH years — a coincidence in that one aggregate;
         the per-band tables differ substantially. Not a bug, but do not read meaning into it.)
         (9) ** THE DEFINITION SWEEP ALREADY EXISTED, AND IT CORRECTS RESULT (5)'s FRAMING
         (2026-08-18). ** phase4_qc_ndvi.py has ALWAYS written a (NDVI x height) canopy-%
         table; it sits in phase4/qc/ndvi_ref_2016.txt and nobody had read it as the U1
         instrument it is. Canopy % of imaged 2016 px:
                        h>=1m   h>=2m   h>=3m   h>=5m
           NDVI>=0.10   45.08   43.26   40.97   35.06
           NDVI>=0.20   39.00   37.74   36.07   31.59     <- 37.74 = the NDVI ref
           NDVI>=0.30   34.15   33.22   31.97   28.50     <- 31.97 = corrected labels
         (a) THE GREENNESS CUT MOVES THE NUMBER AS MUCH AS HEIGHT DOES: at h>=2m, NDVI
         .10->.30 costs 10.0 pp; at NDVI>=.20, h 1->5 m costs 7.4 pp. Every doc quotes a
         HEIGHT and almost none quote the NDVI cut — so half of the definition has been
         invisible. U1 is TWO thresholds, not one.
         (b) h 2->3 m is CHEAP (1.7 pp at NDVI>=.20) -> the 2-3 m IGNORE band buys honesty
         about the contested zone for very little area. Good trade.
         (c) ** CORRECTS (5). ** NO cell reproduces the latent ~.29 except the strictest
         corner (.30/5m = 28.50); the recommended .30/3m lands at 31.97, ~3 pp ABOVE. So
         C-CAP's total is probably NOT reachable by ANY threshold pair, and the "two
         definitions, pick one" framing in (5) is INCOMPLETE: C-CAP forest is STAND-BASED and
         drops isolated crowns BY KIND (McCombs 2016 ID 77 — 3x3 unit, 6-of-9 rule). The gap
         is part threshold (ours to choose) + part unit-of-analysis (not ours). Do not keep
         saying a threshold choice reconciles the two references.
         (d) CAVEAT ON ALL OF IT — RAISED AND THEN CLOSED THE SAME DAY. The rule needs a CHM,
         so no-CHM pixels are FORCED non-canopy: 17,587,495 / 21,066,144 valid cells have CHM
         -> 16.5% of the analysis area decided by ABSENCE OF LIDAR. STATE had always ASSERTED
         that strip is Puget Sound + S margin; NEW phase4_qc_chm_gap.py CHECKED it:
           no-CHM zone : NDVI p50 -0.357 · 99.8% NEGATIVE NDVI · 0.1% green at any cut
           has-CHM zone: NDVI p50 +0.211 · 19.6% negative · 43.8% green at NDVI>=.30
         It is OPEN WATER. Counting EVERY green no-CHM px as canopy adds +0.02 pp. So the D1
         table is a lower bound in principle and EXACT in practice — DO NOT apply a coverage
         correction. STATE's assumption is now verified, not assumed. -> qc/chm_gap_2016.txt
         What survives: a lidar-dependent definition CANNOT be applied pre-2016 (no coverage),
         and this says nothing about CHM ACCURACY where it exists (that is U6, still open).
         Also note the "~60% CHM coverage" figure in CLAUDE.md is of the RASTER; over the
         IMAGED/analysis area it is 83.5%, and the remainder is water. Both true, different
         denominators — quote the 83.5% when talking about the analysis area.
         (10) ** U6 ANSWERED — CHM ERROR CANNOT HAVE MADE THE STAIRCASE; IT BARELY DENTS IT
         (2026-08-18). ** NEW phase4_qc_chm_noise.py, 2016 agreed-canopy px, decim 8.
         (a) NULL TEST (the one that validates the whole method): shuffle each pixel's
         detection outcome to be INDEPENDENT of height at the same overall rate -> spread
         +0.0001. Binning by height CANNOT manufacture a staircase. Every height result in
         this project rests on that and it had never been checked.
         (b) ATTENUATION: add Gaussian error to the BINNING variable and re-bin —
             sigma   0m      1m      2m      3m      5m
             spread  .3877   .3833   .3790   .3697   .3400
             ratio   1.00    .99     .98     .95     .88
         The literature's ~3 m MAE (Moudry 2024 ID 82) costs only 5% of the spread, because
         the headline contrast (5-15 m vs 20 m+) spans a WIDE, well-separated gap that 3 m of
         noise rarely crosses.
         (c) THE DIRECTION IS THE POINT: error in a STRATIFICATION variable attenuates —
         regression dilution — it flattens a real curve and cannot build one from a flat
         truth. So the observed .3877 is an ATTENUATED copy; true spread plausibly ~.4065.
         RESULT (1) IS SAFE AND IF ANYTHING CONSERVATIVE. U6 closed for the headline claim.
         (d) WHAT CHM ERROR *DOES* BREAK: individual 5 m BAND EDGES. At ~3 m error a pixel
         binned 5-10 m often belongs in 2-5 or 10-15. Do NOT quote one band's recall as if
         its boundary were sharp, and do NOT design a height-conditioned model around a hard
         5 m cut without allowing for the smearing (bears on Hamraz ID 86 stratify-then-
         segment: pick wide strata, not 5 m ones).
         CAVEAT: added error is Gaussian/homoscedastic; real CHM error is height-dependent and
         biased, so this brackets attenuation rather than modelling it. And if CHM error and
         detection failure share a cause (both worse in dense mixed stands) the correction in
         (c) is optimistic.
         (11) ** THE 2015 OUTLIER EXPLAINED — AND IT CORRECTS (7d). MISSES ARE DEFINED BY
         LOSS OF COLOUR CONTRAST, NOT BY BRIGHTNESS (2026-08-18). ** No new code: re-read the
         per-channel tables already in forest_miss_{2000,2002,2013,2015}.txt.
           year   dR      dG      dB     blue-excess*  d_sat    d_bright   deep%
           2000  +25.5   +23.2   +32.4     +8.1       -0.075    +27.1      27.7
           2002  +18.6   +11.9   +15.8     +0.6       -0.048    +15.4      31.8
           2013   +6.6    -0.9   +13.3    +10.4       -0.090     +6.3      30.8
           2015   -6.4    -6.4    +1.6     +8.0       -0.006     -3.8      48.2
           *blue-excess = dB - mean(dR,dG); all deltas are missed MINUS recalled.
         (a) CORRECTION TO (7d). I wrote "missed forest is BRIGHTER, and dbright scales with
         sensor era (+27 in 2000 -> +6 in 2013 = the King contractor change)". 2015 BREAKS
         that: its misses are DARKER (-3.8) and it sits BETWEEN 2013 and 2016 in time. The
         era-scaling story was pattern-matching on three points. Do not repeat it.
         (b) WHAT IS ACTUALLY INVARIANT: SATURATION FALLS IN ALL FOUR YEARS (misses are
         greyer/flatter) and BLUE-EXCESS IS POSITIVE IN ALL FOUR. Missed crowns have LOW
         COLOUR CONTRAST — washed toward grey-blue — whether they got there by haze/
         over-exposure (2000/2002/2013, brighter) or by SHADOW (2015, darker; R and G drop
         while B rises = the classic skylight-shadow signature). Two mechanisms, ONE
         appearance, and the model keys on the appearance.
         (c) WHY 2015 IS ALSO THE DEEP-MISS OUTLIER (48.2% vs ~30%): shadowed crowns are not
         near-threshold, they are confidently rejected — a shadowed crown looks like nothing
         the conifer training sites contain. Consistent with (a): the deep/near split tracks
         the MECHANISM, not the year.
         (d) ACTIONABLE: this re-specifies open item (3) radiometric normalization. A
         BRIGHTNESS-matching normalization would do nothing for 2015 (its dbright is -3.8 and
         small) — normalize per-image SATURATION + CHANNEL BALANCE instead. That is now a
         concrete target rather than "radiometric normalization, unbuilt".
         CAVEAT: 2002's blue-excess is +0.6 = essentially nil, so "all four" is carried by
         saturation, not by blue. And these are FN-vs-TP contrasts within a year, which
         confound illumination with WHAT KIND OF STAND gets missed.
         (12) ** KAM WAS RIGHT: 2016 DOES NOT COVER EDMONDS. AND config.py's gsd_cm IS WRONG
         FOR EVERY NON-UTM YEAR (2026-08-18). ** Kam: "I believe 2016 doesn't fit the whole
         extent of edmonds". Checked against the project's OWN study area (phase3 2020 mask,
         7.46 x 10.55 km). Metadata only, no raster scan.
         (a) FOOTPRINT — coverage of the 2020-mask bbox:
             2000 · 2013 · 2015 · CHM   100%
             2019n · 2022n               69.2%
             C-CAP 2016                  53.1%   (missing 3.49 km at the NORTH)
             2016 · 2021s                41.9%   (missing N 3.99 km, S 1.59 km, E 0.82 km)
         2016 covers a CENTRAL/COASTAL BAND (lat 47.7830-47.8280), not the city. This is why
         phase4_sentinel_qc_overlay printed "forest_2: outside 2016 imagery extent" —
         forest_2 sits at 47.8294, just north of the edge. I saw that line and moved on.
         (b) WHAT IT INVALIDATES — every "city" number derived from 2016 is really that
         41.9% band: the D1 threshold sweep ("city canopy 31.97%" in canopy_definition_
         PROPOSAL.md), latent-class prevalence pi~.29, the chm_gap "no-CHM zone is water"
         result, and the 2016 rows of the height/edge work. They are not WRONG, they are
         MIS-SCOPED — relabel, do not rerun.
         (c) WHAT IT PARTLY CONFOUNDS: cross-year scores. Scoring intersects with C-CAP, so
         2000/2013/2015 are scored on ~C-CAP's 53.1% while 2016 is scored on its own 41.9%
         SUBSET of that. So result (7e)'s "2016 is the outlier at 66.2% deep" compares a
         central band against a larger band. A plausible mechanism: 2016's band excludes the
         northern forest and is proportionally more suburban = the known blind spot = more
         STRUCTURAL misses. UNTESTED — the honest statement is that the 66.2% is partly
         geographic. Do not quote it as a pure model property.
         (d) SEPARATE BUG — gsd_cm IS CRS-UNITS x 100, NOT GROUND cm:
             year        config   TRUE ground   why
             2016/2021s   50.0 cm   15.4 cm     EPSG:2285 is US SURVEY FEET, not metres
             2000/2002    59.7 cm   40.1 cm     EPSG:3857 inflates by 1/cos(47.8) = 1.49
             2013/2015    14.9 cm   10.0 cm     same Web-Mercator inflation
             2019n/2022n  60.0 cm   60.7 cm     EPSG:26910 is metres -> CORRECT
         TIER IS DERIVED FROM THIS (cli.py:357 `tier_of(e["gsd_cm"]) == "coarse"`), so 2016
         is trained as COARSE (citywide 2020-mask labels, coarse stride) while its imagery is
         actually ~15 cm. Two consequences: (i) result (7e)'s recipe-comparability claim
         SURVIVES — the engine really did use the citywide recipe for 2016 — but the REASON I
         gave ("2016 is 50 cm coarse imagery") is wrong; (ii) a 512 px tile on 2016 covers
         79 m of ground, not the 256 m the coarse settings assume.
         (e) RESULT (7d) SURVIVES WITH BETTER LABELS. On TRUE gsd the recall-vs-resolution
         trend is intact and cleaner: 10 cm -> .7107/.7075 · 15 cm -> .6844 · 40 cm ->
         .5670/.5086. The finding was right; the axis was mislabelled.
         NOT FIXED HERE: config.py is untouched — changing gsd_cm changes TIER and would
         silently re-recipe every year. That is a deliberate decision for Kam, not a typo fix.
         (13) ** OUR C-CAP WAS A BADLY CLIPPED COPY. THE REAL ONE COVERS 91%. AND A DEDICATED
         CANOPY PRODUCT EXISTS (2026-08-18, Kam). ** Kam: "ccap data should encompass the
         entire area, check my arcgis folder" — RIGHT ON BOTH COUNTS.
         SOURCE: C:\Users\Kameron\Documents\ArcGIS\NOAA\{Land Cover,Tree Canopy,Impervious,Water}
         (a) COVERAGE. Over the study-area grid, DATA cells:
             ccap_2016_hires_lc.tif  (what we score against today)  51.9%
             "2016 land cover snohomish.tif"  (the real source)     91.0%   <- SAME class
             scheme (forest 9/10/11 = 25.81% of data cells vs the clipped copy's 28.19%).
         So the "C-CAP only covers ~53%" ceiling — which I recorded as a hard limit in
         result (12) — is an ARTEFACT OF OUR CLIP, not a property of C-CAP. Re-clipping lifts
         every C-CAP-scored number to ~91% of the city for the full-coverage years.
         (b) ** A DEDICATED TREE-CANOPY LAYER EXISTS AND WE NEVER USED IT. **
         wa_2021_ccap_v2_hires_canopy.tif — statewide WA, EPSG:5070, ~1.14 m, 3.07 GB,
         100% of the study bbox. Values 0/1/2 with STATISTICS_VALID_PERCENT=100, so 0 is a
         real "not canopy", NOT nodata. Canopy (1|2) = 26.0% of the study grid; over LAND
         (excluding the ~9% that is Puget Sound) ~28.6%.
         WHY THIS MATTERS FOR U2/U1: every C-CAP number in this project scores against FOREST
         LAND-COVER CLASSES, which are stand-based and drop isolated crowns BY KIND — the
         exact objection in result (9c). A purpose-built CANOPY product does not have that
         defect, and it lands at ~26-29%, i.e. NEXT TO the latent-class pi ~.29 and C-CAP
         forest 25.8%, and FAR from the NDVI ref's 37.7%. That is a THIRD, independent,
         definitionally-appropriate estimate agreeing with the low number.
         CAVEAT: it is 2021 vintage and a different product generation (v2), so it is a
         cross-check for the NIR years, not a drop-in reference for 2000/2013/2016.
         (c) ALSO SURFACED: imagery years on disk that are NOT in the catalog — 1936, 1998,
         2005, 2007, 2009, 2012, 2017, 2019, 2021, 2023 king_rgb. Unassessed.
         (14) ** METADATA MANAGEMENT — NEW phase4_data_inventory.py (Kam asked for it). **
         Three metadata bugs surfaced in one day (12a footprint, 12d gsd_cm units, 13a clipped
         reference) and none were hard to detect — nothing was looking. The inventory opens
         every raster HEADER and records role · CRS · CRS LINEAR UNIT · px in CRS units ·
         TRUE GROUND GSD (derived from the WGS84 span / pixel count, so feet-vs-metres and
         Web-Mercator inflation cannot fool it) · bounds · % of study area · dtype · nodata.
         FIRST RUN FLAGS: 50 rasters where px*100 misstates ground resolution — EVERY
         EPSG:3857 file by 1.49x and EVERY EPSG:2285 file by 3.24x, i.e. the error is
         SYSTEMATIC AND CRS-DETERMINED, not a typo — and 12 rasters not covering the study
         area (2016/2021s 41.9%, C-CAP 53.1%, NAIP 69.2%).
         RULE IT ENFORCES: true GSD and coverage are MEASURED from the file, never copied
         from a config. A config value is a claim; this is a measurement.
         (15) ** CONFIG CORRECTED + FULL-COVERAGE REF + THE CANOPY PRODUCT READ (2026-08-18,
         Kam: "Change the config. Yes to all 3"). **
         (a) phase4seg/config.py gsd_cm NOW TRUE GROUND cm (was CRS units x 100):
             2000/2002 59.7->40.1 · 2005/07/09 29.9->20.1 · King fine 14.9->10.0 ·
             CoE 7.5->5.0 · NAIP 60.0->60.7 · SNOH 50.0->15.4
         TIER IS UNCHANGED FOR EVERY YEAR. Re-deriving tier from the true numbers moves ONLY
         2016/2021s coarse->medium, and that is NOT harmless: `citywide = (tier=="coarse" or
         --force-citywide)`, so medium would switch them off the citywide 2020-mask labels
         onto the CROWN POLYGONS — the ones CLAUDE.md records as overwritten with accept-all
         test data — and would invalidate every 2016 result here. So those two carry an
         explicit "tier":"coarse", read by a NEW config.tier_for(entry) which prefers an
         explicit tier over tier_of(gsd_cm). cli.py's 4 call sites now use tier_for.
         => metadata TRUE, behaviour UNCHANGED, re-tiering is now a deliberate 1-line edit.
         "coverage" also corrected to MEASURED values (snoh 42%, NAIP 69%).
         phase4seg_preflight.py PASSES (compile · undefined-name sweep · torch-free import ·
         argparse). NOT yet Colab-smoke-tested.
         (b) FULL-COVERAGE C-CAP: FIRST LOOK, THEN A CORRECTION TO MY OWN TEST.
         2013 vs the un-clipped ccap_2016_hires_lc_snohfull.tif (91% vs 51.9% of the study
         area) read recall .7094 -> .7422, precision .8551 -> .8672.
         ** THAT COMPARISON WAS CONFOUNDED — I changed THREE things at once: the reference
         (clipped -> full), the prob raster (_xsensor_rgb -> _citywide_rgb) and the threshold
         (.5209 -> .5000). It cannot attribute the movement to the reference. ** Do not quote
         the +3.3 pp. Re-running properly (same prob, same deployed threshold as each live
         row, ONLY the reference swapped) for 2000 .5133 · 2002 .57 · 2013 .5209 · 2015 .576.
         The DIRECTION is still expected to be favourable — the clipped half is not
         representative — but the size is unmeasured until those land.
         (c) ** THE CANOPY PRODUCT SEPARATES TREE FROM SHRUB — AND HEIGHT DOES NOT. **
         Kam: "1 and 2 mean shrub or tree, cant recall". Settled with our own CHM:
             class 1 = TREE   24.79% of grid · median 21.6 m · 97.6% >=3 m
             class 2 = SHRUB   1.25% of grid · median  4.0 m · 65.6% >=3 m
         A HEIGHT CUT IS A POOR PROXY FOR THE TREE/SHRUB CALL: >=3 m keeps 97.6% of tree but
         ALSO 65.6% of shrub; >=5 m still keeps 38.1% of shrub while losing 6.6% of tree.
         D1/D2 in canopy_definition_PROPOSAL.md both assume height can stand in for form.
         IT CANNOT, cleanly — that assumption needs stating as a limitation.
         AND THE STAKES SHRINK: I framed shrub-vs-tree as worth ~6 pp of canopy. On NOAA's
         accounting shrub is 1.25% of the grid, so it is worth ~1 pp. The .29-vs-.35 gap is
         therefore NOT mostly shrubs — which weakens result (5)'s "2-5 m band = shrubs and
         hedges" reading and re-opens what the NDVI ref's surplus actually is.
         CAVEAT: NOAA's shrub class may simply be conservative; 2021 vintage; and its 24.79%
         tree share is over the FULL study grid (incl. ~9% water) whereas our 31.97% is over
         2016's 41.9% band — DIFFERENT DENOMINATORS, do not subtract them.
         (16) ** ANSWERED: WHAT THE NDVI REF OVER-CALLS IS MID-HEIGHT WOODY VEG, NOT SHRUBS —
         AND A HEIGHT CUT CANNOT SETTLE IT (2026-08-18). ** NEW phase4_qc_ndvi_vs_tree.py.
         VINTAGE-MATCHED: ndvi_ref_2021s vs the 2021 NOAA canopy product, so canopy CHANGE
         cannot explain any of it. 2 m grid, 8.1M valid cells.
           NDVI ref canopy 38.61% · NOAA tree 26.20% · NOAA tree+shrub 27.75%
           of NDVI-ref canopy:  63.84% NOAA TREE (CHM p50 20.6 m, 98.9% >=3 m)
                                 2.87% NOAA SHRUB (p50 4.8 m)
                                33.28% NOAA NEITHER (p50 6.0 m, 88.7% >=3 m, 61.1% >=5 m)
         (a) ** CORRECTS RESULT (5). ** I read the ~8 pp surplus as "shrubs and hedges in the
         2-5 m band" because the NDVI ref's specificity was lowest there. WRONG on both
         halves: only 2.87% of NDVI canopy is NOAA shrub, and the disputed population's
         MEDIAN is 6.0 m with p90 18.4 m — mid-height, not 2-5 m. Do not repeat the shrub
         reading.
         (b) THE GAP IS ONE POPULATION. 38.61 - 26.20 = 12.4 pp, and the disputed cell is
         12.85% of the grid. So essentially the WHOLE .29-vs-.38 disagreement is this single
         mid-height class, not a scatter of small definitional differences.
         (c) ** THIS BREAKS D1 AS POSED. ** canopy_definition_PROPOSAL.md frames the decision
         as a MINIMUM HEIGHT. But 88.7% of the disputed population is >=3 m and 61.1% is
         >=5 m, so NO plausible height cut removes it: the recommended >=3 m rule KEEPS ~89%
         of it and therefore lands near the NDVI ref's number, NOT near .29. Combined with
         (15c) — height is also a poor proxy for tree-vs-shrub — the real U1 decision is
         about CROWN FORM / MINIMUM CROWN SIZE, not height. D1 must be re-posed.
         (d) WHAT THE DISPUTED CLASS PROBABLY IS: young/ornamental crowns, hedgerows,
         understory and yard trees — i.e. exactly the SUBURBAN population the 8/8 visual
         grounding found, and exactly what a stand-based product declines to call "tree".
         WHICH SIDE IS RIGHT IS STILL UNDECIDED: NOAA canopy is a MODEL PRODUCT, not truth.
         P3 photo-interpretation against a written definition is still what settles it — but
         it now has a SPECIFIC population to rule on rather than a vague 8 pp.
         (17) ** 2015 IS A LEAF-OFF ACQUISITION — TWO SESSIONS, TWO INSTRUMENTS, SAME YEAR
         (2026-08-19). ** Cross-checked the stopped session's leaf-off sweep (committed
         58ee67c, its numbers otherwise UNVERIFIED per the audit) against result (11), which
         this session derived independently from per-channel forest-miss statistics.
         LOW-GREENNESS FRACTION (GRVI<0.02) over 2020-mask canopy pixels:
             2015 31.22% · 2013 22.46% · 2000 16.86% · 2002 13.58% · 2005 10.98% ·
             2022n(NAIP, leaf-on BY SPEC) 5.23% · 2016 1.95%
         ** [WITHDRAWN 2026-08-19, SAME DAY — see LIT-WATCH INTAKE item 1 below.] ** The
         cross-year GRVI ranking this result rests on IS NOT SAFE. litwatch_robustness.md
         proves it with an unarguable pair: 2019 KING reads frac(GRVI>.02)=0.1146 and 2019
         NAIP reads 0.8919 — SAME YEAR, SAME GROUND, SAME SEASON, differing by 0.78. That is
         sensor/processing colour balance, not vegetation. The King series also drifts
         monotonically .80 (2000) -> .11 (2019). So "2015 is the most leaf-off year" is NOT
         established: 2015 King vs 2016 Snoh is a CROSS-SENSOR comparison and the index
         itself moves more than any leaf-on/off effect.
         WHAT SURVIVES: (i) the 2015 ANOMALY itself — 48.2% deep misses, misses darker and
         relatively bluer — because result (11) measured that WITHIN each year (missed vs
         recalled forest in the SAME image), and a global colour cast cancels in a
         within-year contrast. That is exactly the use litwatch says is unaffected.
         (ii) the reasoning that leaf-off and low sun angle co-occur.
         WHAT FALLS: the attribution of 2015's anomaly TO leaf-off via the cross-year
         ranking. 2015 may still be leaf-off — it is no longer EVIDENCE that it is.
         LESSON FOR THE NEXT SESSION: I cross-checked two instruments and treated agreement
         as confirmation without checking whether the second instrument was comparable
         across the axis I was comparing on. Agreement between two contaminated readings is
         not corroboration.

         (a) THE CONVERGENCE [now withdrawn, see above]. 2015 is the MOST leaf-off year in the series, and 2015 is the
         year result (11) singled out on completely different evidence: 48.2% DEEP misses vs
         ~30% elsewhere, with misses DARKER and relatively BLUER — which I read as shadow.
         Leaf-off flights fly at LOW SUN ANGLE, so bare crowns and long shadows arrive
         together. So the better account of 2015 is: BARE DECIDUOUS CROWNS the green-trained
         model confidently rejects, with shadow as a CORRELATE rather than the cause.
         That explains why 2015's misses are deep rather than near-threshold: a leafless
         crown is not a marginal call, it looks like nothing in the training set.
         (b) ** IT DOES NOT GENERALISE, AND 2016 KILLS ANY SIMPLE RULE. ** 2016 is the most
         LEAF-ON year measured (1.95%) and yet has the HIGHEST deep-miss share in the project
         (66.2%, result 7e). 2013 is 2nd most leaf-off (22.46%) but sits at an ordinary 30.8%
         deep. So phenology explains 2015 SPECIFICALLY; it is NOT the axis behind the series.
         Do not build a leaf-off correction for the whole record on this.
         (c) STATUS OF THE SOURCE: this raises confidence in the leaf-off SCRIPT (its output
         agrees with an independent instrument on the one year both cover) WITHOUT rescuing
         the stopped session's headline entry, whose code is gone. Corroboration of one claim
         is not reproducibility of the rest.
         CAVEAT: the sweep samples pixels the 2020 MASK calls canopy, so it inherits that
         mask's conifer bias — which biases AGAINST detecting leaf-off, making 2015's 31.22%
         a floor rather than an estimate.
         ════ LIT-WATCH THREAD CLOSED — 2026-08-19 ════
         Scripts/litwatch_robustness.md now carries a CLOSED banner. Closed because its queue
         is dominated by MEASUREMENT and ENGINEERING items, not reading: the last searches
         confirmed existing choices rather than changing them. FOUR of four re-run claims
         reproduced EXACTLY (cast2 / q138b / overhang / q136), so the empirical work is sound
         where checked.
         ** THE ONE FIX WORTH ADOPTING (Q136, verified by re-run today): the AREA NUMBER. **
         Map-count area — counting thresholded pixels, phase3_semantic_dev.py:1722 — is
         THRESHOLD-SENSITIVE BY 17.3 pp (33.56% @ .30 down to 16.24% @ .70) and sits -5.71 pp
         at the deployed .5, measured on 162,786 points in 2013 against C-CAP at 35.97%.
         THE EDMONDS POLICY DEBATE TURNS ON 2.6 pp (32.4% baseline vs 35% goal). The
         estimator's bias is MORE THAN TWICE THE ENTIRE POLICY GAP, and it moves with a
         parameter calibrated separately per year. The Olofsson stratified reference-sample
         estimator is threshold-free and unbiased in simulation. ADOPTION IS KAM'S CALL.
         NOT claimed: that published percentages are wrong by 5.71 pp (different thresholds,
         different footprints, and C-CAP is not truth). Claimed: the estimator in use is
         threshold-sensitive by up to 17 pp and a threshold-free alternative already exists.
         ** THE JOINT SAMPLE-SIZE ANSWER — neither session had this alone, and the two
         budgets differ 5x: **
           arbitrating the REFERENCE DEFINITIONS (8.24 pp gap) -> n=250 SUFFICES, power ~1.0
             at <=5% interpreter error  [my result (6), phase4_qc_design_power.py]
           estimating the POLICY NUMBER (2.6 pp gap)          -> n=250 FAILS, +/-4.42 pp
             cannot separate 32.4% from 35%; ~1,221 pts/yr for +/-2.0 pp, and year-to-year
             CHANGE needs more  [their Q136]
         Both verified. DO NOT quote one budget as though it settled the other. This also
         re-frames U1/P3: the definition question is cheap, the deliverable number is not.
         STILL OPEN, carried forward: Q1=U1 canopy definition (Kam) · Q139 is the softness
         OURS (EPSG:3857 reprojection blur — 2000 2.8x, 2005 4.0x oversampled; cheap to
         check, could recover detail no retraining can) · Q140 the 2000/2002 deficit
         (3 explanations failed — stop guessing, look at the imagery) · channel ablation (GPU).

         ════ SCRATCHPAD RECOVERED AND THREE CLAIMS RE-RUN — 2026-08-19 ════
         The lit-watch session was NOT stopped after all; Kam had it commit its scratchpad.
         229 files now at Scripts/litwatch_scratch/ (commit d88a36b). I amended that commit
         to drop pts.npz + rg_cache.npz — 13 of its 14 MB, both regenerable caches
         (sampler.build_points is a deterministic np.linspace grid, no randomness despite its
         seed arg). Repo stays 1.33 MiB packed. SUGGEST adding *.npz to .gitignore beside the
         existing *.tif/*.pt/*.parquet "must never sneak in" list.
         ** I RE-RAN THREE CLAIMS FROM THE RECOVERED CODE. ALL THREE REPRODUCE EXACTLY. **
           cast2.py    GRVI cross-sensor cast — every figure matches, incl. the decisive pair
                       2019 KING -0.0182 / frac .1146 vs 2019 NAIP +0.1779 / .8919, and the
                       King drift .8027 (2000) -> .3463 (2013) -> .1146 (2019). Also confirms
                       1936 is a single-band constant (mean 253.0) and 1998 single-band.
           q138b.py    effective resolution — all 11 rows match: 1998 244.7 cm (6.10x),
                       2005 80.7 (4.02x), 2000 110.8 (2.76x), the other 8 at 1.26-1.42 px.
           overhang.py on-building split — 23,666 buildings, 12,271 cells, AT-roof 29.77%,
                       ABOVE-roof 68.43%, median delta +2.10 m. Exact.
         => ** UPGRADE THE AUDIT. ** My earlier "treat every figure as unverified" was right
         WHEN THE CODE WAS MISSING and is now too harsh: for the three highest-value claims
         the code exists and reproduces to the digit. Remaining figures are UNRE-RUN, not
         unreproducible — the scripts are there, so anything can be checked before use.
         CONSEQUENCES FOR MY OWN RESULTS:
         (a) The result-(17) WITHDRAWAL IS CONFIRMED CORRECT. The GRVI cast is real and
             measured, so the cross-year leaf-off ranking genuinely could not carry it.
         (b) MY RESOLUTION FINDING NEEDS QUALIFYING, not withdrawing. Recall vs EFFECTIVE
             resolution: 13.7cm .7422 · 12.9 .7401 · 25.5 .6605 · 26.1 .6048 · 57.1 .6136 ·
             80.7 .6346 · 110.8 .5480. The EXTREMES still separate (~19 pp from 13 cm to
             111 cm) but the MIDDLE IS NOT MONOTONE — 2005 at 80.7 cm beats 2009 at 26.1 cm.
             So nominal tiers made the trend look cleaner than it is. Resolution is real at
             the extremes; the mechanism in the middle is unexplained (their three attempts —
             nominal GSD, spectral sharpness, effective resolution — all failed).
         (c) OPERATIONAL, AND IT EXPLAINS MY SLOW NIGHT: cast2.py's docstring records that
             NOTHING in this project has overviews, so a decimated whole-raster read silently
             reads the entire multi-GB file. That is why my qc_indep rescores took 30-60 min
             each. BUILDING OVERVIEWS (gdaladdo) would speed every full-raster QC tool here.
         (d) NOT verified: the headline 88-93% "real miss". overhang.py reproduces the
             ON-BUILDING SPLIT that feeds it, not the whole chain. Re-run the rest before
             quoting that number.
         DO NOT RUN upd*.py / chat*.py / entry*.py / append.py — they are WRITERS that append
         to litwatch_robustness.md, CHATLOG.md and Literature_Tracker.xlsx. Re-running them
         duplicates entries. Superseded buggy versions are kept on purpose: q138.py has the
         np.interp monotonicity bug, cast.py predates the windowed rewrite, q121/q121b predate
         the streaming rewrite. Use q138b / cast2 / q121c.

         ════ LIT-WATCH INTAKE (2026-08-19) — READ THIS BEFORE TRUSTING RESULTS 1-17 ════
         SOURCE: Scripts/litwatch_robustness.md, 4,660 lines, searches 15-45+, IDs 106-178+,
         written by the now-STOPPED parallel session. STATUS OF ITS NUMBERS: the empirical
         sections were computed with the same scratchpad that no longer exists, so treat
         every FIGURE as unverified. Treat the REASONING as usable — several items below
         carry their own internal proof and need no code to be persuasive.
         SIX ITEMS THAT CHANGE WHAT THIS FILE ALREADY SAYS:
         1. ** GRVI IS NOT COMPARABLE ACROSS SENSORS. ** 2019 King frac(GRVI>.02)=0.1146 vs
            2019 NAIP 0.8919 — same year, same ground, same season. King drifts .80->.11
            across 2000->2019. ANY cross-year GRVI diagnostic reports a large steady canopy
            decline that is pure processing artefact. WITHIN-year use is unaffected.
            -> WITHDRAWS result (17); see the note on it. Also means the leaf-off sweep's
            cross-year table must not be quoted.
         2. ** EFFECTIVE RESOLUTION != NOMINAL GSD, by up to 6x. ** Edge-spread measurement,
            12 fixed sites, 11 years: 1998 nominal 40 cm resolves at 245 cm (6.1x); 2005
            nominal 20 cm resolves at 81 cm (4.0x) — COARSER THAN 2000's nominal 40; 2000
            resolves at 111 cm (2.8x). The other 8 years are properly sampled at 1.26-1.42 px.
            -> QUALIFIES my "resolution is worth ~16 pp" (result 15/recipe-matched table).
            The nominal tiering happened to give a clean trend, but 2005 sits at 81 cm
            effective and still scores .6346, near 2007/2009 at ~26 cm. Effective resolution
            REORDERS the years and does NOT reproduce the trend, so the mechanism is not
            settled. Their own words: three attempts to explain the 2000/2002 deficit have
            failed (nominal GSD, spectral sharpness, effective resolution).
            -> ALSO: my gsd_cm fix corrected UNITS (CRS->ground) but tier is still keyed to
            a number that is wrong by up to 6x as a measure of real detail. Worth revisiting
            tier_for() with effective resolution if 2005/2000 are ever retrained.
            -> AND A LEAD WORTH CHASING: every King file is EPSG:3857, and reprojection to
            Web Mercator is itself a blurring resample. The softness may be OURS, introduced
            by mosaicking, not the original acquisition. If so, re-deriving early years from
            native-projection sources recovers detail no retraining can.
         3. ** THE CONTESTED BAND IS MOSTLY REAL MISS, NOT REFERENCE DISAGREEMENT. ** Against
            rasterised per-building heights, canopy over roofs: 88-93% of the tall contested
            band is genuine model failure under both a liberal and a conservative reading of
            the building heights. P2 implied ~35%. -> This attacks the "38.7% is unmeasurable"
            framing that results (5) and (12) lean on. If it holds, the honest recall numbers
            are TOO KIND, not too harsh. HIGH PRIORITY TO RE-DERIVE with tracked code.
         4. ** RECALL HALVES ON CANOPY OVER IMPERVIOUS ** (Q116) and two independent deficits
            COMPOUND (Q118). Consistent with my edge/perimeter result (8) — overhang above
            roofs and driveways is exactly perimeter canopy.
         5. ** SHADOW REFUTED AS THE OVERHANG MECHANISM ** (Q122) — bears on result (11)'s
            shadow reading; their test is of overhang specifically, mine was of 2015's
            per-channel signature, so these are not the same claim, but do not merge them.
         6. ** INVENTORY DEFECTS: ** 1936_king_rgb.tif is an EMPTY SHELL (uniform 253/0 fill —
            King County survey does not reach into Snohomish); 1998 and 1936 are SINGLE-BAND
            despite _rgb filenames; there are TWO DIFFERENT 2017 ACQUISITIONS; no acquisition
            metadata exists in any raster. -> Cross-check against my phase4_data_inventory.py,
            which measures geometry but NOT band count or fill — worth extending.
         WHAT IT DOES NOT TOUCH: the literature itself, which is the durable asset — DOIs
         verified against Crossref, explicit inclusion bar, covered/queued discipline.
         ---- LITERATURE (37 papers, IDs 69-105, searches 9-14) — TWO CORRECTIONS TO ME ----
         FOODY 2010: I claimed raw scores overstate the model's faults. Direction depends on ERROR
         CORRELATION; ours are almost certainly correlated (labels + both refs all from interpreting
         the same imagery) => OUR RECALL IS LIKELY OPTIMISTIC. Do not repeat my old pattern claim.
         MOUDRY 2024 + SIERRA 2026: canopy-height products are height-biased, realistic CHM MAE ~3m,
         [U6 RESOLVED 2026-08-18 — see result (10). The ~3m error costs only 5% of the height
         spread and can only ATTENUATE, never create it. Band EDGES stay smeared.]
         which would blur 5m bands. Part of the staircase could be CHM error. UNVALIDATED (U6).
         Confirmed independently: TURUBANOVA 2023 (error concentrates 4-6m), FERRAZ 2016 (same shape
         from lidar), ARAZO 2020 (our feedback loop is canonical pseudo-label confirmation bias),
         MAJASALMI 2021 (15-17% disagreement is NORMAL).
         ---- P3 MUST CHANGE BEFORE KAM LABELS ----
         (a) U1 NO WRITTEN CANOPY DEFINITION EXISTS. Min height? Min crown area? Shrub vs short tree?
         Lawn under a yard tree? Without it 250 points produce A THIRD OPINION, not an arbitration.
         ONE PAGE, written first, committed. THIS IS THE TOP BLOCKER.
         (b) UNSURE HANDLING: my sampler EXCLUDES unsure. WICKHAM 2023 shows primary-vs-alternate
         scoring swings accuracy 10 POINTS (77.5 -> 87.1). Record PRIMARY + ALTERNATE, report both.
         (c) SAMPLE SIZE: the assessment shows n=250 gives +/-5.9pp, which COVERS BOTH references
         (27.7-39.5 vs C-CAP 29.5 / NDVI 37.7) => cannot arbitrate. NOTE: that arithmetic assumes
         SIMPLE RANDOM SAMPLING; our stratified design over-samples the contested zone and should do
         better. [RESOLVED 2026-08-18 — SIMULATED, see result (6): the stratified design IS
         better (half-width .0122-.0469 vs SRS .0620) and n=250 DOES arbitrate in 2016 up to
         ~5% interpreter error. Do NOT resize n on the +/-5.9pp figure; the binding constraint
         is interpreter fidelity, not sample size.]
         (d) STEHMAN 2014 licenses reference-derived strata but requires ITS estimators; mine is a
         delta-method approximation. WAGNER & STEHMAN 2015/2024 give a principled allocation; my
         shares were ad hoc.
         ---- CHEAPEST NEXT MOVES (all local, no GPU, no labelling) ----
         1. [DONE 2026-08-18] FOODY 2022 LATENT-CLASS — see result (5) below.
         2. [DONE 2026-08-18] Simulate the ACTUAL stratified design's CI — see result (6).
         3. Write the canopy definition (U1). <-- NOW #1, and results (5)+(6) BOTH converge
            on it: (5) says U1 alone decides whether Edmonds canopy is ~29% or ~35%; (6) says
            n=250 CAN resolve that in 2016 — but only against a definition it has been given.
            Write it against the .29/.35 bracket.
         4. [DONE 2026-08-18] P1c per-year miss-depth under ONE recipe — see result (7).
         5. NEW: rerun 2016 forest-miss on the _citywide_rgb recipe so its ~60%-deep figure
            becomes comparable (needs a 2016 --force-citywide inference on Colab).
         ---- P3 COMMANDS (tooling is built and validated) ----
         py -3.12 phase4_accuracy_sample.py --step serve --year 2016             --ortho "D:\edmonds-pipeline\Imagery\2016_snoh_rgbi.tif"
         then open http://localhost:8731/review_app.html  (1 canopy / 2 not / 3 unsure / z undo)
         then --step estimate --year 2016
         Estimator validated twice; a covariance bug was found and fixed 2026-08-18 (8283232) — the
         old version overstated every CI.
         ---- LOCAL ENV ----
         CUDA now works locally: torch 2.13.0+cu126, Quadro T2000 4GB (CLAUDE.md says 2GB — STALE),
         3.45GB free, verified. Still do NOT train locally (rule: don't split training Colab/local).
         ---- HONEST BASELINE — RESTATED 2026-08-18 ON THE FULL-COVERAGE REFERENCE ----
         The old table was scored against ccap_2016_hires_lc.tif, a CLIPPED copy covering
         51.9% of the study area (result 13a). Rescored against the un-clipped source
         ccap_2016_hires_lc_snohfull.tif (91.0%), changing ONLY the reference — same prob
         raster, same deployed threshold, forest_wetland:
             year   clipped ref     FULL ref        d recall   imagery coverage
             2000   .6303/.7745  -> .6749/.7975      +4.5 pp   100%
             2002   .5069/.8377  -> .5580/.8563      +5.1 pp   100%
             2013   .7094/.8551  -> .7395/.8666      +3.0 pp   100%
             2015   .6222/.8835  -> .6629/.8989      +4.1 pp   100%
             2017   .7784/.8083  -> .7986/.8274      +2.0 pp   100%
             2016   .6844/.8651  -> .6636/.8736      -2.1 pp    41.9%
         ---- 2021 SAME-YEAR CROSS-SENSOR PAIR — CANNOT BE READ YET (2026-08-19) ----
         The job queued specifically to isolate the sensor effect, because real canopy change
         between two 2021 acquisitions is ~zero:
             2021s  Snohomish 15.4 cm  p2nir recipe    thresh .499   .6851 / .8547
             2021k  King      10.0 cm  citywide recipe thresh .4013  .6059 / .8778
         Naively: the COARSER sensor wins recall by 7.9 pp, which would contradict the
         recipe-matched resolution trend above (10 cm ~.741). ** DO NOT READ IT THAT WAY. **
         TWO uncontrolled confounds:
           (1) TILING PARAMS — 2021s is coarse tier, 2021k is fine, so stride / neg-rate /
               test-split differ (TIER_TILE_PARAMS).
           (2) FOOTPRINT — 2021s covers 41.9% of the study area, 2021k 100%, so they are
               scored on different ground (result 12c).
         ** CORRECTION 2026-08-19 to what I first wrote here. ** I said the two used
         DIFFERENT LABEL RECIPES (p2nir vs citywide) and that a retrain would settle it.
         WRONG on both counts, found by reading cli.py rather than the run tags: "p2nir" is
         only a RUN TAG. 2021s is COARSE tier, and coarse years take the citywide 2020-mask
         label path BY DEFAULT — the same path --force-citywide gave 2021k. Their LABEL
         SOURCE already matches; what differs is the TIER TILING PARAMETERS.
         AND THAT CANNOT BE RETRAINED AWAY: tiling params are keyed to tier, tier is keyed to
         resolution, so "sensor" and "tiling regime" are entangled BY DESIGN. There is no
         Colab job that isolates the sensor here. DO NOT SPEND A 5 cm RUN ON IT — the earlier
         entry proposing exactly that is withdrawn.
         Recorded as OPEN AND PROBABLY NOT ANSWERABLE by retraining. A real answer needs a
         deliberate ablation (same year, same footprint, tiling params forced equal), which
         is an engine change, not a queue entry.

         ---- QUEUE 2 (Colab, overnight 2026-08-18/19) — FIRST TWO YEARS SCORED ----
         2005 and 2007 trained + inferred OK (VERIFY 100% valid). Scored vs the FULL-coverage
         ref, forest_wetland, tool-chosen threshold:
             2005  thresh .4659   recall .6346   precision .9166   <- HIGHEST precision in
             2007  thresh .5026   recall .6605   precision .8813      the whole project
         ** THE max-prob WARNING WAS AGAIN A RED HERRING. ** Their inference max-prob was
         .843/.882, well under 2019n .949 / 2021s .957, i.e. the same COMPRESSED RANGE that
         made a previous session predict low recall for 2017 TWICE — wrongly, 2017 is the
         series high. I withheld the prediction this time and the numbers are mid-series.
         A compressed probability range means THRESHOLD FRAGILITY, not weak ranking. This is
         now 2-for-2; treat it as settled.
         ** RECIPE CAVEAT — DO NOT RANK THESE AGAINST THE TABLE BELOW. ** 2005/2007 are
         _citywide_rgb; the 2000/2002/2013/2015 rows below are _xsensor_rgb. Result (7b)
         measured that a recipe change moved 2013 by 22 points, so a mixed-recipe ranking is
         not interpretable. To compare, re-score the older years' _citywide_rgb rasters
         (they exist) on this same reference.
         ---- RECIPE-MATCHED SERIES (2026-08-19) — ONE RECIPE, ONE REFERENCE ----
         Ran the re-score rather than writing the reversal claim. ALL _citywide_rgb, ALL vs
         the FULL-coverage ref, forest_wetland, tool-chosen threshold:
             year  TRUE gsd  recall  precision
             2000    40.1cm  .5480     .8534
             2002    40.1cm  .6136     .8372
             2005    20.1cm  .6346     .9166
             2007    20.1cm  .6605     .8813
             2009    20.1cm  .6048     .9177   <- highest precision in the project
             2013    10.0cm  .7422     .8672
             2015    10.0cm  .7401     .8823
         ** RESULT (7d) IS VINDICATED, NOT REVERSED. ** Once recipe is held constant the
         trend is clean and the within-tier agreement is tight:
             40 cm  .5480 .6136          mean .581
             20 cm  .6346 .6605 .6048    mean .633
             10 cm  .7422 .7401          mean .741   <- 0.2 pp apart, different sensors/years
         Resolution is a REAL driver worth ~16 pp of recall across 40->10 cm, and the 10 cm
         pair agreeing to 0.2 pp across two different years is the strongest within-tier
         replication in the project. The apparent reversal in the
         mixed-recipe table WAS the confound, exactly as suspected — which is why the rule
         is to re-score rather than to reason about it.
         ** AND THE RECIPE EFFECT IS LARGE AND YEAR-SPECIFIC: ** same year, same reference,
         only the training recipe differs —
             2000  xsensor .6749  vs  citywide .5480   -> xsensor BETTER by 12.7 pp
             2002  xsensor .5580  vs  citywide .6136   -> citywide BETTER by  5.6 pp
         Opposite directions. So there is NO globally better recipe, and no cross-year table
         mixing them means anything. This is the third independent measurement of the same
         hazard (7b moved 2013 by 22 pp; this moves 2000 by 12.7 pp in the other direction).
         2015 also swings by recipe: xsensor .6629 vs citywide .7401 = citywide better by
         7.7 pp — a THIRD direction-and-magnitude, reinforcing that recipe is year-specific.
         ** QUOTE THE FULL-REF COLUMN. ** Precision rose in ALL SIX years. Complete.
         ** THE ASYMMETRY IS THE FINDING, AND IT IS NOW 5-FOR-5: ** every year with 100%
         imagery coverage got BETTER (2000 +4.5, 2002 +5.1, 2013 +3.0, 2015 +4.1, 2017
         +2.0); 2016 — the ONLY one at 41.9% — got WORSE. Coverage, not year or sensor,
         predicts the sign. 2017 remains the highest recall in the series at .7986. So the clipped reference was
         FLATTERING 2016 specifically and PENALISING the full-coverage years. That matters
         because 2016 is the most-cited year in the project (the only NIR year with a
         matched CHM, and the year the corrected labels were built for).
         ** 2016 HONEST RECALL IS NOW .6636, NOT .6844. ** Anywhere this file or a report
         says "2016 recall .6844" against C-CAP, it is superseded — including the framing
         in results (3) and (5). The DIRECTION of every finding is unchanged; the level is.
         UNAFFECTED: NDVI-ref 2016 .594/.959 (different reference entirely). STILL TRUE:
         every 2016-derived analysis remains bounded by the 41.9% footprint no matter which
         C-CAP is used (result 12b) — a fuller reference does not widen the imagery.
         READ = high-precision UNDER-predictor, misses ~30-35% of C-CAP forest; scrub recall .25
         vs forest .68 -> fails on non-conifer/mixed structure (the conifer-only-label blind spot).
         CAVEAT that must ride with every number: BOTH refs are PROXIES (CHM ~2016 @60% coverage;
         C-CAP 2016/2021 applied to 2000/2002/2013). Unknown share of the gap is ref error + real
         change, NOT model error. P2 bounds it; P3 measures it.
         ---- CORRECTIONS TO EARLIER CLAIMS (do not regress) ----
         (1) forest_miss_2016.txt "RECALL .7623" is a stable-intersect-2021 SUBSET. HONEST 2016 =
         .6821 (qc_indep; independently reconfirmed .6832 by decimated recompute). 
         (2) qc_indep is CORRECT — I hypothesised it was pessimistic for lacking an imagery-footprint
         mask and DISPROVED it (0 px dropped on 2016). Do NOT "fix" it.
         (3) "misses are confident/structural -> labels beat compute" is 2016-ONLY. conf% (misses
         prob<.12): 2016 ~60% BUT 2013 9.3%, 2002 19.4%, 2000 24.1% -> most cross-sensor misses are
         NEAR-THRESHOLD, maybe calibration-recoverable. Do NOT commit to hand-tracing stands until
         P1c recomputes this per year on one recipe.
         [SUPERSEDED 2026-08-18 by result (7) — recomputed on ONE recipe. The near-threshold
         conclusion HOLDS, but every per-year conf% above was a RECIPE ARTEFACT and must not be
         re-quoted: 2013 moved 9.3% -> 30.8%. Use the result-(7) table.]
         (4) There is NO git remote — "git pull" CANNOT update Colab. The working tree IS
         the Drive folder (G:/My Drive/treedata); git DB = D:/edmonds-pipeline/treedata.git,
         local Windows only. GOOGLE DRIVE is the sync path to Colab. Verify there with:
         !grep -c 2022n /content/drive/MyDrive/treedata/Scripts/phase4_p1_colab_run.py
gotcha:  scripts Colab-only for torch (rasterio+geopandas+fiona+sklearn now pip-
         installed local — module import auto-installs). polygons/ overwritten w/
         accept-all test data; 14,476-crown human review never finished.

════════════════ LOG  (newest first) ════════════════

## 2026-08-29  DAMAGE CURVE COMPLETE · NODE C WINS · THE CHM CHANNEL IS INFLATED, NOT LOW (Fable 5, all-night run)
goal:    Kam: 200 credits, run all night, reflect before each arm, parallel GPUs.
did:     ** DAMAGE CURVE (inject known label error at a chosen dose) ** matched-precision
         recall vs clean .6989: 2.70% -> .6951 (-.004) · 6.56% -> .6673 (-.032) ·
         12.34% -> .6436 (-.055). Upper two points are LINEAR at ~0.45 pp per 1% of error;
         the lowest falls BELOW that line (hints at a tolerance zone, but it is inside noise
         so do not claim it). ** AUROC IS FLAT ACROSS ALL FOUR ** (.9210 .9215 .9210 .9218):
         even 12% corruption leaves RANKING untouched — label error moves the OPERATING
         POINT, not discrimination. That is why the hybrid's 0.53% correction was invisible
         (predicted gain ~0.2 pp vs sigma .010) and it retires the mystery.
         ** NODE C WINS ** (3-band, projected key + proven canopy, vs Node B): AUROC
         .9063->.9179, PR-AUC .8365->.8588, matched-precision recall .5990->.6518 (+5.3 pp on
         the common 198.8 Mpx footprint). All three metrics agree; noise would scatter. It
         recovers HALF the 10 pp the height channel is worth WITHOUT the model seeing height —
         lidar knowledge distilled through LABELS. Different mechanism from correction:
         Node C moved AUROC (new information), corruption never did.
         ** THE 4th CHANNEL IS WRONG, AND THE SIGN IS BACKWARDS ** — measured against 863.5M
         raw 2016 returns, no interpolation in the loop (max return minus lowest class-2 in
         the SAME 2 m cell, 8.8M cells): on ground the points say 0.14 m, lidar_snoh_chm.tif
         says 4.90 m and calls 57.3% of bare ground >2 m. Offset +4.1 to +5.4 m in EVERY bin
         0-30 m. NOT misregistration (MAE minimised at zero shift, r=.889). On certified-flat
         ground: old 8.82% called >2 m, chm2 0.01%. Mechanism: ~3-6 m effective support = a
         NEIGHBOURHOOD MAXIMUM smearing canopy height onto adjacent open ground. Every 4-band
         model ever trained here was told lawns beside trees are ~5 m tall. IMAGERY_FACTS 8.3
         corrected (ed3161e); rebuilt lidar_chm2_2016_50cm.tif (0.5 m, EPSG:26910 native,
         same uint8 encoding so the A/B is one variable).
         ** TRAINING MECHANISM ** 4 of 5 arms never early-stopped — they hit EPOCHS_PHASE_B=30.
         rgb3_nodeb's BEST EPOCH WAS ITS LAST. The cap truncates ASYMMETRICALLY (harder
         configs need more epochs, get proportionally less training), biasing every A/B where
         one side is harder — including BOTH headline numbers above. --epochs-phase-b ALREADY
         EXISTED (v034); I never checked and read truncated results for a week.
         Landed: --select-smooth K (ring of trailing CPU weight snapshots so the winning
         epoch's REAL weights are held — a post-hoc pick would select weights nobody saved;
         never averages), stop-reason logging (its absence is why this hid), 18/18 tests.
decided: seed-varied arms (1234, 777) to measure TRUE retrain sigma — the banked .010 came
         from 5 SAME-SEED repeats and is a floor on a floor. Split variance still unmeasured
         (tiling binds its seed at import) and is probably larger: 3 selections ride on a
         ~120-tile val set.
         ════ LATER THE SAME NIGHT — three hypotheses tested, TWO OF THEM MINE, BOTH DEAD ════
         ** TRUNCATION: REFUTED. ** Above I wrote that EPOCHS_PHASE_B=30 truncates
         asymmetrically and biases BOTH headline numbers. Tested it: reran Node B with
         --epochs-phase-b 60. Log reads "Phase B stopped by PATIENCE after 32/60 epochs
         (best epoch 17, patience 15)" — given room it did NOT keep climbing; it converged
         and stopped on its own well short of the ceiling. Scored .9086 AUROC / .8322 PR-AUC
         vs the 30-cap run's .9063 / .8365: differences of noise size that do not even agree
         in sign. So the cap was not biasing the headline numbers, and NODE C'S WIN SURVIVES
         a converged baseline (.9179/.8588 vs .906-.909/.832-.837, ~6x the seed spread on
         AUROC). Correct the paragraph above accordingly: the cap-truncation concern was
         real to raise and is now measured to be inert for this arm. --epochs-phase-b and
         the stop-reason logging both stay; they are how it got settled.
         ** CHM2: REFUTED, AND SLIGHTLY WORSE. ** Curve metrics now in: chm2_v1 AUROC .9153
         vs Node A .9210 — DOWN .0057, about 3.5x the .0016 seed noise — PR-AUC .8654 vs
         .8632, unchanged. So the measurement-correct height channel does not merely fail to
         help, it costs a little ranking. Best available reading: the inflated channel's
         neighbourhood-maximum smear acts like a DILATION of "tall", flagging the ground
         immediately around crowns, and that helps at crown edges; the sharp corrected
         channel does not. Either way the channel is not paying for measurement accuracy —
         its value is COARSE STRUCTURE. Fixing the raster does not buy accuracy.
         ** THE DAMAGE CURVE, RE-READ ON CURVE METRICS — the recall version OVERSTATED it. **
         All four 4-band arms re-scored threshold-free on the common 198.8 Mpx footprint
         (phase4/qc/arm_pr_curves_2009_4band.md). Doses are the MEASURED fractions, not the
         nominal tag names:
             dose      AUROC    PR-AUC   matched-precision recall
             clean     .9210    .8632    .6989
             2.70%     .9215    .8653    .6951
             6.56%     .9210    .8575    .6673
             12.34%    .9218    .8568    .6436
         AUROC spread across the WHOLE range is .0008 — below the .0016 seed noise. Ranking
         is untouched by 12% of crowns being wrong. PR-AUC does register damage but weakly:
         the lowest dose is free, the top two cost .0057 and .0064 (~5x the .0012 PR-AUC seed
         noise). Yet matched-precision recall falls 5.5 pp over the same range.
         RECONCILE — all three are true and the apparent contradiction is the lesson: a SMALL
         real shift in the PR curve lands on a STEEP part of it, so it buys a large-looking
         recall change at the one high-precision operating point we deploy at. The earlier
         "~0.45 pp recall per 1% of label error" is still the right number FOR THAT OPERATING
         POINT, but it is not a measure of knowledge lost; most of what it counts is the
         curve sliding under a fixed precision target. State it that way from now on.
         ** CHECKPOINT SELECTION IS NEARLY A COIN FLIP — free, no GPU. ** New instrument
         qc/phase4_select_smooth_probe.py replays the --select-smooth rule against saved loss
         histories: it answers WHICH epoch each K would deploy, from files already on disk.
         Across all 7 arms with histories, in phase B the spread over the TOP FIVE candidate
         epochs is SMALLER than that same curve's mean epoch-to-epoch wobble (ratios .26-.81;
         e.g. rgb3_ep60 top5 spread .0024 vs wobble .0049). Plain: the top five epochs are
         tied to within less than one epoch of random jitter, so picking the argmax is close
         to drawing one of five at random — and it draws whichever got the luckiest
         validation noise. That is selection ON noise. K=5 changes the deployed epoch in 5 of
         7 arms. This is the justification for running smoothing as its own arm.
         ** NOISE FLOOR — my own error, caught before it set a verdict. ** I first wrote that
         rgb3_nodeb vs rgb3_ep60 (.0023 AUROC) "is the noise floor". It is not: they differ
         in the epoch cap AND the cap BOUND on the first (its best epoch was its last). Their
         gap is cap-change + noise, an UPPER bound. The 3-band branch has NO clean same-recipe
         repeat. Closest real number is the 4-band seed pair, .0016 AUROC. Working floor
         ~.002, flagged soft in the queue file.
         ** THE SECOND ERROR BAR — measured, free, and it CLEARS Node C. ** Every verdict
         here has been a point estimate checked against RETRAIN noise (train twice, see how
         far it moves). That is one of two uncertainties. The other — given two FINISHED
         rasters, how sure are we the ordering is real — had never been measured, and the
         intuitive answer is wrong: 198.8 Mpx sounds like huge statistical power, but
         neighbouring pixels are the SAME TREE, so the real sample size is the number of
         independent patches. New tool qc/phase4_arm_bootstrap_ci.py resamples 512x2048 px
         BLOCKS with replacement. Exact, not approximate: arm_pr_curves scores from 256-bin
         DN histograms and histograms ADD, so per-block histograms resample and re-sum with
         no pixel subsampling. Paired — every replicate scores all arms on the same blocks,
         so shared ground cancels and the interval lands on the DIFFERENCE.
         Result (phase4/qc/arm_bootstrap_ci_2009.md), 235 non-empty blocks — that, not
         198.8 million, is what the evidence is worth:
             nodec_v1 vs rgb3_nodeb   dAUROC +.0116  95% CI [+.0094, +.0136]  100% sign-stable
                                      dPR-AUC +.0223  95% CI [+.0181, +.0266]  100% sign-stable
         Node C's margin is ~5x the CI half-width AND ~6x retrain noise. Where we looked is
         NOT what is holding this claim up.
         ** AND THE TRAP THE SAME RUN EXPOSED. ** rgb3_ep60 vs rgb3_nodeb also came back
         "significant": dAUROC +.0023, CI [+.0012,+.0033], 100% sign-stable. Those two are
         the SAME recipe family differing by an epoch cap that did not bind — the gap is
         trajectory noise. So a tight interval here proves the two RASTERS differ on this
         ground; it does NOT prove the two RECIPES differ, because retrain noise is not in
         it. Rule adopted, and written into the tool's own output so it cannot be quoted
         without it: compare every gap against BOTH numbers and quote the LARGER.
         ** n=3 SEEDS: THE ERROR BAR IS ~3x BIGGER THAN I HAD BEEN USING, AND IT
         RETRACTS THREE OF TONIGHT'S OWN CLAIMS. ** seed777 landed (4-band branch,
         phase4/qc/arm_pr_curves_2009_seeds3.md): AUROC .9210 / .9194 / .9163, PR-AUC
         .8632 / .8620 / .8464. SPREAD (max-min, not a sigma — a 3-sample sigma has more
         decimal places than information): .0047 AUROC, .0168 PR-AUC. I had been quoting
         .0016 / .0012 from the n=2 pair. seed777 is the low draw and it widened everything.
         RETRACTED tonight, all three because the gap is now inside the spread:
           - "chm2 is measurably WORSE (-.0057 AUROC, ~3.5x seed noise)" — NO. .0057 is
             1.2x the .0047 spread, i.e. the same size as retrain noise, not 3.5x it. (It
             is not literally "inside" the observed range — say it precisely.) Correct
             statement: chm2 is INDISTINGUISHABLE from the inflated channel. The conclusion
             (fixing the raster buys nothing) stands; the claim that it costs something does not.
           - "PR-AUC registers the damage weakly (.0057 / .0064 at the top doses)" — NO.
             Both are far inside a .0168 PR-AUC spread. Correct statement: NEITHER curve
             metric registers label corruption up to 12.34%. AUROC flat AND PR-AUC within
             retrain noise. That makes the damage-curve finding STRONGER, not weaker.
           - "Node C is ~6x noise" — NO, ~2.5x on AUROC (.0116 vs .0047), and on PR-AUC
             +.0223 vs a .0168 spread is only ~1.3x, i.e. PR-AUC ALONE would not carry it.
             AUROC and the inside/outside split below are what carry it.
         Lesson worth keeping: an error bar from n=2 is a guess. Every A/B verdict tonight
         that sat under ~.005 AUROC was resting on it.
         ** DID NODE C GENERALISE OR MEMORISE? — IT GENERALISED, AND THAT IS THE STRONGEST
         RESULT OF THE WEEK. ** The obvious worry about training on ADDED labels is that the
         model just repeats what it was told. Split the footprint by the overlay itself
         (phase4/qc/nodec_gain_inside_vs_outside_2009.md; 15 m buffer so spillover beside an
         added label is charged to INSIDE, not counted as transfer):
             region                        dAUROC   95% CI            dPR-AUC
             inside (labels added)         +.0043   [+.0032, +.0052]  +.0109
             OUTSIDE (no labels added)     +.0303   [+.0221, +.0378]  +.0259
         Note what OUTSIDE means precisely: ground where BOTH arms trained on the SAME
         labels (the projected 2020 citywide mask; the overlay never touched it). Node C is
         better there by +.0303 AUROC — SEVEN TIMES its own gain inside the labelled region.
         Adding labels on a small area taught it something that transferred to ground it was
         told nothing new about.
         ** CORRECTION TO MY OWN FIRST WRITE-UP OF THIS, SAME SESSION. ** I first called
         +.0303 "~6x the retrain spread". That used the WHOLE-FOOTPRINT spread (.0047) as
         the denominator for a REGION-SPECIFIC gap — wrong, and flattering. The sparse-canopy
         outside region is much noisier. Measured it properly by running the same split on
         the three same-recipe seeds (phase4/qc/regional_retrain_floor_seeds_2009.md):
             region    same-recipe seed gaps vs base      regional retrain spread
             inside    +.0002 , -.0059                    .0059
             OUTSIDE   -.0035 , -.0157                    .0157
         So the honest ratios are:
             inside   Node C +.0043 vs a .0059 floor  -> NOT distinguishable from noise.
             OUTSIDE  Node C +.0303 vs a .0157 floor  -> ~1.9x. Suggestive, NOT decisive
                      at n=1. Real but far weaker than the 6x I first wrote.
         What still stands, and is the part worth keeping: the gain is CONCENTRATED OUTSIDE
         the labelled region, and its sign is opposite to everything seed variation did
         there (both same-recipe reruns went DOWN outside; Node C went up). Memorisation
         would have put the gain inside. It did not. But "generalises" is now a 1.9x
         result awaiting the replicate, not a settled one — and the replicate's
         pre-registration already asks whether this SHAPE reproduces, which is the test
         that matters more than the magnitude.
         Mechanism that fits: inside is canopy-dense and the baseline was already good
         (nodeb AUROC .8855 there); outside is canopy-sparse (PR-AUC only .2747) and is
         exactly the ornamental/suburban under-prediction blind spot this project has been
         chasing since 2026-07-05. The added labels repaired the weakness, not the strength.
         CAVEAT, stated because it is easy to overread: inside and outside differ in canopy
         density, so the two gaps sit in different difficulty regimes — "7x" is a comparison
         of two gains, not a claim that outside improved 7x in some absolute sense.
         THIS IS THE SCALING ARGUMENT: label a modest area, gain across the rest.
         ** THE VALIDATION METRIC MEASURES LABEL QUALITY, NOT MODEL QUALITY — the damage
         curve arriving from a second, independent direction. ** Tabulating phase A/B val
         peaks against independent AUROC for all 10 scored 2009 arms turned this up:
             corrupt50   val_iou_bt peak .6027   independent AUROC .9218  (HIGHEST of any arm)
             clean       val_iou_bt peak .6842   independent AUROC .9210
         Validation collapsed by .08 IoU while discrimination was UNCHANGED. Of course it
         did — val is scored against the SAME corrupted labels the model trained on, so it
         was measuring the label damage, not the model. Two consequences:
           1. Cross-arm val comparison is INVALID whenever labels differ. corrupt*, nodec
              (overlay) and chm2 (different input channel) each validate on different data.
              Only same-label same-input arms can be ranked by val. Written down because the
              table makes it look tempting.
           2. THE SHARP ONE: early stopping AND checkpoint selection both run on this metric.
              On years whose projected labels are wrong, the selection machinery is being
              steered by label error rather than model quality — and we already know the top
              five candidate epochs are tied within noise. That is a mechanism by which
              label correction could matter for SELECTION even where it does not matter for
              LEARNING. Untested; noted as the strongest remaining hypothesis.
         ** WAS THE BAD DRAW DETECTABLE BEFORE WE PAID FOR IT? YES, at n=3. ** Among the
         three same-recipe same-label runs, phase-A peaks were .6797 / .6802 / .6749 and
         final AUROC .9210 / .9194 / .9163 — the lowest phase A (seed777) is the lowest
         final. n=3 identifies the bad draw; it does NOT establish a graded relationship,
         and fullext/seed1234 swap order between the two. Phase A is the cheap frozen-encoder
         phase (~40% of train time), so a phase-A floor is a candidate ABORT-AND-RESEED gate.
         The bigger value is scientific, not economic: a run whose phase A lands below the
         family range should not be used as an A/B data point at all.
         ** LAUNCHES (P11.6, all A100, all autonomous under Kam's all-night grant) **
         gpu33 nodeb_ep60 (done, ~80 min, self-stopped by the watchdog on schedule — 2nd
         proof the /proc-scan watchdog fires) · gpu34 seed777 (training) · gpu35 nodec_s1234
         (Node C replicate at seed 1234 — the week's only positive rests on ONE run) ·
         smooth5 (select-smooth K=5 vs Node B) — NOT YET RUNNING as of 12:10Z, see below.
         All arms carry pre-registered reads in their queue files.
         ** THE SMOOTH ARM'S TWO FAILED LAUNCHES, AND THE TWO DURABLE LESSONS. **
         (1) `colab new -s gpu36` BLOCKED indefinitely — 13 min, no return, no VM created.
         Cause: a runtime needs a free browser-connection slot and both were bound to the
         live VMs. Real concurrency ceiling with current tooling is TWO managed runtimes,
         not the 3-4 in CLAUDE.md. (2) Chained onto gpu34 instead; between 11:41 and 12:00Z
         gpu34's entry VANISHED from ~/.config/colab-cli/sessions.json while the VM was
         still alive and beaconing. `colab exec` returned "Session 'gpu34' not found", the
         chain script EXITED 0 having launched nothing, and gpu34 idled out to the watchdog.
         LESSON 1: a session handle can disappear while its VM lives — verify the handle
         immediately before relying on it, never assume a chain will land.
         LESSON 2 (the one that actually bit): the chain grepped ONLY for success strings
         ("LAUNCHED|flag ok"), so a dead launch and a live one looked identical. Silence is
         not success. Every launcher now greps failure signatures too and checks each stage
         explicitly. Third attempt is a fresh A100 (`Precondition Failed` on first try —
         A100s are scarce right now, the retry loop backs off 240 s).
         ** SEED777 WAS NOT BROKEN, BUT IT WAS NOT ORDINARY EITHER. ** Checked before
         trusting the widened spread: its phase B ran only 19 epochs with BEST AT EPOCH 4
         (vs epoch 21 of 30 for both other seeds) and its peak val_iou_bt was genuinely
         lower (.6785 vs .6852 / .6842) — validation agrees with the independent score, so
         this is a real convergence outcome, not a scoring artefact. So the .0047 spread is
         honest, but it is driven by ONE RUN CONVERGING EARLY TO A WORSE OPTIMUM rather than
         by uniform jitter. Operationally that is worse than symmetric noise: roughly 1 run
         in 3 landed badly, so a single-run A/B can lose to a bad draw rather than to a bad
         recipe. Argues for repeating any arm that is going to be promoted.
decided: verdicts come from CURVE metrics (AUROC / PR-AUC), never matched-precision recall —
         I read every verdict off recall for a week despite writing the rule myself. Recall is
         ~3x noisier (3 pp swing from seed alone vs .0016 AUROC).
next:    score nodec_s1234 (pre-registered: within ~.002 of .9179 = replicated; back near
         .906-.909 = the original was a lucky draw and must be reported as loudly as the
         positive was) · seed777 -> report n=3 as a SPREAD (max-min), not a sigma, and note
         it is Node-A-branch, a proxy for the 3-band comparisons · smooth5 vs Node B ·
         4-band family (Node A / corrupt10-25-50 / chm2 / seeds) re-scored on curve metrics,
         running local · PARKED for Kam: a systematic-ERASURE corruption arm (Node B vs C is
         already that contrast, and erasure fights rule 6 ADD-ONLY — dose-response only).

## 2026-08-28  FACT TREE — Node B measured (CHM worth 10 pp), crown-touch built, damage curve launched (Fable 5 session)
goal:    Kam's rule, adopted after three uninterpretable experiments: "change ONE thing at a
         time from a previously established position of fact." Build the tree.
did:     ** NODE B ** 2009 / projected key / 3-BAND (--no-hillshade): AUROC .9063, PR-AUC
         .8365, matched-precision recall .5990 vs Node A's .6989. So THE CHM CHANNEL IS WORTH
         10 pp OF RECALL — a clean number this project did not have.
         ** AND ITS VALUE IS CONCENTRATED IN SMALL CROWNS ** (crown-touch, Node A vs B, true
         EPSG:26910 areas): 0-5 m2 .4298/.3568 (-7.3 pp) · 5-10 .5386/.4587 (-8.0) · 10-25
         .7353/.6709 (-6.4) · 25-50 .9044/.8680 (-3.6) · 50-100 .9765/.9646 (-1.2) · 100-250
         .9942/.9912 (-0.3). Height barely helps big trees and does nearly all its work on the
         population the project fails on. A pixel aggregate cannot show this.
         ** qc/phase4_crown_touch.py (f1e6c06) ** — Kam's idea: the 222,435 instance crowns are
         never seen by citywide training, so they are a free held-out set. TRUE for the
         citywide path, FALSE for any arm using --add-canopy-mask: our label-correction
         overlays RASTERIZE stable_crowns_v0.gpkg as forced canopy, so scoring those arms on
         crown touch would drive them toward 1.0 BY CONSTRUCTION. The tool therefore reads each
         arm's own run manifest and classifies clean / add_overlay (auto-excludes 2,307
         crown_ids + 5,184 in the Forest polygon) / site_crowns (refused) / unknown (refused).
         Refusal tested live. Verdict on the metric: a RESTATEMENT at the headline level, but
         it localizes (by size, by sector) where pixels cannot.
         ** TILE CACHE COLLISION FIXED (507dff6) ** — see the retraction below.
decided: TWO EXPERIMENTS IN PARALLEL, because neither answers alone.
         (1) DAMAGE CURVE — stop trying to FIX unknown errors, INJECT known ones at a dose we
         choose. Whole real crowns displaced 10-40 m onto key-background, painted canopy (code
         1 only, rule-6 legal, no engine change; erasure is untestable — rule 6 forbids
         force-background). Doses 2.70 / 6.56 / 12.34% of strip land = 4x-18x the arm that
         nulled. Gives COST PER UNIT OF LABEL ERROR, the number that makes every correction
         experiment interpretable.
         (2) NODE C — one variable vs Node B: proven canopy additions only (datum-matched
         2005>=3.0 m -> 2016>=4.52 m, NDVI>=0.30 from the 2016 4-band ortho NOT the 2009
         imagery, buildings out, erode 1, no change classes, no IGNORE).
killed:  ** MY OWN PRE-REGISTRATION OF NODE C AS 'LIKELY NULL'. ** I forecast ~0.85% dose from
         a denominator-confused comparison (the 563/700/959 ha problem, WORKPLAN 1.5). Measured:
         21.94 true ha = 3.897% of graded strip land, 100% effective flips. AND the hybrid that
         produced the "clean null" was 85% NO-OP — only 2.98 ha of its 20.26 ha landed on
         key-background, plus 4.61 ha of IGNORE, so it was never one-variable. Node C is 7.4x
         its EFFECTIVE dose. Quote the hybrid as "0.53% effective, two variables", never "0.7%".
         Also measured en route: 78.2% of lidar+green candidates land where the key ALREADY says
         canopy — the borrowed key is more right than assumed on persistent tall green ground.
files:   507dff6 tile isolation · f1e6c06 crown-touch · be4f2e4 crown-touch report · 7c7ea90
         damage arms + injector · 332b9c4 --nodec · 6b0743c Node C queue · a9bc443 Node B queue
next:    score 4 arms at matched precision + crown-touch by size; the DAMAGE CURVE SLOPE is the
         result. Flat at 12.34% = no achievable correction ever mattered, close the thread and
         spend on references/definition instead. Steep = labels are the lever and Kam's
         annotation time is the highest-value input in the project.

## 2026-08-28  GROVES VERDICT — SPARSE VERIFIED LABELS LOSE DECISIVELY; Kam's lidar signal is REAL inside the losing arm
result:  2009, common footprint 198.8 Mpx (intersection of all 3 arms x scorable ref), ccap
         snohfull. THRESHOLD-FREE (qc/phase4_arm_pr_curves.py, ea5f205):
           fullext (projected key)  AUROC .9210  PR-AUC .8632
           groves_nolidar           AUROC .8986  PR-AUC .8095
           groves_lidar             AUROC .8887  PR-AUC .7855
         MATCHED PRECISION (=.8472, the baseline's @0.5) — the decisive table:
           fullext .6989 recall · groves_nolidar .4420 · groves_lidar .4885
         21-26 pp below baseline against a .0100 recall sd = ~26 sigma. NOT close.
         The fixed-0.5 "recall win" for nolidar (.7503 vs .6989) was a CALIBRATION
         ARTIFACT — that arm just sits at a more liberal operating point.
         (b) ** RETRACTED 2026-08-28 — DO NOT QUOTE. ** This entry read "KAM'S LIDAR
         NEGATIVES WORK AS DESIGNED, +.0465 recall at matched precision over nolidar".
         VOID: the two arms ran CONCURRENTLY on year 2009 and the tile cache was keyed by
         year only (TILE_DIR/{label}, no run tag), so they raced on ONE directory —
         nolidar tiled 21:28-21:54, lidar 21:36-22:05, 18 min overlap, 635 vs 599 tiles.
         Both models trained on an unknown mixture of each other's labels, so B-vs-C
         compared nothing. The +.0465 is now best read as an accidental SAME-DATA
         replicate gap = >=4x the banked recall sd .0100 (n=1 pair, one early-stopped
         ckpt — a warning, not a measured sigma). Kam's lidar idea is UNTESTED, not
         disproven. Fixed 507dff6 (per-arm tile dirs). The A-vs-B/C headline SURVIVES:
         that effect was 21-26 pp and both arms lost. (c) NEW FINDING: sparse labels BREAK CALIBRATION. Both sparse arms park
         ~31% of valid px within +-0.01 of 0.5 (baseline 10.9%) and push 4-7% to >=0.99;
         trained on 15-21% graded pixels they learned confidence on a little and abstention on
         a third of the scene. VERIFY caught it first: maxprob 1.000 vs baseline .878.
decided: the experiment CONFOUNDED "verified labels" with "FEW labels" — a design fault of
         mine, not of Kam's idea. The separating test is a HYBRID: keep the projected key and
         OVERWRITE it only where verification exists (groves -> canopy, lidar-flat/buildings ->
         background), IGNORE nowhere. That isolates label CORRECTNESS from label QUANTITY and
         is the obvious next arm. Note it needs a force-background path, which rule 6 forbids
         via overlays — so it is a label-builder change, not an overlay code.
         Also: any sparse-label arm must have its threshold re-selected on its own curve;
         never compare one at a shared fixed cut (Method_Pipeline operating-point protocol).
files:   ea5f205 curves · 9de70d9 code-3 + overlay builder · c945619 lidar background
         · scratchpad arm_pr_curves_2009.{md,png}
cost:    ~2 A100-h across the quota-killed attempt and the rerun. Both VMs stopped.
next:    hybrid arm (isolates correctness from quantity) · the baseline's own 10.9% mass at
         0.5 is worth a look · AOI block-leak (WORKPLAN 1.5) before any "% of strips" claim.

## 2026-08-27  STABLE-GROVES EXPERIMENT — BLOCKED ON COLAB QUOTA (both arms lost mid-train)
goal:    Kam-approved: does a SPARSE VERIFIED key beat the projected 2020 key on 2009?
         arm A baseline (have it): rec .6989 prec .8472. arm B groves+buildings.
         arm C = B + Kam's lidar hard negatives (flat in BOTH 2005 and 2016 lidar).
did:     Kam's lidar idea BUILT and validated: qc/build_lidar_background.py, erode 2 cells
         chosen by an independent CHM cross-check (contamination 20.7%->4.4% at 1->2 cells).
         PSLC 2005 density MEASURED 1.68 pts/m2 median (n=46 tiles) vs 0.25 documented — ~7x
         understated, answers WORKPLAN sec4 Tier2 item 8's precondition (IMAGERY_FACTS 8.1).
         Engine: overlay code 3 = unconditional IGNORE (rule-6 compliant; rule permits adding
         IGNORE, forbids only canopy->background) — needed because code 2's `!= 1` guard
         cannot withdraw the projected key's canopy claims. SHIPPED HALF-LANDED: the reader
         additions_from_mask didn't pass code 3, so both arms would have equalled baseline
         and measured NOTHING; caught by an agent round-trip test, fixed (9de70d9).
         Water EXCLUDED from both arms: 78% of negative px, makes C-vs-B a +8.6% change
         instead of +55% — dilutes the contrast the experiment exists to measure.
         Overlays: lidar arm grades 20.9% of strips vs 14.6% nolidar. Both arms retiled OK
         (635 / 599 tiles) and trained.
killed:  BOTH VMs reclaimed ~2 h in, within minutes of each other. Cause is ACCOUNT-LEVEL:
         `colab new --gpu A100` AND `--gpu L4` now both return "Backend rejected accelerator
         … you may not have quota or entitlement". COMPUTE UNITS EXHAUSTED — not a code fault.
         Survived: sem_best_2009_groves_nolidar.pt (773 MB, best at 28 min, converged — train
         ran 40 more min with no improvement). Arm C produced no checkpoint. No rasters, so
         NO VERDICT.
         Self-stop watchdog (f3e5dae) found INERT and fixed (9fe5d6c): `pgrep -f <pat>` spawns
         `/bin/sh -c pgrep -f <pat>` whose cmdline contains the pattern, so it always saw a
         running queue and could never fire. Now a /proc cmdline scan skipping its own pid.
         It did NOT cause the losses.
next:    KAM: top up Colab compute units. Then ~1 GPU-h finishes it — arm B needs inference
         only (~10 min from the saved ckpt), arm C needs retrain+inference (~45 min).
         Also owed: Web-Mercator AREA sweep — EPSG:3857 areas at this latitude are inflated
         2.215x (groves 22.9->10.3 ha, Forest 70.1->31.6, lidar-bg 44->~20); same bug class
         as the gsd_cm defect, and it corroborates the 959-vs-563 ha strip discrepancy.

## 2026-08-27  PoC DELIVERABLE ASSEMBLED — per-crown validity intervals, 8-year ladder (Fable 5 session)
did:     Sweep completed WITH 2024 (219 rows; 2024_fx P_hat .379 +/- .150) -> matrix rebuilt
         -> groves re-mined 2,307 (8 yrs evidence) -> qc/build_validity_intervals.py (23402e2)
         run on the full ladder (2000/2007/2009/2013/2016/2018s/2021s/2024, fullext arm rail).
         38,642 crowns: STABLE_PRESENT 14,869 (38.5%) · INSUFFICIENT 11,118 (28.8%) ·
         FLICKERING 4,422 (11.4%) · ESTABLISHED 3,946 (10.2%) · PRESENT_WITH_GAPS 2,897 (7.5%) ·
         ABSENT_ALL 1,034 (2.7%) · LOST 356 (0.9%). Median span 24 yr (n=26,490).
         sigma_fragile 2,324 (6.0%). Cutoff sensitivity table in the script output (0.40/0.10
         and 0.60/0.20 move ~2.1k/2.3k crowns). Both GPKGs copied to ARCGIS\MachineLearning\.
         SIGMA MEASURED, NOT DERIVED: per-crown sd from the 5 noise-repeat cover columns is
         ~0.000 in the confident bands, .083 in the 0.15-0.50 band — noise lives exactly where
         the three-state rule already abstains (independent validation of that design).
         Operating-point protocol landed in Method_Pipeline.md (1f7ab6d): best-F1 REJECTED as a
         deployment rule (argmax .440-.499 for ~.001 F1 = ~2 sigma of recall for nothing);
         deploy fixed-0.5 or precision-floor; repeat years = ensemble-then-threshold with the
         threshold re-selected on the ensemble curve; comparability rails written down.
         Killed a DUPLICATE concurrent sector_series process (two writers, one CSV — orphan of
         a chained background task the harness had already marked complete).
decided: ESTABLISHED is NOT quotable as establishment dates yet — rate per gap-year varies 8x
         (2013: 74/yr vs 2018s: 594/yr), a real establishment process would be smoother; it is
         part real, part early-year model under-call. Gate = the stable-groves A/B.
next:    stable-groves prototype labels + ~1 A100-h A/B · FUSE-bypass (staging reads + ckpt
         saves) · PoC write-up · U1 canopy definition D1/D3-D6 still open (WORKPLAN section 3).

## 2026-08-27  PoC COMPUTE CLOSED 6/6 — 2024 landed attempt 5; handle discipline; model switch to Opus 5 (Fable 5 session end)
did:     2024_fx complete + scored: rec .6400 prec .7860 @0.5 (train 35 min on healthy
         VM — prior "2.7h trains" were mount-degraded). Full PoC table (fixed 0.5,
         C-CAP, sample footprint): 2000 .590/.920 · 2007 .624/.871 · 2009 .699/.847 ·
         2013 .631/.890 · 2018s .646/.785 · 2024 .640/.786. 2024 cost 5 attempts:
         VM freeze ×2, D-state FUSE hang on job re-verify ×2 → queue fixes b44a6a8 +
         20d8f9c (job-level VERIFY OK now enters done-set; skipped jobs never re-read
         rasters — PROVEN: attempt 5 reached train in 1 min). Colab CLI handles die
         permanently from overlapping/killed colab.exe (4 lost; memory rule: serialize,
         generous timeouts). VM SELF-STOP watchdog in bootstrap (f3e5dae) — fired-adjacent
         on gpu5; zero sessions, zero leak. Ensemble verdict: stability-not-accuracy
         (same-seed errors correlated; ensemble-then-threshold = operating rule for
         repeat years, threshold re-selected on ensemble curve). Synthetic imagery
         PARKED ×2 (memory holds Lanaras/Braga/ACCESS-upgraded phase plan + free
         tile-ratio diagnostic: 512px tile = 77 m at 15 cm vs 512 m at 1 m). GitHub
         cleaned: Kam merged 105 commits to main; stale branches pruned.
next:    (Opus 5) sweep bv2kt8jdv finishing → crown_cover_matrix → mine_stable_crowns
         --gpkg → copy gpkg to ARCGIS → PoC ASSEMBLY (intervals, 38,642 crowns, sigma
         error bars) → operating-point protocol doc → stable-groves prototype A/B
         (~1 A100-h, approved) → FUSE-bypass engineering (staging reads + ckpt saves).

## 2026-08-27  OVERNIGHT PoC — 5/6 years landed + scored; sigma n=5 banked; stable groves 2,309 (Fable 5 session)
goal:    Kam-approved PoC (6-9 A100-h): complete product inside strips. "Fire without
         permission" + overnight parallel runtimes granted.
did:     noise n=5 COMPLETE — recall sd .0100 (range .0283), precision sd .0052, SAME
         seed (LOWER bound). Verdict: fullext promotes over base2020 on converging
         evidence (hand-truth + campaign); fullext-vs-p2nir UNDECIDABLE (~1.5 sd matched
         footprint). Threshold wobble .440-.499 across identical runs (flat F1 plateau)
         → operating-point protocol owed. PoC years trained+scored @0.5 vs C-CAP sample
         footprint: 2000 .590/.920 · 2007 .624/.871 · 2009 .699/.847 · 2013 .631/.890 ·
         2018s .646/.785. 2024 pending (3 stalls, all FUSE-mount freeze class). Chain
         ran: series sweep 209 rows → matrix 47 cols → stable groves re-mined 2,309
         (16 borderline expelled by new evidence). Kam: 0.8 floor locked; hand-declared
         70.1 ha Forest site (838 crown overlap). Three refutations (roof/fusion/shadow
         agents): every dissected FP/FN population = vegetation-class ambiguity at
         margins → label-limited CONFIRMED empirically. Shadow probe found ~5 m east
         ortho-vs-CHM displacement (crown lean + registration). NIR M06 CLOSED: tie
         2016, dominated 2019n → CHM stays; NIR value = normalized-NDVI change work.
         Queue fix b44a6a8: skipped jobs no longer re-read rasters (D-state hang).
decided: no VM creation with degraded CLI handles at night (3 lost handles); rerun-on-
         contamination applied to trashed/frozen ckpts throughout.
files:   b44a6a8 queue fix · 6eaa2ff mine_stable_crowns · 9211f79 evidence scripts ·
         queue_poc_{a,b}.yaml · ANNOTATION_WORKFLOW.md + SAM.dlpk + hotspots (ArcGIS)
next:    2024 attended rerun (Kam) → score → PoC assembly (validity intervals 38,642
         crowns) · ensemble experiment · operating-point protocol doc · FUSE-bypass for
         ckpt saves + staging reads (the remaining reliability gap) · stable-labels
         prototype A/B (~1 A100-h) · S2 calibration pilot.

## 2026-08-26  INFRASTRUCTURE DAY — writer mount fixed, transports bulked, noise n=5 in flight (Fable 5 session)
goal:    Kam workday mandate: NIR training + radiometry + building-ID infrastructure; max
         hardware utilization; oversight tools.
did:     SA zero-quota diagnosis (uploads silently failed server-side; folders yes files no)
         → user-token writer mount + write canary v2 (server-side md5 via SA) in
         gen_vm_bootstrap.py. Oversight suite: vm_heartbeat.py + qc/runtime_health.py +
         dashboard CPU/RAM/data-flow. Tiling bulk-write (tiling.py 71ee388): local stage →
         one rclone copy --checksum → check --one-way → FUSE-visibility gate → meta LAST;
         VALIDATED live 2016 retile 26.8 min. copystat EIO killed noise r2 train epoch 24
         → copyfile + best-effort copystat (common.py 457bc85), both VMs hot-patched
         mid-queue before next train. Staging lock retuned ≥4GiB/15min. NIR M06 arm
         (band-4 hs-source) queued + training. Noise r1 OK, r3 running, B queue (nr2r
         rerun+r4+r5) chain-launches on warm VM. Buildings: citywide roof matrix
         1728/1728 → per-year masks rebuilt. CI green on pushed branch.
decided: watchers read phase4/qc status CSVs only — live nohup files invisible server-side
         until close (VFS uploads on close); filenames discovered by lsf glob, never
         reconstructed (bitten ±2s thrice). Chain-launch git-fetches fixed HEAD (queue
         boundary = code cutover; mid-queue only exact-match hot-patch of landed commit).
killed:  lsjson --hashes canary (flag absent on VM rclone, false-failed good upload);
         nohup-log watchers ×2; per-file FUSE tile writes (~10 s/tile).
files:   common.py 457bc85 · tiling.py 71ee388 · gen_vm_bootstrap.py · queue_noise_2021s_b.yaml
         272ab1c · queue_nir_m06.yaml · vm_heartbeat.py · qc/runtime_health.py
next:    noise sigma (n=5, hardware-nondeterminism LOWER bound) → fullext promotion verdict;
         NIR arms score C-CAP only; golden-v2 on next warm GPU; Kam: champions + main merge.

## 2026-08-26  CAMPAIGN CLOSED — fullext ran (~1h45m A100); promotion UNDECIDABLE; runtime autonomy DONE (Fable 5 session)
goal:    finish the sector campaign + Kam's runtime-autonomy directive
did:     fullext queue complete (2016_fx VERIFY OK 61MB/11.6%; 2021s_fx 182MB/11.0%); A100 stopped at once.
         Scored 8/8 arms — per-ARM lineage HELD (4 pre-existing 2016/2021s live rows intact). 2016_fx rec .6163
         prec .9119 (best grass_rej .9693); 2021s_fx .6568/.8276 vs p2nir .6851/.8547 — UNDECIDABLE (footprint +
         operating-point confounds + no noise sigma). Fine-tunes give 2016+2021s their FIRST 5-sector totals:
         P_hat .383 CI[.208,.558] / .385 CI[.237,.532]. All 8 arms postproc'd. S22/S23 regenerated (149-row
         series, 28 totals, 38,642x35 matrix). S24 report = reports/SECTOR_CAMPAIGN_REPORT_2026-08.md (agent
         draft, cross-checked: area_ha was P_hat x SAMPLED 563 ha -> renamed canopy_ha_sampled; champion
         eligibility rule = full-footprint only; fullext rows added to registry+launches ledgers).
         RUNTIME AUTONOMY (Kam-directed): GCP project edmonds-pipeline + SA treedata-mount, key in
         D:\edmonds-pipeline\secrets\, treedata folder-share, Drive API — all via browser automation with
         Kam present. rclone mount canary PASS (fuse3 auto-install + --allow-other removal = the two measured
         root causes, encoded in pipeline/gen_vm_bootstrap.py). Full unattended lifecycle proven on a virgin
         VM (BOOTSTRAP_READY, zero clicks). P11.6 in CLAUDE.md pending Kam merge. Kam's allowlist live.
decided: promotion waits on the noise arm (P11.5 ask); sector arms champion-INELIGIBLE (test, not deliver);
         city-area ha expansion deferred until city land area measured (P_hat/CIs always correct).
killed:  "NIR-vs-RGB per-crown cover" framing (2021s_p2nir NIR medians 0.0000 too — separator is GSD>=60cm
         OR precision<.55) · "~8 wasted A100-min" (measured 6.2).
files:   report + harvested series/totals/columns/golden CSVs; commits through db7d8d8+.
next:    Kam: push (2 ! commands), 6 champion picks, noise-arm approval, P11.6+branch merge. Then Pillar 3
         (M01/M03/M06-M08/M12 arms on the proven harness).

## 2026-08-25  E-BACKLOG LANE 1 — 8-agent adversarial verify corrected EVERY top-8 practice item; 6 landed (Fable 5 session)
goal:    Kam: industry best-practice review, "full inference doesnt sound smart in terms of money and time"
did:     3 research passes (internal inventory, external sweep, 8 opus verifiers vs live code). Landed:
         E01 registry joins status on `year` not job id (sector campaign got ZERO timing before; SEEDED rows excluded) ·
         E02 _copy_to_drive stages .part.{pid}{token} + verify + os.replace (kills truncated-final + good-artifact-unlink bugs) ·
         E03 CI (.github/workflows/ci.yml, qc/test_ci_gates.py, constraints-ci.txt; 16 tests green) ·
         E05 pipeline/champion_arms.csv + qc/champion.py; dashboard/pipeline_status/series/crown-matrix fail loud, no last-wins ·
         E06 manifest `labels` block; canopy_additions lineage.json (2016 backfilled read-only, sha256 c664c1c8…, build 2026-07-05) ·
         E08 audit Hygiene #16 corrected (NO output overlap exists — write crops tile exactly); new #18 UNCHECKED
         hard-fail, #19 eval-row clobber (year,channels), #20 stale INFER_BATCH_SIZE=160.
decided: patterns-not-products (no MLflow/DVC/Lightning/Snakemake — bespoke already covers); base2020 thr=0.5 =
         pre-registered baseline operating point (M01 owns the real protocol); champion promotion gate deferred into M04
         behind measured noise arm.
killed:  gaussian blending + inference stride cut (false premise: zero output overlap; breaks scored footprint mid-campaign) ·
         tile-based golden set (circular AND inverted vs projected-2020 labels) · registry status column (append-only contract) ·
         train-resume-by-default (0.7 GPU-min lost ever vs 3+ GPU-h in tile/inference → E10 inference resume is the payer).
files:   commits 275511e a238264 287add8 c64a408 2288159 890e97e b917834 on work/20260824-sectors; plan file = the E01-E10 backlog.
next:    E04 cost layers + E07 golden gate (agents, in flight) · E02 drivefs smoke + CI push + 6 champion
         designations = Kam asks · Lane 3 noise arm = first GPU ask after fullext.

## 2026-08-25  SECTOR BASELINE LANDED — 6 arms inferred+scored on A100; both VMs died; fullext at epoch 2 (Fable 5 session)
goal:    run the approved sector campaign (base2020 baseline + fullext fine-tunes) loop-autonomously overnight
did:     base2020 queue: seed-CSV chain fixed (col `job` not job_id; UTC ts; Drive-lag race → VM-side self-seeded
         launch), 3rd launch clean — 6/6 inference VERIFY OK (valid 11.6-16.7%, sizes 8.8MB-563MB); scored vs
         epoch-matched C-CAP (rec .34-.64; prec .70-.82 late years, COLLAPSES .44 on 2006s/2011s — un-adapted
         model + 10-13yr ref gap, now quantified); postproc masks 5/6. qc_indep supersede made per-ARM (commit
         3e7ac30) BEFORE fullext scoring could flip citywide 2016/2021s live rows — caught with zero damage.
decided: 0.5 fallback rows stand as baseline operating points (≈phase3's 0.5026 calibration); loop NOT restarted
         until GPU back (S12 failed-blocking by design).
killed:  scoring-before-lineage-fix (killed task bvnarz607 ~2min in; 2006s/2011s rows were new year-keys, no flips).
files:   train_queue_status_queue_sectors_base2020_*.csv · masks/edmonds_canopy_{prob,mask}_*_sectors_v1.tif ·
         data:phase4/qc/sector_campaign/{state_*.jsonl,RESUME_NOTES.md} · ~8 A100-min wasted total on 2 seed runaways.
next:    Kam 2-step GPU resume → loop restart → fullext (labels+tile OK, train restarts) → score-all AGAIN before
         loop hits S20 (its verify passes on base rows alone) → S21-S24.

## 2026-08-23  ACQUISITION CAMPAIGN BATCHES 1-2 — 9 rasters; 2016+2002 replaced; NIR 4->8 (Fable 5 session)
goal:    Kam: download ALL imagery, multiple per year, upgrade to 4 bands, replace only MEASURED-better. Rewrite dead
         unified_downloader (15-defect review in plan); agentic loop: bottleneck -> diagnose from ledger -> improve -> resume.
did:     Engine pipeline/acquire_imagery.py ~1000L (snapped grid+nearest proven nearest==bilinear 0 diff; per-chunk sha256
         ledger; gap report exit 2; assemble BigTIFF+overviews+provenance tags; --via download; token-bucket limiter; status
         verdict taxonomy) + qc/imagery_measure.py (exact-unit true GSD; effective ESF; band4 ALPHA/NIR; jpeg 8x8; common-grid
         compare; decide()) + 12 offline tests green. Batch1: S16 native-1ft full extent REPLACE (city 100%, common-grid HF
         1.01 vs upsample = same source pixels, provenance win); N15/N17 NAIP. Batch2: U02 = WAGDA Download capability ->
         39 ORIGINAL USGS HRO tiles (75,121,662 B each) -> mosaic 2002_usgs_30cm_rgb.tif REPLACE (common 40cm grid: eff
         56.25 vs 90.86 cm, HF 1.538, block signature ABSENT vs held PRESENT, PSNR 27.5, r .979); M18 marsh drone (2.51 cm
         true, eff 3.08 cm marsh-centre; band4=ALPHA -> _rgb; singleFusedMapCache re-renders -> pilot_waiver, display-cache
         copy accepted); S17/S19 county HXIP 1-ft 4-band (Aug 2017 2-day, Oct 2019; NIR NDVI p90 .67/.61; 234 chunks 0 fail
         each). N21 NAIP 60cm. CC16 closed ZERO download (vsicurl header + 3 windows byte-equal to held _snohfull). Catalog:
         2016+2002 flipped (SUPERSEDED_FILES), keys 2015n/2017n/2021n/2017s/2019s added; check 23/23; table 37 rows gate 0
         misses; IMAGERY_FACTS §10.1-10.6; catalogue sheets flipped per file. Mirrors: batch1-2 on both planes size-verified.
decided: replacement = lexicographic decide() common-grid only (native rise metric floors ~1px, flatters upsamples);
         coverage floor city-polygon >=99% AND study >=80% (extent ~83% land — first S16 REJECT was my bad threshold);
         check Download capability BEFORE chunk-export (original tiles beat any render); NOAA host-cap -> don't tune streams.
killed:  WGS84-span true-GSD (over-reads rotated grids 2.5% — exact unit conversion now, span kept as span_gsd_cm only);
         15000px strips on snoco (HTTP 500); compression=LZ77 on snoco (ignored); byte-faithful CoE cache copy (re-renders).
files:   pipeline/acquire_imagery.py, pipeline/imagery_acquisition_manifest.json, qc/imagery_measure.py,
         qc/test_acquire_imagery.py, pipeline/mirror_sync.py (_parse_manifest dual-format), qc/phase4_catalog_check.py
         (SUPERSEDED_FILES), phase4seg/config.py (2 flips + 5 keys), scratch/imagery_pixelsize_date_campaign.py,
         scratch/imagery_catalog_flip.py, IMAGERY_FACTS.md §10, IMAGERY_ACQUISITION_ASKS_2026-08-23.md,
         D:/edmonds-pipeline/Imagery/{SnoCo,USGS_HRO,NAIP_NOAA,CoE,CCAP}/. Branch work/20260823-acquire.
next:    batch3 in flight (S21 REPLACE test vs 20.6cm clip + S15 3-band); CC21 clip + class-equality gate, STAYS quarantined
         until NOAA ask (d); batches 4-6; S20/S22/S24 300m pilots then per-year OK; Kam: send 4 asks, empty Drive trash,
         2017-dup decision; King K00 ★ on reply. Drive mirrors batch3+ AFTER trash emptied.

## 2026-08-23  PIXEL SIZE + DATE SHOT — one table, every acquisition, every cell cited (Fable 5 session)
goal:    Kam: true pixel size (4 senses) + date shot for every held acquisition, each with a documenting link; lateral search.
did:     In-file sweep first (rasterio all domains + tifffile raw tags, 33 rasters): NULL — no DateTime/Software/XMP/
         IPTC/EXIF anywhere; grids are exact Web-Mercator LODs (tile-cache exports). City-POLYGON re-query of 9 King
         frame indexes (2021 narrows to Apr 14-17; 2017 "May 18" = bbox artefact). Snohomish mosaic catalogs: 2016
         native 1 ft (LowPS=1), 2021 0.5 ft, 2020/22/24 0.25 ft; held 2016 pixels = service, distinct from 2015/2017.
         9 Opus agents (Workflow, max effort) + 7 verify agents, 870 tool uses: 2017_coe = same orthomosaic as
         2017_king (r 0.957-0.997, 66 windows) -> dated; 2000 -> 2000-06-26 (only Wayback capture of the flight-date
         graphic, re-read by lead); 2022_coe MrSID input-set byte-identity with Everett -> PUBLISHED; 2015 CoE contest
         dissolved into 3 products (Aug 7 = NAIP/HXIP per Davey 2018; King leg pixel-excluded; Apr 8/17 consortium,
         NO Apr 9); InPort 53263 recovered as XML; NAIP-2021 over Edmonds exists (2021-07-13 inferred); HXIP SDATE
         is LOCAL (UTC hypothesis killed); weather: 30-deg sun floor falsified by 2015-02-15, calibrated rule 46/46;
         shadow geometry: azimuth reliable (2012 control 8/10), elevation saturates -> 2020 one-pass signature, no day.
         Table v1.1: 29 rows; quote gate 0 misses vs fetched pages only (after catching my own composed quotes).
         IMAGERY_FACTS 9.2 -> delta + pointer; Contradictions/Provenance_Chain/Dating_Methods stamped SUPERSEDED;
         3 Retractions added (14). Evidence harvested: qc/imagery_date_evidence/ (raw index records, weather
         shortlists, shadow results, the 2000 graphic, agent findings + dead ends).
decided: sheet ADDED via adder script, NOT build_master_catalog.py (a rebuild drops the 10 appended sheets) — deviation
         from the brief, deliberate. 2022 INFERRED->PUBLISHED because identity is measured and the window is published
         for that measured-identical product. 2020 stays INFERRED. 2016 stays INFERRED (county 1-ft <-> consortium 15 cm
         link presumed). Reference rasters get flagged rows, not silence.
killed:  per-frame date from the Snohomish service (catalog = 2 whole-project items; schema has no date field);
         WA consortium flight-date layer for 2021+ (series ends 2020; all 68 services enumerated); neighbour-city 2020
         date (Everett JPEG2000 has none; no 2024 neighbour copy); Legistar for 2020/2022 contracts (record starts
         2023); /info/keyProperties on 10.81 servers (400s on the positive control — any earlier null via it is suspect).
files:   qc/imagery_pixelsize_and_date.csv, qc/imagery_date_evidence/*, scratch/imagery_pixelsize_date_{build,sheet,
         quote_gate,supersede}.py, imagery_catalog_2026-08-22.xlsx (24 sheets), IMAGERY_FACTS.md 9.2, CHATLOG STATE.
next:    Kam: (1) PRR text ready (see session report) -> Snohomish DoIT, pins 2020/22/24; CONNECTExplorer ask to Brian
         Tuley is faster. (2) Decide on the C-CAP v2 ML-use clause. (3) Query ORTHO_IMAGE25_AREA_3074 over the city
         (2025 dates, free). (4) 2002 Edmonds date via EarthExplorer M2M. (5) merge work/20260823-pixelsize-date.

## 2026-08-23  SERIES COMPLETE — four years scored; registry joins on the RASTER, not the clock
goal:    post-merge tidy-up on a branch off the new main (dff4adb): harvest, registry rows, the
         WORKPLAN task for the inference gate. Merge itself was scripts-27's; main is not mine to move.
did:     branched work/20260823-post-merge off dff4adb, verified independently that main carries my work
         (14e70aa, 84c935a, 5500048, ec39e32) and that registry_from_manifests.py on main is the 305-line
         fix/ version with the date-filtering intact. Harvest copied 21 measured files (incl. the 2017
         qc_indep outputs and the peer session's renamed 2023n artefacts). Registry: +4 rows for 2017.
found:   ** THE REGISTRY WAS JOINING HONEST NUMBERS ON A CLOCK THAT DISAGREES WITH ITSELF. ** The queue
         writes status rows in UTC on the VM; qc_indep runs LOCALLY and writes LOCAL time. Measured on the
         same run: manifest ts_utc 22:02:31Z vs qc_indep ts 17:29:20 local - a 7 h skew that made tonight's
         scoring look OLDER than the run it came from, so my date filter (added hours earlier to stop the
         opposite bug) silently withheld 2017's row. FIX: join on the `prob` column instead - it names the
         raster that was scored, which IS the artefact the run produced. Exact, and timezone-immune.
         Also fixed: the join took the LAST matching row, i.e. forest_wetland_scrub; the report marks a
         PRIMARY definition (forest_wetland) and that is the headline. It now prefers primary and labels
         the number NON-PRIMARY if it ever has to fall back.
         LESSON, general: two writers on two machines means two clocks. Join on identity (a filename, an
         id), never on a timestamp, unless one writer owns both ends.
numbers: ** ALL FOUR YEARS, honest, live=1, each at its OWN deployed threshold — NOT a model ranking **
         2017  rec .7058  prec .9007  @0.4986  vs ccap_2016_hires_lc_snohfull (FULL coverage)
         2019  rec .6346  prec .8242  @0.332   vs ccap_2021_hires_lc (CLIPPED)
         2022  rec .6818  prec .8012  @0.4988  vs ccap_2021_hires_lc (CLIPPED)
         2024  rec .6170  prec .8239  @0.5043  vs ccap_2021_hires_lc (CLIPPED)
         TWO CAVEATS, both easy to misquote: (1) 2017 alone sits on the full-coverage reference; WORKPLAN
         1.3 measures the clip as costing 2-5 pp of recall, so ".7058 vs .6170" is NOT a 2017-beats-2024
         result - same failure class as the 2021k/2023 caveat already in WORKPLAN. (2) 2017 posted the BEST
         honest numbers on the WEAKEST held-out IoU (.6125 vs 2022 .7300, 2024 .7142, 2019 .6879) - that is
         WORKPLAN 1.1's "model strength does not predict honest recall", now reproduced on four fresh runs
         rather than asserted from history.
         emergent_wetland is the one reproducible weak non-canopy group on the 2021 reference (.4929 /
         .5558 / .5635) but only .1648 for 2017 on the 2016 reference - consistent with a
         reference-definition artefact rather than a model failure. NOT TESTED; worth a deliberate test.
         Scrub recall stays the weakest canopy class everywhere (.2208 / .2796 / .3542 / .4138).
done-2013: ** 2013 CITYWIDE RE-SCORED — and the expected movement DID NOT HAPPEN. ** primary forest_wetland
         rec .7399 prec .8681 @0.5026, grass_reject .9140, ref_canopy 29.19%, vs ccap_2016_hires_lc_snohfull.
         The prediction was that it would move off the quoted .7422 because that was a live=0 row scored at the
         fallback 0.5. It did not: the off-recipe xsensor raster scored .7395/.8666 and the citywide raster
         scores .7399/.8681 — a 0.0004 difference in recall. So for 2013 the recipe change is worth nothing
         measurable, which is itself the finding. The old rows are now live=0; the citywide rows are live=1.
         ** 2013 IS AN RGB-ONLY MODEL ** (its only eval rows are channels=rgb, held-out IoU .4563, raster
         2026-07-07). It scored at an rgb threshold, which is CORRECT — the rule is that the threshold must
         match the model that produced the raster, NOT that it must always say rgb+chm. But that makes 2013 a
         THIRD axis of incomparability on top of the two reference generations: never place it in a table with
         the rgb+chm years (.6125-.7300 held-out IoU) without the RGB-ONLY label.
next:    2013 citywide re-score (its live=1 row is still the off-recipe _xsensor raster) — running local,
         no GPU. Then WORKPLAN Tier 2 item 9 is the standing task: gate step_inference locally.
files:   run_registry.csv (+4), phase4/qc/* (harvest, 21 files), WORKPLAN_2026-08-19.md (Tier 2 item 9),
         pipeline/registry_from_manifests.py, CHATLOG.md — on work/20260823-post-merge off dff4adb.

## 2026-08-22  PRE-MERGE CROSS-CHECK — both sessions verify SAFE TO MERGE; two durable hazards recorded
goal:    Kam: "I want to push everything to main, but I need ensure it won't break everything."
did:     Two independent verifications agree. MY gates on the fix/ tree: py_compile 180/180 ·
         phase4_catalog_check 18/18 · phase4seg_preflight PASSED · phase4seg_smoke PASSED end-to-end ·
         both queue YAMLs dry-run. The OTHER SESSION re-ran the same gates on the same tree and matched
         line for line, and added dry-runs of queue_2019_inference (5) and queue_2024_inference (5) plus
         harvest --dry-run clean.
         READ-ONLY `git merge-tree` of work/p11-5-autonomy x fix/20260822-inference-throughput: the
         MERGED tree contains ZERO "2022n" in live code — the relabel survives the merge rather than
         being reintroduced by work/'s older copies. Exactly 3 conflicts, all agreed by both sessions:
           CHATLOG.md            -> keep BOTH entry sets, interleave by timestamp (insertion points are
                                    ~1000 lines apart, so the risk is low)
           imagery_catalog.xlsx  -> take fix/ (209,669 B, 13 sheets; newer than work/'s 205,631 B)
           registry_from_manifests.py -> take fix/ (305 vs 285 lines). NOT merely longer: fix/ = work/
                                    PLUS honest_metrics(year, run_ts) date-filtering, the _unscored skip
                                    and the unscored counter. Taking work/ would REINTRODUCE a bug that
                                    stapled August's off-recipe 2017 number onto tonight's fresh run.
         State at cross-check: no Colab VM billing, zero RUNNING rows, no stale lock/claim files, both
         sessions' trees clean. Branches diverged at f8949f6f; main untouched at b1b8516.
rules:   ** A RUN MANIFEST IS IMMUTABLE PROVENANCE - NEVER REWRITE ONE TO MATCH A LATER RELABEL. **
         (Corrected 2026-08-22 after cross-session review; an earlier draft of this entry said "rewrite
         the manifests too" - that instruction is WRONG and would destroy the record that makes a run
         reproducible. A manifest records what actually executed: git sha, GPU, argv, seed. Rewriting one
         also puts it silently at odds with the nohup log and the status CSV, which nobody rewrites.)
         The year label is a JOIN KEY in registry_from_manifests.py (held_out_metrics, honest_metrics,
         status_for, and the sem_best_{year}.pt / edmonds_canopy_prob_{year}.tif paths), so relabelling a
         year that HAS manifests silently breaks that join: the row loses its metrics and artefact paths,
         and the unscored-inference rule then SKIPS IT PERMANENTLY. The remedy is an ALIAS, not a
         rewrite - a {old_label: new_label} map the generator consults when joining. UNTIL THAT ALIAS MAP
         EXISTS, RELABELLING A YEAR THAT HAS MANIFESTS IS A BLOCKED OPERATION, not a careful one.
         2022n->2023n was safe ONLY because that acquisition had ZERO manifests (verified 2026-08-22).
         ** THE THREADED-INFERENCE PATH IS COVERED BY NO LOCAL GATE - AND THAT IS FIXABLE. **
         phase4seg_smoke does NOT exercise step_inference; local gates passing says nothing about that
         path. What backs it today is a byte-equivalence benchmark on a live VM (max|diff| = 0 over
         41.9M px) plus four completed citywide rasters. Any edit to that loop must re-run the benchmark
         FROM THE RASTER ORIGIN - an interior-block test passes while production fails (measured
         2026-08-22: the first threaded build passed every local gate, then died on the first batch with
         "IReadBlock failed at X offset 0, Y offset 0" because the reader pool shared one GDAL handle).
         FIX THE GATE, do not just carry the warning: phase4seg_smoke should grow a step_inference case
         over a small synthetic raster on CPU - a few hundred tiles from (0,0), 8 reader threads,
         asserting output identical to EDMONDS_INFER_WORKERS=1. That gates the threading, the per-thread
         handles and the write ordering locally; only the CUDA-specific half (GPU sigmoid/quantise,
         cudnn.benchmark) would then still need a VM. -> WORKPLAN Tier 2 (local, no GPU); the other
         session adds it post-merge so this branch does not gain a 4th merge conflict.
watch:   Colab session tokens live OUTSIDE the repo (~/.config/colab-cli) and expire after exactly 1 h;
         the CLI prunes a session on any transient error, killing its keep-alive daemon and letting Colab
         reclaim the VM mid-run (cost three A100s on 2026-08-22). The mitigation, qc/colab_readopt.py
         --heal, exists ONLY on fix/ — so a session standing on work/ has no self-healing. One more
         reason the merge matters.
         Phases 1-3 scripts now point at the deleted upsample/ (phase1_preprocess 85 refs,
         phase2_data_prep 16, phase3_semantic_dev 2, phase1c_review 1). Not on the Phase 4 path, which is
         why every gate still passes. Kam has accepted this: Phase 1 gets rewritten later, not today.
next:    Kam runs the merge (git merge and git tag are denied in this session). Recommended order: tag
         main first, then merge fix/ (carries the newer copy of all three conflicted files), then work/.
         The other session OWNS the post-merge harvest_results + registry_from_manifests commit on a
         fresh branch off the new main; this session will not duplicate it.

## 2026-08-22  CLEANUP BEFORE MERGE — 2022n relabelled 2023n; upsample/ (1,009 GB) deleted
goal:    Kam: "Delete upsample, its not importnat anymore. rename 2022n... I need to clean up before that
         merge can happen."
did:     (1) THE 2022n MISLABEL IS FIXED. The file was byte-verified as NAIP 2023-10-07: bands 1-3
         identical to WA_NAIP/rgb_2023.tif and band 4 to ir_2023.tif on 3 independent windows, and NOT
         equal to rgb_2019; Edmonds_Optimal_Scenes.xlsx lists NO 2021/2022 NAIP over Edmonds; an archived
         cleanup script explicitly handled "misplaced 2023 files" inside WA_NAIP/2019/. Relabelled to
         2023n (follows the existing 2019n convention: NAIP alongside King's same-year ortho).
         Renamed atomically: 2022_naip_rgbi.tif -> 2023_naip_rgbi.tif on BOTH planes (501 MB each);
         20 artefacts (prob raster, sem_best/sem_latest/loss_history, ndvi_ref, latent_class,
         height_curve, design_power, ref_agreement, sample, qc_indep, leafoff); the year column in
         qc_indep_report.csv (3), semantic_eval_report.csv (2) and run_registry.csv (1); and 26 live
         code files (10 pipeline + 14 qc + 2 queue YAMLs), 32+15 refs total.
         KEPT VERBATIM ON PURPOSE: CHATLOG history, run_registry args/notes (they record what was
         actually executed as 2022n - annotated instead), and Scripts/scratch/litwatch_scratch/*
         (historical analysis records). Rewriting a log would falsify it.
         GATES: every touched file py_compiles (42/42 in qc/); phase4_catalog_check 18/18 OK.
         (2) upsample/ DELETED - 19 files, 1,009 GB, the largest object in the data lake. Its only
         consumer (phase-1 spectral extraction) is complete: edmonds_crowns_phase1.parquet (2026-05-27
         19:06) postdates every input (newest 2026-05-26 23:22). CLAUDE.md rule 7 scopes upsample to
         phase1/phase7; phase 7 was never built. Regenerable via phase1_preprocess.py --upsample-only
         (~20-25 h Colab). Frees ~1 TB of Google DRIVE CLOUD quota - the local G: mount figure did NOT
         rise because those files were cloud-resident, not locally cached (which is how 1 TB "fit" on a
         511 GB volume); local free actually fell 52.1 -> 44.3 GB as tonight's GPU output synced down.
         Google Drive Trash holds them ~30 days if this needs undoing.
decided: relabel rather than re-download - the pixels are fine, only the name was wrong. Historical
         records stay verbatim and get an explanatory annotation; current-state code and data get the
         corrected label.
watch:   phase1c_review.py:90 still hardcodes upsample/2020_coe_rgb.tif and is now BROKEN if re-run.
         Phase 1 is complete so nothing calls it, but it needs repointing or archiving.
         The "2022 CoE vs 2022n NAIP same-year natural experiment" in litwatch_robustness.md is
         CROSS-year (2022 vs 2023) and still needs correcting. Both NAIP flights over Edmonds are
         OCTOBER (2019-10-11, 2023-10-07), so "NAIP is leaf-on by specification" is weakened.
files:   26 live code files, 2 imagery files (both planes), 20 artefacts, 3 measured-text files,
         run_registry.csv annotations, CHATLOG.md
next:    the two IMAGERY_FACTS.md errors (2017_king is on BOTH planes, not D: only; its "14.93 cm" is
         the uncorrected CRS-unit figure, true GSD 10.0 cm) are still unrecorded. Then the branch merge:
         work/p11-5-autonomy and fix/20260822-inference-throughput diverged at f8949f6f.

## 2026-08-22  COUNTY IMAGERY + 2005 LIDAR FOUND — acquisition plan written; the 41.9% ceiling is self-inflicted
goal:    Kam found the county imagery portals and 2005/2016 lidar metadata; "I want to go all out" — new years,
         better versions of held years, metadata, and second acquisitions of covered years.
did:     PLAN ONLY, nothing acquired. New doc IMAGERY_ACQUISITION_PLAN_2026-08-22.md (sources, measured
         analysis, 5 phases, gates, risks); WORKPLAN Tier 2 item 7 points at it (old 7 -> 8).
         ** MEASURED, not assumed: **
         (1) THE 41.9% CEILING IS A PROPERTY OF OUR FILE, NOT THE SOURCE. Snohomish Aerial_2016 ImageServer
         extent = 45x55 km and contains ALL of Edmonds; 2016_snoh_rgbi.tif is 6.7x4.9 km, cut off 3.5 km
         short at the north. Probed the missing strip vs a control inside the file: control 100% non-black
         (85.3% in-city), missing north-east 100% non-black (87.3% in-city), and black fraction tracks being
         OUTSIDE the city polygon (water), not missing data. So full-extent 2016 is available -> removes the
         caveat riding on the project's most-cited year. Same expected for 2021s (verify first).
         (2) SNOHOMISH PUBLISHES 23 ANNUAL SERVICES 1990-2024, surveyed via REST: 1990 3.05m 1-band; 1996 1m;
         2003/2007/2009/2011 30.5cm 3-band; 2013 1m; 2015 30.5cm 4-BAND; 2016 15.2cm 4-BAND; 2017 30.5cm
         4-BAND; 2019 30.5cm 4-BAND; 2020 7.6cm 3-band; 2021 15.2cm 4-BAND. All contain Edmonds. Pixel sizes
         are FEET (EPSG:2285) — the same units trap that caused the gsd_cm defect.
         (3) NIR YEARS COULD GO 4 -> ~11 (King CIR 2000/2009/2010/2015/2023/2025 + Snohomish 4-band
         2015-2021 + NAIP 2015/2017/2021). Only NIR years can carry an independent NDVI reference; it
         currently exists at 4 points in an 18-acquisition series.
         (4) KING METADATA RESOLVES TWO ORPHANS. KingCo_Aerial_2017 description gives vendor (Pictometry),
         window (Feb-Oct 2017) and 3in/px over "King County AND southwestern Snohomish County" — i.e. King
         flights do cover Edmonds. Closes 2012_king_rgb.tif and the second 2017_king_rgb.tif.
         (5) ACCESS: Snohomish ImageServer exportImage, native, max 15000x4100/request. King BaseMaps
         /export DOES work (capabilities omits it) but is a cached MIXED=lossy-JPEG service, max
         4096x4096/request; King ORIGINALS come from the data catalog (www5.kingcounty.gov/sdc/?Layer=NAME)
         + Open Data/FTP portal. NAIP via NOAA Digital Coast with tileindex+urllist+VRT+STAC = cleanest.
         (6) 2005 PSLC lidar (dataset 2579, COPC, 0.25 pts/m2 vs 2016's ~4-5) — stand-scale only; overturns
         "a lidar-dependent definition CANNOT be applied pre-2016". Change-detection use needs a DECIMATION
         protocol or it manufactures growth. Details in the plan + the 2005/2016 InPort records.
decided: order by CONSTRAINT REMOVED, not pixels acquired — full-extent 2016 first (removes an existing
         caveat, adds nothing to reconcile). Prefer original downloads over REST export (double-JPEG).
         Never overwrite a held file; new name + catalog entry. Re-MEASURE every GSD from the delivered
         file — never copy a service's advertised resolution.
killed:  my own claim that King's export "plateaus at ~20cm" — RETRACTED. Controlled test (312m box, 4096px
         request vs 1024px upsampled to the same grid) gives 2.16x the HF energy for the native request, and
         the cache carries LODs to level 21 ~ 5.0 cm ground. The laplacian-falloff proxy was measuring JPEG
         smoothing, not a resolution ceiling.
         ALSO NOT REVIVED: WORKPLAN 2's withdrawal of "the 2021 pair isolates the sensor effect" STANDS —
         after true-GSD correction no same-tier same-year pair exists (Snohomish 30.5cm sits just above the
         29.9cm medium boundary; 2021 pairs 10cm fine vs 15.2cm; 2021s is pinned coarse). The better prize
         is that Snohomish 2015-2021 is one contractor lineage = a self-consistent multi-year 4-band series.
files:   IMAGERY_ACQUISITION_PLAN_2026-08-22.md (new), WORKPLAN_2026-08-19.md (Tier 2 item 7), CHATLOG.md
next:    UNTESTED GATE that decides half the King catalog: do King DERIVED products (TreeCanopy2016/2017/2021,
         TreeCanopy2021Height, TreeCanopy2021 TreePoints, ForestCover2019Ecopia, VegetationFeatureHeights*,
         the annual LiDAR DGM/DSM series) extend into Edmonds, or stop at the county line ~0.1 km south?
         TreeCanopy2021Height + TreePoints would be a THIRD independent canopy reference with heights and
         individual tree locations. Phase 2 of the plan settles it. Then Phase 0 cross-ref -> Phase 1
         metadata -> Phase 3 Tier A (full-extent 2016). None of this is on the critical path to U1.

## 2026-08-22  P11.6 — headless Colab CLI probed + adopted; MCP tabs demoted to fallback
goal:    make the NEXT session agentic for GPU runs. MCP-tab path hit its wall: both server instances open the
         same scratch notebook (SCRATCH_PATH hard-coded) -> ONE shared runtime; moving a tab = manual fragment
         surgery in the browser.
did:     found Google's official google-colab-cli (PyPI 0.6.0). PROBED on CPU sessions (no compute units):
         one-time OAuth via a two-phase helper (D:\tools\colab-cli\auth_twophase.py — the CLI's own flow blocks
         on input(); split URL-print / code-exchange so an agent can drive it; token + refresh cached at
         ~/.config/colab-cli/token.json). colab new -s A --gpu A100 -> READY in ~1 min (proved, then stopped when
         scope drifted; cost = minutes of idle A100). exec runs on the VM with persistent kernel state; detached
         nohup survives; sessions/status/log/stop all work from the agent shell. WINDOWS is unsupported upstream;
         two machine-local fixes make every non-interactive command work: termios stub in the tool venv
         (console.py imports it unconditionally; only console/repl need it) + jupyter-kernel-client<1.0 pin
         (unpinned dep; 1.0 renamed KernelClient -> JupyterKernelClient, breaking exec/drivemount).
         DRIVEMOUNT is NOT agent-runnable: per-VM Google consent, URL -> approve -> Enter on a real TTY
         (/dev/tty) -> Kam's terminal, ~1 min per VM; grant verified NOT to carry to a new VM. So crash recovery
         = push the fix branch + re-exec vm_bootstrap on the LIVE VM (mount intact); only a dead VM costs a mount.
         BUILT pipeline/colab_cli_vmgen.py: generates vm_bootstrap.py (clone at BRANCH with the gh token
         templated at send time and scrubbed from .git/config; Drive assert; logs+locks mkdir; pip install; GPU
         print; queue dry-run) + vm_launch.py (nohup the queue, per-queue log) into LOCAL scratch only (refuses
         repo/Drive outdirs).
         PERMISSIONS (user scope, Kam): colab.exe * + tool-venv python * allow rules. LESSON: a command must
         START with the literal allowed prefix — a leading VAR=... assignment falls back to the auto-mode
         classifier (hit repeatedly tonight). Probes cleaned: probe/probe2/A stopped; one browser-era [?] CPU
         orphan has no local record and expires at the 24 h cap.
decided: CLI path adopted (Kam: "Lets do 1"); MCP entries kept as fallback only. Scope discipline restated by
         Kam mid-session: THIS session DESIGNS the agentic path; the D: session RUNS it.
killed:  reverse-engineering the CLI's Drive credential-propagation to force drivemount headless — that is a fork
         of a tool unsupported on Windows, and it would break silently later.
files:   pipeline/colab_cli_vmgen.py (new), OVERHAUL_PLAN_2026-08-20.md (P11.6), CHATLOG.md; machine-local (not
         in the repo, documented in P11.6): D:\tools\colab-cli\auth_twophase.py, termios stub + jkc pin in the
         uv tool venv, colab CLI OAuth token.
addendum (D: session, 15:20-15:30Z): prompt B CLI edition started. vmgen for queue A -> scratch OK (token local);
         colab sessions authed; colab new -s mounttest READY; agent exec works (host fb2becee74e3). Kam's
         `colab drivemount -s mounttest` (PowerShell): consent OK, then ValueError mount failed (drive-timeout)
         with no 'Authorizing VM' line. ROOT CAUSE: automation.py drivefs_hook opens /dev/tty for the Enter ->
         FileNotFoundError on Windows, swallowed at runtime.py:81 (colab.log 08:22:48) -> propagation POST +
         input_reply never sent -> DriveFS times out. Kam: "patch" -> fix #4 (try/except OSError ->
         sys.stdin.readline(), backup .orig) -> retry: Mounted; agent exec lists treedata on the same VM ->
         MOUNT TEST PASSED, mounttest stopped, gate OPEN. Details: STATE + OVERHAUL_PLAN P11.6 fix 4.
next:    OTHER SESSION (D:): prompt B, CLI edition (plan file). vmgen -> ask Kam -> colab new -s A --gpu A100 ->
         KAM drivemount -s A -> exec bootstrap (expect BOOTSTRAP_DONE on work/p11-5-autonomy) -> exec launch ->
         same for B (>= 2 min later) -> monitor artifacts + colab status/log -> score (channels=rgb+chm gate) ->
         harvest on the branch -> colab stop when the job-end VERIFY rows land. Kam: merge work/p11-5-autonomy
         when the diff is approved, or keep launching from the branch.

## 2026-08-22  P11.5 ALLOWLIST INSTALLED — user settings gained permissions; main-push deny PROVEN in-session
goal:    Kam: install the P11.5 permissions block (OVERHAUL_PLAN P11.5 == plan file, diff-identical) into
         D:\tools\claude-config\settings.json, strip the stray allows from C:\Users\Kameron\.claude\settings.json,
         prove the guard, confirm both Colab MCP servers.
did:     Block merged by script (no retyping): 20 allow / 28 deny; all 8 prior keys kept, permissions byte-equal
         to the doc block. Home file -> {"permissions":{"allow":[]}} (Bash(git push:*) + Bash(rm:*) gone).
         Guard: one standalone `git push github main` (main == github/main at b1b8516, so a leak would have been
         a no-op) -> "Permission to use Bash with command git push github main has been denied" — the edit
         hot-reloaded into the running session (docs: settings are watched; permissions/hooks reload live).
         `claude mcp list`: colab-mcp + colab-mcp-b Connected (Drive/Gmail/Calendar connected, HF needs auth).
decided: nothing new. FACT (docs, code.claude.com/docs/en/permissions): Bash(...) and PowerShell(...) rules are
         evaluated separately -> the deny list protects main only for the Bash tool. Not widened (Kam's call).
files:   CHATLOG.md, OVERHAUL_PLAN_2026-08-20.md (one-time item ticked) on work/p11-5-autonomy. Settings files
         are outside the repo.
addendum: Kam: "widen the block for this session" -> 28 PowerShell(...) DENY twins appended to the live user
         settings (no allow twins; loop stays on the Bash tool). Proven: `git push github main` via the
         PowerShell tool -> "Permission to use PowerShell with command git push github main has been denied".
         Kam then ruled the twins permanent (a blanket PowerShell ban at user scope would break the
         PowerShell-heavy contractor-docs sessions) -> P11.5 JSON block in OVERHAUL_PLAN + plan file
         regenerated FROM the live settings file (20 allow / 56 deny) + one-sentence rationale.
         PROMPT B STEP 1-2 (Kam "yes both"): ToolSearch cold = 1 gate tool per server; both connects -> true; 7
         notebook tools unlocked per server (get_cells, add_code_cell, add_text_cell, update_cell, move_cell,
         delete_cell, run_code_cell). run_code_cell returns the output -> Claude can execute; no runtime-type /
         GPU / notebook-open / runtime-list tool. Both tabs = empty.ipynb, one empty code cell. Details: STATE.
         STEP 3 done on both tabs (CPU): clone 2bf0835 on the branch, catalog 18/18, dry-run A = 10 cmds,
         dry-run B = 10 cmds. FINDING: both tabs are on ONE runtime (tab B: "already mounted / already
         cloned") -> tab B needs its own notebook before launch B; MCP binding is per page (token fragment).
next:    Kam: set tab A to A100 (UI) -> Claude re-runs cells 1-2 on the GPU VM -> STEP 4 launch-A proposal;
         decide tab B (re-point to another notebook keeping the token fragment, Chrome-MCP assist, or
         human-paste B). Nit for later: phase4_train_queue.py:603 display backslash.

## 2026-08-22  LIDAR ACQUIRED — era-matched 2005 + full-density 2016; the CHM in use is a degraded product
goal:    Kam: get the Edmonds-area lidar for BOTH vintages into the data lake and record the find. Local only,
         no GPU, between queue steps. 2005 is the FIRST pre-2016 height data this project has ever had.
did:     Both datasets are public NOAA COPC, same bucket, same CRS (NAD83(HARN) UTM 10N / NAVD88 GEOID18), same
         q47122#### quad grid -> tiles ALIGN between eras and one selection routine served both. Helper set
         (tileindex gpkg/zip, urllist, minmax, ISO xml + forHumans html, and the 67.5 MB west_wash_breaklines.zip)
         downloaded for both. SELECTION: Edmonds Boundry.shp reprojected per tileindex CRS, buffered 600 m (Kam
         raised it from the briefed 200 m), intersecting tiles -> 2005: 47 tiles / 407.5 MB; 2016: 41 tiles /
         5,907.2 MB. At 200 m it was 41 + 35 tiles, so the wider margin cost 12 tiles; buffer exists so
         boundary-straddling crowns keep their points and derived rasters do not degrade at the edge.
         SIZE GATE tripped as briefed (2016 alone 4.68 GiB at 200 m, over the 4 GiB per-set limit) -> STOPPED and
         asked; Kam: "hard drive space is not an issue" -> proceeded, then raised the buffer to 600 m (5.88 GiB
         combined). Downloaded to D: first (rule 3), each file verified against its S3 Content-Length, then
         MANIFEST.sha256 per directory (54 / 48 entries), then copied to the data lake and size-verified
         there: PSLC_2005 55 files / 408.9 MB, USGS_2016 50 files / 5,986.3 MB, both == local. Drive still has
         45.8 GiB free. Nothing processed: no CHM built, no points read, phase4seg untouched.
decided: IMAGERY_FACTS is the right home for the specs (it is the measured-facts doc for source data); the CHM
         provenance detail expands the one-line CLAUDE.md row rather than duplicating it.
found:   ** THE CHM IN USE IS DEGRADED. ** lidar_snoh_chm.tif is NOT county data (the county files are the
         hillshades lidar_snoh_hillshade_fr/be.tif and the retired lidar_snoh_structure.tif). It is USGS 3DEP HAG
         from Planetary Computer: a ~2 m raster BILINEAR-UPSAMPLED to 1 m EPSG:3857, quantised uint8 at 0.2 m/DN,
         CAPPED at 50.6 m (p99 44.6 m; western WA Douglas-fir exceeds 50 m). Bilinear upsampling SMOOTHS local
         maxima and a canopy apex IS a local maximum -> it reads systematically LOW, worst on narrow conical
         crowns = the conifer training sites. CAVEAT ON THE CAVEAT: U6 ("CHM error cannot have made the
         staircase") injected RANDOM Gaussian error; smoothing bias is SYSTEMATIC and one-directional, so U6 does
         NOT cover this case - do not cite it as clearing this.
         ** THE DENSITY GAP IS THE GOVERNING FACT: ~16-29x. ** 2005 is 0.25 pts/m² stated / ~0.17 cross-checked
         from class counts; 2016 is 4 stated / ~5 cross-checked. 2005 also has only 3 classes (Unclassified /
         Ground / Low Point - VEGETATION IS UNCLASSIFIED) against 2016's 6. Two accuracy metrics exist for 2005
         and are NOT the same thing: 6.3 cm fundamental vertical (95th pct, Digital Coast) vs InPort's 25 cm avg /
         15-25 cm soft-vegetated - both recorded, never averaged.
         ** OVERTURNED: ** the CHATLOG line "a lidar-dependent definition CANNOT be applied pre-2016 (no
         coverage)" is wrong. Pre-2016 height data EXISTS, at stand scale.
ranking: CORRECTED mid-assessment. Change-detection was ranked FIRST until the density figure arrived; it is not.
         (1) USABLE, best use: an independent ERA-MATCHED STAND-scale 2005 canopy mask (~5 m cells; at 0.25 pts/m²
         a 2 m cell holds ~1 point - presence does not need the apex). Value = a THIRD reference sharing no
         failure mode with C-CAP or the NDVI reference, aimed at the 15-17% reference-disagreement problem, and
         contemporaneous rather than 2016-projected. (2) CONDITIONAL: bounding real 2005->2016 change, ONLY after
         a written DECIMATION PROTOCOL (thin 2016 to ~0.25 pts/m², rebuild BOTH CHMs identically, then difference
         - sparse lidar under-samples apexes and reads low, so a naive difference MANUFACTURES growth everywhere)
         AND class harmonisation (2016's Water/Bridge Deck/Ignored Ground must be reconciled with 2005's three
         classes). Same failure class as cross-sensor GRVI and the clipped reference. (3) DROP: re-testing the
         height staircase on 2005 - a 1-2 m low bias shifts crowns down a band and the 5-15 m bands hold 53% of
         all misses. Overall 2005 is a STAND-scale instrument, not crown-scale; the hardest miss population is
         scattered suburban/ornamental crowns (8/8 inspected missed stands were suburban) which 0.25 pts/m²
         cannot resolve. A from-points 2016 CHM is worth building ONLY as part of (2), where it comes free.
         NOT reopened: coverage. qc/chm_gap_2016.txt closed that (83.5% of the analysis area has CHM, the rest is
         open water at 99.8% negative NDVI; counting every green no-CHM pixel as canopy moves it +0.02 pp).
next:    step one of ANY of this work = measure realised pts/m² on a central Edmonds tile (stated and
         cross-checked densities disagree ~30% for 2005; do not size cells off either until the local number is
         known). Nothing processed tonight: no CHM built, no points touched, phase4seg untouched.
files:   IMAGERY_FACTS.md (new section 8), WORKPLAN_2026-08-19.md (section 4 Tier 2 item 8), CHATLOG.md;
         data: D:\edmonds-pipeline\Imagery\{PSLC_2005,USGS_2016}\ and Full_Image\{PSLC_2005,USGS_2016}\.
         run_registry.csv NOT touched - it is for Colab runs.

## 2026-08-22  P11.5 RULED — crash-recovery autonomy, A100 default, branch workflow; prep landed on work/p11-5-autonomy
goal:    Kam: "we can coordinate GPUs and runtimes now" — larger GPU to dodge runtime limits; if a run crashes
         Claude may pull, fix, test on a smaller GPU and rerun on the larger GPU without asking; nothing to
         main without approval; work branches free; a permissions prompt; a mega prompt for next session.
did:     Plan + prompts -> D:\tools\claude-config\plans\because-we-are-not-parallel-codd.md (session-start
         mega prompt, /loop prompt, permission-approval prompt). Kam's answers: first launch of each queue
         ask-first; NO spend cap tonight ("we are learning") but loop intervals back off 10->60 min; A100 40 GB
         for real runs, L4/T4 for canaries. Explore agent facts: cockpit clone is --depth 1 = single-branch
         (checkout of a work branch fails on a reused runtime); manifest records no branch/GPU; the repo's
         .gitignore whitelists Scripts/ so a Scripts/.claude/settings.json would be TRACKED -> permission
         rules live in user settings only. STEP 0 (this branch): OVERHAUL_PLAN P11.5 (ruling, canary
         definition, branch rule, GPU tiers, loop pacing, allowlist JSON), rule 3 + open rulings + P11 header
         amended, runbook steps 3-5 (A100, BRANCH, no-ask relaunch); CLAUDE.md spend gate + rule 1c; cockpit
         cell 1 BRANCH (clone --branch; fetch --depth 1 + checkout -B FETCH_HEAD on re-run), cell 0/6 A100 +
         branch text, cell 2 nvidia-smi; manifest git_branch/gpu/gpu_mem_gb (torch-free nvidia-smi);
         queue header GPU line; queue YAML hours on A100.
         VERIFIED (2-lens workflow, 16 verified, 14 confirmed -> all fixed, 2nd commit): cell 5 %run reused the
         kernel's imported phase4seg (stale after a BRANCH switch while the manifest stamped the new branch) ->
         !python -u + shim purges sys.modules; canary redefined = one-job queue YAML via cell 3 (only the queue
         writes VERIFY rows); deny list gained refspec/flag-position/branch-mutation/git -C forms (fix/x:main
         slipped through); docs: Kam pushes main in his OWN shell (deny = blocked outright, not promptable);
         harvest_results.py refuses --commit on main (--on-main override); cell 1 re-points origin at the
         current token; _gpu_line checks the exit code; manifest keeps the GPU name when memory is [N/A];
         CLAUDE.md GPU rows -> A100; stale UNPUSHED/ask-first lines corrected.
decided: permissions = user settings only (repo would track them); deny rules protect main regardless of
         prompt wording; canary = smallest job exercising the fix (<= ~1.5 h) on L4/T4.
files:   OVERHAUL_PLAN_2026-08-20.md, CLAUDE.md, pipeline/colab_launch.ipynb, pipeline/phase4seg/cli.py,
         pipeline/phase4_train_queue.py, pipeline/queue_A_2024_2017.yaml, pipeline/queue_B_2019_2022.yaml,
         CHATLOG.md — all on work/p11-5-autonomy (NOT main).
next:    Kam: paste the permission prompt (plan file, prompt A) -> user settings; merge/push
         work/p11-5-autonomy to main when the diff is approved (or run next session from the branch:
         cockpit BRANCH = 'work/p11-5-autonomy'). Next session = the mega prompt, Step 1 onward.

## 2026-08-22  P11.4 PREREQS LANDED — staging lock, ceilings, resume fix, per-queue logs, balanced queues; MCP inventory done
goal:    Kam: no hand launches; get everything in place so the next session runs the agentic two-runtime workflow.
did:     MCP INVENTORY (read-only stdio probe; server tools load only at session start): ColabMCP (colab_mcp 1.0.1,
         FastMCP 2.14.5) exposes ONE tool cold — open_colab_browser_connection. It opens the browser at
         colab.research.google.com/notebooks/empty.ipynb#mcpProxyToken=..&mcpProxyPort=..; the Colab page connects
         back over a localhost websocket and the server PROXIES the Colab frontend's notebook tools (listChanged).
         One tab = one session = one runtime per connection; tools not enumerable until attached; no Google auth in
         the package — the browser tab is the credential. Nothing called.
         CODE (gates green: py_compile; preflight 2024/inference + 2019/tile; CPU smoke PASSED; --dry-run both
         queues; 6-case local unit test of the lock):
         (1) phase4seg/common.py _StagingLock — per-claimant files in phase4/locks/ (NO O_EXCL: Drive is not
             POSIX), oldest live claim holds, 60 s heartbeat, 15 min stale-break, dead-pid check, 60 min max-wait
             then proceed unlocked + warn, >= 1 GiB copies only; core.py tile staging same lock, stat pass outside
             it; guard tests the real mount (config.BASE is the Colab path everywhere). REWRITTEN after review
             (first version used O_EXCL + 240 min max-wait + unbounded continue paths + raised out of __enter__);
             v3 after REVIEW-2: confirm-after-60 s second listing, in-place re-stamp (no rename-over), one-poll
             hysteresis on a vanished claim, reader-clock liveness (skew-immune), fail-closed stat, claim kept on
             max-wait fallthrough, queue sweeps a killed engine's claim, labels ceiling 45->120, malformed-JSON
             guard, .tmp sweep. Residual (documented): propagation lag > 60 s or a wedged mount; lost races are
             logged by the holder's heartbeat.
         (2) phase4_train_queue.py STEP_TIMEOUT_MIN inference 240->480, tile 90->180, train 240->300: 2017's
             CoE-grid inference took 254.9 min, so the old ceiling would have killed every 2024/2017/2022
             inference 15 min short (audit finding; ~4 h GPU would have burned tonight had staging completed).
         (3) resume (_completed_steps) drops (job,step) whose latest VERIFY:{step} hard-failed — a step that exits
             0 without its artifact is no longer skipped on relaunch (audit finding).
         (4) per-queue nohup logs train_queue_nohup_{queue}_{ts}.log (cockpit cell 3; cell 4 merges all status
             files; cell 6 updated) — the shared path lost queue3's stdout tonight.
         (5) queue_A_2024_2017.yaml (~10 h L4) + queue_B_2019_2022.yaml (~8 h L4): balanced two-runtime split;
             merged-reader resume skips 2024 labels/tile/train/evaluate + 2019 labels (verified locally).
         (6) OVERHAUL_PLAN P11 runbook: mechanism, prereqs, 7-step next-session sequence (every launch its own ask).
         AUDIT (4-agent workflow, refuted where wrong): pre-P11.1 clobber semantics confirmed (last writer wins;
         both tonight's runtimes ran 57bc07b). SCORING PRE-STAGED: --prob is MANDATORY (resolve_prob is
         suffix-blind); deployed_threshold takes the rgb+chm OVERALL row of semantic_eval_report.csv, which for
         2019/2017/2022 does NOT exist until the queue's evaluate step lands — today it would silently use the
         stale July rgb rows .5003/.4997/.4822, so the scorer console MUST say channels=rgb+chm; 2024's row exists
         (.5043). Refs: 2024/2019/2022 vs D:\edmonds-pipeline\Imagery\ccap_2021_hires_lc.tif (T3 clipped);
         2017 vs ccap_2016_hires_lc_snohfull.tif (full; demotes the xsensor .7986 row — intended). Each score =
         two full passes over a Drive raster: ~20 min (2019), ~50-60 min (CoE years); run sequentially.
         CORRECTION (Kam 02:50Z, "not proven"): every "stalled under the throttle" statement reworded to "went
         silent; cause not established" — CHATLOG, plan, queues, notebook, code comments, status rows, memory.
decided: lock = precaution against ONE candidate cause, not the fix; ceilings sized for a foreign staging wait;
         A/B balance 2024+2017 / 2019+2022 (10 h / 8 h) over 2024+2019 / 2017+2022 (7 h / 11 h).
killed:  editing files through bash heredoc python with double backslashes (the tool transport collapses them) and
         without CRLF handling (common.py, train_queue.py, CHATLOG are CRLF) — write the script to a file instead.
files:   pipeline/phase4seg/common.py, pipeline/phase4seg/core.py, pipeline/phase4_train_queue.py,
         pipeline/colab_launch.ipynb, pipeline/queue_A_2024_2017.yaml, pipeline/queue_B_2019_2022.yaml,
         OVERHAUL_PLAN_2026-08-20.md, CHATLOG.md; scratch unit test test_staging_lock.py (session scratchpad only).
         REVIEW (3-lens adversarial workflow, 33 verified): 29 confirmed / 4 refuted -> all 29 addressed:
         lock rewritten (above); lock dir pre-created on Drive + at queue launch + cockpit cell 1 (two VMs racing
         mkdir = two same-named folders); resume also revokes on later FAIL/TIMEOUT/INTERRUPTED/RUNNING and job-end
         VERIFY; footer/utcnow nits; cockpit cell 2 dry-runs the launch YAML; cell 4 guards empty; docs: 214 s ->
         12-26 min, 7.5 cm -> 5 cm true GSD (IMAGERY_FACTS), "~10 min into" -> "~10 min apart", ONE SERVER
         INSTANCE = ONE COLAB TAB (websocket_server.py:113-118 rejects a 2nd socket) -> 2nd runtime needs a 2nd
         mcp entry colab-mcp-b (command in the runbook), P11.1/2/3/4 text reconciled, CLAUDE.md spend-gate wording.
         REVIEW-2 (lock only, 2 lenses, 22 verified): 19 confirmed / 3 refuted -> lock v3 above; the unit test grew
         a two-view lagged-propagation simulation (exclusion must hold for lag < confirm; FIFO after release) —
         the harness that proved v2 lost exclusion whenever drivefs lag exceeded the 10 s settle. A Drive-file
         lock is best-effort by nature; v3 bounds the exposure and LOGS every lost race. No third round.
next:    NEXT SESSION = OVERHAUL_PLAN P11 runbook: claude mcp list -> open_colab_browser_connection (Kam's yes) ->
         tool inventory -> cells 1-2 on a CPU runtime -> propose launch A (queue_A, L4, 1 runtime, ~10 h) ->
         launch B via colab-mcp-b (registered + connected 03:40Z; >= 2 min after A) -> monitor ARTIFACTS -> score (threshold gate) ->
         harvest -> registry rows. Kam: git push github main --tags after this session's commits.

## 2026-08-21  RESUME on D: — colab-mcp NOT registered; 2024-finish + queue3 SILENT since 01:12Z; nothing new to score
goal:    resume after P11: verify colab-mcp read-only; locate GPU work from ARTIFACTS; score newly-VERIFIED years;
         harvest; re-arm watch.
did:     colab-mcp: first read "not registered" was WRONG IN DETAIL — I scanned ~/.claude.json but this install's
         config is D:\tools\claude-config\.claude.json. Truth: last session registered it at LOCAL scope
         (project G:\My Drive\treedata\Scripts, command `uvx` by name); it never connected because
         Python312\Scripts is on neither user nor machine PATH (uv 0.12.5 installed 18:33 local). Tonight
         (Kam's commands, 02:00-02:12Z): user-scope entry with absolute uvx.exe path; local duplicate removed;
         first health check timed out at 30 s (uvx building from git); MCP_TIMEOUT=240000 claude mcp list ->
         ✔ Connected 02:20Z (11 s, cache warm). Read-only tool inventory owed — server tools load at session
         start. Nothing launched.
         GPU state from artifacts (Drive API, server-side mtimes — not local sync): train_queue_status.csv
         01:12:36Z, train_queue_nohup.log 01:12:52Z, 2000-canary manifest 01:29:11Z (cell-5 re-run, no status
         row). queue3 runtime: NOTHING after its 2019 tile manifest 01:03:07Z — tiles write straight to Drive
         (tiling.py rasterio.open(img_out,"w")), so a live tile step leaves files; tiles/2019 = 668 July files,
         unchanged 47 min. 2024 runtime: nohup ends at the "Step 5" header; next print is the staging ⏱ tock
         (core.py step_inference → _stage_imagery_local); none after 36 min. CORRECTED 03:10Z: I wrote "214 s"
         for 2017's staging — the logs show 12-26 min (six stagings) and 19.1 min for 2024, so A's silence was
         only MILDLY anomalous; B's 55 min (King orthos stage in <= 2.5 min) clearly was. The stagings began ~10 min apart (11.7 GB 2019 @01:03Z, 26.9 GB 2024 @01:12Z) and each runtime
         went silent seconds after its own began; a cell-5 canary started 01:29:11Z on one of them wrote its manifest but never its
         step log (a 0-s step) — that VM's Drive writes stopped too. CAUSE NOT ESTABLISHED (Kam, 02:50Z:
         'not proven'): download throttle during parallel staging (measured 08-21) is one candidate;
         a wedged Drive mount or VM death fit the evidence equally. Staging lock = precaution against
         the first only.
         No new VERIFY row, no new prob raster → nothing scorable tonight. Sizes: 2024 ortho = same 31.53 Gpx
         grid as 2017 → inference ≈ 4h15m L4 AFTER staging; queue3 ≈ 13.5 h L4 (2019 ~2.5 h, 2017/2022 ~5.5 h
         each) → two windows.
         Harvest: train_queue_status.csv (01:00–01:12Z rows) → f4601c4. Monitor armed: new status rows / run
         dirs / 2024-2019-2017-2022 prob+mask rasters / tile counts / STALE alerts at 120-600 min.
         FOUND: 2013 citywide_rgb .7422/.8672 (quoted in CHATLOG recipe-matched table AND WORKPLAN §1.3) is
         live=0 in qc_indep_report.csv line 40 — superseded by the 2013 xsensor re-score 19:57Z same ref (live
         flag keyed (year, ref) cannot hold two series), and scored at fallback thresh 0.5, not tool-chosen.
         Quote .7422 with footnote until re-scored (WORKPLAN wins). Scoring 2017 citywide will likewise demote
         the xsensor .7986 row — INTENDED (queue3 exists to replace it), not data loss.
decided: report "both silent, cause unknown" — A's missing stage tock is evidence of silence, not of a throttle.
         Fix 2013 by re-score (newest → live=1), no scorer change tonight.
files:   phase4/qc/train_queue_status.csv (f4601c4), CHATLOG.md (STATE + this entry)
next:    KAM (in order): (1) `git push github main --tags` — d038f34 (P11.1) + f4601c4 + this commit are
         UNPUSHED; every runtime tonight cloned 57bc07b; any relaunch must clone HEAD. (2) DONE: Kam
         stopped both runtimes ~02:05Z (silent 55+ min; cause unproven). Rows closed INTERRUPTED + harvested.
         Relaunch = NEW ask, proposed: queue_2024_finish.yaml, 1 runtime, L4, ~4.5 h (stage ~4 min healthy +
         ~255 min inference per the 2017 precedent); then queue3.yaml in its own window (~13.5 h: 2019 2.5 h,
         2017/2022 5.5 h each). Never stage two orthos at once. A new VM clones HEAD -> per-queue status files.
         KAM 02:15Z: NOT relaunching by hand — waiting for the agentic MCP path to launch queues in PARALLEL.
         Prereqs before that trial: (a) fresh session, colab-mcp read-only inventory (auth step expected);
         (b) engine staging LOCK (Drive lock file + stale timeout) so concurrent runtimes serialize ortho
         staging — removes the throttle candidate (account-wide quota; two stagings overlapped tonight); (c) per-
         runtime nohup log (cell 3 path is shared; queue3's stdout was lost when 2024 relaunched with >);
         (d) split queue3+2024 into two balanced queue files (~9 h each: 2024+2019 / 2017+2022).
         (3) DONE 02:20Z: colab-mcp registered USER scope, absolute uvx.exe path, ✔ Connected. Owed: read-only
         tool inventory in a fresh session (README documents no auth flow — expect a browser step).
         CLAUDE when rasters land: qc_indep 2024 + 2019 vs clipped ccap_2021_hires_lc.tif (T3 footing), 2017
         vs ccap_2016_hires_lc_snohfull.tif, 2022 vs clipped ccap_2021 (2021-epoch); re-score 2013 citywide;
         harvest --commit; registry rows from manifests (generator still deferred).

## 2026-08-21  P11 ADOPTED — Kam hands Claude the GPU keys, ask-first ALWAYS; status clobber fixed
goal:    Kam ruling: Claude may drive Colab via MCP server; MUST ask permission before EVERY
         launch (queue, tier, runtime count, cost); cap 2 concurrent runtimes.
did:     P11.1 landed: per-launch status files train_queue_status_{queue}_{ts}.csv (concurrent
         queues clobbered the single CSV — observed 2026-08-22 01:00-01:03Z when 2024-finish +
         queue3 ran together); readers merge all train_queue_status*.csv (resume, pipeline_status,
         watch_queue). CLAUDE.md spend-gate rewritten; OVERHAUL_PLAN updated w/ P11 + status.
         Windows: canary DONE (manifest 20260822T005611Z, git 57bc07b — provenance LIVE);
         2024 inference relaunched cleanly after 2nd runtime death (verified writes = NO stub
         this time); queue3 to follow. P1 backup COMPLETE earlier today.
decided: keys-with-permission > human-paste (Kam). One queue per runtime. 2-runtime cap until
         Drive-throttle interplay measured (account throttle hit 2x on 2026-08-21).
next:    Kam connects Colab MCP server → Claude verifies read-only → two-runtime trial on next
         real workload (per-launch yes). Deferred still: registry generator, QC provenance,
         P9 sync, P10 cleanups.

## 2026-08-20  OVERHAUL P1–P7 EXECUTED — code moved home, engine hardened, Colab cutover staged
goal:    execute OVERHAUL_PLAN_2026-08-20.md same session as adoption.
did:     P1: robocopy Drive→D:\edmonds-pipeline\backup launched (prob_2020 102GiB solo /Z first,
         then models[sem_best]/masks/gpkg/parquet/phase3/CoE-orthos legs; ~310GB after trims:
         skip sem_latest twins, crops [3.6GB, regenerable], phase5, KingCo 75GB raw [flagged],
         upsample [skip, regenerable]; dedupe vs D:\Imagery). P2: git clone --no-hardlinks →
         D:\edmonds-pipeline\treedata, remotes github+drive-mirror, 48 tags, identity set.
         P3: reorg pipeline(20)/qc(38+html)/scratch/_archive, 299 renames, zero untracked
         (gitignore whitelist admits Scripts subtree — no edit needed); path fixes: LOGS_DIR→
         phase4/logs (35 files), SCRIPTS→__file__ (train_queue/p1 — clone runs CLONED code),
         sentinel probe→Full_Image, pipeline_log provenance re-anchored __file__ (was hashing
         Drive copy), viz/smoke/catalog_check/latent_adversarial path fixes, queue false-MISSING
         fix, docstrings→clone paths; requirements-colab/local.txt (phase0 pins frozen-legacy);
         CLAUDE.md REWRITTEN (two-planes), README git section, doc path refs. VERIFIED: 66
         py_compile, catalog 18/18, preflight, smoke CPU end-to-end, dry-run, data_inventory.
         P4: (1) _copy_to_drive resurrected w/ size+sha256+retry; prob/mask/gpkg full-sha,
         ckpt size-verify — 2022-0-byte/2017-nodata/2024-stub class dies loudly; (2)
         _stage_tiles_local — epochs read NVMe not FUSE (tile_index abs paths rewritten);
         (3) per-step VERIFY:{step} rows, hard-fail aborts job before next GPU dollar.
         P5: colab_launch.ipynb cockpit (clone via GH_TOKEN secret, check cells, nohup launch,
         monitor). P6: run manifests phase4/runs/{run_id}/manifest.json (git sha+dirty, pip
         freeze, seed, argv, resolved imagery), run_id in log fields; training seeded (cudnn/
         AMP nondeterminism accepted); --queue YAML (queue3.yaml, queue_2024_finish.yaml);
         loss-history tagged; area CSV keyed (year,run_tag); tile signature + ortho name+size
         (mtime excluded — phantom-M lesson; legacy caches grandfathered). P7: harvest_results.py
         (first harvest: 3 files) + untagged-overwrite gate (--allow-overwrite).
decided: gates green per commit (preflight+smoke each engine change). mtime NEVER in signatures.
         Ckpt verify = size-only (per-epoch cost); rasters = full sha.
killed:  running engine cli locally for manifest test — would recreate stray C:\content dir.
files:   commits af28526..505b9ab on main (D: repo). Key: 2b622f2 reorg, a052f52 verified
         writes, 5acf16d tile staging, 3e615c9 per-step VERIFY, abf6d96 manifests+seeds,
         04f535a queue-as-data, 2b2edb0 harvest, 505b9ab overwrite gate.
next:    Kam: .git pointer delete, push, PAT, D2, canary → queue_2024_finish → queue3 windows.
         Claude next session: P1 sha manifests+verify (if not done), registry generator,
         QC provenance, pipeline_status.py, watch_queue.py, dag.yaml, mirror_sync.py.

## 2026-08-20  OPTION A OVERHAUL adopted — master plan landed; P0 bookkeeping done
goal:    Kam adopted Option A (re-plumb planes) after 4-env audit. Make plan + decisions durable.
did:     OVERHAUL_PLAN_2026-08-20.md written (phases P0-P10 + verified ground truth from 3-agent
         familiarization sweep: docs, engine, data/infra). 2024 inference found DEAD not RUNNING:
         prob raster = 2.5MB truncated stub (3rd unverified-write failure after 2022 0-byte, 2017
         96.5%-nodata). Stub set aside .stub-20260819; status CSV row closed FAIL; registry
         backfilled 6 rows for the 08-19 QUEUE2 runs (2005/2007/2009/2021k/2023 + 2024 partial).
         STATE active-plan pointers fixed (still named honest-measurement-overhaul.md, demoted 08-19).
decided: Option A adopted (Kam). B declined — no scheduler reaches a human-launched Colab. C later.
         No forwarding shims. Backup trims: skip sem_latest twins/crops/phase5, dedupe vs D:\Imagery.
         D2 polarity NOT recorded — awaits Kam confirmation (adopted ruling reverses draft rec).
files:   Scripts/OVERHAUL_PLAN_2026-08-20.md (new), run_registry.csv, WORKPLAN_2026-08-19.md,
         phase4/qc/train_queue_status.csv, phase4/masks/*2024*.stub-20260819, CHATLOG.md
next:    P1 backup robocopy (measure-first) → P2 clone to D: + detach Drive → P3 reorg.

## 2026-08-20  phase2 gpkg copy DELETED after measured review — cleanup's last pending row closed
goal:    the 1.5 GB phase2/"Copy of edmonds_crowns_phase1.gpkg" was the last
         disposition-pending item; "duplicate" was a guess (sizes differed).
did:     MEASURED, not assumed: same layer, same 222,435 features as the phase1
         original; copy had 148 cols vs original 191, but 7 copy-only cols
         (auto_label, auto_confidence, auto_fp_rule, impervious_frac,
         median_vs_roof, n_high_alpha, n_veg_years) — ALL present in
         phase1a/edmonds_crowns_phase1a.gpkg (198 cols, the superset). Copy was
         an intermediate state fully contained in the phase1a deliverable ->
         deleted. Also this session: BOTH mirror pushes ran (Kam added
         Bash(git push:*) + Bash(rm:*) allow rules via /permissions) — full
         history now on drive-mirror AND github, first offsite copies ever.
decided: verify containment before deleting a "duplicate" — the size mismatch
         would have made a checksum comparison lie; column-set containment was
         the right test.
files:   README.md (phase2 row) · CHATLOG.md (this entry)
next:    cleanup COMPLETE except: _backup_accept_all (held until U1 + 2016c
         close) and the owed CHATLOG STATE compaction (fresh session).

## 2026-08-19  verify-tier dispositions DECIDED by Kam — 3 more deletes, 3 keeps, README updated
goal:    close the "disposition pending" rows the cleanup left open.
did:     DELETED (Kam approved): tiles/ (phase-0/3 tile cache), impervious/impervious.tif
         (1.48 GB statewide source, re-downloadable; the edmonds clip stays and is the
         only file scripts read), Full_Image/temp/ (empty), stale empty bare mirror
         G:\My Drive\_treedata_git_mirror.git (0 refs, never armed). MOVED:
         Full_Image/Image_Scripts/ (4 March-era acquisition notebooks + arcgis_agent.py)
         -> Scripts/_archive/Image_Scripts/, now git-tracked (commit 1dcdecb).
         KEPT (Kam decided): inference/ DTM tifs (112 GB) — "readily access those for
         analysis"; labels/ (346 MB) — per-site distance-transform GeoTIFFs, phase-0
         training targets derived from polygons/, regenerable but kept. checkpoints/ v7
         kept (provenance for the 222k-crown deliverable). _backup_accept_all/ still
         HELD (recommend: keep until U1 + 2016c decisions close, then delete).
decided: labels/ are NOT hand labels — phase0_instance_seg.py header confirms
         "Distance transform GeoTIFFs per training site"; the hand-made assets are
         polygons/, photos/, and the 2020 mask. My permission layer blocked the labels/
         delete twice before Kam decided to keep it anyway.
files:   README.md (4 rows + cleanup line -> ~37 GB) · CHATLOG.md (this entry)
next:    phase2/"Copy of edmonds_crowns_phase1.gpkg" review still pending — layer-count
         comparison vs phase1 original was running in the background when this landed.

## 2026-08-19  README.md rewritten — full ecosystem map, every top-level item has a line
goal:    Kam must be able to walk a stranger through the whole tree and say what each
         thing does. Old README's directory map covered 8 of 51 top-level items;
         ~155 GB (inference/, phase3/, Full_Image/, checkpoints/, phase5/, labels/,
         tiles/, _backup_accept_all/ ...) was undocumented.
did:     Rewrote README as the map. New sections: entry-point chain (WORKPLAN_2026-08-19
         wins -> CHATLOG STATE live log -> README map; retired the "STATE is the single
         source of live truth" line), git architecture (tree on G:, DB on D:, tags
         v001-v048, whitelist .gitignore => everything else has NO git safety net, both
         remotes drive-mirror + github, Kam pushes --mirror himself), top-level map as
         3 tables LIVE / ARCHIVAL / HELD (name | size | status | what it is), data-flow
         prose imagery+labels -> Colab phase4seg -> masks -> QC vs independent refs ->
         Reports -> city deliverable, plus D:\edmonds-pipeline\Imagery 83GB mirror.
         Doc map now lists all 12 Scripts/*.md + 2 HTMLs + workplan xlsx + Reports/*.md
         + _archive/README with one-line purposes. Kept "Rule of the repo" one-home
         paragraph near top. Sizes flagged approximate (du on FUSE is slow).
         One cleanup line notes ~35 GB removed 2026-08-19; deleted items NOT in the map.
decided: load-bearing misspellings `City Boundry/` and `bathology/` documented as
         intentional (scripts reference the paths) instead of quietly renamed.
files:   README.md · CHATLOG.md (this entry)
next:    STALE, out of this worktree's write scope: CLAUDE.md rule 1c still names the
         mirror `G:\My Drive\_treedata_git_mirror.git` and says "no remote" - actual is
         `drive-mirror -> G:/My Drive/edmonds-git-mirror.git` + `github`. Also CLAUDE.md
         Drive-Layout ASCII still lists deleted phase6/.

## 2026-08-19  litwatch_scratch/README.md — new, documents INSTRUMENTS vs WRITERS split
goal:    litwatch_scratch/ (recovered lit-watch scratchpad) had no README - risk of
         someone re-running a one-shot ledger appender and duplicating entries.
did:     New README.md. Two populations: INSTRUMENTS (29 analysis scripts, safe to
         run, several verified/cited by project docs - buildings, cast, cast2*,
         chk1936, cr, height_by_surface, hist, overcount, overhang*, overhang_recall,
         q119, q121, q121b, q121c, q122, q128, q131, q131b, q134, q135, q136*, q137,
         q137b, q138, q138b*, refcompare, rescore, sampler*, unmeasurable - * = re-run
         and verified 2026-08-19); WRITERS (77 one-shot ledger appenders, NEVER
         RE-RUN - upd11-upd80 append to litwatch_robustness.md, chat69/chat72/chat77,
         entry3/4/5, append.py appends rows to Literature_Tracker.xlsx w/ auto-
         incrementing IDs - non-idempotent by design, output is the authoritative
         artifact). Also notes *.json = cached search results, *.out = captured
         outputs, *.npz = regenerable caches (git-ignored per this session's
         .gitignore commit).
         COUNT CORRECTION: task spec said 229 files; `find litwatch_scratch -type f`
         measured 227. Used the measured number per this project's honest-measurement
         rule rather than transcribing the unverified figure.
files:   litwatch_scratch/README.md (NEW)
next:    -

## 2026-08-19  Method_Pipeline.md imagery-stack table replaced with IMAGERY_FACTS.md pointer
goal:    stop Method_Pipeline.md's Imagery Stack table drifting from measured reality.
did:     Table listed 18 acquisitions with nominal GSDs - stale twice over (19 in-scope
         rasters on Drive, nominal GSDs wrong by up to 6x, per IMAGERY_FACTS.md).
         Replaced the table's content with a pointer to Scripts/IMAGERY_FACTS.md (one
         home, updated 2026-08-19) plus a one-line summary: 19 rasters, 2000-2024, 4
         sources (King County, City of Edmonds, Snohomish Co., NAIP). Rest of the file
         (tier logic, hyperparameters, etc.) untouched.
files:   Method_Pipeline.md
next:    -

## 2026-08-19  two stale-claim fixes — Reports/ tracking status, work-plan xlsx path
goal:    fix two outdated pointers found during the doc pass.
did:     canopy_definition_PROPOSAL.md said Reports/ is git-ignored so
         Measurement_Validity_Assessment_2026-08-18.md is NOT version-controlled -
         outdated since 2026-08-18, when Reports/*.md and *.csv started being tracked.
         Fixed the sentence to say it IS tracked.
         pipeline_buildtracker.md pointed at `Admin/Tree Project Work Plan.xlsx` -
         that file now lives at `Scripts/_archive/Tree Project Work Plan.xlsx`. Fixed
         the path.
files:   canopy_definition_PROPOSAL.md · pipeline_buildtracker.md
next:    -

## 2026-08-19  honest-measurement-overhaul.md demoted — superseded by WORKPLAN
goal:    stop honest-measurement-overhaul.md reading as live when WORKPLAN_2026-08-19.md
         already superseded it.
did:     Added SUPERSEDED 2026-08-19 banner under the title, pointing to
         WORKPLAN_2026-08-19.md (wins on disagreement; this file kept for provenance).
         Status line changed ACTIVE -> SUPERSEDED. §0 baseline table's 2016 recall
         0.684 (used the clipped reference) got an inline correction note - honest
         figure is .6636 per WORKPLAN §1.1 - number left as originally measured, not
         silently rewritten.
files:   honest-measurement-overhaul.md
next:    -

## 2026-08-19  CLAUDE.md entry-point chain fixed — WORKPLAN first, phase5/6 annotated
goal:    fix stale routing in Scripts/CLAUDE.md - it still pointed readers at CHATLOG
         STATE as "the single source of live truth", but WORKPLAN_2026-08-19.md and
         CHATLOG STATE itself have since agreed WORKPLAN is the entry point and wins
         on disagreement.
did:     Updated the top blockquote and the "Sources of truth" bullets to: read
         WORKPLAN_2026-08-19.md FIRST (entry point, wins on disagreement), then
         CHATLOG STATE for live log/state. Surgical - routing sentences only.
         Phase table: 5-8 row said "Not yet built" with no context. Annotated -
         phase5/ (3.8GB, model.pkl) and the now-deleted phase6/ were abandoned
         forward-experiments (Kam confirmed 2026-08-19); phase5/ stays because
         phase4_qc_score.py, phase4_qc_indep.py, phase4_threshold_diagnostic.py still
         read its outputs.
files:   CLAUDE.md
next:    Drive-Layout ASCII tree (line ~109) still says "phase5/…phase8/ not yet built"
         and lists phase6/ (now deleted) - same stale claim, different section, not
         in scope here.

## 2026-08-19  .gitignore fixes — Literature_Tracker whitelist bug + npz caches
goal:    close two .gitignore gaps found during the cleanup pass.
did:     whitelist bug: `!/Admin/Literature_Tracker.xlsx` matched nothing - the file
         lives at REPO ROOT (README.md line ~31), not Admin/. Result: the 68-paper
         tracker, actively used, modified 2026-08-19, was NEVER version-controlled.
         Added `!/Literature_Tracker.xlsx` at root, kept the old Admin rule as-is.
         Added `*.npz` to the Scripts binary-data excludes (alongside *.tif/*.pt/
         *.pth/*.parquet/*.gpkg) - covers the regenerable caches in litwatch_scratch/.
files:   .gitignore
next:    -

## 2026-08-19  ecosystem cleanup — GitHub connected, worktrees pruned, ~35 GB legacy deleted
goal:    repo hygiene pass (worktree worktree-ecosystem-cleanup) — GitHub backup, dead
         worktrees, orphan dirs, safe-tier legacy bloat.
did:     GITHUB: gh CLI 2.97.0 installed, authed as Kameron-Eck. Private repo
         github.com/Kameron-Eck/edmonds-treedata created. Remotes added: `drive-mirror`
         -> G:\My Drive\edmonds-git-mirror.git (NEW bare repo, Drive-synced) and `github`.
         Kam runs `git push --mirror` to both himself.
         WORKTREES: 12 merged worktrees + their worktree-* branches pruned. All verified
         merged into main first; `git branch -d` succeeded on every one (refuses on
         unmerged) - nothing lost.
         ORPHANS: C:\content Colab-path gotcha dir removed (verified 0 bytes first).
         D:\edmonds-pipeline\treedata orphan dir removed; its version_script.py variant
         (a blob not in git history) archived to
         Scripts/_archive/orphans/version_script_D-orphan-variant.py rather than deleted.
         SAFE-TIER DELETE (~35 GB, zero live references, Kam approved each category):
         temporal_results/ 8.8GB, phase6/ 3.6GB (abandoned experiment, Kam confirmed),
         clips/ 3.7GB, near_infrared/ 2.9GB, Temp/ 2.1GB, pipeline/ 940MB, Scripts_v2/
         (zero refs, its own text says Scripts/ is canonical), checkpoints/Temp/ ~13GB
         (superseded v5 generation; v7 root files kept), 0-byte stubs
         checkpoints/{ddt_best_global,test}.pt, Untitled0.ipynb,
         TreeCrownInventory.BACKUP-2026-07-08.ipynb (its extra code cells = the documented
         phase0_instance_seg.py extraction; outputs were only streams/errors/2 PNGs), 4
         empty dirs (NDVI, phase1c, review_data, .ipynb_checkpoints), stale ArcGIS
         *.sr.lock files in City Boundry/.
         PHANTOM-M: files on main showing modified with empty diffs (Drive mtime noise)
         cleared per-file after `git diff --quiet` verification; train_queue_status.csv
         left dirty on purpose (Colab 2024 inference RUNNING, real state).
decided: HELD BACK for Kam's explicit call: _backup_accept_all/ (1.9GB, sole pre-accept-all
         model snapshot) - not deleted, needs his sign-off.
         Verify-tier left untouched, dispositions pending: inference/ 108GB, checkpoints/
         v7 ~14GB, labels/, tiles/, impervious statewide tif, phase2 Copy-of gpkg.
files:   (repo-level ops; see git log / gh repo view for detail)
next:    Kam call on _backup_accept_all/. Verify-tier disposition pass.

## 2026-08-19  ** 1936 IS REAL IMAGERY ** + catalog conflict resolved (IMAGERY_PLAN A1/A3/A5)
goal:    execute IMAGERY_PLAN.md order-of-work 1-2 (A1 catalog conflict, A2/A3 orphans).
** RETRACTION **  1936 IS NOT AN EMPTY SHELL. Entry "GRVI IS NOT COMPARABLE ACROSS SENSORS
         + 1936 is an empty file" said "CONTAINS NO IMAGE DATA OVER EDMONDS", from 9 constant
         probe windows. WRONG. Full-extent decimated read: 89.9% fill (253/0/255), 10.1% REAL
         panchromatic photography in the SOUTHERN QUARTER. Content band starts 74.8% down the
         file (row 20094 of 26880) - below every probe. Rendered it: shoreline, street grid,
         forest stands, lake, field boundaries. Content bbox = 24.4% OF STUDY AREA,
         lat 47.768-47.792. Prize is 1936, not 1998 - 64 yrs before current earliest year.
         METHOD RULE: a scattered-window probe proves content EXISTS, never that it is ABSENT.
         Answer "nothing here" -> render whole extent before believing it. Second time this bit.
did:     A1 catalog conflict RESOLVED. phase4seg/config.py:YEAR_CATALOG authoritative.
         pipeline_config.py DEMOTED - docstring rewritten, IMAGERY_CATALOG frozen+labelled
         (2013+ only, its KeyError on raw_path(2000) was the bug). Only importers are
         _archive/scripts/, they still parse. Pointers fixed in CLAUDE.md + buildtracker.
         NEW phase4_catalog_check.py - resolves every entry thru the one resolution order,
         opens it, asserts on-disk BAND COUNT + EPSG vs catalog, lists ortho orphans, probes
         constant fill. 18/18 PASS. exit 1 on failure so it can gate a run.
         A5 ONE HOME: config.imagery_roots() defines root order, common.resolve_native_path()
         reads it. Colab order UNCHANGED (native/ -> root); local = D: mirror -> Drive.
         A3 renamed on D: 1936_king_rgb.tif -> 1936_king_pan.tif, 1998_king_rgb.tif ->
         1998_king_pan.tif. Single-band despite _rgb. Nothing referenced either name.
** NEW DEFECT **  D: MIRROR IS PARTIAL - holds King/Snoh/NAIP years, NONE of the 4 CoE orthos
         (2017/2020/2022/2024, ~127 GB). phase4_data_inventory.py scans ONLY D:. So the CoE
         acquisitions - INCLUDING 2020, THE ONE LABELLED YEAR - have NEVER been characterised
         by the inventory. Every "measured from the file" number for those 4 needs re-checking.
         ALSO: native/ does not exist at all (not empty - absent). Every lookup always fell
         through to the root.
decided: keep 1936 (real data). quarantine nothing - measurement beat assumption.
killed:  "1936 is an empty shell / delete it" - refuted, see RETRACTION.
files:   phase4seg/config.py (imagery_roots) · phase4seg/common.py (resolve_native_path) ·
         pipeline_config.py (demoted) · phase4_catalog_check.py (NEW) · CLAUDE.md ·
         pipeline_buildtracker.md · IMAGERY_PLAN.md (A1/A3 done, A2 table corrected)
next:    IMAGERY_PLAN order 3 (B2 overviews - use gdaladdo -ro, external .ovr, do NOT mutate
         Drive originals) then 4 (B1 merged inventory - MUST cover both roots, not just D:).
         Open: A2 disposition for 2012_king + 2017_king; A4 dates (external).

## 2026-08-19  ** THE MODEL IS BETTER THAN ITS NUMBERS ** - calibration, not capability, is binding
** [AUDIT 2026-08-19 by the other session — READ BEFORE QUOTING ANY NUMBER BELOW] **
** THE CODE BEHIND THIS ENTRY NO LONGER EXISTS AND ITS NUMBERS CANNOT BE REPRODUCED. **
         The entry's own files: line names q121c.py, q131b.py, q134.py, q135.py, sampler.py
         (the 162,829-pt grid), cast2.py, chk1936.py as a "scratchpad, all READ-ONLY". Those
         live OUTSIDE the repo and vanished when the session was stopped. `find` over the
         whole tree returns none of them. So the 61% spread-reduction, the AUC-vs-proxy table
         and the matched-call-rate recalls have NO surviving derivation.
         STATUS: treat every number in this entry as UNVERIFIED. Not wrong — UNCHECKABLE.
         Do not cite it as established, and do not build a decision on it. To promote any of
         it, re-derive with a tracked script.
         WHAT DOES SURVIVE, and is committed (58ee67c): the four QC scripts
         (phase4_qc_leafoff / _turnover / _domain_cluster / phase4_build_ccap_city) and their
         outputs. Those compile and their logic reads sound. Known defects, none fatal:
         phase4_qc_leafoff.sample() computes `bounds` and never uses it; it rebuilds a
         WarpedVRT over the whole ortho inside the window loop; and `can = m > 0` counts
         255=IGNORE as canopy, which violates rule 6 but is HARMLESS on
         edmonds_canopy_mask_2020.tif specifically because that raster holds only 0 and 1
         (checked). It would silently corrupt any mask that does carry IGNORE.
         ALSO CORRECTED: this session repeated the "61% reduction" figure in conversation as
         if it were established, before checking it was reproducible. It was not.
         The LITERATURE side is a different matter and is NOT in question — DOIs verified
         against Crossref, an explicit inclusion bar, covered/queued discipline. Use
         litwatch_robustness.md for its literature; do not inherit its measurements.
scope:   loop iterations 73-77. Measurement + code reading. Nothing deployed, no plan edit.
** FINDING 1 - MOST OF THE CROSS-YEAR RECALL WANDER IS THE OPERATING POINT (Q121). **
         One recipe (_citywide_rgb), one reference (C-CAP), one footprint (161,052 pts, 98.9%),
         8 years. Only the operating point is varied.
           recall spread @ FIXED thr 0.5      0.1827
           recall spread @ MATCHED call .30   0.0721      = 61% REDUCTION
         Mechanism: thr 0.5 calls 22.0%-30.5% of the city depending on year. A fixed threshold
         is NOT a fixed operating point.
         RESIDUAL IS INTERPRETABLE where finding 3's 0.28 wander was not:
           2000 .6454 · 2002 .6541          <- the two coarsest (~40 cm true GSD)
           2005-2021 .6974 .7052 .7069 .7174 .7155 .7086   <- ALL WITHIN 0.020
         across 16 years, 3 providers and a 4x resolution change.
         CREDIT: the 2026-08-18 recipe-controlled run is column two here. This adds the SECOND
         control, not the first. The two together account for most of finding 3.
         ANOMALY: 2007 gives IDENTICAL recall at cr .20 and .25 (.6189) -> degenerate/saturated
         raster. DO NOT quote the cr=.20 row until understood (Q133).
** FINDING 2 - THE MODEL DOES NOT RELY ON COLOUR, AND IS MORE STABLE THAN ITS INPUTS (Q135). **
           year  AUCmodel  AUCbright  AUCgrvi  gain   corr(m,grvi)
           2000    .8760     .6333     .5927  +.2427     +.1882
           2005    .9134     .7170     .6941  +.1964     +.4737
           2009    .9195     .6847     .7061  +.2348     +.4745
           2013    .9125     .6881     .7273  +.2243     +.5428
           2021    .9150     .6662     .5453  +.2488     +.0755
           RANGE   0.044     0.084     0.182
         MODEL AUC VARIES 4x LESS THAN THE COLOUR STATISTICS OF ITS OWN INPUTS. Threshold-free,
         so no calibration choice is doing the work.
         2021 IS DECISIVE: worst GRVI of any year AND lowest model-GRVI correlation (+.0755,
         ~zero), yet model AUC .9150 - its second best. With 2000 (colour saturated, model still
         .8760) that is TWO independent extreme cases, not an inference from correlations.
         ONLY DIP IS 2000 = THE COARSEST YEAR. 2021's colour is worse and does not dip.
         => RESOLUTION separates the years, COLOUR DOES NOT. Same asymmetry finding 1 found.
** FINDING 3 - THE REFRAMING NUMBER: AUC .876-.920 vs MATCHED RECALL .645-.717. **
         The model's RANKING is strong and stable; only WHERE THE LINE IS DRAWN is weak.
         Q132 PREMISE CONFIRMED IN CODE: phase3_semantic_dev.py:1722
           canopy_area = total_canopy_px * pixel_area
         The AREA SERIES - the deliverable - is MAP-COUNT off a thresholded mask, with
         binary_closing applied first, which inflates it further by a threshold-dependent amount.
         phase4_qc_score.py:83 already calls its threshold source "the (circular) eval CSV".
         THREE INDEPENDENT LINES CONVERGE (GRVI drift it.72, operating point it.73, AUC gap
         it.76/77): THIS PROJECT'S MODEL IS BETTER THAN ITS NUMBERS, AND THE NUMBERS ARE
         DOMINATED BY CALIBRATION AND A MAP-COUNT ESTIMATOR.
decided: nothing deployed. Highest-value fix identified (Q136): estimate area from a REFERENCE
         SAMPLE, not by counting thresholded pixels. NOT new research - the Olofsson/CEOS
         machinery is already in the tracker and P3's sample design already exists.
         Colour-comparability problems (it.72/74/75) are REAL BUT NOT BINDING - the model
         already largely ignores the channel they damage.
lit:     +6 papers, IDs 204-209, searches 59-60, DOI/arXiv verified.
           204 Canty & Nielsen 2008 RSE - IR-MAD, invariant to gain/offset
           205 Ryadi 2023 Sensors - cross-sensor relaxation-based normalisation
           206 Chen 2023 Appl.Sci - pseudo-invariant POLYGONS (we have roofs + impervious)
           207 Geirhos 2019 ICLR - CNNs texture-biased. Unifies transfer-vs-resolution asymmetry.
           208 arXiv 2509.20234 (2025) - DIRECTLY CONTRADICTS 207. Read BEFORE leaning on it.
           209 arXiv 2509.11355 (2025) - frequency regularisation for shape bias (conditional)
         NOTE Q130/Q134 ANSWERED NEGATIVE BY MEASUREMENT: AUC is invariant under ANY monotone
         transform, so IR-MAD/histogram matching CANNOT rescue GRVI where AUC ~ 0.5 - and that
         is 2000 (.5927), 2019 King (.5835) and 2021 King (.5453). Normalisation is still worth
         doing for cross-year THRESHOLD comparability, but NOT to make greenness work.
files:   Scripts/litwatch_robustness.md (it.73-77 + Q131-Q136)
         Literature_Tracker.xlsx (210 papers, 60 searches)
         scratchpad, all READ-ONLY: sampler.py (162,829-pt grid), q121c.py, q131b.py, q134.py,
         q135.py, cast2.py, chk1936.py
next:    Q136 area-from-reference-sample. Then channel ablation (needs GPU) for Q98.
gotcha:  NO RASTER IN THIS PROJECT HAS OVERVIEWS (ovr=[] everywhere) and the prob rasters are
         ROW-STRIPED (block=(1,18944)), so every out_shape/decimated read silently reads the
         WHOLE file. Two runs stalled ~40 min at 3.5 GB before this was found. Use
         scratchpad/sampler.py point sampling instead - seconds, not tens of minutes.
         Building overviews would speed every future QC run but writes GB of sidecars on G:,
         so that is Kam's call.

## 2026-08-19  ** GRVI IS NOT COMPARABLE ACROSS SENSORS ** + 1936 is an empty file
scope:   loop iterations 70-72. Measurement + inventory. Nothing deployed, no plan edit.
** THE FINDING **  GRVI over the SAME GROUND in every acquisition, 2400 px window:
           frac>.02 = share of pixels a naive GRVI vegetation test calls green
           2000 King .8027 | 2002 .5029 | 2005 .4782 | 2007 .4016 | 2009 .6237
           2012 .6268 | 2013 .3463 | 2015 .2745 | 2017 .1877 | 2019 .1146
           2021 .1344 | 2023 .1541 | 2016 Snoh .6928 | 2019 NAIP .8919 | 2022 NAIP .7822
         DECISIVE PAIR: 2019 King .1146 vs 2019 NAIP .8919. SAME YEAR, SAME GROUND, SAME
         SEASON, differing by 0.78. Cannot be vegetation, phenology, growth or loss. It is
         sensor + processing colour balance and nothing else.
         AND THE KING SERIES DRIFTS MONOTONICALLY: .80 (2000) -> .35 (2013) -> .11 (2019),
         GRVI mean crossing positive-to-negative around 2017. ANY cross-year GRVI diagnostic
         on this series reports a large steady CANOPY DECLINE THAT IS PURE ARTEFACT.
         DAMAGES OUR OWN WORK: the leaf-off / canopy-rendering signature compared low-
         greenness fractions BETWEEN years. Those comparisons are NOT SAFE. The WITHIN-year
         use (canopy-masked pixels vs the rest of the same image) survives, because the cast
         is global. That distinction is the whole of what is left standing.
killed:  cross-year GRVI comparisons. Do not re-quote them (Q129 = trace what used them).
** CORRECTION **  1936_king_rgb.tif CONTAINS NO IMAGE DATA OVER EDMONDS.
         I reported it in it.71 as "clipped at the bright end, bright detail destroyed".
         WRONG. Nine probe windows across the city are ALL CONSTANT: mean 253.0 std 0.00
         min=max=253 in the south/centre, 0.0 in the north. A georeferenced EMPTY SHELL.
         The "p99=255 clipping" was fill value in a whole-raster downsample.
         WHY: these are KING COUNTY mosaics and EDMONDS IS IN SNOHOMISH COUNTY. A 1936 King
         survey does not reach this far north. INDEPENDENT BONUS: 2000's northern probes are
         also all-zero, so the known north-coverage gap is A COUNTY LINE, not a footprint quirk.
         1998 IS REAL (std 29-44 at all nine probes, whole city) and single-band, on the
         IDENTICAL grid to 2000 -> still the clean panchromatic pilot with a near-
         contemporaneous RGB control. Prize is 2 extra years, not 60.
did:     also (it.71) 1936/1998 are SINGLE-BAND despite _king_rgb names; every other
         _king_rgb is 3-band and phase1_preprocess.py assumes it. Dormant only because grep
         finds 1936/1998 in NO config. They share the 2000 grid exactly (18944x26880) so
         co-registration looks already done - but their GSD is INHERITED FROM THAT GRID, not
         measured from film. Do not quote grid spacing as resolution.
         (it.70) RELIEF DISPLACEMENT, 0 of 197 papers covered it. A conventional ortho is
         rectified on a BARE-EARTH DTM, so only the BASE of a tree lands correctly; everything
         above ground is displaced radially PROPORTIONAL TO HEIGHT. d=(h/H)*r -> a 20 m crown
         500 m off nadir at 3 km = 3.3 m = 33 px at King's true 10 cm GSD. Runs along the SAME
         axis as our staircase but CUTS AGAINST it (tall-band recall is our highest, .9421), so
         it cannot be manufacturing the staircase. BIGGER RISK IS THE DELIVERABLE: 17
         acquisitions = 17 frame layouts = 17 displacement fields -> SPURIOUS CHANGE on tall
         crowns near buildings (Q125).
** INFRASTRUCTURE **  NO RASTER IN THIS PROJECT HAS OVERVIEWS (ovr=[] on every file checked),
         so every out_shape / decimated read silently reads the ENTIRE file. The prob rasters
         are also ROW-STRIPED, block=(1,18944), not tiled. Two QC runs stalled at 3.5-3.7 GB
         for ~40 min before I found this. FIX ADOPTED: scratchpad/sampler.py builds a 162,829-
         point systematic grid inside the city and samples rasters at points - seconds, not
         tens of minutes. Building overviews would help every future QC run but creates GB of
         sidecar files on G:, so that is Kam's call, not mine.
lit:     +9 papers, IDs 195-203, Phase 6 searches 56-58, all DOI-verified via Crossref.
           195 Techapinyawat 2024 CACAIE - retrieves CANOPY-COVERED IMPERVIOUS SURFACES
           196 Liu 2023 RS 15:519 - U-Net specifically suffers SHADOW omission (tested, refuted)
           197 Yoo 2026 RS 18:1899 - transferable NAIP canopy framework (NAIP = our 2019n/2022n)
           198 Gharibi 2018 RS 10:581 - true ortho from frames + LiDAR; names the DTM defect
           199 Wagner 2024 RSE 302:114099 - U-Net regression, 60 cm NAIP -> LiDAR CHM, statewide.
               This is our v045/v046 aux-height experiment ALREADY DONE at scale.
           200 Chen 2014 ISPRS XL-3:67 - double-mapping; spurious multitemporal change
           201 Mboga 2020 ISPRS J 167:385 - FCN land cover from PANCHROMATIC historical frames
           202 Tian 2025 ISPRS Ann X-G:885 - NO method works on panchromatic alone; uses DL
               COLORIZATION as the bridge. Absent from all 200 prior rows.
           203 Kostrzewa 2025 PE&RS - CNN LULC from historical aerial (provisional, abstract unread)
files:   Scripts/litwatch_robustness.md (it.70, 70c, 71, 72 + Q123-Q130)
         Literature_Tracker.xlsx (204 papers, 58 searches)
         scratchpad only, all READ-ONLY: sampler.py, cast2.py, chk1936.py, q119.py, q122.py,
         height_by_surface.py, q121c.py, q128.py
next:    Q121 running (cross-year recall at MATCHED CALL RATE, point-sampled). Then Q128 -
         model DISAGREEMENT as a label-free reliability proxy: 2000/2002/2013/2015 each carry
         4-5 independently trained variants, and Baek 2022 (ID 153) says mutual agreement
         estimates OOD accuracy. Validate against measured recall before trusting it.
gotcha:  a substring match on a filename is NOT evidence - EDM_0001936.jpg is crown 0001936,
         not the year 1936, and I briefly claimed 1936 crops existed on that basis.
         piping a background job through grep BUFFERS all output until exit; use `py -3 -u
         script.py > out.txt 2>&1` instead so partial progress is readable.
         `python` is not on PATH, only `py -3`.

## 2026-08-19  TWO REFUTATIONS AND A DEPLOY WARNING - what is NOT causing the overhang gap
scope:   loop iterations 67-69, all measurement, nothing deployed, no plan file edited.
did:     (1) Q118 HEIGHT AND OVERHANG ARE INDEPENDENT, NOT THE SAME THING.
           Recall by CHM band split by surface beneath, 2016 vs C-CAP city.
           staircase SURVIVES on pervious alone: 0-2m .1206 -> 30+m .9421, spread +.8215
           staircase on impervious:              2-5m .0282 -> 30+m .7509, spread +.7227
           impervious penalty is roughly CONSTANT above 5 m (-.19 to -.29), so the two
           deficits are ~ADDITIVE. Both need fixing separately.
           WORST CELL: 2-5 m OVER IMPERVIOUS = .0282. Model finds under 3% of it. That is
           street/yard trees beside driveways - the canopy a tree ordinance is about.
           And the impervious penalty is NOT a short-tree artefact: -.19 even above 30 m.
         (2) Q119 THE CORRECTED MODEL'S OVERHANG GAIN IS AN OPERATING-POINT ARTEFACT.
           prob_2016 vs prob_2016_corrected, COMMON footprint, 321,651 C-CAP canopy cells.
           at thr .509      recall .6279 -> .8533   over-imp .3183 -> .5612   LOOKS GREAT
             but call rate on C-CAP non-canopy .0493 -> .1725  (TRIPLES)
           at MATCHED overall recall (thr .835)
                            recall .6279 -> .6296   over-imp .3183 -> .3070   GAIN REVERSES
             gap -.3739 -> -.3895 (WIDER); worst cell .0282 -> .0366 (nothing)
             matched gap WORSE where it matters: -.076 at 2-5m, -.050 at 5-10m
           IT MOVED ITS OPERATING POINT, IT DID NOT LEARN OVERHANG.
           CAVEAT STATED, not buried: corrected from NIR+CHM but scored against C-CAP, so
           this is an AGREEMENT statement not a TRUTH statement. Q120 settles it.
         (3) Q122 SHADOW REFUTED AS THE MECHANISM.
           Liu 2023 RS 15:519 says U-Net specifically suffers shadow omission - our arch,
           our symptom. Shadow falls NORTH, contrast is isotropic -> separable by geometry.
           bearing from nearest building, 2016:  N-S = +.0354 (10m) / +.0221 (20m)
           north is BETTER. Holds within matched geometry: faces N .5071 vs S .4401,
           corners +.020, E-W control flat. SIGN ERROR against the hypothesis.
           FLAGGED NOT READ INTO: cardinal .44-.51 vs diagonal .58-.61, spread .123 = 5x
           the N-S effect. Axis-aligned footprints, wall faces vs corner wedges. Artefact.
decided: nothing deployed. RADIOMETRIC FIXES RULED OUT (shadow compensation, histogram
         matching, illumination normalisation). With corrected labels also ruled out, the
         candidate list is down to HEIGHT CHANNEL or NIR BAND - v045/v046 aux-height on the
         impervious split is now the leading untested experiment.
lit:     +3 papers, IDs 195-197, Phase 6 Search 56, all DOI-verified via Crossref:
           195 Techapinyawat 2024 CACAIE 10.1111/mice.13277 - retrieves CANOPY-COVERED
               IMPERVIOUS SURFACES by post-classification. Exact inverse of our failure mode.
           196 Liu 2023 RS 15(2):519 10.3390/rs15020519 - the U-Net shadow claim above.
           197 Yoo 2026 RS 18(12):1899 10.3390/rs18121899 - transferable NAIP canopy
               framework. NAIP is our 2019n/2022n. External benchmark we currently lack.
files:   Scripts/litwatch_robustness.md (it.67-69 + Q120-Q123)
         Literature_Tracker.xlsx (197 papers, 56 searches)
         scratchpad only: height_by_surface.py, q119.py, q122.py - all READ-ONLY, none
         write to phase4/qc
next:    Q123 RELIEF DISPLACEMENT - a genuine blind spot. Ortho displaces elevated objects
         radially from nadir AND THE DISPLACEMENT SCALES WITH HEIGHT, which is the exact
         axis our staircase runs along. C-CAP is stereo-DSM derived and may be nearer
         true-ortho, so mask and reference may be misregistered AS A FUNCTION OF HEIGHT.
         Tracker search for off-nadir / view angle / BRDF / orthorectif returns 0 of 197.
         Then Q121 (running): re-score the cross-year series at MATCHED CALL RATE. Finding
         3's .50-.78 wander has never been checked against the it.68 artefact.
gotcha:  Q121 EVERY per-year threshold is calibrated separately, so ANY cross-year recall
         comparison in this pipeline is confounded until re-scored at matched operating
         point. it.68 shows the size of the effect: +0.225 of pure nothing.
         `python` is not on PATH here, only `py -3` - a heredoc starting `python -` fails
         silently mid-chain and the NEXT command still runs, so check for the alias error.
         Crossref titles carry U+2010; console is cp1252; sanitize to ASCII before print.

## 2026-08-19  ** LEAF-OFF ** - the acquisition SPEC may explain the conifer-only blind spot
goal:    lit-watch loop, iteration 45. Standing top action was "recover acquisition dates".
         Found something better: the published acquisition SPECIFICATIONS.
did:     Searched King County / Puget Sound consortium and NAIP acquisition specs.
         -> Literature_Tracker ID 194. Re-read the iteration-18 GRVI screen against them.
THE TWO SPECS ARE OPPOSITE:
  * PUGET SOUND REGIONAL ORTHOPHOTO CONSORTIUM (88 participants, King County lead manager -
    the source of our King imagery): "acquisition was to occur during LEAF-OFF season while
    ground conditions were free of snow and smoke". 2012 flown March-May "with the intent of
    representing leaf-off conditions". 2015 acquired "in the spring".
  * NAIP: flown "during the agricultural growing season, or LEAF-ON conditions".
  -> OUR ARCHIVE MIXES LEAF-OFF AND LEAF-ON AND NOTHING IN THE PIPELINE ACCOUNTS FOR IT.
IF 2020 CoE FOLLOWED REGIONAL PRACTICE (not yet confirmed), our ONE hand-labelled year was
labelled on imagery where DECIDUOUS CROWNS ARE BARE. Physical explanation for findings we have
treated as modelling defects:
  * "conifer-only-label blind spot" -> deciduous crowns not in the labelling imagery at all
  * scrub recall .25 vs forest .68  -> deciduous scrub bare, conifer forest visible
  * recall .16 (0-5m) -> .93 (30m+) -> short crowns skew deciduous yard/ornamental
  * 8/8 missed stands suburban, "purple-leaf LOW-NDVI" -> purple-leaf = deciduous = bare in spring
  * FINDING 3 IS THE TELL: 9 years span IoU .49-.76 yet recall stays pinned .51-.78. That is
    what you see when the limit is WHAT THE IMAGERY CONTAINS, not the model.
INDEPENDENT SUPPORT - iteration-18 GRVI screen re-read: both NAIP years (spec LEAF-ON) rank
  top-5 of 17 by green-excess; the bottom SIX are all King County or City of Edmonds
  (consortium, spec LEAF-OFF); 2020 is 4th LOWEST of 17.
NOT PROVEN: confirmed = the consortium SPEC, and that KC 2012/2015 were spring flights.
         NOT confirmed = that 2020 CoE followed it, nor the season of Snoh 2016/2021s.
         GRVI stays confounded with colour balance (iteration-18 caveat stands).
         RECOVERABLE: King County photo-centre index carries per-exposure ACQ_DATE + UTC_TIME.
IF IT HOLDS, IT REORDERS THE PROJECT:
  * blind spot is a DATA problem not a model problem - no architecture, augmentation, domain
    generalization or foundation model recovers deciduous crowns from leaf-off pixels.
  * right fix = LABELS ON LEAF-ON IMAGERY (NAIP years, or Snoh if leaf-on), NOT better training
    on 2020.
  * any cross-era comparison mixing leaf-off with leaf-on measures PHENOLOGY, not canopy.
  * the height curve may be substantially a DECIDUOUS-FRACTION curve.
also this session (lit-watch iterations 43-44), NEW Scripts/phase4_qc_turnover.py:
  * C-CAP 2016 vs 2021: discordance 11.16%, net -1.72pp LOSS, implied 5.33%/yr canopy loss -
    which EXCEEDS published street-tree mortality, so most of it is product revision not trees.
  * NDVI ref 2016 vs 2021s (same source, same sensor): discordance 11.14%, net +2.45pp GAIN.
  * -> THE TWO REFERENCES DISAGREE ON THE SIGN OF CHANGE. Neither can say whether Edmonds
    gained or lost canopy 2016-2021. C-CAP dominated by vintage revision, NDVI by phenology
    (its CHM is static across both dates, so the whole signal is greenness).
  * BUG FOUND+FIXED in that script: 0 = nodata in C-CAP but NON-VEGETATED in the NDVI refs.
    First run gave a false 0.97% discordance / 90.6% stable-canopy. --zero-is-data flag added.
files:   Scripts/litwatch_robustness.md (iterations 43-45) - Literature_Tracker.xlsx ID 194
         Scripts/phase4_qc_turnover.py - phase4/qc/turnover_{ccap_2016_2021,ndvi_2016_2021s}.txt
next:    (1) CONFIRM THE 2020 SEASON - photo-centre index, ortho metadata, or ask the City.
         Everything else is downstream. (2) season-label all 18 acquisitions. (3) recall-by-height
         on a LEAF-ON year (2019n/2022n, rasters already scored) vs a leaf-off year.
gotcha:  leaf-off flights are also LOW SUN ANGLE, so the shadow axis and the phenology axis are
         CORRELATED, not independent. Do not treat them as separate confounds.

## 2026-08-18  EDGE TEST — the perimeter hypothesis is TRUE, and the height staircase survives it
goal:    test the crown-perimeter hypothesis raised by the sentinel overlays, BEFORE it could
         reach the annotation plan. It threatened result (1), so it had to be measured.
did:     NEW Scripts/phase4_qc_edge_vs_interior.py — erodes the agreed-canopy mask (numpy-only
         8-connected erosion, no scipy) to split misses into crown INTERIOR vs EDGE, then
         recomputes recall by height band for each. Ran 2016 at decim 4 (2 m lattice), erosion
         1 and 2 cells. -> phase4/qc/edge_vs_interior_{2016_baseline,2016_erode2}.txt/.csv
RESULT: BOTH halves positive — see STATE result (8).
         (a) edge (outer 2 m) = 16.3% of agreed-canopy AREA but 41.8% OF ALL MISSES;
             interior recall .8191 vs edge .3306. At 4 m: 29.3% area / 65.5% misses.
             The sentinel ring pattern GENERALISES. Suburban recall .575 is substantially
             UNDER-SEGMENTATION, not blindness => a second lever: boundary/soft-label handling.
         (b) the staircase SURVIVES inside crowns: interior 5-15 m .6218 -> 20 m+ .9333,
             spread +.3115 vs edge +.3105 — the two effects are INDEPENDENT AND ADDITIVE.
             Robust at 4 m erosion (interior spread still +.2528).
decided: nothing deployed. Result (1) stands unchanged; the new finding is ADDITIVE to it,
         not a replacement. Two distinct levers now on the table (height-conditioned training,
         boundary handling) plus the operating point from result (7).
killed:  "the height staircase might be crown geometry" — TESTED AND REJECTED. Do not re-raise
         without new evidence; the interior-only spread is the number that settles it.
files:   Scripts/phase4_qc_edge_vs_interior.py (new) · phase4/qc/edge_vs_interior_*.txt/.csv ·
         CHATLOG STATE result (8).
next:    [both done same session] replicated on 2021s + bounded the reference-error caveat
         via CHM — see result (8c)/(8d). U1 (Kam) is now the only blocker; remaining local
         work is thin.

## 2026-08-18  P4 CLOSED — sentinel error overlays, and a NEW hypothesis: the misses are CROWN EDGES
goal:    last open P4 item = sentinel TP/FN/FP overlays colour-coded by the P2 partition.
did:     NEW Scripts/phase4_sentinel_qc_overlay.py — 3 panels per fixed sentinel window:
         RGB | P2 agreement partition | model outcome. Imports phase4_sentinel_snap for the
         window/bounds helpers so a site here is the SAME rectangle as there (cross-run
         comparability preserved; the existing script is untouched).
         DESIGN POINT: TP/FN/FP are drawn ONLY on ground where both references agree.
         Contested pixels get their own colour and are NEVER scored — scoring them is the
         single most common way this project has misled itself.
         Ran all 11 sites for 2016 -> phase4/qc/sentinel_overlays/*.png +
         sentinel_overlays_2016.csv
         NOTE: the "needs footprint resolution from photos/" blocker in STATE was STALE —
         sentinel_sites.json already had explicit bounds_wgs84 for every site.
RESULT — recall on AGREED ground (not comparable to citywide qc_indep, which includes
         contested px): forest_6 .955 · forest_1 .826 · forest_4 .825 · marsh_deciduous .786 ·
         forest_3 .750 · residential_mixed .575. Precision .92-.998 EVERYWHERE.
         The conifer-training -> mixed -> suburban gradient is now VISIBLE, not just tabular.
** NEW HYPOTHESIS (visual, NOT yet measured) — THE FN ARE CROWN PERIMETERS. **
         In residential_mixed and marsh_deciduous the red FN forms RINGS around the green TP
         cores: the model finds each tree clump and loses its EDGE. If that generalises,
         recall .575 there is largely a PERIMETER loss, not whole missed trees — a different
         diagnosis from "the model cannot see yard trees", and it would need a different fix
         (boundary/soft-label handling or the operating point, not new crown labels).
         IT ALSO TOUCHES RESULT (1): crown edges have LOWER CHM than crown centres, so the
         5-15 m band may be over-populated by EDGE pixels of tall trees rather than by short
         trees. That would make part of the height staircase a geometry artefact.
         TEST BEFORE BELIEVING ANY OF THIS: split FN into interior vs edge (binary erosion of
         the agreed-canopy mask) and recompute recall by height band for each. Local, cheap.
         Do NOT let this into the annotation plan until that runs — it is one look at two
         windows.
decided: nothing deployed. P1/P2/P4 now all complete; P3 is the only phase left and is gated
         on U1, which is Kam's call.
files:   Scripts/phase4_sentinel_qc_overlay.py (new) · phase4/qc/sentinel_overlays_2016.csv ·
         phase4/qc/sentinel_overlays/*.png (NOT tracked — figures, per the rasters rule) ·
         CHATLOG STATE PHASE STATUS.
next:    the edge-vs-interior FN test above. Then U1 (Kam).

## 2026-08-18  U4 ANSWERED — calibration is a real lever, and the old per-year spread was a recipe artefact
goal:    cheapest-next-move #4 / STATE correction (3): recompute miss-depth PER YEAR on ONE
         recipe, so the "labels vs calibration" call stops resting on 2016 alone.
did:     NO NEW CODE — phase4_qc_forest_misses.py already takes --years + --prob-suffix, and
         its own footer says to compare within one recipe (--force-citywide) to avoid the
         tier-recipe confound. Ran --years 2000,2002,2013,2015 --prob-suffix _citywide_rgb
         --thresh 0.5 (fixed threshold = the fair cross-sensor choice). ~55 min, local, no GPU.
         -> forest_miss_{2000,2002,2013,2015}.txt/.csv + forest_miss_sensor_compare.txt/.csv
RESULT: see STATE result (7). Headline = 52-72% of missed forest sits NEAR THRESHOLD in all
         four years, so the operating point is a genuine lever and hand-tracing is not the only
         option — but lowering it lifts every band and costs precision, so it is not free.
         THE FINDING BEHIND THE FINDING: the per-year spread that motivated the question
         (24.1/19.4/9.3) DISSOLVED on one recipe (27.7/31.8/30.8). A recipe change moved 2013
         by 22 POINTS. Most of that "cross-year variation" was never about the year.
decided: nothing deployed, no plan edit, no annotation commitment. Measurement only.
killed:  every per-year conf% in STATE correction (3) — recipe artefacts, do not re-quote.
         "2016 is the outlier at ~60% deep" — NOT ESTABLISHED. 2016 has no _citywide_rgb
         raster, so it was never measured on this recipe; after (b) that comparison is
         unsafe. Do not build an annotation plan on it.
files:   phase4/qc/forest_miss_{2000,2002,2013,2015}.txt/.csv (updated) ·
         forest_miss_sensor_compare.txt/.csv · forest_miss_stands_*.csv ·
         CHATLOG STATE result (7) + correction (3) marked SUPERSEDED + cheapest-moves list.
next:    U1 still the blocker. New queued item: 2016 --force-citywide inference on Colab so
         its miss-depth becomes comparable — that is the one number that would decide whether
         2016 genuinely differs or just had a different recipe.

## 2026-08-18  SAMPLE SIZE WAS NEVER THE PROBLEM — interpreter fidelity is
goal:    cheapest-next-move #2: the assessment's "n=250 cannot arbitrate" (§3.1) rests on
         SIMPLE RANDOM SAMPLING arithmetic and flags itself as such (§5). The real weights
         now exist on disk (--step design ran for 2016/2022n/2000), so stop assuming.
did:     NEW Scripts/phase4_qc_design_power.py — Monte-Carlo of the ACTUAL design: real W_h
         + real allocation from sample_{year}_meta.json, the design's own strata rebuilt via
         phase4_accuracy_sample.build_strata, and the SAME Olofsson estimator with the full
         multinomial covariance (8283232). 1500 simulated studies per cell.
         -> phase4/qc/design_power_{2016,2022n}.txt/.csv
RESULT: see STATE result (6). §3.1 CORRECTED — stratified half-width .0122-.0469 vs the
         SRS .0620 the assessment assumed; n=250 DOES arbitrate in 2016 at <=5% interpreter
         error. The binding constraint moved from SAMPLE SIZE to INTERPRETER FIDELITY.
         Two things worth more than the headline:
         (a) the 0%-error row is RIGGED (truth defined as a reference => no within-stratum
             variance in strata built from that reference). Built the sweep precisely so that
             number can never be quoted alone.
         (b) interpreter error is not symmetric in EFFECT: flipping labels pulls estimates
             toward .5, i.e. UP from both hypotheses, so sloppiness systematically favours the
             shrub-inclusive definition. power(H_CCAP) .889->.436 while power(H_NDVI) stays 1.0.
decided: nothing deployed, no plan amendment applied (Kam's sign-off). Measurement only.
killed:  "n=250 cannot arbitrate, resize the sample" — DEAD for the wrong reason. Do not
         re-derive n from the +/-5.9pp SRS figure; that number does not describe this design.
         "run 250 x 3 years" — evidenced against: reference separation 2016 8.24pp vs 2022n
         4.65pp, so 2022n is marginal at 5% error. 2016 deep, per amendment 3.
files:   Scripts/phase4_qc_design_power.py (new) · phase4/qc/design_power_*.txt/.csv ·
         CHATLOG STATE results (6) + item (c) + cheapest-moves list.
next:    U1 canopy definition — now the ONLY thing between here and a defensible P3 run.
         Then wire the duplicate-interpreted subset (amendment 5) into --step design; result
         (6) makes it load-bearing, not a nicety.

## 2026-08-18  U2 REFRAMED — the reference dispute is a DEFINITION dispute, and LCA proved its own limit
goal:    run cheapest-next-move #1: Foody-2022 latent class on C-CAP x NDVI-ref x model.
         Give each source a sensitivity/specificity with NO gold standard, before spending
         human hours on P3. Local, no GPU, no labelling.
did:     NEW Scripts/phase4_qc_latent_class.py — 2-class 3-indicator LCA by EM, fitted
         globally AND within each CHM height band, 95% CIs from a SPATIAL BLOCK BOOTSTRAP
         (64-cell blocks; binomial CIs on 21M autocorrelated px would be fiction).
         Band-conditioning is not decoration: height drives every source's error rate, so
         conditioning on it absorbs much of the shared dependence between sources.
         Ran 5 configs -> phase4/qc/latent_class_{2016_baseline,2016_corrected,2021s,
         2019n,2022n}.txt/.csv
VALIDATED BEFORE TRUSTING (both committed, both runnable):
         phase4_qc_latent_class_test.py — recovers known truth to <.002 on synthetic data,
         stable across 12 seeds (spread 7e-11), and CONFIRMS the just-identified claim
         (reproduces the 8-cell table to 9e-12 — so a perfect fit is arithmetic, not evidence).
         Its rho-sweep also MEASURES the failure mode: correlate 2 sources and the odd one
         out loses .07-.12 of sensitivity while the pair is flattered.
         phase4_qc_latent_class_adversarial.py — see result (5c) in STATE.
RESULT: see STATE result (5)/(5b)/(5c). Headline = pi ~ .29 across 4 baseline years, on
         C-CAP's total, not the NDVI ref's; the NDVI ref is liberal and its surplus sits in
         the 2-5m band (shrubs/hedges); the model is the strictest of the three.
         The two answers are TWO DEFINITIONS. U1 decides, no estimator can.
decided: nothing deployed, nothing in the plan edited, no §4 amendment applied (those are
         Kam's sign-off). Measurement only, as with U3.
killed:  "LCA can arbitrate the 2016c deploy" — DEAD, and killed empirically not in
         principle: swapping baseline->corrected moves latent pi 5.8pp because 2016c
         descends from the NDVI ref. Do not retry LCA on any NDVI-descended model.
         "latent truth sits on C-CAP, so C-CAP is the better reference" — NOT claimed.
         Prevalence agreement is not accuracy; C-CAP hits the right TOTAL while making both
         errors (se .70 at 5-10m). Two of three sources share a strict definition and the
         latent class inherits the majority definition (Gutierrez-Velez 2024, ID 81).
files:   Scripts/phase4_qc_latent_class.py (new) · Scripts/phase4_qc_latent_class_test.py
         (new) · Scripts/phase4_qc_latent_class_adversarial.py (new) ·
         phase4/qc/latent_class_*.txt/.csv (5 pairs) · CHATLOG STATE measure: block.
next:    U1 canopy definition, now with a number attached to it (.29 vs .35 turns on it).
         Then cheapest-move #2 (simulate the stratified design's real CI). P3 unchanged and
         still gated on U1.

## 2026-08-18  U3 ANSWERED — the height staircase SURVIVES reference disagreement (it is real)
goal:    run the cheapest free instrument named in the 2026-08-18 assessment: cross P1c
         (recall-by-height) with P2 (ref agreement). Never been crossed. Local, no GPU.
did:     NEW Scripts/phase4_qc_height_by_agreement.py — recall by CHM band computed SEPARATELY
         inside each agreement partition. Ran 2016 baseline, decim 8, thresh .509,
         21,066,144 valid cells. -> phase4/qc/height_by_agreement_2016_baseline.txt/.csv
RESULT — THE STAIRCASE IS REAL:
         both_canopy (both refs agree = ref noise removed), n=5,505,444, overall recall .7374:
           0-2m .1608 · 2-5m .2010 · 5-10m .4181 · 10-15m .6220 · 15-20m .7668 ·
           20-25m .8535 · 25-30m .8971 · 30+m .9404
         THE TEST: 5-15m .5172 vs 20m+ .9049 -> spread +0.3877.
         -> the 5-15m deficit is a MODEL problem, NOT C-CAP counting lawns between yard trees.
         -> height-conditioned training (stratify-then-segment, Hamraz lit ID 86) IS the lever.
         -> the suburban visual grounding and the height curve are BOTH true; they are not
            the same finding, and the height one is not an artifact of the other.
contested partitions (no truth there -> CALL RATE, not recall):
         ccap_only n=713,884, call rate .0814. MASS SITS LOW (2-15m ~478k of 714k cells).
           C-CAP forest that is tall enough but NOT green (ndvi<.2). AMBIGUOUS between
           lawn/roof-between-yard-trees AND low-NDVI purple-leaf ornamentals — and if it is
           the latter, the model AND the NDVI ref BOTH miss them. Worth a look before P3.
         ndvi_only n=2,448,603, call rate .2036, climbing .0855 (2-5m) -> .7764 (30+m).
           Green and >=2m but not C-CAP forest = shrubs/hedges at low height. Model refuses
           8.5% of the 2-5m band — consistent with the known scrub recall .25.
decided: nothing deployed, nothing in the plan edited. This is measurement only.
files:   Scripts/phase4_qc_height_by_agreement.py (new)
         phase4/qc/height_by_agreement_2016_baseline.txt / .csv (new)
         Reports/Measurement_Validity_Assessment_2026-08-18.md (prior entry; 7 amendments
         still PENDING Kam's sign-off — none applied)
next:    ONE COMMAND, not yet run (session ended first) — the 2016c deploy comparison:
           py -3.12 Scripts/phase4_qc_height_by_agreement.py              --prob phase4/masks/edmonds_canopy_prob_2016_corrected.tif              --ccap D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc.tif              --ndvi phase4/qc/ndvi_ref_2016.tif              --thresh 0.509 --label 2016_corrected --decim 8
         Read: did the overlay lift the 5-15m bands INSIDE both-agree (real fix), or only
         in ndvi_only (it just adopted the NDVI ref's definition)? That is the 2016c
         deploy/no-deploy question in one number.
         Then the other free instruments from the assessment: miss-depth per yr on one
         recipe (U4) · Foody-2022 latent class on ccap x ndvi x model (U2) · Clark-2023
         stratified patch re-sample (U5).
gotcha:  console here is cp1252 — keep report bodies ASCII (box-drawing chars crash print()
         before the file write, so a crash means NO output file, not a partial one).

## 2026-08-18  [CONSOLIDATED] ASSESSMENT + LIT PHASE 4 — what our numbers can and cannot support
scope:   folds 2 full entries + 1 duplicate. FULL TEXT: Reports/Measurement_Validity_
         Assessment_2026-08-18.md (now git-tracked) + Admin/Literature_Tracker.xlsx.
did:     37 papers (IDs 69-105, searches 9-14) targeting the VALIDITY gap the first 8
         searches never asked about. Then an assessment ordering unknowns U1-U8 BY THE
         DECISION EACH BLOCKS, with the power math COMPUTED not gestured at.
THE FINDING: P3 at 250 pts/yr answers the question NOT in doubt and cannot answer either
         question that IS. Arbitrating C-CAP 29.5% vs NDVI-ref 37.7% (gap 8.2pp) needs
         n=510; n=250 -> +/-5.9pp = CI [27.7,39.5] COVERS BOTH. Per-band recall at 8 strata
         -> +/-17.6pp. Confirming the height effect needs only n_h=20 — and we already know it.
         [LATER OVERTURNED — see STATE result (6): that power math assumed SIMPLE RANDOM
         SAMPLING. The REAL stratified design separates the two at n=250. Sample size was
         never the constraint; interpreter fidelity is.]
         7 amendments proposed, NONE applied (Kam signs off): canopy definition FIRST ·
         free instruments before human hours · re-derive n · primary+ALTERNATE response
         design (Wickham ID 78: 77.5% -> 87.1%, 10pp from a SCORING CONVENTION) ·
         duplicate-interpreted subset designed in (ID 100/101) · 2000 feasibility block
         (Reis ID 103: 3 interpreters fully agreed on <40% of historical px) · strata
         decision before --step design (ID 72 permits any ONE, not all three).
killed:  "your recall is probably optimistic" (my own blanket claim) — WRONG as stated.
         Direction is PER REFERENCE: vs C-CAP the suburb over-count inflates the recall
         DENOMINATOR -> measured recall is PESSIMISTIC; vs the NDVI ref (shared lineage,
         and post-overlay it also supplied labels) errors CORRELATE -> OPTIMISTIC. That is
         the quantitative form of "the refs bracket truth".

## 2026-08-18  [CONSOLIDATED] 2016c CORRECTED-LABEL VERDICT — better where it can be judged, undecidable elsewhere
scope:   folds 3 full entries (verdict / uncontested-ground update / grass check).
did:     scored the corrected-label 2016 model against both references and inside the P2
         partitions. recall .6844 -> .8718 but precision .8651 -> .7296.
RESULT:  on BOTH-AGREE ground (reference noise removed) it is CLEARLY better: F1 .853 ->
         .937, both-agree recall .7613 -> .9486. The grass-rejection alarm (.912 -> .719)
         is ~73% CONTESTED (the NDVI ref calls those px canopy) and ~27% GENUINE — in
         uncontested terms the grass FP rate roughly DOUBLES (~6.8% -> ~12.7%), it does not
         quadruple as the headline implied.
decided: 2016c is a GENUINE CANDIDATE, not deployed. It adopted the NDVI reference's canopy
         DEFINITION wholesale, so its costs are (a) ~27% of a doubled grass FP rate no
         reference supports and (b) total dependence on the NDVI ref being right in the
         contested ~16%. Both are P3 questions. [Later reinforced by STATE (5b): latent
         class is INADMISSIBLE for this decision — 2016c descends from the NDVI ref.]

## 2026-08-18  [CONSOLIDATED] P1c — HEIGHT IS THE INVARIANT, and the LABEL SOURCE has the same curve
scope:   folds 4 full entries. Live form = STATE results (1) and (3).
RESULT:  recall is a monotonic function of canopy height in EVERY year: ~.15 below 5 m
         rising to .93 above 30 m; the model finds ~24 m trees and misses ~12 m trees.
         5-15 m holds 53% of ALL misses; lifting those two bands to the 20-25 m rate takes
         recall .68 -> ~.80. On the honest (full-forest) denominator the "confident miss"
         gets STRONGER, 60% -> 69%.
         AND THE DEFICIT IS INHERITED: phase3/edmonds_canopy_mask_2020.tif — the label
         source for every coarse year — has the SAME staircase and sits BELOW its own
         students at every band (.5455 vs the 2016 model's .6821). Improving that one mask
         lifts every coarse year at once.
killed:  "misses are confident/structural everywhere" — 2016-only; see STATE (7).

## 2026-08-18  [CONSOLIDATED] P2 — reference disagreement is 15-17%, every year, replicated x4
scope:   folds 3 full entries. Live form = STATE, and the instrument = phase4_ref_agreement.py.
RESULT:  38.7% of the apparent "miss" is UNMEASURABLE — it sits where the two references
         disagree, so no truth exists there. Honest recall on measurable ground .6564 ->
         .7378. Disagreement is 15-17% on EVERY year tested (x4), and the NDVI reference is
         systematically MORE LIBERAL than C-CAP. This partition is the basis of the standing
         rule: NEVER score contested ground.
also:    unattended TRAIN QUEUE built (delivered 3/3); CUDA confirmed working locally
         (torch 2.13.0+cu126, Quadro T2000 4 GB) — but training stays on Colab (rule).

## 2026-08-18  [CONSOLIDATED] P1 — nine years scored on ONE honest instrument
scope:   folds 6 full entries (Colab runs, per-year scoring, the queue).
RESULT:  9 years span IoU .49-.76 / AUROC .938-.954 while honest recall stays .51-.78 with
         NO correlation -> MODEL STRENGTH DOES NOT MOVE THE NUMBER (STATE result 4). The
         gap is SYSTEMATIC, not model quality: the best model still under-predicts ~34%.
         2013 miss-depth moved 9.3% -> 50% under a changed denominator (later resolved as a
         RECIPE artefact, STATE result 7b).
killed:  MY PREDICTION on 2017. I said TWICE "expect LOW recall" from its max-prob .575
         ceiling. WRONG — 2017 has the HIGHEST recall in the series (.7784). A COMPRESSED
         probability range does not imply poor RANKING; the deployed .4759 sits inside that
         band and separates fine. The real problem is THRESHOLD FRAGILITY, not weakness
         (thresh .2000 -> recall 1.0000 / precision .2868 = calls the whole city canopy).
killed:  my claim "you skipped stage 1 (2022n)" — WRONG, logs prove 2022n ran 01:29-02:24.
killed:  "git pull to update Colab" — WRONG, said twice. `git remote -v` is EMPTY. The
         working tree IS G:\My Drive\treedata; the git DB is D:\edmonds-pipeline\treedata.git
         (local only). GOOGLE DRIVE is the sync path to Colab, not git. Verify in Colab with
         `!grep -c 2022n /content/drive/MyDrive/treedata/Scripts/phase4_p1_colab_run.py`.

## 2026-08-17  [CONSOLIDATED] measurement overhaul OPENED; QC instruments hardened
scope:   folds 6 full entries (audit, scorer fixes, Colab driver, logging, doc cleanup).
why:     Kam — "became too reliant on AI judgement"; wants defensible numbers, better tests
         and visuals. -> the 4-phase plan in honest-measurement-overhaul.md.
did:     3 SILENT QC failures found and fixed; scorers now FAIL LOUD; provenance mandatory;
         QC CSVs carry live/run_tag so superseded rows cannot be quoted by accident;
         pipeline_log stamps version + code sha + command so logs self-identify;
         run_registry backfilled (+7 rows); CLAUDE.md + buildtracker de-staled.
killed:  "can I trust forest_miss?" -> NO as it stood: a HIDDEN --stable-with denominator
         made 2016's conf% an outlier. Denominators are now printed in every report.
killed:  nothing else — Method_Pipeline hyperparameters were verified line-by-line against
         phase4seg/config.py (LR 5e-5, epochs 20/30, batch 10, tile 512, stride 512,
         neg-rate .15, MIN_CANOPY_PATCH 3.0 m2) and were already CONSISTENT.

════════ ARCHIVE (1-liners — full text in `_archive/CHATLOG_2026-06-29_to_2026-07-07.md`) ════════

Compacted 2026-08-17 and again 2026-08-18 per this file's SPACE RULE 4 (newest ~6 entries
stay full). Nothing is lost, but WHERE the full text lives now depends on the date:

  * entries up to 2026-07-07  -> verbatim in `_archive/CHATLOG_2026-06-29_to_2026-07-07.md`
  * entries 2026-07-08 onward -> GIT HISTORY ONLY (`git show <sha>:Scripts/CHATLOG.md`).
    The 2026-08-18 pass folded 31 full entries into the six [CONSOLIDATED] blocks above
    and the five newest 1-liners below; the pre-compaction file is the parent of the
    commit titled "compact the LOG per the file's own space rules".

A strict 1-liner was judged TOO STRICT for the 2026-08 measurement campaign: those entries
carry numbers and `killed:` lines, and `killed:` is the content with no other home — STATE
holds the findings, but nothing else records which hypotheses are already dead. So every
`killed:` from the folded entries was carried up into the [CONSOLIDATED] blocks verbatim in
substance, and only the narrative around them was compressed.

- 2026-07-07 v048 — --force-citywide crashed on FINE years: fixed-256 candidate stride → 119,770 candidates (~2h scan). Fix = stride ADAPTS to ortho size (CITYWIDE_CANDIDATE_TARGET=8000, floor 256); coarse unchanged. Decided: bound the SCAN, not the budget.
- 2026-07-07 cross-sensor forest-miss autopsy FIRST CUT (2000/2002/2013, RGB-only, pre-force-citywide) — scored vs C-CAP-2016 forest ∩ C-CAP-2021 stable-forest. Superseded by the uniform-recipe re-run. → phase4/qc/forest_miss_sensor_compare.*
- 2026-07-07 v047 — --infer-batch [32] + inference AMP (fits a 24GB L4, ~2-3x cheaper), --force-citywide (recipe keyed on POOL not GSD tier), --run-tag (runs save instead of overwrite).
- 2026-07-07 BUILT phase4_qc_forest_misses.py — under-prediction autopsy over C-CAP forest px. Decided: TEACH deciduous (stage positive sites at top-FN stands), do NOT lower the threshold.
- 2026-07-07 C-CAP 2016+2021 hi-res 1m ACQUIRED (EVAL-ONLY) → FIRST non-circular numbers. C-CAP is independent of the model's CHM axis → the arbiter for variant ranking. Ranking itself stayed Colab-gated (only the 2016 prob raster existed).
- 2026-07-07 BUILT phase4_qc_indep.py — reference-agnostic independent scorer. Decided: primary canopy class = forest + forested-wetland.
- 2026-07-07 DECISION (multi-agent review): STOP grass iteration; do NOT build the phase3 base mirror yet; ship aux-height v046 as provisional; flicker-gate it → NEW phase4_qc_flicker.py.
- 2026-07-07 aux-height 2016 on v046: mechanism WORKS but WEAK — training stable, grass-rejection only +2pp. Expected: no base pretraining, coarse 2016 only.
- 2026-07-06 aux-height ablation: RGB-only baseline clean, --aux-height run CRASHED → v046 two bugfixes (RGB upcast to float32 corrupted the uint8-assuming colour augs → divergence; 4th forward site not tuple-unpacked).
- 2026-07-06 v045 aux-height REFRAME coded — teach height, don't feed it: RGB-only input + a 2nd head predicting CHM height (masked-L1), flag-gated OFF. Key realization: sem_best_2020.pt is already 3-ch RGB → phase4 fine-tunes from it directly, phase3 untouched.
- 2026-07-06 GIT ADOPTED — private local repo (tree = the Drive folder, DB on D:), version_script.py/.versions/ retired to a frozen git-ignored archive, pre-git history imported as backdated commits. Killed: clean-start-no-import.
- 2026-07-06 CORRECTED-LABEL RESULT (v044, full 2016): honest recall .60→.85 but the grass-rejection guard TRIPPED (.98→.84) — the exact failure CHM was added to fix. Also circular: labels and yardstick were both NDVI+CHM.
- 2026-07-06 corrected labels APPLIED (v043) but inference OOM'd at batch=160 → v044 hardening (gc+empty_cache before inference, OOM-resilient batch halving).
- 2026-07-06 v042 corrected-label run REUSED 685 stale tiles → overlay never reached training. Fix v043: --add-canopy-mask joins the tile signature. Lesson: the overlay is baked at TILE time → must retile.
- 2026-07-06 SOURCES OF TRUTH CENTRALIZED — 5 HANDOFF_*.md retired to _archive/handoffs/, treedata/README.md front door added, one-fact-one-home rule adopted.
- 2026-07-05 corrected labels from NIR+CHM (v042 --add-canopy-mask) — invert the QC instrument to LABEL the misses (ADD-ONLY). Root cause of under-prediction: labels teach CONIFER only. Killed: the 2015-flagship substitution.
- 2026-07-05 HONEST RECALL INSTRUMENT (phase4_qc_ndvi/_score/_site) — 2016 recall is .60, not the circular .94. Under-prediction is STRUCTURAL (deciduous/OOD), NOT a threshold artifact (the sweep refutes it). This is the finding the whole workstream rests on.
- 2026-07-05 marsh deciduous POSITIVE SITE staged (make_positive_site.py) — labels auto-derived from the 2020 mask, not hand-drawn (trees stable 2015-2020).
- 2026-07-05 under-prediction diagnosis → 3 causes; v041 --infer-thresh (explicit op-threshold override) as the interim lever. Killed: retrain-to-lift-recall (re-adds grass FP).
- 2026-07-05 v039 VALIDATED — 2016 RGB+CHM BEATS the RGB baseline on held-out test (IoU .7725 vs .7245). CHM helps once the sampler is honest.
- 2026-07-05 research (4 agents) + code audit → v039 Round 1, 8 fixes (sampler, FREEZE_ENCODER_BN default, phase-B resumes from BEST, pooled global IoU, op-thresh metrics, IGNORE aug borders, leakage caveat).
- 2026-07-05 v038 validation: the metric fix WORKS (stable training) but the chm model still underperformed on that pool → pointed at the sampler.
- 2026-07-05 ROOT CAUSE FOUND — the 2016 "collapse" was a val_iou@0.5 METRIC ARTIFACT, not a training failure. v038 = coarse early-stop metric val_iou → val_iou_bt. KILLED every training-stability hypothesis (class-balance / chm / dice / BN / LR).
- 2026-07-05 run E: BN freeze improved early dynamics but did not stop the val_iou@.5 cliff (kept anyway, cheap) → v037.
- 2026-07-05 run D: pure BCE STILL cliffed → dice term EXONERATED, BN-drift suspected → v036 --freeze-encoder-bn.
- 2026-07-05 IDEMPOTENT TILING (v035) — a complete tile set matching the sampling signature is reused; stops paying a 20-min re-tile after a lost Colab runtime. --force-retile overrides.
- 2026-07-05 run C: softened pool did NOT fix the cliff → class-balance killed as the cause (3 runs).
- 2026-07-04 round-1 (runs A+B): NOT chm, NOT pos_weight. Killed: raising pos_weight as the fix.
- 2026-07-04 fable-takeover — handoff claims verified against code; v031 flags (--coarse-pos-weight-max, --lr-phase-a); round-1 = 2 train-only single-variable runs on existing tiles.
- 2026-07-05 chm-2016 train COLLAPSE — first real test of the CHM channel. Decided: the CHM raster itself is CORRECT (crowns/ground clean, height p50 6.7m) → the fault is in training, not the data. Handed to Fable.
- 2026-07-04 CHM HEIGHT CHANNEL (v030) to kill grass FPs (grass = 64% of all FPs). Root cause of the old channel: struct = hillshade(fr) - hillshade(be) is TEXTURE, not height. Decided: 3DEP HAG > DSM-DTM > county services → fetch_build_chm.py.
- 2026-07-03c yr-2000 struct-first valid test — and the instrument is BIASED AGAINST the channel (labels = the 2020 mask reprojected). First clear statement of the circularity problem.
- 2026-07-03 struct channel + --hs-dropout 0.25 (v027) — structure = clip(fr-be+127) cancels terrain shading, AUC .732 vs raw fr .646; HS_SOURCE stamped on tiles → no flag/tile/ckpt mismatch possible.
- 2026-07-02 CHATLOG.md created — caveman-full entry style, STATE+LOG split, rolling compaction (the rule this ARCHIVE section implements).
- 2026-06-29 LIDAR hillshade as a uniform 4th channel (v025) + RGBI tiling crash fixed. Killed: the per-year NIR 4th band (v023) — variable channels per year too messy. Temporal caveat: hillshade is ~2016 → weak for 2000-2012.
- 2026-08-16 3-agent sweep of every published City canopy report -> the headline 32.4% TRACED to a PlanIT Geo modelling assumption; Reports/ dossier + brief built. Killed: "35% by 2045" (garble — the record says 2036), "PlanIT Geo has no Edmonds engagement" (the agent searched retired iqm2; 2026 packets are on edmondswa.primegov.com), "34.6% is a 2023 figure" (it is 2020). GAP: the full 2024 PlanIT Geo UTC assessment behind 32.4% is NOT PUBLISHED anywhere.
- 2026-07-10 3-agent architecture review -> TWO-STREAM (one shared RGB backbone, instance + semantic heads), instance-on-fine FIRST, labels per domain. Killed: "instance-first is a dead-end" (rejected — a sequencing point, not a veto); "one model spans all years via multi-scale aug" (DEMOTED to half-true — spans 8x GSD, NOT the King contractor change / NAIP / Snoh); "hand-trace deciduous FOREST stands" (WRONG target — the miss is suburban/ornamental, 8/8 inspected stands).
- 2026-07-10 STRATEGIC RESET -> one scale-robust model, labels-first (plan cozy-skipping-jellyfish.md, later superseded by the two-stream review above).
- 2026-07-08 Phase-4 engine MODULARIZED -> phase4seg/ package (config/common/labels/tiling/core[torch]/postproc/cli) + a ~97-line phase4_semantic_finetune.py shim preserving `%run ... --args`. Behaviour-preserving, AST-verified (89/89 defs, 106/106 consts). POC notebook cleaned, experiments/ split out.
- 2026-07-08 full-codebase audit (6 subagents) + declutter + 2 output-safe fixes -> _archive/audit_2026-07-08/ (NOT current).
