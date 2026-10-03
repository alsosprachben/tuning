#!/usr/bin/env python3
"""Holst, The Planets: Saturn, the Bringer of Old Age -- from Jack Deckard's MIDI to an mp3.

    python3 examples/saturn.py [OUTDIR]        # default ~/Downloads/saturn

THE FILE (classicalmidi.co.uk 469saturn.mid) is Deckard's, as Jupiter is: an
MT-32 sequence whose program bytes mean something else entirely -- its harps
are on Contrabass, its horns on SlapBass1 -- and whose part names are right.
So mt32mux reads it part by part, every program from its name.

THE BALANCE is examples/balance.py's: every part rendered alone, here and
through MS Basic and FluidR3, and moved where both say it sits out of line
with the rest. Nothing is pinned: Saturn has had no balance by ear.

The hall at -3 dB wet; hybridmean at A = 440.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import balance as B                                # noqa: E402

URL = "https://www.classicalmidi.co.uk/469saturn.mid"
ROOM, WET, TUNER, MASTER_DB = "hall", "-3", "hybridmean:440", "-12"
PIN = ()
EAR = {}


def run(cmd, env=None):
    print("  $ " + " ".join(cmd))
    subprocess.check_call(cmd, env=dict(os.environ, **(env or {})))


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/saturn")
    os.makedirs(out, exist_ok=True)
    P = lambda f: os.path.join(out, f)            # noqa: E731
    if not os.path.exists(P("saturn.mid")):
        run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", P("saturn.mid"), URL])
    run([sys.executable, os.path.join(HERE, "mt32mux.py"), P("saturn.mid"), P("saturn_mux.mid")])
    env = {"TUNING_ROOM": ROOM, "TUNING_WET": WET, "TUNING_MASTER_DB": MASTER_DB}
    rows = B.balance(P("saturn_mux.mid"), out, env, TUNER, EAR, PIN)
    print("  -> %s" % B.mix(rows, out, "saturn", env, "Saturn, the Bringer of Old Age", "Holst", "The Planets"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
