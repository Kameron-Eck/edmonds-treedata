"""verify_claims.py — re-resolve every claim's evidence and report drift.

`py -3.12 qc/verify_claims.py` after any campaign that could move a number. A DRIFTED
claim is not corrected automatically: which side is wrong — the measurement, or the
sentence built on it — is a judgement, and `stated_in` lists every place that would
have to change.

Exit 1 if anything drifted or errored, so it can gate a commit.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # ledger: test_status_discovery
import claims as _claims                                    # noqa: E402


def main():
    results = _claims.verify_all()
    if not results:
        print("no claims registered (Scripts/claims.yaml)")
        return 0
    bad = 0
    for c, state, detail in results:
        mark = {"ok": "  ok  ", "drifted": " DRIFT", "unresolved": "  ?   ",
                "error": " ERROR"}[state]
        print(f"{mark}  {c['id']:34} {str(detail)[:56]}")
        if state in ("drifted", "error"):
            bad += 1
            for where in (c.get("stated_in") or []):
                print(f"          fix or re-state in: {where}")
    print(f"\n{len(results)} claims · {bad} needing attention")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
