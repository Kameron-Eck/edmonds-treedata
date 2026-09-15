"""P3 — the legacy tracker and manifest loaded into the knowledge base THROUGH admission.

Design §13: "All loaders go through the P2 admission code (§4.6) — migration is admission in bulk,
not a bypass." Nothing in this package inserts a work, an identifier or a file directly; every row
reaches the database through `litkb.admit.front` and `litkb.record_discrepancy`.

decisions.yaml `litkb-p0-foundation`, "P3 load (Kam, 2026-09-14)":
  * identity comes from the REGISTRY RECORD and the VERIFIED FILE — never from the tracker's claim;
  * every tracker or manifest field that disagrees with the registry is kept as a flagged
    discrepancy for later review, nothing dropped;
  * no correction pass on the old tracker before loading;
  * ±1 year only with title AND first author (the P2 rule, unchanged; this package never re-implements it);
  * a file refused at binding waits for OCR (§15.14) — it is not admitted by another route.

P3 is a LOAD, not a hunt: no archive download is made here, so a row with no file on disk stays unbound.
"""
from litkb.migrate_legacy.plan import CASES, plan_row  # noqa: F401
from litkb.migrate_legacy.run import load_manifest, load_tracker  # noqa: F401
