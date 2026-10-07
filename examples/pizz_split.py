#!/usr/bin/env python3
"""Iowa's pizzicato runs, split into one file per note for voicefit.py.

    python3 examples/pizz_split.py [RAW_DIR] [OUT_DIR]

RAW_DIR (default ~/Documents/refs/pizz/raw) holds the Iowa MIS pizzicato
files as downloaded -- Violin.pizz.mf.sulG.G3B3.aiff and the like: one string,
a run of plucks with silence between.

THE FILENAME'S RANGE IS NOT A COUNT. The first version named the k-th onset
the k-th semitone of the range the filename gives, and half the files refused:
the violin's E5Ab5 holds eight plucks for a five-note name, the viola's C4B4
ten for twelve. So every pluck is named by its OWN pitch, the filename's range
serving only to bound the search:

  plucks    peaks of a 10 ms RMS envelope standing 12 dB proud of what is
            around them, at most 25 dB under the file's loudest -- which drops
            the handling noises between notes, 30-45 dB down.
  pitch     autocorrelation over the first 300 ms after the attack, searched
            from a fifth under the range to a fifth over it, and the SHORTEST
            period that correlates within 10% of the best: a window that spans
            an octave holds two periods of a high note, and the longer one
            correlates as well. (voicefit.detect_f0 has no prior, and at a
            bass pizz it sat on the window's edge and reported nonsense.)
  name      the nearest semitone, kept only within 50 cents of one and
            within two semitones of the range the name gives (the count is
            often wrong, the range only by a note or two); a note already
            taken in this file keeps its first pluck.

Writes OUT_DIR/<instrument>/<note>.<string>.wav, mono, 32-bit, the note where
voicefit.note_of finds it. A note played on two strings keeps both: the
stopped length differs, so the pluck lands at a different fraction of the
string, which is one of the things being measured.
"""
import glob
import math
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from roomtail import read_wav, write_wav  # noqa: E402

NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
PC = {'C': 0, 'Db': 1, 'D': 2, 'Eb': 3, 'E': 4, 'F': 5, 'Gb': 6, 'G': 7, 'Ab': 8,
      'A': 9, 'Bb': 10, 'B': 11}
RANGE = re.compile(r'\.([A-G]b?)(\d)(?:([A-G]b?)(\d))?\.aiff?$')
STRING = re.compile(r'sul([A-G])')


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def note_name(m):
    return "%s%d" % (NAMES[m % 12], m // 12 - 1)


def read(path):
    t = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    subprocess.run(["sox", path, "-c", "1", "-b", "32", "-e", "signed-integer", t], check=True)
    x, sr = read_wav(t)
    os.remove(t)
    return (x.mean(axis=1) if x.ndim > 1 else x), sr


def plucks(x, sr):
    """(start, peak) sample indices of each pluck."""
    from scipy.signal import find_peaks
    w = int(0.01 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, 'same'))[::w]
    db = 20 * np.log10(e / e.max() + 1e-9)
    p, _ = find_peaks(db, height=-25, prominence=12, distance=int(0.15 * sr / w))
    out = []
    for i in p:
        j = i
        while j > 0 and i - j < 10 and db[j - 1] > db[i] - 20:   # back to the rise
            j -= 1
        out.append((max(0, (j - 1) * w), i * w))
    return out


def pitch(seg, sr, lo, hi):
    y = seg - seg.mean()
    n = 1 << int(math.ceil(math.log2(len(y) * 2)))
    ac = np.fft.irfft(np.abs(np.fft.rfft(y, n)) ** 2)[:len(y)]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]
    k0, k1 = max(2, int(sr / hi)), min(int(sr / lo), len(ac) - 2)
    if k1 <= k0 + 2:
        return None
    k = k0 + int(np.argmax(ac[k0:k1]))
    best = ac[k]
    for d in (4, 3, 2):                     # the shortest period that holds up
        kk = int(round(k / float(d)))
        if kk > k0:
            j = kk - 2 + int(np.argmax(ac[kk - 2:kk + 3]))
            if ac[j] >= 0.9 * best:
                k = j
                break
    a, b, c = ac[k - 1], ac[k], ac[k + 1]
    den = a - 2 * b + c
    kf = k + ((a - c) / (2 * den) if den != 0 else 0.0)
    return sr / kf if kf > 0 else None


def split(path, outdir):
    m = RANGE.search(os.path.basename(path))
    s = STRING.search(os.path.basename(path))
    if not m or not s:
        return "no range or string in the name"
    lo = (int(m.group(2)) + 1) * 12 + PC[m.group(1)]
    hi = (int(m.group(4)) + 1) * 12 + PC[m.group(3)] if m.group(3) else lo
    x, sr = read(path)
    pl = plucks(x, sr)
    got, off = {}, 0
    for k, (i, p) in enumerate(pl):
        j = pl[k + 1][0] if k + 1 < len(pl) else len(x)
        f = pitch(x[p + int(0.02 * sr): p + int(0.32 * sr)], sr, hz(lo) / 1.5, hz(hi) * 1.5)
        if not f:
            off += 1
            continue
        mf = 69 + 12 * math.log2(f / 440.0)
        n = int(round(mf))
        # ...and near the range the name gives: the count is wrong in half the
        # files, the range only by a semitone or two, so a pitch an octave
        # away is the autocorrelation's error and not the player's
        if abs(mf - n) > 0.5 or n in got or not lo - 2 <= n <= hi + 2:
            off += 1
            continue
        got[n] = (i, j, 100 * (mf - n))
    for n, (i, j, c) in got.items():
        seg = x[max(0, i - int(0.01 * sr)): j - int(0.01 * sr)]
        write_wav(os.path.join(outdir, "%s.sul%s.wav" % (note_name(n), s.group(1))),
                  np.ascontiguousarray(seg, dtype=np.float32)[:, None], sr)
    names = [note_name(n) for n in sorted(got)]
    cents = [c for _, _, c in got.values()]
    return "%2d plucks, %2d notes %s-%s (named %s-%s), %+.0f c mean%s" % (
        len(pl), len(got), names[0] if names else "-", names[-1] if names else "-",
        note_name(lo), note_name(hi), float(np.mean(cents)) if cents else 0.0,
        ", %d unnamed" % off if off else "")


def main(argv):
    raw = argv[1] if len(argv) > 1 else os.path.expanduser("~/Documents/refs/pizz/raw")
    out = argv[2] if len(argv) > 2 else os.path.expanduser("~/Documents/refs/pizz")
    for p in sorted(glob.glob(os.path.join(raw, "*.aif*"))):
        inst = os.path.basename(p).split(".")[0].lower()
        d = os.path.join(out, inst)
        os.makedirs(d, exist_ok=True)
        print("  %-34s %s" % (os.path.basename(p), split(p, d)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
