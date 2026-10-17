#!/usr/bin/env python3
"""The SFX set's weather and water (program 56, keys 79-84, SC-55 p.71) fitted
to Freesound recordings of the real thing (CC0; ~/Documents/refs/freesound,
sources.md), as examples/seashore_fit.py fitted the sea.

    python3 -I examples/weather_fit.py [VOICE ...]            measure: recorded against ours
    python3 -I examples/weather_fit.py --fit [--passes=N] [--write] VOICE
                                                      fit the colour, swell and grains

VOICE is rain, thunder, wind or stream (bubble is set from its recording's
events directly: see tonelib.SfxBubbleProperties).

Each is the seashore's machinery (tonelib.SfxWeatherProperties): a held noise
table, a slow swell, sparse grains. The fit is seashore_fit's: the colour
corrected band by band toward the recording, the swell's depth and rate
scaled toward it, the grains' level moved toward the recording's kurtosis in
the band they live in. NOT the swell: a drum channel has no swell rows (they
are a melodic channel's), so a one-shot's gesture is its rise and its gate -- the level held throughout (the set is balanced
separately, examples/elkit_balance.py --kit=56). The texture is read held: the
key's gate opened to HOLD seconds while it is measured; GeneralUser GS's
sample on the key sets its length in play (percussion_map.KIT_GATE).
"""
import math
import os
import sys
import warnings

import numpy as np
from scipy.signal import butter, sosfiltfilt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")
os.environ["TUNING_REFLECT"] = "0"

import seashore_fit as S          # noqa: E402  (measure, CEN, E3, active)

R = os.path.expanduser("~/Documents/refs/freesound")
HOLD = 24.0
# voice: (class, key, recording, the grains' band for their kurtosis)
VOICES = {
    "rain":    ("SfxRainProperties", 79, "rain/200273__jmbphilmes__rain-light-2-rural.wav", (1000, 16000)),
    "thunder": ("SfxThunderProperties", 80, "thunder/446753__bluedelta__heavy-thunder-strike-no-rain-quadro.wav",
                (40, 400)),
    "wind":    ("SfxWindProperties", 81, "wind/117611__swiftoid__wind_howl2_stereo.wav", None),
    "stream":  ("SfxStreamProperties", 83, "stream/382322__sterferny__stream.wav", (1000, 16000)),
}


def load(path):
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    sr, x = wavfile.read(path)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    if sr != 44100:
        x = resample_poly(x, 441, sr // 100)
        sr = 44100
    return x[:int(90 * sr)] / (np.abs(x).max() + 1e-12), sr


def kurt(x, sr, band):
    """How impulsive a band is: its kurtosis with its 100 ms rms divided out
    (seashore_fit.clicks, in the band a voice's grains live in)."""
    if band is None:
        return 3.0
    y = sosfiltfilt(butter(4, band, btype="band", fs=sr, output="sos"), x[:int(30 * sr)])
    w = int(0.1 * sr)
    z = y / (np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-12)
    return float(np.mean(z ** 4) / np.mean(z ** 2) ** 2)


def render(key):
    import elkit_fit as E
    import percussion_map as P
    E.KIT = 56
    gate = P.KIT_GATE[56].get(key)
    P.KIT_GATE[56][key] = HOLD
    P._RING_CLASSES.clear()
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        mid = os.path.join(d, "w.mid")
        import mido
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack(); m.tracks.append(t)
        t.append(mido.Message("program_change", channel=9, program=56, time=0))
        t.append(mido.Message("note_on", channel=9, note=key, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=9, note=key, velocity=0, time=120))
        t.append(mido.MetaMessage("end_of_track", time=int((HOLD + 2) * 960)))
        m.save(mid)
        import blockrender as B
        L, Rr = B.render(mid)[:2]
    P.KIT_GATE[56][key] = gate
    P._RING_CLASSES.clear()
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(Rr, np.float64)), 44100


def measure(x, sr, band):
    m = S.measure(x, sr)
    m["kurt"] = kurt(S.active(x, sr), sr, band)
    return m


def show(voice, rec, ours):
    sel = [i for i, c in enumerate(S.CEN) if 40 < c < 14000][::2]
    print("== %s" % voice)
    print("  colour at " + " ".join("%6d" % S.CEN[i] for i in sel))
    print("  recorded  " + " ".join("%6.1f" % v for v in rec["colour"][sel]))
    print("  ours      " + " ".join("%6.1f" % v for v in ours["colour"][sel]))
    print("  swell: recorded %.2f dB at %.2f Hz, ours %.2f dB at %.2f Hz;  kurtosis recorded %.1f, ours %.1f"
          % (rec["swell"], rec["rate"], ours["swell"], ours["rate"], rec["kurt"], ours["kurt"]))


def fit(voice, passes=6, write=False):
    import tonelib as T
    cname, key, path, band = VOICES[voice]
    cls = getattr(T, cname)
    rec = measure(*load(os.path.join(R, path)), band)
    # START FROM THE RECORDING'S OWN COLOUR, on the seashore table's scale: a
    # row at every third octave from 50 Hz (the thunder's rumble is under the
    # sea's 63)
    cls.breath_noise_db = tuple((round(float(c)), round(float(v) + 54.0, 1))
                                for c, v in zip(S.CEN, rec["colour"]) if 45 < c < 14000)
    target = None
    for n in range(passes + 1):
        ours = measure(*render(key), band)
        if target is None:
            target = ours["level"]
        d = rec["colour"] - ours["colour"]
        idx = {hz: int(np.argmin(np.abs(S.CEN - hz))) for hz, _ in cls.breath_noise_db}
        err = float(np.sqrt(np.mean([d[i] ** 2 for i in idx.values()])))
        print("  pass %d: colour rms %.1f dB; swell %.2f at %.2f Hz (rec %.2f at %.2f); kurtosis %.1f (rec %.1f)"
              % (n, err, ours["swell"], ours["rate"], rec["swell"], rec["rate"], ours["kurt"], rec["kurt"]),
              flush=True)
        if n == passes:
            break
        cls.breath_noise_db = tuple((hz, round(db + float(d[idx[hz]]) + (target - ours["level"]), 1))
                                    for hz, db in cls.breath_noise_db)
        # NO SWELL: the breath's swell rows are a CHANNEL's, built from its
        # melodic program, and a drum channel (its program the set) has none --
        # nor could one row serve wind, rain and thunder on one channel. A
        # first fit scaled the swell up ten passes running against nothing it
        # could move (8.4 million dB). A one-shot's gesture is its rise
        # (breath_noise_fade_s) and its gate.
        if cls.grains and band is not None:
            dk = 6.0 * math.log(rec["kurt"] / max(ours["kurt"], 1.01))
            cls.grains = tuple((r[0], r[1], r[2], round(r[3] + dk + (target - ours["level"]), 1)) + tuple(r[4:])
                               for r in cls.grains)
    show(voice, rec, ours)
    if write:
        import re
        path_t = os.path.join(HERE, "tonelib.py")
        s = open(path_t).read()
        i = s.index("class %s(" % cname)
        end = s.index("\nclass ", i + 1) if "\nclass " in s[i + 1:] else s.index("\n\nimport os as _os", i)
        body = re.sub(r"\n    # FITTED \(examples/weather_fit\.py\).*?(?=\n\n|\Z)", "", s[i:end], flags=re.S)
        body = re.sub(r"\n    grains = [^\n]*", "", body)
        body = body.rstrip("\n") + (
            "\n    # FITTED (examples/weather_fit.py): colour rms %.1f dB to the recording\n"
            "    breath_noise_db = %r\n"
            "    grains = %r\n" % (err, cls.breath_noise_db, cls.grains))
        s = s[:i] + body + "\n" + s[end:]
        open(path_t, "w").write(s)
        print("   wrote %s" % cname)


def main(argv):
    voices = [a for a in argv[1:] if not a.startswith("--")] or list(VOICES)
    for v in voices:
        if "--fit" in argv:
            fit(v, int(next((a.split("=")[1] for a in argv if a.startswith("--passes=")), 6)),
                write="--write" in argv)
        else:
            cname, key, path, band = VOICES[v]
            show(v, measure(*load(os.path.join(R, path)), band), measure(*render(key), band))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
