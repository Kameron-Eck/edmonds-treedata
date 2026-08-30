"""The dashboard's step chips must actually find their rows.

A NEAR-MISS, NOT A POST-MORTEM. On 2026-08-30 `latest_by_key` was re-keyed from
(job, step) to the ledger's full identity (job, year, tag, step) — correct, and the
reason is in names.py::job_key. But the five places that LOOKED UP in that dict still
built 2-tuples:

    r = qlatest.get((j["id"], st)) or merged_latest.get((j["id"], st))

A 2-tuple lookup against a 4-tuple dict does not raise. It returns None. Every step chip
on every card would have rendered blank — no error, no traceback, a dashboard that draws
perfectly and shows nothing. The file compiled clean, and nothing imported the module, so
the only thing that would have caught it is a human noticing the queue looked idle. A
monitoring tool that silently shows nothing is worse than one that crashes.

It is the same shape as the state-vocabulary blind spot fixed the same day: the oversight
tool reporting fine because it could not see.

WHY THE CODE MOVED. The chip block lived inside `build_card`, which probes live VMs and
reads the lake, so it could not be called from a test at all. It is now
`fill_job_chips(jobs, qlatest, merged_latest)` — pure, and exercised below. Making it
testable is the actual fix; the key correction alone would have left the next such change
just as unguarded.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_dashboard_chips.py -q
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))
sys.path.insert(0, str(SCRIPTS / "qc"))

import runtime_dashboard as D  # noqa: E402


def _rows(job, year, tag, state="OK"):
    """Ledger rows shaped the way phase4_train_queue writes them."""
    return [
        {"job": job, "year": year, "tag": tag, "step": "train",
         "state": state, "minutes": "35.7", "ts": "2026-08-29 17:13:55"},
        {"job": job, "year": year, "tag": tag, "step": "VERIFY:train",
         "state": state, "minutes": "", "ts": "2026-08-29 17:14:00"},
    ]


def test_a_chip_finds_its_row():
    """The end-to-end check a compile pass cannot make."""
    latest = D.latest_by_key(_rows("2009", "2009", "rgb3_nodeb_twin"))
    jobs = [{"id": "2009", "year": "2009", "tag": "rgb3_nodeb_twin", "expect": ""}]
    D.fill_job_chips(jobs, latest, {})

    train = next(c for c in jobs[0]["steps"] if c["step"] == "train")
    assert train["state"] == "OK", (
        "the train chip is blank — the lookup key does not match latest_by_key's key")
    assert train["verify"] == "OK", "the VERIFY chip is blank for the same reason"
    assert train["minutes"] == "35.7"
    assert train["src"] == "this"


def test_two_arms_on_one_year_do_not_share_a_chip():
    """The point of the 4-tuple. Two jobs whose ids collide but whose tags differ must
    read their own rows — under (job, step) the second silently overwrote the first and
    both cards showed one arm's state."""
    latest = D.latest_by_key(_rows("2009", "2009", "arm_a")
                             + _rows("2009", "2009", "arm_b", state="FAIL"))
    for tag, want in (("arm_a", "OK"), ("arm_b", "FAIL")):
        jobs = [{"id": "2009", "year": "2009", "tag": tag, "expect": ""}]
        D.fill_job_chips(jobs, latest, {})
        got = next(c for c in jobs[0]["steps"] if c["step"] == "train")["state"]
        assert got == want, f"{tag} shows {got}, not its own {want}"


def test_an_int_tag_from_yaml_still_matches_the_csv_text():
    """`tag: 2020` in a queue yaml parses as an int; the CSV holds "2020". job_key's
    str() on both sides is what makes them the same job — the dashboard reads the yaml
    directly, so it is the call site most exposed to this."""
    latest = D.latest_by_key(_rows("2020", "2020", "2020"))
    jobs = [{"id": "2020", "year": 2020, "tag": 2020, "expect": ""}]
    D.fill_job_chips(jobs, latest, {})
    got = next(c for c in jobs[0]["steps"] if c["step"] == "train")["state"]
    assert got == "OK", "an int tag from yaml did not match the CSV's text"


def test_a_prior_launch_is_labelled_prior_not_this():
    """`src` drives the UI's this-launch/earlier-launch distinction, and it is computed
    from the same key. If the key is wrong it does not just blank the chip — it can also
    attribute an old launch's row to the running one."""
    prior = D.latest_by_key(_rows("2009", "2009", "t"))
    jobs = [{"id": "2009", "year": "2009", "tag": "t", "expect": ""}]
    D.fill_job_chips(jobs, {}, prior)          # nothing from THIS launch
    train = next(c for c in jobs[0]["steps"] if c["step"] == "train")
    assert train["state"] == "OK" and train["src"] == "prior"


def test_a_running_step_is_reported():
    """fill_job_chips returns the RUNNING step; the card's header depends on it, so a
    key mismatch would also make a live queue look stopped."""
    rows = [{"job": "2009", "year": "2009", "tag": "t", "step": "train",
             "state": "RUNNING", "minutes": "", "ts": "2026-08-29 17:13:55"}]
    jobs = [{"id": "2009", "year": "2009", "tag": "t", "expect": ""}]
    running = D.fill_job_chips(jobs, D.latest_by_key(rows), {})
    assert running and running["step"] == "train" and running["job"] == "2009"


def test_no_two_tuple_lookups_remain():
    """Static backstop for the shape that failed silently — a 2-tuple `.get` against
    this dict returns None rather than raising, so nothing at runtime would report it."""
    src = (SCRIPTS / "qc" / "runtime_dashboard.py").read_text(encoding="utf-8")
    assert 'qlatest.get((j["id"]' not in src, (
        "a chip lookup still builds a 2-tuple; latest_by_key is keyed on 4")
    assert 'merged_latest.get((j["id"]' not in src
    assert "job_key(" in src


def test_build_card_still_delegates_to_the_extracted_function():
    """The extraction is only worth something while the real render path uses it — a
    copy left behind in build_card would be tested by nothing, which is where this
    started."""
    import inspect
    src = inspect.getsource(D.build_card)
    assert "fill_job_chips(" in src, "build_card no longer uses the tested function"
    assert "chips = []" not in src, "build_card grew its own copy of the chip loop again"
