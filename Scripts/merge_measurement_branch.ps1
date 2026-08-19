# ─────────────────────────────────────────────────────────────────────────────
#  Merge the 2026-08-18 measurement branch into main.        (PowerShell 5.1)
#
#  Use this one, not the .sh — in PowerShell, "bash" resolves to WSL, which is
#  not installed on this machine. (The .sh still works if invoked explicitly
#  through Git Bash: & "C:\Program Files\Git\bin\bash.exe" <path>.)
#
#  RUN FROM POWERSHELL, from anywhere.
#  PAUSE GOOGLE DRIVE SYNC FIRST — this writes the working tree (CLAUDE.md
#  rule 1). Resume after, and let Scripts/ finish uploading before Colab.
#
#  Nothing here is destructive: untracked files are MOVED aside, not deleted,
#  and you are shown the list and asked before anything happens.
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = 'Stop'
$Repo   = 'G:\My Drive\treedata'
$Branch = 'worktree-latent-class-u2'
$Stash  = Join-Path $env:TEMP ("edmonds_untracked_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))

Set-Location -LiteralPath $Repo

Write-Host "== 1. where we are ==" -ForegroundColor Cyan
git rev-parse --abbrev-ref HEAD
git log --oneline -1
$pending = @(git log --oneline "main..$Branch")
Write-Host ("commits waiting on {0}: {1}" -f $Branch, $pending.Count)
Write-Host ""

Write-Host "== 2. move untracked outputs aside ==" -ForegroundColor Cyan
# Claude's QC scripts wrote outputs into THIS tree (BASE is hardcoded to the
# Drive path) and the same files are committed on the branch. Git refuses to
# merge over untracked files, so they must move first. They are byte-identical
# to the committed copies, but we move rather than delete on principle.
$untracked = @(git ls-files --others --exclude-standard Scripts phase4/qc)
if ($untracked.Count -eq 0) {
    Write-Host "   none - nothing to move."
} else {
    $untracked | ForEach-Object { Write-Host "   $_" }
    Write-Host ""
    Write-Host "   ^ REVIEW THIS LIST. If anything is NOT a Claude QC output" -ForegroundColor Yellow
    Write-Host "     (i.e. another session's work in flight), answer N." -ForegroundColor Yellow
    $ok = Read-Host "   move these $($untracked.Count) files to $Stash and continue? [y/N]"
    if ($ok -ne 'y') { Write-Host "aborted."; exit 1 }
    foreach ($f in $untracked) {
        $dest = Join-Path $Stash $f
        $dir  = Split-Path -Parent $dest
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Move-Item -LiteralPath $f -Destination $dest -Force
    }
    Write-Host "   moved. recover with:  Copy-Item -Recurse '$Stash\*' '$Repo'"
}
Write-Host ""

Write-Host "== 3. merge ==" -ForegroundColor Cyan
git merge --no-ff $Branch -m "merge: 2026-08-18 measurement, metadata and git-hygiene work"
if (-not $?) { Write-Host "MERGE FAILED - resolve, then re-run from step 3." -ForegroundColor Red; exit 1 }
Write-Host ""

Write-Host "== 4. verify the engine change landed ==" -ForegroundColor Cyan
$cfg = Get-Content 'Scripts\phase4seg\config.py' -Raw
if ($cfg -match 'def tier_for')      { Write-Host "   OK  tier_for() present" }
                                else { Write-Host "   FAIL tier_for() missing" -ForegroundColor Red; exit 1 }
if ($cfg -match '"gsd_cm": 15\.4')   { Write-Host "   OK  true GSD present (Snohomish 15.4 cm)" }
                                else { Write-Host "   FAIL gsd_cm not corrected" -ForegroundColor Red; exit 1 }
$env:PYTHONUTF8 = '1'
py -3.12 -m py_compile Scripts\phase4seg\config.py Scripts\phase4seg\cli.py
if ($?) { Write-Host "   OK  engine compiles" } else { Write-Host "   FAIL engine does not compile" -ForegroundColor Red; exit 1 }
Write-Host ""

Write-Host "== DONE ==" -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1. RESUME Google Drive sync; wait for Scripts/ to finish uploading."
Write-Host "  2. In Colab, confirm the sync landed:"
Write-Host "       !grep -c tier_for /content/drive/MyDrive/treedata/Scripts/phase4seg/config.py"
Write-Host "     Must print 2 or more. If 0, Drive has NOT synced - do not start"
Write-Host "     the queue, you would train against the old config."
Write-Host "  3. Smoke gate:  %run phase4_semantic_finetune.py --year 2000 --step tile"
Write-Host "  4. Queue:       !python phase4_train_queue.py --infer-batch 32"
