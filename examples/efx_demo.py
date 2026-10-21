#!/usr/bin/env python3
"""A short riff through Sound Canvas insertion effects, for the ear.

    python3 examples/efx_demo.py OUT_DIR PROGRAM "TYPE[,TYPE...]" [p=v ...]

Writes OUT_DIR/efx_<program>_<type>.wav (and _room.wav, with the room's
tail) for "Thru" -- the part dry -- and each named type (gsefx.TYPES names,
e.g. "Stereo Delay,Mod Delay"), all at one common gain so their levels
compare. The riff is a few bars on part 1 (MIDI channel 1), assigned to the
effect, in a GS file; p=v sets a parameter of every type (number 1-20 =
value 0-127) over its defaults. A file of our own making, so it can be
heard and shared without anyone else's sequence in it.
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import gsefx                 # noqa: E402
import tone_ab as TA         # noqa: E402

# a riff: (beat, note, length in beats) -- a broken chord, a run, a held top
RIFF = [(0, 52, 0.5), (0.5, 59, 0.5), (1, 64, 0.5), (1.5, 67, 0.5), (2, 71, 1.5),
        (4, 69, 0.25), (4.25, 67, 0.25), (4.5, 64, 0.25), (4.75, 62, 0.25), (5, 64, 2.5)]


def _sx(*addr_data):
    """A GS DT1 to address/data, with Roland's checksum over them."""
    d = list(addr_data)
    return mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12] + d + [(128 - sum(d) % 128) % 128])


def gs_file(type_key, program, params):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))                      # GS reset
    tr.append(_sx(0x40, 0x03, 0x00, type_key[0], type_key[1]))  # the type
    for n, v in params.items():
        tr.append(_sx(0x40, 0x03, 0x02 + n, v))
    tr.append(_sx(0x40, 0x41, 0x22, 0x01))                      # part 1 on the EFX
    tr.append(mido.Message("program_change", channel=0, program=program))
    ev = []
    for b, n, ln in RIFF:
        ev.append((int(b * 480), mido.Message("note_on", channel=0, note=n, velocity=96)))
        ev.append((int((b + ln) * 480) - 1, mido.Message("note_off", channel=0, note=n, velocity=0)))
    ev.append((int(10 * 480), mido.Message("note_off", channel=0, note=0, velocity=0)))
    t = 0
    for at, m in sorted(ev, key=lambda e: e[0]):
        tr.append(m.copy(time=at - t)); t = at
    return mf


def main(argv):
    out, program = argv[1], int(argv[2])
    names = ["Thru"] + [x.strip() for x in argv[3].split(",") if x.strip()]
    params = {int(k): int(v) for k, v in (a.split("=") for a in argv[4:])}
    keys = {v: k for k, v in gsefx.TYPES.items()}
    os.makedirs(out, exist_ok=True)
    got = []
    for nm in names:
        L, R = B.render(gs_file(keys[nm], program, params if nm != "Thru" else {}), "even")[:2]
        f = os.path.join(out, "efx_%d_%s.wav" % (program, nm.replace(" ", "_").replace("/", "-")))
        TA.sidecar(f)
        got.append((f, np.asarray(L, float), np.asarray(R, float)))
        print("  %s rendered" % nm, flush=True)
    pk = max(max(np.abs(l).max(), np.abs(r).max()) for _, l, r in got)
    g = 10 ** (-1 / 20.0) / pk
    for f, l, r in got:
        B.write_wav(f, l * g, r * g)
        fr = os.path.splitext(f)[0] + "_room.wav"
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f, fr], check=True,
                       stdout=subprocess.DEVNULL)
        print("  %s" % fr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
