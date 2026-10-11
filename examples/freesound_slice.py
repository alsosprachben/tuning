#!/usr/bin/env python3
"""Cut a Freesound take of many hits into one file a hit, sorted by drum, for
examples/perc_fit.py to read as it reads VSCO's one-stroke files.

    python3 examples/freesound_slice.py timbales
    python3 examples/freesound_slice.py surdo
    python3 examples/freesound_slice.py pipes
    python3 examples/freesound_slice.py bagpipe

TIMBALES: hello_flowers' "50 Timbales Hits" (freesound 41196, CC0; ~/Documents/
refs/sources.md), one 75 s mp3 decoded to float. 53 onsets (a rise of 20 dB in
10 ms, peaking over -30 dB, 0.15 s apart). Read from 20-200 ms, TWO DRUMS, each
at two pitches interleaved through the take: the high drum's lowest mode at
224 or 241 Hz, the low's at 186 or 197, a minor third apart both ways. The
upper pitch of each is the shorter (the high drum -40 dB by 0.22 s against
0.35-0.5): a stroke that presses the head, raising it ~6% and damping it.
The free strokes are taken -- the drum ringing as GM's open timbale does:
high 218-230 Hz (GM 65), low 182-190 (GM 66), the lowest mode within 12 dB of
the hit's strongest peak (an edge stroke that barely moves the head is not
that drum's ring). Each hit runs to the next onset (at most 1.2 s), written
stereo float into
~/Documents/refs/freesound/timbales/hits/{high,low}_<n>.wav.

SURDO: plotzki's "X Surdo 4Bar D" (freesound 36127, CC0), a samba surdo at
67 Hz, 48 kHz mono, four bars of its pattern -- with a second, higher drum
(~120 Hz) answering, left out. Its own strokes are of three kinds, told
apart by the 55-80 Hz band's fall:

  open    left to ring to the next beat (0.55 s): -10 dB at 0.3 s
  first   of a pair, the same ring, cut 0.19 s later by...
  second  ...the muted stroke: it holds -5 dB for 150 ms, then the hand is
          down and it falls 20-45 dB by 0.3 s

Open (GM 87) are the strokes 0.45 s and more from the next; mute (GM 86) the
second of a pair (0.25 s and less after the one before) with 0.3 s to the
next. Every stroke peaks over -25 dB (the take opens on a -32 dB pickup)
and its 55-80 Hz band stays under its first 60 ms' peak from 60 to 150 ms
(one in the fourth bar swells 3 dB there: another stroke on it). Mono, written as a
stereo pair of the same channel into ~/Documents/refs/freesound/surdo/hits/
{open,mute}_<n>.wav.

PIPES (GM 75-78; ~/Documents/refs/sources.md "Pipes"): the pan flute, blown
bottle, shakuhachi and whistle takes are scales, melodies and held tones, not
one note a file, so each is pitch-tracked (YIN, 10 ms) and its STABLE notes
cut out: a run of frames periodic (aperiodicity < 0.2), within 25 dB of the
take's loudest and within 35 cents of their own median for at least a
voice's MIN_LEN, cut 50 ms either side. Written (16-bit PCM, each at its own
peak) as <note><octave>_<take>_<n>.wav
under ~/Documents/refs/freesound/staged/<voice>/, the note the nearest to its
median pitch -- the sounding pitch, as examples/wind_fit.py reads it.
"""
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/freesound")


def onsets(x, sr, rise_db=20.0, top_db=-30.0, gap=0.15):
    w = int(0.002 * sr)
    edb = 10 * np.log10(np.convolve(x * x, np.ones(w) / w, "same") + 1e-20)
    lag = int(0.01 * sr)
    out = []
    for i in np.flatnonzero(edb[lag:] - edb[:-lag] > rise_db) + lag:
        if (not out or i - out[-1] > int(gap * sr)) and edb[i:i + lag].max() > top_db:
            out.append(int(i))
    return out


def lowest_mode(x, sr, lo=150.0, hi=300.0):
    """The strongest peak in lo-hi Hz, 20-200 ms after the onset (the head's
    lowest mode), and its level in dB re the strongest peak to 3 kHz."""
    seg = x[int(0.02 * sr):int(0.2 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16))
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    b = (f > lo) & (f < hi)
    i = np.argmax(X[b])
    return float(f[b][i]), float(20 * np.log10(X[b][i] / X[(f > lo) & (f < 3000)].max()))


def timbales():
    from scipy.io import wavfile
    src = os.path.join(REFS, "timbales", "41196__hello_flowers__50-timbales-hits.mp3")
    out = os.path.join(REFS, "timbales", "hits")
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "t.wav")
        subprocess.run(["sox", src, "-e", "floating-point", "-b", "32", wav], check=True,
                       stderr=subprocess.DEVNULL)
        a, sr = read(wav)
    x = a.sum(1)
    on = onsets(x, sr) + [len(x)]
    n = {"high": 0, "low": 0}
    for s, t in zip(on[:-1], on[1:]):
        if t - s < int(0.5 * sr):
            continue                  # a hit cut short by the next
        f1, db = lowest_mode(x[s:], sr)
        drum = "high" if 218 <= f1 <= 230 else "low" if 182 <= f1 <= 190 else None
        if drum is None or db < -12.0:
            continue
        pre = int(0.005 * sr)
        seg = a[max(0, s - pre):s + min(t - s, int(1.2 * sr)) - pre].astype(np.float32)
        n[drum] += 1
        wavfile.write(os.path.join(out, "%s_%02d.wav" % (drum, n[drum])), sr, seg)
        print("%s_%02d  t=%6.2f s  lowest mode %5.1f Hz (%+.0f dB)" % (drum, n[drum], s / sr, f1, db))
    print(n, "->", out)


def surdo():
    from scipy.io import wavfile
    src = os.path.join(REFS, "surdo", "36127__plotzki__x-surdo-4bar-d.aiff")
    out = os.path.join(REFS, "surdo", "hits")
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "s.wav")
        # padded: the take's first stroke starts in its first sample
        subprocess.run(["sox", src, "-e", "floating-point", "-b", "32", "-c", "2", wav, "pad", "0.05", "0"],
                       check=True, stderr=subprocess.DEVNULL)
        a, sr = read(wav)
    x = a.sum(1)
    on = onsets(x, sr, top_db=-25.0)
    from scipy.signal import butter, sosfiltfilt
    y = sosfiltfilt(butter(2, [55.0, 80.0], btype="band", fs=sr, output="sos"), x)
    w = int(0.005 * sr)
    band = 10 * np.log10(np.convolve(y * y, np.ones(w) / w, "same") + 1e-20)
    n = {"open": 0, "mute": 0}
    for k, s in enumerate(on):
        t = on[k + 1] if k + 1 < len(on) else len(x)
        f1, db = lowest_mode(x[s:], sr, 50.0, 90.0)
        if not 60.0 <= f1 <= 75.0:
            continue                  # the higher drum
        if band[s + int(0.06 * sr):s + int(0.15 * sr)].max() > band[s:s + int(0.06 * sr)].max():
            continue                  # another stroke on it
        if t - s >= int(0.45 * sr):
            kind = "open"
        elif k and s - on[k - 1] <= int(0.25 * sr) and t - s >= int(0.3 * sr):
            kind = "mute"
        else:
            continue                  # the first of a pair, cut short
        pre = int(0.005 * sr)
        seg = a[max(0, s - pre):s + min(t - s, int(1.2 * sr)) - pre].astype(np.float32)
        n[kind] += 1
        wavfile.write(os.path.join(out, "%s_%02d.wav" % (kind, n[kind])), sr, seg)
        print("%s_%02d  t=%6.2f s  %.2f s to the next  lowest mode %5.1f Hz" % (kind, n[kind], s / sr, (t - s) / sr, f1))
    print(n, "->", out)


NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# voice: [(take glob under REFS, its tag, fmin, fmax, MIN_LEN s)]
PIPES = {
    "bottle": [("bottle/sadiquecat/*.wav", "sadiq", 100, 600, 2.5),
               ("bottle/cabled_mess/*.wav", "cabled", 100, 600, 0.8)],
    "panflute": [("panflute/278175__*.wav", "mrshoes", 200, 1500, 0.5),
                 ("panflute/84748__*.wav", "j008b", 200, 1500, 0.4),
                 ("panflute/427080__*.wav", "zanka", 100, 400, 0.6)],
    "shakuhachi": [("shakuhachi/61498__*.wav", "uncle", 150, 1200, 0.8),
                   ("shakuhachi/486487__*.wav", "gonzooka", 150, 1200, 0.8)],
    "whistle": [("whistle/233569__*.aiff", "nbild", 500, 3000, 1.0),
                ("whistle/790454__*.wav", "oscar", 500, 3000, 0.2)],
}


def track(x, sr, fmin, fmax, hop=0.01, win=0.04):
    """(f0, aperiodicity, level dB) per hop: YIN's cumulative-mean-normalised
    difference, the difference function from an FFT autocorrelation."""
    n, h = int(win * sr), int(hop * sr)
    tmin, tmax = int(sr / fmax), min(int(sr / fmin), n // 2)
    out = []
    for i in range(0, len(x) - n, h):
        seg = x[i:i + n] - x[i:i + n].mean()
        W = n // 2
        a = seg[:W]
        e = np.cumsum(np.concatenate(([0.0], seg * seg)))
        F = np.fft.rfft(seg, 2 * n)
        A = np.fft.rfft(a, 2 * n)
        cc = np.fft.irfft(np.conj(A) * F, 2 * n)[:W + 1]
        t = np.arange(W + 1)
        d = e[W] + (e[t + W] - e[t]) - 2 * cc
        d[0] = 0.0
        c = np.cumsum(d[1:])
        dn = np.ones_like(d)
        dn[1:] = d[1:] * np.arange(1, W + 1) / np.maximum(c, 1e-20)
        # THE FIRST DIP UNDER 0.15, then down to its own minimum -- YIN's rule.
        # The deepest one is not the period: a near-sine (a bottle, a whistle)
        # dips as low at every multiple of it, and the tracker leapt octaves
        # (121 against 253 Hz on a bottle), breaking every run it was in
        under = np.flatnonzero(dn[tmin:tmax] < 0.15)
        if len(under):
            k = tmin + int(under[0])
            while k + 1 < tmax and dn[k + 1] < dn[k]:
                k += 1
        else:
            k = tmin + int(np.argmin(dn[tmin:tmax]))
        if 0 < k < W:
            y0, y1, y2 = dn[k - 1:k + 2]
            dd = y0 - 2 * y1 + y2
            kf = k + (0.5 * (y0 - y2) / dd if dd > 0 else 0.0)
        else:
            kf = k
        out.append((sr / kf, float(dn[k]), 10 * np.log10(np.mean(seg * seg) + 1e-20)))
    return np.array(out)


def pipes():
    from scipy.io import wavfile
    for voice, takes in PIPES.items():
        out = os.path.join(REFS, "staged", voice)
        os.makedirs(out, exist_ok=True)
        for f in glob.glob(os.path.join(out, "*.wav")):
            os.remove(f)
        n = 0
        for pat, tag, fmin, fmax, min_len in takes:
            for src in sorted(glob.glob(os.path.join(REFS, pat))):
                with tempfile.TemporaryDirectory() as d:
                    wav = os.path.join(d, "t.wav")
                    subprocess.run(["sox", src, "-e", "floating-point", "-b", "32", "-c", "1", wav],
                                   check=True, stderr=subprocess.DEVNULL)
                    a, sr = read(wav)
                x = a if a.ndim == 1 else a.mean(1)
                T = track(x, sr, fmin, fmax)
                ok = (T[:, 1] < 0.2) & (T[:, 2] > T[:, 2].max() - 25.0)
                k = 0
                while k < len(T):
                    if not ok[k]:
                        k += 1
                        continue
                    j = k
                    while j + 1 < len(T) and ok[j + 1] and abs(1200 * np.log2(T[j + 1, 0] / np.median(T[k:j + 1, 0]))) < 35:
                        j += 1
                    if (j - k + 1) * 0.01 >= min_len:
                        f0 = float(np.median(T[k:j + 1, 0]))
                        midi = int(round(69 + 12 * np.log2(f0 / 440.0)))
                        a0, a1 = max(0, int((k * 0.01 - 0.05) * sr)), int(((j + 1) * 0.01 + 0.09) * sr)
                        name = "%s%d_%s_%d.wav" % (NAMES[midi % 12], midi // 12 - 1, tag, n)
                        # 16-bit PCM, each at its own peak: voicefit's reader takes PCM
                        # only, and a note's level is no part of a spectral fit
                        seg = x[a0:a1]
                        seg = seg / max(np.abs(seg).max(), 1e-9) * 0.9
                        wavfile.write(os.path.join(out, name), sr, (seg * 32767).astype(np.int16))
                        n += 1
                    k = j + 1
        print("%-10s %3d stable notes -> %s" % (voice, n, out))


# THE CHANTER'S NINE NOTES, by the note a file plays them at: BagpipeProperties'
# scale_cents is degrees of Low A = MIDI 69, so Low G is 67 and High A 81
CHANTER = {"low-g": "G4", "low-a": "A4", "b": "B4", "c": "C#5", "d": "D5",
           "e": "E5", "f": "F#5", "high-g": "G5", "high-a": "A5"}


def bagpipe():
    """IowaSpaceWizard's chanter notes (sources.md "Ethnic programs"; CC0): MP3s
    of one held note each, ~4.5 s of it and the rest of the 31 s silence.
    Decoded (lame), cut to where it sounds (within 40 dB of its peak, 50 ms
    either side) and named by the note that plays it -- the WRITTEN note: this
    chanter's Low A is 487 Hz, which examples/wind_fit.py renders at by a
    static bend (VOICE_OPTS tonic_cents). The drones' take staged beside them
    whole, as drones.wav."""
    from scipy.io import wavfile
    out = os.path.join(REFS, "staged", "bagpipe")
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*.wav")):
        os.remove(f)
    for src in sorted(glob.glob(os.path.join(REFS, "bagpipe/iowaspacewizard/*.mp3"))):
        nm = next((k for k in sorted(CHANTER, key=len, reverse=True) if src.endswith("chanter-%s.mp3" % k)), None)
        if nm is None and not src.endswith("drones.mp3"):
            continue
        with tempfile.TemporaryDirectory() as d:
            wav = os.path.join(d, "t.wav")
            subprocess.run(["lame", "--quiet", "--decode", src, wav], check=True)
            sr, a = wavfile.read(wav)
        x = (a if a.ndim == 1 else a.mean(1)).astype(np.float64)
        w = int(0.01 * sr)
        e = 10 * np.log10(np.convolve(x * x, np.ones(w) / w, "same") + 1e-20)
        on = np.flatnonzero(e > e.max() - 40.0)
        seg = x[max(0, on[0] - int(0.05 * sr)):on[-1] + int(0.05 * sr)]
        seg = seg / max(np.abs(seg).max(), 1e-9) * 0.9
        name = "drones.wav" if nm is None else "%s_iowa_%s.wav" % (CHANTER[nm], nm)
        wavfile.write(os.path.join(out, name), sr, (seg * 32767).astype(np.int16))
        print("  %-22s %.2f s" % (name, len(seg) / sr))


if __name__ == "__main__":
    {"timbales": timbales, "surdo": surdo, "pipes": pipes, "bagpipe": bagpipe}[sys.argv[1]]()
