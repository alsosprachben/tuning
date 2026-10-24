"""GM 2 variations by ear, through GM 2's own path: a GM 2 file (GM 2 System
On, bank select MSB 121 and GM 2's LSB) that plays each tone's capital and
then the tone, one short phrase each -- patch_map.gm2_bank reading the LSB
as the Sound Canvas tone of that name. Writes OUT/gm2_tones.wav (and
_room.wav) and prints where each pair starts.

    python3 examples/gm2_tones_demo.py OUT [PROGRAM.LSB ...]
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
from gm2_names import GM2_NAMES  # noqa: E402

# the settings-and-layers group (GM 2's tones built from voices we have)
DEFAULT = ("0.2 3.1 16.1 16.3 17.2 20.1 25.3 27.2 28.3 29.1 30.2 33.1 48.2 56.1 57.2 59.1").split()
STEP = 4.0                      # seconds a phrase


def phrase(p):
    """(beat, notes, beats) for program p: a chord for keyboards and strings,
    a line for winds, a bass line low, a riff for guitars."""
    if 32 <= p < 40:
        return [(0, (36,), 0.9), (1, (43,), 0.9), (2, (40,), 0.9), (3, (41, ), 0.4), (3.5, (43,), 0.4)]
    if 56 <= p < 80:
        return [(0, (60,), 0.9), (1, (64,), 0.9), (2, (67,), 0.9), (3, (72,), 2.5)]
    if 24 <= p < 32:
        return [(0, (52, 59, 64), 0.4), (0.5, (52, 59, 64), 0.4), (1, (55, 62, 67), 0.9),
                (2, (57, 64, 69), 0.4), (2.5, (57, 64, 69), 0.4), (3, (64, 71, 76), 2.0)]
    return [(0, (48, 60, 64, 67), 1.8), (2, (60,), 0.4), (2.5, (64,), 0.4), (3, (67, 72), 2.5)]


def song(keys):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("sysex", data=[0x7E, 0x7F, 0x09, 0x03], time=0))   # GM 2 System On
    ev, t, marks = [], 0.5, []
    for p, lsb in keys:
        for b in (0, lsb):
            ev.append((t - 0.2, mido.Message("control_change", channel=0, control=0, value=121)))
            ev.append((t - 0.2, mido.Message("control_change", channel=0, control=32, value=b)))
            ev.append((t - 0.15, mido.Message("program_change", channel=0, program=p)))
            if b:
                marks.append((t, p, lsb))
            for beat, notes, dur in phrase(p):
                for n in notes:
                    ev.append((t + beat * 0.5, mido.Message("note_on", channel=0, note=n, velocity=96)))
                    ev.append((t + (beat + dur) * 0.5, mido.Message("note_off", channel=0, note=n, velocity=0)))
            t += STEP
        t += 0.5
    ev.sort(key=lambda e: (e[0], e[1].type == "note_on"))
    now = 0
    for s, m in ev:
        tick = int(round(s * 960))
        tr.append(m.copy(time=tick - now))
        now = tick
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return mf, marks


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    keys = [tuple(int(x) for x in k.split(".")) for k in (argv[2:] or DEFAULT)]
    mf, marks = song(keys)
    for t, p, lsb in marks:
        print("  %6.1f s  %d.%d %s (after its capital at %.1f s)" % (t, p, lsb, GM2_NAMES[(p, lsb)], t - STEP))
    L, R = B.render(mf)[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "gm2_tones.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
