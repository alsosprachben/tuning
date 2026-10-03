#!/usr/bin/env python3
"""Holst, The Planets: Jupiter, the Bringer of Jollity -- from Jack Deckard's MIDI to an mp3.

    python3 examples/jupiter.py [OUTDIR]       # default ~/Downloads/jupiter

THE FILE (classicalmidi.co.uk 470Jupiter.mid) is an MT-32 sequence with
excellent part names: 29 tracks, 16 channels, two harps and a glockenspiel
sharing one, the timpani on the drum channel's. mt32mux reads it part by part
-- 28 parts, every program from its name, each part's volume seeded from what
was in force on its channel when it entered (a split-off percussion track once
played its first 40 s at -56 dB without that) -- and now also splits a track
that changes instrument and carries CC11.

THE BALANCE is examples/balance.py's, as for Mars: every part rendered alone,
here and through MS Basic and FluidR3, and moved where both agree it sits out
of line with the rest. Except the PERCUSSION, which is pinned: its balance is
Ben's ear, worked out in September -- the triangle roll trimmed in
percussion_map after "it is piercingly loud", then "Sounds great" -- and a GM
reference's triangle would undo it.

The hall at -3 dB wet ("with the normal -3 dB wetness"); hybridmean at A = 440
(the September renders were plain hybrid, at the baroque 415).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import balance as B                                # noqa: E402

URL = "https://www.classicalmidi.co.uk/470Jupiter.mid"
ROOM, WET, TUNER, MASTER_DB = "hall", "-3", "hybridmean:440", "-12"
PIN = ("Percussion (General MIDI Map)",)
EAR = {}


def run(cmd, env=None):
    print("  $ " + " ".join(cmd))
    subprocess.check_call(cmd, env=dict(os.environ, **(env or {})))


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/jupiter")
    os.makedirs(out, exist_ok=True)
    P = lambda f: os.path.join(out, f)            # noqa: E731
    if not os.path.exists(P("jupiter.mid")):
        run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", P("jupiter.mid"), URL])
    run([sys.executable, os.path.join(HERE, "mt32mux.py"), P("jupiter.mid"), P("jupiter_mux.mid")])
    env = {"TUNING_ROOM": ROOM, "TUNING_WET": WET, "TUNING_MASTER_DB": MASTER_DB}
    rows = B.balance(P("jupiter_mux.mid"), out, env, TUNER, EAR, PIN)
    print("  -> %s" % B.mix(rows, out, "jupiter", env, "Jupiter, the Bringer of Jollity", "Holst", "The Planets"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
