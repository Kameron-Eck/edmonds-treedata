"""
harvest_results.py — idempotent Drive→repo copy of tracked MEASURED text (overhaul P7).

Since 2026-08-20 the git repo lives on D: and Drive is the data lake, so measured
text (phase4/qc findings, Reports) is PRODUCED on Drive but VERSIONED in the repo.
This script is the bridge: it copies every tracked-pattern file whose content
differs, prints exactly what changed, and (with --commit) stages ONLY those paths
and commits — never `git add -A` (CLAUDE.md rule 1b).

Usage (local Windows, from anywhere):
    py -3.12 harvest_results.py            # copy + report, no git
    py -3.12 harvest_results.py --commit   # copy + explicit-path commit
    py -3.12 harvest_results.py --dry-run  # report only, copy nothing

Session-end contract (rule 9d): run this before the end-of-session commit.
"""
from phase4seg.names import clean_argv
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE          # data plane
REPO = Path(__file__).resolve().parents[2]                           # code plane

# (drive-relative dir, repo-relative dir, patterns) — mirrors the .gitignore whitelist.
HARVEST = [
    ("phase4/qc", "phase4/qc", ("*.txt", "*.csv", "*.json")),
    ("Reports",   "Reports",   ("*.md", "*.csv")),
]


def _sha(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--on-main", action="store_true",
                    help="P11.5: commits normally land on a work branch; pass this only "
                         "when Kam has said the harvest may go straight onto main.")
    args = ap.parse_args(clean_argv())

    if not (REPO / ".git").exists():
        sys.exit(f"not a git repo: {REPO} (this script must live in the repo)")
    if not BASE.exists():
        sys.exit(f"data plane not mounted: {BASE}")

    changed = []
    for src_rel, dst_rel, patterns in HARVEST:
        src_dir, dst_dir = BASE / src_rel, REPO / dst_rel
        if not src_dir.exists():
            print(f"  (skip {src_rel} — not on the data plane)")
            continue
        for pat in patterns:
            for src in sorted(src_dir.glob(pat)):
                dst = dst_dir / src.name
                if dst.exists() and dst.stat().st_size == src.stat().st_size \
                        and _sha(dst) == _sha(src):
                    continue
                state = "update" if dst.exists() else "NEW"
                print(f"  {state:>6}  {dst_rel}/{src.name}")
                if not args.dry_run:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                changed.append(str(Path(dst_rel) / src.name).replace("\\", "/"))

    if not changed:
        print("harvest: repo already current — nothing to copy.")
        return
    print(f"harvest: {len(changed)} file(s) {'would change' if args.dry_run else 'copied'}.")
    if args.commit and not args.dry_run:
        branch = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        if branch == "main" and not args.on_main:
            sys.exit("harvest: checked out on main — P11.5 says main never moves without Kam. "
                     "Switch to a work branch (git checkout -b work/<slug> main) and re-run, "
                     "or pass --on-main when Kam has approved it. Files were copied, not committed.")
        subprocess.run(["git", "-C", str(REPO), "add", "--", *changed], check=True)
        subprocess.run(["git", "-C", str(REPO), "commit",
                        "-m", f"harvest: measured text ({len(changed)} files)"],
                       check=True)
        print("harvest: committed (explicit paths only).")
    elif not args.dry_run:
        print("harvest: not committed — stage with:")
        print("  git add -- " + " ".join(changed[:5])
              + (f" … (+{len(changed)-5} more)" if len(changed) > 5 else ""))


if __name__ == "__main__":
    main()
