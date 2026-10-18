#!/usr/bin/env python3
"""The harmonium's registers (GM 20) fitted to the Debain's, and written into
their classes in tonelib.py.

    python3 -I examples/debain_registers.py [--stop=NAME ...] [--dry] [--hold-level]
    python3 -I examples/debain_registers.py --celeste [--dry]
    python3 -I examples/debain_registers.py --tremolo [--dry]
    python3 -I examples/debain_registers.py --survey
    python3 -I examples/debain_registers.py --ab=OUT.wav --stop=NAME

THE REFERENCE (sources.md "Organs and free reeds"): Jean-Pierre Silvestre's
Hauptwerk set of the Debain harmonium (about 1895) of the Dominican sisters'
chapel at Saint-Denis, La Reunion -- every register recorded alone on every
key of its half, bass C2-E4 (36-64) and treble F4-C7 (65-96), 48 kHz 24-bit
stereo, retuned equal at A440, with about 2 s of the chapel. No licence is
stated: measured here, never redistributed.

THE SET'S OWN BALANCE. Its organ definition plays every rank at one level (no
rank or pipe gain differs), and its files are not normalised -- peaks run 3 to
11 dB under full scale, and the Sourdine, the muted stop, sits 10 dB under the
rest -- so the recorded levels are the instrument's.

THE TAKES ARE COLOURED, AND EVERY REGISTER ALIKE. Against our foundation
(fitted to donyaquick's harmonium, rated 4) the Debain's is 20-40 dB darker
above 2 kHz, its bass fundamentals fall away under ~100 Hz (C2's 40 dB under
its h2), and single harmonics drop into holes 128 dB deep -- under the noise
between them, which no room does: the samples were denoised. Fitted
absolutely, its Hautbois would come out darker than our Flute. But the
registers share one case, one chapel, one microphone and one process, so a
register's DIFFERENCE from the foundation on the same key is free of all of
it. So each target is the Debain register's ladder, corrected by the
colouring its foundation shows against ours (COLOURING below):

    target(k, f) = rec(k, f) + ours_fdn(k, f) - rec_fdn(k, f)

key by key and harmonic by harmonic (dB re each take's harmonic power): an
8''s at the foundation's own frequencies, a 16''s odd harmonics between
them. What is left is the register's own difference from the foundation,
on ours. The denoiser's holes (a harmonic 25 dB under both neighbours) are
dropped and the keys' median fills them.

AND EACH TAKE ONLY OVER ITS LIVE BAND. The samples were cut, each at its own
frequency (1.1 to 15 kHz -- the Cor anglais at C3 has its h12 16 dB down at
1.6 kHz and nothing at 2 kHz, 74 dB lower), and their fundamentals fall away
under 100 Hz. So a take counts from 100 Hz to the first harmonic past which
none comes within 40 dB of its strongest (live()); past either end the target
is our foundation's ladder kept at the register's distance from it at the
band's edge.

Per register, the organ's recorded-rank build (examples/pitea_newranks.py):

  1  SERIES  h1-h32 as measured tables at three anchor pitches across its
             half (pitea_fit.fit_tables' method), three passes of target -
             ours, both measured alike (1-3 s, dB re the take's harmonic
             power: a bass h1 near the noise must not set the ladder's zero)
  2  SPEECH  speech_cycles, speech_harmonic_exp (a free reed's upper
             harmonics come LAST: negative) and the attack floor, against the
             attack's courses (pitea_speech.courses)
  3  LEVEL   its steady power against the Debain's foundation on the same
             keys -- Cor anglais in the bass, Flute in the treble -- and ours
             put the same distance from our foundation
  4  WRITE   the class's body in tonelib.py after its docstring (--dry prints)

--celeste  THE VOIX CELESTE'S DETUNE, key by key: each of its harmonics' level
           swings at m times one rate, so the stop is two rows apart by that
           rate (the median of h1-h6's swing over m), in cents at the rank's
           pitch -- written as the stop's two ratios per key
           (ReedOrganFreeProperties.mixture_compositions)
--tremolo  THE TREMOLO'S RATE AND DEPTH, from the Debain's Tremolo 16 (its
           treble 16' row with the tremolo on): the level's swing at its rate,
           h1-h4, and ours on the Musette (the row it is: its ladder within
           3.8 dB, the Clarinette's 27 away) with the stop drawn, its depth
           scaled until it reads the same
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)
import pitea_fit as P  # noqa: E402  (sets TUNING_REFLECT=0 before blockrender)
import pitea_speech as S  # noqa: E402
import blockrender as B  # noqa: E402
import tonelib as T  # noqa: E402

DEBAIN = os.path.expanduser("~/Documents/refs/harmonium_debain_jps/x/OrganInstallationPackages/"
                            "002601/HarmoniumDebainOriginal")
FOLDER = {
    "cor anglais 1": "1_bas_cor_anglais_8", "flute 1": "1_haut_flute_8",
    "bourdon 2": "2_bas_bourdon_16", "clarinette 2": "2_haut_clarinette_16",
    "clairon 3": "3_bas_clairon_4", "fifre 3": "3_haut_fifre_4",
    "basson 4": "4_bas_basson_8", "hautbois 4": "4_haut_hautbois_8",
    "violoncelle": "5_bas_V_violoncelle_8", "celeste": "5_haut_C_voix_celeste_16",
    "sourdine": "6_bas_S_sourdine_8", "musette": "6_haut_M_musette_16",
    "tremolo": "7_haut_T_tremolo_16",
}
FIT = ("bourdon 2", "clarinette 2", "basson 4", "hautbois 4", "celeste",
       "violoncelle", "sourdine", "musette")
# THE SET'S BROKEN KEYS: the Flute's top six and the Fifre's top thirteen are
# 12-18 dB (Flute) or 3-6 dB (Fifre, cut to 3.2 s) under their neighbours
BROKEN = {"flute 1": range(91, 97), "fifre 3": range(84, 97)}
HOST = T.ReedOrganFreeProperties
BASS_EDGES = ((36, 45), (46, 55), (56, 64))
TREBLE_EDGES = ((65, 75), (76, 86), (87, 96))
LEVEL_KEYS = {"bass": (41, 48, 55, 60), "treble": (67, 72, 79, 84)}
FOUNDATION = {"bass": "cor anglais 1", "treble": "flute 1"}
SPEECH_KEYS = {"bass": (48, 55, 60, 64), "treble": (67, 74, 81, 88)}
SPEECH_T = 0.3


def row(stop):
    return next(r for r in HOST.stop_ranks if r[0] == stop)


def half(stop):
    if stop == "tremolo":                  # the Debain's Tremolo 16, a treble row
        return "treble"
    return "bass" if row(stop)[6][0] < T.HARMONIUM_SPLIT else "treble"


def ratio(stop):
    """The stop's footage against its key: a two-row stop's lower row."""
    if stop == "tremolo":
        return 0.5
    r = row(stop)[1]
    return min(r) if isinstance(r, (list, tuple)) else r


def rank_class(stop):
    return row(stop)[3] or HOST


def sample(stop, key):
    """The Debain's file for STOP at KEY, or None (outside its half, broken)."""
    if key in BROKEN.get(stop, ()):
        return None
    p = glob.glob(os.path.join(DEBAIN, FOLDER[stop], "%03d-*.wav" % key))
    return p[0] if p else None


def keys(stop):
    lo, hi = (36, 64) if half(stop) == "bass" else (65, 96)
    return [k for k in range(lo, hi + 1) if sample(stop, k)]


def onset_trim(x):
    a = int(np.flatnonzero(np.abs(x[:, 0]) > np.abs(x[:, 0]).max() * 0.01)[0])
    return x[a:]


def recorded(stop, key):
    x, sr = P.read(sample(stop, key))
    return onset_trim(x), sr


def render(stop, key, secs=3.5, extra=()):
    """The stop drawn alone (with EXTRA, e.g. the tremolo) on GM 20, key held
    SECS, from its onset."""
    import mido
    names = [r[0] for r in HOST.stop_ranks]
    keep = HOST.default_stops
    HOST.default_stops = sum(1 << names.index(s) for s in (stop,) + tuple(extra))
    try:
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("program_change", channel=0, program=20, time=0))
        t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
        L, R = B.render(m)[:2]
    finally:
        HOST.default_stops = keep
    x = np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)
    return onset_trim(x), B.SR


def pitch(stop, key):
    return 440.0 * 2 ** ((key - 69) / 12.0) * ratio(stop)


# ---- 1  the series ------------------------------------------------------------

def harmonics(x, sr, f0):
    """Each harmonic's power over the steady part (1-3 s, the channels'
    spectra averaged as powers: pitea_fit.spectrum), dB re the first NH's
    total -- NaN past 13 kHz -- and the fundamental found."""
    Pw, f = P.spectrum(x, sr)
    b = (f > f0 / 1.04) & (f < f0 * 1.04)
    f0 = f[b][np.argmax(Pw[b])]
    h = np.full(P.NH, np.nan)
    for m in range(1, P.NH + 1):
        if m * f0 >= min(13000.0, 0.45 * sr):
            break
        w = (f > m * f0 * 0.985) & (f < m * f0 * 1.015)
        h[m - 1] = Pw[w].max()
    return 10 * np.log10(np.maximum(h, 1e-30) / np.nansum(h)), f0


LIVE_LO = 100.0          # under it the takes' fundamentals fall away (C2's 40 dB)
LIVE_SPAN = 40.0         # the live band ends where nothing past rises within this of the top


def live(r, f0):
    """The harmonics a take really carries: from LIVE_LO up to the first
    harmonic past which none rises within LIVE_SPAN dB of the strongest --
    the samples were cut, each at its own frequency (1.1 to 15 kHz), some
    harmonics 16 dB down gone 74 dB within a third of an octave."""
    hz = f0 * np.arange(1, len(r) + 1)
    ok = np.isfinite(r)
    top = np.nanmax(r)
    above = np.flatnonzero(ok & (r > top - LIVE_SPAN))
    end = above[-1] if len(above) else -1
    return ok & (hz >= LIVE_LO) & (np.arange(len(r)) <= end)


_FDN = {}


def ours_fdn(side, k):
    """Our foundation's ladder at key K (it does not change in a fit)."""
    if (side, k) not in _FDN:
        fdn = FOUNDATION[side]
        _FDN[(side, k)] = harmonics(*render(fdn, k), pitch(fdn, k))
    return _FDN[(side, k)]


def holes(r):
    """A harmonic more than 25 dB under both its neighbours is the
    denoiser's, not the reed's."""
    out = np.zeros(len(r), bool)
    for m in range(1, len(r) - 1):
        if np.isfinite(r[m - 1:m + 2]).all() and r[m] < min(r[m - 1], r[m + 1]) - 25.0:
            out[m] = True
    return out


def colouring(side, k):
    """D at key K: our foundation's harmonics less the Debain's, harmonic by
    harmonic over its take's live band (holes out) -- (Hz, dB) points."""
    fdn = FOUNDATION[side]
    if not sample(fdn, k):
        return None
    r, fr = harmonics(*recorded(fdn, k), pitch(fdn, k))
    o, _ = ours_fdn(side, k)
    ok = live(r, fr) & ~holes(r) & np.isfinite(o)
    if ok.sum() < 3:
        return None
    hz = fr * np.arange(1, P.NH + 1)
    d = (o - r)[ok]
    # ...a hole the test missed (at the band's edge, beside a NaN) would
    # spike D: each point held within 15 dB of its three-point median
    sm = np.array([np.median(d[max(0, i - 1):i + 2]) for i in range(len(d))])
    return hz[ok], np.clip(d, sm - 15.0, sm + 15.0)


def corrected(stop, k):
    """The target at key K: over the take's live band its ladder plus D, our
    foundation less the Debain's at the same key -- at the same frequencies
    for an 8', between them (log frequency) for a 16''s odd harmonics -- so
    what is left is the register's own difference from the foundation;
    past either end, our foundation's ladder at those frequencies, kept the
    register's distance from it at the band's nearest three harmonics. dB re
    the harmonic power; NaN where the key's foundation take gives no D."""
    side = half(stop)
    f0 = pitch(stop, k)
    D = colouring(side, k)
    if D is None:
        return np.full(P.NH, np.nan)
    r, fr = harmonics(*recorded(stop, k), f0)
    hz = fr * np.arange(1, P.NH + 1)
    lv = live(r, fr)
    t = r + np.interp(np.log(hz), np.log(D[0]), D[1])
    o, fo = ours_fdn(side, k)
    ofin = np.isfinite(o)
    oh = fo * np.arange(1, P.NH + 1)
    base = np.interp(np.log(hz), np.log(oh[ofin]), o[ofin])
    idx = np.flatnonzero(lv)
    if len(idx) < 2:
        return np.full(P.NH, np.nan)
    lo, hi = idx[:3], idx[-3:]
    d_lo = np.median(t[lo] - base[lo])
    d_hi = np.median(t[hi] - base[hi])
    out = np.where(lv, t, np.nan)
    below = np.arange(P.NH) < idx[0]
    above = (np.arange(P.NH) > idx[-1]) & (hz < min(13000.0, 0.45 * B.SR))
    out[below] = base[below] + d_lo
    out[above] = base[above] + d_hi
    # a hole inside the band (the denoiser's) is no measure: the median of
    # the keys fills it
    out[holes(r) & lv] = np.nan
    return norm(out)


def norm(l):
    """A ladder's zero at its median over h1-h8: one spike (a key's stray
    harmonic) must not move the whole ladder, as a total-power zero does."""
    return l - np.nanmedian(l[:8])


def rms_top(d, ref, span=50.0):
    """rms of d over the harmonics within SPAN dB of REF's strongest -- the
    ones that are heard -- its median taken out (the level is step 3's)."""
    ok = np.isfinite(d) & np.isfinite(ref) & (ref > np.nanmax(ref) - span)
    e = d[ok] - np.median(d[ok])
    return float(np.sqrt(np.mean(e ** 2)))


def fit_tables(stop, passes=3, step=2):
    """h1-h32 at three anchors across the stop's half, each the median target
    ladder of its keys at their geometric-mean pitch (the rank's), blended
    between (SynthProperties.mode_gains_at); each pass adds target - ours,
    the table held at a strongest harmonic of 1."""
    cls = rank_class(stop)
    cls.bore_corner_hz = 0.0
    cls.rank_is_pipe = True
    side = half(stop)
    edges = BASS_EDGES if side == "bass" else TREBLE_EDGES
    groups = [[] for _ in edges]
    for key in keys(stop)[::step]:
        gi = next(i for i, (a0, a1) in enumerate(edges) if a0 <= key <= a1)
        groups[gi].append(key)
    groups = [g for g in groups if g]
    R = [np.nanmedian([corrected(stop, k) for k in g], 0) for g in groups]
    anchors = [float(np.exp(np.mean([np.log(pitch(stop, k)) for k in g]))) for g in groups]
    tabs = []
    for r in R:
        t = np.where(np.isfinite(r), r, np.nanmin(r))
        t = 10 ** ((t - t.max()) / 20.0)
        tabs.append([float(v) for v in t])
    cls.mode_gains_low = None
    cls.max_harmonic = P.NH
    for n in range(passes + 1):
        cls.mode_gains_points = tuple((f, tuple(t)) for f, t in zip(anchors, tabs))
        cls.mode_gains = tuple(tabs[-1])
        msg = []
        for gi, g in enumerate(groups):
            O = np.nanmedian([norm(harmonics(*render(stop, k), pitch(stop, k))[0]) for k in g], 0)
            d = R[gi] - O
            d = d - np.nanmedian(d[:8])
            msg.append("%.2f" % rms_top(d, R[gi]))
            if n < passes:
                for m in range(P.NH):
                    if np.isfinite(d[m]):
                        tabs[gi][m] *= 10 ** (d[m] / 20.0)
                top = max(tabs[gi])
                tabs[gi] = [v / top for v in tabs[gi]]
        print("  %s pass %d: target - ours rms, harmonics within 50 dB, low/middle/high: %s dB"
              % (stop, n, " / ".join(msg)), flush=True)


# ---- 2  the speech --------------------------------------------------------------

def fit_speech(stop, rounds=2):
    """speech_cycles, speech_harmonic_exp and attack_time by coordinate search
    against the attack's courses (fundamental, h2-h4, h5 up; dB re steady,
    clipped -30..+10) over the first SPEECH_T s (pitea_stops.fit_speech)."""
    cls = rank_class(stop)
    rec = {}
    for key in SPEECH_KEYS[half(stop)]:
        if not sample(stop, key):
            continue
        f0 = pitch(stop, key)
        x, sr = P.read(sample(stop, key))
        a = S.onset(x)
        rec[key] = (f0, np.clip(S.courses(x, sr, f0, a, SPEECH_T, ref=S.steady(x, sr, f0, a))[:, :3], -30, 10))

    def cost():
        e = []
        for key, (f0, rc) in rec.items():
            y, s2 = render(stop, key, 2.6)
            oc = np.clip(S.courses(y, s2, f0, 0, SPEECH_T, ref=S.steady(y, s2, f0, 0))[:, :3], -30, 10)
            n = min(len(rc), len(oc))
            e.append(np.mean((rc[:n] - oc[:n]) ** 2))
        return float(np.sqrt(np.mean(e)))

    grids = {
        "speech_cycles": (0.0, 1.5, 3.0, 6.0, 10.0, 16.0, 24.0, 36.0),
        "speech_harmonic_exp": (-1.2, -0.6, -0.3, 0.0, 0.3, 0.6),
        "attack_time": (0.004, 0.008, 0.012, 0.02, 0.035, 0.06, 0.1),
    }
    best = cost()
    print("  %s speech, start: %.2f dB  (%s)" % (stop, best, "  ".join(
        "%s=%s" % (k, getattr(cls, k)) for k in grids)), flush=True)
    for _ in range(rounds):
        for k, grid in grids.items():
            keep = getattr(cls, k)
            for v in grid:
                if v == keep:
                    continue
                setattr(cls, k, v)
                c = cost()
                if c < best - 0.05:
                    best, keep = c, v
            setattr(cls, k, keep)
        print("  %s speech: %.2f dB  (%s)" % (stop, best, "  ".join(
            "%s=%s" % (k, getattr(cls, k)) for k in grids)), flush=True)
    return best


# ---- 3  the level -----------------------------------------------------------------

def steady_db(x, sr):
    s = x[int(1.0 * sr):int(3.0 * sr)]
    return 10 * np.log10(np.mean(s ** 2))


def rec_level(stop, side):
    return 10 * np.log10(np.mean([10 ** (steady_db(*recorded(stop, k)) / 10)
                                  for k in LEVEL_KEYS[side] if sample(stop, k)]))


def ours_level(stop, side):
    return 10 * np.log10(np.mean([10 ** (steady_db(*render(stop, k)) / 10)
                                  for k in LEVEL_KEYS[side]]))


def fit_level(stop, hold=None):
    """The Debain's balance -- or, with HOLD (dB re our foundation, measured
    before the fit), ours kept where it was: the 4''s level is donyaquick's
    take's, measured with its 8' (--hold-level)."""
    side = half(stop)
    ref = FOUNDATION[side]
    rec_d = rec_level(stop, side) - rec_level(ref, side)
    ref_ours = ours_level(ref, side)
    cls = rank_class(stop)
    if hold is not None:
        for _ in range(2):
            cls.initial_gain *= 10 ** (((ref_ours + hold) - ours_level(stop, side)) / 20.0)
        print("  level: HELD at %+.1f dB re our %s (the Debain's %+.1f)" % (
            ours_level(stop, side) - ref_ours, ref, rec_d), flush=True)
        return None
    for _ in range(2):
        d = (ref_ours + rec_d) - ours_level(stop, side)
        cls.initial_gain *= 10 ** (d / 20.0)
    print("  level: the Debain's %+.1f dB re its %s; ours now %+.1f" % (
        rec_d, ref, ours_level(stop, side) - ref_ours), flush=True)
    return rec_d


# ---- 4  the write -------------------------------------------------------------------

def body(stop, rec_d):
    cls = rank_class(stop)
    lines = ["    mode_gains_points = ("]
    for f, t in cls.mode_gains_points:
        lines.append("        (%.1f, (%s))," % (f, ", ".join("%.5f" % v for v in t)))
    lines += ["    )",
              "    mode_gains = mode_gains_points[-1][1]      # (series_volume's switch; the top's)",
              "    mode_gains_low = None",
              "    max_harmonic = 32",
              "    bore_corner_hz = 0.0",
              "    # its own speech and decay, not the host's (blockrender's rank_is_pipe)",
              "    rank_is_pipe = True",
              ("    # LEVEL: the Debain's own balance -- %+.1f dB re its %s on the same" % (
                  rec_d, FOUNDATION[half(stop)].split()[0].replace("cor", "Cor anglais").replace("flute", "Flute"))
               if rec_d is not None else
               "    # LEVEL: HELD where donyaquick's 8'+4' take set it (debain_registers.py"),
              ("    # keys (debain_registers.py) -- held against ours" if rec_d is not None else
               "    # --hold-level): the Debain fitted its series and speech only"),
              "    initial_gain = %.6g" % cls.initial_gain,
              "    # ITS SPEECH, fitted on the Debain's attack (debain_registers.py)",
              "    speech_cycles = %r" % cls.speech_cycles,
              "    speech_harmonic_exp = %r" % cls.speech_harmonic_exp,
              "    attack_time = %r" % cls.attack_time]
    return "\n".join(lines) + "\n"


def write_class(cls, text):
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    m = re.search(r"\nclass %s\(([A-Za-z]+)\):\n    \"\"\"(.*?)\"\"\"\n" % cls.__name__, s, re.S)
    assert m, cls.__name__
    end = m.end()
    nxt = re.compile(r"\n(class |# THE VOIX CELESTE|# ---- )").search(s, end)
    s = s[:end] + text + "\n" + s[nxt.start():]
    open(p, "w").write(s)


def write_block(name, text):
    """Replace (or add, before the stop_ranks) a module-level block that
    starts with the line '# <name>' and ends at a blank line."""
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    m = re.search(r"\n# %s\n.*?\n\n" % re.escape(name), s, re.S)
    if m:
        s = s[:m.start()] + "\n" + text + "\n" + s[m.end():]
    else:
        i = s.index("\n# (name, footage ratio, gain, voice, dyn, pipe, key range).")
        s = s[:i] + "\n" + text + s[i:]
    open(p, "w").write(s)


# ---- the celeste and the tremolo -----------------------------------------------

def held_part(x, sr):
    """The sustained span of a take: from 0.6 s after it speaks to where it
    falls 6 dB under its first steady second (the key's release)."""
    m = x.mean(1) if x.ndim == 2 else x
    hop = sr // 100
    # over 0.3 s: a tremolo's or a celeste's own dips are not the release
    e = np.sqrt(np.convolve(m ** 2, np.ones(30 * hop) / (30 * hop), "same")[::hop]) + 1e-12
    a = int(np.flatnonzero(e > e.max() * 0.1)[0]) + 60
    med = np.median(e[a:a + 100])
    t = np.flatnonzero(e[a:] < 0.5 * med)
    b = a + int(t[0]) if len(t) else len(e)
    return m[a * hop:max(a * hop, b * hop - sr // 10)]


def band_env(s, sr, f, bw):
    from scipy.signal import butter, sosfiltfilt, hilbert
    sos = butter(4, [max(20.0, f - bw), f + bw], "bandpass", fs=sr, output="sos")
    return np.abs(hilbert(sosfiltfilt(sos, s)))


def swing(e, sr, lo=0.5, hi=25.0, at=None):
    """(rate Hz, depth m) of a level's periodic swing, e/mean = 1 + m cos: the
    strongest line between lo and hi (or AT), its amplitude by least squares."""
    d = 200
    e = e[::sr // d]
    e = e[d // 4:-d // 4] if len(e) > d else e
    e = e / np.mean(e) - 1.0
    N = 1 << 16
    E = np.abs(np.fft.rfft(e * np.hanning(len(e)), N))
    fr = np.fft.rfftfreq(N, 1.0 / d)
    if at is None:
        sel = (fr > lo) & (fr < hi)
        at = fr[sel][np.argmax(E[sel])]
    t = np.arange(len(e)) / d
    M = np.stack([np.cos(2 * np.pi * at * t), np.sin(2 * np.pi * at * t)], 1)
    c = np.linalg.lstsq(M, e, rcond=None)[0]
    return float(at), float(np.hypot(*c))


def celeste_cents():
    """Per key, the two rows' distance in cents at the rank's pitch: the
    median over h1-h6 of (each harmonic's swing rate) / m."""
    out = {}
    for key in keys("celeste"):
        x, sr = recorded("celeste", key)
        s = held_part(x, sr)
        f = pitch("celeste", key)
        if len(s) < 2 * sr:
            continue
        r = []
        for m in range(1, 7):
            if m * f > 6000:
                break
            rate, dep = swing(band_env(s, sr, m * f, 0.35 * f), sr, lo=0.3 * m, hi=min(40.0, 12.0 * m))
            r.append(rate / m)
        r = np.array(r)
        med = np.median(r)
        ok = np.abs(r - med) < 0.2 * med
        if ok.sum() >= 3:
            dhz = float(np.mean(r[ok]))
            out[key] = 1200 * np.log2(1 + dhz / f)
            print("  key %d  %6.1f Hz  rows %.2f Hz apart  %5.1f cents  (h1-h%d: %s)" % (
                key, f, dhz, out[key], len(r), " ".join("%.2f" % v for v in r)), flush=True)
        else:
            print("  key %d  no consistent rate (%s)" % (key, " ".join("%.2f" % v for v in r)), flush=True)
    return out


def fit_celeste(dry):
    c = celeste_cents()
    ks = np.array(sorted(c))
    cs = np.array([c[k] for k in ks])
    oct_ = (ks - 69) / 12.0
    slope, at_a4 = np.polyfit(oct_, cs, 1)
    resid = cs - (at_a4 + slope * oct_)
    print("  line: %.1f cents at A4, %+.1f an octave; per key %.1f cents rms about it" % (
        at_a4, slope, np.sqrt(np.mean(resid ** 2))), flush=True)
    # each key its own (a hand-tuned pair); a key the measure missed, the line
    full = {k: (c[k] if k in c else at_a4 + slope * (k - 69) / 12.0) for k in range(65, 97)}
    med = float(np.median(list(c.values())))
    filled = [k for k in sorted(full) if k not in c]
    text = ("# THE VOIX CELESTE'S TWO ROWS, key by key (debain_registers.py --celeste)\n"
            "# (keys %s: no steady rate read -- the line's)\n" % ", ".join(map(str, filled)) +
            "HARMONIUM_CELESTE_BY_KEY = {\n" +
            "".join("    %d: %.1f,%s" % (k, full[k], "\n" if i % 8 == 7 else "")
                    for i, k in enumerate(sorted(full))).rstrip() + "\n}\n")
    print(text)
    print("  median %.1f cents" % med)
    if not dry:
        write_block("THE VOIX CELESTE'S TWO ROWS, key by key (debain_registers.py --celeste)", text)
    return full, med


def tremolo_voice():
    """Which treble 16' the Debain's Tremolo row is: its median ladder against
    each's, h1-h12 rms."""
    def lad(stop):
        return np.nanmedian([P.measure(*recorded(stop, k), pitch(stop, k))[0][:12]
                             for k in keys(stop)[::3]], 0)
    t = lad("tremolo")
    for s in ("clarinette 2", "celeste", "musette"):
        d = lad(s) - t
        print("  tremolo row vs %-13s h1-h12 rms %.1f dB" % (s, np.sqrt(np.nanmean(d[1:] ** 2))), flush=True)


def tremolo_swing(x, sr, f0, at=None):
    s = held_part(x, sr)
    got = [swing(band_env(s, sr, m * f0, 0.35 * f0), sr, lo=4.0, hi=16.0, at=at) for m in (1, 2, 3, 4)]
    return np.median([g[0] for g in got]), np.median([g[1] for g in got])


def fit_tremolo(dry, voice="musette"):
    rates, deps = [], []
    for key in keys("tremolo")[::2]:
        x, sr = recorded("tremolo", key)
        r, d = tremolo_swing(x, sr, pitch("tremolo", key))
        rates.append(r); deps.append(d)
        print("  key %d  %.2f Hz  depth %.3f" % (key, r, d), flush=True)
    rate, dep = float(np.median(rates)), float(np.median(deps))
    print("  the Debain's tremolo: %.2f Hz (%.2f-%.2f), depth %.3f" % (rate, min(rates), max(rates), dep))
    HOST.stop_tremolo_hz = round(rate, 2)
    for _ in range(3):
        got = []
        for key in (67, 74, 81, 88):
            y, s2 = render(voice, key, 5.0, extra=("tremolo",))
            got.append(tremolo_swing(y, s2, pitch(voice, key), at=HOST.stop_tremolo_hz)[1])
        g = float(np.median(got))
        print("  ours: depth %.3f reads %.3f" % (HOST.stop_tremolo_depth, g), flush=True)
        HOST.stop_tremolo_depth = round(HOST.stop_tremolo_depth * dep / max(g, 1e-6), 4)
    print("  stop_tremolo_hz = %.2f, stop_tremolo_depth = %.4f" % (HOST.stop_tremolo_hz, HOST.stop_tremolo_depth))
    if not dry:
        p = os.path.join(HERE, "tonelib.py")
        t = open(p).read()
        t = re.sub(r"\nReedOrganFreeProperties\.stop_tremolo_hz = [0-9.]+\n",
                   "\nReedOrganFreeProperties.stop_tremolo_hz = %.2f\n" % HOST.stop_tremolo_hz, t)
        t = re.sub(r"\nReedOrganFreeProperties\.stop_tremolo_depth = [0-9.]+\n",
                   "\nReedOrganFreeProperties.stop_tremolo_depth = %.4f\n" % HOST.stop_tremolo_depth, t)
        open(p, "w").write(t)
        print("  written to tonelib.py")
    return HOST.stop_tremolo_hz, HOST.stop_tremolo_depth, (min(rates), max(rates))


# ---- the survey and the A/B ----------------------------------------------------

def survey():
    for stop in FOLDER:
        if stop == "tremolo":
            continue
        side = half(stop)
        ks = keys(stop)[::4]
        R = np.nanmedian([corrected(stop, k) for k in ks], 0)
        O = np.nanmedian([norm(harmonics(*render(stop, k), pitch(stop, k))[0]) for k in ks], 0)
        d = R - O
        print("== %-13s %s  target - ours rms %.1f dB (within 50);  level rec %+.1f, ours %+.1f re %s" % (
            stop, side, rms_top(d, R),
            rec_level(stop, side) - rec_level(FOUNDATION[side], side),
            ours_level(stop, side) - ours_level(FOUNDATION[side], side), FOUNDATION[side]), flush=True)
        print("   target " + " ".join("%5.1f" % v for v in R[:12]))
        print("   ours   " + " ".join("%5.1f" % v for v in O[:12]))


# The Debain's chapel, near enough, for ours in an A/B: its takes carry about
# 2 s of it (the set's notes)
DEBAIN_ROOM = "reverb 40 50 70 100 10 -4"


def ab(out, stop):
    """The Debain's take then ours, key by key across the stop's half,
    level-matched over the steady part; the left channel each."""
    import tempfile
    import subprocess
    import wave
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    SR = 48000
    gap = np.zeros(int(0.35 * SR))
    parts = []
    ks = keys(stop)
    for k in ks[::max(1, len(ks) // 6)]:
        x, sr = P.read(sample(stop, k))
        x = x[:, 0]
        a = int(np.flatnonzero(np.abs(x) > np.abs(x).max() * 0.01)[0])
        x = x[max(0, a - int(0.02 * sr)):]
        if sr != SR:
            x = resample_poly(x, SR, sr)
        y, s2 = render(stop, k, secs=min(3.0, len(x) / SR - 2.0))
        y = y[:, 0]
        if s2 != SR:
            y = resample_poly(y, SR, s2)
        with tempfile.TemporaryDirectory() as d:
            wavfile.write(os.path.join(d, "a.wav"), SR, (y / max(np.abs(y).max(), 1e-9) * 0.5).astype(np.float32))
            subprocess.run(["sox", os.path.join(d, "a.wav"), "-e", "floating-point", "-b", "32",
                            os.path.join(d, "b.wav")] + DEBAIN_ROOM.split(), check=True,
                           stderr=subprocess.DEVNULL)
            y = wavfile.read(os.path.join(d, "b.wav"))[1].astype(np.float64)
            y = y.mean(1) if y.ndim == 2 else y
        y = y[:len(x)]
        s0, s1 = int(1.0 * SR), int(3.0 * SR)
        y *= np.sqrt(np.mean(x[s0:s1] ** 2) / max(np.mean(y[s0:s1] ** 2), 1e-30))
        parts += [x, gap, y, gap, gap]
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    import warnings
    warnings.simplefilter("ignore")
    dry = "--dry" in argv
    stops = [a.split("=", 1)[1] for a in argv if a.startswith("--stop=")]
    abo = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if abo:
        ab(abo, stops[0])
        return 0
    if "--survey" in argv:
        survey()
        return 0
    if "--celeste" in argv:
        fit_celeste(dry)
        return 0
    if "--tremolo" in argv:
        tremolo_voice()
        fit_tremolo(dry)
        return 0
    for stop in stops or FIT:
        cls = rank_class(stop)
        print("\n== %s (%s, %s)" % (stop, cls.__name__, FOLDER[stop]), flush=True)
        hold = (ours_level(stop, half(stop)) - ours_level(FOUNDATION[half(stop)], half(stop))
                if "--hold-level" in argv else None)
        fit_tables(stop)
        fit_speech(stop)
        rec_d = fit_level(stop, hold)
        text = body(stop, rec_d)
        if dry:
            print(text)
        else:
            write_class(cls, text)
            print("  written to tonelib.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
