r"""The Codex review stage: one review + its block context -> one schema'd JSON report.

    PYTHONUTF8=1 py -3.12 qc/instruments/litkb_codex_review.py \
        --review ../Reports/reviews/<slug>.md --context <slug>.context.md --out <report>.json

WHY A WRAPPER AND NOT THE RELAY AGENT. The adversarial read of a review is the last stage of the
literature pipeline and it was, until this file, a conversation: a Claude relay composed a prompt,
pasted it into `codex exec`, and wrote the answer into a markdown report by hand
(`D:\tools\claude-config\agents\codex-reviewer.md`; the two proving runs in
`jobs/litkb-operational/`). Three things about that shape cannot be graded. The PROMPT was
composed per run, so two runs are not comparable. The OUTPUT was prose, so "did every citation get
a verdict" was a question somebody read the table to answer -- and run 1's own prose said 7/12
where its table held 6. And nothing bound the report to the bytes reviewed: a report and a review
edited between them look exactly like a report about the review.

So: the prompt is a tracked file (`docs/LITKB_CODEX_PROMPT.md`), the output is a JSON object
against a fixed schema (`qc/fixtures/litkb_codex_report.schema.json`), and the wrapper stamps both
files' sha256 over whatever the model wrote. The gate that reads the report is
`qc/instruments/litkb_acceptance.py codex`.

THE PROMPT CROSSES TWO SHELLS AND IS NEVER RE-QUOTED. It goes to a FILE, and the file's bytes go
to Codex on STDIN, with `-` as the prompt argument: `codex exec --help` (0.155.1) says "If not
provided as an argument (or if `-` is used), instructions are read from stdin". The relay agent's
recipe instead inlines `"$(cat <file>)"` inside a `bash -lc` string, which is a command
substitution inside a double-quoted argument inside a shell string -- three layers where a
backtick, a `$(`, or an unbalanced quote in a review being reviewed changes what the reviewer is
asked. `_launch_argv` passes argv through `bash -lc 'exec codex "$@"' _ ...` so nothing interpolates
at all, and `measure_stdin_transport()` proves the bytes survive by running that exact shape with
`cat` in Codex's place and comparing sha256.

NO TEST CALLS THE REAL CODEX. `--codex-cmd` injects a command in its place; the tests use
`qc/fixtures/litkb_fake_codex.py`, which reads the same stdin, honours `-o` and `--output-schema`,
and emits the same JSONL. What that buys is everything about this wrapper EXCEPT whether a real
model returns a well-formed report -- see the "Did NOT test" of the report that landed this file.
"""
import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
SCHEMA_DEFAULT = SCRIPTS / "qc" / "fixtures" / "litkb_codex_report.schema.json"
PROMPT_DEFAULT = SCRIPTS / "docs" / "LITKB_CODEX_PROMPT.md"
#: Everything below this marker in the prompt doc is the prompt itself.
PROMPT_BEGIN = "<!-- prompt-begin -->"
#: The four substitutions the prompt doc must offer. A doc missing one is refused rather than sent:
#: a prompt with no `{REVIEW_TEXT}` is a prompt asking a reviewer to review nothing, and the report
#: it returns would be well-formed.
PLACEHOLDERS = ("{REVIEW_PATH}", "{REVIEW_TEXT}", "{CONTEXT_PATH}", "{CONTEXT_TEXT}")
#: Keys an event of the `--json` stream might carry the session under. `codex exec --help` (0.155.1)
#: documents `--json` as "Print events to stdout as JSONL" and says nothing about the event shape,
#: and the relay agent that reads the id today does not name the key either. So the search is over
#: an ordered candidate list and the key that matched is RECORDED in the report -- a hardcoded key
#: that stopped matching would silently stamp `session_id: null`, which reads exactly like a run
#: that had no session.
SESSION_KEYS = ("session_id", "thread_id", "conversation_id", "id")


def sha256_file(path):
    """sha256 of a file's raw bytes -- `litkb.review_context.sha256_file`'s rule, restated here so
    this instrument stays importable without the litkb package on the path (it is run from qc, and
    from CI, where only the review and the context exist). A test pins the two to agree."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── the prompt ────────────────────────────────────────────────────────────────────────────


def build_prompt(review, context, *, template=None):
    """The prompt text: the tracked template with the review and the context embedded.

    Codex is given no path to open (see `docs/LITKB_CODEX_PROMPT.md`'s own header for why), so
    this is the only place the two documents enter the run, and the sha256 the wrapper stamps is
    of exactly these two files.
    """
    tpl_path = Path(template or PROMPT_DEFAULT)
    tpl = tpl_path.read_text(encoding="utf-8")
    if PROMPT_BEGIN not in tpl:
        raise SystemExit(f"litkb_codex_review: {tpl_path} has no {PROMPT_BEGIN} marker")
    body = tpl.split(PROMPT_BEGIN, 1)[1].lstrip("\n")
    missing = [p for p in PLACEHOLDERS if p not in body]
    if missing:
        raise SystemExit(f"litkb_codex_review: {tpl_path} is missing {', '.join(missing)} — a "
                         "prompt with no review in it would still produce a well-formed report")
    # newline="" on both reads: the review's and the block's line endings are content (half the
    # corpus's blocks carry CRLF), and a reviewer comparing a quote against a context file whose
    # breaks Python rewrote is comparing something the grader never saw.
    with Path(review).open(encoding="utf-8", newline="") as fh:
        review_text = fh.read()
    with Path(context).open(encoding="utf-8", newline="") as fh:
        context_text = fh.read()
    return (body.replace("{REVIEW_PATH}", str(review))
                .replace("{CONTEXT_PATH}", str(context))
                .replace("{REVIEW_TEXT}", review_text)
                .replace("{CONTEXT_TEXT}", context_text))


# ── the launcher ──────────────────────────────────────────────────────────────────────────


def _wslpath(p):
    """A Windows path as WSL sees it. Done here, in Python, rather than by `$(wslpath -u '<p>')`
    inside the shell string: a path is data, and a path that reaches a shell as text is a path
    that can carry a quote."""
    out = subprocess.run(["wsl.exe", "-e", "wslpath", "-u", str(p)],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _launch_argv(codex_cmd, cd, schema, out, *, translate=None):
    """The argv that runs Codex, and the ONE place the two shells meet.

    Default (`codex_cmd` None): `wsl.exe -e bash -lc 'exec codex "$@"' _ exec …`. The `"$@"`
    form is what makes this safe -- bash receives the arguments as arguments, so no path, no flag
    and no byte of the prompt is ever parsed as shell syntax. Every path is translated to a WSL
    path by `wslpath` BEFORE it becomes an argument.

    With `--codex-cmd`, the command is split by `shlex` and given the same tail with WINDOWS paths
    and no WSL in the middle: the injected fake runs on this side, so translating its paths would
    hand it names that do not exist here.
    """
    tail = ["exec", "-s", "read-only", "--skip-git-repo-check",
            "-C", str(cd), "--output-schema", str(schema), "--json", "-o", str(out), "-"]
    if codex_cmd:
        return shlex.split(codex_cmd) + tail
    tr = translate or _wslpath
    # By NAME, not by index: the tail is edited from time to time and an off-by-one here would
    # translate the wrong element -- the first draft of this line wrote over the `-`, which is
    # the one argument that must survive untouched.
    for flag in ("-C", "--output-schema", "-o"):
        tail[tail.index(flag) + 1] = tr(tail[tail.index(flag) + 1])
    return ["wsl.exe", "-e", "bash", "-lc", 'exec codex "$@"', "_"] + tail


def run_codex(prompt_bytes, argv, *, timeout=900):
    """(stdout, stderr, returncode). The prompt goes in as BYTES with no `text=True`: an encoder
    in the middle is one more thing that can rewrite a line ending between the file that was
    hashed and the reviewer that read it."""
    proc = subprocess.run(argv, input=prompt_bytes, capture_output=True, timeout=timeout)
    return proc.stdout, proc.stderr, proc.returncode


def measure_stdin_transport(prompt_path, *, runner=None):
    """Does a file's bytes reach a WSL process's stdin unchanged, through the exact argv shape
    `_launch_argv` builds? `{"sent": sha, "received": sha, "match": bool}`.

    This is the MEASUREMENT behind the docstring's claim, and it makes no Codex call: `cat` stands
    in for `codex` in the same `bash -lc 'exec … "$@"'` wrapper, so what is proven is the transport
    -- wsl.exe's stdin, bash's argv handling, and the absence of any re-quoting layer -- which is
    the part that could mangle a prompt. Whether the real Codex then reads stdin as its prompt is
    what `codex exec --help` states ("If not provided as an argument (or if `-` is used),
    instructions are read from stdin") and what S2's first live run confirms.
    """
    data = Path(prompt_path).read_bytes()
    argv = runner or ["wsl.exe", "-e", "bash", "-lc", 'exec cat "$@"', "_", "-"]
    proc = subprocess.run(argv, input=data, capture_output=True, timeout=120)
    return {"sent": hashlib.sha256(data).hexdigest(),
            "received": hashlib.sha256(proc.stdout).hexdigest(),
            "match": hashlib.sha256(data).hexdigest() == hashlib.sha256(proc.stdout).hexdigest(),
            "bytes": len(data), "rc": proc.returncode}


def session_from_stream(stdout):
    """(session_id, key) from the `--json` JSONL stream, or (None, None).

    Tolerant by design: the first candidate key in `SESSION_KEYS` that appears anywhere in any
    event object (at any depth) wins, and the key that matched is returned so the report can say
    which one it was. `codex exec --help` documents neither the event type nor the field, so a
    single hardcoded key is an assumption this stage cannot afford to make silently.
    """
    text = stdout.decode("utf-8", "replace") if isinstance(stdout, (bytes, bytearray)) else stdout
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in SESSION_KEYS and isinstance(v, str) and v and k not in found:
                    found[k] = v
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            walk(json.loads(line))
        except json.JSONDecodeError:
            continue
    for k in SESSION_KEYS:
        if k in found:
            return found[k], k
    return None, None


# ── the schema ────────────────────────────────────────────────────────────────────────────


def validate(instance, schema, *, path="$"):
    """Validation errors against the subset of JSON Schema this stage's fixture uses, as a list of
    strings. `[]` means valid.

    WHY NOT `jsonschema`. The package is installed on this machine (4.26.0) and is in neither
    `requirements-local.txt` nor `requirements-colab.txt`, and the same-commit rule (CLAUDE.md
    §2.1) says a bootstrap and a requirements file may not disagree. Adding a runtime dependency
    for one fixed, hand-written schema is the larger change; this validator covers exactly the
    keywords that fixture uses and refuses any keyword it does not implement, so a schema edit
    that reaches past it FAILS LOUDLY instead of passing unchecked.

    `qc/test_litkb_codex_stage.py` cross-checks this function against real `jsonschema` on every
    accept and reject case, and SKIPS when the package is absent -- so the agreement is measured
    where it can be, and this stage never depends on it.
    """
    known = {"$schema", "title", "description", "type", "properties", "required",
             "additionalProperties", "items", "enum", "pattern", "minimum", "maxLength",
             "minLength"}
    unknown = set(schema) - known
    if unknown:
        return [f"{path}: schema uses keywords this validator does not implement: "
                f"{sorted(unknown)} — extend validate() or the check is not a check"]
    errs = []
    types = schema.get("type")
    if types is not None:
        types = [types] if isinstance(types, str) else list(types)
        ok = {"object": dict, "array": list, "string": str, "integer": int,
              "number": (int, float), "boolean": bool, "null": type(None)}
        # bool is a subclass of int in Python and is not an "integer" to JSON Schema.
        if not any(isinstance(instance, ok[t]) and not (t in ("integer", "number")
                                                        and isinstance(instance, bool))
                   for t in types):
            return [f"{path}: expected {'/'.join(types)}, got {type(instance).__name__}"]
    if "enum" in schema and instance not in schema["enum"]:
        errs.append(f"{path}: {instance!r} is not one of {schema['enum']}")
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errs.append(f"{path}: {instance!r} does not match {schema['pattern']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errs.append(f"{path}: longer than {schema['maxLength']} characters ({len(instance)})")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errs.append(f"{path}: shorter than {schema['minLength']} characters")
    if isinstance(instance, int) and not isinstance(instance, bool) and "minimum" in schema:
        if instance < schema["minimum"]:
            errs.append(f"{path}: {instance} is below the minimum {schema['minimum']}")
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errs.append(f"{path}: missing required property {name!r}")
        if schema.get("additionalProperties") is False:
            for name in instance:
                if name not in props:
                    errs.append(f"{path}: additional property {name!r} is not allowed")
        for name, sub in props.items():
            if name in instance:
                errs += validate(instance[name], sub, path=f"{path}.{name}")
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errs += validate(item, schema["items"], path=f"{path}[{i}]")
    return errs


# ── the citation set ──────────────────────────────────────────────────────────────────────


def review_citations(review):
    """[(n, block_id)] for the review, 1-based, in document order, ONE ROW PER OCCURRENCE.

    `review_check.citations` is the parser -- the grammar's citation form has one home
    (LITKB_REVIEW_GRAMMAR.md §2) and a second regex here would be a second grammar. The import is
    lazy and its failure is named, because this instrument also runs where the litkb package is
    not on the path.
    """
    try:
        from litkb.review_check import _read, citations
    except ImportError as e:                                       # noqa: BLE001 - named below
        raise SystemExit("litkb_codex_review: the litkb package is not importable "
                         f"({e}); run from <worktree>/Scripts with PYTHONPATH=pipeline") from e
    return [(i, c["block_id"]) for i, c in enumerate(citations(_read(review)), start=1)]


def check_citation_set(report, review):
    """The offences in the report's citation rows against the review's own citations.

    A MISSING ROW IS A SILENT PASS and is the one failure this whole stage could not otherwise
    see: a reviewer that skipped the citation it could not decide returns a report whose every
    row says SUPPORTED. Rows are compared as a SEQUENCE of (n, block_id), so an extra row, a
    duplicate `n`, a row whose `n` names no citation, and a row whose `block_id` is not that
    citation's are each named separately.
    """
    want = review_citations(review)
    rows = report.get("citations", [])
    offences, by_n = [], {}
    for r in rows:
        n = r.get("n")
        if n in by_n:
            offences.append(f"citation n={n} has two rows")
        by_n[n] = r
    want_ns = {n for n, _ in want}
    for n, bid in want:
        if n not in by_n:
            offences.append(f"citation n={n} (#{bid}) has no row — a missing row reads as a pass")
        elif by_n[n].get("block_id") != bid:
            offences.append(f"citation n={n} names block {bid}, the report says "
                            f"{by_n[n].get('block_id')!r}")
    for n in by_n:
        if n not in want_ns:
            offences.append(f"the report has a row n={n}, the review has {len(want)} citation(s)")
    return offences


# ── the run ───────────────────────────────────────────────────────────────────────────────


def run(review, context, out, *, schema=None, template=None, codex_cmd=None, cd=None,
        prompt_out=None, timeout=900, translate=None):
    """The whole stage. Returns (exit code, report-or-None, counters)."""
    schema_path = Path(schema or SCHEMA_DEFAULT)
    schema_doc = json.loads(schema_path.read_text(encoding="utf-8"))
    prompt = build_prompt(review, context, template=template)
    prompt_path = Path(prompt_out or (Path(out).with_suffix(".prompt.txt")))
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    # The prompt is written with newline="" and read back as BYTES: what is hashed, what is sent,
    # and what a human can open to see what was asked are one file.
    with prompt_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(prompt)
    argv = _launch_argv(codex_cmd, cd or Path(review).resolve().parent, schema_path, out,
                        translate=translate)
    stdout, stderr, rc = run_codex(prompt_path.read_bytes(), argv, timeout=timeout)
    counters = {"codex_rc": rc, "schema_errors": 0, "citation_offences": 0}
    out_path = Path(out)
    if not out_path.exists():
        print(f"codex wrote no report to {out_path} (rc={rc})", file=sys.stderr)
        print((stderr or b"").decode("utf-8", "replace")[-2000:], file=sys.stderr)
        counters["schema_errors"] = 1
        return 1, None, counters
    try:
        report = json.loads(out_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"codex's report is not JSON: {e}", file=sys.stderr)
        counters["schema_errors"] = 1
        return 1, None, counters

    # STAMPED, NOT TRUSTED. Both digests are computed here over the files this wrapper actually
    # read, and overwrite whatever the model put there, so the report can never be wrong about
    # which bytes it is about. The session id is stamped for the same reason.
    report["review_sha256"] = sha256_file(review)
    report["context_sha256"] = sha256_file(context)
    sid, key = session_from_stream(stdout)
    report["session_id"] = sid
    report["session_id_key"] = key

    errs = validate(report, schema_doc)
    offences = [] if errs else check_citation_set(report, review)
    counters["schema_errors"] = len(errs)
    counters["citation_offences"] = len(offences)
    for line in errs + offences:
        print(line, file=sys.stderr)
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return (1 if (errs or offences or rc != 0) else 0), report, counters


def build_parser():
    ap = argparse.ArgumentParser(
        description="run the Codex review stage over one review and its block context")
    ap.add_argument("--review", required=True, help="the review .md under test")
    ap.add_argument("--context", required=True,
                    help="its block context (py -3.12 -m litkb review-context)")
    ap.add_argument("--out", required=True, help="where to write the JSON report")
    ap.add_argument("--schema", default=str(SCHEMA_DEFAULT),
                    help="the report schema (default: %(default)s)")
    ap.add_argument("--prompt-template", dest="template", default=str(PROMPT_DEFAULT),
                    help="the tracked prompt (default: %(default)s)")
    ap.add_argument("--prompt-out", dest="prompt_out",
                    help="where to write the prompt actually sent (default: <out>.prompt.txt)")
    ap.add_argument("--codex-cmd", dest="codex_cmd",
                    help="run this instead of Codex-in-WSL, with the same argv tail and WINDOWS "
                         "paths (tests inject qc/fixtures/litkb_fake_codex.py here; no test "
                         "calls the real Codex)")
    ap.add_argument("--cd", help="Codex's working root (default: the review's directory)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds (default: %(default)s)")
    ap.add_argument("--measure-transport", action="store_true",
                    help="build the prompt, send it through the WSL argv shape with `cat` in "
                         "Codex's place, and print whether its bytes survived. Makes no Codex call")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.measure_transport:
        if not shutil.which("wsl.exe"):
            print("wsl.exe not on PATH — the transport cannot be measured here", file=sys.stderr)
            return 1
        prompt = build_prompt(args.review, args.context, template=args.template)
        p = Path(args.prompt_out or Path(args.out).with_suffix(".prompt.txt"))
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as fh:
            fh.write(prompt)
        m = measure_stdin_transport(p)
        print(" ".join(f"{k}={v}" for k, v in m.items()))
        return 0 if m["match"] else 1
    rc, _report, counters = run(args.review, args.context, args.out, schema=args.schema,
                                template=args.template, codex_cmd=args.codex_cmd, cd=args.cd,
                                prompt_out=args.prompt_out, timeout=args.timeout)
    print(" ".join(f"{k}={v}" for k, v in counters.items()) + f" report={args.out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
