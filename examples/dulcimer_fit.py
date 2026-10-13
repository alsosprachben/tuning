#!/usr/bin/env python3
"""Measure GM 15's hammered dulcimer against Kevin Kemp's (Pianobook "Lite
Hammered Dulcimer", measured only; sources.md), and our render the same way.

    python3 examples/dulcimer_fit.py measure [--notes=50,62,...]
    python3 examples/dulcimer_fit.py spectrum [--params=a,b] [--maxfev=N]
    python3 examples/dulcimer_fit.py body [--passes=N]
    python3 examples/dulcimer_fit.py decay [--params=a,b] [--maxfev=N]
    python3 examples/dulcimer_fit.py peaks [--params=a,b] [--maxfev=N]
    python3 examples/dulcimer_fit.py peakbody [--passes=N]
    python3 examples/dulcimer_fit.py strike [--passes=N]   (writes tonelib.py)
    python3 examples/dulcimer_fit.py sympathy [--fit] [--maxfev=N]
    python3 examples/dulcimer_fit.py halo [--rounds=N]   (writes tonelib.py)
    python3 examples/dulcimer_fit.py ab OUT.wav [--note-s=2.5]   recording, then model, key by key

The recordings are one take a note, D3-F6, one condenser, each cut at 5.0 s;
the note is read from its NAME (D3.wav, G#4.wav, Eb5.wav). Per note, with
upright_fit's tools (a struck steel string is a struck steel string):

  B       inharmonicity from the partials' peaks
  ladder  partials 1-12, dB re the strongest, 30-530 ms after the onset
  T20     seconds for each octave band to fall 20 dB from its peak
  beats   each partial's level wobble, 0.3-3 s: the course's strings beating

and the same for our render of program 15, held 5 s.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

REFS = os.path.expanduser("~/Documents/refs/dulcimer/lite/ds/Hammered Dulcimer")
PROGRAM = 15
VEL = 100
HOLD = 5.0
STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def key_of_name(nm):
    """'G#4' / 'Eb5' / 'D3' -> MIDI key."""
    k = STEP[nm[0]] + (1 if "#" in nm else -1 if nm[1:2] == "b" else 0)
    return (int(nm[-1]) + 1) * 12 + k


def recordings():
    out = {}
    for p in glob.glob(os.path.join(REFS, "*.wav")):
        out[key_of_name(os.path.splitext(os.path.basename(p))[0])] = p
    return out


def measure(x, sr, key):
    found, f0, B = U.partials(x, sr, key)
    return dict(f0=f0, B=B, ladder=U.ladder(found) if found else [-99.0] * 12,
                decay=U.band_decay(x, sr), beats=U.beating(x, sr, key))


def show_measure(keys):
    refs = recordings()
    keys = keys or sorted(refs)
    print("  key   B rec    B ours   T20 by octave band 63..8k (rec / ours)")
    rows = []
    for k in keys:
        x, sr = U.load(refs[k])
        r = measure(x, sr, k)
        y, ysr = U.render(PROGRAM, k, VEL, HOLD)
        o = measure(y, ysr, k)
        rows.append((k, r, o))
        t = " ".join("%4.1f/%4.1f" % (a[0], b[0]) for a, b in zip(r["decay"], o["decay"]))
        print("  %3d %8.2e %8.2e   %s" % (k, r["B"], o["B"], t))
    print("\n  ladder, partials 1-12 dB re strongest (rec, then ours)")
    for k, r, o in rows:
        print("  %3d rec  %s" % (k, " ".join("%5.0f" % v for v in r["ladder"])))
        print("      ours %s" % " ".join("%5.0f" % v for v in o["ladder"]))
    print("\n  beating: partial (wobble dB @ Hz), rec | ours")
    for k, r, o in rows:
        f = lambda bs: " ".join("%d(%.1f@%.1f)" % b for b in bs[:6])
        print("  %3d %s\n      %s" % (k, f(r["beats"]), f(o["beats"])))


def thirds_set():
    """{key: upright_fit.thirds} over every recording: the third-octave
    spectrum 30-530 ms from the fundamental up, dB re the strongest band."""
    return {k: U.thirds(*U.load(p), k) for k, p in sorted(recordings().items())}


# BY REGISTER, NOT BY NOTE. One take a note, its courses beating and the
# undamped strings answering, makes every key's ladder jagged by +-10 dB in
# the recording and in ours alike, and that jag is most of a per-key error
# (10.9 dB after the fit). What is heard is the register's shape: each
# register's mean third-octave spectrum, ours against the recording's.
REGISTERS = ((50, 57), (59, 67), (68, 77), (78, 89))


def reg_mean(spectra):
    import warnings
    out = []
    for lo, hi in REGISTERS:
        rows = [v for k, v in spectra.items() if lo <= k <= hi]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = np.nanmean(np.array(rows), 0)
            n = np.sum(np.isfinite(np.array(rows)), 0)
        out.append(np.where(n >= 3, m, np.nan))
    return out


def thirds_err(rec, hold=1.0):
    """[per-register residual arrays] (ours - recorded), and the model's
    per-key spectra."""
    ours = {}
    for k in rec:
        y, sr = U.render(PROGRAM, k, VEL, hold)
        ours[k] = U.thirds(y, sr, k)
    R, M = reg_mean(rec), reg_mean(ours)
    return [(m - r)[np.isfinite(m - r)] for m, r in zip(M, R)], [m - r for m, r in zip(M, R)]


def nelder(cls, names, f_err, steps, maxfev, label):
    from scipy.optimize import minimize
    seen = {}

    def f(x):
        kx = tuple(np.round(x, 4))
        if kx not in seen:
            for n, v in zip(names, x):
                setattr(cls, n, float(v))
            seen[kx] = f_err()
            print("    %s  %s %.3f" % (" ".join("%s=%.4f" % (n, v) for n, v in zip(names, x)), label,
                                       seen[kx]), flush=True)
        return seen[kx]
    x0 = np.array([float(getattr(cls, n)) for n in names])
    e0 = f(x0)
    res = minimize(f, x0, method="Nelder-Mead",
                   options=dict(xatol=0.005, fatol=0.003, maxfev=maxfev,
                                initial_simplex=[x0] + [x0 + steps.get(n, 0.2) * np.eye(len(x0))[i]
                                                        for i, n in enumerate(names)]))
    for n, v in zip(names, res.x):
        setattr(cls, n, float(v))
    print("  BEST: %s  %s %.3f (from %.3f)" % (", ".join("%s %.4f" % (n, v) for n, v in zip(names, res.x)),
                                              label, res.fun, e0))


# THE LADDER over the whole band (`spectrum`): where the hammer strikes and
# how the partials fall with number and register, against each key's third
# octaves -- the harpsichord's fit (harpsi_fit.py spectrum), every key.
SPECTRUM = "strike_point,strike_depth,tonal_dampening,octave_dampening"


def fit_spectrum(opts):
    import tonelib as T
    cls = T.HammeredDulcimerProperties
    names = opts.get("--params", SPECTRUM).split(",")
    rec = thirds_set()
    nelder(cls, names, lambda: float(np.sqrt(np.mean(np.concatenate(thirds_err(rec)[0]) ** 2))),
           {"strike_point": 0.03, "strike_depth": 0.2, "tonal_dampening": 0.2, "octave_dampening": 0.1},
           int(opts.get("--maxfev", 60)), "thirds rms")


def fit_body(opts):
    """body_trim_db: the residual's shape by absolute frequency, a one-octave
    running mean, half of it a pass, the best pass kept (harpsi_fit body)."""
    import tonelib as T
    cls = T.HammeredDulcimerProperties
    C = np.sqrt(U.E3[:-1] * U.E3[1:])
    rec = thirds_set()
    trim = dict(cls.body_trim_db) if cls.body_trim_db else {}
    passes = int(opts.get("--passes", 4))
    best = None
    for it in range(passes + 1):
        D, full = thirds_err(rec)
        rms = float(np.sqrt(np.mean(np.concatenate(D) ** 2)))
        print("  pass %d: register thirds rms %.2f dB" % (it, rms), flush=True)
        if best is None or rms < best[0]:
            best = (rms, cls.body_trim_db)
        if it == passes:
            break
        acc = [[v for v in col if np.isfinite(v)] for col in np.array(full).T]
        cs = [float(c) for c, a in zip(C, acc) if len(a) >= 1]
        rv = np.array([float(np.mean(a)) for a in acc if len(a) >= 1])
        lc = np.log2(cs)
        sm = np.array([rv[np.abs(lc - l) <= 0.5].mean() for l in lc])
        for c, v in zip(cs, sm):
            trim[c] = float(np.clip(trim.get(c, 0.0) - 0.5 * v, -12, 12))
        # CENTRED: every key is read re its own strongest band, so a trim's
        # mean does nothing but drift -- uncentred, every band ran to the clip
        mu = float(np.mean(list(trim.values())))
        cls.body_trim_db = tuple((round(c), round(v - mu, 1)) for c, v in sorted(trim.items()))
        trim = dict(cls.body_trim_db)
    cls.body_trim_db = best[1]
    print("  best %.2f dB" % best[0])
    print("    body_trim_db = (%s)" % ", ".join("(%d, %.1f)" % (c, v) for c, v in (cls.body_trim_db or ())))


# THE DECAY by third octave (`decay`): harpsi_fit.band_decays, 0.05-1.2 s,
# compared as log rates, on the class's law in Hz (HammeredDulcimerProperties.
# harmonic_decay). The recordings fade out after ~3 s, so nothing
# later is read.
DECAY = "decay_db,decay_hz_db,decay_hz_power"


def fit_decay(opts):
    import tempfile
    import tonelib as T
    import harpsi_fit as H
    from roomtail import write_wav
    cls = T.HammeredDulcimerProperties
    names = opts.get("--params", DECAY).split(",")
    hz = lambda k: 440.0 * 2 ** ((k - 69) / 12.0)
    rec = {k: H.band_decays(p, hz(k)) for k, p in sorted(recordings().items())}
    tmp = tempfile.mkdtemp(prefix="dulc_decay_")

    def err():
        E = []
        for k, r in rec.items():
            y, sr = U.render(PROGRAM, k, VEL, 1.5)
            p = os.path.join(tmp, "d.wav")
            write_wav(p, np.stack([y, y], 1) / max(np.abs(y).max(), 1e-12) * 0.5, sr)
            m = H.band_decays(p, hz(k))
            E += [np.log(m[c] / v) for c, v in r.items() if c in m and v > 0.5 and m[c] > 0.5]
        return float(np.sqrt(np.mean(np.square(E))))
    nelder(cls, names, err, {"decay_db": 2.0, "decay_hz_db": 0.5, "decay_hz_power": 0.2}, int(opts.get("--maxfev", 60)), "log-rate rms")


# THE PARTIALS' OWN PEAKS (`peaks`, `peakbody`), NOT THE BANDS. A dulcimer has
# no dampers: every course answers, and the treble bridge's other side rings a
# fifth away -- the recordings carry energy BETWEEN the partials, ~20 dB under
# the note (E4: -20 dB in the bands between h1 and h2, ours at the floor). A
# band fit counts it, and the model, with no sympathetic strings, can only
# meet it by lifting its own partials: the mid-range raised to stand in for
# the sympathy (Ben: the recordings' mid-range "a little bit thinner"). Read
# at each partial's peak (upright_fit.partials, 30-530 ms) the sympathy
# between them is left out. Each key's level is free (its median difference
# removed), so only the ladder's shape is compared; to 12 kHz, within 45 dB.
PEAK_N = 40


def peaks_of(x, sr, k):
    found, f0, B = U.partials(x, sr, k, PEAK_N)
    return {n: (hz, db) for n, hz, db in found if hz < 12000.0}


def peaks_set():
    return {k: peaks_of(*U.load(p), k) for k, p in sorted(recordings().items())}


def peaks_err(rec):
    """[(key, n, Hz, ours - recorded dB)], each key's median removed."""
    rows = []
    for k, r in rec.items():
        y, sr = U.render(PROGRAM, k, VEL, 1.0)
        m = peaks_of(y, sr, k)
        top = max(v[1] for v in r.values())
        d = [(n, r[n][0], m[n][1] - r[n][1]) for n in r if n in m and r[n][1] > top - 45.0]
        if len(d) < 3:
            continue
        med = float(np.median([q[2] for q in d]))
        rows += [(k, n, hz, v - med) for n, hz, v in d]
    return rows


def fit_peaks(opts):
    import tonelib as T
    cls = T.HammeredDulcimerProperties
    names = opts.get("--params", "tonal_dampening,octave_dampening").split(",")
    rec = peaks_set()
    nelder(cls, names, lambda: float(np.sqrt(np.mean([q[3] ** 2 for q in peaks_err(rec)]))),
           {"tonal_dampening": 0.2, "octave_dampening": 0.1}, int(opts.get("--maxfev", 50)), "peaks rms")


def fit_peakbody(opts):
    """body_trim_db from the partials' residual by absolute frequency: a
    third-octave grid, each point the mean of the partials within half an
    octave of it, half of it a pass, centred, the best pass kept."""
    import tonelib as T
    cls = T.HammeredDulcimerProperties
    rec = peaks_set()
    C = np.sqrt(U.E3[:-1] * U.E3[1:])
    C = C[(C > 120) & (C < 12000)]
    trim = dict(cls.body_trim_db) if cls.body_trim_db else {}
    passes = int(opts.get("--passes", 5))
    best = None
    for it in range(passes + 1):
        rows = peaks_err(rec)
        rms = float(np.sqrt(np.mean([q[3] ** 2 for q in rows])))
        print("  pass %d: peaks rms %.2f dB" % (it, rms), flush=True)
        if best is None or rms < best[0]:
            best = (rms, cls.body_trim_db)
        if it == passes:
            break
        lh = np.log2([q[2] for q in rows])
        dv = np.array([q[3] for q in rows])
        for c in C:
            w = np.abs(lh - np.log2(c)) <= 0.5
            if w.sum() >= 5:
                trim[float(c)] = float(np.clip(trim.get(float(c), 0.0) - 0.5 * dv[w].mean(), -15, 15))
        mu = float(np.mean(list(trim.values())))
        cls.body_trim_db = tuple((round(c), round(v - mu, 1)) for c, v in sorted(trim.items()))
        trim = dict(cls.body_trim_db)
    cls.body_trim_db = best[1]
    print("  best %.2f dB" % best[0])
    print("    body_trim_db = (%s)" % ", ".join("(%d, %.1f)" % (c, v) for c, v in (cls.body_trim_db or ())))


def show_peaks():
    """The residual by absolute frequency, third octaves: where ours is
    over (+) or under (-) the recordings' partials."""
    rows = peaks_err(peaks_set())
    lh = np.log2([q[2] for q in rows])
    dv = np.array([q[3] for q in rows])
    C = np.sqrt(U.E3[:-1] * U.E3[1:])
    print("  rms %.2f dB" % np.sqrt(np.mean(dv ** 2)))
    for c in C[(C > 120) & (C < 12000)]:
        w = np.abs(lh - np.log2(c)) <= 1 / 6.0
        if w.sum() >= 3:
            print("   %6d Hz  %+5.1f dB  (%d)" % (c, dv[w].mean(), w.sum()))


def fit_strike(opts):
    """The box's knock: upright_fit.fit_strike (the strike's noise between the
    partials, third octaves, 0-30 ms, and its register slope) on every
    recorded key; it writes the class's strike_noise_db / _slope itself."""
    import tonelib as T
    U.recordings = lambda dyn: recordings()
    U.STRIKE_KEYS = tuple(sorted(recordings()))
    U.VEL = {2: VEL}
    U.fit_strike(T.HammeredDulcimerProperties, PROGRAM, int(opts.get("--passes", 4)))


# THE SYMPATHY (`sympathy`): what the other strings add, 0.5-2.5 s after the
# stroke, re the note's fundamental. Two figures a key:
#   partner  the bridge partner's peak, at its own pitch (the other length of
#            the struck string, a fifth away: bridge_partner)
#   between  the energy between the note's own partials and the partner's
#            (+-3% of each left out), 100-4000 Hz: every other course answering
# --fit fits register_knock_gain to `between` and partner_coupling to `partner`,
# by their medians over the keys (log of the class values); --fit --partner the
# partner alone. `between` sums whatever lies between the partials -- room,
# microphone and the body's ring with the strings -- and fitted to it the
# knock ran 6 dB over the takes' halo, the strings' own peaks: the halo sets
# the knock (`halo`), and `between` is read, not fitted.
def sympathy_of(x, sr, k, partner):
    found, f0, B = U.partials(x, sr, k, 40)
    t0 = U.onset(x, sr)
    X, f = U.spectrum(x, sr, t0, 0.5, 2.5, 1 << 18)
    h1 = X[(f > f0 * 0.98) & (f < f0 * 1.02)].max()
    near = np.zeros_like(f, bool)
    for _, fn, _ in found:
        near |= np.abs(f - fn) < 0.03 * fn
    pdb = None
    if partner is not None:
        fp = 440.0 * 2 ** ((partner - 69) / 12.0)
        w = (f > fp * 0.985) & (f < fp * 1.015)
        pdb = 10 * np.log10(X[w].max() / h1 + 1e-30)
        for m in range(1, 30):
            near |= np.abs(f - m * fp) < 0.03 * m * fp
    band = (f > 100) & (f < 4000) & ~near
    bdb = 10 * np.log10(X[band].sum() / h1 + 1e-30)
    return pdb, bdb


def sympathy_err(rec, show=False):
    import tonelib as T
    P = T.HammeredDulcimerProperties.bridge_partner
    rp, rb, mp, mb = [], [], [], []
    for k, (p_, b_) in rec.items():
        y, sr = U.render(PROGRAM, k, VEL, 3.0)
        q, c = sympathy_of(y, sr, k, P.get(k))
        if p_ is not None and q is not None:
            rp.append(p_); mp.append(q)
        rb.append(b_); mb.append(c)
        if show:
            print("   %3d  partner %s  between %6.1f / %6.1f" % (
                k, "%6.1f / %6.1f" % (p_, q) if p_ is not None else "      --      ", b_, c))
    e_p = float(np.median(mp) - np.median(rp))
    e_b = float(np.median(mb) - np.median(rb))
    print("  median, ours - recorded: partner %+.1f dB, between %+.1f dB" % (e_p, e_b), flush=True)
    return e_p, e_b


def fit_sympathy(opts):
    import tonelib as T
    cls = T.HammeredDulcimerProperties
    rs = recordings()
    rec = {k: sympathy_of(*U.load(p), k, cls.bridge_partner.get(k)) for k, p in sorted(rs.items())}
    if "--fit" not in opts:
        sympathy_err(rec, show=True)
        return
    # each figure is a level: move each class value by the miss, damped, a
    # few rounds (the partner rides on the board's coupling, so the board first)
    for it in range(int(opts.get("--rounds", 5))):
        e_p, e_b = sympathy_err(rec)
        if "--partner" in opts:
            # the knock's level is the halo's (`halo`): only the partner here
            cls.partner_coupling *= 10 ** (-0.8 * e_p / 20.0)
        else:
            cls.register_knock_gain *= 10 ** (-0.8 * e_b / 20.0)
            cls.partner_coupling *= 10 ** (-0.8 * (e_p - e_b) / 20.0)
        print("    register_knock_gain %.4g  partner_coupling %.4g" % (cls.register_knock_gain,
                                                                    cls.partner_coupling))
    sympathy_err(rec, show=True)


# THE HALO BY DISTANCE (`halo`): which strings answer, by how far above or
# below the struck note they sit -- each semitone's peak, 0.5-2.5 s, dB re
# the fundamental (the note's own partials left out), the median over every
# key. A symmetric falloff (1 dB a semitone) rang the nearest strings either
# side loudest: a chromatic cluster round the note (Ben: "more chromatic
# than the recording"). The takes ring the strings BELOW, peaking 7-14
# semitones down, the near neighbours weak and those above 50-75 dB under.
# Fitted as register_knock_profile, a few rounds, damped and smoothed.
HALO = range(-24, 25)


def halo_of(x, sr, k):
    found, f0, B = U.partials(x, sr, k, 40)
    t0 = U.onset(x, sr)
    seg = x[t0 + int(0.5 * sr):t0 + int(2.5 * sr)]
    n = 1 << 18
    X = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) + 1e-12)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    h1 = X[(f > f0 * 0.98) & (f < f0 * 1.02)].max()
    out = {}
    for d in HALO:
        fd = f0 * 2 ** (d / 12.0)
        if d == 0 or fd < 80 or fd > 8000 or any(abs(fd - fn) < 0.03 * fn for _, fn, _ in found):
            continue
        w = (f > fd * 2 ** (-0.4 / 12)) & (f < fd * 2 ** (0.4 / 12))
        out[d] = float(X[w].max() - h1)
    return out


def halo_med(halos):
    return {d: float(np.median([h[d] for h in halos if d in h]))
            for d in HALO if sum(d in h for h in halos) >= 5}


def fit_halo(opts):
    import re
    import tonelib as T
    cls = T.HammeredDulcimerProperties
    rs = recordings()
    R = halo_med([halo_of(*U.load(p), k) for k, p in sorted(rs.items())])
    prof = dict(cls.register_knock_profile) if getattr(cls, "register_knock_profile", None) \
        else {d: -abs(d) * cls.register_knock_falloff for d in HALO}
    prof[0] = 0.0
    for it in range(int(opts.get("--rounds", 4)) + 1):
        cls.register_knock_profile = tuple((d, round(prof[d], 1)) for d in sorted(prof))
        M = halo_med([halo_of(*U.render(PROGRAM, k, VEL, 3.0), k) for k in sorted(rs)])
        e = {d: M[d] - R[d] for d in R if d in M}
        print("  round %d: halo rms %.1f dB" % (it, np.sqrt(np.mean(list(np.square(list(e.values())))))),
              flush=True)
        if it == int(opts.get("--rounds", 4)):
            break
        ds = sorted(e)
        ev = np.array([e[d] for d in ds])
        sm = np.convolve(np.pad(ev, 1, mode="edge"), [0.25, 0.5, 0.25], "valid")
        for d, v in zip(ds, sm):
            prof[d] = float(np.clip(prof.get(d, 0.0) - 0.7 * v, -60, 0))
        # the distances not measured (the note's own partials sit there, or no
        # course does) follow their measured neighbours -- left alone, the
        # octave above kept its starting -12 between -56 and -60, a spike,
        # and the two octaves below ran to the clip chasing strings the bank
        # has not got
        md = np.array(ds, float)
        pv = np.array([prof[d] for d in ds])
        for d in HALO:
            if d not in e and d != 0:
                prof[d] = float(np.interp(d, md, pv))
    print("  %s" % " ".join("%+d:%.0f/%.0f" % (d, R[d], M[d]) for d in sorted(R) if d in M))
    src = open(os.path.join(os.path.dirname(HERE), "tonelib.py")).read()
    line = "    register_knock_profile = %s\n" % (cls.register_knock_profile,)
    src2 = re.sub(r"^    register_knock_profile = .*\n", lambda _: line, src, count=1, flags=re.M)
    open(os.path.join(os.path.dirname(HERE), "tonelib.py"), "w").write(src2)
    print(line)


AB_KEYS = (50, 55, 59, 62, 67, 69, 74, 79, 84, 89)


def ab(out, note_s):
    """Each key's recording, then the model's, then a rest; each note peak-
    normalised alike (harpsi_ab.fit_note): colour and decay, not level."""
    import harpsi_ab as A
    from roomtail import write_wav
    A.NOTE_S = note_s
    rs = recordings()
    gap, rest = np.zeros(int(A.GAP_S * A.SR)), np.zeros(int(0.6 * A.SR))
    parts = []
    for k in AB_KEYS:
        y, sr = U.render(PROGRAM, k, VEL, note_s + 0.5)
        parts += [A.fit_note(*U.load(rs[k])), gap, A.fit_note(y, sr), rest]
    x = np.concatenate(parts)
    write_wav(out, np.stack([x, x], 1), A.SR)


def main(argv):
    notes = next((a.split("=")[1] for a in argv if a.startswith("--notes=")), None)
    keys = [int(n) for n in notes.split(",")] if notes else None
    opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    if argv[:1] == ["measure"]:
        show_measure(keys)
    elif argv[:1] == ["spectrum"]:
        fit_spectrum(opts)
    elif argv[:1] == ["body"]:
        fit_body(opts)
    elif argv[:1] == ["decay"]:
        fit_decay(opts)
    elif argv[:1] == ["peaks"]:
        fit_peaks(opts)
    elif argv[:1] == ["peakbody"]:
        fit_peakbody(opts)
    elif argv[:1] == ["showpeaks"]:
        show_peaks()
    elif argv[:1] == ["strike"]:
        fit_strike(opts)
    elif argv[:1] == ["sympathy"]:
        opts.update({a: "" for a in argv if a in ("--fit", "--partner")})
        fit_sympathy(opts)
    elif argv[:1] == ["halo"]:
        fit_halo(opts)
    elif argv[:1] == ["ab"]:
        ab(argv[1], float(opts.get("--note-s", 2.5)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
