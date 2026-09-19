"""Run pix2tex on the 20 rendered gold crops. Runs inside venv-pix2tex (GPU, T2000)."""
import json
import time

from PIL import Image
from munch import Munch

from pix2tex.cli import LatexOCR

GOLD_JOINED = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\gold_equations_joined.json"
OUT = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\pix2tex_gold_predictions.json"

args = Munch({"config": "settings/config.yaml", "checkpoint": "checkpoints/weights.pth",
              "no_cuda": False, "no_resize": False})
t0 = time.time()
model = LatexOCR(args)
print("model device:", model.args.device, "load_s:", round(time.time() - t0, 2))

import torch
if torch.cuda.is_available():
    torch.cuda.reset_peak_memory_stats()

rows = json.load(open(GOLD_JOINED, encoding="utf-8"))
out = []
t_total0 = time.time()
for r in rows:
    img = Image.open(r["crop_path"])
    t0 = time.time()
    pred = model(img)
    dt = time.time() - t0
    out.append({"id": r["id"], "pix2tex": pred, "seconds": round(dt, 3)})
    print(r["id"], round(dt, 3), "s ->", pred[:80])

if torch.cuda.is_available():
    peak = torch.cuda.max_memory_allocated() / (1024 ** 2)
    peak_reserved = torch.cuda.max_memory_reserved() / (1024 ** 2)
    print(f"peak CUDA allocated: {peak:.1f} MiB, peak reserved: {peak_reserved:.1f} MiB")

print("total inference wall time:", round(time.time() - t_total0, 2), "s over", len(rows))
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print("wrote", OUT)
