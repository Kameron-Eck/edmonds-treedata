"""Run pix2tex on the bounded bulk sample (venv-pix2tex, GPU)."""
import json
import time

from PIL import Image
from munch import Munch

from pix2tex.cli import LatexOCR

JOINED = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\bulk_sample_joined.json"
OUT = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\pix2tex_bulk_predictions.json"

args = Munch({"config": "settings/config.yaml", "checkpoint": "checkpoints/weights.pth",
              "no_cuda": False, "no_resize": False})
model = LatexOCR(args)
print("device:", model.args.device)

rows = json.load(open(JOINED, encoding="utf-8"))
out = []
t0 = time.time()
for i, r in enumerate(rows):
    img = Image.open(r["crop_path"])
    try:
        pred = model(img)
    except Exception as e:  # noqa: BLE001 -- record the failure, keep going
        pred = None
        print(r["crop_id"], "ERROR", type(e).__name__, str(e)[:120])
    out.append({"crop_id": r["crop_id"], "pix2tex": pred})
    if (i + 1) % 25 == 0:
        print(f"{i+1}/{len(rows)} done, elapsed {round(time.time()-t0,1)}s")

print("total wall time:", round(time.time() - t0, 2), "s over", len(rows))
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print("wrote", OUT)
