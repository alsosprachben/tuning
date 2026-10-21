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

import numpy as np

# A 122-style cabinet.
# ...MEASURED against hammondman's "Rok organ" on the fast rotor, partial by
# partial over 630 Hz-4 kHz (each partial's pitch wobble and level swing): the
# 0.17 m throw and the narrow lobe warbled 1.5-2x the take's pitch above 1 kHz
# and swung up to twice its depth at 2.5-4 kHz (Ben: the original's shimmer
# we were missing, and ours too much up top). A 0.11 m throw, the lobe's floor
# 0.30 and its narrowing 4 (HORN_FLOOR, HORN_SHARPNESS): 6.9 -> 4.7 dB rms over
# the bands. What is left is the take's wobble FALLING with pitch (16.6 cents
# at 630-1000 Hz to 6.9 at 2.5-4 kHz), which a Doppler -- a fixed fraction of
# the pitch -- cannot do: the room's diffuse field averaging the treble, which
# this renderer's discrete images do only in part (over 4 kHz they beat, 25 dB
# swings, whatever the lobe)
HORN_RADIUS = 0.11          # m, the horn mouth's throw (as it reaches the listener)
DRUM_RADIUS = 0.10          # m, the bass rotor's port
CROSSOVER_HZ = 800.0        # horn above, drum below
SLOW_HZ = 0.80              # chorale
FAST_HZ = 6.60              # tremolo
# The two rotors are not synchronised and typically turn opposite ways; a fixed
# ratio here would lock them into a pattern the ear finds very quickly.
DRUM_RATIO = -0.92
C_SOUND = 343.0

# OFFLINE the level swing has to be sidebands: blockrender renders a whole file
# in one stateless call, so there is nowhere to put a gain that changes with
# time. LIVE there is a callback every 2.7 ms, which is 55 updates per turn of
# a 6.6 Hz rotor -- so the swing belongs there, as a gain, the way a real-time
# engine would do it. Then the rotor is a continuously evaluated ANGLE rather
# than something baked into a note, and it can change under a held chord.
SIDEBANDS = True

# ...AND NOW OFFLINE IS A GAIN TOO. The kernel takes each rotor's angle on the
# Moog's grid (128 samples, live's callback) and each rotor row's lobe, and
# swings the row's level as live does (synthkernel.c leslie_grid). The
# sidebands below had two faults: each note kept the rotor speed it started
# under, so a chord held through the half-moon switch did not follow it; and
# to keep their number down they were spent by level against the whole file's
# loudest row -- which a streamed render cannot know, so every file with a
# Leslie was emitted twice (Tokei: six minutes of scan). False keeps the
# sidebands, for an A/B.
KERNEL_LOBE = True

# How many harmonics of the lobe the offline path buys. Three carries the chop
# -- the second and third are what separate a beam from a cosine -- and each
# costs a sideband pair on every partial.
HARMONICS = 3
# The bass rotor is a scoop with a fixed driver, not a horn being swung, so its
# pattern is blunt: measured live, its swing has a second harmonic of 0.11
# against the horn's 0.50. Its lobe is drum_beam's: half the horn's sharpness,
# DRUM_DEPTH of its depth -- and directional from DRUM_REF_HZ, not the horn's
# 700: the scoop is wide, so it beams far lower down than a horn mouth does.
#
# ...MEASURED (hammondman's "Rok organ", freesound pack 15120, CC0; sources.md
# "Organs and free reeds"; one mic): on the fast rotor the fundamentals under
# the crossover swing as deep as the horn's -- 3-5 dB at 98-175 Hz, 5-15 at
# 220-700 -- where this lobe, the horn's law halved, swung them 0.3-2 dB. The
# horn's own (8.6 dB at 1 kHz) already matched. Directional from 160 Hz at
# 0.9 of the horn's depth puts the drum's swing at the take's median within
# 0.1 dB below 175 Hz and 1.7 above (the rates were already the take's: the
# horn 6.6 Hz, the drum 6.1)
DRUM_DEPTH = 0.9
DRUM_REF_HZ = 160.0

# A partial this far below the loudest keeps the whole lobe; below the second
# threshold it keeps only the first harmonic, and below that the rotor still
# turns it but stops describing the shape of the sweep.
#
# Set against where the energy actually is, not guessed. Measured on a Rock
# Organ passage, the partials above 1% of the loudest are 8.5% of the table and
# carry 100.0% of the energy; above 3% they are 5.9% and carry 99.9%. So the
# full lobe goes on everything audible and the tail keeps only its first
# harmonic -- which matters because the amplifier's distortion products are all
# 25 dB down, and giving each of them a three-harmonic lobe had the rotor
# multiplying the amplifier's output by seven.
FULL_LOBE = 0.01
SOME_LOBE = 0.001


# THE CABINET'S OWN RESPONSE, by absolute frequency, dB: what the rotors do
# not -- the bass rotor's drum hollowing the mids under the crossover, the
# horn's presence peak, its fall above 4 kHz. MEASURED, from the residual of
# the drawbar derivation (examples/drawbar_fit.py): with each take's drawbar
# setting solved, what was left lay on ONE curve by absolute frequency in both
# of hammondman's packs, slow and fast (sources.md "Organs and free reeds") --
# the dip at 400-640 Hz (-5 to -11) and the peak at 1.3-1.6 kHz (+5 to +9)
# in each -- so the cabinet, not either room. The two averaged where both
# reach; over 2 kHz the fast pack's alone (the slow pack's notes stop there);
# the slow pack's +10-13 at 160-200 Hz, in it alone, left out as its room.
# Held flat outside the table's ends.
CABINET_DB = ((253.0, 0.0), (319.0, -1.0), (403.0, -8.0), (507.0, -8.0), (639.0, -6.0),
              (806.0, -3.0), (1015.0, 1.0), (1279.0, 5.5), (1612.0, 7.5), (2031.0, 3.0),
              (2559.0, 2.0), (3225.0, 2.0), (4063.0, -8.0), (5119.0, -4.0), (6450.0, -14.0))


# THE CROSSOVER'S SLOPES: power-complementary, 2nd order -- 12 dB an octave
# each side of CROSSOVER_HZ -- so a partial near it goes out by both rotors.
# A copy is made for the other rotor's share when it is within XOVER_FLOOR
# (-20 dB: about 255 Hz to 2.5 kHz); under that the pitch's rotor takes all.
XOVER_FLOOR = 0.1
XOVER_K = 10                 # meta's lobe-harmonic code for the other rotor's copy


def crossover_weights(f):
    """(horn, drum) amplitude shares of a partial at f: their squares sum to
    one -- the copies swing and Doppler apart, so they add as power."""
    x4 = (max(f, 1e-9) / CROSSOVER_HZ) ** 4
    return math.sqrt(x4 / (1.0 + x4)), math.sqrt(1.0 / (1.0 + x4))


def cabinet_gain(freq_hz):
    """CABINET_DB at freq_hz, as a linear gain (log-frequency interpolation)."""
    pts = CABINET_DB
    if freq_hz <= pts[0][0]:
        db = pts[0][1]
    elif freq_hz >= pts[-1][0]:
        db = pts[-1][1]
    else:
        for (f0, d0), (f1, d1) in zip(pts, pts[1:]):
            if freq_hz <= f1:
                db = d0 + (d1 - d0) * math.log(freq_hz / f0) / math.log(f1 / f0)
                break
    return 10.0 ** (db / 20.0)


def azimuth(x, z):
    """Where a receiver sits, as seen from the cabinet."""
    return math.atan2(x, max(z, 1e-6))


def doppler_depth(radius, rate_hz):
    """Peak fractional frequency deviation: the arm's tip speed over c."""
    return 2.0 * math.pi * radius * rate_hz / C_SOUND


HORN_FLOOR = 0.30           # the horn lobe's floor at the top (beam): how deep its swing goes
HORN_SHARPNESS = 4.0        # ...and how far it narrows toward the top -- both as HORN_RADIUS


def beam(freq_hz, floor=None, ref_hz=700.0, sharpness=None):
    """The horn's pattern: (floor, sharpness) of a lobe that narrows with pitch.

    A horn is directional in proportion to its mouth against the wavelength, so
    it is nearly omnidirectional in the bass and a narrow beam at the top. Both
    the DEPTH of the level swing and its SHAPE follow from that, and the shape
    is the part a cosine cannot give.

    Sweeping a narrow lobe past a listener is a pulse, not a sine: measured on
    a plausible horn pattern the swing carries a second harmonic at 0.40 of the
    first and a third at 0.07, and sits above half its peak for a third of a
    turn rather than half. That is the chop of a fast Leslie, and modelling the
    level swing as 1 + m*cos(t) -- which is exactly the first Fourier term and
    nothing else -- leaves it out. A tremolo pedal is a sine; a Leslie is not.
    """
    if floor is None:
        floor = HORN_FLOOR
    if sharpness is None:
        sharpness = HORN_SHARPNESS
    x = (freq_hz / ref_hz) ** 2
    sharp = 0.6 + sharpness * x / (1.0 + x)  # omni in the bass, a beam on top
    fl = 1.0 - (1.0 - floor) * x / (1.0 + x)  # ...and a deeper swing with it
    return fl, sharp


def drum_beam(freq_hz):
    """The BASS ROTOR's lobe, (floor, sharpness) as beam's: a scoop round a
    fixed driver -- blunter (half the sharpness, never under 0.5), DRUM_DEPTH
    of the depth, directional from DRUM_REF_HZ. One law for both renderers
    (offline blunted the swing's harmonics, live the lobe: they differed)."""
    fl, sharp = beam(freq_hz, floor=0.06, ref_hz=DRUM_REF_HZ, sharpness=9.0)   # as fitted
    return 1.0 - (1.0 - fl) * DRUM_DEPTH, max(sharp * 0.5, 0.5)


def beam_gain(theta, fl, sharp):
    """The lobe itself, mean-normalised so it is a colour and not a level."""
    import numpy as _np
    # ((1+cos)/2)^p, NOT cos(t/2)^p: the half-angle form has period 4*pi, so
    # the lobe fired once every TWO revolutions and the whole swing came out at
    # half the rotor rate -- 3.33 Hz measured against a rotor turning at 6.60.
    # This one is period 2*pi by construction and never negative, so it needs
    # no clip either.
    c = (0.5 * (1.0 + _np.cos(_np.asarray(theta)))) ** (0.5 * sharp)
    return fl + (1.0 - fl) * c


def beam_harmonics(freq_hz, n=4, points=512, horn=True):
    """[c1, c2, ...] of the lobe, as a cosine series about its own mean.

    The offline path has no gain that changes with time -- the render is one
    stateless call -- so the swing has to be partials, and each harmonic of the
    lobe is another sideband pair. A cosine needed one pair; a beam needs
    three to be worth the name.
    """
    import numpy as _np
    fl, sharp = beam(freq_hz) if horn else drum_beam(freq_hz)
    # from 0, so index 0 IS the lobe's peak: sampling from -pi puts the
    # peak in the middle of the array and every odd coefficient comes out
    # negated, which reconstructs a lobe pointing the wrong way.
    th = _np.linspace(0.0, 2.0 * _np.pi, points, endpoint=False)
    g = beam_gain(th, fl, sharp)
    g = g / g.mean()
    sp = _np.fft.rfft(g) / points
    return [2.0 * float(_np.real(sp[k])) for k in range(1, n + 1)]


def beam_depth(freq_hz):
    """The first harmonic alone -- what the old cosine model used."""
    return abs(beam_harmonics(freq_hz, 1)[0])


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


def make_rotors(channels):
    """Each Leslie channel's horn and drum rotors, from its speed history --
    or, for an insertion effect's Rotary (gsefx.rotary_setup), a dict giving
    each rotor its own speeds, spin times and levels."""
    out = {}
    for ch, req in channels.items():
        if isinstance(req, dict):
            out[ch] = (Rotor(True, req['horn'], taus=req['horn_tau']),
                       Rotor(False, req['drum'], taus=req['drum_tau'], ratio=-1.0))
        else:
            out[ch] = (Rotor(True, req), Rotor(False, req))
    return out


def expand(A, channels, sr, cols, meta=None, loudest=None, rotors=None, flips=None, place=None):
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
    kernel integrates analytically on an absolute clock. The level swing is
    the kernel's (KERNEL_LOBE): each rotor row gets its rotor and lobe
    (lobe_columns), and synth_voice_lobe swings it by the rotor's angle
    (angle_table) -- or, with KERNEL_LOBE off, sidebands, since AM of a
    sinusoid is three partials.

    THE DOPPLER'S RATE IS FROZEN AT EACH NOTE'S ONSET (the level's is not: it
    reads the rotor's angle as it turns), and that is the one place this is
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
    # the streaming renderer passes the whole file's `loudest` (from a first,
    # scanning run) and its rotors (built once), and a `meta` list that
    # records (source row, lobe harmonic, sign index) per row appended
    if rotors is None:
        rotors = make_rotors(channels)
    extra = {k: [] for k in cols}
    made = 0
    if loudest is None and not KERNEL_LOBE:
        loudest = max(float(np.max(np.abs(A['aM']))), 1e-12) if n else 1.0
    # the kernel's lobe: (row, rotor, azimuth, frequency, on the horn?) for
    # every row put on a rotor -- its position in the table as it ends
    lobe = [] if (SIDEBANDS and KERNEL_LOBE) else None
    rank = {c: k for k, c in enumerate(channels)}

    def rotate(r, horn, i, kbase):
        """Put row r (a dict of its columns) on a rotor: its Doppler in the
        vibrato columns, and the level swing's sideband rows appended to
        extra -- each recorded in meta as (source row, lobe harmonic + kbase,
        sign). Returns how many sidebands it made."""
        f = r['nf']
        rotor = rotors[int(r['mch'])][0 if horn else 1]
        t_on = r['non'] / float(sr)
        rate, angle = rotor.at(t_on)
        if not horn:
            rate *= abs(rotor.ratio)
            angle *= rotor.ratio         # and it turns the other way
        radius = HORN_RADIUS if horn else DRUM_RADIUS
        fm = doppler_depth(radius, rate)
        # The kernel's modulator is sin(2*pi*rate*t + vp) on an absolute clock,
        # and what is wanted is sin(angle(t) - azimuth). Equate them at t_on.
        ph = angle - 2.0 * math.pi * rate * t_on - r['az']
        r['vd'] = fm
        r['vr'] = rate
        r['vp'] = math.atan2(math.sin(ph), math.cos(ph))
        # A STOPPED ROTOR HAS NO SIDEBANDS. At rate 0 they would land exactly
        # on the carrier and simply add level -- a brake that makes the organ
        # louder, which is not what a brake does.
        if SIDEBANDS and KERNEL_LOBE:       # the level is the kernel's (lobe_columns)
            if rate < 0.05:
                r['vd'] = 0.0
            return 0
        if not SIDEBANDS or rate < 0.05:
            if rate < 0.05:
                r['vd'] = 0.0
            return 0
        # ONE SIDEBAND PAIR PER HARMONIC OF THE LOBE. A cosine needed one pair
        # and made a tremolo; a beam swept past a listener is a pulse, and its
        # second and third harmonics are the chop. Offline there is no gain
        # that changes with time, so each harmonic has to be bought as
        # partials -- which is why this truncates where the live path, where
        # the lobe is simply a gain, does not.
        # HOW MUCH LOBE A PARTIAL IS WORTH. The chop lives in the lobe's 2nd
        # and 3rd harmonics, and those are worth buying on the partials you can
        # hear. On one 25 dB down -- which is what every distortion product
        # from the amplifier is -- the 3rd harmonic of its level swing is 50 dB
        # down and costs a partial pair to say so. Spending the full lobe on
        # everything made the rotor multiply the amplifier's output by seven.
        rel = r['aM'] / loudest
        want = HARMONICS if rel > FULL_LOBE else (1 if rel > SOME_LOBE else 0)
        if want == 0:
            return 0
        cs = beam_harmonics(f, want, horn=horn)
        dw = 2.0 * math.pi * rate / sr
        got = 0
        for k, ck in enumerate(cs, 1):
            if abs(ck) < 1e-3:
                continue
            for si, sign in enumerate((1.0, -1.0)):
                if meta is not None:
                    meta.append((i, k + kbase, si))
                for col in cols:
                    extra[col].append(r[col])
                extra['om'][-1] = r['om'] + sign * k * dw
                extra['aL'][-1] = r['aL'] * ck * 0.5
                extra['aR'][-1] = r['aR'] * ck * 0.5
                extra['aM'][-1] = r['aM'] * ck * 0.5
                extra['p0'][-1] = r['p0'] + sign * k * r['vp']
                extra['p0R'][-1] = r['p0R'] + sign * k * r['vp']
                got += 1
        return got

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
        # the cabinet's own colour, on every row it radiates -- applied here,
        # before the sidebands copy the row, so they carry it; live's templates
        # pass through here too (sidebands off), so both renderers have it once
        _cg = cabinet_gain(f)
        # ...AND THE CROSSOVER IS A SLOPE, NOT A LINE (crossover_weights): near
        # it a partial leaves by BOTH rotors -- two Dopplers, two swings, beating
        # against each other, the shimmer of a real cabinet (Ben: "an element in
        # the original that we are missing"). The rotor its pitch picks keeps
        # the row; the other's share, when within XOVER_FLOOR, is a copy on the
        # other rotor (recorded in flips for live, in meta as k + XOVER_K)
        wh, wd = crossover_weights(f)
        # an insertion Rotary's own balance of the rotors (its Hi/Low Level)
        lv = channels[ch].get('levels') if isinstance(channels[ch], dict) else None
        if lv is not None:
            wh, wd = wh * lv[1], wd * lv[0]
        wp, ws = (wh, wd) if horn else (wd, wh)
        if ws < XOVER_FLOOR:
            wp, ws = 1.0, 0.0
        r = {col: A[col][i] for col in cols}
        twin = None
        if ws > 0.0:
            twin = dict(r)
            for col in ('aL', 'aR', 'aM'):
                twin[col] = r[col] * _cg * ws
        for col in ('aL', 'aR', 'aM'):
            r[col] = r[col] * _cg * wp
            A[col][i] = r[col]
        # A RECORDED ROTARY (an insertion Rotary's Separate, gsefx): the direct
        # sound as two microphones round the cabinet hear it, each sent to its
        # speaker -- mic A to the left, mic B to the right, Separate apart --
        # so each has its own angle to the rotors: its own swing and its own
        # Doppler. The room's images still hear the cabinet itself.
        sep = channels[ch].get('separate') if isinstance(channels[ch], dict) else None
        mic = sep is not None and place is not None and float(A['dr'][i]) > 0.5
        rB = twinB = None
        if mic:
            az0 = float(r['az'])
            rB = _to_mic(dict(r), 'r', az0 + 0.5 * sep, place, f)
            _to_mic(r, 'l', az0 - 0.5 * sep, place, f)
            for col in ('aL', 'aR', 'aM', 'p0', 'p0R', 'delL', 'delR', 'az'):
                A[col][i] = r[col]
            if twin is not None:
                twinB = _to_mic(dict(twin), 'r', az0 + 0.5 * sep, place, f)
                _to_mic(twin, 'l', az0 - 0.5 * sep, place, f)
        made += rotate(r, horn, i, 0)
        if lobe is not None:
            lobe.append((i, 2 * rank[ch] + (0 if horn else 1), r['az'], f, horn))
        A['vd'][i], A['vr'][i], A['vp'][i] = r['vd'], r['vr'], r['vp']
        if twin is not None:
            # the copy on the other rotor: first its carrier, then its sidebands
            if flips is not None:
                flips.append(n + len(extra['om']))
            if meta is not None:
                meta.append((i, XOVER_K, 2))
            pos = len(extra['om'])
            for col in cols:
                extra[col].append(twin[col])
            made += rotate(twin, not horn, i, XOVER_K)
            if lobe is not None:
                lobe.append((n + pos, 2 * rank[ch] + (1 if horn else 0), twin['az'], f, not horn))
            for col in ('vd', 'vr', 'vp'):
                extra[col][pos] = twin[col]
            made += 1
        # ...and mic B's: the row's, then its twin's, after them
        for vb, hb, code, rot in ((rB, horn, MIC_K, 0 if horn else 1),
                                  (twinB, not horn, MIC_K + XOVER_K, 1 if horn else 0)):
            if vb is None:
                continue
            if meta is not None:
                meta.append((i, code, 3))
            pos = len(extra['om'])
            for col in cols:
                extra[col].append(vb[col])
            made += rotate(vb, hb, i, code)
            if lobe is not None:
                lobe.append((n + pos, 2 * rank[ch] + rot, vb['az'], f, hb))
            for col in ('vd', 'vr', 'vp'):
                extra[col][pos] = vb[col]
            made += 1
    for k in cols:
        A[k].extend(extra[k])
    if lobe is not None:
        A.update(lobe_columns(lobe, n + len(extra['om'])))
    return made


MIC_K = 20                   # meta's code for mic B's copy (and + XOVER_K for its twin's)
MIC_SHARE = 0.5 ** 0.5       # each mic's share: the pair's power the direct sound's


def _to_mic(v, side, az, place, f):
    """Row v (a dict) as one microphone of a recorded Rotary hears it: at
    azimuth az to the rotors, and arriving from its speaker (place: the GS
    effects' outputs) -- its ear gains and delays the speaker's, its phase the
    line's, as gsdelay's copies are. Returns v, changed in place."""
    gl, gr, dl, dr = place(side, f)
    om, non = float(v['om']), float(v['non'])
    m = abs(float(v['aM'])) * MIC_SHARE
    v['p0'] = -om * (non + dl) + (float(v['p0']) + om * (non + float(v['delL'])))
    v['p0R'] = -om * (non + dr) + (float(v['p0R']) + om * (non + float(v['delR'])))
    v['delL'], v['delR'] = dl, dr
    v['aL'], v['aR'] = m * gl, m * gr
    v['aM'] = float(v['aM']) * MIC_SHARE
    v['az'] = az
    return v


# A row on no rotor: rotor -1, and a lobe that is 1 everywhere
LOBE_COLS = (('lsr', 'i4', -1), ('lph', 'f4', 0.0), ('lfl', 'f4', 1.0), ('lsh', 'f4', 0.0),
             ('lnm', 'f4', 1.0))


def lobe_params(nf, horn):
    """(floor, half the sharpness, one over the mean) of the lobe for partials
    at nf, each on the horn or the drum -- the kernel's form of beam_gain
    (synthkernel.c leslie_grid), the mean as live takes it (Live.leslie_params:
    256 points), so the two renderers swing alike."""
    a = np.asarray(nf, np.float64)
    fl = np.empty(len(a), np.float32)
    sh = np.empty(len(a), np.float32)
    memo = {}
    for j, (f, h) in enumerate(zip(a.tolist(), np.asarray(horn, bool).tolist())):
        k = (f, h)
        if k not in memo:
            memo[k] = beam(f) if h else drum_beam(f)
        fl[j], sh[j] = memo[k]
    th = np.linspace(0.0, 2.0 * np.pi, 256, endpoint=False)
    cc = 0.5 * (1.0 + np.cos(th))
    nrm = np.empty(len(a), np.float32)
    for i0 in range(0, len(a), 4096):
        f_, s_ = fl[i0:i0 + 4096, None], sh[i0:i0 + 4096, None]
        nrm[i0:i0 + 4096] = (f_ + (1.0 - f_) * cc[None, :] ** (0.5 * s_)).mean(axis=1)
    return fl, (0.5 * sh).astype(np.float32), (1.0 / nrm).astype(np.float32)


def lobe_columns(lobe, n):
    """The table's LOBE_COLS for n rows, from expand's (row, rotor, azimuth,
    frequency, horn?) records; every other row on no rotor."""
    out = {k: np.full(n, v, dt) for k, dt, v in LOBE_COLS}
    if lobe:
        pos = np.array([x[0] for x in lobe], np.int64)
        fl, sh, nm = lobe_params([x[3] for x in lobe], [x[4] for x in lobe])
        out['lsr'][pos] = [x[1] for x in lobe]
        out['lph'][pos] = [x[2] for x in lobe]
        out['lfl'][pos], out['lsh'][pos], out['lnm'][pos] = fl, sh, nm
    return out


def rotor_grid(blk):
    """The samples between the lobe's grid points: the kernel's (synthkernel.c,
    MOOG_GRID where the block is a multiple of it)."""
    return 128 if (blk % 128 == 0 and blk // 128 <= 64) else blk


def angle_table(channels, rotors, n_samples, sr, blk):
    """Each rotor's angle at every grid point, [2 per channel (the horn, then
    the drum -- which turns the other way, as rotate has it), points], float32,
    each wrapped to a turn: the kernel's LANG. The rows are channels' order,
    which is expand's rotor index."""
    g = rotor_grid(blk)
    lgn = n_samples // g + 2
    t = np.arange(lgn, dtype=np.float64) * (g / float(sr))
    out = np.empty((2 * len(channels), lgn), np.float32)
    for k, ch in enumerate(channels):
        horn, drum = rotors[ch]
        out[2 * k] = np.mod(horn.angles(t), 2.0 * math.pi)
        out[2 * k + 1] = np.mod(drum.ratio * drum.angles(t), 2.0 * math.pi)
    return out



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

    def __init__(self, horn, requests, step=0.01, length=0.0, taus=None, ratio=None):
        self.up = HORN_SPIN_UP if horn else DRUM_SPIN_UP
        self.down = HORN_SPIN_DOWN if horn else DRUM_SPIN_DOWN
        if taus is not None:                 # an insertion Rotary's own (gsefx)
            self.up, self.down = taus
        # the drum's speed against the requests' (DRUM_RATIO, and the other
        # way round); a Rotary's drum is asked its own speed, so only turns
        self.ratio = 1.0 if horn else (DRUM_RATIO if ratio is None else ratio)
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

    def angles(self, t):
        """The angle at each of the times t (an array): at's, and past the
        schedule's end turning on at its last rate (at holds the last angle
        there; a note's Doppler, from at, keeps the last rate)."""
        t = np.asarray(t, np.float64)
        k = np.arange(len(self.angle), dtype=np.float64) * self.step
        a = np.interp(t, k, np.asarray(self.angle))
        past = t > k[-1]
        a[past] = self.angle[-1] + 2.0 * math.pi * self.rate[-1] * (t[past] - k[-1])
        return a

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
