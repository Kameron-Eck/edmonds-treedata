"""overrides.py — per-run config overlays for R&D, with the re-tile guard.

Trying a variation on a constant that has no CLI flag used to mean: append a
constant AND a flag. Now: put `KEY: value` lines in a YAML file and run with
`--overrides file.yaml`. Applied to `config` BEFORE the argparse parser is built
(cli.py pre-scan), so flag defaults pick them up and an explicit flag still wins.
Recorded verbatim in the run manifest — a run whose config cannot be reconstructed
is not comparable to anything.

THE GUARD: constants that feed tiling._tile_signature change which tile cache a run
reads; overriding one silently would either force a surprise ~20 min/year re-tile
or — worse — read another arm's tiles. The signature set is DERIVED from
_tile_signature's own source at call time (derive-don't-restate), and overriding a
member requires --force-retile-overrides, stating the cost.

Stdlib + yaml only; torch never enters here.
"""
from __future__ import annotations

import ast
from pathlib import Path

from phase4seg import config


def signature_constants():
    """UPPERCASE config names read inside tiling._tile_signature — derived from its
    AST every call, so a constant added to the signature is guarded the same day."""
    src = (Path(__file__).resolve().parent / "tiling.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_tile_signature")
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id.isupper() and hasattr(config, node.id):
            names.add(node.id)
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "config" and node.attr.isupper()):
            names.add(node.attr)
    return names


def apply_overrides(path, force_retile=False):
    """Load a flat YAML mapping and set each entry on config. Refuses: unknown keys
    (typo guard), type-incompatible values, and tile-signature members without
    force_retile. Returns the applied dict; also stored as config.OVERRIDES_APPLIED
    for the manifest writer."""
    import yaml
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or not spec:
        raise SystemExit(f"--overrides {path}: expected a flat non-empty YAML mapping")
    sig = signature_constants()
    applied = {}
    for k, v in spec.items():
        k = str(k)
        if not hasattr(config, k):
            raise SystemExit(f"--overrides: config has no constant {k!r} — typo? "
                             f"(overrides never CREATE constants; append to config.py)")
        if k in sig and not force_retile:
            raise SystemExit(
                f"--overrides: {k} feeds tiling._tile_signature — changing it changes "
                f"which tile cache this run reads (~20 min/year re-tile). If that is "
                f"intended, add --force-retile-overrides.")
        old = getattr(config, k)
        if old is not None and v is not None:
            ok = (isinstance(v, type(old))
                  or (isinstance(old, float) and isinstance(v, int))
                  or (isinstance(old, bool) == isinstance(v, bool) is False
                      and isinstance(old, (int, float)) and isinstance(v, (int, float))))
            if isinstance(old, bool) != isinstance(v, bool):
                ok = False
            if not ok:
                raise SystemExit(f"--overrides: {k} is {type(old).__name__} "
                                 f"({old!r}); got {type(v).__name__} ({v!r})")
        setattr(config, k, v)
        applied[k] = v
    config.OVERRIDES_APPLIED = dict(applied)
    print(f"  overrides: {len(applied)} constant(s) from {path}: "
          + ", ".join(f"{k}={v!r}" for k, v in applied.items()))
    return applied


def prescan_argv(argv):
    """Pop --overrides [PATH] (space or equals form) and --force-retile-overrides from
    argv, apply them, return the remaining argv. Runs BEFORE the parser is built so
    argparse defaults (which read config at build time) see the overridden values."""
    out, path, force = [], None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--force-retile-overrides":
            force = True
        elif a == "--overrides":
            if i + 1 >= len(argv):
                raise SystemExit("--overrides needs a YAML path")
            path = argv[i + 1]
            i += 1
        elif a.startswith("--overrides="):
            path = a.split("=", 1)[1]
        else:
            out.append(a)
        i += 1
    if path:
        apply_overrides(path, force_retile=force)
    elif force:
        raise SystemExit("--force-retile-overrides without --overrides does nothing")
    return out
