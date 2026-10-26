#!/usr/bin/env python3
"""Fit the kit's crashes (GM 49, 57) to DrumGizmo DRSKit's, struck hard.

    python3 examples/crash_fit.py [REFS] [--model] [--fit [--maxfev=N]] [--crash=49,57]
    python3 examples/crash_fit.py --orch [--model] [--fit]   the Orchestra set's 57 and 59
    python3 examples/crash_fit.py --jazz [--model] [--fit]   the Jazz set's 49, 51 and 53
    python3 examples/crash_fit.py --hats [--model] [--fit]   the kit's closed and open hats

--hats: STANDARD'S HATS (GM 42, 46) to DRSKit's, a kit drummer's (CC-BY
4.0, measured only; ~/Documents/refs/drums/drskit_more: Hihat_closed, 24
strokes, cut 0.25-0.4 s on; Hihat_open, 18, 4-7 s), on the hat's close
microphone. They were Iowa's, a percussionist's: the stick hats darker (-6.9
dB of their energy over 8 kHz where a kit hat has -1.4), and under 250 Hz
the stand's thump, which the hats carried -- and which, matched by level,
stood in for the sizzle (Ben, all along: "the hi-hat was quiet"). The grid
starts at 125 Hz here (HAT_EDGES), so the thump is scored.

--jazz: the JAZZ set's CYMBALS (program 32; the SC-8850's Jazz Crash, Ride
and Ride Bell) to soneproject's jazz-bar kit (Freesound pack 25895, CC0;
~/Documents/refs/jazz_kit_soneproject/wav; examples/jazzkit_survey.py told
its plates apart), its takes JAZZ_TAKES, a Zoom H1's two channels summed in
power. They are cut 0.5-3.4 s after the strike: a window past a take's end
weighs nothing, and the room under them is clipped (CLIP), as perc_fit's
jazz drums are.

--orch: the ORCHESTRA set's CONCERT CYMBALS (program 48, SC-55 p.70) to VCSL's
clash pairs (CC0; ~/Documents/refs/vcsl/clash1, clash2; examples/orch_fit.py
chose them): 59 to "Clash Cymbals 1", 57 to "Clash Cymbals 2", a stereo pair
summed in power, played from the set (their own classes, so the kit's crashes
are not moved). Their "short" (choked) hits are not strokes of this note.

REFS (default ~/Documents/refs/drums/drskit) holds Crash_left_shank/ and
Crash_right_shank/ as examples/remote_zip.py pulled them from DRSKit 2.1
(CC-BY 4.0; ~/Documents/refs/sources.md): 11 and 12 strokes of the stick's
shank on the edge, the way a kit drummer crashes, ~35 dB from the softest to
the hardest, 6-10 s each, so the whole ring is there. Each is read on the
overheads (OHL and OHR, summed in power): a crash has no close microphone.
The left crash stands for 49 (panned left), the right for 57.

WHY THESE AND NOT IOWA'S. The crashes were fitted to Iowa's 17" and 18"
suspended cymbals, stick on the bow, pp/mf/ff -- a percussionist controlling
the plate. A kit crash is hit far harder, and a hard hit is a different
sound, not a louder one: the stick's shank excites the low modes, and the
plate's nonlinearity then carries that energy UP, so 2-16 kHz swells for
100-400 ms after the strike. Iowa's strokes never reach that regime.

What a stroke is, on a GRID of octave bands (250 Hz - 16 kHz) by time windows
(T below): each cell's mean power in dB, re the stroke's loudest cell, and the
stroke's level (its loudest 150 ms, as drumset_check reads one). Strokes are
grouped by level into soft, mid and loud, and the model is rendered at the
velocities whose level sits as far under velocity 127 as each group sits under
the loudest stroke.

--model renders the GM notes dry and reads them the same way (L and R summed
in power).
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from drum_fit import CH, read  # noqa: E402

CRASH = {49: "Crash_left_shank", 57: "Crash_right_shank"}
EDGES = (250, 500, 1000, 2000, 4000, 8000, 16000)
T = ((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25),
     (0.25, 0.50), (0.50, 1.00), (1.0, 1.5), (1.5, 2.5), (2.5, 4.0))
GROUPS = ("soft", "mid", "loud")


def onset(chs, sr):
    p = sum(c * c for c in chs)
    w = int(0.0005 * sr)
    e = np.convolve(p, np.ones(w) / w, 'same')
    return max(0, int(np.flatnonzero(e > 0.01 * e.max())[0]) - int(0.001 * sr))


def level(chs, sr):
    """The loudest 150 ms, RMS dB (drumset_check's reading)."""
    p = sum(c * c for c in chs)
    c = np.concatenate(([0.0], np.cumsum(p)))
    n = int(0.15 * sr)
    m = (c[n:] - c[:-n]).max() / n
    return 10 * np.log10(m + 1e-30)


def grid(chs, sr):
    """Octave bands x windows, mean power dB, absolute."""
    t0 = onset(chs, sr)
    out = np.full((len(EDGES) - 1, len(T)), -200.0)
    for j, (a, b) in enumerate(T):
        i0, i1 = t0 + int(a * sr), t0 + int(b * sr)
        if i1 > len(chs[0]):
            continue
        n = i1 - i0
        N = max(n, 4096)
        f = np.fft.rfftfreq(N, 1.0 / sr)
        P = sum(np.abs(np.fft.rfft(c[i0:i1] * np.hanning(n), N)) ** 2 for c in chs)
        P = P / (n * 0.375)            # mean power, Hann's energy
        for i, (lo, hi) in enumerate(zip(EDGES[:-1], EDGES[1:])):
            out[i, j] = 10 * np.log10(P[(f >= lo) & (f < hi)].sum() * (N / n) / N + 1e-30)
    return out


def layer_of(p):
    return int(re.match(r"(\d+)-", os.path.basename(p)).group(1))


ORCH = "--orch" in sys.argv
JAZZ = "--jazz" in sys.argv
HATS = "--hats" in sys.argv
HAT_TAKES = {42: "Hihat_closed", 46: "Hihat_open"}
HAT_REFS = os.path.expanduser("~/Documents/refs/drums/drskit_more")
HAT_EDGES = (125, 250, 500, 1000, 2000, 4000, 8000, 16000)
JAZZ_WAV = os.path.expanduser("~/Documents/refs/jazz_kit_soneproject/wav")
# one plate each: the crash's 1463, 1757, 3136 Hz in every take; the bow's two;
# the cup's 383, 719, 1397 Hz, tonal
# THE TAIL'S TARGET (--jazz): each band's decay, dB/s, over a span of the
# longest take, scored beside the grid (TAIL_W: 3 dB/s weighs as 1 dB of
# grid). The grid reads levels, and with the takes cut short it let the
# crash's tail fall 6-7 dB/s in every band, all aftersound, where the take
# falls 12-26, faster up high -- a ring's shape, which only the ring has
JAZZ_TAIL = {49: ("cymbals2fb-7", 0.5, 2.5), 51: ("ride1", 0.5, 2.0), 53: ("ride4", 0.2, 1.05)}
TAIL_W = 1.0 / 3.0
JAZZ_TAKES = {49: ("crash1", "cymb2da-7", "cymbals6d", "cymbals6e", "cymbals2fb-7"),
              51: ("ride1", "ride2"),
              53: ("ride3", "ride4", "cymbals73", "cymbals74", "cymbals75")}
ORCH_CLASH = {59: "clash1", 57: "clash2"}
_DYN = ("pp", "mp", "mf", "f", "ff", "fff")


def _orch_layer(p):
    m = re.search(r"_(p+|mp|mf|f+)(\d+)\.wav$", os.path.basename(p))
    return 10 * _DYN.index(m.group(1)) + int(m.group(2))


def refs_for(refs, note):
    if HATS:
        out = []
        for p in sorted(glob.glob(os.path.join(HAT_REFS, "*-%s.wav" % HAT_TAKES[note])), key=layer_of):
            a, sr = read(p)
            chs = [a[:, CH["Hihat"]]]
            out.append((layer_of(p), level(chs, sr), grid(chs, sr)))
        return out
    if JAZZ:
        out = []
        for nm in JAZZ_TAKES[note]:
            a, sr = read(os.path.join(JAZZ_WAV, nm + ".wav"))
            chs = [a[:, 0].astype(np.float64), a[:, -1].astype(np.float64)]
            g = grid(chs, sr)
            # ...its last quarter not read: the takes are cut, and faded out
            # where the sampler trimmed them -- read, a take's last window fell
            # under the longer takes' at the same time, and the tail rose
            # where the short takes dropped out of the mean
            span = (len(chs[0]) - onset(chs, sr)) / sr
            for j, (_a, b) in enumerate(T):
                if b > 0.75 * span:
                    g[:, j] = -200.0
            out.append((0, level(chs, sr), g))
        out.sort(key=lambda s: s[1])            # by level: soft to loud
        return [(i, l, g) for i, (_, l, g) in enumerate(out)]
    if ORCH:
        out = []
        files = [p for p in glob.glob(os.path.join(os.path.expanduser("~/Documents/refs/vcsl"),
                                                   ORCH_CLASH[note], "*.wav")) if "short" not in p]
        for p in sorted(files, key=_orch_layer):
            a, sr = read(p)
            chs = [a[:, 0], a[:, -1]]
            out.append((_orch_layer(p), level(chs, sr), grid(chs, sr)))
        return out
    d = os.path.join(refs, CRASH[note])
    out = []
    for p in sorted(glob.glob(os.path.join(d, "*.wav")), key=layer_of):
        a, sr = read(p)
        chs = [a[:, CH["OHL"]], a[:, CH["OHR"]]]
        out.append((layer_of(p), level(chs, sr), grid(chs, sr)))
    return out


def tail_rates(chs, sr, a, b, w=0.25):
    """Each band's decay, dB/s: its power in a window at a against one ending at b."""
    t0 = onset(chs, sr)
    out = []
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        def band(t1, t2):
            i0, i1 = t0 + int(t1 * sr), t0 + int(t2 * sr)
            n = i1 - i0
            f = np.fft.rfftfreq(n, 1.0 / sr)
            P = sum(np.abs(np.fft.rfft(c[i0:i1] * np.hanning(n))) ** 2 for c in chs)
            return 10 * np.log10(P[(f >= lo) & (f < hi)].sum() + 1e-30)
        out.append((band(a, a + w) - band(b - w, b)) / (b - a - w))
    return np.array(out)


def jazz_tail(note):
    nm, a, b = JAZZ_TAIL[note]
    x, sr = read(os.path.join(JAZZ_WAV, nm + ".wav"))
    return tail_rates([x[:, 0], x[:, -1]], sr, a, b, 0.25 if b - a > 1.2 else 0.2), a, b


def grouped(strokes):
    """soft / mid / loud: (level re the loudest, mean grid re its own top cell)."""
    top = max(l for _, l, _ in strokes)
    n = len(strokes)
    picks = {"soft": strokes[n // 6:n // 3 + 1], "mid": strokes[n // 2:2 * n // 3 + 1],
             "loud": strokes[-max(2, n // 6):]}
    out = {}
    for g, ss in picks.items():
        # ...each cell over the strokes that reach it: a take cut short (the
        # jazz kit's) is -200 past its end, and averaged in it read the longer
        # takes' tails at -100 dB
        gs = np.array([np.where(s[2] < -150.0, np.nan, s[2] - s[2].max()) for s in ss])
        with np.errstate(all="ignore"):
            gr = np.nanmean(gs, 0)
        gr = np.where(np.isnan(gr), -200.0, gr)
        out[g] = (float(np.mean([s[1] for s in ss])) - top, gr)
    return out


KIT = 0          # the drum set the note is played from (snare_fit.py --concert: 48)


def render(note, vel, secs=4.2):
    import blockrender as B
    from drumset_check import note_file
    L, R = B.render(note_file(KIT, note, vel=vel, hold=secs))[:2]
    return [np.asarray(L, np.float64), np.asarray(R, np.float64)], B.SR


def model_velocity(note, drop_db, cache):
    """The velocity whose level sits drop_db under velocity 127's."""
    def lv(v):
        if v not in cache:
            chs, sr = render(note, v, 0.6)
            cache[v] = level(chs, sr)
        return cache[v]
    top = lv(127)
    lo, hi = 1, 127
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if lv(mid) - top < drop_db:
            lo = mid
        else:
            hi = mid
    return hi


def show(title, g):
    print("  %s" % title)
    print("      Hz  " + " ".join("%6s" % ("%g" % (1000 * a)) for a, _ in T) + "   (window start, ms)")
    for i, lo in enumerate(EDGES[:-1]):
        print("   %5d  " % lo + " ".join("%6.1f" % v for v in g[i]))


# THE FIT. Shape parameters searched (in log space, from the class's own
# values); the band trim solved inside each candidate in closed form, because
# a trim scales a band's every cell alike and so cannot be told apart from
# what the shape is doing unless it is re-solved under each shape.
PARAMS = ("ring_peak_hz", "ring_decay_floor", "ring_decay_below", "ring_decay_above",
          "aftersound_fraction", "aftersound_dbs", "bloom_gain", "bloom_seconds",
          "bloom_center_hz", "bloom_octaves", "bloom_swell", "bloom_gain_slope",
          "chiff_volume", "chiff_width")
FLOOR = {"aftersound_fraction": 0.01, "aftersound_dbs": 12.0, "bloom_gain": 0.05,
         "bloom_gain_slope": 0.1, "bloom_seconds": 0.004, "bloom_swell": 0.2,
         "ring_decay_below": 0.5, "ring_decay_above": 0.5}
START = {"chiff_width": 0.01, "chiff_bandwidth": 0.05}
CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(EDGES[:-1], EDGES[1:]))
# 0-10 ms is under one kernel block (BLK = 512): no onset shorter than that
# survives the fast renderer, so that window is weighed lightly
COL_W = np.array([0.3] + [1.0] * (len(T) - 1))


def norm(g):
    """dB re the grid's total energy, so a level offset is not a shape error."""
    return g - 10 * np.log10((10 ** (g / 10)).sum())


def weights(rec):
    # the tail counts: weighted by level alone, a ring 15 dB too long at 2.5 s
    # cost the first fit almost nothing, and that is a crash that will not stop
    # and a cell under -100 dB is past the end of the file (DRSKit's soft
    # snare strokes stop at 0.25 s): silence, not a level, so it weighs nothing
    w = np.clip((rec + 75.0) / 45.0, 0.15, 1.0) * COL_W
    return np.where(rec < -100.0, 0.0, w)


# A FLOOR (dB re the grid's total; None: none): a take's room and noise
# under its sound, where ours is truly silent. Unclipped, Iowa's guiro read
# -67 to -80 dB past its scrape and ours -200, 120 dB of error a cell, and
# the fit rang each ridge 0.32 s to fill the room's hiss
CLIP = None


def _clip(g):
    return g if CLIP is None else np.where(g < -100.0, g, np.maximum(g, CLIP))


def score(model, recs):
    """(rms dB, trim): the weighted rms over every group's cells after the
    band trim common to all groups is solved for."""
    if CLIP is not None:
        recs = [_clip(r) for r in recs]
    trim = np.zeros(len(CENTRES))
    for _ in range(4):
        num = np.zeros(len(CENTRES))
        den = np.zeros(len(CENTRES))
        for m, r in zip(model, recs):
            mm = np.maximum(norm(m + trim[:, None]), CLIP if CLIP is not None else -1e9)
            w = weights(r)
            num += (w * (mm - r)).sum(1)
            den += w.sum(1)
        trim -= num / den
    trim -= trim.mean()                # a level, which norm() ignores anyway
    err = []
    wsum = 0.0
    for m, r in zip(model, recs):
        w = weights(r)
        mm = np.maximum(norm(m + trim[:, None]), CLIP if CLIP is not None else -1e9)
        err.append((w * (mm - r) ** 2).sum())
        wsum += w.sum()
    return float(np.sqrt(sum(err) / wsum)), trim


def set_params(cls, vals):
    for k, v in zip(PARAMS, vals):
        setattr(cls, k, float(v))


def fit(note, recs, vels, maxfev):
    from scipy.optimize import minimize
    import percussion_map as PM
    cls = PM.KITS[KIT][note][1] if KIT else PM.PERCUSSION[note][1]
    cls.band_trim_db = ()
    # ...a knob the class leaves at None (the module's default) from where perc_fit starts it
    x0 = [max(float(getattr(cls, k) if getattr(cls, k) is not None else START.get(k, 1e-3)), FLOOR.get(k, 1e-3))
          for k in PARAMS]
    best = [1e9, None, None]

    tail = jazz_tail(note) if JAZZ else None

    def f(z):
        vals = np.exp(z) * np.array(x0)
        set_params(cls, vals)
        rs = [render(note, v) for v in vels]
        model = [norm(grid(*r)) for r in rs]
        e, trim = score(model, recs)
        if tail is not None:
            # ...and the tail's decay, on the loudest velocity's render
            rt, a, b = tail
            rm = tail_rates(rs[-1][0], rs[-1][1], a, b, 0.25 if b - a > 1.2 else 0.2)
            e = float(np.sqrt(e * e + (TAIL_W * np.sqrt(np.mean((rm - rt) ** 2))) ** 2))
        if e < best[0]:
            best[:] = [e, vals, trim]
            print("   %6.3f dB  %s  trim %s" % (e, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(PARAMS, vals)),
                                                " ".join("%+.1f" % t for t in trim)), flush=True)
        return e
    # steps of x1.6 each way in every parameter: zero is not a scale
    n = len(PARAMS)
    simplex = np.vstack([np.zeros(n)] + [0.47 * np.eye(n)[i] * (1 if i % 2 else -1) for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                      "adaptive": True})
    return best


def _class_block(src, cls):
    """(start, end) of class CLS's block in tonelib.py's source, to its first
    top-level line (perc_fit's; not imported from it -- importing perc_fit sets
    this module's PARAMS to the drums', and a write took the wrong names)."""
    a = src.index("class %s(" % cls)
    m = re.search(r"\n(?=[^\s\n])", src[a + 1:])
    b = a + 1 + m.start() if m else len(src)
    while src[b - 1] == "\n" and src[b - 2] == "\n":
        b -= 1
    return a, b - 1 if src[b - 1] == "\n" else b


def write_fit(cls, vals, trim):
    """--write: the fitted knobs and band trim into tonelib.py, each replaced in
    the class's own block or added to it (perc_fit's _class_block)."""
    path = os.path.join(HERE, "tonelib.py")
    src = open(path).read()
    a, b = _class_block(src, cls.__name__)
    blk = src[a:b]
    for k, v in zip(PARAMS, vals):
        line = "    %s = %.6g" % (k, v)
        if re.search(r"^    %s = " % k, blk, re.M):
            blk = re.sub(r"^    %s = [^#\n]*" % k, lambda _: line + "  ", blk, count=1, flags=re.M)
        else:
            blk = blk + "\n" + line
    txt = "    band_trim_db = %s" % (tuple((round(c), round(float(t), 1)) for c, t in zip(CENTRES, trim)),)
    if re.search(r"^    band_trim_db = ", blk, re.M):
        blk = re.sub(r"^    band_trim_db = .*$", lambda _: txt, blk, count=1, flags=re.M)
    else:
        blk = blk + "\n" + txt
    open(path, "w").write(src[:a] + blk + src[b:])
    print("    written to %s" % cls.__name__)


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/drums/drskit")
    notes = next((tuple(int(n) for n in a.split("=")[1].split(","))
                  for a in argv if a.startswith("--crash=")),
                 tuple(HAT_TAKES if HATS else JAZZ_TAKES if JAZZ else ORCH_CLASH if ORCH else CRASH))
    global KIT, CLIP, EDGES, CENTRES
    if HATS:
        EDGES = HAT_EDGES
        CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(EDGES[:-1], EDGES[1:]))
        notes = tuple(n for n in notes if n in HAT_TAKES) or tuple(HAT_TAKES)
    if ORCH:
        KIT = 48
    if JAZZ:
        KIT = 32
        CLIP = -60.0
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    for note in notes:
        strokes = refs_for(refs, note)
        if "--fit" in argv:
            gs = grouped(strokes)
            cache = {}
            vels = [model_velocity(note, gs[g][0], cache) for g in GROUPS]
            recs = [norm(gs[g][1]) for g in GROUPS]
            maxfev = int(next((a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 300))
            print("== GM %d fit at velocities %s" % (note, vels), flush=True)
            e, vals, trim = fit(note, recs, vels, maxfev)
            print("   BEST %.3f dB" % e)
            for k, v in zip(PARAMS, vals):
                print("    %s = %.6g" % (k, v))
            print("    band_trim_db = (%s)" % ", ".join("(%.0f, %.1f)" % (c, t) for c, t in zip(CENTRES, trim)))
            if "--write" in argv:
                import percussion_map as PM
                write_fit(PM.KITS[KIT][note][1] if KIT else PM.PERCUSSION[note][1], vals, trim)
            continue
        gs = grouped(strokes)
        print("== GM %d: %s, %d strokes, levels %s dB re the loudest" % (
            note, (HAT_TAKES if HATS else JAZZ_TAKES if JAZZ else ORCH_CLASH if ORCH else CRASH)[note], len(strokes),
            " ".join("%.0f" % (l - max(s[1] for s in strokes)) for _, l, _ in strokes)))
        cache = {}
        for g in GROUPS:
            drop, gr = gs[g]
            show("recorded %s (%.1f dB)" % (g, drop), gr)
            if "--model" in argv:
                v = model_velocity(note, drop, cache)
                chs, sr = render(note, v)
                m = grid(chs, sr)
                m = m - m.max()
                show("model v%d, minus recorded" % v, m - gr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
