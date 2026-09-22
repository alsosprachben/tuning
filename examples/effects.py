#!/usr/bin/env python3
"""GM 96-103, the synth effects: the last block of eight on one voice.

    python3 examples/effects.py [outdir]
    python3 examples/effects.py --check

Built on the pads, because most of these ARE pads with one unusual property
pushed to the front -- and each class gets one the others do not:

  96  rain        stretched AND echoing: glassy droplets, repeating
  97  soundtrack  the widest chorus and the longest swell in the bank
  98  crystal     the most inharmonic voice here, capped at ten partials
  99  atmosphere  BREATH: sustain_jitter, the mechanism the pan pipe uses
  100 brightness  the hardest front, with nothing rolled off above it
  101 goblins     a deep slow WOBBLE -- 55 cents, where a violinist uses 5
  102 echoes      four repeated attacks 160 ms apart at falling gain
  103 sci-fi      odd harmonics AND a deep sweep, two exact mechanisms stacked

WHAT THE "ECHO" IS, precisely, because it is less than it first looked. The
renderer gives each player of a section their own entry instant, so evenly
spaced entries at falling gain come free. But a delay repeats a SIGNAL and this
repeats an ONSET: each tap is a fresh set of partials starting while the
original still rings, and at the same pitch they comb against it. Measured, a
note with four taps rose again TEN times in its first second. Drifting each tap
a few cents -- what tape and bucket-brigade delays do on every pass, and which
should have decorrelated them -- took ten to nine.

So what these have is a repeated ATTACK, which reads as repeats on a decaying
note and as thickening on a sustaining one. That is why GM 102 is percussive:
with a pad's 0.93 sustain the repeats merged into what they were repeating. A
true delay line wants the renderer to sum a delayed copy of the OUTPUT, which
is a pass like tremolo.py, not a property of a voice.
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

FX = [(96, "rain"), (97, "soundtrack"), (98, "crystal"), (99, "atmosphere"),
      (100, "brightness"), (101, "goblins"), (102, "echoes"), (103, "sci-fi")]


def passage(program):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    for chord in ((52, 59, 64, 68), (50, 57, 62, 69), (48, 55, 60, 67)):
        for n in chord:
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=92, time=0))
        tr.append(mido.Message("note_off", channel=0, note=chord[0], velocity=0,
                               time=480 * 5))
        for n in chord[1:]:
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\neach effect and the mechanism it does not share:\n")
    print("  GM   name        attack   B          breath  wobble  odd    taps  partials")
    for gm, lab in FX:
        c = P.property_class_for_note(gm, 64)
        print("  %-4d %-11s %5.0f ms %-10.4g %-7.2f %-7.0f %-6s %-5s %d"
              % (gm, lab, 1000 * c.attack_time, c.inharmonicity_coefficient,
                 c.sustain_jitter, c.section_vibrato_cents, c.odd_only,
                 len(getattr(c, "echo_taps", ())) or "-", c.max_harmonic))

    print("\nwhat GM 102 hands the renderer:\n")
    q = P.property_class_for_note(102, 64)(329.63, 0.0, 1.0, 1.0)
    on = q.section_onsets_at(329.63)
    vs = q.unison_voices(329.63, 1, 0.0)
    print("  onsets : %s" % ", ".join("%.2f s" % x for x in on))
    print("  gains  : %s" % ", ".join("%.3f" % v[0] for v in vs))
    print("  drift  : %s" % ", ".join("%+.1f cents" % (1200 * math.log2(1 + v[2]))
                                      for v in vs))
    print("\n  and the note it repeats has to END: sustain %.2f, decay %.1f dB/s,"
          % (P.property_class_for_note(102, 64).sustain_level,
             P.property_class_for_note(102, 64).decay_db))
    print("  against the pads' 0.93 and 0.8. See the module docstring for why.")

    print("\nthe two stretched effects, and why they carry few partials:\n")
    for gm, lab in ((96, "rain"), (98, "crystal")):
        c = P.property_class_for_note(gm, 64)
        B = c.inharmonicity_coefficient
        h = c.max_harmonic
        st = 1.0 + 0.5 * (h * h - 1) * B
        print("  GM %2d %-9s B=%-9.5g h%-3d -> %6.1f x f0 = %6.0f Hz at E4"
              % (gm, lab, B, h, h * st, 329.63 * h * st))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in FX:
        mid = os.path.join(outdir, "fx%d.mid" % gm)
        out = os.path.join(outdir, "fx%d.wav" % gm)
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
        print("  %3d %-12s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
