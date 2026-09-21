"""The Codex review stage: `litkb review-context`, the report schema, the wrapper, the gate.

WHAT EACH ROW BELOW IS. CLAUDE.md 3.4c: a kill criterion that has never been shown to fire on a
known-bad input is not a gate. So every counter of `litkb_acceptance.py codex`, and every refusal
of the wrapper, has a row here that MAKES the bad input and asserts the counter fires:

  row  the known-bad input                                          counter / refusal
  X1   a report with no row for citation 2                          citations_unreviewed=1
  X1b  a report whose row 1 names another block                     citations_unreviewed=1
  X2   a verdict outside SUPPORTED/OVERREACH/UNSUPPORTED            verdict_outside_set=1
  X3   a report stamped with digests that are not these files'      hash_mismatch=2
  X4   a mutated review whose planted causation is returned         mutation_not_flagged=1
       SUPPORTED
  X4b  the same, flagged OVERREACH                                  mutation_not_flagged=0
  X5   a review whose cited block the workstream cannot see         BLOCK NOT VISIBLE + exit 1
  X6   a report that is not JSON / no report file at all            wrapper exits 1
  X7   a prompt template with a placeholder deleted                 refused before any launch
  X8   a schema edited to use a keyword `validate` does not
       implement                                                    refused, not passed unchecked
  X9   a mutation rule that would change a citation                 refused, nothing written

WHAT IS NOT TESTED HERE, and must not be read as tested: whether a REAL reviewer flags a planted
causation. Every run below injects `qc/fixtures/litkb_fake_codex.py`, whose verdicts come from a
command-line flag. The live proof is S2's, and the report that landed this file says so in those
words.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import test_litkb_p1 as _p1mod
from test_litkb_review_check import _review, _world

_pg_session = _p1mod._pg_session
pg = _p1mod.pg
pg_only = pytest.mark.requires_litkb_pg

SCRIPTS = Path(__file__).resolve().parents[1]
INSTR = SCRIPTS / "qc" / "instruments" / "litkb_codex_review.py"
ACCEPT = SCRIPTS / "qc" / "instruments" / "litkb_acceptance.py"
SCHEMA = SCRIPTS / "qc" / "fixtures" / "litkb_codex_report.schema.json"
FAKE = SCRIPTS / "qc" / "fixtures" / "litkb_fake_codex.py"
PROMPT_DOC = SCRIPTS / "docs" / "LITKB_CODEX_PROMPT.md"


def _raw(path):
    """A file's text with NEWLINE TRANSLATION OFF -- the reader `review_check._read` uses, and the
    one this stage's hashes are over. `Path.read_text` has no `newline=` parameter, which is the
    same reason `_read` opens the file explicitly."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return fh.read()


def _wrapper():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_litkb_codex_review", INSTR)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _accept():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_litkb_acceptance_codex", ACCEPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


W = _wrapper()
A = _accept()

#: The fake, as a `--codex-cmd`. `sys.executable` rather than `py -3.12` so the subprocess runs
#: the interpreter this suite runs under, whatever launched it.
def _fake_cmd(*flags):
    import shlex

    return " ".join([shlex.quote(sys.executable), shlex.quote(str(FAKE)), *flags])


# ── review-context ─────────────────────────────────────────────────────────────────────────


def _two_block_review(pg, w):
    """A review citing w's block TWICE and a second block once: three occurrences, two distinct
    blocks. The shape that makes the dedupe rule and the occurrence numbering separable."""
    second_text = ("A second paragraph of the same file, long enough to quote from without "
                   "tripping the twenty-five character floor.")
    second = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                    "(%s, %s, 2, 'paragraph', %s) RETURNING id",
                    (w["file"], w["run"], second_text))[0]
    body = (f'It says so plainly: "{w["quote"]}" [{w["key"]} p.1 #{w["block"]}].\n'
            f'It says so again: "{w["quote"]}" [{w["key"]} p.1 #{w["block"]}].\n'
            f'And elsewhere: "{second_text[:60]}" [{w["key"]} p.2 #{second}].\n')
    return _review(w).replace(
        f'The work states it directly: "{w["quote"]}" [{w["key"]} p.1 #{w["block"]}].\n', body
    ), second, second_text


@pg_only
def test_review_context_is_one_section_per_distinct_block_in_citation_order(pg):
    from litkb import review_context as rx

    w = _world(pg)
    text, second, second_text = _two_block_review(pg, w)
    md, report = rx.build(pg.conn, text, is_text=True)
    assert report == {"citations": 3, "blocks": 2, "missing": []}, report
    heads = [ln for ln in md.splitlines() if ln.startswith("## ")]
    assert heads == [f"## [{w['key']} p.1 #{w['block']}]", f"## [{w['key']} p.2 #{second}]"], heads
    assert w["text"] in md and second_text in md


@pg_only
def test_review_context_shows_the_whole_block_not_the_quoted_span(pg):
    """The point of the file. The quote is what the writer chose; the block is what the reviewer
    needs to tell a faithful sentence from one the paragraph does not carry."""
    from litkb import review_context as rx

    w = _world(pg)
    md, _ = rx.build(pg.conn, _review(w), is_text=True)
    assert w["quote"] in w["text"] and len(w["text"]) > len(w["quote"])
    assert w["text"] in md, "the context showed something other than the block's whole text"


@pg_only
def test_X5_a_block_the_workstream_cannot_see_is_named_and_the_command_fails(pg, tmp_path):
    """A context file with a hole must not look complete: the reviewer reads the sections it was
    given and cannot know that the citation it was never shown is the one that was missing."""
    from litkb import review_context as rx

    w = _world(pg)
    md, report = rx.build(pg.conn, _review(w, block_id=uuid.uuid4()), is_text=True)
    assert len(report["missing"]) == 1, report
    assert rx.NOT_VISIBLE in md
    assert "```" not in md, "a not-visible block must not be shown as an empty fenced block"


@pg_only
def test_X5_the_cli_exits_1_on_a_hole_and_0_without_one(pg, tmp_path):
    from litkb import review_context as rx

    w = _world(pg)
    good, bad = tmp_path / "good.md", tmp_path / "bad.md"
    good.write_text(_review(w), encoding="utf-8", newline="")
    bad.write_text(_review(w, block_id=uuid.uuid4()), encoding="utf-8", newline="")
    assert rx.write(pg.conn, good, tmp_path / "g.ctx.md")["missing"] == []
    assert len(rx.write(pg.conn, bad, tmp_path / "b.ctx.md")["missing"]) == 1
    # the CLI's own exit code is `1 if report["missing"] else 0` (commands.cmd_review_context)


@pg_only
def test_the_context_header_carries_the_reviews_path_and_sha256(pg, tmp_path):
    from litkb import review_context as rx

    w = _world(pg)
    p = tmp_path / "r.md"
    p.write_text(_review(w), encoding="utf-8", newline="")
    md, _ = rx.build(pg.conn, p)
    want = hashlib.sha256(p.read_bytes()).hexdigest()
    assert f"review_sha256={want}" in md
    assert str(p) in md


@pg_only
def test_review_context_uses_the_grammars_own_citation_parser(pg):
    """Not a style point. A second regex would be a second grammar, and the first review that
    drifted between them would get a context file missing exactly the citation in dispute."""
    src = (SCRIPTS / "pipeline" / "litkb" / "review_context.py").read_text(encoding="utf-8")
    assert "from litkb.review_check import" in src
    assert "re.compile" not in src, "review_context.py compiled a regex of its own"


def test_the_two_sha256_definitions_agree(tmp_path):
    """The wrapper restates `review_context.sha256_file` so it stays importable without the litkb
    package. Restated is not copied-and-drifted only while something compares them."""
    from litkb.review_context import sha256_file as a

    p = tmp_path / "x.bin"
    p.write_bytes(b"\r\n mixed \n endings \r\n")
    assert a(p) == W.sha256_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


# ── the schema, and the validator that stands in for jsonschema ────────────────────────────


def _ok_report(n=1, block="0199a7d2-aaaa-4c1b-9999-000000000001"):
    return {"review_sha256": "a" * 64, "context_sha256": "b" * 64,
            "citations": [{"n": i, "block_id": block, "quote_head": f"q{i}",
                           "verdict": "SUPPORTED", "reason": "fits"} for i in range(1, n + 1)],
            "editorial": []}


CASES = [
    ("valid", _ok_report(), True),
    ("valid with editorial", {**_ok_report(), "editorial": [{"where": "Scope", "finding": "x"}]},
     True),
    ("valid with session", {**_ok_report(), "session_id": "abc", "session_id_key": "thread_id"},
     True),
    ("X2 verdict outside the enum",
     {**_ok_report(), "citations": [{**_ok_report()["citations"][0], "verdict": "MAYBE"}]}, False),
    ("sha not hex", {**_ok_report(), "review_sha256": "NOTAHASH"}, False),
    ("missing editorial", {k: v for k, v in _ok_report().items() if k != "editorial"}, False),
    ("additional property", {**_ok_report(), "notes": "hello"}, False),
    ("quote_head over 80",
     {**_ok_report(), "citations": [{**_ok_report()["citations"][0], "quote_head": "x" * 81}]},
     False),
    ("n is zero", {**_ok_report(), "citations": [{**_ok_report()["citations"][0], "n": 0}]},
     False),
    ("n is a string", {**_ok_report(), "citations": [{**_ok_report()["citations"][0], "n": "1"}]},
     False),
    ("empty reason",
     {**_ok_report(), "citations": [{**_ok_report()["citations"][0], "reason": ""}]}, False),
    ("citations not a list", {**_ok_report(), "citations": {}}, False),
    ("editorial row missing where", {**_ok_report(), "editorial": [{"finding": "x"}]}, False),
]


@pytest.mark.parametrize("name,doc,valid", CASES, ids=[c[0] for c in CASES])
def test_the_hand_validator_accepts_and_refuses(name, doc, valid):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errs = W.validate(doc, schema)
    assert (errs == []) is valid, (name, errs)


@pytest.mark.parametrize("name,doc,valid", CASES, ids=[c[0] for c in CASES])
def test_the_hand_validator_agrees_with_jsonschema(name, doc, valid):
    """The independence this stage's validator needs. `jsonschema` is installed here and is in
    NEITHER requirements file, so the wrapper does not depend on it (the same-commit rule); this
    test measures that the hand validator says the same thing a real implementation does, and
    SKIPS where the package is absent rather than making the stage need it."""
    js = pytest.importorskip("jsonschema", reason="jsonschema is not installed")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    v = js.Draft202012Validator(schema)
    assert bool(list(v.iter_errors(doc))) is (not valid), name
    assert (W.validate(doc, schema) == []) is valid, name


def test_X8_a_schema_keyword_the_validator_does_not_implement_is_refused():
    """A validator that ignored an unknown keyword would pass every instance the keyword was
    added to constrain, and nothing would say so."""
    schema = {"type": "object", "properties": {"x": {"type": "string", "format": "uuid"}}}
    errs = W.validate({"x": "not a uuid"}, schema)
    assert errs and "does not implement" in errs[0], errs


def test_the_schema_is_the_file_the_wrapper_and_the_gate_both_name():
    assert W.SCHEMA_DEFAULT == SCHEMA
    doc = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert doc["additionalProperties"] is False
    assert (doc["properties"]["citations"]["items"]["properties"]["verdict"]["enum"]
            == list(A.CODEX_VERDICTS))


# ── the prompt ─────────────────────────────────────────────────────────────────────────────


def test_X7_a_prompt_template_missing_a_placeholder_is_refused(tmp_path):
    body = PROMPT_DOC.read_text(encoding="utf-8").replace("{REVIEW_TEXT}", "")
    p = tmp_path / "prompt.md"
    p.write_text(body, encoding="utf-8")
    r, c = tmp_path / "r.md", tmp_path / "c.md"
    r.write_text("review", encoding="utf-8")
    c.write_text("context", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        W.build_prompt(r, c, template=p)
    assert "REVIEW_TEXT" in str(e.value)


def test_the_prompt_embeds_both_documents_verbatim(tmp_path):
    r, c = tmp_path / "r.md", tmp_path / "c.md"
    r.write_text('A claim: "a verbatim span here" [K_2020_x-paper p.1 #0199a7d2-aaaa].\n',
                 encoding="utf-8", newline="")
    c.write_text("## [K_2020_x-paper p.1 #0199a7d2-aaaa]\n\n```\nthe whole block\n```\n",
                 encoding="utf-8", newline="")
    prompt = W.build_prompt(r, c)
    assert _raw(r) in prompt
    assert _raw(c) in prompt
    assert "{REVIEW_TEXT}" not in prompt and "{CONTEXT_TEXT}" not in prompt


def test_the_prompt_doc_is_the_wrappers_default():
    assert W.PROMPT_DEFAULT == PROMPT_DOC
    assert PROMPT_DOC.read_text(encoding="utf-8").count(W.PROMPT_BEGIN) == 1


# ── the launcher, and the prompt-passing mechanism ─────────────────────────────────────────


def test_the_default_launcher_passes_argv_through_bash_without_interpolation():
    """`bash -lc 'exec codex "$@"' _ …` -- bash receives the arguments AS arguments, so no path,
    no flag and no byte of the prompt is ever parsed as shell syntax. The relay agent's recipe
    instead inlines `"$(cat <file>)"`, which is a command substitution inside a quoted argument
    inside a shell string."""
    argv = W._launch_argv(None, "C:/w", "C:/s.json", "C:/o.json",
                          translate=lambda p: "/mnt/c/" + str(p).replace("C:/", ""))
    assert argv[:6] == ["wsl.exe", "-e", "bash", "-lc", 'exec codex "$@"', "_"]
    assert argv[-1] == "-", "the prompt must be read from stdin, not passed as an argument"
    assert "--output-schema" in argv and "-s" in argv and "read-only" in argv
    assert all(not a.startswith("C:") for a in argv), "a Windows path reached the WSL argv"


def test_an_injected_codex_cmd_keeps_windows_paths_and_never_enters_wsl():
    argv = W._launch_argv(_fake_cmd("--behaviour", "supported"), "C:/w", "C:/s.json", "C:/o.json")
    assert "wsl.exe" not in argv
    assert "C:/w" in argv and argv[-1] == "-"


@pytest.mark.skipif(not shutil.which("wsl.exe"), reason="wsl.exe is not on PATH")
def test_the_stdin_transport_delivers_the_prompt_bytes_unchanged(tmp_path):
    """THE MEASUREMENT behind "stdin, not a re-quoted argument". `cat` stands in for `codex` in
    the exact argv shape `_launch_argv` builds, and the sha256 of what comes back is compared to
    the file's. It makes no Codex call. What it does not prove is that the real Codex reads stdin
    as its prompt -- that is what `codex exec --help` states and what S2 confirms live."""
    p = tmp_path / "prompt.txt"
    # the bytes a shell would mangle: a backtick, a $( ), a quote, a CRLF, a non-ASCII character
    p.write_bytes("a `backtick` $(whoami) \"quoted\" '\u2014' \r\n and a break\n".encode("utf-8"))
    m = W.measure_stdin_transport(p)
    assert m["match"], m
    assert m["bytes"] == len(p.read_bytes())


def test_the_session_id_is_read_from_the_stream_by_a_named_key():
    """`codex exec --help` documents `--json` as "Print events to stdout as JSONL" and says
    nothing about the event shape, so the key is searched for and RECORDED, never assumed."""
    stream = (b'{"type":"thread.started","thread_id":"01a0-abcd"}\n'
              b'not json\n{"type":"turn.completed"}\n')
    assert W.session_from_stream(stream) == ("01a0-abcd", "thread_id")
    assert W.session_from_stream(b'{"type":"x","session_id":"s1"}') == ("s1", "session_id")
    assert W.session_from_stream(b"") == (None, None)


def test_a_session_id_nested_in_an_event_is_still_found():
    assert W.session_from_stream(b'{"msg":{"meta":{"thread_id":"deep"}}}') == ("deep", "thread_id")


# ── the wrapper, end to end, with the fake ─────────────────────────────────────────────────


@pytest.fixture()
def bundle(tmp_path):
    """A review with two citations, a context file, and the paths the wrapper needs. No DB: the
    wrapper never queries one -- it parses the review with the grammar's parser and hashes files."""
    b1, b2 = "0199a7d2-aaaa-4c1b-9999-000000000001", "0199a7d2-aaaa-4c1b-9999-000000000002"
    review = tmp_path / "review.md"
    review.write_text(
        "<!-- litkb-review workstream=slug -->\n\n# T\n\n## Scope\nA question.\n\n## Findings\n"
        'The paper is associated with the result: "a first verbatim span of the block" '
        f"[K_2020_x-paper p.1 #{b1}].\n"
        'It also says: "a second verbatim span of the block" '
        f"[K_2020_x-paper p.2 #{b2}].\n",
        encoding="utf-8", newline="")
    context = tmp_path / "context.md"
    context.write_text(f"## [K_2020_x-paper p.1 #{b1}]\n\n```\nwhole block one\n```\n",
                       encoding="utf-8", newline="")
    return {"review": review, "context": context, "out": tmp_path / "report.json",
            "b1": b1, "b2": b2, "tmp": tmp_path}


def _run(bundle, *flags):
    return W.run(bundle["review"], bundle["context"], bundle["out"],
                 codex_cmd=_fake_cmd("--citations", "2", *flags), cd=bundle["tmp"])


def test_the_wrapper_stamps_both_digests_over_whatever_the_model_wrote(bundle):
    """X3's other half: the report can never be wrong about which bytes it is about, because the
    model's values are overwritten rather than checked."""
    rc, report, counters = _run(bundle, "--behaviour", "wrong-hashes")
    assert rc == 0, counters
    assert report["review_sha256"] == W.sha256_file(bundle["review"])
    assert report["context_sha256"] == W.sha256_file(bundle["context"])
    on_disk = json.loads(bundle["out"].read_text(encoding="utf-8"))
    assert on_disk["review_sha256"] == report["review_sha256"]


def test_the_wrapper_stamps_the_session_id_and_the_key_it_came_from(bundle):
    rc, report, _ = _run(bundle)
    assert rc == 0
    assert report["session_id"] and report["session_id_key"] == "thread_id"


def test_a_stream_with_no_session_stamps_null_rather_than_a_guess(bundle):
    rc, report, _ = _run(bundle, "--no-session")
    assert rc == 0 and report["session_id"] is None and report["session_id_key"] is None


def test_the_prompt_reaches_the_launched_process_byte_for_byte(bundle):
    """The launcher's half of the transport measurement: the fake writes sha256 of its own stdin
    into row 1's reason, and the prompt file the wrapper wrote is hashed here."""
    rc, report, _ = _run(bundle)
    assert rc == 0
    prompt = bundle["out"].with_suffix(".prompt.txt")
    assert report["citations"][0]["reason"] == (
        "stdin_sha256=" + hashlib.sha256(prompt.read_bytes()).hexdigest())


def test_X1_a_missing_citation_row_fails_the_wrapper(bundle):
    rc, _report, counters = _run(bundle, "--behaviour", "drop-n:2")
    assert rc == 1 and counters["citation_offences"] >= 1, counters


def test_X1_an_extra_row_fails_the_wrapper(bundle):
    rc, _report, counters = _run(bundle, "--behaviour", "extra-row")
    assert rc == 1 and counters["citation_offences"] >= 1, counters


def test_X2_a_verdict_outside_the_enum_fails_schema_validation(bundle):
    rc, _report, counters = _run(bundle, "--behaviour", "bad-verdict")
    assert rc == 1 and counters["schema_errors"] >= 1, counters


def test_X6_a_report_that_is_not_json_fails(bundle):
    rc, report, counters = _run(bundle, "--behaviour", "bad-json")
    assert rc == 1 and report is None and counters["schema_errors"] == 1


def test_X6_no_report_file_at_all_fails(bundle):
    rc, report, counters = _run(bundle, "--behaviour", "no-output")
    assert rc == 1 and report is None and counters["schema_errors"] == 1


def test_the_wrapper_reuses_the_grammars_citation_parser(bundle):
    """`review_citations` must number OCCURRENCES, 1-based, in document order."""
    assert W.review_citations(bundle["review"]) == [(1, bundle["b1"]), (2, bundle["b2"])]


# ── the gate ───────────────────────────────────────────────────────────────────────────────


def _graded(bundle, *flags, mutate=None, review=None):
    rc, _r, _c = W.run(review or bundle["review"], bundle["context"], bundle["out"],
                       codex_cmd=_fake_cmd("--citations", "2", *flags), cd=bundle["tmp"])
    counters, offences = A.check_codex(review or bundle["review"], bundle["context"],
                                       bundle["out"], mutate=mutate)
    return rc, counters, offences


def test_the_gate_passes_a_complete_report(bundle):
    _rc, counters, offences = _graded(bundle)
    assert counters == {"citations_unreviewed": 0, "verdict_outside_set": 0, "hash_mismatch": 0,
                        "overreach": 0, "unsupported": 0}, (counters, offences)
    assert A.codex_ok(counters)


def test_X1_citations_unreviewed_fires_on_a_missing_row(bundle):
    _rc, counters, offences = _graded(bundle, "--behaviour", "drop-n:2")
    assert counters["citations_unreviewed"] == 1, (counters, offences)
    assert not A.codex_ok(counters)


def test_X1b_citations_unreviewed_fires_when_a_row_names_another_block(bundle):
    _rc, _c, _o = _graded(bundle)
    doc = json.loads(bundle["out"].read_text(encoding="utf-8"))
    doc["citations"][0]["block_id"] = "0199a7d2-aaaa-4c1b-9999-00000000ffff"
    bundle["out"].write_text(json.dumps(doc), encoding="utf-8")
    counters, offences = A.check_codex(bundle["review"], bundle["context"], bundle["out"])
    assert counters["citations_unreviewed"] == 1, (counters, offences)


def test_X2_verdict_outside_set_fires_on_a_free_text_verdict(bundle):
    _rc, _c, _o = _graded(bundle)
    doc = json.loads(bundle["out"].read_text(encoding="utf-8"))
    doc["citations"][0]["verdict"] = "probably fine"
    bundle["out"].write_text(json.dumps(doc), encoding="utf-8")
    counters, _ = A.check_codex(bundle["review"], bundle["context"], bundle["out"])
    assert counters["verdict_outside_set"] == 1 and not A.codex_ok(counters)


def test_X3_hash_mismatch_fires_when_the_review_changed_under_the_report(bundle):
    """A report and a review edited between them look exactly like a report about the review."""
    _rc, counters, _o = _graded(bundle)
    assert counters["hash_mismatch"] == 0
    with bundle["review"].open("a", encoding="utf-8", newline="") as fh:
        fh.write("\nAn extra line added after the review was reviewed.\n")
    counters, offences = A.check_codex(bundle["review"], bundle["context"], bundle["out"])
    assert counters["hash_mismatch"] == 1, (counters, offences)
    assert not A.codex_ok(counters)


def test_hash_mismatch_fires_for_the_context_too(bundle):
    _rc, _c, _o = _graded(bundle)
    with bundle["context"].open("a", encoding="utf-8", newline="") as fh:
        fh.write("\nan added block\n")
    counters, _ = A.check_codex(bundle["review"], bundle["context"], bundle["out"])
    assert counters["hash_mismatch"] == 1


def test_overreach_is_a_finding_and_never_fails_the_gate(bundle):
    """A gate that failed on a finding would pay the reviewer to find nothing."""
    _rc, counters, _o = _graded(bundle, "--behaviour", "flag-n:1")
    assert counters["overreach"] == 1
    assert A.codex_ok(counters), "an OVERREACH finding failed the gate"


# ── the mutation: the kill ─────────────────────────────────────────────────────────────────


def test_the_mutation_plants_causation_and_leaves_every_quote_byte_identical(bundle):
    from litkb.review_check import citations

    text = _raw(bundle["review"])
    mutated, done = A.mutate_review(text, 1)
    assert mutated != text and "causes" in done
    assert "The paper causes the result:" in mutated
    before = [(c["work_key"], c["page"], c["block_id"], c["quote"]) for c in citations(text)]
    after = [(c["work_key"], c["page"], c["block_id"], c["quote"]) for c in citations(mutated)]
    assert before == after, "the rewrite moved a quote"


def test_the_mutation_falls_back_to_a_because_prefix(bundle):
    mutated, done = A.mutate_review(_raw(bundle["review"]), 2)
    assert "prefixed" in done and "Because of this, It also says:" in mutated


def test_the_mutation_is_deterministic_and_idempotent(bundle):
    text = _raw(bundle["review"])
    a, _ = A.mutate_review(text, 1)
    b, _ = A.mutate_review(text, 1)
    assert a == b
    p1, _ = A.write_mutation(bundle["review"], 1)
    first = p1.read_bytes()
    p2, _ = A.write_mutation(bundle["review"], 1)
    assert p2.read_bytes() == first and p1 == p2


def test_the_mutation_refuses_a_citation_number_the_review_does_not_have(bundle):
    with pytest.raises(SystemExit):
        A.mutate_review(_raw(bundle["review"]), 9)


def test_X9_a_rewrite_that_changes_a_citation_is_refused_not_reported(bundle, monkeypatch):
    """The guard that makes the two rules safe rather than merely careful: it compares the whole
    (work_key, page, block_id, quote) list before and after, so a rewrite that touched ANY of the
    four is refused rather than written.

    The known-bad is reached by widening one constant -- `_BECAUSE` carrying a citation token --
    because with the two SHIPPED rules a quote change is not reachable at all, and that is worth
    saying rather than leaving implicit: rule 1 only fires on a region the rule itself has checked
    holds no quote delimiter, and rule 2 inserts text at a sentence start, which is always before
    the quote's opening delimiter. The guard is here for the third rule somebody adds.
    """
    monkeypatch.setattr(A, "_BECAUSE", "Because of this [K_2020_x-paper p.9 #0199a7d2-bbbb], ")
    with pytest.raises(SystemExit) as e:
        A.mutate_review(_raw(bundle["review"]), 2)
    assert "changed a citation or a quote" in str(e.value)


def test_X4b_the_kill_passes_when_the_reviewer_flags_the_planted_claim(bundle):
    mutated, _ = A.write_mutation(bundle["review"], 1)
    _rc, counters, offences = _graded(bundle, "--behaviour", "flag-n:1", mutate=1, review=mutated)
    assert counters["mutation_not_flagged"] == 0, (counters, offences)
    assert counters["overreach"] == 1 and A.codex_ok(counters)


def test_X4_the_kill_FIRES_when_the_reviewer_passes_the_planted_claim(bundle):
    """The row this whole subcommand exists for: a reviewer that calls a planted causation
    SUPPORTED has not been shown to catch a real one."""
    mutated, _ = A.write_mutation(bundle["review"], 1)
    _rc, counters, offences = _graded(bundle, mutate=1, review=mutated)
    assert counters["mutation_not_flagged"] == 1, (counters, offences)
    assert not A.codex_ok(counters)
    assert any("planted overreach" in o for o in offences), offences


def test_the_kill_also_fires_when_the_mutated_citations_row_is_missing(bundle):
    mutated, _ = A.write_mutation(bundle["review"], 1)
    _rc, counters, _o = _graded(bundle, "--behaviour", "drop-n:1", mutate=1, review=mutated)
    assert counters["mutation_not_flagged"] == 1 and counters["citations_unreviewed"] == 1


# ── the CLI ────────────────────────────────────────────────────────────────────────────────


def _cli(*args):
    return subprocess.run([sys.executable, str(ACCEPT), *[str(a) for a in args]],
                          capture_output=True, text=True, cwd=str(SCRIPTS),
                          env={**_env(), "PYTHONUTF8": "1"})


def _env():
    import os

    e = dict(os.environ)
    e["PYTHONPATH"] = str(SCRIPTS / "pipeline")
    return e


def test_the_cli_prepare_mode_writes_the_mutation_and_exits_0(bundle):
    r = _cli("codex", "--review", bundle["review"], "--context", bundle["context"], "--mutate", 1)
    assert r.returncode == 0, r.stderr
    assert Path(str(bundle["review"]) + A.MUTATED_SUFFIX).exists()


def test_the_cli_grades_a_report_and_prints_named_counters(bundle):
    _rc, _c, _o = _graded(bundle)
    r = _cli("codex", "--review", bundle["review"], "--context", bundle["context"],
             "--report", bundle["out"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "citations_unreviewed=0" in r.stdout and "hash_mismatch=0" in r.stdout


def test_the_cli_exits_1_when_a_gate_counter_fires(bundle):
    _rc, _c, _o = _graded(bundle, "--behaviour", "drop-n:2")
    r = _cli("codex", "--review", bundle["review"], "--context", bundle["context"],
             "--report", bundle["out"])
    assert r.returncode == 1 and "citations_unreviewed=1" in r.stdout


def test_the_cli_refuses_to_grade_a_mutation_it_has_not_prepared(bundle):
    r = _cli("codex", "--review", bundle["tmp"] / "absent.md", "--context", bundle["context"],
             "--report", bundle["out"], "--mutate", 1)
    assert r.returncode == 2, (r.stdout, r.stderr)
