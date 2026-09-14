"""litkb.admit — admission checks 1-5 (design §4.6): the resolver (gate 0, ported from aa_fetch), registry
confirmation (check 1), file binding (check 3) and the Python front of litkb.admit() / approve_admission()
(migration 0013). Stdlib at import; psycopg is imported inside the functions that use it."""
