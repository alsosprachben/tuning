#!/usr/bin/env python3
"""The GS gongs (ASIA set 53's Asian, Big and Small Gong; ETHNIC set 50's) to
Iowa MIS's tam-tams, struck pp, mf and ff.

    python3 examples/gong_fit.py [REFS]            measure the recordings
    python3 examples/gong_fit.py [REFS] --model    ...and our gongs, the same way

REFS (default ~/Documents/refs/iowa_gongs/tamtam_wav) holds Iowa's 22", 28"
and 40" tam-tams and 20" wind gong, one strike a take left to ring (30-117 s),
converted from its AIFFs by sox (sources.md). Measure only.

WHAT A TAM-TAM IS, as read here. A struck plate like a cymbal, bigger and
thinner, so three things that a crash only hints at are the whole sound: its
lowest modes are in the bass (the 40" around 50-80 Hz); its energy cascades
UP after the strike, the plate's nonlinearity carrying the mallet's low
modes into the top over a second or more -- the swell a tam-tam is known by,
where a crash's is 100-400 ms; and it rings for a minute.

So each take is read as: its level (the loudest 150 ms, as crash_fit reads a
stroke); a grid of octave bands (63 Hz - 16 kHz) by time windows (T, to 20 s),
each cell in dB re the take's loudest cell; per band, the time it peaks (the
bloom) and its decay rate after the peak (dB/s, a line through the cells from
the peak down to 40 dB under it); and the strongest spectral peaks under 1
kHz in the first 2 s (the low modes, as ratios of the lowest).
"""
import os
import sys

import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

SIZES = ("22tamtam", "28tamtam", "40tamtam", "20windgong")
DYNS = ("pp", "mf", "ff")
EDGES = (63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
T = ((0.0, 0.05), (0.05, 0.15), (0.15, 0.3), (0.3, 0.6), (0.6, 1.0), (1.0, 1.5),
     (1.5, 2.5), (2.5, 4.0), (4.0, 6.0), (6.0, 9.0), (9.0, 13.0), (13.0, 20.0))


def load(path):
    sr, x = wavfile.read(path)
    x = x.astype(np.float64)
    if x.ndim > 1:
        x = np.sqrt((x * x).mean(1)) * np.sign(x.sum(1))   # L and R in power, signed
    return x, sr


def strike(x, sr):
    """The sample the strike lands on: back from the loudest 10 ms in the
    take's first 15 s to where its 2 ms energy first came within 20 dB of it
    -- not the take's first crossing of a threshold, which in a pp take is a
    noise before the strike (Iowa's quiet takes start with the room)."""
    w = int(0.002 * sr)
    n = min(len(x), int(15 * sr))
    c = np.concatenate([[0.0], np.cumsum(x[:n] ** 2)])
    e = (c[w:] - c[:-w]) / w
    k = int(np.argmax(e))
    j = k
    while j > 0 and e[j] > e[k] * 0.01:
        j -= 1
    while j > 0 and e[j] > e[k] * 1e-3 and k - j < int(0.05 * sr):
        j -= 1
    return j


def level(x, sr):
    """The loudest 150 ms, in dB (crash_fit's stroke level)."""
    w = int(0.15 * sr)
    c = np.concatenate([[0.0], np.cumsum(x[:int(10 * sr)] ** 2)])
    e = (c[w:] - c[:-w]) / w
    return 10 * np.log10(e.max() + 1e-30)


def grid(x, sr):
    """{band: [dB per window]}, mean power per cell, re the loudest cell."""
    out = {}
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        row = []
        for a, b in T:
            seg = x[int(a * sr):int(b * sr)]
            if len(seg) < 64:
                row.append(-200.0)
                continue
            X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2 / len(seg)
            f = np.fft.rfftfreq(len(seg), 1.0 / sr)
            row.append(10 * np.log10(X[(f >= lo) & (f < hi)].sum() + 1e-30))
        out[lo] = row
    top = max(max(r) for r in out.values())
    return {k: [v - top for v in r] for k, r in out.items()}


def bloom_decay(row):
    """(the time the band peaks, s; its decay after, dB/s), from a grid row."""
    mid = [0.5 * (a + b) for a, b in T]
    k = int(np.argmax(row))
    pk = row[k]
    xs = [mid[i] for i in range(k, len(row)) if row[i] > pk - 40.0]
    ys = [row[i] for i in range(k, len(row)) if row[i] > pk - 40.0]
    rate = -np.polyfit(xs, ys, 1)[0] if len(xs) >= 3 else float('nan')
    return mid[k], rate


def low_modes(x, sr, n=8):
    """The strongest peaks under 1 kHz in the first 2 s, as (Hz, dB re the strongest)."""
    seg = x[:int(2.0 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1.0 / sr)
    m = (f > 30) & (f < 1000)
    Xm, fm = X[m], f[m]
    loc = [i for i in range(2, len(Xm) - 2) if Xm[i] == Xm[i - 2:i + 3].max()]
    loc = sorted(loc, key=lambda i: -Xm[i])[:n]
    top = Xm[loc[0]] if loc else 1.0
    return sorted((round(float(fm[i]), 1), round(20 * np.log10(Xm[i] / top), 1)) for i in loc)


def read(refs):
    out = {}
    for g in SIZES:
        for d in DYNS:
            p = os.path.join(refs, "%s.%s.wav" % (g, d))
            if not os.path.exists(p):
                continue
            x, sr = load(p)
            i0 = strike(x, sr)
            x = x[i0:]
            out[(g, d)] = dict(level=level(x, sr), grid=grid(x, sr), modes=low_modes(x, sr))
    return out


def report(m, tag):
    for (g, d), r in sorted(m.items()):
        print("%s %-10s %s  level %6.1f dB" % (tag, g, d, r['level']))
        print("      band  " + " ".join("%6.2f" % (0.5 * (a + b)) for a, b in T) + "   peak s  dB/s")
        for lo, row in r['grid'].items():
            t, rate = bloom_decay(row)
            print("    %6d  " % lo + " ".join("%6.1f" % v for v in row) + "   %5.2f %6.1f" % (t, rate))
        print("      low modes:", " ".join("%.0f(%+.0f)" % mh for mh in r['modes']))


# ---------------------------------------------------------------- the modes
NMODES = 200          # as many as the crash carries
MODE_TOP_HZ = 8000.0
MODE_FLOOR_DB = -60.0


def take(refs, g, d):
    x, sr = load(os.path.join(refs, "%s.%s.wav" % (g, d)))
    return x[strike(x, sr):], sr


def modes(x, sr):
    """[(Hz, dB re the strongest)] -- the peaks of the first second's spectrum
    (Hann, zero-padded to 0.25 Hz), the strongest NMODES within MODE_FLOOR_DB,
    each a local maximum over +-3 bins, interpolated parabolically in dB."""
    seg = x[:int(1.0 * sr)]
    n = 1 << int(np.ceil(np.log2(4 * sr)))
    X = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) + 1e-12)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    lo, hi = np.searchsorted(f, 30.0), np.searchsorted(f, MODE_TOP_HZ)
    loc = [i for i in range(lo + 3, hi - 3) if X[i] == X[i - 3:i + 4].max()]
    top = max(X[i] for i in loc)
    # A SHARE PER OCTAVE, not the strongest overall: a tam-tam's low modes are
    # dense and loud, and the strongest 200 all sat under 1.7 kHz -- none in
    # the 2-8 kHz the shimmer is. Each octave from 30 Hz takes its strongest
    # NMODES / 8, within MODE_FLOOR_DB of the take's strongest.
    per = NMODES // 8
    pick = []
    edge = 30.0
    while edge < MODE_TOP_HZ:
        band = [i for i in loc if edge <= f[i] < 2 * edge and X[i] >= top + MODE_FLOOR_DB]
        pick += sorted(band, key=lambda i: -X[i])[:per]
        edge *= 2
    out = []
    for i in pick:
        a, b, c = X[i - 1], X[i], X[i + 1]
        den = a - 2 * b + c
        dk = 0.5 * (a - c) / den if abs(den) > 1e-9 else 0.0
        out.append((float(f[i] + dk * (f[1] - f[0])), float(b - top)))
    out = sorted(out)
    # the base: the lowest mode within 30 dB of the strongest -- not a room
    # rumble 45 dB down that happens to be lower
    k = next(j for j, (hz, db) in enumerate(out) if db > -30.0)
    return out[k:]


def tone_db(x, sr, hz, t0, t1):
    """The level of a sinusoid at hz over [t0, t1) s (a Hann-windowed single
    bin), in dB."""
    seg = x[int(t0 * sr):int(t1 * sr)]
    if len(seg) < 16:
        return -300.0
    t = np.arange(len(seg)) / sr
    w = np.hanning(len(seg))
    v = np.abs((seg * w * np.exp(-2j * np.pi * hz * t)).sum()) / w.sum()
    return 20 * np.log10(v + 1e-15)


def mode_gain_decay(x, sr, hz):
    """(level 0.03-0.13 s, dB; decay, dB/s) of the mode at hz: its level in
    0.25 s windows, a line through them to 30 dB under the first or 8 s,
    whichever comes first -- from 0.2 s under 500 Hz, and from 1.5 s above,
    AFTER THE BLOOM: at ff the upper modes are still rising until 0.5-1.25 s,
    and a line through the rise read their decay too slow (the model's top
    sat 10 dB over the recording at 5-11 s)."""
    g = tone_db(x, sr, hz, 0.03, 0.13)
    ts, ls = [], []
    t = 0.2 if hz < 500.0 else 1.5
    while t < 8.0:
        v = tone_db(x, sr, hz, t, t + 0.25)
        if ls and v < ls[0] - 30.0:
            break
        ts.append(t + 0.125)
        ls.append(v)
        t += 0.25
    rate = -np.polyfit(ts, ls, 1)[0] if len(ts) >= 4 else float('nan')
    return g, rate


def stroke_tilt2(refs, g):
    """The same, from mf and ff alone over 0.03-0.3 s: the pp takes' upper
    bands are the recording's noise floor, which flattened the slope."""
    pts = []
    for d in ("mf", "ff"):
        x, sr = take(refs, g, d)
        seg = x[int(0.03 * sr):int(0.3 * sr)]
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        f = np.fft.rfftfreq(len(seg), 1.0 / sr)
        b = [10 * np.log10(X[(f >= lo) & (f < 2 * lo)].sum() + 1e-30) for lo in (125, 250, 500, 1000, 2000, 4000)]
        pts.append((level(x, sr), np.polyfit(np.arange(len(b)), np.array(b) - b[0], 1)[0]))
    (l0, t0), (l1, t1) = pts
    return (t1 - t0) / (l1 - l0), pts


def stroke_tilt(refs, g):
    """dB of the top over the bottom, per octave, per dB of stroke: the strike's
    spectrum (0-0.15 s) in octave bands for pp, mf, ff, each re its own 125-250
    Hz band; the slope of (band dB vs octave) against the stroke's level."""
    rows = []
    for d in DYNS:
        x, sr = take(refs, g, d)
        seg = x[:int(0.15 * sr)]
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        f = np.fft.rfftfreq(len(seg), 1.0 / sr)
        b = [10 * np.log10(X[(f >= lo) & (f < 2 * lo)].sum() + 1e-30) for lo in (125, 250, 500, 1000, 2000, 4000)]
        tilt = np.polyfit(np.arange(len(b)), np.array(b) - b[0], 1)[0]     # dB per octave
        rows.append((level(x, sr), tilt))
    lv, tl = zip(*rows)
    return float(np.polyfit(lv, tl, 1)[0]), rows


def fit_size(refs, g):
    x, sr = take(refs, g, "ff")
    ms = modes(x, sr)
    f0 = ms[0][0]
    gd = [mode_gain_decay(x, sr, hz) for hz, _ in ms]
    top = max(v for v, _ in gd)
    tilt, rows = stroke_tilt2(refs, g)
    return dict(f0=f0, ratios=[hz / f0 for hz, _ in ms], gains=[v - top for v, _ in gd],
                rates=[r for _, r in gd], tilt=tilt, rows=rows, ref_db=level(x, sr))


KEY = {"22tamtam": 75, "28tamtam": 73, "40tamtam": 74}     # ASIA set 53's keys


def render_strike(key, vel, secs=21.0, kit=52):
    """One strike of key in the set, dry (no reflections), mono power sum."""
    os.environ.setdefault("TUNING_REFLECT", "0")
    import mido
    import blockrender as B
    mf = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=9, program=kit, time=0))
    tr.append(mido.Message("note_on", channel=9, note=key, velocity=vel, time=240))
    tr.append(mido.Message("note_off", channel=9, note=key, velocity=0, time=240))
    tr.append(mido.Message("note_on", channel=9, note=0, velocity=0, time=int(secs * 960)))
    L, R = B.render(mf, "even")[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    x = np.sqrt(L * L + R * R)
    x = x * np.sign(L + R + 1e-30)
    return x[strike(x, B.SR):], B.SR


def model(refs):
    """Our gongs read as the recordings are, at the velocities whose levels
    sit under velocity 127 as the takes' sit under their ff (the drums'
    square law: 40 log10 v/127)."""
    out = {}
    ref = read(refs)
    for g, key in KEY.items():
        top = ref[(g, "ff")]['level']
        for d in DYNS:
            v = int(round(127 * 10 ** ((ref[(g, d)]['level'] - top) / 40.0)))
            x, sr = render_strike(key, max(1, min(127, v)))
            out[(g, d)] = dict(level=level(x, sr), grid=grid(x, sr), modes=low_modes(x, sr), vel=v)
    return ref, out


def compare(ref, mod):
    """Band-by-time error per take: the mean |model - ref| over cells where
    the recording is within 45 dB of its loudest AND 10 dB clear of the band's
    own floor (its quietest cell: under that is Iowa's room, which a model
    rightly does not have); the model floored at 60 dB under its loudest."""
    tot = []
    for k in sorted(mod):
        r, m = ref[k]['grid'], mod[k]['grid']
        errs = []
        rows = []
        for lo in r:
            fl = min(r[lo])
            e = [max(m[lo][i], -60.0) - r[lo][i] for i in range(len(T))
                 if r[lo][i] > -45.0 and r[lo][i] > fl + 10.0]
            errs += [abs(v) for v in e]
            tm, rm = bloom_decay(m[lo]), bloom_decay(r[lo])
            rows.append("    %6d  err %s   peak %4.2f/%4.2f s  decay %5.1f/%5.1f dB/s" % (
                lo, " ".join("%+5.0f" % v for v in e[:10]), tm[0], rm[0], tm[1], rm[1]))
        print("%s %s  vel %d  level %+.1f dB (ref %+.1f re ff)  mean |err| %.1f dB" % (
            k[0], k[1], mod[k]['vel'], mod[k]['level'] - mod[(k[0], 'ff')]['level'],
            ref[k]['level'] - ref[(k[0], 'ff')]['level'], np.mean(errs) if errs else 0.0))
        print("\n".join(rows))
        tot += errs
    print("ALL mean |err| %.2f dB over %d cells" % (np.mean(tot), len(tot)))
    return float(np.mean(tot))


def fit_bloom(refs):
    """A coarse search over the bloom shared by the three tam-tams (tonelib.
    TamTamProperties): its delay, gain and centre, scored as compare() scores,
    on the mf and ff takes (the dynamics a gong roll plays; pp's limit is the
    tilt's, not the bloom's)."""
    import itertools
    import io
    import contextlib
    import tonelib as TL
    ref = read(refs)
    best = None
    for sec, gain, ctr in itertools.product((0.3, 0.5, 0.8), (2.0, 3.0, 5.0, 8.0), (1500.0, 2500.0)):
        TL.TamTamProperties.bloom_seconds = sec
        TL.TamTamProperties.bloom_gain = gain
        TL.TamTamProperties.bloom_center_hz = ctr
        mod = {}
        for g, key in KEY.items():
            top = ref[(g, "ff")]['level']
            for d in ("mf", "ff"):
                v = int(round(127 * 10 ** ((ref[(g, d)]['level'] - top) / 40.0)))
                with contextlib.redirect_stdout(io.StringIO()):
                    x, sr = render_strike(key, max(1, min(127, v)))
                mod[(g, d)] = dict(level=level(x, sr), grid=grid(x, sr), modes=[], vel=v)
        sub = {k: ref[k] for k in mod}
        with contextlib.redirect_stdout(io.StringIO()):
            err = compare(sub, mod)
        print("  bloom %.1f s  gain %.0f  centre %5.0f Hz   mean |err| %.2f dB" % (sec, gain, ctr, err), flush=True)
        if best is None or err < best[0]:
            best = (err, sec, gain, ctr)
    print("BEST", best)


CLASS = {"22tamtam": "TamTam22Properties", "28tamtam": "TamTam28Properties",
         "40tamtam": "TamTam40Properties"}


def _tuple(name, vals, fmt):
    """'    name = (a, b, ...)' wrapped at 100 columns."""
    head = "    %s = (" % name
    ind = " " * len(head)
    lines, cur = [], head
    for i, v in enumerate(vals):
        piece = (fmt % v) + (", " if i < len(vals) - 1 else ")")
        if len(cur) + len(piece) > 100:
            lines.append(cur.rstrip())
            cur = ind
        cur += piece
    lines.append(cur)
    return "\n".join(lines)


def write_classes(refs):
    """The measured block of each tam-tam class in tonelib.py, in place: its
    mode_ratios, mode_gains, mode_decays and mode_stroke_tilt."""
    import re
    path = os.path.join(HERE, "tonelib.py")
    src = open(path).read()
    for g, cname in CLASS.items():
        r = fit_size(refs, g)
        ok = [q for q in r['rates'] if q == q and q > 0]
        med = float(np.median(ok))
        block = "\n".join([
            _tuple("mode_ratios", r['ratios'], "%.4f"),
            _tuple("mode_gains", [10 ** (v / 20.0) for v in r['gains']], "%.4g"),
            _tuple("mode_decays", [(q if (q == q and q > 0) else med) / 2.0 for q in r['rates']], "%.2f"),
            "    mode_stroke_tilt = %.3f" % r['tilt']])
        a = src.index("class %s(TamTamProperties):" % cname)
        b = src.index("    max_harmonic = len(mode_ratios)", a)
        head = src[a:b]
        k = head.index("    mode_ratios = (")
        src = src[:a] + head[:k] + block + "\n" + src[b:]
        print("  %s: %d modes, base %.2f Hz, decays median %.1f dB/s" % (cname, len(r['ratios']), r['f0'], med))
    open(path, "w").write(src)


def main(argv):
    refs = next((a for a in argv[1:] if not a.startswith('--')),
                os.path.expanduser("~/Documents/refs/iowa_gongs/tamtam_wav"))
    if '--model' in argv:
        ref, mod = model(refs)
        compare(ref, mod)
        return 0
    if '--fit-bloom' in argv:
        fit_bloom(refs)
        return 0
    if '--write' in argv:
        write_classes(refs)
        return 0
    if '--emit' in argv:
        # the measured block each tam-tam class carries (tonelib.TamTam*):
        # ratios to the base mode, gains as amplitudes re the strongest (read
        # at ff: mode_stroke_ref_db 0 is velocity 127), decays as tonelib's D
        # (half the dB/s; a mode whose line did not fit takes the median)
        for g in ("22tamtam", "28tamtam", "40tamtam"):
            r = fit_size(refs, g)
            ok = [q for q in r['rates'] if q == q and q > 0]
            med = float(np.median(ok))
            print("# %s: base %.2f Hz, %d modes, stroke tilt %.3f" % (g, r['f0'], len(r['ratios']), r['tilt']))
            print("    mode_ratios = (%s)" % ", ".join("%.4f" % q for q in r['ratios']))
            print("    mode_gains = (%s)" % ", ".join("%.4g" % (10 ** (v / 20.0)) for v in r['gains']))
            print("    mode_decays = (%s)" % ", ".join("%.2f" % ((q if (q == q and q > 0) else med) / 2.0)
                                                    for q in r['rates']))
            print("    mode_stroke_tilt = %.3f" % r['tilt'])
        return 0
    if '--modes' in argv:
        for g in ("22tamtam", "28tamtam", "40tamtam"):
            r = fit_size(refs, g)
            ok = [q for q in r['rates'] if q == q]
            print("%s  f0 %.1f Hz  %d modes to %.0f Hz  stroke tilt %+.3f dB/oct/dB  (pp/mf/ff: %s)" % (
                g, r['f0'], len(r['ratios']), r['ratios'][-1] * r['f0'], r['tilt'],
                ", ".join("%.0f dB %+.1f dB/oct" % q for q in r['rows'])))
            print("    decay dB/s: median %.1f, 10%% %.1f, 90%% %.1f; first modes: %s" % (
                np.median(ok), np.percentile(ok, 10), np.percentile(ok, 90),
                " ".join("%.0fHz %+.0fdB %.1fdB/s" % (q * r['f0'], gg, rr)
                         for q, gg, rr in list(zip(r['ratios'], r['gains'], r['rates']))[:8])))
        return 0
    report(read(refs), "REF")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
