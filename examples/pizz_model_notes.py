#!/usr/bin/env python3
"""Our pizzicato, one note per file, for examples/pizz_measure.py.

    python3 examples/pizz_model_notes.py [REFS] [OUT]

For each instrument under REFS (default ~/Documents/refs/pizz: violin, viola,
cello, bass, as pizz_split.py writes them), renders the MODEL at every note
the recording has, one note per file, into OUT/<instrument>/<note>.model.wav
(default ~/Documents/refs/pizz/model) -- so the recording and the model go
through one measurement.

Like for like with a recording of ONE player in Iowa's anechoic room: dry
(TUNING_REFLECT=0, no tail), and GM 45's section reduced to one player with
no scatter or detune; each instrument's pizzicato class at all of its notes,
whatever register GM 45 would route them to; and GM 32, the solo upright,
measured against the bass as `gm32`. Velocity 80, Iowa's mf.
"""
import glob
import os
import sys

os.environ.setdefault("TUNING_REFLECT", "0")
os.environ.setdefault("TUNING_MASTER_DB", "-14")

import mido  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import blockrender as B  # noqa: E402
import patch_map as PM  # noqa: E402
import tonelib as T  # noqa: E402
from roomtail import write_wav  # noqa: E402
from voicefit import note_of  # noqa: E402

BODY = {"violin": T.ViolinProperties, "viola": T.ViolaProperties,
        "cello": T.CelloProperties, "bass": T.ContrabassProperties}
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def one(cls_route, prog, note, vel=80, secs=3.0):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", program=prog, time=0))
    t.append(mido.Message("note_on", note=note, velocity=vel, time=10))
    t.append(mido.Message("note_off", note=note, time=int(secs * 960)))
    PM.BOWED_SPLIT = cls_route
    L, R = B.render(m)[:2]
    return np.stack([L, R], 1).astype(np.float32)


def solo(cls):
    c = T.pizzicato(cls)
    c.section_players = 1
    c.section_spread_cents = 0.0
    c.section_onset_ms = 0.0
    return c


def main(argv):
    refs = argv[1] if len(argv) > 1 else os.path.expanduser("~/Documents/refs/pizz")
    out = argv[2] if len(argv) > 2 else os.path.join(refs, "model")
    jobs = [(i, ((128, BODY[i]),), 45) for i in BODY] + [("gm32", None, 32)]
    for inst, route, prog in jobs:
        src = "bass" if inst == "gm32" else inst
        if route:
            solo(BODY[inst])
        notes = sorted({note_of(p) for p in glob.glob(os.path.join(refs, src, "*.wav"))} - {None})
        d = os.path.join(out, inst)
        os.makedirs(d, exist_ok=True)
        for n in notes:
            x = one(route or PM.BOWED_SPLIT, prog, n)
            write_wav(os.path.join(d, "%s%d.model.wav" % (NAMES[n % 12], n // 12 - 1)), x, B.SR)
        print("  %-6s %d notes -> %s" % (inst, len(notes), d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
