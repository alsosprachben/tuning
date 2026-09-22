#!/usr/bin/env python3
"""GM 50 and 51, Synth Strings: a string MACHINE, not a string section.

    python3 examples/synthstrings.py [outdir]
    python3 examples/synthstrings.py --check

Both were in BOWED_ENSEMBLE, so they routed per register to the four MEASURED
string bodies -- which meant GM 50 and GM 51 rendered IDENTICALLY to GM 48, the
acoustic string ensemble. Three programs, one voice. Worse than the synth
brass's redundancy, which at least was a resemblance rather than the same class.

THE CHORUS IS THE INSTRUMENT, and it is a different mechanism from a section.
An ARP or Solina string machine has ONE oscillator per key and gets its width
from a bucket-brigade chorus: a few copies at FIXED offsets, each slowly swept
by its own low-frequency oscillator. A string section has many players whose
spread is drawn per note, per player, and who never agree.

That difference is audible and is most of why nobody mistakes a string machine
for an orchestra -- the machine's width is periodic and identical on every note,
and a section's is not. Run --check to see the same three notes give the machine
the same offsets every time and the section a fresh draw each time.

The sweep costs nothing: each chorus tap's slow detune modulation is
voice_vibrato, which SectionMixin already provides per player index and which
the renderer already reads. Set to 0.35-0.85 Hz instead of a violinist's
4.6-6.4, the section's own machinery IS a BBD chorus.
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

VOICES = [(48, "string ensemble"), (50, "synth strings 1"), (51, "synth strings 2")]


def passage(program):
    """Held chords, because these are pads and the swell is the sound."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    for chord in ((52, 59, 64, 68), (50, 57, 62, 66), (48, 55, 60, 64)):
        for i, n in enumerate(chord):
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=92, time=0))
        tr.append(mido.Message("note_off", channel=0, note=chord[0], velocity=0,
                               time=480 * 4))
        for n in chord[1:]:
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\nSYSTEMATIC vs DRAWN. The same three notes, each extra voice's offset")
    print("in cents -- a machine repeats itself and a section does not:\n")
    for gm, lab in ((48, "string ensemble"), (50, "synth strings 1")):
        print("  %s:" % lab)
        for midi in (52, 64, 76):
            f0 = 440.0 * 2.0 ** ((midi - 69) / 12.0)
            q = P.property_class_for_note(gm, midi)(f0, 0.0, 1.0, 1.0)
            vs = q.unison_voices(f0, 1, 0.0)
            print("    note %2d  %s" % (midi, ", ".join(
                "%+6.2f" % (1200 * math.log2(1 + v[2])) for v in vs)))
        print()

    print("the chorus sweep, per tap:\n")
    q = P.property_class_for_note(50, 64)(329.63, 0.0, 1.0, 1.0)
    for i in range(4):
        vb = q.voice_vibrato(329.63, i)
        print("  tap %d -> %.2f cents at %.2f Hz"
              % (i, 1200 * math.log2(1 + vb[0]), vb[1]) if vb else "  tap %d -> none" % i)
    s48 = P.property_class_for_note(48, 64)
    print("\n  a violinist vibrates at %.1f-%.1f Hz; these run at %.2f-%.2f,"
          % (s48.section_vibrato_hz + P.property_class_for_note(50, 64).section_vibrato_hz))
    print("  so nothing here could be mistaken for a player's vibrato.")

    print("\nthe swell -- fixed in seconds, owing nothing to the note's wavelength:\n")
    for gm, lab in VOICES:
        c = P.property_class_for_note(gm, 64)
        print("  %-18s attack %5.0f ms   speech_cycles %s"
              % (lab, 1000 * (c.attack_time or 0.0), c.speech_cycles))

    print("\nthe spectrum at E4, dB re the fundamental:\n")
    ks = (1, 2, 3, 4, 6, 8, 12, 16)
    print("  %-18s %s" % ("", " ".join("%6d" % k for k in ks)))
    for gm, lab in VOICES:
        q = P.property_class_for_note(gm, 64)(329.63, 0.0, 1.0, 1.0)
        v = [q.harmonic_volume(k) for k in ks]
        r = v[0] or 1e-12
        print("  %-18s %s" % (lab, " ".join(
            "%6.1f" % (20 * math.log10(max(x, 1e-12) / r)) for x in v)))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in VOICES:
        mid = os.path.join(outdir, "ss%d.mid" % gm)
        out = os.path.join(outdir, "ss%d.wav" % gm)
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
        print("  %2d %-18s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
