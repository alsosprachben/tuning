#!/usr/bin/env python3
"""The PLECTRUM (tonelib.Plectrum) fitted to picked takes: the 12-string's
(Fender, Pianobook), the mandolin's (Eclectic Mandolin) and the lap steel's
fingerpicks (Lapsteel Articulations) -- sources.md.

    python3 examples/plectrum_fit.py measure          recorded against ours
    python3 examples/plectrum_fit.py fit              the three stages, printed

MEASURED THE SAME WAY ON BOTH SIDES, per note, from the onset (2% of peak):
  HF0    energy over 4 kHz in the first 15 ms, dB re all of it
  FALL   HF0 less the same share at 100-200 ms (the transient's fall)
  FLAT   spectral flatness 1-8 kHz over the first 20 ms (0 = noise)
  RISE   ms from the onset to 90% of the 5 ms envelope's peak (in 80 ms)
The mandolin's take is darker than a mandolin by 15-20 dB over 2 kHz (re-amped,
its pack says), so for it HF0 is left out: its FALL and FLAT still count.

THE STAGES, each on what it moves: (pick_slope_db, pick_dbs) on HF0 and FALL;
chiff_volume on FLAT; course_stagger_s on RISE (the doubled courses only).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

REF = os.path.expanduser("~/Documents/refs")
# voice: (class, program, bank, [(file, MIDI)], use HF0?)
VOICES = {
    "12str": ("TwelveStringProperties", 25, 8,
              [("guitar12_fender/wav/fender_12_string_E2.wav", 40),
               ("guitar12_fender/wav/fender_12_string_E3.wav", 52),
               ("guitar12_fender/wav/fender_12_string_A3.wav", 57),
               ("guitar12_fender/wav/fender_12_string_E4.wav", 64),
               ("guitar12_fender/wav/fender_12_string_A4.wav", 69)], True),
    "mandolin": ("MandolinProperties", 25, 16,
                 [("mandolin_eclectic/wav/57.wav", 50), ("mandolin_eclectic/wav/52.wav", 55),
                  ("mandolin_eclectic/wav/48.wav", 59), ("mandolin_eclectic/wav/45.wav", 63),
                  ("mandolin_eclectic/wav/40.wav", 68)], False),
    # (the lap steel's fingerpicks give no transient -- its top does not fall,
    # FALL ~0 -- and it is fitted without one: kept here to measure)
    "lapsteel": ("HawaiianGuitarProperties", 26, 8,
                 [("lapsteel/x/samples/open/E3.wav", 40), ("lapsteel/x/samples/open/E4.wav", 52),
                  ("lapsteel/x/samples/open/B4.wav", 59), ("lapsteel/x/samples/open/E5.wav", 64)], True),
}


def load(path):
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    import blockrender as B
    sr, x = wavfile.read(os.path.join(REF, path))
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    if sr != B.SR:
        x = resample_poly(x, B.SR, sr)
    return x / (np.abs(x).max() + 1e-12)


def metrics(x, sr):
    a = int(np.flatnonzero(np.abs(x) > 0.02 * np.abs(x).max())[0])
    w = max(1, int(0.005 * sr))
    e = np.sqrt(np.convolve(x ** 2, np.ones(w) / w, "same"))[a:a + int(0.08 * sr)]
    rise = int(np.flatnonzero(e >= 0.9 * e.max())[0]) / sr * 1000.0

    def hf(t0, t1):
        s = x[a + int(t0 * sr):a + int(t1 * sr)]
        X = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 15)) ** 2
        f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
        return 10 * np.log10(X[f > 4000].sum() / X.sum() + 1e-12)
    s = x[a:a + int(0.02 * sr)]
    X = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 14)) ** 2
    f = np.fft.rfftfreq(1 << 14, 1.0 / sr)
    m = (f > 1000) & (f < 8000)
    flat = 10 * np.log10(np.exp(np.mean(np.log(X[m] + 1e-20))) / np.mean(X[m]))
    h0 = hf(0.0, 0.015)
    out = dict(HF0=h0, FALL=h0 - hf(0.1, 0.2), FLAT=flat, RISE=rise)
    # the attack's shape: each octave 1-16 kHz in the first 15 ms, dB re all of it
    s = x[a:a + int(0.015 * sr)]
    X = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 15)) ** 2
    f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
    for lo in (1000, 2000, 4000, 8000):
        out["B%d" % (lo // 1000)] = 10 * np.log10(X[(f >= lo) & (f < 2 * lo)].sum() / X.sum() + 1e-12)
    # ...and HOW LONG it lasts: the 4-8 and 8-16 kHz bands' 2 ms envelope, dB
    # re the note's peak -- its top in the first 16 ms, then at 24, 40, 70 ms.
    # The 15 ms shares above cannot tell a short loud scrape from a long quiet
    # one, and the first fit took the long one (Ben: "too harsh")
    from scipy.signal import butter, sosfiltfilt
    pk = np.abs(x).max()
    for lo in (4000, 8000):
        y = sosfiltfilt(butter(4, [lo, min(2 * lo, 0.45 * sr)], btype="band", fs=sr, output="sos"), x)
        y = y[a:a + int(0.08 * sr)]
        w = int(0.002 * sr)
        e = 20 * np.log10(np.array([np.sqrt((y[i:i + w] ** 2).mean()) for i in range(0, len(y) - w, w)]) / pk + 1e-9)
        k = lo // 1000
        out["E%da" % k] = e[:8].max()
        # (the later points re that top: how fast it falls, which a take's EQ
        # does not move -- the mandolin's dark one counts here too)
        for ms in (24, 40, 70):
            out["E%d_%d" % (k, ms)] = e[ms // 2] - e[:8].max()
    return out


def ours(cls, prog, bank, midi):
    import sfx_variations as V
    x = V.render(V.midi([(0, "cc", 0, 0, bank), (0, "pc", 0, prog, 0), (0.0, "on", 0, midi, 100),
                         (1.0, "off", 0, midi, 0)], 1.3)).mean(1)
    return x / (np.abs(x).max() + 1e-12)


_REC = {}


def table(voice):
    import blockrender as B
    cls, prog, bank, notes, use_hf = VOICES[voice]
    out = []
    for f, midi in notes:
        if f not in _REC:
            _REC[f] = metrics(load(f), B.SR)
        out.append((_REC[f], metrics(ours(cls, prog, bank, midi), B.SR)))
    return out


def score(voice, keys):
    rows = table(voice)
    use_hf = VOICES[voice][4]
    scale = dict(HF0=6.0, FALL=6.0, FLAT=3.0, RISE=5.0, B1=6.0, B2=6.0, B4=6.0, B8=6.0)
    d = [((r[k] - o[k]) / scale.get(k, 6.0)) ** 2 for r, o in rows for k in keys
         if use_hf or not (k == "HF0" or k[0] == "B" or k[-1] == "a")]
    return float(np.sqrt(np.mean(d))) if d else 0.0


def show(voice):
    print("  == %s" % voice)
    for (r, o), (f, midi) in zip(table(voice), VOICES[voice][3]):
        for nm, q in (("%-3d rec " % midi, r), ("    ours", o)):
            print("    %s HF0 %6.1f FALL %5.1f FLAT %6.1f RISE %5.1f  1-2k %6.1f 2-4k %6.1f 4-8k %6.1f 8-16k %6.1f"
                  % (nm, q["HF0"], q["FALL"], q["FLAT"], q["RISE"], q["B1"], q["B2"], q["B4"], q["B8"]))
            print("    %s   4-8k env top %5.0f  then %+4.0f at 24 ms %+4.0f at 40 %+4.0f at 70 | 8-16k top %5.0f  then %+4.0f %+4.0f %+4.0f"
                  % (" " * len(nm), q["E4a"], q["E4_24"], q["E4_40"], q["E4_70"],
                     q["E8a"], q["E8_24"], q["E8_40"], q["E8_70"]))


def fit(voice):
    """THE SCRAPE first (pick_noise_db and _tilt_db on the attack's shape and
    flatness, the partials' boost off), then how fast it goes (pick_noise_dbs
    on FALL), then whether a boost on the partials still helps, then the
    course stagger on RISE."""
    import tonelib as T
    C = getattr(T, VOICES[voice][0])
    C.pick_slope_db, C.chiff_volume, C.pick_noise_dbs = 0.0, 0.0, 300.0
    env = ("E4a", "E4_24", "E4_40", "E4_70", "E8a", "E8_24", "E8_40", "E8_70")
    shape = ("FLAT", "B1", "B2", "B4", "B8") + env
    best = None
    for lv in (-18.0, -12.0, -6.0, 0.0, 6.0):
        for hi in (4000.0, 5500.0, 7000.0):
            for dbs in (400.0, 700.0, 1100.0):
                C.pick_noise_db, C.pick_noise_tilt_db, C.pick_noise_hi_hz, C.pick_noise_dbs = lv, 0.0, hi, dbs
                s = score(voice, shape)
                print("    %s scrape %5.1f dB to %5.0f Hz falling %4.0f dB/s -> %.2f"
                      % (voice, lv, hi, dbs, s), flush=True)
                if best is None or s < best[0]:
                    best = (s, lv, hi, dbs)
    C.pick_noise_db, C.pick_noise_hi_hz, C.pick_noise_dbs = best[1], best[2], best[3]
    bd = None
    for tilt in (-3.0, 0.0, 3.0):
        C.pick_noise_tilt_db = tilt
        s = score(voice, shape)
        print("    %s scrape tilt %+.0f dB/oct -> %.2f" % (voice, tilt, s), flush=True)
        if bd is None or s < bd[0]:
            bd = (s, tilt)
    C.pick_noise_tilt_db = bd[1]
    bb = None
    for slope, pdbs in ((0.0, 60.0), (6.0, 150.0), (12.0, 150.0), (12.0, 400.0)):
        C.pick_slope_db, C.pick_dbs = slope, pdbs
        s = score(voice, shape + ("FALL",))
        print("    %s partials' boost %4.1f dB/oct at %3.0f dB/s -> %.2f" % (voice, slope, pdbs, s), flush=True)
        if bb is None or s < bb[0]:
            bb = (s, slope, pdbs)
    C.pick_slope_db, C.pick_dbs = bb[1], bb[2]
    bs = (0.0, C.course_stagger_s)
    if voice in ("12str", "mandolin") and "--stagger" in sys.argv:
        bs = None
        for st in (0.0, 0.004, 0.008, 0.014, 0.020, 0.028, 0.040):
            C.course_stagger_s = st
            s = score(voice, ("RISE",))
            print("    %s stagger %.0f ms -> %.2f" % (voice, st * 1000, s), flush=True)
            if bs is None or s < bs[0]:
                bs = (s, st)
        C.course_stagger_s = bs[1]
    print("  %s: pick_noise_db = %.1f, pick_noise_tilt_db = %.1f, pick_noise_hi_hz = %s, pick_noise_dbs = %.0f, "
          "pick_slope_db = %.1f, pick_dbs = %.0f, course_stagger_s = %.3f"
          % (voice, best[1], bd[1], best[2], best[3], bb[1], bb[2], bs[1]))


if __name__ == "__main__":
    which = [v for v in sys.argv[2:] if not v.startswith("--")] or ["12str", "mandolin"]
    if sys.argv[1] == "measure":
        for v in which:
            show(v)
    else:
        for v in which:
            fit(v)
            show(v)
