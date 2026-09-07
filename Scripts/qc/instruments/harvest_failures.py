"""harvest_failures.py — what broke, how often, and whether we ever worked out why.

THE MOST EXPENSIVE KNOWLEDGE IN THE PROJECT HAS NO HOME. A run that dies costs GPU
hours; working out WHY costs a session. That understanding currently survives as prose
in CHATLOG entries (22 entries, exactly one with a structured `bugs:` field), nine
hand-curated gotchas in CLAUDE.md that cannot grow because every line costs context in
every session, and commit messages nobody greps. So the same failure gets rediscovered.

Two layers, the same split the experiment registry uses:

    HARVESTED (this script)   phase4/qc/failure_registry.csv — the SYMPTOMS, counted:
                              exception class, normalised signature, how many times,
                              first and last seen, which steps/years/tags, an example
                              log to open. Facts, from `errors: N>0` step logs.

    AUTHORED (a human)        qc/known_failures.yaml — the CAUSE and the FIX, matched
                              onto a symptom by regex. This is the part no script can
                              derive, and it is exactly the part worth writing down.

A symptom with no authored match is published with an EMPTY cause and status
`undiagnosed`. That is the point: undiagnosed failures become a visible to-do list
(`py -3.12 qc/ask.py --gaps`) instead of quietly recurring.

SIGNATURES ARE NORMALISED so the same bug counts as one row across runs: absolute
paths, hex ids, timestamps, tile/pixel counts and line numbers are replaced with
placeholders. Over-normalising would merge distinct bugs, so only the volatile parts
go — the exception class and the message's shape are preserved.

Run:  py -3.12 qc/instruments/harvest_failures.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
KNOWN = SCRIPTS / "qc" / "known_failures.yaml"

COLS = ["failure_id", "exception_class", "signature", "n_occurrences",
        "first_seen", "last_seen", "steps", "years", "run_tags",
        "status", "cause", "fix", "fix_commit", "example_log", "notes"]

# Volatile substrings that must not split one bug into many rows.
_NORMALISERS = (
    (re.compile(r"[A-Za-z]:[\\/][^\s'\"]+"), "<path>"),          # windows abs path
    (re.compile(r"/(?:content|usr|tmp|home)/[^\s'\"]+"), "<path>"),
    (re.compile(r"\b[0-9a-f]{8,}\b"), "<hex>"),
    (re.compile(r"\b\d{8}T\d{6}Z\b"), "<ts>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<date>"),
    (re.compile(r"\bline \d+\b"), "line <n>"),
    (re.compile(r"\b\d{3,}\b"), "<n>"),
)


def normalise(msg):
    s = " ".join(str(msg).split())
    for pat, repl in _NORMALISERS:
        s = pat.sub(repl, s)
    return s[:180]


def parse_log(text):
    """Return (exception_class, message, step, year, run_tag, date) or None."""
    if not re.search(r"^errors:\s+[1-9]", text, re.M):
        return None
    exc = re.findall(r"^([A-Za-z_][\w.]*(?:Error|Exception)[\w]*):\s*(.*)$",
                     text, re.M)
    cls, msg = exc[-1] if exc else ("(no exception class)", "")
    if not exc:
        m = re.search(r"^EXCEPTION:\s*(.*)$", text, re.M)
        msg = m.group(1) if m else ""
    step = (re.search(r"--step\s+(\S+)", text) or
            re.search(r"=== \S+ --step (\S+) ===", text))
    year = re.search(r"--year\s+(\S+)", text)
    tag = re.search(r"--run-tag\s+(\S+)", text)
    date = re.search(r"^started:\s+(\d{4}-\d{2}-\d{2})", text, re.M)
    return (cls, msg,
            step.group(1) if step else "",
            year.group(1) if year else "",
            tag.group(1) if tag else "",
            date.group(1) if date else "")


def load_known():
    if not KNOWN.exists():
        return []
    import yaml
    spec = yaml.safe_load(KNOWN.read_text(encoding="utf-8")) or {}
    out = []
    for f in spec.get("failures", []):
        try:
            f["_re"] = re.compile(f["match"], re.I)
        except re.error as e:
            print(f"  ! known_failures.yaml: bad regex {f.get('match')!r}: {e}")
            continue
        out.append(f)
    return out


def _logs_dir(explicit=None):
    if explicit:
        return Path(explicit)
    from phase4seg import config
    for cand in (Path(config.BASE) / "phase4" / "logs",
                 Path(r"G:/My Drive/treedata/phase4/logs")):
        if cand.exists():
            return cand
    return cand


def harvest(logs_dir, known):
    groups = {}
    for p in sorted(Path(logs_dir).glob("*.log")):
        try:
            parsed = parse_log(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not parsed:
            continue
        cls, msg, step, year, tag, date = parsed
        sig = normalise(msg)
        key = (cls, sig)
        g = groups.setdefault(key, {"n": 0, "dates": [], "steps": set(),
                                    "years": set(), "tags": set(), "example": p.name})
        g["n"] += 1
        if date:
            g["dates"].append(date)
        for s, v in (("steps", step), ("years", year), ("tags", tag)):
            if v:
                g[s].add(v)

    rows = []
    for (cls, sig), g in groups.items():
        hit = next((k for k in known
                    if k["_re"].search(sig) or k["_re"].search(cls)), None)
        dates = sorted(g["dates"])
        rows.append({
            # STABLE across processes: builtin hash() is salted per interpreter
            # (PYTHONHASHSEED), so ids churned on every harvest and the auto-harvest
            # rung produced a spurious diff on a file nothing had changed. Caught
            # 2026-09-06 by that rung, the first time it ran.
            "failure_id": f"{cls.split('.')[-1].lower()}-"
                          f"{hashlib.sha256(sig.encode('utf-8')).hexdigest()[:6]}",
            "exception_class": cls, "signature": sig, "n_occurrences": g["n"],
            "first_seen": dates[0] if dates else "", "last_seen": dates[-1] if dates else "",
            "steps": ",".join(sorted(g["steps"])), "years": ",".join(sorted(g["years"])),
            "run_tags": ",".join(sorted(g["tags"]))[:80],
            "status": (hit or {}).get("status", "undiagnosed"),
            "cause": (hit or {}).get("cause", ""),
            "fix": (hit or {}).get("fix", ""),
            "fix_commit": (hit or {}).get("commit", ""),
            "example_log": g["example"], "notes": (hit or {}).get("notes", ""),
        })
    rows.sort(key=lambda r: (-int(r["n_occurrences"]), r["exception_class"]))
    return rows


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--logs-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    logs_dir = _logs_dir(a.logs_dir)
    if not logs_dir.exists():
        print(f"FATAL: logs not found: {logs_dir} — this reads the lake")
        return 2

    known = load_known()
    rows = harvest(logs_dir, known)
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not a.dry_run:
        QC.mkdir(parents=True, exist_ok=True)
        (QC / "failure_registry.csv").write_text(buf.getvalue(), encoding="utf-8",
                                                 newline="")

    und = [r for r in rows if r["status"] == "undiagnosed"]
    print(f"{'DRY RUN: ' if a.dry_run else ''}{len(rows)} distinct failures over "
          f"{sum(int(r['n_occurrences']) for r in rows)} failed steps "
          f"→ phase4/qc/failure_registry.csv")
    print(f"  diagnosed {len(rows) - len(und)} · UNDIAGNOSED {len(und)} "
          f"({len(known)} patterns in qc/known_failures.yaml)")
    for r in und[:8]:
        print(f"  ! {r['exception_class']:28} x{r['n_occurrences']:<3} "
              f"{r['signature'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
