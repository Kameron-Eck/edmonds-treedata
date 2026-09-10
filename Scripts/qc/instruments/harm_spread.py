r"""harm_spread.py — the CROSS-SURVEY SPREAD read for EXP-H1 / EXP-H2.

Reports/HARMONIZATION_DESIGN_2026-09-10.md pre-registers a convergence experiment whose
primary number is not a recall but a SPREAD: max - min of matched_p75 recall across the
five sample years. Nothing in the repo computed one. This instrument does, from the one
measured home (phase4/qc/arm_metrics.csv), and it computes every pre-registered kill that
a metrics table can carry — H1-K1, H1-K2, H2-K1 (including its two-reference clause), H2-K3
and H2-K4 — so none of them is assembled by hand after the numbers exist. H2-K2 needs
rasters and lives in qc/instruments/harm_change_laundering.py; nothing else is left to the
reader.

WHAT IT READS. arm_metrics.csv rows with policy `matched_p75`, eval_scope `sample-test`,
canopy_def `forest_wetland` — the pre-registered basis (design section 1.8) — for the two
references the design names: ccap_2021_hires_lc.tif and ccap_2016_hires_lc.tif.

HOW AN ARM IS KEYED. arm_metrics has no encoder or treatment column, so the run_tag is
parsed: `<prefix>_<year>_<treatment>`, prefix in PREFIX_ENCODER (t1 / bb18 / bb50 / wb18 /
wb50), treatment in TREATMENTS (base / in05 / in16), year validated against
config.YEAR_CATALOG. Anything else — the seed replicates `_base_s2` / `_base_s3`, the
corruption arms `cor05` / `cor10`, the adders `add05` / `add16`, `nir`, the `hy_e3_*` arms
— is SKIPPED, not coerced. The prefix carries the encoder AND the warm start (bb = ImageNet
start, wb / t1 = a trained base checkpoint), which is why the group key is the prefix and
not the encoder alone: bb18 and wb18 are the same encoder and are not comparable.

WHAT A SPREAD IS COMPARED ON. A spread over four years and a spread over five are not the
same statistic, so every aggregate here is computed on the FIVE PRE-REGISTERED YEARS
(H1_YEARS) and on nothing else — years outside that set are dropped from `spread`,
`h1_premise`, `ref_epoch_share` and `convergence_p` before the max-min is taken, and the
years actually used are printed in the row. Their per-arm `recall` rows are still emitted.
A `spread` row short of the five is flagged INCOMPLETE.

WHY THAT RESTRICTION IS EXPLICIT AND NOT "whatever years are present": the 2019s arms are
queued BY THIS DESIGN. Taking the years as they come turned the pre-registered five-year
spread into a six-year one the moment they landed — on a synthetic six-year set the base
spread read 0.3400 instead of 0.1400 and (P) went -0.0100 instead of -0.0600, i.e. a clear
promote suppressed, and neither the superset test nor the strict-subset test flagged it
because six is neither. The gate is in qc/test_harmonization.py, on that exact six-year
table.

THE PRE-REGISTERED CONSTANTS, and they are read from the design, not chosen here:
  FLOOR        0.0069  the wb18 three-seed 2011s spread (experiments/backbone_sweep.yaml
                       verdict). A per-arm delta inside it is UNDETERMINED, never "no
                       difference" (CLAUDE.md 3.5).
  SPREAD_FLOOR 0.014   2 x FLOOR. A spread is a max-min of five draws and is noisier than
                       one delta, so a spread change must clear twice the floor.
  REF_EPOCH_CUT 0.4    H1-K2: if the 2016-referenced spread is <= 0.4x the 2021-referenced
                       spread, >= 60% of the spread is reference-epoch distance and
                       matched_p75-vs-C-CAP-2021 is not a convergence metric.

THE QUANTITIES, in the order a reader should meet them:
  recall             per (prefix, treatment, ref, year) — the arm's number, with the floor
  spread             max - min over the years present, per (prefix, treatment, ref)
  same_flight_gap    |recall(2019n) - recall(2019s)| when both exist — the zero-circularity
                     read (design section 1.5): same date, same ground, same distance to
                     every reference. Readable as an absolute number under the caveat in
                     WHAT --force-citywide DOES below.
  k3_gap_change      gap(in16) - gap(base) — EXP-H2's K3, the mechanism read. Negative
                     beyond the floor is the shrink the design asks for; anything else
                     makes the cross-year compression UNINTERPRETABLE for this goal.
  k1_ref_verdict     the two-reference clause of H2-K1, applied instead of left to the
                     reader: an interaction that fires against ONE reference only is
                     reference-epoch confounding and is UNDETERMINED, not a pass.
  h1_premise         the base spread, flagged "H2 premise dead" when it is <= SPREAD_FLOOR
                     on a COMPLETE five-year set — EXP-H1's K1
  ref_epoch_share    1 - spread(ccap_2016)/spread(ccap_2021) — EXP-H1's K2
  k1_interaction     [(in16 - in05) @ 2006s] - [(in16 - in05) @ 2016] — EXP-H2's K1, the
                     leak signature as an INTERACTION (a uniform in16 advantage is a
                     CHM-QUALITY effect, experiments/old_chm_defect.yaml, not a leak)
  k4_2016_null       (in16 - base) @ 2016 — EXP-H2's K4, the pre-registered non-event
  convergence_p      spread(in16) - spread(base) on the common years — EXP-H2's (P)

WHAT --force-citywide DOES, AND WHY THE SAME-FLIGHT GAP IS NOT RECIPE-CONFOUNDED.
`--tier` IS inert for a queued job — `cli.py::_resolve_years` consults it only when `--year`
is absent and even there it FILTERS rather than overrides, and the queue always passes
`--year` (phase4_train_queue.py::run_step) — so no arm here passes it. But `--tier` was never
the lever that matters: every arm carries `--force-citywide`, whose stated job (its own help
text, cli.py::main) is to "apply the citywide 2020-mask COARSE recipe (labels + sampler +
selection metric) to EVERY tier, so only the sensor/GSD varies". Read in code, not from the
help text: the early-stop/best-checkpoint metric is keyed on `use_blocked_val`, not on the
tier (core.py::step_train, "Early-stop / best-checkpoint criterion follows the POOL"), and so
is the pos_weight channel; `TIER_LOSS_MODE` is bce_dice at all three tiers; the split is cut
by `tiling._block_partition` at COARSE_VAL_FRAC / COARSE_TEST_FRAC (0.20 / 0.20) for both;
and `TIER_TILE_PARAMS[tier]["neg_rate"]` / `["test_frac"]` are reached only on the legacy
6-site path. So 2019s and 2019n train on ONE recipe.

WHAT DOES STILL DIFFER between the two 2019 arms, and it is sampling support, not recipe:
a 512 px tile is 156 m of ground at 2019s (30.5 cm) and 307 m at 2019n (60 cm), and the two
sample manifests hold 412 and 306 tiles. The curated negative-site tiles are still cut at
the tier stride (tiling._gather_citywide_coarse) — 256 px at 2019s, 128 px at 2019n, i.e.
78.1 m vs 76.8 m of ground, a 1.7% difference rather than a switch. One asymmetry is
DATA-DEPENDENT and must be checked after tiling rather than assumed: if `_block_partition`
degrades to its random fallback on one year and not the other, the two arms no longer share
a split mode — the tile step prints it and the tile index records it (`_index_split_mode`).
H2-K3 reads the CHANGE in the gap (design, K3) and the absolute gap is reported beside it.

K2 (change laundering) is NOT computed here — it needs rasters, not a metrics table, and
lives in qc/instruments/harm_change_laundering.py.

Byte-identical by construction: `render()` is pure, sorted, fixed-precision, and
qc/test_harmonization.py byte-compares the tracked CSV against it.

Run:
  PYTHONUTF8=1 py -3.12 qc/instruments/harm_spread.py
  PYTHONUTF8=1 py -3.12 qc/instruments/harm_spread.py --stdout
"""
import argparse
import csv
import io
from pathlib import Path

HERE = Path(__file__).resolve().parent           # Scripts/qc/instruments
SCRIPTS = HERE.parents[1]                        # Scripts/
REPO = SCRIPTS.parent

ARM_METRICS = REPO / "phase4" / "qc" / "arm_metrics.csv"
OUT_DEFAULT = REPO / "phase4" / "qc" / "harm_spread.csv"

# The pre-registered basis (design section 1.8) — never widen these without a new
# pre-registration; a policy or scope swap changes what the spread means.
POLICY = "matched_p75"
EVAL_SCOPE = "sample-test"
CANOPY_DEF = "forest_wetland"
REF_2021 = "ccap_2021_hires_lc.tif"
REF_2016 = "ccap_2016_hires_lc.tif"
REFS = (REF_2021, REF_2016)

# prefix -> (encoder, warm start). The prefix is the group key: bb18 and wb18 are the
# same encoder from different starts and are NOT one population.
PREFIX_ENCODER = {
    "t1": ("resnet101", "p3_ckpt"),
    "bb18": ("resnet18", "imagenet"),
    "bb50": ("resnet50", "imagenet"),
    "wb18": ("resnet18", "p3_ckpt"),
    "wb50": ("resnet50", "p3_ckpt"),
}
TREATMENTS = ("base", "in05", "in16")
# The five years EXP-H1's spread is defined over (design, EXP-H1 "Primary metric").
H1_YEARS = ("2006s", "2011s", "2016", "2019n", "2020")
SAME_FLIGHT = ("2019n", "2019s")

FLOOR = 0.0069            # experiments/backbone_sweep.yaml verdict (wb18 three-seed 2011s)
SPREAD_FLOOR = 0.014      # 2 x FLOOR — a spread is a max-min of five draws
REF_EPOCH_CUT = 0.4       # H1-K2

FIELDS = ["prefix", "encoder", "warm_start", "treatment", "ref", "quantity", "year",
          "value", "n_years", "years", "floor", "flag", "note"]


def _catalog_labels():
    """Year labels are catalog keys, never calendar years (CLAUDE.md 2.2)."""
    from phase4seg.config import YEAR_CATALOG
    return {str(e["label"]) for e in YEAR_CATALOG}


def parse_tag(run_tag, labels):
    """(prefix, year, treatment) for an arm this instrument scores, else None.

    Deliberately strict: `wb18_2011s_base_s2` (a seed replicate), `t1_2011s_cor05`
    (a corruption dose) and `t1_2016_nir` (a different input) are all NOT treatments of
    the harmonization design and must not be swept into a spread.
    """
    parts = str(run_tag).split("_")
    if len(parts) != 3:
        return None
    prefix, year, treat = parts
    if prefix not in PREFIX_ENCODER or treat not in TREATMENTS or year not in labels:
        return None
    return prefix, year, treat


def load_recalls(arm_metrics=ARM_METRICS, labels=None):
    """{(prefix, treatment, ref): {year: recall}} on the pre-registered basis."""
    if labels is None:
        labels = _catalog_labels()
    out = {}
    with Path(arm_metrics).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if (r["policy"] != POLICY or r["eval_scope"] != EVAL_SCOPE
                    or r["canopy_def"] != CANOPY_DEF or r["ref"] not in REFS):
                continue
            key = parse_tag(r["run_tag"], labels)
            if key is None:
                continue
            prefix, year, treat = key
            if str(r["year"]) != year:
                continue                    # tag and row disagree — do not guess
            out.setdefault((prefix, treat, r["ref"]), {})[year] = float(r["recall"])
    return out


def _fmt(v):
    return "" if v is None else f"{v:.4f}"


def _row(prefix, treatment, ref, quantity, value, year="", years=(), flag="", note=""):
    enc, warm = PREFIX_ENCODER[prefix]
    return {"prefix": prefix, "encoder": enc, "warm_start": warm,
            "treatment": treatment, "ref": ref, "quantity": quantity, "year": year,
            "value": _fmt(value), "n_years": str(len(years)) if years else "",
            "years": ",".join(years), "floor": _fmt(FLOOR), "flag": flag, "note": note}


def _spread(by_year, years):
    vals = [by_year[y] for y in years if y in by_year]
    return (max(vals) - min(vals)) if len(vals) >= 2 else None


def build(arm_metrics=ARM_METRICS, labels=None):
    """Every quantity, as dicts. Pure — no I/O beyond reading arm_metrics."""
    recalls = load_recalls(arm_metrics, labels)
    rows = []

    for (prefix, treat, ref), by_year in sorted(recalls.items()):
        for year in sorted(by_year):
            rows.append(_row(prefix, treat, ref, "recall", by_year[year], year=year))

        # The spread is DEFINED on the five pre-registered years and on nothing else.
        # Reading "whatever years are present" silently re-populated the statistic the
        # moment a sixth year landed — and 2019s is queued BY THIS DESIGN — while passing
        # both the superset test and the strict-subset test, because six is neither.
        years = tuple(y for y in H1_YEARS if y in by_year)
        sp = _spread(by_year, years)
        if sp is not None:
            complete = set(years) == set(H1_YEARS)
            rows.append(_row(prefix, treat, ref, "spread", sp, years=years,
                             flag="" if complete else "INCOMPLETE",
                             note="max-min over the years listed"))
            if treat == "base":
                # EXP-H1 K1: no cross-survey disagreement to harmonize -> H2's premise dies.
                # Only readable on the complete five-year set; a short set is INCOMPLETE,
                # never a pass (CLAUDE.md 3.5: undetermined is not "no difference").
                if not complete:
                    flag = "INCOMPLETE"
                elif sp <= SPREAD_FLOOR:
                    flag = "H2 premise dead"
                else:
                    flag = "SPREAD EXCEEDS 2xFLOOR"
                rows.append(_row(prefix, treat, ref, "h1_premise", sp, years=years,
                                 flag=flag,
                                 note=f"EXP-H1 K1 at 2xfloor {SPREAD_FLOOR}"))

        if all(y in by_year for y in SAME_FLIGHT):
            gap = abs(by_year[SAME_FLIGHT[0]] - by_year[SAME_FLIGHT[1]])
            rows.append(_row(prefix, treat, ref, "same_flight_gap", gap,
                             years=SAME_FLIGHT,
                             note="one recipe under --force-citywide; differs in sampling"
                                  " support (156m vs 307m tiles). H2-K3 reads its CHANGE"))

    # ---- cross-reference and cross-treatment quantities -------------------------
    prefixes = sorted({p for p, _t, _r in recalls})
    for prefix in prefixes:
        for treat in TREATMENTS:
            a = recalls.get((prefix, treat, REF_2021))
            b = recalls.get((prefix, treat, REF_2016))
            if not a or not b:
                continue
            common = tuple(y for y in H1_YEARS if y in a and y in b)
            s21, s16 = _spread(a, common), _spread(b, common)
            if s21 is None or s16 is None or s21 == 0:
                continue
            share = 1.0 - (s16 / s21)
            rows.append(_row(prefix, treat, f"{REF_2016}|{REF_2021}", "ref_epoch_share",
                             share, years=common,
                             flag=("H1-K2 METRIC KILLED" if s16 <= REF_EPOCH_CUT * s21
                                   else ""),
                             note=f"1 - s2016/s2021 on the common years; cut "
                                  f"{REF_EPOCH_CUT}"))

        k1_by_ref = {}
        for ref in REFS:
            base = recalls.get((prefix, "base", ref), {})
            in05 = recalls.get((prefix, "in05", ref), {})
            in16 = recalls.get((prefix, "in16", ref), {})

            # EXP-H2 K1 — the leak signature is the INTERACTION, not "in16 > in05".
            if all("2006s" in d and "2016" in d for d in (in05, in16)):
                k1 = ((in16["2006s"] - in05["2006s"])
                      - (in16["2016"] - in05["2016"]))
                k1_by_ref[ref] = k1
                rows.append(_row(prefix, "in16_minus_in05", ref, "k1_interaction", k1,
                                 years=("2006s", "2016"),
                                 flag="H2-K1 LEAK" if k1 > FLOOR else "",
                                 note="[(in16-in05)@2006s] - [(in16-in05)@2016]"))

            # EXP-H2 K4 — pre-registered non-event on 2016.
            if "2016" in base and "2016" in in16:
                k4 = in16["2016"] - base["2016"]
                rows.append(_row(prefix, "in16_minus_base", ref, "k4_2016_null", k4,
                                 year="2016", years=("2016",),
                                 flag=("H2-K4 NULL AS PRE-REGISTERED" if abs(k4) <= FLOOR
                                       else "H2-K4 OUTSIDE THE FLOOR"),
                                 note="neither a win nor a failure (design, K4)"))

            # EXP-H2 (P) — convergence, on the years both treatments hold.
            common = tuple(y for y in H1_YEARS if y in base and y in in16)
            sb, si = _spread(base, common), _spread(in16, common)
            if sb is None or si is None:
                continue
            p = si - sb
            rows.append(_row(prefix, "in16_minus_base", ref, "convergence_p", p,
                             years=common,
                             # INCOMPLETE is tested FIRST, deliberately: a promote-side
                             # flag must never be easier to fire than a kill-side one.
                             # (P) is defined on the five pre-registered years; on a short
                             # set it is UNDETERMINED, not a convergence.
                             flag=("INCOMPLETE" if set(common) != set(H1_YEARS) else
                                   ("H2-P CONVERGENCE" if p <= -SPREAD_FLOOR else "")),
                             note=f"spread(in16)-spread(base) on the common years; "
                                  f"promote at <= -{SPREAD_FLOOR}"))

            # EXP-H2 K3 — MECHANISM. The same-flight gap must SHRINK; the design reads
            # the CHANGE, not the absolute value, so this is the row K3 is decided on.
            gaps = {}
            for t in ("base", "in16"):
                d = recalls.get((prefix, t, ref), {})
                if all(y in d for y in SAME_FLIGHT):
                    gaps[t] = abs(d[SAME_FLIGHT[0]] - d[SAME_FLIGHT[1]])
            if len(gaps) == 2:
                k3 = gaps["in16"] - gaps["base"]
                rows.append(_row(prefix, "in16_minus_base", ref, "k3_gap_change", k3,
                                 years=SAME_FLIGHT,
                                 flag=("H2-K3 GAP SHRINKS" if k3 <= -FLOOR else
                                       "H2-K3 NO SHRINK - CROSS-YEAR UNINTERPRETABLE"),
                                 note=f"gap(in16)-gap(base); shrink at <= -{FLOOR}"))

        # EXP-H2 K1, the two-reference clause — APPLIED, not left to the reader. An
        # interaction that fires against one reference and vanishes against the other is
        # reference-epoch confounding (design 1.7) and is UNDETERMINED, never a pass.
        if len(k1_by_ref) == len(REFS):
            fires = {r: k1_by_ref[r] > FLOOR for r in REFS}
            if all(fires.values()):
                flag = "H2-K1 LEAK (BOTH REFS)"
            elif any(fires.values()):
                flag = "H2-K1 UNDETERMINED - FIRES ON ONE REFERENCE ONLY"
            else:
                flag = ""
            rows.append(_row(prefix, "in16_minus_in05", f"{REF_2016}|{REF_2021}",
                             "k1_ref_verdict", min(k1_by_ref.values()),
                             years=("2006s", "2016"), flag=flag,
                             note="the SMALLER of the two per-reference interactions; "
                                  "one-reference-only is UNDETERMINED, not a pass"))

    rows.sort(key=lambda r: (r["prefix"], r["treatment"], r["ref"], r["quantity"],
                             r["year"], r["years"]))
    return rows


def render(arm_metrics=ARM_METRICS, labels=None):
    """The CSV text. Deterministic, LF-only — byte-compared by the gate."""
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(build(arm_metrics, labels))
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm-metrics", default=str(ARM_METRICS))
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    if argv is None:
        from phase4seg.names import clean_argv
        argv = clean_argv()
    a = ap.parse_args(argv)
    text = render(Path(a.arm_metrics))
    if a.stdout:
        print(text, end="")
        return 0
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"wrote {out} ({len(text.splitlines()) - 1} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
