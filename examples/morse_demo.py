"""The Morse keyboard: Rhythm FX 2's "Calculating..." (drum key 90: CALC),
then GS 125.10 "Calculating" played -- each key its character of ITU-R
M.1677-1 (percussion_gs.MORSE_CHARS from middle C), at its pitch: SOS, then
CQ, the keys that spell them. Writes OUT/morse.wav (and _room.wav).

    TUNING_ROOM=studio python3 examples/morse_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import percussion_gs as G    # noqa: E402


def key_of(ch):
    return 60 + G.MORSE_CHARS.index(ch)


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    tr.append(mido.Message("program_change", channel=9, program=58, time=0))
    tr.append(mido.Message("control_change", channel=0, control=0, value=10, time=0))
    tr.append(mido.Message("program_change", channel=0, program=125, time=0))
    ev = [(0.25, 9, 90, 1.0)]
    t = 3.5
    for word in ("SOS", "CQ"):
        for c in word:
            n = len(G.morse_pattern(c))
            dur = G.morse_pattern(c)[-1][0] + G.morse_pattern(c)[-1][3]
            ev.append((t, 0, key_of(c), dur))
            t += dur + 3 * G.MORSE_DOT_S
        t += 7 * G.MORSE_DOT_S
    now = 0
    msgs = []
    for s, ch, n, d in ev:
        msgs.append((s, mido.Message("note_on", channel=ch, note=n, velocity=100)))
        msgs.append((s + d, mido.Message("note_off", channel=ch, note=n, velocity=0)))
    msgs.sort(key=lambda m: m[0])
    for s, m in msgs:
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
    f = os.path.join(out, "morse.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
