#!/usr/bin/env python3
"""GM 104-111, the ethnic family: six mechanisms that were three classes.

    python3 examples/ethnic.py [outdir]
    python3 examples/ethnic.py --check

104 sitar and 110 fiddle already had voices. The other six did not: 105-107 were
the generic plucked string, 108 the generic mallet, and 109 and 111 shared one
reed pipe. They are not variations on each other:

  105 banjo     steel over a DRUMHEAD -- thin low end, fast decay, bright
  106 shamisen  the same head, plus a SAWARI buzz, and a wide heavy plectrum
  107 koto      long slack silk over a light WOODEN box: round, and it rings
  108 kalimba   a plucked CANTILEVER, 1 : 6.267 : 17.55 -- not a bar, not a string
  109 bagpipe   DRONES, at a pitch the melody cannot move
  111 shanai    a CONE, so the even harmonics come back

A MEMBRANE IS NOT A SOUNDBOARD, and that is most of the banjo and the shamisen.
A stretched skin is light and heavily damped: it cannot move enough air low
down to radiate the bottom of the note, it empties the string quickly, and what
it does radiate well is the top. Thin, fast and bright are one fact, not three.

A KALIMBA IS A CANTILEVER. It was on the mallet base, which is a struck bar.
A free-free bar runs 1 : 3 : 5 and a clamped-free cantilever 1 : 6.267 : 17.55
-- far wider, which is why a kalimba's overtones sit above the note as separate
pings instead of fusing into it. Those are the Rhodes tine's ratios, for the
same reason, and the two instruments make opposite use of them: a Rhodes damps
its tine's overtones with a tonebar and reads the fundamental with a pickup,
where a kalimba has neither.

A DRONE DOES NOT FOLLOW THE MELODY, which no other voice in this bank does.
Every other user of unison_voices returns a RATIO and so tracks the note by
construction; a drone is handed the note's frequency and returns
drone_hz/frequency, which cancels it.

ASSERTED, NOT MEASURED, all six. Neither reference collection has any of them.
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

ETH = [(104, "sitar"), (105, "banjo"), (106, "shamisen"), (107, "koto"),
       (108, "kalimba"), (109, "bagpipe"), (110, "fiddle"), (111, "shanai")]


def passage(program):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    line = [(60, 1), (62, .5), (64, .5), (67, 1), (64, .5), (62, .5),
            (60, 1), (67, .5), (69, .5), (72, 1.5), (69, .5), (67, 2)]
    for n, b in line:
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=98, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=int(480 * b)))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\nwhat each one IS:\n")
    print("  GM   name       class            bell Hz  decay  tonal  partials")
    for gm, lab in ETH:
        c = P.property_class_for_note(gm, 60)
        print("  %-4d %-10s %-16s %7.0f %6.1f %6.2f  %d"
              % (gm, lab, c.__name__.replace("Properties", ""),
                 getattr(c, "bell_cutoff_hz", 0.0), c.decay_db,
                 c.tonal_dampening, c.max_harmonic))

    print("\nthe two DRUMHEAD instruments against the wooden one:\n")
    for gm, lab in ((105, "banjo"), (106, "shamisen"), (107, "koto")):
        c = P.property_class_for_note(gm, 60)
        print("  %-9s body cuts off below %5.0f Hz, decays at %4.1f dB/s"
              % (lab, c.bell_cutoff_hz, c.decay_db))
    print("  (a membrane is light and damped: it cannot radiate the bottom of")
    print("   the note, and it empties the string quickly)")

    print("\nthe kalimba's CANTILEVER modes, against a marimba's bar:\n")
    import tonelib as T
    k = P.property_class_for_note(108, 60)(261.63, 0.0, 1.0, 1.0)
    print("  kalimba (clamped-free) : 1 : %.3f : %.2f" % (k.mode_ratio(2), k.mode_ratio(3)))
    print("  marimba (free-free bar): %s"
          % " : ".join(str(n) for n, g in T.UndercutBarProperties.bar_modes))
    print("  Rhodes tine            : the same 1 : 6.267 : 17.55, damped by a tonebar")

    print("\nthe bagpipe's drones, which the melody cannot move:\n")
    for midi, lab in ((55, "G3"), (67, "G4"), (79, "G5")):
        f0 = 440.0 * 2.0 ** ((midi - 69) / 12.0)
        q = P.property_class_for_note(109, midi)(f0, 0.0, 1.0, 1.0)
        ds = [f0 * (1 + v[2]) for v in q.unison_voices(f0, 1, 0.0)]
        print("  melody %-4s %6.1f Hz -> drones at %s Hz"
              % (lab, f0, ", ".join("%.1f" % d for d in ds)))

    print("\nand the shanai's cone against the chanter's odd-only reed:\n")
    for gm, lab in ((109, "bagpipe"), (111, "shanai")):
        q = P.property_class_for_note(gm, 60)(261.63, 0.0, 1.0, 1.0)
        v = [q.harmonic_volume(k) for k in (1, 2, 3, 4)]
        r = v[0] or 1e-12
        print("  %-9s h1-h4: %s" % (lab, " ".join(
            "%6.1f" % (20 * math.log10(max(x, 1e-12) / r)) for x in v)))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in ETH:
        mid = os.path.join(outdir, "eth%d.mid" % gm)
        out = os.path.join(outdir, "eth%d.wav" % gm)
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
        print("  %3d %-10s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
