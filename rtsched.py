"""REAL-TIME SCHEDULING for live's audio thread, and a probe of its callbacks.

The audio callback ran as an ordinary thread (SCHED_OTHER, nice 0), queued
behind gnome-shell, the panel, our own workers and the GPU driver; only
PipeWire's threads were real-time (SCHED_RR 20). Ben's stalls of 2026-10-28
(PortAudio not calling for seconds, every Python thread idle) are what this is
for. Three things:

  PRIORITY   rtkit (the desktop's real-time broker, no sudo) makes the callback
             thread SCHED_RR at PRIO, under PipeWire's 20 so the graph's own
             threads still come first. rtkit insists on RLIMIT_RTTIME: a
             real-time thread that runs that long without sleeping is signalled
             (SIGXCPU at the soft limit) and then killed (SIGKILL at the hard,
             200 ms). THE GUARD: a thread of ours that wakes every GUARD_S and,
             finding a callback running past STUCK_S, demotes every thread we
             promoted -- a runaway callback costs real-time, never the session.
             Not a SIGXCPU handler alone: the kernel signals the spinning
             thread itself, and Python runs handlers only on the main thread,
             which sleeps on (measured: handled when the spin ended). The
             guard's waking also keeps the limit from coming: each time it
             wants the interpreter's lock, a real-time thread holding it hands
             it over and sleeps, which restarts its count (measured: a promoted
             thread spun 1 s in Python unharmed beside a 100 ms poller). rtkit
             marks what it grants reset-on-fork: threads the
             callback starts are NOT real-time. The GPU's block setup is an
             OpenMP team the callback thread starts at its first render
             on the GPU path (gpurender.BlockTables, 4 threads; the GPU takes
             over only above gpu_min slots, so that can be minutes in): each
             second the helper looks for threads pinned like the callback that
             are not Python's -- the team, which inherited the pin -- and
             promotes them too, so the callback never waits at its
             barrier for a thread the desktop preempted.
  PINNING    (opt-in, TUNING_RT_PIN=1) the callback thread on CPUS (default: the last two physical cores
             with their hyperthread siblings -- room for the OpenMP team, which
             inherits the pin), every other thread of ours, and the register's
             worker process, on the rest. Not isolcpus (that takes a reboot):
             other programs can still land on CPUS, but real-time outranks
             them there.
  THE PROBE  CbRing: each callback's arrival, duration and PortAudio status in
             a ring (~22 s at 128 frames), with running counts of late
             arrivals. Written with the watchdog's stall dump, it tells a
             callback that grew slow until it missed (our load) from one that
             was on time and then simply not called (the device, PipeWire).

TUNING_RT=0 turns priority and pinning off (the probe stays); TUNING_RT_PIN=1
pins as well -- not the default: on a quiet machine the callback and its team
squeezed onto two cores underran MORE (examples/rt_bench.py, 2026-10-29: 398
underruns in 45 s pinned, 210 real-time alone, 158 neither), and only beside
a machine full of other load did it win (1390 against 1662 and 3248); TUNING_RT_CPUS="2,3,6,7" names the audio CPUs;
TUNING_RT_PRIO the priority (rtkit allows up to 20).
"""
import os
import queue
import resource
import signal
import subprocess
import sys
import threading
import time

import numpy as np

PRIO = 18
# RLIMIT_RTTIME, microseconds: SIGXCPU at the soft limit, SIGKILL at the hard.
# rtkit refuses a hard limit over its RTTimeUSecMax (200 ms here). A callback is
# 2.7 ms; 50 ms without once sleeping is a runaway.
RTTIME_SOFT_US = 100000
RTTIME_HARD_US = 200000
GUARD_S = 0.025               # the guard's wake
STUCK_S = 0.06                # a callback running this long: demote
TEAM_SCAN_S = 1.0             # the helper's look for the callback's OpenMP team


def _cores():
    """{physical core: [cpus]} from sysfs, in core order."""
    out = {}
    base = "/sys/devices/system/cpu"
    for c in sorted(os.sched_getaffinity(0)):
        try:
            with open("%s/cpu%d/topology/core_id" % (base, c)) as f:
                core = int(f.read())
            with open("%s/cpu%d/topology/physical_package_id" % (base, c)) as f:
                pkg = int(f.read())
        except OSError:
            core, pkg = c, 0
        out.setdefault((pkg, core), []).append(c)
    return [out[k] for k in sorted(out)]


def default_cpus():
    """The last two physical cores, siblings included -- or the last one on a
    machine of fewer than four; None (no pinning) on one of fewer than two."""
    cores = _cores()
    if len(cores) < 2:
        return None
    take = cores[-2:] if len(cores) >= 4 else cores[-1:]
    return sorted(c for cs in take for c in cs)


def _tasks(pid="self"):
    try:
        return {int(t) for t in os.listdir("/proc/%s/task" % pid)}
    except OSError:
        return set()


def _children(pid):
    """Child processes of every thread of pid."""
    kids = set()
    for t in _tasks(pid):
        try:
            with open("/proc/%s/task/%d/children" % (pid, t)) as f:
                kids.update(int(x) for x in f.read().split())
        except OSError:
            pass
    return kids


def _comm(tid):
    try:
        with open("/proc/self/task/%d/comm" % tid) as f:
            return f.read().strip()
    except OSError:
        return "?"


def rtkit_promote(tid, prio, pid=None):
    """Ask rtkit to make thread `tid` of `pid` SCHED_RR at `prio`. Returns None
    or the reason it would not. Through busctl: the call names the pid, so it
    works from any process (the plain MakeThreadRealtime looks the thread up
    under the CALLER's pid, and busctl is another process)."""
    try:
        r = subprocess.run(["busctl", "--system", "call", "org.freedesktop.RealtimeKit1",
                            "/org/freedesktop/RealtimeKit1", "org.freedesktop.RealtimeKit1",
                            "MakeThreadRealtimeWithPID", "ttu", str(pid or os.getpid()),
                            str(tid), str(int(prio))],
                           capture_output=True, text=True, timeout=2.0)
    except Exception as e:
        return "%s: %s" % (type(e).__name__, e)
    return None if r.returncode == 0 else (r.stderr.strip() or "busctl %d" % r.returncode)


class RtSched:
    """One per stream. prepare() on the main thread before the stream starts;
    tick() at the top of every callback (cheap: a thread-id compare, and a
    counter); status() for the panel."""

    def __init__(self, prio=None, cpus=None, pin=None, enabled=None):
        env = os.environ
        self.enabled = (env.get("TUNING_RT", "1") != "0") if enabled is None else enabled
        self.prio = int(env.get("TUNING_RT_PRIO", PRIO)) if prio is None else int(prio)
        pin = (env.get("TUNING_RT_PIN", "0") == "1") if pin is None else pin
        if cpus is None and env.get("TUNING_RT_CPUS"):
            cpus = [int(x) for x in env["TUNING_RT_CPUS"].split(",") if x.strip()]
        allowed = os.sched_getaffinity(0)
        if pin:
            cpus = sorted(set(cpus if cpus is not None else (default_cpus() or [])) & allowed)
        self.cpus = set(cpus) if pin and cpus and len(cpus) < len(allowed) else None
        self.rest = (allowed - self.cpus) if self.cpus else None
        self.tid = None              # the callback thread
        self.blocks = 0              # since it started
        self.promoted = {}           # tid -> comm, real-time now
        self.refused = None          # rtkit's reason, if it said no
        self.dropped = 0             # SIGXCPU demotions
        self.team = None             # the OpenMP team found, tids
        self.note = []               # what happened, for the dump
        self._q = queue.Queue()
        self._ready = False
        self.busy_since = None       # the running callback's start (perf_counter)

    # ---- main thread, before the stream ------------------------------------
    def prepare(self, extra_pids=()):
        """The rtkit limit and the SIGXCPU guard; every thread of ours (and of
        extra_pids, the register's worker) off the audio CPUs. Off on any
        failure: real-time without the guard would be killed by its limit."""
        if not self.enabled:
            self.note.append("off (TUNING_RT=0)")
            return
        if threading.current_thread() is not threading.main_thread():
            self.enabled = False
            self.note.append("off (prepare not on the main thread: no SIGXCPU guard)")
            return
        try:
            resource.setrlimit(resource.RLIMIT_RTTIME, (RTTIME_SOFT_US, RTTIME_HARD_US))
            signal.signal(signal.SIGXCPU, self._on_xcpu)
        except Exception as e:
            self.enabled = False
            self.note.append("off (%s)" % e)
            return
        if self.rest:
            self.place_rest(extra_pids)
        threading.Thread(target=self._helper, daemon=True, name="rtsched").start()
        threading.Thread(target=self._guard, daemon=True, name="rtguard").start()
        self._ready = True

    def place_rest(self, extra_pids=()):
        """Every thread of this process but the callback's team, and of
        extra_pids and our children, on the non-audio CPUs."""
        if not self.rest:
            return
        mine = set(self.promoted) | ({self.tid} if self.tid else set()) | set(self.team or ())
        n = 0
        for pid in ["self"] + [str(p) for p in set(extra_pids) | _children(os.getpid())]:
            for t in _tasks(pid):
                if t in mine:
                    continue
                try:
                    os.sched_setaffinity(t, self.rest)
                    n += 1
                except OSError:
                    pass
        return n

    def _guard(self):
        while True:
            time.sleep(GUARD_S)
            b = self.busy_since
            if b is not None and self.promoted and time.perf_counter() - b > STUCK_S:
                self.demote("a callback ran %.0f ms" % (1000 * (time.perf_counter() - b)))

    def _on_xcpu(self, signum, frame):
        self.demote("SIGXCPU")

    def demote(self, why):
        # A REAL-TIME THREAD THAT WILL NOT SLEEP: every one we promoted back
        # to the desktop's scheduler before the hard limit's SIGKILL
        for t in list(self.promoted):
            # (keeping rtkit's reset-on-fork: clearing it takes privilege,
            # and a request that tries is refused whole)
            try:
                os.sched_setscheduler(t, os.SCHED_OTHER | getattr(os, "SCHED_RESET_ON_FORK", 0),
                                      os.sched_param(0))
            except OSError as e:
                self.note.append("could not demote %d: %s" % (t, e))
        self.promoted.clear()
        self.dropped += 1
        self.note.append("%s %s: real-time dropped" % (time.strftime("%H:%M:%S"), why))

    # ---- audio thread --------------------------------------------------------
    def tick(self, t_in):
        """The top of a callback; done() at its end."""
        self.busy_since = t_in
        if not self._ready:
            return
        tid = threading.get_native_id()
        if tid != self.tid:
            # A NEW CALLBACK THREAD (the stream opened, or reopened): pinned
            # here and now, before its first render starts the OpenMP team,
            # so the team inherits the pin; promoted by the helper
            self.tid, self.blocks, self.team = tid, 0, []
            if self.cpus:
                try:
                    os.sched_setaffinity(0, self.cpus)
                except OSError as e:
                    self.note.append("pin failed: %s" % e)
            self._q.put(("promote", tid))
        self.blocks += 1

    def done(self):
        self.busy_since = None

    # ---- the helper thread ---------------------------------------------------
    def _helper(self):
        while True:
            try:
                what, tid = self._q.get(timeout=TEAM_SCAN_S)
            except queue.Empty:
                what, tid = "team", self.tid
            if what == "promote":
                self._promote(tid, "callback")
            elif what == "team" and tid is not None and self.cpus and tid in self.promoted:
                # THE THREADS THE CALLBACK STARTED: pinned as it is (what
                # another thread starts is not), and not Python's own (a file
                # writer it started has no business being real-time)
                py = {th.native_id for th in threading.enumerate()}
                for t in sorted(_tasks() - set(self.promoted) - {tid}):
                    if t in self.team or self._affinity(t) != self.cpus:
                        continue
                    if t in py:
                        self._unpin(t)
                    else:
                        self.team.append(t)
                        self._promote(t, "team")
                # ...AND WHAT IT STARTED THAT IS NOT ITS TEAM, off its CPUs: a
                # Python thread, a process (the register's worker is started
                # by a command the callback runs, and inherits the pin)
                for kid in _children(os.getpid()):
                    for t in _tasks(kid):
                        if self._affinity(t) == self.cpus:
                            self._unpin(t)

    def _unpin(self, t):
        try:
            os.sched_setaffinity(t, self.rest)
        except OSError:
            pass

    @staticmethod
    def _affinity(t):
        try:
            return os.sched_getaffinity(t)
        except OSError:
            return None

    def _promote(self, tid, role):
        why = rtkit_promote(tid, self.prio)
        if why is None:
            self.promoted[tid] = "%s %s" % (role, _comm(tid))
        else:
            self.refused = why
            self.note.append("rtkit refused %s %d: %s" % (role, tid, why))

    # ---- telemetry -----------------------------------------------------------
    def status(self):
        """Short, for the panel: 'RT18 2,3,6,7', 'RT18', 'rt off', 'rt refused'."""
        if not self.enabled:
            return "rt off"
        if self.tid is not None and self.tid not in self.promoted:
            return "rt dropped" if self.dropped else ("rt refused" if self.refused else "rt ...")
        if self.tid is None:
            return "rt ..."
        return "RT%d%s" % (self.prio, (" " + ",".join(map(str, sorted(self.cpus)))) if self.cpus else "")

    def report(self):
        """Long, for the dump."""
        out = ["realtime: %s; callback thread %s; team %s; promoted %d; SIGXCPU %d"
               % (self.status(), self.tid, self.team, len(self.promoted), self.dropped)]
        if self.cpus:
            out.append("  audio CPUs %s, the rest on %s"
                       % (",".join(map(str, sorted(self.cpus))), ",".join(map(str, sorted(self.rest)))))
        for t, (pol, pr) in sorted(self.policies().items()):
            out.append("  thread %d %s: %s %d, CPUs %s"
                       % (t, self.promoted.get(t, _comm(t)), {os.SCHED_OTHER: "other", os.SCHED_RR: "rr",
                                                            os.SCHED_FIFO: "fifo"}.get(pol & 0xff, pol),
                          pr, ",".join(map(str, sorted(self._affinity(t) or ())))))
        out.extend("  " + n for n in self.note[-8:])
        return "\n".join(out)

    def policies(self):
        """{tid: (policy, priority)} of the callback and its team."""
        out = {}
        for t in [self.tid] + list(self.team or ()):
            if t is None:
                continue
            try:
                out[t] = (os.sched_getscheduler(t), os.sched_getparam(t).sched_priority)
            except OSError:
                pass
        return out


class CbRing:
    """The callbacks' timing: arrival (perf_counter), duration, status, in a
    ring of N; with running totals over the whole session. note() is the audio
    thread's only cost: a few array stores."""

    def __init__(self, period_s, n=8192):
        self.period = float(period_s)
        self.n = int(n)
        self.t = np.zeros(self.n)
        self.d = np.zeros(self.n, np.float32)
        self.s = np.zeros(self.n, np.uint16)
        self.i = 0
        self.last = None
        self.late2 = 0               # arrivals over 2 periods after the last
        self.late4 = 0               # ...over 4: an underrun for sure
        self.gap_max = 0.0
        self.over = 0                # callbacks longer than a period
        self.dur_max = 0.0

    def note(self, t_in, t_out, status):
        k = self.i % self.n
        self.t[k] = t_in
        d = t_out - t_in
        self.d[k] = d
        self.s[k] = status
        self.i += 1
        if self.last is not None:
            g = t_in - self.last
            if g > 2.0 * self.period:
                self.late2 += 1
                if g > 4.0 * self.period:
                    self.late4 += 1
                if g > self.gap_max:
                    self.gap_max = g
        self.last = t_in
        if d > self.period:
            self.over += 1
        if d > self.dur_max:
            self.dur_max = d

    def window(self):
        """(t, d, s) of what the ring holds, oldest first."""
        m = min(self.i, self.n)
        k = np.arange(self.i - m, self.i) % self.n
        return self.t[k], self.d[k], self.s[k]

    def summary(self):
        """Numbers: the session's totals, and the ring's percentiles."""
        t, d, s = self.window()
        g = np.diff(t) if len(t) > 1 else np.zeros(0)
        ms = lambda x: round(float(x) * 1000.0, 3)
        out = dict(callbacks=self.i, period_ms=ms(self.period), late2=self.late2, late4=self.late4,
                   gap_max_ms=ms(self.gap_max), over=self.over, dur_max_ms=ms(self.dur_max))
        if len(g):
            out.update(gap_p50_ms=ms(np.percentile(g, 50)), gap_p99_ms=ms(np.percentile(g, 99)),
                       gap_p999_ms=ms(np.percentile(g, 99.9)))
        if len(d):
            out.update(dur_p50_ms=ms(np.percentile(d, 50)), dur_p99_ms=ms(np.percentile(d, 99)),
                       status_nonzero=int((s != 0).sum()))
        return out

    def report(self, last=64):
        """For the stall dump: the summary, then the last callbacks one a line
        -- how long since the one before, how long it took, its status."""
        sm = self.summary()
        out = ["callbacks: " + ", ".join("%s %s" % kv for kv in sm.items())]
        t, d, s = self.window()
        t, d, s = t[-last - 1:], d[-last - 1:], s[-last - 1:]
        now = time.perf_counter()
        for j in range(1, len(t)):
            out.append("  %9.3f s ago  gap %7.2f ms  took %6.2f ms%s"
                       % (now - t[j], 1000 * (t[j] - t[j - 1]), 1000 * d[j],
                          ("  status %d" % s[j]) if s[j] else ""))
        return "\n".join(out)


def selftest(verbose=True):
    fails = []

    def check(name, ok, detail=""):
        if verbose:
            print("   %-62s %s%s" % (name, "ok" if ok else "FAIL", ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    r = CbRing(0.001, n=16)
    t = 0.0
    for k in range(40):
        t += 0.005 if k == 30 else 0.001
        r.note(t, t + (0.002 if k == 35 else 0.0005), 1 if k == 20 else 0)
    sm = r.summary()
    check("the probe counts a late arrival and a long callback",
          sm["late2"] == 1 and sm["late4"] == 1 and sm["over"] == 1 and abs(sm["gap_max_ms"] - 5.0) < 1e-6,
          str({k: sm[k] for k in ("late2", "late4", "over", "gap_max_ms")}))
    check("the ring keeps the last N, oldest first",
          len(r.window()[0]) == 16 and np.all(np.diff(r.window()[0]) > 0))
    cs = default_cpus()
    check("the audio CPUs are whole cores", cs is None or all(
        set(c) <= set(cs) or not (set(c) & set(cs)) for c in _cores()), str(cs))
    # THE REAL THING, in a thread of our own: pinned, promoted, its child
    # pinned and not real-time (reset-on-fork), and demoted by the guard
    rt = RtSched(pin=True)
    if not rt.enabled:
        check("real-time (skipped: TUNING_RT=0)", True)
    else:
        rt.prepare()
        got = {}

        def cb():
            rt.tick(time.perf_counter())
            rt.done()
            deadline = time.monotonic() + 3.0
            while rt.tid not in rt.promoted and rt.refused is None and time.monotonic() < deadline:
                time.sleep(0.01)
            got["pol"] = os.sched_getscheduler(0) & 0xff, os.sched_getparam(0).sched_priority
            got["cpus"] = os.sched_getaffinity(0)
            th = threading.Thread(target=lambda: got.__setitem__(
                "kid", (os.sched_getscheduler(0) & 0xff, os.sched_getaffinity(0))))
            th.start(); th.join()
            rt.done()
            rt._on_xcpu(signal.SIGXCPU, None)
            got["after"] = os.sched_getscheduler(0) & 0xff
        th = threading.Thread(target=cb)
        th.start(); th.join()
        if rt.refused:
            check("rtkit grants real-time", False, rt.refused)
        else:
            check("the callback thread real-time at PRIO", got["pol"] == (os.SCHED_RR, rt.prio), str(got["pol"]))
            check("...pinned to the audio CPUs", rt.cpus is None or got["cpus"] == rt.cpus,
                  str(sorted(got["cpus"])))
            check("...its child pinned too, not real-time",
                  got["kid"][0] == os.SCHED_OTHER and (rt.cpus is None or got["kid"][1] == rt.cpus))
            check("SIGXCPU demotes it", got["after"] == os.SCHED_OTHER and rt.dropped == 1)
            # ...AND BY THE GUARD: promoted again, a callback that spins on
            got2 = {}

            def spin():
                rt._q.put(("promote", threading.get_native_id()))
                deadline = time.monotonic() + 3.0
                while threading.get_native_id() not in rt.promoted and time.monotonic() < deadline:
                    time.sleep(0.01)
                got2["rt"] = os.sched_getscheduler(0) & 0xff
                t0 = time.monotonic()
                rt.tick(time.perf_counter())
                while time.monotonic() - t0 < 0.5 and os.sched_getscheduler(0) & 0xff == os.SCHED_RR:
                    pass
                got2["spun_ms"] = 1000 * (time.monotonic() - t0)
                got2["after"] = os.sched_getscheduler(0) & 0xff
                rt.done()
            th = threading.Thread(target=spin)
            th.start(); th.join()
            check("a runaway real-time thread is demoted, not killed",
                  got2.get("rt") == os.SCHED_RR and got2.get("after") == os.SCHED_OTHER and rt.dropped == 2
                  and got2["spun_ms"] < 1000 * (STUCK_S + 3 * GUARD_S),
                  "(demoted after %.0f ms)" % got2.get("spun_ms", -1))
            check("the main thread is off the audio CPUs",
                  rt.cpus is None or not (os.sched_getaffinity(0) & rt.cpus), str(sorted(os.sched_getaffinity(0))))
        os.sched_setaffinity(0, set(range(os.cpu_count())))
    if verbose:
        print("\n  %s" % ("all passed" if not fails else "FAILED: %s" % ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(selftest())
