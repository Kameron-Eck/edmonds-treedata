r"""vm_hwlogger.py — raw hardware telemetry, one CSV per session, straight to Drive.

Kam, 2026-09-02: "We should be tracking GPU utilization, CPU utilization,
read/write speed, and virtual disk space." This is that tracker: a stdlib
VM-side sampler (5 s cadence, 60 s buffered flush so the mount is written once
a minute, not 12 times) appending

    {DRIVE}/phase4/logs/hw_{session}.csv
    ts_utc, gpu_util_pct, gpu_mem_util_pct, gpu_mem_used_mb, gpu_power_w,
    cpu_pct, disk_read_mb_s, disk_write_mb_s, net_rx_mb_s, net_tx_mb_s,
    disk_used_gb, disk_free_gb

Sources are the kernel's own counters — /proc/stat, /proc/diskstats,
/proc/net/dev, statvfs — plus one nvidia-smi query per sample. No pipeline
code in the measurement path; the numbers are what Linux and NVIDIA say, which
is the point ("hard for me to know what to trust"). Net rx/tx IS the Drive
FUSE traffic (rclone speaks HTTPS), so read/write speed to the lake shows up
there; disk_* is the local NVMe. Launched by the bootstrap next to the beacon;
CPU runtimes just log blank GPU columns. Never crashes the host: every sampler
is try/except-blank, and a failed flush keeps rows for the next flush.
"""
import argparse
import os
import shutil
import subprocess
import time

DRIVE = "/content/drive/MyDrive/treedata"

HEADER = ("ts_utc,gpu_util_pct,gpu_mem_util_pct,gpu_mem_used_mb,gpu_power_w,"
          "cpu_pct,disk_read_mb_s,disk_write_mb_s,net_rx_mb_s,net_tx_mb_s,"
          "disk_used_gb,disk_free_gb\n")


def cpu_ticks():
    with open("/proc/stat") as f:
        p = f.readline().split()[1:]
    vals = [int(x) for x in p[:8]]
    idle = vals[3] + vals[4]                     # idle + iowait
    return sum(vals), idle


def cpu_pct(prev, cur):
    dt_, didle = cur[0] - prev[0], cur[1] - prev[1]
    return round(100.0 * (dt_ - didle) / dt_, 1) if dt_ > 0 else ""


def disk_bytes():
    rd = wr = 0
    with open("/proc/diskstats") as f:
        for ln in f:
            p = ln.split()
            if len(p) < 10 or p[2].startswith(("loop", "ram", "dm-")):
                continue
            if p[2][-1].isdigit() and not p[2].startswith("nvme"):
                continue                          # skip partitions of sdX (whole-disk row counts)
            rd += int(p[5]) * 512
            wr += int(p[9]) * 512
    return rd, wr


def net_bytes():
    rx = tx = 0
    with open("/proc/net/dev") as f:
        for ln in f.readlines()[2:]:
            name, rest = ln.split(":", 1)
            if name.strip() == "lo":
                continue
            p = rest.split()
            rx += int(p[0])
            tx += int(p[8])
    return rx, tx


def rate_mb(prev, cur, secs):
    return round((cur - prev) / secs / 1e6, 2) if secs > 0 and cur >= prev else ""


def gpu_row():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,"
             "memory.used,power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        p = [x.strip() for x in out.split(",")]
        return p[0], p[1], p[2], p[3]
    except Exception:                             # noqa: BLE001
        return "", "", "", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--flush-every", type=int, default=12)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or f"{DRIVE}/phase4/logs/hw_{a.session}.csv"

    rows = []
    if not os.path.exists(out):
        rows.append(HEADER)
    pc, pd, pn, pt = cpu_ticks(), disk_bytes(), net_bytes(), time.time()
    n = 0
    while True:
        time.sleep(a.interval)
        n += 1
        try:
            cc, cd, cn, ct = cpu_ticks(), disk_bytes(), net_bytes(), time.time()
            secs = ct - pt
            g = gpu_row()
            try:
                du = shutil.disk_usage("/content")
                used = round(du.used / 1e9, 1)
                free = round(du.free / 1e9, 1)
            except OSError:
                used = free = ""
            rows.append(",".join(str(x) for x in (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                g[0], g[1], g[2], g[3], cpu_pct(pc, cc),
                rate_mb(pd[0], cd[0], secs), rate_mb(pd[1], cd[1], secs),
                rate_mb(pn[0], cn[0], secs), rate_mb(pn[1], cn[1], secs),
                used, free)) + "\n")
            pc, pd, pn, pt = cc, cd, cn, ct
        except Exception:                         # noqa: BLE001
            pass                                  # a bad sample must never kill the logger
        if len(rows) and n % a.flush_every == 0:
            try:
                with open(out, "a") as f:
                    f.writelines(rows)
                rows = []
            except OSError:
                pass                              # Drive blink: keep rows, retry next flush


if __name__ == "__main__":
    main()
