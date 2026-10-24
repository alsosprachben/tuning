"""The GS reverb macros, each in the room or device it maps to
(blockrender.GS_REVERB_ROOM): one phrase -- piano chords, a snare, each
followed by silence to hear the tail -- as a GS file per macro (a GS reset,
then 40 01 30), rendered, roomtail's tail drawn, and the eight joined with a
spoken-order gap: Room 1, Room 2, Room 3, Hall 1, Hall 2, Plate, Delay,
Panning Delay. Writes OUT/gs_reverb_<n>_<room>.wav and OUT/gs_reverbs.wav.

    python3 examples/gs_reverb_demo.py OUT [MACRO ...]
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

NAMES = ("Room 1", "Room 2", "Room 3", "Hall 1", "Hall 2", "Plate", "Delay", "Panning Delay")


def _sysex(addr, data):
    body = list(addr) + list(data)
    return mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12] + body + [(128 - sum(body) % 128) % 128])


def phrase(macro):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(_sysex((0x40, 0x00, 0x7F), (0x00,)))            # GS reset
    tr.append(_sysex((0x40, 0x01, 0x30), (macro,)))           # REVERB MACRO
    tr.append(mido.Message("program_change", channel=0, program=0, time=240))
    ev = []
    for beat, chord in ((0, (60, 64, 67)), (1, (62, 65, 69)), (2, (59, 62, 67, 71))):
        for n in chord:
            ev.append((beat * 480, 0, n, 96, 400 if beat < 2 else 900))
    for beat in (5, 5.5, 6):                                  # the snare, after the chords ring out
        ev.append((int(beat * 480), 9, 38, 110, 120))
    msgs = []
    for t, ch, n, v, d in ev:
        msgs.append((t, 1, ch, n, v))
        msgs.append((t + d, 0, ch, n, 0))
    msgs.sort()
    now = 0
    for t, on, ch, n, v in msgs:
        tr.append(mido.Message("note_on", channel=ch, note=n, velocity=v, time=t - now))
        now = t
    tr.append(mido.MetaMessage("end_of_track", time=int(10 * 480) - now))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    import blockrender as B
    macros = [int(a) for a in argv[2:]] or list(range(8))
    joined = []
    for m in macros:
        room = B.GS_REVERB_ROOM[m]
        mid = os.path.join(out, "gs_reverb_%d.mid" % m)
        phrase(m).save(mid)
        dry = os.path.join(out, "gs_reverb_%d_%s_dry.wav" % (m, room))
        wet = os.path.join(out, "gs_reverb_%d_%s.wav" % (m, room))
        subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, dry], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), dry, wet], check=True,
                       stdout=subprocess.DEVNULL)
        x, sr = B.read_wav(wet) if hasattr(B, "read_wav") else (None, None)
        if x is None:
            import roomtail as R
            x, sr = R.read_wav(wet)
        joined.append(np.asarray(x, float))
        joined.append(np.zeros((int(0.8 * sr), x.shape[1])))
        print("  %-14s -> %-13s %s" % (NAMES[m], room, wet))
    y = np.concatenate(joined)
    y *= 10 ** (-1 / 20.0) / np.abs(y).max()
    B.write_wav(os.path.join(out, "gs_reverbs.wav"), y[:, 0], y[:, 1])
    print("  " + os.path.join(out, "gs_reverbs.wav"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
