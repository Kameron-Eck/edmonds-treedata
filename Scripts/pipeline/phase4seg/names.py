"""Artifact naming and discovery — the ONE home, importable from BOTH planes.

WHY THIS MODULE EXISTS. The orchestrator (phase4_train_queue.py) deliberately imports
no engine module, because it must keep running when the engine's environment is broken:
importing common.py would pull geopandas, rasterio, shapely, fiona and sklearn into the
process whose whole job is to survive them. That constraint is real and stays.

But it was over-generalised into "the queue cannot import phase4seg at all", and that is
measurably false: `import phase4seg; from phase4seg import config` pulls 29 modules and
ZERO of {torch, rasterio, geopandas, shapely, sklearn, numpy, pandas, fiona}. The heavy
imports live in common.py, not in the package. So naming logic CAN have one home, and the
hand-maintained twins it produced were not free — `_pid_alive` drifted into a copy that
could TerminateProcess on Windows (fixed 2026-08-30, but only after it shipped).

THIS MODULE IMPORTS STDLIB ONLY. Keep it that way; that property is what lets both planes
use it.
"""
import re
from pathlib import Path

# ── the status ledger ─────────────────────────────────────────────────────────
#
# Queue launches each write their own file so concurrent queues cannot clobber each
# other, and every reader merges them. The merge pattern used to be the single glob
# `train_queue_status*.csv`, which is too permissive in a way that bit on 2026-08-29:
# a test-contaminated file was "quarantined" by renaming it to
#
#     train_queue_status.CONTAMINATED-BY-TEST-20260829.csv
#
# That escapes `train_queue_status_*.csv` (underscore) but NOT `train_queue_status*.csv`
# (no underscore) — the pattern the readers actually use. So the rename quarantined
# nothing and five readers kept ingesting a synthetic row. A rename is not a quarantine
# unless the discovery rule agrees.
#
# THE RULE IS STRUCTURAL, NOT LEXICAL — and the first attempt got this wrong in a way
# worth recording. It used a deny-list of words a human might rename a file to
# ("contaminated", "corrupt", "old", "bad", …) matched as substrings. Run against the
# real directory it excluded TEN files, of which only ONE was the contaminated fixture:
#
#     train_queue_status_queue_corrupt10/25/50_*.csv   ← the DAMAGE CURVE experiment,
#                                                        "corrupt" is the queue's name
#     train_queue_status_queue_golden_v2_*.csv         ← "golden" contains "old"
#
# Nine legitimate campaigns would have vanished from the ledger — the exact harm the
# filter existed to prevent, caused by the filter. Short words are substrings of real
# names, so a lexical deny-list cannot be made safe by lengthening it.
#
# Match the writer's ACTUAL SHAPE instead. phase4_train_queue.py:1489 emits
#     STATUS_OUT = QC_DIR / f"train_queue_status_{stem}_{launch_ts}.csv"
# where {stem} is the QUEUE FILE's stem — plus the legacy shared `train_queue_status.csv`.
# So the separator after the stem is an UNDERSCORE, always.
#
# A SECOND WRONG TURN, also worth recording, because the tests caught it: the fix after
# the word-list was `_queue_[…]` — requiring that infix. Every existing status file has
# it, so it looked right. But the infix comes from every queue file happening to be
# named `queue_*.yaml`; it is a naming coincidence, not a property of the writer. A
# pilot queue named `pilot_2019.yaml` — precisely what the overhaul's Stage 5 builds —
# would have been silently excluded. Six existing tests using `train_queue_status_a.csv`
# failed and were right to.
#
# The discriminator is the SEPARATOR, not the content: real files use `_`, and a human
# renaming one aside appends with `.` (`train_queue_status.CONTAMINATED-BY-TEST-….csv`).
# That distinction is structural and needs no vocabulary.
STATUS_STEM = "train_queue_status"

_VALID = re.compile(rf"^{STATUS_STEM}(_[A-Za-z0-9._-]+)?\.csv$")


def is_status_file(path):
    """Should this file be merged into the run-outcome ledger?

    Shape-based on purpose (see above). Excluding a real file costs one launch's rows;
    including a fake one corrupts every number derived from the ledger — and
    registry_from_manifests would then join it into run_registry.csv permanently.

    Quarantining is done by MOVING a file out of the directory, not by renaming it.
    That is the lesson of 2026-08-29: a rename is not a quarantine unless the discovery
    rule agrees, and a discovery rule that tries to guess human rename vocabulary
    silently eats real data.
    """
    return bool(_VALID.match(Path(path).name))


def status_files(qc_dir):
    """Every admissible status CSV under `qc_dir`, sorted. The one discovery rule.

    Replaces `sorted(qc_dir.glob("train_queue_status*.csv"))` at all five reader sites.
    """
    return sorted(p for p in Path(qc_dir).glob(f"{STATUS_STEM}*.csv")
                  if is_status_file(p))
