"""The SC-88 Pro's CS tones (sc88_synth.SC88_SYNTH, on sc88_synth.CS, fitted to
a Yamaha CS-30L's bass), each selected as a GS file selects it on the SC-88
Pro map (CC0 the bank, CC32 3), a short phrase apiece. Writes OUT/NAME.wav
(and _room.wav); NAME cs unless given.

    python3 examples/cs_demo.py OUT [NAME]
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

TEMPO = 112.0
RIFF = [(0, 0.5), (0, 0.5), (12, 0.5), (0, 0.5), (10, 0.5), (0, 0.5), (7, 0.5), (5, 0.5)]
LINE = [(0, 1), (2, 1), (4, 1), (7, 1), (9, 2), (7, 2)]
CHORDS = [((0, 4, 7, 11), 2), ((5, 9, 12, 16), 2), ((2, 5, 9, 12), 2), ((7, 11, 14, 17), 2)]
STABS = [((0,), 1), ((0,), 1), ((3,), 1), ((5,), 1), ((0,), 2)]
# (program, SC-88 Pro bank, name, phrase, root)
TONES = [(38, 2, "CS Bass", "riff", 36), (81, 30, "CS Saw", "line", 60), (81, 18, "CS Saw Lead", "line", 72)]


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / TEMPO), time=0))
    # GS Reset
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    ev = []
    t = 0.0
    for prog, lsb, _name, phrase, root in TONES:
        ev.append((t - 0.25, 0, ("cc", 0, lsb)))
        ev.append((t - 0.25, 1, ("cc", 32, 3)))
        ev.append((t - 0.25, 2, ("pc", prog)))
        b = t
        if phrase == "riff":
            seq = [((d,), l) for d, l in RIFF] * 2
        elif phrase == "line":
            seq = [((d,), l) for d, l in LINE]
        elif phrase == "chords":
            seq = CHORDS
        else:
            seq = STABS
        for notes, length in seq:
            dur = length * (0.9 if phrase != "stabs" else 0.3)
            for d in notes:
                ev.append((b, 3, ("on", root + d, 100)))
                ev.append((b + dur, 4, ("off", root + d)))
            b += length
        t = b + 1.5
    ev.sort(key=lambda e: (e[0], e[1]))
    now = 0
    for beat, _o, m in ev:
        tk = int(round((beat + 0.5) * 480))
        if m[0] == "cc":
            msg = mido.Message("control_change", channel=0, control=m[1], value=m[2], time=tk - now)
        elif m[0] == "pc":
            msg = mido.Message("program_change", channel=0, program=m[1], time=tk - now)
        elif m[0] == "on":
            msg = mido.Message("note_on", channel=0, note=m[1], velocity=m[2], time=tk - now)
        else:
            msg = mido.Message("note_off", channel=0, note=m[1], velocity=0, time=tk - now)
        tr.append(msg)
        now = tk
    tr.append(mido.MetaMessage("end_of_track", time=480 * 4))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, (argv[2] if len(argv) > 2 else "cs") + ".wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)
    t = 0.0
    for prog, lsb, name, phrase, _root in TONES:
        n = {"riff": 8, "line": 8, "chords": 8, "stabs": 6}[phrase]
        print("  %5.1f s  %s (SC-88 Pro %d.%d)" % (t * 60.0 / TEMPO, name, prog, lsb))
        t += n + 1.5
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
