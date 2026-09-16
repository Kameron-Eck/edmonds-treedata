"""Stage 6 ingest — the parked references, mentions, edges and candidates, as ``litkb_ingest``.

    report = load(conn, root)                 every paper under `root`, one transaction each
    result = ingest_paper(conn, paper, ...)   one paper

WHY THIS FILE EXISTS. `litkb.extract.references` is DB-FREE BY CONSTRUCTION (its own header) and
parks its output as JSONL under ``{LITKB_DERIVED}/p6/``. `Reports/LITKB_P4_MERGE_2026-09-15.md`
("Migration: none written") measured the consequence: 658 references, 1,182 citation mentions and
13 citation edges with **no loader on either side of that merge**, and nowhere to put two of the
three. Migration 0020 gave them their columns, their ``ambiguous`` state, the ``citation_edges``
table and a write path for the ingest login. This is the loader that uses it.

ONE TRANSACTION PER PAPER. The run row, its references, their mentions, the edges and the
candidates commit together or not at all — the rule `litkb.extract.ingest` states for stage 5, and
the reason it gives applies unchanged here: §14 P5's kill is "the kill fires when ingest is mutated
to commit text rows outside the run's transaction", and a partial commit is exactly what leaves half
a paper behind when a worker is killed. A reference does have a natural key within its run
(``(run_id, ref_key)``, 0020), so a duplicate reference is refused rather than silently doubled —
but a mention has none but its reference, and an edge and a candidate hang off the reference id, so
a half-written paper is still a half-written graph.

IDEMPOTENT BY (file sha256, pipeline version), the identity stage 5 uses: 0001's UNIQUE on
(file, stage, tool, tool_version, params_hash, pipeline_version). :func:`ingest_paper` asks
:func:`already_ingested` first and does nothing at all when the run is there and ``ok``. A run that
exists and is NOT ok is a killed worker's carcass: its rows are cleared by
``litkb.clear_extraction_rows`` (0017, extended by 0020 to reach stage-6 mentions, the edges and the
candidate links) inside the resuming transaction.

THE POINTER IS NOT MOVED. `set_current_run` is for the reconciliation stage only (design §7, and
`litkb.extract.ingest`'s header): a file's current run is the run whose BLOCKS are the file's text.
A stage-6 run has none, so making it current would point search, exports and evidence at a run with
zero blocks. Nothing in the database stops it — 0017's guard checks only that the run is ``ok`` and
belongs to the file — which is precisely why it is stated here.

WHAT A P6 KEY IS, AND WHAT IT IS NOT. ``citing_work_key``/``cited_work_key`` in the artifacts are
FILE STEMS (`LITERATURE_CONVENTION.md`'s filing convention), not ``works.key``. Measured on the live
`litkb`, 2026-09-15: of the 18 citing stems, 17 match a held file by the stem of
``main_files.rel_path`` and only 10 are also a ``works.key`` — the key truncates the slug to four
words, so `Benedek_2015_multilayer-markov-random-field-models` is held under the work key
`Benedek_2015_multilayer-markov-random-field`. So :func:`held_index` resolves BY FILE STEM FIRST and
falls back to ``works.key``, and records which route matched on the run's metrics. A stem that
reaches neither, or that reaches a work holding no file, is REFUSED for that paper: `"references"`
carries a NOT NULL ``file_id``, and the one thing a loader must never do to satisfy a NOT NULL is
pick a file that is not the paper's.

WHAT RESOLVES TO A HELD WORK. ``resolved_work_id`` is set only when the reference's resolved DOI is
a held work's ACTIVE DOI identifier — the join `litkb` itself can prove. It is NOT the edge rule:
`extract.references` builds its edges from the corpus index (the manifest and bibliography CSVs), so
the two can disagree, and where they do the edge is recorded with ``resolved_work_id`` still NULL
rather than one being talked into the other. 0020's `add_reference` refuses a resolved work on a
reference that is not ``resolved``, so the NULL is enforced, not merely intended.

NO NORMALISATION HAPPENS HERE. Every DOI in the artifacts has already been through
`resolver.normalize_doi` inside stage 6 (`references.py`'s six call sites, harness rows P6-S1..S6).
Re-normalising at load would be a SECOND copy of that guard in a second place, which is the defect
the per-call-site rule exists to catch; comparing raw spellings would be the defect P6-S5 describes.
The loader therefore compares ``resolved_doi`` with ``main_identifiers.value_norm``, both already
canonical, and calls nothing.

NO NUL SCRUB EITHER, and that is a statement about the input: every string here came out of GROBID's
TEI, and XML 1.0 cannot carry U+0000 at all. Stage 5 needs `jsonb_safe` because Docling hands it
text taken from a PDF's own object streams (harness row R531, "THE BLOCKER"); stage 6 never touches
one. A NUL that did appear would abort the paper's transaction in Postgres and leave nothing behind,
which is the outcome this loader wants anyway.
"""
import json
import os

#: This loader's name. `stage` and `pipeline_version` are stage 6's own constants, read from
#: `litkb.extract.references` (:func:`_stage`, :func:`_tool_version`) and never re-spelled here.
TOOL = "litkb-references"

#: The reference fields that ARE the parse (§4.4 ``references.parsed``). Everything else on a P6
#: reference row is the raw string, the run's own labelling (stage, pipeline_version,
#: citing_work_key) or the resolution, each of which has a column of its own. Listed rather than
#: subtracted, so a field added upstream lands in `parsed` only when someone decides it should.
PARSED_FIELDS = ("index", "authors", "first_author", "year", "title", "journal", "volume", "issue",
                 "pages", "publisher", "doi", "doi_norm", "arxiv", "raw_source", "boxes",
                 "confidence", "has_monogr")

#: The artifact filenames stage 6 parks, and the key each is read under.
ARTIFACTS = {"references": "references.jsonl", "citation_mentions": "citation_mentions.jsonl",
             "edges": "edges.jsonl", "candidates": "candidates.jsonl",
             "extraction_log": "extraction_log.jsonl"}


class ReferenceIngestError(RuntimeError):
    """The artifacts disagree with each other, or with what was just written. Nothing is committed."""


def _references():
    from litkb.extract import references

    return references


def _stage():
    """The stage name, from stage 6's own constant. Never a second spelling of it."""
    return _references().STAGE


def _tool_version():
    return _references().PIPELINE_VERSION


def params_hash(params=None):
    """A stable hash of the thresholds stage 6 resolved with.

    Same argument as `ingest.params_hash`: the thresholds ARE parameters. A run made at
    RESOLVE_TITLE_RATIO 0.85 and one made at 0.60 are different extractions of the same file and
    must not collide on the run key — which is also what stops a P6-R1 mutant's output from being
    loaded on top of the honest one.
    """
    import hashlib

    from litkb.admit import resolver

    r = _references()
    payload = dict(params or {})
    payload.setdefault("resolve_title_ratio", resolver.RESOLVE_TITLE_RATIO)
    payload.setdefault("contained_min_words", r.CONTAINED_MIN_WORDS)
    payload.setdefault("contained_min_fraction", r.CONTAINED_MIN_FRACTION)
    payload.setdefault("cacheable_status", list(r.CACHEABLE_STATUS))
    payload.setdefault("breaker_trip_after", r.StageBreaker.TRIP_AFTER)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def run_key(file_id, pipeline_version=None, params=None):
    return dict(file_id=file_id, stage=_stage(), tool=TOOL,
                tool_version=pipeline_version or _tool_version(),
                params_hash=params_hash(params),
                pipeline_version=pipeline_version or _tool_version())


def already_ingested(conn, file_id, pipeline_version=None, params=None):
    """-> (run_id, status) for this file at this pipeline version, or (None, None)."""
    k = run_key(file_id, pipeline_version, params)
    row = conn.execute(
        "SELECT id, status FROM litkb.extraction_runs WHERE file_id = %(file_id)s AND stage = %(stage)s "
        "AND tool = %(tool)s AND tool_version = %(tool_version)s AND params_hash = %(params_hash)s "
        "AND pipeline_version = %(pipeline_version)s", k).fetchone()
    return (row[0], row[1]) if row else (None, None)


def run_counts(conn, run_id):
    """What one run actually holds, read back from the database — never from what was sent."""
    return dict(zip(("references", "citation_mentions", "citation_edges", "candidates"),
                    conn.execute(
                        'SELECT (SELECT count(*) FROM litkb."references" WHERE run_id = %(r)s),'
                        "       (SELECT count(*) FROM litkb.citation_mentions m WHERE m.reference_id IN "
                        '              (SELECT id FROM litkb."references" WHERE run_id = %(r)s)),'
                        "       (SELECT count(*) FROM litkb.citation_edges WHERE run_id = %(r)s),"
                        "       (SELECT count(*) FROM litkb.candidates c WHERE c.citing_reference_id IN "
                        '              (SELECT id FROM litkb."references" WHERE run_id = %(r)s))',
                        {"r": run_id}).fetchone()))


# ── the artifacts ───────────────────────────────────────────────────────────────────────

def artifact_dir(root=None):
    """``<root>/p6``, or `root` itself when it already names the p6 directory."""
    if root is None:
        root = os.path.join(_references().DERIVED_ROOT, "p6")
    root = os.path.abspath(root)
    if os.path.basename(root) != "p6" and os.path.isdir(os.path.join(root, "p6")):
        return os.path.join(root, "p6")
    return root


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def read_artifacts(root=None):
    """-> {"root", "references", "citation_mentions", "edges", "candidates", "extraction_log"}.

    A missing file reads as no rows: the extraction log is provenance, and a corpus in which
    nothing resolved to a held work really does have no edges."""
    d = artifact_dir(root)
    out = {"root": d}
    for key, name in ARTIFACTS.items():
        p = os.path.join(d, name)
        out[key] = read_jsonl(p) if os.path.exists(p) else []
    return out


def mention_elements(mentions):
    """The box rows of one paper -> one row per ``<ref type="bibr">`` ELEMENT, boxes collected.

    `references.citation_mentions` emits ONE ROW PER BOUNDING BOX and says so: a marker that wraps
    across a line carries two, correct as geometry and wrong as a count (measured 2026-09-15: 1,386
    box rows over 1,182 elements). The rows arrive in document order with `box_index` counting from
    0 within each element, so a ``box_index == 0`` OPENS an element and the rows after it are that
    element's remaining boxes. Grouping on ``(target, page)`` instead would merge two genuine
    mentions of one reference on one page into one — the same defect with the opposite sign.
    """
    out = []
    for m in mentions:
        if m.get("box_index") == 0 or not out:
            out.append({"target": m.get("target"), "marker": m.get("marker"),
                        "sentence": m.get("sentence"), "page": m.get("page"), "boxes": []})
        if m.get("page") is not None or m.get("bbox") is not None:
            out[-1]["boxes"].append({"page": m.get("page"), "bbox": m.get("bbox")})
    return out


def pair_candidates(refs, edges, cands):
    """-> {ref_key: candidate row}. The artifacts carry no ref_key on a candidate, so it is derived.

    `references.process_tei` walks the reference list ONCE and writes, for each reference, either an
    in-corpus edge or a candidate — never both, never neither. So within one paper the candidates
    are the references that produced no edge, in the same order, and the pairing is positional. It
    is then CHECKED against the candidate's own copy of the reference (`citing_reference` is
    ``ref["raw"][:2000]``, and the candidate's title is the reference's), because a positional
    pairing that is silently wrong would attach every lead to the wrong citation.
    """
    edged = {e["ref_key"] for e in edges}
    unedged = [r for r in refs if r["ref_key"] not in edged]
    if len(unedged) != len(cands):
        raise ReferenceIngestError(
            f"{len(cands)} candidate(s) for {len(unedged)} reference(s) without an edge "
            f"({len(refs)} references, {len(edges)} edges): these artifacts are not one run's")
    out = {}
    for ref, cand in zip(unedged, cands):
        # BEGIN guard: p6 ingest a candidate is paired with its own reference
        if cand.get("citing_reference") != (ref.get("raw") or "")[:2000] \
                or cand.get("title") != ref.get("title"):
            raise ReferenceIngestError(
                f"candidate {cand.get('title')!r} does not match reference {ref['ref_key']} "
                f"({ref.get('title')!r}): the positional pairing is not the right one")
        # END guard: p6 ingest a candidate is paired with its own reference
        out[ref["ref_key"]] = cand
    return out


def papers(art):
    """The artifacts regrouped -> [{"stem", "references", "mentions", "edges", "candidates", "log"}],
    in the order stage 6 wrote the reference rows."""
    order, by_stem = [], {}
    for r in art["references"]:
        stem = r["citing_work_key"]
        if stem not in by_stem:
            order.append(stem)
            by_stem[stem] = {"stem": stem, "references": [], "mentions": [], "edges": [],
                             "candidates": [], "log": None}
        by_stem[stem]["references"].append(r)
    for key, rows in (("mentions", art["citation_mentions"]), ("edges", art["edges"]),
                      ("candidates", art["candidates"])):
        for row in rows:
            if row.get("citing_work_key") in by_stem:
                by_stem[row["citing_work_key"]][key].append(row)
    for row in art["extraction_log"]:
        if row.get("stem") in by_stem:
            by_stem[row["stem"]]["log"] = row
    return [by_stem[s] for s in order]


# ── what the database already holds ─────────────────────────────────────────────────────

def _stem_of(rel_path):
    return os.path.splitext(os.path.basename(str(rel_path or "").replace("\\", "/")))[0]


def held_index(conn):
    """{stem: {"work_id", "file_id", "route", "rel_path"}} for every stem a P6 key can name.

    FILE STEM FIRST (route ``file-stem``), then ``works.key`` (route ``works.key``) for keys no file
    stem already claims — see the module header for why that order and not the other. A work reached
    by key contributes its own active file when it has exactly one; when it has none the entry stays
    with ``file_id`` None, which is enough to be the CITED end of an edge and not enough to be the
    citing end of a reference list.
    """
    rows = conn.execute(
        "SELECT rel_path, file_id, work_id FROM litkb.main_files WHERE status = 'active'").fetchall()
    files_by_work, out = {}, {}
    for rel_path, file_id, work_id in rows:
        files_by_work.setdefault(work_id, []).append(file_id)
        out.setdefault(_stem_of(rel_path), {"work_id": work_id, "file_id": file_id,
                                            "route": "file-stem", "rel_path": rel_path})
    for key, work_id in conn.execute("SELECT key, id FROM litkb.works").fetchall():
        if key in out:
            continue
        held = files_by_work.get(work_id) or []
        out[key] = {"work_id": work_id, "file_id": held[0] if len(held) == 1 else None,
                    "route": "works.key", "rel_path": None}
    return out


def doi_index(conn):
    """{normalised DOI: work_id} over the ACTIVE doi identifiers — the only DOI join `litkb` can
    prove. Both sides are already canonical (module header)."""
    return {v: w for v, w in conn.execute(
        "SELECT value_norm, work_id FROM litkb.main_identifiers "
        "WHERE scheme = 'doi' AND active AND status = 'active'").fetchall()}


def resolve_paper(stem, index):
    """-> (entry, refusal). A stem litkb does not hold is a REFUSAL, never a substitution."""
    hit = index.get(stem)
    if hit is None or hit.get("file_id") is None:
        return None, _unheld(stem, hit)
    return hit, ""


def _unheld(stem, hit):
    if hit is None:
        return f"{stem}: litkb holds no file with that stem and no work with that key"
    return (f"{stem}: reaches work {hit['work_id']} by {hit['route']}, which holds no active file, "
            "and a reference must name the file it was parsed from")


# ── one paper ───────────────────────────────────────────────────────────────────────────

def ingest_paper(conn, paper, index, dois, *, artifact_path=None, host="local",
                 pipeline_version=None, params=None, commit=True, _after_references=None):
    """One paper's references, mentions, edges and candidates, in ONE transaction.

    `index` is :func:`held_index`, `dois` is :func:`doi_index`. ``_after_references`` is a test
    hook called after the references are inserted and before the transaction commits — where the
    simulated mid-paper kill is raised.
    """
    from psycopg.types.json import Jsonb

    from litkb.admit.resolver import _year_int

    stem, refs = paper["stem"], paper["references"]
    held, refusal = resolve_paper(stem, index)
    if refusal:
        # load() refuses before it gets here; reaching this means a caller skipped that step.
        raise ReferenceIngestError(refusal)
    file_id, work_id = held["file_id"], held["work_id"]

    k = run_key(file_id, pipeline_version, params)
    existing, status = already_ingested(conn, file_id, pipeline_version, params)
    if existing and status == "ok":
        return dict(run_counts(conn, existing), stem=stem, run_id=existing, inserted=False,
                    route=held["route"], skipped={})

    elements = mention_elements(paper["mentions"])
    paired = pair_candidates(refs, paper["edges"], paper["candidates"])
    skipped = {"mentions_without_reference": 0, "mentions_unlocatable": 0,
               "edges_cited_work_not_held": 0, "edges_self_citation": 0}

    was_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        metrics = {"stem": stem, "route": held["route"], "references": len(refs),
                   "mention_box_rows": len(paper["mentions"]), "mention_elements": len(elements),
                   "edges": len(paper["edges"]), "candidates": len(paper["candidates"])}
        if paper.get("log"):
            metrics["tei"] = paper["log"]
        run_id = conn.execute(
            "SELECT litkb.open_extraction_run(%(file_id)s, %(stage)s, %(tool)s, %(tool_version)s, "
            "%(params_hash)s, %(pipeline_version)s, %(host)s, 'failed', %(artifact)s, %(metrics)s)",
            dict(k, host=host, artifact=artifact_path, metrics=Jsonb(metrics))).fetchone()[0]
        # A run that exists and is not ok is a killed worker's leftovers, cleared in THIS
        # transaction so the paper never holds two reference lists, not even momentarily.
        conn.execute("SELECT litkb.clear_extraction_rows(%s)", (run_id,))

        ref_ids = {}
        for r in refs:
            state = r["resolution"]
            # 0020: a resolved reference names the DOI it resolved to, and nothing else names one.
            doi = r.get("resolved_doi") if state == "resolved" else None
            ref_ids[r["ref_key"]] = conn.execute(
                "SELECT litkb.add_reference(%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (file_id, run_id, r["ref_key"], r.get("index"), r.get("raw"),
                 Jsonb({f: r.get(f) for f in PARSED_FIELDS}), work_id,
                 dois.get(doi) if doi else None, doi, state,
                 Jsonb(r.get("resolution_detail") or {}), r.get("confidence"),
                 r.get("mention_count"), r.get("pipeline_version"))).fetchone()[0]

        if _after_references is not None:
            _after_references(conn, run_id)

        written, unlocatable = {}, {}
        for el in elements:
            target = el.get("target") or ""
            # BEGIN guard: p6 ingest a mention names a parsed reference or is not written
            if target not in ref_ids:
                # GROBID emitted a <ref type="bibr"> it could not link to any biblStruct (201 of
                # 1,182 elements on this corpus). There is nothing to attach it to, and guessing
                # the reference from the marker text is the fabrication stage 6 refuses.
                skipped["mentions_without_reference"] += 1
                continue
            # END guard: p6 ingest a mention names a parsed reference or is not written
            if el.get("page") is None:
                # 0020's CHECK: with no block and no page, a stage-6 mention is one nobody can
                # locate. Counted, never written with an invented page.
                skipped["mentions_unlocatable"] += 1
                unlocatable[target] = unlocatable.get(target, 0) + 1
                continue
            conn.execute(
                "SELECT litkb.add_citation_mention(%s, %s, NULL, NULL, NULL, %s, %s, %s, %s)",
                (ref_ids[target], written.get(target, 0), el["page"], Jsonb(el["boxes"]),
                 el.get("marker"), el.get("sentence")))
            written[target] = written.get(target, 0) + 1

        _check_mention_counts(stem, refs, written, unlocatable)

        n_edges = 0
        for e in paper["edges"]:
            cited = index.get(e["cited_work_key"])
            if cited is None:
                # The edge was made against the corpus INDEX (the manifest and bibliography CSVs);
                # a work those name and litkb does not hold has no node to point at.
                skipped["edges_cited_work_not_held"] += 1
                continue
            if cited["work_id"] == work_id:
                # citation_edges_not_a_self_loop. A paper whose reference resolved to itself is a
                # real parse artefact, not an edge; counted so it is never invisible.
                skipped["edges_self_citation"] += 1
                continue
            conn.execute("SELECT litkb.add_citation_edge(%s, %s, %s, %s, %s, %s)",
                         (work_id, cited["work_id"], ref_ids[e["ref_key"]], run_id,
                          e.get("cited_doi"), e.get("mention_count")))
            n_edges += 1

        n_cands = 0
        for ref_key, c in paired.items():
            conn.execute("SELECT litkb.add_citation_candidate(%s, %s, %s, %s, %s, %s, %s)",
                         (ref_ids[ref_key], c.get("title"), Jsonb(c.get("authors")),
                          _year_int(c.get("year")),
                          Jsonb({"doi": c["doi"]}) if c.get("doi") else None,
                          Jsonb(c.get("raw_record")), f"cited by {stem} as {ref_key}"))
            n_cands += 1

        conn.execute("SELECT litkb.finish_extraction_run(%s, 'ok', %s)",
                     (run_id, Jsonb(dict(metrics, written={
                         "references": len(ref_ids), "citation_mentions": sum(written.values()),
                         "citation_edges": n_edges, "candidates": n_cands}, skipped=skipped))))
        # NO set_current_run: a stage-6 run has no blocks and must never become a file's text.
        if commit:
            conn.commit()
        return {"stem": stem, "run_id": run_id, "inserted": True, "route": held["route"],
                "references": len(ref_ids), "citation_mentions": sum(written.values()),
                "citation_edges": n_edges, "candidates": n_cands, "skipped": skipped}
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.autocommit = was_autocommit


def _check_mention_counts(stem, refs, written, unlocatable):
    """The mentions written are the elements stage 6 counted — REFERENCE BY REFERENCE.

    ``mention_count`` on a reference row is stage 6's own count of ELEMENTS naming it
    (`references.process_tei`: one per ``box_index == 0``). If what was written does not add up to
    it, the grouping in :func:`mention_elements` is wrong — a per-box grouping inflates it, a
    per-(target, page) grouping deflates it — and the citation counts in the database would silently
    disagree with the artifact they were read from. The only licensed shortfall is a mention this
    loader could not locate, and it is counted AGAINST ITS OWN REFERENCE: summing the shortfall over
    the paper and comparing it with a paper-wide unlocatable count would let one reference's missing
    mention be excused by another reference's unlocatable one.
    """
    # BEGIN guard: p6 ingest the mentions written are the elements stage 6 counted
    for r in refs:
        key = r["ref_key"]
        expected, got, lost = r.get("mention_count") or 0, written.get(key, 0), unlocatable.get(key, 0)
        if got + lost != expected:
            raise ReferenceIngestError(
                f"{stem} {key}: {got} mention row(s) written and {lost} unlocatable, for a "
                f"reference stage 6 counted {expected} mention(s) of — citation_mentions is not "
                "one row per <ref> element")
    # END guard: p6 ingest the mentions written are the elements stage 6 counted


# ── the whole corpus ────────────────────────────────────────────────────────────────────

def load(conn, root=None, *, only=None, dry_run=False, host="local", pipeline_version=None,
         params=None):
    """Every paper stage 6 parked under `root`, one transaction each. -> the report dict.

    `only` is a stem or an iterable of stems. `dry_run` resolves and counts and writes nothing —
    including no run row, so a dry run leaves the database byte-identical.
    """
    art = read_artifacts(root)
    index, dois = held_index(conn), doi_index(conn)
    wanted = {only} if isinstance(only, str) else (set(only) if only else None)
    report = {"root": art["root"], "dry_run": bool(dry_run), "papers": 0,
              "loaded": [], "already": [], "refused": [], "routes": {},
              "counts": {"references": 0, "citation_mentions": 0, "citation_edges": 0,
                         "candidates": 0},
              "skipped": {"mentions_without_reference": 0, "mentions_unlocatable": 0,
                          "edges_cited_work_not_held": 0, "edges_self_citation": 0}}
    for paper in papers(art):
        stem = paper["stem"]
        if wanted is not None and stem not in wanted:
            continue
        report["papers"] += 1
        held, refusal = resolve_paper(stem, index)
        # BEGIN guard: p6 ingest a stem litkb does not hold is refused, never substituted
        if refusal:
            report["refused"].append({"stem": stem, "reason": refusal,
                                      "references": len(paper["references"])})
            continue
        # END guard: p6 ingest a stem litkb does not hold is refused, never substituted
        report["routes"][held["route"]] = report["routes"].get(held["route"], 0) + 1
        if dry_run:
            run_id, status = already_ingested(conn, held["file_id"], pipeline_version, params)
            bucket = "already" if (run_id and status == "ok") else "loaded"
            report[bucket].append(stem)
            if bucket == "loaded":
                elements = mention_elements(paper["mentions"])
                pair_candidates(paper["references"], paper["edges"], paper["candidates"])
                keys = {r["ref_key"] for r in paper["references"]}
                report["counts"]["references"] += len(paper["references"])
                report["counts"]["citation_mentions"] += sum(
                    1 for e in elements if e["target"] in keys and e["page"] is not None)
                report["counts"]["citation_edges"] += sum(
                    1 for e in paper["edges"] if index.get(e["cited_work_key"]))
                report["counts"]["candidates"] += len(paper["candidates"])
                report["skipped"]["mentions_without_reference"] += sum(
                    1 for e in elements if e["target"] not in keys)
                report["skipped"]["mentions_unlocatable"] += sum(
                    1 for e in elements if e["target"] in keys and e["page"] is None)
                report["skipped"]["edges_cited_work_not_held"] += sum(
                    1 for e in paper["edges"] if not index.get(e["cited_work_key"]))
            continue
        tei = os.path.join(art["root"], "tei", f"{stem}.tei.xml")
        res = ingest_paper(conn, paper, index, dois, host=host, pipeline_version=pipeline_version,
                           params=params, artifact_path=tei if os.path.exists(tei) else art["root"])
        report["loaded" if res["inserted"] else "already"].append(stem)
        if res["inserted"]:
            for key in report["counts"]:
                report["counts"][key] += res[key]
            for key, n in res["skipped"].items():
                report["skipped"][key] += n
    return report


# ── the CLI ─────────────────────────────────────────────────────────────────────────────

def connect(dbname=None):
    """The ingest connection for `dbname`.

    `litkb` goes through `litkb.ingest.connect()` — the ONE path to that login and its own passfile
    (`db.connect.ingest_passfile`), which `db.connect.connect()` refuses outright. A test database
    has no such line: the ingest role's pgpass entry names the database `litkb`
    (`db.provision._pgpass_db`), so there is no password for `litkb_test_w*` and there is not meant
    to be one. The suite reaches the role the way every other role test does — log in as the test
    database's owner and SET ROLE — so the privileges under test are the real ones.
    """
    from litkb.db import connect as c

    if dbname is None or dbname == c.DB_MAIN:
        from litkb import ingest as ingest_login

        return ingest_login.connect(dbname)
    if not c.is_test_db(dbname):
        raise RuntimeError(f"references_ingest: {dbname!r} is neither {c.DB_MAIN} nor a test database")
    conn = c.connect(dbname, "litkb_test", autocommit=True)
    conn.execute("SET ROLE litkb_ingest")
    return conn


def main(argv=None):
    import argparse
    import sys

    from litkb.db import connect as c

    ap = argparse.ArgumentParser(description="load stage 6's parked references into litkb")
    ap.add_argument("--db", default=c.DB_MAIN, help=f"database (default {c.DB_MAIN})")
    ap.add_argument("--derived", default=None,
                    help="the p6 artifact directory (default: <LITKB_DERIVED>/p6)")
    ap.add_argument("--only", action="append", default=None, metavar="STEM",
                    help="load only this citing stem (repeatable)")
    ap.add_argument("--host", default="local", choices=["local", "colab"])
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve and count; write nothing, not even a run row")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    conn = connect(a.db)
    try:
        report = load(conn, a.derived, only=a.only, dry_run=a.dry_run, host=a.host)
    finally:
        conn.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    main()
