r"""Re-derive the formula worker's cost model, its slice balance, and the decode's stability.

    LITKB_PGPORT=1 PYTHONUTF8=1 py -3.12 qc/instruments/litkb_formula_balance.py

CLAUDE.md §3.4b: every number the canary-2 report's "Determinism" section states about the
proxy, the fit, the runaway rate or the corpus projection comes from here, and none of them
is retyped into a doc as an authored fact. It reads only archives that already exist —
canary 1's and canary 2's result zips and the shard they both decoded — and writes nothing to
the lake and nothing to a database. No GPU.

WHAT IT MEASURES, and why each one is here:

1. **The proxy.** Spearman of several pixel-derived candidates against canary 1's decoded
   length. The shipped proxy used to be ``width x ink density``, which cancels to ``ink/h``
   and so cannot see height — the thing that separates a multi-line array from an inline
   fragment. Ink pixel count ranks at +0.873 against that form's +0.389.
2. **The batch cost model.** ``seconds = a + b x max(member chars)`` fitted on canary 2's 40
   measured batches. A batched greedy decode steps every sequence together and stops when the
   LONGEST finishes, so a batch's time is its longest member's, not the sum of its members' —
   which is why ``batch_costs`` takes a max.
3. **The slice balance**, by simulation on those measured timings: re-plan the same 200 crops
   with each proxy, LPT them into 6 slices, and cost each slice with the fitted model. This is
   a SIMULATION on measured data, not a run, and the report says so in those words.
4. **The runaway rate.** How many rows in each canary are repetition loops that ran to
   ``max_new_tokens``, how many of those are identical in BOTH runs (and therefore invisible
   to any stability check), and how many the shipped detector catches.
5. **The corpus projection**, including what the stability guard's re-decode costs — which is
   NOT 5% of the time, because the rows it re-decodes are the expensive ones.
"""
import argparse
import csv
import json
import math
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(SCRIPTS, "Scripts", "pipeline")
                if os.path.isdir(os.path.join(SCRIPTS, "Scripts")) else
                os.path.join(os.path.dirname(HERE), "..", "pipeline"))

DERIVED = r"D:\edmonds-pipeline\litkb_derived\formula"
CORPUS_CROPS = 7164          # the census in Reports/LITKB_COLAB_L4_FORMULA_2026-09-15.md
N_SLICES, BATCH_SIZE = 6, 5


def _rows(zp):
    with zipfile.ZipFile(zp) as z:
        return {r["crop_id"]: r for r in
                (json.loads(ln) for ln in z.read("results.jsonl").decode().splitlines()
                 if ln.strip())}


def _geometry(shard_zip, worker):
    import io as _io

    from PIL import Image
    out = {}
    with zipfile.ZipFile(shard_zip) as z:
        man = json.loads(z.read("manifest.json").decode("utf-8"))
        for c in man["crops"]:
            im = Image.open(_io.BytesIO(z.read("crops/" + c["crop_id"] + ".png")))
            ink, w, h = worker.crop_ink(im.convert("RGB"))
            out[c["crop_id"]] = {"ink": ink, "w": w, "h": h}
    return out


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r, i = [0.0] * len(v), 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0 + 1
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return num / (dx * dy) if dx and dy else 0.0


def linfit(X, Y):
    n = len(X)
    mx, my = sum(X) / n, sum(Y) / n
    b = sum((x - mx) * (y - my) for x, y in zip(X, Y)) / sum((x - mx) ** 2 for x in X)
    a = my - b * mx
    ss = sum((y - my) ** 2 for y in Y)
    rs = sum((y - (a + b * x)) ** 2 for x, y in zip(X, Y))
    return a, b, (1 - rs / ss if ss else 0.0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--derived", default=DERIVED)
    ap.add_argument("--csv", default=None, help="where the measured table goes")
    a = ap.parse_args(argv or sys.argv[1:])

    from litkb.extract import colab_formula_worker as W

    shard = os.path.join(a.derived, "shards", "shard_canary200.zip")
    r1 = _rows(os.path.join(a.derived, "results", "result_shard_canary200.zip"))
    r2 = _rows(os.path.join(a.derived, "results_procs", "result_shard_canary200.zip"))
    geo = _geometry(shard, W)
    ids = sorted(geo)
    L1 = {i: len(r1[i].get("latex") or "") for i in ids}
    L2 = {i: len(r2[i].get("latex") or "") for i in ids}
    out = []

    # ── 1. the proxy ────────────────────────────────────────────────────────────────────
    truth = [L1[i] for i in ids]
    cands = {
        "old: w x ink density (= ink/h)": lambda g: g["w"] * (g["ink"] / float(g["w"] * g["h"]))
        if g["w"] and g["h"] else 0.0,
        "NEW: ink pixel count": lambda g: g["ink"],
        "crop area w x h": lambda g: g["w"] * g["h"],
        "height": lambda g: g["h"],
        "width": lambda g: g["w"],
    }
    print("\n1. PROXY — Spearman against canary-1 decoded characters, n=%d" % len(ids))
    for name, fn in cands.items():
        rho = spearman([fn(geo[i]) for i in ids], truth)
        print("   %-34s %+.3f" % (name, rho))
        out.append({"section": "proxy", "name": name, "value": round(rho, 4),
                    "unit": "spearman_vs_canary1_chars", "n": len(ids)})

    # ── 2. the batch cost model ─────────────────────────────────────────────────────────
    bat = {}
    for i in ids:
        b = bat.setdefault(r2[i].get("batch_index"),
                           {"s": r2[i].get("batch_seconds"), "c": []})
        b["c"].append(L2[i])
    X = [max(v["c"]) for v in bat.values()]
    Y = [v["s"] for v in bat.values()]
    A, B, R2 = linfit(X, Y)
    print("\n2. BATCH COST — fitted on %d measured canary-2 batches" % len(X))
    print("   seconds = %.4f + %.6f x max(member chars)     R2 = %.3f" % (A, B, R2))
    print("   shipped constants: %.4f + %.6f  (worker.BATCH_SECONDS_*)"
          % (W.BATCH_SECONDS_INTERCEPT, W.BATCH_SECONDS_PER_CHAR))
    for k, v in (("intercept_s", A), ("seconds_per_char", B), ("r2", R2)):
        out.append({"section": "batch_cost", "name": k, "value": round(v, 6),
                    "unit": "fit", "n": len(X)})
    # a sum-based model, for the record: it fits worse, which is the mechanism
    _a, _b, r2sum = linfit([sum(v["c"]) for v in bat.values()], Y)
    print("   the same fit on SUM(chars) instead of MAX: R2 = %.3f — max is the mechanism"
          % r2sum)
    out.append({"section": "batch_cost", "name": "r2_if_sum_not_max", "value": round(r2sum, 4),
                "unit": "fit", "n": len(X)})

    # ── 4. runaways (before 3, because 3 reports a runaway-free variant) ────────────────
    print("\n4. RUNAWAYS — repetition loops truncated at max_new_tokens")
    caught = {}
    for tag, L in (("canary1", L1), ("canary2", L2)):
        src = r1 if tag == "canary1" else r2
        det = {i for i in ids if W.degeneracy_of(src[i].get("latex") or "")[0]}
        caught[tag] = det
        print("   %s: %d/%d flagged by the shipped detector (repeated tail only)"
              % (tag, len(det), len(ids)))
        out.append({"section": "runaway", "name": tag + "_detected", "value": len(det),
                    "unit": "rows", "n": len(ids)})
    both = caught["canary1"] & caught["canary2"]
    same = {i for i in both if (r1[i].get("latex") or "") == (r2[i].get("latex") or "")}
    print("   flagged in BOTH runs: %d, of which %d are byte-identical in both —" % (len(both), len(same)))
    print("   those %d are invisible to any stability check, which is why the degeneracy"
          % len(same))
    print("   guard exists as a separate test rather than as a second re-decode.")
    out.append({"section": "runaway", "name": "identical_in_both", "value": len(same),
                "unit": "rows", "n": len(ids)})
    differ = [i for i in ids if (r1[i].get("latex") or "") != (r2[i].get("latex") or "")]
    print("   canary1 vs canary2: %d/%d rows differ" % (len(differ), len(ids)))
    out.append({"section": "stability", "name": "rows_differing_c1_vs_c2",
                "value": len(differ), "unit": "rows", "n": len(ids)})
    long_ids = [i for i in ids if L1[i] >= W.REDECODE_LONG_CHARS]
    long_diff = [i for i in long_ids if i in differ]
    print("   of the %d rows >= %d chars, %d differ (%.0f%%); of the %d under 200, %d (%.0f%%)"
          % (len(long_ids), W.REDECODE_LONG_CHARS, len(long_diff),
             100.0 * len(long_diff) / max(1, len(long_ids)),
             len([i for i in ids if L1[i] < 200]),
             len([i for i in differ if L1[i] < 200]),
             100.0 * len([i for i in differ if L1[i] < 200])
             / max(1, len([i for i in ids if L1[i] < 200]))))

    # ── 3. slice balance, by simulation on the measured timings ─────────────────────────
    def simulate(rank, label, lengths, batch_max=False, mode="lpt"):
        """`rank` orders the crops and `batch_max` says how the PLANNER costs a batch — sum,
        as the old planner did, or max, as `batch_costs` now does. `lengths` is the emitted
        length the batch is TRULY charged for, and comes from the measured run."""
        order = sorted(ids, key=lambda c: (-rank(c), c))
        plan = [order[i:i + BATCH_SIZE] for i in range(0, len(order), BATCH_SIZE)]
        pcost = [(max(rank(c) for c in b) if batch_max else sum(rank(c) for c in b))
                 for b in plan]
        true = [A + B * max(lengths.get(c, 0) for c in b) for b in plan]
        who = W.assign_batches(pcost, N_SLICES, mode=mode)
        load = [0.0] * N_SLICES
        for bi in range(len(plan)):
            load[who[bi]] += true[bi]
        hi, lo = max(load), min(load)
        print("   %-42s slowest %6.1f s  fastest %6.1f s  %5.2fx  total %6.1f s"
              % (label, hi, lo, hi / lo if lo else 0, sum(true)))
        out.append({"section": "balance", "name": label, "value": round(hi, 1),
                    "unit": "slowest_slice_seconds", "n": len(ids)})
        out.append({"section": "balance", "name": label + " [ratio]",
                    "value": round(hi / lo, 3) if lo else None,
                    "unit": "slowest_over_fastest", "n": len(ids)})
        return hi

    def old(c):
        g = geo[c]
        return g["w"] * (g["ink"] / float(g["w"] * g["h"])) if g["w"] and g["h"] else 0.0

    def new(c):
        return W.predicted_seconds(geo[c]["ink"])

    tamed = dict(L2)
    for i in caught["canary2"]:
        tamed[i] = min(tamed[i], 1200)     # what a non-degenerate decode of that region cost

    print("\n3. SLICE BALANCE — SIMULATION on the fitted model of canary-2's MEASURED")
    print("   batch seconds. N=%d slices, batch_size=%d. Not a run." % (N_SLICES, BATCH_SIZE))
    print("   measured canary-2 actual: slowest 315.03 s, fastest 110.46 s = 2.85x")
    simulate(old, "OLD proxy + LPT  [what canary 2 ran]", L2)
    simulate(new, "NEW proxy + LPT", L2, batch_max=True)
    simulate(new, "NEW proxy + DEAL  [what ships]", L2, batch_max=True, mode="deal")
    simulate(old, "OLD proxy + DEAL", L2, mode="deal")
    simulate(lambda c: float(L2.get(c, 0)), "ORACLE: the actual emitted lengths", L2,
             batch_max=True)
    print("   and with the degeneracy guard's runaways removed from the length mix:")
    simulate(old, "OLD proxy + LPT, runaways tamed", tamed)
    simulate(new, "NEW proxy + DEAL, runaways tamed", tamed, batch_max=True, mode="deal")
    simulate(lambda c: float(tamed.get(c, 0)), "ORACLE, runaways tamed", tamed,
             batch_max=True)

    # ── 5. the corpus projection, with the guard's real (time-weighted) overhead ────────
    print("\n5. CORPUS PROJECTION — %d crops" % CORPUS_CROPS)
    total = sum(A + B * max(L2.get(c, 0) for c in b)
                for b in [ids[i:i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)])
    sample = W.stability_sample([{"crop_id": i} for i in ids], "canary200")
    # a row already ruled degenerate is never re-decoded: it is out of the corpus anyway, and
    # those are the runaways, i.e. the dearest crops in the shard.
    re_ids = sorted((set(sample) | {i for i in ids if L2[i] >= W.REDECODE_LONG_CHARS})
                    - caught["canary2"])
    print("   (%d rows are skipped as already-degenerate — they are the runaways)"
          % len((set(sample) | {i for i in ids if L2[i] >= W.REDECODE_LONG_CHARS})
                & caught["canary2"]))
    # a re-decode is ALONE, so it costs a whole batch of one at that row's own length
    re_cost = sum(A + B * L2[i] for i in re_ids)
    print("   rows re-decoded by the guard: %d of %d (%.1f%%) — %d sampled, %d long"
          % (len(re_ids), len(ids), 100.0 * len(re_ids) / len(ids), len(sample),
             len([i for i in ids if L2[i] >= W.REDECODE_LONG_CHARS])))
    print("   THE OVERHEAD IS TIME-WEIGHTED, NOT COUNT-WEIGHTED: the long rows are the")
    print("   expensive ones, so %.1f%% of the rows cost %.1f%% of the decode."
          % (100.0 * len(re_ids) / len(ids), 100.0 * re_cost / total))
    out.append({"section": "projection", "name": "guard_rows_pct",
                "value": round(100.0 * len(re_ids) / len(ids), 2), "unit": "percent",
                "n": len(ids)})
    out.append({"section": "projection", "name": "guard_time_pct",
                "value": round(100.0 * re_cost / total, 2), "unit": "percent", "n": len(ids)})
    rate = 0.4555          # measured aggregate, canary 2 §4.1
    base_h = CORPUS_CROPS / rate / 3600.0
    print("   at canary 2's measured 0.4555 regions/s the corpus is %.2f h;" % base_h)
    print("   with the guard, x%.3f = %.2f h" % (1 + re_cost / total,
                                                 base_h * (1 + re_cost / total)))
    for k, v in (("corpus_hours_no_guard", base_h),
                 ("corpus_hours_with_guard", base_h * (1 + re_cost / total))):
        out.append({"section": "projection", "name": k, "value": round(v, 3),
                    "unit": "hours", "n": CORPUS_CROPS})

    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)) or ".", exist_ok=True)
        with open(a.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["section", "name", "value", "unit", "n"])
            w.writeheader()
            w.writerows(out)
        print("\nwrote %s (%d rows)" % (a.csv, len(out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
