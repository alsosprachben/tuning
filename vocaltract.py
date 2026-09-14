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
import numpy as np

FRAME = 2048
HOP = 256


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
    out = np.zeros((nf, len(timeline[0][1]), 3))
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


def apply(x, sr, timeline, glide=0.070, floor=0.05):
    """Filter `x` (n, ch) by a tract that moves along `timeline`."""
    n = len(x)
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
        g = _shape(f, traj[k], floor=floor)
        for c in range(x.shape[1]):
            seg = np.fft.rfft(x[s:s + FRAME, c] * win)
            out[s:s + FRAME, c] += np.fft.irfft(seg * g, FRAME) * win
        norm[s:s + FRAME] += win * win
    norm[norm < 1e-8] = 1.0
    return (out / norm[:, None]).astype(np.float32)
