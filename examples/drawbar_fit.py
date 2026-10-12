#!/usr/bin/env python3
"""DERIVE a recording's drawbar setting, and VALIDATE the tonewheel model on it.

    python3 examples/drawbar_fit.py [--pack=rok|tonewheel|m100] [--ab=OUT.wav]

A tonewheel organ's drawbar is one near-sine at a fixed multiple of the note
(16' 0.5, 5 1/3' 1.5, 8' 1, 4' 2, 2 2/3' 3, 2' 4, 1 3/5' 5, 1 1/3' 6, 1' 8),
and its setting is a fixed loss below 8 -- about 3 dB a step (DB_STEP). So one
note's spectrum reads off its registration, and every note of a take shares it.

  OURS, DRAWBAR BY DRAWBAR: each key rendered with each drawbar alone at 8
    (GM 16, its Leslie as on the take), the drawbar's own partial measured --
    our wheel gains, foldback and rotor, at that key.
  THE TAKE: each note's level at the nine drawbar frequencies, averaged over
    the note (a slow rotor's swing averaged out).
  SOLVE: level(note, bar) = ours(note, bar) + setting(bar) + c(note) -- the
    setting shared across the notes, a level c per note (each take is
    normalised) -- least squares; a bar the take does not sound (under
    FLOOR_DB of its loudest, on most notes) is OFF. Settings rounded to the
    nearest step.

THE VALIDATION is the residual: one integer setting explaining every note to
a few dB says the wheel gains and foldback are right; a residual that DRIFTS
across the keyboard says which bar, and where, is not.

Sources (sources.md "Organs and free reeds", CC0): hammondman's "Rok organ"
pack (17 notes G2-C6, 3 s, mostly the fast rotor -- ~18 turns a note, so the
rotors' swing averages out), his tonewheel pack (23 notes, slow rotor) and
Olichite's M100 C (no rotor). THE SLOW-ROTOR PACK CANNOT PIN A SETTING: a 1-2 s
note is about one turn, and the bass rotor (under 800 Hz) and the horn (over)
catch it at their own phases -- its 8' against its 2 2/3' swung +15 to -22 dB
note to note, where ours alone held to 3 dB. The rok pack is overdriven, so
ours is rendered with the drive off and only the drawbar frequencies read.
"""
import glob
import os
import re
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import blockrender as B  # noqa: E402
import tonelib as T  # noqa: E402
import voicefit as V  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/freesound/tonewheel")
BARS = ("16", "5-1/3", "8", "4", "2-2/3", "2", "1-3/5", "1-1/3", "1")
DB_STEP = 3.0
FLOOR_DB = -30.0          # under this, on most notes, a bar is the wheels' leakage, not pulled
NAMES = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def notes(pack):
    if pack == "rok":
        out = []
        for p in sorted(glob.glob(os.path.join(REFS, "hammondman_rok/*.wav"))):
            m = re.search(r"__([a-g])(\d)\.wav$", p)
            out.append((NAMES[m.group(1)] + 12 * (int(m.group(2)) + 1), p, 0.3, None))
        return out
    if pack == "m100":
        return [(72, glob.glob(os.path.join(REFS, "244711__*.wav"))[0], 1.0, 6.0)]
    out = []
    for p in sorted(glob.glob(os.path.join(REFS, "hammondman_tonewheel/*.wav"))):
        m = re.search(r"__([a-g])(\d)\.wav$", p)
        out.append((NAMES[m.group(1)] + 12 * (int(m.group(2)) + 1), p, 0.15, None))
    return out


def bar_freqs(f0):
    return [f0 * r for _, r, *_ in T.TonewheelProperties.stop_ranks]


def levels(x, sr, f0, t0, t1):
    """dB at each drawbar's frequency, power-averaged over 46 ms frames."""
    x = x[int(t0 * sr):int((t1 if t1 else len(x) / sr - 0.1) * sr)]
    w = 1 << 11
    hop = w // 2
    acc = None
    for i in range(0, len(x) - w, hop):
        X = np.abs(np.fft.rfft(x[i:i + w] * np.hanning(w), w * 4)) ** 2
        acc = X if acc is None else acc + X
    fr = np.fft.rfftfreq(w * 4, 1.0 / sr)
    out = []
    for f in bar_freqs(f0):
        b = np.abs(fr - f) < max(4.0, 0.015 * f)
        out.append(10 * np.log10(acc[b].max() + 1e-30) if f < 0.45 * sr and b.any() else np.nan)
    return np.array(out)


FAST = False          # the rotor on fast (the rok pack)


def render(key, secs, leslie=True, gains=None, stops=None):
    cls = T.DrawbarOrganProperties
    keep = (cls.default_stops, cls.leslie, list(T.TonewheelProperties.stop_ranks), cls.leslie_fast)
    try:
        if stops is not None:
            cls.default_stops = stops
        cls.leslie = leslie
        cls.leslie_fast = FAST
        if gains is not None:
            T.TonewheelProperties.stop_ranks = [(r[0], r[1], r[2] * g) + tuple(r[3:])
                                                for r, g in zip(keep[2], gains)]
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("program_change", channel=0, program=16, time=0))
        t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
        L, R = B.render(m)[:2]
    finally:
        cls.default_stops, cls.leslie = keep[0], keep[1]
        T.TonewheelProperties.stop_ranks = keep[2]
        cls.leslie_fast = keep[3]
    x = np.asarray(L, np.float64)                   # one mic, as the takes
    return x[np.flatnonzero(np.abs(x) > np.abs(x).max() * 0.02)[0]:], B.SR


def main(argv):
    global FAST
    pack = next((a.split("=")[1] for a in argv if a.startswith("--pack=")), "rok")
    FAST = pack == "rok"
    leslie = pack != "m100"
    tab = B.tuning_table("hybrid440")
    R, O, keys = [], [], []
    for key, p, t0, t1 in notes(pack):
        x, sr = V.mono(p)
        x = x.astype(np.float64)
        f0 = tab[key] if pack != "m100" else 525.4 / 2 ** (0 / 12)
        if pack == "m100":
            key = int(round(69 + 12 * np.log2(525.4 / 440.0)))
            f0 = 525.4
        R.append(levels(x, sr, f0, t0, t1))
        secs = (t1 or len(x) / sr) + 0.2
        row = []
        for i in range(len(BARS)):
            y, s2 = render(key, secs, leslie, stops=1 << i)
            row.append(levels(y, s2, tab[key], t0, min(t1 or 9e9, len(y) / s2 - 0.1))[i])
        O.append(row)
        keys.append(key)
    R, O = np.array(R), np.array(O)
    # which bars the take sounds: within FLOOR_DB of its loudest on most notes
    rel = R - np.nanmax(R, 1, keepdims=True)
    on = np.nanmedian(rel, 0) > FLOOR_DB
    D = R - O                                      # setting(bar) + c(note)
    c = np.zeros(len(keys))
    s = np.zeros(len(BARS))
    for _ in range(50):                             # alternate: per-note level, per-bar setting
        s[on] = np.nanmedian(D[:, on] - c[:, None], 0)
        c = np.nanmedian(D[:, on] - s[on][None, :], 1)
    top = s[on].max()
    steps = np.where(on, np.clip(np.round(8 + (s - top) / DB_STEP), 0, 8), 0).astype(int)
    print("  %s: %d notes; drawbar setting (16 5 8 4 2.7 2 1.6 1.3 1):  %s"
          % (pack, len(keys), "".join(str(v) for v in steps)))
    print("  continuous, dB re the loudest bar:  " + "  ".join(
        "%s %+.1f" % (b, s[i] - top) if on[i] else "%s off" % b for i, b in enumerate(BARS)))
    fit = O + (top + (steps - 8) * DB_STEP)[None, :] + c[:, None]
    res = R - fit
    print("  residual by bar (rms over notes, dB):  " + "  ".join(
        "%s %.1f" % (b, np.sqrt(np.nanmean(res[:, i] ** 2))) for i, b in enumerate(BARS) if on[i]))
    print("  residual overall rms %.2f dB (sounded bars)" % np.sqrt(np.nanmean(res[:, on] ** 2)))
    if len(keys) > 3:
        for i, b in enumerate(BARS):
            if on[i]:
                ok = np.isfinite(res[:, i])
                sl = np.polyfit((np.array(keys)[ok] - 60) / 12.0, res[ok, i], 1)[0]
                print("    %-6s drift %+5.1f dB/octave   by key: %s" % (b, sl, " ".join(
                    "%d:%+.0f" % (k, v) for k, v in zip(keys, res[:, i]))))
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        ab(out, pack, steps, leslie)
    return steps


def ab(out, pack, steps, leslie):
    """Each take, then ours AT THE DERIVED SETTING, level-matched."""
    import wave
    from scipy.signal import resample_poly
    SR = 44100
    gains = [10 ** ((v - 8) * DB_STEP / 20.0) if v else 0.0 for v in steps]
    stops = sum(1 << i for i, v in enumerate(steps) if v)
    parts = []
    gap = np.zeros(int(0.35 * SR))
    sel = notes(pack)
    sel = sel if len(sel) < 8 else [sel[int(i)] for i in np.linspace(0, len(sel) - 1, 7)]
    for key, p, t0, t1 in sel:
        x, sr = V.mono(p)
        x = resample_poly(x.astype(np.float64), SR, sr)
        k = key if pack != "m100" else 72
        y, s2 = render(k, len(x) / SR, leslie, gains=gains, stops=stops)
        y = resample_poly(y, SR, s2)[:len(x) + int(0.2 * SR)]
        y *= np.sqrt(np.mean(x ** 2) / max(np.mean(y[:len(x)] ** 2), 1e-30))
        parts += [x, gap, y, gap, gap]
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


if __name__ == "__main__":
    main(sys.argv)
