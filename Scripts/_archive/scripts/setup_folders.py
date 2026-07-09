#!/usr/bin/env python3
"""Creates the Full_Image directory tree. Run once in Colab."""
import os

BASE = "/content/drive/MyDrive/treedata/Full_Image"

FOLDERS = [
    "Edmonds",      # 5 files: 2015, 2017, 2020, 2022, 2024
    "KingCo",       # 14 files: 1936-2023
    "SnoCo",        # 21 files: 1990-2024
    "WA_NAIP",      # 12 files: 1989-2000 BW, 2003-2017, 2019, 2023
    "NOAA",         # 7 files: rgb/cir/4band 8/16bit + ir
    "USGS",         # 2 files: NAIPPlus, NAIPImagery
    "Esri_NAIP",    # 1 file: latest composite
    "USDA_NRCS",    # 2 files: NHAP, NHAP colorbalance
    "WA_DNR",       # 1 file: nearshore 2022
]

for f in FOLDERS:
    path = os.path.join(BASE, f)
    os.makedirs(path, exist_ok=True)
    print(f"  ✓ {path}")

print(f"\nCreated {len(FOLDERS)} folders under {BASE}")
