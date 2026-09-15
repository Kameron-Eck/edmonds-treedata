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
        return self.conn.execute(
            "SELECT litkb.record_discrepancy(%s, %s, %s, %s, %s, %s, %s, %s::numeric, %s, %s, %s, %s, %s)",
            (self.ws, self.token, source, str(source_row), field,
             None if d.get("claimed") is None else str(d["claimed"]),
             None if d.get("registry") is None else str(d["registry"]),
             d.get("ratio"), front._jsonb(d.get("detail") or {}), work, candidate,
             self.agent, self.session)).fetchone()[0]
        # END guard: every disagreeing legacy field is recorded

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
            ("use", None, front._jsonb({"work_id": work_id, "gap_id": None}), None, front._jsonb(fields),
             None, self.ws, self.token, self.agent, self.session)).fetchone()


def free_key(conn, base):
    """`Surname_Year_slug`, with the convention's a/b/c suffix when that key is already a work's.

    LITERATURE_CONVENTION.md: "An `a`/`b` suffix is used ONLY to break a same-surname, same-year collision
    (`Smith_2019a_…`) — never as a versioning convention." A bulk load of 460 rows meets that collision: the
    key's slug is the first four non-stopword title words, so two papers by one author in one year on one
    subject land on the same key, and `works.key` is unique. Without this the second is refused as a
    collision and lost. This is a READ before the write, not a bypass of a check.
    """
    import re as _re

    if not conn.execute("SELECT 1 FROM litkb.works WHERE key = %s", (base,)).fetchone():
        return base
    m = _re.match(r"^([A-Za-z]+)_([0-9]{4})_(.*)$", base)
    if not m:
        return base
    # `a` and `b` are all the key's CHECK constraint allows (migration 0001, `works.key`), so a FOURTH work
    # on the same surname/year/slug is refused as a collision and reported — never renamed into an
    # unconventional key.
    for letter in "ab":
        cand = f"{m.group(1)}_{m.group(2)}{letter}_{m.group(3)}"[:59]
        if not conn.execute("SELECT 1 FROM litkb.works WHERE key = %s", (cand,)).fetchone():
            return cand
    return base


def _key_for(ctx, rec, claimed):
    from litkb.admit.front import make_key

    first = rec["first_author"] if rec else front.first_author_of(claimed.get("authors"))
    year = (rec or {}).get("year") or claimed.get("year") or 0
    title = (rec or {}).get("title") or claimed.get("title") or ""
    try:
        base = make_key(first, year, title)
    except (TypeError, ValueError):
        return None
    return free_key(ctx.conn, base)


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
        title=claimed["title"], authors=[claimed["authors"]] if claimed["authors"] else None,
        year=claimed["year"] or None, ids={k: v for k, v in (("doi", doi), ("arxiv", arxiv)) if v})
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
        # END guard: a row with no verified file and a claim the registry contradicts is HELD, never admitted
    elif plan["shape"] == "manual":
        res = front.admit_manual(
            ctx.conn, ctx.ws, ctx.token, title=claimed["title"], authors=claimed["authors"],
            year=claimed["year"] or None, file_path=str(pdf), source_note=f"{detail} (no registry record)",
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
            if ctx.record_use(work, row) is not None:
                c["uses"] += 1
                entry["use"] = True
    entry["discrepancies"] = _flush(ctx, c, pending, work, cand)
    ctx.log.append(entry)


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
    if ctx.already_loaded(detail) or _stem_held(ctx, stem):
        c["skipped_already_loaded"] += 1
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
                               year=claimed["year"] or None,
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
    elif plan["shape"] == "manual":
        res = front.admit_manual(ctx.conn, ctx.ws, ctx.token, title=claimed["title"], authors=claimed["authors"],
                                 year=claimed["year"] or None, file_path=str(pdf),
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
    entry["discrepancies"] = _flush(ctx, c, pending, work, cand)
    ctx.log.append(entry)


def _stem_held(ctx, stem):
    return bool(ctx.conn.execute(
        "SELECT 1 FROM litkb.identifiers i JOIN litkb.identifier_versions v ON v.identifier_id = i.id "
        "WHERE i.scheme = 'legacy_stem' AND i.value_norm = %s LIMIT 1", (stem,)).fetchone())
