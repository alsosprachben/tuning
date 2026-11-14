#!/usr/bin/env python3
"""A command under a memory cap, its peak reported: memcap.py [--cap=MB] [--every=S] [--trace=FILE] -- COMMAND...

systemd-run --scope -p MemoryMax caps a job on Linux; macOS (the port ahead
of iOS, an 8 GB machine) has no cgroups and ignores RLIMIT_AS. This runs
COMMAND in a process group of its own and every EVERY seconds (default 0.25)
sums the memory of the group, stopping the whole group --
SIGTERM, then SIGKILL -- the moment it passes CAP megabytes (default 3500,
the Linux checks' cap). A job stopped for memory is a design to rethink,
never a cap to raise.

THE MEASURE: on Linux each process's resident set (ps); on macOS its PHYSICAL
FOOTPRINT (proc_pid_rusage's ri_phys_footprint: Activity Monitor's Memory,
what iOS's jetsam limits an app by) -- macOS compresses idle pages, so its
resident set reads a fifth of the footprint (a file export: 648 MB resident,
3.06 GB footprint).

--trace=FILE: each sample's time (s from the start) and MB written there, a
line each -- where a job's memory climbs.

Prints, on stderr, the group's peak and whether it was stopped; exits with
COMMAND's status, or 137 if stopped for memory.
"""
import os
import signal
import subprocess
import sys
import time


def _footprint(pid):
    """macOS: a process's physical footprint, bytes (0 where it cannot be read)."""
    import ctypes
    if not hasattr(_footprint, "lib"):
        _footprint.lib = ctypes.CDLL("/usr/lib/libproc.dylib")
    buf = (ctypes.c_uint64 * 64)()                  # (rusage_info_v4: ri_phys_footprint is field 9)
    if _footprint.lib.proc_pid_rusage(int(pid), 4, ctypes.byref(buf)) != 0:
        return 0
    return int(buf[9])


def group_rss_mb(pgid):
    """The memory of every process in group pgid, MB: Linux's resident sets
    (ps's RSS, KiB), macOS's physical footprints."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,pgid=,rss="], capture_output=True, text=True).stdout
    except OSError:
        return 0.0
    tot = 0.0
    for ln in out.splitlines():
        p = ln.split()
        if len(p) == 3 and p[1] == str(pgid):
            tot += _footprint(p[0]) / 1048576.0 if sys.platform == "darwin" else int(p[2]) / 1024.0
    return tot


def main(argv):
    if "--" not in argv:
        print(__doc__)
        return 2
    k = argv.index("--")
    opt = dict(a[2:].split("=", 1) for a in argv[:k] if a.startswith("--") and "=" in a)
    cap = float(opt.get("cap", 3500))
    every = float(opt.get("every", 0.25))
    cmd = argv[k + 1:]
    tr = open(opt["trace"], "w") if opt.get("trace") else None
    t0 = time.monotonic()
    p = subprocess.Popen(cmd, start_new_session=True)
    peak, stopped = 0.0, False
    while p.poll() is None:
        m = group_rss_mb(p.pid)
        peak = max(peak, m)
        if tr:
            tr.write("%.2f %.0f\n" % (time.monotonic() - t0, m))
            tr.flush()
        if m > cap:
            stopped = True
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
            break
        time.sleep(every)
    sys.stderr.write("memcap: peak %.0f MB (cap %.0f)%s\n" % (peak, cap, ", STOPPED for memory" if stopped else ""))
    return 137 if stopped else p.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
