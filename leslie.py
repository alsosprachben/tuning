#!/usr/bin/env python3
"""The rotating speaker, as geometry rather than as an effect.

A Leslie is famous for being hard to synthesise, and the reason is usually
given as "phase and directional differences", which is true but vague. What it
means concretely is this: the horn is a DIRECTIONAL source on the end of a
rotating arm, so for every path out of the cabinet -- to the listener, to each
wall, to the ceiling -- three things modulate at the rotor rate, and they do it
with a DIFFERENT PHASE on every path:

  Doppler     the arm's radial velocity toward that receiver is
              w*R*sin(w*t - alpha), where alpha is the receiver's azimuth from
              the rotor. Frequency modulation, phase -alpha.

  Level       the horn points at that receiver once per turn. Amplitude
              modulation, same phase.

  Colour      the horn beams, so what it sends that way is brighter when it
              points there. The modulation is DEEPER at high frequencies.

Take the direct sound alone and you have a tremolo with a wobble. What makes a
Leslie is that the room hears a different phase of all three than you do, and
the reflections arrive still carrying it -- so the beating between direct and
reflected sound is itself modulated, and no two rooms do it alike. A plugin
fakes that with a static early-reflection network and a modulated delay line.

This renderer does not have to fake it. Reflections are already independent
partials, each carrying the source's directivity AT ITS OWN DEPARTURE ANGLE
(blockrender's reflection loop), each with its own delay and placement. Give
each one the rotor phase of its own azimuth and the effect is a consequence of
the geometry, not a patch over it.

WHAT IS MISSING AND WHAT IS NOT. The kernel already does per-partial sinusoidal
FM with an independent phase on an ABSOLUTE clock -- which is exactly the
Doppler, and the absolute clock matters, because a rotor's angle is shared by
every note and cannot restart at each note-on. What the kernel has no column
for is amplitude modulation; but AM is not a new primitive here, since

    (1 + m*cos(w t + ph)) * sin(W t)
      = sin(W t) + (m/2)*[ sin((W+w) t + ph) + sin((W-w) t - ph) ]

is three partials, and partials are what this renderer makes.
"""
import math

# A 122-style cabinet.
HORN_RADIUS = 0.17          # m, the horn mouth's throw
DRUM_RADIUS = 0.10          # m, the bass rotor's port
CROSSOVER_HZ = 800.0        # horn above, drum below
SLOW_HZ = 0.80              # chorale
FAST_HZ = 6.60              # tremolo
# The two rotors are not synchronised and typically turn opposite ways; a fixed
# ratio here would lock them into a pattern the ear finds very quickly.
DRUM_RATIO = -0.92
C_SOUND = 343.0


def azimuth(x, z):
    """Where a receiver sits, as seen from the cabinet."""
    return math.atan2(x, max(z, 1e-6))


def doppler_depth(radius, rate_hz):
    """Peak fractional frequency deviation: the arm's tip speed over c."""
    return 2.0 * math.pi * radius * rate_hz / C_SOUND


def beam_depth(freq_hz, floor=0.10, corner=700.0, ceiling=0.85):
    """How deeply the level swings as the horn sweeps past.

    A horn is directional in proportion to its mouth against the wavelength,
    so the swing is shallow in the bass and deep in the treble. This is the
    part that makes a Leslie sound like a Leslie rather than like a tremolo:
    the bass barely moves while the top swings nearly on and off, so the
    spectrum itself breathes at the rotor rate.
    """
    x = (freq_hz / corner) ** 2
    return floor + (ceiling - floor) * x / (1.0 + x)


def path(freq_hz, x, z, fast=True):
    """(rate_hz, fm_depth, am_depth, phase) for one path out of the cabinet."""
    horn = freq_hz >= CROSSOVER_HZ
    rate = (FAST_HZ if fast else SLOW_HZ) * (1.0 if horn else DRUM_RATIO)
    radius = HORN_RADIUS if horn else DRUM_RADIUS
    return (abs(rate),
            doppler_depth(radius, abs(rate)),
            beam_depth(freq_hz) if horn else beam_depth(freq_hz) * 0.5,
            -azimuth(x, z) * (1.0 if rate > 0 else -1.0))
