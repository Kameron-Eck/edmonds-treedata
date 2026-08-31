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
