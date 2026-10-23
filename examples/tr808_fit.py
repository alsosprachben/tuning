#!/usr/bin/env python3
"""The TR-808 set (program 25 on the drum channel) fitted to a real TR-808.

    python3 -I examples/tr808_fit.py                 score every note against its hit
    python3 -I examples/tr808_fit.py --select        level one: which hit each note plays
    python3 -I examples/tr808_fit.py --fit=VOICE[,VOICE] [--write]
                                                     level two: fit a patch's knobs to its hit
                                                     (--write: into tonelib.py)
    python3 -I examples/tr808_fit.py --osc           the six oscillators, read off the cymbal
    python3 -I examples/tr808_fit.py --wav=DIR       write each hit and ours beside it

TWO LEVELS, AS THE SIMMONS WAS (examples/elkit_fit.py). Michael Fischer's
recordings (~/Documents/refs/tr808_fischer, sources.md) are one 808, serial
103852, recorded from its individual outputs with every knob at five
positions: a real machine at 116 settings. Level one picks the setting each
note plays: the GM set whose sample for the note IS an 808 -- GeneralUser
GS's snare, hats, cymbal and cowbell; where GeneralUser has a 909 kick or
sine toms instead, FluidR3's, whose 808 samples are Fischer's own recordings
(its congas match his note for note) -- picks the closest hit. Level two
fits the patch's knobs (tr808.py) to that hit.

THE SCORE is the hit's TIME-FREQUENCY picture: energy in third-octave bands
(31 Hz - 16 kHz) over log-spaced frames (0-5, 5-10, 10-20 ... 1-1.6 s), dB re
its loudest cell, floor -60; the rms difference over the cells either one
holds above the floor, PLUS the rms difference of the hit's balance across
those bands (dB re its total) while the 808's sounds -- its hiss after excluded. The 808's voices are all onset -- a kick's first cycle,
a hat's band dying -- and an octave-band summary over 250 ms (elkit_fit's)
cannot see where they differ. A resonator's PITCH TRACK is scored beside it,
2 dB a semitone, over its first 150 ms. Level is not scored: the set is
balanced against Standard separately (tr808_balance.py).
"""
import os
import sys
import tempfile
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")      # Fischer's WAVs end a byte short of their headers

import elkit_fit as E          # noqa: E402  (drum_mid, theirs, ours, read, measure)

KIT = 25
E.KIT = KIT
PACK = os.path.expanduser("~/Documents/refs/tr808_fischer/pack/TR808WAV")

# which of Fischer's voices each note is, and which GM set's sample is an 808
VOICE = {36: "BD", 37: "RS", 38: "SD", 41: "LT", 43: "LT", 45: "MT", 47: "MT", 48: "HT",
         50: "HT", 42: "CH", 44: "CH", 46: "OH", 49: "CY", 56: "CB", 62: "HC", 63: "MC",
         64: "LC", 70: "MA", 75: "CL"}
SELECTOR = {n: "GeneralUser" for n in (37, 38, 42, 44, 46, 49, 56, 70, 75)}
SELECTOR.update({n: "FluidR3" for n in (36, 41, 43, 45, 47, 48, 50, 62, 63, 64)})

# LEVEL ONE's answer (--select). A tom or conga that FluidR3 plays repitched
# is fitted at the hit's own pitch and played at FluidR3's (percussion_map).
HITS = {36: "BD0050", 37: "RS", 38: "SD7575", 41: "LT75", 43: "LT10", 45: "MT50", 47: "MT10",
        48: "HT75", 50: "HT10", 42: "CH", 44: "CH", 46: "OH75", 49: "CY7500", 56: "CB",
        62: "HC50", 63: "MC25", 64: "LC25", 70: "MA", 75: "CL"}

EDGES = np.array([0, 5, 10, 20, 35, 60, 100, 160, 250, 400, 650, 1000, 1600]) / 1000.0
TOB = 31.25 * 2 ** (np.arange(0, 28) / 3.0)          # 31 Hz - 16 kHz
FLOOR = -60.0


def hit(name):
    return E.read(os.path.join(PACK, name[:2], name + ".WAV"))


def onset(x):
    return int(np.argmax(np.abs(x) > np.abs(x).max() * 0.02))


def tf_energy(x, sr):
    """Energy per second in each (frame, third-octave band): each frame
    Hann-windowed, so a frame's edge leaks nothing to speak of."""
    x = np.asarray(x, float)
    x = x[max(0, onset(x) - int(0.001 * sr)):]
    N = 1 << 14
    lo, hi = TOB / 2 ** (1 / 6.0), TOB * 2 ** (1 / 6.0)
    out = np.full((len(EDGES) - 1, len(TOB)), 1e-20)
    for i in range(len(EDGES) - 1):
        a, b = int(EDGES[i] * sr), int(EDGES[i + 1] * sr)
        seg = x[a:b]
        if len(seg) < 16:
            continue
        # energy per second: a short frame is not quieter for being short
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), max(N, len(seg)))) ** 2 / len(seg)
        ff = np.fft.rfftfreq(max(N, len(seg)), 1.0 / sr)
        for j in range(len(TOB)):
            out[i, j] = X[(ff >= lo[j]) & (ff < hi[j])].sum() + 1e-20
    return out


def tf(x, sr):
    """dB per (frame, third-octave band) re the loudest cell."""
    db = 10 * np.log10(tf_energy(x, sr))
    return db - db.max()


def track(x, sr, fmax=1500.0, span=0.15, win=0.02):
    """The strongest partial under fmax, win-long frames every 5 ms."""
    x = np.asarray(x, float)
    x = x[onset(x):]
    fr, hop, N = int(win * sr), int(0.005 * sr), 1 << 16
    f = np.fft.rfftfreq(N, 1.0 / sr)
    band = (f > 25) & (f < fmax)
    out = []
    top = np.sqrt(np.mean(x[:fr] ** 2)) + 1e-12
    for i in range(0, int(span * sr), hop):
        seg = x[i:i + fr]
        if len(seg) < fr or np.sqrt(np.mean(seg ** 2)) < top * 10 ** (-30 / 20.0):
            break                     # ...while it sounds: under -30 dB a track reads noise
        X = np.abs(np.fft.rfft(seg * np.hanning(fr), N))
        out.append(f[band][np.argmax(X[band])])
    return np.array(out)


def settled(y, sr, fmax, short=False):
    """Where a resonator's pitch settles: its strongest partial over a long
    window once the strike's sweep is over (2-40 ms for a rim shot or a
    clave, gone by 100)."""
    y = np.asarray(y, float)
    a = onset(y)
    t0, t1 = (0.002, 0.04) if short else (0.1, 0.5)
    seg = y[a + int(t0 * sr):a + int(t1 * sr)]
    N = 1 << 18
    f = np.fft.rfftfreq(N, 1.0 / sr)
    band = (f > 25) & (f < fmax)
    return float(f[band][np.argmax(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))[band])])


def sounding(y, sr, floor=-60.0):
    """How long a hit sounds: until its 5 ms level is `floor` under its peak
    for good. A recording's hiss goes on past it, and a 25 ms clave's
    balance over a fixed 1.6 s was the hiss's -- the fit raised the click to
    match it and burst 35 dB over the 808 at the strike."""
    y = np.asarray(y, float)
    y = y[onset(y):]
    w = max(1, int(0.005 * sr))
    e = np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-12
    db = 20 * np.log10(e / e.max())
    above = np.flatnonzero(db > floor)
    return min(EDGES[-1], (above[-1] + 1) / sr if len(above) else EDGES[-1])


def balance(x, sr, span=EDGES[-1]):
    """The hit's energy in each third-octave band over the grid's frames that
    start inside its first `span` seconds, dB re its total. FROM THE FRAMES,
    each Hann-windowed: one plain FFT over the span cut the ring off where it
    still stood at -60 dB, and the cut leaked the tone across the spectrum at
    6 dB an octave -- a 'skirt' the fit chased, the 808's and ours ending at
    different levels."""
    e = tf_energy(x, sr)
    dur = np.diff(EDGES)
    keep = EDGES[:-1] < span
    tot = (e[keep] * dur[keep, None]).sum(0) + 1e-30
    return 10 * np.log10(tot / tot.sum())


def score(ours, theirs, sr, pitch=True, fmax=1500.0, win=0.02):
    a, b = tf(ours, sr), tf(theirs, sr)
    a, b = np.maximum(a, FLOOR), np.maximum(b, FLOOR)
    live = (a > FLOOR) | (b > FLOOR)
    s = float(np.sqrt(np.mean((a[live] - b[live]) ** 2)))
    # ...AND THE WHOLE HIT'S BALANCE across the bands: the cells weigh every
    # moment alike, and a kick 10-25 dB short of the 808's 80-320 Hz (its
    # punch -- what a small speaker plays) moved them by a few tenths
    # (Ben: "The kick is a little louder on fluid")
    span = sounding(theirs, sr)                # both over the 808's own sounding
    ba, bb = np.maximum(balance(ours, sr, span), FLOOR), np.maximum(balance(theirs, sr, span), FLOOR)
    lb = (ba > FLOOR) | (bb > FLOOR)
    s += float(np.sqrt(np.mean((ba[lb] - bb[lb]) ** 2)))
    if pitch:
        ta, tb = track(ours, sr, fmax, win=win), track(theirs, sr, fmax, win=win)
        n = min(len(ta), len(tb))
        if n:
            s += 2.0 * float(np.mean(np.abs(12 * np.log2(ta[:n] / tb[:n]))))
    return s


def fmax(cls):
    """The pitch track's ceiling: over the voice's tuning, under its next
    resonator (a rim shot's second sits 3.6x up)."""
    p = cls.tr808_patch
    return max(1500.0, 1.5 * p["tune_hz"]) if p["circuit"] == "resonator" else 1500.0


def win(cls):
    """The track's window: three periods of the tuning, 20 ms at least."""
    return max(0.02, 3.0 / cls.tr808_patch["tune_hz"])


def ours(note, d):
    x, sr = E.ours(note, d)
    return x, sr


# ---- level one ---------------------------------------------------------------
def select(d, notes=None):
    """Each note's closest hit to its selector set's sample -- by the same
    score, pitch left out (a repitched sample would choose by pitch alone)."""
    from gm_release import SETS
    sets = dict(SETS.items() if isinstance(SETS, dict) else SETS)
    out = {}
    for n in notes or sorted(VOICE):
        sf = [p for k, p in sets.items() if k.startswith(SELECTOR[n])][0]
        g, sr = E.theirs(sf, n, d)
        names = sorted(os.path.basename(p)[:-4] for p in os.listdir(os.path.join(PACK, VOICE[n]))
                       if p.upper().endswith(".WAV"))
        names = [m for m in names if m.startswith(VOICE[n])]
        res = sorted((score(hit(m)[0], g, sr, pitch=False), m) for m in names)
        out[n] = res[0][1]
        print("%3d %-16s %-11s -> %s  (%s)" % (n, SELECTOR[n], VOICE[n], res[0][1],
                                               "  ".join("%s %.1f" % (m, s) for s, m in res[:3])))
    return out


# ---- level two -----------------------------------------------------------------
# A knob: (path into the patch, log?, step). A path is a key, or (key, i, j)
# into a tuple of tuples (a second resonator's level, a band's decay).
KNOBS = {
    "kick": (36, "TR808KickProperties", (
        ("decay_s", True, 0.3), ("h2_db", False, 6.0), ("h3_db", False, 6.0),
        ("jump_ratio", True, 0.2), ("jump_db", False, 4.0), ("jump_ms", True, 0.4),
        ("bend_oct", False, 0.1), ("bend_ms", True, 0.4), ("tone_delay_ms", False, 2.0),
        ("jump_phase", False, 1.0), ("click_db", False, 6.0),
        ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))),
    "snare": (38, "TR808SnareProperties", (
        ("decay_s", True, 0.3), (("res", 0, 0), True, 0.05), (("res", 0, 1), False, 4.0),
        (("res", 0, 2), True, 0.3), ("jump_ratio", True, 0.2), ("jump_db", False, 4.0),
        ("noise_db", False, 4.0), ("noise_hp_hz", True, 0.4), ("noise_lp_hz", True, 0.4),
        ("noise_decay_s", True, 0.3), ("jump_ms", True, 0.4), ("jump_phase", False, 1.0), ("click_db", False, 6.0),
        ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))),
    # THE TOMS AND CONGAS: the diodes set the bend's time (the ring's) and
    # their harmonics' decays; the noise's filter and envelope time are the
    # schematic's (service notes p.9). What is left: the ring, the bend's
    # depth, the first cycle, the noise's level, h3's level.
    "lowtom": (41, "TR808TomProperties", (
        ("decay_s", True, 0.3), ("jump_ratio", True, 0.2), ("jump_db", False, 4.0),
        ("jump_ms", True, 0.4), ("bend_oct", False, 0.03), ("noise_db", False, 4.0),
        ("noise_decay_s", True, 0.2), ("h3_db", False, 6.0), ("jump_phase", False, 1.0), ("click_db", False, 6.0),
        ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))),
    "conga": (64, "TR808CongaProperties", (
        ("decay_s", True, 0.3), ("jump_ratio", True, 0.2), ("jump_db", False, 4.0),
        ("jump_ms", True, 0.4), ("bend_oct", False, 0.02), ("h3_db", False, 6.0),
        ("jump_phase", False, 1.0), ("click_db", False, 6.0),
        ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))),
    # THE RIM SHOT: two networks into the swing VCA, its output through Q63's
    # resonant high-pass (590 Hz, Q 2.9, the schematic's): the second
    # network's pitch and level, where the VCA conducts, its envelope, and
    # the step the envelope rings the high-pass with
    "rim": (37, "TR808RimShotProperties", (
        ("decay_s", True, 0.3), ("tone_decay_s", True, 0.3), (("res", 0, 0), True, 0.03),
        (("res", 0, 2), True, 0.3), ("swing_db", False, 4.0), ("swing_bias", False, 0.15),
        ("step_db", False, 6.0), ("click_db", False, 6.0), ("click_hp_hz", True, 0.4),
        ("click_dbs", True, 0.4))),
    "claves": (75, "TR808ClavesProperties", (
        ("decay_s", True, 0.3), ("h2_db", False, 6.0), ("h3_db", False, 6.0),
        ("jump_ratio", True, 0.2), ("jump_db", False, 4.0), ("click_db", False, 6.0),
        ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))),
    # THE MARACAS: Q68's filter is the schematic's (a 1 kHz RC and a 10.6 kHz
    # Sallen-Key, Q 2.3); the gate's swell, hold and length are fitted
    "maracas": (70, "TR808MaracasProperties", (
        ("noise_db", False, 4.0), ("noise_rise_ms", True, 0.4), ("noise_len_ms", True, 0.3),
        ("noise_decay_s", True, 0.4))),
    "cowbell": (56, "TR808CowbellProperties", (
        ("osc_duty", False, 0.05), (("bands", 0, 0), True, 0.2), (("bands", 0, 1), True, 0.3),
        (("bands", 0, 3), True, 0.3), ("after_db", False, 3.0), ("after_s", True, 0.3),
        ("attack_ms", True, 0.5))),
    "closedhat": (42, "TR808ClosedHatProperties", (
        ("osc_duty", False, 0.05), (("bands", 0, 0), True, 0.2), (("bands", 0, 1), True, 0.3),
        (("bands", 0, 3), True, 0.3), ("hp_hz", True, 0.2), ("hp_q", True, 0.3),
        ("noise_db", False, 4.0), ("noise_decay_s", True, 0.3))),
    "openhat": (46, "TR808OpenHatProperties", (
        (("bands", 0, 0), True, 0.2), (("bands", 0, 1), True, 0.3), (("bands", 0, 3), True, 0.3),
        ("hp_hz", True, 0.2), ("hp_q", True, 0.3), ("noise_db", False, 4.0),
        ("noise_decay_s", True, 0.3))),
    # THE CYMBAL: the band-passes' centres are the circuit's (Werner's cymbal
    # paper: ~3440 and ~7100 Hz, the high band split again, its top through a
    # high-pass resonant near 10.5 kHz); fitted free, the low band had wandered
    # up to 7.7 kHz. Their widths, levels (TONE) and VCAs' decays are fitted.
    "cymbal": (49, "TR808CymbalProperties", (
        ("osc_duty", False, 0.05),
        (("bands", 0, 1), True, 0.3), (("bands", 0, 2), False, 4.0), (("bands", 0, 3), True, 0.3),
        (("bands", 1, 1), True, 0.3), (("bands", 1, 2), False, 4.0), (("bands", 1, 3), True, 0.3),
        (("bands", 2, 1), True, 0.3), (("bands", 2, 2), False, 4.0), (("bands", 2, 3), True, 0.3),
        ("hp_hz", True, 0.3), ("noise_db", False, 4.0), ("noise_decay_s", True, 0.3))),
}
# THE OTHER TOMS AND CONGAS are each their own circuit with their own components, so
# each its own knobs -- over the low one's patch, its starting point
_TOM = ("decay_s", "jump_ratio", "jump_db", "jump_ms", "bend_oct", "noise_db",
        "noise_decay_s", "h3_db", "jump_phase", "click_db", "click_dbs", "click_tilt")
_CONGA = ("decay_s", "jump_ratio", "jump_db", "jump_ms", "bend_oct", "h3_db", "jump_phase",
          "click_db", "click_dbs", "click_tilt")
SHARED = {"midtom": (45, "TR808MidTomProperties", _TOM),
          "hitom": (48, "TR808HiTomProperties", _TOM),
          "midconga": (63, "TR808MidCongaProperties", _CONGA),
          "hiconga": (62, "TR808HiCongaProperties", _CONGA)}


def get(patch, path):
    if isinstance(path, tuple):
        k, i, j = path
        return patch[k][i][j]
    return patch[path]


def put(own, full, path, v):
    """Set a knob in a class's OWN patch (a tuple path copies the whole
    tuple from the full panel first)."""
    if isinstance(path, tuple):
        k, i, j = path
        rows = [list(r) for r in full[k]]
        rows[i][j] = v
        own[k] = tuple(tuple(r) for r in rows)
        full[k] = own[k]
    else:
        own[path] = v
        full[path] = v


def fit(voice, d, maxfev=400):
    from scipy.optimize import minimize
    import tonelib as T
    import percussion_map as P
    if voice in SHARED:
        note, cls_name, names = SHARED[voice]
        knobs = tuple(k for k in KNOBS["lowtom" if "tom" in voice else "conga"][2] if k[0] in names)
    else:
        note, cls_name, knobs = KNOBS[voice]
    cls = getattr(T, cls_name)
    y, sr = hit(HITS[note])
    # the hit's own pitch: a resonator is tuned where its track settles
    nm, cl, fq = P.KITS[KIT][note]
    if cls.tr808_patch["circuit"] == "resonator" and cls.tr808_patch["tone_db"] > -90:
        fq = settled(y, sr, fmax(cls), sounding(y, sr) < 0.15)     # by the hit, not the patch
        cls.tr808 = dict(cls.tr808, tune_hz=round(fq, 1))
        T.tr808_refresh(cls)
    P.KITS[KIT][note] = (nm, cls, cls.tr808_base_hz)
    P._RING_CLASSES.clear()
    pitch = cls.tr808_patch["circuit"] == "resonator" and cls.tr808_patch["tone_db"] > -90
    full = dict(cls.tr808_patch)
    own = dict(cls.tr808)
    x0 = np.array([np.log(get(full, k)) if lg else get(full, k) for k, lg, _ in knobs])
    step = np.array([s for _, _, s in knobs])

    def setx(x):
        for (k, lg, _), v in zip(knobs, x):
            put(own, full, k, float(np.exp(v)) if lg else float(v))
        cls.tr808 = dict(own)
        T.tr808_refresh(cls)
        P._RING_CLASSES.clear()
    best = [1e9]

    def f(x):
        setx(x)
        s = score(ours(note, d)[0], y, sr, pitch, fmax(cls), win(cls))
        if s < best[0]:
            best[0] = s
            print("   %.2f  %s" % (s, " ".join("%.3f" % v for v in x)), flush=True)
        return s
    s0 = f(x0)
    r = minimize(f, x0, method="Nelder-Mead",
                 options=dict(initial_simplex=np.vstack([x0] + [x0 + np.eye(len(x0))[i] * step[i]
                                                                 for i in range(len(x0))]),
                              maxfev=maxfev, xatol=0.005, fatol=0.02))
    setx(r.x)
    print("FITTED %s to %s: score %.2f -> %.2f" % (voice, HITS[note], s0, r.fun))
    fit.done.append((cls_name, dict(cls.tr808)))
    print("   tr808 = %s" % {k: (round(v, 4) if isinstance(v, float) else
                                 tuple(tuple(round(float(a), 4) for a in row) for row in v)
                                 if isinstance(v, tuple) and v and isinstance(v[0], tuple) else v)
                             for k, v in cls.tr808.items()})
    return cls.tr808


def fmt(v):
    if isinstance(v, float):
        return repr(round(v, 4))
    if isinstance(v, tuple):
        return "(" + ", ".join(fmt(a) for a in v) + ("," if len(v) == 1 else "") + ")"
    return repr(v)


def write(cls_name, patch):
    """Rewrite the class's `tr808 = {...}` in tonelib.py with its fitted patch."""
    path = os.path.join(HERE, "tonelib.py")
    s = open(path).read()
    i = s.index("class %s(" % cls_name)
    j = s.index("    tr808 = {", i)
    k, depth = j + len("    tr808 = "), 0
    while True:
        depth += {"{": 1, "}": -1}.get(s[k], 0)
        k += 1
        if depth == 0:
            break
    items = ['"%s": %s' % (key, fmt(v)) for key, v in patch.items()]
    lines, cur = [], "    tr808 = {"
    for it in items:
        if len(cur) + len(it) + 2 > 92 and cur.strip() != "tr808 = {":
            lines.append(cur.rstrip())
            cur = "             "
        cur += it + ", "
    lines.append(cur[:-2] + "}")
    s = s[:j] + "\n".join(lines) + s[k:]
    open(path, "w").write(s)
    print("   wrote %s" % cls_name)


fit.done = []


def report(d, notes=None):
    tot = []
    for n in notes or sorted(VOICE):
        y, sr = hit(HITS[n])
        x, _ = ours(n, d)
        import tonelib as T  # noqa: F401
        import percussion_map as P
        cls = P.KITS[KIT][n][1]
        pitch = cls.tr808_patch["circuit"] == "resonator" and cls.tr808_patch["tone_db"] > -90
        if n in (43, 47, 50):        # played repitched: its picture only
            pitch = False
        s = score(x, y, sr, pitch, fmax(cls), win(cls))
        tot.append(s)
        print("%3d %-16s %-7s score %5.1f" % (n, P.KITS[KIT][n][0], HITS[n], s))
    print("mean %.1f" % np.mean(tot))


def write_wavs(out, d, tag="808"):
    from scipy.io import wavfile
    os.makedirs(out, exist_ok=True)
    for n in sorted(VOICE):
        y, sr = hit(HITS[n])
        x, _ = ours(n, d)
        for name, z in ((tag, y), ("ours", x)):
            z = np.asarray(z, float)
            z = z[max(0, onset(z) - 200):][:int(1.6 * sr)]
            z = 0.5 * z / (np.abs(z).max() + 1e-12)
            wavfile.write(os.path.join(out, "%d_%s.wav" % (n, name)), sr, (z * 32767).astype(np.int16))


def osc(d):
    """The six oscillators: the bases whose harmonics explain the cymbal's
    strongest peaks (any harmonic: the oscillators are not 50% duty)."""
    from scipy.signal import find_peaks
    y, sr = hit("CY5010")
    seg = y[onset(y) + int(0.05 * sr):onset(y) + int(1.5 * sr)]
    N = 1 << 20
    X = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) + 1e-9)
    f = np.fft.rfftfreq(N, 1.0 / sr)
    X -= X.max()
    k, _ = find_peaks(X, prominence=10, height=-20, distance=int(8 / (sr / N)))
    left = [(f[i], X[i]) for i in k if 100 < f[i] < 18000]
    for _ in range(6):
        best = None
        for b in np.arange(300, 900, 0.1):
            ex = [(fp, round(fp / b)) for fp, a in left
                  if round(fp / b) >= 1 and abs(fp - round(fp / b) * b) < max(1.5, 0.0004 * fp)]
            w = sum(10 ** (a / 20) for fp, a in left if any(fp == e[0] for e in ex))
            if best is None or w > best[0]:
                best = (w, ex)
        ex = best[1]
        b = float(np.mean([fp / h for fp, h in ex]))
        print("oscillator %.1f Hz: %d peaks, harmonics %s" % (b, len(ex), sorted(h for _, h in ex)))
        left = [p for p in left if p[0] not in [e[0] for e in ex]]


def main(argv):
    with tempfile.TemporaryDirectory() as d:
        args = dict(a.split("=", 1) if "=" in a else (a, "") for a in argv)
        if "--select" in args:
            select(d)
        elif "--osc" in args:
            osc(d)
        elif "--fit" in args:
            for v in args["--fit"].split(","):
                fit(v, d, int(args.get("--maxfev", 400)))
            report(d)
            if "--write" in args:
                for cls_name, patch in fit.done:
                    write(cls_name, patch)
        elif "--wav" in args:
            write_wavs(args["--wav"], d)
        else:
            report(d)


if __name__ == "__main__":
    main(sys.argv[1:])
