"""The ACQUISITION-EVENT CONTRACT: one provenance shape for every bound file, and one verifier.

    from litkb.acquire import events
    events.record_url_landing(writer, ws, token, work_id, url=ref, sha256=sha, md5=md5,
                              nbytes=len(data), http_status=200, filed=store.rel(pdf))
    events.bound_without_event(conn, ws_id, since_utc)   -> [{file_id, work_id, sha256, ...}]

WHY IT EXISTS. Until 2026-09-20 a PDF could reach `litkb.file_versions` by two different doors and
only one of them wrote down how it got there.

  the ROUTE path   `litkb.acquire.run.acquire()` -> `land_and_attach()` -> `record_attempt()`,
                   which calls the SQL function `litkb.record_acquisition_attempt` presenting the
                   workstream token (the writer role holds NO direct INSERT on
                   `acquisition_attempts`, migration 0011). EVERY attempt leaves a row, success or
                   failure, carrying `route`, `identifier_used`, `status` and a `detail` jsonb.
  the URL path     `litkb.hunt.hunt()`'s web-source block: `_default_fetch` -> `land_download` ->
                   `file_under_key` -> `admit_web(pdf_path=...)`. It recorded NOTHING. A file bound
                   that way had a work, a version and a sha256, and no row anywhere saying which
                   URL it came from, what the server answered, or how many bytes arrived.

That is not a missing log line. `acquisition_attempts` is where the knowledge base answers "where
did this file come from", and a file with no row there is a file whose provenance is a story in a
session transcript. The S2 acceptance counter `operator_interventions` reads the verifier below
for exactly that reason: a bound file that arrived without an event is, by definition,
unaccounted-for, whether a human put it there or a code path forgot.

THE SHAPE, and every key in it (docs/SCHEMAS.md, "litkb.acquisition_attempts"):

    route            `hunt-url` -- this module's ROUTE constant. A value of its own, not
                     `browser`: `browser` means a HUMAN fetched the file and handed it in
                     (`acquire --from-file`), and folding an automated URL fetch into it would
                     make the manual-route reading of `operator_interventions` a lie. Widening
                     `acquisition_attempts_route_check` is what migration 0028 does.
    identifier_used  the URL, REDACTED. `record_attempt` redacts the DETAIL (`run._redacted`) and
                     not this column -- on the route path the column holds a DOI, which carries no
                     secret -- so the redaction happens at the one call site here, through the same
                     `litkb.netutil.redact` the route path already uses for `source_url`. No
                     second redaction rule is written anywhere in this module.
    status           `ok`. The URL path records an event only when a file is BOUND (below).
    detail           `sha256`, `md5`, `bytes`, `source_url`, `filed` -- the same five keys
                     `land_and_attach` writes for a route download -- plus `http_status`, which the
                     route path has no equivalent for (it records HTTP through the `http_codes`
                     column, which this path also fills with the one status it saw).

WHICH REFUSALS LEAVE NO EVENT, AND WHY THAT IS THE CONTRACT AND NOT A HOLE. The event is recorded
AFTER `admit_web` returns, because `acquisition_attempts` has no row shape for a file with neither
a work nor a candidate: its own CHECK is `work_id IS NOT NULL OR candidate_id IS NOT NULL`, and on
the URL path the candidate row is created BY the admission (`front.admit_web` -> `add_candidate`).
So these four refusals leave no event, and each already leaves its own record:

    fetch-failed                 nothing arrived. No bytes, no work, nothing bound.
    not-a-pdf / truncated-pdf    the bytes are in `_quarantine/` with a `.reason.json` beside them
                                 (`hunt.land_download`) -- the record of what arrived and why it
                                 was refused. Nothing is bound.
    incomplete-record            the document's first page did not yield title/author/year. The
                                 file sits in `_litkb_staging/incoming`. Nothing is bound.
    admission-refused            the checks refused the work. The PDF is filed, nothing is bound.

The contract is about BOUND FILES -- `bound_without_event` names a file version, and a refusal
before admission produces none -- so the four above are outside it by construction, not by
exemption. The verifier below is what makes that claim checkable rather than asserted: if any of
those paths ever DID bind a file, it would come back RED.

THE VERIFIER IS THE GATE, NOT THE WRITE. `record_url_landing` is called inside a `try` at its one
call site in `hunt.py`: a provenance row that cannot be written must not destroy an admitted,
bound, extracted work -- that would trade a missing record for a lost one. The failure is reported
in the hunt result (`acquisition_event.ok = false` with the error) and the file then comes back
from `bound_without_event` as an offence. A database that has not yet applied migration 0028 is
exactly this case, and it is the reason the swallow exists at all.
"""
import hashlib

#: The `route` value every URL-path landing is recorded under (migration 0028 widened the CHECK).
ROUTE = "hunt-url"

#: The `detail` keys this route writes. Five are `land_and_attach`'s own; `http_status` is this
#: path's addition. Pinned by
#: qc/test_litkb_hunt.py::test_a_url_hunt_records_an_acquisition_event_and_the_verifier_is_clean.
DETAIL_KEYS = ("sha256", "md5", "bytes", "source_url", "filed", "http_status")


def md5_of(data):
    """The md5 of the bytes that were downloaded. `land_and_attach` records one for every route
    download (it is the archive's own record key), so the URL path records the same fact rather
    than leaving one of the six keys empty for a reason a reader would have to guess."""
    return hashlib.md5(data).hexdigest()       # noqa: S324 -- a record key, never a credential


#: The detail keys the SNAPSHOT half of this route adds (S3, 2026-09-21). An HTML page and a PDF
#: both land through `hunt-url`, and the row has to say which arrived: `snapshot` is the boolean a
#: reader filters on and `content_type` is what the server actually declared -- the fact the
#: routing decision was made on (`litkb.extract.text_snapshot.classify`), kept beside the bytes it
#: was made about. They are OPTIONAL: a PDF landing writes the six keys it always wrote and
#: nothing else, so no row written before today needs re-reading.
#:
#: `sha256_raw` / `bytes_raw` ARE A SECOND PAIR OF HASHES, and that is the point. On this route the
#: bound file is the page's TEXT, so `sha256` -- the key :data:`BOUND_WITHOUT_EVENT_SQL` joins on,
#: and therefore the only one that can exonerate a binding -- has to be the text's. The HTML the
#: server actually sent is a different string of bytes and its hash would exonerate nothing; it is
#: recorded here, beside the text's, because it is the provenance of the extraction.
SNAPSHOT_DETAIL_KEYS = ("content_type", "snapshot", "sha256_raw", "bytes_raw")


def record_url_landing(conn, ws, token, work_id, *, url, sha256, md5, nbytes, http_status,
                       filed, content_type=None, snapshot=False, sha256_raw=None,
                       bytes_raw=None):
    """One `ok` acquisition event for a file the URL path landed and bound. -> the attempt id.

    Goes through `litkb.acquire.run.record_attempt` -- the SAME function the route path uses, so
    the token is presented and the detail is redacted in one place. `conn` must be the connection
    that holds EXECUTE on `litkb.record_acquisition_attempt`, which migration 0011 grants to
    `litkb_writer` alone; the call site hands it the writer connection `admit_web` just used.

    `snapshot` / `content_type` (S3, 2026-09-21): the bound file is a TEXT SNAPSHOT of an HTML page
    rather than the document itself. Two keys and not one, because they answer different questions
    -- what was bound, and what the server said it was serving -- and the second is the evidence
    for the first.
    """
    from litkb.netutil import redact

    from . import run

    detail = {"sha256": sha256, "md5": md5, "bytes": nbytes, "source_url": url,
              "filed": filed, "http_status": http_status}
    if snapshot or content_type:
        detail |= {"content_type": content_type, "snapshot": bool(snapshot),
                   "sha256_raw": sha256_raw, "bytes_raw": bytes_raw}
    codes = [int(http_status)] if str(http_status).isdigit() else []
    return run.record_attempt(conn, ws, token, work_id, ROUTE, redact(url), "ok", detail, codes)


#: Every file version this workstream bound after the instant, that no successful acquisition
#: attempt accounts for.
#:
#: TWO PREDICATES, and the second was missing until 2026-09-20. `detail->>'sha256'` is the join
#: rather than `file_id`, because the event is about the BYTES that arrived and the route path
#: records it before `attach_file` has returned a file id. But bytes alone are not the question
#: this asks: `a.work_id = fv.work_id` scopes the exoneration to the work the file is BOUND TO
#: (`file_versions.work_id`, the column `attach_file` writes and the one main's `main_files` view
#: reads), so an `ok` attempt recorded for some OTHER work -- in another workstream, in another
#: year -- cannot account for this binding.
#:
#: The first version deliberately left that out, reasoning that "a sha256 acquired once is
#: acquired". That reasoning was wrong in the direction that matters: the counter this feeds asks
#: whether THIS run's binding is accounted for, and a corpus that has ever fetched these bytes for
#: anything would otherwise exonerate a file bound to a different work with no fetch of its own --
#: which is precisely the hand-placed file the verifier exists to name.
#:
#: The attempt is still not scoped to the WORKSTREAM, and that is deliberate: a file acquired for
#: this work in an earlier workstream and re-bound here is accounted for, by an event that names
#: the same work and the same bytes.
BOUND_WITHOUT_EVENT_SQL = """
SELECT fv.file_id::text, fv.work_id::text, f.sha256, fv.version_id::text, fv.rel_path,
       fv.source_route, fv.created_at
  FROM litkb.file_versions fv
  JOIN litkb.files f ON f.id = fv.file_id
 WHERE fv.workstream_id = %(ws)s AND fv.created_at > %(since)s
   AND NOT EXISTS (SELECT 1 FROM litkb.acquisition_attempts a
                    WHERE a.status = 'ok' AND a.detail->>'sha256' = f.sha256
                      AND a.work_id = fv.work_id)
 ORDER BY fv.created_at, fv.file_id
"""

_COLS = ("file_id", "work_id", "sha256", "version_id", "rel_path", "source_route", "created_at")


def bound_without_event(conn, workstream_id, since_utc):
    """[{file_id, work_id, sha256, version_id, rel_path, source_route, created_at}] -- the files
    this workstream bound after `since_utc` with no `ok` acquisition attempt naming their bytes
    FOR THE WORK THEY ARE BOUND TO (see the two predicates above the SQL).

    EMPTY IS THE ONLY PASSING ANSWER. A non-empty list is what S2's `operator_interventions`
    counts and what S5 reuses: a file that is in the knowledge base and cannot say how it got
    there.

    `since_utc` is an AWARE datetime (`file_versions.created_at` is timestamptz; a naive one
    compares wall clocks and would silently answer for the wrong hour on a machine off UTC).
    Reads three tables `litkb_reader` has held SELECT on since migration 0006, so this needs no
    write role and no new grant.
    """
    rows = conn.execute(BOUND_WITHOUT_EVENT_SQL,
                        {"ws": str(workstream_id), "since": since_utc}).fetchall()
    return [dict(zip(_COLS, r)) for r in rows]
