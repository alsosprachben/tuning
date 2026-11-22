"""The Wurlitzer 4500's Spectra-Tone, measured off Ben's takes (2026-11-21).

Takes: ~/Documents/refs/wurlitzer_ben/spectratone2/ (SESSION.md logs each).
Ben's own instrument and recordings: ours outright.

For each held note, each harmonic's band (+-1.5%): its level over time (the
swirl) and its pitch over time (the Doppler), at 200 Hz. From those:

  rates     the swirl's fundamental (harmonic-sum over 0.2-4 Hz) and the pitch
            wobble's -- two back-to-back cones beam twice per turn, so the
            level may swing at twice the rotation while the Doppler (one cone
            nearer, then the other) swings once
  lobe      the swirl's depth and its 2nd/3rd harmonics against frequency
  doppler   cents peak-to-peak against frequency
  ramps     st_change.wav: the rate in 2 s windows through each switch, and
            the time constants up and down
  chorus    the swirl's depth with Upper alone and with Upper + Chorus

    python3 examples/spectratone_fit.py [--ramps]
"""
import os, sys, json
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, hilbert

DIR = os.path.expanduser("~/Documents/refs/wurlitzer_ben/spectratone2")
FS_ENV = 200.0
# the organ sits ~32 cents flat of A440 (2026-11-20); its C's, measured
C = {2: 64.2, 3: 128.4, 4: 256.9, 5: 513.7, 6: 1027.4, 7: 2054.8}


def load(name):
    sr, a = wavfile.read(os.path.join(DIR, name))
    return a[:, 0].astype(np.float64) / 32768.0, sr


def band(x, sr, f, w=0.015):
    sos = butter(4, [f * (1 - w), f * (1 + w)], btype="band", fs=sr, output="sos")
    return sosfiltfilt(sos, x)


def env_db(y, sr):
    n = int(sr / FS_ENV)
    e = np.sqrt(np.convolve(y ** 2, np.ones(2 * n) / (2 * n), "same"))[::n]
    return 20 * np.log10(e + 1e-12)


def inst_cents(y, sr, f):
    n = int(sr / FS_ENV)
    ph = np.unwrap(np.angle(hilbert(y)))
    fi = np.diff(ph) * sr / (2 * np.pi)
    fi = np.convolve(fi, np.ones(2 * n) / (2 * n), "same")[::n]
    return 1200 * np.log2(np.maximum(fi, 1.0) / f)


def segments(x, sr, notes, lo=0.0, hi=None):
    """{octave: (t0, t1)}: the longest run where that C sounds (its band within
    20 dB of its loudest) and is not the octave below's 2nd harmonic."""
    hi = hi or len(x) / sr
    i0, i1 = int(lo * sr), int(hi * sr)
    xs = x[i0:i1]
    E = {o: env_db(band(xs, sr, C[o], 0.03), sr) for o in set(notes) | {o - 1 for o in notes if o - 1 in C}}
    out = {}
    for o in notes:
        e = np.convolve(E[o], np.ones(200) / 200, "same")
        own = e > e.max() - 20
        if o - 1 in E:
            below = np.convolve(E[o - 1], np.ones(200) / 200, "same")
            own &= below < e - 10
        best, i = (0, 0), 0
        while i < len(own):
            if own[i]:
                j = i
                while j < len(own) and own[j]:
                    j += 1
                if j - i > best[1] - best[0]:
                    best = (i, j)
                i = j
            else:
                i += 1
        if best[1] - best[0] > 4 * FS_ENV:
            out[o] = (lo + best[0] / FS_ENV + 1.0, lo + best[1] / FS_ENV - 1.0)
    return out


def fundamental(z, fmin=0.2, fmax=4.0):
    """(rate, strength): the fundamental of a periodic swing by harmonic sum."""
    z = z - z.mean()
    nfft = 1 << int(np.ceil(np.log2(len(z) * 16)))
    P = np.abs(np.fft.rfft(z * np.hanning(len(z)), nfft))
    f = np.fft.rfftfreq(nfft, 1.0 / FS_ENV)
    cand = f[(f >= fmin) & (f <= fmax)]
    score = [sum(np.interp(k * c, f, P) / k for k in (1, 2, 3)) for c in cand]
    k = int(np.argmax(score))
    return float(cand[k]), float(score[k] / (np.median(P[f < 8]) + 1e-12))


def swing_shape(z, rate):
    """(depth dB p-p, c1, c2/c1, c3/c1) of the level swing in linear amplitude,
    by projection on the rate's harmonics."""
    t = np.arange(len(z)) / FS_ENV
    a = 10 ** (z / 20)
    a = a / a.mean()
    c = [2 * abs(np.mean(a * np.exp(-2j * np.pi * k * rate * t))) for k in (1, 2, 3)]
    return float(np.percentile(z, 95) - np.percentile(z, 5)), c[0], c[1] / max(c[0], 1e-9), c[2] / max(c[0], 1e-9)


def note_rows(name, notes, lo=0.0, hi=None, harmonics=6):
    x, sr = load(name)
    segs = segments(x, sr, notes, lo, hi)
    rows = []
    for o, (t0, t1) in sorted(segs.items()):
        xs = x[int(t0 * sr):int(t1 * sr)]
        for h in range(1, harmonics + 1):
            f = C[o] * h
            if f > 9000:
                break
            y = band(xs, sr, f)
            z = env_db(y, sr)[20:-20]
            if z.mean() < -80:
                continue
            cents = inst_cents(y, sr, f)[20:-20]
            rate, strength = fundamental(z)
            frate, fstr = fundamental(cents)
            depth, c1, r2, r3 = swing_shape(z, rate)
            rows.append(dict(take=name, oct=o, h=h, f=round(f, 1), t0=round(t0, 1), t1=round(t1, 1),
                             level=round(float(z.mean()), 1), rate=round(rate, 3), rate_q=round(strength, 1),
                             depth=round(depth, 1), c1=round(c1, 3), r2=round(r2, 2), r3=round(r3, 2),
                             cents=round(float(np.percentile(cents, 95) - np.percentile(cents, 5)), 1),
                             frate=round(frate, 3), frate_q=round(fstr, 1)))
    return rows


def ramps():
    """st_change.wav: the swirl's rate on C6 and C7 in 2 s windows, 0.5 s apart."""
    x, sr = load("st_change.wav")
    out = []
    for o, (lo, hi) in ((6, (28.0, 100.0)), (7, (101.0, 189.0))):
        y = band(x[int(lo * sr):int(hi * sr)], sr, C[o])
        z = env_db(y, sr)
        w, s = int(4 * FS_ENV), int(0.5 * FS_ENV)
        for i in range(0, len(z) - w, s):
            r, q = fundamental(z[i:i + w], 0.3, 3.0)
            out.append((o, round(lo + (i + w / 2) / FS_ENV, 2), round(r, 3), round(q, 1)))
    return out


def main(argv):
    rows = []
    rows += note_rows("st_warm.wav", (2, 3, 4, 5, 6, 7), 20.0, 113.0)      # fast
    rows += note_rows("st_warm.wav", (2, 3, 4, 5, 6, 7), 113.0, 226.0)     # slow
    rows += note_rows("st_upper_fast.wav", (5, 6, 7))
    rows += note_rows("st_upper_slow.wav", (5, 6, 7))
    rows += note_rows("st_lower_fast.wav", (5, 6, 7))
    rows += note_rows("st_lower_slow.wav", (5, 6, 7))
    rows += note_rows("st_chorus.wav", (5, 6))
    rows += note_rows("st_dry.wav", (3, 4, 5, 6))
    out = dict(notes=rows)
    if "--ramps" in argv:
        out["ramps"] = ramps()
    json.dump(out, open(os.path.join(DIR, "spectratone_fit.json"), "w"), indent=1)
    for r in rows:
        print("%-18s C%d h%d %7.1f Hz %6.1f-%6.1f s  lvl %6.1f  swirl %5.3f Hz (q%5.1f) %5.1f dB  c1 %.3f r2 %.2f r3 %.2f"
              "  pitch %5.1f c @ %5.3f Hz (q%5.1f)" % (
                  r["take"], r["oct"], r["h"], r["f"], r["t0"], r["t1"], r["level"], r["rate"], r["rate_q"],
                  r["depth"], r["c1"], r["r2"], r["r3"], r["cents"], r["frate"], r["frate_q"]))
    for o, t, r, q in out.get("ramps", []):
        print("ramp C%d %7.2f s  %.3f Hz (q%.1f)" % (o, t, r, q))


if __name__ == "__main__":
    main(sys.argv)
