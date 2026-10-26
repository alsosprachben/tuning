#!/usr/bin/env python3
"""Fit a synth panel's UNISON (moog.unison: a supersaw) to a player's recording
of one: the CC0 "Roland Tekno Lead 1 C" (Freesound 573045, Sorinious_Genious,
a JD-Xi's SuperSaw lead held on C4; ~/Documents/refs/supersaw_jdxi, sources.md
-- a non-sampled Roland synth, player-recorded: allowed, Ben 2026-10-26).

A supersaw's saws are not fixed lines in this take: every harmonic is a
continuous smear ~+/-65 cents wide (each saw drifting), its centre wobbling
~9 cents. So the fit is on STATISTICS, measured the same way on both:

  profile   each harmonic's power against cents re its centre (5-cent bins,
            -90 ... +90), harmonics 2-5 averaged: the spread, the mix
            (centre against sides) and the drift together
  shimmer   each harmonic's level over 50 ms frames, its std in dB,
            harmonics 2-10 averaged: how the voices beat
  tilt      the harmonics' levels 1-40 re the first: the filter
  stereo    left/right correlation

    python3 examples/supersaw_fit.py --ref             the reference's numbers
    python3 examples/supersaw_fit.py                   fit; prints the spec
    python3 examples/supersaw_fit.py --demo OUT        the take, ours, trance chords
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE]
REF = os.path.expanduser("~/Documents/refs/supersaw_jdxi/573045__sorinious_genious__roland-tekno-lead-1-c.wav")
SR = 44100
F0 = 261.63
BINS = np.arange(-90.0, 91.0, 5.0)


def load(path):
    raw = subprocess.run(['sox', path, '-t', 'f32', '-r', str(SR), '-c', '2', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)


def stats(x, t0, t1, f0=F0):
    """(profile dB over BINS, shimmer dB, tilt dB [40], L/R correlation)."""
    L, R = x[int(t0 * SR):int(t1 * SR), 0], x[int(t0 * SR):int(t1 * SR), 1]
    m = 0.5 * (L + R)
    n = len(m)
    S = np.abs(np.fft.rfft(m * np.blackman(n))) ** 2
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    prof = np.zeros(len(BINS))
    # (harmonics 2-5 only: from the 6th the next one is under 300 cents away,
    # and a +/-100-cent window reads its skirt as this one's)
    for k in range(2, 6):
        b = (fr > k * f0 * 2 ** (-100 / 1200.0)) & (fr < k * f0 * 2 ** (100 / 1200.0))
        c = 1200.0 * np.log2(fr[b] / (k * f0))
        p = S[b] / S[b].sum()
        c = c - (c * p).sum()                    # re the harmonic's own centre
        prof += np.histogram(c, bins=np.append(BINS - 2.5, BINS[-1] + 2.5), weights=p)[0]
    prof = 10.0 * np.log10(prof / prof.max() + 1e-6)
    tilt = []
    for k in range(1, 41):
        b = (fr > k * f0 * 2 ** (-100 / 1200.0)) & (fr < k * f0 * 2 ** (100 / 1200.0))
        tilt.append(S[b].sum())
    tilt = 10.0 * np.log10(np.array(tilt) / tilt[0] + 1e-12)
    # shimmer: 50 ms frames, each harmonic's band level
    w = int(0.05 * SR)
    sh = []
    frs = np.fft.rfftfreq(4 * w, 1.0 / SR)
    lv = []
    for i in range(0, n - w, w):
        s = np.abs(np.fft.rfft(m[i:i + w] * np.hanning(w), 4 * w)) ** 2
        lv.append([s[(frs > k * f0 * 0.94) & (frs < k * f0 * 1.06)].sum() for k in range(2, 11)])
    lv = 10.0 * np.log10(np.array(lv) + 1e-20)
    sh = float(np.mean(lv.std(axis=0)))
    return prof, sh, tilt, float(np.corrcoef(L, R)[0, 1])


def show(name, st):
    prof, sh, tilt, cor = st
    print("  %s" % name)
    print("    profile dB @ -90..+90 by 10c:", " ".join("%.0f" % v for v in prof[::2]))
    print("    shimmer %.2f dB   L/R corr %.3f" % (sh, cor))
    print("    tilt dB h1-h40 by 4:", " ".join("%.0f" % v for v in tilt[::4]))


# THE MODEL: GM 81's saw lead (tonelib.MoogSawLead), its ladder open (the
# take's harmonics fall as a saw's, 1/k: -14 dB at h5), the unison over it.
# TWO LAYERS AN OCTAVE APART (Ben: "the reference was 2 octaves, and ours was
# one"): the take holds C3 3 dB under its C4, both supersaws of the same
# spread (~21 cents rms), the C3 layer ~18 cents flat of the C4 -- OSC 2 a saw
# at 16', -18 cents, level 0.8 x -5 dB (amplitudes; -3 read the C3 band 1.8 dB hot,
# the two layers' shared harmonics adding)
PANEL = dict(osc1_wave=0.5, osc1_level=0.8, osc2_wave=0.5, osc2_octave=16, osc2_freq=0.5 - 18.0 / 1400.0,
             osc2_level=0.8 * 10 ** (-5.0 / 20.0), cutoff=1.0, resonance=0.0,
             eg_amount=0.5, kb_track=1.0, a_attack=0.0, a_sustain=1.0)   # EG amount: 0.5 is none
NAMES = ('cents', 'mix', 'drift_cents', 'drift_hz', 'width')


def spec_of(v):
    c, mix, dc, dhz, w = v
    return dict(voices=7, cents=float(c), mix=float(mix), drift_cents=float(dc),
                drift_hz=(0.1, max(0.11, float(dhz))), width=float(w))


def render(spec, sec=15.5):
    import mido
    import blockrender as B
    import patch_map as PM
    cls = PM.property_class_for_program(81)
    cls.moog_unison = spec
    cls.messenger = dict(getattr(cls, '_messenger0', cls.messenger), **PANEL)
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    tr.append(mido.Message('program_change', channel=0, program=81, time=0))
    tr.append(mido.Message('note_on', channel=0, note=60, velocity=100, time=0))
    tr.append(mido.Message('note_off', channel=0, note=60, velocity=0, time=int(sec * 960)))
    tr.append(mido.MetaMessage('end_of_track', time=480))
    L, R = B.render(mf)[:2]
    return np.stack([np.asarray(L, float), np.asarray(R, float)], axis=1)


def loss(st, ref):
    """Profile rms (dB, over the bins the reference holds above -20), shimmer
    and stereo differences, weighted to about equal parts at a fair fit."""
    m = ref[0] > -20.0
    e_p = float(np.sqrt(np.mean((st[0][m] - ref[0][m]) ** 2)))
    return e_p + 2.0 * abs(st[1] - ref[1]) + 20.0 * abs(st[3] - ref[3]), e_p


def main(argv):
    ref = stats(load(REF), 1.0, 15.0)
    if '--ref' in argv:
        show("reference (JD-Xi supersaw, C4, 1-15 s)", ref)
        return 0
    import patch_map as PM
    cls = PM.property_class_for_program(81)
    cls._messenger0 = dict(cls.messenger)
    seen = {}

    def f(v):
        key = tuple(round(x, 3) for x in v)
        if key not in seen:
            st = stats(render(spec_of(v)), 1.0, 15.0)
            seen[key] = (loss(st, ref), st)
            print("  %s  loss %.2f (profile %.2f dB, shimmer %.2f, corr %.3f)"
                  % (" ".join("%s=%.3g" % kv for kv in zip(NAMES, v)), seen[key][0][0], seen[key][0][1],
                     st[1], st[3]), flush=True)
        return seen[key][0][0]
    if '--one' in argv:
        v = [float(a) for a in argv[argv.index('--one') + 1:][:5]]
        f(v)
        show("model", seen[tuple(round(x, 3) for x in v)][1])
        show("reference", ref)
        return 0
    best = None
    # the take's profile is a bell (flat +/-20 cents, -14 dB at +/-50): detuned
    # voices blurred by a fast, deep drift, so the grid starts there
    for c in (25.0, 40.0, 55.0):
        for mix in (0.6, 0.9):
            for dc in (15.0, 30.0):
                v = [c, mix, dc, 4.0, 0.4]
                fv = f(v)
                if best is None or fv < best[0]:
                    best = (fv, v)
    from scipy.optimize import minimize
    r = minimize(f, best[1], method='Nelder-Mead',
                 options=dict(maxfev=int(os.environ.get('FIT_EVALS', '40')), xatol=0.5, fatol=0.05,
                              initial_simplex=None))
    v = r.x
    print("BEST", spec_of(v))
    show("model", seen[tuple(round(x, 3) for x in v)][1] if tuple(round(x, 3) for x in v) in seen
         else stats(render(spec_of(v)), 1.0, 15.0))
    show("reference", ref)
    return 0


if __name__ == "__main__" and "--demo" not in sys.argv:
    sys.exit(main(sys.argv))


# THE FITTED UNISON (TUNING_GPU=1 FIT_EVALS=45 python3 examples/supersaw_fit.py,
# 2026-10-26, with the octave layer): profile 3.0 dB rms, shimmer 2.94 dB
# (3.89), L/R 0.918 (0.914). The layers' harmonics on C3's grid within ~1 dB
# but the two they share most, C5 +2.4 and C6 +1.2 dB
FIT = dict(voices=7, cents=25.31, mix=0.613, drift_cents=30.49, drift_hz=(0.1, 3.955), width=0.3954)


def demo(out):
    """OUT/supersaw_ab.wav: the take's first 8 s, our held C4 (8 s), then four
    bars of trance chords (Am F C G, 132 bpm) on the fitted supersaw."""
    import mido
    import blockrender as B
    import patch_map as PM
    cls = PM.property_class_for_program(81)
    cls.moog_unison = FIT
    cls.messenger = dict(cls.messenger, **PANEL)
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=int(60e6 / 132), time=0))
    tr.append(mido.Message('program_change', channel=0, program=81, time=0))
    ev = [(0.0, 60, 1), (8.0 * 132 / 60, 60, 0)]
    b0 = 9.0 * 132 / 60
    for i, ch in enumerate(((57, 60, 64, 69), (53, 57, 60, 65), (48, 55, 60, 64), (55, 59, 62, 67))):
        for j in range(8):                 # offbeat stabs, eighth notes
            t = b0 + 4 * i + 0.5 * j + 0.25
            for n in ch:
                ev += [(t, n, 1), (t + 0.22, n, 0)]
    ev.sort(key=lambda e: (e[0], e[2]))
    now = 0
    for t, n, on in ev:
        tk = int(round(t * 480))
        tr.append(mido.Message('note_on' if on else 'note_off', channel=0, note=n, velocity=100 if on else 0,
                               time=tk - now))
        now = tk
    tr.append(mido.MetaMessage('end_of_track', time=960))
    L, R = B.render(mf)[:2]
    ours = np.stack([np.asarray(L, float), np.asarray(R, float)], axis=1)
    ref = load(REF)[:int(8.0 * SR)]
    rms = lambda a: np.sqrt(np.mean(a[int(1 * SR):int(7 * SR)] ** 2))
    ref = ref * rms(ours[:int(8 * SR)]) / rms(ref)
    gap = np.zeros((int(0.8 * SR), 2))
    y = np.concatenate([ref, gap, ours])
    y *= 10 ** (-1 / 20.0) / np.abs(y).max()
    os.makedirs(out, exist_ok=True)
    f = os.path.join(out, "supersaw_ab.wav")
    B.write_wav(f, y[:, 0], y[:, 1])
    return f


if __name__ == "__main__" and "--demo" in sys.argv:
    print("  " + demo(sys.argv[sys.argv.index("--demo") + 1]))
