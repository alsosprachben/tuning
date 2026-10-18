#!/usr/bin/env python3
"""Fit a harpsichord STOP against the 8' it is drawn beside, on one instrument.

    harpsi_fit.py measure REF_DIR STOP_DIR
    harpsi_fit.py fit --stop=lute REF_DIR STOP_DIR

REF_DIR and STOP_DIR are VCSL's two recordings of one harpsichord -- the
English (Zuckermann) set's Normal and Lute, the Flemish set's Low and High --
one wav per key, paired by the note name in the filename.

WHY A DIFFERENCE AND NOT A LEVEL. These recordings are single-microphone and
not anechoic, so a stop's own ladder carries the room and the body. Two stops
of one instrument in one room share both: the stop MINUS the 8', note by note,
divides them out (voicefit.py ratio is the same argument for decay). So the
model is rendered the same way -- GM 6 with only the 8' drawn, and with only
the stop drawn (the CC11 stop word, tonelib.HarpsichordProperties.stop_ranks)
-- and the two differences are compared.

PER REGISTER, NOT POOLED. A buff pad at the nut barely touches the bass and
dulls the treble by 15-30 dB (measured, English set): a pooled mean would fit
the tenor and be wrong at both ends -- voicefit.py ladder's own warning.

Output goes to tonelib.Harpsi*Properties by hand; this prints the numbers.
"""
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import voicefit as V
from roomtail import write_wav

BANDS = ((0, 200, "bass"), (200, 500, "tenor"), (500, 1e9, "treble"))
MS = np.arange(2, 13)               # harmonics compared: m=1 is the reference
BITS = {"8": 0, "8-upper": 1, "4": 2, "lute": 3}
CLASS = {"lute": "HarpsiLuteProperties", "8-upper": "HarpsiUpperProperties"}
HOLD = 2.0


def key_of(path):
    """The key a file is named for: a note name (VCSL), or a bare MIDI number
    (Pianobook's Harpsimachord, named by the A=440 number), or None."""
    n = V.note_of(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    return int(stem) if n is None and stem.isdigit() else n


def pairs(ref_dir, stop_dir):
    """[(key, ref_path, stop_path)] keyed by the REF recording's measured pitch
    (VCSL's Flemish labels sit an octave under what sounds)."""
    import glob
    byn = {}
    for d, k in ((ref_dir, 0), (stop_dir, 1)):
        for p in glob.glob(os.path.join(d, '*.wav')):
            n = key_of(p)
            if n is not None:
                byn.setdefault(n, [None, None])[k] = p
    # THE SET'S OCTAVE, from its labels against what sounds: the median over
    # notes of the unprompted pitch's octave offset. One note's reading can be
    # an octave out; the set's median is not.
    offs = []
    for n in byn:
        a = byn[n][0]
        if a:
            x, sr = V.mono(a)
            f = V.detect_f0(V.steady(x, sr), sr)
            if f and np.isfinite(f) and f > 0:
                offs.append(round(np.log2(f / key_hz(n))))
    shift = 12 * int(np.median(offs)) if offs else 0
    return [(n + shift, a, b) for n, (a, b) in sorted(byn.items())
            if a and b and single_note(a) and single_note(b)]


def ladder_at(path, f_hint, nmax=16):
    """voicefit.ladder_of, but with the pitch found NEAR f_hint (+-10%).
    Unprompted, the autocorrelation locks an octave low on a weak-fundamental
    note -- the lute does it -- and every partial then lands on an even slot:
    a ladder that alternates, which is a measurement and not a timbre."""
    x, sr = V.mono(path)
    seg = V.steady(x, sr, 0.05, 0.5)
    if len(seg) < 8192:
        return None
    f0 = V.detect_f0(seg, sr, lo=0.9 * f_hint, hi=1.1 * f_hint)
    if not f0:
        return None
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    a = []
    for m in range(1, nmax + 1):
        fm = m * f0
        if fm > 0.45 * sr:
            return None
        w = (f > fm - 0.3 * f0) & (f < fm + 0.3 * f0)
        a.append(X[w].max())
    a = np.array(a)
    if a[0] <= 0:
        return None
    return f0, 20 * np.log10(np.maximum(a, 1e-12) / a[0])


def ladder_diff(a_path, b_path, f_hint):
    la, lb = ladder_at(a_path, f_hint), ladder_at(b_path, f_hint)
    if not la or not lb:
        return None
    return la[0], lb[1][MS - 1] - la[1][MS - 1]


def key_hz(k):
    return 440.0 * 2 ** ((k - 69) / 12.0)


def d1(path, f_hint):
    """voicefit ratio's decay figure: the fundamental's amplitude rate, from a
    line through the first partials' rates -- at the pitch near f_hint."""
    x, sr = V.mono(path)
    f0 = V.detect_f0(V.steady(x, sr), sr, lo=0.9 * f_hint, hi=1.1 * f_hint)
    if not f0:
        return None
    seg = x[V.onset(x, sr):]
    ds = []
    for m in range(1, 13):
        if m * f0 > 0.45 * sr:
            break
        s = V.partial_slope(seg, sr, m * f0, 0.35 * f0, f0)
        if s is not None:
            ds.append((m, -s))
    if len(ds) < 4:
        return None
    m = np.array([d[0] for d in ds], float)
    D = np.array([d[1] for d in ds]) / 2.0
    c = np.polyfit(m, D, 1)
    v = c[1] + c[0]
    return v if v > 0 else None


def by_band(rows):
    """{band: mean difference over its notes}, rows = [(f0, diff)]."""
    out = {}
    for lo, hi, name in BANDS:
        d = [r[1] for r in rows if lo <= r[0] < hi]
        if len(d) >= 2:
            out[name] = np.mean(d, axis=0)
    return out


def measured(ref_dir, stop_dir):
    P = pairs(ref_dir, stop_dir)
    rows = [r for r in (ladder_diff(a, b, key_hz(k)) for k, a, b in P) if r]
    rat = []
    for k, a, b in P:
        A, B_ = d1(a, key_hz(k)), d1(b, key_hz(k))
        if A and B_:
            rat.append(B_ / A)
    return P, by_band(rows), (float(np.median(rat)) if rat else None), len(rat)


def render(key, bits, path):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=6, time=0))
    t.append(mido.Message("control_change", channel=0, control=11, value=bits & 0x7F, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=10))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(HOLD * 960)))
    L, R = B.render(m)[:2]
    x = 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64))
    x = x / max(np.abs(x).max(), 1e-12) * 0.5
    write_wav(path, np.stack([x, x], 1), B.SR)


def model(keys, stop, tmp, ref_cache):
    """The model's (by-band ladder difference, median decay ratio) for STOP
    against the 8', over KEYS. The 8' renders are cached: only the stop moves."""
    rows, rat = [], []
    for k in keys:
        a = ref_cache.get(k)
        if a is None:
            a = os.path.join(tmp, "ref_%d.wav" % k)
            render(k, 1 << BITS["8"], a)
            ref_cache[k] = a
        b = os.path.join(tmp, "stop_%d.wav" % k)
        render(k, 1 << BITS[stop], b)
        r = ladder_diff(a, b, key_hz(k))
        if r:
            rows.append(r)
        A, B_ = d1(a, key_hz(k)), d1(b, key_hz(k))
        if A and B_:
            rat.append(B_ / A)
    return by_band(rows), (float(np.median(rat)) if rat else None)


def err(mb, rb):
    e = [mb[n] - rb[n] for n in rb if n in mb]
    return float(np.sqrt(np.mean(np.concatenate(e) ** 2))) if e else 99.0


def show(title, bands, ratio=None):
    print("  %s%s" % (title, "" if ratio is None else "   decay ratio %.2f" % ratio))
    print("     m      " + " ".join("%6d" % m for m in MS))
    for _, _, n in BANDS:
        if n in bands:
            print("     %-7s" % n + " ".join("%6.1f" % v for v in bands[n]))


TAIL = (1.0, 2.0)          # s: well after the buffed string has gone


def tail_of(path, f_hint):
    """The fundamental's TAIL against its attack: (level of its envelope over
    TAIL re its peak, dB; its pitch there re the attack's, cents). A tail at
    the plucked string's own pitch is that string still ringing; one a few
    cents off is ANOTHER string -- the key's other choir, free and driven
    through the bridge (tonelib.HarpsichordProperties.string_choirs)."""
    x, sr = V.mono(path)
    x = x[V.onset(x, sr):]
    if len(x) < int((TAIL[1] + 0.1) * sr):
        return None
    f0 = V.detect_f0(V.steady(x, sr), sr, lo=0.9 * f_hint, hi=1.1 * f_hint)
    if not f0:
        return None
    e = V.analytic_env(x, sr, 0.7 * f0, 1.3 * f0)
    w = int(0.02 * sr)
    fr = np.array([e[j:j + w].mean() for j in range(0, len(e) - w, w)])
    pk = fr[:10].max()
    late = fr[int(TAIL[0] / 0.02):int(TAIL[1] / 0.02)].mean()

    def peak(a, b):
        s = x[int(a * sr):int(b * sr)]
        N = 1 << 21
        X = np.abs(np.fft.rfft(s * np.hanning(len(s)), N))
        f = np.fft.rfftfreq(N, 1.0 / sr)
        m = (f > 0.96 * f0) & (f < 1.04 * f0)
        return f[m][np.argmax(X[m])]
    return 20 * np.log10(max(late, 1e-12) / pk), 1200 * np.log2(peak(*TAIL) / peak(0.02, 0.25))


ENV_T = np.arange(0.1, 2.01, 0.1)      # s: the envelope's frames


def env_db(path, f_hint):
    """Harmonics 1 and 2's envelopes, dB re each one's peak, at ENV_T,
    smoothed over 200 ms -- two strings a few cents apart beat, and the beat's
    phase is the instrument's accident, not its physics."""
    x, sr = V.mono(path)
    x = x[V.onset(x, sr):]
    if len(x) < int((ENV_T[-1] + 0.2) * sr):
        return None
    f0 = V.detect_f0(V.steady(x, sr), sr, lo=0.9 * f_hint, hi=1.1 * f_hint)
    if not f0:
        return None
    out = []
    for m in (1, 2):
        e = V.analytic_env(x, sr, (m - 0.3) * f0, (m + 0.3) * f0)
        pk = e[:int(0.1 * sr)].max()
        h = int(0.1 * sr)
        out.append([20 * np.log10(max(e[int(t * sr) - h:int(t * sr) + h].mean(), 1e-12) / pk)
                    for t in ENV_T])
    return np.array(out)


def fit_envelope(stop_dir, stop, opts):
    """The buffed string's own decay AND the other choir's answer, together
    (`envelope`): the two are one envelope in the recording -- a fast fall,
    then a tail a few cents off -- so they are fitted as one, on a grid of
    (decay scale on the stop's decay_db/harmonic_decay_db, register_gain)."""
    import glob
    import tonelib as T
    cls = getattr(T, CLASS[stop])
    d0, h0 = cls.decay_db, cls.harmonic_decay_db
    files = {key_of(p): p for p in glob.glob(os.path.join(stop_dir, "*.wav"))
             if key_of(p) is not None}
    P = pairs(stop_dir, stop_dir)
    shift = (P[0][0] - key_of(P[0][1])) if P else 0
    rec = {}
    for n, p in sorted(files.items()):
        e = env_db(p, key_hz(n + shift))
        if e is not None:
            rec[n + shift] = e
    keys = sorted(rec)
    tmp = tempfile.mkdtemp(prefix="harpsi_env_")
    global HOLD
    HOLD = ENV_T[-1] + 0.5
    best = None
    for k_ in [float(v) for v in opts.get("--scales", "1,1.5,2,3,4").split(",")]:
        for g in [float(v) for v in opts.get("--gains", "0.1,0.3,1,3").split(",")]:
            cls.decay_db, cls.harmonic_decay_db = d0 * k_, h0 * k_
            T.HarpsichordProperties.register_gain = g
            errs = []
            for k in keys:
                p = os.path.join(tmp, "e_%d.wav" % k)
                render(k, 1 << BITS[stop], p)
                m = env_db(p, key_hz(k))
                if m is not None:
                    errs.append((m - rec[k]).ravel())
            r = float(np.sqrt(np.mean(np.concatenate(errs) ** 2)))
            print("  decay x%-4g register_gain %-5g  envelope rms %.2f dB" % (k_, g, r), flush=True)
            if best is None or r < best[0]:
                best = (r, k_, g)
    cls.decay_db, cls.harmonic_decay_db = d0, h0
    print("  BEST: decay x%g (decay_db %.2f, harmonic_decay_db %.2f), register_gain %g, rms %.2f dB"
          % (best[1], d0 * best[1], h0 * best[1], best[2], best[0]))
    return 0


def fit_envelope_nm(stop_dir, stop, opts):
    """`envfit`: as `envelope`, but Nelder-Mead in log space over --params --
    the stop class's attributes, or register_gain (the instrument's) -- since
    the buff's fall steepens up the compass while the tail rises everywhere,
    and no one scale fits both (measured: the treble's 0.3 s level -17.9 dB
    against the model's -12.7, its 2 s level -55 against -65)."""
    import glob
    import tonelib as T
    from scipy.optimize import minimize
    cls = getattr(T, CLASS[stop])
    names = opts.get("--params", "decay_db,decay_register_slope,register_gain").split(",")
    own = lambda n: T.HarpsichordProperties if n == "register_gain" else cls   # noqa: E731
    files = {key_of(p): p for p in glob.glob(os.path.join(stop_dir, "*.wav"))
             if key_of(p) is not None}
    P = pairs(stop_dir, stop_dir)
    shift = (P[0][0] - key_of(P[0][1])) if P else 0
    rec, rtail = {}, {}
    for n, p in sorted(files.items()):
        e = env_db(p, key_hz(n + shift))
        if e is not None:
            rec[n + shift] = e
            t = tail_of(p, key_hz(n + shift))
            if t and n + shift >= 48:        # the bass's shift reads are octave-confused
                rtail[n + shift] = t[1]
    keys = sorted(rec)
    # THE TAIL'S PITCH IS THE EVIDENCE WHOSE STRING IT IS: its level alone
    # fits the buffed string ringing on just as well (measured: 7.79 dB with
    # no coupling, 7.72 with it, the tail then 1.4 cents off against the
    # recording's 5.8). --shift-weight dB of cost per cent of that error.
    sw = float(opts.get("--shift-weight", 0.0))
    tmp = tempfile.mkdtemp(prefix="harpsi_envnm_")
    global HOLD
    HOLD = ENV_T[-1] + 0.5
    # --start=name:value,... -- e.g. register_gain where the register is
    # above its floor at all: under it the error is flat and there is
    # nothing for the simplex to follow
    for kv in filter(None, opts.get("--start", "").split(",")):
        n, v = kv.split(":")
        setattr(own(n), n, float(v))
    x0 = np.log([max(float(getattr(own(n), n)), 1e-3) for n in names])
    seen = {}

    def f(lx):
        kx = tuple(np.round(lx, 3))
        if kx in seen:
            return seen[kx]
        for n, v in zip(names, np.exp(lx)):
            setattr(own(n), n, float(v))
        errs, serr = [], []
        for k in keys:
            p = os.path.join(tmp, "e_%d.wav" % k)
            render(k, 1 << BITS[stop], p)
            m = env_db(p, key_hz(k))
            if m is not None:
                errs.append((m - rec[k]).ravel())
            if sw and k in rtail:
                t = tail_of(p, key_hz(k))
                if t:
                    serr.append(abs(t[1] - rtail[k]))
        env = float(np.sqrt(np.mean(np.concatenate(errs) ** 2)))
        shf = float(np.median(serr)) if serr else 0.0
        seen[kx] = env + sw * shf
        print("    %s  envelope rms %.2f  tail shift err %.1f c  cost %.2f"
              % (" ".join("%s=%.4g" % (n, v) for n, v in zip(names, np.exp(lx))), env, shf, seen[kx]),
              flush=True)
        return seen[kx]
    res = minimize(f, x0, method="Nelder-Mead",
                   options=dict(xatol=0.02, fatol=0.05, maxfev=int(opts.get("--maxfev", 45)),
                                initial_simplex=[x0] + [x0 + 0.5 * np.eye(len(x0))[i]
                                                        for i in range(len(x0))]))
    print("  BEST: %s  envelope rms %.2f dB"
          % (", ".join("%s %.4g" % (n, v) for n, v in zip(names, np.exp(res.x))), res.fun))
    return 0


def fit_spectrum(ref_dir, opts):
    """`spectrum`: the strings' ladder over the WHOLE band, by third octaves
    from each key's fundamental up (upright_fit.thirds: 30-530 ms, dB re the
    strongest band), every key -- on HarpsiBase, the strings every choir
    shares. The ladder had been fitted on harmonics 1-16 against the
    fundamental, and extended past them it rolled the bass's top off 20-25 dB
    under the recordings: their C2 carries harmonics 30-66 at -7 to +11 dB re
    its fundamental, ours -25 (Ben: "more buzz in the 8"). octave_dampening is
    what lets the bass be flatter than the treble."""
    import glob
    import tonelib as T
    import upright_fit as U
    from scipy.optimize import minimize
    cls = T.HarpsiBase
    names = opts.get("--params", "tonal_dampening,octave_dampening").split(",")
    files = {key_of(p): p for p in glob.glob(os.path.join(ref_dir, "*.wav"))
             if key_of(p) is not None}
    P = pairs(ref_dir, ref_dir)
    shift = (P[0][0] - key_of(P[0][1])) if P else 0
    rec = {}
    for n, p in sorted(files.items()):
        if single_note(p):
            x, sr = V.mono(p)
            rec[n + shift] = U.thirds(x, sr, n + shift)
    keys = sorted(rec)
    tmp = tempfile.mkdtemp(prefix="harpsi_spec_")
    global HOLD
    HOLD = 1.0
    seen = {}

    def err_now():
        D = []
        for k in keys:
            p = os.path.join(tmp, "s.wav")
            render(k, 1 << BITS["8"], p)
            x, sr = V.mono(p)
            d = U.thirds(x, sr, k) - rec[k]
            D.append(d[np.isfinite(d)])
        return float(np.sqrt(np.mean(np.concatenate(D) ** 2)))

    def f(x):
        kx = tuple(np.round(x, 4))
        if kx not in seen:
            for n, v in zip(names, x):
                setattr(cls, n, float(v))
            seen[kx] = err_now()
            print("    %s  thirds rms %.2f" % (" ".join("%s=%.4f" % (n, v) for n, v in zip(names, x)),
                                              seen[kx]), flush=True)
        return seen[kx]
    x0 = np.array([float(getattr(cls, n)) for n in names])
    print("  %d keys" % len(keys))
    steps = [float(s) for s in opts.get("--steps", "0.2,0.15").split(",")]
    res = minimize(f, x0, method="Nelder-Mead",
                   options=dict(xatol=0.005, fatol=0.03, maxfev=int(opts.get("--maxfev", 40)),
                                initial_simplex=[x0] + [x0 + steps[i] * np.eye(len(x0))[i]
                                                        for i in range(len(x0))]))
    print("  BEST: %s  thirds rms %.2f dB (from %.2f)"
          % (", ".join("%s %.4f" % (n, v) for n, v in zip(names, res.x)), res.fun, seen[tuple(np.round(x0, 4))]))
    return 0


def band_decays(path, f_hint, t0=0.05, t1=1.2):
    """Each third octave's decay, dB/s, from the key's fundamental to 12 kHz:
    a line through its 20 ms frame levels from t0 until it is 25 dB down or
    t1 -- where the band is within 40 dB of the note's strongest. {centre: dB/s}."""
    import upright_fit as U
    x, sr = V.mono(path)
    x = x[V.onset(x, sr):]
    out = {}
    w = int(0.02 * sr)
    for lo, hi in zip(U.E3[:-1], U.E3[1:]):
        if hi < 0.89 * f_hint or lo > 12000:
            continue
        e = V.analytic_env(x, sr, lo, hi)
        fr = np.array([np.mean(e[j:j + w] ** 2) for j in range(0, len(e) - w, w)])
        out[float(np.sqrt(lo * hi))] = 10 * np.log10(fr + 1e-30)
    if not out:
        return {}
    top = max(v[:10].max() for v in out.values())
    res = {}
    for c, db in out.items():
        a = int(t0 / 0.02)
        pk = db[a:a + 5].max()
        if pk < top - 40:
            continue
        stop = min(int(t1 / 0.02), len(db))
        below = np.flatnonzero(db[a:stop] < pk - 25)
        b = a + (below[0] if len(below) else stop - a)
        if b - a < 5:
            continue
        t = np.arange(a, b) * 0.02
        res[c] = -float(np.polyfit(t, db[a:b], 1)[0])
    return res


def fit_decay(ref_dir, opts):
    """`decay`: the strings' decay over the WHOLE band, per third octave, every
    key -- HarpsiBase's decay law (decay_db + harmonic_decay_db * m^(1 +
    harmonic_decay_dampening), times 2^(decay_register_slope * octave)), or a
    stop's (--stop=lute, against its own set). Fitted on harmonics 1-12, the
    line ran the bass's top -- partials to 16 kHz now -- out at 80-100+ dB/s
    against the recordings' 15-25: a bright attack collapsing, which Ben
    heard as a phaser ("decaying the metallic upper harmonics too quickly").
    Compared as the log of the rates: 4 dB/s against 8 is the same miss as 40
    against 80."""
    import glob
    import tonelib as T
    from scipy.optimize import minimize
    stop = opts.get("--stop", "8")
    cls = T.HarpsiBase if stop == "8" else getattr(T, CLASS[stop])
    names = opts.get("--params", "decay_db,harmonic_decay_db,harmonic_decay_dampening,decay_register_slope").split(",")
    files = {key_of(p): p for p in glob.glob(os.path.join(ref_dir, "*.wav"))
             if key_of(p) is not None}
    P = pairs(ref_dir, ref_dir)
    shift = (P[0][0] - key_of(P[0][1])) if P else 0
    rec = {}
    for n, p in sorted(files.items()):
        if single_note(p):
            r = band_decays(p, key_hz(n + shift))
            if r:
                rec[n + shift] = r
    keys = sorted(rec)
    tmp = tempfile.mkdtemp(prefix="harpsi_decay_")
    global HOLD
    HOLD = 1.5
    seen = {}

    def err_now(show=False):
        E, rows = [], []
        for k in keys:
            p = os.path.join(tmp, "d.wav")
            render(k, 1 << BITS[stop], p)
            m = band_decays(p, key_hz(k))
            for c, r in rec[k].items():
                if c in m and r > 0.5 and m[c] > 0.5:
                    E.append(np.log(m[c] / r))
                    rows.append((k, c, r, m[c]))
        e = float(np.sqrt(np.mean(np.square(E))))
        if show:
            for lo, hi, nm in BANDS:
                sel = [x for x in rows if lo <= key_hz(x[0]) < hi]
                for flo, fhi in ((0, 1000), (1000, 4000), (4000, 13000)):
                    s2 = [x for x in sel if flo <= x[1] < fhi]
                    if s2:
                        print("     %-7s %5d-%5d Hz: recorded %5.1f dB/s, model %5.1f (%d)"
                              % (nm, flo, fhi, np.median([x[2] for x in s2]), np.median([x[3] for x in s2]), len(s2)))
        return e

    def f(x):
        kx = tuple(np.round(x, 4))
        if kx not in seen:
            for n, v in zip(names, x):
                setattr(cls, n, float(v))
            seen[kx] = err_now()
            print("    %s  log-rate rms %.3f" % (" ".join("%s=%.4f" % (n, v) for n, v in zip(names, x)),
                                                 seen[kx]), flush=True)
        return seen[kx]
    x0 = np.array([float(getattr(cls, n)) for n in names])
    print("  %d keys; as it stands:" % len(keys))
    e0 = err_now(show=True)
    print("  log-rate rms %.3f" % e0)
    steps = {"decay_db": 1.0, "harmonic_decay_db": 0.5, "harmonic_decay_dampening": 0.3,
             "decay_register_slope": 0.15}
    res = minimize(f, x0, method="Nelder-Mead",
                   options=dict(xatol=0.005, fatol=0.003, maxfev=int(opts.get("--maxfev", 60)),
                                initial_simplex=[x0] + [x0 + steps.get(n, 0.2) * np.eye(len(x0))[i]
                                                        for i, n in enumerate(names)]))
    for n, v in zip(names, res.x):
        setattr(cls, n, float(v))
    print("  BEST: %s  log-rate rms %.3f (from %.3f)"
          % (", ".join("%s %.4f" % (n, v) for n, v in zip(names, res.x)), res.fun, e0))
    err_now(show=True)
    return 0


def fit_body(ref_dir, opts):
    """`body`: HarpsiBase.body_trim_db, dB by ABSOLUTE frequency -- what the
    harmonic-number law cannot say. After `spectrum`, the residual held one
    shape in every register (model under the recordings 6-11 dB at 80-320 Hz,
    over by 4-7 at 1.3-2.6 kHz, under by 3-6 past 5 kHz): a body. Iterated as
    steel_fit --body iterates it, on the third octaves of every key."""
    import glob
    import tonelib as T
    import upright_fit as U
    cls = T.HarpsiBase
    C = np.sqrt(U.E3[:-1] * U.E3[1:])
    files = {key_of(p): p for p in glob.glob(os.path.join(ref_dir, "*.wav"))
             if key_of(p) is not None}
    P = pairs(ref_dir, ref_dir)
    shift = (P[0][0] - key_of(P[0][1])) if P else 0
    rec = {}
    for n, p in sorted(files.items()):
        if single_note(p):
            x, sr = V.mono(p)
            rec[n + shift] = U.thirds(x, sr, n + shift)
    keys = sorted(rec)
    tmp = tempfile.mkdtemp(prefix="harpsi_body_")
    global HOLD
    HOLD = 1.0
    trim = dict(cls.body_trim_db) if cls.body_trim_db else {}
    best = None
    for it in range(int(opts.get("--passes", 3)) + 1):
        acc = [[] for _ in C]
        D = []
        for k in keys:
            p = os.path.join(tmp, "b.wav")
            render(k, 1 << BITS["8"], p)
            x, sr = V.mono(p)
            d = U.thirds(x, sr, k) - rec[k]
            D.append(d[np.isfinite(d)])
            for i, v in enumerate(d):
                if np.isfinite(v):
                    acc[i].append(v)
        print("  pass %d: thirds rms %.2f dB" % (it, float(np.sqrt(np.mean(np.concatenate(D) ** 2)))),
              flush=True)
        if it == int(opts.get("--passes", 3)):
            break
        rms = float(np.sqrt(np.mean(np.concatenate(D) ** 2)))
        if best is None or rms < best[0]:
            best = (rms, cls.body_trim_db)
        # A BODY IS SMOOTH: the residual a one-octave running mean, and half of
        # it a pass. Unsmoothed, the bands a few bass keys alone reach ran to
        # the clip in a sawtooth (+15, +8.7, +15) and the fit got worse after
        # its first pass -- each key is read re its own strongest band, so a
        # raised band lowers the rest
        cs = [float(c) for c, a in zip(C, acc) if len(a) >= 3]
        rv = np.array([float(np.mean(a)) for a in acc if len(a) >= 3])
        lc = np.log2(cs)
        sm = np.array([rv[np.abs(lc - l) <= 0.5].mean() for l in lc])
        for c, r in zip(cs, sm):
            trim[c] = float(np.clip(trim.get(c, 0.0) - 0.5 * r, -12, 12))
        pts = sorted(trim.items())
        cls.body_trim_db = tuple((round(c), round(v, 1)) for c, v in pts)
    if best[0] < rms:
        cls.body_trim_db = best[1]
    print("  best %.2f dB" % min(best[0], rms))
    print("    body_trim_db = (%s)" % ", ".join("(%d, %.1f)" % (c, v) for c, v in (cls.body_trim_db or ())))
    return 0


def single_note(path):
    """One clean note in the file? Not a second strike (a 12 dB rise in 30 ms
    to within 20 dB of the peak), and not a rattle: VCSL's English A#0 -- Lute
    and Normal alike, so the string, not the stop -- swings 6-10 dB every
    50-120 ms for two seconds, which Ben heard as "multiple notes"; so do a
    few Flemish keys. Counted as rises of 6 dB in 30 ms above -25 dB after the
    attack: over 20 rejects (the worst clean file has 13)."""
    x, sr = V.mono(path)
    w = int(0.01 * sr)
    e = np.array([np.sqrt(np.mean(x[i:i + w] ** 2)) for i in range(0, len(x) - w, w)])
    db = 20 * np.log10(e / max(e.max(), 1e-12) + 1e-9)
    rise = np.array([db[i] - db[max(0, i - 3):i + 1].min() for i in range(len(db))])
    on = [i for i in range(len(db)) if db[i] > -20 and rise[i] > 12]
    groups, last = 0, -99
    for i in on:
        if i - last > 10:
            groups += 1
        last = i
    a = int(np.argmax(db)) + 50
    bumps = int(np.sum((db[a:] > -25) & (rise[a:] > 6)))
    return groups <= 1 and bumps <= 20


def fit_pluck(ref_dir, opts):
    """`pluck`: the QUILL'S NOISE on the 8' -- tonelib's strike_noise rows, the
    piano's strike, used as a pluck. Measured as upright_fit.strike_noise
    measures the hammer: the third-octave spectrum OUTSIDE the partials over
    the first 30 ms, dB re all of it, and its fall by 30-80 ms. Ben: "missing
    some metallic buzz in upper harmonics ... more buzz in the 8": the
    recordings' 4-8 kHz is 12 dB over ours and mostly between the harmonics."""
    import glob
    import tonelib as T
    import upright_fit as U
    cls = T.HarpsichordProperties
    files = {key_of(p): p for p in glob.glob(os.path.join(ref_dir, "*.wav"))
             if key_of(p) is not None}
    P = pairs(ref_dir, ref_dir)
    shift = (P[0][0] - key_of(P[0][1])) if P else 0
    lo_key = int(opts.get("--from", 48))          # below, the partials fill the gaps
    rec, falls = {}, []
    for n, p in sorted(files.items()):
        k = n + shift
        if k < lo_key or not single_note(p):
            continue
        x, sr = V.mono(p)
        s, fall = U.strike_noise(x, sr, k)
        rec[k] = s
        falls.append(fall)
    keys = sorted(rec)
    fall = float(np.median(falls))
    # the rows fall at strike_noise_dbs: the windows' centres are 40 ms apart
    cls.strike_noise_dbs = max(20.0, -fall / 0.04)
    cls.strike_noise_fade_s = 0.001
    if not getattr(cls, 'strike_noise_db', ()):
        cls.strike_noise_db = tuple((int(round(c)), -45.0) for c in U.S3C)
    cls.strike_noise_octave_db = float(getattr(cls, 'strike_noise_octave_db', 0.0) or 0.0)
    print("  %d keys from %d; recorded fall by 30-80 ms %.1f dB -> strike_noise_dbs %.0f"
          % (len(keys), lo_key, fall, cls.strike_noise_dbs))
    tmp = tempfile.mkdtemp(prefix="harpsi_pluck_")
    global HOLD
    HOLD = 1.0
    passes = int(opts.get("--passes", 4))
    for it in range(passes + 1):
        D = []
        for k in keys:
            p = os.path.join(tmp, "p.wav")
            render(k, 1 << BITS["8"], p)
            x, sr = V.mono(p)
            D.append(rec[k] - U.strike_noise(x, sr, k)[0])
        D = np.array(D)
        ok = np.isfinite(D)
        print("  pass %d: pluck noise recorded - ours, rms %.1f dB" % (it, float(np.sqrt(np.mean(D[ok] ** 2)))),
              flush=True)
        if it == passes:
            break
        band = np.array([np.nanmean(np.where(ok[:, j], D[:, j], np.nan)) if ok[:, j].any() else 0.0
                         for j in range(D.shape[1])])
        reg = np.log2(np.array([key_hz(k) for k in keys]) / 440.0)
        km = np.array([np.nanmean(np.where(ok[i], D[i], np.nan) - band) for i in range(len(keys))])
        cls.strike_noise_octave_db += 0.7 * float(np.polyfit(reg, km, 1)[0])
        old = dict(cls.strike_noise_db)
        cls.strike_noise_db = tuple(
            (int(round(c)), round(float(np.interp(np.log(c), np.log(list(old)), list(old.values()))
                                        + np.clip(np.nan_to_num(b), -12, 12)), 1))
            for c, b in zip(U.S3C, band))
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))
    print("    strike_noise_octave_db = %.3f" % cls.strike_noise_octave_db)
    print("    strike_noise_dbs = %.1f" % cls.strike_noise_dbs)
    return 0


def fit_tail(stop_dir, stop, opts):
    """register_gain against the stop's tail, key by key (`tail`)."""
    import glob
    import tonelib as T
    files = {key_of(p): p for p in glob.glob(os.path.join(stop_dir, "*.wav"))
             if key_of(p) is not None}
    P = pairs(stop_dir, stop_dir)                 # the set's octave, by its labels
    shift = (P[0][0] - key_of(P[0][1])) if P else 0
    rec = {}
    for n, p in sorted(files.items()):
        k = n + shift
        t = tail_of(p, key_hz(k))
        if t:
            rec[k] = t
    keys = sorted(rec)
    tmp = tempfile.mkdtemp(prefix="harpsi_tail_")
    global HOLD
    HOLD = TAIL[1] + 0.5
    print("  key  recorded tail dB / cents")
    for k in keys:
        print("  %3d   %6.1f %+6.1f" % (k, rec[k][0], rec[k][1]))
    for g in [float(v) for v in opts.get("--gains", "0.02,0.1,0.3,1,3").split(",")]:
        T.HarpsichordProperties.register_gain = g
        got, err_ = [], []
        for k in keys:
            p = os.path.join(tmp, "t_%d.wav" % k)
            render(k, 1 << BITS[stop], p)
            t = tail_of(p, key_hz(k))
            if t:
                got.append((k, t))
                err_.append(t[0] - rec[k][0])
        print("  register_gain %-6g tail level rms %.1f dB (model - recorded, mean %+.1f)   %s"
              % (g, float(np.sqrt(np.mean(np.square(err_)))), float(np.mean(err_)),
                 " ".join("%d:%.0f/%+.0fc" % (k, t[0], t[1]) for k, t in got)), flush=True)
    return 0


def main(argv):
    if len(argv) >= 3 and argv[1] == "decay":
        opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
        return fit_decay([a for a in argv[2:] if not a.startswith("--")][0], opts)
    if len(argv) >= 3 and argv[1] == "body":
        opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
        return fit_body([a for a in argv[2:] if not a.startswith("--")][0], opts)
    if len(argv) >= 3 and argv[1] == "spectrum":
        opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
        return fit_spectrum([a for a in argv[2:] if not a.startswith("--")][0], opts)
    if len(argv) >= 3 and argv[1] == "pluck":
        opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
        return fit_pluck([a for a in argv[2:] if not a.startswith("--")][0], opts)
    if len(argv) >= 3 and argv[1] in ("tail", "envelope", "envfit"):
        opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
        return {"tail": fit_tail, "envelope": fit_envelope, "envfit": fit_envelope_nm}[argv[1]](
            [a for a in argv[2:] if not a.startswith("--")][0], opts.get("--stop", "lute"), opts)
    if len(argv) < 4 or argv[1] not in ("measure", "fit"):
        print(__doc__.strip())
        return 2
    opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    ref_dir, stop_dir = [a for a in argv[2:] if not a.startswith("--")][:2]
    P, rb, rr, nr = measured(ref_dir, stop_dir)
    show("RECORDED, stop minus 8' (%d pairs, decay over %d)" % (len(P), nr), rb, rr)
    if argv[1] == "measure":
        return 0
    stop = opts.get("--stop", "lute")
    import tonelib as T
    cls = getattr(T, CLASS[stop])
    keys = sorted({k for k, _, _ in P})
    tmp = tempfile.mkdtemp(prefix="harpsi_fit_")
    cache = {}
    names = opts.get("--params", "tonal_dampening,octave_dampening").split(",")
    x0 = np.array([float(getattr(cls, n)) for n in names])
    mb, mr = model(keys, stop, tmp, cache)
    show("MODEL as it stands (%s)" % ", ".join("%s %.3f" % (n, v) for n, v in zip(names, x0)), mb, mr)
    print("  ladder rms %.2f dB" % err(mb, rb))
    if "--grid" in opts:
        # --grid=name:v1,v2,... -- a bounded scan, for a landscape the simplex
        # cannot walk: two plucking points' combs put their nulls at different
        # harmonics, and the difference jumps 30 dB as one crosses a harmonic
        name, vals = opts["--grid"].split(":")
        for v in [float(u) for u in vals.split(",")]:
            setattr(cls, name, v)
            mb, mr = model(keys, stop, tmp, cache)
            show("MODEL %s %.4f" % (name, v), mb, mr)
            print("  ladder rms %.2f dB" % err(mb, rb), flush=True)
        return 0
    seen = {}

    def f(x):
        kx = tuple(np.round(x, 4))
        if kx not in seen:
            for n, v in zip(names, x):
                setattr(cls, n, float(v))
            seen[kx] = err(model(keys, stop, tmp, cache)[0], rb)
            print("    %s  rms %.2f" % (" ".join("%s=%.3f" % (n, v) for n, v in zip(names, x)), seen[kx]),
                  flush=True)
        return seen[kx]
    from scipy.optimize import minimize
    res = minimize(f, x0, method="Nelder-Mead",
                   options=dict(xatol=0.01, fatol=0.05, maxfev=int(opts.get("--maxfev", 40)),
                                initial_simplex=[x0, x0 + [0.3, 0.0][:len(x0)] if len(x0) > 1 else x0 + 0.3,
                                                 x0 + [0.0, 0.2][:len(x0)]] if len(x0) == 2 else None))
    for n, v in zip(names, res.x):
        setattr(cls, n, float(v))
    mb, mr = model(keys, stop, tmp, cache)
    show("MODEL fitted (%s)" % ", ".join("%s %.3f" % (n, v) for n, v in zip(names, res.x)), mb, mr)
    print("  ladder rms %.2f dB; decay ratio model %.2f against recorded %.2f"
          % (err(mb, rb), mr or float('nan'), rr or float('nan')))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
