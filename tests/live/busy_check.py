#!/usr/bin/env python3
"""The audio thread when a worker is busy: python3 tests/live/busy_check.py

The scanner's, the valve's and the register's workers are handed their jobs
with try_lock (slab.cpp): a busy lock and the audio thread goes on -- a
scanner press plays dry, answers wait for the next block, a job waits in a
list for the next hand-off. A real worker is rarely caught holding its lock,
so nvlive --test --busy=4 makes the audio side's lock fail three tries in
four, and each case is played in real time (--paced, the workers as played)
with and without it:

  scanner   a chord repeated on the scanner organ (program 16) at one setting
  valve     changing chords through the valve (program 30)
  register  chords under the pedal on the piano (program 0)

Each must: miss at its hand-offs under --busy (the held-over paths ran);
send every job it made (none lost in a list); the scanner's held-over
presses later found ready (what waited still reached the worker); sound as
without --busy (each 50 ms window's level: 95% within 2 dB, none more than
8 dB down -- a held-over job lands a block late, never not at all); and the
process end cleanly -- a worker still running into the exit crashed it
(stop_workers), so the busy scanner case runs three times.

Exits 1 if any check fails.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))

# the hand-off sites nvlive prints, in its order, and which worker each is
SITES = ("scanner", "its positions", "valve answers", "valve jobs", "register jobs", "register answers")
CASES = (("scanner", 16, "scan.mid", ("scanner", "its positions")),
         ("valve", 30, "chords.mid", ("valve answers", "valve jobs")),
         ("register", 0, "chords.mid", ("register jobs", "register answers")))


def make_midi(tmp):
    import mido
    # a chord repeated at one scanner setting: its ranks prepared once, ready after
    mf = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    mf.tracks.append(t)
    t.append(mido.Message("control_change", control=81, value=60, time=0))
    for i in range(8):
        c = (48, 55, 64, 72)
        for n in c:
            t.append(mido.Message("note_on", note=n, velocity=90, time=0 if i == 0 else 240))
        for k, n in enumerate(c):
            t.append(mido.Message("note_off", note=n, velocity=0, time=480 if k == 0 else 0))
    mf.save(os.path.join(tmp, "scan.mid"))
    # changing chords, a note over each, under the pedal (lifted once): the valve's
    # chord changes, the register's strikes and releases
    mf = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    mf.tracks.append(t)
    chords = [(48, 55, 64), (50, 57, 65), (52, 59, 67), (53, 60, 69), (55, 62, 71), (57, 64, 72), (45, 52, 60),
              (47, 55, 62)]
    t.append(mido.Message("control_change", control=64, value=127, time=0))
    for i, c in enumerate(chords):
        for n in c:
            t.append(mido.Message("note_on", note=n, velocity=90, time=0))
        t.append(mido.Message("note_on", note=c[0] + 24, velocity=70, time=240))
        t.append(mido.Message("note_off", note=c[0] + 24, velocity=0, time=120))
        for k, n in enumerate(c):
            t.append(mido.Message("note_off", note=n, velocity=0, time=120 if k == 0 else 0))
        if i == 3:
            t.append(mido.Message("control_change", control=64, value=0, time=0))
            t.append(mido.Message("control_change", control=64, value=127, time=10))
    t.append(mido.Message("control_change", control=64, value=0, time=240))
    mf.save(os.path.join(tmp, "chords.mid"))


def play(exe, nvx, mid, out, prog, busy):
    r = subprocess.run([exe, nvx, "--test", mid, out, "--program=%d" % prog, "--cpu", "--no-pipeline", "--no-drums",
                        "--async", "--reg-async", "--paced"] + (["--busy=%d" % busy] if busy else []),
                       capture_output=True, text=True)
    st = {}
    m = re.search(r"hand-offs tried/missed: (.*)", r.stderr)
    if m:
        for site, a, b in re.findall(r"([a-z ]+?) (\d+)/(\d+)", m.group(1)):
            st[site.strip()] = (int(a), int(b))
    m = re.search(r"jobs made/sent: scanner (\d+)/(\d+), valve (\d+)/(\d+), register (\d+)/(\d+); "
                  r"scanner presses ready (\d+)", r.stderr)
    jobs = [int(x) for x in m.groups()] if m else None
    return r.returncode, st, jobs, r.stderr


def levels(path, win=2400):
    _, x = wavfile.read(path)
    m = x.astype(np.float64).mean(axis=1)
    n = len(m) // win
    return 20 * np.log10(np.sqrt((m[:n * win].reshape(n, win) ** 2).mean(axis=1)) + 1e-9)


def main():
    import native as N
    import nvlive_check as NC
    exe = N.build_nvlive()
    tmp = tempfile.mkdtemp(prefix="busycheck")
    bad = 0

    def check(what, ok, detail=""):
        nonlocal bad
        bad += not ok
        print("  %-66s %s  %s" % (what, "ok" if ok else "FAILED", detail), flush=True)

    try:
        nvx = NC.live_export(tmp, "hall")
        make_midi(tmp)
        for name, prog, midf, sites in CASES:
            mid = os.path.join(tmp, midf)
            ref, busy = os.path.join(tmp, name + "_ref.wav"), os.path.join(tmp, name + "_busy.wav")
            rc0, _, _, err0 = play(exe, nvx, mid, ref, prog, 0)
            runs = [play(exe, nvx, mid, busy, prog, 4) for _ in range(3 if name == "scanner" else 1)]
            rcs = [rc0] + [r[0] for r in runs]
            check("%s: every run ends cleanly (%d runs)" % (name, len(rcs)), all(rc == 0 for rc in rcs),
                  "exits %s%s" % (rcs, "" if all(rc == 0 for rc in rcs) else "\n" + (err0 + runs[-1][3])[-800:]))
            rc, st, jobs, err = runs[-1]
            if rc or jobs is None:
                continue
            for s in sites:
                tried, missed = st.get(s, (0, 0))
                check("%s: busy at the hand-off of %s" % (name, s), missed > 0 and missed < tried,
                      "%d of %d tries missed" % (missed, tried))
            w = {"scanner": 0, "valve": 1, "register": 2}[name]
            made, sent = jobs[2 * w], jobs[2 * w + 1]
            check("%s: every job made was sent" % name, made > 0 and made == sent, "%d made, %d sent" % (made, sent))
            if name == "scanner":
                check("scanner: held-over presses later found their rank ready", jobs[6] > 0,
                      "%d presses ready" % jobs[6])
            a, b = levels(ref), levels(busy)
            n = min(len(a), len(b))
            a, b = a[:n], b[:n]
            live = a > -60
            d = np.abs(a - b)[live]
            down = (a - b)[live].max()
            check("%s: sounds as without --busy" % name,
                  live.sum() > 20 and np.percentile(d, 95) <= 2.0 and down <= 8.0,
                  "%d windows; 95%% within %.2f dB, most down %.2f dB" % (live.sum(), np.percentile(d, 95), down))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)      # (the export, made here without NV_EXPORT_CACHE: 1 GB)
    print("busy workers: %d failed" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
