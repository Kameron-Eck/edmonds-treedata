"""litkb extraction stages 0-4 (design Scripts/LITERATURE_KB_DESIGN_2026-09-13.md §7).

Each adapter maps ONE tool's output into the canonical §7.1 frame and block model. No
adapter may import its heavy tool at module scope: the project's own environment
(``py -3.12``, the ladder, ``qc/check.py``) must import these modules with nothing but the
standard library and pypdfium2 installed (design referee M9). Heavy tools run in their own
virtual environment, as a subprocess, behind a worker module.
"""
