#!/usr/bin/env python3
"""Fit the helicopter (GM 125) to three passes: its spectrum and its chop.
sources.md "Sound effects".

    python3 -I examples/heli_fit.py measure      the passes, and ours
    python3 -I examples/heli_fit.py fit          harmonics, wash and chop (writes tonelib.py)
    python3 -I examples/heli_fit.py ab OUT.wav   each pass's closest second, then ours

THE TAKES (CC0, Freesound): Nox_Sound's close flyby (546806, Rode NT4) and
TRP's two overhead passes (573941, 573942, a parabolic). Light two-blade
machines: the main rotor's blade passes ~70 ms apart (~14 Hz), a turn of the
rotor ~150 ms (one blade not quite the other), and a faster chop ~24 ms
(the tail rotor or the engine).

WHAT THEY HOLD, near the closest point: energy from 80 Hz to 1.3 kHz, little
at 20-40 Hz, falling ~18 dB by 2.5 kHz and ~40 by 5 kHz (distance and air);
the chop swinging the level 7-13 dB -- a steady wash under the blade passes.
Ours had been a bare sawtooth at 16 Hz: its energy at 20-40 Hz, nothing past
1 kHz, a 35 dB chop.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

FS = os.path.expanduser("~/Documents/refs/freesound/helicopter_wav")
OCT = (20, 40, 80, 160, 320, 640, 1280, 2560, 5120, 10240)
KEY = 60
CHOP_DB = None          # the passes' own, measured


def load(p):
    from scipy.io import wavfile
    import warnings
    warnings.simplefilter("ignore")
    sr, x = wavfile.read(p)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    return x / np.abs(x).max(), sr


def _movavg(x, w):
    c = np.concatenate(([0.0], np.cumsum(x)))
    return (c[w:] - c[:-w]) / w


def closest(x, sr, secs=3.0):
    """SECS around the pass's loudest half-second."""
    e = _movavg(x * x, int(0.5 * sr))
    i = int(np.argmax(e))
    a = max(0, i - int(secs / 2 * sr))
    return x[a:a + int(secs * sr)]


def reading(seg, sr):
    """(octave bands from 20 Hz, dB re the loudest; chop depth, dB: the
    95th over the 5th percentile of the 0.3-3 kHz envelope at 5 ms)."""
    from scipy.signal import butter, sosfiltfilt
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 18)) ** 2
    f = np.fft.rfftfreq(1 << 18, 1.0 / sr)
    o = np.array([10 * np.log10(X[(f >= lo) & (f < 2 * lo)].sum() + 1e-30) for lo in OCT])
    b = sosfiltfilt(butter(2, [300, 3000], btype="band", fs=sr, output="sos"), seg)
    env = _movavg(np.abs(b), int(0.005 * sr))
    chop = 20 * np.log10(np.percentile(env, 95) / max(np.percentile(env, 5), 1e-12))
    return o - o.max(), float(chop)


def takes():
    return [closest(*load(p)) + (None,) for p in sorted(glob.glob(os.path.join(FS, "*.wav")))]


def target():
    rs = []
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        rs.append(reading(closest(x, sr), sr))
    return np.mean([r[0] for r in rs], 0), float(np.mean([r[1] for r in rs]))


def ours():
    y, sr = U.render(125, KEY, 100, 4.0)
    return reading(y[int(1.0 * sr):int(3.5 * sr)], sr)


def measure():
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        o, c = reading(closest(x, sr), sr)
        print("  %-40s chop %4.1f dB  octaves %s" % (os.path.basename(p)[:40], c, " ".join("%+4.0f" % v for v in o)))
    o, c = ours()
    print("  %-40s chop %4.1f dB  octaves %s" % ("ours", c, " ".join("%+4.0f" % v for v in o)))


def fit(passes=8):
    """The harmonics by octave (mode_gains: the series' level in each band)
    and the wash (breath_noise_db: third-octave rows held for the note) to
    the passes' octave spectrum, and the wash's share under the harmonics to
    their chop. Writes both into tonelib.py."""
    import tonelib as T
    cls = T.HelicopterProperties
    R, chop = target()
    f0 = 440.0 * 2 ** ((KEY - 69) / 12.0) * 2 ** cls.sounding_octaves
    nh = cls.max_harmonic
    hb = np.zeros(len(OCT))           # dB a band, the harmonics
    nb = np.full(len(OCT), -12.0)     # dB a band, the wash re the harmonics there
    share = 0.0
    cen = [c * 2 ** (k / 3.0) for c in OCT for k in (0, 1, 2)]

    def band(fr):
        return int(np.clip(np.searchsorted(OCT, fr, side="right") - 1, 0, len(OCT) - 1))

    def apply():
        cls.mode_gains = tuple(round(float(10 ** (hb[band(m * f0)] / 20.0) / m), 6) for m in range(1, nh + 1))
        top = band(nh * f0)
        cls.breath_noise_db = tuple((int(round(c)), round(float(
            (hb[band(c)] + nb[band(c)] + share) if band(c) <= top else (hb[top] + nb[band(c)])), 1)) for c in cen)
    for it in range(passes + 1):
        apply()
        O, c = ours()
        d = R - O
        print("  pass %d: rec - ours by octave %s (rms %.1f); chop %.1f against %.1f" % (
            it, " ".join("%+.0f" % v for v in d), np.sqrt(np.mean(d ** 2)), c, chop), flush=True)
        if it == passes:
            break
        top = band(nh * f0)
        for k in range(len(OCT)):
            if k <= top:
                hb[k] += 0.7 * d[k]
            else:
                nb[k] += 0.7 * d[k]
        # more wash under the harmonics -> a shallower chop
        share += 0.5 * (c - chop)
    path = os.path.join(os.path.dirname(HERE), "tonelib.py")
    src = open(path).read()
    a = src.index("class HelicopterProperties(")
    b = src.index("\nclass ", a + 10)
    body = src[a:b]
    for name, val in (("mode_gains", cls.mode_gains), ("breath_noise_db", cls.breath_noise_db)):
        line = "    %s = %s" % (name, val)
        if re.search(r"^    %s = " % name, body, flags=re.M):
            body = re.sub(r"^    %s = .*$" % name, lambda _: line, body, count=1, flags=re.M)
        else:
            body = body.rstrip("\n") + "\n" + line + "\n"
    open(path, "w").write(src[:a] + body + src[b:])
    print("  written: mode_gains (%d), breath_noise_db (%d rows), wash share %+.1f dB" % (
        len(cls.mode_gains), len(cls.breath_noise_db), share))


def ab(out):
    import harpsi_ab as A
    from roomtail import write_wav
    gap = np.zeros(int(0.6 * A.SR))
    parts = []
    A.NOTE_S = 4.0
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        parts += [A.fit_note(closest(x, sr, 4.0), sr), gap]
    y, sr2 = U.render(125, KEY, 100, 4.0)
    parts += [A.fit_note(y, sr2)]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


def main(argv):
    if argv[1:2] == ["measure"]:
        measure()
    elif argv[1:2] == ["fit"]:
        fit()
    elif argv[1:2] == ["ab"]:
        ab(argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
