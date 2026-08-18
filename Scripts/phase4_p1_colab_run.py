"""
╔══════════════════════════════════════════════════════════════════════════╗
  PHASE 4 — P1 COLAB RUN DRIVER   (honest-measurement-overhaul, Phase 1)
  Edmonds Temporal Active Learning Pipeline

  ONE Colab session that produces the two prob rasters P1/P3 are blocked on:
      2022  citywide  → unblocks the Phase-3 stratified sample (250 pts × 3 yr)
      2017  citywide  → replaces the failed run (96.5% nodata)

  ── WHY A DRIVER AND NOT JUST TWO %run LINES ──────────────────────────────
  The 2017 run ALREADY "succeeded" once: its log said "173 MB ✓, 19.3 min"
  and the raster it wrote is unusable. GPU time was spent producing a file
  nobody could score, and the scorer then wrote a nan row that looked like a
  measurement. This driver refuses to repeat that:

    * STAGE 0 costs NO GPU. It checks the ortho, the checkpoint and the disk
      BEFORE any accelerator work, and tells you whether a re-run can even
      help. If the 2017 ORTHO is itself mostly empty, no amount of GPU fixes
      it — the answer is imagery, not compute, and stage 0 says so.
    * Cheap year first (2022, coarse) then expensive (2017, fine), so a
      broken recipe surfaces on the cheap job.
    * Every GPU stage is VERIFIED immediately (valid fraction + prob range).
      A bad raster aborts the run instead of licensing the next hour.
    * Stages are independent and re-runnable; nothing is overwritten
      (--run-tag), so a partial session is never a lost session.

  ── GPU BUDGET (the point of the exercise) ────────────────────────────────
    Training is SKIPPED entirely — sem_best_2017_xsensor_train.pt and
    sem_best_2022_xsensor_train.pt already exist. We run --step inference
    only. That removes the large majority of the GPU cost.

    Pick the CHEAPEST tier that fits: L4 24 GB. --infer-batch 32 is sized
    for it (v047 made inference batch a pure memory knob — output is
    batch-invariant, so a smaller batch changes cost, never results).
    Do NOT select A100/Blackwell for this; there is nothing here that needs
    them.

    Rough expectation: 2022 (60 cm, coarse) minutes. 2017 (≈15 cm, fine) is
    ~30-60 min because the ortho is ~2.1e5 × 1.5e5 px. If 2017 exceeds ~90
    min, stop and re-check rather than letting it burn.

  ── USAGE (Colab, GPU runtime = L4) ───────────────────────────────────────
      %cd /content/drive/MyDrive/treedata/Scripts
      %run phase4_p1_colab_run.py --stage 0            # free; ALWAYS run first
      %run phase4_p1_colab_run.py --stage 1            # 2022 inference (cheap)
      %run phase4_p1_colab_run.py --stage 2            # 2017 inference (costly)
      %run phase4_p1_colab_run.py --stage all          # 0 → 1 → 2, gated

  Read stage 0 before running 1 or 2. If stage 0 reports a problem it will
  refuse to continue under --stage all.

  Outputs land in phase4/masks/ as edmonds_canopy_prob_{year}_{tag}.tif with
  --run-tag p1 (default), so nothing existing is overwritten.
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import datetime as _dt
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

SCRIPTS = BASE / "Scripts"
MASKS   = BASE / "phase4" / "masks"
MODELS  = BASE / "phase4" / "models"
QC_DIR  = BASE / "phase4" / "qc"
IMAGERY = BASE / "Full_Image" / "Pipeline Imagery"
ENGINE  = SCRIPTS / "phase4_semantic_finetune.py"

# The two years P1 needs, cheap first. `tag` selects BOTH the checkpoint
# (sem_best_{year}_{tag}.pt) and the output name — see core.step_inference,
# which keys the ckpt off --run-tag, not off --ckpt.
JOBS = [
    dict(year="2022", ckpt_tag="xsensor_train", why="Phase-3 BLOCKER: no citywide 2022 prob raster exists",
         cost="cheap (coarse ~60 cm)"),
    dict(year="2017", ckpt_tag="xsensor_train", why="replaces the 96.5%-nodata failed run",
         cost="EXPENSIVE (fine ~15 cm)"),
]

MIN_VALID_FRAC = 0.05      # below this a prob raster is a failed run
MIN_MAX_PROB   = 0.50      # below this the model never confidently says canopy


# ══════════════════════════════════════════════════════════════════════════
#  helpers
# ══════════════════════════════════════════════════════════════════════════
def _hr(title=""):
    print("\n" + "═" * 74)
    if title:
        print(f"  {title}")
        print("═" * 74)


def _decimated(path, bands=(1,), h=1500):
    """Sample a raster cheaply.

    Whole-extent `out_shape` decimation still walks every block when the file
    has no overviews, which on a fine ortho (2.1e5 x 1.5e5 px) takes many
    minutes over Drive — unacceptable for a preflight whose whole selling point
    is being fast and free. Use overviews when present, otherwise read a grid of
    small windows, which is O(windows) rather than O(raster).
    """
    with rasterio.open(path) as s:
        bl = list(bands)
        if s.overviews(1):
            w = max(1, int(s.width * h / s.height))
            a = s.read(bl, out_shape=(len(bl), min(h, s.height), w),
                       resampling=Resampling.nearest)
        else:
            n, win = 8, 512                      # 64 windows, ~16M px worst case
            tiles = []
            for r in range(n):
                row = []
                for c in range(n):
                    r0 = min(int((r + 0.5) * s.height / n), max(s.height - win, 0))
                    c0 = min(int((c + 0.5) * s.width / n), max(s.width - win, 0))
                    row.append(s.read(bl, window=Window(c0, r0,
                                                        min(win, s.width),
                                                        min(win, s.height))))
                tiles.append(np.concatenate(row, axis=2))
            a = np.concatenate(tiles, axis=1)
        return a, s.nodata, s.width, s.height, (s.transform.a * 100.0), str(s.crs)


def _ortho_for(year):
    """Native ortho for a year — ASK THE ENGINE, never guess.

    phase4seg.common is torch-free, so this works in preflight without an
    accelerator. Guessing by glob is wrong: 2022 has both 2022_coe_rgb.tif and
    2022_naip_rgbi.tif in the imagery folder, and only the catalog knows which
    one the engine will actually infer over.
    """
    name = None
    try:
        from phase4seg.common import entry_for
        name = entry_for(str(year))["native_file"]
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! could not read the catalog ({e}); falling back to a glob — "
              f"VERIFY the filename below.")
        hits = sorted(IMAGERY.glob(f"{year}*_rgb*.tif"))
        return hits[0] if hits else None

    # Take the FILENAME from the catalog (authoritative) but the ROOT from this
    # script's BASE. phase4seg.config is Colab-rooted, so resolve_native_path()
    # returns /content/... and reports MISSING when preflight is exercised on the
    # local Windows mount — a false alarm that would train you to ignore stage 0.
    for d in (IMAGERY / "native", IMAGERY):
        p = d / name
        if p.exists():
            return p
    return IMAGERY / name          # canonical path, for a clear error message


def gpu_report():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        out = ""
    if not out:
        print("  GPU: NONE VISIBLE — set Runtime ▸ Change runtime type ▸ GPU (L4).")
        return None
    print(f"  GPU: {out}")
    low = out.lower()
    if "a100" in low or "h100" in low or "blackwell" in low or "6000" in low:
        print("  ! You are on a PREMIUM tier. Nothing in this run needs it — inference")
        print("    at --infer-batch 32 fits a 24 GB L4. Switch down and save the credits.")
    return out


def disk_report():
    try:
        du = shutil.disk_usage("/content" if _COLAB_BASE.exists() else ".")
        free = du.free / 1e9
        print(f"  Local disk free: {free:.1f} GB")
        if free < 30:
            print("  ! Under 30 GB free. A fine-year run stages the ortho locally "
                  "(rule 3: local-then-copy) and may not fit.")
        return free
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
#  STAGE 0 — preflight. No GPU. Decides whether GPU work can even help.
# ══════════════════════════════════════════════════════════════════════════
def stage0():
    _hr("STAGE 0 — PREFLIGHT (no GPU spent)")
    ok = True

    print("\nEnvironment")
    gpu_report()
    disk_report()
    if not ENGINE.exists():
        print(f"  ! engine missing: {ENGINE}")
        ok = False

    for job in JOBS:
        y, tag = job["year"], job["ckpt_tag"]
        _hr(f"{y} — {job['why']}   [{job['cost']}]")

        ck = MODELS / f"sem_best_{y}_{tag}.pt"
        if ck.exists():
            print(f"  ckpt   OK   {ck.name}  ({ck.stat().st_size/1e6:.0f} MB)")
            print(f"         → training will be SKIPPED (this is the GPU saving)")
        else:
            print(f"  ckpt   MISSING  {ck}")
            print(f"         → would require a full --step train. Do not proceed blind.")
            ok = False
            continue

        ortho = _ortho_for(y)
        if ortho is None or not ortho.exists():
            print(f"  ortho  MISSING for {y}: {ortho}")
            ok = False
            continue
        try:
            a, nd, W, H, gsd, crs = _decimated(ortho, bands=(1, 2, 3))
            cover = float(((a[0].astype(np.int32) + a[1] + a[2]) > 0).mean())
            print(f"  ortho  {ortho.name}  {W}×{H}  GSD≈{gsd:.1f}cm  {crs}")
            print(f"         imagery cover {cover:.1%}")
            if cover < 0.20:
                print(f"  ! THE ORTHO ITSELF IS {1-cover:.0%} EMPTY.")
                print(f"    Re-running inference CANNOT fix this — the model would be")
                print(f"    predicting into blank pixels. The problem is the imagery,")
                print(f"    not the compute. Do NOT spend GPU on {y} until this is")
                print(f"    resolved (re-fetch / re-mosaic the {y} ortho).")
                ok = False
        except Exception as e:                                  # noqa: BLE001
            print(f"  ortho  UNREADABLE: {type(e).__name__}: {e}")
            ok = False

        prior = sorted(MASKS.glob(f"edmonds_canopy_prob_{y}*.tif"))
        if prior:
            print("  existing rasters for this year (none will be overwritten):")
            for p in prior:
                mb = p.stat().st_size / 1e6
                if mb == 0:
                    print(f"         {p.name:<50} 0 MB  EMPTY")
                    continue
                try:
                    d, ndp, _, _, _, _ = _decimated(p)
                    vf = float((d[0] != (255 if ndp is None else ndp)).mean())
                    print(f"         {p.name:<50} {mb:7.0f} MB  valid {vf:5.1%}")
                except Exception:
                    print(f"         {p.name:<50} {mb:7.0f} MB  (unreadable)")

    _hr("STAGE 0 VERDICT")
    print("  READY — stages 1 and 2 may run." if ok else
          "  NOT READY — fix the items marked ! above. Do not spend GPU.")
    return ok


# ══════════════════════════════════════════════════════════════════════════
#  GPU stages
# ══════════════════════════════════════════════════════════════════════════
def verify_output(year, tag):
    """Immediately check what the GPU produced. Bad raster ⇒ abort the run."""
    out = MASKS / f"edmonds_canopy_prob_{year}_{tag}.tif"
    print(f"\n  verifying {out.name}")
    if not out.exists():
        print("  ! FAIL: no output raster written.")
        return False
    mb = out.stat().st_size / 1e6
    if mb == 0:
        print("  ! FAIL: output is 0 bytes (this is the 2022 failure mode — a copy/")
        print("    sync failure. The log may still say it wrote fine).")
        return False
    try:
        a, nd, W, H, _, _ = _decimated(out)
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! FAIL: unreadable ({type(e).__name__}: {e})")
        return False
    valid = a[0] != (255 if nd is None else nd)
    vf = float(valid.mean())
    mx = float(a[0][valid].max()) / 254.0 if valid.any() else float("nan")
    print(f"    {mb:.0f} MB  {W}×{H}  valid {vf:.1%}  max prob {mx:.3f}")
    if vf < MIN_VALID_FRAC:
        print(f"  ! FAIL: {1-vf:.1%} nodata — this is the 2017 failure mode repeating.")
        print("    STOP. Do not run the next stage; diagnose before spending more GPU.")
        return False
    if mx == mx and mx < MIN_MAX_PROB:
        print(f"  ! FAIL: max prob {mx:.3f} — the model never confidently predicts")
        print("    canopy anywhere. The raster is technically full but useless.")
        return False
    print("    PASS")
    return True


def run_job(job, infer_batch, run_tag, extra=()):
    y, tag = job["year"], job["ckpt_tag"]
    _hr(f"{y} — citywide inference   [{job['cost']}]")
    print(f"  {job['why']}")
    print(f"  training SKIPPED (reusing sem_best_{y}_{tag}.pt)")

    # NOTE: core.step_inference keys the CHECKPOINT off --run-tag, so the tag
    # must match the existing ckpt. Output therefore also carries that tag.
    cmd = [sys.executable, str(ENGINE), "--year", y, "--step", "inference",
           "--infer-batch", str(infer_batch), "--run-tag", tag, *extra]
    print(f"  $ {' '.join(cmd[1:])}")
    t0 = _dt.datetime.now()
    r = subprocess.run(cmd, cwd=str(SCRIPTS))
    mins = (_dt.datetime.now() - t0).total_seconds() / 60
    print(f"\n  exit={r.returncode}  elapsed {mins:.1f} min")
    if r.returncode != 0:
        print("  ! engine returned non-zero — not verifying, not continuing.")
        return False
    return verify_output(y, tag)


def main():
    # Colab injects `-f <json>`; strip it (rule 4). ALSO strip shell-style
    # comments: IPython's %run does NOT parse `#` as a comment, so a pasted
    # `--stage 0   # preflight` arrives as argv and argparse dies on it.
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a.startswith("#"):
            argv = argv[:i]
            break
    filtered = [a for a in argv if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(
        description="P1 Colab driver — citywide 2022 + 2017 inference, GPU-mindful.")
    ap.add_argument("--stage", default="0",
                    help="0 = preflight (free), 1 = 2022, 2 = 2017, all = gated 0→1→2.")
    ap.add_argument("--infer-batch", type=int, default=32,
                    help="Inference batch (default 32, sized for a 24 GB L4). "
                         "Pure memory knob — output is batch-invariant.")
    ap.add_argument("--run-tag", default=None,
                    help="Override the run tag. Default = each job's ckpt tag, which "
                         "is what selects the checkpoint. Change only if you know why.")
    ap.add_argument("--force", action="store_true",
                    help="Run GPU stages even if preflight failed. Spends GPU on a "
                         "job preflight believes cannot succeed.")
    args = ap.parse_args(filtered)

    print(f"[p1-run] BASE={BASE}")
    stage = str(args.stage).lower()

    if stage in ("0", "all"):
        ok = stage0()
        if stage == "0":
            if ok:
                print("\nNext:  %run phase4_p1_colab_run.py --stage 1")
                print("       (2022, cheap. Then --stage 2 for 2017.)")
            else:
                print("\nDo NOT run --stage 1 or 2 yet. Fix the ! items above first —")
                print("spending GPU now would repeat the failure this driver exists to stop.")
            return
        if not ok and not args.force:
            print("\n[p1-run] STOPPING — preflight failed. Re-run with --force only if "
                  "you have read why and still want to spend the GPU.")
            raise SystemExit(2)

    todo = {"1": [JOBS[0]], "2": [JOBS[1]], "all": JOBS}.get(stage)
    if todo is None:
        raise SystemExit(f"unknown --stage {args.stage!r} (use 0, 1, 2 or all)")

    for job in todo:
        if not run_job(job, args.infer_batch, args.run_tag):
            print(f"\n[p1-run] ABORTING after {job['year']} — output failed verification.")
            print("[p1-run] Nothing further will run. Later stages are unaffected and")
            print("[p1-run] can be resumed once this is diagnosed.")
            raise SystemExit(2)

    _hr("DONE")
    print("  Verified rasters written. Next, LOCALLY (no GPU needed):")
    print("    py -3.12 phase4_qc_inventory.py --glob 'edmonds_canopy_prob_*.tif'")
    for job in todo:
        y, tag = job["year"], job["ckpt_tag"]
        print(f"    py -3.12 phase4_qc_indep.py --year {y} "
              f"--ref <ccap>.tif --prob "
              f"{MASKS.name}/edmonds_canopy_prob_{y}_{tag}.tif")
    print("\n  Then add a run_registry.csv row per rule 9, and update CHATLOG STATE.")


if __name__ == "__main__":
    main()
