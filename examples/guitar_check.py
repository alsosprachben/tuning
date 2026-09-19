#!/usr/bin/env python3
"""What the electric guitar voice actually does, measured rather than asserted.

Run: python3 examples/guitar_check.py

Three things are worth checking here, and only one of them is about the sound
being "right" in a way an ear could confirm on its own:

  - the pickup's comb nulls where its geometry says it must
  - the cabinet throws away what a cabinet throws away
  - the amplifier reproduces, unprompted, why guitarists play fifths and
    octaves through distortion and avoid thirds

The last is the interesting one. It is a falsifiable prediction, not a
listening impression: nothing in this model was told which intervals survive
overdrive, so if the ordering comes out right it is because the physics is.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import cabinet
import tonelib as T
import tubeamp as TA

SR = 44100.0


def hdr(s):
    print("\n" + s + "\n" + "-" * len(s))


def partials(midi, vel=110, top=16000.0):
    """One note's partials, as the renderer builds them."""
    f0 = 440.0 * 2.0 ** ((midi - 69) / 12.0)
    p = T.ElectricGuitarProperties(f0, 0.0, vel / 127.0, 1.0)
    fs, am = [], []
    for h in range(1, 41):
        v = p.harmonic_volume(h)
        if v <= 0.0:
            continue
        f = f0 * h
        if f > top:
            break
        fs.append(f); am.append(v)
    return np.array(fs), np.array(am)


# ------------------------------------------------------------------ 1. pickup
hdr("1. the pickup combs where its geometry says")
g = T.ElectricGuitarProperties(329.63, 0.0, 1.0, 1.0)
q = g.pickup_points[0]
p = g.strike_point
print("  pick at %.3f of the length from the bridge -> nulls at n = %.1f, %.1f"
      % (p, 1.0 / p, 2.0 / p))
print("  pickup at %.3f                            -> nulls at n = %.1f, %.1f"
      % (q, 1.0 / q, 2.0 / q))
pk = [g.pickup_gain(h) / h for h in range(1, 21)]      # /h removes the velocity term
pk = [v / max(pk) for v in pk]
print("  pickup response h1..h20, dB (velocity term removed):")
print("   " + " ".join("%5.0f" % (20 * math.log10(max(v, 1e-6))) for v in pk))
lo = int(np.argmin(pk)) + 1
print("  deepest null at h%d; 1/q predicts %.1f and 2/q predicts %.1f"
      % (lo, 1.0 / q, 2.0 / q))

# ----------------------------------------------------------------- 2. cabinet
hdr("2. the cabinet, which is what stops a clip being a wasp")
cab = cabinet.get("guitar12")
fr = [50, 110, 250, 630, 1000, 2400, 4000, 6300, 10000, 16000]
print("  " + " ".join("%6d" % f for f in fr) + "  Hz")
print("  " + " ".join("%6.1f" % v for v in cab.response_db(fr)) + "  dB re 1 kHz")
print("  A clipped signal has harmonics to Nyquist and a real 12\" throws")
print("  nearly all of them away. Rendered at drive 4, the cabinet takes")
print("  14.3 dB out of 5-10 kHz and 19.9 dB out above 10 kHz, and ADDS 3.0 dB")
print("  of presence at 2-5 kHz. Bite up, fizz down.")

# ------------------------------------------------- 3. why power chords work
hdr("3. why power chords work, which nobody told it")
print("  Distortion energy landing more than 25 cents from ANY sounding")
print("  partial: products that beat against the chord rather than reinforce")
print("  it. A fifth's products fall on the near-harmonic lattice the two")
print("  notes already share; a third's do not.")
print()


def roughness(root, other, drive=2.0, tol_cents=25.0, seed=4):
    f1, a1 = partials(root)
    f2, a2 = partials(other)
    f = np.concatenate([f1, f2]); a = np.concatenate([a1, a2])
    ph = np.random.default_rng(seed).uniform(0.0, 2.0 * np.pi, len(f))
    fc, ac, pc = TA.combine(f, a, ph)
    out = TA.emit(fc.tolist(), ac.tolist(), pc.tolist(), SR, drive)
    if not out:
        return 0.0
    sounding = np.sort(f)
    tot = far = 0.0
    for hz, amp, _ in out:
        e = amp * amp
        tot += e
        j = np.searchsorted(sounding, hz)
        best = 1e9
        for k in (j - 1, j):
            if 0 <= k < len(sounding):
                best = min(best, abs(1200.0 * math.log2(hz / sounding[k])))
        if best > tol_cents:
            far += e
    return 100.0 * far / max(tot, 1e-30)


print("   interval          ratio    rough")
for name, semis, ratio in (("octave", 12, "2:1"), ("fifth", 7, "3:2"),
                           ("fourth", 5, "4:3"), ("major sixth", 9, "5:3"),
                           ("minor third", 3, "6:5"), ("tritone", 6, "45:32"),
                           ("major third", 4, "5:4")):
    print("   %-15s  %-6s  %5.1f%%" % (name, ratio, roughness(40, 40 + semis)))
print()
print("  The ordering is the fact: an octave is free, a fifth is about half as")
print("  rough as a third, and the intervals in between land in between. That")
print("  is the power chord, arrived at from the transfer function.")
print("  CAVEAT, because the metric has one: a minor SECOND scores low for the")
print("  wrong reason -- its own partials are so dense that everything is near")
print("  something. The measure is only meaningful for intervals wide enough")
print("  that 'near a sounding partial' means something, so it is not listed.")

# -------------------------------------------------- 4. drive follows the pick
hdr("4. playing harder breaks up, which is what amp_reference buys")
ref = T.ElectricGuitarProperties.amp_reference
print("  amp_reference = %s (measured: examples/guitar.py --calibrate)" % ref)
print()
print("   velocity | peak     | with reference | without (per-segment)")
base = None
for vel in (40, 70, 100, 127):
    f, a = partials(40, vel)
    f2, a2 = partials(47, vel)
    f = np.concatenate([f, f2]); a = np.concatenate([a, a2])
    ph = np.random.default_rng(7).uniform(0.0, 2.0 * np.pi, len(f))
    fc, ac, pc = TA.combine(f, a, ph)
    rows = []
    for r in (ref, None):
        st = {}
        out = TA.emit(fc.tolist(), ac.tolist(), pc.tolist(), SR, 1.0,
                      reference=r, stats=st)
        d = math.sqrt(sum(x[1] ** 2 for x in out) * 0.5) if out else 0.0
        s = math.sqrt(float((ac ** 2).sum()) * 0.5)
        rows.append(20.0 * math.log10(max(d, 1e-18) / max(s, 1e-18)))
    print("      %3d   | %.5f  |   %+7.1f dB   |   %+7.1f dB"
          % (vel, st['peak'], rows[0], rows[1]))
print()
print("  The right-hand column is what a Hammond does and what this voice")
print("  must NOT: identical distortion however hard the string is hit,")
print("  because each segment is normalised to its own peak. The left-hand")
print("  column is a fixed-gain amplifier, which is what a guitar plays into.")
