#!/usr/bin/env python3
"""The shanai (GM 111) against its proxy, gesture for gesture: each of cdrk's
four zurna shots (freesound 18661, CC BY 4.0; sources.md "Ethnic programs")
whole -- a G4 slurred up to a flat E5, the last a G4 alone -- then ours playing
the same notes for as long, at the measured pitches (a bend before each note),
the second note slurred.

    python3 examples/shanai_ab.py OUT.wav
"""
import glob
import os
import subprocess
import sys
import tempfile
import wave

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import blockrender as B  # noqa: E402
from freesound_slice import track  # noqa: E402

SRC = os.path.expanduser("~/Documents/refs/freesound/zurna/18661__*.flac")
SR = 44100


def load():
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "t.wav")
        subprocess.run(["sox", glob.glob(SRC)[0], "-r", str(SR), "-e", "floating-point", "-b", "32",
                        "-c", "1", w], check=True)
        from scipy.io import wavfile
        return wavfile.read(w)[1].astype(np.float64)


def shots(x):
    """[(start s, end s, [(t0, t1, Hz), ...])]: runs of periodic frames within
    25 dB of the loudest (gaps to 60 ms bridged), a note a run of steady pitch
    (60 cents)."""
    T = track(x, SR, 150, 1500)
    ok = (T[:, 1] < 0.2) & (T[:, 2] > T[:, 2].max() - 25.0)
    out, k = [], 0
    while k < len(T):
        if not ok[k]:
            k += 1
            continue
        j = k                                       # a slur's few unsteady frames bridged
        while j + 1 < len(T) and ok[j + 1:j + 7].any():
            j += 1 + int(np.argmax(ok[j + 1:j + 7]))
        notes, a = [], k
        for i in range(k + 1, j + 2):
            if i == j + 1 or abs(1200 * np.log2(T[i, 0] / np.median(T[a:i, 0]))) > 60:
                if i - a >= 10:
                    notes.append((a * 0.01, i * 0.01, float(np.median(T[a:i, 0]))))
                a = i
        out.append((k * 0.01, (j + 1) * 0.01, notes))
        k = j + 1
    return out


def ours(notes):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=111, time=0))
    tk = lambda s: int(round(s * 960))
    now, prev = 0, None
    t0 = notes[0][0]
    for a, b, hz in notes:
        key = int(round(69 + 12 * np.log2(hz / 440.0)))
        cents = 1200 * np.log2(hz / (440.0 * 2 ** ((key - 69) / 12.0)))
        at = tk(a - t0)
        t.append(mido.Message("pitchwheel", channel=0, pitch=int(round(cents / 200.0 * 8191)),
                              time=max(0, at - now - 1)))
        t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=1 if at - now >= 1 else 0))
        now = at
        if prev is not None:                         # slurred: the old note off as the new speaks
            t.append(mido.Message("note_off", channel=0, note=prev, velocity=0, time=0))
        prev = key
    end = tk(notes[-1][1] - t0)
    t.append(mido.Message("note_off", channel=0, note=prev, velocity=0, time=end - now))
    t.append(mido.MetaMessage("end_of_track", time=tk(0.4)))
    L, R = B.render(m)[:2]
    y = 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64))
    if B.SR != SR:
        from scipy.signal import resample_poly
        y = resample_poly(y, SR, B.SR)
    return y


def main(out):
    x = load()
    parts = []
    gap = np.zeros(int(0.35 * SR))
    for s0, s1, notes in shots(x):
        rec = x[max(0, int((s0 - 0.08) * SR)):int((s1 + 0.3) * SR)]
        y = ours(notes)
        e = lambda z: np.sqrt(np.mean(z[int(0.1 * SR):int(0.6 * SR)] ** 2))
        y = y * e(rec) / max(e(y), 1e-30)
        parts += [rec, gap, y, gap, gap]
        print("  shot %.2f-%.2f s: %s" % (s0, s1, ", ".join("%.0f Hz %.2f s" % (h, b - a) for a, b, h in notes)))
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


if __name__ == "__main__":
    main(sys.argv[1])
