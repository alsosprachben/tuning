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
CAL = dict(MG.PANEL, osc1_octave=8, osc1_wave=MG.SAW, osc1_level=1.0, osc2_level=0.0,
           sub_level=0.0, noise_level=0.0, cutoff=1.0, resonance=0.0, eg_amount=0.5,
           kb_track=1.0, mode=MG.LP4, f_sustain=1.0, a_attack=0.0, a_sustain=1.0,
           a_release=0.3, tune=0.5, sync=False, mod_amount=0.5, lfo1_depth=0.5)


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
                                '-r', str(SR), '-c', '2', '-d', str(int(np.ceil(seconds))), path])
        self.t0 = time.monotonic()
        self.played = []
        time.sleep(0.5)
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


TESTS = {'tune': test_tune}


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
