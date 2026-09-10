r"""crown_state_vs_gold.py — score the crown state model against the frozen Panel A gold.

THE REFEREE'S INSTRUMENT (`Scripts/experiments/crown_state_model.yaml`, DESIGN CONTRACT:
the proposer does not score the proposal). It reads a posterior written by
`crown_state_model.py` and scores it at the 1,214 Panel A gold points EXACTLY as
`heal_vs_gold.py` scores the healer, so `phase4/qc/crown_state_vs_gold.csv` and
`phase4/qc/heal_vs_gold_12ep.csv` read side by side with the same trailer keys.

WHAT "BEFORE" AND "AFTER" MEAN HERE.
  raw   — the delivered mask value at the gold point's CELL on the 2 m stack, identical to
          heal_vs_gold's `raw`. Its impossible-triple count therefore reconciles exactly
          with heal_vs_gold_12ep.csv (327 no-change / 14 loss / 1 gain) and that
          reconciliation is asserted, not hoped for: a mismatch is FATAL.
  after — the CROWN state model's trajectory for the crown CONTAINING that point:
          the Viterbi path (PRIMARY; states canopy_new and canopy both read as canopy)
          and, secondary, the posterior >= 0.5 path. A gold point that falls on no crown
          is OFF-CROWN: the model has nothing to say there, it is excluded from every
          label trailer, and it is counted in `offcrown_n`.

The point-to-crown join goes through the SAME rasterised crown ids the model's own
observation operator used — `crown_state_model.load_crowns` — never a fresh sjoin, so the
scorer cannot silently disagree with the thing it scores. That rasterisation costs ~90 s
and 1.3 GB of I/O, so `--crown-map` caches it: the map depends on the stack lattice and
the crown file only, never on which posterior is being scored, and the 20 placebo draws
and the K4 rate set all reuse one map.

CENSORING IS ZERO BY CONSTRUCTION. The model has no IGNORE state — it asserts canopy or
absence at every crown-epoch. `loss_term_censored` is therefore structurally 0 and is NOT
evidence of good behaviour; the healer earns its own 0 while retaining the option. Read
K2 knowing the same asymmetry: 149 of the healer's no-change fixes are IGNORE markings,
which the model cannot make.

Output: phase4/qc/crown_state_vs_gold.csv

Run:  py -3.12 qc/instruments/crown_state_vs_gold.py
      py -3.12 qc/instruments/crown_state_vs_gold.py --npz <other.npz> --out <other.csv>
"""
from __future__ import annotations

import argparse
import collections
import csv
import importlib.util
import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

STACK = Path(r"D:\edmonds-pipeline\heal_stack_2m.npz")
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")
POSTERIOR = QC / "crown_state_posterior.npz"
GOLD = QC / "panel_a_gold.csv"
HEALER = QC / "heal_vs_gold_12ep.csv"
OUT_CSV = QC / "crown_state_vs_gold.csv"

PRESENT_AT = 0.50
# heal_vs_gold_12ep.csv trailer — the reconciliation target for the RAW trajectories.
RAW_TRIPLES_EXPECTED = {"nochange": 327, "loss": 14, "gain": 1}

LABELS = ("nochange", "loss", "gain")


def _rows(p):
    p = Path(p)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _trailer(p):
    """The `# key,value` trailer of a sibling csv -> dict."""
    p = Path(p)
    if not p.exists():
        return {}
    out = {}
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("#") and "," in ln:
            k, _, v = ln[1:].strip().partition(",")
            out[k.strip()] = v.strip()
    return out


def _load_model_module():
    """Import crown_state_model by path — no new path hack (the ledger in
    test_status_discovery.py is a ratchet)."""
    p = SCRIPTS / "qc" / "instruments" / "crown_state_model.py"
    spec = importlib.util.spec_from_file_location("_crown_state_model_for_referee", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --------------------------------------------------------------------- pure scoring

def triples(t):
    """canopy -> gone -> canopy on consecutive epochs. Verbatim from heal_vs_gold.py."""
    return sum(1 for i in range(1, len(t) - 1)
               if t[i - 1] == 1 and t[i] == 0 and t[i + 1] == 1)


def terminal_start(raw):
    """Index where the TERMINAL run of absent epochs begins (== len(raw) if none).
    Verbatim semantics from heal_vs_gold.py."""
    term = len(raw)
    while term > 0 and raw[term - 1] == 0:
        term -= 1
    return term


def score_point(raw, after, after2):
    """One gold point. `raw` is the pixel trajectory (1/0/255); `after`/`after2` are the
    crown model's primary (Viterbi) and secondary (posterior>=0.5) trajectories, each
    1/0 with no IGNORE. -> dict of the same quantities heal_vs_gold reports.

    Laundering, defined exactly as heal_vs_gold defines it: the model asserts canopy at an
    epoch inside the TERMINAL run of absence — the run the loss itself created. Filling a
    mid-series dropout at a point cut later is the operator working, not laundering.
    """
    term = terminal_start(raw)
    laundered = sum(1 for i in range(term, len(raw)) if raw[i] == 0 and after[i] == 1)
    laundered2 = sum(1 for i in range(term, len(raw)) if raw[i] == 0 and after2[i] == 1)
    # the model has no IGNORE state; kept so the column exists in both files.
    censored = sum(1 for i in range(term, len(raw)) if raw[i] == 0 and after[i] == 255)
    return {
        "terminal_absent_epochs": len(raw) - term,
        "terminal_laundered": laundered,
        "terminal_laundered_posterior": laundered2,
        "terminal_censored": censored,
        # mechanism of each laundering: what did the CROWN observe there?
        "laundered_crown_obs1": 0, "laundered_crown_obs0": 0,
        "laundered_crown_missing": 0,
        "impossible_triples_raw": triples(raw),
        "impossible_triples_healed": triples(after),
        "impossible_triples_posterior": triples(after2),
        "healed_to_canopy": sum(1 for i in range(len(raw))
                                if raw[i] == 0 and after[i] == 1),
        "healed_to_ignore": 0,
        "n_epochs_touched": sum(1 for i in range(len(raw)) if raw[i] != after[i]),
    }


def summarise(rows):
    """-> (by-label Counter dict, offcrown_n). Off-crown rows are excluded from the
    label trailers and counted on their own."""
    by = collections.defaultdict(collections.Counter)
    off = 0
    for r in rows:
        if r["offcrown"]:
            off += 1
            continue
        b = by[r["label"]]
        b["n"] += 1
        b["touched"] += int(r["n_epochs_touched"] > 0)
        b["to_canopy"] += int(r["healed_to_canopy"] > 0)
        b["to_ignore"] += int(r["healed_to_ignore"] > 0)
        b["triples_raw"] += r["impossible_triples_raw"]
        b["triples_healed"] += r["impossible_triples_healed"]
        b["triples_posterior"] += r["impossible_triples_posterior"]
        b["triples_fixed"] += max(0, r["impossible_triples_raw"]
                                  - r["impossible_triples_healed"])
        b["triples_fixed_posterior"] += max(0, r["impossible_triples_raw"]
                                            - r["impossible_triples_posterior"])
        b["laundered"] += r["terminal_laundered"]
        b["laundered_posterior"] += r["terminal_laundered_posterior"]
        b["laundered_points"] += int(r["terminal_laundered"] > 0)
        b["laundered_crown_obs1"] += r["laundered_crown_obs1"]
        b["laundered_crown_obs0"] += r["laundered_crown_obs0"]
        b["laundered_crown_missing"] += r["laundered_crown_missing"]
        b["term_censored"] += r["terminal_censored"]
        b["has_terminal_absence"] += int(r["terminal_absent_epochs"] > 0)
    return by, off


def offcrown_triples(rows):
    """Raw triples sitting at OFF-CROWN points, by label. K2 read on the plain yaml
    denominator (all 1,170 no-change points) counts these as UNFIXED."""
    d = collections.Counter()
    for r in rows:
        if r["offcrown"]:
            d[r["label"]] += r["impossible_triples_raw"]
    return d


# --------------------------------------------------------------------------- I/O

def crown_map(stack_path, crowns_path, gold, cache=None):
    """Gold point -> (row, col, crown raster id). Uses the model's OWN rasterisation.

    `cache` is a csv of point_id,row,col,crown_idx,inside — written if absent, read if
    present. It depends only on the stack lattice and the crown file.
    """
    import numpy as np
    if cache is not None and Path(cache).exists():
        got = {r["point_id"]: (int(r["row"]), int(r["col"]), int(r["crown_idx"]),
                               int(r["inside"])) for r in _rows(cache)}
        missing = [g["point_id"] for g in gold if g["point_id"] not in got]
        if missing:
            raise SystemExit(f"FATAL: crown map {cache} misses {len(missing)} gold points")
        return got

    m = _load_model_module()
    stack, inside, years, tags, g, ids = m.load_crowns(stack_path, crowns_path)
    d = np.load(stack_path)
    tf = d["transform"]
    h, w = inside.shape
    out = {}
    for pt in gold:
        col = int((float(pt["x"]) - tf[2]) / tf[0])
        row = int((float(pt["y"]) - tf[5]) / tf[4])
        ok = 0 <= row < h and 0 <= col < w and bool(inside[row, col])
        cid = int(ids[row, col]) if (0 <= row < h and 0 <= col < w) else 0
        out[pt["point_id"]] = (row, col, cid, int(ok))
    if cache is not None:
        buf = io.StringIO(newline="")
        wtr = csv.writer(buf, lineterminator="\n")
        wtr.writerow(["point_id", "row", "col", "crown_idx", "inside"])
        for pid, (r, c, cid, ok) in out.items():
            wtr.writerow([pid, r, c, cid, ok])
        buf.write(f"# stack,{stack_path}\n# crowns,{crowns_path}\n")
        buf.write(f"# n_crowns,{len(g)}\n")
        Path(cache).write_text(buf.getvalue(), encoding="utf-8", newline="")
    return out


def build(stack=None, crowns=None, npz=None, gold_csv=None, cache=None,
          check_raw=True):
    """-> (rows, meta, err)."""
    import numpy as np
    stack_path = Path(stack) if stack is not None else STACK
    crowns_path = Path(crowns) if crowns is not None else CROWNS
    npz_path = Path(npz) if npz is not None else POSTERIOR
    gold = _rows(gold_csv or GOLD)
    if not gold:
        return None, None, "panel_a_gold.csv absent — run freeze_panel_a_gold.py"
    if not npz_path.exists():
        return None, None, f"{npz_path} absent — run crown_state_model.py first"
    if not stack_path.exists():
        return None, None, f"{stack_path} not found (local cache)"

    P = np.load(npz_path, allow_pickle=True)
    vit = P["viterbi"]                     # (E, N) states 0=absent 1=new 2=canopy
    pcan = P["post_canopy"]
    obs = P["obs"]
    n_crowns = vit.shape[1]

    d = np.load(stack_path)
    sarr = d["stack"]
    years = [str(y) for y in d["years"]]
    if len(years) != vit.shape[0]:
        return None, None, (f"epoch mismatch: stack has {len(years)}, posterior "
                            f"{vit.shape[0]}")

    m = crown_map(stack_path, crowns_path, gold, cache)

    rows = []
    for pt in gold:
        row, col, cidx, ok = m[pt["point_id"]]
        raw = [int(sarr[i][row, col]) for i in range(len(years))] if ok else []
        offcrown = (not ok) or cidx <= 0 or cidx > n_crowns
        if offcrown:
            rec = {k: 0 for k in score_point([0], [0], [0])}
            rec["impossible_triples_raw"] = triples(raw) if raw else 0
            rec.update({"point_id": pt["point_id"], "label": pt["label"],
                        "crown_idx": cidx, "crown_id": "", "offcrown": 1,
                        "off_grid": int(not ok),
                        "raw_trajectory": "".join(
                            "C" if v == 1 else ("." if v == 0 else "x") for v in raw),
                        "viterbi_trajectory": "", "posterior_trajectory": "",
                        "crown_obs": ""})
            rows.append(rec)
            continue
        j = cidx - 1
        after = [1 if int(vit[i, j]) != 0 else 0 for i in range(len(years))]
        after2 = [1 if float(pcan[i, j]) >= PRESENT_AT else 0 for i in range(len(years))]
        crown_obs = [int(obs[i, j]) for i in range(len(years))]
        rec = score_point(raw, after, after2)
        term = terminal_start(raw)
        for i in range(term, len(raw)):
            if raw[i] == 0 and after[i] == 1:
                if crown_obs[i] == 1:
                    rec["laundered_crown_obs1"] += 1
                elif crown_obs[i] == 0:
                    rec["laundered_crown_obs0"] += 1
                else:
                    rec["laundered_crown_missing"] += 1
        rec.update({
            "point_id": pt["point_id"], "label": pt["label"], "crown_idx": cidx,
            "crown_id": str(P["crown_id"][j]), "offcrown": 0, "off_grid": 0,
            "raw_trajectory": "".join("C" if v == 1 else ("." if v == 0 else "x")
                                      for v in raw),
            "viterbi_trajectory": "".join("ANC"[int(vit[i, j])]
                                          for i in range(len(years))),
            "posterior_trajectory": "".join(
                "C" if float(pcan[i, j]) >= PRESENT_AT else "."
                for i in range(len(years))),
            "crown_obs": "".join("C" if v == 1 else ("." if v == 0 else "x")
                                 for v in crown_obs),
        })
        rows.append(rec)

    raw_by_label = collections.Counter()
    for r in rows:
        raw_by_label[r["label"]] += r["impossible_triples_raw"]
    if check_raw:
        bad = {k: (raw_by_label[k], v) for k, v in RAW_TRIPLES_EXPECTED.items()
               if raw_by_label[k] != v}
        if bad:
            return None, None, (
                "RAW TRIPLES DO NOT RECONCILE with heal_vs_gold_12ep.csv "
                f"(got vs expected): {bad}. The point-to-cell mapping or the stack is "
                "wrong — refusing to report any trailer number.")
    meta = {"years": years, "n_crowns": n_crowns, "npz": str(npz_path),
            "stack": str(stack_path), "raw_triples": dict(raw_by_label),
            "placebo_seed": int(P["placebo_seed"]),
            "permutation": P["permutation"].tolist(),
            "ref": str(P["ref"]), "policy": str(P["policy"]),
            "dropped_tags": [str(t) for t in P["dropped_tags"]]}
    return rows, meta, None


def _parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=str(STACK))
    ap.add_argument("--crowns", default=str(CROWNS))
    ap.add_argument("--npz", default=str(POSTERIOR),
                    help="posterior written by crown_state_model.py")
    ap.add_argument("--gold", default=str(GOLD))
    ap.add_argument("--crown-map", default=None,
                    help="cache of the point->crown join; written if absent, reused if "
                         "present (the 20 placebo draws all share one)")
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv=None):
    from phase4seg.names import clean_argv
    a = _parser().parse_args(clean_argv() if argv is None else argv)

    rows, meta, err = build(stack=a.stack, crowns=a.crowns, npz=a.npz,
                            gold_csv=a.gold, cache=a.crown_map)
    if err:
        print(f"FATAL: {err}")
        return 2

    by, off = summarise(rows)
    offtrip = offcrown_triples(rows)

    cols = ["point_id", "label", "crown_idx", "crown_id", "offcrown", "off_grid",
            "terminal_absent_epochs", "terminal_laundered",
            "terminal_laundered_posterior", "terminal_censored",
            "laundered_crown_obs1", "laundered_crown_obs0", "laundered_crown_missing",
            "raw_trajectory", "viterbi_trajectory", "posterior_trajectory", "crown_obs",
            "n_epochs_touched", "impossible_triples_raw", "impossible_triples_healed",
            "impossible_triples_posterior", "healed_to_canopy", "healed_to_ignore"]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    for lab in sorted(by):
        for k, v in sorted(by[lab].items()):
            buf.write(f"# {lab}_{k},{v}\n")
    buf.write(f"# offcrown_n,{off}\n")
    for lab in LABELS:
        buf.write(f"# offcrown_triples_raw_{lab},{offtrip.get(lab, 0)}\n")
    buf.write(f"# off_grid,{sum(r['off_grid'] for r in rows)}\n")
    buf.write(f"# npz,{meta['npz']}\n# stack,{meta['stack']}\n")
    buf.write(f"# placebo_seed,{meta['placebo_seed']}\n")
    buf.write(f"# permutation,\"{meta['permutation']}\"\n")
    buf.write(f"# rates_ref,{meta['ref']}\n# rates_policy,{meta['policy']}\n")
    buf.write(f"# dropped_tags,\"{','.join(meta['dropped_tags'])}\"\n")
    buf.write(f"# n_crowns,{meta['n_crowns']}\n")
    if not a.dry_run:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(buf.getvalue(), encoding="utf-8", newline="")

    if a.quiet:
        nc = by.get("nochange", collections.Counter())
        ls = by.get("loss", collections.Counter())
        print(f"seed={meta['placebo_seed']} K2={nc['triples_fixed']} "
              f"K1={ls['laundered']} offcrown={off}")
        return 0

    h = _trailer(HEALER)
    print(f"{'DRY RUN: ' if a.dry_run else ''}{a.out} — {len(rows)} gold points, "
          f"{off} OFF-CROWN (no 2020 polygon contains them), "
          f"{sum(r['off_grid'] for r in rows)} off-grid")
    print(f"  posterior: {meta['npz']}  seed={meta['placebo_seed']} "
          f"ref={meta['ref']}")
    print(f"  RAW triples reconcile with heal_vs_gold_12ep.csv: {meta['raw_triples']}")
    print(f"\n{'label':10}{'n':>6}{'touched':>9}{'->canopy':>10}{'trip raw':>10}"
          f"{'vit':>7}{'post':>7}{'fixed':>7}{'laund':>7}")
    for lab in LABELS:
        b = by.get(lab)
        if not b:
            continue
        print(f"{lab:10}{b['n']:>6}{b['touched']:>9}{b['to_canopy']:>10}"
              f"{b['triples_raw']:>10}{b['triples_healed']:>7}"
              f"{b['triples_posterior']:>7}{b['triples_fixed']:>7}"
              f"{b['laundered']:>7}")

    nc = by.get("nochange", collections.Counter())
    ls = by.get("loss", collections.Counter())
    print("\nK1 LAUNDERING — canopy asserted inside a verified loss's TERMINAL absence")
    print(f"  Viterbi (primary): {ls['laundered']} epochs at "
          f"{ls['laundered_points']} of {ls['n']} loss points   <- must be 0")
    print(f"  posterior>=0.5   : {ls['laundered_posterior']} epochs")
    print(f"  AT-RISK denominator: {ls['has_terminal_absence']} of {ls['n']} on-crown "
          "loss points have a terminal absence at all.")
    print("    Unlike the healer there is no fill PREDICATE to gate on: the model asserts "
          "a state at\n    every crown-epoch, so at-risk == eligible == the points with a "
          "terminal absence.")
    print(f"  mechanism of the laundered epochs — crown observed CANOPY: "
          f"{ls['laundered_crown_obs1']}, observed ABSENT: {ls['laundered_crown_obs0']}, "
          f"MISSING: {ls['laundered_crown_missing']}")
    print(f"  censoring: {ls['term_censored']} — ZERO BY CONSTRUCTION, the model has no "
          "IGNORE state.\n    Not evidence of restraint; the healer's own 0 "
          f"({h.get('loss_term_censored', '?')}) is earned while keeping the option.")

    print("\nK2 TRIPLES — impossible triples removed at verified NO-CHANGE")
    raw_all = nc['triples_raw'] + offtrip.get("nochange", 0)
    print(f"  healer, 12 epochs: {h.get('nochange_triples_fixed', '?')} of "
          f"{h.get('nochange_triples_raw', '?')}  "
          f"({int(h.get('nochange_triples_fixed', 0)) / max(int(h.get('nochange_triples_raw', 1)), 1):.3f})")
    print(f"  model, Viterbi   : {nc['triples_fixed']} of {raw_all}  "
          f"({nc['triples_fixed'] / max(raw_all, 1):.3f})   "
          "[yaml denominator: all no-change points; off-crown triples count as UNFIXED]")
    print(f"  model, on-crown  : {nc['triples_fixed']} of {nc['triples_raw']}  "
          f"({nc['triples_fixed'] / max(nc['triples_raw'], 1):.3f})")
    print(f"  model, posterior : {nc['triples_fixed_posterior']} of {raw_all}  "
          "(secondary)")
    print(f"  ASYMMETRY: {h.get('nochange_to_ignore', '?')} of the healer's no-change "
          "fixes are IGNORE markings.\n    The model cannot mark IGNORE, so it must "
          "assert to fix. The two counts are not\n    apples-to-apples and the direction "
          "of that bias is toward the model.")
    print("\n-- MEASURED / DERIVED / ASSUMED " + "-" * 34)
    print("  MEASURED: the raw pixel trajectories at the 1,214 frozen gold points; the "
          "healer's own\n            twelve-epoch trailer (heal_vs_gold_12ep.csv); the "
          "model's Viterbi and posterior.")
    print("  DERIVED : impossible triples, terminal-absence runs, laundering counts — "
          "all by the\n            definitions in heal_vs_gold.py, reused verbatim.")
    print("  ASSUMED : (1) a gold POINT inherits the state of the CROWN containing it — "
          "the model has\n            no pixel-level output, so a partial removal inside "
          "a surviving crown reads as\n            laundering by construction; (2) the "
          "rasterised crown ids resolve overlaps by\n            draw order, as the "
          "model's own observation operator does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
