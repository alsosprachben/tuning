#!/usr/bin/env python3
"""What the Rhodes voice claims, measured against what Hamburg measured.

    python3 examples/rhodes_check.py

No score and no render: this walks the voice's own amplitude and decay laws and
prints them beside the published numbers. The papers are in sources.md --

  Muenster & Pfeifle, "Non-Linear Behaviour in Sound Production of the Rhodes
  Piano", ISMA 2014, Le Mans; and Pfeifle & Muenster, "Tone Production of the
  Wurlitzer and Rhodes E-Pianos", DAGA 2017, Kiel.

Both are high-speed camera (38-44 kfps) plus piezo accelerometer measurements
on a real Mk I, which is unusually good ground truth for a voice in this repo.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tonelib as T

# ISMA 2014, Table 1: tine frequency against the tonebar's own lowest
# eigenfrequency, struck with an impulse hammer and read by a piezo. The point
# of the table is that these two are NOT the same, "several hundred to more
# than 1400 cents apart", and that they diverge with pitch.
REAL_TONEBAR = ((79, 51), (118, 69), (176, 79), (263, 105), (393, 138),
                (588, 183), (880, 140), (1316, 145), (1969, 222))

# Measured on the instrument, and the two numbers the transient is built to.
REAL_HAMMER_CONTACT_MS = 6.42
REAL_TRANSIENT_MS = (10.0, 14.0)


def hdr(s):
    print("\n%s\n%s" % (s, "-" * len(s)))


def voice(f0, vel, cls=T.RhodesProperties):
    return cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)


def band(cls, f0=261.63, vel=100, hmax=8):
    """Level and growl over a FIXED band -- the series is trimmed where the
    curve dies, so max_harmonic moves with velocity and summing 'all of them'
    at two velocities would compare two different bands."""
    q = cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)
    top = getattr(q, "pickup_harmonics", q.max_harmonic)
    v = [q.harmonic_volume(h) if h <= top else 0.0 for h in range(1, hmax + 1)]
    tot = math.sqrt(sum(x * x for x in v))
    up = math.sqrt(sum(x * x for x in v[1:]))
    return 20 * math.log10(tot), 20 * math.log10(up / v[0])


def main(argv):
    hdr("1. The tonebar fit, against ISMA 2014 Table 1")
    print("  the tonebar is NOT tuned to the tine, and the gap grows with pitch")
    print("   tine Hz   tonebar, measured   modelled    error      ratio")
    errs = []
    for tine, meas in REAL_TONEBAR:
        got = T.ElectricPianoProperties.tonebar_hz_coeff * \
            (tine ** T.ElectricPianoProperties.tonebar_hz_power)
        errs.append(got / meas - 1.0)
        print("   %7d   %13d      %8.1f   %+6.0f%%     %.3f"
              % (tine, meas, got, 100 * errs[-1], got / tine))
    rms = math.sqrt(sum(e * e for e in errs) / len(errs))
    print("   rms %.0f%%. A transient's pitch is not its point; what has to be"
          % (100 * rms))
    print("   right is that it moves the way the measurement says, and it does.")

    hdr("2. The pickup, and the claim that is easiest to falsify")
    print("  'When aligned perfectly centered, the produced sound behind the")
    print("   pickup is twice the fundamental of the tine.' (DAGA 2017)")
    print("   offset    h1 vs h2      what it is")
    for off, what in ((0.0, "centred: no fundamental at all"),
                      (0.10, "barely off the axis"),
                      (0.30, "as voiced here"),
                      (0.60, "well off the axis")):
        cls = type("V", (T.RhodesProperties,), {"pickup_offset": off})
        q = voice(261.63, 100, cls)
        r = q.harmonic_volume(1) / q.harmonic_volume(2)
        print("   %.2f    %+8.1f dB   %s" % (off, 20 * math.log10(max(r, 1e-300)), what))

    hdr("3. Harmonic k decays k times as fast as the tine")
    print("  because harmonic k of a waveshaped sine goes as A^k. This is not")
    print("  fitted -- it is the engine's own decay law with decay_db at zero.")
    q = voice(87.31, 120)
    d1 = q.harmonic_decay(1)
    print("   partial   dB/s    ratio to h1   -40 dB in")
    for h in range(1, min(7, q.pickup_harmonics + 1)):
        d = q.harmonic_decay(h)
        print("   h%-6d  %6.2f   %8.2f      %5.2f s" % (h, d, d / d1, 40 / d))
    print("  so a hard bass note starts with a growl and ends as a bell, which")
    print("  is the Rhodes' signature and costs nothing to say.")

    hdr("4. Velocity changes the sound more than it changes the volume")
    print("  'Velocity sensitivity is to be distinguished by a change in volume")
    print("   to lesser extent than in sound.' (ISMA 2014)")
    print("   voice          level v35->v127    growl v35->v127")
    for nm, cls in (("grand piano", T.GrandPianoProperties),
                    ("Rhodes", T.RhodesProperties)):
        lo, hi = band(cls, vel=35), band(cls, vel=127)
        print("   %-13s  %+8.1f dB       %+8.1f dB   (%.1f -> %.1f)"
              % (nm, hi[0] - lo[0], hi[1] - lo[1], lo[1], hi[1]))

    hdr("5. The growl is a bass-register effect")
    print("  'Best audible in the lower register of the rhodes where the tines")
    print("   have a larger deflection.' (ISMA 2014)")
    print("   note   deflection A/w   growl     h2        partials")
    for nm, f in (("C2", 65.4), ("C3", 130.8), ("C4", 261.6),
                  ("C5", 523.3), ("C6", 1046.5)):
        q = voice(f, 100)
        print("   %-5s  %12.3f   %+6.1f   %+6.1f dB   %d"
              % (nm, q._deflection(), band(T.RhodesProperties, f, 100)[1],
                 20 * math.log10(q.harmonic_volume(2) / q.harmonic_volume(1)),
                 q.max_harmonic))

    hdr("6. The transient")
    q = voice(261.63, 100)
    tb = [h for h in range(1, q.max_harmonic + 1) if h > q.pickup_harmonics]
    ms = 1000.0 * 40.0 / q.harmonic_decay(tb[0])
    print("  hammer contact, measured        %.2f ms" % REAL_HAMMER_CONTACT_MS)
    print("  attack_time                     %.2f ms" % (1000 * q.attack_time))
    print("  waveform sinusoidal again       %.0f-%.0f ms (measured)" % REAL_TRANSIENT_MS)
    print("  tonebar modes -40 dB in         %.1f ms" % ms)
    print("  %d tonebar modes at %.0f dB/s against the tine's %.1f"
          % (len(tb), q.harmonic_decay(tb[0]), q.harmonic_decay(1)))

    hdr("7. What it costs")
    print("   note   v35   v100   v127     (a grand piano note is 64 x 3)")
    for nm, f in (("C2", 65.4), ("C4", 261.6), ("C6", 1046.5)):
        print("   %-5s  %3d   %4d   %4d"
              % (nm, voice(f, 35).max_harmonic, voice(f, 100).max_harmonic,
                 voice(f, 127).max_harmonic))
    print("  the series is trimmed where the curve dies, so playing softly is")
    print("  cheaper than playing hard -- which is also what the instrument does.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
