"""A coursed instrument's courses and its open courses' sympathy, read off
its takes and ours by one measure: the oud (hammondman's three long notes,
Freesound, CC0) and the mandolin (Joshua Meltzer's, Pianobook, as
pluck_fit.py stages them; sources.md).

  COURSES   each harmonic's envelope beats where the course's two strings
            sit a few cents apart: the beat's rate gives the split, its depth
            (peak to peak) the partner's level
  SYMPATHY  0.4-1.4 s in, the peaks that are not the note's own harmonics,
            each matched to an open course's harmonic (the oud's C2 F2 A2 D3
            G3 C4, the mandolin's D3 A3 E4 B4 -- tuned a fourth low),
            in dB under the note's 1st -- 25 cents and more off the note's
            own harmonics, past its course partner's (which resolve as peaks
            beside them, 6-9 dB under)

    python3 examples/course_sympathy.py [--voice=oud|mandolin]   # the takes and ours
    python3 examples/course_sympathy.py --voice=... --fit        # sympathetic_gain to the peaks
"""
import glob
import os
import sys

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)),
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
from drum_fit import read  # noqa: E402

VOICES = {
    "oud": dict(cls="OudProperties",
                takes="~/Documents/refs/freesound/oud_hammondman/*.wav",
                open={"C2": 65.41, "F2": 87.31, "A2": 110.0, "D3": 146.83, "G3": 196.0, "C4": 261.63},
                f0=(85.0, 140.0), top_hz=1100.0),
    # its staged notes name their pitch (pluck_fit.py --voice=mandolin --stage)
    "mandolin": dict(cls="MandolinProperties",
                     takes="~/Documents/refs/freesound/staged/mandolin/*.wav",
                     open={"D3": 146.83, "A3": 220.0, "E4": 329.63, "B4": 493.88},
                     f0=None, top_hz=3000.0)}
V = VOICES["oud"]


def f0_of(x, sr, lo, hi):
    N = 1 << 19
    S = np.abs(np.fft.rfft(x * np.hanning(len(x)), N)) ** 2
    f = np.fft.rfftfreq(N, 1 / sr)
    Lg = np.log(S + 1e-20)

    def at(hz):
        i = int(round(hz / f[1]))
        w = max(2, int(0.005 * hz / f[1]))
        return Lg[max(0, i - w):i + w + 1].max()
    return max((np.mean([at(c * h) for h in range(1, 9)])
                - np.mean([at(c * (h + 0.5)) for h in range(1, 9)]), c)
               for c in np.arange(lo, hi, 0.05))[1]


def courses(x, sr, f0, hs=range(3, 11)):
    """[(h, cents, partner dB)] from each harmonic's beating."""
    rows = []
    for h in hs:
        fc = h * f0
        y = sosfiltfilt(butter(2, [fc * 0.985, fc * 1.015], btype="band", fs=sr, output="sos"), x)
        w = int(0.01 * sr)
        e = 10 * np.log10(np.convolve(y ** 2, np.ones(w) / w, "same")[::w] + 1e-20)
        t = np.arange(len(e)) * 0.01
        sel = (t > 0.15) & (e > e.max() - 40)
        if sel.sum() < 30:
            continue
        res = e[sel] - np.polyval(np.polyfit(t[sel], e[sel], 2), t[sel])
        R = np.abs(np.fft.rfft((res - res.mean()) * np.hanning(len(res)), 16 * len(res)))
        fr = np.fft.rfftfreq(16 * len(res), 0.01)
        ok = (fr > 1.0 / (t[sel][-1] - t[sel][0])) & (fr < 15)
        if not ok.any():
            continue
        beat = fr[ok][np.argmax(R[ok])]
        pp = np.subtract(*np.percentile(res, [95, 5]))
        a = (10 ** (pp / 20) - 1) / (10 ** (pp / 20) + 1)
        rows.append((h, 1200 * np.log2(1 + beat / fc), 20 * np.log10(max(a, 1e-6))))
    return rows


def sympathy(x, sr, f0, t0=0.4, t1=1.4, f0s=()):
    """{(course, harmonic): dB under h1} for the peaks off the note's harmonics."""
    seg = x[int(t0 * sr):int(min(t1 * sr, len(x)))]
    N = 1 << 19
    S = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) + 1e-12)
    f = np.fft.rfftfreq(N, 1 / sr)
    ok = (f > 50) & (f < V["top_hz"])
    pk, _ = find_peaks(S[ok], prominence=10, distance=int(1.0 / f[1]))
    a1 = S[(f > f0 * 0.99) & (f < f0 * 1.01)].max()
    out = {}
    for hz, lv in zip(f[ok][pk], S[ok][pk]):
        # not the note's own harmonics, stretched, nor its course partner's
        # (4-16 cents off them): within 25 cents of one is the note
        # (f0s: the note's other estimates -- a stiff string's harmonic
        # score lands its stretched upper harmonics, ~10 cents over)
        if any(abs(1200 * np.log2(hz / (max(1, round(hz / g)) * g))) < 25 for g in (f0,) + tuple(f0s)):
            continue
        c, n, m = min((abs(1200 * np.log2(hz / (fo * m))), n, m)
                      for n, fo in V["open"].items() for m in range(1, 9))
        if c < 25 and lv - a1 > -45:
            out[(n, m)] = max(out.get((n, m), -99.0), lv - a1)
    return out


def takes():
    out = []
    for p in sorted(glob.glob(os.path.expanduser(V["takes"]))):
        x, sr = read(p)
        x = x.mean(1) if x.ndim > 1 else x
        k = int(np.argmax(np.abs(x)))
        x = x[k:]
        name = os.path.basename(p).split("__")[-1]
        if V["f0"]:
            f0 = f0_of(x[int(0.05 * sr):], sr, *V["f0"])
        else:
            # the staged pitch, read at the fundamental
            f0 = float(name.rsplit("_f0_", 1)[1][:-4])
        out.append((name, x, sr, f0))
    return out


def ours(f0, secs):
    import pluck_fit as P
    P.PROG, P.CLS, _ = P.VOICES[V["name"]]
    P.BANK = P.BANKS[V["name"]]
    y, sr = P.render(f0, secs)
    k = int(np.argmax(np.abs(y)))
    return y[k:], sr


def report(T, gain=None):
    import tonelib
    if gain is not None:
        setattr(getattr(tonelib, V["cls"]), "sympathetic_gain", gain)
    err = []
    for name, x, sr, f0 in T:
        y, s2 = ours(f0, len(x) / sr)
        print("== %s %.2f Hz" % (name, f0))
        o = dict((r[0], r) for r in courses(y, s2, f0))
        for h, c, d in courses(x, sr, f0):
            r = o.get(h)
            print("   h%-2d  take %4.1f c %+5.1f dB   ours %s" % (
                h, c, d, "%4.1f c %+5.1f dB" % r[1:] if r else "-"))
        hs = (f0_of(x[int(0.05 * sr):], sr, f0 * 0.99, f0 * 1.015),)
        A, B = sympathy(x, sr, f0, f0s=hs), sympathy(y, s2, f0, f0s=hs)
        for key in sorted(set(A) | set(B), key=lambda k: V["open"][k[0]] * k[1]):
            a, b = A.get(key), B.get(key)
            print("   %s h%d  take %s  ours %s" % (key[0], key[1],
                  "%+5.1f" % a if a is not None else "  -  ", "%+5.1f" % b if b is not None else "  -  "))
            if a is not None:
                err.append((b if b is not None else -45.0) - a)
    e = np.asarray(err)
    print("sympathy, ours - take: mean %+.1f dB, rms %.1f over %d peaks" % (e.mean(), np.sqrt((e ** 2).mean()), len(e)))
    return e


def main(argv):
    global V
    name = next((a.split("=", 1)[1] for a in argv if a.startswith("--voice=")), "oud")
    V = dict(VOICES[name], name=name)
    T = takes()
    if "--fit" in argv:
        import tonelib
        g = getattr(tonelib, V["cls"]).sympathetic_gain
        for _ in range(3):
            e = report(T, g)
            g *= 10 ** (-np.median(e) / 20)
            print("-> sympathetic_gain %.3f\n" % g)
        report(T, g)
    else:
        report(T)


if __name__ == "__main__":
    main(sys.argv[1:])
