"""heal_stack_build.py — the N-epoch 2 m stack the healer runs on, beside the published 8.

WHY. `temporal_heal.py` and every instrument downstream of it (`heal_gap_spectrum.py`,
`heal_closing_baseline.py`, `heal_fill_*.py`) are STACK-DRIVEN: they read one npz of
warped masks and take the epoch list from its `years` key. The eight-epoch cache
`D:\\edmonds-pipeline\\trend8_stack_2m.npz` is written by
`trend8_transition_census.py::main` and it is a PUBLISHED MEASUREMENT — every tracked
`phase4/qc/temporal_heal.csv`, `heal_gap_spectrum.csv`, `heal_closing_baseline.csv` and
`heal_fill_*.csv` was regenerated from it. The `heal_infill_2017_2023` campaign adds four
epochs (2017, 2020, 2022, 2023 as `heal_{year}` masks) and the healer must then run on
twelve. Re-running the census would overwrite the eight-epoch cache under the same name
and every published number would silently stop being reproducible. This file builds the
wider stack somewhere ELSE, on the SAME lattice, by the SAME warp, and refuses to touch
the published one.

WHAT. One npz with the four keys every consumer reads — `stack` (n, h, w) uint8 0/1/255,
`inside` (h, w) bool, `years` (n) str, `transform` (6 floats) — plus two the consumers
ignore: `tags` (n) str run tags and `sources` (n) str mask file names, so a reader can
tell which arm produced each layer. An epoch is a (year_label, run_tag) pair whose mask is
`{masks-dir}/edmonds_canopy_mask_{label}_{tag}.tif`. The default epoch set is the eight
trend8 pairs from `trend8_transition_census.py::YEARS` plus every
`edmonds_canopy_mask_{Y}_heal_{Y}.tif` found in the masks dir, ordered chronologically by
`temporal_heal.py::_year_int`, ties by label. The lattice is
`trend8_transition_census.py::city_grid` (or `--grid-from` an existing stack, which pins
this build to that stack's lattice exactly); each layer is
`trend8_transition_census.py::warp_mask`, the census's own code, called not copied.

GATES, each shown to fire in `qc/test_heal_stack_build.py`:
  * The output may NEVER be named `trend8_stack_2m.npz` — exit 2 before anything is read,
    and `--force` does not lift it. That name is the published eight-epoch cache.
  * A heal epoch whose year label already has a trend8 epoch is refused by name: two
    layers for one label would give the healer a bracket of zero years.
  * An existing `--out` is not overwritten without `--force`.
  * `--dry-run` resolves and prints the epoch table and writes nothing.
  * When a reference stack shares epochs with this build (default: the published cache,
    if present) the shared layers are compared cell for cell and any difference is
    reported as PARITY MISMATCH with exit 3 — the eight published epochs must be the same
    data in both files or the twelve-epoch results are not comparable to the eight.

Output: D:\\edmonds-pipeline\\heal_stack_2m.npz (local cache, NOT the lake)

Run:  py -3.12 qc/instruments/heal_stack_build.py --dry-run
      py -3.12 qc/instruments/heal_stack_build.py [--force]
      py -3.12 qc/instruments/heal_stack_build.py --epochs "2009:trend8_2009,2017:heal_2017"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from lake import BASE

MASKS = BASE / "phase4" / "masks"
DEFAULT_OUT = Path(r"D:\edmonds-pipeline\heal_stack_2m.npz")
PUBLISHED_CACHE = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")
FORBIDDEN_NAME = "trend8_stack_2m.npz"

_HEAL_RE = re.compile(r"^edmonds_canopy_mask_(?P<y>[^_]+)_heal_(?P=y)\.tif$")


def _sibling(name):
    """Import a sibling instrument BY FILE LOCATION — no sys.path insert (the ledger in
    test_status_discovery.py::test_path_insert_ledger is a ratchet)."""
    import importlib.util
    p = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_hsb_{name}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def trend8_epochs():
    """The eight published pairs, read from the census — one fact, one home."""
    tc = _sibling("trend8_transition_census")
    return [(y, f"trend8_{y}") for y in tc.YEARS]


def mask_path(masks_dir, label, tag):
    return Path(masks_dir) / f"edmonds_canopy_mask_{label}_{tag}.tif"


def discover_heal(masks_dir):
    """(label, heal_{label}) for every campaign mask in the dir. Files only, .tif only,
    label == tag suffix — the dir also holds .gpkg twins and prob rasters."""
    out = []
    for p in sorted(Path(masks_dir).glob("edmonds_canopy_mask_*_heal_*.tif")):
        m = _HEAL_RE.match(p.name)
        if m:
            out.append((m.group("y"), f"heal_{m.group('y')}"))
    return out


def parse_epochs(spec):
    """'2009:trend8_2009,2017:heal_2017' -> [(label, tag), ...]."""
    out = []
    for item in str(spec).split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"epoch {item!r} is not label:tag")
        label, tag = item.split(":", 1)
        out.append((label.strip(), tag.strip()))
    return out


def order_epochs(epochs):
    th = _sibling("temporal_heal")
    return sorted(epochs, key=lambda e: (th._year_int(e[0]), e[0]))


def resolve_epochs(spec=None, masks_dir=MASKS):
    """The epoch list this build will use, ordered. Raises ValueError on a duplicate
    label — a heal epoch colliding with a trend8 one is named as such."""
    if spec:
        epochs = parse_epochs(spec)
    else:
        base = trend8_epochs()
        have = {y for y, _ in base}
        heal = discover_heal(masks_dir)
        clash = [f"{y} ({t} vs trend8_{y})" for y, t in heal if y in have]
        if clash:
            raise ValueError("heal epoch collides with a trend8 epoch for the same year "
                             "label: " + ", ".join(clash))
        epochs = base + heal
    seen, dup = set(), []
    for y, _ in epochs:
        if y in seen:
            dup.append(y)
        seen.add(y)
    if dup:
        raise ValueError(f"duplicate year label(s): {sorted(set(dup))}")
    return order_epochs(epochs)


def epoch_table(epochs, masks_dir=MASKS):
    rows = []
    for y, t in epochs:
        p = mask_path(masks_dir, y, t)
        rows.append((y, t, p, p.exists()))
    return rows


def grid_from_stack(path):
    """(tf, w, h, inside) pinned to an existing stack's lattice."""
    import numpy as np
    from affine import Affine
    d = np.load(path, allow_pickle=False)
    inside = d["inside"].astype(bool)
    h, w = inside.shape
    return Affine(*[float(v) for v in d["transform"][:6]]), w, h, inside


def _log_flush(msg):
    # Redirected to a file, plain print buffers until exit: a 40-minute build looked
    # dead for its whole duration on 2026-09-08. Flush every progress line.
    print(msg, flush=True)


def build(epochs, masks_dir=MASKS, grid=None, log=_log_flush):
    """Warp every epoch onto the lattice. Returns the dict `write` saves.

    `grid` is (tf, w, h, inside); None means `trend8_transition_census.py::city_grid`.
    """
    import numpy as np
    tc = _sibling("trend8_transition_census")
    tf, w, h, inside = grid if grid is not None else tc.city_grid()
    layers, years, tags, sources = [], [], [], []
    for y, t in epochs:
        p = mask_path(masks_dir, y, t)
        layers.append(tc.warp_mask(p, tf, w, h))
        years.append(y)
        tags.append(t)
        sources.append(p.name)
        log(f"  {y} ({t}) cached")
    stack = np.stack(layers).astype(np.uint8)
    return {"stack": stack, "inside": np.asarray(inside, dtype=bool),
            "years": np.array(years), "tags": np.array(tags),
            "sources": np.array(sources),
            "transform": np.array(tf)[:6].astype(float)}


def parity(arrays, reference):
    """Compare every epoch shared with `reference` cell for cell.

    Returns (n_shared, mismatched_labels, note). A lattice that differs is reported as a
    mismatch of every shared epoch, since no cell-wise comparison is then meaningful.
    """
    import numpy as np
    d = np.load(reference, allow_pickle=False)
    ry = [str(y) for y in d["years"]]
    mine = [str(y) for y in arrays["years"]]
    shared = [y for y in mine if y in ry]
    if not shared:
        return 0, [], "no shared epochs"
    if (d["stack"].shape[1:] != arrays["stack"].shape[1:]
            or not np.allclose(d["transform"][:6], arrays["transform"])):
        return len(shared), list(shared), "lattice differs"
    bad = []
    for y in shared:
        if not np.array_equal(d["stack"][ry.index(y)], arrays["stack"][mine.index(y)]):
            bad.append(y)
    return len(shared), bad, ""


def refuse_name(out):
    return Path(out).name.lower() == FORBIDDEN_NAME


def write(out, arrays):
    import numpy as np
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **arrays)
    return out


def _parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", default=None,
                    help='override: "2009:trend8_2009,2017:heal_2017,..."')
    ap.add_argument("--masks-dir", default=str(MASKS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--grid-from", default=None,
                    help="pin the lattice to an existing stack's inside+transform")
    ap.add_argument("--reference", default=str(PUBLISHED_CACHE),
                    help="stack to parity-check shared epochs against ('' to skip)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved epoch table, write nothing")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing --out (never the published cache)")
    return ap


def main(argv=None):
    from phase4seg.names import clean_argv
    a = _parser().parse_args(clean_argv() if argv is None else argv)
    out = Path(a.out)

    # THE HARD GATE, first, before anything is read and regardless of --force.
    if refuse_name(out):
        print(f"REFUSED: {out} — {FORBIDDEN_NAME} is the published 8-epoch cache "
              f"(trend8_transition_census.py::main). This builder never writes it.")
        return 2

    try:
        epochs = resolve_epochs(a.epochs, a.masks_dir)
    except ValueError as e:
        print(f"REFUSED: {e}")
        return 2

    rows = epoch_table(epochs, a.masks_dir)
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} epochs -> {out}")
    print(f"  {'label':7}{'tag':14}{'exists':7}path")
    for y, t, p, ex in rows:
        print(f"  {y:7}{t:14}{str(ex):7}{p}")
    if a.dry_run:
        return 0

    missing = [str(p) for _, _, p, ex in rows if not ex]
    if missing:
        print("FATAL: mask(s) missing:\n  " + "\n  ".join(missing))
        return 2
    if out.exists() and not a.force:
        print(f"REFUSED: {out} exists — pass --force to overwrite it")
        return 2

    grid = grid_from_stack(a.grid_from) if a.grid_from else None
    arrays = build(epochs, a.masks_dir, grid)
    write(out, arrays)
    n, h, w = arrays["stack"].shape
    print(f"wrote {out}: {n} epochs, shape ({n}, {h}, {w}), "
          f"{out.stat().st_size / 1e6:.1f} MB")

    ref = Path(a.reference) if a.reference else None
    if ref is not None and ref.exists() and ref.resolve() != out.resolve():
        n_shared, bad, note = parity(arrays, ref)
        if bad:
            print(f"PARITY MISMATCH vs {ref}: {len(bad)}/{n_shared} shared epochs differ "
                  f"{bad}{(' — ' + note) if note else ''}")
            return 3
        print(f"parity vs {ref.name}: {n_shared} shared epochs identical"
              + (f" ({note})" if note else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
