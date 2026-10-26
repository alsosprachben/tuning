"""The SC-88 Pro's Jupiter-8 tones (sc88_synth.SC88_SYNTH, each the panel
fitted to the Separate Ways record -- sc88_synth.JUPITER -- with what its name
changes), each selected as a GS file selects it on the SC-88 Pro map (CC0 the
bank, CC32 3), a short phrase apiece. Writes
OUT/jp8.wav (and _room.wav).

    python3 examples/jp8_demo.py OUT
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
# (GM 2 program, LSB, name, the phrase, its root)
# (program, SC-88 Pro bank, name, phrase, root)
TONES = [(7, 33, "JP8 Clav. 1", "riff", 60), (7, 35, "JP8 Clav. 2", "riff", 60), (38, 3, "JP-4 Bass", "riff", 36),
         (38, 4, "JP-8 Bass", "riff", 36), (38, 6, "JPMG Bass", "riff", 36), (50, 3, "JP Strings", "chords", 60),
         (80, 18, "JP-8 Square", "line", 72), (80, 25, "JP8 PulseLd1", "line", 72), (80, 26, "JP8 PulseLd2", "line", 72),
         (87, 4, "JP8 BsLead 1", "riff", 48), (87, 5, "JP8 BsLead 2", "riff", 48), (92, 2, "JP8 Sqr Pad", "chords", 60)]


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
    f = os.path.join(out, "jp8.wav")
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
