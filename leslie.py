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


def path_at(freq_hz, az, fast=True):
    """(rate_hz, fm_depth, am_depth, phase) for a path leaving at azimuth `az`.

    The azimuth is the RECEIVER's, and it has to come from the full geometry:
    x against the distance down the hall, not x against height. The partial
    table stores position as right/up and keeps the distance nowhere, so this
    is handed an angle computed where the image's y was still in scope.
    """
    horn = freq_hz >= CROSSOVER_HZ
    rate = (FAST_HZ if fast else SLOW_HZ) * (1.0 if horn else DRUM_RATIO)
    radius = HORN_RADIUS if horn else DRUM_RADIUS
    return (abs(rate),
            doppler_depth(radius, abs(rate)),
            beam_depth(freq_hz) if horn else beam_depth(freq_hz) * 0.5,
            -az * (1.0 if rate > 0 else -1.0))


def path(freq_hz, x, z, fast=True):
    """Convenience for callers holding a position rather than an angle."""
    return path_at(freq_hz, azimuth(x, z), fast)


def expand(A, channels, sr, cols):
    """Give every partial of a Leslie voice its rotor, in place on the table.

    `channels` is {midi_channel: [(seconds, fast), ...]} -- the half-moon
    switch's history, not a single speed, because a rotor has momentum and
    spends real time between its two speeds.

    Done here, on the finished partial table, rather than inside emit_partial,
    because by this point each row already knows the one thing that matters:
    WHERE IT WENT. px/pz hold the direct sound's position for direct rows and
    the IMAGE's for reflected ones, so each row's azimuth -- carried in 'az',
    computed where the image's y was still in scope -- gives its rotor phase.
    A reflection is not given the listener's modulation; it is given its own.

    The Doppler goes into the existing per-partial vibrato columns, which the
    kernel integrates analytically on an absolute clock. The level swing
    becomes two sidebands, since AM of a sinusoid is three partials and this
    renderer's only primitive is a partial.

    THE RATE IS FROZEN AT EACH NOTE'S ONSET, and that is the one place this is
    an approximation rather than a model. The kernel's modulator is a fixed
    sinusoid, so a partial cannot itself chirp; what it can do is start at the
    rotor's true angle and true rate at the moment it speaks. Over a note short
    against the spin-up that is very close, and it is exact in both steady
    states. A note held right through a speed change will drift from the rotor.
    """
    import math
    n = len(A['om'])
    if not channels:
        return 0
    rotors = {}
    for ch, req in channels.items():
        rotors[ch] = (Rotor(True, req), Rotor(False, req))
    extra = {k: [] for k in cols}
    made = 0
    for i in range(n):
        # 'mch' is the MIDI channel; 'ch' is CHIFF. Getting that wrong compares
        # a chiff amount against a channel number, matches nothing, and expands
        # no partials -- silently, because the report is guarded on the count.
        ch = int(A['mch'][i])
        if ch not in rotors:
            continue
        f = A['nf'][i]
        if f <= 0.0:
            continue
        horn = f >= CROSSOVER_HZ
        rotor = rotors[ch][0 if horn else 1]
        t_on = A['non'][i] / float(sr)
        rate, angle = rotor.at(t_on)
        if not horn:
            rate *= abs(DRUM_RATIO)
            angle *= DRUM_RATIO          # and it turns the other way
        radius = HORN_RADIUS if horn else DRUM_RADIUS
        fm = doppler_depth(radius, rate)
        am = beam_depth(f) if horn else beam_depth(f) * 0.5
        # The kernel's modulator is sin(2*pi*rate*t + vp) on an absolute clock,
        # and what is wanted is sin(angle(t) - azimuth). Equate them at t_on.
        ph = angle - 2.0 * math.pi * rate * t_on - A['az'][i]
        A['vd'][i] = fm
        A['vr'][i] = rate
        A['vp'][i] = math.atan2(math.sin(ph), math.cos(ph))
        # A STOPPED ROTOR HAS NO SIDEBANDS. At rate 0 they would land exactly
        # on the carrier and simply add level -- a brake that makes the organ
        # louder, which is not what a brake does.
        if am <= 1e-4 or rate < 0.05:
            if rate < 0.05:
                A['vd'][i] = 0.0
            continue
        dw = 2.0 * math.pi * rate / sr
        for sign in (1.0, -1.0):
            for k in cols:
                extra[k].append(A[k][i])
            extra['om'][-1] = A['om'][i] + sign * dw
            extra['aL'][-1] = A['aL'][i] * am * 0.5
            extra['aR'][-1] = A['aR'][i] * am * 0.5
            extra['aM'][-1] = A['aM'][i] * am * 0.5
            extra['p0'][-1] = A['p0'][i] + sign * A['vp'][i]
            extra['p0R'][-1] = A['p0R'][i] + sign * A['vp'][i]
            made += 1
    for k in cols:
        A[k].extend(extra[k])
    return made



# ---------------------------------------------------------------------------
# Momentum.
#
# A rotor does not change speed when the switch does. Both are driven through
# friction, so each winds up and coasts down on its own time constant, and the
# HORN AND DRUM DIFFER -- the drum is heavy and its motor is working against a
# much larger moment of inertia, so it takes several seconds where the horn
# takes about one. That mismatch is the sound of the half-moon switch: for a
# few seconds after the change the two rotors are at different fractions of
# their speeds, beating against each other in a way neither steady state does.
# Getting to the speed instantly throws away the most recognisable gesture the
# instrument has.
#
# Coast-down is slower than wind-up on both, because a motor accelerating has
# torque and a motor switched off has only friction.
HORN_SPIN_UP = 1.0          # seconds to 1 - 1/e
HORN_SPIN_DOWN = 1.4
DRUM_SPIN_UP = 3.5
DRUM_SPIN_DOWN = 5.0


# The half-moon switch has three positions on the cabinets that have a brake,
# and CC1 is read in three zones to match: stop, chorale, tremolo. The brake is
# worth having because a rotor coasting to rest is the other characteristic
# gesture -- the modulation slowing and widening until it simply stops.
STOP, CHORALE, TREMOLO = 0.0, SLOW_HZ, FAST_HZ


def zone(cc_value):
    """CC1 -> requested rotor speed in Hz."""
    if cc_value < 42:
        return STOP
    if cc_value < 85:
        return CHORALE
    return TREMOLO


class Rotor:
    """One rotor's angle over time, given a schedule of speed requests.

    Integrated rather than sampled, because the ANGLE is what a partial needs
    and angle is the integral of a rate that is itself still changing. Asking
    only "how fast is it now" loses where it has got to.
    """

    def __init__(self, horn, requests, step=0.01, length=0.0):
        self.up = HORN_SPIN_UP if horn else DRUM_SPIN_UP
        self.down = HORN_SPIN_DOWN if horn else DRUM_SPIN_DOWN
        self.step = step
        self.t, self.rate, self.angle = [0.0], [], [0.0]
        req = sorted(requests) or [(0.0, TREMOLO)]
        end = max(req[-1][0], length) + 30.0
        want = float(req[0][1])
        r = want
        a = 0.0
        t = 0.0
        i = 0
        self.rate.append(r)
        while t < end:
            while i < len(req) and req[i][0] <= t:
                want = float(req[i][1])
                i += 1
            tau = self.up if want > r else self.down
            r += (want - r) * (1.0 - math.exp(-step / tau))
            a += 2.0 * math.pi * r * step
            t += step
            self.t.append(t)
            self.rate.append(r)
            self.angle.append(a)

    def at(self, t):
        """(rate_hz, angle_rad) -- linear between the integration steps."""
        k = t / self.step
        i = int(k)
        if i < 0:
            return self.rate[0], self.angle[0]
        if i >= len(self.rate) - 1:
            return self.rate[-1], self.angle[-1]
        f = k - i
        return (self.rate[i] + (self.rate[i + 1] - self.rate[i]) * f,
                self.angle[i] + (self.angle[i + 1] - self.angle[i]) * f)
