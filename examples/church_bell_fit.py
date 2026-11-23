#!/usr/bin/env python3
"""GS 14.8 "Church Bell" (tonelib.ChurchBellProperties): its modes read off
one strike of a church bell, and ours read the same way.

    python3 -I examples/church_bell_fit.py [--write] [--passes=N]
    python3 -I examples/church_bell_fit.py ab OUT.wav   the strike, then ours

THE BELL (since 2026-11-22; St Kathrin's, the first, is Pianobook's and no
longer read: licences.md L7): the lowest of the four tower bells at Bethesda
Church, Saratoga Springs NY, "rung once softly by rope", an SM58 in the tower
(HMTSCCSound, Freesound 554655, CC0; ~/Documents/refs/church_bells/
bethesda_low_bell.wav): one strike, a 30 s ring-out.

THE STRIKE NOTE is half the NOMINAL (the partial a bell is named by an octave
over), here 624.8 Hz: the strike D#4 at 312.4. Against it the bell reads as a
bell does -- a flat HUM (0.558), the prime/tierce region (1.16), the nominal
(2.0), the superquint (3.03) and the clang above, 4.2 the strongest.

Each mode: its ratio (the strike window's peak, 0.05-0.6 s, or the tail's,
3-8 s, for a mode only the tail shows), and from its band's envelope over
0.25 s windows a line in dB -- its level at the strike (re the strongest) and
its decay, dB/s. Ours rendered at the strike note and read the same way: each
mode's LEVEL moved by what ours misses (--passes); its decay is the take's,
read the same way (the decay is printed for both, a check).
"""
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)
from timpani_fit import analytic_env  # noqa: E402

TAKE = os.path.expanduser("~/Documents/refs/church_bells/bethesda_low_bell.wav")
NOMINAL = 624.8
STRIKE = NOMINAL / 2.0
MAX_MODES = 20
PROGRAM, BANK = 14, 8


def load(path=TAKE):
    from scipy.io import wavfile
    sr, y = wavfile.read(path)
    y = np.asarray(y, float)
    y = y.mean(1) if y.ndim > 1 else y
    y /= np.abs(y).max()
    t0 = int(np.argmax(np.abs(y) > 0.2))
    return y[max(0, t0 - int(0.01 * sr)):], sr


def peaks(x, sr, a, b, floor_db, lo=60.0, hi=8000.0):
    seg = x[int(a * sr):int(b * sr)]
    N = 1 << 19
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    D = 20 * np.log10(S / S.max() + 1e-12)
    return [(float(f[i]), float(D[i])) for i in range(3, len(S) - 3)
            if S[i] == S[i - 3:i + 4].max() and D[i] > floor_db and lo < f[i] < hi]


def find_modes(x, sr):
    """the bell's modes: the strike's peaks (0.05-1.5 s, fine enough to part
    the hum from its neighbours) and the tail's (3-8 s) -- none under the HUM
    (the lowest strong partial of the tail: a bell has nothing below it; what
    is there is the rope and the tower), none within 6% of a stronger one
    (the hum's sidebands, a window's spread)"""
    tail = peaks(x, sr, 3.0, 8.0, -12.0)
    hum = min(f for f, _ in tail)
    cand = [(f, d) for f, d in peaks(x, sr, 0.05, 1.5, -48.0, hi=12000.0) + peaks(x, sr, 3.0, 8.0, -30.0)
            if f > 0.97 * hum]
    keep = []
    for f, d in sorted(cand, key=lambda p: -p[1]):
        if all(abs(f / g - 1) > 0.06 for g, _ in keep):
            keep.append((f, d))
    return sorted(f for f, _ in keep[:MAX_MODES])


def mode_line(x, sr, fm, t1=12.0, drop=30.0, win=0.05):
    """(level dB at the strike, decay dB/s): a line through the mode's band's
    envelope in 50 ms windows from 0.05 s, until it has fallen `drop` dB or
    come within 8 dB of the band's FLOOR (its 10th percentile over the whole
    span). A fast mode drops into its neighbours' leakage within 0.2 s; one
    line through 0.25 s windows read that floor's slow fall as the mode's --
    6-9 dB/s for modes of 30 and more, in the take and in ours alike."""
    wd = max(1.5, 0.0035 * fm)
    e = analytic_env(x, sr, fm - wd, fm + wd)
    w = int(win * sr)
    t = np.arange(int(0.05 * sr), min(len(e) - w, int(t1 * sr)), w)
    db = np.array([20 * np.log10(np.sqrt(np.mean(e[i:i + w] ** 2)) + 1e-12) for i in t])
    floor = float(np.percentile(db, 10))
    stop = np.flatnonzero((db < db[0] - drop) | (db < floor + 8.0))
    n = max(3, int(stop[0]) if len(stop) else len(db))
    tt = (t[:n] + w / 2) / sr
    k, c = np.polyfit(tt, db[:n], 1)
    return float(c), float(-k)


def read(x, sr, freqs):
    rows = [(f,) + mode_line(x, sr, f) for f in freqs]
    top = max(r[1] for r in rows)
    return [(f, lv - top, dec) for f, lv, dec in rows]


def render_ours(seconds=12.0):
    import mido
    import blockrender as B
    k = 69 + 12 * np.log2(STRIKE / 440.0)
    key = int(round(k))
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("control_change", channel=0, control=0, value=BANK, time=0))
    t.append(mido.Message("program_change", channel=0, program=PROGRAM, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(seconds * 960)))
    L, R = B.render(m)[:2]
    y = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    t0 = int(np.argmax(np.abs(y) > 0.2 * np.abs(y).max()))
    y = y[max(0, t0 - int(0.01 * B.SR)):]
    # THE PITCH IT PLAYED, read off its own nominal: the render's tuning puts
    # the key ~10 cents off equal temperament, wider than a mode's band (0.35%)
    # -- read at the nominal pitch the bands caught only the partials' skirts
    nom = 2.0 * 440.0 * 2 ** ((key - 69) / 12.0)
    seg = y[int(0.3 * B.SR):int(4.3 * B.SR)]
    N = 1 << 20
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / B.SR)
    b = (f > nom * 0.97) & (f < nom * 1.03)
    return y, B.SR, float(f[b][np.argmax(S[b])]) / 2.0


def table_text(modes):
    return "\n".join("        (%.3f, 0.0, %.1f, 0.0, %.1f)," % m for m in modes)


def write(modes):
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    a = s.index("class ChurchBellProperties(")
    b = s.index("\nclass ", a + 10)
    body = s[a:b]
    body = re.sub(r"    TUBE_MODES = \(\n.*?\n    \)\n", lambda _: "    TUBE_MODES = (\n%s\n    )\n" % table_text(modes),
                  body, count=1, flags=re.S)
    body = re.sub(r"^    TUBE_REF_HZ = .*$", "    TUBE_REF_HZ = %.1f" % STRIKE, body, count=1, flags=re.M)
    open(p, "w").write(s[:a] + body + s[b:])


def main(argv):
    x, sr = load()
    freqs = find_modes(x, sr)
    rec = read(x, sr, freqs)
    print("THE TAKE: %d modes, strike %.1f Hz (ratio, dB re the strongest, dB/s)" % (len(rec), STRIKE))
    for f, lv, dec in rec:
        print("  %8.1f Hz  %6.3f  %6.1f dB  %6.1f dB/s" % (f, f / STRIKE, lv, dec))
    if argv[1:2] == ["ab"]:
        return ab(argv[2])
    import tonelib as T
    cls = T.ChurchBellProperties
    modes = [(round(f / STRIKE, 3), round(lv, 1), round(dec, 1)) for f, lv, dec in rec]
    passes = int(next((a.split("=")[1] for a in argv if a.startswith("--passes=")), 3))
    for it in range(passes + 1):
        cls.TUBE_MODES = tuple((r, 0.0, lv, 0.0, dec) for r, lv, dec in modes)
        cls.TUBE_REF_HZ = STRIKE
        cls.mode_ratios = tuple(m[0] for m in cls.TUBE_MODES)
        cls.max_harmonic = len(cls.TUBE_MODES)
        y, ysr, played = render_ours()
        ours = read(y, ysr, [r * played for r, _, _ in modes])
        dl = [rl - ol for (_, rl, _), (_, ol, _) in zip(rec, ours)]
        dd = [np.log(max(od, 0.1) / max(rd, 0.1)) for (_, _, rd), (_, _, od) in zip(rec, ours)]
        print("  pass %d: level rms %.1f dB, decay log-rate rms %.2f" % (
            it, float(np.sqrt(np.mean(np.square(dl)))), float(np.sqrt(np.mean(np.square(dd))))), flush=True)
        if it == passes:
            break
        # THE LEVELS only. The decays stay the take's: the engine plays a slow
        # mode's table rate 1:1 (the hum: table 1.0, ours 1.0, the take 1.0),
        # and a fast one dies within three 50 ms windows on both sides alike,
        # so the reader sees ~25 dB/s for anything faster -- fed back through
        # the render, a 32 dB/s mode's table climbed past 250 and the slow
        # 1.16 swung to 0.1.
        modes = [(r, round(lv + 0.8 * d, 1), dec) for (r, lv, dec), d in zip(modes, dl)]
    print("    TUBE_MODES = (\n%s\n    )" % table_text([(r, lv, dec) for r, lv, dec in modes]))
    if "--write" in argv:
        write([(r, lv, dec) for r, lv, dec in modes])
        print("  written to tonelib.ChurchBellProperties")


def ab(out):
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    x, sr = load()
    y, ysr, _ = render_ours(30.0)
    if sr != ysr:
        x = resample_poly(x, ysr, sr)
    n = min(len(x), int(30 * ysr))
    x, y = x[:n] / np.abs(x[:n]).max(), y[:n] / np.abs(y[:n]).max()
    z = np.concatenate([x, np.zeros(int(1.0 * ysr)), y]) * 0.7
    wavfile.write(out, ysr, (np.stack([z, z], 1) * 32767).astype(np.int16))
    print("written", out)


if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
