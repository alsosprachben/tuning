#!/usr/bin/env python3
"""Fit Small Club 1 (GS Hip-Hop / Dance key 88; tonelib.SmallClubProperties)
to Freesound's CC0 small-crowd applause (~/Documents/refs/applause_small/raw,
sources.md).

    smallclub_fit.py              measure: recorded against ours
    smallclub_fit.py --fit        the claps' colour, third octave by third octave
    smallclub_fit.py --ab=OUT.wav [--room=studio]
                                  the takes' bursts, then ours

SMALL CLUB sits in the SFX set between Telephone and Applause Wave (SC-88
Pro, native SFX 91-92): a small crowd's applause. Three takes (Breviceps'
"~30 people", AudioSea's small room, miuziqa's small crowd) give its colour, a
hump at 1.3-2 kHz, 6-8 dB down by 5 kHz -- fitted here over their sustained
part (where the 200 ms level is within 6 dB of its top). Its claps are PEOPLE
(tonelib.SmallClubProperties.strike_flam_people: Ben, "12 individuals in
different positions, clapping at different rates", and different volumes),
not a crowd's rate: a peak count of the takes had read 106-116 a second, but
it read 103 inside one ensemble clap -- it counts ripples, not claps.
"""
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

REFS = os.path.expanduser("~/Documents/refs/applause_small/raw")
KIT, NOTE = 26, 88
E3 = 2 ** np.arange(np.log2(45), np.log2(16000), 1 / 3.0)
CEN = np.sqrt(E3[:-1] * E3[1:])


def load(p, stereo=False):
    """A take at 44.1 kHz: mono (its colour), or (n, 2) for the A/B."""
    from scipy.io import wavfile
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "x.wav")
        subprocess.run(["sox", p, "-r", "44100", "-b", "32", "-e", "float", w, "channels", "2"]
                       + ([] if stereo else ["remix", "-"]), check=True, stderr=subprocess.DEVNULL)
        sr, x = wavfile.read(w)
    return x.astype(np.float64), sr


def sustained(x, sr):
    e = np.convolve(x * x, np.ones(int(0.2 * sr)) / int(0.2 * sr), "same")
    return x[e > e.max() * 10 ** (-6 / 10.0)]


def colour(x, sr):
    N = 1 << 14
    hop = N // 2
    X = np.zeros(N // 2 + 1)
    for i in range(0, max(1, len(x) - N), hop):
        X += np.abs(np.fft.rfft(x[i:i + N] * np.hanning(N))) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    c = np.array([X[(f >= lo) & (f < hi)].sum() for lo, hi in zip(E3[:-1], E3[1:])])
    return 10 * np.log10(c / c.max() + 1e-12)


def recorded():
    return np.mean([colour(sustained(*load(p)), 44100) for p in sorted(glob.glob(os.path.join(REFS, "*")))], 0)


def render(n=2, gap=3.5, room=None, stereo=False):
    import mido
    import blockrender as B
    if room:
        import tonelib
        tonelib.set_room(room)
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    t.append(mido.Message("program_change", channel=9, program=KIT, time=0))
    for i in range(n):
        t.append(mido.Message("note_on", channel=9, note=NOTE, velocity=100, time=0 if i == 0 else int(gap * 960) - 48))
        t.append(mido.Message("note_off", channel=9, note=NOTE, velocity=0, time=48))
    L, R = B.render(m)[:2]
    L, R = np.asarray(L, np.float64), np.asarray(R, np.float64)
    if room:
        from scipy.io import wavfile
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "dry.wav"), os.path.join(d, "wet.wav")
            B.write_wav(a, L, R)
            subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), a, b], check=True,
                           stdout=subprocess.DEVNULL, env=dict(os.environ, TUNING_ROOM=room))
            _sr, w = wavfile.read(b)
        w = w.astype(np.float64)
        L, R = w[:, 0], w[:, 1]
    y = np.stack([L, R], 1) if stereo else 0.5 * (L + R)
    return [y[int(i * gap * B.SR):int((i + 1) * gap * B.SR)] for i in range(n)], B.SR


def ours():
    hits, sr = render()
    return np.mean([colour(sustained(y, sr), sr) for y in hits], 0)


def report():
    rec, o = recorded(), ours()
    sel = [i for i, c in enumerate(CEN) if c > 100][::2]
    print("  colour at " + " ".join("%6d" % CEN[i] for i in sel))
    print("  recorded  " + " ".join("%6.1f" % rec[i] for i in sel))
    print("  ours      " + " ".join("%6.1f" % o[i] for i in sel))


def fit(passes=3):
    """--fit: strike_noise_db band by band toward the takes' colour, shape
    only (the level is the rate's). Written into tonelib.py."""
    import re
    import tonelib
    cls = tonelib.SmallClubProperties
    rec = recorded()
    keep = {int(hz): i for i, c in enumerate(CEN) for hz, _ in cls.strike_noise_db if abs(c / hz - 1) < 0.02}
    for n in range(passes + 1):
        o = ours()
        d = {hz: rec[i] - o[i] for hz, i in keep.items()}
        off = float(np.mean(list(d.values())))
        d = {hz: v - off for hz, v in d.items()}
        print("  pass %d: colour rms %.1f dB" % (n, np.sqrt(np.mean([v * v for v in d.values()]))), flush=True)
        if n == passes:
            break
        cls.strike_noise_db = tuple((hz, round(db + d.get(hz, 0.0), 1)) for hz, db in cls.strike_noise_db)
    path = os.path.join(HERE, "tonelib.py")
    body = open(path).read()
    i = body.index("class SmallClubProperties(")
    # the class ends at the next top-level line (a function may follow it)
    j = i + re.search(r"\n(?=\S)", body[i + 10:]).start() + 10
    blk = body[i:j]
    line = "    strike_noise_db = %s" % (cls.strike_noise_db,)
    if re.search(r"(?m)^    strike_noise_db = ", blk):
        blk = re.sub(r"(?m)^    strike_noise_db = \(.*\)$", lambda _: line, blk)
    else:
        blk = blk.rstrip("\n") + "\n" + line + "\n\n"
    open(path, "w").write(body[:i] + blk + body[j:])
    print(line)


def ab(out, room=None):
    """--ab=OUT.wav: each take's sustained burst (2.8 s), then two of ours,
    matched in level -- in STEREO, as heard."""
    from scipy.io import wavfile
    R = []
    for p in sorted(glob.glob(os.path.join(REFS, "*"))):
        x, sr = load(p, stereo=True)
        m = x.mean(1)
        e = np.convolve(m * m, np.ones(int(0.2 * sr)) / int(0.2 * sr), "same")
        on = int(np.flatnonzero(e > e.max() * 0.05)[0])
        R.append(x[on:on + int(2.8 * sr)])
    hits, sr2 = render(room=room, stereo=True)
    rms = lambda v: np.sqrt(np.mean(v * v))
    g = np.mean([rms(r) for r in R]) / np.mean([rms(h[:int(2.8 * sr2)]) for h in hits])
    gap = np.zeros((int(0.6 * sr), 2))
    z = np.concatenate(sum(([r, gap] for r in R), []) + [np.zeros((int(0.8 * sr), 2))]
                       + sum(([h * g, gap] for h in hits), []))
    z *= 0.5 / np.abs(z).max()
    wavfile.write(out, sr, (z * 32767).astype(np.int16))
    for name, v in [(os.path.basename(p)[:28], r) for p, r in zip(sorted(glob.glob(os.path.join(REFS, "*"))), R)] + \
            [("ours %d" % i, h) for i, h in enumerate(hits)]:
        c = np.corrcoef(v[:, 0], v[:, 1])[0, 1]
        print("  %-30s L/R correlation %.2f" % (name, c))


def main(argv):
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    room = next((a.split("=", 1)[1] for a in argv if a.startswith("--room=")), None)
    if out:
        return ab(out, room) or 0
    if "--fit" in argv:
        fit()
        return 0
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
