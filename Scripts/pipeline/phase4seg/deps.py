"""In-script dependency bootstrap — THE one implementation. Stdlib-only.

WHY THIS MODULE EXISTS. Twenty-two files each carried their own pip bootstrap: fourteen
byte-identical `_pip` copies (family A), one ASCII-only variant, two DIVERGENT ones that
must never merge (see below), and the engine's `_ensure_deps` pair (family C). None
imported any other — 22 definitions, zero reuse. The centralization survey diffed every
body before this was written; same name did not mean same behaviour.

FAMILY-C SEMANTICS WON, for one measured reason: after a successful install it calls
`importlib.invalidate_caches()`. Without it, a fresh-runtime install followed by
`import rasterio` in the same process can miss the new site-packages entry, because
FileFinder caches directory listings by mtime. Family A never did this and got away with
it only because the VM-level bootstrap pre-installs requirements-colab.txt before any
script runs — the in-script loops are belt-and-braces for the local/interactive plane.

THE TWO THAT MUST NOT FOLD ONTO THIS, recorded so nobody "finishes the job":
  · qc/phase4_qc_inventory.py / qc/phase4_ref_agreement.py (family B): guard INSIDE the
    function and `check=False` — they no-op when the package exists and degrade
    gracefully offline. Folding them here would shell out to pip on every run and turn a
    graceful degrade into a hard abort. Their import-name derivation is also wrong for
    scikit-learn→sklearn and pillow→PIL; do not port it.
  · pipeline/phase0_instance_seg.py: FROZEN pins (smp==0.3.4, timm==0.9.7), documented
    in requirements-colab.txt under "FROZEN LEGACY". Never load in a phase3/4 runtime.

DEP LISTS STAY PER-FILE. Nine distinct sets exist across the callers (a stack QC script
needs scipy; a label tool needs pillow); one shared list would over-install everywhere.
This module owns the MECHANISM, each caller declares its own needs.

Prints are ASCII-only on purpose: on a Windows cp1252 console without PYTHONUTF8, a
bullet glyph in this message raises UnicodeEncodeError — from the installer.
"""
import importlib
import subprocess
import sys


def pip_install(spec):
    """`pip install -q <spec>` via THIS interpreter, loud on failure (check=True)."""
    print(f"  * installing {spec} ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)


def ensure_deps(deps):
    """[(import_name, pip_spec), ...] -> import each, installing on ImportError.

    invalidate_caches() after each install is the load-bearing line — see the module
    docstring. The import name and the pip spec are SEPARATE arguments because deriving
    one from the other is exactly the bug family B carries (scikit_learn is not a module).
    """
    for import_name, pip_spec in deps:
        try:
            importlib.import_module(import_name)
        except ImportError:
            pip_install(pip_spec)
            importlib.invalidate_caches()
