#!/usr/bin/env python3
"""GM 55, Orchestra Hit, against what General MIDI's own sets play.

    python3 -I examples/orchhit_fit.py            the sets' hits, then ours
    python3 -I examples/orchhit_fit.py --fit      ...and fit ours to them
    python3 -I examples/orchhit_fit.py --ab OUTDIR TAG=ROOT ...
                                                  a stab phrase per tree, and
                                                  FluidR3's own hit (timidity)

AN ORCHESTRA HIT IS A SAMPLE. The patch GM names is the Fairlight-era stab
(ORCH5): one recorded chord of a real orchestra, played back up and down the
keyboard. So the GM sets' own hits are the instrument itself, not stand-ins
for it -- the way a Messenger patch is measured on the Messenger. Four sets on
disk (examples/gm_release.SETS): FluidR3 and MuseScore General share their
G#6/G#7 pair, GeneralUser GS has two of its own, TimGM6mb one. Measured only.

Each hit, measured: its PITCH CLASSES (one note in octaves, or a chord?) as
a chroma against the sample's root key; its energy per OCTAVE from two below
the root to three above; how much of it is NOISE (between the harmonic peaks);
its ENVELOPE (the peak, and when it is 10, 20 and 40 dB down).
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
NAMES = "C C# D D# E F F# G G# A A# B".split()


def envelope(x, sr):
    """Peak time, and the times it is 10, 20 and 40 dB under its peak (5 ms rms)."""
    w = max(1, int(0.005 * sr))
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same")) + 1e-12
    db = 20 * np.log10(e / e.max())
    p = int(np.argmax(db))
    out = [p / sr]
    for d in (-10, -20, -40):
        k = np.flatnonzero(db[p:] < d)
        out.append((p + k[0]) / sr if len(k) else np.nan)
    return out


def measure(x, sr, root):
    """chroma (12, re the root's pitch class, dB re the strongest), octave
    energy (-2..+3 octaves about the root, dB re the strongest), noise share
    (dB of the energy between harmonic peaks), envelope."""
    x = np.asarray(x, float)
    a = int(np.argmax(np.abs(x)))
    seg = x[a:a + int(0.25 * sr)]
    N = 1 << 16
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    ok = (f > 40) & (f < min(12000, 0.45 * sr))
    f0 = 440.0 * 2 ** ((root - 69) / 12.0)
    # chroma: every bin's power to its nearest pitch class (re the root)
    pc = np.round(12 * np.log2(f[ok] / f0)).astype(int) % 12
    chroma = np.bincount(pc, X[ok], 12)
    chroma = 10 * np.log10(chroma / chroma.max() + 1e-12)
    octs = []
    for o in range(-2, 4):
        lo, hi = f0 * 2 ** (o - 0.5), f0 * 2 ** (o + 0.5)
        m = (f >= lo) & (f < hi) & ok
        octs.append(X[m].sum())
    octs = 10 * np.log10(np.array(octs) / max(octs) + 1e-12)
    # noise: the spectrum's floor (running 5th percentile over 1/6 octave)
    # against its total, in the band that sounds
    lf = np.log2(f[ok])
    Xo = X[ok]
    floor = np.array([np.percentile(Xo[(lf > l - 1 / 12.0) & (lf < l + 1 / 12.0)], 20)
                      for l in lf[::64]])
    noise = 10 * np.log10(floor.sum() * 64 / Xo.sum() + 1e-12)
    return chroma, octs, noise, envelope(x, sr)


E3 = 45.0 * 2 ** (np.arange(0, 26) / 3.0)          # the strike table's bands, 45 Hz-11.5 kHz


def noise_bands(x, sr):
    """The hit's NOISE per third octave, 0-60 ms from the peak: the
    spectrum's 20th-percentile floor over each band (the harmonics stand
    above it), dB re the whole hit's power."""
    x = np.asarray(x, float)
    a = int(np.argmax(np.abs(x)))
    seg = x[a:a + int(0.06 * sr)]
    N = 1 << 15
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    tot = X.sum()
    out = []
    for lo, hi in zip(E3 / 2 ** (1 / 6.0), E3 * 2 ** (1 / 6.0)):
        m = (f >= lo) & (f < hi)
        out.append(10 * np.log10(np.percentile(X[m], 20) * m.sum() / tot + 1e-30)
                   if m.sum() > 3 and hi < 0.45 * sr else np.nan)
    return np.array(out)


def show(label, root, m):
    chroma, octs, noise, env = m
    strong = [(NAMES[(root + i) % 12], c) for i, c in enumerate(chroma) if c > -12]
    print("  %-26s root %-4s  pcs: %s" % (label, "%s%d" % (NAMES[root % 12], root // 12 - 1),
                                          " ".join("%s%+.0f" % s for s in strong)))
    print("  %26s octaves -2..+3: %s   noise %+.0f dB   peak %.0f ms, -10/-20/-40 dB at %s ms"
          % ("", " ".join("%+.0f" % o for o in octs), noise, 1000 * env[0],
             "/".join("%.0f" % (1000 * t) if np.isfinite(t) else "-" for t in env[1:])))


def ours(root, out, secs=1.5, vel=110):
    import mido
    import wave
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.Message("program_change", channel=0, program=55, time=0))
    t.append(mido.Message("note_on", channel=0, note=root, velocity=vel, time=0))
    t.append(mido.Message("note_off", channel=0, note=root, velocity=0, time=int(secs * 960)))
    mid = out[:-4] + ".mid"
    m.save(mid)
    L, R = B.render(mid)[:2]
    os.remove(mid)
    x = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(B.SR)
    w.writeframes((x / max(np.abs(x).max(), 1e-12) * 0.5 * 32767).astype("<i2").tobytes())
    w.close()
    return x, B.SR


# The ranks, re-voiced for the fifth the GM hits carry (4-7 dB under the root:
# a power chord in octaves, not a triad). CC11's stop word is 7 bits, so the
# fifth comes from re-voicing, not adding: the horns on the fifth, the winds on
# the twelfth.
FOOT = (("bass", 0.25, "ConicalBrassProperties"), ("tenor", 0.5, "TromboneProperties"),
        ("horn", 1.5, "HornProperties"), ("string", 1.0, "BowedStringProperties"),
        ("tpt", 2.0, "TrumpetProperties"), ("wind", 3.0, "StoppedPipeProperties"),
        ("picc", 4.0, "StoppedPipeProperties"))
NOISE = None                    # their noise shape, set in main
THUMP = (45, 56, 71, 90, 113)                  # the bass drum's bands (Hz)
CRASH = (5760, 7257, 9143, 11520, 14514)       # the cymbal's
BANDS = (("thump", 40, 120), ("crash", 6000, 12000))
BT = (10, 25, 50, 100, 200)                    # ms after 10 ms before the peak


def low_end(x, sr):
    """The hit's LOW END, which the octave profile (two octaves under the key
    and up) never saw: dB of its power under 400 Hz and in 40-120 Hz, 0-40 ms
    (the impact) and 40-150 ms (what rings). The GM hits put 55-74% of their
    power under 400 Hz -- the chord's own root and fifth three and four
    octaves under the key, G#1 52 Hz, D#2 78, G#2 104: timpani and low brass."""
    x = np.asarray(x, float)
    a = int(np.argmax(np.abs(x)))
    out = []
    for t0, t1 in ((0.0, 0.04), (0.04, 0.15)):
        seg = x[a + int(t0 * sr):a + int(t1 * sr)]
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)) ** 2
        f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
        tot = X[(f > 30) & (f < 0.45 * sr)].sum()
        out += [10 * np.log10(X[(f > 30) & (f < 400)].sum() / tot),
                10 * np.log10(X[(f > 40) & (f < 120)].sum() / tot + 1e-12)]
    return out


def band_env(x, sr):
    """The drum's and the cymbal's bands over the first 200 ms, dB re the
    hit's loudest moment in any band: where the GM hits' percussion lives."""
    from scipy.signal import butter, sosfiltfilt
    x = np.asarray(x, float)
    a = max(0, int(np.argmax(np.abs(x))) - int(0.01 * sr))
    w = int(0.01 * sr)
    full = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    ref = 20 * np.log10(full.max() + 1e-9)
    out = []
    for _, lo, hi in BANDS:
        if hi >= 0.45 * sr:
            out.append(None); continue
        y = sosfiltfilt(butter(4, [lo, hi], btype="band", fs=sr, output="sos"), x)
        e = np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-9
        out.append([20 * np.log10(e[min(len(e) - 1, a + int(t / 1000 * sr))]) - ref for t in BT])
    return out


def over_of(x):
    import tonelib as T
    g = np.exp(x[:7])
    return dict(stop_ranks=[(n, ft, float(gi), getattr(T, c)) for (n, ft, c), gi in zip(FOOT, g)],
                decay_db=float(np.exp(x[7])), harmonic_decay_db=float(x[8]),
                strike_noise_db=tuple((float(f), float(v + x[9])) for f, v in NOISE),
                strike_noise_dbs=float(np.exp(x[10])), strike_noise_len_s=1.0,
                strike_noise_fade_s=0.001, strike_noise_slope=0.0,
                strike_noise_layers=((
                    (tuple((float(f), float(x[13])) for f in CRASH), 0.001, float(np.exp(x[14])), 0.8),)
                    if len(x) > 16 else (
                    (tuple((float(f), float(x[11])) for f in THUMP), float(np.exp(x[12])),
                     float(np.exp(x[15])) if len(x) > 15 else 40.0, 0.8),
                    (tuple((float(f), float(x[13])) for f in CRASH), 0.001, float(np.exp(x[14])), 0.8))),
                struck_layer=((T.TimpaniProperties, float(x[16]), float(np.exp(x[17])),
                               float(np.exp(x[18]))) if len(x) > 16 else None))


def hit_class(over):
    import tonelib as T
    return type("Hit", (T.OrchestraHitProperties,), over)


def score(tg, m):
    """Squared error, ours against one GM hit: the octave profile (dB), the
    fifth's level (dB), the noise share (dB), and the -10/-20/-40 dB times
    (10 x log2 of the ratio: a time twice too long costs as 10 dB does)."""
    (c1, o1, n1, e1, b1, l1), (c0, o0, n0, e0, b0, l0) = m, tg
    e = list(o1 - o0) + [c1[7] - c0[7], n1 - n0]
    e += [2.0 * (u - v) for u, v in zip(l1, l0)]  # the low end, weighted: it is most of the hit
    for p1, p0 in zip(b1, b0):                  # the drum's and the cymbal's bands
        if p1 is not None and p0 is not None:
            e += [0.5 * (u - v) for u, v in zip(p1, p0)]
    for a, b in zip(e1[1:], e0[1:]):
        if np.isfinite(a) and np.isfinite(b):
            e.append(10 * np.log2(a / b))
    return float(np.sum(np.square(e))), e


def fit(targets, x0, iters=350, only=None):
    import patch_map
    from scipy.optimize import minimize
    d = os.path.expanduser("~/Documents/refs/orchhit/model")
    os.makedirs(d, exist_ok=True)
    keep = patch_map.PROGRAM_CLASS.get(55)
    best = [np.inf, None]

    full = np.array(x0, float)

    def loss(x):
        if only is not None:
            y = full.copy(); y[only] = x; x = y      # best[] keeps the FULL vector
        patch_map.PROGRAM_CLASS[55] = hit_class(over_of(x))
        L = 0.0
        for root in sorted(set(r for r, _ in targets)):
            y, sr = ours(root, os.path.join(d, "fit_%d.wav" % root))
            m = measure(y, sr, root) + (band_env(y, sr), low_end(y, sr))
            for r, tg in targets:
                if r == root:
                    L += score(tg, m)[0]
        if L < best[0]:
            best[0], best[1] = L, np.array(x)
            print("  %.0f  %s" % (L, " ".join("%.3g" % v for v in x)), flush=True)
        return L
    try:
        # THE SIMPLEX'S OWN STEPS: scipy starts a zero parameter 0.00025 away,
        # and the noise offset (starting at 0 dB) never moved in the first run
        step = np.r_[[0.4] * 7, 0.3, 1.0, 6.0, 0.5, 6.0, 0.5, 6.0, 0.5, 0.5, 8.0, 0.7, 0.5][:len(x0)]
        xs = x0 if only is None else full[only]
        st = step if only is None else step[only]
        sim = np.vstack([xs] + [xs + np.eye(len(xs))[i] * st[i] for i in range(len(xs))])
        minimize(loss, xs, method="Nelder-Mead",
                 options=dict(maxfev=iters, xatol=1e-2, fatol=1.0, adaptive=True,
                              initial_simplex=sim))
    finally:
        patch_map.PROGRAM_CLASS[55] = keep
    return best[1]


def phrase(out):
    """Stabs, the way the patch is played: a syncopated figure on C, E-flat,
    F and G across two octaves, then a held low hit."""
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=960)          # 120 bpm
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.Message("program_change", channel=0, program=55, time=0))
    beat = 960
    fig = [(0, 60), (1.5, 60), (3, 63), (4, 65), (5.5, 65), (7, 67), (8, 72), (9.5, 72),
           (11, 75), (12, 77), (13.5, 79), (15, 72), (16, 48)]
    now = 0
    for b, k in fig:
        at = int(b * beat)
        t.append(mido.Message("note_on", channel=0, note=k, velocity=110, time=at - now))
        t.append(mido.Message("note_off", channel=0, note=k, velocity=0, time=int(0.4 * beat)))
        now = at + int(0.4 * beat)
    m.save(out)


def ab(out, pairs):
    import subprocess
    from gm_release import SETS
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "stabs.mid")
    phrase(mid)
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_WET="-3", TUNING_MASTER_DB="-12")
    for tag, root in pairs:
        P = lambda f: os.path.join(out, "stabs_%s%s" % (tag, f))   # noqa: E731
        subprocess.check_call([sys.executable, os.path.join(root, "blockrender.py"), mid,
                               P(".dry.wav"), "hybrid440"], env=env, cwd=root)
        subprocess.check_call([sys.executable, os.path.join(HERE, "roomtail.py"),
                               P(".dry.wav"), P(".wav")], env=env)
    # the reference: FluidR3's own Orchestra Hit, dry, then the same hall
    sf = dict(SETS)["FluidR3"]
    cfg = os.path.join(out, "fluid.cfg")
    open(cfg, "w").write('bank 0\n55 %%font "%s" 0 55\n' % sf)
    P = lambda f: os.path.join(out, "stabs_C_FluidR3%s" % f)        # noqa: E731
    subprocess.check_call(["timidity", "-c", cfg, "-Ow", "-o", P(".dry.wav"), "-s", "44100",
                           "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid])
    subprocess.check_call([sys.executable, os.path.join(HERE, "roomtail.py"),
                           P(".dry.wav"), P(".wav")], env=env)
    os.remove(cfg)
    for tag in [t for t, _ in pairs] + ["C_FluidR3"]:
        P = lambda f: os.path.join(out, "stabs_%s%s" % (tag, f))   # noqa: E731
        subprocess.check_call(["sox", P(".wav"), P(".norm.wav"), "gain", "-n", "-1"])
        subprocess.check_call(["lame", "-b", "256", "--quiet", P(".norm.wav"), P(".mp3")])
        for f in (".dry.wav", ".dry.send.wav", ".norm.wav", ".wav", ".dry.room.json"):
            if os.path.exists(P(f)):
                os.remove(P(f))
        print("  -> " + P(".mp3"), flush=True)


def main(argv):
    if "--ab" in argv:
        i = argv.index("--ab")
        ab(argv[i + 1], [a.split("=", 1) for a in argv[i + 2:]])
        return 0
    import choir_fit as C
    from gm_release import SETS
    roots, nb, targets = set(), [], []
    print("== the GM sets' hits")
    for name, path in SETS:
        if not path or not os.path.exists(path):
            continue
        for sname, root, sr, x in C.gm_samples(path, 55):
            if sname.endswith("(R)") or sname.endswith("xt"):
                continue                    # the stereo pair's other side; GU's low-rate copy
            mm = measure(x, sr, root)
            show("%s %s" % (name.split()[0], sname), root, mm)
            roots.add(root)
            if not sname.startswith("Orch Hit G#") or name.startswith("FluidR3"):
                targets.append((root, mm + (band_env(x, sr), low_end(x, sr))))   # MuseScore's pair is FluidR3's: counted once
            nb.append(noise_bands(x, sr))
    nb = np.nanmedian(np.array(nb), axis=0)
    print("\n  their noise per third octave (dB re the hit's power, median of the hits):")
    print("  " + " ".join("%d:%.0f" % (f, v) for f, v in zip(E3, nb) if np.isfinite(v)))
    if "--fit" in argv:
        global NOISE
        NOISE = [(f, v) for f, v in zip(E3, nb) if np.isfinite(v)]
        import tonelib as T
        H = T.OrchestraHitProperties
        g0 = dict((r[0], r[2]) for r in H.stop_ranks)
        x0 = np.r_[np.log([g0[n] for n, _, _ in FOOT]), np.log(H.decay_db), H.harmonic_decay_db,
                   0.0, np.log(60.0)]
        if "--from-first" in argv:              # the first run's best (score 2874)
            x0 = np.array([0.184, 0.178, -0.675, -0.424, -0.29, -0.712, -1.59, 3.68, 2.78, 0.0, np.log(30.0)])
        # the second run's best (the class as committed to tonelib), and the
        # drum and cymbal layers to start: drum 20 dB, 50 ms rise; cymbal 20 dB, 40 dB/s
        x0 = np.r_[np.log([r[2] for r in H.stop_ranks]), np.log(H.decay_db), H.harmonic_decay_db,
                   26.9, np.log(H.strike_noise_dbs), 20.0, np.log(0.05), 20.0, np.log(40.0)]
        only = None
        if "--drum" in argv:
            # the third run's best, and the DRUM alone free: its level, rise and
            # fall (the third run held the fall at 40 dB/s, so a bloom at 50 ms
            # rang on to 200 ms and the fit gave the drum up)
            x0 = np.array([-0.241, 0.311, -0.95, 0.627, -0.00704, 0.0503, -1.54, 3.38, -0.236,
                           26.2, 3.9, 20.0, np.log(0.05), 17.4, 4.1, np.log(90.0)])
            only = [11, 12, 15]
        if "--timpani" in argv:
            # the third run's best with the noise drum OUT (x[16:] in use drops
            # it) and a TIMPANI on the root, D2-D3: its level, rise and fall
            # (Ben: "Add tympani?" -- the noise drum the fit would not keep)
            x0 = np.array([-0.241, 0.311, -0.95, 0.627, -0.00704, 0.0503, -1.54, 3.38, -0.236,
                           26.2, 3.9, 0.0, 0.0, 17.4, 4.1, 0.0, 0.0, np.log(0.02), np.log(20.0)])
            only = [0, 9, 16, 17, 18]     # ...and the bass rank and the noise, which share the low end
        xb = fit(targets, x0, iters=90 if only else 350, only=only)
        o = over_of(xb)
        print("\n  stop_ranks = [%s]" % ", ".join("(%r, %s, %.3f, %s)" % (n, ft, g, c.__name__)
                                                 for n, ft, g, c in o["stop_ranks"]))
        print("  decay_db %.2f  harmonic_decay_db %.3f  strike_noise_dbs %.1f  noise offset %+.1f dB"
              % (o["decay_db"], o["harmonic_decay_db"], o["strike_noise_dbs"], xb[9]))
        print("  drum %+.1f dB, rise %.0f ms, %.0f dB/s;  cymbal %+.1f dB, %.0f dB/s"
              % (xb[11], 1000 * np.exp(xb[12]), np.exp(xb[15]) if len(xb) > 15 else 40.0,
                 xb[13], np.exp(xb[14])))
        if len(xb) > 16:
            print("  timpani %+.1f dB, rise %.0f ms, %.0f dB/s" % (xb[16], 1000 * np.exp(xb[17]), np.exp(xb[18])))
        import patch_map
        keep = patch_map.PROGRAM_CLASS.get(55)
        patch_map.PROGRAM_CLASS[55] = hit_class(o)
        print("\n== ours, fitted")
        d = os.path.expanduser("~/Documents/refs/orchhit/model")
        for root in sorted(roots):
            x, sr = ours(root, os.path.join(d, "fitted_%d.wav" % root))
            show("ours", root, measure(x, sr, root))
        patch_map.PROGRAM_CLASS[55] = keep
        return 0
    print("\n== ours")
    d = os.path.expanduser("~/Documents/refs/orchhit/model")
    os.makedirs(d, exist_ok=True)
    for root in sorted(roots):
        x, sr = ours(root, os.path.join(d, "ours_%d.wav" % root))
        show("ours", root, measure(x, sr, root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
