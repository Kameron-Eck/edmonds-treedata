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
import sys

from colab_cli.common import state
from colab_cli.state import SessionState


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", help="endpoint id, from `colab sessions` or --list")
    ap.add_argument("--name", help="local name to bind it to (avoid a name already in use)")
    ap.add_argument("--list", action="store_true", help="only list live server-side assignments")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written, write nothing")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    assignments = state.client.list_assignments()
    known = {s.endpoint: n for n, s in (state.store.list() or {}).items()}
    print("live assignments:")
    for x in assignments:
        print(f"   {x.endpoint}  {getattr(x.accelerator, 'name', x.accelerator)}  "
              f"{getattr(x.variant, 'name', x.variant)}  "
              f"[{known.get(x.endpoint, 'ORPHAN — no local name')}]")
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
        return 0
    state.store.add(s)
    print(f"READOPTED {a.name} -> {x.endpoint}   (verify: colab exec -s {a.name} ...; "
          f"end billing with: colab stop -s {a.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
