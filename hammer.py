"""A PIANO HAMMER ON ITS STRING: the contact force, simulated.

A hammer is not a low-pass. It is a mass on a felt spring that the string
pushes back against: the felt's force grows as a power of its compression
(F = K x^p, p 2-3.5 -- Stulov; Chaigne & Askenfelt, JASA 95, 1994), so a
harder blow squeezes it stiffer and shortens the contact; and the string is
not a wall -- the wave the blow launches runs to the near end (the agraffe)
and back while the felt is still on, and in the bass that returning wave is
what throws the hammer off. In the treble the contact outlasts a period and
the felt itself damps the string's top.

So the force is simulated: the hammer (mass m, speed v0) against a lossless
string of the note's own speaking length, tension and density, struck at
the strike point, the string as two travelling velocity waves (a digital
waveguide) with inverting ends. The force's spectrum at each partial's
frequency, re its own at 0 Hz (the impulse), is the hammer's share of that
partial: harmonic_gain(). The contact's length is the onset's.

The string's numbers: speaking length L = C/f until the case runs out
(scale_c_hz_m, string_max_m: tonelib.ElectricGrandProperties' law), the
tension T per key (a grand's 600-900 N; more on the wound bass), density
from f = sqrt(T/mu) / 2L. The hammer's: mass from ~11 g in the bass to ~6.6
g at the top (Conklin, JASA 99, 1996: hammer weights across a concert
grand), the felt's K and p by register -- the free numbers, fitted.
"""
from math import cos, sin, pi, sqrt, log, exp

_CACHE = {}


def string_of(f0, scale_c_hz_m=162.0, string_max_m=1.95, tension_n=750.0, bass_tension_n=1100.0,
              bass_below_hz=110.0):
    """(L m, T N, Z = sqrt(T mu) kg/s) for a string sounding f0."""
    L = min(scale_c_hz_m / f0, string_max_m)
    T = bass_tension_n if f0 < bass_below_hz else tension_n
    c = 2.0 * L * f0                    # wave speed
    mu = T / (c * c)
    return L, T, sqrt(T * mu)


def contact(f0, v0, mass_kg, K, p, beta, L, Z, os_=8, sr=44100, t_max=0.025, alpha=0.0, tau=1e-4,
            core_x=0.0, core_K=0.0, core_p=3.5):
    """The hammer's force on the string, one value per step of 1/(sr*os_) s,
    from first touch until it leaves (or t_max). Returns (force list, dt).

    THE FELT REMEMBERS (Stulov, JASA 97, 1995): F = K [u^p - alpha/tau
    integral u^p(s) e^-(t-s)/tau ds] -- it pushes back harder squeezed than
    recovering, the more so the faster the squeeze. alpha 0 is the elastic
    felt; the memory a running sum, decaying by e^-dt/tau a step.

    AND A WORN HAMMER'S HARD LAYER (core_x m, core_K, core_p): a felt
    compacted by years of blows, or thinned, leaves less soft felt over the
    hard underfelt and the wooden core. A soft blow never reaches it; a hard
    one squeezes through and meets it -- F gains core_K (x - core_x)^core_p
    -- and the contact sharpens: a bright, hard fortissimo over an unchanged
    piano (Ben: "maybe it is older felt that is worn"). core_x 0 is off."""
    import numpy as np
    from math import exp
    dt = 1.0 / (sr * os_)
    kdec = exp(-dt / tau)
    mem = 0.0                                    # the felt's memory of u^p
    c = 2.0 * L * f0
    M = max(8, int(round(L / (c * dt))))        # string segments
    i0 = max(1, min(M - 2, int(round(beta * M))))
    r = [0.0] * M                                # right- and left-going velocity waves
    l = [0.0] * M
    ys = yh = 0.0
    vh = v0
    F = []
    touched = False
    for n in range(int(t_max / dt)):
        x = yh - ys
        up = x ** p if x > 0.0 else 0.0
        mem = mem * kdec + up * (1.0 - kdec)
        f = K * (up - alpha * mem) if x > 0.0 else 0.0
        if core_x > 0.0 and x > core_x:
            f += core_K * (x - core_x) ** core_p
        if f < 0.0:
            f = 0.0
        if f > 0.0:
            touched = True
        elif touched:
            break                                # the felt has left the string
        F.append(float(f))
        inj = f / (2.0 * Z)
        vs = r[i0 - 1] + l[i0 + 1] + inj          # the string at the strike point
        ys += vs * dt
        vh -= f / mass_kg * dt
        yh += vh * dt
        rl, ll0 = r[-1], l[0]
        r = [-ll0] + r[:-1]                       # one segment on: right-goers right,
        l = l[1:] + [-rl]                         # left-goers left; the ends invert
        r[i0] += inj
        l[i0] += inj
    return F, dt


# THE VELOCITIES THE CONTACT IS SIMULATED AT: between them a note's partials
# are the two nearest levels' blended in dB (gains_at). A table of 88 keys x 17
# levels is the whole piano, whatever the tuning -- what the C engine computes
# once, ahead of the notes, so no note waits on a simulation.
LEVELS = (1, 9, 17, 25, 33, 41, 49, 57, 65, 73, 81, 89, 97, 105, 113, 121, 127)


def nominal_f0(f0):
    """The key's equal-tempered pitch: its contact is simulated there (a few
    cents of tuning move the hammer's spectrum by nothing audible)."""
    k = int(round(69.0 + 12.0 * log(f0 / 440.0) / log(2.0)))
    return 440.0 * 2.0 ** ((k - 69) / 12.0)


def gains(f0, velocity, nharm, beta, mass_kg, K, p, v_lo=0.5, v_hi=5.0, string=None, alpha=0.0, tau=1e-4,
          core_x=0.0, core_K=0.0):
    """The hammer's share of partials 1..nharm (at h x the key's nominal
    pitch) for a key struck at MIDI velocity: |F(f)| re |F(0)|, the two
    nearest LEVELS blended in dB.

    EVERY SUM IN ORDER, every cosine libm's, the spectrum by a rotation
    (cos, sin of w(n+1) from w n's): native/voice.c computes the same, step for
    step, so a note's partials are the same numbers in the C engine as here."""
    fn = nominal_f0(f0)
    v = min(max(int(velocity), 1), 127)
    j = 0
    while j + 1 < len(LEVELS) - 1 and LEVELS[j + 1] <= v:
        j += 1
    va, vb = LEVELS[j], LEVELS[j + 1]
    ga = level_gains(fn, j, nharm, beta, mass_kg, K, p, v_lo, v_hi, string, alpha, tau, core_x, core_K)
    if v == va:
        return list(ga[:nharm])
    gb = level_gains(fn, j + 1, nharm, beta, mass_kg, K, p, v_lo, v_hi, string, alpha, tau, core_x, core_K)
    if v == vb:
        return list(gb[:nharm])
    t = (v - va) / (vb - va)
    return [exp((1.0 - t) * log(max(a, 1e-30)) + t * log(max(b, 1e-30))) for a, b in zip(ga[:nharm], gb[:nharm])]


def level_gains(fn, j, nharm, beta, mass_kg, K, p, v_lo, v_hi, string, alpha, tau, core_x, core_K):
    """LEVELS[j]'s spectrum for the key at nominal pitch fn, partials 1..nharm
    (cached, longest asked)."""
    key = (fn, j, beta, mass_kg, K, p, v_lo, v_hi, string, alpha, tau, core_x, core_K)
    got = _CACHE.get(key)
    if got is not None and len(got) >= nharm:
        return got
    L, T, Z = string_of(fn, *(string or ()))
    vel = LEVELS[j]
    v0 = v_lo * (v_hi / v_lo) ** ((vel - 1) / 126.0)
    F, dt = contact(fn, v0, mass_kg, K, p, beta, L, Z, alpha=alpha, tau=tau, core_x=core_x, core_K=core_K)
    tot = 0.0
    for x in F:
        tot += x
    out = []
    for h in range(1, nharm + 1):
        w = 2.0 * pi * fn * h * dt
        cw, sw = cos(w), sin(w)
        c, s_ = 1.0, 0.0
        re = im = 0.0
        for x in F:
            re += x * c
            im += x * s_
            c, s_ = c * cw - s_ * sw, s_ * cw + c * sw
        out.append(sqrt(re * re + im * im) / tot if tot > 0.0 else 0.0)
    _CACHE[key] = out
    if len(_CACHE) > 8192:
        _CACHE.clear()
        _CACHE[key] = out
    return out


def force_spectrum(F, dt, freqs):
    """|sum F e^-i w t| dt / (sum F dt): each frequency's share, 1 at 0 Hz."""
    tot = sum(F) * dt
    out = []
    for f in freqs:
        w = 2.0 * pi * f * dt
        re = im = 0.0
        for n, x in enumerate(F):
            re += x * cos(w * n)
            im -= x * sin(w * n)
        out.append(sqrt(re * re + im * im) * dt / tot if tot > 0 else 0.0)
    return out
