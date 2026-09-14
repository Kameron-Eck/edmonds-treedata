"""secrets_check.py — refuse secrets in git's index. (decisions.yaml litkb-p0-foundation; litkb design §10:
"a check in the ladder fails if a key file, .env or pgpass is staged".)

    py -3.12 Scripts/qc/secrets_check.py              the repository this file lives in
    py -3.12 Scripts/qc/secrets_check.py --repo PATH  another repository

It reads git's INDEX, not the working tree: the index is exactly what the next commit will contain,
so one pass covers every tracked file and every staged change (a staged edit replaces the tracked blob).
Stdlib only. Exit 0 = clean, 1 = findings, 2 = git failed. A finding names the file, the line and the
rule; it never prints the matched value.

Rules
  name     basename *.pgpass, pgpass.conf, .env, *.env, .litkb-workstream; or any path under a secrets/ folder
  pgpass   a line that is exactly host:port:database:user:password with a numeric (or *) port and a
           password of 16+ non-space characters (libpq's pgpass format)
  token    a 64-hex-digit value assigned (= or :) to a name containing token, secret, api_key/apikey,
           password/passwd/pwd, bearer or auth (sha256 digests under other names are not flagged)

Allowlisting, always with a stated reason:
  * a line carrying `secrets-check: allow <reason>` is skipped by the token rule (a pgpass line cannot
    carry the pragma: anything after the password breaks its shape, so the pgpass rule never matches it);
  * ALLOW_PATHS below maps a path to its reason (none needed on 2026-09-13).

As a pre-commit hook. Not installed: .git/hooks is shared by every worktree of this repository, so
installing it here would change every other session's commits. To install it yourself (reversible by
deleting the file):
    printf '#!/bin/sh\\nexec py -3.12 Scripts/qc/secrets_check.py\\n' > "$(git rev-parse --git-common-dir)/hooks/pre-commit"
"""
import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

NAME_PATTERNS = ("*.pgpass", "pgpass.conf", ".env", "*.env", ".litkb-workstream")
SECRET_DIR = "secrets"
ALLOW_PATHS = {}   # "repo/relative/path": "reason it is not a secret"

# host, database and user exclude commas: without that, CSV rows of UTC timestamps
# (`x,,2026-09-09T12:06:08Z,...`) read as host:port:db:user:password — 82 false findings in
# phase4/qc/runtime_sessions.csv on the first run, 2026-09-13
PGPASS_RE = re.compile(r"^[ \t]*[^\s:#,]+:(?:\d{1,5}|\*):[^\s:,]+:[^\s:,]+:\S{16,}[ \t]*\r?$", re.M)
# starts AT the keyword, not at a `[\w.-]*` name prefix: that prefix backtracked over every word in
# every file and made the rung take 23 s on 1139 files (2026-09-13)
TOKEN_RE = re.compile(
    r"(?i)(?:token|secret|api[_-]?key|apikey|passw(?:or)?d|pwd|bearer|auth)[A-Za-z0-9_.-]*"
    r"[\"']?\s*[:=]\s*[\"']?(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
ALLOW_RE = re.compile(r"secrets-check:\s*allow\s+\S.{3,}")
MAX_BYTES = 50 * 1024 * 1024


def _git(repo, *args, data=None):
    r = subprocess.run(["git", "-C", str(repo), *args], input=data, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def index_entries(repo):
    """[(blob_sha, path)] for every stage-0 entry in the index, submodules excluded."""
    out = []
    for rec in _git(repo, "ls-files", "-s", "-z").split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, sha, _stage = meta.split()
        if mode != b"160000":
            out.append((sha.decode(), path.decode("utf-8", "replace")))
    return out


def read_blobs(repo, shas):
    """{sha: bytes} through one `git cat-file --batch`."""
    uniq = list(dict.fromkeys(shas))
    raw = _git(repo, "cat-file", "--batch", data=("\n".join(uniq) + "\n").encode()) if uniq else b""
    blobs, pos = {}, 0
    while pos < len(raw):
        nl = raw.index(b"\n", pos)
        header = raw[pos:nl].split()
        sha, size = header[0].decode(), int(header[2])
        blobs[sha] = raw[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1
    return blobs


def name_finding(path):
    p = PurePosixPath(path)
    base = p.name.lower()
    if any(fnmatch.fnmatchcase(base, pat) for pat in NAME_PATTERNS):
        return f"name: '{p.name}' is a secrets file name"
    if SECRET_DIR in (part.lower() for part in p.parts[:-1]):
        return f"name: under a {SECRET_DIR}/ folder"
    return None


def content_findings(text):
    """[(line_no, rule)] — never the matched value."""
    found = []
    for rule, rx in (("pgpass", PGPASS_RE), ("token", TOKEN_RE)):
        for m in rx.finditer(text):
            start = text.rfind("\n", 0, m.start()) + 1
            end = text.find("\n", m.end())
            line = text[start:end if end != -1 else len(text)]
            if ALLOW_RE.search(line):
                continue
            found.append((text.count("\n", 0, m.start()) + 1, rule))
    return sorted(set(found))


def scan(repo):
    entries = [(sha, path) for sha, path in index_entries(repo) if path not in ALLOW_PATHS]
    findings = [(path, 0, why) for _sha, path in entries if (why := name_finding(path))]
    blobs = read_blobs(repo, [sha for sha, _p in entries])
    for sha, path in entries:
        data = blobs.get(sha, b"")
        if len(data) > MAX_BYTES or b"\0" in data[:8192]:
            continue   # binary (or huge): the content rules are line-oriented text rules
        text = data.decode("utf-8", "replace")
        for line_no, rule in content_findings(text):
            hint = ("a pgpass line (host:port:db:user:password, password 16+ chars)" if rule == "pgpass"
                    else "a 64-hex value assigned to a token-like name")
            findings.append((path, line_no, f"{rule}: {hint}"))
    return len(entries), findings


def main(argv=None):
    ap = argparse.ArgumentParser(description="refuse secrets in git's index (tracked + staged files)")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        n, findings = scan(a.repo)
    except RuntimeError as e:
        print(f"secrets_check: {e}")
        return 2
    for path, line_no, why in findings:
        print(f"  {path}{f':{line_no}' if line_no else ''}: {why}")
    if findings:
        print(f"secrets_check: REFUSED — {len(findings)} finding(s) in {n} indexed files. Unstage the file "
              "(git rm --cached <path>), move the secret out of the repository, or allowlist with a reason.")
        return 1
    print(f"secrets_check: clean — {n} indexed files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
