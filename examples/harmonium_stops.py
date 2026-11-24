#!/usr/bin/env python3
"""THE HARMONIUM'S STOPS FROM THEIR CONSTRUCTION (L10, step 2: Ben,
2026-11-23). Each stop is its reeds and where they sound, as Mustel describes
them (L'Orgue-Expressif ou Harmonium, Tome I, 1903, pp. 101-146), simulated
by examples/freereed_sim.py.

MUSTEL'S LEVERS (no numbers in the book -- each a named variable here, set in
the direction he gives):
  width      wide = intense and pure, narrow = fine and clear (p. 140)
  curl       the curved reed ("anche courbee"): the tip bent up, the air cut
             off gradually -- rounder, slower to speak (p. 139-140); on the
             Cor anglais/Flute and the Bourdon/Clarinette
  edge       the euphonic reed's rounded slot edges: softer, the expression
             kept (p. 140-141)
  rest       the voicing's rest gap ("jour"): smaller speaks quicker and
             brighter (p. 142)
  cover      the FRONT stops sound under the Fausse-Table, a felt-covered
             board laid almost on the pallets -- "arrondir son timbre et faire
             disparaitre les sons harmoniques" (p. 107-109, 120, 152): here
             felt absorbing above a corner over the outlets. The BACK stops
             sound open into the box (its lids are the Forte, later)
  pressure   the Sourdine is a throttle on the wind, not a reed (p. 115-120):
             the foundation's reeds at a share of the pressure
  celeste    two ranks, one tuned above and one below (Mustel's own method,
             1855): six beats a second "pour une note donnee", slower in the
             bass and faster in the treble, the progression even (p. 145)
MUSTEL'S TARGETS: the Hautbois the richest in harmonics, the Clarinette the
poorest (glossary p. 151); the front stops round and full ("ronde et
grasse"), the back stops decided and biting ("decide, mordant", p. 109).

    python3 examples/harmonium_stops.py --listen OUT.wav   each stop's middle note, raw
    python3 examples/harmonium_stops.py --survey           each stop's ladder, level and speech
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
import freereed_sim as F  # noqa: E402

# THE TREMOLO'S RATE (Ben, by ear: "the slower side; leave room for speed on
# higher and louder"): 5 Hz at 700 Pa (freereed_sim.TREMOLO_*), the treble
# half's own smaller bellows this much quicker
TREMOLO_HZ = 5.0
TREMOLO_TREBLE_RATIO = 1.15
PRESSURE_PA = 700.0           # a moderate playing pressure (Puranik & Scavone measured 200-1000 Pa)
CELESTE_BEATS = 6.0           # beats a second between its two ranks, at CELESTE_REF_HZ
CELESTE_REF_HZ = 440.0
CELESTE_BEAT_EXP = 0.5        # the beats' rise with pitch ("slower in the bass, faster in the treble")

# The foundation: the Cor anglais / Flute 8', front, curved -- our voice's own
# (fitted to donyaquick's CC0 harmonium); the stops are its differences
FOUNDATION = dict(curl=0.015, width=0.16, rest=0.019, edge=0.0, cover_hz=1500.0, pressure=1.0)
STOPS = {
    # front, curved, wide (pure): the Bourdon and its treble, the poorest stop
    # (one stop, its bass and treble halves; a curve of 0.03 L made a sine --
    # Ben: "very sinusoidal" -- 0.015 keeps its harmonics, darker than the
    # foundation, the Clarinette the poorest of all as Mustel has it)
    "Bourdon":     dict(cls="HarmoniumBourdonProperties", curl=0.015, width=0.20, rest=0.019, edge=0.0,
                        cover_hz=1200.0, pressure=1.0),
    "Clarinette":  dict(cls="HarmoniumClarinetteProperties", curl=0.015, width=0.20, rest=0.019, edge=0.0,
                        cover_hz=1200.0, pressure=1.0),
    # back, flat, narrow, close-set: the Basson and the Hautbois, the richest
    "Basson":      dict(cls="HarmoniumBassonProperties", curl=0.0, width=0.12, rest=0.012, edge=0.0,
                        cover_hz=None, pressure=1.0),
    "Hautbois":    dict(cls="HarmoniumHautboisProperties", curl=0.0, width=0.12, rest=0.012, edge=0.0,
                        cover_hz=None, pressure=1.0),
    # back, flat: the Clairon and the Fifre, 4'
    "Clairon":     dict(cls="HarmoniumClaironProperties", curl=0.0, width=0.14, rest=0.019, edge=0.0,
                        cover_hz=None, pressure=1.0),
    "Fifre":       dict(cls="HarmoniumFifreProperties", curl=0.0, width=0.14, rest=0.019, edge=0.0,
                        cover_hz=None, pressure=1.0),
    # back, flat, narrow: the Musette ("biting, rustic")
    "Musette":     dict(cls="HarmoniumMusetteProperties", curl=0.0, width=0.11, rest=0.015, edge=0.0,
                        cover_hz=None, pressure=1.0),
    # the Debain's string-toned bass solo (Mustel does not describe it): back,
    # flat, narrow, its slot's edges rounded
    "Violoncelle": dict(cls="HarmoniumVioloncelleProperties", curl=0.0, width=0.11, rest=0.019, edge=0.2e-3,
                        cover_hz=None, pressure=1.0),
    # the Sourdine: the foundation's reeds behind a throttle
    # (0.6 of the pressure once the tongues were thinned spoke 4 dB under the
    # foundation, bright: 0.4)
    "Sourdine":    dict(cls="HarmoniumSourdineProperties", **dict(FOUNDATION, pressure=0.4)),
    # the Voix celeste: the foundation's reeds in two ranks, one above, one below
    "Celeste":     dict(cls="HarmoniumCelesteProperties", **FOUNDATION, celeste=True),
}


# THE CASE (examples/harmonium_case.py --measure): donyaquick's harmonium (CC0,
# our foundation's own recording) against our simulated foundation, both re
# their total power, the differences by absolute frequency over eight notes
# 104-591 Hz -- its cabinet, room and microphone on the bare reed: a lift at
# 570-900 Hz, a dip at 1.1-1.4 kHz, a peak near 2.9 kHz. Applied to the raw
# renders only: the bake puts each stop on as its difference from the
# simulated foundation onto our foundation (fitted to that same recording),
# so a case common to every stop cancels there and the real one comes through
# the foundation.
CASE_DB = ((283, -0.4), (356, -0.8), (449, -1.3), (566, 6.2), (713, 6.9), (898, 3.1), (1131, -2.8),
           (1425, -6.4), (1796, -0.3), (2263, 6.4), (2851, 15.5), (3592, 6.1), (4525, 4.3), (5702, 3.8),
           (7184, 1.4), (9051, -3.5))
# THE BOX (Mustel pp. 116-120): the back stops sound into a box whose lids stay
# shut unless a Forte is drawn -- "decided, biting" still, but enclosed. No
# measurement: a first-order absorption above BOX_CLOSED_HZ with the lids
# shut, none with them open (forte=True)
BOX_CLOSED_HZ = 2000.0


def case(y, sr=48000):
    """The measured case curve on a whole note (frequency domain, zero phase),
    the note padded with silence first: unpadded, the FFT wrapped its cut-off
    end round to its start -- a click on every note (Ben)."""
    n0 = len(y)
    pad = int(0.1 * sr)
    y = np.concatenate([np.zeros(pad), y, np.zeros(pad)])
    n = len(y)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    hz = np.array([c[0] for c in CASE_DB], float)
    db = np.array([c[1] for c in CASE_DB], float)
    g = np.interp(np.log(np.maximum(f, 1.0)), np.log(hz), db, left=db[0], right=db[-1])
    g -= np.interp(np.log(1000.0), np.log(hz), db)     # (re 1 kHz: the level is the stop's)
    return np.fft.irfft(np.fft.rfft(y) * 10 ** (g / 20.0), n)[pad:pad + n0]


def _set(v):
    F.CURL_M = 0.0
    F.EDGE_ROUND_M = v["edge"]
    F.WIDTH_RATIO = v["width"]
    F.REST_RATIO = v["rest"]


def cover(y, hz, sr=48000):
    """The felt board over the outlets: a first-order absorption above hz."""
    if not hz:
        return y
    a = np.exp(-2.0 * np.pi * hz / sr)
    out = np.empty_like(y)
    s = 0.0
    for i, x in enumerate(y):
        s = a * s + (1.0 - a) * x
        out[i] = s
    return out


def sound(v, f0, secs=1.0, vel=0.6, forte=False, with_case=False):
    """A stop's note at f0 (Hz, sounding): the radiated signal at 48 kHz --
    a back stop through its box (lids shut, unless forte), and, with_case,
    through the measured case."""
    _set(v)
    L, _, _ = F.tongue(f0)
    F.CURL_M = v["curl"] * L
    p = PRESSURE_PA * v["pressure"]
    if v.get("celeste"):
        beats = CELESTE_BEATS * (f0 / CELESTE_REF_HZ) ** CELESTE_BEAT_EXP
        ys = [F.simulate(f0 + s * beats / 2.0, p, secs=secs, vel=vel)[0] for s in (1.0, -1.0)]
        y = 0.5 * (ys[0] + ys[1])
    else:
        y = F.simulate(f0, p, secs=secs, vel=vel)[0]
    y = cover(y, v["cover_hz"])
    if v["cover_hz"] is None and not forte:          # a back stop: the box, its lids shut
        y = cover(y, BOX_CLOSED_HZ)
    return case(y) if with_case else y


def ladder(y, f0, n=12, sr=48000):
    s = y[len(y) // 2:]
    X = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 17))
    fr = np.fft.rfftfreq(1 << 17, 1.0 / sr)
    h = np.array([X[(fr > f0 * k * 0.97) & (fr < f0 * k * 1.03)].max() for k in range(1, n + 1)])
    return 20 * np.log10(h / h.max() + 1e-12)


def survey():
    import tonelib as T
    for name, v in STOPS.items():
        pts = getattr(T, v["cls"]).mode_gains_points
        f0 = pts[len(pts) // 2][0]
        y = sound(v, f0, secs=0.8)
        y0 = sound(FOUNDATION, f0, secs=0.8)
        lv = 10 * np.log10(np.mean(y[len(y) // 2:] ** 2) / np.mean(y0[len(y0) // 2:] ** 2))
        hl = ladder(y, f0)
        cen = np.sum(np.arange(1, 13) * 10 ** (hl / 10)) / np.sum(10 ** (hl / 10))
        print("  %-11s %6.1f Hz: level %+5.1f dB re the foundation, centroid h%.2f, h1-12 %s"
              % (name, f0, lv, cen, " ".join("%4.0f" % x for x in hl)), flush=True)


def listen(outp):
    import tonelib as T
    from scipy.io import wavfile
    parts = []
    for name, v in [("Foundation", dict(FOUNDATION, cls="ReedOrganFreeProperties"))] + list(STOPS.items()):
        pts = getattr(T, v["cls"], None)
        pts = getattr(pts, "mode_gains_points", None) or ((261.63, None),)
        f0 = pts[len(pts) // 2][0] if name != "Foundation" else 261.63
        y = sound(v, f0, secs=1.2)
        env = np.ones_like(y)
        env[-2400:] = np.linspace(1, 0, 2400)
        parts += [y * env, np.zeros(14400)]
        print("  %s at %.1f Hz" % (name, f0), flush=True)
    y = np.concatenate(parts)
    wavfile.write(outp, 48000, (y / np.abs(y).max() * 0.8 * 32767).astype(np.int16))


# each stop's name on the voice (ReedOrganFreeProperties.stop_ranks) and its
# footage ratio (16' 0.5, 8' 1, 4' 2)
VOICE_STOP = {"Foundation": ("cor anglais 1", 1.0), "Bourdon": ("bourdon 2", 0.5),
              "Clarinette": ("clarinette 2", 0.5), "Basson": ("basson 4", 1.0), "Hautbois": ("hautbois 4", 1.0),
              "Clairon": ("clairon 3", 2.0), "Fifre": ("fifre 3", 2.0), "Musette": ("musette", 0.5),
              "Violoncelle": ("violoncelle", 1.0), "Sourdine": ("sourdine", 1.0), "Celeste": ("celeste", 0.5)}


def old_new(outp, secs=1.4):
    """Each stop as the voice plays it now, then from its construction, at
    the same sounding pitch, each pair matched in loudness (the steady part's
    rms) -- tone against tone, not level."""
    import tonelib as T
    import debain_registers as D
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    parts = []
    for name, v in [("Foundation", dict(FOUNDATION, cls="ReedOrganFreeProperties"))] + list(STOPS.items()):
        pts = getattr(getattr(T, v["cls"]), "mode_gains_points", None)
        f0 = pts[len(pts) // 2][0] if pts else 261.63
        stop, ratio = VOICE_STOP[name]
        key = int(round(69 + 12 * np.log2(f0 / ratio / 440.0)))
        x, sr = D.render(stop, key, secs=secs)
        old = resample_poly(x.mean(1), 48000, sr)[:int(secs * 48000)]
        new = sound(v, f0, secs=secs, with_case=True)
        clips = [old, new]
        if v["cover_hz"] is None:                     # a back stop: and with its Forte drawn
            clips.append(sound(v, f0, secs=secs, forte=True, with_case=True))
        pair = []
        for y in clips:
            r = np.sqrt(np.mean(y[len(y) // 2:] ** 2)) + 1e-12
            y = y / r * 0.1
            env = np.ones_like(y)
            env[:144] = np.linspace(0, 1, 144)          # (3 ms in: no step at the splice)
            env[-2400:] = np.linspace(1, 0, 2400)
            pair += [y * env, np.zeros(9600)]
        parts += pair + [np.zeros(14400)]
        print("  %-11s key %d (%.1f Hz): old, new%s" % (name, key, f0, ", new with Forte" if len(clips) > 2 else ""),
              flush=True)
    y = np.concatenate(parts)
    wavfile.write(outp, 48000, (y / np.abs(y).max() * 0.8 * 32767).astype(np.int16))


def tremolo_listen(outp, rates=(5.0, 6.5, 8.0)):
    """The tremolo at each rate (middle C, G4, through the case), then the
    middle rate soft and loud: the bellows quickening with the wind."""
    from scipy.io import wavfile
    parts = []

    def clip(f0, p_scale=1.0):
        y = sound(dict(FOUNDATION, pressure=p_scale), f0, secs=2.2, with_case=True)
        env = np.ones_like(y)
        env[:144] = np.linspace(0, 1, 144)
        env[-2400:] = np.linspace(1, 0, 2400)
        return [y / (np.sqrt(np.mean(y[len(y) // 2:] ** 2)) + 1e-12) * 0.1 * env, np.zeros(9600)]
    for r in rates:
        F.TREMOLO_HZ = r
        for f0 in (261.63, 392.0):
            parts += clip(f0)
        parts.append(np.zeros(19200))
        print("  %.1f Hz" % r, flush=True)
    F.TREMOLO_HZ = rates[len(rates) // 2]
    for ps in (0.45, 2.0):
        parts += clip(261.63, ps)
    print("  %.1f Hz at 315 and 1400 Pa" % F.TREMOLO_HZ, flush=True)
    F.TREMOLO_HZ = 0.0
    y = np.concatenate(parts)
    wavfile.write(outp, 48000, (y / np.abs(y).max() * 0.8 * 32767).astype(np.int16))


if __name__ == "__main__":
    if "--tremolo" in sys.argv:
        tremolo_listen(sys.argv[sys.argv.index("--tremolo") + 1])
    if "--oldnew" in sys.argv:
        old_new(sys.argv[sys.argv.index("--oldnew") + 1])
    if "--survey" in sys.argv:
        survey()
    if "--listen" in sys.argv:
        listen(sys.argv[sys.argv.index("--listen") + 1])
