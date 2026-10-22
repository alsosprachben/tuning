#!/usr/bin/env python3
"""GS variation tones beside their capitals, for the ear.

    python3 examples/variation_demo.py OUT_DIR PROG.BANK[@MAP] [PROG.BANK ...]

Each tone plays efx_demo's riff (a broken chord, a run, a held top) twice:
the capital (bank 0), then the variation (CC0 = BANK, CC32 = MAP, the SC-88Pro
map, 3, by default), in a GS file of our own making. Each pair is written at
one common gain (its louder take's peak to -1 dB), so the variation's level
against its capital is heard as it is; OUT_DIR/var_<prog>_<bank>.wav holds
the pair with a second between, and _room.wav the room's tail. Programs that
live low (the basses, 32-39, and 87's bass+lead) play the riff two octaves
down, as kit_levels and sfx_levels place them.
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import patch_map as P        # noqa: E402
from efx_demo import RIFF, _sx   # noqa: E402

LOW = set(range(32, 40)) | {87}


def var_file(program, bank, gsmap):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))                      # GS reset
    tr.append(mido.Message("control_change", channel=0, control=0, value=bank))
    tr.append(mido.Message("control_change", channel=0, control=32, value=gsmap if bank else 0))
    tr.append(mido.Message("program_change", channel=0, program=program))
    shift = -24 if program in LOW else 0
    ev = []
    for b, n, ln in RIFF:
        ev.append((int(b * 480), mido.Message("note_on", channel=0, note=n + shift, velocity=96)))
        ev.append((int((b + ln) * 480) - 1, mido.Message("note_off", channel=0, note=n + shift, velocity=0)))
    ev.append((int(10 * 480), mido.Message("note_off", channel=0, note=0, velocity=0)))
    t = 0
    for at, m in sorted(ev, key=lambda e: e[0]):
        tr.append(m.copy(time=at - t)); t = at
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for spec in argv[2:]:
        pb, _, mp = spec.partition("@")
        p, b = (int(x) for x in pb.split("."))
        gsmap = int(mp) if mp else 3
        name = P.VARIATION_NAMES.get((p, P.map_bank(p, b, gsmap)), "?")
        takes = [B.render(var_file(p, bb, gsmap), "even")[:2] for bb in (0, b)]
        takes = [(np.asarray(L, float), np.asarray(R, float)) for L, R in takes]
        g = 10 ** (-1 / 20.0) / max(max(np.abs(L).max(), np.abs(R).max()) for L, R in takes)
        gap = np.zeros(int(B.SR))
        L = np.concatenate([takes[0][0], gap, takes[1][0]]) * g
        R = np.concatenate([takes[0][1], gap, takes[1][1]]) * g
        f = os.path.join(out, "var_%d_%d.wav" % (p, b))
        B.write_wav(f, L, R)
        lv = [10 * np.log10(np.mean(l ** 2 + r ** 2) / 2 + 1e-30) for l, r in takes]
        print("  %3d.%-3d %-12s variation %+5.1f dB re its capital  %s" % (p, b, name, lv[1] - lv[0], f),
              flush=True)
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                        os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
