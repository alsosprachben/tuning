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
    # THE VEHICLES (63-69): read from a stretch of the recording (SEGMENT), the
    # crash whole (SHORT); the train's FLAC decoded by sox into SCRATCH
    "engine":  ("SfxEngineProperties", 63, "engine/433584__jackthemurray__car-starting-and-accelerating.wav", None),
    "train":   ("SfxTrainProperties", 68, "train/567731__trp__200614-train-starts-rumble-clacks-speeds-up-passes-12pm.flac",
                (200, 4000)),
    "jet":     ("SfxJetProperties", 69, "jet/251966__clif_creates__jet-plane-8.wav", None),
    "crash":   ("SfxCrashProperties", 66, "crash/592388__magnuswaker__car-crash-with-glass.wav", (2000, 12000)),
    # the pitched ones' noise (their tones set from the recordings' peaks,
    # tonelib); the siren has none
    "skid":    ("SfxSkidProperties", 64, "skid/71741__audible-edge__nissan-maxima-handbrake-turn-04-25-2009.wav", None),
    "carpass": ("SfxCarPassProperties", 65,
                "carpass/380207__lunchmoney__car-passing-winter-day-wet-road-doppler-sound-devices-702-senn-k6.wav",
                None),
    # no recording: GeneralUser's patch as it means it, built by
    # examples/starship_ref.py into a scratch WAV (load, below)
    "starship": ("SfxStarshipProperties", 71, "STARSHIP", None),
    # THE REST (39-75): a blast, a turntable, a hinge, a rifle
    "explosion": ("SfxExplosionProperties", 75, "explosion/251401__felixblume__dynamite-explosion-in-the-mountain.wav",
                  None),
    "scratch": ("SfxScratchPushProperties", 41, "scratch/610676__liftpizzas__scratch-4x.wav", None),
    "creak":   ("SfxDoorCreakProperties", 59, "doorcreak/316683__alex_hears_things__slow-door-hinges_nm.wav", None),
    "machinegun": ("SfxMachinegunProperties", 73, "machinegun/693546__areniporgen__colt-m16a1.wav", None),
    # THE VOICES (52, 53): a voice's harmonics set from the recording's own
    # (tonelib), their breath fitted under them -- a woman's laugh, a girl's
    # scream, at the recordings' own pitches
    "laugh":   ("SfxLaughProperties", 52, "laugh/433921__kalibrk__woman-laugh.wav", None),
    "scream":  ("SfxScreamProperties", 53, "scream/400183__tomattka__girl-screaming_01.wav", None),
}
SEGMENT = {"engine": (4.5, 10.0), "train": (10.0, 55.0), "jet": (5.0, 25.0),
           "skid": (6.1, 6.9), "carpass": (3.5, 7.5),
           "explosion": (0.0, 2.1), "scratch": (0.12, 0.55), "creak": (0.55, 3.4), "machinegun": (5.37, 6.9)}
SHORT = {"crash", "starship", "explosion", "scratch", "creak", "machinegun", "laugh", "scream"}
# A NOTE BESIDE THE NOISE: (f0 Hz, each harmonic's height over its local floor
# in the recording, dB) -- the engine idle's firing (examples/weather_fit.py
# reads it at --fit; tonelib.SfxEngineProperties)
TONE = {"engine": 47.42}
# THE TABLE A VOICE'S COLOUR IS FITTED IN: the held noise's (breath_noise_db),
# or another the class names, started from the class's own. (Not the machine
# gun's strike: a strike's rows are noise bands, which swell ~0.1 s whatever
# their rate -- no crack; its shots are grains on a clock)
TABLE = {}
# ...or a TONE'S HARMONICS, each moved by the colour where it sits at the
# rate's middle (Hz). Not the creak's: its rate sweeps an octave, and alone
# its harmonics left bands empty (14.9 dB) -- its noise is fitted under them
# The scream's: its harmonics stand 60 dB over its breath (the take steady,
# clean to 7.4 kHz), which a colour fit of the noise alone filled in -- 60 dB
# of noise in the fundamental's band. Its breath set 30 dB under the take's
# colour, the harmonics fitted over it. The laugh's "ha"s are clean harmonics
# too, its breath the "h" before them: 20 dB under
HARMCOL = {"scream": 1243.0, "laugh": 337.0}


def load(path, seg=None):
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    if path.endswith("STARSHIP"):
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.mkdtemp(), "starship_ref.wav")
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "examples", "starship_ref.py"), tmp],
                       check=True, stdout=subprocess.DEVNULL)
        path = tmp
    elif not path.endswith(".wav"):
        # a FLAC or an MP3: decoded by sox to a scratch WAV beside nothing else
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.mkdtemp(), "decoded.wav")
        subprocess.run(["sox", path, tmp], check=True)
        path = tmp
    sr, x = wavfile.read(path)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    if sr != 44100:
        x = resample_poly(x, 441, sr // 100)
        sr = 44100
    if seg is not None:
        x = x[int(seg[0] * sr):int(seg[1] * sr)]
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


def measure(x, sr, band, short=False, f0=None):
    if short or len(x) < 8 * sr:
        # a SHORT sound (the crash, 2.6 s; the engine's 5.5 s of idle): its
        # colour whole, from where it sounds -- no second trimmed off each
        # end, no swell (its 3 s running mean needs more)
        w = int(0.05 * sr)
        e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
        on = np.flatnonzero(e > e.max() * 10 ** (-40 / 20))
        x = x[on[0]:on[-1]]
        N = 1 << 14
        X = np.zeros(N // 2 + 1)
        for a in range(0, max(1, len(x) - N), N // 4):
            seg = x[a:a + N]
            X += np.abs(np.fft.rfft(np.pad(seg, (0, N - len(seg))) * np.hanning(N))) ** 2
        f = np.fft.rfftfreq(N, 1.0 / sr)
        c = np.array([X[(f >= lo) & (f < hi)].sum() for lo, hi in zip(S.E3[:-1], S.E3[1:])])
        m = dict(colour=10 * np.log10(c / c.max() + 1e-12), swell=0.0, rate=0.0,
                 level=float(10 * np.log10(np.mean(x * x) + 1e-30)))
        m["kurt"] = kurt(x, sr, band)
    else:
        m = S.measure(x, sr)
        m["kurt"] = kurt(S.active(x, sr), sr, band)
    if f0:
        m["harm"] = harmonics(x, sr, f0)
    return m


def harmonics(x, sr, f0, n=16):
    """Each harmonic's peak over its local floor (+-12 Hz, its own +-3 Hz
    left out), dB: how far the note stands out of the noise."""
    x = x[:int(8 * sr)]
    N = 1 << 19
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    out = []
    for k in range(1, n + 1):
        c = k * f0
        pk = X[(f > c - 1.5) & (f < c + 1.5)].max()
        fl = (f > c - 12) & (f < c + 12) & ~((f > c - 3) & (f < c + 3))
        out.append(20 * np.log10(pk / (np.median(X[fl]) + 1e-12)))
    return np.array(out)


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
    short, f0 = voice in SHORT, TONE.get(voice)
    rec = measure(*load(os.path.join(R, path), SEGMENT.get(voice)), band, short, f0)
    # START FROM THE RECORDING'S OWN COLOUR, on the seashore table's scale: a
    # row at every third octave from 50 Hz (the thunder's rumble is under the
    # sea's 63)
    tab, hc = TABLE.get(voice, "breath_noise_db"), HARMCOL.get(voice)
    if tab == "breath_noise_db" and not hc:
        cls.breath_noise_db = tuple((round(float(c)), round(float(v) + 54.0, 1))
                                    for c, v in zip(S.CEN, rec["colour"]) if 45 < c < 14000)
    target = None
    for n in range(passes + 1):
        ours = measure(*render(key), band, short, f0)
        if target is None:
            target = ours["level"]
        d = rec["colour"] - ours["colour"]
        if hc:
            # each harmonic at the band its middle rate puts it in
            idx = {k: int(np.argmin(np.abs(S.CEN - k * hc))) for k in range(1, len(cls.mode_gains) + 1)
                   if k * hc < 14000}
        else:
            idx = {hz: int(np.argmin(np.abs(S.CEN - hz))) for hz, _ in getattr(cls, tab)}
        err = float(np.sqrt(np.mean([d[i] ** 2 for i in idx.values()])))
        print("  pass %d: colour rms %.1f dB; swell %.2f at %.2f Hz (rec %.2f at %.2f); kurtosis %.1f (rec %.1f)"
              % (n, err, ours["swell"], ours["rate"], rec["swell"], rec["rate"], ours["kurt"], rec["kurt"]),
              flush=True)
        if n == passes:
            break
        # the level held where it began -- except under a note, where the
        # noise moves against the note: down by how much less the firing
        # stands out of it than the recording's (half the gap a pass; the
        # colour alone cannot see it, the noise filling the firing's band)
        lv = 0.5 * (ours["harm"][0] - rec["harm"][0]) if f0 else target - ours["level"]
        if hc:
            # half the gap a pass: neighbouring harmonics share a band
            cls.mode_gains = tuple(float(g * 10 ** ((0.5 * float(d[idx[k + 1]]) + lv) / 20.0)) if k + 1 in idx
                                   else float(g) for k, g in enumerate(cls.mode_gains))
        else:
            setattr(cls, tab, tuple((hz, round(db + float(d[idx[hz]]) + lv, 1)) for hz, db in getattr(cls, tab)))
        # NO SWELL: the breath's swell rows are a CHANNEL's, built from its
        # melodic program, and a drum channel (its program the set) has none --
        # nor could one row serve wind, rain and thunder on one channel. A
        # first fit scaled the swell up ten passes running against nothing it
        # could move (8.4 million dB). A one-shot's gesture is its rise
        # (breath_noise_fade_s) and its gate.
        if f0:
            # each harmonic moved by how far it stands out of the noise against
            # the recording's, against the firing's own gap -- the gains are a
            # SHAPE (normalised to the strongest; the colour sets the note's
            # level against the noise) -- half the gap a pass
            dh = 0.5 * ((rec["harm"] - ours["harm"]) - (rec["harm"][0] - ours["harm"][0]))
            # ...only those standing clear of the noise (18 dB): one a few dB
            # over it reads the noise, not the harmonic, and the fit chased it
            # to nothing (h8 at -101 dB) -- those keep their measured heights
            dh = np.where(rec["harm"] >= 18.0, dh, 0.0)
            cls.mode_gains = tuple(float(g * 10 ** (d / 20.0)) for g, d in zip(cls.mode_gains, dh))
            print("     harmonics over the floor, ours - recorded: %s"
                  % " ".join("%+.0f" % v for v in (ours["harm"] - rec["harm"])[:10]))
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
        # the class ends at its last indented line: a next section's comment
        # header before the next class stays after the fit (it had been
        # written under the explosion's following header)
        tail = re.search(r"(\n(\n|#[^\n]*\n?)*)\Z", s[i:end])
        end = i + tail.start() if tail else end
        body = re.sub(r"\n    # FITTED \(examples/weather_fit\.py\).*?(?=\n\n|\Z)", "", s[i:end], flags=re.S)
        body = re.sub(r"\n    grains = [^\n]*(\n              [^\n]*)*", "", body)
        if f0 or hc:
            body = re.sub(r"\n    mode_gains = [^\n]*", "", body)
        if tab != "breath_noise_db":
            body = re.sub(r"\n    %s = [^\n]*" % tab, "", body)
        body = body.rstrip("\n") + (
            "\n    # FITTED (examples/weather_fit.py): colour rms %.1f dB to the recording\n"
            "    breath_noise_db = %r\n"
            "    grains = %r\n" % (err, cls.breath_noise_db, cls.grains)
            + ("    %s = %r\n" % (tab, getattr(cls, tab)) if tab != "breath_noise_db" else "")
            + ("    mode_gains = (%s)\n" % ", ".join("%.5g" % g for g in cls.mode_gains) if f0 or hc else ""))
        s = s[:i] + body[:-1] + s[end:]      # the spacing after the class as it was
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
            short, f0 = v in SHORT, TONE.get(v)
            show(v, measure(*load(os.path.join(R, path), SEGMENT.get(v)), band, short, f0),
                 measure(*render(key), band, short, f0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
