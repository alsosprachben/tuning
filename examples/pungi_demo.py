"""GS 111.8 Pungi with its drone, the wheel choosing the drone's note: one
phrase round C5 played twice, first with no CC1 -- the drone pipe on F3, as
the take's -- then with CC1 0, the wheel's lowest step, the drone on C3 (the
phrase's own tonic). Writes OUT_DIR/pungi_drone_f.wav and
OUT_DIR/pungi_drone_c.wav (and _room.wav of each).

    python3 examples/pungi_demo.py OUT_DIR
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
from efx_demo import _sx     # noqa: E402

# a snake charmer's line round C5 (the take's most-held note): (key, beats)
PHRASE = ((72, 1.0), (73, 0.5), (72, 0.5), (70, 1.0), (72, 1.5), (75, 0.5), (73, 0.5),
          (72, 1.0), (70, 0.5), (69, 0.5), (70, 1.0), (72, 2.0))


def phrase_file(cc1):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))                      # GS reset
    tr.append(mido.Message("control_change", channel=0, control=0, value=8))
    tr.append(mido.Message("control_change", channel=0, control=32, value=3))
    tr.append(mido.Message("program_change", channel=0, program=111))
    if cc1 is not None:
        tr.append(mido.Message("control_change", channel=0, control=1, value=cc1))
    for i, (k, beats) in enumerate(PHRASE):
        # legato: each note runs into the next (circular breathing)
        tr.append(mido.Message("note_on", channel=0, note=k, velocity=100, time=0 if i == 0 else 0))
        tr.append(mido.Message("note_off", channel=0, note=k, velocity=0, time=int(beats * 480)))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for name, cc1 in (("pungi_drone_f", None), ("pungi_drone_c", 0)):
        L, R = B.render(phrase_file(cc1))[:2]
        L, R = np.asarray(L, float), np.asarray(R, float)
        g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
        f = os.path.join(out, name + ".wav")
        B.write_wav(f, L * g, R * g)
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                        os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
        print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
