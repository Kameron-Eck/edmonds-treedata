r"""colab_readopt.py — re-adopt an orphaned Colab CLI assignment under a name (overhaul P11.6).

WHY THIS EXISTS (measured 2026-08-22, mid-run, with two A100s live):
`colab_cli.common.sync_sessions()` prunes every local session whose endpoint is
absent from the CURRENT `list_assignments()` response. One partial or transient
list — the VMs live in different regions (A was asia-southeast1, B us-central1) —
therefore deletes that name from `~/.config/colab-cli/sessions.json` FOREVER. The
VM keeps running and BILLING, but `colab exec/status/stop -s NAME` can no longer
reach it and it shows up as a `[?]` orphan. Every `colab sessions` call runs that
prune, so a monitoring loop polling it is the likeliest trigger (which is why
`qc/runtime_dashboard.py` reads the store file directly instead).

This rebuilds the local entry from the server's own assignment list, which carries
a fresh `runtime_proxy_info` (url + token) for every live assignment. No new VM,
no GPU spend, no browser. Afterwards `colab exec/status/stop -s NAME` work again —
including the `colab stop` that ends the billing.

Runs on the CLI's own interpreter (it imports `colab_cli`, installed by uv), e.g.

    <uv-tools>\google-colab-cli\Scripts\python.exe qc/colab_readopt.py --list
    <uv-tools>\google-colab-cli\Scripts\python.exe qc/colab_readopt.py \
        --endpoint gpu-a100-s-kkb-... --name A2 [--dry-run]

The uv tool path on this machine is in OVERHAUL_PLAN_2026-08-20.md P11.6 (it is
also an allowed Bash prefix in the P11.5 permission block).
"""
import argparse
import base64
import json
import subprocess
import sys
import time

from colab_cli.common import state
from colab_cli.state import SessionState
from phase4seg.names import clean_argv  # noqa: E402

TOKEN_TTL_MARGIN_S = 25 * 60      # refresh when under this much life remains


def _token_expiry(tok):
    """Unix expiry of a runtime-proxy JWT, or None if it cannot be read."""
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:                                       # noqa: BLE001
        return None


def _alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                             capture_output=True, text=True, timeout=20).stdout
        return str(pid) in out
    except (OSError, ValueError, subprocess.SubprocessError):
        return True                                        # unknown: do not respawn blindly


def _spawn_daemon(endpoint, name):
    from colab_cli.commands.session import spawn_keep_alive
    return spawn_keep_alive(endpoint, name, auth_provider=state.auth_provider)


def heal(assignments, prefix="heal"):
    """Keep every live assignment reachable, heartbeated, and stoppable by name.

    Three failure modes, all measured on 2026-08-22, all of which end with Colab
    reclaiming a computing VM ~15-25 min later:
      * the CLI PRUNES a session on any transient error (a 404 from /api/kernels was
        enough) — entry deleted AND its keep-alive daemon killed;
      * a session's runtime-proxy token lives exactly 1 h, after which every `colab
        exec` fails and triggers that same cleanup;
      * a re-adopted entry has no daemon unless one is spawned for it.
    So: re-adopt orphans, refresh tokens before they lapse, respawn dead daemons.
    """
    local = state.store.list() or {}
    by_ep = {s.endpoint: (n, s) for n, s in local.items()}
    now = int(time.time())
    acted = []
    for a in assignments:
        ep = a.endpoint
        fresh = a.runtime_proxy_info
        if ep in by_ep:
            name, s = by_ep[ep]
            exp = _token_expiry(s.token)
            if exp is None or exp - now < TOKEN_TTL_MARGIN_S:
                s.token, s.url = fresh.token, fresh.url
                state.store.add(s)
                acted.append(f"{name}: token refreshed (was expiring "
                             f"{'unknown' if exp is None else f'in {(exp - now) // 60} min'})")
            if not _alive(s.keep_alive_pid):
                s.keep_alive_pid = _spawn_daemon(ep, name)
                state.store.add(s)
                acted.append(f"{name}: keep-alive daemon respawned (pid {s.keep_alive_pid})")
        else:
            name = f"{prefix}-{ep.split('-')[-1][:8]}"
            s = SessionState(name=name, token=fresh.token, url=fresh.url, endpoint=ep,
                             variant=str(getattr(a.variant, "name", a.variant)),
                             accelerator=str(getattr(a.accelerator, "name", a.accelerator)))
            state.store.add(s)
            s.keep_alive_pid = _spawn_daemon(ep, name)
            state.store.add(s)
            acted.append(f"{name}: ORPHAN re-adopted -> {ep} (daemon pid {s.keep_alive_pid})")
    return acted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", help="endpoint id, from `colab sessions` or --list")
    ap.add_argument("--name", help="local name to bind it to (avoid a name already in use)")
    ap.add_argument("--list", action="store_true", help="only list live server-side assignments")
    ap.add_argument("--heal", action="store_true",
                    help="re-adopt orphans, refresh tokens nearing their 1 h expiry, respawn dead "
                         "keep-alive daemons (safe to run on a schedule; changes nothing when healthy)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written, write nothing")
    a = ap.parse_args(clean_argv())

    assignments = state.client.list_assignments()
    known = {s.endpoint: n for n, s in (state.store.list() or {}).items()}
    print("live assignments:")
    for x in assignments:
        print(f"   {x.endpoint}  {getattr(x.accelerator, 'name', x.accelerator)}  "
              f"{getattr(x.variant, 'name', x.variant)}  "
              f"[{known.get(x.endpoint, 'ORPHAN — no local name')}]")
    if a.heal:
        acted = heal(assignments)
        for line in acted:
            print("HEAL", line)
        print("HEAL nothing to do" if not acted else f"HEAL {len(acted)} action(s)")
        return 0
    if a.list:
        return 0
    if not (a.endpoint and a.name):
        sys.exit("--endpoint and --name are required (or use --list)")

    match = [x for x in assignments if x.endpoint == a.endpoint]
    if not match:
        sys.exit(f"endpoint {a.endpoint} is not in the live list — that VM is gone (nothing to adopt)")
    x = match[0]
    if a.endpoint in known:
        sys.exit(f"endpoint already bound to name {known[a.endpoint]!r} — nothing to do")
    if state.store.get(a.name):
        sys.exit(f"name {a.name!r} already exists locally — pick another name")

    s = SessionState(name=a.name, token=x.runtime_proxy_info.token, url=x.runtime_proxy_info.url,
                     endpoint=x.endpoint, variant=str(getattr(x.variant, "name", x.variant)),
                     accelerator=str(getattr(x.accelerator, "name", x.accelerator)))
    if a.dry_run:
        print("DRY RUN — would store:", s.model_dump_json(indent=2)[:300], "...")
        print("DRY RUN — would spawn the keep-alive daemon for", x.endpoint)
        return 0
    state.store.add(s)

    # THE PART THAT MATTERS: prune_session() kills the session's keep-alive daemon, and
    # that daemon is the only thing refreshing Colab's idle timer for the assignment.
    # Without it Colab reclaims the VM ~15-25 min later EVEN WHILE IT IS COMPUTING —
    # measured twice on 2026-08-22 (A died 14 min after its prune; B died ~25 min after a
    # re-adoption that restored the name but not the daemon, losing a 40%-done inference).
    # So re-adoption must restart the heartbeat, not just the name.
    from colab_cli.commands.session import spawn_keep_alive
    pid = spawn_keep_alive(x.endpoint, a.name, auth_provider=state.auth_provider)
    s.keep_alive_pid = pid
    state.store.add(s)
    print(f"READOPTED {a.name} -> {x.endpoint}   keep-alive daemon pid {pid}")
    print(f"  verify: colab exec -s {a.name} ... ; end billing with: colab stop -s {a.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
