#!/usr/bin/env python3
"""Fit a voice's parameters to a directory of single-note recordings.

Every calibration in tonelib.py was done with a throwaway script, which is why
`sources.md` can say what was measured but never how to measure it again -- and
why HarpsiBase rang twice too long for as long as it existed without anyone
noticing. This is that script, kept.

It implements the method sources.md already describes: Schroeder backward
integration for decay, autocorrelation with parabolic interpolation for f0 (a
spectral peak locks onto h2 or h3), and a noise floor taken from the tail rather
than from the analysis window.

    voicefit.py decay   DIR   -- decay_db, harmonic_decay_db, decay_register_slope
    voicefit.py inharm  DIR   -- inharmonicity_coefficient
    voicefit.py comb    DIR   -- strike_point
    voicefit.py ratio   DIR DIR2  -- decay ratio between two stops (room-free)

DIR holds one wav per note, with the note name in the filename (C4, A#3, ...).
Nothing here assumes a particular library's layout beyond that.

WHAT THIS CANNOT DO, and no amount of arithmetic will fix: these recordings are
not anechoic and have one microphone position, so the room cannot be subtracted.
What makes anything separable is that ROOM DECAY IS COMMON ACROSS NOTES IN A BAND
AND STRING DECAY IS NOT -- so `decay` reports its per-note spread and you must
look at it. A set whose decay is the same at every pitch is telling you about a
room. `ratio` is the exception and the only room-free decay here: two stops of
one instrument in one room divide the room out.
"""
import glob
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from roomtail import read_wav

NOTE = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6,
        'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
_NOTE_RE = re.compile(r'(?:^|[_\-. ])([A-G]#?)(-?\d)(?:[_\-. ]|$)')
REF_HZ = 415.0          # tonelib's frequency_x: the register slope hangs off it


def note_of(path):
    """MIDI number from a note name in the filename, or None."""
    m = _NOTE_RE.search(os.path.basename(path))
    if not m:
        return None
    return (int(m.group(2)) + 1) * 12 + NOTE[m.group(1)]


def mono(path):
    a, sr = read_wav(path)
    return a.mean(axis=1), sr


def detect_f0(x, sr, lo=55.0, hi=2200.0):
    """Autocorrelation, parabolically interpolated. No prior about the tuning:
    these instruments are not all at the same pitch, and a window around an
    assumed A=415 lands on the edge and reports the edge."""
    y = x - x.mean()
    n = 1 << int(math.ceil(math.log2(max(len(y) * 2, 4))))
    ac = np.fft.irfft(np.abs(np.fft.rfft(y, n)) ** 2)[:len(y)]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]
    k0, k1 = int(sr / hi), min(int(sr / lo), len(ac) - 2)
    if k1 <= k0 + 2:
        return None
    k = k0 + int(np.argmax(ac[k0:k1]))
    d = ac[k - 1] - 2 * ac[k] + ac[k + 1]
    if d != 0:
        k = k + (ac[k - 1] - ac[k + 1]) / (2 * d)
    return sr / k


def onset(x, sr):
    return int(np.argmax(np.abs(x)))


def steady(x, sr, skip=0.05, dur=0.8):
    i = onset(x, sr)
    return x[i + int(skip * sr): i + int((skip + dur) * sr)]


def analytic_env(x, sr, lo, hi):
    """Envelope of one band, via the analytic signal.

    A partial IS a decaying sinusoid, so its envelope can be read directly.
    Schroeder backward integration is the right tool for a room -- it exists to
    recover a decay from a noisy impulse response -- but on a single partial it
    buys nothing and it is exquisitely sensitive to where the recording was
    truncated, which is how the first version of this fit gave two adjacent
    semitones decay rates fifty times apart.
    """
    n = len(x)
    X = np.fft.fft(x)
    f = np.fft.fftfreq(n, 1.0 / sr)
    Y = np.zeros(n, complex)
    m = (f >= lo) & (f <= hi)           # positive band only => analytic signal
    Y[m] = 2.0 * X[m]
    return np.abs(np.fft.ifft(Y))


def partial_slope(x, sr, fm, width, f0, lo_db=-5.0, hi_db=-25.0):
    """Amplitude dB/s for the partial at fm, or None if it will not support one.

    The floor comes from the LAST tenth of the file, never from the fit window:
    taking it from the window makes a room's noise look like the instrument's
    sustain, which is one of the four standing ways these fits go wrong.
    """
    e = analytic_env(x, sr, fm - width, fm + width)
    w = max(4, int(3.0 * sr / max(fm, 1.0)))        # smooth over ~3 periods
    e = np.convolve(e, np.ones(w) / w, 'same')
    skip = int(0.03 * sr)                            # past the attack
    if len(e) < skip + sr // 4:
        return None
    e = e[skip:]
    floor = np.median(e[int(0.9 * len(e)):]) * 3.0   # 10 dB above the tail
    pk = e[:int(0.2 * len(e))].max()
    if pk <= 0 or floor >= pk * 10 ** (hi_db / 20.0):
        return None                                  # no room between peak and floor
    db = 20.0 * np.log10(np.maximum(e, 1e-15) / pk)
    t = np.arange(len(db)) / float(sr)
    m = (db <= lo_db) & (db >= hi_db) & (e > floor)
    if m.sum() < int(0.05 * sr):                     # need 50 ms of straight line
        return None
    idx = np.flatnonzero(m)
    # The FIRST contiguous run only. Once the partial reaches the floor the mask
    # lights up again on noise, and a fit spanning that gap is a line drawn
    # between a decay and a hiss.
    brk = np.flatnonzero(np.diff(idx) > sr // 50)
    if len(brk):
        idx = idx[:brk[0] + 1]
    if len(idx) < int(0.05 * sr):
        return None
    s, _ = np.polyfit(t[idx], db[idx], 1)
    return s if s < -0.2 else None


def partial_decays(path, nmax=12):
    """[(m, amplitude dB/s)] for the first nmax partials, plus f0."""
    x, sr = mono(path)
    i = onset(x, sr)
    seg = x[i:]
    f0 = detect_f0(steady(x, sr), sr)
    if f0 is None or f0 <= 0:
        return None, None
    out = []
    for m in range(1, nmax + 1):
        fm = m * f0
        if fm > 0.45 * sr:
            break
        s = partial_slope(seg, sr, fm, 0.35 * f0, f0)
        if s is not None:
            out.append((m, -s))
    return f0, out


def cmd_decay(args):
    """D(m,f0) = (decay_db + harmonic_decay_db*m) * (f0/415)^slope, in the dB/s
    POWER convention tonelib uses -- so a measured amplitude decay of A dB/s is
    D = A/2, and T60 = 30/D."""
    files = sorted(f for f in glob.glob(os.path.join(args[0], '*.wav'))
                   if note_of(f) is not None)
    rows = []
    print("  per-note fits (amplitude dB/s per partial -> D = half that)")
    print("   note    f0      D(m=1)   slope over m   partials")
    for p in files:
        f0, ds = partial_decays(p)
        if not ds or len(ds) < 4:
            continue
        m = np.array([d[0] for d in ds], float)
        D = np.array([d[1] for d in ds]) / 2.0        # amplitude dB/s -> D
        a, b = np.polyfit(m, D, 1)                    # D = b + a*m
        if b <= 0 or a <= 0:
            continue
        rows.append((f0, b, a, len(ds)))
        print("   %-5s %7.1f  %7.2f   %7.2f        %2d"
              % (os.path.basename(p)[:5], f0, b + a, a, len(ds)))
    if len(rows) < 6:
        print("  too few usable notes (%d)" % len(rows)); return 1
    f0s = np.array([r[0] for r in rows])
    # The register slope is a power law in f0, so it is linear in the logs. Fit
    # it on D(m=1) rather than on the intercept: the intercept is the noisier of
    # the two and this is the number the model hangs the whole compass from.
    D1 = np.array([r[1] + r[2] for r in rows])
    slope, k = np.polyfit(np.log(f0s / REF_HZ), np.log(D1), 1)
    # Now solve the two decay terms at the reference pitch.
    scale = (f0s / REF_HZ) ** slope
    dec_db = float(np.median([r[1] / s for r, s in zip(rows, scale)]))
    har_db = float(np.median([r[2] / s for r, s in zip(rows, scale)]))
    print("\n  FITTED  decay_db %.3f   harmonic_decay_db %.3f   decay_register_slope %.3f"
          % (dec_db, har_db, slope))
    # Residuals per register: a fit that is only right in one octave is the
    # commonest way this goes wrong.
    print("\n  residual by register (dB/s of D, model - measured)")
    for lo, hi, name in ((0, 130, "below C3"), (130, 260, "C3-C4"),
                         (260, 520, "C4-C5"), (520, 1e9, "above C5")):
        sel = [(f, d) for f, d in zip(f0s, D1) if lo <= f < hi]
        if not sel:
            continue
        r = [(dec_db + har_db) * (f / REF_HZ) ** slope - d for f, d in sel]
        print("   %-9s n=%2d  mean %+6.2f  rms %5.2f" % (name, len(sel), np.mean(r),
                                                         np.sqrt(np.mean(np.square(r)))))
    # And the spread that says whether this is an instrument or a room.
    print("\n  D(m=1) spans %.2f to %.2f over %.1f octaves"
          % (D1.min(), D1.max(), math.log2(f0s.max() / f0s.min())))
    print("  a set whose decay does NOT rise with pitch is describing its room")
    return 0


def cmd_inharm(args):
    """f_m = m*f0*sqrt(1 + B m^2), so (f_m/m)^2 is linear in m^2.

    Frequencies are immune to reverberation -- a room changes when energy
    arrives, never at what frequency -- so this is the one fit that runs on
    every set regardless of how wet it is."""
    files = sorted(f for f in glob.glob(os.path.join(args[0], '*.wav'))
                   if note_of(f) is not None)
    print("   note     f0       B         partials")
    Bs = []
    for p in files:
        x, sr = mono(p)
        seg = steady(x, sr, 0.05, 0.8)
        if len(seg) < 8192:
            continue
        f0 = detect_f0(seg, sr)
        if not f0:
            continue
        N = 1 << 19
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
        f = np.fft.rfftfreq(N, 1.0 / sr)
        ns, fs = [], []
        for m in range(1, 19):
            fm = m * f0
            if fm > 0.45 * sr:
                break
            w = (f > fm * 0.985) & (f < fm * 1.035)
            if not w.any():
                break
            j = int(np.argmax(X[w]))
            if X[w][j] < X.max() * 1e-4:
                continue
            ns.append(m); fs.append(f[w][j])
        if len(ns) < 8:
            continue
        ns = np.array(ns, float); fs = np.array(fs)
        A = np.vstack([np.ones_like(ns), ns ** 2]).T
        c, *_ = np.linalg.lstsq(A, (fs / ns) ** 2, rcond=None)
        if c[0] <= 0 or c[1] <= 0:
            continue
        B = c[1] / c[0]
        Bs.append(B)
        print("   %-6s %7.1f  %9.2e  %2d" % (os.path.basename(p)[:6], f0, B, len(ns)))
    if Bs:
        print("\n  median B %.3e   mean %.3e   sd %.3e   n=%d"
              % (np.median(Bs), np.mean(Bs), np.std(Bs), len(Bs)))
        print("  adopt only if the spread is tight; scatter here is an f0 failure,")
        print("  not a property of the strings")
    return 0


def cmd_comb(args):
    """strike_point: mode m excited as |sin(m*pi*beta)|.

    Averaged across notes IN HARMONIC NUMBER, where the comb is invariant and a
    soundboard resonance -- which sits at a fixed frequency -- is not. That is
    the only reason this survives a reverberant set."""
    files = sorted(f for f in glob.glob(os.path.join(args[0], '*.wav'))
                   if note_of(f) is not None)
    nmax = 24
    R = []
    for p in files:
        x, sr = mono(p)
        i = onset(x, sr)
        seg = x[i + int(0.02 * sr): i + int(0.14 * sr)]     # direct-dominated
        if len(seg) < 4096:
            continue
        f0 = detect_f0(seg, sr)
        if not f0:
            continue
        N = 1 << 18
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
        f = np.fft.rfftfreq(N, 1.0 / sr)
        a = []
        for m in range(1, nmax + 1):
            fm = m * f0
            if fm > 0.45 * sr:
                break
            w = (f > fm - 0.3 * f0) & (f < fm + 0.3 * f0)
            a.append(X[w].max() if w.any() else 0.0)
        if len(a) < nmax:
            continue
        a = 20 * np.log10(np.maximum(np.array(a), 1e-12)); a -= a.max()
        if (a > -70).sum() < nmax:
            continue
        n = np.arange(1, nmax + 1)
        R.append(a - np.polyval(np.polyfit(np.log(n), a, 2), np.log(n)))
    if len(R) < 6:
        print("  too few usable notes (%d)" % len(R)); return 1
    mean = np.array(R).mean(0)
    n = np.arange(1, nmax + 1)
    best = (None, -9.0)
    for b in np.arange(0.015, 0.34, 0.0005):
        mdl = 20 * np.log10(np.abs(np.sin(n * np.pi * b)) + 10 ** -1.2)
        mdl = mdl - np.polyval(np.polyfit(np.log(n), mdl, 2), np.log(n))
        c = float(np.corrcoef(mean, mdl)[0, 1])
        if c > best[1]:
            best = (b, c)
    print("  %d notes   strike_point %.4f = 1/%.1f   fit r=%.2f"
          % (len(R), best[0], 1 / best[0], best[1]))
    return 0


def cmd_ratio(args):
    """Decay ratio between two stops of ONE instrument.

    The only room-free decay measurement available from single-mic recordings:
    both stops share the room, so dividing removes it exactly. Use this for a
    buff stop, where the question is 'how much faster', not 'how fast'."""
    a_dir, b_dir = args[0], args[1]
    byn = {}
    for d, k in ((a_dir, 0), (b_dir, 1)):
        for p in glob.glob(os.path.join(d, '*.wav')):
            n = note_of(p)
            if n is not None:
                byn.setdefault(n, [None, None])[k] = p
    print("   note   f0      D_a(m=1)  D_b(m=1)   ratio")
    rs = []
    for n in sorted(byn):
        pa, pb = byn[n]
        if not (pa and pb):
            continue
        fa, da = partial_decays(pa)
        fb, db_ = partial_decays(pb)
        if not da or not db_ or len(da) < 4 or len(db_) < 4:
            continue
        def D1(ds):
            m = np.array([d[0] for d in ds], float)
            D = np.array([d[1] for d in ds]) / 2.0
            c = np.polyfit(m, D, 1)
            return c[1] + c[0]
        A, B = D1(da), D1(db_)
        if A <= 0 or B <= 0:
            continue
        rs.append(B / A)
        print("   %-5d %7.1f %9.2f %9.2f %8.2f" % (n, fa, A, B, B / A))
    if rs:
        print("\n  median ratio %.2f   mean %.2f   sd %.2f   n=%d"
              % (np.median(rs), np.mean(rs), np.std(rs), len(rs)))
        print("  room-free: both stops shared it, so it divided out")
    return 0


CMDS = {'decay': cmd_decay, 'inharm': cmd_inharm, 'comb': cmd_comb, 'ratio': cmd_ratio}


def main(argv):
    if len(argv) < 3 or argv[1] not in CMDS:
        print(__doc__.strip())
        return 2
    return CMDS[argv[1]](argv[2:])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
