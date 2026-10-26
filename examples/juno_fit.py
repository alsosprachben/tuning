#!/usr/bin/env python3
"""Fit a Moog panel to a Roland Juno-6's notes: the SC-88 map's JUNO tones.

    python3 -I examples/juno_fit.py PATCH [REFDIR]   # REFDIR ~/Documents/refs/juno6
    PATCH: pw-pluck, pulse-bass, saw-bass-split, open-pad; or --sine (sine-pluck),
    or --chorus (the Open Pad's chorus, from its held notes)

THE TAKES (Modular Samples, Freesound, CC0; sources.md): Juno-6 patches
sampled key by key, C2 to C7, each note alone. The Juno is one DCO a voice --
its pulse (the width the PWM moves), its saw and a square SUB an octave under,
all locked in tune, no drift -- into the 4-pole IR3109 low-pass, one ADSR for
the filter and the amplifier. On the engine: OSC 1 the pulse (LFO 1 moves
OSC 1's wave, which is PWM), OSC 2 the saw at exact unison, the SUB a square
(SUB WAVE 0.3: its harmonics 1/k, odd only).

THE FIT, three stages, every C of the take at once (Saw Bass Split only to
B3: its upper keys all sound C1):
  1 THE OSCILLATORS AND RESONANCE: the RANGE (8' or 16': three of the
    patches play an octave down, every harmonic of the half there, which a
    square sub is not), the pulse's width and level, the saw's, the sub's,
    the resonance -- and, for every note and moment (40 ms frames,
    longer for a low note, from the attack on while it is within 45 dB of its
    peak), the cutoff that best matches that frame's harmonics. The cost is
    the rms dB error over every frame, each at its own best cutoff.
  2 THE FILTER CONTOUR: the cutoffs found, in octaves, against the engine's
    own contour (moog.adsr): cutoff, EG AMOUNT, attack, decay, sustain.
  3 THE AMPLIFIER: each frame's level, less what the cutoff alone makes of
    it, against the amplifier's ADSR (a level per note).
Prints the panel, and the error of each stage.
"""
import glob
import os
import re
import sys
import wave

import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import moog      # noqa: E402

REF = os.path.expanduser("~/Documents/refs/juno6")
# patch -> (notes, the octave the key sounds at re its name: the sub's octave
# is where the lowest partial lies, so the oscillators sound at the key)
NOTES = {"pw-pluck": (36, 48, 60, 72, 84), "pulse-bass": (36, 48, 60, 72, 84),
         "saw-bass-split": (36, 42, 48, 54), "open-pad": (36, 48, 60, 72, 84)}
TIMES = (0.02, 0.06, 0.12, 0.2, 0.3, 0.45, 0.65, 0.9, 1.3, 2.0, 3.0, 5.0, 8.0)
FLOOR_DB = -45.0
FMAX = 6000.0
CUTS = np.linspace(0.15, 1.0, 86)
SUB_SQUARE = 0.3


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


def take(ref, patch, n):
    f = [p for p in glob.glob(os.path.join(ref, patch, "wav", "*.wav")) if re.search(r"-%d-127" % n, p)]
    return read(f[0])


def frames(x, r, f0, foot=8, times=TIMES):
    """[(t, band dB re the frame's strongest, frame level dB)] on the grid of
    harmonics of the sub's frequency (half the oscillators', which sound at
    f0 x 8/foot), from the onset while within FLOOR_DB."""
    fb = f0 * 8.0 / foot / 2.0
    K = int(min(FMAX, r / 2.2) // fb)
    e = np.abs(x)
    on = int(np.argmax(e > e.max() * 0.03))
    W = max(int(0.04 * r), int(4.0 / fb * r))
    peak = None
    out = []
    for t in times:
        i = on + int(t * r)
        if i + W > len(x):
            break
        seg = x[i:i + W]
        lv = 10 * np.log10(np.mean(seg ** 2) + 1e-20)
        peak = lv if peak is None else max(peak, lv)
        if lv < peak + FLOOR_DB:
            break
        S = np.abs(np.fft.rfft(seg * np.hanning(W), 4 * W)) ** 2
        F = np.fft.rfftfreq(4 * W, 1 / r)
        h = np.array([S[np.abs(F - k * fb) < 0.01 * k * fb + 1.0].sum() for k in range(1, K + 1)])
        h = 10 * np.log10(h + 1e-30)
        out.append((t, h - h.max(), lv))
    return out


def panel_of(v, track, foot=8):
    w1, l1, l2, ls, res = np.clip(v, (0.6, 0.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 1.0, 0.65))
    return dict(moog.PANEL, osc1_wave=float(w1), osc1_level=float(l1), osc2_wave=0.5, osc2_level=float(l2),
                osc1_octave=foot, osc2_octave=foot, osc2_freq=0.5, tune=0.5, sync=False, sub_wave=SUB_SQUARE,
                sub_level=float(ls), noise_level=0.0, resonance=float(res), mode=moog.LP4, res_bass=False,
                kb_track=float(track), mod_amount=0.5, lfo1_depth=0.5, eg_amount=0.5)


def spectra(panel, f0, K):
    """The engine's band powers (dB, absolute) at every cutoff of CUTS: (len(CUTS), K)."""
    fb = f0 * 8.0 / panel['osc1_octave'] / 2.0
    p = [(f, a) for osc, _h, f, a, _ph in moog.partials(panel, f0, FMAX)
         if osc in (moog.OSC1, moog.OSC2, moog.SUB)]
    f = np.array([q[0] for q in p])
    a = np.array([q[1] for q in p])
    j = np.round(f / fb).astype(int) - 1
    ok = (j >= 0) & (j < K)
    f, a, j = f[ok], a[ok], j[ok]
    fc = moog.knob_cutoff(0.0) * 2.0 ** (moog.CUT_OCT * CUTS) * moog.cutoff_at(1.0, f0, panel['kb_track'])
    g = moog.ladder_gain(f[None, :], fc[:, None], moog.knob_k(panel['resonance']), int(panel['mode']))
    pw = (a * g * moog.output_gain(f)) ** 2
    out = np.zeros((len(CUTS), K))
    for c in range(len(CUTS)):
        out[c] = np.bincount(j, pw[c], minlength=K)
    return 10 * np.log10(out + 1e-30)


def best_cuts(panel, meas):
    """For every frame: (its best cutoff knob, its error, the model's level there)."""
    res = []
    for f0, fr in meas:
        K = len(fr[0][1])
        sp = spectra(panel, f0, K)
        rel = sp - sp.max(1, keepdims=True)
        lvl = 10 * np.log10((10 ** (sp / 10)).sum(1))
        for t, h, lv in fr:
            sel = (h > FLOOR_DB)[None, :] | (rel > FLOOR_DB)
            d = np.maximum(rel, FLOOR_DB) - np.maximum(h, FLOOR_DB)[None, :]
            err = np.sqrt((np.where(sel, d, 0.0) ** 2).sum(1) / np.maximum(sel.sum(1), 1))
            c = int(np.argmin(err))
            res.append((f0, t, CUTS[c], err[c], lvl[c], lv))
    return res


def cost1(v, track, meas, foot):
    r = best_cuts(panel_of(v, track, foot), meas)
    return float(np.sqrt(np.mean([q[3] ** 2 for q in r])))


def stage1(meas, foot):
    best = None
    for track in (0.0,):                # each frame's cutoff is free: tracking is stage 2's
        for w in (0.68, 0.8, 0.92):
            for l2 in (0.0, 0.6):
                for ls in (0.0, 0.6):
                    v0 = np.array([w, 0.7, l2, ls, 0.15])
                    r = minimize(cost1, v0, args=(track, meas, foot), method="Nelder-Mead",
                                 options=dict(xatol=2e-3, fatol=2e-3, maxiter=250))
                    if best is None or r.fun < best[0]:
                        best = (r.fun, track, r.x)
    return best


def stage2(rows, track=None):
    """The contour on the cutoffs (octaves): cutoff, EG AMOUNT, f attack, decay,
    sustain, and KB TRACKING -- continuous here: the Juno's KYBD slider is,
    and the kernel takes any exponent (moog.cutoff_at). Frames that fit worse
    than 6 dB (a high note down to its fundamental: no cutoff to read) are
    left out. TRACK, if given, is held (an instrument without it)."""
    rows = [q for q in rows if q[3] < 6.0]
    f0 = np.array([q[0] for q in rows])
    t = np.array([q[1] for q in rows])
    o = moog.CUT_OCT * np.array([q[2] for q in rows])
    w = 1.0 / (1.0 + np.array([q[3] for q in rows]))         # trust the frames that fit

    LO, HI = (0.0, 0.5, 0.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)

    def model(v):
        cut, eg, fa, fd, fs, track = v
        env = moog.adsr(t, moog.knob_attack(fa), moog.knob_time(fd), moog.sustain_target(fs), 1.0)
        return (moog.CUT_OCT * cut + track * np.log2(f0 / moog.KB_REF_HZ)
                + moog.eg_octaves(eg) * env)

    if track is not None:
        LO, HI = LO[:5] + (track,), HI[:5] + (track,)

    def cost(v):
        v = np.clip(v, LO, HI)
        return float(np.sqrt(np.sum(w * (model(v) - o) ** 2) / w.sum()))
    best = None
    for eg in (0.6, 0.75, 0.9):
        for fd in (0.2, 0.4, 0.6):
            for fs in (0.0, 0.5, 0.9):
                r = minimize(cost, np.array([0.4, eg, 0.05, fd, fs, 0.5 if track is None else track]),
                             method="Nelder-Mead",
                             options=dict(xatol=1e-3, fatol=1e-4, maxiter=1500))
                if best is None or r.fun < best[0]:
                    best = (r.fun, np.clip(r.x, LO, HI))
    return best


def stage3(rows):
    """The amplifier: frame level less the model's level at that cutoff, a gain
    per note -- over each note's top 25 dB: the engine's contour closes there
    (moog.adsr, the Messenger's), where the Juno's runs on as a line in dB."""
    top = {f: max(q[5] for q in rows if q[0] == f) for f in set(q[0] for q in rows)}
    rows = [q for q in rows if q[5] > top[q[0]] - 25.0]
    f0 = np.array([q[0] for q in rows])
    t = np.array([q[1] for q in rows])
    d = np.array([q[5] - q[4] for q in rows])
    notes = sorted(set(f0))
    idx = np.array([notes.index(f) for f in f0])

    def resid(v):
        aa, ad, as_ = np.clip(v, 0.0, 1.0)
        env = moog.adsr(t, moog.knob_attack(aa), moog.knob_time(ad), moog.sustain_target(as_), 1.0)
        m = 20 * np.log10(np.maximum(env, 1e-4))
        r = d - m
        g = np.array([r[idx == i].mean() for i in range(len(notes))])
        return r - g[idx]

    def cost(v):
        return float(np.sqrt(np.mean(resid(v) ** 2)))
    best = None
    for ad in (0.2, 0.4, 0.6, 0.8):
        for as_ in (0.0, 0.5, 0.9):
            r = minimize(cost, np.array([0.05, ad, as_]), method="Nelder-Mead",
                         options=dict(xatol=1e-3, fatol=1e-4, maxiter=600))
            if best is None or r.fun < best[0]:
                best = (r.fun, np.clip(r.x, 0.0, 1.0))
    return best


def sine(ref):
    """Sine Pluck: the ladder's own sine. Where it sounds against the key, and its decay."""
    for n in (36, 48, 60, 72, 84):
        x, r = take(ref, "sine-pluck", n)
        e = np.abs(x)
        on = int(np.argmax(e > e.max() * 0.03))
        seg = x[on + int(0.05 * r):on + int(0.55 * r)]
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 17))
        F = np.fft.rfftfreq(1 << 17, 1 / r)
        f = F[np.argmax(S)]
        hop = int(0.05 * r)
        lv = [10 * np.log10(np.mean(x[i:i + hop] ** 2) + 1e-20) for i in range(on, len(x) - hop, hop)]
        lv = np.array(lv)
        k = np.flatnonzero(lv > lv.max() - 30)
        slope = np.polyfit(k * 0.05, lv[k], 1)[0]
        print("  key %d: sine at %.1f Hz (%+.2f semitones re the key), falls %.1f dB/s"
              % (n, f, 12 * np.log2(f / (440 * 2 ** ((n - 69) / 12.0))), slope))
    return 0


def chorus(ref):
    """THE CHORUS, from the Open Pad's held notes (1-9 s): each harmonic's
    pitch and level through a 6% band. Summed to one channel the dry and the
    BBD's copy BEAT, at the copy's frequency offset -- f x the delay's rate of
    change -- so the beat quickens with the harmonic while its depth in cents
    stays: the delay's slope is the rate over the frequency."""
    from scipy.signal import hilbert, butter, sosfiltfilt
    for n in (48, 60):
        x, r = take(ref, "open-pad", n)
        f0 = 440.0 * 2 ** ((n - 69) / 12.0)
        for k in (1, 2, 4, 8):
            fc = k * f0
            sos = butter(4, [fc * 0.97, fc * 1.03], 'bandpass', fs=r, output='sos')
            z = hilbert(sosfiltfilt(sos, x)[int(1.0 * r):int(9.0 * r)])
            d = int(r / 200)
            fi = (np.diff(np.unwrap(np.angle(z))) * r / (2 * np.pi))[::d][5:-5]
            am = 20 * np.log10(np.abs(z) + 1e-12)[::d][5:-5]
            cents = 1200 * np.log2(np.maximum(fi, 1.0) / fc)

            def rate(v):
                v = v - v.mean()
                S = np.abs(np.fft.rfft(v * np.hanning(len(v))))
                F = np.fft.rfftfreq(len(v), 1 / 200.0)
                return F[np.argmax(np.where(F > 0.2, S, 0))]
            br = rate(am)
            print("  key %d h%d %5.0f Hz: pitch sd %4.1f c, beat %5.2f Hz -> slope %.4f"
                  % (n, k, fc, np.std(cents), br, br / fc))
    return 0


def main(argv):
    rest = [a for a in argv[1:] if not a.startswith('--')]
    ref = rest[1] if len(rest) > 1 else REF
    if '--sine' in argv:
        return sine(ref)
    if '--chorus' in argv:
        return chorus(ref)
    patch = rest[0]
    best = None
    for foot in (8, 16):        # the RANGE switch: 16' is the saw an octave down, not the sub
        meas = []
        for n in NOTES[patch]:
            x, r = take(ref, patch, n)
            f0 = 440.0 * 2 ** ((n - 69) / 12.0)
            meas.append((f0, frames(x, r, f0, foot)))
        err, track, v = stage1(meas, foot)
        print("  %d': %.2f dB" % (foot, err), flush=True)
        if best is None or err < best[0]:
            best = (err, track, v, foot, meas)
    err, track, v, foot, meas = best
    panel = panel_of(v, track, foot)
    rows = best_cuts(panel, meas)
    print("   range %d'" % foot)
    print("1  oscillators: rms %.2f dB over %d frames" % (err, len(rows)))
    print("   pulse width %.3f level %.3f, saw %.3f, sub %.3f, resonance %.3f"
          % (panel['osc1_wave'], panel['osc1_level'], panel['osc2_level'], panel['sub_level'], panel['resonance']))
    for f0 in sorted(set(q[0] for q in rows)):
        print("   %6.1f Hz cutoffs: " % f0 + " ".join("%.0f@%.2f" % (moog.knob_cutoff(q[2]) * moog.cutoff_at(1.0, f0, track), q[1])
                                                    for q in rows if q[0] == f0))
    e2, (cut, eg, fa, fd, fs, track) = stage2(rows)
    print("2  filter contour: rms %.2f octaves; cutoff %.3f (%.0f Hz), eg_amount %.3f (%.1f oct), "
          "f_attack %.3f, f_decay %.3f (%.2f s), f_sustain %.3f, kb_track %.2f"
          % (e2, cut, moog.knob_cutoff(cut), eg, moog.eg_octaves(eg), fa, fd, moog.knob_time(fd), fs, track))
    e3, (aa, ad, as_) = stage3(rows)
    print("3  amplifier: rms %.2f dB; a_attack %.3f, a_decay %.3f (%.2f s), a_sustain %.3f"
          % (e3, aa, ad, moog.knob_time(ad), as_))
    out = {k: round(float(panel[k]), 3) for k in ("osc1_wave", "osc1_level", "osc2_level", "sub_level", "resonance")}
    out.update(osc1_octave=foot, osc2_octave=foot)
    out.update(kb_track=round(float(track), 3), cutoff=round(float(cut), 3), eg_amount=round(float(eg), 3),
               f_attack=round(float(fa), 3), f_decay=round(float(fd), 3), f_sustain=round(float(fs), 3),
               a_attack=round(float(aa), 3), a_decay=round(float(ad), 3), a_sustain=round(float(as_), 3))
    print("PANEL %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
