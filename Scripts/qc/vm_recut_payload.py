"""Recut payload: nohup-chained postproc at the policy-C cuts (torch-free).
Reads /content/RECUT_ARMS lines: year tag thresh"""
import subprocess
REPO = "/content/repo/Scripts"
arms = []
with open("/content/RECUT_ARMS", encoding="utf-8") as f:
    for ln in f:
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            y, t, th = ln.split()
            arms.append((y, t, th))
chain = " && ".join(
    f"python -u {REPO}/pipeline/phase4_semantic_finetune.py --year {y} "
    f"--step postproc --run-tag {t} --force-citywide --infer-thresh {th} "
    f">> /content/drive/MyDrive/treedata/phase4/logs/recut_{y}_{t}.log 2>&1" for y, t, th in arms)
subprocess.Popen(["bash", "-c", f"nohup bash -c \"{chain}\" > /content/drive/MyDrive/treedata/phase4/logs/recut_chain.log 2>&1 &"])
print(f"RECUT_CHAIN_LAUNCHED {len(arms)} arms")
