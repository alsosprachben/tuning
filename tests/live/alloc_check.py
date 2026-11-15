#!/usr/bin/env python3
"""What the audio thread allocates while a chord is held: python3 tests/live/alloc_check.py

An allocation on the audio thread can wait on the allocator's lock, or on
the system for memory -- a late block, a click. A block of a held chord
does the same work as the one before it, so it should allocate nothing:
render_now's columns, reap's lists, the register's tables, the valve's
changes are kept from block to block (slab.cpp), the free slots a ring.

tests/live/allocwatch.c, built here and preloaded into nvlive --test (the
workers on their threads, in real time: --async --reg-async --paced),
counts each block's allocations on the audio thread, blamed on whoever
asked. A chord is held 6 s (under the pedal) on

  piano     program 0 -- the register's strings answering and falling silent
  scanner   program 16 -- the scanner organ
  valve     program 30 -- the valve's chord

each on the CPU and, where there is one, the GPU (every block on it:
--gpu-min=1) -- and from 1.5 s to 5.5 s no block may allocate in the
engine's own code. A runtime's are left out: OpenMP's (libgomp allocates
its team for the kernel's parallel loop, even of one thread), the GPU
driver's (an event each launch). The watcher must see the onset's
allocations, or it was not attached.

Linux only (it interposes glibc's malloc): elsewhere it says so and passes.
Exits 1 if any check fails.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))
CASES = (("piano", 0), ("scanner", 16), ("valve", 30))
PATHS = (("CPU", ["--cpu", "--no-pipeline"]), ("GPU", ["--gpu", "--gpu-min=1"]))
STEADY = (1.5, 5.5)


def held_midi(path):
    import mido
    mf = mido.MidiFile(ticks_per_beat=480)                  # 120 bpm: 960 ticks a second
    t = mido.MidiTrack()
    mf.tracks.append(t)
    t.append(mido.Message("control_change", control=64, value=127, time=0))
    for n in (48, 55, 64, 67):
        t.append(mido.Message("note_on", note=n, velocity=90, time=0))
    t.append(mido.Message("note_off", note=48, velocity=0, time=960 * 6))
    for n in (55, 64, 67):
        t.append(mido.Message("note_off", note=n, velocity=0, time=0))
    t.append(mido.Message("control_change", control=64, value=0, time=480))
    mf.save(path)


def main():
    if not sys.platform.startswith("linux"):
        print("allocations: skipped -- the watcher interposes glibc's malloc (Linux only): 0 failed")
        return 0
    import native as N
    import nvlive_check as NC
    exe = N.build_nvlive()
    tmp = tempfile.mkdtemp(prefix="alloccheck")
    bad = 0

    def check(what, ok, detail=""):
        nonlocal bad
        bad += not ok
        print("  %-62s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    try:
        so = os.path.join(tmp, "allocwatch.so")
        subprocess.check_call(["gcc", "-O1", "-fPIC", "-shared", "-o", so, os.path.join(HERE, "allocwatch.c"), "-ldl"])
        nvx = NC.live_export(tmp, "hall")
        mid = os.path.join(tmp, "held.mid")
        held_midi(mid)
        sr, blk = 48000, 128
        for path, popt in PATHS:
          for case, prog in CASES:
            name = "%s, %s" % (case, path)
            tag = "%s_%s" % (case, path)
            blocks, report = os.path.join(tmp, tag + ".blocks"), os.path.join(tmp, tag + ".txt")
            env = dict(os.environ, LD_PRELOAD=so, NV_ALLOCWATCH_BLOCKS=blocks, NV_ALLOCWATCH_OUT=report)
            r = subprocess.run([exe, nvx, "--test", mid, os.path.join(tmp, tag + ".wav"), "--program=%d" % prog]
                               + popt + ["--no-drums", "--async", "--reg-async", "--paced"],
                               env=env, capture_output=True, text=True)
            if path == "GPU" and "the GPU" not in r.stderr:
                print("  %-62s skipped  (no GPU here)" % name)
                continue
            if r.returncode or not os.path.exists(blocks):
                check("%s: played under the watcher" % name, False, r.stderr[-800:])
                continue
            b = np.loadtxt(blocks, dtype=np.int64, ndmin=1)
            sec = sr / blk
            w = b[int(STEADY[0] * sec):int(STEADY[1] * sec)]
            onset = int(b[:int(0.5 * sec)].sum())
            check("%s: the watcher sees the onset's allocations" % name, onset > 0, "%d in the first 0.5 s" % onset)
            nz = np.nonzero(w)[0]
            where = ""
            if len(nz):
                where = "; first at %.2f s -- its stacks in %s" % (STEADY[0] + nz[0] / sec, os.path.basename(report))
                with open(report) as f:
                    print("".join(f.readlines()[:40]))
            check("%s: held %g-%g s, no block allocates" % (name, STEADY[0], STEADY[1]), len(nz) == 0,
                  "%d of %d blocks allocated (%d allocations)%s" % (len(nz), len(w), int(w.sum()), where))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    print("allocations: %d failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
