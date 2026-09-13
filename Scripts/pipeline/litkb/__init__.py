"""litkb — the literature knowledge base (design: Scripts/LITERATURE_KB_DESIGN_2026-09-13.md).

P1 "Foundation" lives here: the PostgreSQL schema (plain SQL migrations under
db/migrations), the migration runner (db/migrate.py), one-time server provisioning
(db/provision.py) and the git side of promotion (promote.py).

Import weight is a gated contract (design §9, referee M9): importing this package, or
any module in it, must not import psycopg, torch, Docling or any other heavy library.
Drivers are imported inside the functions that use them. Test:
qc/test_litkb_p1.py, test_import_litkb_pulls_no_heavy_dependency.
"""
