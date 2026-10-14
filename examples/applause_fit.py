#!/usr/bin/env python3
"""Fit the applause (GM 126) to three audiences: claps, not a wash.
sources.md "Sound effects".

    python3 -I examples/applause_fit.py measure      the audiences, and ours
    python3 -I examples/applause_fit.py fit          the claps (writes tonelib.py)
    python3 -I examples/applause_fit.py ab OUT.wav   each audience, then ours
    python3 -I examples/applause_fit.py variants OUT.wav   the audiences, then ours three ways, in the hall

THE TAKES (CC0, Freesound): thaighaudio's concert audience (478415), leo153's
100-seat theatre (338259), nervousneal's ~750 people in a sanctuary (457295);
each read over 4 s about its loudest second.

WHAT THEY HOLD: energy peaking at 1-2 kHz -- a hand's cavity rings there --
falling 10-20 dB by 8 kHz and 25-38 under it at 63-125 Hz; and GRAIN, the
claps: the level over 5 ms windows (1-6 kHz) swings 2.2-4.4 dB sd where a
wash's swings 0.8. Ours had been the breath's wash, brightest at 16 kHz.
Modelled as the hand clap's burst (HandClapProperties) fired at random
instants through the note (strike_flam_rate): its colour moved by octave to
the audiences', the rate to the grain. Damped sines (grains) were tried
first and pinged: "more like seashore drips than distinct claps" (Ben).
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

FS = os.path.expanduser("~/Documents/refs/freesound/applause")
OCT = (63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
KEY = 60


def load(p):
    from scipy.io import wavfile
    import warnings
    warnings.simplefilter("ignore")
    sr, x = wavfile.read(p)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    return x / np.abs(x).max(), sr


def _mov(x, w):
    c = np.concatenate(([0.0], np.cumsum(x)))
    return (c[w:] - c[:-w]) / w


def reading(x, sr):
    """(octaves, dB re the loudest; the 5 ms level's sd at 1-6 kHz, dB)."""
    from scipy.signal import butter, sosfiltfilt
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), 1 << 18)) ** 2
    f = np.fft.rfftfreq(1 << 18, 1.0 / sr)
    o = np.array([10 * np.log10(X[(f >= c / np.sqrt(2)) & (f < c * np.sqrt(2))].sum() + 1e-20) for c in OCT])
    b = sosfiltfilt(butter(2, [1000, 6000], btype="band", fs=sr, output="sos"), x)
    w = int(0.005 * sr)
    e = np.sqrt(_mov(b * b, w))[::w]
    return o - o.max(), float(np.std(20 * np.log10(e + 1e-12)))


def loudest(x, sr, secs=4.0):
    """SECS about the take's loudest second (the whole take if shorter)."""
    e = _mov(x * x, int(1.0 * sr))
    i = int(np.argmax(e))
    return x[max(0, i - int(secs / 2 * sr)):i + int(secs / 2 * sr)]


def target():
    rs = [reading(loudest(*load(p)), load(p)[1]) for p in sorted(glob.glob(os.path.join(FS, "*.wav")))]
    return np.mean([r[0] for r in rs], 0), float(np.mean([r[1] for r in rs]))


def ours():
    y, sr = U.render(126, KEY, 100, 5.0)
    return reading(y[int(1.0 * sr):int(4.5 * sr)], sr)


def measure():
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        o, g = reading(loudest(x, sr), sr)
        print("  %-36s octaves %s | grain %.1f dB" % (os.path.basename(p)[:36], " ".join("%+4.0f" % v for v in o), g))
    o, g = ours()
    print("  %-36s octaves %s | grain %.1f dB" % ("ours", " ".join("%+4.0f" % v for v in o), g))


def fit(passes=10):
    """The claps: the hand clap's colour (strike_noise_db, its rows moved
    by octave) toward the audiences' octaves, and strike_flam_rate (claps a
    second) toward their grain -- fewer claps, more grain. Keeps the best
    pass; writes into tonelib.py."""
    import tonelib as T
    cls = T.ApplauseProperties
    R, g = target()
    base = dict(T.HandClapProperties.strike_noise_db)
    off = np.zeros(len(OCT))
    best = None

    def band(c):
        return int(np.argmin([abs(np.log2(c / o)) for o in OCT]))

    def apply():
        cls.strike_noise_db = tuple((c, round(float(v + off[band(c)]), 1)) for c, v in base.items())
    k = [OCT.index(c) for c in (250, 500, 1000, 2000, 4000, 8000, 16000)]
    for it in range(passes + 1):
        apply()
        O, go = ours()
        d = R - O
        e = float(np.sqrt(np.mean(d[k] ** 2) + 0.5 * (g - go) ** 2))
        print("  pass %d: rec - ours by octave %s; grain %.1f against %.1f; %.0f claps/s; error %.2f" % (
            it, " ".join("%+.0f" % v for v in d), go, g, cls.strike_flam_rate, e), flush=True)
        if best is None or e < best[0]:
            best = (e, cls.strike_noise_db, cls.strike_flam_rate)
        if it == passes:
            break
        off += 0.7 * d
        cls.strike_flam_rate = float(np.clip(cls.strike_flam_rate * 2 ** (-(g - go) / 3.0), 20.0, 3000.0))
    cls.strike_noise_db, cls.strike_flam_rate = best[1], best[2]
    print("  best: error %.2f" % best[0])
    path = os.path.join(os.path.dirname(HERE), "tonelib.py")
    src = open(path).read()
    a = src.index("class ApplauseProperties(")
    # the class ends at the next line at the margin
    b = a + re.search(r"\n(?=\S)", src[a + 10:]).start() + 10
    body = src[a:b]
    for name, val in (("strike_noise_db", cls.strike_noise_db), ("strike_flam_rate", round(cls.strike_flam_rate, 1))):
        body = re.sub(r"^    %s = .*$" % name, lambda _: "    %s = %s" % (name, val), body, count=1, flags=re.M)
    open(path, "w").write(src[:a] + body + src[b:])

def ab(out):
    import harpsi_ab as A
    from roomtail import write_wav
    gap = np.zeros(int(0.6 * A.SR))
    secs = 8.0
    A.NOTE_S = secs
    parts = []
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        # each audience 8 s (the 100-seat theatre's whole take is 12), then ours as long
        parts += [A.fit_note(loudest(x, sr, secs), sr), gap]
        y, sr2 = U.render(126, KEY, 100, secs)
        parts += [A.fit_note(y, sr2), gap, gap]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


VARIANTS = (
    ("as fitted", {}),
    ("crisper claps: 2500 dB/s", {"strike_noise_dbs": 2500.0}),
    ("crisper, near and far: 25 dB of level spread", {"strike_noise_dbs": 2500.0, "strike_flam_db": 25.0}),
)


def hall_render(attrs, secs, out):
    """Ours as the corpus renders it -- the hall and roomtail -- with ATTRS
    set on the class first (a variant), in a subprocess: blockrender's own
    command line, so the room's sidecar is written as for any render."""
    import subprocess
    import tempfile
    import mido
    import lib
    d = tempfile.mkdtemp(prefix="applause_")
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=126, time=0))
    t.append(mido.Message("note_on", channel=0, note=KEY, velocity=100, time=10))
    t.append(mido.Message("note_off", channel=0, note=KEY, time=int(secs * 960)))
    mid = os.path.join(d, "a.mid")
    m.save(mid)
    dry = os.path.join(d, "a_dry.wav")
    root = os.path.dirname(HERE)
    code = ("import sys, runpy; sys.path.insert(0, %r); import tonelib as T\n"
            "for k, v in %r.items(): setattr(T.ApplauseProperties, k, v)\n"
            "sys.argv = ['blockrender.py', %r, %r, 'hybrid440']\n"
            "runpy.run_path(%r, run_name='__main__')\n"
            % (root, dict(attrs), mid, dry, os.path.join(root, "blockrender.py")))
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_MASTER_DB="-14")
    subprocess.run([sys.executable, "-c", code], env=env, check=True, stdout=subprocess.DEVNULL)
    lib.roomtail(dry, out, env={"TUNING_ROOM": "hall"})
    return out


def variants(out, secs=15.0, rec_secs=8.0):
    """Each audience (REC_SECS), then ours in each of VARIANTS (SECS), in
    the hall -- which part of "rain on a metal roof" (Ben) is the clap and
    which the room."""
    import tempfile
    import harpsi_ab as A
    from roomtail import write_wav
    gap = np.zeros(int(0.6 * A.SR))
    A.NOTE_S = secs
    ours_ = []
    d = tempfile.mkdtemp(prefix="applause_v_")
    for i, (name, attrs) in enumerate(VARIANTS):
        y, sr = load(hall_render(attrs, secs, os.path.join(d, "v%d.wav" % i)))
        a = int(np.flatnonzero(np.abs(y) > 0.05 * np.abs(y).max())[0])
        ours_.append(A.fit_note(y[a:], sr))
        print("  variant %d: %s" % (i + 1, name))
    parts = []
    A.NOTE_S = rec_secs
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        parts += [A.fit_note(loudest(x, sr, rec_secs), sr), gap]
    parts.append(gap)
    for v in ours_:
        parts += [v, gap]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


def main(argv):
    if argv[1:2] == ["measure"]:
        measure()
    elif argv[1:2] == ["fit"]:
        fit()
    elif argv[1:2] == ["variants"]:
        variants(argv[2], secs=float(argv[3]) if len(argv) > 3 else 15.0)
    elif argv[1:2] == ["ab"]:
        ab(argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
