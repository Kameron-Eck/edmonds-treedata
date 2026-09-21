"""The settings a litkb run may be told to change, and their defaults — the FIRST such home.

WHAT THIS IS NOT. It is not a migration of litkb's environment reads. There are sixteen of them at
module scope across thirteen files (`LITKB_DB`, `LITKB_LITERATURE_ROOT`, `LITKB_WORKTREE`,
`LITKB_PGHOST`, …), each read where the thing it configures is defined, and moving them here would
make every one of those modules import this one for a value it already owns. What belongs here is
the setting whose HOME is genuinely nowhere else: a value a route hardcodes, that an operator has a
reason to change, and that no module can claim as its own fact.

Today that is one list: the Sci-Hub mirrors. `litkb.acquire.scihub` hardcoded two of the four Kam's
operating note names (memory `scihub-fetch-method`, 2026-09-12), and `litkb.acquire.run` called the
route without passing `mirrors=` at all — so the caller that decides the route order could not
decide the mirror order, and a mirror that went dark could only be replaced by editing the module.

EMPTY IS NOT A CHOICE. `LITKB_SCIHUB_MIRRORS=""` — an operator clearing the variable, a launcher
exporting it unset, a CI job that sets every LITKB_* to the empty string — yields the DEFAULT, not
an empty tuple. An empty mirror list is not "try no mirrors": it is a Sci-Hub route that iterates
zero times and answers `not-in-archive` for every DOI, which reads in `acquisition_attempts` as
"Sci-Hub does not hold it" for a work nobody asked Sci-Hub about.
"""
import os

#: The four mirrors Kam's operating note names, in the order the route tries them
#: (memory `scihub-fetch-method`). `LITKB_SCIHUB_MIRRORS` overrides: comma-separated, whitespace
#: around each entry stripped, blank entries dropped. An override that leaves nothing behind is
#: the default (see the module docstring).
SCIHUB_MIRRORS_DEFAULT = ("https://sci-hub.ru", "https://sci-hub.ren",
                          "https://sci-hub.box", "https://sci-hub.wf")


def scihub_mirrors(env=None):
    """-> the mirror tuple this process should try, in order. Read once at import into
    :data:`SCIHUB_MIRRORS`; callable so a test can pass its own mapping instead of mutating
    `os.environ` for the length of a process."""
    raw = (env if env is not None else os.environ).get("LITKB_SCIHUB_MIRRORS") or ""
    # BEGIN guard: an empty or blank mirror override is the default, never an empty loop
    chosen = tuple(m.strip() for m in raw.split(",") if m.strip())
    return chosen or SCIHUB_MIRRORS_DEFAULT
    # END guard: an empty or blank mirror override is the default, never an empty loop


SCIHUB_MIRRORS = scihub_mirrors()
