#!/usr/bin/env python3
"""GM 72-79, the pipes: open, closed, vessel, and how much breath misses.

    python3 examples/pipes.py [outdir]
    python3 examples/pipes.py --check

Two of these were measured against the Iowa flutes (72, 73) and two were already
vessel flutes (76, 79). The other four sat on a generic base -- and they are not
variations on a flute. A flue instrument is decided by three things, and the
four differ in all of them:

  IS THE TUBE OPEN OR CLOSED?  A pan pipe is stopped at the bottom, so it
      resonates at ODD multiples and overblows at the twelfth, not the octave.
      Everything else here is open -- except the two that are not tubes at all.

  HOW IS THE JET AIMED?  A recorder has a windway cut into it: the jet reaches
      the labium identically every time, for every player, at every dynamic. A
      flautist forms it with their lips and steers it. That one fact is the
      whole difference between GM 73 and GM 74.

  HOW MUCH BREATH MISSES THE EDGE?  On a pan pipe or a shakuhachi, a great deal
      -- there is no windway, and the player aims across an open rim. That noise
      is not a defect; it is most of the sound. GM 75 had NONE of it, because
      StoppedPipeProperties ships sustain_jitter = 0 and is written for an
      organ's Gedackt rank.

And GM 78 is a category correction rather than a refinement: a HUMAN whistle is
a Helmholtz resonator, not a pipe. The mouth is the vessel and the lips its
neck, tuned by the tongue -- which is why whistling has no registers, no
overblowing and no fingering, and why it is the closest thing to a sine a person
makes. It belongs with the ocarina and the bottle, between which GM put it.
"""
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import mido

import patch_map as P

PIPES = [(72, "piccolo"), (73, "flute"), (74, "recorder"), (75, "pan flute"),
         (76, "blown bottle"), (77, "shakuhachi"), (78, "whistle"), (79, "ocarina")]


def passage(program):
    """A breath-length line: these are all one-breath instruments."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=545000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    line = [(76, 1.5), (74, .5), (72, 1), (74, 1), (76, 1), (79, 2),
            (77, 1), (76, .5), (74, .5), (72, 1.5), (71, .5), (72, 3)]
    for n, b in line:
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=94, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0,
                               time=int(480 * b)))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\nwhat each one IS -- the three things that decide a flue voice:\n")
    print("  GM  pipe          body                 tube     breath  partials")
    for gm, lab in PIPES:
        c = P.property_class_for_note(gm, 72)
        # The CLASS, not its base: OpenPipeProperties inherits
        # StoppedPipeProperties (for the machinery, having overridden odd_only),
        # so printing the base labelled the two flutes "StoppedPipe" -- the
        # exact opposite of what they are.
        name = c.__name__.replace("Properties", "")
        tube = "CLOSED" if c.odd_only else ("vessel" if any(
            k.__name__ == "VesselFluteProperties" for k in c.__mro__) else "open")
        print("  %2d  %-12s %-20s %-8s %5.2f   %s"
              % (gm, lab, name, tube, c.sustain_jitter, c.max_harmonic))

    print("\nthe spectra at C5, dB relative to the fundamental:\n")
    print("  GM  pipe          %s" % " ".join("%6d" % k for k in range(1, 9)))
    for gm, lab in PIPES:
        q = P.property_class_for_note(gm, 72)(523.25, 0.0, 1.0, 1.0)
        v = [q.harmonic_volume(k) for k in range(1, 9)]
        r = v[0] or 1e-12
        print("  %2d  %-12s %s" % (gm, lab, " ".join(
            "%6.1f" % (20 * math.log10(max(x, 1e-12) / r)) for x in v)))
    print("\n  The pan pipe's even harmonics are ABSENT, not quiet: a tube closed")
    print("  at one end does not have them. Nothing else in the family is closed.")
    print("  The whistle is the purest thing here, which is what a whistled note is.")
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in PIPES:
        mid = os.path.join(outdir, "pipe%d.mid" % gm)
        out = os.path.join(outdir, "pipe%d.wav" % gm)
        passage(gm).save(mid)
        env = dict(os.environ)
        env.setdefault("TUNING_ROOM", "chamber")
        env.setdefault("TUNING_MASTER_DB", "-12")
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "blockrender.py"),
                            mid, out, "even"], env=env, cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:]); print(r.stderr[-2000:]); return 1
        print("  %2d %-13s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
