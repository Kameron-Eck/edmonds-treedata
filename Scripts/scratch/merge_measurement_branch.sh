#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Merge the 2026-08-18 measurement branch into main.
#
#  WHY A SCRIPT: Claude Code ran in an isolated git worktree, so it could not
#  perform this merge itself — a worktree-isolated session is blocked from
#  git operations on the shared checkout. This encodes the steps it would have
#  run, including the one non-obvious part (step 2).
#
#  RUN THIS ON WINDOWS, IN GIT BASH, FROM ANYWHERE.
#  PAUSE GOOGLE DRIVE SYNC FIRST — this writes the working tree (CLAUDE.md
#  rule 1). Resume it after, and let Scripts/ finish uploading before using
#  Colab.
#
#  Nothing here is destructive: step 2 MOVES files aside rather than deleting
#  them, and the merge itself is refused rather than forced if anything is off.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="G:/My Drive/treedata"
BRANCH="worktree-latent-class-u2"
STASH_DIR="${TMPDIR:-/tmp}/edmonds_untracked_$(date +%Y%m%d_%H%M%S)"

cd "$REPO"

echo "== 1. where we are =="
git rev-parse --abbrev-ref HEAD
git log --oneline -1
echo
echo "commits waiting on $BRANCH:"
git log --oneline "main..$BRANCH" | wc -l
echo

echo "== 2. move untracked outputs aside =="
# Claude's QC scripts wrote their outputs into THIS tree (BASE is hardcoded to
# the Drive path), and the same files are also committed on the branch. Git
# refuses to merge over untracked files, so they must go somewhere first.
# They are byte-identical to the committed copies, so this is recoverable
# either way — but we move rather than delete, on principle.
mapfile -t UNTRACKED < <(git ls-files --others --exclude-standard Scripts phase4/qc || true)
if [ ${#UNTRACKED[@]} -eq 0 ]; then
  echo "   none — nothing to move."
else
  printf '   %s\n' "${UNTRACKED[@]}"
  echo
  echo "   ^ REVIEW THIS LIST. If anything there is NOT a Claude QC output"
  echo "     (another session's work in flight), press Ctrl-C now."
  read -r -p "   move these ${#UNTRACKED[@]} files to $STASH_DIR and continue? [y/N] " ok
  [ "$ok" = "y" ] || { echo "aborted."; exit 1; }
  mkdir -p "$STASH_DIR"
  for f in "${UNTRACKED[@]}"; do
    mkdir -p "$STASH_DIR/$(dirname "$f")"
    mv "$f" "$STASH_DIR/$f"
  done
  echo "   moved. recover with: cp -r '$STASH_DIR'/* '$REPO'/"
fi
echo

echo "== 3. merge =="
git merge --no-ff "$BRANCH" -m "merge: 2026-08-18 measurement, metadata and git-hygiene work"
echo

echo "== 4. verify the engine change actually landed =="
grep -q "def tier_for" Scripts/phase4seg/config.py \
  && echo "   OK  tier_for() present" || { echo "   FAIL tier_for() missing"; exit 1; }
grep -q '"gsd_cm": 15.4' Scripts/phase4seg/config.py \
  && echo "   OK  true GSD present (Snohomish 15.4 cm)" || { echo "   FAIL gsd_cm not corrected"; exit 1; }
PYTHONUTF8=1 py -3.12 -m py_compile Scripts/phase4seg/config.py Scripts/phase4seg/cli.py \
  && echo "   OK  engine compiles"
echo

echo "== DONE =="
echo "Next:"
echo "  1. RESUME Google Drive sync and wait for Scripts/ to finish uploading."
echo "  2. In Colab, confirm the sync landed:"
echo "       !grep -c tier_for /content/drive/MyDrive/treedata/Scripts/phase4seg/config.py"
echo "     Must print 2 or more. If it prints 0, Drive has not synced — do NOT"
echo "     start the queue, you would train against the old config."
echo "  3. Smoke gate, then the queue (see CHATLOG STATE)."
