#!/usr/bin/env python3
"""The Wurlitzer Spectra-Tone: two cones back to back on one rotor.

Ben's Wurlitzer 4500 (c. 1968-70) has, inside its console, a rotor carrying
two 4" speakers facing opposite ways (patent US3070660; schematic 504600),
with tabs SPECTRA-TONE UPPER and LOWER (each manual through the rotor) and
CHORUS (the rotor and the console speakers together), and a THEATER/CATHEDRAL
rocker: fast and slow. A Leslie is one horn on an arm -- one beam a turn, one
Doppler -- and that is what leslie.py and the kernel's lobe draw. This is not
that, and does not sound like it:

  * THE SWELLS PER TURN GROW WITH PITCH. Measured in Ben's garage (2026-11-21,
    17 takes, refs/wurlitzer_ben/spectratone2/SESSION.md): one a turn to C5,
    three on C6, two on C7. Each cone is a piston that beams more the higher
    the note, and the two beams -- unequal, one each way, at different radii
    -- pass the listener at different points of the turn, each with its own
    Doppler, interfering. A raised cosine has no such thing in it.
  * THE PITCH SWING IS SMALL ON LOW NOTES (under a cent) and 3-7 cents at 1-2
    kHz: the cones move in opposite directions, so where both are heard their
    Dopplers cancel, and where one beams the other's is gone.

So a row's gain is COMPLEX: S(theta) = c + g * sum_i A_i(f, theta) exp(j k r_i
s_i cos theta), theta the rotor's angle less the azimuth of the row's path
(each image in the room hears its own part of the turn, as with the Leslie).
|S| is the swirl, arg S the pitch swing. The kernel works it at the Leslie's
grid points (synthkernel.c cone_grid) and turns the row's phasor by it.

THE TABLE. A_i, each cone's level toward the path (the piston's pattern and
the cone's rear), is smooth in frequency and angle, so it is a table: TABLE_NA
angles by 1/TABLE_BPO-octave bins. The Doppler phase k r cos theta is NOT --
at 12 kHz it is 37 radians and turns a radian across a 1/24-octave bin -- so
the kernel works it from the row's own frequency. c (the share that does not
turn: the steady share, and for Chorus the console speakers) and g (the rotor
path's response) are smooth too, per bin. One table for every row of every
file; the export carries it (native/leslie.cpp reads it, not rebuilds it).

THE FIT (examples/spectratone_garage.py): the two cones fitted INSIDE the
garage -- its floor, back wall and ceiling as images, two loose paths for the
rest -- so the garage can be dropped again: Ben, model the dry side; our room
supplies the reflections. Only the cones are kept here, on the direct path.
"""
import math

import numpy as np

# THE CONES (spectratone_garage.json, 2026-11-22: with the cone's rear a fade
# just past side-on -- a hard switch there stepped the level eight times a
# turn, a click every cycle: Ben heard it). Cost 3.74 against the takes'
# swells per turn and pitch swing: C6 three a turn 0.57 (takes 0.60-0.78),
# depth 20 dB (15-23); C7 two a turn 0.53 (0.35-0.57), 17 dB (16-21); the pitch
# swing 3.6 and 4.5 cents (2.5-5.3, 6-7.6). Short: C7's swing, and C2's 1-3 dB.
RADIUS_M = 0.12671          # cone 1's centre from the axis
CONE_RADIUS_M = 0.04912     # the piston's radius (a 4" cone)
BACK = 0.32075              # a cone's level behind it, against in front
CONE2_GAIN = 0.49584        # cone 2 against cone 1
CONE2_RADIUS_M = 0.16748    # cone 2's centre from the axis (facing the other way)
LEAK = 1.11591              # the steady share at 1 kHz, against the rotor's mean
LEAK_SLOPE = -0.90019       # ...as (f / 1 kHz)^LEAK_SLOPE: the low notes barely move
REAR_W = 0.2                # the rear's fade, in cos(psi): ~12 degrees past side-on
C_SOUND = 343.0

# THE ROTOR (spectratone_ramps.py, the warm takes): Cathedral 0.60 turns a
# second, Theater 2.95 (1.6-2.15 while the organ was cold: Ben's garage at
# 40 F); slow to fast on a 13 s time constant -- the motor working a light
# rotor up through its belt -- and fast to slow in about one.
SLOW_HZ = 0.60
FAST_HZ = 2.95
SPIN_UP = 13.0
SPIN_DOWN = 1.0

# THE ROTOR PATH AGAINST THE CONSOLE SPEAKERS, dB by frequency: what the 4"
# cones do that the divider's tab tables (the console speakers, as measured)
# do not. examples/spectratone_response.py, the rotor takes less the dry ones
# per partial: the garage's comb swings single partials 10 dB, so only the
# broad shape -- weak under 250 Hz (-7.6 at 128), flat to 1 kHz, -11 by 2 kHz
# -- is taken, and the level held at the console's (the mic sat at the console
# speakers, the rotor's slits are on top: its -6 dB there is the mic's).
RESPONSE_DB = ((65.0, -10.0), (128.0, -6.0), (250.0, 0.0), (1000.0, 0.0), (2000.0, -8.0),
               (4000.0, -14.0), (8000.0, -20.0))
# CHORUS: the rotor and the console speakers at equal power
CHORUS_SHARE = 0.5 ** 0.5

MODES = ('rotor', 'chorus')
TABLE_F0 = 30.0
TABLE_BPO = 24
TABLE_NB = int(math.ceil(math.log2(20000.0 / TABLE_F0) * TABLE_BPO)) + 2
TABLE_NA = 128              # a power of two: the kernel wraps with a mask

# the CONES as the kernel takes them: (sign, radius) -- cone 1 faces the angle
# theta = 0, cone 2 the other way
CONES = ((1.0, RADIUS_M), (-1.0, CONE2_RADIUS_M))


def zone(cc_value):
    """CC80 (tonelib.WHEEL_CC['leslie']) -> the rotor's speed: below 64 the
    rocker down, Cathedral; else Theater."""
    return SLOW_HZ if cc_value < 64 else FAST_HZ


def response_gain(f):
    """RESPONSE_DB at f, linear (log-frequency interpolation, flat past the ends)."""
    pts = RESPONSE_DB
    if f <= pts[0][0]:
        db = pts[0][1]
    elif f >= pts[-1][0]:
        db = pts[-1][1]
    else:
        for (f0, d0), (f1, d1) in zip(pts, pts[1:]):
            if f <= f1:
                db = d0 + (d1 - d0) * math.log(f / f0) / math.log(f1 / f0)
                break
    return 10.0 ** (db / 20.0)


def piston(x):
    """2 J1(x) / x: a rigid piston's pattern, x = k a sin(psi)."""
    from scipy.special import j1
    x = np.where(np.abs(x) < 1e-6, 1e-6, x)
    return 2.0 * j1(x) / x


def rear(cpsi):
    """A cone's level from in front (1) round to behind (BACK): a fade over
    REAR_W of cos(psi) just past side-on (a switch stepped: a click a turn)."""
    u = np.clip(-np.asarray(cpsi) / REAR_W, 0.0, 1.0)
    return BACK + (1.0 - BACK) * 0.5 * (1.0 + np.cos(np.pi * u))


def cone_levels(f, theta):
    """[A_1, A_2]: each cone's level toward a path at rotor angle theta (array)."""
    k = 2.0 * np.pi * f / C_SOUND
    out = []
    for (sgn, _), g in zip(CONES, (1.0, CONE2_GAIN)):
        c = sgn * np.cos(theta)
        s = np.sqrt(np.maximum(1.0 - c * c, 0.0))
        out.append(g * piston(k * CONE_RADIUS_M * s) * rear(c))
    return out


def bin_freq(b):
    return TABLE_F0 * 2.0 ** (b / float(TABLE_BPO))


def bin_coord(f, mode=0):
    """The row's place in the table (its lfl): mode * NB + the bin, fractional."""
    u = math.log2(max(float(f), TABLE_F0) / TABLE_F0) * TABLE_BPO
    return float(mode * TABLE_NB) + min(u, TABLE_NB - 1.001)


_TABLE = None


def table():
    """(CA, CK): CA[b, a, i] cone i's level at bin b, angle a (float32, NB x NA
    x 2), normalised by the turn's power-sum mean -- smooth in frequency, where
    the coherent mean combs (+-2 dB above 8 kHz: the two beams' interference,
    which stays in the sound); CK[m, b] = (g, c) for mode m: the rotor path's
    response, and the share that does not turn -- the two at the response's
    level together."""
    global _TABLE
    if _TABLE is not None:
        return _TABLE
    th = np.linspace(0.0, 2.0 * np.pi, TABLE_NA, endpoint=False)
    thf = np.linspace(0.0, 2.0 * np.pi, 1024, endpoint=False)
    CA = np.zeros((TABLE_NB, TABLE_NA, 2), np.float32)
    CK = np.zeros((len(MODES), TABLE_NB, 2), np.float32)
    for b in range(TABLE_NB):
        f = bin_freq(b)
        A = cone_levels(f, th)
        Af = cone_levels(f, thf)
        norm = float(np.mean(np.sqrt(Af[0] ** 2 + Af[1] ** 2)))
        CA[b, :, 0] = A[0] / norm
        CA[b, :, 1] = A[1] / norm
        rg = response_gain(f)
        lk = LEAK * (f / 1000.0) ** LEAK_SLOPE
        # the steady share as the fit has it: lk times the rotor's mean (here
        # 1), and the two together brought to the console's level -- as
        # power, the turning part's phase against the steady one's all round
        # the turn (the steady share on top was +13 dB on C2: it is most of it)
        nt = math.sqrt(1.0 + lk * lk)
        CK[0, b] = (rg / nt, rg * lk / nt)
        CK[1, b] = (rg / nt * CHORUS_SHARE, rg * lk / nt * CHORUS_SHARE + CHORUS_SHARE)
    _TABLE = (CA, CK)
    return _TABLE


def reference(f, theta, mode=0):
    """The kernel's S at rotor-less-azimuth angles theta (array), in numpy:
    the table read as cone_grid reads it (bilinear), the phase worked exactly."""
    CA, CK = table()
    u = bin_coord(f, 0)
    b = int(u)
    w = u - b
    x = np.mod(np.asarray(theta, np.float64), 2.0 * np.pi) * (TABLE_NA / (2.0 * np.pi))
    ia = np.floor(x).astype(int) % TABLE_NA
    ib = (ia + 1) % TABLE_NA
    fa = x - np.floor(x)
    g = CK[mode, b, 0] * (1 - w) + CK[mode, b + 1, 0] * w
    c = CK[mode, b, 1] * (1 - w) + CK[mode, b + 1, 1] * w
    k = 2.0 * np.pi * f / C_SOUND
    ct = np.cos(theta)
    S = np.full(len(x), c, complex)
    for i, (sgn, r) in enumerate(CONES):
        a0 = CA[b, ia, i] * (1 - fa) + CA[b, ib, i] * fa
        a1 = CA[b + 1, ia, i] * (1 - fa) + CA[b + 1, ib, i] * fa
        S += g * (a0 * (1 - w) + a1 * w) * np.exp(1j * k * sgn * r * ct)
    return S


def requests(times_values, fast=True):
    """A Spectra-Tone channel's speed requests from its CC80 timeline."""
    req = [(t, zone(v)) for t, v in times_values]
    if not req or req[0][0] > 0.0:
        req.insert(0, (0.0, FAST_HZ if fast else SLOW_HZ))
    return req


def channel(req, mode='rotor'):
    """The _LESLIE_CH entry for a Spectra-Tone channel (leslie.make_rotors and
    expand read it): one rotor -- the 'drum' slot turns with it, unused."""
    return dict(kind='spectra', mode=mode, horn=req, horn_tau=(SPIN_UP, SPIN_DOWN),
                drum=req, drum_tau=(SPIN_UP, SPIN_DOWN))


def is_spectra(rec):
    return isinstance(rec, dict) and rec.get('kind') == 'spectra'
