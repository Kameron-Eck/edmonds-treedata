"""auditor-C2a round 2 F3, builder A's half (applied at the merge: builder-C2a-r3.md, scratch merge_patches.py):
`stage_b_rungs_unmeasured` reads a `not-asked: <route> <works reached> <condition>` line as the measure of a Stage B
rung the registry gives an `ask_condition` (builder C2a's `run.Rung` field). Builder C2a's own half — the line printed
from the run — is tested by
qc/test_litkb_stage_ab.py::test_a_conditional_rung_its_condition_skipped_on_every_row_prints_a_not_asked_line
No test touches the network or a database.

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 -m pytest qc/test_litkb_s45_not_asked.py -q
"""
import importlib.util
import types
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_litkb_hardening_a_not_asked",
                                               SCRIPTS / "qc" / "instruments" / "litkb_hardening_a.py")
HA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(HA)


def test_builder_a_s_counter_reads_a_conditional_rung_s_not_asked_line_as_measured(tmp_path):
    """The line measures a rung the registry gives an ask condition, when it reached at least one work and states the
    registry's own condition; never for an unconditional rung, a line that reached nobody, or a hand-typed reason. The
    known-bad: the zenodo line deleted -> zenodo unmeasured. A yield line that asked rows measures a rung; with a
    not-asked line beside it the rung is unmeasured, and a paraphrased condition answers nothing (S4.5 decision D32,
    integrator-w3). CONSTRUCTED
    registry (rung objects carrying the field) and report."""
    rungs = [types.SimpleNamespace(route="zenodo", ask_condition="CONSTRUCTED condition Z"),
             types.SimpleNamespace(route="figshare", ask_condition="CONSTRUCTED condition F"),
             types.SimpleNamespace(route="europepmc", ask_condition="CONSTRUCTED condition E"),
             types.SimpleNamespace(route="hal", ask_condition="")]
    _built, unbuilt = HA.stage_b_rungs(rungs)
    tail = [f"not-built: {r} CONSTRUCTED: no key" for r in unbuilt]
    good = ["yield: zenodo=0/0", "not-asked: zenodo 12 CONSTRUCTED condition Z",
            "yield: figshare=0/0", "not-asked: figshare 0 CONSTRUCTED condition F",       # reached nobody
            "yield: europepmc=0/0", "not-asked: europepmc 3 another reason",               # not the registry's words
            "yield: hal=0/0", "not-asked: hal 3 CONSTRUCTED"]                              # an unconditional rung

    def detail(lines):
        p = tmp_path / "LITKB_LADDER1_CONSTRUCTED.md"
        p.write_text("\n".join(lines + tail) + "\n", encoding="utf-8")
        return HA.stage_b_unmeasured_detail({"repo": str(tmp_path), "report_path": str(p)}, rungs)

    assert detail(good) == ["figshare", "europepmc", "hal"]
    assert detail([ln for ln in good if not ln.startswith("not-asked: zenodo")]) == [
        "zenodo", "figshare", "europepmc", "hal"]
    assert detail(["yield: zenodo=0/35"] + good[2:]) == ["figshare", "europepmc", "hal"]   # asked: a yield line
    # S4.5 decision D32 condition 3: asked AND not-asked in one report is a contradiction -> unmeasured (integrator-w3)
    assert detail(["yield: zenodo=0/35"] + good[1:]) == ["zenodo", "figshare", "europepmc", "hal"]
    # D32 condition 1: a PARAPHRASE of the registry's condition answers nothing (the known-bad of the byte-equal rule)
    para = [ln.replace("CONSTRUCTED condition Z", "CONSTRUCTED Z condition") for ln in good]
    assert detail(para) == ["zenodo", "figshare", "europepmc", "hal"]
    assert HA.conditional_routes(rungs) == {"zenodo": "CONSTRUCTED condition Z", "figshare": "CONSTRUCTED condition F",
                                            "europepmc": "CONSTRUCTED condition E"}


def test_the_real_registry_s_conditional_rungs_are_builder_c2a_s():
    """The registry's own `ask_condition`s (builder C2a's stage_b.ASK_CONDITIONS) are what the counter reads."""
    from litkb.acquire import policy as P
    from litkb.acquire import stage_b as B

    assert HA.conditional_routes() == {r: c for r, c in B.ASK_CONDITIONS.items() if P.STAGE_OF.get(r) == "B"}
    assert {"zenodo", "figshare", "europepmc"} <= set(HA.conditional_routes())
