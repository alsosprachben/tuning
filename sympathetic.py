#!/usr/bin/env python3
"""The notes nobody hit.

Measured on a steelpan against a CC0 recording, across 40 isolated strikes: a
median 23% of the peak energy is NOT a harmonic of the note struck. It turns up
at 0.75, 0.80, 1.33 and 1.50 of the fundamental -- fourths, thirds and fifths,
which are musical INTERVALS and not modes, because they are the neighbouring
note areas answering through the shared steel. A quarter of what you hear on a
pan is notes nobody hit.

TWO MECHANISMS, AND THE PAN USES THE ONE I DID NOT EXPECT. `tonelib`'s
sympathetic_partials describes both. COINCIDENCE is resonance -- a responder
answers only where one of the driver's partials lands inside one of its own
modes -- and it is right for a sitar's sympathetic strings and a piano's
undamped ones, which are separate oscillators loosely coupled. CONTACT is a
mechanical kick through shared material: an impulse is broadband, so the
responder rings at its own modes whatever interval it sits at.

The measurement settles it, and not gently. A steelpan mode at 261 Hz decaying
at 6.2 dB/s has a half-power bandwidth of 0.11 Hz -- a Q above two thousand --
and an equal-tempered fifth is two cents narrow of a just one, which at the 3:2
coincidence is twenty bandwidths away. Computed on this voice, coincidence
gives the octave 0.0071 and the fifth 0.0000024: essentially OCTAVES ONLY. The
recording shows a broad spread with the fifth at 20% and a major second at 27%.
Coincidence cannot produce that, and a pan is one continuous sheet of steel
rather than a rack of separate oscillators, so it should not be asked to.

WHY THIS IS A PASS AND NOT PART OF THE NOTE LOOP. A responder rings with its
OWN spectrum, and on a pan every note area is the same class -- so a responder
is the driver's partial set transposed, which is a row copy with a frequency
scale. Emitting it inside the note loop would mean rebuilding twenty per-partial
quantities that the loop has already computed. Here it is one pass over the
finished table, the same shape as cabinet.py and tubeamp.py.

Runs BEFORE the amplifier, because a sympathetic note is part of what the
instrument produces and therefore part of what an amplifier would be given.
"""
import numpy as np

import tonelib as T


def responders(props, sr=None):
    """[(semitone offset, drive)] for one struck note, strongest first.

    The drive is a scalar per responder rather than per mode, which is exact
    for CONTACT -- where the whole note area is kicked at once -- and an
    approximation for coincidence, where strictly only the coinciding modes
    answer. Coincidence at a steelpan's Q answers essentially nowhere, so the
    approximation is not load-bearing for the one voice that uses this.
    """
    g = getattr(props, 'sympathetic_gain', 0.0)
    if g <= 0.0:
        return []
    span = int(getattr(props, 'sympathetic_span', 24))
    floor = float(getattr(props, 'sympathetic_floor', 0.02))
    top = int(getattr(props, 'sympathetic_max', 6))
    mode = getattr(props, 'sympathetic_mode', 'coincidence')
    fall = float(getattr(props, 'sympathetic_falloff', 0.0))
    out = []
    strings = getattr(props, 'sympathetic_strings', ())
    if strings:
        # A FIXED SET OF TUNED STRINGS, which is what a sitar has. They do not
        # move with the melody, so the offset from the driver changes note by
        # note -- play the pitch a string is tuned to and that string answers
        # loudly, play between them and little happens. That is what a sitar
        # sounds like, and it is coincidence doing it: an exact unison is
        # exactly in the resonance, and two cents away is already outside it.
        tonic = int(getattr(props, 'sympathetic_tonic', 60))
        f0 = props.frequency_x * (2.0 ** props.octave_position)
        drv = int(round(69 + 12 * np.log2(max(f0, 1e-9) / 440.0)))
        for off in strings:
            s = (tonic + int(off)) - drv
            if s == 0:
                continue                 # the string the note is played on
            d = _coupling(props, _at(props, f0 * 2.0 ** (s / 12.0)), g)
            if d >= floor:
                out.append((s, d))
        out.sort(key=lambda sd: -sd[1])
        return out[:top]
    if mode == 'contact':
        # The kick is broadband, so every responder gets the same spectrum and
        # only its DISTANCE matters. Semitone distance stands in for distance
        # across the metal; see tonelib.sympathetic_falloff for why that is a
        # proxy and not the truth.
        for s in range(-span, span + 1):
            if s == 0:
                continue
            # DISTANCE ROUND THE CYCLE OF FIFTHS, not in semitones -- that is
            # the order the note areas are hammered into a pan, so the area
            # next to C is G and not C#. tonelib.body_distance owns the rule;
            # this used to have its own semitone copy of it, which put the
            # strongest responders a semitone away and made a chromatic mush
            # that the recording flatly contradicts.
            d = g * 10.0 ** (-fall * T.body_distance(s, props) / 20.0)
            if d >= floor:
                out.append((s, d))
    else:
        f0 = props.frequency_x * (2.0 ** props.octave_position)
        for s in range(-span, span + 1):
            if s == 0:
                continue
            d = _coupling(props, _at(props, f0 * 2.0 ** (s / 12.0)), g)
            if d >= floor:
                out.append((s, d))
    out.sort(key=lambda sd: -sd[1])
    return out[:top]


_VOICE_CACHE = {}


def _coupling(driver, responder, gain):
    """How loudly `responder` rings, as a FRACTION of its own natural level.

    The same units the contact path returns, which matters because `expand`
    scales a row copy by whatever comes back. sympathetic_partials gives
    absolute amplitudes -- the responder's own spectrum, already carrying the
    instrument's gain -- so dividing by that spectrum's own total is what turns
    it into a coupling fraction. Without it the two paths meant different
    things and every coincidence responder fell under the floor.
    """
    p = T.sympathetic_partials(driver, responder, gain=gain)
    if not p:
        return 0.0
    nat = sum(a * a for _, a in T._voice_partials(responder))
    if nat <= 0.0:
        return 0.0
    return float(np.sqrt(sum(a * a for _, a in p) / nat))


def _at(props, freq):
    """The same voice at another pitch, built once per (class, frequency)."""
    key = (type(props), round(freq, 4))
    v = _VOICE_CACHE.get(key)
    if v is None:
        v = type(props)(freq, 0.0, 1.0, 1.0)
        _VOICE_CACHE[key] = v
    return v


def expand(A, channels, sr, cols=None):
    """Emit every channel's sympathetic notes, in place on the table.

    A struck note is one group of rows sharing an onset; each responder is that
    group transposed and scaled. Returns how many partials were added.
    """
    if not channels or not len(A.get('nf', ())):
        return 0
    mch = np.asarray(A['mch'])
    non = np.asarray(A['non'], float)
    om = np.asarray(A['om'], float)
    nf = np.asarray(A['nf'], float)
    p0 = np.asarray(A['p0'], float)
    p0R = np.asarray(A['p0R'], float)
    aL = np.asarray(A['aL'], float)
    aR = np.asarray(A['aR'], float)
    aM = np.asarray(A['aM'], float)
    keys = list(cols or A.keys())
    extra = {k: [] for k in keys}
    made = 0
    for ch, props in channels.items():
        resp = responders(props, sr)
        if not resp:
            continue
        rows = np.flatnonzero(mch == ch)
        if not len(rows):
            continue
        # One struck note is one onset. Rounded, because a section's entry
        # scatter moves `non` by a few samples per partial and those belong to
        # the same strike.
        grp = {}
        for i in rows:
            grp.setdefault(int(round(non[i] / 64.0)), []).append(i)
        for _, idx in grp.items():
            ix = np.asarray(idx)
            for semis, drive in resp:
                ratio = 2.0 ** (semis / 12.0)
                if (nf[ix] * ratio > sr * 0.5).all():
                    continue
                keep = ix[nf[ix] * ratio < sr * 0.5]
                if not len(keep):
                    continue
                for i in keep:
                    for k in keys:
                        extra[k].append(A[k][int(i)])
                    # Frequency scales; the phase anchor scales with it, since
                    # p0 = -om*(non + delay) and om has just been multiplied.
                    extra['om'][-1] = om[i] * ratio
                    extra['nf'][-1] = nf[i] * ratio
                    extra['p0'][-1] = p0[i] * ratio
                    extra['p0R'][-1] = p0R[i] * ratio
                    extra['aL'][-1] = aL[i] * drive
                    extra['aR'][-1] = aR[i] * drive
                    extra['aM'][-1] = aM[i] * drive
                    made += 1
    for k in keys:
        A[k].extend(extra[k])
    return made
