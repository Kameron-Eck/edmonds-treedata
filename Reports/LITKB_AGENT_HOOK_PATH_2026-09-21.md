# The subagent credential-guard hook blocks instead of warning — fix for Kam (2026-09-21)

**Where:** `.claude/agents/review-writer.md` and `.claude/agents/librarian.md`, frontmatter
`hooks.PreToolUse[0].hooks[0].command`. Editing agent hook frontmatter is classifier-refused for
Claude (self-modification), so this is a diff for Kam to apply.

**Mechanism (measured, not inferred).** The command is
`py -3.12 ${CLAUDE_PROJECT_DIR}/.claude/hooks/litkb_guard.py`. `CLAUDE_PROJECT_DIR` is the
directory the session OPENED in — `Scripts\` for every session (CLAUDE.md §2.3) — while `.claude/`
lives at the git root one level up. `py` handed a missing script prints "can't open file" and
exits **2**, and exit 2 is the one code the hook protocol reads as BLOCK. Measured from `Scripts\`:
missing-file exit=2; the real guard exit=0. So a guard written to warn-only has silently blocked
every Read/Grep/Glob of both agents from `Scripts\`. The S2 review-writer could not read
`docs/LITKB_REVIEW_GRAMMAR.md` and its first draft failed `review-check` at line 1 (no header).

**Fix — locate the guard, fail open.** Replace the `command:` line in BOTH files with:

```yaml
          command: "py -3.12 -c \"import os,runpy;d=os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd();c=[os.path.join(x,'.claude','hooks','litkb_guard.py') for x in (d,os.path.dirname(d),os.path.dirname(os.path.dirname(d)))];p=next((x for x in c if os.path.isfile(x)),None);p and runpy.run_path(p,run_name='__main__')\""
```

Tested with a credential-path probe on stdin from four `CLAUDE_PROJECT_DIR` values —
`treedata\Scripts`, `treedata`, a worktree's `Scripts`, and `C:\Windows` (no guard anywhere):
the first three emit the guard's `additionalContext` warning and exit 0; the fourth runs
nothing and exits 0. Fail-open is the guard's own contract (its docstring: "WARNS and never
blocks"; the deny block in settings.json is the enforcement).

Suggested comment above it (so the next reader knows why it is a locator):

```
# THE PATH IS LOCATED, NOT ASSUMED (2026-09-21, S2): `${CLAUDE_PROJECT_DIR}` is the directory
# the session OPENED in (`Scripts\`), `.claude/` is one level up, and `py` on a missing script
# exits 2 = BLOCK. The one-liner walks up two levels and, finding no guard, exits 0.
```

Until applied: any dispatch of `review-writer` or `librarian` from a `Scripts\` session must carry
the documents it needs inline (S2 did this with the grammar).
