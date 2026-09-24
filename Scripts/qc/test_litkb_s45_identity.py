"""litkb S4.5 item 1 — THE IDENTIFIER MODEL (builder B1, migration 0032).

The scheme registry and its Python twin, the per-scheme normalisers (SQL and Python driven over one table), the
validators ported in the linkage survey's order and the one it says not to port, the Wave-0 derivations, the
harvest parsers, the conflict rule (fatcat's, COUNTED), the third state of a relation edge, identifier-first
check 2 with type-scoped ISBN, the key-length rule — and every fire of qc/instruments/litkb_hardening_b1.py as a
test (the harness is the cold re-fire path; these are the gate in `pytest qc`).

No test touches the network: registry answers are CONSTRUCTED (qc/fixtures/litkb_b1_constructed_registry.json)
or read from the tracked crosswalk probe CSV. Every mechanism tested here is a RELAYED design, UNVALIDATED in the
CLAUDE.md §3.4c sense until an independent referee scores it on litkb's real rows.
"""
import csv
import hashlib
import importlib.util
import json
import random
import re
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
pg_only = pytest.mark.requires_litkb_pg


def _hb1():
    spec = importlib.util.spec_from_file_location("litkb_hardening_b1",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_hardening_b1.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _probe_module():
    spec = importlib.util.spec_from_file_location("litkb_acq_probe_relation",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_acq_probe_relation.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── pure: validators, normalisers, derivations, parsers ─────────────────────────────────────────────

def test_isbn_check_digits_are_rederived_and_a_wrong_one_is_rejected_not_coerced():
    from litkb import identifiers as I

    assert I.to_isbn13("0-306-40615-2") == "9780306406157"          # the ISBN standard's own worked example
    assert I.to_isbn13("ISBN-13: 978-0-306-40615-7") == "9780306406157"
    assert I.to_isbn13("0-306-40615-3") is None                     # wrong ISBN-10 check digit: rejected
    assert I.to_isbn13("9780306406158") is None                     # wrong ISBN-13 check digit: rejected
    assert I.to_isbn13("0000000000") is None and I.to_isbn13("000000000X") is None   # isbnlib's sentinels
    assert I.to_isbn10("9780306406157") == "0306406152"
    assert I.to_isbn10("9791034304423") is None                     # a 979 ISBN has no ISBN-10
    assert I.norm("isbn", "0306406152") == "9780306406157"          # the two spellings are ONE row
    assert I.norm("isbn", "0306406153") == "0306406153"             # an invalid one is kept visibly invalid
    assert not I.valid("isbn", "0306406153")


def test_the_isbn13_routine_the_survey_says_not_to_port_is_not_what_isbn13_valid_does():
    """LINKAGE §3.5: oc_idmanager's ISBN-13 check assigns a boolean, so its weights degenerate to 1,3,0,0,...
    and the test becomes (d0 + 3*d1) % 10 == 0 — which EVERY 978-prefixed string satisfies (9 + 21 = 30).
    The oracle below is that routine's arithmetic, CONSTRUCTED here only to show isbn13_valid is not it."""
    from litkb import identifiers as I

    def buggy(s):
        return (int(s[0]) * 1 + int(s[1]) * 3) % 10 == 0
    rng = random.Random(20260923)
    strings = ["978" + "".join(rng.choice("0123456789") for _ in range(10)) for _ in range(2000)]
    assert all(buggy(s) for s in strings)                            # the bug: every one "passes"
    passed = sum(I.isbn13_valid(s) for s in strings)
    assert 150 <= passed <= 250, passed                              # the real rule: one check digit in ten


@pytest.mark.parametrize("text, doi", [
    ("(doi:10.1234/abc)", "10.1234/abc"),                            # the reference list's own bracket
    ("see [10.1000/xyz].", "10.1000/xyz"),
    ("10.1061/40794(179)45", "10.1061/40794(179)45"),                # a pair the DOI was minted with, kept
    ("https://doi.org/10.1002/(SICI)1097-0258(19980430)17:8<857::AID-SIM777>3.0.CO;2-E)",
     "10.1002/(sici)1097-0258(19980430)17:8<857::aid-sim777>3.0.co;2-e"),
    ("no doi here", ""),
])
def test_clean_doi_balances_brackets(text, doi):
    from litkb import identifiers as I

    assert I.clean_doi(text) == doi


def test_find_doi_falls_back_to_the_slice():
    from litkb import identifiers as I

    assert I.find_doi("doi:10.1/x") == "10.1/x"                      # no 4-digit registrant: the slice finds it


def test_detection_returns_every_match_with_pmid_last():
    from litkb import identifiers as I

    got = I.detect_schemes("12345678")
    assert {"oclc", "mag", "core", "pmid"} <= set(got) and got[-1] == "pmid"
    assert "pmid" not in I.detect_schemes("12345678901")             # longer than PubMed's ids
    assert I.detect_schemes("PMC7391") == ("pmcid",)
    assert "doi" in I.detect_schemes("https://doi.org/10.1016/j.rse.2020.111723")
    assert "isbn" in I.detect_schemes("0-306-40615-2")


def test_the_three_normalisation_traps():
    from litkb import identifiers as I

    assert I.doi_for_provider("10.1016/J.RSE.2020.111723", "crossref") == "10.1016/j.rse.2020.111723"
    assert I.doi_for_provider("10.1016/j.rse.2020.111723", "wikidata") == "10.1016/J.RSE.2020.111723"
    assert I.norm("doi", "10.48550/arXiv.2206.01062") == "10.48550/arxiv.2206.01062"   # DataCite lower-cases
    assert I.pmcid_forms("7391") == ("PMC7391", "7391")
    assert I.pmcid_for_provider("PMC7391", "wikidata") == "7391"


def test_wave0_derivations_carry_deterministic_provenance():
    from litkb import identifiers as I

    r = I.arxiv_to_doi("arXiv:2206.01062v2")
    assert r["value"] == "10.48550/arxiv.2206.01062" and r["asserted_by"] == "deterministic"
    assert r["verified_by"] is None and r["evidence"]["candidate"] is True      # a CANDIDATE until DataCite
    assert r["derived_from"] == {"scheme": "arxiv", "value": "2206.01062"}
    assert I.doi_to_arxiv("10.48550/arXiv.2206.01062")["value"] == "2206.01062"
    assert I.doi_to_arxiv("10.1145/3534678.3539043") is None
    assert I.isbn10_to_13("0-306-40615-2")["value"] == "9780306406157"
    assert I.isbn10_to_13("0-306-40615-3") is None
    assert I.isbn_a_doi("978-0-306-40615-7")["value"] == "10.978.0306/406157"
    assert I.isbn_a_doi("9780306406157") is None                      # no hyphenation, no guessed split
    assert I.is_shortdoi("10/abcde") and not I.is_shortdoi("10.1/abcde")
    assert I.shortdoi_alias_url("10/abcde").endswith("/api/handles/10/abcde?type=HS_ALIAS")
    got = I.parse_hs_alias("10/abcde", {"responseCode": 1, "values": [
        {"type": "HS_ALIAS", "data": {"value": "10.1016/J.RSE.2020.111723"}}]})
    assert got["value"] == "10.1016/j.rse.2020.111723" and got["derived_from"]["value"] == "10/abcde"
    assert I.parse_hs_alias("10/abcde", {"responseCode": 100}) is None


def test_crossref_harvest_reads_the_fields_it_used_to_discard():
    from litkb.admit import harvest as H

    msg = {"member": "78", "alternative-id": ["S0034-4257(20)30123-4"], "ISBN": ["0-306-40615-2"],
           "issn-type": [{"value": "00344257", "type": "print"}], "ISSN": ["0034-4257"],
           "relation": {"has-preprint": [{"id-type": "doi", "id": "10.1101/357798", "asserted-by": "object"}],
                        "is-referenced-by": [{"id-type": "doi", "id": "10.1/x"}]}}
    rows, rels, rejected = H.from_crossref(msg, "10.1016/j.rse.2020.111723")      # CONSTRUCTED message
    got = {(r["scheme"], r["value"]) for r in rows}
    assert got == {("pii", "S0034425720301234"), ("isbn", "9780306406157"), ("issn", "0034-4257")}
    assert all(r["asserted_by"] == "crossref" and r["derived_from"] == {"scheme": "doi",
               "value": "10.1016/j.rse.2020.111723"} and r["verified_by"] is None for r in rows)
    assert [(e["relation"], e["target_value"]) for e in rels] == [("has_preprint", "10.1101/357798")]
    assert rejected == []
    # a non-Elsevier alternative-id is not a PII; an empty relation field is the THIRD state
    rows, rels, _ = H.from_crossref({"alternative-id": ["S0034425720301234"], "relation": {}}, "10.3390/rs1")
    assert rows == [] and [e["state"] for e in rels] == ["none_returned"]
    assert H.from_crossref({}, "10.3390/rs1")[1][0]["state"] == "none_returned"


def test_datacite_annas_openalex_s2_parsers():
    from litkb.admit import harvest as H

    rows, rels, _ = H.from_datacite({"identifiers": [{"identifier": "2206.01062", "identifierType": "arXiv"}],
                                     "relatedIdentifiers": [
                                         {"relatedIdentifier": "10.1145/3534678.3539043",
                                          "relatedIdentifierType": "DOI", "relationType": "IsPreprintOf"},
                                         {"relatedIdentifier": "10.1/cited", "relatedIdentifierType": "DOI",
                                          "relationType": "Cites"}]}, "10.48550/arXiv.2206.01062")
    assert [(r["scheme"], r["value"]) for r in rows] == [("arxiv", "2206.01062")]
    assert [(e["relation"], e["target_value"]) for e in rels] == [("is_preprint_of", "10.1145/3534678.3539043")]
    rows, skipped = H.from_annas({"md5": ["AABBCCDDEEFF00112233445566778899"], "isbn13": ["9780306406157"],
                                  "isbn10": ["0306406152"], "zlib": ["123"], "asin": ["B0"], "doi": ["10.1/x"],
                                  "ipfs_cid": ["bafy"]}, "10.1/x", "aabbccddeeff00112233445566778899")
    assert {(r["scheme"], r["value"]) for r in rows} == {("md5", "aabbccddeeff00112233445566778899"),
                                                        ("isbn", "9780306406157"), ("zlib", "123")}
    assert {s["key"] for s in skipped} == {"asin", "doi", "ipfs_cid"}
    assert all(r["asserted_by"] == "annas" for r in rows)
    oa = H.from_openalex({"ids": {"openalex": "https://openalex.org/W2244457783", "mag": "2244457783",
                                  "pmid": "https://pubmed.ncbi.nlm.nih.gov/123"},
                          "locations": [{"pmh_id": "oai:repo.example:1721.1/5"}]}, "10.1109/tgrs.2015.2463689")
    assert {(r["scheme"], r["value"]) for r in oa} == {("openalex", "W2244457783"), ("mag", "2244457783"),
                                                      ("pmid", "123"), ("oai", "oai:repo.example:1721.1/5")}
    rows, rels = H.from_s2({"externalIds": {"ArXiv": "2206.01062", "CorpusId": 250089265}}, "10.1145/3534678.3539043")
    assert [(r["scheme"], r["value"]) for r in rows] == [("s2", "250089265")]
    assert [(e["relation"], e["target_scheme"], e["target_value"]) for e in rels] == [("has_version", "arxiv",
                                                                                          "2206.01062")]
    rows, rels = H.from_s2({"externalIds": {"ArXiv": "2206.01062"}}, "10.48550/arXiv.2206.01062")
    assert [(r["scheme"], r["value"]) for r in rows] == [("arxiv", "2206.01062")] and rels == []


def test_fetch_for_litkb_returns_the_record_s_identifiers_unified():
    """S4.5 item 1 (decision D2): gate 2's record was fetched whole and all but its `doi` key dropped."""
    from litkb.acquire import annas
    from litkb.netutil import Pacer

    pdf = b"%PDF-1.4 known"
    md5 = hashlib.md5(pdf).hexdigest()
    iu = {"doi": ["10.1/known"], "md5": [md5], "isbn13": ["9780306406157"]}

    class Stub:
        base = "https://annas-archive.gl"

        def get(self, url, accept="", timeout=0, follow=True, data=None, headers=None):
            if "/scidb/" in url:
                return 200, {}, f'<a href="/md5/{md5}">record</a>'.encode()
            if "/db/aarecord_elasticsearch/" in url:
                return 200, {}, json.dumps({"file_unified_data": {"identifiers_unified": iu, "extension_best": "pdf",
                                                                  "filesize_best": len(pdf)}}).encode()
            raise AssertionError(url)
    r = annas.fetch_for_litkb(Stub(), "SEKRIT", "10.1/known", Pacer(interval=0, sleep=lambda s: None),
                              known_md5={md5})
    assert r["status"] == "duplicate-held" and r["identifiers_unified"] == iu


def test_make_key_builds_a_valid_key_for_row_187_and_for_every_long_creator():
    from litkb.admit import front

    creator = "Land Product Validation Subgroup (Working Group on Calibration and Validation"
    title = "Land Cover and Change Map Accuracy Assessment and Area Estimation Good Practices Protocol"
    assert front.make_key(creator, 2025, title) == "LPVSWGCV_2025_land-cover-change-map"
    legacy = _hb1().legacy_make_key(creator, 2025, title)             # the pre-S4.5 rule: key[:59]
    assert not front.KEY_RE.fullmatch(legacy)                         # ... cut inside the surname
    rng = random.Random(187)
    words = ["Committee", "on", "Earth", "Observation", "Satellites", "Working", "Group", "of", "the",
             "Supercalifragilisticexpialidociousnessesque", "Pneumonoultramicroscopicsilicovolcanoconiosis"]
    for n in range(400):                                             # CONSTRUCTED creators and titles
        who = " ".join(rng.choice(words) for _ in range(rng.randint(1, 14)))
        what = " ".join(rng.choice(words + ["map", "x", "a"]) for _ in range(rng.randint(0, 9)))
        key = front.make_key(who, rng.randint(1000, 2999), what)
        assert front.KEY_RE.fullmatch(key) and len(key) <= front.KEY_MAX, (who, what, key)
        # the a/b collision suffix still fits works_key_check
        assert len(re.sub(r"^([A-Za-z]+_[0-9]{4})_", r"\1a_", key)) < 60


def test_the_relation_probe_writes_one_row_per_edge_or_its_third_state(tmp_path):
    P = _probe_module()
    reg = json.loads((SCRIPTS / "qc" / "fixtures" / "litkb_b1_constructed_registry.json").read_text(encoding="utf-8"))
    for doi, msg in reg["crossref"].items():
        P.response_file(tmp_path, doi).write_text(json.dumps({"message": msg}), encoding="utf-8")
    P.response_file(tmp_path, "10.3390/empty").write_text(json.dumps({"message": {"relation": {}}}),
                                                           encoding="utf-8")
    out = tmp_path / "litkb_acq_probe_relation.csv"
    assert P.main(["--responses", str(tmp_path), "--dois",
                   "10.1111/2041-210x.13107,10.1101/357798,10.3390/empty,10.9999/absent", "--out", str(out)]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [(r["doi"], r["state"], r["relation"]) for r in rows] == [
        ("10.1111/2041-210x.13107", "asserted", "has_preprint"), ("10.1101/357798", "asserted", "is_preprint_of"),
        ("10.3390/empty", "none_returned", ""), ("10.9999/absent", "unanswered", "")]


def test_file_counters_read_zero_or_unread_when_their_file_is_absent(tmp_path):
    M = _hb1()
    assert M.relation_probe_rows(None, {"probe_csvs": {}}) == 0
    with pytest.raises(M.Unread):
        M.key_derivation_crashes(None, {"run_csv": str(tmp_path / "nope.csv")})


def test_relation_probe_rows_counts_only_answered_rows(tmp_path):
    """Auditor-B1 F1: a probe whose every request failed still writes one `unanswered` row per DOI — and has
    measured nothing. Those rows are reported in the counter's detail, never counted (CONSTRUCTED DOIs)."""
    M, P = _hb1(), _probe_module()
    out = tmp_path / "litkb_acq_probe_relation.csv"
    P.write_csv(P.probe_rows([("a", "10.5555/b1-dead-a"), ("b", "10.5555/b1-dead-b")], lambda doi: (0, None)), out)
    m = {"probe_csvs": {M.RELATION_PROBE: str(out)}}
    assert M.relation_probe_rows(None, m) == 0 and M.relation_probe_unanswered(None, m) == 2
    assert M.DETAILS["relation_probe_rows"](None, m) == ["unanswered probe rows (not counted): 2"]


def test_fire_relation_probe_unanswered(tmp_path):
    M = _hb1()
    assert M.fire_relation_probe_unanswered(None, "control", tmp_path / "c") == 2
    assert M.fire_relation_probe_unanswered(None, "known_bad", tmp_path / "k") == 0


def test_key_derivation_crashes_counts_both_shapes_a_key_fails_in(tmp_path):
    """Auditor-B1 F3: the pre-S4.5 key failure (`admit:CheckViolation`) and the S4.5 one (`make_key` refusing by
    name, `admit:KeyUnderivable`) both count; another crash at the admit stage does not (CONSTRUCTED rows)."""
    M = _hb1()
    p = tmp_path / "run.csv"
    p.write_text("row_id,ref,state,reason\nr1,a,crashed,admit:CheckViolation\nr2,b,crashed,admit:KeyUnderivable\n"
                 "r3,c,crashed,admit:ValueError\nr4,d,held,no-file\n", encoding="utf-8")
    assert M.key_derivation_crashes(None, {"run_csv": str(p)}) == 2


def test_make_key_without_its_surname_guard_refuses_row_187_by_name():
    """The in-process mutation the `key_guard_deleted` fire applies: the guard's lines removed from the LIVE
    make_key source. Row 187's 68-character surname then leaves no room, and the key rule refuses by NAME
    (KeyUnderivable, an AdmissionError) — never a cut key."""
    from litkb.admit import front

    creator = "Land Product Validation Subgroup (Working Group on Calibration and Validation"
    title = "Land Cover and Change Map Accuracy Assessment and Area Estimation Good Practices Protocol"
    unguarded = _hb1().make_key_without_surname_guard()
    with pytest.raises(front.KeyUnderivable, match="key-underivable"):
        unguarded(creator, 2025, title)
    assert issubclass(front.KeyUnderivable, front.AdmissionError)
    assert unguarded("Page", 2020, "A short title of a paper") == front.make_key("Page", 2020, "A short title of a paper")


# ── the database ─────────────────────────────────────────────────────────────────────────────────────

class PG:
    def __init__(self, conn):
        self.conn = conn

    def one(self, q, params=()):
        return self.conn.execute(q, params).fetchone()

    def writer(self):
        from litkb.db import connect as c

        k = c.connect(c.DB_TEST, "litkb_test", autocommit=True)
        k.execute("SET ROLE litkb_writer")
        return k


def _reset_and_migrate(conn):
    from litkb.db import migrate

    migrate.reset(conn)
    migrate.apply(conn)


@pytest.fixture(scope="module")
def pg(litkb_pg_base):
    """The shared worker database, RESET AND MIGRATED before this module's first database test and again after
    its last (brief-COMMON rule 5; auditor-B1 F7). This module admits REAL titles and DOIs — E21's pair, row
    187's record, E06's carrier title, real crosswalk keys — and `_title_duplicates` is global: left behind they
    refused the hunt suite's page tests and the edges replay when the three files ran in that order. The reset
    BEFORE makes this module independent of what earlier modules left (the same real rows admitted elsewhere);
    the reset AFTER leaves the next module the database a fresh session starts with (qc/test_litkb_edges.py's
    pattern, run under the suite's advisory lock that `litkb_pg_base` holds)."""
    _psycopg, conn, _ran = litkb_pg_base
    _reset_and_migrate(conn)
    yield PG(conn)
    _reset_and_migrate(conn)


#: (scheme, value) forms the Python twin and the SQL normaliser are driven over together (CONSTRUCTED).
NORM_FORMS = [
    ("doi", " https://doi.org/10.1016/J.RSE.2020.111723. "), ("doi", "doi:10.1101/357798"),
    ("arxiv", "arXiv:2206.01062v3"), ("arxiv", "hep-th/9901001v1"),
    ("isbn", "ISBN 0-306-40615-2"), ("isbn", "ISBN-13: 978-0-306-40615-7"), ("isbn", "0-306-40615-3"),
    ("isbn", "0000000000"), ("isbn", "080442957x"),
    ("pmcid", "7391"), ("pmcid", "pmc7391"), ("pmcid", " PMC 7391"), ("pmid", "PMID: 12345"),
    ("issn", "00344257"), ("issn", "1558-064x"), ("pii", "S0034-4257(20)30123-4"),
    ("handle", "hdl:1721.1/5"), ("handle", "https://hdl.handle.net/1721.1/5"), ("oclc", "(OCoLC)12345"),
    ("oclc", "ocm0012"), ("lccn", "N 78-89035"), ("hal", "HAL-01234567v2"), ("md5", " AABBccdd "),
    ("sha256", "ABCDEF"), ("s2", "ABCdef"), ("olid", "ol123m"), ("openalex", "https://openalex.org/w123/"),
    ("wikidata", "q42"), ("url", " https://example.org/x "), ("tracker", " 187 "), ("legacy_stem", "Stem_x"),
    ("core", " 42 "), ("mag", "2244457783"), ("dblp", "conf/kdd/X22"), ("bibcode", "2020ApJ...900...1A"),
]


@pg_only
def test_the_python_normaliser_is_litkb_norm_identifier(pg):
    from litkb import identifiers as I

    for scheme, value in NORM_FORMS:
        sql = pg.one("SELECT litkb.norm_identifier(%s, %s)", (scheme, value))[0]
        assert sql == I.norm(scheme, value), (scheme, value, sql, I.norm(scheme, value))


@pg_only
def test_the_scheme_registry_is_its_python_seed(pg):
    from litkb import identifiers as I

    rows = {r[0]: r[1:] for r in pg.conn.execute(
        "SELECT scheme, label, url_template, regex, normaliser, distinct_values, identity_strong, "
        "registry_confirmed, identity_types, tier, why FROM litkb.scheme_registry").fetchall()}
    assert set(rows) == set(I.SCHEMES)
    for s, d in I.SCHEMES.items():
        assert rows[s] == (d["label"], d.get("url"), d.get("regex"), d["normaliser"], d["distinct"],
                           bool(d.get("strong")), bool(d.get("registry")),
                           list(d["identity_types"]) if d.get("identity_types") else None, d["tier"], d["why"]), s
    # the plan's split, as landed
    distinct = {s for s, d in I.SCHEMES.items() if d["distinct"]}
    assert {"doi", "arxiv", "pmid", "pmcid", "openalex", "s2", "mag", "bibcode"} <= distinct
    assert not ({"isbn", "issn", "oai", "handle", "md5"} & distinct)
    # auditor-B1 F6: a STRONG scheme is identity somewhere — distinct, or type-scoped — and the registry refuses a
    # row that is neither (handle, non-distinct, is no longer strong)
    import psycopg

    assert all(d["distinct"] or d.get("identity_types") for d in I.SCHEMES.values() if d.get("strong"))
    assert not I.SCHEMES["handle"].get("strong")
    with pytest.raises(psycopg.errors.CheckViolation, match="scheme_registry_strong_is_identity"):
        with pg.conn.transaction():
            pg.conn.execute("UPDATE litkb.scheme_registry SET identity_strong = true WHERE scheme = 'handle'")


@pg_only
def test_the_provenance_and_relation_vocabularies_are_the_checks(pg):
    from litkb.admit import harvest as H

    def check(table, name):
        d = pg.one("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s AND conrelid = %s::regclass",
                   (name, f"litkb.{table}"))[0]
        return set(re.findall(r"'([a-z0-9_-]+)'::text", d))
    assert check("identifier_versions", "identifier_versions_verified_by_check") == set(H.VERIFIERS)
    assert check("identifier_versions", "identifier_versions_asserted_by_check") == set(H.ASSERTERS)
    assert check("work_relations", "work_relations_relation_check") == set(H.RELATIONS)
    assert check("work_relations", "work_relations_asserted_by_check") == set(H.ASSERTERS) | {"conflict-resolution"}
    # auditor-B1 round 2 N6 (integrator-w2): the two newer tables repeat the ASSERTERS list; widening one home alone
    # would make every claim from the new source raise CheckViolation inside the harvest
    assert check("identifier_claims", "identifier_claims_asserted_by_check") == set(H.ASSERTERS)
    assert check("identifier_conflicts", "identifier_conflicts_asserted_by_check") == set(H.ASSERTERS)
    for rel, inv in H.INVERSE.items():
        assert pg.one("SELECT litkb._relation_inverse(%s)", (rel,))[0] == inv, rel


@pg_only
def test_the_unique_index_covers_exactly_the_distinct_schemes(pg):
    M = _hb1()
    want = sorted(r[0] for r in pg.conn.execute("SELECT scheme FROM litkb.scheme_registry WHERE distinct_values"))
    assert M.index_schemes(pg.conn) == want
    assert "isbn" not in want and M.nondistinct_schemes_in_unique_index(pg.conn, {}) == 0


def _open(pg, tag):
    return _hb1().open_ws(pg.conn, tag)


def _admit(pg, ws, token, work, ids, *, key=None, route="registry", file_json=None, conn=None):
    k = conn or pg.conn
    cand = k.execute("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
                     (ws, token, work["title"])).fetchone()[0]
    from psycopg.types.json import Jsonb

    return k.execute("SELECT litkb.admit(%s, %s, %s, %s, %s, %s, %s, %s, %s, 'b1-test', 'b1-test-session')",
                     (ws, token, cand, route, key or f"Tester_2020_b1-{uuid.uuid4().hex[:10]}", Jsonb(work),
                      Jsonb(ids), Jsonb(file_json) if file_json else None, Jsonb({}))).fetchone()[0]


def _registry_work(hexid, *, work_type="article", extra_ids=(), scheme="doi", value=None, year=2020):
    title = f"A CONSTRUCTED identifier-model record {hexid}"
    ev = {"registry": "crossref", "registry_title": title, "registry_first_author": "Tester", "registry_year": year,
          "registry_only": True}
    ids = [{"scheme": scheme, "value": value or f"10.5555/b1-{hexid}", "verified_by": "crossref", "evidence": ev},
           *extra_ids]
    return {"type": work_type, "title": title, "authors": [{"family": "Tester"}], "year": year}, ids


@pg_only
def test_admission_refuses_a_harvest_row_and_defaults_asserted_by(pg):
    """B1G1 / B1G2: a row with derived_from is harvest (record_identifiers takes it); every admitted identifier
    carries asserted_by — the caller's DOI, the tracker's row."""
    import psycopg

    ws, token = _open(pg, "adm")
    hexid = uuid.uuid4().hex[:10]
    work, ids = _registry_work(hexid)
    bad = ids + [{"scheme": "issn", "value": "0034-4257", "asserted_by": "crossref",
                  "derived_from": {"scheme": "doi", "value": ids[0]["value"]}}]
    with pytest.raises(psycopg.errors.InvalidParameterValue, match="harvest row"):
        _admit(pg, ws, token, work, bad)
    res = _admit(pg, ws, token, work, ids + [{"scheme": "tracker", "value": f"9{int(hexid[:6], 16)}"}])
    assert res["outcome"] == "admitted", res
    got = dict(pg.conn.execute("SELECT i.scheme, v.asserted_by FROM litkb.identifier_versions v JOIN "
                               "litkb.identifiers i ON i.id = v.identifier_id WHERE v.work_id = %s",
                               (res["work_id"],)).fetchall())
    assert got == {"doi": "caller", "tracker": "tracker"}


@pg_only
def test_record_functions_require_their_workstream_token(pg):
    """B1G3 / B1G7: both harvest writers refuse another workstream's token and write nothing."""
    import psycopg
    from psycopg.types.json import Jsonb

    ws, token = _open(pg, "tok")
    other_ws, other_token = _open(pg, "tok2")
    work, ids = _registry_work(uuid.uuid4().hex[:10])
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    w = pg.writer()
    try:
        row = [{"scheme": "issn", "value": "0034-4257", "asserted_by": "crossref"}]
        rel = [{"state": "none_returned", "asserted_by": "crossref", "derived_from": {"scheme": "doi", "value": "x"}}]
        for fn, payload in (("record_identifiers", row), ("record_work_relations", rel)):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                w.execute(f"SELECT litkb.{fn}(%s, %s, %s, %s, 'a', 's')", (ws, other_token, wid, Jsonb(payload)))
            w.execute(f"SELECT litkb.{fn}(%s, %s, %s, %s, 'a', 's')", (ws, token, wid, Jsonb(payload)))
    finally:
        w.close()
    assert pg.one("SELECT count(*) FROM litkb.identifier_versions WHERE work_id = %s AND asserted_by = 'crossref'",
                  (wid,))[0] == 1


@pg_only
def test_a_harvest_row_without_asserted_by_is_refused_and_nul_is_stripped(pg):
    """B1G4 / B1S2: provenance is required on every harvested row; a NUL in a harvested value never reaches
    the database (jsonb refuses \\u0000, which would lose the whole harvest)."""
    import psycopg

    from litkb.admit import harvest as H

    ws, token = _open(pg, "prov")
    work, ids = _registry_work(uuid.uuid4().hex[:10])
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    w = pg.writer()
    try:
        with pytest.raises(psycopg.errors.InvalidParameterValue, match="asserted_by"):
            H.record(w, ws, token, wid, [{"scheme": "issn", "value": "0034-4257"}], (), agent="a", session="s")
        got = H.record(w, ws, token, wid, [{"scheme": "issn", "value": "1558-0644", "asserted_by": "crossref",
                                            "evidence": {"as_given": "1558\x00-0644"}}], (), agent="a", session="s")
    finally:
        w.close()
    assert [x["value"] for x in got["identifiers"]["written"]] == ["1558-0644"]


@pg_only
def test_isbn_is_type_scoped_and_a_later_source_never_overwrites(pg):
    """A book's ISBN on its chapters is data (non-distinct, never a duplicate); two BOOKS with one ISBN are one
    edition: admission refuses the second as a duplicate, and a harvested copy is a counted is_identical_to
    conflict. Harvesting what a work already holds writes nothing (fatcat's monotone merge)."""
    from litkb.admit import harvest as H

    ws, token = _open(pg, "isbn")
    rng = random.Random(uuid.uuid4().int)
    body = "978" + "".join(rng.choice("0123456789") for _ in range(9))
    from litkb import identifiers as I

    isbn = body + I.check_digit13(body)                              # a CONSTRUCTED valid ISBN-13
    c1 = _admit(pg, ws, token, *_registry_work(uuid.uuid4().hex[:10], work_type="chapter"))
    c2 = _admit(pg, ws, token, *_registry_work(uuid.uuid4().hex[:10], work_type="chapter"))
    b1 = _admit(pg, ws, token, *_registry_work(uuid.uuid4().hex[:10], work_type="book",
                                                scheme="isbn", value=isbn))
    assert (c1["outcome"], c2["outcome"], b1["outcome"]) == ("admitted", "admitted", "admitted"), (c1, c2, b1)
    w = pg.writer()
    try:
        row = [{"scheme": "isbn", "value": isbn, "asserted_by": "crossref"}]
        for c in (c1, c2):
            got = H.record(w, ws, token, c["work_id"], row, (), agent="a", session="s")["identifiers"]
            assert len(got["written"]) == 1 and not got["conflicts"], got
        again = H.record(w, ws, token, c1["work_id"], row, (), agent="a", session="s")["identifiers"]
        assert len(again["held"]) == 1 and not again["written"]      # monotone: nothing overwritten
        # a second BOOK with the same ISBN is the same edition
        b2 = _admit(pg, ws, token, *_registry_work(uuid.uuid4().hex[:10], work_type="book", scheme="isbn",
                                                    value=isbn))
        assert b2["outcome"] == "duplicate" and str(b2["work_id"]) == str(b1["work_id"]), b2
        b3 = _admit(pg, ws, token, *_registry_work(uuid.uuid4().hex[:10], work_type="book"))
        got = H.record(w, ws, token, b3["work_id"], row, (), agent="a", session="s")["identifiers"]
        assert [c["relation"] for c in got["conflicts"]] == ["is_identical_to"] and not got["written"]
    finally:
        w.close()


def _manual(pg, ws, token, title, ids, work_type, year=2019):
    """A MANUAL admission (route manual, with a CONSTRUCTED bound file) — the route an ISBN-carrying report or a
    handle-only record takes. Every value CONSTRUCTED."""
    from psycopg.types.json import Jsonb

    binding = {"verdict": "bound", "ratio": 1.0, "matched": title, "registry_title": title, "author_found": True,
               "author_near_title": True, "text_layer": True, "page": 1, "title_region": True}
    file_json = {"sha256": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                 "rel_path": f"_litkb_staging/b1-{uuid.uuid4().hex[:8]}.pdf", "binding": binding}
    cand = pg.conn.execute("SELECT litkb.add_candidate(%s, %s, 'manual', NULL, NULL, NULL, NULL, %s, NULL, NULL, NULL)",
                           (ws, token, title)).fetchone()[0]
    work = {"type": work_type, "title": title, "authors": [{"family": "Tester", "given": ""}], "year": year}
    return pg.conn.execute(
        "SELECT litkb.admit(%s, %s, %s, 'manual', %s, %s, %s, %s, %s, 'b1-test', 'b1-test-session')",
        (ws, token, cand, f"Tester_{year}_manual-{uuid.uuid4().hex[:10]}", Jsonb(work),
         Jsonb([{**i, "verified_by": "manual", "evidence": {"source": "CONSTRUCTED"}} for i in ids]),
         Jsonb(file_json), Jsonb({}))).fetchone()[0]


@pg_only
@pytest.mark.parametrize("scheme, work_type", [("isbn", "report"), ("isbn", "chapter"), ("handle", "report"),
                                               (None, "report")])
def test_the_same_record_twice_is_never_silently_a_second_work(pg, scheme, work_type):
    """Auditor-B1 F6 (a regression against 0014 the audit measured): the SAME record — same title, same value of a
    scheme that is NOT this record's identity (an ISBN outside a book, a handle anywhere) — admitted twice.
    Check 2's lookup rightly does not look for such a value, so it must not count as STRONG either: the title
    review runs and the second admission is `duplicate-review`, as the no-identifier control is. Before the fix
    the second was `proposed` — a silent second work. CONSTRUCTED in every value (the title is mostly random so
    no other test's title is near it)."""
    ws, token = _open(pg, "twice")
    hexid = uuid.uuid4().hex[:10]
    title = f"{uuid.uuid4().hex} {hexid} constructed grey literature record"
    value = {"isbn": _hb1().constructed_isbn(hexid), "handle": f"1721.1/b1-{hexid}"}.get(scheme)
    ids = [{"scheme": scheme, "value": value}] if scheme else []
    first = _manual(pg, ws, token, title, ids, work_type)
    second = _manual(pg, ws, token, title, ids, work_type)
    assert first["outcome"] == "proposed", first
    assert second["outcome"] == "duplicate-review", (scheme, work_type, second["outcome"])


@pg_only
def test_a_chapter_admitted_with_its_book_s_isbn_is_not_the_book(pg):
    """Check 2's ISBN type scope AT ADMISSION (auditor-B1 O2 survived the suite): a chapter carrying its book's
    ISBN is not a duplicate of the book — the ISBN is identity only between two books."""
    ws, token = _open(pg, "chapisbn")
    hexid = uuid.uuid4().hex[:10]
    isbn = _hb1().constructed_isbn(hexid)
    book = _admit(pg, ws, token, *_registry_work(hexid + "b", work_type="book", scheme="isbn", value=isbn))
    chapter = _manual(pg, ws, token, f"{uuid.uuid4().hex} {hexid} constructed chapter of a book",
                      [{"scheme": "isbn", "value": isbn}], "chapter")
    assert book["outcome"] == "admitted" and chapter["outcome"] == "proposed", (book, chapter)


@pg_only
def test_a_chapter_s_is_part_of_its_book_s_isbn_fills_part_of_work_id(pg):
    """Auditor-B1 F13: chapter -> book (the plan's first common case) through the book's ISBN, a TYPE-SCOPED
    scheme. The relation's target is the BOOK holding the value, whatever the chapter's own type — before the
    fix `_identity_holder` asked for two books and the parent never filled."""
    from litkb.admit import harvest as H

    ws, token = _open(pg, "chapbook")
    hexid = uuid.uuid4().hex[:10]
    isbn = _hb1().constructed_isbn(hexid)
    book = _admit(pg, ws, token, *_registry_work(hexid + "b", work_type="book", scheme="isbn", value=isbn))
    chapter = _admit(pg, ws, token, *_registry_work(hexid + "c", work_type="chapter"))
    edge = {"relation": "is_part_of", "source_relation": "IsPartOf", "state": "asserted", "asserted_by": "datacite",
            "target_scheme": "isbn", "target_value": isbn, "derived_from": {"scheme": "doi", "value": "x"},
            "evidence": {}}
    w = pg.writer()
    try:
        got = H.record(w, ws, token, chapter["work_id"], (), [edge], agent="a", session="s")["relations"]
    finally:
        w.close()
    assert str(got["edges"][0]["target_work_id"]) == str(book["work_id"]) and got["edges"][0]["parent"] == "filled"
    assert str(pg.one("SELECT part_of_work_id FROM litkb.works WHERE id = %s", (chapter["work_id"],))[0]) == \
        str(book["work_id"])


@pg_only
def test_a_candidate_identifier_waits_for_its_registry(pg):
    """Auditor-B1 F12: `arxiv_to_doi` is a CANDIDATE until DataCite confirms it (plan item 3). Offered with no
    `verified_by` it is refused (returned, not written); named confirmed, it is written."""
    from litkb import identifiers as I
    from litkb.admit import harvest as H

    ws, token = _open(pg, "cand")
    work, ids = _registry_work(uuid.uuid4().hex[:10], work_type="preprint")
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    arx = f"2601.{random.Random(uuid.uuid4().int).randint(10000, 99999)}"
    cand = I.arxiv_to_doi(arx)
    w = pg.writer()
    try:
        got = H.record(w, ws, token, wid, [cand], (), agent="a", session="s")["identifiers"]
        assert got["written"] == [] and "confirmation" in got["refused"][0]["reason"], got
        # auditor-B1 round 2 N1 (integrator-w2): the derivation itself and a person confirm nothing
        for who in ("deterministic", "manual"):
            got = H.record(w, ws, token, wid, [dict(cand, verified_by=who)], (), agent="a", session="s")["identifiers"]
            assert got["written"] == [] and "confirmation" in got["refused"][0]["reason"], (who, got)
        got = H.record(w, ws, token, wid, [dict(cand, verified_by="datacite")], (), agent="a", session="s")
    finally:
        w.close()
    assert [x["value"] for x in got["identifiers"]["written"]] == [I.ARXIV_DOI_PREFIX + arx]


@pg_only
def test_a_failed_harvest_never_takes_a_transactional_caller_s_work_with_it(pg):
    """Auditor-B1 F14: `harvest.record` runs in its own transaction block — inside a caller's open transaction a
    SAVEPOINT — so a harvest that fails (here: a row naming no asserted_by) rolls back only itself; the caller's
    transaction stays usable and its earlier write commits."""
    import psycopg

    from litkb.admit import harvest as H

    ws, token = _open(pg, "savepoint")
    work, ids = _registry_work(uuid.uuid4().hex[:10])
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    w = pg.writer()
    try:
        w.autocommit = False
        w.execute("SELECT 1")                       # the caller's transaction is open
        H.record(w, ws, token, wid, [{"scheme": "issn", "value": "0034-4257", "asserted_by": "crossref"}], (),
                 agent="a", session="s")
        with pytest.raises(psycopg.errors.InvalidParameterValue, match="asserted_by"):
            H.record(w, ws, token, wid, [{"scheme": "issn", "value": "1558-0644"}], (), agent="a", session="s")
        assert w.execute("SELECT 1").fetchone()[0] == 1          # not InFailedSqlTransaction
        w.commit()
    finally:
        w.close()
    assert pg.one("SELECT count(*) FROM litkb.identifier_versions v JOIN litkb.identifiers i ON i.id = v.identifier_id "
                  "WHERE v.work_id = %s AND i.scheme = 'issn'", (wid,))[0] == 1


@pg_only
def test_the_migration_refuses_an_index_the_registry_disagrees_with(pg):
    """Auditor-B1 F9: 0032's guard 'the unique index covers exactly the registry's distinct schemes' is dormant on
    a correct migration, so it is exercised directly: its DO block, read from the migration file as it is NOW,
    run against the index widened to a non-distinct scheme (oai), inside a transaction rolled back by the
    refusal. The control: the same block passes the real index."""
    import psycopg

    mig = (SCRIPTS / "pipeline" / "litkb" / "db" / "migrations" / "0032_identifier_model.sql").read_text(encoding="utf-8")
    marker = "the unique index covers exactly the registry's distinct schemes"
    blocks = [b for b in re.findall(r"DO \$\$.*?\n\$\$;", mig, flags=re.S) if marker in b]
    assert len(blocks) == 1, len(blocks)
    covered = _hb1().index_schemes(pg.conn)
    widened = ", ".join(f"'{s}'" for s in sorted(set(covered) | {"oai"}))
    with pytest.raises(psycopg.errors.RaiseException, match="identifiers_active_scheme_value covers"):
        with pg.conn.transaction():
            pg.conn.execute("DROP INDEX litkb.identifiers_active_scheme_value")
            pg.conn.execute("CREATE UNIQUE INDEX identifiers_active_scheme_value ON litkb.identifiers "
                            f"(scheme, value_norm) WHERE active AND scheme IN ({widened})")
            pg.conn.execute(blocks[0])
            raise psycopg.Rollback()     # reached only if the guard did NOT refuse: the widened index never commits
    assert _hb1().index_schemes(pg.conn) == covered              # rolled back
    pg.conn.execute(blocks[0])                                    # control: the real index passes


@pg_only
def test_the_backfill_driver_connects_and_dry_runs_by_default(pg, capsys):
    """Auditor-B1 F2: the reviewed backfill DRIVER (its `main`, not only its function) connects — through
    `references_ingest.connect`, the ingest login's one rule (a worker database: owner login + SET ROLE
    litkb_ingest). Before, `db.connect.connect(db, 'litkb_ingest')` was refused before any driver import."""
    from psycopg.types.json import Jsonb

    from litkb.db import connect as c

    ws, token = _open(pg, "bfmain")
    work, ids = _registry_work(uuid.uuid4().hex[:10])
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    pg.conn.execute("SELECT litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, NULL, %s, 'a', 's')",
                    (Jsonb({"scheme": "tracker"}), Jsonb({"work_id": str(wid), "value": f"7{uuid.uuid4().int % 10**8}",
                                                          "verified_by": None, "evidence": {}, "status": "active"}), ws))
    spec = importlib.util.spec_from_file_location("bf_main", SCRIPTS / "qc" / "instruments" /
                                                  "litkb_identifier_provenance_backfill.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    capsys.readouterr()
    assert bf.main(["--db", c.DB_TEST]) == 0
    dry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert dry["apply"] is False and dry["updated"] == 0 and dry["plan"].get("tracker -> tracker", 0) >= 1, dry
    # auditor-B1 round 2 N8 (integrator-w2): a write names its session; `--apply` alone is refused, nothing written
    with pytest.raises(SystemExit, match="--session"):
        bf.main(["--db", c.DB_TEST, "--apply"])
    assert _hb1().identifiers_without_provenance(pg.conn, {}) >= 1
    assert bf.main(["--db", c.DB_TEST, "--apply", "--session", "b1-test-main"]) == 0
    done = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert done["apply"] is True and done["updated"] >= 1, done
    assert _hb1().identifiers_without_provenance(pg.conn, {}) == 0


@pg_only
def test_relation_edges_missing_finds_a_work_by_its_doi(pg, tmp_path):
    """Auditor-B1 F8: a probe row's DOI finds its work when the row's key is not the work's key (the DOI clause
    was handed the key). CONSTRUCTED probe rows."""
    from litkb.admit import harvest as H

    M, P = _hb1(), _probe_module()
    ws, token = _open(pg, "relmiss")
    work, ids = _registry_work(uuid.uuid4().hex[:10])
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    doi = ids[0]["value"]
    out = tmp_path / "litkb_acq_probe_relation.csv"
    P.write_csv([{"key": "Nobody_1900_not-this-key", "doi": doi, "cr_status": 200, "state": "asserted",
                  "relation": "has_preprint", "source_relation": "has-preprint", "target_scheme": "doi",
                  "target_value": f"{doi}.preprint"}], out)
    m = {"probe_csvs": {M.RELATION_PROBE: str(out)}}
    assert M.relation_edges_missing(pg.conn, m) == 1                    # found by DOI, and it has no edge yet
    w = pg.writer()
    try:
        H.record(w, ws, token, wid, (), [{"relation": "has_preprint", "state": "asserted", "asserted_by": "crossref",
                                         "target_scheme": "doi", "target_value": f"{doi}.preprint"}],
                 agent="a", session="s")
    finally:
        w.close()
    assert M.relation_edges_missing(pg.conn, m) == 0


@pg_only
def test_a_parent_is_filled_once_and_never_overwritten(pg):
    """B1G9: the monotone trigger on works' parent columns."""
    import psycopg

    ws, token = _open(pg, "parent")
    a, b, c = (_admit(pg, ws, token, *_registry_work(uuid.uuid4().hex[:10]))["work_id"] for _ in range(3))
    pg.conn.execute("UPDATE litkb.works SET version_of_work_id = %s WHERE id = %s", (b, a))
    with pytest.raises(psycopg.errors.CheckViolation, match="never overwrites"):
        pg.conn.execute("UPDATE litkb.works SET version_of_work_id = %s WHERE id = %s", (c, a))
    assert str(pg.one("SELECT version_of_work_id FROM litkb.works WHERE id = %s", (a,))[0]) == str(b)


@pg_only
def test_a_relation_to_a_work_already_in_the_base_fills_its_parent(pg):
    """B1G8: a stated direction to a work in the base fills the parent column at insertion (chapter -> book),
    and the third state records an empty field without inventing a relation."""
    from litkb.admit import harvest as H

    ws, token = _open(pg, "partof")
    hexid = uuid.uuid4().hex[:10]
    book = _admit(pg, ws, token, *_registry_work(hexid + "b", work_type="book"))
    chapter = _admit(pg, ws, token, *_registry_work(hexid + "c", work_type="chapter"))
    book_doi = pg.one("SELECT i.value_norm FROM litkb.identifiers i JOIN litkb.identifier_versions v ON "
                      "v.version_id = i.current_version_id WHERE v.work_id = %s AND i.scheme = 'doi'",
                      (book["work_id"],))[0]
    edge = {"relation": "is_part_of", "source_relation": "is-part-of", "state": "asserted", "asserted_by": "crossref",
            "target_scheme": "doi", "target_value": book_doi,
            "derived_from": {"scheme": "doi", "value": "x"}, "evidence": {}}
    w = pg.writer()
    try:
        got = H.record(w, ws, token, chapter["work_id"], (), [edge], agent="a", session="s")["relations"]
        again = H.record(w, ws, token, chapter["work_id"], (), [edge], agent="a", session="s")["relations"]
        empty = H.record(w, ws, token, book["work_id"], (), [H.none_returned("crossref", ("doi", book_doi),
                                                                              "relation")], agent="a", session="s")
    finally:
        w.close()
    assert got["edges"][0]["parent"] == "filled" and again["edges"][0]["held"] is True
    assert str(pg.one("SELECT part_of_work_id FROM litkb.works WHERE id = %s", (chapter["work_id"],))[0]) == \
        str(book["work_id"])
    assert pg.one("SELECT relation, state FROM litkb.work_relations WHERE work_id = %s",
                  (book["work_id"],)) == (None, "none_returned")
    assert empty["relations"]["edges"][0]["state"] == "none_returned"


@pg_only
def test_the_backfill_fills_null_provenance_only_and_dry_runs_by_default(pg, tmp_path):
    from psycopg.types.json import Jsonb

    ws, token = _open(pg, "backfill")
    work, ids = _registry_work(uuid.uuid4().hex[:10])
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    # CONSTRUCTED rows written the way every pre-0032 row was: no asserted_by
    for scheme, value, vb in (("tracker", f"8{uuid.uuid4().int % 10**8}", None),
                              ("legacy_stem", f"Stem_{uuid.uuid4().hex[:8]}", None)):
        pg.conn.execute("SELECT litkb._write_version('fact', 'identifier', NULL, %s, NULL, %s, NULL, %s, 'a', 's')",
                        (Jsonb({"scheme": scheme}), Jsonb({"work_id": str(wid), "value": value, "verified_by": vb,
                                                           "evidence": {}, "status": "active"}), ws))
    spec = importlib.util.spec_from_file_location("bf", SCRIPTS / "qc" / "instruments" /
                                                  "litkb_identifier_provenance_backfill.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    k = pg.conn
    k.execute("SET ROLE litkb_ingest")
    try:
        dry = bf.backfill(k, apply=False, session="b1-test")
        assert dry["updated"] == 0 and dry["plan"].get("tracker -> tracker", 0) >= 1
        done = bf.backfill(k, apply=True, session="b1-test")
        again = bf.backfill(k, apply=True, session="b1-test")
    finally:
        k.execute("RESET ROLE")
    assert done["updated"] >= 2 and again["updated"] == 0
    got = dict(pg.conn.execute("SELECT i.scheme, v.asserted_by || '/' || v.provenance_backfilled FROM "
                               "litkb.identifier_versions v JOIN litkb.identifiers i ON i.id = v.identifier_id "
                               "WHERE v.work_id = %s", (wid,)).fetchall())
    assert got == {"doi": "caller/false", "tracker": "tracker/true", "legacy_stem": "legacy/true"}


@pg_only
def test_an_archive_answer_s_identifiers_are_written_with_their_provenance(pg):
    """`harvest.record_route_identifiers` (the acquisition write the orchestrator wires into acquire/run.py): an
    Anna's route answer (CONSTRUCTED: the result-dict shape `fetch_for_litkb` returns) -> md5 derived from the
    work's DOI, isbn/zlib derived from that md5, asserted_by annas; a non-archive route writes nothing."""
    from litkb.admit import harvest as H

    ws, token = _open(pg, "annas")
    hexid = uuid.uuid4().hex[:10]
    work, ids = _registry_work(hexid)
    wid = _admit(pg, ws, token, work, ids)["work_id"]
    md5 = hashlib.md5(hexid.encode()).hexdigest()
    answer = {"status": "downloaded", "md5": md5, "record_doi": ids[0]["value"],
              "identifiers_unified": {"doi": [ids[0]["value"]], "md5": [md5], "zlib": ["123456"],
                                      "ipfs_cid": ["bafy-not-a-work-identifier"]}}
    w = pg.writer()
    try:
        assert H.record_route_identifiers(w, ws, token, wid, ids[0]["value"], "open_access", answer,
                                          agent="a", session="s") is None
        got = H.record_route_identifiers(w, ws, token, wid, ids[0]["value"], "annas", answer, agent="a", session="s")
    finally:
        w.close()
    assert {x["scheme"] for x in got["identifiers"]["written"]} == {"md5", "zlib"}
    assert {s["key"] for s in got["skipped"]} == {"doi", "ipfs_cid"}
    rows = {(s, a, d) for s, a, d in pg.conn.execute(
        "SELECT i.scheme, v.asserted_by, v.derived_from_scheme FROM litkb.identifier_versions v JOIN "
        "litkb.identifiers i ON i.id = v.identifier_id WHERE v.work_id = %s AND i.scheme IN ('md5', 'zlib')",
        (wid,)).fetchall()}
    assert rows == {("md5", "annas", "doi"), ("zlib", "annas", "md5")}


@pg_only
def test_admission_harvests_its_registry_answer_with_provenance(pg):
    """B1P2: an admission's Crossref record (CONSTRUCTED, Elsevier-shaped) fills pii / issn / relation rows with
    asserted_by crossref and derived_from its DOI — and a DUPLICATE hunt of the same DOI fills what is still
    missing, never overwriting (the E21 fire below covers the relation edge between two works)."""
    M = _hb1()
    from litkb.admit import front

    ws, token = _open(pg, "harvest")
    hexid = uuid.uuid4().hex[:8]
    doi = f"10.1016/j.b1.{hexid}"
    pii = f"S{int(hexid, 16) % 10**15:015d}X"
    rec = {"DOI": doi, "type": "journal-article", "title": [f"A CONSTRUCTED Elsevier record {hexid}"],
           "author": [{"family": "Tester", "given": "T", "sequence": "first"}], "issued": {"date-parts": [[2021]]},
           "member": "78", "alternative-id": [pii], "issn-type": [{"value": "0034-4257", "type": "print"}],
           "relation": {}}
    w = pg.writer()
    try:
        res = front.admit_registry(w, ws, token, doi=doi, agent="b1", session="b1-s",
                                   client=M.RegistryStub(crossref={doi: rec}), pacer=M._nopace())
        rec2 = dict(rec) | {"ISBN": ["0-306-40615-2"]}
        dup = front.admit_registry(w, ws, token, doi=doi, agent="b1", session="b1-s2",
                                   client=M.RegistryStub(crossref={doi: rec2}), pacer=M._nopace())
    finally:
        w.close()
    assert res["outcome"] == "admitted" and not res["harvest"]["identifiers"]["conflicts"], res
    assert dup["outcome"] == "duplicate" and dup["harvest"]["identifiers"]["written"][0]["scheme"] == "isbn", dup
    got = {(s, a, d) for s, a, d in pg.conn.execute(
        "SELECT i.scheme, v.asserted_by, v.derived_from_scheme || ':' || v.derived_from_value FROM "
        "litkb.identifier_versions v JOIN litkb.identifiers i ON i.id = v.identifier_id WHERE v.work_id = %s",
        (res["work_id"],)).fetchall()}
    assert got == {("doi", "caller", None), ("pii", "crossref", f"doi:{doi}"), ("issn", "crossref", f"doi:{doi}"),
                   ("isbn", "crossref", f"doi:{doi}")}
    assert pg.one("SELECT state FROM litkb.work_relations WHERE work_id = %s", (res["work_id"],))[0] == "none_returned"


# ── every fire of litkb_hardening_b1.py, both arms ───────────────────────────────────────────────────

@pg_only
def test_fire_relation_probe_emptied(pg, tmp_path):
    M = _hb1()
    assert M.fire_relation_probe_emptied(pg.conn, "control", tmp_path / "c") >= 1
    assert M.fire_relation_probe_emptied(pg.conn, "known_bad", tmp_path / "k") == 0


@pg_only
def test_fire_key_rule_reverted_row_187(pg, tmp_path):
    """187's DataCite record: the reverted key rule crashes admit:CheckViolation; the length rule admits it with
    the derived key and no --key. The known-bad arm runs FIRST here: this database is shared, and once the
    control arm has admitted the DOI a later hunt would find it held instead of deriving a key."""
    M = _hb1()
    state, reason, _ = M.hunt_187(pg.conn, tmp_path, make_key=M.legacy_make_key)
    assert (state, reason) == ("crashed", "admit:CheckViolation")
    assert M.fire_key_rule_reverted(pg.conn, "known_bad", tmp_path / "k") == 1
    # auditor-B1 F3: the surname guard DELETED (not the rule reverted) crashes in the S4.5 shape — make_key
    # refusing by name — and the counter sees that shape too. Also before the control arm, for the same reason.
    state, reason, _ = M.hunt_187(pg.conn, tmp_path, make_key=M.make_key_without_surname_guard())
    assert (state, reason) == ("crashed", "admit:KeyUnderivable")
    assert M.fire_key_guard_deleted(pg.conn, "known_bad", tmp_path / "g") == 1
    state, reason, res = M.hunt_187(pg.conn, tmp_path)
    assert state == "held", (state, reason)
    assert pg.one("SELECT key FROM litkb.works WHERE id = %s", (res["admission"]["work_id"],))[0] == \
        "LPVSWGCV_2025_land-cover-change-map"


@pg_only
def test_fire_harvest_disabled_crosswalk(pg, tmp_path):
    M = _hb1()
    from litkb.admit import harvest as H

    rows, wids, missing = M.crosswalk_world(pg.conn)
    assert len(rows) == 3 and missing == 0
    # the article reaches its arXiv copy through the edge, not through an alias (litkb-sibling-edition)
    got = H.copy_identifiers(pg.conn, wids[rows[0]["key"]])
    assert ("arxiv", rows[0]["s2_arxiv"], "has_version") in got
    assert ("arxiv", rows[0]["s2_arxiv"]) not in {(s, v) for s, v, via in got if via == "own"}
    assert M.fire_harvest_disabled(pg.conn, "known_bad", tmp_path) == 3


@pg_only
def test_fire_null_asserted_by(pg, tmp_path):
    M = _hb1()
    assert M.fire_null_asserted_by(pg.conn, "control", tmp_path) == 0
    assert M.fire_null_asserted_by(pg.conn, "known_bad", tmp_path) == 1


@pg_only
def test_fire_constructed_second_work_claims_an_existing_doi(pg, tmp_path):
    """fatcat's collision rule: the harvested DOI is DROPPED from the second work, an is_version_of edge is
    asserted by conflict-resolution, and the conflict is COUNTED — the counter reads 0 only because it moved."""
    M = _hb1()
    ws, a, b, got = M.conflict_world(pg.conn)
    assert got["written"] == [] and len(got["conflicts"]) == 1, got
    edge = pg.one("SELECT relation, asserted_by, conflict_source, target_work_id FROM litkb.work_relations "
                  "WHERE work_id = %s", (b,))
    assert edge[:3] == ("is_version_of", "conflict-resolution", "doi") and str(edge[3]) == str(a)
    assert pg.one("SELECT count(*) FROM litkb.identifier_conflicts WHERE claimed_by_work_id = %s", (b,))[0] == 1
    assert pg.one("SELECT count(*) FROM litkb.identifier_versions v JOIN litkb.identifiers i ON "
                  "i.id = v.identifier_id WHERE v.work_id = %s AND i.scheme = 'doi'", (b,))[0] == 0
    # the claim itself is a durable row, resolved `conflict` against its holder
    claim = pg.one("SELECT outcome, held_by_work_id FROM litkb.identifier_claims WHERE work_id = %s AND scheme = 'doi'",
                   (b,))
    assert claim is not None and claim[0] == "conflict" and str(claim[1]) == str(a), claim
    assert M.conflicts_uncounted(pg.conn, {"scope_workstream_ids": [ws]}) == 0
    assert M.fire_constructed_conflict(pg.conn, "known_bad", tmp_path) == 1


@pg_only
def test_fire_conflict_detection_removed_keeps_the_claim_collided(pg, tmp_path):
    """Codex X4 / auditor-B1 F4 (its O6): conflict DETECTION removed from litkb.record_identifiers (in-process, on
    this database) — the write meets the unique index. The claim survives as `collided`, the call returns, and
    conflicts_uncounted reads it. Before identifier_claims this arm raised UniqueViolation (the harvest error
    was returned, not stored) and the counter read 0."""
    M = _hb1()
    assert M.fire_conflict_detection_removed(pg.conn, "control", tmp_path) == 0
    ws, _a, b, got = M.conflict_world(pg.conn, known_bad=True, strip=M.DETECTION_GUARD)
    assert got["written"] == [] and got["conflicts"] == [] and len(got["collided"]) == 1, got
    claim = pg.one("SELECT outcome, error FROM litkb.identifier_claims WHERE work_id = %s AND scheme = 'doi'", (b,))
    assert claim is not None and claim[0] == "collided" and "identifiers_active_scheme_value" in claim[1], claim
    assert M.conflicts_uncounted(pg.conn, {"scope_workstream_ids": [ws]}) == 1
    assert M.DETAILS["conflicts_uncounted"](pg.conn, {"scope_workstream_ids": [ws]})[0].endswith(": collided")
    assert M.fire_conflict_detection_removed(pg.conn, "known_bad", tmp_path) == 1


@pg_only
@pytest.mark.parametrize("column", ["cr_isbn", "cr_relation_types"])
def test_fire_crosswalk_isbn_and_relation_clauses(pg, tmp_path, column):
    """Auditor-B1 F5: the crosswalk counter's ISBN clause and its relation clause, each shown to fire on its own
    CONSTRUCTED row (the arXiv fire exercises only the `s2_arxiv` clause)."""
    M = _hb1()
    run = {"cr_isbn": M.fire_crosswalk_isbn, "cr_relation_types": M.fire_crosswalk_relation}[column]
    assert run(pg.conn, "control", tmp_path / "c") == 0
    assert run(pg.conn, "known_bad", tmp_path / "k") == 1


@pg_only
def test_fire_isbn_in_distinct_set(pg, tmp_path):
    M = _hb1()
    assert M.fire_isbn_in_distinct_set(pg.conn, "control", tmp_path) == 0
    assert M.fire_isbn_in_distinct_set(pg.conn, "known_bad", tmp_path) == 1
    assert M.fire_isbn_in_distinct_set(pg.conn, "control", tmp_path) == 0       # restored
    # the index itself widened to a plan-non-distinct scheme no test writes (oai) is counted too
    with M.index_with(pg.conn, "oai"):
        assert M.nondistinct_detail(pg.conn) == ["oai"]
    assert M.nondistinct_schemes_in_unique_index(pg.conn, {}) == 0


@pg_only
def test_fire_e21_pair_is_two_works_and_one_edge(pg, tmp_path):
    """litkb-sibling-edition: E21's preprint and article are TWO works, linked by ONE registry relation edge (the
    article's has-preprint; the preprint's is-preprint-of is the same fact from the other side and fills the
    edge's target instead of writing a second), and the preprint's version_of_work_id names the article."""
    M = _hb1()
    ws, res = M.e21_world(pg.conn, tmp_path)
    assert [r["outcome"] for r in res] == ["admitted", "admitted"], res
    article, preprint = (r["work_id"] for r in res)
    edges = pg.conn.execute("SELECT work_id, relation, target_work_id, asserted_by FROM litkb.work_relations "
                            "WHERE workstream_id = %s AND state = 'asserted'", (ws,)).fetchall()
    assert [(str(w), r, str(t), a) for w, r, t, a in edges] == [(str(article), "has_preprint", str(preprint),
                                                                 "crossref")]
    assert str(pg.one("SELECT version_of_work_id FROM litkb.works WHERE id = %s", (preprint,))[0]) == str(article)
    assert M.fire_e21_pair(pg.conn, "known_bad", tmp_path) == 2


@pg_only
def test_fire_e06_still_refuses_duplicate_review(pg, tmp_path):
    M = _hb1()
    assert M.fire_e06(pg.conn, "control", tmp_path) == 0
    assert M.fire_e06(pg.conn, "known_bad", tmp_path) == 1
