#!/usr/bin/env python3
"""Riffsym: Ben's own 2001 piece, in its three guitar orchestrations.

    python3 examples/riffsym.py [outdir]
    python3 examples/riffsym.py --all [outdir]      # all seven orchestrations
    python3 examples/riffsym.py --src DIR [outdir]

"Riffsym -- an exercise in riff symmetry", By Ben Woolley, build 20010508.
Seven MIDI files, all 60 s, the SAME piece orchestrated differently. Because it
is his own work there is no corpus licence question -- unlike the Sankey Bach
MIDI, whose renders must not be distributed -- and his ear is the authority on
how it should sound.

That makes it the natural A/B set for voice work: one piece voiced seven ways,
where the three guitar versions differ ONLY in which part gets which program
and drive. They are the files to re-render whenever the electric guitar or bass
voices move, which is why this script exists rather than the renders being made
by hand each time.

    bwx25b   lead 29 overdriven, rhythm 1 30 distortion, rhythm 2 29, bass 35
    bwx25b2  lead / rhythm 1 / rhythm 2 all 30 distortion, bass 34
    bwx25b3  lead 29 overdriven, rhythm 1 + 2 30 distortion, bass 34

The other four are here under --all as the voice-neutral control: if a change
to the guitar voices moves the harpsichord or the ocarina, the change leaked.

    bwx25, bwx25a  harpsichord (6) + clavinet (7)
    bwx25c         ocarina (79)
    bwx25d         synth lead (81)

Riffsym writes every one of its 727 notes at velocity 100, so it exercises the
voices at exactly the level `amp_reference` is calibrated for and none of the
dynamic range above or below it. What it shows is balance, not touch.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.expanduser("~/Downloads/midi")

GUITARS = ("bwx25b", "bwx25b2", "bwx25b3")
CONTROLS = ("bwx25", "bwx25a", "bwx25c", "bwx25d")

# As examples/guitar.py renders: a chamber, and enough headroom that the amp's
# own output is what is being judged rather than the master limiter's.
ENV = {"TUNING_ROOM": "chamber", "TUNING_MASTER_DB": "-12"}


def render(name, src, outdir):
    mid = os.path.join(src, name + ".mid")
    if not os.path.exists(mid):
        print("  %-8s missing (%s)" % (name, mid))
        return None
    out = os.path.join(outdir, name + ".wav")
    env = dict(os.environ)
    for k, v in ENV.items():
        env.setdefault(k, v)
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "blockrender.py"),
                        mid, out, "even"], env=env, cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:]); print(r.stderr[-3000:])
        return None
    note = [l.strip() for l in r.stdout.splitlines()
            if "tube amp" in l or "cabinet" in l]
    print("  %-8s %5.1fs  %s" % (name, time.time() - t0, "; ".join(note[:2])))
    return out


def main(argv):
    src = SRC
    if "--src" in argv:
        i = argv.index("--src")
        src = os.path.expanduser(argv[i + 1])
        del argv[i:i + 2]
    names = GUITARS
    if "--all" in argv:
        argv.remove("--all")
        names = GUITARS + CONTROLS
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)

    print("Riffsym from %s -> %s\n" % (src, outdir))
    made = [render(n, src, outdir) for n in names]
    made = [m for m in made if m]
    print("\n  %d rendered" % len(made))
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
