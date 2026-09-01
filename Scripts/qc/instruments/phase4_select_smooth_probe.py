"""What would --select-smooth K have deployed, for arms already trained?

An INSTRUMENT (re-runnable, read-only). Usage:
    py -3.12 qc/instruments/phase4_select_smooth_probe.py rgb3_nodeb nodec_v1 ...
Args are run tags; it reads {MODELS}/sem_loss_history_2009_{tag}.csv.

Replays _SmoothCkptSelector's rule offline against each arm's saved loss
history: centred moving average WITHIN a phase, winners compared across
phases with strict > in A-then-B order (exactly core.py's logic).
No GPU, no weights - this only answers WHICH EPOCH each K picks.
"""
import csv, sys
from pathlib import Path

M = Path(r"G:/My Drive/treedata/phase4/models")

def cma(vals, k):
    if k <= 1: return [float(v) for v in vals]
    half, n, out = k // 2, len(vals), []
    for i in range(n):
        w = vals[max(0, i - half):min(n, i + half + 1)]
        out.append(sum(w) / len(w))
    return out

def pick(rows, k):
    best = None                       # (smoothed, phase, epoch, raw)
    for ph in ("A", "B"):
        ser = [r for r in rows if r["phase"] == ph]
        if not ser: continue
        raw = [float(r.get("es_val") or r["val_iou_bt"]) for r in ser]
        sm = cma(raw, k)
        for i, r in enumerate(ser):
            if best is None or sm[i] > best[0]:
                best = (sm[i], ph, int(r["epoch"]), raw[i])
    return best

for name in sys.argv[1:]:
    p = M / f"sem_loss_history_2009_{name}.csv"
    if not p.exists():
        print(f"{name:16s} MISSING {p.name}"); continue
    rows = list(csv.DictReader(p.open()))
    nA = sum(1 for r in rows if r["phase"] == "A")
    nB = sum(1 for r in rows if r["phase"] == "B")
    print(f"\n=== {name}  (A:{nA} ep, B:{nB} ep, metric={rows[0].get('es_metric','val_iou_bt')}) ===")
    base = None
    for k in (1, 3, 5, 7):
        sm, ph, ep, raw = pick(rows, k)
        if k == 1: base = (ph, ep)
        flag = "" if (ph, ep) == base else "   <-- DIFFERENT EPOCH"
        print(f"  K={k}: deploy phase {ph} epoch {ep:2d}   raw es={raw:.4f}  smoothed={sm:.4f}{flag}")
    # how noisy is the curve near the raw peak?
    for ph in ("A", "B"):
        ser = [float(r.get("es_val") or r["val_iou_bt"]) for r in rows if r["phase"] == ph]
        if len(ser) < 3: continue
        d = [abs(ser[i+1]-ser[i]) for i in range(len(ser)-1)]
        print(f"  phase {ph}: peak={max(ser):.4f} at ep{ser.index(max(ser))+1}, "
              f"mean |epoch-to-epoch delta|={sum(d)/len(d):.4f}, "
              f"top5 spread={max(sorted(ser)[-5:])-min(sorted(ser)[-5:]):.4f}")
