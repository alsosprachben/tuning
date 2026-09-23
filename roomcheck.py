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
  stage     the stagger was judged on the centre line only, and three metres
            off it the chamber and the church had arrivals 0.8 and 0.6 ms
            apart again. A PAIR must coincide somewhere on every stage (the
            side walls cross), so the test is no TRIPLE within 1 ms anywhere
            across the stage, plus the soloist's pair on the centre line.
  early     the tail faded in on a smoothstep and left the early field 20-32 dB
            short in the first 15 ms of the hall and church. It must be flat
            (decay removed) from the first reflection to the mixing time, and
            its sparse early arrivals must not stand out as clicks.

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
EARLY_TOL_DB = 3.0        # the early field's flatness, decay removed
SPIKE_TOL_DB = 6.0        # a 1 ms window over its 20 ms neighbourhood
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
    S = T.SynthProperties
    planes = [S.room_left, S.room_right, S.room_back, S.room_front, S.room_ceiling]
    trip = T.stage_triple(planes, S.room_floor, S.radiation_distance) / S.sound_speed * 1000.0 \
        if hasattr(S, "sound_speed") else T.stage_triple(planes, S.room_floor, S.radiation_distance) / 0.343
    out.append(("stage", trip >= MIN_GAP_MS,
                "no three surfaces within %.2f ms anywhere across the stage (need %.1f)"
                % (trip, MIN_GAP_MS)))
    out.append(("fusion", not limit or latest <= limit + 1e-9,
                "latest kept image %.1f ms, limit %.0f ms; %d of 6 kept"
                % (latest * 1000.0, limit * 1000.0, len(kept))))
    return out


def check_early(T, room):
    """The tail's early field, from the IR itself: flat (decay removed) from the
    first reflection to the mixing time, and no early arrival a click."""
    import roomtail as R
    sr = 48000
    p = T.StoppedPipeProperties(261.6, 0, 1, 1)
    ir, bands, onset = R.build_ir(p, sr, channels=2)
    t0 = R.first_reflection(p)
    n = len(ir)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    spec = np.fft.rfft(ir, axis=0)
    worst = 0.0
    for fc, t60, _ in bands:
        if fc not in (500.0, 1000.0, 2000.0):
            continue
        m = (f >= fc / 2 ** 0.5) & (f < fc * 2 ** 0.5)
        x = np.fft.irfft(spec * m[:, None], n, axis=0)
        # ENERGY decays at twice the amplitude's rate: 13.8/T60, not 6.9.
        d = (x ** 2).sum(axis=1) * np.exp(13.8155 * np.arange(n) / sr / t60)
        late = d[int((onset + 0.02) * sr):int((onset + 0.3) * sr)].mean()
        a = t0 + 0.002
        while a + 0.01 < onset:
            v = 10 * np.log10(max(d[int(a * sr):int((a + 0.01) * sr)].mean(), 1e-30) / late)
            worst = max(worst, abs(v))
            a += 0.01
    e = (ir.astype(np.float64) ** 2).sum(axis=1)
    k = sr // 1000
    seg = e[int(t0 * sr):int((onset + 0.2) * sr)]
    m1 = np.convolve(seg, np.ones(k) / k, 'same')
    m20 = np.convolve(seg, np.ones(20 * k) / (20 * k), 'same')
    spike = 10 * np.log10((m1[10 * k:-10 * k] / np.maximum(m20[10 * k:-10 * k], 1e-30)).max())
    return [("early", worst <= EARLY_TOL_DB,
             "flat within %.1f dB from the first reflection (%.1f ms) to the mixing "
             "time (%.0f ms); tol %.0f" % (worst, t0 * 1000, onset * 1000, EARLY_TOL_DB)),
            ("spike", spike <= SPIKE_TOL_DB,
             "loudest 1 ms %+.1f dB over its neighbourhood (tol %.0f)" % (spike, SPIKE_TOL_DB))]


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
            for name, ok, msg in (check_geometry(T, room) + check_early(T, room)
                                  + check_tail(room, tmp)):
                print("   %-9s %-4s %s" % (name, "ok" if ok else "FAIL", msg))
                bad += not ok
    print("\n%s" % ("all rooms pass" if not bad else "%d FAILED" % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
