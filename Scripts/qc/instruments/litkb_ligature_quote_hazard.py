r"""Item 1(b) measurement: WOULD normalising a block's text in place invalidate a recorded use's
quote? Read-only against live litkb to build a bounded, guaranteed-inclusion sample; every write
happens on the worker database litkb_test_w11 (never live).

    PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_ligature_quote_hazard.py

Measured first (see this script's own printed lines and qc/instruments/litkb_ligature_c0.py): of
the 8 use_evidence rows that exist anywhere in live litkb today, ZERO reference a current-run block
that carries a ligature C0 byte. So there is nothing live to break RIGHT NOW -- but that is a
statement about today's tiny recorded-use corpus, not about the mechanism, and the mechanism is
what a normaliser would exercise on every future use recorded against an unnormalised block. This
measures the mechanism concretely: real block text from real affected files, run through the
DATABASE'S OWN verification trigger (`litkb._use_evidence_verify`, migration 0007), not a
hand-rolled comparison.

Sample (bounded, guaranteed inclusion):
  * CONTROL group: the 8 real use_evidence rows, verbatim (quote/offsets/block), copied to w11.
    None of their blocks carry a C0 byte -- they must show ZERO flips, or something is wrong with
    the harness itself, not with normalisation.
  * AFFECTED group: every block in the litkb_ligature_c0_2026-09-19.csv conflict row (file
    01a0a4d6-6db4-7343-965a-aca7b3c090d4, byte 0x1, which that instrument found resolving to BOTH
    "ff" and "fi" in the same file) plus a capped, evenly-spread sample across resolved / ambiguous
    / unresolved rows from that CSV (guarantees inclusion of a byte the instrument could actually
    place, one it could not, and the one proven-ambiguous case). For each affected block this
    script SYNTHESISES three use_evidence rows -- there are no real ones to draw on -- covering the
    three positions a quote can take relative to the block's first C0 byte: entirely BEFORE it,
    SPANNING it, and entirely AFTER it. This is real block text with an invented use recorded
    against it (labelled synthetic in the CSV and in this docstring); it is not a claim that these
    uses exist.

Mechanism exercised: insert real+synthetic use_evidence rows through the live table (the BEFORE
INSERT trigger computes quote_verified for real -- this IS the baseline, not a copy of it); apply a
STATED placeholder ligature expansion to the affected blocks' text only (byte -> ligature per the
C0 instrument's resolved majority where it has one, else a stated default "fi" -- explicitly NOT a
validated general mapping, see that instrument); then force the SAME trigger to re-run by
`UPDATE use_evidence SET stance = stance` (a no-op value change that still re-fires a BEFORE UPDATE
trigger) and read what it recomputed. quote_verified before vs. after is the database's own answer,
twice.

Output: Reports/litkb_ligature_quote_hazard_2026-09-19.csv, one row per use_evidence row, plus a
stdout summary of flips by position class (before / spanning / after / control) and whether the
original quote text can still be found anywhere in the block after normalisation (distinguishing
"stale offsets, text still there" from "the quote text is simply gone").
"""
import csv
import sys
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
C0_CSV = SCRIPTS.parent / "Reports" / "litkb_ligature_c0_2026-09-19.csv"
OUT = SCRIPTS.parent / "Reports" / "litkb_ligature_quote_hazard_2026-09-19.csv"
WORKER_DB = "litkb_test_w11"

C0 = "\x01-\x08\x0b\x0c\x0e-\x1f"
C0_SET = set(range(0x01, 0x09)) | {0x0b, 0x0c} | set(range(0x0e, 0x20))

# The C0 instrument's resolved byte->ligature MAJORITY (litkb_ligature_c0_2026-09-19.csv), used
# here as a STATED PLACEHOLDER for the normalisation edit -- not proposed as a validated general
# table (that instrument found a same-file, same-byte conflict; see its docstring).
PLACEHOLDER = {0x01: "fi", 0x04: "ffi", 0x1f: "ff", 0x1e: "fi", 0x1c: "ffi", 0x06: "fi"}
DEFAULT_PLACEHOLDER = "fi"

CONFLICT_FILE = "01a0a4d6-6db4-7343-965a-aca7b3c090d4"
SAMPLE_CAP_PER_STATUS = 5


def fetch_dicts(conn, sql, args=()):
    """Rows as dicts, every uuid.UUID value stringified so the CSV-sourced str ids in the affected
    sample and the driver-native UUID objects from live compare and key equal throughout."""
    cur = conn.execute(sql, args)
    cols = [d.name for d in cur.description]
    return [{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in zip(cols, row)}
            for row in cur.fetchall()]


def bulk_insert(conn, table, rows):
    if not rows:
        return
    from psycopg.types.json import Jsonb

    rows = [{k: (Jsonb(v) if isinstance(v, dict) else v) for k, v in r.items()} for r in rows]
    cols = list(rows[0].keys())
    placeholders = ", ".join(f"%({c})s" for c in cols)
    collist = ", ".join(f'"{c}"' for c in cols)
    with conn.cursor() as cur:
        cur.executemany(f'INSERT INTO litkb."{table}" ({collist}) VALUES ({placeholders})', rows)


def normalize(text):
    out = []
    for ch in text:
        cp = ord(ch)
        out.append(PLACEHOLDER.get(cp, DEFAULT_PLACEHOLDER) if cp in C0_SET else ch)
    return "".join(out)


def pick_affected_sample():
    """-> list of (file_id, block_id) from the C0 instrument's CSV: the known conflict block pair,
    plus up to SAMPLE_CAP_PER_STATUS per status (resolved/ambiguous/unresolved) for breadth."""
    rows = list(csv.DictReader(open(C0_CSV, encoding="utf-8", newline="")))
    conflict = [(r["file_id"], r["block_id"]) for r in rows if r["file_id"] == CONFLICT_FILE]
    by_status = {}
    for r in rows:
        by_status.setdefault(r["status"], []).append((r["file_id"], r["block_id"]))
    sample = list(dict.fromkeys(conflict))  # dedupe, keep order
    for status in ("resolved", "ambiguous", "unresolved"):
        for pair in by_status.get(status, [])[:SAMPLE_CAP_PER_STATUS]:
            if pair not in sample:
                sample.append(pair)
    return sample


def main():
    from litkb.db import connect as c

    live = c.connect(c.DB_MAIN, "litkb_reader", autocommit=True)
    worker = c.connect(WORKER_DB, "litkb_test", autocommit=False)

    try:
        # ---- control group: the real use_evidence rows, verbatim ----
        control_evidence = fetch_dicts(live, "SELECT * FROM litkb.use_evidence")
        control_block_ids = sorted({r["block_id"] for r in control_evidence})
        print(f"measured: {len(control_evidence)} real use_evidence rows (control group), "
              f"{len(control_block_ids)} distinct blocks")

        # ---- affected group: bounded, guaranteed-inclusion sample from the C0 instrument's CSV ----
        affected_pairs = pick_affected_sample()
        affected_block_ids = [bid for _, bid in affected_pairs]
        print(f"measured: {len(affected_pairs)} affected blocks sampled "
              f"(conflict file {CONFLICT_FILE} guaranteed in the set)")

        all_block_ids = sorted(set(control_block_ids) | set(affected_block_ids))
        blocks = fetch_dicts(live, "SELECT * FROM litkb.blocks WHERE id = ANY(%s::uuid[])", (all_block_ids,))
        block_by_id = {b["id"]: b for b in blocks}
        file_ids = sorted({b["file_id"] for b in blocks})
        files = fetch_dicts(live, "SELECT * FROM litkb.files WHERE id = ANY(%s::uuid[])", (file_ids,))
        run_ids = sorted({b["run_id"] for b in blocks} | {f["current_run_id"] for f in files if f["current_run_id"]})
        runs = fetch_dicts(live, "SELECT * FROM litkb.extraction_runs WHERE id = ANY(%s::uuid[])", (run_ids,))
        print(f"measured: FK closure needs {len(blocks)} blocks, {len(files)} files, {len(runs)} extraction_runs")

        # ---- build the worker DB scaffold: one dummy workstream/work/use/use_version ----
        ws = fetch_dicts(worker, "INSERT INTO litkb.workstreams (slug, git_branch, purpose) "
                          "VALUES ('ligature-hazard-sample', 'work/20260919-ligature', "
                          "'Item 1(b) bounded quote-hazard sample') RETURNING id")[0]["id"]
        work = fetch_dicts(worker, "INSERT INTO litkb.works (key, created_in_ws) "
                            "VALUES ('Ligaturehazard_2026_sample-work', %s) RETURNING id", (ws,))[0]["id"]
        use = fetch_dicts(worker, "INSERT INTO litkb.uses (work_id, created_in_ws) "
                           "VALUES (%s, %s) RETURNING id", (work, ws))[0]["id"]
        uv = fetch_dicts(worker,
            "INSERT INTO litkb.use_versions (use_id, version_no, statement, kind, status, "
            "workstream_id, agent, session_id) VALUES (%s, 1, 'sample use for Item 1(b)', "
            "'context', 'proposed', %s, 'ligature-builder', 'session-ligature-1b') "
            "RETURNING version_id", (use, ws))[0]["version_id"]

        # ---- copy files / extraction_runs / blocks verbatim, redirecting FKs the sample doesn't
        # carry (created_in_ws -> our dummy workstream; current_version_id -> NULL, no file_versions
        # in this sample). files_current_run_fk is NOT deferrable, so files must land with
        # current_run_id NULL, then extraction_runs, then the pointer moves -- the same order
        # set_current_run() imposes in production. ----
        current_run_by_file = {f["id"]: f["current_run_id"] for f in files}
        for f in files:
            f["created_in_ws"] = ws
            f["current_version_id"] = None
            f["current_run_id"] = None
        bulk_insert(worker, "files", files)
        bulk_insert(worker, "extraction_runs", runs)
        with worker.cursor() as cur:
            cur.executemany("UPDATE litkb.files SET current_run_id = %s WHERE id = %s",
                            [(run_id, file_id) for file_id, run_id in current_run_by_file.items() if run_id])
        for b in blocks:
            b["parent_block_id"] = None  # avoid pulling in parents outside the bounded sample
        bulk_insert(worker, "blocks", blocks)
        print(f"copied {len(files)} files, {len(runs)} runs, {len(blocks)} blocks into {WORKER_DB}")

        # ---- use_evidence: control rows verbatim, affected rows synthesised ----
        evidence_rows = []
        position_by_key = {}  # (block_id, char_start, char_end) -> "before"/"spanning"/"after"/"control"
        for r in control_evidence:
            row = dict(use_version_id=uv, block_id=r["block_id"], run_id=r["run_id"], page=r["page"],
                      quote=r["quote"], char_start=r["char_start"], char_end=r["char_end"],
                      stance=r["stance"])
            evidence_rows.append(row)
            position_by_key[(row["block_id"], row["char_start"], row["char_end"])] = "control"

        QLEN = 24
        for file_id, block_id in affected_pairs:
            text = block_by_id[block_id]["text"]
            first_c0 = next((i for i, ch in enumerate(text) if ord(ch) in C0_SET), None)
            if first_c0 is None:
                continue
            run_id = block_by_id[block_id]["run_id"]
            page_no = block_by_id[block_id]["page_no"]
            spans = {}
            if first_c0 >= QLEN:
                spans["before"] = (first_c0 - QLEN, first_c0)
            lo = max(0, first_c0 - QLEN // 2)
            hi = min(len(text), first_c0 + QLEN // 2 + 1)
            if lo < first_c0 < hi:
                spans["spanning"] = (lo, hi)
            if len(text) - (first_c0 + 1) >= QLEN:
                spans["after"] = (first_c0 + 1, first_c0 + 1 + QLEN)
            for position, (s, e) in spans.items():
                quote = text[s:e]
                if not quote:
                    continue
                row = dict(use_version_id=uv, block_id=block_id, run_id=run_id, page=page_no,
                          quote=quote, char_start=s, char_end=e, stance="context")
                evidence_rows.append(row)
                position_by_key[(block_id, s, e)] = position

        bulk_insert(worker, "use_evidence", [{k: v for k, v in r.items()} for r in evidence_rows])
        worker.commit()

        baseline_rows = fetch_dicts(
            worker, "SELECT id, block_id, quote, char_start, char_end, quote_verified FROM litkb.use_evidence")
        # keyed by (block_id, char_start, char_end): quote TEXT is not guaranteed unique across rows
        baseline_by_key = {(r["block_id"], r["char_start"], r["char_end"]): r for r in baseline_rows}
        print(f"inserted {len(evidence_rows)} use_evidence rows into {WORKER_DB}; "
              f"baseline quote_verified computed by the REAL trigger on insert")

        control_bad = [r for r in baseline_rows
                       if r["block_id"] in control_block_ids and not r["quote_verified"]]
        if control_bad:
            print(f"WARNING: {len(control_bad)} control rows failed verification on the UNMODIFIED "
                  f"copy -- harness bug, investigate before trusting anything else below")

        # ---- apply the stated placeholder normalisation to AFFECTED blocks only ----
        new_text_by_block = {}
        for _, block_id in affected_pairs:
            old = block_by_id[block_id]["text"]
            new_text_by_block[block_id] = normalize(old)
        with worker.cursor() as cur:
            cur.executemany("UPDATE litkb.blocks SET text = %s WHERE id = %s",
                            [(t, bid) for bid, t in new_text_by_block.items()])
        worker.commit()
        print(f"normalised {len(new_text_by_block)} affected blocks' text on {WORKER_DB} "
              f"(control blocks untouched)")

        # ---- re-fire the REAL trigger: a no-op value UPDATE still re-runs BEFORE UPDATE ----
        with worker.cursor() as cur:
            cur.execute("UPDATE litkb.use_evidence SET stance = stance")
        worker.commit()

        after = fetch_dicts(worker, "SELECT ue.id, ue.block_id, ue.quote, ue.char_start, ue.char_end, "
                            "ue.quote_verified, b.text AS block_text FROM litkb.use_evidence ue "
                            "JOIN litkb.blocks b ON b.id = ue.block_id")

        out_rows = []
        flips_true_to_false = flips_false_to_true = 0
        for a in after:
            key = (a["block_id"], a["char_start"], a["char_end"])
            base = baseline_by_key.get(key)
            is_control = a["block_id"] in control_block_ids
            still_findable = a["quote"] in a["block_text"]
            new_offset = a["block_text"].find(a["quote"]) if still_findable else -1
            offset_shifted = still_findable and new_offset != a["char_start"]
            flip = None
            if base is not None and base["quote_verified"] != a["quote_verified"]:
                flip = f"{base['quote_verified']}->{a['quote_verified']}"
                if base["quote_verified"] and not a["quote_verified"]:
                    flips_true_to_false += 1
                elif not base["quote_verified"] and a["quote_verified"]:
                    flips_false_to_true += 1
            out_rows.append(dict(
                use_evidence_id=str(a["id"]), block_id=str(a["block_id"]),
                group="control" if is_control else "affected",
                position=position_by_key.get(key, "?"),
                baseline_quote_verified=base["quote_verified"] if base else None,
                after_normalize_quote_verified=a["quote_verified"], flip=flip or "",
                quote_still_findable=still_findable, offset_shifted=offset_shifted,
                original_char_start=a["char_start"], new_found_offset=new_offset))

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            w.writerows(out_rows)

        control_flips = sum(1 for r in out_rows if r["group"] == "control" and r["flip"])
        affected_flips = sum(1 for r in out_rows if r["group"] == "affected" and r["flip"])
        print(f"control group flips (must be 0): {control_flips}")
        print(f"affected group: {len(out_rows) - len([r for r in out_rows if r['group']=='control'])} rows, "
              f"{affected_flips} flips ({flips_true_to_false} true->false, {flips_false_to_true} false->true)")
        for pos in ("before", "spanning", "after"):
            rows_p = [r for r in out_rows if r["group"] == "affected" and r["position"] == pos]
            flips_p = sum(1 for r in rows_p if r["flip"])
            print(f"  position={pos}: {len(rows_p)} rows, {flips_p} flips")
        shifted = sum(1 for r in out_rows if r["group"] == "affected" and r["offset_shifted"])
        gone = sum(1 for r in out_rows if r["group"] == "affected" and not r["quote_still_findable"])
        print(f"affected rows where the original quote text is simply GONE from the block: {gone}")
        print(f"affected rows where the quote text still exists but at a SHIFTED offset: {shifted}")
        print(f"wrote {OUT} ({len(out_rows)} rows)")
        return 0
    except BaseException:
        # a client-side adaptation error never touches the server transaction, so an unconditional
        # commit() in a bare `finally` would still persist whatever ran before it (found the hard
        # way: a failed run left an 'open' scaffold workstream behind and broke the next run's
        # unique slug). Roll back on ANY exception instead.
        worker.rollback()
        raise
    finally:
        worker.close()
        live.close()


if __name__ == "__main__":
    sys.exit(main())
