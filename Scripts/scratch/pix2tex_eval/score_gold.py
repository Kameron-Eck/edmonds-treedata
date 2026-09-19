"""Final scoring pass for the 20-equation gold set: agreement (automated, normalize_and_score)
crossed with correctness against Reports/gold/p5_gold_2026-09-16.json's `reading` field.

CORRECTNESS is a human judgment call, made the same way the P5 final referee made it for
CodeFormula (Reports/LITKB_P5_FINAL_REFEREE_2026-09-16.md S3): read the rendered crop
(Scripts/scratch/pix2tex_eval/crops_gold/{id}.png), compare to `reading`, grade
identical/equivalent vs wrong. CODEFORMULA_CORRECT below is not re-derived here -- it is
transcribed from that referee's own table (S3, "identical / equivalent" n=11 /
"wrong" n=9) plus the one correction the referee recorded in prose (E02: the gold's
`reading` field itself is wrong -- "\\hat{u} = My"; the page prints \\hat{\\mu}=My; the
STORED codeformula-l4 "\\hat{\\mu}=My" is right and graded correct here in the database's
favour, exactly as that referee did). PIX2TEX_CORRECT is this evaluation's own read, done
by the same rule, with the one-line evidence noted per id.
"""
import json
import sys

sys.path.insert(0, r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval")
from normalize_and_score import agree  # noqa: E402

GOLD_JOINED = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\gold_equations_joined.json"
PREDS = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\pix2tex_gold_predictions.json"
OUT = r"D:\edmonds-pipeline\treedata-pix2tex\Scripts\scratch\pix2tex_eval\gold_scored.json"

# Reports/LITKB_P5_FINAL_REFEREE_2026-09-16.md S3, table verbatim + the E02 correction noted
# in prose immediately below it.
CODEFORMULA_CORRECT = {
    "E01": False, "E02": True, "E03": False, "E04": True, "E05": False, "E06": False,
    "E07": False, "E08": True, "E09": True, "E10": True, "E11": False, "E12": False,
    "E13": True, "E14": True, "E15": True, "E16": True, "E17": True, "E18": True,
    "E19": False, "E20": False,
}

# This evaluation's own read of the pix2tex output against the crop + gold `reading`
# (E02's true answer is \hat{\mu}=My, per the correction above -- NOT the gold file's own
# uncorrected "\hat{u}=My" string).
PIX2TEX_CORRECT = {
    "E01": (False, "garbled fraction/vdots array, no relation to the 6-line derivation"),
    "E02": (False, "\\bar{\\mu}=My -- wrong diacritic (bar, not hat); confirmed on the crop"),
    "E03": (False, "drops the |k| factor before Cov(...), adds a spurious ^2 on nabla', "
                    "trailing garbage rows"),
    "E04": (True, "matches gold exactly, plus the page's own (59) tag"),
    "E05": (True, "has S^{d-1} correctly -- CodeFormula's own error (S^{d}) is ABSENT here; "
                    "confirmed on the crop"),
    "E06": (False, "near-total garbage (\"trueglenusf unk oven oreung...\"), math unrecoverable"),
    "E07": (False, "total garbage: a run of repeated \"~\" tokens, no equation content"),
    "E08": (False, "matrix corrupted: row3 col3 drops \"1-\" (reads 0, should be 1-e_{32}); "
                    "row4 missing its 4th entry; confirmed on the crop"),
    "E09": (True, "matches gold"),
    "E10": (False, "\\mathcal{P}_lambda(D) -- confuses the calligraphic G for P on the LHS "
                    "functional name; confirmed on the crop (page clearly shows G)"),
    "E11": (True, "core integral matches gold exactly (my crop did not carry the neighbouring "
                    "\\intertext contamination CodeFormula's real crop apparently did -- see "
                    "report caveat on crop-boundary fidelity)"),
    "E12": (False, "different garbling from CodeFormula's (wrong subscripts/symbols throughout)"),
    "E13": (True, "matches gold"),
    "E14": (True, "matches gold"),
    "E15": (False, "malformed brace nesting plus unrelated boxed/circled junk prepended; "
                    "the embedded rho_0 fraction itself is legible and correct but the region "
                    "is not"),
    "E16": (True, "matches gold"),
    "E17": (False, "piecewise structure scrambled via mismatched \\stackrel pairs; \"otherwise\" "
                    "corrupted to \"\\otherwise\"; confirmed on the crop"),
    "E18": (True, "matches gold"),
    "E19": (False, "total garbage: a wall of repeated arrows/backslash-w tokens"),
    "E20": (False, "unrelated garbled fragments, no relation to the permutation-matrix content"),
}


def main():
    joined = {r["id"]: r for r in json.load(open(GOLD_JOINED, encoding="utf-8"))}
    preds = {r["id"]: r["pix2tex"] for r in json.load(open(PREDS, encoding="utf-8"))}
    rows = []
    for eid in sorted(joined, key=lambda x: int(x[1:])):
        cf_latex = joined[eid]["codeformula_latex"]
        p2_latex = preds[eid]
        a = agree(cf_latex, p2_latex)
        cf_ok = CODEFORMULA_CORRECT[eid]
        p2_ok, note = PIX2TEX_CORRECT[eid]
        rows.append({
            "id": eid, "file": joined[eid]["rel_path"], "page": joined[eid]["page"],
            "gold_reading": joined[eid]["gold_reading"],
            "codeformula_latex": cf_latex, "pix2tex_latex": p2_latex,
            "agree": a, "codeformula_correct": cf_ok, "pix2tex_correct": p2_ok,
            "pix2tex_note": note,
        })
    n = len(rows)
    n_agree = sum(r["agree"] for r in rows)
    n_cf_ok = sum(r["codeformula_correct"] for r in rows)
    n_p2_ok = sum(r["pix2tex_correct"] for r in rows)
    both_wrong_agree = sum(r["agree"] and not r["codeformula_correct"] and not r["pix2tex_correct"]
                            for r in rows)
    both_ok_agree = sum(r["agree"] and r["codeformula_correct"] and r["pix2tex_correct"]
                        for r in rows)
    cf_only = sum((not r["agree"]) and r["codeformula_correct"] and not r["pix2tex_correct"]
                  for r in rows)
    p2_only = sum((not r["agree"]) and (not r["codeformula_correct"]) and r["pix2tex_correct"]
                  for r in rows)
    both_wrong_disagree = sum((not r["agree"]) and (not r["codeformula_correct"])
                               and (not r["pix2tex_correct"]) for r in rows)

    print(f"{'id':<4} {'agree':<6} {'cf_ok':<6} {'p2_ok':<6} note")
    for r in rows:
        print(f"{r['id']:<4} {str(r['agree']):<6} {str(r['codeformula_correct']):<6} "
              f"{str(r['pix2tex_correct']):<6} {r['pix2tex_note']}")
    print()
    print(f"n={n}  agree={n_agree} ({n_agree/n:.0%})  codeformula_correct={n_cf_ok} ({n_cf_ok/n:.0%})  "
          f"pix2tex_correct={n_p2_ok} ({n_p2_ok/n:.0%})")
    print()
    print("2x2 (agreement x correctness), n=20:")
    print(f"  AGREE & both correct        : {both_ok_agree}")
    print(f"  AGREE & BOTH WRONG          : {both_wrong_agree}   <-- key cell")
    print(f"  DISAGREE, CodeFormula only  : {cf_only}")
    print(f"  DISAGREE, pix2tex only      : {p2_only}")
    print(f"  DISAGREE, both wrong        : {both_wrong_disagree}")
    assert both_ok_agree + both_wrong_agree + cf_only + p2_only + both_wrong_disagree == n

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows, "totals": {
            "n": n, "agree": n_agree, "codeformula_correct": n_cf_ok, "pix2tex_correct": n_p2_ok,
            "agree_both_correct": both_ok_agree, "agree_both_wrong": both_wrong_agree,
            "disagree_codeformula_only": cf_only, "disagree_pix2tex_only": p2_only,
            "disagree_both_wrong": both_wrong_disagree,
        }}, fh, indent=1, ensure_ascii=False)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
