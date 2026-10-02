#!/usr/bin/env python3
"""Fit the Messenger model's knob laws to Ben's own Messenger.

    python3 examples/messenger_fit.py tune [--card 2] [--port Messenger]

The loop: the panel is sent to the hardware as its CC chart (moog.py, the
same messages live sends), notes are played over MIDI, and the Messenger's
audio is recorded back through a USB mixer (arecord on the card); what it
does is measured and set against what the model's law says. One test per
law, each a short scripted run ending in a fitted constant -- the
calibration moog.py's estimates have been waiting for.

PITCH IS THE LOWEST STRONG HARMONIC, not the strongest peak near where the
note should be: a saw's second harmonic is half its first, and the first
measurement here read a note an octave low as one in tune -- that is how the
octave switch's chart was found to be backwards (moog.FOOT_CC).

Tests:
  tune   TUNE across its travel: cents per unit of knob, and where its zero
         is against A440 (the model: +-moog.SEMIS, centred).
  freq   OSC 2 FREQ, the same way, OSC 2 alone.
  wave   WAVESHAPE: each knob position's harmonics against the model's
         spectra (moog.osc_spectrum), and which model position each matches.
  cutoff CUTOFF: a saw on A2, key tracking off; each setting's harmonics over
         the open filter's, fitted with the ladder (moog.ladder_gain) for its
         corner -- the knob's law (the model: 20 Hz * 1000^v).
  res    RESONANCE at a fixed corner: the ladder's feedback k fitted at each
         setting (the model: K_MAX * v), and where it starts to sing alone.
  amp    the amp contour's ATTACK, DECAY and RELEASE times against the knob
         (the model: 1 ms * 10^(4v); attack reaches the top at A, decay and
         release are exponentials of time constant D/4, R/4).
  lfo    LFO 1 on OSC 2's pitch: its RATE law (0.05 Hz * 240^v) and how far
         DEPTH swings the pitch (LFO_PITCH_OCTAVES at full).
  mod    the MOD section's F ENV -> OSC 2 FREQ at the contour's sustain: how
         far MOD AMOUNT moves OSC 2 (MOD_PITCH_OCTAVES at full).
  fm     1 -> 2 FM: triangles, carrier and modulator on the key; the
         hardware's spectrum at each MOD AMOUNT against the model rendered at
         trial values of FM_INDEX_MAX -- the one that matches is the fit.
  eg     EG AMOUNT: the filter contour held at sustain 1.0, the corner's shift
         from where CUTOFF alone puts it, per setting (the model: +-7 octaves
         about 0.5).
"""
import os
import subprocess
import sys
import time

import mido
import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import moog as MG

SR = 48000
OUT = os.path.join(os.environ.get('TMPDIR', '/tmp'), 'messenger_fit')

# A PLAIN PANEL: one saw on the key, everything else out of the way -- the
# filter open, no contour, no modulation -- so a measurement sees one law.
# THE FILTER CONTOUR IS TAKEN OUT, not left at sustain: held at 1.0 with EG
# AMOUNT at the model's centre it lifted every measured corner 3.8 octaves --
# the hardware's EG AMOUNT is not centred where the model says (see 'eg').
CAL = dict(MG.PANEL, osc1_octave=8, osc1_wave=MG.SAW, osc1_level=1.0, osc2_level=0.0,
           sub_level=0.0, noise_level=0.0, cutoff=1.0, resonance=0.0, eg_amount=0.5,
           kb_track=1.0, mode=MG.LP4, f_attack=0.0, f_decay=0.3, f_sustain=0.0,
           a_attack=0.0, a_sustain=1.0, a_release=0.3, tune=0.5, sync=False,
           mod_amount=0.5, lfo1_depth=0.5)


# THE MIXER'S CAPTURE COMES ALIVE about a second after arecord starts: the
# file is digital zero until 1.01 s, whatever was played before it. A note
# sent in that second loses its start -- a slow attack read as instant, until
# it was seen that every "instant" note was the first of its take.
PREROLL = 1.0
# WHERE BEN'S MESSENGER PLAYS against its key, once the chart has put its
# TUNE on A440 (moog.MESSENGER_TUNE_CENTS): the harmonic probes look for it
# there. ('tune' reads it; before the chart's trim it was 36.7-40.5 sharp.)
TUNE_CENTS = 0.0


class Rig(object):
    """The Messenger on MIDI and the mixer's card, recording one take at a time."""

    def __init__(self, port='Messenger', card=2, firmware='1.0.7+'):
        name = next((n for n in mido.get_output_names() if port.lower() in n.lower()), None)
        if name is None:
            sys.exit('no MIDI output matches %r' % port)
        self.out = mido.open_output(name)
        self.card, self.firmware = card, firmware
        os.makedirs(OUT, exist_ok=True)

    def panel(self, pan, knobs=None):
        for cc, v in MG.messenger_messages(pan, self.firmware, knobs):
            self.out.send(mido.Message('control_change', channel=0, control=cc, value=v))
            time.sleep(0.002)

    def take(self, name, seconds, play):
        """Record `seconds` while play(rig) runs; returns the mono take. Each
        note() is logged as its time into the take, so a test slices notes by
        what it PLAYED -- an onset detector counted one note twice."""
        path = os.path.join(OUT, name + '.wav')
        rec = subprocess.Popen(['arecord', '-q', '-D', 'plughw:%d,0' % self.card, '-f', 'S16_LE',
                                '-r', str(SR), '-c', '2', '-d', str(int(np.ceil(seconds + PREROLL))), path])
        self.t0 = time.monotonic()
        self.played = []
        time.sleep(0.5 + PREROLL)
        play(self)
        rec.wait()
        sr, x = wavfile.read(path)
        return x.astype(float).mean(axis=1) / 32768.0

    def note(self, n, dur, vel=110):
        self.played.append(time.monotonic() - self.t0)
        self.out.send(mido.Message('note_on', channel=0, note=n, velocity=vel))
        time.sleep(dur)
        self.out.send(mido.Message('note_off', channel=0, note=n, velocity=0))


def onsets(y, frac=0.2):
    env = np.sqrt(np.convolve(y ** 2, np.ones(2400) / 2400.0, 'same'))
    return np.flatnonzero(np.diff((env > env.max() * frac).astype(int)) == 1) / float(SR)


def pitch(seg):
    """The lowest strong harmonic, refined between bins: the note's own f0."""
    N = 1 << 19
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / SR)
    pk, _ = find_peaks(X, height=X.max() * 0.15, distance=50)
    pk = pk[f[pk] > 20.0]
    if not len(pk):
        return float('nan')                 # silence, or nothing pitched
    i = int(pk.min())
    y0, y1, y2 = np.log(X[i - 1:i + 2])
    return f[i] + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) * (f[1] - f[0])


def test_tune(rig):
    vals = [round(v, 2) for v in np.linspace(0.0, 1.0, 11)]
    rig.panel(CAL)
    rig.out.send(mido.Message('pitchwheel', channel=0, pitch=0))
    time.sleep(0.3)

    def play(r):
        for v in vals:
            r.panel(dict(CAL, tune=v), knobs=('tune',))
            time.sleep(0.15)
            r.note(69, 0.8)
            time.sleep(0.25)
    y = rig.take('tune', len(vals) * 1.2 + 1.5, play)
    ts = rig.played
    rows = []
    for v, t in zip(vals, ts):
        f0 = pitch(y[int((t + 0.2) * SR):int((t + 0.7) * SR)])
        rows.append((v, f0, 1200.0 * np.log2(f0 / 440.0)))
        print('  TUNE %.2f   %8.2f Hz   %+8.1f cents from A440' % rows[-1])
    v = np.array([r[0] for r in rows]) - 0.5
    c = np.array([r[2] for r in rows])
    k, c0 = np.polyfit(v, c, 1)
    res = c - (k * v + c0)
    print('  fit: %.1f cents per unit of knob -> +-%.2f semitones at the ends (the model: +-%g);'
          % (k, k * 0.5 / 100.0, MG.SEMIS))
    print('       centre %+.1f cents from A440; worst departure from a straight line %.1f cents'
          % (c0, np.abs(res).max()))


def harmonics(seg, f0, K, sr=SR):
    """|A_k| of harmonics 1..K of a note at f0 (each the peak near k f0).
    `sr` the take's own rate: the file renderer's is 44.1 kHz, the mixer's
    48 -- read at the wrong one, every frequency is off by 9%."""
    N = 1 << 19
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    out = []
    for k in range(1, K + 1):
        b = (f > k * f0 * 0.985) & (f < k * f0 * 1.015)
        out.append(X[b].max() if b.any() else 0.0)
    return np.array(out)


def sweep_pitch(rig, name, knob, base, vals, note=69):
    rig.panel(base)
    rig.out.send(mido.Message('pitchwheel', channel=0, pitch=0))
    time.sleep(0.3)

    def play(r):
        for v in vals:
            r.panel(dict(base, **{knob: v}), knobs=(knob,))
            time.sleep(0.15)
            r.note(note, 0.8)
            time.sleep(0.25)
    y = rig.take(name, len(vals) * 1.2 + 1.5, play)
    return [(v, pitch(y[int((t + 0.2) * SR):int((t + 0.7) * SR)])) for v, t in zip(vals, rig.played)]


def fit_semis(rows, ref, label):
    for v, f0 in rows:
        print('  %s %.2f   %8.2f Hz   %+8.1f cents' % (label, v, f0, 1200.0 * np.log2(f0 / ref)))
    v = np.array([r[0] for r in rows]) - 0.5
    c = np.array([1200.0 * np.log2(r[1] / ref) for r in rows])
    k, c0 = np.polyfit(v, c, 1)
    print('  fit: +-%.2f semitones at the ends (the model: +-%g); centre %+.1f cents; '
          'worst off a straight line %.1f cents' % (k * 0.5 / 100.0, MG.SEMIS, c0,
                                                    np.abs(c - (k * v + c0)).max()))
    return k * 0.5 / 100.0, c0


def test_freq(rig):
    vals = [round(v, 2) for v in np.linspace(0.0, 1.0, 11)]
    base = dict(CAL, osc1_level=0.0, osc2_level=1.0, osc2_wave=MG.SAW, osc2_octave=8)
    fit_semis(sweep_pitch(rig, 'freq', 'osc2_freq', base, vals), 440.0, 'OSC 2 FREQ')


def test_wave(rig):
    vals = [round(v, 2) for v in np.linspace(0.0, 1.0, 21)]
    note, K = 45, 16                          # A2: sixteen harmonics well inside the band
    rig.panel(CAL)
    time.sleep(0.3)

    def play(r):
        for v in vals:
            r.panel(dict(CAL, osc1_wave=v), knobs=('osc1_wave',))
            time.sleep(0.15)
            r.note(note, 0.8)
            time.sleep(0.25)
    y = rig.take('wave', len(vals) * 1.2 + 1.5, play)
    grid = np.linspace(0.0, 1.0, 401)
    # the model's spectra at every knob position, normalised to the fundamental
    # ... and to the measured line's own tilt: the open ladder at 20 kHz
    model = []
    for g in grid:
        a = 2.0 * np.abs(MG.osc_spectrum(g, K))
        model.append(a / max(a[0], 1e-9))
    model = np.array(model)
    f0 = 110.0 * 2 ** (0.0)          # the key; the measured pitch is used below
    print('  knob   h2/h1  h3/h1  h4/h1  h5/h1    best model position (dB rms off)')
    out = []
    for v, t in zip(vals, rig.played):
        seg = y[int((t + 0.2) * SR):int((t + 0.7) * SR)]
        fp = pitch(seg)
        h = harmonics(seg, fp, K)
        h = h / max(h[0], 1e-12)
        lm = 20 * np.log10(np.maximum(model, 1e-4))
        lh = 20 * np.log10(np.maximum(h, 1e-4))
        err = np.sqrt(((lm - lh) ** 2).mean(axis=1))
        j = int(np.argmin(err))
        out.append((v, grid[j], err[j]))
        print('  %.2f   %5.2f  %5.2f  %5.2f  %5.2f    %.3f (%.1f)' % (v, h[1], h[2], h[3], h[4], grid[j], err[j]))
    return out


def held(rig, name, base, knob, vals, note, dur=0.9):
    """One held note per value of `knob`; each note's steady middle."""
    rig.panel(base)
    time.sleep(0.3)

    def play(r):
        for v in vals:
            r.panel(dict(base, **{knob: v}), knobs=(knob,))
            time.sleep(0.15)
            r.note(note, dur)
            time.sleep(0.25)
    y = rig.take(name, len(vals) * (dur + 0.45) + 1.5, play)
    return [(v, y[int((t + 0.25) * SR):int((t + dur - 0.1) * SR)]) for v, t in zip(vals, rig.played)]


def fit_ladder(h, f, fc0=None, k0=None):
    """The corner and feedback whose |H| best fits the measured gains h at
    frequencies f (log error), by search. Returns (fc, k, dB rms off)."""
    lh = 20 * np.log10(np.maximum(h, 1e-6))
    best = None
    fcs = np.geomspace(30.0, 18000.0, 400) if fc0 is None else [fc0]
    ks = [0.0] if k0 is not None and k0 == 0 else (np.linspace(0.0, 3.99, 134) if k0 is None else [k0])
    for fc in fcs:
        for k in ks:
            lm = 20 * np.log10(np.maximum(MG.ladder_gain(f, fc, k), 1e-6))
            # ABOVE THE FLOOR ONLY: the hardware's own noise sits ~60 dB under
            # the open filter, and fitting a corner to it put the low settings
            # anywhere -- the low end looked unmeasurable until it was left out
            w = (lh > -45)
            e = np.sqrt(((lm - lh)[w] ** 2).mean())
            if best is None or e < best[2]:
                best = (fc, k, e)
    return best


def psd(seg, nper=4096):
    """Welch power spectral density: (f, P)."""
    from scipy.signal import welch
    return welch(seg, SR, nperseg=nper)


def test_cutoff(rig):
    """By NOISE, not a saw's harmonics: white noise through the ladder over
    the open ladder's noise is |H|^2 at every frequency, so the corner can be
    fitted where a saw's harmonics have sunk into the floor (low settings) or
    all lie under it (high)."""
    base = dict(CAL, kb_track=0.0, resonance=0.0, osc1_level=0.0, noise_level=1.0)
    vals = [1.0] + [round(v, 2) for v in np.linspace(0.0, 0.6, 13)]
    takes = held(rig, 'cutoff', base, 'cutoff', vals, 69, dur=1.6)
    f, P0 = psd(takes[0][1])
    band = (f > 25.0) & (f < 16000.0)
    open_h = MG.ladder_gain(f, MG.knob_cutoff(1.0), 0.0)
    rows = []
    print('  knob   fitted corner   (model)      dB rms off')
    for v, seg in takes[1:]:
        _f, P = psd(seg)
        h = np.sqrt(P[band] / np.maximum(P0[band], 1e-30)) * open_h[band]
        fc, _k, e = fit_ladder(h, f[band], k0=0)
        rows.append((v, fc, e))
        print('  %.2f   %9.1f Hz   (%7.1f)   %.1f' % (v, fc, MG.knob_cutoff(v), e))
    ok = [r for r in rows if r[2] < 3.0 and 40.0 < r[1] < 15000.0]
    v = np.array([r[0] for r in ok]); lf = np.log2([r[1] for r in ok])
    print('  (the model now: %s)' % ' '.join('%.0f' % MG.knob_cutoff(x) for x in v))
    v = np.array([r[0] for r in ok]); lf = np.log2([r[1] for r in ok])
    a, b = np.polyfit(v, lf, 1)
    print('  fit over %d good points: corner = %.1f Hz * 2^(%.2f v): %.1f Hz at 0, %.0f Hz at 1 '
          '(the model: 20 Hz * 2^(%.2f v)); worst off the line %.2f octaves'
          % (len(ok), 2 ** b, a, 2 ** b, 2 ** (a + b), np.log2(1000), np.abs(lf - (a * v + b)).max()))
    return rows


def test_cutoff_saw(rig):
    note, f_key, K = 45, 110.0, 80
    base = dict(CAL, kb_track=0.0, resonance=0.0, eg_amount=0.5)
    vals = [1.0] + [round(v, 2) for v in np.linspace(0.25, 0.85, 13)]
    takes = held(rig, 'cutoff', base, 'cutoff', vals, note)
    ref_seg = takes[0][1]
    f0 = pitch(ref_seg)
    ref = harmonics(ref_seg, f0, K)
    fk = f0 * np.arange(1, K + 1)
    ref = ref / MG.ladder_gain(fk, MG.knob_cutoff(1.0), 0.0)      # the open filter's own tilt out
    rows = []
    print('  knob   fitted corner   (model)      dB rms off')
    for v, seg in takes[1:]:
        h = harmonics(seg, f0, K) / np.maximum(ref, 1e-12)
        fc, _k, e = fit_ladder(h, fk, k0=0)
        rows.append((v, fc))
        print('  %.2f   %9.1f Hz   (%7.1f)   %.1f' % (v, fc, MG.knob_cutoff(v), e))
    v = np.array([r[0] for r in rows]); lf = np.log2([r[1] for r in rows])
    a, b = np.polyfit(v, lf, 1)
    print('  fit: corner = %.1f Hz * 2^(%.2f v) -> %.1f Hz to %.0f Hz over the knob '
          '(the model: 20 Hz to 20 kHz, %.2f octaves)' % (2 ** b, a, 2 ** b, 2 ** (a + b), np.log2(1000)))
    return 2 ** b, a


def test_res(rig):
    note, K = 45, 80
    base = dict(CAL, kb_track=0.0, cutoff=0.55, eg_amount=0.5)
    vals = [round(v, 2) for v in np.linspace(0.0, 0.9, 10)]
    takes = held(rig, 'res', dict(base, resonance=0.0, cutoff=1.0), 'resonance', [0.0], note)
    f0 = pitch(takes[0][1])
    fk = f0 * np.arange(1, K + 1)
    ref = harmonics(takes[0][1], f0, K) / MG.ladder_gain(fk, MG.knob_cutoff(1.0), 0.0)
    takes = held(rig, 'res', base, 'resonance', vals, note)
    h0 = harmonics(takes[0][1], f0, K) / np.maximum(ref, 1e-12)
    fc, _k, e = fit_ladder(h0, fk, k0=0)
    print('  the corner at CUTOFF 0.55, no resonance: %.1f Hz (%.1f dB rms off)' % (fc, e))
    print('  knob   fitted k   (model)   dB rms off')
    rows = []
    for v, seg in takes:
        h = harmonics(seg, f0, K) / np.maximum(ref, 1e-12)
        _fc, k, e = fit_ladder(h, fk, fc0=fc)
        rows.append((v, k))
        print('  %.2f   %6.2f    (%4.2f)    %.1f' % (v, k, MG.knob_k(v), e))
    # SELF-OSCILLATION: the oscillators silent, the ladder alone
    alone = dict(base, osc1_level=0.0)
    sv = [round(v, 2) for v in np.linspace(0.7, 1.0, 7)]
    takes = held(rig, 'selfosc', alone, 'resonance', sv, note)
    print('  alone:  knob   level (dBFS)   tone at')
    for v, seg in takes:
        lv = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12)
        tone = pitch(seg) if lv > -60 else 0.0
        print('          %.2f   %6.1f        %s' % (v, lv, ('%.0f Hz' % tone) if tone else '-'))
    return rows


def test_eg(rig):
    """By noise, as the cutoff: the contour held at sustain 1.0, the corner at
    each EG AMOUNT against the corner with no contour at all."""
    base = dict(CAL, kb_track=0.0, resonance=0.0, osc1_level=0.0, noise_level=1.0, cutoff=0.15)
    ref = held(rig, 'eg_open', dict(base, cutoff=1.0), 'cutoff', [1.0], 69, dur=1.6)[0][1]
    f, P0 = psd(ref)
    band = (f > 25.0) & (f < 16000.0)
    open_h = MG.ladder_gain(f, MG.knob_cutoff(1.0), 0.0)

    def corner(seg):
        _f, P = psd(seg)
        h = np.sqrt(P[band] / np.maximum(P0[band], 1e-30)) * open_h[band]
        return fit_ladder(h, f[band], k0=0)
    fz, _k, ez = corner(held(rig, 'eg_zero', base, 'cutoff', [0.15], 69, dur=1.6)[0][1])
    print('  CUTOFF 0.15, no contour: corner %.1f Hz (%.1f dB off)' % (fz, ez))
    vals = [round(v, 2) for v in np.linspace(0.0, 1.0, 21)]
    takes = held(rig, 'eg', dict(base, f_sustain=1.0, f_decay=0.6), 'eg_amount', vals, 69, dur=1.6)
    rows = []
    print('  EG     corner      octaves from it   (the model)    dB off')
    for v, seg in takes:
        fc, _k, e = corner(seg)
        rows.append((v, np.log2(fc / fz), e))
        print('  %.2f  %8.1f Hz   %+6.2f           (%+5.2f)        %.1f'
              % (v, fc, np.log2(fc / fz), MG.eg_octaves(v), e))
    return rows, fz


def envelope(seg, hop=48):
    """RMS in 1 ms frames."""
    n = len(seg) // hop
    return np.sqrt((seg[:n * hop].reshape(n, hop) ** 2).mean(axis=1))


def test_amp(rig):
    base = dict(CAL, a_decay=0.8, a_release=0.5)
    out = {}
    # ATTACK: time to 90% of the plateau; the model's curve gets there at 0.834 A
    vals = [0.3, 0.4, 0.5, 0.6, 0.7]
    rig.panel(base); time.sleep(0.3)

    def play_a(r):
        for v in vals:
            r.panel(dict(base, a_attack=v), knobs=('a_attack',)); time.sleep(0.15)
            r.note(57, 2.0); time.sleep(0.6)
    y = rig.take('attack', len(vals) * 2.75 + 1.5, play_a)
    print('  ATTACK  knob   time (measured)   (model)')
    for v, t in zip(vals, rig.played):
        e = envelope(y[int(t * SR):int((t + 2.0) * SR)])
        top = np.median(e[-300:])
        i0 = int(np.argmax(e > top * 0.02)); i9 = int(np.argmax(e > top * 0.9))
        a = (i9 - i0) / 1000.0 / 0.834
        out.setdefault('attack', []).append((v, a))
        print('          %.2f   %8.1f ms       (%7.1f)' % (v, 1000 * a, 1000 * MG.knob_time(v)))
    # DECAY to nothing, and RELEASE: the time constant of a log-linear fall
    for which in ('decay', 'release'):
        vals = [0.4, 0.5, 0.6, 0.7]
        b2 = dict(base, a_attack=0.0, a_sustain=0.0 if which == 'decay' else 1.0)
        rig.panel(b2); time.sleep(0.3)
        knob = 'a_decay' if which == 'decay' else 'a_release'

        def play_d(r):
            for v in vals:
                r.panel(dict(b2, **{knob: v}), knobs=(knob,)); time.sleep(0.15)
                r.note(57, 3.0 if which == 'decay' else 0.6); time.sleep(3.0 if which == 'release' else 0.4)
        y = rig.take(which, len(vals) * 3.7 + 1.5, play_d)
        print('  %-7s knob   time (measured)   (model)' % which.upper())
        for v, t in zip(vals, rig.played):
            st = t if which == 'decay' else t + 0.6
            e = envelope(y[int(st * SR):int((st + 2.9) * SR)])
            # FROM WHERE IT IS AT ITS TOP: the sound reaches the mixer some
            # milliseconds after the MIDI, so the peak is found, not assumed
            p = int(np.argmax(e[:400]))
            top = e[p]
            tail = e[p:]
            end = int(np.argmax(tail < top * 0.05)) or len(tail)
            idx = np.flatnonzero(tail[:end] < top * 0.8)
            if len(idx) < 5:
                print('          %.2f   (too short to fit)' % v)
                continue
            sl, _c = np.polyfit(idx / 1000.0, np.log(tail[idx]), 1)
            tau = -1.0 / sl
            out.setdefault(which, []).append((v, 4 * tau))
            print('          %.2f   %8.1f ms       (%7.1f)   [tau %.1f ms]'
                  % (v, 4000 * tau, 1000 * MG.knob_time(v), 1000 * tau))
    for k, rows in out.items():
        v = np.array([r[0] for r in rows]); lt = np.log10([max(r[1], 1e-5) for r in rows])
        a, b = np.polyfit(v, lt, 1)
        print('  %s fit: %.2f ms * 10^(%.2f v)  (the model: 1 ms * 10^(4 v))' % (k, 1000 * 10 ** b, a))
    return out


def notes_by_silence(y, quiet_db=-50.0, gap_ms=300):
    """The take's notes as (onset frame, envelope) in 1 ms hops of a 10 ms
    RMS -- found by the silences between them, not by when they were sent:
    a slow attack has no edge to find, and a 1 ms frame on a 4.5 ms period
    reads the waveform, not the envelope."""
    c = np.cumsum(np.r_[0.0, y ** 2])
    w, hop = SR // 100, SR // 1000
    i = np.arange(0, len(y) - w, hop)
    e = np.sqrt((c[i + w] - c[i]) / w)
    quiet = e < np.percentile(e, 90) * 10 ** (quiet_db / 20.0)
    starts, run = [], gap_ms
    for j in range(1, len(e)):
        run = run + 1 if quiet[j - 1] else 0
        if not quiet[j] and run >= gap_ms:
            starts.append(j)
    return [(o, e[o:(starts[k + 1] if k + 1 < len(starts) else len(e))]) for k, o in enumerate(starts)]


def test_attack(rig):
    """ATTACK over its whole travel: the 10, 50 and 90% rise times, with
    sustain full and notes long enough to finish (the shape: an RC charge
    toward T, cut at 1, reaches them at -ln(1 - L/T) time constants); then
    with sustain 0, where the peak lands -- when the charge is cut and the
    decay begins."""
    base = dict(CAL, a_decay=0.8, a_sustain=1.0, a_release=0.3)
    vals = [round(v, 1) for v in np.linspace(0.0, 1.0, 11)]
    durs = [4.5 if v < 0.75 else 14.0 for v in vals]
    rig.panel(base); time.sleep(0.3)

    def play(r):
        for v, d in zip(vals, durs):
            r.panel(dict(base, a_attack=v), knobs=('a_attack',)); time.sleep(0.15)
            r.note(57, d); time.sleep(1.0)
    y = rig.take('attack', sum(durs) + len(vals) * 1.3 + 1.5, play)
    rows = []
    print('  ATTACK   t10     t50     t90 ms   t50/t90  t10/t90')
    for v, (o, seg) in zip(vals, notes_by_silence(y)):
        top = seg.max()
        t10, t50, t90 = [int(np.argmax(seg > top * f)) / 1000.0 for f in (0.1, 0.5, 0.9)]
        rows.append((v, t10, t50, t90, top))
        print('  %.1f  %7.0f %7.0f %7.0f    %.3f    %.3f' % (v, 1000 * t10, 1000 * t50, 1000 * t90,
                                                         t50 / max(t90, 1e-3), t10 / max(t90, 1e-3)))
    base0 = dict(base, a_sustain=0.0, a_decay=0.55)
    pv = [0.3, 0.5, 0.7]
    rig.panel(base0); time.sleep(0.3)

    def play_p(r):
        for v in pv:
            r.panel(dict(base0, a_attack=v), knobs=('a_attack',)); time.sleep(0.15)
            r.note(57, 5.0); time.sleep(1.0)
    y = rig.take('attack_peak', len(pv) * 6.3 + 1.5, play_p)
    print('  SUSTAIN 0: the peak, against the full-sustain t90 and its level')
    for v, (o, seg) in zip(pv, notes_by_silence(y)):
        full = [r for r in rows if r[0] == v][0]
        p = int(np.argmax(seg))
        print('  %.1f  peak at %5d ms  (t90 sustained %5.0f ms)  at %.3f of the sustained top'
              % (v, p, 1000 * full[3], seg[p] / full[4]))
    return rows


def test_times(rig):
    """DECAY and RELEASE over their whole travel, as 4 time constants of a
    log-linear fall (the model's knob time): A5, so a 2.3 ms RMS -- two
    periods -- can follow the shortest; each note measured from where it
    crosses 2% of its own top, never from where it was sent (see PREROLL)."""
    base = dict(CAL, a_attack=0.0, a_decay=0.8, a_sustain=1.0, a_release=0.3)
    vals = [round(v, 2) for v in np.arange(0.0, 0.81, 0.1)]
    out = {}
    for which in ('decay', 'release'):
        knob = 'a_' + which
        b2 = dict(base, a_sustain=0.0 if which == 'decay' else 1.0)
        rig.panel(b2); time.sleep(0.3)
        hold = (lambda v: 6.0) if which == 'decay' else (lambda v: 0.4)
        gap = (lambda v: 0.3) if which == 'decay' else (lambda v: 6.0 if v > 0.6 else 3.0)

        def play(r):
            for v in vals:
                r.panel(dict(b2, **{knob: v}), knobs=(knob,)); time.sleep(0.15)
                r.note(81, hold(v)); time.sleep(gap(v))
        y = rig.take('t_' + which, sum(hold(v) + gap(v) + 0.2 for v in vals) + 1.5, play)
        c = np.cumsum(np.r_[0.0, y ** 2]); w, hop = int(SR * 0.0023), SR // 2000
        i = np.arange(0, len(y) - w, hop)
        e = np.sqrt((c[i + w] - c[i]) / w)                     # 0.5 ms hops
        print('  %-7s knob   4 tau (ms)   (model)' % which.upper())
        for v, t in zip(vals, rig.played):
            a = int((t + 0.1) * 2000)
            seg = e[a:a + int((hold(v) + gap(v) - 0.1) * 2000)]
            top = seg.max(); on = int(np.argmax(seg > top * 0.02))
            st = on + int(np.argmax(seg[on:])) if which == 'decay' else on + int(hold(v) * 2000) - 40
            fall = seg[st:]
            ref = fall[0] if which == 'decay' else np.median(seg[on + 200:st])
            idx = np.flatnonzero((fall < ref * 0.7) & (fall > ref * 0.03))
            idx = idx[idx < (np.argmax(fall < ref * 0.03) or len(fall))]
            if len(idx) < 4:
                print('          %.2f   (too short to fit)' % v); continue
            sl, _c = np.polyfit(idx / 2000.0, np.log(fall[idx]), 1)
            out.setdefault(which, []).append((v, -4.0 / sl))
            print('          %.2f  %9.1f     (%8.1f)' % (v, -4000.0 / sl, 1000 * MG.knob_time(v)))
    return out


def _sweep_harmonics(rig, name, base, knob, vals, note, f0, K=10):
    takes = held(rig, name, base, knob, vals, note, dur=0.9)
    rows = {}
    print('  %-6s h1 dB   h2..h%d dB re h1' % (knob, K))
    for v, seg in takes:
        h = harmonics(seg, f0, K); rows[v] = h
        d = 20 * np.log10(np.maximum(h, 1e-9) / h[0])
        print('  %.3f %6.1f  %s' % (v, 20 * np.log10(h[0] + 1e-12), ' '.join('%5.1f' % x for x in d[1:])))
    return rows


def _shape_err(model, h):
    """dB rms between the shapes (each re its own h1), floored at -45."""
    def db(x):
        return 20 * np.log10(np.maximum(x, 1e-9))
    m, d = db(model / model[0]), db(h / h[0])
    sel = (d > -40) | (m > -40)
    return float(np.sqrt(np.mean((np.clip(m, -45, 0) - np.clip(d, -45, 0))[sel] ** 2)))


def test_wavefull(rig):
    """WAVESHAPE over the whole knob, h1-h10 at every 0.025, against the
    model's: shape error and h1 level (the waves all swing +-1, so the level
    against the saw's checks the landmarks as well)."""
    base = dict(CAL, osc1_level=1.0, osc2_level=0.0, cutoff=1.0)
    vals = [round(v, 3) for v in np.arange(0.0, 1.0001, 0.025)]
    rows = _sweep_harmonics(rig, 'wavefull', base, 'osc1_wave', vals, 57, 220.0 * 2 ** (TUNE_CENTS / 1200))
    saw = rows[0.5][0] / (2 / np.pi)
    print('  wave   shape err dB   h1 level hw-model dB')
    for v, h in rows.items():
        a = 2 * np.abs(MG.osc_spectrum(v, len(h)))
        print('  %.3f   %5.2f        %+5.1f%s' % (v, _shape_err(a, h), 20 * np.log10(h[0] / saw / a[0]),
                                                  '   (the fold: not fitted)' if v < MG.TRI else ''))
    return rows


def test_sub(rig):
    """SUB WAVE over the whole knob, its own harmonics (half the key)."""
    base = dict(CAL, osc1_level=0.0, osc2_level=0.0, sub_level=1.0, cutoff=1.0)
    vals = [round(v, 3) for v in np.arange(0.0, 1.0001, 0.05)]
    rows = _sweep_harmonics(rig, 'subfull', base, 'sub_wave', vals, 57, 110.0 * 2 ** (TUNE_CENTS / 1200))
    print('  sub    shape err dB')
    for v, h in rows.items():
        print('  %.2f   %5.2f' % (v, _shape_err(2 * np.abs(MG.sub_spectrum(v, len(h))), h)))
    return rows


def test_sustain(rig):
    """SUSTAIN: the level the amp contour settles at, against full."""
    base = dict(CAL, a_attack=0.0, a_decay=0.3, a_release=0.3)
    vals = [1.0, 0.0, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
    rig.panel(base); time.sleep(0.3)

    def play(r):
        for v in vals:
            r.panel(dict(base, a_sustain=v), knobs=('a_sustain',)); time.sleep(0.15)
            r.note(81, 2.0); time.sleep(0.8)
    y = rig.take('sustain', len(vals) * 3.0 + 1.5, play)
    lv = [np.sqrt(np.mean(y[int((t + 1.2) * SR):int((t + 1.9) * SR)] ** 2)) for t in rig.played]
    ref = (lv[0] + lv[-1]) / 2.0
    print('  SUSTAIN  level    (model)')
    for v, l in zip(vals, lv):
        print('  %.2f    %.4f   (%.4f)' % (v, l / ref, MG.sustain_level(v)))
    return list(zip(vals, [l / ref for l in lv]))


def pitch_track(seg, hop=960, win=4096):
    """f0 every 20 ms, from the lowest strong harmonic of each window."""
    out = []
    for i in range(0, len(seg) - win, hop):
        out.append(pitch(seg[i:i + win]))
    return np.array(out)


def test_lfo(rig):
    base = dict(CAL, osc1_level=0.0, osc2_level=1.0, osc2_wave=MG.SAW, lfo1_dest=1,
                lfo1_shape=0, lfo1_depth=1.0, lfo1_reset=True)
    vals = [0.3, 0.4, 0.5]
    rig.panel(base); time.sleep(0.3)

    def play(r):
        for v in vals:
            r.panel(dict(base, lfo1_rate=v), knobs=('lfo1_rate',)); time.sleep(0.15)
            r.note(57, 5.0); time.sleep(0.3)
    y = rig.take('lfo', len(vals) * 5.45 + 1.5, play)
    print('  RATE  knob   measured   (model)    pitch swing, octaves either way (model at full)')
    for v, t in zip(vals, rig.played):
        seg = y[int((t + 0.3) * SR):int((t + 4.9) * SR)]
        lv = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12)
        tr = pitch_track(seg)
        tr = tr[np.isfinite(tr)]
        if len(tr) < 50:
            print('        %.2f   no steady pitch (level %.1f dBFS)' % (v, lv))
            continue
        c = 1200 * np.log2(tr / np.median(tr))
        F = np.abs(np.fft.rfft(c - c.mean(), 1 << 14)); fr = np.fft.rfftfreq(1 << 14, 0.02)
        rate = fr[1 + np.argmax(F[1:])]
        swing = (np.percentile(c, 98) - np.percentile(c, 2)) / 2400.0
        print('        %.2f   %6.2f Hz  (%5.2f)    %.2f  (%.2f)' % (v, rate, MG.knob_lfo_rate(v), swing, MG.LFO_PITCH_OCTAVES))


def test_mod(rig):
    base = dict(CAL, osc1_level=0.0, osc2_level=1.0, osc2_wave=MG.SAW, mod_dest=1,
                f_attack=0.0, f_decay=0.3, f_sustain=1.0)
    vals = [0.5, 0.55, 0.6, 0.65, 0.45, 0.4]
    rig.panel(base); time.sleep(0.3)

    def play(r):
        for v in vals:
            r.panel(dict(base, mod_amount=v), knobs=('mod_amount',)); time.sleep(0.15)
            r.note(57, 1.0); time.sleep(0.25)
    y = rig.take('mod', len(vals) * 1.4 + 1.5, play)
    f00 = None
    print('  MOD AMOUNT   OSC 2 at    octaves   (model)')
    for v, t in zip(vals, rig.played):
        f = pitch(y[int((t + 0.4) * SR):int((t + 0.9) * SR)])
        if f00 is None:
            f00 = f
        print('  %.2f        %8.2f Hz  %+.3f   (%+.3f)' % (v, f, np.log2(f / f00), MG.bipolar(v, MG.MOD_PITCH_OCTAVES)))


def model_harmonics(panel, note, K):
    """The model's own render of one held note of `panel`: its harmonics."""
    import json, tempfile
    import blockrender as BR
    path = os.path.join(tempfile.gettempdir(), 'mfit_note.mid')
    m = mido.MidiFile(ticks_per_beat=480); t = mido.MidiTrack(); m.tracks.append(t)
    t += [mido.MetaMessage('set_tempo', tempo=500000),
          mido.Message('program_change', channel=0, program=81),
          mido.Message('note_on', channel=0, note=note, velocity=100, time=0),
          mido.Message('note_off', channel=0, note=note, velocity=0, time=960)]
    m.save(path)
    old = os.environ.get('TUNING_MOOG_PANEL'), os.environ.get('TUNING_REFLECT')
    os.environ['TUNING_MOOG_PANEL'] = json.dumps(panel)
    os.environ['TUNING_REFLECT'] = '0'
    try:
        q = BR.prepare(path, 'even')
        y = BR.synth_window(q, 0, q['N'])[0].astype(float)
    finally:
        for k, v in zip(('TUNING_MOOG_PANEL', 'TUNING_REFLECT'), old):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    seg = y[int(0.4 * BR.SR):int(0.9 * BR.SR)]
    return harmonics(seg, 440.0 * 2 ** ((note - 69) / 12.0), K, BR.SR)


def test_fm(rig):
    """1 -> 2 FM's index against MOD AMOUNT: triangles at unison, each take's
    harmonics fitted by a linear FM of its own (numeric, its index in the
    model's units -- they agree within 2%), energy-weighted. The error says
    where the hardware stops being linear FM (from ~0.65: its exponential FM
    drifts the carrier off the key, and the lines split)."""
    note, K = 57, 12
    base = dict(CAL, osc1_level=0.0, osc2_level=1.0, osc1_wave=MG.TRI, osc2_wave=MG.TRI, mod_dest=0)
    vals = [round(v, 4) for v in np.arange(0.5, 0.7501, 0.0125)] + [0.45, 0.4, 0.35]
    takes = held(rig, 'fm', base, 'mod_amount', vals, note, dur=0.9)
    f0 = pitch(takes[0][1])
    n = 1 << 14
    t = np.arange(n) / float(n)
    tri = lambda ph: 1 - 4 * np.abs((ph % 1.0) - 0.5)
    a = np.cumsum(tri(t)) / n
    a -= a.mean()

    def spec(index):
        c = np.fft.rfft(tri(t + index * a))[1:K + 1] / n
        return 2 * np.abs(c)

    def err(m, h):
        m, h = m / np.sqrt((m ** 2).sum()), h / np.sqrt((h ** 2).sum())
        w = np.maximum(h ** 2, m ** 2)
        return float(np.sqrt(np.sum(w * (20 * np.log10(np.maximum(m, 1e-4) / np.maximum(h, 1e-4))) ** 2) / w.sum()))
    rows = []
    print('  MOD AMOUNT   index   (the model)   dB off')
    for v, seg in takes:
        h = harmonics(seg, f0, K)
        e, i = min((err(spec(x), h), x) for x in np.linspace(0, 5, 1001))
        rows.append((v, i / 1.019, e))
        print('  %.4f      %5.2f   (%5.2f)      %.2f' % (v, i / 1.019, abs(MG.fm_amount_index(v)), e))
    return rows


def _wave_at(h, K=10):
    """Where on WAVESHAPE (triangle up) a measured spectrum stands: the model's
    position whose shape it is (that region now fits within 0.2-2 dB)."""
    best = None
    for g in np.linspace(MG.TRI, 1.0, 267):
        e = _shape_err(2 * np.abs(MG.osc_spectrum(g, K)), h)
        if best is None or e < best[0]:
            best = (e, g)
    return best[1], best[0]


def _noise_corner(rig, base):
    """A corner fitter for windows of a noise take, against the open ladder."""
    ref = held(rig, 'corner_open', dict(base, cutoff=1.0), 'cutoff', [1.0], 69, dur=1.6)[0][1]
    f, P0 = psd(ref)
    band = (f > 25.0) & (f < 16000.0)
    open_h = MG.ladder_gain(f, MG.knob_cutoff(1.0), 0.0)

    def corner(seg):
        _f, P = psd(seg, nper=2048)
        h = np.sqrt(np.interp(f, _f, P)[band] / np.maximum(P0[band], 1e-30)) * open_h[band]
        return fit_ladder(h, f[band], k0=0)[0]
    return corner


def test_lfocut(rig):
    """LFO 1 on the cutoff: a slow square from the key (high first), the
    corner in 0.25 s windows of noise -- its height against DEPTH (a cube),
    and each shape's polarity (the triangle both ways, the rest one way)."""
    base = dict(CAL, kb_track=0.0, resonance=0.0, osc1_level=0.0, noise_level=1.0, cutoff=0.15,
                lfo1_dest=0, lfo1_shape=3, lfo1_rate=MG.lfo_rate_knob(0.5), lfo1_reset=True)
    corner = _noise_corner(rig, dict(base, lfo1_depth=0.5))
    rest = MG.knob_cutoff(0.15)
    print('  DEPTH  shape      octaves re the panel: low .. high   (the model)')
    for shape, vals in ((3, [0.6, 0.65, 0.7, 0.75, 0.8]), (0, [0.75, 0.25]), (3, [0.25]), (1, [0.75]), (2, [0.75])):
        for v, seg in held(rig, 'lfocut%d' % shape, dict(base, lfo1_shape=shape), 'lfo1_depth', vals, 69, dur=4.2):
            w = int(0.25 * SR)
            o = np.log2(np.array([corner(seg[i:i + w]) for i in range(0, len(seg) - w, w)]) / rest)
            lv = MG.lfo(np.linspace(0, 1, 64, endpoint=False), shape) * MG.lfo_cut_octaves(v)
            print('  %.2f   %-9s  %+5.2f .. %+5.2f                    (%+5.2f .. %+5.2f)'
                  % (v, MG.LFO_SHAPES[shape], np.percentile(o, 10), np.percentile(o, 90), lv.min(), lv.max()))


def test_lfopitch(rig):
    """LFO 1 on OSC 2's pitch: the triangle's swing against DEPTH, and the
    square's polarity."""
    base = dict(CAL, osc1_level=0.0, osc2_level=1.0, osc2_wave=MG.SAW, lfo1_dest=1, lfo1_shape=0,
                lfo1_rate=MG.lfo_rate_knob(0.5), lfo1_reset=True)
    runs = [(0, v) for v in (0.6, 0.65, 0.7, 0.75, 0.8, 0.9)] + [(3, 0.7), (3, 0.3)]
    rig.panel(base); time.sleep(0.3)

    def play(r):
        for sh, v in runs:
            r.panel(dict(base, lfo1_shape=sh, lfo1_depth=v), knobs=('lfo1_shape', 'lfo1_depth')); time.sleep(0.2)
            r.note(57, 4.2); time.sleep(0.4)
    y = rig.take('lfopitch', len(runs) * 4.85 + 1.5, play)
    f0 = 220.0 * 2 ** (TUNE_CENTS / 1200)
    print('  shape     depth   octaves: low .. high   (the model)')
    for (sh, v), t in zip(runs, rig.played):
        tr = pitch_track(y[int((t + 0.1) * SR):int((t + 4.1) * SR)])
        o = np.log2(tr[np.isfinite(tr)] / f0)
        lv = MG.lfo(np.linspace(0, 1, 64, endpoint=False), sh) * MG.lfo_pitch_octaves(v)
        print('  %-9s %.2f   %+5.2f .. %+5.2f       (%+5.2f .. %+5.2f)'
              % (MG.LFO_SHAPES[sh], v, np.percentile(o, 3), np.percentile(o, 97), lv.min(), lv.max()))


def test_lfowave(rig):
    """LFO 1 and MOD on a waveshape: how far each moves the knob, the moved
    wave read off its spectrum -- LFO 1 a square from the key (the high half
    against the low), MOD the contour held at full."""
    K = 10
    f0 = 220.0 * 2 ** (TUNE_CENTS / 1200)
    base = dict(CAL, osc1_level=1.0, osc2_level=0.0, cutoff=1.0, osc1_wave=0.35, lfo1_dest=2, lfo1_shape=3,
                lfo1_rate=MG.lfo_rate_knob(0.4), lfo1_reset=True)
    print('  LFO 1 DEPTH   reach   (the model)')
    for v, seg in held(rig, 'lfowave', base, 'lfo1_depth', [0.6, 0.65, 0.7, 0.75, 0.8, 0.9], 57, dur=2.6):
        hi, _e = _wave_at(harmonics(seg[int(0.3 * SR):int(1.1 * SR)], f0, K))
        lo, _e = _wave_at(harmonics(seg[int(1.55 * SR):int(2.35 * SR)], f0, K))
        print('  %.2f          %+.3f  (%+.3f)' % (v, hi - lo, MG.lfo_wave_reach(v)))
    base = dict(CAL, osc1_level=0.0, osc2_level=1.0, osc2_wave=0.35, mod_dest=2, f_attack=0.0, f_sustain=1.0, f_decay=0.3)
    print('  MOD AMOUNT    reach   (the model)')
    for v, seg in held(rig, 'modwave', base, 'mod_amount', [0.55, 0.6, 0.65, 0.7, 0.75, 0.8], 57, dur=1.2):
        g, _e = _wave_at(harmonics(seg[int(0.4 * SR):], f0, K))
        print('  %.2f          %+.3f  (%+.3f)' % (v, g - 0.35, MG.bipolar(v, MG.MOD_WAVE_REACH)))


def test_modes(rig):
    """MODE: |H| of each, by noise at CUTOFF 0.35, against the model's."""
    base = dict(CAL, kb_track=0.0, resonance=0.0, osc1_level=0.0, noise_level=1.0, cutoff=0.35)
    ref = held(rig, 'mode_open', dict(base, cutoff=1.0, mode=0), 'cutoff', [1.0], 69, dur=1.6)[0][1]
    f, P0 = psd(ref)
    open_h = MG.ladder_gain(f, MG.knob_cutoff(1.0), 0.0)
    pts = 2.0 ** np.arange(6.5, 14.01, 0.5)
    print('  Hz       ' + ' '.join('%6.0f' % p for p in pts))
    for m, seg in held(rig, 'modes', base, 'mode', [0, 1, 2, 3], 69, dur=1.6):
        _f, P = psd(seg)
        h = np.sqrt(P / np.maximum(P0, 1e-30)) * open_h
        hw = [20 * np.log10(np.median(h[(f > p / 1.05) & (f < p * 1.05)]) + 1e-9) for p in pts]
        md = 20 * np.log10(MG.ladder_gain(pts, MG.knob_cutoff(0.35), 0.0, m) + 1e-9)
        print('  %-8s ' % MG.MODES[m][:8] + ' '.join('%6.1f' % x for x in hw))
        print('   model   ' + ' '.join('%6.1f' % x for x in md))


def test_mixer(rig):
    """The mixer: a level knob's law (OSC 1), and the noise against a saw in
    100 Hz-2 kHz (above it the path's own roll-off takes the noise's top)."""
    f0 = 220.0 * 2 ** (TUNE_CENTS / 1200)
    vals = [1.0, 0.1, 0.3, 0.5, 0.7, 0.9]
    takes = held(rig, 'mix', dict(CAL, osc1_wave=0.5, cutoff=1.0), 'osc1_level', vals, 57, dur=0.9)
    ref = harmonics(takes[0][1], f0, 1)[0]
    print('  OSC 1 LEVEL  dB re full  (the model)')
    for v, seg in takes:
        print('  %.1f          %+5.1f      (%+5.1f)' % (v, 20 * np.log10(harmonics(seg, f0, 1)[0] / ref), 20 * np.log10(v)))
    saw = takes[0][1]
    noise = held(rig, 'noise', dict(CAL, osc1_level=0.0, noise_level=1.0, cutoff=1.0), 'cutoff', [1.0], 57, dur=1.6)[0][1]
    n = np.arange(len(saw)); w = np.hanning(len(saw))
    a1 = 2 * abs(np.sum(saw * w * np.exp(-2j * np.pi * pitch(saw) * n / SR))) / w.sum()
    X = np.fft.rfft(noise); fr = np.fft.rfftfreq(len(noise), 1.0 / SR)
    X[(fr < 100) | (fr >= 2000)] = 0
    nb = np.sqrt(np.mean(np.fft.irfft(X, len(noise)) ** 2))
    md = MG.NOISE_RMS * np.sqrt(1900 / 10160.0) / (2 / np.pi / np.sqrt(2))
    print('  NOISE in 100 Hz-2 kHz re the saw fundamental: %+.1f dB  (the model %+.1f)'
          % (20 * np.log10(nb / (a1 / np.sqrt(2))), 20 * np.log10(md)))


def test_topcut(rig):
    """THE OUTPUT STAGE: a saw at A5 with the ladder wide open, its harmonics
    against 1/k -- the roll-off that stays put however far CUTOFF goes (and a
    resonant peak that leaves the band from 0.6 rather than standing at the
    top: the ladder is not what stops it). Take the mixer's path ('path') out
    of it to have the Messenger's own (moog.output_gain)."""
    vals = [1.0, 0.8, 0.6]
    takes = held(rig, 'topcut', dict(CAL, osc1_wave=0.5, kb_track=0.0), 'cutoff', vals, 81, dur=1.2)
    f0 = pitch(takes[0][1])
    k = np.arange(1, 19)
    print('  CUTOFF  harmonics (kHz): dB under 1/k      (the model\'s output stage)')
    for v, seg in takes:
        h = harmonics(seg, f0, len(k))
        d = 20 * np.log10(h / h[0]) + 20 * np.log10(k)
        m = 20 * np.log10(MG.output_gain(k * f0) / MG.output_gain(f0))
        print('  %.1f     %s' % (v, '  '.join('%.1fk:%+.1f(%+.1f)' % (kk * f0 / 1000, dd, mm)
                                             for kk, dd, mm in zip(k[2::3], d[2::3], m[2::3]))))


def test_path(rig):
    """THE MIXER'S OWN PATH, for taking out of the others: a log sweep from this
    laptop's headphone out into a mixer channel (--card's), recorded back over
    USB, per third of an octave against 1 kHz. Plug the laptop into a channel
    with FX/PC REC on first; the Messenger is not used."""
    n = int(6.0 * SR)
    t = np.arange(n) / float(SR)
    K = 6.0 / np.log(22000.0 / 20.0)
    y = 0.1 * np.sin(2 * np.pi * 20.0 * K * (np.exp(t / K) - 1))
    y[:480] *= np.linspace(0, 1, 480); y[-480:] *= np.linspace(1, 0, 480)
    path = os.path.join(OUT, 'sweep.wav')
    wavfile.write(path, SR, (np.c_[y, y] * 32767).astype(np.int16))
    r = rig.take('path', 9.0, lambda _r: subprocess.call(['paplay', path]))
    R, P = np.fft.rfft(r, 2 * len(r)), np.fft.rfft(y, 2 * len(r))
    lag = int(np.argmax(np.fft.irfft(R * np.conj(P))))
    Pp, Pr = np.abs(np.fft.rfft(y)) ** 2, np.abs(np.fft.rfft(r[lag:lag + n])) ** 2
    f = np.fft.rfftfreq(n, 1.0 / SR)
    rows = []
    for c in 2.0 ** np.arange(np.log2(40), np.log2(21000), 1 / 3.0):
        m = (f >= c / 2 ** (1 / 6.0)) & (f < c * 2 ** (1 / 6.0))
        rows.append((c, 10 * np.log10(Pr[m].sum() / Pp[m].sum())))
    ref = [g for c, g in rows if c >= 1000][0]
    print('  laptop -> mixer -> USB, dB re 1 kHz:')
    print('  ' + '  '.join('%.0f:%+.1f' % (c, g - ref) for c, g in rows))
    return rows


TESTS = {'tune': test_tune, 'freq': test_freq, 'wave': test_wave, 'cutoff': test_cutoff,
         'res': test_res, 'eg': test_eg, 'amp': test_amp, 'attack': test_attack, 'times': test_times, 'wavefull': test_wavefull, 'sub': test_sub, 'sustain': test_sustain, 'lfo': test_lfo, 'mod': test_mod,
         'fm': test_fm, 'lfocut': test_lfocut, 'lfopitch': test_lfopitch, 'lfowave': test_lfowave,
         'modes': test_modes, 'mixer': test_mixer,
         'topcut': test_topcut, 'path': test_path}


def main(argv):
    args = argv[1:]
    card = int(args[args.index('--card') + 1]) if '--card' in args else 2
    port = args[args.index('--port') + 1] if '--port' in args else 'Messenger'
    names = [a for a in args if a in TESTS] or ['tune']
    rig = Rig(port, card)
    for n in names:
        print(n)
        TESTS[n](rig)
    rig.panel(CAL)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
