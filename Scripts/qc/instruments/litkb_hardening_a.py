r"""builder-A's counters and fires for `litkb_acceptance.py hardening` (S4.5; brief-CONTRACTS.md
"Counters and fires").

    # the replay summary these counters read is written by
    LITKB_TEST_DB=litkb_test_wN PYTHONUTF8=1 PYTHONPATH=pipeline \
        py -3.12 qc/instruments/litkb_acceptance.py hardening --replay --manifest <m> --db litkb_test_wN

THE MODULE CONTRACT (fixed by the orchestrator so six builders could work in parallel): `COUNTERS` and
`REPORTED` map a counter name to `fn(conn, manifest) -> int`, `FIRES` maps a fire name to
{"counter": <counter>, "run": fn(conn, arm, workdir) -> int}. `hardening --manifest` loads every
`qc/instruments/litkb_hardening_*.py` BY PATH (qc/instruments is not a package); `hardening --fire`
runs a fire's `control` arm and its `known_bad` arm on a freshly reset worker database each and prints
FIRED only when the control is inside the counter's bound and the known-bad outside it.

WHAT THIS MODULE COUNTS (docs/SCHEMAS.md, "S4.5 builder A", is the one home of each definition):

  unvalidated_items       of the nine rung classes of S4.5 decision D13 (:data:`REFEREE_CLASSES`,
                          the classes' one home), those whose referee report the manifest does not
                          name, or names but is not on disk, or is on disk with no line matching
                          :data:`FIRED_LINE` (`fired: <counter>=<value> on <input>`).
  stage_b_rungs_unmeasured  of the Stage B routes (`litkb.acquire.policy.STAGE_OF`), a rung the
                          ladder's registry holds (`litkb.acquire.run.RUNGS`) with no :data:`YIELD_LINE`
                          (`yield: <route>=<converted>/<asked>`), and a route no rung registers with
                          no :data:`NOT_BUILT_LINE` (`not-built: <route> <reason>`), in the
                          LITKB_LADDER1 report the manifest names (:func:`stage_b_rungs`). A measured
                          zero (`=0/35`) IS measured. A rung the registry marks `metadata_only` (it yields
                          identifiers, never a file) may answer with an :data:`IDENTIFIERS_LINE`
                          (`identifiers: <route>=<works gaining>/<asked>`) instead (S4.5 decision D19).
  replay_rows_graded_against_stubs  replayed register rows whose `acquirer` column is `stub` — the
                          synthetic `_acquirer_stub` return, read off what the replay RAN, not off
                          what the register asks for.
  replay_network_calls    every connect or lookup the replay's socket guard counted (refused or not).
  cassettes_stale         entries of the rows the replay REPLAYED that it never requested + requests
                          the replay made that the index lacks (misses), over every cassette it used
                          (the run's index and each CONSTRUCTED row's own), both listed in the
                          summary; UNREAD when the manifest's recorded index is not on disk. The rows
                          the live pass recorded and the replay never began are REPORTED apart
                          (`cassette_rows_not_replayed`), never counted here (auditor-A round 1, F1).
  replay_rows_disagreeing replayed rows whose (state, reason) is not the register's, whose hunt
                          raised or missed the cassette, or that are absent from the replay CSV —
                          the `edges` grader's own counters over the replay (NOT a (b) name of the
                          plan: it is the gate the plan's (c) "the replay disagrees with the register
                          -> RED" needs, and the report says so).

The four replay counters read the REPLAY SUMMARY the manifest names (`replay_report`), and refuse it
(UNREAD, which fails the gate) when it was made from a register or a cassette index that is not the
one on disk now: a summary of a different recording grades a different question. Also refused: a
summary edited after the replay wrote it (`summary_sha256`), and an index that is not the one the
live pass finished recording (the run driver's recording report, the manifest's `recording_report`).
"""
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
FIXTURES = SCRIPTS / "qc" / "fixtures"

#: The rung classes of S4.5 decision D13 (the plan's (b): "rung classes — the substrate, the
#: vocabulary, Stage A, Stage B, Stage C, the Sci-Hub part 1, Stage E, replay, the bad-file read").
#: Their ONE home; `hardening --freeze` promises a referee report path for each from here.
REFEREE_CLASSES = ("substrate", "vocabulary", "stage-a", "stage-b", "stage-c", "scihub-1", "stage-e",
                   "replay", "badfile-read")

#: A referee report's evidence line (the plan's (b), `unvalidated_items`).
FIRED_LINE = re.compile(r"^fired: \S+=\S+ on .+", re.M)

#: A Stage B rung's measured yield in the LITKB_LADDER1 report: `yield: <route>=<converted>/<asked>`,
#: whole line, integers, converted <= asked. docs/SCHEMAS.md holds the grammar.
YIELD_LINE = re.compile(r"^yield: (?P<route>[a-z0-9_-]+)=(?P<converted>\d+)/(?P<asked>\d+)[ \t]*$", re.M)

#: A Stage B route this session did NOT build: `not-built: <route> <reason>` in the same report
#: (brief-CONTRACTS.md, the 2026-09-23 amendment: a rung that cannot be built keyless is recorded
#: NOT-BUILT with evidence). The reason is required: a bare `not-built: core` states nothing.
NOT_BUILT_LINE = re.compile(r"^not-built: (?P<route>[a-z0-9_-]+)[ \t]+(?P<reason>\S[^\n]*)$", re.M)

#: A METADATA-ONLY Stage B rung's measure (S4.5 decision D19: "`identifiers: <route>=<works gaining>/<asked>` for
#: a metadata-only rung (opencitations, ncbi-idconv); the counter accepts either for a rung the registry marks
#: metadata-only"): whole line, integers, gaining <= asked, asked >= 1 — the yield line's rules. The registry's
#: mark is the rung's `metadata_only` attribute (builder C2a's `run.Rung` field; a rung without it is a PDF rung).
#: Integrator-w2.
IDENTIFIERS_LINE = re.compile(r"^identifiers: (?P<route>[a-z0-9_-]+)=(?P<converted>\d+)/(?P<asked>\d+)[ \t]*$",
                              re.M)

REPLAY_SUMMARY_KIND = "litkb-hardening-replay"

#: The CONSTRUCTED register and cassette the replay fires run (qc/fixtures, named constructed).
CONSTRUCTED_REGISTER = FIXTURES / "litkb_hardening_constructed_register.json"


class Unread(LookupError):
    """A counter that cannot be read from what the manifest names. `hardening` prints it `unread`,
    and an unread GATED counter fails the exit — never a silent pass."""


def _acceptance():
    spec = importlib.util.spec_from_file_location(
        "litkb_acceptance", SCRIPTS / "qc" / "instruments" / "litkb_acceptance.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _edge_run():
    spec = importlib.util.spec_from_file_location(
        "litkb_edge_run", SCRIPTS / "qc" / "instruments" / "litkb_edge_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _resolve(manifest, p):
    """A manifest path: absolute as given, else relative to the manifest's repo root."""
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else Path(manifest.get("repo") or SCRIPTS.parent) / q


def _content_sha(path):
    """CRLF-folded content hash (litkb_acceptance._register_sha256's rule) for authored text."""
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ── unvalidated_items ────────────────────────────────────────────────────────────────────────

def unvalidated_detail(manifest):
    """[(class, why)] for every rung class that is not validated."""
    reports = manifest.get("referee_reports") or {}
    out = []
    for cls in REFEREE_CLASSES:
        p = _resolve(manifest, reports.get(cls))
        # BEGIN guard: a rung class with no named, present, fired referee report is unvalidated
        if p is None:
            out.append((cls, "the manifest names no referee report"))
        elif not p.is_file():
            out.append((cls, f"{p} is not on disk"))
        elif not FIRED_LINE.search(p.read_text(encoding="utf-8", errors="replace")):
            out.append((cls, f"{p} has no `fired: <counter>=<value> on <input>` line"))
        # END guard: a rung class with no named, present, fired referee report is unvalidated
    return out


def unvalidated_items(conn, manifest):
    return len(unvalidated_detail(manifest))


# ── stage_b_rungs_unmeasured ─────────────────────────────────────────────────────────────────

def yields(text, line=YIELD_LINE):
    """{route: (converted, asked)} of every well-formed yield line; a line whose converted exceeds
    its asked is not a measurement and is left out, and neither is a line that asked NOBODY
    (`=0/0`): the plan asks every Stage B rung of EVERY `no-oa-copy` row, so a rung that was asked of
    no row was not measured, whatever the line says (auditor-A round 1, F3). A measured zero
    (`=0/35`) is still measured. `line` = :data:`IDENTIFIERS_LINE` reads the identifiers lines by the same
    rules (integrator-w2, S4.5 decision D19)."""
    got = {}
    for m in line.finditer(text or ""):
        conv, asked = int(m["converted"]), int(m["asked"])
        # BEGIN guard: a yield line that asked no row is not a measurement
        if conv <= asked and asked >= 1:
            got[m["route"]] = (conv, asked)
        # END guard: a yield line that asked no row is not a measurement
    return got


def not_built(text):
    """{route: reason} of every well-formed not-built line."""
    return {m["route"]: m["reason"].strip() for m in NOT_BUILT_LINE.finditer(text or "")}


def stage_b_rungs(rungs=None):
    """(built, unbuilt): the Stage B routes REGISTERED in the ladder's rung registry
    (`litkb.acquire.run.RUNGS`), and the Stage B routes of the route vocabulary no rung registers — both
    read from builder C1a's one home (`litkb.acquire.policy.STAGE_OF`, `ROUTES_ALL`), never a list kept
    here (brief-CONTRACTS.md amendment 2026-09-23; seam integrator-w1, A x C1a). A rung is registered by
    importing its module (`run.register`), so a rung that `litkb.acquire.run` does not import is UNBUILT
    here, and the report must then say `not-built:` for it — fail closed."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    rungs = R.RUNGS if rungs is None else rungs
    built = [r.route for r in rungs if P.STAGE_OF.get(r.route) == "B"]
    unbuilt = [r for r in P.ROUTES_ALL if P.STAGE_OF.get(r) == "B" and r not in built]
    return built, unbuilt


def metadata_only_routes(rungs=None):
    """The Stage B routes whose registered rung is marked `metadata_only` (it yields identifiers, never a file:
    S4.5 decision D19's opencitations and ncbi-idconv). Read off the REGISTRY, like `stage_b_rungs`; a rung object
    without the attribute is a PDF-yielding rung (integrator-w2)."""
    from litkb.acquire import policy as P
    from litkb.acquire import run as R

    rungs = R.RUNGS if rungs is None else rungs
    return {r.route for r in rungs if P.STAGE_OF.get(r.route) == "B" and getattr(r, "metadata_only", False)}


def stage_b_unmeasured_detail(manifest, rungs=None):
    """The Stage B routes the report leaves unmeasured, built ones first: a BUILT rung with no yield
    line, and an UNBUILT route with no not-built line. A yield line for an unbuilt route, or a not-built
    line for a built rung, answers neither question. A built rung the registry marks metadata-only is
    measured by a yield line OR an identifiers line (S4.5 decision D19); a PDF rung's identifiers line
    answers nothing."""
    p = _resolve(manifest, manifest.get("report_path"))
    text = p.read_text(encoding="utf-8", errors="replace") if p is not None and p.is_file() else ""
    got, excused = yields(text), not_built(text)
    # BEGIN guard: a metadata-only Stage B rung is measured by the identifiers it gained
    meta = metadata_only_routes(rungs)
    got = {**{r: v for r, v in yields(text, IDENTIFIERS_LINE).items() if r in meta}, **got}
    # END guard: a metadata-only Stage B rung is measured by the identifiers it gained
    built, unbuilt = stage_b_rungs(rungs)
    # BEGIN guard: a Stage B rung with no yield line in the report is unmeasured
    return [r for r in built if r not in got] + [r for r in unbuilt if r not in excused]
    # END guard: a Stage B rung with no yield line in the report is unmeasured


def stage_b_rungs_unmeasured(conn, manifest):
    return len(stage_b_unmeasured_detail(manifest))


# ── the replay summary, and the four counters read from it ───────────────────────────────────

def build_replay_summary(conn, *, register, register_path, db, workdir, cassette=None, guard=None,
                         index_path=None, out_csv=None, constructed_path=None):
    """Replay every graded row of `register` on the worker database `conn` is on, inside `guard`,
    with `cassette` (replay mode) behind every `ladder` row, grade it with the `edges` grader, and
    return the summary the replay counters read. ONE function for `hardening --replay` and for the
    fires, so a fire measures exactly what the gate measures.

    THE STALENESS DIFF reads EVERY cassette a row replayed from — the run's recorded index and each
    row's own (a CONSTRUCTED fixture) — and each only over the rows this replay began (auditor-A
    round 1, F1: the live pass records every manifest row into one index, the replay grades the
    register, so an entry of a row nobody replayed is listed in `rows_not_replayed`, a REPORTED
    count, never in `stale`). `constructed_path` names the CONSTRUCTED register whose rows
    `register` carries beside the edge register's (`hardening --replay`), hashed like the register."""
    E = _edge_run()
    A = _acceptance()
    workdir = Path(workdir)
    out_csv = Path(out_csv or workdir / "replay.csv")
    used = [cassette] if cassette is not None else []
    E.run_replay(register, out_csv, db=db, tmp=str(workdir), conn=conn, cassette=cassette, guard=guard,
                 cassettes_used=used)
    rows = E.rows_of(register)
    manifest = {"kind": "litkb-edges", "db": db, "db_migration_tip": None,
                "rows": [{"id": r["id"], "mode": E.resolve_mode(r, None)} for r in rows],
                "run_csv": str(out_csv), "replay_csv": str(out_csv)}
    counters, offences = A.check_edges(manifest, rows=rows, csv_path=str(out_csv), replay=True)
    written = E.existing_rows(out_csv)
    stale = {"unplayed": [], "misses": []}
    # BEGIN guard: the staleness diff reads every cassette the replay used, the rows' own included
    for cas in used:
        st = cas.stale()
        stale["unplayed"] += [dict(u, index=cas.index.name) for u in st["unplayed"]]
        stale["misses"] += [dict(m, index=cas.index.name) for m in st["misses"]]
    # END guard: the staleness diff reads every cassette the replay used, the rows' own included
    not_replayed = cassette.rows_not_replayed() if cassette is not None else []
    # every row's misses meet in the CSV too (a miss the CSV counted and a cassette ledger lost
    # would otherwise vanish); `count_stale` reads the larger of the two
    row_misses = sum(int(r.get("cassette_misses") or 0) for r in written)
    summary = {
        "kind": REPLAY_SUMMARY_KIND,
        "db": db,
        "register": str(register_path) if register_path else None,
        "register_sha256": _content_sha(register_path) if register_path else None,
        "constructed_register": str(constructed_path) if constructed_path else None,
        "constructed_register_sha256": _content_sha(constructed_path) if constructed_path else None,
        "cassette_index": str(index_path) if index_path else None,
        "index_sha256": _index_sha(index_path),
        "replay_csv": str(out_csv),
        "rows": [{k: r.get(k, "") for k in ("row_id", "acquirer", "network_calls", "cassette_misses",
                                            "expected_state", "expected_reason", "observed_state",
                                            "observed_reason", "traceback", "message")}
                 for r in written],
        "edges": counters,
        "edges_offences": offences,
        "network_calls": len(guard.blocked) if guard is not None else None,
        "network_attempts": [{k: a[k] for k in ("host", "port", "how", "refused")}
                             for a in (guard.blocked if guard is not None else [])],
        "stale": stale,
        "rows_not_replayed": not_replayed,
        "row_cassette_misses": row_misses,
    }
    summary["summary_sha256"] = summary_sha(summary)
    return summary


def summary_sha(obj, key="summary_sha256"):
    """sha256 of a JSON document's content without its own self-hash field (sorted keys, compact
    separators, UTF-8, `default=str`): `litkb_acceptance._canonical_sha`'s rule, kept here so the
    run driver's recording report and the replay summary share it."""
    body = {k: v for k, v in obj.items() if k != key}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def _index_sha(path):
    from litkb import cassette as C

    return C.index_sha256(path) if path else None


def count_stubs(summary):
    # BEGIN guard: a replayed row answered by the synthetic acquirer is counted
    return sum(1 for r in summary["rows"] if r.get("acquirer") == "stub")
    # END guard: a replayed row answered by the synthetic acquirer is counted


def count_network(summary):
    n = summary.get("network_calls")
    if n is None:
        raise Unread("the replay ran with no socket guard, so its network use was not measured")
    return int(n)


def count_stale(summary):
    # BEGIN guard: a staleness diff of a recording that does not exist is unread, never 0
    # A replay whose manifest names a recorded index that is not on disk replayed NO recording, so
    # "nothing is stale" would be a vacuous zero (auditor-A round 1, F1: the builder's own trial read
    # `cassettes_stale=0` for exactly this reason). A summary that names no index at all (the fires'
    # CONSTRUCTED rows, each on its own fixture cassette) is graded on what it did replay.
    if summary.get("cassette_index") and summary.get("index_sha256") is None:
        raise Unread(f"the recorded index {summary.get('cassette_index')} does not exist: the replay "
                     "replayed no recording, so its staleness is not measured (record it first)")
    # END guard: a staleness diff of a recording that does not exist is unread, never 0
    s = summary.get("stale") or {}
    misses = len(s.get("misses") or [])
    # every cassette's misses are in `stale`; the CSV's per-row count is the cross-check
    misses = max(misses, int(summary.get("row_cassette_misses") or 0))
    return len(s.get("unplayed") or []) + misses


def count_rows_not_replayed(summary):
    # BEGIN guard: rows not replayed of a recording that does not exist are unread, never 0
    # (auditor-A round 2, F5: with no recording there is no row to list, and 0 would read as "the
    # replay covered every recorded row")
    if summary.get("cassette_index") and summary.get("index_sha256") is None:
        raise Unread(f"the recorded index {summary.get('cassette_index')} does not exist: no recorded row "
                     "to compare the replay against (record it first)")
    # END guard: rows not replayed of a recording that does not exist are unread, never 0
    return len(summary.get("rows_not_replayed") or [])


def count_disagreeing(summary):
    e = summary.get("edges") or {}
    # BEGIN guard: a replay that disagrees with the register is counted
    return (int(e.get("state_or_reason_mismatches") or 0) + int(e.get("tracebacks") or 0)
            + int(e.get("skipped") or 0))
    # END guard: a replay that disagrees with the register is counted


def load_recording(manifest):
    """The run driver's recording report the manifest names (`recording_report`), REFUSED (Unread) when
    the manifest names none, when it is not on disk, and when it was edited after the run driver wrote
    it (its `recording_sha256`): an edited recording report is not the live pass's word, whatever its
    `index_sha256` now says (auditor-A round 2, F2 — the self-hash half of the check was untested)."""
    rec = manifest.get("recording_report")
    rp = _resolve(manifest, rec)
    if rp is None or not rp.is_file():
        raise Unread(f"no recording report at {rp} (the run driver writes it at the end of a RECORD pass)")
    r = json.loads(rp.read_text(encoding="utf-8"))
    # BEGIN guard: a recording report edited after the run driver wrote it is refused
    if r.get("recording_sha256") != summary_sha(r, "recording_sha256"):
        raise Unread(f"the recording report {rec} was itself edited after the run driver wrote it "
                     "(recording_sha256 does not match its content): it is not the live pass's word")
    # END guard: a recording report edited after the run driver wrote it is refused
    return r


def load_summary(manifest):
    """The replay summary the manifest names, REFUSED (Unread) when absent; when it was edited after
    the replay wrote it (its `summary_sha256`); when it was made from a register, a CONSTRUCTED
    register or an index that is not the one on disk now; and when that index is not the one the live
    pass finished recording (the manifest's `recording_report`, written by the run driver, itself
    refused when edited — :func:`load_recording`)."""
    p = _resolve(manifest, manifest.get("replay_report"))
    if p is None or not p.is_file():
        raise Unread(f"no replay summary at {p} (run `hardening --replay` after the recording)")
    s = json.loads(p.read_text(encoding="utf-8"))
    if s.get("kind") != REPLAY_SUMMARY_KIND:
        raise Unread(f"{p} is not a {REPLAY_SUMMARY_KIND} summary")
    # BEGIN guard: a replay summary edited after the replay wrote it is refused
    if s.get("summary_sha256") != summary_sha(s):
        raise Unread(f"{p} was edited after `hardening --replay` wrote it (summary_sha256 does not match "
                     "its content); replay again")
    # END guard: a replay summary edited after the replay wrote it is refused
    reg = (manifest.get("register") or {}).get("path")
    if reg and _content_sha(_resolve(manifest, reg)) != s.get("register_sha256"):
        raise Unread(f"{p} replayed a register that is not {reg} as it is on disk now; replay again")
    con = (manifest.get("constructed_register") or {}).get("path")
    # BEGIN guard: a replay summary of a CONSTRUCTED register that changed since is refused
    if con and _content_sha(_resolve(manifest, con)) != s.get("constructed_register_sha256"):
        raise Unread(f"{p} replayed a CONSTRUCTED register that is not {con} as it is on disk now; "
                     "replay again")
    # END guard: a replay summary of a CONSTRUCTED register that changed since is refused
    idx = (manifest.get("cassette_index") or {}).get("path")
    if idx and _index_sha(_resolve(manifest, idx)) != s.get("index_sha256"):
        raise Unread(f"{p} replayed a cassette index that is not {idx} as it is on disk now; replay again")
    # BEGIN guard: the replayed index is the one the live pass finished recording
    rec = manifest.get("recording_report")
    if rec and s.get("index_sha256") is not None:
        rp = _resolve(manifest, rec)
        if rp is None or not rp.is_file():
            raise Unread(f"the recorded index exists but no recording report ({rec}) ties it to the live "
                         "pass: an index the run driver did not finish is not the recording")
        r = load_recording(manifest)
        if r.get("index_sha256") != s.get("index_sha256"):
            raise Unread(f"the index {idx} that {p.name} replayed is not the index the live pass "
                         f"recorded ({rec} says {str(r.get('index_sha256'))[:12]}): it was changed after "
                         "the recording")
    # END guard: the replayed index is the one the live pass finished recording
    return s


def replay_rows_graded_against_stubs(conn, manifest):
    return count_stubs(load_summary(manifest))


def replay_network_calls(conn, manifest):
    return count_network(load_summary(manifest))


def cassettes_stale(conn, manifest):
    return count_stale(load_summary(manifest))


def replay_rows_disagreeing(conn, manifest):
    return count_disagreeing(load_summary(manifest))


# ── reported ─────────────────────────────────────────────────────────────────────────────────

def replay_rows_pending_recording(conn, manifest):
    """Register rows carrying a `pending_recording` marker (on the stub until the live pass records
    them; E16 cannot be recorded live at all). REPORTED."""
    reg = (manifest.get("register") or {}).get("path")
    p = _resolve(manifest, reg)
    if p is None or not p.is_file():
        raise Unread(f"no register at {p}")
    rows = json.loads(p.read_text(encoding="utf-8")).get("rows") or []
    return sum(1 for r in rows if ((r.get("replay") or {}).get("routes") or {}).get("pending_recording"))


def cassette_rows_not_replayed(conn, manifest):
    """Row tags the live pass recorded that the replay never began (the run rows the register does
    not carry). REPORTED, never gated: `cassettes_stale` is scoped to the rows the replay replayed
    (auditor-A round 1, F1), and this is the other half of the index, said out loud."""
    return count_rows_not_replayed(load_summary(manifest))


def cassette_record_errors(conn, manifest):
    """Recordings the live pass could not write (the recording report's `record_errors`: a disk error, an
    unwritable store). REPORTED: a lost recording of a REGISTER row surfaces anyway as a replay MISS,
    but one of the other run rows would be invisible in the grade line without it (auditor-A round 2,
    F5). UNREAD when there is no recording report (or it was edited)."""
    return len(load_recording(manifest).get("record_errors") or [])


def cassette_interactions(conn, manifest):
    """Live interactions in the recorded index (latest take per row). REPORTED."""
    from litkb import cassette as C

    p = _resolve(manifest, (manifest.get("cassette_index") or {}).get("path"))
    if p is None or not p.is_file():
        return 0
    return len(C.Cassette(p, "replay", bodies=Path(p).parent).entries)


COUNTERS = {
    "unvalidated_items": unvalidated_items,
    "stage_b_rungs_unmeasured": stage_b_rungs_unmeasured,
    "replay_rows_graded_against_stubs": replay_rows_graded_against_stubs,
    "replay_network_calls": replay_network_calls,
    "cassettes_stale": cassettes_stale,
    "replay_rows_disagreeing": replay_rows_disagreeing,
}

REPORTED = {
    "replay_rows_pending_recording": replay_rows_pending_recording,
    "cassette_interactions": cassette_interactions,
    "cassette_rows_not_replayed": cassette_rows_not_replayed,
    "cassette_record_errors": cassette_record_errors,
}


def _stale_lines(conn, manifest):
    s = load_summary(manifest)
    st = s.get("stale") or {}
    return ([f"unplayed row={u['row']} seq={u['seq']} {u['url']}" for u in st.get("unplayed") or []]
            + [f"miss row={m['row']} {m['url']} ({m['why']})" for m in st.get("misses") or []])


#: What `hardening --manifest` lists on stderr beside a non-zero counter (an extension of the module
#: contract: `DETAILS[name] = fn(conn, manifest) -> [line]`; a module may omit it).
DETAILS = {
    "unvalidated_items": lambda conn, m: [f"{cls}: {why}" for cls, why in unvalidated_detail(m)],
    "stage_b_rungs_unmeasured": lambda conn, m: [
        f"no `yield: {r}=<converted>/<asked>` line (a registered Stage B rung)" if r in stage_b_rungs()[0]
        else f"no `not-built: {r} <reason>` line (no rung registers {r})" for r in stage_b_unmeasured_detail(m)],
    "cassettes_stale": _stale_lines,
    "cassette_rows_not_replayed": lambda conn, m: [
        f"recorded, not replayed: row={r['row']} entries={r['entries']}"
        for r in load_summary(m).get("rows_not_replayed") or []],
    "replay_rows_graded_against_stubs": lambda conn, m: [
        f"row {r['row_id']} graded by the synthetic acquirer" for r in load_summary(m)["rows"]
        if r.get("acquirer") == "stub"],
    "cassette_record_errors": lambda conn, m: [
        f"a recording the live pass could not write: {e}" for e in load_recording(m).get("record_errors") or []],
}


# ── fires ────────────────────────────────────────────────────────────────────────────────────
#
# Each `run(conn, arm, workdir)` builds its input in `workdir`, applies the known-bad IN-PROCESS for
# arm == "known_bad" (a copy edited, a patch installed, a dict flipped) and returns the counter's value
# computed by the SAME function the gate uses. Nothing here edits a tracked file.

def _report_files(workdir, drop=None):
    """Nine referee reports, each carrying a fired line, in `workdir`; -> the manifest."""
    workdir = Path(workdir)
    reports = {}
    for cls in REFEREE_CLASSES:
        p = workdir / f"LITKB_REFEREE_S45_{cls.upper()}_CONSTRUCTED.md"
        p.write_text(f"# CONSTRUCTED referee report ({cls})\n\nfired: some_counter=1 on a constructed input\n",
                     encoding="utf-8")
        reports[cls] = str(p)
    if drop:
        reports.pop(drop)
    return {"repo": str(workdir), "referee_reports": reports}


def fire_referee_report_dropped(conn, arm, workdir):
    """CONSTRUCTED: nine referee reports, each with a fired line; the known-bad drops one class's
    report from the manifest (the plan's (c): `unvalidated_items=1`)."""
    manifest = _report_files(workdir, drop="stage-c" if arm == "known_bad" else None)
    return unvalidated_items(conn, manifest)


def _ladder_report(workdir, drop=None):
    """A CONSTRUCTED report with a yield line (a measured zero) for every REGISTERED Stage B rung and a
    not-built line for every other Stage B route; `drop` leaves that route's line out."""
    built, unbuilt = stage_b_rungs()
    p = Path(workdir) / "LITKB_LADDER1_CONSTRUCTED.md"
    lines = ["# CONSTRUCTED ladder report", ""]
    lines += [f"yield: {r}=0/35" for r in built if r != drop]
    lines += [f"not-built: {r} CONSTRUCTED reason" for r in unbuilt if r != drop]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"repo": str(workdir), "report_path": str(p)}


def fire_yield_line_deleted(conn, arm, workdir):
    """CONSTRUCTED: a report that measures every Stage B route (a yield line per registered rung, a
    not-built line per other Stage B route); the known-bad deletes the YIELD line of the first registered
    Stage B rung (the plan's (c): "a Stage B rung's yield line deleted from the report" ->
    `stage_b_rungs_unmeasured=1`), or a not-built line if no Stage B rung is registered at all."""
    built, unbuilt = stage_b_rungs()
    drop = (built or unbuilt)[0] if arm == "known_bad" else None
    return stage_b_rungs_unmeasured(conn, _ladder_report(workdir, drop=drop))


def _constructed_register():
    return json.loads(CONSTRUCTED_REGISTER.read_text(encoding="utf-8"))


def _replay_constructed(conn, workdir, register, *, guard_patch=None):
    """Replay a (possibly mutated) constructed register inside a guard that allows nothing."""
    import contextlib

    from litkb import cassette as C

    guard = C.SocketGuard(allow_hosts=(), label="hardening replay guard")
    with (guard_patch or contextlib.nullcontext()):
        return build_replay_summary(conn, register=register, register_path=None,
                                    db=conn.info.dbname, workdir=workdir, guard=guard)


def fire_cassette_403_edited_to_200(conn, arm, workdir):
    """CONSTRUCTED: the constructed row replays blocked/403 through the real ladder. The known-bad
    edits a COPY of its cassette so every recorded 403 reads 200 (the plan's (c): "a cassette's 403
    edited to 200 (CONSTRUCTED) -> the replay disagrees with the register -> RED")."""
    reg = _constructed_register()
    if arm == "known_bad":
        src = FIXTURES / reg["rows"][0]["replay"]["routes"]["cassette"]
        dst = Path(workdir) / "edited" / "index.jsonl"
        dst.parent.mkdir(parents=True, exist_ok=True)
        lines = src.read_bytes().splitlines()
        out = [lines[0]]
        for ln in lines[1:]:
            e = json.loads(ln)
            if e["response"]["status"] == 403:
                e["response"]["status"] = 200
            out.append(json.dumps(e, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        dst.write_bytes(b"\n".join(out) + b"\n")
        reg = copy.deepcopy(reg)
        reg["rows"][0]["replay"]["routes"]["cassette"] = str(dst)
    return count_disagreeing(_replay_constructed(conn, workdir, reg))


class _StraySocket:
    """The known-bad of `socket_opened_during_replay`: wrap the Sci-Hub route so it first opens a TCP
    connection, then runs the real route. The target is a listener THIS process opened on loopback —
    so no packet can leave the machine even with the guard's refusal mutated away — and the replay's
    guard allows nothing, loopback included, so the connect is exactly what it must count."""

    def __enter__(self):
        import socket
        from unittest import mock

        from litkb.acquire import scihub as S

        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        port = self.listener.getsockname()[1]
        real = S.fetch_scihub
        self.opened = 0

        def fetch(*a, **kw):
            # ONE stray socket per replay, whatever the number of rows it crosses (the CONSTRUCTED
            # register holds three since fix round 2): the plan's (c) reads `replay_network_calls=1`
            if not self.opened:
                self.opened += 1
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.settimeout(2)
                    s.connect(("127.0.0.1", port))
                except OSError:
                    pass            # refused by the guard: the route carries on, the count stays
                finally:
                    s.close()
            return real(*a, **kw)
        self.patch = mock.patch("litkb.acquire.scihub.fetch_scihub", fetch)
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()
        self.listener.close()
        return False


def fire_socket_opened_during_replay(conn, arm, workdir):
    """CONSTRUCTED: the constructed row replays with no socket; the known-bad opens one mid-route
    (the plan's (c): "a socket opened during a replay -> refused, replay_network_calls=1")."""
    patch = _StraySocket() if arm == "known_bad" else None
    return count_network(_replay_constructed(conn, workdir, _constructed_register(), guard_patch=patch))


def fire_synthetic_acquirer_reinstated(conn, arm, workdir):
    """CONSTRUCTED: the constructed row replays through the real ladder; the known-bad puts it back on
    the synthetic acquirer with the answer the ladder gave (the plan's (c): "the synthetic acquirer
    return reinstated -> replay_rows_graded_against_stubs>0")."""
    reg = _constructed_register()
    if arm == "known_bad":
        reg = copy.deepcopy(reg)
        reg["rows"][0]["replay"]["routes"] = {
            "kind": "acquirer", "outcome": "not-acquired",
            "route_detail": [{"route": "scihub", "status": "blocked", "codes": [403], "exception": ""}]}
    return count_stubs(_replay_constructed(conn, workdir, reg))


FIRES = {
    "referee_report_dropped": {"counter": "unvalidated_items", "run": fire_referee_report_dropped},
    "yield_line_deleted": {"counter": "stage_b_rungs_unmeasured", "run": fire_yield_line_deleted},
    "cassette_403_edited_to_200": {"counter": "replay_rows_disagreeing",
                                   "run": fire_cassette_403_edited_to_200},
    "socket_opened_during_replay": {"counter": "replay_network_calls",
                                    "run": fire_socket_opened_during_replay},
    "synthetic_acquirer_reinstated": {"counter": "replay_rows_graded_against_stubs",
                                      "run": fire_synthetic_acquirer_reinstated},
}
