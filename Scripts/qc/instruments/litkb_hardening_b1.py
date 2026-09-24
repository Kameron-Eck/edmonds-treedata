r"""builder-B1's counters and fires for `litkb_acceptance.py hardening` (S4.5 item 1, the identifier model;
brief-CONTRACTS.md "Counters and fires").

THE MODULE CONTRACT (fixed by the orchestrator): `COUNTERS` / `REPORTED` map a counter name to
`fn(conn, manifest) -> int` on a READ-ONLY connection; `FIRES` maps a fire name to
{"counter": <name>, "run": fn(conn, arm, workdir) -> int} (an optional "bound" where the counter is not a gated
(b) name). `hardening --manifest` loads this file BY PATH; `hardening --fire` runs a fire's `control` arm and its
`known_bad` arm on a freshly reset worker database each. Every fire here is ALSO a pytest test
(qc/test_litkb_s45_identity.py) — the harness is the cold re-fire path, the test is the gate in `pytest qc`.

WHAT THIS MODULE COUNTS (docs/SCHEMAS.md, "S4.5 builder B1", is the one home of each definition):

  GATED
  relation_probe_rows            ANSWERED data rows (state `asserted` or `none_returned`) of the Crossref relation
                                 probe CSV the manifest names (`litkb_acq_probe_relation.csv`, written by
                                 qc/instruments/litkb_acq_probe_relation.py). `unanswered` rows (no 200 answer) are
                                 NOT a measurement and never count; the detail line reports them. A manifest that
                                 names no probe reads 0.
  key_derivation_crashes         rows of the run CSV (`run_csv`) ending `crashed` with reason `admit:CheckViolation`
                                 (the pre-S4.5 shape row 187 died in, survey-code §4.2) or `admit:KeyUnderivable`
                                 (make_key refusing by name). UNREAD when the manifest names no run CSV.
  crosswalk_rows_without_identifier  of the run's crosswalk-selected works (manifest `rows` whose `source` holds
                                 `crosswalk`; without `rows`, every crosswalk CSV row whose work holds no active
                                 file), those missing what the crosswalk probe says they should gain: its
                                 `s2_arxiv` as an `arxiv` identifier OR an asserted edge to that arXiv id (S2's
                                 ArXiv on a non-arXiv work is an EDGE — litkb-sibling-edition, harvest.from_s2);
                                 any `cr_isbn` as an `isbn` identifier; for each NON-CITATION `cr_relation_types`
                                 word, an asserted edge of THAT relation on the work (or its inverse pointing at
                                 it). The relation clause proves the edge's TYPE, never its target: the CSV holds
                                 relation words only (see `crosswalk_missing`). ALL-TIME (S4.5 decision D1).
  identifiers_without_provenance identifier_versions rows with `asserted_by` NULL. ALL-TIME: every row written
                                 before migration 0032 counts until the reviewed backfill
                                 (qc/instruments/litkb_identifier_provenance_backfill.py) fills it.
  conflicts_uncounted            conflict EVENTS with no resolution record (`conflict_events_uncounted`):
                                 litkb.identifier_claims rows `collided` (the unique index refused a claim the rule
                                 did not see), unresolved (outcome NULL), or `conflict` with no
                                 litkb.identifier_conflicts row; and conflict-resolution edges with no conflict row
                                 — deduplicated per (scheme, value, claiming work). Plus distinct-scheme
                                 (scheme, value_norm) pairs that two works' active versions hold (main's current
                                 version or a proposal) with no conflict row between them. ALL-TIME.
  nondistinct_schemes_in_unique_index  schemes the partial unique index `identifiers_active_scheme_value` covers
                                 that the registry says are NOT distinct, or that the plan names non-distinct
                                 (`isbn issn oai handle md5` — PLAN_NONDISTINCT, so flipping the registry row does
                                 not hide it); an index with no scheme predicate covers every registry scheme.
  REPORTED
  relation_edges_missing         works a relation probe row gives an asserted relation that hold no asserted
                                 work_relations edge (subject or target); 0 when no probe CSV is named.
  identifier_first_refusals      admissions (in the run's workstreams, after `frozen_at` when given) refused
                                 `duplicate-review` although their candidate carried an identifier of an
                                 `identity_strong` DISTINCT scheme — a violation of identifier-first (a type-scoped
                                 strong scheme is strong only for its types, which the candidate row does not carry).
  books_without_isbn             main works of type book or chapter holding no active isbn identifier.

`scope_workstream_ids` (a manifest key only a FIRE or a TEST sets — `hardening --freeze` never writes it)
narrows the three ALL-TIME database counters to rows written in those workstreams, so a fire's pytest twin can
run on the suite's shared worker database beside every other test's rows.

Every mechanism here is a RELAYED design (CLAUDE.md §3.4c), UNVALIDATED until an independent referee scores it.
"""
import csv
import json
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
FIXTURES = SCRIPTS / "qc" / "fixtures"

RELATION_PROBE = "litkb_acq_probe_relation.csv"
CROSSWALK_PROBE = "litkb_acq_probe_crosswalk.csv"
#: The plan's own non-distinct schemes (LITKB_WORKPLAN.md S4.5 item 1: "false for isbn issn oai handle md5").
PLAN_NONDISTINCT = ("isbn", "issn", "oai", "handle", "md5")
#: The CONSTRUCTED registry answers the fires replay (qc/fixtures; each record says CONSTRUCTED in its `_note`).
CONSTRUCTED = FIXTURES / "litkb_b1_constructed_registry.json"


class Unread(LookupError):
    """A counter that cannot be read from what the manifest names: `hardening` prints it `unread`."""


def _resolve(manifest, p):
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else Path(manifest.get("repo") or SCRIPTS.parent) / q


def _csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _probe(manifest, name):
    return _resolve(manifest, (manifest.get("probe_csvs") or {}).get(name))


def _scope(manifest, alias):
    """A SQL fragment and its params restricting `alias.workstream_id` to the fire/test scope, or nothing."""
    ids = manifest.get("scope_workstream_ids")
    if not ids:
        return "", []
    return f" AND {alias}.workstream_id = ANY(%s::uuid[])", [list(map(str, ids))]


# ── gated ───────────────────────────────────────────────────────────────────────────────────────────

#: The probe states that are a MEASUREMENT: Crossref answered, and its relation field held edges (`asserted`) or
#: nothing (`none_returned`, the third state). `unanswered` (no 200 answer — offline, blocked, a 429 storm, a
#: DataCite DOI) measures nothing and never counts (auditor-B1 F1: 466 dead requests read 466 and passed).
ANSWERED_STATES = ("asserted", "none_returned")


def relation_probe_rows(conn, manifest):
    p = _probe(manifest, RELATION_PROBE)
    # BEGIN guard: the relation probe counts the rows the probe wrote, and a probe never run reads 0
    if p is None or not p.is_file():
        return 0
    # END guard: the relation probe counts the rows the probe wrote, and a probe never run reads 0
    # BEGIN guard: only an ANSWERED probe row is a measurement
    return sum(1 for r in _csv(p) if r.get("state") in ANSWERED_STATES)
    # END guard: only an ANSWERED probe row is a measurement


def relation_probe_unanswered(conn, manifest):
    """The probe rows that are NOT counted (`unanswered`), for the counter's detail line."""
    p = _probe(manifest, RELATION_PROBE)
    if p is None or not p.is_file():
        return 0
    return sum(1 for r in _csv(p) if r.get("state") not in ANSWERED_STATES)


#: The run-CSV reasons a key-derivation crash ends in: the pre-S4.5 shape (a key CUT to 59 characters inside its
#: surname, refused by `works_key_check`: row 187, survey-code §4.2) and the S4.5 shape (`make_key` refusing by
#: name, `litkb.admit.front.KeyUnderivable`). Auditor-B1 F3: counting only the first was blind to the second.
KEY_CRASH_REASONS = ("admit:CheckViolation", "admit:KeyUnderivable")


def key_derivation_crashes(conn, manifest):
    p = _resolve(manifest, manifest.get("run_csv"))
    if p is None or not p.is_file():
        raise Unread(f"no run CSV at {manifest.get('run_csv')!r}: the run has not written it")
    # BEGIN guard: a key-derivation crash is either shape a key can fail in
    return sum(1 for r in _csv(p) if r.get("state") == "crashed" and r.get("reason") in KEY_CRASH_REASONS)
    # END guard: a key-derivation crash is either shape a key can fail in


def _crosswalk_population(conn, manifest):
    """[(csv row, work_id)] the crosswalk counter is over (see the module docstring)."""
    p = _probe(manifest, CROSSWALK_PROBE)
    if p is None or not p.is_file():
        raise Unread(f"the manifest names no {CROSSWALK_PROBE}")
    by_key = {r["key"]: r for r in _csv(p)}
    rows = manifest.get("rows")
    if rows is not None:
        keys = [r.get("key") for r in rows if "crosswalk" in (r.get("source") or []) and r.get("key")]
    else:
        have = {k for (k,) in conn.execute(
            "SELECT DISTINCT w.key FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id = f.work_id "
            "WHERE f.status = 'active'").fetchall()}
        keys = [k for k, r in by_key.items() if k not in have and r.get("doi")
                and any(r.get(c) for c in ("s2_arxiv", "cr_isbn", "cr_relation_types"))]
    out = []
    for k in keys:
        r = by_key.get(k)
        if r is None:
            continue
        hit = conn.execute("SELECT id FROM litkb.works WHERE key = %s", (k,)).fetchone()
        out.append((r, hit[0] if hit else None))
    return out


def crosswalk_missing(conn, manifest):
    """[(key, what is missing)] — the crosswalk counter's detail.

    WHAT EACH CLAUSE CAN AND CANNOT PROVE (Codex X4; auditor-B1 F15). The crosswalk CSV names VALUES for two
    columns and only TYPES for the third:
      * `s2_arxiv` — a value: the work must hold that arXiv id as an identifier, or an asserted edge whose target
        is that id (or its 10.48550 DOI). Proves the value arrived.
      * `cr_isbn` — values: the work must hold one of them as an `isbn` identifier. Proves a value arrived.
      * `cr_relation_types` — relation WORDS only (`has-preprint`, `is-part-of`, ...; the probe did not record
        the targets). For each non-citation word the work must carry an asserted edge of THAT relation
        (`harvest.relation_of(word)`) as its subject, or the inverse relation as its target. It proves an edge of
        the stated TYPE exists on the work; it CANNOT prove the edge points at the target Crossref meant — the
        CSV does not hold the target to compare with."""
    from litkb import identifiers as I
    from litkb.admit import harvest as H

    out = []
    for r, wid in _crosswalk_population(conn, manifest):
        if wid is None:
            out.append((r["key"], "no such work"))
            continue
        held = {(s, v) for s, v in conn.execute(
            "SELECT i.scheme, i.value_norm FROM litkb.identifiers i JOIN litkb.identifier_versions v "
            "ON v.identifier_id = i.id WHERE v.work_id = %s AND v.status = 'active' "
            "AND (v.version_id = i.current_version_id OR v.state = 'proposed')", (wid,)).fetchall()}
        edges = conn.execute(
            "SELECT target_scheme, target_value_norm, relation, work_id = %s FROM litkb.work_relations "
            "WHERE state = 'asserted' AND (work_id = %s OR target_work_id = %s)", (wid, wid, wid)).fetchall()
        targets = {(s, v) for s, v, _rel, _subject in edges}
        as_subject = {rel for _s, _v, rel, subject in edges if subject}
        as_target = {rel for _s, _v, rel, subject in edges if not subject}
        missing = []
        arx = I.norm("arxiv", r.get("s2_arxiv") or "")
        if arx and ("arxiv", arx) not in held and ("arxiv", arx) not in targets \
                and ("doi", I.ARXIV_DOI_PREFIX + arx) not in targets:
            missing.append(f"arxiv {arx}")
        isbns = {I.to_isbn13(x) for x in (r.get("cr_isbn") or "").split(";") if x.strip()} - {None}
        if isbns and not any(("isbn", x) in held for x in isbns):
            missing.append(f"isbn {sorted(isbns)}")
        types = [t for t in (r.get("cr_relation_types") or "").split(";") if t and H.relation_of(t) is not None]
        lacking = [t for t in types if H.relation_of(t) not in as_subject
                   and H.INVERSE.get(H.relation_of(t), H.relation_of(t)) not in as_target]
        if lacking:
            missing.append(f"relation {lacking}")
        if missing:
            out.append((r["key"], "; ".join(missing)))
    return out


def crosswalk_rows_without_identifier(conn, manifest):
    return len(crosswalk_missing(conn, manifest))


def identifiers_without_provenance(conn, manifest):
    sql, params = _scope(manifest, "v")
    return conn.execute("SELECT count(*) FROM litkb.identifier_versions v WHERE v.asserted_by IS NULL" + sql,
                        params).fetchone()[0]


def conflict_events_uncounted(conn, manifest):
    """[(scheme, value_norm, claiming work, why)] — the conflict EVENTS no resolution record answers (Codex X4:
    count attempted claims against durable resolutions, because a unique index keeps the duplicate itself from
    ever persisting). Two sources, deduplicated by (scheme, value_norm, claiming work):
      * `litkb.identifier_claims` rows whose outcome is `collided` (the unique index refused a claim the conflict
        rule did not see), NULL (a committed claim never resolved), or `conflict` with no identifier_conflicts
        row for that (value, claimant, holder);
      * conflict-resolution edges with no identifier_conflicts row."""
    s_c, p_c = _scope(manifest, "k")
    s_e, p_e = _scope(manifest, "e")
    rows = conn.execute(
        "SELECT k.scheme, k.value_norm, k.work_id, coalesce(k.outcome, 'unresolved') FROM litkb.identifier_claims k"
        " WHERE (k.outcome IS NULL OR k.outcome = 'collided'"
        "   OR (k.outcome = 'conflict' AND NOT EXISTS (SELECT 1 FROM litkb.identifier_conflicts c"
        "        WHERE c.scheme = k.scheme AND c.value_norm = k.value_norm AND c.claimed_by_work_id = k.work_id"
        "          AND c.held_by_work_id = k.held_by_work_id)))" + s_c +
        " UNION"
        " SELECT e.conflict_source, e.target_value_norm, e.work_id, 'edge without a conflict row'"
        "   FROM litkb.work_relations e WHERE e.asserted_by = 'conflict-resolution'"
        "    AND NOT EXISTS (SELECT 1 FROM litkb.identifier_conflicts c WHERE c.edge_id = e.id)" + s_e,
        p_c + p_e).fetchall()
    seen, out = set(), []
    for scheme, value, work, why in sorted(rows, key=lambda r: (r[0], r[1], str(r[2]), r[3])):
        if (scheme, value, work) not in seen:
            seen.add((scheme, value, work))
            out.append((scheme, value, str(work), why))
    return out


def conflicts_uncounted(conn, manifest):
    # BEGIN guard: a conflict EVENT with no resolution record is uncounted
    events = len(conflict_events_uncounted(conn, manifest))
    # END guard: a conflict EVENT with no resolution record is uncounted
    s_v, p_v = _scope(manifest, "v")
    # two works holding one distinct-valued identifier, each pair of works with no conflict row between them
    shared = conn.execute(
        "WITH held AS (SELECT DISTINCT i.scheme, i.value_norm, v.work_id FROM litkb.identifiers i"
        "  JOIN litkb.identifier_versions v ON v.identifier_id = i.id"
        "  JOIN litkb.scheme_registry sr ON sr.scheme = i.scheme AND sr.distinct_values"
        "  WHERE v.status = 'active' AND ((i.active AND v.version_id = i.current_version_id) OR v.state = 'proposed')"
        + s_v + ")"
        " SELECT count(*) FROM held a JOIN held b ON a.scheme = b.scheme AND a.value_norm = b.value_norm"
        "  AND a.work_id < b.work_id"
        " WHERE NOT EXISTS (SELECT 1 FROM litkb.identifier_conflicts c WHERE c.scheme = a.scheme"
        "   AND c.value_norm = a.value_norm AND ((c.claimed_by_work_id = a.work_id AND c.held_by_work_id = b.work_id)"
        "   OR (c.claimed_by_work_id = b.work_id AND c.held_by_work_id = a.work_id)))", p_v).fetchone()[0]
    return int(events) + int(shared)


def index_schemes(conn):
    """The schemes the partial unique index covers, from the catalog; None = no scheme predicate (all)."""
    row = conn.execute(
        "SELECT pg_get_expr(x.indpred, x.indrelid) FROM pg_index x "
        "WHERE x.indexrelid = to_regclass('litkb.identifiers_active_scheme_value')").fetchone()
    if row is None:
        raise Unread("litkb.identifiers_active_scheme_value does not exist")
    pred = row[0] or ""
    if "scheme" not in pred:
        return None
    return sorted(set(re.findall(r"'([a-z0-9_]+)'::text", pred)))


def nondistinct_detail(conn, manifest=None):
    """The non-distinct schemes the index covers, united with the plan's non-distinct schemes the REGISTRY
    marks distinct (a registry row flipped is the migration-to-be that would put the scheme in the index)."""
    registry = dict(conn.execute("SELECT scheme, distinct_values FROM litkb.scheme_registry").fetchall())
    covered = index_schemes(conn)
    if covered is None:
        covered = sorted(registry)
    in_index = {s for s in covered if registry.get(s) is False or s in PLAN_NONDISTINCT}
    flipped = {s for s in PLAN_NONDISTINCT if registry.get(s) is True}
    return sorted(in_index | flipped)


def nondistinct_schemes_in_unique_index(conn, manifest):
    return len(nondistinct_detail(conn, manifest))


# ── reported ─────────────────────────────────────────────────────────────────────────────────────────

def relation_edges_missing(conn, manifest):
    p = _probe(manifest, RELATION_PROBE)
    if p is None or not p.is_file():
        return 0
    # (key, doi): the work is found by its key OR by its DOI (auditor-B1 F8: the DOI clause was handed the key)
    pairs = sorted({(r["key"], r.get("doi") or "") for r in _csv(p) if r.get("state") == "asserted"})
    n = 0
    for k, doi in pairs:
        hit = conn.execute(
            "SELECT w.id, EXISTS (SELECT 1 FROM litkb.work_relations e WHERE e.state = 'asserted' "
            "AND (e.work_id = w.id OR e.target_work_id = w.id)) FROM litkb.works w WHERE w.key = %s "
            "OR w.id IN (SELECT v.work_id FROM litkb.identifiers i JOIN litkb.identifier_versions v "
            "ON v.version_id = i.current_version_id WHERE i.scheme = 'doi' "
            "AND i.value_norm = litkb.norm_identifier('doi', %s))",
            (k, doi)).fetchone()
        n += 0 if (hit and hit[1]) else 1
    return n


def identifier_first_refusals(conn, manifest):
    where, params = ["a.state = 'refused'", "c.state = 'duplicate-review'"], []
    if manifest.get("frozen_at"):
        where.append("a.created_at > %s")
        params.append(manifest["frozen_at"])
    ids = manifest.get("scope_workstream_ids") or manifest.get("run_workstream_ids")
    if ids:
        where.append("a.workstream_id = ANY(%s::uuid[])")
        params.append(list(map(str, ids)))
    return conn.execute(
        "SELECT count(*) FROM litkb.admissions a JOIN litkb.candidates c ON c.id = a.candidate_id "
        "WHERE " + " AND ".join(where) +
        # a strong DISTINCT scheme only: a type-scoped one (isbn) is strong only for a candidate of its types, and
        # the candidate row does not carry the type, so its refusals are not counted here (check 2's own rule)
        " AND EXISTS (SELECT 1 FROM jsonb_object_keys(coalesce(c.ids, '{}'::jsonb)) k"
        "   JOIN litkb.scheme_registry sr ON sr.scheme = k AND sr.identity_strong AND sr.distinct_values)",
        params).fetchone()[0]


def books_without_isbn(conn, manifest):
    return conn.execute(
        "SELECT count(*) FROM litkb.main_works w WHERE w.type IN ('book', 'chapter') AND NOT EXISTS ("
        " SELECT 1 FROM litkb.main_identifiers i WHERE i.work_id = w.work_id AND i.scheme = 'isbn' AND i.active)"
    ).fetchone()[0]


COUNTERS = {
    "relation_probe_rows": relation_probe_rows,
    "key_derivation_crashes": key_derivation_crashes,
    "crosswalk_rows_without_identifier": crosswalk_rows_without_identifier,
    "identifiers_without_provenance": identifiers_without_provenance,
    "conflicts_uncounted": conflicts_uncounted,
    "nondistinct_schemes_in_unique_index": nondistinct_schemes_in_unique_index,
}

REPORTED = {
    "relation_edges_missing": relation_edges_missing,
    "identifier_first_refusals": identifier_first_refusals,
    "books_without_isbn": books_without_isbn,
}

DETAILS = {
    "relation_probe_rows": lambda conn, m: [f"unanswered probe rows (not counted): {relation_probe_unanswered(conn, m)}"],
    "conflicts_uncounted": lambda conn, m: [f"{s}:{v} claimed by {w}: {why}"
                                            for s, v, w, why in conflict_events_uncounted(conn, m)],
    "crosswalk_rows_without_identifier": lambda conn, m: [f"{k}: {why}" for k, why in crosswalk_missing(conn, m)],
    "nondistinct_schemes_in_unique_index": lambda conn, m: [f"the unique index covers non-distinct {s}"
                                                           for s in nondistinct_detail(conn, m)],
}


# ── the fires ────────────────────────────────────────────────────────────────────────────────────────
# Each runs ONE arm on an already reset + migrated worker database (`conn` = its owner login, autocommit) or,
# as a pytest twin, on the suite's shared worker database — so every database counter a fire reads is scoped
# to the fire's own workstream (`scope_workstream_ids`). A known-bad arm applies its mutation in-process (a
# monkeypatch, or a function / index / registry row replaced ON THE WORKER DATABASE) and restores it before
# returning. Nothing here touches the network: the registry answers are CONSTRUCTED (qc/fixtures) or read
# from the tracked crosswalk probe CSV.

def constructed():
    return json.loads(CONSTRUCTED.read_text(encoding="utf-8"))


def _jsonb(v):
    from psycopg.types.json import Jsonb

    return Jsonb(v)


def _db_test():
    from litkb.db import connect as c

    return c.DB_TEST


def _writer():
    """A second connection to the worker database, as litkb_writer (the grants are part of what a fire tests)."""
    from litkb.db import connect as c

    k = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
    k.execute("SET ROLE litkb_writer")
    return k


def open_ws(conn, tag):
    ws, token = conn.execute("SELECT workstream_id, token FROM litkb.open_workstream(%s, 'work/s45-b1', NULL, %s, NULL)",
                             (f"b1-{tag}-{uuid.uuid4().hex[:8]}", f"builder-B1 fire {tag}")).fetchone()
    return str(ws), token


class RegistryStub:
    """Crossref `works/{doi}` and DataCite `dois/{doi}` from the CONSTRUCTED records; everything else 404.
    Never touches the network (brief-COMMON rule 11)."""
    base = ""

    def __init__(self, crossref=None, datacite=None):
        self.crossref = {k.lower(): v for k, v in (crossref or {}).items()}
        self.datacite = {k.lower(): v for k, v in (datacite or {}).items()}
        self.calls = []

    def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
        import urllib.parse

        self.calls.append(url)
        if "api.crossref.org/works/" in url:
            rec = self.crossref.get(urllib.parse.unquote(url.split("/works/", 1)[1]).lower())
            return (200, {}, json.dumps({"message": rec}).encode()) if rec else (404, {}, b"")
        if "api.datacite.org/dois/" in url:
            rec = self.datacite.get(urllib.parse.unquote(url.split("/dois/", 1)[1]).lower())
            return (200, {}, json.dumps({"data": {"attributes": rec}}).encode()) if rec else (404, {}, b"")
        return 404, {}, b""


def _nopace():
    from litkb.netutil import Pacer

    return Pacer(interval=0, sleep=lambda s: None)


def _registry_admission(conn, ws, token, work, identifiers, *, key, agent="b1-fire", session="b1-fire-session"):
    """A registry admission through litkb.admit itself, with the evidence check 1 needs (CONSTRUCTED records)."""
    cand = conn.execute("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
                        (ws, token, work["title"])).fetchone()[0]
    return conn.execute("SELECT litkb.admit(%s, %s, %s, 'registry', %s, %s, %s, NULL, %s, %s, %s)",
                        (ws, token, cand, key, _jsonb(work), _jsonb(identifiers), _jsonb({}), agent,
                         session)).fetchone()[0]


def _registry_evidence(title, author, year, registry="crossref"):
    return {"registry": registry, "registry_title": title, "registry_first_author": author, "registry_year": year,
            "registry_only": True}


@contextmanager
def replaced_function(conn, signature, strip_marker):
    """Replace a litkb SQL function ON THIS DATABASE with its own definition minus the lines between
    `BEGIN <strip_marker>` and `END <strip_marker>`; restore the original on exit (the harness also resets)."""
    oid = conn.execute("SELECT %s::regprocedure::oid", (signature,)).fetchone()[0]
    original = conn.execute("SELECT pg_get_functiondef(%s)", (oid,)).fetchone()[0]
    lines = original.splitlines(keepends=True)
    b = [i for i, ln in enumerate(lines) if f"BEGIN {strip_marker}" in ln]
    e = [i for i, ln in enumerate(lines) if f"END {strip_marker}" in ln]
    if len(b) != 1 or len(e) != 1:
        raise RuntimeError(f"{signature}: marker {strip_marker!r} not found exactly once")
    conn.execute("".join(lines[:b[0] + 1] + lines[e[0]:]))
    try:
        yield
    finally:
        conn.execute(original)


# fire: the probe CSV emptied -> relation_probe_rows = 0
def fire_relation_probe_emptied(conn, arm, workdir):
    import importlib.util

    spec = importlib.util.spec_from_file_location("litkb_acq_probe_relation",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_acq_probe_relation.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    reg = constructed()
    responses = Path(workdir) / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    for doi, msg in reg["crossref"].items():
        P.response_file(responses, doi).write_text(json.dumps({"message": msg}), encoding="utf-8")
    pairs = [(d, d) for d in reg["e21"]["dois"]]
    out = Path(workdir) / RELATION_PROBE
    P.write_csv(P.probe_rows(pairs, P.recorded_crossref(responses)), out)
    if arm == "known_bad":
        P.write_csv([], out)                    # the probe CSV emptied: header only
    return relation_probe_rows(None, {"repo": str(workdir), "probe_csvs": {RELATION_PROBE: str(out)}})


def _probe_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("litkb_acq_probe_relation",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_acq_probe_relation.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    return P


# fire: the probe got NO answer (every request failed) -> relation_probe_rows = 0 (auditor-B1 F1)
def fire_relation_probe_unanswered(conn, arm, workdir):
    """Control: E21's two DOIs probed against their CONSTRUCTED Crossref answers (2 answered rows). Known-bad:
    the same DOIs probed with a fetch whose every request failed (status 0, as offline / a blocked socket / a
    refused connect would answer) — the probe still writes one `unanswered` row per DOI, and the counter must
    read 0, because a probe that measured nothing is not the probe the gate asks for."""
    P = _probe_module()
    reg = constructed()
    responses = Path(workdir) / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    for doi, msg in reg["crossref"].items():
        P.response_file(responses, doi).write_text(json.dumps({"message": msg}), encoding="utf-8")
    fetch = P.recorded_crossref(responses) if arm == "control" else (lambda doi: (0, None))
    out = Path(workdir) / RELATION_PROBE
    P.write_csv(P.probe_rows([(d, d) for d in reg["e21"]["dois"]], fetch), out)
    return relation_probe_rows(None, {"repo": str(workdir), "probe_csvs": {RELATION_PROBE: str(out)}})


# the pre-S4.5 key rule, VERBATIM from pipeline/litkb/admit/front.py at 2ca3896 (the known-bad's revert)
def legacy_make_key(first_author, year, title):
    from litkb.admit.front import _STOP
    from litkb.admit.resolver import _ascii_fold

    parts = re.findall(r"[A-Za-z]+", _ascii_fold(first_author or ""))
    surname = "".join(p[0].upper() + (p[1:].lower() if p.isupper() else p[1:]) for p in parts) or "Anon"
    words = re.findall(r"[a-z0-9]+", _ascii_fold(title or "").lower())
    kept = [w for w in words if w not in _STOP] or words
    if len(kept) < 2:
        kept = (kept + [w for w in words if w not in kept] + ["work", "record"])[:2]
    slug_words = kept[:4]
    key = f"{surname}_{int(year):04d}_{'-'.join(slug_words)}"
    while len(key) >= 60 and len(slug_words) > 2:
        slug_words = slug_words[:-1]
        key = f"{surname}_{int(year):04d}_{'-'.join(slug_words)}"
    return key[:59]


@contextmanager
def _env(values):
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def hunt_187(conn, workdir, *, make_key=None):
    """Row 187's DOI hunted through `litkb.hunt.hunt` on the worker database, its registry answer the
    CONSTRUCTED DataCite record (the live record's fields as stored on work LPVSubgroup_2025_...), spend off,
    extraction off. -> (state, reason, hunt result)."""
    from litkb import hunt as Hn
    from litkb import workstream
    from litkb.acquire.store import Store
    from litkb.admit import front

    reg = constructed()["187"]
    wd = Path(workdir) / f"hunt-{uuid.uuid4().hex[:6]}"
    root = wd / "Literture"
    (root / "Validation").mkdir(parents=True)
    workstream.open_workstream(conn, f"b1-187-{uuid.uuid4().hex[:8]}", "work/s45-b1", "fire 187", directory=wd)
    stub = RegistryStub(datacite={reg["doi"]: reg["datacite_attributes"]})
    saved = front.make_key
    if make_key is not None:
        front.make_key = make_key
    try:
        with _env({"LITKB_DB": _db_test(), "LITKB_WORKTREE": str(wd), "LITKB_LITERATURE_ROOT": str(root)}):
            res = Hn.hunt(reg["doi"], db=_db_test(), worktree=wd, agent="b1-fire", session=f"b1-{uuid.uuid4().hex[:6]}",
                          reader_role="litkb_test", writer_role="litkb_test",
                          store=Store(root=root, index_cache=wd / "index.json"), derived=str(wd / "derived"),
                          registry_client=stub, spend=False, extract=False)
    finally:
        front.make_key = saved
    return res.get("state"), res.get("reason"), res


def _run_csv_187(workdir, state, reason):
    run_csv = Path(workdir) / "run.csv"
    with run_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=("row_id", "ref", "state", "reason"))
        w.writeheader()
        w.writerow({"row_id": "L187", "ref": constructed()["187"]["doi"], "state": state, "reason": reason})
    return run_csv


# fire: the key rule reverted -> 187's record -> key_derivation_crashes = 1
def fire_key_rule_reverted(conn, arm, workdir):
    state, reason, _res = hunt_187(conn, workdir, make_key=legacy_make_key if arm == "known_bad" else None)
    return key_derivation_crashes(None, {"run_csv": str(_run_csv_187(workdir, state, reason))})


KEY_GUARD = "guard: a key never cuts inside the surname segment"


def make_key_without_surname_guard():
    """`litkb.admit.front.make_key` as it is NOW, minus the lines between `BEGIN <KEY_GUARD>` and `END
    <KEY_GUARD>` — the guard deleted in-process (compiled from the live source in a copy of the module's
    globals; the module itself is never edited). Row 187's 68-character surname then overflows the budget and
    the key rule refuses by name: `KeyUnderivable` (auditor-B1 F3's crash shape)."""
    import inspect

    from litkb.admit import front

    lines = inspect.getsource(front.make_key).splitlines(keepends=True)
    b = [i for i, ln in enumerate(lines) if f"BEGIN {KEY_GUARD}" in ln]
    e = [i for i, ln in enumerate(lines) if f"END {KEY_GUARD}" in ln]
    if len(b) != 1 or len(e) != 1:
        raise RuntimeError(f"make_key: marker {KEY_GUARD!r} not found exactly once")
    ns = dict(vars(front))
    exec(compile("".join(lines[:b[0] + 1] + lines[e[0]:]), "<make_key without the surname guard>", "exec"), ns)
    return ns["make_key"]


# fire: the surname guard deleted -> 187's record -> crashed / admit:KeyUnderivable -> key_derivation_crashes = 1
def fire_key_guard_deleted(conn, arm, workdir):
    state, reason, _res = hunt_187(conn, workdir,
                                   make_key=make_key_without_surname_guard() if arm == "known_bad" else None)
    return key_derivation_crashes(None, {"run_csv": str(_run_csv_187(workdir, state, reason))})


def crosswalk_arxiv_rows(conn, n=3):
    """The first `n` rows (by key) of the TRACKED crosswalk probe CSV that carry an `s2_arxiv` id and a DOI that is
    not arXiv's own, and whose key and DOI no work on THIS database holds yet — real rows, re-hunted against
    CONSTRUCTED S2 answers built from their own columns. On a fresh worker database (the harness) that is the first
    three; on the suite's shared one it skips rows another test already admitted, and the known-bad arm, run after
    the control, takes the next three."""
    p = SCRIPTS.parent / "phase4" / "qc" / CROSSWALK_PROBE
    rows = sorted((r for r in _csv(p) if r.get("s2_arxiv") and r.get("doi")
                   and not r["doi"].lower().startswith("10.48550/")), key=lambda r: r["key"])
    out = []
    for r in rows:
        taken = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM litkb.works WHERE key = %s) OR EXISTS (SELECT 1 FROM litkb.identifiers "
            "WHERE scheme = 'doi' AND value_norm = litkb.norm_identifier('doi', %s))", (r["key"], r["doi"])).fetchone()[0]
        if not taken:
            out.append(r)
        if len(out) == n:
            break
    return out


def seed_work(conn, ws, key, doi, title, year, work_type="article"):
    """A CONSTRUCTED work in main carrying a real key and DOI (written as facts, as qc/test_litkb_hunt.py's
    seed_extracted does), its DOI's provenance `caller`."""
    wid = conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'work', NULL, %s, NULL, %s, NULL, %s, 'b1-seed', 'b1-seed')",
        (_jsonb({"key": key}), _jsonb({"type": work_type, "title": title, "authors": [], "year": year}), ws)).fetchone()[0]
    conn.execute(
        "SELECT entity_id FROM litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, NULL, %s, 'b1-seed', 'b1-seed')",
        (_jsonb({"scheme": "doi"}), _jsonb({"work_id": str(wid), "value": doi, "verified_by": "crossref",
                                            "asserted_by": "caller", "evidence": {}, "status": "active"}), ws))
    return str(wid)


# fire: the harvest disabled and the crosswalk's arXiv-id works re-hunted -> crosswalk_rows_without_identifier > 0
def crosswalk_world(conn, *, harvest=True):
    """Three crosswalk arXiv-id works seeded and re-hunted (see `crosswalk_arxiv_rows`). -> (rows, work ids,
    crosswalk_rows_without_identifier over exactly those rows). `harvest=False` is the known-bad."""
    from litkb.admit import harvest as H

    ws, token = open_ws(conn, "crosswalk")
    rows = crosswalk_arxiv_rows(conn, 3)
    wids = {r["key"]: seed_work(conn, ws, r["key"], r["doi"], f"CONSTRUCTED crosswalk work {r['key']}", 2020)
            for r in rows}
    saved = H.record
    if not harvest:
        H.record = lambda *a, **k: {"identifiers": None, "relations": None}     # the harvest disabled
    w = _writer()
    try:
        for r in rows:
            answer = {"externalIds": {"DOI": r["doi"], "ArXiv": r["s2_arxiv"], "CorpusId": r.get("s2_corpus") or None}}
            got_rows, rels = H.from_s2(answer, r["doi"])
            H.record(w, ws, token, wids[r["key"]], got_rows, rels, agent="b1-fire", session="b1-fire-session")
    finally:
        H.record = saved
        w.close()
    manifest = {"repo": str(SCRIPTS.parent),
                "probe_csvs": {CROSSWALK_PROBE: str(SCRIPTS.parent / "phase4" / "qc" / CROSSWALK_PROBE)},
                "rows": [{"key": r["key"], "source": ["crosswalk"]} for r in rows]}
    return rows, wids, crosswalk_rows_without_identifier(conn, manifest)


# fire: the harvest disabled and the crosswalk's arXiv-id works re-hunted -> crosswalk_rows_without_identifier > 0
def fire_harvest_disabled(conn, arm, workdir):
    return crosswalk_world(conn, harvest=(arm == "control"))[2]


def constructed_isbn(seed):
    """A CONSTRUCTED valid ISBN-13 (978 + nine digits from `seed` + the check digit the standard derives)."""
    from litkb import identifiers as I

    body = "978" + f"{int(seed, 16) % 10**9:09d}"
    return body + I.check_digit13(body)


def constructed_crosswalk_world(conn, workdir, column, *, harvest=True):
    """ONE CONSTRUCTED crosswalk row carrying ONLY `column` (`cr_isbn` or `cr_relation_types`), its work seeded in
    main, and the CONSTRUCTED Crossref answer that column was read from harvested through `harvest.from_crossref`
    + `harvest.record` — the admission's own parse and write. `harvest=False` (the known-bad) disables the write.
    -> (row, work id, crosswalk_rows_without_identifier over exactly that row). Each clause of the counter gets
    its own world, so deleting ONE clause makes its own fire read 0 (auditor-B1 F5: the arXiv fire alone left
    the ISBN and relation clauses unshown)."""
    from litkb.admit import harvest as H

    ws, token = open_ws(conn, f"cw-{column}")
    hexid = uuid.uuid4().hex[:10]
    key = f"Constructed_2020_crosswalk-{column.replace('_', '-')}-{hexid}"
    doi = f"10.5555/b1-cw-{column.replace('_', '-')}-{hexid}"
    header = _csv_header(SCRIPTS.parent / "phase4" / "qc" / CROSSWALK_PROBE)
    row = {c: "" for c in header} | {"key": key, "doi": doi}
    msg = {"DOI": doi, "title": [f"CONSTRUCTED crosswalk {column} work {hexid}"], "relation": {}}
    if column == "cr_isbn":
        isbn = constructed_isbn(hexid)
        row["cr_isbn"] = isbn
        msg |= {"type": "book-chapter", "ISBN": [isbn]}
        work_type = "chapter"
    elif column == "cr_relation_types":
        row["cr_relation_types"] = "has-preprint"
        msg |= {"type": "journal-article", "relation": {"has-preprint": [
            {"id-type": "doi", "id": f"10.5555/b1-cw-preprint-{hexid}", "asserted-by": "subject"}]}}
        work_type = "article"
    else:
        raise ValueError(column)
    wid = seed_work(conn, ws, key, doi, msg["title"][0], 2020, work_type)
    path = Path(workdir) / f"crosswalk-{column}-{hexid}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerow(row)
    rows, rels, _rejected = H.from_crossref(msg, doi)
    if harvest:
        k = _writer()
        try:
            H.record(k, ws, token, wid, rows, rels, agent="b1-fire", session="b1-fire-session")
        finally:
            k.close()
    manifest = {"repo": str(workdir), "probe_csvs": {CROSSWALK_PROBE: str(path)},
                "rows": [{"key": key, "source": ["crosswalk"]}]}
    return row, wid, crosswalk_rows_without_identifier(conn, manifest)


def _csv_header(path):
    with open(path, encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


# fire: the harvest disabled for a crosswalk ISBN row -> crosswalk_rows_without_identifier = 1
def fire_crosswalk_isbn(conn, arm, workdir):
    return constructed_crosswalk_world(conn, workdir, "cr_isbn", harvest=(arm == "control"))[2]


# fire: the harvest disabled for a crosswalk relation row -> crosswalk_rows_without_identifier = 1
def fire_crosswalk_relation(conn, arm, workdir):
    return constructed_crosswalk_world(conn, workdir, "cr_relation_types", harvest=(arm == "control"))[2]


# fire: an identifier row written with NULL asserted_by -> identifiers_without_provenance = 1
def fire_null_asserted_by(conn, arm, workdir):
    ws, token = open_ws(conn, "provenance")
    hexid = uuid.uuid4().hex[:10]
    title = f"A CONSTRUCTED registry record for the provenance fire {hexid}"
    work = {"type": "article", "title": title, "authors": [{"family": "Tester", "given": "T."}], "year": 2020}
    ids = [{"scheme": "doi", "value": f"10.5555/b1-prov-{hexid}", "verified_by": "crossref",
            "evidence": _registry_evidence(title, "Tester", 2020)}]
    guard = "guard: an admitted identifier carries who asserted it"
    if arm == "known_bad":
        sig = "litkb.admit(uuid, text, uuid, text, text, jsonb, jsonb, jsonb, jsonb, text, text)"
        with replaced_function(conn, sig, guard):
            res = _registry_admission(conn, ws, token, work, ids, key=f"Tester_2020_prov-{hexid}")
    else:
        res = _registry_admission(conn, ws, token, work, ids, key=f"Tester_2020_prov-{hexid}")
    if res.get("outcome") != "admitted":
        raise RuntimeError(f"the provenance fire's admission was not admitted: {res.get('outcome')}")
    return identifiers_without_provenance(conn, {"scope_workstream_ids": [ws]})


# fire: a CONSTRUCTED second work claiming an existing DOI -> refused, edge written, counted (known-bad: no count)
COUNT_GUARD = "guard: a conflict is counted"
DETECTION_GUARD = ("guard: two works claiming one distinct-valued identifier are a counted conflict, never a "
                   "second row")


def conflict_world(conn, known_bad=False, strip=COUNT_GUARD):
    """Work A holds DOI X (admitted); work B (admitted by its own arXiv id Y) is offered X as a harvest row
    derived from Y. -> (workstream, A, B, the record_identifiers result). CONSTRUCTED in every value.
    `known_bad` replaces litkb.record_identifiers on this database with its own body minus the `strip` guard:
    COUNT_GUARD (the conflict found but not counted) or DETECTION_GUARD (the conflict not even looked for — the
    write then meets the unique index, and the claim must survive as `collided`)."""
    ws, token = open_ws(conn, "conflict")
    hexid = uuid.uuid4().hex[:10]
    ta, tb = f"CONSTRUCTED article {hexid}", f"CONSTRUCTED preprint of an article {hexid}"
    doi = f"10.5555/b1-conflict-{hexid}"
    arxiv = f"2601.{int(hexid[:5], 16) % 90000 + 10000:05d}"
    a = _registry_admission(conn, ws, token, {"type": "article", "title": ta, "authors": [{"family": "Tester"}],
                                              "year": 2021},
                            [{"scheme": "doi", "value": doi, "verified_by": "crossref",
                              "evidence": _registry_evidence(ta, "Tester", 2021)}], key=f"Tester_2021_a-{hexid}")
    b = _registry_admission(conn, ws, token, {"type": "preprint", "title": tb, "authors": [{"family": "Tester"}],
                                              "year": 2021},
                            [{"scheme": "arxiv", "value": arxiv, "verified_by": "arxiv",
                              "evidence": _registry_evidence(tb, "Tester", 2021, "arxiv")}], key=f"Tester_2021_b-{hexid}")
    if a.get("outcome") != "admitted" or b.get("outcome") != "admitted":
        raise RuntimeError(f"conflict world: {a.get('outcome')}, {b.get('outcome')}")
    row = {"scheme": "doi", "value": doi, "asserted_by": "arxiv", "derived_from": {"scheme": "arxiv", "value": arxiv},
           "evidence": {"_note": "CONSTRUCTED: the arXiv record's journal-DOI field, naming the article"}}
    w = _writer()
    try:
        if known_bad:
            with replaced_function(conn, "litkb.record_identifiers(uuid, text, uuid, jsonb, text, text)", strip):
                got = w.execute("SELECT litkb.record_identifiers(%s, %s, %s, %s, 'b1-fire', 'b1-fire-session')",
                                (ws, token, b["work_id"], _jsonb([row]))).fetchone()[0]
        else:
            got = w.execute("SELECT litkb.record_identifiers(%s, %s, %s, %s, 'b1-fire', 'b1-fire-session')",
                            (ws, token, b["work_id"], _jsonb([row]))).fetchone()[0]
    finally:
        w.close()
    return ws, a["work_id"], b["work_id"], got


def fire_constructed_conflict(conn, arm, workdir):
    ws, _a, _b, _got = conflict_world(conn, known_bad=(arm == "known_bad"))
    return conflicts_uncounted(conn, {"scope_workstream_ids": [ws]})


# fire: conflict DETECTION removed -> the claim meets the unique index -> kept `collided` -> conflicts_uncounted = 1
# (Codex X4 / auditor-B1 F4: before identifier_claims this arm raised UniqueViolation and the counter read 0)
def fire_conflict_detection_removed(conn, arm, workdir):
    ws, _a, _b, _got = conflict_world(conn, known_bad=(arm == "known_bad"), strip=DETECTION_GUARD)
    return conflicts_uncounted(conn, {"scope_workstream_ids": [ws]})


# fire: `isbn` placed in the distinct set -> nondistinct_schemes_in_unique_index = 1
@contextmanager
def index_with(conn, extra_scheme):
    """The unique index rebuilt with one more scheme in its predicate; restored on exit."""
    original = conn.execute("SELECT pg_get_indexdef('litkb.identifiers_active_scheme_value'::regclass)").fetchone()[0]
    covered = index_schemes(conn) or []
    schemes = ", ".join(f"'{s}'" for s in sorted(set(covered) | {extra_scheme}))
    conn.execute("DROP INDEX litkb.identifiers_active_scheme_value")
    conn.execute("CREATE UNIQUE INDEX identifiers_active_scheme_value ON litkb.identifiers (scheme, value_norm) "
                 f"WHERE active AND scheme IN ({schemes})")
    try:
        yield
    finally:
        conn.execute("DROP INDEX litkb.identifiers_active_scheme_value")
        conn.execute(original)


@contextmanager
def registry_says_distinct(conn, scheme):
    """`scheme` placed in the registry's distinct set, and the unique index rebuilt from the registry as a
    migration would — unless the rows already held refuse it (two chapters sharing their book's ISBN are exactly
    why isbn is non-distinct), in which case the old index stays and only the registry row is flipped. Both are
    restored on exit."""
    row = conn.execute("SELECT distinct_values, identity_types FROM litkb.scheme_registry WHERE scheme = %s",
                       (scheme,)).fetchone()
    original = conn.execute("SELECT pg_get_indexdef('litkb.identifiers_active_scheme_value'::regclass)").fetchone()[0]
    conn.execute("UPDATE litkb.scheme_registry SET distinct_values = true, identity_types = NULL WHERE scheme = %s",
                 (scheme,))
    rebuilt = False
    try:
        try:
            with conn.transaction():
                schemes = ", ".join(f"'{r[0]}'" for r in conn.execute(
                    "SELECT scheme FROM litkb.scheme_registry WHERE distinct_values ORDER BY 1").fetchall())
                conn.execute("DROP INDEX litkb.identifiers_active_scheme_value")
                conn.execute("CREATE UNIQUE INDEX identifiers_active_scheme_value ON litkb.identifiers "
                             f"(scheme, value_norm) WHERE active AND scheme IN ({schemes})")
                rebuilt = True
        except Exception:                   # noqa: BLE001 — the held rows refuse the index: the registry flip stays
            rebuilt = False
        yield rebuilt
    finally:
        if rebuilt:
            conn.execute("DROP INDEX litkb.identifiers_active_scheme_value")
            conn.execute(original)
        conn.execute("UPDATE litkb.scheme_registry SET distinct_values = %s, identity_types = %s WHERE scheme = %s",
                     (row[0], row[1], scheme))


def fire_isbn_in_distinct_set(conn, arm, workdir):
    if arm == "known_bad":
        with registry_says_distinct(conn, "isbn"):
            return nondistinct_schemes_in_unique_index(conn, {})
    return nondistinct_schemes_in_unique_index(conn, {})


# fire: E21's pair -> two works + one relation edge (known-bad: the admission harvest disabled)
def _tagged(reg, tag):
    """The CONSTRUCTED Crossref records with every E21 DOI suffixed `.<tag>` (keys, DOI fields and relation
    targets), so a second arm on one database admits a pair shaped like E21 without re-admitting its DOIs."""
    if not tag:
        return reg["crossref"], reg["e21"]["dois"]
    text = json.dumps(reg["crossref"])
    for d in reg["e21"]["dois"]:
        text = text.replace(f'"{d}"', f'"{d}.{tag}"')
    return json.loads(text), [f"{d}.{tag}" for d in reg["e21"]["dois"]]


def e21_world(conn, workdir, *, harvest=True, tag=None):
    """E21's two DOIs admitted through `litkb.admit.front.admit_registry` against the CONSTRUCTED Crossref
    records (the relation fields each side really carries: has-preprint / is-preprint-of), the article FIRST so
    its edge is written before the preprint is a work. -> (ws, results). `tag` (the known-bad arm): the pair's
    DOIs suffixed, see `_tagged`."""
    from litkb.admit import front

    records, dois = _tagged(constructed(), tag)
    ws, token = open_ws(conn, "e21")
    stub = RegistryStub(crossref=records)
    saved = front.harvest_admission
    if not harvest:
        front.harvest_admission = lambda conn_, ws_, token_, res, rec, **kw: res
    w = _writer()
    out = []
    try:
        for doi in dois:
            out.append(front.admit_registry(w, ws, token, doi=doi, agent="b1-fire", session="b1-fire-session",
                                            client=stub, pacer=_nopace()))
    finally:
        front.harvest_admission = saved
        w.close()
    return ws, out


def fire_e21_pair(conn, arm, workdir):
    ws, res = e21_world(conn, workdir, harvest=(arm != "known_bad"),
                        tag=None if arm == "control" else f"kb{uuid.uuid4().hex[:6]}")
    if [r.get("outcome") for r in res] != ["admitted", "admitted"]:
        raise RuntimeError(f"E21's pair did not land as two works: {[r.get('outcome') for r in res]}")
    wids = [r["work_id"] for r in res]
    edges = conn.execute("SELECT count(*) FROM litkb.work_relations WHERE state = 'asserted' AND workstream_id = %s "
                         "AND (work_id = ANY(%s::uuid[]) OR target_work_id = ANY(%s::uuid[]))",
                         (ws, wids, wids)).fetchone()[0]
    # the fire's counter: works of the pair with no edge on either side (0 = the pair is linked)
    return sum(1 for wid in wids if not conn.execute(
        "SELECT EXISTS (SELECT 1 FROM litkb.work_relations WHERE state = 'asserted' AND "
        "(work_id = %s OR target_work_id = %s))", (wid, wid)).fetchone()[0]) + (0 if edges <= 1 else edges - 1)


# fire: E06 — no confirmed identifier, title-near an existing work — must STILL refuse duplicate-review
def e06_admission(conn, *, url_strong=False, tag=None):
    """E06's URL admitted as a manual proposal, title-near its carrier (Tkaczyk_2024, seeded CONSTRUCTED with its
    real title and DOI). -> the admission result. `url_strong` is the known-bad: `url` made an identity-strong
    scheme, so identifier-first would skip the title review."""
    reg = constructed()["e06"]
    ws, token = open_ws(conn, "e06")
    seed_work(conn, ws, f"Tkaczyk_2024_how-good-your-matching-{uuid.uuid4().hex[:6]}",
              reg["carrier_doi"] + (f".{tag}" if tag else ""), reg["carrier_title"], reg["carrier_year"], "preprint")
    import hashlib

    title = reg["carrier_title"]
    binding = {"verdict": "bound", "ratio": 1.0, "matched": title, "registry_title": title, "author_found": True,
               "author_near_title": True, "text_layer": True, "page": 1, "title_region": True}
    file_json = {"sha256": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                 "rel_path": f"_litkb_staging/web/e06-{uuid.uuid4().hex[:6]}.txt", "binding": binding,
                 "copy_kind": "web snapshot"}
    cand = conn.execute("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
                        (ws, token, title)).fetchone()[0]
    work = {"type": "report", "title": title, "authors": [{"family": "Tkaczyk", "given": ""}], "year": reg["carrier_year"]}
    ids = [{"scheme": "url", "value": reg["url"], "verified_by": "manual", "evidence": {"source": "E06 CONSTRUCTED"}}]
    if url_strong:
        conn.execute("UPDATE litkb.scheme_registry SET identity_strong = true WHERE scheme = 'url'")
    try:
        return conn.execute("SELECT litkb.admit(%s, %s, %s, 'manual', %s, %s, %s, %s, %s, 'b1-fire', 'b1-fire-session')",
                            (ws, token, cand, f"Tkaczyk_2024_e06-{uuid.uuid4().hex[:8]}", _jsonb(work), _jsonb(ids),
                             _jsonb(file_json), _jsonb({}))).fetchone()[0]
    finally:
        if url_strong:
            conn.execute("UPDATE litkb.scheme_registry SET identity_strong = false WHERE scheme = 'url'")


def fire_e06(conn, arm, workdir):
    res = e06_admission(conn, url_strong=(arm == "known_bad"),
                        tag=None if arm == "control" else f"kb{uuid.uuid4().hex[:6]}")
    return 0 if res.get("outcome") == "duplicate-review" else 1


FIRES = {
    "relation_probe_emptied": {"counter": "relation_probe_rows", "run": fire_relation_probe_emptied},
    "relation_probe_unanswered": {"counter": "relation_probe_rows", "run": fire_relation_probe_unanswered},
    "key_rule_reverted": {"counter": "key_derivation_crashes", "run": fire_key_rule_reverted},
    "key_guard_deleted": {"counter": "key_derivation_crashes", "run": fire_key_guard_deleted},
    "harvest_disabled_crosswalk": {"counter": "crosswalk_rows_without_identifier", "run": fire_harvest_disabled},
    "harvest_disabled_crosswalk_isbn": {"counter": "crosswalk_rows_without_identifier", "run": fire_crosswalk_isbn},
    "harvest_disabled_crosswalk_relation": {"counter": "crosswalk_rows_without_identifier",
                                            "run": fire_crosswalk_relation},
    "null_asserted_by": {"counter": "identifiers_without_provenance", "run": fire_null_asserted_by},
    "constructed_second_work_claims_doi": {"counter": "conflicts_uncounted", "run": fire_constructed_conflict},
    "conflict_detection_removed": {"counter": "conflicts_uncounted", "run": fire_conflict_detection_removed},
    "isbn_in_distinct_set": {"counter": "nondistinct_schemes_in_unique_index", "run": fire_isbn_in_distinct_set},
    # the two ADMISSION rows of the plan's test set have no (b) counter of their own, so each fire names its own
    # count and bound (the module contract's optional "bound"): works of E21's pair left unlinked; E06 admitted
    # instead of refused duplicate-review
    "e21_pair_two_works_one_edge": {"counter": "e21_pair_unlinked", "bound": "=0", "run": fire_e21_pair},
    "e06_still_duplicate_review": {"counter": "e06_not_duplicate_review", "bound": "=0", "run": fire_e06},
}
