#!/usr/bin/env python3
"""Real-time scheduling, measured (rtsched.py): live played by a script into a
silent PipeWire sink, with and without the audio thread real-time and pinned,
with and without the machine busy.

    python3 examples/rt_bench.py [--secs=45] [--modes=off,rt,pin] [--load=0,8] [--gpu]

Each run is a fresh live process (scheduling is per process, and so is the GPU)
playing the same piano: pedalled chords, a fast run, the pedal swept through
its band, for --secs. Its audio goes to a null sink made for the bench
(nothing reaches the speakers) and is unloaded after. Modes:

    off   TUNING_RT=0: an ordinary thread, as before rtsched
    rt    real-time through rtkit, not pinned
    pin   real-time and pinned (the default live now runs)

--load=N runs N processes of numpy busy work beside it (the "CPU activity
interfering"); 0 is the quiet machine. Per run: PortAudio's underruns, late
arrivals (over 2 and 4 periods), the longest gap, the callbacks' durations,
and what rtsched did. Not while live is playing: it is a heavy job.

--diag=DIR, to find what makes a callback slow and what the silence after one
waits on (the 2026-10-29 runs: one callback of 0.25-0.77 s, then PortAudio
silent ~14 s -- Ben's live hang). Per run, in DIR:
  NODE.slow.txt  every thread's stack once a second into a gap (not 100 ms
                 into a slow callback, as it first did: faulthandler walking a
                 thread that is running crashed a run, 2026-10-29)
  NODE.err       the child's stderr (PortAudio, ALSA)
and in the result: the collector's passes over 2 ms, and each gap over 50 ms
with where the callback thread slept meanwhile (/proc wchan, sampled).
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SINK = "tuning_rtbench"


def burn(stop_at):
    import numpy as np
    a = np.random.rand(300, 300)
    while time.time() < stop_at:
        a = a @ a
        a /= np.abs(a).max() + 1.0


class Diag:
    """The slow-callback and gap instruments of --diag (see the docstring)."""

    def __init__(self, path):
        import gc
        import faulthandler
        import threading
        self.fh = faulthandler
        self.f = open(path, "w", buffering=1)
        self.tid = None
        self.t_last = None           # the last callback's start
        self.busy = False
        self.gcs = []                # (t, generation, ms) over 2 ms
        self.gaps = []
        self._gc_t = None
        self.t0 = time.perf_counter()

        def gcb(phase, info):
            if phase == "start":
                self._gc_t = time.perf_counter()
            elif self._gc_t is not None:
                ms = 1000 * (time.perf_counter() - self._gc_t)
                if ms > 2.0:
                    self.gcs.append((round(self._gc_t - self.t0, 3), info.get("generation"), round(ms, 2)))
        gc.callbacks.append(gcb)
        threading.Thread(target=self._sample, daemon=True).start()

    def wrap(self, cb):
        import threading

        def callback(*a):
            if self.tid is None:
                self.tid = threading.get_native_id()
            self.t_last = time.perf_counter()
            self.busy = True
            self.n = getattr(self, "n", 0) + 1
            try:
                if self.n == int(os.environ.get("RTBENCH_INJECT", 0)):
                    time.sleep(0.3)          # (a test of the instrument itself)
                return cb(*a)
            finally:
                self.busy = False
        return callback

    def _wchan(self, t):
        try:
            with open("/proc/self/task/%d/wchan" % t) as f:
                w = f.read().strip() or "-"
            with open("/proc/self/task/%d/stat" % t) as f:
                st = f.read().rsplit(")", 1)[1].split()[0]
            return "%s:%s" % (st, w)
        except OSError:
            return "gone"

    def _sample(self):
        import collections
        gap = None
        while True:
            time.sleep(0.01)
            tl, tid = self.t_last, self.tid
            if tl is None or tid is None:
                continue
            now = time.perf_counter()
            if not self.busy and now - tl > 0.05:
                if gap is None or gap["at"] != tl:
                    gap = dict(at=tl, w=collections.Counter(), dumped=0)
                gap["w"][self._wchan(tid)] += 1
                if now - tl > 1.0 + gap["dumped"] and gap["dumped"] < 3:
                    gap["dumped"] += 1
                    self.f.write("==== gap %.1f s after the callback at %.3f s; every task's wchan: %s\n"
                                 % (now - tl, tl - self.t0,
                                    ", ".join("%s=%s" % (t, self._wchan(int(t)))
                                              for t in sorted(os.listdir("/proc/self/task")))))
                    self.fh.dump_traceback(file=self.f, all_threads=True)
            elif gap is not None and self.t_last != gap["at"]:
                self.gaps.append(dict(at_s=round(gap["at"] - self.t0, 3),
                                      len_ms=round(1000 * (self.t_last - gap["at"]), 1),
                                      wchan=dict(gap["w"].most_common(6))))
                gap = None


def child(secs, gpu, program, diag=None):
    """One run: a live, its stream, the script; the numbers as JSON on stdout."""
    sys.path.insert(0, REPO)
    import threading
    import mido
    import live as LV
    sys.setswitchinterval(0.0005)
    lv = LV.Live(program=program, rate=48000, frames=128, gpu=gpu, verbose=False)
    lv.enable_room("hall")
    lv.warm()
    LV._gc_freeze()
    dg = None
    if diag:
        dg = Diag(os.path.join(diag, os.environ.get("RTBENCH_NODE", "run") + ".slow.txt"))
        lv.callback = dg.wrap(lv.callback)       # (open_stream hands PortAudio lv.callback)
        import rtsched
        lv.cb_ring = rtsched.CbRing(lv.frames / float(lv.rate), n=1 << 15)   # the whole run
    pa, stream = LV.open_stream(lv, lv.rate, lv.frames)
    stream.start_stream()
    stop = threading.Event()

    def play():
        import random
        rnd = random.Random(7)
        m = lambda *a, **k: lv.on_midi(mido.Message(*a, **k))
        t_end = time.monotonic() + secs
        while time.monotonic() < t_end and not stop.is_set():
            m("control_change", control=64, value=127)
            root = rnd.choice((36, 41, 43, 45, 48))
            ch = [root, root + 12, root + 19, root + 24, root + 28, root + 31]
            for n in ch:
                m("note_on", note=n, velocity=rnd.randint(60, 100))
            time.sleep(0.6)
            for n in ch:
                m("note_off", note=n, velocity=0)
            for k in range(16):                       # a fast run over the ring
                n = 60 + (k * 5) % 24
                m("note_on", note=n, velocity=rnd.randint(50, 90))
                time.sleep(0.04)
                m("note_off", note=n, velocity=0)
            for v in list(range(127, 40, -3)) + list(range(40, 128, 6)):   # the band
                m("control_change", control=64, value=v)
                time.sleep(0.01)
            m("control_change", control=64, value=0)
            time.sleep(0.3)

    th = threading.Thread(target=play, daemon=True)
    th.start()
    time.sleep(2.0)
    sink = our_sink()
    th.join(secs + 5)
    stop.set()
    time.sleep(0.5)
    rt_report = lv.rt.report() if lv.rt else ""
    lv.stop_kicker()
    stream.stop_stream()
    out = dict(sink=sink, kicks=lv.kicks, underruns=lv.underruns, render_max_ms=round(lv.render_max, 3),
               errors=lv.errors, shed=lv.partials_shed, gpu=bool(lv.stats().get("on_gpu")))
    out.update(lv.cb_ring.summary())
    out["rt"] = lv.rt.status() if lv.rt else ""
    out["rt_report"] = rt_report
    if dg is not None:
        import numpy as np
        t, d, st = lv.cb_ring.window()
        np.savez(os.path.join(diag, os.environ.get("RTBENCH_NODE", "run") + ".ring.npz"),
                 t=t - dg.t0, d=d, s=st)
        out["gc_slow"] = dg.gcs
        out["gaps"] = dg.gaps
    print("RESULT " + json.dumps(out), flush=True)
    stream.close()
    pa.terminate()
    lv.shutdown()


def our_sink():
    """The name of the sink this process's stream plays into."""
    si = subprocess.run(["pactl", "list", "sink-inputs"], capture_output=True, text=True).stdout
    sinks = {ln.split()[0]: ln.split()[1] for ln in
             subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True).stdout.splitlines()
             if ln.strip()}
    for blk in si.split("Sink Input #")[1:]:
        if 'node.name = "%s"' % os.environ.get("RTBENCH_NODE", "-") in blk:
            for ln in blk.splitlines():
                if ln.strip().startswith("Sink:"):
                    return sinks.get(ln.split(":")[1].strip(), "?")
    return None


def pw_quantum():
    try:
        r = subprocess.run(["pw-metadata", "-n", "settings", "0", "clock.force-quantum"],
                           capture_output=True, text=True, timeout=5)
        for ln in r.stdout.splitlines():
            if "value:" in ln:
                return ln.split("value:")[1].split()[0].strip("'")
    except Exception:
        pass
    return "?"


def main(argv):
    opt = dict(a.split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
    gpu = "--gpu" in argv
    secs = float(opt.get("--secs", 45))
    program = int(opt.get("--program", 0))
    if "--child" in argv:
        child(secs, gpu, program, opt.get("--diag"))
        return 0
    modes = opt.get("--modes", "off,rt,pin").split(",")
    diag = opt.get("--diag")
    if diag:
        diag = os.path.abspath(diag)
        os.makedirs(diag, exist_ok=True)
    reps = int(opt.get("--reps", 1))
    loads = [int(x) for x in opt.get("--load", "0,8").split(",")]
    r = subprocess.run(["pgrep", "-af", "python3"], capture_output=True, text=True)
    if any(("livetui" in ln or "live.py" in ln) and "rt_bench" not in ln for ln in r.stdout.splitlines()):
        print("live is running: not now")
        return 1
    mod = subprocess.run(["pactl", "load-module", "module-null-sink", "sink_name=" + SINK,
                          "sink_properties=device.description=tuning-rtbench"],
                         capture_output=True, text=True)
    if mod.returncode != 0:
        print("could not make the null sink: %s" % mod.stderr.strip())
        return 1
    mod_id = mod.stdout.strip()
    print("quantum forced to %s; null sink %s (module %s)" % (pw_quantum(), SINK, mod_id), flush=True)
    rows = []
    try:
        import multiprocessing as mp
        for load in loads:
          for rep_i in range(reps):
            for mode in modes:
                # THE NULL SINK, by the ALSA plugin's own stream properties
                # (PIPEWIRE_NODE does not reach it); named, so the child can
                # find its stream and say where it played
                node = "%s_%s_%d_%d" % (SINK, mode, load, rep_i)
                env = dict(os.environ, TUNING_GPU="1" if gpu else "0", RTBENCH_NODE=node,
                           PIPEWIRE_ALSA='{ target.object = "%s" node.name = "%s" }' % (SINK, node))
                env["TUNING_RT"] = "0" if mode == "off" else "1"
                env["TUNING_RT_PIN"] = "1" if mode == "pin" else "0"
                burners = []
                if load:
                    stop_at = time.time() + secs + 120
                    burners = [mp.Process(target=burn, args=(stop_at,), daemon=True) for _ in range(load)]
                    for b in burners:
                        b.start()
                t0 = time.time()
                p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--child", "--secs=%g" % secs,
                                      "--program=%d" % program] + (["--gpu"] if gpu else [])
                                     + (["--diag=" + diag] if diag else []),
                                     cwd=REPO, env=env, stdout=subprocess.PIPE, text=True,
                                     stderr=open(os.path.join(diag, node + ".err"), "w") if diag
                                     else subprocess.DEVNULL)
                out, _ = p.communicate()
                for b in burners:
                    b.terminate()
                res = next((json.loads(ln[7:]) for ln in out.splitlines() if ln.startswith("RESULT ")), None)
                if res is None:
                    print("  %-4s load %d: no result (exit %s)" % (mode, load, p.returncode), flush=True)
                    continue
                routed = res.get("sink") == SINK
                res.update(mode=mode, load=load, secs=round(time.time() - t0), null_sink=routed)
                rows.append(res)
                print("  %-4s load %d: underruns %4d  late>2p %4d  >4p %4d  gap max %7.2f ms  "
                      "took p50 %.2f p99 %.2f max %.2f ms  over %d  kicks %d  %s%s"
                      % (mode, load, res["underruns"], res["late2"], res["late4"], res["gap_max_ms"],
                         res.get("dur_p50_ms", 0), res.get("dur_p99_ms", 0), res["dur_max_ms"], res["over"],
                         res.get("kicks", 0), res["rt"], "" if routed else "  (played into %s, not the null sink)" % res.get("sink")), flush=True)
                for g in res.get("gaps", []):
                    if g["len_ms"] > 200:
                        print("        gap %.1f ms at %.1f s; the callback thread meanwhile: %s"
                              % (g["len_ms"], g["at_s"], g["wchan"]), flush=True)
                if res.get("gc_slow"):
                    print("        collector over 2 ms: %d, longest %.1f ms"
                          % (len(res["gc_slow"]), max(x[2] for x in res["gc_slow"])), flush=True)
    finally:
        subprocess.run(["pactl", "unload-module", mod_id], capture_output=True)
    path = os.path.join(REPO, "rt_bench.json")
    with open(path, "w") as f:
        json.dump(rows, f, indent=1)
    for r in rows:
        if r["mode"] == "pin" and r["rt_report"]:
            print("\n" + r["rt_report"])
            break
    print("\n  %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
