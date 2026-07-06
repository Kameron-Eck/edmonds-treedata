"""
version_script.py — Script versioner for the Edmonds pipeline
==============================================================
Call this BEFORE editing any phase script. It reads the current
version from Drive and writes a numbered backup to .versions/.

USAGE (from Claude Code terminal, local machine):
    python version_script.py --script /path/to/phase4_label_review.py --tag "before serve rewrite"
    python version_script.py --script /path/to/phase4_label_review.py --tag "fix crop padding bug"

REVERT:
    python version_script.py --revert --script /path/to/phase4_label_review.py --version 3

LIST:
    python version_script.py --list --script /path/to/phase4_label_review.py

The .versions/ directory sits next to the Scripts/ folder:
    treedata/Scripts/.versions/{script_stem}/v{NNN}_{YYYY-MM-DD}_{tag}.py

Version numbers are sequential integers, zero-padded to 3 digits (v001, v002 …).
Tags are sanitised: spaces → underscores, special chars stripped.
"""

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitise_tag(tag: str) -> str:
    """Lowercase, spaces→underscores, keep only [a-z0-9_-]."""
    tag = tag.lower().strip().replace(" ", "_")
    tag = re.sub(r"[^a-z0-9_\-]", "", tag)
    return tag[:60]  # cap length so filenames stay sane


def _versions_dir(script_path: Path) -> Path:
    """Return .versions/{stem}/ next to the Scripts directory."""
    scripts_dir = script_path.parent
    return scripts_dir / ".versions" / script_path.stem


def _next_version(versions_dir: Path) -> int:
    """Scan existing backups and return the next sequential number."""
    versions_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(versions_dir.glob("v*.py"))
    if not existing:
        return 1
    # Extract the integer from the leading vNNN prefix
    nums = []
    for p in existing:
        m = re.match(r"v(\d+)_", p.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def _backup_name(n: int, tag: str) -> str:
    today = date.today().isoformat()  # YYYY-MM-DD
    return f"v{n:03d}_{today}_{tag}.py"


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_save(script_path: Path, tag: str) -> Path:
    """Save the current script as a new numbered version. Returns backup path."""
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    versions_dir = _versions_dir(script_path)
    versions_dir.mkdir(parents=True, exist_ok=True)

    n = _next_version(versions_dir)
    clean_tag = _sanitise_tag(tag) if tag else "no_tag"
    backup = versions_dir / _backup_name(n, clean_tag)

    shutil.copy2(script_path, backup)
    print(f"  ✓ v{n:03d}  {script_path.name}  →  {backup}")
    return backup


def cmd_list(script_path: Path):
    """Print all saved versions for a script."""
    versions_dir = _versions_dir(script_path)
    if not versions_dir.exists():
        print(f"  No versions found for {script_path.name}")
        return
    versions = sorted(versions_dir.glob("v*.py"))
    if not versions:
        print(f"  No versions found for {script_path.name}")
        return
    print(f"\n  Versions for {script_path.name}:")
    print(f"  {'#':<6}  {'Date':<12}  {'Tag'}")
    print(f"  {'-'*55}")
    for v in versions:
        m = re.match(r"v(\d+)_(\d{4}-\d{2}-\d{2})_(.*?)\.py$", v.name)
        if m:
            num, dt, tag = m.group(1), m.group(2), m.group(3).replace("_", " ")
            print(f"  v{num}    {dt}    {tag}")
        else:
            print(f"  {v.name}")
    print()


def cmd_revert(script_path: Path, version: int):
    """Overwrite the live script with a saved version (after backing up current)."""
    versions_dir = _versions_dir(script_path)
    # Find the requested version
    candidates = sorted(versions_dir.glob(f"v{version:03d}_*.py"))
    if not candidates:
        raise FileNotFoundError(
            f"Version v{version:03d} not found under {versions_dir}\n"
            f"Run --list to see available versions."
        )
    source = candidates[0]

    # Save the current live script first (so revert itself is reversible)
    print(f"  Saving current version before revert …")
    cmd_save(script_path, tag=f"pre_revert_to_v{version:03d}")

    # Overwrite
    shutil.copy2(source, script_path)
    print(f"  ✓ Reverted {script_path.name} to {source.name}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Script versioner — save/list/revert phase scripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--script", required=True,
                   help="Path to the script to version")
    p.add_argument("--tag", default="",
                   help="Short description of the change (for --save, default action)")
    p.add_argument("--list", action="store_true",
                   help="List all saved versions for this script")
    p.add_argument("--revert", action="store_true",
                   help="Revert the script to a saved version (requires --version)")
    p.add_argument("--version", type=int, default=None,
                   help="Version number to revert to (used with --revert)")

    args = p.parse_args()
    script_path = Path(args.script).expanduser().resolve()

    if args.list:
        cmd_list(script_path)
    elif args.revert:
        if args.version is None:
            p.error("--revert requires --version N")
        cmd_revert(script_path, args.version)
    else:
        # Default action: save a new version
        if not args.tag:
            p.error("--tag is required when saving a version")
        cmd_save(script_path, args.tag)


if __name__ == "__main__":
    main()
