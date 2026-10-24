"""Standard 3's [RND] (tonelib.RandomStrike) by ear: one machine-exact groove
-- every velocity the same, every hit on the grid -- on Standard 1 (kit 0),
then on Standard 3 (kit 2), then on Standard 3 with the variation x3, to
reveal what the real one does. Writes OUT/standard3.wav (and _room.wav), the
three in turn with a second of silence between.

    python3 examples/standard3_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tonelib as T          # noqa: E402

BPM = 100.0
BARS = 4


def groove(kit):
    ev = []
    for bar in range(BARS):
        b0 = bar * 4
        for k in range(8):
            cym = 51 if bar >= 2 else 42             # hats, then the ride
            ev.append((b0 + k / 2.0, 46 if (k == 7 and bar < 2) else cym, 96))
        ev += [(b0, 36, 110), (b0 + 2, 36, 110), (b0 + 2.5, 36, 110), (b0 + 1, 38, 110), (b0 + 3, 38, 110)]
        if bar == 3:
            ev += [(b0 + 3.5, 38, 110), (b0 + 3.75, 38, 110)]
    ev += [(0, 49, 110), (BARS * 4, 49, 110), (BARS * 4, 36, 110)]
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / BPM), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    tr.append(mido.Message("program_change", channel=9, program=kit, time=0))
    msgs = []
    for b, n, v in ev:
        t = int(round((b + 0.5) * 480))
        msgs += [(t, mido.Message("note_on", channel=9, note=n, velocity=v)),
                 (t + 200, mido.Message("note_off", channel=9, note=n, velocity=0))]
    msgs.sort(key=lambda m: (m[0], m[1].type == "note_on"))
    now = 0
    for t, m in msgs:
        tr.append(m.copy(time=t - now))
        now = t
    tr.append(mido.MetaMessage("end_of_track", time=4 * 480))
    return mf


def render(kit, scale=1.0):
    names = ("rnd_level_db", "rnd_effort_db", "rnd_cents", "rnd_timing_s")
    old = [getattr(T.RandomStrike, n) for n in names]
    for n, v in zip(names, old):
        setattr(T.RandomStrike, n, v * scale)
    try:
        L, R = B.render(groove(kit))[:2]
    finally:
        for n, v in zip(names, old):
            setattr(T.RandomStrike, n, v)
    return np.asarray(L, float), np.asarray(R, float)


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    parts = [render(0), render(2), render(2, 3.0)]
    gap = np.zeros(B.SR)
    L = np.concatenate([np.concatenate([p[0], gap]) for p in parts])
    R = np.concatenate([np.concatenate([p[1], gap]) for p in parts])
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "standard3.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f + "  (Standard 1; Standard 3; Standard 3, variation x3)")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
