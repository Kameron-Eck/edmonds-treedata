"""Bounded random sample of the 7,164 L4 formula crops for a pix2tex vs CodeFormula
agreement-rate check (no gold here -- agreement only, per Item 3 step 4).

Population: D:\\edmonds-pipeline\\litkb_derived\\formula\\latex_formula_colab_full.jsonl
(7,164 rows, one per crop, fields include crop_id, shard_id, file, page, latex).
Crop PNGs live in litkb_derived/formula/shards_full/shard_{shard_id}.zip under crops/{crop_id}.png.

Sample: N=200, random.Random(seed).sample over the row-index population, seed recorded so the
draw is reproducible. Restricted to rows whose latex_status the ingest would call 'ok'-shaped
is NOT applied here -- deliberately unfiltered, since the point is the AGREEMENT RATE on the
population pix2tex would actually see, not a pre-cleaned subset.
"""
import json
import os
import random
import zipfile

REPO_DERIVED = r"D:\edmonds-pipeline\litkb_derived\formula"
POP_PATH = os.path.join(REPO_DERIVED, "latex_formula_colab_full.jsonl")
SHARDS_DIR = os.path.join(REPO_DERIVED, "shards_full")
OUT_DIR = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\crops_bulk"
OUT_JSON = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\bulk_sample_joined.json"
SEED = "litkb-item3-pix2tex-bulk-2026-09-19"
N = 200

def main():
    rows = []
    with open(POP_PATH, encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    print(f"population: {len(rows)} rows")
    rng = random.Random(SEED)
    sample = rng.sample(rows, min(N, len(rows)))
    os.makedirs(OUT_DIR, exist_ok=True)
    # group by shard to open each zip once
    by_shard = {}
    for r in sample:
        by_shard.setdefault(r["shard_id"], []).append(r)
    out = []
    missing = 0
    for shard_id, items in by_shard.items():
        zpath = os.path.join(SHARDS_DIR, f"shard_{shard_id}.zip")
        with zipfile.ZipFile(zpath) as z:
            for r in items:
                cid = r["crop_id"]
                member = f"crops/{cid}.png"
                try:
                    data = z.read(member)
                except KeyError:
                    missing += 1
                    print(f"MISSING {member} in {zpath}")
                    continue
                out_path = os.path.join(OUT_DIR, f"{cid}.png")
                with open(out_path, "wb") as fh:
                    fh.write(data)
                out.append({
                    "crop_id": cid, "shard_id": shard_id, "file": r["file"], "page": r["page"],
                    "codeformula_latex": r["latex"], "crop_path": out_path,
                })
    print(f"extracted {len(out)} crops, missing {missing}")
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("wrote", OUT_JSON)

if __name__ == "__main__":
    main()
