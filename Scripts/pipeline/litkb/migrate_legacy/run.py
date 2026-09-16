"""The loaders. One workstream, one candidate per legacy row, admission through `litkb.admit.front`.

    ctx = Loader(conn, ws, token, agent=..., session=...)
    summary = load_tracker(ctx)
    summary = load_manifest(ctx)

Idempotence (P3's third kill): a row is identified by its candidate's `source_detail`
(`tracker ID <n>` / `manifest stem <s>`) inside this workstream. A second run finds that candidate and
does nothing at all — no candidate, no admission, no discrepancy, no use. That is a READ before the
write, never a bypass of a check.
"""
import datetime
import json

from litkb.admit import front, registry as _registry, resolver as _resolver
from litkb.migrate_legacy import sources
from litkb.migrate_legacy.plan import COMPARED_FIELDS, compare_row, doi_discrepancy, plan_row
from litkb.netutil import Client, Pacer
from litkb.migrate_legacy.export_shape import year_int
from litkb.textnorm import jsonb_safe

#: the tracker's Evidence grade, as the `confidence` of the use it produced. The grades are the
#: reviewer's READ grade (LITERATURE_CONVENTION.md), not a claim about the work, so they are carried
#: verbatim rather than mapped onto anything.
USE_KIND = "context"
USE_STATUS = "proposed"


class CachingClient(Client):
    """One HTTP GET per distinct registry URL per run, and the pacing that goes with it.

    The plan asks the registry whether the DOI confirms; `admit_registry` then asks again, because the
    database is given the registry evidence the client measured. Without this the load would make two
    paced calls per row. A cache HIT is not paced, because it is not a request.
    """

    def __init__(self, pacer=None, **kw):
        super().__init__(**kw)
        self.pacer = pacer or Pacer(interval=_resolver.REGISTRY_MIN_INTERVAL, backoff=_resolver.REGISTRY_BACKOFF)
        self._cache = {}
        self.requests = 0
        self.hits = 0

    def get(self, url, accept="text/html", timeout=120, follow=True, data=None, headers=None):
        if data is not None or not follow:
            return super().get(url, accept, timeout, follow, data, headers)
        key = (url, accept)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.pacer.wait()
        self.requests += 1
        self._cache[key] = super().get(url, accept, timeout, follow, None, headers)
        return self._cache[key]


class _NoWait:
    """The pacer handed to admission: the CachingClient above already paced every real request."""

    interval = 0.0

    def wait(self):
        return None

    def penalise(self, *a, **k):
        return None


class Loader:
    def __init__(self, conn, ws, token, *, agent, session, client=None, root=None, dry_run=False):
        self.conn, self.ws, self.token = conn, ws, token
        self.agent, self.session = agent, session
        self.client = client or CachingClient()
        self.pacer = _NoWait()
        self.root = root
        self.dry_run = dry_run
        self.log = []

    # ── registry access, bound to this run's client ──────────────────────────────────────
    def confirm(self, doi):
        return _registry.confirm_doi(self.client, doi, self.client.pacer)

    def resolve(self, title, surname, year):
        return _resolver.resolve_doi(title, surname, year, client=self.client, pacer=self.client.pacer)

    # ── the database, always through the token-checked functions ─────────────────────────
    def already_loaded(self, source_detail):
        row = self.conn.execute(
            "SELECT id, state, admitted_work_id FROM litkb.candidates "
            "WHERE workstream_id = %s AND source_detail = %s ORDER BY id LIMIT 1",
            (self.ws, source_detail)).fetchone()
        return row

    def discrepancy(self, source, source_row, field, d, *, work=None, candidate=None):
        # BEGIN guard: every disagreeing legacy field is recorded
        # jsonb_safe on the TEXT parameters too, not only the JSON: a registry record's author list or a
        # scanned PDF's metadata can carry a NUL, and Postgres refuses one in a text column outright
        # ("PostgreSQL text fields cannot contain NUL"), which would end the load rather than record the row.
        return self.conn.execute(
            "SELECT litkb.record_discrepancy(%s, %s, %s, %s, %s, %s, %s, %s::numeric, %s, %s, %s, %s, %s)",
            (self.ws, self.token, source, str(source_row), field,
             None if d.get("claimed") is None else jsonb_safe(str(d["claimed"])),
             None if d.get("registry") is None else jsonb_safe(str(d["registry"])),
             d.get("ratio"), front._jsonb(d.get("detail") or {}), work, candidate,
             self.agent, self.session)).fetchone()[0]
        # END guard: every disagreeing legacy field is recorded

    def hold(self, candidate_id, reason):
        # BEGIN guard: a held candidate records WHY it is held
        # Referee P3 F6: every held candidate carried `state_reason IS NULL`, so why a row was held had to be
        # inferred from the absence of an admission. The loader knows it exactly — it is the case the case
        # table decided — and migration 0016 gives it the one writer that may say so.
        return self.conn.execute("SELECT litkb.hold_candidate(%s, %s, %s, %s)",
                                 (self.ws, self.token, candidate_id, reason)).fetchone()[0]
        # END guard: a held candidate records WHY it is held

    def refused_file(self, candidate_id):
        """The file id a refused admission collided with, if it was refused on the file's sha256."""
        r = self.conn.execute(
            "SELECT checks ->> 'file_duplicate' FROM litkb.admissions WHERE candidate_id = %s "
            "AND state = 'refused' ORDER BY id DESC LIMIT 1", (candidate_id,)).fetchone()
        return r[0] if r and r[0] else None

    def work_authors(self, work_id):
        r = self.conn.execute("SELECT v.authors FROM litkb.ws_works v WHERE v.work_id = %s "
                              "AND v.view_workstream_id = %s", (work_id, self.ws)).fetchone()
        return r[0] if r else None

    def is_proposed(self, work_id):
        """A work admitted by the MANUAL route: its author list was parsed, not read from a registry."""
        return bool(self.conn.execute(
            "SELECT 1 FROM litkb.admissions WHERE work_id = %s AND route = 'manual' LIMIT 1", (work_id,)).fetchone())

    def work_for_stem(self, stem):
        r = self.conn.execute(
            "SELECT v.work_id FROM litkb.identifiers i JOIN litkb.identifier_versions v ON v.identifier_id = i.id "
            "WHERE i.scheme = 'legacy_stem' AND i.value_norm = %s LIMIT 1", (stem,)).fetchone()
        return r[0] if r else None

    def use_for(self, work_id):
        """This workstream's use on that work, if it wrote one. A READ before the write, so a resumed load
        never writes a second copy of the same use."""
        return self.conn.execute(
            "SELECT u.id FROM litkb.uses u JOIN litkb.use_versions v ON v.use_id = u.id "
            "WHERE u.work_id = %s AND v.workstream_id = %s LIMIT 1", (work_id, self.ws)).fetchone()

    def record_use(self, work_id, row):
        """The tracker's Relevance / Evidence grade / Feeds / Notes as a use version (design §4.5).

        State `proposed`, kind `context`: P3 carries what the tracker asserted, and asserts nothing new.
        No evidence pointer is attached — evidence needs a verified quote against an extracted block, and
        blocks arrive in P5 (design §14). A use with no quote therefore has no `use_evidence` row, rather
        than an unverified one.
        """
        statement = (row.get("Relevance (max 3 sentences)") or "").strip()
        feeds = sources.feeds_tokens(row.get("Feeds"))
        notes = (row.get("Notes") or "").strip()
        grade = (row.get("Evidence grade") or "").strip()
        if not statement and not feeds:
            return None
        fields = {"statement": statement or f"tracker row {row['ID']}: no relevance recorded",
                  "kind": USE_KIND, "status": USE_STATUS, "feeds": feeds,
                  "confidence": grade or None,
                  "rationale": "; ".join(x for x in (f"tracker Evidence grade: {grade}" if grade else "",
                                                     f"tracker Status: {row.get('Status')}" if row.get("Status") else "",
                                                     f"tracker Notes: {notes}" if notes else "") if x) or None}
        return self.conn.execute(
            "SELECT * FROM litkb.write_proposal(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            # str(): the admission path hands back a work id from JSON, the resume path reads a uuid object
            ("use", None, front._jsonb({"work_id": str(work_id), "gap_id": None}), None, front._jsonb(fields),
             None, self.ws, self.token, self.agent, self.session)).fetchone()


def _key_for(ctx, rec, claimed):
    """The work key this row should take, or None to let `admit_registry` build it.

    It does NOT resolve a collision. `works.key` is `Surname_Year_slug` with the slug taken from the first
    four non-stopword title words, so a bulk load of 460 rows meets two papers by one author in one year on
    one subject — and the DATABASE already answers that: migration 0014 (referee fix D5) retries the key
    with the convention's `a` and `b` year suffixes before refusing. An earlier version of this function
    duplicated that rule in Python; the mutation harness caught it, because removing the Python copy changed
    nothing (CLAUDE.md 3.3, one fact one home). The key is built here only so it comes from the same title
    and first author the comparison used.
    """
    from litkb.admit.front import make_key
    from litkb.admit.registry import work_title

    first = rec["first_author"] if rec else front.first_author_of(claimed.get("authors"))
    year = (rec or {}).get("year") or year_int(claimed.get("year")) or 0
    # the WORK's title — the registry title joined with its subtitle (registry.work_title, 2026-09-15).
    # The key is derived from the work's title; deriving it from the BARE one here would mint a
    # different key from the same record, which is the Konda_2016_magellan-work defect one layer down.
    title = (work_title(rec) if rec else "") or claimed.get("title") or ""
    try:
        return make_key(first, year, title)
    except (TypeError, ValueError):
        return None


def _counter():
    return {"rows": 0, "skipped_already_loaded": 0, "admitted": 0, "bound": 0, "duplicate": 0,
            "duplicate_review": 0, "proposed": 0, "refused": 0, "binding_pending": 0, "binding_failed": 0,
            "held_no_identity": 0, "held_no_file": 0, "discrepancies": 0, "uses": 0,
            "by_case": {}, "refused_at": {}}


def _bump(c, k, n=1):
    c[k] = c.get(k, 0) + n


def load_tracker(ctx, rows=None, manifest=None, *, limit=None, only_ids=None):
    """Every tracker row, in ID order. -> a summary dict; per-row detail is in `ctx.log`."""
    rows = rows if rows is not None else sources.tracker_rows()
    manifest = manifest if manifest is not None else sources.manifest_by_stem(root=ctx.root)
    c = _counter()
    for row in rows:
        if only_ids and row["ID"] not in {str(i) for i in only_ids}:
            continue
        if limit is not None and c["rows"] >= limit:
            break
        c["rows"] += 1
        _load_tracker_row(ctx, row, manifest, c)
    return c


def _load_tracker_row(ctx, row, manifest, c):
    tid = row["ID"]
    detail = f"tracker ID {tid}"
    seen = ctx.already_loaded(detail)
    if seen:
        c["skipped_already_loaded"] += 1
        # BEGIN guard: a resumed load finishes a row it had already admitted but not finished
        # The row's candidate exists, so nothing is admitted again. What CAN be missing is its use: a load
        # interrupted between the admission and the use version, or (the live run of 2026-09-15) rows loaded
        # before deduped rows were given uses at all. Writing it here is idempotent — `use_for` finds the one
        # already written — so a correct first run still leaves the second run nothing to do.
        if seen[2] is not None and not (row.get("Duplicate of") or "").strip() and not ctx.use_for(seen[2]):
            if ctx.record_use(seen[2], row) is not None:
                c["uses_backfilled"] = c.get("uses_backfilled", 0) + 1
        stem_seen = (row.get("File stem") or "").strip()
        held_file = ctx.refused_file(seen[0])
        late = []
        if stem_seen and held_file:
            late += _collision_pending(ctx, {"refused_at": "file_duplicate", "file_id": held_file}, stem_seen, tid)
        if stem_seen:
            late += _missing_file_pending(ctx, manifest.get(stem_seen), sources.pdf_for(stem_seen, root=ctx.root),
                                          stem_seen, tid)
        late += _dropped_arxiv_pending(sources.identifiers_of(row)[1] or (manifest.get(stem_seen) or {}).get("arxiv"),
                                       "tracker", tid)
        if seen[2] is not None and ctx.is_proposed(seen[2]):
            late += _manual_authors_pending(row.get("Author(s)"), ctx.work_authors(seen[2]), "tracker", tid)
        for src, key, field, d in late:
            ctx.discrepancy(src, key, field, d, work=seen[2], candidate=None if seen[2] else seen[0])
            c["file_records_backfilled"] = c.get("file_records_backfilled", 0) + 1
        # END guard: a resumed load finishes a row it had already admitted but not finished
        ctx.log.append({"tracker_id": tid, "outcome": "already-loaded", "candidate_id": str(seen[0]),
                        "candidate_state": seen[1]})
        return
    doi, arxiv = sources.identifiers_of(row)
    claimed = sources.claimed_of(row)
    stem = (row.get("File stem") or "").strip()
    mrow = manifest.get(stem)
    pdf = sources.pdf_for(stem, root=ctx.root)
    plan = plan_row(doi=doi, arxiv=arxiv, claimed=claimed, has_file=pdf is not None,
                    confirm=ctx.confirm, resolve=ctx.resolve)
    _bump(c["by_case"], plan["case"])
    cand = front.add_candidate(
        ctx.conn, ctx.ws, ctx.token, source="manual", source_detail=detail,
        # the candidate's raw_record is the legacy row VERBATIM — the one home for the tracker fields the
        # data model has no column for (Search Phase, Status, Read date, Bib line, Duplicate of) and, under
        # `_manifest`, the manifest row's own columns (source_route, obtained_date, cited_by). The export
        # reads both back; without them those cells could not be regenerated at all.
        raw=json.loads(json.dumps({**row, **({"_manifest": mrow} if mrow else {})})),
        title=jsonb_safe(claimed["title"]), authors=[claimed["authors"]] if claimed["authors"] else None,
        year=year_int(claimed["year"]), ids={k: v for k, v in (("doi", doi), ("arxiv", arxiv)) if v})
    entry = {"tracker_id": tid, "case": plan["case"], "shape": plan["shape"], "candidate_id": str(cand),
             "stem": stem or None, "doi": plan["doi"], "resolved_doi": plan["resolved"]}

    # ── the discrepancies: every disagreeing field. Measured BEFORE the admission (the comparison is
    # what decides the shape), written AFTER it, so each one names the work it belongs to when there is one.
    pending = _field_discrepancies(plan, doi, "tracker", tid)
    if (row.get("Duplicate of") or "").strip():
        pending.append(("tracker", tid, "duplicate_of",
                        {"claimed": row["Duplicate of"], "registry": None, "ratio": None,
                         "detail": {"tracker_status": row.get("Status")}}))
    if mrow and plan["record"] is not None:
        # the manifest row states its OWN title, authors, year, venue and DOI, and they can differ from both
        # the tracker's claim and the registry. Compared and recorded separately, or the manifest export's
        # diff would carry differences nothing explains.
        mclaim = {"title": mrow.get("title") or "", "authors": mrow.get("authors") or "",
                  "year": mrow.get("year") or "", "venue": mrow.get("venue") or ""}
        pending += _field_discrepancies(plan, mrow.get("doi"), "manifest", stem,
                                        fields=compare_row(plan["record"], mclaim))

    # ── the admission ────────────────────────────────────────────────────────────────────
    ids_extra = [{"scheme": "tracker", "value": str(tid), "verified_by": None,
                  "evidence": {"source": "Reports/literature_tracker.csv", "row": tid,
                               "loaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}}]
    if stem:
        ids_extra.append({"scheme": "legacy_stem", "value": stem, "verified_by": None,
                          "evidence": {"source": str(sources.manifest_path(ctx.root)), "stem": stem}})
    res = None
    if plan["shape"] == "held":
        # BEGIN guard: a row with no verified file and a claim the registry contradicts is HELD, never admitted
        if plan["case"] == "E":
            c["held_no_identity"] += 1                       # nothing resolved AND no file to bind
            entry["outcome"] = "held-no-identity"
        else:
            c["held_no_file"] += 1                           # the DOI confirms; the claim does not, and no file
            entry["outcome"] = "held-needs-file"
        ctx.hold(cand, HELD_REASONS[entry["outcome"]])
        # END guard: a row with no verified file and a claim the registry contradicts is HELD, never admitted
    elif plan["shape"] == "manual":
        res = front.admit_manual(
            ctx.conn, ctx.ws, ctx.token, title=claimed["title"], authors=claimed["authors"],
            year=year_int(claimed["year"]), file_path=str(pdf), source_note=f"{detail} (no registry record)",
            identifiers=[{"scheme": i["scheme"], "value": i["value"]} for i in ids_extra],
            key=_key_for(ctx, None, claimed), root=ctx.root, agent=ctx.agent, session=ctx.session,
            candidate_id=cand)
    else:
        res = front.admit_registry(
            ctx.conn, ctx.ws, ctx.token, doi=plan["doi"], arxiv=None,
            claimed=claimed if plan["shape"] == "claimed" else None,
            file_path=str(pdf) if pdf else None, root=ctx.root, agent=ctx.agent, session=ctx.session,
            client=ctx.client, pacer=ctx.pacer, candidate_id=cand, source_detail=detail,
            key=_key_for(ctx, plan["record"], claimed), extra_identifiers=ids_extra)
    work = None
    if res is not None:
        entry["outcome"] = res["outcome"]
        _record_outcome(c, res)
        if res["outcome"] == "duplicate":
            # the discrepancies belong to the work this row duplicates, not to a candidate with no work
            work = res.get("work_id")
        if res.get("work_id") and res["outcome"] in ("admitted", "proposed"):
            work = res["work_id"]
            c["admitted" if res["outcome"] == "admitted" else "proposed"] += 1
            if res.get("file_id"):
                c["bound"] += 1
    # BEGIN guard: a row that reached a work records its use, DEDUPED rows included
    # A row whose DOI was already admitted (one of the 30 works P2 and the pre-1990 run left, or an earlier
    # tracker row) comes back `duplicate` and is NOT re-admitted — but it still carries the tracker's
    # Relevance, grade and Feeds, and that is exactly what a use version is for. A `Duplicate of` row is the
    # one exception: the tracker keeps the payload on the original row only.
    if work is not None and not (row.get("Duplicate of") or "").strip():
        if ctx.record_use(work, row) is not None:
            c["uses"] += 1
            entry["use"] = True
    # END guard: a row that reached a work records its use, DEDUPED rows included
    # BEGIN guard: a file another work already holds is recorded as a sha256 collision
    pending += _collision_pending(ctx, res, stem, tid)
    pending += _missing_file_pending(ctx, mrow, pdf, stem, tid)
    pending += _dropped_arxiv_pending(arxiv or (mrow or {}).get("arxiv"), "tracker", tid)
    if res is not None and res.get("outcome") == "proposed":
        pending += _manual_authors_pending(claimed["authors"], ctx.work_authors(res["work_id"]), "tracker", tid)
    # END guard: a file another work already holds is recorded as a sha256 collision
    entry["discrepancies"] = _flush(ctx, c, pending, work, cand)
    ctx.log.append(entry)


def _dropped_arxiv_pending(arxiv, source, key):
    """An arXiv id the legacy row carries that P3 does not admit.

    P2 judgement 5: an unverified extra strong identifier refuses the WHOLE registry admission, and the arXiv
    API answers 429 often enough that P3 would lose confirmed works to it. So the loader admits on the DOI and
    passes `arxiv=None` — which drops a cell the legacy row filled. The id is kept verbatim on the candidate's
    raw record, and this says where it went. Confirming them is a P4-or-later pass.
    """
    if not (arxiv or "").strip():
        return []
    # BEGIN guard: an arXiv id the load does not admit is recorded, never just dropped
    return [(source, str(key), "arxiv",
             {"claimed": arxiv.strip(), "registry": None, "ratio": None,
              "detail": {"meaning": "the legacy row carries this arXiv id; P3 admitted the work on its DOI "
                                    "alone, because an unverified strong identifier refuses the whole "
                                    "admission (P2 judgement 5). The id is unconfirmed, not lost."}})]
    # END guard: an arXiv id the load does not admit is recorded, never just dropped


def _manual_authors_pending(claimed_authors, work_authors, source, key):
    """A manual admission's author list is a LOSSY read of the legacy cell.

    `admit_manual` splits the claimed string on `&`, `;` and ` and ` only, so `A, B, C & D` becomes two names,
    and `A et al.` becomes one. That is P2's parser and P3 does not replace it — but the export then prints
    fewer authors than the legacy row, and every difference the export prints needs a record.
    """
    from litkb.migrate_legacy.export_shape import authors_line, norm_cell

    printed = authors_line(work_authors)
    if not claimed_authors or norm_cell(claimed_authors) == norm_cell(printed):
        return []
    # BEGIN guard: a manual admission's lossy author parse is recorded
    return [(source, str(key), "authors",
             {"claimed": claimed_authors, "registry": printed, "ratio": None,
              "detail": {"meaning": "no registry record confirmed this work, so its author list was parsed "
                                    "from the legacy cell; the parser splits on '&', ';' and ' and ' only"}})]
    # END guard: a manual admission's lossy author parse is recorded


def _missing_file_pending(ctx, mrow, pdf, stem, source_row):
    """A legacy row that names a file the topic folder does not hold.

    Two kinds, and the row cannot tell them apart, so it records what it can SEE — that the named file is not
    in the store — and names the sha256 the row claims, which is the handle the review needs:

      * the file was never there (Matheron 1986: its `filed_stem` exists nowhere under the pipeline root,
        Reports/LITKB_EDGE_PRE1990_2026-09-14.md);
      * the file was QUARANTINED because it is not the paper its row names. Stage 0's inventory found two such
        sha256s, each claimed by two manifest rows — the archive served one md5 for two DOIs — and its
        referee's first-page reads showed the bytes are a THIRD paper in both cases, so neither claimant may
        bind. Which paper each file actually is lives in Reports/LITKB_INVENTORY_2026-09-15.md, not here.

    Either way the work is admitted on its registry record and stays UNBOUND, which is the honest state: no
    verified file. Binding would refuse these anyway; this is the record that says why nothing was offered.
    """
    if not mrow or pdf is not None:
        return []
    # BEGIN guard: a legacy row naming a file the store does not hold is recorded
    return [("manifest", stem or str(source_row), "file_missing",
             {"claimed": (mrow.get("sha256") or "").strip() or None, "registry": None, "ratio": None,
              "detail": {"stem": stem, "source_route": mrow.get("source_route"),
                         "meaning": "the manifest names this file but the topic folder does not hold it: it "
                                    "was never there, or it was quarantined as not being this paper. The work "
                                    "is admitted unbound; see Reports/LITKB_INVENTORY_2026-09-15.md"}})]
    # END guard: a legacy row naming a file the store does not hold is recorded


def _collision_pending(ctx, res, stem, source_row):
    """A legacy row whose file is ALREADY HELD by another work — one sha256, two manifest rows.

    Stage 0's inventory (Reports/LITKB_INVENTORY_2026-09-15.md) found two: Chen 2024 / Song 2026 and
    Stehman 2022 / Xing 2024, both from the archive serving one md5 for two DOIs. The database already refuses
    the second admission on `files.sha256` being unique, so ONE file can never bind to two works — and which
    work keeps it is decided by BINDING, not by tracker order: the file's first page carries one registry
    title, so the other work's admission fails check 3 whichever is tried first.

    What was missing is the record. Without it the second work is simply unbound and nothing says why.
    """
    if not res or res.get("refused_at") != "file_duplicate":
        return []
    held_by = ctx.conn.execute(
        "SELECT w.key FROM litkb.files f JOIN litkb.file_versions v ON v.version_id = f.current_version_id "
        "JOIN litkb.works w ON w.id = v.work_id WHERE f.id = %s", (res.get("file_id"),)).fetchone()
    sha = ctx.conn.execute("SELECT sha256 FROM litkb.files WHERE id = %s", (res.get("file_id"),)).fetchone()
    return [("manifest", stem or str(source_row), "sha256_collision",
             {"claimed": stem or str(source_row), "registry": (held_by or [None])[0], "ratio": None,
              "detail": {"sha256": (sha or [None])[0], "file_id": str(res.get("file_id")),
                         "meaning": "this legacy row names a file another work already holds; the file stays "
                                    "with the work whose registry title it binds to, and this work is unbound"}})]


def _field_discrepancies(plan, spelled_doi, source, key, fields=None):
    """(source, key, field, d) for every compared field the legacy row and the registry DISAGREE on.

    The predicate is `differs` (plain normalised inequality), never `agrees` (check-1 acceptability).
    decisions.yaml: "every tracker or manifest field that disagrees with the registry is kept as a flagged
    discrepancy" — a title accepted at ratio 0.92 still prints differently in the export from what the
    tracker says today, and the diff gate has nothing to explain that difference with unless it is recorded.
    """
    out = []
    fields = plan["fields"] if fields is None else fields
    for name in COMPARED_FIELDS:
        if name == "doi":
            d = doi_discrepancy(spelled_doi, plan["doi"]) if plan["doi"] else None
        else:
            f = (fields or {}).get(name)
            d = None if (f is None or not f.get("differs")) else f
        if d:
            out.append((source, key, name, d))
    return out


def _flush(ctx, c, pending, work, candidate):
    """Write the measured discrepancies. `work` when the row was admitted, else the candidate — either way
    the row is recorded, which is the whole point of the flag (decisions.yaml: nothing dropped)."""
    names = []
    for source, key, name, d in pending:
        ctx.discrepancy(source, key, name, d, work=work, candidate=None if work else candidate)
        c["discrepancies"] += 1
        names.append(f"{source}:{name}")
    return names


#: why a row is HELD, in the case table's own terms. ONE home, read by both loaders (referee P3 F6): a held
#: candidate's `state_reason` is the only place the reason is written down, and it must say which case held it.
HELD_REASONS = {
    "held-no-identity": "case E: nothing resolved — no DOI the registry confirms, and title + first author + "
                        "year resolve to no record — and no file is held, so there is nothing to propose on",
    "held-needs-file": "case C: the registry confirms the DOI but contradicts the row's claim, and no file is "
                       "held to bind — admitting it would bypass check 1 (0013 _check_registry)",
}


def _record_outcome(c, res):
    o = res["outcome"]
    if o == "duplicate":
        c["duplicate"] += 1
    elif o == "duplicate-review":
        c["duplicate_review"] += 1
    elif o in ("refused", "collided"):
        c["refused"] += 1
        at = res.get("refused_at") or res.get("constraint") or "unknown"
        _bump(c["refused_at"], str(at))
        verdict = ((res.get("checks") or {}).get("check3_binding") or {}).get("verdict")
        if verdict == "binding-pending":
            c["binding_pending"] += 1
        elif verdict == "binding-failed":
            c["binding_failed"] += 1


def load_manifest(ctx, rows=None, *, limit=None):
    """Manifest rows with no tracker row of their own: the held file is the identity, bound in place.

    A manifest row whose stem already reached the database through a tracker row is not loaded again —
    its file is already bound, and a second admission would collide on the file's sha256.
    """
    rows = rows if rows is not None else sources.manifest_rows(root=ctx.root)
    c = _counter()
    for row in rows:
        if limit is not None and c["rows"] >= limit:
            break
        c["rows"] += 1
        _load_manifest_row(ctx, row, c)
    return c


def _load_manifest_row(ctx, row, c):
    stem = row["stem"]
    detail = f"manifest stem {stem}"
    seen = ctx.already_loaded(detail)
    if seen or _stem_held(ctx, stem):
        c["skipped_already_loaded"] += 1
        # BEGIN guard: a resumed manifest load records what an earlier pass could not
        work = seen[2] if seen else ctx.work_for_stem(stem)
        late = _dropped_arxiv_pending(row.get("arxiv"), "manifest", stem)
        late += _missing_file_pending(ctx, row, sources.pdf_for(stem, root=ctx.root), stem, stem)
        if work is not None and ctx.is_proposed(work):
            late += _manual_authors_pending(row.get("authors"), ctx.work_authors(work), "manifest", stem)
        for src, key, field, d in late:
            ctx.discrepancy(src, key, field, d, work=work, candidate=None if work else (seen[0] if seen else None))
            c["file_records_backfilled"] = c.get("file_records_backfilled", 0) + 1
        # END guard: a resumed manifest load records what an earlier pass could not
        ctx.log.append({"stem": stem, "outcome": "already-loaded"})
        return
    pdf = sources.pdf_for(stem, root=ctx.root)
    claimed = {"title": row.get("title") or "", "authors": row.get("authors") or "",
               "year": row.get("year") or "", "venue": row.get("venue") or ""}
    plan = plan_row(doi=row.get("doi"), arxiv=row.get("arxiv") or None, claimed=claimed,
                    has_file=pdf is not None, confirm=ctx.confirm, resolve=ctx.resolve)
    _bump(c["by_case"], plan["case"])
    cand = front.add_candidate(ctx.conn, ctx.ws, ctx.token, source="manual", source_detail=detail,
                               raw=json.loads(json.dumps(row)), title=claimed["title"],
                               authors=[claimed["authors"]] if claimed["authors"] else None,
                               year=year_int(claimed["year"]),
                               ids={k: v for k, v in (("doi", row.get("doi")), ("arxiv", row.get("arxiv"))) if v})
    entry = {"stem": stem, "case": plan["case"], "shape": plan["shape"], "candidate_id": str(cand)}
    pending = _field_discrepancies(plan, row.get("doi"), "manifest", stem)
    if pdf is not None and row.get("sha256"):
        from litkb.acquire.store import file_facts
        on_disk = file_facts(pdf)["sha256"]
        # BEGIN guard: a manifest sha256 that is not the file on disk is a discrepancy, never a silent pass
        if on_disk != row["sha256"].strip().lower():
            pending.append(("manifest", stem, "sha256",
                            {"claimed": row["sha256"], "registry": on_disk, "ratio": None,
                             "detail": {"measured": "file_facts on the held PDF"}}))
        # END guard: a manifest sha256 that is not the file on disk is a discrepancy, never a silent pass
    ids_extra = [{"scheme": "legacy_stem", "value": stem, "verified_by": None,
                  "evidence": {"source": str(sources.manifest_path(ctx.root)), "stem": stem}}]
    res = None
    if plan["shape"] == "held":
        if plan["case"] == "E":
            c["held_no_identity"] += 1
            entry["outcome"] = "held-no-identity"
        else:
            c["held_no_file"] += 1
            entry["outcome"] = "held-needs-file"
        ctx.hold(cand, HELD_REASONS[entry["outcome"]])
    elif plan["shape"] == "manual":
        res = front.admit_manual(ctx.conn, ctx.ws, ctx.token, title=claimed["title"], authors=claimed["authors"],
                                 year=year_int(claimed["year"]), file_path=str(pdf),
                                 source_note=f"{detail} (no registry record)",
                                 identifiers=[{"scheme": "legacy_stem", "value": stem}],
                                 key=_key_for(ctx, None, claimed), root=ctx.root, agent=ctx.agent,
                                 session=ctx.session, candidate_id=cand)
    else:
        res = front.admit_registry(ctx.conn, ctx.ws, ctx.token, doi=plan["doi"], arxiv=None,
                                   claimed=claimed if plan["shape"] == "claimed" else None,
                                   file_path=str(pdf) if pdf else None, root=ctx.root, agent=ctx.agent,
                                   session=ctx.session, client=ctx.client, pacer=ctx.pacer,
                                   candidate_id=cand, source_detail=detail,
                                   key=_key_for(ctx, plan["record"], claimed), extra_identifiers=ids_extra)
    work = None
    if res is not None:
        entry["outcome"] = res["outcome"]
        _record_outcome(c, res)
        if res["outcome"] in ("admitted", "proposed"):
            work = res.get("work_id")
            c["admitted" if res["outcome"] == "admitted" else "proposed"] += 1
            if res.get("file_id"):
                c["bound"] += 1
    pending += _collision_pending(ctx, res, stem, stem)
    pending += _missing_file_pending(ctx, row, pdf, stem, stem)
    pending += _dropped_arxiv_pending(row.get("arxiv"), "manifest", stem)
    if res is not None and res.get("outcome") == "proposed":
        pending += _manual_authors_pending(claimed["authors"], ctx.work_authors(res["work_id"]), "manifest", stem)
    entry["discrepancies"] = _flush(ctx, c, pending, work, cand)
    ctx.log.append(entry)


def _stem_held(ctx, stem):
    return bool(ctx.conn.execute(
        "SELECT 1 FROM litkb.identifiers i JOIN litkb.identifier_versions v ON v.identifier_id = i.id "
        "WHERE i.scheme = 'legacy_stem' AND i.value_norm = %s LIMIT 1", (stem,)).fetchone())
