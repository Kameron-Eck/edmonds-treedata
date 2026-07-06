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
"""

import datetime
import io
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path


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
    """

    def __init__(self, script: str, step: str, logs_dir: Path,
                 capture_stdout: bool = True):
        self.script = script
        self.step   = step
        self.logs_dir = Path(logs_dir)
        self.capture_stdout = capture_stdout

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

        lines = [
            f"=== {self.script} --step {self.step} ===",
            f"started:   {self._t0.isoformat() if self._t0 else 'unknown'}",
            f"completed: {t1.isoformat()}",
            f"elapsed:   {elapsed_str}",
            f"errors:    {errors if errors else 'none'}",
        ]

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
                   notes: str = "", **fields):
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
    logger = StepLogger(script, step, logs_dir, capture_stdout=False)
    logger._t0 = datetime.datetime.now()
    logger._write(datetime.datetime.now(), 0.0, errors, notes, fields, stdout_text)
