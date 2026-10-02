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
hybrid, at the baroque 415). Not done, from the September notes: the file's
dynamics are compressed (11.6 dB across its 30 s windows), and a fader ride to
restore the crescendo to its collapse was suggested and not made.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://www.classicalmidi.co.uk/468mars.mid"
ROOM, WET, TUNER, MASTER_DB = "hall", "-3", "hybridmean:440", "-12"


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
    run([sys.executable, os.path.join(HERE, "blockrender.py"), P("mars_mux.mid"), P("mars.dry.wav"), TUNER], env)
    run([sys.executable, os.path.join(HERE, "roomtail.py"), P("mars.dry.wav"), P("mars.wav")], env)
    run(["sox", P("mars.wav"), P("mars.norm.wav"), "gain", "-n", "-1"])
    run(["lame", "-b", "320", "-h", "--quiet", "--tt", "Mars, the Bringer of War", "--ta", "Holst",
         "--tl", "The Planets", P("mars.norm.wav"), P("mars.mp3")])
    for f in ("mars.dry.wav", "mars.norm.wav", "mars.dry.room.json", "mars.dry.send.wav"):
        if os.path.exists(P(f)):
            os.remove(P(f))
    print("  -> %s" % P("mars.mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
