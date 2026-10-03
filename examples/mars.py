#!/usr/bin/env python3
"""Holst, The Planets: Mars, the Bringer of War -- from Jack Hines' MIDI to an mp3.

    python3 examples/mars.py [OUTDIR]          # default ~/Downloads/mars

THE FILE is Jack Hines' ("Converted to GM/GS", classicalmidi.co.uk 468mars.mid),
chosen over CRM114's for its named tracks, its organ, its ten tempo changes and
an orchestra almost entirely in range ("really, really well done. The organ
sounds full" -- Ben, on its first render). It is read part by part with
mt32mux: each track keeps its own program and volume, stamped before every
note.

THE ORGAN. Hines writes one track "Clarinet/Pipe Organ": a clarinet that
becomes the organ for the last minute (324 s). mt32mux made the whole track a
clarinet until it learnt to split a track where its instrument changes -- the
September renders played the organ's entry on a clarinet -- and it now stamps
CC11 as it stamps CC7, which on the church organ is the stop word: the file's
CC11 = 127 draws the full chorus, where without it the organ sounds its 8'
alone.

The hall at -3 dB wet; hybridmean at A = 440 (the September renders were plain
hybrid, at the baroque 415).

THE BALANCE is not the file's alone: its CC7s and velocities were set for a GM
synth, and these voices are not a GM synth's. So every part is rendered on its
own, here and through two standard GM sets -- MuseScore's MS Basic and
TiMidity's FluidR3 -- and measured K-weighted while it plays (lib.loudness);
each engine is aligned to ours by its median over every part, and a part moves
by how far it sits from the others against what both references give it --
when they agree within 3 dB, and not at all when they do not ("no verdict").
The stems are summed at those gains and the hall given once to the sum
(lib.merge_room). Ben, on the first pass: "the french horns are too quiet.
The organ is not loud enough."
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import balance as B                                # noqa: E402

URL = "https://www.classicalmidi.co.uk/468mars.mid"
ROOM, WET, TUNER, MASTER_DB = "hall", "-3", "hybridmean:440", "-12"
# BY EAR, on top of the references, where they split: Ben, on the first pass,
# "the french horns are too quiet. The organ is not loud enough." FluidR3 has
# the horns 4 dB up, MS Basic level; MS Basic would even lower the organ, but
# its GM organ is one loud stop where this one is a registered full chorus.
EAR = {"French Horn": +3.0, "Pipe Organ": +3.0}


def run(cmd, env=None):
    print("  $ " + " ".join(cmd))
    subprocess.check_call(cmd, env=dict(os.environ, **(env or {})))


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/mars")
    os.makedirs(out, exist_ok=True)
    P = lambda f: os.path.join(out, f)            # noqa: E731
    if not os.path.exists(P("mars_hines.mid")):
        run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", P("mars_hines.mid"), URL])
    run([sys.executable, os.path.join(HERE, "mt32mux.py"), P("mars_hines.mid"), P("mars_mux.mid")])
    env = {"TUNING_ROOM": ROOM, "TUNING_WET": WET, "TUNING_MASTER_DB": MASTER_DB}
    rows = B.balance(P("mars_mux.mid"), out, env, TUNER, EAR)
    print("  -> %s" % B.mix(rows, out, "mars", env, "Mars, the Bringer of War", "Holst", "The Planets"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
