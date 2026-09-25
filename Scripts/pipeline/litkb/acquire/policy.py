"""The acquisition ladder's vocabulary, its pre-fetch policy and its budget: ONE Python home for each
(LITKB_WORKPLAN.md "### S4.5" item 2; S4.5 CONTRACTS "The route vocabulary", "The sub_status
vocabulary"; migration 0033, which holds the database's CHECKs equal to the tuples here —
qc/test_litkb_ledger.py::test_the_0033_checks_are_the_python_vocabularies).

Every mechanism here is a RELAYED design (CLAUDE.md §3.4c): read in other codebases by the PDF-sources
survey (Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md §1, guards 12, 14, 17, 21, 23) and UNVALIDATED
until an independent referee scores it on the rows the plan names.

  ROUTES_ALL        every route an attempt row may carry (CONTRACTS list; 0033's route CHECK)
  STAGES / STAGE_OF the ladder's stages in order and which stage a rung route belongs to
  SUB_STATUSES      status -> the sub-statuses that status may carry (0033's sub_status CHECK)
  KINDS             what kind of content an attempt obtained (survey §3.4)
  COPY_KIND_OF_VERSION  a route's article version -> file_versions.copy_kind (guard 23, no new column)
  POLICY / decide() the pre-fetch PolicyDecision (guard 21): one auditable line per rung/host, the
                    shadow tier a one-line switch, a single line switched off with its reason
                    (`PolicyLine.off_why`, S4.5 decision D39), returned BEFORE any request and recorded
                    on the attempt row that follows it
  LadderBudget      the declarative budget over the whole ladder (guard 12): total seconds, attempts,
                    concurrency, checked between every stage and rung; exhaustion writes a
                    `budget-stop` row, never silence
"""
import time
from dataclasses import asdict, dataclass, field

# ── routes ──────────────────────────────────────────────────────────────────────────────────
#: Every route an `acquisition_attempts` row may carry, in the order 0033's CHECK lists them
#: (S4.5 CONTRACTS "The route vocabulary 0033's CHECK holds"). A builder that needs a route not on
#: this list stops and asks: widening the CHECK needs a migration number.
ROUTES_ALL = (
    "open_access", "annas", "scihub", "browser", "hunt-url",
    "ladder",
    "arxiv", "openalex", "crossref-link", "s2", "datacite", "core", "doaj", "openaire", "osf",
    "europepmc", "venue", "zenodo", "hal", "figshare", "opencitations", "ncbi-idconv",
    "eartharxiv", "publisher-url",
    "landing",
    "bban",
    "wayback", "ia", "commoncrawl")

#: The ladder's stages in the order they run (plan item 2 / S4.5 brief C1a: Stage A, Stage B
#: concurrent, Stage C, Stage E, the shadow tier LAST — `litkb-shadow-hosts`: "the tier runs only
#: after every legitimate rung has missed").
STAGES = ("A", "B", "C", "E", "shadow")

#: Which stage each rung route belongs to (PDF-sources survey §1's stage letters; CONTRACTS names
#: B1-B14 as Stage B, A4/A7 as Stage A, Stage C's `landing`, E1/E3/E5). `open_access` (Unpaywall's
#: OA locations and the arXiv copy) is a metadata fan-out rung, so Stage B. `browser`, `hunt-url`
#: and `ladder` are not rungs.
STAGE_OF = {
    "eartharxiv": "A", "publisher-url": "A",
    "open_access": "B", "arxiv": "B", "openalex": "B", "crossref-link": "B", "s2": "B", "datacite": "B",
    "core": "B", "doaj": "B", "openaire": "B", "osf": "B", "europepmc": "B", "venue": "B", "zenodo": "B",
    "hal": "B", "figshare": "B", "opencitations": "B", "ncbi-idconv": "B",
    "landing": "C",
    "wayback": "E", "ia": "E", "commoncrawl": "E",
    "annas": "shadow", "bban": "shadow", "scihub": "shadow",
}

# ── statuses and sub-statuses ───────────────────────────────────────────────────────────────
#: The four attempt words 0033 adds. None is a hunt STATE: the hunt's closed STATES/REASONS
#: (litkb/hunt.py) and the acceptance instrument's CLOSED_STATES pin do not change.
#:   skipped      a rung the ladder did not ask, with the reason (guard 14)
#:   budget-stop  the ladder budget ran out before this point (guard 12); route `ladder`
#:   measured     a rung answered a hit in MEASURE mode and nothing was landed (S4.5 decision D9)
#:   known-bad    a route served bytes whose sha256 matches refused bytes; nothing was written
NEW_STATUSES = ("skipped", "budget-stop", "measured", "known-bad")

#: CONTRACTS "The sub_status vocabulary": what a bad-file / blocked / not-in-archive row may say.
BAD_FILE_SUBS = ("html_response", "too_small", "missing_pdf_header", "corrupt_pdf_header",
                 "early_eof_with_trailing_payload", "stub_not_article", "volume_not_article",
                 "cited_document_not_this_article", "compressed_or_archived_payload")
BLOCKED_SUBS = ("identity_required", "challenge_or_bot_check", "not_found", "html_or_reader")
NOT_IN_ARCHIVE_SUBS = ("not_in_corpus", "no_pdf_link")
#: The skip and budget reasons (C1a's to name, CONTRACTS):
#:   dead_route      a prior attempt on this route ended in a terminal miss (DEAD_STATUSES)
#:   dead_in_run     a prior attempt IN THIS RUN (workstream) ended `blocked` (plan item 2: blocked
#:                   is dead within a run; across runs the back-off governs)
#:   no_identifier   the rung needs an identifier the work does not hold (a DOI-only route, no DOI)
#:   policy_refused  the pre-fetch PolicyDecision refused the request (guard 21)
#:   backoff_window  the route's refusal ladder for this work has not reopened yet (guard 2)
SKIP_REASONS = ("dead_route", "dead_in_run", "no_identifier", "policy_refused", "backoff_window")
BUDGET_SUBS = ("budget_seconds", "budget_attempts")
#: `unverified_keep` (guard 17): a file landed (or, in MEASURE mode, would have) although a check
#: that needs metadata could not run. A third outcome the counters report, never a silent pass.
KEEP_SUBS = ("unverified_keep",)

SUB_STATUSES = {
    "bad-file": BAD_FILE_SUBS,
    "blocked": BLOCKED_SUBS,
    "not-in-archive": NOT_IN_ARCHIVE_SUBS,
    "skipped": SKIP_REASONS,
    "budget-stop": BUDGET_SUBS,
    "ok": KEEP_SUBS,
    "measured": KEEP_SUBS,
}
#: How a sub-status was decided. `live` is every row the ladder writes (0033's function forces it);
#: the other three are the reviewed backfill's, from C1b's item-8 CSV and the blocked typing
#: (CONTRACTS: "basis ∈ bytes|detail|inferred").
SUB_STATUS_BASES = ("live", "bytes", "detail", "inferred")

#: survey §3.4 "the minimum schema change": the kind of content an attempt obtained.
KINDS = ("pdf", "jats", "text", "html-doc", "cached_text", "snippet")

#: A route's article version -> `file_versions.copy_kind` (guard 23; plan item 2: "the version of
#: record carried by EXTENDING copy_kind ... rather than a new column"). The keys are Unpaywall's
#: `version` values (the same three Zotero's OA resolver carries as `articleVersion`); the values are
#: copy_kind's existing words (0001/0020), which already say published / accepted / submitted.
COPY_KIND_OF_VERSION = {"publishedVersion": "publisher", "acceptedVersion": "author manuscript",
                        "submittedVersion": "preprint"}


# ── the pre-fetch policy (guard 21) ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PolicyLine:
    """One auditable line: which rung may ask which host, in which tier, and on whose authority."""
    route: str
    host: str               # a host name, or "*" (any host this rung was handed, e.g. an Unpaywall location)
    tier: str               # "legitimate" | "shadow"
    why: str
    corpus_frozen_at: str = ""   # a shadow front's corpus freeze date (data for its freeze gate)
    #: S4.5 decision D39 (builder-fix6): a line kept IN the table but switched OFF, with its measured reason —
    #: guard 21's "a tier is an auditable switch", for one host. `decide` refuses the line with this reason, so every
    #: row the ladder records for it is a `skipped/policy_refused` carrying it: never silence, never a deleted line.
    off_why: str = ""


#: `litkb-shadow-hosts` (decided 2026-09-22): "Every host is one auditable line in the pre-fetch
#: policy object; the tier runs only after every legitimate rung has missed; the corpus froze in
#: early 2022". The freeze DATE is the LINKAGE survey's §1.8 (Anna's in-code provenance
#: `dois-2022-02-12.7z`); it is DATA on the line, for the freeze gate builder C2b writes (plan 5b i).
SHADOW_CORPUS_FROZEN_AT = "2022-02-12"
#: The ONE switch for the shadow tier (guard 21: "shadow tier authorised" as a one-line auditable
#: switch rather than a code path). True under `litkb-shadow-hosts` (a)-(d), all granted.
SHADOW_TIER_ENABLED = True

#: S4.5 decision D39 (builder-fix6): Stage E5's two hosts were switched OFF with this reason, the orchestrator's
#: measurement during the live run hardening-1; every skip the ladder recorded for them from the switch on carries it.
#: HISTORY since S4.5 decision D53 (2026-09-24 ~14:40, integrator-w4): no line of the table carries it any more — the
#: orchestrator measured the index serving again (`collinfo.json` 200 in 0.40 s; one index query of CC-MAIN-2025-33 200
#: in 0.72 s with real records) and Kam's goal ("maximum coverage of literature ... testing all our established
#: sources") puts E5 back ON so hardening-2 MEASURES its yield. It stays the hardening-1 measurement the D39 mechanism
#: switched on (`PolicyLine.off_why`), which is how the orchestrator switches E5 off again if the index fails again.
COMMONCRAWL_OFF_WHY = ("switched off 2026-09-24 (S4.5 decision D39): in the live run hardening-1 every Common "
                       "Crawl attempt that was not an ordinary 404 ended on the index answering 502/504 (13 of "
                       "14 attempts; one transport failure), attempts took up to ~300 s, and a direct probe at "
                       "02:03 PDT had its connection closed in 0.3 s, so the index was not serving")

POLICY = (
    PolicyLine("open_access", "api.unpaywall.org", "legitimate",
               "Unpaywall's record for the DOI (decisions.yaml litkb-p0-foundation §15.5: the email is Kam's)"),
    PolicyLine("open_access", "arxiv.org", "legitimate", "the arXiv copy of a work with an arXiv id"),
    PolicyLine("open_access", "*", "legitimate", "any OA location Unpaywall itself lists for the DOI"),
    # S4.5 builder-C2c (Stage E, plan item 6; survey §1 E1/E3/E5): the archives a dead URL is recovered from
    PolicyLine("wayback", "archive.org", "legitimate", "Stage E1: the Wayback availability API (plan item 6)"),
    PolicyLine("wayback", "web.archive.org", "legitimate",
               "Stage E1: the CDX index and a capture's raw bytes (the id_/if_ modifiers)"),
    PolicyLine("ia", "archive.org", "legitimate",
               "Stage E3: Internet Archive item search, item metadata and an item's file (plan item 6)"),
    # S4.5 decision D53: E5's two lines are ON again (D39's `off_why=COMMONCRAWL_OFF_WHY` removed from both)
    PolicyLine("commoncrawl", "index.commoncrawl.org", "legitimate",
               "Stage E5: the Common Crawl crawl list and index (plan item 6)"),
    PolicyLine("commoncrawl", "data.commoncrawl.org", "legitimate",
               "Stage E5: one WARC record by byte range (survey §1 E5-RG)"),
    PolicyLine("annas", "annas-archive.gl", "shadow", "litkb-shadow-hosts (a)", SHADOW_CORPUS_FROZEN_AT),
    PolicyLine("scihub", "sci-hub.ru", "shadow", "litkb-shadow-hosts (a)", SHADOW_CORPUS_FROZEN_AT),
    PolicyLine("scihub", "sci-hub.ren", "shadow", "litkb-shadow-hosts (a)", SHADOW_CORPUS_FROZEN_AT),
    PolicyLine("scihub", "sci-hub.box", "shadow", "litkb-shadow-hosts (a)", SHADOW_CORPUS_FROZEN_AT),
    PolicyLine("scihub", "sci-hub.wf", "shadow", "litkb-shadow-hosts (a)", SHADOW_CORPUS_FROZEN_AT),
    PolicyLine("bban", "sci.bban.top", "shadow", "litkb-shadow-hosts (b); plan item 5b (ii)", SHADOW_CORPUS_FROZEN_AT),
    # S4.5 builder-C2b (Stage C): the publisher landing page a DOI resolves to, and the PDF URL that page, a lead page
    # or a per-publisher rule names (litkb.acquire.landing refuses a candidate on a host any SHADOW line names)
    PolicyLine("landing", "*", "legitimate",
               "Stage C: the DOI's landing page and the PDF it points to (plan item 5; survey §2)"),
)
LEGITIMATE, SHADOW = "legitimate", "shadow"

# S4.5 builder-C2a: the Stage A and Stage B rungs (plan items 3 and 4; brief-CONTRACTS.md route names), one line per
# host a rung asks — appended as a statement, not inside the tuple above, so parallel builders' hunks never meet
# (S4.5 decision D5). A `*` line is a rung that follows the URLs an index itself lists (never a SHADOW host: the
# rungs refuse one, litkb.acquire.stage_b.fetch_candidates).
POLICY = POLICY + (
    PolicyLine("eartharxiv", "eartharxiv.org", "legitimate",
               "Stage A7: the preprint PDF the offline-harvested EarthArXiv OAI map names (survey A7, MEASURED)"),
    PolicyLine("publisher-url", "*", "legitimate",
               "Stage A4: the publisher's own PDF URL built from the DOI (survey A4; stage_a.PUBLISHER_TEMPLATES)"),
    PolicyLine("opencitations", "api.opencitations.net", "legitimate", "Stage B Wave 1: OpenCitations META"),
    PolicyLine("crossref-link", "api.crossref.org", "legitimate",
               "Stage B4: Crossref's record, then the link[] PDF URLs it lists"),
    PolicyLine("openalex", "api.openalex.org", "legitimate",
               "Stage B3: OpenAlex's record, then the pdf_url of each location it lists"),
    PolicyLine("doaj", "doaj.org", "legitimate", "Stage B8: DOAJ's article API, then its fulltext links"),
    PolicyLine("openaire", "api.openaire.eu", "legitimate", "Stage B9: OpenAIRE, then the PDF URLs it lists"),
    PolicyLine("hal", "api.archives-ouvertes.fr", "legitimate", "Stage B14: HAL, then its deposited file"),
    PolicyLine("osf", "api.osf.io", "legitimate", "Stage B11: OSF APIv2, then the preprint's primary file"),
    PolicyLine("datacite", "api.datacite.org", "legitimate", "Stage B6: DataCite, then its contentUrl"),
    PolicyLine("zenodo", "zenodo.org", "legitimate", "Stage B14: Zenodo's record API and its files"),
    PolicyLine("figshare", "api.figshare.com", "legitimate", "Stage B14: figshare's article API and its files"),
    PolicyLine("ncbi-idconv", "pmc.ncbi.nlm.nih.gov", "legitimate", "Stage B Wave 2: the NCBI ID Converter"),
    PolicyLine("s2", "api.semanticscholar.org", "legitimate",
               "Stage B5/B1: Semantic Scholar's record, then its openAccessPdf"),
    PolicyLine("europepmc", "www.ebi.ac.uk", "legitimate",
               "Stage B12/B21: Europe PMC's core record, then its OA PDF and ?pdf=render"),
    PolicyLine("arxiv", "arxiv.org", "legitimate", "Stage B1: an arXiv id's PDF (the open-access route's host)"),
    PolicyLine("venue", "*", "legitimate",
               "Stage B13: ACL Anthology by id, OpenReview by title (title, first author and year agreeing)"),
)


def add_lines(lines, *, route=None):
    """Append a rung module's OWN lines to POLICY (called by `run.register` with the rung's
    `policy_lines`), so POLICY stays the one auditable object every decision reads while each rung's lines
    are written beside the rung. Every line is checked before any is added: a `PolicyLine`; its route a
    staged route (`STAGE_OF`) and, when `route` is given, that route; its tier the tier of its route's STAGE
    (a shadow-stage route is `shadow`, every other stage `legitimate` — so a shadow front can never be
    declared legitimate and escape the tier's switch and its after-every-legitimate-miss rule); and no
    (route, host) lined twice. -> the lines added."""
    global POLICY
    lines = tuple(lines or ())
    seen = {(p.route, p.host) for p in POLICY}
    for line in lines:
        if not isinstance(line, PolicyLine):
            raise TypeError(f"a policy line is a PolicyLine, not {type(line).__name__}")
        if line.route not in STAGE_OF or (route is not None and line.route != route):
            raise ValueError(f"policy line for {line.route!r}: a rung registers lines for its own staged route "
                             f"only ({route!r})")
        if line.tier not in (LEGITIMATE, SHADOW):
            raise ValueError(f"policy line {line.route}/{line.host}: tier {line.tier!r} is not "
                             f"{LEGITIMATE!r} or {SHADOW!r}")
        # BEGIN guard: a policy line's tier is its route's stage
        if (line.tier == SHADOW) != (STAGE_OF[line.route] == "shadow"):
            raise ValueError(f"policy line {line.route}/{line.host}: tier {line.tier!r} is not the tier of stage "
                             f"{STAGE_OF[line.route]!r} (litkb-shadow-hosts: the shadow tier is one switch)")
        # END guard: a policy line's tier is its route's stage
        if (line.route, line.host) in seen:
            raise ValueError(f"policy line {line.route}/{line.host} is already in POLICY (one line per rung/host)")
        seen.add((line.route, line.host))
    POLICY = POLICY + lines
    return lines


@dataclass(frozen=True)
class PolicyDecision:
    """What the policy answered for one (route, host) BEFORE any request. `line` is the index into
    POLICY of the line that decided (None when no line exists — itself a refusal)."""
    route: str
    host: str
    tier: str
    allowed: bool
    reason: str
    line: int = None

    def as_detail(self):
        return asdict(self)


def line_for(route, host="*", policy=None):
    """-> (index, PolicyLine) for (route, host): an exact host line first, else the route's "*" line,
    else the route's first line when no host is named. (None, None) when the route has none."""
    policy = POLICY if policy is None else policy
    exact = [(i, p) for i, p in enumerate(policy) if p.route == route and p.host == host]
    if exact:
        return exact[0]
    star = [(i, p) for i, p in enumerate(policy) if p.route == route and p.host == "*"]
    if star:
        return star[0]
    if host in ("*", "", None):
        first = [(i, p) for i, p in enumerate(policy) if p.route == route]
        if first:
            return first[0]
    return None, None


def decide(route, host="*", *, legit_hit=False, shadow_enabled=None, policy=None):
    """-> PolicyDecision for asking `host` on `route` now.

    Refused when: no policy line names the route/host; the line is switched off (`off_why`, S4.5
    decision D39: refused with that reason, whatever its tier); the line is shadow and the shadow switch is
    off; the line is shadow and a legitimate rung has already HIT in this ladder run (in MEASURE mode
    a hit does not stop the ladder, so this is what keeps the shadow tier after every legitimate rung
    has MISSED, as `litkb-shadow-hosts` rules)."""
    shadow_enabled = SHADOW_TIER_ENABLED if shadow_enabled is None else shadow_enabled
    i, line = line_for(route, host or "*", policy)
    if line is None:
        return PolicyDecision(route, host or "*", "", False, "no policy line names this route/host")
    # BEGIN guard: a line switched off is refused with its measured reason
    if line.off_why:
        return PolicyDecision(route, host or "*", line.tier, False, line.off_why, i)
    # END guard: a line switched off is refused with its measured reason
    # BEGIN guard: the shadow tier is one switch and runs only after every legitimate rung missed
    if line.tier == SHADOW and not shadow_enabled:
        return PolicyDecision(route, host or "*", line.tier, False, "the shadow tier is switched off", i)
    if line.tier == SHADOW and legit_hit:
        return PolicyDecision(route, host or "*", line.tier, False,
                              "a legitimate rung already hit in this ladder run", i)
    # END guard: the shadow tier is one switch and runs only after every legitimate rung missed
    return PolicyDecision(route, host or "*", line.tier, True, line.why, i)


#: S4.5 decision D18 (the orchestrator's ruling on integrator-w1 Q4), word for word in its reason.
MEASURE_REFUSAL = ("MEASURE mode asks the legitimate tiers only (Stages A, B, C, E): it never spends an archive "
                   "download and never asks the shadow stage for a work that already holds a file (S4.5 decision D18)")


def measure_decision(decision):
    """-> the decision MEASURE mode acts on (`run._skip_reason`, seam integrator-w2): `decision` itself when it
    refused or its line is `legitimate`; otherwise a refusal naming D18, on the same line. MEASURE mode runs on a
    work that already holds a file (S4.5 decision D9), and what it measures is the LEGITIMATE tiers' yield — so an
    archive download (`annas`) or a shadow front asked there would spend a quota or a shadow request for bytes the
    corpus already holds. A refused rung is a `skipped/policy_refused` row, recorded, never silence."""
    # BEGIN guard: MEASURE mode asks the legitimate tiers only
    if decision.allowed and decision.tier != LEGITIMATE:
        return PolicyDecision(decision.route, decision.host, decision.tier, False, MEASURE_REFUSAL, decision.line)
    # END guard: MEASURE mode asks the legitimate tiers only
    return decision


# ── the ladder budget (guard 12) ────────────────────────────────────────────────────────────
#: One scheduled in-run transient retry per rung (litkb's own one-retry convention:
#: admit/resolver.py::registry_get, acquire/annas.py::resolve and ::get_json_backoff each retry once).
#: The attempts default below is DERIVED from it.
IN_RUN_RETRIES = 1

#: Set to the OBSERVED MAXIMUM on litkb's own hunt ledgers — ONE OUTLIER, not a fitted value (builder-C1a
#: report, scratch calib.py): the longest hunt that spent all three of today's routes and landed nothing,
#: over the 17 such rows of Reports/LITKB_RULED_HUNTS_2026-09-21.csv, LITKB_EDGE_RUN_2026-09-21.csv and
#: LITKB_TITLE_HUNTS_2026-09-21.csv, was 504.76 s — E13 (10.1145/3534678.3539043), the very row whose
#: second hunt the back-off exists to stop; the median was 52.77 s and the next largest 62.09 s. Rounded
#: UP to the next whole second, so no historical hunt would have hit it. It bounds TODAY's three-rung
#: ladder only; the S4.5 ladder adds rungs (Stage B runs concurrently, so its cost is its slowest rung,
#: not their sum), and the run's manifest (`ladder_budget`) is where a re-measured value belongs.
LADDER_SECONDS_DEFAULT = 505


@dataclass
class LadderBudget:
    """The whole ladder's budget for ONE work (guard 12: "total timeout / attempts / concurrency,
    checked between every tier and every source"). `attempts` counts SPENT attempts (a row that made
    a request); skip and budget rows spend nothing. None for `attempts` / `concurrency` means DERIVED
    from the rung registry when the ladder starts (`resolved`)."""
    seconds: float = LADDER_SECONDS_DEFAULT
    attempts: int = None
    concurrency: int = None
    clock: object = field(default=time.monotonic, repr=False, compare=False)

    def resolved(self, rungs):
        """-> a copy with `attempts` and `concurrency` filled from the registry: every rung asked once
        plus IN_RUN_RETRIES scheduled retries each (DERIVED, not chosen), and the widest concurrent
        stage all at once (plan item 4: Stage B's rungs all concurrent, wall-clock the slowest)."""
        widths = {}
        for r in rungs:
            widths[r.stage] = widths.get(r.stage, 0) + (1 if r.concurrent else 0)
        return LadderBudget(seconds=self.seconds,
                            attempts=self.attempts if self.attempts is not None else len(rungs) * (1 + IN_RUN_RETRIES),
                            concurrency=self.concurrency if self.concurrency is not None else max(
                                [1, *widths.values()]),
                            clock=self.clock)

    def spec(self):
        return {"seconds": self.seconds, "attempts": self.attempts, "concurrency": self.concurrency}

    def exhausted(self, started, spent):
        """-> the budget sub-status that stops the ladder now, or None. Checked BETWEEN stages and
        rungs, never mid-request (plan S5 'A per-hunt time budget': checked between stages and
        between routes, never mid-request)."""
        # BEGIN guard: the ladder budget is checked between every stage and rung
        if self.attempts is not None and spent >= self.attempts:
            return "budget_attempts"
        if self.seconds is not None and self.clock() - started >= self.seconds:
            return "budget_seconds"
        return None
        # END guard: the ladder budget is checked between every stage and rung
