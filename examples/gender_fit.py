#!/usr/bin/env python3
"""GS 112.9 "Gender": the gamelan's metallophone, fitted to the gangsa of the
University of North Texas' Balinese gong kebyar Bwana Kumala (cpolcyn's
pack, CC0; sources.md) -- bronze bars over bamboo resonators, struck with a
hard wooden mallet (panggul), played in PAIRS tuned apart so they beat (the
ombak).

    python3 examples/gender_fit.py             each key's modes, levels, decays and its pair
    python3 examples/gender_fit.py --fit       the class values
    python3 examples/gender_fit.py --gong      GS 112.10 "Gamelan Gong": the big gong's modes and beat
    python3 examples/gender_fit.py --demo OUT.wav   the gong at the recording's pitch (C#2) and two above
    python3 examples/gender_fit.py --ab OUT.wav     each take, then ours at its pitch (gangsa keys, the gong)
    python3 examples/gender_fit.py --bonang    GS 112.8 "Bonang": Casa da Musica's kettles, fitted
    python3 examples/gender_fit.py --mallet    the bonang's MALLET: its burst between the modes, fitted
    python3 examples/gender_fit.py --ab-bonang OUT.wav  four of its kettles, each then ours
    python3 examples/gender_fit.py --ab-java OUT.wav    the same against Casa da Musica's JAVANESE gender
                                                    barung (CC BY 3.0; sources.md), four keys of its pelog

THE PACK holds each key twice -- the pair's two instruments, the pengumbang
and the pengisep, each file with its partner ringing beside it: the gangsa
kantilan (20 files) and pemade (19, an octave down), and the ugal (13, the
lead). Room recordings, with the rest of the gamelan ringing under them.

  strike   the file's loudest sample
  pitch    the strongest peak 0.6-0.7 s after it, 250-2600 Hz: the
           fundamental, the only mode left by then (at the strike a low
           key's third mode can stand over it)
  modes    the strongest peak in each ratio window, 2.3-3.1 and 4.6-6.0
           (hand-tuned bars: the ratios wander key to key), level 0.01-0.11 s
           after the strike re the fundamental's; its decay the slope (dB/s)
           of its band's level to 30 dB down or 1.5 s
  pair     over 0.3-2.3 s, the strongest local maximum 3-60 Hz from the
           fundamental: the partner's pitch (its offset, in cents and Hz)
"""
import glob
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

PACK = os.path.expanduser("~/Documents/refs/freesound/gamelan_bwana_kumala")
INSTRUMENTS = ("ugal", "gangsa-pemade", "gangsa-kantilan")
WINDOWS = ((2.3, 3.1), (4.6, 6.0))


def load(path):
    """The take as mono float (a wav copy beside the scratch: sox)."""
    from scipy.io import wavfile
    out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "gender_" + os.path.basename(path) + ".wav")
    if not os.path.exists(out):
        subprocess.run(["sox", path, "-b", "16", out], check=True)
    sr, x = wavfile.read(out)
    x = x.astype(np.float64) / 32768.0
    return (x.mean(1) if x.ndim > 1 else x), sr


def spectrum(x, sr, a, b):
    seg = x[a:b]
    N = 1 << 17
    return np.fft.rfftfreq(N, 1 / sr), 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) + 1e-12)


def band_decay(x, sr, k, fm):
    from scipy.signal import butter, sosfiltfilt
    bw = max(6.0, 0.006 * fm)
    y = sosfiltfilt(butter(2, [fm - bw, min(fm + bw, 0.49 * sr)], btype="band", fs=sr, output="sos"),
                    x[k:k + int(1.6 * sr)])
    w = int(0.01 * sr)
    e = 10 * np.log10(np.array([np.mean(y[j:j + w] ** 2) for j in range(0, len(y) - w, w)]) + 1e-20)
    a = 2
    stop = np.flatnonzero(e[a:] < e[a] - 30)
    b = a + (stop[0] if len(stop) else len(e) - a)
    return -np.polyfit(np.arange(a, b) * 0.01, e[a:b], 1)[0] if b - a >= 4 else np.nan


LATE = (0.2, 0.4)


def late_level(x, sr, k, f0, fm):
    """A mode's level re the fundamental's, LATE (0.2-0.4 s): after the
    mallet. Read at the strike a kettle's level holds the mallet's transient
    too, which falls ~400 dB/s and is no mode of it."""
    f, S = spectrum(x, sr, k + int(LATE[0] * sr), k + int(LATE[1] * sr))
    a0 = S[(f > f0 * 0.99) & (f < f0 * 1.01)].max()
    return float(S[(f > fm * 0.995) & (f < fm * 1.005)].max() - a0)


def key(path, windows=WINDOWS, f0_band=(250.0, 2600.0)):
    x, sr = load(path)
    k = int(np.argmax(np.abs(x)))
    if len(x) - k < int(0.8 * sr):
        return None
    f, S = spectrum(x, sr, k + int(0.6 * sr), k + int(0.7 * sr))
    ok = (f > f0_band[0]) & (f < f0_band[1])
    f0 = float(f[ok][np.argmax(S[ok])])
    # THE PAIR over 2 s (a 0.1 s window's peak is ~20 Hz wide: its skirt
    # read as a partner 15 cents off on every key): the strongest LOCAL
    # maximum 3-60 Hz from the fundamental, re it
    fl, Sl = spectrum(x, sr, k + int(0.3 * sr), min(len(x), k + int(2.3 * sr)))
    f0 = float(fl[(fl > f0 * 0.99) & (fl < f0 * 1.01)][np.argmax(Sl[(fl > f0 * 0.99) & (fl < f0 * 1.01)])])
    a1 = Sl[np.argmin(np.abs(fl - f0))]
    lm = np.r_[False, (Sl[1:-1] > Sl[:-2]) & (Sl[1:-1] > Sl[2:]), False]
    w = lm & (np.abs(fl - f0) > 3.0) & (np.abs(fl - f0) < 60.0)
    fp = float(fl[w][np.argmax(Sl[w])]) if w.any() else np.nan
    pair_db = float(Sl[w].max() - a1) if w.any() else np.nan
    fe, Se = spectrum(x, sr, k + int(0.01 * sr), k + int(0.11 * sr))
    a0 = Se[(fe > f0 * 0.99) & (fe < f0 * 1.01)].max()
    modes = []
    for lo, hi in windows:
        m = (fe > f0 * lo) & (fe < f0 * hi) & (fe < 0.45 * sr)
        if not m.any():
            modes.append((np.nan, np.nan, np.nan, np.nan))
            continue
        i = np.argmax(Se[m])
        fm = float(fe[m][i])
        modes.append((fm / f0, float(Se[m][i] - a0), band_decay(x, sr, k, fm), late_level(x, sr, k, f0, fm)))
    below = (fe > f0 * 0.4) & (fe < f0 * 0.95)
    sub_db = float(Se[below].max() - a0) if below.any() else -99.0
    return dict(f0=f0, pair_cents=1200 * np.log2(fp / f0), pair_hz=fp - f0, pair_db=pair_db, sub_db=sub_db,
                d1=band_decay(x, sr, k, f0), modes=modes)


def survey():
    rows = []
    for inst in INSTRUMENTS:
        for p in sorted(glob.glob(os.path.join(PACK, "*%s-*.flac" % inst)),
                        key=lambda q: int(re.search(r"-(\d+)\.flac$", q).group(1))):
            r = key(p)
            if r:
                r["inst"], r["n"] = inst, int(re.search(r"-(\d+)\.flac$", p).group(1))
                rows.append(r)
    return rows


# THE KEYS TRUSTED: the kantilan's all; the pemade's and the ugal's where the
# late peak is the instrument's own register (above it, another instrument in
# the room, or a mode, read as the pitch)
TRUSTED = {"gangsa-kantilan": (500.0, 2600.0), "gangsa-pemade": (400.0, 1200.0), "ugal": (250.0, 700.0)}


def fit(rows):
    """The class values: the modes' median ratios; their levels as gains
    under one contact roll-off in Hz (the panggul's: bore_corner_hz, its
    order -- a low key's third mode lands near 3 kHz and stands over the
    fundamental, a high key's near 8 kHz and is gone); the decay as
    steelbar_fit's (tonelib's D, half the band's dB/s, at 415 Hz along one
    register slope); the pair, the median offset of the pairs whose partner
    rings within 12 dB."""
    from scipy.optimize import minimize
    rs = [r for r in rows if TRUSTED[r["inst"]][0] <= r["f0"] <= TRUSTED[r["inst"]][1]]
    f0 = np.array([r["f0"] for r in rs])
    ratios = [float(np.nanmedian([r["modes"][j][0] for r in rs])) for j in range(len(WINDOWS))]
    L = np.array([[r["modes"][j][1] for j in range(len(WINDOWS))] for r in rs])
    R = np.array([[r["modes"][j][0] for j in range(len(WINDOWS))] for r in rs])

    def G(hz, fc, order):
        return -10 * np.log10(1 + (hz / fc) ** (2 * order))

    def err(v):
        g, fc, order = v[:len(WINDOWS)], v[-2], v[-1]
        if fc < 300 or not 0.3 < order < 8:
            return 1e9
        M = g[None, :] + G(f0[:, None] * R, fc, order) - G(f0, fc, order)[:, None]
        ok = np.isfinite(L) & (L > -45)
        return float(np.mean(np.abs(M[ok] - L[ok])))
    best = None
    for fc in (2000.0, 4000.0, 7000.0):
        r = minimize(err, [0.0] * len(WINDOWS) + [fc, 2.0], method="Nelder-Mead",
                     options=dict(maxfev=3000, xatol=1e-3, fatol=1e-4))
        if best is None or r.fun < best.fun:
            best = r
    g = best.x[:len(WINDOWS)]
    d1 = np.array([r["d1"] for r in rs])
    ok = np.isfinite(d1) & (d1 > 0.3)
    slope, c = np.polyfit(np.log2(f0[ok] / 415.0), np.log2(d1[ok] / 2.0), 1)
    decs = [float(2 ** c)]
    for j in range(len(WINDOWS)):
        D = np.array([r["modes"][j][2] for r in rs])
        okd = np.isfinite(D) & (D > 0.5) & np.isfinite(L[:, j]) & (L[:, j] > -40)
        decs.append(float(np.median(D[okd] / 2.0 / 2.0 ** (slope * np.log2(f0[okd] / 415.0)))))
    pc = [abs(r["pair_cents"]) for r in rs if np.isfinite(r["pair_db"]) and r["pair_db"] > -12]
    print("  %d keys trusted of %d" % (len(rs), len(rows)))
    print("  mode_ratios = %s" % ((1.0,) + tuple(round(x, 3) for x in ratios),))
    print("  mode_gains = %s   (dB %s; miss %.2f dB)" % ((1.0,) + tuple(round(10 ** (x / 20), 4) for x in g),
                                                       " ".join("%+.1f" % x for x in g), best.fun))
    print("  bore_corner_hz = %.0f, bore_order = %.2f   (the panggul's contact)" % (best.x[-2], best.x[-1]))
    print("  mode_decays = %s, decay_register_slope = %.3f" % (tuple(round(d, 2) for d in decs), slope))
    print("  the pair: %d pairs, %.1f cents apart (median; quartiles %.0f-%.0f)"
          % (len(pc), np.median(pc), np.percentile(pc, 25), np.percentile(pc, 75)))


# THE BIG GONG (gong ageng): the pack's gong 00, 01, 03 -- one strike each,
# left to ring (02 holds three, 04-08 a small gong at 413 Hz, the kempli's,
# 09-12 the low gong played otherwise)
GONG_TAKES = ("00", "01", "03")
GONG_MODES = (1.0, 1.471, 1.65, 2.0, 2.076, 2.594, 2.80, 3.585)
GONG_BANDS = (250, 500, 1000, 2000, 4000, 8000)


def gong():
    """Each mode's level re the fundamental (0.05-0.3 s) and decay; the
    fundamental's beat (its envelope's modulation over 12 s) and swell (its
    peak's time); the strike's octave bands above 250 Hz re the fundamental,
    0-0.1 s, and how fast they fall."""
    from scipy.signal import butter, sosfiltfilt
    rows = []
    for n in GONG_TAKES:
        p = glob.glob(os.path.join(PACK, "*gong-%s.flac" % n))[0]
        x, sr = load(p)
        k = int(np.argmax(np.abs(x)))
        fl, Sl = spectrum(x, sr, k + int(0.2 * sr), k + int(8.2 * sr))
        ok = (fl > 50) & (fl < 100)
        f0 = float(fl[ok][np.argmax(Sl[ok])])
        fe, Se = spectrum(x, sr, k + int(0.05 * sr), k + int(0.3 * sr))
        a0 = Se[(fe > f0 * 0.985) & (fe < f0 * 1.015)].max()
        modes = []
        for r in GONG_MODES:
            m = (fe > f0 * r * 0.985) & (fe < f0 * r * 1.015)
            modes.append((float(Se[m].max() - a0), band_decay(x, sr, k, f0 * r)))
        y = sosfiltfilt(butter(2, [f0 - 4, f0 + 4], btype="band", fs=sr, output="sos"), x[k:])
        w = int(0.02 * sr)
        e = 10 * np.log10(np.convolve(y ** 2, np.ones(w) / w, "same")[::w] + 1e-20)
        t = np.arange(len(e)) * 0.02
        sel = (t > 0.3) & (t < min(12.0, t[-1]))
        tr = np.polyfit(t[sel], e[sel], 1)
        res = e[sel] - np.polyval(tr, t[sel])
        R = np.abs(np.fft.rfft((res - res.mean()) * np.hanning(len(res)), 8 * len(res)))
        fr = np.fft.rfftfreq(8 * len(res), 0.02)
        okr = (fr > 0.2) & (fr < 10)
        bands = []
        for lo in GONG_BANDS:
            yb = sosfiltfilt(butter(2, [lo, min(2 * lo, 0.45 * sr)], btype="band", fs=sr, output="sos"),
                             x[k:k + int(1.0 * sr)])
            eb = 10 * np.log10(np.convolve(yb ** 2, np.ones(w) / w, "same")[::w] + 1e-20)
            bands.append((float(eb[:5].max() - e[:5].max()), float(eb[:5].max() - eb[25:30].mean())))
        rows.append(dict(n=n, f0=f0, modes=modes, d1=-tr[0], beat=float(fr[okr][np.argmax(R[okr])]),
                         beat_pp=float(np.subtract(*np.percentile(res, [95, 5]))),
                         peak_s=float(t[np.argmax(e[:100])]), bands=bands))
    for r in rows:
        print("  gong-%s  f0 %.2f Hz  decay %.2f dB/s  beat %.2f Hz (%.1f dB p-p)  peak at %.2f s"
              % (r["n"], r["f0"], r["d1"], r["beat"], r["beat_pp"], r["peak_s"]))
        print("     modes: %s" % "  ".join("x%g %+.0f dB %.1f dB/s" % (q, l, d) for q, (l, d) in zip(GONG_MODES, r["modes"])))
        print("     strike, bands re the fundamental (and fallen by 0.5 s): %s"
              % "  ".join("%d %+.0f (%.0f)" % (b, l, d) for b, (l, d) in zip(GONG_BANDS, r["bands"])))
    return rows


def demo(out):
    """GamelanGong (112.10, the SC-88 map) struck at C#2 -- the recording's 69.3
    Hz -- left 9 s, then at G#2 and C#3, 6 s each."""
    import mido
    import blockrender as B
    from efx_demo import _sx
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))
    for c, v in ((0, 10), (32, 2)):
        tr.append(mido.Message("control_change", channel=0, control=c, value=v))
    tr.append(mido.Message("program_change", channel=0, program=112))
    t = 0
    for note, secs in ((37, 9.0), (44, 6.0), (49, 6.0)):
        tr.append(mido.Message("note_on", channel=0, note=note, velocity=100, time=t))
        tr.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=int(secs * 960)))
        t = 0
    L, R = B.render(mf, "even")[:2]
    x = np.stack([np.asarray(L), np.asarray(R)], 1)
    x = x / np.abs(x).max() * 10 ** (-1 / 20.0)
    from scipy.io import wavfile
    wavfile.write(out, B.SR, (x * 32767).astype(np.int16))
    print("  wrote %s" % out)


AB_KEYS = (("gangsa-pemade", "08"), ("gangsa-kantilan", "00"), ("gangsa-kantilan", "04"),
           ("gangsa-kantilan", "09"))


def _ours_at(program, bank, hz, secs):
    """One note of PROGRAM.BANK (the SC-88 map) at HZ exactly: the nearest key,
    bent the rest (GS's +-2 semitones)."""
    import mido
    import blockrender as B
    from efx_demo import _sx
    midi = 69 + 12 * np.log2(hz / 440.0)
    key = int(round(midi))
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))
    for c, v in ((0, bank), (32, 2)):
        tr.append(mido.Message("control_change", channel=0, control=c, value=v))
    tr.append(mido.Message("program_change", channel=0, program=program))
    tr.append(mido.Message("pitchwheel", channel=0, pitch=int(round((midi - key) / 2.0 * 8191))))
    tr.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=10))
    tr.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    L, R = B.render(mf, "even")[:2]
    x = 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64))
    k = int(np.argmax(np.abs(x)))
    return x[max(0, k - int(0.05 * B.SR)):][:int(secs * B.SR)], B.SR


CDM = os.path.expanduser("~/Documents/refs/freesound/gamelan_cdm")
JAVA_KEYS = ("gender_gbpl3", "gender_gbpl2h", "gender_gbpl6h", "gender_gbpl2hh")
BONANG_KEYS = ("bonang_bbpl2h", "bonang_bbsl3h", "bonang_bbpl5h", "bonang_bpsl2")


def ab_pairs(jobs, out):
    """Each take from 50 ms before its loudest sample, then ours at its pitch
    (the strongest peak 0.3-2.3 s in, between LO and HI Hz), both at one
    level over their bodies (0.2-1 s), a second between. JOBS: (path, program, bank, secs, lo, hi)."""
    from scipy.io import wavfile
    parts = []
    for p, prog, bank, secs, lo, hi in jobs:
        x, sr = load(p)
        k = int(np.argmax(np.abs(x)))
        rec = x[max(0, k - int(0.05 * sr)):][:int(secs * sr)]
        f, S = spectrum(x, sr, k + int(0.3 * sr), min(len(x), k + int(2.3 * sr)))
        ok = (f > lo) & (f < hi)
        hz = float(f[ok][np.argmax(S[ok])])
        ours, sr2 = _ours_at(prog, bank, hz, secs)
        assert sr2 == sr
        # LEVELLED ON THE BODY, 0.2-1 s: by the peak, a take's mallet click
        # set its level and its ring played quieter than ours, which has none
        body = [np.sqrt(np.mean(y[int(0.2 * sr):int(1.0 * sr)] ** 2)) for y in (rec, ours)]
        g = [0.1 / max(b, 1e-12) for b in body]
        pk = max(np.abs(rec).max() * g[0], np.abs(ours).max() * g[1])
        for y, gi in zip((rec, ours), g):
            parts += [y * gi * 0.7 / pk, np.zeros(sr)]
        print("  %s: %.1f Hz" % (os.path.basename(p), hz))
    y = np.concatenate(parts)
    wavfile.write(out, sr, (y * 32767).astype(np.int16))
    print("  wrote %s" % out)


def ab(out):
    """Four gangsa keys (3 s), the big gong (9 s). Ours is 112.9, the Gender,
    without the gangsa's pair (tonelib.GangsaPairProperties has it); the
    takes carry the partner ringing beside them."""
    jobs = [(glob.glob(os.path.join(PACK, "*%s-%s.flac" % (inst, n)))[0], 112, 9, 3.0, 250, 2600)
            for inst, n in AB_KEYS]
    jobs.append((glob.glob(os.path.join(PACK, "*gong-00.flac"))[0], 112, 10, 9.0, 50, 100))
    ab_pairs(jobs, out)


def ab_java(out):
    """The Javanese gender barung's keys (4 s): what Roland's "Gender" names,
    against ours fitted to the Balinese gangsa."""
    jobs = [(glob.glob(os.path.join(CDM, "*__%s.wav" % n))[0], 112, 9, 4.0, 150, 2600) for n in JAVA_KEYS]
    ab_pairs(jobs, out)


# THE BONANG: Casa da Musica's kettles (bonang barung and panerus, pelog and
# slendro). Its modes, read as the gender's: a bossed kettle's partner at
# ~1.5-1.65 and the weaker ones near 2 and 2.8-3.8
BONANG_WINDOWS = ((1.42, 1.72), (1.9, 2.12), (2.6, 3.9))


def bonang():
    """Every kettle read as key() reads a bar (pitch 0.6-0.7 s in, 200-1400
    Hz); kept where nothing under the fundamental stands within 15 dB of it at
    the strike (a neighbour ringing, or a pitch misread). The modes' median
    ratios and levels at the strike (late_level's after the mallet shown); the decays as medians (tonelib's D, half the band's
    dB/s): they do not climb the register."""
    rows = []
    for p in sorted(glob.glob(os.path.join(CDM, "*__bonang_*.wav"))):
        r = key(p, BONANG_WINDOWS, (200.0, 1400.0))
        if r:
            r["name"] = os.path.basename(p).split("__")[-1][:-4]
            rows.append(r)
    rs = [r for r in rows if r["sub_db"] < -15]
    print("  %d kettles, %d kept" % (len(rows), len(rs)))
    f0 = np.array([r["f0"] for r in rs])
    d1 = np.array([r["d1"] for r in rs])
    ok = np.isfinite(d1) & (d1 > 0.3)
    slope, c = np.polyfit(np.log2(f0[ok] / 415.0), np.log2(d1[ok] / 2.0), 1)
    # NO REGISTER LAW (slope ~0.04): every decay a MEDIAN, the fundamental's
    # over the strikes under 15 dB/s (7 of 33 were damped by the player,
    # 22-32 dB/s, and a regression through them bent the level)
    ratios, gains, decs = [1.0], [1.0], [float(np.median(d1[ok & (d1 < 15)]) / 2.0)]
    for j, (lo, hi) in enumerate(BONANG_WINDOWS):
        R = np.array([r["modes"][j][0] for r in rs])
        L = np.array([r["modes"][j][1] for r in rs])
        D = np.array([r["modes"][j][2] for r in rs])
        okl = np.isfinite(L) & (L > -45)
        okd = okl & np.isfinite(D) & (D > 0.5) & (L > -35)
        # the level AFTER THE MALLET too, for comparison: carried back along a
        # mode's decay it lands at nonsense for the broad mode near 3 (-7 dB
        # against -31 at the strike) -- its "decay" is the mallet's, so the
        # strike's reading stays
        LL = np.array([r["modes"][j][3] for r in rs])
        okll = np.isfinite(LL) & (LL > -50)
        print("   window %.2f-%.2f: after the mallet (0.2-0.4 s) %+.1f dB (%d)" % (lo, hi, np.median(LL[okll]), okll.sum()))
        ratios.append(round(float(np.median(R[okl])), 3))
        gains.append(round(float(10 ** (np.median(L[okl]) / 20)), 4))
        decs.append(round(float(np.median(D[okd]) / 2.0), 2))
        print("   window %.2f-%.2f: ratio %.3f (IQR %.3f-%.3f), level %+.1f dB (IQR %.1f), %d of %d"
              % (lo, hi, ratios[-1], *np.percentile(R[okl], [25, 75]), np.median(L[okl]),
                 np.subtract(*np.percentile(L[okl], [75, 25])), okl.sum(), len(rs)))
    print("  f0 %.0f-%.0f Hz" % (f0.min(), f0.max()))
    print("  mode_ratios = %s" % (tuple(ratios),))
    print("  mode_gains = %s" % (tuple(gains),))
    print("  mode_decays = %s  (the register slope %.3f: none)" % (tuple(round(d, 2) for d in decs), slope))
    pd = np.array([r["pair_db"] for r in rs])
    print("  a partner within 12 dB on %d of %d kettles" % ((pd > -12).sum(), len(rs)))


def bonang_takes():
    """[(path, f0)]: the kettles bonang() keeps."""
    out = []
    for p in sorted(glob.glob(os.path.join(CDM, "*__bonang_*.wav"))):
        r = key(p, BONANG_WINDOWS, (200.0, 1400.0))
        if r and r["sub_db"] < -15:
            out.append((p, r["f0"]))
    return out


def mallet(passes=5):
    """THE MALLET'S OWN SOUND (Ben: "what it is missing is the sound of the
    reaction of the mallet itself"): the padded stick meeting the boss, a
    burst between the kettle's modes. steelbar_fit's pluck, on the kettles:
    the noise between the partials (noise_profile: third octaves over 0-5 and
    5-15 ms, re the fundamental), take against ours through the renderer at
    each kettle's pitch; tonelib's strike_noise rows moved by the median
    difference -- the table from the first 5 ms, its octave slope over the
    kettles, its rate from 5-15 ms. NO TAIL: a first fit took a slower tail
    from 15-60 ms and it was the room's floor and the other kettles (it ran
    to its slowest bound, and ours 10-24 dB over the takes below 1.4 kHz).
    The best pass by the two windows' mean miss. Prints the class values."""
    import steelbar_fit as SB
    import tonelib as T
    cls = T.BonangProperties
    modes = (1.0,) + tuple(cls.mode_ratios[1:])
    takes = bonang_takes()
    rec, f0s = [], []
    for p, f0 in takes:
        x, sr = load(p)
        rec.append(SB.noise_profile(x, sr, f0, modes)[:2])
        f0s.append(f0)
    rec = np.array(rec)
    reg = np.log2(np.array(f0s) / 440.0)
    if not getattr(cls, "strike_noise_db", ()):
        cls.strike_noise_db = tuple((int(round(c)), -30.0) for c in SB.A3C)
        cls.strike_noise_octave_db = 0.0
        cls.strike_noise_dbs = 1000.0
        cls.strike_noise_fade_s = 0.0005
        cls.strike_noise_len_s = 0.1
    best = None
    for it in range(passes + 1):
        ours = []
        for f0 in f0s:
            y, sr2 = _ours_at(112, 8, f0, 0.5)
            ours.append(SB.noise_profile(y, sr2, f0, modes)[:2])
        D = rec - np.array(ours)
        w = [float(np.nanmedian(D[:, j])) for j in range(2)]
        miss = float(np.nanmean(np.abs(np.nanmedian(D, 0))))
        print("  pass %d: take - ours, 0-5 ms %+.1f, 5-15 ms %+.1f (median); by band %.2f dB"
              % (it, w[0], w[1], miss), flush=True)
        if best is None or miss < best[0]:
            best = (miss, cls.strike_noise_db, cls.strike_noise_octave_db, cls.strike_noise_dbs, D)
        if it == passes:
            break
        band = np.nanmedian(D[:, 0], 0)
        km = np.nanmedian(D[:, 0] - band, 1)
        cls.strike_noise_octave_db += 0.5 * float(np.polyfit(reg, np.nan_to_num(km), 1)[0])
        old = dict(cls.strike_noise_db)
        cls.strike_noise_db = tuple(
            (int(round(c)), round(float(np.interp(np.log(c), np.log(list(old)), list(old.values()))
                                        + 0.6 * np.clip(np.nan_to_num(b), -12, 12)), 1))
            for c, b in zip(SB.A3C, band))
        cls.strike_noise_dbs = round(max(150.0, cls.strike_noise_dbs - 0.6 * (w[1] - w[0]) / 0.0075), 1)
    miss, cls.strike_noise_db, cls.strike_noise_octave_db, cls.strike_noise_dbs, D = best
    print("  best: by band %.2f dB" % miss)
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))
    print("    strike_noise_octave_db = %.3f" % cls.strike_noise_octave_db)
    print("    strike_noise_dbs = %.1f" % cls.strike_noise_dbs)
    print("  residual take - ours by band, per window:")
    print("  Hz      " + " ".join("%5.1f" % (c / 1000) for c in SB.A3C))
    for j, (a, b) in enumerate(SB.PLUCK_WINDOWS[:2]):
        print("  %3.0f-%3.0f " % (a * 1e3, b * 1e3) + " ".join("%5.0f" % v for v in np.nanmedian(D[:, j], 0)))


def ab_bonang(out):
    """Four of Casa da Musica's kettles (3 s), each then ours (112.8)."""
    jobs = [(glob.glob(os.path.join(CDM, "*__%s.wav" % n))[0], 112, 8, 3.0, 200, 1400) for n in BONANG_KEYS]
    ab_pairs(jobs, out)


def main(argv):
    if "--mallet" in argv:
        mallet()
        return 0
    if "--ab-bonang" in argv:
        ab_bonang(argv[argv.index("--ab-bonang") + 1])
        return 0
    if "--bonang" in argv:
        bonang()
        return 0
    if "--ab-java" in argv:
        ab_java(argv[argv.index("--ab-java") + 1])
        return 0
    if "--ab" in argv:
        ab(argv[argv.index("--ab") + 1])
        return 0
    if "--demo" in argv:
        demo(argv[argv.index("--demo") + 1])
        return 0
    if "--gong" in argv:
        gong()
        return 0
    rows = survey()
    if "--fit" in argv:
        return fit(rows) or 0
    print("  inst             #     f0   pair (cents, Hz, dB)    D1 dB/s | mode 2: ratio, dB, dB/s | mode 3")
    for r in rows:
        print("  %-15s %2d %7.1f  %+6.0f %+6.1f %+6.1f  %6.1f | %s" % (
            r["inst"], r["n"], r["f0"], r["pair_cents"], r["pair_hz"], r["pair_db"], r["d1"],
            " | ".join("%.2f %+5.0f %6.0f" % m for m in r["modes"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
