#!/usr/bin/env python3
"""Fit a struck hand-percussion voice (tonelib.MeasuredStrokeProperties) to
VSCO-2 Community Edition's recordings.

    python3 examples/perc_fit.py INST [--modes] [--scatter] [--model] [--fit [--maxfev=N]]

INST is one of INSTS below. REFS is ~/Documents/refs/vsco2 (sources.md):
VSCO-2 CE (Versilian Studios, CC0), stereo 44.1 kHz, the two channels summed
in power.

  --modes    the instrument's modes from its loudest strokes, 10-150 ms:
             every peak the highest within +-1.5%, within FLOOR dB of the
             strongest, in the instrument's band -- as (ratio to the note's
             pitch, dB re the strongest, amplitude dB/s read between two
             windows). The DRUM_MODES the class carries.
  --scatter  how much two takes of one stroke differ, band by band (1/48
             octave, 3-16 kHz or the instrument's band), against the model's
             -- what mode_scatter_db is set from (the tambourine's lesson:
             strokes rendered alike read as one ringing thing)
  --model    the band-by-time grid, recorded against our render
  --fit      the decay, strike and noise, the band trim solved inside, and
             the modes' flatness in the instrument's band

The grid is examples/crash_fit.py's, on windows sized to these (most are
40 dB down by 0.3-0.6 s). The files are trimmed close at both ends, so a
cell past a file's end reads -200 and weighs nothing; there is no clean
pre-onset silence to read a floor from.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import crash_fit as C  # noqa: E402
from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/vsco2")
_V1 = "VSCO 1 Percussion/"


def _vtag(p):
    m = re.search(r"_v(\d)_", os.path.basename(p))
    return int(m.group(1)) if m else 0


def _dyn(p):
    m = re.search(r"_(ppp|pp|p|mp|mf|f|ff|fff)[_.\d]", os.path.basename(p))
    return m.group(1) if m else ""


# A HAND DRUM'S NOISE IS ITS SLAP, NOT ITS HEAD. The head's modes ring clean
# (mode_jitter 0: jitter redraws a mode's phase nf * bandwidth times a second,
# and on a loud 216 Hz head that is ~24 clicks a second -- the open conga's
# first fit crackled 34 dB); the slap's partials, dense as the snare's wires
# (click_per_band 24), carry the noise, and the noise is judged where it
# lives, 1-8 kHz -- under 4 kHz the head's modes are all the flatness reads.
DRUM_PARAMS = ("slow_share", "slow_dbs", "click_cal_db", "click_dbs", "click_stroke_slope",
               "chiff_volume", "chiff_width", "chiff_bandwidth", "sustain_jitter")

# note, files, how they group into soft/mid/loud (None: one group), the
# modes' band and floor, the flatness band
INSTS = {
    "cowbell":   dict(note=56, glob="Percussion/Cowbell1_Hit_v*_Sum.wav",
                      groups=lambda p: {1: "soft", 2: "mid", 3: "mid", 4: "loud"}[_vtag(p)],
                      band=(300, 16000), floor=-30, flat=(1000, 12000),
                      # clean bell modes and a dense, noisy strike from 400 Hz, as
                      # the drums (DRUM_PARAMS), judged on the attack's contrast too
                      params=DRUM_PARAMS, contrast=True),
    "agogo_hi":  dict(note=67, glob=_V1 + "varMetal/various/agogoBell2_*.wav",
                      groups=lambda p: {"mp": "soft", "mf": "loud"}[_dyn(p)],
                      band=(500, 16000), floor=-30, flat=(1000, 12000)),
    "agogo_lo":  dict(note=68, glob=_V1 + "varMetal/various/agogoBell3_*.wav",
                      groups=lambda p: {"f": "soft", "ff": "loud"}[_dyn(p)],
                      band=(300, 16000), floor=-30, flat=(1000, 12000)),
    "conga_mute": dict(note=62, glob="Percussion/Quinto-Tap1_v*_Sum.wav", groups=None,
                       band=(150, 4000), floor=-25, flat=(1000, 8000),
                      params=DRUM_PARAMS),
    "conga_open": dict(note=63, glob="Percussion/Quinto-HitN_v*_Sum.wav",
                       groups=lambda p: {1: "soft", 2: "mid", 3: "loud"}[_vtag(p)],
                       band=(150, 4000), floor=-40, flat=(1000, 8000),
                       params=DRUM_PARAMS),
    "conga_low": dict(note=64, glob="Percussion/Conga-HitN_v*_Sum.wav",
                      groups=lambda p: {1: "soft", 2: "mid", 3: "loud"}[_vtag(p)],
                      band=(120, 4000), floor=-40, flat=(1000, 8000),
                      params=DRUM_PARAMS),
    "bongo_hi":  dict(note=60, glob=_V1 + "drums/other/Bongos/HighBongo*.wav", groups=None,
                      band=(120, 6000), floor=-25, flat=(1000, 8000),
                      params=DRUM_PARAMS),
    "maracas":   dict(note=70, glob=_V1 + "varWood/maraca[0-9].wav", groups=None,
                      band=(1000, 16000), floor=-20, flat=(1000, 12000),
                      # A RATTLE'S BURST IS HALF THE NOTE (PERCUSSION_RATTLE): a
                      # 1 s note is a half-second shake. A VSCO stroke shakes for
                      # ~50 ms and then settles for 0.3 s, so a 0.12 s note -- an
                      # eighth at 250 bpm, where maraca parts mostly live -- with
                      # the settle carrying the tail. 0.4 s first: a 0.2 s shake,
                      # flat until 200 ms where the recording falls from 100.
                      # The third-octave trim is kept (keep_trim): the spectrum
                      # was matched to the recordings band by band, by ear
                      hold=0.4, keep_trim=True,
                      params=("@rattle_rate", "@impact_ring", "@rattle_fall", "@settle_s", "@settle_db",
                              "@accent_s", "@accent_db")),
    "bongo_lo":  dict(note=61, glob=_V1 + "drums/other/Bongos/LowBongo*.wav", groups=None,
                      band=(120, 6000), floor=-25, flat=(1000, 8000),
                      params=DRUM_PARAMS),
}

C.EDGES = (125, 250, 500, 1000, 2000, 4000, 8000, 16000)
C.T = ((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25),
       (0.25, 0.40), (0.40, 0.70))
C.CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(C.EDGES[:-1], C.EDGES[1:]))
C.COL_W = np.array([0.3] + [1.0] * (len(C.T) - 1))
_render = C.render
HOLD = [1.0]
C.render = lambda note, vel, secs=None: _render(note, vel, HOLD[0] if secs is None else secs)
C.PARAMS = ("slow_share", "slow_dbs", "click_cal_db", "click_dbs",
            "click_stroke_slope", "chiff_volume", "chiff_width", "chiff_bandwidth",
            "mode_jitter", "sustain_jitter")
C.FLOOR = {"slow_share": 0.005, "click_stroke_slope": 0.05, "click_cal_db": 1.0}


def files(inst):
    return sorted(glob.glob(os.path.join(REFS, INSTS[inst]["glob"])))


def load(p):
    a, sr = read(p)
    a = np.pad(a.astype(np.float64), ((0, sr), (0, 0)))
    return [a[:, 0], a[:, 1]], sr


def strokes(inst):
    g = INSTS[inst]["groups"]
    out = []
    for p in files(inst):
        chs, sr = load(p)
        out.append(("all" if g is None else g(p), C.level(chs, sr), C.grid(chs, sr), p))
    return out


def grouped(ss):
    names = [g for g in C.GROUPS if any(s[0] == g for s in ss)] or ["all"]
    top = max(np.mean([s[1] for s in ss if s[0] == g]) for g in names)
    out = {}
    for g in names:
        rr = [s for s in ss if s[0] == g]
        gs = np.array([s[2] - s[2].max() for s in rr])
        m = np.where((gs < -100).any(0), -200.0, gs.mean(0))
        out[g] = (float(np.mean([s[1] for s in rr])) - top, m, [s[3] for s in rr])
    return out


def modes(inst, f0):
    spec = INSTS[inst]
    lo, hi = spec["band"]
    ss = strokes(inst)
    gs = grouped(ss)
    loud = gs[list(gs)[-1]][2]
    win = ((0.01, 0.15), (0.02, 0.06), (0.10, 0.20))
    acc = [0.0, 0.0, 0.0]
    for p in loud:
        chs, sr = load(p)
        x = chs[0] + chs[1]
        t0 = C.onset([x], sr)
        for k, (a0, a1) in enumerate(win):
            seg = x[t0 + int(a0 * sr):t0 + int(a1 * sr)]
            acc[k] = acc[k] + np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)) ** 2 / len(seg)
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    A = 10 * np.log10(acc[0] + 1e-30)
    b = np.flatnonzero((f > lo) & (f < hi))
    pk = [i for i in b if A[i] >= A[(f > f[i] * 0.985) & (f < f[i] * 1.015)].max()]
    top = max(A[i] for i in pk)
    pk = [i for i in pk if A[i] > top + spec["floor"]]
    out = []
    for i in pk:
        out.append((float(f[i] / f0), float(A[i] - top), mode_rate(loud, f[i])))
    return out


def mode_rate(paths, fm):
    """One mode's amplitude dB/s, read off its own envelope: band-passed
    +-1.5% around it, 5 ms RMS, the line through its first 35 dB down from
    its peak (from 10 ms, the strike's own crack out of the way), the median
    over the strokes. The two-window reading this replaces could not tell a
    mode's decay from its neighbour's, and the fit then scaled them all by
    one number -- the uniform ring that let the congas' highs hang on."""
    from scipy.signal import butter, sosfiltfilt
    rates = []
    for p in paths:
        chs, sr = load(p)
        x = chs[0] + chs[1]
        t0 = C.onset([x], sr)
        sos = butter(2, [fm * 0.985, fm * 1.015], btype="band", fs=sr, output="sos")
        y = sosfiltfilt(sos, x[t0:])
        n = int(0.005 * sr)
        e = np.sqrt(np.convolve(y * y, np.ones(n) / n, "valid")[::n])
        db = 20 * np.log10(e + 1e-12)
        t = np.arange(len(db)) * 0.005
        k0 = max(2, int(np.argmax(db[2:])) + 2)
        k1 = k0 + int(np.argmax(db[k0:] < db[k0] - 35.0)) if (db[k0:] < db[k0] - 35.0).any() else len(db)
        if k1 - k0 < 4:
            continue
        slope = np.polyfit(t[k0:k1], db[k0:k1], 1)[0]
        rates.append(-slope)
    return float(max(10.0, np.median(rates))) if rates else 40.0


def bands_db(x, sr, t0, lo, hi, a=0.01, b=0.10):
    seg = x[t0 + int(a * sr):t0 + int(b * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 15)) ** 2
    f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
    e = 2 ** np.arange(np.log2(lo), np.log2(hi), 1 / 48.0)
    return np.array([10 * np.log10(X[(f >= p) & (f < q)].sum() + 1e-30) for p, q in zip(e[:-1], e[1:])])


def stroke_diff(specs):
    S = [s - s.mean() for s in specs]
    return float(np.mean([np.std(S[i] - S[j]) for i in range(len(S)) for j in range(i + 1, len(S))]))


def scatter(inst):
    """Two takes of one stroke against each other, and four model strokes."""
    spec = INSTS[inst]
    lo, hi = spec["band"]
    by = {}
    for p in files(inst):
        key = re.sub(r"_rr\d|\d(?=\.wav$)|_\d(?=\.wav$)", "", os.path.basename(p))
        by.setdefault(key, []).append(p)
    rec = []
    for key, ps in by.items():
        if len(ps) > 1:
            sp = []
            for p in ps:
                chs, sr = load(p)
                x = chs[0] + chs[1]
                sp.append(bands_db(x, sr, C.onset([x], sr), lo, hi))
            rec.append(stroke_diff(sp))
    import mido
    import tempfile
    import blockrender as B
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    for k in range(4):
        t.append(mido.Message("note_on", channel=9, note=spec["note"], velocity=100, time=0 if k == 0 else 900))
        t.append(mido.Message("note_off", channel=9, note=spec["note"], velocity=0, time=60))
    path = tempfile.mktemp(suffix=".mid")
    m.save(path)
    L, R = B.render(path)[:2]
    x = np.asarray(L, np.float64) + np.asarray(R, np.float64)
    step = B.SR
    sp = [bands_db(x, B.SR, C.onset([x[i:i + step]], B.SR) + i, lo, hi) for i in range(0, 4 * step, step)]
    return (float(np.mean(rec)) if rec else None), stroke_diff(sp)


def flatness(chs, sr, lo, hi):
    t0 = C.onset(chs, sr)
    x = sum(chs)
    seg = x[t0 + int(0.03 * sr):t0 + int(0.15 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 14)) ** 2
    f = np.fft.rfftfreq(1 << 14, 1.0 / sr)
    P = X[(f > lo) & (f < hi)] + 1e-30
    return float(np.exp(np.mean(np.log(P))) / np.mean(P))


_RATTLE_SLOT = {"@settle_s": 3, "@settle_db": 4, "@accent_s": 5, "@accent_db": 6}


def _get(cls, note, k):
    import percussion_map as PM
    if k == "@rattle_rate":
        span, n = PM.PERCUSSION_RATTLE[note][:2]
        return n / span
    if k == "@impact_ring":
        return PM.PERCUSSION_RING[note]
    if k == "@rattle_fall":
        r = PM.PERCUSSION_RATTLE[note]
        return r[2] if len(r) > 2 else 0.75
    if k in _RATTLE_SLOT:
        return PM.PERCUSSION_RATTLE[note][_RATTLE_SLOT[k]]
    return getattr(cls, k)


def _set(cls, note, k, v):
    """A class attribute, or one of the rattle's own numbers in the map
    (whose per-note ring classes are cached, so the cache goes)."""
    import percussion_map as PM
    if k == "@rattle_rate":
        span = PM.PERCUSSION_RATTLE[note][0]
        PM.PERCUSSION_RATTLE[note] = (span, max(2, int(round(v * span)))) + tuple(PM.PERCUSSION_RATTLE[note][2:])
    elif k == "@rattle_fall":
        r = list(PM.PERCUSSION_RATTLE[note])
        r[2] = min(0.99, float(v))
        PM.PERCUSSION_RATTLE[note] = tuple(r)
    elif k in _RATTLE_SLOT:
        r = list(PM.PERCUSSION_RATTLE[note])
        r[_RATTLE_SLOT[k]] = float(v)
        PM.PERCUSSION_RATTLE[note] = tuple(r)
    elif k == "@impact_ring":
        PM.PERCUSSION_RING[note] = float(v)
        PM._RING_CLASSES.clear()
    else:
        setattr(cls, k, float(v))


def crackle(y, sr):
    """The largest rise, in dB, from one 5 ms step to the next in the tail
    (after 40 ms, above 700 Hz, while within 60 dB of the peak). A decaying
    stroke barely rises at all (VSCO's: 1-9 dB); the open conga's first
    fit rose 34 -- crackle from a jitter the grid and the flatness, both
    averages over windows, could not see."""
    from scipy.signal import butter, sosfiltfilt
    t0 = C.onset([y], sr)
    hp = sosfiltfilt(butter(4, 700, btype="high", fs=sr, output="sos"), y)[t0:t0 + int(0.5 * sr)]
    n = int(0.005 * sr)
    e = 10 * np.log10(np.convolve(hp * hp, np.ones(n) / n, "valid")[::n] + 1e-30)
    e = e - e.max()
    d = np.diff(e)[8:]
    live = e[9:] > -60
    d = d[live[:len(d)]] if live[:len(d)].any() else d
    return float(d.max()) if len(d) else 0.0


def contrast(y, sr):
    """How far the top (above 3 kHz) falls from the strike's first 3 ms to
    5-15 ms, in dB: what makes an attack sharp. VSCO's cowbell falls 4.7
    (the mean of its eight takes); the first fit's fell 2.3, its modes'
    jitter keeping the top ringing -- Ben: "not as sharp of an attack, and a
    bit more modal"."""
    from scipy.signal import butter, sosfiltfilt
    t0 = C.onset([y], sr)
    h = sosfiltfilt(butter(4, 3000, btype="high", fs=sr, output="sos"), y)
    a = np.mean(h[t0:t0 + int(0.003 * sr)] ** 2)
    b = np.mean(h[t0 + int(0.005 * sr):t0 + int(0.015 * sr)] ** 2)
    return float(10 * np.log10((a + 1e-30) / (b + 1e-30)))


def fit(inst, recs, rflat, vels, maxfev):
    from scipy.optimize import minimize
    import percussion_map as PM
    spec = INSTS[inst]
    note = spec["note"]
    cls = PM.PERCUSSION[note][1]
    if not spec.get("keep_trim"):
        cls.band_trim_db = ()
    x0 = [max(float(_get(cls, note, k)), C.FLOOR.get(k, 1e-3)) for k in C.PARAMS]
    rcrack = max(crackle(sum(load(p)[0]), 44100) for p in files(inst))
    rcon = float(np.mean([contrast(sum(load(p)[0]), 44100) for p in files(inst)])) if spec.get("contrast") else None
    best = [1e9, None, None]

    def f(z):
        vals = np.exp(z) * np.array(x0)
        for k, v in zip(C.PARAMS, vals):
            _set(cls, note, k, v)
        model, mflat, mcrack = [], [], 0.0
        for v in vels:
            chs, sr = C.render(note, v)
            model.append(C.norm(C.grid(chs, sr)))
            mflat.append(flatness(chs, sr, *spec["flat"]))
            mcrack = max(mcrack, crackle(sum(chs), sr))
        econ = abs(contrast(sum(chs), sr) - rcon) if rcon is not None else 0.0
        e, trim = C.score(model, recs)
        ef = float(np.sqrt(np.mean(np.square(10 * np.log10(np.array(mflat) / np.array(rflat))))))
        ec = max(0.0, mcrack - rcrack)
        tot = float(np.sqrt(e * e + ef * ef + ec * ec + econ * econ))
        if tot < best[0]:
            best[:] = [tot, vals, trim]
            print("   %6.3f dB (grid %.2f flat %.2f crackle %.1f attack %.1f)  %s  trim %s" % (
                tot, e, ef, ec, econ, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(C.PARAMS, vals)),
                " ".join("%+.1f" % t for t in trim)), flush=True)
        return tot
    n = len(C.PARAMS)
    simplex = np.vstack([np.zeros(n)] + [0.4 * np.eye(n)[i] * (1 if i % 2 else -1) for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                      "adaptive": True})
    return best


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    inst = pos[0]
    spec = INSTS[inst]
    if "params" in spec:
        C.PARAMS = spec["params"]
    HOLD[0] = spec.get("hold", 1.0)
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import percussion_map as PM
    f0 = PM.PERCUSSION[spec["note"]][2]
    if "--modes" in argv:
        ms = modes(inst, f0)
        print("== %s: %d modes over %.1f Hz" % (inst, len(ms), f0))
        print("    DRUM_MODES = (%s)" % ", ".join("(%.4f, %.1f, %.0f)" % m for m in ms))
        return 0
    if "--scatter" in argv:
        r, m = scatter(inst)
        print("== %s: takes of one stroke differ %s dB; the model's strokes %.1f dB" % (
            inst, "%.1f" % r if r is not None else "--", m))
        return 0
    ss = strokes(inst)
    gs = grouped(ss)
    print("== %s, %d strokes: %s" % (inst, len(ss), "  ".join(
        "%s %.0f" % (os.path.basename(p)[:24], l - max(s[1] for s in ss)) for _, l, _, p in ss)))
    cache = {}
    names = list(gs)
    if "--fit" in argv:
        if names == ["all"]:
            vels = [100]
        else:
            vels = [C.model_velocity(spec["note"], gs[g][0], cache) for g in names]
        recs = []
        rflat = []
        for g in names:
            r = C.norm(np.where(gs[g][1] < -100, -200.0, gs[g][1]))
            recs.append(np.where(gs[g][1] < -100, -200.0, r))
            rflat.append(float(np.mean([flatness(*load(p), *spec["flat"]) for p in gs[g][2]])))
        print("== fit at velocities %s, recorded flatness %s" % (vels, " ".join("%.3f" % x for x in rflat)),
              flush=True)
        e, vals, trim = fit(inst, recs, rflat, vels, int(next(
            (a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 300)))
        print("   BEST %.3f dB" % e)
        for k, v in zip(C.PARAMS, vals):
            print("    %s = %.6g" % (k, v))
        print("    band_trim_db = (%s)" % ", ".join("(%.0f, %.1f)" % (c, t) for c, t in zip(C.CENTRES, trim)))
        return 0
    for g in names:
        drop, gr, _ = gs[g]
        C.show("recorded %s (%.1f dB)" % (g, drop), gr)
        if "--model" in argv:
            v = 100 if g == "all" else C.model_velocity(spec["note"], drop, cache)
            chs, sr = C.render(spec["note"], v)
            m = C.grid(chs, sr)
            C.show("model v%d, minus recorded" % v, np.where(gr < -100, np.nan, (m - m.max()) - gr))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
