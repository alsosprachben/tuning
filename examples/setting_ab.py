#!/usr/bin/env python3
"""A window of a file's whole mix, rendered several ways for the ear: each
TAKE sets module values before its render (and puts them back after), and
every take is written at one common gain (the loudest's peak to -1 dB) with
the room's tail as a full render has it (tone_ab.sidecar, roomtail.py).

    python3 examples/setting_ab.py FILE.mid START_S SECONDS OUT_DIR TAKE [TAKE ...]

A TAKE is name[:module.attr=value[,module.attr=value...]], the value a Python
literal: "now" alone is the code as it stands;
"drums:patch_map.GS_DRUM_TRIM_DB=3.0" one setting; several joined by commas.
Writes OUT_DIR/<file>_<name>_room_cut.wav, cut to the window.
"""
import ast
import importlib
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tone_ab as TA         # noqa: E402


def parse_take(t):
    name, _, sets = t.partition(":")
    out = []
    for kv in filter(None, sets.split(",")):
        k, v = kv.split("=", 1)
        mod, attr = k.rsplit(".", 1)
        out.append((importlib.import_module(mod), attr, ast.literal_eval(v)))
    return name, out


def main(argv):
    path, t0, secs, out = argv[1], float(argv[2]), float(argv[3]), argv[4]
    takes = [parse_take(t) for t in argv[5:]]
    os.makedirs(out, exist_ok=True)
    name = os.path.splitext(os.path.basename(path))[0].lower()
    import mido
    m = TA.window(path, set(range(len(mido.MidiFile(path).tracks))), t0, secs)
    got = []
    for tn, sets in takes:
        old = [(mod, a, getattr(mod, a)) for mod, a, _ in sets]
        try:
            for mod, a, v in sets:
                setattr(mod, a, v)
            L, R = B.render(m, "even")[:2]
        finally:
            for mod, a, v in old:
                setattr(mod, a, v)
        f = os.path.join(out, "%s_%s.wav" % (name, tn))
        TA.sidecar(f)
        got.append((f, np.asarray(L, float), np.asarray(R, float)))
        print("  %s rendered" % tn, flush=True)
    pk = max(max(np.abs(l).max(), np.abs(r).max()) for _, l, r in got)
    g = 10 ** (-1 / 20.0) / pk
    for f, l, r in got:
        B.write_wav(f, l * g, r * g)
        fr = os.path.splitext(f)[0] + "_room.wav"
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f, fr], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["sox", fr, os.path.splitext(fr)[0] + "_cut.wav", "trim", "%.3f" % t0],
                       check=True)
        print("  %s" % (os.path.splitext(fr)[0] + "_cut.wav"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
