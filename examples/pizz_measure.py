#!/usr/bin/env python3
"""A pizzicato note, measured: its pluck, its decay, its length.

    python3 examples/pizz_measure.py DIR [DIR ...]

DIR holds one note per file, the note in the name (examples/pizz_split.py
writes Iowa's that way, <note>.sul<string>.wav). voicefit.py's own tools find
the pitch with no prior, and on a pluck under a second long they slip an
octave -- the violin reported notes at 65 Hz, below its lowest string, and the
bass's ladder alternated, the sign of a period twice the real one. Here the
pitch is the NAME's, refined to the spectral peak within 60 cents, and
everything is read at harmonics of it:

  B        the string's stretch, from partials 2-12 found up to 6% sharp of
           their harmonic: f_m / m f0 = sqrt(1 + B m^2) / sqrt(1 + B).
  ladder   partials 1-16 over the 60 ms after the envelope's peak, dB under
           the fundamental, each read where B puts it: the pluck's spectrum,
           where its comb shows. (Read at m f0 instead, a stretched partial
           falls out of its window -- the model's 8th of G4 sits 4% sharp,
           and the first ladder showed a 30 dB cliff that was not there.)
  beta     the pluck point, from that ladder: the comb |sin(m pi beta)| best
           correlated with it once the smooth trend is taken out, as
           voicefit's comb does -- but per note, so it can MOVE: a player
           plucks a fixed distance from the bridge, so as a finger stops the
           string shorter that distance becomes a larger fraction of it.
  D(m)     each partial's amplitude decay, dB/s (voicefit.partial_slope),
           partials 1-8, and the line a + b m through them.
  T30      the note's length: 10 ms RMS envelope from its peak to 30 dB under.

Prints per note, then per instrument by octave. The same code measures a
render (`--render` on a file whose notes were rendered one per file), so the
model is compared like for like.
"""
import glob
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from voicefit import mono, note_of, partial_slope  # noqa: E402

NM = 16


def measure(path):
    n = note_of(path)
    if n is None:
        return None
    x, sr = mono(path)
    w = int(0.01 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, 'same'))
    pk = int(np.argmax(e))
    f_nom = 440.0 * 2 ** ((n - 69) / 12.0)
    seg = x[pk + int(0.005 * sr): pk + int(0.065 * sr)]
    if len(seg) < int(0.05 * sr):
        return None
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    # the fundamental: the peak within 60 cents of the name, in a longer window
    lw = x[pk + int(0.005 * sr): pk + int(0.3 * sr)]
    LX = np.abs(np.fft.rfft(lw * np.hanning(len(lw)), N))
    b = (f > f_nom * 2 ** (-0.6 / 12)) & (f < f_nom * 2 ** (0.6 / 12))
    f0 = float(f[b][np.argmax(LX[b])])
    # the stretch, from the longer window's peaks
    st = []
    for m in range(2, 13):
        b = (f > m * f0 * 0.985) & (f < m * f0 * 1.06)
        if not b.any() or f[b].max() > 0.45 * sr:
            break
        i = np.argmax(LX[b])
        if 20 * np.log10(LX[b][i] / LX.max()) > -50:
            st.append((m, f[b][i] / (m * f0)))
    B = (float(np.median([(r * r - 1) / (m * m - r * r) for m, r in st])) if len(st) >= 4 else 0.0)
    B = max(0.0, B)
    lad = []
    for m in range(1, NM + 1):
        fm = m * f0 * (1.0 + 0.5 * (m * m - 1) * B)
        if fm > 0.45 * sr:
            break
        bw = (f > fm - 0.25 * f0) & (f < fm + 0.25 * f0)
        lad.append(X[bw].max())
    lad = 20 * np.log10(np.maximum(np.array(lad), 1e-12) / max(lad[0], 1e-12))
    # the comb, per note, as voicefit's: trend out, then correlate
    beta = None
    if len(lad) >= 10 and (lad > -70).sum() >= 10:
        mm = np.arange(1, len(lad) + 1)
        r = lad - np.polyval(np.polyfit(np.log(mm), lad, 2), np.log(mm))
        best = (None, -9.0)
        for bb in np.arange(0.03, 0.5, 0.0025):
            mdl = 20 * np.log10(np.abs(np.sin(mm * np.pi * bb)) + 10 ** -1.2)
            mdl = mdl - np.polyval(np.polyfit(np.log(mm), mdl, 2), np.log(mm))
            c = float(np.corrcoef(r, mdl)[0, 1])
            if c > best[1]:
                best = (bb, c)
        beta = best
    tail = x[pk:]
    D = []
    for m in range(1, 9):
        fm = m * f0 * (1.0 + 0.5 * (m * m - 1) * B)
        if fm > 0.45 * sr:
            break
        s = partial_slope(tail, sr, fm, 0.3 * f0, f0)
        if s is not None:
            D.append((m, -s))
    db = 20 * np.log10(e[pk:] / e[pk] + 1e-12)
    below = np.flatnonzero(db < -30)
    t30 = below[0] / float(sr) if len(below) else None
    return dict(note=n, f0=f0, B=B, ladder=lad, beta=beta, D=D, t30=t30,
                string=os.path.basename(path).split('.')[1] if path.count('.') > 1 else '')


def line(D):
    if len(D) < 3:
        return None
    m = np.array([d[0] for d in D], float)
    v = np.array([d[1] for d in D], float)
    b, a = np.polyfit(m, v, 1)
    return a, b


def report(rows, title):
    print("== %s: %d notes" % (title, len(rows)))
    octs = {}
    for r in rows:
        octs.setdefault(r['note'] // 12 - 1, []).append(r)
    print("   oct  n   T30 s   D1 dB/s  a+b*m          beta (r)       B        ladder m2..m10 (dB re m1)")
    for o in sorted(octs):
        rs = octs[o]
        t = [r['t30'] for r in rs if r['t30']]
        d1 = [dict(r['D']).get(1) for r in rs if dict(r['D']).get(1)]
        ab = [line(r['D']) for r in rs if line(r['D'])]
        be = [r['beta'] for r in rs if r['beta'] and r['beta'][1] > 0.5]
        L = np.array([r['ladder'][:10] for r in rs if len(r['ladder']) >= 10])
        Bs = [r['B'] for r in rs if r['B'] > 0]
        print("   %3d %2d  %5s   %6s   %-14s %-14s %-8s %s" % (
            o, len(rs), "%.2f" % np.median(t) if t else "-",
            "%.1f" % np.median(d1) if d1 else "-",
            "%.1f%+.1f m" % tuple(np.median(np.array(ab), 0)) if ab else "-",
            "%.3f (%d)" % (np.median([b[0] for b in be]), len(be)) if be else "-",
            "%.1e" % np.median(Bs) if Bs else "-",
            " ".join("%5.1f" % v for v in np.median(L, 0)[1:]) if len(L) else "-"))


def main(argv):
    dirs = [a for a in argv[1:] if not a.startswith('--')]
    for d in dirs:
        rows = [r for r in (measure(p) for p in sorted(glob.glob(os.path.join(d, '*.wav')))) if r]
        report(rows, os.path.basename(os.path.normpath(d)))
        if '--notes' in argv:
            for r in sorted(rows, key=lambda r: (r['string'], r['note'])):
                print("     %-6s %-5s f0 %7.1f  T30 %5s  beta %s" % (
                    r['string'], r['note'], r['f0'], "%.2f" % r['t30'] if r['t30'] else "-",
                    "%.3f r=%.2f" % r['beta'] if r['beta'] else "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
