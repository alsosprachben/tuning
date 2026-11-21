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
from math import cos, sin, pi, sqrt, log

_CACHE = {}


def string_of(f0, scale_c_hz_m=162.0, string_max_m=1.95, tension_n=750.0, bass_tension_n=1100.0,
              bass_below_hz=110.0):
    """(L m, T N, Z = sqrt(T mu) kg/s) for a string sounding f0."""
    L = min(scale_c_hz_m / f0, string_max_m)
    T = bass_tension_n if f0 < bass_below_hz else tension_n
    c = 2.0 * L * f0                    # wave speed
    mu = T / (c * c)
    return L, T, sqrt(T * mu)


def contact(f0, v0, mass_kg, K, p, beta, L, Z, os_=8, sr=44100, t_max=0.025, alpha=0.0, tau=1e-4):
    """The hammer's force on the string, one value per step of 1/(sr*os_) s,
    from first touch until it leaves (or t_max). Returns (force list, dt).

    THE FELT REMEMBERS (Stulov, JASA 97, 1995): F = K [u^p - alpha/tau
    integral u^p(s) e^-(t-s)/tau ds] -- it pushes back harder squeezed than
    recovering, the more so the faster the squeeze. alpha 0 is the elastic
    felt; the memory a running sum, decaying by e^-dt/tau a step."""
    import numpy as np
    from math import exp
    dt = 1.0 / (sr * os_)
    kdec = exp(-dt / tau)
    mem = 0.0                                    # the felt's memory of u^p
    c = 2.0 * L * f0
    M = max(8, int(round(L / (c * dt))))        # string segments
    i0 = max(1, min(M - 2, int(round(beta * M))))
    r = np.zeros(M)                              # right- and left-going velocity waves
    l = np.zeros(M)
    ys = yh = 0.0
    vh = v0
    F = []
    touched = False
    for n in range(int(t_max / dt)):
        x = yh - ys
        up = x ** p if x > 0.0 else 0.0
        mem = mem * kdec + up * (1.0 - kdec)
        f = K * (up - alpha * mem) if x > 0.0 else 0.0
        if f < 0.0:
            f = 0.0
        if f > 0.0:
            touched = True
        elif touched:
            break                                # the felt has left the string
        F.append(f)
        inj = f / (2.0 * Z)
        vs = r[i0 - 1] + l[i0 + 1] + inj          # the string at the strike point
        ys += vs * dt
        vh -= f / mass_kg * dt
        yh += vh * dt
        rl, ll0 = r[-1], l[0]
        r[1:] = r[:-1].copy()                     # one segment on: right-goers right,
        l[:-1] = l[1:].copy()                     # left-goers left
        r[i0] += inj
        l[i0] += inj
        r[0] = -ll0                               # the ends invert
        l[-1] = -rl
    return F, dt


def gains(f0, velocity, freqs, beta, mass_kg, K, p, v_lo=0.5, v_hi=5.0, string=None, alpha=0.0, tau=1e-4):
    """The hammer's share of each partial (freqs, Hz) for a key at f0 struck
    at MIDI velocity: |F(f)| re |F(0)|, cached by (f0, velocity, the felt).
    The hammer's speed spans v_lo..v_hi m/s exponentially over velocity 1..127
    (a piano's pp to ff, Askenfelt & Jansson 1990)."""
    import numpy as np
    key = (round(f0, 4), int(velocity), beta, mass_kg, K, p, v_lo, v_hi, string, alpha, tau)
    got = _CACHE.get(key)
    if got is None:
        L, T, Z = string_of(f0, *(string or ()))
        v0 = v_lo * (v_hi / v_lo) ** ((max(1, velocity) - 1) / 126.0)
        F, dt = contact(f0, v0, mass_kg, K, p, beta, L, Z, alpha=alpha, tau=tau)
        F = np.asarray(F)
        got = _CACHE[key] = (F, dt, F.sum() * dt)
        if len(_CACHE) > 4096:
            _CACHE.clear()
    F, dt, tot = got
    import numpy as np
    t = np.arange(len(F)) * dt
    w = 2.0 * np.pi * np.asarray(freqs, float)[:, None]
    re = (F * np.cos(w * t)).sum(1)
    im = (F * np.sin(w * t)).sum(1)
    return np.sqrt(re * re + im * im) * dt / tot if tot > 0 else np.zeros(len(freqs))


def contact_s(f0, velocity, beta, mass_kg, K, p, v_lo=0.5, v_hi=5.0, string=None):
    """How long the felt is on the string (s), for the onset."""
    gains(f0, velocity, [f0], beta, mass_kg, K, p, v_lo, v_hi, string)
    F, dt, _ = _CACHE[(round(f0, 4), int(velocity), beta, mass_kg, K, p, v_lo, v_hi, string)]
    return len(F) * dt


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
