#!/usr/bin/env python3
"""STAGED, NOT INSTALLED. The PreToolUse guard for literature routes outside litkb (design §9.1).

Design §9.1 is explicit about the order: "**After P8's gate passes.** Before the MCP tools exist, a
blocking hook would leave agents no route to literature at all." So this hook WARNS and never
blocks: it emits `additionalContext` and exits 0, which lets the tool run and puts one sentence in
front of the agent. It is not registered in any settings file — installation is Kam's, after the
gate, and the instructions are in `Reports/LITKB_P8_ACCESS_2026-09-15.md`.

What it watches, and why each one:

  * the paper-search MCP tools' download / read routes — the habit §9.1 was written against: an
    agent that has read the rule still reaches for the tool it already knows, and the database never
    hears of the paper;
  * `Read` of a PDF under the literature root — a paper read straight off disk leaves no use, no
    quote and no record that the project relied on it;
  * a shell command naming `aa_fetch` or Sci-Hub — the acquisition routes that now belong to
    `litkb.acquire`, whose attempts log is the only place a refused fetch is remembered.

It fires only when the working directory has no `.litkb-workstream`, because inside a workstream
those routes are how `litkb.acquire` itself reaches the network.

Guardrails, not enforcement: the database's checks (§4.6, §4.7) are the enforcement, and they stay
the enforcement. This hook exists because a rule nobody is reminded of is a rule that is forgotten.

Contract (code.claude.com/docs/en/hooks): stdin is one JSON object with `tool_name`, `tool_input`
and `cwd`; stdout is a JSON object whose `hookSpecificOutput.additionalContext` is shown to the
agent. `additionalContext` MUST be nested inside `hookSpecificOutput` — at the top level it is
silently ignored. No `permissionDecision` key is emitted, so the normal permission flow is
untouched. Exit 0 always: a hook that crashes on an unexpected payload must not become a tax on
every tool call.
"""
import json
import os
import re
import sys
from pathlib import Path

TOKEN_FILE = ".litkb-workstream"
SKILL = "the `literature` skill (.claude/skills/literature/SKILL.md)"

#: paper-search's fetching and reading routes. Its SEARCH tools are deliberately absent: looking to
#: see what exists is not the same as pulling a paper into the project, and warning on a search
#: would train the agent to ignore the warning.
PAPER_SEARCH = re.compile(r"^mcp__paper-search-mcp__(download|read)_", re.I)
SHELL_ROUTE = re.compile(r"aa_fetch|sci-?hub|annas-archive", re.I)
LITERATURE_ROOT = os.environ.get("LITKB_LITERATURE_ROOT", r"D:\edmonds-pipeline\Literture")


def reason(tool_name, tool_input):
    """-> why this call is a literature route outside litkb, or None."""
    tool_name = tool_name or ""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if PAPER_SEARCH.match(tool_name):
        return (f"`{tool_name}` fetches or reads a paper outside the knowledge base, so nothing "
                "records that the project relied on it")
    if tool_name in ("Read", "NotebookRead"):
        p = str(tool_input.get("file_path") or "")
        if p.lower().endswith(".pdf") and _under(p, LITERATURE_ROOT):
            return (f"`{Path(p).name}` is being read straight off disk: no work, no use and no "
                    "quote will exist for it")
    if tool_name in ("Bash", "PowerShell"):
        cmd = str(tool_input.get("command") or "")
        if SHELL_ROUTE.search(cmd):
            return ("this command reaches an acquisition route (aa_fetch / Sci-Hub / the archive) "
                    "directly; `litkb acquire` is the route that logs the attempt")
    return None


def _under(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def has_workstream(cwd):
    """True if `cwd` or any parent up to the drive holds a token file. A worktree root is where the
    file lives, and a tool call is usually made from somewhere below it."""
    try:
        here = Path(cwd or os.getcwd()).resolve()
    except OSError:
        return False
    for d in (here, *here.parents):
        if (d / TOKEN_FILE).exists():
            return True
    return False


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    why = reason(event.get("tool_name"), event.get("tool_input"))
    if not why or has_workstream(event.get("cwd")):
        return 0
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            f"litkb: {why}. Any literature the project relies on is admitted, acquired and cited "
            f"through the literature knowledge base — open a workstream and use the litkb MCP "
            f"tools. Procedure: {SKILL}. This call is not blocked; ad-hoc reading that supports no "
            "claim is outside the rule (decisions.yaml litkb-p0-foundation §15.17).")}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
