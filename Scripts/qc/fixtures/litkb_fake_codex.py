r"""A stand-in for `codex exec`, for the tests of the Codex review stage. NEVER a reviewer.

    py -3.12 qc/fixtures/litkb_fake_codex.py exec -s read-only --skip-git-repo-check \
        -C <dir> --output-schema <schema> --json -o <out> -

It accepts the argv tail `qc/instruments/litkb_codex_review.py::_launch_argv` builds, reads the
prompt from stdin as BYTES, writes a report to the `-o` path and prints a JSONL event stream to
stdout -- the same four things the real command does, and nothing else. It is here rather than in
the test file because the wrapper launches it as a SUBPROCESS: a fake defined inside the test
module could not be, and a wrapper tested with its launcher monkeypatched would have its launcher
untested, which is the half most likely to be wrong.

WHAT IT PROVES ABOUT THE PROMPT. It writes `sha256` of the bytes it received on stdin into the
report's `reason` of its first row (`stdin_sha256=<hex>`), so a Windows-side test can compare that
to the prompt file's own digest and measure that nothing between them re-encoded, re-quoted or
truncated it. That is the same question `measure_stdin_transport` asks of the WSL hop, asked of
the launcher.

WHAT IT DOES NOT PROVE. Nothing about a model. Every verdict it returns comes from `--behaviour`;
it has no idea what the review says. The live proof that a real reviewer FLAGS a planted causation
mutation is not made by any test that uses this file.

`--behaviour` (default `supported`):
  supported       a SUPPORTED row per citation of the review it is shown
  flag-n:<n>      the same, with citation <n> returned OVERREACH
  drop-n:<n>      the same, with citation <n>'s row MISSING (the silent pass)
  extra-row       the same, plus a row for a citation the review does not have
  bad-verdict     a verdict outside the schema's enum
  bad-json        not JSON at all
  wrong-hashes    correct rows, with both sha256 fields set to a lie (the wrapper overwrites them)
  no-output       writes no file at all
`--citations <n>` sets how many rows to emit; the wrapper's caller passes the real count.
`--no-session` omits the session id from the event stream.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

FAKE_SESSION = "01a0bf5d-0b6d-7c21-a4a5-4bad288bb436"
ZERO = "0" * 64


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("-o", "--output-last-message", dest="out")
    ap.add_argument("--output-schema", dest="schema")
    ap.add_argument("-C", "--cd", dest="cd")
    ap.add_argument("-s", "--sandbox", dest="sandbox")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-git-repo-check", action="store_true")
    ap.add_argument("--behaviour", default="supported")
    ap.add_argument("--citations", type=int, default=1)
    ap.add_argument("--no-session", action="store_true")
    # parse_known_args, not parse_args: the wrapper appends the real command's whole argv tail
    # (`exec`, `-`, and anything a later Codex adds) after the flags a test injects, and a fake
    # that refused an argument it did not know would fail for a reason that is not the test's.
    args, _rest = ap.parse_known_args(sys.argv[1:] if argv is None else argv)

    raw = sys.stdin.buffer.read()
    digest = hashlib.sha256(raw).hexdigest()

    # The real command refuses a schema it cannot read; so does this, because a test that pointed
    # at a missing schema would otherwise pass for the wrong reason.
    if args.schema and not Path(args.schema).exists():
        print(f"no such schema: {args.schema}", file=sys.stderr)
        return 2

    if args.json:
        # Two events, the shape of a JSONL stream: one carrying the session, one the result. The
        # wrapper searches for the session key rather than assuming this shape.
        if not args.no_session:
            print(json.dumps({"type": "thread.started", "thread_id": FAKE_SESSION}))
        print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": len(raw)}}))

    if args.behaviour == "no-output":
        return 0

    n = max(args.citations, 1)
    rows = []
    for i in range(1, n + 1):
        verdict = "SUPPORTED"
        if args.behaviour.startswith("flag-n:") and i == int(args.behaviour.split(":")[1]):
            verdict = "OVERREACH"
        if args.behaviour.startswith("drop-n:") and i == int(args.behaviour.split(":")[1]):
            continue
        if args.behaviour == "bad-verdict" and i == 1:
            verdict = "PROBABLY FINE"
        rows.append({"n": i, "block_id": _block_id(raw, i),
                     "quote_head": f"citation {i}"[:80], "verdict": verdict,
                     "reason": f"stdin_sha256={digest}" if i == 1 else "fake reviewer"})
    if args.behaviour == "extra-row":
        rows.append({"n": n + 1, "block_id": ZERO[:8], "quote_head": "not in the review",
                     "verdict": "SUPPORTED", "reason": "a row for a citation that does not exist"})

    report = {"review_sha256": ZERO if args.behaviour != "wrong-hashes" else "f" * 64,
              "context_sha256": ZERO if args.behaviour != "wrong-hashes" else "e" * 64,
              "citations": rows, "editorial": []}
    text = "not json at all {" if args.behaviour == "bad-json" else json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0


def _block_id(prompt_bytes, i):
    """The i-th citation's block id, read out of the prompt the wrapper embedded.

    The fake has no database and no parser of its own: it finds the citation tokens in the prompt
    text with the SAME regex the grammar defines, imported when the litkb package is importable
    and matched loosely when it is not. Copying the review's own block ids is what lets the
    wrapper's citation-set check be exercised for real -- a fake that invented them would make
    every test a test of the mismatch branch.
    """
    text = prompt_bytes.decode("utf-8", "replace")
    try:
        from litkb.review_check import CITATION_RE
        hits = [m.group(3) for m in CITATION_RE.finditer(text)]
    except ImportError:                                        # pragma: no cover - path fallback
        import re
        hits = re.findall(r"\[[A-Za-z0-9][^\]\n]* p\.\d+ #([0-9a-fA-F][0-9a-fA-F-]*)\]", text)
    return hits[i - 1] if i - 1 < len(hits) else ZERO[:8]


if __name__ == "__main__":
    sys.exit(main())
