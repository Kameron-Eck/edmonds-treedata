r"""Which file in a suspect pair is displaced? — generalised from the 2024 investigation.

Cross-registration flags a pair as offset, but an offset is symmetric: it says the two files
disagree, not which one is wrong. This resolves that by triangulating against reference files
whose georeferencing is independently trusted.

METHOD
  1. Measure the pair's own offset, and the offset after removing it (r before vs after tells
     you whether it is the SAME imagery mis-georeferenced or two different acquisitions).
  2. Measure each side of the pair against every reference file. Real change between years
     lowers correlation, but phase correlation locks onto stable built structure, so the
     OFFSET remains meaningful even across years.
  3. Whichever side sits close to the references is correctly georeferenced; the other moved.
     If both sit equally far, say INCONCLUSIVE rather than guessing.

References should be files already shown to agree with each other. As of 2026-08-24 the
sub-metre, tight-agreement set is: 2020_coe/2020_snoh_3in (0.00 m), 2022 pair (0.00 m),
2019_naip/2019_snoh (0.07 m), 2021_king/2021_snoh_6in (0.15 m).

USAGE
  py -3.12 qc/instruments/investigate_displacement.py --a 2013_king_rgb.tif --b 2013_snoh_1m_rgb.tif \
      --refs 2021_snoh_6in_rgbi.tif 2019_snoh_1ft_rgbi.tif 2015_snoh_1ft_rgb.tif
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[2]  # instruments/ -> qc/ -> Scripts/
sys.path.insert(0, str(SCRIPTS / "qc"))                    # imagery_qc_suite (qc root)
sys.path.insert(0, str(Path(__file__).resolve().parent))   # sibling instruments
import imagery_measure as im               # noqa: E402
import imagery_qc_suite as QS              # noqa: E402
from investigate_2024_offset import corr, shift_correct   # noqa: E402
from phase4seg.names import clean_argv  # noqa: E402


def measure(pa: Path, pb: Path, label: str, box_m: float):
    offs, dxs, dys, raw, fixed, peaks = [], [], [], [], [], []
    for site, (lon, lat) in im.SITES.items():
        try:
            A, B, g = QS.common_grid_pair(pa, pb, lon, lat, box_m)
        except Exception:
            continue
        if A is None:
            continue
        ok = (A > 0) & (B > 0)
        if ok.mean() < 0.5:
            continue
        sh = QS.phase_shift(A, B)
        if sh is None or sh[2] < QS.PEAK_FLOOR:
            continue
        dx, dy, peak = sh
        offs.append(float(np.hypot(dx, dy) * g))
        dxs.append(dx * g)
        dys.append(dy * g)
        peaks.append(peak)
        r0 = corr(A, B, ok)
        A2, B2 = shift_correct(A, B, dx, dy)
        r1 = corr(A2, B2, (A2 > 0) & (B2 > 0)) if A2 is not None else None
        if r0 is not None:
            raw.append(r0)
        if r1 is not None:
            fixed.append(r1)
    if not offs:
        return dict(pair=label, n_sites=0, note="no usable sites")
    med = lambda v: round(float(np.median(v)), 4) if v else None      # noqa: E731
    mad = lambda v: round(float(np.median(np.abs(np.asarray(v, float) - np.median(v)))), 3)  # noqa: E731
    out = dict(pair=label, n_sites=len(offs), offset_m=med(offs),
               spread_m=max(mad(dxs), mad(dys)), median_peak=med(peaks),
               r_raw=med(raw), r_shift_corrected=med(fixed))
    print(f"  {label:34s} offset {out['offset_m']:>7} m  spread {out['spread_m']:>6}  "
          f"r {out['r_raw']} -> {out['r_shift_corrected']}", flush=True)
    return out


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--refs", nargs="+", required=True)
    ap.add_argument("--box-m", type=float, default=200.0)
    ap.add_argument("--tag", default=None)
    args = ap.parse_args(argv)

    inv = {r["file"]: r["path"] for r in QS.inventory() if r["path"] is not None}
    for f in [args.a, args.b] + args.refs:
        if f not in inv:
            sys.exit(f"{f} does not resolve on this machine")

    res = {"date": dt.date.today().isoformat(), "a": args.a, "b": args.b,
           "refs": args.refs, "box_m": args.box_m, "pairs": []}
    print(f"SUSPECT PAIR — {args.a} vs {args.b}")
    own = measure(inv[args.a], inv[args.b], f"{args.a[:14]}|{args.b[:14]}", args.box_m)
    res["pairs"].append(own)

    print("\nTRIANGULATION against references")
    a_offs, b_offs = [], []
    for ref in args.refs:
        ra = measure(inv[args.a], inv[ref], f"A|{ref[:24]}", args.box_m)
        rb = measure(inv[args.b], inv[ref], f"B|{ref[:24]}", args.box_m)
        res["pairs"] += [ra, rb]
        # A reference measurement counts ONLY if its five sites agree. Without this gate the
        # 2013 investigation (2026-08-24) returned a confident "2013_snoh is displaced" from
        # inputs whose site spreads were 2.1, 5.0, 9.0 and 14.8 m — larger than the 2.76 m
        # question being asked. Cross-YEAR triangulation at 1 m resolution, across six to eight
        # years of real change, frequently fails this test, and saying so is the correct answer.
        for rec, bucket in ((ra, a_offs), (rb, b_offs)):
            off, spr = rec.get("offset_m"), rec.get("spread_m")
            if off is None or spr is None:
                continue
            if spr <= max(0.30, 0.25 * off):
                bucket.append(off)
            else:
                rec["excluded"] = f"site spread {spr} m too large for a {off} m offset"

    a_med = float(np.median(a_offs)) if a_offs else None
    b_med = float(np.median(b_offs)) if b_offs else None
    if len(a_offs) < 2 or len(b_offs) < 2:
        verdict = (f"INCONCLUSIVE — only {len(a_offs)}/{len(args.refs)} A-references and "
                   f"{len(b_offs)}/{len(args.refs)} B-references had sites that agreed; "
                   f"triangulation cannot resolve this pair")
    else:
        verdict = "INCONCLUSIVE — both sides sit similar distances from the references"
        if a_med > b_med + 0.5:
            verdict = f"{args.a} is displaced"
        elif b_med > a_med + 0.5:
            verdict = f"{args.b} is displaced"
    res["verdict"] = dict(a_median_offset_vs_refs_m=round(a_med, 3) if a_med is not None else None,
                          b_median_offset_vs_refs_m=round(b_med, 3) if b_med is not None else None,
                          a_refs_that_agreed=len(a_offs), b_refs_that_agreed=len(b_offs),
                          n_refs=len(args.refs),
                          same_imagery_after_shift_correction=bool((own.get("r_shift_corrected") or 0) > 0.95),
                          displaced=verdict)
    print("\nVERDICT")
    for k, v in res["verdict"].items():
        print(f"  {k}: {v}")
    tag = args.tag or f"{args.a.split('_')[0]}"
    out = SCRIPTS.parent / "phase4" / "qc" / f"investigate_displacement_{tag}_{res['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
