r"""Noise-ensemble experiment (2026-08-27): mean of the five same-recipe 2021s
noise repeats -> one lower-variance prob raster, scored like any arm.

Conventions copied from qc/phase4_qc_indep.py: uint8 DN, prob = DN/254,
nodata = 255. Ensemble valid = intersection (nodata where ANY input is nodata).
Local-write-then-copy per the repo discipline. LABEL: tag noise_ens5 via the
output filename (the fixed run_tag parser derives the tag from it).
"""
import shutil
from pathlib import Path

import numpy as np
import rasterio

MASKS = Path(r"G:/My Drive/treedata/phase4/masks")
LOCAL = Path(r"D:/edmonds-pipeline/_tmp/noise_ens5")
OUT_NAME = "edmonds_canopy_prob_2021s_noise_ens5.tif"
SRCS = [MASKS / f"edmonds_canopy_prob_2021s_noise_r{i}.tif" for i in range(1, 6)]

LOCAL.mkdir(parents=True, exist_ok=True)
out_local = LOCAL / OUT_NAME

handles = [rasterio.open(p) for p in SRCS]
prof = handles[0].profile.copy()
for h in handles[1:]:
    assert h.shape == handles[0].shape and h.transform == handles[0].transform, \
        f"grid mismatch: {h.name}"
prof.update(compress="lzw")

BLOCK = 1024
H, W = handles[0].shape
valid_counts = [0] * 5
ens_valid = 0
with rasterio.open(out_local, "w", **prof) as dst:
    for r0 in range(0, H, BLOCK):
        rows = min(BLOCK, H - r0)
        win = rasterio.windows.Window(0, r0, W, rows)
        stack = np.stack([h.read(1, window=win) for h in handles])   # (5, rows, W)
        valid = np.all(stack != 255, axis=0)
        for i in range(5):
            valid_counts[i] += int((stack[i] != 255).sum())
        ens_valid += int(valid.sum())
        mean = np.zeros(stack.shape[1:], dtype=np.uint8)
        if valid.any():
            m = stack[:, valid].astype(np.float32).mean(axis=0)
            mean[valid] = np.clip(np.rint(m), 0, 254).astype(np.uint8)
        mean[~valid] = 255
        dst.write(mean, 1, window=win)
for h in handles:
    h.close()

total = H * W
print(f"ensemble valid px: {ens_valid:,} ({ens_valid/total:.2%} of grid)")
for i, c in enumerate(valid_counts, 1):
    print(f"  r{i} valid: {c:,}")
print(f"intersection loss vs min single: {min(valid_counts) - ens_valid:,} px")

dst_path = MASKS / OUT_NAME
shutil.copy2(out_local, dst_path)
got = dst_path.stat().st_size
want = out_local.stat().st_size
assert got == want, f"copy size mismatch {got} != {want}"
print(f"-> {dst_path}  ({got:,} B, size-verified)")
