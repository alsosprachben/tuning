"""GS 12.24 Log Drum, fitted to VSCO 2's log drum (Versilian Studios, CC0;
~/Documents/refs/vsco2/Percussion/LogDrum{Hi,Lo}_MedM_v1-3_rr1-2_Sum.wav,
sources.md): two tongues, 155 and 108 Hz.

Each mode read where it sounds -- the tongue's 1st, 2nd and 3rd harmonics and
the log's three (tonelib.LogDrumProperties.body_modes_hz) -- its peak in four
windows after the stroke, dB re the fundamental's first; the middle stroke
(v2), both round-robins averaged. Ours rendered at the tongue's pitch and read
the same way. Each pass moves a mode's level by the early windows' mean
difference and its decay by the slope's.

    python3 examples/logdrum_fit.py           # the cells, takes and ours
    python3 examples/logdrum_fit.py --fit     # gains and decays, 4 passes
    python3 examples/logdrum_fit.py --tilt    # the strokes' brightening, v1-v3
    python3 examples/logdrum_fit.py --knock   # the mallet's knock, the strike noise
    python3 examples/logdrum_fit.py --ab=DIR  # the takes' strokes, then ours, per tongue
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/vsco2/Percussion")
TONGUES = {"Lo": 108.0, "Hi": 155.0}
WINS = ((0.0, 0.05), (0.05, 0.15), (0.15, 0.3), (0.3, 0.6))
VEL = {1: 70, 2: 100, 3: 127}       # VSCO's strokes as velocities (assumed)
FLOOR = -60.0


def load(path):
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "t.wav")
        subprocess.run(["sox", path, "-e", "floating-point", "-b", "32", "-c", "1", w], check=True)
        x, sr = read(w)
    x = x.reshape(len(x), -1).mean(1)
    k = int(np.argmax(np.abs(x)))
    return x[max(0, k - int(0.002 * sr)):], sr


def freqs(f0):
    import tonelib
    C = tonelib.LogDrumProperties
    return [f0, 2 * f0, 3 * f0] + list(C.body_modes_hz)


def cells(x, sr, fs):
    """dB of each mode's peak (+-3%) in each window."""
    out = np.zeros((len(fs), len(WINS)))
    for j, (a, b) in enumerate(WINS):
        s = x[int(a * sr):int(b * sr)]
        N = 1 << 17
        Y = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
        f = np.fft.rfftfreq(N, 1 / sr)
        for i, fm in enumerate(fs):
            out[i, j] = Y[(f > fm * 0.97) & (f < fm * 1.03)].max()
    return out


def take(tongue, v):
    """The measured pitch, and the cells averaged over the round-robins."""
    acc, f0s = [], []
    for rr in (1, 2):
        x, sr = load(os.path.join(REFS, "LogDrum%s_MedM_v%d_rr%d_Sum.wav" % (tongue, v, rr)))
        seg = x[int(0.05 * sr):int(0.5 * sr)]
        N = 1 << 19
        Y = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
        f = np.fft.rfftfreq(N, 1 / sr)
        g = TONGUES[tongue]
        m = (f > g * 0.95) & (f < g * 1.05)
        f0s.append(f[m][np.argmax(Y[m])])
        acc.append((x, sr))
    f0 = float(np.mean(f0s))
    M = np.mean([cells(x, sr, freqs(f0)) for x, sr in acc], 0)
    return f0, M - M[0, 0]


def ours(f0, vel=100, secs=1.0):
    import mido
    import blockrender as B
    tab = B.tuning_table("hybrid440")
    near = min(tab, key=lambda n: abs(np.log2(tab[n] / f0)))
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("control_change", channel=0, control=0, value=24, time=0))
    t.append(mido.Message("program_change", channel=0, program=12, time=0))
    cents = 1200 * np.log2(f0 / tab[near])
    t.append(mido.Message("pitchwheel", channel=0, pitch=int(round(cents / 200.0 * 8191)), time=0))
    t.append(mido.Message("note_on", channel=0, note=near, velocity=vel, time=0))
    t.append(mido.Message("note_off", channel=0, note=near, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    x = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    k = int(np.argmax(np.abs(x)))
    return x[max(0, k - int(0.002 * B.SR)):], B.SR


def ours_cells(f0, vel=100):
    x, sr = ours(f0, vel)
    M = cells(x, sr, freqs(f0))
    return M - M[0, 0]


NAMES = ("h1", "h2", "h3", "body1", "body2", "body3")


def show(T, O):
    err = []
    for tg, (f0, M) in T.items():
        print("== %s %.1f Hz: take/ours, dB re h1's first window" % (tg, f0))
        for i, n in enumerate(NAMES):
            print("   %-6s " % n + " ".join("%5.0f/%-5.0f" % (M[i, j], O[tg][i, j]) for j in range(len(WINS))))
            for j in range(len(WINS)):
                if M[i, j] > FLOOR:
                    err.append(O[tg][i, j] - M[i, j])
    e = np.array(err)
    print("rms %.2f dB over %d cells" % (np.sqrt(np.mean(e ** 2)), len(e)))


def fit(T, passes=4):
    """Per pass, per mode: its level by the first two windows' mean miss
    (each tongue's table), its decay (dB/s) by the slope's."""
    import tonelib
    C = tonelib.LogDrumProperties
    order = sorted(T.items(), key=lambda q: q[1][0])
    for n in range(passes):
        O = {tg: ours_cells(f0) for tg, (f0, M) in T.items()}
        show(T, O)
        pts = [list(g) for _, g in C.mode_gains_points]
        dec = list(C.mode_decays)
        # THE LOG'S 183 HZ IS TWO MODES (tonelib: 4 rings, 7 thumps): the
        # thump's level by the first window's miss, the ring's by the last two
        # windows' and its decay by their slope
        for k, (tg, (f0, M)) in enumerate(order):
            pts[k][6] *= 10 ** ((M[3, 0] - O[tg][3, 0]) / 20.0)
            pts[k][3] *= 10 ** (np.mean(M[3, 2:] - O[tg][3, 2:]) / 20.0)
        for i in range(6):
            if i == 3:
                dd = []
                for tg, (f0, M) in order:
                    if (M[3, 2:] > FLOOR).all():
                        tm = [0.5 * (WINS[j][0] + WINS[j][1]) for j in (2, 3)]
                        dd.append(np.polyfit(tm, M[3, 2:], 1)[0] - np.polyfit(tm, O[tg][3, 2:], 1)[0])
                if dd:
                    dec[3] = max(1.0, dec[3] - float(np.mean(dd)))
                continue
            dd = []
            for k, (tg, (f0, M)) in enumerate(order):
                if i > 0:
                    pts[k][i] *= 10 ** (np.mean(M[i, :2] - O[tg][i, :2]) / 20.0)
                ok = [j for j in range(len(WINS)) if M[i, j] > FLOOR]
                if len(ok) >= 2:
                    tm = [0.5 * (WINS[j][0] + WINS[j][1]) for j in ok]
                    dd.append(np.polyfit(tm, M[i, ok], 1)[0] - np.polyfit(tm, O[tg][i, ok], 1)[0])
            if dd:
                dec[i] = max(1.0, dec[i] - float(np.mean(dd)))
        C.mode_gains_points = tuple((hz, tuple(round(v, 5) for v in g))
                                    for (hz, _), g in zip(C.mode_gains_points, pts))
        C.mode_decays = tuple(round(d, 1) for d in dec)
        print("  pass %d:\n    mode_gains_points = %s\n    mode_decays = %s"
              % (n, C.mode_gains_points, C.mode_decays), flush=True)
    show(T, {tg: ours_cells(f0) for tg, (f0, M) in T.items()})


def tilt():
    """Each mode's level re h1 (first two windows), v1 -> v3, takes and ours."""
    for tg in TONGUES:
        rows = []
        for v in (1, 2, 3):
            f0, M = take(tg, v)
            O = ours_cells(f0, VEL[v])
            rows.append((v, M[:, :2].mean(1), O[:, :2].mean(1)))
        print("== %s" % tg)
        for i, n in enumerate(NAMES):
            print("   %-6s " % n + "  ".join("v%d %+5.1f/%+5.1f" % (v, a[i], b[i]) for v, a, b in rows))


CB = (63, 79, 100, 126, 159, 200, 252, 317, 400, 504, 635, 800, 1008, 1270, 1600, 2016, 2540, 3200,
      4032, 5080, 6400, 8064)
KW = ((0.0, 0.03), (0.03, 0.08))


def floor_bands(x, sr, f0):
    """The knock: in each window (KW) and third-octave band (CB), the
    spectrum's median between the modes, dB re the fundamental's peak over
    50-150 ms (past the knock). Each mode emptied +-70 Hz or +-5%, the wider:
    a 30 ms window smears a mode ~67 Hz either side, and a narrower gap read
    the fundamental's own skirt as knock -- the fit put noise ON the tongue,
    14 dB over it at the stroke. Bands left with no room are nan."""
    fs = freqs(f0)
    s = x[int(0.05 * sr):int(0.15 * sr)]
    N = 1 << 16
    f = np.fft.rfftfreq(N, 1 / sr)
    Y = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
    ref = Y[(f > f0 * 0.97) & (f < f0 * 1.03)].max()
    keep = np.ones(len(f), bool)
    for fm in fs:
        w = max(0.05 * fm, 70.0)
        keep &= ~((f > fm - w) & (f < fm + w))
    out = np.full((len(KW), len(CB)), np.nan)
    for j, (a, b) in enumerate(KW):
        s = x[int(a * sr):int(b * sr)]
        Y = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
        for i, c in enumerate(CB):
            m = keep & (f > c * 2 ** (-1 / 6.0)) & (f < c * 2 ** (1 / 6.0))
            if m.sum() >= 2:
                out[j, i] = np.median(Y[m]) - ref
    return out


def knock(passes=5):
    """The strike noise through the renderer: its table by the bands' median
    miss (both tongues, first window), its key slope by the tongues' own
    misses' difference, its fall by the two windows' drop."""
    import tonelib
    C = tonelib.LogDrumProperties
    want = {}
    for tg in TONGUES:
        acc, f0s = [], []
        for rr in (1, 2):
            x, sr = load(os.path.join(REFS, "LogDrum%s_MedM_v2_rr%d_Sum.wav" % (tg, rr)))
            f0s.append(take(tg, 2)[0])
            acc.append(floor_bands(x, sr, f0s[-1]))
        want[tg] = (float(np.mean(f0s)), np.nanmean(acc, 0))
    lo, hi = sorted(want, key=lambda t: want[t][0])
    for n in range(passes + 1):
        got = {tg: floor_bands(*ours(f0), f0) for tg, (f0, _) in want.items()}
        D = {tg: want[tg][1] - got[tg] for tg in want}
        band = np.nanmedian([D[tg][0] for tg in want], 0)
        off = {tg: np.nanmedian(D[tg][0] - band) for tg in want}
        drop_w = np.nanmedian([want[tg][1][0] - want[tg][1][1] for tg in want])
        drop_o = np.nanmedian([got[tg][0] - got[tg][1] for tg in want])
        print("  pass %d: band miss %s (mean |miss| %.1f); tongues %s; drop take %.1f ours %.1f dB"
              % (n, " ".join("%+.0f" % v if np.isfinite(v) else "--" for v in band),
                 np.nanmean(np.abs(band)), " ".join("%s %+.1f" % (t, off[t]) for t in want),
                 drop_w, drop_o), flush=True)
        if n == passes:
            break
        tab = dict(C.strike_noise_db)
        fit_ = [i for i, v in enumerate(band) if np.isfinite(v)]
        for i, (c, v) in enumerate(zip(CB, band)):
            if np.isfinite(v):
                tab[c] = round(tab[c] + float(v), 1)
        # a band no gap reaches (under the tongues, among the log's modes)
        # takes its nearest measured neighbour's level
        for i, c in enumerate(CB):
            if not np.isfinite(band[i]):
                tab[c] = tab[CB[min(fit_, key=lambda q: abs(q - i))]]
        # THE SLOPE IS READ FROM A4, two octaves over the tongues: a step in
        # it moves both tongues ~2 octaves' worth, so the table takes it back
        # at their mean pitch -- only their difference changes
        dsl = (off[hi] - off[lo]) / np.log2(want[hi][0] / want[lo][0])
        back = -dsl * np.log2(np.sqrt(want[hi][0] * want[lo][0]) / 440.0)
        tab = {c: round(v + back, 1) for c, v in tab.items()}
        C.strike_noise_db = tuple(sorted(tab.items()))
        C.strike_noise_octave_db = round(C.strike_noise_octave_db + dsl, 2)
        # the windows' centres are 15 and 55 ms apart: 40 ms
        C.strike_noise_dbs = round(max(30.0, C.strike_noise_dbs + (drop_w - drop_o) / 0.04), 1)
    print("    strike_noise_db = %s\n    strike_noise_octave_db = %s\n    strike_noise_dbs = %s"
          % (C.strike_noise_db, C.strike_noise_octave_db, C.strike_noise_dbs))


def ab(out):
    """OUT: the takes' three strokes on each tongue, then ours at the same
    pitch and velocities (VEL), 0.9 s apart, each side at one gain."""
    import blockrender as B
    gap = 0.9
    for tg in ("Lo", "Hi"):
        f0 = take(tg, 2)[0]
        rec, ours_ = [], []
        for v in (1, 2, 3):
            x, sr = load(os.path.join(REFS, "LogDrum%s_MedM_v%d_rr1_Sum.wav" % (tg, v)))
            rec.append(x[:int(gap * sr)])
            y, _ = ours(f0, VEL[v], secs=gap)
            ours_.append(y[:int(gap * sr)])
        def row(parts):
            z = np.zeros(int(gap * sr) * len(parts))
            for k, p in enumerate(parts):
                z[k * int(gap * sr):k * int(gap * sr) + len(p)] = p
            return z
        a, b = row(rec), row(ours_)
        a *= 0.5 / np.abs(a).max()
        b *= 0.5 / np.abs(b).max()
        z = np.concatenate([a, np.zeros(int(0.6 * sr)), b])
        f = os.path.join(out, "logdrum_ab_%s.wav" % tg)
        B.write_wav(f, z, z)
        print("  " + f)


def main(argv):
    ab_out = next((a[5:] for a in argv if a.startswith("--ab=")), None)
    if ab_out:
        return ab(ab_out)
    if "--knock" in argv:
        return knock()
    if "--tilt" in argv:
        return tilt()
    T = {tg: take(tg, 2) for tg in TONGUES}
    if "--fit" in argv:
        fit(T, passes=int(next((a[9:] for a in argv if a.startswith('--passes=')), 4)))
    else:
        show(T, {tg: ours_cells(f0) for tg, (f0, M) in T.items()})


if __name__ == "__main__":
    main(sys.argv[1:])
