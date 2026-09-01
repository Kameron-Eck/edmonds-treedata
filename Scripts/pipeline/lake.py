r"""The data lake's paths — THE one home. Stdlib-only, importable from both planes.

WHY. Before this module, ~70 files each spelled the lake root themselves, in three probe
forms. The dominant one was subtly wrong:

    BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE          # 36 files
    BASE = _COLAB_BASE if (_COLAB_BASE / "Full_Image").exists() else …  #  3 files  << CORRECT

The bare `.exists()` is true whenever the mount POINT exists — including when Drive is
attached but the treedata share is not actually mounted under it, at which point every
path resolves, every read finds nothing, and the caller concludes the lake is empty
rather than unreachable. The strict probe checks for a directory only a real mount has.
The minority was right; this module standardises on it. (config.py keeps its own
hardcoded Colab BASE — the engine is Colab-only by design and config.py is append-only.)

MOUNT-PREFIX STRINGS STAY STRING LITERALS. `DRIVE_MOUNT_PREFIX` feeds `startswith()`
guards in common.py, core.py and phase4_train_queue. `str(Path(...))` would yield
backslashes on Windows and break every one of them, and the trailing slash is
load-bearing. Do not "clean this up" into a Path.

WHO MUST NOT IMPORT THIS, recorded so the next sweep doesn't "fix" them:
  · vm_heartbeat.py / gen_vm_bootstrap.py and every generated VM code string — the beacon
    and bootstrap must run before/without the repo's import machinery. Deliberate twins,
    gated for equivalence where it matters.
  · Colab-only scripts that hardcode /content/... on purpose (they SHOULD crash loudly
    off-plane rather than silently read G: on a Windows box), and local-only tools that
    pin G:\ or the D: mirror for the same reason in reverse. Divergence by design is not
    duplication.
"""
from pathlib import Path

COLAB_BASE = Path("/content/drive/MyDrive/treedata")
LOCAL_BASE = Path(r"G:\My Drive\treedata")

# The strict probe — see module docstring for why `.exists()` on the bare root is wrong.
BASE = COLAB_BASE if (COLAB_BASE / "Full_Image").exists() else LOCAL_BASE

QC_DIR      = BASE / "phase4" / "qc"
LOGS_DIR    = BASE / "phase4" / "logs"
MASKS_DIR   = BASE / "phase4" / "masks"
MODELS_DIR  = BASE / "phase4" / "models"
EVAL_DIR    = BASE / "phase4" / "eval"
LABELS_DIR  = BASE / "phase4" / "labels_corrected"
RUNS_DIR    = BASE / "phase4" / "runs"
TILES_DIR   = BASE / "phase4" / "tiles"
IMAGERY_DIR = BASE / "Full_Image" / "Pipeline Imagery"

# String, not Path — feeds startswith() guards; slash direction and the trailing
# separator are load-bearing (see docstring).
DRIVE_MOUNT_PREFIX = "/content/drive/MyDrive/treedata/"


def read_retry(fn, tries=10, pause=1.0):
    """Run `fn` until it returns something non-empty, or give up (then return the
    last attempt so the caller sees the real emptiness, not None).

    THE MIRROR BLINKS — on both planes. Locally, Drive for Desktop streams G: and a
    read or a directory LISTING can come back empty for files plainly there seconds
    later (measured 2026-08-31; it nearly had a healthy runtime declared dead, and
    pilot_gate printed "no ledger rows" for an arm that had eleven). On the VM the
    FUSE mount has the same failure shape. Retry the ANSWER — the listing or the
    parsed rows — never a timestamp guess. This is the ONE home for that rule;
    pilot_gate carried the original and now delegates here.
    """
    import time
    for _ in range(tries):
        out = fn()
        if out:
            return out
        time.sleep(pause)
    return fn()
