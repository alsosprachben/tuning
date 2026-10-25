"""The plunger (MuteTrumpet2, GM 2's 59 LSB 1; efxfilter.plunger) by ear: one
phrase on the open trumpet (GM 56), on GM 59's harmon, then on the plunger
-- each note a doo-wah, the channel's aftertouch swept 0 -> 127 -> 0 across
it (pressure opens the cup) -- then held notes opened slowly and quickly.
Writes OUT/plunger.wav (and _room.wav).

    python3 examples/plunger_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

PHRASE = [(0.0, 67, 0.9), (1.0, 70, 0.9), (2.0, 72, 1.9), (4.0, 70, 0.9), (5.0, 67, 2.8)]


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("sysex", data=[0x7E, 0x7F, 0x09, 0x03], time=0))
    ev = []

    def prog(t, ch, p, lsb):
        ev.append((t, mido.Message("control_change", channel=ch, control=0, value=121)))
        ev.append((t, mido.Message("control_change", channel=ch, control=32, value=lsb)))
        ev.append((t, mido.Message("program_change", channel=ch, program=p)))

    def note(t, ch, n, dur, wah=None):
        ev.append((t, mido.Message("note_on", channel=ch, note=n, velocity=96)))
        ev.append((t + dur, mido.Message("note_off", channel=ch, note=n, velocity=0)))
        if wah:                       # aftertouch: shut, open over `wah[0]`, shut by the end
            k = int(dur / 0.01)
            for i in range(k):
                s = i * 0.01
                v = min(1.0, s / wah[0]) if s < dur - wah[1] else max(0.0, (dur - s) / wah[1])
                ev.append((t + s, mido.Message("aftertouch", channel=ch, value=int(127 * v))))
    # the open horn, the harmon, the plunger: one channel each
    for ch, p, lsb, t0, wah in ((0, 56, 0, 0.5, None), (1, 59, 0, 5.5, None), (2, 59, 1, 10.5, (0.12, 0.2))):
        prog(0.0, ch, p, lsb)
        for b, n, d in PHRASE:
            note(t0 + b * 0.5, ch, n, d * 0.5, wah)
    # held notes on the plunger: opened slowly, then a quick wa-wa
    note(16.0, 2, 65, 2.5, (1.2, 1.2))
    for i in range(4):
        note(19.0 + 0.5 * i, 2, 65, 0.45, (0.06, 0.12))
    ev.sort(key=lambda e: (e[0], e[1].type == "note_on"))
    now = 0
    for s, m in ev:
        tick = int(round(s * 960))
        tr.append(m.copy(time=tick - now))
        now = tick
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "plunger.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f + "  (open 0.5 s, harmon 5.5 s, plunger doo-wahs 10.5 s, slow open 16 s, wa-wa 19 s)")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
