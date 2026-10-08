#!/usr/bin/env python3
"""Fit the kit's kick and toms (GM 35/36, 41-50) to DrumGizmo's DRSKit.

    python3 examples/drum_fit.py [REFS] [--inst=kick,tom1,...] [--files] [--model] [--bands]

REFS (default ~/Documents/refs/drums/drskit) holds the instruments' samples as
examples/remote_zip.py pulled them out of DRSKit 2.1 (CC-BY 4.0; ~/Documents/
refs/sources.md): one stroke a file, ~30 velocity layers each, 13 microphones
a file, 44.1 kHz float. Each instrument is read on its own CLOSE microphones,
summed in power where it has two (the kick's two heads), because the
overheads and the room carry every other drum on the kit ringing in sympathy.

What a stroke is, read off the close microphones:

  modes   the drum's resonances, found from the settled spectrum (0.15-0.6 s
          after the strike) of the upper half of the strokes: every peak
          within 30 dB of the strongest, as a ratio to the lowest
  levels  each mode in dB under the first, early (10-80 ms, each looked for
          at its settled place times the stroke's own glide)
  decay   each mode's amplitude dB/s, its band's envelope from 30 ms until it
          has fallen 30 dB (timpani_fit.mode_decay), and the same split at
          150 ms into an EARLY and a LATE slope -- a damped head (a pillow,
          a felt strip) takes the energy out fast and then lets what is left
          ring
  glide   the first mode's pitch, its band's instantaneous frequency
          (20 ms smoothed), in cents over its settled pitch at 10, 25, 50,
          100 and 200 ms, fitted as C exp(-t/tau): the head stretched by the
          stroke, relaxing
  click   the stick or beater: third-octave levels 0.5-12 kHz over the first
          20 ms in dB re the first mode's early level, and how fast that
          band dies (dB/s over 5-40 ms)
  level   the stroke's peak, dB re the instrument's loudest stroke

--model renders the GM notes that stand for each instrument through the
percussion map, dry, and reads them the same way (one microphone: the mix).
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from timpani_fit import mode_decay, peak_near  # noqa: E402
from voicefit import analytic_env  # noqa: E402

# DRSKit's thirteen channels, as the instrument XML names them
CH = dict(AmbL=0, AmbR=1, Hihat=2, Kdrum_back=3, Kdrum_front=4, OHL=5, OHR=6, Ride=7,
          Snare_bottom=8, Snare_top=9, Tom1=10, Tom2=11, Tom3=12)
# instrument -> (directory, close microphones, the GM notes it stands for)
INST = {
    "kick":    ("Kdrum_without_contact", ("Kdrum_back", "Kdrum_front"), (36, 35)),
    "kick_in": ("Kdrum_with_contact", ("Kdrum_back", "Kdrum_front"), (36,)),
    "tom1":    ("Tom1", ("Tom1",), (48, 50)),
    "tom2":    ("Tom2", ("Tom2",), (43, 45)),
    "tom3":    ("Tom3", ("Tom3",), (41,)),
    "snare":   ("Snare", ("Snare_top", "Snare_bottom"), (38,)),
}
WHOLE_T = (0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2)
GLIDE_T = (0.010, 0.025, 0.050, 0.100, 0.200)
CLICK_BANDS = 2 ** np.arange(np.log2(500.0), np.log2(12000.0) + 1e-9, 1.0 / 3)


def read(path):
    from scipy.io import wavfile
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sr, a = wavfile.read(path)
    a = np.asarray(a, np.float64)
    if a.dtype.kind == 'i' or np.abs(a).max() > 2.0:
        a = a / 32768.0
    return (a if a.ndim == 2 else a[:, None]), sr


def strike(chs, sr):
    """The stroke's start: the summed envelope's first 5 ms past 10% of its peak."""
    w = int(0.002 * sr)
    e = np.sqrt(np.convolve(sum(c * c for c in chs), np.ones(w) / w, 'same'))
    return int(np.flatnonzero(e > 0.1 * e.max())[0])


def spectrum(x, sr, t0, t1, N=1 << 17):
    seg = x[int(t0 * sr):int(t1 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    return np.fft.rfftfreq(N, 1.0 / sr), X


def power_spectrum(chs, sr, t0, t1):
    P = None
    for x in chs:
        f, X = spectrum(x, sr, t0, t1)
        P = X ** 2 if P is None else P + X ** 2
    return f, np.sqrt(P)


def find_modes(rows_chs, sr, lo=30.0, hi=1500.0, floor_db=-30.0):
    """Peaks of the settled spectrum, summed over strokes: (Hz, dB)."""
    acc = None
    for chs in rows_chs:
        f, X = power_spectrum(chs, sr, 0.15, 0.60)
        acc = X ** 2 if acc is None else acc + X ** 2
    X = np.sqrt(acc)
    b = (f > lo) & (f < hi)
    fb, Xb = f[b], X[b]
    # local maxima over +/- 1.5% so a mode's skirt is not a second mode
    out = []
    for i in np.flatnonzero((Xb[1:-1] > Xb[:-2]) & (Xb[1:-1] >= Xb[2:])) + 1:
        near = np.abs(fb - fb[i]) < 0.015 * fb[i]
        if Xb[i] >= Xb[near].max():
            out.append((float(fb[i]), float(Xb[i])))
    top = max(a for _, a in out)
    out = [(fq, 20 * np.log10(a / top)) for fq, a in out if a > top * 10 ** (floor_db / 20.0)]
    return out


def glide(x, sr, f1):
    """Cents over f1 of the first mode at GLIDE_T, and (C, tau) of C exp(-t/tau)."""
    lo, hi = 0.85 * f1, 1.30 * f1
    N = len(x)
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    X[(fr < lo) | (fr > hi)] = 0.0
    full = np.zeros(N, complex)
    full[:len(X)] = X
    full[1:len(X) - (1 if N % 2 == 0 else 0)] *= 2.0
    z = np.fft.ifft(full)
    inst = np.diff(np.unwrap(np.angle(z))) * sr / (2 * np.pi)
    amp = np.abs(z[1:])
    w = int(0.02 * sr)
    # amplitude-weighted, so the beat against a neighbour's ring is outvoted
    inst = np.convolve(inst * amp, np.ones(w), 'same') / np.maximum(np.convolve(amp, np.ones(w), 'same'), 1e-12)
    c = 1200.0 * np.log2(np.maximum(inst, 1.0) / f1)
    pts = [float(c[int(t * sr)]) for t in GLIDE_T]
    t = np.array(GLIDE_T)
    good = np.array(pts) > 3.0
    if good.sum() >= 3:
        k, b = np.polyfit(t[good], np.log(np.array(pts)[good]), 1)
        C, tau = float(np.exp(b)), (float(-1.0 / k) if k < 0 else np.nan)
    else:
        C, tau = np.nan, np.nan
    return pts, C, tau


def band_slope(x, sr, lo, hi, t0, t1):
    e = analytic_env(x, sr, lo, hi)
    w = int(0.004 * sr)
    e = np.convolve(e, np.ones(w) / w, 'same')
    a, b = int(t0 * sr), int(t1 * sr)
    db = 20 * np.log10(np.maximum(e[a:b], 1e-12))
    s, _ = np.polyfit(np.arange(len(db)) / float(sr), db, 1)
    return -s


ENV_T = np.arange(0.03, 0.80, 0.01)


def band_env(chs, sr, fc, wd):
    """The band's envelope in dB re its own level at 30 ms, at ENV_T (30 ms
    smoothing), NaN where the file has ended or the band is in the floor."""
    e = sum(analytic_env(x, sr, fc - wd, fc + wd) ** 2 for x in chs) ** 0.5
    w = int(0.03 * sr)
    e = np.convolve(e, np.ones(w) / w, 'same')
    idx = (ENV_T * sr).astype(int)
    out = np.full(len(ENV_T), np.nan)
    ok = idx < len(e) - w
    out[ok] = 20 * np.log10(np.maximum(e[idx[ok]], 1e-15))
    out -= out[0]
    under = np.flatnonzero(out < -40.0)
    if len(under):
        out[under[0]:] = np.nan
    return out


def fit_decay(rows, nmodes):
    """Each mode's FAST decay, and one SLOW stage the drum shares: amplitude
    (1-a) e^-fast + a e^-slow, with slow = min(fast, slow) -- the pillow
    takes the energy out at each mode's own rate and leaves a remainder that
    rings at the shell's. Fitted on every band envelope (dB, 30-800 ms) of
    the strokes in `rows`, each with its own offset, soft-L1 against the
    beating of a neighbour's sympathetic ring. Rates in amplitude dB/s."""
    from scipy.optimize import least_squares
    data = [(m, r['envs'][m]) for r in rows for m in range(nmodes)]

    def model(fast, a, slow, off):
        k = np.log(10.0) / 20.0
        sl = min(fast, slow)
        return off + 20 * np.log10((1 - a) * np.exp(-k * fast * ENV_T) + a * np.exp(-k * sl * ENV_T))

    data = [(m, e[~np.isnan(e)], ~np.isnan(e)) for m, e in data if (~np.isnan(e)).sum() > 5]

    def res(p):
        # each envelope's own level is solved, not fitted: the mean of what
        # is left once the shape is taken out
        fast, a, slow = p[:nmodes], p[nmodes], p[nmodes + 1]
        out = []
        for m, e, ok in data:
            r = model(fast[m], a, slow, 0.0)[ok] - e
            out.append(r - r.mean())
        return np.concatenate(out)
    p0 = [60.0] * nmodes + [0.2, 25.0]
    lo = [1.0] * nmodes + [0.0, 1.0]
    hi = [600.0] * nmodes + [1.0, 200.0]
    q = least_squares(res, p0, bounds=(lo, hi), loss='soft_l1', f_scale=2.0)
    return q.x[:nmodes], q.x[nmodes], q.x[nmodes + 1], float(np.median(np.abs(res(q.x))))


def split_decay(chs, sr, fm, wd):
    """(early, late) amplitude dB/s of the band at fm: 30-150 ms, 150 ms on."""
    e = sum(analytic_env(x, sr, fm - wd, fm + wd) ** 2 for x in chs) ** 0.5
    w = int(0.03 * sr)
    e = np.convolve(e, np.ones(w) / w, 'same')
    out = []
    for t0, t1 in ((0.03, 0.15), (0.15, 0.6)):
        a, b = int(t0 * sr), min(len(e) - w, int(t1 * sr))
        if b - a < int(0.08 * sr):
            out.append(None)
            continue
        db = 20 * np.log10(np.maximum(e[a:b], 1e-12))
        s, _ = np.polyfit(np.arange(len(db)) / float(sr), db, 1)
        out.append(-s)
    return out


def measure(chs, sr, modes, f1):
    """One stroke, its close microphones in `chs`, against the instrument's
    settled modes (Hz)."""
    s = strike(chs, sr)
    chs = [x[s:] for x in chs]
    g, C, tau = glide(sum(chs), sr, f1)
    gl = 2 ** (g[2] / 1200.0)            # the glide at 50 ms, mid-window
    f, X = power_spectrum(chs, sr, 0.01, 0.08)
    lv, dec, envs = [], [], []
    a1 = None
    for i, fm in enumerate(modes):
        fe, a = peak_near(f, X, fm * gl, 0.04 if i else 0.10)
        if a1 is None:
            a1 = a
        lv.append(20 * np.log10(max(a, 1e-12) / a1))
        gaps = [abs(fm - o) for o in modes if o != fm]
        wd = max(2.0, min(0.05 * fm, 0.45 * min(gaps) if gaps else 0.05 * fm))
        fc = fm
        if i == 0:
            # the first mode's band spans its glide: a band at its settled
            # pitch only fills as the pitch comes down into it, and read as
            # a mode growing louder for the first 100 ms
            lo, hi = 0.88 * fm, min(1.30 * fm, 0.5 * (fm + modes[1]) if len(modes) > 1 else 1.3 * fm)
            fc, wd = 0.5 * (lo + hi), 0.5 * (hi - lo)
        d = mode_decay(sum(chs), sr, fc, wd, t0=0.03, t1=1.5, drop=30.0)
        dec.append((d,) + tuple(split_decay(chs, sr, fc, wd)))
        envs.append(band_env(chs, sr, fc, wd))
    # the click: third-octave bands over the first 20 ms
    fc, Xc = power_spectrum(chs, sr, 0.0, 0.02)
    cl = []
    for c in CLICK_BANDS:
        b = (fc >= c * 2 ** (-1 / 6.0)) & (fc < c * 2 ** (1 / 6.0))
        cl.append(10 * np.log10(np.mean(Xc[b] ** 2) / a1 ** 2 + 1e-30) if b.any() else np.nan)
    cd = band_slope(sum(chs), sr, 1500.0, 8000.0, 0.005, 0.040)
    w = int(0.01 * sr)
    pe = np.convolve(sum(x * x for x in chs), np.ones(w) / w, 'same')
    whole = [10 * np.log10(max(pe[int(t * sr)], 1e-30) / pe.max()) if int(t * sr) < len(pe) else np.nan
             for t in WHOLE_T]
    return dict(levels=lv, decays=dec, envs=envs, whole=whole, glide=g, C=C, tau=tau, click=cl, click_decay=cd,
                peak=float(max(np.abs(x).max() for x in chs)))


def layer_of(path):
    m = re.search(r'(\d+)-[^/]*\.wav$', path)
    return int(m.group(1)) if m else 0


def load(refs, inst):
    d, mics, _ = INST[inst]
    files = sorted(glob.glob(os.path.join(refs, d, "*.wav")), key=layer_of)
    out = []
    for p in files:
        a, sr = read(p)
        out.append((layer_of(p), [a[:, CH[m]] for m in mics], sr))
    return out


def analyse(strokes, title, show_files=False, modes=None, cache=None):
    sr = strokes[0][2]
    if modes is None:
        top = strokes[len(strokes) // 2:]
        found = find_modes([chs for _, chs, _ in top], sr)
        modes = [fq for fq, _ in found]
        print("== %s: %d strokes; settled modes %s" % (title, len(strokes), "  ".join(
            "%.1f (%.0f dB)" % m for m in found)))
    else:
        print("== %s: %d strokes" % (title, len(strokes)))
    f1 = modes[0]
    rows = None
    if cache:
        import hashlib
        import pickle
        key = hashlib.md5(repr((title, [round(m, 2) for m in modes], len(strokes),
                                open(__file__, 'rb').read())).encode()).hexdigest()[:12]
        cp = os.path.join(cache, "%s.pkl" % key)
        if os.path.exists(cp):
            rows = pickle.load(open(cp, "rb"))
    if rows is None:
        rows = [measure(chs, sr, modes, f1) for _, chs, _ in strokes]
        if cache:
            os.makedirs(cache, exist_ok=True)
            pickle.dump(rows, open(cp, "wb"))
    pmax = max(r['peak'] for r in rows)
    for r in rows:
        r['level'] = 20 * np.log10(r['peak'] / pmax)
    print("   ratios  " + " ".join("%6.3f" % (m / f1) for m in modes))
    groups = (("soft", [r for r in rows if r['level'] < -18]),
              ("mid", [r for r in rows if -18 <= r['level'] < -8]),
              ("loud", [r for r in rows if r['level'] >= -8]))
    for name, rs in groups:
        if not rs:
            continue
        med = lambda k: np.nanmedian(np.array([r[k] for r in rs], float), 0)
        dd = lambda j: [np.nanmedian([r['decays'][i][j] if r['decays'][i][j] is not None else np.nan
                                      for r in rs]) for i in range(len(modes))]
        print("   %-4s (%2d, %5.1f dB)" % (name, len(rs), np.median([r['level'] for r in rs])))
        print("      level dB   " + " ".join("%6.1f" % v for v in med('levels')))
        print("      decay dB/s " + " ".join("%6.0f" % v for v in dd(0)))
        print("        early    " + " ".join("%6.0f" % v for v in dd(1)))
        print("        late     " + " ".join("%6.0f" % v for v in dd(2)))
        print("      whole dB   " + " ".join("%5.1f" % v for v in med('whole'))
              + "   at t=" + ",".join("%g" % t for t in WHOLE_T))
        print("      glide cents " + " ".join("%5.0f" % v for v in med('glide'))
              + "   at t=" + ",".join("%g" % t for t in GLIDE_T)
              + "   C %.0f tau %.0f ms" % (np.nanmedian([r['C'] for r in rs]),
                                           1000 * np.nanmedian([r['tau'] for r in rs])))
        print("      click dB   " + " ".join("%5.0f" % v for v in med('click'))
              + "   (%s Hz)   dies %.0f dB/s" % (",".join("%.0f" % c for c in CLICK_BANDS[::3]),
                                                np.median([r['click_decay'] for r in rs])))
    rs = [r for r in rows if r['level'] >= -18]
    fast, a, slow, miss = fit_decay(rs, len(modes))
    print("   two-stage fit (mid+loud): fast dB/s " + " ".join("%5.0f" % v for v in fast)
          + "   slow share %.2f at %.0f dB/s  (median miss %.1f dB)" % (a, slow, miss))
    if show_files:
        for (layer, _, _), r in zip(strokes, rows):
            print("   %2d %6.1f dB  lv %s  glide %s" % (layer, r['level'], " ".join(
                "%5.1f" % v for v in r['levels'][:6]), " ".join("%4.0f" % v for v in r['glide'])))
    return modes, rows


def click_reading(note, vels=(50, 64, 80)):
    """The click bands read off renders of `note` at mid strokes, power."""
    import blockrender as B
    from drumset_check import note_file
    out = []
    for v in vels:
        L, R = B.render(note_file(0, note, vel=v, hold=1.0))[:2]
        x = np.asarray(L, np.float64) + np.asarray(R, np.float64)
        f1 = None
        import percussion_map as PM
        cls, f0 = PM.PERCUSSION[note][1], PM.PERCUSSION[note][2]
        modes = [f0 * r[0] for r in cls.DRUM_MODES]
        out.append(10 ** (np.array(measure([x], B.SR, modes, modes[0])['click']) / 10.0))
    return np.median(out, 0)


def calibrate(pick, rounds=4):
    """CLICK_CAL: render the note as it stands and with its click silenced,
    and solve, band by band in power, for what the click partials have to
    add over that floor to read as CLICK_DB does."""
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import percussion_map as PM
    done = set()
    for inst in pick:
        note = INST[inst][2][0]
        cls = PM.PERCUSSION[note][1]
        if cls in done or not getattr(cls, 'CLICK_DB', None):
            continue
        done.add(cls)
        target = 10 ** (np.array(cls.CLICK_DB, float) / 10.0)
        saved = cls.CLICK_DB
        cls.CLICK_DB = tuple([-300.0] * len(saved))
        floor = click_reading(note)
        cls.CLICK_DB = saved
        cal = np.array(cls.CLICK_CAL or [0.0] * len(saved), float)
        for k in range(rounds):
            cls.CLICK_CAL = tuple(cal)
            got = click_reading(note)
            mine = np.maximum(got - floor, 1e-3 * floor)
            want = np.maximum(target - floor, 0.1 * target)
            step = 10 * np.log10(want / mine)
            # a band read at the floor says nothing about its own gain: the
            # first round moves every band by the median, then each band by
            # at most 10 dB a round
            cal = cal + (np.median(step) if k == 0 and not any(cls.CLICK_CAL) else np.clip(step, -10, 10))
            print("   %-18s floor %s\n   %-18s read  %s\n   %-18s cal   %s" % (
                cls.__name__, " ".join("%5.0f" % v for v in 10 * np.log10(floor)), "",
                " ".join("%5.0f" % v for v in 10 * np.log10(got)), "",
                " ".join("%5.1f" % v for v in cal)))
        print("   %s.CLICK_CAL = (%s)" % (cls.__name__, ", ".join("%.1f" % v for v in cal)))


BANDS_T = (0.03, 0.1, 0.2, 0.3, 0.6)
BANDS_R = ((0.8, 1.35), (1.4, 2.4), (2.6, 4.3))


def band_shape(chs, sr, f0):
    """Power in three bands about f0 -- the thump, the head modes up to 2.4,
    the modes above -- at BANDS_T, in dB re the thump's peak. Per-mode levels
    misread two modes 7% apart (each takes the shared skirt, and their sum
    comes out 5 dB over); a band does not care how its modes are split."""
    from scipy.signal import butter, sosfiltfilt
    e = np.abs(sum(np.abs(c) for c in chs))
    t0 = int(np.flatnonzero(e > 0.1 * e.max())[0])
    out = []
    for lo, hi in BANDS_R:
        sos = butter(4, [lo * f0, hi * f0], 'bandpass', fs=sr, output='sos')
        p = sum(sosfiltfilt(sos, c) ** 2 for c in chs)
        w = int(0.02 * sr)
        p = np.convolve(p, np.ones(w) / w, 'same')
        out.append([10 * np.log10(p[t0 + int(t * sr)] + 1e-30) for t in BANDS_T])
    out = np.array(out)
    return out - out[0].max()


def bands(refs, pick):
    """--bands: the recording's three bands against the model's, by stroke."""
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import blockrender as B
    import percussion_map as PM
    from drumset_check import note_file
    print("bands %s x f0, each at t = %s s, dB re the thump's peak" % (
        "  ".join("%.1f-%.1f" % b for b in BANDS_R), ", ".join("%g" % t for t in BANDS_T)))
    row = lambda nm, e: print("  %-16s" % nm + " | ".join(" ".join("%4.0f" % v for v in r) for r in e))
    for inst in pick:
        strokes = load(refs, inst)
        note = INST[inst][2][0]
        cls, f0 = PM.PERCUSSION[note][1], PM.PERCUSSION[note][2]
        settled = f0 if not strokes else find_modes([c for _, c, _ in strokes[len(strokes) // 2:]],
                                                     strokes[0][2])[0][0]
        print("== %s (recorded %.1f Hz; GM %d at %.1f)" % (inst, settled, note, f0))
        n = len(strokes)
        for nm, grp in (("soft", strokes[n // 6:n // 3]), ("mid", strokes[n // 2:2 * n // 3]),
                        ("loud", strokes[-n // 6:])):
            row("rec " + nm, np.mean([band_shape(c, sr, settled) for _, c, sr in grp], 0))
        for v in (50, 90, 127):
            L, R = B.render(note_file(0, note, vel=v, hold=1.5))[:2]
            x = np.asarray(L, np.float64) + np.asarray(R, np.float64)
            row("model v%d" % v, band_shape([x], B.SR, f0))


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/drums/drskit")
    pick = next((a.split("=")[1].split(",") for a in argv if a.startswith("--inst=")), list(INST))
    found = {}
    for inst in (pick if "--no-refs" not in argv else []):
        strokes = load(refs, inst)
        if not strokes:
            print("== %s: no files" % inst)
            continue
        found[inst] = analyse(strokes, "DRSKit " + inst, "--files" in argv,
                              cache=os.path.join(refs, ".cache"))[0]
    if "--bands" in argv:
        return bands(refs, pick) or 0
    if "--cal" in argv:
        calibrate(pick)
    if "--model" in argv:
        os.environ.setdefault("TUNING_REFLECT", "0")
        os.environ.setdefault("TUNING_MASTER_DB", "-14")
        import blockrender as B
        from drumset_check import note_file
        vels = (36, 50, 64, 80, 100, 127)
        for inst in pick:
            for note in INST[inst][2]:
                strokes = []
                for v in vels:
                    m = note_file(0, note, vel=v, hold=1.5)
                    L, R = B.render(m)[:2]
                    strokes.append((v, [np.asarray(L, np.float64) + np.asarray(R, np.float64)], B.SR))
                # read at the class's own modes, so mode m is compared with mode m
                import percussion_map as PM
                cls = PM.PERCUSSION[note][1]
                f0 = PM.PERCUSSION[note][2]
                modes = ([f0 * r[0] for r in cls.DRUM_MODES] if hasattr(cls, 'DRUM_MODES') else None)
                analyse(strokes, "model GM %d (for %s), velocities %s" % (note, inst, vels), modes=modes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
