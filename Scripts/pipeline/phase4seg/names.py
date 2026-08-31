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
# Match the writer's ACTUAL SHAPE instead. phase4_train_queue.py::main emits
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


def parse_status_name(name):
    """`(stem, ts)` for a status file, or None if it is not one.

    `ts` is the LAUNCH STAMP and is None for the two kinds of file that never
    represent a launch: the legacy shared `train_queue_status.csv` (stem "") and the
    hand-written `*_seed.csv` files. That distinction is load-bearing for cost
    accounting — a seed row records a step that was declared already-done, so it
    burned no GPU, and counting it would inflate the bill for work nobody paid for.

    IT IS ALSO THE RIGHT FILTER TO SELECT LAUNCHES BY, and cost_report.py used a
    different one: it globbed `train_queue_status_queue_*_2*.csv`. That requires the
    `_queue_` infix — the naming coincidence this module's header records rejecting,
    because a queue file may be named anything. `pilot_2019.yaml`, which Stage 5 of
    the overhaul builds, writes `train_queue_status_pilot_2019_{ts}.csv` and would
    have been globbed out: its runs would burn A100 hours and appear in no cost
    report, with nothing raised. Discovery goes through status_files(); whether a
    file is a LAUNCH is then `ts is not None`, which is a fact about the file rather
    than a guess about its name.
    """
    if not is_status_file(name):
        return None
    stem = Path(name).name[len(STATUS_STEM):-len(".csv")].lstrip("_")
    m = re.search(r"_([0-9]{8}T[0-9]{6}Z)$", stem)
    if not m:
        return (stem, None)
    return (stem[:m.start()], m.group(1))


# ── the row key ───────────────────────────────────────────────────────────────

def job_key(job_id, year, tag, step):
    """The identity a ledger row has: (job, year, tag, step). THE one implementation.

    D8 (2026-08-29) fixed the queue's resume key from (job, step) to this, because a
    job id is a short hand-written NICKNAME reused across queue files — `2019` appears
    in three, `2024` in three — and nothing makes an id mean the same year or the same
    tag twice. A resume keyed on the nickname skips a step that never ran for THIS
    year and tag, and the job proceeds on another run's artifacts.

    The queue was fixed; two READERS were not, and kept the old 2-tuple:
        cost_report.harvest_launch    within one launch file
        runtime_dashboard.latest_by_key  across every launch of one queue stem
    Both collapse rows that differ only in year or tag, so one run's outcome silently
    replaces another's in the cost table and on the dashboard.

    HONESTLY, AND THE SCOPE IS NARROWER THAN D8's: both readers key inside a single
    queue's files, so a collision needs one yaml to reuse an id across two (year, tag)
    pairs — not merely across queue files. Nothing forbids that, and no run has done
    it. Latent, fixed because nothing prevents it, exactly as D8's own note put it.

    Both sides go through str() so the CSV's text and the YAML's values (a `tag: 2020`
    parses as an int) cannot disagree about what the same job is.
    """
    return (str(job_id), str(year), str(tag), str(step))


# ── finding a symbol's source without importing the engine ────────────────────
#
# WHY THIS IS HERE AND NOT `inspect.getsource`. Several gates assert something about the
# engine's TEXT — that step_evaluate still stamps run_tag, that the Dataset gates the
# distance field on the weight, that the training path never mentions crowns. Those are
# claims about the engine, not about a file, but every one of them was written as
#
#     (SCRIPTS / "pipeline" / "phase4seg" / "core.py").read_text()
#
# core.py is 2,833 lines and is scheduled to be split. Every such gate would then pass
# vacuously or fail spuriously depending on which half the symbol landed in — a gate
# that silently stops checking is the failure this repo keeps finding.
#
# inspect.getsource would follow the symbol, but importing the engine pulls torch, and
# these gates run in CI where torch is deliberately absent. So: locate by parsing, not
# by importing. Same reason names.py is stdlib-only in the first place.

def engine_files(pkg_dir):
    return sorted(p for p in Path(pkg_dir).glob("*.py") if p.name != "__init__.py")


class AmbiguousSymbol(LookupError):
    """More than one engine module defines this name and nothing narrowed it.

    Returning the first match would be a silent wrong answer, which is the whole class
    of defect these locators exist to prevent: a gate that quietly starts checking a
    different thing reads exactly like a gate that passes.
    """


def _matches(pkg_dir, name, kind=None, within=None):
    import ast

    hits = []
    for p in engine_files(pkg_dir):
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        roots = [tree]
        if within:
            roots = [n for n in ast.walk(tree)
                     if isinstance(n, ast.ClassDef) and n.name == within]
        for root in roots:
            for node in ast.walk(root):
                if not isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                         ast.AsyncFunctionDef)):
                    continue
                if node.name != name:
                    continue
                if kind == "class" and not isinstance(node, ast.ClassDef):
                    continue
                if kind == "function" and isinstance(node, ast.ClassDef):
                    continue
                hits.append((p, src, node))
    if len({h[0] for h in hits}) > 1:
        raise AmbiguousSymbol(
            f"{name!r} is defined in {sorted({h[0].name for h in hits})} — pass `within` "
            f"to name the class, or a more specific `kind`. Taking the first would be a "
            f"silent wrong answer.")
    return hits


def find_symbol_source(pkg_dir, name, kind=None):
    """`(path, source_text)` for `name` in `pkg_dir`, or None if it is not there.

    Returns the WHOLE module's text, because callers want to search around the symbol as
    often as inside it; use `symbol_body` when the segment itself is what matters.
    Raises AmbiguousSymbol rather than guessing.
    """
    hits = _matches(pkg_dir, name, kind)
    return (hits[0][0], hits[0][1]) if hits else None


def symbol_body(pkg_dir, name, kind=None, within=None):
    """Source text of `name` itself. `within` scopes the search to a class's body, which
    is how `__getitem__` is found without matching every other class's."""
    import ast

    hits = _matches(pkg_dir, name, kind, within)
    if not hits:
        return None
    _p, src, node = hits[0]
    return ast.get_source_segment(src, node)


def status_out_name(stem, launch_ts):
    """The status file THIS launch writes: the one formatter, paired with the parser.

    phase4_train_queue built this f-string by hand while names.py owned the parser, so the
    two could drift and nothing would notice — no test constructed a name through the
    writer. Round-trip is now gated: parse_status_name(status_out_name(s, ts)) == (s, ts).
    """
    return f"{STATUS_STEM}_{stem}_{launch_ts}.csv"


def status_files_for_stem(qc_dir, stem):
    """This queue's status files — its launches AND its seed, and nothing else.

    THE TRAP THIS EXISTS TO AVOID, measured against the real lake on 2026-08-31. Callers
    globbed `train_queue_status_{stem}_*.csv`, which is PREFIX matching: 23 of the 77 files
    are matched by some other queue's stem. Twenty-two of those are that queue's own
    `_seed` file and are wanted — `sector_campaign_loop` writes a 24-row seed whose whole
    job is to stop the queue re-running finished base-year fine-tunes, so dropping it makes
    completed work look un-run. Exactly ONE is a genuine cross-queue collision:

        queue_noise_2021s   also matches   queue_noise_2021s_b   (a different 4-job queue)

    So neither the naive glob nor naive stem-equality is right. Equality against `stem` OR
    `stem + "_seed"` keeps all 22 and rejects the one.
    """
    want = (str(stem), f"{stem}_seed")
    out = []
    for p in status_files(qc_dir):
        parsed = parse_status_name(p.name)
        if parsed and parsed[0] in want:
            out.append(p)
    return sorted(out)


def nir_years(year_catalog):
    """{label: entry} for every NIR-bearing acquisition. DERIVED, never restated.

    WHY THIS EXISTS, measured 2026-08-31. Four live files each restated this catalog as a
    literal dict, and all four had drifted to filenames that lost their resolution token:

        catalog (authoritative)        restated in 4 files
        2016_snoh_1ft_rgbi.tif    ->   2016_snoh_rgbi.tif
        2019_naip_60cm_rgbi.tif   ->   2019_naip_rgbi.tif
        2021_snoh_6in_rgbi.tif    ->   2021_snoh_rgbi.tif
        2023_naip_60cm_rgbi.tif   ->   2023_naip_rgbi.tif

    BOTH NAMES EXIST ON DISK, so every `.exists()` check passed and nothing ever raised.
    The stale files are DIFFERENT PRODUCTS covering less ground — 34.49 km2 against the
    authoritative 87.11 for 2016 and 2021s (39.6%), 53.79 against 80.31 for the NAIP years
    (67.0%). `phase4_build_corrected_labels.py` is a LABEL PRODUCER, and
    canopy_additions_2016.lineage.json records `imagery: ...\2016_snoh_rgbi.tif` — that
    overlay was built from under 40% of the city. The lineage system caught it perfectly;
    nobody read the lineage.

    Nothing consumed that overlay (0 registry rows, 0 queue files, 0 run manifests), so no
    landed result is affected — but the four dicts also held only 4 of the catalog's 10
    NIR-bearing acquisitions, and MACHINERY_AUDIT_2026-08.md's sanctioned next action was
    to hand-add the missing six to dicts whose existing four were wrong.

    Deriving fixes the instance AND the class: this cannot drift, and it grows on its own
    when the catalog does. Pass `config.YEAR_CATALOG` in rather than importing config here,
    so this module stays stdlib-only and importable from both planes.
    """
    return {str(e["label"]): e for e in year_catalog if int(e.get("bands", 0)) >= 4}


def clean_argv(argv=None):
    """sys.argv[1:] with Colab's injected `-f <kernel>.json` removed — THE one filter.

    Jupyter/Colab launches kernels with `-f /path/kernel-xxxx.json` appended, so every
    script that argparses under `%run` must strip it. Three implementations existed and
    two were wrong in ways only a real Colab exec ever exercises:

      the 100-file one-liner    [a for a in argv if not (a == "-f" or a.endswith(".json"))]
                                drops ANY .json value: `--aoi sectors_v1.json` loses its
                                value and argparse dies loudly ("expected one argument")…
                                but `--aoi=sectors_v1.json` is dropped WHOLE and the flag
                                silently falls back to its default. No error, wrong AOI.
      cli.py's pair filter +    the extra "bare .json with no owning flag" clause ate the
      positional guard          equals form the same way. Guards a case never observed.
      runtime_health's          the PAIR filter: drop `-f` and drop a .json token only
      pair filter (this one)    when the PREVIOUS token was `-f`. Correct on all four
                                measured cases: space form, equals form, bare kernel
                                json, and no injection at all.

    Deliberately does NOT try to detect kernel jsons positionally — `-f` pairing is the
    contract Colab actually uses, and every cleverer guess broke a legitimate argument.
    """
    import sys as _sys

    if argv is None:
        argv = _sys.argv[1:]
    keep, prev = [], ""
    for a in argv:
        if a == "-f" or (prev == "-f" and a.endswith(".json")):
            prev = a
            continue
        keep.append(a)
        prev = a
    return keep
