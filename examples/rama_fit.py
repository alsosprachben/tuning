#!/usr/bin/env python3
"""GS 112.16 "RAMA Cymbal" (tonelib.CengCengProperties) to the Balinese
ceng-ceng: the University of North Texas gamelan Bwana Kumala's strikes
(cpolcyn, Freesound pack 12954, CC0; sources.md).

    python3 examples/rama_fit.py            the strokes against ours
    python3 examples/rama_fit.py --fit [--maxfev=N]

THE STROKES: of the pack's twelve ceng-ceng files, three are PATTERNS of
strikes (00, 01, 07: restrikes() finds them), not one; the other nine are
single strikes of two kinds -- DAMPED (five, falling 140-180 dB/s, the
gamelan's closed "cak") and RINGING (04, 05, 08, 10: 41-61 dB/s, gone in
1-1.8 s). The tone is the ringing one: SENSATIO holds its eight accents 0.29
s and lets them ring. The ringing strokes are those whose first 0.3 s falls
under OPEN_DBS.

Read on examples/crash_fit.py's grid -- octave bands 250 Hz-16 kHz by windows
to 4 s, each stroke re its total energy -- and fitted with its score (the
band trim common to the strokes solved for) and its parameters (the ring's
peak and decays, the aftersound, the bloom, the strike). Ours as the file
plays it: C6, velocity 60.
"""
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
sys.argv = [a for a in sys.argv]
import crash_fit as C  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/freesound/gamelan_bwana_kumala")
OPEN_DBS = 70.0
NOTE, VEL = 84, 60


def read(p):
    from scipy.io import wavfile
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "x.wav")
        subprocess.run(["sox", p, "-b", "32", "-e", "floating-point", w], check=True)
        sr, x = wavfile.read(w)
    x = np.asarray(x, np.float64)
    return ([x[:, 0], x[:, 1]] if x.ndim > 1 else [x]), sr


def restrikes(chs, sr):
    """Strikes after the first: a fresh strike brings its own burst at 6-16
    kHz, where a ringing plate's level only falls -- the 6-16 kHz envelope
    (5 ms) rising 4 dB over its last 30 ms, within 50 dB of its loudest, past
    the first 0.1 s. Files 00 and 01 are PATTERNS (5 strikes in 1.1 s; one
    every half second for 7 s), not rings: fitted as one stroke they held
    the ring 15-20 s (Ben: "decaying way too long")."""
    from scipy.signal import butter, sosfilt
    x = sum(chs) / len(chs)
    hf = sosfilt(butter(4, [6000, 16000], "band", fs=sr, output="sos"), x)
    w = int(0.005 * sr)
    e = 10 * np.log10(np.convolve(hf ** 2, np.ones(w) / w, "same")[::w] + 1e-20)
    top, hits = e.max(), []
    for k in range(20, len(e)):
        if e[k] > top - 50 and e[k] - e[k - 6:k].max() > 4 and (not hits or k - hits[-1] > 10):
            hits.append(k)
    return len(hits)


def strokes():
    out = []
    for p in sorted(glob.glob(os.path.join(REFS, "*ceng-ceng*.flac"))):
        chs, sr = read(p)
        if restrikes(chs, sr):
            continue
        m = sum(c * c for c in chs)
        w = int(0.01 * sr)
        e = 10 * np.log10(np.convolve(m, np.ones(w) / w, "same")[::w] + 1e-30)
        k = int(np.argmax(e))
        fall = (e[k] - e[min(len(e) - 1, k + 30)]) / 0.3
        if fall < OPEN_DBS:
            out.append((os.path.basename(p), C.norm(C.grid(chs, sr)), fall))
    return out


def render(vel=VEL, secs=4.2):
    import mido
    import blockrender as B
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    for x in (mido.Message("control_change", channel=0, control=0, value=16),
              mido.Message("control_change", channel=0, control=32, value=3),
              mido.Message("program_change", channel=0, program=112),
              mido.Message("note_on", channel=0, note=NOTE, velocity=vel, time=240),
              mido.Message("note_off", channel=0, note=NOTE, velocity=0, time=int(0.29 * 960))):
        t.append(x)
    t.append(mido.MetaMessage("end_of_track", time=int(secs * 960)))
    L, R = B.render(m, "even")[:2]
    return [np.asarray(L, np.float64), np.asarray(R, np.float64)], B.SR


def main(argv):
    import tonelib as T
    rec = strokes()
    print("  open strokes: %s" % ", ".join("%s (%.0f dB/s)" % (n.split("ceng-ceng-")[-1], f) for n, _, f in rec))
    R = np.array([g for _, g, _ in rec])
    # the strokes' mean, each cell where any has it
    Rm = np.where((R > -100).any(0), 10 * np.log10(np.mean(10 ** (np.maximum(R, -200) / 10), 0) + 1e-30), -200.0)
    cls = T.CengCengProperties
    if "--fit" in argv:
        from scipy.optimize import minimize
        maxfev = int(next((a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 200))
        cls.band_trim_db = ()
        x0 = [max(float(getattr(cls, k)), C.FLOOR.get(k, 1e-3)) for k in C.PARAMS]
        best = [1e9, None, None]

        def f(z):
            vals = np.exp(z) * np.array(x0)
            C.set_params(cls, vals)
            e, trim = C.score([C.norm(C.grid(*render()))], [Rm])
            if e < best[0]:
                best[:] = [e, vals, trim]
                print("   %6.3f dB  %s  trim %s" % (e, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(C.PARAMS, vals)),
                                                    " ".join("%+.1f" % t for t in trim)), flush=True)
            return e
        n = len(C.PARAMS)
        simplex = np.vstack([np.zeros(n)] + [0.47 * np.eye(n)[i] * (1 if i % 2 else -1) for i in range(n)])
        minimize(f, np.zeros(n), method="Nelder-Mead",
                 options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                          "adaptive": True})
        e, vals, trim = best
        print("  best %.3f dB" % e)
        for k, v in zip(C.PARAMS, vals):
            print("    %s = %.4g" % (k, v))
        print("    band_trim_db = %s" % (tuple((int(round(c)), round(float(t), 1)) for c, t in zip(C.CENTRES, trim)),))
        return 0
    M = C.norm(C.grid(*render()))
    e, trim = C.score([M], [Rm])
    print("  ours as it is: %.2f dB rms (band trim %s)" % (e, " ".join("%+.1f" % t for t in trim)))
    for nm, g in (("strokes", Rm), ("ours", M)):
        print("  %s" % nm)
        for i, c in enumerate(C.CENTRES):
            print("   %6.0f Hz " % c + " ".join("%6.1f" % v if v > -150 else "    --" for v in g[i]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
