#!/usr/bin/env python3
"""The SFX set's voices as throats (tonelib.SfxThroatProperties): their
formants by LPC of the recordings, written as the classes' DRUM_MODES.

    python3 -I examples/throat_fit.py [VOICE ...]          the formants, frame by frame and chosen
    python3 -I examples/throat_fit.py --write [VOICE ...]  ...into tonelib.py
    python3 -I examples/throat_fit.py --contours           the dogs' barks' pitch, 2.5 ms steps
    python3 -I examples/throat_fit.py --tilt               the barks' brightness, 30 ms windows
    python3 -I examples/throat_fit.py --balance [--write] [VOICE ...]
                                    the formants' levels against the takes' band balance
                                    (after --write: LPC's levels are only its start)

VOICE is dog (76), laugh (52, a "ho ho ho"), cat, growl or hoo (GS 78-79).

LPC (order 20-22 at 22.05 kHz, no pre-emphasis: the source's tilt stays in
the envelope) over 25-30 ms frames where the voice is loud; each pole a
resonance, its frequency and bandwidth from its angle and radius, its height
the envelope there. Each formant is the median of the poles in its WINDOW
across the frames. A high voice (a bark at 550 Hz, a laugh at 340) puts a
pole ON the fundamental, tens of Hz wide -- a harmonic, not a resonance --
so a formant's bandwidth is floored (BW_MIN): rung at 30 Hz it would be a
tone.

AS MODES, struck by each glottal pulse (the FOF): an impulse through a
resonance of bandwidth B rings at e^(-pi B t) -- 27.3 B dB/s -- and its peak
in the spectrum is its amplitude over B, so each mode's level is the
envelope's peak plus 20 log10 B, re the strongest.
"""
import math
import os
import re
import sys

import numpy as np
from scipy.io import wavfile
from scipy.linalg import solve_toeplitz
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.expanduser("~/Documents/refs/freesound")
SR = 22050
BW_MIN = 150.0
# voice: (class, recording, LPC order, frame starts s, frame length s, formant windows Hz)
VOICES = {
    "dog": ("SfxDogProperties", "dog/hits/bark_01.wav", 20, (0.03, 0.06, 0.09, 0.12), 0.03,
            ((450, 700), (1150, 1600), (2200, 2800), (3200, 3900), (5000, 5800))),
    # a Santa's "ho ho ho" (Ben: "Why not try to make it a ho ho ho?"): its
    # four "ho"s and the long "hooo", an /o/ -- F1 ~500, F2 ~850, the pair at
    # 2.5 and 2.9 kHz that rings in it, and one at 5.7 kHz (none at 1-2 kHz:
    # the vowel's valley, his energy there the harmonics' skirts)
    "laugh": ("SfxLaughProperties", "hohoho/110641__canucklovingbrit__santa-ho-ho-ho-1.wav", 20,
              (0.06, 0.09, 0.51, 0.54, 0.90, 0.93, 1.27, 1.30, 1.62, 1.70, 1.80, 1.95), 0.03,
              ((420, 620), (700, 1000), (1100, 2000), (2350, 2700), (2800, 3100), (3200, 6000))),
    # GS 123.4 Kitty: peridactyloptrix's five meows (CC0), ~640 Hz, clean --
    # frames through each meow's body (its first 0.1 s and last 0.15 s left out)
    "cat": ("SfxKittyProperties", "cat/214759__peridactyloptrix__cat-meowing-x5.wav", 20,
            (1.62, 1.80, 1.98, 5.82, 6.00, 6.18, 8.62, 8.80, 8.98, 10.90, 11.08, 11.26, 14.23, 14.41, 14.59),
            0.03, ((500, 900), (900, 1700), (1700, 2300), (2300, 2900), (2900, 3700), (3700, 5000))),
    # GS 123.5 Growl: qubodup's dog growling (CC0; its FLAC as WAV beside it),
    # ~130 Hz and rough -- frames in its loudest bursts
    "growl": ("SfxGrowlProperties", "growl/122183__qubodup__dog-growling-snarling-grumbling.wav", 22,
              (4.55, 4.70, 5.55, 5.70, 6.95, 7.10, 8.15, 8.35, 8.55, 9.95, 10.15, 10.55, 12.0, 15.5, 16.0),
              0.04, ((150, 450), (450, 900), (900, 1400), (1400, 2000), (2000, 2800), (2800, 3800))),
    # GS Hip-Hop / Dance 78-79, High/Low Hoo: Reitanna's "HOO! HA! HEE HA!"
    # (CC0), its HOO -- ~480 Hz level for 0.12 s, then falling an octave --
    # frames through its level part; an /u/
    "hoo": ("HooProperties", "../hoo/raw/343968__reitanna__hoo-ha-hee-ha.wav", 20,
            (0.09, 0.11, 0.13, 0.15, 0.17), 0.025,
            ((400, 650), (700, 1300), (2100, 3000), (3400, 4400), (6000, 7000))),
    # RHYTHM FX 2 65-70, Voice One / Two / Three: steprock's count (Freesound
    # 541622, CC0; a deep man's voice, ~130 Hz) -- each word's vowel at its
    # start ("x") and its end ("x_b", the class's DRUM_MODES_B, a morph):
    # "one" /wʌn/ F2 940 -> 1520 into the n, "two" /tuː/ F2 1700 -> 1000,
    # "three" /θriː/ F2 1440 -> 2190 from the r into the ee
    "one": ("RfxVoiceOneProperties", "../voice_fx/raw/541622__steprock__video-game-count-and-more.wav", 18,
            (0.64, 0.67, 0.70), 0.025, ((450, 850), (800, 1300), (2300, 3200), (3300, 4300))),
    "one_b": ("RfxVoiceOneProperties", "../voice_fx/raw/541622__steprock__video-game-count-and-more.wav", 18,
              (0.82, 0.85, 0.88), 0.025, ((450, 850), (1300, 2000), (2300, 3200), (3300, 4300))),
    "two": ("RfxVoiceTwoProperties", "../voice_fx/raw/541622__steprock__video-game-count-and-more.wav", 18,
            (1.90, 1.93, 1.96), 0.025, ((220, 500), (1300, 2100), (2500, 3300), (3300, 4300))),
    "two_b": ("RfxVoiceTwoProperties", "../voice_fx/raw/541622__steprock__video-game-count-and-more.wav", 18,
              (2.12, 2.15, 2.18), 0.025, ((220, 500), (800, 1300), (2500, 3300), (3300, 4300))),
    "three": ("RfxVoiceThreeProperties", "../voice_fx/raw/541622__steprock__video-game-count-and-more.wav", 18,
              (3.22, 3.25, 3.28), 0.025, ((250, 500), (1100, 1800), (2500, 3300), (3300, 4300))),
    "three_b": ("RfxVoiceThreeProperties", "../voice_fx/raw/541622__steprock__video-game-count-and-more.wav", 18,
                (3.46, 3.50, 3.54), 0.025, ((200, 450), (1800, 2600), (2500, 3300), (3300, 4300))),
}


def load(path):
    sr, x = wavfile.read(path)
    x = np.asarray(x, float)
    x = x.mean(1) if x.ndim > 1 else x
    x = resample_poly(x, SR, sr)
    return x / np.abs(x).max()


def poles(seg, order):
    """[(Hz, bandwidth Hz, envelope dB)] of a frame's LPC."""
    seg = seg * np.hamming(len(seg))
    r = np.correlate(seg, seg, "full")[len(seg) - 1:len(seg) + order]
    a = np.concatenate([[1.0], solve_toeplitz(r[:order], -r[1:order + 1])])
    out = []
    for z in np.roots(a):
        if np.imag(z) <= 0:
            continue
        f = np.angle(z) * SR / (2 * np.pi)
        bw = -np.log(np.abs(z)) * SR / np.pi
        h = 1.0 / np.abs(np.dot(a, np.exp(-1j * 2 * np.pi * f / SR * np.arange(len(a)))))
        out.append((f, bw, 20 * np.log10(h)))
    return out


def formants(voice, show=False):
    cname, rec, order, starts, flen, windows = VOICES[voice]
    x = load(os.path.join(R, rec))
    allp = []
    for t0 in starts:
        p = poles(x[int(t0 * SR):int((t0 + flen) * SR)], order)
        allp += p
        if show:
            print("  %.2f s  %s" % (t0, " ".join("%.0f/%.0f/%.0f" % q for q in sorted(p) if q[0] > 150 and q[1] < 800)))
    out = []
    for lo, hi in windows:
        q = [p for p in allp if lo <= p[0] < hi and p[1] < 800]
        if not q:
            continue
        f, bw, db = (float(np.median([p[k] for p in q])) for k in range(3))
        out.append((f, max(bw, BW_MIN), db))
    return cname, out


def as_modes(fs):
    """(ratio re 1 kHz, dB re the strongest, dB/s) for each (Hz, bandwidth, dB)."""
    amps = [db + 20 * math.log10(b) for f, b, db in fs]
    top = max(amps)
    return tuple((round(f / 1000.0, 4), round(a - top, 1), round(27.29 * b, 0)) for (f, b, db), a in zip(fs, amps))


# THE BARKS' CONTOURS (percussion_map.KIT_STROKES "voiced"): six dogs, each
# bark's pitch by YIN in 15 ms windows every 2.5 ms where it is within 22 dB
# of its loudest. Mostly unvoiced to YIN -- rough -- and where it holds, nearly
# level: 600 to 575, 525 to 505, 640 to 620 Hz; a Shih Tzu's rising 680 to 760
DOGS = ("100032_*.wav", "277058_*.wav", "372528_*.wav", "449490_*.wav", "495658_*.wav", "630648_*.mp3")


def yin(x, sr, fmin=150.0, fmax=2000.0, win=0.015, hop=0.0025, th=0.3):
    W, H, tmax, tmin = int(win * sr), int(hop * sr), int(sr / fmin), int(sr / fmax)
    out = []
    for i in range(0, len(x) - W - tmax, H):
        f = x[i:i + W + tmax]
        d = np.array([np.sum((f[:W] - f[t:t + W]) ** 2) for t in range(tmax + 1)])
        dn = np.ones_like(d)
        dn[1:] = d[1:] * np.arange(1, tmax + 1) / np.maximum(np.cumsum(d[1:]), 1e-12)
        k = np.flatnonzero(dn[tmin:] < th)
        if len(k):
            t = tmin + k[0]
            while t + 1 < len(dn) and dn[t + 1] < dn[t]:
                t += 1
            out.append((i / sr, sr / t))
        else:
            out.append((i / sr, float("nan")))
    return out


def contours():
    import glob
    import subprocess
    import tempfile
    for g in DOGS:
        for path in sorted(glob.glob(os.path.join(R, "dog", g))):
            with tempfile.TemporaryDirectory() as d:
                wav = os.path.join(d, "d.wav")
                subprocess.run(["sox", path, "-c", "1", "-r", "44100", "-b", "16", wav], check=True)
                sr, x = wavfile.read(wav)
            x = x / 32768.0
            w = int(0.01 * sr)
            db = 20 * np.log10(np.sqrt(np.convolve(x * x, np.ones(w) / w, "same")) / 1.0 + 1e-12)
            db -= db.max()
            ons = []
            for o in np.flatnonzero((db[1:] > -20) & (db[:-1] <= -20)):
                if not ons or o - ons[-1] > 0.25 * sr:
                    ons.append(o)
            print("== %s" % os.path.basename(path)[:40])
            for o in ons[:3]:
                a = max(0, o - int(0.01 * sr))
                seg, sdb = x[a:o + int(0.3 * sr)], db[a:o + int(0.3 * sr)]
                print("   " + " ".join("%d:%s" % (round(1000 * t), "%.0f" % f if f == f else "-")
                                      for t, f in yin(seg, sr) if sdb[min(len(sdb) - 1, int(t * sr))] > -22))


# THE BALANCE (--balance): LPC gives each formant's place and width, but a
# pulse's modes read as an impulse's (peak x bandwidth) left the bark's 1-2
# kHz 30 dB under its body where the dogs' sit ~4 under -- the strongest
# formant sits on the fundamental, tall and narrow, and the estimate leans on
# it. So each formant's level is moved by its band's error against the
# recordings', the band's power over the voice's first SPAN s re 300 Hz-1
# kHz, rendered (the key, as it plays) against recorded (these takes, each
# from its onset), four passes, the lowest band the anchor.
EDGES = (300, 1000, 2000, 4000, 8000)
TAKES = {"dog": ((("dog", "277058_*.wav"), (0.01,)), (("dog", "449490_*.wav"), (0.33, 1.44, 2.75)),
                 (("dog", "630648_*.mp3"), (0.79,)), (("dog", "100032_*.wav"), (0.02,)),
                 (("dog", "372528_*.wav"), (0.09,))),
         "laugh": ((("hohoho", "110641_*.wav"), (0.03, 0.48, 0.87, 1.24, 1.56)),),
         # the five meows' starts; the growl's six loudest bursts (its formant frames')
         "cat": ((("cat", "214759_*.wav"), (1.50, 5.70, 8.50, 10.78, 14.11)),),
         "growl": ((("growl", "122183_*.wav"), (4.44, 5.41, 6.84, 8.02, 9.85, 10.45)),)}
SPAN = {"dog": 0.12, "laugh": 0.15, "cat": 0.6, "growl": 0.4}
KEY = {"dog": 76, "laugh": 52, "cat": 85, "growl": 87}


def band_power(x, sr):
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), 1 << 15)) ** 2
    f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
    return np.array([X[(f >= a) & (f < b)].sum() for a, b in zip(EDGES[:-1], EDGES[1:])])


def recorded_balance(voice):
    import glob
    import subprocess
    import tempfile
    tot = np.zeros(len(EDGES) - 1)
    for (folder, g), ons in TAKES[voice]:
        path = sorted(glob.glob(os.path.join(R, folder, g)))[0]
        with tempfile.TemporaryDirectory() as d:
            wav = os.path.join(d, "t.wav")
            subprocess.run(["sox", path, "-c", "1", "-r", "44100", "-b", "16", wav], check=True)
            sr, x = wavfile.read(wav)
        x = x / 32768.0
        for o in ons:
            p = band_power(x[int(o * sr):int((o + SPAN[voice]) * sr)], sr)
            tot += p / p[0]
    return 10 * np.log10(tot / tot[0])


def ours_balance(voice):
    import tempfile
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(HERE, "examples"))
    os.environ.setdefault("TUNING_REFLECT", "0")
    import elkit_fit as E
    E.KIT = 56
    with tempfile.TemporaryDirectory() as d:
        x, sr = E.ours(KEY[voice], d)
    x = np.asarray(x, float)
    a = int(np.argmax(np.abs(x) > np.abs(x).max() * 0.01))
    # the laugh whole (its syllables), the bark its first SPAN
    n = int((2.1 if voice == "laugh" else SPAN[voice]) * sr)
    p = band_power(x[a:a + n], sr)
    return 10 * np.log10(p / p[0])


def balance(voice, passes=4):
    import importlib
    import tonelib as T
    cname = VOICES[voice][0]
    cls = getattr(T, cname)
    rec = recorded_balance(voice)
    print("  recorded, re 300 Hz-1 kHz: " + " ".join("%+.1f" % v for v in rec[1:]))
    for n in range(passes + 1):
        ours = ours_balance(voice)
        d = rec - ours
        print("  pass %d: ours %s  error %s" % (n, " ".join("%+.1f" % v for v in ours[1:]),
                                                " ".join("%+.1f" % v for v in d[1:])), flush=True)
        if n == passes:
            break
        modes = []
        for r, db, rate in cls.DRUM_MODES:
            k = int(np.searchsorted(EDGES, 1000.0 * r)) - 1
            modes.append((r, round(db + (float(d[k]) if 0 < k < len(d) else 0.0), 1), rate))
        cls.DRUM_MODES = tuple(modes)
    return cls.DRUM_MODES


def write_modes(cname, m, field="DRUM_MODES"):
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    i = s.index("class %s(" % cname)
    j = s.index("\n\n\n", i)
    b = re.sub(r"    %s = .*\n" % field, "    %s = %r\n" % (field, m), s[i:j] + "\n")[:-1]
    open(p, "w").write(s[:i] + b + s[j:])
    print("  wrote %s" % cname)


def tilt(voice="dog"):
    """--tilt: each take's band balance in 30 ms windows from its onset, re
    300 Hz-1 kHz -- the bark brightest ~30 ms in, darkening after
    (percussion_map.KIT_STROKES "voiced", its BRIGHT contour)."""
    import glob
    import subprocess
    import tempfile
    print("  bands %s Hz, re the first; windows from 0, 30, 60, 90, 120 ms" % "-".join(str(e) for e in EDGES[1:]))
    for (folder, g), ons in TAKES[voice]:
        path = sorted(glob.glob(os.path.join(R, folder, g)))[0]
        with tempfile.TemporaryDirectory() as d:
            wav = os.path.join(d, "t.wav")
            subprocess.run(["sox", path, "-c", "1", "-r", "44100", "-b", "16", wav], check=True)
            sr, x = wavfile.read(wav)
        x = x / 32768.0
        for o in ons:
            rows = []
            for t in (0.0, 0.03, 0.06, 0.09, 0.12):
                p = band_power(x[int((o + t) * sr):int((o + t + 0.03) * sr)], sr)
                rows.append(10 * np.log10(p[1:] / p[0]))
            print("  %-12s %.2f  %s" % (os.path.basename(path)[:12], o,
                                       " | ".join(" ".join("%+.0f" % v for v in r) for r in rows)))


def main(argv):
    if "--tilt" in argv:
        tilt()
        return 0
    if "--contours" in argv:
        contours()
        return 0
    if "--balance" in argv:
        sys.path.insert(0, HERE)
        for v in [a for a in argv[1:] if not a.startswith("--")] or list(VOICES):
            print("== %s" % v)
            m = balance(v)
            print("  DRUM_MODES = %r" % (m,))
            if "--write" in argv:
                write_modes(VOICES[v][0], m)
        return 0
    voices = [a for a in argv[1:] if not a.startswith("--")] or list(VOICES)
    for v in voices:
        print("== %s" % v)
        cname, fs = formants(v, show=True)
        print("  formants: " + "  ".join("%.0f Hz / %.0f wide / %.0f dB" % q for q in fs))
        m = as_modes(fs)
        field = "DRUM_MODES_B" if v.endswith("_b") else "DRUM_MODES"
        print("  %s = %r" % (field, m))
        if "--write" in argv:
            write_modes(cname, m, field)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
