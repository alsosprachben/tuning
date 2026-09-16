#!/usr/bin/env python3
"""The vocal tract as a time-varying filter: formants that GLIDE.

Formants applied per note are formants that JUMP, and a jump is the one thing
a tract cannot do -- the tongue and jaw have mass and take 50-150 ms to move.
Worse, the transition is not incidental to the vowel, it IS much of it: a good
deal of what identifies /i/ against /u/ is the direction F2 travels getting
there. Static formants, however exactly placed, give the sound of an organ
playing vowel-shaped chords rather than of anyone speaking.

So the tract moves here instead of in the note. The renderer makes the source
-- the glottal buzz, with its pitch, vibrato, section spread and room -- with
its own formants switched off (TUNING_VOCAL_FLAT=1), and this applies the
filter over the top, interpolating between one syllable's formants and the
next. That is the source-filter model the voice should have had from the
start, and it is why this is a separate pass rather than another parameter.

Done on the STFT: a 2048-point frame every 256 samples is ~6 ms of resolution,
fast enough to follow a real articulator and cheap enough to be free.
"""
import os

import numpy as np

import vocaltube

FRAME = 2048
HOP = 256

# The tube response is rebuilt every TUBE_EVERY frames and interpolated
# between, because walking 44 sections per 6 ms frame is most of the cost of
# the pass and a tongue does not move in 23 ms.
TUBE_EVERY = 4

# A SINGER EVENS OUT THE VOWELS AND A TALKER DOES NOT.
#
# Vowels have an intrinsic intensity: open ones radiate more than close ones,
# so in speech /a/ runs 4-5 dB above /i/ and /u/ without anybody intending it
# (Lehiste and Peterson). A tube reproduces that for free, being the same
# physics -- and overdoes it here, spreading the inventory over 10.9 dB with
# /i/ 8.3 dB under /a/. Singers spend years removing exactly this, adjusting
# breath pressure and vowel shape to hold a line even; it is most of what
# "vowel modification" is for. The three-pole path never had the problem
# because its formant amplitudes were set by hand and so came pre-levelled.
#
# Left in, it reads as a choir that goes quiet on every /i/ and /e/ -- which
# in the Lacrimosa is most of the words.
#
# 1.0 = fully even, 0.0 = whatever the tube gives. Speech wants a low value:
# the unevenness is real, and only singing trains it out.
VOWEL_NORM = float(os.environ.get('TUNING_VOWEL_NORM', '1.0'))

# The source the levelling is weighted by -- measured off a flat render at
# -6.6 dB/octave. Loudness is what reaches the ear, so the filter has to be
# judged against the spectrum it will actually be filtering.
_SRC_TILT = -6.6 / 6.0
_NORM_CACHE = {}


def _even_out(f, g, key):
    """Scale a tract response so every vowel arrives at the same loudness."""
    if not VOWEL_NORM:
        return g
    ref = _NORM_CACHE.get(key)
    if ref is None:
        src = (np.maximum(f, 50.0) / 500.0) ** _SRC_TILT
        band = (f > 80.0) & (f < 9000.0)
        ref = float(((g * src)[band] ** 2).sum())
        _NORM_CACHE[key] = ref
    if ref <= 0.0:
        return g
    return g * (1.0 / np.sqrt(ref)) ** VOWEL_NORM


def _shape(f, formants, floor=0.05, corner=4000.0, order=2.0, tilt=1.0):
    """The tract's response.

    TILT COMPENSATES THE SOURCE. The formant amplitudes in the table are read
    off measured spectral ENVELOPES, which already contain the glottal
    roll-off -- about 11 dB/octave. Applied to a source that still has that
    roll-off they count it twice, and the upper formants never arrive: /i/
    came back with its F2 at 991 Hz instead of 2290, which is not an /i/.
    A resonance is a resonance whatever the source does, so the filter is
    tilted back up before the formants are laid on it.
    """
    g = np.full_like(f, floor)
    for centre, bw, amp in formants:
        d = (f - centre) / max(1.0, bw * 0.5)
        g += amp * ((max(centre, 1.0) / 500.0) ** tilt) / (1.0 + d * d)
    g *= 1.0 / (1.0 + (np.maximum(f, 1.0) / corner) ** order)
    return g


def trajectory(timeline, n, sr, glide=0.070):
    """(frames, 3, 3) of formants over time, interpolated between syllables.

    `timeline` is [(second, formants)]. Between two syllables the formants
    travel from one to the other over `glide` seconds centred on the boundary
    -- the articulator is already moving before the note changes, which is why
    a transition does not line up with a note-on.
    """
    nf = 1 + max(0, (n - FRAME)) // HOP
    t = (np.arange(nf) * HOP + FRAME * 0.5) / sr
    if not timeline:
        return None, t
    times = np.array([x[0] for x in timeline])
    out = np.zeros((nf,) + np.asarray(timeline[0][1], float).shape)
    idx = np.searchsorted(times, t, 'right') - 1
    idx = np.clip(idx, 0, len(timeline) - 1)
    for k in range(nf):
        i = idx[k]
        cur = np.array(timeline[i][1], float)
        j = min(i + 1, len(timeline) - 1)
        nxt = np.array(timeline[j][1], float)
        if j > i:
            b = times[j]
            w = (t[k] - (b - glide * 0.5)) / glide
            w = 0.0 if w <= 0 else (1.0 if w >= 1 else w)
            w = 0.5 - 0.5 * np.cos(np.pi * w)        # ease, do not ramp
        else:
            w = 0.0
        out[k] = cur * (1.0 - w) + nxt * w
    return out, t


def _tube_shape(f, coeffs, tract_cm, tilt, floor, corner=3600.0, order=3.0):
    """The response of the TUBE this syllable is, rather than of three poles.

    The bandwidths and relative formant heights are not supplied here: they
    fall out of the wall losses and the radiation load, which is the point of
    doing it this way. `tilt` remains because the SOURCE is still a rendered
    harmonic series rather than a modelled glottis, so its slope has to be
    reconciled with the filter's.
    """
    g = vocaltube.response(vocaltube.area_from_modes(coeffs), f, tract_cm)
    g = g * (np.maximum(f, 50.0) / 500.0) ** tilt
    # THE SAME HIGH-FREQUENCY ROLL-OFF THE FORMANT PATH USES, and it is not
    # optional. A tube's radiation load is a +6 dB/oct highpass, so left alone
    # the model runs 31 dB hot above 4.5 kHz -- audible as hissing consonants,
    # because the consonant gain was tuned by ear against a filter that had
    # this lowpass in it. What it stands for physically is the glottal return
    # phase: a real source falls 12 dB/oct and steepens further above 3 kHz,
    # where the rendered source here measures only 6.6.
    g = g / (1.0 + (np.maximum(f, 1.0) / corner) ** order)
    src = (np.maximum(f, 50.0) / 500.0) ** _SRC_TILT
    band = (f > 80.0) & (f < 9000.0)
    e = float(((g * src)[band] ** 2).sum())
    if VOWEL_NORM and e > 0.0:
        g = g * (1.0 / np.sqrt(e)) ** VOWEL_NORM
    return g + floor


def apply(x, sr, timeline, glide=0.070, floor=0.05, tube=False,
          tract_cm=vocaltube.TRACT_CM, tilt=-0.15, gain=1.0):
    """Filter `x` (n, ch) by a tract that moves along `timeline`.

    With `tube`, the timeline carries tract SHAPES (mode coefficients) instead
    of formant triples, and what is interpolated between syllables is a
    geometry rather than three independent numbers.
    """
    n = len(x)
    if tube:
        # The tube supplies its own floor: between formants its many poles
        # overlap and fill in to about -16 dB, where the three-pole model digs
        # a 48 dB trench and then has to have a floor added back under it.
        # Real speech has the shallower valley.
        floor = min(floor, 0.005)
    traj, _ = trajectory(timeline, n, sr, glide)
    if traj is None:
        return x
    win = np.hanning(FRAME).astype(np.float32)
    f = np.fft.rfftfreq(FRAME, 1.0 / sr)
    out = np.zeros_like(x, dtype=np.float64)
    norm = np.zeros(n)
    nf = len(traj)
    for k in range(nf):
        s = k * HOP
        if s + FRAME > n: break
        if tube:
            if k % TUBE_EVERY == 0 or k == nf - 1:
                nxt = min(k + TUBE_EVERY, nf - 1)
                g0 = _tube_shape(f, traj[k], tract_cm, tilt, floor)
                g1 = _tube_shape(f, traj[nxt], tract_cm, tilt, floor)
                step, base = max(1, nxt - k), k
            w = (k - base) / step
            g = (g0 ** (1.0 - w)) * (g1 ** w) * gain     # interpolate in dB
        else:
            g = _shape(f, traj[k], floor=floor)
        for c in range(x.shape[1]):
            seg = np.fft.rfft(x[s:s + FRAME, c] * win)
            out[s:s + FRAME, c] += np.fft.irfft(seg * g, FRAME) * win
        norm[s:s + FRAME] += win * win
    norm[norm < 1e-8] = 1.0
    return (out / norm[:, None]).astype(np.float32)
