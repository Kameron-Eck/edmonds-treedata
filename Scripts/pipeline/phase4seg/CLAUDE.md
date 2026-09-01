# phase4seg/ — engine rules (load-bearing; the root CLAUDE.md is the full rulebook)

- **`config.py` is APPEND-ONLY.** Constants feed `_tile_signature`; comments carry
  experimental history. Never reformat, reorder, or "fix" its stale path comments.
- **Masks are three-state**: 0 background / 1 canopy / 255 IGNORE. Every loss term must
  be IGNORE-aware or it silently trains on 255. Corrected overlays are ADD-ONLY.
- **Native resolution only** — no upscaling anywhere in the segmentation path.
- **torch is LAZY.** No module-level `import torch` outside the sanctioned pattern;
  function-local imports (see `losses.py`, `sdm_for_mask`) — hoisting them fails tests.
- **`names.py` is stdlib-only** (orchestrators import it on machines with no engine env).
- **Colab-only runtime.** Locally validate with `py -3.12 qc/check.py` (preflight+smoke
  rungs); never try to train here.
- `core.py` split policy: move clusters out with a facade re-export in `core` so call
  sites and test monkeypatches keep working (`losses.py` is the precedent).
