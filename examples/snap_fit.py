#!/usr/bin/env python3
"""Fit the finger snap (GS Standard key 26; tonelib.FingerSnapProperties) to
Freesound's CC0 snaps (~/Documents/refs/fingersnap/raw, sources.md).

    snap_fit.py              measure: recorded against ours
    snap_fit.py --takes      each take's snaps, which are kept and why
    snap_fit.py --fit        the strike's colour, third octave by third octave
    snap_fit.py --ab=OUT.wav [--room=studio]
                             the kept snaps, then as many of ours (in a room)

A SNAP IS ONE HAND'S CLAP: the middle finger slapping the palm, a single
burst of noise dying in a few ms -- where the hand clap (clap_fit.py) is
several hands' bursts over 60 ms. Its colour a hump at 2-2.7 kHz (some
takes 1.5-1.7), 4-8 kHz a few dB under it, under 1 kHz 15-30 dB down. So
the clap's model with strike_flam = 1: the hammer's strike rows (tonelib
strike_noise_db) fired once.

Which strikes are snaps: a take's peaks within 25 dB of its loudest, kept
when their spectrum peaks at 1.3-3.5 kHz -- the 300 Hz thumps in two takes
are the hand or the desk, not the snap. The colour is read over the first
25 ms, before the rooms arrive (the Unicornaphobist take rings ~400 ms of
room, whose echoes are no strikes: a strike rises 15 dB in 5 ms); the fall
from -6 to -26 dB after the peak.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

REFS = os.path.expanduser("~/Documents/refs/fingersnap/raw")
NOTE = 26
WIN_S = 0.025
E3 = 2 ** np.arange(np.log2(45), np.log2(16000), 1 / 3.0)
CEN = np.sqrt(E3[:-1] * E3[1:])
# zmobie's take starts inside its snap (the first sample at full level);
# bassimat's series tires (Ben, on the A/B: "the first 3 snaps sounding good,
# then it seems like the person gets tired and they change"): its seven peak
# at 1.5-1.7 kHz where the crisp snaps do at 2.0-2.6, and fall 800-1500 dB/s
# where they do 7-9 thousand -- seven of eleven, they had made the mean theirs
SKIP = ("319812", "824675")


def load(p):
    import subprocess
    import tempfile
    from scipy.io import wavfile
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "x.wav")
        subprocess.run(["sox", p, "-r", "44100", "-b", "32", "-e", "float", w, "remix", "-"], check=True)
        sr, x = wavfile.read(w)
    return x.astype(np.float64), sr


def peaks(x, sr):
    from scipy.signal import find_peaks
    e = np.convolve(x * x, np.ones(64) / 64, "same")
    env = 10 * np.log10(e + 1e-12)
    pk, _ = find_peaks(env, height=env.max() - 25, distance=int(0.15 * sr))
    # a strike rises 15 dB in 5 ms; a room's echo of one does not
    d = int(0.005 * sr)
    return [i for i in pk if i >= d and env[i] - env[i - d] >= 15.0]


def peak_hz(seg, sr):
    N = 8192
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    S = np.convolve(S, np.ones(9) / 9, "same") * (f > 300)
    return f[int(np.argmax(S))]


def snaps(verbose=False):
    """[(take, onset s, 0.3 s from 2 ms before the peak)] -- the kept snaps."""
    out = []
    for p in sorted(glob.glob(os.path.join(REFS, "*"))):
        name = os.path.basename(p)
        if any(s in name for s in SKIP):
            if verbose:
                print("  %-44s skipped (SKIP)" % name[:44])
            continue
        x, sr = load(p)
        for i in peaks(x, sr):
            a = max(0, i - int(0.002 * sr))
            seg = x[a:a + int(0.3 * sr)]
            hz = peak_hz(seg[:int(WIN_S * sr)], sr)
            keep = 1300 <= hz <= 3500
            if verbose:
                print("  %-44s %6.3f s  peak %5.0f Hz  %s" % (name[:44], i / sr, hz, "kept" if keep else "-- not a snap"))
            if keep:
                out.append((name, i / sr, seg))
    return out, 44100


def measure(seg, sr):
    """A snap: its colour over WIN_S from 2 ms before its peak (third
    octaves, dB re the strongest) and its fall, dB/s (-6 to -26 dB)."""
    w = int(0.0007 * sr)
    e = np.sqrt(np.convolve(seg * seg, np.ones(w) / w, "same"))
    db = 20 * np.log10(e / e.max() + 1e-9)
    k = int(np.argmax(db))
    t = db[k:]
    a6 = np.flatnonzero(t < -6)
    a26 = np.flatnonzero(t < -26)
    dps = 20.0 / ((a26[0] - a6[0]) / sr) if len(a6) and len(a26) and a26[0] > a6[0] else np.nan
    on = max(0, k - int(0.002 * sr))
    y = seg[on:on + int(WIN_S * sr)]
    N = 1 << 15
    X = np.abs(np.fft.rfft(y * np.hanning(len(y)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    c = np.array([X[(f >= lo) & (f < hi)].sum() for lo, hi in zip(E3[:-1], E3[1:])])
    c = 10 * np.log10(c / c.max() + 1e-12)
    return dict(fall=dps, colour=c)


def render(n=8, gap=0.5, vel=100, room=None):
    """N snaps GAP seconds apart; in ROOM (a tonelib room preset: its first
    reflections in the render, its diffuse tail by roomtail.py), else dry."""
    import mido
    import blockrender as B
    if room:
        import tonelib
        tonelib.set_room(room)
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    for i in range(n):
        t.append(mido.Message("note_on", channel=9, note=NOTE, velocity=vel, time=0 if i == 0 else int(gap * 960) - 48))
        t.append(mido.Message("note_off", channel=9, note=NOTE, velocity=0, time=48))
    L, R = B.render(m)[:2]
    L, R = np.asarray(L, np.float64), np.asarray(R, np.float64)
    if room:
        import subprocess
        import tempfile
        from scipy.io import wavfile
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "dry.wav"), os.path.join(d, "wet.wav")
            B.write_wav(a, L, R)
            subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), a, b], check=True,
                           stdout=subprocess.DEVNULL, env=dict(os.environ, TUNING_ROOM=room))
            _sr, w = wavfile.read(b)
        w = w.astype(np.float64)
        if w.dtype.kind == "i" or np.abs(w).max() > 2.0:
            w /= 32768.0
        L, R = w[:, 0], w[:, 1]
    y = 0.5 * (L + R)
    return [y[int(i * gap * B.SR):int((i + 1) * gap * B.SR)] for i in range(n)], B.SR


def level(x, sr):
    c = np.concatenate(([0.0], np.cumsum(x * x)))
    n = min(int(0.15 * sr), len(x) - 1)
    return 10 * np.log10((c[n:] - c[:-n]).max() / n + 1e-30)


def recorded():
    S, sr = snaps()
    return [measure(s, sr) for _n, _t, s in S]


def report():
    R = recorded()
    hits, sr = render()
    O = [measure(y, sr) for y in hits]
    for name, rows in (("recorded", R), ("ours", O)):
        print("  %-9s %d snaps, fall %.0f dB/s (median)" % (name, len(rows), np.nanmedian([r["fall"] for r in rows])))
    sel = [i for i, c in enumerate(CEN) if c > 200][::2]
    print("  colour at " + " ".join("%6d" % CEN[i] for i in sel))
    for name, rows in (("recorded", R), ("ours", O)):
        m = np.mean([r["colour"] for r in rows], 0)
        print("  %-9s " % name + " ".join("%6.1f" % m[i] for i in sel))
    print("  level at velocity 100: %.2f dB" % np.mean([level(y, sr) for y in hits]))


# the hand clap's level at velocity 100, its loudest 150 ms (clap_fit.TARGET),
# less 6 dB: one hand where the clap is several
TARGET = -44.48 - 6.0


def fit(passes=4):
    """--fit: strike_noise_db band by band toward the snaps' mean colour,
    the table shifted to hold TARGET. Written into tonelib.py."""
    import re
    import tonelib
    cls = tonelib.FingerSnapProperties
    rec = np.mean([r["colour"] for r in recorded()], 0)
    keep = {int(hz): i for i, c in enumerate(CEN) for hz, _ in cls.strike_noise_db if abs(c / hz - 1) < 0.02}
    for n in range(passes + 1):
        hits, sr = render()
        ours = np.mean([measure(y, sr)["colour"] for y in hits], 0)
        lv = np.mean([level(y, sr) for y in hits])
        d = {hz: rec[i] - ours[i] for hz, i in keep.items()}
        # SHAPE ONLY: the takes' snaps peak at different frequencies, so their
        # mean colour sits ~9 dB under its own top where ours (one shape) sits
        # at it -- an offset that cancelled the level's step each pass
        off = float(np.mean(list(d.values())))
        d = {hz: v - off for hz, v in d.items()}
        print("  pass %d: colour rms %.1f dB, level %.2f dB (target %.2f)" % (
            n, np.sqrt(np.mean([v * v for v in d.values()])), lv, TARGET), flush=True)
        if n == passes:
            break
        cls.strike_noise_db = tuple((hz, round(db + d.get(hz, 0.0) + (TARGET - lv), 1))
                                    for hz, db in cls.strike_noise_db)
    path = os.path.join(HERE, "tonelib.py")
    body = open(path).read()
    i = body.index("class FingerSnapProperties(")
    j = body.index("\nclass ", i + 10)
    blk = re.sub(r"(?m)^    strike_noise_db = \(.*\)$", lambda _: "    strike_noise_db = %s" % (cls.strike_noise_db,),
                 body[i:j])
    open(path, "w").write(body[:i] + blk + body[j:])
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))


def ab(out, room=None):
    """--ab=OUT.wav [--room=NAME]: the kept snaps, a pause, then as many of
    ours, matched in level -- ours in ROOM (the takes carry theirs; Ben: a
    studio to hear ours properly), else dry."""
    import wave
    S, sr = snaps()
    R = [s[:int(0.3 * sr)] for _n, _t, s in S]
    hits, sr2 = render(n=len(R), room=room)
    O = []
    for y in hits:
        on = int(np.flatnonzero(np.abs(y) > np.abs(y).max() * 0.05)[0])
        O.append(y[max(0, on - int(0.002 * sr2)):on + int(0.3 * sr2)])
    lr = np.mean([level(r, sr) for r in R])
    lo = np.mean([level(o, sr) for o in O])
    O = [o * 10 ** ((lr - lo) / 20) for o in O]
    gap, pause = np.zeros(int(0.25 * sr)), np.zeros(int(1.0 * sr))
    z = np.concatenate(sum(([r, gap] for r in R), []) + [pause] + sum(([o, gap] for o in O), []))
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes())
    w.close()


def main(argv):
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    room = next((a.split("=", 1)[1] for a in argv if a.startswith("--room=")), None)
    if out:
        return ab(out, room) or 0
    if "--takes" in argv:
        snaps(verbose=True)
        return 0
    if "--fit" in argv:
        fit()
        return 0
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
