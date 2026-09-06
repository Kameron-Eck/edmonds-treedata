"""Sweep-batch payload for CPU scoring VMs (exec-by-path via vm_ops exec).

Reads its arm list from /content/SWEEP_ARMS (one 'year tag' per line, written
by a tiny exec preamble or a sibling payload variant), and nohup-detaches one
qc/phase4_qc_indep.py run per arm SEQUENTIALLY via a shell chain — the exec
returns immediately; the patched bootstrap watchdog recognizes phase4_qc_indep
processes as work and self-stops 10 min after the last one exits.
Citywide sweeps, ccap_2021 reference, thresh 0.5 (the dense sweep is the
product; the deployed cut comes later from select_indep_threshold).
"""
import subprocess

REPO = "/content/repo/Scripts"
BASE = "/content/drive/MyDrive/treedata"
REF = f"{BASE}/Full_Image/Pipeline Imagery/ccap_2021_hires_lc.tif"
arms = []
with open("/content/SWEEP_ARMS", encoding="utf-8") as f:
    for ln in f:
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            year, tag = ln.split()
            arms.append((year, tag))
chain = " && ".join(
    f"python -u {REPO}/qc/phase4_qc_indep.py --year {y} "
    f"--prob '{BASE}/phase4/masks/edmonds_canopy_prob_{y}_{t}.tif' "
    f"--ref '{REF}' --thresh 0.5 "
    f">> /content/sweep_{y}_{t}.log 2>&1" for y, t in arms)
subprocess.Popen(["bash", "-c", f"nohup bash -c \"{chain}\" "
                  f"> /content/sweep_chain.log 2>&1 &"])
print(f"SWEEP_CHAIN_LAUNCHED {len(arms)} arms: " +
      ", ".join(t for _, t in arms))
