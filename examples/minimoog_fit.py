#!/usr/bin/env python3
"""Fit a Moog panel to a Minimoog Model D's held notes: the SC-88 map's MG tones.

    python3 -I examples/minimoog_fit.py [REFDIR]     # REFDIR ~/Documents/refs/minimoog
    python3 -I examples/minimoog_fit.py --render [REFDIR]   # sc88_synth.MINIMOOG, rendered

THE TAKES (Garzul, Freesound, CC0; sources.md): one patch -- "Badass Minimoog
bass", his note: the same patch at both -- held at C1 (213900, 32.8 Hz) and
at C4 (213899, labelled C7, 263.2 Hz). Both read as two oscillators an octave
apart, the upper the louder: the odd harmonics stand 15-20 dB under the even
at C1, 15 dB under at C4 -- the Minimoog bass, 8' under 4' (16' under 8' on
its own footage). Neither beats faster than 0.2 Hz: the two in tune.

THE MEASURE: each harmonic's energy (within 0.6% of k f0) over the held
stretch -- C1 from 0.5 to 5 s, C4 from 4.5 to 9.5 s (it swells and opens over
its first 4 s; held, it is steady) -- in dB re its strongest. C1's
fundamental is left out: 12 dB under C4's against the same mixer, which is
the recording chain's low end (33 Hz), not the patch. Harmonics more than 40
dB down are the noise floor in both and are left out too.

THE MODEL: the engine's own spectrum, not a render -- moog.partials (the
oscillators' exact series) times the ladder's |H| at the cutoff the contour
holds (moog.ladder_gain, moog.output_gain), each harmonic the power sum of the
partials on it. Both notes share the panel; KB TRACKING is tried off and on
(the hardware's two settings), which the two notes three octaves apart
decide. Searched: both waves, OSC 2's level, the cutoff, the resonance
(Nelder-Mead from a grid of starts); the rms dB error is printed per note.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import moog      # noqa: E402

REF = os.path.expanduser("~/Documents/refs/minimoog")
# (file glob, nominal f0, held stretch s, harmonics, first harmonic counted)
TAKES = (("bass/213900_*.wav", 32.83, (0.5, 5.0), 48, 2),
         ("bass/213899_*.wav", 263.4, (4.5, 9.5), 16, 1))
FLOOR_DB = -40.0


def read(path):
    w = wave.open(path)
    r, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    b = np.frombuffer(w.readframes(w.getnframes()), np.uint8)
    if sw == 3:
        b = b.reshape(-1, 3).astype(np.int32)
        a = (b[:, 0] << 8 | b[:, 1] << 16 | b[:, 2] << 24).astype(float) / 2 ** 31
    else:
        a = np.frombuffer(b.tobytes(), {2: '<i2', 4: '<i4'}[sw]).astype(float) / (2 ** (8 * sw - 1))
    return a.reshape(-1, ch).mean(1), r


def harmonics(x, r, f0, n):
    """(f0 refined, dB of harmonics 1..n re the strongest)."""
    N = len(x)
    S = np.abs(np.fft.rfft(x * np.blackman(N), 4 * N)) ** 2
    F = np.fft.rfftfreq(4 * N, 1 / r)

    def band(k, f):
        return S[np.abs(F - k * f) < max(0.6, 0.006 * k * f)].sum()
    f0 = max(np.linspace(f0 * 0.99, f0 * 1.01, 401),
             key=lambda f: sum(np.log(band(k, f) + 1e-30) for k in range(1, 9)))
    h = np.array([10 * np.log10(band(k, f0) + 1e-30) for k in range(1, n + 1)])
    return f0, h - h.max()


def model(panel, f0, n):
    """The engine's held spectrum at harmonics 1..n of f0, dB re the strongest."""
    p = moog.partials(panel, f0)
    fc = (moog.knob_cutoff(panel['cutoff']) * moog.cutoff_at(1.0, f0, panel['kb_track'])
          * 2.0 ** (moog.eg_octaves(panel['eg_amount']) * moog.sustain_level(panel['f_sustain'])))
    k = moog.knob_k(panel['resonance'])
    pw = np.zeros(n)
    for _osc, _h, f, a, _ph in p:
        j = int(round(f / f0))
        if 1 <= j <= n and abs(f - j * f0) < 0.01 * j * f0:
            g = moog.ladder_gain(f, max(fc, 1.0), k, int(panel['mode']), bool(panel['res_bass']))
            pw[j - 1] += (a * g * moog.output_gain(f)) ** 2
    h = 10 * np.log10(pw + 1e-30)
    return h - h.max()


# the patch's fixed part: OSC 1 at 8', OSC 2 an octave over it, in tune; the
# contour held open (EG AMOUNT at its detent: the cutoff is the knob)
BASE = dict(moog.PANEL, osc1_octave=8, osc2_octave=4, osc2_freq=0.5, sub_level=0.0, noise_level=0.0,
            osc1_level=0.8, eg_amount=0.5, mode=0, res_bass=False, sync=False, mod_amount=0.5,
            lfo1_depth=0.0)
KEYS = ("osc1_wave", "osc2_wave", "osc2_level", "cutoff", "resonance")
LO = np.array([0.2, 0.2, 0.0, 0.3, 0.0])
HI = np.array([1.0, 1.0, 1.0, 1.0, 0.75])


def panel_of(v, track):
    v = np.clip(v, LO, HI)
    return dict(BASE, kb_track=track, **{k: float(x) for k, x in zip(KEYS, v)})


def errors(panel, meas):
    out = []
    for f0, h, n, first in meas:
        m = model(panel, f0, n)
        sel = np.arange(n) >= first - 1
        sel &= (h > FLOOR_DB) | (m > FLOOR_DB)
        d = (np.maximum(m, FLOOR_DB) - np.maximum(h, FLOOR_DB))[sel]
        out.append(d - d.mean())        # each take's own level
    return out


def cost(v, track, meas):
    return float(np.sqrt(np.mean(np.concatenate(errors(panel_of(v, track), meas)) ** 2)))


def fit(meas):
    best = None
    for track in (0.0, 1.0):
        for w1 in (0.35, 0.5, 0.65):
            for w2 in (0.35, 0.5, 0.65):
                for cut in (0.5, 0.6, 0.7):
                    v0 = np.array([w1, w2, 0.8, cut, 0.1])
                    r = minimize(cost, v0, args=(track, meas), method="Nelder-Mead",
                                 options=dict(xatol=1e-3, fatol=1e-3, maxiter=600))
                    if best is None or r.fun < best[0]:
                        best = (r.fun, track, np.clip(r.x, LO, HI))
    return best


def render(panel, notes, prog=38, held=5.5):
    """The panel through the renderer itself (the kernel, not the model): each
    note held alone, a second apart; the wav's path."""
    import mido
    d = tempfile.mkdtemp(prefix="minimoog_")
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    t.append(mido.Message('program_change', program=prog, time=0))
    for n in notes:
        t.append(mido.Message('note_on', note=n, velocity=100, time=480))
        t.append(mido.Message('note_off', note=n, time=int(held * 960)))
    mid, out = os.path.join(d, "n.mid"), os.path.join(d, "n.wav")
    m.save(mid)
    env = dict(os.environ, TUNING_MOOG_PANEL=json.dumps(panel), TUNING_REFLECT="0")
    subprocess.run([sys.executable, os.path.join(HERE, "blockrender.py"), mid, out, "even"],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    return out


def check(ref):
    """sc88_synth.MINIMOOG rendered at C1 and C4, measured as the takes are."""
    from sc88_synth import MINIMOOG
    panel = dict(BASE, **MINIMOOG)
    x, r = read(render(panel, (24, 60)))
    held = 5.5
    for i, (pat, f0, _span, n, first) in enumerate(TAKES):
        y, ry = read(glob.glob(os.path.join(ref, pat))[0])
        t0, t1 = _span
        fr, hr = harmonics(y[int(t0 * ry):int(t1 * ry)], ry, f0, n)
        a = 0.5 + i * (held + 0.5) + 0.5
        f, h = harmonics(x[int(a * r):int((a + 4.0) * r)], r, fr, n)
        sel = (np.arange(n) >= first - 1) & ((hr > FLOOR_DB) | (h > FLOOR_DB))
        d = (np.maximum(h, FLOOR_DB) - np.maximum(hr, FLOOR_DB))[sel]
        print("%s rendered at %.2f Hz: rms %.2f dB against the take" % (pat, f, np.sqrt(np.mean((d - d.mean()) ** 2))))
        for j in range(0, n, 16):
            print("  h%-3d take " % (j + 1) + ' '.join('%5.0f' % v for v in hr[j:j + 16]))
            print("       ours " + ' '.join('%5.0f' % v for v in h[j:j + 16]))
    return 0


def main(argv):
    if '--render' in argv:
        rest = [a for a in argv[1:] if a != '--render']
        return check(rest[0] if rest else REF)
    ref = argv[1] if len(argv) > 1 else REF
    meas = []
    for pat, f0, (t0, t1), n, first in TAKES:
        x, r = read(glob.glob(os.path.join(ref, pat))[0])
        f, h = harmonics(x[int(t0 * r):int(t1 * r)], r, f0, n)
        meas.append((f, h, n, first))
        print("%s  f0 %.2f Hz" % (pat, f))
    err, track, v = fit(meas)
    panel = panel_of(v, track)
    print("fit: rms %.2f dB, kb_track %d" % (err, track))
    print("  " + ", ".join("%s=%.3f" % (k, panel[k]) for k in KEYS),
          " (cutoff %.0f Hz at middle C)" % moog.knob_cutoff(panel['cutoff']))
    for (f0, h, n, first), e in zip(meas, errors(panel, meas)):
        m = model(panel, f0, n)
        print("%.1f Hz: rms %.2f dB" % (f0, np.sqrt(np.mean(e ** 2))))
        for i in range(0, n, 16):
            print("  h%-3d take " % (i + 1) + ' '.join('%5.0f' % x for x in h[i:i + 16]))
            print("       ours " + ' '.join('%5.0f' % x for x in m[i:i + 16]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
