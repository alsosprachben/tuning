#!/usr/bin/env python3
"""The free reeds: GM 20-23, and why they are not a pipe organ's reed stop.

    python3 examples/reeds.py [outdir]       # render all four
    python3 examples/reeds.py --check        # measure, no render

GM 20 Reed Organ, 21 Accordion, 22 Harmonica and 23 Tango Accordion are all
FREE reeds, and all four used to render as ReedOrganProperties -- which is a
pipe organ's reed RANK: a beating reed with a resonator behind it. That class is
right for what it is, and is the base of the clarinets, so it did not change;
what changed is that these four stopped pointing at it.

The distinction is the resonator, and it is worth hearing rather than reading:

  a BEATING reed slams shut against a shallot and a PIPE selects the harmonics.
  A stopped cylinder passes odd multiples, so the rank is odd-only, and a short
  high resonator goes weak, so the rank breaks back early.

  a FREE reed swings THROUGH a slot, never seals, and has no resonator at all.
  The pitch is the tongue's own bending mode and the harmonics come from the
  airflow it chops -- so there are evens, and there is no break-back. An
  accordion carries a 4' piccolo rank to the top of its compass precisely
  because nothing up there has to resonate.

--check prints the series for each voice and the two numbers that separate the
accordion from the bandoneon, which is the whole difference between GM 21 and
GM 23: one is tuned wet and the other dry.
"""
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import mido

import tonelib as T

VOICES = [(20, "Reed organ"), (21, "Accordion"),
          (22, "Harmonica"), (23, "Tango accordion")]


def passage(program):
    """A sustained line and a chord: free reeds are a wind voice, so what
    matters is the steady state and how the banks beat against each other,
    not an attack."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))

    def note(n, beats, vel=88, gap=0):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=vel, time=gap))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0,
                               time=int(480 * beats)))

    # A rising line, so the register behaviour is audible...
    for n in (53, 55, 57, 60, 62, 65, 69, 72):
        note(n, 0.75)
    # ...then a held chord, where a wet tuning warbles and a dry one does not.
    for n, t0 in ((53, 240), (57, 0), (60, 0), (65, 0)):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=84, time=t0))
    tr.append(mido.Message("note_off", channel=0, note=53, velocity=0, time=480 * 6))
    for n in (57, 60, 65):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.MetaMessage("end_of_track", time=480))
    return m


def check():
    ks = (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24)
    print("\nthe series at C4, dB relative to the fundamental\n")
    print("  voice              %s" % "".join("%6d " % k for k in ks))
    import patch_map as P
    for gm, label in VOICES:
        cls = P.property_class_for_program(gm)
        p = cls(261.63, 0.0, 1.0, 1.0)
        v = {k: p.harmonic_volume(k) for k in ks}
        ref = v[1] or 1e-12
        print("  %-18s %s" % (label, "".join(
            "%6.1f " % (20 * math.log10(max(v[k], 1e-12) / ref)) for k in ks)))

    print("\nthe evens are the point. A reed in a stopped pipe has none:\n")
    p = P.property_class_for_program(20)(261.63, 0.0, 1.0, 1.0)
    r = lambda k: 20 * math.log10(max(p.harmonic_volume(k), 1e-12) / p.harmonic_volume(1))
    print("  free reed (GM 20)      h2 %5.1f   h4 %5.1f   h6 %5.1f dB" % (r(2), r(4), r(6)))
    q = T.ReedOrganProperties(261.63, 0.0, 1.0, 1.0)
    rq = lambda k: (20 * math.log10(max(q.harmonic_volume(k), 1e-12) / q.harmonic_volume(1))
                    if q.harmonic_volume(1) else float('nan'))
    print("  organ reed rank        h2 %5.1f   h4 %5.1f   h6 %5.1f dB  (odd_only)"
          % (rq(2), rq(4), rq(6)))

    print("\nand wet against dry -- the whole of GM 21 versus GM 23:\n")
    for gm, label in ((21, "Accordion (musette)"), (23, "Tango (dry)")):
        cls = P.property_class_for_program(gm)
        a = cls(261.63, 0.0, 1.0, 1.0)
        banks = a.unison_voices(261.63, 1, 0.0)
        f = [261.63 * (1.0 + b[2]) for b in banks]
        print("  %-22s banks at %s Hz; beat %.2f Hz against the true 8'"
              % (label, ", ".join("%.2f" % x for x in f), abs(f[0] - 261.63)))

    print("\nno deep zeros: an idealised pulse has true nulls, and the gate spread")
    print("smears them (see FreeReedProperties).\n")
    for gm, label in VOICES:
        cls = P.property_class_for_program(gm)
        p = cls(261.63, 0.0, 1.0, 1.0)
        rr = lambda k: 20 * math.log10(max(p.harmonic_volume(k), 1e-12)
                                       / max(p.harmonic_volume(1), 1e-12))
        worst = min((rr(k), k) for k in range(2, 25))
        print("  %-18s deepest partial h%-2d at %6.1f dB" % (label, worst[1], worst[0]))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, label in VOICES:
        mid = os.path.join(outdir, "reed%d.mid" % gm)
        out = os.path.join(outdir, "reed%d.wav" % gm)
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
        print("  %2d %-18s %5.1fs -> %s" % (gm, label, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
