#!/usr/bin/env python3
"""Send an impulse through the whole room chain and measure what comes back.

Every fault this looks for was found by ear first and measured afterwards, which
is the wrong order and cost several renders. An impulse through the full chain
takes a couple of seconds per room and would have caught all of them before
anyone listened:

  wrap      modal_ir shaped its output by multiplying the finished spectrum by
            a roll-off mask. That is a CIRCULAR convolution, so a copy of the
            response folded back into the buffer -- a burst 42 dB above the
            decay it interrupted, 2.75 s late. Heard as "an echo a couple
            seconds later, like a taped recording... about 3 beats or 1 measure
            offset".
  cut       overlap_add returned out[:len(x)], so the reverberation stopped at
            the last sample of the music: a 2.44 s chapel got 1.0 s. Heard as
            "This version is cut off" -- but only AFTER the wrap was fixed,
            because the wrap had been filling the space the tail should have
            occupied. A defect that hides another is why this file exists.
  coincide  every preset is laterally symmetric, so left and right walls were
            equidistant and summed coherently -- the hall had three surfaces at
            12 m, +9.5 dB of energy the room never sent, and a periodic 34 Hz
            comb heard as booming.
  fusion    a specular image past ~50 ms is heard as a separate arrival rather
            than fused, and with only six of them there is nothing to hide it.

Usage: roomcheck.py [room ...]        (default: every room)
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from roomtail import read_wav, write_wav

IMPULSE_AT = 0.5          # s
IMPULSE_LEN = 6.0         # s, comfortably longer than any T60 here
MIN_GAP_MS = 1.0          # two surfaces closer than this sum coherently
RISE_TOL_DB = 1.0         # a decay may not climb by more than this
END_FLOOR_DB = -70.0      # the tail must have got at least this far down


def envelope(x, sr, win=0.05):
    w = max(1, int(win * sr))
    return np.convolve(np.abs(x), np.ones(w) / w, 'same')


def check_geometry(T, room):
    """The stagger and the fusion handover, read off the geometry itself."""
    P = T.SoloViolinProperties()
    arr = sorted(sum(c * c for c in img) ** 0.5 / P.sound_speed
                 for _, img, _ in P.image_sources(
                     P.position_x, P.radiation_distance, P.position_z))
    gap = min(b - a for a, b in zip(arr, arr[1:])) * 1000.0
    kept = P.reflection_terms(440.0, P.position_x, P.radiation_distance,
                              P.position_z, None)
    latest = max([d for _, d, _ in kept], default=0.0)
    limit = T.SynthProperties.reflection_fusion_s
    out = []
    out.append(("coincide", gap >= MIN_GAP_MS,
                "closest two surfaces %.2f ms apart (need %.1f)"
                % (gap, MIN_GAP_MS)))
    out.append(("fusion", not limit or latest <= limit + 1e-9,
                "latest kept image %.1f ms, limit %.0f ms; %d of 6 kept"
                % (latest * 1000.0, limit * 1000.0, len(kept))))
    return out


def check_tail(room, tmp):
    """An impulse through roomtail: does the room finish, and only once?"""
    sr = 44100
    src = os.path.join(tmp, 'imp.wav')
    dst = os.path.join(tmp, 'imp_%s.wav' % room)
    x = np.zeros((int(IMPULSE_LEN * sr), 2))
    x[int(IMPULSE_AT * sr), :] = 0.5
    write_wav(src, x, sr)
    env = dict(os.environ, TUNING_ROOM=room)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'roomtail.py'),
                        src, dst], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        return [("tail", False, "roomtail failed: %s" % r.stderr.strip()[:120])]

    y, sr = read_wav(dst)
    e = envelope(y[:, 0], sr)
    peak = e.max()
    out = []

    extra = (len(y) - len(x)) / float(sr)
    out.append(("cut", len(y) > len(x),
                "%.2f s of room kept past the last sample" % extra))

    tail_db = 20.0 * np.log10(e[-int(0.05 * sr):].max() / peak + 1e-12)
    out.append(("decayed", tail_db <= END_FLOOR_DB,
                "ends at %.1f dB (need %.0f)" % (tail_db, END_FLOOR_DB)))

    # After the impulse the envelope must fall and keep falling. A wrapped copy
    # shows up as a bin that climbs above the one before it.
    start = int((IMPULSE_AT + 0.1) * sr)
    step = int(0.1 * sr)
    bins = [e[i:i + step].max() for i in range(start, len(e) - step, step)]
    db = 20.0 * np.log10(np.array(bins) / peak + 1e-12)
    rises = [(i, db[i + 1] - db[i]) for i in range(len(db) - 1)
             if db[i + 1] - db[i] > RISE_TOL_DB and db[i + 1] > END_FLOOR_DB]
    worst = max((r for _, r in rises), default=0.0)
    where = ""
    if rises:
        i = max(rises, key=lambda t: t[1])[0]
        where = " at %.2f s" % (start / sr + (i + 1) * 0.1)
    out.append(("wrap", not rises,
                "decay climbs %+.1f dB%s (tol %.1f)" % (worst, where, RISE_TOL_DB)))
    return out


def main(argv):
    import tonelib as T
    rooms = argv[1:] or sorted(T.ROOM_PRESETS)
    bad = 0
    with tempfile.TemporaryDirectory(prefix='roomcheck.') as tmp:
        for room in rooms:
            T.set_room(room)
            print("== %s" % room)
            for name, ok, msg in check_geometry(T, room) + check_tail(room, tmp):
                print("   %-9s %-4s %s" % (name, "ok" if ok else "FAIL", msg))
                bad += not ok
    print("\n%s" % ("all rooms pass" if not bad else "%d FAILED" % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
