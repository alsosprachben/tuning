#!/usr/bin/env python3
"""Holst, The Planets, the whole suite -- one clean pass a movement.

    python3 examples/planets.py [OUTDIR] [--only=mars,venus,...]   # default ~/Downloads/planets

Every movement from classicalmidi.co.uk (sources below), read part by part
by mt32mux -- which maps an MT-32's velocities to GM by default (3/4 v + 32,
"it could be how Jupiter was mixed", Ben) -- and rendered ONCE, whole: the
bank's own balance (patch_map.PROGRAM_TRIM_DB, GeneralUser GS's) and no
per-part moves (Ben: "just do one clean pass"; balance.py is mars.py's and
jupiter.py's). The hall at -3 dB wet, hybridmean at A = 440, master -12 dB,
the room tail from the render's own sidecar -- mars.py's and jupiter.py's
settings. Neptune is examples/neptune.py's: its offstage chorus, its ending
repeated "until the sound is lost in the distance", its recession; it maps
the velocities itself before building that ending.

THE FILES (mt32check.py read each first):
  1 Mars      Jack Hines, 468mars.mid ("Converted to GM/GS"; mars.py's choice)
  2 Venus     CRM114, HolstVenusfixed.mid -- unnamed tracks: each track's
              declared program (a "cello" track at 58-96 kept as declared)
  3 Mercury   David Siu, 471mercury.mid -- named parts
  4 Jupiter   Jack Deckard, 470Jupiter.mid -- named parts
  5 Saturn    Jack Deckard, 469saturn.mid -- named parts
  6 Uranus    Jack Deckard, 465URANUS.mid -- an MT-32 file (its Master
              Parameters track), named parts
  7 Neptune   CRM114, HolstNeptuneOrchestral.mid -- examples/neptune.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://www.classicalmidi.co.uk/"
MOVES = (("1", "mars", "Mars, the Bringer of War", "468mars.mid"),
         ("2", "venus", "Venus, the Bringer of Peace", "music2/HolstVenusfixed.mid"),
         ("3", "mercury", "Mercury, the Winged Messenger", "471mercury.mid"),
         ("4", "jupiter", "Jupiter, the Bringer of Jollity", "470Jupiter.mid"),
         ("5", "saturn", "Saturn, the Bringer of Old Age", "469saturn.mid"),
         ("6", "uranus", "Uranus, the Magician", "465URANUS.mid"),
         ("7", "neptune", "Neptune, the Mystic", "music2/HolstNeptuneOrchestral.mid"))
ROOM, WET, TUNER, MASTER_DB = "hall", "-3", "hybridmean:440", "-12"


def run(cmd, env=None):
    print("  $ " + " ".join(cmd), flush=True)
    subprocess.check_call(cmd, env=dict(os.environ, **(env or {})))


def movement(out, num, name, title, url):
    d = os.path.join(out, name)            # each movement's download in its own folder
    os.makedirs(d, exist_ok=True)
    P = lambda f: os.path.join(d, f)       # noqa: E731
    mp3 = os.path.join(out, "%s_%s.mp3" % (num, name))
    if name == "neptune":
        src = P("neptune_crm.mid")
        if not os.path.exists(src):
            run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", src, SITE + url])
        run([sys.executable, os.path.join(HERE, "examples", "neptune.py"), d])
        shutil.copy(P("neptune.mp3"), mp3)
        return mp3
    src = P(name + ".mid")
    if not os.path.exists(src):
        run(["curl", "-sfL", "--max-time", "60", "-A", "Mozilla/5.0", "-o", src, SITE + url])
    run([sys.executable, os.path.join(HERE, "mt32mux.py"), src, P(name + "_mux.mid")])
    env = {"TUNING_ROOM": ROOM, "TUNING_WET": WET, "TUNING_MASTER_DB": MASTER_DB}
    run([sys.executable, os.path.join(HERE, "blockrender.py"), P(name + "_mux.mid"), P(name + ".dry.wav"), TUNER], env)
    run([sys.executable, os.path.join(HERE, "roomtail.py"), P(name + ".dry.wav"), P(name + ".wav")], env)
    run(["sox", P(name + ".wav"), P(name + ".norm.wav"), "gain", "-n", "-1"])
    run(["lame", "-b", "320", "-h", "--quiet", "--tt", title, "--ta", "Holst", "--tl", "The Planets",
         "--tn", num + "/7", P(name + ".norm.wav"), mp3])
    for f in (name + ".norm.wav", name + ".dry.wav"):
        if os.path.exists(P(f)):
            os.remove(P(f))
    return mp3


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/planets")
    only = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--only=")), None)
    os.makedirs(out, exist_ok=True)
    for num, name, title, url in MOVES:
        if only and name not in only:
            continue
        print("== %s %s" % (num, title), flush=True)
        print("  -> %s" % movement(out, num, name, title, url), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
