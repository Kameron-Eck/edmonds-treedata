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


# ── run tags and the per-arm tile directory ───────────────────────────────────
#
# These were hand-maintained TWINS: the sanitiser existed in cli.py and again in
# phase4_train_queue.py, and the tile-directory rule existed in common.py and again in
# the queue. Both pairs were in sync when audited, which is the trap — a twin is not
# dangerous while it agrees, it is dangerous at the moment someone edits one side.
#
# _pid_alive is the proof that the moment arrives: its two copies DID diverge, and the
# copy without the Windows guard would have called TerminateProcess instead of probing.
# That shipped, passed the suite, and was caught by an audit rather than by use.

def sanitize_tag(tag):
    """A run tag, reduced to characters safe in a filename. THE one implementation.

    Everything an arm writes is keyed on this — the tile directory, the checkpoint, the
    output raster, the status rows — so two implementations that disagree by one
    character would send the writer and the reader to different places, and the reader
    would find someone else's artifacts rather than nothing.
    """
    return "".join(c if (c.isalnum() or c in "._-") else "_"
                   for c in str(tag)).strip("_")


def tile_dir_name(label, tag):
    """Directory NAME for this arm's tiles: `{label}__{tag}`, or `{label}` untagged.

    Returns a NAME, not a path, so both planes can join it to their own root — the
    engine to TILE_DIR, the orchestrator to its own BASE. That is the only reason the
    twin existed: the two sides disagreed about the root, not about the rule.

    WHY TAGGED DIRECTORIES EXIST (measured 2026-08-28, and it corrupted a landed
    result): two arms on the same year running CONCURRENTLY both resolved to one
    directory, each judged the other's cache invalid, and both re-tiled into it. The
    2026-08-27 groves arms overlapped for 18 minutes and produced 635 vs 599 tiles, so
    their comparison was between two models trained on an unknown mixture of each
    other's labels.
    """
    t = sanitize_tag(tag) if tag else ""
    return f"{label}__{t}" if t else str(label)


def pid_alive(pid):
    """Is this pid running ON THIS HOST? POSIX only — and the guard is not cosmetic.

    On Windows `os.kill` does not probe: CPython maps it to TerminateProcess for every
    signal except CTRL_C_EVENT and CTRL_BREAK_EVENT, so `os.kill(pid, 0)` KILLS the
    process it was asked about. Returning True off-posix is the correct fallback for
    every current caller — they use this to decide whether a peer's claim on a run tag
    is stale, and "assume the peer is alive" preserves the protection rather than
    weakening it.
    """
    import os

    if os.name != "posix":
        return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                      # exists, owned by someone else
    except (OSError, ValueError, TypeError):
        return True                      # cannot tell — assume live
    return True


# ── the state vocabulary ──────────────────────────────────────────────────────
#
# THE BLIND SPOT THIS CLOSES. The queue writes ten states meaning "the artifact you
# just paid GPU hours for is broken". The watcher that oversight reads through watched
# a DIFFERENT eleven, and the campaign loop watched a third set of six. Lined up:
#
#   written by the queue but watched by NOBODY:
#       UNREADABLE      the probability raster cannot be opened
#       STALE_EVAL      evaluate exited 0 and left the previous run's numbers
#       SIZE_CHANGED    the artifact is not the one that passed verification
#
# All three are really written (phase4_train_queue writes each of them). So a run that
# died because its raster could not be opened produced `bad_jobs == []`, and
# runtime_health printed ALL_OK and exited 0. The oversight command was not merely
# incomplete — it was confidently wrong, which is worse than having no watcher.
#
# Two sets, because they are two different things and conflating them is how the
# watcher ended up with a set that was neither:
#   VERIFY_HARD_FAIL — a produced ARTIFACT is broken. Written by verify_step.
#   RUN_FAIL         — the STEP itself did not complete. Written by run_step.
# Oversight wants the union; the queue's own abort logic wants only the first.

VERIFY_HARD_FAIL = frozenset({
    "MISSING", "EMPTY", "MOSTLY_NODATA", "NO_CONFIDENCE", "BAD_CKPT",
    "NO_TILES", "BAD_INDEX", "UNREADABLE", "STALE_EVAL", "SIZE_CHANGED",
})

RUN_FAIL = frozenset({"FAIL", "ERROR", "TIMEOUT", "ABORTED", "INTERRUPTED"})

# What any oversight tool should treat as "this needs a human".
BAD_STATES = VERIFY_HARD_FAIL | RUN_FAIL

# NOT a failure: "the check could not answer". Distinct on purpose — a checker that
# threw is not evidence the artifact is bad, and treating it as one would throw away
# good GPU hours. It is also not a pass; the resume ledger keeps it flagged.
VERIFY_UNVERIFIED = frozenset({"UNCHECKED", "UNVERIFIED"})
