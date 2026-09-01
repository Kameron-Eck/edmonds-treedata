r"""
╔══════════════════════════════════════════════════════════════════╗
  DEGRADATION SYNTHESIS — Phase A tool (plan item 4.5)
  Push a well-labelled acquisition to a target acquisition's LOOK.

  WHAT THIS PRODUCES AND WHAT IT IS FOR
  ------------------------------------------------------------------
  Training imagery for a year that has few good labels, built from a year that
  has many: take the source acquisition, resample it to the target's ground
  sample distance, apply the measured radiometric map, and carry the source's
  mask through unchanged. The mask is exact for the synthetic image because the
  geometry never moves — only the sampling and the colour do.

  READ qc/instruments/radiometry_norm.py's DOCSTRING FIRST. It is the authority on the map
  this script applies, it is unusually careful, and three claims about it were
  wrong in this project's own plan until 2026-08-31. Everything below is
  downstream of it.

  ══ THE POLICY THIS SCRIPT OPERATES UNDER ════════════════════════════════
  radiometry_norm.normalize_array carries a POLICY block that forbids wiring
  normalization into "phase4seg tiling or training input". That is not a
  contradiction of this tool, but the distinction is the whole safety argument
  and it must not be blurred:

      FORBIDDEN — take year Y's REAL imagery, normalize it onto the reference,
                  and train on the result. Y's DNs have been silently rewritten
                  and no artifact says so.

      THIS TOOL — take the SOURCE year's imagery, push it to Y's look, and write
                  a NEW file that announces itself as synthetic in its filename,
                  its band descriptions and its tags. Nothing real is rewritten.

  The policy's positive requirement applies in full: "Every product built with
  this function must NAME it — in the filename, the band description, and the
  README. If a reader cannot tell from the artifact alone whether it was
  normalized, the artifact is wrong." So every output here is named
  `synth_{source}_as_{target}...`, every band description says so, and the
  GeoTIFF carries tags recording source, target, coefficients and this script.
  ═════════════════════════════════════════════════════════════════════════

  ORDER OF OPERATIONS — RESAMPLE FIRST, AND THE REASON IS NOT COSMETIC
  ------------------------------------------------------------------
  radiometry_norm's header records that the fitted OFFSET is not a physical
  black point. Much of the ~+70 DN red offset on the coarse years is the
  REFERENCE's sharpness: at 7.6 cm a PIF-masked hardscape pixel is pure
  hardscape, while at 60 cm the same nominal pixel mixes in the shaded edge of
  neighbouring canopy. The offset therefore already CONTAINS the mixing that
  downsampling produces.

  So applying the inverse offset AND downsampling counts that effect twice, and
  the result looks plausible while being wrong — the failure mode this project
  keeps finding. This tool resamples first and then applies GAIN ONLY by
  default, because the same header states the gain is far less affected: "it is
  set by the bright end, where mixing has little to do." `--with-offset` exists
  for deliberate experiments and prints a warning naming this paragraph.

  THE DIRECTION OF THE MAP
  ------------------------------------------------------------------
  The table fits   DN_reference ~= gain * DN_acquisition + offset.
  To make a source look like a TARGET acquisition, go reference-ward from the
  source and acquisition-ward into the target:

      DN_target_look = ( gain_src * DN_src + offset_src - offset_tgt ) / gain_tgt

  With --gain-only (the default) both offsets drop out:

      DN_target_look = ( gain_src / gain_tgt ) * DN_src

  If the source IS the reference (2020s), gain_src = 1 and offset_src = 0 and
  the expression reduces to the plain inverse map, which is what the plan
  described. Sourcing from the 2020 ANCHOR instead would be wrong: the anchor is
  in the table as a TRANSFORMED acquisition, not as the reference.

  NODATA
  ------------------------------------------------------------------
  The project's convention is all-bands-exactly-0. normalize_array's docstring
  warns that a positive offset turns those zeros into a plausible DN,
  "fabricating imagery out of the fill value". The valid mask is therefore taken
  from the RAW pixels before anything is applied, and invalid pixels are written
  back as 0.

  WHAT THIS TOOL DOES NOT CLAIM
  ------------------------------------------------------------------
  · The masks are NOT gold. No hand labels exist in this project: the 2020 mask
    is a model PREDICTION and polygons/ holds accept-all test data. A synthetic
    sample inherits the base model's blind spots, deciduous marsh included.
  · The PSF/blur half of degradation stays APPROXIMATE. The radiometric half is
    measured; the optical half is a resampling kernel standing in for a sensor.
  · The map is fitted on hardscape and is blind to phenology, vignetting,
    within-scene gradient, saturation and non-linearity.

  TWO MODES. `--plan` resolves and reports the transform for a target — coefficients,
  fitted domain, fit RMS against the uncorrected baseline, and which bands the table
  declines to supply — and touches no raster. `--src-raster` writes one synthetic window.
  Windowed by design: 2020s is a 31 GB ortho, and tile-sized synthesis is what training
  data actually needs; a whole-ortho pass is a Colab job, not a laptop one.

  Measured while building it, and it picks the A/B year: fit quality varies a lot across
  the archive, and 2000 — the weakest, oldest year — has the BEST fit in the sample
  (red RMS 5.75 against 47.37 uncorrected, an 8x improvement), against 2005 at 13.3/20.4
  and 2019n at 17.3/42.3. The plan calls for "a weak early year" for the A/B; 2000 is both
  weak and unusually well characterised, which is the combination that makes an A/B
  interpretable.

  HOW SYNTHETIC TILES MUST ENTER TRAINING — AND THE LEAKAGE THAT WOULD NOT ANNOUNCE ITSELF
  ------------------------------------------------------------------
  core.py::step_train reads ONE index, `tile_index_{label}.csv`, and selects on its
  `split` column. So synthetic samples enter by APPENDING ROWS to that index — no catalog
  surgery, no new acquisition, no re-tile of the real year. Columns are
  tile_name, site, split, row_off, col_off, canopy_frac, block, split_mode, img_path,
  mask_path, height_path.

  Three requirements, and the third is the one that would silently ruin the experiment:

  1. `split` MUST be "train" for every synthetic row. A synthetic tile in val or test
     means the model is being SCORED on imagery it was handed rather than on the year.
  2. `site` should read "synth" so every downstream reader can separate them. The index is
     consumed by more than step_train.
  3. **SYNTHETIC TILES MUST COME ONLY FROM GROUND IN THE TARGET YEAR'S TRAIN BLOCKS.**
     Measured on a real index: 36 blocks, and NO block holds more than one split — ground
     is partitioned by block and the split follows the block. The synthetic imagery covers
     the SAME GROUND as the real year, so a synthetic tile built over ground that sits in
     a val or test block puts that ground into training WITH BETTER LABELS. The model then
     scores well on held-out blocks it has effectively already seen, the A/B reports a
     gain, and nothing anywhere raises an error.

     This is the same failure the blocked split exists to prevent, arriving through a door
     the split does not watch. Filter candidate ground by the target index's train blocks
     BEFORE synthesising, not after.

  py -3.12 qc/instruments/degrade_synth.py --target 2009 --plan
  py -3.12 qc/instruments/degrade_synth.py --target 2000 --src-raster <2020s.tif>       --window COL ROW W H --out synth_2020s_as_2000.tif
"""
import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]  # instruments/ -> qc/ -> Scripts/

_COLAB = Path("/content/drive/MyDrive/treedata")
BASE = _COLAB if _COLAB.exists() else Path(r"G:\My Drive\treedata")
NORM_CSV = BASE / "phase4" / "qc" / "radiometry_norm.csv"
REPO_NORM = SCRIPTS.parent / "phase4" / "qc" / "radiometry_norm.csv"

BANDS = ("R", "G", "B", "N")


def load_table(path=None):
    """acquisition -> band -> row. Prefers the lake, falls back to the harvested copy."""
    for p in (path, NORM_CSV, REPO_NORM):
        if p and Path(p).exists():
            out = {}
            for r in csv.DictReader(open(p, encoding="utf-8")):
                out.setdefault(r["acquisition"], {})[r["band"]] = r
            return out, Path(p)
    raise SystemExit(f"radiometry_norm.csv not found (looked in {NORM_CSV}, {REPO_NORM})")


def coeffs(table, acq, band):
    """(gain, offset, row) or (None, None, row) when the table declines to emit one.

    A missing coefficient is INFORMATION, not an omission: two acquisitions carry an
    explicit excluded_reason (lifted NIR black point) and the table refuses to invent a
    number rather than pretending the floor was fixed. Callers must not fill it in.
    """
    row = (table.get(acq) or {}).get(band)
    if row is None:
        return None, None, None
    g, o = (row.get("gain") or "").strip(), (row.get("offset") or "").strip()
    if not g or not o:
        return None, None, row
    return float(g), float(o), row


def plan_for(target, source="2020s", table=None, table_path=None):
    """What synthesis to `target` would apply, per band — without touching a raster."""
    if table is None:
        table, table_path = load_table()
    from phase4seg import config as C
    from phase4seg.common import tier_for

    entry = next((e for e in C.YEAR_CATALOG if str(e["label"]) == target), None)
    src_entry = next((e for e in C.YEAR_CATALOG if str(e["label"]) == source), None)
    out = {"source": source, "target": target, "table": str(table_path),
           "target_gsd_cm": entry and float(entry["gsd_cm"]),
           "source_gsd_cm": src_entry and float(src_entry["gsd_cm"]),
           "target_tier": entry and tier_for(entry), "bands": {}}
    for b in BANDS:
        gs, os_, srow = coeffs(table, source, b)
        gt, ot, trow = coeffs(table, target, b)
        note = ""
        if trow is None:
            note = "target has no row for this band"
        elif gt is None:
            note = "NO COEFFICIENT EMITTED: " + (trow.get("excluded_reason") or "")[:90]
        ratio = (gs / gt) if (gs and gt) else ((1.0 / gt) if gt else None)
        out["bands"][b] = {
            "gain_src": gs, "gain_tgt": gt, "offset_src": os_, "offset_tgt": ot,
            "gain_ratio": ratio, "note": note,
            "fit_x_min": trow and trow.get("fit_x_min"),
            "fit_x_max": trow and trow.get("fit_x_max"),
            "fit_quality": trow and trow.get("fit_quality"),
            "pre_rms": trow and trow.get("pre_rms"),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True, help="acquisition to imitate, e.g. 2009")
    ap.add_argument("--source", default="2020s",
                    help="acquisition to transform (default 2020s, THE REFERENCE — not "
                         "the 2020 anchor, which the table holds as a transformed row)")
    ap.add_argument("--plan", action="store_true",
                    help="print what would be applied and exit; touches no raster")
    ap.add_argument("--with-offset", action="store_true",
                    help="also apply the offsets. OFF by default because the offset "
                         "already contains the mixing that resampling reproduces — see "
                         "the ORDER OF OPERATIONS block.")
    ap.add_argument("--src-raster", type=str, default=None,
                    help="source ortho to transform. Omit for --plan.")
    ap.add_argument("--window", type=int, nargs=4, metavar=("COL", "ROW", "W", "H"),
                    default=None, help="source-pixel window; omit for the whole raster "
                                       "(2020s is 31 GB — you want a window)")
    ap.add_argument("--out", type=str, default=None, help="output GeoTIFF")
    ap.add_argument("--passes", type=int, default=0,
                    help="degradation passes. 0 (default) = one clean `average` resample. "
                         "2 = the Real-ESRGAN pattern: blur/resize/noise/JPEG twice with "
                         "independently drawn params, because ONE clean chain is too "
                         "regular and transfers poorly to real degraded imagery.")
    ap.add_argument("--seed", type=int, default=42,
                    help="seed for the chain's draws; the applied params are written into "
                         "the output's tags either way")
    ap.add_argument("--no-jpeg", action="store_true",
                    help="skip the JPEG step of each pass")
    ap.add_argument("--resampling", default="average",
                    choices=["average", "bilinear", "cubic", "nearest"],
                    help="average (default) AGGREGATES, which is what a coarse sensor "
                         "does; nearest sub-samples and gives a sharp image on a coarse "
                         "grid — the look of neither sensor")
    a = ap.parse_args()

    table, tpath = load_table()
    p = plan_for(a.target, a.source, table, tpath)

    print(f"source {p['source']} ({p['source_gsd_cm']} cm nominal)  ->  "
          f"target {p['target']} ({p['target_gsd_cm']} cm nominal, {p['target_tier']})")
    print(f"table: {p['table']}")
    print(f"mode : {'gain + OFFSET' if a.with_offset else 'GAIN ONLY (default)'}")
    if a.with_offset:
        print("  !! --with-offset: the fitted offset is NOT a physical black point. Much "
              "of the\n     coarse-year red offset is the REFERENCE's sharpness, and "
              "resampling reproduces\n     that same mixing — applying both counts it "
              "twice. See ORDER OF OPERATIONS.")
    print()
    print(f"{'band':5s} {'gain_src':>9s} {'gain_tgt':>9s} {'ratio':>8s} "
          f"{'fit_dom':>13s} {'fitRMS':>7s} {'preRMS':>7s}  note")
    for b in BANDS:
        d = p["bands"][b]
        dom = (f"{d['fit_x_min']}-{d['fit_x_max']}"
               if d["fit_x_min"] else "-")
        def f(x, w=9):
            return f"{x:{w}.4f}" if isinstance(x, float) else f"{'-':>{w}}"
        print(f"{b:5s} {f(d['gain_src'])} {f(d['gain_tgt'])} {f(d['gain_ratio'], 8)} "
              f"{dom:>13s} {str(d['fit_quality'] or '-')[:7]:>7s} "
              f"{str(d['pre_rms'] or '-')[:7]:>7s}  {d['note']}")

    print()
    print("REMINDERS, none of them optional:")
    print("  · outputs must be named synth_{source}_as_{target}; the policy block on")
    print("    radiometry_norm.normalize_array requires the artifact to announce itself.")
    print("  · take the valid mask from RAW pixels first — nodata is all-bands-zero and a")
    print("    positive offset would fabricate imagery out of the fill value.")
    print("  · DNs outside the fitted domain above are EXTRAPOLATION, not measurement.")
    print("  · the masks are NOT gold: the 2020 mask is a model prediction.")

    if a.src_raster:
        if not a.out:
            raise SystemExit("--src-raster needs --out")
        print()
        res = synthesize(a.src_raster, a.source, a.target, a.out, window=a.window,
                         with_offset=a.with_offset, table=table,
                         resampling=a.resampling, passes=a.passes, seed=a.seed,
                         jpeg=not a.no_jpeg)
        print(f"wrote {res['out']}")
        print(f"  shape {res['shape']}  scale {res['scale']:.4f}  "
              f"valid {res['valid_frac_src']:.3f} src -> {res['valid_frac_out']:.3f} out")
        for b, what in res['applied'].items():
            print(f"  {b}: {what}")
        if res.get('chain'):
            for rec in res['chain']:
                print(f"  pass {rec['pass']}: kernel {rec['kernel']}  "
                      f"resize {rec['resize']['interp']}->{rec['resize']['to']}  "
                      f"noise sigma {rec['noise_sigma']}  jpeg q{rec.get('jpeg_q', '-')}")
    return 0




# ── the raster step ───────────────────────────────────────────────────────────

def synthesize(src_path, source, target, out_path, window=None, with_offset=False,
               table=None, resampling="average", passes=0, seed=42, jpeg=True):
    """Write ONE synthetic window: resample to the target's GSD, then apply the map.

    ORDER IS RESAMPLE-THEN-RADIOMETRY, for the reason in the module header: the fitted
    offset already contains the mixing that downsampling reproduces, so doing radiometry
    first and resampling second counts it twice.

    RESAMPLING IS `average`, NOT `nearest`. Downsampling a 7.6 cm ortho to 20 cm is an
    AGGREGATION — a coarse pixel genuinely is the mean of the fine pixels under it, which
    is exactly the mixing the coarse sensor performs. `nearest` would sub-sample instead,
    keeping one fine pixel's value and discarding the rest, which produces a sharp image at
    a coarse grid: the look of neither sensor. (qc/instruments/phase4_qc_extent_matched.py uses nearest
    for a different job — matching a categorical reference — and that is why it must not be
    reused here.)

    The valid mask comes from the RAW pixels BEFORE anything is applied, because the
    project's nodata convention is all-bands-exactly-0 and any positive term would turn
    those zeros into a plausible DN. Invalid pixels are written back as 0.
    """
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import Window

    if table is None:
        table, _ = load_table()
    plan = plan_for(target, source, table)
    tgt_cm, src_cm = plan["target_gsd_cm"], plan["source_gsd_cm"]
    if not (tgt_cm and src_cm):
        raise SystemExit(f"missing gsd for {source} or {target}")
    scale = src_cm / tgt_cm                      # < 1 when the target is coarser

    with rasterio.open(src_path) as src:
        win = Window(*window) if window else Window(0, 0, src.width, src.height)
        raw = src.read(window=win)                                    # (bands, h, w)
        prof = src.profile.copy()
        tf = src.window_transform(win)

        valid = ~(raw == 0).all(axis=0)                               # BEFORE anything
        oh = max(1, int(round(raw.shape[1] * scale)))
        ow = max(1, int(round(raw.shape[2] * scale)))
        if passes and passes > 0:
            # The two-pass chain owns the whole downsample; see degrade_chain.
            rng = np.random.default_rng(seed)
            small, chain_log = degrade_chain(raw.astype("float32"), scale, rng,
                                             passes=passes, jpeg=jpeg)
            oh, ow = small.shape[1], small.shape[2]
        else:
            chain_log = None
            small = src.read(window=win, out_shape=(raw.shape[0], oh, ow),
                             resampling=getattr(Resampling, resampling)).astype("float32")
        # A coarse pixel is valid only where it sampled real ground. Derived from the
        # RESAMPLED stack rather than by resampling the raw mask: `average` over a
        # part-nodata footprint already pulls those pixels toward 0, and this keeps the
        # validity test consistent with the pixels actually written.
        vmask = (small != 0).any(axis=0)

    names = ["R", "G", "B", "N"][:small.shape[0]]
    applied = {}
    for i, b in enumerate(names):
        d = plan["bands"].get(b) or {}
        gr = d.get("gain_ratio")
        if gr is None:
            applied[b] = "UNCHANGED (no coefficient — the table declines to supply one)"
            continue
        band = small[i] * gr
        if with_offset:
            os_, ot = d.get("offset_src") or 0.0, d.get("offset_tgt") or 0.0
            band = band + (os_ - ot) / (d.get("gain_tgt") or 1.0)
        small[i] = band
        applied[b] = (f"gain_ratio={gr:.4f}" + (" +offset" if with_offset else ""))

    small = np.clip(small, 0, 255)
    small[:, ~vmask] = 0                                              # nodata stays nodata
    out = small.astype("uint8")

    prof.update(width=ow, height=oh, count=out.shape[0], dtype="uint8",
                transform=rasterio.Affine(tf.a / scale, tf.b, tf.c,
                                          tf.d, tf.e / scale, tf.f),
                compress="deflate", tiled=True)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(out)
        for i, b in enumerate(names, start=1):
            dst.set_band_description(
                i, f"SYNTHETIC {b}: {source} resampled to {target} GSD, {applied[b]}")
        dst.update_tags(
            SYNTHETIC="yes", synth_source=source, synth_target=target,
            synth_tool="qc/instruments/degrade_synth.py", synth_order="resample-then-radiometry",
            synth_offset_applied=str(bool(with_offset)),
            synth_resampling=(resampling if not chain_log else "degrade_chain"),
            synth_passes=str(passes or 0), synth_seed=str(seed),
            synth_chain=("" if not chain_log else json.dumps(chain_log)),
            synth_note=("Masks are NOT gold: the 2020 canopy mask is a model prediction. "
                        "PSF/blur half is approximate. Offsets omitted by default because "
                        "the fitted offset already contains the mixing that resampling "
                        "reproduces."))
    return dict(out=str(out_path), shape=[int(x) for x in out.shape],
                scale=scale, applied=applied, chain=chain_log,
                valid_frac_src=float(valid.mean()), valid_frac_out=float(vmask.mean()))




# ── the two-pass degradation chain (Real-ESRGAN pattern) ─────────────────────

def _gen_gaussian_kernel(rng, size=None, sigma=None, beta=None):
    """A GENERALIZED Gaussian kernel: exp(-(r^2 / 2 sigma^2)^(beta/2)).

    beta = 2 is the ordinary Gaussian. beta < 2 gives heavier tails (a softer, hazier
    blur), beta > 2 a flatter core with a sharper cutoff (nearer a box). Real sensor PSFs
    are not Gaussian, and drawing beta per pass is what stops the synthetic blur from
    carrying one recognisable signature that a network can key on.
    """
    import numpy as np
    size = size or int(rng.choice([7, 9, 11, 13, 15, 17, 21]))
    size = size + 1 if size % 2 == 0 else size
    sigma = sigma if sigma is not None else float(rng.uniform(0.2, 3.0))
    beta = beta if beta is not None else float(rng.uniform(0.5, 4.0))
    r = np.arange(size) - size // 2
    xx, yy = np.meshgrid(r, r)
    rr = xx ** 2 + yy ** 2
    k = np.exp(-((rr / (2 * sigma ** 2)) ** (beta / 2.0)))
    s = k.sum()
    return (k / s) if s > 0 else k, dict(size=size, sigma=round(sigma, 3),
                                         beta=round(beta, 3))


def degrade_chain(arr, scale, rng, passes=2, jpeg=True):
    """Blur -> resize -> noise -> JPEG, run `passes` times, splitting the total scale.

    WHY TWICE. One clean chain is too REGULAR: a single blur sigma and a single noise
    level give the network a constant, learnable signature, and models trained on it
    transfer poorly to real degraded imagery (the Real-ESRGAN finding, carried in this
    project's own degraded-imagery lit review). Splitting the total downsample across two
    passes with independently drawn parameters produces a distribution of looks instead of
    one look.

    Deterministic given `rng`, and the drawn parameters are RETURNED so the artifact can
    record exactly what was applied — a synthetic image whose degradation cannot be
    described is not reproducible evidence.

    arr   : (bands, h, w) float32
    scale : total linear scale (< 1 downsamples)
    """
    import numpy as np
    from scipy.ndimage import convolve

    per = scale ** (1.0 / passes)
    log = []
    cur = arr
    for p in range(passes):
        rec = {"pass": p + 1}
        k, kinfo = _gen_gaussian_kernel(rng)
        rec["kernel"] = kinfo
        cur = np.stack([convolve(c, k, mode="nearest") for c in cur])

        h, w = cur.shape[1], cur.shape[2]
        nh, nw = max(1, int(round(h * per))), max(1, int(round(w * per)))
        interp = str(rng.choice(["area", "bilinear", "bicubic"]))
        rec["resize"] = {"to": [nh, nw], "interp": interp}
        import cv2
        code = {"area": cv2.INTER_AREA, "bilinear": cv2.INTER_LINEAR,
                "bicubic": cv2.INTER_CUBIC}[interp]
        cur = np.stack([cv2.resize(c, (nw, nh), interpolation=code) for c in cur])

        sigma_n = float(rng.uniform(0.0, 6.0))
        rec["noise_sigma"] = round(sigma_n, 3)
        if sigma_n > 0:
            cur = cur + rng.normal(0.0, sigma_n, size=cur.shape)

        if jpeg:
            q = int(rng.integers(60, 96))
            rec["jpeg_q"] = q
            u8 = np.clip(cur, 0, 255).astype("uint8")
            chans = []
            for c in u8:
                ok, enc = cv2.imencode(".jpg", c, [int(cv2.IMWRITE_JPEG_QUALITY), q])
                chans.append(cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE) if ok else c)
            cur = np.stack(chans).astype("float32")
        log.append(rec)
    return cur.astype("float32"), log


if __name__ == "__main__":
    sys.exit(main())
