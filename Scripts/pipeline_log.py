"""
pipeline_log.py — Step log writer for the Edmonds pipeline
===========================================================
Imported by every phase script. Call write_step_log() at the end of each
--step to write a structured log to Drive. Claude Code reads these logs
after Colab runs a step — you should not need to paste terminal output.

LOG LOCATION:
    treedata/Scripts/logs/{script}_{step}_{YYYY-MM-DDTHH-MM}.log

USAGE (inside a phase script):
    from pipeline_log import StepLogger

    # At the start of a step:
    logger = StepLogger(script="phase4_label_review", step="prep",
                        logs_dir=BASE / "Scripts" / "logs")
    logger.start()

    # ... do work, print normally ...

    # At the end of the step:
    logger.finish(
        sites=["Forest_1", "Forest_2"],
        crowns=14476,
        manifest_mb=25.1,
        errors=0,
        notes="",          # optional free-form
    )

StepLogger captures stdout during the step so the log includes the full
printed output without requiring the caller to redirect anything manually.

MINIMAL USAGE (no stdout capture, just structured fields):
    logger = StepLogger("phase4_label_review", "prep", logs_dir)
    logger.start()
    # ... work ...
    logger.finish(crowns=14476)

The log is always attempted; failures are printed but never raise so they
cannot crash a running pipeline step.

WHICH CODE PRODUCED THIS LOG
    Every log header carries three provenance lines, resolved automatically —
    callers need to pass nothing:

        version:   v048                      (curated version string, if any)
        code sha:  3f9a1c2e  (8 files)       (SHA-1 of the actual source that ran)
        command:   --year 2016 --step train  (argv, Colab's -f <json> filtered out)

    `version` is looked up in order: an explicit version= argument > the script's
    (or its package's) __version__ > the first \bvNNN\b marker in the file header
    > "unset". `code sha` is a content hash over the script plus any same-named
    package directory beside it (e.g. phase4_semantic_finetune.py + phase4seg/),
    so two runs that report the same sha ran byte-identical code even when nobody
    remembered to bump a version string. That pair is what makes a run_registry.csv
    row reconstructable from logs/ alone — see CLAUDE.md rule 9.

    Resolution never raises: any failure degrades to "unknown" and the step runs on.
"""

import datetime
import hashlib
import io
import re
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path


# ── provenance: which code actually ran ───────────────────────────────────────

_VERSION_RE = re.compile(r"\bv(\d{3})\b")
_PROV_CACHE: dict = {}


def _script_sources(script: str, logs_dir: Path):
    """
    Locate the source that implements `script`: the .py file itself, plus a
    same-named package directory beside it if one exists (the phase4seg/ split
    means the shim's own bytes say nothing about what ran).

    Looks in the Scripts/ dir (logs_dir's parent) first, then beside __main__.
    """
    cands = []
    scripts_dir = Path(logs_dir).parent
    cands.append(scripts_dir / f"{script}.py")
    main_file = getattr(sys.modules.get("__main__"), "__file__", None)
    if main_file:
        cands.append(Path(main_file).resolve())

    for f in cands:
        try:
            if not f.is_file():
                continue
        except OSError:
            continue
        files = [f]
        # phase4_semantic_finetune.py -> phase4seg/ ; also <stem>/ verbatim.
        for pkg_name in {script.split("_")[0] + "seg", script}:
            pkg = f.parent / pkg_name
            try:
                if pkg.is_dir():
                    files += sorted(q for q in pkg.glob("*.py"))
            except OSError:
                pass
        return files
    return []


def _resolve_provenance(script: str, logs_dir: Path, version=None) -> dict:
    """Best-effort {version, sha, n_files}. Never raises."""
    key = (script, str(logs_dir), version)
    if key in _PROV_CACHE:
        return _PROV_CACHE[key]

    out = {"version": version or None, "sha": None, "n_files": 0}
    try:
        files = _script_sources(script, logs_dir)
        out["n_files"] = len(files)

        if files:
            h = hashlib.sha1()
            for f in files:
                h.update(f.name.encode("utf-8"))
                h.update(f.read_bytes())
            out["sha"] = h.hexdigest()[:8]

        if out["version"] is None:
            # a declared __version__ beats a parsed marker
            for mod in (sys.modules.get(script), sys.modules.get("__main__")):
                v = getattr(mod, "__version__", None)
                if isinstance(v, str) and v.strip():
                    out["version"] = v.strip()
                    break
        if out["version"] is None:
            for f in files:
                init = f.parent / "__init__.py"
                for src in (f, init if init != f and init.is_file() else None):
                    if src is None:
                        continue
                    head = src.read_text(encoding="utf-8", errors="replace")[:4096]
                    m = re.search(r"__version__\s*=\s*[\"\']([^\"\']+)", head)
                    if m:
                        out["version"] = m.group(1)
                        break
                    m = _VERSION_RE.search(head)
                    if m:
                        out["version"] = "v" + m.group(1)
                        break
                if out["version"]:
                    break
    except Exception:  # noqa: BLE001 — provenance must never break a run
        pass

    _PROV_CACHE[key] = out
    return out


def _command_line() -> str:
    """argv as run, with Colab's injected `-f <kernel>.json` pair removed."""
    try:
        argv = list(sys.argv[1:])
        kept = [a for a in argv if not (a == "-f" or a.endswith(".json"))]
        return " ".join(kept)
    except Exception:  # noqa: BLE001
        return ""


# ── StepLogger ────────────────────────────────────────────────────────────────

class StepLogger:
    """
    Records a structured step log to Drive.

    Parameters
    ----------
    script : str
        Script stem, e.g. "phase4_label_review".
    step : str
        Step name, e.g. "prep", "train", "compile".
    logs_dir : Path
        Drive path to the logs/ directory, e.g. BASE / "Scripts" / "logs".
    capture_stdout : bool
        If True, tee stdout to an in-memory buffer so the full printed
        output is included in the log. Default True.
    version : str | None
        Explicit version string for the header. Leave None (the normal case)
        and it is resolved from the source that ran — see the module
        docstring, "WHICH CODE PRODUCED THIS LOG".
    """

    def __init__(self, script: str, step: str, logs_dir: Path,
                 capture_stdout: bool = True, version: str | None = None):
        self.script = script
        self.step   = step
        self.logs_dir = Path(logs_dir)
        self.capture_stdout = capture_stdout
        self.version = version      # None -> resolved from the source at write time

        self._t0: datetime.datetime | None = None
        self._buf: io.StringIO | None = None
        self._tee: "_Tee | None" = None
        self._finished = False   # guard: finish() must write exactly once

    # ── context manager (optional) ────────────────────────────────────────────
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            tb_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            self.finish(errors=1, notes=f"EXCEPTION:\n{tb_str}")
        else:
            self.finish()
        return False   # do not suppress exceptions

    # ── public API ────────────────────────────────────────────────────────────
    def start(self):
        """Call at the beginning of the step."""
        self._t0 = datetime.datetime.now()
        if self.capture_stdout:
            self._buf = io.StringIO()
            self._tee = _Tee(sys.stdout, self._buf)
            sys.stdout = self._tee

    def finish(self, errors: int = 0, notes: str = "", **fields):
        """
        Call at the end of the step.

        Parameters
        ----------
        errors : int
            Number of non-fatal errors encountered (0 = clean).
        notes : str
            Free-form text appended after the structured block.
        **fields : any
            Arbitrary key=value pairs written to the structured block.
            Common keys: crowns, sites, tiles, epochs, iou, elapsed_s,
            manifest_mb, output_path.
        """
        # Idempotency guard: when StepLogger is used as a context manager the
        # caller typically invokes finish(**fields) inside the block, and then
        # __exit__ calls finish() again. Without this guard the second (bare)
        # call would rewrite the same minute-stamped log file with no fields
        # and no captured stdout, clobbering the rich log. Write exactly once.
        if self._finished:
            return
        self._finished = True

        t1 = datetime.datetime.now()
        elapsed = (t1 - self._t0).total_seconds() if self._t0 else 0.0

        # Restore stdout before writing (so any print errors are visible)
        stdout_capture = ""
        if self._tee is not None:
            sys.stdout = self._tee.original
            stdout_capture = self._buf.getvalue()
            self._tee = None
            self._buf = None

        try:
            self._write(t1, elapsed, errors, notes, fields, stdout_capture)
        except Exception as e:
            print(f"  ⚠ pipeline_log: failed to write log — {e}", flush=True)

    # ── internals ─────────────────────────────────────────────────────────────
    def _log_path(self, t1: datetime.datetime) -> Path:
        ts = t1.strftime("%Y-%m-%dT%H-%M")
        return self.logs_dir / f"{self.script}_{self.step}_{ts}.log"

    def _write(self, t1, elapsed, errors, notes, fields, stdout_capture):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_path(t1)

        # Format elapsed nicely
        if elapsed < 60:
            elapsed_str = f"{elapsed:.1f}s"
        elif elapsed < 3600:
            elapsed_str = f"{elapsed/60:.1f}min"
        else:
            elapsed_str = f"{elapsed/3600:.2f}h"

        prov = _resolve_provenance(self.script, self.logs_dir, self.version)
        sha_str = (f"{prov['sha']}  ({prov['n_files']} file"
                   f"{'' if prov['n_files'] == 1 else 's'})") if prov["sha"] else "unknown"
        cmd = _command_line()

        lines = [
            f"=== {self.script} --step {self.step} ===",
            f"started:   {self._t0.isoformat() if self._t0 else 'unknown'}",
            f"completed: {t1.isoformat()}",
            f"elapsed:   {elapsed_str}",
            f"errors:    {errors if errors else 'none'}",
            f"version:   {prov['version'] or 'unset'}",
            f"code sha:  {sha_str}",
        ]
        if cmd:
            lines.append(f"command:   {cmd}")

        # Structured fields
        for k, v in fields.items():
            key = k.replace("_", " ")
            if isinstance(v, (list, tuple)):
                v_str = "  ".join(str(x) for x in v)
            elif isinstance(v, float):
                v_str = f"{v:.4g}"
            else:
                v_str = str(v)
            lines.append(f"{key:<11}{v_str}")

        if notes:
            lines.append("")
            lines.append("--- notes ---")
            lines.append(notes.strip())

        if stdout_capture:
            lines.append("")
            lines.append("--- stdout ---")
            lines.append(stdout_capture.rstrip())

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  ✓ log → {path}", flush=True)


# ── _Tee: write to two streams simultaneously ─────────────────────────────────

class _Tee:
    """Proxy that writes to both the original stdout and a buffer."""

    def __init__(self, original, buffer: io.StringIO):
        self.original = original
        self.buffer   = buffer

    def write(self, data):
        self.original.write(data)
        self.buffer.write(data)
        return len(data)

    def flush(self):
        self.original.flush()

    # Forward everything else (isatty, fileno, etc.) to original
    def __getattr__(self, name):
        return getattr(self.original, name)


# ── convenience: write_step_log() ─────────────────────────────────────────────

def write_step_log(script: str, step: str, logs_dir: Path,
                   stdout_text: str = "", errors: int = 0,
                   notes: str = "", version: str | None = None, **fields):
    """
    One-shot log writer — use when you are not using StepLogger as a
    context manager and have already collected the output text yourself.

    Example
    -------
    write_step_log(
        script="phase4_label_review", step="compile",
        logs_dir=BASE / "Scripts" / "logs",
        crowns=14476, sites=["Forest_1", "Forest_2"], errors=0,
    )
    """
    logger = StepLogger(script, step, logs_dir, capture_stdout=False,
                        version=version)
    logger._t0 = datetime.datetime.now()
    logger._write(datetime.datetime.now(), 0.0, errors, notes, fields, stdout_text)
